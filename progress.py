#!/usr/bin/env python3
"""
Progress - real progress of long renders, for the UI's progress bars.

moviepy already computes per-frame encoding progress inside
write_videofile(); it was silenced (logger=None). EncodeProgress is a
proglog logger that turns those callbacks into a 0..1 fraction: the audio
track is written first ("chunk" bar), then every video frame ("t" bar).
Audio counts for the first AUDIO_SHARE of the bar, frames for the rest.

Jobs live in memory only (they describe something running in THIS server
process); a restart loses them — see recover_interrupted() in webapp/main.py
for the statuses a restart would otherwise leave stuck.
"""

import threading
import time
from typing import Callable, Dict, Optional

import proglog

AUDIO_SHARE = 0.08  # audio is written first and fast; frames are the real work

_jobs: Dict[str, Dict] = {}
_lock = threading.Lock()


class EncodeProgress(proglog.ProgressBarLogger):
    """Pass as write_videofile(logger=...). Calls on_fraction(0..1)."""

    def __init__(self, on_fraction: Callable[[float], None]):
        super().__init__()
        self.on_fraction = on_fraction

    def bars_callback(self, bar, attr, value, old_value=None):
        if attr != "index":
            return
        total = (self.bars.get(bar) or {}).get("total") or 0
        if not total:
            return
        done = min(1.0, value / total)
        if bar == "chunk":
            self.on_fraction(AUDIO_SHARE * done)
        elif bar == "t":
            self.on_fraction(AUDIO_SHARE + (1 - AUDIO_SHARE) * done)


def start(key: str, **info) -> Dict:
    now = time.time()
    job = {"key": key, "fraction": 0.0, "phase": None, "started_at": now, "updated_at": now,
           "done": False, "error": None, **info}
    with _lock:
        _jobs[key] = job
    return dict(job)


def update(key: str, fraction: Optional[float] = None, **info):
    with _lock:
        job = _jobs.get(key)
        if not job:
            return
        if fraction is not None:
            job["fraction"] = max(0.0, min(1.0, fraction))
        job.update(info)
        job["updated_at"] = time.time()


def finish(key: str, error: Optional[str] = None, **info):
    update(key, fraction=None if error else 1.0, done=True, error=error, **info)


def get(key: str) -> Optional[Dict]:
    """Snapshot of a job, with eta_seconds once there's enough progress to
    extrapolate from (elapsed / fraction done)."""
    with _lock:
        job = _jobs.get(key)
        if not job:
            return None
        job = dict(job)
        if isinstance(job.get("items"), list):
            job["items"] = [dict(i) for i in job["items"]]  # snapshot, not the live list
    elapsed = time.time() - job["started_at"]
    f = job["fraction"]
    job["elapsed_seconds"] = round(elapsed)
    job["eta_seconds"] = round(elapsed * (1 - f) / f) if not job["done"] and f >= 0.05 else None
    return job


def update_item(key: str, item_id: str, **fields):
    """Updates one entry of a job's "items" list (matched on item["id"]),
    then recomputes the job fraction as the share of finished items."""
    with _lock:
        job = _jobs.get(key)
        if not job:
            return
        items = job.get("items") or []
        for item in items:
            if item.get("id") == item_id:
                item.update(fields)
                break
        finished = sum(1 for i in items if i.get("state") in ("done", "failed", "duplicate"))
        job["fraction"] = finished / len(items) if items else 0.0
        job["updated_at"] = time.time()


def is_running(key: str) -> bool:
    job = get(key)
    return bool(job and not job["done"])
