#!/usr/bin/env python3
"""
Caption styles - pluggable renderers for the karaoke-caption layer in
video_composer.py. Each style is a small set of (font, layout, per-word
timing) rules; video_composer picks one by name via `caption_style` and
calls its `build_clips(words, size)` to get the list of moviepy ImageClips
to composite over the background, exactly the same shape as the previous
hardcoded karaoke-only renderer.

Adding a new style: write one module-level function following the pattern
below and register it in STYLES. Nothing else in the pipeline needs to
change — video_composer.py only ever calls STYLES[name].
"""

from typing import List, Tuple
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip

from generative.voice_generator import WordTimings

FONT_DIR = "/usr/share/fonts/truetype"
FONT_BOLD = f"{FONT_DIR}/dejavu/DejaVuSans-Bold.ttf"
FONT_HEAVY = f"{FONT_DIR}/freefont/FreeSansBold.ttf"
FONT_MONO = f"{FONT_DIR}/dejavu/DejaVuSansMono.ttf"
FONT_SERIF = "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"

MARGIN = 70  # safe-zone margin each side, in px, at the 1080-wide reference size
HARD_BREAK_CHARS = (".", "!", "?", ":")

_measure_img = Image.new("RGBA", (10, 10))
_measure = ImageDraw.Draw(_measure_img)


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _parse_color(hex_str, alpha: int = 255, default=None):
    """"#rrggbb" (as sent by an HTML <input type="color">) -> (r,g,b,a).
    Falls back to `default` on anything missing/malformed, so a bad or
    absent value never breaks rendering."""
    if not hex_str or not isinstance(hex_str, str):
        return default
    h = hex_str.lstrip("#")
    if len(h) != 6:
        return default
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)
    except ValueError:
        return default


# Styles whose accent color the user can override (a chip fill, a stroke, a
# cursor) — everything else ignores the accent_color argument it's still
# passed, for one uniform call signature across every style.
CUSTOMIZABLE_COLOR_STYLES = {"karaoke", "bounce", "typewriter"}


def _text_size(text: str, font: ImageFont.FreeTypeFont, stroke_width: int = 0):
    bbox = _measure.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    return bbox[2] - bbox[0], bbox[3] - bbox[1], bbox[1]


# ---------------------------------------------------------------------------
# Shared word-grouping (same "don't split mid-clause" logic for every style
# that shows a full line rather than a tiny chunk)
# ---------------------------------------------------------------------------

def group_into_blocks(words: WordTimings):
    blocks, current = [], []
    for w in words:
        current.append(w)
        if w[0].rstrip("\"')]").endswith(HARD_BREAK_CHARS):
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def wrap_block(block, font, stroke_width, max_width: int, measure_fn=None):
    """measure_fn(text) -> px overrides the default plain-text measurement —
    needed by styles (e.g. minimal's letter-tracking) that render wider than
    a plain _text_size call would suggest, so wrapping doesn't under-count
    and let a line overflow once actually drawn."""
    measure = measure_fn or (lambda text: _text_size(text, font, stroke_width)[0])
    lines, current = [], []
    for w in block:
        candidate = current + [w]
        text = " ".join(x[0] for x in candidate)
        w_px = measure(text)
        if w_px <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = [w]
    if current:
        lines.append(current)
    return lines


def group_into_lines(words: WordTimings, font, stroke_width, max_width: int, measure_fn=None):
    lines = []
    for block in group_into_blocks(words):
        lines.extend(wrap_block(block, font, stroke_width, max_width, measure_fn))
    return lines


def group_into_chunks(words: WordTimings, chunk_size: int, font=None, stroke_width: int = 0, max_width: int = None):
    """N-words-at-a-time grouping (Hormozi-style) — ignores punctuation
    boundaries on purpose, since the whole point is a fast, punchy rhythm
    rather than clause-aware line wrapping. Still width-aware when
    font/max_width are given: a chunk drops to fewer words (down to 1)
    rather than ever overflowing the frame on a long word."""
    if font is None or max_width is None:
        return [words[i:i + chunk_size] for i in range(0, len(words), chunk_size)]

    chunks, i = [], 0
    while i < len(words):
        size = min(chunk_size, len(words) - i)
        while size > 1:
            text = " ".join(w[0].upper() for w in words[i:i + size])
            w_px, _, _ = _text_size(text, font, stroke_width)
            if w_px <= max_width:
                break
            size -= 1
        chunks.append(words[i:i + size])
        i += size
    return chunks


def _clip_from_array(arr: np.ndarray, start: float, dur: float) -> ImageClip:
    return ImageClip(arr).set_start(start).set_duration(max(dur, 0.05)).set_position("center")


# ---------------------------------------------------------------------------
# Karaoke / Active Highlight (the original, current default) — full line
# stays on screen, the spoken word turns yellow.
# ---------------------------------------------------------------------------

_KARAOKE_FONT_SIZE = 64
_KARAOKE_STROKE = 6
_KARAOKE_HIGHLIGHT = (255, 224, 0, 255)
_KARAOKE_TEXT = (255, 255, 255, 255)
_KARAOKE_STROKE_COLOR = (0, 0, 0, 255)


def _karaoke_line_frame(line, highlight_idx, font, highlight_color=_KARAOKE_HIGHLIGHT) -> np.ndarray:
    space_w, _, _ = _text_size(" ", font, _KARAOKE_STROKE)
    word_sizes = [_text_size(w[0], font, _KARAOKE_STROKE) for w in line]
    total_w = sum(s[0] for s in word_sizes) + space_w * (len(line) - 1)
    _, line_h, y_offset = _text_size(" ".join(w[0] for w in line), font, _KARAOKE_STROKE)

    pad = 20
    img = Image.new("RGBA", (total_w + pad * 2, line_h + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = pad
    for i, ((text, _, _), (w_px, _, _)) in enumerate(zip(line, word_sizes)):
        color = highlight_color if i == highlight_idx else _KARAOKE_TEXT
        d.text((x, pad - y_offset), text, font=font, fill=color, stroke_width=_KARAOKE_STROKE, stroke_fill=_KARAOKE_STROKE_COLOR)
        x += w_px + space_w
    return np.array(img)


def karaoke_build_clips(words: WordTimings, size, accent_color: str = None) -> List[ImageClip]:
    font = _font(FONT_BOLD, _KARAOKE_FONT_SIZE)
    highlight_color = _parse_color(accent_color) or _KARAOKE_HIGHLIGHT
    max_width = size[0] - 2 * MARGIN
    lines = group_into_lines(words, font, _KARAOKE_STROKE, max_width)
    clips = []
    for li, line in enumerate(lines):
        for i, (text, start, end) in enumerate(line):
            next_start = line[i + 1][1] if i + 1 < len(line) else (lines[li + 1][0][1] if li + 1 < len(lines) else end)
            clips.append(_clip_from_array(_karaoke_line_frame(line, i, font, highlight_color), start, next_start - start))
    return clips


def karaoke_preview_frame(size, accent_color: str = None) -> Image.Image:
    words = _SAMPLE_WORDS
    font = _font(FONT_BOLD, _KARAOKE_FONT_SIZE)
    highlight_color = _parse_color(accent_color) or _KARAOKE_HIGHLIGHT
    max_width = size[0] - 2 * MARGIN
    lines = group_into_lines(words, font, _KARAOKE_STROKE, max_width)
    arr = _karaoke_line_frame(lines[0], 2, font, highlight_color)  # highlight the 3rd word, mid-sentence
    return Image.fromarray(arr)


# ---------------------------------------------------------------------------
# MrBeast — thick white/yellow text, ultra-heavy black stroke, centered
# bottom-third, all caps.
# ---------------------------------------------------------------------------

_MRBEAST_FONT_SIZE = 72
_MRBEAST_STROKE = 14
_MRBEAST_COLOR = (255, 255, 255, 255)
_MRBEAST_STROKE_COLOR = (0, 0, 0, 255)


def _mrbeast_line_frame(line, font) -> np.ndarray:
    space_w, _, _ = _text_size(" ", font, _MRBEAST_STROKE)
    word_sizes = [_text_size(w[0].upper(), font, _MRBEAST_STROKE) for w in line]
    total_w = sum(s[0] for s in word_sizes) + space_w * (len(line) - 1)
    _, line_h, y_offset = _text_size(" ".join(w[0].upper() for w in line), font, _MRBEAST_STROKE)
    pad = 24
    img = Image.new("RGBA", (total_w + pad * 2, line_h + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = pad
    for (text, _, _), (w_px, _, _) in zip(line, word_sizes):
        d.text((x, pad - y_offset), text.upper(), font=font, fill=_MRBEAST_COLOR, stroke_width=_MRBEAST_STROKE, stroke_fill=_MRBEAST_STROKE_COLOR)
        x += w_px + space_w
    return np.array(img)


def mrbeast_build_clips(words: WordTimings, size) -> List[ImageClip]:
    font = _font(FONT_HEAVY, _MRBEAST_FONT_SIZE)
    max_width = size[0] - 2 * MARGIN
    lines = group_into_lines(words, font, _MRBEAST_STROKE, max_width)
    clips = []
    for li, line in enumerate(lines):
        start = line[0][1]
        end = line[-1][2] if li + 1 >= len(lines) else lines[li + 1][0][1]
        clips.append(_clip_from_array(_mrbeast_line_frame(line, font), start, end - start))
    return clips


def mrbeast_preview_frame(size) -> Image.Image:
    font = _font(FONT_HEAVY, _MRBEAST_FONT_SIZE)
    max_width = size[0] - 2 * MARGIN
    lines = group_into_lines(_SAMPLE_WORDS, font, _MRBEAST_STROKE, max_width)
    return Image.fromarray(_mrbeast_line_frame(lines[0], font))


# ---------------------------------------------------------------------------
# Hormozi — 1-3 words on screen at a time, huge, bold, colored highlight
# "chip" behind the text, exactly as spoken.
# ---------------------------------------------------------------------------

_HORMOZI_FONT_SIZE = 92
_HORMOZI_STROKE = 10
_HORMOZI_COLORS = [(255, 224, 0, 255), (74, 222, 128, 255), (248, 113, 113, 255)]  # yellow/green/red, rotate per chunk
_HORMOZI_TEXT = (255, 255, 255, 255)
_HORMOZI_STROKE_COLOR = (0, 0, 0, 255)
_HORMOZI_CHUNK_SIZE = 2


def _hormozi_chunk_frame(chunk, color, font) -> np.ndarray:
    text = " ".join(w[0].upper() for w in chunk)
    w_px, line_h, y_offset = _text_size(text, font, _HORMOZI_STROKE)
    pad_x, pad_y = 34, 20
    box_w, box_h = w_px + pad_x * 2, line_h + pad_y * 2
    img = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, box_w, box_h], radius=14, fill=(color[0], color[1], color[2], 235))
    d.text((pad_x, pad_y - y_offset), text, font=font, fill=_HORMOZI_TEXT, stroke_width=_HORMOZI_STROKE, stroke_fill=_HORMOZI_STROKE_COLOR)
    return np.array(img)


def hormozi_build_clips(words: WordTimings, size) -> List[ImageClip]:
    font = _font(FONT_HEAVY, _HORMOZI_FONT_SIZE)
    max_width = size[0] - 2 * MARGIN
    chunks = group_into_chunks(words, _HORMOZI_CHUNK_SIZE, font, _HORMOZI_STROKE, max_width)
    clips = []
    for i, chunk in enumerate(chunks):
        start, end = chunk[0][1], chunk[-1][2]
        color = _HORMOZI_COLORS[i % len(_HORMOZI_COLORS)]
        clips.append(_clip_from_array(_hormozi_chunk_frame(chunk, color, font), start, end - start))
    return clips


def hormozi_preview_frame(size) -> Image.Image:
    font = _font(FONT_HEAVY, _HORMOZI_FONT_SIZE)
    max_width = size[0] - 2 * MARGIN
    chunks = group_into_chunks(_SAMPLE_WORDS, _HORMOZI_CHUNK_SIZE, font, _HORMOZI_STROKE, max_width)
    return Image.fromarray(_hormozi_chunk_frame(chunks[1], _HORMOZI_COLORS[1], font))


# ---------------------------------------------------------------------------
# Spring / Bounce Pop-In — one word at a time, scaled 0% -> 110% -> 100% as
# it appears. build_clips animates via moviepy's per-frame resize; the
# preview just captures the 110% overshoot instant, the style's signature.
# ---------------------------------------------------------------------------

_BOUNCE_FONT_SIZE = 88
_BOUNCE_STROKE = 10
_BOUNCE_COLOR = (255, 255, 255, 255)
_BOUNCE_STROKE_COLOR = (109, 141, 253, 255)  # accent blue, matches the app's own theme


def _bounce_word_frame(word_text, font, stroke_color=_BOUNCE_STROKE_COLOR) -> np.ndarray:
    text = word_text.upper()
    w_px, line_h, y_offset = _text_size(text, font, _BOUNCE_STROKE)
    pad = 24
    img = Image.new("RGBA", (w_px + pad * 2, line_h + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((pad, pad - y_offset), text, font=font, fill=_BOUNCE_COLOR, stroke_width=_BOUNCE_STROKE, stroke_fill=stroke_color)
    return np.array(img)


def _bounce_scale_factor(t: float, dur: float) -> float:
    """40% -> 110% in the first third of the word's duration, settle to 100%
    by two-thirds, hold — a simple overshoot spring without needing an
    easing library. Starts at 40%, never 0%: a resize factor of exactly 0
    is an invalid (zero-size) frame for the video encoder, and a word
    popping in from "already readable but small" looks better anyway than
    one appearing from nothing then instantly legible."""
    third = max(dur / 3, 0.01)
    if t < third:
        return 0.4 + 0.70 * (t / third)
    if t < 2 * third:
        settle = (t - third) / third
        return 1.10 - 0.10 * settle
    return 1.0


def bounce_build_clips(words: WordTimings, size, accent_color: str = None) -> List[ImageClip]:
    font = _font(FONT_BOLD, _BOUNCE_FONT_SIZE)
    stroke_color = _parse_color(accent_color) or _BOUNCE_STROKE_COLOR
    clips = []
    for text, start, end in words:
        dur = max(end - start, 0.05)
        arr = _bounce_word_frame(text, font, stroke_color)
        base = ImageClip(arr).set_start(start).set_duration(dur).set_position("center")
        clip = base.resize(lambda t, d=dur: _bounce_scale_factor(t, d))
        clips.append(clip)
    return clips


def bounce_preview_frame(size, accent_color: str = None) -> Image.Image:
    font = _font(FONT_BOLD, _BOUNCE_FONT_SIZE)
    stroke_color = _parse_color(accent_color) or _BOUNCE_STROKE_COLOR
    arr = _bounce_word_frame(_SAMPLE_WORDS[3][0], font, stroke_color)  # the word shown mid-overshoot
    img = Image.fromarray(arr)
    return img.resize((int(img.width * 1.10), int(img.height * 1.10)))


# ---------------------------------------------------------------------------
# Typewriter — letters reveal one at a time within each word's own timing
# window (Whisper only gives per-WORD timestamps, so letters are spaced
# evenly across that window), plus a blinking cursor bar.
# ---------------------------------------------------------------------------

_TYPEWRITER_FONT_SIZE = 58
_TYPEWRITER_COLOR = (255, 255, 255, 255)
_TYPEWRITER_CURSOR = (255, 224, 0, 255)


def _typewriter_frame(revealed_text, show_cursor, font, cursor_color=_TYPEWRITER_CURSOR) -> np.ndarray:
    w_px, line_h, y_offset = _text_size(revealed_text + "I", font, 0)  # "I" reserves cursor width even at revealed_text=""
    pad = 20
    img = Image.new("RGBA", (w_px + pad * 2, line_h + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((pad, pad - y_offset), revealed_text, font=font, fill=_TYPEWRITER_COLOR)
    if show_cursor:
        text_w, _, _ = _text_size(revealed_text, font, 0)
        cursor_x = pad + text_w + 4
        d.rectangle([cursor_x, pad, cursor_x + 6, pad + line_h], fill=cursor_color)
    return np.array(img)


def typewriter_build_clips(words: WordTimings, size, accent_color: str = None) -> List[ImageClip]:
    """Builds up the sentence-so-far one word at a time (same "stays on
    screen, grows" idea as karaoke) but with the CURRENT word's letters
    typed in progressively across its own duration, monospace font."""
    font = _font(FONT_MONO, _TYPEWRITER_FONT_SIZE)
    cursor_color = _parse_color(accent_color) or _TYPEWRITER_CURSOR
    max_width = size[0] - 2 * MARGIN
    lines = group_into_lines(words, font, 0, max_width)
    clips = []
    for li, line in enumerate(lines):
        prefix = ""
        for i, (text, start, end) in enumerate(line):
            next_start = line[i + 1][1] if i + 1 < len(line) else (lines[li + 1][0][1] if li + 1 < len(lines) else end)
            # Each letter step ends exactly where the next begins, with no 50 ms
            # floor: the floor stretched short letter steps over the next one,
            # and word timings can overlap (a word "ends" after the next starts)
            # — both showed two versions of the line at once (doubled text).
            word_end = max(next_start, start)  # a zero-length "word" (e.g. «) appears with the next one
            typing_end = min(end, word_end) if end > start else word_end
            steps = max(len(text), 1)
            bounds = [start + (typing_end - start) * k / steps for k in range(steps)] + [word_end]
            for ci in range(1, steps + 1):
                partial = prefix + text[:ci]
                clip_start, clip_end = bounds[ci - 1], bounds[ci]
                if clip_end <= clip_start:
                    continue
                arr = _typewriter_frame(partial, True, font, cursor_color)
                clips.append(ImageClip(arr).set_start(clip_start).set_duration(clip_end - clip_start).set_position("center"))
            prefix += text + " "
    return clips


def typewriter_preview_frame(size, accent_color: str = None) -> Image.Image:
    font = _font(FONT_MONO, _TYPEWRITER_FONT_SIZE)
    cursor_color = _parse_color(accent_color) or _TYPEWRITER_CURSOR
    partial = " ".join(w[0] for w in _SAMPLE_WORDS[:2]) + " " + _SAMPLE_WORDS[2][0][:3]
    return Image.fromarray(_typewriter_frame(partial, True, font, cursor_color))


# ---------------------------------------------------------------------------
# Minimalist / Cinematic Fade — thin serif, wide letter-tracking, low-key.
# ---------------------------------------------------------------------------

_MINIMAL_FONT_SIZE = 54
_MINIMAL_COLOR = (255, 255, 255, 235)
_MINIMAL_TRACKING = 6  # extra px between letters


def _minimal_text_width(text, font) -> int:
    """The real rendered width including letter-tracking -- used both to
    size the canvas and (via measure_fn) to wrap lines, so a line that
    "fits" is never wider once actually drawn with tracking applied."""
    upper = text.upper()
    width = sum(_text_size(ch, font, 0)[0] for ch in upper)
    return width + _MINIMAL_TRACKING * max(len(upper) - 1, 0)


def _minimal_text_frame(text, font) -> np.ndarray:
    w_px = _minimal_text_width(text, font)
    _, line_h, y_offset = _text_size(text.upper(), font, 0)
    pad = 20
    img = Image.new("RGBA", (w_px + pad * 2, line_h + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = pad
    for ch in text.upper():
        d.text((x, pad - y_offset), ch, font=font, fill=_MINIMAL_COLOR)
        ch_w, _, _ = _text_size(ch, font, 0)
        x += ch_w + _MINIMAL_TRACKING
    return np.array(img)


def minimal_build_clips(words: WordTimings, size) -> List[ImageClip]:
    font = _font(FONT_SERIF, _MINIMAL_FONT_SIZE)
    max_width = size[0] - 2 * MARGIN
    measure_fn = lambda text: _minimal_text_width(text, font)
    lines = group_into_lines(words, font, 0, max_width, measure_fn)
    clips = []
    for li, line in enumerate(lines):
        text = " ".join(w[0] for w in line)
        start = line[0][1]
        end = line[-1][2] if li + 1 >= len(lines) else lines[li + 1][0][1]
        arr = _minimal_text_frame(text, font)
        dur = max(end - start, 0.05)
        fade_dur = min(0.4, dur / 2)
        base = ImageClip(arr).set_start(start).set_duration(dur).set_position("center")
        clips.append(base.crossfadein(fade_dur))
    return clips


def minimal_preview_frame(size) -> Image.Image:
    font = _font(FONT_SERIF, _MINIMAL_FONT_SIZE)
    max_width = size[0] - 2 * MARGIN
    measure_fn = lambda text: _minimal_text_width(text, font)
    lines = group_into_lines(_SAMPLE_WORDS, font, 0, max_width, measure_fn)
    text = " ".join(w[0] for w in lines[0])
    return Image.fromarray(_minimal_text_frame(text, font))


# ---------------------------------------------------------------------------

_SAMPLE_WORDS: WordTimings = [
    ("Ce", 0.0, 0.3), ("détail", 0.3, 0.8), ("change", 0.8, 1.3),
    ("absolument", 1.3, 2.0), ("tout.", 2.0, 2.4),
]

STYLES = {
    "karaoke": karaoke_build_clips,
    "mrbeast": mrbeast_build_clips,
    "hormozi": hormozi_build_clips,
    "bounce": bounce_build_clips,
    "typewriter": typewriter_build_clips,
    "minimal": minimal_build_clips,
}

PREVIEWS = {
    "karaoke": karaoke_preview_frame,
    "mrbeast": mrbeast_preview_frame,
    "hormozi": hormozi_preview_frame,
    "bounce": bounce_preview_frame,
    "typewriter": typewriter_preview_frame,
    "minimal": minimal_preview_frame,
}
