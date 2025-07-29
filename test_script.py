#!/usr/bin/env python3
"""
Working TikTok Video Processor - Fixed Compatibility Issues
This version handles PIL.Image.ANTIALIAS and other compatibility problems
"""

import os
import re
import random
from pathlib import Path
import logging

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
        Path(folder).mkdir(exist_ok=True)

def download_tiktok_video(url: str):
    """Download TikTok video using yt-dlp"""
    try:
        import yt_dlp
        
        logger.info(f"📥 Downloading: {url}")
        
        ydl_opts = {
            'outtmpl': f"{CONFIG['temp_folder']}/%(title)s.%(ext)s",
            'format': 'best[height<=1920]',
            'writeinfojson': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_title = info.get('title', 'TikTok_Video')
            
            # Clean title for filename
            safe_title = re.sub(r'[^\w\s-]', '', video_title)[:30]
            
            logger.info(f"📹 Video title: {video_title}")
            logger.info(f"⏱️ Duration: {info.get('duration', 'Unknown')}s")
            
            # Actually download
            ydl.download([url])
            
            # Find downloaded file
            temp_files = list(Path(CONFIG['temp_folder']).glob('*.mp4'))
            if temp_files:
                video_path = str(temp_files[-1])
                logger.info(f"✅ Downloaded to: {video_path}")
                return video_path, safe_title
            else:
                logger.error("❌ No video file found after download")
                return None, None
                
    except Exception as e:
        logger.error(f"❌ Download failed: {e}")
        return None, None

def get_background_image():
    """Get a random background image"""
    try:
        bg_folder = Path(CONFIG['backgrounds_folder'])
        backgrounds = list(bg_folder.glob('*.jpg')) + list(bg_folder.glob('*.png')) + list(bg_folder.glob('*.jpeg'))
        
        if backgrounds:
            selected = random.choice(backgrounds)
            logger.info(f"🎨 Selected background: {selected.name}")
            return str(selected)
        else:
            logger.warning("⚠️ No background images found")
            return None
    except Exception as e:
        logger.error(f"❌ Background selection failed: {e}")
        return None

def fix_pil_compatibility():
    """Fix PIL.Image.ANTIALIAS compatibility issue"""
    try:
        from PIL import Image
        # Fix for newer Pillow versions
        if not hasattr(Image, 'ANTIALIAS'):
            Image.ANTIALIAS = Image.LANCZOS
            logger.info("🔧 Fixed PIL.Image.ANTIALIAS compatibility")
        return True
    except Exception as e:
        logger.error(f"❌ PIL compatibility fix failed: {e}")
        return False

def process_video_moviepy(video_path: str, title: str):
    """Process video using MoviePy with compatibility fixes"""
    try:
        # Fix PIL compatibility first
        fix_pil_compatibility()
        
        from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
        
        logger.info(f"🎬 Processing with MoviePy: {Path(video_path).name}")
        
        # Load video
        video = VideoFileClip(video_path)
        logger.info(f"📊 Original: {video.size[0]}x{video.size[1]}, Duration: {video.duration:.1f}s")
        
        # Trim if too long
        if video.duration > CONFIG['max_duration']:
            logger.info(f"✂️ Trimming to {CONFIG['max_duration']}s")
            video = video.subclip(0, CONFIG['max_duration'])
        
        # Calculate new dimensions
        video_w, video_h = video.size
        target_w, target_h = CONFIG['target_resolution']
        
        # Scale to fit within target while maintaining aspect ratio
        scale = min(target_w / video_w, target_h / video_h)
        new_w = int(video_w * scale)
        new_h = int(video_h * scale)
        
        video_resized = video.resize((new_w, new_h))
        logger.info(f"📏 Resized to: {new_w}x{new_h}")
        
        # Add background if needed
        if new_w < target_w or new_h < target_h:
            bg_path = get_background_image()
            
            if bg_path:
                try:
                    background = ImageClip(bg_path, duration=video.duration)
                    background = background.resize(CONFIG['target_resolution'])
                    
                    video_centered = video_resized.set_position('center')
                    final_video = CompositeVideoClip([background, video_centered])
                    logger.info("✨ Added background image")
                except Exception as bg_error:
                    logger.warning(f"⚠️ Background failed, using black: {bg_error}")
                    # Fallback to black background
                    final_video = video_resized.on_color(
                        size=CONFIG['target_resolution'],
                        color=(0, 0, 0),
                        pos='center'
                    )
                    logger.info("⬛ Added black background (fallback)")
            else:
                # Black background
                final_video = video_resized.on_color(
                    size=CONFIG['target_resolution'],
                    color=(0, 0, 0),
                    pos='center'
                )
                logger.info("⬛ Added black background")
        else:
            final_video = video_resized
            logger.info("📱 Video fits perfectly")
        
        # Output path
        output_path = f"{CONFIG['output_folder']}/{title}_processed.mp4"
        
        # Export with error handling
        logger.info("💾 Exporting video...")
        try:
            final_video.write_videofile(
                output_path,
                fps=30,
                codec='libx264',
                audio_codec='aac',
                verbose=False,
                logger=None,
                temp_audiofile=f"{CONFIG['temp_folder']}/temp-audio.m4a",
                remove_temp=True
            )
        except Exception as export_error:
            logger.warning(f"⚠️ Export with audio failed: {export_error}")
            logger.info("🔄 Trying export without audio...")
            final_video_no_audio = final_video.without_audio()
            final_video_no_audio.write_videofile(
                output_path,
                fps=30,
                codec='libx264',
                verbose=False,
                logger=None
            )
            final_video_no_audio.close()
        
        # Cleanup
        video.close()
        final_video.close()
        
        # File size
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"✅ Processed! Size: {size_mb:.1f}MB")
        logger.info(f"📁 Saved to: {output_path}")
        
        return output_path
        
    except Exception as e:
        logger.error(f"❌ MoviePy processing failed: {e}")
        return None

def process_video_ffmpeg_fallback(video_path: str, title: str):
    """Fallback processing using ffmpeg directly"""
    try:
        import subprocess
        
        logger.info("🔄 Trying ffmpeg fallback processing...")
        
        output_path = f"{CONFIG['output_folder']}/{title}_processed.mp4"
        
        # Basic ffmpeg command to resize and pad video
        cmd = [
            'ffmpeg', '-i', video_path,
            '-vf', f'scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black',
            '-c:v', 'libx264', '-c:a', 'aac',
            '-t', str(CONFIG['max_duration']),  # Limit duration
            '-y',  # Overwrite output file
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            logger.info(f"✅ FFmpeg processing successful! Size: {size_mb:.1f}MB")
            logger.info(f"📁 Saved to: {output_path}")
            return output_path
        else:
            logger.error(f"❌ FFmpeg failed: {result.stderr}")
            return None
            
    except Exception as e:
        logger.error(f"❌ FFmpeg fallback failed: {e}")
        return None

def main():
    """Main processing function"""
    print("🚀 TikTok Video Processor (Compatibility Fixed)")
    print("=" * 60)
    
    # Setup
    setup_directories()
    
    # Get URL from user
    url = input("📝 Enter your TikTok video URL: ").strip()
    
    if not url:
        print("❌ No URL provided")
        return
    
    print(f"\n🎯 Processing: {url}")
    print("-" * 60)
    
    # Download
    video_path, title = download_tiktok_video(url)
    
    if not video_path:
        print("❌ Download failed")
        return
    
    print(f"✅ Download successful!")
    
    # Try MoviePy first, then ffmpeg fallback
    output_path = process_video_moviepy(video_path, title)
    
    if not output_path:
        logger.info("🔄 MoviePy failed, trying ffmpeg fallback...")
        output_path = process_video_ffmpeg_fallback(video_path, title)
    
    if output_path:
        print(f"\n🎉 SUCCESS!")
        print(f"📹 Final video: {output_path}")
        print(f"📊 Ready for YouTube Shorts (1080x1920)")
        
        # Show video info
        if os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"📁 File size: {size_mb:.1f}MB")
    else:
        print("❌ All processing methods failed")
    
    # Cleanup
    print("\n🧹 Cleaning up temporary files...")
    temp_files = list(Path(CONFIG['temp_folder']).glob('*.mp4')) + list(Path(CONFIG['temp_folder']).glob('*.json'))
    for temp_file in temp_files:
        if temp_file.is_file():
            temp_file.unlink()
    
    print("✅ Process complete!")
    print(f"📂 Check your processed video in: {CONFIG['output_folder']}")

if __name__ == "__main__":
    main()