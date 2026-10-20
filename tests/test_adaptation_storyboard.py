"""'Script d'abord': the storyboard written before any footage — one image per
plan shared by every language, texts per language, retention rules, review."""

import json
import os
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
    calls = {"write": 0, "revise": [], "reference": 0, "angles": [], "written_with": []}

    def analyse(url):
        calls["reference"] += 1
        return {"sujet": "trams", "question": "pourquoi", "plans": [{}]}
    monkeypatch.setattr(reference, "analyse", analyse)

    def angles(ref, n=3, avoid=None):
        calls["angles"].append(list(avoid or []))
        names = [x for x in ("Le test honnête", "Les 3 erreurs", "Ça vaut le coup ?", "Le secret") if x not in (avoid or [])]
        return [{"titre": t, "idee": "idée " + t} for t in names[:n]]
    monkeypatch.setattr(sb, "angles", angles)

    def write(ref, codes, angle=None):
        calls["write"] += 1
        calls["written_with"].append((angle or {}).get("titre"))
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


# ---------------------------------------------------------------- step 3: the footage, plan by plan

def test_plan_queries_and_wanted_scenes():
    from adaptation import finder

    class G:
        def _generate_content(self, parts, **kw):
            assert "1. un tram percute une voiture" in parts[0]["text"]
            return {"plans": [{"plan": 1, "anglais": ["tram hits car cab view", " "], "pays": "Biélorussie",
                               "langue": "Russe", "locales": ["трамвай авария"]}, {"plan": 9, "anglais": ["x"]}]}
    plans = [{"image": "un tram percute une voiture", "plans_modele": [1, 3]}, {"image": "le visage du conducteur", "plans_modele": []}]
    q = finder.plan_queries(finder.wanted_from_storyboard(plans, {}), gemini=G())
    assert q == {0: {"recherches": ["tram hits car cab view"], "pays": "Biélorussie", "langue": "Russe", "locales": ["трамвай авария"]}}
    w = finder.wanted_from_storyboard(plans, q)
    assert w[0] == {"scene": "un tram percute une voiture", "plans": [0, 2], "indices": "", "recherches": ["tram hits car cab view"]}
    assert w[1]["recherches"] == ["le visage du conducteur"] and w[1]["plans"] == []


def test_auto_pick_takes_the_best_level_and_never_the_same_moment_twice():
    from adaptation import finder
    v = lambda per: {"verdict": "oui", "par_scene": per, "title": "t"}
    sug = {"scenes": [{"candidats": [{"url": "A", "title": "Compilation"}]}], "verifs": {
        "A": v({"0": {"niveau": "exacte", "moments": [{"debut": 10, "fin": 14}]},
                "1": {"niveau": "exacte", "moments": [{"debut": 10, "fin": 14}, {"debut": 40, "fin": 49}]}}),
        "B": v({"0": {"niveau": "equivalente", "moments": [{"debut": 3, "fin": 20}]},
                "2": {"niveau": "partielle", "moments": [{"debut": 5}]}}),
        "C": v({"2": {"niveau": "rien", "moments": []}})}}
    picks = finder.auto_pick(sug, [{}, {}, {}, {}])
    assert (picks[0]["url"], picks[0]["moment"]) == ("A", {"debut": 10.0, "fin": 14.0}) and picks[0]["titre"] == "Compilation"
    assert (picks[1]["url"], picks[1]["moment"]["debut"]) == ("A", 40.0)       # 0:10 is taken by plan 1
    assert (picks[2]["url"], picks[2]["niveau"], picks[2]["moment"]) == ("B", "partielle", {"debut": 5.0, "fin": 8.0})
    assert picks[3] is None


def _approved_project(project, fakes):
    pid = new_project(project)["project_id"]
    ap.run_analysis(pid)
    for ch in ("chanA", "chanB"):
        ap.approve_plan(pid, ch)
    return pid


def test_searching_needs_every_script_approved_then_picks_a_moment_per_plan(project, fakes, monkeypatch):
    from adaptation import finder
    pid = new_project(project)["project_id"]
    ap.run_analysis(pid)
    ap.approve_plan(pid, "chanA")
    with pytest.raises(ap.PipelineError, match="chanB"):
        ap.start_images(pid)
    ap.approve_plan(pid, "chanB")
    seen = {}
    monkeypatch.setattr(finder, "plan_queries", lambda found: {0: {"recherches": ["tram crash"], "pays": "Russie",
                                                                    "langue": "Russe", "locales": ["трамвай"]}})

    def suggest(ref, url, work_dir=None, wanted=None, local=None, report=None, **kw):
        seen["wanted"], seen["local"] = wanted, local(wanted)
        return {"scenes": [{**w, "candidats": [{"url": "A", "title": "Compil"}]} for w in wanted], "comptes": [], "verifs": {}}
    monkeypatch.setattr(finder, "suggest", suggest)

    def verify_best(sug, ref, n, report=None):
        seen["n"], seen["plans"] = n, ref["plans"]
        sug["verifs"] = {"A": {"verdict": "oui", "par_scene": {"0": {"niveau": "exacte", "moments": [{"debut": 2, "fin": 6}]}}}}
        return sug
    monkeypatch.setattr(finder, "verify_best", verify_best)
    ap.start_images(pid)
    assert ap.load(pid)["status"] == "searching"
    ap.run_images(pid)
    p = ap.load(pid)
    assert p["status"] == "images_review" and seen["n"] == 12 and seen["plans"] == []     # judged against the images themselves
    assert seen["wanted"][0]["recherches"] == ["tram crash"] and seen["local"][0]["recherches"] == ["трамвай"]
    assert seen["wanted"][0]["scene"] == p["storyboard"]["plans"][0]["image"]
    assert p["picks"][0]["url"] == "A" and p["picks"][1] is None

    p = ap.choose_pick(pid, 1, "A", 30, 35)
    assert p["picks"][1] == {"url": "A", "titre": "Compil", "niveau": "choisie", "moment": {"debut": 30.0, "fin": 35.0},
                             "raison": "", "auto": False, "remontage": False, "defauts": ""}
    assert ap.choose_pick(pid, 0, None)["picks"][0] is None
    with pytest.raises(ap.PipelineError):
        ap.choose_pick(pid, 9, "A")


def test_a_failed_search_can_be_retried(project, fakes, monkeypatch):
    from adaptation import finder
    pid = _approved_project(project, fakes)
    monkeypatch.setattr(finder, "plan_queries", lambda found: (_ for _ in ()).throw(RuntimeError("Gemini HS")))
    ap.start_images(pid); ap.run_images(pid)
    p = ap.load(pid)
    assert p["status"] == "error" and p["failed_step"] == "searching"
    assert ap.retry(pid) == "searching"


def test_api_images_and_picks(client, project, fakes, monkeypatch):
    from adaptation import finder
    pid = _approved_project(project, fakes)
    monkeypatch.setattr(finder, "plan_queries", lambda found: {})
    monkeypatch.setattr(finder, "suggest", lambda *a, **k: {"scenes": [], "comptes": [], "verifs": {}})
    monkeypatch.setattr(finder, "verify_best", lambda sug, ref, n, report=None: sug)
    import time
    assert client.post(f"/api/adaptations/{pid}/images").status_code == 200
    for _ in range(50):
        if client.get(f"/api/adaptations/{pid}").json()["status"] != "searching":
            break
        time.sleep(0.1)
    p = client.get(f"/api/adaptations/{pid}").json()
    assert p["status"] == "images_review" and p["picks"] == [None] * 6
    r = client.put(f"/api/adaptations/{pid}/picks/2", json={"url": "https://youtu.be/aaaaaaaaaaa", "debut": 4})
    assert r.status_code == 200 and r.json()["picks"][2]["moment"] == {"debut": 4.0, "fin": 8.0}


def test_auto_pick_prefers_original_footage_to_someone_elses_re_edit():
    from adaptation import finder
    v = lambda lvl, remix: {"verdict": "oui", "remontage": remix, "par_scene": {"0": {"niveau": lvl, "moments": [{"debut": 1, "fin": 5}]}}}
    sug = {"verifs": {"remix": v("exacte", True), "orig": v("equivalente", False)}}
    assert finder.auto_pick(sug, [{}])[0]["url"] == "orig"
    sug = {"verifs": {"remix": v("exacte", True)}}
    pick = finder.auto_pick(sug, [{}])[0]
    assert pick["url"] == "remix" and pick["remontage"]                       # nothing else: taken, flagged


# ---------------------------------------------------------------- steps 4-5: your link, adapt, set aside, fetch

def _images_project(project, fakes, monkeypatch, picks=None):
    from adaptation import finder
    pid = _approved_project(project, fakes)
    ap.start_images(pid)
    monkeypatch.setattr(finder, "plan_queries", lambda found: {})
    monkeypatch.setattr(finder, "suggest", lambda ref, url, work_dir=None, wanted=None, local=None, report=None, **kw: {
        "scenes": [{**w, "candidats": [{"url": "https://www.youtube.com/watch?v=aaaaaaaaaaa", "title": "Compil", "duration": 600}]}
                   for w in wanted], "comptes": [], "verifs": {}})
    v = {"verdict": "oui", "title": "Compil", "duration": 600, "par_scene": {
        str(k): {"niveau": "exacte", "moments": [{"debut": 100 + 30 * k, "fin": 104 + 30 * k, "ce_qu_on_voit": f"moment {k}"}]}
        for k in range(5)}}
    monkeypatch.setattr(finder, "verify_best", lambda sug, ref, n, report=None: sug.update(
        verifs={"https://www.youtube.com/watch?v=aaaaaaaaaaa": v}) or sug)
    ap.run_images(pid)
    return pid


def test_set_aside_a_plan_and_your_link_for_a_plan(project, fakes, monkeypatch):
    pid = _images_project(project, fakes, monkeypatch)
    p = ap.load(pid)
    assert [bool(x) for x in p["picks"]] == [True] * 5 + [False]
    with pytest.raises(ap.PipelineError, match="Plans sans vidéo : 6"):
        ap.start_fetch(pid)
    tt = "https://www.tiktok.com/@a/video/1"
    p = ap.check_plan_link(pid, 5, tt, checker=lambda u, sc, pl: {"verdict": "oui", "title": "Mon TikTok", "par_scene": {
        "5": {"niveau": "equivalente", "moments": [{"debut": 2, "fin": 3}, {"debut": 8, "fin": 15}], "raison": "pareil"}}})
    assert p["picks"][5] == {"url": tt, "titre": "Mon TikTok", "niveau": "equivalente", "moment": {"debut": 8.0, "fin": 15.0},
                             "raison": "pareil", "auto": False}
    assert p["suggestions"]["scenes"][5]["candidats"][0]["origines"] == ["perso"]
    p = ap.skip_plan(pid, 5)
    assert p["storyboard"]["plans"][5]["retire"]
    for k in (4, 3):
        ap.skip_plan(pid, k)
    with pytest.raises(ap.PipelineError, match="au moins 3"):
        ap.skip_plan(pid, 2)
    assert not ap.skip_plan(pid, 5, skip=False)["storyboard"]["plans"][5]["retire"]


def test_a_plan_without_video_is_adapted_to_an_image_found(project, fakes, monkeypatch):
    pid = _images_project(project, fakes, monkeypatch)
    seen = {}

    def adapt_to(bundle, k, options, codes):
        seen["options"], seen["k"] = options, k
        new = {**bundle["plans"][k], "image": "moment 4 vu autrement",
               "textes": {"fr": {"bandeau": "X : Y 😐", "texte": "Une phrase adaptée et complète.", "mots_cles": []},
                          "ar": {"bandeau": "س", "texte": "جملة جديدة كاملة.", "mots_cles": []}}}
        return 0, new
    monkeypatch.setattr(sb, "adapt_to", adapt_to)
    ap.choose_pick(pid, 4, None)                              # plan 5's moment is free again
    p = ap.adapt_plan(pid, 5)
    assert seen["k"] == 5 and [o["vu"] for o in seen["options"]] == ["moment 4"]       # the moments other plans use are not offered
    assert p["storyboard"]["plans"][5]["image"] == "moment 4 vu autrement" and p["storyboard"]["plans"][5]["adapte"]
    assert p["picks"][5]["niveau"] == "adaptée" and p["picks"][5]["moment"] == {"debut": 220.0, "fin": 224.0}
    assert p["targets"][0]["script"]["passages"][5]["texte"] == "Une phrase adaptée et complète."


def test_fetch_downloads_only_the_moments_and_gives_each_plan_its_clip(project, fakes, monkeypatch):
    from adaptation import sources
    pid = _images_project(project, fakes, monkeypatch)
    ap.skip_plan(pid, 5)
    got = {}

    def download(url, d, name, sections=None):
        got["sections"] = sections
        return f"{d}/{name}.mp4"
    monkeypatch.setattr(sources, "download", download)
    monkeypatch.setattr(sources, "source_meta", lambda path: {"handle": "@auteur"})
    monkeypatch.setattr(sources, "still", lambda path, t, crop, out, *a, **k: out)
    monkeypatch.setattr(sources, "find_boxes", lambda stills: [(None, [], ["@auteur"])] * len(stills))
    made = []

    def clip_at(path, i, cid, a, b, found, desc=""):
        made.append((cid, round(a, 2), round(b, 2)))
        return {"id": cid, "source": i, "src": path, "start": a, "end": b, "impact": a, "w": 1080, "h": 1920,
                "usable": True, "marks": found[2], "desc": desc, "shock": False}
    monkeypatch.setattr(sources, "clip_at", clip_at)
    monkeypatch.setattr(sources, "describe", lambda path, segs: [
        {"visuel": f"vu {k}", "utilisable": k != 4, "pourquoi_pas": "présentateur" if k == 4 else "", "choc_sonore": False}
        for k in range(len(segs))])
    ap.start_fetch(pid)
    ap.run_fetch(pid)
    p = ap.load(pid)
    assert p["status"] == "script_review" and p["source_urls"] == ["https://www.youtube.com/watch?v=aaaaaaaaaaa"]
    plans = p["storyboard"]["plans"]
    room = [min(pl["duree"], 6.0) for pl in plans]                             # room to lengthen inside the shot
    assert got["sections"][0][0] == pytest.approx(100 - room[0] - 1) and len(got["sections"]) == 5
    # times in the downloaded file: the spans are joined one after the other
    lens = [b - a for a, b in got["sections"]]
    assert made[1][1] == pytest.approx(lens[0] + 1.0 + room[1], abs=0.01)
    assert made[0][2] - made[0][1] == pytest.approx(max(4, plans[0]["duree"]))   # long enough for its sentence
    assert set(p["clips"]) == {"P1", "P2", "P3", "P4", "P5"} and p["credits"] == "@auteur"
    assert p["clips"]["P1"]["desc"] == "vu 0" and not p["clips"]["P5"]["usable"]
    t = p["targets"][0]
    assert [x["clip"] for x in t["script"]["passages"]] == ["P1", "P2", "P3", "P4", "P5"]      # plan 6 set aside
    assert any("présentateur" in x for x in t["problems"]) and not t["approved"]          # the check refused plan 5's moment
    p = ap.back_to_images(pid)
    assert p["status"] == "images_review" and p["picks"][0]                                # pick another moment there


def test_a_short_moment_is_lengthened_inside_its_shot_never_across_a_cut():
    # measured: 24-27 then an interview from 28.1 s; 0-3 then a black end screen from 3.8 s
    assert ap.fit_window(24, 27, 5.4, [(10.08, 27.98), (28.18, 40)], 99) == (22.58, 27.98)
    assert ap.fit_window(0, 3, 5.5, [(0.08, 3.62), (3.82, 6.42)], 6.5) == (0, 3.62)
    assert ap.fit_window(10, 12, 4, [(5, 30)], 60) == (10, 14)                  # room ahead: forward first
    assert ap.fit_window(10, 16, 4, [(5, 30)], 60) == (10, 16)                  # long enough: as it is
    assert ap.fit_window(10, 12, 0, [(11, 30)], 60) == (10, 12)                 # an excerpt: untouched


def test_a_sentence_too_long_for_its_shorter_clip_is_shortened_alone(monkeypatch):
    from adaptation import script
    clips = {"P1": {"start": 0, "end": 4}, "P2": {"start": 0, "end": 2}, "P3": {"start": 0, "end": 4}}
    texts = ["Une phrase courte.", "Une phrase beaucoup trop longue pour un clip de deux secondes seulement.", "Fin."]
    sc = {"titre": "T", "passages": [{"clip": f"P{k + 1}", "texte": t, "bandeau": ""} for k, t in enumerate(texts)]}
    p = {"storyboard": {"plans": [{"textes": {"fr": {"texte": t}}} for t in texts]}, "skipped": []}
    asked = []

    def revise(sc, clips, request, gemini=None):
        asked.append(request)
        return {"passages": [{**x, "texte": "Tout autre chose."} if k != 1 else {**x, "texte": "Trop court pour lui."}
                             for k, x in enumerate(sc["passages"])]}
    monkeypatch.setattr(script, "revise", revise)
    monkeypatch.setattr(ap, "_active", lambda p: [0, 1, 2])
    out = ap._shorten(p, sc, clips, "fr", lambda *a: None)
    assert [x["texte"] for x in out["passages"]] == ["Une phrase courte.", "Trop court pour lui.", "Fin."]   # only passage 2
    assert len(asked) == 1 and "Passage 2" in asked[0]
    assert p["storyboard"]["plans"][1]["textes"]["fr"]["texte"] == "Trop court pour lui."


def test_each_sentence_is_compared_with_what_its_clip_really_shows():
    from adaptation import script

    class G:
        def _generate_content(self, parts, **kw):
            G.prompt = parts[0]["text"]
            return {"passages": [{"note": "non", "pourquoi": "on entend dos d'âne, on voit un labo",
                                  "proposition": "Ce liquide cache un secret."}, {"note": "bon", "proposition": "x"},
                                 {"note": "bizarre"}]}
    clips = {"P1": {"start": 0, "end": 4, "desc": "un homme frappe un bac"}, "P2": {"start": 0, "end": 3, "desc": "une roue"},
             "P3": {"start": 0, "end": 3, "desc": "?"}}
    sc = {"passages": [{"clip": f"P{k}", "texte": f"Phrase {k}."} for k in (1, 2, 3)]}
    out = script.match(sc, clips, "fr", gemini=G())
    assert "un homme frappe un bac" in G.prompt and "ACCROCHE" in G.prompt
    assert [a["note"] for a in out] == ["non", "bon", "bon"] and out[1]["proposition"] == ""   # unknown note: never blocks
    assert out[0] == {"clip": "P1", "texte": "Phrase 1.", "note": "non", "pourquoi": "on entend dos d'âne, on voit un labo",
                      "proposition": "Ce liquide cache un secret."}
    probs = ap._fetched_problems(sc, clips, "fr", out)
    assert any("Passage 1 : la phrase ne correspond pas" in x for x in probs)
    sc["passages"][0]["texte"] = "Une autre phrase."                       # the sentence changed: the verdict is stale
    assert not any("ne correspond pas" in x for x in ap._fetched_problems(sc, clips, "fr", out))


def test_a_sentence_that_does_not_match_its_clip_blocks_until_rewritten_or_kept(project, fakes, monkeypatch):
    from adaptation import sources, script
    pid = _images_project(project, fakes, monkeypatch)
    ap.skip_plan(pid, 5)
    monkeypatch.setattr(sources, "download", lambda url, d, name, sections=None: f"{d}/{name}.mp4")
    monkeypatch.setattr(sources, "source_meta", lambda path: {})
    monkeypatch.setattr(sources, "still", lambda path, t, crop, out, *a, **k: out)
    monkeypatch.setattr(sources, "find_boxes", lambda stills: [(None, [], [])] * len(stills))
    monkeypatch.setattr(sources, "clip_at", lambda path, i, cid, a, b, found, desc="": {
        "id": cid, "source": i, "src": path, "start": a, "end": b + 3, "impact": a, "w": 1080, "h": 1920, "usable": True,
        "marks": [], "desc": desc, "shock": False})
    monkeypatch.setattr(sources, "describe", lambda path, segs: [{"visuel": "vu", "utilisable": True} for _ in segs])
    monkeypatch.setattr(script, "match", lambda sc, clips, code: [
        {"clip": x["clip"], "texte": x["texte"], "note": "non" if k < 2 else "bon", "pourquoi": "autre chose",
         "proposition": "Une phrase pour cette image." if k < 2 else ""} for k, x in enumerate(sc["passages"])])
    ap.start_fetch(pid)
    ap.run_fetch(pid)
    t = ap.load(pid)["targets"][0]
    assert sum("ne correspond pas" in x for x in t["problems"]) == 2 and not t["approved"]
    p = ap.use_proposal(pid, t["channel"], 0)
    t = p["targets"][0]
    assert t["script"]["passages"][0]["texte"] == "Une phrase pour cette image."
    assert p["storyboard"]["plans"][0]["textes"][t["language"]]["texte"] == "Une phrase pour cette image."
    t = ap.keep_passage(pid, t["channel"], 1)["targets"][0]
    assert not any("ne correspond pas" in x for x in t["problems"])
    with pytest.raises(ap.PipelineError):
        ap.use_proposal(pid, t["channel"], 2)                               # a good match has nothing to propose


def test_the_montage_effects_chosen_after_the_download_reach_the_script_and_the_render(project, fakes, monkeypatch, tmp_path):
    from adaptation import sources, effects, annotate
    pid = _images_project(project, fakes, monkeypatch)
    ap.skip_plan(pid, 5)
    monkeypatch.setattr(sources, "download", lambda url, d, name, sections=None: f"{d}/{name}.mp4")
    monkeypatch.setattr(sources, "source_meta", lambda path: {})
    monkeypatch.setattr(sources, "still", lambda path, t, crop, out, *a, **k: out)
    monkeypatch.setattr(sources, "find_boxes", lambda stills: [(None, [], [])] * len(stills))
    monkeypatch.setattr(sources, "clip_at", lambda path, i, cid, a, b, found, desc="": {
        "id": cid, "source": i, "src": path, "start": a, "end": b + 3, "impact": a + 1, "w": 1920, "h": 1080,
        "usable": True, "marks": [], "desc": desc, "shock": True})
    monkeypatch.setattr(sources, "describe", lambda path, segs: [{"visuel": "vu", "utilisable": True} for _ in segs])
    monkeypatch.setattr(effects, "decide", lambda passages, clips, work: [
        {"ralenti": True, "zoom": "les pieds", "arret": False, "transition": False} if k == 1 else None
        for k in range(len(passages))])
    ap.start_fetch(pid)
    ap.run_fetch(pid)
    p = ap.load(pid)
    assert p["storyboard"]["plans"][1]["effets"]["zoom"] == "les pieds"
    t = p["targets"][0]
    assert t["script"]["passages"][1]["effets"] == {"ralenti": True, "zoom": "les pieds", "arret": False, "transition": False}
    asked = []
    monkeypatch.setattr(annotate, "locate", lambda stills, cible: asked.append(cible) or [[700, 400, 800, 500]])
    fx = ap._effects(p, t, str(tmp_path / "w"))
    assert fx[0] is None and fx[1]["ralenti"] and fx[1]["zoom"]["cx"] == 0.45 and asked == ["les pieds"]
    ap._effects(p, t, str(tmp_path / "w"))
    assert asked == ["les pieds"]                                      # found once, the final render reuses it
    edited = ap.edit_script(pid, t["channel"], {"passages": [{**x, "effets": None} if k == 1 else x
                                                             for k, x in enumerate(t["script"]["passages"])]})
    assert edited["targets"][0]["script"]["passages"][1]["effets"] is None   # unticked by hand: gone


def test_an_advert_is_a_warning_not_a_refusal():
    from adaptation import finder
    assert finder.real_faults("publicité") == "" and finder.warnings_of("publicité") == "publicité"
    assert finder.real_faults("présentateur, pub") == "présentateur" and finder.warnings_of("présentateur, pub") == "pub"


def test_spans_merge_close_moments_and_calm_clips_do_not_shake():
    from adaptation import render
    assert ap._spans([(0, 10, 14), (1, 15, 18), (2, 100, 104)]) == [[9.0, 19.0], [99.0, 105.0]]
    seg = {"ws": 0.0, "dur": 3.0, "impact_out": 1.0, "out": 0.0}
    calm = {"start": 0, "end": 4, "w": 1080, "h": 1920, "shock": False}
    assert "exp(" not in " ".join(render.clip_chain(0, 0, calm, seg))
    assert "exp(" in " ".join(render.clip_chain(0, 0, {**calm, "shock": None}, seg))


def test_api_steps_4_and_5(client, project, fakes, monkeypatch):
    pid = _images_project(project, fakes, monkeypatch)
    assert client.post(f"/api/adaptations/{pid}/fetch").status_code == 400          # plan 6 has no video
    r = client.post(f"/api/adaptations/{pid}/plans/5/skip", json={"skip": True})
    assert r.status_code == 200 and r.json()["storyboard"]["plans"][5]["retire"]
    assert client.post(f"/api/adaptations/{pid}/plans/0/link", json={"url": "pas un lien"}).status_code == 400


def test_a_logo_alone_does_not_refuse_a_chosen_moment():
    assert ap._real_faults("logo") == "" and ap._real_faults("filigrane TikTok @x, logo") == ""
    assert ap._real_faults("presentateur, logo, ecran scinde") == "presentateur, ecran scinde"
    assert ap._real_faults("logo, texte incrusté") == ""                  # the cleaning crops or paints it
    assert ap._real_faults("montage de clips avec texte incrusté") == "" and ap._real_faults("clip musical") == ""
    assert ap._real_faults("presentateur, split screen") == "presentateur, split screen"
    assert ap._real_faults("Écran de fin") == "Écran de fin" and ap._real_faults("image floue") == "image floue"
    assert ap._real_faults("voix off") == "" and ap._real_faults("présentateur, musique forte") == "présentateur"
    clips = {"P1": {"start": 0, "end": 5, "usable": False, "why_not": "voix off"},
             "P2": {"start": 0, "end": 5, "usable": False, "why_not": "présentateur"}}
    sc = {"passages": [{"clip": "P1", "texte": "Une phrase.", "bandeau": "", "mots_cles": []},
                       {"clip": "P2", "texte": "Une autre.", "bandeau": "", "mots_cles": []}]}
    found = [x for x in ap._fetched_problems(sc, clips, "fr") if "moment choisi" in x]
    assert len(found) == 1 and "Passage 2" in found[0]               # an earlier "voix off" refusal no longer blocks


def test_a_re_edit_chosen_by_hand_keeps_its_warning(project, fakes, monkeypatch):
    pid = _images_project(project, fakes, monkeypatch)
    p = ap.load(pid)
    p["suggestions"]["verifs"]["https://www.youtube.com/watch?v=aaaaaaaaaaa"]["remontage"] = True
    ap.save(p)
    assert ap.choose_pick(pid, 5, "https://www.youtube.com/watch?v=aaaaaaaaaaa", 10)["picks"][5]["remontage"]


# ---------------------------------------------------------------- improvements: clean moments, kept clips

def test_a_moment_with_a_presenter_is_avoided_already_at_the_pick():
    from adaptation import finder

    class G:
        def _generate_content(self, parts, **kw):
            return {"plans": [{"plan": 1, "niveau": "exacte", "moments": [{"debut": 30, "fin": 41}],
                               "defauts": "présentateur, logo, texte incrusté"}], "resume": "r"}
    r = finder.check("https://www.youtube.com/watch?v=aaaaaaaaaaa", [{"scene": "un cheval fume"}], gemini=G())
    assert r["par_scene"]["0"]["defauts"] == "présentateur"           # a logo or a text is no fault: it is cleaned
    v = lambda lvl, fault: {"verdict": "oui", "par_scene": {"0": {"niveau": lvl, "moments": [{"debut": 1, "fin": 5}], "defauts": fault}}}
    sug = {"verifs": {"tv": v("exacte", "présentateur"), "clean": v("partielle", "")}}
    assert finder.auto_pick(sug, [{}])[0]["url"] == "clean"
    pick = finder.auto_pick({"verifs": {"tv": v("exacte", "présentateur")}}, [{}])[0]
    assert pick["url"] == "tv" and pick["defauts"] == "présentateur"     # nothing else: taken, and said


def test_fetching_again_keeps_the_clips_of_the_unchanged_plans(project, fakes, monkeypatch):
    from adaptation import sources
    pid = _images_project(project, fakes, monkeypatch)
    ap.skip_plan(pid, 5)
    downloads = []

    def download(url, d, name, sections=None):
        downloads.append((name, sections))
        Path(d).mkdir(parents=True, exist_ok=True)
        path = f"{d}/{name}.mp4"
        Path(path).write_bytes(b"x")
        return path
    monkeypatch.setattr(sources, "download", download)
    monkeypatch.setattr(sources, "source_meta", lambda path: {"handle": "@auteur", "url": "u"})
    monkeypatch.setattr(sources, "still", lambda path, t, crop, out, *a, **k: out)
    monkeypatch.setattr(sources, "find_boxes", lambda stills: [(None, [], [])] * len(stills))
    monkeypatch.setattr(sources, "describe", lambda path, segs: [{} for _ in segs])
    monkeypatch.setattr(sources, "clip_at", lambda path, i, cid, a, b, found, desc="": {
        "id": cid, "source": i, "src": path, "start": a, "end": b, "impact": a, "w": 1080, "h": 1920, "usable": True,
        "marks": [], "desc": desc})
    ap.start_fetch(pid); ap.run_fetch(pid)
    first = ap.load(pid)["clips"]
    assert len(downloads) == 1
    ap.back_to_images(pid)
    ap.choose_pick(pid, 2, "https://www.tiktok.com/@a/video/9", 3, 9)       # only plan 3 changes
    ap.start_fetch(pid); ap.run_fetch(pid)
    p = ap.load(pid)
    assert len(downloads) == 2 and downloads[1][0] != downloads[0][0]     # a new file name, the kept clips' file untouched
    assert p["clips"]["P1"] == first["P1"] and p["clips"]["P3"]["src"].endswith(downloads[1][0] + ".mp4")
    assert p["source_urls"] == ["https://www.youtube.com/watch?v=aaaaaaaaaaa", "https://www.tiktok.com/@a/video/9"]
    assert [m["handle"] for m in p["sources"]] == ["@auteur", "@auteur"] and p["clips"]["P3"]["source"] == 1


# ---------------------------------------------------------------- last resort: an excerpt of the reference

def test_excerpt_window_stays_inside_one_shot_and_three_seconds(project, fakes, monkeypatch):
    from adaptation import sources
    pid = new_project(project)["project_id"]
    ap.run_analysis(pid)
    p = ap.load(pid)
    p["reference"]["plans"] = [{"debut": 0, "fin": 4}, {"debut": 4, "fin": 12}, {"debut": 12, "fin": 15}]
    monkeypatch.setattr(ap, "_short_file", lambda p: None)
    assert ap.excerpt_window(p, [1]) == (6.5, 9.5)
    monkeypatch.setattr(ap, "_short_file", lambda p: "short.mp4")
    monkeypatch.setattr(sources, "probe", lambda path: {"duration": 15})
    monkeypatch.setattr(sources, "detect_cuts", lambda *a, **k: [(0, 4), (4, 6), (6.1, 11.9), (12, 15)])
    assert ap.excerpt_window(p, [1]) == (7.5, 10.5)            # the longest real shot of the scene, its middle
    assert ap.excerpt_window(p, [2]) == (12.0, 15.0)
    monkeypatch.setattr(sources, "detect_cuts", lambda *a, **k: [(4, 5.1), (5.2, 6.3), (6.4, 7.4), (7.5, 8.6), (8.7, 12)])
    assert ap.excerpt_window(p, [1]) == (8.85, 11.85)          # quick cuts, but one 3.3 s shot: that one…
    monkeypatch.setattr(sources, "detect_cuts", lambda *a, **k: [(4 + k, 4.9 + k) for k in range(8)])
    assert ap.excerpt_window(p, [1]) == (6.5, 9.5)             # …all under 2 s: 3 s of the scene, cuts included
    with pytest.raises(ap.PipelineError):
        ap.excerpt_window(p, [9])


def test_script_first_excerpt_never_for_the_hook_two_at_most(project, fakes, monkeypatch):
    pid = _images_project(project, fakes, monkeypatch)
    monkeypatch.setattr(ap, "excerpt_window", lambda p, plans: (6.5, 9.5))
    with pytest.raises(ap.PipelineError, match="accroche"):
        ap.use_excerpt_for_plan(pid, 0)
    p = ap.use_excerpt_for_plan(pid, 5)
    pick = p["picks"][5]
    assert pick["extrait"] and pick["url"] == "https://youtube.com/shorts/x" and pick["moment"] == {"debut": 6.5, "fin": 9.5}
    ap.use_excerpt_for_plan(pid, 4)
    with pytest.raises(ap.PipelineError, match="maximum"):
        ap.use_excerpt_for_plan(pid, 3)
    assert ap.use_excerpt_for_plan(pid, 5)["picks"][5]["extrait"]          # redoing one already counted is fine


def test_sources_first_excerpt_becomes_a_clean_credited_clip(project, monkeypatch):
    import json as _json
    from adaptation import sources
    from adaptation import pipeline
    project.add_channel("chanA")
    (Path("channels") / "chanA" / "profile.json").write_text(_json.dumps({"language_hint": "fr", "adaptation": {"voice_id": "v"}}))
    import db
    db.upsert_voice({"voice_id": "v", "name": "v", "language": "fr"})
    pid = ap.create("https://youtube.com/shorts/ref", [], [{"channel": "chanA", "profile": {"language_hint": "fr",
                    "adaptation": {"voice_id": "v"}}, "music_dir": "."}])["project_id"]
    p = ap.load(pid)
    p.update(status="sources_search", reference={"plans": [{"debut": 0, "fin": 3}, {"debut": 3, "fin": 9}]},
             suggestions={"scenes": [{"scene": "l'accroche", "plans": [0]}, {"scene": "l'homme au masque", "plans": [1]}]})
    ap.save(p)
    monkeypatch.setattr(ap, "_short_file", lambda p: "short.mp4")
    monkeypatch.setattr(sources, "probe", lambda path: {"duration": 9})
    monkeypatch.setattr(sources, "detect_cuts", lambda *a, **k: [(0, 3), (3, 9)])
    monkeypatch.setattr(sources, "still", lambda *a, **k: "s.jpg")
    monkeypatch.setattr(sources, "find_boxes", lambda stills: [([0, 0, 1000, 1000], [], ["@createur_du_short"])])
    monkeypatch.setattr(sources, "source_meta", lambda path: {"handle": "@createur_du_short"})
    monkeypatch.setattr(sources, "clip_at", lambda path, i, cid, a, b, found, desc="": {
        "id": cid, "source": i, "src": path, "start": a, "end": b, "impact": a, "w": 1080, "h": 1920, "usable": True,
        "marks": found[2], "desc": desc})
    with pytest.raises(ap.PipelineError, match="Aucun nouveau lien"):
        ap.add_sources(pid, [])
    p = ap.add_excerpt_source(pid, 1)                       # while choosing: only planned, the step stays
    assert p["status"] == "sources_search" and p["pending_excerpts"] == [1] and p["clips"] == {}
    assert ap.add_excerpt_source(pid, 1)["pending_excerpts"] == []          # clicked again: cancelled
    ap.add_excerpt_source(pid, 1)
    ap.add_sources(pid, [])                                 # an excerpt alone may be "downloaded"
    ap.run_analysis(pid)
    p = ap.load(pid)
    c = p["clips"]["M1"]
    assert p["status"] == "sources_review" and c["extrait"] and (c["start"], c["end"]) == (4.5, 7.5)
    assert not p.get("pending_excerpts")
    with pytest.raises(ap.PipelineError, match="déjà son extrait"):
        ap.add_excerpt_source(pid, 1)
    assert "extrait du Short modèle" in c["desc"] and "@createur_du_short" in p["credits"]
    assert p["source_urls"] == ["https://youtube.com/shorts/ref"] and len(p["sources"]) == 1
    sc = {"passages": [{"clip": "M1", "texte": "Court.", "bandeau": "", "mots_cles": []}]}
    from adaptation import script
    assert any("accroche" in x for x in script.problems(sc, p["clips"], "fr"))



# ---------------------------------------------------------------- one version per channel: angles and groups

def test_one_project_per_channel_each_with_its_own_angle(project, fakes):
    a, b = channel(project, "chanA", "fr", "v_fr"), channel(project, "chanB", "ar", "v_ar")
    lead = ap.create("https://youtube.com/shorts/x", [], [a, b], mode="script", versions=True)
    group = [lead] + ap.group_of(lead)
    assert len(group) == 2 and all(len(x["targets"]) == 1 for x in group)
    ap.run_analysis(lead["project_id"])                         # the leader's run does the whole group
    group = [ap.load(x["project_id"]) for x in group]
    assert fakes["reference"] == 1 and fakes["write"] == 2
    assert [x["status"] for x in group] == ["plan_review", "plan_review"]
    assert {x["angle"]["titre"] for x in group} == {"Le test honnête", "Les 3 erreurs"}
    assert group[1]["reference"] == group[0]["reference"] and not group[1]["await_leader"]
    assert sorted(fakes["written_with"]) == ["Le test honnête", "Les 3 erreurs"]


def test_without_versions_it_is_one_project_translated(project, fakes):
    p = ap.create("https://youtube.com/shorts/x", [], [channel(project, "chanA", "fr", "v_fr"),
                                                      channel(project, "chanB", "ar", "v_ar")], mode="script")
    assert len(p["targets"]) == 2 and not p.get("group")
    ap.run_analysis(p["project_id"])
    assert fakes["write"] == 1 and ap.load(p["project_id"])["angle"]["titre"] == "Le test honnête"


def test_a_new_version_for_another_channel_takes_an_unused_angle(project, fakes):
    pid = ap.create("https://youtube.com/shorts/x", [], [channel(project, "chanA", "fr", "v_fr")], mode="script")["project_id"]
    ap.run_analysis(pid)
    with pytest.raises(ap.PipelineError, match="déjà sa version"):
        ap.new_version(pid, channel(project, "chanA", "fr", "v_fr"))
    nv = ap.new_version(pid, channel(project, "chanB", "en", "v_en"))
    assert nv["group"] == pid and ap.load(pid)["group"] == pid and nv["reference"]
    ap.run_analysis(nv["project_id"])
    nv = ap.load(nv["project_id"])
    assert fakes["reference"] == 1                              # the reference is not read again
    assert fakes["angles"][-1] == ["Le test honnête"] and nv["angle"]["titre"] == "Les 3 erreurs"


def test_change_the_angle_rewrites_the_storyboard(project, fakes):
    pid = ap.create("https://youtube.com/shorts/x", [], [channel(project, "chanA", "fr", "v_fr")], mode="script")["project_id"]
    ap.run_analysis(pid)
    with pytest.raises(ap.PipelineError):
        ap.change_angle(pid)
    assert ap.change_angle(pid, index=2)["status"] == "analysing"
    ap.run_analysis(pid)
    p = ap.load(pid)
    assert p["status"] == "plan_review" and p["angle"]["titre"] == "Ça vaut le coup ?" and fakes["written_with"][-1] == "Ça vaut le coup ?"
    assert len(fakes["angles"]) == 1                            # the angles are proposed once
    ap.change_angle(pid, custom="Le point de vue du conducteur")
    ap.run_analysis(pid)
    assert fakes["written_with"][-1] == "Le point de vue du conducteur"


def test_api_versions_angle_and_new_version(client, project, fakes):
    import time
    channel(project, "chanA", "fr", "v_fr"); channel(project, "chanB", "ar", "v_ar")
    r = client.post("/api/adaptations", json={"reference_url": "https://youtube.com/shorts/x", "channels": ["chanA", "chanB"],
                                              "mode": "script", "versions": True})
    pid = r.json()["project_id"]
    for _ in range(80):
        if all(x["status"] != "analysing" for x in client.get("/api/adaptations").json()):
            break
        time.sleep(0.1)
    listing = client.get("/api/adaptations").json()
    assert len(listing) == 2 and {x["group"] for x in listing} == {pid}
    p = client.get(f"/api/adaptations/{pid}").json()
    assert p["angle"]["titre"] and len(p["angles"]) >= 2 and sorted(p["group_channels"]) == ["chanA", "chanB"]
    assert client.post(f"/api/adaptations/{pid}/angle", json={}).status_code == 400
    assert client.post(f"/api/adaptations/{pid}/new-version", json={"channel": "chanB"}).status_code == 400


def test_an_arrow_set_on_the_storyboard_comes_back_to_the_page(client, project, fakes):
    pid = ap.create("https://youtube.com/shorts/x", [], [channel(project, "chanA", "fr", "v_fr")], mode="script")["project_id"]
    ap.run_analysis(pid)
    p = client.get(f"/api/adaptations/{pid}").json()
    plan_ = {**p["targets"][0]["script"], "passages": [{**x, "image": p["storyboard"]["plans"][k]["image"]}
                                                      for k, x in enumerate(p["targets"][0]["script"]["passages"])]}
    plan_["passages"][0]["annotation"] = {"type": "cercle", "cible": "la semelle collée au sol"}
    r = client.put(f"/api/adaptations/{pid}/targets/chanA/plan", json={"plan": plan_}).json()
    assert r["storyboard"]["plans"][0]["annotation"] == {"type": "cercle", "cible": "la semelle collée au sol"}
    assert client.get(f"/api/adaptations/{pid}").json()["storyboard"]["plans"][0]["annotation"]["cible"] == "la semelle collée au sol"


def test_a_picked_video_that_wont_download_is_replaced_and_the_picks_come_back(project, fakes, monkeypatch):
    from adaptation import sources
    pid = _images_project(project, fakes, monkeypatch)
    p = ap.load(pid)
    other = "https://www.youtube.com/watch?v=bbbbbbbbbbb"
    p["suggestions"]["verifs"][other] = {"verdict": "probable", "par_scene": {"0": {"niveau": "equivalente", "moments": [{"debut": 1, "fin": 6}]}}}
    ap.save(p)
    ap.skip_plan(pid, 5)
    monkeypatch.setattr(sources, "download", lambda *a, **k: (_ for _ in ()).throw(sources.SourceError("bloquée")))
    ap.start_fetch(pid); ap.run_fetch(pid)
    p = ap.load(pid)
    assert p["status"] == "images_review" and "aaaaaaaaaaa" in p["suggestions"]["unavailable"][0]
    assert p["picks"][0]["url"] == other                    # plan 1: another checked video
    assert p["picks"][1] is None                            # nothing else for plan 2
    assert "plan(s) 1, 2, 3, 4, 5" in p["fetch_note"] and "Une autre vidéo" in p["fetch_note"]
    assert ap.choose_pick(pid, 1, other, 1, 6)["picks"][1]["url"] == other   # the person picks again from there


def test_a_sentence_split_between_two_plans_is_refused_at_both_ends():
    b = sb.normalise(json.loads(json.dumps(GOOD)), ["fr", "ar"])
    b["plans"][4]["textes"]["fr"]["texte"] = "Cette colle empêche ces bolides de patiner sur place…"
    b["plans"][5]["textes"]["fr"]["texte"] = "…et leur évite surtout de s'envoler au démarrage !"
    found = " | ".join(sb.problems(b, "fr"))
    assert "Plan 5 : phrase incomplète" in found and "Plan 6 : la phrase commence par « … »" in found
    from adaptation import script
    sc = {"passages": [{"clip": "A", "texte": "...et voilà.", "bandeau": "", "mots_cles": []}]}
    assert any("commence par" in x for x in script.problems(sc, {"A": {"start": 0, "end": 5}}, "fr"))


def test_force_a_refused_clip_and_the_versions_tabs(client, project, fakes):
    a, b = channel(project, "chanA", "fr", "v_fr"), channel(project, "chanB", "ar", "v_ar")
    lead = ap.create("https://youtube.com/shorts/x", [], [a, b], mode="script", versions=True)
    ap.run_analysis(lead["project_id"])
    p = client.get(f"/api/adaptations/{lead['project_id']}").json()
    assert [m["channels"] for m in p["group_members"]] == [["chanA"], ["chanB"]] and all(m["angle"] for m in p["group_members"])
    q = ap.load(lead["project_id"])
    q["status"] = "script_review"
    q["clips"] = {"P1": {"id": "P1", "start": 0, "end": 5, "usable": False, "why_not": "trop flou"}}
    t = q["targets"][0]
    t["script"] = {"titre": "t", "passages": [{"clip": "P1", "texte": "Une phrase complète.", "bandeau": "", "mots_cles": []}]}
    ap.save(q)
    r = client.post(f"/api/adaptations/{lead['project_id']}/clips/P1/force").json()
    clip = next(c for c in r["clips"] if c["id"] == "P1")
    assert clip["usable"] and clip["forced"] == "trop flou"
    assert not any("ne convient pas" in x for x in r["targets"][0]["problems"])
    assert client.post(f"/api/adaptations/{lead['project_id']}/clips/ZZ/force").status_code == 400


def test_the_versions_of_a_group_share_the_searches_that_are_the_same(project, fakes, monkeypatch):
    from adaptation import finder, frames, imagesearch
    a, b = channel(project, "chanA", "fr", "v_fr"), channel(project, "chanB", "ar", "v_ar")
    lead = ap.create("https://youtube.com/shorts/x", [], [a, b], mode="script", versions=True)
    ap.run_analysis(lead["project_id"])
    members = [ap.load(lead["project_id"])] + ap.group_of(ap.load(lead["project_id"]))
    calls = {"frames": 0, "yandex": 0, "youtube": []}
    monkeypatch.setattr(finder, "plan_queries", lambda found: {i: {"recherches": ["tram crash"], "pays": "", "langue": "",
                                                                    "locales": []} for i in range(len(found))})
    monkeypatch.setattr(finder, "sort_out", lambda found, gemini=None, prompt=None: None)
    monkeypatch.setattr(finder, "verify_best", lambda sug, ref, n, report=None: sug)

    def youtube(q, n=5):
        calls["youtube"].append(q)
        return [{"id": "aaaaaaaaaaa", "url": "https://www.youtube.com/watch?v=aaaaaaaaaaa", "title": "t", "channel": "c"}]
    monkeypatch.setattr(finder, "search_youtube", youtube)

    def ref_frames(ref, url, work, scenes, report=None):
        calls["frames"] += 1
        os.makedirs(work, exist_ok=True)
        Path(work, "f00.jpg").write_bytes(b"jpg")
        return {"frames": [{"file": "f00.jpg", "t": 1.0, "plan": 0, "scene": None}], "source": "short", "error": None}
    monkeypatch.setattr(frames, "reference_frames", ref_frames)

    def yandex(files):
        calls["yandex"] += 1
        return {"hits": {f: [{"url": "https://vkvideo.ru/video-1_2", "title": "v", "thumb": "", "platform": "VK"}] for f in files},
                "error": None, "seconds": 1}
    monkeypatch.setattr(imagesearch, "timed_search", yandex)
    for m in members:
        for t in m["targets"]:
            ap.approve_plan(m["project_id"], t["channel"])
        ap.start_images(m["project_id"]); ap.run_images(m["project_id"])
    assert calls["frames"] == 1 and calls["yandex"] == 1                 # done once for the group
    assert len(calls["youtube"]) == 1                                    # the same words searched once
    second = ap.load(members[1]["project_id"])
    assert second["status"] == "images_review" and second["suggestions"]["images"]["frames"][0]["file"] == "f00.jpg"
    assert Path(ap.project_dir(members[1]["project_id"]), "finder", "f00.jpg").exists()     # copied for its page
    assert "search_cache" in ap.load(lead["project_id"])
