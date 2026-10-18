#!/usr/bin/env python3
"""
TikTub local web UI - thin FastAPI layer over the existing pipeline classes.
No business logic lives here: every endpoint just calls into ChannelManager,
URLManager, BatchProcessor, or youtube_uploader.

Run from the project root:
    uvicorn webapp.main:app --reload --port 8000
Then open http://127.0.0.1:8000/
"""

import os
import sys
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import quote

# Make sure the project root (parent of webapp/) is importable regardless of
# how uvicorn was invoked.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
# All existing modules use paths relative to the cwd (channels/, database/,
# temp/, config.yaml...), so the cwd IS the data directory. TIKTUB_DATA_DIR
# lets the test suite point it at a throwaway folder instead of the real
# project data; normal runs leave it unset and keep using the project root.
DATA_ROOT = Path(os.environ.get("TIKTUB_DATA_DIR") or PROJECT_ROOT)
os.chdir(DATA_ROOT)

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from channel_manager import ChannelManager

CONFIG_PATH = DATA_ROOT / "config.yaml"

@asynccontextmanager
async def lifespan(app):
    # each is best-effort: none of them may ever keep the app from starting
    _recover_interrupted_jobs()
    _daily_backup_on_startup()
    _start_stats_tracker()
    yield


app = FastAPI(title="TikTub", lifespan=lifespan)
channel_manager = ChannelManager()

# Serve downloaded/processed videos so <video> tags in the UI can preview them
os.makedirs("temp", exist_ok=True)
os.makedirs("processed_videos", exist_ok=True)
app.mount("/media/temp", StaticFiles(directory="temp"), name="media_temp")
app.mount("/media/processed", StaticFiles(directory="processed_videos"), name="media_processed")


@app.middleware("http")
async def log_actions_middleware(request: Request, call_next):
    """Persists every action taken through the app (every non-GET request) to
    the action_log table — GET requests are just reads/polling, not actions.
    Captured generically here (rather than one log call per endpoint) so no
    current or future endpoint can be forgotten."""
    body_bytes = b""
    is_action = request.method in ("POST", "PATCH", "PUT", "DELETE")
    content_type = request.headers.get("content-type", "")

    if is_action and "multipart/form-data" not in content_type:
        body_bytes = await request.body()

        async def receive():
            return {"type": "http.request", "body": body_bytes, "more_body": False}
        request._receive = receive

    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        try:
            response.headers["X-TikTub-Build"] = frontend_build()
        except OSError:
            pass

    if is_action:
        details = None
        if "multipart/form-data" in content_type:
            details = "<file upload>"
        elif body_bytes:
            details = body_bytes.decode("utf-8", errors="replace")[:2000]
        try:
            import db as _db
            _db.log_action(request.method, request.url.path, response.status_code, details)
        except Exception:
            pass  # logging must never break the actual request

    return response


_batch_processor = None
_batch_processor_lock = threading.Lock()


def get_batch_processor():
    global _batch_processor
    if not CONFIG_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail="config.yaml missing. Copy config.yaml.example to config.yaml first."
        )
    if _batch_processor is None:
        # Route handlers here are sync `def`s, so FastAPI runs them in real
        # worker threads — without this lock, two requests arriving at boot
        # before the first init finishes can both see None and each build
        # their own BatchProcessor (double AI-provider connection tests).
        with _batch_processor_lock:
            if _batch_processor is None:
                # Imported lazily: BatchProcessor.__init__ reads config.yaml and
                # initializes the AI providers, so we only pay that cost once.
                from batch_processor import BatchProcessor
                _batch_processor = BatchProcessor(config_path=str(CONFIG_PATH))
    return _batch_processor


INTERRUPTED_STATUSES = {
    # a background render/processing can't survive a server restart (its
    # thread and progress live in this process) — put those videos back
    # where the user can relaunch them instead of leaving them stuck
    "assembling": "audio_generated",
    "downloading": "download_failed",
    "processing": "selected",
    "generating_tags": "selected",
    "montage_planning": "selected",
}


def recover_interrupted() -> int:
    bp = get_batch_processor()
    count = 0
    for stuck, back_to in INTERRUPTED_STATUSES.items():
        for video in bp.url_manager.list_videos(status=stuck):
            extra = {"error_message": "Téléchargement interrompu par un redémarrage du serveur — réimporte le lien."} \
                if back_to == "download_failed" else {}
            bp.url_manager.update_video_status(video["video_id"], back_to, interrupted_from=stuck, **extra)
            count += 1
    if count:
        print(f"↩️ {count} vidéo(s) interrompue(s) par le redémarrage remise(s) à relancer")
    return count


def _recover_interrupted_jobs():
    try:
        recover_interrupted()
    except Exception as e:
        print(f"⚠️ Recovery of interrupted jobs skipped: {e}")
    try:
        from adaptation import pipeline as adaptation_pipeline
        adaptation_pipeline.recover_interrupted()
    except Exception as e:
        print(f"⚠️ Recovery of interrupted adaptations skipped: {e}")


def _daily_backup_on_startup():
    def run():
        try:
            import backup
            done = backup.backup_if_due()
            if done:
                print(f"💾 Sauvegarde automatique : {done['name']}")
        except Exception as e:
            print(f"⚠️ Sauvegarde automatique impossible : {e}")
    threading.Thread(target=run, daemon=True).start()


@app.get("/api/storage")
def storage_overview():
    import storage
    report = storage.scan()
    report.pop("items")
    return report


class CleanupRequest(BaseModel):
    include_rejected: bool = False


@app.post("/api/storage/cleanup")
def storage_cleanup(req: CleanupRequest):
    import storage
    return storage.cleanup(include_rejected=req.include_rejected)


@app.get("/api/backups")
def list_backups():
    import backup
    age = backup.latest_backup_age()
    return {"backups": backup.list_backups(), "keep": backup.KEEP,
            "last_age_hours": round(age.total_seconds() / 3600, 1) if age is not None else None}


@app.post("/api/backups")
def create_backup_now():
    import backup
    return backup.create_backup("manuelle")


@app.post("/api/backups/{name}/restore")
def restore_backup(name: str):
    import backup
    try:
        return backup.restore_backup(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Sauvegarde introuvable")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/backups/{name}/download")
def download_backup(name: str):
    import backup
    try:
        path = backup._safe_name(name)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="Sauvegarde introuvable")
    return FileResponse(path, filename=name, media_type="application/zip")


def _start_stats_tracker():
    """Launches the background performance-snapshot loop (stats_tracker.py)
    — best-effort: config.yaml missing or any init hiccup shouldn't ever
    block the app itself from starting, this is a nice-to-have."""
    try:
        from stats_tracker import start_background_tracker
        start_background_tracker(get_batch_processor())
    except Exception as e:
        print(f"⚠️ Stats tracker did not start: {e}")


def video_media_url(video: dict) -> Optional[str]:
    """Best-effort browser-playable URL for a video's current file.

    raw_video_path lives under temp/<video_id>/<file>.mp4 (see download_tiktok_video's
    per-video subfolder), so the full path relative to the mounted dir must be kept,
    not just the filename. TikTok titles routinely contain '#' (hashtags) and spaces,
    which a browser treats as a URL fragment/needs-escaping if left raw — so every
    path segment is percent-encoded before it goes out in JSON.
    """
    path = video.get("video_path") or video.get("raw_video_path")
    if not path:
        return None
    path = path.replace("\\", "/")

    def encode(rel: str) -> str:
        return "/".join(quote(part) for part in rel.split("/"))

    if path.startswith("processed_videos/"):
        return f"/media/processed/{encode(path[len('processed_videos/'):])}"
    if path.startswith("temp/"):
        return f"/media/temp/{encode(path[len('temp/'):])}"
    return None


def serialize_video(video: dict) -> dict:
    return {
        "video_id": video.get("video_id"),
        "url": video.get("url"),
        "status": video.get("status"),
        "channel": video.get("channel", "default"),
        "title": video.get("original_title") or video.get("custom_title") or video.get("url"),
        "media_url": video_media_url(video),
        "ai_data": video.get("ai_data"),
        "error_message": video.get("error_message"),
        "frame_mode": video.get("frame_mode"),
        "rounded_corners": video.get("rounded_corners", False),
        **serialize_montage(video),
    }


def serialize_montage(video: dict) -> dict:
    """Montage auto fields: the resolved mode and settings (channel default
    + this video's overrides), and for a planned video everything the
    Import → Montage step shows and edits."""
    from montage import pipeline as mp, recipes
    try:
        profile = channel_manager.get_channel_profile(video.get("channel", "default"))
    except Exception:
        profile = {}
    out = {"edit_mode": recipes.edit_mode(profile, video),
           "montage_overrides": video.get("montage_overrides") or {},
           "montage_settings": recipes.resolve_settings(profile, video)}
    m = video.get("montage")
    if m:
        preview = m.get("preview_path")
        out["montage"] = {
            "validated": bool(m.get("validated")), "error": m.get("error"), "unsuitable": m.get("unsuitable"),
            "hooks": m.get("hooks") or [], "hook": m.get("hook") or "",
            "keywords": m.get("keywords") or [], "words": [w[0] for w in m.get("words") or []],
            "brolls": [{"id": i, "thumb_url": f"/api/broll/{i}/thumb", "video_url": f"/api/broll/{i}/video"}
                       for i in m.get("brolls") or []],
            "preview_url": video_media_url({"video_path": preview}) if preview and os.path.exists(preview) else None,
            "summary": (m.get("plan") or {}).get("resume"),
            "timeline": mp.timeline(video, profile),
        }
    return out


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------

@app.get("/api/channels")
def list_channels():
    return channel_manager.list_channels()


OVERVIEW_BUCKETS = {
    "to_sort": {"selected", "montage_review"},  # downloaded, waiting for Sélection/Cadrage/Montage/Traiter
    "generating": {"awaiting_script", "script_generated", "audio_generated", "assembling"},
    "ready": {"ready_for_upload"},  # waiting for Résultats IA → Planning → Publier
    "in_progress": {"pending", "downloading", "processing", "generating_tags", "montage_planning"},
    "errors": {"download_failed", "processing_failed", "error", "rendering_failed"},
}


@app.get("/api/overview")
def overview():
    """Accueil: per channel, what's waiting at each stage + what's scheduled
    + the Google project's quota today. Local data only (one DB read, no
    YouTube call) so the home screen is instant — the UI fetches each
    channel's connection state separately."""
    import quota
    from dateutil import parser as date_parser
    from datetime import timezone as _tz

    bp = get_batch_processor()
    now = datetime.now(_tz.utc)
    per_channel: Dict[str, dict] = {
        ch["name"]: {
            "counts": {bucket: 0 for bucket in OVERVIEW_BUCKETS} | {"scheduled": 0},
            "next_publish": None, "errors": [],
        }
        for ch in channel_manager.list_channels()
    }

    for video in bp.url_manager.list_videos():
        entry = per_channel.get(video.get("channel"))
        if entry is None:
            continue
        status = video.get("status")
        for bucket, statuses in OVERVIEW_BUCKETS.items():
            if status in statuses:
                entry["counts"][bucket] += 1
        if status in OVERVIEW_BUCKETS["errors"] and len(entry["errors"]) < 20:
            entry["errors"].append({
                "video_id": video["video_id"],
                "url": video.get("url"),
                "title": (video.get("ai_data") or {}).get("optimized_title") or video.get("original_title"),
                "status": status,
                "message": video.get("error_message") or video.get("render_error"),
            })
        if status == "scheduled_on_youtube" and video.get("scheduled_publish_time"):
            try:
                when = date_parser.parse(video["scheduled_publish_time"])
                when = when if when.tzinfo else when.astimezone()
            except (ValueError, OverflowError):
                continue
            if when > now:
                entry["counts"]["scheduled"] += 1
                if entry["next_publish"] is None or when < date_parser.parse(entry["next_publish"]):
                    entry["next_publish"] = when.isoformat()

    channels_out = [
        {"channel": name, **data, "quota": quota.status_for_channel(name)}
        for name, data in per_channel.items()
    ]
    totals = {key: sum(c["counts"][key] for c in channels_out) for key in list(OVERVIEW_BUCKETS) + ["scheduled"]}
    return {"channels": channels_out, "totals": totals}


@app.post("/api/videos/{video_id}/dismiss")
def dismiss_failed_video(video_id: str):
    """Removes a failed video from the "en erreur" lists (Accueil) — sets
    it to 'rejected', the same status as a video unticked in Sélection, so
    its URL can be imported again later (rejected is ignored by the
    duplicate check). Only for videos actually in an error status."""
    import db as _db
    video = _db.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.get("status") not in OVERVIEW_BUCKETS["errors"]:
        raise HTTPException(status_code=400, detail="Cette vidéo n'est pas en erreur")
    get_batch_processor().url_manager.update_video_status(video_id, "rejected", dismissed_from=video["status"])
    return {"dismissed": True}


@app.get("/api/channels/{channel_name}/profile")
def get_channel_profile(channel_name: str):
    return channel_manager.get_channel_profile(channel_name)


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    analysis_mode: Optional[str] = None
    ai_style_prompt: Optional[str] = None
    language_hint: Optional[str] = None
    preferred_days: Optional[list] = None
    preferred_hours: Optional[list] = None


@app.put("/api/channels/{channel_name}/profile")
def update_channel_profile(channel_name: str, update: ProfileUpdate):
    profile = channel_manager.get_channel_profile(channel_name)
    for key, value in update.dict(exclude_unset=True).items():
        profile[key] = value
    channel_manager.save_channel_profile(channel_name, profile)
    return profile


@app.post("/api/channels/{channel_name}/background")
async def upload_background(channel_name: str, file: UploadFile = File(...)):
    channel_dir = Path("channels") / channel_name
    channel_dir.mkdir(parents=True, exist_ok=True)

    # Remove any previous background image so get_background_path finds only one
    for ext in ("jpg", "jpeg", "png"):
        old = channel_dir / f"background.{ext}"
        if old.exists():
            old.unlink()

    ext = Path(file.filename).suffix.lstrip(".").lower() or "jpg"
    if ext not in ("jpg", "jpeg", "png"):
        ext = "jpg"
    dest = channel_dir / f"background.{ext}"

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    return {"background_path": str(dest)}


@app.get("/api/channels/{channel_name}/background")
def get_background_image(channel_name: str):
    path = channel_manager.get_background_path(channel_name)
    if not path:
        raise HTTPException(status_code=404, detail="No background set for this channel")
    return FileResponse(path)


@app.delete("/api/channels/{channel_name}/background")
def remove_background(channel_name: str):
    """Removes this channel's background image — future videos fall back to
    plain black (never a random pick from backgrounds/, per an earlier decision)."""
    channel_dir = Path("channels") / channel_name
    removed = False
    for ext in ("jpg", "jpeg", "png"):
        path = channel_dir / f"background.{ext}"
        if path.exists():
            path.unlink()
            removed = True
    return {"removed": removed}


# ---------------------------------------------------------------------------
# YouTube OAuth ("Connexion" step) — connect each channel's Google account
# from the browser instead of hunting an auth URL in the server terminal.
# ---------------------------------------------------------------------------

@app.post("/api/channels/{channel_name}/connect/start")
def connect_start(channel_name: str, request: Request):
    from youtube_uploader import start_oauth_flow

    # Always use "localhost" (matching credentials.json's registered
    # "http://localhost" redirect URI) rather than whatever host the browser
    # used to reach us (e.g. 127.0.0.1), so Google's loopback-redirect match
    # for "installed app" OAuth clients succeeds regardless of port.
    port = request.url.port or 80
    redirect_uri = f"http://localhost:{port}/api/oauth/callback"

    try:
        auth_url = start_oauth_flow(channel_name, redirect_uri)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"auth_url": auth_url}


@app.get("/api/oauth/callback")
def oauth_callback(request: Request):
    from youtube_uploader import complete_oauth_flow

    state = request.query_params.get("state")
    try:
        channel_name = complete_oauth_flow(state, str(request.url))
        body = f"<p>Chaîne « {channel_name} » connectée ✅ — tu peux fermer cet onglet.</p>"
    except Exception as e:
        import traceback
        traceback.print_exc()  # so a failure shows up in the server terminal, not just silently
        body = f"<p>Échec de l'autorisation : {e}</p>"

    return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:40px;text-align:center">
        {body}
        <script>setTimeout(() => window.close(), 1500)</script>
        </body></html>
    """)


@app.get("/api/channels/{channel_name}/connection_status")
def connection_status(channel_name: str):
    """state tells WHY a channel isn't usable (see get_connection_health) —
    "expired" vs "not_connected" vs "error" — instead of one bare
    "Non connectée" for every case."""
    from youtube_uploader import get_connection_health, has_edit_scope
    health = get_connection_health(channel_name)
    connected = health["state"] == "connected"
    try:
        import alerts
        alerts.connection_state(channel_name, health["state"], health["reason"])
    except Exception:
        pass
    return {
        "connected": connected,
        "state": health["state"],
        "reason": health["reason"],
        "youtube_channel_title": health["youtube_channel_title"],
        "can_edit": has_edit_scope(channel_name) if connected else False,
    }


@app.get("/api/channels/{channel_name}/dashboard")
def channel_dashboard(channel_name: str, refresh: bool = False):
    """Every video TikTub has published to this channel, with locally-known
    metadata always shown, plus live YouTube stats (views/likes/real privacy
    status) fetched on demand (?refresh=true) — not on every page load, since
    that's a live API call rather than a free local read."""
    bp = get_batch_processor()
    channel_videos = bp.url_manager.list_videos(channel=channel_name)
    published = [v for v in channel_videos if v.get('youtube_id')]

    stats = {}
    stats_available = False
    if refresh and published:
        from youtube_uploader import get_video_stats
        try:
            stats = get_video_stats(channel_name, [v['youtube_id'] for v in published])
            stats_available = bool(stats)
        except Exception:
            pass

    items = []
    for v in published:
        yid = v['youtube_id']
        ai = v.get('ai_data') or {}
        live = stats.get(yid, {})
        items.append({
            "video_id": v['video_id'],
            "youtube_id": yid,
            "youtube_url": v.get('youtube_url'),
            "title": ai.get('optimized_title') or v.get('original_title') or '',
            "tags": ai.get('tags', []),
            "description": (ai.get('description_suggestions') or [''])[0],
            "scheduled_time": v.get('scheduled_publish_time'),
            "local_status": v.get('status'),
            "view_count": live.get('view_count'),
            "like_count": live.get('like_count'),
            "comment_count": live.get('comment_count'),
            "privacy_status": live.get('privacy_status'),
            "publish_at": live.get('publish_at'),
            "thumbnail_url": live.get('thumbnail_url'),
            "published_at": live.get('published_at'),
        })

    items.sort(key=lambda x: x.get('published_at') or x.get('scheduled_time') or '', reverse=True)
    from youtube_uploader import has_analytics_scope
    return {"videos": items, "stats_available": stats_available, "analytics_available": has_analytics_scope(channel_name)}


class VisibilityUpdate(BaseModel):
    privacy_status: str  # "private" | "public" | "unlisted"
    publish_at: Optional[str] = None  # ISO 8601 UTC, only meaningful with "private"


@app.patch("/api/channels/{channel_name}/videos/{youtube_id}/visibility")
def update_visibility(channel_name: str, youtube_id: str, update: VisibilityUpdate):
    from youtube_uploader import update_video_visibility

    try:
        new_status = update_video_visibility(
            channel_name, youtube_id, update.privacy_status, update.publish_at
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"YouTube API error: {e}")

    # Keep our local record in step with what we just told YouTube, so the
    # "Planning" screen and the dashboard's local_status don't go stale.
    bp = get_batch_processor()
    for video in bp.url_manager.list_videos(channel=channel_name):
        if video.get('youtube_id') == youtube_id:
            local_status = 'scheduled_on_youtube' if new_status.get('publishAt') else 'uploaded'
            bp.url_manager.update_video_status(
                video['video_id'], local_status,
                scheduled_publish_time=new_status.get('publishAt')
            )
            break

    return {"privacy_status": new_status.get('privacyStatus'), "publish_at": new_status.get('publishAt')}


@app.get("/api/channels/{channel_name}/videos/{youtube_id}/analytics")
def video_analytics(channel_name: str, youtube_id: str):
    from youtube_uploader import get_video_analytics, has_analytics_scope

    if not has_analytics_scope(channel_name):
        raise HTTPException(
            status_code=403,
            detail="Ce compte n'a pas encore le scope yt-analytics.readonly — reconnecte cette chaîne."
        )
    try:
        return get_video_analytics(channel_name, youtube_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"YouTube API error: {e}")


@app.get("/api/channels/{channel_name}/performance")
def channel_performance(channel_name: str):
    """"Ce qui marche": this channel's published videos ranked by views 7
    days after publication, each scored against the channel's median, plus
    which choices (format, décor, captions, publish day/hour...) beat it.
    Local data only (snapshots already recorded by stats_tracker)."""
    import performance
    bp = get_batch_processor()
    videos = [v for v in bp.url_manager.list_videos(channel=channel_name) if v.get("youtube_id")]
    history = {v["video_id"]: bp.url_manager.get_stats_history(v["video_id"]) for v in videos}
    return performance.analyze(videos, history)


@app.get("/api/suggestions")
def suggestions():
    """Accueil's "idée de la semaine": per generation channel, the winning
    style worth relaunching (see performance.suggest). Local data only."""
    out = []
    for ch in channel_manager.list_channels():
        if not ch.get("generation_mode"):
            continue  # "Refaire ce style" writes new scripts: generation channels only
        import performance
        s = performance.suggest(channel_performance(ch["name"]))
        if s:
            out.append({"channel": ch["name"], **s})
    return out


@app.post("/api/sync_youtube_statuses")
def sync_youtube_statuses_now():
    """Runs the YouTube status resync right away (it also runs hourly in the
    background, see stats_tracker) — the Dashboard's "Synchroniser" button."""
    from stats_tracker import sync_youtube_statuses, sync_retention
    bp = get_batch_processor()
    result = sync_youtube_statuses(bp)
    result["retention_measured"] = sync_retention(bp)
    return result


@app.get("/api/channels/{channel_name}/channel_analytics")
def channel_analytics_endpoint(channel_name: str, days: int = 30):
    from youtube_uploader import get_channel_analytics, has_analytics_scope

    if not has_analytics_scope(channel_name):
        raise HTTPException(
            status_code=403,
            detail="Ce compte n'a pas encore le scope yt-analytics.readonly — reconnecte cette chaîne."
        )
    try:
        return get_channel_analytics(channel_name, days=days)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"YouTube API error: {e}")


# ---------------------------------------------------------------------------
# URLs -> batch -> download -> selection -> processing
# ---------------------------------------------------------------------------

class UrlsSubmission(BaseModel):
    text: str
    batch_name: Optional[str] = None


@app.post("/api/channels/{channel_name}/urls")
def submit_urls(channel_name: str, submission: UrlsSubmission):
    bp = get_batch_processor()

    urls_dir = channel_manager.get_urls_input_dir(channel_name)
    filename = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    file_path = Path(urls_dir) / filename
    file_path.write_text(submission.text, encoding="utf-8")

    batch_id = bp.process_channel_url_file(channel_name, filename, batch_name=submission.batch_name)
    if not batch_id:
        raise HTTPException(status_code=400, detail="No valid URLs found in submitted text")

    return {"batch_id": batch_id}


@app.post("/api/batches/{batch_id}/download")
def download_batch(batch_id: str):
    bp = get_batch_processor()
    videos = bp.download_batch(batch_id)
    duplicates = bp.list_batch_videos(batch_id, status='duplicate')
    return {
        "videos": [serialize_video(v) for v in videos],
        "duplicates_skipped": len(duplicates)
    }


DOWNLOAD_JOB = "download"
_download_start_lock = threading.Lock()


class DownloadRequest(BaseModel):
    batch_ids: list


@app.post("/api/downloads")
def start_downloads(req: DownloadRequest):
    """Downloads the given batches (one per channel, created by
    POST /channels/{name}/urls) in a background thread and returns at
    once. GET /api/download_status follows EVERY link: waiting, its current
    step (reading the post, bytes received...), then ✓ / ✗ + reason /
    duplicate — instead of one long request that only said at the end how
    many worked."""
    import progress
    bp = get_batch_processor()
    with _download_start_lock:
        if progress.is_running(DOWNLOAD_JOB):
            return {"started": False, "running": True}
        items = []
        for batch_id in req.batch_ids:
            for v in sorted(bp.list_batch_videos(batch_id), key=lambda v: v.get("line_number") or 0):
                if v.get("status") == "pending":
                    items.append({"id": v["video_id"], "channel": v.get("channel"), "url": v.get("url"),
                                  "state": "waiting", "message": None})
        if not items:
            return {"started": False, "running": False, "total": 0}
        progress.start(DOWNLOAD_JOB, kind="download", items=items, total=len(items))

    def run():
        try:
            for batch_id in req.batch_ids:
                bp.download_batch(batch_id, on_item=lambda vid, state, message, detail=None: progress.update_item(
                    DOWNLOAD_JOB, vid, state=state, message=message, detail=detail))
            progress.finish(DOWNLOAD_JOB)
        except Exception as e:
            progress.finish(DOWNLOAD_JOB, error=str(e))

    threading.Thread(target=run, daemon=True).start()
    return {"started": True, "total": len(items)}


UPLOAD_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}


@app.post("/api/videos/{video_id}/upload_source")
async def upload_source_file(video_id: str, file: UploadFile = File(...)):
    """"Déposer le fichier": for a link whose download failed (restricted or
    private post...), the user provides the video file from their computer.
    It's saved where a download would have put it, checked to be a readable
    video, and the video goes on exactly like a downloaded one ('selected' →
    Sélection, Cadrage, IA)."""
    import db as _db
    video = _db.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.get("status") != "download_failed":
        raise HTTPException(status_code=400, detail="Un fichier ne peut être déposé que pour un lien dont le téléchargement a échoué.")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in UPLOAD_VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Format non pris en charge ({ext or 'sans extension'}) — dépose un fichier .mp4, .mov, .m4v ou .webm.")

    folder = Path("temp") / video_id
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"source{ext}"
    with open(dest, "wb") as out:
        shutil.copyfileobj(file.file, out)

    from video_processor import get_video_dimensions, is_decodable_video
    width, height = get_video_dimensions(str(dest))
    if not width or not is_decodable_video(str(dest)):
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Ce fichier ne se lit pas comme une vidéo — vérifie qu'il n'est pas abîmé.")

    title = video.get("original_title") or Path(file.filename).stem[:60]
    get_batch_processor().url_manager.update_video_status(
        video_id, "selected", raw_video_path=str(dest), original_title=title,
        error_message=None, error_detail=None, source_uploaded=True,
    )
    import progress
    progress.update_item(DOWNLOAD_JOB, video_id, state="done", message="fichier déposé")
    return {"uploaded": True, "width": width, "height": height}


@app.get("/api/download_status")
def download_status():
    import progress
    return progress.get(DOWNLOAD_JOB) or {"key": None, "done": True, "items": []}


@app.get("/api/batches/{batch_id}/videos")
def get_batch_videos(batch_id: str, status: Optional[str] = None):
    bp = get_batch_processor()
    videos = bp.list_batch_videos(batch_id, status=status)
    return [serialize_video(v) for v in videos]


@app.get("/api/videos")
def get_all_videos(status: Optional[str] = None, channel: Optional[str] = None):
    """Global video listing across every channel/batch — what the wizard UI uses,
    since it works on all 6 channels at once rather than one at a time."""
    bp = get_batch_processor()
    videos = bp.list_all_videos(status=status, channel=channel)
    return [serialize_video(v) for v in videos]


class SelectionUpdate(BaseModel):
    selected: bool


@app.post("/api/videos/{video_id}/select")
def select_video(video_id: str, update: SelectionUpdate):
    bp = get_batch_processor()
    bp.set_video_selection(video_id, update.selected)
    return {"ok": True}


@app.post("/api/videos/{video_id}/reprocess")
def reprocess_video(video_id: str):
    """Sends a ready video whose processed file is missing back to
    Import → Cadrage ('selected'), to be rendered again from its downloaded
    source — keeping its reviewed title/description/tags (reprocess_keep_ai).
    Refused if the downloaded source is gone too (then: re-import the URL)."""
    import db as _db
    video = _db.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.get("status") in ("uploaded", "scheduled_on_youtube"):
        raise HTTPException(status_code=400, detail="Vidéo déjà envoyée sur YouTube")
    raw = video.get("raw_video_path")
    if not raw or not os.path.exists(raw):
        raise HTTPException(status_code=400, detail="Le fichier téléchargé n'existe plus non plus — réimporte le lien dans Import → URLs.")
    get_batch_processor().url_manager.update_video_status(video_id, "selected", video_path=None, reprocess_keep_ai=True)
    return {"reprocess": True}


@app.post("/api/videos/{video_id}/abandon")
def abandon_ready_video(video_id: str):
    """Drops a video that's waiting to be published (e.g. its file is gone
    and it isn't worth reprocessing): removed from upload_schedule.json —
    otherwise "Publier tout" would still try it — and set to 'rejected'
    (its URL can be imported again later)."""
    import db as _db
    video = _db.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.get("status") in ("uploaded", "scheduled_on_youtube"):
        raise HTTPException(status_code=400, detail="Vidéo déjà envoyée sur YouTube")
    bp = get_batch_processor()
    data = bp.scheduler.load_schedule()
    if data:
        remaining = [e for e in data.get("schedule", []) if e.get("video_id") != video_id]
        if len(remaining) != len(data.get("schedule", [])):
            bp.scheduler.save_schedule(remaining)
    bp.url_manager.update_video_status(video_id, "rejected", abandoned_from=video.get("status"))
    return {"abandoned": True}


@app.get("/api/videos/{video_id}/frame_suggestion")
def get_frame_suggestion(video_id: str):
    bp = get_batch_processor()
    suggestion = bp.get_frame_suggestion(video_id)
    if not suggestion:
        raise HTTPException(status_code=404, detail="Video not found or not downloaded yet")
    return suggestion


@app.get("/api/videos/{video_id}/frame_preview")
def frame_preview(video_id: str, frame_mode: str, rounded_corners: bool = False):
    """A real composited still frame (actual video content + actual channel
    background), so the Cadrage step shows exactly what the mode will produce
    instead of a schematic box — without paying for a full video render.
    rounded_corners is independent of frame_mode — it can combine with any
    of them."""
    bp = get_batch_processor()
    db = bp.url_manager.load_database()
    video = db["videos"].get(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    raw_path = video.get("raw_video_path")
    if not raw_path or not os.path.exists(raw_path):
        raise HTTPException(status_code=404, detail="Video file not available")

    bg_mode, specific_bg = bp.get_background_for_video(video)
    bg_path = specific_bg if bg_mode == "specific" else None

    from video_processor import render_frame_preview
    jpeg_bytes = render_frame_preview(raw_path, frame_mode, bg_path, rounded_corners)
    if not jpeg_bytes:
        raise HTTPException(status_code=500, detail="Preview render failed")
    return Response(content=jpeg_bytes, media_type="image/jpeg")


class FrameModeUpdate(BaseModel):
    frame_mode: str  # "letterbox" | "full_border" | "fill"
    rounded_corners: Optional[bool] = None  # independent of frame_mode — combines with any of them


@app.patch("/api/videos/{video_id}/frame_mode")
def update_frame_mode(video_id: str, update: FrameModeUpdate):
    bp = get_batch_processor()
    video = bp.set_video_frame_mode(video_id, update.frame_mode, update.rounded_corners)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return serialize_video(video)


# ---------------------------------------------------------------------------
# Montage auto — Import → Cadrage (simple / montage + per-video style),
# Import → Montage (review a planned video before its real render),
# Réglages → Montage (channel defaults) and Réglages → Drones (shot library)
# ---------------------------------------------------------------------------

def _video_or_404(video_id: str) -> dict:
    import db as _db
    video = _db.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


def _montage_or_400(video: dict) -> dict:
    m = video.get("montage")
    if not m or not m.get("plan"):
        raise HTTPException(status_code=400, detail="Cette vidéo n'a pas encore de plan de montage.")
    return dict(m)


class MontageUpdate(BaseModel):
    edit_mode: Optional[str] = None     # "simple" | "montage"
    overrides: Optional[dict] = None    # replaces this video's style overrides ({} = follow the channel)
    hook: Optional[str] = None
    keywords: Optional[list] = None     # word indices drawn in the accent style


@app.patch("/api/videos/{video_id}/montage")
def update_video_montage(video_id: str, update: MontageUpdate):
    from montage import recipes
    video = _video_or_404(video_id)
    status, fields = video.get("status"), {}
    if update.edit_mode is not None:
        if update.edit_mode not in recipes.EDIT_MODES:
            raise HTTPException(status_code=400, detail="edit_mode: simple ou montage")
        fields["edit_mode"] = update.edit_mode
        if update.edit_mode == "simple" and status == "montage_review":
            status = "selected"           # back to Cadrage, rendered the simple way
    if update.overrides is not None:
        fields["montage_overrides"] = recipes.clean_settings(update.overrides)
    m = video.get("montage")
    if m and (update.hook is not None or update.keywords is not None or update.overrides is not None):
        m = dict(m)
        if update.hook is not None:
            m["hook"] = update.hook.strip()[:120]
        if update.keywords is not None:
            n = len(m.get("words") or [])
            m["keywords"] = sorted({int(i) for i in update.keywords if isinstance(i, int) and 0 <= i < n})
        m["preview_path"] = None          # the preview no longer shows what will be rendered
        fields["montage"] = m
    get_batch_processor().url_manager.update_video_status(video_id, status, **fields)
    return serialize_video(_video_or_404(video_id))


@app.post("/api/videos/{video_id}/montage/swap_broll/{slot}")
def swap_video_broll(video_id: str, slot: int):
    from montage import pipeline as mp
    video = _video_or_404(video_id)
    m = _montage_or_400(video)
    if slot not in (0, 1):
        raise HTTPException(status_code=400, detail="slot: 0 ou 1")
    m["brolls"], m["preview_path"] = mp.swap_broll(video, slot), None
    get_batch_processor().url_manager.update_video_status(video_id, video["status"], montage=m)
    return serialize_video(_video_or_404(video_id))


@app.post("/api/videos/{video_id}/montage/preview")
def preview_video_montage(video_id: str):
    """A quick low-resolution render (540x960, fast encode) of exactly what
    the real render will produce — seconds instead of a full render."""
    from montage import pipeline as mp
    video = _video_or_404(video_id)
    m = _montage_or_400(video)
    bp = get_batch_processor()
    try:
        path = mp.render_preview(video, bp._channel_profile(video.get("channel", "default")),
                                 bp.music_dir(video.get("channel", "default")))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Aperçu impossible : {e}")
    m = dict(_video_or_404(video_id).get("montage") or m)
    m["preview_path"], m["brolls"] = path, video["montage"]["brolls"]
    bp.url_manager.update_video_status(video_id, video["status"], montage=m)
    out = serialize_video(_video_or_404(video_id))
    if out.get("montage", {}).get("preview_url"):    # same path every time: defeat the browser cache
        out["montage"]["preview_url"] += f"?v={int(os.path.getmtime(path))}"
    return out


@app.post("/api/videos/{video_id}/montage/validate")
def validate_video_montage(video_id: str):
    """The person approved the plan: back to 'selected', and the next
    Traiter run does the real render, then the usual AI pass."""
    video = _video_or_404(video_id)
    m = _montage_or_400(video)
    if video.get("status") != "montage_review":
        raise HTTPException(status_code=400, detail="Seule une vidéo en attente de validation peut être validée.")
    m["validated"] = True
    get_batch_processor().url_manager.update_video_status(video_id, "selected", montage=m)
    return serialize_video(_video_or_404(video_id))


@app.post("/api/videos/{video_id}/montage/replan")
def replan_video_montage(video_id: str):
    """Asks Gemini for a new plan (it rarely gives the same one twice), in a
    background thread — the video shows 'montage_planning' meanwhile."""
    from montage import pipeline as mp
    video = _video_or_404(video_id)
    if video.get("status") != "montage_review":
        raise HTTPException(status_code=400, detail="Seule une vidéo en attente de validation peut être réanalysée.")
    bp = get_batch_processor()
    bp.url_manager.update_video_status(video_id, "montage_planning")

    def run():
        try:
            montage = mp.prepare_review(video, video.get("channel", "default"))
        except Exception as e:
            montage = {**(video.get("montage") or {}), "error": f"Analyse impossible : {e}"}
        bp.url_manager.update_video_status(video_id, "montage_review", montage=montage)

    threading.Thread(target=run, daemon=True).start()
    return {"started": True}


def _montage_channel_payload(channel_name: str) -> dict:
    from montage import recipes
    profile = channel_manager.get_channel_profile(channel_name)
    music_dir = Path(channel_manager.get_assets_dirs(channel_name)["music"])
    music = sorted(p.name for p in music_dir.iterdir() if p.suffix.lower() in MUSIC_EXTENSIONS) \
        if music_dir.exists() else []
    return {"settings": recipes.channel_settings(profile), "music_files": music,
            "recipes": {k: r["label"] for k, r in recipes.RECIPES.items()},
            "caption_styles": list(recipes.CAPTION_STYLES), "volumes": list(recipes.VOLUMES)}


MUSIC_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}


@app.get("/api/channels/{channel_name}/montage")
def get_channel_montage(channel_name: str):
    return _montage_channel_payload(channel_name)


class ChannelMontageUpdate(BaseModel):
    settings: dict


@app.put("/api/channels/{channel_name}/montage")
def update_channel_montage(channel_name: str, update: ChannelMontageUpdate):
    from montage import recipes
    profile = channel_manager.get_channel_profile(channel_name)
    profile["montage"] = recipes.clean_settings(update.settings)
    channel_manager.save_channel_profile(channel_name, profile)
    return _montage_channel_payload(channel_name)


@app.post("/api/channels/{channel_name}/assets/music")
async def upload_channel_music(channel_name: str, file: UploadFile = File(...)):
    """Adds a song to the channel's music folder (what Montage auto and the
    generative pipeline pick their background music from)."""
    name = Path(file.filename or "").name
    if Path(name).suffix.lower() not in MUSIC_EXTENSIONS or name.startswith("."):
        raise HTTPException(status_code=400, detail="Formats acceptés : mp3, wav, m4a, aac, ogg, flac.")
    dest = Path(channel_manager.get_assets_dirs(channel_name)["music"]) / name
    with open(dest, "wb") as out:
        shutil.copyfileobj(file.file, out)
    return _montage_channel_payload(channel_name)


def _serialize_broll(clip: dict, counts: Optional[dict] = None) -> dict:
    used = (counts or {}).get(str(clip["id"]), {"total": 0, "channels": {}})
    return {**{k: clip.get(k) for k in ("id", "query", "tags", "duration", "w", "h", "page")},
            "uses": used["total"], "uses_by_channel": used["channels"],
            "thumb_url": f"/api/broll/{clip['id']}/thumb", "video_url": f"/api/broll/{clip['id']}/video"}


@app.get("/api/broll")
def list_broll():
    """The drone library, how many times each shot has been used (rendered
    videos only), and whether it's big enough for a channel not to see a
    shot again before ~10 of its videos."""
    from montage import broll
    clips, counts = broll.list_clips(), broll.usage_counts()
    return {"clips": [_serialize_broll(c, counts) for c in clips], "themes": broll.DEFAULT_THEMES,
            "has_key": bool(os.getenv("PIXABAY_API_KEY")),
            "healthy_size": broll.HEALTHY_LIBRARY, "videos_without_repeat": broll.RECENT_PER_CHANNEL // 2}


class BrollFetch(BaseModel):
    theme: str
    count: int = 3


@app.post("/api/broll/fetch")
def fetch_broll(req: BrollFetch):
    from montage import broll
    theme = req.theme.strip()[:60]
    if not theme:
        raise HTTPException(status_code=400, detail="Thème vide")
    try:
        added = broll.fetch(theme, max(1, min(req.count, 6)))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Pixabay : {e}")
    return {"added": [_serialize_broll(c) for c in added], **list_broll()}


@app.delete("/api/broll/{clip_id}")
def delete_broll(clip_id: str):
    from montage import broll
    if not broll.delete(clip_id):
        raise HTTPException(status_code=404, detail="Plan introuvable")
    return list_broll()


@app.get("/api/broll/{clip_id}/thumb")
def broll_thumbnail(clip_id: str):
    from montage import broll
    clip = broll.get_clip(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Plan introuvable")
    path = broll.make_thumbnail(clip)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Miniature indisponible")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/broll/{clip_id}/video")
def broll_video(clip_id: str):
    from montage import broll
    clip = broll.get_clip(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Plan introuvable")
    return FileResponse(broll.clip_path(clip), media_type="video/mp4")


# ---------------------------------------------------------------------------
# Adaptation — Réglages → Voix (the ElevenLabs voice library) and each
# channel's adaptation settings (language, voice, music)
# ---------------------------------------------------------------------------

def _serialize_voice(v: dict) -> dict:
    from adaptation import settings as ad
    return {**{k: v.get(k) for k in ("voice_id", "name", "custom_name", "language", "accent", "gender", "age",
                                       "use_case", "description", "has_preview")},
            "display_name": ad.display_name(v), "preview_url": f"/api/voices/{v['voice_id']}/preview"}


@app.get("/api/voices")
def list_voice_library(language: Optional[str] = None):
    import db as _db
    from adaptation.langs import LANGS
    return {"voices": [_serialize_voice(v) for v in _db.list_voices(language)],
            "languages": {k: v["label"] for k, v in LANGS.items()}}


class VoiceAdd(BaseModel):
    voice_ids: list    # one or several ElevenLabs ids


@app.post("/api/voices")
def add_voices(req: VoiceAdd):
    """Adds voices by id; each is looked up at ElevenLabs (name, language,
    accent, preview). Returns what was added and why the others weren't."""
    from adaptation import settings as ad
    added, failed = [], []
    for vid in [str(v).strip() for v in req.voice_ids if str(v).strip()][:50]:
        try:
            added.append(_serialize_voice(ad.add_voice(vid)))
        except Exception as e:
            failed.append({"voice_id": vid, "error": str(e)[:200]})
    return {"added": added, "failed": failed, **list_voice_library()}


class VoiceRename(BaseModel):
    name: str


@app.patch("/api/voices/{voice_id}")
def rename_voice(voice_id: str, req: VoiceRename):
    from adaptation import settings as ad
    v = ad.rename_voice(voice_id, req.name)
    if not v:
        raise HTTPException(status_code=404, detail="Voix introuvable")
    return _serialize_voice(v)


@app.delete("/api/voices/{voice_id}")
def remove_voice(voice_id: str):
    from adaptation import settings as ad
    if not ad.remove_voice(voice_id):
        raise HTTPException(status_code=404, detail="Voix introuvable")
    return list_voice_library()


@app.get("/api/voices/{voice_id}/preview")
def voice_preview(voice_id: str):
    import db as _db
    from adaptation import settings as ad
    if not _db.get_voice(voice_id) or not os.path.exists(ad.preview_path(voice_id)):
        raise HTTPException(status_code=404, detail="Pas d'extrait pour cette voix")
    return FileResponse(ad.preview_path(voice_id), media_type="audio/mpeg")


def _adaptation_channel_payload(channel_name: str) -> dict:
    from adaptation import settings as ad
    profile = channel_manager.get_channel_profile(channel_name)
    s = ad.channel_settings(profile)
    music_dir = Path(channel_manager.get_assets_dirs(channel_name)["music"])
    music = sorted(p.name for p in music_dir.iterdir() if p.suffix.lower() in MUSIC_EXTENSIONS) \
        if music_dir.exists() else []
    from adaptation.render import STYLES
    return {"settings": s, "music_files": music, "voices": [_serialize_voice(v) for v in ad.voices_for(s["language"])],
            "styles": [{"name": k, "label": v["label"]} for k, v in STYLES.items()]}


@app.get("/api/adaptation/styles/{name}/preview")
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


@app.get("/api/channels/{channel_name}/adaptation")
def get_channel_adaptation(channel_name: str):
    return _adaptation_channel_payload(channel_name)


class ChannelAdaptationUpdate(BaseModel):
    language: Optional[str] = None
    settings: dict = Field(default_factory=dict)


@app.put("/api/channels/{channel_name}/adaptation")
def update_channel_adaptation(channel_name: str, update: ChannelAdaptationUpdate):
    from adaptation import settings as ad
    from adaptation.langs import LANGS
    profile = channel_manager.get_channel_profile(channel_name)
    if update.language is not None:
        if update.language not in LANGS:
            raise HTTPException(status_code=400, detail=f"Langue : {', '.join(LANGS)}")
        profile["language_hint"] = update.language      # also the language of its AI titles
    profile["adaptation"] = {**(profile.get("adaptation") or {}), **ad.clean_update(update.settings)}
    channel_manager.save_channel_profile(channel_name, profile)
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
            report = lambda phase, f: progress.update(key, f, phase=phase)
            if step in ("voicing", "scripting") and only:
                runner(pid, report, only=only)
            else:
                runner(pid, report)
            progress.finish(key)
        except Exception as e:
            progress.finish(key, error=str(e))
    threading.Thread(target=run, daemon=True).start()


def _serialize_adaptation(p: dict, full: bool = True) -> dict:
    import progress
    from adaptation import langs
    job = progress.get(_adaptation_job(p["project_id"])) or {}
    base = {k: p.get(k) for k in ("project_id", "status", "reference_url", "credits", "error", "failed_step",
                                   "created_at", "updated_at")}
    base["mode"] = p.get("mode") or "sources"
    base["annotations_reviewed"] = bool(p.get("annotations_reviewed"))
    base["fetch_note"] = p.get("fetch_note")
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
            "angle": t.get("angle"),
            "preview_url": video_media_url({"video_path": prev["path"]}) if prev.get("path") and os.path.exists(prev["path"]) else None,
            "checks": prev.get("checks"), "final_checks": fin.get("checks"),
            "duration": (prev.get("summary") or {}).get("duration"),
        })
    base["targets"] = targets
    if full:
        ref = p.get("reference") or {}
        base["reference"] = {k: ref.get(k) for k in ("sujet", "question", "credits", "faits_douteux", "duree_s")}
        base["clips"] = [{**{k: c.get(k) for k in ("id", "source", "start", "end", "impact", "desc", "camera", "usable",
                                                  "why_not", "low_res", "audio_ok", "marks", "extrait", "scene", "forced", "note")},
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


@app.post("/api/adaptations")
def create_adaptation(req: AdaptationCreate):
    from adaptation import pipeline as ap
    targets = [{"channel": ch, "profile": channel_manager.get_channel_profile(ch),
                "music_dir": channel_manager.get_assets_dirs(ch)["music"]} for ch in req.channels]
    p = _adaptation_call(ap.create, req.reference_url, req.source_urls, targets, req.mode, req.versions)
    _start_adaptation_step(p["project_id"], "analysing")
    return _serialize_adaptation(p)


@app.get("/api/adaptations")
def list_adaptations():
    import db as _db
    return [_serialize_adaptation(p, full=False) for p in _db.list_adaptations()]


@app.get("/api/adaptations/{pid}")
def get_adaptation(pid: str):
    return _serialize_adaptation(_adaptation_or_404(pid))


@app.delete("/api/adaptations/{pid}")
def delete_adaptation(pid: str):
    import db as _db
    from adaptation import pipeline as ap
    p = _adaptation_or_404(pid)
    if p["status"] in ap.BUSY:
        raise HTTPException(status_code=400, detail="Une étape tourne encore : attends sa fin.")
    shutil.rmtree(ap.project_dir(pid), ignore_errors=True)
    _db.delete_adaptation(pid)
    return {"deleted": True}


@app.get("/api/adaptations/{pid}/frames/{name}")
def adaptation_frame(pid: str, name: str):
    """A clean picture of one of the reference Short's shots (for the manual image search)."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    path = os.path.join(ap.project_dir(pid), "finder", os.path.basename(name))
    if not name.endswith(".jpg") or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Image introuvable")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/adaptations/{pid}/clips/{cid}/thumb")
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


@app.get("/api/adaptations/{pid}/clips/{cid}/video")
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


@app.patch("/api/adaptations/{pid}/sources")
def update_adaptation_sources(pid: str, req: AdaptationSources):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.set_sources, pid, req.usable, req.credits))


class AdaptationAddSources(BaseModel):
    urls: list


@app.post("/api/adaptations/{pid}/sources/add")
def add_adaptation_sources(pid: str, req: AdaptationAddSources):
    """Sources picked among the suggestions (or pasted), analysed on top of the others."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    p = _adaptation_call(ap.add_sources, pid, [str(u) for u in req.urls])
    _start_adaptation_step(pid, "analysing")
    return _serialize_adaptation(p)


class AdaptationCheck(BaseModel):
    url: str


@app.post("/api/adaptations/{pid}/suggestions/check")
def check_adaptation_candidate(pid: str, req: AdaptationCheck):
    """Gemini watches one suggested video against every scene (30 s to 1 min)."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.check_candidate, pid, req.url))


@app.post("/api/adaptations/{pid}/suggestions/own")
def check_adaptation_own_links(pid: str, req: AdaptationAddSources):
    """Your own links, judged by Gemini like the suggestions (1 to 2 min)."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.check_own, pid, [str(u) for u in req.urls]))


class AdaptationAngle(BaseModel):
    index: Optional[int] = None
    custom: Optional[str] = None


@app.post("/api/adaptations/{pid}/angle")
def change_adaptation_angle(pid: str, req: AdaptationAngle):
    """Another angle: the storyboard is written again (about a minute)."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    p = _adaptation_call(ap.change_angle, pid, req.index, req.custom)
    _start_adaptation_step(pid, "analysing")
    return _serialize_adaptation(p)


class AdaptationNewVersion(BaseModel):
    channel: str


@app.post("/api/adaptations/{pid}/targets/{channel}/angle")
def change_adaptation_target_angle(pid: str, channel: str, req: AdaptationAngle):
    """Sources d'abord with versions: another angle for one channel's script (about a minute)."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    p = _adaptation_call(ap.change_target_angle, pid, channel, req.index, req.custom)
    _start_adaptation_step(pid, "scripting", only=channel)
    return _serialize_adaptation(p)


@app.post("/api/adaptations/{pid}/new-version")
def new_adaptation_version(pid: str, req: AdaptationNewVersion):
    """Another channel's version of the same Short, with a new angle."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    ch = {"channel": req.channel, "profile": channel_manager.get_channel_profile(req.channel),
          "music_dir": channel_manager.get_assets_dirs(req.channel)["music"]}
    p = _adaptation_call(ap.new_version, pid, ch)
    _start_adaptation_step(p["project_id"], "analysing")
    return _serialize_adaptation(p)


class AdaptationPlan(BaseModel):
    plan: dict


class AdaptationPlanRevise(BaseModel):
    request: str


@app.put("/api/adaptations/{pid}/targets/{channel}/plan")
def edit_adaptation_plan(pid: str, channel: str, req: AdaptationPlan):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.edit_plan, pid, channel, req.plan))


@app.post("/api/adaptations/{pid}/targets/{channel}/plan/revise")
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


@app.post("/api/adaptations/{pid}/targets/{channel}/plan/approve")
def approve_adaptation_plan(pid: str, channel: str):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.approve_plan, pid, channel))


@app.post("/api/adaptations/{pid}/images")
def start_adaptation_images(pid: str):
    """Script d'abord: search the footage for every plan of the storyboard (3 to 6 min)."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    p = _adaptation_call(ap.start_images, pid)
    _start_adaptation_step(pid, "searching")
    return _serialize_adaptation(p)


class AdaptationPick(BaseModel):
    url: Optional[str] = None
    debut: float = 0.0
    fin: Optional[float] = None


@app.put("/api/adaptations/{pid}/picks/{plan}")
def choose_adaptation_pick(pid: str, plan: int, req: AdaptationPick):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.choose_pick, pid, plan, req.url, req.debut, req.fin))


class AdaptationSkip(BaseModel):
    skip: bool = True


@app.post("/api/adaptations/{pid}/plans/{plan}/skip")
def skip_adaptation_plan(pid: str, plan: int, req: AdaptationSkip):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.skip_plan, pid, plan, req.skip))


class AdaptationLink(BaseModel):
    url: str


@app.post("/api/adaptations/{pid}/plans/{plan}/link")
def check_adaptation_plan_link(pid: str, plan: int, req: AdaptationLink):
    """Your link for one plan, judged by Gemini (15 s to 2 min); it becomes the pick if it fits."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.check_plan_link, pid, plan, req.url))


@app.post("/api/adaptations/{pid}/plans/{plan}/adapt")
def adapt_adaptation_plan(pid: str, plan: int):
    """A plan with no video: rewritten around an image already found."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.adapt_plan, pid, plan))


@app.post("/api/adaptations/{pid}/back-to-images")
def back_to_adaptation_images(pid: str):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.back_to_images, pid))


@app.post("/api/adaptations/{pid}/plans/{plan}/excerpt")
def excerpt_for_adaptation_plan(pid: str, plan: int):
    """Last resort: a few seconds of the reference Short for a plan nobody filmed."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.use_excerpt_for_plan, pid, plan))


@app.post("/api/adaptations/{pid}/scenes/{scene}/excerpt")
def excerpt_for_adaptation_scene(pid: str, scene: int):
    """Last resort (Sources d'abord): a clip of the reference Short for a scene nobody filmed."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.add_excerpt_source, pid, scene))


@app.post("/api/adaptations/{pid}/clips/{cid}/force")
def force_adaptation_clip(pid: str, cid: str):
    """Use a clip the check refused (you have the last word)."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.force_clip, pid, cid))


@app.post("/api/adaptations/{pid}/fetch")
def start_adaptation_fetch(pid: str):
    """Download only the picked moments and make one clip per plan (1 to 4 min)."""
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    p = _adaptation_call(ap.start_fetch, pid)
    _start_adaptation_step(pid, "fetching")
    return _serialize_adaptation(p)


@app.post("/api/adaptations/{pid}/scripts")
def start_adaptation_scripts(pid: str):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    p = _adaptation_call(ap.start_scripts, pid)
    _start_adaptation_step(pid, "scripting")
    return _serialize_adaptation(p)


class AdaptationScript(BaseModel):
    script: dict


@app.put("/api/adaptations/{pid}/targets/{channel}/script")
def edit_adaptation_script(pid: str, channel: str, req: AdaptationScript):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.edit_script, pid, channel, req.script))


class AdaptationRevise(BaseModel):
    request: str


@app.post("/api/adaptations/{pid}/targets/{channel}/revise")
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


@app.post("/api/adaptations/{pid}/targets/{channel}/approve")
def approve_adaptation_script(pid: str, channel: str):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.approve_script, pid, channel))


@app.post("/api/adaptations/{pid}/voices")
def start_adaptation_voices(pid: str):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    p = _adaptation_call(ap.start_voices, pid)
    _start_adaptation_step(pid, "voicing")
    return _serialize_adaptation(p)


class AdaptationVoice(BaseModel):
    voice_id: str


@app.patch("/api/adaptations/{pid}/targets/{channel}/voice")
def change_adaptation_voice(pid: str, channel: str, req: AdaptationVoice):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    p = _adaptation_call(ap.change_voice, pid, channel, req.voice_id)
    _start_adaptation_step(pid, "voicing", only=channel)
    return _serialize_adaptation(p)


@app.post("/api/adaptations/{pid}/targets/{channel}/validate")
def validate_adaptation_preview(pid: str, channel: str):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    return _serialize_adaptation(_adaptation_call(ap.validate_preview, pid, channel))


@app.post("/api/adaptations/{pid}/render")
def start_adaptation_render(pid: str):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    p = _adaptation_call(ap.start_render, pid)
    _start_adaptation_step(pid, "rendering")
    return _serialize_adaptation(p)


@app.post("/api/adaptations/{pid}/retry")
def retry_adaptation(pid: str):
    from adaptation import pipeline as ap
    _adaptation_or_404(pid)
    step = _adaptation_call(ap.retry, pid)
    _start_adaptation_step(pid, step)
    return _serialize_adaptation(_adaptation_or_404(pid))


@app.post("/api/batches/{batch_id}/process")
def process_selected(batch_id: str):
    bp = get_batch_processor()
    count = bp.process_selected_videos(batch_id)
    videos = bp.list_batch_videos(batch_id, status='ready_for_upload')
    return {"processed": count, "videos": [serialize_video(v) for v in videos]}


PROCESS_JOB = "process_selected"
_process_start_lock = threading.Lock()


@app.post("/api/process_selected")
def process_selected_all():
    """Starts processing every 'selected' video (all channels) in a background
    thread and returns at once — it used to be one HTTP request blocking for
    minutes. Progress (real per-frame encoding, then the AI pass) is read
    from GET /api/process_status. A second start while one runs is refused."""
    import progress
    bp = get_batch_processor()
    with _process_start_lock:
        if progress.is_running(PROCESS_JOB):
            return {"started": False, "running": True}
        total = len(bp.list_all_videos(status="selected"))
        if not total:
            return {"started": False, "running": False, "total": 0}
        progress.start(PROCESS_JOB, kind="process", total=total, index=0, title=None, phase="encodage", processed=None)

    def run():
        try:
            processed = bp.process_selected_videos(
                batch_id=None,
                on_progress=lambda i, t, title, phase, f: progress.update(PROCESS_JOB, f, index=i, total=t, title=title, phase=phase),
            )
            progress.finish(PROCESS_JOB, processed=processed)
        except Exception as e:
            progress.finish(PROCESS_JOB, error=str(e))

    threading.Thread(target=run, daemon=True).start()
    return {"started": True, "total": total}


@app.get("/api/process_status")
def process_status():
    """The current/last Import processing run (see process_selected_all)."""
    import progress
    return progress.get(PROCESS_JOB) or {"key": None, "done": True, "processed": None}


class AiRedoRequest(BaseModel):
    instruction: str


@app.post("/api/videos/{video_id}/ai_redo")
def ai_redo(video_id: str, req: AiRedoRequest):
    bp = get_batch_processor()
    video = bp.regenerate_ai_content(video_id, req.instruction)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return serialize_video(video)


class AiDataUpdate(BaseModel):
    optimized_title: Optional[str] = None
    description_suggestions: Optional[list] = None
    tags: Optional[list] = None


@app.patch("/api/videos/{video_id}/ai_data")
def update_ai_data(video_id: str, update: AiDataUpdate):
    bp = get_batch_processor()
    db = bp.url_manager.load_database()
    video = db["videos"].get(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    ai_data = video.get("ai_data", {}) or {}
    for key, value in update.dict(exclude_unset=True).items():
        ai_data[key] = value

    bp.url_manager.update_video_status(video_id, video["status"], ai_data=ai_data)
    return serialize_video(bp.url_manager.load_database()["videos"][video_id])


# ---------------------------------------------------------------------------
# Generative pipeline (script -> voice -> video), for channels with
# "generation_mode": true in their profile.json (e.g. lungtemotivates). This
# runs alongside the curation pipeline above without touching it — it only
# ever produces ordinary `videos` rows, and once one reaches
# status='ready_for_upload' the scheduling/publish code below (and the
# existing dashboard) picks it up exactly like a curated video.
# ---------------------------------------------------------------------------

_generative_pipeline = None
_generative_pipeline_lock = threading.Lock()


def get_generative_pipeline():
    global _generative_pipeline
    if _generative_pipeline is None:
        with _generative_pipeline_lock:
            if _generative_pipeline is None:
                from generative.pipeline import GenerativePipeline
                _generative_pipeline = GenerativePipeline()
    return _generative_pipeline


# Tracks the background thread (if any) currently running a batch's script
# or audio phase, so the UI can tell "still generating" apart from "done, or
# paused waiting on the user" after a page reload — a plain video-status scan
# can't distinguish those (script_generated is both "phase 1 finished, ready
# for review" and "phase 2 hasn't reached this one yet").
_batch_threads: Dict[str, threading.Thread] = {}
_batch_threads_lock = threading.Lock()


def _start_batch_thread(batch_id: str, target) -> bool:
    """Starts `target(batch_id)` in a background thread — unless one is
    already running for this batch (double click, second tab...), since two
    concurrent audio phases would each synthesize every draft and pay
    ElevenLabs twice. Returns whether a new thread was started."""
    with _batch_threads_lock:
        existing = _batch_threads.get(batch_id)
        if existing and existing.is_alive():
            return False
        thread = threading.Thread(target=target, args=(batch_id,), daemon=True)
        _batch_threads[batch_id] = thread
        thread.start()
    return True


@app.get("/api/batches/{batch_id}/active")
def is_batch_active(batch_id: str):
    """Whether a background phase (script or audio generation) is currently
    running for this batch. Polled by the UI so it keeps refreshing across a
    page reload instead of only trusting an in-memory 'I just clicked go'
    flag, which a reload would lose."""
    with _batch_threads_lock:
        thread = _batch_threads.get(batch_id)
    return {"active": bool(thread and thread.is_alive())}


def serialize_generated_video(video: dict) -> dict:
    ai = video.get("ai_data") or {}
    return {
        "video_id": video.get("video_id"),
        "batch_id": video.get("batch_id"),
        "channel": video.get("channel"),
        "status": video.get("status"),
        "script_text": video.get("script_text"),
        "script_format": video.get("script_format"),
        "title": ai.get("optimized_title") or ai.get("title"),
        "description": (ai.get("description_suggestions") or [""])[0],
        "tags": ai.get("tags", []),
        "bg_video_path": video.get("bg_video_path"),
        "bg_music_path": video.get("bg_music_path"),
        "frame_mode": video.get("frame_mode", "fill"),
        "rounded_corners": video.get("rounded_corners", False),
        "caption_style": video.get("caption_style", "karaoke"),
        "caption_color": video.get("caption_color"),
        "words_path": video.get("words_path"),
        "media_url": video_media_url(video),
        "render_error": video.get("render_error"),
        "inspired_by": video.get("inspired_by"),
        "decor_preset": video.get("decor_preset"),
        "progress": _assemble_progress(video),
    }


def _assemble_progress(video: dict):
    if video.get("status") != "assembling":
        return None
    import progress
    return progress.get(f"assemble:{video.get('video_id')}")


def _safe_asset_path(channel_name: str, subfolder: str, filename: str) -> Path:
    """Resolves a user-picked filename to a real file strictly inside that
    channel's assets/<subfolder>/ dir — rejects any attempt at a path outside
    it (this endpoint is reachable from the browser, so filenames are
    untrusted input, not just internal state)."""
    if not filename or "/" in filename or "\\" in filename or filename in ("..", "."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    base = Path(channel_manager.get_assets_dirs(channel_name)[subfolder]).resolve()
    path = (base / filename).resolve()
    if path != base and base not in path.parents:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return path


MAX_BATCH_COUNT = 20


class CreateDraftRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=MAX_BATCH_COUNT)
    inspired_by: Optional[str] = None  # video_id of a top performer to remake ("Refaire ce style")
    # winning choices overriding the model's (Accueil's "idée de la semaine"):
    # {script_format, background, music, caption_style}
    recipe: Optional[Dict[str, str]] = None


@app.post("/api/channels/{channel_name}/generation_draft")
def create_generation_draft(channel_name: str, req: CreateDraftRequest):
    """Phase 1 kickoff: registers `count` draft rows (no decor — that's
    chosen later, per-video, in phase 3) and immediately starts writing their
    scripts in a background thread. The request returns right away; the UI
    polls generated_videos?batch_id=... to watch scripts land. Audio (phase 2)
    and decor+assembly (phase 3) are separate, user-triggered steps."""
    gp = get_generative_pipeline()
    try:
        batch_id = gp.create_draft(channel_name, count=req.count, inspired_by=req.inspired_by,
                                   recipe=req.recipe if req.inspired_by else None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _start_batch_thread(batch_id, gp.run_batch_scripts)
    videos = gp.url_manager.list_videos(batch_id=batch_id)
    return {"batch_id": batch_id, "videos": [serialize_generated_video(v) for v in videos]}


@app.post("/api/videos/{video_id}/generate_script")
def generate_script_for_draft(video_id: str):
    """Writes ONE script (+ title/description/tags) for an existing draft —
    also used to regenerate a script the user doesn't like during review, no
    ElevenLabs call here, so this is cheap to retry/reject."""
    gp = get_generative_pipeline()
    try:
        video = gp.generate_script_for(video_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return serialize_generated_video(video)


@app.post("/api/batches/{batch_id}/generate_audio")
def generate_batch_audio(batch_id: str):
    """Phase 2 kickoff: once scripts have been reviewed/edited, synthesizes
    narration (ElevenLabs, real credits) for every draft in this batch that
    has a script but no audio yet — a background thread, same polling
    pattern as phase 1's script generation."""
    gp = get_generative_pipeline()
    return {"started": _start_batch_thread(batch_id, gp.run_batch_audio)}


@app.post("/api/videos/{video_id}/advance")
def advance_generation_draft(video_id: str):
    """Retries exactly the step that failed on this draft (script, audio, or
    assemble) — single retry endpoint used by the UI instead of it having to
    guess which specific step to re-fire. A no-op if the draft isn't
    currently in rendering_failed."""
    import db as _db
    gp = get_generative_pipeline()
    video = _db.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    # A failed ASSEMBLY (voice + décor already there) is retried in the
    # background with its progress bar, like "Lancer la création" — not in
    # this request, which would block for 1-2 minutes.
    if video.get("status") == "rendering_failed" and video.get("words_path") \
            and video.get("bg_video_path") and video.get("bg_music_path"):
        _start_assembly(gp, video_id)
        return serialize_generated_video(_db.get_video(video_id))
    try:
        video = gp.advance_draft(video_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return serialize_generated_video(video)


GENERATION_DRAFT_STATUSES = {"awaiting_script", "script_generated", "audio_generated", "rendering_failed"}


@app.get("/api/channels/{channel_name}/generated_videos")
def get_generated_videos(channel_name: str, status: Optional[str] = None, batch_id: Optional[str] = None):
    """Without an explicit status or batch_id, only the still-in-progress
    draft(s) are returned — never a completed one. Once a video reaches
    'ready_for_upload' (and anything further downstream: 'uploaded',
    'scheduled_on_youtube') it's done with this page; it's reviewed for
    title/description/tags in the normal 'Résultats IA' wizard step like any
    other video, not re-shown here as history.

    batch_id returns every video in that batch regardless of status — used
    by the batch-progress screen to track its own drafts through to
    ready_for_upload/rendering_failed without picking up unrelated ones."""
    DONE_STATUSES = {"ready_for_upload", "uploaded", "scheduled_on_youtube"}
    gp = get_generative_pipeline()
    if batch_id:
        videos = gp.url_manager.list_videos(batch_id=batch_id)
    elif status:
        videos = gp.url_manager.list_videos(channel=channel_name, status=status)
    else:
        videos = [
            v for v in gp.url_manager.list_videos(channel=channel_name)
            if v.get("source") == "generated" and v.get("status") not in DONE_STATUSES
        ]
    return [serialize_generated_video(v) for v in videos]


@app.delete("/api/videos/{video_id}/generation_draft")
def abandon_generation_draft(video_id: str):
    """Lets the user drop one draft — e.g. a script they don't want to bother
    fixing — deletes the row entirely rather than leaving it orphaned in an
    in-progress status, which would otherwise keep resurfacing from
    generated_videos. Only reachable for drafts still mid-flow: never a video
    that already reached ready_for_upload or beyond."""
    import db as _db
    gp = get_generative_pipeline()
    video = _db.get_video(video_id)
    if not video or video.get("source") != "generated":
        raise HTTPException(status_code=404, detail="Draft not found")
    if video.get("status") not in GENERATION_DRAFT_STATUSES:
        raise HTTPException(status_code=400, detail="This video is no longer an editable draft")
    gp.url_manager.delete_video(video_id)
    return {"deleted": True}


class ScriptUpdate(BaseModel):
    script_text: str


@app.patch("/api/videos/{video_id}/script")
def update_generated_script(video_id: str, update: ScriptUpdate):
    """Edit the script text while it still awaits assets — before render() ever
    fires an ElevenLabs call for it."""
    import db as _db
    gp = get_generative_pipeline()
    gp.update_script(video_id, update.script_text)
    video = _db.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return serialize_generated_video(video)


@app.get("/api/channels/{channel_name}/assets")
def get_channel_assets(channel_name: str):
    """Lists the background videos/music the user has manually dropped into
    channels/<name>/assets/ — nothing here is fetched from an external API."""
    return get_generative_pipeline().list_assets(channel_name)


@app.get("/api/channels/{channel_name}/assets/backgrounds/{filename}")
def get_background_asset(channel_name: str, filename: str):
    return FileResponse(_safe_asset_path(channel_name, "backgrounds", filename))


@app.get("/api/channels/{channel_name}/assets/music/{filename}")
def get_music_asset(channel_name: str, filename: str):
    return FileResponse(_safe_asset_path(channel_name, "music", filename))


@app.get("/api/channels/{channel_name}/asset_frame_preview")
def asset_frame_preview(
    channel_name: str, bg_video_filename: str, frame_mode: str = "fill",
    rounded_corners: bool = False, caption_style: Optional[str] = None, caption_color: Optional[str] = None,
):
    """A composited still frame of a candidate background asset with the
    chosen cadrage — lets the Décor step show what the video will actually
    look like before a script (or anything else) is generated for it.
    caption_style, when given, also overlays a sample of that subtitle style
    (generative.caption_styles) so the whole décor — background AND
    captions — previews together, WYSIWYG. caption_color overrides that
    style's accent color, for the styles that support one."""
    video_path = str(_safe_asset_path(channel_name, "backgrounds", bg_video_filename))
    border_path = channel_manager.get_background_path(channel_name)

    from video_processor import render_frame_preview
    jpeg_bytes = render_frame_preview(
        video_path, frame_mode, border_path, rounded_corners,
        caption_style=caption_style, caption_color=caption_color,
    )
    if not jpeg_bytes:
        raise HTTPException(status_code=500, detail="Preview render failed")
    return Response(content=jpeg_bytes, media_type="image/jpeg")


@app.post("/api/videos/{video_id}/generate_audio")
def generate_audio_for_draft(video_id: str):
    """Synchronous: fires the ElevenLabs TTS call (real credits spent) and
    measures its timing locally (Whisper) — this request blocks for real
    seconds, the UI should say so. Assembly is a separate later step so the
    voice can be reviewed before compositing the final video."""
    import db as _db
    gp = get_generative_pipeline()
    try:
        gp.generate_audio_for(video_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Audio generation failed: {e}")
    return serialize_generated_video(_db.get_video(video_id))


@app.get("/api/videos/{video_id}/narration")
def get_narration_preview(video_id: str):
    """The generated narration audio, so it can be listened to before
    assembling the final video."""
    import db as _db
    video = _db.get_video(video_id)
    if not video or not video.get("narration_path") or not os.path.exists(video["narration_path"]):
        raise HTTPException(status_code=404, detail="No narration generated yet")
    return FileResponse(video["narration_path"])


@app.get("/api/videos/{video_id}/stats_history")
def get_video_stats_history(video_id: str):
    """Every performance snapshot ever captured for this video (see
    stats_tracker.py — 24h/3d/7d/30d checkpoints after publish), plus
    however the publish date was decided (publish_decision: which method,
    and its context — e.g. the channel's analytics peak hours at the time).
    Empty history just means no checkpoint has come due yet, not an error."""
    import db as _db
    video = _db.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    gp = get_batch_processor()
    return {
        "video_id": video_id,
        "publish_decision": video.get("publish_decision"),
        "history": gp.url_manager.get_stats_history(video_id),
    }


class DecorRequest(BaseModel):
    bg_video_filename: str
    bg_music_filename: str
    frame_mode: str = "fill"  # "fill" | "letterbox" | "full_border"
    rounded_corners: bool = False  # independent of frame_mode — combines with any of them
    caption_style: str = "karaoke"  # one of generative.caption_styles.STYLES
    caption_color: Optional[str] = None  # "#rrggbb"; only applies to CUSTOMIZABLE_COLOR_STYLES


@app.post("/api/videos/{video_id}/finalize")
def finalize_generated_video(video_id: str, req: DecorRequest):
    """Phase 3, the per-video 'launch creation' action: assigns the chosen
    background/music/cadrage to this one draft (already scripted and voiced)
    and immediately composites the final video — local/free, no ElevenLabs
    call. Each draft in a batch calls this independently, so they can each
    get their own décor instead of one shared upfront."""
    import db as _db
    video = _db.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    bg_video_path = str(_safe_asset_path(video["channel"], "backgrounds", req.bg_video_filename))
    bg_music_path = str(_safe_asset_path(video["channel"], "music", req.bg_music_filename))

    import progress
    key = f"assemble:{video_id}"
    if video.get("status") == "assembling" or progress.is_running(key):
        raise HTTPException(status_code=409, detail="Création déjà en cours pour cette vidéo")
    if not video.get("words_path"):
        raise HTTPException(status_code=400, detail="Cette vidéo n'a pas encore de voix générée.")

    gp = get_generative_pipeline()
    gp.set_decor(video_id, bg_video_path, bg_music_path, req.frame_mode, req.rounded_corners, req.caption_style, req.caption_color)
    _start_assembly(gp, video_id)
    return serialize_generated_video(_db.get_video(video_id))


def _start_assembly(gp, video_id: str):
    """Rendering takes 1-2 min: runs it in the background (it used to block
    the request the whole time) and exposes the real encoding progress
    under progress key "assemble:<video_id>"."""
    import db as _db
    import progress
    key = f"assemble:{video_id}"
    gp.url_manager.update_video_status(video_id, "assembling", render_error=None)
    progress.start(key, kind="assemble", phase="encodage")

    def run():
        try:
            gp.assemble(video_id, progress_cb=lambda f: progress.update(key, f))
            progress.finish(key)
        except Exception as e:
            # assemble() records rendering_failed for render errors; anything
            # raised before rendering would otherwise leave it "assembling"
            current = _db.get_video(video_id) or {}
            if current.get("status") == "assembling":
                gp.url_manager.update_video_status(video_id, "rendering_failed", render_error=str(e))
            progress.finish(key, error=str(e))

    threading.Thread(target=run, daemon=True).start()


# ---------------------------------------------------------------------------
# Scheduling & publishing
# ---------------------------------------------------------------------------

class ScheduleRequest(BaseModel):
    method: str = "static"  # "static" | "analytics" | "ai"
    target_channel: Optional[str] = None
    max_videos: Optional[int] = None


@app.post("/api/schedule")
def create_schedule(req: ScheduleRequest):
    bp = get_batch_processor()
    schedule = bp.create_upload_schedule(
        max_videos=req.max_videos,
        target_channel=req.target_channel,
        schedule_method=req.method
    )
    return schedule


@app.get("/api/schedule")
def get_schedule():
    """Only videos still genuinely pending — upload_schedule.json is append-only
    and never dropped a video once published, so without this filter the
    'Publier' screen would keep showing already-uploaded videos forever.
    Also self-heals: any 'ready_for_upload' video missing from the schedule
    (processed after the last "Générer le planning" click) gets added first,
    so Planning/Publier never silently omit real, waiting work."""
    data, pending, _ = _pending_schedule(get_batch_processor())
    return {**data, "schedule": pending}


def _pending_schedule(bp):
    """(schedule file data, entries still to publish, db snapshot) — the
    shared basis of the Planning/Publier screens and the pre-publish check."""
    bp.ensure_schedule_includes_all_ready()
    data = bp.scheduler.load_schedule() or {"schedule": []}
    db = bp.url_manager.load_database()
    published_statuses = {"uploaded", "scheduled_on_youtube"}
    pending = [
        e for e in data.get("schedule", [])
        if db.get("videos", {}).get(e.get("video_id"), {}).get("status") not in published_statuses
    ]
    # Show the CURRENT title (what will actually be published — see
    # youtube_uploader.current_video_data), not the copy frozen into
    # upload_schedule.json when the schedule was generated.
    for entry in pending:
        video = db.get("videos", {}).get(entry.get("video_id")) or {}
        current_title = (video.get("ai_data") or {}).get("optimized_title")
        if current_title:
            entry["title"] = current_title
        # Timezone-aware ISO date, so the browser formats it (in French) —
        # scheduled_time_readable is strftime'd in the server's (English)
        # locale, and scheduled_time mixes aware/naive formats.
        try:
            entry["when"] = bp._parse_slot(entry["scheduled_time"]).isoformat()
        except (KeyError, ValueError, TypeError):
            entry["when"] = None
    return data, pending, db


@app.get("/api/publish/preflight")
def publish_preflight():
    """Checks, per channel, everything that would make "Publier tout" fail
    or silently skip videos — BEFORE anything is sent: connection state,
    the Google project's YouTube quota, missing video files, planned dates
    already passed. Read-only on YouTube's side (one cheap channels.list
    call per channel for the connection check, no upload)."""
    import quota
    from youtube_uploader import get_connection_health, current_video_data, effective_scheduled_time

    _, pending, db = _pending_schedule(get_batch_processor())
    by_channel: Dict[str, list] = {}
    for entry in pending:
        channel = entry.get("channel") or (entry.get("video_data") or {}).get("channel", "default")
        by_channel.setdefault(channel, []).append(entry)

    report = []
    for channel, entries in sorted(by_channel.items()):
        health = get_connection_health(channel)
        quota_status = quota.status_for_channel(channel)
        missing_files, missing_ids, past_dates = [], [], []
        for entry in entries:
            video = current_video_data(entry, db)
            path = video.get("video_path")
            if not path or not os.path.exists(path):
                missing_files.append(entry["title"])
                missing_ids.append(entry["video_id"])
            if effective_scheduled_time(entry)[1]:
                past_dates.append(entry["title"])

        blocked = health["state"] != "connected" or quota_status["exhausted"]
        report.append({
            "channel": channel,
            "videos": len(entries),
            "connection": health,
            "quota": quota_status,
            "missing_files": missing_files,
            "missing_ids": missing_ids,
            "past_dates": past_dates,
            "blocked": blocked,
            "publishable": 0 if blocked else len(entries) - len(missing_files),
        })

    # Channels sharing one Google Cloud project share one quota: flag it,
    # so "≈ N uploads left" isn't read as N per channel.
    channels_by_project: Dict[str, list] = {}
    for item in report:
        channels_by_project.setdefault(item["quota"]["project_key"], []).append(item["channel"])
    for item in report:
        item["quota"]["shared_with"] = [c for c in channels_by_project[item["quota"]["project_key"]] if c != item["channel"]]

    return {
        "channels": report,
        "total_videos": sum(i["videos"] for i in report),
        "total_publishable": sum(i["publishable"] for i in report),
    }


class ScheduleEntryUpdate(BaseModel):
    scheduled_time: Optional[str] = None  # "YYYY-MM-DD HH:MM:SS"
    publish_now: Optional[bool] = None  # True: upload immediately as public, ignoring scheduled_time


@app.patch("/api/schedule/{video_id}")
def update_schedule_entry(video_id: str, update: ScheduleEntryUpdate):
    """Manually override one video's proposed date/time (the pencil icon), or
    flag it to publish immediately as public instead of waiting for that date
    (the 'Publier maintenant' toggle) — the two are independent."""
    bp = get_batch_processor()
    data = bp.scheduler.load_schedule()
    if not data:
        raise HTTPException(status_code=404, detail="No schedule yet")

    schedule = data.get("schedule", [])
    entry = next((e for e in schedule if e.get("video_id") == video_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Video not in current schedule")

    if update.scheduled_time is not None:
        try:
            dt = datetime.strptime(update.scheduled_time, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            raise HTTPException(status_code=400, detail="Date invalide (format attendu : AAAA-MM-JJ HH:MM:SS)")
        # A date in the past can't be scheduled on YouTube — refuse it here
        # (e.g. a calendar drag onto yesterday) rather than at publish time.
        from datetime import timezone as _tz
        if bp._parse_slot(update.scheduled_time) <= datetime.now(_tz.utc):
            raise HTTPException(status_code=400, detail="Cette date est déjà passée — choisis un moment dans le futur.")
        entry["scheduled_time"] = update.scheduled_time
        entry["scheduled_time_readable"] = dt.strftime("%A %d/%m/%Y à %H:%M")
        # Overrides whatever automated method decided — the record on the
        # video itself should say so, not keep claiming "analytics"/"ai".
        bp.url_manager.record_publish_decision(video_id, "manual", update.scheduled_time)

    if update.publish_now is not None:
        entry["publish_now"] = update.publish_now

    bp.scheduler.save_schedule(schedule)
    return entry


@app.get("/api/calendar")
def calendar():
    """Everything with a publish date, for the Planning calendar: entries
    still to publish (movable — from the schedule) AND videos already sent
    to YouTube (read-only — their publishAt is YouTube's now), so the
    calendar shows real gaps and overloaded days, not just the pending part.
    Every `when` is a timezone-aware ISO date (the schedule mixes aware and
    naive local strings depending on the method that wrote it)."""
    bp = get_batch_processor()
    _, pending, db = _pending_schedule(bp)

    items = []
    for entry in pending:
        channel = entry.get("channel") or (entry.get("video_data") or {}).get("channel", "default")
        try:
            when = bp._parse_slot(entry["scheduled_time"]).isoformat()
        except (KeyError, ValueError, TypeError):
            continue
        items.append({
            "video_id": entry["video_id"], "channel": channel, "title": entry.get("title"),
            "when": when, "kind": "pending", "publish_now": bool(entry.get("publish_now")),
        })

    from datetime import timezone as _tz
    now = datetime.now(_tz.utc)
    for video in db.get("videos", {}).values():
        status = video.get("status")
        if status not in ("scheduled_on_youtube", "uploaded"):
            continue
        raw = video.get("scheduled_publish_time") if status == "scheduled_on_youtube" else video.get("uploaded_at")
        if not raw:
            continue
        try:
            when_dt = bp._parse_slot(raw)
        except (ValueError, TypeError):
            continue
        # scheduled_on_youtube is never updated locally once YouTube actually
        # publishes the video at its publishAt — past that date it IS published.
        kind = "scheduled" if status == "scheduled_on_youtube" and when_dt > now else "published"
        items.append({
            "video_id": video["video_id"], "channel": video.get("channel"),
            "title": (video.get("ai_data") or {}).get("optimized_title") or video.get("original_title"),
            "when": when_dt.isoformat(), "kind": kind,
            "youtube_url": video.get("youtube_url"), "publish_now": False,
        })

    return {
        "items": items,
        "max_daily_uploads": bp.config["general"]["max_daily_uploads"],
        "spacing_hours": bp.config["scheduling"]["spacing_hours"],
    }


class PublishRequest(BaseModel):
    channel_name: str


@app.post("/api/publish")
def publish(req: PublishRequest):
    bp = get_batch_processor()
    bp.ensure_schedule_includes_all_ready()  # safety net: see ensure_schedule_includes_all_ready docstring
    from youtube_uploader import upload_channel_schedule
    results = upload_channel_schedule(req.channel_name, auto_confirm=True)
    _alert_publish_results(results, req.channel_name)
    return {"results": results}


@app.post("/api/publish_all")
def publish_all():
    """Publish the entire schedule, across every channel it touches — the wizard's
    single final "Publier tout" button."""
    bp = get_batch_processor()
    bp.ensure_schedule_includes_all_ready()  # safety net: see ensure_schedule_includes_all_ready docstring
    from youtube_uploader import upload_all_channels_schedule
    results = upload_all_channels_schedule(auto_confirm=True)
    _alert_publish_results(results)
    return {"results": results}


def _alert_publish_results(results, channel_name=None):
    import alerts
    for r in results:
        try:
            alerts.publish_result(channel_name or r.get("channel"), r)
        except Exception:
            pass


@app.get("/api/alerts")
def list_alerts():
    import alerts
    return alerts.active()


@app.post("/api/alerts/{key:path}/dismiss")
def dismiss_alert(key: str):
    import alerts
    alerts.dismiss(key)
    return {"dismissed": key}


# ---------------------------------------------------------------------------
# Action log
# ---------------------------------------------------------------------------

@app.get("/api/action_log")
def get_action_log(limit: int = 200):
    import db as _db
    return _db.list_action_log(limit=limit)


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------

STATIC_DIR = Path(__file__).parent / "static"


def frontend_build() -> str:
    """Identifies the current page version (index.html's last modification).
    Sent with every API response (X-TikTub-Build) and baked into the page
    when served, so a tab still running an older page — server restarted
    with new code, page not reloaded — notices and asks for a reload
    instead of failing on a changed API answer."""
    return str(int((STATIC_DIR / "index.html").stat().st_mtime))


@app.get("/")
def index():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8").replace("__TIKTUB_BUILD__", frontend_build())
    # never let the browser reuse a stale copy of the app itself
    return HTMLResponse(html, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
