"""Génération's "Drones, un plan par phrase" décor and the per-draft voice."""

import json
import random
import time
from pathlib import Path

import db
from generative import drone_montage


def wait_until(cond, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_a_shot_per_sentence_short_ones_merged_long_ones_split_cuts_on_the_beat():
    starts = [0.0, 1.0, 3.0, 4.6, 15.0]          # 1.0: too soon after 0 -> no cut; 4.6->15: too long -> split
    bounds = drone_montage.shot_bounds(starts, 18.0, beats=[2.9, 8.0])
    assert bounds[0] == (0.0, 2.9)               # the 3.0 cut moved onto the beat at 2.9
    assert all(b - a <= drone_montage.SHOT_MAX + 1e-6 for a, b in bounds)
    assert bounds[-1][1] == 18.0 and all(x[1] == y[0] for x, y in zip(bounds, bounds[1:]))


def test_clips_skip_what_the_channel_used_lately_and_are_reserved_at_once(project, monkeypatch):
    from montage import broll
    library = [{"id": i, "file": f"{i}.mp4", "w": 1920, "duration": 20} for i in range(10)]
    monkeypatch.setattr(broll, "list_clips", lambda usable_only=True: library)
    db.record_broll_usage("chanA", [0, 1, 2], "older_video")

    first = drone_montage.choose_clips("chanA", 4, "v1", random.Random(1), fetch_more=False)
    second = drone_montage.choose_clips("chanA", 3, "v2", random.Random(2), fetch_more=False)

    ids1, ids2 = {c["id"] for c in first}, {c["id"] for c in second}
    assert not ids1 & {0, 1, 2} and len(ids1) == 4
    assert not ids2 & ids1 and not ids2 & {0, 1, 2}  # the first video's shots were reserved before it rendered


def test_when_the_library_runs_short_more_shots_are_downloaded(project, monkeypatch):
    from montage import broll
    library = [{"id": 1, "file": "1.mp4", "w": 1920}]
    fetched = []
    def fake_fetch(theme, count=3, api_key=None):
        fetched.append(theme)
        library.extend({"id": 100 + len(library) + k, "file": "x.mp4", "w": 1920} for k in range(count))
    monkeypatch.setattr(broll, "list_clips", lambda usable_only=True: library)
    monkeypatch.setattr(broll, "fetch", fake_fetch)

    chosen = drone_montage.choose_clips("chanA", 5, "v1", random.Random(0))
    assert len({c["id"] for c in chosen}) == 5 and fetched


def draft(project):
    assets = Path("channels/chanA/assets")
    (assets / "music").mkdir(parents=True, exist_ok=True)
    (assets / "music" / "m.mp3").write_bytes(b"x")
    (assets / "backgrounds").mkdir(parents=True, exist_ok=True)
    Path("temp/g1").mkdir(parents=True)
    Path("temp/g1/words.json").write_text(json.dumps([["Bonjour.", 0.0, 1.0], ["Encore.", 2.5, 3.5]]))
    project.add_video("g1", status="audio_generated", source="generated", words_path="temp/g1/words.json",
                      narration_path="temp/g1/narration.mp3", script_text="Bonjour. Encore.")


def test_the_drones_choice_builds_its_background_then_renders_on_it(client, project, monkeypatch):
    import generative.pipeline as gp_mod
    draft(project)
    seen = {}
    def fake_build(words, music, channel, video_id, out_path, seed=None, ffmpeg="ffmpeg"):
        Path(out_path).write_bytes(b"bg")
        return {"look": "doré", "plans": [{"debut": 0.0, "fin": 2.5, "clip": 7}, {"debut": 2.5, "fin": 3.9, "clip": 8}]}
    def fake_render(narration, words, bg, music, out_path, frame_mode=None, **kw):
        seen.update(bg=bg, frame_mode=frame_mode)
        Path(out_path).write_bytes(b"mp4")
        return out_path
    monkeypatch.setattr(gp_mod.drone_montage, "build", fake_build)
    monkeypatch.setattr(gp_mod, "render_video", fake_render)

    r = client.post("/api/videos/g1/finalize", json={"bg_video_filename": "__drones__", "bg_music_filename": "m.mp3",
                                                     "frame_mode": "letterbox"})
    assert r.status_code == 200
    assert wait_until(lambda: db.get_video("g1")["status"] == "ready_for_upload")
    v = db.get_video("g1")
    assert seen["bg"].endswith("drones.mp4") and seen["frame_mode"] == "fill"   # already 9:16: never letterboxed
    assert v["bg_video_path"] == "drones" and v["drones"]["look"] == "doré"
    assert v["recette"]["style"]["fond_video"].startswith("drones") and len(v["recette"]["details"]["plans_drone"]) == 2

    import repetition
    assert repetition.fingerprint(v)["fond"] is None   # a shot per sentence never counts as "the same background"


def test_a_draft_keeps_the_voice_picked_on_its_card(client, project, monkeypatch):
    import generative.pipeline as gp_mod
    project.add_video("s1", status="script_generated", source="generated", script_text="Bonjour.")
    used = []
    def fake_synth(text, voice_id, out_mp3_path, model_id="eleven_v3"):
        Path(out_mp3_path).parent.mkdir(parents=True, exist_ok=True)   # as the real one does
        used.append(voice_id)
        return [("Bonjour.", 0.0, 1.0)]
    monkeypatch.setattr(gp_mod, "synthesize", fake_synth)
    monkeypatch.setattr(db, "get_voice", lambda vid: {"voice_id": vid} if vid == "vF" else None)

    assert client.post("/api/videos/s1/voice", json={"voice_id": "nope"}).status_code == 400
    assert client.post("/api/videos/s1/voice", json={"voice_id": "vF"}).json()["voice_id"] == "vF"
    gp_mod.GenerativePipeline().generate_audio_for("s1")
    assert used == ["vF"] and db.get_video("s1")["voice_id"] == "vF"

    r = client.post("/api/videos/s1/generate_audio", json={"voice_id": "vG"})   # regenerate with another voice
    assert r.status_code == 200 and used[-1] == "vG" and db.get_video("s1")["voice_id"] == "vG"
