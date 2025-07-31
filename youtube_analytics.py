#!/usr/bin/env python3
"""
📊 YouTube Analytics Integration
Get real engagement data from your channels to optimize upload timing
"""

import os
import json
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

class YouTubeAnalytics:
    """Get real engagement data from YouTube channels"""
    
    def __init__(self, channel_name="default"):
        self.channel_name = channel_name
        self.analytics_service = None
        
    def authenticate_analytics(self):
        """Authenticate with YouTube Analytics API (same credentials as upload)"""
        try:
            # Use existing channel credentials
            from channel_manager import ChannelManager
            manager = ChannelManager()
            credentials_path, token_path = manager.get_channel_paths(self.channel_name)
            
            # Load existing credentials
            if os.path.exists(token_path):
                creds = Credentials.from_authorized_user_file(token_path, 
                    ['https://www.googleapis.com/auth/youtube.upload',
                     'https://www.googleapis.com/auth/yt-analytics.readonly'])
                
                self.analytics_service = build('youtubeAnalytics', 'v2', credentials=creds)
                return True
            else:
                print(f"❌ No credentials found for {self.channel_name}")
                return False
                
        except Exception as e:
            print(f"❌ Analytics authentication error: {e}")
            return False
    
    def get_channel_id(self):
        """Get channel ID for analytics queries"""
        try:
            # Use YouTube Data API to get channel ID
            youtube = build('youtube', 'v3', credentials=self.analytics_service._http.credentials)
            response = youtube.channels().list(part='id', mine=True).execute()
            
            if response['items']:
                return response['items'][0]['id']
            return None
        except Exception as e:
            print(f"❌ Error getting channel ID: {e}")
            return None
    
    def get_hourly_engagement_data(self, days_back=30):
        """Get hourly engagement patterns for the last 30 days"""
        if not self.analytics_service:
            if not self.authenticate_analytics():
                return None
        
        try:
            channel_id = self.get_channel_id()
            if not channel_id:
                return None
            
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            # Query hourly engagement data
            response = self.analytics_service.reports().query(
                ids=f'channel=={channel_id}',
                startDate=start_date.strftime('%Y-%m-%d'),
                endDate=end_date.strftime('%Y-%m-%d'),
                dimensions='hour',
                metrics='views,likes,comments,shares',
                sort='hour'
            ).execute()
            
            return self.process_hourly_data(response)
            
        except Exception as e:
            print(f"❌ Error getting analytics data: {e}")
            return None
    
    def process_hourly_data(self, analytics_response):
        """Process raw analytics data into usable format"""
        hourly_engagement = {}
        
        if 'rows' not in analytics_response:
            return hourly_engagement
        
        for row in analytics_response['rows']:
            hour = int(row[0])  # Hour (0-23)
            views = int(row[1])
            likes = int(row[2]) if row[2] else 0
            comments = int(row[3]) if row[3] else 0
            shares = int(row[4]) if row[4] else 0
            
            # Calculate engagement score
            engagement_score = self.calculate_engagement_score(views, likes, comments, shares)
            
            hourly_engagement[hour] = {
                'views': views,
                'likes': likes,
                'comments': comments,
                'shares': shares,
                'engagement_score': engagement_score
            }
        
        return hourly_engagement
    
    def calculate_engagement_score(self, views, likes, comments, shares):
        """Calculate weighted engagement score"""
        if views == 0:
            return 0
        
        # Weighted engagement formula
        engagement_rate = ((likes * 1.0) + (comments * 2.0) + (shares * 3.0)) / views
        engagement_score = views * (1 + engagement_rate)
        
        return engagement_score
    
    def get_peak_hours(self, days_back=30, top_hours=4):
        """Get the top peak engagement hours for this channel"""
        hourly_data = self.get_hourly_engagement_data(days_back)
        
        if not hourly_data:
            # Fallback to static times if no data
            return [8, 12, 18, 20]  # 8AM, 12PM, 6PM, 8PM
        
        # Sort hours by engagement score
        sorted_hours = sorted(hourly_data.items(), 
                            key=lambda x: x[1]['engagement_score'], 
                            reverse=True)
        
        # Get top peak hours
        peak_hours = [hour for hour, data in sorted_hours[:top_hours]]
        
        return sorted(peak_hours)  # Return in chronological order
    
    def get_weekly_pattern(self, days_back=30):
        """Get weekly engagement patterns (weekday vs weekend)"""
        try:
            channel_id = self.get_channel_id()
            if not channel_id:
                return None
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            # Query daily engagement data
            response = self.analytics_service.reports().query(
                ids=f'channel=={channel_id}',
                startDate=start_date.strftime('%Y-%m-%d'),
                endDate=end_date.strftime('%Y-%m-%d'),
                dimensions='day',
                metrics='views,likes,comments',
                sort='day'
            ).execute()
            
            return self.process_weekly_data(response)
            
        except Exception as e:
            print(f"❌ Error getting weekly data: {e}")
            return None
    
    def process_weekly_data(self, analytics_response):
        """Process weekly engagement patterns"""
        weekday_engagement = []
        weekend_engagement = []
        
        if 'rows' not in analytics_response:
            return {'weekdays': [8, 12, 18, 20], 'weekends': [10, 14, 19, 21]}
        
        for row in analytics_response['rows']:
            date_str = row[0]
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            views = int(row[1])
            likes = int(row[2]) if row[2] else 0
            comments = int(row[3]) if row[3] else 0
            
            engagement_score = self.calculate_engagement_score(views, likes, comments, 0)
            
            if date_obj.weekday() < 5:  # Monday = 0, Sunday = 6
                weekday_engagement.append(engagement_score)
            else:
                weekend_engagement.append(engagement_score)
        
        # Calculate averages
        avg_weekday = sum(weekday_engagement) / len(weekday_engagement) if weekday_engagement else 0
        avg_weekend = sum(weekend_engagement) / len(weekend_engagement) if weekend_engagement else 0
        
        return {
            'weekday_avg': avg_weekday,
            'weekend_avg': avg_weekend,
            'weekday_better': avg_weekday > avg_weekend
        }

def test_analytics(channel_name="default"):
    """Test analytics functionality"""
    print(f"📊 Testing Analytics for {channel_name}")
    print("=" * 40)
    
    analytics = YouTubeAnalytics(channel_name)
    
    # Test authentication
    if analytics.authenticate_analytics():
        print("✅ Analytics authentication successful")
        
        # Get peak hours
        peak_hours = analytics.get_peak_hours()
        print(f"🕐 Peak engagement hours: {peak_hours}")
        
        # Convert to readable times
        readable_times = [f"{hour:02d}:00" for hour in peak_hours]
        print(f"⏰ Peak times: {', '.join(readable_times)}")
        
        # Get weekly patterns
        weekly_data = analytics.get_weekly_pattern()
        if weekly_data:
            print(f"📅 Weekday vs Weekend: {'Weekdays better' if weekly_data['weekday_better'] else 'Weekends better'}")
        
        return True
    else:
        print("❌ Analytics authentication failed")
        return False

if __name__ == "__main__":
    # Test with default channel
    test_analytics("AnimeShorts137")
