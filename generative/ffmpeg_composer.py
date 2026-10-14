#!/usr/bin/env python3
"""
FFmpeg composer - the same final video as video_composer.render_video_moviepy(),
built in ONE native ffmpeg pass instead of moviepy's per-frame Python
compositing.

Measured on a real 40 s draft: moviepy spends ~60 s on the background alone
(per-frame resize + composite in Python) and only ~5-15 s on the captions,
so moving just the captions to ffmpeg would barely help — the whole render
moves. Same layout math as the moviepy path (compute_frame_scale,
rounded_corner_mask, caption_styles line/chunk grouping and PIL metrics),
so both produce the same picture:

  background video  → looped, scaled per frame_mode, optional rounded-corner
                      mask, centered over the channel border image (or black)
  captions          → an .ass subtitle file rendered by libass, one builder
                      per caption style (all 6 styles of caption_styles)
  narration + music → music ducked under the voice, faded in/out, looped
                      with a crossfade when shorter than the video

Text is placed so its INK is centered where moviepy centered its image
(libass centers the font's line box instead: see _ink_center_offset), and
word gaps match moviepy's stroke-inclusive spacing (see _gap_tag).
"""

import math
import os
import re
import shutil
import subprocess
import tempfile
from typing import Callable, List, Optional

from PIL import Image

from generative import caption_styles as cs
from generative.voice_generator import WordTimings

ASS_STYLES = {"karaoke", "mrbeast", "hormozi", "bounce", "typewriter", "minimal"}

# music: level in the pauses, how much it ducks under the voice, fades
MUSIC_LEVEL = 0.22          # moviepy path: a constant 0.15
DUCK = {"threshold": 0.04, "ratio": 5, "attack": 25, "release": 450}
MUSIC_FADE_IN = 0.8
MUSIC_FADE_OUT = 1.5
LOOP_CROSSFADE = 2.0


def ffmpeg_exe() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def media_duration(path: str) -> float:
    out = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", path], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", out)
    if not m:
        raise ValueError(f"unreadable media: {path}")
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


# ---------------------------------------------------------------------------
# ASS helpers
# ---------------------------------------------------------------------------

def _ass_color(rgba) -> str:
    """(r,g,b,a) → style-line form &HAABBGGRR (ASS alpha: 00 = opaque)."""
    r, g, b, a = rgba
    return f"&H{255 - a:02X}{b:02X}{g:02X}{r:02X}"


def _tag_color(rgba) -> str:
    """(r,g,b,a) → inline override form &HBBGGRR& (alpha goes in \\1a)."""
    r, g, b, _ = rgba
    return f"&H{b:02X}{g:02X}{r:02X}&"


def _tag_alpha(a: int) -> str:
    return f"&H{255 - a:02X}&"


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def _win_metrics(path: str):
    """(unitsPerEm, usWinAscent + usWinDescent) read straight from the font
    file's head and OS/2 tables (no fontTools dependency for two numbers)."""
    import struct
    with open(path, "rb") as fh:
        data = fh.read()
    tables = {}
    for i in range(struct.unpack(">H", data[4:6])[0]):
        tag, _, off, length = struct.unpack(">4sIII", data[12 + 16 * i: 28 + 16 * i])
        tables[tag] = data[off: off + length]
    upm = struct.unpack(">H", tables[b"head"][18:20])[0]
    win_ascent, win_descent = struct.unpack(">HH", tables[b"OS/2"][74:78])
    return upm, win_ascent + win_descent


class FontSpec:
    def __init__(self, path: str, size: int):
        self.path = path
        self.pil = cs._font(path, size)
        self.family, style_name = self.pil.getname()
        self.bold = -1 if "Bold" in style_name else 0
        # libass sizes a font so that usWinAscent+usWinDescent == Fontsize
        # (VSFilter compatibility); PIL's `size` is the em size. Converting
        # through the font's own OS/2 metrics gives glyphs exactly as big as
        # the moviepy render — using PIL's ascent+descent instead made
        # FreeSans (MrBeast, Hormozi) 18 % too small.
        upm, win_height = _win_metrics(path)
        self.ass_size = round(size * win_height / upm, 1)


def _style(name: str, f: FontSpec, primary, outline=(0, 0, 0, 255), border: float = 0, spacing: float = 0) -> str:
    return (f"Style: {name},{f.family},{f.ass_size},{_ass_color(primary)},{_ass_color(primary)},"
            f"{_ass_color(outline)},&H00000000,{f.bold},0,0,0,100,100,{spacing:g},0,1,{border:g},0,5,0,0,0,1")


def _header(size, styles: List[str]) -> str:
    w, h = size
    return ("[Script Info]\nScriptType: v4.00+\n"
            f"PlayResX: {w}\nPlayResY: {h}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n" + "\n".join(styles) +
            "\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")


def _event(start: float, end: float, style: str, text: str, layer: int = 0, min_dur: float = 0.05) -> str:
    return f"Dialogue: {layer},{_ass_time(start)},{_ass_time(max(end, start + min_dur))},{style},,0,0,0,,{text}"


def _ink_center_offset(text: str, f: FontSpec, stroke: int = 0) -> float:
    """moviepy centers the text's INK box on screen; libass (\\an5) centers
    the font's line box (ascent+descent). Returns how far the ink center
    sits below the line-box center, so the position can be shifted up by it."""
    _, ink_h, ink_top = cs._text_size(text, f.pil, stroke)
    ascent, descent = f.pil.getmetrics()
    return (ink_top + ink_h / 2) - (ascent + descent) / 2


def _gap_tag(f: FontSpec, stroke: int) -> str:
    """moviepy lays words out as separate stroke-inclusive boxes plus a
    stroke-inclusive space, so its gap between words is wider than a font
    space; reproduce it as a space with extra letter-spacing (\\fsp)."""
    sample = "H"
    moviepy_gap = cs._text_size(" ", f.pil, stroke)[0] + (cs._text_size(sample, f.pil, stroke)[0] - f.pil.getlength(sample))
    extra = moviepy_gap - f.pil.getlength(" ")
    return f"{{\\fsp{extra:.1f}}} {{\\fsp0}}" if extra > 0.5 else " "


def _next_start(lines, li: int, i: int, end: float) -> float:
    line = lines[li]
    if i + 1 < len(line):
        return line[i + 1][1]
    return lines[li + 1][0][1] if li + 1 < len(lines) else end


def _scale_tag(scale: float) -> str:
    """Shrinks a unit that would be wider than the safe area (cs.fit_scale)."""
    return "" if scale >= 1.0 else f"\\fscx{scale * 100:.1f}\\fscy{scale * 100:.1f}"


def _rounded_rect_path(w: float, h: float, r: float) -> str:
    """ASS vector drawing of a rounded rectangle (cubic Bézier corners)."""
    k = r * 0.4477  # 1 - 0.5523 (circle approximation)
    return (f"m {r:.1f} 0 l {w - r:.1f} 0 b {w - k:.1f} 0 {w:.1f} {k:.1f} {w:.1f} {r:.1f} "
            f"l {w:.1f} {h - r:.1f} b {w:.1f} {h - k:.1f} {w - k:.1f} {h:.1f} {w - r:.1f} {h:.1f} "
            f"l {r:.1f} {h:.1f} b {k:.1f} {h:.1f} 0 {h - k:.1f} 0 {h - r:.1f} "
            f"l 0 {r:.1f} b 0 {k:.1f} {k:.1f} 0 {r:.1f} 0")


# ---------------------------------------------------------------------------
# One builder per caption style (mirrors generative/caption_styles.py)
# ---------------------------------------------------------------------------

def _karaoke(words, size, accent):
    f = FontSpec(cs.FONT_BOLD, cs._KARAOKE_FONT_SIZE)
    hi = cs._parse_color(accent) or cs._KARAOKE_HIGHLIGHT
    max_width = size[0] - 2 * cs.MARGIN
    measure = lambda text: cs.drawn_words_width(text, f.pil, cs._KARAOKE_STROKE)
    lines = cs.group_into_lines(words, f.pil, cs._KARAOKE_STROKE, max_width, measure)
    gap = _gap_tag(f, cs._KARAOKE_STROKE)
    cx, cy = size[0] // 2, size[1] / 2
    events = []
    for li, line in enumerate(lines):
        joined = " ".join(w[0] for w in line)
        scale = cs.fit_scale(measure(joined), max_width)
        dy = _ink_center_offset(joined, f, cs._KARAOKE_STROKE) * scale
        for i, (_, start, end) in enumerate(line):
            parts = [f"{{\\c{_tag_color(hi)}}}{_esc(w[0])}{{\\c{_tag_color(cs._KARAOKE_TEXT)}}}" if k == i else _esc(w[0])
                     for k, w in enumerate(line)]
            events.append(_event(start, _next_start(lines, li, i, end), "K",
                                 f"{{\\an5\\pos({cx},{cy - dy:.1f}){_scale_tag(scale)}}}" + gap.join(parts)))
    return [_style("K", f, cs._KARAOKE_TEXT, cs._KARAOKE_STROKE_COLOR, cs._KARAOKE_STROKE)], events


def _mrbeast(words, size, accent):
    f = FontSpec(cs.FONT_HEAVY, cs._MRBEAST_FONT_SIZE)
    max_width = size[0] - 2 * cs.MARGIN
    measure = lambda text: cs.drawn_words_width(text, f.pil, cs._MRBEAST_STROKE, upper=True)
    lines = cs.group_into_lines(words, f.pil, cs._MRBEAST_STROKE, max_width, measure)
    gap = _gap_tag(f, cs._MRBEAST_STROKE)
    cx, cy = size[0] // 2, size[1] / 2
    events = []
    for li, line in enumerate(lines):
        text = [w[0].upper() for w in line]
        start = line[0][1]
        end = line[-1][2] if li + 1 >= len(lines) else lines[li + 1][0][1]
        scale = cs.fit_scale(measure(" ".join(w[0] for w in line)), max_width)
        dy = _ink_center_offset(" ".join(text), f, cs._MRBEAST_STROKE) * scale
        events.append(_event(start, end, "M", f"{{\\an5\\pos({cx},{cy - dy:.1f}){_scale_tag(scale)}}}" + gap.join(_esc(t) for t in text)))
    return [_style("M", f, cs._MRBEAST_COLOR, cs._MRBEAST_STROKE_COLOR, cs._MRBEAST_STROKE)], events


def _hormozi(words, size, accent):
    f = FontSpec(cs.FONT_HEAVY, cs._HORMOZI_FONT_SIZE)
    chunks = cs.group_into_chunks(words, cs._HORMOZI_CHUNK_SIZE, f.pil, cs._HORMOZI_STROKE, size[0] - 2 * cs.MARGIN)
    cx, cy = size[0] // 2, size[1] / 2
    events = []
    for i, chunk in enumerate(chunks):
        text = " ".join(w[0].upper() for w in chunk)
        start, end = chunk[0][1], chunk[-1][2]
        color = cs._HORMOZI_COLORS[i % len(cs._HORMOZI_COLORS)]
        w_px, line_h, _ = cs._text_size(text, f.pil, cs._HORMOZI_STROKE)
        box_w, box_h = w_px + 34 * 2, line_h + 20 * 2
        scale = cs.fit_scale(box_w, size[0] - 2 * cs.MARGIN)
        box = (f"{{\\an5\\pos({cx},{cy:.1f}){_scale_tag(scale)}\\bord0\\shad0\\c{_tag_color(color)}\\1a{_tag_alpha(235)}\\p1}}"
               f"{_rounded_rect_path(box_w, box_h, 14)}{{\\p0}}")
        events.append(_event(start, end, "H", box, layer=0))
        dy = _ink_center_offset(text, f, cs._HORMOZI_STROKE) * scale
        events.append(_event(start, end, "H", f"{{\\an5\\pos({cx},{cy - dy:.1f}){_scale_tag(scale)}}}{_esc(text)}", layer=1))
    return [_style("H", f, cs._HORMOZI_TEXT, cs._HORMOZI_STROKE_COLOR, cs._HORMOZI_STROKE)], events


def _bounce(words, size, accent):
    f = FontSpec(cs.FONT_BOLD, cs._BOUNCE_FONT_SIZE)
    stroke_color = cs._parse_color(accent) or cs._BOUNCE_STROKE_COLOR
    cx, cy = size[0] // 2, size[1] / 2
    b = cs._BOUNCE_STROKE
    events = []
    for text, start, end in words:
        dur_ms = max(end - start, 0.05) * 1000
        third = dur_ms / 3
        t = text.upper()
        k = cs.fit_scale(cs._text_size(t, f.pil, b)[0] * 1.10, size[0] - 2 * cs.MARGIN)
        dy = _ink_center_offset(t, f, b) * k
        # 40% → 110% in the first third, settle to 100% by two thirds (cs._bounce_scale_factor);
        # the stroke scales with the word, as in moviepy's whole-image resize; k shrinks
        # the whole animation for a word too long to overshoot inside the frame
        anim = (f"\\fscx{40 * k:.1f}\\fscy{40 * k:.1f}\\bord{b * 0.4 * k:.1f}"
                f"\\t(0,{third:.0f},\\fscx{110 * k:.1f}\\fscy{110 * k:.1f}\\bord{b * 1.1 * k:.1f})"
                f"\\t({third:.0f},{2 * third:.0f},\\fscx{100 * k:.1f}\\fscy{100 * k:.1f}\\bord{b * k:.1f})")
        events.append(_event(start, start + dur_ms / 1000, "B", f"{{\\an5\\pos({cx},{cy - dy:.1f}){anim}}}{_esc(t)}"))
    return [_style("B", f, cs._BOUNCE_COLOR, stroke_color, b)], events


def _typewriter(words, size, accent):
    f = FontSpec(cs.FONT_MONO, cs._TYPEWRITER_FONT_SIZE)
    cursor = cs._parse_color(accent) or cs._TYPEWRITER_CURSOR
    lines = cs.group_into_lines(words, f.pil, 0, size[0] - 2 * cs.MARGIN, lambda t: cs.typewriter_drawn_width(t, f.pil))
    cx, cy = size[0] / 2, size[1] / 2
    pad = 20
    events = []
    cs_ = lambda t: round(t * 100) / 100  # ASS's own time resolution (centiseconds)
    for li, line in enumerate(lines):
        prefix = ""
        for i, (text, start, end) in enumerate(line):
            next_start = _next_start(lines, li, i, end)
            steps = max(len(text), 1)
            # Each letter step ends EXACTLY where the next begins, on the
            # centisecond grid, with no minimum duration: the old 50 ms floor
            # stretched 33 ms letter steps over the next one, and Whisper
            # word timings can overlap (a word "ends" after the next starts)
            # — both showed two versions of the line at once (doubled text).
            # a zero-length "word" (e.g. a « placed at the next word's start)
            # gets no step of its own: it appears together with the next word
            word_end = max(cs_(next_start), cs_(start))
            typing_end = min(cs_(end), word_end) if cs_(end) > cs_(start) else word_end
            bounds = [cs_(start + (typing_end - start) * k / steps) for k in range(steps)] + [word_end]
            for ci in range(1, steps + 1):
                partial = prefix + text[:ci]
                t0, t1 = bounds[ci - 1], bounds[ci]
                if t1 <= t0:
                    continue  # several letters within one centisecond: show the last one
                # same geometry as cs._typewriter_frame: an image as wide as
                # partial+"I" centered on screen, text from its left padding,
                # cursor 4 px after the text, as tall as the text line
                frame_w, line_h, _ = cs._text_size(partial + "I", f.pil, 0)
                left = cx - (frame_w + 2 * pad) / 2 + pad
                dy = _ink_center_offset(partial + "I", f, 0)
                events.append(_event(t0, t1, "T", f"{{\\an4\\pos({left:.1f},{cy - dy:.1f})}}{_esc(partial)}", min_dur=0))
                text_w = cs._text_size(partial, f.pil, 0)[0]
                events.append(_event(t0, t1, "T",
                                     f"{{\\an7\\pos({left + text_w + 4:.1f},{cy - line_h / 2:.1f})\\bord0\\shad0"
                                     f"\\c{_tag_color(cursor)}\\p1}}m 0 0 l 6 0 l 6 {line_h} l 0 {line_h}{{\\p0}}", min_dur=0))
            prefix += text + " "
    return [_style("T", f, cs._TYPEWRITER_COLOR)], events


def _minimal(words, size, accent):
    f = FontSpec(cs.FONT_SERIF, cs._MINIMAL_FONT_SIZE)
    measure = lambda text: cs._minimal_text_width(text, f.pil)
    lines = cs.group_into_lines(words, f.pil, 0, size[0] - 2 * cs.MARGIN, measure)
    cx, cy = size[0] // 2, size[1] / 2
    events = []
    for li, line in enumerate(lines):
        text = " ".join(w[0] for w in line).upper()
        start = line[0][1]
        end = line[-1][2] if li + 1 >= len(lines) else lines[li + 1][0][1]
        fade_ms = min(0.4, max(end - start, 0.05) / 2) * 1000
        # moviepy steps each letter by its INK width + tracking; give the line
        # the per-letter spacing that yields the same total width
        n = max(len(text) - 1, 1)
        advance = sum(f.pil.getlength(ch) for ch in text)
        spacing = (cs._minimal_text_width(text, f.pil) - advance) / n
        dy = _ink_center_offset(text, f, 0)
        events.append(_event(start, end, "N", f"{{\\an5\\pos({cx},{cy - dy:.1f})\\fsp{spacing:.2f}\\fad({fade_ms:.0f},0)}}{_esc(text)}"))
    return [_style("N", f, cs._MINIMAL_COLOR)], events


BUILDERS = {"karaoke": _karaoke, "mrbeast": _mrbeast, "hormozi": _hormozi,
            "bounce": _bounce, "typewriter": _typewriter, "minimal": _minimal}
FONT_FILES = [cs.FONT_BOLD, cs.FONT_HEAVY, cs.FONT_MONO, cs.FONT_SERIF]


def build_ass(words: WordTimings, size, caption_style: str = "karaoke", accent_color: str = None) -> str:
    styles, events = BUILDERS[caption_style](words, size, accent_color)
    return _header(size, styles) + "\n".join(events) + "\n"


def build_karaoke_ass(words: WordTimings, size, accent_color: str = None) -> str:
    return build_ass(words, size, "karaoke", accent_color)


# ---------------------------------------------------------------------------
# Audio: ducked, faded, crossfade-looped music
# ---------------------------------------------------------------------------

def music_copies_needed(music_dur: float, total: float) -> int:
    if music_dur >= total:
        return 1
    xf = min(LOOP_CROSSFADE, music_dur / 4)
    return 1 + math.ceil((total - music_dur) / (music_dur - xf))


def _music_filters(music_inputs: List[int], music_dur: float, total: float) -> List[str]:
    """Filters producing [mus]: the music (several copies chained with a
    crossfade if it's shorter than the video), stereo, at MUSIC_LEVEL,
    faded in and out."""
    to_stereo = "aresample=44100,aformat=channel_layouts=stereo"
    f = [f"[{idx}:a]{to_stereo}[m{n}]" for n, idx in enumerate(music_inputs)]
    xf = min(LOOP_CROSSFADE, music_dur / 4)
    last = "m0"
    for n in range(1, len(music_inputs)):
        f.append(f"[{last}][m{n}]acrossfade=d={xf:.2f}:c1=tri:c2=tri[mx{n}]")
        last = f"mx{n}"
    fade_out_at = max(0.0, total - MUSIC_FADE_OUT)
    f.append(f"[{last}]atrim=0:{total:.3f},volume={MUSIC_LEVEL},"
             f"afade=t=in:d={MUSIC_FADE_IN},afade=t=out:st={fade_out_at:.3f}:d={MUSIC_FADE_OUT}[mus]")
    return f


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def _escape_filter_path(path: str) -> str:
    # inside a filtergraph: escape \ : ' (spaces are fine)
    return path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def render_video_ffmpeg(
    narration_mp3: str, words: WordTimings, bg_video_path: str, bg_music_path: str, out_path: str,
    music_volume: float = 0.15, size=(1080, 1920), caption_style: str = "karaoke", caption_color: str = None,
    frame_mode: str = "fill", rounded_corners: bool = False, border_image_path: str = None,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> str:
    """music_volume is kept for signature compatibility with the moviepy
    path; the ffmpeg path uses MUSIC_LEVEL + ducking instead."""
    from test3_script import compute_frame_scale, get_video_dimensions, rounded_corner_mask, ROUNDED_CORNER_RADIUS_RATIO

    if caption_style not in BUILDERS:
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
    try:
        ass_path = os.path.join(work, "captions.ass")
        with open(ass_path, "w", encoding="utf-8") as fh:
            fh.write(build_ass(words, size, caption_style, caption_color))
        # libass reads ONE fonts dir: gather the caption fonts in it
        fonts_dir = os.path.join(work, "fonts")
        os.makedirs(fonts_dir)
        for font_file in FONT_FILES:
            if os.path.exists(font_file):
                shutil.copy(font_file, fonts_dir)

        music_dur = media_duration(bg_music_path)
        copies = music_copies_needed(music_dur, total)
        inputs = ["-stream_loop", "-1", "-i", bg_video_path,   # 0: background video, looped
                  "-i", narration_mp3]                          # 1: narration
        music_inputs = []
        for n in range(copies):
            music_inputs.append(2 + n)
            inputs += ["-i", bg_music_path]                     # 2..: music copies (crossfaded)
        next_input = 2 + copies

        filters = [f"[0:v]fps=25,scale={sw}:{sh}:flags=bicubic,setsar=1[vid]"]
        force_black = rounded_corners and frame_mode in ("fill", None)
        if rounded_corners:
            cw, ch = min(sw, tw), min(sh, th)
            if (cw, ch) != (sw, sh):
                filters.append(f"[vid]crop={cw}:{ch}[vid]")
            mask_path = os.path.join(work, "mask.png")
            radius = int(min(cw, ch) * ROUNDED_CORNER_RADIUS_RATIO)
            Image.fromarray(rounded_corner_mask(cw, ch, radius)).convert("L").save(mask_path)
            inputs += ["-loop", "1", "-i", mask_path]
            filters.append(f"[{next_input}:v]format=gray[mask]")
            filters.append("[vid]format=yuva420p[vida];[vida][mask]alphamerge[vid]")
            next_input += 1
        if has_border and not force_black:
            inputs += ["-loop", "1", "-i", border_image_path]
            filters.append(f"[{next_input}:v]scale={tw}:{th},setsar=1,format=yuv420p[base]")
            next_input += 1
        else:
            filters.append(f"color=c=black:s={tw}x{th}:r=25,format=yuv420p[base]")
        filters.append(
            f"[base][vid]overlay=(W-w)/2:(H-h)/2:shortest=0:eof_action=repeat,"
            f"subtitles='{_escape_filter_path(ass_path)}':fontsdir='{_escape_filter_path(fonts_dir)}',format=yuv420p[v]")

        # Narration is mono: convert to stereo the way moviepy does when it
        # reads it (a raw mono mix came out 3 dB louder than the moviepy render).
        # One copy is mixed, the other drives the music's ducking.
        filters.append("[1:a]aresample=44100,aformat=channel_layouts=stereo,asplit=2[nar][key]")
        filters += _music_filters(music_inputs, music_dur, total)
        d = DUCK
        filters.append(f"[mus][key]sidechaincompress=threshold={d['threshold']}:ratio={d['ratio']}:"
                       f"attack={d['attack']}:release={d['release']}[ducked]")
        filters.append("[nar][ducked]amix=inputs=2:duration=first:normalize=0[a]")

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
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if progress_cb:
        progress_cb(1.0)
    return out_path
