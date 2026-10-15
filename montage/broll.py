"""
Shared library of drone / nature shots for the montage, fetched from Pixabay
(free to use, commercial included) and kept under assets/broll/.

    index.json   one entry per clip (id, file, theme, size, Pixabay page)
    usage.json   per channel, the clips its last videos used — picking skips
                 them, so a channel doesn't post the same waves ten times
                 (YouTube reads that as repetitive content)
"""

import json
import os
import random
import threading
from typing import Dict, List, Optional

import requests

BROLL_DIR = "assets/broll"
MIN_WIDTH = 1920           # 960x540 clips look soft once cropped and blown up to the 9:16 box
RECENT_PER_CHANNEL = 8     # clips remembered per channel
DEFAULT_THEMES = ["aerial forest river", "drone mountain cliff", "aerial snowy forest",
                  "drone coastline waves", "aerial winding road hills", "drone lake",
                  "aerial waterfall", "drone canyon"]

_lock = threading.Lock()


def _read(name: str, default):
    path = os.path.join(BROLL_DIR, name)
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write(name: str, data):
    os.makedirs(BROLL_DIR, exist_ok=True)
    tmp = os.path.join(BROLL_DIR, name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, os.path.join(BROLL_DIR, name))


def list_clips(usable_only: bool = True) -> List[Dict]:
    clips = [c for c in _read("index.json", []) if os.path.exists(clip_path(c))]
    return [c for c in clips if c.get("w", 0) >= MIN_WIDTH] if usable_only else clips


def get_clip(clip_id) -> Optional[Dict]:
    return next((c for c in list_clips(usable_only=False) if str(c["id"]) == str(clip_id)), None)


def clip_path(clip: Dict) -> str:
    return os.path.join(BROLL_DIR, os.path.basename(clip["file"]))


def thumbnail_path(clip: Dict) -> str:
    return os.path.join(BROLL_DIR, f"{clip['id']}.jpg")


def fetch(theme: str, count: int = 3, api_key: Optional[str] = None) -> List[Dict]:
    """Downloads up to `count` new Full-HD clips for `theme` from Pixabay.
    Returns the clips added (already-known ones are skipped)."""
    key = api_key or os.getenv("PIXABAY_API_KEY")
    if not key:
        raise RuntimeError("PIXABAY_API_KEY manquante dans .env")
    r = requests.get("https://pixabay.com/api/videos/",
                     params={"key": key, "q": theme, "per_page": 20, "safesearch": "true"}, timeout=30)
    r.raise_for_status()
    with _lock:
        known = {str(c["id"]) for c in _read("index.json", [])}
    added = []
    for hit in r.json().get("hits", []):
        if len(added) >= count:
            break
        if str(hit["id"]) in known:
            continue
        # smallest rendition that is still Full HD (4K files are 100+ MB for nothing)
        v = next((hit["videos"][k] for k in ("small", "medium", "large")
                  if hit["videos"].get(k, {}).get("url") and hit["videos"][k].get("width", 0) >= MIN_WIDTH), None)
        if not v:
            continue
        os.makedirs(BROLL_DIR, exist_ok=True)
        clip = {"id": hit["id"], "file": f"{hit['id']}.mp4", "query": theme, "tags": hit.get("tags", ""),
                "duration": hit.get("duration"), "w": v["width"], "h": v["height"], "page": hit.get("pageURL")}
        with requests.get(v["url"], timeout=300, stream=True) as dl:
            dl.raise_for_status()
            with open(clip_path(clip) + ".part", "wb") as f:
                for chunk in dl.iter_content(1 << 20):
                    f.write(chunk)
        os.replace(clip_path(clip) + ".part", clip_path(clip))
        make_thumbnail(clip)
        with _lock:
            index = _read("index.json", [])
            index.append(clip)
            _write("index.json", index)
        added.append(clip)
    return added


def make_thumbnail(clip: Dict) -> str:
    import subprocess
    out = thumbnail_path(clip)
    if not os.path.exists(out):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "2", "-i", clip_path(clip), "-frames:v", "1",
                        "-vf", "scale=-2:360,crop=202:360", out], check=False)
    return out


def delete(clip_id) -> bool:
    with _lock:
        index = _read("index.json", [])
        clip = next((c for c in index if str(c["id"]) == str(clip_id)), None)
        if not clip:
            return False
        for path in (clip_path(clip), thumbnail_path(clip)):
            if os.path.exists(path):
                os.remove(path)
        _write("index.json", [c for c in index if c is not clip])
    return True


def pick(channel: str, n: int = 2, seed=None, exclude=()) -> List[Dict]:
    """n different clips, avoiding the ones this channel used recently and
    `exclude` (e.g. the shot being swapped out). Falls back to recently used
    ones only when the library is too small."""
    clips = list_clips()
    if not clips:
        return []
    rng = random.Random(seed)
    recent = [str(i) for i in _read("usage.json", {}).get(channel, [])]
    excluded = {str(e) for e in exclude}
    fresh = [c for c in clips if str(c["id"]) not in recent and str(c["id"]) not in excluded]
    rng.shuffle(fresh)
    chosen = fresh[:n]
    if len(chosen) < n:
        # oldest-used first, so the most recent ones are reused last
        rest = [c for c in clips if c not in chosen and str(c["id"]) not in excluded]
        rest.sort(key=lambda c: recent.index(str(c["id"])) if str(c["id"]) in recent else -1)
        chosen += rest[: n - len(chosen)]
    return chosen


def record_usage(channel: str, clip_ids: List) -> None:
    with _lock:
        usage = _read("usage.json", {})
        seen = [str(i) for i in usage.get(channel, []) if str(i) not in {str(c) for c in clip_ids}]
        usage[channel] = (seen + [str(c) for c in clip_ids])[-RECENT_PER_CHANNEL:]
        _write("usage.json", usage)
