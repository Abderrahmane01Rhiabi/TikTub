#!/usr/bin/env python3
"""
Alerts - the problems worth interrupting for, noticed even when nobody is
looking at the screen where they happen:

  connection  – a channel's YouTube authorization stopped working (expired
                or revoked): nothing can be published there until it's
                reconnected. Checked hourly; cleared once it works again.
  quota       – YouTube answered quotaExceeded: the project is done for the
                day. Disappears by itself at the quota reset.
  publish     – a video's upload failed for a real reason (not skipped
                because of the two above, which have their own alert).
  deleted     – a published video is gone from YouTube.

One row per problem (`key`): raising an alert that's already open does
nothing, so the hourly checks never spam. The page shows open alerts on
every screen and, if allowed, as a Windows notification.
"""

from datetime import datetime
from typing import Dict, List, Optional

import db as _db


def raise_alert(key: str, kind: str, title: str, message: str, channel: Optional[str] = None) -> bool:
    """Opens the alert; True if it's new (or came back after being solved)."""
    conn = _db.get_connection()
    try:
        with conn:
            row = conn.execute("SELECT resolved_at FROM alerts WHERE key = ?", (key,)).fetchone()
            if row and row["resolved_at"] is None:
                conn.execute("UPDATE alerts SET message = ? WHERE key = ?", (message, key))
                return False
            conn.execute(
                """INSERT INTO alerts (key, kind, channel, title, message, created_at) VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET kind = excluded.kind, channel = excluded.channel,
                       title = excluded.title, message = excluded.message, created_at = excluded.created_at,
                       dismissed_at = NULL, resolved_at = NULL""",
                (key, kind, channel, title, message, datetime.now().isoformat()))
            return True
    finally:
        conn.close()


def resolve(key: str):
    """The problem is gone (connection works again, upload succeeded...)."""
    _update("UPDATE alerts SET resolved_at = ? WHERE key = ? AND resolved_at IS NULL", key)


def dismiss(key: str):
    """Seen by the user: hidden, but stays open — not raised again until solved."""
    _update("UPDATE alerts SET dismissed_at = ? WHERE key = ? AND dismissed_at IS NULL", key)


def _update(sql: str, key: str):
    conn = _db.get_connection()
    try:
        with conn:
            conn.execute(sql, (datetime.now().isoformat(), key))
    finally:
        conn.close()


def active() -> List[Dict]:
    import quota
    today = quota.quota_day()
    conn = _db.get_connection()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT key, kind, channel, title, message, created_at FROM alerts "
            "WHERE resolved_at IS NULL AND dismissed_at IS NULL ORDER BY created_at DESC")]
    finally:
        conn.close()
    # a quota alert is for one quota day: gone once YouTube has reset it
    return [r for r in rows if r["kind"] != "quota" or r["key"].endswith(":" + today)]


# ---------------------------------------------------------------------------
# The checks, wired where each problem is noticed
# ---------------------------------------------------------------------------

def connection_state(channel: str, state: str, reason: Optional[str] = None):
    """Called with every connection check (hourly, and whenever the UI asks)."""
    key = f"connection:{channel}"
    if state == "expired":
        raise_alert(key, "connection", f"{_display(channel)} : connexion YouTube expirée",
                    "Plus rien ne peut être publié sur cette chaîne — reconnecte-la dans Réglages → Connexion."
                    + (f" ({reason})" if reason else ""), channel)
    elif state == "connected":
        resolve(key)


def check_connections() -> int:
    """Hourly: every channel that has been connected once (1 API unit each)."""
    from channel_manager import ChannelManager
    from youtube_uploader import get_connection_health
    expired = 0
    for ch in ChannelManager().list_channels():
        if not ch.get("has_token"):
            continue
        health = get_connection_health(ch["name"])
        connection_state(ch["name"], health["state"], health.get("reason"))
        expired += health["state"] == "expired"
    return expired


def quota_exhausted(channel: str, project_key: str, day: str):
    raise_alert(f"quota:{project_key}:{day}", "quota", "Quota YouTube du jour atteint",
                f"YouTube refuse de nouveaux envois (dernier essai : {_display(channel)}). "
                "Les vidéos restantes attendent : relance « Publier » après minuit, heure du Pacifique (9 h en France).",
                channel)


def publish_result(channel: str, result: Dict):
    """One line of upload_channel_schedule's results."""
    key = f"publish:{result['video_id']}"
    if result.get("success"):
        resolve(key)
    elif not result.get("skipped"):  # skipped = quota/connection, alerted on their own
        raise_alert(key, "publish", f"Échec de publication sur {_display(channel)}",
                    f"« {result.get('title') or result['video_id']} » : {result.get('error') or 'erreur inconnue'}", channel)


def video_deleted(video: Dict):
    title = (video.get("ai_data") or {}).get("optimized_title") or video.get("original_title") or video["video_id"]
    raise_alert(f"deleted:{video['video_id']}", "deleted", f"Vidéo disparue de YouTube ({_display(video.get('channel'))})",
                f"« {title} » n'existe plus sur YouTube (supprimée ou retirée).", video.get("channel"))


def _display(channel: Optional[str]) -> str:
    if not channel:
        return "?"
    try:
        from channel_manager import ChannelManager
        return next((c["display_name"] for c in ChannelManager().list_channels() if c["name"] == channel), channel)
    except Exception:
        return channel
