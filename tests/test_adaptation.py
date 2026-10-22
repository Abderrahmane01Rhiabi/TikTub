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


def test_script_problems_show_the_ellipsis_and_refuse_a_repeated_clip():
    p = lambda c, t: {"clip": c, "texte": t, "bandeau": "", "mots_cles": []}
    sc = {"passages": [p("A", "Une question ?"), p("B", "Une réponse."), p("A", "Mais au fait...")]}
    clips = {**_clips(), "C": clip(end=4.0)}
    found = script.problems(sc, clips, "fr")
    assert "Passage 3 : phrase incomplète (elle finit par « … »)." in found
    assert any("clip A est déjà utilisé au passage 1" in f for f in found)
    assert not any("déjà utilisé" in f for f in script.problems(sc, _clips(), "fr"))   # 2 clips for 3 passages: allowed


def test_the_writer_is_told_about_the_advertisement():
    seen = {}

    class G:
        def _generate_content(self, parts, **kw):
            seen["prompt"] = parts[0]["text"]
            return {"titre": "t", "passages": [{"clip": "A", "texte": "x."}]}
    script.write({"sujet": "piscines", "publicite": "IPoolGo, piscine ultra-résistante", "plans": []}, _clips(), "fr", gemini=G())
    assert "IPoolGo, piscine ultra-résistante" in seen["prompt"] and "JAMAIS deux fois le meme clip" in seen["prompt"]
    assert "reprend le clip du 1er" not in seen["prompt"]


def test_credits_never_show_an_account_number_and_tiktok_names_are_used():
    from adaptation import pipeline as ap
    clips = {"A": {"usable": True, "source": 0, "marks": ["filigrane TikTok @7315046821897962529", "@562burke"]}}
    assert ap.guess_credits([{}], clips) == "@562burke"
    assert ap.guess_credits([{"handle": "@123456789"}], {"A": {"usable": True, "source": 0, "marks": []}}) == ""
    assert sources._handle({"uploader_id": "7556965783809576214", "uploader": "iamklimakov"}) == "@iamklimakov"
    assert sources._handle({"uploader_id": "-201897941", "uploader": "proprirody"}) == "@proprirody"   # a VK group number
    assert ap.guess_credits([{"handle": "@-201897941"}, {"handle": "@thetraveller4614"}],
                            {"A": {"usable": True, "source": 0, "marks": []}, "B": {"usable": True, "source": 1, "marks": []}}) == "@thetraveller4614"
    assert sources._handle({"uploader_id": None, "channel": "Car Crashes Times"}) is None   # a display name, not a handle
    assert sources.MIN_CLIP == 1.0                                           # fast TikTok edits: 1.0-1.4 s shots


def test_advertisement_scenes_are_marked_and_not_searched():
    from adaptation import finder
    ref = {"plans_pub": [3, 4], "a_chercher": [{"scene": "piscine qui cède", "plans": [0, 1], "recherches": ["pool"]},
                                               {"scene": "démo IPoolGo", "plans": [3, 4], "recherches": ["ipoolgo"]}]}
    asked = []
    out = finder.suggest(ref, "u", search=lambda q: asked.append(q) or [], search_in=lambda h, q: [], sort=lambda f: None,
                         local=lambda f: {})
    assert [s.get("pub", False) for s in out["scenes"]] == [False, True] and asked == ["pool"]


def test_normalise_cleans_gemini_output():
    sc = script.normalise({"titre": "T" * 150, "tags": [" a ", ""], "passages": [
        {"clip": " a ", "texte": "  Une   phrase. ", "bandeau": "B", "mots_cles": ["x", "", "y", "z", "w"]},
        {"clip": "B", "texte": ""}]}, _clips())
    assert len(sc["titre"]) == 100 and sc["tags"] == ["a"]
    assert sc["passages"] == [{"clip": "A", "bandeau": "B", "texte": "Une phrase.", "mots_cles": ["x", "y", "z"], "annotation": None, "effets": None}]
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
    assert fixed["passages"][0] == {"clip": "A", "bandeau": "", "texte": "Pourquoi donc ?", "mots_cles": [], "annotation": None, "effets": None}
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


def test_a_render_with_every_effect_keeps_picture_and_voice_together(tmp_path):
    square, wide = tmp_path / "square.mp4", tmp_path / "wide.mp4"
    _lavfi(square, ["-f", "lavfi", "-i", "testsrc=size=320x304:rate=30", "-f", "lavfi", "-i", "sine=frequency=200"],
           6, ["-c:v", "libx264", "-c:a", "aac", "-shortest"])
    _lavfi(wide, ["-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30"], 6, ["-c:v", "libx264"])
    voice = tmp_path / "voice.wav"
    _lavfi(voice, ["-f", "lavfi", "-i", "anoisesrc=color=pink:seed=1:duration=6.6:sample_rate=44100"], 6.6)
    words = [{"w": w, "start": i * 0.5, "end": i * 0.5 + 0.4} for i, w in enumerate("un deux trois quatre".split())]
    words += [{"w": w, "start": 3.6 + i * 0.5, "end": 4.0 + i * 0.5} for i, w in enumerate("cinq six sept".split())]
    clips = {"A": {**clip(src=str(square), start=0.5, end=4.5, impact=2.0), "w": 320, "h": 304, "audio_ok": True,
                   "shock": True},
             "B": {**clip(src=str(wide), start=1.0, end=2.6, impact=2.0), "w": 640, "h": 360}}
    passages = [passage("A", 0.0, 3.0, words=[0, 1, 2, 3]), passage("B", 3.6, 6.6, words=[4, 5, 6])]
    fx = [{"ralenti": True, "zoom": {"cx": 0.3, "cy": 0.7, "z": 1.3}}, {"arret": True, "transition": True}]
    out = tmp_path / "out.mp4"
    r = render.render(passages, words, clips, str(voice), "fr", str(out), str(tmp_path / "w"), preview=False, effects=fx)
    v = checks.verify(str(out), str(voice), passages)
    assert abs(v["measures"]["video_s"] - v["measures"]["audio_s"]) <= 0.15
    assert all(o is not None and abs(o) <= 0.12 for o in v["measures"]["offsets"])
    assert r["segments"][0]["impact"] > 0.5
    sons = [e["son"] for e in r["recette"]["effets_sonores"]]
    assert any(x.startswith("shutter_") for x in sons)              # the freeze frame has its sound effect


# ------------------------------------------- voice library & channel settings

def _fake_elevenlabs(monkeypatch, known):
    from adaptation import voices as el

    def fetch(vid):
        if vid not in known:
            raise el.VoiceError(f"Voix {vid} introuvable chez ElevenLabs.")
        return {"voice_id": vid, "preview_url": None, **known[vid]}
    monkeypatch.setattr(el, "fetch_info", fetch)


def test_voices_are_added_by_id_with_language_and_accent(client, monkeypatch):
    _fake_elevenlabs(monkeypatch, {"v1": {"name": "Anas", "language": "ar", "accent": "modern standard"},
                                   "v2": {"name": "Haytham", "language": "ar", "accent": "egyptian"},
                                   "v3": {"name": "Mélanie", "language": "fr", "accent": "standard"}})
    r = client.post("/api/voices", json={"voice_ids": ["v1", "v2", "v3", "nope"]}).json()
    assert {v["voice_id"] for v in r["added"]} == {"v1", "v2", "v3"}          # regional accents kept too
    assert r["failed"][0]["voice_id"] == "nope" and "introuvable" in r["failed"][0]["error"]
    arabic = client.get("/api/voices?language=ar").json()["voices"]
    assert [v["display_name"] for v in arabic] == ["Anas", "Haytham"] and arabic[1]["accent"] == "egyptian"


def test_a_voice_can_be_renamed_and_keeps_its_name_when_refreshed(client, monkeypatch):
    _fake_elevenlabs(monkeypatch, {"v1": {"name": "Anas - Calm", "language": "ar", "accent": "modern standard"}})
    client.post("/api/voices", json={"voice_ids": ["v1"]})
    assert client.patch("/api/voices/v1", json={"name": "Arabe calme"}).json()["display_name"] == "Arabe calme"
    client.post("/api/voices", json={"voice_ids": ["v1"]})                   # refresh from ElevenLabs
    assert client.get("/api/voices").json()["voices"][0]["display_name"] == "Arabe calme"
    assert client.delete("/api/voices/v1").json()["voices"] == []
    assert client.get("/api/voices/v1/preview").status_code == 404


def test_channel_adaptation_settings_language_voice_music(client, project, monkeypatch):
    _fake_elevenlabs(monkeypatch, {"v1": {"name": "Anas", "language": "ar", "accent": "msa"},
                                   "v3": {"name": "Mélanie", "language": "fr", "accent": "standard"}})
    client.post("/api/voices", json={"voice_ids": ["v1", "v3"]})
    project.add_channel("chanA")
    r = client.put("/api/channels/chanA/adaptation", json={"language": "ar", "settings": {
        "voice_id": "v1", "music_file": "../x/song.mp3", "music_start": "33", "bogus": 1}}).json()
    assert r["settings"] == {"language": "ar", "voice_id": "v1", "music_file": "song.mp3", "music_start": 33.0,
                             "style": "classique"}
    assert [x["name"] for x in r["styles"]][:2] == ["classique", "flamme"]
    assert [v["voice_id"] for v in r["voices"]] == ["v1"]                    # only voices of its language
    assert client.put("/api/channels/chanA/adaptation", json={"language": "xx"}).status_code == 400


# ---------------------------------------------------------------- finder

def test_finder_scenes_fall_back_on_the_shots():
    from adaptation import finder
    ref = {"plans": [{"visuel": "Un tram percute une voiture"}, {"visuel": "un tram percute une voiture"},
                     {"visuel": "Interview"}]}
    assert [s["scene"] for s in finder.scenes(ref)] == ["Un tram percute une voiture", "Interview"]
    ref["a_chercher"] = [{"scene": "Un SUV contre un tram", "plans": [1, 2], "recherches": ["suv tram crash", " "]},
                         {"scene": ""}]
    s = finder.scenes(ref)
    assert len(s) == 1 and s[0]["recherches"] == ["suv tram crash"] and s[0]["plans"] == [1, 2]


def test_finder_credit_links_and_suggest():
    from adaptation import finder
    links = finder.credit_links(["Credits: @adrenalinejunkie4661", "9News", "9news"])
    assert [c["name"] for c in links] == ["Credits: @adrenalinejunkie4661", "9News"]
    assert links[0]["links"][1]["url"] == "https://www.tiktok.com/@adrenalinejunkie4661"
    assert "search_query=9News" in links[1]["links"][0]["url"]

    def search(q):
        return [{"id": vid, "url": f"https://www.youtube.com/watch?v={vid}"} for vid in ("refrefrefre", "aaaaaaaaaaa")]
    def search_in(handle, q):
        assert (handle, q) == ("adrenalinejunkie4661", "tram")
        return [{"id": "ccccccccccc", "url": "https://www.youtube.com/watch?v=ccccccccccc"}]

    def sort(found):
        found[0]["candidats"] = found[0]["candidats"][:1]
    ref = {"credits": ["@adrenalinejunkie4661"], "recherche_courte": "tram",
           "a_chercher": [{"scene": "Un tram", "recherches": ["tram crash", "tram cabin"]}]}
    out = finder.suggest(ref, "https://youtube.com/shorts/refrefrefre", search=search, search_in=search_in, sort=sort,
                         local=lambda found: {})
    sc = out["scenes"][0]
    assert [c["id"] for c in sc["candidats"]] == ["aaaaaaaaaaa"]      # the reference itself and duplicates are left out
    assert out["comptes"][0]["videos"][0]["id"] == "ccccccccccc" and out["verifs"] == {}
    assert sc["liens"][1]["url"] == "https://www.tiktok.com/search?q=tram+crash"


def test_finder_check_judges_plan_by_plan_with_a_partial_level():
    from adaptation import finder
    scenes = [{"scene": "des hommes bouchent un puits puis une pelleteuse", "plans": [0, 2], "indices": "café"},
              {"scene": "un geyser de boue", "plans": [1]}]
    plans = [{"visuel": "des hommes autour d'un jet de gaz"}, {"visuel": "un tube crache de la boue"},
             {"visuel": "une pelleteuse plante un pieu"}, {"visuel": "générique"}]

    class G:
        def _generate_content(self, parts, **kw):
            assert parts[0]["file_data"]["file_uri"].startswith("https://www.youtube.com/")
            text = parts[1]["text"]
            assert "1. des hommes autour d'un jet de gaz (indices : café)" in text and "partielle" in text
            assert "générique" not in text                      # a plan of no scene is not judged
            return {"plans": [{"plan": 1, "niveau": "Exacte", "moments": [{"debut": 40, "fin": 47}, "x"], "raison": "même puits"},
                              {"plan": "2", "niveau": "partielle", "moments": [{"debut": 90, "fin": 95}], "raison": "le jet seul"},
                              {"plan": 3, "niveau": "rien", "moments": [{"debut": 1}], "raison": "pas de pelleteuse"},
                              {"plan": 0, "niveau": "exacte"}, {"plan": 9, "niveau": "exacte"}],
                    "resume": "le puits d'Ia Phin"}
    r = finder.check("https://www.youtube.com/watch?v=aaaaaaaaaaa", scenes, plans, gemini=G())
    assert r["verdict"] == "oui" and r["raison"] == "le puits d'Ia Phin"
    assert r["par_scene"]["0"]["niveau"] == "exacte"            # the best of its plans: the excavator's "nothing" can't sink it
    assert r["par_scene"]["1"]["niveau"] == "partielle"
    assert r["par_plan"]["2"] == {"niveau": "rien", "moments": [], "raison": "pas de pelleteuse", "scene": 0, "defauts": ""}
    assert r["moments"] == [{"debut": 40, "fin": 47}, {"debut": 90, "fin": 95}]
    assert finder.sections(r, 207) == [[34.0, 53.0], [84.0, 101.0]]


def test_finder_check_downloads_a_youtube_video_gemini_may_not_open(monkeypatch):
    from adaptation import finder
    asked = []

    class G:
        def _generate_content(self, parts, **kw):
            asked.append(parts[0]["file_data"])
            return {"error": "API error: 403"}
    import yt_dlp

    class Boom:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, *a, **k): raise RuntimeError("ERROR: [youtube] x: Private video")
    monkeypatch.setattr(yt_dlp, "YoutubeDL", Boom)
    with pytest.raises(finder.FinderError, match="privée"):
        finder.check("https://www.youtube.com/watch?v=aaaaaaaaaaa", [{"scene": "x"}], gemini=G())
    assert asked == [{"file_uri": "https://www.youtube.com/watch?v=aaaaaaaaaaa"}]   # tried by link first


def test_finder_check_accepts_a_video_without_a_known_duration(monkeypatch, tmp_path):
    """Instagram gives no duration: the 20-minute filter must let it through."""
    import yt_dlp
    from adaptation import finder, sources
    seen = {}

    class DL:
        def __init__(self, opts): seen["opts"] = opts
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, url, download):
            assert seen["opts"]["match_filter"]({"title": "reel"}, incomplete=False) is None   # no duration: passes
            path = seen["opts"]["outtmpl"].replace("%(ext)s", "mp4")
            open(path, "wb").write(b"x")
            return {"title": "Video by hr_mahto_official", "uploader": "HR MAHTO", "ext": "mp4"}
        def prepare_filename(self, info): return seen["opts"]["outtmpl"].replace("%(ext)s", "mp4")
    monkeypatch.setattr(yt_dlp, "YoutubeDL", DL)
    monkeypatch.setattr(sources, "probe", lambda p: {"w": 576, "h": 1024, "duration": 22.1})
    monkeypatch.setattr(sources, "has_picture", lambda p: True)          # the fake file stands for a real video

    class G:
        def _upload_video_file(self, path): return {"name": "f", "uri": "u", "mime_type": "video/mp4"}
        def _wait_for_file_active(self, *a, **k): return True
        def _delete_file(self, name): pass
        def _generate_content(self, parts, **kw):
            return {"plans": [{"plan": 1, "niveau": "exacte", "moments": [{"debut": 0}]}], "resume": "sel"}
    r = finder.check("http://instagram.com/reel/DSHXwI3DEug/", [{"scene": "récolte du sel"}], gemini=G())
    assert r["verdict"] == "oui" and r["duration"] == 22.1 and r["title"] == "Video by hr_mahto_official · HR MAHTO"
    assert seen["opts"]["match_filter"]({"duration": 3600}, incomplete=False)   # a 1-hour video is still refused


def test_finder_check_falls_back_on_scenes_for_an_older_analysis():
    from adaptation import finder
    units = finder._units([{"scene": "un tram"}, {"scene": "une voiture", "indices": "rouge"}], [])
    assert [(u["plan"], u["scene"], u["text"]) for u in units] == [(0, 0, "un tram"), (1, 1, "une voiture")]


def test_finder_merges_every_search_and_ranks_by_how_it_was_found():
    from adaptation import finder
    ref = {"credits": [], "plans": [{}, {}],
           "a_chercher": [{"scene": "un puits crache du gaz", "plans": [0], "recherches": ["gas well"]},
                          {"scene": "un geyser", "plans": [1], "recherches": ["geyser"]}]}
    yt = lambda vid, t="": {"id": vid, "url": f"https://www.youtube.com/watch?v={vid}", "title": t or vid, "channel": "c"}

    def search(q):
        return {"gas well": [yt("aaaaaaaaaaa")], "khoan giếng": [yt("aaaaaaaaaaa"), yt("bbbbbbbbbbb")]}.get(q, [])

    def frames_fn(ref, url, work, found, report=None):
        return {"frames": [{"file": "f00.jpg", "scene": 0}, {"file": "f01.jpg", "scene": 0},
                           {"file": "f02.jpg", "scene": None}], "source": "short", "error": None}

    def image_search(files):
        vk = {"url": "https://vkvideo.ru/video-1_2", "title": "Железные нервы", "thumb": "", "platform": "VK"}
        short = {"url": "https://www.youtube.com/watch?v=refrefrefre", "title": "le Short lui-même", "thumb": "", "platform": "YouTube"}
        b = {"url": "https://www.youtube.com/watch?v=bbbbbbbbbbb", "title": "b", "thumb": "", "platform": "YouTube"}
        garage = {"url": "https://vkvideo.ru/video-9_9", "title": "Garage tour", "thumb": "", "platform": "VK"}
        return {"hits": {files[0]: [vk, short, b, garage], files[1]: [vk], files[2]: [{**vk, "url": "https://rutube.ru/video/x/"}]},
                "error": None, "seconds": 1}
    def sort_image(pools):                                  # the off-topic picture results go (title check)
        assert pools[-1]["scene"].startswith("n'importe laquelle")
        pools[0]["candidats"] = [c for c in pools[0]["candidats"] if "Garage" not in c["title"]]

    out = finder.suggest(ref, "https://youtube.com/shorts/refrefrefre", work_dir="w", search=search,
                         search_in=lambda h, q: [], sort=lambda found: None,
                         local=lambda found: {0: {"pays": "Viêt Nam", "langue": "Vietnamien", "recherches": ["khoan giếng"]}},
                         frames_fn=frames_fn, image_search=image_search, sort_image=sort_image)
    s0 = out["scenes"][0]
    by = {c["url"]: c for c in s0["candidats"]}
    assert set(by) == {"https://www.youtube.com/watch?v=aaaaaaaaaaa", "https://www.youtube.com/watch?v=bbbbbbbbbbb",
                       "https://vkvideo.ru/video-1_2"}           # one card per video, never the Short itself
    assert by["https://www.youtube.com/watch?v=aaaaaaaaaaa"]["origines"] == ["youtube", "langue"]
    assert by["https://www.youtube.com/watch?v=bbbbbbbbbbb"]["origines"] == ["langue", "image"]
    vk = by["https://vkvideo.ru/video-1_2"]
    assert vk["origines"] == ["image"] and vk["hits"] == 2 and vk["platform"] == "VK"
    assert by["https://www.youtube.com/watch?v=bbbbbbbbbbb"]["score"] > vk["score"]   # words AND a picture beat pictures alone
    assert s0["langue"]["langue"] == "Vietnamien" and "khoan" in s0["liens_langue"][0]["url"]
    assert [c["url"] for c in out["image_videos"]] == ["https://rutube.ru/video/x/"]   # a picture of no known scene
    assert out["image_videos"][0]["score"] < vk["score"]       # ... ranks lower
    assert out["scenes"][1]["candidats"] == [] and out["images"]["source"] == "short"


def test_finder_survives_a_blocked_image_search_and_no_picture():
    from adaptation import finder
    ref = {"a_chercher": [{"scene": "un tram", "recherches": ["tram"]}]}
    kw = dict(search=lambda q: [], search_in=lambda h, q: [], sort=lambda f: None, local=lambda f: {},
              sort_image=lambda pools: None)
    out = finder.suggest(ref, "u", work_dir="w", frames_fn=lambda *a, **k: {"frames": [{"file": "f.jpg", "scene": 0}], "source": "youtube"},
                         image_search=lambda files: {"hits": {}, "error": "captcha", "seconds": 1}, **kw)
    assert out["images"]["search_error"] == "captcha" and out["scenes"][0]["candidats"] == []
    out = finder.suggest(ref, "u", work_dir="w", frames_fn=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("ffmpeg")), **kw)
    assert "ffmpeg" in out["images"]["error"]


def test_verify_best_checks_the_most_promising_and_notes_failures():
    from adaptation import finder
    c = lambda u, sc, d=60: {"url": u, "score": sc, "duration": d}
    sug = {"scenes": [{"scene": "x", "candidats": [c("a", 1), c("b", 9), c("long", 99, 3600), c("e", 7)]}],
           "comptes": [{"videos": [c("b", 9), c("f", 5)]}], "image_videos": [c("g", 8)],
           "verifs": {"e": {"verdict": "oui"}}}
    seen = []

    def checker(url, scenes, plans):
        seen.append(url)
        if url == "g":
            raise finder.FinderError("bloquée")
        return {"verdict": "probable", "par_scene": {}}
    finder.verify_best(sug, {"plans": []}, n=3, checker=checker)
    assert sorted(seen) == ["a", "b", "g"]                   # the account's, the scene's, the best left; checked/too long skipped
    assert set(sug["verifs"]) == {"a", "b", "e"} and sug["verif_errors"] == {"g": "bloquée"}


def test_verify_best_gives_every_scene_a_check_before_the_high_scores():
    from adaptation import finder
    c = lambda u, sc, o="langue": {"url": u, "score": sc, "duration": 60, "origines": [o]}
    sug = {"scenes": [{"candidats": [c("a1", 2), c("a2", 1), c("ai", 4, "image")]}, {"candidats": [c("b1", 1)]}],
           "image_videos": [c("x", 9, "image"), c("y", 8, "image")]}
    seen = []
    finder.verify_best(sug, {}, n=4, checker=lambda u, s, p: seen.append(u) or {"verdict": "non"}, workers=1)
    assert seen == ["a1", "b1", "ai", "x"]                   # words first per scene, then pictures, then the rest
    many = {"scenes": [{"candidats": [c(f"t{k}", 2), c(f"i{k}", 1, "image")]} for k in range(7)]}
    seen.clear()
    finder.verify_best(many, {}, n=4, checker=lambda u, s, p: seen.append(u) or {"verdict": "non"}, workers=1)
    assert seen == ["t0", "t1", "i0", "i1"]                  # seven scenes: words can't take the whole budget
    many["comptes"] = [{"videos": [c("acc0", 2, "compte"), {**c("acc", 2, "compte"), "views": 1_400_000}]}]
    seen.clear()
    finder.verify_best(many, {}, n=4, checker=lambda u, s, p: seen.append(u) or {"verdict": "non"}, workers=1)
    assert seen[0] == "acc"                                  # the credited account first
    seen.clear()
    finder.verify_best({"scenes": [{"candidats": [c(f"t{k}", 2), c(f"i{k}", 1, "image")]} for k in range(7)]}, {},
                       n=8, words_share=1.0, workers=1, checker=lambda u, s, p: seen.append(u) or {"verdict": "non"})
    assert seen == [f"t{k}" for k in range(7)] + ["i0"]      # Script d'abord: every plan's words before any picture


# ---------------------------------------------------------------- image search / frames

def test_imagesearch_keeps_one_spelling_of_each_readable_video():
    from adaptation import imagesearch as im
    assert im.canonical("https://www.youtube.com/watch?app=desktop&v=S9xHYqVJ5BM&utm_medium=organic") == \
        "https://www.youtube.com/watch?v=S9xHYqVJ5BM"
    assert im.canonical("https://m.vkvideo.ru/video-187008039_456241866?pl=2&utm_source=y") == \
        "https://vkvideo.ru/video-187008039_456241866"
    assert im.canonical("https://m.vk.com/video-60130670_456283265") == "https://vkvideo.ru/video-60130670_456283265"
    assert im.canonical("https://rutube.ru/video/dc9f/?utm_source=x") == "https://rutube.ru/video/dc9f/"
    assert im.canonical("https://ok.ru/video/353465993834") is None          # yt-dlp can't read it
    assert im.canonical("https://www.milliyet.com.tr/galeri/kaza-479159") is None
    assert im.platform("https://vkvideo.ru/video-1_2") == "VK"


def test_imagesearch_ranks_by_pictures_and_says_when_blocked(monkeypatch):
    from adaptation import imagesearch as im

    async def fake(files, pause):
        return {"a": [{"url": "https://youtu.be/aaaaaaaaaaa", "title": "Tram - YouTube", "thumb": "//x"},
                      {"url": "https://news.example/article", "title": "", "thumb": ""}],
                "b": [{"url": "https://rutube.ru/video/r/", "title": "r", "thumb": "https://t"},
                      {"url": "https://www.youtube.com/watch?v=aaaaaaaaaaa&utm_x=1", "title": "Tram", "thumb": ""}],
                "c": {"error": "timeout"}}
    monkeypatch.setattr(im, "_yandex", fake)
    hits = im.search(["a", "b", "c"], pause=0)
    assert hits["a"] == [{"url": "https://www.youtube.com/watch?v=aaaaaaaaaaa", "title": "Tram", "thumb": "", "platform": "YouTube"}]
    assert im._title("Трамвай не объедет - Видео от Женская Газета VK Видео") == "Трамвай не объедет"
    assert hits["c"] == []
    ranked = im.rank(hits, {"0": ["a", "b"], "1": ["c"]})
    assert [(h["url"], h["hits"]) for h in ranked["0"]] == [("https://www.youtube.com/watch?v=aaaaaaaaaaa", 2),
                                                           ("https://rutube.ru/video/r/", 1)]

    async def blocked(files, pause):
        return {f: {"error": "captcha"} for f in files}
    monkeypatch.setattr(im, "_yandex", blocked)
    assert im.timed_search(["a"])["error"].startswith("Yandex n'a répondu")


def test_frames_clean_crops_the_picture_and_removes_added_text(tmp_path):
    from PIL import Image
    from adaptation import frames
    im = Image.new("RGB", (400, 800), (0, 0, 0))
    im.paste((200, 30, 30), (0, 200, 400, 600))                 # the real picture: a band in the middle
    im.paste((255, 255, 255), (0, 200, 400, 250))               # a banner along its top edge
    im.paste((255, 255, 255), (150, 380, 250, 420))             # a caption in the middle
    raw, out = tmp_path / "raw.jpg", tmp_path / "out.jpg"
    im.save(raw)
    assert frames.clean(str(raw), [250, 0, 750, 1000], [[250, 0, 312, 1000], [475, 375, 525, 625]], str(out))
    pic = Image.open(out)
    assert pic.width == 400 and abs(pic.height - 350) <= 1     # band minus the banner
    assert pic.getpixel((200, 155))[1] < 120                    # the middle caption is painted over, not white
    assert frames.clean(str(raw), [250, 0, 260, 1000], [], str(out)) is None   # nothing left to search


def test_frames_times_scenes_and_the_public_fallback(monkeypatch, tmp_path):
    from adaptation import frames, sources
    assert frames._times([(0, 2), (2, 10)]) == [1.0, 4.0, 6.0, 8.0]          # a long shot gives three
    assert len(frames._times([(k, k + 1) for k in range(40)])) == frames.MAX_FRAMES
    plans = [{"debut": 0, "fin": 5}, {"debut": 5, "fin": 9}]
    scenes = [{"plans": [1]}]
    assert frames._plan_of(6, plans) == 1 and frames._scene_of(1, scenes) == 0 and frames._scene_of(0, scenes) is None

    monkeypatch.setattr(sources, "download", lambda *a, **k: (_ for _ in ()).throw(sources.SourceError("robot")))
    raw = tmp_path / "public1.jpg"
    from PIL import Image
    Image.new("RGB", (640, 360), (90, 90, 90)).save(raw)
    monkeypatch.setattr(frames, "_public_frames", lambda url, work, d: [(str(raw), 7.5)])
    monkeypatch.setattr(sources, "find_boxes", lambda stills: [(None, [], [])])
    out = frames.reference_frames({"plans": plans}, "https://youtube.com/shorts/x", str(tmp_path), scenes)
    assert out["source"] == "youtube" and out["error"] == "robot"
    assert out["frames"] == [{"file": "f00.jpg", "t": 7.5, "plan": None, "scene": None}]   # no shots: not tied to a scene
def test_finder_sort_out_keeps_what_gemini_keeps_and_everything_on_failure():
    from adaptation import finder
    found = [{"scene": "tram", "candidats": [{"title": t, "channel": "c"} for t in ("tram crash", "kangourou", "tram 2")]}]

    class G:
        def __init__(self, r): self.r = r
        def _generate_content(self, parts, **kw): return self.r
    finder.sort_out(found, gemini=G({"error": "quota"}))
    assert len(found[0]["candidats"]) == 3
    finder.sort_out(found, gemini=G({"garder": {"0": [2, 0, 0, 9]}}))
    assert [c["title"] for c in found[0]["candidats"]] == ["tram 2", "tram crash"]

    class PerScene:                                         # one call per scene: a failed one only spares its scene
        def _generate_content(self, parts, **kw):
            return {"garder": {"1": [0]}} if "Scene 1:" in parts[0]["text"] else "cut off"
    two = [{"scene": "a", "candidats": [{"title": "x"}, {"title": "y"}]}, {"scene": "b", "candidats": [{"title": "z"}, {"title": "w"}]}]
    finder.sort_out(two, gemini=PerScene())
    assert [len(s["candidats"]) for s in two] == [2, 1]


def test_finder_sections_pad_and_merge_the_verified_moments():
    from adaptation import finder
    v = {"verdict": "oui", "moments": [{"debut": 100, "fin": 110}, {"debut": 118, "fin": 125}, {"debut": 400, "fin": 405}]}
    assert finder.sections(v, 600) == [[94.0, 131.0], [394.0, 411.0]]
    assert finder.sections(v, 60) is None                    # a short video is taken whole
    assert finder.sections({**v, "verdict": "non"}, 600) is None
    assert finder.sections(None, 600) is None


def test_download_errors_are_explained():
    from adaptation import sources
    assert "robot" in sources.explain("https://www.youtube.com/watch?v=x", "ERROR: Sign in to confirm you're not a bot")
    vk = sources.explain("https://vkvideo.ru/video-1_2", "ERROR: [vk] Sign in to confirm you're not a bot")
    assert vk.startswith("VK refuse") and "YouTube" not in vk
    msg = sources.explain("u", "\x1b[0;31mERROR:\x1b[0m [youtube] jlQv41qROxk: This video is not available")
    assert "bloquée dans ton pays" in msg and "\x1b" not in msg


def test_check_match_does_not_step_over_a_sharp_peak():
    from adaptation import checks
    rng = np.random.default_rng(3)
    smooth = lambda x: np.convolve(x, np.ones(5) / 5, mode="same")   # like speech at 8 kHz: a peak a few samples wide
    ref = smooth(rng.normal(size=800))
    win = np.concatenate([smooth(rng.normal(size=1003)) * 0.3, ref, smooth(rng.normal(size=500)) * 0.3])
    best, at = checks._match(win, ref)
    assert at == 1003 and best > 0.99


def test_impact_sounds_only_where_a_real_shock_is_heard():
    from adaptation import render
    crash = {"audio_ok": True, "shock": True}
    salt = {"audio_ok": False, "shock": False}
    hammer_in_speech = {"audio_ok": False, "shock": True}
    assert render.impact_sound(crash, None) is crash
    assert render.impact_sound(salt, crash) is None                    # no borrowed boom under a calm shot
    assert render.impact_sound(hammer_in_speech, crash) is crash       # a shock drowned in speech: a clean one borrowed
    assert render.impact_sound({"audio_ok": False}, crash) is None     # older analysis: never borrowed
    old_clean = {"audio_ok": True}
    assert render.impact_sound(old_clean, None) is old_clean


def test_a_repost_of_the_reference_short_is_never_usable():
    from adaptation import finder
    seen = {}

    class G:
        def _generate_content(self, parts, **kw):
            seen["prompt"] = parts[1]["text"]
            return {"copie_du_modele": True, "plans": [{"plan": 1, "niveau": "exacte", "moments": [{"debut": 0}]}], "resume": "repost"}
    model = finder.model_of({"script_complet": "Why do people clip horses?", "duree_s": 30})
    r = finder.check("https://www.youtube.com/watch?v=aaaaaaaaaaa", [{"scene": "tonte"}], gemini=G(), model=model)
    assert "Why do people clip horses?" in seen["prompt"] and "30 s" in seen["prompt"]
    assert r["copie"] and r["verdict"] == "non" and r["par_scene"]["0"]["niveau"] == "rien" and r["moments"] == []
    assert finder.model_of({"plans": []}) is None
    calls = []
    finder.verify_best({"scenes": [{"candidats": [{"url": "a", "score": 1, "origines": ["youtube"]}]}]},
                       {"script_complet": "x", "duree_s": 30}, checker=lambda u, s, p, **kw: calls.append(kw) or {"verdict": "non"})
    assert calls == [{"model": {"texte": "x", "duree": 30}}]


def test_a_download_without_picture_is_never_returned(monkeypatch, tmp_path):
    from adaptation import sources
    calls = []

    def fake(url, d, name, sections=None, fmt=sources.VIDEO_FORMAT):
        calls.append((sections, fmt))
        path = tmp_path / f"{name}.mp4"
        path.write_bytes(b"x")
        return str(path)
    monkeypatch.setattr(sources, "_download", fake)
    monkeypatch.setattr(sources, "has_picture", lambda path: False)
    with pytest.raises(sources.SourceError, match="pas d'image"):
        sources.download("u", str(tmp_path), "a", [[1, 5]])          # a section: the caller takes the whole video
    with pytest.raises(sources.SourceError, match="sans image"):
        sources.download("u", str(tmp_path), "b")
    assert calls[-1] == (None, "b/best")                             # the whole video tried with a plain format
    monkeypatch.setattr(sources, "has_picture", lambda path: True)
    assert sources.download("u", str(tmp_path), "c").endswith("c.mp4")
    assert sources.VIDEO_FORMAT.startswith("bv*[vcodec^=avc1]")


def test_a_channel_style_colours_its_banners_and_captions(tmp_path):
    from PIL import Image
    from adaptation import render, settings
    from adaptation.langs import lang
    st = render.style_of("flamme")
    out = render.banner_png("PNEUS : DÉFORMATION", str(tmp_path / "b.png"), lang("fr"), st)
    im = Image.open(out).convert("RGBA")
    reds = sum(1 for x in range(0, render.W, 6) for y in range(20, 140, 6)
               if im.getpixel((x, y))[0] > 180 and im.getpixel((x, y))[1] < 60 and im.getpixel((x, y))[3] > 200)
    assert reds > 50                                         # the Flamme box is red
    ass = tmp_path / "c.ass"
    passages = [{"mots_cles": ["pneu"], "words": [0, 1]}]
    words = [{"w": "Le", "start": 0.0, "end": 0.3}, {"w": "pneu", "start": 0.3, "end": 0.7}]
    segs = [{"k": 0, "va": 0.0, "vb": 1.0, "out": 0.0, "dur": 1.2, "ws": 0.0}]
    render.captions_ass(passages, words, segs, str(ass), lang("fr"), render.style_of("neon"))
    assert render._ass_color("#00E5FF") in ass.read_text()   # the Néon keyword colour
    assert render.style_of("inconnu") is render.STYLES["classique"]
    assert settings.channel_settings({"adaptation": {"style": "or"}})["style"] == "or"
    assert settings.channel_settings({"adaptation": {"style": "n'importe"}})["style"] == "classique"
    assert settings.clean_update({"style": "neon"}) == {"style": "neon"} and settings.clean_update({"style": "x"}) == {}
    render.style_preview("clair", lang("ar"), str(tmp_path / "p.jpg"))
    assert (tmp_path / "p.jpg").exists()
