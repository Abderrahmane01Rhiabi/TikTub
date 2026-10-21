"""The recipe of a video, the same shape for Adaptation, Génération, Montage auto and Import."""

import os

import pytest

import recette

KEYS = {"version", "type", "chaine", "langue", "faite_le", "accroche", "structure", "musique", "voix", "style",
        "details", "reconstruite"}


@pytest.fixture
def here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "song.mp3").write_bytes(b"music" * 100)
    (tmp_path / "bg.jpg").write_bytes(b"picture")
    return tmp_path


def test_the_hook_of_a_narration_is_its_first_sentence_without_voice_tags():
    assert recette.first_sentence('[curious] Tu as vu ça ? <break time="0.5s"/> Ensuite…') == "Tu as vu ça ?"
    assert recette.first_sentence("") is None


def test_an_asset_is_archived_once_by_content(here):
    a = recette.archive("song.mp3", "musique")
    assert a and os.path.exists(a) and a == recette.archive("song.mp3", "musique")
    assert len(os.listdir("archive/musique")) == 1 and recette.archive("missing.mp3", "musique") is None


def test_every_kind_has_the_same_shape(here):
    gen = recette.from_generation({"channel": "c", "script_text": "Première phrase. Deuxième.", "bg_music_path": "song.mp3",
                                   "caption_style": "accent", "bg_video_path": "bg.jpg"}, length=40.0, voice_id="v1",
                                  music_level=0.22)
    mon = recette.from_montage({"channel": "c", "montage": {"hook": "Regarde ça 😂", "hooks": ["Regarde ça 😂"],
                                                            "plan": {"resume": "r"}, "brolls": ["b1"]}},
                               {"music_file": "song.mp3", "music_entry": 34.0, "volume": "doux", "caption_style": "accent",
                                "recipe": "hopecore", "hook": True},
                               {"duration": 20.0, "keep": [(0, 10), (12, 18)], "shots": [{"start": 10}]}, "song.mp3")
    imp = recette.from_import({"channel": "c", "url": "https://tiktok.com/x", "frame_mode": "letterbox"},
                              {"fond": "bg.jpg"}, length=15.0)
    ada = recette.from_adaptation({"chaine": "c", "langue": "fr", "voix": "v2", "style": "neon",
                                   "musique": {"fichier": "song.mp3", "debut_s": 33.0, "gain": 0.15},
                                   "structure": {"duree_s": 30.0, "plans": 7, "accroche_s": 3.5, "fin_en_boucle": True},
                                   "plans": [{"texte": "Pourquoi ?"}]}, "song.mp3")
    for r in (gen, mon, imp, ada):
        assert set(r) == KEYS and r["version"] == recette.VERSION and not r["reconstruite"]
    assert gen["accroche"]["texte"] == "Première phrase." and gen["musique"]["fichier"] == "song.mp3"
    assert gen["musique"]["archive"] and gen["voix"] == {"id": "v1"} and gen["style"]["sous_titres"] == "accent"
    assert mon["accroche"]["texte"] == "Regarde ça 😂" and mon["musique"]["debut_s"] == 34.0 and mon["structure"]["plans"] == 3
    assert imp["style"]["fond"] == "bg.jpg" and imp["style"]["fond_archive"] and imp["musique"] is None
    assert ada["accroche"] == {"texte": "Pourquoi ?", "duree_s": 3.5} and ada["musique"]["gain"] == 0.15
    assert ada["structure"]["plan_moyen_s"] == round(30 / 7, 2) and ada["details"]["style"] == "neon"


def test_old_videos_get_a_rebuilt_recipe_and_a_recipe_is_never_overwritten(here):
    videos = [{"video_id": "g", "source": "generated", "channel": "c", "youtube_id": "y1", "script_text": "Salut.",
               "bg_music_path": "song.mp3"},
              {"video_id": "i", "channel": "c", "youtube_id": "y2", "background_mode": "random"},
              {"video_id": "k", "channel": "c", "youtube_id": "y3", "recette": {"type": "import"}},
              {"video_id": "draft", "channel": "c"}]
    done = {v["video_id"]: v["recette"] for v in recette.backfill(videos)}
    assert set(done) == {"g", "i"} and all(r["reconstruite"] for r in done.values())
    assert done["g"]["type"] == "generation" and done["i"]["type"] == "import"


def test_the_videos_using_a_track_are_found(here):
    videos = [{"video_id": "a", "recette": {"musique": {"fichier": "song.mp3"}, "style": {}}},
              {"video_id": "b", "bg_music_path": "/x/other.mp3"}, {"video_id": "c", "bg_video_path": "/y/song.mp3"}]
    assert recette.used_by(videos, "channels/x/assets/music/song.mp3") == ["a", "c"]
