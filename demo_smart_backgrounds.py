#!/usr/bin/env python3
"""
Smart Background System Demo
Shows how channel-matched backgrounds work
"""

from test3_script import get_smart_background_for_channel, detect_target_channel_ai
import json

def demo_smart_backgrounds():
    print("🎨 SMART BACKGROUND SYSTEM DEMO")
    print("=" * 50)
    
    # Demo cases
    test_cases = [
        {
            'title': 'Amazing anime compilation AMV',
            'description': 'Cool anime edit #anime #manga #otaku',
            'tags': ['anime', 'manga'],
            'platform': 'tiktok'
        },
        {
            'title': 'Daily motivation for success',
            'description': 'Get motivated #motivation #success',
            'tags': ['motivation', 'success'],
            'platform': 'instagram'
        },
        {
            'title': 'Funny meme compilation',
            'description': 'LOL this is hilarious #meme #funny',
            'tags': ['meme', 'funny'],
            'platform': 'tiktok'
        }
    ]
    
    print("🧪 Testing AI Channel Detection + Smart Backgrounds:")
    print()
    
    for i, case in enumerate(test_cases, 1):
        print(f"Test {i}: {case['title']}")
        
        # Detect channel
        channel = detect_target_channel_ai(case)
        print(f"  🎯 Detected Channel: {channel}")
        
        # Get smart background
        background = get_smart_background_for_channel(channel)
        bg_name = background.split('/')[-1] if background else "None"
        print(f"  🎨 Smart Background: {bg_name}")
        print()
    
    print("🎯 CHANNEL → BACKGROUND MAPPING:")
    print("=" * 40)
    
    channel_mapping = {
        'AnimeShorts137': 'animeshorts.png',
        'LungTeMotivates': 'LungTeMotivates.png',
        'meme0culture': 'memeculture.jpg or memeculture2.png',
        'ZitBliss': 'zitbliss.png',
        'LungTe8888': 'lungTe888.png or default.jpg'
    }
    
    for channel, bg in channel_mapping.items():
        print(f"📺 {channel:<15} → 🎨 {bg}")
    
    print("\n✅ Smart Background System Ready!")
    print("\n🚀 Usage:")
    print("python3 multi_platform_processor.py urls_input/mixed_batch.txt smart")

if __name__ == "__main__":
    demo_smart_backgrounds()
