"""
Shared test setup — every test runs in its own throwaway data directory
(fresh SQLite DB, schedule, channels/), never the real project data, and
never reaches a real AI/TTS provider or YouTube.

Run:  .venv/bin/python -m pytest
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# load_dotenv() (called at import time by ai_tags_generator and the
# generative modules) never overrides a variable that already exists, so
# these empty values win over the real .env: no test can call Gemini,
# OpenAI or ElevenLabs.
for _key in ("GEMINI_API_KEY", "OPENAI_API_KEY", "ELEVENLABS_API_KEY"):
    os.environ[_key] = ""

# webapp.main chdirs into its data dir when first imported (by the `client`
# fixture): point it at a throwaway one, so import-time side effects (dirs
# created, ChannelManager init) never touch the real project. No chdir here
# at conftest load: pytest resolves `testpaths` AFTER loading this file, and
# moving the cwd away made it miss tests/ and crawl the project root instead.
_SESSION_DIR = tempfile.mkdtemp(prefix="tiktub-tests-")
shutil.copy(ROOT / "config.yaml.example", Path(_SESSION_DIR) / "config.yaml")
os.environ["TIKTUB_DATA_DIR"] = _SESSION_DIR


def _import_webapp_once():
    """Imports webapp.main exactly once, with its import-time chdir landing
    in the throwaway session dir, then restores the cwd — so no test ever
    finds itself moved out of its own tmp dir by a first import."""
    if "webapp.main" in sys.modules:
        return sys.modules["webapp.main"]
    cwd = os.getcwd()
    try:
        import webapp.main as m
    finally:
        os.chdir(cwd)
    return m


class Project:
    """Helpers over the per-test data directory."""

    def __init__(self, root: Path):
        self.root = root

    def add_video(self, video_id, channel="chanA", status="ready_for_upload", **fields):
        import db
        video = {"video_id": video_id, "batch_id": "b1", "channel": channel, "url": f"https://t/{video_id}",
                 "status": status, "priority": "normal", **fields}
        db.upsert_video(video_id, video)
        return video

    def add_video_file(self, name):
        path = Path("processed_videos") / name
        path.write_bytes(b"fake mp4")
        return str(path)

    def add_channel(self, name, client_id="client-A"):
        """A channel whose credentials.json comes from the Google Cloud
        project identified by client_id (fake — never used for real auth)."""
        channel_dir = Path("channels") / name
        channel_dir.mkdir(parents=True, exist_ok=True)
        (channel_dir / "credentials.json").write_text(json.dumps({"installed": {"client_id": client_id}}))
        return channel_dir

    def write_schedule(self, entries, method=None):
        with open("upload_schedule.json", "w", encoding="utf-8") as f:
            json.dump({"schedule_method": method, "schedule": entries}, f)


@pytest.fixture(autouse=True)  # every test runs in a throwaway dir, never the real project
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    shutil.copy(ROOT / "config.yaml.example", tmp_path / "config.yaml")
    (tmp_path / "processed_videos").mkdir()
    (tmp_path / "channels").mkdir()

    import db
    db.init_db()

    # webapp.main keeps module-level singletons: rebuild them for this dir
    if "webapp.main" in sys.modules:
        m = sys.modules["webapp.main"]
        from channel_manager import ChannelManager
        monkeypatch.setattr(m, "CONFIG_PATH", tmp_path / "config.yaml")
        monkeypatch.setattr(m, "_batch_processor", None)
        monkeypatch.setattr(m, "channel_manager", ChannelManager())
        m._batch_threads.clear()

    return Project(tmp_path)


@pytest.fixture
def client(project):
    """FastAPI test client (startup events — the stats tracker — not run)."""
    from fastapi.testclient import TestClient
    m = _import_webapp_once()
    from channel_manager import ChannelManager
    m.CONFIG_PATH = project.root / "config.yaml"
    m._batch_processor = None
    m.channel_manager = ChannelManager()
    m._batch_threads.clear()
    return TestClient(m.app)


class FakeYouTube:
    """Minimal stand-in for the googleapiclient YouTube service: records each
    videos().insert() call and answers with a fake id, or raises the given
    errors in order (one per call, None = succeed)."""

    def __init__(self, errors=None):
        self.inserted = []
        self.errors = list(errors or [])

    def videos(self):
        return self

    def insert(self, part, body, media_body):
        self.inserted.append(body)
        return self

    def execute(self):
        error = self.errors.pop(0) if self.errors else None
        if error:
            raise error
        return {"id": f"yt{len(self.inserted)}"}


def quota_http_error(reason="quotaExceeded"):
    import httplib2
    from googleapiclient.errors import HttpError
    content = json.dumps({"error": {"code": 403, "message": reason, "errors": [{"reason": reason}]}}).encode()
    return HttpError(httplib2.Response({"status": 403}), content)


@pytest.fixture
def fake_youtube(monkeypatch):
    """Makes every channel look connected and routes uploads to a FakeYouTube
    (through the REAL upload_video, so quota recording and DB updates are
    exercised for real)."""
    import youtube_uploader as yu
    service = FakeYouTube()
    monkeypatch.setattr(yu, "get_connection_health",
                        lambda ch: {"state": "connected", "youtube_channel_title": ch, "reason": None})
    monkeypatch.setattr(yu, "authenticate_youtube", lambda ch, interactive=True: service)
    return service
