#!/usr/bin/env python3
"""
Performance - "what actually works" on a channel, from the real YouTube
snapshots stats_tracker.py records (video_stats_history).

Videos are compared at the SAME age: views 7 days after publication (the
"7d" checkpoint). Comparing total views would just reward older videos.
Each video is scored against its own channel's median — channels differ by
orders of magnitude, so a raw view count says nothing across channels.

Then every attribute we know about a video (script format, décor, caption
style, publish weekday/hour, scheduling method, content type) is grouped,
and each group's median score shows which choices beat the channel's usual.
Alongside views, the first-week retention (average % of the video watched,
measured once per video by stats_tracker.sync_retention) says whether the
people who came stayed — what YouTube itself pushes on.
"""

from statistics import median
from typing import Dict, List, Optional

from stats_tracker import published_moment

METRIC_CHECKPOINT = "7d"
MIN_GROUP_SIZE = 2       # below this a "group" is one video — not a pattern
RELIABLE_GROUP_SIZE = 3  # below this, shown but flagged as weak evidence
# Smoothing added to both sides of views/median: on a channel whose median is
# 1-4 views, a raw ratio turns 30 views into "×30" and a viral video into
# "×7559". With +10 views each side, small channels read sanely while real
# gaps on bigger ones stay visible.
SCORE_SMOOTHING = 10

FORMAT_LABELS = {"A": "Affirmations", "B": "Storytime", "D": "Liste éducative"}
WEEKDAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

DIMENSIONS = [
    ("script_format", "Format de script"),
    ("background", "Fond vidéo"),
    ("music", "Musique"),
    ("caption_style", "Style de sous-titres"),
    ("weekday", "Jour de publication"),
    ("hour_slot", "Heure de publication"),
    ("method", "Méthode de planning"),
    ("content_type", "Type de contenu"),
]


def _basename(path: Optional[str]) -> Optional[str]:
    return path.replace("\\", "/").rsplit("/", 1)[-1] if path else None


def _hour_slot(hour: int) -> str:
    start = (hour // 3) * 3
    return f"{start:02d}h–{start + 3:02d}h"


def video_row(video: Dict, history: List[Dict]) -> Optional[Dict]:
    """One published video with its 7-day stats and every attribute we can
    group on. None when it has no 7-day snapshot yet (too recent)."""
    snap = next((h for h in history if h.get("checkpoint") == METRIC_CHECKPOINT), None)
    if not snap or snap.get("view_count") is None:
        return None
    ai = video.get("ai_data") or {}
    published = published_moment(video)
    views, likes = snap.get("view_count") or 0, snap.get("like_count")
    latest = history[-1] if history else snap
    retention = video.get("retention_7d") or {}
    return {
        "video_id": video["video_id"],
        "title": ai.get("optimized_title") or video.get("original_title") or video.get("title") or video["video_id"],
        "youtube_url": video.get("youtube_url"),
        "thumbnail_url": latest.get("thumbnail_url") or snap.get("thumbnail_url"),
        "source": video.get("source") or "import",
        "views_7d": views,
        "likes_7d": likes,
        "like_rate": round(likes / views, 4) if likes is not None and views else None,
        "views_latest": latest.get("view_count"),
        # first-week % watched (YouTube Analytics), None until measured
        "retention_7d": retention.get("average_view_percentage"),
        "avg_view_duration_7d": retention.get("average_view_duration"),
        "published": published.isoformat() if published else None,
        "attrs": {
            "script_format": video.get("script_format") or None,
            "background": _basename(video.get("bg_video_path")),
            "music": _basename(video.get("bg_music_path")),
            "caption_style": video.get("caption_style") or ("karaoke" if video.get("source") == "generated" else None),
            "weekday": WEEKDAYS[published.weekday()] if published else None,
            "hour_slot": _hour_slot(published.hour) if published else None,
            "method": (video.get("publish_decision") or {}).get("method"),
            "content_type": ai.get("content_type"),
        },
        # What "Refaire ce style" would reuse — generated videos only
        "remakeable": video.get("source") == "generated" and bool(video.get("script_text")),
    }


def label(dimension: str, value: str) -> str:
    if dimension == "script_format":
        return f"{value} · {FORMAT_LABELS.get(value, value)}"
    return value


def _median_or_none(values) -> Optional[float]:
    values = [v for v in values if v is not None]
    return round(median(values), 1) if values else None


def analyze(videos: List[Dict], history_by_video: Dict[str, List[Dict]]) -> Dict:
    """videos: one channel's published videos (rows from the videos table)."""
    rows, too_recent = [], 0
    for video in videos:
        row = video_row(video, history_by_video.get(video["video_id"], []))
        if row is None:
            too_recent += 1
        else:
            rows.append(row)

    if not rows:
        return {"analyzed": 0, "too_recent": too_recent, "median_views_7d": None,
                "median_retention_7d": None, "videos": [], "insights": []}

    base = median(r["views_7d"] for r in rows)
    for r in rows:
        r["score"] = round((r["views_7d"] + SCORE_SMOOTHING) / (base + SCORE_SMOOTHING), 2)
    rows.sort(key=lambda r: r["views_7d"], reverse=True)

    insights = []
    for dim, dim_label in DIMENSIONS:
        groups: Dict[str, List[Dict]] = {}
        for r in rows:
            value = r["attrs"].get(dim)
            if value:
                groups.setdefault(value, []).append(r)
        scored = [
            {"value": v, "label": label(dim, v), "count": len(g),
             "score": round(median(x["score"] for x in g), 2),
             "median_views_7d": median(x["views_7d"] for x in g),
             "median_retention_7d": _median_or_none(x["retention_7d"] for x in g),
             "reliable": len(g) >= RELIABLE_GROUP_SIZE}
            for v, g in groups.items() if len(g) >= MIN_GROUP_SIZE
        ]
        if len(scored) < 2:
            continue  # one option only: nothing to compare against
        scored.sort(key=lambda g: g["score"], reverse=True)
        insights.append({"dimension": dim, "label": dim_label, "groups": scored,
                         "best": scored[0], "worst": scored[-1]})

    # Solid evidence first (best group backed by enough videos), then the
    # strongest contrasts: where the choice matters most.
    insights.sort(key=lambda i: (i["best"]["reliable"], i["best"]["score"] - i["worst"]["score"]), reverse=True)
    return {"analyzed": len(rows), "too_recent": too_recent, "median_views_7d": base,
            "median_retention_7d": _median_or_none(r["retention_7d"] for r in rows),
            "videos": rows, "insights": insights}
