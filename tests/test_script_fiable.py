"""A reliable script (Ouahbi news, 2026-11-08): every sentence checked against the verified facts after every rewrite
(fixed once, else marked and blocking), the hook keeping its key number, a neutral news, and the manners a family
allows (no whispered news, no [excited] sanction), two at most."""

import pytest

from adaptation import pipeline as ap
from adaptation import recits
from adaptation import storyboard as sb
from adaptation import voix_casting as vc

FACTS = ["Seuls 10 a 11 fonctionnaires sur 160 viennent travailler aux tribunaux de Laayoune.",
         "Les cameras de surveillance n'ont pas pu etre utilisees (vie privee, securite incendie).",
         "Le syndicat dit que les fonctionnaires ont traite 116 203 dossiers en trois ans."]


def bundle(*texts):
    plans = [{"role": "accroche" if k == 0 else "montee", "image": "un bureau vide dans un tribunal marocain",
              "plans_modele": [], "annotation": None, "textes": {"fr": {"bandeau": "B", "texte": t, "mots_cles": []}}}
             for k, t in enumerate(texts)]
    return {"plans": plans, "meta": {"fr": {"titre": "T", "description": "D", "tags": []}}}


class G:
    def __init__(self, *answers):
        self.answers, self.prompts = list(answers), []

    def _generate_content(self, parts, **kw):
        self.prompts.append(parts[0]["text"])
        return self.answers.pop(0) if self.answers else {}


def test_the_check_finds_a_sentence_that_contradicts_the_facts_in_one_call():
    b = bundle("Seuls 10 sur 160 viennent travailler.", "Ils ont trompe les cameras de surveillance.")
    g = G({"fautes": [{"plan": 2, "langue": "fr", "quoi": "les cameras n'ont pas pu etre utilisees"},
                      {"plan": 9, "langue": "fr", "quoi": "plan inconnu"}]})

    found = sb.fact_check(b, ["fr"], FACTS, gemini=g)

    assert found == {(1, "fr"): "les cameras n'ont pas pu etre utilisees"} and len(g.prompts) == 1
    assert "cameras de surveillance n'ont pas pu" in g.prompts[0]
    assert sb.fact_check(b, ["fr"], [], gemini=g) == {}                        # no facts: nothing to check against


def test_a_fault_left_is_marked_on_its_plan_and_blocks_the_approval():
    b = sb.mark_facts(bundle("Seuls 10 sur 160.", "Ils ont trompe les cameras."), {(1, "fr"): "les cameras"})

    assert any("absente des faits" in x and "Plan 2" in x for x in sb.problems(b, "fr"))
    assert not any("absente des faits" in x for x in sb.problems(sb.mark_facts(b, {}), "fr"))   # cleared once right


def test_a_wrong_sentence_is_fixed_once_and_kept_only_if_it_has_fewer_faults(monkeypatch):
    b = bundle("Seuls 10 sur 160.", "Ils ont trompe les cameras.")
    good = bundle("Seuls 10 sur 160.", "Les cameras n'ont pas pu etre utilisees.")
    checks = iter([{(1, "fr"): "cameras"}, {}])
    monkeypatch.setattr(sb, "fact_check", lambda bb, codes, facts, gemini=None: next(checks))
    asked = []
    monkeypatch.setattr(sb, "revise", lambda bb, codes, req, gemini=None: asked.append(req) or {**good, "corrections": []})

    out = ap._checked_facts(b, ["fr"], FACTS)

    assert "trompe" not in out["plans"][1]["textes"]["fr"]["texte"] and "hors_faits" not in out["plans"][1]
    assert "plan 2 [fr] : cameras" in asked[0] and any("Faits vérifiés" in c for c in out["corrections"])

    checks = iter([{(1, "fr"): "cameras"}, {(1, "fr"): "cameras"}])          # the fix did not help: the mark stays
    out = ap._checked_facts(b, ["fr"], FACTS)
    assert out["plans"][1]["hors_faits"] == {"fr": "cameras"}


def test_a_fact_fix_is_told_the_length_limit_and_shortened_again_if_it_got_too_long(monkeypatch):
    # 2026-11-12, the flamingos: the fact fix wrote 7.2 s sentences after the length checks, nothing measured them
    long_ = "Mais pour nourrir le poussin, le parent regurgite un lait rouge vif puise dans ses propres reserves de pigments."
    b = bundle("Seuls 10 sur 160.", "Ils ont trompe les cameras.", "Fin.")
    too_long = bundle("Seuls 10 sur 160.", long_ + " " + long_, "Fin.")
    short = bundle("Seuls 10 sur 160.", "Les cameras n'ont pas pu etre utilisees.", "Fin.")
    checks = iter([{(1, "fr"): "cameras"}, {}, {}])
    monkeypatch.setattr(sb, "fact_check", lambda bb, codes, facts, gemini=None: next(checks))
    answers, asked = iter([too_long, short]), []
    monkeypatch.setattr(sb, "revise", lambda bb, codes, req, gemini=None: asked.append(req) or {**next(answers), "corrections": []})

    out = ap._checked_facts(b, ["fr"], FACTS)

    assert "plan 2 [fr] :" in asked[0] and "caracteres au plus" in asked[0]          # the limit given with the fix
    assert "trop longue" in asked[1] and "garde exactement ses faits" in asked[1]
    assert not any("longue" in x for x in sb.problems(out, "fr"))
    assert out["plans"][1]["textes"]["fr"]["texte"].startswith("Les cameras")


def test_the_hook_keeps_its_key_number_and_the_news_stays_neutral():
    assert "chiffre frappant" in sb.LENGTH_FIX
    news = recits.part("news")
    assert "chiffre frappant" in news and "autre version" in news and "une annonce reste une annonce" in news
    assert "INFORMATION NEUTRE" not in recits.part("pov")                    # only the news family


def test_a_news_channel_never_whispers_nor_gets_excited_and_two_manners_at_most():
    news = vc.manieres_for({"recit": "news"})
    assert "chuchote" not in news and "excite" not in news and "serieux" in news
    assert "chuchote" in vc.manieres_for({"recit": "mystere"})
    assert vc.clean_manieres(["serieux", "", "chuchote", "calme", "excite", "calme"], news, 6) == \
        ["serieux", "", "", "calme", "", ""]


def test_the_ai_s_manners_are_kept_to_the_family_s(monkeypatch, project):
    monkeypatch.setattr(vc, "rules_of", lambda ch: {"main": "m", "allowed": [], "mode": "principale", "dialect": None,
                                                    "language": "ar"})
    monkeypatch.setattr(ap, "_tone", lambda p, t: "calme")
    t = {"channel": "c", "language": "ar", "voice_id": "m",
         "script": {"passages": [{"texte": x} for x in "abcdef"]}}
    g = G({"manieres": ["serieux", "", "", "", "chuchote", "excite"]})

    vc.cast({"recit": "news"}, t, gemini=g)

    assert t["manieres"] == ["serieux", "", "", "", "", ""]
    assert '"chuchote"' not in g.prompts[0] and '"serieux"' in g.prompts[0]


def test_the_person_cannot_pick_a_manner_the_family_forbids(project):
    ap.save({"project_id": "ad_n", "status": "plan_review", "recit": "news", "famille_recit": "actualite",
             "targets": [{"channel": "chanA", "language": "ar", "voice_id": "m",
                          "script": {"passages": [{"texte": "a"}, {"texte": "b"}]}}]})
    with pytest.raises(ap.PipelineError):
        vc.set_casting("ad_n", "chanA", manieres=["", "chuchote"])
    assert vc.set_casting("ad_n", "chanA", manieres=["serieux", ""])["targets"][0]["manieres"] == ["serieux", ""]



def test_every_sentence_gets_a_verdict_and_every_fault_comes_back_at_once():
    b = bundle("Seuls 10 sur 160 viennent.", "Ils ont trompe les cameras.", "Ils ont traite 200 000 dossiers.")
    g = G({"verdicts": [{"plan": 1, "langue": "fr", "ok": True, "quoi": ""},
                        {"plan": 2, "langue": "fr", "ok": False, "quoi": "les cameras n'ont pas pu etre utilisees"},
                        {"plan": 3, "langue": "fr", "ok": False, "quoi": "116 203 dossiers, pas 200 000"}]})

    found = sb.fact_check(b, ["fr"], FACTS, gemini=g)

    assert set(found) == {(1, "fr"), (2, "fr")} and len(g.prompts) == 1
    assert "UNE PAR UNE" in g.prompts[0] and "(3 verdicts)" in g.prompts[0]


def test_faults_left_after_a_first_fix_get_a_second_one(monkeypatch):
    b = bundle("Seuls 10 sur 160.", "Ils ont trompe les cameras.", "200 000 dossiers.")
    checks = iter([{(1, "fr"): "cameras", (2, "fr"): "dossiers"}, {(2, "fr"): "dossiers"}, {}])
    monkeypatch.setattr(sb, "fact_check", lambda bb, codes, facts, gemini=None: next(checks))
    asked = []
    monkeypatch.setattr(sb, "revise", lambda bb, codes, req, gemini=None: asked.append(req) or {**bb, "corrections": []})

    out = ap._checked_facts(b, ["fr"], FACTS)

    assert len(asked) == 2 and "plan 2 [fr] : cameras ; plan 3 [fr] : dossiers" in asked[0]
    assert not any("hors_faits" in p for p in out["plans"])


def test_a_request_to_the_ai_sees_the_facts_and_its_fact_faults_are_fixed(project, monkeypatch):
    # 2026-11-12: « raccourcis l'accroche » wrote « tout blanc » again (the facts say « pâlit »), only marked in red
    ap.save({"project_id": "ad_f", "status": "plan_review", "mode": "script", "storyboard": bundle("A.", "B.", "C."),
             "reference": {"origine": "idee", "faits": FACTS}, "targets": [{"channel": "c", "language": "fr"}]})
    asked = []
    monkeypatch.setattr(sb, "revise", lambda bb, codes, req, gemini=None: asked.append(req) or {**bb, "corrections": []})
    fixed = []
    monkeypatch.setattr(ap, "_checked_facts", lambda bb, codes, facts, extra=None: fixed.append(facts) or bb)

    ap.revise_plan("ad_f", "c", "raccourcis l'accroche")

    assert "Faits verifies" in asked[0] and "10 a 11 fonctionnaires" in asked[0] and fixed == [FACTS]
