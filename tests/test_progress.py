"""Real progress bars: encoding callbacks → fraction, background jobs."""

import json
import threading
from pathlib import Path

import pytest

import db
import progress


def wait_until(pred, timeout=5):
    import time
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


def test_encoding_callbacks_become_a_fraction():
    seen = []
    logger = progress.EncodeProgress(seen.append)
    logger.state["bars"] = {"chunk": {"total": 10}, "t": {"total": 20}}
    logger.bars_callback("chunk", "index", 10)   # audio fully written
    logger.bars_callback("t", "index", 10)       # half the frames
    logger.bars_callback("t", "index", 20)       # all frames
    logger.bars_callback("t", "total", 20)       # non-index updates ignored
    assert seen == pytest.approx([progress.AUDIO_SHARE, progress.AUDIO_SHARE + (1 - progress.AUDIO_SHARE) / 2, 1.0])


def test_eta_appears_once_there_is_enough_progress():
    progress.start("job-eta")
    assert progress.get("job-eta")["eta_seconds"] is None
    progress.update("job-eta", 0.5)
    assert progress.get("job-eta")["eta_seconds"] is not None
    progress.finish("job-eta")
    job = progress.get("job-eta")
    assert job["done"] and job["fraction"] == 1.0 and job["eta_seconds"] is None


@pytest.fixture
def draft_ready_for_decor(project):
    assets = Path("channels/chanA/assets")
    for sub, name in (("backgrounds", "bg.mp4"), ("music", "m.mp3")):
        (assets / sub).mkdir(parents=True, exist_ok=True)
        (assets / sub / name).write_bytes(b"x")
    Path("temp/g1").mkdir(parents=True)
    Path("temp/g1/words.json").write_text(json.dumps([["Bonjour", 0.0, 1.0]]))
    project.add_video("g1", status="audio_generated", source="generated", words_path="temp/g1/words.json",
                      narration_path="temp/g1/narration.mp3")
    return {"bg_video_filename": "bg.mp4", "bg_music_filename": "m.mp3"}


def test_creation_runs_in_background_with_real_progress(client, draft_ready_for_decor, monkeypatch):
    import generative.pipeline as gp_mod
    halfway, release = threading.Event(), threading.Event()

    def fake_render(narration, words, bg, music, out_path, progress_cb=None, **kw):
        progress_cb(0.5)
        halfway.set()
        release.wait(5)
        Path(out_path).write_bytes(b"mp4")
        return out_path
    monkeypatch.setattr(gp_mod, "render_video", fake_render)

    first = client.post("/api/videos/g1/finalize", json=draft_ready_for_decor)
    assert first.status_code == 200 and first.json()["status"] == "assembling"  # returned at once
    assert halfway.wait(5)

    running = [v for v in client.get("/api/channels/chanA/generated_videos").json() if v["video_id"] == "g1"][0]
    assert running["status"] == "assembling" and running["progress"]["fraction"] == 0.5
    assert client.post("/api/videos/g1/finalize", json=draft_ready_for_decor).status_code == 409  # no double render

    release.set()
    assert wait_until(lambda: db.get_video("g1")["status"] == "ready_for_upload")
    assert progress.get("assemble:g1")["done"]


def test_a_failed_creation_is_reported_not_left_running(client, draft_ready_for_decor, monkeypatch):
    import generative.pipeline as gp_mod
    def broken_render(*a, **kw):
        raise RuntimeError("ffmpeg exploded")
    monkeypatch.setattr(gp_mod, "render_video", broken_render)

    client.post("/api/videos/g1/finalize", json=draft_ready_for_decor)

    assert wait_until(lambda: db.get_video("g1")["status"] == "rendering_failed")
    assert "ffmpeg exploded" in db.get_video("g1")["render_error"]
    assert wait_until(lambda: progress.get("assemble:g1")["done"])


def test_import_processing_runs_in_background(client, project, monkeypatch):
    import webapp.main as m
    Path("temp/v1").mkdir(parents=True)
    Path("temp/v1/src.mp4").write_bytes(b"x")
    project.add_video("v1", status="selected", raw_video_path="temp/v1/src.mp4", original_title="Ma vidéo")
    bp = m.get_batch_processor()
    halfway, release = threading.Event(), threading.Event()

    def fake_process(raw, title, bg_mode, specific_bg=None, frame_mode=None, rounded=False, output_name=None, progress_cb=None):
        progress_cb(0.5)
        halfway.set()
        release.wait(5)
        return f"processed_videos/{output_name}.mp4"
    monkeypatch.setattr(bp, "process_tiktok_video", fake_process)
    monkeypatch.setattr(bp, "generate_ai_content", lambda video, title, video_path=None: {"optimized_title": "T"})

    assert client.post("/api/process_selected").json() == {"started": True, "total": 1}
    assert halfway.wait(5)
    status = client.get("/api/process_status").json()
    assert not status["done"] and status["title"] == "Ma vidéo" and status["phase"] == "encodage"
    assert status["fraction"] == pytest.approx(bp.PROCESS_ENCODE_SHARE * 0.5)
    assert client.post("/api/process_selected").json()["running"] is True  # no second run

    release.set()
    assert wait_until(lambda: client.get("/api/process_status").json()["done"])
    assert client.get("/api/process_status").json()["processed"] == 1
    assert db.get_video("v1")["status"] == "ready_for_upload"


def test_restart_puts_interrupted_videos_back_where_they_can_be_relaunched(client, project):
    import webapp.main as m
    project.add_video("a", status="assembling", source="generated")
    project.add_video("p", status="processing")
    project.add_video("t", status="generating_tags")
    project.add_video("ok", status="ready_for_upload")

    assert m.recover_interrupted() == 3

    assert db.get_video("a")["status"] == "audio_generated"
    assert db.get_video("p")["status"] == "selected" and db.get_video("t")["status"] == "selected"
    assert db.get_video("ok")["status"] == "ready_for_upload"


def test_downloads_run_in_background_and_report_every_link(client, project, monkeypatch):
    import webapp.main as m
    bp = m.get_batch_processor()
    project.add_video("old", status="ready_for_upload", url="https://t/dup")       # already imported on chanA
    for n, url in ((1, "https://t/ok"), (2, "https://t/photo"), (3, "https://t/dup")):
        project.add_video(f"b_{n}", batch_id="B", status="pending", url=url, line_number=n)
    gate = threading.Event()

    def fake_download(url, video_id=None, on_status=None):
        on_status("téléchargement 50 %")
        if url.endswith("photo"):
            return None, None, {"download_error": "Aucune vidéo .mp4 récupérée (publication photo/diaporama ?)"}
        gate.wait(5)
        return f"temp/{video_id}/v.mp4", "Titre", {}
    monkeypatch.setattr(bp, "download_tiktok_video", fake_download)

    assert client.post("/api/downloads", json={"batch_ids": ["B"]}).json() == {"started": True, "total": 3}
    assert wait_until(lambda: client.get("/api/download_status").json()["items"][0]["message"] == "téléchargement 50 %")
    running = client.get("/api/download_status").json()
    assert not running["done"] and running["items"][0]["state"] == "running"
    assert client.post("/api/downloads", json={"batch_ids": ["B"]}).json()["running"] is True

    gate.set()
    assert wait_until(lambda: client.get("/api/download_status").json()["done"])
    items = {i["url"]: i for i in client.get("/api/download_status").json()["items"]}
    assert items["https://t/ok"]["state"] == "done"
    assert items["https://t/photo"]["state"] == "failed" and "photo" in items["https://t/photo"]["message"]
    assert items["https://t/dup"]["state"] == "duplicate"
    assert client.get("/api/download_status").json()["fraction"] == 1.0
    assert db.get_video("b_1")["status"] == "selected" and db.get_video("b_2")["status"] == "download_failed"


def test_interrupted_download_ends_as_a_visible_failure(client, project):
    import webapp.main as m
    project.add_video("d", status="downloading")
    m.recover_interrupted()
    assert db.get_video("d")["status"] == "download_failed"
