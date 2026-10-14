#!/usr/bin/env python3
"""
FFmpeg composer - the same final video as video_composer.render_video(),
built in ONE native ffmpeg pass instead of moviepy's per-frame Python
compositing.

Measured on a real 40 s draft: moviepy spends ~60 s on the background alone
(per-frame resize + composite in Python) and only ~5-15 s on the captions,
so moving just the captions to ffmpeg would barely help — the whole render
has to move. This module does it with the exact same layout math as the
moviepy path (compute_frame_scale, rounded_corner_mask, caption line
grouping), so both produce the same picture:

  background video  → looped, scaled per frame_mode, optional rounded-corner
                      mask, centered over the channel border image (or black)
  narration + music → music looped at 15 % volume, mixed, trimmed
  captions          → an .ass subtitle file (libass), one event per word

Only the caption styles listed in ASS_STYLES are supported here; for any
other style, render_video() keeps using moviepy (see video_composer).
"""

import os
import re
import subprocess
import tempfile
from typing import Callable, Optional

from PIL import Image

from generative import caption_styles
from generative.voice_generator import WordTimings

ASS_STYLES = {"karaoke"}


def ffmpeg_exe() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _ass_color(rgba) -> str:
    """(r,g,b,a) → ASS &HAABBGGRR (ASS alpha: 00 = opaque)."""
    r, g, b, a = rgba
    return f"&H{255 - a:02X}{b:02X}{g:02X}{r:02X}"


def _ass_tag_color(rgba) -> str:
    """(r,g,b,a) → the inline override form \\c&HBBGGRR& (no alpha there)."""
    r, g, b, _ = rgba
    return f"&H{b:02X}{g:02X}{r:02X}&"


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def build_karaoke_ass(words: WordTimings, size, accent_color: str = None) -> str:
    """Karaoke as ASS: the full line centered, the spoken word in the accent
    color — same font, size, stroke and line breaks as
    caption_styles.karaoke_build_clips (lines computed by the SAME
    group_into_lines with the same PIL font metrics)."""
    width, height = size
    font = caption_styles._font(caption_styles.FONT_BOLD, caption_styles._KARAOKE_FONT_SIZE)
    highlight = caption_styles._parse_color(accent_color) or caption_styles._KARAOKE_HIGHLIGHT
    max_width = width - 2 * caption_styles.MARGIN
    lines = caption_styles.group_into_lines(words, font, caption_styles._KARAOKE_STROKE, max_width)

    # ASS "Fontsize" is the font's ascent+descent, not PIL's em size: convert
    # so the text is exactly as tall as in the moviepy render.
    ascent, descent = font.getmetrics()
    family = font.getname()[0]
    white = _ass_color(caption_styles._KARAOKE_TEXT)           # style line: &HAABBGGRR
    black = _ass_color(caption_styles._KARAOKE_STROKE_COLOR)
    tag_white = _ass_tag_color(caption_styles._KARAOKE_TEXT)  # inline tags: &HBBGGRR&
    tag_yellow = _ass_tag_color(highlight)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,{family},{ascent + descent},{white},{white},{black},&H00000000,-1,0,0,0,100,100,0,0,1,{caption_styles._KARAOKE_STROKE},0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for li, line in enumerate(lines):
        for i, (_, start, end) in enumerate(line):
            next_start = line[i + 1][1] if i + 1 < len(line) else (lines[li + 1][0][1] if li + 1 < len(lines) else end)
            parts = [
                (f"{{\\c{tag_yellow}}}{_ass_escape(w[0])}{{\\c{tag_white}}}" if k == i else _ass_escape(w[0]))
                for k, w in enumerate(line)
            ]
            # moviepy leaves ~46 px between words (each word's stroke-inclusive
            # box + a stroke-inclusive space) vs ~22 px for one ASS space: a
            # space + a hard space (\h, never collapsed) matches it within 2 px.
            text = f"{{\\an5\\pos({width // 2},{height // 2})}}" + " \\h".join(parts)
            events.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(max(next_start, start + 0.05))},Karaoke,,0,0,0,,{text}")
    return header + "\n".join(events) + "\n"


def _escape_filter_path(path: str) -> str:
    # inside a filtergraph: escape \ : ' (spaces are fine)
    return path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def render_video_ffmpeg(
    narration_mp3: str, words: WordTimings, bg_video_path: str, bg_music_path: str, out_path: str,
    music_volume: float = 0.15, size=(1080, 1920), caption_style: str = "karaoke", caption_color: str = None,
    frame_mode: str = "fill", rounded_corners: bool = False, border_image_path: str = None,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> str:
    from test3_script import compute_frame_scale, get_video_dimensions, rounded_corner_mask, ROUNDED_CORNER_RADIUS_RATIO

    if caption_style not in ASS_STYLES:
        raise ValueError(f"caption style {caption_style!r} not supported by the ffmpeg composer")
    if not words:
        raise ValueError("no word timings")
    total = words[-1][2]
    tw, th = size

    vw, vh = get_video_dimensions(bg_video_path)
    if not vw:
        raise ValueError(f"unreadable background video: {bg_video_path}")
    has_border = bool(border_image_path and os.path.exists(border_image_path))
    scale = compute_frame_scale(frame_mode or "fill", "specific" if has_border else "none",
                                border_image_path, vw, vh, tw, th)
    sw, sh = max(2, int(vw * scale) // 2 * 2), max(2, int(vh * scale) // 2 * 2)  # even sizes for yuv420p

    work = tempfile.mkdtemp(prefix="ffcompose-")
    ass_path = os.path.join(work, "captions.ass")
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(build_karaoke_ass(words, size, caption_color))

    inputs = ["-stream_loop", "-1", "-i", bg_video_path,       # 0: background video, looped
              "-i", narration_mp3,                              # 1: narration
              "-stream_loop", "-1", "-i", bg_music_path]        # 2: music, looped
    filters = []

    # background video placed exactly like the moviepy path
    filters.append(f"[0:v]fps=25,scale={sw}:{sh}:flags=bicubic,setsar=1[vid]")
    content_w, content_h = sw, sh
    force_black = rounded_corners and frame_mode in ("fill", None)
    if rounded_corners:
        cw, ch = min(sw, tw), min(sh, th)
        if (cw, ch) != (sw, sh):
            filters.append(f"[vid]crop={cw}:{ch}[vid]")
        content_w, content_h = cw, ch
        mask_path = os.path.join(work, "mask.png")
        radius = int(min(content_w, content_h) * ROUNDED_CORNER_RADIUS_RATIO)
        Image.fromarray(rounded_corner_mask(content_w, content_h, radius)).convert("L").save(mask_path)
        inputs += ["-loop", "1", "-i", mask_path]               # 3: corner mask
        filters.append("[3:v]format=gray[mask]")
        filters.append("[vid]format=yuva420p[vida];[vida][mask]alphamerge[vid]")

    if has_border and not force_black:
        border_index = 3 + (1 if rounded_corners else 0)
        inputs += ["-loop", "1", "-i", border_image_path]       # border image
        filters.append(f"[{border_index}:v]scale={tw}:{th},setsar=1,format=yuv420p[base]")
    else:
        filters.append(f"color=c=black:s={tw}x{th}:r=25,format=yuv420p[base]")

    fonts_dir = os.path.dirname(caption_styles.FONT_BOLD)
    filters.append(
        f"[base][vid]overlay=(W-w)/2:(H-h)/2:shortest=0:eof_action=repeat,"
        f"subtitles='{_escape_filter_path(ass_path)}':fontsdir='{_escape_filter_path(fonts_dir)}',format=yuv420p[v]"
    )
    # Narration is mono: convert both tracks to stereo with ffmpeg's standard
    # conversion before mixing — that's what moviepy does when it reads them,
    # and mixing a raw mono track came out 3 dB louder than the moviepy render.
    filters.append("[1:a]aresample=44100,aformat=channel_layouts=stereo[nar]")
    filters.append(f"[2:a]aresample=44100,aformat=channel_layouts=stereo,volume={music_volume}[mus]")
    filters.append("[nar][mus]amix=inputs=2:duration=first:normalize=0[a]")

    cmd = [ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1",
           *inputs, "-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]",
           "-t", f"{total:.3f}", "-r", "25", "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out_path]

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in proc.stdout:  # -progress: key=value lines, out_time_us = position written so far
        m = re.match(r"out_time_us=(\d+)", line.strip())
        if m and progress_cb and total > 0:
            progress_cb(min(1.0, int(m.group(1)) / 1e6 / total))
    stderr = proc.stderr.read()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed: {stderr.strip()[-800:]}")
    if progress_cb:
        progress_cb(1.0)
    return out_path
