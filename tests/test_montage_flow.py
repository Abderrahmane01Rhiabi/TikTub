"""Montage auto inside the Import flow: Traiter plans and stops for review,
validation sends the video back to Traiter for its real render, and the
channel/video settings and drone library endpoints."""

import json
from pathlib import Path

import db
from montage import pipeline as montage_pipeline

WORDS = [[f"w{i}", i * 0.5, i * 0.5 + 0.45] for i in range(20)]
PLAN = {"garder": [{"debut_s": 0, "fin_s": 10}], "chute_mot": 16, "noir": {"debut_mot": 2, "fin_mot": 5},
        "drones": {"debut_mot": 10, "fin_mot": 15}, "accroches": ["Hook A 😂", "Hook B", "Hook C"],
        "resume": "un gars raconte"}


def fake_montage(**extra):
    return {"words": WORDS, "plan": PLAN, "keywords": [3], "hooks": PLAN["accroches"], "hook": "Hook A 😂",
            "brolls": [], "validated": False, "error": None, "unsuitable": None, **extra}


def montage_channel(project, name="chanA"):
    project.add_channel(name)
    (Path("channels") / name / "profile.json").write_text(json.dumps({"montage": {"default_mode": "montage"}}))


def add_downloaded(project, vid="v1", **fields):
    Path(f"temp/{vid}").mkdir(parents=True, exist_ok=True)
    Path(f"temp/{vid}/src.mp4").write_bytes(b"x")
    return project.add_video(vid, status="selected", raw_video_path=f"temp/{vid}/src.mp4",
                             original_title="Ma vidéo", **fields)


def test_traiter_plans_a_montage_video_and_stops_for_review(client, project, monkeypatch):
    import webapp.main as m
    montage_channel(project)
    add_downloaded(project)
    bp = m.get_batch_processor()
    monkeypatch.setattr(montage_pipeline, "prepare_review", lambda video, channel, report=None: fake_montage())
    monkeypatch.setattr(bp, "process_tiktok_video", lambda *a, **k: (_ for _ in ()).throw(AssertionError("rendered")))

    assert bp.process_selected_videos() == 0          # nothing finished yet: waiting for the person
    v = db.get_video("v1")
    assert v["status"] == "montage_review" and v["edit_mode"] == "montage"
    shown = client.get("/api/videos?status=montage_review").json()[0]
    assert shown["edit_mode"] == "montage" and shown["montage"]["hooks"][0] == "Hook A 😂"
    kinds = [s["kind"] for s in shown["montage"]["timeline"]["segments"]]
    assert kinds == ["noir", "drone", "drone"] and shown["montage"]["words"][3] == "w3"
    assert shown["montage"]["timeline"]["kept_words"] == list(range(20))   # all kept: 0-10 s


def test_validated_montage_is_rendered_then_goes_through_the_ai_pass(client, project, monkeypatch):
    import webapp.main as m
    montage_channel(project)
    add_downloaded(project)
    db.upsert_video("v1", {**db.get_video("v1"), "status": "montage_review", "montage": fake_montage()})
    bp = m.get_batch_processor()

    r = client.post("/api/videos/v1/montage/validate").json()
    assert r["status"] == "selected" and r["montage"]["validated"]

    rendered = {}

    def fake_render(video, profile, music_dir, out_path, progress_cb=None):
        rendered["hook"] = video["montage"]["hook"]
        Path(out_path).write_bytes(b"mp4")
        progress_cb(1.0)
        return {"duration": 10}
    monkeypatch.setattr(montage_pipeline, "render_final", fake_render)
    monkeypatch.setattr(bp, "generate_ai_content", lambda video, title, video_path=None: {"optimized_title": "T"})

    assert bp.process_selected_videos() == 1
    v = db.get_video("v1")
    assert v["status"] == "ready_for_upload" and v["video_path"].endswith("v1.mp4")
    assert rendered["hook"] == "Hook A 😂" and v["montage"]["summary"] == {"duration": 10}


def test_only_a_video_waiting_for_review_can_be_validated_or_replanned(client, project):
    montage_channel(project)
    add_downloaded(project, montage=fake_montage())
    assert client.post("/api/videos/v1/montage/validate").status_code == 400
    assert client.post("/api/videos/v1/montage/replan").status_code == 400


def test_switching_a_reviewed_video_to_simple_sends_it_back_to_cadrage(client, project):
    montage_channel(project)
    add_downloaded(project)
    db.upsert_video("v1", {**db.get_video("v1"), "status": "montage_review", "montage": fake_montage()})
    r = client.patch("/api/videos/v1/montage", json={"edit_mode": "simple"}).json()
    assert r["status"] == "selected" and r["edit_mode"] == "simple"


def test_review_edits_hook_keywords_and_style_and_drop_the_stale_preview(client, project):
    montage_channel(project)
    add_downloaded(project)
    db.upsert_video("v1", {**db.get_video("v1"), "status": "montage_review",
                           "montage": fake_montage(preview_path="temp/v1/montage/preview.mp4")})
    r = client.patch("/api/videos/v1/montage", json={
        "hook": "  Mon accroche  ", "keywords": [1, 4, 999, "x"],
        "overrides": {"caption_style": "cascade", "volume": "fort", "music_entry": "12.5"}}).json()
    assert r["montage"]["hook"] == "Mon accroche" and r["montage"]["keywords"] == [1, 4]
    assert r["montage_overrides"] == {"caption_style": "cascade", "music_entry": 12.5}
    assert r["montage_settings"]["caption_style"] == "cascade" and r["montage_settings"]["volume"] == "doux"
    assert db.get_video("v1")["montage"]["preview_path"] is None


def test_channel_montage_settings_are_cleaned_and_saved(client, project):
    project.add_channel("chanA")
    r = client.put("/api/channels/chanA/montage", json={"settings": {
        "default_mode": "montage", "caption_style": "accent", "music_file": "../../etc/passwd",
        "volume": "marque", "bogus": 1}}).json()
    assert r["settings"]["default_mode"] == "montage" and r["settings"]["volume"] == "marque"
    assert r["settings"]["music_file"] == "passwd"     # a name inside the music folder, never a path
    saved = json.loads((Path("channels") / "chanA" / "profile.json").read_text())["montage"]
    assert "bogus" not in saved


def test_music_upload_accepts_audio_only(client, project):
    project.add_channel("chanA")
    bad = client.post("/api/channels/chanA/assets/music", files={"file": ("x.exe", b"MZ")})
    assert bad.status_code == 400
    ok = client.post("/api/channels/chanA/assets/music", files={"file": ("Dramamine.mp3", b"ID3")}).json()
    assert ok["music_files"] == ["Dramamine.mp3"]


def test_broll_library_endpoints(client, project):
    from montage import broll
    Path(broll.BROLL_DIR).mkdir(parents=True)
    (Path(broll.BROLL_DIR) / "7.mp4").write_bytes(b"x")
    (Path(broll.BROLL_DIR) / "index.json").write_text(json.dumps([{"id": 7, "file": "7.mp4", "w": 1920, "h": 1080}]))
    assert [c["id"] for c in client.get("/api/broll").json()["clips"]] == [7]
    assert client.get("/api/broll/7/video").status_code == 200
    assert client.get("/api/broll/nope/thumb").status_code == 404
    assert client.delete("/api/broll/7").json()["clips"] == []


def test_restart_puts_a_video_stuck_in_planning_back_to_cadrage(client, project):
    import webapp.main as m
    project.add_video("p", status="montage_planning")
    m.recover_interrupted()
    assert db.get_video("p")["status"] == "selected"


def test_only_words_still_heard_in_the_montage_are_offered_as_keywords(client, project):
    montage_channel(project)
    add_downloaded(project)
    plan = {**PLAN, "garder": [{"debut_s": 0, "fin_s": 4}, {"debut_s": 7, "fin_s": 10}]}
    db.upsert_video("v1", {**db.get_video("v1"), "status": "montage_review", "montage": fake_montage(plan=plan)})
    kept = client.get("/api/videos?status=montage_review").json()[0]["montage"]["timeline"]["kept_words"]
    assert kept == list(range(0, 8)) + list(range(14, 20))
