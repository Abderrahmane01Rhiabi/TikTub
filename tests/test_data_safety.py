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
