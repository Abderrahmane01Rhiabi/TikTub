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

# Configuration
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.json'
STATUS_DB = 'database/videos_status.json'
SCHEDULE_FILE = 'upload_schedule.json'

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

def authenticate_youtube():
    """Authentification avec YouTube API"""
    creds = None

    # Charge le token existant
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # Si pas de credentials valides, lance le flow OAuth
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            # 👉 Force manual browser authorization (no GUI/browser popup)
            creds = flow.run_local_server(port=0, open_browser=False)

        # Sauvegarde le token
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    return build('youtube', 'v3', credentials=creds)

def upload_video(youtube, video_path, title, description="", tags=None, video_id=None, scheduled_time=None, auto_confirm=False):
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
    """Upload tous les vidéos programmées en une fois"""
    print("🎬 Upload Programmé de Toutes les Vidéos")
    print("======================================")
    
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
    
    print(f"📅 {len(scheduled_videos)} vidéo(s) dans le planning:")
    for i, video in enumerate(scheduled_videos, 1):
        print(f"{i}. {video['title']} → {video['scheduled_time_readable']}")
    
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
    
    confirm = input(f"\n�🚀 Uploader TOUTES les vidéos (mode {mode_text})? (y/n): ")
    if confirm.lower() != 'y':
        print("❌ Upload annulé")
        return
        
    try:
        youtube = authenticate_youtube()
        print("✅ Authentification YouTube réussie\n")
    except Exception as e:
        print(f"❌ Erreur d'authentification: {e}")
        return
    
    success_count = 0
    for i, video in enumerate(scheduled_videos, 1):
        print(f"\n📤 Upload {i}/{len(scheduled_videos)}: {video['title']}")
        
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
            auto_confirm=auto_confirm
        )
        
        if url:
            success_count += 1
            print(f"✅ {video['title']} programmé avec succès!")
        else:
            print(f"❌ Échec: {video['title']}")
        
        # Pause entre uploads
        if i < len(scheduled_videos):
            print("⏳ Pause 3 secondes...")
            import time
            time.sleep(3)
    
    print(f"\n🎉 RÉSUMÉ:")
    print(f"✅ {success_count}/{len(scheduled_videos)} vidéos uploadées")
    print(f"📅 Toutes les vidéos sont maintenant dans YouTube Studio → Scheduled")
    print(f"🤖 YouTube publiera automatiquement aux heures programmées")

def main():
    print("🎥 YouTube Uploader avec IA et Programmation")
    print("============================================")
    
    print("\n📋 OPTIONS:")
    print("1. 📤 Upload vidéo individuelle")
    print("2. 📅 Upload TOUTES les vidéos programmées")
    
    try:
        choice = input("\nChoix (1-2): ").strip()
    except KeyboardInterrupt:
        print("\n👋 Au revoir!")
        return
    
    if choice == "2":
        upload_scheduled_videos()
        return
    elif choice != "1":
        print("❌ Choix invalide")
        return

    if not os.path.exists(CREDENTIALS_FILE):
        print(f"❌ Fichier {CREDENTIALS_FILE} introuvable!")
        print("Assure-toi d'avoir téléchargé le fichier OAuth de Google Cloud Console")
        return

    try:
        youtube = authenticate_youtube()
        print("✅ Authentification YouTube réussie")
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

    url = upload_video(youtube, selected_video_path, title, description, tags, video_id, auto_confirm=auto_confirm)

    if url:
        print(f"\n🎉 Vidéo uploadée avec succès!")
        print(f"Tu peux la voir sur: {url}")
        print(f"📊 Statut mis à jour dans la base de données")
    else:
        print("\n❌ Échec de l'upload")

if __name__ == "__main__":
    main()