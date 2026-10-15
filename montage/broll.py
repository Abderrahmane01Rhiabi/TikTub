"""
Shared library of drone / nature shots for the montage, fetched from Pixabay
(free to use, commercial included) and kept under assets/broll/.

    index.json   one entry per clip (id, file, theme, size, Pixabay page)

Usage lives in the database (table broll_usage, so it is in the backups):
picking skips the shots a channel used in its last ~10 rendered videos AND
the ones other videos of the channel have reserved (planned, not rendered
yet), so a channel doesn't post the same waves over and over — a viewer
notices, and YouTube may read it as repetitive content.
"""

import json
import os
import random
import threading
from typing import Dict, List, Optional

import requests

import db

BROLL_DIR = "assets/broll"
MIN_WIDTH = 1920           # 960x540 clips look soft once cropped and blown up to the 9:16 box
RECENT_PER_CHANNEL = 20    # different shots remembered per channel = its last 10 videos (2 shots each)
HEALTHY_LIBRARY = 30       # below this, a channel's shots come back sooner than every 10 videos
WAITING_STATUSES = {"montage_planning", "montage_review"}
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


def reserved(channel: str, except_video: Optional[str] = None) -> List[str]:
    """Shots already chosen by the channel's videos that are planned but not
    rendered yet (waiting for review, or validated and waiting for Traiter):
    a batch of several videos must not all land on the same waves."""
    out = []
    for v in db.query_videos(channel=channel):
        m = v.get("montage") or {}
        waiting = v.get("status") in WAITING_STATUSES or (v.get("status") == "selected" and m.get("validated"))
        if waiting and v.get("video_id") != except_video:
            out += [str(i) for i in m.get("brolls") or []]
    return out


def pick(channel: str, n: int = 2, seed=None, exclude=(), video_id: Optional[str] = None) -> List[Dict]:
    """n different clips, skipping what the channel used recently, what its
    other waiting videos reserved, and `exclude` (e.g. the shot being
    swapped out). When the library is too small, falls back to the shots
    this channel used longest ago (never-used ones first)."""
    _migrate_usage_json()
    clips = list_clips()
    if not clips:
        return []
    rng = random.Random(seed)
    excluded = {str(e) for e in exclude}
    busy = set(db.recent_broll_clips(channel, RECENT_PER_CHANNEL)) | set(reserved(channel, except_video=video_id))
    fresh = [c for c in clips if str(c["id"]) not in busy and str(c["id"]) not in excluded]
    rng.shuffle(fresh)
    chosen = fresh[:n]
    if len(chosen) < n:
        last = db.broll_last_used(channel)
        rest = [c for c in clips if c not in chosen and str(c["id"]) not in excluded]
        rest.sort(key=lambda c: last.get(str(c["id"]), ""))
        chosen += rest[: n - len(chosen)]
    return chosen


def record_usage(channel: str, clip_ids: List, video_id: Optional[str] = None) -> None:
    db.record_broll_usage(channel, clip_ids, video_id)


def usage_counts() -> Dict[str, Dict]:
    _migrate_usage_json()
    return db.broll_usage_counts()


def _migrate_usage_json() -> None:
    """The first version kept usage in assets/broll/usage.json: moved into
    the database once, then the file is renamed out of the way."""
    path = os.path.join(BROLL_DIR, "usage.json")
    if not os.path.exists(path):
        return
    with _lock:
        if not os.path.exists(path):
            return
        try:
            for channel, ids in _read("usage.json", {}).items():
                db.record_broll_usage(channel, ids, used_at="2000-01-01T00:00:00")
        finally:
            os.replace(path, path + ".migrated")
