#!/usr/bin/env python3

import os
import re
import random
import logging
import cv2
import numpy as np
from pathlib import Path

from moviepy.editor import (
    VideoFileClip,
    ImageClip,
    CompositeVideoClip,
    ColorClip
)

# Import AI content generator
from ai_tags_generator import AITagsGenerator

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

BACKGROUND_CONFIG = {
    'backgrounds_folder': 'backgrounds/',
    'solid_colors': [
        (0, 0, 0),
        (32, 32, 64),
        (64, 32, 64),
        (32, 64, 32),
    ],
    'gradients': [
        [(0, 0, 0), (32, 32, 64)],
        [(32, 0, 32), (64, 32, 64)],
        [(16, 32, 48), (48, 16, 32)],
    ]
}

def setup_directories():
    for folder in [CONFIG['temp_folder'], CONFIG['output_folder']]:
        Path(folder).mkdir(exist_ok=True)

def fix_pil_compatibility():
    try:
        from PIL import Image
        if not hasattr(Image, 'ANTIALIAS'):
            Image.ANTIALIAS = Image.LANCZOS
        return True
    except:
        return False

def detect_platform(url: str) -> str:
    """Detect platform from URL"""
    if 'tiktok.com' in url.lower():
        return 'tiktok'
    elif 'instagram.com' in url.lower():
        return 'instagram'
    elif 'youtube.com' in url.lower() and 'shorts' in url.lower():
        return 'youtube_shorts'
    else:
        return 'unknown'

def download_social_video(url: str):
    """Download video from TikTok, Instagram, or YouTube Shorts"""
    try:
        import yt_dlp
        
        platform = detect_platform(url)
        logger.info(f"🎯 Detected platform: {platform}")

        # Platform-specific configurations
        if platform == 'instagram':
            ydl_opts = {
                'outtmpl': f"{CONFIG['temp_folder']}/%(uploader)s_%(title)s.%(ext)s",
                'format': 'best[height<=1920]',
                'writeinfojson': True,
                'extract_flat': False,
            }
        elif platform == 'tiktok':
            ydl_opts = {
                'outtmpl': f"{CONFIG['temp_folder']}/%(uploader)s_%(title)s.%(ext)s",
                'format': 'best[height<=1920]',
                'writeinfojson': True,
            }
        else:
            # Default for other platforms
            ydl_opts = {
                'outtmpl': f"{CONFIG['temp_folder']}/%(title)s.%(ext)s",
                'format': 'best[height<=1920]',
                'writeinfojson': True,
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Extract metadata
            title = info.get('title', 'video')
            description = info.get('description', '')
            uploader = info.get('uploader', '')
            tags = info.get('tags', [])
            
            # Create safe filename
            safe_title = re.sub(r'[^\w\s-]', '', title)[:30]
            
            # Download the video
            ydl.download([url])

            # Find downloaded video
            temp_files = list(Path(CONFIG['temp_folder']).glob('*.mp4'))
            if temp_files:
                video_path = str(temp_files[-1])
                
                # Create enhanced metadata
                metadata = {
                    'title': title,
                    'safe_title': safe_title,
                    'description': description,
                    'uploader': uploader,
                    'tags': tags,
                    'platform': platform,
                    'original_url': url,
                    'file_path': video_path
                }
                
                return video_path, metadata
            else:
                return None, None

    except Exception as e:
        logger.error(f"❌ Download failed: {e}")
        return None, None

# Keep original function for backward compatibility
def download_tiktok_video(url: str):
    """Legacy function - redirects to download_social_video"""
    result = download_social_video(url)
    if result and result[1]:
        return result[0], result[1]['safe_title']
    return None, None

def detect_target_channel_ai(metadata: dict) -> str:
    """AI-powered channel detection based on content analysis"""
    
    # Channel profiles with keywords and patterns
    CHANNEL_PROFILES = {
        'AnimeShorts137': {
            'keywords': ['anime', 'manga', 'otaku', 'naruto', 'dragon ball', 'one piece', 'attack on titan', 'demon slayer', 'jujutsu kaisen'],
            'hashtags': ['#anime', '#manga', '#otaku', '#weeb', '#animeedit', '#animememes'],
            'weight': 0
        },
        'LungTeMotivates': {
            'keywords': ['motivation', 'success', 'mindset', 'goals', 'inspire', 'grind', 'hustle', 'entrepreneur', 'gym', 'fitness'],
            'hashtags': ['#motivation', '#success', '#mindset', '#grind', '#hustle', '#entrepreneur', '#gym', '#fitness'],
            'weight': 0
        },
        'meme0culture': {
            'keywords': ['meme', 'funny', 'viral', 'trend', 'comedy', 'humor', 'lol', 'cringe', 'troll'],
            'hashtags': ['#meme', '#funny', '#viral', '#trend', '#comedy', '#humor', '#lol', '#cringe'],
            'weight': 0
        },
        'ZitBliss': {
            'keywords': ['lifestyle', 'daily', 'vlog', 'life', 'story', 'personal', 'experience', 'real'],
            'hashtags': ['#lifestyle', '#daily', '#vlog', '#life', '#real', '#story'],
            'weight': 0
        },
        'LungTe8888': {
            'keywords': ['general', 'content', 'entertainment', 'fun', 'cool', 'awesome', 'amazing'],
            'hashtags': ['#content', '#entertainment', '#fun', '#cool', '#awesome'],
            'weight': 0
        }
    }
    
    # Extract text content for analysis
    text_content = []
    if metadata.get('title'):
        text_content.append(metadata['title'].lower())
    if metadata.get('description'):
        text_content.append(metadata['description'].lower())
    if metadata.get('tags'):
        text_content.extend([tag.lower() for tag in metadata['tags']])
    
    full_text = ' '.join(text_content)
    
    # Score each channel based on keyword matches
    for channel, profile in CHANNEL_PROFILES.items():
        # Keyword scoring
        for keyword in profile['keywords']:
            if keyword in full_text:
                profile['weight'] += 2
        
        # Hashtag scoring (higher weight)
        for hashtag in profile['hashtags']:
            if hashtag.lower() in full_text:
                profile['weight'] += 3
        
        # Platform-specific bonus
        platform = metadata.get('platform', '')
        if platform == 'instagram' and channel in ['LungTeMotivates', 'ZitBliss']:
            profile['weight'] += 1  # Instagram better for motivational/lifestyle
        elif platform == 'tiktok' and channel in ['meme0culture', 'AnimeShorts137']:
            profile['weight'] += 1  # TikTok better for memes/anime
    
    # Find best match
    best_channel = max(CHANNEL_PROFILES.keys(), key=lambda x: CHANNEL_PROFILES[x]['weight'])
    best_score = CHANNEL_PROFILES[best_channel]['weight']
    
    # If no clear match, use default based on platform
    if best_score == 0:
        platform = metadata.get('platform', '')
        if platform == 'instagram':
            return 'ZitBliss'  # Default for Instagram
        elif platform == 'tiktok':
            return 'LungTe8888'  # Default for TikTok
        else:
            return 'LungTe8888'  # General default
    
    logger.info(f"🎯 AI Channel Detection: {best_channel} (score: {best_score})")
    return best_channel

def get_smart_background_for_channel(channel_name: str, mode: str = 'smart') -> str:
    """Select background based on detected channel for better brand consistency"""
    
    # Channel-specific background mapping
    CHANNEL_BACKGROUNDS = {
        'AnimeShorts137': ['animeshorts.png'],
        'LungTeMotivates': ['LungTeMotivates.png'], 
        'meme0culture': ['memeculture.jpg', 'memeculture2.png'],
        'ZitBliss': ['zitbliss.png'],
        'LungTe8888': ['lungTe888.png', 'default.jpg']
    }
    
    try:
        folder = Path(BACKGROUND_CONFIG['backgrounds_folder'])
        
        # If we have channel-specific backgrounds and channel is detected
        if channel_name and channel_name in CHANNEL_BACKGROUNDS:
            channel_bgs = CHANNEL_BACKGROUNDS[channel_name]
            available_bgs = []
            
            for bg in channel_bgs:
                bg_path = folder / bg
                if bg_path.exists():
                    available_bgs.append(str(bg_path))
            
            if available_bgs:
                selected = random.choice(available_bgs)
                logger.info(f"🎨 Smart background for {channel_name}: {Path(selected).name}")
                return selected
        
        # Fallback to random selection if no channel match
        logger.info(f"🎲 No specific background for {channel_name}, using random selection")
        return get_background_image('random')
        
    except Exception as e:
        logger.warning(f"⚠️ Smart background selection failed: {e}, using random")
        return get_background_image('random')

def get_background_image(mode='random', specific=None):
    try:
        folder = Path(BACKGROUND_CONFIG['backgrounds_folder'])
        files = list(folder.glob('*.jpg')) + list(folder.glob('*.png'))

        if mode == 'random' and files:
            return str(random.choice(files))

        if mode == 'specific' and specific:
            path = folder / specific
            if path.exists():
                return str(path)

        return None
    except:
        return None

def crop_black_borders(video_path):
    try:
        cap = cv2.VideoCapture(video_path)
        ret, frame = cap.read()
        cap.release()

        if not ret:
            return None

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 20, 255, cv2.THRESH_BINARY)
        coords = cv2.findNonZero(thresh)
        if coords is None:
            return None
        x, y, w, h = cv2.boundingRect(coords)
        return x, y, w, h
    except:
        return None

def process_lungte888_portrait_mode(video, title, target_w, target_h):
    """Special portrait mode processing for lungTe888 channel with blurred background"""
    try:
        logger.info("🎬 Processing lungTe888 with Portrait Mode + Blurred Background")
        
        video_w, video_h = video.size
        
        # Create blurred background from the video itself
        background = video.resize((target_w, target_h))
        
        # Apply blur effect with fallback
        try:
            import moviepy.video.fx.all as vfx
            background_blurred = vfx.blur(background, 25)  # Heavy blur
            logger.info("✨ Created blurred background from video")
        except:
            try:
                from moviepy.video.fx import blur
                background_blurred = blur.blur(background, 25)
                logger.info("✨ Created blurred background from video")
            except:
                logger.warning("⚠️ Blur effect not available, using stretched background")
                background_blurred = background
        
        # Calculate scaling for the main video to fill the screen (full size)
        scale = min(target_w / video_w, target_h / video_h)
        new_w = int(video_w * scale)
        new_h = int(video_h * scale)
        
        # Resize main video to full size
        video_resized = video.resize((new_w, new_h))
        logger.info(f"📏 lungTe888 video resized to FULL SIZE: {new_w}x{new_h}")
        
        # Position video in center (full size)
        video_centered = video_resized.set_position('center')
        
        # Compose final video with blurred background and main video
        final = CompositeVideoClip([background_blurred, video_centered])
        
        # Export with lungTe888 identifier
        safe_title = re.sub(r'[^\w\s-]', '', title)[:40]
        output_path = f"{CONFIG['output_folder']}/{safe_title}_lungte888_portrait.mp4"
        
        logger.info("💾 Exporting lungTe888 portrait mode video...")
        final.write_videofile(
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
        background_blurred.close()
        final.close()
        
        # File size
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"✅ lungTe888 Portrait Mode processed! Size: {size_mb:.1f}MB")
        
        return output_path
        
    except Exception as e:
        logger.error(f"❌ lungTe888 portrait mode processing failed: {e}")
        return None

def process_video_with_background_options(video_path: str, title: str, bg_mode='random', specific_bg=None, channel_name=None, video_data=None):
    try:
        # Generate AI content for the video
        print("🤖 Generating AI content...")
        ai_generator = AITagsGenerator()
        
        # Prepare video data for AI analysis
        if not video_data:
            video_data = {
                'title': title,
                'file_path': video_path,
                'description': f"Video: {title}",
                'platform': 'unknown'
            }
        
        # Enhanced description for AI based on platform
        platform = video_data.get('platform', 'unknown')
        if platform == 'instagram':
            video_data['description'] = f"Instagram content: {video_data.get('title', title)}"
        elif platform == 'tiktok':
            video_data['description'] = f"TikTok content: {video_data.get('title', title)}"
        
        # Add channel info to video data if provided
        if channel_name:
            video_data['target_channel'] = channel_name
        
        ai_content = ai_generator.generate_ai_content(video_data)
        if ai_content:
            print(f"📝 AI Title: {ai_content.get('title', 'N/A')}")
            print(f"📄 AI Description: {ai_content.get('description', 'N/A')[:100]}...")
            print(f"🏷️ AI Tags: {', '.join(ai_content.get('tags', []))}")
        else:
            print("⚠️ AI content generation failed, using defaults")
        
        fix_pil_compatibility()

        video = VideoFileClip(video_path)

        if video.duration > CONFIG['max_duration']:
            video = video.subclip(0, CONFIG['max_duration'])

        # Crop borders
        crop = crop_black_borders(video_path)
        if crop:
            x, y, w, h = crop
            video = video.crop(x1=x, y1=y, x2=x+w, y2=y+h)
            logger.info(f"✂️ Cropped video borders: x={x}, y={y}, w={w}, h={h}")

        # Resize
        video_w, video_h = video.size
        target_w, target_h = CONFIG['target_resolution']
        
        # SPECIAL: Portrait mode for lungTe888 channel
        if channel_name and ('lungte888' in channel_name.lower() or 'lungte8888' in channel_name.lower()):
            logger.info("🌟 Using Portrait Mode for lungTe888 channel")
            return process_lungte888_portrait_mode(video, title, target_w, target_h)
        
        # Regular processing for other channels
        scale = min(target_w / video_w, target_h / video_h)
        new_size = (int(video_w * scale), int(video_h * scale))
        video_resized = video.resize(new_size)

        # Create background with smart channel matching
        if bg_mode == 'random':
            # Use smart background if channel is detected, otherwise random
            if channel_name:
                bg_path = get_smart_background_for_channel(channel_name, 'smart')
            else:
                bg_path = get_background_image('random')
                
            if bg_path:
                background = ImageClip(bg_path, duration=video.duration).resize((target_w, target_h))
            else:
                background = ColorClip(size=(target_w, target_h), color=(0, 0, 0), duration=video.duration)

        elif bg_mode == 'smart':
            # Smart channel-matched background selection
            if channel_name:
                bg_path = get_smart_background_for_channel(channel_name, 'smart')
            else:
                bg_path = get_background_image('random')
                
            if bg_path:
                background = ImageClip(bg_path, duration=video.duration).resize((target_w, target_h))
            else:
                background = ColorClip(size=(target_w, target_h), color=(0, 0, 0), duration=video.duration)

        elif bg_mode == 'blur':
            background = video.resize((target_w, target_h))
            try:
                from moviepy.video.fx import blur
                background = blur.blur(background, 15)
            except:
                pass

        elif bg_mode == 'solid':
            color = random.choice(BACKGROUND_CONFIG['solid_colors'])
            background = ColorClip(size=(target_w, target_h), color=color, duration=video.duration)

        elif bg_mode == 'gradient':
            gradient = random.choice(BACKGROUND_CONFIG['gradients'])
            background = ColorClip(size=(target_w, target_h), color=gradient[0], duration=video.duration)

        elif bg_mode == 'specific':
            bg_path = get_background_image('specific', specific_bg)
            if bg_path:
                background = ImageClip(bg_path, duration=video.duration).resize((target_w, target_h))
            else:
                background = ColorClip(size=(target_w, target_h), color=(0, 0, 0), duration=video.duration)

        else:
            background = ColorClip(size=(target_w, target_h), color=(0, 0, 0), duration=video.duration)

        video_centered = video_resized.set_position('center')
        final = CompositeVideoClip([background, video_centered])

        output_path = f"{CONFIG['output_folder']}/{title}_{bg_mode}_processed.mp4"

        final.write_videofile(
            output_path,
            fps=30,
            codec='libx264',
            audio_codec='aac',
            temp_audiofile=f"{CONFIG['temp_folder']}/temp-audio.m4a",
            remove_temp=True,
            verbose=False,
            logger=None
        )

        video.close()
        background.close()
        final.close()

        return output_path

    except Exception as e:
        logger.error(f"❌ Processing failed: {e}")
        return None

def get_background_options():
    print("Background Options:")
    print("1. Smart channel-matched backgrounds (recommended)")
    print("2. Random image from backgrounds/")
    print("3. Blurred video background")
    print("4. Solid color")
    print("5. Gradient color")
    print("6. Specific image")
    print("7. Black background")

def interactive_background_selection():
    get_background_options()
    choice = input("Choose background mode (1-7): ").strip()

    mode_map = {
        '1': 'smart',
        '2': 'random',
        '3': 'blur',
        '4': 'solid',
        '5': 'gradient',
        '6': 'specific',
        '7': 'none'
    }

    mode = mode_map.get(choice, 'smart')  # Default to smart
    specific = None

    if mode == 'specific':
        bgs = list(Path(CONFIG['backgrounds_folder']).glob('*'))
        print("Available backgrounds:")
        for i, bg in enumerate(bgs, 1):
            print(f"{i}. {bg.name}")
        specific = input("Enter background filename: ").strip()

    return mode, specific

def main():
    print("📹 Multi-Platform Social Media Processor")
    print("🎯 Supports: TikTok, Instagram, YouTube Shorts")
    setup_directories()

    url = input("Enter video URL (TikTok/Instagram/YouTube): ").strip()
    if not url:
        print("❌ No URL entered.")
        return

    # Detect platform
    platform = detect_platform(url)
    print(f"🎯 Detected platform: {platform}")

    bg_mode, specific = interactive_background_selection()

    # Download with enhanced metadata
    video_path, metadata = download_social_video(url)
    if not video_path or not metadata:
        print("❌ Download failed.")
        return

    # AI-powered channel detection
    target_channel = detect_target_channel_ai(metadata)
    print(f"🤖 AI detected target channel: {target_channel}")

    # Process video with enhanced metadata
    output = process_video_with_background_options(
        video_path, 
        metadata['safe_title'], 
        bg_mode, 
        specific,
        channel_name=target_channel,
        video_data=metadata
    )

    if output:
        print(f"\n✅ Success! Video saved to: {output}")
        print(f"📊 Video Info:")
        print(f"   Platform: {metadata.get('platform', 'Unknown')}")
        print(f"   Original Title: {metadata.get('title', 'N/A')}")
        print(f"   Uploader: {metadata.get('uploader', 'N/A')}")
        print(f"   Target Channel: {target_channel}")
    else:
        print("❌ Video processing failed.")

    # Cleanup
    for f in Path(CONFIG['temp_folder']).glob('*'):
        f.unlink()

if __name__ == "__main__":
    main()
