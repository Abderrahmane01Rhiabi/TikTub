#!/usr/bin/env python3
"""
Stats Tracker - periodically snapshots real YouTube performance (views,
likes, comments, privacy status) for published videos, at fixed checkpoints
after publish, so there's an actual history to look back on instead of only
a live-fetched, never-saved number (the old Dashboard "Actualiser les
stats" behavior — one API call, shown once, gone on the next page load).

Runs as a background thread started at app startup (see webapp/main.py) —
nothing needs to be clicked for this to happen. YouTube has no push
mechanism for view/like counts (no webhook), so this polls instead — but
only calls out when something is actually due, and batches up to 50 videos
per channel into one cheap API call.
"""

import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

CHECKPOINTS: Dict[str, timedelta] = {
    "24h": timedelta(hours=24),
    "3d": timedelta(days=3),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}

PUBLISHED_STATUSES = {"uploaded", "scheduled_on_youtube"}


def _due_checkpoints(video: Dict, now: datetime, captured: set) -> List[str]:
    """Which of this video's checkpoints have both come due (time-wise) and
    not been captured yet."""
    uploaded_at = video.get("uploaded_at")
    if not uploaded_at:
        return []
    try:
        uploaded_dt = datetime.fromisoformat(uploaded_at)
    except ValueError:
        return []
    return [name for name, delta in CHECKPOINTS.items() if name not in captured and now - uploaded_dt >= delta]


def run_snapshot_cycle(batch_processor):
    """One pass: find every published video with a due, not-yet-captured
    checkpoint, batch-fetch fresh stats per channel (cheap — one API call
    covers up to 50 videos), and record a snapshot for each due checkpoint."""
    from youtube_uploader import get_video_stats

    url_manager = batch_processor.url_manager
    db = url_manager.load_database()
    now = datetime.now()

    due_by_channel: Dict[str, List[Tuple[Dict, List[str]]]] = {}
    for video in db.get("videos", {}).values():
        if video.get("status") not in PUBLISHED_STATUSES or not video.get("youtube_id"):
            continue
        captured = url_manager.get_captured_checkpoints(video["video_id"])
        due = _due_checkpoints(video, now, captured)
        if due:
            channel = video.get("channel", "default")
            due_by_channel.setdefault(channel, []).append((video, due))

    if not due_by_channel:
        return

    for channel, entries in due_by_channel.items():
        youtube_ids = [v["youtube_id"] for v, _ in entries]
        try:
            stats = get_video_stats(channel, youtube_ids)
        except Exception as e:
            print(f"⚠️ Stats snapshot failed for {channel}: {e}")
            continue

        captured_count = 0
        for video, due_checkpoints in entries:
            live = stats.get(video["youtube_id"])
            if not live:
                continue  # channel not connected, or video not returned — retry next cycle
            for checkpoint in due_checkpoints:
                url_manager.add_stats_snapshot(video["video_id"], checkpoint, live)
            captured_count += 1
        if captured_count:
            print(f"📸 {channel}: {captured_count} vidéo(s) — snapshot de performance enregistré")


def start_background_tracker(batch_processor, interval_seconds: int = 3600):
    """Starts the periodic snapshot loop in a daemon thread — call once at
    app startup. Runs one cycle right away, then every `interval_seconds`
    (default 1h — checkpoints are day-granularity, no need for tighter
    polling than that)."""
    def _loop():
        while True:
            try:
                run_snapshot_cycle(batch_processor)
            except Exception as e:
                print(f"⚠️ Stats tracker cycle failed: {e}")
            time.sleep(interval_seconds)

    threading.Thread(target=_loop, daemon=True).start()
