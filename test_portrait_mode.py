#!/usr/bin/env python3
"""
Test Script: Portrait Mode Processing for lungTe888 Channel
This script tests portrait mode with blurred background and vertical video with fill
instead of using traditional background overlay.
"""

import os
import re
import random
import logging
import cv2
import numpy as np
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
CONFIG = {
    'backgrounds_folder': 'backgrounds/',
    'temp_folder': 'temp/',
    'output_folder': 'processed_videos/',
    'target_resolution': (1080, 1920),  # 9:16 aspect ratio
    'max_duration': 60,
}

def setup_directories():
    """Create necessary directories"""
    for folder in [CONFIG['temp_folder'], CONFIG['output_folder']]:
        Path(folder).mkdir(parents=True, exist_ok=True)

def fix_pil_compatibility():
    """Fix PIL compatibility issues"""
    try:
        from PIL import Image
        if not hasattr(Image, 'Resampling'):
            Image.Resampling = Image
        if hasattr(Image, 'ANTIALIAS') and not hasattr(Image, 'LANCZOS'):
            Image.LANCZOS = Image.ANTIALIAS
    except:
        pass

def download_tiktok_video(url: str):
    """Download TikTok video using yt-dlp"""
    try:
        import subprocess
        
        # Clean filename
        safe_name = re.sub(r'[^\w\s-]', '', url.split('/')[-1])[:30]
        output_path = f"{CONFIG['temp_folder']}/{safe_name}_%(title)s.%(ext)s"
        
        cmd = [
            'yt-dlp',
            '--format', 'best[height<=1920]/best',
            '--output', output_path,
            '--no-warnings',
            url
        ]
        
        print("🔄 Downloading video...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            # Find downloaded video file
            temp_files = list(Path(CONFIG['temp_folder']).glob('*.mp4'))
            if temp_files:
                video_path = str(temp_files[-1])  # Get the latest
                title = video_path.split('/')[-1].replace('.mp4', '')
                print(f"✅ Downloaded: {title}")
                return video_path, title
        
        print(f"❌ Download failed: {result.stderr}")
        return None, None
        
    except Exception as e:
        print(f"❌ Download error: {e}")
        return None, None

def create_blurred_background(video_clip):
    """Create a blurred background from the video itself"""
    try:
        from moviepy.editor import VideoFileClip
        target_w, target_h = CONFIG['target_resolution']
        
        # Create stretched version for background
        background = video_clip.resize((target_w, target_h))
        
        # Try to apply blur effect
        try:
            import moviepy.video.fx.all as vfx
            background_blurred = vfx.blur(background, 25)  # Heavy blur
            logger.info("✨ Created blurred background from video")
            return background_blurred
        except:
            try:
                from moviepy.video.fx import blur
                background_blurred = blur.blur(background, 25)
                logger.info("✨ Created blurred background from video")  
                return background_blurred
            except:
                logger.warning("⚠️ Blur effect not available, using stretched background")
                return background
        
    except Exception as e:
        logger.error(f"❌ Blur background creation failed: {e}")
        # Fallback to stretched version
        return video_clip.resize(CONFIG['target_resolution'])

def process_portrait_mode_with_blur(video_path: str, title: str):
    """Process video with portrait mode and blurred background"""
    try:
        fix_pil_compatibility()
        from moviepy.editor import VideoFileClip, CompositeVideoClip
        
        logger.info("🎬 Processing with Portrait Mode + Blurred Background")
        
        # Load video
        video = VideoFileClip(video_path)
        logger.info(f"📊 Original: {video.size[0]}x{video.size[1]}, Duration: {video.duration:.1f}s")
        
        # Trim if too long
        if video.duration > CONFIG['max_duration']:
            logger.info(f"✂️ Trimming to {CONFIG['max_duration']}s")
            video = video.subclip(0, CONFIG['max_duration'])
        
        target_w, target_h = CONFIG['target_resolution']
        video_w, video_h = video.size
        
        # Create blurred background first
        blurred_background = create_blurred_background(video)
        
        # Calculate scaling for the main video to fit nicely in portrait mode
        # We want to maintain aspect ratio but scale to fit nicely
        scale = min(target_w * 0.9 / video_w, target_h * 0.8 / video_h)  # Leave some margin
        new_w = int(video_w * scale)
        new_h = int(video_h * scale)
        
        # Resize main video
        video_resized = video.resize((new_w, new_h))
        logger.info(f"📏 Main video resized to: {new_w}x{new_h}")
        
        # Position video in center
        video_centered = video_resized.set_position('center')
        
        # Compose final video with blurred background
        final_video = CompositeVideoClip([blurred_background, video_centered])
        
        # Export
        safe_title = re.sub(r'[^\w\s-]', '', title)[:40]
        output_path = f"{CONFIG['output_folder']}/{safe_title}_portrait_blur.mp4"
        
        logger.info("💾 Exporting portrait mode video...")
        final_video.write_videofile(
            output_path,
            fps=30,
            codec='libx264',
            audio_codec='aac',
            temp_audiofile=f"{CONFIG['temp_folder']}/temp-audio.m4a",
            remove_temp=True,
            verbose=False,
            logger=None
        )
        
        # Cleanup
        video.close()
        blurred_background.close()
        final_video.close()
        
        # File size
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"✅ Portrait Mode processed! Size: {size_mb:.1f}MB")
        logger.info(f"📁 Saved to: {output_path}")
        
        return output_path
        
    except Exception as e:
        logger.error(f"❌ Portrait mode processing failed: {e}")
        return None

def process_vertical_fill_mode(video_path: str, title: str):
    """Process video with vertical fill mode (stretch/crop to fill)"""
    try:
        fix_pil_compatibility()
        from moviepy.editor import VideoFileClip
        
        logger.info("🎬 Processing with Vertical Fill Mode")
        
        # Load video
        video = VideoFileClip(video_path)
        logger.info(f"📊 Original: {video.size[0]}x{video.size[1]}, Duration: {video.duration:.1f}s")
        
        # Trim if too long
        if video.duration > CONFIG['max_duration']:
            logger.info(f"✂️ Trimming to {CONFIG['max_duration']}s")
            video = video.subclip(0, CONFIG['max_duration'])
        
        target_w, target_h = CONFIG['target_resolution']
        video_w, video_h = video.size
        
        # Calculate scale to fill the entire vertical space
        # This will crop sides if necessary to maintain vertical fill
        scale_w = target_w / video_w
        scale_h = target_h / video_h
        scale = max(scale_w, scale_h)  # Use the larger scale to fill
        
        new_w = int(video_w * scale)
        new_h = int(video_h * scale)
        
        logger.info(f"📏 Scaling to: {new_w}x{new_h} (scale: {scale:.2f})")
        
        # Resize video
        video_resized = video.resize((new_w, new_h))
        
        # If the resized video is larger than target, crop it
        if new_w > target_w or new_h > target_h:
            # Calculate crop coordinates to center the video
            crop_x = max(0, (new_w - target_w) // 2)
            crop_y = max(0, (new_h - target_h) // 2)
            
            video_final = video_resized.crop(
                x1=crop_x,
                y1=crop_y, 
                x2=crop_x + min(target_w, new_w),
                y2=crop_y + min(target_h, new_h)
            )
            logger.info(f"✂️ Cropped to center: {crop_x},{crop_y}")
        else:
            video_final = video_resized
        
        # Export
        safe_title = re.sub(r'[^\w\s-]', '', title)[:40]
        output_path = f"{CONFIG['output_folder']}/{safe_title}_vertical_fill.mp4"
        
        logger.info("💾 Exporting vertical fill video...")
        video_final.write_videofile(
            output_path,
            fps=30,
            codec='libx264',
            audio_codec='aac',
            temp_audiofile=f"{CONFIG['temp_folder']}/temp-audio.m4a",
            remove_temp=True,
            verbose=False,
            logger=None
        )
        
        # Cleanup
        video.close()
        video_final.close()
        
        # File size
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"✅ Vertical fill processed! Size: {size_mb:.1f}MB")
        logger.info(f"📁 Saved to: {output_path}")
        
        return output_path
        
    except Exception as e:
        logger.error(f"❌ Vertical fill processing failed: {e}")
        return None

def interactive_processing_mode():
    """Let user choose processing mode"""
    print("\n🎨 lungTe888 Portrait Processing Options:")
    print("1. 🌟 Portrait Mode with Blurred Background (Recommended)")
    print("2. 📱 Vertical Video with Fill (Stretch/Crop to fill)")
    print("3. 🔄 Process with both modes for comparison")
    
    choice = input("Choose processing mode (1-3): ").strip()
    
    mode_map = {
        '1': 'blur',
        '2': 'fill', 
        '3': 'both'
    }
    
    return mode_map.get(choice, 'blur')

def main():
    """Main processing function for lungTe888 portrait mode testing"""
    print("🚀 lungTe888 Portrait Mode Processor - Test Script")
    print("=" * 60)
    print("This script tests portrait modes instead of traditional background overlay")
    print("=" * 60)
    
    # Setup
    setup_directories()
    
    # Get URL from user
    url = input("📝 Enter your TikTok video URL: ").strip()
    
    if not url:
        print("❌ No URL provided")
        return
    
    # Choose processing mode
    mode = interactive_processing_mode()
    
    print(f"\n🎯 Processing: {url}")
    print(f"🎨 Mode: {mode}")
    print("-" * 60)
    
    # Download
    video_path, title = download_tiktok_video(url)
    
    if not video_path:
        print("❌ Download failed")
        return
    
    print(f"✅ Download successful!")
    
    # Process based on selected mode
    results = []
    
    if mode in ['blur', 'both']:
        print("\n🌟 Processing with Portrait Mode + Blurred Background...")
        output1 = process_portrait_mode_with_blur(video_path, title)
        if output1:
            results.append(('Portrait Mode with Blur', output1))
    
    if mode in ['fill', 'both']:
        print("\n📱 Processing with Vertical Fill Mode...")
        output2 = process_vertical_fill_mode(video_path, title)
        if output2:
            results.append(('Vertical Fill', output2))
    
    # Show results
    if results:
        print(f"\n🎉 SUCCESS! Processed {len(results)} version(s):")
        print("=" * 60)
        
        for method, path in results:
            size_mb = os.path.getsize(path) / (1024 * 1024)
            print(f"✅ {method}:")
            print(f"   📁 {path}")
            print(f"   📊 Size: {size_mb:.1f}MB")
            print()
        
        print("💡 Compare the results and choose your preferred method!")
        print("🔧 Once you're happy, we can integrate this into the main project.")
        
    else:
        print("❌ Processing failed for all methods")
    
    # Cleanup temp files
    for f in Path(CONFIG['temp_folder']).glob('*'):
        try:
            f.unlink()
        except:
            pass

if __name__ == "__main__":
    main()
