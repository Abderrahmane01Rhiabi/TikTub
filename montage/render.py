"""
Builds the montage in one ffmpeg pass.

    image : kept ranges of the clip in a centered box with rounded corners on
            black; a black screen, then two drone shots, replace the IMAGE
            only — the voice runs on underneath
    text  : the hook drawn on the video near its top edge; cascade captions
            (one word per line, zigzag), optionally with keywords in a
            yellow serif italic with a glow ("accent")
    audio : the clip's own sound, untouched inside each kept range, plus the
            song: the build-up just BEFORE the chosen entry point plays under
            the setup and is cut dead on the black screen, the entry point
            lands when the image comes back, then the song runs on at the
            same level to the end (volume set relative to the voice)
"""

import os
import random
import re
import subprocess
import unicodedata
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from montage.recipes import recipe as recipe_of
from montage.transcribe import Words

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(HERE, "fonts")
FONT = os.path.join(FONTS_DIR, "Montserrat-SemiBold.ttf")
KEY_FONT = os.path.join(FONTS_DIR, "InstrumentSerif-Italic.ttf")
EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

W, H, FPS = 1080, 1920, 30
CAP_SIZE = 150
KEY_SCALE = 1.25        # the serif italic reads smaller: drawn a bit bigger
EPS = 0.001

Range = Tuple[float, float]


# ------------------------------------------------------------- plan checking

class Edit:
    """The plan once checked: kept source ranges, and the black screen /
    drones / punchline in SOURCE time (None when refused)."""

    def __init__(self, keep, noir, drones, chute):
        self.keep: List[Range] = keep
        self.noir: Optional[Range] = noir
        self.drones: Optional[Range] = drones
        self.chute: Optional[float] = chute
        self.notes: List[str] = []

    @property
    def total(self) -> float:
        return sum(b - a for a, b in self.keep)

    def to_out(self, t: float) -> Optional[float]:
        """source time -> output time, through the kept ranges"""
        off = 0.0
        for a, b in self.keep:
            if a - 0.05 <= t <= b + 0.05:
                return off + min(max(t, a), b) - a
            off += b - a
        return None

    def out_range(self, r: Optional[Range]) -> Optional[Range]:
        return (self.to_out(r[0]), self.to_out(r[1])) if r else None


def resolve_plan(plan: Dict, words: Words, rec: Dict, duration: Optional[float] = None) -> Edit:
    keep = []
    for r in plan.get("garder") or []:
        try:
            a, b = max(0.0, float(r["debut_s"])), float(r["fin_s"])
        except (KeyError, TypeError, ValueError):
            continue
        if duration:
            b = min(b, duration)
        if b - a > 0.3:
            keep.append((a, b))
    keep.sort()
    merged = []
    for a, b in keep:                      # overlapping ranges would play twice
        if merged and a < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    keep = merged or [(0.0, duration or ((words[-1][2] + 1.0) if words else 1.0))]
    edit = Edit(keep, None, None, None)

    def inside(a, b):
        return any(k0 - 0.05 <= a and b <= k1 + 0.05 for k0, k1 in keep)

    def span(key):
        s = plan.get(key)
        if not s:
            return None
        try:
            i, j = int(s["debut_mot"]), int(s["fin_mot"])
        except (KeyError, TypeError, ValueError):
            return None
        if not (0 <= i <= j < len(words)):
            edit.notes.append(f"{key} : mots hors limites, ignoré")
            return None
        return words[i][1], words[j][2]

    chute = plan.get("chute_s")
    if plan.get("chute_mot") is not None:
        try:
            if 0 <= int(plan["chute_mot"]) < len(words):
                chute = words[int(plan["chute_mot"])][1]
        except (TypeError, ValueError):
            pass
    try:
        edit.chute = float(chute) if chute is not None else None
    except (TypeError, ValueError):
        edit.chute = None

    bs = rec["black_screen"]
    noir = span("noir")
    if noir:
        a, b = noir
        b = min(b, a + bs["max"])
        if b - a < bs["min"] or not inside(a, b) or (edit.chute and b > edit.chute):
            edit.notes.append(f"écran noir {a:.2f}-{b:.2f} refusé (durée, hors passage gardé ou après la chute)")
        else:
            edit.noir = (a, b)

    dr = rec["drones"]
    drones = span("drones")
    if drones:
        a, b = drones
        if edit.chute:
            b = min(b, edit.chute)                    # never over the punchline
        a = max(a, b - dr["max_total"])
        min_total = dr["min_each"] * dr["count"]      # shorter reads as a glitch:
        if b - a < min_total:
            a = b - min_total                         # start earlier, end stays before the punchline
        if not inside(a, b) or (edit.noir and a < edit.noir[1]):
            edit.notes.append(f"drones {a:.2f}-{b:.2f} refusés (hors passage gardé ou avant la fin de l'écran noir)")
        else:
            edit.drones = (a, b)
    return edit


def drone_slots(edit: Edit, count: int) -> List[Range]:
    """Output-time slots of the drone shots, split evenly."""
    r = edit.out_range(edit.drones)
    if not r:
        return []
    a, b = r
    step = (b - a) / count
    return [(a + k * step, a + (k + 1) * step) for k in range(count)]


# --------------------------------------------------------------- geometry

def box_geometry(rec: Dict) -> Tuple[int, int, int, int]:
    bh = int(H * rec["frame_height"]) // 2 * 2
    bw = int(bh * 9 / 16) // 2 * 2
    return bw, bh, (W - bw) // 2, (H - bh) // 2


# ----------------------------------------------------------------- overlays

def _is_emoji(ch: str) -> bool:
    return unicodedata.category(ch) == "So" or ord(ch) >= 0x1F000


def _text_width(draw, text, font, size) -> float:
    return sum(size + 4 if _is_emoji(c) else draw.textlength(c, font=font) for c in text)


def _draw_runs(img, draw, x, y, text, font, efont, size):
    """Text + color emoji, left to right."""
    for ch in text:
        if _is_emoji(ch) and efont:
            e = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
            ImageDraw.Draw(e).text((0, 0), ch, font=efont, embedded_color=True)
            e = e.crop(e.getbbox() or (0, 0, 1, 1))
            e = e.resize((size, int(size * e.height / max(e.width, 1))), Image.LANCZOS)
            img.alpha_composite(e, (int(x), int(y + size * 0.12)))
            x += size + 4
        else:
            draw.text((x, y), ch, font=font, fill="white")
            x += draw.textlength(ch, font=font)


def frame_overlay(hook: Optional[str], path: str, rec: Dict) -> str:
    """Full-frame RGBA: black corners that round the box + the hook, drawn ON
    the video near its top edge with a soft shadow."""
    bw, bh, bx, by = box_geometry(rec)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    corners = Image.new("L", (bw, bh), 255)
    ImageDraw.Draw(corners).rounded_rectangle((0, 0, bw - 1, bh - 1), rec["corner_radius"], fill=0)
    img.paste(Image.new("RGBA", (bw, bh), (0, 0, 0, 255)), (bx, by), corners)

    if hook:
        efont = ImageFont.truetype(EMOJI_FONT, 109) if os.path.exists(EMOJI_FONT) else None
        d = ImageDraw.Draw(img)
        words = hook.split()
        for size in (84, 76, 68, 60, 52):
            font = ImageFont.truetype(FONT, size)
            fits = lambda text: _text_width(d, text, font, size) <= bw - 80
            if fits(hook):
                lines = [hook]
                break
            # two lines, balanced: "$100 if you can / say B 😂", never "... say / B 😂"
            splits = [(" ".join(words[:i]), " ".join(words[i:])) for i in range(1, len(words))]
            splits = [s for s in splits if fits(s[0]) and fits(s[1])]
            if splits:
                lines = list(min(splits, key=lambda s: max(_text_width(d, t, font, size) for t in s)))
                break
        else:
            lines = [hook]          # one huge word: let it overflow rather than vanish
        line_h = int(size * 1.2)
        text = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        td = ImageDraw.Draw(text)
        y = by + 45
        for line in lines:
            _draw_runs(text, td, (W - _text_width(td, line, font, size)) / 2, y, line, font, efont, size)
            y += line_h
        alpha = text.getchannel("A").filter(ImageFilter.GaussianBlur(6))
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        shadow.putalpha(alpha.point(lambda v: int(v * 0.75)))
        img.alpha_composite(shadow, (0, 3))
        img.alpha_composite(text)
    img.save(path)
    return path


def _ass_time(t: float) -> str:
    h, rem = divmod(max(t, 0), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def captions_ass(words: Words, edit: Edit, path: str, rec: Dict, burned: Sequence[Range] = (),
                 keywords: Sequence[int] = ()) -> int:
    """Cascade captions: each word appears when spoken, on its OWN line under
    the previous one, shifted left/right in a zigzag; the block empties at a
    sentence end, a pause, a cut between kept ranges, or after 5 words.
    burned: source ranges where the clip already shows its own text — no
    caption there, unless that image is hidden (black screen, drones).
    keywords: word indices drawn yellow serif italic with a glow."""
    bw, bh, bx, by = box_geometry(rec)
    keywords = set(keywords)
    hidden = [r for r in (edit.noir, edit.drones) if r]
    out = []
    for idx, (w, a, b) in enumerate(words):
        if any(s - 0.1 <= a <= e + 0.1 for s, e in burned) and not any(s <= a <= e for s, e in hidden):
            continue
        oa, ob = edit.to_out(a), edit.to_out(b)
        if oa is None or ob is None or ob <= oa:
            continue
        seg = next(i for i, (k0, k1) in enumerate(edit.keep) if k0 - 0.05 <= a <= k1 + 0.05)
        out.append((w, oa, ob, seg, idx in keywords))

    groups, cur = [], []
    for item in out:
        w, a, b, seg, key = item
        if cur and (len(cur) >= 5 or a - cur[-1][2] > 0.6 or seg != cur[-1][3]):
            groups.append(cur)
            cur = []
        cur.append(item)
        if w.endswith((".", "?", "!")):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)

    font = ImageFont.truetype(FONT, CAP_SIZE)
    key_font = ImageFont.truetype(KEY_FONT, int(CAP_SIZE * KEY_SCALE))
    measure = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
    step = int(CAP_SIZE * 0.78)
    lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "",
             "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
             "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
             "Alignment, MarginL, MarginR, MarginV, Encoding",
             f"Style: Cap,Montserrat SemiBold,{CAP_SIZE},&H00FFFFFF,&H00FFFFFF,&H00000000,&H70000000,"
             "0,0,0,0,100,100,-1,0,1,2,4,5,0,0,0,1",
             f"Style: Key,Instrument Serif,{int(CAP_SIZE * KEY_SCALE)},&H005CF2F7,&H005CF2F7,&H405CF2F7,&H00000000,"
             "0,-1,0,0,100,100,0,0,1,3,0,5,0,0,0,1", "",
             "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for g, grp in enumerate(groups):
        rng = random.Random(f"{g}-{grp[0][0]}")
        end = groups[g + 1][0][1] if g + 1 < len(groups) else grp[-1][2] + 0.5
        end = min(end, grp[-1][2] + 0.8)
        y = int(H * 0.47) - (len(grp) - 1) * step // 4   # long blocks start a bit higher
        side = rng.choice((-1, 1))
        for k, (w, a, _, _, key) in enumerate(grp):
            if k:   # a serif line needs more room above and below
                y += int(step * (1.2 if key or grp[k - 1][4] else 1.0))
            text = w.replace("{", "(").replace("}", ")").replace("\\", "")
            half = measure.textlength(text, font=key_font if key else font) / 2
            shift = 0 if k == 0 else side * rng.randint(40, 190)
            side = -side
            x = W / 2 + rng.randint(-40, 40) + shift
            x = min(max(x, bx + 50 + half), bx + bw - 50 - half)
            glow = r"\blur6" if key else ""      # blurred yellow border = the glow
            tags = rf"{{\an5\pos({int(x)},{y}){glow}\fscx70\fscy70\t(0,110,\fscx100\fscy100)}}"
            lines.append(f"Dialogue: 0,{_ass_time(a)},{_ass_time(end)},{'Key' if key else 'Cap'},,0,0,0,,{tags}{text}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return len(out)


# -------------------------------------------------------------------- audio

def rms_db(path: str, start: float = 0.0, dur: Optional[float] = None,
           ranges: Optional[Sequence[Range]] = None) -> float:
    """RMS level (dB) of `path` from `start` for `dur` s, or over `ranges`."""
    import numpy as np
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", path]
    if dur:
        cmd += ["-t", f"{dur:.3f}"]
    raw = subprocess.run(cmd + ["-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    if ranges:
        parts = [x[int(a * 8000):int(b * 8000)] for a, b in ranges]
        parts = [p for p in parts if len(p)]
        if parts:
            x = np.concatenate(parts)
    if not len(x):
        return -60.0
    return float(10 * np.log10((x ** 2).mean() + 1e-10))


def music_keypoints(total: float, noir: Optional[Range], level: float, ramp: float) -> List[Tuple[float, float]]:
    """[(t, gain)] in output time, linearly interpolated; (t, t+EPS) pairs are
    hard cuts. Bed -> dead cut for the black screen only -> back in `ramp`
    seconds -> same level to the end."""
    if not noir:
        return [(0, level), (total, level)]
    n0, n1 = noir
    return [(0, level), (n0, level), (n0 + EPS, 0.0), (n1, 0.0), (min(n1 + ramp, total), level), (total, level)]


def keypoints_expr(pts: List[Tuple[float, float]]) -> str:
    terms = []
    for (t0, g0), (t1, g1) in zip(pts, pts[1:]):
        if t1 <= t0 or (g0 == 0 and g1 == 0):
            continue
        val = f"{g0:.4f}" if g0 == g1 else f"({g0:.4f}+{g1 - g0:.4f}*(t-{t0:.3f})/{t1 - t0:.3f})"
        terms.append(f"gte(t,{t0:.3f})*lt(t,{t1:.3f})*{val}")
    return "+".join(terms) or "0"


# ------------------------------------------------------------------- render

def _filter_path(p: str) -> str:
    return os.path.abspath(p).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def render(video_path: str, words: Words, plan: Dict, settings: Dict, out_path: str,
           broll_paths: Sequence[str] = (), keywords: Sequence[int] = (), hook: Optional[str] = None,
           music_path: Optional[str] = None, work_dir: Optional[str] = None, preview: bool = False,
           progress_cb: Optional[Callable[[float], None]] = None) -> Dict:
    """Renders the montage to out_path. Returns a summary (duration, shots,
    music levels, notes about refused plan parts)."""
    from montage.planner import video_duration

    rec = recipe_of(settings)
    edit = resolve_plan(plan, words, rec, duration=video_duration(video_path))
    bw, bh, bx, by = box_geometry(rec)
    work = work_dir or os.path.dirname(os.path.abspath(out_path))
    os.makedirs(work, exist_ok=True)
    stem = os.path.join(work, os.path.splitext(os.path.basename(out_path))[0])

    overlay = frame_overlay(hook if settings.get("hook", True) else None, stem + "_overlay.png", rec)
    burned = []
    for t in plan.get("texte_incruste") or []:
        try:
            burned.append((float(t["debut_s"]), float(t["fin_s"])))
        except (KeyError, TypeError, ValueError):
            pass
    keys = keywords if settings.get("caption_style") == "accent" else ()
    n_caps = captions_ass(words, edit, stem + ".ass", rec, burned, keys)

    total = edit.total
    inputs = ["-i", video_path, "-loop", "1", "-i", overlay]
    g = []
    for k, (a, b) in enumerate(edit.keep):
        g.append(f"[0:v]trim={a:.3f}:{b:.3f},setpts=PTS-STARTPTS[v{k}]")
        g.append(f"[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS[a{k}]")
    n = len(edit.keep)
    g.append("".join(f"[v{k}][a{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=1[mv][ma]")
    g.append(f"[mv]fps={FPS},scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},setsar=1[box0]")
    cur, shots = "box0", []

    slots = drone_slots(edit, rec["drones"]["count"]) if broll_paths else []
    for k, ((s, e), clip) in enumerate(zip(slots, broll_paths)):
        idx = len([x for x in inputs if x == "-i"])
        inputs += ["-i", clip]
        g.append(f"[{idx}:v]trim=start=2:duration={e - s + 0.2:.3f},setpts=PTS-STARTPTS+{s:.3f}/TB,"
                 f"fps={FPS},scale=-2:{bh},crop={bw}:{bh},setsar=1[b{k}]")
        g.append(f"[{cur}][b{k}]overlay=0:0:eof_action=pass:enable='between(t,{s:.3f},{e:.3f})'[box{k + 1}]")
        cur = f"box{k + 1}"
        shots.append({"start": round(s, 2), "end": round(e, 2), "kind": "drone", "file": os.path.basename(clip)})
    noir = edit.out_range(edit.noir)
    if noir:
        g.append(f"[{cur}]drawbox=0:0:iw:ih:black:t=fill:enable='between(t,{noir[0]:.3f},{noir[1]:.3f})'[boxn]")
        cur = "boxn"
        shots.append({"start": round(noir[0], 2), "end": round(noir[1], 2), "kind": "noir"})

    audio_out, music = "[ma]", None
    if music_path and os.path.exists(music_path):
        entry = float(settings.get("music_entry") or 0.0)
        spoken = [(a, b) for w, a, b in words if any(k0 <= a and b <= k1 for k0, k1 in edit.keep)]
        voice_db = rms_db(video_path, ranges=spoken) if spoken else -20.0
        midx = len([x for x in inputs if x == "-i"])
        if noir:
            # the build-up just before `entry` plays under the setup and is cut
            # right as it would land; `entry` hits when the image comes back
            n0, n1 = noir
            pre = entry - n0
            inputs += ["-ss", f"{max(pre, 0):.3f}", "-t", f"{n0 - max(-pre, 0):.3f}", "-i", music_path,
                       "-ss", f"{entry:.3f}", "-i", music_path]
            delay_a = f"adelay={int(-pre * 1000)}:all=1," if pre < 0 else ""
            g.append(f"[{midx}:a]aformat=channel_layouts=stereo,{delay_a}apad[ma1]")
            g.append(f"[{midx + 1}:a]aformat=channel_layouts=stereo,adelay={int(n1 * 1000)}:all=1[ma2]")
            g.append("[ma1][ma2]amix=inputs=2:duration=longest:normalize=0[mraw]")
            song_db = rms_db(music_path, start=max(pre, 0), dur=max(n0, 1.0))
        else:
            inputs += ["-ss", f"{entry:.3f}", "-i", music_path]
            g.append(f"[{midx}:a]aformat=channel_layouts=stereo[mraw]")
            song_db = rms_db(music_path, start=entry, dur=max(total, 1.0))
        rel = rec["volumes"].get(settings.get("volume"), rec["volumes"]["doux"])
        level = 10 ** ((voice_db + rel - song_db) / 20)
        env = music_keypoints(total, noir, level, rec["music_return_ramp"])
        g.append(f"[mraw]volume='{keypoints_expr(env)}':eval=frame[mus]")
        g.append("[ma]aformat=channel_layouts=stereo[voice]")
        g.append("[voice][mus]amix=inputs=2:duration=first:normalize=0[mix]")
        audio_out = "[mix]"
        music = {"file": os.path.basename(music_path), "entry": entry, "voice_db": round(voice_db, 1),
                 "gain": round(level, 3), "keypoints": [(round(t, 2), round(v, 3)) for t, v in env]}

    g.append(f"color=black:s={W}x{H}:r={FPS}:d={total:.3f}[bg]")
    g.append(f"[bg][{cur}]overlay={bx}:{by}:shortest=1[c1]")
    g.append("[c1][1:v]overlay=0:0:shortest=1[c2]")
    final = "scale=540:960," if preview else ""
    g.append(f"[c2]subtitles='{_filter_path(stem + '.ass')}':fontsdir='{_filter_path(FONTS_DIR)}',{final}"
             f"format=yuv420p[outv]")

    enc = (["-preset", "ultrafast", "-crf", "30", "-c:a", "aac", "-b:a", "96k"] if preview else
           ["-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "160k"])
    tmp_out = out_path + ".part.mp4"
    cmd = ["ffmpeg", "-v", "error", "-y", "-nostats", "-progress", "pipe:1", *inputs,
           "-filter_complex", ";".join(g), "-map", "[outv]", "-map", audio_out, "-t", f"{total:.3f}",
           "-c:v", "libx264", *enc, "-movflags", "+faststart", tmp_out]
    _run_ffmpeg(cmd, total, progress_cb)
    os.replace(tmp_out, out_path)

    return {"duration": round(total, 2), "captions": n_caps, "shots": sorted(shots, key=lambda s: s["start"]),
            "keep": [(round(a, 2), round(b, 2)) for a, b in edit.keep], "music": music, "notes": edit.notes}


def _run_ffmpeg(cmd: List[str], total: float, progress_cb: Optional[Callable[[float], None]]) -> None:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in proc.stdout:
        m = re.match(r"out_time_us=(\d+)", line)
        if m and progress_cb and total > 0:
            progress_cb(min(1.0, int(m.group(1)) / 1e6 / total))
    err = proc.stderr.read()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg a échoué : {err.strip()[-500:]}")
    if progress_cb:
        progress_cb(1.0)
