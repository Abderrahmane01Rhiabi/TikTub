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


def _local_naive(value: str):
    """Any stored date (ISO with or without offset, 'YYYY-MM-DD HH:MM:SS')
    as a naive local datetime, comparable with datetime.now()."""
    from dateutil import parser as date_parser
    dt = date_parser.parse(value)
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt


def published_moment(video: Dict):
    """When the video actually went public: YouTube's own publishedAt once
    synced, else the planned publishAt for a scheduled upload, else the
    upload time (immediate public upload). Checkpoints ("24h", "7d"...)
    count from THIS — counting from the upload made a video scheduled 3
    days out get its "24h" snapshot while still private."""
    for key in ("youtube_published_at", "scheduled_publish_time", "uploaded_at"):
        if video.get(key):
            try:
                return _local_naive(video[key])
            except (ValueError, OverflowError):
                continue
    return None


def _due_checkpoints(video: Dict, now: datetime, captured: set) -> List[str]:
    """Which of this video's checkpoints have both come due (time-wise) and
    not been captured yet."""
    published = published_moment(video)
    if not published:
        return []
    return [name for name, delta in CHECKPOINTS.items() if name not in captured and now - published >= delta]


def sync_youtube_statuses(batch_processor) -> Dict[str, int]:
    """Brings local statuses back in line with YouTube. 'scheduled_on_youtube'
    was never updated after YouTube actually published the video at its
    publishAt, so videos stayed "programmées" forever. For every scheduled
    video whose planned date has passed, asks YouTube (one cheap
    videos.list call per 50 videos per channel) and records what it really
    is: public → uploaded, still private → uploaded + youtube_privacy,
    re-scheduled later → new date kept, gone from the channel →
    youtube_deleted. A channel that can't be reached is left untouched."""
    from youtube_uploader import get_video_stats

    url_manager = batch_processor.url_manager
    now = datetime.now()
    summary = {"checked": 0, "published": 0, "private": 0, "rescheduled": 0, "deleted": 0, "unreachable": 0}

    due_by_channel: Dict[str, List[Dict]] = {}
    for video in url_manager.list_videos(status="scheduled_on_youtube"):
        when = published_moment(video)
        if video.get("youtube_id") and when and when <= now:
            due_by_channel.setdefault(video.get("channel", "default"), []).append(video)

    for channel, videos in due_by_channel.items():
        try:
            stats = get_video_stats(channel, [v["youtube_id"] for v in videos])
        except Exception as e:
            print(f"⚠️ Status sync failed for {channel}: {e}")
            stats = {}
        if not stats:
            # not connected / API unreachable: never conclude "deleted" from silence
            summary["unreachable"] += len(videos)
            continue
        for video in videos:
            summary["checked"] += 1
            live = stats.get(video["youtube_id"])
            if live is None:
                url_manager.update_video_status(video["video_id"], "youtube_deleted")
                summary["deleted"] += 1
                continue
            privacy, publish_at = live.get("privacy_status"), live.get("publish_at")
            if privacy == "private" and publish_at and _local_naive(publish_at) > now:
                url_manager.update_video_status(video["video_id"], "scheduled_on_youtube", scheduled_publish_time=publish_at)
                summary["rescheduled"] += 1
                continue
            url_manager.update_video_status(
                video["video_id"], "uploaded",
                youtube_published_at=live.get("published_at") or video.get("scheduled_publish_time"),
                youtube_privacy=privacy,
            )
            summary["published" if privacy != "private" else "private"] += 1

    if any(summary[k] for k in ("published", "private", "rescheduled", "deleted")):
        print(f"🔄 Statuts YouTube resynchronisés : {summary}")
    return summary


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
                # statuses first, so freshly published videos get their
                # real publish date before checkpoints are computed
                sync_youtube_statuses(batch_processor)
            except Exception as e:
                print(f"⚠️ Status sync failed: {e}")
            try:
                import backup
                backup.backup_if_due()  # daily: only when the last backup is over 24 h old
            except Exception as e:
                print(f"⚠️ Daily backup failed: {e}")
            try:
                import storage
                cleaned = storage.cleanup_if_due()  # daily: published leftovers + old orphans
                if cleaned and cleaned["freed_total"]:
                    print(f"🧹 Nettoyage automatique : {cleaned['freed_total'] / 1024 / 1024:.1f} Mo libérés")
            except Exception as e:
                print(f"⚠️ Daily cleanup failed: {e}")
            try:
                sync_retention(batch_processor)
            except Exception as e:
                print(f"⚠️ Retention sync failed: {e}")
            try:
                run_snapshot_cycle(batch_processor)
            except Exception as e:
                print(f"⚠️ Stats tracker cycle failed: {e}")
            time.sleep(interval_seconds)

    threading.Thread(target=_loop, daemon=True).start()


RETENTION_DELAY = timedelta(days=9)  # first week + YouTube Analytics' ~2-3 days of processing


def sync_retention(batch_processor, limit: int = 60) -> int:
    """Measures each published video's first-week retention once (stored on
    the row as retention_7d), past videos included — at most `limit` per
    run, so a big backlog is spread over a few hourly cycles."""
    from youtube_uploader import get_first_week_retention

    url_manager = batch_processor.url_manager
    now = datetime.now()
    due: Dict[str, List[Dict]] = {}
    for video in url_manager.list_videos():
        if not video.get("youtube_id") or video.get("retention_7d"):
            continue
        published = published_moment(video)
        if published and published + RETENTION_DELAY <= now:
            due.setdefault(video.get("channel", "default"), []).append(video)

    measured = 0
    for channel, videos in due.items():
        batch = videos[:max(0, limit - measured)]
        if not batch:
            break
        try:
            found = get_first_week_retention(channel, [
                {"youtube_id": v["youtube_id"], "start": published_moment(v).strftime("%Y-%m-%d")} for v in batch])
        except Exception as e:
            print(f"⚠️ Retention sync failed for {channel}: {e}")
            continue
        for v in batch:
            r = found.get(v["youtube_id"])
            if r:
                url_manager.update_video_status(v["video_id"], v["status"],
                                                retention_7d={**r, "measured_at": now.isoformat()})
                measured += 1
    if measured:
        print(f"📈 Rétention 1re semaine mesurée pour {measured} vidéo(s)")
    return measured
