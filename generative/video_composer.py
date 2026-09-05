#!/usr/bin/env python3
"""
Video Composer - assembles narration + background video + background music +
karaoke-style captions (a phrase stays on screen, the word being spoken turns
yellow) into a final 9:16 mp4.

Captions are grouped in two passes:
1. Words are split into "blocks" at hard punctuation boundaries (. ! ? :) so
   a list marker like "1." or the clause after a ":" never gets glued to a
   neighboring clause just because there was room left on the line.
2. Each block is then wrapped into one or more caption lines that fit the
   frame's safe width (a margin on each side, so text never touches/exceeds
   the screen edges).

Rendered with PIL (not moviepy's TextClip) because TextClip requires
ImageMagick, which is not installed in this environment.
"""

import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    VideoFileClip, AudioFileClip, ImageClip, ColorClip, CompositeVideoClip, CompositeAudioClip,
)
from moviepy.video.fx.all import loop as vloop
from moviepy.audio.fx.all import audio_loop

from generative.voice_generator import WordTimings
from test3_script import compute_frame_scale, rounded_corner_mask, ROUNDED_CORNER_RADIUS_RATIO
from moviepy.video.fx.all import crop as vcrop

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_SIZE = 64
MARGIN = 70  # safe-zone margin each side, in px, at the 1080-wide reference size
HIGHLIGHT_COLOR = (255, 224, 0, 255)  # bright yellow — validated against this channel's dark backgrounds
TEXT_COLOR = (255, 255, 255, 255)
STROKE_COLOR = (0, 0, 0, 255)
STROKE_WIDTH = 6
HARD_BREAK_CHARS = (".", "!", "?", ":")

_FONT = ImageFont.truetype(FONT_PATH, FONT_SIZE)
_MEASURE = ImageDraw.Draw(Image.new("RGBA", (10, 10)))


def _text_width(text: str) -> int:
    bbox = _MEASURE.textbbox((0, 0), text, font=_FONT, stroke_width=STROKE_WIDTH)
    return bbox[2] - bbox[0]


def _group_into_blocks(words: WordTimings):
    blocks, current = [], []
    for w in words:
        current.append(w)
        if w[0].rstrip("\"')]").endswith(HARD_BREAK_CHARS):
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def _wrap_block(block, max_width: int):
    lines, current = [], []
    for w in block:
        candidate = current + [w]
        text = " ".join(x[0] for x in candidate)
        if _text_width(text) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = [w]
    if current:
        lines.append(current)
    return lines


def _group_into_lines(words: WordTimings, max_width: int):
    lines = []
    for block in _group_into_blocks(words):
        lines.extend(_wrap_block(block, max_width))
    return lines


def _render_line_image(line, highlight_idx: int, highlight_enabled: bool = True) -> np.ndarray:
    # All words must share ONE baseline. Using each word's own tight bbox
    # top (as before) snapped every word to pad independently, so words
    # without ascenders/accents (e.g. "se") sat visibly higher than words
    # with them (e.g. "l'impression", "à") — that was the misalignment.
    # Fixing it by measuring the vertical extent of the WHOLE line once and
    # using that single offset for every word.
    space_w = _MEASURE.textbbox((0, 0), " ", font=_FONT, stroke_width=STROKE_WIDTH)[2]
    word_bboxes = [_MEASURE.textbbox((0, 0), w[0], font=_FONT, stroke_width=STROKE_WIDTH) for w in line]
    total_w = sum(b[2] - b[0] for b in word_bboxes) + space_w * (len(line) - 1)

    line_bbox = _MEASURE.textbbox((0, 0), " ".join(w[0] for w in line), font=_FONT, stroke_width=STROKE_WIDTH)
    line_h = line_bbox[3] - line_bbox[1]
    y_offset = line_bbox[1]

    pad = 20
    img = Image.new("RGBA", (total_w + pad * 2, line_h + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    x = pad
    for i, ((text, _, _), bbox) in enumerate(zip(line, word_bboxes)):
        color = HIGHLIGHT_COLOR if (highlight_enabled and i == highlight_idx) else TEXT_COLOR
        d.text((x, pad - y_offset), text, font=_FONT, fill=color, stroke_width=STROKE_WIDTH, stroke_fill=STROKE_COLOR)
        x += (bbox[2] - bbox[0]) + space_w

    return np.array(img)


def _build_caption_clips(words: WordTimings, size, highlight_enabled: bool = True):
    max_width = size[0] - 2 * MARGIN
    lines = _group_into_lines(words, max_width)
    clips = []
    for li, line in enumerate(lines):
        for i, (text, start, end) in enumerate(line):
            # Highlight holds until the NEXT word starts anywhere in the
            # script (not just within this visual line) so captions never
            # go blank mid-sentence just because a line got wrapped for
            # width — only the very last word falls back to its own end.
            if i + 1 < len(line):
                next_start = line[i + 1][1]
            elif li + 1 < len(lines):
                next_start = lines[li + 1][0][1]
            else:
                next_start = end
            dur = max(next_start - start, 0.05)
            arr = _render_line_image(line, i, highlight_enabled)
            clip = (
                ImageClip(arr)
                .set_start(start)
                .set_duration(dur)
                .set_position("center")
            )
            clips.append(clip)
    return clips


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
    highlight_enabled: bool = True,
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
    caption_clips = _build_caption_clips(words, size, highlight_enabled)

    final = CompositeVideoClip(bg_layers + caption_clips, size=size).set_duration(total_duration)
    final = final.set_audio(final_audio)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    final.write_videofile(
        out_path, fps=25, codec="libx264", audio_codec="aac",
        threads=4, preset="medium", logger=None,
    )
    return out_path
