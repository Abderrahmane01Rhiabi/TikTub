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
