"""
The reference Short's shots as clean pictures — what a reverse image search
needs. The Short is downloaded (the YouTube cookies file helps), cut with the
same cut detection as the sources, and each shot gives one picture (three for
a long shot: the action may not be in the middle). Gemini marks the real
picture area and what was added on top (banners, captions, logos): the
picture is cropped to the area, an added strip along its top or bottom edge
is cut, anything else is painted over from its surroundings — a search engine must see the scene, not
the re-uploader's text.

Without a download (YouTube still refusing), YouTube's three public frames
(25 / 50 / 75 %) are used instead.
"""

import os
import subprocess
import urllib.request
from typing import Callable, Dict, List, Optional

from PIL import Image

from adaptation import sources

LONG_SHOT = 4.0          # longer shots give 3 pictures
MAX_FRAMES = 18          # one search each: keep the analysis a few minutes long
WIDTH = 960


def _raw_still(path: str, t: float, out: str) -> str:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1",
                    "-vf", f"scale={WIDTH}:-2", "-q:v", "2", out], check=False)
    return out


def clean(raw: str, area: Optional[List[int]], boxes: List[List[int]], out: str) -> Optional[str]:
    """Crop to the real picture, cut an added strip at its top/bottom edge,
    blur any other added text. Coordinates 0-1000 on the raw still."""
    try:
        im = Image.open(raw).convert("RGB")
    except OSError:
        return None
    W, H = im.size
    y0, x0, y1, x1 = area if area and len(area) == 4 and area[2] > area[0] and area[3] > area[1] else (0, 0, 1000, 1000)
    left, top, right, bottom = int(x0 * W / 1000), int(y0 * H / 1000), int(x1 * W / 1000), int(y1 * H / 1000)
    cut_top, cut_bot, holes = top, bottom, []
    for b in boxes:
        by0, bx0, by1, bx1 = (int(b[0] * H / 1000), int(b[1] * W / 1000), int(b[2] * H / 1000), int(b[3] * W / 1000))
        if by1 <= top or by0 >= bottom:
            continue
        span = bottom - top
        if by0 - top < span * 0.22:                       # a banner along the top edge
            cut_top = max(cut_top, by1)
        elif bottom - by1 < span * 0.22:                  # captions along the bottom edge
            cut_bot = min(cut_bot, by0)
        else:                                             # in the middle: filled from around it
            holes.append((max(bx0, 0), max(by0, 0), min(bx1, W), min(by1, H)))
    if holes:
        im = _fill(im, holes)
    if cut_bot - cut_top < (bottom - top) * 0.45:         # cutting would eat the picture
        cut_top, cut_bot = top, bottom
    pic = im.crop((left, cut_top, right, cut_bot))
    if pic.width < 120 or pic.height < 120:
        return None
    pic.save(out, quality=92)
    return out


def _fill(im: Image.Image, holes) -> Image.Image:
    """Added text in the middle of the picture, rebuilt from its surroundings
    (a plain blur keeps a white caption box white)."""
    import cv2
    import numpy as np
    arr = np.array(im)
    mask = np.zeros(arr.shape[:2], np.uint8)
    for x0, y0, x1, y1 in holes:
        mask[max(y0 - 3, 0):y1 + 3, max(x0 - 3, 0):x1 + 3] = 255
    return Image.fromarray(cv2.inpaint(arr, mask, 7, cv2.INPAINT_TELEA))


def _plan_of(t: float, plans: List[Dict]) -> Optional[int]:
    for i, p in enumerate(plans):
        try:
            if float(p.get("debut", 0)) <= t < float(p.get("fin", 0)):
                return i
        except (TypeError, ValueError):
            continue
    return None


def _scene_of(plan: Optional[int], scenes: List[Dict]) -> Optional[int]:
    if plan is None:
        return None
    for i, s in enumerate(scenes):
        if plan in (s.get("plans") or []):
            return i
    return None


def _times(shots) -> List[float]:
    times = []
    for a, b in shots:
        if b - a > LONG_SHOT:
            times += [a + (b - a) * f for f in (0.25, 0.5, 0.75)]
        else:
            times.append((a + b) / 2)
    if len(times) > MAX_FRAMES:                           # spread the budget over the whole Short
        step = len(times) / MAX_FRAMES
        times = [times[int(k * step)] for k in range(MAX_FRAMES)]
    return times


def _public_frames(url: str, work_dir: str, duration: float) -> List[tuple]:
    from adaptation.finder import _video_id
    vid = _video_id(url)
    out = []
    for k in (1, 2, 3):
        dest = os.path.join(work_dir, f"public{k}.jpg")
        try:
            urllib.request.urlretrieve(f"https://i.ytimg.com/vi/{vid}/maxres{k}.jpg", dest)
            out.append((dest, duration * k / 4))
        except Exception:
            continue
    return out if vid else []


def reference_frames(ref: Dict, reference_url: str, work_dir: str, scenes: List[Dict],
                     report: Optional[Callable[[str, float], None]] = None) -> Dict:
    """{"frames": [{"file", "t", "plan", "scene"}], "source": "short" | "youtube" | None, "error"}"""
    report = report or (lambda phase, f: None)
    os.makedirs(work_dir, exist_ok=True)
    plans = ref.get("plans") or []
    raws, source, error = [], None, None
    try:
        report("images du Short : téléchargement", 0.0)
        try:
            path = sources.download(reference_url, work_dir, "short")
        except sources.SourceError:
            from adaptation.finder import _video_id
            vid = _video_id(reference_url)               # YouTube's refusals come and go: once more, other spelling
            if not vid:
                raise
            path = sources.download(f"https://www.youtube.com/watch?v={vid}", work_dir, "short")
        info = sources.probe(path)
        shots = sources.detect_cuts(path, info, None, min_len=0.8) or [(0.0, info["duration"])]
        raws = [(_raw_still(path, t, os.path.join(work_dir, f"raw{k:02d}.jpg")), t)
                for k, t in enumerate(_times(shots))]
        source = "short"
    except sources.SourceError as e:
        error = str(e)
        raws = _public_frames(reference_url, work_dir, float(ref.get("duree_s") or 30))
        source = "youtube" if raws else None
    raws = [(p, t) for p, t in raws if os.path.exists(p)]
    if not raws:
        return {"frames": [], "source": None, "error": error or "Aucune image du Short."}
    report("images du Short : nettoyage", 0.5)
    found = sources.find_boxes([p for p, _ in raws])
    frames = []
    for k, ((raw, t), (area, boxes, _)) in enumerate(zip(raws, found)):
        name = f"f{k:02d}.jpg"
        if clean(raw, area, boxes, os.path.join(work_dir, name)):
            plan = _plan_of(t, plans) if source == "short" else None
            frames.append({"file": name, "t": round(t, 2), "plan": plan, "scene": _scene_of(plan, scenes)})
    return {"frames": frames, "source": source, "error": error}
