"""Alerts: one per problem, never spammed, cleared when solved."""

import alerts
import db
import quota


def keys():
    return [a["key"] for a in alerts.active()]


def test_an_open_alert_is_never_raised_twice_and_comes_back_only_after_being_solved(project):
    assert alerts.raise_alert("connection:a", "connection", "t", "m1", "a") is True
    assert alerts.raise_alert("connection:a", "connection", "t", "m2", "a") is False  # hourly check: no spam
    assert alerts.active()[0]["message"] == "m2"

    alerts.dismiss("connection:a")
    assert keys() == []
    assert alerts.raise_alert("connection:a", "connection", "t", "m", "a") is False  # still broken: stays hidden

    alerts.resolve("connection:a")
    assert alerts.raise_alert("connection:a", "connection", "t", "m", "a") is True  # broke again later: new alert
    assert keys() == ["connection:a"]


def test_connection_state_opens_and_clears(project):
    alerts.connection_state("chanA", "expired", "invalid_grant")
    assert keys() == ["connection:chanA"] and "invalid_grant" in alerts.active()[0]["message"]
    alerts.connection_state("chanA", "error")      # network hiccup: says nothing either way
    assert keys() == ["connection:chanA"]
    alerts.connection_state("chanA", "connected")
    assert keys() == []


def test_quota_alert_lasts_one_quota_day(project, monkeypatch):
    monkeypatch.setattr(quota, "project_key_for_channel", lambda c: "proj")
    monkeypatch.setattr(quota, "quota_day", lambda: "2026-10-14")
    quota.mark_exhausted("chanA")
    assert keys() == ["quota:proj:2026-10-14"] and db.get_quota_usage("proj", "2026-10-14")["exhausted"]
    monkeypatch.setattr(quota, "quota_day", lambda: "2026-10-15")
    assert keys() == []  # YouTube reset the quota


def test_publish_results_alert_real_failures_only(project):
    alerts.publish_result("chanA", {"video_id": "v1", "title": "T1", "success": False, "error": "Video file not found"})
    alerts.publish_result("chanA", {"video_id": "v2", "success": False, "skipped": True, "error": "quota"})
    assert keys() == ["publish:v1"]
    alerts.publish_result("chanA", {"video_id": "v1", "success": True})  # retried fine
    assert keys() == []


def test_publish_endpoint_raises_alerts_and_they_can_be_dismissed(client, project, monkeypatch):
    import youtube_uploader as yu
    monkeypatch.setattr(yu, "upload_all_channels_schedule", lambda auto_confirm=True: [
        {"video_id": "v1", "title": "T1", "success": False, "error": "Upload failed", "channel": "chanA"}])
    client.post("/api/publish_all")

    listed = client.get("/api/alerts").json()
    assert [a["key"] for a in listed] == ["publish:v1"] and listed[0]["channel"] == "chanA"
    assert client.post("/api/alerts/publish%3Av1/dismiss").status_code == 200
    assert client.get("/api/alerts").json() == []


def test_a_video_gone_from_youtube_raises_an_alert(project, monkeypatch):
    from batch_processor import BatchProcessor
    import stats_tracker
    import youtube_uploader as yu
    project.add_video("gone", status="scheduled_on_youtube", youtube_id="Ygone", scheduled_publish_time="2026-01-10T18:00:00+01:00")
    project.add_video("here", status="scheduled_on_youtube", youtube_id="Yhere", scheduled_publish_time="2026-01-10T18:00:00+01:00")
    monkeypatch.setattr(yu, "get_video_stats", lambda c, ids: {"Yhere": {"privacy_status": "public"}})
    stats_tracker.sync_youtube_statuses(BatchProcessor("config.yaml"))
    assert keys() == ["deleted:gone"]
