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

def download_tiktok_video(url: str):
    try:
        import yt_dlp

        ydl_opts = {
            'outtmpl': f"{CONFIG['temp_folder']}/%(title)s.%(ext)s",
            'format': 'best[height<=1920]',
            'writeinfojson': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            safe_title = re.sub(r'[^\w\s-]', '', info.get('title', 'video'))[:30]
            ydl.download([url])

            temp_files = list(Path(CONFIG['temp_folder']).glob('*.mp4'))
            if temp_files:
                return str(temp_files[-1]), safe_title
            else:
                return None, None

    except Exception as e:
        logger.error(f"❌ Download failed: {e}")
        return None, None

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

def process_video_with_background_options(video_path: str, title: str, bg_mode='random', specific_bg=None):
    try:
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
        scale = min(target_w / video_w, target_h / video_h)
        new_size = (int(video_w * scale), int(video_h * scale))
        video_resized = video.resize(new_size)

        # Create background
        if bg_mode == 'random':
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
    print("1. Random image from backgrounds/")
    print("2. Blurred video background")
    print("3. Solid color")
    print("4. Gradient color")
    print("5. Specific image")
    print("6. Black background")

def interactive_background_selection():
    get_background_options()
    choice = input("Choose background mode (1-6): ").strip()

    mode_map = {
        '1': 'random',
        '2': 'blur',
        '3': 'solid',
        '4': 'gradient',
        '5': 'specific',
        '6': 'none'
    }

    mode = mode_map.get(choice, 'random')
    specific = None

    if mode == 'specific':
        bgs = list(Path(CONFIG['backgrounds_folder']).glob('*'))
        print("Available backgrounds:")
        for i, bg in enumerate(bgs, 1):
            print(f"{i}. {bg.name}")
        specific = input("Enter background filename: ").strip()

    return mode, specific

def main():
    print("📹 TikTok Processor with Background Fill")
    setup_directories()

    url = input("Enter TikTok video URL: ").strip()
    if not url:
        print("❌ No URL entered.")
        return

    bg_mode, specific = interactive_background_selection()

    video_path, title = download_tiktok_video(url)
    if not video_path:
        print("❌ Download failed.")
        return

    output = process_video_with_background_options(video_path, title, bg_mode, specific)

    if output:
        print(f"\n✅ Success! Video saved to: {output}")
    else:
        print("❌ Video processing failed.")

    # Cleanup
    for f in Path(CONFIG['temp_folder']).glob('*'):
        f.unlink()

if __name__ == "__main__":
    main()
