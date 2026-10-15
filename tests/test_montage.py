"""Montage auto engine: plan checking, captions, music envelope, settings
layering, drone library, and one real (tiny, synthetic) ffmpeg render."""

import json
import subprocess
from pathlib import Path

import pytest

from montage import broll, recipes, render

REC = recipes.RECIPES["hopecore"]

# "one two three ... " — 20 words, 0.5 s each, from t=0
WORDS = [(f"w{i}", i * 0.5, i * 0.5 + 0.45) for i in range(20)]


def plan(**fields):
    base = {"garder": [{"debut_s": 0, "fin_s": 10}], "chute_mot": 16,
            "noir": {"debut_mot": 2, "fin_mot": 5}, "drones": {"debut_mot": 10, "fin_mot": 15}}
    base.update(fields)
    return base


# ---------------------------------------------------------------- plan rules

def test_a_sane_plan_keeps_black_screen_and_drones():
    e = render.resolve_plan(plan(), WORDS, REC, duration=10)
    assert e.keep == [(0.0, 10.0)]
    assert e.noir == (1.0, 2.95)
    assert e.drones == (5.0, 7.95) and e.drones[1] <= e.chute == 8.0
    assert not e.notes


def test_black_screen_is_capped_at_three_seconds_and_refused_when_too_short():
    long = render.resolve_plan(plan(noir={"debut_mot": 0, "fin_mot": 9}), WORDS, REC, duration=10)
    assert long.noir == (0.0, 3.0)
    short = render.resolve_plan(plan(noir={"debut_mot": 2, "fin_mot": 2}), WORDS, REC, duration=10)
    assert short.noir is None and short.notes


def test_drones_never_cover_the_punchline_and_last_at_least_two_seconds():
    over = render.resolve_plan(plan(drones={"debut_mot": 14, "fin_mot": 19}), WORDS, REC, duration=10)
    assert over.drones[1] == 8.0                      # cut at the punchline
    assert over.drones[1] - over.drones[0] == pytest.approx(2.0)   # stretched back to 2 s


def test_drones_starting_before_the_end_of_the_black_screen_are_refused():
    # black screen 1.0-3.95, drones asked from 3.0: they would hide it
    e = render.resolve_plan(plan(noir={"debut_mot": 2, "fin_mot": 7}, drones={"debut_mot": 6, "fin_mot": 11}),
                            WORDS, REC, duration=10)
    assert e.noir == (1.0, 3.95) and e.drones is None


def test_garbage_plan_degrades_to_the_whole_clip_without_effects():
    e = render.resolve_plan({"garder": "nope", "noir": {"debut_mot": 99, "fin_mot": 120}, "drones": "x",
                             "chute_mot": "?"}, WORDS, REC, duration=10)
    assert e.keep == [(0.0, 10.0)] and e.noir is None and e.drones is None


def test_kept_ranges_are_sorted_merged_and_mapped_to_output_time():
    e = render.resolve_plan(plan(garder=[{"debut_s": 6, "fin_s": 9}, {"debut_s": 0, "fin_s": 3},
                                         {"debut_s": 2, "fin_s": 4}]), WORDS, REC, duration=10)
    assert e.keep == [(0.0, 4.0), (6.0, 9.0)]
    assert e.total == 7.0
    assert e.to_out(7.0) == 5.0 and e.to_out(5.0) is None


# ------------------------------------------------------------------ captions

def _events(path):
    return [line for line in Path(path).read_text(encoding="utf-8").splitlines() if line.startswith("Dialogue")]


def test_captions_one_word_per_line_and_keywords_in_accent_style(tmp_path):
    e = render.resolve_plan(plan(), WORDS, REC, duration=10)
    n = render.captions_ass(WORDS, e, tmp_path / "c.ass", REC, keywords=[3])
    events = _events(tmp_path / "c.ass")
    assert n == len(events) == 20
    assert [ev for ev in events if ",Key," in ev] == [ev for ev in events if "}w3" in ev]


def test_captions_skip_burned_text_except_where_the_image_is_hidden(tmp_path):
    e = render.resolve_plan(plan(), WORDS, REC, duration=10)
    render.captions_ass(WORDS, e, tmp_path / "c.ass", REC, burned=[(0.0, 4.0)])
    texts = {ev.rsplit("}", 1)[1] for ev in _events(tmp_path / "c.ass")}
    assert "w0" not in texts and "w1" not in texts       # under the clip's own text
    assert {"w2", "w3", "w4", "w5"} <= texts             # black screen hides that text


def test_a_caption_block_never_spans_a_cut_between_kept_ranges(tmp_path):
    words = [("a", 0.0, 0.4), ("b", 0.5, 0.9), ("c", 5.0, 5.4)]
    e = render.resolve_plan({"garder": [{"debut_s": 0, "fin_s": 1}, {"debut_s": 5, "fin_s": 6}]},
                            words, REC, duration=6)
    render.captions_ass(words, e, tmp_path / "c.ass", REC)
    ends = [ev.split(",")[2] for ev in _events(tmp_path / "c.ass")]
    assert ends[0] == ends[1] and ends[0] <= "0:00:01.00"  # a and b leave before c arrives


# --------------------------------------------------------------------- music

def test_music_is_cut_only_during_the_black_screen():
    pts = render.music_keypoints(20.0, (2.0, 4.0), 0.3, 0.12)
    gain = lambda t: next(g0 + (g1 - g0) * (t - t0) / (t1 - t0)
                          for (t0, g0), (t1, g1) in zip(pts, pts[1:]) if t0 <= t < t1)
    assert gain(1.0) == 0.3 and gain(3.0) == 0.0 and gain(10.0) == 0.3 and gain(19.0) == 0.3
    assert 0 < gain(4.06) < 0.3                         # quick ramp back


def test_without_black_screen_the_music_just_plays():
    assert render.music_keypoints(12.0, None, 0.2, 0.12) == [(0, 0.2), (12.0, 0.2)]


# ------------------------------------------------------------------ settings

def test_settings_layer_recipe_then_channel_then_video():
    profile = {"montage": {"caption_style": "cascade", "volume": "marque", "music_file": "song.mp3"}}
    video = {"montage_overrides": {"caption_style": "accent"}}
    s = recipes.resolve_settings(profile, video)
    assert s["caption_style"] == "accent" and s["volume"] == "marque" and s["music_file"] == "song.mp3"
    assert s["music_entry"] == 34.0 and s["recipe"] == "hopecore"


def test_invalid_settings_are_ignored():
    s = recipes.resolve_settings({"montage": {"caption_style": "comic-sans", "volume": 7, "music_entry": "abc",
                                              "recipe": "nope", "unknown": 1}}, None)
    assert s == recipes.DEFAULT_SETTINGS


# ----------------------------------------------------------- drone library

def _fake_library(n, width=1920):
    Path(broll.BROLL_DIR).mkdir(parents=True, exist_ok=True)
    index = []
    for i in range(n):
        (Path(broll.BROLL_DIR) / f"{i}.mp4").write_bytes(b"x")
        index.append({"id": i, "file": f"{i}.mp4", "w": width, "h": 1080, "query": "t"})
    (Path(broll.BROLL_DIR) / "index.json").write_text(json.dumps(index))


def test_pick_avoids_what_the_channel_used_recently():
    _fake_library(6)
    broll.record_usage("chanA", [0, 1, 2, 3])
    for seed in range(10):
        ids = {c["id"] for c in broll.pick("chanA", 2, seed=seed)}
        assert ids <= {4, 5} and len(ids) == 2
    assert len({c["id"] for c in broll.pick("chanB", 2, seed=1)}) == 2   # other channels unaffected


def test_pick_reuses_the_oldest_when_the_library_is_too_small():
    _fake_library(3)
    broll.record_usage("chanA", [0, 1, 2])
    assert [c["id"] for c in broll.pick("chanA", 2, seed=0)] == [0, 1]


def test_low_resolution_clips_are_never_picked():
    _fake_library(2, width=960)
    assert broll.pick("chanA", 2) == []


def test_delete_removes_clip_and_index_entry():
    _fake_library(2)
    assert broll.delete(0) and not broll.delete(0)
    assert [c["id"] for c in broll.list_clips()] == [1]


# ------------------------------------------------------------- real render

def _lavfi(out, src, seconds, extra=()):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *src, "-t", str(seconds), *extra, str(out)], check=True)


def test_preview_render_end_to_end(tmp_path):
    clip, drone, song = tmp_path / "clip.mp4", tmp_path / "drone.mp4", tmp_path / "song.wav"
    _lavfi(clip, ["-f", "lavfi", "-i", "testsrc=size=360x640:rate=30", "-f", "lavfi",
                  "-i", "sine=frequency=300"], 10, ["-c:v", "libx264", "-c:a", "aac", "-shortest"])
    _lavfi(drone, ["-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30"], 6, ["-c:v", "libx264"])
    _lavfi(song, ["-f", "lavfi", "-i", "sine=frequency=500"], 60)
    progress = []
    r = render.render(str(clip), WORDS, plan(accroches=["Hello 😂"]),
                      {**recipes.DEFAULT_SETTINGS, "music_entry": 34}, str(tmp_path / "out.mp4"),
                      [str(drone), str(drone)], keywords=[3], hook="Hello 😂", music_path=str(song),
                      preview=True, progress_cb=progress.append)
    probe = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
         "-of", "json", str(tmp_path / "out.mp4")]))
    v = next(s for s in probe["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (540, 960)
    assert any(s["codec_type"] == "audio" for s in probe["streams"])
    assert float(probe["format"]["duration"]) == pytest.approx(10.0, abs=0.1)
    assert [s["kind"] for s in r["shots"]] == ["noir", "drone", "drone"]
    assert r["music"]["keypoints"][2][1] == 0.0 and progress[-1] == 1.0
    assert not (tmp_path / "out.mp4.part.mp4").exists()


# ------------------------------------------------- drone usage (database)

def test_shots_reserved_by_waiting_videos_of_the_channel_are_skipped(project):
    _fake_library(6)
    project.add_video("a", channel="chanA", status="montage_review", montage={"brolls": [0, 1]})
    project.add_video("b", channel="chanA", status="selected", montage={"brolls": [2, 3], "validated": True})
    project.add_video("c", channel="chanB", status="montage_review", montage={"brolls": [4, 5]})
    for seed in range(10):
        assert {c["id"] for c in broll.pick("chanA", 2, seed=seed)} == {4, 5}
    # a video never blocks itself (re-plan / swap of its own shots)
    assert {0, 1} & {c["id"] for s in range(10) for c in broll.pick("chanA", 2, seed=s, video_id="a")}


def test_a_channel_remembers_its_last_20_shots():
    _fake_library(24)
    for v in range(10):                                   # 10 videos x 2 shots
        broll.record_usage("chanA", [2 * v, 2 * v + 1], f"v{v}")
    for seed in range(10):                                # only the 4 never-used shots are fresh
        assert all(c["id"] >= 20 for c in broll.pick("chanA", 2, seed=seed))


def test_rendering_a_video_again_does_not_count_its_shots_twice():
    _fake_library(3)
    broll.record_usage("chanA", [0, 1], "v1")
    broll.record_usage("chanA", [0, 2], "v1")             # re-render with a swapped shot
    counts = broll.usage_counts()
    assert counts["0"]["total"] == 1 and "1" not in counts and counts["2"]["total"] == 1


def test_old_usage_file_is_moved_into_the_database_once():
    _fake_library(4)
    (Path(broll.BROLL_DIR) / "usage.json").write_text(json.dumps({"chanA": ["0", "1"]}))
    assert {c["id"] for s in range(10) for c in broll.pick("chanA", 2, seed=s)} == {2, 3}
    assert not (Path(broll.BROLL_DIR) / "usage.json").exists()
    assert broll.usage_counts()["0"]["channels"] == {"chanA": 1}


def test_library_lists_how_many_times_each_shot_served(client):
    _fake_library(2)
    broll.record_usage("chanA", [0], "v1")
    broll.record_usage("chanB", [0], "v2")
    data = client.get("/api/broll").json()
    shot = next(c for c in data["clips"] if c["id"] == 0)
    assert shot["uses"] == 2 and shot["uses_by_channel"] == {"chanA": 1, "chanB": 1}
    assert data["healthy_size"] == 30 and data["videos_without_repeat"] == 10
