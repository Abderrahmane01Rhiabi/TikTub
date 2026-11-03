"""The caption library's routes (captions/): its catalogue, the gallery's previews, each channel's choice
(Réglages → Sous-titres, used by the Adaptation, the Reprise and, with their own choice, the Montage auto and the
Génération)."""

import json
import sys
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

router = APIRouter()


def _main():
    return sys.modules["webapp.main"]


def _valid_channel_name(channel_name: str) -> str:
    return _main().checked_channel(channel_name)


ChannelName = Annotated[str, Depends(_valid_channel_name)]


@router.get("/api/captions/styles")
def caption_styles(space: Optional[str] = None, lang: Optional[str] = None):
    """Every style (space=None: the gallery, the Adaptation's own looks included), or those a space can use (in
    Arabic: only those that work in Arabic)."""
    from captions import styles as S
    items = S.for_space(space, lang) if space else list(S.STYLES.values())
    groups = []
    for st in items:
        if st.group not in groups:
            groups.append(st.group)
    return {"styles": [st.public() for st in items], "groups": groups}


@router.get("/api/captions/preview/{style_id}")
def caption_preview(style_id: str, lang: str = "fr", params: Optional[str] = None, channel: Optional[str] = None):
    """A 4-s preview of a style on the gallery's phrase (made once, then cached)."""
    from captions import render as R
    if style_id not in R.S.STYLES:
        raise HTTPException(status_code=404, detail="Style inconnu")
    try:
        raw = json.loads(params) if params else {}
    except ValueError:
        raise HTTPException(status_code=400, detail="Réglages illisibles")
    colour = R.channel_colour(_main().checked_channel(channel)) if channel else "#FF7A00"
    try:
        path = R.preview(style_id, lang, raw if isinstance(raw, dict) else {}, colour)
    except R.CaptionError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return FileResponse(path, media_type="video/mp4")


def _choice_payload(channel_name: str) -> dict:
    from captions import render as R
    profile = _main().channel_manager.get_channel_profile(channel_name) or {}
    return {**R.channel_choice(channel_name), "language": (profile.get("language_hint") or "fr").split("-")[0],
            "colour": R.channel_colour(channel_name)}


@router.get("/api/channels/{channel_name}/sous_titres")
def get_channel_captions(channel_name: ChannelName):
    return _choice_payload(channel_name)


class CaptionChoice(BaseModel):
    style: Optional[str] = None                 # None: the space's own captions (the Adaptation's look, the Reprise's)
    params: dict = Field(default_factory=dict)


@router.put("/api/channels/{channel_name}/sous_titres")
def update_channel_captions(channel_name: ChannelName, choice: CaptionChoice):
    from captions import styles as S
    profile = _main().channel_manager.get_channel_profile(channel_name)
    if choice.style is None:
        profile.pop("sous_titres", None)
    else:
        st = S.get(choice.style)
        if not st or not ({"adaptation", "reprise"} & set(st.spaces)):
            raise HTTPException(status_code=400, detail="Ce style ne peut pas servir à l'Adaptation ni à la Reprise.")
        lang = (profile.get("language_hint") or "fr").split("-")[0]
        if lang == "ar" and not st.arabic:
            raise HTTPException(status_code=400, detail="Ce style ne marche pas en arabe.")
        profile["sous_titres"] = {"style": st.id, "params": st.clean(choice.params)}
    _main().channel_manager.save_channel_profile(channel_name, profile)
    return _choice_payload(channel_name)
