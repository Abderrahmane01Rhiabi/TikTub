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

import math
import os
import re
import subprocess
import unicodedata
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from adaptation.langs import FONTS_DIR, font_path, lang as lang_of

W, H, FPS = 1080, 1920, 30
BOX_X, BOX_Y, BOX_W, BOX_H = 30, 380, 1020, 980
BANNER_Y, CREDIT_Y, CAPTION_Y = 220, 150, 1500
GAP = 0.18                                         # pause kept between two sentences
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
SFX_GAIN = 0.55


class RenderError(RuntimeError):
    pass


# --------------------------------------------------------------- timeline

def build_timeline(passages: List[Dict], clips: Dict[str, Dict],
                   effects: Optional[List[Optional[Dict]]] = None) -> Tuple[List[Dict], float]:
    """One segment per sentence: where its voice is cut from (va..vb), where
    it sits in the output, and which part of its clip plays under it.
    effects (one per passage, see adaptation/effects.py) change how the clip
    plays: s["fx"] and s["pieces"], the time map every overlay follows."""
    from adaptation import effects as E
    segs, t = [], 0.0
    for k, p in enumerate(passages):
        a, b = max(0.0, p["start"] - 0.04), p["end"] + 0.10
        dur = (b - a) + GAP
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
    return unicodedata.category(ch) in ("So", "Sk") or ord(ch) >= 0x1F000 or ch == "️"


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
        for size in range(30, 15, -2):          # four handles once ran off both edges: smaller until it fits
            font = ImageFont.truetype(font_path(lang["credit_font"]), size)
            lw, hw = d.textlength(label, font=font, **kw), d.textlength(handles, font=font)
            if lw + 12 + hw <= W - 60:
                break
        x0 = (W - (lw + 12 + hw)) / 2
        if lang["rtl"]:      # Arabic label on the right
            d.text((x0, 45), handles, font=font, fill=col, anchor="lm")
            d.text((x0 + hw + 12, 45), label, font=font, fill=col, anchor="lm", **kw)
        else:
            d.text((x0, 45), label, font=font, fill=col, anchor="lm")
            d.text((x0 + lw + 12, 45), handles, font=font, fill=col, anchor="lm")
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
    zoom, cx, cy = "1", "0.5", "0.5"
    z = fx.get("zoom") if isinstance(fx.get("zoom"), dict) else None
    held = E.hold_at(s.get("pieces") or [])
    if z:                               # a slow push-in, reached at the strong moment, then held
        t1 = T if 0.6 < T < s["dur"] - 0.2 else s["dur"] * 0.7
        e = _ease(0.0, t1)
        zoom = f"(1+{z['z'] - 1:.3f}*{e})"
        cx, cy = f"(0.5+{z['cx'] - 0.5:.3f}*{e})", f"(0.5+{z['cy'] - 0.5:.3f}*{e})"
    elif held:                          # a freeze frame breathes: a small push-in while it holds
        zoom = f"(1+0.07*{_ease(held[0], held[0] + held[1])})"
    crop_delogo = f",crop={c['crop']}" if c.get("crop") else ""
    from adaptation.sources import delogo_filters
    for f in delogo_filters(c.get("delogo"), c["w"], c["h"]):
        crop_delogo += "," + f
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
                 f"crop={BOX_W}:{BOX_H},setsar=1[v{k}]")
    else:                                                    # wide or tall: on a blurred copy of itself
        fw, fh = (BOX_W, _even(BOX_W / aspect)) if aspect > box_aspect else (_even(BOX_H * aspect), BOX_H)
        cover_w = _even(max(BOX_W, BOX_H * aspect) * 1.02)
        g.append(f"{pre}split[c{k}a][c{k}b]")
        g.append(f"[c{k}b]scale={cover_w}:-2,crop={BOX_W}:{BOX_H},boxblur=24:4,eq=brightness=-0.12[bg{k}]")
        g.append(f"[c{k}a]scale={fw}:{fh}:flags=bicubic,{_zoom_filter(f'1.04*{punch}*{zoom}', cx, cy, shake, fw, fh)}[fg{k}]")
        g.append(f"[bg{k}][fg{k}]overlay=(W-w)/2:(H-h)/2,setsar=1[v{k}]")
    return g


# --------------------------------------------------------------- render

def _filter_path(p: str) -> str:
    return os.path.abspath(p).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


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


WHOOSH_PEAK = 0.32                  # seconds into whoosh.wav where it is loudest


def whoosh_wav(path: str) -> str:
    """A whoosh made from filtered noise (no sound file to ship): it swells
    to the cut, then falls away quickly."""
    if not os.path.exists(path):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "anoisesrc=d=0.55:c=pink:a=0.9:r=44100", "-af",
                        "highpass=f=250,lowpass=f=4200,bandreject=f=60:width_type=h:w=40,"
                        f"afade=t=in:st=0:d={WHOOSH_PEAK}:curve=exp,"
                        f"afade=t=out:st={WHOOSH_PEAK}:d=0.22:curve=exp,aecho=0.6:0.4:35:0.25",
                        "-ac", "2", path], check=True)
    return path


def render(passages: List[Dict], words: List[Dict], clips: Dict[str, Dict], voice_path: str, lang_code: str,
           out_path: str, work_dir: str, credit: str = "", music: Optional[Tuple[str, float]] = None,
           preview: bool = False, progress_cb=None, annotations: Optional[List[Dict]] = None,
           style: Optional[str] = None, effects: Optional[List[Optional[Dict]]] = None) -> Dict:
    """annotations: arrows/circles prepared by annotate.prepare (frames + start time), laid on the
    picture box under the banners and captions.
    passages: [{clip, bandeau, mots_cles, start, end, words: [word indices]}] with narration
    times; words: [{w, start, end}]; clips: id -> {src, start, end, impact, w, h, crop?,
    delogo?, audio_ok?}. Returns {duration, segments, captions}."""
    lang = lang_of(lang_code)
    os.makedirs(work_dir, exist_ok=True)
    segs, total = build_timeline(passages, clips, effects)

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
    src_index = {}
    for c in clips.values():
        if c["src"] not in src_index:
            src_index[c["src"]] = add_input("-i", c["src"])
    for s in segs:
        c = clips[s["clip"]]
        g += clip_chain(src_index[c["src"]], s["k"], c, s, preview)
    g.append("".join(f"[v{s['k']}]" for s in segs) + f"concat=n={len(segs)}:v=1:a=0[box]")
    box = "box"
    for j, an in enumerate(annotations or []):              # each one a PNG sequence, shifted to its moment
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
    fx = []
    for s in segs:
        sound = impact_sound(clips[s["clip"]], donor)
        if not sound:
            continue
        a = max(sound["start"], sound["impact"] - 0.35)
        b = min(sound["end"], sound["impact"] + 0.9)
        delay = int(max(0.0, s["impact_out"] - (sound["impact"] - a)) * 1000)
        g.append(f"[{src_index[sound['src']]}:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,"
                 f"afade=t=out:st={max(0.0, b - a - 0.3):.3f}:d=0.3,"
                 f"aformat=sample_rates=44100:channel_layouts=stereo,adelay={delay}:all=1[fx{s['k']}]")
        fx.append(f"[fx{s['k']}]")
    cuts = [s for s in segs if (s.get("fx") or {}).get("transition") and s["k"] > 0]
    if cuts:                            # a whoosh peaking on each transition's cut
        wi = add_input("-i", whoosh_wav(os.path.join(work_dir, "whoosh.wav")))
        g.append(f"[{wi}:a]aformat=sample_rates=44100:channel_layouts=stereo,asplit={len(cuts)}"
                 + "".join(f"[wh{j}]" for j in range(len(cuts))))
        for j, s in enumerate(cuts):
            g.append(f"[wh{j}]adelay={int(max(0.0, s['out'] - WHOOSH_PEAK) * 1000)}:all=1,volume=1.4[wd{j}]")
            fx.append(f"[wd{j}]")
    if fx:
        g.append("".join(fx) + f"amix=inputs={len(fx)}:normalize=0,volume={SFX_GAIN}[fx]")
        mix.append("[fx]")
    if music and music[0] and os.path.exists(music[0]):
        mi = add_input("-ss", f"{music[1]:.3f}", "-i", music[0])
        g.append(f"[{mi}:a]aformat=sample_rates=44100:channel_layouts=stereo,atrim=0:{total:.3f},"
                 f"afade=t=in:d=0.4,afade=t=out:st={max(0.0, total - 0.6):.3f}:d=0.6,volume={MUSIC_GAIN}[mus]")
        mix.append("[mus]")
    g.append("".join(mix) + f"amix=inputs={len(mix)}:duration=first:normalize=0,alimiter=limit=0.95,"
             f"aresample=48000,apad,atrim=0:{total:.3f}[aout]")

    # picture
    ci = add_input("-loop", "1", "-i", credit_file)
    ki = add_input("-loop", "1", "-i", corners)
    bi = [add_input("-loop", "1", "-i", b) for b in banners]
    g.append(f"color=black:s={W}x{H}:r={FPS}:d={total:.3f}[bgc]")
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
    _run(cmd, total, progress_cb)
    os.replace(tmp, out_path)
    return {"duration": round(total, 2), "captions": n_caps,
            "segments": [{"clip": s["clip"], "start": round(s["out"], 2), "end": round(s["out"] + s["dur"], 2),
                          "impact": round(s["impact_out"], 2)} for s in segs]}


def _run(cmd: Sequence[str], total: float, progress_cb) -> None:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in proc.stdout:
        m = re.match(r"out_time_us=(\d+)", line)
        if m and progress_cb and total > 0:
            progress_cb(min(1.0, int(m.group(1)) / 1e6 / total))
    err = proc.stderr.read()
    if proc.wait() != 0:
        raise RenderError(f"ffmpeg a échoué : {err.strip()[-600:]}")
    if progress_cb:
        progress_cb(1.0)
