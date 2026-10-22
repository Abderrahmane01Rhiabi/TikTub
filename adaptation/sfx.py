"""
Sound effects that follow what the picture does. No AI here: the montage has
already decided where an arrow or a circle appears, where the picture freezes,
where it slows down on the strong moment, where a figure shows, where the story
turns. Each of those has its sound, the way editors do it:

    arrow / circle appears        whoosh
    freeze frame                  camera shutter
    slow motion on the moment     a riser ending on it, then an impact (none if the
                                  clip's own crash is heard there)
    a figure appears              pop
    the main transition           whoosh (one only: on every cut, none stands out)

No ding on the last sentence: nothing says it is a reveal (on the cactus Short a ding
over a plain conclusion sounded out of place); the file stays for a moment marked as one.

At most MAX moments a video, GAP seconds apart, each sound's loudest instant
on its event, variants taken in turn (the same whoosh three times sounds cheap).
Measured before (2026-10-22): a noise "whoosh" made by the app, about 26 dB
under the voice and on every transition — hardly heard, or heard as a hiss.

The sounds are files in assets/sfx/<type>_<name>.mp3 (CC0, see LICENCES.md);
a type with no file is simply left out.
"""

import os
import subprocess
from typing import Dict, List, Optional, Set

FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "sfx")
MAX = 4                  # moments with a sound effect, a video
GAP = 3.0                # seconds between two of them
TURN = 0.4               # the main transition: the one nearest this share of the video
GAIN = {"whoosh": 0.32, "pop": 0.28, "click": 0.25, "shutter": 0.30, "riser": 0.22, "impact": 0.32, "ding": 0.22}
_PEAKS: Dict[str, float] = {}


def library(folder: str = FOLDER) -> Dict[str, List[str]]:
    """{type: [files]} from the folder's <type>_<name>.mp3 files."""
    out: Dict[str, List[str]] = {}
    if not os.path.isdir(folder):
        return out
    for name in sorted(os.listdir(folder)):
        if name.endswith((".mp3", ".wav")) and "_" in name:
            out.setdefault(name.split("_", 1)[0], []).append(os.path.join(folder, name))
    return out


def peak_of(path: str) -> float:
    """Seconds into the sound where it is loudest (a riser: at its end)."""
    if path not in _PEAKS:
        import numpy as np
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "8000", "-f", "f32le", "-"],
                             capture_output=True).stdout
        y = np.frombuffer(raw, np.float32)
        if not len(y):
            _PEAKS[path] = 0.0
        else:
            env = np.sqrt(np.convolve(y ** 2, np.ones(160) / 160, "same"))
            _PEAKS[path] = float(np.argmax(env)) / 8000
    return _PEAKS[path]


def plan(segs: List[Dict], annotations: List[Dict], numbers: List[Dict], total: float,
         own_crash: Optional[Set[int]] = None) -> List[Dict]:
    """The moments that get a sound: [{"kind", "t", "pourquoi"}], t where the
    sound must be loudest. segs: the render timeline (k, out, dur, impact_out, fx)."""
    own_crash = own_crash or set()
    wanted: List[Dict] = []             # in order of importance
    for an in annotations:
        wanted.append({"t": an["start"] + 0.05, "sons": ["whoosh"], "pourquoi": "flèche / cercle"})
    for s in segs:
        fx = s.get("fx") or {}
        if fx.get("arret"):
            wanted.append({"t": s["impact_out"], "sons": ["shutter"], "pourquoi": "arrêt sur image"})
    for s in segs:
        fx = s.get("fx") or {}
        if fx.get("ralenti") and not fx.get("arret"):
            sons = ["riser"] + ([] if s["k"] in own_crash else ["impact"])
            wanted.append({"t": s["impact_out"], "sons": sons, "pourquoi": "ralenti sur le moment fort"})
    for nb in numbers:
        wanted.append({"t": nb["start"] + 0.05, "sons": ["pop"], "pourquoi": "chiffre"})
    cuts = [s for s in segs if s["k"] > 0 and (s.get("fx") or {}).get("transition")]
    if cuts:
        main = min(cuts, key=lambda s: abs(s["out"] - TURN * total))
        wanted.append({"t": main["out"], "sons": ["whoosh"], "pourquoi": "transition principale"})
    kept: List[Dict] = []
    for w in wanted:
        if len(kept) >= MAX:
            break
        if 0.0 <= w["t"] < total - 0.3 and all(abs(w["t"] - k["t"]) >= GAP for k in kept):
            kept.append(w)
    return sorted(kept, key=lambda w: w["t"])


def sounds(moments: List[Dict], lib: Optional[Dict[str, List[str]]] = None) -> List[Dict]:
    """Each moment's files, variants in turn: [{"kind", "file", "start", "gain", "pourquoi"}],
    start = when the file begins (its loudest instant on the moment)."""
    lib = library() if lib is None else lib
    used: List[str] = []
    out = []
    for m in moments:
        for kind in m["sons"]:
            files = lib.get(kind) or []
            if not files:
                continue
            order = sorted(files, key=used.count)           # the least used first: each variant in turn
            # a variant whose loudest instant fits before the event (a circle at 0.48 s got a whoosh peaking at 0.63 s)
            f = next((x for x in order if peak_of(x) <= m["t"]), order[0])
            used.append(f)
            out.append({"kind": kind, "file": f, "start": round(max(0.0, m["t"] - peak_of(f)), 3),
                        "gain": GAIN.get(kind, 0.25), "pourquoi": m["pourquoi"]})
    return out
