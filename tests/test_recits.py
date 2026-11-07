"""The narrative styles in one catalogue: a channel's family (and the styles it unticks), the AI's pick among
them for each video, a Reprise's genre respected, the person's change, and every script writer told the rule."""

import pytest

from adaptation import pipeline as ap
from adaptation import recits
from adaptation import settings


class G:
    def __init__(self, answer):
        self.answer, self.prompts = answer, []

    def _generate_content(self, parts, **kw):
        self.prompts.append(parts[0]["text"])
        return self.answer


def test_every_family_has_styles_with_a_rule_and_a_name():
    assert set(recits.FAMILLES) == {"actualite", "explicatif", "humour", "hype", "motivation", "satisfying"}
    for f in recits.FAMILLES.values():
        for name, (label, genre, rule) in f["styles"].items():
            assert label and rule and genre in (None, "top", "histoire")
            assert recits.part(name).startswith("STYLE DE RECIT IMPOSE")


def test_a_channel_chooses_its_family_and_its_look_decides_until_then():
    assert settings.channel_settings({"language_hint": "fr"})["famille_recit"] == "explicatif"
    assert settings.channel_settings({"language_hint": "ar", "adaptation": {"style": "actu"}})["famille_recit"] == "actualite"
    s = settings.channel_settings({"language_hint": "en", "adaptation": {"famille_recit": "humour",
                                                                          "styles_exclus": ["pov", "klingon"]}})
    assert s["famille_recit"] == "humour" and s["styles_exclus"] == ["pov"]


def test_the_ai_picks_among_the_allowed_styles_and_avoids_the_last_ones():
    g = G({"style": "pov"})                                       # unticked by the channel
    name = recits.choose({"sujet": "un chat"}, "humour", ["pov"], ["reaction"], gemini=g)

    assert "pov :" not in g.prompts[0].lower() and "chute" in g.prompts[0]
    assert name in recits.FAMILLES["humour"]["styles"] and name not in ("pov", "reaction")


def test_a_reprise_keeps_its_model_s_genre():
    assert set(recits.allowed("explicatif", genre="top")) == {"fait_surprenant", "explication", "top"}
    assert "top" not in recits.allowed("explicatif", genre="histoire")
    assert len(recits.allowed("explicatif", excluded=list(recits.FAMILLES["explicatif"]["styles"]))) == 5   # all unticked: all


def test_the_project_keeps_its_style_and_the_person_changes_it(project, monkeypatch):
    monkeypatch.setattr(recits, "channel_rules", lambda ch: {"famille": "hype", "exclus": []})
    monkeypatch.setattr(recits, "choose", lambda ref, fam, exc, rec, genre=None, gemini=None: "montee")
    p = {"targets": [{"channel": "chanA"}], "reference": {}}

    assert recits.for_project(p) == "montee" and p["famille_recit"] == "hype" and p["recit_par"] == "ia"
    assert recits.for_project({**p, "recit": "face_a_face"}) == "face_a_face"        # kept once chosen

    ap.save({"project_id": "ad_r", "status": "plan_review", "targets": [], "recit": "montee"})
    q = ap.change_recit("ad_r", "le_moment_ou")
    assert q["recit"] == "le_moment_ou" and q["recit_par"] == "toi" and q["status"] == "analysing"
    with pytest.raises(ap.PipelineError):
        ap.save({**q, "status": "plan_review"}) and ap.change_recit("ad_r", "klingon")


def test_sources_and_reprise_writers_are_told_the_style():
    from adaptation import reprise_montage as rm, script
    g = G({})
    with pytest.raises(Exception):
        script.write({"plans": []}, {}, "fr", gemini=g, recit=recits.part("vrai_faux"))
    assert "VRAI OU FAUX" in g.prompts[0]
    g2 = G({})
    with pytest.raises(Exception):
        rm.write_script({"plans": []}, ["fr"], gemini=g2, recit=recits.part("pov"))
    assert "POV" in g2.prompts[0] and "un top reste un top" in g2.prompts[0]
