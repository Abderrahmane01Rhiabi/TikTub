"""Storage cleanup: only what no longer serves, never what's in use."""

import os
import time
from pathlib import Path

import db
import storage


def files_for(project, video_id, status, processed=True, **fields):
    folder = Path("temp") / video_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "src.mp4").write_bytes(b"x" * 1000)
    out = Path("processed_videos") / f"{video_id}.mp4"
    if processed:
        out.write_bytes(b"y" * 2000)
    project.add_video(video_id, status=status, raw_video_path=str(folder / "src.mp4"),
                      video_path=str(out) if processed else None, **fields)
    return folder, out


def make_old(path):
    old = time.time() - 3 * 24 * 3600
    os.utime(path, (old, old))


def test_scan_sorts_files_by_what_their_video_is_doing(project):
    files_for(project, "pub", "uploaded")
    files_for(project, "ready", "ready_for_upload")
    files_for(project, "rej", "rejected", processed=False)
    Path("temp/ghost").mkdir(parents=True)
    (Path("temp/ghost") / "a.mp4").write_bytes(b"z" * 500)

    t = storage.scan()["totals"]

    assert t["published"]["count"] == 2 and t["in_use"]["count"] == 2
    assert t["rejected"]["count"] == 1 and t["orphans"]["count"] == 1


def test_cleanup_never_touches_videos_in_use_nor_fresh_orphans(project):
    pub = files_for(project, "pub", "uploaded")
    ready = files_for(project, "ready", "ready_for_upload")
    failed = files_for(project, "fail", "processing_failed", processed=False)  # can still be retried
    rej = files_for(project, "rej", "rejected", processed=False)
    fresh = Path("processed_videos/rendering-now.mp4"); fresh.write_bytes(b"w")  # being written right now
    old = Path("temp/ghost"); old.mkdir(); make_old(old)

    result = storage.cleanup(include_rejected=False)

    assert not pub[0].exists() and not pub[1].exists() and not old.exists()
    assert ready[0].exists() and ready[1].exists() and failed[0].exists()
    assert fresh.exists()                      # an unreferenced file under 24 h old is kept
    assert rej[0].exists()                     # rejected only on explicit request
    assert result["freed_total"] == 3000 and db.get_video("rej")["status"] == "rejected"


def test_rejected_are_removed_only_on_request_and_leave_selection(project):
    rej = files_for(project, "rej", "rejected", processed=False)
    result = storage.cleanup(include_rejected=True)
    assert not rej[0].exists() and result["discarded"] == 1
    assert db.get_video("rej")["status"] == "discarded"   # can't be ticked again without its file


def test_automatic_cleanup_is_daily_and_never_removes_rejected(project):
    pub = files_for(project, "pub", "uploaded")
    rej = files_for(project, "rej", "rejected", processed=False)
    assert storage.cleanup_if_due() is not None
    assert not pub[0].exists() and rej[0].exists()
    assert storage.cleanup_if_due() is None    # already done today


def test_storage_endpoints(client, project):
    files_for(project, "pub", "uploaded")
    overview = client.get("/api/storage").json()
    assert "items" not in overview and overview["totals"]["published"]["size"] == 3000
    assert client.post("/api/storage/cleanup", json={}).json()["freed_total"] == 3000


def test_adaptation_projects_are_kept_while_running_and_freed_once_published(project):
    from adaptation import pipeline
    for pid, status, video_status in (("ad_run", "script_review", None), ("ad_done", "done", "uploaded")):
        folder = Path("temp/adaptations") / pid
        folder.mkdir(parents=True)
        (folder / "voice.mp3").write_bytes(b"v" * 100)
        targets = [{"channel": "chanA", "video_id": f"v_{pid}" if video_status else None}]
        db.save_adaptation({"project_id": pid, "status": status, "targets": targets})
        if video_status:
            project.add_video(f"v_{pid}", status=video_status)
    Path("temp/adaptations/ad_gone").mkdir()
    cats = {os.path.basename(i["path"]): i["category"] for i in storage.scan()["items"] if "adaptations" in i["path"]}
    assert cats == {"ad_run": "in_use", "ad_done": "published", "ad_gone": "orphans"}


def test_app_folders_in_temp_are_never_orphans(project):
    # temp/usage (Gemini cost log), temp/music_info (track cache), temp/style_previews (style images)
    # aren't video folders: old as they are, cleanup must leave them (AUDIT.md §8.3)
    Path("temp/usage").mkdir(parents=True)
    (Path("temp/usage") / "gemini.jsonl").write_text('{"model": "x"}\n')
    Path("temp/music_info").mkdir()
    (Path("temp/music_info") / "abc.json").write_text("{}")
    Path("temp/style_previews").mkdir()
    (Path("temp/style_previews") / "calme_fr.jpg").write_bytes(b"j")
    ghost = Path("temp/ghost"); ghost.mkdir(); (ghost / "a.mp4").write_bytes(b"z")
    for p in ("temp/usage", "temp/usage/gemini.jsonl", "temp/music_info", "temp/style_previews", ghost):
        make_old(p)

    assert {it["path"] for it in storage.scan()["items"] if it["category"] == "orphans"} == {os.path.join("temp", "ghost")}
    storage.cleanup()

    assert Path("temp/usage/gemini.jsonl").exists()
    assert Path("temp/music_info/abc.json").exists() and Path("temp/style_previews/calme_fr.jpg").exists()
    assert not ghost.exists()                  # a real orphan still goes


def test_thumbnail_of_a_video_not_yet_published_is_kept(project):
    # the Adaptation writes the cover next to the video, processed_videos/<id>.jpg (AUDIT.md §8.3)
    thumb = Path("processed_videos/chanA_ad1.jpg"); thumb.parent.mkdir(exist_ok=True); thumb.write_bytes(b"j" * 10)
    folder, out = files_for(project, "chanA_ad1", "ready_for_upload", thumbnail_path=str(thumb))
    make_old(thumb)

    storage.cleanup()

    assert thumb.exists() and out.exists()


def test_thumbnail_of_a_published_video_is_freed(project):
    thumb = Path("processed_videos/chanA_ad2.jpg"); thumb.parent.mkdir(exist_ok=True); thumb.write_bytes(b"j" * 10)
    files_for(project, "chanA_ad2", "uploaded", thumbnail_path=str(thumb))

    storage.cleanup()

    assert not thumb.exists()
