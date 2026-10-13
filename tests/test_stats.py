"""stats_tracker: YouTube status resync and publish-based checkpoints."""

from datetime import datetime, timedelta

import pytest

import db
import stats_tracker
import youtube_uploader as yu

PAST = "2026-01-10T18:00:00+01:00"
FUTURE = "2099-01-10T18:00:00+01:00"


@pytest.fixture
def bp(project):
    from batch_processor import BatchProcessor
    return BatchProcessor("config.yaml")


def fake_stats(monkeypatch, answers):
    """answers: {channel: {youtube_id: live_dict}} — {} = channel unreachable"""
    calls = []
    def get_video_stats(channel, ids):
        calls.append((channel, sorted(ids)))
        return {yid: live for yid, live in answers.get(channel, {}).items() if yid in ids}
    monkeypatch.setattr(yu, "get_video_stats", get_video_stats)
    return calls


def test_resync_records_what_youtube_really_says(project, bp, monkeypatch):
    for vid in ("pub", "priv", "resched", "gone"):
        project.add_video(vid, status="scheduled_on_youtube", youtube_id=f"Y{vid}", scheduled_publish_time=PAST)
    project.add_video("future", status="scheduled_on_youtube", youtube_id="Yfuture", scheduled_publish_time=FUTURE)
    calls = fake_stats(monkeypatch, {"chanA": {
        "Ypub": {"privacy_status": "public", "published_at": "2026-01-10T17:00:03Z"},
        "Ypriv": {"privacy_status": "private", "publish_at": None},
        "Yresched": {"privacy_status": "private", "publish_at": FUTURE},
    }})

    summary = stats_tracker.sync_youtube_statuses(bp)

    assert summary["published"] == 1 and summary["private"] == 1 and summary["rescheduled"] == 1 and summary["deleted"] == 1
    assert db.get_video("pub")["status"] == "uploaded"
    assert db.get_video("pub")["youtube_published_at"] == "2026-01-10T17:00:03Z"
    assert db.get_video("priv")["status"] == "uploaded" and db.get_video("priv")["youtube_privacy"] == "private"
    assert db.get_video("resched")["scheduled_publish_time"] == FUTURE
    assert db.get_video("gone")["status"] == "youtube_deleted"
    assert db.get_video("future")["status"] == "scheduled_on_youtube"  # not due: not even asked
    assert "Yfuture" not in calls[0][1]


def test_unreachable_channel_is_never_marked_deleted(project, bp, monkeypatch):
    project.add_video("v", status="scheduled_on_youtube", youtube_id="Yv", scheduled_publish_time=PAST)
    fake_stats(monkeypatch, {})  # not connected → get_video_stats answers {}

    summary = stats_tracker.sync_youtube_statuses(bp)

    assert summary["unreachable"] == 1 and db.get_video("v")["status"] == "scheduled_on_youtube"


def test_checkpoints_count_from_publication_not_upload():
    now = datetime(2026, 10, 13, 12, 0)
    video = {"uploaded_at": "2026-10-10T12:00:00", "scheduled_publish_time": "2026-10-13T09:00:00"}
    # uploaded 3 days ago but published only 3 hours ago: no checkpoint due yet
    assert stats_tracker._due_checkpoints(video, now, set()) == []
    video["youtube_published_at"] = "2026-10-12T09:00:00"
    assert stats_tracker._due_checkpoints(video, now, set()) == ["24h"]


def test_sync_endpoint(client, project, monkeypatch):
    project.add_video("pub", status="scheduled_on_youtube", youtube_id="Ypub", scheduled_publish_time=PAST)
    fake_stats(monkeypatch, {"chanA": {"Ypub": {"privacy_status": "public", "published_at": None}}})

    assert client.post("/api/sync_youtube_statuses").json()["published"] == 1
    assert db.get_video("pub")["status"] == "uploaded"
