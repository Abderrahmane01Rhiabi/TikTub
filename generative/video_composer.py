#!/usr/bin/env python3
"""
Video Composer - assembles narration + background video + background music +
animated captions into a final 9:16 mp4.

Caption rendering (word grouping/wrapping, per-style fonts and animation)
lives in generative/caption_styles.py — this module only picks a style by
name (STYLES dict) and composites its clips with the background/audio.
"""

import os
from moviepy.editor import (
    VideoFileClip, AudioFileClip, ImageClip, ColorClip, CompositeVideoClip, CompositeAudioClip,
)
from moviepy.video.fx.all import loop as vloop
from moviepy.audio.fx.all import audio_loop

from generative.voice_generator import WordTimings
from generative import caption_styles
from test3_script import compute_frame_scale, rounded_corner_mask, ROUNDED_CORNER_RADIUS_RATIO
from moviepy.video.fx.all import crop as vcrop


def _build_background_layers(bg_video_path, total_duration, size, frame_mode, rounded_corners, border_image_path):
    """Returns the list of clips (bottom to top) that make up the background:
    the video placed/scaled per frame_mode ('fill' / 'letterbox' /
    'full_border', same scale math as the curation pipeline's Cadrage step),
    with rounded_corners as an INDEPENDENT toggle that can combine with any
    of them — including 'fill', where the video covers the whole canvas.

    For 'fill', the video is scaled to *cover* the canvas (bigger than it in
    one dimension), so with rounded_corners it's cropped down to exactly
    canvas size before masking — otherwise the mask's rounded corners would
    land outside the visible frame and never show. Those corner slivers are
    always plain black, never the channel's background image, since there's
    no room for one to read as a border anyway."""
    raw = VideoFileClip(bg_video_path).without_audio()
    video_w, video_h = raw.size
    target_w, target_h = size

    bg_mode = "specific" if border_image_path else "none"
    scale = compute_frame_scale(frame_mode or "fill", bg_mode, border_image_path, video_w, video_h, target_w, target_h)
    new_size = (max(1, int(video_w * scale)), max(1, int(video_h * scale)))

    content = raw.resize(new_size)
    if content.duration < total_duration:
        content = vloop(content, duration=total_duration)
    content = content.subclip(0, total_duration)

    force_black_bg = rounded_corners and frame_mode in ("fill", None)
    if rounded_corners:
        if new_size[0] > target_w or new_size[1] > target_h:
            content = vcrop(
                content, width=min(new_size[0], target_w), height=min(new_size[1], target_h),
                x_center=new_size[0] / 2, y_center=new_size[1] / 2,
            )
            new_size = (min(new_size[0], target_w), min(new_size[1], target_h))

        radius = int(min(new_size) * ROUNDED_CORNER_RADIUS_RATIO)
        mask_array = rounded_corner_mask(new_size[0], new_size[1], radius) / 255.0
        content = content.set_mask(ImageClip(mask_array, ismask=True, duration=total_duration))

    content = content.set_position("center")

    if force_black_bg:
        border = ColorClip(size=size, color=(0, 0, 0), duration=total_duration)
    elif border_image_path and os.path.exists(border_image_path):
        border = ImageClip(border_image_path, duration=total_duration).resize(size)
    else:
        border = ColorClip(size=size, color=(0, 0, 0), duration=total_duration)

    return [border, content]


def render_video(
    narration_mp3: str,
    words: WordTimings,
    bg_video_path: str,
    bg_music_path: str,
    out_path: str,
    music_volume: float = 0.15,
    size=(1080, 1920),
    caption_style: str = "karaoke",
    caption_color: str = None,
    frame_mode: str = "fill",
    rounded_corners: bool = False,
    border_image_path: str = None,
) -> str:
    total_duration = words[-1][2] if words else AudioFileClip(narration_mp3).duration
    narration_audio = AudioFileClip(narration_mp3).subclip(0, total_duration)

    bg_layers = _build_background_layers(bg_video_path, total_duration, size, frame_mode, rounded_corners, border_image_path)

    music = AudioFileClip(bg_music_path)
    if music.duration < total_duration:
        music = audio_loop(music, duration=total_duration)
    music = music.subclip(0, total_duration).volumex(music_volume)

    final_audio = CompositeAudioClip([narration_audio, music])
    style_fn = caption_styles.STYLES.get(caption_style, caption_styles.STYLES["karaoke"])
    style_kwargs = {"accent_color": caption_color} if caption_style in caption_styles.CUSTOMIZABLE_COLOR_STYLES else {}
    caption_clips = style_fn(words, size, **style_kwargs)

    final = CompositeVideoClip(bg_layers + caption_clips, size=size).set_duration(total_duration)
    final = final.set_audio(final_audio)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    final.write_videofile(
        out_path, fps=25, codec="libx264", audio_codec="aac",
        threads=4, preset="medium", logger=None,
    )
    return out_path
