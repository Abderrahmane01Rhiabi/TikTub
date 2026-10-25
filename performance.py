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

FORMAT_LABELS = {"A": "Affirmations", "B": "Histoire", "D": "Liste éducative", "M": "Mythe ou réalité",
                 "C": "Citation expliquée", "E": "Exercice guidé", "L": "Lettre à toi", "P": "Le saviez-vous (psycho)"}
# (same labels as generative/script_plan.FORMATS, kept here so this module needs no generation import)
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
    # from the recipe every video now keeps (recette.py): how it was made
    ("video_type", "Type de vidéo"),
    ("mode", "Mode d'Adaptation"),
    ("duration", "Durée de la vidéo"),
    ("hook", "Durée de l'accroche"),
    ("pace", "Rythme des plans"),
    ("voice", "Voix"),
    ("visual_style", "Style visuel"),
    ("arrows", "Flèches et cercles"),
    ("slowmo", "Ralenti"),
    ("sfx", "Effets sonores"),
]

TYPE_LABELS = {"adaptation": "Adaptation", "generation": "Génération", "montage": "Montage auto", "import": "Import"}


def _bucket(x: Optional[float], edges: List[float], labels: List[str]) -> Optional[str]:
    """The range a number falls in: labels has one more item than edges."""
    if x is None:
        return None
    for edge, lab in zip(edges, labels):
        if x < edge:
            return lab
    return labels[-1]


def recipe_attrs(rec: Optional[Dict]) -> Dict[str, Optional[str]]:
    """What a video's recipe says, as groups to compare (None: not known)."""
    if not rec:
        return {}
    st, d = rec.get("structure") or {}, rec.get("details") or {}
    plans = [p for p in d.get("plans") or [] if isinstance(p, dict)]
    out = {"video_type": TYPE_LABELS.get(rec.get("type")),
           "duration": _bucket(st.get("duree_s"), [20, 30, 40], ["moins de 20 s", "20 à 30 s", "30 à 40 s", "40 s et plus"]),
           "hook": _bucket((rec.get("accroche") or {}).get("duree_s"), [2, 3, 4],
                           ["moins de 2 s", "2 à 3 s", "3 à 4 s", "4 s et plus"]),
           "pace": _bucket(st.get("plan_moyen_s"), [2, 3, 5], ["plans de moins de 2 s", "plans de 2 à 3 s",
                                                               "plans de 3 à 5 s", "plans de 5 s et plus"])
           if (st.get("plans") or 0) > 1 else None,
           "voice": (rec.get("voix") or {}).get("id") if isinstance(rec.get("voix"), dict) else None,
           "visual_style": (rec.get("style") or {}).get("visuel") or (rec.get("style") or {}).get("recette")}
    if rec.get("type") == "adaptation":
        n = sum(1 for p in plans if p.get("fleche"))
        out.update(mode="Script d'abord" if d.get("mode") == "script" else "Sources d'abord",
                   arrows="sans flèche" if not n else "1 flèche ou cercle" if n == 1 else "2 flèches ou cercles et plus",
                   slowmo="avec ralenti" if any((p.get("effets_appliques") or {}).get("ralenti") for p in plans)
                   else "sans ralenti")
        if "effets_sonores" in d:          # recipes made before the sound effects existed say nothing
            out["sfx"] = "avec effets sonores" if d["effets_sonores"] else "sans effets sonores"
    return out


_VOICE_NAMES: Dict[str, str] = {}


def _voice_name(voice_id: str) -> str:
    if voice_id not in _VOICE_NAMES:
        try:
            import db
            v = db.get_voice(voice_id) or {}
        except Exception:
            v = {}
        _VOICE_NAMES[voice_id] = v.get("name") or voice_id
    return _VOICE_NAMES[voice_id]


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
    rec = video.get("recette") or {}
    made = recipe_attrs(rec)
    if not made.get("duration") and retention.get("average_view_duration") and retention.get("average_view_percentage"):
        # a rebuilt recipe lost the length (file deleted after upload): watched time / share watched
        made["duration"] = _bucket(retention["average_view_duration"] * 100 / retention["average_view_percentage"],
                                   [20, 30, 40], ["moins de 20 s", "20 à 30 s", "30 à 40 s", "40 s et plus"])
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
            "music": _basename(video.get("bg_music_path")) or (rec.get("musique") or {}).get("fichier"),
            "caption_style": video.get("caption_style") or ("karaoke" if video.get("source") == "generated" else None),
            "weekday": WEEKDAYS[published.weekday()] if published else None,
            "hour_slot": _hour_slot(published.hour) if published else None,
            "method": (video.get("publish_decision") or {}).get("method"),
            "content_type": ai.get("content_type"),
            **made,
        },
        # What "Refaire ce style" would reuse — generated videos only
        "remakeable": video.get("source") == "generated" and bool(video.get("script_text")),
        # ...and for an Adaptation: its voice, music and look on another model Short
        "remake_adaptation": (video.get("recette") or {}).get("type") == "adaptation",
    }


def label(dimension: str, value: str) -> str:
    if dimension == "script_format":
        return f"{value} · {FORMAT_LABELS.get(value, value)}"
    if dimension == "voice":
        return _voice_name(value)
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


# ------------------------------------------------------------------ where viewers leave, shot by shot

def shots_of(rec: Optional[Dict]) -> List[Dict]:
    """The video's shots from its recipe: [{k, debut, fin, texte, bandeau}] (one
    shot for a video without a plan list: an import, a generated video)."""
    rec = rec or {}
    plans = [p for p in (rec.get("details") or {}).get("plans") or [] if isinstance(p, dict)]
    if plans and all(p.get("debut") is not None and p.get("duree") for p in plans):
        return [{"k": i, "debut": round(p["debut"], 2), "fin": round(p["debut"] + p["duree"], 2),
                 "texte": p.get("texte"), "bandeau": p.get("bandeau")} for i, p in enumerate(plans)]
    dur = (rec.get("structure") or {}).get("duree_s")
    return [{"k": 0, "debut": 0.0, "fin": dur, "texte": (rec.get("accroche") or {}).get("texte"), "bandeau": None}] if dur else []


def _watch_at(points: List[List[float]], ratio: float) -> Optional[float]:
    """The audience watch ratio at a share of the video (linear between YouTube's points)."""
    if not points:
        return None
    pts = sorted(points)
    if ratio <= pts[0][0]:
        return pts[0][1]
    for (r0, w0, *_), (r1, w1, *_) in zip(pts, pts[1:]):
        if r0 <= ratio <= r1:
            return w0 + (w1 - w0) * (ratio - r0) / ((r1 - r0) or 1)
    return pts[-1][1]


def curve_by_shot(points: List[List[float]], shots: List[Dict], duration: Optional[float]) -> Dict:
    """Each shot's audience at its start and its end (in % of the viewers who
    started the video, above 100 % where people watch again) and what it
    loses; the shot that loses the most, the hook's keep."""
    if not points or not shots or not duration:
        return {"plans": [], "pire": None, "apres_accroche": None}
    out = []
    for s in shots:
        a = _watch_at(points, min(1.0, s["debut"] / duration))
        b = _watch_at(points, min(1.0, s["fin"] / duration))
        out.append({**s, "debut_pct": round(a * 100, 1), "fin_pct": round(b * 100, 1), "perte": round((a - b) * 100, 1),
                    "perte_par_s": round((a - b) * 100 / max(0.1, s["fin"] - s["debut"]), 1)})
    # the worst shot AFTER the hook: people swipe a Short away in its first seconds whatever follows (the hook
    # always came out worst); what the hook keeps is said apart ("apres_accroche")
    body = out[1:] if len(out) > 2 else out
    worst = max(body, key=lambda x: x["perte_par_s"]) if len(out) > 1 else None
    # what the hook keeps of those who started: a Short loops, so the curve starts well above 100 %
    # (205 % at the start, 192 % after the hook = 93 % kept) — raw levels can't be compared between videos
    first = out[0]
    kept = round(first["fin_pct"] / first["debut_pct"] * 100, 1) if len(out) > 1 and first["debut_pct"] > 0 else None
    return {"plans": out, "pire": worst["k"] if worst and worst["perte"] > 0 else None, "apres_accroche": kept}


# ------------------------------------------------------------------ versions of one Short, side by side

TIE_POINTS = 3.0          # retention closer than this (points of % watched): no winner


def versions(videos: List[Dict], history_by_video: Dict[str, List[Dict]]) -> List[Dict]:
    """The Shorts made in several versions (one per channel, same model Short,
    its own angle and hook): a free A/B test of the writing, since the
    pictures are the same. Views are scored against each version's OWN channel
    (a French and an Arabic audience differ); the winner is the version that
    keeps people longer (first-week retention), else the one after the hook."""
    rows_by_channel: Dict[str, List[Dict]] = {}
    for v in videos:
        if v.get("youtube_id"):
            row = video_row(v, history_by_video.get(v["video_id"], []))
            if row:
                rows_by_channel.setdefault(v.get("channel"), []).append(row)
    medians = {ch: median(r["views_7d"] for r in rows) for ch, rows in rows_by_channel.items() if rows}
    rows = {r["video_id"]: r for rs in rows_by_channel.values() for r in rs}
    groups: Dict[str, List[Dict]] = {}
    for v in videos:
        # Adaptations only: an import posted on two channels is the same video, not two versions
        if v.get("youtube_id") and v.get("url") and (v.get("recette") or {}).get("type") == "adaptation":
            groups.setdefault(v["url"], []).append(v)
    out = []
    for url, vs in groups.items():
        if len({v.get("channel") for v in vs}) < 2:
            continue
        items = []
        for v in vs:
            rec, r = v.get("recette") or {}, rows.get(v["video_id"])
            d = rec.get("details") or {}
            curve = curve_by_shot((v.get("retention_curve") or {}).get("points") or [], shots_of(rec),
                                  (rec.get("structure") or {}).get("duree_s"))
            base = medians.get(v.get("channel"))
            items.append({
                "video_id": v["video_id"], "channel": v.get("channel"), "langue": rec.get("langue") or d.get("langue"),
                "titre": (v.get("ai_data") or {}).get("optimized_title") or d.get("titre") or v.get("title"),
                "youtube_url": v.get("youtube_url"), "angle": d.get("angle"),
                "accroche": (rec.get("accroche") or {}).get("texte"), "accroche_s": (rec.get("accroche") or {}).get("duree_s"),
                "duree_s": (rec.get("structure") or {}).get("duree_s"), "plans": (rec.get("structure") or {}).get("plans"),
                "published": (r or {}).get("published") or (published_moment(v).isoformat() if published_moment(v) else None),
                "views_7d": (r or {}).get("views_7d"),
                "views_latest": ((history_by_video.get(v["video_id"]) or [{}])[-1]).get("view_count"),
                "score": round((r["views_7d"] + SCORE_SMOOTHING) / (base + SCORE_SMOOTHING), 2) if r and base is not None else None,
                "retention_7d": (r or {}).get("retention_7d"),
                "apres_accroche": curve.get("apres_accroche")})
        items.sort(key=lambda x: (x["channel"] or ""))
        out.append({"reference_url": url, "versions": items, **_winner(items),
                    "published": max((x["published"] or "") for x in items)})
    out.sort(key=lambda g: g["published"], reverse=True)
    return out


def _winner(items: List[Dict]) -> Dict:
    """Who keeps people longer, and on what it is decided (None: too close / not measured yet)."""
    for key, why in (("retention_7d", "rétention 1re semaine"), ("apres_accroche", "ce que garde l'accroche")):
        measured = [x for x in items if x.get(key) is not None]
        if len(measured) >= 2:
            measured.sort(key=lambda x: x[key], reverse=True)
            gap = round(measured[0][key] - measured[1][key], 1)
            if gap < TIE_POINTS:
                return {"gagnant": None, "critere": why, "ecart": gap}
            return {"gagnant": measured[0]["video_id"], "critere": why, "ecart": gap}
    return {"gagnant": None, "critere": None, "ecart": None}


# What "Refaire ce style" carries over to new scripts: only these choices
# can be suggested (a publish weekday isn't something a remake reuses).
REMAKE_DIMENSIONS = {"script_format", "background", "music", "caption_style"}
# The full winning recipe: the remake choices + when to publish (advice only)
RECIPE_DIMENSIONS = ["script_format", "background", "music", "caption_style", "hour_slot"]
SUGGEST_MIN_SCORE = 1.5  # the headline style must clearly beat the channel's usual


def recipe(analysis: Dict) -> Dict[str, Dict]:
    """The best option of each recipe dimension — only when it's backed by
    enough videos and actually beats the channel's usual (score > 1)."""
    out = {}
    for ins in analysis.get("insights", []):
        top = ins["best"]
        if ins["dimension"] in RECIPE_DIMENSIONS and top["reliable"] and top["score"] > 1 \
                and top["score"] > ins["worst"]["score"]:
            out[ins["dimension"]] = {"dimension": ins["dimension"], "dimension_label": ins["label"],
                                     "value": top["value"], "label": top["label"], "score": top["score"],
                                     "count": top["count"], "median_retention_7d": top.get("median_retention_7d")}
    return out


def suggest(analysis: Dict) -> Optional[Dict]:
    """The Accueil's "idée de la semaine": headlined by the strongest
    well-backed winning style, with the whole winning recipe (format, décor,
    music, captions, publish hour) and the remakeable video closest to it as
    the model. None when nothing clearly stands out."""
    headline = None
    for ins in analysis.get("insights", []):
        top = ins["best"]
        if ins["dimension"] not in REMAKE_DIMENSIONS or not top["reliable"] \
                or top["score"] < SUGGEST_MIN_SCORE or top["score"] <= ins["worst"]["score"]:
            continue
        if any(r["remakeable"] and r["attrs"].get(ins["dimension"]) == top["value"] for r in analysis["videos"]) \
                and (headline is None or top["score"] > headline[1]["score"]):
            headline = (ins, top)
    if headline is None:
        return None
    ins, top = headline
    winning = recipe(analysis)

    # the model: among the remakeable videos of the headline style, the one
    # sharing the most recipe choices (the script prompt copies its
    # structure); rows are sorted by 7-day views, so ties go to the best one
    candidates = [r for r in analysis["videos"] if r["remakeable"] and r["attrs"].get(ins["dimension"]) == top["value"]]
    matches = lambda r: sum(r["attrs"].get(d) == w["value"] for d, w in winning.items())
    model = max(candidates, key=matches)  # max keeps the first of equal ones

    items = []
    for dim in RECIPE_DIMENSIONS:
        if dim in winning:
            items.append({**winning[dim], "from_model": False})
        elif dim in REMAKE_DIMENSIONS and model["attrs"].get(dim):
            # not enough evidence to pick a winner: the model's own choice
            value = model["attrs"][dim]
            items.append({"dimension": dim, "dimension_label": dict(DIMENSIONS)[dim], "value": value,
                          "label": label(dim, value), "score": None, "count": None,
                          "median_retention_7d": None, "from_model": True})
    return {"dimension": ins["dimension"], "dimension_label": ins["label"], "value": top["value"],
            "label": top["label"], "score": top["score"], "count": top["count"],
            "median_retention_7d": top.get("median_retention_7d"), "video": model,
            "recipe": items,
            # what the drafts get pre-filled with (winning choices only)
            "recipe_values": {d: w["value"] for d, w in winning.items() if d in REMAKE_DIMENSIONS}}
