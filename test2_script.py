#!/usr/bin/env python3
"""
Complete Enhanced TikTok Video Processor with Advanced Backgrounds
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
    'target_resolution': (1080, 1920),
    'max_duration': 60,
}

# Enhanced background configuration
BACKGROUND_CONFIG = {
    'backgrounds_folder': 'backgrounds/',
    'background_modes': {
        'random': 'Select random background for each video',
        'blur': 'Use blurred version of the video itself as background', 
        'solid': 'Use solid color background',
        'gradient': 'Use gradient background',
        'specific': 'Use specific background image'
    },
    'solid_colors': [
        (0, 0, 0),      # Black
        (32, 32, 64),   # Dark blue
        (64, 32, 64),   # Dark purple
        (32, 64, 32),   # Dark green
    ],
    'gradients': [
        [(0,0,0), (32,32,64)],      # Black to dark blue
        [(32,0,32), (64,32,64)],    # Dark purple gradient
        [(16,32,48), (48,16,32)],   # Blue to red
    ]
}

def setup_directories():
    """Create necessary directories"""
    for folder in [CONFIG['temp_folder'], CONFIG['output_folder']]:
        Path(folder).mkdir(exist_ok=True)

def fix_pil_compatibility():
    """Fix PIL.Image.ANTIALIAS compatibility issue"""
    try:
        from PIL import Image
        if not hasattr(Image, 'ANTIALIAS'):
            Image.ANTIALIAS = Image.LANCZOS
            logger.info("🔧 Fixed PIL.Image.ANTIALIAS compatibility")
        return True
    except Exception as e:
        logger.error(f"❌ PIL compatibility fix failed: {e}")
        return False

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

def get_background_options():
    """Show available background options"""
    print("🎨 Background Options:")
    print("1. Random image from backgrounds/ folder (current)")
    print("2. Blurred version of the video itself")
    print("3. Solid color background")  
    print("4. Gradient background")
    print("5. Specific background image")
    print("6. No background (black bars)")

def get_background_image_advanced(mode='random', specific_image=None):
    """Advanced background selection"""
    try:
        bg_folder = Path(BACKGROUND_CONFIG['backgrounds_folder'])
        backgrounds = list(bg_folder.glob('*.jpg')) + list(bg_folder.glob('*.png')) + list(bg_folder.glob('*.jpeg'))
        
        if mode == 'random' and backgrounds:
            selected = random.choice(backgrounds)
            logger.info(f"🎨 Random background: {selected.name}")
            return str(selected)
        elif mode == 'specific' and specific_image:
            specific_path = bg_folder / specific_image
            if specific_path.exists():
                logger.info(f"🎨 Specific background: {specific_image}")
                return str(specific_path)
        
        logger.warning("⚠️ No suitable background found")
        return None
        
    except Exception as e:
        logger.error(f"❌ Background selection failed: {e}")
        return None

def process_video_with_background_options(video_path: str, title: str, bg_mode='random', specific_bg=None):
    """Process video with different background options"""
    try:
        fix_pil_compatibility()
        from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip, ColorClip
        
        logger.info(f"🎬 Processing with background mode: {bg_mode}")
        
        # Load video
        video = VideoFileClip(video_path)
        logger.info(f"📊 Original: {video.size[0]}x{video.size[1]}, Duration: {video.duration:.1f}s")
        
        # Trim if too long
        if video.duration > CONFIG['max_duration']:
            logger.info(f"✂️ Trimming to {CONFIG['max_duration']}s")
            video = video.subclip(0, CONFIG['max_duration'])
        
        target_w, target_h = CONFIG['target_resolution']
        
        # Resize video to fit
        video_w, video_h = video.size
        scale = min(target_w / video_w, target_h / video_h)
        new_w = int(video_w * scale)
        new_h = int(video_h * scale)
        
        video_resized = video.resize((new_w, new_h))
        logger.info(f"📏 Resized to: {new_w}x{new_h}")
        
        # Create background based on mode
        if bg_mode == 'random':
            bg_path = get_background_image_advanced('random')
            if bg_path:
                background = ImageClip(bg_path, duration=video.duration)
                background = background.resize((target_w, target_h))
                logger.info("✨ Added random background image")
            else:
                background = ColorClip(size=(target_w, target_h), color=(0,0,0), duration=video.duration)
                logger.info("⬛ Added black background (no images found)")
                
        elif bg_mode == 'blur':
            # Create blurred version of the video itself
            background = video.resize((target_w, target_h))
            try:
                from moviepy.video.fx import blur
                background = blur(background, 15)
                logger.info("✨ Created blurred video background")
            except:
                logger.warning("⚠️ Blur effect not available, using resized video")
                
        elif bg_mode == 'solid':
            color = random.choice(BACKGROUND_CONFIG['solid_colors'])
            background = ColorClip(size=(target_w, target_h), color=color, duration=video.duration)
            logger.info(f"🎨 Solid color background: RGB{color}")
            
        elif bg_mode == 'gradient':
            # Simplified gradient (just use first color for now)
            gradient = random.choice(BACKGROUND_CONFIG['gradients'])
            background = ColorClip(size=(target_w, target_h), color=gradient[0], duration=video.duration)
            logger.info(f"🌈 Gradient background: {gradient}")
            
        elif bg_mode == 'specific':
            bg_path = get_background_image_advanced('specific', specific_bg)
            if bg_path:
                background = ImageClip(bg_path, duration=video.duration)
                background = background.resize((target_w, target_h))
                logger.info(f"✨ Added specific background: {specific_bg}")
            else:
                background = ColorClip(size=(target_w, target_h), color=(0,0,0), duration=video.duration)
                logger.info("⬛ Added black background (specific image not found)")
                
        else:  # none/black bars
            background = ColorClip(size=(target_w, target_h), color=(0,0,0), duration=video.duration)
            logger.info("⬛ Added black background (no decoration)")
        
        # Compose final video
        video_centered = video_resized.set_position('center')  
        final_video = CompositeVideoClip([background, video_centered])
        
        # Export
        output_path = f"{CONFIG['output_folder']}/{title}_{bg_mode}_processed.mp4"
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
        background.close()
        
        # File size
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"✅ Processed! Size: {size_mb:.1f}MB")
        logger.info(f"📁 Saved to: {output_path}")
        
        return output_path
        
    except Exception as e:
        logger.error(f"❌ Enhanced background processing failed: {e}")
        return None

def interactive_background_selection():
    """Let user choose background mode"""
    get_background_options()
    
    choice = input("\nSelect background option (1-6): ").strip()
    
    mode_map = {
        '1': 'random',
        '2': 'blur', 
        '3': 'solid',
        '4': 'gradient',
        '5': 'specific',
        '6': 'none'
    }
    
    mode = mode_map.get(choice, 'random')
    
    if mode == 'specific':
        print("\nAvailable backgrounds:")
        bg_folder = Path(BACKGROUND_CONFIG['backgrounds_folder'])
        backgrounds = list(bg_folder.glob('*.jpg')) + list(bg_folder.glob('*.png'))
        for i, bg in enumerate(backgrounds, 1):
            print(f"{i}. {bg.name}")
        
        bg_choice = input("Enter background filename: ").strip()
        return mode, bg_choice
    
    return mode, None

def main():
    """Main processing function"""
    print("🚀 TikTok Video Processor - Enhanced Backgrounds")
    print("=" * 60)
    
    # Setup
    setup_directories()
    
    # Get URL from user
    url = input("📝 Enter your TikTok video URL: ").strip()
    
    if not url:
        print("❌ No URL provided")
        return
    
    # Interactive background selection
    bg_mode, specific_bg = interactive_background_selection()
    
    print(f"\n🎯 Processing: {url}")
    print(f"🎨 Background mode: {bg_mode}")
    print("-" * 60)
    
    # Download
    video_path, title = download_tiktok_video(url)
    
    if not video_path:
        print("❌ Download failed")
        return
    
    print(f"✅ Download successful!")
    
    # Process with enhanced backgrounds
    output_path = process_video_with_background_options(video_path, title, bg_mode, specific_bg)
    
    if output_path:
        print(f"\n🎉 SUCCESS!")
        print(f"📹 Final video: {output_path}")
        print(f"📊 Ready for YouTube Shorts (1080x1920)")
        print(f"🎨 Background: {bg_mode}")
        
        # Show video info
        if os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"📁 File size: {size_mb:.1f}MB")
    else:
        print("❌ Processing failed")
    
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