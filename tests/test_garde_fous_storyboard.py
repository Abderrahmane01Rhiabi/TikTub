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


# ---- numbers: a sourced number of the draft must not vanish nor lose its unit

def bundle(*plans, code="ar"):
    return {"plans": [{"image": img, "textes": {code: {"texte": t}}} for img, t in plans]}


SEA = ["تخفض نسبة الأملاح الذائبة في مياه البحر، والبالغة نحو 35 غراماً لكل كيلوغرام، درجة تجمدها من الصفر المئوي إلى نحو 1.9 درجة تحت الصفر."]
CAMEL = ["Pour compenser rapidement ses pertes hydriques, un spécimen déshydraté est capable d'ingurgiter jusqu'à 130 litres d'eau en à peine 10 minutes.",
         "Ses globules rouges ovales peuvent se dilater jusqu'à 240 % de leur volume initial sans éclater lors d'une réhydratation."]


def test_the_sea_ice_salt_that_lost_its_per_kilogram_is_caught():         # glace de mer, arabe (DeepSeek's fix)
    before = bundle(("أمواج متدفقة بقوة", "وجود خمسة وثلاثين غراماً من الملح في كل كيلوغرام يخفض درجة تجمد الماء إلى نحو 1.9 درجة تحت الصفر."))
    after = bundle(("مياه بحر قطبية", "ماء البحر يحتوي على 35 غراماً من الملح."), ("بلورات", "ويتجمد عند 1.9 درجة تحت الصفر."))
    lost = sb.lost_numbers(before, after, ["ar"], SEA)
    assert len(lost) == 1 and "35" in lost[0] and "كيلوغرام" in lost[0]


def test_the_camels_130_litres_become_more_than_100_is_caught():          # chameau, arabe (Gemini's re-read)
    before = bundle(("Un chameau buvant", "وحين يعثر على الماء، يشرب مئة وثلاثين لترا دفعة واحدة خلال عشر دقائق."))
    after = bundle(("Un chameau buvant", "وحين يصل إلى الماء، يشرب أكثر من مئة لتر دفعة واحدة في عشر دقائق."))
    assert len(sb.lost_numbers(before, after, ["ar"], CAMEL)) == 1


def test_a_fact_left_out_or_replaced_by_another_sourced_one_is_not_refused():
    before = bundle(("A", "كريات دمه تنتفخ حتى مئتين وأربعين بالمئة من حجمها."), ("B", "يفقد الجمل ثلاثين بالمئة من وزنه ماء."))
    after = bundle(("B", "يفقد الجمل ثلاثين بالمئة من وزنه ماء."), ("C", "يشرب كثيرا."))
    assert sb.lost_numbers(before, after, ["ar"], CAMEL + ["Il tolère 30 % de perte en eau."]) == []     # 240 % left out


def test_what_a_good_fix_does_is_not_refused():
    before = bundle(("A", "Il boit cent trente litres en dix minutes."), ("B", "Ses globules gonflent alors de 240 % sans éclater."),
                    ("C", "Il marche cinquante jours sans boire."), code="fr")
    moved = bundle(("B", "Ses globules gonflent de 240 %."), ("A", "En dix minutes, il avale 130 litres d'eau."), code="fr")
    assert sb.lost_numbers(before, moved, ["fr"], CAMEL) == []                 # moved, in digits, plan C deleted,
    assert sb.lost_numbers(before, before, ["fr"], CAMEL) == []                # 50 not a sourced number: free to go
    doubtful = bundle(("A", "Il boit deux cents litres."), code="fr")
    assert sb.lost_numbers(doubtful, bundle(("A", "Il boit énormément."), code="fr"), ["fr"], CAMEL) == []   # never sourced


def test_a_lost_number_is_sent_to_the_automatic_fix_once(project, fakes, monkeypatch):
    def write(ref, codes, angle=None):
        b = json.loads(json.dumps(GOOD))
        b["plans"][2]["textes"]["fr"]["texte"] = "Quarante tonnes d'acier freinent sur 120 mètres sous la pluie."
        return sb.normalise(b, codes)

    def critique(b, codes):
        out = json.loads(json.dumps(b))
        out["plans"][2]["textes"]["fr"]["texte"] = "Quarante tonnes d'acier freinent sur 100 mètres sous la pluie."
        return {**out, "corrections": ["relu"]}
    monkeypatch.setattr(sb, "write", write)
    monkeypatch.setattr(sb, "critique", critique)
    from adaptation import reference
    monkeypatch.setattr(reference, "analyse", lambda url: {"sujet": "trams", "question": "pourquoi", "plans": [{}],
                                                           "faits": ["Un tram de 40 tonnes freine sur 120 mètres sous la pluie."]})
    p = new_project(project)
    ap.run_analysis(p["project_id"])
    asked = [r for r in fakes["revise"] if "120" in r]
    assert len(asked) == 1 and "remets 120" in asked[0]                           # sent back once
