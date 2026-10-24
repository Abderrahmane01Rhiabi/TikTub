"""
The voice library (Réglages → Voix) and each channel's adaptation settings.

A voice is added by its ElevenLabs id: its name, language, accent, gender,
age and official preview are fetched once (the preview mp3 is kept under
assets/voices/, so listening never spends credits). Every voice given is
kept, regional accents included — the accent is shown so the choice is
informed.

A channel's settings live in its profile.json under "adaptation"; its
language is the profile's language_hint (also what its AI titles use).
"""

import os
from typing import Dict, List, Optional

import db
from adaptation import voices as el

PREVIEWS_DIR = "assets/voices"

# "ton": a fixed tone keeps every video of the channel alike (same effects, same sounds, its own music — a
# channel's identity, the person's choice for his channels); None: the subject's tone, said by the analysis
DEFAULTS = {"voice_id": None, "music_file": None, "music_start": 0.0, "style": "classique", "ton": None}


def preview_path(voice_id: str) -> str:
    return os.path.join(PREVIEWS_DIR, f"{voice_id}.mp3")


def add_voice(voice_id: str) -> Dict:
    """Fetches the voice from ElevenLabs and keeps it (re-adding refreshes it,
    a name given by the person is kept)."""
    voice_id = voice_id.strip()
    info = el.fetch_info(voice_id)
    old = db.get_voice(voice_id)
    if old and old.get("custom_name"):
        info["custom_name"] = old["custom_name"]
    path = el.download_preview(info.get("preview_url"), preview_path(voice_id))
    info["has_preview"] = bool(path)
    db.upsert_voice(info)
    return db.get_voice(voice_id)


def rename_voice(voice_id: str, name: str) -> Optional[Dict]:
    voice = db.get_voice(voice_id)
    if not voice:
        return None
    voice["custom_name"] = name.strip()[:80] or None
    db.upsert_voice(voice)
    return db.get_voice(voice_id)


def remove_voice(voice_id: str) -> bool:
    if os.path.exists(preview_path(voice_id)):
        os.remove(preview_path(voice_id))
    return db.delete_voice(voice_id)


def display_name(voice: Dict) -> str:
    return voice.get("custom_name") or voice.get("name") or voice["voice_id"]


def channel_language(profile: Optional[Dict]) -> str:
    return ((profile or {}).get("language_hint") or "fr").split("-")[0].lower()


def channel_settings(profile: Optional[Dict]) -> Dict:
    raw = (profile or {}).get("adaptation") or {}
    out = {**DEFAULTS, "language": channel_language(profile)}
    if isinstance(raw.get("voice_id"), str) and raw["voice_id"].strip():
        out["voice_id"] = raw["voice_id"].strip()
    if isinstance(raw.get("music_file"), str) and raw["music_file"].strip():
        out["music_file"] = os.path.basename(raw["music_file"].strip())
    try:
        out["music_start"] = max(0.0, float(raw.get("music_start") or 0.0))
    except (TypeError, ValueError):
        pass
    from adaptation.render import STYLES
    if raw.get("style") in STYLES:
        out["style"] = raw["style"]
    from adaptation import tone
    out["ton"] = tone.valid(raw.get("ton"))
    return out


def clean_update(update: Dict) -> Dict:
    """Only the keys a person may set, cleaned."""
    out = {}
    if "voice_id" in update:
        v = update["voice_id"]
        out["voice_id"] = v.strip() if isinstance(v, str) and v.strip() else None
    if "music_file" in update:
        m = update["music_file"]
        out["music_file"] = os.path.basename(m.strip()) if isinstance(m, str) and m.strip() else None
    if "style" in update:
        from adaptation.render import STYLES
        if update["style"] in STYLES:
            out["style"] = update["style"]
    if "music_start" in update:
        try:
            out["music_start"] = max(0.0, float(update["music_start"]))
        except (TypeError, ValueError):
            pass
    if "ton" in update:
        from adaptation import tone
        out["ton"] = tone.valid(update["ton"])        # None: the subject's tone
    return out


def voices_for(language: str) -> List[Dict]:
    return db.list_voices(language)
