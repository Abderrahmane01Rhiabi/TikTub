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
    short = clip(start=1.0, end=1.8, impact=1.4)
    very = E.fit(short, {**s, "dur": 4.0}, None)
    assert very["vitesse"] == E.MIN_SPEED and very["arret"]                   # half speed at most, then a freeze…
    pcs = E.pieces(short, {**s, "dur": 4.0, "fx": very})
    assert E.hold_at(pcs)[1] == E.FREEZE and pcs[1] == {**pcs[1], "kind": "hold", "t": 1.4}   # …on the strong moment


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
    assert "minterpolate" in final and "perspective" in final and "(0.500+-0.100*" in final   # toward x = 0.4
    quick = " ; ".join(render.clip_chain(1, 0, clips["A"], segs[0], preview=True))
    assert "minterpolate" not in quick                                        # the preview repeats frames: seconds
    frozen = " ; ".join(render.clip_chain(2, 1, clips["B"], segs[1]))
    assert "tpad=stop_mode=clone" in frozen and "concat=n=3" in frozen


def test_a_small_subject_gets_a_zoom_measured_not_guessed(tmp_path, monkeypatch):
    from PIL import Image
    from adaptation import sources
    monkeypatch.setattr(sources, "clip_still", lambda c, out: Image.new("RGB", (8, 8)).save(out) or out)
    clips = {f"P{k}": clip() for k in range(1, 6)}
    passages = [{"clip": f"P{k}", "texte": f"Phrase {k}."} for k in range(1, 6)]
    passages[3]["annotation"] = {"type": "cercle", "cible": "x"}             # an arrow: never zoomed under it
    fx = [None, {"ralenti": True, "zoom": None, "arret": False, "transition": False}, None, None,
          {"ralenti": False, "zoom": "deja", "arret": False, "transition": False}]

    class G:
        def _generate_content(self, parts, **kw):
            G.n = sum("inline_data" in x for x in parts)
            return {"plans": [{"plan": 1, "sujet": "l'homme au loin", "box_2d": [600, 500, 700, 540]},     # small
                              {"plan": 2, "sujet": "les jambes", "box_2d": [200, 450, 900, 520]},          # big on screen
                              {"plan": 3, "sujet": "rien", "box_2d": None}]}
    out = E.auto_zoom(passages, clips, fx, str(tmp_path), gemini=G())
    assert G.n == 3                                                            # plans 1, 2, 3 looked at
    assert out[0]["zoom"] == "l'homme au loin" and out[1] == fx[1] and out[2] is None
    assert out[3] is None and out[4]["zoom"] == "deja"
    assert E.on_screen(clip(), [600, 500, 700, 540]) < E.SMALL < E.on_screen(clip(), [200, 450, 900, 520])
    assert E.on_screen(clip(), [500, 450, 900, 520]) < E.SMALL                  # 40 % of a wide clip: small once shown


def test_a_cropped_picture_follows_its_subject_and_the_arrow_follows_too():
    from adaptation import annotate
    square = {**clip(w=1080, h=1080), "centre": [0.9, 0.5]}
    assert render.framing(square) == (0.9, 0.5) and render.framing(clip()) == (0.5, 0.5)
    seg = {"ws": 1.0, "dur": 3.0, "out": 0.0, "impact_out": 1.0, "fx": None}
    chain = " ; ".join(render.clip_chain(1, 0, square, seg))
    assert "clip(0.900*W" in chain                                          # the crop is centred on the subject
    mid, right = annotate.to_box(clip(w=1080, h=1080), 0.9, 0.5), annotate.to_box(square, 0.9, 0.5)
    assert right[0] < mid[0]                                                # the arrow moves with the picture


def test_a_dark_clip_is_lit_up_and_a_bright_one_left_alone(tmp_path):
    import subprocess
    dark, bright = str(tmp_path / "d.mp4"), str(tmp_path / "b.mp4")
    for f, col in ((dark, "0x101010"), (bright, "0xb0b0b0")):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={col}:s=320x240:d=2", "-c:v", "libx264",
                        f], check=True)
    assert render.light({"src": dark, "start": 0, "end": 2}).startswith("eq=gamma=")
    assert render.light({"src": bright, "start": 0, "end": 2}) is None


def _ff(*args):
    import subprocess
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def test_the_beat_of_a_click_track_is_found_and_cuts_land_on_it(tmp_path):
    clicks = str(tmp_path / "clicks.wav")                  # 120 BPM: a short click every 0.5 s
    _ff("-f", "lavfi", "-i", "sine=f=1000:d=0.03,apad=whole_dur=0.5", "-af", "aloop=loop=-1:size=22050",
        "-t", "20", "-ar", "44100", clicks)
    beats = render.beats_of(clicks, 0, 15)
    gaps = [b - a for a, b in zip(beats, beats[1:])]
    assert len(beats) > 20 and abs(sum(gaps) / len(gaps) - 0.5) < 0.03
    clips = {"A": clip(end=9.0, impact=3.0), "B": clip(end=9.0, impact=3.0)}
    passages = [{"clip": "A", "start": 0.0, "end": 2.13}, {"clip": "B", "start": 2.5, "end": 4.0}]
    segs, _ = render.build_timeline(passages, clips, None, beats)
    cut = segs[1]["out"]
    assert min(abs(cut - b) for b in beats) < 0.01 and render.GAP_MIN <= cut - 2.23 <= render.GAP_MAX
    assert render.beats_of(str(tmp_path / "missing.wav"), 0, 10) == []


def test_a_strong_figure_is_drawn_popping_in(tmp_path):
    from PIL import Image
    from adaptation import langs
    n = render.number_frames("1481 N", str(tmp_path / "n"), langs.lang("fr"), render.style_of("neon"), 1.0)
    assert n == 30
    first, mid = (Image.open(tmp_path / "n" / f"f_{i:03d}.png") for i in (0, 15))
    assert mid.size == (render.BOX_W, render.BOX_H) and mid.getbbox()[1] > render.BOX_H * 0.5   # low in the box
    assert (first.getbbox() or (0, 0, 0, 0))[2] - (first.getbbox() or (0, 0, 0, 0))[0] < mid.getbbox()[2] - mid.getbbox()[0]


def test_a_colour_cast_is_pulled_back_and_a_neutral_clip_left_alone(tmp_path):
    sepia, grey = str(tmp_path / "s.mp4"), str(tmp_path / "g.mp4")
    _ff("-f", "lavfi", "-i", "color=c=0xb08850:s=320x240:d=2", "-c:v", "libx264", sepia)
    _ff("-f", "lavfi", "-i", "color=c=0x909090:s=320x240:d=2", "-c:v", "libx264", grey)
    assert "lutyuv" in render.look({"src": sepia, "start": 0, "end": 2})
    assert render.look({"src": grey, "start": 0, "end": 2}) is None


def test_a_shaky_clip_is_told_from_a_steady_one(tmp_path):
    shaky, steady, scene = str(tmp_path / "shaky.mp4"), str(tmp_path / "steady.mp4"), str(tmp_path / "scene.png")
    _ff("-f", "lavfi", "-i", "testsrc2=s=640x360", "-frames:v", "1", scene)      # a still scene, a shaking camera
    _ff("-loop", "1", "-i", scene, "-t", "4", "-r", "30", "-vf", "crop=560:300:40+14*sin(n*0.9)+6*sin(n*2.3):30+10*cos(n*1.1)+5*sin(n*2.9)",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", shaky)
    _ff("-loop", "1", "-i", scene, "-t", "4", "-r", "30", "-vf", "crop=560:300:40:30", "-c:v", "libx264",
        "-pix_fmt", "yuv420p", steady)
    assert render.shakiness(shaky, 0, 4) > render.SHAKY > render.shakiness(steady, 0, 4)
    out = render.stabilised(shaky, 0, 4, str(tmp_path / "stab.mp4"))
    assert render.shakiness(out, 0, 4) < 0.5 * render.shakiness(shaky, 0, 4)       # a hand-held wobble: much steadier


def test_text_left_after_the_cleaning_is_painted_over(tmp_path, monkeypatch):
    from adaptation import sources
    monkeypatch.setattr(sources, "still", lambda src, t, crop, out, *a, **k: open(out, "wb").close() or out)
    clips = {"P1": {**clip(w=1000, h=500), "delogo": [(1, 1, 10, 10)]}, "P2": clip(w=1000, h=500)}
    seen = sources.leftover_text(clips, str(tmp_path), finder=lambda shots: [
        (None, [[100, 200, 200, 600]], ["If you drive over it too fast"]), (None, [], []),
        (None, [[0, 0, 900, 900]], ["huge"]), (None, [], [])])
    assert seen == {"P1": ["If you drive over it too fast"]} and clips["P1"]["texte_efface"]
    assert clips["P1"]["delogo"][-1] == (194, 44, 412, 62) and "texte_efface" not in clips["P2"]   # too big: left


def test_a_latin_figure_stays_left_to_right_in_an_arabic_video(tmp_path, monkeypatch):
    from PIL import ImageDraw
    from adaptation import langs
    seen = []
    real = ImageDraw.ImageDraw.text
    monkeypatch.setattr(ImageDraw.ImageDraw, "text", lambda self, xy, text, *a, **k: seen.append((text, k.get("direction"))) or real(self, xy, text, *a, **k))
    render.number_frames("1481 N", str(tmp_path / "a"), langs.lang("ar"), render.style_of("flamme"), 0.2)
    render.number_frames("٢ م", str(tmp_path / "b"), langs.lang("ar"), render.style_of("flamme"), 0.2)
    assert ("1481 N", None) in seen and ("٢ م", "rtl") in seen


def test_a_latin_figure_stays_left_to_right_in_an_arabic_video(tmp_path, monkeypatch):
    from PIL import ImageDraw
    from adaptation import langs
    seen = []
    real = ImageDraw.ImageDraw.text
    monkeypatch.setattr(ImageDraw.ImageDraw, "text", lambda self, xy, text, *a, **k: seen.append((text, k.get("direction"))) or real(self, xy, text, *a, **k))
    render.number_frames("1481 N", str(tmp_path / "a"), langs.lang("ar"), render.style_of("flamme"), 0.2)
    render.number_frames("٢ م", str(tmp_path / "b"), langs.lang("ar"), render.style_of("flamme"), 0.2)
    assert ("1481 N", None) in seen and ("٢ م", "rtl") in seen


def test_beats_are_plain_numbers_the_database_can_keep(tmp_path):
    import json
    clicks = str(tmp_path / "clicks.wav")
    _ff("-f", "lavfi", "-i", "sine=f=1000:d=0.03,apad=whole_dur=0.5", "-af", "aloop=loop=-1:size=22050",
        "-t", "12", "-ar", "44100", clicks)
    beats = render.beats_of(clicks, 0, 10)
    assert beats and all(type(b) is float for b in beats)
    json.dumps(beats)                                   # a numpy number once broke the final render's save
