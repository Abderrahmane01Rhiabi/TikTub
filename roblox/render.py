"""
The five montage styles, rendered in one ffmpeg pass each (measured in etude_roblox/montage/, 2026-10-28).

    picture  the scene (16:9) in a frame in the middle, over the same scene blurred and darkened (9:16);
             a quick zoom on the face that reacts; a freeze frame for « Devine la suite »
    text     .ass captions in Montserrat (as the Montage auto): hook, POV line, the dialogue, the told story word
             by word (the word said in yellow), the top's numbers, the countdown
    sound    the original sound (or muted under a track of the channel), the ElevenLabs voice for the told story,
             the sound effects of assets/sfx

Each extract is its own ffmpeg input, opened at its start: trimming far parts of one input kept every frame in
between in memory (killed at 7.8 GB in the lab).
"""

import os
import subprocess
from typing import Callable, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H, FPS = 1080, 1920, 30
FG_W, FG_H, FG_Y = 1080, 810, 520
FONTS = os.path.join(HERE, "montage", "fonts")
SFX = {k: os.path.join(HERE, "assets", "sfx", f) for k, f in {
    "boom": "impact_boom_c_06.mp3", "whoosh": "whoosh_swoosh_1.mp3", "tick": "click_ui_click.mp3", "ding": "ding_bell_ding_1.mp3"}.items()}
JAUNE, BLANC = "&H0000F2FF", "&H00FFFFFF"
NOISE = {"h", "huh", "uh", "um", "hm", "ah", "oh"}
VOICE_GAIN, ORIGINAL_UNDER_VOICE, MUSIC_LEVEL = 1.35, 0.10, 0.30     # the lab's "la musique est un peu forte" fixed

Segment = Dict
Sound = Tuple[str, float, float]


class RenderError(RuntimeError):
    pass


# ------------------------------------------------------------------ text

def t_ass(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def esc(s) -> str:
    return str(s or "").replace("{", "(").replace("}", ")").replace("\n", " ").strip()


class Ass:
    STYLES = [("Titre", 82, BLANC, 8, 70, 215), ("Pov", 84, BLANC, 8, 70, 200), ("Cap", 74, BLANC, 8, 60, 1395),
              ("Mot", 98, BLANC, 8, 50, 1390), ("Rang", 230, JAUNE, 8, 40, 300), ("Label", 76, JAUNE, 8, 60, 1395),
              ("Gros", 460, JAUNE, 5, 0, 0), ("Question", 86, JAUNE, 8, 70, 215), ("Final", 84, JAUNE, 8, 70, 1395)]

    def __init__(self):
        self.events: List[str] = []

    def add(self, style: str, a: float, b: float, text: str) -> None:
        if b > a and text:
            self.events.append(f"Dialogue: 0,{t_ass(a)},{t_ass(b)},{style},,0,0,0,,{text}")

    def write(self, path: str) -> str:
        head = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0", "",
                "[V4+ Styles]", "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
                "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
                "MarginR, MarginV, Encoding"]
        for name, size, col, al, ml, mv in self.STYLES:
            head.append(f"Style: {name},Montserrat SemiBold,{size},{col},{col},&H00000000,&H90000000,1,0,0,0,100,100,0,0,1,"
                        f"{9 if size > 150 else 7},3,{al},{ml},{ml},{mv},1")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(head + ["", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
                                      "Effect, Text"] + self.events) + "\n")
        return path


def dialogue_lines(words, a: float, b: float) -> List[Dict]:
    """The lines said between a and b (seconds of the long video), five words at most, cut at a pause."""
    kept = [(w, s, e) for w, s, e in words if a <= s < b and not w.startswith("[") and w.lower().strip(".,!?") not in NOISE]
    out, cur = [], []
    for w, s, e in kept:
        if cur and (len(cur) >= 5 or s - cur[-1][2] > 0.6):
            out.append(cur)
            cur = []
        cur.append((w, s, e))
    if cur:
        out.append(cur)
    return [{"texte": " ".join(w for w, _, _ in l), "a": l[0][1], "b": l[-1][2] + 0.25} for l in out]


# ------------------------------------------------------------------ picture and sound

def _zoom(zooms) -> str:
    z = "+".join(f"0.30*min(1,max(0,(t-{a:.2f})/0.12))*lt(t,{b:.2f})" for a, b in zooms)
    return f"(1+{z})" if z else "1"


def build(segments: List[Segment], ass_path: str, sounds: List[Sound], out: str, music: Optional[str] = None) -> float:
    """segments: [{fichier, a, b, x, zooms: [(a, b)] from the segment's start, gel, sombre, vol}] (file times);
    sounds: [(file, at, volume)] on the final timeline. music: a track replacing the original sound."""
    inputs, g, total = [], [], 0.0
    for s in segments:
        inputs += ["-ss", f"{s['a']:.3f}", "-t", f"{s['b'] - s['a']:.3f}", "-i", s["fichier"]]
    for k, s in enumerate(segments):
        gel, x = s.get("gel", 0.0), min(1.0, max(0.0, float(s.get("x") or 0.5)))
        z = _zoom(s.get("zooms") or [])
        g.append(f"[{k}:v]setpts=PTS-STARTPTS,fps={FPS},format=yuv420p,split=2[b{k}][f{k}]")
        g.append(f"[b{k}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=28,eq=brightness=-0.22[bb{k}]")
        g.append(f"[f{k}]crop=w='min(iw,ih*4/3)':h=ih:x='(iw-min(iw,ih*4/3))*{x:.2f}':y=0,scale=w='trunc({FG_W}*{z}/2)*2':"
                 f"h='trunc({FG_H}*{z}/2)*2':eval=frame,crop={FG_W}:{FG_H}:(iw-{FG_W})/2:(ih-{FG_H})/2[ff{k}]")
        tail = f",tpad=stop_mode=clone:stop_duration={gel:.2f}" if gel else ""
        dark = ",eq=brightness=-0.18:saturation=0.55" if s.get("sombre") else ""
        g.append(f"[bb{k}][ff{k}]overlay=0:{FG_Y},setsar=1{tail}{dark}[v{k}]")
        vol = 0.0 if music else s.get("vol", 1.0)
        g.append(f"[{k}:a]asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo,volume={vol:.2f}"
                 + (f",apad=pad_dur={gel:.2f}" if gel else "") + f"[a{k}]")
        total += s["b"] - s["a"] + gel
    n = len(segments)
    g.append("".join(f"[v{k}][a{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=1[cv][ca]")
    g.append(f"[cv]subtitles='{ass_path}':fontsdir='{FONTS}',format=yuv420p[outv]")
    mix = ["[ca]"]
    extra = ([(music, 0.0, MUSIC_LEVEL)] if music else []) + list(sounds)
    for j, (f, at, vol) in enumerate(extra):
        idx = n + j
        inputs += (["-stream_loop", "-1"] if music and j == 0 else []) + ["-i", f]
        ms = int(max(0.0, at) * 1000)
        g.append(f"[{idx}:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={vol:.2f},adelay={ms}|{ms}[x{j}]")
        mix.append(f"[x{j}]")
    g.append("".join(mix) + f"amix=inputs={len(mix)}:duration=first:normalize=0,alimiter=limit=0.95[outa]")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    tmp = out + ".part.mp4"
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(g), "-map", "[outv]", "-map", "[outa]",
                        "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k",
                        "-movflags", "+faststart", tmp], capture_output=True, text=True)
    if r.returncode:
        raise RenderError(f"Rendu impossible ({r.returncode}) : {r.stderr[-600:]}")
    os.replace(tmp, out)
    return round(total, 2)


# ------------------------------------------------------------------ the styles

class Context:
    """What a style needs: the moments (by id), the long video's words, the language, the voice, a translator."""

    def __init__(self, moments: Dict[str, Dict], words, lang: str, source_lang: str, voice_id: Optional[str], work: str,
                 translate: Callable[[List[str], str], List[str]], synthesize: Optional[Callable] = None):
        self.moments, self.words, self.lang, self.source_lang = moments, words, lang, source_lang
        self.voice_id, self.work, self.translate = voice_id, work, translate
        self.synthesize = synthesize

    def moment(self, mid: str) -> Dict:
        return self.moments[mid]


def _captions(ctx: Context, ass: Ass, m: Dict, a: float, b: float, offset: float) -> None:
    """The lines said in [a, b] (file times of moment m), in the Short's language, placed at offset + (t - a)."""
    lines = dialogue_lines(ctx.words, m["t0"] + a, m["t0"] + b)
    texts = [l["texte"] for l in lines]
    if lines and ctx.lang != ctx.source_lang:
        texts = ctx.translate(texts, ctx.lang)
    for l, t in zip(lines, texts):
        ass.add("Cap", offset + l["a"] - m["t0"] - a, offset + l["b"] - m["t0"] - a, esc(t))


def clip(p: Dict, ctx: Context):
    m = ctx.moment(p["moment"])
    a, fin = m["debut"], min(m["fin"], m["chute"] + 2.0)
    reac = float(m.get("visage_reaction") or m["chute"])
    segs = [{"fichier": m["fichier"], "a": a, "b": fin, "x": m.get("action_x"), "zooms": [(reac - a, reac - a + 1.6)]}]
    ass = Ass()
    ass.add("Titre", 0, fin - a, esc(p["titre"][ctx.lang]))
    _captions(ctx, ass, m, a, fin, 0.0)
    return segs, ass, [(SFX["boom"], m["chute"] - a, 0.9)]


def pov(p: Dict, ctx: Context):
    m = ctx.moment(p["moment"])
    s, e = m["debut"] + p["debut"], m["debut"] + p["fin"]
    reac = float(m.get("visage_reaction") or m["chute"])
    segs = [{"fichier": m["fichier"], "a": s, "b": e, "x": m.get("action_x"), "zooms": [(reac - s, reac - s + 1.8)]}]
    ass = Ass()
    line = esc(p["pov"][ctx.lang])
    head, sep, rest = line.partition(":")
    ass.add("Pov", 0, e - s, f"{{\\c{JAUNE}}}{head}:{{\\c{BLANC}}}{rest}" if sep and len(head) <= 6 else line)
    return segs, ass, ([(SFX["boom"], m["chute"] - s, 0.9)] if s <= m["chute"] <= e else [])


def histoire(p: Dict, ctx: Context):
    from adaptation import voices
    mp3 = os.path.join(ctx.work, f"voix_histoire_{ctx.lang}.mp3")
    v = (ctx.synthesize or voices.synthesize)([{"texte": x["textes"][ctx.lang]} for x in p["passages"]], ctx.voice_id, ctx.lang, mp3)
    spans = [(x["start"], x["end"]) for x in v["passages"]]
    segs, ass, sounds, t = [], Ass(), [(mp3, 0.0, VOICE_GAIN)], 0.0
    for k, x in enumerate(p["passages"]):
        m = ctx.moment(x["moment"])
        dur = (spans[k + 1][0] if k + 1 < len(spans) else v["duration"] + 0.6) - (spans[k][0] if k else 0.0)
        start = min(m["debut"] + x["debut"], max(0.0, m["fichier_duree"] - dur - 0.05))
        segs.append({"fichier": m["fichier"], "a": start, "b": start + dur, "x": m.get("action_x"), "vol": ORIGINAL_UNDER_VOICE})
        if k:
            sounds.append((SFX["whoosh"], t - 0.15, 0.45))
        t += dur
    ass.add("Titre", 0, 2.6, esc(p["titre"][ctx.lang]))
    words = v["words"]
    for i in range(0, len(words), 3):
        chunk = words[i:i + 3]
        for j, w in enumerate(chunk):
            nxt = chunk[j + 1]["start"] if j + 1 < len(chunk) else (words[i + 3]["start"] if i + 3 < len(words) else w["end"] + 0.4)
            ass.add("Mot", w["start"], nxt, " ".join(f"{{\\c{JAUNE}}}{esc(c['w'])}{{\\c{BLANC}}}" if c is w else esc(c["w"]) for c in chunk))
    return segs, ass, sounds


def top3(p: Dict, ctx: Context):
    segs, ass, sounds, t = [], Ass(), [], 0.0
    for r in p["rangs"]:
        m = ctx.moment(r["moment"])
        s, e = m["debut"] + r["debut"], m["debut"] + r["fin"]
        hit = s <= m["chute"] <= e
        segs.append({"fichier": m["fichier"], "a": s, "b": e, "x": m.get("action_x"),
                     "zooms": [(m["chute"] - s, m["chute"] - s + 1.2)] if hit else []})
        sounds.append((SFX["whoosh"], t - 0.1, 0.55))
        ass.add("Rang", t, t + e - s, f"{{\\an5\\pos({W // 2},{FG_Y - 150})\\fscx130\\fscy130\\t(0,180,\\fscx100\\fscy100)}}#{r['rang']}")
        ass.add("Label", t, t + e - s, esc(r["label"][ctx.lang]))
        if r["rang"] == 1 and hit:
            sounds.append((SFX["boom"], t + m["chute"] - s, 0.9))
        t += e - s
    ass.add("Titre", 0, t, f"{{\\an8\\pos({W // 2},120)}}" + esc(p["titre"][ctx.lang]))
    return segs, ass, sounds


def devine(p: Dict, ctx: Context):
    m = ctx.moment(p["moment"])
    stop = m["debut"] + p["arret"]
    start, fin, gel = max(m["debut"], stop - 9.0), min(m["fin"], max(m["chute"], stop) + 2.5), 3.0
    x = m.get("action_x")
    segs = [{"fichier": m["fichier"], "a": start, "b": stop, "x": x},
            {"fichier": m["fichier"], "a": stop, "b": stop + 1 / FPS, "x": x, "gel": gel, "sombre": True, "vol": 0.0},
            {"fichier": m["fichier"], "a": stop, "b": fin, "x": x, "zooms": [(m["chute"] - stop, m["chute"] - stop + 1.4)]}]
    t_gel = stop - start
    t_rev = t_gel + 1 / FPS + gel
    total = t_rev + fin - stop
    ass = Ass()
    ass.add("Question", 0, t_rev, esc(p["question"][ctx.lang]))
    for k in range(3):
        ass.add("Gros", t_gel + k, t_gel + k + 0.9, f"{{\\fad(60,120)\\pos({W // 2},{FG_Y + FG_H // 2})}}{3 - k}")
    ass.add("Final", total - 2.2, total, esc(p["final"][ctx.lang]))
    sounds = [(SFX["tick"], t_gel + k, 1.0) for k in range(3)] + [(SFX["ding"], t_rev - 0.05, 0.7),
                                                                  (SFX["boom"], t_rev + m["chute"] - stop, 0.9)]
    return segs, ass, sounds


MAKERS = {"clip": clip, "pov": pov, "histoire": histoire, "top3": top3, "devine": devine}


def make(style: str, p: Dict, ctx: Context, out: str, music: Optional[str] = None) -> float:
    """One Short: the style's extracts, texts and sounds, rendered to out. Returns its duration."""
    segs, ass, sounds = MAKERS[style](p, ctx)
    path = ass.write(os.path.splitext(out)[0] + ".ass")
    return build(segs, path, sounds, out, music)
