"""
The adaptation render, in one ffmpeg pass.

Every sentence of the script plays over one clip; the clip window is chosen
so its crash/peak lands ~40 % into the sentence (the first one within the
first second: the hook; the last one late, just before the video loops).

    picture : clips in a rounded box on black (near-square clips fill it,
              wide/tall ones sit on a blurred copy of themselves), a short
              zoom + shake on each crash, a banner per clip, the credit line
    text    : big captions under the box, 1-3 words, one keyword coloured
              (yellow / pink / green, one colour per sentence)
    sound   : the narration with its pauses tightened, loudness-normalised;
              a music bed; each clip's own crash sound (or a borrowed one
              when the clip's sound has speech in it)
"""

import json
import math
import os
import re
import subprocess
import threading
import unicodedata
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from adaptation import sfx
from adaptation.langs import FONTS_DIR, font_path, lang as lang_of

W, H, FPS = 1080, 1920, 30
BOX_X, BOX_Y, BOX_W, BOX_H = 30, 380, 1020, 980
BANNER_Y, CREDIT_Y, CAPTION_Y = 220, 150, 1500
GAP = 0.18                                         # pause kept between two sentences
GAP_MIN, GAP_MAX = 0.08, 0.40                      # the pause may move within this to put the cut on a beat
KEY_COLORS = ["#FFD60A", "#FF4D8D", "#4ADE80"]     # yellow, pink, green — one per sentence

# A channel's look (Réglages → Voix): its banners and captions, the same on every video it publishes.
STYLES = {
    "classique": {"label": "Classique", "box": (14, 14, 16, 240), "border": (255, 255, 255, 220), "head": "white",
                  "key": "#FFD60A", "words": ["#FFD60A", "#FF4D8D", "#4ADE80"], "text": "#FFFFFF", "outline": "#000000"},
    "flamme": {"label": "Flamme", "box": (200, 24, 36, 245), "border": (255, 214, 10, 255), "head": "white",
               "key": "#FFD60A", "words": ["#FFB020", "#FF4D3D", "#FFD60A"], "text": "#FFFFFF", "outline": "#000000"},
    "neon": {"label": "Néon", "box": (8, 8, 20, 240), "border": (0, 229, 255, 255), "head": "white",
             "key": "#00E5FF", "words": ["#00E5FF", "#FF3DF5", "#B6FF3B"], "text": "#FFFFFF", "outline": "#000000"},
    "or": {"label": "Or", "box": (16, 22, 40, 245), "border": (232, 190, 92, 255), "head": "white",
           "key": "#F2C94C", "words": ["#F2C94C", "#F2994A", "#FFFFFF"], "text": "#FFFFFF", "outline": "#101828"},
    "clair": {"label": "Clair", "box": (255, 255, 255, 245), "border": (20, 20, 20, 255), "head": "#111111",
              "key": "#2563EB", "words": ["#60A5FA", "#F472B6", "#34D399"], "text": "#FFFFFF", "outline": "#0B1220"},
}


def style_of(name: Optional[str]) -> Dict:
    return STYLES.get(name or "", STYLES["classique"])


def style_preview(name: str, lang: Dict, path: str) -> str:
    """A banner and a caption line drawn in a style, on a dark picture — what
    the settings show next to the choice."""
    st = style_of(name)
    rtl = lang["rtl"]
    banner_text = "إطارات : لغز التجعد" if rtl else "PNEUS : DÉFORMATION"
    words = (["لماذا", "تتجعد", "الإطارات؟"] if rtl else ["POURQUOI", "LE PNEU", "SE PLISSE ?"])
    img = Image.new("RGBA", (W, 560), (34, 38, 46, 255))
    for y in range(560):                                        # a soft vertical gradient, like a dim picture
        ImageDraw.Draw(img).line([(0, y), (W, y)], fill=(30 + y // 20, 34 + y // 22, 44 + y // 18, 255))
    tmp = path + ".banner.png"
    banner_png(banner_text, tmp, lang, st)
    img.alpha_composite(Image.open(tmp).convert("RGBA"), (0, 30))
    os.remove(tmp)
    d = ImageDraw.Draw(img)
    kw = {"direction": "rtl", "language": "ar"} if rtl else {}
    cols = [st["text"], st["words"][0], st["text"]]
    for size in (96, 86, 76, 68, 60):                          # the line fits the picture
        font = ImageFont.truetype(font_path(lang["banner_font"]), size)
        widths = [d.textlength(w + " ", font=font, **kw) for w in words]
        if sum(widths) <= W - 120:
            break
    x = (W - sum(widths)) / 2
    order = list(zip(words, cols, widths))[::-1] if rtl else list(zip(words, cols, widths))
    for w, col, wd in order:
        d.text((x, 410), w, font=font, fill=col, anchor="lm", stroke_width=7, stroke_fill=st["outline"], **kw)
        x += wd
    img.convert("RGB").resize((W // 2, 280)).save(path, quality=88)
    return path
BANNER_KEY = "#FFD60A"
EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
MUSIC_GAIN = 0.16                                  # under a -16 LUFS voice
MUSIC_OUTRO = 0.32                                 # +6 dB once the last word is said (a usual outro swell)
OUTRO_S, OUTRO_RISE = 0.9, 0.45                    # seconds of picture after the last word; how fast it rises
SFX_GAIN = 0.55


class RenderError(RuntimeError):
    pass


# --------------------------------------------------------------- timeline

def build_timeline(passages: List[Dict], clips: Dict[str, Dict],
                   effects: Optional[List[Optional[Dict]]] = None,
                   beats: Optional[List[float]] = None) -> Tuple[List[Dict], float]:
    """One segment per sentence: where its voice is cut from (va..vb), where
    it sits in the output, and which part of its clip plays under it.
    effects (one per passage, see adaptation/effects.py) change how the clip
    plays: s["fx"] and s["pieces"], the time map every overlay follows."""
    from adaptation import effects as E
    segs, t = [], 0.0
    for k, p in enumerate(passages):
        a, b = max(0.0, p["start"] - 0.04), p["end"] + 0.10
        gap = GAP
        if beats and k < len(passages) - 1:     # the cut to the next clip lands on a beat of the music, when one is near
            near = [bt - (t + b - a) for bt in beats if GAP_MIN <= bt - (t + b - a) <= GAP_MAX]
            if near:
                gap = min(near, key=lambda g: abs(g - GAP))
        if k == len(passages) - 1:      # after the last word: a short outro, the music up (see render)
            gap += OUTRO_S
        dur = (b - a) + gap
        c = clips[p["clip"]]
        fx = (effects or [None] * (k + 1))[k] if k < len(effects or []) else None
        last = k == len(passages) - 1
        frac = 0.12 if k == 0 else (0.80 if last else 0.40)
        lead = min(0.9, dur * frac) if k == 0 else dur * frac
        need = max(0.5, dur - E.extra(fx))            # a ramp or a freeze shows less of the clip
        ws = min(max(c["start"], c["impact"] - lead), max(c["start"], c["end"] - need))
        s = {"k": k, "clip": p["clip"], "va": a, "vb": b, "out": t, "dur": dur, "ws": ws}
        s["fx"] = E.fit(c, s, fx)
        s["pieces"] = E.pieces(c, s)
        s["impact_out"] = t + E.out_at(s["pieces"], c["impact"])
        segs.append(s)
        t += dur
    return segs, t


def beats_of(music: str, start: float, length: float) -> List[float]:
    """The music's beats in video time (0 = the video's start): spectral flux,
    the tempo by autocorrelation (70-170 BPM), the phase that fits it best.
    Empty when no steady pulse is found (measured on the channels' tracks:
    afrobeat 123 BPM, lo-fi 144, ballad 76; a plain energy curve missed them)."""
    import numpy as np
    sr, hop = 11025, 128
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{length + 1:.3f}", "-i", music,
                          "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"], capture_output=True).stdout
    y = np.frombuffer(raw, np.float32)
    if len(y) < sr * 4:
        return []
    n = len(y) // hop
    mag = np.log1p(np.abs(np.fft.rfft(y[:n * hop].reshape(n, hop) * np.hanning(hop), axis=1)) * 10)
    flux = np.maximum(np.diff(mag, axis=0, prepend=mag[:1]), 0).sum(1)
    flux -= flux.mean()
    fps = sr / hop
    lags = list(range(int(fps * 60 / 170), int(fps * 60 / 70) + 1))
    ac = np.array([np.dot(flux[:-l], flux[l:]) / (n - l) for l in lags])
    if not len(ac) or ac.max() / (np.dot(flux, flux) / n + 1e-9) < 0.3:
        return []                       # no steady pulse (an ambient pad): cuts stay where the voice puts them
    i = int(ac.argmax())
    period = float(lags[i])
    if 0 < i < len(ac) - 1:             # between two lags: the peak of the parabola through them
        den = ac[i - 1] - 2 * ac[i] + ac[i + 1]
        if den < 0:
            period += 0.5 * (ac[i - 1] - ac[i + 1]) / den
    count = int(n / period)
    phase = max(range(int(period)), key=lambda ph: float(sum(flux[min(n - 1, int(round(ph + j * period)))]
                                                            for j in range(count))))
    return [round(float((phase + j * period) / fps), 3) for j in range(count + 1) if phase + j * period < n]


def out_time(segs: List[Dict], vt: float) -> Optional[float]:
    """Narration time -> output time (pauses between sentences are tightened)."""
    for s in segs:
        if s["va"] - 0.01 <= vt <= s["vb"]:
            return s["out"] + (vt - s["va"])
    for s in segs:
        if s["vb"] < vt <= s["vb"] + GAP:
            return s["out"] + (s["vb"] - s["va"]) + min(vt - s["vb"], GAP)
    return None


# --------------------------------------------------------------- overlays

def _is_emoji(ch: str) -> bool:
    """The emoji blocks only: "°" (also a symbol for Unicode) was once taken for
    the banner's emoji and cut out of "ANGLE À 90°"; © ® ™ € £ are text too."""
    o = ord(ch)
    return (o >= 0x1F000 or 0x2600 <= o <= 0x27BF or 0x2B00 <= o <= 0x2BFF or 0x2300 <= o <= 0x23FF
            or 0x2190 <= o <= 0x21FF or ch in ("️", "‍", "⃣"))


def split_emoji(text: str) -> Tuple[str, Optional[str]]:
    emoji = "".join(ch for ch in text if _is_emoji(ch)).replace("️", "")
    clean = "".join(ch for ch in text if not _is_emoji(ch)).strip()
    return re.sub(r"\s{2,}", " ", clean), (emoji[:1] or None)


def _emoji_image(ch: str, size: int) -> Image.Image:
    e = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
    ImageDraw.Draw(e).text((0, 0), ch, font=ImageFont.truetype(EMOJI_FONT, 109), embedded_color=True)
    return e.crop(e.getbbox() or (0, 0, 1, 1)).resize((size, size), Image.LANCZOS)


def _draw_runs(img, center, parts, font, rtl, emoji=None, emoji_size=0):
    """parts = [(text, colour), ...] in READING order, one line centred."""
    d = ImageDraw.Draw(img)
    kw = {"direction": "rtl", "language": "ar"} if rtl else {}
    widths = [d.textlength(s, font=font, **kw) for s, _ in parts]
    total = sum(widths) + ((emoji_size + 14) if emoji else 0)
    x0, y = center[0] - total / 2, center[1]
    if rtl:                                    # first part on the right, emoji at the left end
        x = x0 + total
        for (s, col), w in zip(parts, widths):
            x -= w
            d.text((x, y), s, font=font, fill=col, anchor="lm", **kw)
        ex = x0
    else:
        x = x0
        for (s, col), w in zip(parts, widths):
            d.text((x, y), s, font=font, fill=col, anchor="lm")
            x += w
        ex = x + 14
    if emoji and os.path.exists(EMOJI_FONT):
        img.alpha_composite(_emoji_image(emoji, emoji_size), (int(ex), int(y - emoji_size / 2)))
    return total


def banner_parts(text: str, head: str = "white", key: str = None) -> Tuple[List[Tuple[str, str]], Optional[str]]:
    """'HEAD : TAIL 😐' -> head colour + key colour tail; no colon -> last word in the key colour."""
    key = key or BANNER_KEY
    clean, emoji = split_emoji(text)
    if ":" in clean:
        h, tail = clean.split(":", 1)
        return [(h.strip() + " : ", head), (tail.strip(), key)], emoji
    ws = clean.split()
    if len(ws) > 1:
        return [(" ".join(ws[:-1]) + " ", head), (ws[-1], key)], emoji
    return [(clean, key)], emoji


def banner_png(text: str, path: str, lang: Dict, style: Optional[Dict] = None) -> str:
    """Rounded box with a border, sized to its text, in the channel's style."""
    st = style or STYLES["classique"]
    img = Image.new("RGBA", (W, 300), (0, 0, 0, 0))
    parts, emoji = banner_parts(text, st["head"], st["key"])
    if lang["rtl"]:
        parts = [(s.replace(" : ", ": "), c) for s, c in parts]
    d = ImageDraw.Draw(img)
    kw = {"direction": "rtl", "language": "ar"} if lang["rtl"] else {}
    for size in (70, 64, 58, 52, 46, 40, 34):
        font = ImageFont.truetype(font_path(lang["banner_font"]), size)
        tw = sum(d.textlength(s, font=font, **kw) for s, _ in parts) + (size + 14 if emoji else 0)
        if tw <= W - 150:
            break
    bw, bh = int(tw + 70), int(size * 1.75)
    x0, y0 = (W - bw) // 2, 20
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((x0, y0 + 6, x0 + bw, y0 + bh + 6), 22, fill=(0, 0, 0, 160))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(8)))
    d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), 22, fill=st["box"], outline=st["border"], width=4)
    _draw_runs(img, (W / 2, y0 + bh / 2 + 2), parts, font, lang["rtl"], emoji, size)
    img.save(path)
    return path


def credit_png(handles: str, path: str, lang: Dict) -> str:
    """'Images : @a · @b' — the Latin handles always stay left-to-right."""
    img = Image.new("RGBA", (W, 90), (0, 0, 0, 0))
    if handles:
        d = ImageDraw.Draw(img)
        col = (170, 176, 188, 255)
        label = lang["credit_label"]
        kw = {"direction": "rtl", "language": "ar"} if lang["rtl"] else {}
        names = handles.split(" · ")
        # one line, smaller until it fits (four handles once ran off both edges); too small to read
        # (six sources once): the names on two lines
        for lines in ([handles], [" · ".join(names[:(len(names) + 1) // 2]), " · ".join(names[(len(names) + 1) // 2:])]):
            for size in range(30, 25 if len(lines) == 1 and len(names) > 1 else 15, -2):   # 22 px was hard to read
                font = ImageFont.truetype(font_path(lang["credit_font"]), size)
                lw = d.textlength(label, font=font, **kw)
                hw = max(d.textlength(x, font=font) for x in lines)
                if lw + 12 + hw <= W - 60:
                    break
            else:
                continue
            break
        x0 = (W - (lw + 12 + hw)) / 2
        ys = [45] if len(lines) == 1 else [25, 65]
        for y, text in zip(ys, lines):
            tw = d.textlength(text, font=font)
            if lang["rtl"]:      # Arabic label on the right
                d.text((x0 + hw - tw, y), text, font=font, fill=col, anchor="lm")
            else:
                d.text((x0 + lw + 12, y), text, font=font, fill=col, anchor="lm")
        if lang["rtl"]:
            d.text((x0 + hw + 12, 45), label, font=font, fill=col, anchor="lm", **kw)
        else:
            d.text((x0, 45), label, font=font, fill=col, anchor="lm")
    img.save(path)
    return path


def corners_png(path: str) -> str:
    img = Image.new("RGBA", (BOX_W, BOX_H), (0, 0, 0, 255))
    mask = Image.new("L", (BOX_W, BOX_H), 255)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, BOX_W - 1, BOX_H - 1), 30, fill=0)
    img.putalpha(mask)
    img.save(path)
    return path


# --------------------------------------------------------------- captions

def _ass_time(x: float) -> str:
    h, r = divmod(max(x, 0), 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _ass_color(hexcol: str) -> str:
    h = hexcol.lstrip("#")
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}&"


def _norm(w: str) -> str:
    return re.sub(r"[^\w]", "", w.lower())


CAPTION_MAX_W = W - 160          # px a caption line may take (safe margins)


def _caption_font(lang: Dict) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_path(lang["banner_font"]), lang["caption_size"])   # same Black weight


def caption_width(words: List[str], lang: Dict, font=None) -> float:
    """Real drawn width, in px, of words shown together (counting letters let
    'POURQUOI LES CONDUCTEURS' run off the screen)."""
    font = font or _caption_font(lang)
    text = " ".join(w.upper() if lang["upper"] else w for w in words)
    d = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
    kw = {"direction": "rtl", "language": "ar"} if lang["rtl"] else {}
    return d.textlength(text, font=font, **kw) + 14       # + the outline on both ends


def caption_groups(ws: List[Dict], lang: Dict) -> List[List[Dict]]:
    """1-3 words at a time, never wider than the screen, and a sentence
    break (comma, full stop...) always ends a group."""
    font = _caption_font(lang)
    groups, cur = [], []
    for w in ws:
        if cur and (len(cur) >= 3 or caption_width([x["w"] for x in cur + [w]], lang, font) > CAPTION_MAX_W):
            groups.append(cur)
            cur = []
        cur.append(w)
        if w["w"][-1:] in ",.:;?!،؟…":
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def captions_ass(passages: List[Dict], words: List[Dict], segs: List[Dict], path: str, lang: Dict,
                 style: Optional[Dict] = None) -> int:
    """1-3 words at a time, centred under the box, popping in; the sentence's
    keywords in its colour. Arabic: every word is its own colour run and the
    style's encoding is -1 (right-to-left base) — measured: with one multi-word
    run after a colour change, libass laid the words out left to right."""
    enc = -1 if lang["rtl"] else 1
    st = style or STYLES["classique"]
    base, outline = _ass_color(st["text"]).strip("&") , _ass_color(st["outline"]).strip("&")
    base, outline = "&" + base, "&" + outline
    reset = base + "&"
    lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2", "",
             "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
             "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
             "MarginL, MarginR, MarginV, Encoding",
             f"Style: Cap,{lang['caption_font']},{lang['caption_size']},{base},{base},{outline},&H90000000,"
             f"0,0,0,0,100,100,0,0,1,7,4,5,60,60,0,{enc}",
             "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    n = 0
    for k, p in enumerate(passages):
        colour = _ass_color(st["words"][k % len(st["words"])])
        keys = {_norm(x) for kw in p.get("mots_cles") or [] for x in str(kw).split()}
        groups = caption_groups([words[i] for i in p["words"]], lang)
        for g, grp in enumerate(groups):
            a = out_time(segs, grp[0]["start"])
            b = out_time(segs, groups[g + 1][0]["start"]) if g + 1 < len(groups) else \
                (out_time(segs, grp[-1]["end"]) or 0) + 0.25
            if a is None or b is None:
                continue
            parts = []
            for w in grp:
                word = (w["w"].upper() if lang["upper"] else w["w"]).replace("{", "").replace("}", "")
                hit = _norm(w["w"]) in keys
                if lang["rtl"]:
                    parts.append(f"{{\\c{colour if hit else reset}}}{word}")
                else:
                    parts.append(f"{{\\c{colour}}}{word}{{\\c{reset}}}" if hit else word)
            # a single word wider than the screen is squeezed to fit, never cut
            fit = min(100, int(100 * CAPTION_MAX_W / max(1.0, caption_width([w["w"] for w in grp], lang))))
            pop = (rf"{{\an5\pos({W // 2},{CAPTION_Y})\fscx{int(fit * 0.8)}\fscy80"
                   rf"\t(0,90,\fscx{int(fit * 1.06)}\fscy106)\t(90,160,\fscx{fit}\fscy100)}}")
            lines.append(f"Dialogue: 0,{_ass_time(a)},{_ass_time(b)},Cap,,0,0,0,,{pop}{' '.join(parts)}")
            n += 1
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return n


# --------------------------------------------------------------- picture

def _even(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


def _ease(t0: float, t1: float) -> str:
    """0 before t0, 1 after t1, smooth in between (ffmpeg expression of t)."""
    p = f"clip((t-{t0:.3f})/{max(t1 - t0, 0.01):.3f},0,1)"
    return f"({p}*{p}*(3-2*{p}))"


def _played(i: int, k: int, c: Dict, s: Dict, crop_delogo: str, width: int = 0,
            preview: bool = False) -> Tuple[List[str], str]:
    """The clip as the time map plays it (ramps, freezes, slow-down), as one
    stream at FPS lasting the segment: filters + its label. width: the
    largest width the picture is shown at — slow motion is interpolated at
    that size (measured: 32 s for 0.9 s of 1080p, 13 s at 1280 wide); the
    preview repeats frames instead (seconds)."""
    pcs = s.get("pieces") or [{"kind": "play", "a": s["ws"], "b": min(s["ws"] + s["dur"], c["end"]), "speed": 1.0,
                               "o": 0.0, "len": min(s["dur"], c["end"] - s["ws"])}]
    a0 = min(p["a"] if p["kind"] == "play" else p["t"] for p in pcs)
    b0 = max(p["b"] if p["kind"] == "play" else p["t"] + 0.1 for p in pcs)
    pre = f"[{i}:v]trim={a0:.3f}:{b0:.3f},setpts=PTS-STARTPTS,fps={FPS}{crop_delogo}"
    simple = [p for p in pcs if not p.get("pad")]
    if len(simple) == 1 and simple[0]["kind"] == "play" and simple[0]["speed"] == 1.0:
        p, pad = simple[0], s["dur"] - simple[0]["len"]     # as before the effects: one cut, the last picture held
        pre = f"[{i}:v]trim={p['a']:.3f}:{p['b']:.3f},setpts=PTS-STARTPTS,fps={FPS}"
        if pad > 0.01:
            pre += f",tpad=stop_mode=clone:stop_duration={pad:.3f}"
        return [f"{pre}{crop_delogo}[pl{k}]"], f"pl{k}"
    if width and any(p["kind"] == "play" and p["speed"] < 0.99 for p in pcs):
        pre += f",scale='min(iw,{_even(width)})':-2"
    g = [f"{pre},split={len(pcs)}" + "".join(f"[pi{k}_{j}]" for j in range(len(pcs)))]
    for j, p in enumerate(pcs):
        if p["kind"] == "play":
            f = f"[pi{k}_{j}]trim={p['a'] - a0:.3f}:{p['b'] - a0:.3f},setpts=PTS-STARTPTS"
            if p["speed"] < 0.99 and preview:
                f += f",setpts=PTS/{p['speed']:.3f}"
            elif p["speed"] < 0.99:                   # new frames in between, not the same ones twice
                f += (f",setpts=PTS/{p['speed']:.3f},minterpolate=fps={FPS}:mi_mode=mci:mc_mode=aobmc:"
                      f"me_mode=bidir:vsbmc=1")
            f += f",trim=0:{p['len']:.3f},setpts=PTS-STARTPTS"
        else:
            t = max(0.0, p["t"] - a0)
            f = (f"[pi{k}_{j}]trim={t:.3f}:{t + 1.5 / FPS:.3f},setpts=PTS-STARTPTS,trim=end_frame=1,"
                 f"tpad=stop_mode=clone:stop_duration={p['len']:.3f},trim=0:{p['len']:.3f},setpts=PTS-STARTPTS")
        g.append(f"{f},fps={FPS},setsar=1[pp{k}_{j}]")
    g.append("".join(f"[pp{k}_{j}]" for j in range(len(pcs))) + f"concat=n={len(pcs)}:v=1:a=0,fps={FPS}[pl{k}]")
    return g, f"pl{k}"


def framing(c: Dict) -> Tuple[float, float]:
    """Where a filled (cropped) picture is centred: on the sentence's subject
    when it was found (a man's head was cut off by a centred crop), else the
    middle. Only a filled picture is cropped; a wide one is shown whole."""
    ce = c.get("centre")
    if isinstance(ce, (list, tuple)) and len(ce) == 2:
        return min(max(float(ce[0]), 0.0), 1.0), min(max(float(ce[1]), 0.0), 1.0)
    return 0.5, 0.5


SHARPEN = ",hqdn3d=1.5:1.5:3:3,unsharp=5:5:0.9:5:5:0.0"   # a blown-up low resolution clip: denoised, then sharpened
NUMBER_S = 1.6                           # seconds a strong figure stays on screen
LOOP_S = 0.35                            # the last instants dissolve into the first picture


def number_frames(text: str, out_dir: str, lang: Dict, style: Dict, length: float) -> int:
    """A strong figure ("2 m", "1481 N") as PNG frames the size of the picture
    box: big, in the channel's key colour with a thick outline, popping in
    like the arrows, low in the box (the subject stays visible)."""
    from adaptation.annotate import _pop
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        os.remove(os.path.join(out_dir, f))
    arabic = any("\u0600" <= ch <= "\u06ff" for ch in text)     # "1481 N" in an Arabic video stays left to right
    kw = {"direction": "rtl", "language": "ar"} if lang["rtl"] and arabic else {}
    size = 190
    while size > 70:
        font = ImageFont.truetype(font_path(lang["banner_font"]), size)
        probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
        if probe.textlength(text, font=font, **kw) <= BOX_W - 120:
            break
        size -= 10
    base = Image.new("RGBA", (BOX_W, int(size * 1.6)), (0, 0, 0, 0))
    d = ImageDraw.Draw(base)
    d.text((BOX_W / 2, base.height / 2), text, font=font, fill=style["key"], anchor="mm",
           stroke_width=max(6, size // 14), stroke_fill=style["outline"], **kw)
    glow = base.split()[3].filter(ImageFilter.GaussianBlur(14)).point(lambda v: int(v * 0.6))
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    shadow.putalpha(glow)
    base = Image.alpha_composite(shadow, base)
    n = max(1, int(round(length * FPS)))
    cy = int(BOX_H * 0.74)
    for i in range(n):
        scale, alpha = _pop(i / FPS, n / FPS)
        w, h = max(2, int(base.width * scale)), max(2, int(base.height * scale))
        im = base.resize((w, h), Image.LANCZOS)
        if alpha < 1:
            im.putalpha(im.split()[3].point(lambda v: int(v * alpha)))
        layer = Image.new("RGBA", (BOX_W, BOX_H), (0, 0, 0, 0))
        layer.alpha_composite(im, ((BOX_W - w) // 2, cy - h // 2))
        layer.save(os.path.join(out_dir, f"f_{i:03d}.png"))
    return n


DARK = 70                                # mean luma (0-255) under which a clip is lit up
CAST = 6                                 # mean chroma this far from neutral (128): a colour cast, pulled back


def look(c: Dict) -> Optional[str]:
    """Filters that bring a clip in line with the others, measured on its own
    frames: a dark clip lit up (a classroom came out almost black next to
    sunny streets), a colour cast (a sepia shot among daylight ones) pulled
    70 % of the way back to neutral. None when nothing is off."""
    crop = f"crop={c['crop']}," if c.get("crop") else ""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-ss", f"{c['start']:.2f}", "-t", f"{max(0.5, c['end'] - c['start']):.2f}",
                        "-i", c["src"], "-vf", f"{crop}fps=2,scale=96:-2,signalstats,"
                        "metadata=print:key=lavfi.signalstats.YAVG,metadata=print:key=lavfi.signalstats.UAVG,"
                        "metadata=print:key=lavfi.signalstats.VAVG", "-f", "null", "-"], capture_output=True, text=True)
    avg = {}
    for key in ("YAVG", "UAVG", "VAVG"):
        vals = [float(v) for v in re.findall(key + r"=([\d.]+)", r.stderr)]
        if vals:
            avg[key] = sum(vals) / len(vals)
    out = []
    if avg.get("YAVG", 255) < DARK:
        out.append(f"eq=gamma={min(1.7, 1.0 + (DARK + 30 - avg['YAVG']) / 100):.2f}:contrast=1.08:saturation=1.1")
    du, dv = avg.get("UAVG", 128) - 128, avg.get("VAVG", 128) - 128
    if max(abs(du), abs(dv)) > CAST:
        out.append(f"lutyuv=u='clip(val-{0.7 * du:.1f},0,255)':v='clip(val-{0.7 * dv:.1f},0,255)'")
    return ",".join(out) or None


def light(c: Dict) -> Optional[str]:
    return look(c)


SHAKY = 0.012                            # frame-to-frame jitter (share of the width) above which a clip is stabilised


def shakiness(path: str, t0: float, length: float, crop: Optional[str] = None) -> float:
    """How much the picture jitters: the global shift between frames (phase
    correlation on small frames), minus its smooth part (a pan is not a shake)."""
    import cv2
    import numpy as np
    from adaptation.sources import _gray_frames
    f = _gray_frames(path, 96, 54, 15.0, crop, ss=t0, t=length).astype(np.float32)
    if len(f) < 8:
        return 0.0
    win = np.outer(np.hanning(54), np.hanning(96)).astype(np.float32)
    shifts = np.array([cv2.phaseCorrelate(f[i] * win, f[i + 1] * win)[0] for i in range(len(f) - 1)])
    path_ = np.cumsum(shifts, axis=0)
    k = np.ones(7) / 7
    smooth = np.stack([np.convolve(path_[:, j], k, mode="same") for j in (0, 1)], 1)
    return float(np.sqrt(np.mean(np.sum((path_ - smooth)[3:-3] ** 2, 1))) / 96) if len(path_) > 8 else 0.0


def stabilised(path: str, t0: float, length: float, out: str) -> str:
    """The clip's seconds steadied (vid.stab, two passes): a smoothed camera
    path, a slight zoom so no black edge shows."""
    trf = out + ".trf"
    common = ["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.3f}", "-t", f"{length:.3f}", "-i", path]
    subprocess.run(common + ["-vf", f"vidstabdetect=shakiness=6:accuracy=9:result='{_filter_path(trf)}'", "-f", "null", "-"],
                   check=True, capture_output=True)
    subprocess.run(common + ["-vf", f"vidstabtransform=input='{_filter_path(trf)}':smoothing=12:optzoom=1:interpol=bicubic",
                             "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-an", out], check=True, capture_output=True)
    return out


def _zoom_filter(z: str, cx: str, cy: str, shake: str, vw: int, vh: int) -> str:
    """Zoom z toward (cx, cy) (0-1 of the frame) at a FIXED frame size: a
    perspective warp, sub-pixel and per frame. (A per-frame scale + crop was
    tried: crop keeps the size of the first frame, the push-in missed its
    target.) The view vw x vh is the centre of the output; it never leaves
    the picture. Expressions of t, in seconds from the segment start."""
    tt = lambda e: re.sub(r"\bt\b", f"(on/{FPS})", e)
    Z = f"({tt(z)})"
    xc = f"clip({tt(cx)}*W+{tt(shake)},{vw}/(2*{Z}),W-{vw}/(2*{Z}))"
    yc = f"clip({tt(cy)}*H,{vh}/(2*{Z}),H-{vh}/(2*{Z}))"
    x0, x1 = f"{xc}-W/(2*{Z})", f"{xc}+W/(2*{Z})"
    y0, y2 = f"{yc}-H/(2*{Z})", f"{yc}+H/(2*{Z})"
    return (f"perspective=x0='{x0}':y0='{y0}':x1='{x1}':y1='{y0}':x2='{x0}':y2='{y2}':x3='{x1}':y3='{y2}':"
            f"interpolation=cubic:eval=frame")


def clip_chain(i: int, k: int, c: Dict, s: Dict, preview: bool = False) -> List[str]:
    """Filters turning clip c (input i) into segment k: [v{k}] BOX_W x BOX_H."""
    from adaptation import effects as E
    fx = s.get("fx") or {}
    T = s["impact_out"] - s["out"]
    punch = f"(1+0.07*exp(-pow((t-{T:.3f})/0.16,2)))"
    shake = f"9*sin(t*73)*exp(-pow((t-{T:.3f})/0.13,2))"
    if c.get("shock") is False:         # the zoom + shake is a crash's: a calm shot (no shock heard) stays still
        punch, shake = "1", "0"
    if fx.get("transition"):            # a whip zoom into the new part of the story
        punch += f"*(1+0.22*pow(1-clip(t/{E.TRANSITION},0,1),2))"
    x0, y0 = framing(c)                 # the subject's place: a cropped picture is centred on it, not on the middle
    zoom, cx, cy = "1", f"{x0:.3f}", f"{y0:.3f}"
    z = fx.get("zoom") if isinstance(fx.get("zoom"), dict) else None
    held = E.hold_at(s.get("pieces") or [])
    if z:                               # a slow push-in, reached at the strong moment, then held
        t1 = T if 0.6 < T < s["dur"] - 0.2 else s["dur"] * 0.7
        e = _ease(0.0, t1)
        zoom = f"(1+{z['z'] - 1:.3f}*{e})"
        cx, cy = f"({x0:.3f}+{z['cx'] - x0:.3f}*{e})", f"({y0:.3f}+{z['cy'] - y0:.3f}*{e})"
    elif held:                          # a freeze frame breathes: a small push-in while it holds
        zoom = f"(1+0.07*{_ease(held[0], held[0] + held[1])})"
    crop_delogo = f",crop={c['crop']}" if c.get("crop") else ""
    from adaptation.sources import delogo_filters
    for f in delogo_filters(c.get("delogo"), c["w"], c["h"]):
        crop_delogo += "," + f
    if c.get("eq"):                     # a dark clip, lit up (see light)
        crop_delogo += "," + c["eq"]
    aspect, box_aspect = c["w"] / c["h"], BOX_W / BOX_H
    fill = z or abs(math.log(aspect / box_aspect)) < 0.25
    shown = (max(BOX_W, BOX_H * aspect) * (z["z"] if z else 1.08) if fill
             else (BOX_W if aspect > box_aspect else BOX_H * aspect)) * 1.12
    g, played = _played(i, k, c, s, crop_delogo, int(shown), preview)
    pre = f"[{played}]"
    if fill:                                                 # close to the box (or zoomed in): fill it
        wc = _even(max(BOX_W, BOX_H * aspect))
        hc = _even(wc / aspect)
        g.append(f"{pre}scale={wc}:{hc}:flags=bicubic,"
                 f"{_zoom_filter(f'{1.08 if not z else 1.02}*{punch}*{zoom}', cx, cy, shake, BOX_W, BOX_H)},"
                 f"crop={BOX_W}:{BOX_H}{SHARPEN if c.get('low_res') else ''},setsar=1[v{k}]")
    else:                                                    # wide or tall: on a blurred copy of itself
        fw, fh = (BOX_W, _even(BOX_W / aspect)) if aspect > box_aspect else (_even(BOX_H * aspect), BOX_H)
        cover_w = _even(max(BOX_W, BOX_H * aspect) * 1.02)
        g.append(f"{pre}split[c{k}a][c{k}b]")
        g.append(f"[c{k}b]scale={cover_w}:-2,crop={BOX_W}:{BOX_H},boxblur=24:4,eq=brightness=-0.12[bg{k}]")
        g.append(f"[c{k}a]scale={fw}:{fh}:flags=bicubic,{_zoom_filter(f'1.04*{punch}*{zoom}', cx, cy, shake, fw, fh)}"
                 f"{SHARPEN if c.get('low_res') else ''}[fg{k}]")
        g.append(f"[bg{k}][fg{k}]overlay=(W-w)/2:(H-h)/2,setsar=1[v{k}]")
    return g


# --------------------------------------------------------------- render

def _filter_path(p: str) -> str:
    return os.path.abspath(p).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


MUSIC_LUFS = -26.0       # the music bed's loudness under a -16 LUFS voice (the level the person approved)
HUSH_S = 0.5             # the music stops this long before the strongest crash


def music_gain(path: str, start: float, length: float) -> float:
    """The volume that brings this track's part to MUSIC_LUFS (measured: from
    -9.9 LUFS to -18.2 between two tracks of the same channel; one fixed
    volume made one cover the voice and the other vanish)."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-ss", f"{start:.2f}", "-t", f"{max(5.0, length):.2f}", "-i", path,
                        "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True)
    found = re.findall(r"^\s+I:\s+(-?[\d.]+) LUFS", r.stderr, re.M)
    if not found:
        return MUSIC_GAIN
    return round(min(1.0, max(0.05, 10 ** ((MUSIC_LUFS - float(found[-1])) / 20))), 4)   # never amplified


def hush_at(segs: List[Dict], clips: Dict[str, Dict]) -> Optional[float]:
    """When the music stops for a breath: just before the first real crash
    heard after the hook (a trailer's trick, once per video), else None."""
    for s in segs[1:-1]:
        c = clips[s["clip"]]
        if c.get("shock") and s["impact_out"] - s["out"] > HUSH_S + 0.2:
            return round(s["impact_out"], 3)
    return None


def impact_sound(c: Dict, donor: Optional[Dict]) -> Optional[Dict]:
    """Whose sound plays at a clip's strong moment. Made for crash Shorts: on
    a salt-lake Short, the "loudest moment" of a reel's music (a boom) was
    borrowed and pasted under every sentence. So: a clip with a real shock
    heard (Gemini's "choc_sonore") plays its own sound, or a clean shock
    borrowed from another clip; a clip without one stays quiet. An older
    analysis (no flag) keeps its own clean sound and never borrows."""
    shock = c.get("shock")
    if shock is None:
        return c if c.get("audio_ok") else None
    if not shock:
        return None
    return c if c.get("audio_ok") else donor


def _window(s: Dict) -> Tuple[float, float]:
    """The source seconds a segment needs: (start, length), with a margin."""
    pcs = s.get("pieces") or [{"kind": "play", "a": s["ws"], "b": s["ws"] + s["dur"]}]
    a0 = min(p["a"] if p["kind"] == "play" else p["t"] for p in pcs)
    b0 = max(p["b"] if p["kind"] == "play" else p["t"] + 0.1 for p in pcs)
    t0 = max(0.0, a0 - 0.5)
    return t0, b0 - t0 + 0.5


def _shifted(c: Dict, s: Dict, t0: float) -> Tuple[Dict, Dict]:
    """The clip and its segment in the times of an input opened at t0 (-ss).
    One input per source, cut many times, made ffmpeg hold every frame waiting
    for a later segment in memory: a final render was killed at 4.5 GB."""
    c2 = {**c, "start": c["start"] - t0, "end": c["end"] - t0, "impact": c["impact"] - t0}
    pcs = [{**p, **({"a": p["a"] - t0, "b": p["b"] - t0} if p["kind"] == "play" else {"t": p["t"] - t0})}
           for p in s.get("pieces") or []]
    return c2, {**s, "ws": s["ws"] - t0, "pieces": pcs}


RENDERING = threading.BoundedSemaphore(1)   # two final renders at once once ran out of memory


def _picture_box(segs: List[Dict], clips: Dict[str, Dict], work_dir: str, preview: bool, progress=None,
                 notes: Optional[Dict[int, Dict]] = None) -> str:
    """The picture box of the whole video, made one segment at a time, then
    joined without re-encoding. In one graph ffmpeg reads every source at once
    and keeps the frames of the segments still waiting: a final render was
    killed by the system at 4.5 GB. Each segment has the exact number of
    frames of its place in the timeline, so nothing drifts."""
    files, lit = [], {}
    for n, s in enumerate(segs):
        c = clips[s["clip"]]
        if s["clip"] not in lit:
            try:
                lit[s["clip"]] = look(c)
            except Exception:
                lit[s["clip"]] = None
        c = {**c, "eq": lit[s["clip"]]}
        t0, length = _window(s)
        src, seek = c["src"], t0
        if notes is not None:           # what the render decided for this plan (the recipe)
            notes[s["k"]] = {"correction_image": lit[s["clip"]], "nettete": bool(c.get("low_res")), "stabilise": False}
        if not preview:                 # a shaky hand-held shot is steadied (the preview stays fast)
            try:
                before = shakiness(c["src"], t0, length, c.get("crop"))
                if before > SHAKY:
                    steady = stabilised(c["src"], t0, length, os.path.join(work_dir, f"stab_{s['k']}.mp4"))
                    if shakiness(steady, 0.0, length, c.get("crop")) < before * 0.7:   # kept only if clearly steadier
                        src, seek = steady, 0.0
                        if notes is not None:
                            notes[s["k"]]["stabilise"] = True
            except Exception:
                src, seek = c["src"], t0
        frames = max(1, round((s["out"] + s["dur"]) * FPS) - round(s["out"] * FPS))
        g = clip_chain(0, s["k"], *_shifted(c, s, t0), preview)
        g.append(f"[v{s['k']}]tpad=stop_mode=clone:stop_duration=1[vo]")
        out = os.path.join(work_dir, f"seg_{s['k']}.mp4")
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{seek:.3f}", "-t", f"{length:.3f}", "-i", src,
                            "-filter_complex", ";".join(g), "-map", "[vo]", "-frames:v", str(frames), "-r", str(FPS),
                            "-c:v", "libx264", "-preset", "ultrafast" if preview else "veryfast",
                            "-crf", "24" if preview else "12", "-pix_fmt", "yuv420p", "-an", out],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RenderError(f"ffmpeg a échoué (plan {s['k'] + 1}) : {r.stderr.strip()[-600:]}")
        files.append(out)
        if progress:
            progress((n + 1) / len(segs))
    listing = os.path.join(work_dir, "segments.txt")
    with open(listing, "w", encoding="utf-8") as f:
        f.writelines(f"file '{os.path.abspath(x)}'\n" for x in files)
    box = os.path.join(work_dir, "box.mp4")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", box],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RenderError(f"ffmpeg a échoué (assemblage) : {r.stderr.strip()[-600:]}")
    return box


def render(*args, **kw) -> Dict:
    """Final renders one at a time (two at once ran out of memory); previews freely."""
    if kw.get("preview"):
        return _render(*args, **kw)
    with RENDERING:
        return _render(*args, **kw)


def _render(passages: List[Dict], words: List[Dict], clips: Dict[str, Dict], voice_path: str, lang_code: str,
           out_path: str, work_dir: str, credit: str = "", music: Optional[Tuple[str, float]] = None,
           preview: bool = False, progress_cb=None, annotations: Optional[List[Dict]] = None,
           style: Optional[str] = None, effects: Optional[List[Optional[Dict]]] = None,
           beats: Optional[List[float]] = None) -> Dict:
    """annotations: arrows/circles prepared by annotate.prepare (frames + start time), laid on the
    picture box under the banners and captions.
    passages: [{clip, bandeau, mots_cles, start, end, words: [word indices]}] with narration
    times; words: [{w, start, end}]; clips: id -> {src, start, end, impact, w, h, crop?,
    delogo?, audio_ok?}. Returns {duration, segments, captions}."""
    lang = lang_of(lang_code)
    os.makedirs(work_dir, exist_ok=True)
    segs, total = build_timeline(passages, clips, effects, beats)

    look = style_of(style)
    banners = [banner_png(p["bandeau"], os.path.join(work_dir, f"banner_{k}.png"), lang, look) for k, p in enumerate(passages)]
    credit_file = credit_png(credit, os.path.join(work_dir, "credit.png"), lang)
    corners = corners_png(os.path.join(work_dir, "corners.png"))
    ass = os.path.join(work_dir, "captions.ass")
    n_caps = captions_ass(passages, words, segs, ass, lang, look)

    inputs: List[str] = []
    g: List[str] = []

    def add_input(*args) -> int:
        inputs.extend(args)
        return sum(1 for x in inputs if x == "-i") - 1

    vin = add_input("-i", voice_path)
    part = lambda a, b: (lambda f: progress_cb(a + (b - a) * f)) if progress_cb else None
    notes: Dict[int, Dict] = {}
    bi = add_input("-i", _picture_box(segs, clips, work_dir, preview, part(0.0, 0.5), notes))
    g.append(f"[{bi}:v]setpts=PTS-STARTPTS,fps={FPS}[box]")
    box = "box"
    look_ = style_of(style)
    numbers = []                                            # a strong figure, big, at the plan's strong moment
    for s in segs:
        text = (s.get("fx") or {}).get("chiffre")
        if text:
            start = min(max(s["out"], s["impact_out"] - 0.15), s["out"] + max(0.0, s["dur"] - 1.0))
            length = min(NUMBER_S, s["out"] + s["dur"] - start)
            d = os.path.join(work_dir, f"num{s['k']}")
            if length > 0.4 and number_frames(text, d, lang, look_, length):
                numbers.append({"dir": d, "start": start})
    for j, an in enumerate(list(annotations or []) + numbers):  # each one a PNG sequence, shifted to its moment
        ai = add_input("-framerate", str(FPS), "-i", os.path.join(an["dir"], "f_%03d.png"))
        g.append(f"[{ai}:v]format=rgba,setpts=PTS-STARTPTS+{an['start']:.3f}/TB[an{j}]")
        g.append(f"[{box}][an{j}]overlay=0:0:eof_action=pass[bx{j}]")
        box = f"bx{j}"

    # narration, pauses tightened, one loudness for every video
    for s in segs:
        g.append(f"[{vin}:a]atrim={s['va']:.3f}:{s['vb']:.3f},asetpts=PTS-STARTPTS,"
                 f"apad=pad_dur={s['dur'] - (s['vb'] - s['va']):.3f},atrim=0:{s['dur']:.3f},"
                 f"aformat=sample_rates=44100:channel_layouts=stereo[a{s['k']}]")
    # loudnorm resamples to 192 kHz internally: back to 44.1 kHz before mixing,
    # or the mix comes out shorter than the picture (lost the end of the narration once)
    g.append("".join(f"[a{s['k']}]" for s in segs) + f"concat=n={len(segs)}:v=0:a=1,"
             "loudnorm=I=-16:TP=-1.5:LRA=7,aresample=44100,aformat=sample_rates=44100:channel_layouts=stereo[voice]")
    mix = ["[voice]"]

    # crash sounds: only where a real shock is heard (see impact_sound)
    donor = next((c for c in clips.values() if c.get("audio_ok") and c.get("shock")), None)
    fx, own_crash = [], set()
    for s in segs:
        sound = impact_sound(clips[s["clip"]], donor)
        if not sound:
            continue
        own_crash.add(s["k"])
        a = max(sound["start"], sound["impact"] - 0.35)
        b = min(sound["end"], sound["impact"] + 0.9)
        delay = int(max(0.0, s["impact_out"] - (sound["impact"] - a)) * 1000)
        ai = add_input("-ss", f"{a:.3f}", "-t", f"{b - a + 0.1:.3f}", "-i", sound["src"])
        g.append(f"[{ai}:a]atrim=0:{b - a:.3f},asetpts=PTS-STARTPTS,"
                 f"afade=t=out:st={max(0.0, b - a - 0.3):.3f}:d=0.3,"
                 f"aformat=sample_rates=44100:channel_layouts=stereo,adelay={delay}:all=1[fx{s['k']}]")
        fx.append(f"[fx{s['k']}]")
    if fx:
        g.append("".join(fx) + f"amix=inputs={len(fx)}:normalize=0,volume={SFX_GAIN}[fx]")
        mix.append("[fx]")
    # the sound effects that follow the picture (arrows, freeze, slow motion, figures, the main transition)
    effets = sfx.sounds(sfx.plan(segs, list(annotations or []), numbers, total, own_crash))
    for j, e in enumerate(effets):
        ei = add_input("-i", e["file"])
        g.append(f"[{ei}:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={e['gain']},"
                 f"adelay={int(e['start'] * 1000)}:all=1[sx{j}]")
        mix.append(f"[sx{j}]")
    music_info: Dict = {}
    if music and music[0] and os.path.exists(music[0]):
        mi = add_input("-ss", f"{music[1]:.3f}", "-i", music[0])
        # one steady level under the voice (ducking between sentences 0.2 s apart made it pump: tiring),
        # then, once the last word is said, the music comes up for the outro
        said = segs[-1]["out"] + (segs[-1]["vb"] - segs[-1]["va"])
        gain = music_gain(music[0], music[1], total)          # every track as loud under the voice
        up = gain * MUSIC_OUTRO / MUSIC_GAIN
        level = f"if(lt(t,{said:.3f}),{gain:.4f},{gain:.4f}+{up - gain:.4f}*min(1,(t-{said:.3f})/{OUTRO_RISE}))"
        hush = hush_at(segs, clips)
        if hush is not None:            # the music holds its breath half a second before the strongest crash
            a0 = hush - HUSH_S
            level = (f"({level})*(1-clip((t-{a0:.3f})/0.08,0,1)*clip(({hush:.3f}-t)/0.04,0,1))")
        music_info.update(gain=round(gain, 3), silence_avant_choc=hush)
        g.append(f"[{mi}:a]aformat=sample_rates=44100:channel_layouts=stereo,atrim=0:{total:.3f},"
                 f"afade=t=in:d=0.4,volume='{level}':eval=frame,"
                 f"afade=t=out:st={max(0.0, total - 0.15):.3f}:d=0.15[mus]")
        mix.append("[mus]")
    g.append("".join(mix) + f"amix=inputs={len(mix)}:duration=first:normalize=0,alimiter=limit=0.95,"
             f"aresample=48000,apad,atrim=0:{total:.3f}[aout]")

    # picture
    ci = add_input("-loop", "1", "-i", credit_file)
    ki = add_input("-loop", "1", "-i", corners)
    bi = [add_input("-loop", "1", "-i", b) for b in banners]
    g.append(f"color=black:s={W}x{H}:r={FPS}:d={total:.3f}[bgc]")
    first = os.path.join(work_dir, "first.png")
    if total > 3 and subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(work_dir, "box.mp4"),
                                     "-frames:v", "1", first]).returncode == 0 and os.path.exists(first):
        # the end dissolves into the very first picture: watched again, the Short loops seamlessly
        li = add_input("-loop", "1", "-framerate", str(FPS), "-t", f"{total:.3f}", "-i", first)
        g.append(f"[{li}:v]format=rgba,fade=t=in:st={total - LOOP_S:.3f}:d={LOOP_S}:alpha=1[loopimg]")
        g.append(f"[{box}][loopimg]overlay=0:0:eof_action=pass[boxl]")
        box = "boxl"
    g.append(f"[bgc][{box}]overlay={BOX_X}:{BOX_Y}:shortest=1[p0]")
    g.append(f"[p0][{ki}:v]overlay={BOX_X}:{BOX_Y}:shortest=1[p1]")
    g.append(f"[p1][{ci}:v]overlay=0:{CREDIT_Y}:shortest=1[p2]")
    cur = "p2"
    for s, b in zip(segs, bi):
        a, e = s["out"], s["out"] + s["dur"]
        g.append(f"[{cur}][{b}:v]overlay=0:{BANNER_Y}:shortest=1:enable='between(t,{a:.3f},{e - 0.001:.3f})'[q{s['k']}]")
        cur = f"q{s['k']}"
    final = ",scale=540:960" if preview else ""
    g.append(f"[{cur}]ass='{_filter_path(ass)}':fontsdir='{_filter_path(FONTS_DIR)}':shaping=complex{final},format=yuv420p[vout]")

    enc = ["-preset", "ultrafast", "-crf", "28"] if preview else ["-preset", "medium", "-crf", "19"]
    tmp = out_path + ".part.mp4"
    cmd = ["ffmpeg", "-v", "error", "-y", "-nostats", "-progress", "pipe:1", *inputs, "-filter_complex", ";".join(g),
           "-map", "[vout]", "-map", "[aout]", "-t", f"{total:.3f}", "-c:v", "libx264", *enc,
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", tmp]
    _run(cmd, total, part(0.5, 1.0))
    os.replace(tmp, out_path)
    bpm = round(60 / (beats[1] - beats[0])) if beats and len(beats) > 1 else None
    on_beat = lambda s: bool(beats and s["k"] > 0 and min(abs(s["out"] - b) for b in beats) < 0.02)
    recipe = {"style": style or "classique", "fin_en_boucle": bool(first and os.path.exists(first) and total > 3),
              "musique_niveau": "constant sous la voix, monte à la fin" if music and music[0] else None,
              "musique_gain": music_info.get("gain"), "silence_avant_choc": music_info.get("silence_avant_choc"),
              "tempo_musique": bpm,
              "effets_sonores": [{"son": os.path.basename(e["file"]), "a_s": round(e["start"], 2), "pourquoi": e["pourquoi"]}
                                 for e in effets], "plans": []}
    for s in segs:
        fx = dict(s.get("fx") or {})
        if isinstance(fx.get("zoom"), dict):
            fx["zoom"] = {"force": fx["zoom"]["z"], "vers": [fx["zoom"]["cx"], fx["zoom"]["cy"]]}
        recipe["plans"].append({"clip": s["clip"], "debut": round(s["out"], 2), "duree": round(s["dur"], 2),
                                "coupe_sur_le_temps": on_beat(s), "effets_appliques": fx,
                                **notes.get(s["k"], {})})
    recipe = json.loads(json.dumps(recipe, default=lambda o: o.item() if hasattr(o, "item") else str(o)))  # plain JSON
    return {"duration": round(total, 2), "captions": n_caps, "recette": recipe,
            "segments": [{"clip": s["clip"], "start": round(s["out"], 2), "end": round(s["out"] + s["dur"], 2),
                          "impact": round(s["impact_out"], 2)} for s in segs]}


def _run(cmd: Sequence[str], total: float, progress_cb) -> None:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in proc.stdout:
        m = re.match(r"out_time_us=(\d+)", line)
        if m and progress_cb and total > 0:
            progress_cb(min(1.0, int(m.group(1)) / 1e6 / total))
    err = proc.stderr.read()
    code = proc.wait()
    if code != 0:
        if code in (-9, 137) and not err.strip():   # killed by the system, no word from ffmpeg: memory
            raise RenderError("ffmpeg a été arrêté par le système (mémoire pleine) : réessaie quand aucun autre rendu ne tourne.")
        raise RenderError(f"ffmpeg a échoué : {err.strip()[-600:]}")
    if progress_cb:
        progress_cb(1.0)
