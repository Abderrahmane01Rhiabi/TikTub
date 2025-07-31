import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
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
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
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

def load_video_database():
    """Charge la base de données des vidéos"""
    try:
        if os.path.exists(STATUS_DB):
            with open(STATUS_DB, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"⚠️ Erreur lecture base de données: {e}")
    return {"videos": {}, "batches": {}}

def save_video_database(data):
    """Sauvegarde la base de données des vidéos"""
    try:
        os.makedirs(os.path.dirname(STATUS_DB), exist_ok=True)
        with open(STATUS_DB, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
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
    """Trouve le fichier vidéo correspondant même si le nom a changé"""
    # Fix double slashes
    expected_path = expected_path.replace('//', '/')
    
    # Si le fichier existe déjà, le retourner
    if os.path.exists(expected_path):
        return expected_path
    
    # Chercher dans processed_videos
    processed_dir = Path('processed_videos')
    if not processed_dir.exists():
        return None
    
    # Lister tous les fichiers MP4
    available_files = list(processed_dir.glob('*.mp4'))
    
    if not available_files:
        return None
    
    # Si une seule vidéo disponible, l'utiliser
    if len(available_files) == 1:
        print(f"🔍 Fichier unique trouvé: {available_files[0].name}")
        return str(available_files[0])
    
    # Essayer de matcher par titre/nom
    if video_data:
        search_terms = []
        
        # Ajouter différents termes de recherche
        if video_data.get('custom_title'):
            search_terms.append(video_data['custom_title'].lower())
        if video_data.get('original_title'):
            search_terms.append(video_data['original_title'].lower())
        
        # Chercher un match partiel
        for file_path in available_files:
            filename_lower = file_path.name.lower()
            for term in search_terms:
                # Nettoyer les termes pour la comparaison
                clean_term = ''.join(c for c in term if c.isalnum() or c.isspace()).strip()
                if clean_term and len(clean_term) > 3:
                    if clean_term[:10] in filename_lower or any(word in filename_lower for word in clean_term.split() if len(word) > 3):
                        print(f"🔍 Match trouvé: {file_path.name} (terme: {clean_term})")
                        return str(file_path)
    
    # Sinon, prendre le plus récent
    latest_file = max(available_files, key=lambda f: f.stat().st_mtime)
    print(f"🔍 Fichier le plus récent: {latest_file.name}")
    return str(latest_file)

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
    """Met à jour le statut d'une vidéo après upload"""
    database = load_video_database()
    if video_id in database.get("videos", {}):
        update_data = {
            "youtube_url": youtube_url,
            "youtube_id": youtube_id,
            "uploaded_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        if scheduled_time:
            update_data["status"] = "scheduled_on_youtube"
            update_data["scheduled_publish_time"] = scheduled_time
        else:
            update_data["status"] = "uploaded"
            
        database["videos"][video_id].update(update_data)
        return save_video_database(database)
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
        
        video_data = video['video_data']
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
        
        url = upload_video(
            youtube=youtube,
            video_path=video_path,
            title=title,
            description=description,
            tags=tags,
            video_id=video['video_id'],
            scheduled_time=video['scheduled_time'],
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