#!/usr/bin/env python3
"""
🔄 Multi-Channel Upload Helper
Reset video status to allow uploading to multiple channels
"""

import json
import os
from pathlib import Path

def load_video_database():
    """Load video database"""
    db_path = "database/videos_status.json"
    if os.path.exists(db_path):
        with open(db_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"videos": {}}

def save_video_database(database):
    """Save video database"""
    os.makedirs("database", exist_ok=True)
    with open("database/videos_status.json", 'w', encoding='utf-8') as f:
        json.dump(database, f, indent=2, ensure_ascii=False)

def list_uploaded_videos():
    """List videos that have been uploaded"""
    database = load_video_database()
    uploaded_videos = []
    
    for video_id, video_data in database.get("videos", {}).items():
        status = video_data.get("status", "")
        if status in ["uploaded", "scheduled_on_youtube"]:
            title = video_data.get("ai_data", {}).get("optimized_title") or video_data.get("original_title", "Unknown")
            video_path = video_data.get("video_path", "")
            uploaded_videos.append({
                "id": video_id,
                "title": title,
                "path": video_path,
                "status": status
            })
    
    return uploaded_videos

def reset_video_for_multi_channel(video_id):
    """Reset a video status to allow multi-channel upload"""
    database = load_video_database()
    
    if video_id in database.get("videos", {}):
        # Change status back to ready_for_upload
        database["videos"][video_id]["status"] = "ready_for_upload"
        database["videos"][video_id]["updated_at"] = "2025-07-30T" + "12:00:00.000000"
        
        # Add multi-channel flag
        database["videos"][video_id]["multi_channel_upload"] = True
        
        save_video_database(database)
        return True
    return False

def main():
    print("🔄 MULTI-CHANNEL UPLOAD HELPER")
    print("=" * 40)
    
    uploaded_videos = list_uploaded_videos()
    
    if not uploaded_videos:
        print("❌ No uploaded videos found")
        print("💡 Process some videos first with batch_processor.py")
        return
    
    print(f"📺 Found {len(uploaded_videos)} uploaded videos:")
    print()
    
    for i, video in enumerate(uploaded_videos, 1):
        print(f"{i}. {video['title'][:50]}{'...' if len(video['title']) > 50 else ''}")
        print(f"   Status: {video['status']}")
        print(f"   Path: {Path(video['path']).name}")
        print()
    
    try:
        choice = input("Select video to reset for multi-channel upload (number): ").strip()
        if not choice.isdigit():
            print("❌ Invalid selection")
            return
            
        idx = int(choice) - 1
        if not (0 <= idx < len(uploaded_videos)):
            print("❌ Invalid selection")
            return
            
        selected_video = uploaded_videos[idx]
        
        print(f"\n🔄 Resetting: {selected_video['title']}")
        
        if reset_video_for_multi_channel(selected_video['id']):
            print("✅ Video reset successfully!")
            print("🎬 You can now upload it to other channels:")
            print("   python3 youtube_uploader.py")
        else:
            print("❌ Failed to reset video")
            
    except KeyboardInterrupt:
        print("\n👋 Cancelled")

if __name__ == "__main__":
    main()
