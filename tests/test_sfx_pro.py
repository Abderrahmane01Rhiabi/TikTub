"""The montage pro's sound effects (2026-11-08): the library's sounds (Réglages → Effets sonores) on the story's real
moments — the hook, the answer, a figure, the start of the story — as many as the family wants, never over a
whisper (one same whoosh on every sentence before, and over the orcas' whisper)."""

from adaptation import montage_pro as mp
from adaptation import sfx

ROLES = ["accroche", "promesse", "montee", "montee", "montee", "reponse"]


def voice(n=6, step=4.0):
    return {"passages": [{"start": k * step, "end": k * step + 3.5} for k in range(n)]}


def passages(*banners):
    return [{"texte": "x", "bandeau": b} for b in banners]


def test_the_story_s_moments_get_their_sound_and_a_reveal_its_ding():
    ms = mp.sound_moments(voice(), passages("A", "B", "700 BATEAUX", "C", "D", "E"), ROLES, "mystere", [], 24.0)
    assert [(m["t"], m["sons"], m["pourquoi"]) for m in ms] == [
        (0.0, ["impact"], "accroche"), (20.0, ["ding"], "révélation"), (8.05, ["pop"], "chiffre"),
        (4.0, ["whoosh"], "le récit commence")]
    plain = mp.sound_moments(voice(), passages(*"ABCDEF"), ROLES, "explication", [], 24.0)
    assert ["whoosh"] == next(m["sons"] for m in plain if m["pourquoi"] == "la réponse")    # no ding without a reveal


def test_arabic_digits_count_as_a_figure_and_nothing_sounds_over_a_whisper():
    ms = mp.sound_moments(voice(), passages("A", "B", "٧٠٠ قارب", "C", "D", "E"), ROLES, "mystere", [], 24.0)
    assert any(m["pourquoi"] == "chiffre" for m in ms)
    hushed = mp.sound_moments(voice(), passages(*"ABCDEF"), ROLES, "mystere", ["", "", "", "", "", "chuchote"], 24.0)
    assert not any(m["pourquoi"] == "révélation" for m in hushed)


def test_the_family_keeps_as_many_as_it_wants_and_the_sounds_turned_off_are_left_out(monkeypatch):
    lib = {"impact": ["/i.mp3"], "whoosh": ["/w.mp3"], "pop": ["/p.mp3"], "ding": ["/d.mp3"]}
    monkeypatch.setattr(sfx, "library", lambda folder=None: lib)
    monkeypatch.setattr(sfx, "peak_of", lambda path: 0.0)
    t = {"voice": voice(), "script": {"passages": passages("A", "B", "700", "C", "D", "E")}, "manieres": []}
    p = {"recit": "mystere", "storyboard": {"plans": [{"role": r} for r in ROLES]}}

    assert [e["kind"] for e in mp.sound_effects({**p, "famille_recit": "explicatif"}, t)] == \
        ["impact", "whoosh", "pop", "ding"]
    assert [e["kind"] for e in mp.sound_effects({**p, "famille_recit": "actualite", "recit": "news"}, t)] == \
        ["pop", "whoosh"]                                                                # news: sober, no impact
    del lib["impact"]                                                                    # turned off in Réglages
    assert "impact" not in [e["kind"] for e in mp.sound_effects({**p, "famille_recit": "explicatif"}, t)]


def test_a_hook_with_a_figure_pops_when_the_impact_is_turned_off():
    def hook(on):
        ms = mp.sound_moments(voice(), passages("700 ATTAQUES", *"BCDEF"), ROLES, "mystere", [], 24.0)
        return [m["sons"] for m in sfx.keep(ms, 24.0, 4, None, on) if m["t"] < 1]
    assert hook({"pop", "ding", "whoosh"}) == [["pop"]]
    assert hook({"impact", "pop"}) == [["impact"]]
