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

The sounds are files in assets/sfx/<type>_<name>.mp3 (CC0, see LICENCES.md),
plus the ones added in Réglages → Effets sonores (sfx_perso/ in the data folder);
a sound can be turned off there; a type with no file is simply left out.
"""

import json
import os
import re
import subprocess
import tempfile
from typing import Dict, List, Optional, Set

FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "sfx")
USER_FOLDER = "sfx_perso"        # in the data folder (the app's working directory)
# the types a rule plays, and when — a sound of another type is never played
RULES = {"whoosh": "une flèche ou un cercle apparaît ; la transition principale",
         "shutter": "arrêt sur image",
         "riser": "la montée juste avant le ralenti sur le moment fort",
         "impact": "le coup sur le moment fort au ralenti",
         "pop": "un chiffre apparaît"}
MAX_LEN = 4.0                    # seconds kept of an added sound
EXTENSIONS = (".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac")
MAX = 4                  # moments with a sound effect, a video
GAP = 3.0                # seconds between two of them
TURN = 0.4               # the main transition: the one nearest this share of the video
GAIN = {"whoosh": 0.32, "pop": 0.28, "click": 0.25, "shutter": 0.30, "riser": 0.22, "impact": 0.32, "ding": 0.22}
_PEAKS: Dict[str, float] = {}


def _files(folder: str) -> List[str]:
    if not os.path.isdir(folder):
        return []
    return [os.path.join(folder, n) for n in sorted(os.listdir(folder)) if n.endswith((".mp3", ".wav")) and "_" in n]


def library(folder: Optional[str] = None) -> Dict[str, List[str]]:
    """{type: [files]} from the <type>_<name>.mp3 files: the app's and the added
    ones, without those turned off (or only `folder`'s, as they are)."""
    off = set() if folder else set(_state()["off"])
    out: Dict[str, List[str]] = {}
    for path in _files(folder) if folder else _files(FOLDER) + _files(USER_FOLDER):
        name = os.path.basename(path)
        if name not in off:
            out.setdefault(name.split("_", 1)[0], []).append(path)
    return out


# ------------------------------------------------------------------ Réglages → Effets sonores

def _state() -> Dict:
    try:
        with open(os.path.join(USER_FOLDER, "reglages.json"), encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        st = {}
    return {"off": st.get("off") or [], "infos": st.get("infos") or {}}


def _save_state(st: Dict) -> None:
    os.makedirs(USER_FOLDER, exist_ok=True)
    with open(os.path.join(USER_FOLDER, "reglages.json"), "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def _duration(path: str) -> Optional[float]:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                             capture_output=True, text=True, timeout=20).stdout.strip()
        return round(float(out), 2)
    except (ValueError, OSError, subprocess.SubprocessError):
        return None


def _app_pages() -> Dict[str, str]:
    """The freesound page of each of the app's sounds, from LICENCES.md
    ("whoosh_whip_1.mp3 … whoosh_whip_5.mp3" covers the five)."""
    pages: Dict[str, str] = {}
    try:
        with open(os.path.join(FOLDER, "LICENCES.md"), encoding="utf-8") as f:
            rows = [l.split("|") for l in f if l.startswith("|")]
    except OSError:
        return pages
    for cells in rows:
        if len(cells) < 6 or not cells[-2].strip().startswith("http"):
            continue
        names = re.findall(r"[\w-]+\.mp3", cells[1])
        span = [re.search(r"^(.*?)(\d+)\.mp3$", x) for x in names]
        if len(names) == 2 and "…" in cells[1] and all(span):
            names = [f"{span[0].group(1)}{k}.mp3" for k in range(int(span[0].group(2)), int(span[1].group(2)) + 1)]
        for n in names:
            pages[n] = cells[-2].strip()
    return pages


def catalog() -> List[Dict]:
    """Every sound, for Réglages: its type, when the montage plays it (or that
    it never does), whether it is on, added by hand, and where it comes from."""
    st, out, pages = _state(), [], _app_pages()
    for path, perso in [(x, False) for x in _files(FOLDER)] + [(x, True) for x in _files(USER_FOLDER)]:
        name = os.path.basename(path)
        kind = name.split("_", 1)[0]
        info = st["infos"].get(name) or ({} if perso else {"source": pages.get(name, ""), "licence": "CC0"})
        out.append({"name": name, "type": kind, "perso": perso, "actif": name not in st["off"],
                    "regle": RULES.get(kind), "duree": _duration(path),
                    "source": info.get("source") or "", "licence": info.get("licence") or ""})
    return out


def path_of(name: str) -> str:
    for path in _files(FOLDER) + _files(USER_FOLDER):
        if os.path.basename(path) == name:
            return path
    raise ValueError("Son introuvable.")


def set_active(name: str, on: bool) -> None:
    path_of(name)
    st = _state()
    st["off"] = [x for x in st["off"] if x != name] + ([] if on else [name])
    _save_state(st)


def add(src: str, kind: str, label: str, source: str = "", licence: str = "") -> str:
    """Adds a sound of a type a rule plays, made like the app's own: the silence
    at its start cut (its loudest instant is what lands on the event), at most
    MAX_LEN seconds, its peak at -1 dBFS, in mp3. Returns its file name."""
    if kind not in RULES:
        raise ValueError("Ce type de son n'est joué par aucune règle du montage.")
    slug = re.sub(r"[^a-z0-9]+", "_", (label or "son").lower()).strip("_")[:40] or "son"
    taken = {os.path.basename(x) for x in _files(FOLDER) + _files(USER_FOLDER)}
    name, n = f"{kind}_{slug}.mp3", 2
    while name in taken:
        name, n = f"{kind}_{slug}_{n}.mp3", n + 1
    os.makedirs(USER_FOLDER, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        cut = os.path.join(tmp, "cut.wav")
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-ac", "2", "-ar", "44100",
                            "-af", "silenceremove=start_periods=1:start_threshold=-50dB", "-t", str(MAX_LEN), cut],
                           capture_output=True, text=True)
        if r.returncode or not _duration(cut):
            raise ValueError("Ce fichier ne se lit pas comme un son.")
        peak = subprocess.run(["ffmpeg", "-v", "info", "-i", cut, "-af", "volumedetect", "-f", "null", "-"],
                              capture_output=True, text=True).stderr
        m = re.search(r"max_volume:\s*(-?[\d.]+) dB", peak)
        gain = -1.0 - float(m.group(1)) if m else 0.0
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", cut, "-af", f"volume={gain:.2f}dB",
                        "-codec:a", "libmp3lame", "-q:a", "2", os.path.join(USER_FOLDER, name)], check=True)
    st = _state()
    st["infos"][name] = {"source": source.strip(), "licence": licence.strip()}
    _save_state(st)
    return name


def remove(name: str) -> None:
    """Deletes an added sound (the app's own can only be turned off)."""
    path = path_of(name)
    if os.path.dirname(os.path.abspath(path)) != os.path.abspath(USER_FOLDER):
        raise ValueError("Les sons de l'app ne se suppriment pas : désactive-le.")
    os.remove(path)
    st = _state()
    st["infos"].pop(name, None)
    st["off"] = [x for x in st["off"] if x != name]
    _save_state(st)


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
         own_crash: Optional[Set[int]] = None, rules: Optional[Dict] = None,
         available: Optional[Set[str]] = None) -> List[Dict]:
    """The moments that get a sound: [{"kind", "t", "pourquoi"}], t where the
    sound must be loudest. segs: the render timeline (k, out, dur, impact_out, fx).
    rules: the subject's tone's ({"max", "types"}: a calm subject keeps almost
    none); available: the types that have a sound switched on — a moment whose
    sounds are all off takes no place (a slow motion once blocked a whoosh
    with its riser and impact turned off)."""
    own_crash = own_crash or set()
    rules = rules or {}
    most = rules.get("max", MAX)
    allowed = rules.get("types")
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
        w["sons"] = [x for x in w["sons"] if (allowed is None or x in allowed) and (available is None or x in available)]
        if not w["sons"]:
            continue
        if len(kept) >= most:
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
