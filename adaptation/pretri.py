"""
The free pre-sort « image + parole » of the montage pro search (labs of 2026-11-13: labo_soustitres, Whisper on the
58 videos of the Al Boraq project; the user's blind vote: the 4 criteria fixed before passed).

Gemini watches only 14 of the ~60 videos a search finds (the most promising by their title), and the good moments
were in the others: the free model (adaptation/vision, CLIP) found 9 good moments of 12 there from the YouTube
storyboards alone, and what is SAID in a video tells which place it shows — CLIP sees « a stadium », the narrator
says « Hassan II à Benslimane ». So, before the paid checks:

  planches   every YouTube candidate's storyboard (~1 picture a 2 s, free, no download), scored by CLIP against each
             visual's English idea (the director's)
  noms       one small text call: the proper nouns one would HEAR in a video showing each visual, with their spellings
             (latin, arabic) — [] for a generic visual
  parole     only for the visuals with a proper noun, the TOP_SPEECH videos best scored by CLIP (12/12 good moments
             kept by that rule, 7/12 by the search's own score): their audio alone, transcribed by Whisper on this PC
  ordre      for each visual: the video where its name is SAID while the picture fits (identity), then the video whose
             picture fits best (CLIP) -> verify_best has Gemini watch them first

Nothing is paid here. A video that fails (no storyboard, refused download) is only left out.
"""

import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from typing import Callable, Dict, List, Optional

import numpy as np

TOP_SPEECH = 20             # the user, 2026-11-13: Whisper on the 20 videos best scored by CLIP, not all of them
MAX_FRAMES = 150            # storyboard pictures kept a video (spread evenly)
WIN = 5.0                   # a name said at t: the storyboard pictures within ±WIN s (they are ~2-5 s apart)
SPEECH_MIN_S = 20           # less said than that: a music-only video
Report = Callable[[str, float], None]

NOMS_PROMPT = """Pour un YouTube Short, on cherche des videos qui montrent chacune de ces images :
{images}

Pour CHAQUE image : les NOMS PROPRES qui designent CE QU'ON VOIT dans cette image (le lieu precis, le batiment, le
projet, la personne, l'evenement), ceux qu'on entendrait dire au moment ou la video le montre, avec leurs ecritures
(anglais, francais, arabe, variantes courantes : « boraq », « buraq », « البراق »), en minuscules, 8 au plus.
JAMAIS le pays, une grande ville ou un organisme cite partout dans le sujet (« maroc », « casablanca », « oncf ») s'ils
ne sont pas EUX-MEMES ce que montre l'image ; pas de mots communs (« stade », « train ») ; [] pour une image generique.
JSON uniquement : {{"images": [{{"n": 1, "noms": ["", ""]}}]}}"""


# ---------------------------------------------------------------- words heard

AR_DIAC = re.compile("[ً-ْـٰ]")


def norm(s: str) -> str:
    s = AR_DIAC.sub("", str(s or "").lower())
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه").replace("ى", "ي")
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c) or "؀" <= c <= "ۿ")
    return re.sub(r"\s+", " ", s)


def _arabic(t: str) -> bool:
    return any("؀" <= c <= "ۿ" for c in t)


def heard(cues: List[Dict], terms: List[str]) -> List[float]:
    """The instants a term is said: Latin at a word's start, Arabic anywhere (و ب ل ال stick to the word)."""
    pats = []
    for term in terms:
        t = norm(term).strip()
        if len(t) >= 3:
            pats.append(re.compile(re.escape(t) if _arabic(t) else r"(?<![a-z0-9])" + re.escape(t)))
    out = []
    for c in cues:
        text = norm(c.get("text"))
        for pat in pats:
            for m in pat.finditer(text):
                t, acc = c["t"], 0
                for wt, word in c.get("words") or []:        # the word's own instant
                    if acc + len(norm(word)) + 1 > m.start():
                        t = wt
                        break
                    acc += len(norm(word)) + 1
                out.append(round(float(t), 2))
    return sorted(set(out))


# ---------------------------------------------------------------- storyboards

def _vid(url: str) -> Optional[str]:
    from adaptation import finder
    return finder._video_id(url)


def storyboard(url: str, folder: str) -> List[List]:
    """[[t, path]] — the YouTube storyboard's pictures (cached in folder/<id>/index.json); [] when there is none."""
    import io
    import requests
    import yt_dlp
    from PIL import Image
    from adaptation.sources import ytdlp_opts
    vid = _vid(url)
    if not vid:
        return []
    d = os.path.join(folder, vid)
    idx = os.path.join(d, "index.json")
    if os.path.exists(idx):
        return [[t, os.path.join(d, n)] for t, n in json.load(open(idx))["frames"]]
    with yt_dlp.YoutubeDL(ytdlp_opts(skip_download=True)) as y:
        info = y.extract_info(url, download=False)
    sbs = [f for f in info.get("formats") or [] if str(f.get("format_id", "")).startswith("sb") and f.get("fragments")]
    if not sbs:
        return []
    sb = max(sbs, key=lambda f: f.get("width") or 0)
    dur = info.get("duration") or 0
    fps, rows, cols, w, h = sb["fps"], sb["rows"], sb["columns"], sb["width"], sb["height"]
    frames, i = [], 0
    for frag in sb["fragments"]:
        r = requests.get(frag["url"], timeout=30)
        if r.status_code != 200:
            i += rows * cols
            continue
        sheet = Image.open(io.BytesIO(r.content)).convert("RGB")
        for rr in range(rows):
            for cc in range(cols):
                t, i = i / fps, i + 1
                box = (cc * w, rr * h, cc * w + w, rr * h + h)
                if (dur and t > dur) or box[2] > sheet.width or box[3] > sheet.height:
                    continue
                frames.append((round(t, 2), sheet.crop(box)))
    if len(frames) > MAX_FRAMES:
        step = len(frames) / MAX_FRAMES
        frames = [frames[int(k * step)] for k in range(MAX_FRAMES)]
    os.makedirs(d, exist_ok=True)
    out = []
    for t, im in frames:
        name = f"{t:08.2f}.jpg"
        im.save(os.path.join(d, name), quality=88)
        out.append([t, name])
    json.dump({"duration": dur, "frames": out}, open(idx, "w"))
    return [[t, os.path.join(d, n)] for t, n in out]


def clip_scores(urls: List[str], ideas: List[str], folder: str, report: Report) -> Dict[str, Dict]:
    """{url: {"ts": [t], "s": [[score of each idea] for each picture]}} — CLIP, picture against the visual's idea."""
    from concurrent.futures import ThreadPoolExecutor
    from adaptation import vision
    got: Dict[str, List] = {}

    def one(u):
        try:
            return u, storyboard(u, folder)
        except Exception:
            return u, []
    with ThreadPoolExecutor(4) as pool:
        for k, (u, fr) in enumerate(pool.map(one, urls)):
            report(f"pré-tri : images des vidéos {k + 1}/{len(urls)}", 0.4 * (k + 1) / max(1, len(urls)))
            if fr:
                got[u] = fr
    T = vision.embed_texts(ideas)
    out = {}
    for k, (u, fr) in enumerate(got.items()):
        cache = os.path.join(folder, _vid(u), "clip.json")
        try:
            emb = json.load(open(cache)) if os.path.exists(cache) else None
        except (OSError, ValueError):
            emb = None
        try:
            if emb is None or len(emb) != len(fr):
                emb = [list(map(float, x)) for x in vision.embed_images([p for _, p in fr])]
                try:
                    json.dump(emb, open(cache, "w"))
                except OSError:
                    pass
            out[u] = {"ts": [t for t, _ in fr], "s": (np.array(emb) @ np.array(T).T).tolist()}
        except OSError:              # a picture the Windows disk would not read (Errno 5, 13/11): this video left out
            continue
        report("pré-tri : le modèle gratuit regarde les images", 0.4 + 0.1 * (k + 1) / max(1, len(got)))
    return out


# ---------------------------------------------------------------- names and speech

def noms(visuals: List[str], gemini=None) -> Dict[int, List[str]]:
    """{visual index: [names and spellings]} — one small text call; {} when it fails."""
    from adaptation.script import _gemini
    try:
        r = (gemini or _gemini())._generate_content([{"text": NOMS_PROMPT.format(
            images="\n".join(f"{k}. {x}" for k, x in enumerate(visuals, 1)))}], max_tokens=8000, timeout=90,
            temperature=0.1)
    except Exception:
        return {}
    out = {}
    for x in (r or {}).get("images") or []:
        try:
            k = int(x.get("n")) - 1
        except (TypeError, ValueError, AttributeError):
            continue
        names = [str(n).strip().lower() for n in x.get("noms") or [] if len(str(n).strip()) >= 3]
        if 0 <= k < len(visuals) and names:
            out[k] = names[:8]
    return out


def _nvidia_libs() -> str:
    """The CUDA libraries pip installed with torch (faster-whisper needs them on the library path)."""
    import glob
    base = os.path.dirname(os.path.dirname(os.path.abspath(sys.executable)))
    libs = glob.glob(os.path.join(base, "lib", "python3*", "site-packages", "nvidia", "*", "lib"))
    return ":".join(libs + [os.environ.get("LD_LIBRARY_PATH", "")])


def speech(urls: List[str], folder: str, report: Report, timeout: int = 3600) -> Dict[str, List[Dict]]:
    """{url: cues [{t, d, text, words: [[t, w]]}]} — Whisper in its own process (adaptation/parole_worker), one video
    at a time; a video already transcribed is read from its file."""
    os.makedirs(folder, exist_ok=True)
    todo = [u for u in urls if _vid(u) and not os.path.exists(os.path.join(folder, _vid(u) + ".json"))]
    if todo:
        jobs = os.path.join(folder, "a_faire.json")
        json.dump([{"url": u, "vid": _vid(u)} for u in todo], open(jobs, "w"))
        env = {**os.environ, "LD_LIBRARY_PATH": _nvidia_libs()}
        worker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parole_worker.py")   # this code's own
        proc = subprocess.Popen([sys.executable, worker, jobs, folder], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        start, n = time.time(), 0
        for line in proc.stdout:
            if line.startswith("FAIT "):
                n += 1
                report(f"pré-tri : écoute des vidéos (Whisper) {n}/{len(todo)}", 0.5 + 0.45 * n / len(todo))
            if time.time() - start > timeout:
                proc.kill()
                break
        proc.wait()
    out = {}
    for u in urls:
        f = os.path.join(folder, (_vid(u) or "") + ".json")
        try:
            rec = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (rec.get("parole_s") or 0) >= SPEECH_MIN_S:
            out[u] = rec.get("cues") or []
    return out


# ---------------------------------------------------------------- the order

def order(clips: Dict[str, Dict], names: Dict[int, List[str]], said: Dict[str, List[Dict]], n_visuals: int) -> Dict:
    """For each visual: the video where its name is said while the picture fits best (identity), and the video whose
    picture fits best (CLIP). -> {"premiers": [urls], "visuels": [{k, identite, image}]}."""
    rows, first = [], []
    for k in range(n_visuals):
        best_clip = max(((u, max(range(len(c["ts"])), key=lambda i: c["s"][i][k])) for u, c in clips.items()),
                        key=lambda x: clips[x[0]]["s"][x[1]][k], default=None)
        ident = None
        for u, cues in said.items():
            if k not in names or u not in clips:
                continue
            c = clips[u]
            for t in heard(cues, names[k]):
                near = [i for i, ft in enumerate(c["ts"]) if abs(ft - t) <= WIN]
                if not near:
                    continue
                i = max(near, key=lambda i: c["s"][i][k])
                if not ident or c["s"][i][k] > ident["clip"]:
                    ident = {"url": u, "t": c["ts"][i], "clip": round(c["s"][i][k], 3), "dit_a": t}
        img = None
        if best_clip:
            u, i = best_clip
            img = {"url": u, "t": clips[u]["ts"][i], "clip": round(clips[u]["s"][i][k], 3)}
        rows.append({"k": k, "identite": ident, "image": img})
    for key in ("identite", "image"):
        for r in rows:
            if r[key] and r[key]["url"] not in first:
                first.append(r[key]["url"])
    return {"premiers": first, "visuels": rows}


def run(sug: Dict, ideas: List[str], visuals: List[str], folder: str, report: Optional[Report] = None,
        gemini=None) -> Dict:
    """The whole pre-sort: kept in sug["pretri"] and returned. ideas/visuals: one per scene of sug["scenes"]."""
    from adaptation import finder
    report = report or (lambda ph, f: None)
    t0 = time.time()
    urls = [c["url"] for c in finder.all_candidates(sug) if _vid(c["url"])
            and (c.get("duration") or 0) <= finder.MAX_DURATION]
    clips = clip_scores(urls, ideas, os.path.join(folder, "planches"), report)
    names = noms(visuals, gemini)
    best = lambda u: max(max(row) for row in clips[u]["s"]) if clips[u]["s"] else 0.0
    top = sorted(clips, key=best, reverse=True)[:TOP_SPEECH] if names else []
    said = speech(top, os.path.join(folder, "parole"), report) if top else {}
    out = order(clips, names, said, len(ideas))
    out.update(noms=names, ecoutees=len(top), parlees=len(said), images=len(clips), videos=len(urls),
               duree_s=round(time.time() - t0))
    sug["pretri"] = out
    report("pré-tri terminé", 1.0)
    return out
