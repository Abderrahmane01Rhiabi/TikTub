"""The music casting: songs with categories and lyrics (the person's tags win over the AI's), a channel's
rules, the AI's pick among the allowed songs, and a change at the preview that keeps the edit."""

import json
import os

from adaptation import montage_pro as mp
from adaptation import musique_casting as mc
from adaptation import pipeline as ap


def song(folder, name, categories=None, paroles=None, humeur="x"):
    path = os.path.join(folder, name)
    open(path, "wb").write(b"\0" * 10)
    os.makedirs(os.path.join(folder, ".analyses"), exist_ok=True)
    a = {"titre": name[:-4], "humeur": humeur, "moment_fort": 12.0, "duree": 120.0, "montees": [12.0]}
    if categories is not None:
        a.update(categories=categories, paroles=paroles)
    json.dump(a, open(os.path.join(folder, ".analyses", name + ".json"), "w"))
    return path


def test_the_person_s_tags_win_over_the_ai_s(tmp_path):
    p = song(str(tmp_path), "a.mp3", ["triste"], True)
    assert mc.song_info(p)["categories"] == ["triste"] and mc.song_info(p)["par"] == "ia"

    info = mc.set_tags(p, ["tension", "klingon", "tension"], False)

    assert info["categories"] == ["tension"] and info["paroles"] is False and info["par"] == "toi"


def test_a_channel_s_rules_keep_its_categories_and_no_lyrics_when_asked(tmp_path):
    d = str(tmp_path)
    song(d, "news.mp3", ["actu", "tension"], False)
    song(d, "pop.mp3", ["triste"], True)
    song(d, "calme_chante.mp3", ["calme"], True)
    song(d, "jamais.mp3")                                       # never classified: lyrics unknown
    songs = mc.library([d])

    assert [s["fichier"] for s in mc.allowed(songs, ["actu", "calme"], False)] == ["calme_chante.mp3", "news.mp3"]
    assert [s["fichier"] for s in mc.allowed(songs, ["actu", "calme"], True)] == ["news.mp3"]
    assert len(mc.allowed(songs, [], False)) == 4                # nothing ticked: every song


def test_the_ai_picks_among_the_allowed_songs_only(tmp_path):
    d = str(tmp_path)
    song(d, "a.mp3", ["actu"], False)
    song(d, "b.mp3", ["tension"], False)

    class G:
        def _generate_content(self, parts, **kw):
            self.prompt = parts[0]["text"]
            return {"musique": 2, "pourquoi": "tendue comme le sujet"}
    g = G()
    r = mc.choose(mc.library([d]), "Titre", "ce qui est dit", "spectaculaire", "news", gemini=g)

    assert r["song"]["fichier"] == "b.mp3" and "a" in g.prompt and "sans paroles" in g.prompt
    assert mc.choose(mc.library([d])[:1], "T", "r", "calme", None)["song"]["fichier"] == "a.mp3"   # one: no question


def test_changing_the_music_at_the_preview_keeps_the_voice_and_the_cuts(project, monkeypatch, tmp_path):
    d = str(tmp_path)
    song(d, "news.mp3", ["actu"], False)
    monkeypatch.setattr(mp, "_music_folders", lambda t: [d])
    ap.save({"project_id": "ad_m", "status": "preview_review", "pro": True,
             "targets": [{"channel": "chanA", "language": "fr", "voice_id": "v", "music_path": None,
                          "preview": {"montage": [{"phrase": 1, "plan": "S0_00", "debut": 0, "fin": 2}]}}]})

    p = mp.set_music("ad_m", "chanA", "news.mp3")

    t = p["targets"][0]
    assert p["status"] == "voicing" and t["keep_edit"] and t["music_by"] == "toi"
    assert t["music_path"].endswith("news.mp3") and t["music_start"] == 12.0      # on its strongest moment
    p = ap.save({**p, "status": "preview_review"})
    assert mp.set_music("ad_m", "chanA", None)["targets"][0]["music_path"] is None   # no music: allowed
