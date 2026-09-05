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
from typing import Optional
from urllib.parse import quote

# Make sure the project root (parent of webapp/) is importable regardless of
# how uvicorn was invoked.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)  # all existing modules use relative paths (channels/, database/, temp/...)

from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from channel_manager import ChannelManager

CONFIG_PATH = PROJECT_ROOT / "config.yaml"

app = FastAPI(title="TikTub")
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
    }


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------

@app.get("/api/channels")
def list_channels():
    return channel_manager.list_channels()


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
    from youtube_uploader import get_connected_channel_title, has_edit_scope
    try:
        title = get_connected_channel_title(channel_name)
    except Exception:
        title = None
    return {
        "connected": title is not None,
        "youtube_channel_title": title,
        "can_edit": has_edit_scope(channel_name) if title is not None else False,
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

    from test3_script import render_frame_preview
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


@app.post("/api/batches/{batch_id}/process")
def process_selected(batch_id: str):
    bp = get_batch_processor()
    count = bp.process_selected_videos(batch_id)
    videos = bp.list_batch_videos(batch_id, status='ready_for_upload')
    return {"processed": count, "videos": [serialize_video(v) for v in videos]}


@app.post("/api/process_selected")
def process_selected_all():
    """Process every 'selected' video across all channels/batches at once."""
    bp = get_batch_processor()
    count = bp.process_selected_videos(batch_id=None)
    videos = bp.list_all_videos(status='ready_for_upload')
    return {"processed": count, "videos": [serialize_video(v) for v in videos]}


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


def serialize_generated_video(video: dict) -> dict:
    ai = video.get("ai_data") or {}
    return {
        "video_id": video.get("video_id"),
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
        "words_path": video.get("words_path"),
        "media_url": video_media_url(video),
        "render_error": video.get("render_error"),
    }


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


class CreateDraftRequest(BaseModel):
    bg_video_filename: str
    bg_music_filename: str
    frame_mode: str = "fill"  # "fill" | "letterbox" | "full_border"
    rounded_corners: bool = False  # independent of frame_mode — combines with any of them


@app.post("/api/channels/{channel_name}/generation_draft")
def create_generation_draft(channel_name: str, req: CreateDraftRequest):
    """Step 1 of the generative flow: register the user's chosen background
    video + music + frame style — nothing is written or generated yet, so
    nothing is imposed on them before they've made these choices."""
    bg_video_path = str(_safe_asset_path(channel_name, "backgrounds", req.bg_video_filename))
    bg_music_path = str(_safe_asset_path(channel_name, "music", req.bg_music_filename))

    gp = get_generative_pipeline()
    batch_id = gp.create_draft(channel_name, bg_video_path, bg_music_path, req.frame_mode, req.rounded_corners)
    videos = gp.url_manager.list_videos(batch_id=batch_id)
    return {"batch_id": batch_id, "videos": [serialize_generated_video(v) for v in videos]}


@app.post("/api/videos/{video_id}/generate_script")
def generate_script_for_draft(video_id: str):
    """Step 2: writes ONE script (+ title/description/tags) for an existing
    draft, via the LLM cascade — no ElevenLabs call here, so this step is
    cheap to retry/reject."""
    gp = get_generative_pipeline()
    try:
        video = gp.generate_script_for(video_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return serialize_generated_video(video)


@app.get("/api/channels/{channel_name}/generated_videos")
def get_generated_videos(channel_name: str, status: Optional[str] = None):
    """Without an explicit status, only the still-in-progress draft(s) are
    returned — never a completed one. Once a video reaches
    'ready_for_upload' (and anything further downstream: 'uploaded',
    'scheduled_on_youtube') it's done with this page; it's reviewed for
    title/description/tags in the normal 'Résultats IA' wizard step like any
    other video, not re-shown here as history."""
    DONE_STATUSES = {"ready_for_upload", "uploaded", "scheduled_on_youtube"}
    gp = get_generative_pipeline()
    if status:
        videos = gp.url_manager.list_videos(channel=channel_name, status=status)
    else:
        videos = [
            v for v in gp.url_manager.list_videos(channel=channel_name)
            if v.get("source") == "generated" and v.get("status") not in DONE_STATUSES
        ]
    return [serialize_generated_video(v) for v in videos]


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
def asset_frame_preview(channel_name: str, bg_video_filename: str, frame_mode: str = "fill", rounded_corners: bool = False):
    """A composited still frame of a candidate background asset with the
    chosen cadrage — lets the Décor step show what the video will actually
    look like before a script (or anything else) is generated for it."""
    video_path = str(_safe_asset_path(channel_name, "backgrounds", bg_video_filename))
    border_path = channel_manager.get_background_path(channel_name)

    from test3_script import render_frame_preview
    jpeg_bytes = render_frame_preview(video_path, frame_mode, border_path, rounded_corners)
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


@app.post("/api/videos/{video_id}/assemble")
def assemble_generated_video(video_id: str):
    """Composites the final video from the already-generated narration —
    local/free, no ElevenLabs call."""
    import db as _db
    gp = get_generative_pipeline()
    try:
        gp.assemble(video_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Assembly failed: {e}")
    return serialize_generated_video(_db.get_video(video_id))


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
    bp = get_batch_processor()
    bp.ensure_schedule_includes_all_ready()
    data = bp.scheduler.load_schedule() or {"schedule": []}
    db = bp.url_manager.load_database()
    published_statuses = {"uploaded", "scheduled_on_youtube"}
    pending = [
        e for e in data.get("schedule", [])
        if db.get("videos", {}).get(e.get("video_id"), {}).get("status") not in published_statuses
    ]
    return {**data, "schedule": pending}


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
        dt = datetime.strptime(update.scheduled_time, "%Y-%m-%d %H:%M:%S")
        entry["scheduled_time"] = update.scheduled_time
        entry["scheduled_time_readable"] = dt.strftime("%A %d/%m/%Y à %H:%M")

    if update.publish_now is not None:
        entry["publish_now"] = update.publish_now

    bp.scheduler.save_schedule(schedule)
    return entry


class PublishRequest(BaseModel):
    channel_name: str


@app.post("/api/publish")
def publish(req: PublishRequest):
    bp = get_batch_processor()
    bp.ensure_schedule_includes_all_ready()  # safety net: see ensure_schedule_includes_all_ready docstring
    from youtube_uploader import upload_channel_schedule
    results = upload_channel_schedule(req.channel_name, auto_confirm=True)
    return {"results": results}


@app.post("/api/publish_all")
def publish_all():
    """Publish the entire schedule, across every channel it touches — the wizard's
    single final "Publier tout" button."""
    bp = get_batch_processor()
    bp.ensure_schedule_includes_all_ready()  # safety net: see ensure_schedule_includes_all_ready docstring
    from youtube_uploader import upload_all_channels_schedule
    results = upload_all_channels_schedule(auto_confirm=True)
    return {"results": results}


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


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
