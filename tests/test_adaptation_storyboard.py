"""'Script d'abord': the storyboard written before any footage — one image per
plan shared by every language, texts per language, retention rules, review."""

import json
from pathlib import Path

import pytest

from adaptation import pipeline as ap
from adaptation import storyboard as sb


def plan(role, image, fr, ar=None, ref=(1,)):
    t = {"fr": {"bandeau": "B : X 😐", "texte": fr, "mots_cles": [fr.split()[0]]}}
    if ar is not None:
        t["ar"] = {"bandeau": "ب", "texte": ar, "mots_cles": []}
    return {"role": role, "image": image, "plans_modele": list(ref), "textes": t}


GOOD = {"plans": [
    plan("accroche", "un tram percute une voiture vue cabine", "Pourquoi ce tram ne freine pas ?", "لماذا لا يفرمل؟"),
    plan("promesse", "le conducteur reste calme dans sa cabine", "La raison est bien plus subtile qu'on ne le croit.", "السبب الحقيقي أدق بكثير مما نظن جميعا في البداية."),
    plan("montee", "des roues en acier glissent sur les rails", "Quarante tonnes d'acier ne s'arrêtent jamais net sur des rails mouillés.", "أربعون طنا من الحديد لا تتوقف فجأة على القضبان."),
    plan("montee", "des passagers debout se tiennent aux barres", "Un freinage brutal ferait tomber tous les passagers debout dans la rame.", "الكبح العنيف يسقط كل الركاب الواقفين داخل العربة."),
    plan("montee", "un carrefour où les voitures attendent le tram", "Et sur ses rails, le tram garde la priorité sur les voitures.", "وعلى قضبانه، يملك الترام الأولوية على السيارات."),
    plan("reponse", "le visage serein du conducteur dans la cabine", "Son calme n'est pas de l'indifférence : il protège d'abord ses voyageurs.", "هدوؤه ليس لامبالاة أبدا، بل هو حماية لركابه قبل كل شيء آخر.")],
    "meta": {"fr": {"titre": "Pourquoi ?", "description": "d", "tags": ["tram"]},
             "ar": {"titre": "لماذا", "description": "و", "tags": ["ترام"]}}}


def test_normalise_keeps_every_language_and_computes_how_long_each_image_must_be():
    out = sb.normalise(json.loads(json.dumps({**GOOD, "plans": GOOD["plans"] + [{"role": "x", "textes": {}}]})), ["fr", "ar"])
    assert len(out["plans"]) == 6                              # an empty plan is dropped
    assert out["plans"][0]["duree"] == round(max(sb.seconds("Pourquoi ce tram ne freine pas ?", "fr"),
                                                 sb.seconds("لماذا لا يفرمل؟", "ar")) + 0.3, 1)
    assert sb.normalise({"plans": [{"role": "Montée", "image": "x", "textes": {"fr": {"texte": "a"}}}]}, ["fr"])["plans"][0]["role"] == "montee"
    with pytest.raises(Exception):
        sb.normalise({"error": "quota"}, ["fr"])
    s = sb.script_for(out, "ar")
    assert s["titre"] == "لماذا" and s["passages"][0]["texte"] == "لماذا لا يفرمل؟" and s["passages"][0]["clip"] == ""


def test_problems_guard_the_retention_rules():
    b = sb.normalise(json.loads(json.dumps(GOOD)), ["fr", "ar"])
    assert sb.problems(b, "fr") == [] and sb.problems(b, "ar") == []
    b["plans"][0]["textes"]["fr"]["texte"] = "Pourquoi les conducteurs de tramway restent-ils impassibles face à un crash ?"
    b["plans"][5]["textes"]["fr"]["texte"] = "Mais au fait..."
    b["plans"][3]["image"] = b["plans"][2]["image"]
    b["plans"][4]["image"] = "un tram"
    found = " | ".join(sb.problems(b, "fr"))
    assert "accroche trop longue" in found and "« … »" in found and "même image que le plan 3" in found
    assert "décris l'image voulue" in found


def test_the_writer_gets_the_model_plans_the_languages_and_the_ad():
    seen = {}

    class G:
        def _generate_content(self, parts, **kw):
            seen["prompt"] = parts[0]["text"]
            return json.loads(json.dumps(GOOD))
    ref = {"sujet": "trams", "question": "pourquoi", "publicite": "aucune marque",
           "plans": [{"role": "accroche", "visuel": "tram percute voiture", "paroles": "Why?"}]}
    out = sb.write(ref, ["fr", "ar"], gemini=G())
    assert "1. [accroche] tram percute voiture" in seen["prompt"] and "- ar (" in seen["prompt"]
    assert "JUSQU'A LA FIN" in seen["prompt"] and '"fr": {"bandeau"' in seen["prompt"]
    assert len(out["plans"]) == 6


def test_critique_keeps_the_bundle_when_it_breaks_it():
    b = sb.normalise(json.loads(json.dumps(GOOD)), ["fr"])

    class Broken:
        def _generate_content(self, parts, **kw): return {"plans": [GOOD["plans"][0]], "meta": {}}
    assert sb.critique(b, ["fr"], gemini=Broken())["plans"] == b["plans"]


# ---------------------------------------------------------------- the project

@pytest.fixture
def fakes(monkeypatch):
    from adaptation import reference
    calls = {"write": 0, "revise": []}
    monkeypatch.setattr(reference, "analyse", lambda url: {"sujet": "trams", "question": "pourquoi", "plans": [{}]})

    def write(ref, codes):
        calls["write"] += 1
        b = json.loads(json.dumps(GOOD))
        b["plans"][0]["textes"]["fr"]["texte"] = "Pourquoi les conducteurs de tramway restent-ils impassibles face à un crash ?"
        return sb.normalise(b, codes)
    monkeypatch.setattr(sb, "write", write)
    monkeypatch.setattr(sb, "critique", lambda b, codes: {**b, "corrections": ["relu"]})

    def revise(b, codes, request):
        calls["revise"].append(request)
        out = json.loads(json.dumps(b))
        out["plans"][0]["textes"]["fr"]["texte"] = "Pourquoi ce tram ne freine pas ?"
        return out
    monkeypatch.setattr(sb, "revise", revise)
    return calls


def channel(project, name, lang, voice):
    import db
    project.add_channel(name)
    (Path("channels") / name / "profile.json").write_text(json.dumps({"language_hint": lang, "adaptation": {"voice_id": voice}}))
    db.upsert_voice({"voice_id": voice, "name": voice, "language": lang})
    return {"channel": name, "profile": json.loads((Path("channels") / name / "profile.json").read_text()),
            "music_dir": str(Path("channels") / name / "assets" / "music")}


def new_project(project):
    return ap.create("https://youtube.com/shorts/x", ["https://ignored"], [channel(project, "chanA", "fr", "v_fr"),
                                                                         channel(project, "chanB", "ar", "v_ar")], mode="script")


def test_script_first_writes_one_storyboard_for_every_language(project, fakes):
    p = new_project(project)
    assert p["mode"] == "script" and p["source_urls"] == []
    ap.run_analysis(p["project_id"])
    p = ap.load(p["project_id"])
    assert p["status"] == "plan_review" and fakes["write"] == 1 and p["suggestions"] is None
    assert "accroche trop longue" in fakes["revise"][0]            # what the re-read missed: fixed once more
    assert p["storyboard"]["corrections"][-1].startswith("Correction automatique")
    a, b = p["targets"]
    assert a["problems"] == [] and b["problems"] == []
    assert a["script"]["passages"][0]["texte"] == "Pourquoi ce tram ne freine pas ?"
    assert b["script"]["passages"][0]["texte"] == "لماذا لا يفرمل؟"


def test_a_text_change_keeps_the_other_language_approved_but_an_image_change_does_not(project, fakes):
    pid = new_project(project)["project_id"]
    ap.run_analysis(pid)
    ap.approve_plan(pid, "chanA"); ap.approve_plan(pid, "chanB")
    p = ap.load(pid)
    fr = {**p["targets"][0]["script"], "passages": [{**x, "image": p["storyboard"]["plans"][k]["image"]}
                                                   for k, x in enumerate(p["targets"][0]["script"]["passages"])]}
    fr["passages"][1]["texte"] = "La raison est vraiment surprenante."
    p = ap.edit_plan(pid, "chanA", fr)
    assert [t["approved"] for t in p["targets"]] == [False, True]
    fr["passages"][2]["image"] = "un tramway freine d'urgence sous la pluie, vue de face"
    p = ap.edit_plan(pid, "chanA", fr)
    assert [t["approved"] for t in p["targets"]] == [False, False]
    assert p["targets"][1]["script"]["passages"][2]["texte"] == "أربعون طنا من الحديد لا تتوقف فجأة على القضبان."   # the Arabic text stays
    with pytest.raises(ap.PipelineError, match="nombre de plans"):
        ap.edit_plan(pid, "chanA", {**fr, "passages": fr["passages"][:3]})


def test_a_storyboard_with_problems_cannot_be_approved(project, fakes):
    pid = new_project(project)["project_id"]
    ap.run_analysis(pid)
    p = ap.load(pid)
    fr = {**p["targets"][0]["script"], "passages": [{**x, "image": p["storyboard"]["plans"][k]["image"]}
                                                   for k, x in enumerate(p["targets"][0]["script"]["passages"])]}
    fr["passages"][5]["texte"] = "Mais au fait..."
    ap.edit_plan(pid, "chanA", fr)
    with pytest.raises(ap.PipelineError, match="incomplète"):
        ap.approve_plan(pid, "chanA")
    p = ap.revise_plan(pid, "chanA", "termine sur la réponse")
    assert fakes["revise"][-1] == "termine sur la réponse"


def test_unknown_mode_and_api(client, project, fakes):
    with pytest.raises(ap.PipelineError):
        ap.create("https://x", [], [channel(project, "chanA", "fr", "v_fr")], mode="magie")
    import time
    r = client.post("/api/adaptations", json={"reference_url": "https://youtube.com/shorts/x", "channels": ["chanA"], "mode": "script"})
    assert r.status_code == 200 and r.json()["mode"] == "script"
    pid = r.json()["project_id"]
    for _ in range(50):
        if client.get(f"/api/adaptations/{pid}").json()["status"] != "analysing":
            break
        time.sleep(0.1)
    p = client.get(f"/api/adaptations/{pid}").json()
    assert p["status"] == "plan_review" and len(p["storyboard"]["plans"]) == 6 and p["storyboard"]["plans"][0]["duree"] > 0
    plan_ = {**p["targets"][0]["script"], "passages": [{**x, "image": p["storyboard"]["plans"][k]["image"]}
                                                      for k, x in enumerate(p["targets"][0]["script"]["passages"])]}
    assert client.put(f"/api/adaptations/{pid}/targets/chanA/plan", json={"plan": plan_}).status_code == 200
    assert client.post(f"/api/adaptations/{pid}/targets/chanA/plan/approve").json()["targets"][0]["approved"]
    assert client.post(f"/api/adaptations/{pid}/targets/chanA/plan/revise", json={"request": " "}).status_code == 400
