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
