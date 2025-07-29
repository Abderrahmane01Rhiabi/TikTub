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

    def create_upload_schedule(self, max_videos: int = None) -> List[Dict]:
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
        
        print(f"📅 Création du planning pour {len(ready_videos)} vidéos")
        
        # Crée le planning
        schedule = self.scheduler.create_upload_schedule(ready_videos)
        
        # Sauvegarde
        self.scheduler.save_schedule(schedule)
        
        return schedule
    
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
        
        schedule = self.create_upload_schedule(max_videos)
        
        if schedule:
            self.scheduler.print_schedule_summary(schedule)
    
    def menu_show_status(self):
        """Menu affichage statut"""
        print("\n📊 STATUT DES VIDÉOS")
        
        summary = self.url_manager.get_status_summary()
        
        print("Résumé des statuts:")
        for status, count in summary.items():
            print(f"  {status}: {count} vidéos")
        
        # Détails des vidéos en erreur
        if 'error' in summary:
            print("\n❌ Vidéos en erreur:")
            db = self.url_manager.load_database()
            for video in db['videos'].values():
                if video['status'] == 'error':
                    print(f"  - {video['url']}: {video.get('error_message', 'Erreur inconnue')}")
    
    def menu_upload_youtube(self):
        """Menu upload YouTube"""
        print("\n🎬 UPLOAD VERS YOUTUBE")
        print("Cette fonctionnalité utilise ton script youtube_uploader.py existant")
        
        # Charge le planning existant ou en crée un nouveau
        if os.path.exists('upload_schedule.json'):
            use_existing = input("Utiliser le planning existant? (y/n): ").lower() == 'y'
            if use_existing:
                schedule_data = self.scheduler.load_schedule()
                print(f"📅 Planning chargé: {len(schedule_data['schedule'])} vidéos")
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

if __name__ == "__main__":
    processor = BatchProcessor()
    processor.interactive_menu()