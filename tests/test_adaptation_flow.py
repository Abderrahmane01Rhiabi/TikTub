"""An adaptation project from link to Publication, with Gemini, ElevenLabs
and ffmpeg replaced by fakes: the steps, the mandatory reviews, the errors
and retries, and what Publication receives."""

import json
import time
from pathlib import Path

import pytest

import db
from adaptation import pipeline as ap

CLIPS = {"A": {"id": "A", "source": 0, "src": "s0.mp4", "start": 0, "end": 5, "impact": 2, "w": 480, "h": 456,
               "usable": True, "desc": "choc", "marks": ["logo TikTok @azzamyreal"]},
         "B": {"id": "B", "source": 1, "src": "s1.mp4", "start": 0, "end": 6, "impact": 3, "w": 1080, "h": 608,
               "usable": True, "desc": "SUV", "marks": ["logo 9NEWS"]},
         "C": {"id": "C", "source": 1, "src": "s1.mp4", "start": 6, "end": 9, "impact": 7, "w": 1080, "h": 608,
               "usable": False, "why_not": "interview", "marks": []}}
SCRIPT = {"titre": "Pourquoi ?", "description": "Une explication.", "tags": ["tram"], "passages": [
    {"clip": "A", "bandeau": "TRAM : POURQUOI ? 😐", "texte": "Pourquoi ?", "mots_cles": ["Pourquoi"]},
    {"clip": "B", "bandeau": "SUV : CHOC 🚗", "texte": "Parce que.", "mots_cles": []},
    {"clip": "A", "bandeau": "FIN : CALME 🧘", "texte": "Voilà pourquoi.", "mots_cles": []}]}


@pytest.fixture
def fakes(monkeypatch):
    calls = {"synth": 0, "reference": 0, "analysed": []}
    from adaptation import checks, finder, reference, render, script, sources, voices

    def analyse_ref(url):
        calls["reference"] += 1
        return {"sujet": "trams", "question": "pourquoi", "plans": [{}]}
    monkeypatch.setattr(reference, "analyse", analyse_ref)
    monkeypatch.setattr(finder, "suggest", lambda ref, url="", report=None: {
        "comptes": [], "verifs": {},
        "scenes": [{"scene": "un tram qui percute une voiture", "recherches": ["tram crash"], "indices": "",
                    "candidats": [{"url": "https://www.youtube.com/watch?v=aaaaaaaaaaa", "duration": 600}]}]})
    calls["sections"] = {}

    def download(url, d, name, sections=None):
        calls["sections"][url] = sections
        return f"{d}/{name}.mp4"
    monkeypatch.setattr(sources, "download", download)
    monkeypatch.setattr(sources, "source_meta", lambda p: {"handle": "@reposter"})
    def analyse_source(path, i, work, ids):
        calls["analysed"].append(i)
        return [dict(c) for c in CLIPS.values() if c["source"] == i]
    monkeypatch.setattr(sources, "analyse_source", analyse_source)
    monkeypatch.setattr(script, "write", lambda ref, clips, lang: json.loads(json.dumps(SCRIPT)))
    monkeypatch.setattr(script, "critique", lambda sc, lang, clips: {**sc, "corrections": ["fin complète"]})

    def synth(passages, voice_id, lang, out):
        calls["synth"] += 1
        return {"words": [], "passages": passages, "duration": 5.0}
    monkeypatch.setattr(voices, "synthesize", synth)

    def fake_render(passages, words, clips, voice, lang, out, work, credit="", music=None, preview=False, progress_cb=None):
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(b"mp4")
        return {"duration": 5.0, "segments": [], "captions": 2}
    monkeypatch.setattr(render, "render", fake_render)
    calls["checks_ok"] = True
    monkeypatch.setattr(checks, "verify", lambda out, voice, passages: {
        "ok": calls["checks_ok"], "problems": [] if calls["checks_ok"] else ["son trop court"], "measures": {}})
    return calls


def channel(project, name="chanA", lang="fr", voice="v_fr"):
    project.add_channel(name)
    (Path("channels") / name / "profile.json").write_text(json.dumps(
        {"language_hint": lang, "adaptation": {"voice_id": voice}}))
    db.upsert_voice({"voice_id": voice, "name": voice, "language": lang})
    return {"channel": name, "profile": json.loads((Path("channels") / name / "profile.json").read_text()),
            "music_dir": str(Path("channels") / name / "assets" / "music")}


def new_project(project):
    return ap.create("https://youtube.com/shorts/x", ["https://tiktok.com/a", "https://tiktok.com/b"],
                     [channel(project), channel(project, "chanB", "ar", "v_ar")])


def test_full_project_from_link_to_publication(project, fakes):
    p = new_project(project)
    ap.run_analysis(p["project_id"])
    p = ap.load(p["project_id"])
    assert p["status"] == "sources_review" and set(p["clips"]) == {"A", "B", "C"}
    assert p["credits"] == "@azzamyreal · 9NEWS"            # the watermark names, not the re-uploader

    ap.set_sources(p["project_id"], {"B": False}, "@azzamyreal · 9News")
    ap.set_sources(p["project_id"], {"B": True})
    ap.start_scripts(p["project_id"])
    ap.run_scripts(p["project_id"])
    p = ap.load(p["project_id"])
    assert p["status"] == "script_review" and all(t["script"]["corrections"] for t in p["targets"])

    with pytest.raises(ap.PipelineError):                    # every script must be approved first
        ap.start_voices(p["project_id"])
    for t in p["targets"]:
        ap.approve_script(p["project_id"], t["channel"])
    ap.start_voices(p["project_id"])
    ap.run_voices(p["project_id"])
    p = ap.load(p["project_id"])
    assert p["status"] == "preview_review" and fakes["synth"] == 2

    ap.validate_preview(p["project_id"], "chanA")
    ap.start_render(p["project_id"])
    ap.run_final(p["project_id"])
    p = ap.load(p["project_id"])
    assert p["status"] == "preview_review"                   # chanB not validated yet: the project waits
    assert fakes["synth"] == 2                               # the final render reuses the narration
    video = db.get_video(p["targets"][0]["video_id"])
    assert video["status"] == "ready_for_upload" and video["channel"] == "chanA"
    assert video["ai_data"]["optimized_title"] == "Pourquoi ?"
    assert video["ai_data"]["description"].endswith("Images : @azzamyreal · 9News")
    assert Path(video["video_path"]).exists()

    ap.validate_preview(p["project_id"], "chanB")
    ap.start_render(p["project_id"])
    ap.run_final(p["project_id"])
    assert ap.load(p["project_id"])["status"] == "done"
    assert "المصدر:" in db.get_video(f"chanB_{p['project_id']}")["ai_data"]["description"]


def test_a_script_with_problems_cannot_be_approved(project, fakes):
    p = new_project(project)
    ap.run_analysis(p["project_id"]); ap.start_scripts(p["project_id"]); ap.run_scripts(p["project_id"])
    bad = {"passages": [{"clip": "A", "texte": "Et donc :", "bandeau": "X", "mots_cles": []}]}
    p = ap.edit_script(p["project_id"], "chanA", bad)
    assert "incomplète" in " ".join(ap.target(p, "chanA")["problems"])
    with pytest.raises(ap.PipelineError, match="incomplète"):
        ap.approve_script(p["project_id"], "chanA")


def test_a_failed_check_blocks_the_validation_and_a_voice_change_redoes_one_target(project, fakes):
    p = new_project(project)
    pid = p["project_id"]
    ap.run_analysis(pid); ap.start_scripts(pid); ap.run_scripts(pid)
    for ch in ("chanA", "chanB"):
        ap.approve_script(pid, ch)
    fakes["checks_ok"] = False
    ap.start_voices(pid); ap.run_voices(pid)
    with pytest.raises(ap.PipelineError, match="contrôle"):
        ap.validate_preview(pid, "chanA")
    fakes["checks_ok"] = True
    db.upsert_voice({"voice_id": "v_fr2", "name": "autre", "language": "fr"})
    ap.change_voice(pid, "chanA", "v_fr2")
    before = fakes["synth"]
    ap.run_voices(pid, only="chanA")
    assert fakes["synth"] == before + 1                      # only chanA was narrated again
    assert ap.target(ap.load(pid), "chanA")["voice_id"] == "v_fr2"
    ap.validate_preview(pid, "chanA")


def test_a_failure_marks_the_step_and_retry_resumes_it(project, fakes, monkeypatch):
    from adaptation import reference
    p = new_project(project)
    monkeypatch.setattr(reference, "analyse", lambda url: (_ for _ in ()).throw(RuntimeError("Gemini HS")))
    ap.run_analysis(p["project_id"])
    p = ap.load(p["project_id"])
    assert p["status"] == "error" and p["failed_step"] == "analysing" and "Gemini HS" in p["error"]
    assert ap.retry(p["project_id"]) == "analysing" and ap.load(p["project_id"])["status"] == "analysing"


def test_a_channel_without_voice_cannot_be_a_target(project):
    project.add_channel("chanZ")
    with pytest.raises(ap.PipelineError, match="voix"):
        ap.create("https://x", ["https://y"], [{"channel": "chanZ", "profile": {}, "music_dir": "."}])


def test_restart_marks_running_steps_as_failed(project):
    db.save_adaptation({"project_id": "ad_1", "status": "voicing", "targets": []})
    db.save_adaptation({"project_id": "ad_2", "status": "script_review", "targets": []})
    assert ap.recover_interrupted() == 1
    p = ap.load("ad_1")
    assert p["status"] == "error" and p["failed_step"] == "voicing"
    assert ap.load("ad_2")["status"] == "script_review"


def test_api_runs_the_analysis_in_the_background(client, project, fakes):
    channel(project)
    r = client.post("/api/adaptations", json={"reference_url": "https://youtube.com/shorts/x",
                                              "source_urls": ["https://tiktok.com/a", "https://tiktok.com/b"],
                                              "channels": ["chanA"]})
    assert r.status_code == 200
    pid = r.json()["project_id"]
    for _ in range(50):
        if client.get(f"/api/adaptations/{pid}").json()["status"] != "analysing":
            break
        time.sleep(0.1)
    p = client.get(f"/api/adaptations/{pid}").json()
    assert p["status"] == "sources_review" and {c["id"] for c in p["clips"]} == {"A", "B", "C"}
    assert client.post(f"/api/adaptations/{pid}/voices").status_code == 400       # not at that step
    assert client.post("/api/adaptations", json={"reference_url": " ", "source_urls": [],
                                                 "channels": ["chanA"]}).status_code == 400


def test_without_sources_the_app_says_what_to_download_then_analyses_the_picks(project, fakes, monkeypatch):
    from adaptation import finder
    p = ap.create("https://youtube.com/shorts/x", [], [channel(project)])
    pid = p["project_id"]
    ap.run_analysis(pid)
    p = ap.load(pid)
    assert p["status"] == "sources_search" and p["clips"] == {}
    assert p["suggestions"]["scenes"][0]["scene"] == "un tram qui percute une voiture"
    with pytest.raises(ap.PipelineError):                    # nothing picked
        ap.add_sources(pid, ["  "])

    monkeypatch.setattr(finder, "check", lambda url, scene: {"verdict": "oui", "moments": [{"debut": 3, "fin": 6}],
                                                             "qualite": "bonne", "raison": "même accident"})
    url = "https://www.youtube.com/watch?v=aaaaaaaaaaa"
    p = ap.check_candidate(pid, 0, url)
    assert p["suggestions"]["verifs"][url]["verdict"] == "oui"
    assert ap.check_candidate(pid, -1, url)["suggestions"]["verifs"][url]["scene"] == -1   # any scene

    ap.add_sources(pid, [url])
    assert ap.load(pid)["status"] == "analysing"
    ap.run_analysis(pid)
    p = ap.load(pid)
    assert p["status"] == "sources_review" and set(p["clips"]) == {"A"}
    assert fakes["reference"] == 1                           # the reference is read once
    assert fakes["sections"][url] == [[0.0, 12.0]]            # a verified 10-min video: only its moment

    ap.set_sources(pid, credits="@moi")                      # a correction is never overwritten
    ap.add_sources(pid, [url, "https://tiktok.com/b"])       # already there: ignored
    ap.run_analysis(pid)
    p = ap.load(pid)
    assert fakes["analysed"] == [0, 1]                       # only the new source was analysed
    assert set(p["clips"]) == {"A", "B", "C"} and p["credits"] == "@moi"
    assert p["source_urls"] == [url, "https://tiktok.com/b"]


def test_api_add_sources_and_check(client, project, fakes, monkeypatch):
    from adaptation import finder
    channel(project)
    pid = client.post("/api/adaptations", json={"reference_url": "https://youtube.com/shorts/x", "source_urls": [],
                                                "channels": ["chanA"]}).json()["project_id"]
    for _ in range(50):
        if client.get(f"/api/adaptations/{pid}").json()["status"] != "analysing":
            break
        time.sleep(0.1)
    p = client.get(f"/api/adaptations/{pid}").json()
    assert p["status"] == "sources_search" and p["suggestions"]["scenes"]
    monkeypatch.setattr(finder, "check", lambda url, scene: (_ for _ in ()).throw(finder.FinderError("lien YouTube")))
    r = client.post(f"/api/adaptations/{pid}/suggestions/check", json={"scene": 0, "url": "https://tiktok.com/x"})
    assert r.status_code == 400 and "YouTube" in r.json()["detail"]
    assert client.post(f"/api/adaptations/{pid}/sources/add", json={"urls": []}).status_code == 400
    r = client.post(f"/api/adaptations/{pid}/sources/add", json={"urls": ["https://tiktok.com/a"]})
    assert r.status_code == 200
