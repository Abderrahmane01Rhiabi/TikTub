"""Montage Roblox, the routes and the screen: a project created, its texts corrected, its Shorts made, watched and
sent to Publication, all through the API (YouTube, Gemini and ffmpeg faked, the background steps run inline)."""

import os

import db
from test_roblox_pipeline import fakes  # noqa: F401  (the fixture)


def inline(monkeypatch):
    import webapp.roblox_routes as rr
    from roblox import pipeline as rp
    monkeypatch.setattr(rr, "_start", lambda pid, step: rp.RUNNERS[step](pid))


def test_a_project_through_the_api(client, project, fakes, monkeypatch):
    inline(monkeypatch)
    project.add_channel("chanA")
    project.add_channel("chanB")
    body = {"url": "https://www.youtube.com/watch?v=NvGUWTH2U5Q", "styles": ["clip", "devine"],
            "cibles": [{"langue": "fr", "channel": "chanA", "voix": "Jrq4GqCKqYpigdQsZRkP"}, {"langue": "en", "channel": "chanB"}],
            "identite": True}
    r = client.post("/api/roblox", json=body)
    assert r.status_code == 200
    pid = r.json()["project_id"]
    p = client.get(f"/api/roblox/{pid}").json()
    assert p["status"] == "plan_review" and p["titre"] == "FUNNY MOMENTS" and p["noms_styles"]["devine"] == "Devine la suite"
    assert [(c["voix"], c["nom_voix"]) for c in p["cibles"]] == [("Jrq4GqCKqYpigdQsZRkP", "Anatole"), ("SA7eD52NRr8WAehitVt1", "Tyler")]
    assert p["voix_joueur"] == "remplacer" and p["identite"] is True
    assert p["moments"] == {"w0#0": "r", "w600#0": "r"}
    assert [x["project_id"] for x in client.get("/api/roblox").json()] == [pid]
    assert p["repliques"]["w0#0"]["lignes"][0]["fr"].startswith("[laughs]") and p["repliques"]["w0#0"]["styles"] == ["clip"]
    r = client.put(f"/api/roblox/{pid}/repliques", json={"moment": "w0#0", "langue": "fr", "lignes": ["Beurk !"]})
    assert r.status_code == 200 and r.json()["repliques"]["w0#0"]["lignes"][0]["fr"] == "Beurk !"
    assert p["joueurs"] == {"1": "Sunny", "2": ""} and p["cibles"][0]["voix_joueurs"]["1"]["nom"] == "Anatole"
    lucas = next(v["voice_id"] for v in client.get("/api/roblox/voix").json()["fr"] if v["nom"] == "Lucas")
    r = client.put(f"/api/roblox/{pid}/voix", json={"langue": "fr", "joueur": "2", "voix": lucas})
    assert r.status_code == 200 and r.json()["cibles"][0]["voix_joueurs"]["2"]["nom"] == "Lucas"
    r = client.put(f"/api/roblox/{pid}/textes", json={"style": "clip", "langue": "fr", "edit": {"titre": "Beurk"}})
    assert r.status_code == 200 and r.json()["plan"]["clip"]["titre"]["fr"] == "Beurk"
    p = client.post(f"/api/roblox/{pid}/render").json()
    p = client.get(f"/api/roblox/{pid}").json()
    assert p["status"] == "review" and sorted(p["videos"]) == ["clip_en", "clip_fr", "devine_en", "devine_fr"]
    assert client.get(p["videos"]["clip_fr"]["url"]).status_code == 200
    r = client.post(f"/api/roblox/{pid}/send", json={"videos": ["clip_fr"]})
    assert r.status_code == 200 and r.json()["videos"]["clip_fr"]["video_id"] == f"chanA_{pid}_clip_fr"
    assert db.get_video(f"chanA_{pid}_clip_fr")["status"] == "ready_for_upload"
    assert client.delete(f"/api/roblox/{pid}").status_code == 200
    assert client.get(f"/api/roblox/{pid}").status_code == 400
    assert db.get_video(f"chanA_{pid}_clip_fr")                                  # what was sent stays in Publication


def test_wrong_requests_are_refused_plainly(client, project, monkeypatch):
    inline(monkeypatch)
    project.add_channel("chanA")
    ok = {"url": "https://y", "styles": ["clip"], "cibles": [{"langue": "fr", "channel": "chanA"}]}
    assert client.post("/api/roblox", json={**ok, "styles": []}).json()["detail"] == "Choisis au moins un style."
    assert client.post("/api/roblox", json={**ok, "cibles": [{"langue": "fr", "channel": "nope"}]}).status_code == 404
    assert client.post("/api/roblox/rb_x/render").status_code == 400


def test_a_failed_step_can_be_run_again(client, project, fakes, monkeypatch):
    from roblox import moments
    inline(monkeypatch)
    project.add_channel("chanA")
    found = {"n": 0}

    def find(path, dur):
        found["n"] += 1
        return [] if found["n"] <= 2 else [{"debut": 10.0, "fin": 22.0, "chute": 18.0, "resume": "r"}]
    monkeypatch.setattr(moments, "find", find)
    pid = client.post("/api/roblox", json={"url": "https://y", "styles": ["clip"], "cibles": [{"langue": "fr", "channel": "chanA"}]}).json()["project_id"]
    assert client.get(f"/api/roblox/{pid}").json()["status"] == "error"
    assert client.post(f"/api/roblox/{pid}/retry").status_code == 200
    assert client.get(f"/api/roblox/{pid}").json()["status"] == "plan_review"


def test_the_screen_is_in_the_app():
    static = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "webapp", "static")
    html = open(os.path.join(static, "index.html"), encoding="utf-8").read()
    core = open(os.path.join(static, "js", "core.js"), encoding="utf-8").read()
    js = open(os.path.join(static, "js", "roblox.js"), encoding="utf-8").read()
    assert 'data-space="roblox"' in html and 'id="robloxScreen"' in html and "/static/js/roblox.js" in html
    assert "openRoblox()" in core and "robloxScreen" in core
    assert "async function loadRbProject" in js and js.count("esc(") > 20


def test_a_background_step_that_breaks_never_leaves_the_project_stuck(client, project, fakes, monkeypatch):
    import time
    import webapp.roblox_routes as rr
    from roblox import pipeline as rp
    project.add_channel("chanA")
    pid = rp.create("https://y", ["clip"], [{"langue": "fr", "channel": "chanA", "profile": {}, "music_dir": "x"}])["project_id"]

    def broken(pid, report=None):
        raise SystemExit("arrêt brutal")                    # not an Exception: it used to end the thread silently
    monkeypatch.setitem(rp.RUNNERS, "analysing", broken)
    rr._start(pid, "analysing")
    for _ in range(50):
        if rp.load(pid)["status"] == "error":
            break
        time.sleep(0.1)
    p = rp.load(pid)
    assert p["status"] == "error" and "arrêt brutal" in p["error"] and p["failed_step"] == "analysing"



def test_more_moments_through_the_api(client, project, fakes, monkeypatch):
    inline(monkeypatch)
    project.add_channel("chanA")
    pid = client.post("/api/roblox", json={"url": "https://y.com/v", "styles": ["clip"],
                                           "cibles": [{"langue": "fr", "channel": "chanA"}]}).json()["project_id"]
    r = client.post(f"/api/roblox/{pid}/suite")
    assert r.status_code == 200 and r.json()["project_id"] != pid and r.json()["suite"] is True
    p = client.get(f"/api/roblox/{pid}").json()
    assert p["video"]["passages"] == 4 and p["video"]["projets"] == 2
