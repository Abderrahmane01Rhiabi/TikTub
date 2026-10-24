"""
Repetition guard: a video too close to what its channel already posted is
not uploaded. YouTube stops showing a channel that mass-produces the same
thing; on lungtemotivates (sublimoi) the Shorts feed went from 5 777 views in
September 2026 to 0 in October, right after the same script went out three
times (13, 25 and 26 Sept.) and one title four times, all on the same voice,
one background in 18 of 32 videos and two songs.

    block   script >= 85 % like a published one, or title >= 90 %:
            the upload is refused (an alert says which video it repeats)
    warn    script >= 60 %, title >= 70 %, the same background in 3 of the
            channel's last 10 videos, the same song in 5 of the last 10

The warnings never stop a video; they are kept on it ("repetition") with its
fingerprint, so what made each video can be compared with how it did.
No AI: plain text similarity (difflib) on normalized words.
"""

import difflib
import os
import re
import unicodedata
from typing import Dict, List, Optional

PUBLISHED = {"uploaded", "scheduled_on_youtube"}
BLOCK_SCRIPT, BLOCK_TITLE = 0.85, 0.90
WARN_SCRIPT, WARN_TITLE = 0.60, 0.70
RECENT = 10
WARN_BACKGROUND, WARN_MUSIC = 3, 5


def _norm(text: str) -> str:
    text = re.sub(r"\[[^\]]*\]|<[^>]*>", " ", text or "")          # [calm], <break time="0.5s" />
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9؀-ۿ]+", text))


def _title(video: Dict) -> str:
    return (video.get("ai_data") or {}).get("optimized_title") or video.get("title") or video.get("original_title") or ""


def _script(video: Dict) -> str:
    if video.get("script_text"):
        return video["script_text"]
    plans = ((video.get("recette") or {}).get("details") or {}).get("plans") or []
    return " ".join(p.get("texte") or "" for p in plans if isinstance(p, dict))


def fingerprint(video: Dict) -> Dict:
    """What a viewer (and YouTube) sees repeat from one video to the next."""
    rec = video.get("recette") or {}
    voice = rec.get("voix")
    music = video.get("bg_music_path") or ((rec.get("musique") or {}).get("fichier") if isinstance(rec.get("musique"), dict) else None)
    return {"type": rec.get("type") or video.get("source"),
            "format": video.get("script_format"),
            "accroche": (rec.get("accroche") or {}).get("texte"),
            "duree_s": (rec.get("structure") or {}).get("duree_s"),
            "plans": (rec.get("structure") or {}).get("plans"),
            "fond": os.path.basename(video.get("bg_video_path") or "") or None,
            "musique": os.path.basename(music or "") or None,
            "voix": voice.get("id") if isinstance(voice, dict) else voice,
            "style": (rec.get("style") or {}).get("visuel") or video.get("caption_style")}


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.split(), b.split(), autojunk=False).ratio()


def check(video: Dict, others: List[Dict]) -> Dict:
    """{"block": [...], "warn": [...], "empreinte": {...}} for `video` against
    `others` (any rows: only the same channel's published ones count)."""
    channel = video.get("channel")
    mine = [o for o in others if o.get("channel") == channel and o.get("video_id") != video.get("video_id")
            and o.get("status") in PUBLISHED and o.get("youtube_id")]
    mine.sort(key=lambda o: o.get("uploaded_at") or "", reverse=True)
    script, title = _norm(_script(video)), _norm(_title(video))
    out: Dict = {"block": [], "warn": [], "empreinte": fingerprint(video)}
    for o in mine:
        s, t = _ratio(script, _norm(_script(o))), _ratio(title, _norm(_title(o)))
        when = (o.get("youtube_published_at") or o.get("scheduled_publish_time") or o.get("uploaded_at") or "")[:10]
        what = f"« {_title(o)[:70]} » (publiée le {when})"
        if s >= BLOCK_SCRIPT:
            out["block"].append(f"script identique à {round(s * 100)} % à {what}")
        elif t >= BLOCK_TITLE:
            out["block"].append(f"titre identique à {round(t * 100)} % à {what}")
        elif s >= WARN_SCRIPT:
            out["warn"].append(f"script proche ({round(s * 100)} %) de {what}")
        elif t >= WARN_TITLE:
            out["warn"].append(f"titre proche ({round(t * 100)} %) de {what}")
    recent = [fingerprint(o) for o in mine[:RECENT]]
    fp = out["empreinte"]
    for key, limit, label in (("fond", WARN_BACKGROUND, "fond vidéo"), ("musique", WARN_MUSIC, "musique")):
        n = sum(1 for r in recent if fp[key] and r[key] == fp[key])
        if n >= limit:
            out["warn"].append(f"même {label} ({fp[key]}) que {n} des {len(recent)} dernières vidéos")
    return out


def too_close(video: Dict, others: List[Dict]) -> List[str]:
    """Why a freshly written script is too close to one of `others` (drafts
    included: two scripts of one batch must differ too) — at the warning
    level, so the AI rewrites it before anything is spent on it."""
    script, title = _norm(_script(video)), _norm(_title(video))
    out = []
    for o in others:
        if o.get("video_id") == video.get("video_id"):
            continue
        s, t = _ratio(script, _norm(_script(o))), _ratio(title, _norm(_title(o)))
        if s >= WARN_SCRIPT:
            out.append(f"script trop proche ({round(s * 100)} %) de « {_title(o)[:70]} »")
        elif t >= WARN_TITLE:
            out.append(f"titre trop proche ({round(t * 100)} %) de « {_title(o)[:70]} »")
    return out


def blocking_message(result: Dict) -> Optional[str]:
    if not result["block"]:
        return None
    return ("Doublon, non publiée : " + " ; ".join(result["block"][:2]) +
            ". YouTube cesse de montrer une chaîne qui répète ses vidéos : change le script ou supprime cette vidéo.")
