"""Data that must survive two threads and a restart (AUDIT.md §8.3-5):
video rows updated at the same time, token.json and the schedule file."""

import threading
import time

import db
from url_manager import URLManager


def test_two_updates_at_once_never_erase_each_other(project, monkeypatch):
    project.add_video("v1")
    real_get = db.get_video

    def slow_get(video_id, db_path=db.DB_PATH):        # both threads read before either writes
        video = real_get(video_id, db_path)
        time.sleep(0.2)
        return video
    monkeypatch.setattr(db, "get_video", slow_get)

    manager = URLManager()
    threads = [threading.Thread(target=manager.update_video_status, args=("v1", "ready_for_upload"), kwargs=kw)
               for kw in ({"tracker_field": 1}, {"ui_field": 2})]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    video = real_get("v1")
    assert video["tracker_field"] == 1 and video["ui_field"] == 2


class ServerKilled(BaseException):
    """A restart in the middle of writing a file."""


def test_a_crash_while_saving_a_token_leaves_the_old_one_intact(project):
    import youtube_uploader as yu
    folder = project.add_channel("chanA")
    (folder / "token.json").write_text('{"refresh_token": "OLD"}')

    class Flow:
        def fetch_token(self, authorization_response):
            pass

        class credentials:
            @staticmethod
            def to_json():
                raise ServerKilled()                 # dies while the new token is being written
    yu._pending_oauth_flows["s1"] = (Flow(), "chanA")

    try:
        yu.complete_oauth_flow("s1", "http://localhost/api/oauth/callback?state=s1&code=x")
    except ServerKilled:
        pass

    assert (folder / "token.json").read_text() == '{"refresh_token": "OLD"}'     # still connected
    assert [p.name for p in folder.iterdir() if p.name.endswith(".part")] == []


def test_a_crash_while_saving_the_schedule_leaves_the_old_one_intact(project, monkeypatch):
    import json
    from youtube_scheduler import YouTubeScheduler
    project.write_schedule([{"video_id": "v1", "channel": "chanA", "scheduled_time": "2030-01-07 18:00:00"}])
    before = open("upload_schedule.json", encoding="utf-8").read()

    def killed(*a, **k):
        raise ServerKilled()
    monkeypatch.setattr(json, "dump", killed)
    monkeypatch.setattr(json, "dumps", killed)

    try:
        YouTubeScheduler("config.yaml").save_schedule([{"video_id": "v2", "channel": "chanA", "scheduled_time": None}])
    except ServerKilled:
        pass

    assert open("upload_schedule.json", encoding="utf-8").read() == before


def test_a_date_moved_while_a_screen_completes_the_schedule_is_kept(client, project, monkeypatch):
    """A GET (Planning, Publier) adds missing videos and rewrites the file; a
    date moved by hand at the same moment used to be overwritten."""
    import webapp.main as m
    project.declare_channel("chanA")
    project.add_video("p1")
    project.write_schedule([{"video_id": "p1", "channel": "chanA", "title": "p1",
                             "scheduled_time": "2030-01-07 18:00:00", "video_data": {}}], method="static")
    project.add_video("late")                                    # missing: the next GET adds it
    bp = m.get_batch_processor()
    reading, finish = threading.Event(), threading.Event()
    real = bp.scheduler.create_upload_schedule

    def slow_method(videos, **kw):                               # the GET has read the file and is computing
        reading.set()
        finish.wait(5)
        return real(videos, **kw)
    monkeypatch.setattr(bp.scheduler, "create_upload_schedule", slow_method)

    screen = threading.Thread(target=lambda: client.get("/api/schedule"))
    screen.start()
    assert reading.wait(5)
    move = threading.Thread(target=lambda: client.patch("/api/schedule/p1", json={"scheduled_time": "2030-01-09 18:00:00"}))
    move.start()
    time.sleep(0.3)
    finish.set()
    screen.join(10)
    move.join(10)

    import json
    saved = {e["video_id"]: e for e in json.load(open("upload_schedule.json"))["schedule"]}
    assert saved["p1"]["scheduled_time"] == "2030-01-09 18:00:00" and "late" in saved
