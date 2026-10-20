"""Montage effects: the time map (ramp, freeze, slow-down) shared by the
picture, the arrows and the crash sound; the AI's choice kept within limits."""

import pytest

from adaptation import effects as E, render


def clip(start=0.0, end=6.0, impact=3.0, **kw):
    return {"src": "x.mp4", "start": start, "end": end, "impact": impact, "w": 1920, "h": 1080, **kw}


def seg(ws=1.0, dur=4.0, fx=None):
    return {"ws": ws, "dur": dur, "out": 10.0, "fx": fx}


def test_a_ramp_plays_the_strong_moment_at_half_speed_and_keeps_the_segment_length():
    c, s = clip(), seg(fx={"ralenti": True})
    pcs = E.pieces(c, s)
    assert [(p["kind"], p["speed"]) for p in pcs] == [("play", 1.0), ("play", 0.5), ("play", 1.0)]
    assert pcs[1]["a"] == pytest.approx(3.0 - E.PRE) and pcs[1]["len"] == pytest.approx(E.SLOW_SRC * 2)
    assert sum(p["len"] for p in pcs) == pytest.approx(4.0)
    assert E.out_at(pcs, 3.0) == pytest.approx(2.0 - E.PRE + E.PRE * 2)      # the moment arrives later on screen
    for o in (0.3, 1.9, 3.5):                                                 # the two maps agree
        assert E.out_at(pcs, E.src_at(pcs, o)) == pytest.approx(o, abs=1e-6)


def test_a_freeze_holds_the_strong_moment_and_shows_less_of_the_clip():
    pcs = E.pieces(clip(), seg(fx={"arret": True}))
    assert [p["kind"] for p in pcs] == ["play", "hold", "play"]
    assert pcs[1]["t"] == 3.0 and pcs[1]["len"] == E.FREEZE and E.hold_at(pcs) == (2.0, E.FREEZE)
    assert pcs[2]["b"] == pytest.approx(1.0 + 4.0 - E.FREEZE)
    assert E.src_at(pcs, 2.5) == 3.0


def test_a_clip_too_short_for_its_sentence_is_slowed_down_not_frozen():
    c, s = clip(start=1.0, end=3.0), seg(ws=1.0, dur=3.0)
    fx = E.fit(c, s, None)
    assert fx["vitesse"] == pytest.approx(2.0 / 3.0, abs=1e-3)
    pcs = E.pieces(c, {**s, "fx": fx})
    assert len(pcs) == 1 and pcs[0]["speed"] < 1 and pcs[0]["len"] == pytest.approx(3.0, abs=0.01)
    very = E.fit(clip(start=1.0, end=1.8), {**s, "dur": 4.0}, None)
    assert very["vitesse"] == E.MIN_SPEED                                     # never slower than half speed…
    pcs = E.pieces(clip(start=1.0, end=1.8), {**s, "dur": 4.0, "fx": very})
    assert pcs[-1]["kind"] == "hold" and pcs[-1]["pad"]                        # …the rest is the last picture
    assert E.hold_at(pcs) is None                                             # not a freeze the AI chose


def test_the_ai_choice_is_cleaned_and_capped():
    assert E.clean({"ralenti": 1, "zoom": "null"}) == {"ralenti": True, "zoom": None, "arret": False, "transition": False}
    assert E.clean({"zoom": "  les   pieds "})["zoom"] == "les pieds" and E.clean({}) is None and E.clean("x") is None
    many = [{"ralenti": True, "transition": True, "arret": True}] * 5
    out = E.cap(many)
    assert sum(bool(e and e["ralenti"]) for e in out) == E.MAX["ralenti"]
    assert sum(bool(e and e["arret"]) for e in out) == 1
    assert not out[0]["transition"] and sum(bool(e and e["transition"]) for e in out) == E.MAX["transition"]


def test_a_zoom_goes_toward_its_target_within_what_the_resolution_bears():
    z = E.zoom_of(clip(), [700, 400, 800, 500])
    assert (z["cx"], z["cy"]) == (0.45, 0.75) and 1.12 <= z["z"] <= E.ZOOM
    small = E.zoom_of({**clip(), "w": 640, "h": 360}, [700, 400, 800, 500])  # a small source: barely zoomed
    assert small["z"] < z["z"] and E.zoom_of(clip(), None) is None


def test_the_timeline_and_the_filters_follow_the_effects():
    clips = {"A": clip(), "B": clip(end=4.0, impact=2.0, w=1080, h=1080)}
    passages = [{"clip": "A", "start": 0.0, "end": 3.5}, {"clip": "B", "start": 3.7, "end": 7.0}]
    plain, _ = render.build_timeline(passages, clips)
    fx = [{"ralenti": True, "zoom": {"cx": 0.4, "cy": 0.8, "z": 1.3}}, {"arret": True, "transition": True}]
    segs, total = render.build_timeline(passages, clips, fx)
    assert total == pytest.approx(_)
    assert segs[0]["impact_out"] > plain[0]["impact_out"]                      # the crash sound waits for the slowed moment
    final = " ; ".join(render.clip_chain(1, 0, clips["A"], segs[0]))
    assert "minterpolate" in final and "perspective" in final and "(0.5+-0.100*" in final   # toward x = 0.4
    quick = " ; ".join(render.clip_chain(1, 0, clips["A"], segs[0], preview=True))
    assert "minterpolate" not in quick                                        # the preview repeats frames: seconds
    frozen = " ; ".join(render.clip_chain(2, 1, clips["B"], segs[1]))
    assert "tpad=stop_mode=clone" in frozen and "concat=n=3" in frozen
