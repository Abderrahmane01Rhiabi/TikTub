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
DEFAULTS = {"voice_id": None, "music_file": None, "music_start": 0.0, "style": "classique", "ton": None,
            "voice_model": None, "dialecte": None, "musique_categories": [], "musique_sans_paroles": False,
            "voix_permises": [], "voix_mode": "auto", "famille_recit": None, "styles_exclus": [],
            "cout": "economique"}
# montage pro (« Idée d'abord »): "economique" = the free local model sorts the stock before Gemini describes it, the
# AI editor thinks less (lab 2026-11-12: ~4x cheaper, judged as good on 3 projects); "qualite" = every shot described
COUTS = ("economique", "qualite")
# an Arabic channel's spoken dialect: its voice and captions in it, its title/description/tags kept in Modern
# Standard Arabic (what people type in the search) — montage pro only for now
DIALECTS = {"darija": "darija marocaine"}
# the ElevenLabs models a person may choose (Réglages, the project's Aperçu); None: eleven_v4 in every mode
VOICE_MODELS = ("eleven_v4", "eleven_v3", "eleven_multilingual_v2", "eleven_flash_v2_5")


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
    if raw.get("voice_model") in VOICE_MODELS:
        out["voice_model"] = raw["voice_model"]
    if raw.get("dialecte") in DIALECTS and out["language"] == "ar":
        out["dialecte"] = raw["dialecte"]
    from adaptation.musique_casting import CATEGORIES
    out["musique_categories"] = [c for c in raw.get("musique_categories") or [] if c in CATEGORIES]
    out["musique_sans_paroles"] = bool(raw.get("musique_sans_paroles"))
    out["voix_permises"] = [str(v) for v in raw.get("voix_permises") or [] if isinstance(v, str) and v.strip()]
    out["voix_mode"] = raw.get("voix_mode") if raw.get("voix_mode") in ("auto", "principale") else "auto"
    from adaptation import recits
    out["famille_recit"] = raw.get("famille_recit") if raw.get("famille_recit") in recits.FAMILLES \
        else recits.default_family(out["style"])
    out["styles_exclus"] = [x for x in raw.get("styles_exclus") or [] if recits.find(x)]
    out["cout"] = raw.get("cout") if raw.get("cout") in COUTS else "economique"
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
    if "voice_model" in update:
        out["voice_model"] = update["voice_model"] if update["voice_model"] in VOICE_MODELS else None
    if "dialecte" in update:
        out["dialecte"] = update["dialecte"] if update["dialecte"] in DIALECTS else None
    if "musique_categories" in update:
        from adaptation.musique_casting import CATEGORIES
        out["musique_categories"] = [c for c in dict.fromkeys(update["musique_categories"] or []) if c in CATEGORIES]
    if "musique_sans_paroles" in update:
        out["musique_sans_paroles"] = bool(update["musique_sans_paroles"])
    if "voix_permises" in update:
        out["voix_permises"] = [str(v).strip() for v in dict.fromkeys(update["voix_permises"] or []) if str(v).strip()]
    if "voix_mode" in update:
        out["voix_mode"] = update["voix_mode"] if update["voix_mode"] in ("auto", "principale") else "auto"
    if "famille_recit" in update:
        from adaptation import recits
        out["famille_recit"] = update["famille_recit"] if update["famille_recit"] in recits.FAMILLES else None
    if "styles_exclus" in update:
        from adaptation import recits
        out["styles_exclus"] = [x for x in dict.fromkeys(update["styles_exclus"] or []) if recits.find(x)]
    if "cout" in update:
        out["cout"] = update["cout"] if update["cout"] in COUTS else "economique"
    return out


def voices_for(language: str) -> List[Dict]:
    return db.list_voices(language)
