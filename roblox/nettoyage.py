"""
The cleaning of a passage before any montage (labs etude_roblox/style/nettoyage_gpu_v1..v6, 2026-10-29/30): what the
creator added on top of the game is hidden IN ITS OWN SHAPE — the person refused rectangles ("ça rend la vidéo
bizarre") — and the result must be good WITHOUT our mascot (checked on clean-only sheets at 10 images/s).

    avatars, stickers   SAM 2.1 large follows each element Gemini found (roblox/identite.detect), its box and two
                        points (body, head) given at 3 instants; its tracking is trusted (only the whole scenery is
                        refused), a lost shape is carried on along its motion until it leaves the picture, the parts
                        in the avatar's sticker style (white outline, bright colours) that touch it are added (an arm
                        swung out at once), each shape also hidden 4 images around it
    webcam, logo        their box (they are rectangles; SAM on a webcam over a plain floor took the floor)
    names               EasyOCR reads every image (10/s) and hides what is a player's name — a word with "_" or
                        letters and digits, or a name Gemini saw — never the game's own sentences
    captions            the creator's captions at the bottom: the bottom band cut (the top KEEP of the picture kept)

On the graphics card (torch for CUDA, the RTX 3060: SAM 2.1 large ~0.16 s an image); on the processor it works but
~30 times slower. The model (~900 MB) is downloaded once into modeles/.
"""

import difflib
import os
import re
import shutil
import subprocess
from typing import Dict, List, Optional

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.path.join(HERE, "modeles", "sam2.1_hiera_large.pt")
MODEL_URL = "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt"
CONFIG = "configs/sam2.1/sam2.1_hiera_l.yaml"
FPS, SW, SH = 30, 960, 540                       # the mask: 30 images/s at half size
SAM_FPS = 15                                     # SAM follows at 15 images/s, each shape kept for the image after
                                                 # too (30/s took ~2.5 min a passage; TWIN covers the rest)
KEEP = 0.80                                      # the top of the picture kept when the creator's captions are below
SCENERY, MIN_PX, NEAR, TWIN = 0.30, 60, 8, 4
GROW_AV, GROW_TXT = 7, 3
OCR_FPS, OCR_HOLD = 10, 0.5
UI = {"cells", "phones", "yard", "desert", "teleport", "bathroom", "dungeon", "captures", "employees", "month", "top", "player",
      "your", "time", "cooldown", "security", "cafeteria", "exit", "of", "the", "buy", "item", "cancel", "shop", "settings",
      "inventory", "health", "level", "coins", "robux", "everyone", "slap", "end"}
NOT_NAMES = {"pseudo", "pseudos", "player", "joueur", "joueurs", "tableau", "scores", "dessus", "personnage", "top", "message",
             "chat", "dans", "sous", "jeu"}
KNOWN: set = set()                               # the names Gemini saw in this passage


class NettoyageError(RuntimeError):
    pass


def _run(cmd: List[str]) -> None:
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode:
        raise NettoyageError(f"{os.path.basename(cmd[0])} : {r.stderr.decode(errors='replace').strip()[-400:]}")


# ---------------------------------------------------------------- names

def known_names(elements: List[Dict]) -> set:
    """The names written in Gemini's descriptions of the "pseudo" elements ("Pseudo bigman_melon au-dessus…")."""
    out = set()
    for e in elements:
        if e.get("type") != "pseudo":
            continue
        for w in e.get("description", "").split():
            w = w.strip(".,:;()'\"«»")
            if len(w) >= 4 and w.lower() not in NOT_NAMES and ("_" in w or re.search(r"\d", w) or w[:1].isupper()) \
                    and not (w[:1].isupper() and w[1:].islower() and len(w) < 5):
                out.add(w.lower())
    return {n for n in out if "_" in n or re.search(r"\d", n)} | {n for n in out if n.isalpha() and n not in NOT_NAMES and len(n) > 5}


def looks_like_name(text: str) -> bool:
    """A player's name: one word with "_" or letters and digits, or close to a name Gemini saw — never a sentence of the
    game ("TELEPORT TO END", "EVERYONE TO END" were hidden in Slap Tower)."""
    t = text.strip()
    low = re.sub(r"[^a-z0-9_]", "", t.lower())
    if len(low) < 4 or low in UI:
        return False
    if any(k and (k in low or low in k and len(low) >= 6 or difflib.SequenceMatcher(None, low, k).ratio() >= 0.75) for k in KNOWN):
        return True
    words = t.split()
    if len(words) > 2 or all(w.lower().strip(".,!?") in UI for w in words):
        return False
    return "_" in t or bool(re.search(r"\d", low) and re.search(r"[a-z]", low) and len(words) == 1)


# ---------------------------------------------------------------- shapes

def _cv2():
    import cv2
    return cv2


def _kernel(r: int):
    cv2 = _cv2()
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def whole(m: np.ndarray) -> np.ndarray:
    """The avatar in one piece: near pieces joined and holes filled (sunglasses stayed sharp in a face) — its shape."""
    cv2 = _cv2()
    u = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_CLOSE, _kernel(15))
    contours, _ = cv2.findContours(u, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(u)
    cv2.drawContours(filled, contours, -1, 1, thickness=cv2.FILLED)
    return filled > 0


def in_time(masks: Dict[int, np.ndarray]) -> Dict[int, np.ndarray]:
    """Each image also hides what the shape covered in the TWIN images around it (an arm swung out faster than SAM)."""
    out: Dict[int, np.ndarray] = {}
    for i in sorted(masks):
        for j in range(i - TWIN, i + TWIN + 1):
            out[j] = out[j] | masks[i] if j in out else masks[i].copy()
    return out


def with_sticker_parts(m: np.ndarray, jpg: str) -> np.ndarray:
    """The avatar plus what touches it in a sticker's style (white outline, bright flat colours) around it; kept only if
    it stays close to the avatar's size (a colourful game must not flood in)."""
    cv2 = _cv2()
    if not m.any() or not os.path.exists(jpg):
        return m
    hsv = cv2.cvtColor(cv2.imread(jpg), cv2.COLOR_BGR2HSV)
    s, v = hsv[..., 1].astype(int), hsv[..., 2].astype(int)
    style = ((s > 140) & (v > 90)) | ((s < 30) & (v > 235))
    ys, xs = np.nonzero(m)
    h, w = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
    zone = np.zeros_like(m)
    zone[max(0, ys.min() - h // 2):min(SH, ys.max() + h // 2), max(0, xs.min() - w):min(SW, xs.max() + w)] = True
    _, lab = cv2.connectedComponents(((style & zone) | m).astype(np.uint8), connectivity=8)
    touching = set(np.unique(lab[cv2.dilate(m.astype(np.uint8), _kernel(GROW_AV)) > 0])) - {0}
    out = np.isin(lab, list(touching)) | m
    return out if out.sum() <= 2.2 * m.sum() else m


def _grown(box, side=0.0, top=0.0):
    x0, y0, x1, y1 = box
    return [max(0.0, x0 - side), max(0.0, y0 - top), min(1.0, x1 + side), min(1.0, y1 + side)]


def _box_mask(box) -> np.ndarray:
    x0, y0, x1, y1 = box
    m = np.zeros((SH, SW), bool)
    m[int(y0 * SH):int(y1 * SH), int(x0 * SW):int(x1 * SW)] = True
    return m


def _frames(src: str, a: float, b: float, out: str, fps: int, w: int, h: int) -> int:
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{a}", "-t", f"{b - a}", "-i", src, "-vf", f"fps={fps},scale={w}:{h}",
          "-q:v", "2", "-start_number", "0", os.path.join(out, "%05d.jpg")])
    return len(os.listdir(out))


def _device() -> str:
    import torch
    return "cuda" if torch.cuda.is_available() else "cpu"


_MODELS: Dict[str, object] = {}                 # loaded once: reloading them for every passage filled the card's 6 GB


def _load_sam():
    if not os.path.exists(MODEL):
        import requests
        os.makedirs(os.path.dirname(MODEL), exist_ok=True)
        with requests.get(MODEL_URL, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(MODEL + ".part", "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        os.replace(MODEL + ".part", MODEL)
    from sam2.build_sam import build_sam2_video_predictor
    return build_sam2_video_predictor(CONFIG, MODEL, device=_device())


def _load_ocr():
    import easyocr
    return easyocr.Reader(["en"], gpu=_device() == "cuda", verbose=False)


def sam():
    """SAM 2.1 large, on the graphics card if there is one (downloaded once, loaded once)."""
    if "sam" not in _MODELS:
        _MODELS["sam"] = _load_sam()
    return _MODELS["sam"]


def ocr():
    if "ocr" not in _MODELS:
        _MODELS["ocr"] = _load_ocr()
    return _MODELS["ocr"]


def shapes(pred, src: str, elements: List[Dict], work: str) -> Dict[int, np.ndarray]:
    """{image of the passage at FPS: mask} of the avatars and stickers, followed by SAM."""
    import torch
    cuda = _device() == "cuda"
    allm: Dict[int, np.ndarray] = {}
    for k, e in enumerate(elements):
        sticker = e["type"] != "avatar"
        d0, d1 = max(0.0, e["debut"] - 0.6), e["fin"] + 1.0
        fdir = os.path.join(work, f"objet{k}")
        n = _frames(src, d0, d1, fdir, SAM_FPS, SW, SH)
        if not n:
            continue
        x0, y0, x1, y1 = _grown(e["cadre"], side=0.02, top=0.0 if sticker else 0.07)   # higher: a head stuck out above
        box = np.array([x0 * SW, y0 * SH, x1 * SW, y1 * SH], dtype=np.float32)
        bx0, by0, bx1, by1 = [int(v) for v in box]
        cx = (bx0 + bx1) / 2
        prompts = ([(1, box, [[cx, (by0 + by1) / 2]])] if sticker else
                   [(1, box, [[cx, by0 + 0.62 * (by1 - by0)]]),
                    (2, np.array([bx0, by0, bx1, by0 + 0.5 * (by1 - by0)], np.float32), [[cx, by0 + 0.22 * (by1 - by0)]])])
        keys = sorted({min(n - 1, max(0, round((t - d0) * SAM_FPS))) for t in (e["debut"] + 0.25, (e["debut"] + e["fin"]) / 2, e["fin"] - 0.25)})
        got: Dict[int, np.ndarray] = {}
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16, enabled=cuda):
            st = pred.init_state(video_path=fdir, offload_video_to_cpu=True)
            for f in keys:
                for obj, b, pts in prompts:
                    pred.add_new_points_or_box(inference_state=st, frame_idx=f, obj_id=obj, box=b,
                                               points=np.array(pts, np.float32), labels=np.ones(len(pts), np.int32))
            for reverse in (False, True):
                for idx, _, logits in pred.propagate_in_video(st, start_frame_idx=keys[-1] if reverse else keys[0], reverse=reverse):
                    m = (logits > 0).any(dim=0).float().cpu().numpy()[0] > 0
                    got[idx] = got[idx] | m if idx in got else m
        found = {i: m for i, m in got.items() if MIN_PX <= m.sum() <= SCENERY * SW * SH}
        filled = dict(found)
        order = sorted(found)
        for direction in (1, -1):                              # lost at the edge: carried on along its motion
            run = order if direction == 1 else order[::-1]
            if len(run) < 2:
                continue
            last, prev = run[-1], run[-2]
            c = lambda m: np.argwhere(m).mean(axis=0)
            dy, dx = (c(found[last]) - c(found[prev])) / max(1, abs(last - prev))
            if abs(dx) + abs(dy) < 1.5:
                continue
            m, i = found[last], last + direction
            while 0 <= i < n and i not in filled:
                m = np.roll(np.roll(m, int(round(dy)), axis=0), int(round(dx)), axis=1)
                if int(round(dx)) > 0:
                    m[:, :int(round(dx))] = False
                elif int(round(dx)) < 0:
                    m[:, int(round(dx)):] = False
                if m.sum() < MIN_PX:
                    break
                filled[i] = m
                i += direction
        cv2 = _cv2()
        for idx in range(n):
            m = filled.get(idx)
            if m is None:
                if not (e["debut"] <= d0 + idx / SAM_FPS <= e["fin"]):
                    continue
                near = [j for j in filled if abs(j - idx) <= NEAR]
                if not near:
                    continue
                m = filled[min(near, key=lambda j: abs(j - idx))]
            if not sticker:
                m = with_sticker_parts(m, os.path.join(fdir, f"{idx:05d}.jpg"))
            m = cv2.dilate(whole(m).astype(np.uint8), _kernel(GROW_AV)) > 0
            first = round((d0 + idx / SAM_FPS) * FPS)
            for i in range(first, first + FPS // SAM_FPS):                # the images of the mask this one stands for
                allm[i] = allm[i] | m if i in allm else m
        shutil.rmtree(fdir)
    if cuda:
        torch.cuda.empty_cache()
    return allm


def names(reader, src: str, spans: List[List[float]], work: str):
    """({image at FPS: mask} of every player name read in the spans, the names hidden). Two passes: what is a name,
    then what looks like one already read (OCR misreads: "CKIEMANERO")."""
    from PIL import Image, ImageDraw
    cv2 = _cv2()
    out: Dict[int, np.ndarray] = {}
    reads = []
    for k, (a, b) in enumerate(spans):
        fdir = os.path.join(work, f"ocr{k}")
        n = _frames(src, a, b, fdir, OCR_FPS, 1920, 1080)
        reads += [(a + i / OCR_FPS, reader.readtext(os.path.join(fdir, f"{i:05d}.jpg"))) for i in range(n)]
        shutil.rmtree(fdir)
    norm = lambda t: re.sub(r"[^a-z0-9]", "", t.lower())
    seen = {norm(t) for _, res in reads for _, t, _ in res if looks_like_name(t) and len(norm(t)) >= 5 and len(t.split()) <= 2}
    is_name = lambda t: looks_like_name(t) or (len(norm(t)) >= 5 and len(t.split()) <= 2 and any(
        norm(t) in k or difflib.SequenceMatcher(None, norm(t), k).ratio() >= 0.7 for k in seen))
    hidden = set()
    for t, res in reads:
        boxes = [pts for pts, text, _ in res if is_name(text) and not hidden.add(text)]
        if not boxes:
            continue
        im = Image.new("L", (SW, SH), 0)
        d = ImageDraw.Draw(im)
        for pts in boxes:
            d.polygon([(x * SW / 1920, y * SH / 1080) for x, y in pts], fill=255)
        m = cv2.dilate(np.asarray(im), _kernel(GROW_TXT)) > 0
        for i in range(round((t - OCR_HOLD) * FPS), round((t + OCR_HOLD) * FPS) + 1):
            out[i] = out[i] | m if i in out else m
    return out, sorted(hidden)


def _write_mask(masks: Dict[int, np.ndarray], length: float, path: str) -> None:
    cv2 = _cv2()
    p = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{SW}x{SH}",
                          "-r", f"{FPS}", "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "10", "-pix_fmt", "yuv420p", path],
                         stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    black = np.zeros((SH, SW), np.uint8).tobytes()
    for i in range(int(length * FPS) + 1):
        m = masks.get(i)
        p.stdin.write(black if m is None else cv2.GaussianBlur((m * 255).astype(np.uint8), (0, 0), 1.5).tobytes())
    p.stdin.close()
    if p.wait():
        raise NettoyageError("Le masque du nettoyage n'a pas pu être écrit.")


def _duration(path: str) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def clean(src: str, elements: List[Dict], spans: List[List[float]], out: str, work: str,
          reader=None, predictor=None) -> Dict:
    """The passage src with the creator's elements hidden -> {"fichier", "keep", "pseudos"}; spans: the seconds the
    Shorts use (names are read only there). Nothing to hide: the passage itself."""
    os.makedirs(work, exist_ok=True)
    keep = KEEP if any(e["type"] == "sous_titres_incrustes" and e["cadre"][1] >= 0.6 for e in elements) else 1.0
    masks: Dict[int, np.ndarray] = {}
    for e in elements:                                                # rectangles by nature, or captions up in the picture
        if e["type"] in ("webcam", "logo") or (e["type"] == "sous_titres_incrustes" and e["cadre"][1] < 0.6):
            m = _box_mask(_grown(e["cadre"], side=0.01, top=0.01))
            for i in range(round(e["debut"] * FPS), round(e["fin"] * FPS) + 1):
                masks[i] = masks[i] | m if i in masks else m
    followed = [e for e in elements if e["type"] in ("avatar", "autocollant", "texte_effet")]
    if followed:
        for i, m in shapes(predictor or sam(), src, followed, work).items():
            masks[i] = masks[i] | m if i in masks else m
    KNOWN.clear()
    KNOWN.update(known_names(elements))
    named, hidden = names(reader or ocr(), src, spans, work)
    masks = in_time(masks)
    for i, m in named.items():
        masks[i] = masks[i] | m if i in masks else m
    if not masks and keep == 1.0:
        return {"fichier": src, "keep": 1.0, "pseudos": hidden}
    mask = os.path.join(work, "masque.mp4")
    _write_mask(masks, _duration(src), mask)
    h = int(1080 * keep) // 2 * 2
    tmp = out + ".part.mp4"
    # the blur made at half size (4 times less work, the same blur to the eye: it took ~2.5 min a passage at full size)
    graph = ("[0:v]scale=1920:1080,split[o][c];[c]scale=960:540,gblur=sigma=22:steps=3,eq=saturation=0.12:brightness=-0.04,"
             "scale=1920:1080,format=yuva420p[b];"
             f"[1:v]scale=1920:1080,format=gray[m];[b][m]alphamerge[bm];[o][bm]overlay=eof_action=pass,crop=1920:{h}:0:0[v]")
    base = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", src, "-i", mask, "-filter_complex", graph, "-map", "[v]", "-map", "0:a?"]
    try:                                                              # encoded by the graphics card when there is one
        _run(base + ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "19", "-c:a", "copy", tmp])
    except NettoyageError:
        _run(base + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "copy", tmp])
    os.replace(tmp, out)
    os.remove(mask)
    return {"fichier": out, "keep": keep, "pseudos": hidden}
