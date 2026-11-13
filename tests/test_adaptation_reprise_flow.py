"""A Reprise project from the friend's link to Publication, with the downloads, Gemini, ElevenLabs, the graphics
card and ffmpeg replaced by fakes: the steps, the cleaning beside them and its review, the script edits, the sound
rules (the smart music only on its channels, the voice kept when only the sound changes), a video's own settings,
the song's strip and what Publication receives."""

import json
import os

import pytest

import db
from adaptation import musique, pipeline as ap, reprise, reprise_montage as rm, reprise_pipeline as rp

SCRIPT = {"genre": "histoire", "reordonne": False, "pourquoi": "une suite", "titre": {"fr": "Le cochon", "ar": "الخنزير"},
          "youtube": {"fr": {"titre": "Ce cochon a survécu 🐷", "description": "Une histoire vraie. #shorts #cochon",
                             "tags": ["cochon", "sauvetage"]}, "ar": {"titre": "خنزير", "description": "قصة", "tags": ["خنزير"]}},
          "parties": [{"role": "accroche", "numero": None, "plans": [0], "fr": "Ce porcelet !", "ar": "هذا"},
                      {"role": "etape", "numero": None, "plans": [1], "fr": "Il grandit.", "ar": "كبر"}]}


@pytest.fixture
def fakes(monkeypatch, tmp_path):
    calls = {"voices": [], "beds": [], "clean": 0, "renders": []}
    from adaptation import reference, sources

    def download_short(url, d, name):
        path = os.path.join(d, name + ".mp4")
        open(path, "wb").write(b"x")
        json.dump({"handle": "@monami"}, open(path + ".meta.json", "w"))
        return path
    monkeypatch.setattr(sources, "download_short", download_short)
    monkeypatch.setattr(sources, "download_thumbnail", lambda url, d, name: None)
    monkeypatch.setattr(reference, "analyse", lambda url: {"sujet": "un cochon", "ton": "calme", "duree_s": 70,
                                                           "plans": [{"debut": 0, "fin": 40}, {"debut": 40, "fin": 110.0}]})
    monkeypatch.setattr(reprise, "probe", lambda path: {"w": 1080, "h": 1920, "rate": "30/1", "fps": 30.0, "duree": 70.0})
    monkeypatch.setattr(reprise, "find_elements", lambda src: [
        {"type": "sous_titres", "description": "sous-titres", "debut": 0, "fin": 70, "cadre": [0.1, 0.6, 0.9, 0.8], "action": "cacher"},
        {"type": "autocollant", "description": "croix rouge", "debut": 2, "fin": 4, "cadre": [0.3, 0.3, 0.6, 0.6],
         "action": "garder", "raison": "explique"}])

    def clean(src, els, out, work, progress=None):
        calls["clean"] += 1
        calls["kept"] = [e["description"] for e in els if e["action"] == "garder"]
        open(out, "wb").write(b"x")
        return {"images": 2100, "relues": 0}
    monkeypatch.setattr(reprise, "clean", clean)
    monkeypatch.setattr(rm, "write_script", lambda ref, codes, **kw: json.loads(json.dumps(SCRIPT)))

    def voice(script, code, voice_id, mp3, model=rm.MODEL, dialect=None):
        calls["voices"].append((code, voice_id, model))
        open(mp3, "wb").write(b"x")
        v = {"words": [], "passages": [{"start": 0.0}, {"start": 5.0}], "duration": 69.2}
        json.dump(v, open(mp3[:-4] + ".json", "w"))
        return v
    monkeypatch.setattr(rm, "voice", voice)

    def render(clean, plans, script, code, v, mp3, bed, out, work, y=rm.CAPTION_Y, captions=None, mastered=False):
        calls["renders"].append((code, bed and os.path.basename(bed)))
        calls.setdefault("sons", []).append((os.path.basename(mp3), mastered))
        open(out, "wb").write(b"x")
        return out
    monkeypatch.setattr(rm, "render", render)

    def bed(src, out, total, start=0.0, pad=0.0, gap=musique.GAP, lift_at=None):
        calls["beds"].append((os.path.basename(src), gap))
        open(out, "wb").write(b"x")
        return out
    monkeypatch.setattr(musique, "bed", bed)
    from adaptation import mixage
    monkeypatch.setattr(mixage, "bed", lambda src, out, total, start=0.0, pad=0.0, gap=7.0, lift_at=None, **kw:
                        bed(src, out, total, start, pad, gap, lift_at))
    monkeypatch.setattr(mixage, "music_source", lambda song, start, length: song)

    def track(voice, music, out, carve=True, punch=False, **kw):
        calls.setdefault("tracks", []).append((music and os.path.basename(music), carve))
        open(out, "wb").write(b"x")
        return out
    monkeypatch.setattr(mixage, "track", track)
    monkeypatch.setattr(musique, "plan", lambda d, sujet, ton, parts, total: {
        "fichier": "past.mp3", "titre": "Past Lives", "montee": 47.4, "partie": 1, "a": 5.0, "comment": "ok"})
    monkeypatch.setattr(musique, "listen", lambda path: {"moment_fort": 47.4, "montees": [47.4], "duree": 150.0})
    monkeypatch.setattr(musique, "placed_bed", lambda d, c, total, out, gap=musique.GAP: bed(c["fichier"], out, total, gap=gap))
    from roblox import voix
    monkeypatch.setattr(voix, "separate", lambda src, work: {"reste": "sa_musique.wav", "voix": "v.wav"})
    monkeypatch.setattr(ap, "project_dir", lambda pid: str(tmp_path / pid))
    monkeypatch.setattr(rp, "_spawn", lambda fn: fn())                      # the cleaning's thread: run at once
    monkeypatch.setattr(mixage, "audible", lambda path: (0.0, 150.0))
    monkeypatch.setattr(mixage, "placed", lambda src, start, total, pad=0.0, lift_at=None: (start, lift_at))
    monkeypatch.setattr(rp, "song_level", lambda path: [-20.0] * 300)
    monkeypatch.chdir(tmp_path)
    music = tmp_path / "music"
    music.mkdir()
    (music / "piste.mp3").write_bytes(b"x")
    calls["channels"] = [
        {"channel": "cestpourca", "profile": {"language_hint": "fr", "adaptation": {"voice_id": "vfr"}}, "music_dir": str(music)},
        {"channel": "lungtemotivates", "profile": {"language_hint": "ar", "adaptation": {"voice_id": "var", "music_file": "piste.mp3",
                                                                                         "voice_model": "eleven_flash_v2_5"}},
         "music_dir": str(music)}]
    return calls


def test_a_reprise_from_the_link_to_publication(fakes):
    p = ap.create("https://www.youtube.com/shorts/abc", [], fakes["channels"], mode="reprise", son="intelligente")
    pid = p["project_id"]
    assert p["mode"] == "reprise" and p["reprise"]["son"] == "intelligente"
    ap.runner_for(pid, "analysing")(pid)
    p = ap.load(pid)
    assert p["status"] == "script_review" and fakes["clean"] == 1           # the script did not wait for the cleaning
    assert rp.clean_state(p)["etat"] == "a_verifier"
    assert [x["fin"] for x in p["reprise"]["plans"]] == [40, 70.0]          # "1:10" written 110 read back
    assert fakes["kept"] == ["croix rouge"]

    rp.set_element(pid, 1, "cacher")                                         # the person hides the X after all
    rp.clean_again(pid)
    p = ap.load(pid)
    assert rp.clean_state(p)["etat"] == "a_verifier" and fakes["kept"] == [] and p["status"] == "script_review"
    assert [e["action"] for e in rp.elements_of(p)] == ["cacher", "cacher"]
    rp.edit_script(pid, "cestpourca", ["Ce petit cochon !", "Il a bien grandi."], "Le porcelet",
                   {"titre": "Ce porcelet a tout changé 🐷", "description": "Une histoire vraie. #shorts", "tags": ["#cochon", "ferme"]})
    with pytest.raises(ap.PipelineError):
        ap.start_voices(pid)                                                 # not every language approved yet
    ap.approve_script(pid, "cestpourca")
    ap.approve_script(pid, "lungtemotivates")
    ap.start_voices(pid)
    assert ap.load(pid)["status"] == "settings_review" and not fakes["voices"]   # the settings first: nothing paid yet
    rp.make_videos(pid)
    ap.runner_for(pid, "voicing")(pid)
    p = ap.load(pid)
    assert p["status"] == "cleaning_wait" and len(fakes["voices"]) == 2 and not fakes["renders"]  # the voices now
    p = rp.approve_cleaning(pid)
    assert p["status"] == "voicing"                                           # the videos once it is approved
    ap.runner_for(pid, "voicing")(pid)
    p = ap.load(pid)
    assert p["status"] == "preview_review"
    assert sorted(fakes["voices"]) == [("ar", "var", "eleven_flash_v2_5"), ("fr", "vfr", "eleven_v4")]
    # the smart music on its channel; the other one gets its own track (not on its list yet)
    assert sorted(fakes["beds"]) == [("past.mp3", 16.0), ("piste.mp3", 16.0)]
    assert sorted(fakes["tracks"]) == [("fond_intelligente.wav", True), ("fond_notre_musique.wav", True)]
    assert set(fakes["sons"]) == {("son.wav", True)}                         # the Short's sound made by mixage
    assert {t["channel"]: rp.son_for(p, t) for t in p["targets"]} == {"cestpourca": "intelligente",
                                                                     "lungtemotivates": "notre_musique"}
    f = rp.frise(p, p["targets"][0])                                         # the timeline of the preview
    assert f["total"] == 70.0 and [x["debut"] for x in f["parties"]] == [0.0, 5.0]
    assert f["images"] and all(a["fin"] <= b["debut"] + 0.01 for a, b in zip(f["images"], f["images"][1:]))
    assert f["images"][-1]["fin"] == 70.0 and f["son"] == "intelligente"
    place = os.path.join(ap.project_dir(pid), "cibles", "cestpourca", "fond_intelligente.wav.json")
    json.dump({"entree": 0.0, "montee": 5.0, "coupe": 67.5, "pas": 0.25, "niveau": [-30.0]}, open(place, "w"))
    assert rp.frise(p, p["targets"][0])["musique"]["titre"] == "Past Lives"

    rp.change_sound(pid, "sa_musique", 13)                                   # another sound: the voices are kept
    ap.runner_for(pid, "voicing")(pid)
    assert len(fakes["voices"]) == 2
    assert fakes["beds"][-2:] == [("sa_musique.wav", 13.0), ("sa_musique.wav", 13.0)]
    made = len(fakes["renders"])
    rp.change_sound(pid, "sa_musique", 13)                                   # the same sound again: nothing changed
    ap.runner_for(pid, "voicing")(pid)
    assert len(fakes["renders"]) == made and ap.load(pid)["status"] == "preview_review"
    rp.change_sound(pid, "sa_musique", 10)                                   # the music lower: made again
    ap.runner_for(pid, "voicing")(pid)
    assert len(fakes["renders"]) == made + 2

    ap.validate_preview(pid, "cestpourca")
    ap.start_render(pid)
    ap.runner_for(pid, "rendering")(pid)
    p = ap.load(pid)
    assert p["status"] == "preview_review"                                   # the Arabic one still waits
    rec = db.get_video(f"cestpourca_{pid}")
    assert rec["status"] == "ready_for_upload" and rec["original_title"] == "Ce porcelet a tout changé 🐷"
    assert rec["ai_data"]["description"] == "Une histoire vraie. #shorts"      # no credit line (taken out by hand)
    assert rec["ai_data"]["tags"] == ["cochon", "ferme"]
    assert rec["recette"]["mode"] == "reprise" and rec["recette"]["son"] == "sa_musique"


def _to_settings(fakes):
    p = ap.create("https://www.youtube.com/shorts/abc", [], fakes["channels"], mode="reprise", son="intelligente")
    pid = p["project_id"]
    ap.runner_for(pid, "analysing")(pid)
    rp.approve_cleaning(pid)
    for t in ap.load(pid)["targets"]:
        ap.approve_script(pid, t["channel"])
    ap.start_voices(pid)
    return pid


def test_the_settings_before_the_videos_then_on_the_previews(fakes, monkeypatch):
    pid = _to_settings(fakes)
    os.makedirs(rp.SHARED_MUSIC, exist_ok=True)
    open(os.path.join(rp.SHARED_MUSIC, "ma_chanson.mp3"), "wb").write(b"x")
    with pytest.raises(ap.PipelineError):
        rp.set_settings(pid, {"son": "choisie"})                              # a picked song needs its song
    with pytest.raises(ap.PipelineError):
        rp.set_settings(pid, {"sous_titres": {"style": "inconnu"}})
    monkeypatch.setattr(db, "get_voice", lambda vid: {"voice_id": vid} if vid == "vfr2" else None)
    p = rp.set_settings(pid, {"son": "choisie", "chanson": "ma_chanson.mp3", "partie": 1, "volume_db": 12,
                              "sous_titres": {"style": "hormozi", "params": {}},
                              "voix": {"cestpourca": {"voice_id": "vfr2", "model": "eleven_v3"}}})
    assert p["status"] == "settings_review"                                  # kept for the videos, nothing made
    r = p["reprise"]
    assert (r["son"], r["chanson"], r["partie"], r["volume_db"]) == ("choisie", "ma_chanson.mp3", 1, 12.0)
    assert r["sous_titres"]["style"] == "hormozi" and rp.captions_for(p, p["targets"][0])["style"] == "hormozi"
    assert (p["targets"][0]["voice_id"], p["targets"][0]["voice_model"]) == ("vfr2", "eleven_v3")
    assert [rp.son_for(p, t) for t in p["targets"]] == ["choisie", "notre_musique"]   # shared songs: its channels only
    monkeypatch.setattr(musique, "listen", lambda path: {"titre": "Ma chanson", "moment_fort": 30.0, "montees": [30.0], "duree": 150.0})
    v = rp.timings_of(p, p["targets"][0])                                    # no voice yet: estimated from the script
    assert v["passages"][1]["start"] > 0 and v["duration"] > v["passages"][1]["start"]
    assert all(a["end"] <= b["start"] for a, b in zip(v["words"], v["words"][1:]))
    path, start, lift = rp.song_plan(p, p["targets"][0], v, lambda *a: None)
    assert path.endswith("ma_chanson.mp3") and abs(lift - v["passages"][1]["start"]) < 0.01   # its rise on part 2
    rp.make_videos(pid)
    ap.runner_for(pid, "voicing")(pid)
    assert ("fr", "vfr2", "eleven_v3") in fakes["voices"]
    made = len(fakes["voices"])
    rp.set_settings(pid, {"volume_db": 20, "sous_titres": None})              # on the previews: made again …
    p = ap.load(pid)
    assert p["status"] == "voicing" and p["reprise"]["sous_titres"] is None and not any(t["validated"] for t in p["targets"])
    ap.runner_for(pid, "voicing")(pid)
    assert len(fakes["voices"]) == made                                       # … the voices kept


def test_no_music_and_a_channel_without_track(fakes):
    fakes["channels"][1]["profile"]["adaptation"].pop("music_file")
    p = ap.create("https://www.youtube.com/shorts/abc", [], fakes["channels"], mode="reprise", son="notre_musique")
    assert rp.son_for(p, p["targets"][1]) == "sans_musique"                  # no track: no music rather than a failure
    with pytest.raises(ap.PipelineError):
        ap.create("https://www.youtube.com/shorts/abc", [], fakes["channels"], mode="reprise", son="fanfare")


def test_a_failed_cleaning_is_retried(fakes, monkeypatch):
    p = ap.create("https://www.youtube.com/shorts/abc", [], fakes["channels"], mode="reprise")
    pid = p["project_id"]
    monkeypatch.setattr(reprise, "clean", lambda *a, **k: (_ for _ in ()).throw(reprise.RepriseError("carte pleine")))
    ap.runner_for(pid, "analysing")(pid)
    p = ap.load(pid)
    assert p["status"] == "script_review"                                    # the script goes on without it
    lane = rp.clean_state(p)
    assert lane["etat"] == "erreur" and "carte pleine" in lane["erreur"]
    with pytest.raises(ap.PipelineError):
        rp.approve_cleaning(pid)
    fakes_again = []
    monkeypatch.setattr(rp, "_spawn", lambda fn: fakes_again.append(fn))     # started again: in its thread
    rp.clean_again(pid)
    assert rp.clean_state(ap.load(pid))["etat"] == "en_cours" and len(fakes_again) == 1
    p = ap.load(pid)                                                          # a project cut on the old step
    p.update(status="error", failed_step="cleaning")
    ap.save(p)
    assert ap.retry(pid) == "cleaning"
    import progress
    progress.finish(rp.clean_job(pid))
    ap.runner_for(pid, "cleaning")(pid)
    assert ap.load(pid)["status"] == "script_review" and len(fakes_again) == 2   # on to its script, cleaned beside


def test_plans_written_in_minutes_and_seconds_are_read_back_for_every_mode():
    from adaptation import reference
    r = reference.plans_in_seconds({"duree_s": 122, "plans": [{"debut": 0, "fin": 56.7}, {"debut": 56.7, "fin": 100.7},
                                                              {"debut": 100.7, "fin": 162.2}]})
    assert [p["fin"] for p in r["plans"]] == [56.7, 60.7, 122.2]
    ok = {"duree_s": 50, "plans": [{"debut": 0, "fin": 50.0}]}
    assert reference.plans_in_seconds(json.loads(json.dumps(ok))) == ok


def test_the_voice_model_is_a_channel_setting():
    from adaptation import settings
    assert settings.channel_settings({"adaptation": {"voice_model": "eleven_v3"}})["voice_model"] == "eleven_v3"
    assert settings.channel_settings({"adaptation": {"voice_model": "inconnu"}})["voice_model"] is None
    assert settings.clean_update({"voice_model": "eleven_flash_v2_5"}) == {"voice_model": "eleven_flash_v2_5"}


def test_the_screen_gets_the_reprise(fakes, client):
    from webapp import adaptation_routes as routes
    p = ap.create("https://www.youtube.com/shorts/abc", [], fakes["channels"], mode="reprise", son="intelligente")
    ap.runner_for(p["project_id"], "analysing")(p["project_id"])
    s = routes._serialize_adaptation(ap.load(p["project_id"]))
    r = s["reprise"]
    assert s["mode"] == "reprise" and s["status"] == "script_review"
    assert r["lane"]["etat"] == "a_verifier" and not r["lane"]["interrompu"]
    assert r["son"] == "intelligente" and r["smart_channels"] == ["cestpourca", "lihadha_alsabab"]
    assert [e["action"] for e in r["elements"]] == ["cacher", "garder"] and r["credit"] == "@monami"
    assert r["original_url"].endswith("/reprise/video/original") and r["propre_url"].endswith("/reprise/video/propre")
    assert [t["son"] for t in s["targets"]] == ["intelligente", "notre_musique"]
    assert client.get(f"/api/adaptations/{p['project_id']}/reprise/video/nimporte").status_code == 404


def test_the_page_loads_the_reprise_screen(client):
    page = client.get("/").text
    assert "/static/js/reprise.js" in page and page.index("adaptation.js") < page.index("reprise.js")
    js = client.get("/static/js/reprise.js").text
    assert "function renderReprise" in js and "reprise/cleaning/approve" in js


def test_the_shared_songs_and_the_voice_model_in_reglages(client, monkeypatch, tmp_path):
    from adaptation import reprise_pipeline as rp
    monkeypatch.setattr(rp, "SHARED_MUSIC", str(tmp_path / "musiques"))
    os.makedirs(rp.SHARED_MUSIC)
    open(os.path.join(rp.SHARED_MUSIC, "Past Lives [iNa1n6Gch7E].mp3"), "wb").write(b"x")
    os.makedirs(os.path.join(rp.SHARED_MUSIC, ".analyses"))
    json.dump({"titre": "Past Lives", "humeur": "onirique", "montees": [15.6, 47.4]},
              open(os.path.join(rp.SHARED_MUSIC, ".analyses", "Past Lives [iNa1n6Gch7E].mp3.json"), "w"))
    d = client.get("/api/musiques").json()
    assert d["chaines_intelligentes"] == ["cestpourca", "lihadha_alsabab"]
    assert d["musiques"][0]["analyse"]["montees"] == [15.6, 47.4]
    assert client.get(d["musiques"][0]["url"]).status_code == 200
    assert client.get("/api/musiques/..%2F..%2Fconfig.yaml/audio").status_code == 404     # never outside the list
    started = []
    import webapp.adaptation_routes as routes
    monkeypatch.setattr(routes, "_analyse_song_later", lambda path: started.append(os.path.basename(path)))
    r = client.post("/api/musiques/fichier", files={"file": ("ma chanson.mp3", b"y", "audio/mpeg")})
    assert r.status_code == 200 and started == ["ma chanson.mp3"] and len(r.json()["musiques"]) == 2
    assert client.post("/api/musiques/fichier", files={"file": ("x.exe", b"y")}).status_code == 400
    assert len(client.delete("/api/musiques/ma%20chanson.mp3").json()["musiques"]) == 1


def test_a_video_set_apart_and_the_song_strip(fakes, monkeypatch):
    pid = _to_settings(fakes)
    os.makedirs(rp.SHARED_MUSIC, exist_ok=True)
    open(os.path.join(rp.SHARED_MUSIC, "ma_chanson.mp3"), "wb").write(b"x")
    monkeypatch.setattr(musique, "listen", lambda path: {"titre": "Ma chanson", "moment_fort": 30.0,
                                                         "montees": [12.0, 30.0, 60.0], "duree": 150.0})
    monkeypatch.setattr(rp, "SMART_CHANNELS", ("cestpourca", "lungtemotivates"))
    p = rp.set_settings(pid, {"son": "intelligente", "par_chaine": {
        "lungtemotivates": {"son": "choisie", "chanson": "ma_chanson.mp3", "partie": 1, "volume_db": 20}}})
    fr, ar = p["targets"]
    assert rp.son_for(p, fr) == "intelligente" and rp.son_for(p, ar) == "choisie"
    assert rp.opts(p, ar)["volume_db"] == 20.0 and rp.opts(p, fr)["volume_db"] == 16.0
    with pytest.raises(ap.PipelineError):
        rp.set_settings(pid, {"par_chaine": {"lungtemotivates": {"son": "fanfare"}}})

    w = rp.song_window(p, ar)                                                  # its strip: the part taken, its rises
    hit = w["partie_debut"]
    assert w["titre"] == "Ma chanson" and w["auto"] and w["montee_video"] == pytest.approx(hit)
    assert w["debut"] == pytest.approx(w["montee"] - hit) and w["montees"] == [m for m in (12.0, 30.0, 60.0) if m >= hit - 2]
    p = rp.set_settings(pid, {"par_chaine": {"lungtemotivates": {"montee_chanson": 60.0}}})   # another rise on the part
    w = rp.song_window(p, ar)
    assert w["montee"] == 60.0 and not w["auto"] and w["debut"] == pytest.approx(60.0 - hit)
    assert rp.song_window(p, fr) == {"attente": True}                          # Gemini has not chosen yet

    quiet = [-20.0] * 300                                                      # a whisper where the strong moment opens
    lo = int((30.0 - hit) / 0.5)
    quiet[lo:lo + 4] = [-50.0] * 4
    monkeypatch.setattr(rp, "song_level", lambda path: quiet)
    p = rp.set_settings(pid, {"par_chaine": {"lungtemotivates": {"montee_chanson": None}}})
    assert rp.song_window(p, ar)["montee"] != 30.0                            # the nearest rise opening on its sound

    rp.make_videos(pid)
    ap.runner_for(pid, "voicing")(pid)
    ap.validate_preview(pid, "cestpourca")
    made = len(fakes["renders"])
    p = rp.set_settings(pid, {"par_chaine": {"lungtemotivates": {"volume_db": 24}}})   # only the Arabic one changes
    assert p["status"] == "voicing"
    ap.runner_for(pid, "voicing")(pid)
    p = ap.load(pid)
    assert len(fakes["renders"]) == made + 1 and p["targets"][0]["validated"] and not p["targets"][1]["validated"]
    p = rp.set_settings(pid, {"par_chaine": {"lungtemotivates": None}})        # back to every video's settings
    assert p["reprise"]["par_chaine"] == {} and rp.son_for(p, p["targets"][1]) == "intelligente"
    assert p["status"] == "voicing"                                            # the Arabic one made again
