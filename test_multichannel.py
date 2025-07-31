#!/usr/bin/env python3
"""
🧪 Multi-Channel Test Script
Test the multi-channel YouTube support functionality
"""

import os
import sys

def test_multi_channel_support():
    """Test multi-channel support functionality"""
    print("🧪 TESTING MULTI-CHANNEL SUPPORT")
    print("=" * 40)
    
    # Test imports
    try:
        from channel_manager import ChannelManager
        print("✅ ChannelManager import successful")
    except ImportError as e:
        print(f"❌ ChannelManager import failed: {e}")
        return False
        
    try:
        from youtube_uploader import select_channel, get_credentials_path, get_token_path
        print("✅ YouTube uploader multi-channel functions imported")
    except ImportError as e:
        print(f"❌ YouTube uploader import failed: {e}")
        return False
    
    # Test ChannelManager
    try:
        manager = ChannelManager()
        print("✅ ChannelManager instantiated")
        
        # Test channel listing
        channels = manager.list_channels()
        print(f"📺 Found {len(channels)} channels:")
        for channel in channels:
            status = "✅ Ready" if channel["ready"] else "❌ Needs setup"
            print(f"  - {channel['display_name']} ({channel['name']}) - {status}")
            
    except Exception as e:
        print(f"❌ ChannelManager test failed: {e}")
        return False
        
    # Test path functions
    try:
        default_creds = get_credentials_path("default")
        default_token = get_token_path("default")
        print(f"✅ Path functions work:")
        print(f"  - Credentials: {default_creds}")
        print(f"  - Token: {default_token}")
    except Exception as e:
        print(f"❌ Path functions failed: {e}")
        return False
        
    print("\n🎉 All tests passed! Multi-channel support is working.")
    return True

def show_usage_examples():
    """Show usage examples"""
    print("\n📖 USAGE EXAMPLES:")
    print("=" * 40)
    print("1. Setup channels:")
    print("   python setup_channels.py")
    print("")
    print("2. Upload with channel selection:")
    print("   python youtube_uploader.py")
    print("")
    print("3. Batch processing with channels:")
    print("   python batch_processor.py")
    print("")
    print("4. Test multi-channel support:")
    print("   python test_multichannel.py")

def main():
    print("🎯 TikTub Multi-Channel Support Test")
    print("=" * 50)
    
    # Run tests
    success = test_multi_channel_support()
    
    if success:
        show_usage_examples()
        
        print("\n🚀 NEXT STEPS:")
        print("1. Run: python setup_channels.py")
        print("2. Add your additional YouTube channels")
        print("3. Download OAuth credentials for each channel")
        print("4. Start uploading with multi-channel support!")
    else:
        print("\n❌ Tests failed. Check the error messages above.")

if __name__ == "__main__":
    main()
