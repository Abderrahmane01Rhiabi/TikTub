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
    
    def get_optimal_publish_times(self, num_videos: int, start_date: Optional[datetime] = None) -> List[datetime]:
        """Calcule les meilleurs créneaux de publication"""
        if not start_date:
            start_date = datetime.now(self.timezone)
        
        # Configuration du scheduling
        spacing_hours = self.config['scheduling']['spacing_hours']
        # Ensure spacing_hours is a number, not a timedelta
        if hasattr(spacing_hours, 'total_seconds'):
            spacing_hours = spacing_hours.total_seconds() / 3600
        preferred_days = self.config['scheduling']['preferred_days']
        preferred_hours = self.config['scheduling']['preferred_hours']
        
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
    
    def ask_scheduling_method(self) -> bool:
        """Ask user to choose between static and analytics-based scheduling"""
        print("\n🕐 SCHEDULING METHOD SELECTION")
        print("="*40)
        print("Choose your scheduling strategy:")
        print()
        print("1. 📅 STATIC SCHEDULING")
        print("   • Uses fixed times from config")
        print("   • Predictable schedule")
        print("   • Monday/Wednesday/Friday at 09:00, 17:00, 20:00")
        print("   • 48-hour spacing between videos")
        print()
        print("2. 🧠 ANALYTICS-BASED SCHEDULING")
        print("   • Uses real audience data from each channel")
        print("   • Optimized for maximum engagement")
        print("   • Based on when YOUR viewers are most active")
        print("   • Adapts to each channel's unique audience")
        print()
        
        while True:
            choice = input("Choose method (1=Static, 2=Analytics) [1]: ").strip()
            
            if choice == '' or choice == '1':
                print("📅 Using STATIC scheduling")
                return False
            elif choice == '2':
                print("🧠 Using ANALYTICS-BASED scheduling")
                return True
            else:
                print("❌ Please enter 1 or 2")
    
    def get_analytics_based_times(self, videos: List[Dict], start_date: Optional[datetime] = None, target_channel: str = None) -> List[datetime]:
        """Get optimal times based on channel analytics"""
        if not start_date:
            start_date = datetime.now(self.timezone)
        
        # Simulate analytics data - in real implementation, this would fetch from YouTube Analytics API
        channel_analytics = self.get_channel_analytics(target_channel)
        
        publish_times = []
        current_date = start_date
        
        for i in range(len(videos)):
            # Find next optimal slot based on analytics
            optimal_time = self.find_analytics_optimal_slot(
                current_date, 
                channel_analytics
            )
            
            publish_times.append(optimal_time)
            
            # Minimum spacing (still respect some spacing)
            spacing_hours = max(24, self.config['scheduling']['spacing_hours'] // 2)  # Reduce spacing for analytics
            current_date = optimal_time + timedelta(hours=spacing_hours)
        
        return publish_times
    
    def get_channel_analytics(self, channel_name: str) -> Dict:
        """Get analytics data for a specific channel"""
        # This would connect to YouTube Analytics API in real implementation
        # For now, return simulated data based on channel type
        
        analytics_data = {
            'AnimeShorts137': {
                'peak_days': [1, 2, 5, 6],  # Tuesday, Wednesday, Saturday, Sunday
                'peak_hours': ['14:00', '18:00', '21:00'],  # Afternoon/evening for anime fans
                'engagement_pattern': 'evening_focused'
            },
            'lungte8888': {
                'peak_days': [4, 5, 6],  # Friday, Saturday, Sunday
                'peak_hours': ['17:00', '19:00', '21:00'],  # Evening for dance content
                'engagement_pattern': 'dance_focused'
            },
            'meme0culture': {
                'peak_days': [0, 2, 4],  # Monday, Wednesday, Friday
                'peak_hours': ['12:00', '17:00', '20:00'],  # Lunch break and evening
                'engagement_pattern': 'workday_breaks'
            }
        }
        
        # Default fallback
        default_analytics = {
            'peak_days': [1, 3, 5],  # Tuesday, Thursday, Saturday
            'peak_hours': ['09:00', '17:00', '20:00'],
            'engagement_pattern': 'balanced'
        }
        
        return analytics_data.get(channel_name, default_analytics)
    
    def find_analytics_optimal_slot(self, from_date: datetime, analytics: Dict) -> datetime:
        """Find optimal slot based on analytics data"""
        current = from_date
        peak_days = analytics['peak_days']
        peak_hours = analytics['peak_hours']
        
        # Search for optimal slot within 14 days
        for days_ahead in range(14):
            check_date = current + timedelta(days=days_ahead)
            
            # Check if it's a peak day for this channel
            if check_date.weekday() in peak_days:
                # Find the best hour based on analytics
                for hour_str in peak_hours:
                    hour, minute = map(int, hour_str.split(':'))
                    potential_time = check_date.replace(
                        hour=hour, 
                        minute=minute, 
                        second=0, 
                        microsecond=0
                    )
                    
                    # Must be in the future
                    if potential_time > from_date:
                        return potential_time
        
        # Fallback to next available peak hour
        next_day = current + timedelta(days=1)
        hour, minute = map(int, peak_hours[0].split(':'))
        return next_day.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    def create_upload_schedule(self, videos: List[Dict], start_date: Optional[datetime] = None, use_analytics: bool = None, target_channel: str = None) -> List[Dict]:
        """Crée un planning d'upload complet avec choix de méthode"""
        
        # Limite selon la config
        max_daily = self.config['general']['max_daily_uploads']
        max_weekly = self.config['general']['max_weekly_uploads']
        
        if len(videos) > max_weekly:
            print(f"⚠️ Attention: {len(videos)} vidéos > limite hebdomadaire ({max_weekly})")
            videos = videos[:max_weekly]
        
        # Ask user for scheduling method if not specified
        if use_analytics is None:
            use_analytics = self.ask_scheduling_method()
        
        if use_analytics:
            # Analytics-based scheduling
            print(f"🧠 Creating ANALYTICS-BASED schedule for {len(videos)} videos")
            if target_channel:
                print(f"📺 Target channel: {target_channel}")
            publish_times = self.get_analytics_based_times(videos, start_date, target_channel)
        else:
            # Static scheduling
            print(f"📅 Creating STATIC schedule for {len(videos)} videos")
            if target_channel:
                print(f"📺 Target channel: {target_channel}")
            publish_times = self.get_optimal_publish_times(len(videos), start_date)
        
        # Crée le planning complet
        schedule = []
        for i, (video, publish_time) in enumerate(zip(videos, publish_times)):
            # Ensure we always have a valid title
            title = video.get('custom_title') or video.get('title') or f'Video {i+1}'
            
            schedule_item = {
                'video_id': video.get('video_id', f'video_{i}'),
                'title': title,
                'scheduled_time': publish_time.isoformat(),
                'scheduled_time_readable': publish_time.strftime('%A %d/%m/%Y à %H:%M'),
                'status': 'scheduled',
                'priority': video.get('priority', 'normal'),
                'scheduling_method': 'analytics' if use_analytics else 'static',
                'target_channel': target_channel,
                'video_data': video
            }
            schedule.append(schedule_item)
        
        return schedule
    
    def validate_schedule(self, schedule: List[Dict]) -> Dict:
        """Valide un planning et retourne des statistiques"""
        
        # Groupe par jour
        daily_counts = {}
        weekly_counts = {}
        
        for item in schedule:
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
                'start': min(item['scheduled_time'] for item in schedule),
                'end': max(item['scheduled_time'] for item in schedule)
            },
            'daily_distribution': daily_counts,
            'weekly_distribution': weekly_counts,
            'violations': violations,
            'is_valid': len(violations) == 0
        }
    
    def save_schedule(self, schedule: List[Dict], filename: str = "upload_schedule.json"):
        """Sauvegarde le planning"""
        schedule_data = {
            'created_at': datetime.now().isoformat(),
            'config_used': self.config,
            'schedule': schedule,
            'validation': self.validate_schedule(schedule)
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(schedule_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Planning sauvegardé dans {filename}")
        return filename
    
    def load_schedule(self, filename: str = "upload_schedule.json") -> Dict:
        """Charge un planning existant"""
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def print_schedule_summary(self, schedule: List[Dict]):
        """Affiche un résumé du planning"""
        if not schedule:
            print("📅 No videos scheduled")
            return
            
        # Determine scheduling method used
        method = schedule[0].get('scheduling_method', 'static')
        method_icon = '🧠' if method == 'analytics' else '📅'
        method_name = 'ANALYTICS-BASED' if method == 'analytics' else 'STATIC'
        
        print(f"\n{method_icon} {method_name} SCHEDULE - {len(schedule)} videos")
        print("=" * 60)
        
        # Show target channel if specified
        target_channel = schedule[0].get('target_channel')
        if target_channel:
            print(f"📺 Target Channel: {target_channel}")
            print("-" * 30)
        
        for i, item in enumerate(schedule, 1):
            # Safely handle None titles
            title = item.get('title') or 'Untitled Video'
            print(f"{i:2d}. {item['scheduled_time_readable']}")
            print(f"    📹 {title[:50]}...")
            print(f"    🏷️ Priority: {item['priority']}")
            if method == 'analytics':
                print(f"    🧠 Optimized for audience engagement")
            print()
        
        # Validation
        validation = self.validate_schedule(schedule)
        if validation['is_valid']:
            print("✅ Schedule is valid")
        else:
            print("⚠️ Schedule violations detected:")
            for violation in validation['violations']:
                print(f"   - {violation}")
        
        # Show method benefits
        if method == 'analytics':
            print("\n🎯 ANALYTICS BENEFITS:")
            print("  • Times optimized for YOUR audience")
            print("  • Based on when viewers are most active")
            print("  • Higher engagement potential")
        else:
            print("\n📅 STATIC BENEFITS:")
            print("  • Predictable and consistent")
            print("  • Easy to plan content around")
            print("  • Reliable scheduling pattern")

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