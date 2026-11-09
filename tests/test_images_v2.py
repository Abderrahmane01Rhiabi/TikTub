"""Images v2 (the lab of 2026-11-08, docs/recherches/labo_images.md): shots judged against each sentence's idea, the
off-topic ones that fit brought back, the news videos about another place set aside, a Pixabay fallback for a
sentence nothing fits, 2 shots a video at most, and the finished montage read again."""

import pytest

from adaptation import montage_pro as mp
from adaptation import vision


def shot(sid, source, colle, garde=True, ecarte=None, pert=7):
    return {"id": sid, "source": source, "start": 0.0, "end": 3.0, "file": "f.mp4", "thumb": "t.jpg", "colle": colle,
            "garde": garde, "ecarte": ecarte, "pertinence": pert, "force": 6, "desc": sid}


def test_an_off_topic_shot_that_fits_a_sentence_comes_back_and_a_sentence_nothing_fits_is_found():
    shots = [shot("S0_00", 0, [0.33, 0.20]), shot("S1_01", 1, [0.20, 0.35], garde=False, ecarte="hors sujet", pert=2),
             shot("S1_02", 1, [0.21, 0.22], garde=False, ecarte="hors sujet", pert=2)]
    assert vision.rescue(shots, 2) == ["S1_01"]                         # « Casablanca being rebuilt » for sentence 2
    assert shots[1]["garde"] and shots[1]["repeche"] == 2 and not shots[2]["garde"]
    shots[1]["colle"] = [0.2, 0.2]
    assert vision.missing(shots, 2) == [1]                               # nothing kept conveys sentence 2


def test_the_editor_sees_which_sentences_a_shot_fits_and_the_code_keeps_two_shots_a_video_at_most():
    assert mp._fits({"colle": [0.30, 0.10, 0.35]}) == "3:0.35 1:0.30" and mp._fits({"colle": [0.1]}) == "-"
    v = {"duration": 9.0, "words": [{"w": w, "start": s, "end": s + 0.3} for w, s in
                                    [("a", 0.0), ("b", 1.5), ("c", 3.0), ("d", 4.5), ("e", 6.0), ("f", 7.5)]],
         "passages": [{"start": 0.0, "end": 2.9, "words": [0, 1]}, {"start": 3.0, "end": 5.9, "words": [2, 3]},
                      {"start": 6.0, "end": 8.9, "words": [4, 5]}]}
    shots = [shot("A1", 0, [0.3, 0.3, 0.3]), shot("A2", 0, [0.3, 0.3, 0.3]), shot("A3", 0, [0.3, 0.3, 0.3]),
             shot("B1", 1, [0.1, 0.1, 0.32])]
    raw = {"montage": [{"phrase": 1, "coupes": [{"plan": "A1", "mot": 0}]}, {"phrase": 2, "coupes": [{"plan": "A2", "mot": 0}]},
                       {"phrase": 3, "coupes": [{"plan": "A3", "mot": 0}]}]}
    edl = mp.build_edit(raw, v, shots)
    assert [e["plan"] for e in edl] == ["A1", "A2", "B1"]                # a 3rd shot of the same video refused


def test_the_news_videos_about_another_place_are_set_aside_only_when_two_answers_agree():
    class G:
        def __init__(self, *answers):
            self.answers = list(answers)

        def _generate_content(self, parts, **kw):
            assert "They're Building a 170 KM City" in parts[0]["text"]
            return self.answers.pop(0)
    metas = [{"path": "a", "titre": "ملعب الحسن الثاني آخر تطورات"}, {"path": "b", "titre": "They're Building a 170 KM City in the Desert"},
             {"path": "c", "titre": "Benslimane stadium works"}]
    neom = {"videos": [{"n": 0, "lieu": "Benslimane", "autre": False}, {"n": 1, "lieu": "NEOM, Arabie saoudite", "autre": True}]}
    assert vision.other_places("Le Grand Stade à Benslimane", metas, gemini=G(neom, neom)) == {1: "NEOM, Arabie saoudite"}
    flip = {"videos": [{"n": 0, "lieu": "Casablanca", "autre": True}]}     # one answer alone is not enough
    assert vision.other_places("Le Grand Stade à Benslimane", metas, gemini=G(flip, neom)) == {}
    most = {"videos": [{"n": k, "lieu": "ailleurs", "autre": True} for k in range(3)]}
    assert vision.other_places("Le Grand Stade à Benslimane", metas, gemini=G(most, most)) == {}   # more than half: distrusted


def test_ideas_come_from_the_storyboard_else_one_call_and_are_kept():
    p = {"targets": [{"language": "fr", "script": {"passages": []}}],
         "storyboard": {"plans": [{"image": "x", "textes": {"fr": {"texte": "Les familles reçoivent les clés."}}}]}}

    class G:
        def _generate_content(self, parts, **kw):
            return {"idees": ["new apartment buildings, a hand giving keys"]}
    assert vision.ideas_of(p, gemini=G()) == ["new apartment buildings, a hand giving keys"]
    assert p["storyboard"]["plans"][0]["idee"] == "new apartment buildings, a hand giving keys"
    assert vision.ideas_of(p, gemini=None) == ["new apartment buildings, a hand giving keys"]   # kept: no call


def test_the_fallback_needs_its_key_and_never_takes_an_ai_clip_for_the_news(monkeypatch, tmp_path):
    monkeypatch.setattr(vision, "_pixabay_key", lambda: None)
    assert vision.pixabay("new apartment buildings", str(tmp_path), 0, True, set()) is None
    import requests

    class R:
        def __init__(self, data=None, content=b"img"):
            self.data, self.content = data, content

        def json(self):
            return self.data
    hits = [{"id": 1, "tags": "ai generated, keys", "duration": 8, "pageURL": "u1", "user": "x",
             "videos": {"small": {"thumbnail": "http://t1", "url": "http://v1"}, "medium": {"url": "http://v1"}}},
            {"id": 2, "tags": "keys, house", "duration": 8, "pageURL": "u2", "user": "y",
             "videos": {"small": {"thumbnail": "http://t2", "url": "http://v2"}, "medium": {"url": "http://v2", "width": 1280, "height": 720}}}]
    seen = []
    monkeypatch.setattr(vision, "_pixabay_key", lambda: "k")
    monkeypatch.setattr(requests, "get", lambda url, **kw: seen.append(url) or (R({"hits": hits}) if "api" in url else R()))
    import torch
    monkeypatch.setattr(vision, "embed_images", lambda paths: torch.ones(len(paths), 2) / 2 ** 0.5)
    monkeypatch.setattr(vision, "embed_texts", lambda texts: torch.ones(len(texts), 2) / 2 ** 0.5)
    (tmp_path / "pixabay_2.mp4").write_bytes(b"v")
    got = vision.pixabay("a hand giving keys", str(tmp_path), 0, True, set())
    assert got["pixabay_id"] == 2 and got["credit"] == "Pixabay — y" and "http://t1" not in seen   # the AI clip skipped


def test_the_review_flags_the_shots_that_contradict_and_proposes_one_from_the_stock(monkeypatch, tmp_path):
    out = tmp_path / "preview.mp4"
    out.write_bytes(b"x")
    monkeypatch.setattr(mp, "_run", lambda cmd: open(cmd[-1], "wb").write(b"jpg"))
    p = {"project_id": "ad_r", "reference": {"sujet": "Karian"},
         "stock": [shot("S0_00", 0, [0.3, 0.2]), shot("S1_01", 1, [0.2, 0.36])]}
    t = {"script": {"passages": [{"texte": "On évacue."}, {"texte": "Les familles reçoivent les clés."}]}}
    preview = {"path": str(out), "montage": [{"phrase": 1, "plan": "S0_00", "debut": 0, "fin": 2},
                                             {"phrase": 2, "plan": "S0_00", "debut": 2, "fin": 4}]}

    class G:
        def _generate_content(self, parts, **kw):
            assert len(parts) == 3 and "reçoivent les clés" in parts[0]["text"]
            return {"plans": [{"plan": 1, "verdict": "exact"},
                              {"plan": 2, "verdict": "contredit", "pourquoi": "on voit le bidonville",
                               "a_la_place": "des immeubles neufs", "recherche": "new apartment buildings"}]}
    import torch
    monkeypatch.setattr(vision, "available", lambda: True)
    monkeypatch.setattr(vision, "_frames", lambda s, folder: [s["id"]])
    monkeypatch.setattr(vision, "embed_images", lambda paths: torch.tensor([[1.0, 0.0] if x == "S1_01" else [0.0, 1.0] for x in paths]))
    monkeypatch.setattr(vision, "embed_texts", lambda texts: torch.tensor([[0.3, 0.0]]))
    found = mp.review(p, t, preview, gemini=G())
    assert [(f["plan"], f["verdict"], f["proposition"]) for f in found] == [(2, "contredit", "S1_01")]


def test_a_big_stock_shows_the_editor_each_sentence_s_best_shots_and_the_strongest():
    shots = [shot(f"S{k // 10}_{k % 10}", k // 10, [0.1, 0.1], pert=5) for k in range(100)]
    shots[57]["colle"], shots[83]["colle"] = [0.4, 0.1], [0.1, 0.4]
    shots[12]["force"] = 10
    seen = mp.editable(shots, 2)
    ids = {s["id"] for s in seen}
    assert len(seen) == mp.EDIT_MAX and {"S5_7", "S8_3", "S1_2"} <= ids
    assert mp.editable(shots[:10], 2) == shots[:10]                      # a small stock: all of it
