#!/usr/bin/env python3
"""
Batch Processor - Système complet TikTok → YouTube automatisé
===========================================================
Workflow: URLs → Download → Process → AI Tags → Schedule → Upload
"""

import os
import sys
import yaml
import json
from pathlib import Path
from datetime import datetime
import logging

# Imports des modules créés
from url_manager import URLManager
from ai_tags_generator import AITagsGenerator  
from youtube_scheduler import YouTubeScheduler

# Import multi-channel support
try:
    from channel_manager import ChannelManager
    MULTI_CHANNEL_SUPPORT = True
except ImportError:
    MULTI_CHANNEL_SUPPORT = False
    print("⚠️  Multi-channel support not available")

# Import analytics-based scheduling
try:
    from smart_scheduler import SmartScheduler
    ANALYTICS_SUPPORT = True
    print("✨ Analytics-based scheduling available!")
except ImportError:
    ANALYTICS_SUPPORT = False
    print("⚠️  Analytics scheduling not available")

# Import AI-suggested scheduling (per-video, content/channel-aware)
try:
    from ai_scheduler import AIScheduler
    AI_SCHEDULING_SUPPORT = True
except ImportError:
    AI_SCHEDULING_SUPPORT = False
    print("⚠️  AI-suggested scheduling not available")

from typing import Dict, List, Optional  # add any other needed types here


# Import du script TikTok existant (modifié)
# from test3_script import process_video_with_background_options, download_tiktok_video

# Import du script YouTube existant
# from youtube_uploader import authenticate_youtube, upload_video

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BatchProcessor:
    def __init__(self, config_path="config.yaml"):
        self.load_config(config_path)
        self.url_manager = URLManager()
        self.ai_generator = AITagsGenerator()
        self.scheduler = YouTubeScheduler(config_path)
        self.youtube_service = None
        
        # Initialize multi-channel support
        if MULTI_CHANNEL_SUPPORT:
            self.channel_manager = ChannelManager()
        
        # Initialize analytics-based scheduling
        if ANALYTICS_SUPPORT:
            self.smart_scheduler = SmartScheduler()
            self.smart_scheduler.load_analytics_cache()
            print("📊 Analytics-based scheduling initialized")

        # Initialize AI-suggested scheduling (per-video, channel/content-aware —
        # also fed real analytics peak-hours when available, see AIScheduler)
        if AI_SCHEDULING_SUPPORT:
            self.ai_scheduler = AIScheduler(self.ai_generator, smart_scheduler=getattr(self, 'smart_scheduler', None))
        
    def load_config(self, config_path: str):
        """Charge la configuration"""
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
    
    def process_url_file(self, file_path: str, batch_name: str = None, channel_name: str = "default") -> str:
        """Traite un fichier d'URLs et crée un batch, tagué avec la chaîne cible"""
        if not batch_name:
            batch_name = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        print(f"📋 Traitement du fichier: {file_path}")

        # Parse le fichier d'URLs
        videos = self.url_manager.parse_url_file(file_path)
        if not videos:
            print("❌ Aucune URL valide trouvée")
            return None

        print(f"✅ {len(videos)} URLs trouvées")

        # Tague chaque vidéo avec sa chaîne de destination
        for video in videos:
            video['channel'] = channel_name

        # Ajoute le batch à la base
        batch_id = self.url_manager.add_batch(batch_name, videos)

        return batch_id

    def process_channel_url_file(self, channel_name: str, filename: str, batch_name: str = None) -> str:
        """Traite un fichier d'URLs situé dans channels/<channel_name>/urls_input/"""
        if not MULTI_CHANNEL_SUPPORT:
            raise RuntimeError("Multi-channel support not available")

        urls_dir = self.channel_manager.get_urls_input_dir(channel_name)
        file_path = os.path.join(urls_dir, filename)
        if not os.path.exists(file_path):
            print(f"❌ Fichier introuvable: {file_path}")
            return None

        return self.process_url_file(file_path, batch_name=batch_name, channel_name=channel_name)
    
    def download_and_process_batch(self, batch_id: str, background_strategy: str = "random"):
        """Télécharge et traite toutes les vidéos d'un batch"""
        print(f"🔄 Traitement du batch: {batch_id}")
        
        # Récupère les vidéos du batch
        db = self.url_manager.load_database()
        batch_videos = [v for v in db['videos'].values() if v['batch_id'] == batch_id]
        
        if not batch_videos:
            print("❌ Batch introuvable")
            return
        
        print(f"📹 {len(batch_videos)} vidéos à traiter")
        
        # Show video statuses
        print("\n📊 Statuts des vidéos:")
        for video in batch_videos:
            print(f"  - {video['url'][:50]}... : {video['status']}")
        
        # Ask if user wants to reprocess videos
        reprocess = input("\n🔄 Reprocesser les vidéos déjà traitées? (y/n): ").lower() == 'y'
        
        # Détermine la stratégie de background
        if background_strategy == "same_for_all":
            global_background = self.choose_global_background()
        else:
            global_background = None
        
        processed_count = 0
        
        for video in batch_videos:
            # Skip only if not pending AND user doesn't want to reprocess
            if video['status'] != 'pending' and not reprocess:
                print(f"⏭️ Skipping {video['url'][:50]}... (status: {video['status']})")
                continue
            
            print(f"\n🔄 Traitement: {video['url']}")
            
            try:
                # Reset status if reprocessing
                if video['status'] != 'pending':
                    print(f"🔄 Reprocessing video with status: {video['status']}")
                
                # Étape 1: Téléchargement
                self.url_manager.update_video_status(
                    video['video_id'], 
                    'downloading'
                )
                
                video_path, title, tiktok_meta = self.download_tiktok_video(video['url'], video_id=video['video_id'])
                if not video_path:
                    self.url_manager.update_video_status(
                        video['video_id'],
                        'download_failed'
                    )
                    continue

                video.update(tiktok_meta)  # so generate_ai_content() below can use the real TikTok caption
                
                # Étape 2: Traitement vidéo
                self.url_manager.update_video_status(
                    video['video_id'], 
                    'processing'
                )
                
                # Détermine le mode background
                bg_mode = self.determine_background_mode(
                    video, background_strategy, global_background
                )
                
                processed_path = self.process_tiktok_video(
                    video_path, title, bg_mode
                )
                
                if not processed_path:
                    self.url_manager.update_video_status(
                        video['video_id'], 
                        'processing_failed'
                    )
                    continue
                
                # Étape 3: Génération AI des tags
                self.url_manager.update_video_status(
                    video['video_id'], 
                    'generating_tags'
                )
                
                ai_data = self.generate_ai_content(video, title, video_path=processed_path)
                
                # Étape 4: Mise à jour des données
                self.url_manager.update_video_status(
                    video['video_id'],
                    'ready_for_upload',
                    video_path=processed_path,
                    original_title=title,
                    ai_data=ai_data,
                    **tiktok_meta
                )
                
                processed_count += 1
                print(f"✅ Traité: {title}")
                
            except Exception as e:
                logger.error(f"Erreur traitement {video['url']}: {e}")
                self.url_manager.update_video_status(
                    video['video_id'], 
                    'error',
                    error_message=str(e)
                )
        
        print(f"\n🎉 Batch traité: {processed_count}/{len(batch_videos)} vidéos")

    def download_batch(self, batch_id: str) -> List[Dict]:
        """Télécharge uniquement les vidéos d'un batch (pas d'IA, pas de background).

        Les vidéos téléchargées sont marquées 'selected' par défaut (l'UI affiche
        leurs cases cochées d'emblée) — décocher une case dans l'étape suivante la
        repasse à 'rejected'.
        """
        db = self.url_manager.load_database()
        batch_videos = [v for v in db['videos'].values() if v['batch_id'] == batch_id]

        if not batch_videos:
            print("❌ Batch introuvable")
            return []

        downloaded = []
        skipped_duplicates = 0
        for video in batch_videos:
            if video['status'] != 'pending':
                continue

            duplicate = self.url_manager.find_duplicate(
                video['url'], exclude_video_id=video['video_id'], channel=video.get('channel')
            )
            if duplicate:
                self.url_manager.update_video_status(
                    video['video_id'], 'duplicate',
                    duplicate_of=duplicate['video_id'],
                    duplicate_channel=duplicate.get('channel', 'default'),
                    duplicate_status=duplicate['status']
                )
                print(f"⏭️ Déjà traité (chaîne {duplicate.get('channel', 'default')}, statut {duplicate['status']}) — ignoré: {video['url']}")
                skipped_duplicates += 1
                continue

            self.url_manager.update_video_status(video['video_id'], 'downloading')
            video_path, title, tiktok_meta = self.download_tiktok_video(video['url'], video_id=video['video_id'])

            if not video_path:
                self.url_manager.update_video_status(video['video_id'], 'download_failed')
                continue

            self.url_manager.update_video_status(
                video['video_id'], 'selected',
                raw_video_path=video_path, original_title=title,
                **tiktok_meta
            )
            downloaded.append(video)

        print(f"✅ {len(downloaded)}/{len(batch_videos)} vidéos téléchargées"
              f"{f', {skipped_duplicates} doublon(s) ignoré(s)' if skipped_duplicates else ''}")
        return self.list_batch_videos(batch_id, status='selected')

    def list_batch_videos(self, batch_id: str, status: str = None) -> List[Dict]:
        """Liste les vidéos d'un batch, filtrées par statut si fourni (requête
        indexée — ne charge que les lignes concernées)"""
        return self.url_manager.list_videos(status=status, batch_id=batch_id)

    def list_all_videos(self, status: str = None, channel: str = None) -> List[Dict]:
        """Liste toutes les vidéos de la base, tous batches/chaînes confondus
        (requête indexée)"""
        return self.url_manager.list_videos(status=status, channel=channel)

    def set_video_selection(self, video_id: str, selected: bool):
        """Marque une vidéo téléchargée comme sélectionnée (ou rejetée) pour l'étape IA"""
        self.url_manager.update_video_status(video_id, 'selected' if selected else 'rejected')

    def process_selected_videos(self, batch_id: str = None) -> int:
        """Traite (background + IA channel-aware) les vidéos marquées 'selected'.

        Sans batch_id : traite TOUTES les vidéos sélectionnées, toutes chaînes/batches
        confondus (c'est le mode utilisé par l'assistant web, qui travaille sur les 6
        chaînes en une seule fois plutôt que chaîne par chaîne)."""
        selected_videos = (
            self.list_batch_videos(batch_id, status='selected') if batch_id
            else self.list_all_videos(status='selected')
        )
        if not selected_videos:
            print("❌ Aucune vidéo sélectionnée à traiter")
            return 0

        processed_count = 0
        for video in selected_videos:
            channel_name = video.get('channel', 'default')
            print(f"\n🔄 Traitement (chaîne: {channel_name}): {video['url']}")

            try:
                self.url_manager.update_video_status(video['video_id'], 'processing')

                raw_path = video.get('raw_video_path')
                title = video.get('original_title', 'video')
                if not raw_path or not os.path.exists(raw_path):
                    self.url_manager.update_video_status(video['video_id'], 'processing_failed')
                    continue

                bg_mode, specific_bg = self.get_background_for_video(video)
                frame_mode = video.get('frame_mode')
                rounded_corners = video.get('rounded_corners', False)
                processed_path = self.process_tiktok_video(raw_path, title, bg_mode, specific_bg, frame_mode, rounded_corners)

                if not processed_path:
                    self.url_manager.update_video_status(video['video_id'], 'processing_failed')
                    continue

                self.url_manager.update_video_status(video['video_id'], 'generating_tags')
                ai_data = self.generate_ai_content(video, title, video_path=processed_path)

                self.url_manager.update_video_status(
                    video['video_id'], 'ready_for_upload',
                    video_path=processed_path, ai_data=ai_data
                )
                processed_count += 1
                print(f"✅ Traité: {ai_data.get('optimized_title', title)}")

            except Exception as e:
                logger.error(f"Erreur traitement {video['url']}: {e}")
                self.url_manager.update_video_status(video['video_id'], 'error', error_message=str(e))

        print(f"\n🎉 {processed_count}/{len(selected_videos)} vidéos sélectionnées traitées")
        return processed_count

    def regenerate_ai_content(self, video_id: str, instruction: str) -> Optional[Dict]:
        """Régénère les métadonnées IA d'UNE vidéo déjà traitée, en tenant compte
        d'une instruction libre de l'utilisateur (ex: 'rends le titre plus drôle'),
        sans toucher au profil de la chaîne (l'instruction ne vaut que pour cette
        vidéo)."""
        db = self.url_manager.load_database()
        video = db['videos'].get(video_id)
        if not video:
            return None

        channel_name = video.get('channel', 'default')
        channel_profile = {}
        if MULTI_CHANNEL_SUPPORT:
            channel_profile = dict(self.channel_manager.get_channel_profile(channel_name))

        base_style = channel_profile.get('ai_style_prompt', '') or ''
        channel_profile['ai_style_prompt'] = (
            f"{base_style}\n\nAdditional one-off instruction for this specific video: {instruction}"
        ).strip()

        video_path = video.get('video_path') or video.get('raw_video_path', '')
        title = video.get('original_title', 'video')

        video_data = {
            'processed_video_path': video_path, 'title': title,
            'tiktok_description': video.get('tiktok_description', ''),
        }
        ai_data = self.ai_generator.generate_ai_content(video_data, channel_profile)

        self.url_manager.update_video_status(video_id, video['status'], ai_data=ai_data)
        return self.url_manager.load_database()['videos'][video_id]

    def choose_global_background(self) -> str:
        """Permet de choisir un background global"""
        print("\n🎨 Choix du background global:")
        print("1. Random")
        print("2. Blur")
        print("3. Solid color")
        print("4. Gradient")
        print("5. Specific image")
        
        choice = input("Choix (1-5): ").strip()
        mode_map = {
            '1': 'random',
            '2': 'blur', 
            '3': 'solid',
            '4': 'gradient',
            '5': 'specific'
        }
        
        return mode_map.get(choice, 'random')
    
    def get_background_for_video(self, video: Dict) -> tuple:
        """Retourne (bg_mode, specific_bg_path) pour une vidéo, en priorisant
        l'image de fond par défaut de sa chaîne si elle existe.

        Tant qu'une chaîne n'a pas sa propre image, on ne pioche JAMAIS une image
        au hasard dans le pool générique backgrounds/ (comportement non désiré) —
        on retombe sur un fond noir uni, prévisible, en attendant que la chaîne
        ait sa propre image."""
        channel_name = video.get('channel', 'default')
        if MULTI_CHANNEL_SUPPORT:
            bg_path = self.channel_manager.get_background_path(channel_name)
            if bg_path:
                return 'specific', bg_path
        return 'none', None  # unrecognized mode -> test3_script falls back to plain black, no randomness

    def determine_background_mode(self, video: Dict, strategy: str, global_bg: str = None) -> str:
        """Détermine le mode background pour une vidéo"""
        if strategy == "same_for_all":
            return global_bg
        elif strategy == "custom_each":
            # Mode personnalisé défini dans le fichier URL
            return video.get('background_mode', 'random')
        elif strategy == "theme_based":
            # Détecte le thème et choisit le background approprié
            return self.get_theme_background(video)
        else:
            return 'random'
    
    def get_theme_background(self, video: Dict) -> str:
        """Choisit un background basé sur le thème détecté"""
        title = video.get('custom_title', '')
        description = video.get('custom_description', '')
        
        # Détecte le thème
        text = f"{title} {description}".lower()
        
        if any(word in text for word in ['anime', 'manga', 'otaku']):
            return 'specific'  # Background anime
        elif any(word in text for word in ['game', 'gaming', 'gameplay']):
            return 'blur'     # Background blur pour gaming
        elif any(word in text for word in ['funny', 'comedy', 'laugh']):
            return 'gradient' # Background coloré pour comedy
        else:
            return 'random'
    
    def download_tiktok_video(self, url: str, video_id: str = None) -> tuple:
        """Downloads a TikTok, Facebook (reel) or Instagram (post/reel) video —
        yt-dlp handles all three the same way, only the format filter differs
        (TikTok's own height-capped format string 404s on Facebook/Instagram,
        which don't expose a height on their formats the same way).

        Downloads into a per-video subfolder of temp/ (named after video_id when
        provided) so that downloading several videos of the same batch before
        processing them (the new download -> select -> process flow) never lets
        one download overwrite/collide with another still waiting to be processed.

        Also captures the caption/uploader/music info yt-dlp already extracts
        (it was being written to a .info.json on disk and then never read) —
        returned as a 3rd dict, so callers can store it and feed the full,
        untruncated caption to the AI as extra context. `description` is used
        as the real caption on all three platforms: TikTok's `title` is just a
        72-char-truncated copy of it, Facebook's `title` is polluted with
        view/reaction counts, and Instagram's `title` is a generic
        "Video by <user>" placeholder — `description` is the reliable field
        everywhere.
        """
        try:
            import yt_dlp
            import re
            from pathlib import Path
            import uuid

            subfolder = video_id or uuid.uuid4().hex
            temp_path = Path('temp') / subfolder
            temp_path.mkdir(parents=True, exist_ok=True)

            # TikTok's height-capped format works only on TikTok; Facebook/Instagram
            # need the plain "best" — their formats 404 against the height filter.
            video_format = 'best[height<=1920]' if 'tiktok.com' in url else 'best'

            ydl_opts = {
                'outtmpl': f"{temp_path}/%(id)s.%(ext)s",
                'format': video_format,
                'writeinfojson': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                caption = info.get('description') or info.get('title') or 'video'
                # Collapse newlines/tabs/repeated spaces BEFORE stripping symbols — \s in the
                # regex below matches newlines too, so a multi-line caption (common on
                # Instagram/Facebook) would otherwise leave a literal newline inside the
                # title, which becomes part of the output filename and breaks both writing
                # it and (confirmed) serving it back over HTTP (static file serving rejects
                # paths containing control characters).
                caption = re.sub(r'\s+', ' ', caption).strip()
                safe_title = re.sub(r'[^\w\s-]', '', caption)[:30].strip()
                ydl.download([url])

                tiktok_meta = {
                    'tiktok_description': info.get('description') or '',
                    'tiktok_uploader': info.get('uploader') or '',
                    'tiktok_track': info.get('track') or '',
                    'tiktok_artists': info.get('artists') or [],
                }

                temp_files = list(temp_path.glob('*.mp4'))
                if temp_files:
                    return str(temp_files[0]), safe_title, tiktok_meta

        except Exception as e:
            logger.error(f"Erreur téléchargement: {e}")

        return None, None, {}

    def process_tiktok_video(self, video_path: str, title: str, bg_mode: str, specific_bg: str = None, frame_mode: str = None, rounded_corners: bool = False) -> str:
        """Interface avec le traitement vidéo existant"""
        # Réutilise la fonction de test3_script.py
        try:
            from test3_script import process_video_with_background_options

            return process_video_with_background_options(
                video_path, title, bg_mode, specific_bg, frame_mode, rounded_corners
            )

        except Exception as e:
            logger.error(f"Erreur traitement vidéo: {e}")
            return None

    def get_frame_suggestion(self, video_id: str) -> Optional[Dict]:
        """Cadrage suggéré pour une vidéo 'selected' (avant traitement), basé
        sur son ratio natif — voir test3_script.suggest_frame_mode."""
        db = self.url_manager.load_database()
        video = db['videos'].get(video_id)
        if not video:
            return None

        raw_path = video.get('raw_video_path')
        if not raw_path or not os.path.exists(raw_path):
            return None

        from test3_script import get_video_dimensions, suggest_frame_mode
        width, height = get_video_dimensions(raw_path)
        return {
            'video_id': video_id,
            'width': width,
            'height': height,
            'video_ratio': (width / height) if width and height else None,
            'suggested_frame_mode': suggest_frame_mode(raw_path),
            'current_frame_mode': video.get('frame_mode'),
        }

    def set_video_frame_mode(self, video_id: str, frame_mode: str, rounded_corners: bool = None):
        """Enregistre le mode de cadrage (et, indépendamment, les coins
        arrondis) choisi/confirmé pour une vidéo, sans toucher à son statut."""
        db = self.url_manager.load_database()
        video = db['videos'].get(video_id)
        if not video:
            return None
        updates = {'frame_mode': frame_mode}
        if rounded_corners is not None:
            updates['rounded_corners'] = rounded_corners
        self.url_manager.update_video_status(video_id, video['status'], **updates)
        return self.url_manager.load_database()['videos'][video_id]
    
    def generate_ai_content(self, video: Dict, title: str, video_path: str = None) -> Dict:
        """Génère le contenu AI pour une vidéo (analyse vision/audio selon le profil de
        la chaîne), avec repli sur la génération locale en cas d'erreur."""
        try:
            channel_name = video.get('channel', 'default')
            channel_profile = None
            if MULTI_CHANNEL_SUPPORT:
                channel_profile = self.channel_manager.get_channel_profile(channel_name)

            video_data = {
                'processed_video_path': video_path or video.get('video_path', ''),
                'title': title,
                'tiktok_description': video.get('tiktok_description', ''),
            }

            return self.ai_generator.generate_ai_content(video_data, channel_profile)

        except Exception as e:
            logger.error(f"Erreur génération AI: {e}")
            # Return default AI data structure
            return {
                "tags": [
                    "TikTok", "Shorts", "Viral", "Trending", "Entertainment"
                ],
                "hashtags": [
                    "#Shorts", "#Viral", "#TikTok"
                ],
                "optimized_title": title,
                "content_type": "general",
                "description_suggestions": [
                    "Contenu viral du jour ! 🔥",
                    "Tu as vu ça ? Partage en commentaire ! 💬",
                    "Tendance TikTok à ne pas manquer ! #viral"
                ]
            }

    def create_upload_schedule(self, max_videos: int = None, use_analytics: bool = None,
                                target_channel: str = None, schedule_method: str = None) -> List[Dict]:
        """Crée un planning d'upload pour les vidéos prêtes.

        schedule_method: "static", "analytics", or "ai" (per-video, content/channel-aware
        via AIScheduler). Takes precedence over the legacy use_analytics bool if given.
        """

        # Récupère les vidéos prêtes
        ready_videos = []
        db = self.url_manager.load_database()

        for video in db['videos'].values():
            if video['status'] == 'ready_for_upload':
                # Add target channel to video data
                if target_channel:
                    video['target_channel'] = target_channel
                ready_videos.append(video)

        if not ready_videos:
            print("❌ Aucune vidéo prête pour l'upload")
            return []

        # Limite le nombre si spécifié
        if max_videos:
            ready_videos = ready_videos[:max_videos]

        # Determine scheduling method
        if schedule_method is None:
            if use_analytics is None:
                use_analytics = ANALYTICS_SUPPORT and self.ask_user_analytics_preference()
            schedule_method = "analytics" if use_analytics else "static"

        if schedule_method == "ai" and AI_SCHEDULING_SUPPORT:
            print(f"🤖 Création du planning IA (par vidéo) pour {len(ready_videos)} vidéos")
            channel_manager = self.channel_manager if MULTI_CHANNEL_SUPPORT else None
            result = self.ai_scheduler.create_ai_suggested_schedule(ready_videos, self.config, channel_manager)
            schedule = result['schedule']
        elif schedule_method == "analytics" and ANALYTICS_SUPPORT:
            print(f"🧠 Création du planning ANALYTICS pour {len(ready_videos)} vidéos")
            if target_channel:
                print(f"📺 Channel de destination: {target_channel}")
            schedule = self.smart_scheduler.create_analytics_based_schedule(ready_videos)['schedule']
        else:
            print(f"📅 Création du planning STANDARD pour {len(ready_videos)} vidéos")
            if target_channel:
                print(f"📺 Channel de destination: {target_channel}")
            channel_manager = self.channel_manager if MULTI_CHANNEL_SUPPORT else None
            schedule = self.scheduler.create_upload_schedule(ready_videos, channel_manager=channel_manager)

        # Sauvegarde (save_schedule attend une liste de dicts, pas le wrapper avec métadonnées)
        self.scheduler.save_schedule(schedule)
        self._record_schedule_decisions(schedule, schedule_method)

        return schedule

    def _record_schedule_decisions(self, schedule: List[Dict], method: str):
        """Persists WHY each video's date was picked directly on the video row
        (url_manager.record_publish_decision) — not just in the ephemeral
        upload_schedule.json — so it's still there after publish, to later
        check whether analytics/AI scheduling actually performs better than
        static. analytics_peak_hours is attached regardless of the method
        used, as context (what analytics WOULD have suggested), whenever
        analytics support is available."""
        for entry in schedule:
            context = {}
            if ANALYTICS_SUPPORT and hasattr(self, 'smart_scheduler'):
                try:
                    context['analytics_peak_hours'] = self.smart_scheduler.get_channel_peak_times(entry['channel'])
                except Exception as e:
                    print(f"⚠️ Could not record analytics context for {entry.get('video_id')}: {e}")
            self.url_manager.record_publish_decision(entry['video_id'], method, entry['scheduled_time'], context)

    def ensure_schedule_includes_all_ready(self, schedule_method: str = 'static') -> List[Dict]:
        """Filet de sécurité appelé juste avant une publication : 'Publier tout' ne
        publie que ce qui est dans upload_schedule.json, donc une vidéo passée à
        'ready_for_upload' APRÈS la dernière génération du planning serait sinon
        ignorée en silence (200 OK, mais rien publié pour elle). Ajoute au planning
        existant toute vidéo prête qui n'y figure pas encore, sans toucher aux
        entrées déjà présentes (y compris une date modifiée à la main)."""
        existing = self.scheduler.load_schedule() or {}
        existing_schedule = existing.get('schedule', [])
        existing_ids = {e.get('video_id') for e in existing_schedule}

        db = self.url_manager.load_database()
        missing = [
            v for v in db['videos'].values()
            if v.get('status') == 'ready_for_upload' and v.get('video_id') not in existing_ids
        ]
        if not missing:
            return existing_schedule

        print(f"⚠️ {len(missing)} vidéo(s) prête(s) manquaient du planning — ajout automatique avant publication")
        channel_manager = self.channel_manager if MULTI_CHANNEL_SUPPORT else None

        if schedule_method == 'ai' and AI_SCHEDULING_SUPPORT:
            new_entries = self.ai_scheduler.create_ai_suggested_schedule(missing, self.config, channel_manager)['schedule']
        elif schedule_method == 'analytics' and ANALYTICS_SUPPORT:
            new_entries = self.smart_scheduler.create_analytics_based_schedule(missing)['schedule']
        else:
            new_entries = self.scheduler.create_upload_schedule(missing, channel_manager=channel_manager)

        combined = existing_schedule + new_entries
        self.scheduler.save_schedule(combined)
        self._record_schedule_decisions(new_entries, schedule_method)
        return combined

    def ask_user_analytics_preference(self) -> bool:
        """Ask user if they want to use analytics-based scheduling"""
        if not ANALYTICS_SUPPORT:
            return False
        
        print("\n📊 SCHEDULING OPTIONS:")
        print("1. 🧠 Analytics-Based (Uses your channel's peak engagement times)")
        print("2. 📅 Static Times (Uses predefined optimal times)")
        
        while True:
            choice = input("Choose scheduling method (1/2): ").strip()
            if choice == '1':
                return True
            elif choice == '2':
                return False
            else:
                print("❌ Please choose 1 or 2")
    
    def interactive_menu(self):
        """Menu interactif principal"""
        print("🚀 BATCH PROCESSOR - TikTok to YouTube Automation")
        print("=" * 55)
        
        while True:
            print("\n📋 MENU PRINCIPAL:")
            print("1. 📁 Traiter un fichier d'URLs")
            print("2. 🔄 Télécharger et traiter un batch")
            print("3. 📅 Créer planning d'upload")
            print("4. 📊 Voir statut des vidéos")
            print("5. 🎬 Upload vers YouTube")
            print("6. ⚙️ Configuration")
            if ANALYTICS_SUPPORT:
                print("8. 📈 Comparer Analytics vs Statique")
            print("9. 📋 Gérer planning d'upload")
            print("10. 🔄 Gérer statut des vidéos")
            print("7. ❌ Quitter")
            
            choice = input("\nChoix (1-10): ").strip()
            
            if choice == '1':
                self.menu_process_urls()
            elif choice == '2':
                self.menu_download_batch()
            elif choice == '3':
                self.menu_create_schedule()
            elif choice == '4':
                self.menu_show_status()
            elif choice == '5':
                self.menu_upload_youtube()
            elif choice == '6':
                self.menu_configuration()
            elif choice == '7':
                print("👋 Au revoir!")
                break
            elif choice == '8' and ANALYTICS_SUPPORT:
                self.menu_compare_scheduling()
            elif choice == '9':
                self.menu_manage_schedule()
            elif choice == '10':
                self.menu_manage_video_status()
            else:
                print("❌ Choix invalide")
    
    def menu_process_urls(self):
        """Menu traitement fichier URLs"""
        print("\n📁 TRAITEMENT FICHIER URLs")
        
        # Liste les fichiers disponibles
        urls_folder = Path('urls_input/')
        if urls_folder.exists():
            url_files = list(urls_folder.glob('*.txt'))
            if url_files:
                print("Fichiers disponibles:")
                for i, file in enumerate(url_files, 1):
                    print(f"{i}. {file.name}")
                
                try:
                    choice = int(input(f"Choisir (1-{len(url_files)}) ou 0 pour chemin custom: "))
                    if choice == 0:
                        file_path = input("Chemin du fichier: ").strip()
                    else:
                        file_path = str(url_files[choice - 1])
                except (ValueError, IndexError):
                    print("❌ Choix invalide")
                    return
            else:
                file_path = input("Chemin du fichier URLs: ").strip()
        else:
            file_path = input("Chemin du fichier URLs: ").strip()
        
        if not os.path.exists(file_path):
            print("❌ Fichier introuvable")
            return
        
        batch_name = input("Nom du batch (ou Enter pour auto): ").strip()
        
        batch_id = self.process_url_file(file_path, batch_name)
        if batch_id:
            print(f"✅ Batch créé: {batch_id}")
    
    def menu_download_batch(self):
        """Menu téléchargement batch"""
        print("\n🔄 TÉLÉCHARGEMENT ET TRAITEMENT BATCH")
        
        # Liste les batches disponibles
        db = self.url_manager.load_database()
        batches = db.get('batches', {})
        
        if not batches:
            print("❌ Aucun batch disponible")
            return
        
        print("Batches disponibles:")
        batch_list = list(batches.items())
        for i, (batch_id, batch_info) in enumerate(batch_list, 1):
            print(f"{i}. {batch_info['name']} ({batch_info['total_videos']} vidéos) - {batch_info['status']}")
        
        try:
            choice = int(input(f"Choisir (1-{len(batch_list)}): ")) - 1
            selected_batch = batch_list[choice][0]
        except (ValueError, IndexError):
            print("❌ Choix invalide")
            return
        
        # Choix stratégie background
        print("\n🎨 Stratégie de background:")
        print("1. Même fond pour toutes les vidéos")
        print("2. Fond basé sur le thème")
        print("3. Fond aléatoire pour chaque vidéo")
        print("4. Fond personnalisé (défini dans le fichier)")
        
        bg_choice = input("Choix (1-4): ").strip()
        bg_strategies = {
            '1': 'same_for_all',
            '2': 'theme_based',
            '3': 'random_each',
            '4': 'custom_each'
        }
        
        strategy = bg_strategies.get(bg_choice, 'random_each')
        
        self.download_and_process_batch(selected_batch, strategy)
    
    def menu_create_schedule(self):
        """Menu création planning"""
        print("\n📅 CRÉATION PLANNING D'UPLOAD")
        
        # Check if we have videos ready
        db = self.url_manager.load_database()
        ready_videos = [v for v in db['videos'].values() if v['status'] == 'ready_for_upload']
        
        if not ready_videos:
            print("❌ Aucune vidéo prête pour l'upload")
            print("💡 Utilisez l'option 2 pour traiter des vidéos d'abord")
            return
        
        print(f"📦 {len(ready_videos)} vidéo(s) prête(s) pour le planning")
        
        # Select target channel for scheduling
        target_channel = None
        if MULTI_CHANNEL_SUPPORT:
            try:
                from channel_manager import ChannelManager
                manager = ChannelManager()
                channels = manager.list_channels()
                
                if channels:
                    print("\n📺 Sélectionnez le channel de destination:")
                    for i, channel in enumerate(channels, 1):
                        print(f"{i}. {channel.get('display_name', channel.get('name', 'Unknown'))}")
                    
                    choice = int(input(f"Choix (1-{len(channels)}): "))
                    selected_channel = channels[choice - 1]
                    target_channel = selected_channel.get('name')
                    print(f"✅ Channel sélectionné: {selected_channel.get('display_name', target_channel)}")
            except (ValueError, IndexError):
                print("❌ Choix invalide, utilisation du channel par défaut")
            except Exception as e:
                print(f"⚠️  Erreur sélection channel: {e}")
        
        max_videos = input("\nNombre max de vidéos (ou Enter pour toutes): ").strip()
        max_videos = int(max_videos) if max_videos.isdigit() else None
        
        # Ask about analytics if available
        use_analytics = None
        if ANALYTICS_SUPPORT:
            print("\n🧠 Analytics-based scheduling available!")
            use_analytics = self.ask_user_analytics_preference()
        
        schedule = self.create_upload_schedule(max_videos, use_analytics, target_channel)
        
        if schedule:
            self.scheduler.print_schedule_summary(schedule)
    
    def menu_show_status(self):
        """Menu affichage statut avec détails des channels"""
        print("\n📊 STATUT DES VIDÉOS")
        
        summary = self.url_manager.get_status_summary()
        
        print("Résumé des statuts:")
        for status, count in summary.items():
            print(f"  {status}: {count} vidéos")
        
        # Afficher les détails par statut avec les channels
        self.show_detailed_status_with_channels()
        
        # Détails des vidéos en erreur
        if 'error' in summary:
            print("\n❌ Vidéos en erreur:")
            db = self.url_manager.load_database()
            for video in db['videos'].values():
                if video['status'] == 'error':
                    print(f"  - {video['url']}: {video.get('error_message', 'Erreur inconnue')}")
    
    def show_detailed_status_with_channels(self):
        """Affiche le statut détaillé avec les channels pour chaque vidéo"""
        db = self.url_manager.load_database()
        
        # Group videos by status
        status_groups = {}
        for video in db['videos'].values():
            status = video['status']
            if status not in status_groups:
                status_groups[status] = []
            status_groups[status].append(video)
        
        # Show details for important statuses
        important_statuses = {
            'scheduled_on_youtube': '📅 SCHEDULED ON YOUTUBE',
            'uploaded': '✅ UPLOADED', 
            'ready_for_upload': '📦 READY FOR UPLOAD',
            'error': '❌ ERROR'
        }
        
        for status, title in important_statuses.items():
            if status in status_groups and status_groups[status]:
                print(f"\n{title} ({len(status_groups[status])} vidéos):")
                print("-" * 50)
                
                for video in status_groups[status]:
                    # Get video title (truncated)
                    title = video.get('original_title', 'Unknown')[:40]
                    if len(video.get('original_title', '')) > 40:
                        title += "..."
                    
                    # Get channel info
                    channel_info = self.get_video_channel_info(video)
                    
                    # Format display
                    print(f"📺 {title}")
                    print(f"   📺 Channel: {channel_info}")
                    
                    if video.get('youtube_url'):
                        print(f"   ▶️  YouTube: {video['youtube_url']}")
                    
                    if video.get('scheduled_publish_time'):
                        print(f"   ⏰ Scheduled: {video['scheduled_publish_time']}")
                    
                    if status == 'error' and video.get('error_message'):
                        print(f"   ❌ Error: {video['error_message']}")
                    
                    print()
    
    def get_video_channel_info(self, video):
        """Get channel information for a video"""
        # Check if video has target_channel specified
        if video.get('target_channel'):
            return f"🎯 {video['target_channel']}"
        
        # Check upload schedule for channel info
        try:
            if os.path.exists('database/upload_schedule.json'):
                with open('database/upload_schedule.json', 'r') as f:
                    schedule_data = json.load(f)
                    
                for entry in schedule_data.get('schedule', []):
                    if entry.get('video_id') == video.get('video_id'):
                        if entry.get('channel'):
                            return f"📅 {entry['channel']}"
        except:
            pass
        
        # Check if multi-channel upload
        if video.get('multi_channel_upload'):
            return "📺 Multi-channel"
        
        # Get actual channel name instead of "Default"
        if MULTI_CHANNEL_SUPPORT:
            try:
                from channel_manager import ChannelManager
                manager = ChannelManager()
                channels = manager.list_channels()
                if channels:
                    # Get the first active channel name
                    channel_name = channels[0].get('name', 'Unknown')
                    display_name = channels[0].get('display_name', channel_name)
                    return f"📺 {display_name}"
            except:
                pass
        
        return "📺 Unknown channel"
    
    def menu_upload_youtube(self):
        """Menu upload YouTube - Instructions pour utiliser youtube_uploader.py"""
        print("\n🎬 UPLOAD VERS YOUTUBE")
        print("=" * 50)
        
        # Check for ready videos
        db = self.url_manager.load_database()
        ready_videos = [v for v in db['videos'].values() if v['status'] == 'ready_for_upload']
        failed_videos = [v for v in db['videos'].values() if v['status'] == 'upload_failed']
        
        total_videos = len(ready_videos) + len(failed_videos)
        
        if total_videos == 0:
            print("❌ Aucune vidéo prête pour l'upload")
            print("💡 Utilisez l'option 2 pour traiter des vidéos d'abord")
            return
        
        # Show video summary
        print(f"📹 Vidéos disponibles pour upload:")
        print(f"   📦 Prêtes: {len(ready_videos)} vidéos")
        if failed_videos:
            print(f"   🔄 Échouées (retry): {len(failed_videos)} vidéos")
        print()
        
        # Show scheduled videos by channel if schedule exists
        if os.path.exists('upload_schedule.json'):
            try:
                with open('upload_schedule.json', 'r', encoding='utf-8') as f:
                    schedule_data = json.load(f)
                
                scheduled_videos = schedule_data.get('schedule', [])
                if scheduled_videos:
                    print("📅 VIDÉOS PROGRAMMÉES PAR CHANNEL:")
                    print("-" * 40)
                    
                    # Group by channel
                    channel_schedules = {}
                    for video in scheduled_videos:
                        # Get channel from video data or default
                        channel = video.get('channel', 'default')
                        if hasattr(video, 'get') and video.get('video_data', {}).get('target_channel'):
                            channel = video['video_data']['target_channel']
                        
                        if channel not in channel_schedules:
                            channel_schedules[channel] = []
                        channel_schedules[channel].append(video)
                    
                    # Show channels with and without scheduled videos
                    if MULTI_CHANNEL_SUPPORT:
                        try:
                            from channel_manager import ChannelManager
                            manager = ChannelManager()
                            all_channels = manager.list_channels()
                            
                            for channel_info in all_channels:
                                channel_name = channel_info.get('name')
                                display_name = channel_info.get('display_name', channel_name)
                                
                                if channel_name in channel_schedules:
                                    count = len(channel_schedules[channel_name])
                                    print(f"   ✅ {display_name}: {count} vidéo(s) programmée(s)")
                                else:
                                    print(f"   ❌ {display_name}: Aucune vidéo programmée")
                        except:
                            # Fallback to showing what we have in schedule
                            for channel, videos in channel_schedules.items():
                                print(f"   ✅ {channel}: {len(videos)} vidéo(s) programmée(s)")
                    else:
                        for channel, videos in channel_schedules.items():
                            print(f"   ✅ {channel}: {len(videos)} vidéo(s) programmée(s)")
                    
                    print()
            except Exception as e:
                print(f"⚠️  Erreur lecture planning: {e}")
        else:
            print("📅 Aucun planning trouvé")
            print("💡 Créez un planning avec l'option 3")
            print()
        
        # Multi-channel info
        if MULTI_CHANNEL_SUPPORT:
            print("📺 Multi-Channel Support: ✅ Enabled")
            try:
                from channel_manager import ChannelManager
                manager = ChannelManager()
                channels = manager.list_channels()
                print(f"📺 Channels configurés: {len(channels)}")
                for channel in channels:
                    print(f"   • {channel.get('display_name', channel.get('name', 'Unknown'))}")
            except:
                print("⚠️  Erreur lecture channels")
        
        print("\n" + "=" * 50)
        print("📋 INSTRUCTIONS POUR L'UPLOAD:")
        print("=" * 50)
        print()
        print("🚀 Pour uploader vos vidéos, utilisez le script dédié:")
        print()
        print("   python3 youtube_uploader.py")
        print()
        print("📋 Options disponibles dans youtube_uploader.py:")
        print("   1. 📤 Upload vidéo individuelle")
        print("   2. 📅 Upload TOUTES les vidéos programmées") 
        print("   3. 🔄 Re-upload video to different channel")
        if MULTI_CHANNEL_SUPPORT:
            print("   4. ⚙️  Manage channels")
        print()
        print("✨ Avantages du script youtube_uploader.py:")
        print("   • 🤖 Interface dédiée avec AI tags")
        print("   • 📺 Sélection interactive des channels")
        print("   • 📅 Support upload programmé")
        print("   • � Retry des uploads échoués")
        print("   • 🛡️  Mode manuel ou automatique")
        print()
        print("💡 Ce système garde les fonctionnalités séparées et plus maintenables!")
        
        input("\nAppuyez sur Entrée pour continuer...")
    
    def menu_compare_scheduling(self):
        """Menu comparaison Analytics vs Static scheduling"""
        if not ANALYTICS_SUPPORT:
            print("❌ Analytics support not available")
            return
        
        print("\n📈 COMPARAISON ANALYTICS vs STATIQUE")
        print("=" * 45)
        
        # Get available channels
        if MULTI_CHANNEL_SUPPORT:
            try:
                manager = ChannelManager()
                channels = manager.list_channels()
                
                if not channels:
                    print("❌ Aucun channel configuré")
                    return
                
                print("Channels disponibles:")
                for i, channel in enumerate(channels, 1):
                    print(f"{i}. {channel}")
                
                choice = int(input(f"Choisir channel (1-{len(channels)}): "))
                selected_channel_info = channels[choice - 1]
                # Extract channel name from the dictionary
                selected_channel = selected_channel_info['name'] if isinstance(selected_channel_info, dict) else selected_channel_info
                
            except (ValueError, IndexError):
                print("❌ Choix invalide")
                return
        else:
            selected_channel = input("Nom du channel: ").strip()
        
        # Compare scheduling methods
        self.smart_scheduler.compare_static_vs_analytics(selected_channel)
        
        print("Cette fonctionnalité utilise ton script youtube_uploader.py existant")
        
        # Charge le planning existant ou en crée un nouveau
        if os.path.exists('upload_schedule.json'):
            use_existing = input("Utiliser le planning existant? (y/n): ").lower() == 'y'
            if use_existing:
                schedule_data = self.scheduler.load_schedule()
                print(f"📅 Planning chargé: {len(schedule_data['schedule'])} vidéos")
                if selected_channel:
                    print(f"📺 Upload vers: {selected_channel}")
                # Ici tu peux implémenter l'upload automatique
                print("💡 Lance youtube_uploader.py pour uploader manuellement")
            else:
                self.menu_create_schedule()
        else:
            print("Aucun planning trouvé, création...")
            self.menu_create_schedule()
    
    def menu_configuration(self):
        """Menu configuration"""
        print("\n⚙️ CONFIGURATION")
        print("Fichier de config: config.yaml")
        print("Édite ce fichier pour modifier les paramètres")
        
        # Affiche la config actuelle
        print("\nConfiguration actuelle:")
        print(f"- Max uploads/jour: {self.config['general']['max_daily_uploads']}")
        print(f"- Max uploads/semaine: {self.config['general']['max_weekly_uploads']}")
        print(f"- Espacement: {self.config['scheduling']['spacing_hours']}h")
    
    def menu_manage_schedule(self):
        """Menu gestion du planning d'upload"""
        print("\n📋 GESTION DU PLANNING D'UPLOAD")
        print("=" * 50)
        
        # Check if schedule exists
        if not os.path.exists('upload_schedule.json'):
            print("❌ Aucun planning trouvé")
            print("💡 Créez d'abord un planning avec l'option 3")
            return
        
        # Load schedule
        try:
            with open('upload_schedule.json', 'r', encoding='utf-8') as f:
                schedule_data = json.load(f)
        except Exception as e:
            print(f"❌ Erreur lecture planning: {e}")
            return
        
        scheduled_videos = schedule_data.get('schedule', [])
        
        if not scheduled_videos:
            print("❌ Planning vide")
            return
        
        print(f"📅 Planning actuel: {len(scheduled_videos)} vidéo(s)")
        print()
        
        # Show current schedule with upload status
        db = self.url_manager.load_database()
        for i, video in enumerate(scheduled_videos, 1):
            video_id = video['video_id']
            video_data = db.get('videos', {}).get(video_id, {})
            status = video_data.get('status', 'unknown')
            
            status_icons = {
                'uploaded': '✅',
                'scheduled_on_youtube': '📅', 
                'ready_for_upload': '📦',
                'upload_failed': '❌'
            }
            
            icon = status_icons.get(status, '❓')
            print(f"{i}. {icon} {video['title'][:50]}...")
            print(f"   📅 {video['scheduled_time_readable']}")
            print(f"   📊 Status: {status}")
            
            if status in ['uploaded', 'scheduled_on_youtube'] and video_data.get('youtube_url'):
                print(f"   🔗 {video_data['youtube_url']}")
            
            print()
        
        print("\n📋 ACTIONS:")
        print("1. 🗑️  Supprimer le planning complet")
        print("2. ❌ Supprimer des vidéos spécifiques")
        print("3. ➕ Ajouter des vidéos au planning")
        print("4. 📊 Afficher statistiques détaillées")
        print("5. 🔙 Retour au menu principal")
        
        choice = input("\nChoix (1-5): ").strip()
        
        if choice == '1':
            self.delete_entire_schedule()
        elif choice == '2':
            self.remove_videos_from_schedule(scheduled_videos)
        elif choice == '3':
            self.add_videos_to_schedule()
        elif choice == '4':
            self.show_schedule_statistics(scheduled_videos, db)
        elif choice == '5':
            return
        else:
            print("❌ Choix invalide")
    
    def delete_entire_schedule(self):
        """Supprime complètement le planning"""
        print("\n🗑️  SUPPRIMER LE PLANNING COMPLET")
        print("⚠️  Cette action supprimera tout le planning d'upload!")
        
        confirm = input("Êtes-vous sûr? Tapez 'SUPPRIMER' pour confirmer: ").strip()
        
        if confirm == 'SUPPRIMER':
            try:
                os.remove('upload_schedule.json')
                print("✅ Planning supprimé avec succès!")
            except Exception as e:
                print(f"❌ Erreur suppression: {e}")
        else:
            print("❌ Suppression annulée")
    
    def remove_videos_from_schedule(self, scheduled_videos):
        """Supprime des vidéos spécifiques du planning"""
        print("\n❌ SUPPRIMER DES VIDÉOS DU PLANNING")
        
        print("Entrez les numéros des vidéos à supprimer (ex: 1,3,5):")
        selection = input("Numéros: ").strip()
        
        try:
            indices_to_remove = [int(x.strip())-1 for x in selection.split(',')]
            
            # Validate indices
            valid_indices = [i for i in indices_to_remove if 0 <= i < len(scheduled_videos)]
            
            if not valid_indices:
                print("❌ Aucun numéro valide")
                return
            
            # Show videos to be removed
            print(f"\n📋 Vidéos à supprimer ({len(valid_indices)}):")
            for i in valid_indices:
                print(f"- {scheduled_videos[i]['title']}")
            
            confirm = input(f"\nSupprimer ces {len(valid_indices)} vidéo(s)? (y/n): ").lower()
            
            if confirm == 'y':
                # Remove videos (reverse order to maintain indices)
                for i in sorted(valid_indices, reverse=True):
                    del scheduled_videos[i]
                
                # Save updated schedule
                schedule_data = {
                    'created_at': datetime.now().isoformat(),
                    'total_videos': len(scheduled_videos),
                    'schedule': scheduled_videos
                }
                
                with open('upload_schedule.json', 'w', encoding='utf-8') as f:
                    json.dump(schedule_data, f, indent=2, ensure_ascii=False)
                
                print(f"✅ {len(valid_indices)} vidéo(s) supprimée(s) du planning!")
            else:
                print("❌ Suppression annulée")
                
        except ValueError:
            print("❌ Format invalide. Utilisez des nombres séparés par des virgules")
        except Exception as e:
            print(f"❌ Erreur: {e}")
    
    def add_videos_to_schedule(self):
        """Ajoute des vidéos au planning existant"""
        print("\n➕ AJOUTER DES VIDÉOS AU PLANNING")
        
        # Get videos ready for upload that are not in schedule
        db = self.url_manager.load_database()
        ready_videos = []
        
        # Load current schedule to avoid duplicates
        try:
            with open('upload_schedule.json', 'r', encoding='utf-8') as f:
                schedule_data = json.load(f)
            scheduled_ids = {v['video_id'] for v in schedule_data.get('schedule', [])}
        except:
            scheduled_ids = set()
        
        for video_id, video_data in db.get('videos', {}).items():
            if (video_data.get('status') == 'ready_for_upload' and 
                video_id not in scheduled_ids):
                ready_videos.append((video_id, video_data))
        
        if not ready_videos:
            print("❌ Aucune nouvelle vidéo prête pour le planning")
            print("💡 Traitez d'abord des vidéos avec l'option 2")
            return
        
        print(f"📦 {len(ready_videos)} vidéo(s) disponible(s):")
        for i, (video_id, video_data) in enumerate(ready_videos, 1):
            title = video_data.get('ai_data', {}).get('optimized_title') or video_data.get('original_title', 'Unknown')
            print(f"{i}. {title[:50]}...")
        
        selection = input(f"\nSélectionner vidéos à ajouter (1-{len(ready_videos)}, ex: 1,2,3): ").strip()
        
        try:
            indices = [int(x.strip())-1 for x in selection.split(',')]
            selected_videos = [ready_videos[i] for i in indices if 0 <= i < len(ready_videos)]
            
            if not selected_videos:
                print("❌ Aucune vidéo sélectionnée")
                return
            
            # Create schedule entries for selected videos
            use_analytics = ANALYTICS_SUPPORT and self.ask_user_analytics_preference()
            
            if use_analytics:
                new_schedule = self.smart_scheduler.create_analytics_based_schedule(
                    [{'video_id': vid, **vdata} for vid, vdata in selected_videos]
                )
            else:
                new_schedule = self.scheduler.create_upload_schedule(
                    [{'video_id': vid, **vdata} for vid, vdata in selected_videos]
                )
            
            # Add to existing schedule
            schedule_data['schedule'].extend(new_schedule)
            schedule_data['total_videos'] = len(schedule_data['schedule'])
            schedule_data['updated_at'] = datetime.now().isoformat()
            
            with open('upload_schedule.json', 'w', encoding='utf-8') as f:
                json.dump(schedule_data, f, indent=2, ensure_ascii=False)
            
            print(f"✅ {len(selected_videos)} vidéo(s) ajoutée(s) au planning!")
            
        except ValueError:
            print("❌ Format invalide")
        except Exception as e:
            print(f"❌ Erreur: {e}")
    
    def show_schedule_statistics(self, scheduled_videos, db):
        """Affiche les statistiques détaillées du planning"""
        print("\n📊 STATISTIQUES DU PLANNING")
        print("=" * 50)
        
        # Count by status
        status_counts = {}
        channel_counts = {}
        
        for video in scheduled_videos:
            video_id = video['video_id']
            video_data = db.get('videos', {}).get(video_id, {})
            status = video_data.get('status', 'unknown')
            
            status_counts[status] = status_counts.get(status, 0) + 1
            
            # Count by channel (if uploaded)
            if status in ['uploaded', 'scheduled_on_youtube']:
                channel = video_data.get('uploaded_channel', 'Unknown')
                channel_counts[channel] = channel_counts.get(channel, 0) + 1
        
        print("📊 Par statut:")
        for status, count in status_counts.items():
            icon = {'uploaded': '✅', 'scheduled_on_youtube': '📅', 'ready_for_upload': '📦'}.get(status, '❓')
            print(f"   {icon} {status}: {count} vidéos")
        
        if channel_counts:
            print("\n📺 Par channel (uploadées):")
            for channel, count in channel_counts.items():
                print(f"   📺 {channel}: {count} vidéos")
        
        # Time statistics
        upload_times = []
        for video in scheduled_videos:
            if video.get('scheduled_time'):
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(video['scheduled_time'].replace('Z', '+00:00'))
                    upload_times.append(dt)
                except:
                    pass
        
        if upload_times:
            upload_times.sort()
            print(f"\n📅 Période d'upload:")
            print(f"   🗓️  Du: {upload_times[0].strftime('%d/%m/%Y %H:%M')}")
            print(f"   🗓️  Au: {upload_times[-1].strftime('%d/%m/%Y %H:%M')}")
        
        print(f"\n📈 Total: {len(scheduled_videos)} vidéos dans le planning")
    
    def menu_manage_video_status(self):
        """Menu gestion du statut des vidéos"""
        print("\n🔄 GESTION DU STATUT DES VIDÉOS")
        print("=" * 50)
        print("💡 Permet de réutiliser des vidéos pour d'autres channels")
        
        db = self.url_manager.load_database()
        videos = db.get('videos', {})
        
        if not videos:
            print("❌ Aucune vidéo trouvée")
            return
        
        # Filter videos that can be re-used (uploaded, scheduled, or failed)
        reusable_videos = {}
        for video_id, video_data in videos.items():
            status = video_data.get('status')
            if status in ['uploaded', 'scheduled_on_youtube', 'upload_failed', 'ready_for_upload']:
                reusable_videos[video_id] = video_data
        
        if not reusable_videos:
            print("❌ Aucune vidéo réutilisable trouvée")
            return
        
        print(f"📦 {len(reusable_videos)} vidéo(s) disponible(s) pour modification:")
        print()
        
        # Group by status for better display
        status_groups = {}
        for video_id, video_data in reusable_videos.items():
            status = video_data.get('status')
            if status not in status_groups:
                status_groups[status] = []
            status_groups[status].append((video_id, video_data))
        
        # Display videos by status
        all_videos = []
        counter = 1
        
        status_display = {
            'uploaded': '✅ UPLOADÉES',
            'scheduled_on_youtube': '📅 PROGRAMMÉES', 
            'ready_for_upload': '📦 PRÊTES',
            'upload_failed': '❌ ÉCHOUÉES'
        }
        
        for status, display_name in status_display.items():
            if status in status_groups:
                print(f"\n{display_name} ({len(status_groups[status])} vidéos):")
                print("-" * 40)
                
                for video_id, video_data in status_groups[status]:
                    title = video_data.get('original_title', 'Unknown')[:50]
                    if len(video_data.get('original_title', '')) > 50:
                        title += "..."
                    
                    # Show channel info
                    channel_info = self.get_video_channel_info(video_data)
                    
                    print(f"{counter}. 📺 {title}")
                    print(f"   📺 {channel_info}")
                    
                    if video_data.get('youtube_url'):
                        print(f"   🔗 {video_data['youtube_url']}")
                    
                    all_videos.append((video_id, video_data))
                    counter += 1
                    print()
        
        if not all_videos:
            return
        
        print("\n🔄 ACTIONS DISPONIBLES:")
        print("1. 🔄 Remettre vidéo(s) en 'ready_for_upload' (pour re-scheduling)")
        print("2. 📺 Changer le channel de destination")
        print("3. 🗑️  Supprimer l'historique d'upload (reset complet)")
        print("4. 🔙 Retour au menu principal")
        
        action = input("\nChoix (1-4): ").strip()
        
        if action == '1':
            self.reset_video_status_for_rescheduling(all_videos)
        elif action == '2':
            self.change_video_target_channel(all_videos)
        elif action == '3':
            self.reset_video_upload_history(all_videos)
        elif action == '4':
            return
        else:
            print("❌ Choix invalide")
    
    def reset_video_status_for_rescheduling(self, all_videos):
        """Remet des vidéos en ready_for_upload pour re-scheduling"""
        print("\n🔄 REMETTRE EN 'READY_FOR_UPLOAD'")
        print("=" * 40)
        print("💡 Les vidéos seront disponibles pour nouveau planning")
        
        selection = input(f"Sélectionner vidéos (1-{len(all_videos)}, ex: 1,2,3 ou 'all'): ").strip()
        
        try:
            if selection.lower() == 'all':
                selected_videos = all_videos
            else:
                indices = [int(x.strip())-1 for x in selection.split(',')]
                selected_videos = [all_videos[i] for i in indices if 0 <= i < len(all_videos)]
            
            if not selected_videos:
                print("❌ Aucune vidéo sélectionnée")
                return
            
            print(f"\n📋 Vidéos à remettre en 'ready_for_upload' ({len(selected_videos)}):")
            for video_id, video_data in selected_videos:
                title = video_data.get('original_title', 'Unknown')[:50]
                print(f"- {title}")
            
            confirm = input(f"\nConfirmer? Les vidéos seront disponibles pour nouveau planning (y/n): ").lower()
            
            if confirm == 'y':
                for video_id, video_data in selected_videos:
                    # Keep upload history but change status
                    self.url_manager.update_video_status(
                        video_id, 
                        'ready_for_upload',
                        # Keep existing data
                        video_path=video_data.get('video_path'),
                        original_title=video_data.get('original_title'),
                        ai_data=video_data.get('ai_data')
                    )
                
                print(f"✅ {len(selected_videos)} vidéo(s) remise(s) en 'ready_for_upload'!")
                print("💡 Utilisez l'option 3 pour créer un nouveau planning")
            else:
                print("❌ Opération annulée")
                
        except (ValueError, IndexError):
            print("❌ Format invalide")
        except Exception as e:
            print(f"❌ Erreur: {e}")
    
    def change_video_target_channel(self, all_videos):
        """Change le channel de destination d'une vidéo"""
        print("\n📺 CHANGER LE CHANNEL DE DESTINATION")
        print("=" * 40)
        
        if not MULTI_CHANNEL_SUPPORT:
            print("❌ Multi-channel support non disponible")
            return
        
        try:
            from channel_manager import ChannelManager
            manager = ChannelManager()
            channels = manager.list_channels()
            
            if not channels:
                print("❌ Aucun channel configuré")
                return
            
            print("📺 Channels disponibles:")
            for i, channel in enumerate(channels, 1):
                print(f"{i}. {channel.get('display_name', channel.get('name', 'Unknown'))}")
            
            channel_choice = int(input(f"Choisir nouveau channel (1-{len(channels)}): "))
            selected_channel = channels[channel_choice - 1]
            target_channel = selected_channel.get('name')
            
            selection = input(f"\nSélectionner vidéos (1-{len(all_videos)}, ex: 1,2,3): ").strip()
            indices = [int(x.strip())-1 for x in selection.split(',')]
            selected_videos = [all_videos[i] for i in indices if 0 <= i < len(all_videos)]
            
            if not selected_videos:
                print("❌ Aucune vidéo sélectionnée")
                return
            
            print(f"\n📋 Changer le channel pour {len(selected_videos)} vidéo(s) vers: {selected_channel.get('display_name', target_channel)}")
            confirm = input("Confirmer? (y/n): ").lower()
            
            if confirm == 'y':
                db = self.url_manager.load_database()
                for video_id, video_data in selected_videos:
                    # Update target channel
                    db['videos'][video_id]['target_channel'] = target_channel
                    # Reset status to ready for new channel
                    db['videos'][video_id]['status'] = 'ready_for_upload'

                self.url_manager.save_database(db)

                print(f"✅ Channel changé pour {len(selected_videos)} vidéo(s)!")
            else:
                print("❌ Opération annulée")
                
        except (ValueError, IndexError):
            print("❌ Choix invalide")
        except Exception as e:
            print(f"❌ Erreur: {e}")
    
    def reset_video_upload_history(self, all_videos):
        """Reset complet de l'historique d'upload"""
        print("\n🗑️  RESET COMPLET DE L'HISTORIQUE")
        print("=" * 40)
        print("⚠️  ATTENTION: Ceci supprimera tout l'historique d'upload!")
        print("💡 Utiliser seulement si vous voulez complètement reset une vidéo")
        
        selection = input(f"Sélectionner vidéos (1-{len(all_videos)}, ex: 1,2,3): ").strip()
        
        try:
            indices = [int(x.strip())-1 for x in selection.split(',')]
            selected_videos = [all_videos[i] for i in indices if 0 <= i < len(all_videos)]
            
            if not selected_videos:
                print("❌ Aucune vidéo sélectionnée")
                return
            
            print(f"\n⚠️  RESET COMPLET pour {len(selected_videos)} vidéo(s):")
            for video_id, video_data in selected_videos:
                title = video_data.get('original_title', 'Unknown')[:50]
                print(f"- {title}")
            
            print("\nCeci supprimera:")
            print("• Liens YouTube")
            print("• Historique d'upload")
            print("• Channel de destination")
            print("• Statut programmé")
            
            confirm = input("\nÊtes-vous sûr? Tapez 'RESET' pour confirmer: ").strip()
            
            if confirm == 'RESET':
                db = self.url_manager.load_database()
                for video_id, video_data in selected_videos:
                    # Remove upload-related data
                    video_ref = db['videos'][video_id]
                    video_ref.pop('youtube_url', None)
                    video_ref.pop('uploaded_channel', None)
                    video_ref.pop('scheduled_publish_time', None)
                    video_ref.pop('target_channel', None)
                    video_ref.pop('upload_history', None)
                    
                    # Reset status
                    video_ref['status'] = 'ready_for_upload'

                self.url_manager.save_database(db)

                print(f"✅ Reset complet effectué pour {len(selected_videos)} vidéo(s)!")
            else:
                print("❌ Reset annulé")
                
        except (ValueError, IndexError):
            print("❌ Format invalide")
        except Exception as e:
            print(f"❌ Erreur: {e}")

if __name__ == "__main__":
    processor = BatchProcessor()
    processor.interactive_menu()