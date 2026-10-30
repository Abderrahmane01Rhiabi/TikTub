"""
One long video, many Roblox projects (2026-10-30): what was done on a YouTube video is done once.

    the record   in the database (roblox_videos), for good: the link, the video's facts, each passage used (its
                 seconds, its rank among the most replayed, its moments, what the creator added in it), the
                 moments already published, the projects made — light, it is never removed
    the files    in temp/roblox/videos/<id>/, shared by the projects: the passages, the voices apart from the
                 game, the cleaned versions — heavy (500 MB to 1 GB a video), removed 30 days after their last
                 use; a project that needs one again downloads (or remakes) it, the same seconds
"""

import hashlib
import os
import re
import shutil
import time
from typing import Dict, List, Optional

import db

ROOT = os.path.join("temp", "roblox", "videos")
KEEP_DAYS = 30
_ID = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})")


def video_key(url: str) -> str:
    """The YouTube id of the video, whatever the link; another site: a short hash of the link."""
    m = _ID.search(url or "")
    return m.group(1) if m else hashlib.sha1((url or "").strip().encode()).hexdigest()[:12]


def load(url: str) -> Dict:
    key = video_key(url)
    return db.get_roblox_video(key) or {"video_id": key, "url": url, "meta": None, "passages": {}, "publies": [],
                                        "projets": [], "utilise_le": time.time()}


def save(rec: Dict) -> Dict:
    return db.save_roblox_video(rec)


def folder(rec: Dict) -> str:
    return os.path.join(ROOT, rec["video_id"])


def passage(rec: Dict, a: float, b: float) -> Dict:
    """A passage's entry (created when new): {a, b, rang, fichier, duree, moments, createur, separe, propres}."""
    return rec["passages"].setdefault(f"{a:.1f}-{b:.1f}", {"a": a, "b": b})


def used(rec: Dict) -> List[List[float]]:
    return [[p["a"], p["b"]] for p in rec["passages"].values()]


def touch(rec: Dict) -> None:
    rec["utilise_le"] = time.time()


def stale(rec: Dict, days: int = KEEP_DAYS) -> bool:
    return time.time() - (rec.get("utilise_le") or 0) > days * 86400


def purge(days: int = KEEP_DAYS) -> int:
    """The files of the videos not used for `days` removed (their record stays). -> how many."""
    n = 0
    for rec in db.list_roblox_videos():
        if stale(rec, days) and os.path.isdir(folder(rec)):
            shutil.rmtree(folder(rec), ignore_errors=True)
            n += 1
    return n


def exists(path: Optional[str]) -> bool:
    return bool(path) and os.path.exists(path)
