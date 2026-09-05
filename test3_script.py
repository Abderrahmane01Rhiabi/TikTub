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

# How much of the canvas the video fills when a per-channel background image is
# used (bg_mode='specific'), so that image's branding always shows around the
# video instead of only when the source's aspect ratio happens to leave a gap.
BRANDED_BACKGROUND_SCALE = 0.88

# Corner radius for frame_mode='rounded_border', as a fraction of the resized
# video's shorter side — scales with the video instead of a fixed pixel value,
# so the roundness looks consistent across different source aspect ratios.
ROUNDED_CORNER_RADIUS_RATIO = 0.07

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

def rounded_corner_mask(w: int, h: int, radius: int) -> np.ndarray:
    """Grayscale rounded-rectangle mask (0-255, uint8) the size of the resized
    video, used to give frame_mode='rounded_border' its rounded corners."""
    from PIL import Image, ImageDraw
    mask_img = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask_img).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    return np.array(mask_img)

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
            # Accept either a path resolvable as-is (e.g. a per-channel
            # channels/<name>/background.jpg) or a filename inside backgrounds_folder.
            direct_path = Path(specific)
            if direct_path.exists():
                return str(direct_path)

            path = folder / specific
            if path.exists():
                return str(path)

        return None
    except:
        return None

def get_video_dimensions(video_path: str):
    """Native (width, height) of a video file, read from the container header
    (no decoding), or (None, None) if it can't be read."""
    try:
        cap = cv2.VideoCapture(video_path)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        if w and h:
            return w, h
    except Exception:
        pass
    return None, None

def suggest_frame_mode(video_path: str) -> str:
    """Best-guess framing mode for a video, based only on how close its native
    aspect ratio is to the 9:16 target canvas — always overridable by the user.

    - Already close to 9:16 -> 'full_border' (branded border visible on all
      sides, minimal content lost to the 0.88 shrink).
    - Anything wider/more square (or landscape) -> 'letterbox' (fits the full
      width, bars only top/bottom, cropped top/bottom instead of bars if the
      video is actually taller than 9:16)."""
    w, h = get_video_dimensions(video_path)
    if not w or not h:
        return 'full_border'
    target_w, target_h = CONFIG['target_resolution']
    target_ratio = target_w / target_h
    video_ratio = w / h
    deviation = abs(video_ratio - target_ratio) / target_ratio
    return 'full_border' if deviation < 0.12 else 'letterbox'

CROP_SAFETY_MARGIN = 20  # px kept around detected content so text/logos sitting
                         # right at the edge of a black border (e.g. a caption)
                         # aren't left touching the crop line with zero breathing room

def crop_black_borders(video_path):
    try:
        cap = cv2.VideoCapture(video_path)
        ret, frame = cap.read()
        cap.release()

        if not ret:
            return None

        frame_h, frame_w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 20, 255, cv2.THRESH_BINARY)
        coords = cv2.findNonZero(thresh)
        if coords is None:
            return None
        x, y, w, h = cv2.boundingRect(coords)

        x2, y2 = x + w, y + h
        x = max(0, x - CROP_SAFETY_MARGIN)
        y = max(0, y - CROP_SAFETY_MARGIN)
        x2 = min(frame_w, x2 + CROP_SAFETY_MARGIN)
        y2 = min(frame_h, y2 + CROP_SAFETY_MARGIN)

        return x, y, x2 - x, y2 - y
    except:
        return None

def compute_frame_scale(frame_mode, bg_mode, specific_bg, video_w, video_h, target_w, target_h):
    """Shared by the real render (process_video_with_background_options) and the
    still-frame preview (render_frame_preview) so the preview is always an exact
    match for what the actual processing will produce."""
    if frame_mode == 'fill':
        return max(target_w / video_w, target_h / video_h)
    elif frame_mode == 'letterbox':
        return target_w / video_w
    elif frame_mode == 'full_border':
        return min(target_w / video_w, target_h / video_h) * BRANDED_BACKGROUND_SCALE
    else:
        # Legacy behaviour (no explicit frame_mode from the Cadrage step).
        scale = min(target_w / video_w, target_h / video_h)
        if bg_mode == 'specific' and specific_bg:
            scale *= BRANDED_BACKGROUND_SCALE
        return scale

def render_frame_preview(video_path: str, frame_mode: str, bg_path: str = None, rounded_corners: bool = False, target_resolution=None) -> bytes:
    """Renders ONE representative still frame exactly as the real pipeline would
    composite it (crop + scale + background), for a WYSIWYG cadrage preview —
    much cheaper than encoding the whole video just to check the positioning.

    rounded_corners is independent of frame_mode — it can combine with any of
    them, including 'fill' (video covers the whole canvas; there, the tiny
    corner slivers a rounded mask reveals are always plain black, never the
    channel's background image, since there's no room for it to read as a
    border anyway).

    Returns JPEG bytes, or None on failure."""
    try:
        target_w, target_h = target_resolution or CONFIG['target_resolution']

        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        mid_frame = max(0, total_frames // 2)
        cap.set(cv2.CAP_PROP_POS_FRAMES, mid_frame)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return None

        crop = crop_black_borders(video_path)
        if crop:
            x, y, w, h = crop
            frame = frame[y:y + h, x:x + w]

        video_h, video_w = frame.shape[:2]
        bg_mode = 'specific' if bg_path else 'none'
        scale = compute_frame_scale(frame_mode, bg_mode, bg_path, video_w, video_h, target_w, target_h)
        new_w, new_h = max(1, int(video_w * scale)), max(1, int(video_h * scale))
        frame_resized = cv2.resize(frame, (new_w, new_h))

        if bg_path and frame_mode != 'fill' and os.path.exists(bg_path):
            bg_img = cv2.imread(bg_path)
            bg_img = cv2.resize(bg_img, (target_w, target_h))
        else:
            bg_img = np.zeros((target_h, target_w, 3), dtype=np.uint8)

        x_off = (target_w - new_w) // 2
        y_off = (target_h - new_h) // 2

        # Same clipping semantics as moviepy's blit() for a clip larger than the
        # canvas (frame_mode='fill' or 'letterbox' overflow) — crop instead of
        # drawing out of bounds.
        src_x1, src_y1 = max(0, -x_off), max(0, -y_off)
        dst_x1, dst_y1 = max(0, x_off), max(0, y_off)
        dst_x2, dst_y2 = min(target_w, x_off + new_w), min(target_h, y_off + new_h)
        src_x2, src_y2 = src_x1 + (dst_x2 - dst_x1), src_y1 + (dst_y2 - dst_y1)

        if dst_x2 > dst_x1 and dst_y2 > dst_y1:
            src_region = frame_resized[src_y1:src_y2, src_x1:src_x2]
            if rounded_corners:
                radius = int(min(new_w, new_h) * ROUNDED_CORNER_RADIUS_RATIO)
                mask = rounded_corner_mask(new_w, new_h, radius)[src_y1:src_y2, src_x1:src_x2]
                alpha = (mask[..., None] / 255.0)
                dst_region = bg_img[dst_y1:dst_y2, dst_x1:dst_x2]
                bg_img[dst_y1:dst_y2, dst_x1:dst_x2] = (src_region * alpha + dst_region * (1 - alpha)).astype(np.uint8)
            else:
                bg_img[dst_y1:dst_y2, dst_x1:dst_x2] = src_region

        ok, buf = cv2.imencode('.jpg', bg_img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return buf.tobytes() if ok else None
    except Exception as e:
        logger.error(f"❌ Preview render failed: {e}")
        return None

def process_video_with_background_options(video_path: str, title: str, bg_mode='random', specific_bg=None, frame_mode=None, rounded_corners=False):
    """frame_mode ('letterbox' | 'full_border' | 'fill' | None): how the video
    sits inside the 9:16 canvas relative to the background border, chosen
    per-video by the user in the 'Cadrage' wizard step (see
    suggest_frame_mode). None keeps the legacy auto behaviour (fit-inside, +0.88
    shrink only when bg_mode='specific').

    rounded_corners is independent of frame_mode — it can combine with any of
    them, including 'fill'. For 'fill' specifically the video is scaled to
    *cover* the canvas (bigger than it in one dimension), so it's cropped
    down to exactly canvas size before masking — otherwise the mask's rounded
    corners would land outside the visible frame and never show at all. The
    tiny corner slivers a rounded mask reveals under 'fill' are always plain
    black, never the chosen background, since there's no room for one to
    read as a border anyway."""
    try:
        # NOTE: AI metadata generation happens once, later, in
        # BatchProcessor.generate_ai_content() (channel-aware, real video path).
        # This function only handles background/cropping/resizing.
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

        scale = compute_frame_scale(frame_mode, bg_mode, specific_bg, video_w, video_h, target_w, target_h)

        new_size = (int(video_w * scale), int(video_h * scale))
        video_resized = video.resize(new_size)

        # Black corners for 'fill' + rounded_corners regardless of whether this
        # particular source's aspect ratio actually needs cropping — a video
        # that already matches 9:16 exactly (no overflow) must look identical
        # to one that doesn't, so this can't depend on incidental overflow.
        force_black_bg = rounded_corners and frame_mode == 'fill'
        if rounded_corners:
            if new_size[0] > target_w or new_size[1] > target_h:
                # 'fill' (or any overflowing scale) covers more than the canvas —
                # crop down to exactly canvas size first, so the mask's rounded
                # corners land on the canvas's own corners instead of outside
                # the visible frame where they'd never show.
                from moviepy.video.fx.all import crop as _vcrop
                video_resized = _vcrop(
                    video_resized, width=min(new_size[0], target_w), height=min(new_size[1], target_h),
                    x_center=new_size[0] / 2, y_center=new_size[1] / 2,
                )
                new_size = (min(new_size[0], target_w), min(new_size[1], target_h))

            radius = int(min(new_size) * ROUNDED_CORNER_RADIUS_RATIO)
            mask_array = rounded_corner_mask(new_size[0], new_size[1], radius) / 255.0
            mask_clip = ImageClip(mask_array, ismask=True, duration=video.duration)
            video_resized = video_resized.set_mask(mask_clip)

        # Create background
        if force_black_bg:
            background = ColorClip(size=(target_w, target_h), color=(0, 0, 0), duration=video.duration)
        elif bg_mode == 'random':
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
