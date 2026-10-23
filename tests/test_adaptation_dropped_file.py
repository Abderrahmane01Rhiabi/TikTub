"""« Déposer un fichier » : a video saved by hand (Douyin's app, a private
post…) stands where a link would, on a plan or as a source."""

import json
import os
import subprocess

import pytest

from adaptation import finder, sources
from adaptation import pipeline as ap
from tests.test_adaptation_storyboard import _approved_project, _images_project, fakes  # noqa: F401


def phone_video(path, seconds=6, audio=True):
    """A small video, HEVC like a phone's when the encoder exists, else H.264."""
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size=320x568:rate=30:duration={seconds}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=500:duration={seconds}"]
    subprocess.run(cmd + ["-pix_fmt", "yuv420p", str(path)], check=True)
    return str(path)


def test_a_dropped_file_is_kept_cut_and_credited(tmp_path):
    url = sources.save_local(phone_video(tmp_path / "Mon Douyin!.mov"), str(tmp_path / "fichiers"), "Mon Douyin!.mov",
                             "微蓝 (Douyin 69627156)")
    assert url.startswith("fichier:") and url.endswith("Mon_Douyin.mp4")
    assert sources.local_info(url) == {"title": "Mon Douyin!.mov", "credit": "微蓝 (Douyin 69627156)"}
    assert sources.reachable(url) is True
    path = sources.download(url, str(tmp_path / "src"), "src0", [[1.0, 2.5], [4.0, 5.0]])
    assert abs(sources.probe(path)["duration"] - 2.5) < 0.2                  # the two spans, joined
    meta = json.load(open(path + ".meta.json", encoding="utf-8"))
    assert meta["url"] == url and meta["handle"] == "微蓝 (Douyin 69627156)"   # the credit of its clips
    whole = sources.download(url, str(tmp_path / "src"), "src1")
    assert abs(sources.probe(whole)["duration"] - 6) < 0.2


def test_a_file_without_sound_and_a_broken_one(tmp_path):
    url = sources.save_local(phone_video(tmp_path / "muet.mp4", audio=False), str(tmp_path / "f"), "muet.mp4")
    assert sources.has_picture(sources.download(url, str(tmp_path / "s"), "x", [[0.5, 2.0]]))
    (tmp_path / "abime.mp4").write_bytes(b"not a video")
    with pytest.raises(sources.SourceError):
        sources.save_local(str(tmp_path / "abime.mp4"), str(tmp_path / "f"), "abime.mp4")


def test_gemini_is_sent_the_file_itself(tmp_path):
    url = sources.save_local(phone_video(tmp_path / "v.mp4"), str(tmp_path / "f"), "v.mp4")
    sent = []

    class G:
        def _upload_video_file(self, path):
            sent.append(path)
            return {"name": "n", "mime_type": "video/mp4", "uri": "u"}
        _wait_for_file_active = lambda self, name, timeout: True
        _delete_file = lambda self, name: None
        _generate_content = lambda self, parts, **kw: {"plans": []}
    seen = finder._watch(url, G(), "?")
    assert sent == [sources.local_path(url)] and seen["title"] == "v.mp4" and abs(seen["duration"] - 6) < 0.2


def test_a_file_dropped_on_a_plan_becomes_its_pick_with_its_credit(project, fakes, monkeypatch, tmp_path):
    pid = _images_project(project, fakes, monkeypatch)
    checker = lambda u, sc, pl: {"verdict": "oui", "title": "v", "par_scene": {
        "5": {"niveau": "exacte", "moments": [{"debut": 1, "fin": 4}], "raison": "le même"}}}
    p = ap.file_for_plan(pid, 5, phone_video(tmp_path / "in.mp4"), "douyin_cactus.mp4", "微蓝 (Douyin 69627156)", checker)
    pick = p["picks"][5]
    assert pick["url"].startswith("fichier:") and pick["titre"] == "📁 douyin_cactus.mp4"
    assert pick["credit"] == "微蓝 (Douyin 69627156)" and pick["moment"] == {"debut": 1.0, "fin": 4.0}
    assert os.path.exists(sources.local_path(pick["url"]))
    nothing = lambda u, sc, pl: {"verdict": "non", "title": "v", "par_scene": {"4": {"niveau": "rien", "moments": []}}}
    p = ap.file_for_plan(pid, 4, phone_video(tmp_path / "in2.mp4"), "autre.mp4", "x", nothing)
    assert not (p["picks"][4] or {}).get("url", "").startswith("fichier:")   # not what this plan shows: not taken
    assert p["fetch_note"] == "Ta vidéo ne montre pas le plan 5, ni aucun autre plan."
    elsewhere = lambda u, sc, pl: {"verdict": "oui", "title": "v", "par_scene": {"1": {"niveau": "exacte", "moments": [{"debut": 0, "fin": 2}]}}}
    p = ap.file_for_plan(pid, 4, phone_video(tmp_path / "in3.mp4"), "ailleurs.mp4", "", elsewhere)
    assert "plan(s) 2" in p["fetch_note"] and p["suggestions"]["scenes"][1]["candidats"][0]["url"].startswith("fichier:")


def test_the_api_takes_a_file_for_a_plan(client, project, fakes, monkeypatch, tmp_path):
    pid = _images_project(project, fakes, monkeypatch)
    monkeypatch.setattr(finder, "check", lambda u, sc, pl=None, **kw: {"verdict": "oui", "title": "v", "par_scene": {
        "5": {"niveau": "equivalente", "moments": [{"debut": 0, "fin": 3}]}}})
    with open(phone_video(tmp_path / "x.mp4"), "rb") as f:
        r = client.post(f"/api/adaptations/{pid}/plans/5/file", files={"file": ("x.mp4", f, "video/mp4")},
                        data={"credit": "@quelquun (Xiaohongshu)"})
    assert r.status_code == 200, r.text
    pick = r.json()["picks"][5]
    assert pick["credit"] == "@quelquun (Xiaohongshu)"
    name = pick["url"].split("/")[-1]
    assert client.get(f"/api/adaptations/{pid}/fichiers/{name}").status_code == 200
    assert client.get(f"/api/adaptations/{pid}/fichiers/..%2F..%2F.env").status_code == 404
    with open(tmp_path / "x.mp4", "rb") as f:
        assert client.post(f"/api/adaptations/{pid}/plans/5/file", files={"file": ("x.txt", f)}).status_code == 400


def test_a_file_as_a_source(project, fakes, tmp_path):
    from tests.test_adaptation_flow import channel
    p = ap.create("https://youtube.com/shorts/x", [], [channel(project)])
    p.update(status="sources_search")
    ap.save(p)
    p = ap.file_as_source(p["project_id"], phone_video(tmp_path / "s.mp4"), "s.mp4", "米合勒 (Douyin Maicy161105)")
    assert p["status"] == "analysing" and p["source_urls"][-1].startswith("fichier:")


def test_chinese_searches_open_douyin_too():
    assert [l["label"] for l in finder.search_links("仙人掌 烧毛")][-3:] == ["Douyin", "Xiaohongshu", "Bilibili"]
    assert "Douyin" not in [l["label"] for l in finder.search_links("cactus fire")]
