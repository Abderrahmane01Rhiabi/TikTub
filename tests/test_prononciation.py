"""The pronunciation dictionary (2026-11-09): listed WHOLE words read ElevenLabs' way, everything else untouched, the
captions keeping the written words, and a narration said again when the dictionary changes."""

import base64

import pytest

from adaptation import prononciation as pr
from adaptation import voices


def test_only_whole_listed_words_change_and_their_punctuation_stays():
    words = {"المعلمة": "مَعْلَمة", "جرادي": "جْرادي"}
    said, sizes = pr.apply("صممو هاد المعلمة، فيه جرادي معلقة. والمعلمة", "ar", words)
    assert said == "صممو هاد مَعْلَمة، فيه جْرادي معلقة. والمعلمة"     # « والمعلمة » is another word: untouched
    assert sizes == [1, 1, 1, 1, 1, 1, 1]
    said, sizes = pr.apply("Les Benslimane arrivent", "fr", {"Benslimane": "Ben Slimane"})
    assert said == "Les Ben Slimane arrivent" and sizes == [1, 2, 1]


def test_the_dictionary_is_kept_and_a_wrong_entry_is_refused_or_removed(project):
    pr.add("المعلمة", "مَعْلَمة", "ar", "pas m3alma")
    pr.add("المعلمة", "مَعْلَمَة", "ar")                                  # the same word again: replaced
    assert pr.table("ar") == {"المعلمة": "مَعْلَمَة"} and pr.table("fr") == {}
    with pytest.raises(ValueError):
        pr.add("deux mots", "x")
    with pytest.raises(ValueError):
        pr.add("pareil", "pareil")
    sig = pr.signature("ar")
    pr.remove("المعلمة", "ar")
    assert pr.table("ar") == {} and pr.signature("ar") != sig


def test_elevenlabs_hears_the_dictionary_and_the_captions_keep_the_written_words(project, monkeypatch, tmp_path):
    pr.add("Benslimane", "Ben Slimane", "fr")
    sent = {}

    class R:
        status_code = 200

        def json(self):
            text = sent["text"]
            n = len(text)
            return {"audio_base64": base64.b64encode(b"mp3").decode(),
                    "alignment": {"characters": list(text), "character_start_times_seconds": [i * 0.1 for i in range(n)],
                                  "character_end_times_seconds": [i * 0.1 + 0.1 for i in range(n)]}}
    monkeypatch.setattr(voices, "_key", lambda: "k")
    monkeypatch.setattr(voices.requests, "post", lambda url, **kw: sent.update(text=kw["json"]["text"]) or R())
    v = voices.synthesize([{"texte": "Le stade de Benslimane."}, {"texte": "Il est grand."}], "vid", "fr",
                          str(tmp_path / "v.mp3"))
    assert sent["text"] == "Le stade de Ben Slimane. Il est grand."
    assert [w["w"] for w in v["words"]] == ["Le", "stade", "de", "Benslimane.", "Il", "est", "grand."]
    assert v["passages"][0]["texte"] == "Le stade de Benslimane." and v["passages"][1]["words"] == [4, 5, 6]
    ben = v["words"][3]
    assert ben["start"] == pytest.approx(1.2) and ben["end"] > 2.0          # « Ben Slimane. » as one written word
    assert v["prononciation"] == pr.signature("fr")


def test_a_narration_is_said_again_when_the_dictionary_changes(project, monkeypatch):
    from adaptation import montage_pro as mp
    t = {"voice_id": "v", "language": "ar", "channel": "c", "script": {"passages": [{"texte": "المعلمة"}]},
         "voice": {"voice_id": "v", "texts": ["المعلمة"], "model": voices.MODEL, "prononciation": "[]"}}
    said = []
    monkeypatch.setattr(voices, "synthesize", lambda *a, **k: said.append(1) or {"words": [], "passages": [{"words": []}]})
    import os
    open("v.mp3", "w").write("x")
    mp._voice({}, t, "v.mp3", lambda *a: None, 0)
    assert said == []                                                     # same text, same dictionary: kept
    pr.add("المعلمة", "مَعْلَمة", "ar")
    mp._voice({}, t, "v.mp3", lambda *a: None, 0)
    assert said == [1]


def test_the_settings_routes_add_list_listen_and_remove(client, monkeypatch):
    r = client.post("/api/prononciation", json={"mot": "فبرطمات", "dire": "فپارطمات", "langue": "ar", "note": "pas bartamat"})
    assert r.status_code == 200 and r.json()["mots"][0]["dire"] == "فپارطمات"
    assert client.post("/api/prononciation", json={"mot": "deux mots", "dire": "x"}).status_code == 400
    said = []

    def fake(passages, voice_id, lang, path, model=None, dictionary=True):
        said.append((passages[0]["texte"], dictionary))
        import os
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "wb").write(b"mp3")
        return {}
    monkeypatch.setattr(voices, "synthesize", fake)
    url = client.post("/api/prononciation/ecouter", json={"texte": "فبرطمات", "voice_id": "v", "langue": "ar",
                                                          "dictionnaire": False}).json()["url"]
    assert said == [("فبرطمات", False)] and client.get(url).content == b"mp3"
    client.post("/api/prononciation/ecouter", json={"texte": "فبرطمات", "voice_id": "v", "langue": "ar", "dictionnaire": False})
    assert len(said) == 1                                                 # the same listen: not paid twice
    assert client.delete("/api/prononciation/ar/فبرطمات").json()["mots"] == []
