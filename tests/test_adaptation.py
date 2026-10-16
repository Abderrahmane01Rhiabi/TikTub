"""Adaptation engine: timeline, captions, banners, clip clean-up rules,
script checks, voice alignment, and one real (tiny, synthetic) render with
the automatic checks run on it."""

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from adaptation import checks, langs, render, script, sources, voices

FR, AR = langs.lang("fr"), langs.lang("ar")


def clip(start=0.0, end=6.0, impact=3.0, src="x.mp4", **kw):
    return {"src": src, "start": start, "end": end, "impact": impact, "w": 480, "h": 456, **kw}


def passage(cid, start, end, words=(), texte="a b c", bandeau="SUJET : DETAIL 😐"):
    return {"clip": cid, "start": start, "end": end, "words": list(words), "texte": texte, "bandeau": bandeau,
            "mots_cles": ["b"]}


# ------------------------------------------------------------------ timeline

def test_timeline_hooks_first_crash_early_and_tightens_pauses():
    clips = {"A": clip(), "B": clip(impact=4.0)}
    segs, total = render.build_timeline([passage("A", 0.0, 3.0), passage("B", 4.0, 7.0)], clips)
    assert segs[0]["impact_out"] <= 1.0                       # the hook: a crash within the first second
    assert segs[1]["out"] == pytest.approx(segs[0]["dur"])     # the 1 s pause in the voice is gone
    assert total == pytest.approx(sum(s["dur"] for s in segs))
    assert render.out_time(segs, 4.5) == pytest.approx(segs[1]["out"] + 0.54)


def test_a_clip_shorter_than_its_sentence_starts_at_its_beginning():
    segs, _ = render.build_timeline([passage("A", 0.0, 5.0)], {"A": clip(end=2.0, impact=1.0)})
    assert segs[0]["ws"] == 0.0


# ------------------------------------------------------------------ text

def test_banner_colours_the_part_after_the_colon_and_keeps_the_emoji():
    parts, emoji = render.banner_parts("CONDUCTRICE : AUCUNE RÉACTION 😐")
    assert parts == [("CONDUCTRICE : ", "white"), ("AUCUNE RÉACTION", render.BANNER_KEY)] and emoji == "😐"
    parts, emoji = render.banner_parts("POURQUOI S'ÉNERVER ?")
    assert parts[-1] == ("?", render.BANNER_KEY) and emoji is None


def test_caption_groups_never_exceed_the_screen():
    long_words = [{"w": w, "start": i, "end": i + 0.5} for i, w in
                  enumerate("Pourquoi les conducteurs de tramway ne paniquent jamais".split())]
    for g in render.caption_groups(long_words, FR):
        assert len(g) <= 3
        assert len(g) == 1 or render.caption_width([w["w"] for w in g], FR) <= render.CAPTION_MAX_W


def test_a_sentence_break_always_ends_a_caption_group():
    ws = [{"w": w, "start": 0, "end": 1} for w in ["Bonjour,", "le", "tram"]]
    assert [[w["w"] for w in g] for g in render.caption_groups(ws, FR)] == [["Bonjour,"], ["le", "tram"]]


def test_arabic_captions_are_right_to_left_with_one_colour_run_per_word(tmp_path):
    words = [{"w": w, "start": i * 0.4, "end": i * 0.4 + 0.3} for i, w in enumerate(["لماذا", "لا", "يفزع"])]
    p = passage("A", 0.0, 1.2, words=[0, 1, 2])
    p["mots_cles"] = ["يفزع"]
    segs, _ = render.build_timeline([p], {"A": clip()})
    render.captions_ass([p], words, segs, tmp_path / "c.ass", AR)
    text = (tmp_path / "c.ass").read_text(encoding="utf-8")
    assert ",-1\n" in text.split("[Events]")[0]                      # right-to-left base direction
    event = [l for l in text.splitlines() if l.startswith("Dialogue")][0]
    assert event.count("\\c&H") == 3                                  # one colour run per word


# ------------------------------------------------------------------ sources

def test_strips_at_the_edges_are_cropped_other_marks_painted_over():
    top, bot, patches = sources.edges_and_patches(
        [[920, 850, 990, 950],          # TikTok logo, bottom right -> crop
         [300, 0, 380, 200],            # name on the left, mid-height -> paint
         [0, 0, 900, 900]],             # too big: would ruin the clip -> ignored
        480, 456)
    assert bot > 0 and top == 0 and len(patches) == 1


def test_band_from_area_accepts_only_a_full_width_landscape_band():
    assert sources.band_from_area([212, 0, 545, 1000], 1080, 1920) == (407, 1046)
    assert sources.band_from_area([0, 0, 1000, 1000], 1080, 1920) is None      # full screen
    assert sources.band_from_area([212, 200, 545, 800], 1080, 1920) is None    # not full width


def test_a_crash_jolt_is_not_a_cut_but_a_scene_change_is():
    rng = np.random.default_rng(0)
    scene_a, scene_b = rng.uniform(0, 255, (16, 16)), rng.uniform(0, 255, (16, 16))
    shaky = np.stack([scene_a + rng.normal(0, 4, (16, 16)) for _ in range(20)])
    assert not sources.is_cut(shaky, 10)
    cut = np.stack([scene_a] * 10 + [scene_b] * 10)
    assert sources.is_cut(cut, 10)


# ------------------------------------------------------------------ script

def _clips():
    return {"A": clip(end=4.0), "B": clip(end=6.0)}


def test_script_problems_flag_unknown_clips_long_and_incomplete_sentences():
    sc = {"passages": [{"clip": "A", "texte": "x" * 200, "bandeau": "", "mots_cles": []},
                       {"clip": "Z", "texte": "Bonjour.", "bandeau": "", "mots_cles": []},
                       {"clip": "B", "texte": "Et donc, tout le monde se demande :", "bandeau": "", "mots_cles": []}]}
    found = " | ".join(script.problems(sc, _clips(), "fr"))
    assert "trop longue" in found and "« Z »" in found and "incomplète" in found


def test_normalise_cleans_gemini_output():
    sc = script.normalise({"titre": "T" * 150, "tags": [" a ", ""], "passages": [
        {"clip": " a ", "texte": "  Une   phrase. ", "bandeau": "B", "mots_cles": ["x", "", "y", "z", "w"]},
        {"clip": "B", "texte": ""}]}, _clips())
    assert len(sc["titre"]) == 100 and sc["tags"] == ["a"]
    assert sc["passages"] == [{"clip": "A", "bandeau": "B", "texte": "Une phrase.", "mots_cles": ["x", "y", "z"]}]
    with pytest.raises(script.ScriptError):
        script.normalise({"error": "boom"}, _clips())


def test_critique_keeps_the_clips_and_falls_back_on_a_bad_answer():
    class Fake:
        def __init__(self, answer): self.answer = answer
        def _generate_content(self, *a, **k): return self.answer
    sc = {"titre": "t", "description": "", "tags": [], "passages": [
        {"clip": "A", "texte": "Pourquoi ?", "bandeau": "", "mots_cles": []}]}
    good = {"passages": [{"clip": "B", "texte": "Pourquoi donc ?", "bandeau": "", "mots_cles": []}], "corrections": ["x"]}
    fixed = script.critique(sc, "fr", _clips(), gemini=Fake(good))
    assert fixed["passages"][0] == {"clip": "A", "bandeau": "", "texte": "Pourquoi donc ?", "mots_cles": []}
    assert fixed["corrections"] == ["x"]
    assert script.critique(sc, "fr", _clips(), gemini=Fake({"passages": []}))["passages"] == sc["passages"]


# ------------------------------------------------------------------ voices

def test_alignment_turns_characters_into_words_and_passage_spans():
    text = "Ab cd. Ef"
    st = [i * 0.1 for i in range(len(text))]
    en = [t + 0.1 for t in st]
    out = voices.align([{"texte": "Ab cd."}, {"texte": "Ef"}], [(0, 6), (7, 9)], list(text), st, en)
    assert [w["w"] for w in out["words"]] == ["Ab", "cd.", "Ef"]
    assert out["passages"][0]["words"] == [0, 1] and out["passages"][1]["words"] == [2]
    assert out["passages"][1]["start"] == pytest.approx(0.7)


# ------------------------------------------------------------- real render

def _lavfi(out, src, seconds, extra=()):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *src, "-t", str(seconds), *extra, str(out)], check=True)


def test_preview_render_passes_the_automatic_checks(tmp_path):
    square, wide = tmp_path / "square.mp4", tmp_path / "wide.mp4"
    _lavfi(square, ["-f", "lavfi", "-i", "testsrc=size=480x456:rate=30", "-f", "lavfi", "-i", "sine=frequency=200"],
           8, ["-c:v", "libx264", "-c:a", "aac", "-shortest"])
    _lavfi(wide, ["-f", "lavfi", "-i", "testsrc2=size=1080x608:rate=30"], 8, ["-c:v", "libx264"])
    voice = tmp_path / "voice.wav"          # a "voice": two noise bursts with a pause, like two sentences
    _lavfi(voice, ["-f", "lavfi", "-i", "anoisesrc=color=pink:seed=1:duration=3:sample_rate=44100", "-f", "lavfi",
                   "-i", "anullsrc=r=44100:cl=mono", "-f", "lavfi",
                   "-i", "anoisesrc=color=brown:seed=7:duration=3:sample_rate=44100",
                   "-filter_complex", "[1]atrim=0:0.6[s];[0][s][2]concat=n=3:v=0:a=1"], 7)
    words = [{"w": w, "start": i * 0.5, "end": i * 0.5 + 0.4} for i, w in enumerate("un deux trois quatre".split())]
    words += [{"w": w, "start": 3.6 + i * 0.5, "end": 4.0 + i * 0.5} for i, w in enumerate("cinq six sept".split())]
    clips = {"A": {**clip(src=str(square)), "w": 480, "h": 456, "audio_ok": True},
             "B": {**clip(src=str(wide)), "w": 1080, "h": 608, "delogo": [(10, 10, 60, 30)]}}
    passages = [passage("A", 0.0, 3.0, words=[0, 1, 2, 3]), passage("B", 3.6, 6.6, words=[4, 5, 6])]
    r = render.render(passages, words, clips, str(voice), "fr", str(tmp_path / "out.mp4"), str(tmp_path / "w"),
                      credit="@a · @b", preview=True)
    probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=width,height",
                                                "-of", "json", str(tmp_path / "out.mp4")]))
    assert (probe["streams"][0]["width"], probe["streams"][0]["height"]) == (540, 960)
    assert [s["clip"] for s in r["segments"]] == ["A", "B"]
    v = checks.verify(str(tmp_path / "out.mp4"), str(voice), passages)
    assert abs(v["measures"]["video_s"] - v["measures"]["audio_s"]) <= 0.15
    assert all(o is not None and abs(o) <= 0.12 for o in v["measures"]["offsets"])
    assert not (tmp_path / "out.mp4.part.mp4").exists()
