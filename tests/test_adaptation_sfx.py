"""Sound effects that follow the picture: rules, no AI."""

from adaptation import sfx


def seg(k, out, dur=4.0, impact=None, **fx):
    return {"k": k, "out": out, "dur": dur, "impact_out": out + 1.0 if impact is None else impact, "fx": fx}


def test_each_effect_on_screen_has_its_sound_and_one_transition_only():
    segs = [seg(0, 0.0), seg(1, 4.0, transition=True), seg(2, 8.0, arret=True), seg(3, 12.0, transition=True),
            seg(4, 16.0, ralenti=True), seg(5, 20.0, transition=True)]
    moments = sfx.plan(segs, [{"start": 0.4}], [], 24.0)
    assert [m["pourquoi"] for m in moments] == ["flèche / cercle", "arrêt sur image", "transition principale",
                                                "ralenti sur le moment fort"]
    assert moments[2]["t"] == 12.0                        # the transition nearest 40 % of the video, alone
    assert moments[3]["sons"] == ["riser", "impact"]


def test_at_most_four_moments_three_seconds_apart():
    segs = [seg(k, 4.0 * k, arret=True) for k in range(8)]
    moments = sfx.plan(segs, [{"start": 1.2}], [], 32.0)
    assert len(moments) == sfx.MAX
    assert all(b["t"] - a["t"] >= sfx.GAP for a, b in zip(moments, moments[1:]))
    assert sfx.plan([seg(0, 0.0, ralenti=True)], [], [], 6.0, own_crash={0})[0]["sons"] == ["riser"]   # its own crash


def test_variants_in_turn_and_the_loudest_instant_on_the_event(monkeypatch):
    monkeypatch.setattr(sfx, "peak_of", lambda f: 0.5 if "riser" in f else 0.05)
    lib = {"whoosh": ["w1.mp3", "w2.mp3"], "riser": ["riser.mp3"]}
    out = sfx.sounds([{"t": 1.0, "sons": ["whoosh"], "pourquoi": "a"}, {"t": 5.0, "sons": ["whoosh"], "pourquoi": "b"},
                      {"t": 9.0, "sons": ["riser", "impact"], "pourquoi": "c"}], lib)
    assert [o["file"] for o in out] == ["w1.mp3", "w2.mp3", "riser.mp3"]   # no impact file: left out
    assert out[0]["start"] == 0.95 and out[2]["start"] == 8.5


def test_the_library_is_the_folder_of_the_app():
    lib = sfx.library()
    assert {"whoosh", "pop", "shutter", "riser", "impact", "ding"} <= set(lib)
    assert len(lib["whoosh"]) >= 3
    assert 1.5 < sfx.peak_of(lib["riser"][0]) < 2.0       # a riser is loudest at its end
