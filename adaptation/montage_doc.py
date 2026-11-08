"""
The editable montage of a montage pro version (the person's idea, 2026-11-08: « show the montage as a timeline I can
change before publishing — the shots, the sound, the music's volume on one part, the captions, the frame »).

One document per version, t["montage"], says everything the render needs — the person changes it, the render follows:

  plans         the edit: [{phrase, plan (stock id), debut, fin, zoom (1 = as the AI framed it), centre (0-1, None =
                the shot's subject)}], back to back from 0, each cut on a word
  bandeaux      per sentence: {texte (None = the script's), cache}; bandeau_cadre: its box colours (None = the look's)
  sous_titres   {style (None = ours, else a caption library style), position, taille (%), mots {word index: text}}
  musique       {fichier, debut (in the song), volume (%), zones [{debut, fin, volume (%)}], fondu (s)}
  effets        [{kind, file, start (when the file begins), gain, pourquoi, par}]

Every version the person renders is kept (VERSIONS): « Annuler » goes back one, « Avant / Après » compares.
What the person sends is checked and made safe (clean): cuts snapped on words, nothing outside the video.
"""

import copy
import os
from typing import Dict, List, Optional

MIN_CUT_S = 1.0
VERSIONS = 20
POSITIONS = ("bas", "milieu", "haut")
CADRES = {"noir": ("#111111", "#FFFFFF"), "rouge": ("#D62828", "#FFFFFF"), "blanc": ("#FFFFFF", "#111111"),
          "bleu": ("#6D8DFD", "#FFFFFF")}
SOUND_KEYS = ("musique", "effets")      # a change only there: the picture is kept, only the sound is made again


class MontageError(Exception):
    pass


def new(edl: List[Dict], n_sentences: int, music_path: Optional[str], music_start: float, effets: List[Dict]) -> Dict:
    """The document of a montage the AI just made."""
    return {"plans": [{**e, "zoom": 1.0, "centre": None} for e in edl],
            "bandeaux": [{"texte": None, "cache": False} for _ in range(n_sentences)], "bandeau_cadre": None,
            "sous_titres": {"style": None, "position": "bas", "taille": 100, "mots": {}},
            "musique": {"fichier": music_path, "debut": float(music_start or 0.0), "volume": 100, "zones": [],
                        "fondu": 1.2},
            "effets": [{**e, "par": "ia"} for e in effets]}


def total(doc: Dict) -> float:
    return doc["plans"][-1]["fin"] if doc.get("plans") else 0.0


def _num(x, lo: float, hi: float, default: float) -> float:
    try:
        return min(hi, max(lo, float(x)))
    except (TypeError, ValueError):
        return default


def snap(t: float, starts: List[float]) -> float:
    """A cut on the nearest word's start."""
    return min(starts, key=lambda s: abs(s - t)) if starts else t


def clean(doc: Dict, voice: Dict, shot_ids: List[str], sfx_files: Optional[List[str]] = None) -> Dict:
    """The person's document made safe, or MontageError saying what is wrong (in French, for the screen)."""
    d = copy.deepcopy(doc)
    end = voice["passages"][-1]["end"] + 0.6 if voice.get("passages") else total(d)
    starts = [w["start"] for w in voice.get("words") or []]
    plans = sorted(d.get("plans") or [], key=lambda e: float(e.get("debut") or 0))
    if not plans:
        raise MontageError("Il faut au moins un plan.")
    out = []
    for k, e in enumerate(plans):
        if e.get("plan") not in shot_ids:
            raise MontageError(f"Plan {k + 1} : cette image n'est plus dans ton stock.")
        a = 0.0 if k == 0 else snap(_num(e.get("debut"), 0, end, 0), starts)
        out.append({"phrase": int(e.get("phrase") or 1), "plan": e["plan"], "debut": round(a, 2),
                    "zoom": round(_num(e.get("zoom"), 1.0, 1.6, 1.0), 2),
                    "centre": None if e.get("centre") is None else round(_num(e["centre"], 0, 1, 0.5), 3)})
    for k, e in enumerate(out):                     # back to back: each one ends where the next begins
        e["fin"] = round(out[k + 1]["debut"] if k + 1 < len(out) else end, 2)
        if e["fin"] - e["debut"] < MIN_CUT_S - 0.01:
            raise MontageError(f"Plan {k + 1} : trop court ({e['fin'] - e['debut']:.1f} s, au moins {MIN_CUT_S:.0f} s).")
    for e in out:                                   # its sentence: the one being said when it starts
        e["phrase"] = 1 + max((i for i, ps in enumerate(voice.get("passages") or []) if ps["start"] <= e["debut"] + 0.3),
                              default=0)
    d["plans"] = out
    n = len(voice.get("passages") or [])
    bs = (d.get("bandeaux") or [])[:n]
    d["bandeaux"] = [{"texte": None if b.get("texte") is None else str(b["texte"])[:60], "cache": bool(b.get("cache"))}
                     for b in bs] + [{"texte": None, "cache": False}] * (n - len(bs))
    if d.get("bandeau_cadre") not in CADRES:
        d["bandeau_cadre"] = None
    st = d.get("sous_titres") or {}
    d["sous_titres"] = {"style": st.get("style") or None,
                        "position": st.get("position") if st.get("position") in POSITIONS else "bas",
                        "taille": int(_num(st.get("taille"), 60, 160, 100)),
                        "mots": {str(int(k)): str(v)[:40] for k, v in (st.get("mots") or {}).items()
                                 if str(k).isdigit() and int(k) < len(voice.get("words") or []) and str(v).strip()}}
    m = d.get("musique") or {}
    zones = []
    for z in m.get("zones") or []:
        a, b = _num(z.get("debut"), 0, end, 0), _num(z.get("fin"), 0, end, 0)
        if b - a >= 0.3:
            zones.append({"debut": round(a, 2), "fin": round(b, 2), "volume": int(_num(z.get("volume"), 0, 200, 100))})
    d["musique"] = {"fichier": m.get("fichier") if m.get("fichier") and os.path.exists(m["fichier"]) else None,
                    "debut": round(_num(m.get("debut"), 0, 3600, 0), 2), "volume": int(_num(m.get("volume"), 0, 200, 100)),
                    "zones": sorted(zones, key=lambda z: z["debut"]), "fondu": round(_num(m.get("fondu"), 0, 5, 1.2), 2)}
    fx = []
    for e in d.get("effets") or []:
        f = e.get("file")
        if not f or (sfx_files is not None and f not in sfx_files) or not os.path.exists(f):
            continue
        fx.append({"kind": str(e.get("kind") or os.path.basename(f).split("_")[0]), "file": f,
                   "start": round(_num(e.get("start"), 0, end, 0), 3), "gain": round(_num(e.get("gain"), 0, 1.0, 0.3), 3),
                   "pourquoi": str(e.get("pourquoi") or "ajouté par toi")[:80], "par": e.get("par") or "toi"})
    d["effets"] = sorted(fx, key=lambda e: e["start"])
    return d


def sound_only(old: Optional[Dict], new_doc: Dict) -> bool:
    """Only the music or the effects changed: the picture already made is kept."""
    if not old:
        return False
    return all(old.get(k) == new_doc.get(k) for k in set(old) | set(new_doc) if k not in SOUND_KEYS)


def changed_at(old: Optional[Dict], new_doc: Dict) -> float:
    """Where the first change is (the player jumps there after the render)."""
    if not old:
        return 0.0
    for a, b in zip(old.get("plans") or [], new_doc.get("plans") or []):
        if a != b:
            return min(a["debut"], b["debut"])
    times = []
    for key in ("effets",):
        sa = {(e["start"], e["file"], e["gain"]) for e in old.get(key) or []}
        sb = {(e["start"], e["file"], e["gain"]) for e in new_doc.get(key) or []}
        times += [x[0] for x in sa ^ sb]
    za = {tuple(z.values()) for z in (old.get("musique") or {}).get("zones") or []}
    zb = {tuple(z.values()) for z in (new_doc.get("musique") or {}).get("zones") or []}
    times += [z[0] for z in za ^ zb]
    return round(min(times), 2) if times else 0.0


def push(t: Dict, doc: Dict) -> None:
    """The new document becomes the version's, the one before it kept for « Annuler »."""
    if t.get("montage"):
        t["montage_versions"] = ((t.get("montage_versions") or []) + [t["montage"]])[-VERSIONS:]
    t["montage"] = doc


def undo(t: Dict) -> Dict:
    versions = t.get("montage_versions") or []
    if not versions:
        raise MontageError("Rien à annuler.")
    t["montage"] = versions.pop()
    t["montage_versions"] = versions
    return t["montage"]
