#!/usr/bin/env python3
"""
Batch Processor - Système complet TikTok → YouTube automatisé
===========================================================
Workflow: URLs → Download → Process → AI Tags → Schedule → Upload
"""

import os
import yaml
from pathlib import Path
from datetime import datetime, timedelta
import logging

# Imports des modules créés
from url_manager import URLManager
from ai_tags_generator import AITagsGenerator  
from youtube_scheduler import YouTubeScheduler
from montage import pipeline as montage_pipeline
from montage import recipes as montage_recipes

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

logging.basicConfig(level=logging.INFO)

import re as _re

# yt-dlp error texts → what it means for the user, in French. Checked in
# order; the first matching pattern wins. The raw text is kept alongside.
DOWNLOAD_ERROR_HINTS = [
    (r"isn't available to everyone|certain audiences|age.?restrict|inappropriate for some users|confirm your age",
     "Publication à accès restreint (âge ou audience limitée) : la plateforme ne la montre pas sans connexion à un compte."),
    (r"private|login required|log in|requested content is not available|rate-limit reached or login",
     "Publication privée, ou connexion au compte requise pour la voir."),
    (r"no video formats|there is no video|no video in this post|Aucune vidéo \.mp4",
     "Pas de vidéo dans cette publication (photo ou diaporama)."),
    (r"unsupported url",
     "Lien non reconnu : ce n'est pas une vidéo TikTok, Instagram ou Facebook."),
    (r"http error 429|too many requests",
     "Trop de requêtes : la plateforme limite temporairement les téléchargements, réessaie plus tard."),
    (r"404|not found|has been removed|deleted|no longer available|video unavailable|post isn't available",
     "Publication introuvable ou supprimée."),
    (r"timed out|connection|network|temporary failure in name resolution",
     "Problème de connexion réseau pendant le téléchargement."),
]


def explain_download_error(raw: str):
    """(French explanation, cleaned raw message) for a yt-dlp failure. The
    raw text loses its terminal color codes and its "ERROR: [Site] id:"
    prefix."""
    text = _re.sub(r"\x1b\[[0-9;]*m", "", raw or "").strip()
    text = _re.sub(r"^(ERROR:\s*)+", "", text)
    text = _re.sub(r"^\[[^\]]+\]\s*[\w-]+:\s*", "", text).strip()
    for pattern, hint in DOWNLOAD_ERROR_HINTS:
        if _re.search(pattern, text, _re.IGNORECASE):
            return hint, text
    return (text[:300] or "Échec du téléchargement"), text
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
    
    def download_batch(self, batch_id: str, on_item=None) -> List[Dict]:
        """Télécharge uniquement les vidéos d'un batch (pas d'IA, pas de background).

        Les vidéos téléchargées sont marquées 'selected' par défaut (l'UI affiche
        leurs cases cochées d'emblée) — décocher une case dans l'étape suivante la
        repasse à 'rejected'.

        on_item(video_id, state, message), si fourni : l'état de CHAQUE lien au
        fil de l'eau ('running' + étape, puis 'done' / 'failed' + raison /
        'duplicate'), pour le suivi lien par lien de l'UI.
        """
        def notify(video_id, state, message=None, detail=None):
            if on_item:
                on_item(video_id, state, message, detail)
        batch_videos = sorted(self.list_batch_videos(batch_id), key=lambda v: v.get('line_number') or 0)

        if not batch_videos:
            print("❌ Batch introuvable")
            return []

        downloaded = []
        skipped_duplicates = 0
        for video in batch_videos:
            if video['status'] != 'pending':
                continue
            notify(video['video_id'], 'running', 'vérification…')

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
                notify(video['video_id'], 'duplicate', 'déjà importée sur cette chaîne')
                continue

            self.url_manager.update_video_status(video['video_id'], 'downloading')
            notify(video['video_id'], 'running', 'connexion…')
            video_path, title, tiktok_meta = self.download_tiktok_video(
                video['url'], video_id=video['video_id'],
                on_status=lambda message, vid=video['video_id']: notify(vid, 'running', message),
            )

            if not video_path:
                reason = tiktok_meta.get('download_error')
                detail = tiktok_meta.get('download_error_detail')
                self.url_manager.update_video_status(video['video_id'], 'download_failed',
                                                     error_message=reason, error_detail=detail)
                notify(video['video_id'], 'failed', reason or 'échec du téléchargement', detail)
                continue

            self.url_manager.update_video_status(
                video['video_id'], 'selected',
                raw_video_path=video_path, original_title=title,
                **tiktok_meta
            )
            downloaded.append(video)
            notify(video['video_id'], 'done', title)

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

    # Within one video: encoding is the long, measurable part; the AI pass
    # after it has no progress of its own, so it gets the last slice.
    PROCESS_ENCODE_SHARE = 0.85

    def process_selected_videos(self, batch_id: str = None, on_progress=None) -> int:
        """Traite (background + IA channel-aware) les vidéos marquées 'selected'.

        Sans batch_id : traite TOUTES les vidéos sélectionnées, toutes chaînes/batches
        confondus (c'est le mode utilisé par l'assistant web, qui travaille sur les 6
        chaînes en une seule fois plutôt que chaîne par chaîne).

        on_progress(index, total, title, phase, fraction_overall), si fourni :
        progression réelle (encodage image par image, puis phase IA), pour
        la barre de progression de l'UI."""
        selected_videos = (
            self.list_batch_videos(batch_id, status='selected') if batch_id
            else self.list_all_videos(status='selected')
        )
        if not selected_videos:
            print("❌ Aucune vidéo sélectionnée à traiter")
            return 0

        processed_count = 0
        total = len(selected_videos)
        for index, video in enumerate(selected_videos):
            channel_name = video.get('channel', 'default')
            print(f"\n🔄 Traitement (chaîne: {channel_name}): {video['url']}")
            label = video.get('original_title') or video.get('url')

            def report(phase, within, i=index):
                if on_progress:
                    on_progress(i, total, label, phase, (i + within) / total)

            report('encodage', 0.0)

            try:
                self.url_manager.update_video_status(video['video_id'], 'processing')

                raw_path = video.get('raw_video_path')
                title = video.get('original_title', 'video')
                if not raw_path or not os.path.exists(raw_path):
                    self.url_manager.update_video_status(video['video_id'], 'processing_failed')
                    continue

                profile = self._channel_profile(channel_name)
                if montage_recipes.edit_mode(profile, video) == 'montage':
                    if not (video.get('montage') or {}).get('validated'):
                        # Montage auto, first pass: plan only, then wait for
                        # the person in Import → Montage (nothing rendered yet)
                        self.url_manager.update_video_status(video['video_id'], 'montage_planning',
                                                             edit_mode='montage')
                        montage = montage_pipeline.prepare_review(
                            video, channel_name, report=lambda phase, f: report(phase, f))
                        self.url_manager.update_video_status(video['video_id'], 'montage_review', montage=montage)
                        continue
                    processed_path = self.render_montage(
                        video, profile, progress_cb=lambda f: report('montage', self.PROCESS_ENCODE_SHARE * f))
                else:
                    bg_mode, specific_bg = self.get_background_for_video(video)
                    frame_mode = video.get('frame_mode')
                    rounded_corners = video.get('rounded_corners', False)
                    processed_path = self.process_tiktok_video(
                        raw_path, title, bg_mode, specific_bg, frame_mode, rounded_corners,
                        output_name=video['video_id'],  # unique per video, see video_processor
                        progress_cb=lambda f: report('encodage', self.PROCESS_ENCODE_SHARE * f),
                    )

                if not processed_path:
                    self.url_manager.update_video_status(video['video_id'], 'processing_failed')
                    continue

                if video.get('reprocess_keep_ai') and video.get('ai_data'):
                    # Re-rendering a video whose file went missing: keep the
                    # title/description/tags already reviewed — only the
                    # file needed redoing, not the AI pass.
                    ai_data = video['ai_data']
                else:
                    self.url_manager.update_video_status(video['video_id'], 'generating_tags')
                    report('ia', self.PROCESS_ENCODE_SHARE)
                    ai_data = self.generate_ai_content(video, title, video_path=processed_path)
                report('ia', 1.0)

                self.url_manager.update_video_status(
                    video['video_id'], 'ready_for_upload',
                    video_path=processed_path, ai_data=ai_data, reprocess_keep_ai=False
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
        return 'none', None  # unrecognized mode -> video_processor falls back to plain black, no randomness

    def download_tiktok_video(self, url: str, video_id: str = None, on_status=None) -> tuple:
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

            def progress_hook(d):
                # yt-dlp's own progress: bytes as they arrive, then "finished"
                if not on_status:
                    return
                if d.get('status') == 'downloading':
                    total = d.get('total_bytes') or d.get('total_bytes_estimate')
                    done = d.get('downloaded_bytes') or 0
                    on_status(f"téléchargement {int(done * 100 / total)} %" if total else "téléchargement…")
                elif d.get('status') == 'finished':
                    on_status("finalisation…")

            ydl_opts = {
                'outtmpl': f"{temp_path}/%(id)s.%(ext)s",
                'format': video_format,
                'writeinfojson': True,
                'progress_hooks': [progress_hook],
                'no_color': True,  # its error texts reach the UI: no terminal color codes
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if on_status:
                    on_status("lecture de la publication…")
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
                # yt-dlp "succeeded" but produced no .mp4 (photo post, slideshow...)
                hint, detail = explain_download_error("Aucune vidéo .mp4 récupérée (publication photo/diaporama ?)")
                return None, None, {'download_error': hint, 'download_error_detail': detail}

        except Exception as e:
            logger.error(f"Erreur téléchargement: {e}")
            # Kept on the video row (error_message) so the UI can say WHY,
            # in plain French, not just "téléchargement échoué".
            hint, detail = explain_download_error(str(e))
            return None, None, {'download_error': hint, 'download_error_detail': detail[:500]}

        return None, None, {}

    def _channel_profile(self, channel_name: str) -> Dict:
        return self.channel_manager.get_channel_profile(channel_name) if MULTI_CHANNEL_SUPPORT else {}

    def music_dir(self, channel_name: str) -> Optional[str]:
        return self.channel_manager.get_assets_dirs(channel_name)["music"] if MULTI_CHANNEL_SUPPORT else None

    def render_montage(self, video: Dict, profile: Dict, progress_cb=None) -> Optional[str]:
        """Montage auto, second pass (plan validated in Import → Montage): the
        real render, to the same output path a simple render would use."""
        from video_processor import processed_output_paths
        out_path, _ = processed_output_paths(video.get('original_title', 'video'), 'montage', video['video_id'])
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        summary = montage_pipeline.render_final(video, profile, self.music_dir(video.get('channel', 'default')),
                                                out_path, progress_cb=progress_cb)
        # brolls may have been replaced (a shot deleted from the library since the review)
        self.url_manager.update_video_status(video['video_id'], 'processing',
                                             montage={**video['montage'], 'summary': summary})
        return out_path

    def process_tiktok_video(self, video_path: str, title: str, bg_mode: str, specific_bg: str = None, frame_mode: str = None, rounded_corners: bool = False, output_name: str = None, progress_cb=None) -> str:
        """Interface avec le traitement vidéo existant"""
        # Réutilise la fonction de video_processor.py
        try:
            from video_processor import process_video_with_background_options

            return process_video_with_background_options(
                video_path, title, bg_mode, specific_bg, frame_mode, rounded_corners,
                output_name=output_name, progress_cb=progress_cb
            )

        except Exception as e:
            logger.error(f"Erreur traitement vidéo: {e}")
            return None

    def get_frame_suggestion(self, video_id: str) -> Optional[Dict]:
        """Cadrage suggéré pour une vidéo 'selected' (avant traitement), basé
        sur son ratio natif — voir video_processor.suggest_frame_mode."""
        db = self.url_manager.load_database()
        video = db['videos'].get(video_id)
        if not video:
            return None

        raw_path = video.get('raw_video_path')
        if not raw_path or not os.path.exists(raw_path):
            return None

        from video_processor import get_video_dimensions, suggest_frame_mode
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
        self.scheduler.save_schedule(schedule, schedule_method=schedule_method)
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

    def _parse_slot(self, value: str) -> datetime:
        """Les méthodes de planning n'écrivent pas la même chose : 'static'
        une date ISO avec fuseau, 'analytics'/'ai'/modif manuelle une date
        locale sans fuseau. Tout est ramené à une date avec fuseau (celui de
        config.yaml) pour pouvoir les comparer entre elles."""
        from dateutil import parser as date_parser
        dt = date_parser.parse(value)
        return dt if dt.tzinfo else self.scheduler.timezone.localize(dt)

    def _shift_off_taken_slots(self, new_entries: List[Dict], existing_entries: List[Dict]):
        """Chaque méthode de planning repart de "maintenant" : les vidéos
        ajoutées après coup tomberaient donc sur les MÊMES premiers créneaux
        que celles déjà planifiées sur la même chaîne. Décale chaque nouvelle
        entrée (de spacing_hours en spacing_hours) jusqu'à ce qu'elle soit à
        au moins spacing_hours de tout créneau déjà pris sur sa chaîne."""
        from dateutil import parser as date_parser
        spacing = timedelta(hours=self.config['scheduling']['spacing_hours'])
        taken: Dict[str, List[datetime]] = {}
        for entry in existing_entries:
            try:
                taken.setdefault(entry.get('channel'), []).append(self._parse_slot(entry['scheduled_time']))
            except (KeyError, ValueError, TypeError):
                continue

        for entry in sorted(new_entries, key=lambda e: self._parse_slot(e['scheduled_time'])):
            slot = original = self._parse_slot(entry['scheduled_time'])
            channel_slots = taken.setdefault(entry.get('channel'), [])
            while any(abs(slot - other) < spacing for other in channel_slots):
                slot += spacing
            channel_slots.append(slot)
            if slot != original:
                # Keep the format the scheduling method originally wrote (with/without timezone)
                had_tz = date_parser.parse(entry['scheduled_time']).tzinfo is not None
                entry['scheduled_time'] = slot.isoformat() if had_tz else slot.strftime('%Y-%m-%d %H:%M:%S')
                entry['scheduled_time_readable'] = slot.strftime('%A %d/%m/%Y à %H:%M')

    def ensure_schedule_includes_all_ready(self, schedule_method: str = None) -> List[Dict]:
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
        # Même méthode que celle choisie à "Générer le planning", pas toujours 'static'
        schedule_method = schedule_method or existing.get('schedule_method') or 'static'
        channel_manager = self.channel_manager if MULTI_CHANNEL_SUPPORT else None

        if schedule_method == 'ai' and AI_SCHEDULING_SUPPORT:
            new_entries = self.ai_scheduler.create_ai_suggested_schedule(missing, self.config, channel_manager)['schedule']
        elif schedule_method == 'analytics' and ANALYTICS_SUPPORT:
            new_entries = self.smart_scheduler.create_analytics_based_schedule(missing)['schedule']
        else:
            new_entries = self.scheduler.create_upload_schedule(missing, channel_manager=channel_manager)

        self._shift_off_taken_slots(new_entries, existing_schedule)
        combined = sorted(existing_schedule + new_entries, key=lambda e: self._parse_slot(e['scheduled_time']))
        self.scheduler.save_schedule(combined, schedule_method=schedule_method)
        self._record_schedule_decisions(new_entries, schedule_method)
        return combined
