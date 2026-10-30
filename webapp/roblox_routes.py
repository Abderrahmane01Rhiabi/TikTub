"""Montage Roblox projects — the "Roblox" space: a long video → its moments → the texts to read → the Shorts →
Publication (roblox/pipeline.py). The analysis and the render run in the background with their progress."""

import os
import sys
import threading
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter()


def _main():
    return sys.modules["webapp.main"]


def _job(pid: str) -> str:
    return f"roblox:{pid}"


def _call(fn, *args):
    from roblox.pipeline import PipelineError
    try:
        return fn(*args)
    except PipelineError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _start(pid: str, step: str):
    import progress
    from roblox import pipeline as rp
    key = _job(pid)
    progress.start(key, kind="roblox", phase=step)

    def run():
        try:
            seen = {"f": 0.0}

            def report(phase, f):
                seen["f"] = max(seen["f"], f)
                progress.update(key, seen["f"], phase=phase)
            from gemini_ai_generator import usage_context
            with usage_context(projet=pid):              # each AI call noted with its project
                rp.RUNNERS[step](pid, report)
            progress.finish(key)
        except BaseException as e:                      # anything — a step once ended silently, its project "en cours"
            import traceback
            traceback.print_exc()
            progress.finish(key, error=str(e) or type(e).__name__)
            try:
                p = rp.load(pid)
                if p["status"] == step:
                    rp.fail(pid, step, RuntimeError(f"{type(e).__name__} : {e}"))
            except Exception:
                traceback.print_exc()
    threading.Thread(target=run, daemon=True).start()


def _serialize(p: Dict, full: bool = True) -> Dict:
    import progress
    from roblox import plan
    from roblox import pipeline as rp
    job = progress.get(_job(p["project_id"])) or {}
    from roblox import voix
    out = {k: p.get(k) for k in ("project_id", "status", "url", "styles", "musique", "error", "failed_step", "created_at", "absents")}
    out["voix_joueur"] = p.get("voix_joueur") or "originale"          # a project made before the choice kept it
    out["identite"] = bool(p.get("identite"))
    out["titre"] = (p.get("meta") or {}).get("titre") or ""
    out["chaine_source"] = (p.get("meta") or {}).get("chaine") or ""
    names = {(lang, v["voice_id"]): v["nom"] for lang in voix.CATALOGUE for v in voix.catalogue(lang)}
    players = (p.get("voix") or {}).get("joueurs") or {}
    out["joueurs"] = players
    out["cibles"] = [{"langue": t["langue"], "channel": t["channel"], "voix": t.get("voice_id"),
                      "nom_voix": names.get((t["langue"], t.get("voice_id"))),
                      "voix_joueurs": {q: {"voix": v, "nom": names.get((t["langue"], v))}
                                       for q in sorted(set(players) | {"1"}) for v in [rp.player_voice(t, q)]}}
                     for t in p["targets"]]
    out["progress"] = {"fraction": job.get("fraction"), "phase": job.get("phase")} if job and not job.get("done") else None
    out["noms_styles"] = {k: v[0] for k, v in plan.STYLES.items()}
    if full:
        out["plan"] = p.get("plan") or {}
        out["moments"] = {m["id"]: m.get("resume") for m in p.get("catalogue") or []}
        uses = rp.styles_of_moments(p.get("plan") or {})
        out["repliques"] = {mid: {"lignes": r["lignes"], "styles": uses.get(mid, [])}
                            for mid, r in ((p.get("voix") or {}).get("repliques") or {}).items()}
        out["videos"] = {k: {**{x: v.get(x) for x in ("style", "langue", "channel", "duree", "video_id", "a_refaire")},
                             "url": f"/api/roblox/{p['project_id']}/videos/{k}?v={int(os.path.getmtime(v['path'])) if os.path.exists(v['path']) else 0}"}
                         for k, v in (p.get("videos") or {}).items()}
    return out


class Cible(BaseModel):
    langue: str
    channel: str
    voix: Optional[str] = None
    voix_2: Optional[str] = None


class RobloxCreate(BaseModel):
    url: str
    styles: List[str]
    cibles: List[Cible]
    musique: str = "original"
    voix_joueur: str = "remplacer"
    identite: bool = False


@router.post("/api/roblox")
def create_roblox(req: RobloxCreate):
    from roblox import pipeline as rp
    targets = []
    for c in req.cibles:
        _main().checked_channel(c.channel)
        targets.append({"langue": c.langue, "channel": c.channel, "profile": _main().channel_manager.get_channel_profile(c.channel),
                        "music_dir": _main().channel_manager.get_assets_dirs(c.channel)["music"], "voice_id": c.voix, "voix_2": c.voix_2})
    p = _call(rp.create, req.url, req.styles, targets, req.musique, req.voix_joueur, req.identite)
    _start(p["project_id"], "analysing")
    return _serialize(p)


@router.get("/api/roblox")
def list_roblox():
    import db
    return [_serialize(p, full=False) for p in db.list_roblox()]


@router.get("/api/roblox/voix")                  # before /{pid}: "voix" is not a project
def roblox_voices():
    from roblox import voix
    return {lang: voix.catalogue(lang) for lang in voix.CATALOGUE}


@router.get("/api/roblox/voix/{voice_id}/echantillon")
def roblox_voice_sample(voice_id: str, langue: str = "fr"):
    from roblox import voix
    try:
        path = voix.sample(voice_id, langue)
    except Exception:
        path = None
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Pas d'extrait pour cette voix.")
    return FileResponse(path, media_type="audio/mpeg")


@router.get("/api/roblox/{pid}")
def get_roblox(pid: str):
    from roblox import pipeline as rp
    return _serialize(_call(rp.load, pid))


class Textes(BaseModel):
    style: str
    langue: str
    edit: Dict


@router.put("/api/roblox/{pid}/textes")
def edit_roblox_texts(pid: str, req: Textes):
    from roblox import pipeline as rp
    return _serialize(_call(rp.set_texts, pid, req.style, req.langue, req.edit))


class Repliques(BaseModel):
    moment: str
    langue: str
    lignes: List[str]


@router.put("/api/roblox/{pid}/repliques")
def edit_roblox_lines(pid: str, req: Repliques):
    from roblox import pipeline as rp
    return _serialize(_call(rp.set_lines, pid, req.moment, req.langue, req.lignes))


class VoixJoueur(BaseModel):
    langue: str
    joueur: str
    voix: str


@router.put("/api/roblox/{pid}/voix")
def edit_roblox_voice(pid: str, req: VoixJoueur):
    from roblox import pipeline as rp
    return _serialize(_call(rp.set_voice, pid, req.langue, req.joueur, req.voix))


@router.post("/api/roblox/{pid}/render")
def render_roblox(pid: str):
    from roblox import pipeline as rp
    p = _call(rp.start_render, pid)
    _start(pid, "rendering")
    return _serialize(p)


@router.post("/api/roblox/{pid}/retry")
def retry_roblox(pid: str):
    """The failed step again (analysis or render), from where it stood."""
    from roblox import pipeline as rp
    p = _call(rp.load, pid)
    step = p.get("failed_step")
    if p["status"] != "error" or step not in rp.RUNNERS:
        raise HTTPException(status_code=400, detail="Rien à relancer.")
    p.update(status=step, error=None)
    rp.save(p)
    _start(pid, step)
    return _serialize(p)


@router.get("/api/roblox/{pid}/videos/{key}")
def roblox_video(pid: str, key: str):
    from roblox import pipeline as rp
    v = (_call(rp.load, pid).get("videos") or {}).get(key)
    if not v or not os.path.exists(v["path"]):
        raise HTTPException(status_code=404, detail="Vidéo introuvable.")
    return FileResponse(v["path"], media_type="video/mp4")


class Envoi(BaseModel):
    videos: List[str]


@router.post("/api/roblox/{pid}/send")
def send_roblox(pid: str, req: Envoi):
    from roblox import pipeline as rp
    return _serialize(_call(rp.send, pid, req.videos))


@router.delete("/api/roblox/{pid}")
def delete_roblox(pid: str):
    import progress
    from roblox import pipeline as rp
    if progress.is_running(_job(pid)):
        raise HTTPException(status_code=409, detail="Le projet travaille encore : attends la fin.")
    _call(rp.delete, pid)
    return {"ok": True}
