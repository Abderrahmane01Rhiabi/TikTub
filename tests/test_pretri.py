"""The free pre-sort « image + parole » and its two companions (2026-11-13, labo_soustitres): the channels to avoid,
and the « image générée par IA ? » question in the shots' description."""

import json

import pytest

from adaptation import chaines_evitees as ce
from adaptation import finder, montage_pro, pretri


# ---------------------------------------------------------------- channels to avoid

def test_the_list_starts_with_the_ai_explainer_channel_and_is_kept(project):
    assert [e["nom"] for e in ce.entries()] == ["عين على مشاريع الغد"]
    ce.add("  Giga   Builds FR ", "images douteuses")
    assert ce.avoided("giga builds fr") and ce.avoided("GIGA-BUILDS FR") and not ce.avoided("Giga Builds")
    ce.add("giga builds fr")                                       # the same channel again: replaced
    assert len(ce.entries()) == 2
    ce.remove("عين على مشاريع الغد")
    assert [e["nom"] for e in ce.entries()] == ["giga builds fr"]
    with pytest.raises(ValueError):
        ce.remove("nulle part")
    with pytest.raises(ValueError):
        ce.add("   ")


def test_an_unreadable_list_is_never_rewritten(project, monkeypatch):
    ce.add("Une chaîne")
    open(ce.FILE, "w").write("{pas du json")
    monkeypatch.setattr(ce.time, "sleep", lambda s: None)
    with pytest.raises(ValueError):
        ce.add("Une autre")
    assert open(ce.FILE).read() == "{pas du json"


def test_their_videos_leave_the_search_before_any_check(project):
    c = lambda u, ch: {"url": u, "channel": ch, "score": 5, "duration": 60}
    sug = {"scenes": [{"candidats": [c("a", "👁️ عين على مشاريع الغد"), c("b", "ONCF")]}],
           "comptes": [{"videos": [c("a", "👁️ عين على مشاريع الغد")]}], "verifs": {"a": {"verdict": "oui"}}}
    assert ce.drop(sug) == ["a"]
    assert [x["url"] for x in sug["scenes"][0]["candidats"]] == ["b"] and sug["comptes"][0]["videos"] == []
    assert "a" not in sug["verifs"] and sug["evitees"] == ["a"]


def test_the_settings_routes(client):
    r = client.get("/api/chaines-evitees")
    assert r.status_code == 200 and r.json()["chaines"][0]["nom"] == "عين على مشاريع الغد"
    assert client.post("/api/chaines-evitees", json={"nom": "X", "note": "n"}).json()["chaines"][-1]["nom"] == "X"
    assert client.post("/api/chaines-evitees", json={"nom": " "}).status_code == 400
    assert [c["nom"] for c in client.post("/api/chaines-evitees/retirer", json={"nom": "x"}).json()["chaines"]] == \
        ["عين على مشاريع الغد"]
    assert client.post("/api/chaines-evitees/retirer", json={"nom": "x"}).status_code == 404


# ---------------------------------------------------------------- AI-made pictures

def test_a_shot_described_as_ai_made_is_set_aside(monkeypatch, tmp_path):
    class G:
        def _generate_content(self, parts, **kw):
            assert '"ia"' in parts[0]["text"] and "rendu 3D" in parts[0]["text"]
            return {"plans": [{"id": "S0_00", "desc": "chantier", "pertinence": 9, "ia": True},
                              {"id": "S0_01", "desc": "rendu du stade", "pertinence": 9, "ia": False}]}
    thumb = tmp_path / "t.jpg"
    thumb.write_bytes(b"\xff\xd8\xff")
    shots = [{"id": "S0_00", "thumb": str(thumb)}, {"id": "S0_01", "thumb": str(thumb)}]
    montage_pro.describe(shots, "TGV", gemini=G())
    assert shots[0]["ia"] is True and montage_pro.set_aside(shots[0]) == "image IA"
    assert shots[1]["ia"] is False and montage_pro.set_aside(shots[1]) is None


# ---------------------------------------------------------------- the pre-sort

def test_a_name_is_heard_in_its_spellings_at_its_word():
    cues = [{"t": 10.0, "text": "Le Buraq file vers Marrakech",
             "words": [[10.0, "Le"], [10.4, "Buraq"], [11.0, "file"], [11.5, "vers"], [12.0, "Marrakech"]]},
            {"t": 30.0, "text": "وصل البراق إلى المحطة", "words": [[30.0, "وصل"], [30.6, "البراق"], [31.2, "إلى"]]},
            {"t": 50.0, "text": "un buraqueur", "words": []}]
    assert pretri.heard(cues, ["boraq", "buraq", "البراق"]) == [10.4, 30.6, 50.0]
    assert pretri.heard(cues, ["xyz"]) == []
    assert pretri.heard(cues, ["ab"]) == []                         # too short to mean anything


def test_the_order_puts_the_video_where_the_name_is_said_first():
    clips = {"a": {"ts": [0, 10, 20], "s": [[0.30, 0.1], [0.10, 0.1], [0.12, 0.1]]},      # best picture, name never said
             "b": {"ts": [0, 10, 20], "s": [[0.10, 0.1], [0.25, 0.1], [0.10, 0.1]]},      # « Settat » said at 11 s
             "c": {"ts": [0, 5], "s": [[0.0, 0.31], [0.0, 0.2]]}}
    said = {"b": [{"t": 11.0, "text": "le viaduc de Settat", "words": []}],
            "a": [{"t": 40.0, "text": "Settat", "words": []}]}                             # said far from any picture
    out = pretri.order(clips, {0: ["settat", "سطات"]}, said, 2)
    assert out["visuels"][0]["identite"]["url"] == "b" and out["visuels"][0]["image"]["url"] == "a"
    assert out["visuels"][1]["identite"] is None and out["visuels"][1]["image"]["url"] == "c"
    assert out["premiers"] == ["b", "a", "c"]                       # identities first, then the best pictures


def test_verify_best_watches_the_pre_sort_first():
    c = lambda u, sc: {"url": u, "score": sc, "duration": 60, "origines": ["youtube"]}
    sug = {"scenes": [{"candidats": [c("top", 9), c("x", 5), c("y", 4)]}, {"candidats": [c("z", 3), c("long", 1)]}]}
    sug["scenes"][1]["candidats"][1]["duration"] = 99999
    seen = []
    finder.verify_best(sug, {}, n=3, checker=lambda u, s, p: seen.append(u) or {"verdict": "non"}, workers=1,
                       first=["y", "long", "inconnue", "z"])
    assert seen == ["y", "z", "top"]                                # too long / unknown skipped, then as before


def test_the_whole_pre_sort_with_its_parts_faked(project, monkeypatch, tmp_path):
    sug = {"scenes": [{"candidats": [{"url": "https://www.youtube.com/watch?v=AAAAAAAAAAA", "duration": 60},
                                     {"url": "https://www.youtube.com/watch?v=BBBBBBBBBBB", "duration": 60}]},
                      {"candidats": [{"url": "https://www.youtube.com/watch?v=CCCCCCCCCCC", "duration": 60}]}]}
    a, b, c = (f"https://www.youtube.com/watch?v={x * 11}" for x in "ABC")
    monkeypatch.setattr(pretri, "clip_scores", lambda urls, ideas, folder, report: {
        a: {"ts": [0, 10], "s": [[0.3, 0.1], [0.1, 0.1]]}, b: {"ts": [0, 10], "s": [[0.1, 0.1], [0.28, 0.1]]},
        c: {"ts": [0], "s": [[0.0, 0.29]]}})
    monkeypatch.setattr(pretri, "noms", lambda visuals, gemini=None: {0: ["hassan ii", "الحسن الثاني"]})
    listened = []
    monkeypatch.setattr(pretri, "speech", lambda urls, folder, report: listened.extend(urls) or {
        b: [{"t": 9.0, "text": "ملعب الحسن الثاني", "words": []}]})
    out = pretri.run(sug, ["stadium render", "airport"], ["le stade", "l'aéroport"], str(tmp_path))
    assert out["premiers"] == [b, a, c] and sug["pretri"]["ecoutees"] == 3 and listened[0] == a
    monkeypatch.setattr(pretri, "noms", lambda visuals, gemini=None: {})
    listened.clear()
    assert pretri.run(sug, ["x", "y"], ["x", "y"], str(tmp_path))["ecoutees"] == 0 and listened == []   # no name: no Whisper


def test_the_names_call_reads_only_real_names():
    class G:
        def _generate_content(self, parts, **kw):
            return {"images": [{"n": 1, "noms": ["Boraq", "البراق", "x"]}, {"n": 2, "noms": []}, {"n": 9, "noms": ["z12"]}]}
    assert pretri.noms(["le train", "un chantier"], gemini=G()) == {0: ["boraq", "البراق"]}

    class Down:
        def _generate_content(self, parts, **kw):
            raise RuntimeError("503")
    assert pretri.noms(["a"], gemini=Down()) == {}


def test_the_speech_reads_finished_files_and_leaves_music_only_videos(tmp_path, monkeypatch):
    u1, u2 = "https://www.youtube.com/watch?v=AAAAAAAAAAA", "https://www.youtube.com/watch?v=BBBBBBBBBBB"
    (tmp_path / "AAAAAAAAAAA.json").write_text(json.dumps({"parole_s": 120, "cues": [{"t": 1, "text": "x"}]}))
    (tmp_path / "BBBBBBBBBBB.json").write_text(json.dumps({"parole_s": 4, "cues": []}))
    monkeypatch.setattr(pretri.subprocess, "Popen", lambda *a, **k: pytest.fail("nothing left to transcribe"))
    assert pretri.speech([u1, u2], str(tmp_path), lambda *a: None) == {u1: [{"t": 1, "text": "x"}]}


def test_a_description_answered_as_a_bare_list_is_read(tmp_path):
    """2026-11-13: Gemini answered [..] instead of {"plans": [..]} and the whole stock stopped ('list'.get)."""
    class G:
        def _generate_content(self, parts, **kw):
            return [{"id": "S0_00", "desc": "un viaduc", "pertinence": 8, "ia": False}]
    thumb = tmp_path / "t.jpg"
    thumb.write_bytes(b"\xff\xd8\xff")
    shots = [{"id": "S0_00", "thumb": str(thumb)}]
    montage_pro.describe(shots, "TGV", gemini=G())
    assert shots[0]["desc"] == "un viaduc"
