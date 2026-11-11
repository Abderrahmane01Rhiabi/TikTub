"""
The editable montage of a montage pro version (the person's idea, 2026-11-08: « show the montage as a timeline I can
change before publishing — the shots, the sound, the music's volume on one part, the captions, the frame »).

One document per version, t["montage"], says everything the render needs — the person changes it, the render follows:

  plans         the edit: [{phrase, plan (stock id), debut, fin, zoom (1 = as the AI framed it), centre (0-1, None =
                the shot's subject)}], back to back from 0, each cut on a word
  bandeaux      per sentence: {texte (None = the script's), cache, cadre (its own box, else bandeau_cadre)};
                bandeau_cadre: every banner's box colours (None = the look's)
  sous_titres   {style (None = ours, else a caption library style), position, taille (%), mots {word index: text},
                groupes {first word index: {style, position, taille}} — one group of 3 words set apart}
  musique       {fichier, debut (in the song), volume (%), zones [{debut, fin, volume (%)}], fondu (s)}
  effets        [{kind, file, start (when the file begins), gain, pourquoi, par}]
  incrustation  the hook's animated number laid over its picture (adaptation/graphiques): {fichier, phrase, cache}
                or None — the person only shows or hides it

Every version the person renders is kept (VERSIONS): « Annuler » goes back one, « Avant / Après » compares.
What the person sends is checked and made safe (clean): cuts snapped on words, nothing outside the video.
"""

import copy
import os
from typing import Dict, List, Optional

MIN_CUT_S = 0.5                 # the director's quick cuts on a list of names (montage_pro.RAFALE_S)
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
            raise MontageError(f"Plan {k + 1} : trop court ({e['fin'] - e['debut']:.1f} s, au moins {MIN_CUT_S:.1f} s).")
    for e in out:                                   # its sentence: the one being said when it starts
        e["phrase"] = 1 + max((i for i, ps in enumerate(voice.get("passages") or []) if ps["start"] <= e["debut"] + 0.3),
                              default=0)
    d["plans"] = out
    n = len(voice.get("passages") or [])
    bs = (d.get("bandeaux") or [])[:n]
    d["bandeaux"] = [{"texte": None if b.get("texte") is None else str(b["texte"])[:60], "cache": bool(b.get("cache"))}
                     | ({"cadre": b["cadre"]} if b.get("cadre") in CADRES or b.get("cadre") == "style" else {})   # its own box
                     for b in bs] + [{"texte": None, "cache": False}] * (n - len(bs))
    if d.get("bandeau_cadre") not in CADRES:
        d["bandeau_cadre"] = None
    st = d.get("sous_titres") or {}
    nw = len(voice.get("words") or [])
    d["sous_titres"] = {"style": st.get("style") or None,
                        "position": st.get("position") if st.get("position") in POSITIONS else "bas",
                        "taille": int(_num(st.get("taille"), 60, 160, 100)),
                        "mots": {str(int(k)): str(v)[:40] for k, v in (st.get("mots") or {}).items()
                                 if str(k).isdigit() and int(k) < nw and str(v).strip()}}
    groups = {}                                     # one group of words (key: its first word) set apart from the rest
    for k, g in (st.get("groupes") or {}).items():
        if not str(k).isdigit() or int(k) >= nw or not isinstance(g, dict):
            continue
        x = {}
        if "style" in g:
            x["style"] = g["style"] or None
        if g.get("position") in POSITIONS:
            x["position"] = g["position"]
        if g.get("taille") is not None:
            x["taille"] = int(_num(g["taille"], 60, 160, 100))
        if x:
            groups[str(int(k))] = x
    if groups:
        d["sous_titres"]["groupes"] = groups
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


def _remap(t: float, old: List[Dict], new: List[Dict]) -> float:
    """A moment of the old voice at the same place of the same sentence in the new voice (a sentence said again
    lasts a little more or less: what was a third into it stays a third into it)."""
    o = [p["start"] for p in old] + [old[-1]["end"] + 0.6]
    n = [p["start"] for p in new] + [new[-1]["end"] + 0.6]
    k = max((i for i in range(len(old)) if o[i] <= t), default=0)
    r = (t - o[k]) / max(0.01, o[k + 1] - o[k])
    return round(n[k] + max(0.0, min(1.0, r)) * (n[k + 1] - n[k]), 3)


def retime(doc: Dict, old_voice: Dict, new_voice: Dict, changed: List[int]) -> Dict:
    """The montage moved onto a new narration (one sentence's text or manner changed: the whole voice is made again):
    cuts, sounds and music zones at the same place of their sentence; the word fixes kept where the sentence did
    not change (a changed sentence's words are new). Cuts are snapped on the new words by clean()."""
    old, new = old_voice["passages"], new_voice["passages"]
    if len(old) != len(new):
        raise MontageError("La voix refaite n'a plus le même nombre de phrases.")
    d = copy.deepcopy(doc)
    for e in d["plans"]:
        e["debut"] = _remap(e["debut"], old, new)
    for e in d.get("effets") or []:
        e["start"] = _remap(e["start"], old, new)
    for z in (d.get("musique") or {}).get("zones") or []:
        z["debut"], z["fin"] = _remap(z["debut"], old, new), _remap(z["fin"], old, new)
    fixes = (d.get("sous_titres") or {}).get("mots") or {}
    kept = {}
    for k, (po, pn) in enumerate(zip(old, new)):
        if k in changed or len(po["words"]) != len(pn["words"]):
            continue
        for wo, wn in zip(po["words"], pn["words"]):
            if str(wo) in fixes:
                kept[str(wn)] = fixes[str(wo)]
    if d.get("sous_titres") is not None:
        d["sous_titres"]["mots"] = kept
    return d


def _fmt(t) -> str:
    t = float(t or 0)
    return f"{int(t // 60)}:{t % 60:04.1f}"


MOVED = 0.3                 # a cut or a sound moved by less: the voice said again moved it, not the person


def changes(ai: Dict, final: Dict, texts_before: Optional[List[str]] = None, texts_after: Optional[List[str]] = None,
            manners_before: Optional[List[str]] = None, manners_after: Optional[List[str]] = None) -> List[Dict]:
    """What the person changed from the AI's montage to the final one, element by element ({element, quoi}, in
    French) — for the recipe (the Dashboard sees what is corrected most) and the timeline."""
    out: List[Dict] = []
    add = lambda element, quoi: out.append({"element": element, "quoi": quoi})
    a, b = ai.get("plans") or [], final.get("plans") or []
    if len(a) != len(b):
        add("images", f"{abs(len(b) - len(a))} plan(s) {'ajouté(s)' if len(b) > len(a) else 'supprimé(s)'} ({len(a)} → {len(b)})")
    for k, (x, y) in enumerate(zip(a, b), 1):
        if x.get("plan") != y.get("plan"):
            add("images", f"Plan {k} remplacé ({x.get('plan')} → {y.get('plan')})")
        if (x.get("zoom") or 1) != (y.get("zoom") or 1) or x.get("centre") != y.get("centre"):
            add("images", f"Plan {k} recadré (zoom ×{y.get('zoom') or 1}" + (f", centre {y['centre']}" if y.get("centre") is not None else "") + ")")
        if k > 1 and abs((x.get("debut") or 0) - (y.get("debut") or 0)) > MOVED and len(a) == len(b):
            add("images", f"Coupe du plan {k} déplacée ({_fmt(x.get('debut'))} → {_fmt(y.get('debut'))})")
    for k, (x, y) in enumerate(zip(ai.get("bandeaux") or [], final.get("bandeaux") or []), 1):
        if bool(x.get("cache")) != bool(y.get("cache")):
            add("bandeau", f"Bandeau {k} {'enlevé' if y.get('cache') else 'remis'}")
        if x.get("texte") != y.get("texte") and not y.get("cache"):
            add("bandeau", f"Bandeau {k} réécrit : « {y.get('texte')} »")
        if x.get("cadre") != y.get("cadre"):
            add("bandeau", f"Cadre du bandeau {k} : {y.get('cadre') or 'celui de la vidéo'}")
    ia, ib = ai.get("incrustation") or {}, final.get("incrustation") or {}
    if ia and bool(ia.get("cache")) != bool(ib.get("cache")):
        add("images", f"Chiffre animé de l'accroche {'enlevé' if ib.get('cache') else 'remis'}")
    if ai.get("bandeau_cadre") != final.get("bandeau_cadre"):
        add("bandeau", f"Cadre de tous les bandeaux : {final.get('bandeau_cadre') or 'celui du style'}")
    sa, sb = ai.get("sous_titres") or {}, final.get("sous_titres") or {}
    for key, label in (("style", "Style"), ("position", "Position"), ("taille", "Taille")):
        if sa.get(key) != sb.get(key):
            add("sous-titres", f"{label} des sous-titres : {sb.get(key) or 'les nôtres'}")
    fixed = set((sb.get("mots") or {})) - set((sa.get("mots") or {}))
    if fixed:
        add("sous-titres", f"{len(fixed)} mot(s) corrigé(s) : " + ", ".join((sb.get("mots") or {})[w] for w in sorted(fixed, key=int))[:120])
    if (sb.get("groupes") or {}) != (sa.get("groupes") or {}):
        add("sous-titres", f"{len(sb.get('groupes') or {})} groupe(s) avec leur propre look")
    ma, mb = ai.get("musique") or {}, final.get("musique") or {}
    if ma.get("fichier") != mb.get("fichier"):
        add("musique", f"Chanson changée : {os.path.basename(mb.get('fichier') or '') or 'sans musique'}")
    if ma.get("debut") != mb.get("debut"):
        add("musique", f"Départ dans la chanson : {_fmt(ma.get('debut'))} → {_fmt(mb.get('debut'))}")
    if ma.get("volume") != mb.get("volume"):
        add("musique", f"Volume général : {ma.get('volume')} % → {mb.get('volume')} %")
    if ma.get("fondu") != mb.get("fondu"):
        add("musique", f"Fondu de fin : {mb.get('fondu')} s")
    za = {(z["debut"], z["fin"], z["volume"]) for z in ma.get("zones") or []}
    for z in mb.get("zones") or []:
        if (z["debut"], z["fin"], z["volume"]) not in za:
            add("musique", f"Zone de volume {_fmt(z['debut'])} → {_fmt(z['fin'])} à {z['volume']} %")
    ea = [(os.path.basename(e["file"]), e["start"]) for e in ai.get("effets") or []]
    eb = [(os.path.basename(e["file"]), e["start"]) for e in final.get("effets") or []]
    near = lambda x, ys: any(x[0] == y[0] and abs(x[1] - y[1]) <= MOVED for y in ys)
    for f, t in sorted((x for x in eb if not near(x, ea)), key=lambda x: x[1]):
        add("effets", f"Son {f.split('_')[0]} à {_fmt(t)} (ajouté ou déplacé)")
    for f, t in sorted((x for x in ea if not near(x, eb)), key=lambda x: x[1]):
        add("effets", f"Son {f.split('_')[0]} à {_fmt(t)} retiré ou déplacé")
    for k, (x, y) in enumerate(zip(texts_before or [], texts_after or []), 1):
        if x != y:
            add("voix", f"Phrase {k} réécrite : « {x} » → « {y} »")
    for k, (x, y) in enumerate(zip(manners_before or [], manners_after or []), 1):
        if (x or "") != (y or ""):
            add("voix", f"Phrase {k} : manière {x or 'normale'} → {y or 'normale'}")
    return out
