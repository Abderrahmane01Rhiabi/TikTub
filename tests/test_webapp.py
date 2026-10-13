"""Web API: connection states, the pre-publish check, and the endpoints
whose behavior was fixed (visibility sync, background-phase dedupe)."""

import threading

import pytest
from google.auth.exceptions import RefreshError

import db
import quota
import youtube_uploader as yu

FUTURE = "2030-01-07T18:00:00+01:00"


def entry(video_id, channel="chanA", when=FUTURE):
    return {"video_id": video_id, "channel": channel, "title": video_id, "scheduled_time": when,
            "scheduled_time_readable": when, "video_data": {}}


# ---- connection states

@pytest.mark.parametrize("setup, expected", [
    ("no_credentials", "missing_credentials"),
    ("no_token", "not_connected"),
    ("refused", "expired"),
    ("network", "error"),
    ("ok", "connected"),
])
def test_connection_status_says_why(client, project, monkeypatch, setup, expected):
    if setup != "no_credentials":
        channel_dir = project.add_channel("chanA")
        if setup != "no_token":
            (channel_dir / "token.json").write_text("{}")

    def fake_title(channel):
        if setup == "refused":
            raise RefreshError("invalid_grant: Bad Request", {"error": "invalid_grant", "error_description": "Bad Request"})
        if setup == "network":
            raise OSError("network unreachable")
        return "My Channel"
    monkeypatch.setattr(yu, "get_connected_channel_title", fake_title)

    status = client.get("/api/channels/chanA/connection_status").json()

    assert status["state"] == expected
    assert status["connected"] == (expected == "connected")
    if expected == "expired":
        assert "Bad Request" in status["reason"]


# ---- pre-publish check

def test_preflight_reports_blocked_channels_missing_files_and_shared_quota(client, project, monkeypatch):
    project.add_channel("chanA", client_id="shared")
    project.add_channel("chanB", client_id="shared")
    project.add_video("a1", channel="chanA", video_path=project.add_video_file("a1.mp4"))
    project.add_video("a2", channel="chanA", video_path="processed_videos/gone.mp4")
    project.add_video("b1", channel="chanB", video_path=project.add_video_file("b1.mp4"))
    project.write_schedule([entry("a1"), entry("a2", when="2020-01-01T09:00:00+01:00"), entry("b1", "chanB")])
    monkeypatch.setattr(yu, "get_connection_health", lambda ch: (
        {"state": "connected", "youtube_channel_title": ch, "reason": None} if ch == "chanA"
        else {"state": "expired", "youtube_channel_title": None, "reason": "invalid_grant"}))

    report = client.get("/api/publish/preflight").json()

    by_channel = {c["channel"]: c for c in report["channels"]}
    assert by_channel["chanA"]["missing_files"] == ["a2"]
    assert by_channel["chanA"]["past_dates"] == ["a2"]
    assert by_channel["chanA"]["publishable"] == 1
    assert by_channel["chanB"]["blocked"] and by_channel["chanB"]["publishable"] == 0
    assert by_channel["chanA"]["quota"]["shared_with"] == ["chanB"]
    assert (report["total_videos"], report["total_publishable"]) == (3, 1)


def test_preflight_blocks_a_project_out_of_quota(client, project, monkeypatch):
    project.add_channel("chanA")
    project.add_video("a1", video_path=project.add_video_file("a1.mp4"))
    project.write_schedule([entry("a1")])
    monkeypatch.setattr(yu, "get_connection_health",
                        lambda ch: {"state": "connected", "youtube_channel_title": ch, "reason": None})
    quota.mark_exhausted("chanA")

    item = client.get("/api/publish/preflight").json()["channels"][0]

    assert item["blocked"] and item["quota"]["exhausted"] and item["publishable"] == 0


def test_schedule_screens_work_before_any_schedule_exists(client, project):
    assert client.get("/api/schedule").json()["schedule"] == []
    assert client.get("/api/publish/preflight").json()["channels"] == []


# ---- fixed endpoints

def test_visibility_change_syncs_the_local_status(client, project, monkeypatch):
    project.add_video("v1", status="scheduled_on_youtube", youtube_id="YT1")
    monkeypatch.setattr(yu, "update_video_visibility", lambda ch, yid, privacy, at=None: {"privacyStatus": privacy})

    response = client.patch("/api/channels/chanA/videos/YT1/visibility", json={"privacy_status": "public"})

    assert response.json() == {"privacy_status": "public", "publish_at": None}
    assert db.get_video("v1")["status"] == "uploaded"


def test_a_second_background_phase_is_refused_while_one_runs(client):
    import webapp.main as m
    release = threading.Event()
    runs = []

    def slow_phase(batch_id):
        runs.append(batch_id)
        release.wait(5)

    assert m._start_batch_thread("B", slow_phase) is True
    assert m._start_batch_thread("B", slow_phase) is False
    release.set()
    m._batch_threads["B"].join(5)
    assert m._start_batch_thread("B", lambda b: runs.append(b)) is True
    m._batch_threads["B"].join(5)
    assert runs == ["B", "B"]


# ---- Accueil overview

def test_overview_counts_each_stage_per_channel(client, project, monkeypatch):
    import channel_manager
    monkeypatch.setattr(channel_manager.ChannelManager, "list_channels",
                        lambda self: [{"name": "chanA"}, {"name": "chanB"}])
    project.add_video("s1", status="selected")
    project.add_video("s2", status="selected")
    project.add_video("r1", status="ready_for_upload")
    project.add_video("g1", status="script_generated")
    project.add_video("e1", status="download_failed", error_message="404")
    project.add_video("p1", status="scheduled_on_youtube", scheduled_publish_time="2030-01-07T18:00:00+01:00")
    project.add_video("p0", status="scheduled_on_youtube", scheduled_publish_time="2020-01-07T18:00:00+01:00")
    project.add_video("b1", channel="chanB", status="ready_for_upload")
    project.add_video("x1", channel="unknown_channel", status="ready_for_upload")

    data = client.get("/api/overview").json()

    a = next(c for c in data["channels"] if c["channel"] == "chanA")
    assert a["counts"] == {"to_sort": 2, "generating": 1, "ready": 1, "in_progress": 0, "errors": 1, "scheduled": 1}
    assert a["errors"] == [{"video_id": "e1", "url": "https://t/e1", "title": None,
                            "status": "download_failed", "message": "404"}]
    assert a["next_publish"].startswith("2030-01-07")
    assert data["totals"]["ready"] == 2  # chanA + chanB; unknown channels are ignored
    assert "uploads_today" in a["quota"]


def test_dismissing_a_failed_video_removes_it_from_errors(client, project):
    project.add_video("e1", status="download_failed")
    project.add_video("ok", status="ready_for_upload")

    assert client.post("/api/videos/e1/dismiss").json() == {"dismissed": True}
    assert db.get_video("e1")["status"] == "rejected"
    assert client.post("/api/videos/ok/dismiss").status_code == 400  # not an error: untouched
    assert db.get_video("ok")["status"] == "ready_for_upload"


# ---- Planning calendar

def test_calendar_lists_pending_and_youtube_scheduled_with_aware_dates(client, project):
    project.add_video("p1", status="ready_for_upload")
    project.add_video("s1", status="scheduled_on_youtube", scheduled_publish_time="2030-02-01T18:00:00+01:00",
                      ai_data={"optimized_title": "Déjà programmée"})
    project.add_video("u1", status="uploaded", uploaded_at="2026-10-01T10:00:00")
    project.write_schedule([{"video_id": "p1", "channel": "chanA", "title": "À publier",
                             "scheduled_time": "2030-01-07 18:00:00", "video_data": {}}])

    data = client.get("/api/calendar").json()

    by_id = {i["video_id"]: i for i in data["items"]}
    assert by_id["p1"]["kind"] == "pending" and by_id["p1"]["when"].startswith("2030-01-07T18:00:00+")
    assert by_id["s1"]["kind"] == "scheduled" and by_id["s1"]["title"] == "Déjà programmée"
    assert by_id["u1"]["kind"] == "published"
    assert data["max_daily_uploads"] > 0 and data["spacing_hours"] > 0


def test_schedule_edit_rejects_past_and_malformed_dates(client, project):
    project.add_video("p1", status="ready_for_upload")
    project.write_schedule([{"video_id": "p1", "channel": "chanA", "title": "x",
                             "scheduled_time": "2030-01-07 18:00:00", "video_data": {}}])

    assert client.patch("/api/schedule/p1", json={"scheduled_time": "2020-01-01 09:00:00"}).status_code == 400
    assert client.patch("/api/schedule/p1", json={"scheduled_time": "demain"}).status_code == 400
    ok = client.patch("/api/schedule/p1", json={"scheduled_time": "2030-01-09 18:00:00"})
    assert ok.status_code == 200 and ok.json()["scheduled_time"] == "2030-01-09 18:00:00"


def test_calendar_treats_past_youtube_schedules_as_published(client, project):
    project.add_video("old", status="scheduled_on_youtube", scheduled_publish_time="2020-05-01T18:00:00+02:00")
    project.add_video("future", status="scheduled_on_youtube", scheduled_publish_time="2030-05-01T18:00:00+02:00")

    kinds = {i["video_id"]: i["kind"] for i in client.get("/api/calendar").json()["items"]}

    assert kinds == {"old": "published", "future": "scheduled"}
