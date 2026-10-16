#!/usr/bin/env python3
"""
Storage - what takes disk space, and cleaning what no longer serves.

Video files pile up: every download keeps a temp/<video_id>/ folder (raw
video, yt-dlp metadata, narration, word timings) and every render a file
in processed_videos/. Nothing removed them except the upload itself (and
only two of those files). This sorts them by the state of their video:

  published   – the video is on YouTube: its leftover files are dead weight
  orphans     – files no video row points to any more (older than 24 h,
                so a file still being written is never touched)
  rejected    – videos unticked in Sélection: removable on request only,
                and they then leave Sélection for good ('discarded')
  in use      – everything else (to sort, ready, failed-but-retryable,
                generation drafts...): never touched

Automatic cleanup (daily) removes published + orphans; the Stockage
screen can also remove rejected.
"""

import os
import shutil
import time
from typing import Dict, List

import db as _db

TEMP_DIR = "temp"
PROCESSED_DIR = "processed_videos"
ORPHAN_MIN_AGE = 24 * 3600
PUBLISHED = {"uploaded", "scheduled_on_youtube", "youtube_deleted"}
GONE = {"discarded", "duplicate"}          # never coming back either
REJECTED = {"rejected"}


def _size(path: str) -> int:
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _age(path: str) -> float:
    try:
        return time.time() - os.path.getmtime(path)
    except OSError:
        return 0


def _category(status) -> str:
    if status is None:
        return "orphans"
    if status in PUBLISHED or status in GONE:
        return "published"
    if status in REJECTED:
        return "rejected"
    return "in_use"


def _adaptation_items(root: str, rows: Dict) -> List[Dict]:
    """temp/adaptations/<project>: kept while the project runs (its sources,
    voices and previews are being reviewed); published once every video it
    made is on YouTube; an orphan when the project no longer exists."""
    out = []
    for pid in os.listdir(root):
        path = os.path.join(root, pid)
        project = _db.get_adaptation(pid)
        if not project:
            category = "orphans"
        else:
            made = [t.get("video_id") for t in project.get("targets", [])]
            statuses = [(rows.get(v) or {}).get("status") for v in made if v]
            category = "published" if (project["status"] == "done" and statuses
                                       and all(st in PUBLISHED for st in statuses)) else "in_use"
        out.append({"path": path, "video_id": None, "category": category, "size": _size(path), "age": _age(path)})
    return out


def scan() -> Dict:
    """Every temp/ folder and processed file, sorted by category."""
    rows = {v["video_id"]: v for v in _db.query_videos()}
    owner_of_file = {}
    for v in rows.values():
        if v.get("video_path"):
            owner_of_file[os.path.normpath(v["video_path"])] = v

    items: List[Dict] = []
    if os.path.isdir(TEMP_DIR):
        for name in os.listdir(TEMP_DIR):
            path = os.path.join(TEMP_DIR, name)
            if name == "adaptations" and os.path.isdir(path):
                items.extend(_adaptation_items(path, rows))
                continue
            video = rows.get(name) if os.path.isdir(path) else None
            items.append({"path": path, "video_id": video["video_id"] if video else None,
                          "category": _category(video["status"] if video else None),
                          "size": _size(path), "age": _age(path)})
    if os.path.isdir(PROCESSED_DIR):
        for name in os.listdir(PROCESSED_DIR):
            path = os.path.normpath(os.path.join(PROCESSED_DIR, name))
            video = owner_of_file.get(path)
            items.append({"path": path, "video_id": video["video_id"] if video else None,
                          "category": _category(video["status"] if video else None),
                          "size": _size(path), "age": _age(path)})

    totals = {c: {"size": 0, "count": 0} for c in ("published", "orphans", "rejected", "in_use")}
    for it in items:
        totals[it["category"]]["size"] += it["size"]
        totals[it["category"]]["count"] += 1
    assets = sum(_size(os.path.join("channels", c, "assets")) for c in os.listdir("channels")
                 if os.path.isdir(os.path.join("channels", c, "assets"))) if os.path.isdir("channels") else 0
    return {
        "items": items,
        "totals": totals,
        "assets": assets,
        "backups": _size(os.path.join("database", "backups")),
        "database": _size(_db.DB_PATH),
    }


def _removable(item: Dict, include_rejected: bool) -> bool:
    if item["category"] == "published":
        return True
    if item["category"] == "orphans":
        return item["age"] >= ORPHAN_MIN_AGE  # never a file still being written
    if item["category"] == "rejected":
        return include_rejected
    return False


def cleanup(include_rejected: bool = False) -> Dict:
    from url_manager import URLManager
    report = scan()
    freed = {"published": 0, "orphans": 0, "rejected": 0}
    count = 0
    discarded = set()
    for it in report["items"]:
        if not _removable(it, include_rejected):
            continue
        try:
            if os.path.isdir(it["path"]):
                shutil.rmtree(it["path"])
            else:
                os.remove(it["path"])
        except OSError:
            continue
        freed[it["category"]] += it["size"]
        count += 1
        if it["category"] == "rejected" and it["video_id"]:
            discarded.add(it["video_id"])
    if discarded:
        um = URLManager()
        for vid in discarded:
            # its source is gone: it can't be ticked again, take it out of Sélection
            um.update_video_status(vid, "discarded", raw_video_path=None, video_path=None)
    return {"freed": freed, "freed_total": sum(freed.values()), "removed": count, "discarded": len(discarded)}


CLEANUP_MARKER = os.path.join("database", ".last_cleanup")
CLEANUP_EVERY = 24 * 3600


def cleanup_if_due():
    """The daily automatic cleanup: published leftovers + old orphans only
    (never rejected videos — those wait for an explicit click)."""
    try:
        if time.time() - os.path.getmtime(CLEANUP_MARKER) < CLEANUP_EVERY:
            return None
    except OSError:
        pass
    result = cleanup(include_rejected=False)
    os.makedirs(os.path.dirname(CLEANUP_MARKER), exist_ok=True)
    with open(CLEANUP_MARKER, "w") as fh:
        fh.write(str(time.time()))
    return result
