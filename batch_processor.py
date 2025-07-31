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
        
    def load_config(self, config_path: str):
        """Charge la configuration"""
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
    
    def process_url_file(self, file_path: str, batch_name: str = None) -> str:
        """Traite un fichier d'URLs et crée un batch"""
        if not batch_name:
            batch_name = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        print(f"📋 Traitement du fichier: {file_path}")
        
        # Parse le fichier d'URLs
        videos = self.url_manager.parse_url_file(file_path)
        if not videos:
            print("❌ Aucune URL valide trouvée")
            return None
        
        print(f"✅ {len(videos)} URLs trouvées")
        
        # Ajoute le batch à la base
        batch_id = self.url_manager.add_batch(batch_name, videos)
        
        return batch_id
    
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
                
                video_path, title = self.download_tiktok_video(video['url'])
                if not video_path:
                    self.url_manager.update_video_status(
                        video['video_id'], 
                        'download_failed'
                    )
                    continue
                
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
                
                ai_data = self.generate_ai_content(video, title)
                
                # Étape 4: Mise à jour des données
                self.url_manager.update_video_status(
                    video['video_id'], 
                    'ready_for_upload',
                    video_path=processed_path,
                    original_title=title,
                    ai_data=ai_data
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
    
    def download_tiktok_video(self, url: str) -> tuple:
        """Interface avec le script de téléchargement existant"""
        try:
            import yt_dlp
            import re
            from pathlib import Path
            import shutil
            
            # CLEAR TEMP FOLDER FIRST to avoid conflicts
            temp_path = Path('temp/')
            if temp_path.exists():
                for file in temp_path.glob('*.mp4'):
                    file.unlink()  # Delete old mp4 files
            
            ydl_opts = {
                'outtmpl': f"temp/%(title)s.%(ext)s",
                'format': 'best[height<=1920]',
                'writeinfojson': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                safe_title = re.sub(r'[^\w\s-]', '', info.get('title', 'video'))[:30]
                ydl.download([url])
                
                # Now we can safely get the only mp4 file
                temp_files = list(Path('temp/').glob('*.mp4'))
                if temp_files:
                    return str(temp_files[0]), safe_title  # Should be only one file now
                    
        except Exception as e:
            logger.error(f"Erreur téléchargement: {e}")
        
        return None, None
    
    def process_tiktok_video(self, video_path: str, title: str, bg_mode: str) -> str:
        """Interface avec le traitement vidéo existant"""
        # Réutilise la fonction de test3_script.py
        try:
            # Ici tu peux appeler directement process_video_with_background_options
            # ou réimplémenter la logique selon tes besoins
            from test3_script import process_video_with_background_options
            
            return process_video_with_background_options(
                video_path, title, bg_mode
            )
            
        except Exception as e:
            logger.error(f"Erreur traitement vidéo: {e}")
            return None
    
    def generate_ai_content(self, video: Dict, title: str) -> Dict:
        """Génère le contenu AI pour une vidéo avec gestion d'erreurs"""
        try:
            description = video.get('custom_description', '') or ''  # Handle None values
            custom_title = video.get('custom_title', title) or title  # Handle None values
            
            # Ensure we have strings, not None
            if not isinstance(custom_title, str):
                custom_title = str(custom_title) if custom_title else title
            if not isinstance(description, str):
                description = str(description) if description else ''
            
            return self.ai_generator.generate_tags(custom_title, description)
            
        except Exception as e:
            logger.error(f"Erreur génération AI tags: {e}")
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

    def create_upload_schedule(self, max_videos: int = None, use_analytics: bool = None) -> List[Dict]:
        """Crée un planning d'upload pour les vidéos prêtes"""
        
        # Récupère les vidéos prêtes
        ready_videos = []
        db = self.url_manager.load_database()
        
        for video in db['videos'].values():
            if video['status'] == 'ready_for_upload':
                ready_videos.append(video)
        
        if not ready_videos:
            print("❌ Aucune vidéo prête pour l'upload")
            return []
        
        # Limite le nombre si spécifié
        if max_videos:
            ready_videos = ready_videos[:max_videos]
        
        # Determine scheduling method
        if use_analytics is None:
            use_analytics = ANALYTICS_SUPPORT and self.ask_user_analytics_preference()
        
        if use_analytics and ANALYTICS_SUPPORT:
            print(f"� Création du planning ANALYTICS pour {len(ready_videos)} vidéos")
            schedule = self.smart_scheduler.create_analytics_based_schedule(ready_videos)
        else:
            print(f"📅 Création du planning STANDARD pour {len(ready_videos)} vidéos")
            schedule = self.scheduler.create_upload_schedule(ready_videos)
        
        # Sauvegarde
        self.scheduler.save_schedule(schedule)
        
        return schedule
    
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
            print("7. ❌ Quitter")
            
            choice = input("\nChoix (1-7): ").strip()
            
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
        
        max_videos = input("Nombre max de vidéos (ou Enter pour toutes): ").strip()
        max_videos = int(max_videos) if max_videos.isdigit() else None
        
        # Ask about analytics if available
        use_analytics = None
        if ANALYTICS_SUPPORT:
            print("\n🧠 Analytics-based scheduling available!")
            use_analytics = self.ask_user_analytics_preference()
        
        schedule = self.create_upload_schedule(max_videos, use_analytics)
        
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
                self.create_upload_schedule()
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

if __name__ == "__main__":
    processor = BatchProcessor()
    processor.interactive_menu()