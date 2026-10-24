"""
The Adaptation's routes (see ADAPTATION.md), moved out of main.py as they
were — same code, same order of the routes (main.py includes this router
where they stood).

What belongs to main.py (channel_manager, that tests replace on the fly; the
batch processor; a few helpers) is read from it at the time of each call,
never copied at import: _main().
"""

import asyncio
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

router = APIRouter()


def _main():
    return sys.modules["webapp.main"]


def _adaptation_channel_payload(channel_name: str) -> dict:
    from adaptation import settings as ad
    profile = _main().channel_manager.get_channel_profile(channel_name)
    s = ad.channel_settings(profile)
    music_dir = Path(_main().channel_manager.get_assets_dirs(channel_name)["music"])
    music = sorted(p.name for p in music_dir.iterdir() if p.suffix.lower() in _main().MUSIC_EXTENSIONS) \
        if music_dir.exists() else []
    from adaptation.render import STYLES
    return {"settings": s, "music_files": music, "voices": [_main()._serialize_voice(v) for v in ad.voices_for(s["language"])],
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
def get_channel_adaptation(channel_name: str):
    return _adaptation_channel_payload(channel_name)


class ChannelAdaptationUpdate(BaseModel):
    language: Optional[str] = None
    settings: dict = Field(default_factory=dict)


@router.put("/api/channels/{channel_name}/adaptation")
def update_channel_adaptation(channel_name: str, update: ChannelAdaptationUpdate):
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
    runner = ap.RUNNERS[step]

    def run():
        try:
            seen = {"f": 0.0}            # never backwards: sources handled at once each report their own share

            def report(phase, f):
                seen["f"] = max(seen["f"], f)
                progress.update(key, seen["f"], phase=phase)
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
    base["annotations_reviewed"] = bool(p.get("annotations_reviewed"))
    base["fetch_note"] = p.get("fetch_note")
    from adaptation import tone as _tone_mod
    base["ton"] = _tone_mod.of(p.get("reference")) if (p.get("reference") or {}).get("ton") else None
    base["tons"] = _tone_mod.choices()
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
            "duration": (prev.get("summary") or {}).get("duration"),
        })
    base["targets"] = targets
    if full:
        ref = p.get("reference") or {}
        base["reference"] = {k: ref.get(k) for k in ("sujet", "question", "credits", "faits_douteux", "duree_s")}
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


def _adaptation_or_404(pid: str) -> dict:
    import db as _db
    p = _db.get_adaptation(pid)
    if not p:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    return p


def _adaptation_call(fn, *args):
    from adaptation.pipeline import PipelineError
    try:
        return fn(*args)
    except PipelineError as e:
        raise HTTPException(status_code=400, detail=str(e))


class AdaptationCreate(BaseModel):
    reference_url: str
    source_urls: list = Field(default_factory=list)
    channels: list
    mode: str = "sources"
    versions: bool = False


@router.post("/api/adaptations")
def create_adaptation(req: AdaptationCreate):
    from adaptation import pipeline as ap
    targets = [{"channel": ch, "profile": _main().channel_manager.get_channel_profile(ch),
                "music_dir": _main().channel_manager.get_assets_dirs(ch)["music"]} for ch in req.channels]
    p = _adaptation_call(ap.create, req.reference_url, req.source_urls, targets, req.mode, req.versions)
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
def change_adaptation_target_angle(pid: str, channel: str, req: AdaptationAngle):
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
def edit_adaptation_plan(pid: str, channel: str, req: AdaptationPlan):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.edit_plan, pid, channel, req.plan))


@router.post("/api/adaptations/{pid}/targets/{channel}/plan/revise")
def revise_adaptation_plan(pid: str, channel: str, req: AdaptationPlanRevise):
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
def approve_adaptation_plan(pid: str, channel: str):
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
def keep_adaptation_passage(pid: str, channel: str, k: int):
    """The check says the sentence and its picture don't match: keep it anyway."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.keep_passage, pid, channel, k))


@router.post("/api/adaptations/{pid}/targets/{channel}/passages/{k}/clip")
def use_adaptation_clip_proposal(pid: str, channel: str, k: int):
    """Take the other clip the check found for this sentence (the sentence stays)."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.use_clip_proposal, pid, channel, k))


@router.post("/api/adaptations/{pid}/targets/{channel}/passages/{k}/proposal")
def use_adaptation_proposal(pid: str, channel: str, k: int):
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
def edit_adaptation_script(pid: str, channel: str, req: AdaptationScript):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.edit_script, pid, channel, req.script))


class AdaptationRevise(BaseModel):
    request: str


@router.post("/api/adaptations/{pid}/targets/{channel}/revise")
def revise_adaptation_script(pid: str, channel: str, req: AdaptationRevise):
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
def approve_adaptation_script(pid: str, channel: str):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.approve_script, pid, channel))


@router.post("/api/adaptations/{pid}/voices")
def start_adaptation_voices(pid: str):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    p = _adaptation_call(ap.start_voices, pid)
    _start_adaptation_step(pid, "voicing")
    return _serialize_adaptation(p)


class AdaptationVoice(BaseModel):
    voice_id: str


@router.patch("/api/adaptations/{pid}/targets/{channel}/voice")
def change_adaptation_voice(pid: str, channel: str, req: AdaptationVoice):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    p = _adaptation_call(ap.change_voice, pid, channel, req.voice_id)
    _start_adaptation_step(pid, "voicing", only=channel)
    return _serialize_adaptation(p)


@router.post("/api/adaptations/{pid}/targets/{channel}/validate")
def validate_adaptation_preview(pid: str, channel: str):
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
