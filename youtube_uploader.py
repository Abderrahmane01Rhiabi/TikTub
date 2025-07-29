import os
import sys
from pathlib import Path
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

def upload_video(youtube, video_path, title, description="", tags=None):
    """Upload une vidéo sur YouTube"""
    if tags is None:
        tags = ['Shorts', 'TikTok', 'Viral']

    body = {
        'snippet': {
            'title': title[:100],
            'description': description,
            'tags': tags,
            'categoryId': '24'  # Entertainment
        },
        'status': {
            'privacyStatus': 'public',
            'selfDeclaredMadeForKids': False
        }
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)

    print(f"📤 Upload en cours: {title}")
    print(f"📁 Fichier: {video_path}")

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
        video_id = response.get('id')

        if video_id:
            url = f"https://youtube.com/watch?v={video_id}"
            print(f"✅ Upload réussi!")
            print(f"🔗 URL: {url}")
            return url

    except HttpError as e:
        print(f"❌ Erreur YouTube API: {e}")
    except Exception as e:
        print(f"❌ Erreur upload: {e}")

    return None

def main():
    print("🎥 YouTube Uploader")
    print("==================")

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

    processed_folder = Path('processed_videos/')
    if not processed_folder.exists():
        print("❌ Dossier processed_videos/ introuvable")
        return

    videos = list(processed_folder.glob('*.mp4'))
    if not videos:
        print("❌ Aucune vidéo trouvée dans processed_videos/")
        print("Lance d'abord test3_script.py pour traiter une vidéo TikTok")
        return

    print(f"\n📹 {len(videos)} vidéo(s) trouvée(s):")
    for i, video in enumerate(videos, 1):
        print(f"{i}. {video.name}")

    try:
        choice = int(input(f"\nChoisir une vidéo (1-{len(videos)}): ")) - 1
        selected_video = videos[choice]
    except (ValueError, IndexError):
        print("❌ Choix invalide")
        return

    title = input(f"Titre (ou Enter pour '{selected_video.stem}'): ").strip()
    if not title:
        title = selected_video.stem.replace('_', ' ')

    description = input("Description (optionnel): ").strip()
    if not description:
        description = "Vidéo TikTok retravaillée. Abonne-toi pour plus de contenu!"

    url = upload_video(youtube, str(selected_video), title, description)

    if url:
        print(f"\n🎉 Vidéo uploadée avec succès!")
        print(f"Tu peux la voir sur: {url}")
    else:
        print("\n❌ Échec de l'upload")

if __name__ == "__main__":
    main()