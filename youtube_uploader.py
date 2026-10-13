import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Dict

# oauthlib refuses to exchange an authorization code over a plain http://
# redirect URI ("OAuth 2 MUST utilize https") unless this is set. That's
# exactly our case: the app runs locally on http://localhost, which is the
# standard, expected setup for a desktop/local OAuth client — Google's own
# libraries document this env var for precisely that situation. Must be set
# before any Flow/InstalledAppFlow does its token exchange.
os.environ.setdefault('OAUTHLIB_INSECURE_TRANSPORT', '1')

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow, Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# Import multi-channel support
try:
    from channel_manager import ChannelManager
    MULTI_CHANNEL_SUPPORT = True
except ImportError:
    MULTI_CHANNEL_SUPPORT = False
    print("⚠️  Multi-channel support not available")

# Configuration
# youtube.upload alone can't call channels.list(mine=True) — it 403s with
# "insufficientPermissions". youtube.readonly is added so the "Connexion" step
# can show which real YouTube channel got linked (upload-only tokens still
# work for actually publishing, they just can't be used to look themselves up).
# youtube.force-ssl is added so the dashboard can edit a video's schedule/privacy
# after the fact (videos.update) — confirmed by testing that upload+readonly
# alone 403 on that call ("insufficient authentication scopes").
SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/youtube.force-ssl',
    'https://www.googleapis.com/auth/yt-analytics.readonly',
]
CREDENTIALS_FILE = 'credentials.json'  # Fallback for single-channel
TOKEN_FILE = 'token.json'              # Fallback for single-channel
STATUS_DB = 'database/videos_status.json'
SCHEDULE_FILE = 'upload_schedule.json'

def get_credentials_path(channel_name="default"):
    """Get credentials path for specified channel (multi-channel support)"""
    if MULTI_CHANNEL_SUPPORT:
        manager = ChannelManager()
        credentials_path, _ = manager.get_channel_paths(channel_name)
        return credentials_path
    return CREDENTIALS_FILE  # Fallback to single-channel

def get_token_path(channel_name="default"):
    """Get token path for specified channel (multi-channel support)"""
    if MULTI_CHANNEL_SUPPORT:
        manager = ChannelManager()
        _, token_path = manager.get_channel_paths(channel_name)
        return token_path
    return TOKEN_FILE  # Fallback to single-channel

def select_channel():
    """Interactive channel selection (returns channel name)"""
    if not MULTI_CHANNEL_SUPPORT:
        return "default"  # Single-channel mode
        
    manager = ChannelManager()
    channels = manager.list_channels()
    
    if not channels:
        print("❌ No channels configured. Run: python setup_channels.py")
        return None
        
    if len(channels) == 1:
        channel = channels[0]
        print(f"📺 Using channel: {channel['display_name']}")
        return channel['name']
        
    # Multi-channel selection
    return manager.select_channel_interactive()


# ---------------------------------------------------------------------------
# Browser-based OAuth for the web UI's "Connexion" step.
#
# authenticate_youtube() (below) is fine for the CLI: it blocks the calling
# thread in InstalledAppFlow.run_local_server() until the redirect completes.
# That's unusable from a web request (nothing to show the user while it's
# blocked). These two functions split the same flow into two non-blocking
# steps: get an auth_url to open in a popup, then complete it when Google
# redirects back to our own /api/oauth/callback route.
# ---------------------------------------------------------------------------

_pending_oauth_flows = {}  # state -> (Flow, channel_name)


def start_oauth_flow(channel_name: str, redirect_uri: str) -> str:
    """Begin the OAuth flow for a channel. Returns the URL to open in a browser."""
    credentials_path = get_credentials_path(channel_name)
    if not os.path.exists(credentials_path):
        raise FileNotFoundError(f"No credentials.json for channel '{channel_name}': {credentials_path}")

    flow = Flow.from_client_secrets_file(credentials_path, scopes=SCOPES, redirect_uri=redirect_uri)
    auth_url, state = flow.authorization_url(
        access_type='offline', prompt='consent', include_granted_scopes='true'
    )
    _pending_oauth_flows[state] = (flow, channel_name)
    return auth_url


def complete_oauth_flow(state: str, authorization_response_url: str) -> str:
    """Exchange the callback's authorization code for a token, save it, return
    the channel_name this flow was for."""
    entry = _pending_oauth_flows.pop(state, None)
    if not entry:
        raise ValueError("Unknown or expired authorization request (state not found)")

    flow, channel_name = entry
    flow.fetch_token(authorization_response=authorization_response_url)

    token_path = get_token_path(channel_name)
    os.makedirs(os.path.dirname(token_path) or ".", exist_ok=True)
    with open(token_path, 'w') as f:
        f.write(flow.credentials.to_json())

    return channel_name


def get_connected_channel_title(channel_name: str):
    """Returns the real YouTube channel title behind a connected token, or None
    if that channel has no valid token yet. Lets the UI confirm the right
    brand account got linked (several of this user's channels share a Google
    account with multiple brand channels)."""
    token_path = get_token_path(channel_name)
    if not os.path.exists(token_path):
        return None

    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, 'w') as f:
            f.write(creds.to_json())

    youtube = build('youtube', 'v3', credentials=creds)
    response = youtube.channels().list(part='snippet', mine=True).execute()
    items = response.get('items', [])
    return items[0]['snippet']['title'] if items else None


def has_edit_scope(channel_name: str) -> bool:
    """Whether this channel's saved token actually carries youtube.force-ssl
    (needed for the dashboard's visibility/schedule editing) — a plain local
    file read, no API call, so the UI can flag "connected but can't edit yet"
    without waiting on a network round-trip."""
    token_path = get_token_path(channel_name)
    if not os.path.exists(token_path):
        return False
    try:
        with open(token_path, 'r', encoding='utf-8') as f:
            granted = json.load(f).get('scopes', [])
    except (json.JSONDecodeError, OSError):
        return False
    return 'https://www.googleapis.com/auth/youtube.force-ssl' in granted


def get_video_stats(channel_name: str, youtube_video_ids: List[str]) -> Dict[str, Dict]:
    """Batch-fetch live YouTube stats (views/likes/comments, real privacy status,
    thumbnail) for this channel's already-uploaded videos, keyed by youtube_id.

    One videos.list call costs 1 quota unit regardless of how many ids it carries
    (up to 50), so this is cheap even for dozens of videos — chunked at 50 ids
    per call. Returns {} if the channel isn't connected rather than raising, so
    the dashboard can still show locally-known info with no live stats.
    """
    if not youtube_video_ids:
        return {}

    token_path = get_token_path(channel_name)
    if not os.path.exists(token_path):
        return {}

    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, 'w') as f:
            f.write(creds.to_json())

    youtube = build('youtube', 'v3', credentials=creds)
    stats = {}

    for i in range(0, len(youtube_video_ids), 50):
        chunk = youtube_video_ids[i:i + 50]
        response = youtube.videos().list(part='snippet,statistics,status', id=','.join(chunk)).execute()
        for item in response.get('items', []):
            snippet = item.get('snippet', {})
            statistics = item.get('statistics', {})
            status = item.get('status', {})
            thumbnails = snippet.get('thumbnails', {})
            thumb = thumbnails.get('medium') or thumbnails.get('default') or {}

            stats[item['id']] = {
                'view_count': int(statistics['viewCount']) if 'viewCount' in statistics else None,
                'like_count': int(statistics['likeCount']) if 'likeCount' in statistics else None,
                'comment_count': int(statistics['commentCount']) if 'commentCount' in statistics else None,
                'privacy_status': status.get('privacyStatus'),
                'publish_at': status.get('publishAt'),  # future = "programmée"; absent/past + private = "privée"
                'thumbnail_url': thumb.get('url'),
                'published_at': snippet.get('publishedAt'),
            }

    return stats


def has_analytics_scope(channel_name: str) -> bool:
    """Whether this channel's saved token carries yt-analytics.readonly (needed
    for the per-video detailed stats) — local file read, no API call."""
    token_path = get_token_path(channel_name)
    if not os.path.exists(token_path):
        return False
    try:
        with open(token_path, 'r', encoding='utf-8') as f:
            granted = json.load(f).get('scopes', [])
    except (json.JSONDecodeError, OSError):
        return False
    return 'https://www.googleapis.com/auth/yt-analytics.readonly' in granted


def get_video_analytics(channel_name: str, youtube_video_id: str) -> Dict:
    """Detailed YouTube Analytics for ONE published video: watch time, average
    view duration/percentage, traffic sources, real search terms that led to
    it, and its full second-by-second retention curve. All-time (since the
    channel could have been created any time, there's no cheap way to know a
    video's exact publish date here without another API call, so a date range
    starting well before any realistic upload covers it)."""
    token_path = get_token_path(channel_name)
    if not os.path.exists(token_path):
        raise FileNotFoundError(f"Channel '{channel_name}' is not connected")

    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, 'w') as f:
            f.write(creds.to_json())

    yta = build('youtubeAnalytics', 'v2', credentials=creds)
    start_date, end_date = '2020-01-01', datetime.now().strftime('%Y-%m-%d')
    video_filter = f'video=={youtube_video_id}'

    def query(**kwargs):
        try:
            return yta.reports().query(ids='channel==MINE', startDate=start_date, endDate=end_date, **kwargs).execute()
        except HttpError:
            return {'rows': []}

    totals = query(
        metrics='views,likes,dislikes,comments,shares,estimatedMinutesWatched,'
                'averageViewDuration,averageViewPercentage,subscribersGained,subscribersLost',
        filters=video_filter
    )
    totals_row = (totals.get('rows') or [[0] * 10])[0]
    totals_keys = ['views', 'likes', 'dislikes', 'comments', 'shares', 'estimated_minutes_watched',
                   'average_view_duration', 'average_view_percentage', 'subscribers_gained', 'subscribers_lost']

    traffic = query(metrics='views', dimensions='insightTrafficSourceType', filters=video_filter)
    search_terms = query(
        metrics='views', dimensions='insightTrafficSourceDetail',
        filters=f'{video_filter};insightTrafficSourceType==YT_SEARCH', sort='-views', maxResults=15
    )
    retention = query(
        metrics='audienceWatchRatio,relativeRetentionPerformance',
        dimensions='elapsedVideoTimeRatio', filters=video_filter
    )

    return {
        'totals': dict(zip(totals_keys, totals_row)),
        'traffic_sources': [{'type': r[0], 'views': r[1]} for r in traffic.get('rows', [])],
        'search_terms': [{'term': r[0], 'views': r[1]} for r in search_terms.get('rows', [])],
        'retention_curve': [{'elapsed_ratio': r[0], 'watch_ratio': r[1], 'relative_performance': r[2]} for r in retention.get('rows', [])],
    }


def get_channel_analytics(channel_name: str, days: int = 30) -> Dict:
    """Channel-wide YouTube Analytics over the last `days` days: totals, a
    day-by-day view trend, traffic sources, and the top-performing videos
    (any video on the channel, not just ones uploaded through TikTub) — the
    channel-level counterpart to get_video_analytics()."""
    token_path = get_token_path(channel_name)
    if not os.path.exists(token_path):
        raise FileNotFoundError(f"Channel '{channel_name}' is not connected")

    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, 'w') as f:
            f.write(creds.to_json())

    yta = build('youtubeAnalytics', 'v2', credentials=creds)
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    def query(**kwargs):
        try:
            return yta.reports().query(ids='channel==MINE', startDate=start_date, endDate=end_date, **kwargs).execute()
        except HttpError:
            return {'rows': []}

    totals = query(
        metrics='views,likes,comments,shares,estimatedMinutesWatched,'
                'averageViewDuration,averageViewPercentage,subscribersGained,subscribersLost'
    )
    totals_row = (totals.get('rows') or [[0] * 9])[0]
    totals_keys = ['views', 'likes', 'comments', 'shares', 'estimated_minutes_watched',
                   'average_view_duration', 'average_view_percentage', 'subscribers_gained', 'subscribers_lost']

    daily = query(metrics='views', dimensions='day')
    traffic = query(metrics='views', dimensions='insightTrafficSourceType')
    top_videos = query(metrics='views,estimatedMinutesWatched,averageViewPercentage',
                        dimensions='video', sort='-views', maxResults=5)

    youtube = build('youtube', 'v3', credentials=creds)
    top_rows = top_videos.get('rows', [])
    titles = {}
    if top_rows:
        ids = ','.join(r[0] for r in top_rows)
        for item in youtube.videos().list(part='snippet', id=ids).execute().get('items', []):
            titles[item['id']] = item['snippet']['title']

    subscriber_count = None
    ch = youtube.channels().list(part='statistics', mine=True).execute()
    if ch.get('items'):
        stats = ch['items'][0]['statistics']
        subscriber_count = None if stats.get('hiddenSubscriberCount') else int(stats.get('subscriberCount', 0))

    return {
        'period_days': days,
        'subscriber_count': subscriber_count,
        'totals': dict(zip(totals_keys, totals_row)),
        'daily_views': [{'date': r[0], 'views': r[1]} for r in daily.get('rows', [])],
        'traffic_sources': [{'type': r[0], 'views': r[1]} for r in traffic.get('rows', [])],
        'top_videos': [
            {'video_id': r[0], 'title': titles.get(r[0], r[0]), 'views': r[1],
             'estimated_minutes_watched': r[2], 'average_view_percentage': r[3]}
            for r in top_rows
        ],
    }


def update_video_visibility(channel_name: str, youtube_video_id: str,
                             privacy_status: str, publish_at: str = None) -> Dict:
    """Change a video's privacy/schedule directly from the dashboard.

    privacy_status: 'private' | 'public' | 'unlisted'.
    publish_at: ISO 8601 UTC datetime (e.g. "2026-08-30T18:00:00Z") — only
    meaningful together with privacy_status='private' (that's what "programmée"
    means to the YouTube API: private + a future publishAt). Passing publish_at
    with 'public' would be rejected by the API — a video can't have both.
    """
    token_path = get_token_path(channel_name)
    if not os.path.exists(token_path):
        raise FileNotFoundError(f"Channel '{channel_name}' is not connected")

    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, 'w') as f:
            f.write(creds.to_json())

    youtube = build('youtube', 'v3', credentials=creds)

    status = {'privacyStatus': privacy_status}
    if publish_at and privacy_status == 'private':
        status['publishAt'] = publish_at

    response = youtube.videos().update(
        part='status',
        body={'id': youtube_video_id, 'status': status}
    ).execute()
    return response.get('status', {})


def load_video_database():
    """Charge la base de données des vidéos.

    Route vers URLManager (SQLite, voir db.py) plutôt que de lire le fichier
    JSON directement — c'était un deuxième chemin d'accès parallèle à celui
    de batch_processor.py, désormais unifié sur la même source de vérité."""
    try:
        from url_manager import URLManager
        return URLManager().load_database()
    except Exception as e:
        print(f"⚠️ Erreur lecture base de données: {e}")
        return {"videos": {}, "batches": {}}

def save_video_database(data):
    """Sauvegarde la base de données des vidéos (SQLite, via URLManager)"""
    try:
        from url_manager import URLManager
        URLManager().save_database(data)
        return True
    except Exception as e:
        print(f"⚠️ Erreur sauvegarde base de données: {e}")
        return False

def find_video_by_path(database, video_path):
    """Trouve une vidéo dans la base de données par son chemin"""
    video_filename = Path(video_path).name
    for video_id, video_data in database.get("videos", {}).items():
        if video_data.get("video_path") and Path(video_data["video_path"]).name == video_filename:
            return video_id, video_data
    return None, None

def find_matching_video_file(expected_path, video_data=None):
    """Retourne le fichier vidéo enregistré pour cette vidéo, ou None s'il
    n'existe plus. Ne devine JAMAIS un autre fichier (ancien comportement :
    fichier unique / nom approchant / plus récent de processed_videos/) —
    ça pouvait publier la vidéo B sous le titre de la vidéo A. Mieux vaut un
    échec explicite "fichier introuvable" qu'un upload du mauvais contenu."""
    if not expected_path:
        return None
    expected_path = expected_path.replace('//', '/')
    if os.path.exists(expected_path):
        return expected_path
    print(f"❌ Fichier vidéo introuvable: {expected_path}")
    return None

def current_video_data(schedule_entry, database):
    """La ligne vidéo À JOUR (base SQLite), pas la copie figée dans
    upload_schedule.json au moment où le planning a été généré — sinon un
    titre/description/tags corrigé à l'étape "Résultats IA" après la
    génération du planning serait ignoré et l'ancien publié. La copie ne sert
    plus que de secours si la ligne a disparu de la base."""
    return database.get('videos', {}).get(schedule_entry['video_id']) or schedule_entry['video_data']

def convert_to_utc(local_time_str):
    """Convertit un timestamp local en UTC pour YouTube API"""
    try:
        # Parse la date locale avec timezone
        from datetime import datetime
        import dateutil.parser
        
        local_dt = dateutil.parser.parse(local_time_str)
        
        # Convertit en UTC
        utc_dt = local_dt.astimezone(timezone.utc)
        
        # Format pour YouTube API (ISO 8601)
        return utc_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    except Exception as e:
        print(f"⚠️ Erreur conversion UTC: {e}")
        return None

def load_schedule():
    """Charge le planning d'upload"""
    try:
        if os.path.exists(SCHEDULE_FILE):
            with open(SCHEDULE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"⚠️ Erreur lecture planning: {e}")
    return None

def update_video_status(video_id, youtube_url, youtube_id, scheduled_time=None):
    """Met à jour le statut d'une vidéo après upload, puis supprime ses fichiers
    vidéo locaux (brut + traité) — une fois réellement publiée sur YouTube, ils
    n'ont plus besoin de rester sur le disque, où ils s'accumulaient sinon
    indéfiniment (rien d'autre dans le pipeline ne les nettoyait)."""
    # Lecture + écriture ciblées sur CETTE ligne (URLManager.update_video_status),
    # jamais load_all + replace_all de toute la base : ce dernier faisait
    # DELETE FROM videos puis réinsérait l'instantané, effaçant au passage
    # toute écriture faite entre-temps par un thread d'arrière-plan
    # (génération de scripts/audio, stats_tracker).
    from url_manager import URLManager
    import db as _db
    video = _db.get_video(video_id)
    if video:
        update_data = {
            "youtube_url": youtube_url,
            "youtube_id": youtube_id,
            "uploaded_at": datetime.now().isoformat(),
        }
        if scheduled_time:
            status = "scheduled_on_youtube"
            update_data["scheduled_publish_time"] = scheduled_time
        else:
            status = "uploaded"

        try:
            URLManager().update_video_status(video_id, status, **update_data)
        except Exception as e:
            print(f"⚠️ Erreur sauvegarde base de données: {e}")
            return False

        for path_key in ("raw_video_path", "video_path"):
            path = video.get(path_key)
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    print(f"🗑️ Fichier local supprimé ({path_key}): {path}")
                except OSError as e:
                    print(f"⚠️ Impossible de supprimer {path}: {e}")

        return True
    return False

def authenticate_youtube(channel_name="default"):
    """Authentification avec YouTube API (Multi-channel support)"""
    credentials_file = get_credentials_path(channel_name)
    token_file = get_token_path(channel_name)
    
    # Check if credentials file exists
    if not os.path.exists(credentials_file):
        if channel_name != "default":
            print(f"❌ Credentials not found for channel '{channel_name}': {credentials_file}")
            print("Run: python setup_channels.py")
        else:
            print(f"❌ Credentials file not found: {credentials_file}")
            print("Download OAuth credentials from Google Cloud Console")
        return None
        
    creds = None

    # Charge le token existant
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    # Si pas de credentials valides, lance le flow OAuth
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            # 👉 Force manual browser authorization (no GUI/browser popup)
            creds = flow.run_local_server(port=0, open_browser=False)

        # Sauvegarde le token
        # Create directory if it doesn't exist (for multi-channel)
        os.makedirs(os.path.dirname(token_file), exist_ok=True)
        with open(token_file, 'w') as token:
            token.write(creds.to_json())

    return build('youtube', 'v3', credentials=creds)

def upload_video(youtube, video_path, title, description="", tags=None, video_id=None, scheduled_time=None, auto_confirm=False, channel_name="default"):
    """Upload une vidéo sur YouTube avec données AI et scheduling optionnel"""
    if tags is None:
        tags = ['Shorts', 'TikTok', 'Viral']

    # Nettoie et limite les tags (YouTube limite à 500 caractères total)
    clean_tags = []
    total_length = 0
    for tag in tags[:15]:  # Max 15 tags
        tag = str(tag).strip()
        if tag and total_length + len(tag) < 450:  # Sécurité pour la limite
            clean_tags.append(tag)
            total_length += len(tag)

    # Configuration du statut selon scheduling
    status_config = {
        'selfDeclaredMadeForKids': False
    }
    
    if scheduled_time:
        # Upload programmé
        utc_time = convert_to_utc(scheduled_time)
        if utc_time:
            status_config['privacyStatus'] = 'private'
            status_config['publishAt'] = utc_time
            print(f"📅 Programmé pour: {scheduled_time} (UTC: {utc_time})")
        else:
            print("⚠️ Erreur conversion horaire, upload immédiat")
            status_config['privacyStatus'] = 'public'
    else:
        # Upload immédiat
        status_config['privacyStatus'] = 'public'

    body = {
        'snippet': {
            'title': title[:100],  # YouTube limite à 100 caractères
            'description': description[:5000],  # YouTube limite à 5000 caractères
            'tags': clean_tags,
            'categoryId': '24'  # Entertainment
        },
        'status': status_config
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)

    if scheduled_time:
        print(f"📤 Upload programmé: {title}")
        print(f"📅 Publication: {scheduled_time}")
    else:
        print(f"📤 Upload immédiat: {title}")
    
    print(f"📁 Fichier: {video_path}")
    print(f"🏷️ Tags: {', '.join(clean_tags[:5])}{'...' if len(clean_tags) > 5 else ''}")

    if auto_confirm:
        print("🚀 Upload automatique activé - pas de confirmation")
        confirm = 'y'
    else:
        confirm = input("Confirmer l'upload? (y/n): ")
    
    if confirm.lower() != 'y':
        print("❌ Upload annulé")
        return None

    try:
        request = youtube.videos().insert(
            part='snippet,status',
            body=body,
            media_body=media
        )
        response = request.execute()
        youtube_video_id = response.get('id')

        if youtube_video_id:
            url = f"https://youtube.com/watch?v={youtube_video_id}"
            print(f"✅ Upload réussi!")
            print(f"🔗 URL: {url}")
            
            if scheduled_time:
                print(f"📅 Vidéo programmée dans YouTube Studio")
                print(f"🕐 Publication automatique: {scheduled_time}")
            
            # Met à jour la base de données
            if video_id:
                if update_video_status(video_id, url, youtube_video_id, scheduled_time):
                    status_msg = "programmée" if scheduled_time else "uploadée"
                    print(f"📊 Statut mis à jour: {status_msg}")
                else:
                    print(f"⚠️ Erreur mise à jour statut")
            
            return url

    except HttpError as e:
        print(f"❌ Erreur YouTube API: {e}")
    except Exception as e:
        print(f"❌ Erreur upload: {e}")

    return None

def upload_scheduled_videos():
    """Upload tous les vidéos programmées en une fois (Multi-channel support)"""
    print("🎬 Upload Programmé de Toutes les Vidéos")
    print("======================================")
    
    # Select channel first
    channel_name = select_channel()
    if not channel_name:
        return
    
    # Charge le planning
    schedule_data = load_schedule()
    if not schedule_data:
        print("❌ Aucun planning trouvé")
        print("💡 Lance d'abord batch_processor.py → option 3 pour créer un planning")
        return
    
    scheduled_videos = schedule_data.get('schedule', [])
    if not scheduled_videos:
        print("❌ Aucune vidéo dans le planning")
        return
    
    print(f"📺 Channel: {channel_name}")
    print(f"📅 {len(scheduled_videos)} vidéo(s) dans le planning:")
    
    # Check which videos are already uploaded
    database = load_video_database()
    videos_to_upload = []
    
    for i, video in enumerate(scheduled_videos, 1):
        video_id = video['video_id']
        video_data = database.get('videos', {}).get(video_id, {})
        status = video_data.get('status', 'unknown')
        
        # Check if video is already uploaded
        if status in ['uploaded', 'scheduled_on_youtube']:
            # Get channel info from video data
            uploaded_channel = "Unknown"
            if video_data.get('youtube_url'):
                # Try to get channel from multi-channel info or assume current channel
                uploaded_channel = video_data.get('uploaded_channel', channel_name)
            
            if status == 'uploaded':
                status_icon = "✅"
                status_text = f"Already uploaded to {uploaded_channel}"
            else:
                status_icon = "📅"  
                status_text = f"Already scheduled on {uploaded_channel}"
                
            print(f"{i}. {status_icon} {video['title']} → {video['scheduled_time_readable']}")
            print(f"   {status_text}")
            
            # Skip if already on target channel
            if uploaded_channel.lower() == channel_name.lower():
                print(f"   ⏭️  Skipping - already exists on target channel")
                continue
            else:
                print(f"   🔄 Will re-upload to {channel_name}")
                videos_to_upload.append(video)
                
        else:
            # Video not uploaded yet
            print(f"{i}. 📦 {video['title']} → {video['scheduled_time_readable']}")
            print(f"   Status: {status} - Ready for upload")
            videos_to_upload.append(video)
    
    if not videos_to_upload:
        print(f"\n✅ All videos are already uploaded to {channel_name}!")
        print("💡 Use option 3 to re-upload videos to different channels")
        return
    
    print(f"\n🚀 MODE D'UPLOAD:")
    print("1. 🤖 Automatique (pas de confirmation)")
    print("2. 🛡️ Manuel (confirmer chaque upload)")
    
    try:
        mode_choice = input("Choisir le mode (1-2, défaut: 2): ").strip()
    except KeyboardInterrupt:
        print("\n� Au revoir!")
        return
    
    auto_confirm = mode_choice == "1"
    mode_text = "automatique" if auto_confirm else "manuel"
    
    print(f"\n📊 UPLOAD SUMMARY:")
    print(f"📹 Videos to upload: {len(videos_to_upload)}")
    print(f"📺 Target channel: {channel_name}")
    print(f"🚀 Mode: {mode_text}")
    
    confirm = input(f"\n🚀 Uploader {len(videos_to_upload)} vidéo(s) (mode {mode_text})? (y/n): ")
    if confirm.lower() != 'y':
        print("❌ Upload annulé")
        return
        
    try:
        youtube = authenticate_youtube(channel_name)
        print(f"✅ Authentification YouTube réussie pour {channel_name}\n")
    except Exception as e:
        print(f"❌ Erreur d'authentification: {e}")
        return
    
    success_count = 0
    for i, video in enumerate(videos_to_upload, 1):
        print(f"\n📤 Upload {i}/{len(videos_to_upload)}: {video['title']}")
        
        video_data = current_video_data(video, database)
        ai_data = video_data.get('ai_data', {})
        
        # Utilise les données AI optimisées
        title = ai_data.get('optimized_title') or video['title']
        description = video_data.get('custom_description') or ai_data.get('description_suggestions', [''])[0]
        tags = ai_data.get('tags', ['Shorts', 'TikTok', 'Viral'])
        
        # Upload avec scheduling
        video_path = find_matching_video_file(video_data['video_path'], video_data)
        
        if not video_path:
            print(f"❌ Aucun fichier vidéo trouvé pour: {video['title']}")
            continue
        
        print(f"📁 Utilisation du fichier: {video_path}")

        # 'publish_now' (set via the "Publier maintenant" toggle in Planning)
        # means upload immediately as public instead of private+scheduled —
        # upload_video() already treats scheduled_time=None as an immediate
        # public upload, so no other change is needed here.
        scheduled_time = None if video.get('publish_now') else video['scheduled_time']

        url = upload_video(
            youtube=youtube,
            video_path=video_path,
            title=title,
            description=description,
            tags=tags,
            video_id=video['video_id'],
            scheduled_time=scheduled_time,
            auto_confirm=auto_confirm,
            channel_name=channel_name
        )
        
        if url:
            success_count += 1
            print(f"✅ {video['title']} programmé avec succès!")
        else:
            print(f"❌ Échec: {video['title']}")
        
        # Pause entre uploads
        if i < len(videos_to_upload):
            print("⏳ Pause 3 secondes...")
            import time
            time.sleep(3)
    
    print(f"\n🎉 RÉSUMÉ:")
    print(f"✅ {success_count}/{len(videos_to_upload)} vidéos uploadées")
    print(f"📅 Toutes les vidéos sont maintenant dans YouTube Studio → Scheduled")
    print(f"🤖 YouTube publiera automatiquement aux heures programmées")

def upload_all_channels_schedule(auto_confirm: bool = True) -> List[Dict]:
    """Publie le planning entier, en itérant sur toutes les chaînes qui y apparaissent
    (mode multi-chaînes de la UI web : un seul bouton "Publier tout")."""
    schedule_data = load_schedule()
    if not schedule_data:
        return []

    channels = set()
    for video in schedule_data.get('schedule', []):
        channels.add(video.get('channel') or video.get('video_data', {}).get('channel', 'default'))

    all_results = []
    for channel_name in sorted(channels):
        for result in upload_channel_schedule(channel_name, auto_confirm=auto_confirm):
            result['channel'] = channel_name
            all_results.append(result)

    return all_results

def upload_channel_schedule(channel_name: str, auto_confirm: bool = True) -> List[Dict]:
    """Non-interactive variant of upload_scheduled_videos(), for the web UI: uploads
    every scheduled video whose target channel matches `channel_name`, with no input().
    Returns a list of {video_id, title, success, url, error}."""
    results = []

    schedule_data = load_schedule()
    if not schedule_data:
        return results

    scheduled_videos = schedule_data.get('schedule', [])
    database = load_video_database()

    videos_to_upload = []
    for video in scheduled_videos:
        video_channel = video.get('channel') or video.get('video_data', {}).get('channel', 'default')
        if video_channel != channel_name:
            continue

        video_id = video['video_id']
        status = database.get('videos', {}).get(video_id, {}).get('status', 'unknown')
        if status in ('uploaded', 'scheduled_on_youtube'):
            continue

        videos_to_upload.append(video)

    if not videos_to_upload:
        return results

    try:
        youtube = authenticate_youtube(channel_name)
    except Exception as e:
        return [{"video_id": None, "title": None, "success": False, "url": None, "error": str(e)}]

    if not youtube:
        return [{"video_id": None, "title": None, "success": False, "url": None,
                  "error": f"Authentication failed for channel '{channel_name}'"}]

    for video in videos_to_upload:
        video_data = current_video_data(video, database)
        ai_data = video_data.get('ai_data', {})

        title = ai_data.get('optimized_title') or video['title']
        description = video_data.get('custom_description') or (ai_data.get('description_suggestions') or [''])[0]
        tags = ai_data.get('tags', ['Shorts', 'TikTok', 'Viral'])

        video_path = find_matching_video_file(video_data['video_path'], video_data)
        if not video_path:
            results.append({"video_id": video['video_id'], "title": video['title'],
                             "success": False, "url": None, "error": "Video file not found"})
            continue

        # 'publish_now' (set via the "Publier maintenant" toggle in Planning)
        # means upload immediately as public instead of private+scheduled —
        # upload_video() already treats scheduled_time=None as an immediate
        # public upload, so no other change is needed here.
        scheduled_time = None if video.get('publish_now') else video['scheduled_time']

        url = upload_video(
            youtube=youtube,
            video_path=video_path,
            title=title,
            description=description,
            tags=tags,
            video_id=video['video_id'],
            scheduled_time=scheduled_time,
            auto_confirm=auto_confirm,
            channel_name=channel_name
        )

        results.append({
            "video_id": video['video_id'], "title": title,
            "success": bool(url), "url": url,
            "error": None if url else "Upload failed"
        })

    return results

def reupload_to_different_channel():
    """Re-upload a previously uploaded video to a different channel"""
    print("\n🔄 RE-UPLOAD TO DIFFERENT CHANNEL")
    print("=" * 50)
    
    # Select target channel first
    channel_name = select_channel()
    if not channel_name:
        return
    
    # Load database to find uploaded videos
    database = load_video_database()
    uploaded_videos = []
    
    for video_id, video_data in database.get("videos", {}).items():
        status = video_data.get("status", "")
        if status in ["uploaded", "scheduled_on_youtube"]:
            title = video_data.get("ai_data", {}).get("optimized_title") or video_data.get("original_title", "Unknown")
            video_path = video_data.get("video_path", "")
            uploaded_videos.append({
                "id": video_id,
                "title": title,
                "path": video_path,
                "status": status,
                "data": video_data
            })
    
    if not uploaded_videos:
        print("❌ No uploaded videos found")
        print("💡 Upload some videos first, then use this feature")
        return
    
    print(f"📺 Target Channel: {channel_name}")
    print(f"📹 Found {len(uploaded_videos)} uploaded videos:")
    print()
    
    for i, video in enumerate(uploaded_videos, 1):
        print(f"{i}. {video['title'][:60]}{'...' if len(video['title']) > 60 else ''}")
        print(f"   Status: {video['status']} | File: {Path(video['path']).name}")
        print()
    
    try:
        choice = input("Select video to re-upload (number): ").strip()
        if not choice.isdigit():
            print("❌ Invalid selection")
            return
            
        idx = int(choice) - 1
        if not (0 <= idx < len(uploaded_videos)):
            print("❌ Invalid selection")
            return
            
        selected_video = uploaded_videos[idx]
        video_data = selected_video["data"]
        
        print(f"\n🔄 Re-uploading: {selected_video['title']}")
        print(f"📺 To channel: {channel_name}")
        
        # Check if video file exists
        video_path = find_matching_video_file(video_data["video_path"], video_data)
        if not video_path:
            print(f"❌ Video file not found: {video_data['video_path']}")
            return
        
        # Authenticate
        try:
            youtube = authenticate_youtube(channel_name)
            print(f"✅ Authentication successful for {channel_name}")
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return
        
        # Use existing AI data but allow editing
        ai_data = video_data.get("ai_data", {})
        original_title = ai_data.get("optimized_title") or video_data.get("original_title", "Untitled")
        original_description = ai_data.get("description_suggestions", [""])[0] if ai_data.get("description_suggestions") else "Viral content!"
        original_tags = ai_data.get("tags", ['Shorts', 'TikTok', 'Viral'])
        
        print(f"\n� EDIT CONTENT FOR {channel_name}")
        print("=" * 40)
        
        # Edit title
        print(f"\n🤖 IA - Titre suggéré: {original_title}")
        title = input("Titre (Enter pour utiliser IA): ").strip()
        if not title:
            title = original_title
        
        # Edit description  
        print(f"\n🤖 IA - Description suggérée: {original_description}")
        description = input("Description (Enter pour utiliser IA): ").strip()
        if not description:
            description = original_description
        
        # Edit tags
        print(f"\n🤖 IA - Tags: {', '.join(original_tags[:10])}")
        use_ai_tags = input("Utiliser les tags IA? (y/n, défaut: y): ").strip().lower()
        if use_ai_tags in ['', 'y', 'yes', 'oui']:
            tags = original_tags
        else:
            manual_tags = input("Tags manuels (séparés par virgules): ").strip()
            tags = [tag.strip() for tag in manual_tags.split(',')] if manual_tags else original_tags
        
        print(f"\n📋 RÉSUMÉ:")
        print(f"📺 Channel: {channel_name}")
        print(f"📺 Titre: {title}")
        print(f"📝 Description: {description[:100]}{'...' if len(description) > 100 else ''}")
        print(f"🏷️ Tags: {', '.join(tags[:5])}{'...' if len(tags) > 5 else ''}")
        
        # Mode de confirmation
        print(f"\n🚀 MODE D'UPLOAD:")
        print("1. 🤖 Upload automatique")
        print("2. 🛡️ Demander confirmation")
        
        try:
            mode_choice = input("Choisir le mode (1-2, défaut: 2): ").strip()
        except KeyboardInterrupt:
            print("\n👋 Re-upload cancelled")
            return
            
        auto_confirm = mode_choice == "1"
        
        confirm = input(f"\n🚀 Upload to {channel_name}? (y/n): ").lower().strip()
        if confirm != 'y':
            print("❌ Upload cancelled")
            return
        
        # Upload video
        url = upload_video(
            youtube=youtube,
            video_path=video_path,
            title=title,
            description=description,
            tags=tags,
            video_id=selected_video["id"] + "_reupload",
            auto_confirm=auto_confirm,
            channel_name=channel_name
        )
        
        if url:
            print(f"\n🎉 Video re-uploaded successfully to {channel_name}!")
            print(f"🔗 URL: {url}")
        else:
            print(f"\n❌ Re-upload failed")
            
    except KeyboardInterrupt:
        print("\n👋 Re-upload cancelled")

def main():
    print("🎥 YouTube Uploader avec IA et Programmation")
    print("============================================")
    
    # Multi-channel support check
    if MULTI_CHANNEL_SUPPORT:
        print("📺 Multi-Channel Support: ✅ Enabled")
    
    print("\n📋 OPTIONS:")
    print("1. 📤 Upload vidéo individuelle")
    print("2. 📅 Upload TOUTES les vidéos programmées")
    print("3. 🔄 Re-upload video to different channel")
    if MULTI_CHANNEL_SUPPORT:
        print("4. ⚙️  Manage channels")
    
    try:
        choice = input(f"\nChoix (1-{4 if MULTI_CHANNEL_SUPPORT else 3}): ").strip()
    except KeyboardInterrupt:
        print("\n👋 Au revoir!")
        return
    
    if choice == "2":
        upload_scheduled_videos()
        return
    elif choice == "3":
        reupload_to_different_channel()
        return
    elif MULTI_CHANNEL_SUPPORT and choice == "4":
        print("🔧 Pour gérer les channels, lance: python setup_channels.py")
        return
    elif choice != "1":
        print("❌ Choix invalide")
        return

    # Select channel for individual upload
    channel_name = select_channel()
    if not channel_name:
        return

    # Check credentials for selected channel
    credentials_file = get_credentials_path(channel_name)
    if not os.path.exists(credentials_file):
        print(f"❌ Fichier credentials introuvable pour {channel_name}: {credentials_file}")
        if MULTI_CHANNEL_SUPPORT:
            print("Lance: python setup_channels.py pour configurer tes channels")
        else:
            print("Assure-toi d'avoir téléchargé le fichier OAuth de Google Cloud Console")
        return

    try:
        youtube = authenticate_youtube(channel_name)
        print(f"✅ Authentification YouTube réussie pour {channel_name}")
    except Exception as e:
        print(f"❌ Erreur d'authentification: {e}")
        return

    # Charge la base de données
    database = load_video_database()
    
    # Trouve les vidéos prêtes pour upload
    ready_videos = []
    for video_id, video_data in database.get("videos", {}).items():
        if video_data.get("status") == "ready_for_upload" and video_data.get("video_path"):
            # Utilise le smart finder
            actual_video_path = find_matching_video_file(video_data["video_path"], video_data)
            if actual_video_path:
                ready_videos.append((video_id, video_data, actual_video_path))

    if not ready_videos:
        print("❌ Aucune vidéo prête pour upload trouvée")
        print("💡 Lance d'abord batch_processor.py pour traiter des vidéos")
        return

    print(f"\n📹 {len(ready_videos)} vidéo(s) prête(s) pour upload:")
    for i, (video_id, video_data, video_path) in enumerate(ready_videos, 1):
        filename = Path(video_path).name
        ai_title = video_data.get("ai_data", {}).get("optimized_title", "")
        custom_title = video_data.get("custom_title", "")
        title_preview = ai_title or custom_title or filename
        print(f"{i}. {title_preview[:50]}{'...' if len(title_preview) > 50 else ''}")

    try:
        choice = int(input(f"\nChoisir une vidéo (1-{len(ready_videos)}): ")) - 1
        video_id, video_data, selected_video_path = ready_videos[choice]
    except (ValueError, IndexError):
        print("❌ Choix invalide")
        return

    # Utilise les données AI si disponibles
    ai_data = video_data.get("ai_data", {})
    
    # Titre optimisé
    suggested_title = (
        ai_data.get("optimized_title") or 
        video_data.get("custom_title") or 
        Path(selected_video_path).stem.replace('_', ' ')
    )
    
    print(f"\n🤖 IA - Titre suggéré: {suggested_title}")
    title = input(f"Titre (Enter pour utiliser IA): ").strip()
    if not title:
        title = suggested_title

    # Description optimisée
    suggested_descriptions = ai_data.get("description_suggestions", [])
    custom_description = video_data.get("custom_description")
    
    if custom_description:
        suggested_desc = custom_description
    elif suggested_descriptions:
        suggested_desc = suggested_descriptions[0]
    else:
        suggested_desc = "Vidéo TikTok retravaillée. Abonne-toi pour plus de contenu!"
    
    print(f"\n🤖 IA - Description suggérée: {suggested_desc}")
    description = input("Description (Enter pour utiliser IA): ").strip()
    if not description:
        description = suggested_desc

    # Tags AI
    ai_tags = ai_data.get("tags", ['Shorts', 'TikTok', 'Viral'])
    print(f"\n🤖 IA - Tags: {', '.join(ai_tags[:10])}")
    
    use_ai_tags = input("Utiliser les tags IA? (y/n, défaut: y): ").strip().lower()
    if use_ai_tags in ['', 'y', 'yes', 'oui']:
        tags = ai_tags
    else:
        manual_tags = input("Tags manuels (séparés par virgules): ").strip()
        tags = [tag.strip() for tag in manual_tags.split(',')] if manual_tags else ['Shorts', 'TikTok', 'Viral']

    print(f"\n📋 RÉSUMÉ:")
    print(f"📺 Titre: {title}")
    print(f"📝 Description: {description[:100]}{'...' if len(description) > 100 else ''}")
    print(f"🏷️ Tags: {', '.join(tags[:5])}{'...' if len(tags) > 5 else ''}")

    # Mode de confirmation
    print(f"\n🚀 MODE D'UPLOAD:")
    print("1. 🤖 Upload automatique")
    print("2. 🛡️ Demander confirmation")
    
    try:
        mode_choice = input("Choisir le mode (1-2, défaut: 2): ").strip()
    except KeyboardInterrupt:
        print("\n👋 Au revoir!")
        return
        
    auto_confirm = mode_choice == "1"

    url = upload_video(youtube, selected_video_path, title, description, tags, video_id, auto_confirm=auto_confirm, channel_name=channel_name)

    if url:
        print(f"\n🎉 Vidéo uploadée avec succès!")
        print(f"Tu peux la voir sur: {url}")
        print(f"📊 Statut mis à jour dans la base de données")
    else:
        print("\n❌ Échec de l'upload")

if __name__ == "__main__":
    main()