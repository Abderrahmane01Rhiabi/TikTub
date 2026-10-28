"""The two guards of the storyboard's automatic fix: its voice must fit 25-35 s (measured: Gemini's fixes ran
38 to 48 s in 5 cases out of 5, RESULTATS_MODELES.md), and a number of the draft must not vanish or lose its
unit ("35 grammes par kilogramme" became "35 grammes")."""

import json

from adaptation import pipeline as ap
from adaptation import storyboard as sb
from test_adaptation_storyboard import GOOD, fakes, new_project, plan  # noqa: F401  (fakes: the fixture)

LONG = "Le conducteur garde une main sur la manette et surveille les quais pendant toute la traversée."


def long_bundle(codes):
    b = json.loads(json.dumps(GOOD))
    b["plans"].append(plan("montee", "un quai bondé au petit matin en hiver", LONG, "ركاب كثيرون على الرصيف"))
    for p in b["plans"][1:]:
        p["textes"]["fr"]["texte"] = LONG
    return sb.normalise(b, codes)


def total(b, code="fr"):
    return sum(sb.seconds(p["textes"][code]["texte"], code) for p in b["plans"])


def test_a_storyboard_too_long_is_asked_with_a_length_per_plan_then_once_more_firmly(project, fakes, monkeypatch):
    monkeypatch.setattr(sb, "write", lambda ref, codes, angle=None: long_bundle(codes))
    asked = []

    def revise(b, codes, request):
        asked.append(request)
        out = json.loads(json.dumps(b))
        if request.startswith(sb.LENGTH_FIX[:20]):                  # only the firm request shortens
            for p in out["plans"][1:]:
                p["textes"]["fr"]["texte"] = "Il surveille les quais pendant la traversée."
        return out
    monkeypatch.setattr(sb, "revise", revise)
    assert total(long_bundle(["fr", "ar"])) > sb.TOTAL_S[1]
    p = new_project(project)
    ap.run_analysis(p["project_id"])
    p = ap.load(p["project_id"])
    assert "caracteres au plus" in asked[0] and "plan 2 :" in asked[0]           # the length of each plan, from the start
    assert len(asked) == 2 and asked[-1].startswith(sb.LENGTH_FIX[:20])          # then once more, firmly
    assert total(p["storyboard"]) <= sb.TOTAL_S[1]
    assert p["storyboard"]["corrections"][-1].startswith("Correction automatique : durée")


def test_still_too_long_after_the_firm_request_the_best_is_kept_and_the_warning_stays(project, fakes, monkeypatch):
    monkeypatch.setattr(sb, "write", lambda ref, codes, angle=None: long_bundle(codes))
    asked = []
    monkeypatch.setattr(sb, "revise", lambda b, codes, request: asked.append(request) or json.loads(json.dumps(b)))
    p = new_project(project)
    ap.run_analysis(p["project_id"])
    p = ap.load(p["project_id"])
    assert len(asked) == 2                                                       # never more than one firm request
    assert any("Durée totale" in x for x in p["targets"][0]["problems"])          # the usual warning


def test_a_storyboard_of_the_right_length_gets_no_length_request(project, fakes):
    p = new_project(project)
    ap.run_analysis(p["project_id"])
    assert not any("caracteres au plus" in r for r in fakes["revise"])
    assert sb.length_budgets(ap.load(p["project_id"])["storyboard"], ["fr", "ar"]) == ""
