"""
« Reprise » (4th Adaptation mode, lab etude_reprise/, 2026-10-30/31): a friend's vertical Short taken again — its
IMAGES kept, everything its creator added on top erased, then our text, voice and captions (reprise_montage.py).

The cleaning, tested on 7 Shorts (captions in any colour, numbers, stickers, follow buttons, watermarks):

    elements     Gemini lists what the creator added (one element per caption sentence, not per word: a 160 s Short
                 cut the answer), its stickers placed again on a still image (precise there), and for each drawing
                 « garder » or « cacher » with its reason (a red X saying "don't", an arrow, a circle: kept; a like /
                 follow sticker, a logo: hidden). Texts, names, buttons are always hidden. The person may change it.
    every image  EasyOCR in his text's places only (half size, the image before OR'd in), his text colours (learned from what the OCR reads:
                 coloured letters in a black or white outline, white letters in black; only thin strokes in his
                 captions' places — not a strawberry), the exact shape of each drawing / logo to hide followed by
                 SAM 2 (roblox/nettoyage.shapes: no rectangle), names / numbers: their box; inpainted (TELEA), a big
                 hole softly blurred
    re-read      the clean video read again at full size in his captions' places: a word left is erased there and
                 on the 2 images around it (an "IT" growing in was missed on 3 images)

On the graphics card (EasyOCR, SAM 2); 3 to 45 min a Short (its length and size). Nothing is reused from a file
half written (it is written aside, then renamed).
"""

import base64
import json
import os
import re
import subprocess
from typing import Callable, Dict, List, Optional

import numpy as np

WHITE = -1                       # "his text is white", among the learned hues
HOLD = 2                         # images before / after a word left (re-read) also erased
EVERY = 3                        # his text read, his stickers looked for, one image in EVERY (kept in between): the
                                 # cleaning 3.5 times faster, as clean (labo 2026-11-06: esturgeon 52 -> 14 min, 0 word left)
TEXT = ("sous_titres", "numero", "pseudo")
DRAWN = ("autocollant", "logo")


class RepriseError(RuntimeError):
    pass


def _cv2():
    import cv2
    return cv2


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode:
        raise RepriseError(r.stderr.decode(errors="replace")[-800:])
    return r


def probe(src: str) -> Dict:
    """{"w", "h", "rate" ("30/1"), "fps", "duree"} of a video."""
    out = json.loads(_run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                           "stream=width,height,r_frame_rate:format=duration", "-of", "json", src]).stdout)
    st = out["streams"][0]
    rate = st.get("r_frame_rate") or "30/1"
    a, _, b = rate.partition("/")
    fps = float(a) / float(b or 1) if a.replace(".", "").isdigit() and (b or "1").isdigit() and float(b or 1) else 30.0
    return {"w": int(st["width"]), "h": int(st["height"]), "rate": rate, "fps": fps or 30.0,
            "duree": float(out["format"]["duration"])}


def _still(src: str, t: float, vf: str, fmt: List[str]) -> bytes:
    return _run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{t:.2f}", "-i", src, "-frames:v", "1", "-vf", vf, *fmt,
                 "-"]).stdout


def _jpg(src: str, t: float) -> str:
    return base64.b64encode(_still(src, t, "scale=540:-2", ["-f", "image2", "-c:v", "mjpeg"])).decode()


# ---------------------------------------------------------------- what the creator added

CREATOR = """Ce Short vertical est d'un autre createur. On va reprendre ses IMAGES et refaire nos propres textes. Liste
CHAQUE element ajoute par-dessus les images au montage (pas ce qui est filme) : sous-titres, numeros, titres, emojis,
autocollants, bouton abonne-toi, logo, filigrane, pseudo. Pour chacun : "type" (sous_titres | numero | autocollant |
logo | pseudo), "description", "debut" et "fin" en secondes, "cadre" = {"gauche","haut","droite","bas"} en FRACTIONS
de l'image entre 0 et 1 (0.5 = le milieu ; pas des pixels, pas des milliemes) englobant tout l'element.
Des sous-titres mot a mot au meme endroit : UN element par phrase (pas un par mot), son cadre englobant tous ses mots.
JSON uniquement : {"elements": [...]}"""

RELOCATE = """Sur cette image d'un Short, ou est exactement cet element ajoute au montage : {desc} ?
Donne son cadre en FRACTIONS de l'image entre 0 et 1 (0.5 = le milieu), un peu plus grand que l'element.
S'il n'est pas sur l'image, "absent": true. JSON uniquement : {{"absent": false, "cadre": {{"gauche": 0, "haut": 0, "droite": 0, "bas": 0}}}}"""

DECIDE = """Ce dessin a ete ajoute par-dessus les images d'un Short par son createur : {desc}.
On refait ce Short avec notre propre texte et notre voix, dans une autre langue, et sans rien qui montre son createur.
Le GARDER seulement si c'est un dessin ou un symbole sans texte ni marque qui aide a comprendre l'image (une croix sur
ce qu'il ne faut pas faire, une fleche ou un cercle qui montre un detail). Le CACHER si c'est du texte, un logo, un
pseudo, un bouton abonne-toi / follow / like, un emoji ou un decor qui n'explique rien.
JSON uniquement : {{"action": "garder" | "cacher", "raison": "..."}}"""


def as_seconds(times: List[float], length: float) -> Optional[List[float]]:
    """Gemini's times read back when it wrote the minutes and the seconds as one number, the seconds not always
    wrapped at 60 (1:00.7 -> 100.7, "1:62.2" -> 162.2, 2:40 -> 240): the 5th Short's plans ran to 162.2 s of a
    122.6 s video (every one then fell on a real cut, ±0.2 s), the 3rd's to 240 s of 160. The times as they are when
    they fit; None when they fit neither way (a time between 60 and 100 can't be written so)."""
    if not times or max(times) <= length * 1.02:
        return list(times)
    if any(60 <= t < 100 for t in times):
        return None
    fixed = [(t // 100) * 60 + t % 100 if t >= 100 else t for t in times]
    return [round(t, 2) for t in fixed] if max(fixed) <= length * 1.02 else None


def box_of(cadre, size) -> Optional[List[float]]:
    """Gemini's box as fractions [x0, y0, x1, y1], whatever it answered in (fractions, thousandths — the 2nd Short's
    boxes all came back [1, 1, 1, 1] read as fractions — or pixels); None when too small to be anything."""
    try:
        raw = [float(cadre[k]) for k in ("gauche", "haut", "droite", "bas")] if isinstance(cadre, dict) else \
            [float(v) for v in cadre]
    except (KeyError, TypeError, ValueError):
        return None
    if len(raw) != 4:
        return None
    if max(raw) > 1.0:
        raw = [v / 1000.0 for v in raw] if max(raw) <= 1000 else \
            [raw[0] / size[0], raw[1] / size[1], raw[2] / size[0], raw[3] / size[1]]
    box = [min(1.0, max(0.0, v)) for v in raw]
    return box if box[2] - box[0] >= 0.01 and box[3] - box[1] >= 0.01 else None


def read_elements(answer: Optional[Dict], size, length: float) -> Optional[List[Dict]]:
    """Gemini's list -> clean elements, its times as seconds (as_seconds); None when the answer can't be trusted."""
    got = (answer or {}).get("elements") or []
    try:
        flat = as_seconds([float(e[k]) for e in got for k in ("debut", "fin")], length) if got else None
    except (KeyError, TypeError, ValueError):
        return None
    if not flat:
        return None
    got = [{**e, "debut": flat[2 * i], "fin": flat[2 * i + 1]} for i, e in enumerate(got)]
    out = []
    for e in got:
        box = box_of(e.get("cadre"), size)
        try:
            if box:
                out.append({**e, "cadre": box, "debut": float(e["debut"]), "fin": float(e["fin"])})
        except (KeyError, TypeError, ValueError):
            continue
    return out


def placed(src: str, e: Dict, size, g, t: Optional[float] = None) -> Dict:
    """The element's box looked for again on a still image, where Gemini is precise (on the moving video it put a
    button too high, a watermark at 3 % of the height instead of 13 %, a title at 70 % instead of 60 % — and the
    OCR now erases only inside these boxes). A caption keeps both boxes joined: its words change over its span."""
    t = e["debut"] + (e["fin"] - e["debut"]) * 0.4 if t is None else t
    r = g._generate_content([{"inline_data": {"mime_type": "image/jpeg", "data": _jpg(src, t)}},
                             {"text": RELOCATE.format(desc=e.get("description") or e["type"])}],
                            max_tokens=800, timeout=60, temperature=0.0) or {}
    box = None if r.get("absent") else box_of(r.get("cadre"), size)
    if not box:
        return e
    if e.get("type") == "sous_titres":
        old = e["cadre"]
        box = [min(old[0], box[0]), min(old[1], box[1]), max(old[2], box[2]), max(old[3], box[3])]
    return {**e, "cadre": box}


def find_elements(src: str, gemini=None) -> List[Dict]:
    """What the creator added, its drawings placed again and each one's « garder » / « cacher » (see the header)."""
    from adaptation.sources import _gemini, gemini_file
    info = probe(src)
    size = (info["w"], info["h"])
    els = None
    for fps in (4, 2):
        with gemini_file(src) as (g, part):
            r = g._generate_content([{**part, "video_metadata": {"fps": fps}}, {"text": CREATOR}], max_tokens=16000,
                                    timeout=300, temperature=0.1)
        els = read_elements(r, size, info["duree"])
        if els is not None:
            break
    if els is None:
        raise RepriseError("Gemini n'a pas su lister ce que le créateur a ajouté sur la vidéo.")
    g = gemini or _gemini()
    out = []
    for e in els:
        t = e["debut"] + (e["fin"] - e["debut"]) * 0.4
        e = placed(src, e, size, g, t)
        if e.get("type") == "autocollant":
            r = g._generate_content([{"inline_data": {"mime_type": "image/jpeg", "data": _jpg(src, t)}},
                                     {"text": DECIDE.format(desc=e.get("description") or "un autocollant")}],
                                    max_tokens=500, timeout=60, temperature=0.0) or {}
            e = {**e, "action": "garder" if r.get("action") == "garder" else "cacher", "raison": r.get("raison", "")}
        else:
            e = {**e, "action": "cacher", "raison": "texte, marque ou bouton du créateur"}
        out.append(e)
    return out


# ---------------------------------------------------------------- his text colours

def learn_colours(src: str, reader, info: Dict) -> List[int]:
    """The creator's text colours, from 20 images: the hues of the strokes inside what the OCR reads that are not
    the scenery's around them (peanut butter taken for orange text), and WHITE when his sure words are white
    letters in black (not a keyboard's keys)."""
    cv2 = _cv2()
    w, h = info["w"], info["h"]
    hues, words, white = [], 0, 0
    for t in np.linspace(0.5, max(0.6, info["duree"] - 0.5), 20):
        raw = _still(src, t, "null", ["-f", "rawvideo", "-pix_fmt", "bgr24"])
        if len(raw) < w * h * 3:
            continue
        bgr = np.frombuffer(raw, np.uint8)[:w * h * 3].reshape(h, w, 3)
        img = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        for pts, text, conf in reader.readtext(bgr):
            if conf < 0.3:
                continue
            x0, y0 = np.maximum(np.min(pts, axis=0).astype(int), 0)
            x1, y1 = np.max(pts, axis=0).astype(int)
            bh = max(4, (y1 - y0) // 2)
            inner = img[y0:y1, x0:x1].reshape(-1, 3)
            ring = np.concatenate([img[max(0, y0 - bh):y0, x0:x1].reshape(-1, 3), img[y1:y1 + bh, x0:x1].reshape(-1, 3)])
            vivid = lambda a: a[(a[:, 1] > 130) & (a[:, 2] > 150)][:, 0].astype(int)   # noqa: E731
            hi, hr = np.bincount(vivid(inner), minlength=180), np.bincount(vivid(ring), minlength=180)
            excess = hi - hr * max(1.0, len(inner) / max(1, len(ring)))
            for c in np.nonzero(excess > 0.08 * max(1, len(inner)))[0]:
                hues += [int(c)] * int(excess[c])
            box = img[y0:y1, x0:x1]
            if conf >= 0.5 and len(text.strip()) >= 2 and box.size:
                words += 1
                white += ((box[..., 1] < 45) & (box[..., 2] > 215)).mean() > 0.15 and (box[..., 2] < 70).mean() > 0.15
    out = [WHITE] if white >= 3 and white >= 0.25 * words else []
    if not hues:
        return out
    hist = np.bincount(np.array(hues, int), minlength=180)
    for _ in range(3):                                   # up to 3 colours, each a peak of 5 % of the strokes at least
        c = int(np.argmax(hist))
        if hist[c] < 0.05 * len(hues):
            break
        out.append(c)
        hist[max(0, c - 8):c + 9] = 0
    return out


def _box(mask: np.ndarray, pad: int = 8):
    """(y0, y1, x0, x1) around what is set in mask, pad pixels more; None: nothing set."""
    ys, xs = np.nonzero(mask)
    if not len(ys):
        return None
    h, w = mask.shape
    return max(0, ys.min() - pad), min(h, ys.max() + pad + 1), max(0, xs.min() - pad), min(w, xs.max() + pad + 1)


def colour_mask(img: np.ndarray, hues: List[int], zones: np.ndarray) -> np.ndarray:
    """In the zones where he writes, his letters the OCR missed (a one-letter "A", a 2-letter "IT", an animated
    number): coloured strokes outlined in black (cyan) or in white (red "A", "THE"), white strokes almost all close
    to black; thin only (a letter, not a strawberry), grown to take the outline and the inside too. Looked for in
    the zones' rows only (the whole width kept: the « thin » test is the same)."""
    cv2 = _cv2()
    b = _box(zones, 40)                              # 40: room for the outlines and the growing
    if b is None:
        return np.zeros(zones.shape, np.uint8)
    if b[1] - b[0] < zones.shape[0]:
        out = np.zeros(zones.shape, np.uint8)
        out[b[0]:b[1]] = colour_mask(img[b[0]:b[1]], hues, zones[b[0]:b[1]])
        return out
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[..., 0].astype(int), hsv[..., 1], hsv[..., 2]
    stroke = np.zeros(sat.shape, bool)
    white = ((sat < 45) & (val > 215) & zones) if WHITE in hues else np.zeros(sat.shape, bool)
    for c in hues:
        if c == WHITE:
            continue
        d = np.minimum(np.abs(hue - c), 180 - np.abs(hue - c))
        stroke |= (d <= 7) & (sat > 150) & (val > 140)   # vivid only: a pale cyan blanket held "you" in place
    stroke &= zones
    if not stroke.any() and not white.any():
        return np.zeros(sat.shape, np.uint8)
    dark = val < 70
    keep = np.zeros(sat.shape, np.uint8)
    for strokes, edge, need in ((stroke, dark | ((sat < 45) & (val > 215)), 0.15), (white, dark, 0.6)):
        if not strokes.any():
            continue
        near_edge = cv2.dilate(edge.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))) > 0
        thin = cv2.distanceTransform(strokes.astype(np.uint8), cv2.DIST_L2, 3)
        n, lab, stats, _ = cv2.connectedComponentsWithStats(strokes.astype(np.uint8), connectivity=8)
        for i in range(1, n):
            comp = lab == i
            if stats[i, cv2.CC_STAT_AREA] < 25 or (comp & near_edge).sum() < need * comp.sum():
                continue
            if thin[comp].max() > 0.012 * sat.shape[1]:   # a letter's stroke is thin (the red "A": ~23 px of 1440)
                continue
            keep[comp] = 255
    keep = cv2.dilate(keep, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17)))
    return cv2.morphologyEx(keep, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)))


# ---------------------------------------------------------------- stickers

def grown(e: Dict, w: int, h: int, k: float = 0.35):
    x0, y0, x1, y1 = e["cadre"]
    dx, dy = (x1 - x0) * k, (y1 - y0) * k
    return int(max(0, x0 - dx) * w), int(max(0, y0 - dy) * h), int(min(1, x1 + dx) * w), int(min(1, y1 + dy) * h)


def zones_at(els: List[Dict], t: float, w: int, h: int) -> np.ndarray:
    """Where he writes text at t: his captions / numbers / names boxes, grown (not a sticker's: a big "X" box let
    the colour search into the peanut butter)."""
    z = np.zeros((h, w), bool)
    for e in els:
        if e.get("type") in TEXT and e["debut"] - 0.4 <= t <= e["fin"] + 0.4:
            x0, y0, x1, y1 = grown(e, w, h, 0.25)
            z[y0:y1, x0:x1] = True
    return z


def sticker_looks(src: str, els: List[Dict], w: int, h: int) -> List[np.ndarray]:
    """Each sticker / watermark to hide as a picture (half size), to find it again where Gemini's box was wrong or
    missing (a Chinese watermark the OCR can't read was seen by Gemini only at 35 s and 47 s, 5th Short: it is
    there all along); a sticker box with no vivid colour in it (over the scenery) gives none."""
    cv2 = _cv2()
    looks = []
    for e in els:
        if e.get("type") not in ("autocollant", "pseudo"):
            continue
        raw = _still(src, (e["debut"] + e["fin"]) / 2, f"scale={w // 2}:{h // 2}", ["-f", "rawvideo", "-pix_fmt", "bgr24"])
        if len(raw) < (w // 2) * (h // 2) * 3:
            continue
        img = np.frombuffer(raw, np.uint8)[:(w // 2) * (h // 2) * 3].reshape(h // 2, w // 2, 3)
        x0, y0, x1, y1 = [v // 2 for v in grown(e, w, h, 0.0)]
        crop = img[y0:y1, x0:x1]
        if not crop.size:
            continue
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        if e["type"] == "pseudo" and gray.std() > 12 or (cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)[..., 1] > 150).mean() > 0.04:
            looks.append(gray)
    return looks


def find_looks(small_gray: np.ndarray, looks: List[np.ndarray]):
    """Where any sticker picture is in this image (several sizes) -> [(x0, y0, x1, y1)] at half size."""
    cv2 = _cv2()
    out = []
    for look in looks:
        for scale in (0.7, 0.85, 1.0, 1.15, 1.3):
            lw, lh = int(look.shape[1] * scale), int(look.shape[0] * scale)
            if lw < 12 or lh < 8 or lw >= small_gray.shape[1] or lh >= small_gray.shape[0]:
                continue
            r = cv2.matchTemplate(small_gray, cv2.resize(look, (lw, lh)), cv2.TM_CCOEFF_NORMED)
            _, score, _, (x, y) = cv2.minMaxLoc(r)
            if score > 0.72:
                out.append((x, y, x + lw, y + lh))
    return out


def shapes(src: str, els: List[Dict], info: Dict, work: str) -> Dict[int, np.ndarray]:
    """The exact shape of each drawing / logo to hide, followed by SAM 2 -> {image: mask at half size}."""
    todo = [{**e, "type": "autocollant"} for e in els if e.get("type") in DRAWN]
    if not todo:
        return {}
    from roblox import nettoyage as N
    os.makedirs(work, exist_ok=True)
    return N.shapes(N.sam(), src, todo, work, size=(info["w"] // 2, info["h"] // 2), fps=int(round(info["fps"])))


# ---------------------------------------------------------------- the cleaning

def _frames(path: str, w: int, h: int):
    dec = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                           stdout=subprocess.PIPE)
    try:
        while True:
            raw = dec.stdout.read(w * h * 3)
            if len(raw) < w * h * 3:
                break
            yield np.frombuffer(raw, np.uint8).reshape(h, w, 3).copy()
    finally:
        dec.stdout.close()
        dec.wait()


def _writer(out: str, src: str, info: Dict):
    return subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s",
                             f"{info['w']}x{info['h']}", "-r", info["rate"], "-i", "-", "-i", src, "-map", "0:v",
                             "-map", "1:a?", "-c:v", "h264_nvenc", "-cq", "19", "-pix_fmt", "yuv420p", "-c:a", "copy", "-shortest",
                             out],                      # yuv420p: from bgr24 nvenc made a 4:4:4 RGB video, green in browsers
                            stdin=subprocess.PIPE)


def _inpaint(img: np.ndarray, mask: np.ndarray, kern) -> np.ndarray:
    """The holes filled from around them: in their box only (+ room for the blur), rebuilt at half size (4 times
    fewer pixels; the holes are soft anyway), laid back in the holes only, without a hard edge."""
    cv2 = _cv2()
    h, w = mask.shape
    y0, y1, x0, x1 = _box(mask, 48)
    sub = img[y0:y1, x0:x1].copy()
    m = cv2.dilate(mask[y0:y1, x0:x1], kern)
    sh, sw = m.shape
    half = cv2.inpaint(cv2.resize(sub, (max(1, sw // 2), max(1, sh // 2)), interpolation=cv2.INTER_AREA),
                       (cv2.resize(m, (max(1, sw // 2), max(1, sh // 2)), interpolation=cv2.INTER_NEAREST) > 0)
                       .astype(np.uint8) * 255, 3, cv2.INPAINT_TELEA)
    soft = cv2.GaussianBlur(m, (0, 0), 2).astype(np.float32)[..., None] / 255
    sub = (sub * (1 - soft) + cv2.resize(half, (sw, sh), interpolation=cv2.INTER_LINEAR) * soft).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    big = np.zeros(m.shape, np.uint8)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] > 0.01 * w * h:   # a big hole: blurred so the rebuilt blocks don't show
            big[lab == i] = 255
    if big.any():
        soft = cv2.GaussianBlur(cv2.dilate(big, kern), (0, 0), 12).astype(np.float32)[..., None] / 255
        sub = (sub * (1 - soft) + cv2.GaussianBlur(sub, (0, 0), 9) * soft).astype(np.uint8)
    out = img.copy()
    out[y0:y1, x0:x1] = sub
    return out


def read_in(reader, img: np.ndarray, zones: np.ndarray, scale: int, sure: float) -> np.ndarray:
    """What the OCR reads in his text's places only (at least half of a word inside them) -> a mask at full size.
    Not elsewhere: it read and erased what was FILMED — "KENYA" on the runners' shirts, their bibs, the race clock
    (the 8th Short) — which Gemini had rightly left out of its list."""
    cv2 = _cv2()
    out = np.zeros(zones.shape, np.uint8)
    b = _box(zones[::scale, ::scale])
    if b is None:
        return out
    y0, y1, x0, x1 = b                               # the OCR reads the zones' box only, not the whole image
    for pts, _, conf in reader.readtext(img[y0:y1, x0:x1]):
        if conf < sure:
            continue
        m = np.zeros(zones.shape, np.uint8)
        cv2.fillPoly(m, [((np.array(pts) + [x0, y0]) * scale).astype(np.int32)], 255)
        if (m.astype(bool) & zones).sum() > 0.5 * (m > 0).sum():
            out |= m
    return out


def clean(src: str, elements: List[Dict], out: str, work: str, reader=None,
          progress: Optional[Callable[[float], None]] = None) -> Dict:
    """src with what the creator added erased (the elements « cacher » only) -> out; {"images", "relues"}."""
    cv2 = _cv2()
    info = probe(src)
    w, h, fps = info["w"], info["h"], info["fps"]
    if reader is None:
        from roblox import nettoyage as N
        reader = N.ocr()
    hide = [e for e in elements if e.get("action", "cacher") == "cacher"]
    drawn = [e for e in hide if e.get("type") in DRAWN]
    boxes = [e for e in hide if e.get("type") in ("pseudo", "numero")]
    sam = shapes(src, drawn, info, os.path.join(work, "sam"))
    hues = learn_colours(src, reader, info)
    looks = sticker_looks(src, drawn + [e for e in hide if e.get("type") == "pseudo"], w, h)
    total = max(1, int(info["duree"] * fps))
    tmp = out + ".part.mp4"                               # never a half-written file taken for a done one
    enc = _writer(tmp, src, info)
    kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    k, last, before, found = 0, None, None, []
    for img in _frames(src, w, h):
        t = k / fps
        small = cv2.resize(img, (w // 2, h // 2))
        zones = zones_at(hide, t, w, h)
        if k % EVERY == 0 or last is None:          # read one image in EVERY: his last two readings kept between
            before, last = last, read_in(reader, small, zones, 2, 0.2)
        if not zones.any():
            mask = np.zeros((h, w), np.uint8)       # his text gone: nothing carried over
        else:
            mask = last.copy() if before is None else cv2.bitwise_or(last, before)
        if hues and zones.any():
            mask = cv2.bitwise_or(mask, colour_mask(img, hues, zones))
        if k in sam:
            mask = cv2.bitwise_or(mask, cv2.dilate(cv2.resize(sam[k].astype(np.uint8) * 255, (w, h),
                                                              interpolation=cv2.INTER_NEAREST), kern))
        elif not any(e["debut"] - 0.6 <= t <= e["fin"] + 1.0 for e in drawn):
            if k % EVERY == 0:                       # a sticker barely moves in 3 images: its place kept
                found = find_looks(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), looks)
            for x0, y0, x1, y1 in found:
                cv2.rectangle(mask, (x0 * 2 - 10, y0 * 2 - 10), (x1 * 2 + 10, y1 * 2 + 10), 255, -1)
        for e in boxes:
            if e["debut"] - 0.4 <= t <= e["fin"] + 0.4:
                x0, y0, x1, y1 = grown(e, w, h, 0.35)
                mask[y0:y1, x0:x1] = 255
        if mask.any():
            img = _inpaint(img, mask, kern)
        enc.stdin.write(img.tobytes())
        k += 1
        if progress and k % 30 == 0:
            progress(min(0.8, 0.8 * k / total))
    enc.stdin.close()
    if enc.wait():
        raise RepriseError("Le nettoyage n'a pas pu écrire la vidéo.")
    again = recheck(tmp, src, info, reader, hide, progress)
    os.replace(tmp, out)
    return {"images": k, "relues": again}


def recheck(path: str, src: str, info: Dict, reader, hide: List[Dict],
            progress: Optional[Callable[[float], None]] = None) -> int:
    """The clean video read again at full size in his captions' places: a word left erased there and on the HOLD
    images around it (filmed text elsewhere is left) -> the number of images taken again."""
    cv2 = _cv2()
    w, h, fps = info["w"], info["h"], info["fps"]
    total = max(1, int(info["duree"] * fps))
    left: Dict[int, np.ndarray] = {}
    for k, img in enumerate(_frames(path, w, h)):
        if progress and k % 30 == 0:
            progress(0.8 + 0.15 * k / total)
        if k % 2:                                    # one image in 2: HOLD + 1 around a word left covers the other
            continue
        zones = zones_at(hide, k / fps, w, h).astype(np.uint8) * 255
        if not zones.any():
            continue
        m = read_in(reader, img, zones > 0, 1, 0.3)
        if m.any():
            for j in range(k - HOLD - 1, k + HOLD + 2):
                left[j] = left.get(j, np.zeros((h, w), np.uint8)) | m
    if not left:
        return 0
    kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    again = path + ".2.mp4"
    enc = _writer(again, src, info)
    for k, img in enumerate(_frames(path, w, h)):
        if k in left:
            img = cv2.inpaint(img, cv2.dilate(left[k], kern), 6, cv2.INPAINT_TELEA)
        enc.stdin.write(img.tobytes())
    enc.stdin.close()
    if enc.wait():
        raise RepriseError("La relecture du nettoyage n'a pas pu écrire la vidéo.")
    os.replace(again, path)
    return len(left)
