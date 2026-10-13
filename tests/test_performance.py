"""Top performers: 7-day comparison, channel-median scoring, groups, remake."""

import os
from pathlib import Path

import db
import performance


def make(vid, views, fmt=None, bg=None, published="2026-09-01T18:00:00", source="generated", **extra):
    video = {"video_id": vid, "channel": "chanA", "source": source, "youtube_id": "Y" + vid,
             "youtube_published_at": published, "title": f"T{vid}", "script_text": "s",
             "script_format": fmt, "bg_video_path": bg and f"channels/chanA/assets/backgrounds/{bg}", **extra}
    history = [{"checkpoint": "24h", "view_count": views // 3}, {"checkpoint": "7d", "view_count": views, "like_count": views // 10}]
    return video, history


def run(items):
    return performance.analyze([v for v, _ in items], {v["video_id"]: h for v, h in items})


def test_ranks_by_views_at_7_days_and_scores_against_the_channel_median():
    items = [make("a", 100, "B"), make("b", 300, "B"), make("c", 200, "D")]
    items.append(({"video_id": "new", "channel": "chanA", "youtube_id": "Ynew"}, [{"checkpoint": "24h", "view_count": 999}]))

    result = run(items)

    assert result["analyzed"] == 3 and result["too_recent"] == 1  # no 7d snapshot yet → not compared
    assert result["median_views_7d"] == 200
    assert [r["video_id"] for r in result["videos"]] == ["b", "c", "a"]
    assert [r["score"] for r in result["videos"]] == [1.48, 1.0, 0.52]  # (views+10)/(median+10)
    assert result["videos"][0]["like_rate"] == 0.1


def test_groups_need_two_videos_and_show_what_beats_the_median():
    items = [make("b1", 400, "B", "sea.mp4"), make("b2", 300, "B", "sea.mp4"), make("b3", 350, "B", "city.mp4"),
             make("d1", 100, "D", "city.mp4"), make("d2", 120, "D", "city.mp4"), make("a1", 900, "A", "sea.mp4")]

    insights = {i["dimension"]: i for i in run(items)["insights"]}

    fmt = insights["script_format"]
    assert [g["value"] for g in fmt["groups"]] == ["B", "D"]  # "A" has a single video: not a pattern
    assert fmt["best"]["label"] == "B · Storytime" and fmt["best"]["reliable"]
    assert not fmt["worst"]["reliable"]  # only 2 videos
    assert insights["background"]["best"]["value"] == "sea.mp4"


def test_endpoint_uses_only_this_channels_published_videos(client, project):
    project.add_video("pub", youtube_id="Y1", status="uploaded", youtube_published_at="2026-09-01T10:00:00")
    project.add_video("other", channel="chanB", youtube_id="Y2", status="uploaded")
    project.add_video("draft", status="ready_for_upload")
    db.insert_stats_snapshot("pub", "7d", {"view_count": 50, "like_count": 5})

    data = client.get("/api/channels/chanA/performance").json()

    assert data["analyzed"] == 1 and data["videos"][0]["video_id"] == "pub"


def test_remake_presets_the_decor_and_feeds_the_winner_to_the_script_prompt(client, project, monkeypatch):
    assets = Path("channels/chanA/assets")
    (assets / "backgrounds").mkdir(parents=True)
    (assets / "music").mkdir(parents=True)
    (assets / "backgrounds" / "sea.mp4").write_bytes(b"x")
    project.add_video("win", status="uploaded", source="generated", youtube_id="Yw", title="Le titre gagnant",
                      script_text="[calm] 3 signes...", script_format="D",
                      bg_video_path=str(assets / "backgrounds" / "sea.mp4"),
                      bg_music_path=str(assets / "music" / "deleted.mp3"),  # no longer in assets
                      caption_style="typewriter", frame_mode="letterbox")

    import webapp.main as m
    started = []
    monkeypatch.setattr(m, "_start_batch_thread", lambda batch_id, target: started.append(batch_id) or True)
    data = client.post("/api/channels/chanA/generation_draft", json={"count": 2, "inspired_by": "win"}).json()

    drafts = data["videos"]
    assert len(drafts) == 2 and all(d["inspired_by"] == "win" for d in drafts)
    preset = drafts[0]["decor_preset"]
    assert preset["bg_video_filename"] == "sea.mp4" and preset["bg_music_filename"] is None
    assert preset["caption_style"] == "typewriter" and preset["frame_mode"] == "letterbox"

    # the winner reaches the script prompt
    import generative.pipeline as gp_mod
    seen = {}
    def fake_generate_script(profile, recent_titles=None, recent_formats=None, inspiration=None):
        seen["inspiration"] = inspiration
        return {"script_text": "nouveau", "title": "Nouveau", "format": "D", "tags": []}
    monkeypatch.setattr(gp_mod, "generate_script", fake_generate_script)
    m.get_generative_pipeline().generate_script_for(drafts[0]["video_id"])
    assert seen["inspiration"] == {"format": "D", "title": "Le titre gagnant", "script_text": "[calm] 3 signes..."}


def test_remake_refuses_a_video_from_another_channel_or_not_generated(client, project):
    project.add_video("imported", status="uploaded", youtube_id="Y")
    assert client.post("/api/channels/chanA/generation_draft", json={"count": 1, "inspired_by": "imported"}).status_code == 400


def test_prompt_asks_for_same_format_new_topic():
    from generative.script_generator import _build_prompt
    prompt = _build_prompt({}, ["ex"], ["Ancien titre"], ["A", "B"], {"format": "B", "title": "Gagnant", "script_text": "Jour 1..."})
    assert "Gagnant" in prompt and 'même format ("B")' in prompt and "SUJET doit être différent" in prompt
    assert "sous-représenté" not in prompt  # the least-used-format nudge would fight the winner's format
