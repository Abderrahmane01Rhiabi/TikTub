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
BANNER_KEY = "#FFD60A"
EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
MUSIC_GAIN = 0.16                                  # under a -16 LUFS voice
SFX_GAIN = 0.55


class RenderError(RuntimeError):
    pass


# --------------------------------------------------------------- timeline

def build_timeline(passages: List[Dict], clips: Dict[str, Dict]) -> Tuple[List[Dict], float]:
    """One segment per sentence: where its voice is cut from (va..vb), where
    it sits in the output, and which part of its clip plays under it."""
    segs, t = [], 0.0
    for k, p in enumerate(passages):
        a, b = max(0.0, p["start"] - 0.04), p["end"] + 0.10
        dur = (b - a) + GAP
        c = clips[p["clip"]]
        last = k == len(passages) - 1
        frac = 0.12 if k == 0 else (0.80 if last else 0.40)
        lead = min(0.9, dur * frac) if k == 0 else dur * frac
        ws = min(max(c["start"], c["impact"] - lead), max(c["start"], c["end"] - dur))
        segs.append({"k": k, "clip": p["clip"], "va": a, "vb": b, "out": t, "dur": dur, "ws": ws,
                     "impact_out": t + (c["impact"] - ws)})
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


def banner_parts(text: str) -> Tuple[List[Tuple[str, str]], Optional[str]]:
    """'HEAD : TAIL 😐' -> white head + yellow tail; no colon -> last word yellow."""
    clean, emoji = split_emoji(text)
    if ":" in clean:
        head, tail = clean.split(":", 1)
        return [(head.strip() + " : ", "white"), (tail.strip(), BANNER_KEY)], emoji
    ws = clean.split()
    if len(ws) > 1:
        return [(" ".join(ws[:-1]) + " ", "white"), (ws[-1], BANNER_KEY)], emoji
    return [(clean, BANNER_KEY)], emoji


def banner_png(text: str, path: str, lang: Dict) -> str:
    """Rounded dark box with a thin white border, sized to its text."""
    img = Image.new("RGBA", (W, 300), (0, 0, 0, 0))
    parts, emoji = banner_parts(text)
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
    d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), 22, fill=(14, 14, 16, 240), outline=(255, 255, 255, 220), width=3)
    _draw_runs(img, (W / 2, y0 + bh / 2 + 2), parts, font, lang["rtl"], emoji, size)
    img.save(path)
    return path


def credit_png(handles: str, path: str, lang: Dict) -> str:
    """'Images : @a · @b' — the Latin handles always stay left-to-right."""
    img = Image.new("RGBA", (W, 90), (0, 0, 0, 0))
    if handles:
        d = ImageDraw.Draw(img)
        font = ImageFont.truetype(font_path(lang["credit_font"]), 30)
        col = (170, 176, 188, 255)
        label = lang["credit_label"]
        kw = {"direction": "rtl", "language": "ar"} if lang["rtl"] else {}
        lw, hw = d.textlength(label, font=font, **kw), d.textlength(handles, font=font)
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


def captions_ass(passages: List[Dict], words: List[Dict], segs: List[Dict], path: str, lang: Dict) -> int:
    """1-3 words at a time, centred under the box, popping in; the sentence's
    keywords in its colour. Arabic: every word is its own colour run and the
    style's encoding is -1 (right-to-left base) — measured: with one multi-word
    run after a colour change, libass laid the words out left to right."""
    enc = -1 if lang["rtl"] else 1
    lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2", "",
             "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
             "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
             "MarginL, MarginR, MarginV, Encoding",
             f"Style: Cap,{lang['caption_font']},{lang['caption_size']},&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,"
             f"0,0,0,0,100,100,0,0,1,7,4,5,60,60,0,{enc}",
             "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    n = 0
    for k, p in enumerate(passages):
        colour = _ass_color(KEY_COLORS[k % len(KEY_COLORS)])
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
                    parts.append(f"{{\\c{colour if hit else '&H00FFFFFF&'}}}{word}")
                else:
                    parts.append(f"{{\\c{colour}}}{word}{{\\c&H00FFFFFF&}}" if hit else word)
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


def clip_chain(i: int, k: int, c: Dict, s: Dict) -> List[str]:
    """Filters turning clip c (input i) into segment k: [v{k}] BOX_W x BOX_H."""
    end = min(s["ws"] + s["dur"], c["end"])
    pad = s["dur"] - (end - s["ws"])
    T = s["impact_out"] - s["out"]
    punch = f"(1+0.07*exp(-pow((t-{T:.3f})/0.16,2)))"
    shake = f"9*sin(t*73)*exp(-pow((t-{T:.3f})/0.13,2))"
    pre = f"[{i}:v]trim={s['ws']:.3f}:{end:.3f},setpts=PTS-STARTPTS,fps={FPS}"
    if pad > 0.01:
        pre += f",tpad=stop_mode=clone:stop_duration={pad:.3f}"
    if c.get("crop"):
        pre += f",crop={c['crop']}"
    from adaptation.sources import delogo_filters
    for f in delogo_filters(c.get("delogo"), c["w"], c["h"]):
        pre += "," + f
    aspect, box_aspect = c["w"] / c["h"], BOX_W / BOX_H
    g = []
    if abs(math.log(aspect / box_aspect)) < 0.25:            # close to the box: fill it
        cover_w = _even(max(BOX_W, BOX_H * aspect) * 1.08)
        g.append(f"{pre},scale=w='{cover_w}*{punch}':h=-2:eval=frame:flags=bicubic,"
                 f"crop={BOX_W}:{BOX_H}:x='(iw-ow)/2+{shake}':y='(ih-oh)/2',setsar=1[v{k}]")
    else:                                                    # wide or tall: on a blurred copy of itself
        fw, fh = (BOX_W, _even(BOX_W / aspect)) if aspect > box_aspect else (_even(BOX_H * aspect), BOX_H)
        cover_w = _even(max(BOX_W, BOX_H * aspect) * 1.02)
        g.append(f"{pre},split[c{k}a][c{k}b]")
        g.append(f"[c{k}b]scale={cover_w}:-2,crop={BOX_W}:{BOX_H},boxblur=24:4,eq=brightness=-0.12[bg{k}]")
        g.append(f"[c{k}a]scale=w='{_even(fw * 1.04)}*{punch}':h=-2:eval=frame:flags=bicubic,"
                 f"crop={fw}:{fh}:x='(iw-ow)/2+{shake}':y='(ih-oh)/2'[fg{k}]")
        g.append(f"[bg{k}][fg{k}]overlay=(W-w)/2:(H-h)/2,setsar=1[v{k}]")
    return g


# --------------------------------------------------------------- render

def _filter_path(p: str) -> str:
    return os.path.abspath(p).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def render(passages: List[Dict], words: List[Dict], clips: Dict[str, Dict], voice_path: str, lang_code: str,
           out_path: str, work_dir: str, credit: str = "", music: Optional[Tuple[str, float]] = None,
           preview: bool = False, progress_cb=None) -> Dict:
    """passages: [{clip, bandeau, mots_cles, start, end, words: [word indices]}] with narration
    times; words: [{w, start, end}]; clips: id -> {src, start, end, impact, w, h, crop?,
    delogo?, audio_ok?}. Returns {duration, segments, captions}."""
    lang = lang_of(lang_code)
    os.makedirs(work_dir, exist_ok=True)
    segs, total = build_timeline(passages, clips)

    banners = [banner_png(p["bandeau"], os.path.join(work_dir, f"banner_{k}.png"), lang) for k, p in enumerate(passages)]
    credit_file = credit_png(credit, os.path.join(work_dir, "credit.png"), lang)
    corners = corners_png(os.path.join(work_dir, "corners.png"))
    ass = os.path.join(work_dir, "captions.ass")
    n_caps = captions_ass(passages, words, segs, ass, lang)

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
        g += clip_chain(src_index[c["src"]], s["k"], c, s)
    g.append("".join(f"[v{s['k']}]" for s in segs) + f"concat=n={len(segs)}:v=1:a=0[box]")

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

    # crash sounds: the clip's own, or one borrowed from a clip whose sound is clean
    donor = next((c for c in clips.values() if c.get("audio_ok")), None)
    fx = []
    for s in segs:
        c = clips[s["clip"]]
        sound = c if c.get("audio_ok") else donor
        if not sound:
            continue
        a = max(sound["start"], sound["impact"] - 0.35)
        b = min(sound["end"], sound["impact"] + 0.9)
        delay = int(max(0.0, s["impact_out"] - (sound["impact"] - a)) * 1000)
        g.append(f"[{src_index[sound['src']]}:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,"
                 f"afade=t=out:st={max(0.0, b - a - 0.3):.3f}:d=0.3,"
                 f"aformat=sample_rates=44100:channel_layouts=stereo,adelay={delay}:all=1[fx{s['k']}]")
        fx.append(f"[fx{s['k']}]")
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
    g.append(f"[bgc][box]overlay={BOX_X}:{BOX_Y}:shortest=1[p0]")
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
