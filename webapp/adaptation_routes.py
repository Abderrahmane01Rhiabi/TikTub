"""
The Adaptation's routes (see ADAPTATION.md), moved out of main.py as they
were — same code, same order of the routes (main.py includes this router
where they stood).

What belongs to main.py (channel_manager, that tests replace on the fly; the
batch processor; a few helpers) is read from it at the time of each call,
never copied at import: _main().
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path
from typing import Annotated, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

router = APIRouter()


def _main():
    return sys.modules["webapp.main"]


# Channel names in these routes go through the same check as webapp.main's
# (ChannelManager.validate_channel_name): allowed format, existing channel.
def _valid_channel_name(channel_name: str) -> str:
    return _main().checked_channel(channel_name)


def _valid_target_channel(channel: str) -> str:
    return _main().checked_channel(channel)


ChannelName = Annotated[str, Depends(_valid_channel_name)]
TargetChannel = Annotated[str, Depends(_valid_target_channel)]


def _adaptation_channel_payload(channel_name: str) -> dict:
    from adaptation import settings as ad
    profile = _main().channel_manager.get_channel_profile(channel_name)
    s = ad.channel_settings(profile)
    music_dir = Path(_main().channel_manager.get_assets_dirs(channel_name)["music"])
    music = sorted(p.name for p in music_dir.iterdir() if p.suffix.lower() in _main().MUSIC_EXTENSIONS) \
        if music_dir.exists() else []
    from adaptation.render import STYLES
    return {"settings": s, "music_files": music, "voices": [_main()._serialize_voice(v) for v in ad.voices_for(s["language"])],
            "voice_models": list(ad.VOICE_MODELS),
            "styles": [{"name": k, "label": v["label"]} for k, v in STYLES.items()]}


@router.get("/api/adaptation/styles/{name}/preview")
def adaptation_style_preview(name: str, lang: str = "fr"):
    """A banner and a caption line drawn in one of the channel styles."""
    from adaptation import render, langs
    if name not in render.STYLES:
        raise HTTPException(status_code=404, detail="Style inconnu")
    out = os.path.join("temp", "style_previews", f"{name}_{lang}.jpg")
    if not os.path.exists(out):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        render.style_preview(name, langs.lang(lang), out)
    return FileResponse(out, media_type="image/jpeg")


@router.get("/api/channels/{channel_name}/adaptation")
def get_channel_adaptation(channel_name: ChannelName):
    return _adaptation_channel_payload(channel_name)


class ChannelAdaptationUpdate(BaseModel):
    language: Optional[str] = None
    settings: dict = Field(default_factory=dict)


@router.put("/api/channels/{channel_name}/adaptation")
def update_channel_adaptation(channel_name: ChannelName, update: ChannelAdaptationUpdate):
    from adaptation import settings as ad
    from adaptation.langs import LANGS
    profile = _main().channel_manager.get_channel_profile(channel_name)
    if update.language is not None:
        if update.language not in LANGS:
            raise HTTPException(status_code=400, detail=f"Langue : {', '.join(LANGS)}")
        profile["language_hint"] = update.language      # also the language of its AI titles
    profile["adaptation"] = {**(profile.get("adaptation") or {}), **ad.clean_update(update.settings)}
    _main().channel_manager.save_channel_profile(channel_name, profile)
    return _adaptation_channel_payload(channel_name)


# ---------------------------------------------------------------------------
# Adaptation projects — the "Adaptation" space: Modèle → Sources → Script
# (mandatory review) → Aperçu → Rendu, then the videos join Publication
# ---------------------------------------------------------------------------

def _adaptation_job(pid: str) -> str:
    return f"adapt:{pid}"


def _start_adaptation_step(pid: str, step: str, only: Optional[str] = None):
    """Runs one background step of a project, with real progress for the UI."""
    import progress
    from adaptation import pipeline as ap
    key = _adaptation_job(pid)
    progress.start(key, kind="adaptation", phase=step)
    runner = ap.runner_for(pid, step)

    def run():
        try:
            seen = {"f": 0.0}            # never backwards: sources handled at once each report their own share

            def report(phase, f):
                seen["f"] = max(seen["f"], f)
                progress.update(key, seen["f"], phase=phase)
            from gemini_ai_generator import usage_context
            with usage_context(projet=pid):          # each AI call of the step noted with its project
                if step in ("voicing", "scripting") and only:
                    runner(pid, report, only=only)
                else:
                    runner(pid, report)
            progress.finish(key)
        except Exception as e:
            progress.finish(key, error=str(e))
    threading.Thread(target=run, daemon=True).start()


def ap_wanting(p: dict):
    from adaptation import pipeline as ap
    return ap.wanting(p)


def _serialize_adaptation(p: dict, full: bool = True) -> dict:
    import progress
    from adaptation import langs
    job = progress.get(_adaptation_job(p["project_id"])) or {}
    base = {k: p.get(k) for k in ("project_id", "status", "reference_url", "credits", "error", "failed_step",
                                   "created_at", "updated_at")}
    base["mode"] = p.get("mode") or "sources"
    base["idee"] = p.get("idee")
    base["annotations_reviewed"] = bool(p.get("annotations_reviewed"))
    base["fetch_note"] = p.get("fetch_note")
    from adaptation import tone as _tone_mod
    base["ton"] = _tone_mod.of(p.get("reference")) if (p.get("reference") or {}).get("ton") else None
    base["tons"] = _tone_mod.choices()
    from adaptation import pipeline as _ap
    fixed = {t["channel"]: _ap._channel_tone(t) for t in p.get("targets") or []}
    base["ton_chaine"] = next(iter(fixed.values())) if fixed and all(fixed.values()) else None   # every version keeps its channel's
    try:
        base["wanting"] = [k + 1 for k in ap_wanting(p)] if p.get("status") in ("images_review", "sources_search") else []
    except Exception:
        base["wanting"] = []
    base["group"] = p.get("group")
    base["angle"] = p.get("angle")
    base["angles"] = p.get("angles") or []
    if full and p.get("group"):
        from adaptation import pipeline as _ap
        members = sorted([p] + _ap.group_of(p), key=lambda x: x.get("created_at") or "")
        base["group_channels"] = [t["channel"] for x in members for t in x["targets"]]
        base["group_members"] = [{"project_id": x["project_id"], "status": x["status"],
                                  "channels": [t["channel"] for t in x["targets"]],
                                  "angle": (x.get("angle") or {}).get("titre")} for x in members]
    base["subject"] = (p.get("reference") or {}).get("sujet")
    base["progress"] = {"fraction": job.get("fraction"), "phase": job.get("phase")} if job and not job.get("done") else None
    targets = []
    for t in p.get("targets", []):
        prev, fin = t.get("preview") or {}, t.get("final") or {}
        targets.append({
            "channel": t["channel"], "language": t["language"], "language_label": langs.lang(t["language"])["label"],
            "rtl": langs.lang(t["language"])["rtl"], "voice_id": t["voice_id"], "approved": t.get("approved"),
            "validated": t.get("validated"), "video_id": t.get("video_id"), "script": t.get("script"),
            "problems": t.get("problems") or [], "music": os.path.basename(t["music_path"]) if t.get("music_path") else None,
            "angle": t.get("angle"), "accords": t.get("accords"),
            "preview_url": _main().video_media_url({"video_path": prev["path"]}) if prev.get("path") and os.path.exists(prev["path"]) else None,
            "checks": prev.get("checks"), "final_checks": fin.get("checks"),
            "duration": (prev.get("summary") or {}).get("duration") or prev.get("duree"),
            "voice_model": t.get("voice_model"),
        })
    base["targets"] = targets
    if p.get("mode") == "reprise":
        base["reprise"] = _serialize_reprise(p, targets)
    if p.get("mode") == "discours":
        base["discours"] = _serialize_discours(p, targets, full)
        d = p.get("discours") or {}
        titre = (d.get("choix") or {}).get("titre")
        base["subject"] = " — ".join(x for x in (d.get("orateur"), titre) if x) or d.get("titre_video") or None
    if full:
        ref = p.get("reference") or {}
        base["reference"] = {k: ref.get(k) for k in ("sujet", "question", "credits", "faits_douteux", "duree_s",
                                                     "origine", "faits_sources", "suggestions_youtube")}
        base["reference"]["plans"] = [{k: x.get(k) for k in ("debut", "fin", "visuel")}
                                      for x in ref.get("plans") or [] if isinstance(x, dict)]
        base["clips"] = [{**{k: c.get(k) for k in ("id", "source", "start", "end", "impact", "desc", "camera", "usable",
                                                  "why_not", "low_res", "audio_ok", "marks", "extrait", "scene", "forced", "note", "absent", "action", "w", "h", "texte_efface")},
                          "thumb_url": f"/api/adaptations/{p['project_id']}/clips/{c['id']}/thumb"}
                         for c in (p.get("clips") or {}).values()]
        base["sources"] = p.get("sources") or []
        base["source_urls"] = p.get("source_urls") or []
        base["pending_excerpts"] = p.get("pending_excerpts") or []
        sb = p.get("storyboard")
        base["storyboard"] = {"plans": [{k: pl.get(k) for k in ("role", "image", "plans_modele", "duree", "retire", "adapte", "annotation")}
                                        for pl in sb["plans"]],
                              "corrections": sb.get("corrections") or []} if sb else None
        base["picks"] = p.get("picks")
        base["suggestions"] = p.get("suggestions")
    return base


def _serialize_reprise(p: dict, targets: list) -> dict:
    from adaptation import reprise_pipeline as rp, settings as st
    r = p.get("reprise") or {}
    pid = p["project_id"]
    for out, t in zip(targets, p.get("targets") or []):
        out["son"] = rp.son_for(p, t)
        out["voice_model_used"] = rp.model_for(t)
    sc = r.get("script") or {}
    mus = r.get("musique") or {}
    return {
        "son": r.get("son"), "volume_db": r.get("volume_db"), "sons": ["sa_musique", "notre_musique", "intelligente", "sans_musique"],
        "smart_channels": list(rp.SMART_CHANNELS), "voice_models": list(st.VOICE_MODELS),
        "elements": [{"index": i, **{k: e.get(k) for k in ("type", "description", "action", "raison", "debut", "fin")}}
                     for i, e in enumerate(r.get("elements") or [])],
        "original_url": f"/api/adaptations/{pid}/reprise/video/original" if r.get("video") else None,
        "propre_url": f"/api/adaptations/{pid}/reprise/video/propre" if r.get("clean") else None,
        "nettoyage": r.get("nettoyage"),
        "script": {"genre": sc.get("genre"), "reordonne": sc.get("reordonne"), "pourquoi": sc.get("pourquoi"),
                   "titre": sc.get("titre"), "youtube": sc.get("youtube") or {}, "parties": sc.get("parties") or []} if sc else None,
        "musique": {k: mus.get(k) for k in ("titre", "partie", "comment", "pourquoi_chanson", "pourquoi_partie", "attention")}
        if mus else None,
        "credit": rp.credit(p) if r.get("video") else "",
    }


def _serialize_discours(p: dict, targets: list, full: bool = True) -> dict:
    from adaptation import discours as D, discours_pipeline as dp
    d = p.get("discours") or {}
    pid = p["project_id"]
    for out, t in zip(targets, p.get("targets") or []):
        out["son"] = dp.son_for(p, t)
        out["reglages"] = dp.settings_for(p, t)
        out["films"] = (t.get("discours") or {}).get("films") is True
    out = {"son": d.get("son"), "chanson": d.get("chanson"), "sons": list(dp.SONS), "duree": d.get("duree"),
           "orateur": d.get("orateur") or "", "langue": d.get("langue"), "titre_video": d.get("titre_video") or "",
           "films": dp.films_ok(p) if p.get("targets") else False, "reglages": d.get("reglages") or {},
           "defauts": D.DEFAULTS, "cadres": list(D.FRAMES), "fonds": list(D.FONDS), "etalonnages": list(D.GRADES),
           "musique": {k: (d.get("musique") or {}).get(k) for k in ("titre", "fichier", "pourquoi_chanson")}
           if d.get("musique") else None,
           "video_url": f"/api/adaptations/{pid}/discours/video" if d.get("video") else None,
           "passage_url": f"/api/adaptations/{pid}/discours/passage" if d.get("segment") else None}
    if not full:
        return out
    words = d.get("mots") or []
    out["passages"] = [{**x, "texte": " ".join(w[0] for w in words[x["i0"]:x["i1"] + 1])} for x in d.get("passages") or []]
    c = d.get("choix")
    if c:
        lo, hi = max(0, c["i0"] - 40), min(len(words), c["i1"] + 41)     # the words around it, to move its ends
        out["choix"] = {**c, "autour": {"debut": lo, "mots": [w[0] for w in words[lo:hi]]}}
    local, moments = d.get("local") or [], d.get("moments") or []
    taken = {(m.get("clip") or {}).get("stock"): i for i, m in enumerate(moments)}
    out["moments"] = [{"index": i, "mot": m.get("mot"), "temps": m.get("temps"), "scene": m.get("scene"),
                       "action": m.get("action"), "journal": m.get("journal") or [],
                       "type": m.get("type"), "ambiance": m.get("ambiance") or "",
                       "mot_i": min(range(len(local)), key=lambda k: abs(local[k][1] - float(m.get("temps") or 0)))
                       if local else None,
                       "propositions": [{k: c.get(k) for k in ("stock", "tags", "page", "image", "apercu")}
                                        | {"pris": taken.get(c["stock"])} for c in m.get("propositions") or []],
                       "clip": {k: (m.get("clip") or {}).get(k) for k in ("url", "titre", "niveau", "film", "a_la_main",
                                                                           "stock")}
                       if m.get("clip") else None,
                       "clip_url": f"/api/adaptations/{pid}/discours/moments/{i}/clip" if m.get("clip") else None}
                      for i, m in enumerate(moments)]
    try:
        out["frise"] = dp.frise(p)
    except Exception:                                # a timeline that cannot be drawn never hides the screen
        out["frise"] = None
    tr = d.get("traduction") or {}
    out["traduction"] = {"phrases": tr.get("phrases") or [],
                         "youtube": {c: (x or {}).get("youtube") for c, x in (tr.get("langues") or {}).items()}} if tr else None
    out["mots_forts"] = d.get("mots_forts") or []
    out["mot_fort"] = d.get("mot_fort")
    return out


def _adaptation_or_404(pid: str) -> dict:
    import db as _db
    p = _db.get_adaptation(pid)
    if not p:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    return p


def _adaptation_call(fn, *args):
    from adaptation.pipeline import PipelineError
    from gemini_ai_generator import usage_context
    pid = args[0] if args and isinstance(args[0], str) and args[0].startswith("ad_") else None
    try:
        with usage_context(projet=pid):              # a chat, a link checked by hand…: noted with its project
            return fn(*args)
    except PipelineError as e:
        raise HTTPException(status_code=400, detail=str(e))


class AdaptationCreate(BaseModel):
    reference_url: str = ""
    idea: str = ""                      # « Idée d'abord »: no model Short
    source_urls: list = Field(default_factory=list)
    channels: list
    mode: str = "sources"
    versions: bool = False
    son: str = "notre_musique"          # Reprise: sa_musique | notre_musique | intelligente | sans_musique
    volume_db: Optional[float] = None   # Reprise: the music this many dB under the voice
    chanson: Optional[str] = None       # Discours, son "choisie": a shared song (assets/musiques)
    duree: int = 45                     # Discours: the Short's length aimed at (30 / 45 / 60 s)


@router.post("/api/adaptations")
def create_adaptation(req: AdaptationCreate):
    from adaptation import pipeline as ap
    for ch in req.channels:
        _main().checked_channel(ch)
    targets = [{"channel": ch, "profile": _main().channel_manager.get_channel_profile(ch),
                "music_dir": _main().channel_manager.get_assets_dirs(ch)["music"]} for ch in req.channels]
    mode = "script" if req.mode == "idee" else req.mode
    p = _adaptation_call(ap.create, req.reference_url, req.source_urls, targets, mode, req.versions, None, None, req.idea,
                         req.son, req.volume_db, req.chanson, req.duree)
    _start_adaptation_step(p["project_id"], "analysing")
    return _serialize_adaptation(p)


def _remake_source(video_id: str):
    """The published Adaptation to copy the style of, and its versions on other channels."""
    import db as _db
    video = _db.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Vidéo introuvable.")
    others = [v for v in _main().get_batch_processor().url_manager.list_videos()
              if v["video_id"] != video_id and video.get("url") and v.get("url") == video.get("url")
              and v.get("channel") != video.get("channel") and (v.get("recette") or {}).get("type") == "adaptation"]
    return video, others


@router.get("/api/videos/{video_id}/remake_style")
def remake_style(video_id: str):
    """What "Refaire ce style" would reuse, said before anything is made."""
    from adaptation import pipeline as ap
    import performance
    video, others = _remake_source(video_id)
    st = _adaptation_call(ap.style_to_remake, video, others)
    for ch, s in st["par_chaine"].items():
        s["voix_nom"] = performance._voice_name(s["voice_id"]) if s.get("voice_id") else None
        s["chaine_nom"] = (_main().channel_manager.get_channel_profile(ch) or {}).get("display_name") or ch
    return st


class AdaptationRemake(BaseModel):
    video_id: str
    reference_url: str


@router.post("/api/adaptations/remake")
def remake_adaptation(req: AdaptationRemake):
    """A new Adaptation of another model Short, made the way a video that worked was."""
    from adaptation import pipeline as ap
    video, others = _remake_source(req.video_id)
    st = _adaptation_call(ap.style_to_remake, video, others)
    targets = [{"channel": ch, "profile": _main().channel_manager.get_channel_profile(ch),
                "music_dir": _main().channel_manager.get_assets_dirs(ch)["music"]} for ch in st["channels"]]
    p = _adaptation_call(ap.create, req.reference_url, [], targets, st["mode"], st["versions"],
                         st["par_chaine"], req.video_id)
    _start_adaptation_step(p["project_id"], "analysing")
    return _serialize_adaptation(p)


@router.get("/api/adaptations")
def list_adaptations():
    import db as _db
    return [_serialize_adaptation(p, full=False) for p in _db.list_adaptations()]


@router.get("/api/adaptations/{pid}")
def get_adaptation(pid: str):
    return _serialize_adaptation(_adaptation_or_404(pid))


@router.delete("/api/adaptations/{pid}")
def delete_adaptation(pid: str):
    import db as _db
    from adaptation import pipeline as ap
    p = _adaptation_or_404(pid)
    if p["status"] in ap.BUSY:
        raise HTTPException(status_code=400, detail="Une étape tourne encore : attends sa fin.")
    shutil.rmtree(ap.project_dir(pid), ignore_errors=True)
    _db.delete_adaptation(pid)
    return {"deleted": True}


@router.get("/api/adaptations/{pid}/frames/{name}")
def adaptation_frame(pid: str, name: str):
    """A clean picture of one of the reference Short's shots (for the manual image search)."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    path = os.path.join(ap.project_dir(pid), "finder", os.path.basename(name))
    if not name.endswith(".jpg") or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Image introuvable")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/api/adaptations/{pid}/clips/{cid}/thumb")
def adaptation_clip_thumb(pid: str, cid: str):
    from adaptation import pipeline as ap, sources
    p = _adaptation_or_404(pid)
    c = (p.get("clips") or {}).get(cid)
    if not c:
        raise HTTPException(status_code=404, detail="Clip introuvable")
    out = os.path.join(ap.project_dir(pid), "thumbs", f"{cid}.jpg")
    if not os.path.exists(out):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        sources.clip_still(c, out)
    if not os.path.exists(out):
        raise HTTPException(status_code=404, detail="Miniature indisponible")
    return FileResponse(out, media_type="image/jpeg")


@router.get("/api/adaptations/{pid}/clips/{cid}/video")
def adaptation_clip_video(pid: str, cid: str):
    """The clip as a small video, cleaned like the render (made once, then kept)."""
    from adaptation import pipeline as ap, sources
    p = _adaptation_or_404(pid)
    c = (p.get("clips") or {}).get(cid)
    if not c:
        raise HTTPException(status_code=404, detail="Clip introuvable")
    key = f"{cid}_{c['start']:.2f}_{c['end']:.2f}".replace(".", "-")
    out = os.path.join(ap.project_dir(pid), "previews", f"{key}.mp4")
    if not os.path.exists(out):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        sources.clip_preview(c, out)
    if not os.path.exists(out):
        raise HTTPException(status_code=404, detail="Aperçu indisponible")
    return FileResponse(out, media_type="video/mp4")


class AdaptationSources(BaseModel):
    usable: dict = Field(default_factory=dict)
    credits: Optional[str] = None


@router.patch("/api/adaptations/{pid}/sources")
def update_adaptation_sources(pid: str, req: AdaptationSources):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.set_sources, pid, req.usable, req.credits))


class AdaptationCredits(BaseModel):
    credits: str


@router.patch("/api/adaptations/{pid}/credits")
def update_adaptation_credits(pid: str, req: AdaptationCredits):
    """The credits line, corrected by hand until the final render."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.set_credits, pid, req.credits))


class AdaptationAddSources(BaseModel):
    urls: list


@router.post("/api/adaptations/{pid}/sources/add")
def add_adaptation_sources(pid: str, req: AdaptationAddSources):
    """Sources picked among the suggestions (or pasted), analysed on top of the others."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    p = _adaptation_call(ap.add_sources, pid, [str(u) for u in req.urls])
    _start_adaptation_step(pid, "analysing")
    return _serialize_adaptation(p)


class AdaptationCheck(BaseModel):
    url: str


@router.post("/api/adaptations/{pid}/suggestions/check")
def check_adaptation_candidate(pid: str, req: AdaptationCheck):
    """Gemini watches one suggested video against every scene (30 s to 1 min)."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.check_candidate, pid, req.url))


@router.post("/api/adaptations/{pid}/suggestions/own")
def check_adaptation_own_links(pid: str, req: AdaptationAddSources):
    """Your own links, judged by Gemini like the suggestions (1 to 2 min)."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.check_own, pid, [str(u) for u in req.urls]))


class AdaptationAngle(BaseModel):
    index: Optional[int] = None
    custom: Optional[str] = None


@router.post("/api/adaptations/{pid}/angle")
def change_adaptation_angle(pid: str, req: AdaptationAngle):
    """Another angle: the storyboard is written again (about a minute)."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    p = _adaptation_call(ap.change_angle, pid, req.index, req.custom)
    _start_adaptation_step(pid, "analysing")
    return _serialize_adaptation(p)


class AdaptationNewVersion(BaseModel):
    channel: str


@router.post("/api/adaptations/{pid}/targets/{channel}/angle")
def change_adaptation_target_angle(pid: str, channel: TargetChannel, req: AdaptationAngle):
    """Sources d'abord with versions: another angle for one channel's script (about a minute)."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    p = _adaptation_call(ap.change_target_angle, pid, channel, req.index, req.custom)
    _start_adaptation_step(pid, "scripting", only=channel)
    return _serialize_adaptation(p)


@router.post("/api/adaptations/{pid}/new-version")
def new_adaptation_version(pid: str, req: AdaptationNewVersion):
    """Another channel's version of the same Short, with a new angle."""
    from adaptation import pipeline as ap
    _main().checked_channel(req.channel)
    _adaptation_or_404(pid)
    ch = {"channel": req.channel, "profile": _main().channel_manager.get_channel_profile(req.channel),
          "music_dir": _main().channel_manager.get_assets_dirs(req.channel)["music"]}
    p = _adaptation_call(ap.new_version, pid, ch)
    _start_adaptation_step(p["project_id"], "analysing")
    return _serialize_adaptation(p)


class AdaptationPlan(BaseModel):
    plan: dict


class AdaptationPlanRevise(BaseModel):
    request: str


@router.put("/api/adaptations/{pid}/targets/{channel}/plan")
def edit_adaptation_plan(pid: str, channel: TargetChannel, req: AdaptationPlan):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.edit_plan, pid, channel, req.plan))


@router.post("/api/adaptations/{pid}/targets/{channel}/plan/revise")
def revise_adaptation_plan(pid: str, channel: TargetChannel, req: AdaptationPlanRevise):
    from adaptation import pipeline as ap
    from adaptation.script import ScriptError
    _adaptation_or_404(pid)
    if not req.request.strip():
        raise HTTPException(status_code=400, detail="Écris ce qu'il faut changer.")
    try:
        return _serialize_adaptation(_adaptation_call(ap.revise_plan, pid, channel, req.request.strip()))
    except ScriptError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/api/adaptations/{pid}/targets/{channel}/plan/approve")
def approve_adaptation_plan(pid: str, channel: TargetChannel):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.approve_plan, pid, channel))


@router.post("/api/adaptations/{pid}/images")
def start_adaptation_images(pid: str):
    """Script d'abord: search the footage for every plan of the storyboard (3 to 6 min)."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    p = _adaptation_call(ap.start_images, pid)
    _start_adaptation_step(pid, "searching")
    return _serialize_adaptation(p)


@router.post("/api/adaptations/{pid}/images/more")
def more_adaptation_images(pid: str):
    """Search again, by action, for the plans still without footage (2 to 5 min)."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    p = _adaptation_call(ap.start_more_images, pid)
    _start_adaptation_step(pid, "searching")
    return _serialize_adaptation(p)


class AdaptationPick(BaseModel):
    url: Optional[str] = None
    debut: float = 0.0
    fin: Optional[float] = None


@router.put("/api/adaptations/{pid}/picks/{plan}")
def choose_adaptation_pick(pid: str, plan: int, req: AdaptationPick):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.choose_pick, pid, plan, req.url, req.debut, req.fin))


class AdaptationSkip(BaseModel):
    skip: bool = True


@router.post("/api/adaptations/{pid}/plans/{plan}/skip")
def skip_adaptation_plan(pid: str, plan: int, req: AdaptationSkip):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.skip_plan, pid, plan, req.skip))


class AdaptationLink(BaseModel):
    url: str


@router.post("/api/adaptations/{pid}/plans/{plan}/link")
def check_adaptation_plan_link(pid: str, plan: int, req: AdaptationLink):
    """Your link for one plan, judged by Gemini (15 s to 2 min); it becomes the pick if it fits."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.check_plan_link, pid, plan, req.url))


async def _dropped(file: UploadFile, tmp: str) -> str:
    from adaptation import sources
    ext = Path(file.filename or "").suffix.lower()
    if ext not in sources.VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Format non pris en charge ({ext or 'sans extension'}) — dépose un fichier .mp4, .mov, .m4v, .webm ou .mkv.")
    src = os.path.join(tmp, "in" + ext)
    with open(src, "wb") as out:
        shutil.copyfileobj(file.file, out)
    return src


@router.get("/api/adaptations/{pid}/fichiers/{name}")
def adaptation_dropped_file(pid: str, name: str):
    """A video dropped by hand, to watch it in the browser."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    folder = Path(ap.project_dir(pid)) / "fichiers"
    path = folder / Path(name).name
    if path.suffix != ".mp4" or not path.is_file():
        raise HTTPException(status_code=404, detail="Fichier introuvable.")
    return FileResponse(path, media_type="video/mp4")


@router.post("/api/adaptations/{pid}/plans/{plan}/file")
async def file_for_adaptation_plan(pid: str, plan: int, file: UploadFile = File(...), credit: str = Form("")):
    """"Déposer un fichier pour ce plan": a video saved by hand, judged by Gemini (15 s to 2 min)."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    with tempfile.TemporaryDirectory() as tmp:
        src = await _dropped(file, tmp)
        p = await asyncio.to_thread(_adaptation_call, ap.file_for_plan, pid, plan, src, Path(file.filename).name, credit)
    return _serialize_adaptation(p)


@router.post("/api/adaptations/{pid}/sources/file")
async def file_as_adaptation_source(pid: str, file: UploadFile = File(...), credit: str = Form("")):
    """Sources d'abord: a video saved by hand, analysed with the other sources."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    with tempfile.TemporaryDirectory() as tmp:
        src = await _dropped(file, tmp)
        p = await asyncio.to_thread(_adaptation_call, ap.file_as_source, pid, src, Path(file.filename).name, credit)
    _start_adaptation_step(pid, "analysing")
    return _serialize_adaptation(p)


@router.post("/api/adaptations/{pid}/plans/{plan}/adapt")
def adapt_adaptation_plan(pid: str, plan: int):
    """A plan with no video: rewritten around an image already found."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.adapt_plan, pid, plan))


@router.post("/api/adaptations/{pid}/back-to-script")
def back_to_adaptation_script(pid: str):
    """From the previews back to the scripts (a clip or a sentence to change)."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.back_to_script, pid))


@router.post("/api/adaptations/{pid}/back-to-images")
def back_to_adaptation_images(pid: str):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.back_to_images, pid))


class AdaptationExcerpt(BaseModel):
    ref: Optional[int] = None


@router.post("/api/adaptations/{pid}/plans/{plan}/excerpt")
def excerpt_for_adaptation_plan(pid: str, plan: int, req: Optional[AdaptationExcerpt] = None):
    """Last resort: a few seconds of the reference Short for a plan nobody filmed (ref: which of its shots)."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.use_excerpt_for_plan, pid, plan, (req.ref if req else None)))


@router.post("/api/adaptations/{pid}/scenes/{scene}/excerpt")
def excerpt_for_adaptation_scene(pid: str, scene: int):
    """Last resort (Sources d'abord): a clip of the reference Short for a scene nobody filmed."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.add_excerpt_source, pid, scene))


@router.post("/api/adaptations/{pid}/clips/{cid}/force")
def force_adaptation_clip(pid: str, cid: str):
    """Use a clip the check refused (you have the last word)."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.force_clip, pid, cid))


@router.post("/api/adaptations/{pid}/targets/{channel}/passages/{k}/keep")
def keep_adaptation_passage(pid: str, channel: TargetChannel, k: int):
    """The check says the sentence and its picture don't match: keep it anyway."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.keep_passage, pid, channel, k))


@router.post("/api/adaptations/{pid}/targets/{channel}/passages/{k}/clip")
def use_adaptation_clip_proposal(pid: str, channel: TargetChannel, k: int):
    """Take the other clip the check found for this sentence (the sentence stays)."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.use_clip_proposal, pid, channel, k))


@router.post("/api/adaptations/{pid}/targets/{channel}/passages/{k}/proposal")
def use_adaptation_proposal(pid: str, channel: TargetChannel, k: int):
    """Take the sentence the check wrote for what the clip shows."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.use_proposal, pid, channel, k))


@router.post("/api/adaptations/{pid}/fetch")
def start_adaptation_fetch(pid: str):
    """Download only the picked moments and make one clip per plan (1 to 4 min)."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    p = _adaptation_call(ap.start_fetch, pid)
    _start_adaptation_step(pid, "fetching")
    return _serialize_adaptation(p)


@router.post("/api/adaptations/{pid}/scripts")
def start_adaptation_scripts(pid: str):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    p = _adaptation_call(ap.start_scripts, pid)
    _start_adaptation_step(pid, "scripting")
    return _serialize_adaptation(p)


class AdaptationScript(BaseModel):
    script: dict


@router.put("/api/adaptations/{pid}/targets/{channel}/script")
def edit_adaptation_script(pid: str, channel: TargetChannel, req: AdaptationScript):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.edit_script, pid, channel, req.script))


class AdaptationRevise(BaseModel):
    request: str


@router.post("/api/adaptations/{pid}/targets/{channel}/revise")
def revise_adaptation_script(pid: str, channel: TargetChannel, req: AdaptationRevise):
    from adaptation import pipeline as ap
    from adaptation.script import ScriptError
    _adaptation_or_404(pid)
    if not req.request.strip():
        raise HTTPException(status_code=400, detail="Écris ce qu'il faut changer.")
    try:
        return _serialize_adaptation(_adaptation_call(ap.revise_script, pid, channel, req.request.strip()))
    except ScriptError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/api/adaptations/{pid}/targets/{channel}/approve")
def approve_adaptation_script(pid: str, channel: TargetChannel, force: bool = False):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.approve_script, pid, channel, force))


@router.post("/api/adaptations/{pid}/voices")
def start_adaptation_voices(pid: str):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    p = _adaptation_call(ap.start_voices, pid)
    _start_adaptation_step(pid, "voicing")
    return _serialize_adaptation(p)


class AdaptationVoice(BaseModel):
    voice_id: str = ""
    model: Optional[str] = None         # Reprise: the ElevenLabs model (adaptation/settings.VOICE_MODELS)


@router.patch("/api/adaptations/{pid}/targets/{channel}/voice")
def change_adaptation_voice(pid: str, channel: TargetChannel, req: AdaptationVoice):
    from adaptation import pipeline as ap
    p = _adaptation_or_404(pid)
    if p.get("mode") == "reprise":
        from adaptation import reprise_pipeline as rp
        p = _adaptation_call(rp.change_voice, pid, channel, req.voice_id or None, req.model)
    else:
        p = _adaptation_call(ap.change_voice, pid, channel, req.voice_id)
    _start_adaptation_step(pid, "voicing", only=channel)
    return _serialize_adaptation(p)


@router.post("/api/adaptations/{pid}/targets/{channel}/validate")
def validate_adaptation_preview(pid: str, channel: TargetChannel):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.validate_preview, pid, channel))


@router.post("/api/adaptations/{pid}/render")
def start_adaptation_render(pid: str):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    p = _adaptation_call(ap.start_render, pid)
    _start_adaptation_step(pid, "rendering")
    return _serialize_adaptation(p)


class AdaptationTone(BaseModel):
    ton: str


@router.patch("/api/adaptations/{pid}/ton")
def set_adaptation_tone(pid: str, req: AdaptationTone):
    """The subject's tone, changed by hand (every version): music, effects and sounds follow it."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.set_tone, pid, req.ton))


@router.post("/api/adaptations/{pid}/retry")
def retry_adaptation(pid: str):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    step = _adaptation_call(ap.retry, pid)
    _start_adaptation_step(pid, step)
    return _serialize_adaptation(_adaptation_or_404(pid))


# ---------------------------------------------------------------------------
# Reprise (a friend's Short taken again): the cleaning review, its script, its sound
# ---------------------------------------------------------------------------

def _reprise_or_404(pid: str) -> dict:
    p = _adaptation_or_404(pid)
    if p.get("mode") != "reprise":
        raise HTTPException(status_code=400, detail="Ce projet n'est pas une Reprise.")
    return p


class RepriseElement(BaseModel):
    action: str                         # garder | cacher


@router.post("/api/adaptations/{pid}/reprise/elements/{index}")
def reprise_element(pid: str, index: int, req: RepriseElement):
    from adaptation import reprise_pipeline as rp
    _reprise_or_404(pid)
    return _serialize_adaptation(_adaptation_call(rp.set_element, pid, index, req.action))


@router.post("/api/adaptations/{pid}/reprise/clean-again")
def reprise_clean_again(pid: str):
    from adaptation import reprise_pipeline as rp
    _reprise_or_404(pid)
    p = _adaptation_call(rp.clean_again, pid)
    _start_adaptation_step(pid, "cleaning")
    return _serialize_adaptation(p)


@router.post("/api/adaptations/{pid}/reprise/cleaning/approve")
def reprise_approve_cleaning(pid: str):
    from adaptation import reprise_pipeline as rp
    _reprise_or_404(pid)
    p = _adaptation_call(rp.approve_cleaning, pid)
    _start_adaptation_step(pid, "scripting")
    return _serialize_adaptation(p)


class RepriseScript(BaseModel):
    texts: list                         # one text per part, in this channel's language
    title: Optional[str] = None         # the thumbnail's
    youtube: Optional[dict] = None      # {"titre", "description", "tags"}


@router.put("/api/adaptations/{pid}/targets/{channel}/reprise-script")
def reprise_edit_script(pid: str, channel: TargetChannel, req: RepriseScript):
    from adaptation import reprise_pipeline as rp
    _reprise_or_404(pid)
    return _serialize_adaptation(_adaptation_call(rp.edit_script, pid, channel, req.texts, req.title, req.youtube))


class RepriseSound(BaseModel):
    son: str
    volume_db: Optional[float] = None


@router.patch("/api/adaptations/{pid}/reprise/son")
def reprise_sound(pid: str, req: RepriseSound):
    from adaptation import reprise_pipeline as rp
    _reprise_or_404(pid)
    p = _adaptation_call(rp.change_sound, pid, req.son, req.volume_db)
    _start_adaptation_step(pid, "voicing")
    return _serialize_adaptation(p)


@router.get("/api/adaptations/{pid}/reprise/video/{which}")
def reprise_video(pid: str, which: str):
    """The Short as downloaded ("original") or cleaned ("propre"), to compare them."""
    r = _reprise_or_404(pid).get("reprise") or {}
    path = {"original": r.get("video"), "propre": r.get("clean")}.get(which)
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Vidéo pas encore prête.")
    return FileResponse(path, media_type="video/mp4")


# ---------------------------------------------------------------------------
# Discours (a speech, the speaker's own voice): its passage, its cut-aways, its settings
# ---------------------------------------------------------------------------

def _discours_or_404(pid: str) -> dict:
    p = _adaptation_or_404(pid)
    if p.get("mode") != "discours":
        raise HTTPException(status_code=400, detail="Ce projet n'est pas un Discours.")
    return p


class DiscoursPassage(BaseModel):
    index: int
    i0: Optional[int] = None            # its first word (index in the whole transcript)
    i1: Optional[int] = None            # its last word
    orateur: Optional[str] = None       # the speaker's name, for the credits


@router.put("/api/adaptations/{pid}/discours/passage")
def discours_passage(pid: str, req: DiscoursPassage):
    from adaptation import discours_pipeline as dp
    _discours_or_404(pid)
    return _serialize_adaptation(_adaptation_call(dp.choose_passage, pid, req.index, req.i0, req.i1, req.orateur))


@router.post("/api/adaptations/{pid}/discours/passages/plus")
def discours_more_passages(pid: str):
    from adaptation import discours_pipeline as dp
    _discours_or_404(pid)
    return _serialize_adaptation(_adaptation_call(dp.more_passages, pid))


@router.post("/api/adaptations/{pid}/discours/passage/approve")
def discours_approve_passage(pid: str):
    from adaptation import discours_pipeline as dp
    _discours_or_404(pid)
    p = _adaptation_call(dp.approve_passage, pid)
    _start_adaptation_step(pid, "searching")
    return _serialize_adaptation(p)


class DiscoursMoment(BaseModel):
    action: Optional[str] = None        # garder | retirer
    url: Optional[str] = None           # the person's own link for this moment
    debut: float = 0.0                  # the second of that video it starts at


def _restart_if_voicing(pid: str, p: dict):
    if p["status"] == "voicing":
        _start_adaptation_step(pid, "voicing")


@router.post("/api/adaptations/{pid}/discours/moments/{index}")
def discours_moment(pid: str, index: int, req: DiscoursMoment):
    from adaptation import discours_pipeline as dp
    _discours_or_404(pid)
    if req.url:
        p = _adaptation_call(dp.link_moment, pid, index, req.url, req.debut)
    else:
        p = _adaptation_call(dp.set_moment, pid, index, req.action or "")
    _restart_if_voicing(pid, p)
    return _serialize_adaptation(p)


class DiscoursStock(BaseModel):
    recherche: Optional[str] = None     # new words to search Pixabay with
    stock: Optional[str] = None         # or one proposition taken ("pixabay:<id>")


@router.post("/api/adaptations/{pid}/discours/moments/{index}/pixabay")
def discours_moment_stock(pid: str, index: int, req: DiscoursStock):
    from adaptation import discours_pipeline as dp
    _discours_or_404(pid)
    if req.stock:
        p = _adaptation_call(dp.pick_stock, pid, index, req.stock)
    else:
        p = _adaptation_call(dp.search_stock, pid, index, req.recherche or "")
    _restart_if_voicing(pid, p)
    return _serialize_adaptation(p)


class DiscoursMove(BaseModel):
    mot: int                            # the word of the passage the shot now starts on


@router.post("/api/adaptations/{pid}/discours/moments/{index}/move")
def discours_moment_move(pid: str, index: int, req: DiscoursMove):
    from adaptation import discours_pipeline as dp
    _discours_or_404(pid)
    p = _adaptation_call(dp.move_moment, pid, index, req.mot)
    _restart_if_voicing(pid, p)
    return _serialize_adaptation(p)


@router.post("/api/adaptations/{pid}/discours/moments/{index}/file")
async def discours_moment_file(pid: str, index: int, file: UploadFile = File(...)):
    """« Déposer un fichier » for one cut-away: kept in the project, its first seconds used."""
    from adaptation import discours_pipeline as dp, pipeline as ap, sources
    _discours_or_404(pid)
    with tempfile.TemporaryDirectory() as tmp:
        src = await _dropped(file, tmp)
        try:
            key = await asyncio.to_thread(sources.save_local, src, os.path.join(ap.project_dir(pid), "fichiers"),
                                          Path(file.filename).name)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)[:300])
    p = await asyncio.to_thread(_adaptation_call, dp.link_moment, pid, index, key, 0.0)
    _restart_if_voicing(pid, p)
    return _serialize_adaptation(p)


@router.get("/api/adaptations/{pid}/discours/moments/{index}/clip")
def discours_moment_clip(pid: str, index: int):
    ms = (_discours_or_404(pid).get("discours") or {}).get("moments") or []
    paths = [x.get("path") for x in ((ms[index].get("clip") or {}).get("extraits") or [])] if 0 <= index < len(ms) else []
    path = next((x for x in paths if x and os.path.exists(x)), None)
    if not path:
        raise HTTPException(status_code=404, detail="Extrait introuvable.")
    return FileResponse(path, media_type="video/mp4")


@router.get("/api/adaptations/{pid}/discours/moments/{index}/frame")
def discours_moment_frame(pid: str, index: int):
    """One small image of the cut-away (its timeline block)."""
    from adaptation import discours as D
    clip = discours_moment_clip(pid, index).path
    try:
        path = D.frame_at(clip, 0.5, os.path.splitext(clip)[0] + "_bloc.jpg")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)[:200])
    return FileResponse(path, media_type="image/jpeg")


@router.post("/api/adaptations/{pid}/discours/plans/approve")
def discours_approve_plans(pid: str):
    from adaptation import discours_pipeline as dp
    _discours_or_404(pid)
    p = _adaptation_call(dp.approve_plans, pid)
    _start_adaptation_step(pid, "voicing")
    return _serialize_adaptation(p)


@router.post("/api/adaptations/{pid}/discours/plans/back")
def discours_back_to_plans(pid: str):
    from adaptation import discours_pipeline as dp
    _discours_or_404(pid)
    return _serialize_adaptation(_adaptation_call(dp.back_to_plans, pid))


class DiscoursSettings(BaseModel):
    reglages: Optional[dict] = None     # the video's own settings (over the channel's « style Discours »)
    son: Optional[str] = None
    chanson: Optional[str] = None


@router.patch("/api/adaptations/{pid}/discours/reglages")
def discours_settings(pid: str, req: DiscoursSettings):
    from adaptation import discours_pipeline as dp
    _discours_or_404(pid)
    p = _adaptation_call(dp.change_settings, pid, req.reglages, req.son, req.chanson)
    _restart_if_voicing(pid, p)
    return _serialize_adaptation(p)


@router.get("/api/adaptations/{pid}/discours/passage")
def discours_passage_video(pid: str):
    """The chosen passage as it was said (before its pauses are cut): the Plans screen's player."""
    d = _discours_or_404(pid).get("discours") or {}
    if not d.get("segment") or not os.path.exists(d["segment"]):
        raise HTTPException(status_code=404, detail="Passage pas encore découpé.")
    return FileResponse(d["segment"], media_type="video/mp4")


@router.get("/api/adaptations/{pid}/discours/frame")
def discours_frame(pid: str, t: float = 0.0):
    """The speaker at `t` s of the passage (a timeline block), a small image made once."""
    from adaptation import discours as D, discours_pipeline as dp
    p = _discours_or_404(pid)
    seg = (p.get("discours") or {}).get("segment")
    if not seg or not os.path.exists(seg):
        raise HTTPException(status_code=404, detail="Passage pas encore découpé.")
    t = round(max(0.0, t), 1)
    try:
        path = D.frame_at(seg, t, os.path.join(dp.work_dir(p, "passage", "images"), f"{t:.1f}.jpg"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)[:200])
    return FileResponse(path, media_type="image/jpeg")


@router.get("/api/adaptations/{pid}/discours/video")
def discours_video(pid: str):
    d = _discours_or_404(pid).get("discours") or {}
    if not d.get("video") or not os.path.exists(d["video"]):
        raise HTTPException(status_code=404, detail="Vidéo pas encore prête.")
    return FileResponse(d["video"], media_type="video/mp4")


def _discours_channel_payload(channel_name: str) -> dict:
    from adaptation import discours as D
    from captions import styles as S
    profile = _main().channel_manager.get_channel_profile(channel_name) or {}
    lang = (profile.get("language_hint") or "fr").split("-")[0]
    return {"reglages": D.channel_settings(profile), "defauts": D.DEFAULTS, "language": lang,
            "cadres": list(D.FRAMES), "fonds": list(D.FONDS), "etalonnages": list(D.GRADES),
            "densites": list(D.DENSITY),
            "styles": [{"id": st.id, "label": st.label, "number": st.number, "group": st.group}
                       for st in S.for_space("discours", lang) if not st.native]}


@router.get("/api/channels/{channel_name}/discours")
def get_channel_discours(channel_name: str):
    _main().checked_channel(channel_name)
    return _discours_channel_payload(channel_name)


@router.put("/api/channels/{channel_name}/discours")
def update_channel_discours(channel_name: str, body: dict):
    """A channel's « style Discours » (Réglages → Discours) and whether its cut-aways may be films."""
    from adaptation import discours as D
    _main().checked_channel(channel_name)
    profile = _main().channel_manager.get_channel_profile(channel_name)
    mine = {k: v for k, v in D.clean_settings(body).items() if k in body or (k == "sous_titres_params" and "sous_titres" in body)}
    if isinstance(body.get("films"), bool):
        mine["films"] = body["films"]
    profile["discours"] = {**(profile.get("discours") or {}), **mine}
    _main().channel_manager.save_channel_profile(channel_name, profile)
    return _discours_channel_payload(channel_name)


# ---------------------------------------------------------------------------
# The shared songs (assets/musiques): any channel may use them; the smart music picks among them
# ---------------------------------------------------------------------------

def _song_path(name: str) -> str:
    from adaptation import musique, reprise_pipeline as rp
    name = os.path.basename(name)
    path = os.path.join(rp.SHARED_MUSIC, name)
    if not name.lower().endswith(musique.EXTENSIONS) or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Musique introuvable.")
    return path


def _analyse_song_later(path: str):
    """Gemini listens to a new song once (its mood, its strongest moment); the rises are measured."""
    from adaptation import musique

    def run():
        try:
            from gemini_ai_generator import usage_context
            with usage_context(projet="musiques"):
                musique.listen(path)
        except Exception as e:                  # shown as « pas encore écoutée »; tried again at its first use
            print(f"Musique {os.path.basename(path)} : écoute impossible ({e})")
    threading.Thread(target=run, daemon=True).start()


@router.get("/api/musiques")
def list_songs():
    from adaptation import musique, reprise_pipeline as rp
    out = []
    for path in musique.songs_of(rp.SHARED_MUSIC):
        cache = musique._cache(path)
        a = json.load(open(cache, encoding="utf-8")) if os.path.exists(cache) else None
        name = os.path.basename(path)
        out.append({"fichier": name, "url": f"/api/musiques/{quote(name)}/audio",
                    "analyse": {k: a.get(k) for k in ("titre", "humeur", "convient_a", "moment_fort", "montees", "duree")} if a else None})
    return {"musiques": out, "chaines_intelligentes": list(rp.SMART_CHANNELS)}


@router.get("/api/musiques/{name}/audio")
def song_audio(name: str):
    return FileResponse(_song_path(name))


class SongLink(BaseModel):
    url: str


@router.post("/api/musiques/lien")
def add_song_link(req: SongLink):
    """A song from a link (YouTube…): its sound only, as mp3, then listened to once."""
    import glob
    from adaptation import reprise_pipeline as rp, sources
    os.makedirs(rp.SHARED_MUSIC, exist_ok=True)
    before = set(glob.glob(os.path.join(rp.SHARED_MUSIC, "*.mp3")))
    opts = sources.ytdlp_opts(outtmpl=os.path.join(rp.SHARED_MUSIC, "%(title)s [%(id)s].%(ext)s"), format="bestaudio/best",
                              noplaylist=True, postprocessors=[{"key": "FFmpegExtractAudio", "preferredcodec": "mp3",
                                                                "preferredquality": "2"}])
    try:
        sources._fetch_once(req.url.strip(), opts)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)[:300])
    new = sorted(set(glob.glob(os.path.join(rp.SHARED_MUSIC, "*.mp3"))) - before)
    if not new:
        raise HTTPException(status_code=400, detail="Pas de son récupéré depuis ce lien (déjà dans la liste ?).")
    for path in new:
        _analyse_song_later(path)
    return list_songs()


@router.post("/api/musiques/fichier")
async def add_song_file(file: UploadFile = File(...)):
    from adaptation import musique, reprise_pipeline as rp
    name = os.path.basename(file.filename or "")
    if not name.lower().endswith(musique.EXTENSIONS):
        raise HTTPException(status_code=400, detail="Un fichier audio : " + ", ".join(musique.EXTENSIONS))
    os.makedirs(rp.SHARED_MUSIC, exist_ok=True)
    path = os.path.join(rp.SHARED_MUSIC, name)
    with open(path, "wb") as f:
        f.write(await file.read())
    _analyse_song_later(path)
    return list_songs()


@router.delete("/api/musiques/{name}")
def delete_song(name: str):
    from adaptation import musique
    path = _song_path(name)
    os.remove(path)
    if os.path.exists(musique._cache(path)):
        os.remove(musique._cache(path))
    return list_songs()

