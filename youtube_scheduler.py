#!/usr/bin/env python3
"""
YouTube Scheduler - Planification intelligente des uploads
========================================================
Gère la planification des publications YouTube avec optimisation
"""

import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import yaml
from dateutil import parser
import pytz

class YouTubeScheduler:
    def __init__(self, config_path="config.yaml"):
        self.load_config(config_path)
        self.timezone = pytz.timezone(self.config['general']['timezone'])
    
    def load_config(self, config_path: str):
        """Charge la configuration"""
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
    
    def get_optimal_publish_times(self, num_videos: int, start_date: Optional[datetime] = None,
                                   preferred_days: Optional[List[str]] = None,
                                   preferred_hours: Optional[List[str]] = None) -> List[datetime]:
        """Calcule les meilleurs créneaux de publication.

        preferred_days/preferred_hours: override propre à une chaîne (depuis son
        profile.json) ; si absent, retombe sur les valeurs globales de config.yaml.
        """
        if not start_date:
            start_date = datetime.now(self.timezone)

        # Configuration du scheduling
        spacing_hours = self.config['scheduling']['spacing_hours']
        preferred_days = preferred_days or self.config['scheduling']['preferred_days']
        preferred_hours = preferred_hours or self.config['scheduling']['preferred_hours']

        # Convertit les jours en indices (lundi=0, dimanche=6)
        day_map = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }
        preferred_day_indices = [day_map[day] for day in preferred_days]
        
        publish_times = []
        current_date = start_date
        
        for i in range(num_videos):
            # Trouve le prochain créneau optimal
            optimal_time = self.find_next_optimal_slot(
                current_date, 
                preferred_day_indices, 
                preferred_hours
            )
            
            publish_times.append(optimal_time)
            
            # Prochaine date minimum (espacement)
            current_date = optimal_time + timedelta(hours=spacing_hours)
        
        return publish_times
    
    def find_next_optimal_slot(self, from_date: datetime, preferred_days: List[int], preferred_hours: List[str]) -> datetime:
        """Trouve le prochain créneau optimal"""
        current = from_date
        
        # Cherche jusqu'à 14 jours max
        for days_ahead in range(14):
            check_date = current + timedelta(days=days_ahead)
            
            # Vérifie si c'est un jour préféré
            if check_date.weekday() in preferred_days:
                # Trouve la meilleure heure
                for hour_str in preferred_hours:
                    hour, minute = map(int, hour_str.split(':'))
                    potential_time = check_date.replace(
                        hour=hour, 
                        minute=minute, 
                        second=0, 
                        microsecond=0
                    )
                    
                    # Vérifie que c'est dans le futur
                    if potential_time > from_date:
                        return potential_time
        
        # Fallback: prochaine heure préférée
        next_day = current + timedelta(days=1)
        hour, minute = map(int, preferred_hours[0].split(':'))
        return next_day.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    def create_upload_schedule(self, videos: List[Dict], start_date: Optional[datetime] = None,
                                channel_manager=None) -> List[Dict]:
        """Crée un planning d'upload complet.

        Chaque chaîne obtient sa PROPRE séquence de créneaux, indépendante des
        autres : si la chaîne X prend les dates a/b/c, la chaîne Z prend AUSSI
        a/b/c (ses propres premiers créneaux disponibles), jamais d/e/f à la
        suite de X. Sans ça, une seule file globale ferait hériter les chaînes
        traitées en dernier des dates les plus tardives.
        """
        max_weekly = self.config['general']['max_weekly_uploads']

        by_channel: Dict[str, List[Dict]] = {}
        for video in videos:
            channel = video.get('channel') or video.get('target_channel', 'default')
            by_channel.setdefault(channel, []).append(video)

        schedule = []
        for channel, channel_videos in by_channel.items():
            if len(channel_videos) > max_weekly:
                print(f"⚠️ {channel}: {len(channel_videos)} vidéos > limite hebdomadaire ({max_weekly})")
                channel_videos = channel_videos[:max_weekly]

            profile = channel_manager.get_channel_profile(channel) if channel_manager else {}
            publish_times = self.get_optimal_publish_times(
                len(channel_videos), start_date,
                preferred_days=profile.get('preferred_days') or None,
                preferred_hours=profile.get('preferred_hours') or None
            )

            for i, (video, publish_time) in enumerate(zip(channel_videos, publish_times)):
                title = video.get('custom_title') or video.get('title') or f'Video {i+1}'
                schedule.append({
                    'video_id': video.get('video_id', f'video_{i}'),
                    'title': title,
                    'channel': channel,
                    'scheduled_time': publish_time.isoformat(),
                    'scheduled_time_readable': publish_time.strftime('%A %d/%m/%Y à %H:%M'),
                    'status': 'scheduled',
                    'priority': video.get('priority', 'normal'),
                    'video_data': video
                })

        schedule.sort(key=lambda e: e['scheduled_time'])
        return schedule
    
    def validate_schedule(self, schedule: List[Dict]) -> Dict:
        """Valide un planning et retourne des statistiques"""
        
        # Groupe par jour
        daily_counts = {}
        weekly_counts = {}
        
        timed = [item for item in schedule if item.get('scheduled_time')]   # one published right away has no time
        for item in timed:
            publish_time = parser.parse(item['scheduled_time'])
            day_key = publish_time.strftime('%Y-%m-%d')
            week_key = publish_time.strftime('%Y-W%U')
            
            daily_counts[day_key] = daily_counts.get(day_key, 0) + 1
            weekly_counts[week_key] = weekly_counts.get(week_key, 0) + 1
        
        # Détecte les violations
        violations = []
        max_daily = self.config['general']['max_daily_uploads']
        max_weekly = self.config['general']['max_weekly_uploads']
        
        for day, count in daily_counts.items():
            if count > max_daily:
                violations.append(f"Jour {day}: {count} vidéos > limite {max_daily}")
        
        for week, count in weekly_counts.items():
            if count > max_weekly:
                violations.append(f"Semaine {week}: {count} vidéos > limite {max_weekly}")
        
        return {
            'total_videos': len(schedule),
            'date_range': {
                'start': min((item['scheduled_time'] for item in timed), default=None),
                'end': max((item['scheduled_time'] for item in timed), default=None)
            },
            'daily_distribution': daily_counts,
            'weekly_distribution': weekly_counts,
            'violations': violations,
            'is_valid': len(violations) == 0
        }
    
    def save_schedule(self, schedule: List[Dict], filename: str = "upload_schedule.json",
                      schedule_method: Optional[str] = None):
        """Sauvegarde le planning.

        schedule_method ("static" | "analytics" | "ai") est mémorisé dans le
        fichier pour que les vidéos ajoutées plus tard au planning
        (BatchProcessor.ensure_schedule_includes_all_ready) suivent la même
        méthode que celle choisie par l'utilisateur. Sans valeur, celle déjà
        présente dans le fichier est conservée (ex: simple modif d'une date)."""
        if schedule_method is None and os.path.exists(filename):
            try:
                schedule_method = self.load_schedule(filename).get('schedule_method')
            except (OSError, json.JSONDecodeError):
                pass
        schedule_data = {
            'created_at': datetime.now().isoformat(),
            'config_used': self.config,
            'schedule_method': schedule_method,
            'schedule': schedule,
            'validation': self.validate_schedule(schedule) if schedule else None
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(schedule_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Planning sauvegardé dans {filename}")
        return filename
    
    def load_schedule(self, filename: str = "upload_schedule.json") -> Optional[Dict]:
        """Charge un planning existant — None s'il n'y en a pas encore (tous
        les appelants font déjà `load_schedule() or {...}`; avant, une première
        utilisation sans planning levait FileNotFoundError → erreur 500)."""
        if not os.path.exists(filename):
            return None
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def print_schedule_summary(self, schedule: List[Dict]):
        """Affiche un résumé du planning"""
        print(f"\n📅 PLANNING D'UPLOAD - {len(schedule)} vidéos")
        print("=" * 50)
        
        for i, item in enumerate(schedule, 1):
            # Safely handle None titles
            title = item.get('title') or 'Untitled Video'
            print(f"{i:2d}. {item['scheduled_time_readable']}")
            print(f"    📹 {title[:50]}...")
            print(f"    🏷️ Priorité: {item['priority']}")
            print()
        
        # Validation
        validation = self.validate_schedule(schedule)
        if validation['is_valid']:
            print("✅ Planning valide")
        else:
            print("⚠️ Violations détectées:")
            for violation in validation['violations']:
                print(f"   - {violation}")

# Test du planificateur
if __name__ == "__main__":
    # Vidéos d'exemple
    example_videos = [
        {'video_id': 'v1', 'title': 'Anime Epic Fight', 'priority': 'high'},
        {'video_id': 'v2', 'title': 'Gaming Fail Compilation', 'priority': 'normal'},
        {'video_id': 'v3', 'title': 'Daily Life Routine', 'priority': 'low'},
        {'video_id': 'v4', 'title': 'Funny Moments', 'priority': 'normal'},
        {'video_id': 'v5', 'title': 'TikTok Viral', 'priority': 'high'},
    ]
    
    scheduler = YouTubeScheduler()
    
    # Crée un planning
    schedule = scheduler.create_upload_schedule(example_videos)
    
    # Affiche le résumé
    scheduler.print_schedule_summary(schedule)
    
    # Sauvegarde
    scheduler.save_schedule(schedule, "example_schedule.json")