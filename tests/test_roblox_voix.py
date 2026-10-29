"""Montage Roblox, the voices: the catalogue chosen by ear in the lab (etude_roblox/voix), the best one first and
starred, and a sample to listen to for each — the lab's own recording, else ElevenLabs' free preview (kept)."""

import os

from roblox import voix


def test_the_catalogue_puts_the_best_voice_first_and_never_marcus():
    fr, en = voix.catalogue("fr"), voix.catalogue("en")
    assert fr[0]["nom"] == "Donny" and fr[0]["meilleure"] and voix.DEFAULTS["fr"] == fr[0]["voice_id"]
    assert en[0]["nom"] == "Tyler" and en[0]["meilleure"] and voix.DEFAULTS["en"] == en[0]["voice_id"]
    assert sum(v["meilleure"] for v in fr + en) == 2
    assert all(v["nom"] != "Marcus" and v["voice_id"] != "y0s2ExEMuum3muUnA6Zd" for v in fr + en)
    assert len({v["voice_id"] for v in fr}) == len(fr) and voix.catalogue("ar") == []
    assert voix.known("fr", fr[3]["voice_id"]) and not voix.known("en", fr[0]["voice_id"])


def test_every_voice_tried_in_the_lab_has_its_own_sample():
    missing = [(l, v["nom"]) for l in ("fr", "en") for v in voix.catalogue(l) if not os.path.exists(voix.lab_sample(v["voice_id"], l))]
    assert missing == [("en", "Arthur")]                       # only tried in French: the free preview instead


def test_a_voice_without_a_lab_sample_gets_the_free_preview_once(project, monkeypatch):
    calls = []

    def info(vid):
        calls.append(vid)
        return {"preview_url": "https://x/p.mp3"}

    def download(url, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "wb").write(b"mp3")
        return path
    monkeypatch.setattr(voix.el, "fetch_info", info)
    monkeypatch.setattr(voix.el, "download_preview", download)
    arthur = next(v["voice_id"] for v in voix.catalogue("en") if v["nom"] == "Arthur")
    assert voix.sample(arthur, "en").endswith(f"{arthur}.mp3")
    assert voix.sample(arthur, "en") and calls == [arthur]                 # kept: asked once
    assert voix.sample(voix.DEFAULTS["fr"], "fr") == voix.lab_sample(voix.DEFAULTS["fr"], "fr") and calls == [arthur]


def test_the_voices_and_their_samples_through_the_api(client):
    r = client.get("/api/roblox/voix").json()
    assert r["fr"][0]["nom"] == "Donny" and r["en"][0]["nom"] == "Tyler"
    s = client.get(f"/api/roblox/voix/{voix.DEFAULTS['fr']}/echantillon?langue=fr")
    assert s.status_code == 200 and s.headers["content-type"] == "audio/mpeg"
    assert client.get("/api/roblox/voix/nope/echantillon?langue=fr").status_code == 404


def test_the_ai_writes_the_players_lines_at_their_place_in_the_file():
    class G:
        def _generate_content(self, parts, **kw):
            assert "[laughs]" in parts[-1]["text"] and "1.2 s : on y va" in parts[-1]["text"]
            return {"phrases": [{"a": 4.0, "fr": "[laughs] Trop fort !", "en": "[laughs] So good!"},
                                {"a": 0.5, "fr": "On y va !", "en": "Let's go!"}, {"a": "x"}, {"a": 99, "fr": "hors du passage"}]}
    lines = voix.write_lines("v.wav", 20.0, 35.0, "il saute", [{"texte": "on y va", "a": 21.2}], ["fr", "en"], gemini=G())
    assert lines == [{"a": 20.5, "fr": "On y va !", "en": "Let's go!"}, {"a": 24.0, "fr": "[laughs] Trop fort !", "en": "[laughs] So good!"}]
    assert voix.sans_balises("[laughs] Trop [shouts] fort !") == "Trop fort !"
