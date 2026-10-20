"""
Arrows and circles on the action (phase 2) — what the tram Short did: a
yellow arrow on the car just before the crash. The eye knows where to look,
and the viewer waits for what comes.

For a passage that asks for one ({"type": "fleche" | "cercle", "cible": "the
black car"}):
  - when: from about 1.1 s before the clip's strong moment up to it (or a
    1.2 s window in the middle when the moment is not on screen)
  - where: Gemini finds the target on 4 cleaned stills of that window
    (box_2d), a smooth path is drawn between them — the car moves, the
    camera too
  - the boxes are moved into the composed frame (crop, cover or blurred
    contain, the same maths as render.clip_chain)
  - drawn frame by frame as transparent PNGs the size of the picture box:
    a "pop" in (scale with a small overshoot), a thick outline and a soft
    shadow so it reads on any image, a short fade out; render overlays
    them on the picture box, under the banner and the captions.
"""

import base64
import math
import os
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter

from adaptation import render as R

KINDS = ("fleche", "cercle")
YELLOW, RED, INK = (255, 212, 0, 255), (255, 59, 48, 255), (0, 0, 0, 255)
SHOW = 1.1                 # seconds on screen before the strong moment
POP = 0.22                 # the pop-in
FADE = 0.12

LOCATE_PROMPT = """Voici {n} images successives d'une meme video (quelques dixiemes de seconde d'ecart).
Dans CHAQUE image, trouve : {cible}.
JSON uniquement : {{"images": [{{"box_2d": [ymin, xmin, ymax, xmax]}} ou {{"box_2d": null}} si elle n'est pas visible]}}
Coordonnees entre 0 et 1000 sur l'image entiere, dans l'ordre des images."""


class AnnotateError(RuntimeError):
    pass


def window(seg: Dict, clip: Dict) -> Tuple[float, float]:
    """Source times [a, b] where the annotation shows: up to the strong
    moment when it is on screen, else a window in the middle of the shot."""
    ws, dur = seg["ws"], seg["dur"]
    shown_end = min(ws + dur, clip["end"])
    b = clip.get("impact", ws)
    if ws + 0.5 <= b <= shown_end:
        return max(ws + 0.1, b - SHOW), b
    a = ws + min(0.4, dur * 0.2)
    return a, min(shown_end - 0.2, a + 1.2)


def after_last_cut(clip: Dict, a: float, b: float) -> float:
    """A shot change inside [a, b] would make the arrow jump to another
    subject (measured on a clip cutting from one horse to another): the
    annotation then starts after the last cut. Returns the new start."""
    from adaptation import sources
    try:
        import numpy as np
        f = sources._gray_frames(clip["src"], 16, 16, 25.0, clip.get("crop"), ss=a, t=b - a)
        if len(f) < 4:
            return a
        d = np.abs(np.diff(f, axis=0)).mean((1, 2))
        med = np.median(d) + 1e-6
        cuts = [i + 1 for i in range(len(d)) if d[i] > max(4 * med, 12) and sources.is_cut(f, i + 1)]
    except Exception:
        return a
    return a + cuts[-1] / 25.0 + 0.04 if cuts else a


def to_box(clip: Dict, x: float, y: float) -> Tuple[float, float]:
    """A point of the cleaned clip picture (0-1 on each side) -> pixels in the
    picture box, as clip_chain places it (zoom pulse and shake left out)."""
    aspect, box_aspect = clip["w"] / clip["h"], R.BOX_W / R.BOX_H
    if abs(math.log(aspect / box_aspect)) < 0.25:              # cover, centred on the subject (render.framing)
        cw = R._even(max(R.BOX_W, R.BOX_H * aspect) * 1.08)
        ch = cw / aspect
        fx, fy = R.framing(clip)
        ox = min(max(fx * cw - R.BOX_W / 2, 0), cw - R.BOX_W)
        oy = min(max(fy * ch - R.BOX_H / 2, 0), ch - R.BOX_H)
        return x * cw - ox, y * ch - oy
    if aspect > box_aspect:                                    # wide, on its blurred copy
        fw, fh = R.BOX_W, R._even(R.BOX_W / aspect)
    else:
        fw, fh = R._even(R.BOX_H * aspect), R.BOX_H
    sw, sh = R._even(fw * 1.04), R._even(fw * 1.04) / aspect
    return (R.BOX_W - fw) / 2 + x * sw - (sw - fw) / 2, (R.BOX_H - fh) / 2 + y * sh - (sh - fh) / 2


def locate(stills: List[str], cible: str, gemini=None) -> List[Optional[List[int]]]:
    """The target's box_2d (0-1000) on each still, None where not seen."""
    from adaptation.sources import _gemini
    parts = [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(open(p, "rb").read()).decode()}}
             for p in stills]
    r = (gemini or _gemini())._generate_content(parts + [{"text": LOCATE_PROMPT.format(n=len(stills), cible=cible)}],
                                                max_tokens=2000, timeout=90, temperature=0.1)
    items = r if isinstance(r, list) else (r.get("images") if isinstance(r, dict) else None)
    if not isinstance(items, list):
        raise AnnotateError(f"Cible introuvable : {str(r)[:160]}")
    out = []
    for k in range(len(stills)):
        it = items[k] if k < len(items) and isinstance(items[k], dict) else {}
        b = it.get("box_2d", next((v for key, v in it.items() if key.startswith("box")), None))   # once spelt "box_2"
        ok = isinstance(b, list) and len(b) == 4 and b[2] > b[0] and b[3] > b[1]
        out.append([int(v) for v in b] if ok else None)
    return out


def track(clip: Dict, boxes: List[Optional[List[int]]], times: List[float]) -> List[Dict]:
    """[{t, cx, cy, rx, ry}] in picture-box pixels, missing samples filled
    from their neighbours; [] when the target was never seen."""
    pts = []
    for t, b in zip(times, boxes):
        if not b:
            continue
        y0, x0, y1, x1 = (v / 1000 for v in b)
        (ax, ay), (bx, by) = to_box(clip, x0, y0), to_box(clip, x1, y1)
        pts.append({"t": t, "cx": (ax + bx) / 2, "cy": (ay + by) / 2, "rx": abs(bx - ax) / 2, "ry": abs(by - ay) / 2})
    return pts


def at(path: List[Dict], t: float) -> Dict:
    """Smooth position at time t between the samples (eased, held at the ends)."""
    if t <= path[0]["t"]:
        return path[0]
    for p, q in zip(path, path[1:]):
        if p["t"] <= t <= q["t"]:
            f = (t - p["t"]) / max(q["t"] - p["t"], 1e-6)
            f = f * f * (3 - 2 * f)
            return {k: p[k] + (q[k] - p[k]) * f for k in ("cx", "cy", "rx", "ry")} | {"t": t}
    return path[-1]


def _pop(t: float, length: float) -> Tuple[float, float]:
    """(scale, opacity) at t seconds into an annotation lasting `length`."""
    if t < POP:
        f = t / POP
        s = 1 + 2.2 * (f - 1) ** 3 + 1.2 * (f - 1) ** 2          # ease-out-back: 0 -> ~1.1 -> 1
        scale = max(0.05, s)
    else:
        scale = 1.0
    alpha = 1.0 if t < length - FADE else max(0.0, (length - t) / FADE)
    return scale, alpha


def _arrow_side(p: Dict) -> Tuple[float, float]:
    """A direction for the arrow to come FROM: the diagonal with the most room,
    preferring from above (the banner is above the box, the captions below)."""
    best, room = (-1.0, -1.0), -1.0
    for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        rx = p["cx"] if dx < 0 else R.BOX_W - p["cx"]
        ry = p["cy"] if dy < 0 else R.BOX_H - p["cy"]
        r = min(rx, ry) + (40 if dy < 0 else 0)
        if r > room:
            best, room = (dx / math.sqrt(2), dy / math.sqrt(2)), r
    return best


def _draw_arrow(d: ImageDraw.ImageDraw, tip: Tuple[float, float], frm: Tuple[float, float], scale: float):
    length, width, head = 230 * scale, 30 * scale, 78 * scale
    ux, uy = -frm[0], -frm[1]                                  # unit vector, tail -> tip
    tx, ty = tip
    bx, by = tx - ux * head, ty - uy * head                    # base of the head
    sx, sy = tx - ux * length, ty - uy * length                # tail
    nx, ny = -uy, ux
    shaft = [(sx + nx * width / 2, sy + ny * width / 2), (bx + nx * width / 2, by + ny * width / 2),
             (bx + nx * head * 0.62, by + ny * head * 0.62), (tx, ty),
             (bx - nx * head * 0.62, by - ny * head * 0.62), (bx - nx * width / 2, by - ny * width / 2),
             (sx - nx * width / 2, sy - ny * width / 2)]
    d.polygon(shaft, fill=YELLOW, outline=INK, width=max(2, int(7 * scale)))


def _draw_circle(d: ImageDraw.ImageDraw, p: Dict, scale: float):
    rx, ry = max(p["rx"] * 1.25, 48) * scale, max(p["ry"] * 1.25, 48) * scale
    box = (p["cx"] - rx, p["cy"] - ry, p["cx"] + rx, p["cy"] + ry)
    d.ellipse(box, outline=INK, width=max(3, int(22 * scale)))
    d.ellipse(box, outline=RED, width=max(2, int(13 * scale)))


def frames(path: List[Dict], kind: str, a: float, b: float, out_dir: str, fps: int = R.FPS) -> int:
    """Draws the annotation from source time a to b; returns the frame count.
    Frames are BOX_W x BOX_H RGBA, named f_000.png…"""
    os.makedirs(out_dir, exist_ok=True)
    n = max(1, int(round((b - a) * fps)))
    length = n / fps
    frm = _arrow_side(path[0])
    for i in range(n):
        t = i / fps
        p = at(path, a + t)
        scale, alpha = _pop(t, length)
        layer = Image.new("RGBA", (R.BOX_W, R.BOX_H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        if kind == "cercle":
            _draw_circle(d, p, scale)
        else:
            reach = max(p["rx"], p["ry"]) * 0.55 + 12              # the tip stops at the target's edge
            tip = (p["cx"] + frm[0] * reach, p["cy"] + frm[1] * reach)
            _draw_arrow(d, tip, frm, scale)
        shadow = layer.split()[3].filter(ImageFilter.GaussianBlur(9)).point(lambda v: int(v * 0.55))
        out = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        out.paste((0, 0, 0, 255), (6, 8), shadow)                  # soft drop shadow, slightly below-right
        out.alpha_composite(layer)
        if alpha < 1:
            out.putalpha(out.split()[3].point(lambda v: int(v * alpha)))
        out.save(os.path.join(out_dir, f"f_{i:03d}.png"))
    return n


def prepare(seg: Dict, clip: Dict, ann: Dict, work_dir: str, k: int, gemini=None,
            cached: Optional[Dict] = None) -> Optional[Dict]:
    """Everything render needs for one passage's annotation, or None when the
    target can't be found. `cached`: a track from an earlier render of the
    same clip window (the final render reuses the preview's, no new call)."""
    kind = ann.get("type") if ann.get("type") in KINDS else "fleche"
    a, b = window(seg, clip)
    a = after_last_cut(clip, a, b)
    if b - a < 0.4:
        return None
    if cached and cached.get("window") == [round(a, 2), round(b, 2)] and cached.get("cible") == ann.get("cible"):
        path = cached["path"]
    else:
        from adaptation import sources
        times = [a + (b - a) * f for f in (0.0, 0.33, 0.66, 1.0)]
        size = (clip["w"], clip["h"])
        stills = [sources.still(clip["src"], t, clip.get("crop"), os.path.join(work_dir, f"ann{k}_{j}.jpg"),
                                clip.get("delogo"), size) for j, t in enumerate(times)]
        path = track(clip, locate(stills, ann.get("cible") or "le sujet principal", gemini), times)
    if not path:
        return None
    d = os.path.join(work_dir, f"ann{k}")
    for f in os.listdir(d) if os.path.isdir(d) else []:
        os.remove(os.path.join(d, f))
    from adaptation import effects as E
    pcs = seg.get("pieces") or E.pieces(clip, seg)     # ramps and freezes: the arrow follows the time map
    oa, ob = E.out_at(pcs, a), E.out_at(pcs, b)
    for x in pcs:                                      # a freeze on the moment keeps the arrow on the frozen picture
        if x["kind"] == "hold" and not x.get("pad") and a - 0.01 <= x["t"] <= b + 0.01:
            ob = max(ob, x["o"] + x["len"])
    n = frames([{**q, "t": E.out_at(pcs, q["t"])} for q in path], kind, oa, ob, d)
    return {"k": k, "dir": d, "frames": n, "start": seg["out"] + oa,
            "cache": {"window": [round(a, 2), round(b, 2)], "cible": ann.get("cible"), "path": path}}


REVIEW_PROMPT = """Voici {n} images, une par plan d'un YouTube Short (le moment fort de chaque clip), dans l'ordre.
Plans (numero : phrase dite / fleche ou cercle prevu) :
{plans}

Revois les fleches et cercles AVEC CES VRAIES IMAGES :
- 2 ou 3 plans au plus, la ou le spectateur doit ANTICIPER une action (fleche) ou VOIR un detail (cercle) ;
- la cible DOIT etre clairement visible dans l'image du plan ; decris-la pour qu'on la retrouve
  (couleur, position : ex. "le pneu arriere gauche", "la voiture rouge a droite") ;
- garde une annotation prevue si sa cible est bien visible (en precisant la description si besoin),
  retire-la sinon, et ajoute-en une la ou elle aide vraiment.
JSON uniquement : {{"plans": [{{"plan": numero, "annotation": null ou {{"type": "fleche | cercle", "cible": "..."}}}}]}}"""


def review(passages: List[Dict], clips: Dict[str, Dict], work_dir: str, gemini=None) -> Optional[List[Optional[Dict]]]:
    """The arrows and circles decided again by Gemini looking at the real
    clips (the storyboard chose them before any footage existed). One
    annotation (or None) per passage, or None when Gemini can't answer."""
    from adaptation import sources
    from adaptation.storyboard import clean_annotation
    os.makedirs(work_dir, exist_ok=True)
    stills, idx = [], []
    for k, x in enumerate(passages):
        c = clips.get(x.get("clip"))
        if not c:
            continue
        out = os.path.join(work_dir, f"review_{k}.jpg")
        try:
            sources.clip_still(c, out)
        except Exception:
            continue
        if os.path.exists(out):
            stills.append(out)
            idx.append(k)
    if not stills:
        return None
    listing = "\n".join(
        f"{n}. {passages[k].get('texte', '')} / " + (f"{a['type']} sur « {a['cible']} »" if (a := passages[k].get("annotation")) else "rien")
        for n, k in enumerate(idx, 1))
    parts = [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(open(p, "rb").read()).decode()}}
             for p in stills]
    try:
        from adaptation.sources import _gemini
        r = (gemini or _gemini())._generate_content(parts + [{"text": REVIEW_PROMPT.format(n=len(stills), plans=listing)}],
                                                    max_tokens=3000, timeout=120, temperature=0.2)
    except Exception:
        return None
    items = (r.get("plans") if isinstance(r, dict) else None)
    if not isinstance(items, list):
        return None
    out = [None] * len(passages)
    for e in items:
        try:
            n = int(e.get("plan")) - 1
        except (TypeError, ValueError, AttributeError):
            continue
        if 0 <= n < len(idx):
            out[idx[n]] = clean_annotation(e.get("annotation"))
    kept = [k for k, a in enumerate(out) if a]
    for k in kept[3:]:                  # never more than three
        out[k] = None
    return out
