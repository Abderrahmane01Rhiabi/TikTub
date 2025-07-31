#!/usr/bin/env python3
"""
🧪 Test Analytics Integration
Test the new analytics-based scheduling functionality
"""

import os
import sys
from datetime import datetime

# Test analytics module
def test_analytics_module():
    """Test the analytics module"""
    print("🧪 TESTING ANALYTICS MODULE")
    print("=" * 40)
    
    try:
        from youtube_analytics import YouTubeAnalytics
        print("✅ YouTube Analytics module imported successfully")
        
        # Test with a sample channel
        print("\n📊 Testing with sample channel...")
        analytics = YouTubeAnalytics("test_channel")
        
        # Test authentication setup
        print("✅ Analytics class created successfully")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"⚠️  Error: {e}")
        return False
    
    return True

def test_smart_scheduler():
    """Test the smart scheduler"""
    print("\n🧠 TESTING SMART SCHEDULER")
    print("=" * 40)
    
    try:
        from smart_scheduler import SmartScheduler
        print("✅ Smart Scheduler imported successfully")
        
        scheduler = SmartScheduler()
        print("✅ Smart Scheduler created successfully")
        
        # Test with sample data
        sample_videos = [
            {
                'video_id': 'test_1',
                'title': 'Test Video 1',
                'target_channel': 'AnimeShorts137',
                'priority': 'high'
            },
            {
                'video_id': 'test_2',
                'title': 'Test Video 2', 
                'target_channel': 'lungte8888',
                'priority': 'normal'
            }
        ]
        
        print(f"\n📅 Testing schedule creation with {len(sample_videos)} videos...")
        schedule = scheduler.create_analytics_based_schedule(sample_videos, days_ahead=2)
        
        print(f"✅ Schedule created with {len(schedule.get('schedule', []))} entries")
        
        # Show sample entries
        if schedule.get('schedule'):
            print("\n📋 Sample schedule entries:")
            for entry in schedule['schedule'][:3]:  # Show first 3
                print(f"   📺 {entry['title']} → {entry['channel']} → {entry['scheduled_time_readable']}")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"⚠️  Error: {e}")
        return False
    
    return True

def test_batch_processor_integration():
    """Test batch processor integration"""
    print("\n🔄 TESTING BATCH PROCESSOR INTEGRATION")
    print("=" * 45)
    
    try:
        from batch_processor import BatchProcessor, ANALYTICS_SUPPORT
        print("✅ Batch Processor imported successfully")
        
        if ANALYTICS_SUPPORT:
            print("✅ Analytics support detected in batch processor")
        else:
            print("⚠️  Analytics support not detected")
            return False
        
        processor = BatchProcessor()
        print("✅ Batch Processor created successfully")
        
        # Test analytics scheduler initialization
        if hasattr(processor, 'smart_scheduler'):
            print("✅ Smart scheduler initialized in batch processor")
        else:
            print("⚠️  Smart scheduler not initialized")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"⚠️  Error: {e}")
        return False
    
    return True

def test_channel_integration():
    """Test multi-channel integration"""
    print("\n📺 TESTING MULTI-CHANNEL INTEGRATION")
    print("=" * 42)
    
    try:
        from channel_manager import ChannelManager
        print("✅ Channel Manager imported successfully")
        
        manager = ChannelManager()
        channels = manager.list_channels()
        
        print(f"📋 Found {len(channels)} configured channels:")
        for channel in channels:
            print(f"   📺 {channel}")
        
        if channels:
            print("✅ Multi-channel system operational")
        else:
            print("⚠️  No channels configured (run setup_channels.py)")
        
    except ImportError as e:
        print(f"❌ Multi-channel not available: {e}")
        return False
    except Exception as e:
        print(f"⚠️  Error: {e}")
        return False
    
    return True

def main():
    """Run all tests"""
    print("🚀 ANALYTICS INTEGRATION TEST SUITE")
    print("=" * 50)
    print(f"📅 Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    tests = [
        ("Analytics Module", test_analytics_module),
        ("Smart Scheduler", test_smart_scheduler),
        ("Batch Processor Integration", test_batch_processor_integration),
        ("Multi-Channel Integration", test_channel_integration)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results[test_name] = False
        print()
    
    # Summary
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 30)
    passed = 0
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n🎯 Overall: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("\n🎉 ALL SYSTEMS OPERATIONAL!")
        print("Your analytics-based scheduling is ready to use!")
    elif passed >= len(tests) - 1:
        print("\n⚠️  System mostly operational with minor issues")
    else:
        print("\n❌ Multiple issues detected - check configuration")
    
    print("\n💡 NEXT STEPS:")
    if passed == len(tests):
        print("1. Run: python batch_processor.py")
        print("2. Choose option 3 to create analytics-based schedule")
        print("3. Select analytics scheduling when prompted")
    else:
        print("1. Fix any import/configuration issues above")
        print("2. Ensure all channels are properly configured")
        print("3. Re-run this test")

if __name__ == "__main__":
    main()
