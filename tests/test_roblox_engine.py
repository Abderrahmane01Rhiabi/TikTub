"""Montage Roblox, the engine: which passages of a long video are looked at, the moments kept, the plan checked,
and the five styles really rendered (a small synthetic video, a fake voice: no paid call)."""

import json
import subprocess

import pytest

from roblox import moments, plan, render, sources


def test_the_passages_are_the_most_replayed_ones_never_overlapping():
    heat = [{"start_time": k * 72.0, "end_time": (k + 1) * 72.0, "value": v} for k, v in enumerate([0.6, 0.1, 0.1, 0.9, 0.85, 0.2] + [0.05] * 94)]
    w = sources.windows({"duree": 7200.0, "heatmap": heat}, n=3, size=75)
    assert w == sorted(w) and len(w) == 3
    assert any(a <= 252 <= b for a, b in w) and any(a <= 36 <= b for a, b in w)          # the 0.9 and the 0.6
    assert all(b1 <= a2 for (_, b1), (a2, _) in zip(w, w[1:]))                          # 0.85 overlapped 0.9: left out
    chap = sources.windows({"duree": 3600.0, "chapitres": [{"start_time": 0}, {"start_time": 600}]}, n=4, size=75)
    assert chap == [[0.0, 75.0], [600.0, 675.0]]
    assert len(sources.windows({"duree": 3600.0}, n=4, size=75)) == 4                    # no graph, no chapter: spread
    assert sources.windows({"duree": 50.0}) == [[0.0, 50.0]]                              # a short video: all of it


def test_the_subtitles_are_read_word_by_word(tmp_path):
    p = tmp_path / "s.json3"
    p.write_text(json.dumps({"events": [{"tStartMs": 11160, "dDurationMs": 3730, "segs": [{"utf8": "I'm"}, {"utf8": " going", "tOffsetMs": 160}]},
                                        {"tStartMs": 13870, "segs": [{"utf8": "\n"}]}]}))
    assert sources.words(str(p)) == [("I'm", 11.16, 11.32), ("going", 11.32, 14.89)]
    assert sources.words(None) == []


def test_only_the_moments_inside_the_file_are_kept():
    class G:
        def _generate_content(self, parts, **kw):
            return [{"debut": 9.5, "fin": 20, "chute": 17.5}, {"debut": 101, "fin": 113, "chute": 108}, {"debut": "x"}]
    assert [m["debut"] for m in moments.find("f.mp4", 73.0, gemini=G())] == [9.5]


CAT = [{"id": "w0#0", "debut": 10.0, "fin": 22.0, "chute": 18.0, "resume": "r", "mise_en_place": "m", "dialogues": "d"},
       {"id": "w0#1", "debut": 30.0, "fin": 40.0, "chute": 37.0, "resume": "r", "mise_en_place": "m", "dialogues": "d"}]
T = {"fr": "Bonjour", "en": "Hello"}
PUB = {"fr": {"titre": "Titre", "description": "d", "tags": ["a"]}, "en": {"titre": "Title", "description": "d", "tags": ["a"]}}


def test_the_plan_keeps_what_can_be_made_and_says_what_cannot():
    raw = {"clip": {"moment": "w0#0", "titre": T, "publication": PUB},
           "pov": {"moment": "w0#1", "debut": 2, "fin": 50, "pov": T, "publication": PUB},              # cut to the moment
           "devine": {"moment": "nope", "arret": 3, "question": T, "final": T, "publication": PUB},
           "top3": {"titre": T, "publication": PUB, "rangs": [{"rang": 1, "moment": "w0#0", "debut": 1, "fin": 7, "label": T},
                                                              {"rang": 3, "moment": "w0#1", "debut": 0, "fin": 6, "label": T}]},
           "histoire": {"titre": T, "publication": PUB, "passages": [{"moment": "w0#0", "debut": 0, "fin": 4, "textes": {"fr": "a"}}]}}
    p, dropped = plan.normalise(raw, CAT, list(plan.STYLES), ["fr", "en"])
    assert set(p) == {"clip", "pov", "top3"}
    assert p["pov"]["fin"] == 10.0 and [r["rang"] for r in p["top3"]["rangs"]] == [2, 1]        # renumbered, #1 last
    assert len(dropped) == 2 and all("pas de moment" in d for d in dropped)
    assert plan.publication(p, "clip", "en")["titre"] == "Title"
    schema = plan.prompt({"titre": "x"}, CAT, list(plan.STYLES), ["fr", "en"]).split("JSON uniquement :")[1]
    json.loads(schema.replace(": s", ": 0"))                                                    # the asked JSON is valid


# ---- the five styles, really rendered

@pytest.fixture(scope="module")
def source(tmp_path_factory):
    d = tmp_path_factory.mktemp("rb")
    path = str(d / "w0.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=45", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=45", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", path],
                   check=True)
    return d, path


def fake_voice(passages, voice_id, lang, out):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "6", out], check=True)
    spans = [(k * 2.0, k * 2.0 + 1.8) for k in range(len(passages))]
    words = [{"w": w, "start": a + 0.3 * i, "end": a + 0.3 * i + 0.25} for (a, _), p in zip(spans, passages) for i, w in enumerate(p["texte"].split())]
    return {"words": words, "passages": [{"start": a, "end": b} for a, b in spans], "duration": spans[-1][1]}


def duration(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                                capture_output=True, text=True).stdout)


@pytest.mark.parametrize("style,p,expected", [
    ("clip", {"moment": "w0#0", "titre": T}, 10.0),
    ("pov", {"moment": "w0#0", "debut": 1.0, "fin": 9.0, "pov": {"fr": "POV : quand ça part", "en": "POV: when it goes"}}, 8.0),
    ("histoire", {"titre": T, "passages": [{"moment": "w0#0", "debut": 0, "fin": 3, "textes": {"fr": "Il entre", "en": "He walks in"}},
                                           {"moment": "w0#1", "debut": 1, "fin": 4, "textes": {"fr": "Et là", "en": "And then"}}]}, 4.4),
    ("top3", {"titre": T, "rangs": [{"rang": 2, "moment": "w0#1", "debut": 1, "fin": 7, "label": T},
                                    {"rang": 1, "moment": "w0#0", "debut": 2, "fin": 9, "label": T}]}, 13.0),
    ("devine", {"moment": "w0#0", "arret": 7.5, "question": T, "final": T}, 13.53)])     # 7.5 s + 3 s frozen + 3 s
def test_each_style_renders_a_vertical_short(source, style, p, expected):
    d, path = source
    ms = {"w0#0": {"fichier": path, "fichier_duree": 45.0, "t0": 100.0, "debut": 10.0, "fin": 22.0, "chute": 18.0, "action_x": 0.5},
          "w0#1": {"fichier": path, "fichier_duree": 45.0, "t0": 100.0, "debut": 30.0, "fin": 40.0, "chute": 37.0, "action_x": 0.3}}
    words = [("Let's", 112.0, 112.4), ("eat", 112.4, 112.9)]
    ctx = render.Context(ms, words, "fr", "en", "voice", str(d), lambda lines, lang: [f"[{lang}] " + l for l in lines], fake_voice)
    out = str(d / f"{style}.mp4")
    got = render.make(style, p, ctx, out)
    assert abs(got - expected) < 0.2 and abs(duration(out) - expected) < 0.3
    w, h = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", out],
                          capture_output=True, text=True).stdout.strip().split(",")
    assert (w, h) == ("1080", "1920")
    ass = open(out[:-4] + ".ass", encoding="utf-8").read()
    if style == "clip":
        assert "[fr] Let's eat" in ass and "Bonjour" in ass                       # the line said, translated
    if style == "devine":
        assert ass.count("Gros") >= 3 + 1


def test_the_channels_music_replaces_the_original_sound(source):
    d, path = source
    ms = {"w0#0": {"fichier": path, "fichier_duree": 45.0, "t0": 0.0, "debut": 10.0, "fin": 22.0, "chute": 18.0}}
    ctx = render.Context(ms, [], "fr", "fr", None, str(d), lambda l, x: l)
    music = str(d / "m.mp3")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=3", music], check=True)
    out = str(d / "music.mp4")
    assert render.make("pov", {"moment": "w0#0", "debut": 0, "fin": 6, "pov": T}, ctx, out, music=music) == 6.0
    assert abs(duration(out) - 6.0) < 0.3                                       # a 3-s track loops to the end


def test_two_lines_of_dialogue_never_show_at_once():
    words = [(w, 10 + 0.2 * k, 10 + 0.2 * k + 0.18) for k, w in enumerate("so hey Barry you have not no well gotta do it now".split())]
    lines = render.dialogue_lines(words, 0, 100)                     # a player who talks without a pause
    assert len(lines) >= 2 and all(a["b"] <= b["a"] for a, b in zip(lines, lines[1:]))
