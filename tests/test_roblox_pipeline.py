"""Montage Roblox, a project: created, analysed (the long video read, its moments found, the texts written), the
texts corrected, every Short made, the chosen ones sent to Publication. YouTube, Gemini and ffmpeg are faked."""

import json
import os

import pytest

import db
from roblox import pipeline as rp
from roblox import identite, nettoyage, plan, render, sources, moments, voix

T = {"fr": "Bonjour", "en": "Hello"}
PUB = {"fr": {"titre": "Le pire petit déjeuner 🤢", "description": "Il goûte.", "tags": ["roblox", "brookhaven"]},
       "en": {"titre": "The worst breakfast 🤢", "description": "He tastes it.", "tags": ["roblox"]}}


@pytest.fixture
def fakes(project, monkeypatch):
    calls = {"render": [], "translate": 0, "ctx": []}
    monkeypatch.setattr(sources, "info", lambda url, work: {"titre": "FUNNY MOMENTS", "chaine": "Roblox Idol", "duree": 7200.0,
                                                           "langue": "en", "vues": 10, "heatmap": [], "chapitres": [], "sous_titres": None})
    monkeypatch.setattr(sources, "windows", lambda meta: [[0.0, 75.0], [600.0, 675.0]])

    def download(url, work, wins):
        os.makedirs(work, exist_ok=True)
        path = os.path.join(work, f"w{int(wins[0][0])}.mp4")
        open(path, "w").write("x")
        return [path]
    monkeypatch.setattr(sources, "download", download)
    monkeypatch.setattr(rp, "render_duration", lambda path: 75.0)
    monkeypatch.setattr(moments, "find", lambda path, dur: [{"debut": 10.0, "fin": 22.0, "chute": 18.0, "resume": "r"}])

    def write(meta, cat, styles, langs):
        assert [m["id"] for m in cat] == ["w0#0", "w600#0"] and cat[1]["t0"] == 600.0
        return ({"clip": {"moment": "w0#0", "titre": dict(T), "publication": json.loads(json.dumps(PUB))},
                 "devine": {"moment": "w600#0", "arret": 7.0, "question": dict(T), "final": dict(T), "publication": json.loads(json.dumps(PUB))}},
                ["POV : pas de moment qui convienne dans cette vidéo."])
    monkeypatch.setattr(plan, "write", write)

    def make(style, p, ctx, out, music=None):
        calls["ctx"].append((style, ctx.lang, ctx))
        calls["render"].append((style, ctx.lang, ctx.voice_id, music, dict(p.get("titre") or p.get("question") or {})))
        open(out, "wb").write(b"\x00")
        return 9.0
    monkeypatch.setattr(render, "make", make)
    monkeypatch.setattr(rp, "_thumbnail", lambda v: None)

    def separate(src, work):
        calls["separe"].append(src)
        return {"voix": src + ".voix.wav", "reste": src + ".reste.wav"}

    def write_lines(vocals, a, b, resume, dialogue, langs, gemini=None, joueurs=None, video=""):
        assert video == "FUNNY MOMENTS (Roblox Idol)"
        calls["repliques"].append((vocals, a, b, dict(joueurs or {})))
        return [{"a": a + 1.0, "qui": "1", "nom": "Sunny" if "w600" in vocals else "", **{l: f"[laughs] {l} {a}" for l in langs}}] + \
            ([{"a": a + 3.0, "qui": "2", "nom": "", **{l: f"{l} melon" for l in langs}}] if "w600" in vocals else [])
    def track(lines, lang, voice_id, a, b, work, ref_db):
        calls["lues"].append((lang, voice_id, [l["texte"] for l in lines]))
        calls["voix_par_ligne"].append((lang, [(l["texte"], l.get("voice")) for l in lines]))
        name = f"{work}/{lang}_{a}_{abs(hash(tuple(l['texte'] for l in lines)))}.wav"            # named after its text, as the real one
        return name, [{"a": l["a"], "b": l["a"] + 1, "texte": l["texte"]} for l in lines]

    def passage_audio(src, reste, voices, out):
        calls["passages"].append((src, reste, voices))
        open(out, "w").write("x")
        return out
    calls.update(separe=[], repliques=[], lues=[], passages=[], voix_par_ligne=[])
    monkeypatch.setattr(voix, "track", track)
    monkeypatch.setattr(voix, "passage_audio", passage_audio)
    monkeypatch.setattr(voix, "mean_db", lambda path, a=None, b=None: -20.0)

    def detect(src, a, b, gemini=None):
        calls["vus"].append((src, a, b))
        return [{"type": "avatar", "debut": a + 1, "fin": a + 2, "cadre": [0.6, 0.4, 1.0, 1.0], "pose": "rire"}]

    def clean(src, elements, spans, out, work, reader=None, predictor=None):
        calls["nettoyes"].append((src, len(elements), spans))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, "w").write("x")
        return {"fichier": out, "keep": 0.8, "pseudos": []}
    calls.update(vus=[], nettoyes=[])
    monkeypatch.setattr(identite, "detect", detect)
    monkeypatch.setattr(nettoyage, "clean", clean)
    monkeypatch.setattr(voix, "separate", separate)
    monkeypatch.setattr(voix, "write_lines", write_lines)
    return calls


def new(project, music="original"):
    project.add_channel("chanA")
    project.add_channel("chanB")
    return rp.create("https://www.youtube.com/watch?v=NvGUWTH2U5Q", ["clip", "pov", "devine"],
                     [{"langue": "fr", "channel": "chanA", "profile": {"language_hint": "fr"}, "music_dir": "x"},
                      {"langue": "en", "channel": "chanB", "profile": {"language_hint": "en"}, "music_dir": "x"}], music)


def test_a_project_needs_a_link_a_style_and_one_channel_per_language(project):
    ok = [{"langue": "fr", "channel": "chanA", "profile": {}, "music_dir": "x"}]
    for url, styles, targets, err in (("pas un lien", ["clip"], ok, "lien"), ("https://y", [], ok, "style"),
                                      ("https://y", ["clip"], ok * 2, "langue"), ("https://y", ["clip"], [], "langue")):
        with pytest.raises(rp.PipelineError, match=err):
            rp.create(url, styles, targets)
    with pytest.raises(rp.PipelineError, match="musique"):
        rp.create("https://y", ["clip"], ok, "chaine")                     # no track chosen for the channel


def test_each_language_gets_the_voice_chosen_and_the_players_voice_can_be_kept(project):
    project.add_channel("chanA")
    project.add_channel("chanB")
    anatole = voix.catalogue("fr")[1]["voice_id"]
    t = [{"langue": "fr", "channel": "chanA", "profile": {}, "music_dir": "x", "voice_id": anatole},
         {"langue": "en", "channel": "chanB", "profile": {}, "music_dir": "x"}]
    t[1]["voix_2"] = voix.catalogue("en")[2]["voice_id"]
    p = rp.create("https://y", ["clip"], t, voix_joueur="originale")
    assert [x["voice_id"] for x in p["targets"]] == [anatole, voix.DEFAULTS["en"]] and p["voix_joueur"] == "originale"
    assert p["targets"][0]["voix_joueurs"] == {"1": anatole, "2": voix.DEFAULTS["fr"]}      # Anatole taken: Donny for the 2nd
    assert p["targets"][1]["voix_joueurs"] == {"1": voix.DEFAULTS["en"], "2": voix.catalogue("en")[2]["voice_id"]}
    with pytest.raises(rp.PipelineError, match="voix"):
        rp.create("https://y", ["clip"], [{**t[1], "voice_id": anatole}])          # a French voice for English
    with pytest.raises(rp.PipelineError, match="voix du joueur"):
        rp.create("https://y", ["clip"], t, voix_joueur="muette")


def test_the_analysis_finds_the_moments_and_writes_the_texts(fakes, project):
    p = new(project)
    assert p["status"] == "analysing" and p["styles"] == ["clip", "pov", "devine"]
    assert {t["langue"]: t["voice_id"] for t in p["targets"]} == {"fr": voix.DEFAULTS["fr"], "en": voix.DEFAULTS["en"]}
    assert p["voix_joueur"] == "remplacer"                                     # no choice made: Donny, Tyler, voice replaced
    rp.run_analysis(p["project_id"])
    p = rp.load(p["project_id"])
    assert p["status"] == "plan_review" and set(p["plan"]) == {"clip", "devine"}
    assert p["absents"] == ["POV : pas de moment qui convienne dans cette vidéo."]
    assert p["meta"]["chaine"] == "Roblox Idol" and len(p["catalogue"]) == 2


def test_the_players_voice_is_separated_and_his_lines_written_once_per_moment(fakes, project):
    p = new(project)
    rp.run_analysis(p["project_id"])
    p = rp.load(p["project_id"])
    assert sorted(fakes["separe"]) == sorted({m["fichier"] for m in p["catalogue"]})       # each passage used, once
    r = p["voix"]["repliques"]
    assert set(r) == {"w0#0", "w600#0"} and r["w0#0"]["a"] == 8.5 and r["w0#0"]["b"] == 23.5   # the moment, 1.5 s around
    assert r["w0#0"]["lignes"] == [{"a": 9.5, "qui": "1", "nom": "", "fr": "[laughs] fr 8.5", "en": "[laughs] en 8.5"}]
    assert p["voix"]["joueurs"] == {"1": "Sunny", "2": ""}                                # his name, heard later, kept
    assert [j for *_, j in fakes["repliques"]] == [{}, {"1": "sans pseudo, a dit « [laughs] fr 8.5 »"}]   # recognised by a line
    p2 = rp.create("https://y", ["clip"], [{"langue": "fr", "channel": "chanA", "profile": {}, "music_dir": "x"}], voix_joueur="originale")
    fakes["separe"].clear()
    rp.run_analysis(p2["project_id"])
    assert fakes["separe"] == [] and not rp.load(p2["project_id"]).get("voix")           # his voice kept: nothing to do


def test_his_lines_corrected_make_the_shorts_that_use_them_again(fakes, project):
    pid = new(project)["project_id"]
    rp.run_analysis(pid)
    rp.start_render(pid)
    rp.run_render(pid)
    p = rp.set_lines(pid, "w0#0", "fr", ["  [laughs]  Trop   fort ! "])
    assert p["voix"]["repliques"]["w0#0"]["lignes"][0] == {"a": 9.5, "qui": "1", "nom": "", "fr": "[laughs] Trop fort !",
                                                           "en": "[laughs] en 8.5"}
    assert p["videos"]["clip_fr"]["a_refaire"] and not p["videos"]["clip_en"].get("a_refaire")
    assert not p["videos"]["devine_fr"].get("a_refaire")                                  # another moment
    with pytest.raises(rp.PipelineError, match="moment"):
        rp.set_lines(pid, "nope", "fr", ["x"])


def test_his_voice_is_read_by_the_chosen_one_in_every_short(fakes, project):
    pid = new(project)["project_id"]
    rp.run_analysis(pid)
    rp.start_render(pid)
    rp.run_render(pid)
    assert ("fr", voix.DEFAULTS["fr"], ["[laughs] fr 8.5"]) in fakes["lues"] and ("en", voix.DEFAULTS["en"], ["[laughs] en 8.5"]) in fakes["lues"]
    style, lang, ctx = next(c for c in fakes["ctx"] if c[:2] == ("clip", "fr"))
    assert ctx.moments["w0#0"]["fichier"].endswith(".mp4") and "voix" in ctx.moments["w0#0"]["fichier"]
    assert ctx.lines["w0#0"][0]["texte"] == "[laughs] fr 8.5" and ctx.son_refait and ctx.voice_model == voix.MODEL
    reste = [r for _, r, _ in fakes["passages"]]
    assert all(r and r.endswith(".reste.wav") for r in reste)                     # the game's sounds kept
    copies = [o for o in os.listdir(os.path.join(rp.project_dir(pid), "voix")) if o.endswith(".mp4")]
    assert copies == []                                    # the passages remade for the render are not kept (~35 MB each)
    made = len(fakes["passages"])
    rp.set_lines(pid, "w0#0", "fr", ["Beurk !"])
    rp.start_render(pid)
    rp.run_render(pid)
    assert len(fakes["passages"]) == made + 1                                     # only the passage of the Short made again


def test_each_player_is_read_by_his_own_voice_which_can_be_changed(fakes, project):
    pid = new(project)["project_id"]
    rp.run_analysis(pid)
    rp.start_render(pid)
    rp.run_render(pid)
    fr = dict(next(v for l, v in fakes["voix_par_ligne"] if l == "fr" and len(v) == 2))
    assert fr == {"[laughs] fr 8.5": voix.default_for("fr", "1", {}), "fr melon": voix.default_for("fr", "2", {})}
    lea = next(v["voice_id"] for v in voix.catalogue("fr") if v["nom"] == "Lea")
    p = rp.set_voice(pid, "fr", "2", lea)
    assert p["targets"][0]["voix_joueurs"]["2"] == lea
    assert p["videos"]["devine_fr"]["a_refaire"] and not p["videos"]["clip_fr"].get("a_refaire")   # only where Melon speaks
    assert not p["videos"]["devine_en"].get("a_refaire")
    p = rp.set_voice(pid, "fr", "1", lea)
    assert p["targets"][0]["voice_id"] == lea and p["videos"]["clip_fr"]["a_refaire"]           # the 1st also tells the story
    with pytest.raises(rp.PipelineError, match="voix"):
        rp.set_voice(pid, "en", "1", lea)                                                     # a French voice for English


def test_the_channels_identity_hides_the_creator_once_then_every_short_is_made_on_the_clean_passages(fakes, project):
    project.add_channel("chanA")
    project.add_channel("chanB")
    t = [{"langue": "fr", "channel": "chanA", "profile": {}, "music_dir": "x"}, {"langue": "en", "channel": "chanB", "profile": {}, "music_dir": "x"}]
    p = rp.create("https://y", ["clip", "devine"], t, voix_joueur="originale", identite=True)
    assert p["identite"]
    rp.run_analysis(p["project_id"])
    p = rp.load(p["project_id"])
    assert sorted(f.rsplit("/", 1)[-1] for f, _, _ in fakes["vus"]) == ["w0.mp4", "w600.mp4"]          # each moment shown
    assert set(p["createur"]["elements"]) == {m["fichier"] for m in p["catalogue"]}
    rp.start_render(p["project_id"])
    rp.run_render(p["project_id"])
    assert len(fakes["nettoyes"]) == 2 and all(spans for _, _, spans in fakes["nettoyes"])         # once per passage, 2 languages
    style, lang, ctx = next(c for c in fakes["ctx"] if c[:2] == ("clip", "fr"))
    clean = ctx.moments["w0#0"]["fichier"]
    assert "propre" in clean and ctx.identite["keep"][clean] == 0.8 and ctx.identite["apparitions"][clean][0]["pose"] == "rire"
    rp.set_texts(p["project_id"], "clip", "fr", {"titre": "Autre"})
    rp.start_render(p["project_id"])
    rp.run_render(p["project_id"])
    assert len(fakes["nettoyes"]) == 2                                                    # kept: never hidden twice


def test_without_the_identity_nothing_is_detected_nor_cleaned(fakes, project):
    pid = new(project)["project_id"]
    rp.run_analysis(pid)
    rp.start_render(pid)
    rp.run_render(pid)
    assert fakes["vus"] == [] and fakes["nettoyes"] == [] and all(c[2].identite is None for c in fakes["ctx"])


def test_his_voice_kept_leaves_the_sources_as_they_are(fakes, project):
    project.add_channel("chanA")
    p = rp.create("https://y", ["clip"], [{"langue": "fr", "channel": "chanA", "profile": {}, "music_dir": "x"}], voix_joueur="originale")
    rp.run_analysis(p["project_id"])
    rp.start_render(p["project_id"])
    rp.run_render(p["project_id"])
    ctx = fakes["ctx"][-1][2]
    assert fakes["passages"] == [] and not ctx.son_refait and ctx.lines == {} and ctx.moments["w0#0"]["fichier"].endswith("w0.mp4")


def test_a_failed_analysis_says_why(fakes, project, monkeypatch):
    monkeypatch.setattr(moments, "find", lambda path, dur: [])
    p = new(project)
    rp.run_analysis(p["project_id"])
    p = rp.load(p["project_id"])
    assert p["status"] == "error" and "Aucun moment" in p["error"] and p["failed_step"] == "analysing"


def test_texts_corrected_then_every_short_made_then_sent_to_publication(fakes, project):
    pid = new(project)["project_id"]
    rp.run_analysis(pid)
    rp.set_texts(pid, "clip", "fr", {"titre": "  Le  pire   p'tit déj ", "publication": {"tags": ["roblox", " drôle "]}})
    rp.start_render(pid)
    rp.run_render(pid)
    p = rp.load(pid)
    assert p["status"] == "review" and sorted(p["videos"]) == ["clip_en", "clip_fr", "devine_en", "devine_fr"]
    assert ("clip", "fr", voix.DEFAULTS["fr"], None, {"fr": "Le pire p'tit déj", "en": "Hello"}) in fakes["render"]
    # a correction after the render: only that Short is made again
    rp.set_texts(pid, "devine", "en", {"question": "What happens next?"})
    rp.start_render(pid)
    fakes["render"].clear()
    rp.run_render(pid)
    assert [(s, l) for s, l, *_ in fakes["render"]] == [("devine", "en")]
    p = rp.send(pid, ["clip_fr", "devine_en"])
    v = db.get_video(f"chanA_{pid}_clip_fr")
    assert v["status"] == "ready_for_upload" and v["source"] == "roblox" and v["channel"] == "chanA"
    assert v["ai_data"]["title"] == "Le pire petit déjeuner 🤢" and v["ai_data"]["tags"] == ["roblox", "drôle"]
    assert "Images : Roblox Idol — https://www.youtube.com/watch?v=NvGUWTH2U5Q" in v["ai_data"]["description"]
    assert os.path.exists(v["video_path"]) and v["recette"] == {"type": "roblox", "style": "clip", "langue": "fr",
                                                               "source": "https://www.youtube.com/watch?v=NvGUWTH2U5Q"}
    assert db.get_video(f"chanB_{pid}_devine_en")["ai_data"]["title"] == "The worst breakfast 🤢"
    assert p["status"] == "review"                                   # two still to send
    assert rp.send(pid, ["clip_en", "devine_fr"])["status"] == "done"
    assert rp.send(pid, ["clip_fr"])                                 # sent twice: nothing doubled
    assert len(db.query_videos(batch_id=pid)) == 4


def test_the_channels_music_is_used_when_asked(fakes, project, tmp_path):
    for ch in ("chanA", "chanB"):
        os.makedirs(f"music_{ch}", exist_ok=True)
        open(f"music_{ch}/song.mp3", "w").write("x")
    project.add_channel("chanA")
    project.add_channel("chanB")
    p = rp.create("https://y", ["clip"], [{"langue": l, "channel": c, "profile": {"adaptation": {"music_file": "song.mp3"}},
                                          "music_dir": f"music_{c}"} for l, c in (("fr", "chanA"), ("en", "chanB"))], "chaine")
    rp.run_analysis(p["project_id"])
    rp.start_render(p["project_id"])
    rp.run_render(p["project_id"])
    assert {m for *_, m, _ in fakes["render"]} == {"music_chanA/song.mp3", "music_chanB/song.mp3"}


def test_nothing_is_sent_before_it_is_made(fakes, project):
    pid = new(project)["project_id"]
    rp.run_analysis(pid)
    with pytest.raises(rp.PipelineError, match="pas à cette étape"):
        rp.send(pid, ["clip_fr"])
    rp.delete(pid)
    with pytest.raises(rp.PipelineError, match="introuvable"):
        rp.load(pid)


def test_a_project_folder_is_kept_by_the_storage_cleanup_while_the_project_lives(fakes, project):
    import storage
    pid = new(project)["project_id"]
    rp.run_analysis(pid)
    cat = lambda: {os.path.normpath(i["path"]): i["category"] for i in storage.scan()["items"]}
    assert cat()[os.path.normpath(f"temp/roblox/{pid}")] == "in_use"
    db.delete_roblox(pid)
    assert cat()[os.path.normpath(f"temp/roblox/{pid}")] == "orphans"
