#!/usr/bin/env python3
"""
Backup - daily, automatic snapshots of everything that can't be rebuilt:
the SQLite database (every video, schedule decision and stats snapshot),
the upload schedule, and each channel's settings and border image.

Not included on purpose: channels/*/credentials.json and token.json (OAuth
secrets — no reason to multiply copies of them on disk; a channel is just
reconnected if needed), and the large media folders (videos, music,
backgrounds) which aren't the irreplaceable part.

The database is copied with SQLite's online backup API, which takes a
consistent snapshot even while the app keeps writing — a plain file copy
could catch it mid-write.
"""

import glob
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import db as _db

BACKUP_DIR = os.path.join("database", "backups")
KEEP = 14
MAX_AGE = timedelta(hours=24)
PREFIX = "tiktub-"
EXTRA_FILES = ["upload_schedule.json", "channels/channel_config.json"]
CHANNEL_FILES = ["profile.json", "background.jpg", "background.jpeg", "background.png"]


def _extra_paths() -> List[str]:
    paths = [p for p in EXTRA_FILES if os.path.exists(p)]
    for channel_dir in sorted(glob.glob("channels/*/")):
        for name in CHANNEL_FILES:
            p = os.path.join(channel_dir, name)
            if os.path.exists(p):
                paths.append(os.path.normpath(p))
    return paths


def _sqlite_copy(src: str, dst: str):
    """Consistent copy of a live SQLite database (online backup API)."""
    source = sqlite3.connect(src)
    target = sqlite3.connect(dst)
    try:
        with target:
            source.backup(target)
    finally:
        target.close()
        source.close()


def create_backup(reason: str = "auto") -> Dict:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(BACKUP_DIR, f"{PREFIX}{stamp}.zip")
    n = 1
    while os.path.exists(path):  # two backups within one second
        path = os.path.join(BACKUP_DIR, f"{PREFIX}{stamp}-{n}.zip")
        n += 1

    with tempfile.TemporaryDirectory() as tmp:
        db_copy = os.path.join(tmp, "tiktub.db")
        _sqlite_copy(_db.DB_PATH, db_copy)
        meta = {"created_at": datetime.now().isoformat(), "reason": reason}
        with zipfile.ZipFile(path + ".part", "w", zipfile.ZIP_DEFLATED) as z:
            z.write(db_copy, "database/tiktub.db")
            for p in _extra_paths():
                z.write(p, p.replace(os.sep, "/"))
            z.writestr("backup.json", json.dumps(meta, ensure_ascii=False))
        os.replace(path + ".part", path)  # never leave a half-written archive behind

    prune()
    return describe(path)


def describe(path: str) -> Dict:
    name = os.path.basename(path)
    info = {"name": name, "size": os.path.getsize(path), "created_at": None, "reason": None}
    try:
        with zipfile.ZipFile(path) as z:
            meta = json.loads(z.read("backup.json"))
            info.update(created_at=meta.get("created_at"), reason=meta.get("reason"))
    except (KeyError, zipfile.BadZipFile, json.JSONDecodeError):
        pass
    if not info["created_at"]:
        info["created_at"] = datetime.fromtimestamp(os.path.getmtime(path)).isoformat()
    return info


def list_backups() -> List[Dict]:
    paths = glob.glob(os.path.join(BACKUP_DIR, f"{PREFIX}*.zip"))
    return sorted((describe(p) for p in paths), key=lambda b: b["created_at"], reverse=True)


def prune(keep: int = KEEP):
    for old in list_backups()[keep:]:
        os.remove(os.path.join(BACKUP_DIR, old["name"]))


def latest_backup_age() -> Optional[timedelta]:
    backups = list_backups()
    if not backups:
        return None
    return datetime.now() - datetime.fromisoformat(backups[0]["created_at"])


def backup_if_due() -> Optional[Dict]:
    """The daily automatic backup: only when the last one is older than a day."""
    age = latest_backup_age()
    if age is not None and age < MAX_AGE:
        return None
    return create_backup("auto")


def _safe_name(name: str) -> str:
    if not name or os.path.basename(name) != name or not name.startswith(PREFIX) or not name.endswith(".zip"):
        raise ValueError("Nom de sauvegarde invalide")
    path = os.path.join(BACKUP_DIR, name)
    if not os.path.exists(path):
        raise FileNotFoundError(name)
    return path


def restore_backup(name: str) -> Dict:
    """Puts a backup back in place. The current state is backed up FIRST
    (reason "avant restauration"), so a restore can itself be undone."""
    path = _safe_name(name)
    with zipfile.ZipFile(path) as z:
        members = z.namelist()
        if "database/tiktub.db" not in members:
            raise ValueError("Sauvegarde incomplète (pas de base de données)")
        safety = create_backup("avant restauration")
        with tempfile.TemporaryDirectory() as tmp:
            z.extractall(tmp)
            # copy INTO the live database through SQLite (not a file
            # overwrite), so connections opened later all see the restored data
            _sqlite_copy(os.path.join(tmp, "database/tiktub.db"), _db.DB_PATH)
            for member in members:
                if member in ("database/tiktub.db", "backup.json") or member.endswith("/"):
                    continue
                dest = os.path.normpath(member)
                if dest.startswith("..") or os.path.isabs(dest):
                    continue  # never write outside the app folder
                os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
                shutil.copy(os.path.join(tmp, member), dest)
    return {"restored": name, "safety_backup": safety["name"]}
