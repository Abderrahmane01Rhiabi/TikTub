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


def test_retention_is_measured_once_over_each_videos_own_first_week(project, bp, monkeypatch):
    project.add_video("old", status="uploaded", youtube_id="Yold", youtube_published_at="2026-01-10T17:00:00")
    project.add_video("fresh", status="uploaded", youtube_id="Yfresh",
                      youtube_published_at=(datetime.now() - timedelta(days=3)).isoformat())
    calls = []
    def fake(channel, videos):
        calls.append(videos)
        return {v["youtube_id"]: {"views": 50, "average_view_percentage": 42.5, "average_view_duration": 17,
                                  "engaged_views": 20} for v in videos}
    monkeypatch.setattr(yu, "get_first_week_retention", fake)
    monkeypatch.setattr(yu, "get_retention_curve", lambda c, y, s: [[0.01, 1.2, 0.5], [1.0, 0.4, 0.5]])

    assert stats_tracker.sync_retention(bp) == 1
    assert calls == [[{"youtube_id": "Yold", "start": "2026-01-10"}]]  # the fresh one waits for its week + processing
    assert db.get_video("old")["retention_7d"]["average_view_percentage"] == 42.5
    assert db.get_video("old")["retention_curve"]["points"][0] == [0.01, 1.2, 0.5]  # the curve is kept with it

    assert stats_tracker.sync_retention(bp) == 0 and len(calls) == 1  # never measured twice


def test_retention_measured_before_engagement_existed_is_measured_again(project, bp, monkeypatch):
    project.add_video("old", status="uploaded", youtube_id="Yold", youtube_published_at="2026-01-10T17:00:00",
                      retention_7d={"views": 50, "average_view_percentage": 42.5})
    monkeypatch.setattr(yu, "get_first_week_retention", lambda c, vs: {v["youtube_id"]: {
        "views": 50, "average_view_percentage": 42.5, "engaged_views": 20, "shares": 2} for v in vs})
    monkeypatch.setattr(yu, "get_retention_curve", lambda c, y, s: [])

    assert stats_tracker.sync_retention(bp) == 1
    assert db.get_video("old")["retention_7d"]["shares"] == 2


def test_first_week_retention_queries_a_7_day_window(monkeypatch, tmp_path):
    seen = []
    class Q:
        def __init__(self, kw): self.kw = kw
        def execute(self):
            seen.append(self.kw)
            if "Yb" in self.kw["filters"]:
                return {"rows": []}
            if self.kw.get("dimensions") == "insightTrafficSourceType":
                return {"rows": [["SHORTS", 60], ["YT_SEARCH", 20]]}
            return {"rows": [[80, 37.2, 15.0, 32, 5, 1, 2, 3, 0]]}
    class Yta:
        def reports(self): return self
        def query(self, **kw): return Q(kw)
    token = tmp_path / "token.json"
    token.write_text("{}")
    monkeypatch.setattr(yu, "get_token_path", lambda c: str(token))
    monkeypatch.setattr(yu, "has_analytics_scope", lambda c: True)
    monkeypatch.setattr(yu.Credentials, "from_authorized_user_file", lambda *a: type("C", (), {"expired": False})())
    monkeypatch.setattr(yu, "build", lambda *a, **k: Yta())

    out = yu.get_first_week_retention("chanA", [{"youtube_id": "Ya", "start": "2026-03-30"},
                                                {"youtube_id": "Yb", "start": "2026-03-30"}])

    assert out["Ya"] == {"views": 80, "average_view_percentage": 37.2, "average_view_duration": 15.0,
                         "engaged_views": 32, "engaged_ratio": 0.4, "likes": 5, "comments": 1, "shares": 2,
                         "subscribers_gained": 3, "subscribers_lost": 0, "shorts_feed_share": 0.75,
                         "sources": {"SHORTS": 60, "YT_SEARCH": 20}}
    assert out["Yb"]["views"] == 0 and out["Yb"]["average_view_percentage"] is None  # nobody watched: measured as 0
    assert (seen[0]["startDate"], seen[0]["endDate"]) == ("2026-03-30", "2026-04-05")
