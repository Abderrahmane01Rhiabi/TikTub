"""Arrows and circles on the action: where, when, how they are drawn."""

import os

import pytest
from PIL import Image

from adaptation import annotate as A
from adaptation import render as R


def clip(w=1080, h=1920, **k):
    return {"src": "s.mp4", "start": 0.0, "end": 10.0, "impact": 5.0, "w": w, "h": h, **k}


def test_points_land_where_clip_chain_puts_them():
    tall = clip(1020, 980)                                     # close to the box: cover
    x, y = A.to_box(tall, 0.5, 0.5)
    assert abs(x - R.BOX_W / 2) < 1 and abs(y - R.BOX_H / 2) < 1
    wide = clip(1920, 1080)                                    # 16:9 on its blurred copy, centered band
    _, top = A.to_box(wide, 0.5, 0.0)
    _, bottom = A.to_box(wide, 0.5, 1.0)
    band = R._even(R.BOX_W / (1920 / 1080))
    assert abs((bottom - top) - band * 1.04) < 3 and abs((top + bottom) / 2 - R.BOX_H / 2) < 2


def test_the_window_ends_on_the_strong_moment_or_sits_in_the_middle():
    seg = {"ws": 2.0, "dur": 5.0, "out": 10.0}
    assert A.window(seg, clip(impact=5.0)) == (5.0 - A.SHOW, 5.0)
    a, b = A.window(seg, clip(impact=9.5))                    # not on screen: a window in the shot
    assert 2.0 < a < b <= 7.0 and b - a == pytest.approx(1.2)


def test_track_fills_and_eases_between_samples():
    c = clip(1020, 980)
    path = A.track(c, [[400, 400, 600, 600], None, [400, 500, 600, 700], None], [0.0, 0.3, 0.6, 0.9])
    assert [p["t"] for p in path] == [0.0, 0.6]
    mid = A.at(path, 0.3)
    assert path[0]["cx"] < mid["cx"] < path[1]["cx"]
    assert A.at(path, 5)["cx"] == path[1]["cx"] and A.track(c, [None, None], [0, 1]) == []


def test_pop_overshoots_then_fades():
    assert A._pop(0.0, 1.0)[0] < 0.2
    assert max(A._pop(t / 100, 1.0)[0] for t in range(0, 22)) > 1.02
    assert A._pop(0.5, 1.0) == (1.0, 1.0) and A._pop(0.99, 1.0)[1] < 0.2


def test_frames_are_drawn_on_the_box_and_transparent_elsewhere(tmp_path):
    path = [{"t": 0.0, "cx": 500, "cy": 500, "rx": 80, "ry": 60}, {"t": 1.0, "cx": 560, "cy": 520, "rx": 80, "ry": 60}]
    n = A.frames(path, "cercle", 0.0, 1.0, str(tmp_path / "c"))
    assert n == R.FPS and len(os.listdir(tmp_path / "c")) == n
    im = Image.open(tmp_path / "c" / "f_015.png")
    assert im.size == (R.BOX_W, R.BOX_H) and im.getpixel((5, 5))[3] == 0
    p = A.at(path, 0.5)                                        # half way: the ring has moved with its target
    left = int(p["cx"] - p["rx"] * 1.25)
    assert any(im.getpixel((x, int(p["cy"])))[0] > 200 and im.getpixel((x, int(p["cy"])))[3] > 200
               for x in range(left - 15, left + 15))           # the red ring
    A.frames(path, "fleche", 0.0, 0.5, str(tmp_path / "f"))
    im = Image.open(tmp_path / "f" / "f_010.png")
    yellow = sum(1 for x in range(0, R.BOX_W, 4) for y in range(0, R.BOX_H, 4)
                 if im.getpixel((x, y))[:3] == A.YELLOW[:3])
    assert yellow > 50


def test_prepare_locates_once_and_reuses_the_track(tmp_path, monkeypatch):
    from adaptation import sources
    calls = []
    monkeypatch.setattr(sources, "still", lambda src, t, crop, out, *a, **k: out)
    monkeypatch.setattr(A, "after_last_cut", lambda c, a, b: a)
    monkeypatch.setattr(A, "locate", lambda stills, cible, gemini=None: calls.append(cible) or [[400, 400, 600, 600]] * 4)
    seg = {"ws": 2.0, "dur": 5.0, "out": 10.0}
    r = A.prepare(seg, clip(1020, 980), {"type": "cercle", "cible": "la voiture"}, str(tmp_path), 0)
    assert r["start"] == pytest.approx(10.0 + (5.0 - A.SHOW - 2.0)) and r["frames"] == round(A.SHOW * R.FPS)
    again = A.prepare(seg, clip(1020, 980), {"type": "cercle", "cible": "la voiture"}, str(tmp_path), 0, cached=r["cache"])
    assert calls == ["la voiture"] and again["frames"] == r["frames"]               # no second Gemini call
    A.prepare(seg, clip(1020, 980), {"type": "cercle", "cible": "le camion"}, str(tmp_path), 0, cached=r["cache"])
    assert calls == ["la voiture", "le camion"]                                       # another target: located again
    monkeypatch.setattr(A, "locate", lambda stills, cible, gemini=None: [None] * 4)
    assert A.prepare(seg, clip(1020, 980), {"type": "fleche", "cible": "un fantôme"}, str(tmp_path), 1) is None


def test_locate_reads_boxes_and_ignores_bad_ones(tmp_path):
    p = tmp_path / "s.jpg"
    Image.new("RGB", (16, 16)).save(p)

    class G:
        def _generate_content(self, parts, **kw):
            assert "la voiture noire" in parts[-1]["text"]
            return {"images": [{"box_2d": [1, 2, 300, 400]}, {"box_2d": None}, {"box_2d": [5, 5, 1, 1]}]}
    assert A.locate([str(p)] * 3, "la voiture noire", gemini=G()) == [[1, 2, 300, 400], None, None]


def test_render_lays_the_annotations_on_the_picture_box(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(R, "_run", lambda cmd, total, cb: seen.setdefault("cmd", cmd))
    monkeypatch.setattr(R, "_picture_box", lambda segs, clips, work, preview, progress=None, notes=None: "box.mp4")
    monkeypatch.setattr(os, "replace", lambda a, b: None)
    passages = [{"clip": "A", "bandeau": "X : Y", "texte": "Bonjour.", "mots_cles": [], "start": 0.0, "end": 1.0, "words": []}]
    clips = {"A": clip(1080, 1920, impact=1.0)}
    R.render(passages, [], clips, "v.mp3", "fr", str(tmp_path / "o.mp4"), str(tmp_path),
             annotations=[{"k": 0, "dir": str(tmp_path / "ann0"), "frames": 10, "start": 0.4}])
    graph = seen["cmd"][seen["cmd"].index("-filter_complex") + 1]
    assert "setpts=PTS-STARTPTS+0.400/TB[an0]" in graph and "[box][an0]overlay=0:0:eof_action=pass[bx0]" in graph
    assert "[bgc][bx0]overlay" in graph


def test_review_decides_the_arrows_again_on_the_real_clips(tmp_path, monkeypatch):
    from adaptation import sources
    monkeypatch.setattr(sources, "clip_still", lambda c, out: Image.new("RGB", (8, 8)).save(out) or out)
    passages = [{"clip": "P1", "texte": "Pourquoi ?", "annotation": {"type": "fleche", "cible": "la voiture"}},
                {"clip": "P2", "texte": "Le pneu se plisse.", "annotation": None},
                {"clip": "PX", "texte": "Sans clip.", "annotation": {"type": "cercle", "cible": "x"}},
                {"clip": "P3", "texte": "Fin.", "annotation": None}, {"clip": "P4", "texte": "Bonus.", "annotation": None}]
    clips = {k: clip() for k in ("P1", "P2", "P3", "P4")}
    seen = {}

    class G:
        def _generate_content(self, parts, **kw):
            seen["n"], seen["text"] = len(parts) - 1, parts[-1]["text"]
            return {"plans": [{"plan": 1, "annotation": None},
                              {"plan": 2, "annotation": {"type": "Cercle", "cible": "le pneu arrière gauche"}},
                              {"plan": 3, "annotation": {"type": "fleche", "cible": "a"}},
                              {"plan": 4, "annotation": {"type": "fleche", "cible": "b"}}]}
    out = A.review(passages, clips, str(tmp_path), gemini=G())
    assert seen["n"] == 4 and "fleche sur « la voiture »" in seen["text"]          # a passage without clip is skipped
    assert out[0] is None and out[1] == {"type": "cercle", "cible": "le pneu arrière gauche"}
    assert out[2] is None and out[3]["cible"] == "a" and out[4]["cible"] == "b"
    assert A.review(passages, clips, str(tmp_path), gemini=type("B", (), {"_generate_content": lambda s, *a, **k: "cut"})()) is None
