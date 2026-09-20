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
                           db_path: str = DB_PATH) -> Optional[Dict]:
    """Indexed on url — no linear scan through every video regardless of table size."""
    conn = get_connection(db_path)
    try:
        placeholders = ",".join("?" * len(ignorable_statuses))
        row = conn.execute(
            f"""SELECT * FROM videos
                WHERE url = ? AND video_id != ? AND status NOT IN ({placeholders})
                LIMIT 1""",
            (url, exclude_video_id or "", *ignorable_statuses)
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
