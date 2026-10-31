"""
The music of a Reprise, chosen and placed like an editor would (lab etude_reprise/lab_musique.py, 2026-10-31):

    listen       Gemini listens to each song of the channel's list once (mood, what it suits, its strongest
                 moment); the loudness measured finds its REAL rises — loud after, coming from a part 4 dB calmer
                 (Gemini's section times drift by x1.5 past the first minute: not used) — kept in .analyses/ beside it
    choose       Gemini reads our Short (subject, tone, parts and when each starts) and picks the song, the part to
                 land on a rise (the reveal, the n°1, the moment of success) and the rise; a sad song on a funny
                 video is refused ("attention" when nothing fits)
    place        the song shifted so that rise falls at that part's start (up to 2 s of silence first is nothing; if
                 the song can't start before, a later real rise), set GAP dB under the voice, 2.5 dB more from the
                 rise on, faded in and out

The person's other choices (pipeline, `son`): his music (Demucs, his voice removed), our music (the channel's
track), no music; the level (dB under the voice) for every one.
"""

import base64
import json
import os
import re
import subprocess
from typing import Dict, List, Optional, Tuple

import numpy as np

RATE = 11025
VOICE_LUFS = -16.0               # our voice's level in a Reprise
GAP = 16.0                       # the music this many dB under the voice (chosen on the 5th Short, 2026-10-31)
LIFT = 1.33                      # +2.5 dB from the rise on
SONS = ("sa_musique", "notre_musique", "intelligente", "sans_musique")
EXTENSIONS = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")


class MusiqueError(RuntimeError):
    pass


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode:
        raise MusiqueError(r.stderr.decode(errors="replace")[-600:])
    return r


def lufs(path: str) -> float:
    out = subprocess.run(["ffmpeg", "-nostats", "-i", path, "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    found = re.findall(r"I:\s+(-?[\d.]+) LUFS", out)
    return float(found[-1]) if found else -70.0


def energy(path: str) -> np.ndarray:
    """Loudness every 0.1 s (dB), smoothed over 1 s."""
    x = np.frombuffer(_run(["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-ac", "1", "-ar", str(RATE), "-f", "f32le",
                            "-"]).stdout, np.float32)
    hop = RATE // 10
    n = len(x) // hop
    if not n:
        return np.zeros(1)
    db = 20 * np.log10(np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(axis=1) + 1e-10))
    return np.convolve(db, np.ones(10) / 10, mode="same")


def rises(e: np.ndarray, keep: float = 8.0) -> List[Tuple[float, float]]:
    """The song's real rises [(s, +dB)], the strongest first, 8 s apart: loud after (near its loudest parts),
    4 dB calmer before (not a drum hit inside a drop), never the file's first / last 5 s."""
    if len(e) < 120:
        return []
    jump = np.array([e[i + 5] - e[i - 1] if 50 <= i < len(e) - 55 else 0.0 for i in range(len(e))])
    loud = np.percentile(e, 90) - 5
    out: List[Tuple[float, float]] = []
    for i in np.argsort(-jump):
        if jump[i] <= 0 or len(out) >= 12:
            break
        t = round(float(i + 1) / 10, 1)
        after, before = e[i + 1:i + 41].mean(), e[max(0, i - 40):i].mean()
        if after >= loud and after - before >= 4.0 and all(abs(t - u) >= keep for u, _ in out):
            out.append((t, float(jump[i])))
    return out


def sharpen(e: np.ndarray, t: float, around: float = 2.0) -> float:
    """The exact instant it rises, near t: the biggest jump of loudness within ±2 s."""
    i0, i1 = max(1, int((t - around) * 10)), min(len(e) - 6, int((t + around) * 10))
    if i1 <= i0:
        return t
    jump = [e[i + 5] - e[i - 1] for i in range(i0, i1)]
    return round(float(i0 + int(np.argmax(jump)) + 1) / 10, 1)


# ---------------------------------------------------------------- listen

LISTEN = """Ecoute cette chanson comme un monteur video qui va la mettre sous un YouTube Short.
JSON uniquement :
{"humeur": "3 a 6 mots (ex: triste, nostalgique, puissante)", "energie_generale": 1-10,
 "convient_a": "le genre de video qu'elle porte bien (ex: histoire emouvante, transformation, reussite, humour)",
 "moment_fort": s, "pourquoi": "ce qui se passe a ce moment (la voix monte, la batterie arrive...)"}
Les secondes comptent depuis le debut du fichier. "moment_fort" = l'instant precis ou la chanson donne le plus
d'emotion (le debut du refrain ou du drop, la ou ca 'monte'), pas le milieu d'une section calme."""


def songs_of(music_dir: str) -> List[str]:
    if not os.path.isdir(music_dir):
        return []
    return sorted(os.path.join(music_dir, f) for f in os.listdir(music_dir) if f.lower().endswith(EXTENSIONS))


def _cache(path: str) -> str:
    return os.path.join(os.path.dirname(path), ".analyses", os.path.basename(path) + ".json")


def listen(path: str, gemini=None) -> Dict:
    """A song's analysis (kept beside it, made once): humeur, convient_a, moment_fort, montees, duree, titre."""
    cache = _cache(path)
    if os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(path):
        return json.load(open(cache, encoding="utf-8"))
    e = energy(path)
    r = {}
    if os.path.getsize(path) < 18 * 1024 * 1024:        # sent inline (a 4-minute mp3 is ~4 MB)
        from adaptation.sources import _gemini
        r = (gemini or _gemini())._generate_content(
            [{"inline_data": {"mime_type": "audio/mp3", "data": base64.b64encode(open(path, "rb").read()).decode()}},
             {"text": LISTEN}], max_tokens=3000, timeout=240, temperature=0.1) or {}
    duree = round(len(e) / 10, 1)
    out = {"titre": re.sub(r"\s*\[[\w-]+\]$", "", os.path.splitext(os.path.basename(path))[0]),   # not Gemini's guess
           "humeur": r.get("humeur"), "convient_a": r.get("convient_a"), "pourquoi": r.get("pourquoi"),
           "duree": duree, "montees": [t for t, _ in rises(e)]}
    try:
        mf = float(r.get("moment_fort"))
    except (TypeError, ValueError):
        mf = -1.0
    if 0 < mf < duree - 3:
        out["moment_fort"] = sharpen(e, mf)
    else:                                               # past the end (302 s of a 229 s song), or no answer
        out["moment_fort"] = out["montees"][0] if out["montees"] else round(duree / 3, 1)
        out["pourquoi"] = "la plus forte montée de volume mesurée"
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    json.dump(out, open(cache, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return out


# ---------------------------------------------------------------- choose

CHOOSE = """Tu es le monteur d'un YouTube Short. Voici le Short (notre version, avec notre voix) :
sujet : {sujet}
ton : {ton}
parties, dans l'ordre, avec le moment ou chacune commence :
{parties}
duree totale : {total:.0f} s

Chansons disponibles (chacune avec son moment fort et toutes ses vraies montees, en secondes de la chanson) :
{chansons}
La chanson ne peut pas commencer avant le debut du Short : une montee a M s de la chanson ne peut tomber que sur une
partie qui commence a M s ou avant (+2 s). Choisis une partie et une montee compatibles.

Choisis LA chanson qui porte le mieux ce Short (l'humeur doit coller au ton : une chanson triste sur une video drole
est un contresens), et LA partie du Short qui doit tomber sur sa montee (la revelation, le numero 1, la chute, le
moment de la reussite ou de l'emotion). Si aucune ne convient vraiment, dis-le dans "attention".
JSON uniquement : {{"chanson": numero, "partie": numero, "montee": s, "pourquoi_chanson": "...", "pourquoi_partie": "...",
"attention": "..."}}"""


def choose(sujet: str, ton: str, parts: List[Dict], total: float, songs: List[Dict], gemini=None) -> Dict:
    """parts: [{"role", "numero", "texte", "debut"}] -> Gemini's valid pick (asked again when cut)."""
    from adaptation.sources import _gemini
    g = gemini or _gemini()
    lines = "\n".join(f"  {k}. a {p['debut']:.1f} s, {p.get('role')}{' #' + str(p['numero']) if p.get('numero') else ''} : "
                      f"{p.get('texte', '')}" for k, p in enumerate(parts))
    chans = "\n".join(f"  {k}. {s.get('titre')} — humeur : {s.get('humeur')} ; convient a : {s.get('convient_a')} ; "
                      f"moment fort a {s.get('moment_fort')} s ({s.get('pourquoi')}) ; vraies montees a "
                      f"{sorted(s.get('montees') or [])} s ; duree {s.get('duree')} s" for k, s in enumerate(songs))
    for _ in range(2):
        r = g._generate_content([{"text": CHOOSE.format(sujet=sujet, ton=ton, parties=lines, total=total, chansons=chans)}],
                                max_tokens=6000, timeout=120, temperature=0.2)
        try:
            if isinstance(r, dict) and 0 <= int(r["chanson"]) < len(songs) and 0 <= int(r["partie"]) < len(parts):
                return r
        except (KeyError, TypeError, ValueError):
            pass
    raise MusiqueError("Gemini n'a pas choisi de chanson.")


def peak_for(song: Dict, hit: float, total: float, want: Optional[float] = None) -> Tuple[float, str]:
    """The rise of the song to put at `hit` s of the montage, and why."""
    ups = song.get("montees") or []
    if want is not None and want >= hit - 2.0 and any(abs(want - t) < 1.5 for t in ups):
        return min(ups, key=lambda t: abs(t - want)), "la montée choisie par Gemini"
    if song["moment_fort"] >= hit - 2.0:                # up to 2 s of silence first: the fade-in hides it
        return song["moment_fort"], "le moment fort de la chanson"
    ok = [t for t in ups if t >= hit - 2.0]
    fits = [t for t in ok if t + (total - hit) <= song["duree"]] or ok   # the song lasting to the end, if possible
    if fits:
        return min(fits), "une autre vraie montée, plus loin dans la chanson"
    return song["moment_fort"], "aucune montée assez tard : la chanson commence après un silence"


def plan(music_dir: str, sujet: str, ton: str, parts: List[Dict], total: float, gemini=None) -> Dict:
    """The song and where it goes: {"fichier", "titre", "montee", "partie", "a", "pourquoi_chanson", ...}."""
    paths = songs_of(music_dir)
    if not paths:
        raise MusiqueError("La chaîne n'a aucune musique dans sa liste.")
    songs = [listen(p, gemini) for p in paths]
    c = choose(sujet, ton, parts, total, songs, gemini)
    s, pi = songs[int(c["chanson"])], int(c["partie"])
    hit = parts[pi]["debut"]
    try:
        want = float(c.get("montee"))
    except (TypeError, ValueError):
        want = None
    peak, how = peak_for(s, hit, total, want)
    return {"fichier": os.path.basename(paths[int(c["chanson"])]), "titre": s["titre"], "montee": peak, "partie": pi,
            "a": round(hit, 2), "comment": how, "pourquoi_chanson": c.get("pourquoi_chanson"),
            "pourquoi_partie": c.get("pourquoi_partie"), "attention": c.get("attention") or ""}


# ---------------------------------------------------------------- the music bed

def bed(src: str, out: str, total: float, start: float = 0.0, pad: float = 0.0, gap: float = GAP,
        lift_at: Optional[float] = None) -> str:
    """A music bed of `total` s from src (from `start`, after `pad` s of silence), set `gap` dB under the voice,
    LIFT from `lift_at` on, faded in and out -> out (wav)."""
    cut = out + ".brut.wav"
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-stream_loop", "-1", "-i", src, "-af",
          f"atrim=start={start:.2f},asetpts=PTS-STARTPTS,adelay={int(pad * 1000)}:all=1,atrim=0:{total:.2f}",
          "-ar", "44100", "-ac", "2", cut])
    level = lufs(cut)
    gain = 10 ** ((VOICE_LUFS - gap - level) / 20) if level > -60 else 1.0
    lift = f",volume='if(gte(t,{lift_at:.2f}),{LIFT},1)':eval=frame" if lift_at is not None else ""
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", cut, "-af",
          f"volume={gain:.4f}{lift},afade=t=in:st=0:d=1.2,afade=t=out:st={max(0.0, total - 2.0):.2f}:d=2", out])
    os.remove(cut)
    return out


def placed_bed(music_dir: str, choice: Dict, total: float, out: str, gap: float = GAP) -> str:
    """The bed of the song chosen by plan(): its rise at choice["a"] s."""
    start = choice["montee"] - choice["a"]
    pad = 0.0
    if start < 0:
        pad, start = -start, 0.0
    return bed(os.path.join(music_dir, choice["fichier"]), out, total, start, pad, gap, lift_at=choice["a"])
