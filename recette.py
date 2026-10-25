"""
The recipe of a video: what made it, in the same shape for every kind of
video the app produces (Adaptation, Génération, Montage auto, Import) — kept
in its record so the Dashboard can set it against how the audience liked it,
and so a style that worked can be made again.

    type        adaptation | generation | montage | import
    accroche    the first words on screen / heard, and how long the hook lasts
    structure   length, number of shots, average shot length
    musique     file, where it starts, its level (or None: the original sound)
    voix        the narrator's voice id, or "son d'origine"
    style       captions, colours, frame, background
    details     what only this kind has (an Adaptation's plan by plan, a
                Montage's kept segments and drone shots…)
    reconstruite  True when rebuilt afterwards from what the record kept

The music, the backgrounds and the border images a video used are copied
once into archive/ (by content): a track deleted or replaced later is still
there to make the same video again.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from typing import Dict, List, Optional

VERSION = 1
ARCHIVE = "archive"


# ------------------------------------------------------------------ archive

def archive(path: Optional[str], kind: str) -> Optional[str]:
    """A copy of an asset kept for good (archive/<kind>/<hash8>_<name>); the
    same content is copied once. None when there is nothing to keep."""
    if not path or not os.path.isfile(path):
        return None
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    folder = os.path.join(ARCHIVE, kind)
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, f"{h.hexdigest()[:8]}_{os.path.basename(path)}")
    if not os.path.exists(dest):
        try:
            shutil.copy2(path, dest)
        except OSError:
            return None
    return dest


def duration(path: Optional[str]) -> Optional[float]:
    if not path or not os.path.exists(path):
        return None
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                             capture_output=True, text=True, timeout=30).stdout.strip()
        return round(float(out), 2)
    except (ValueError, OSError, subprocess.SubprocessError):
        return None


# ------------------------------------------------------------------ the common shape

def make(kind: str, channel: Optional[str], *, langue: Optional[str] = None, accroche: Optional[str] = None,
         accroche_s: Optional[float] = None, duree_s: Optional[float] = None, plans: Optional[int] = None,
         musique: Optional[Dict] = None, voix=None, style: Optional[Dict] = None, details: Optional[Dict] = None,
         reconstruite: bool = False) -> Dict:
    return {
        "version": VERSION, "type": kind, "chaine": channel, "langue": langue,
        "faite_le": datetime.now().isoformat(timespec="seconds"),
        "accroche": {"texte": accroche or None, "duree_s": accroche_s},
        "structure": {"duree_s": duree_s, "plans": plans,
                      "plan_moyen_s": round(duree_s / plans, 2) if duree_s and plans else None},
        "musique": musique, "voix": voix, "style": style or {}, "details": details or {},
        "reconstruite": reconstruite,
    }


def _music(path: Optional[str], start: Optional[float] = None, **extra) -> Optional[Dict]:
    if not path:
        return None
    return {"fichier": os.path.basename(path), "debut_s": start, "archive": archive(path, "musique"),
            **{k: v for k, v in extra.items() if v is not None}}


def first_sentence(text: str) -> Optional[str]:
    """The hook of a narration: its first sentence, without the voice tags."""
    clean = re.sub(r"\[[^\]]*\]|<[^>]*>", " ", text or "")
    clean = " ".join(clean.split())
    if not clean:
        return None
    m = re.match(r"(.+?[.!?…])(\s|$)", clean)
    return (m.group(1) if m else clean)[:200]


# ------------------------------------------------------------------ per kind

def from_adaptation(rec: Dict, music_path: Optional[str] = None, reconstruite: bool = False) -> Dict:
    """An Adaptation's own recipe (adaptation.pipeline._recipe) in the common shape."""
    plans = rec.get("plans") or []
    struct = rec.get("structure") or {}
    m = rec.get("musique") or {}
    musique = {k: v for k, v in m.items() if v is not None} if m.get("fichier") else None
    if musique and music_path:
        musique["archive"] = archive(music_path, "musique")
    return make("adaptation", rec.get("chaine"), langue=rec.get("langue"),
                accroche=(plans[0].get("texte") if plans else None), accroche_s=struct.get("accroche_s"),
                duree_s=struct.get("duree_s"), plans=struct.get("plans") or len(plans) or None,
                musique=musique, voix={"id": rec.get("voix")} if rec.get("voix") else None,
                style={"visuel": rec.get("style"), "sous_titres": "mot par mot, mots-clés en couleur",
                       "bandeaux": True, "fin_en_boucle": struct.get("fin_en_boucle")},
                details=rec, reconstruite=reconstruite)


def from_generation(video: Dict, length: Optional[float] = None, voice_id: Optional[str] = None,
                    music_level: Optional[float] = None, reconstruite: bool = False,
                    phrases: Optional[List[Dict]] = None) -> Dict:
    """A narrated video on a background (generative pipeline). phrases: each
    sentence as said, [{"debut", "duree", "texte"}] — the retention curve is
    read sentence by sentence against them (the words file in temp/ is
    cleaned up after publishing)."""
    phrases = phrases or []
    return make("generation", video.get("channel"),
                accroche=phrases[0]["texte"] if phrases else first_sentence(video.get("script_text") or ""),
                accroche_s=phrases[0]["duree"] if phrases else None,
                duree_s=length or duration(video.get("video_path")), plans=len(phrases) or 1,
                musique=_music(video.get("bg_music_path"), 0.0, volume=music_level, niveau="baisse sous la voix"),
                voix={"id": voice_id} if voice_id else None,
                style={"sous_titres": video.get("caption_style") or "karaoke", "couleur": video.get("caption_color"),
                       "cadre": video.get("frame_mode") or "fill", "coins_arrondis": bool(video.get("rounded_corners")),
                       "fond_video": "drones, un plan par phrase" if video.get("drones") else
                                     os.path.basename(video.get("bg_video_path") or "") or None,
                       "fond_video_archive": archive(video.get("bg_video_path"), "fonds"),
                       **({"etalonnage": video["drones"].get("look")} if video.get("drones") else {})},
                details={"format_script": video.get("script_format"), "inspire_de": video.get("inspired_by"),
                         "script": video.get("script_text"), **({"plans": phrases} if phrases else {}),
                         **({"plans_drone": video["drones"].get("plans")} if video.get("drones") else {})},
                reconstruite=reconstruite)


def from_montage(video: Dict, settings: Dict, summary: Optional[Dict], music_path: Optional[str],
                 reconstruite: bool = False) -> Dict:
    """Montage auto: a downloaded clip cut and dressed by the AI plan."""
    m = video.get("montage") or {}
    summary = summary or m.get("summary") or {}
    shots = summary.get("shots") or []
    keep = summary.get("keep") or []
    return make("montage", video.get("channel"),
                accroche=(m.get("hook") if settings.get("hook", True) else None),
                duree_s=summary.get("duration") or duration(video.get("video_path")),
                plans=(len(keep) + len(shots)) or None,
                musique=_music(music_path, settings.get("music_entry"), volume=settings.get("volume"))
                if music_path else ({"fichier": settings.get("music_file"), "debut_s": settings.get("music_entry"),
                                     "volume": settings.get("volume")} if settings.get("music_file") else None),
                voix="son d'origine",
                style={"recette": settings.get("recipe"), "sous_titres": settings.get("caption_style"),
                       "cadre": video.get("frame_mode")},
                details={"resume": (m.get("plan") or {}).get("resume"), "accroches_proposees": m.get("hooks"),
                         "passages_gardes": keep, "plans_de_coupe": m.get("brolls"), "mots_cles": m.get("keywords"),
                         "musique_rendu": summary.get("music"), "source": video.get("url")},
                reconstruite=reconstruite)


def from_import(video: Dict, notes: Optional[Dict] = None, length: Optional[float] = None,
                reconstruite: bool = False) -> Dict:
    """Import: the downloaded video placed on a background, as it is."""
    notes = notes or {}
    fond = notes.get("fond")
    return make("import", video.get("channel"), duree_s=length or duration(video.get("video_path")), plans=1,
                musique=None, voix="son d'origine",
                style={"fond": os.path.basename(fond) if fond and os.path.exists(str(fond)) else
                       (fond or video.get("background_mode")),
                       "fond_archive": archive(fond, "fonds") if fond and os.path.exists(str(fond)) else None,
                       "cadre": video.get("frame_mode"), "coins_arrondis": bool(video.get("rounded_corners"))},
                details={"source": video.get("url"), "auteur": video.get("tiktok_uploader"),
                         "musique_tiktok": video.get("tiktok_track"), "titre_original": video.get("original_title")},
                reconstruite=reconstruite)


# ------------------------------------------------------------------ old videos

def kind_of(video: Dict) -> str:
    if video.get("source") == "adaptation" or video.get("adaptation_project"):
        return "adaptation"
    if video.get("source") == "generated":
        return "generation"
    if video.get("montage") or video.get("edit_mode") == "montage":
        return "montage"
    return "import"


def rebuild(video: Dict) -> Optional[Dict]:
    """A recipe for a video made before recipes existed, from what its record
    (and an Adaptation's project) kept. Marked reconstruite; what was never
    noted stays None (a Montage's music is today's channel setting, said so)."""
    kind = kind_of(video)
    if kind == "adaptation":
        try:
            from adaptation import pipeline as ap
            p = ap.load(video.get("adaptation_project") or video.get("batch_id"))
        except Exception:
            return None
        t = next((x for x in p.get("targets") or [] if x.get("channel") == video.get("channel")), None)
        if not t or not t.get("script"):
            return None
        segs = ((t.get("final") or t.get("preview") or {}).get("summary") or {}).get("segments") or []
        rendered = {"style": t.get("style"), "plans": [{"clip": s["clip"], "debut": s["start"],
                                                        "duree": round(s["end"] - s["start"], 2)} for s in segs]}
        rec = ap._recipe(p, t, rendered)
        return from_adaptation(rec, t.get("music_path"), reconstruite=True)
    if kind == "generation":
        voice = None
        try:                            # never noted then: the channel's voice setting today
            from channel_manager import ChannelManager
            voice = ChannelManager().get_channel_profile(video.get("channel")).get("tts_voice_id")
        except Exception:
            pass
        r = from_generation(video, voice_id=voice, reconstruite=True)
        if voice:
            r["details"]["attention"] = "voix : le réglage de la chaîne aujourd'hui"
        return r
    if kind == "montage":
        try:
            from channel_manager import ChannelManager
            from montage import recipes
            cm = ChannelManager()
            settings = recipes.resolve_settings(cm.get_channel_profile(video.get("channel")), video)
            folder = cm.get_assets_dirs(video.get("channel"))["music"]
            path = os.path.join(folder, settings["music_file"]) if settings.get("music_file") else None
        except Exception:
            settings, path = {}, None
        r = from_montage(video, settings, None, path if path and os.path.exists(path) else None, reconstruite=True)
        r["details"]["attention"] = "musique et réglages : ceux de la chaîne aujourd'hui, pas forcément ceux du rendu"
        return r
    return from_import(video, reconstruite=True)


def backfill(videos: List[Dict]) -> List[Dict]:
    """Recipes for the finished videos that have none (never overwrites one)."""
    done = []
    for v in videos:
        if v.get("recette") or not (v.get("video_path") or v.get("youtube_id")):
            continue
        r = rebuild(v)
        if r:
            done.append({**v, "recette": r})
    return done


# ------------------------------------------------------------------ what uses an asset

def used_by(videos: List[Dict], filename: str) -> List[str]:
    """The videos whose recipe uses this music / background file name."""
    name = os.path.basename(filename)
    out = []
    for v in videos:
        r = v.get("recette") or {}
        blob = json.dumps({"m": r.get("musique"), "s": r.get("style")}, ensure_ascii=False)
        if name and (name in blob or name == os.path.basename(v.get("bg_music_path") or "")
                     or name == os.path.basename(v.get("bg_video_path") or "")):
            out.append(v.get("video_id"))
    return out
