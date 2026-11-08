"""The timeline's server side (2026-11-08): the person's montage is checked, kept (« Annuler »), the preview before it
kept (« Avant / Après »), and only the render is made again — no voice, no AI."""

import pytest

from adaptation import montage_doc as md
from adaptation import montage_pro as mp
from adaptation import pipeline as ap

VOICE = {"passages": [{"start": 0.0, "end": 2.8, "words": [0, 1]}, {"start": 3.0, "end": 6.5, "words": [2, 3]}],
         "words": [{"w": w, "start": s, "end": s + 0.4} for w, s in [("Pourquoi", 0.0), ("700", 1.2), ("Depuis", 3.0),
                                                                     ("quatre", 4.4)]]}
EDL = [{"phrase": 1, "plan": "a", "debut": 0.0, "fin": 3.0}, {"phrase": 2, "plan": "b", "debut": 3.0, "fin": 7.1}]


def save(status="preview_review"):
    t = {"channel": "chanA", "language": "fr", "voice_id": "m", "voice": VOICE,
         "script": {"passages": [{"texte": "a", "bandeau": "ORQUES : 700"}, {"texte": "b", "bandeau": "MYSTÈRE"}]},
         "montage": md.new(EDL, 2, None, 0.0, []), "preview": {"path": "x/preview.mp4"}}
    ap.save({"project_id": "ad_t", "status": status, "pro": True, "targets": [t],
             "stock": [{"id": k, "garde": True, "start": 0, "end": 5, "file": f"{k}.mp4"} for k in "abc"]})


def changed(**plan):
    d = md.new(EDL, 2, None, 0.0, [])
    d["plans"][1].update(plan)
    return d


def test_the_person_s_montage_is_kept_and_only_rendered_again():
    save()
    t = ap.target(mp.set_montage("ad_t", "chanA", changed(zoom=1.3)), "chanA")
    p = ap.load("ad_t")
    assert p["status"] == "voicing" and t["rerender"] and t["montage"]["plans"][1]["zoom"] == 1.3
    assert len(t["montage_versions"]) == 1 and t["montage_jump"] == 3.0 and not t["montage_son"]


def test_nothing_changed_or_a_wrong_shot_is_said_and_nothing_is_rendered():
    save()
    with pytest.raises(ap.PipelineError, match="Rien n'a changé"):
        mp.set_montage("ad_t", "chanA", md.new(EDL, 2, None, 0.0, []))
    with pytest.raises(ap.PipelineError, match="plus dans ton stock"):
        mp.set_montage("ad_t", "chanA", changed(plan="zz"))
    assert ap.load("ad_t")["status"] == "preview_review"


def test_annuler_goes_back_to_the_montage_before():
    save()
    mp.set_montage("ad_t", "chanA", changed(zoom=1.3))
    p = ap.load("ad_t")
    p["status"] = "preview_review"
    ap.save(p)
    t = ap.target(mp.undo_montage("ad_t", "chanA"), "chanA")
    assert t["montage"]["plans"][1]["zoom"] == 1.0 and t["montage_versions"] == [] and t["rerender"]


def test_the_step_renders_the_person_s_montage_without_voice_or_ai(monkeypatch):
    save()
    mp.set_montage("ad_t", "chanA", changed(zoom=1.3))
    monkeypatch.setattr(mp, "make_target", lambda *a, **k: pytest.fail("no new voice nor AI edit"))
    monkeypatch.setattr(mp, "render_target", lambda p, t, report=None: {"path": "x", "credits": [], "zoom": t["montage"]["plans"][1]["zoom"]})
    mp.run_montage("ad_t")
    p = ap.load("ad_t")
    assert p["status"] == "preview_review" and p["targets"][0]["preview"]["zoom"] == 1.3
    assert "rerender" not in p["targets"][0]


def test_the_timeline_gets_the_montage_the_sentences_and_what_can_be_used(monkeypatch):
    save()
    monkeypatch.setattr(mp, "music_choices", lambda t: [])
    out = mp.timeline(ap.load("ad_t"), ap.target(ap.load("ad_t"), "chanA"))
    assert out["total"] == 7.1 and [x["bandeau"] for x in out["phrases"]] == ["ORQUES 700", "MYSTÈRE"]
    assert [x["id"] for x in out["stock"]] == ["a", "b", "c"] and out["mots"][1] == ["700", 1.2, 1.6]
    assert "karaoke" in {x["id"] for x in out["styles_sous_titres"]} and out["cadres"][0] == "noir"


def test_the_routes(client, project, monkeypatch):
    from webapp import adaptation_routes as r
    project.add_channel("chanA")
    save()
    started = []
    monkeypatch.setattr(r, "_start_adaptation_step", lambda pid, step, only=None: started.append((step, only)))
    monkeypatch.setattr(mp, "music_choices", lambda t: [])
    got = client.get("/api/adaptations/ad_t/targets/chanA/montage")
    assert got.json()["total"] == 7.1, got.text
    res = client.post("/api/adaptations/ad_t/targets/chanA/montage", json={"doc": changed(zoom=1.2)})
    assert res.status_code == 200, res.text
    assert started == [("voicing", "chanA")] and res.json()["targets"][0]["montage_versions"] == 1
    busy = client.post("/api/adaptations/ad_t/targets/chanA/montage", json={"doc": changed(zoom=1.4)})
    assert busy.status_code == 400 and "voicing" in busy.text                   # one render at a time
    p = ap.load("ad_t")
    p["status"] = "preview_review"
    ap.save(p)
    bad = client.post("/api/adaptations/ad_t/targets/chanA/montage", json={"doc": changed(plan="zz")})
    assert bad.status_code == 400 and "stock" in bad.text


def test_the_check_looks_for_each_sentence_where_the_voice_says_it_not_at_a_moved_cut(monkeypatch):
    save()
    p = ap.load("ad_t")
    t = p["targets"][0]
    t["montage"]["plans"][1]["debut"] = 4.4                     # the cut dragged away from sentence 2's start (3.0)
    t["montage"]["plans"][0]["fin"] = 4.4
    seen = {}
    monkeypatch.setattr(mp, "render_doc", lambda *a, **k: {"captions": {"position": "bas", "y": 1, "taille": 96, "police": "f",
                        "mots_par_ligne": 3, "mot_dit": "#fff", "bandeau": {}}, "duree": 7.1})
    monkeypatch.setattr(mp.checks, "verify", lambda out, mp3, passages, starts: seen.update(starts=starts) or {"ok": True})
    monkeypatch.setattr(mp, "recipe", lambda *a, **k: {})
    mp.render_target(p, t)
    assert seen["starts"] == [0.0, 3.0]


NEW_VOICE = {"passages": [{"start": 0.0, "end": 2.8, "words": [0, 1]}, {"start": 3.0, "end": 8.5, "words": [2, 3, 4]}],
             "words": [{"w": w, "start": s, "end": s + 0.4} for w, s in [("Pourquoi", 0.0), ("700", 1.2), ("Depuis", 3.0),
                                                                         ("bien", 4.6), ("quatre", 6.0)]], "texts": ["x"]}


def test_a_new_voice_keeps_every_cut_sound_and_zone_at_its_place_in_its_sentence():
    d = md.new(EDL, 2, None, 0.0, [{"kind": "pop", "file": "f", "start": 4.75, "gain": 0.3}])
    d["plans"][1]["debut"] = 4.4                                  # half-way into sentence 2 (3.0 -> 7.1)
    d["musique"]["zones"] = [{"debut": 3.0, "fin": 7.1, "volume": 40}]
    out = md.retime(d, VOICE, NEW_VOICE, [1])
    assert out["plans"][1]["debut"] == pytest.approx(3.0 + (1.4 / 4.1) * 6.1, abs=0.01)
    assert out["effets"][0]["start"] == pytest.approx(3.0 + (1.75 / 4.1) * 6.1, abs=0.01)
    assert out["musique"]["zones"][0] == {"debut": 3.0, "fin": 9.1, "volume": 40}


def test_a_sentence_s_new_text_or_manner_is_checked():
    save()
    with pytest.raises(ap.PipelineError, match="vide"):
        mp.set_montage("ad_t", "chanA", md.new(EDL, 2, None, 0.0, []), [{"i": 1, "texte": "  "}])
    with pytest.raises(ap.PipelineError, match="pas permise"):
        mp.set_montage("ad_t", "chanA", md.new(EDL, 2, None, 0.0, []), [{"i": 1, "maniere": "excite"}])
    t = ap.target(mp.set_montage("ad_t", "chanA", md.new(EDL, 2, None, 0.0, []), [{"i": 1, "texte": "Depuis bien quatre"}]),
                  "chanA")
    assert t["voix_edits"] == [{"i": 1, "texte": "Depuis bien quatre", "maniere": ""}] and t["montage_jump"] == 3.0


def test_the_voice_is_said_again_the_montage_moved_onto_it_and_annuler_brings_the_old_voice_back(monkeypatch, tmp_path):
    save()
    p = ap.load("ad_t")
    import os
    os.makedirs(os.path.join(ap.project_dir("ad_t"), "chanA"), exist_ok=True)
    mp3 = os.path.join(ap.project_dir("ad_t"), "chanA", "voice.mp3")
    open(mp3, "w").write("old voice")
    mp.set_montage("ad_t", "chanA", md.new(EDL, 2, None, 0.0, []), [{"i": 1, "texte": "Depuis bien quatre"}])
    said = []
    def fake_voice(p, t, path, report, at):
        said.append(t["script"]["passages"][1]["texte"])
        open(path, "w").write("new voice")
        return NEW_VOICE
    monkeypatch.setattr(mp, "_voice", fake_voice)
    monkeypatch.setattr(mp, "render_target", lambda p, t, report=None: {"path": "x", "credits": []})
    mp.run_montage("ad_t")
    assert ap.load("ad_t")["status"] == "preview_review", ap.load("ad_t").get("error")
    t = ap.load("ad_t")["targets"][0]
    assert said == ["Depuis bien quatre"] and t["voice"] == NEW_VOICE and t["manieres_by"] == "toi"
    assert t["montage"]["plans"][-1]["fin"] == 9.1 and open(mp3).read() == "new voice"
    t2 = ap.target(mp.undo_montage("ad_t", "chanA"), "chanA")
    assert t2["script"]["passages"][1]["texte"] == "b" and t2["voice"]["passages"][1]["end"] == 6.5
    assert open(mp3).read() == "old voice" and "_voix" not in t2["montage"]
