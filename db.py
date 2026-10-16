#!/usr/bin/env python3
"""
SQLite storage backend for TikTub's video/batch tracking.

Videos have a lot of dynamic, evolving fields (raw_video_path, ai_data — itself
a nested dict, duplicate_of, youtube_url, ...), so each row keeps a handful of
columns that are actually queried a lot (status, channel, url, batch_id) as
real indexed columns, plus one JSON column holding the full record. This gives
real indexed lookups for the hot paths (status updates, duplicate checks,
listing) while staying schema-flexible for everything else — no migration
needed every time a new field gets added to a video dict.
"""

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = "database/tiktub.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    batch_id TEXT,
    channel TEXT,
    url TEXT,
    status TEXT,
    updated_at TEXT,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
CREATE INDEX IF NOT EXISTS idx_videos_channel ON videos(channel);
CREATE INDEX IF NOT EXISTS idx_videos_url ON videos(url);
CREATE INDEX IF NOT EXISTS idx_videos_batch ON videos(batch_id);

CREATE TABLE IF NOT EXISTS batches (
    batch_id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS action_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    status_code INTEGER,
    details TEXT
);
CREATE INDEX IF NOT EXISTS idx_action_log_timestamp ON action_log(timestamp);

-- One row per performance snapshot of a published video (views/likes/status
-- at a point in time) — a video accumulates many rows over its lifetime,
-- unlike the `videos` table which holds only the current state. Powers any
-- future "what actually performs well" analysis (script_format/décor/
-- scheduling-method vs real outcome), which a single live-fetched snapshot
-- (the old Dashboard "Actualiser les stats" behavior) can't support since
-- it was never kept past the current page load.
CREATE TABLE IF NOT EXISTS video_stats_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    checkpoint TEXT,
    snapshot_at TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stats_history_video ON video_stats_history(video_id);
CREATE INDEX IF NOT EXISTS idx_stats_history_snapshot ON video_stats_history(snapshot_at);

-- YouTube API quota consumption, per Google Cloud project (the quota is
-- per project, shared by every channel whose credentials.json comes from
-- it) and per quota day (YouTube resets at midnight Pacific Time) — see
-- quota.py. `exhausted` is set only from a REAL quotaExceeded answer from
-- YouTube, never from our own estimate.
CREATE TABLE IF NOT EXISTS quota_usage (
    project_key TEXT NOT NULL,
    day TEXT NOT NULL,
    units INTEGER NOT NULL DEFAULT 0,
    uploads INTEGER NOT NULL DEFAULT 0,
    exhausted INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (project_key, day)
);

-- Problems worth interrupting for (expired connection, quota hit, failed
-- upload, video gone from YouTube) — see alerts.py. One row per problem.
CREATE TABLE IF NOT EXISTS alerts (
    key TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    channel TEXT,
    title TEXT NOT NULL,
    message TEXT,
    created_at TEXT NOT NULL,
    dismissed_at TEXT,
    resolved_at TEXT
);

-- Montage auto: one row per drone shot used in a RENDERED video (see
-- montage/broll.py). Keeps a channel from reusing its recent shots, and
-- says how often each shot has served. Previews and plans awaiting review
-- are not usage: those are read from the videos themselves.
CREATE TABLE IF NOT EXISTS broll_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    clip_id TEXT NOT NULL,
    video_id TEXT,
    used_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_broll_usage_channel ON broll_usage(channel, used_at);
CREATE INDEX IF NOT EXISTS idx_broll_usage_clip ON broll_usage(clip_id);

-- Adaptation: the ElevenLabs voices a person can pick for a channel
-- (Réglages → Voix). name/language/accent are queried columns, the rest
-- (gender, age, preview...) lives in the JSON.
-- Adaptation projects: one viral reference Short + its source videos ->
-- one video per target channel/language (see adaptation/pipeline.py).
CREATE TABLE IF NOT EXISTS adaptations (
    project_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS voices (
    voice_id TEXT PRIMARY KEY,
    name TEXT,
    language TEXT,
    accent TEXT,
    added_at TEXT NOT NULL,
    data TEXT NOT NULL
);
"""


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str = DB_PATH):
    conn = get_connection(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def _video_row_to_dict(row: sqlite3.Row) -> Dict:
    return json.loads(row["data"])


def load_all(db_path: str = DB_PATH) -> Dict:
    """Full snapshot, same shape as the old JSON file: {"videos": {...}, "batches": {...}}."""
    conn = get_connection(db_path)
    try:
        videos = {r["video_id"]: _video_row_to_dict(r) for r in conn.execute("SELECT * FROM videos")}
        batches = {r["batch_id"]: json.loads(r["data"]) for r in conn.execute("SELECT * FROM batches")}
        return {"videos": videos, "batches": batches}
    finally:
        conn.close()


def replace_all(data: Dict, db_path: str = DB_PATH):
    """Atomically replace the whole store with `data` (same all-at-once semantics
    the old save_database(whole_dict) had) — wrapped in one transaction, so a
    crash mid-write can never leave a half-written / corrupted store, unlike a
    plain JSON file write."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM videos")
            conn.execute("DELETE FROM batches")
            for video_id, video in data.get("videos", {}).items():
                _upsert_video(conn, video_id, video)
            for batch_id, batch in data.get("batches", {}).items():
                conn.execute(
                    "INSERT INTO batches (batch_id, data) VALUES (?, ?)",
                    (batch_id, json.dumps(batch, ensure_ascii=False))
                )
    finally:
        conn.close()


def _upsert_video(conn: sqlite3.Connection, video_id: str, video: Dict):
    conn.execute(
        """INSERT INTO videos (video_id, batch_id, channel, url, status, updated_at, data)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(video_id) DO UPDATE SET
               batch_id=excluded.batch_id, channel=excluded.channel, url=excluded.url,
               status=excluded.status, updated_at=excluded.updated_at, data=excluded.data""",
        (
            video_id, video.get("batch_id"), video.get("channel"), video.get("url"),
            video.get("status"), video.get("updated_at"), json.dumps(video, ensure_ascii=False)
        )
    )


def upsert_video(video_id: str, video: Dict, db_path: str = DB_PATH):
    conn = get_connection(db_path)
    try:
        with conn:
            _upsert_video(conn, video_id, video)
    finally:
        conn.close()


def get_video(video_id: str, db_path: str = DB_PATH) -> Optional[Dict]:
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,)).fetchone()
        return _video_row_to_dict(row) if row else None
    finally:
        conn.close()


def delete_video(video_id: str, db_path: str = DB_PATH):
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM videos WHERE video_id = ?", (video_id,))
    finally:
        conn.close()


def insert_stats_snapshot(video_id: str, checkpoint: Optional[str], data: Dict, db_path: str = DB_PATH):
    """Appends one performance snapshot — never overwrites a previous one,
    the whole point is keeping the history, not just the latest value."""
    from datetime import datetime
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO video_stats_history (video_id, checkpoint, snapshot_at, data) VALUES (?, ?, ?, ?)",
                (video_id, checkpoint, datetime.now().isoformat(), json.dumps(data, ensure_ascii=False)),
            )
    finally:
        conn.close()


def get_stats_history(video_id: str, db_path: str = DB_PATH) -> List[Dict]:
    """Every snapshot ever taken for this video, oldest first."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT checkpoint, snapshot_at, data FROM video_stats_history WHERE video_id = ? ORDER BY snapshot_at",
            (video_id,),
        ).fetchall()
        return [
            {"checkpoint": r["checkpoint"], "snapshot_at": r["snapshot_at"], **json.loads(r["data"])}
            for r in rows
        ]
    finally:
        conn.close()


def get_captured_checkpoints(video_id: str, db_path: str = DB_PATH) -> set:
    """Which named checkpoints ('24h', '3d', ...) already have a snapshot for
    this video — so the background tracker never double-captures one."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT DISTINCT checkpoint FROM video_stats_history WHERE video_id = ? AND checkpoint IS NOT NULL",
            (video_id,),
        ).fetchall()
        return {r["checkpoint"] for r in rows}
    finally:
        conn.close()


def query_videos(status: str = None, channel: str = None, batch_id: str = None,
                  db_path: str = DB_PATH) -> List[Dict]:
    """Real indexed lookup — only the matching rows are read, not the whole table."""
    conn = get_connection(db_path)
    try:
        clauses, params = [], []
        if status is not None:
            clauses.append("status = ?"); params.append(status)
        if channel is not None:
            clauses.append("channel = ?"); params.append(channel)
        if batch_id is not None:
            clauses.append("batch_id = ?"); params.append(batch_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(f"SELECT * FROM videos {where}", params).fetchall()
        return [_video_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def find_duplicate_by_url(url: str, exclude_video_id: str, ignorable_statuses: tuple,
                           channel: str = None, db_path: str = DB_PATH) -> Optional[Dict]:
    """Indexed on url — no linear scan through every video regardless of table size.
    channel, when given, scopes the check to that one channel — the same URL
    is a legitimate, separate download for a different channel, only a
    duplicate within the SAME channel."""
    conn = get_connection(db_path)
    try:
        placeholders = ",".join("?" * len(ignorable_statuses))
        channel_clause = "AND channel = ?" if channel is not None else ""
        params = [url, exclude_video_id or "", *ignorable_statuses]
        if channel is not None:
            params.append(channel)
        row = conn.execute(
            f"""SELECT * FROM videos
                WHERE url = ? AND video_id != ? AND status NOT IN ({placeholders}) {channel_clause}
                LIMIT 1""",
            params
        ).fetchone()
        return _video_row_to_dict(row) if row else None
    finally:
        conn.close()


def log_action(method: str, path: str, status_code: int, details: str = None, db_path: str = DB_PATH):
    """Persists one action so the app's activity survives restarts — unlike the
    terminal output, which is gone the moment the uvicorn window closes."""
    from datetime import datetime
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO action_log (timestamp, method, path, status_code, details) VALUES (?, ?, ?, ?, ?)",
                (datetime.now().isoformat(), method, path, status_code, details)
            )
    finally:
        conn.close()


def list_action_log(limit: int = 200, db_path: str = DB_PATH) -> List[Dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM action_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_quota_usage(project_key: str, day: str, units: int, uploads: int = 1, db_path: str = DB_PATH):
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """INSERT INTO quota_usage (project_key, day, units, uploads) VALUES (?, ?, ?, ?)
                   ON CONFLICT(project_key, day) DO UPDATE SET
                       units = units + excluded.units, uploads = uploads + excluded.uploads""",
                (project_key, day, units, uploads)
            )
    finally:
        conn.close()


def set_quota_exhausted(project_key: str, day: str, db_path: str = DB_PATH):
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """INSERT INTO quota_usage (project_key, day, exhausted) VALUES (?, ?, 1)
                   ON CONFLICT(project_key, day) DO UPDATE SET exhausted = 1""",
                (project_key, day)
            )
    finally:
        conn.close()


def get_quota_usage(project_key: str, day: str, db_path: str = DB_PATH) -> Dict:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT units, uploads, exhausted FROM quota_usage WHERE project_key = ? AND day = ?",
            (project_key, day)
        ).fetchone()
        if not row:
            return {"units": 0, "uploads": 0, "exhausted": False}
        return {"units": row["units"], "uploads": row["uploads"], "exhausted": bool(row["exhausted"])}
    finally:
        conn.close()


def insert_batch(batch_id: str, batch: Dict, videos: Dict[str, Dict], db_path: str = DB_PATH):
    """Atomic: the batch row and all its video rows commit together or not at all."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO batches (batch_id, data) VALUES (?, ?)",
                (batch_id, json.dumps(batch, ensure_ascii=False))
            )
            for video_id, video in videos.items():
                _upsert_video(conn, video_id, video)
    finally:
        conn.close()


def record_broll_usage(channel: str, clip_ids: List, video_id: Optional[str] = None,
                       used_at: Optional[str] = None, db_path: str = DB_PATH):
    """The drone shots a rendered video used. Rendering the same video again
    replaces its rows instead of counting the shots twice."""
    from datetime import datetime
    when = used_at or datetime.now().isoformat()
    conn = get_connection(db_path)
    try:
        with conn:
            if video_id:
                conn.execute("DELETE FROM broll_usage WHERE channel = ? AND video_id = ?", (channel, video_id))
            conn.executemany(
                "INSERT INTO broll_usage (channel, clip_id, video_id, used_at) VALUES (?, ?, ?, ?)",
                [(channel, str(c), video_id, when) for c in clip_ids],
            )
    finally:
        conn.close()


def recent_broll_clips(channel: str, limit: int, db_path: str = DB_PATH) -> List[str]:
    """The channel's last `limit` different shots, most recently used first."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT clip_id, MAX(used_at) AS last FROM broll_usage WHERE channel = ? "
            "GROUP BY clip_id ORDER BY last DESC LIMIT ?", (channel, limit)).fetchall()
        return [r["clip_id"] for r in rows]
    finally:
        conn.close()


def broll_last_used(channel: str, db_path: str = DB_PATH) -> Dict[str, str]:
    """clip_id -> last time this channel used it."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute("SELECT clip_id, MAX(used_at) AS last FROM broll_usage WHERE channel = ? "
                            "GROUP BY clip_id", (channel,)).fetchall()
        return {r["clip_id"]: r["last"] for r in rows}
    finally:
        conn.close()


def broll_usage_counts(db_path: str = DB_PATH) -> Dict[str, Dict]:
    """clip_id -> {"total": n, "channels": {channel: n}}"""
    conn = get_connection(db_path)
    try:
        out: Dict[str, Dict] = {}
        for r in conn.execute("SELECT clip_id, channel, COUNT(*) AS n FROM broll_usage GROUP BY clip_id, channel"):
            entry = out.setdefault(r["clip_id"], {"total": 0, "channels": {}})
            entry["total"] += r["n"]
            entry["channels"][r["channel"]] = r["n"]
        return out
    finally:
        conn.close()


def upsert_voice(voice: Dict, db_path: str = DB_PATH):
    from datetime import datetime
    conn = get_connection(db_path)
    try:
        with conn:
            row = conn.execute("SELECT added_at FROM voices WHERE voice_id = ?", (voice["voice_id"],)).fetchone()
            conn.execute(
                "INSERT OR REPLACE INTO voices (voice_id, name, language, accent, added_at, data) VALUES (?, ?, ?, ?, ?, ?)",
                (voice["voice_id"], voice.get("name"), voice.get("language"), voice.get("accent"),
                 row["added_at"] if row else datetime.now().isoformat(), json.dumps(voice, ensure_ascii=False)))
    finally:
        conn.close()


def list_voices(language: Optional[str] = None, db_path: str = DB_PATH) -> List[Dict]:
    """By language, then name. language='ar' also matches 'ar-EG' etc."""
    conn = get_connection(db_path)
    try:
        if language:
            rows = conn.execute("SELECT * FROM voices WHERE language = ? OR language LIKE ? ORDER BY name",
                                (language, language + "-%")).fetchall()
        else:
            rows = conn.execute("SELECT * FROM voices ORDER BY language, name").fetchall()
        return [{**json.loads(r["data"]), "added_at": r["added_at"]} for r in rows]
    finally:
        conn.close()


def get_voice(voice_id: str, db_path: str = DB_PATH) -> Optional[Dict]:
    conn = get_connection(db_path)
    try:
        r = conn.execute("SELECT * FROM voices WHERE voice_id = ?", (voice_id,)).fetchone()
        return {**json.loads(r["data"]), "added_at": r["added_at"]} if r else None
    finally:
        conn.close()


def delete_voice(voice_id: str, db_path: str = DB_PATH) -> bool:
    conn = get_connection(db_path)
    try:
        with conn:
            return conn.execute("DELETE FROM voices WHERE voice_id = ?", (voice_id,)).rowcount > 0
    finally:
        conn.close()


def save_adaptation(project: Dict, db_path: str = DB_PATH):
    from datetime import datetime
    now = datetime.now().isoformat()
    project = {**project, "updated_at": now}
    project.setdefault("created_at", now)
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute("INSERT OR REPLACE INTO adaptations (project_id, status, created_at, updated_at, data) "
                         "VALUES (?, ?, ?, ?, ?)", (project["project_id"], project["status"], project["created_at"],
                                                    now, json.dumps(project, ensure_ascii=False)))
    finally:
        conn.close()
    return project


def get_adaptation(project_id: str, db_path: str = DB_PATH) -> Optional[Dict]:
    conn = get_connection(db_path)
    try:
        r = conn.execute("SELECT data FROM adaptations WHERE project_id = ?", (project_id,)).fetchone()
        return json.loads(r["data"]) if r else None
    finally:
        conn.close()


def list_adaptations(db_path: str = DB_PATH) -> List[Dict]:
    conn = get_connection(db_path)
    try:
        return [json.loads(r["data"]) for r in conn.execute("SELECT data FROM adaptations ORDER BY created_at DESC")]
    finally:
        conn.close()


def delete_adaptation(project_id: str, db_path: str = DB_PATH) -> bool:
    conn = get_connection(db_path)
    try:
        with conn:
            return conn.execute("DELETE FROM adaptations WHERE project_id = ?", (project_id,)).rowcount > 0
    finally:
        conn.close()
