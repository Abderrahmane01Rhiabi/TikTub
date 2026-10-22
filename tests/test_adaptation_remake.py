"""« Refaire ce style » for an Adaptation: another model Short made with the
winning video's channels, mode, voices, music and look."""

from pathlib import Path

import pytest

import db
from adaptation import pipeline as ap
from tests.test_adaptation_flow import channel


def published(vid, ch, voice, track, start, style, url="https://youtube.com/shorts/old", mode="script"):
    return {"video_id": vid, "channel": ch, "url": url, "status": "uploaded",
            "recette": {"type": "adaptation", "voix": {"id": voice}, "style": {"visuel": style},
                        "musique": {"fichier": track, "debut_s": start} if track else None,
                        "details": {"mode": mode}}}


def test_style_to_remake_takes_each_versions_own_settings():
    fr = published("v1", "chanA", "v_fr", "epic.mp3", 12.5, "dynamique")
    ar = published("v2", "chanB", "v_ar", "calm.mp3", 3.0, "classique")
    st = ap.style_to_remake(fr, [ar])
    assert st["mode"] == "script" and st["versions"] and st["channels"] == ["chanA", "chanB"]
    assert st["par_chaine"]["chanB"] == {"voice_id": "v_ar", "music_file": "calm.mp3", "music_start": 3.0,
                                         "style": "classique"}


def test_style_to_remake_refuses_other_videos():
    with pytest.raises(ap.PipelineError):
        ap.style_to_remake({"video_id": "g", "recette": {"type": "generation"}}, [])


def test_create_keeps_the_winning_voice_music_and_look(project):
    a = channel(project)
    Path(a["music_dir"]).mkdir(parents=True, exist_ok=True)
    (Path(a["music_dir"]) / "epic.mp3").write_bytes(b"x")
    p = ap.create("https://youtube.com/shorts/new", [], [a], "script", False,
                  {"chanA": {"voice_id": "v_win", "music_file": "epic.mp3", "music_start": 12.5, "style": "dynamique"}},
                  "v1")
    t = p["targets"][0]
    assert t["voice_id"] == "v_win" and t["music_path"].endswith("epic.mp3") and t["music_start"] == 12.5
    assert t["music_chosen"]                                 # no AI choice over the track that worked
    assert ap._style_of(t) == "dynamique"                    # not the channel's look of today
    assert p["remake_of"] == "v1" and p["mode"] == "script"


def test_a_deleted_track_falls_back_to_the_channels_choice(project):
    a = channel(project)
    p = ap.create("https://x", [], [a], "sources", False, {"chanA": {"voice_id": None, "music_file": "gone.mp3"}})
    t = p["targets"][0]
    assert t["voice_id"] == "v_fr" and not t.get("music_chosen") and t["music_path"] is None


def test_remake_endpoint_makes_one_version_per_channel(client, project, monkeypatch):
    import webapp.main as m
    monkeypatch.setattr(m, "_start_adaptation_step", lambda pid, step: None)
    channel(project), channel(project, "chanB", "ar", "v_ar")
    db.upsert_video("v1", published("v1", "chanA", "v_fr", None, None, "dynamique"))
    db.upsert_video("v2", published("v2", "chanB", "v_ar", None, None, "classique"))
    db.upsert_video("v3", published("v3", "chanB", "v_x", None, None, "x", url="https://youtube.com/shorts/other"))

    st = client.get("/api/videos/v1/remake_style").json()
    assert set(st["par_chaine"]) == {"chanA", "chanB"} and st["par_chaine"]["chanB"]["voix_nom"] == "v_ar"

    r = client.post("/api/adaptations/remake", json={"video_id": "v1", "reference_url": "https://youtube.com/shorts/new"})
    assert r.status_code == 200, r.text
    lead = ap.load(r.json()["project_id"])
    group = [lead] + ap.group_of(lead)
    assert {g["targets"][0]["channel"] for g in group} == {"chanA", "chanB"}
    assert all(g["remake_of"] == "v1" and g["reference_url"].endswith("/new") for g in group)
    assert client.post("/api/adaptations/remake", json={"video_id": "nope", "reference_url": "https://x"}).status_code == 404
