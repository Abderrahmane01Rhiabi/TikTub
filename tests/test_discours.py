"""The « Discours » mode (adaptation/discours.py, discours_pipeline.py): the passage chosen on the words, the pauses
tightened, the cut-aways placed, the captions translated on the speaker's timing, the 3 layers of settings, the
films refused unless the channel allows them, a real render, and a project from the link to Publication with
Gemini, Whisper, Demucs, YouTube and ffmpeg replaced by fakes."""

import json
import os
import shutil
import subprocess

import pytest

import db
from adaptation import discours as D, discours_pipeline as dp, musique, pipeline as ap

WORDS = [[w, round(i * 0.5, 2), round(i * 0.5 + 0.4, 2)] for i, w in enumerate(
    ("Forty years ago, I met him. He was young, hungry and already great. When they created this award, "
     "Denzel was waiting in the wings. Congratulations, my friend. Thank you all for coming tonight. "
     "Now let us talk about the film.").split())]


class FakeGemini:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts = []

    def _generate_content(self, parts, **kw):
        self.prompts.append(parts[0]["text"])
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


# ---------------------------------------------------------------- engine

def test_settings_in_three_layers_and_checked():
    s = D.clean_settings({"cadre": "4:5", "taille": 300, "fond": "rose", "volume_db": "fort", "grain": False,
                          "sous_titres": "karaoke"})
    assert s["cadre"] == "4:5" and s["taille"] == 100 and s["fond"] == "noir" and s["volume_db"] == 7.0
    assert s["grain"] is False and s["sous_titres"] == "escalier"        # a space's own style is not offered here
    chan = D.channel_settings({"discours": {"fond": "flou", "films": True, "sous_titres": "editorial"}})
    assert chan["fond"] == "flou" and chan["films"] is True and chan["sous_titres"] == "editorial"
    video = D.clean_settings({"cadre": "16:9"}, base=D.clean_settings(chan))
    assert video["cadre"] == "16:9" and video["fond"] == "flou" and video["sous_titres"] == "editorial"
    assert D.channel_settings({})["films"] is False                       # films: never unless ticked
    assert D.caption_style_for({"sous_titres": "typewriter"}, "ar") == "escalier"


def test_a_passage_snaps_to_the_words_and_never_overlaps():
    g = FakeGemini({"orateur": "Morgan Freeman", "passages": [
        {"debut": 0, "fin": 9.5, "titre": "L'hommage", "pourquoi": "fort", "note": 9},
        {"debut": 2, "fin": 12, "titre": "Doublon", "note": 8},                 # overlaps the first: dropped
        {"debut": 10.2, "fin": 19.9, "titre": "Merci", "note": "7"}]})
    r = D.passages(WORDS, 45, gemini=g)
    assert r["orateur"] == "Morgan Freeman"
    assert [(x["i0"], x["i1"]) for x in r["passages"]] == [(0, 18), (20, 39)]
    first = r["passages"][0]
    assert first["debut"] == 0.0 and first["fin"] == WORDS[18][2] + 0.25 and first["note"] == 9
    assert "entre 33 et 60 s" in g.prompts[0]
    with pytest.raises(D.DiscoursError):                                   # only passages already proposed
        D.passages(WORDS, 45, avoid=r["passages"], gemini=FakeGemini({"passages": [{"debut": 1, "fin": 9},
                                                                                {"debut": 21, "fin": 33}]}))
    with pytest.raises(D.DiscoursError):
        D.passages(WORDS[:10], 45, gemini=g)


def test_pauses_are_tightened_on_the_cut_timeline():
    parts = [[0.0, 2.0], [3.0, 5.0], [8.0, 9.0]]
    assert D.remap(1.0, parts) == 1.0 and D.remap(3.5, parts) == 2.5
    assert D.remap(2.5, parts) == 2.0                                      # inside a cut pause: the next part
    assert D.remap(8.5, parts) == 4.5 and D.remap(20, parts) == 5.0


def test_a_mood_shot_is_the_best_tagged_one_not_used_yet(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = str(tmp_path / "src.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30:duration=6",
                    "-c:v", "libx264", "-preset", "ultrafast", src], check=True)
    hits = [{"id": 1, "tags": "subway, train, man", "duration": 6, "pageURL": "p1",
             "videos": {"medium": {"url": "u1", "width": 1920}}},
            {"id": 2, "tags": "boxer, training, gym, dark", "duration": 6, "pageURL": "p2",
             "videos": {"medium": {"url": "u2", "width": 1920}}},
            {"id": 3, "tags": "boxer, gym", "duration": 6, "pageURL": "p3", "videos": {"small": {"url": "u3", "width": 960}}}]

    class Answer:
        def raise_for_status(self):
            pass

        def json(self):
            return {"hits": hits}
    fetched = []

    def fetch(url, dest):
        fetched.append(url)
        shutil.copy(src, dest)
    got = D.stock_clip("boxer training dark gym", set(), str(tmp_path / "w"), api_key="k", get=lambda *a, **k: Answer(),
                       fetch=fetch)
    assert got["stock"] == "pixabay:2" and fetched == ["u2"] and got["niveau"] == "ambiance"
    assert abs(D.duration(got["extraits"][0]["path"]) - 2.3) < 0.2
    again = D.stock_clip("boxer training dark gym", {"pixabay:2"}, str(tmp_path / "w"), api_key="k",
                         get=lambda *a, **k: Answer(), fetch=fetch)
    assert again["stock"] == "pixabay:1"                  # the used one skipped; the 960-px one never taken
    assert D.stock_clip("x", set(), str(tmp_path), api_key="") is None
    found = D.stock_search("boxer training dark gym", {"pixabay:1"}, api_key="k", get=lambda *a, **k: Answer())
    assert [c["stock"] for c in found] == ["pixabay:2"] and found[0]["src"] == "u2" and found[0]["page"] == "p2"


def test_the_speaker_comes_first():
    plan = D.shots([(0.1, ["a.mp4"]), (5.0, ["b.mp4"])], [i * 0.5 for i in range(40)], 20.0, drop=10.0)
    assert plan[0][0] == D.HOOK_S


def test_cut_aways_end_on_words_and_quicken_after_the_rise():
    starts = [i * 0.5 for i in range(40)]
    plan = D.shots([(3.0, ["a.mp4", "b.mp4"]), (8.0, ["c.mp4"]), (12.0, ["d.mp4"])], starts, 20.0, drop=10.0)
    assert plan[0][:3] == (3.0, 4.5, "a.mp4")                              # 1.9 s at most, ended on a word
    assert plan[1][:3] == (4.5, 6.0, "b.mp4")                              # its second extract right after
    crowded = D.shots([(3.0, ["a.mp4", "b.mp4"]), (3.2, ["c.mp4"])], starts, 20.0, drop=10.0)
    assert [x[2] for x in crowded] == ["a.mp4", "c.mp4"] and crowded[1][0] == 4.0     # two at once: one after the other
    assert [x[2] for x in plan].count("d.mp4") == 2                        # after the rise: two quick plans
    assert all(e - s >= 0.5 for s, e, _, _ in plan)
    assert all(plan[i][1] <= plan[i + 1][0] + 1e-6 for i in range(len(plan) - 1))


def test_captions_are_translated_on_the_speakers_timing():
    local = WORDS[:9]
    groups = D.phrases_of(local)
    assert groups[0] == (0, 5)                     # « Forty years ago, I met him. »: a comma cuts after 4 words only
    tr = {"phrases": [{"i0": a, "i1": b, "fr": f"phrase {k} en français"} for k, (a, b) in enumerate(groups)]}
    parts = [[0.0, 2.0], [2.5, 10.0]]
    words = D.caption_words(local, parts, tr, "fr", "en")
    assert words[0][0] == "phrase" and words[0][1] == 0.0
    end = D.remap(local[groups[0][1]][2], parts)
    first = [w for w in words if w[1] < end]
    assert len(first) == 4 and first[-1][2] <= end
    own = D.caption_words(local, parts, tr, "en", "en")
    assert [w[0] for w in own] == [w[0] for w in local] and own[5][1] == D.remap(local[5][1], parts)
    assert D.spread("", 0, 1) == []


def test_translation_and_youtube_texts_for_every_language():
    local = WORDS[:9]
    n = len(D.phrases_of(local))
    g = FakeGemini({"phrases": [{"n": k + 1, "fr": f"fr {k}", "ar": f"ar {k}"} for k in range(n)],
                    "langues": {"fr": {"mots_forts": ["Jeune", "affamé"], "youtube": {"titre": "Freeman 🔥", "tags": ["x"]}},
                                "ar": {"mots_forts": [], "youtube": {}}}})
    r = D.translate(local, "en", ["fr", "ar"], "Morgan Freeman", gemini=g)
    assert [x["fr"] for x in r["phrases"]] == [f"fr {k}" for k in range(n)]
    assert r["langues"]["fr"]["mots_forts"] == ["jeune", "affamé"]
    assert r["langues"]["fr"]["youtube"]["description"].endswith("#shorts")
    assert r["langues"]["ar"]["youtube"]["titre"] == "Morgan Freeman"
    mine = D.translate(local, "fr", ["fr"], gemini=FakeGemini({"phrases": [], "langues": {}}))
    assert mine["phrases"][0]["fr"] == "Forty years ago, I met him."       # his own language: his own words


def test_moments_are_on_said_words_and_films_follow_the_channel():
    g = FakeGemini({"moments": [{"mot": "Denzel", "temps": 9.5, "scene": "Denzel souriant", "recherches": ["Denzel smile"]},
                                {"mot": "young", "temps": 4.2, "scene": "Denzel jeune", "recherches": ["young Denzel"]},
                                {"mot": "award", "temps": 8.6, "scene": "le trophée", "recherches": ["AFI award"]},
                                {"mot": "inconnu", "temps": 3, "scene": "?", "recherches": ["x"]}],
                    "mots_forts": ["Wings", "great."], "mot_fort": {"mot": "wings", "temps": 24.6}})
    r = D.moments(WORDS, 30.0, films=False, gemini=g)
    # « award » 0.5 s before « Denzel »: too close, the second one dropped
    assert [(m["mot"], m["temps"]) for m in r["moments"]] == [("young,", 4.0), ("award,", 8.5)]
    assert r["mots_forts"] == ["wings", "great"] and r["mot_fort"]["mot"] == "wings."
    assert "JAMAIS d'extrait de film de fiction" in g.prompts[0] and "emission TV" in g.prompts[0]
    D.moments(WORDS, 30.0, films=True, gemini=g)
    assert "Wonka" in g.prompts[-1]


def test_a_clip_is_watched_and_a_film_refused_unless_allowed(tmp_path):
    item = {"mot": "Denzel", "scene": "Denzel souriant", "recherches": ["q1", "q2"]}
    found = {"q1": [{"url": "https://www.youtube.com/watch?v=AAAAAAAAAAA", "title": "Film clip", "duration": 120},
                    {"url": "https://www.youtube.com/watch?v=BBBBBBBBBBB", "title": "Interview", "duration": 300}],
             "q2": [{"url": "https://youtu.be/AAAAAAAAAAA", "title": "Film clip", "duration": 120}]}
    verdicts = {"AAAAAAAAAAA": {"film": True, "fiction": True, "par_scene": {"0": {"niveau": "exacte", "moments": [{"debut": 3}]}}},
                "BBBBBBBBBBB": {"film": False, "par_scene": {"0": {"niveau": "equivalente", "moments": [{"debut": 10.26},
                                                                                                      {"debut": 40}]}}}}
    watched = []

    def checker(url, scene, phrase):
        watched.append(url[-11:])
        return verdicts[url[-11:]]

    def download(url, a, name):
        path = str(tmp_path / f"{name}.mp4")
        open(path, "wb").write(b"x")
        return path
    log = []
    got = D.find_clip(item, False, set(), str(tmp_path), log=log, checker=checker, search=lambda q: found[q],
                      download=download)
    assert watched == ["AAAAAAAAAAA", "BBBBBBBBBBB"]                       # the same video twice: watched once
    assert got["url"].endswith("BBBBBBBBBBB") and [x["debut"] for x in got["extraits"]] == [10.3, 40.0]
    assert "pas autorisé" in log[0]
    allowed = D.find_clip(item, True, set(), str(tmp_path), checker=checker, search=lambda q: found[q], download=download)
    assert allowed["film"] is True and allowed["url"].endswith("AAAAAAAAAAA")
    assert D.find_clip(item, True, {"youtube:AAAAAAAAAAA", "youtube:BBBBBBBBBBB"}, str(tmp_path), checker=checker,
                       search=lambda q: found[q], download=download) is None
    # a ceremony is a TV show (« film » for the Adaptation) but not fiction: allowed without films
    verdicts["AAAAAAAAAAA"]["fiction"] = False
    assert D.find_clip(item, False, set(), str(tmp_path), checker=checker, search=lambda q: found[q],
                       download=download)["url"].endswith("AAAAAAAAAAA")


def test_two_videos_watched_per_moment_at_most(tmp_path):
    many = [{"url": f"https://www.youtube.com/watch?v={c * 11}", "title": c, "duration": 60} for c in "ABCDE"]
    watched = []

    def checker(url, scene, phrase):
        watched.append(url[-1])
        return {"par_scene": {"0": {"niveau": "rien"}}}
    assert D.find_clip({"mot": "x", "scene": "y", "recherches": ["q"]}, False, {"youtube:" + "A" * 11}, str(tmp_path),
                       checker=checker, search=lambda q: many) is None
    assert watched == ["B", "C"]                                           # an already used one is not counted


def test_the_strict_check_keeps_the_logos_left_on_screen():
    from adaptation import finder
    assert finder.LOGO_LINE in finder.CHECK_PROMPT
    assert finder.strict_faults("logo TV (coin) : BFM, logo TV (centre) : CNN") == "logo TV (centre) : CNN"
    assert finder.real_faults("logo TV (centre) : CNN") == ""
    assert '"fiction"' in finder.FICTION_LINE and "ceremonie" in finder.FICTION_LINE


def test_the_frame_is_centred_and_sized():
    assert D.frame_box(D.DEFAULTS) == (87, 507, 906, 906)
    x, y, w, h = D.frame_box(D.clean_settings({"cadre": "4:5", "taille": 100}))
    assert (w, h) == (1080, 1350) and y == (1920 - 1350) // 2
    assert D.frame_box(D.clean_settings({"cadre": "16:9"}))[3] == 510


def _synthetic(tmp_path, name, size, seconds, tone=True):
    path = str(tmp_path / name)
    audio = ["-f", "lavfi", "-i", f"sine=frequency=300:duration={seconds}"] if tone else []
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30:duration={seconds}",
                    *audio, "-c:v", "libx264", "-preset", "ultrafast", *(["-c:a", "aac"] if tone else []), "-shortest", path],
                   check=True)
    return path


def test_a_real_render_with_cut_aways_translated_captions_and_music(tmp_path):
    pic = _synthetic(tmp_path, "orateur.mp4", "1280x720", 4)
    speech = str(tmp_path / "parole.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", pic, "-vn", speech], check=True)
    clip = _synthetic(tmp_path, "plan.mp4", "640x360", 2, tone=False)
    bed = str(tmp_path / "fond.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=500:duration=4", bed], check=True)
    words = D.spread("quand ils ont créé ce prix il attendait", 0.2, 3.6)
    s = D.clean_settings({"cadre": "4:5", "fond": "flou", "ombre": True, "identite": True, "sous_titres": "editorial"})
    out = D.render(pic, speech, [(1.0, 2.2, clip, 0.0)], words, "fr", s, bed, str(tmp_path / "court.mp4"),
                   str(tmp_path / "travail"), strong={"prix"}, signature="C'est pour ça : 100%")
    assert D.size_of(out) == (1080, 1920) and abs(D.duration(out) - 4.0) < 0.2
    ass = open(tmp_path / "travail" / "sous_titres" / "cap.ass", encoding="utf-8").read()
    assert "attendait" in ass
    ar = D.render(pic, speech, [], D.spread("قبل أربعين سنة", 0.2, 3.0), "ar", D.clean_settings({"fond": "degrade"}), None,
                  str(tmp_path / "ar.mp4"), str(tmp_path / "travail_ar"))
    assert abs(D.duration(ar) - 4.0) < 0.2


# ---------------------------------------------------------------- a project, from the link to Publication

@pytest.fixture
def fakes(monkeypatch, tmp_path):
    calls = {"renders": [], "beds": [], "found": 0, "passages": 0}
    from adaptation import sources
    from roblox import voix

    def download(url, d, name, sections=None):
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, name + ".mp4")
        open(path, "wb").write(b"x")
        return path
    monkeypatch.setattr(sources, "download", download)
    monkeypatch.setattr(sources, "source_meta", lambda path: {"title": "Morgan Freeman honors Denzel"})
    monkeypatch.setattr(D, "transcribe", lambda video: (WORDS, "en"))

    def passages(words, target, n=3, title="", avoid=None, gemini=None):
        calls["passages"] += 1
        if avoid:
            return {"orateur": "", "passages": [{"i0": 20, "i1": 39, "debut": 9.85, "fin": 19.9, "titre": "Merci",
                                                 "pourquoi": "", "note": 6}]}
        return {"orateur": "Morgan Freeman", "passages": [{"i0": 0, "i1": 18, "debut": 0.0, "fin": 9.65,
                                                           "titre": "L'hommage", "pourquoi": "fort", "note": 9}]}
    monkeypatch.setattr(D, "passages", passages)
    monkeypatch.setattr(D, "cut_passage", lambda src, a, b, out: open(out, "wb").write(b"x") and out)
    monkeypatch.setattr(D, "duration", lambda path: 9.4)
    monkeypatch.setattr(voix, "separate", lambda src, work: {"voix": "v.wav", "reste": "r.wav"})
    monkeypatch.setattr(D, "tightened", lambda vocals, total: [[0.0, 4.0], [4.6, 9.4]])

    def cut(seg, parts, pic, snd):
        open(pic, "wb").write(b"x")
        open(snd, "wb").write(b"x")
        return pic, snd
    monkeypatch.setattr(D, "cut", cut)
    monkeypatch.setattr(D, "moments", lambda local, speech, films, density="normale", speaker="": {
        "moments": [{"mot": "award,", "temps": 7.0, "scene": "trophée", "recherches": ["afi award"], "type": "precis",
                     "ambiance": "golden trophy"},
                    {"mot": "Denzel", "temps": 7.5, "scene": "Denzel", "recherches": ["denzel"], "type": "precis",
                     "ambiance": "man walking alone night"},
                    {"mot": "great.", "temps": 5.0, "scene": "la grandeur", "recherches": ["x"], "type": "ambiance",
                     "ambiance": "mountain summit sunrise"}],
        "mots_forts": ["award"], "mot_fort": {"mot": "great.", "temps": 6.5}})
    calls["films"] = []

    def find_clip(item, films, used, work, exclude="", log=None, **kw):
        calls["found"] += 1
        calls["films"].append(films)
        if item["mot"] == "Denzel":
            log.append("✗ rien")
            return None
        path = os.path.join(work, "trophee.mp4")
        open(path, "wb").write(b"x")
        return {"url": "https://www.youtube.com/watch?v=CCCCCCCCCCC", "titre": "AFI", "niveau": "exacte", "film": False,
                "extraits": [{"path": path, "debut": 2.0}]}
    monkeypatch.setattr(D, "find_clip", find_clip)
    calls["stock"] = []

    def stock_clip(query, used, work, **kw):
        calls["stock"].append((query, sorted(used)))
        if query == "golden trophy":
            return None
        path = os.path.join(work, f"pixabay_{len(calls['stock'])}.mp4")
        open(path, "wb").write(b"x")
        return {"url": "https://pixabay.com/x", "titre": query, "niveau": "ambiance", "film": False,
                "stock": f"pixabay:{len(calls['stock'])}", "extraits": [{"path": path, "debut": 0.0}]}
    monkeypatch.setattr(D, "stock_clip", stock_clip)

    def translate(local, source, codes, speaker="", gemini=None):
        rows = [{"i0": a, "i1": b, **{c: f"{c} {k}" for c in codes}} for k, (a, b) in enumerate(D.phrases_of(local))]
        return {"phrases": rows, "langues": {c: {"mots_forts": [f"{c} 1"], "youtube": {
            "titre": f"Freeman ({c}) 🔥", "description": "Un hommage. #shorts", "tags": ["freeman"]}} for c in codes}}
    monkeypatch.setattr(D, "translate", translate)

    def render(pic, speech, plan, words, lang, settings, bed, out, work, strong=None, channel=None, signature=""):
        calls["renders"].append({"lang": lang, "plans": len(plan), "first": words[0][0], "bed": bed and os.path.basename(bed),
                                 "cadre": settings["cadre"], "fond": settings["fond"], "strong": strong})
        open(out, "wb").write(b"x")
        return out
    monkeypatch.setattr(D, "render", render)

    def song_bed(song, hit, total, out, gap, on_rise=True):
        calls["beds"].append((os.path.basename(song), round(hit, 2), gap))
        open(out, "wb").write(b"x")
        return out
    monkeypatch.setattr(D, "song_bed", song_bed)
    monkeypatch.setattr(D, "thumbnail", lambda video, at, out: None)
    monkeypatch.setattr(musique, "plan", lambda d, sujet, ton, parts, total: {
        "fichier": "past.mp3", "titre": "Past Lives", "montee": 47.4, "partie": 1, "a": 5.0, "comment": "ok"})
    monkeypatch.setattr(musique, "listen", lambda path: {"moment_fort": 47.4, "montees": [47.4], "duree": 150.0})
    monkeypatch.setattr(musique, "placed_bed", lambda d, c, total, out, gap=musique.GAP:
                        song_bed(c["fichier"], c["a"], total, out, gap))
    monkeypatch.setattr(ap, "project_dir", lambda pid: str(tmp_path / pid))
    monkeypatch.chdir(tmp_path)
    os.makedirs("assets/musiques")
    open("assets/musiques/choisie.mp3", "wb").write(b"x")
    music = tmp_path / "music"
    music.mkdir()
    (music / "piste.mp3").write_bytes(b"x")
    calls["channels"] = [
        {"channel": "cestpourca", "profile": {"language_hint": "fr", "display_name": "C'est pour ça",
                                              "discours": {"fond": "flou", "films": True}}, "music_dir": str(music)},
        {"channel": "lihadha_alsabab", "profile": {"language_hint": "ar", "adaptation": {"music_file": "piste.mp3"},
                                                   "discours": {"cadre": "4:5"}}, "music_dir": str(music)}]
    return calls


def test_a_discours_from_the_link_to_publication(fakes):
    p = ap.create("https://www.youtube.com/watch?v=XIGWjzqKTp0", [], fakes["channels"], mode="discours",
                  son="intelligente", duree=30)
    pid = p["project_id"]
    assert p["mode"] == "discours" and p["discours"]["duree"] == 30
    assert [t["discours"]["films"] for t in p["targets"]] == [True, False]    # no voice needed: the speaker's own
    ap.runner_for(pid, "analysing")(pid)
    p = ap.load(pid)
    assert p["status"] == "passage_review" and p["discours"]["orateur"] == "Morgan Freeman"
    assert p["discours"]["choix"]["i1"] == 18

    dp.more_passages(pid)
    assert len(ap.load(pid)["discours"]["passages"]) == 2
    dp.choose_passage(pid, 0, i0=1, i1=17, orateur="Morgan  Freeman")
    with pytest.raises(ap.PipelineError):
        dp.choose_passage(pid, 0, i0=10, i1=12)                              # too short
    c = ap.load(pid)["discours"]["choix"]
    assert (c["i0"], c["i1"]) == (1, 17) and c["debut"] == WORDS[1][1] - 0.15
    dp.approve_passage(pid)
    ap.runner_for(pid, "searching")(pid)
    p = ap.load(pid)
    assert p["status"] == "plans_review", p.get("error")
    assert fakes["films"] == [False, False]           # one channel refuses films: the whole project does
    # « Denzel »: nothing on YouTube -> a mood shot; « great. » (an idea): straight to Pixabay, never watched
    assert [(m["action"], (m["clip"] or {}).get("niveau")) for m in p["discours"]["moments"]] == [
        ("garder", "exacte"), ("garder", "ambiance"), ("garder", "ambiance")]
    assert [q for q, _ in fakes["stock"]] == ["man walking alone night", "mountain summit sunrise"]
    assert fakes["stock"][1][1] == ["pixabay:1"]                            # never the same shot twice
    assert p["discours"]["local"][0] == ["years", 0.15, 0.55]
    dp.set_moment(pid, 2, "retirer")
    dp.link_moment(pid, 1, "https://www.youtube.com/watch?v=DDDDDDDDDDD", 12.5)
    assert ap.load(pid)["discours"]["moments"][1]["clip"]["a_la_main"] is True

    dp.approve_plans(pid)
    ap.runner_for(pid, "voicing")(pid)
    p = ap.load(pid)
    assert p["status"] == "preview_review", p.get("error")
    fr, ar = fakes["renders"]
    assert fr["lang"] == "fr" and fr["first"] == "fr" and fr["fond"] == "flou" and fr["cadre"] == "carre"
    assert ar["lang"] == "ar" and ar["cadre"] == "4:5" and ar["strong"] == {"ar 1"}
    assert fr["plans"] >= 2
    hit = D.remap(6.5, [[0.0, 4.0], [4.6, 9.4]])                           # the punchline, on the cut timeline
    assert fakes["beds"] == [("past.mp3", round(hit, 2), 7.0)] * 2            # smart music on every channel here

    dp.change_settings(pid, {"cadre": "16:9", "volume_db": 12}, son="choisie", chanson="choisie.mp3")
    p = ap.load(pid)
    assert p["status"] == "voicing" and p["discours"]["reglages"] == {"cadre": "16:9", "volume_db": 12.0}
    ap.runner_for(pid, "voicing")(pid)
    assert [r["cadre"] for r in fakes["renders"][-2:]] == ["16:9", "16:9"]
    assert fakes["beds"][-1] == ("choisie.mp3", round(hit, 2), 12.0)
    with pytest.raises(ap.PipelineError):
        ap.change_voice(pid, "cestpourca", "x")                              # the speaker's voice: nothing to change

    ap.validate_preview(pid, "cestpourca")
    ap.start_render(pid)
    ap.runner_for(pid, "rendering")(pid)
    p = ap.load(pid)
    assert p["status"] == "preview_review"                                    # the Arabic one still waits
    rec = db.get_video(f"cestpourca_{pid}")
    assert rec["original_title"] == "Freeman (fr) 🔥" and rec["recette"]["mode"] == "discours"
    assert rec["recette"]["son"] == "choisie" and rec["recette"]["musique"] == "choisie.mp3"
    assert rec["recette"]["orateur"] == "Morgan Freeman" and "Morgan Freeman" in rec["ai_data"]["description"]
    assert db.broll_last_used("cestpourca") == {}         # the mood shot was taken out: nothing remembered


def test_the_shots_can_be_chosen_searched_and_moved(fakes, monkeypatch, client):
    p = ap.create("https://www.youtube.com/watch?v=XIGWjzqKTp0", [], fakes["channels"][:1], mode="discours")
    pid = p["project_id"]
    ap.runner_for(pid, "analysing")(pid)
    dp.approve_passage(pid)
    ap.runner_for(pid, "searching")(pid)
    props = [{"stock": f"pixabay:{n}", "tags": f"tag {n}", "page": "p", "image": "i", "apercu": "a", "src": "s",
              "duree": 6.0} for n in (7, 8, 9)]
    seen = []
    monkeypatch.setattr(D, "stock_search", lambda q, used, **kw: seen.append((q, sorted(used))) or props)

    def stock_take(cand, query, work, fetch=None):
        path = os.path.join(work, f"{cand['stock'][7:]}.mp4")
        open(path, "wb").write(b"x")
        return {"url": "p", "titre": cand["tags"], "niveau": "ambiance", "film": False, "stock": cand["stock"],
                "recherche": query, "extraits": [{"path": path, "debut": 0.0}]}
    monkeypatch.setattr(D, "stock_take", stock_take)
    r = client.post(f"/api/adaptations/{pid}/discours/moments/0/pixabay", json={"recherche": "boxer alone dark gym"})
    assert r.status_code == 200, r.text
    assert seen[0][0] == "boxer alone dark gym" and "pixabay:1" in seen[0][1]      # the shots already taken left out
    m = r.json()["discours"]["moments"][0]
    assert m["ambiance"] == "boxer alone dark gym" and [c["stock"] for c in m["propositions"]] == [c["stock"] for c in props]
    assert m["clip"]["niveau"] == "exacte"                                          # a search alone changes no shot
    r = client.post(f"/api/adaptations/{pid}/discours/moments/0/pixabay", json={"stock": "pixabay:8"})
    m = r.json()["discours"]["moments"][0]
    assert m["clip"]["stock"] == "pixabay:8" and m["action"] == "garder" and m["propositions"][1]["pris"] == 0
    assert client.post(f"/api/adaptations/{pid}/discours/moments/0/pixabay", json={"stock": "pixabay:99"}).status_code == 400

    d = ap.load(pid)["discours"]
    r = client.post(f"/api/adaptations/{pid}/discours/moments/0/move", json={"mot": len(d["local"]) - 1})
    s = r.json()["discours"]
    times = [m["temps"] for m in s["moments"]]
    assert times == sorted(times) and s["moments"][-1]["mot"] == d["local"][-1][0]   # still in the speech's order
    assert s["moments"][-1]["clip"]["stock"] == "pixabay:8" and s["moments"][-1]["mot_i"] == len(d["local"]) - 1
    assert client.post(f"/api/adaptations/{pid}/discours/moments/0/move", json={"mot": 999}).status_code == 400
    f = s["frise"]
    assert f["total"] > 0 and len(f["mots"]) == len(d["local"]) and f["plans"]
    assert all(b["debut"] >= D.HOOK_S and b["fin"] <= f["total"] for b in f["plans"])
    dp.set_moment(pid, 1, "retirer")
    f = dp.frise(ap.load(pid))
    assert 1 in [x["index"] for x in f["retires"]] and 1 not in [b["index"] for b in f["plans"]]


def test_a_used_mood_shot_is_remembered_per_channel(fakes):
    p = ap.create("https://www.youtube.com/watch?v=XIGWjzqKTp0", [], fakes["channels"][:1], mode="discours")
    pid = p["project_id"]
    for step in ("analysing",):
        ap.runner_for(pid, step)(pid)
    dp.approve_passage(pid)
    ap.runner_for(pid, "searching")(pid)
    dp.approve_plans(pid)
    ap.runner_for(pid, "voicing")(pid)
    ap.validate_preview(pid, "cestpourca")
    ap.start_render(pid)
    ap.runner_for(pid, "rendering")(pid)
    assert set(db.broll_last_used("cestpourca")) == {"pixabay:1", "pixabay:2"}
    p2 = ap.create("https://www.youtube.com/watch?v=other", [], fakes["channels"][:1], mode="discours")
    assert {"pixabay:1", "pixabay:2"} <= dp.stock_used_by(p2)


def test_a_discours_sound_falls_back_and_unknown_choices_are_refused(fakes):
    with pytest.raises(ap.PipelineError):
        ap.create("https://youtu.be/x", [], fakes["channels"], mode="discours", son="choisie", chanson="absente.mp3")
    p = ap.create("https://youtu.be/x", [], fakes["channels"], mode="discours", son="notre_musique")
    assert [dp.son_for(p, t) for t in p["targets"]] == ["sans_musique", "notre_musique"]
    with pytest.raises(ap.PipelineError):
        ap.create("", [], fakes["channels"], mode="discours")


def test_the_screen_gets_the_discours(fakes, client):
    from webapp import adaptation_routes as routes
    p = ap.create("https://www.youtube.com/watch?v=XIGWjzqKTp0", [], fakes["channels"], mode="discours")
    pid = p["project_id"]
    ap.runner_for(pid, "analysing")(pid)
    s = routes._serialize_adaptation(ap.load(pid))
    d = s["discours"]
    assert s["mode"] == "discours" and d["orateur"] == "Morgan Freeman" and d["films"] is False
    assert d["passages"][0]["texte"].startswith("Forty years ago,") and d["choix"]["autour"]["debut"] == 0
    assert s["targets"][0]["reglages"]["fond"] == "flou" and s["targets"][0]["films"] is True
    assert routes._serialize_adaptation(ap.load(pid), full=False)["discours"].get("passages") is None
    assert client.get(f"/api/adaptations/{pid}/discours/moments/0/clip").status_code == 404


def test_a_channels_discours_settings(client, project):
    project.add_channel("chanD")
    name = "chanD"
    d = client.get(f"/api/channels/{name}/discours").json()
    assert d["reglages"]["films"] is False and "escalier" in [s["id"] for s in d["styles"]]
    assert "karaoke" not in [s["id"] for s in d["styles"]]
    d = client.put(f"/api/channels/{name}/discours", json={"films": True, "fond": "degrade", "taille": 999}).json()
    assert d["reglages"]["films"] is True and d["reglages"]["fond"] == "degrade" and d["reglages"]["taille"] == 100
    d = client.put(f"/api/channels/{name}/discours", json={"cadre": "4:5"}).json()
    assert d["reglages"]["fond"] == "degrade" and d["reglages"]["cadre"] == "4:5"     # kept, not reset


def test_the_new_ai_steps_are_in_the_model_table():
    import ai_models
    for step in ("discours.passages", "discours.moments", "discours.translate"):
        assert step in ai_models.STEPS and step in ai_models.TEXT_ONLY


def test_the_page_loads_the_discours_screens(client):
    page = client.get("/").text
    assert "/static/js/discours.js" in page and page.index("reprise.js") < page.index("discours.js")
    assert 'data-idx="17"' in page and 'id="dsChannels"' in page and "Réglages · 8 sur 11" in page
    js = client.get("/static/js/discours.js").text
    assert "function renderDiscours" in js and "discours/passage/approve" in js and "function loadDiscoursSettings" in js
    core = client.get("/static/js/core.js").text
    assert "settings: [0, 1, 11, 12, 13, 14, 16, 17, 15, 8, 9]" in core
