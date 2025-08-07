#!/usr/bin/env python3
"""
Direct test for lungTe888 portrait mode without AI channel detection
"""
import sys
import os
import logging

# Add current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from test3_script import process_lungte888_portrait_mode, download_tiktok_video, analyze_video_with_ai, CONFIG
import re
from moviepy.editor import VideoFileClip

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Test lungTe888 portrait mode processing directly"""
    
    print("🧪 Direct lungTe888 Portrait Mode Test")
    print("=" * 50)
    
    # Use the same URL
    url = "https://www.tiktok.com/@nawlezy/video/7535490833085173014"
    
    print(f"📥 Downloading: {url}")
    video_path = download_tiktok_video(url, "temp/")
    
    if not video_path or not os.path.exists(video_path):
        print("❌ Download failed")
        return
    
    print(f"✅ Downloaded: {video_path}")
    
    # Generate AI content
    print("🤖 Generating AI content...")
    video_data = analyze_video_with_ai(video_path)
    
    if not video_data:
        print("❌ AI analysis failed")
        return
    
    title = video_data.get('title', 'Test Video')
    print(f"📝 Title: {title}")
    
    # Load video with MoviePy
    print("🎬 Loading video for portrait mode processing...")
    video = VideoFileClip(video_path)
    
    # Force lungTe888 portrait mode processing
    print("🎯 FORCING lungTe888 Portrait Mode Processing...")
    
    target_w, target_h = 1080, 1920  # Standard YouTube Shorts dimensions
    
    result_path = process_lungte888_portrait_mode(video, title, target_w, target_h)
    
    if result_path and os.path.exists(result_path):
        size_mb = os.path.getsize(result_path) / (1024 * 1024)
        print(f"✅ SUCCESS! lungTe888 portrait mode video created!")
        print(f"📁 Output: {result_path}")
        print(f"📏 File size: {size_mb:.1f}MB")
    else:
        print("❌ Portrait mode processing failed")
    
    # Cleanup
    video.close()

if __name__ == "__main__":
    main()
