"""« Le plan du réalisateur » (the director's plan kept, the person's version translated) and « Je choisis mes plans »
(the main shot of each sentence, the editor around it, « aucun ne va ») — 2026-11-14. No real call."""

import os
import subprocess

import pytest

from adaptation import montage_pro as mp
from adaptation import pipeline as ap
from adaptation import realisateur

SENTENCES = ["البراق كيحفر التراب", "430 كلم جديدة", "نفق فالرباط"]


def entry(n, kind="reel", image="une image", graphique=None):
    return {"phrase": n, "type": kind, "pourquoi": "", "graphique": graphique,
            "visuels": [{"mot": "", "image": image, "idee": "an image", "anglais": ["q"], "pays": "", "locales": [],
                         "entite": None}]}


def make(status="plan_review", **kw):
    t = {"channel": "c", "language": "ar", "voice_id": "v", "approved": True,
         "script": {"passages": [{"texte": s} for s in SENTENCES]}}
    p = {"project_id": "ad_cp", "status": status, "pro": True, "mode": "script", "targets": [t],
         "reference": {"sujet": "TGV", "faits": []},
         "storyboard": {"plans": [{"textes": {"ar": {"texte": s}}} for s in SENTENCES]}, **kw}
    return ap.save(p)


# ---------------------------------------------------------------- screen 1

def test_the_plan_is_made_once_for_the_same_sentences(project):
    p = make()
    assert not realisateur.is_current(p)
    p["realisation"], p["realisation_cle"] = [entry(1), entry(2), entry(3)], realisateur.key(p)
    assert realisateur.is_current(p)
    p["storyboard"]["plans"][0]["textes"]["ar"]["texte"] = "جملة أخرى"     # a sentence changed: made again
    assert not realisateur.is_current(p)


def test_the_search_starts_with_the_director_then_his_plan_is_shown(project, monkeypatch):
    make()
    assert ap.start_images("ad_cp")["status"] == "directing"
    monkeypatch.setattr(realisateur, "plan", lambda p, gemini=None: [entry(1), entry(2, "carte"), entry(3)])
    monkeypatch.setattr(realisateur, "channels", lambda r, **kw: 0)
    ap.run_directing("ad_cp")
    p = ap.load("ad_cp")
    assert p["status"] == "realisation_review" and realisateur.is_current(p)
    assert ap.back_from_realisation("ad_cp")["status"] == "plan_review"
    monkeypatch.setattr(realisateur, "plan", lambda p, gemini=None: pytest.fail("the plan must not be made again"))
    assert ap.start_images("ad_cp")["status"] == "realisation_review"    # back from the script: the same plan shown


def test_the_search_keeps_the_plan_the_person_validated(project, monkeypatch):
    p = make("searching", realisation=[entry(1, image="mon image")])
    p["realisation_cle"] = realisateur.key(p)
    ap.save(p)
    monkeypatch.setattr(realisateur, "plan", lambda p, gemini=None: pytest.fail("never made again"))
    stop = RuntimeError("searched")
    monkeypatch.setattr(realisateur, "wanted", lambda r, plans: (_ for _ in ()).throw(stop))
    from adaptation import vision
    monkeypatch.setattr(vision, "warm", lambda: None)
    ap.run_images("ad_cp")
    assert "searched" in (ap.load("ad_cp").get("error") or "")             # it went on with the kept plan


def test_the_person_s_versions_become_the_director_s_plan(project, monkeypatch):
    make("realisation_review", realisation=[entry(1), entry(2), entry(3, image="le Boraq à Marrakech")])
    asked = []

    def from_user(p, phrase, texte, genre=None, gemini=None):
        asked.append((phrase, texte, genre))
        return {**entry(phrase, "carte", "la route", {"contenu": "Tanger → Marrakech"}), "ta_version": texte}
    monkeypatch.setattr(realisateur, "from_user", from_user)
    monkeypatch.setattr(realisateur, "channels", lambda r, **kw: 0)
    p = ap.approve_realisation("ad_cp", {3: {"texte": "une carte Tanger → Marrakech", "type": "carte"},
                                         2: {"texte": "  ", "type": None}})
    assert asked == [(3, "une carte Tanger → Marrakech", "carte")]           # an empty version: kept as it was
    assert p["status"] == "searching" and p["realisation"][2]["type"] == "carte"
    assert p["realisation"][1]["visuels"][0]["image"] == "une image" and realisateur.is_current(p)


def test_a_version_the_ai_could_not_read_is_said(project, monkeypatch):
    make("realisation_review", realisation=[entry(1), entry(2), entry(3)])
    monkeypatch.setattr(realisateur, "from_user", lambda *a, **k: (_ for _ in ()).throw(ValueError("reformule")))
    with pytest.raises(ap.PipelineError, match="Phrase 1 : reformule"):
        ap.approve_realisation("ad_cp", {1: {"texte": "???"}})
    assert ap.load("ad_cp")["status"] == "realisation_review"


def test_from_user_writes_one_sentence_in_the_director_s_format(project):
    p = make(realisation=[entry(1), entry(2), entry(3)])

    class G:
        def _generate_content(self, parts, **kw):
            assert "Tanger" in parts[0]["text"] and "une carte animee" in parts[0]["text"]
            return {"plans": [{"phrase": 1, "type": "carte", "pourquoi": "trajet",
                               "visuels": [{"mot": "", "image": "la route Tanger Marrakech", "idee": "route map"}],
                               "graphique": {"contenu": "trajet", "lieu": "Morocco", "nom": "المغرب",
                                             "reperes": [{"lieu": "Tangier", "nom": "طنجة"}, {"lieu": "Marrakech", "nom": "مراكش"}]}}]}
    e = realisateur.from_user(p, 3, "la route Tanger → Marrakech", "carte", gemini=G())
    assert e["phrase"] == 3 and e["type"] == "carte" and len(e["graphique"]["reperes"]) == 2
    assert e["ta_version"].startswith("la route")
    with pytest.raises(ValueError):
        realisateur.from_user(p, 3, "   ", gemini=G())


# ---------------------------------------------------------------- screen 2

def stock():
    s = lambda sid, src, colle, **kw: {"id": sid, "source": src, "start": 0.0, "end": 2.6, "desc": sid, "force": 7,
                                       "pertinence": 8, "garde": True, "colle": colle, **kw}
    return [s("A", 0, [0.30, 0.10, 0.10]), s("B", 1, [0.29, 0.28, 0.10]), s("C", 2, [0.10, 0.27, 0.31]),
            s("D", 3, [0.20, 0.20, 0.20]), s("E", 5, [0.0, 0.0, 0.0]), s("F", 6, [0.0, 0.0, 0.0]), s("G2", "graphiques", [0, 0, 0], graphique="carte", pour=2),
            s("X", 4, [0.40, 0.40, 0.40], garde=False)]


def test_each_sentence_gets_its_proposals_and_the_ai_s_pick(project):
    p = make("stock_review", stock=stock())
    ph = mp.choices(p)["phrases"]
    assert [x["n"] for x in ph] == [1, 2, 3] and ph[0]["texte"] == SENTENCES[0]
    assert ph[0]["candidats"][:2] == ["A", "B"] and "X" not in ph[0]["candidats"]      # set aside: never proposed
    assert ph[1]["candidats"][0] == "G2" and ph[1]["ia"] == "G2"                       # its graphic first
    assert ph[0]["ia"] == "A" and ph[2]["ia"] == "C"
    p["choix_plans"] = {"1": "D"}
    assert mp.choices(p)["phrases"][0]["choix"] == "D"


def test_the_main_shot_opens_its_sentence_and_holds_half_of_it():
    from test_montage_pro import voice
    v = voice(["un deux trois quatre cinq six", "sept huit neuf dix"])
    shots = [{"id": i, "source": k, "start": 0, "end": 3, "desc": i, "force": 5, "pertinence": 8, "garde": True,
              "colle": [0.3, 0.3]} for k, i in enumerate("ABCDE")]
    raw = {"montage": [{"phrase": 1, "coupes": [{"mot": 0, "plan": "B"}, {"mot": 1, "plan": "C"}, {"mot": 4, "plan": "D"}]},
                       {"phrase": 2, "coupes": [{"mot": 0, "plan": "A"}]}]}
    edl = mp.build_edit(raw, v, shots, main={1: "A"})
    one = [e for e in edl if e["phrase"] == 1]
    assert one[0]["plan"] == "A"                                         # the person's shot opens it
    assert one[0]["fin"] - one[0]["debut"] >= 0.5 * (one[-1]["fin"] - one[0]["debut"]) - 0.01
    assert "C" not in [e["plan"] for e in one]                           # the cut inside its half: dropped
    assert all(e["plan"] != "A" for e in edl if e["phrase"] == 2)        # never used elsewhere


def test_the_choices_are_kept_and_the_montage_starts(project):
    make("stock_review", stock=stock(), ajout_note="x")
    p = mp.approve_choices("ad_cp", {"1": "D", "2": "X", "3": "C"})
    assert p["choix_plans"] == {"1": "D", "3": "C"} and p["status"] == "voicing" and not p.get("ajout_note")
    assert mp.chosen_main(p, [s for s in p["stock"] if not s.get("graphique")]) == {1: "D", 3: "C"}


def test_nothing_fits_a_link_is_added_for_that_sentence(project, monkeypatch, tmp_path):
    make("stock_review", stock=stock(), realisation=[entry(1), entry(2), entry(3)])
    with pytest.raises(ap.PipelineError):
        mp.start_add("ad_cp", 1)
    with pytest.raises(ap.PipelineError):
        mp.start_add("ad_cp", 1, url="pas un lien")
    assert mp.start_add("ad_cp", 3, url="https://youtu.be/x")["status"] == "adding"
    monkeypatch.setattr(mp.finder, "check", lambda url, sc, pl: {"par_scene": {"0": {"niveau": "exacte",
                                                                                      "moments": [{"debut": 5, "fin": 9}]}}})
    got = {}
    monkeypatch.setattr(mp.sources, "download", lambda url, d, name, spans: got.update(spans=spans) or str(tmp_path / "v.mp4"))
    monkeypatch.setattr(mp.sources, "source_meta", lambda path: {"title": "Le Boraq à Marrakech", "uploader": "ONCF"})
    monkeypatch.setattr(mp, "shots_of", lambda path, k, thumbs: [{"id": f"S{k}_00", "source": k, "start": 0, "end": 2},
                                                                   {"id": f"S{k}_01", "source": k, "start": 2, "end": 4}])

    def describe(shots, sujet, gemini=None):
        for s, sc in zip(shots, (0.2, 0.35)):
            s.update(desc="le train", pertinence=8, colle=[0.1, 0.1, sc])
    monkeypatch.setattr(mp, "describe", describe)
    monkeypatch.setattr(mp, "_vision_ok", lambda: False)
    mp.run_add("ad_cp")
    p = ap.load("ad_cp")
    assert p["status"] == "stock_review" and got["spans"] == [[2.0, 12.0]]
    new = [s for s in p["stock"] if s.get("ajout_pour") == 3]
    assert [s["id"] for s in new] == ["S7_00", "S7_01"] and new[0]["titre_source"] == "Le Boraq à Marrakech"
    assert p["choix_plans"]["3"] == "S7_01" and "2 plans ajoutés" in p["ajout_note"]
    assert mp.choices(p)["phrases"][2]["candidats"][:2] == ["S7_01", "S7_00"]       # its added shots first


def test_an_addition_that_fails_comes_back_to_the_choices_with_why(project, monkeypatch):
    make("stock_review", stock=stock(), realisation=[entry(1), entry(2), entry(3)])
    mp.start_add("ad_cp", 2, description="le Boraq vu de face")
    monkeypatch.setattr(mp, "_found_for", lambda *a: ([], entry(2)))
    mp.run_add("ad_cp")
    p = ap.load("ad_cp")
    assert p["status"] == "stock_review" and "Rien trouvé" in p["ajout_note"]


def test_a_shot_preview_is_a_short_vertical_clip(project, tmp_path):
    src = tmp_path / "src.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25", "-t", "4",
                    "-pix_fmt", "yuv420p", str(src)], check=True)
    make("stock_review", stock=[{"id": "A", "source": 0, "file": str(src), "start": 0.5, "end": 3.0, "x": 0.8,
                                    "garde": True}])
    out = mp.preview("ad_cp", "A")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", out],
                           capture_output=True, text=True).stdout.strip()
    assert probe == "216,384" and mp.preview("ad_cp", "A") == out
    with pytest.raises(ap.PipelineError):
        mp.preview("ad_cp", "Z")


def test_the_routes(client, monkeypatch):
    make("stock_review", stock=stock(), realisation=[entry(1), entry(2), entry(3)])
    r = client.get("/api/adaptations/ad_cp/choix-plans")
    assert r.status_code == 200 and r.json()["phrases"][1]["ia"] == "G2"
    p = client.get("/api/adaptations/ad_cp").json()
    assert p["phrases"] == SENTENCES and p["realisation"][0]["phrase"] == 1
    started = []
    import webapp.adaptation_routes as routes
    monkeypatch.setattr(routes, "_start_adaptation_step", lambda pid, step, only=None: started.append(step))
    r = client.post("/api/adaptations/ad_cp/choix-plans/2/ajout", json={"url": "https://youtu.be/y", "choix": {"1": "B"}})
    assert r.status_code == 200 and started == ["adding"] and ap.load("ad_cp")["choix_plans"] == {"1": "B"}
    q = ap.load("ad_cp")
    q["status"] = "stock_review"
    ap.save(q)
    r = client.post("/api/adaptations/ad_cp/choix-plans", json={"choix": {"1": "A"}})
    assert r.status_code == 200 and started[-1] == "voicing"


def test_the_ai_pre_ticks_from_the_descriptions(project):
    p = make("stock_review", stock=stock(), realisation=[entry(1), entry(2), entry(3, image="un tunnel")])

    class G:
        def _generate_content(self, parts, **kw):
            assert "un tunnel" in parts[0]["text"] and "D | D |" in parts[0]["text"]
            return {"choix": [{"phrase": 1, "plan": "B"}, {"phrase": 3, "plan": "D"}, {"phrase": 2, "plan": "B"},
                              {"phrase": 9, "plan": "A"}, {"phrase": 1, "plan": "inconnu"}]}
    picks = mp.ai_picks(p, gemini=G())
    assert picks == {"1": "B", "3": "D"}                                  # one shot a sentence, only real ones
    p["choix_ia"] = picks
    ph = mp.choices(p)["phrases"]
    assert ph[0]["ia"] == "B" and ph[0]["candidats"][0] == "B"
    assert ph[2]["ia"] == "D" and ph[2]["candidats"][0] == "D"
    assert ph[1]["ia"] == "G2"                                            # a graphic stays its sentence's pick

    class Down:
        def _generate_content(self, parts, **kw):
            raise RuntimeError("503")
    assert mp.ai_picks(p, gemini=Down()) == {}
