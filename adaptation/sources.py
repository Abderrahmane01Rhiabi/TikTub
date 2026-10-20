"""
Source videos -> a catalogue of clean clips.

What was done by hand for the tram prototype, made generic:
  - the clean picture: a vertical video showing a 16:9 TV/camera band on a
    blurred copy of itself is cropped to that band (logo and subtitles in
    the blurred zone go away with it)
  - the cuts: frame-to-frame difference peaks
  - the crash/peak of each clip: the loudest 50 ms (or, on a quiet clip, the
    biggest picture jolt)
  - what each clip shows, whether it's usable, whether its sound has speech:
    asked to Gemini, clip by clip, on OUR cut times
  - watermarks / logos / channel names: boxes asked to Gemini on one still
    per clip; a strip along the top or bottom edge is cropped away, anything
    else is painted over (ffmpeg delogo)
"""

from contextlib import contextmanager
import json
import math
import os
import re
import string
import subprocess
from typing import Dict, List, Optional, Tuple

import numpy as np


class SourceError(RuntimeError):
    pass


# --------------------------------------------------------------- download / probe

MIN_CLIP = 1.0                            # shorter: unticked as "trop court"
COOKIES_FILE = "youtube_cookies.txt"      # a cookies.txt export, when YouTube asks to "confirm you're not a bot"


def ytdlp_opts(**extra) -> Dict:
    """What every yt-dlp call shares: quiet, the cookies file when there is
    one, node as JavaScript runtime (recent YouTube needs one)."""
    import shutil as _sh
    opts = {"quiet": True, "no_warnings": True, "noprogress": True}
    cookies = os.getenv("YTDLP_COOKIES") or COOKIES_FILE
    if os.path.exists(cookies):
        opts["cookiefile"] = cookies
    if _sh.which("node") and not _sh.which("deno"):
        opts["js_runtimes"] = {"node": {}}
    return {**opts, **extra}


def explain(url: str, err: str) -> str:
    """yt-dlp's error, said plainly."""
    err = re.sub(r"\x1b\[[0-9;]*m", "", err).replace("ERROR: ", "")       # yt-dlp's terminal colours
    low = err.lower()
    youtube = "youtube.com" in url or "youtu.be" in url
    if not youtube and ("not a bot" in low or "429" in low or "sign in" in low or "log in" in low or "login" in low):
        from adaptation.imagesearch import platform
        return (f"{platform(url)} refuse le téléchargement de cette vidéo ({url}) : il demande d'être connecté ou "
                f"limite les téléchargements. Prends une autre vidéo pour ce plan, ou réessaie plus tard.")
    if "not a bot" in low or "429" in low or "sign in" in low:
        return (f"YouTube bloque le téléchargement ({url}) : il demande de « confirmer que tu n'es pas un robot ». "
                f"Ça passe souvent tout seul après une heure. Sinon : exporte les cookies de ton navigateur "
                f"(extension « Get cookies.txt LOCALLY », en étant connecté à YouTube) dans le fichier "
                f"{COOKIES_FILE} à la racine de TikTub, ou prends la même vidéo sur TikTok.")
    if any(w in low for w in ("private", "unavailable", "not available", "removed", "blocked", "country")):
        return f"Vidéo impossible à télécharger d'ici (supprimée, privée ou bloquée dans ton pays) : {url}"
    return f"Téléchargement impossible ({url}) : {err[:200]}"

def _refused(err: str) -> bool:
    low = err.lower()
    return ("not a bot" in low or "429" in low or "page needs to be reloaded" in low
            or "http error 403" in low)          # YouTube's 403 on a video it served a minute before: passing


def _fetch(url: str, opts: Dict) -> Dict:
    """One yt-dlp run; YouTube's "not a bot" refusals come and go (measured: a
    Short refused, then fetched a minute later), so a refusal is tried once more."""
    import time
    import yt_dlp
    waits = (10, 25)                    # measured: a 403 still there after 8 s was gone a few minutes later
    for attempt in range(len(waits) + 1):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return {"info": info, "path": _final_path(ydl, info)}
        except Exception as e:
            if attempt < len(waits) and _refused(str(e)):
                time.sleep(waits[attempt])
                continue
            raise SourceError(explain(url, str(e)))


def _handle(info: Dict) -> Optional[str]:
    """The account's name: TikTok's uploader_id is a number, its uploader the @name."""
    for v in (info.get("uploader_id"), info.get("uploader"), info.get("channel")):
        v = str(v or "").strip().lstrip("@")
        if v and not v.replace("_", "").lstrip("-").isdigit() and " " not in v:
            return "@" + v
    return None


# Picture AND sound: "mp4/best" once took a YouTube video-only stream (398), and the crash sounds need the sound
# H.264 first: a VP9 stream over HLS cut into sections once came out as sound only
VIDEO_FORMAT = ("bv*[vcodec^=avc1][height<=1080]+ba[ext=m4a]/bv*[ext=mp4][height<=1080]+ba[ext=m4a]/"
                "b[ext=mp4]/bv*[height<=1080]+ba/b")


def has_picture(path: str) -> bool:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=codec_type",
                              "-of", "csv=p=0", path], capture_output=True, text=True).stdout
        return "video" in out
    except OSError:
        return False


def _final_path(ydl, info: Dict) -> str:
    """Where the file really is: a merged download ends in .mp4 whatever the parts were."""
    path = ydl.prepare_filename(info)
    merged = os.path.splitext(path)[0] + ".mp4"
    return merged if not os.path.exists(path) and os.path.exists(merged) else path


def _write_meta(path: str, url: str, info: Dict, **extra):
    meta = {"url": url, "title": info.get("title"), "uploader": info.get("uploader"),
            "handle": _handle(info),
            "extractor": info.get("extractor_key"), **extra}
    with open(path + ".meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)


def download(url: str, dest_dir: str, name: str, sections: Optional[List[List[float]]] = None) -> str:
    """sections: only these [start, end] spans of a long video (joined, in order).
    A file without picture is never returned: sections fall back to the whole
    video, then a plain "best" format is tried."""
    path = _download(url, dest_dir, name, sections)
    if has_picture(path):
        return path
    for p in (path, path + ".meta.json"):
        if os.path.exists(p):
            os.remove(p)
    if sections:
        raise SourceError(f"Le passage téléchargé n'a pas d'image ({url}) : on retélécharge la vidéo entière.")
    path = _download(url, dest_dir, name, None, fmt="b/best")
    if not has_picture(path):
        raise SourceError(f"Vidéo sans image après téléchargement ({url}).")
    return path


def _download(url: str, dest_dir: str, name: str, sections: Optional[List[List[float]]] = None,
              fmt: str = VIDEO_FORMAT) -> str:
    os.makedirs(dest_dir, exist_ok=True)
    if sections and len(sections) > 1:
        return _download_parts(url, dest_dir, name, sections)
    opts = ytdlp_opts(outtmpl=os.path.join(dest_dir, name + ".%(ext)s"), format=fmt, merge_output_format="mp4", noplaylist=True)
    if sections:
        from yt_dlp.utils import download_range_func
        opts.update(download_ranges=download_range_func(None, [tuple(sections[0])]), force_keyframes_at_cuts=True)
    got = _fetch(url, opts)
    if not os.path.exists(got["path"]):
        raise SourceError(f"Téléchargement sans fichier vidéo ({url}).")
    _write_meta(got["path"], url, got["info"])
    return got["path"]


def _download_parts(url: str, dest_dir: str, name: str, sections: List[List[float]]) -> str:
    """Several spans in ONE yt-dlp run (one request to the site, not one per
    span: each request is a chance for YouTube to refuse), then joined — the
    cuts between them become ordinary shot changes."""
    import glob
    from yt_dlp.utils import download_range_func
    pattern = os.path.join(dest_dir, f"{name}_part%(section_start)08.2f.%(ext)s")
    opts = ytdlp_opts(outtmpl=pattern, format=VIDEO_FORMAT, merge_output_format="mp4", noplaylist=True, force_keyframes_at_cuts=True,
                      download_ranges=download_range_func(None, [tuple(sec) for sec in sections]))
    got = _fetch(url, opts)
    parts = sorted(p for p in glob.glob(os.path.join(dest_dir, f"{name}_part*"))
                   if not p.endswith((".json", ".txt", ".part")))
    if not parts:
        raise SourceError(f"Téléchargement des passages sans fichier vidéo ({url}).")
    out = os.path.join(dest_dir, name + ".mp4")
    lst = os.path.join(dest_dir, name + "_parts.txt")
    with open(lst, "w", encoding="utf-8") as f:
        f.writelines(f"file '{os.path.abspath(p)}'\n" for p in parts)
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c:v", "libx264",
                        "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-ar", "44100", out], capture_output=True)
    if r.returncode or not os.path.exists(out):
        raise SourceError(f"Assemblage des passages impossible ({url}).")
    _write_meta(out, url, got["info"], sections=sections)
    for p in parts + [lst]:
        os.remove(p)
    return out


def source_meta(path: str) -> Dict:
    try:
        with open(path + ".meta.json", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def probe(path: str) -> Dict:
    out = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
        "-of", "json", path]))
    s = out["streams"][0]
    return {"w": int(s["width"]), "h": int(s["height"]), "duration": float(out["format"]["duration"])}


def _gray_frames(path: str, w: int, h: int, fps: float, crop: Optional[str] = None,
                 ss: float = 0.0, t: Optional[float] = None) -> np.ndarray:
    vf = (f"crop={crop}," if crop else "") + f"fps={fps},scale={w}:{h}"
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{ss:.3f}"] + (["-t", f"{t:.3f}"] if t else []) + \
          ["-i", path, "-vf", vf, "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(float)


# --------------------------------------------------------------- clean picture

def refine_edges(path: str, info: Dict, times: List[float], top: int, bot: int,
                 margin: int = 40) -> Tuple[int, int]:
    """Gemini puts a band edge within a few % — the exact row is the strongest
    row-to-row jump within +-margin of it, averaged over a few frames."""
    w, h = info["w"], info["h"]
    profiles = []
    for t in times[:4]:
        f = _gray_frames(path, w, h, 1, ss=max(0.0, t), t=1.0)
        if len(f):
            profiles.append(np.abs(np.diff(f[0], axis=0)).mean(1))
    if not profiles:
        return top, bot
    edge = np.mean(profiles, axis=0)

    def best(guess):
        a, b = max(1, guess - margin), min(h - 2, guess + margin)
        return a + int(np.argmax(edge[a:b])) + 1 if b > a else guess
    return best(top) + 4, best(bot) - 4           # a few rows inside: no dark seam


def band_from_area(area: Optional[List[int]], w: int, h: int) -> Optional[Tuple[int, int]]:
    """A Gemini picture-area box (0-1000) -> (top, bottom) rows when it is a
    full-width landscape band inside a taller frame."""
    if not area or len(area) != 4:
        return None
    y0, x0, y1, x1 = area
    top, bot = int(y0 * h / 1000), int(y1 * h / 1000)
    if x1 - x0 < 850 or bot - top > h * 0.85 or bot <= top:
        return None
    return (top, bot) if 1.2 <= w / (bot - top) <= 2.6 else None


# --------------------------------------------------------------- cuts and peaks

def detect_cuts(path: str, info: Dict, crop: Optional[str], min_len: float = 1.2) -> List[Tuple[float, float]]:
    """Clip boundaries from frame-difference peaks (25 fps, small frames)."""
    fps = 25.0
    f = _gray_frames(path, 96, 96, fps, crop)
    if len(f) < 3:
        return [(0.0, info["duration"])]
    d = np.abs(np.diff(f, axis=0)).mean((1, 2))
    med = np.median(d) + 1e-6
    peaks = [i + 1 for i in range(len(d)) if d[i] > 4 * med]
    small = _gray_frames(path, 16, 16, fps, crop)
    cuts = []
    for i in peaks:
        t = i / fps
        if cuts and t - cuts[-1] <= 0.3:                       # a fade gives several peaks in a row
            continue
        if is_cut(small, i):
            cuts.append(t)
    bounds = [0.0] + cuts + [info["duration"]]
    segs = [(round(a + 0.08, 2), round(b - 0.08, 2)) for a, b in zip(bounds, bounds[1:]) if b - a >= min_len]
    return segs or [(0.0, info["duration"])]


def is_cut(small: np.ndarray, i: int) -> bool:
    """A real cut changes the whole picture; a crash only shakes it. Measured
    on 0.2 s before vs 0.3 s after (16x16 frames): cuts differ by 26-57 with a
    correlation <= 0.81, crash jolts by 6-12 with a correlation >= 0.91."""
    a, b = small[max(0, i - 6):max(1, i - 1)], small[i + 2:i + 10]
    if not len(a) or not len(b):
        return True
    a, b = a.mean(0), b.mean(0)
    diff = np.abs(a - b).mean()
    corr = np.corrcoef(a.ravel(), b.ravel())[0, 1] if a.std() > 0 and b.std() > 0 else 0.0
    return diff > 18 or corr < 0.85


def find_peak(path: str, a: float, b: float, crop: Optional[str]) -> Tuple[float, bool]:
    """(time, from_sound): the loudest 50 ms of [a, b]; a clip with no clear
    sound peak gets its biggest picture jolt instead."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", path, "-vn",
                          "-ac", "1", "-ar", "8000", "-f", "s16le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, np.int16).astype(float) / 32768
    if len(x) >= 800:
        n = len(x) // 400 * 400
        db = 20 * np.log10(np.sqrt((x[:n].reshape(-1, 400) ** 2).mean(1)) + 1e-6)
        i = int(np.argmax(db))
        if db[i] - np.median(db) > 6:
            return round(a + i / 20, 2), True
    f = _gray_frames(path, 96, 96, 25, crop, ss=a, t=b - a)
    if len(f) >= 3:
        d = np.abs(np.diff(f, axis=0)).mean((1, 2))
        return round(a + (int(np.argmax(d)) + 1) / 25, 2), False
    return round((a + b) / 2, 2), False


# --------------------------------------------------------------- Gemini

def _gemini():
    from gemini_ai_generator import GeminiAIGenerator
    return GeminiAIGenerator(api_key=os.getenv("GEMINI_API_KEY"))


DESCRIBE_PROMPT = """Voici une video source, deja decoupee en passages (secondes) :
{segments}
Pour CHAQUE passage, dans le meme ordre, decris-le. JSON uniquement :
{{"passages": [{{"camera": "cabine | camera avant | surveillance | telephone | plateau TV | autre",
  "visuel": "description precise : ce qui se passe, vehicules et COULEURS, jour/nuit, personnes",
  "utilisable": true/false, "pourquoi_pas": "si inutilisable : presentateur, interview, logo, ecran de fin, pub, flou...",
  (un "presentateur" PARLE face a la camera ou sur un plateau ; quelqu'un qui FAIT l'action ou une demonstration
   sans parler a la camera n'en est pas un, meme dans une salle de classe ou un tutoriel),
  "parole_dans_le_son": true/false,
  "choc_sonore": true/false (on ENTEND un vrai choc a son moment fort : collision, coup de marteau, explosion, chute,
                 eclaboussure violente ; pas une musique, un effet de montage ou un bruit d'ambiance)}}]}}"""

BOXES_PROMPT = """Voici {n} images (une par clip). Pour CHACUNE :
1. "zone_image" : le rectangle de la VRAIE image filmee, sans le fond flou, les bandes noires ou les cadres
   ajoutes autour (si la video occupe tout l'ecran, donne [0, 0, 1000, 1000]).
2. "boites" : les elements AJOUTES par-dessus qu'il faut effacer : filigranes, logos de chaines/reseaux
   (TikTok, 9News...), noms d'utilisateur (@...), sous-titres ou textes incrustes. PAS les textes naturels
   de la scene (panneaux, plaques) ni les donnees de camera (heure, vitesse, GPS).
JSON uniquement : {{"images": [{{"zone_image": [ymin, xmin, ymax, xmax],
  "boites": [{{"box_2d": [ymin, xmin, ymax, xmax], "quoi": "le TEXTE EXACT lisible (ex. '@azzamyreal', '9NEWS'), sinon une description courte"}}]}}]}}
Coordonnees entre 0 et 1000, sur l'image ENTIERE. "boites" vide si rien a effacer."""


@contextmanager
def gemini_file(path: str):
    """The file sent to Gemini once, for several questions: (gemini, file part)."""
    g = _gemini()
    up = g._upload_video_file(path)
    if not up:
        raise SourceError("Envoi de la source à Gemini impossible.")
    try:
        if not g._wait_for_file_active(up["name"], timeout=180):
            raise SourceError("Gemini n'a pas fini de lire la source à temps.")
        yield g, {"file_data": {"mime_type": up["mime_type"], "file_uri": up["uri"]}}
    finally:
        g._delete_file(up["name"])


RETIME_PROMPT = """Voici une video (les secondes comptent depuis son debut). Pour chaque plan d'un Short, on cherche le
moment ou l'on VOIT l'action decrite, pendant que la phrase est dite. Un moment approximatif est donne : il peut
etre decale de plusieurs secondes, cherche autour d'abord, puis dans toute la video.
{plans}
On cherche l'ACTION qui illustre la phrase : le lieu, les personnes, le decor et le cadrage peuvent etre
differents de la description (un saut jambes tendues dans une salle de classe illustre "atterrir jambes tendues"
meme si la description dit "sur du goudron, en gros plan").
Pour chaque plan : "visible" = true si cette action se voit vraiment ; "debut" et "fin" au dixieme de seconde, du
debut a la fin de l'action elle-meme (pas de la sequence autour) ; "ce_qu_on_voit" en francais.
"visible" = false si l'action n'apparait nulle part dans la video.
JSON uniquement : {{"plans": [{{"plan": numero, "visible": true, "debut": s, "fin": s, "ce_qu_on_voit": "..."}}]}}"""


def retime(path: str, asks: List[Dict], length: float, file=None) -> List[Optional[Dict]]:
    """Where each wanted action really is in a downloaded file — measured on a
    parkour Short: the search's seconds, given watching a 6-minute video at
    about one image a second, missed the pole slide by a few seconds twice.
    asks: [{"image", "phrase", "a", "b"}] (file times). Per ask {"visible",
    "debut", "fin", "vu"}, or None when Gemini can't say (the old moment stays)."""
    if not asks:
        return []
    if file is None:
        with gemini_file(path) as f:
            return retime(path, asks, length, f)
    g, part = file
    listing = "\n".join(f"{n}. action : {x['image']} | phrase : « {x.get('phrase') or ''} » | moment approximatif : "
                        f"{x['a']:.1f}-{x['b']:.1f} s" for n, x in enumerate(asks, 1))
    fps = 4 if length <= 40 else 2                  # finer than the search's look, within a sensible token budget
    try:
        r = g._generate_content([{**part, "video_metadata": {"fps": fps}}, {"text": RETIME_PROMPT.format(plans=listing)}],
                                max_tokens=4000, timeout=180, temperature=0.1)
    except Exception:
        return [None] * len(asks)
    items = r.get("plans") if isinstance(r, dict) else None
    out: List[Optional[Dict]] = [None] * len(asks)
    for e in items if isinstance(items, list) else []:
        try:
            n = int(e.get("plan")) - 1
        except (TypeError, ValueError, AttributeError):
            continue
        if not 0 <= n < len(asks):
            continue
        vu = str(e.get("ce_qu_on_voit") or "").strip()[:200]
        if e.get("visible") is False:
            out[n] = {"visible": False, "vu": vu}
            continue
        try:
            a, b = sorted((float(e["debut"]), float(e["fin"])))
        except (KeyError, TypeError, ValueError):
            continue
        a, b = max(0.0, min(a, length)), max(0.0, min(b, length))
        if b - a >= 0.3:
            out[n] = {"visible": True, "debut": round(a, 2), "fin": round(b, 2), "vu": vu}
    return out


def describe(path: str, segments: List[Tuple[float, float]], file=None) -> List[Dict]:
    if file is None:
        with gemini_file(path) as f:
            return describe(path, segments, f)
    g, part = file
    listing = "\n".join(f"{k + 1}. {a:.2f}-{b:.2f}" for k, (a, b) in enumerate(segments))
    r = g._generate_content([part, {"text": DESCRIBE_PROMPT.format(segments=listing)}],
                            max_tokens=16000, timeout=180, temperature=0.2)
    items = r if isinstance(r, list) else (r.get("passages") if isinstance(r, dict) else None)
    if not isinstance(items, list):
        raise SourceError(f"Description de la source inutilisable : {str(r)[:200]}")
    return (items + [{}] * len(segments))[:len(segments)]


def find_boxes(stills: List[str]) -> List[Tuple[Optional[List[int]], List[List[int]], List[str]]]:
    """Per still: (picture area, boxes to erase, what they are), coordinates
    0-1000 on the full frame. Best effort: on failure, the whole frame and
    nothing to erase. What they are ("logo TikTok @azzamyreal") feeds the
    credits: the real source is often the watermark, not the re-uploader."""
    import base64
    if not stills:
        return []
    parts = [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(open(p, "rb").read()).decode()}}
             for p in stills]
    imgs = []
    for _attempt in range(2):          # a long answer (many stills) was once cut off mid-JSON
        try:
            r = _gemini()._generate_content(parts + [{"text": BOXES_PROMPT.format(n=len(stills))}],
                                            max_tokens=24000, timeout=180, temperature=0.1)
        except Exception:
            continue
        imgs = r if isinstance(r, list) else (r.get("images") or [])
        if imgs:
            break
    if not imgs:
        return [(None, [], []) for _ in stills]
    out = []
    for k in range(len(stills)):
        item = imgs[k] if k < len(imgs) and isinstance(imgs[k], dict) else {}
        area = item.get("zone_image") if isinstance(item.get("zone_image"), list) else None
        kept = [b for b in item.get("boites") or [] if isinstance(b, dict) and len(b.get("box_2d") or []) == 4]
        out.append((area, [b["box_2d"] for b in kept], [str(b.get("quoi") or "") for b in kept]))
    return out


def edges_and_patches(boxes: List[List[int]], w: int, h: int) -> Tuple[int, int, List[Tuple[int, int, int, int]]]:
    """Boxes (0-1000) -> rows to cut at the top/bottom, and boxes to paint over.
    A thin strip touching the top or bottom 12 % is cropped (cleaner than any
    painting); a box covering more than a quarter of the frame is ignored
    (painting it would ruin the clip)."""
    cut_top, cut_bot, patches = 0, 0, []
    for y0, x0, y1, x1 in boxes:
        y0, y1, x0, x1 = y0 * h / 1000, y1 * h / 1000, x0 * w / 1000, x1 * w / 1000
        bw, bh = x1 - x0, y1 - y0
        if bw <= 2 or bh <= 2 or bw * bh > 0.25 * w * h:
            continue
        if y1 >= h * 0.88 and bh <= h * 0.15:
            cut_bot = max(cut_bot, int(h - y0) + 4)
        elif y0 <= h * 0.12 and bh <= h * 0.15:
            cut_top = max(cut_top, int(y1) + 4)
        else:
            m = 6
            patches.append((int(x0) - m, int(y0) - m, int(bw) + 2 * m, int(bh) + 2 * m))
    return cut_top, cut_bot, patches


# --------------------------------------------------------------- the catalogue

def _ids():
    letters = string.ascii_uppercase
    for k in range(10_000):
        yield letters[k % 26] * (k // 26 + 1)


def delogo_filters(boxes, w: int, h: int) -> List[str]:
    """ffmpeg delogo refuses a box touching or crossing the frame edge: clamp it inside."""
    out = []
    for x, y, bw, bh in boxes or []:
        x, y = max(1, int(x)), max(1, int(y))
        bw, bh = min(int(bw), w - x - 2), min(int(bh), h - y - 2)
        if bw > 4 and bh > 4:
            out.append(f"delogo=x={x}:y={y}:w={bw}:h={bh}")
    return out


def still(path: str, t: float, crop: Optional[str], out: str, delogo=None, size=None) -> str:
    """size: (w, h) of the frame after the crop — needed to clamp the delogo boxes."""
    marks = delogo_filters(delogo, *size) if (delogo and size) else []
    vf = ",".join(([f"crop={crop}"] if crop else []) + marks + ["scale=640:-2"])
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1", "-vf", vf, out],
                   check=False)
    return out


def clip_still(c: Dict, out: str) -> str:
    """A thumbnail as the render will show it (cropped, marks erased), at the
    crash — or mid-clip when that frame is dark (replays open on a fade)."""
    from PIL import Image, ImageStat
    for t in (c["impact"], (c["start"] + c["end"]) / 2):
        if os.path.exists(out):
            os.remove(out)
        still(c["src"], t, c.get("crop"), out, c.get("delogo"), (c["w"], c["h"]))
        if not os.path.exists(out):                       # never fail a thumbnail over the clean-up
            still(c["src"], t, c.get("crop"), out)
        try:
            if ImageStat.Stat(Image.open(out).convert("L")).mean[0] > 18:
                break
        except OSError:
            break
    return out


def clip_preview(c: Dict, out: str) -> str:
    """A small video of the clip as the render will show it (cropped, marks
    erased), with its own sound — to watch it before choosing."""
    marks = delogo_filters(c.get("delogo"), c["w"], c["h"]) if c.get("delogo") else []
    vf = ",".join(([f"crop={c['crop']}"] if c.get("crop") else []) + marks + ["scale=480:-2"])
    dur = max(0.3, c["end"] - c["start"])
    base = ["ffmpeg", "-v", "error", "-y", "-ss", f"{c['start']:.3f}", "-t", f"{dur:.3f}", "-i", c["src"]]
    tail = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-c:a", "aac", "-b:a", "96k",
            "-movflags", "+faststart", out]
    if subprocess.run(base + ["-vf", vf] + tail).returncode or not os.path.exists(out):
        subprocess.run(base + ["-vf", "scale=480:-2"] + tail)       # never fail a preview over the clean-up
    return out


def _to_band_coords(boxes: List[List[int]], h_full: int, top: int, height: int) -> List[List[int]]:
    """Boxes given on the full frame (0-1000) -> 0-1000 relative to the band."""
    out = []
    for y0, x0, y1, x1 in boxes:
        a, b = (y0 * h_full / 1000 - top) / height * 1000, (y1 * h_full / 1000 - top) / height * 1000
        if b > 0 and a < 1000:                 # only what overlaps the band
            out.append([max(0, int(a)), x0, min(1000, int(b)), x1])
    return out


def black_bars(path: str, a: float, b: float) -> Optional[Tuple[int, int, int, int]]:
    """(w, h, x, y) of the picture inside black bars over [a, b] — a vertical
    video posted inside a horizontal file showed as a thin strip (measured:
    608x1072 inside 1920x1080). None when there are no real bars."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-ss", f"{max(0.0, a):.2f}", "-i", path, "-t", f"{max(0.5, b - a):.2f}",
                        "-vf", "cropdetect=limit=24:round=2:reset=0", "-f", "null", "-"],
                       capture_output=True, text=True)
    found = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", r.stderr)
    if not found:
        return None
    w, h, x, y = (int(v) for v in found[-1])
    info = probe(path)
    if w < 64 or h < 64 or w * h > 0.85 * info["w"] * info["h"]:
        return None
    return w, h, x, y


ORIENT_PROMPT = """Regarde cette video. Est-elle a l'endroit ? Si elle a ete filmee ou publiee couchee sur le cote ou a
l'envers (le ciel sur un cote, le sol de l'autre, les gens penches a 90 degres), dis de combien de degres il faut la
tourner DANS LE SENS DES AIGUILLES D'UNE MONTRE pour la remettre droite.
JSON uniquement : {{"rotation": 0 | 90 | 180 | 270}}"""


def orientation(file) -> int:
    """Clockwise degrees that put a sideways video upright (a hook was once shown lying on its side)."""
    g, part = file
    try:
        r = g._generate_content([{**part, "video_metadata": {"fps": 0.5}}, {"text": ORIENT_PROMPT.format()}],
                                max_tokens=2000, timeout=120, temperature=0.0)
        deg = int((r or {}).get("rotation") or 0) if isinstance(r, dict) else 0
    except Exception:
        return 0
    return deg if deg in (90, 180, 270) else 0


def rotated(path: str, deg: int) -> str:
    """The file turned upright (re-encoded once; every later step sees it straight)."""
    vf = {90: "transpose=1", 270: "transpose=2", 180: "hflip,vflip"}[deg]
    out = os.path.splitext(path)[0] + f"_r{deg}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "18", "-c:a", "copy", out], check=True)
    return out


def clip_at(path: str, index: int, cid: str, a: float, b: float, found, desc: str = "") -> Dict:
    """"Script d'abord": one clip from a chosen moment [a, b] (already
    picked and checked), cleaned like the analysed ones — the real picture
    area, an added strip at an edge cropped, other added marks painted over.
    found: (area, boxes, marks) from find_boxes on a still of the moment."""
    info = probe(path)
    w_full, h_full = info["w"], info["h"]
    a, b = max(0.0, a), min(b, info["duration"] - 0.05)
    area, bx, marks = found
    own = band_from_area(area, w_full, h_full)
    on_band = bool(own)
    if own:
        own = refine_edges(path, info, [(a + b) / 2], *own)
    top, height = (own[0], own[1] - own[0]) if on_band else (0, h_full)
    boxes = _to_band_coords(bx, h_full, top, height) if on_band else bx
    cut_top, cut_bot, patches = edges_and_patches(boxes, w_full, height)
    h = height - cut_top - cut_bot
    if h < height * 0.6:
        cut_top = cut_bot = 0
        h = height
    crop = f"{w_full}:{h}:0:{top + cut_top}" if (on_band or cut_top or cut_bot) else None
    patches = [(x, y - cut_top, pw, ph) for x, y, pw, ph in patches if y - cut_top >= 0]
    w = w_full
    if not crop:                                # black bars Gemini's picture area missed
        bars = black_bars(path, a, b)
        if bars:
            w, h, bx0, by0 = bars
            crop = f"{w}:{h}:{bx0}:{by0}"
            patches = [(x - bx0, y - by0, pw, ph) for x, y, pw, ph in patches
                       if bx0 <= x < bx0 + w and by0 <= y < by0 + h]
    peak, from_sound = find_peak(path, a, b, crop)
    return {"id": cid, "source": index, "src": path, "start": a, "end": b, "impact": peak,
            "w": w - w % 2, "h": h - h % 2, "crop": crop, "delogo": patches, "desc": desc,
            "camera": "", "usable": True, "why_not": "", "audio_ok": False, "shock": False,
            "low_res": min(w, h) < 540, "marks": [m for m in marks if m]}


def analyse_source(path: str, index: int, work_dir: str, id_gen=None, use_gemini: bool = True) -> List[Dict]:
    """Every clip of one source video, ready for the script and the render."""
    info = probe(path)
    w_full, h_full = info["w"], info["h"]
    os.makedirs(work_dir, exist_ok=True)

    # 1. the clean picture area, if the video is a band on a blurred copy of itself
    band = None
    if use_gemini and h_full >= w_full * 1.3:
        times = [info["duration"] * k / 9 for k in range(1, 9)]
        found = [band_from_area(a, w_full, h_full) for a, _, _ in
                 find_boxes([still(path, t, None, os.path.join(work_dir, f"b{index}_{k}.jpg"))
                             for k, t in enumerate(times)])]
        found = [(b, t) for b, t in zip(found, times) if b]
        if len(found) >= 3:
            top = int(np.median([b[0] for b, _ in found]))
            bot = int(np.median([b[1] for b, _ in found]))
            band = refine_edges(path, info, [t for _, t in found], top, bot)
    base_crop = f"{w_full}:{band[1] - band[0]}:0:{band[0]}" if band else None

    # 2. clips, and what each one shows
    segments = detect_cuts(path, info, base_crop)
    descriptions = describe(path, segments) if use_gemini else [{} for _ in segments]
    stills = [still(path, (a + b) / 2, None, os.path.join(work_dir, f"s{index}_{k}.jpg"))
              for k, (a, b) in enumerate(segments)]
    found = find_boxes(stills) if use_gemini else [(None, [], []) for _ in segments]

    ids = id_gen or _ids()
    clips = []
    for (a, b), d, (area, bx, marks) in zip(segments, descriptions, found):
        own = band_from_area(area, w_full, h_full)
        on_band = bool(own)
        if own and band and abs(own[0] - band[0]) <= 60 and abs(own[1] - band[1]) <= 60:
            own = band                          # the video's usual band, already measured
        elif own:
            own = refine_edges(path, info, [(a + b) / 2], *own)
        top, height = (own[0], own[1] - own[0]) if on_band else (0, h_full)
        boxes = _to_band_coords(bx, h_full, top, height) if on_band else bx
        cut_top, cut_bot, patches = edges_and_patches(boxes, w_full, height)
        h = height - cut_top - cut_bot
        if h < height * 0.6:                    # cropping would eat the picture: paint instead
            cut_top = cut_bot = 0
            h = height
        crop = f"{w_full}:{h}:0:{top + cut_top}" if (on_band or cut_top or cut_bot) else None
        patches = [(x, y - cut_top, pw, ph) for x, y, pw, ph in patches if y - cut_top >= 0]
        peak, from_sound = find_peak(path, a, b, crop)
        clips.append({
            "id": next(ids), "source": index, "src": path, "start": a, "end": b, "impact": peak,
            "w": w_full - w_full % 2, "h": h - h % 2, "crop": crop, "delogo": patches,
            "desc": d.get("visuel") or "", "camera": d.get("camera") or "",
            # 1 s is enough for a short sentence (the script check keeps longer ones off it); fast TikTok
            # edits are made of 1.0-1.4 s shots, and merging them would mix unrelated scenes (measured)
            "usable": bool(d.get("utilisable", True)) and b - a >= MIN_CLIP,
            "why_not": d.get("pourquoi_pas") or ("trop court" if b - a < MIN_CLIP else ""),
            "audio_ok": from_sound and not d.get("parole_dans_le_son", False),
            **({"shock": bool(d.get("choc_sonore"))} if use_gemini else {}),
            "low_res": min(w_full, h) < 540,
            "marks": [m for m in marks if m],
        })
    return clips
