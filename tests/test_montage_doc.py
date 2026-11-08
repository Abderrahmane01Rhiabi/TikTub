"""The editable montage (2026-11-08): one document per version says everything the render needs, the person's
changes are made safe, every render kept for « Annuler », and the render follows the document — banners, box,
words, captions' place, framing, the music's zones."""

import pytest

from adaptation import montage_doc as md
from adaptation import montage_pro as mp

VOICE = {"passages": [{"start": 0.0, "end": 2.8, "words": [0, 1]}, {"start": 3.0, "end": 6.5, "words": [2, 3]},
                      {"start": 6.8, "end": 9.4, "words": [4, 5]}],
         "words": [{"w": w, "start": s, "end": s + 0.4} for w, s in
                   [("Pourquoi", 0.0), ("700", 1.2), ("Depuis", 3.0), ("quatre", 4.4), ("En", 6.8), ("réalité", 7.9)]]}
EDL = [{"phrase": 1, "plan": "a", "debut": 0.0, "fin": 3.0}, {"phrase": 2, "plan": "b", "debut": 3.0, "fin": 6.8},
       {"phrase": 3, "plan": "c", "debut": 6.8, "fin": 10.0}]


def doc():
    return md.new(EDL, 3, None, 0.0, [])


def test_a_new_document_says_the_ai_s_montage():
    d = doc()
    assert [e["plan"] for e in d["plans"]] == ["a", "b", "c"] and d["plans"][0]["zoom"] == 1.0
    assert d["bandeaux"] == [{"texte": None, "cache": False}] * 3 and md.total(d) == 10.0


def test_the_person_s_cuts_are_snapped_on_words_and_kept_back_to_back():
    d = doc()
    d["plans"][1]["debut"] = 4.1                                  # dragged near « quatre » (4.4)
    d["plans"][2]["zoom"] = 9                                     # too close: the most allowed
    out = md.clean(d, VOICE, ["a", "b", "c"])
    assert [(e["debut"], e["fin"]) for e in out["plans"]] == [(0.0, 4.4), (4.4, 6.8), (6.8, 10.0)]
    assert out["plans"][1]["phrase"] == 2 and out["plans"][2]["zoom"] == 1.6


def test_what_cannot_be_is_refused_in_words_the_person_understands():
    d = doc()
    d["plans"][1]["plan"] = "zz"
    with pytest.raises(md.MontageError, match="plus dans ton stock"):
        md.clean(d, VOICE, ["a", "b", "c"])
    d = doc()
    d["plans"].insert(2, {"plan": "a", "debut": 6.5})              # 0.3 s: too short
    with pytest.raises(md.MontageError, match="trop court"):
        md.clean(d, VOICE, ["a", "b", "c"])


def test_music_zones_and_effects_are_kept_inside_the_video(tmp_path):
    fx = tmp_path / "pop_x.mp3"
    fx.write_bytes(b"x")
    d = doc()
    d["musique"]["zones"] = [{"debut": 3, "fin": 6, "volume": 40}, {"debut": 5, "fin": 5.1, "volume": 10}]
    d["effets"] = [{"file": str(fx), "start": 99, "gain": 0.3}, {"file": "/nope.mp3", "start": 1}]
    out = md.clean(d, VOICE, ["a", "b", "c"])
    assert out["musique"]["zones"] == [{"debut": 3.0, "fin": 6.0, "volume": 40}]           # 0.1 s: dropped
    assert [(e["kind"], e["start"], e["par"]) for e in out["effets"]] == [("pop", 10.0, "toi")]


def test_a_sound_change_keeps_the_picture_and_the_player_jumps_to_the_change():
    a = doc()
    b = md.clean({**a, "musique": {**a["musique"], "zones": [{"debut": 3, "fin": 6, "volume": 40}]}}, VOICE, ["a", "b", "c"])
    assert md.sound_only(a, b) and md.changed_at(a, b) == 3.0
    c = {**a, "plans": [a["plans"][0], {**a["plans"][1], "zoom": 1.3}, a["plans"][2]]}
    assert not md.sound_only(a, c) and md.changed_at(a, c) == 3.0


def test_every_render_is_kept_and_annuler_goes_back_one():
    t = {"montage": doc()}
    md.push(t, {**doc(), "bandeau_cadre": "rouge"})
    assert len(t["montage_versions"]) == 1 and t["montage"]["bandeau_cadre"] == "rouge"
    assert md.undo(t)["bandeau_cadre"] is None and t["montage_versions"] == []
    with pytest.raises(md.MontageError):
        md.undo(t)


def test_the_captions_follow_the_document(tmp_path):
    passages = [{"bandeau": "ORQUES : 700"}, {"bandeau": "MYSTÈRE"}, {"bandeau": "RÉVÉLATION"}]
    style = {"text": (255, 255, 255), "key": (255, 214, 10), "box": (17, 17, 17)}
    d = doc()
    d["bandeaux"][1] = {"texte": None, "cache": True}
    d["bandeaux"][2] = {"texte": "UN JEU", "cache": False}
    d["bandeau_cadre"] = "rouge"
    d["sous_titres"] = {"style": None, "position": "haut", "taille": 120, "mots": {"1": "sept-cents"}}
    path = tmp_path / "t.ass"
    caps = mp.captions_ass(VOICE, passages, str(path), "fr", style, d)
    ass = path.read_text(encoding="utf-8")
    assert "MYSTÈRE" not in ass and "UN JEU" in ass and "RÉVÉLATION" not in ass
    assert "&H002828D6" in ass and "SEPT-CENTS" in ass                     # the red box, the word fixed
    assert caps["y"] == mp.CAPTION_PLACES["haut"] and caps["taille"] == 115
    d["sous_titres"]["style"] = "karaoke"                                    # a library style draws the words
    mp.captions_ass(VOICE, passages, str(path), "fr", style, d)
    assert "SEPT-CENTS" not in path.read_text(encoding="utf-8")


def test_the_music_level_follows_the_zones_and_a_framing_change_makes_its_shot_again():
    level = mp.music_level({"volume": 50, "zones": [{"debut": 3.0, "fin": 6.0, "volume": 40}]}, 10.0)
    assert level.startswith(f"{mp.MUSIC_GAIN / 2:.4f}*(1+-0.600*clip((t-3.000)/0.2")
    s = {"file": "f.mp4", "start": 0, "end": 5, "x": 0.5}
    assert mp._piece_key(EDL[0], s) == mp._piece_key(dict(EDL[0]), s)
    assert mp._piece_key({**EDL[0], "zoom": 1.3}, s) != mp._piece_key(EDL[0], s)


def test_one_banner_or_one_group_of_captions_can_be_set_apart(tmp_path):
    passages = [{"bandeau": "ORQUES"}, {"bandeau": "MYSTÈRE"}, {"bandeau": "RÉVÉLATION"}]
    style = {"text": (255, 255, 255), "key": (255, 214, 10), "box": (17, 17, 17)}
    d = doc()
    d["bandeaux"][2]["cadre"] = "rouge"                                     # only the reveal's banner is red
    d["sous_titres"]["groupes"] = {"2": {"position": "haut", "taille": 140}, "4": {"style": "karaoke"}}
    d = md.clean(d, VOICE, ["a", "b", "c"])
    assert d["bandeaux"][2] == {"texte": None, "cache": False, "cadre": "rouge"} and "cadre" not in d["bandeaux"][0]
    path = tmp_path / "t.ass"
    mp.captions_ass(VOICE, passages, str(path), "fr", style, d)
    lines = path.read_text(encoding="utf-8").splitlines()
    ban = {l.split("}")[-1]: l for l in lines if ",Bandeau," in l}
    assert "\\3c&H002828D6&" in ban["RÉVÉLATION"] and "\\3c" not in ban["ORQUES"]
    depuis = next(l for l in lines if ",Sous," in l and "DEPUIS" in l)
    assert f"\\pos(540,{mp.CAPTION_PLACES['haut']})" in depuis and "\\fs134" in depuis
    assert not any(",Sous," in l and "RÉALITÉ" in l for l in lines)        # drawn by the karaoke style instead
    assert [g["style"] for g in mp.caption_groups(VOICE, d)] == [None, None, "karaoke"]
