#!/usr/bin/env python3
"""
Fix for _execute_days_schedule function to actually upload to YouTube
"""

def _execute_days_schedule(self, channel_name: str, videos: List[str], selected_days: List[int], upload_time: str, schedule_dates: List[str]):
    """Execute the days-based upload schedule by actually uploading to YouTube"""
    from datetime import datetime, timedelta
    
    print(f"\n🚀 Starting YouTube Upload & Schedule for {channel_name}!")
    print(f"📺 Uploading {len(videos)} videos with scheduled publish times")
    print("=" * 60)
    
    # Calculate next upload dates
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    selected_day_names = [day_names[d-1] for d in selected_days]
    
    # Show final schedule confirmation
    print(f"\n📋 Upload Schedule:")
    print(f"   📅 Days: {', '.join(selected_day_names)}")
    print(f"   ⏰ Time: {upload_time}")
    print(f"   📊 Total uploads: {len(schedule_dates)}")
    
    # Track upload results
    successful_uploads = 0
    failed_uploads = 0
    
    # Upload each video with its scheduled time
    for i, (video_path, schedule_date) in enumerate(zip(videos, schedule_dates), 1):
        video_name = os.path.basename(video_path)[:40]
        print(f"\n📤 Uploading {i}/{len(videos)}: {video_name}")
        print(f"📅 Scheduled for: {schedule_date}")
        
        try:
            # Load metadata for this video
            metadata_path = video_path.replace('.mp4', '_metadata.json')
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            # Upload with scheduled time
            upload_success = self.upload_video_with_schedule(
                video_path=video_path,
                metadata=metadata,
                scheduled_time=schedule_date,
                channel_name=channel_name
            )
            
            if upload_success:
                successful_uploads += 1
                print(f"✅ Upload {i} successful!")
                
                # Clean up local files after successful upload
                try:
                    os.remove(video_path)
                    if os.path.exists(metadata_path):
                        os.remove(metadata_path)
                    print(f"🗑️ Cleaned up local files")
                except:
                    pass
            else:
                failed_uploads += 1
                print(f"❌ Upload {i} failed!")
            
            # Small delay between uploads to avoid rate limits
            if i < len(videos):
                print("⏳ Waiting 3 seconds before next upload...")
                time.sleep(3)
                
        except Exception as e:
            failed_uploads += 1
            print(f"❌ Upload error for video {i}: {e}")
            continue
    
    # Show final results
    print(f"\n🎉 Upload Complete!")
    print("=" * 50)
    print(f"✅ Successful uploads: {successful_uploads}")
    print(f"❌ Failed uploads: {failed_uploads}")
    print(f"📊 Success rate: {(successful_uploads/len(videos)*100):.1f}%")
    
    if successful_uploads > 0:
        print(f"\n🎯 {successful_uploads} videos scheduled on YouTube!")
        print(f"📅 Publishing on: {', '.join(selected_day_names)} at {upload_time}")
        print(f"📺 Check YouTube Studio to see your scheduled videos")
        print(f"⏰ Videos will automatically publish at scheduled times")
    
    if failed_uploads > 0:
        print(f"\n⚠️ {failed_uploads} uploads failed - videos remain in channels_processed/")
        print(f"💡 You can retry failed uploads later")
    
    # Calculate schedule analytics
    videos_per_week = len(selected_days)
    total_weeks = (successful_uploads + videos_per_week - 1) // videos_per_week
    
    print(f"\n📈 Schedule Analytics:")
    print(f"   🔄 Frequency: {videos_per_week} videos per week")
    print(f"   📅 Duration: ~{total_weeks} weeks")
    print(f"   ⚡ Pattern: Every {', '.join(selected_day_names)} at {upload_time}")
    print(f"   🎯 Optimized for {channel_name} audience engagement")
