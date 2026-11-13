"""A darija narration's numbers said in darija words (2026-11-13: the user's blind test, numbers in words 4/5 then
9/10 against 3/5 with digits); the captions keep the digits."""

import base64

import pytest

from adaptation import nombres_darija as nd
from adaptation import voices


@pytest.mark.parametrize("n, said", [
    (0, "صفر"), (1, "واحد"), (2, "جوج"), (3, "تلاتة"), (8, "تمنية"), (9, "تسعود"), (10, "عشرة"), (11, "حداش"),
    (12, "طناش"), (15, "خمسطاش"), (19, "تسعطاش"), (20, "عشرين"), (21, "واحد وعشرين"), (22, "تنين وعشرين"),
    (29, "تسعة وعشرين"), (99, "تسعة وتسعين"), (100, "مية"), (102, "مية وجوج"), (110, "مية وعشرة"),
    (200, "ميتين"), (350, "تلتمية وخمسين"), (430, "ربعمية وتلاتين"), (1000, "ألف"), (1400, "ألف وربعمية"),
    (1889, "ألف وتمنمية وتسعة وتمانين"), (2000, "ألفين"), (2029, "ألفين وتسعة وعشرين"), (3000, "تلت آلاف"),
    (10000, "عشر آلاف"), (20000, "عشرين ألف"), (115000, "مية وخمسطاش ألف"), (1000000, "مليون"),
    (2000000, "جوج ملايين"), (10000000, "عشرة ملايين"), (11000000, "حداش مليون"), (110000000, "مية وعشرة مليون"), (5000000000, "خمسة مليار"),
])
def test_whole_numbers(n, said):
    assert nd.words(n) == said


@pytest.mark.parametrize("written, said", [
    ("3,5", "تلاتة ونص"), ("0,5", "نص"), ("2,5%", "جوج ونص فالمية"), ("3,25", "تلاتة فاصلة خمسة وعشرين"), ("5,000", "خمس آلاف"), ("115.000", "مية وخمسطاش ألف"), ("30%", "تلاتين فالمية"),
    ("%", "فالمية"), ("ف2029", "فألفين وتسعة وعشرين"), ("ل110", "لمية وعشرة"), ("٢٠٢٩", "ألفين وتسعة وعشرين"),
    ("0,05", "صفر فاصلة صفر خمسة"),
])
def test_written_numbers(written, said):
    assert nd.token(written) == said


@pytest.mark.parametrize("written", ["07", "14:30", "2-1", "m³", "البراق", "km", "12345678901234"])
def test_what_is_not_a_plain_number_is_left_alone(written):
    assert nd.token(written) is None


@pytest.mark.parametrize("text, said, sizes", [
    ("11 000 عامل", "حداش ألف عامل", [2, 0, 1]),                    # thousands written apart: one number
    ("3 000 شجرة", "تلت آلاف شجرة", [2, 0, 1]),
    ("1 500 000 مسافر", "مليون وخمسمية ألف مسافر", [3, 0, 0, 1]),
    ("2 مليون مسافر", "جوج ملايين مسافر", [1, 1, 1]),               # « ملايين » after 2 to 10
    ("11 مليون", "حداش مليون", [1, 1]),
    ("5 ألف", "خمسة آلاف", [1, 1]),
    ("3 كلم", "تلاتة كيلومتر", [1, 1]),                              # the short units said in full
    ("1400 م.", "ألف وربعمية متر.", [2, 1]),
    ("3كلم", "تلاتة كيلومتر", [2]),
    ("110 م³ ديال التراب", "مية وعشرة متر مكعب ديال التراب", [2, 2, 1, 1]),
    ("20 كلغ", "عشرين كيلو", [1, 1]),
    ("350 كلم/س", "تلتمية وخمسين كيلومتر فالساعة", [2, 2]),
    ("في 2029 م", "في ألفين وتسعة وعشرين م", [1, 3, 1]),             # « م » after a year: a date, not a metre
    ("م وصافي", "م وصافي", [1, 1]),
])
def test_numbers_with_their_neighbours(text, said, sizes):
    from adaptation import prononciation as pr
    assert pr.apply(text, "ar", {}, nd.reading) == (said, sizes)


def _fake_elevenlabs(monkeypatch, sent):
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


def test_a_darija_voice_hears_words_and_the_captions_keep_the_digits(project, monkeypatch, tmp_path):
    sent = {}
    _fake_elevenlabs(monkeypatch, sent)
    v = voices.synthesize([{"texte": "غيحفر 110 مليون متر."}, {"texte": "من 2029."}], "vid", "ar",
                          str(tmp_path / "v.mp3"), dialect="darija")
    assert sent["text"] == "غيحفر مية وعشرة مليون متر. من ألفين وتسعة وعشرين."
    assert [w["w"] for w in v["words"]] == ["غيحفر", "110", "مليون", "متر.", "من", "2029."]
    assert v["passages"][1]["words"] == [4, 5]


def test_a_number_written_in_groups_keeps_its_written_words_in_the_captions(project, monkeypatch, tmp_path):
    sent = {}
    _fake_elevenlabs(monkeypatch, sent)
    v = voices.synthesize([{"texte": "خدمو 11 000 عامل."}], "vid", "ar", str(tmp_path / "v.mp3"), dialect="darija")
    assert sent["text"] == "خدمو حداش ألف عامل."
    assert [w["w"] for w in v["words"]] == ["خدمو", "11", "000", "عامل."]
    assert v["words"][2]["start"] == v["words"][1]["end"]          # « 000 » said with « 11 »


@pytest.mark.parametrize("lang, dialect", [("ar", None), ("ar", "fusha"), ("fr", "darija")])
def test_other_voices_keep_the_digits(project, monkeypatch, tmp_path, lang, dialect):
    sent = {}
    _fake_elevenlabs(monkeypatch, sent)
    voices.synthesize([{"texte": "110 2029"}], "vid", lang, str(tmp_path / "v.mp3"), dialect=dialect)
    assert sent["text"] == "110 2029"


def test_the_pipelines_give_the_channel_dialect_to_the_voice(project, monkeypatch):
    from adaptation import montage_pro as mp
    got = {}
    monkeypatch.setattr(voices, "synthesize", lambda *a, **k: got.update(k) or {"words": [], "passages": [{"words": []}]})
    t = {"voice_id": "v", "language": "ar", "dialecte": "darija", "channel": "c",
         "script": {"passages": [{"texte": "2"}]}}
    mp._voice({}, t, "nouveau.mp3", lambda *a: None, 0)
    assert got["dialect"] == "darija"
