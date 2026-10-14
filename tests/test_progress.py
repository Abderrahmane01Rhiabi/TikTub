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

    def fake_download(url, video_id=None, on_status=None):  # noqa: same signature as the real one
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


@pytest.mark.parametrize("raw, expected", [
    ("\x1b[0;31mERROR:\x1b[0m [Instagram] DcjiGFGsI37: This content isn't available to everyone: It can't be seen by certain audiences.", "accès restreint"),
    ("ERROR: [Instagram] abc: Requested content is not available, rate-limit reached or login required", "privée"),
    ("ERROR: [TikTok] 123: Unable to extract webpage video data; HTTP Error 404: Not Found", "introuvable"),
    ("ERROR: Unsupported URL: https://example.com/x", "Lien non reconnu"),
    ("Aucune vidéo .mp4 récupérée (publication photo/diaporama ?)", "Pas de vidéo"),
])
def test_download_errors_are_explained_in_french_without_color_codes(raw, expected):
    from batch_processor import explain_download_error
    hint, detail = explain_download_error(raw)
    assert expected in hint
    assert "\x1b" not in detail and not detail.startswith("ERROR") and not detail.startswith("[")


def test_unknown_error_keeps_the_cleaned_text():
    from batch_processor import explain_download_error
    hint, detail = explain_download_error("\x1b[0;31mERROR:\x1b[0m [Instagram] x1: Something odd happened")
    assert hint == detail == "Something odd happened"


def test_retrying_a_failed_creation_runs_in_background_too(client, draft_ready_for_decor, monkeypatch):
    import generative.pipeline as gp_mod
    calls = {"n": 0}
    def flaky_render(narration, words, bg, music, out_path, progress_cb=None, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("first try fails")
        progress_cb(1.0)
        Path(out_path).write_bytes(b"mp4")
        return out_path
    monkeypatch.setattr(gp_mod, "render_video", flaky_render)

    client.post("/api/videos/g1/finalize", json=draft_ready_for_decor)
    assert wait_until(lambda: db.get_video("g1")["status"] == "rendering_failed")

    retry = client.post("/api/videos/g1/advance").json()
    assert retry["status"] == "assembling"            # returned at once, not after the render
    assert wait_until(lambda: db.get_video("g1")["status"] == "ready_for_upload")
    assert db.get_video("g1")["render_error"] is None


def test_assembling_counts_as_in_generation_on_home(client, project, monkeypatch):
    import channel_manager
    monkeypatch.setattr(channel_manager.ChannelManager, "list_channels", lambda self: [{"name": "chanA"}])
    project.add_video("g", status="assembling", source="generated")
    assert client.get("/api/overview").json()["totals"]["generating"] == 1


def test_interrupted_download_says_why(client, project):
    import webapp.main as m
    project.add_video("d", status="downloading")
    m.recover_interrupted()
    assert "redémarrage" in db.get_video("d")["error_message"]


@pytest.fixture(scope="module")
def tiny_mp4(tmp_path_factory):
    """A real, readable 1-second video."""
    from moviepy.editor import ColorClip
    path = tmp_path_factory.mktemp("media") / "clip.mp4"
    ColorClip(size=(90, 160), color=(20, 40, 60), duration=1).write_videofile(str(path), fps=5, codec="libx264", audio=False, logger=None)
    return path


def test_dropping_a_file_for_a_failed_link_continues_like_a_download(client, project, tiny_mp4):
    import progress, webapp.main as m
    project.add_video("f1", status="download_failed", url="https://www.instagram.com/p/X/", error_message="Publication à accès restreint")
    progress.start(m.DOWNLOAD_JOB, items=[{"id": "f1", "state": "failed", "message": "restreinte"}])
    progress.finish(m.DOWNLOAD_JOB)

    r = client.post("/api/videos/f1/upload_source", files={"file": ("ma vidéo.mp4", tiny_mp4.read_bytes(), "video/mp4")})

    assert r.status_code == 200 and r.json()["width"] == 90
    v = db.get_video("f1")
    assert v["status"] == "selected" and v["error_message"] is None and v["source_uploaded"]
    assert Path(v["raw_video_path"]).exists() and v["original_title"] == "ma vidéo"
    assert progress.get(m.DOWNLOAD_JOB)["items"][0]["state"] == "done"  # the live list shows it fixed


def test_dropped_file_is_refused_when_it_cannot_be_a_video(client, project):
    project.add_video("f2", status="download_failed")
    project.add_video("ok", status="selected")

    assert client.post("/api/videos/f2/upload_source", files={"file": ("x.pdf", b"%PDF", "application/pdf")}).status_code == 400
    bad = client.post("/api/videos/f2/upload_source", files={"file": ("x.mp4", b"not a video at all", "video/mp4")})
    assert bad.status_code == 400 and "vidéo" in bad.json()["detail"]
    assert not Path("temp/f2/source.mp4").exists()            # the unreadable file isn't kept
    assert db.get_video("f2")["status"] == "download_failed"
    assert client.post("/api/videos/ok/upload_source", files={"file": ("a.mp4", b"x", "video/mp4")}).status_code == 400


def test_video_dimensions_of_an_unreadable_file_are_none(tmp_path):
    """Regression: cv2 reports -1 x -1 for an unreadable file, which the
    helper used to return as real dimensions (also used to suggest framing)."""
    from test3_script import get_video_dimensions, is_decodable_video
    fake = tmp_path / "fake.mp4"
    fake.write_bytes(b"not a video")
    assert get_video_dimensions(str(fake)) == (None, None)
    assert not is_decodable_video(str(fake))
