"""The voice casting: a channel's voices (darija = Moroccan ones), the AI's pick (the main voice unless a real
reason), each sentence's manner as an ElevenLabs v4 tag never shown in the captions, the person's choices kept."""

import db
from adaptation import pipeline as ap
from adaptation import settings
from adaptation import voix_casting as vc


def voice(vid, accent="modern standard", lang="ar", gender="female", **kw):
    db.upsert_voice({"voice_id": vid, "name": vid, "language": lang, "accent": accent, "gender": gender, **kw})


class G:
    def __init__(self, answer):
        self.answer, self.prompts = answer, []

    def _generate_content(self, parts, **kw):
        self.prompts.append(parts[0]["text"])
        return self.answer


def target(**kw):
    return {"channel": "chanA", "language": "ar", "voice_id": "main",
            "script": {"passages": [{"texte": "une"}, {"texte": "deux"}, {"texte": "trois"}]}, **kw}


def rules(monkeypatch, **kw):
    r = {"main": "main", "allowed": ["badr", "abdullah"], "mode": "auto", "dialect": None, "language": "ar", **kw}
    monkeypatch.setattr(vc, "rules_of", lambda ch: r)
    monkeypatch.setattr(ap, "_tone", lambda p, t: "calme")


def test_a_darija_channel_only_gets_moroccan_voices_but_keeps_its_main_one(project):
    voice("main", "moroccan")
    voice("badr", "moroccan", gender="male")
    voice("abdullah", "modern standard", gender="male")
    voice("hamid", "moroccan", gender="male")                       # not allowed by the channel

    ids = lambda **kw: [v["voice_id"] for v in vc.eligible("ar", "main", ["badr", "abdullah"], **kw)]

    assert ids(dialect=None) == ["main", "abdullah", "badr"]          # the main one first
    assert ids(dialect="darija") == ["main", "badr"]


def test_the_ai_keeps_the_main_voice_unless_it_says_why_and_sets_each_sentence_s_manner(project, monkeypatch):
    for v in ("main", "badr", "abdullah"):
        voice(v)
    rules(monkeypatch)
    t = target()
    g = G({"voix": "badr", "pourquoi": "une histoire d'homme", "manieres": ["serieux", "", "klingon"]})

    vc.cast({"recit": "news"}, t, gemini=g)

    assert t["voice_id"] == "badr" and t["voice_by"] == "ia" and t["voice_why"] == "une histoire d'homme"
    assert t["manieres"] == ["serieux", "", ""] and "★ main" in g.prompts[0]
    t2 = target()
    vc.cast({}, t2, gemini=G({"voix": "inconnue", "manieres": []}))      # a voice not allowed: the main one
    assert t2["voice_id"] == "main" and t2["manieres"] == ["", "", ""]


def test_always_the_main_voice_and_the_person_s_choices_are_kept(project, monkeypatch):
    for v in ("main", "badr"):
        voice(v)
    rules(monkeypatch, mode="principale")
    t = target(voice_id="other")
    vc.cast({}, t, gemini=G({"voix": "badr", "manieres": ["chuchote", "", ""]}))
    assert t["voice_id"] == "main" and t["voice_by"] == "principale" and t["manieres"][0] == "chuchote"

    rules(monkeypatch)
    mine = target(voice_id="badr", voice_by="toi", manieres=["", "triste", ""], manieres_by="toi")
    vc.cast({}, mine, gemini=G({"voix": "main", "manieres": ["excite", "", ""]}))
    assert mine["voice_id"] == "badr" and mine["manieres"] == ["", "triste", ""]


def test_the_tags_are_said_to_elevenlabs_never_shown_in_the_captions():
    assert vc.tagged("bonjour", "chuchote") == "[whispers] bonjour" and vc.tagged("bonjour", "") == "bonjour"
    v = {"duration": 3.0,
         "words": [{"w": "[serious]", "start": 0.0, "end": 0.0}, {"w": "un", "start": 0.1, "end": 0.4},
                   {"w": "deux", "start": 0.5, "end": 0.9}, {"w": "[whispers]", "start": 1.0, "end": 1.0},
                   {"w": "trois", "start": 1.2, "end": 1.6}],
         "passages": [{"texte": "[serious] un deux", "start": 0.0, "end": 0.9, "words": [0, 1, 2]},
                      {"texte": "[whispers] trois", "start": 1.0, "end": 1.6, "words": [3, 4]}]}

    out = vc.strip_tags(v, ["un deux", "trois"])

    assert [w["w"] for w in out["words"]] == ["un", "deux", "trois"]
    assert [p["words"] for p in out["passages"]] == [[0, 1], [2]] and out["passages"][1]["start"] == 1.2
    assert [p["texte"] for p in out["passages"]] == ["un deux", "trois"]


def test_the_person_changes_the_voice_on_the_script_screen_only_in_the_channel_s_language(project):
    voice("main")
    voice("fr_voice", lang="fr")
    voice("badr", "moroccan")
    ap.save({"project_id": "ad_v", "status": "plan_review", "targets": [target()]})

    t = vc.set_casting("ad_v", "chanA", "badr", ["", "chuchote", "", "en trop"])["targets"][0]

    assert t["voice_id"] == "badr" and t["voice_by"] == "toi" and t["manieres"] == ["", "chuchote", ""]
    import pytest
    with pytest.raises(ap.PipelineError):
        vc.set_casting("ad_v", "chanA", "fr_voice")


def test_a_channel_s_voice_rules_are_cleaned():
    s = settings.channel_settings({"language_hint": "ar", "adaptation": {"voix_permises": ["a", "", 3], "voix_mode": "x"}})
    assert s["voix_permises"] == ["a"] and s["voix_mode"] == "auto"
    assert settings.clean_update({"voix_mode": "principale", "voix_permises": ["a", "a", " b "]}) == \
        {"voix_mode": "principale", "voix_permises": ["a", "b"]}
