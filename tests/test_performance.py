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


def test_retention_is_shown_per_video_and_as_a_median_per_group():
    items = [make("b1", 400, "B", retention_7d={"average_view_percentage": 60.0, "average_view_duration": 24}),
             make("b2", 300, "B", retention_7d={"average_view_percentage": 50.0}),
             make("d1", 100, "D", retention_7d={"average_view_percentage": 20.0}),
             make("d2", 120, "D")]  # not measured yet: ignored in medians, never counted as 0

    result = run(items)

    rows = {r["video_id"]: r for r in result["videos"]}
    assert rows["b1"]["retention_7d"] == 60.0 and rows["b1"]["avg_view_duration_7d"] == 24
    assert rows["d2"]["retention_7d"] is None
    assert result["median_retention_7d"] == 50.0
    groups = {g["value"]: g for g in next(i for i in result["insights"] if i["dimension"] == "script_format")["groups"]}
    assert groups["B"]["median_retention_7d"] == 55.0 and groups["D"]["median_retention_7d"] == 20.0


def test_suggestion_picks_a_clear_well_backed_winning_style_with_a_model_video():
    items = [make("b1", 900, "B"), make("b2", 800, "B"), make("b3", 700, "B"),
             make("d1", 100, "D"), make("d2", 120, "D"), make("d3", 110, "D"), make("d4", 90, "D")]
    s = performance.suggest(run(items))
    assert s["dimension"] == "script_format" and s["value"] == "B" and s["count"] == 3
    assert s["video"]["video_id"] == "b1"  # the best remakeable video of that style is the model

    # only 2 videos in the winning group: weak evidence, no suggestion
    assert performance.suggest(run(items[1:])) is None
    # a winning style made only of imports can't be remade
    imported = [make(f"b{i}", 900, "B", source="import") for i in range(3)] + items[3:]
    assert performance.suggest(run(imported)) is None


def test_suggestions_endpoint_only_covers_generation_channels(client, project, monkeypatch):
    import performance as perf
    from webapp import main
    monkeypatch.setattr(main.channel_manager, "list_channels", lambda: [
        {"name": "gen", "generation_mode": True}, {"name": "imp", "generation_mode": False}])
    monkeypatch.setattr(main, "channel_performance", lambda name: {"name": name})
    monkeypatch.setattr(perf, "suggest", lambda a: {"score": 2.0, "from": a["name"]})
    assert client.get("/api/suggestions").json() == [{"channel": "gen", "score": 2.0, "from": "gen"}]


def test_suggestion_carries_the_whole_winning_recipe_and_the_closest_model():
    def v(vid, views, fmt, bg, music, hour):
        return make(vid, views, fmt, bg, bg_music_path=f"m/{music}", published=f"2026-09-01T{hour}:00:00")
    items = [v("b1", 900, "B", "sea.mp4", "calm.mp3", "08"),   # best views, but the losing music and hour
             v("b2", 800, "B", "sea.mp4", "calm.mp3", "19"), v("b3", 700, "B", "sea.mp4", "pop.mp3", "19"),
             v("b4", 650, "B", "city.mp4", "pop.mp3", "19"), v("b5", 600, "B", "city.mp4", "pop.mp3", "19"),
             v("d1", 100, "D", "city.mp4", "calm.mp3", "08"), v("d2", 120, "D", "city.mp4", "calm.mp3", "08"),
             v("d3", 110, "D", "city.mp4", "calm.mp3", "08"), v("d4", 90, "D", "city.mp4", "calm.mp3", "08"),
             v("d5", 95, "D", "city.mp4", "calm.mp3", "08")]
    s = performance.suggest(run(items))

    rec = {r["dimension"]: r for r in s["recipe"]}
    assert rec["script_format"]["value"] == "B" and rec["music"]["value"] == "pop.mp3"
    assert rec["hour_slot"]["value"] == "18h–21h" and not rec["hour_slot"]["from_model"]
    assert s["recipe_values"]["music"] == "pop.mp3" and "hour_slot" not in s["recipe_values"]  # advice only
    # the model shares the most winning choices (b3: B, sea, pop, 19h), not just the most views (b1)
    assert s["video"]["video_id"] == "b3"
    # captions: no evidence on this channel → the model's own, flagged as such
    assert rec["caption_style"]["from_model"] and rec["caption_style"]["score"] is None


def test_recipe_overrides_the_models_decor_and_format(client, project, monkeypatch):
    assets = Path("channels/chanA/assets")
    (assets / "backgrounds").mkdir(parents=True)
    (assets / "music").mkdir(parents=True)
    for f in ("backgrounds/sea.mp4", "backgrounds/city.mp4", "music/calm.mp3", "music/pop.mp3"):
        (assets / f).write_bytes(b"x")
    project.add_video("win", status="uploaded", source="generated", youtube_id="Yw", title="Gagnant",
                      script_text="Jour 1...", script_format="B", caption_style="hormozi", caption_color="#ff0000",
                      bg_video_path=str(assets / "backgrounds/sea.mp4"), bg_music_path=str(assets / "music/calm.mp3"))
    import webapp.main as m
    monkeypatch.setattr(m, "_start_batch_thread", lambda batch_id, target: True)
    recipe = {"background": "city.mp4", "music": "pop.mp3", "caption_style": "karaoke", "script_format": "D"}
    draft = client.post("/api/channels/chanA/generation_draft",
                        json={"count": 1, "inspired_by": "win", "recipe": recipe}).json()["videos"][0]

    p = draft["decor_preset"]
    assert (p["bg_video_filename"], p["bg_music_filename"], p["caption_style"]) == ("city.mp4", "pop.mp3", "karaoke")
    assert p["caption_color"] is None and p["from_recipe"]  # the model's red went with ITS style

    import generative.pipeline as gp_mod
    seen = {}
    monkeypatch.setattr(gp_mod, "generate_script", lambda profile, recent_titles=None, recent_formats=None, inspiration=None:
                        seen.update(inspiration=inspiration) or {"script_text": "n", "title": "N", "format": "D", "tags": []})
    m.get_generative_pipeline().generate_script_for(draft["video_id"])
    assert seen["inspiration"] == {"format": "D"}  # not B's structure: just the winning format

    from generative.script_generator import _build_prompt
    assert 'Indique "D"' in _build_prompt({}, ["ex"], ["t"], ["A"], {"format": "D"})


def adaptation_recipe(duree, hook, plans, mode="script", fleches=0, ralenti=False, sfx=None, voice="v1"):
    details = {"mode": mode, "plans": [{"debut": i, "duree": 1, "fleche": {"type": "fleche"} if i < fleches else None,
                                        "effets_appliques": {"ralenti": ralenti and i == 1}} for i in range(plans)]}
    if sfx is not None:
        details["effets_sonores"] = sfx
    return {"type": "adaptation", "accroche": {"texte": "Q ?", "duree_s": hook},
            "structure": {"duree_s": duree, "plans": plans, "plan_moyen_s": round(duree / plans, 2)},
            "voix": {"id": voice}, "style": {"visuel": "neon"}, "details": details}


def test_the_recipe_of_each_video_is_compared_too():
    items = [make("s1", 400, recette=adaptation_recipe(25, 2.5, 10, fleches=2, ralenti=True, sfx=[{"son": "pop"}])),
             make("s2", 300, recette=adaptation_recipe(28, 2.8, 9, fleches=2, ralenti=True, sfx=[])),
             make("l1", 100, recette=adaptation_recipe(44, 4.6, 6, mode="sources")),
             make("l2", 120, recette=adaptation_recipe(42, 4.2, 6, mode="sources"))]
    insights = {i["dimension"]: i for i in run(items)["insights"]}
    assert insights["duration"]["best"]["value"] == "20 à 30 s" and insights["duration"]["worst"]["value"] == "40 s et plus"
    assert insights["hook"]["best"]["value"] == "2 à 3 s"
    assert insights["mode"]["best"]["value"] == "Script d'abord"
    assert insights["arrows"]["best"]["value"] == "2 flèches ou cercles et plus"
    assert insights["slowmo"]["best"]["value"] == "avec ralenti"
    assert "sfx" not in insights                          # one recipe with, one without, two that never said


def test_a_rebuilt_recipe_gets_its_length_from_the_retention():
    rec = {"type": "import", "structure": {"duree_s": None, "plans": 1}, "accroche": {}}
    v, h = make("i1", 50, recette=rec, retention_7d={"average_view_duration": 9.0, "average_view_percentage": 60.0})
    assert performance.video_row(v, h)["attrs"]["duration"] == "moins de 20 s"            # 9 s watched = 60 % of 15 s
    assert performance.recipe_attrs(None) == {}
