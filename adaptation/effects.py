"""
Montage effects decided per plan, like the arrows: what a pro explainer does
to make a found clip say exactly what its sentence says.

    ralenti     : speed ramp — normal, then half speed over the strong moment
                  (frames interpolated, not repeated), then normal again
    zoom        : a slow push-in on a target (the feet, the wheel) found on
                  the clip — a wide shot becomes a close one
    arret       : freeze frame on the strong moment with a small push-in; an
                  arrow/circle of the same plan stays on the frozen picture
    transition  : the next part of the story starts with a whip zoom and a
                  whoosh

A clip shorter than its sentence is slowed down as a whole (never below half
speed) instead of ending on a frozen last frame.

Everything shares one time map per segment (`pieces`): render cuts the
clip with it, the arrows and the crash sound are placed with it.
"""

import base64
import os
from typing import Dict, List, Optional, Tuple

SLOW = 0.5            # ramp speed: interpolated frames stay clean up to 2x
SLOW_SRC = 0.9        # seconds of clip slowed (-> 1.8 s on screen)
PRE = 0.35            # the ramp starts this long before the strong moment
FREEZE = 0.8          # seconds a frozen frame stays
MIN_SPEED = 0.5       # a short clip is never slowed more than this
ZOOM = 1.35           # push-in on a target
ZOOM_MAX_UPSCALE = 1.7  # beyond this the source pixels show
TRANSITION = 0.2      # the whip zoom
MAX = {"ralenti": 2, "zoom": 3, "arret": 1, "transition": 3}
KEYS = ("ralenti", "zoom", "arret", "transition")


def clean(e) -> Optional[Dict]:
    """{"ralenti": bool, "zoom": "target" | None, "arret": bool, "transition": bool} or None when nothing."""
    if not isinstance(e, dict):
        return None
    zoom = " ".join(str(e.get("zoom") or "").split())[:120] or None
    if zoom and zoom.lower() in ("null", "none", "false", "non", "aucun"):
        zoom = None
    out = {"ralenti": bool(e.get("ralenti")), "zoom": zoom, "arret": bool(e.get("arret")),
           "transition": bool(e.get("transition"))}
    return out if any(out.values()) else None


def cap(fx: List[Optional[Dict]]) -> List[Optional[Dict]]:
    """Never more of each than MAX: a pro edit keeps them for the strong moments."""
    seen = {k: 0 for k in KEYS}
    out = []
    for k, e in enumerate(fx):
        e = dict(e) if e else None
        if e:
            for key in KEYS:
                if e.get(key):
                    if seen[key] >= MAX[key] or (key == "transition" and k == 0):   # the first plan has nothing before it
                        e[key] = None if key == "zoom" else False
                    else:
                        seen[key] += 1
        out.append(clean(e))
    return out


# ------------------------------------------------------------------ time map

def extra(fx: Optional[Dict]) -> float:
    """Seconds of screen the effects add over the clip's own length."""
    fx = fx or {}
    return (SLOW_SRC * (1 / SLOW - 1) if fx.get("ralenti") else 0.0) + (FREEZE if fx.get("arret") else 0.0)


def pieces(c: Dict, s: Dict) -> List[Dict]:
    """The segment as played: [{"kind": "play", "a", "b", "speed", "o", "len"} | {"kind": "hold", "t", "o", "len"}],
    clip times a/b/t, output times o (from the segment start), covering exactly s["dur"]."""
    fx = s.get("fx") or {}
    ws, D, end = s["ws"], s["dur"], c["end"]
    base = float(fx.get("vitesse") or 1.0)
    imp = min(max(c.get("impact", ws), ws), end)
    if fx.get("ralenti") and base >= 0.99:
        a = max(ws, imp - PRE)
        b = min(end, a + SLOW_SRC)
        spans = [(ws, a, 1.0), (a, b, SLOW), (b, end, 1.0)]
    else:
        spans = [(ws, end, base)]
    freeze = imp if fx.get("arret") else None
    steps = []
    for a, b, sp in spans:
        if freeze is not None and a <= freeze < b:
            steps += [("play", a, freeze, sp), ("hold", freeze, FREEZE, 0), ("play", freeze, b, sp)]
            freeze = None
        else:
            steps.append(("play", a, b, sp))
    if freeze is not None:                      # the moment is at the very end of what is shown
        steps.append(("hold", freeze, FREEZE, 0))
    out, o = [], 0.0
    for kind, a, b, sp in steps:
        if o >= D - 1e-3:
            break
        if kind == "play":
            if b - a < 1e-3:
                continue
            L = (b - a) / sp
            if o + L > D:
                b, L = a + (D - o) * sp, D - o
            out.append({"kind": "play", "a": a, "b": b, "speed": sp, "o": o, "len": L})
        else:
            L = min(b, D - o)
            out.append({"kind": "hold", "t": a, "o": o, "len": L})
        o += L
    if o < D - 0.02:                            # the clip ran out: its last picture stays
        last = out[-1]["b"] if out and out[-1]["kind"] == "play" else (out[-1]["t"] if out else ws)
        out.append({"kind": "hold", "t": max(ws, last - 0.04), "o": o, "len": D - o, "pad": True})
    return out


def out_at(pcs: List[Dict], t: float) -> float:
    """Clip time -> seconds from the segment start (the first time it shows)."""
    for p in pcs:
        if p["kind"] == "play" and p["a"] - 1e-6 <= t <= p["b"] + 1e-6:
            return p["o"] + (t - p["a"]) / p["speed"]
        if p["kind"] == "hold" and abs(t - p["t"]) < 1e-6:
            return p["o"]
    plays = [p for p in pcs if p["kind"] == "play"]
    if plays and t < plays[0]["a"]:
        return 0.0
    return pcs[-1]["o"] + pcs[-1]["len"] if pcs else 0.0


def src_at(pcs: List[Dict], o: float) -> float:
    """Seconds from the segment start -> the clip time on screen."""
    for p in pcs:
        if p["o"] - 1e-6 <= o < p["o"] + p["len"]:
            return p["t"] if p["kind"] == "hold" else p["a"] + (o - p["o"]) * p["speed"]
    p = pcs[-1]
    return p["t"] if p["kind"] == "hold" else p["b"]


def hold_at(pcs: List[Dict]) -> Optional[Tuple[float, float]]:
    """(start, length) of the freeze frame chosen by the AI, from the segment start."""
    for p in pcs:
        if p["kind"] == "hold" and not p.get("pad"):
            return p["o"], p["len"]
    return None


def fit(c: Dict, s: Dict, fx: Optional[Dict]) -> Dict:
    """The effects as played for this segment: a clip too short for its
    sentence gets a uniform slow-down (then no ramp)."""
    fx = dict(fx or {})
    avail = c["end"] - s["ws"]
    hold = FREEZE if fx.get("arret") else 0.0
    need = s["dur"] - hold - (SLOW_SRC * (1 / SLOW - 1) if fx.get("ralenti") else 0.0)
    if avail < need - 0.05 and avail > 0.1:
        fx["vitesse"] = round(max(MIN_SPEED, avail / max(s["dur"] - hold, 0.1)), 3)
        if fx["vitesse"] < 0.99:
            fx["ralenti"] = False
    return fx


# ------------------------------------------------------------------ zoom target

def zoom_of(c: Dict, box: Optional[List[int]]) -> Optional[Dict]:
    """A push-in toward a box_2d (0-1000 on the clean clip): its centre and a
    strength the source resolution can bear."""
    if not box:
        return None
    y0, x0, y1, x1 = (v / 1000 for v in box)
    from adaptation import render as R
    aspect = c["w"] / c["h"]
    cover_h = max(R.BOX_H, R.BOX_W / aspect) * 1.02
    upscale = cover_h / c["h"]                      # already > 1 for a small source
    z = max(1.12, min(ZOOM, ZOOM_MAX_UPSCALE / max(upscale, 1e-6)))
    if (y1 - y0) > 0.75:                            # the target fills the picture already
        z = min(z, 1.12)
    return {"cx": round((x0 + x1) / 2, 3), "cy": round((y0 + y1) / 2, 3), "z": round(z, 3)}


# ------------------------------------------------------------------ the AI's choice

DECIDE_PROMPT = """Tu fais le montage d'un YouTube Short explicatif. Voici {n} images, une par plan (le moment fort de
chaque clip), dans l'ordre. Plans (numero : phrase dite / ce que montre le clip / duree du clip / choc entendu) :
{plans}

Choisis les effets de montage, PEU mais aux bons endroits (un montage pro n'en met pas partout) :
- "ralenti": true -> un mouvement rapide qu'on veut voir (saut, atterrissage, choc, chute, roue sur l'obstacle) ;
  2 plans au plus.
- "zoom": "la cible" -> le sujet de la phrase est petit ou loin dans l'image (ex. "les pieds de l'homme",
  "la roue avant de la voiture blanche") : on s'en rapproche ; decris la cible pour qu'on la retrouve ;
  null si le sujet remplit deja l'image. 3 plans au plus. Jamais sur un plan qui a deja une fleche ou un cercle.
- "arret": true -> arret sur image sur LE detail a comprendre (souvent le plan qui a une fleche/un cercle) ;
  1 plan au plus.
- "transition": true -> ce plan commence une NOUVELLE partie de l'histoire (apres l'accroche, la reponse, la
  chute) ; 3 plans au plus, jamais le plan 1.
JSON uniquement : {{"plans": [{{"plan": numero, "ralenti": false, "zoom": null, "arret": false, "transition": false}}]}}"""


def decide(passages: List[Dict], clips: Dict[str, Dict], work_dir: str, gemini=None) -> Optional[List[Optional[Dict]]]:
    """One effects dict (or None) per passage, chosen looking at the real
    clips; None when Gemini can't answer (the video is then edited plainly)."""
    from adaptation import sources
    os.makedirs(work_dir, exist_ok=True)
    stills, idx = [], []
    for k, x in enumerate(passages):
        c = clips.get(x.get("clip"))
        if not c:
            continue
        out = os.path.join(work_dir, f"fx_{k}.jpg")
        try:
            sources.clip_still(c, out)
        except Exception:
            continue
        if os.path.exists(out):
            stills.append(out)
            idx.append(k)
    if not stills:
        return None
    def line(n, k):
        x, c = passages[k], clips[passages[k]["clip"]]
        ann = x.get("annotation")
        return (f"{n}. « {x.get('texte', '')} » / {c.get('desc') or 'clip'} / {c['end'] - c['start']:.1f} s / "
                f"{'choc' if c.get('shock') else 'calme'}" + (f" / {ann['type']} sur {ann['cible']}" if ann else ""))
    listing = "\n".join(line(n, k) for n, k in enumerate(idx, 1))
    parts = [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(open(p, "rb").read()).decode()}}
             for p in stills]
    try:
        r = (gemini or sources._gemini())._generate_content(
            parts + [{"text": DECIDE_PROMPT.format(n=len(stills), plans=listing)}],
            max_tokens=3000, timeout=120, temperature=0.2)
    except Exception:
        return None
    items = r.get("plans") if isinstance(r, dict) else None
    if not isinstance(items, list):
        return None
    out: List[Optional[Dict]] = [None] * len(passages)
    for e in items:
        try:
            n = int(e.get("plan")) - 1
        except (TypeError, ValueError, AttributeError):
            continue
        if 0 <= n < len(idx):
            fx = clean(e)
            if fx and fx.get("zoom") and passages[idx[n]].get("annotation"):
                fx["zoom"] = None                  # the arrow is placed on the unzoomed picture
            out[idx[n]] = clean(fx)
    return cap(out)


# ------------------------------------------------------------------ zoom when the subject is small

SMALL = 0.25          # the subject takes less than this share of the picture box: zoomed in on

SUBJECT_PROMPT = """Voici {n} images, une par plan d'un YouTube Short (le moment fort de chaque clip), dans l'ordre.
La phrase dite sur chaque plan :
{plans}
Dans CHAQUE image, trouve le SUJET de sa phrase : la personne ou l'objet dont elle parle, ou qui fait l'action
(pour "atterrir jambes tendues" : les jambes de la personne qui atterrit).
JSON uniquement : {{"plans": [{{"plan": numero, "sujet": "description courte pour le retrouver (couleur, position)",
"box_2d": [ymin, xmin, ymax, xmax] ou null s'il n'est pas visible}}]}}
Coordonnees entre 0 et 1000 sur l'image entiere."""


def on_screen(c: Dict, box: List[int]) -> float:
    """The share of the picture box a box_2d (0-1000 on the clean clip) takes
    once framed as render.clip_chain frames it (filled, or on its blurred copy)."""
    import math
    from adaptation import render as R
    y0, x0, y1, x1 = (v / 1000 for v in box)
    aspect, box_aspect = c["w"] / c["h"], R.BOX_W / R.BOX_H
    if abs(math.log(aspect / box_aspect)) < 0.25:                # fills the box
        pw, ph = max(R.BOX_W, R.BOX_H * aspect) * 1.08, max(R.BOX_H, R.BOX_W / aspect) * 1.08
    elif aspect > box_aspect:                                   # wide, on its blurred copy
        pw, ph = R.BOX_W * 1.04, R.BOX_W / aspect * 1.04
    else:                                                       # tall
        pw, ph = R.BOX_H * aspect * 1.04, R.BOX_H * 1.04
    return max((y1 - y0) * ph / R.BOX_H, (x1 - x0) * pw / R.BOX_W)


def auto_zoom(passages: List[Dict], clips: Dict[str, Dict], fx: List[Optional[Dict]], work_dir: str,
              gemini=None) -> List[Optional[Dict]]:
    """Measured, not guessed: the subject of each sentence is found on its clip
    and, when it takes less than a quarter of the picture, the plan gets a zoom
    on it (measured on a parkour Short: a man landing stiff-legged in a wide
    classroom shot, small, left unzoomed by the AI's eye). Never on a plan
    with an arrow or a zoom already; the smallest subjects first, within MAX."""
    from adaptation import sources
    fx = list(fx) + [None] * (len(passages) - len(fx))
    os.makedirs(work_dir, exist_ok=True)
    idx, stills = [], []
    for k, x in enumerate(passages):
        c = clips.get(x.get("clip"))
        if not c or (fx[k] or {}).get("zoom") or (x.get("annotation") or {}).get("cible"):
            continue
        out = os.path.join(work_dir, f"subject_{k}.jpg")
        try:
            sources.clip_still(c, out)
        except Exception:
            continue
        if os.path.exists(out):
            idx.append(k)
            stills.append(out)
    if not stills:
        return fx
    listing = "\n".join(f"{n}. « {passages[k].get('texte', '')} »" for n, k in enumerate(idx, 1))
    parts = [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(open(p, "rb").read()).decode()}}
             for p in stills]
    try:
        r = (gemini or sources._gemini())._generate_content(
            parts + [{"text": SUBJECT_PROMPT.format(n=len(stills), plans=listing)}],
            max_tokens=4000, timeout=120, temperature=0.1)
    except Exception:
        return fx
    small = []
    for e in (r.get("plans") if isinstance(r, dict) else None) or []:
        try:
            n = int(e.get("plan")) - 1
        except (TypeError, ValueError, AttributeError):
            continue
        b = e.get("box_2d", next((v for key, v in e.items() if str(key).startswith("box")), None))
        sujet = " ".join(str(e.get("sujet") or "").split())[:120]
        if not (0 <= n < len(idx) and sujet and isinstance(b, list) and len(b) == 4 and b[2] > b[0] and b[3] > b[1]):
            continue
        k = idx[n]
        share = on_screen(clips[passages[k]["clip"]], [int(v) for v in b])
        if share < SMALL:
            small.append((share, k, sujet))
    room = MAX["zoom"] - sum(1 for e in fx if e and e.get("zoom"))
    for share, k, sujet in sorted(small)[:max(0, room)]:
        e = dict(fx[k] or {"ralenti": False, "arret": False, "transition": False})
        e["zoom"] = sujet
        fx[k] = clean(e)
    return fx
