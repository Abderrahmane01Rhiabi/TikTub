"""A style + words -> the .ass and its extras, the ffmpeg filters that burn them in a space's own render, the
gallery's previews, the faces (OpenCV YuNet) and the person's mask (SAM 2.1) some styles need."""

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from captions import styles as S
from captions.core import FPS, H, ROOT, W, Ctx, Words, fonts_dir, header, rgb, strong_words

YUNET = os.path.join(ROOT, "modeles", "face_detection_yunet_2023mar.onnx")
YUNET_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
PREVIEW_VERSION = 2                     # bump: every cached gallery preview is made again


class CaptionError(Exception):
    pass


@dataclass
class Built:
    """A style drawn for a video: its .ass text, and what ffmpeg must add beside it."""
    style: str
    ass: str
    extras: Dict = field(default_factory=dict)
    needs: Tuple[str, ...] = ()

    @property
    def plain(self) -> bool:
        return not any(self.extras.get(k) for k in ("blend", "perspective", "emojis", "sounds", "behind"))


def build(style_id: str, words: Words, ctx: Ctx, params: Optional[Dict] = None) -> Built:
    st = S.get(style_id)
    if not st:
        raise CaptionError(f"Style de sous-titres inconnu : {style_id}")
    words = [list(w) for w in words if str(w[0]).strip()]
    if not words:
        return Built(style_id, header([]), {}, st.needs)
    p = st.clean(params)
    token = S.SPEED.set(S.SPEED_OF.get(p.get("animation", "normale"), 1.0))
    try:
        styles_, events_, extras = st.build(words, ctx, p)
    finally:
        S.SPEED.reset(token)
    text = events_ if styles_ is None else header(styles_, ctx.size) + "\n".join(events_) + "\n"
    if extras.get("behind"):              # the big words: their own file, drawn under the person
        extras = dict(extras, behind_ass=header(styles_, ctx.size) + "\n".join(extras["behind"]) + "\n")
    return Built(style_id, text, extras, st.needs)


# ---------------------------------------------------------------- the filters a space adds to its own graph

def _fp(path: str) -> str:
    """A path inside a filtergraph: \\ : ' escaped."""
    return os.path.abspath(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def emoji_png(ch: str, out_dir: str) -> str:
    from PIL import Image, ImageDraw, ImageFont
    path = os.path.join(out_dir, f"emoji_{ord(ch[0]):x}.png")
    if not os.path.exists(path):
        font = ImageFont.truetype(EMOJI_FONT, 109)                  # Noto Color Emoji: a bitmap font, 109 px only
        img = Image.new("RGBA", (160, 140), (0, 0, 0, 0))
        ImageDraw.Draw(img).text((0, 0), ch, font=font, embedded_color=True)
        img.crop(img.getbbox() or (0, 0, 160, 140)).save(path)
    return path


def filters(built: Built, src: str, add_input: Callable[..., int], work: str, size=(W, H), fps: int = FPS,
            mask: Optional[Tuple[str, Tuple[int, int, int, int]]] = None, tag: str = "cap") -> Tuple[List[str], str, List[str]]:
    """The filters burning `built` onto the stream [src] -> (filters, the picture's label, the audio labels to mix).
    add_input(*args) adds an ffmpeg input and returns its index (the space's own helper). mask: (mask video of the
    zone, zone) for the text behind the person — without it the big words are drawn in front."""
    os.makedirs(work, exist_ok=True)
    fonts = fonts_dir()
    w, h = size
    ass = os.path.join(work, f"{tag}.ass")
    text = built.ass
    if built.extras.get("behind") and not mask:          # no mask: the big words simply in front
        text = text.rstrip("\n") + "\n" + "\n".join(built.extras["behind"]) + "\n"
    with open(ass, "w", encoding="utf-8") as fh:
        fh.write(text)
    draw = f"ass='{_fp(ass)}':fontsdir='{_fp(fonts)}':shaping=complex"   # complex: Arabic final forms (ه ة)
    g, cur = [], src
    blend, angle = built.extras.get("blend"), built.extras.get("perspective")
    if built.extras.get("behind") and mask:
        big = os.path.join(work, f"{tag}_behind.ass")
        with open(big, "w", encoding="utf-8") as fh:
            fh.write(built.extras["behind_ass"])
        mi = add_input("-i", mask[0])
        x, y, zw, zh = mask[1]
        g += [f"[{cur}]split[{tag}a][{tag}b]",
              f"[{tag}a]ass='{_fp(big)}':fontsdir='{_fp(fonts)}':shaping=complex[{tag}t]",
              f"[{tag}b]crop={zw}:{zh}:{x}:{y},format=yuva420p[{tag}p]",
              f"[{mi}:v]scale={zw}:{zh},format=gray[{tag}m]", f"[{tag}p][{tag}m]alphamerge[{tag}pm]",
              f"[{tag}t][{tag}pm]overlay={x}:{y}:shortest=1[{tag}0]"]
        cur = f"{tag}0"
    if blend or angle:
        bg = "0x808080" if blend == "softlight" else "black"            # soft light: grey leaves the picture as it is
        g.append(f"color={bg}:s={w}x{h}:r={fps},{draw},format=gbrp[{tag}txt]")
        layer = f"{tag}txt"
        if angle:
            d = int(w * angle / 100)
            g.append(f"[{layer}]perspective=x0={d}:y0={int(d * 1.5)}:x1={w - d}:y1={d // 2}:x2={d}:y2={h - int(d * 1.5)}:"
                     f"x3={w - d}:y3={h - d // 2}:sense=destination[{tag}tp]")
            layer = f"{tag}tp"
        mode = blend or "lighten"
        g.append(f"[{cur}]format=gbrp[{tag}base];[{tag}base][{layer}]blend=all_mode={mode}:shortest=1,format=yuv420p[{tag}1]")
        cur = f"{tag}1"
    else:
        g.append(f"[{cur}]{draw}[{tag}1]")
        cur = f"{tag}1"
    for i, (ch, a, b, x, y) in enumerate(built.extras.get("emojis") or []):
        ei = add_input("-loop", "1", "-i", emoji_png(ch, work))
        g.append(f"[{ei}:v]scale=-1:80,format=rgba[{tag}e{i}];[{cur}][{tag}e{i}]overlay=x={x:.0f}-overlay_w/2:y={y:.0f}-overlay_h/2:"
                 f"enable='between(t,{a:.3f},{b:.3f})':shortest=1[{tag}w{i}]")
        cur = f"{tag}w{i}"
    audio = []
    for i, (path, at, vol) in enumerate(built.extras.get("sounds") or []):
        if at is None or not os.path.exists(path):
            continue
        si = add_input("-i", path)
        ms = int(max(0.0, at) * 1000)
        g.append(f"[{si}:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={vol:.2f},adelay={ms}:all=1[{tag}s{i}]")
        audio.append(f"[{tag}s{i}]")
    return g, cur, audio


# ---------------------------------------------------------------- faces and the person's mask

def _yunet():
    import cv2
    if not os.path.exists(YUNET):
        import requests
        os.makedirs(os.path.dirname(YUNET), exist_ok=True)
        r = requests.get(YUNET_URL, timeout=60)
        r.raise_for_status()
        with open(YUNET + ".part", "wb") as fh:
            fh.write(r.content)
        os.replace(YUNET + ".part", YUNET)
    return cv2


def faces(video: str, zone: Tuple[int, int, int, int], fps: float = 5.0, until: Optional[float] = None,
          time_map: Optional[Callable[[float], Optional[float]]] = None, fit: str = "cover") -> List[Tuple[float, Tuple]]:
    """[(t, (x0, y0, x1, y1)) on the canvas] of the biggest face, fps times a second. The video is shown in `zone`
    scaled to cover it (or `fit="stretch"`: it IS the zone); a video shorter than `until` loops (a Génération
    background); time_map: the video's own time -> the output's (a Montage auto's kept ranges), None = not shown."""
    cv2 = _yunet()
    cap = cv2.VideoCapture(video)
    vfps = cap.get(cv2.CAP_PROP_FPS) or 25
    vw, vh = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    if not vw or not vh:
        return []
    zx, zy, zw, zh = zone
    s = max(zw / vw, zh / vh) if fit == "cover" else None
    det = cv2.FaceDetectorYN.create(YUNET, "", (vw, vh), score_threshold=0.6)
    found, step, k = [], max(1, round(vfps / fps)), 0
    while True:
        ok, img = cap.read()
        if not ok:
            break
        if k % step == 0:
            _, boxes = det.detect(img)
            if boxes is not None and len(boxes):
                x, y, bw, bh = max(boxes[:, :4].tolist(), key=lambda b: b[2] * b[3])
                if s:
                    ox, oy = (vw * s - zw) / 2, (vh * s - zh) / 2
                    box = (zx + x * s - ox, zy + y * s - oy, zx + (x + bw) * s - ox, zy + (y + bh) * s - oy)
                else:
                    box = (zx + x * zw / vw, zy + y * zh / vh, zx + (x + bw) * zw / vw, zy + (y + bh) * zh / vh)
                found.append((k / vfps, box))
        k += 1
    cap.release()
    dur = n / vfps if n else (found[-1][0] if found else 0)
    out = []
    for t, box in found:
        for rep in range(int((until or dur) // max(dur, 0.1)) + 1 if until and dur else 1):
            tt = t + rep * dur
            tt = time_map(tt) if time_map else tt
            if tt is not None and (until is None or tt <= until):
                out.append((tt, box))
    return sorted(out)


def _cover_filter(zone, fit: str, scale: int) -> str:
    zx, zy, zw, zh = zone
    shown = (f"scale={zw}:{zh}:force_original_aspect_ratio=increase,crop={zw}:{zh}" if fit == "cover"
             else f"scale={zw}:{zh}")
    return f"{shown},scale={max(2, zw // scale)}:{max(2, zh // scale)}"


def scene(video: str, zone: Tuple[int, int, int, int], fit: str = "cover", fps: float = 3.0, scale: int = 4,
          until: Optional[float] = None, time_map: Optional[Callable[[float], Optional[float]]] = None):
    """The video as shown in the zone (covering it, or `fit="stretch"`: it IS the zone), 3 small grey images a second,
    on the output's timeline (time_map; a background shorter than `until` loops) -> core.Scene, or None."""
    import numpy as np
    from captions.core import Scene
    zx, zy, zw, zh = zone
    w, h = max(2, zw // scale), max(2, zh // scale)
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", video, "-vf",
                        f"fps={fps},{_cover_filter(zone, fit, scale)},format=gray", "-f", "rawvideo", "-"],
                       capture_output=True)
    n = len(r.stdout) // (w * h)
    if r.returncode or not n:
        return None
    arr = np.frombuffer(r.stdout[:n * w * h], np.uint8).reshape(n, h, w).astype(np.float32)
    dur = n / fps
    frames = []
    reps = int((until or dur) // max(dur, 0.1)) + 1 if until and dur else 1
    for rep in range(reps):
        for i in range(n):
            t = i / fps + rep * dur
            t = time_map(t) if time_map else t
            if t is not None and (until is None or t <= until):
                frames.append((t, arr[i]))
    frames.sort(key=lambda tf: tf[0])
    return Scene(frames, zone, scale)


def analyse(ctx: Ctx, style_id: str, params: Optional[Dict], video: Optional[str], fit: str = "cover",
            until: Optional[float] = None, time_map: Optional[Callable[[float], Optional[float]]] = None) -> Ctx:
    """What a style needs to see of the picture before it is drawn: the faces (« Évite le visage », or « Auto » that
    avoids them) and the scene (« Auto », « Lisibilité auto »). The spaces' own styles need nothing."""
    st = S.get(style_id)
    if not st or st.native or not video or not os.path.exists(video):
        return ctx
    p = st.clean(params)
    auto = p.get("position") == "auto" or "faces" in st.needs
    if "faces" in st.needs or (auto and p.get("eviter_visages") and ctx.anchor_y is None):
        try:
            ctx.faces = faces(video, ctx.zone, until=until, time_map=time_map, fit=fit)
        except Exception as e:                    # no model, unreadable video: placed without the faces
            print(f"⚠️ Visages introuvables ({e}) : placement sans eux")
    if auto or p.get("lisibilite"):
        try:
            ctx.scene = scene(video, ctx.zone, fit=fit, until=until, time_map=time_map)
        except Exception as e:
            print(f"⚠️ Image non analysée ({e}) : placement par défaut")
    return ctx


def person_mask(video: str, zone: Tuple[int, int, int, int], face_track: List, out: str, fps: int = 15) -> Optional[str]:
    """SAM 2.1 large (graphics card) follows the person from a box built on the first face (head to the bottom, ~2.6
    faces wide) and two points (face, chest) -> a softened mask video of the zone at 30 i/s, or None (no face)."""
    if not face_track:
        return None
    import cv2
    import numpy as np
    import torch
    from roblox import nettoyage as N
    zx, zy, zw, zh = zone
    work = out + "_sam"
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", video, "-vf", f"fps={fps},crop={zw}:{zh}:{zx}:{zy}",
                    "-q:v", "2", "-start_number", "0", os.path.join(work, "%05d.jpg")], check=True)
    count = len([f for f in os.listdir(work) if f.endswith(".jpg")])
    x0, y0, x1, y1 = [v - o for v, o in zip(face_track[0][1], (zx, zy, zx, zy))]
    fw, fh, cx = x1 - x0, y1 - y0, (x0 + x1) / 2
    box = np.array([max(0, cx - 1.3 * fw), max(0, y0 - 0.25 * fh), min(zw, cx + 1.3 * fw), zh], np.float32)
    pts = np.array([[cx, (y0 + y1) / 2], [cx, min(zh - 5, y1 + 0.8 * fh)]], np.float32)
    pred, masks = N.sam(), {}
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16, enabled=torch.cuda.is_available()):
        st = pred.init_state(video_path=work, offload_video_to_cpu=True)
        pred.add_new_points_or_box(inference_state=st, frame_idx=0, obj_id=1, box=box, points=pts,
                                   labels=np.ones(len(pts), np.int32))
        for idx, _, logits in pred.propagate_in_video(st):
            masks[idx] = (logits > 0).any(dim=0).float().cpu().numpy()[0] > 0
    last = np.zeros((zh, zw), bool)
    for i in range(count):
        last = masks.get(i, last)
        cv2.imwrite(os.path.join(work, f"m{i:05d}.png"), cv2.GaussianBlur(last.astype(np.uint8) * 255, (0, 0), 2.5))
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-framerate", str(fps), "-i", os.path.join(work, "m%05d.png"),
                    "-vf", f"fps={FPS},format=gray", "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", out], check=True)
    shutil.rmtree(work, ignore_errors=True)
    return out


# ---------------------------------------------------------------- the gallery's previews

SAMPLES = {
    "en": ("when they created this award, he was waiting in the wings.", {"created", "award", "waiting", "wings"}),
    "fr": ("quand ils ont créé ce prix, il attendait déjà en coulisses.", {"créé", "prix", "attendait", "coulisses"}),
    "ar": ("عندما أنشأوا هذه الجائزة، كان ينتظر خلف الكواليس.", {"أنشأوا", "الجائزة", "ينتظر", "الكواليس"}),
}


def sample_words(lang: str) -> Tuple[Words, set]:
    """The gallery's phrase, timed like speech (a word's time by its length, a breath after the comma)."""
    text, strong = SAMPLES.get(lang, SAMPLES["fr"])
    out, t = [], 0.25
    for tok in text.split():
        d = 0.12 + 0.045 * len(tok)
        out.append([tok, round(t, 3), round(t + d, 3)])
        t += d + (0.3 if tok[-1:] in ",،" else 0.02)
    return out, strong


def _preview_background(path: str, zone) -> str:
    """The gallery's backdrop: black, the frame filled with a library drone shot (else a soft gradient), rounded."""
    from PIL import Image, ImageDraw, ImageFilter
    if os.path.exists(path):
        return path
    zx, zy, zw, zh = zone
    canvas = Image.new("RGB", (W, H), (7, 7, 7))
    shot = None
    broll = os.path.join("assets", "broll")
    for f in sorted(os.listdir(broll)) if os.path.isdir(broll) else []:
        if f.endswith(".jpg"):
            shot = Image.open(os.path.join(broll, f)).convert("RGB")
            break
    if shot is None:
        shot = Image.new("RGB", (zw, zh), (40, 46, 60))
        ImageDraw.Draw(shot).ellipse((-zw // 2, zh // 3, zw * 3 // 2, zh * 2), fill=(70, 80, 104))
        shot = shot.filter(ImageFilter.GaussianBlur(60))
    s = max(zw / shot.width, zh / shot.height)
    shot = shot.resize((int(shot.width * s) + 1, int(shot.height * s) + 1))
    shot = shot.crop(((shot.width - zw) // 2, (shot.height - zh) // 2, (shot.width - zw) // 2 + zw, (shot.height - zh) // 2 + zh))
    mask = Image.new("L", (zw, zh), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, zw - 1, zh - 1), 40, fill=255)
    canvas.paste(shot, (zx, zy), mask)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    canvas.save(path)
    return path


def preview(style_id: str, lang: str = "fr", params: Optional[Dict] = None, colour: str = "#FF7A00") -> str:
    """A 4-s silent preview of a style on the gallery's phrase (540x960) -> its path, made once and cached in
    temp/caption_previews (kept by the storage cleanup)."""
    st = S.get(style_id)
    if not st:
        raise CaptionError(f"Style de sous-titres inconnu : {style_id}")
    lang = lang if lang in SAMPLES else "fr"
    p = st.clean(params)
    key = hashlib.sha1(json.dumps([PREVIEW_VERSION, style_id, lang, p, colour], sort_keys=True).encode()).hexdigest()[:16]
    out_dir = os.path.abspath(os.path.join("temp", "caption_previews"))
    out = os.path.join(out_dir, f"{style_id}_{lang}_{key}.mp4")
    if os.path.exists(out):
        return out
    os.makedirs(out_dir, exist_ok=True)
    zone = (87, 507, 906, 906)
    words, strong = sample_words(lang)
    ctx = Ctx(lang=lang, zone=zone, strong=strong, impact=sorted(strong, key=len)[-1], colour=colour)
    built = build(style_id, words, ctx, p)
    dur = words[-1][2] + 0.9
    bg = _preview_background(os.path.join(out_dir, "fond.png"), zone)
    inputs = ["-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.2f}", "-i", bg]
    count = [1]

    def add_input(*args):
        inputs.extend(args)
        count[0] += 1
        return count[0] - 1
    work = os.path.join(out_dir, f"work_{key}")
    g, cur, audio = filters(built, "0:v", add_input, work)
    g.append(f"[{cur}]scale=540:960,format=yuv420p[v]")
    sound = ["-an"]
    if audio:                               # a style that plays a sound (« Clic »): heard in its preview
        g.append(f"anullsrc=r=44100:cl=stereo[sil];[sil]{''.join(audio)}amix=inputs={len(audio) + 1}:duration=first:normalize=0[a]")
        sound = ["-map", "[a]", "-c:a", "aac", "-b:a", "96k"]
    tmp = out + ".part.mp4"
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(g), "-map", "[v]",
                        *sound, "-t", f"{dur:.2f}", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                        "-movflags", "+faststart", tmp], capture_output=True, text=True)
    shutil.rmtree(work, ignore_errors=True)
    if r.returncode:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise CaptionError(f"Aperçu impossible : {r.stderr[-400:]}")
    os.replace(tmp, out)
    return out


# ---------------------------------------------------------------- a channel's choice

def channel_choice(channel: Optional[str]) -> Dict:
    """profile["sous_titres"] of a channel: {"style": id or None (the space's own), "params": {...}}."""
    if not channel:
        return {"style": None, "params": {}}
    try:
        from channel_manager import ChannelManager
        prof = ChannelManager().get_channel_profile(channel) or {}
    except Exception:
        return {"style": None, "params": {}}
    raw = prof.get("sous_titres") or {}
    st = S.get(raw.get("style"))
    return {"style": st.id if st else None, "params": st.clean(raw.get("params")) if st else {}}


def channel_colour(channel: Optional[str]) -> str:
    try:
        cfg = json.load(open(os.path.join("channels", "channel_config.json"), encoding="utf-8"))
        node = cfg.get("channels", cfg) if isinstance(cfg, dict) else {}
        return (node.get(channel) or {}).get("color") or "#FF7A00"
    except Exception:
        return "#FF7A00"


def context(lang: str, zone, words: Words, keywords=None, channel: Optional[str] = None, faces_=None) -> Ctx:
    """The usual context: the strong words (Gemini's key words, else the heuristic), the channel's colour."""
    strong = strong_words(words, keywords)
    impact = None
    for w in reversed(words):
        from captions.core import bare
        if bare(w[0]) in strong:
            impact = bare(w[0])
            break
    return Ctx(lang=lang or "fr", zone=tuple(int(v) for v in zone), strong=strong, impact=impact,
               colour=channel_colour(channel), faces=faces_ or [])
