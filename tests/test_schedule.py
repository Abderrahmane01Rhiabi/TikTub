"""Scheduling: slots, the remembered method, videos added after the fact."""

import pytest

from batch_processor import BatchProcessor
from youtube_scheduler import YouTubeScheduler


@pytest.fixture
def bp(project):
    return BatchProcessor("config.yaml")


def channel_slots(bp, schedule, channel):
    return sorted(bp._parse_slot(e["scheduled_time"]) for e in schedule if e["channel"] == channel)


def gaps_hours(slots):
    return [(b - a).total_seconds() / 3600 for a, b in zip(slots, slots[1:])]


def test_load_schedule_without_any_schedule_yet():
    assert YouTubeScheduler("config.yaml").load_schedule("does_not_exist.json") is None


def test_chosen_method_is_remembered_and_survives_a_plain_save(project, bp):
    project.add_video("v1", title="V1")
    bp.create_upload_schedule(schedule_method="static")
    assert bp.scheduler.load_schedule()["schedule_method"] == "static"

    bp.scheduler.save_schedule(bp.scheduler.load_schedule()["schedule"])  # e.g. a manual date edit
    assert bp.scheduler.load_schedule()["schedule_method"] == "static"


def test_videos_added_later_never_reuse_a_taken_slot(project, bp):
    for i in range(3):
        project.add_video(f"early{i}", title=f"E{i}")
    bp.create_upload_schedule(schedule_method="static")
    for i in range(3):
        project.add_video(f"late{i}", title=f"L{i}")

    combined = bp.ensure_schedule_includes_all_ready()

    slots = channel_slots(bp, combined, "chanA")
    assert len(slots) == 6
    assert all(g >= bp.config["scheduling"]["spacing_hours"] for g in gaps_hours(slots))


def test_mixed_date_formats_are_compared_correctly(project, bp):
    """A manual edit writes a naive local date, 'static' an ISO date with
    timezone — both must be understood as the same kind of instant."""
    project.add_video("early", title="E")
    bp.create_upload_schedule(schedule_method="static")
    data = bp.scheduler.load_schedule()
    entry = data["schedule"][0]
    entry["scheduled_time"] = bp._parse_slot(entry["scheduled_time"]).strftime("%Y-%m-%d %H:%M:%S")
    bp.scheduler.save_schedule(data["schedule"])
    project.add_video("late", title="L")

    combined = bp.ensure_schedule_includes_all_ready()

    slots = channel_slots(bp, combined, "chanA")
    assert gaps_hours(slots)[0] >= bp.config["scheduling"]["spacing_hours"]


def test_other_channels_keep_their_own_first_slots(project, bp):
    project.add_video("a", channel="chanA", title="A")
    project.add_video("b", channel="chanB", title="B")

    schedule = bp.create_upload_schedule(schedule_method="static")

    times = {e["channel"]: e["scheduled_time"] for e in schedule}
    assert times["chanA"] == times["chanB"]  # independent sequences per channel


def test_an_entry_published_right_away_without_time_does_not_break_the_schedule(project, bp):
    """A video published at once stays in the schedule with no time: adding
    a new ready video must not crash on it (Planning showed a 500)."""
    project.add_video("early", title="E")
    bp.create_upload_schedule(schedule_method="static")
    data = bp.scheduler.load_schedule()
    data["schedule"].append({"video_id": "published_now", "channel": "chanA", "scheduled_time": None})
    bp.scheduler.save_schedule(data["schedule"])
    project.add_video("late", title="L")

    combined = bp.ensure_schedule_includes_all_ready()

    assert combined[0]["video_id"] == "published_now"
    assert {e["video_id"] for e in combined} == {"published_now", "early", "late"}


# ---- the "Analytics" and "IA" methods (AUDIT.md §8.3, points 1-2)

@pytest.fixture
def no_analytics_call(monkeypatch):
    """Peak hours and weekdays without asking YouTube Analytics."""
    from smart_scheduler import SmartScheduler
    monkeypatch.setattr(SmartScheduler, "get_channel_peak_times", lambda self, ch, use_cache=True: [8, 12, 18, 20])
    monkeypatch.setattr(SmartScheduler, "get_channel_best_weekdays", lambda self, ch, use_cache=True: [0, 1, 2, 3, 4, 5, 6])


def test_analytics_keeps_each_videos_own_channel(project, bp, no_analytics_call):
    for ch in ("chanA", "chanB", "chanC"):
        for i in range(2):
            project.add_video(f"{ch}_{i}", channel=ch, title=f"{ch} {i}")

    schedule = bp.create_upload_schedule(schedule_method="analytics")

    assert {e["channel"] for e in schedule} == {"chanA", "chanB", "chanC"}
    assert all(e["channel"] == e["video_id"].split("_")[0] for e in schedule)
    saved = bp.scheduler.load_schedule()["schedule"]
    assert "default" not in {e["channel"] for e in saved} and len(saved) == 6
    # each channel has its own slots: the second channel is not pushed after the first one's
    assert channel_slots(bp, schedule, "chanA") == channel_slots(bp, schedule, "chanB") == channel_slots(bp, schedule, "chanC")


def test_analytics_puts_high_priority_first(project, bp, no_analytics_call):
    for vid, prio in (("low", "low"), ("high", "high"), ("normal", "normal")):
        project.add_video(vid, title=vid, priority=prio)

    schedule = bp.create_upload_schedule(schedule_method="analytics")

    order = [e["video_id"] for e in sorted(schedule, key=lambda e: bp._parse_slot(e["scheduled_time"]))]
    assert order == ["high", "normal", "low"]


def test_analytics_never_drops_a_video_silently(project, no_analytics_call):
    from smart_scheduler import SmartScheduler
    videos = [{"video_id": f"v{i}", "channel": "chanA", "title": f"V{i}"} for i in range(25)]   # 5 best weekdays x 4 hours = 20 slots

    result = SmartScheduler().create_analytics_based_schedule(videos, days_ahead=7)

    assert len(result["schedule"]) == 20
    assert [u["video_id"] for u in result["unscheduled"]] == [f"v{i}" for i in range(20, 25)]
    assert all(u["channel"] == "chanA" and u["reason"] for u in result["unscheduled"])


def test_videos_added_later_with_analytics_keep_their_channel_and_spacing(project, bp, no_analytics_call):
    for ch in ("chanA", "chanB"):
        project.add_video(f"{ch}_early", channel=ch, title="E")
    bp.create_upload_schedule(schedule_method="analytics")
    for ch in ("chanA", "chanB"):
        project.add_video(f"{ch}_late", channel=ch, title="L")

    combined = bp.ensure_schedule_includes_all_ready()

    assert {e["video_id"]: e["channel"] for e in combined} == {
        "chanA_early": "chanA", "chanB_early": "chanB", "chanA_late": "chanA", "chanB_late": "chanB"}
    for ch in ("chanA", "chanB"):
        assert all(g >= bp.config["scheduling"]["spacing_hours"] for g in gaps_hours(channel_slots(bp, combined, ch)))


def test_ai_method_keeps_channels_and_enforces_spacing(project, bp):
    project.add_video("a1", channel="chanA", title="A1")
    project.add_video("a2", channel="chanA", title="A2")
    project.add_video("b1", channel="chanB", title="B1")
    asked = []

    class FakeGemini:                                   # no network: the answer Gemini would give
        def call_gemini_api(self, prompt, **kw):
            asked.append(prompt)
            return {"schedule": [{"video_id": "a1", "date": "2030-01-07", "time": "18:00"},
                                 {"video_id": "a2", "date": "2030-01-07", "time": "19:00"}]}   # b1 left out
    bp.ai_scheduler.ai_generator.gemini_ai = FakeGemini()
    bp.ai_scheduler.ai_generator.openai_ai = None

    schedule = bp.create_upload_schedule(schedule_method="ai")

    assert len(asked) == 1
    by_id = {e["video_id"]: e for e in schedule}
    assert {v: e["channel"] for v, e in by_id.items()} == {"a1": "chanA", "a2": "chanA", "b1": "chanB"}
    gap = (bp._parse_slot(by_id["a2"]["scheduled_time"]) - bp._parse_slot(by_id["a1"]["scheduled_time"])).total_seconds() / 3600
    assert gap >= bp.config["scheduling"]["spacing_hours"]       # the AI's 1 h gap is never trusted
    assert by_id["b1"]["scheduled_time"]                           # missing from the answer: still gets a slot


# ---- the common guard (AUDIT.md §4.5 F29-F30): whatever the method, before saving

from collections import Counter
from datetime import datetime, timedelta
import json


def tight_rules(bp, spacing=2, daily=2, weekly=4):
    bp.config["scheduling"]["spacing_hours"] = spacing
    bp.config["general"]["max_daily_uploads"] = daily
    bp.config["general"]["max_weekly_uploads"] = weekly


def fake_method(monkeypatch, bp, method, plan):
    """The chosen method hands back `plan` ({video_id: (channel, local time)}),
    written the way that method writes dates (static: ISO with timezone,
    analytics/ai: naive local)."""
    def entries(videos):
        out = []
        for v in videos:
            if v["video_id"] not in plan:
                continue
            channel, when = plan[v["video_id"]]
            when = bp.scheduler.timezone.localize(when)
            out.append({"video_id": v["video_id"], "title": v["video_id"], "channel": channel, "priority": "normal",
                        "scheduled_time": when.isoformat() if method == "static" else when.strftime("%Y-%m-%d %H:%M:%S"),
                        "scheduled_time_readable": "x", "video_data": v})
        return out
    if method == "static":
        monkeypatch.setattr(bp.scheduler, "create_upload_schedule", lambda videos, channel_manager=None, **k: entries(videos))
    elif method == "analytics":
        monkeypatch.setattr(bp.smart_scheduler, "create_analytics_based_schedule",
                            lambda videos, days_ahead=7: {"schedule": entries(videos), "unscheduled": []})
    else:
        monkeypatch.setattr(bp.ai_scheduler, "create_ai_suggested_schedule",
                            lambda videos, config, channel_manager=None, days_ahead=7: {"schedule": entries(videos)})


def assert_rules_hold(bp, schedule, channel):
    slots = channel_slots(bp, schedule, channel)
    lead = datetime.now(bp.scheduler.timezone) + timedelta(minutes=30)
    tz = bp.scheduler.timezone
    assert all(s >= lead for s in slots)                                         # nothing past / too soon
    assert all(g >= bp.config["scheduling"]["spacing_hours"] for g in gaps_hours(slots))
    assert max(Counter(s.astimezone(tz).date() for s in slots).values()) <= bp.config["general"]["max_daily_uploads"]
    assert max(Counter(s.astimezone(tz).isocalendar()[:2] for s in slots).values()) <= bp.config["general"]["max_weekly_uploads"]


BAD_PLAN = {                       # one past date, two too close, a day over its cap, a week over its cap
    "past": ("chanA", datetime.now().replace(microsecond=0) - timedelta(days=2)),
    "c1": ("chanA", datetime(2030, 1, 7, 18, 0)), "c2": ("chanA", datetime(2030, 1, 7, 18, 30)),
    "d1": ("chanA", datetime(2030, 1, 9, 9, 0)), "d2": ("chanA", datetime(2030, 1, 9, 12, 0)),
    "d3": ("chanA", datetime(2030, 1, 9, 15, 0)),
    "b1": ("chanB", datetime(2030, 1, 7, 18, 0)),                                # another channel: free
}


@pytest.mark.parametrize("method", ["static", "analytics", "ai"])
def test_guard_fixes_past_dates_spacing_and_caps_for_every_method(project, bp, monkeypatch, method):
    tight_rules(bp)
    for vid, (channel, _) in BAD_PLAN.items():
        project.add_video(vid, channel=channel, title=vid)
    fake_method(monkeypatch, bp, method, BAD_PLAN)

    schedule = bp.create_upload_schedule(schedule_method=method)

    saved = bp.scheduler.load_schedule()
    assert {e["video_id"] for e in saved["schedule"]} == set(BAD_PLAN)        # all placed, none lost
    assert all(e["scheduled_time"] for e in saved["schedule"])
    assert saved.get("unscheduled") == []
    assert_rules_hold(bp, schedule, "chanA")
    by_id = {e["video_id"]: bp._parse_slot(e["scheduled_time"]) for e in schedule}
    tz = bp.scheduler.timezone
    for kept in ("c1", "d1", "d2", "b1"):                                     # a slot breaking no rule stays put
        assert by_id[kept] == tz.localize(BAD_PLAN[kept][1])
    assert by_id["past"].astimezone(tz).strftime("%H:%M") == BAD_PLAN["past"][1].strftime("%H:%M")   # same hour, a later day


@pytest.mark.parametrize("method", ["static", "analytics", "ai"])
def test_a_video_already_scheduled_on_youtube_holds_its_slot(project, bp, monkeypatch, method):
    tight_rules(bp, spacing=23, daily=5, weekly=20)
    project.add_video("yt", status="scheduled_on_youtube", scheduled_publish_time="2030-01-07T18:00:00+01:00")
    project.add_video("v1", title="v1")
    fake_method(monkeypatch, bp, method, {"v1": ("chanA", datetime(2030, 1, 7, 20, 0))})   # 2 h after it

    schedule = bp.create_upload_schedule(schedule_method=method)

    yt = bp._parse_slot("2030-01-07T18:00:00+01:00")
    assert abs(bp._parse_slot(schedule[0]["scheduled_time"]) - yt) >= timedelta(hours=23)


def test_guard_runs_on_videos_added_later_too(project, bp, monkeypatch):
    tight_rules(bp, spacing=23, daily=5, weekly=20)
    project.add_video("yt", status="scheduled_on_youtube", scheduled_publish_time="2030-01-07T18:00:00+01:00")
    project.add_video("early", title="early")
    fake_method(monkeypatch, bp, "analytics", {"early": ("chanA", datetime(2030, 1, 9, 18, 0)),
                                               "late": ("chanA", datetime.now() - timedelta(hours=1)),
                                               "late2": ("chanA", datetime(2030, 1, 7, 19, 0))})
    bp.create_upload_schedule(schedule_method="analytics")
    project.add_video("late", title="late")
    project.add_video("late2", title="late2")

    combined = bp.ensure_schedule_includes_all_ready()

    slots = channel_slots(bp, combined, "chanA") + [bp._parse_slot("2030-01-07T18:00:00+01:00")]
    assert {e["video_id"] for e in combined} == {"early", "late", "late2"}
    assert_rules_hold(bp, combined, "chanA")
    assert all(g >= 23 for g in gaps_hours(sorted(slots)))


def test_a_video_impossible_to_place_is_listed_with_its_reason(project, bp, monkeypatch):
    tight_rules(bp, spacing=1, daily=5, weekly=1)                               # one a week: 12 can't all fit
    plan = {f"v{i}": ("chanA", datetime(2030, 1, 7, 9 + i, 0)) for i in range(12)}
    for vid in plan:
        project.add_video(vid, title=vid)
    fake_method(monkeypatch, bp, "static", plan)

    bp.create_upload_schedule(schedule_method="static")

    saved = bp.scheduler.load_schedule()
    placed = {e["video_id"] for e in saved["schedule"]}
    missing = {u["video_id"] for u in saved["unscheduled"]}
    assert placed | missing == set(plan) and not placed & missing and missing
    assert all(e["scheduled_time"] for e in saved["schedule"])
    assert all(u["reason"] and u["channel"] == "chanA" for u in saved["unscheduled"])
    assert_rules_hold(bp, saved["schedule"], "chanA")
    # not retried (nor re-asked to an AI) on every screen load: only at the next "Générer le planning"
    assert {e["video_id"] for e in bp.ensure_schedule_includes_all_ready()} == placed


def test_publish_now_entries_are_left_alone(project, bp, monkeypatch):
    project.add_video("now", title="now")
    project.write_schedule([{"video_id": "now", "channel": "chanA", "title": "now", "publish_now": True,
                             "scheduled_time": "2020-01-01 09:00:00", "video_data": {}}], method="static")
    project.add_video("late", title="late")
    fake_method(monkeypatch, bp, "static", {"late": ("chanA", datetime(2030, 1, 7, 18, 0))})

    combined = bp.ensure_schedule_includes_all_ready()

    assert next(e for e in combined if e["video_id"] == "now")["scheduled_time"] == "2020-01-01 09:00:00"


def test_guard_keeps_the_hour_the_method_chose(project, bp, monkeypatch):
    tight_rules(bp, spacing=23, daily=5, weekly=20)                             # the real config: one a day at 20:00
    project.add_video("yt", status="scheduled_on_youtube", scheduled_publish_time="2030-01-07T17:00:00+01:00")
    project.add_video("v1", title="v1")
    fake_method(monkeypatch, bp, "static", {"v1": ("chanA", datetime(2030, 1, 7, 20, 0))})

    schedule = bp.create_upload_schedule(schedule_method="static")

    assert bp._parse_slot(schedule[0]["scheduled_time"]) == bp.scheduler.timezone.localize(datetime(2030, 1, 8, 20, 0))
