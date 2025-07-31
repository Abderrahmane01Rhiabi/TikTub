#!/usr/bin/env python3
"""
Quick test for enhanced status display with channel information
"""

import json
import os

def test_enhanced_status():
    """Test the enhanced status display"""
    print("🧪 TESTING ENHANCED STATUS DISPLAY")
    print("=" * 50)
    
    # Read the actual video database
    if not os.path.exists('database/videos_status.json'):
        print("❌ No video database found")
        return
    
    with open('database/videos_status.json', 'r') as f:
        data = json.load(f)
    
    # Group videos by status
    status_groups = {}
    for video in data['videos'].values():
        status = video['status']
        if status not in status_groups:
            status_groups[status] = []
        status_groups[status].append(video)
    
    # Show summary first
    print("📊 STATUT DES VIDÉOS")
    print("Résumé des statuts:")
    for status, videos in status_groups.items():
        print(f"  {status}: {len(videos)} vidéos")
    
    # Show detailed status with channels
    important_statuses = {
        'scheduled_on_youtube': '📅 SCHEDULED ON YOUTUBE',
        'uploaded': '✅ UPLOADED', 
        'ready_for_upload': '📦 READY FOR UPLOAD'
    }
    
    for status, title in important_statuses.items():
        if status in status_groups and status_groups[status]:
            print(f"\n{title} ({len(status_groups[status])} vidéos):")
            print("-" * 50)
            
            for video in status_groups[status]:
                # Get video title (truncated)
                video_title = video.get('original_title', 'Unknown')[:40]
                if len(video.get('original_title', '')) > 40:
                    video_title += "..."
                
                # Get channel info
                channel_info = get_channel_info(video)
                
                # Format display
                print(f"📺 {video_title}")
                print(f"   📺 Channel: {channel_info}")
                
                if video.get('youtube_url'):
                    print(f"   ▶️  YouTube: {video['youtube_url']}")
                
                if video.get('scheduled_publish_time'):
                    print(f"   ⏰ Scheduled: {video['scheduled_publish_time']}")
                
                print()

def get_channel_info(video):
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
    try:
        if os.path.exists('channels'):
            # Get actual channel info from channel_manager
            from channel_manager import ChannelManager
            manager = ChannelManager()
            channels = manager.list_channels()
            if channels:
                # Get the first active channel name
                channel_name = channels[0].get('name', 'Unknown')
                display_name = channels[0].get('display_name', channel_name)
                return f"📺 {display_name}"
    except:
        # Fallback to directory listing
        try:
            if os.path.exists('channels'):
                channels = os.listdir('channels')
                if channels:
                    return f"📺 {channels[0]}"
        except:
            pass
    
    return "📺 Unknown channel"

if __name__ == "__main__":
    test_enhanced_status()
