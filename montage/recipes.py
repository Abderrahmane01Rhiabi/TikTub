"""
Montage recipes and settings.

A recipe is the fixed part of a style (structure, timings, volume levels);
settings are the choices a person makes on top of it (caption style, song,
song entry point, volume). Settings resolve in three layers:

    recipe defaults  <  channel profile["montage"]  <  video["montage_overrides"]

so a channel sets its look once and a single video can still differ.
"""

import os
from typing import Dict, Optional

RECIPES: Dict[str, Dict] = {
    "hopecore": {
        "label": "Hopecore — écran noir + drones",
        # image
        "frame_height": 0.90,          # video box height / frame height (references: 72-92%)
        "corner_radius": 36,
        "black_screen": {"min": 0.8, "max": 3.0},
        "drones": {"count": 2, "min_each": 1.0, "max_total": 4.0},
        # music: bed under the setup, HARD cut for the black screen only, the
        # song's chosen moment lands when the image comes back, then the same
        # level to the end (no rise on the drones: the song lives on its own)
        "music_return_ramp": 0.12,     # s, the release after the black screen
        "volumes": {"doux": -9.0, "marque": -5.0},   # music bed, dB relative to the voice
    },
}

DEFAULT_RECIPE = "hopecore"
CAPTION_STYLES = ("cascade", "accent")
VOLUMES = ("doux", "marque")
EDIT_MODES = ("simple", "montage")

DEFAULT_SETTINGS = {
    "default_mode": "simple",      # what a freshly downloaded video of the channel starts as
    "recipe": DEFAULT_RECIPE,
    "caption_style": "accent",
    "music_file": None,            # file name inside the channel's assets/music folder
    "music_entry": 34.0,           # second of the song that lands after the black screen
    "volume": "doux",
    "hook": True,
}


def clean_settings(raw: Optional[Dict]) -> Dict:
    """Keep only known keys with valid values — a hand-edited profile.json or
    an old override never reaches the renderer as garbage."""
    out = {}
    for key, value in (raw or {}).items():
        if value is None or key not in DEFAULT_SETTINGS:
            continue
        if key == "recipe" and value not in RECIPES:
            continue
        if key == "caption_style" and value not in CAPTION_STYLES:
            continue
        if key == "volume" and value not in VOLUMES:
            continue
        if key == "default_mode" and value not in EDIT_MODES:
            continue
        if key == "music_file":
            value = os.path.basename(str(value))   # a name inside the channel's music folder, never a path
            if not value:
                continue
        if key == "music_entry":
            try:
                value = max(0.0, float(value))
            except (TypeError, ValueError):
                continue
        if key == "hook":
            value = bool(value)
        out[key] = value
    return out


def channel_settings(profile: Optional[Dict]) -> Dict:
    """Recipe defaults overlaid with the channel's own montage settings."""
    return {**DEFAULT_SETTINGS, **clean_settings((profile or {}).get("montage"))}


def resolve_settings(profile: Optional[Dict], video: Optional[Dict]) -> Dict:
    """What a given video is actually rendered with."""
    return {**channel_settings(profile), **clean_settings((video or {}).get("montage_overrides"))}


def edit_mode(profile: Optional[Dict], video: Optional[Dict]) -> str:
    """'montage' or 'simple' — the video's own choice, else its channel's default."""
    mode = (video or {}).get("edit_mode")
    return mode if mode in EDIT_MODES else channel_settings(profile)["default_mode"]


def recipe(settings: Dict) -> Dict:
    return RECIPES.get(settings.get("recipe"), RECIPES[DEFAULT_RECIPE])
