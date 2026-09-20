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
            
            # Load existing credentials — same scope list as youtube_uploader.SCOPES
            # (the token file is shared with it). Missing 'youtube.readonly' here
            # was causing get_channel_id()'s channels().list(mine=True) call — a
            # read, not an analytics call — to fail with a 403 "insufficient
            # authentication scopes", independently of the analytics scope itself.
            if os.path.exists(token_path):
                creds = Credentials.from_authorized_user_file(token_path,
                    ['https://www.googleapis.com/auth/youtube.upload',
                     'https://www.googleapis.com/auth/youtube.readonly',
                     'https://www.googleapis.com/auth/youtube.force-ssl',
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
    
    def get_daily_engagement_data(self, days_back=30):
        """Real per-day engagement (views/likes/comments/shares) for the last
        N days. dimensions='day' IS a real, documented dimension for the
        YouTube Analytics Core report — unlike 'hour', which is NOT (there is
        no intraday/hour-of-day dimension for Core reports; querying it
        returns "Unknown identifier (hour)" straight from the API, confirmed
        by testing against a real connected channel — see get_peak_hours)."""
        if not self.analytics_service:
            if not self.authenticate_analytics():
                return None

        try:
            channel_id = self.get_channel_id()
            if not channel_id:
                return None

            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)

            return self.analytics_service.reports().query(
                ids=f'channel=={channel_id}',
                startDate=start_date.strftime('%Y-%m-%d'),
                endDate=end_date.strftime('%Y-%m-%d'),
                dimensions='day',
                metrics='views,likes,comments,shares',
                sort='day'
            ).execute()

        except Exception as e:
            print(f"❌ Error getting daily analytics data: {e}")
            return None

    def calculate_engagement_score(self, views, likes, comments, shares):
        """Calculate weighted engagement score"""
        if views == 0:
            return 0
        
        # Weighted engagement formula
        engagement_rate = ((likes * 1.0) + (comments * 2.0) + (shares * 3.0)) / views
        engagement_score = views * (1 + engagement_rate)
        
        return engagement_score
    
    def get_peak_hours(self, days_back=30, top_hours=4):
        """Hour-of-day is NOT something the YouTube Analytics API can tell us
        for Core reports — there is no 'hour'/intraday dimension (confirmed:
        querying dimensions='hour' is rejected by the API itself with
        "Unknown identifier (hour)"). Rather than keep making a doomed API
        call and silently falling back every single time, this always
        returns the same reasonable generic defaults — honest about the
        limitation instead of pretending to compute something the data
        can't support. The real per-channel signal this class CAN provide
        is get_best_weekdays() below, which uses the (working) 'day'
        dimension."""
        return [8, 12, 18, 20]  # 8AM, 12PM, 6PM, 8PM

    def get_best_weekdays(self, days_back=30, top_days=5):
        """Real weekday ranking (0=Monday..6=Sunday), best-performing first,
        from actual per-day view/like/comment/share data — genuinely uses
        this channel's own history, unlike get_peak_hours above."""
        response = self.get_daily_engagement_data(days_back)
        if not response or 'rows' not in response or not response['rows']:
            return [0, 1, 2, 3, 4]  # Mon-Fri — a generic, reasonable default

        scores_by_weekday = {}
        for row in response['rows']:
            date_obj = datetime.strptime(row[0], '%Y-%m-%d')
            views, likes, comments, shares = int(row[1]), int(row[2] or 0), int(row[3] or 0), int(row[4] or 0)
            score = self.calculate_engagement_score(views, likes, comments, shares)
            scores_by_weekday.setdefault(date_obj.weekday(), []).append(score)

        if not scores_by_weekday:
            return [0, 1, 2, 3, 4]

        averaged = {day: sum(scores) / len(scores) for day, scores in scores_by_weekday.items()}
        ranked = sorted(averaged, key=averaged.get, reverse=True)
        return ranked[:top_days]

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
        
        # Get best weekdays (real data, unlike peak_hours above)
        weekday_names = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
        best_days = analytics.get_best_weekdays()
        print(f"📅 Meilleurs jours: {', '.join(weekday_names[d] for d in best_days)}")
        
        return True
    else:
        print("❌ Analytics authentication failed")
        return False

if __name__ == "__main__":
    # Test with default channel
    test_analytics("AnimeShorts137")
