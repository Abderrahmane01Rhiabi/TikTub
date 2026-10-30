"""Montage Roblox, the video's stock (roblox/stock.py): one record per YouTube video in the database (kept for good,
light) and one shared folder of its heavy files (passages, voices apart, cleaned versions — kept 30 days after
their last use): a 2nd project on the same video does not download, separate, analyse or clean again."""

import os
import time

import db
from roblox import sources, stock


def test_one_key_per_youtube_video_whatever_the_link():
    for url in ("https://www.youtube.com/watch?v=G-tr41VgzB8", "https://youtu.be/G-tr41VgzB8?t=30",
                "https://www.youtube.com/watch?app=desktop&v=G-tr41VgzB8&t=2s", "https://youtube.com/shorts/G-tr41VgzB8"):
        assert stock.video_key(url) == "G-tr41VgzB8"
    other = stock.video_key("https://example.com/video.mp4")
    assert other == stock.video_key("https://example.com/video.mp4") and len(other) == 12


def test_the_record_is_kept_in_the_database(project):
    url = "https://www.youtube.com/watch?v=G-tr41VgzB8"
    rec = stock.load(url)
    assert rec["video_id"] == "G-tr41VgzB8" and rec["passages"] == {} and rec["publies"] == []
    rec["meta"] = {"titre": "WATER BARRY", "duree": 6078.0}
    stock.passage(rec, 0.0, 75.0).update(rang=1, fichier="x.mp4", moments=[{"debut": 1}])
    stock.save(rec)
    again = stock.load("https://youtu.be/G-tr41VgzB8")
    assert again["meta"]["titre"] == "WATER BARRY" and again["passages"]["0.0-75.0"]["moments"] == [{"debut": 1}]
    assert db.get_roblox_video("G-tr41VgzB8")["url"] == url


def test_more_passages_never_take_the_ones_already_used():
    heat = [{"start_time": k * 60.0, "end_time": (k + 1) * 60.0, "value": v} for k, v in enumerate([0.9, 0.1, 0.8, 0.2, 0.7, 0.3, 0.6, 0.05])]
    meta = {"duree": 900.0, "heatmap": heat}                                     # 8 min of graph, 15 min of video
    first = sources.windows(meta, n=2, size=75)
    more = sources.windows(meta, n=2, size=75, exclude=first)
    assert more and all(b1 <= a2 or a1 >= b2 for a1, b1 in first for a2, b2 in more)
    allw = first + more
    rest = sources.windows(meta, n=10, size=75, exclude=allw)
    assert rest and all(b1 <= a2 or a1 >= b2 for a1, b1 in allw for a2, b2 in rest)
    assert sources.windows({"duree": 3600.0}, n=3, size=75, exclude=[[0.0, 3600.0]]) == []      # nothing left


def test_old_files_are_removed_but_the_record_stays(project):
    rec = stock.load("https://www.youtube.com/watch?v=OLDVIDEO123")
    folder = stock.folder(rec)
    os.makedirs(os.path.join(folder, "src"), exist_ok=True)
    f = os.path.join(folder, "src", "w0.mp4")
    open(f, "w").write("x")
    stock.passage(rec, 0.0, 75.0).update(fichier=f, moments=[{"debut": 1}])
    rec["utilise_le"] = time.time() - 31 * 86400
    stock.save(rec)
    fresh = stock.load("https://www.youtube.com/watch?v=NEWVIDEO1234")
    os.makedirs(stock.folder(fresh), exist_ok=True)
    stock.save(fresh)
    assert stock.purge() == 1
    assert not os.path.exists(folder) and os.path.exists(stock.folder(fresh))
    kept = stock.load("https://www.youtube.com/watch?v=OLDVIDEO123")
    assert kept["passages"]["0.0-75.0"]["moments"] == [{"debut": 1}]                             # the analysis stays


def test_the_storage_screen_sees_the_stock_and_old_stock_goes(project):
    import storage
    rec = stock.load("https://www.youtube.com/watch?v=STOCKVIDEO1")
    os.makedirs(stock.folder(rec), exist_ok=True)
    open(os.path.join(stock.folder(rec), "a.mp4"), "w").write("x")
    stock.save(rec)
    cat = lambda: {os.path.normpath(i["path"]): i["category"] for i in storage.scan()["items"]}
    assert cat()[os.path.normpath(stock.folder(rec))] == "in_use"
    rec["utilise_le"] = time.time() - 31 * 86400
    stock.save(rec)
    assert cat()[os.path.normpath(stock.folder(rec))] == "orphans"
    assert os.path.normpath(os.path.join("temp", "roblox", "videos")) not in cat()            # never taken for a project
