"""Publishing: what actually gets sent to YouTube, and what happens when
something (file, connection, quota) gets in the way."""

from datetime import datetime, timedelta, timezone

import db
import quota
import youtube_uploader as yu
from conftest import quota_http_error

FUTURE = "2030-01-07T18:00:00+01:00"


def schedule_entry(video_id, channel="chanA", title="old title", when=FUTURE, **extra):
    return {"video_id": video_id, "channel": channel, "title": title, "scheduled_time": when,
            "scheduled_time_readable": when, "video_data": {"ai_data": {"optimized_title": title}}, **extra}


# ---- the right file, the right metadata

def test_missing_file_is_never_replaced_by_another_one(project):
    project.add_video_file("someone_else.mp4")
    assert yu.find_matching_video_file("processed_videos/gone.mp4", {"original_title": "someone else"}) is None


def test_upload_publishes_the_current_title_not_the_schedule_copy(project, fake_youtube):
    project.add_channel("chanA")
    path = project.add_video_file("v1.mp4")
    project.add_video("v1", video_path=path, ai_data={"optimized_title": "edited title", "tags": ["a"]})
    project.write_schedule([schedule_entry("v1", title="old title")])

    results = yu.upload_channel_schedule("chanA")

    assert [r["success"] for r in results] == [True]
    assert fake_youtube.inserted[0]["snippet"]["title"] == "edited title"


def test_missing_file_fails_only_that_video(project, fake_youtube):
    project.add_channel("chanA")
    project.add_video("v1", video_path="processed_videos/gone.mp4")
    project.add_video("v2", video_path=project.add_video_file("v2.mp4"))
    project.write_schedule([schedule_entry("v1"), schedule_entry("v2")])

    results = {r["video_id"]: r for r in yu.upload_channel_schedule("chanA")}

    assert results["v1"]["error"] == "Video file not found" and not results["v1"]["success"]
    assert results["v2"]["success"]
    assert len(fake_youtube.inserted) == 1


def test_post_upload_write_touches_only_its_own_row(project):
    path = project.add_video_file("v1.mp4")
    project.add_video("v1", video_path=path)
    project.add_video("other", status="script_generated", script_text="before")
    # a background thread writes this row while the upload is in flight
    db.upsert_video("other", {**db.get_video("other"), "script_text": "written meanwhile"})

    assert yu.update_video_status("v1", "https://y/1", "yt1", scheduled_time=FUTURE)

    assert db.get_video("other")["script_text"] == "written meanwhile"
    assert db.get_video("v1")["status"] == "scheduled_on_youtube"
    assert db.get_video("v1")["youtube_id"] == "yt1"


# ---- connection

def test_expired_channel_skips_each_video_without_trying_to_upload(project, fake_youtube, monkeypatch):
    project.add_channel("chanA")
    for vid in ("v1", "v2"):
        project.add_video(vid, video_path=project.add_video_file(f"{vid}.mp4"))
    project.write_schedule([schedule_entry("v1"), schedule_entry("v2")])
    monkeypatch.setattr(yu, "get_connection_health",
                        lambda ch: {"state": "expired", "youtube_channel_title": None, "reason": "invalid_grant"})

    results = yu.upload_channel_schedule("chanA")

    assert [(r["video_id"], r["skipped"]) for r in results] == [("v1", True), ("v2", True)]
    assert "expirée" in results[0]["error"]
    assert fake_youtube.inserted == []
    assert db.get_video("v1")["status"] == "ready_for_upload"


def test_authenticate_never_blocks_on_a_login_from_the_web_app(project):
    project.add_channel("chanA")  # credentials but no token: the CLI would open a local OAuth server
    assert yu.authenticate_youtube("chanA", interactive=False) is None


# ---- quota

def test_quota_exceeded_stops_the_run_and_blocks_the_whole_project(project, fake_youtube):
    project.add_channel("chanA", client_id="shared-project")
    project.add_channel("chanB", client_id="shared-project")
    for vid, ch in (("a1", "chanA"), ("a2", "chanA"), ("a3", "chanA"), ("b1", "chanB")):
        project.add_video(vid, channel=ch, video_path=project.add_video_file(f"{vid}.mp4"))
    project.write_schedule([schedule_entry("a1"), schedule_entry("a2"), schedule_entry("a3"),
                            schedule_entry("b1", channel="chanB")])
    fake_youtube.errors = [None, quota_http_error("quotaExceeded")]

    results = yu.upload_all_channels_schedule()

    by_id = {r["video_id"]: r for r in results}
    assert by_id["a1"]["success"]
    assert by_id["a2"]["skipped"] and by_id["a3"]["skipped"]
    assert by_id["b1"]["skipped"], "same Google project: chanB must not even try"
    assert len(fake_youtube.inserted) == 2  # a1 ok, a2 refused, then nothing else
    assert quota.is_exhausted("chanA") and quota.is_exhausted("chanB")
    # the held-back videos stay ready for the next run
    assert db.get_video("a2")["status"] == "ready_for_upload"


def test_channel_upload_limit_does_not_block_the_other_channels_of_the_project(project, fake_youtube):
    project.add_channel("chanA", client_id="shared-project")
    project.add_channel("chanB", client_id="shared-project")
    project.add_video("a1", channel="chanA", video_path=project.add_video_file("a1.mp4"))
    project.add_video("b1", channel="chanB", video_path=project.add_video_file("b1.mp4"))
    project.write_schedule([schedule_entry("a1"), schedule_entry("b1", channel="chanB")])
    fake_youtube.errors = [quota_http_error("uploadLimitExceeded")]

    by_id = {r["video_id"]: r for r in yu.upload_all_channels_schedule()}

    assert by_id["a1"]["skipped"]
    assert by_id["b1"]["success"]
    assert not quota.is_exhausted("chanB")


def test_successful_uploads_are_counted_for_the_project(project, fake_youtube):
    project.add_channel("chanA", client_id="p1")
    project.add_video("a1", video_path=project.add_video_file("a1.mp4"))
    project.write_schedule([schedule_entry("a1")])

    yu.upload_channel_schedule("chanA")

    status = quota.status_for_channel("chanA")
    assert status["uploads_today"] == 1
    assert status["units_used_estimate"] == quota.load_settings()["upload_cost"]


def test_the_estimate_alone_never_blocks_an_upload(project, fake_youtube):
    project.add_channel("chanA", client_id="p1")
    db.add_quota_usage(quota.project_key_for_channel("chanA"), quota.quota_day(), 999_999, uploads=500)
    project.add_video("a1", video_path=project.add_video_file("a1.mp4"))
    project.write_schedule([schedule_entry("a1")])

    assert yu.upload_channel_schedule("chanA")[0]["success"]


def test_http_error_reason_is_read_from_the_api_answer():
    assert yu.http_error_reason(quota_http_error("quotaExceeded")) == "quotaExceeded"


# ---- dates

def test_a_planned_date_already_passed_is_published_immediately():
    past = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    when, note = yu.effective_scheduled_time({"scheduled_time": past})
    assert when is None and "passée" in note


def test_a_future_date_is_kept_and_publish_now_wins():
    assert yu.effective_scheduled_time({"scheduled_time": FUTURE}) == (FUTURE, None)
    assert yu.effective_scheduled_time({"scheduled_time": FUTURE, "publish_now": True}) == (None, None)


def test_past_date_upload_goes_out_public(project, fake_youtube):
    project.add_channel("chanA")
    project.add_video("v1", video_path=project.add_video_file("v1.mp4"))
    project.write_schedule([schedule_entry("v1", when="2020-01-01T09:00:00+01:00")])

    result = yu.upload_channel_schedule("chanA")[0]

    assert result["success"] and "passée" in result["note"]
    assert fake_youtube.inserted[0]["status"]["privacyStatus"] == "public"
    assert db.get_video("v1")["status"] == "uploaded"


# ---- one source URL imported for several channels

def test_same_caption_videos_get_distinct_processed_files():
    """Regression: the processed file was named after the caption, so one URL
    imported for 3 channels wrote ONE shared file (each processing overwrote
    the previous one, and the first upload deleted it for the others)."""
    from video_processor import processed_output_paths
    a = processed_output_paths("Same caption", "specific", output_name="chanA_1")
    b = processed_output_paths("Same caption", "specific", output_name="chanB_1")
    assert a[0] != b[0] and a[1] != b[1]
    assert a[0].endswith("chanA_1.mp4") and b[0].endswith("chanB_1.mp4")


def test_batch_processing_names_the_file_after_the_video(project, monkeypatch):
    import video_processor
    from batch_processor import BatchProcessor
    seen = {}
    monkeypatch.setattr(video_processor, "process_video_with_background_options",
                        lambda *a, output_name=None, **k: seen.setdefault("name", output_name) and None)
    BatchProcessor("config.yaml").process_tiktok_video("x.mp4", "t", "none", output_name="vid_42")
    assert seen["name"] == "vid_42"


def test_reprocess_sends_a_video_back_to_cadrage_keeping_its_ai_data(client, project):
    from pathlib import Path
    Path("temp/v1").mkdir(parents=True)
    Path("temp/v1/src.mp4").write_bytes(b"x")
    project.add_video("v1", raw_video_path="temp/v1/src.mp4", video_path="processed_videos/gone.mp4",
                      ai_data={"optimized_title": "reviewed"})
    project.add_video("v2", raw_video_path="temp/none.mp4", video_path="processed_videos/gone2.mp4")

    assert client.post("/api/videos/v1/reprocess").status_code == 200
    v1 = db.get_video("v1")
    assert v1["status"] == "selected" and v1["reprocess_keep_ai"] and v1["ai_data"]["optimized_title"] == "reviewed"
    assert client.post("/api/videos/v2/reprocess").status_code == 400  # source gone too
