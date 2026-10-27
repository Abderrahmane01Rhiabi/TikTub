"""ECONOMIES_IA.md, the 🟢: work already done and still valid is not paid again —
and a result is reused only while everything it depends on is unchanged."""

import json

import pytest

from adaptation import pipeline as ap
from adaptation import script


def _clips():
    return {f"P{k}": {"id": f"P{k}", "source": k - 1, "start": 0, "end": 4, "impact": 1, "usable": True, "marks": [],
                      "desc": f"plan {k}"} for k in (1, 2, 3, 4)}


def _verdicts(sc):
    return [{"clip": x["clip"], "texte": x["texte"], "note": "bon", "pourquoi": "", "proposition": "", "autre_clip": None}
            for x in sc["passages"]]


# ---- G1: after a hand change or a swap, only the sentences concerned are judged again

def test_only_the_changed_sentence_is_judged_again(monkeypatch):
    judged = []
    monkeypatch.setattr(ap, "_judge", lambda sc, clips, code, work=None: judged.append(sc) or _verdicts(sc))
    p = {"project_id": "x", "clips": _clips()}
    old = [{"clip": "P1", "texte": "A.", "note": "non", "pourquoi": "labo", "garde": True},
           {"clip": "P2", "texte": "B.", "note": "moyen", "pourquoi": "flou"},
           {"clip": "P3", "texte": "C.", "note": "bon", "pourquoi": ""}]
    t = {"channel": "c", "language": "fr", "accords": [dict(a) for a in old],
         "script": {"passages": [{"clip": "P1", "texte": "A."}, {"clip": "P2", "texte": "B, réécrite."},
                                 {"clip": "P3", "texte": "C."}]}}

    ap._rejudge(p, t)

    assert [[x["texte"] for x in sc["passages"]] for sc in judged] == [["B, réécrite."]]   # one sentence, not three
    assert set(judged[0]["clips_utilises"]) == {"P1", "P2", "P3"}     # never offered a clip another sentence uses
    assert t["accords"][0] == old[0] and t["accords"][2] == old[2]    # the others keep their verdict ("garder" too)
    assert t["accords"][1]["texte"] == "B, réécrite." and t["accords"][1]["note"] == "bon"


def test_a_changed_clip_is_judged_again_even_with_the_same_words(monkeypatch):
    judged = []
    monkeypatch.setattr(ap, "_judge", lambda sc, clips, code, work=None: judged.append(sc) or _verdicts(sc))
    old = [{"clip": "P1", "texte": "A.", "note": "bon"}, {"clip": "P2", "texte": "B.", "note": "non", "autre_clip": "P4"}]
    sc = {"passages": [{"clip": "P1", "texte": "A."}, {"clip": "P4", "texte": "B."}]}       # the judge's swap
    out = ap._judge_changed(sc, _clips(), "fr", None, old)
    assert [x["clip"] for x in judged[0]["passages"]] == ["P4"] and out[0] == old[0] and out[1]["clip"] == "P4"
    assert ap._judge_changed(sc, _clips(), "fr", None, out) == out and len(judged) == 1    # nothing new: no call


def test_the_match_never_offers_a_clip_an_unjudged_sentence_uses():
    class G:
        def _generate_content(self, parts, **kw):
            G.prompt = parts[0]["text"]
            return {"passages": [{"note": "non", "pourquoi": "x", "autre_clip": "P1"}]}
    out = script.match({"passages": [{"clip": "P2", "texte": "B."}], "clips_utilises": ["P1", "P2", "P3"]},
                       _clips(), "fr", gemini=G())
    assert "P1 : plan 1" not in G.prompt and "P4 : plan 4" in G.prompt and out[0]["autre_clip"] is None


# ---- G2: the 2nd round of storyboard fixes judges only the plans the fix changed

def test_the_second_round_judges_only_the_plans_the_fix_changed(project, monkeypatch):
    from adaptation import storyboard as sb
    from test_adaptation_storyboard import GOOD, channel
    p = ap.create("https://youtube.com/shorts/x", [], [channel(project, "chanA", "fr", "v_fr")], mode="script")
    p["reference"] = {"sujet": "trams", "question": "?", "plans": [{}]}
    ap.save(p)
    monkeypatch.setattr(sb, "write", lambda ref, codes, angle=None: sb.normalise(json.loads(json.dumps(GOOD)), codes))
    monkeypatch.setattr(sb, "critique", lambda b, codes: b)
    judged = []

    def match(sc, clips, code, gemini=None, stills=None):
        judged.append([x["texte"] for x in sc["passages"]])
        return [{"clip": x["clip"], "texte": x["texte"], "note": "non" if x["texte"].startswith("Un freinage") else "bon",
                 "pourquoi": "on ne voit pas de passagers", "proposition": "", "autre_clip": None} for x in sc["passages"]]
    monkeypatch.setattr(script, "match", match)

    def revise(b, codes, request):                      # the fix rewrites plan 4 only
        out = json.loads(json.dumps(b))
        out["plans"][3]["textes"]["fr"]["texte"] = "Les passagers debout seraient projetés en avant."
        return out
    monkeypatch.setattr(sb, "revise", revise)

    ap.write_storyboard(ap.load(p["project_id"]), lambda phase, f: None)

    assert len(judged) == 2 and len(judged[0]) == 6                       # 1st round: every plan
    assert judged[1] == ["Les passagers debout seraient projetés en avant."]  # 2nd round: only the plan fixed


def test_a_plan_the_fix_did_not_touch_keeps_its_problem(project, monkeypatch):
    from adaptation import storyboard as sb
    from test_adaptation_storyboard import GOOD
    b = sb.normalise(json.loads(json.dumps(GOOD)), ["fr"])
    calls = []
    monkeypatch.setattr(script, "match", lambda sc, clips, code, gemini=None, stills=None: calls.append(len(sc["passages"])) or [
        {"clip": x["clip"], "texte": x["texte"], "note": "non", "pourquoi": "rien", "proposition": "", "autre_clip": None}
        for x in sc["passages"]])
    out = sb.illustration(b, "fr", only=[2])
    assert calls == [1] and len(out) == 1 and out[0].startswith("Plan 3 :")     # numbered as in the storyboard


# ---- G3: fetching again keeps the cleaning, arrows, effects and zoom of the unchanged clips

def _fetch_fakes(monkeypatch, seen):
    from pathlib import Path
    from adaptation import annotate, effects, sources

    def download(url, d, name, sections=None):
        Path(d).mkdir(parents=True, exist_ok=True)
        Path(f"{d}/{name}.mp4").write_bytes(b"x")
        return f"{d}/{name}.mp4"
    monkeypatch.setattr(sources, "download", download)
    monkeypatch.setattr(sources, "source_meta", lambda path: {"handle": "@auteur", "url": "u"})
    monkeypatch.setattr(sources, "still", lambda path, t, crop, out, *a, **k: out)
    monkeypatch.setattr(sources, "find_boxes", lambda stills: [(None, [], [])] * len(stills))
    monkeypatch.setattr(sources, "describe", lambda path, segs: [{} for _ in segs])
    monkeypatch.setattr(sources, "clip_at", lambda path, i, cid, a, b, found, desc="": {
        "id": cid, "source": i, "src": path, "start": a, "end": b, "impact": a, "w": 1080, "h": 1920, "usable": True,
        "marks": [], "desc": desc})
    monkeypatch.setattr(sources, "leftover_text", lambda clips, work, **k: seen["left"].append(sorted(clips)) or {})
    monkeypatch.setattr(annotate, "review", lambda ps, clips, work, **k: seen["review"].append([x["clip"] for x in ps]) or [
        {"type": "fleche", "cible": "la cible de " + x["clip"]} for x in ps])
    monkeypatch.setattr(effects, "decide", lambda ps, clips, work, tone=None, **k: seen["decide"].append([x["clip"] for x in ps]) or [
        {"ralenti": True, "zoom": None, "source": x["clip"]} for x in ps])
    monkeypatch.setattr(effects, "auto_zoom", lambda ps, clips, fx, work, **k: seen["zoom"].append([x["clip"] for x in ps]) or fx)
    monkeypatch.setattr(effects, "cap", lambda fx, limits=None: fx)


def test_fetching_again_redoes_only_the_changed_clip(project, monkeypatch):
    from test_adaptation_storyboard import _images_project, fakes as _f  # noqa: F401
    seen = {"left": [], "review": [], "decide": [], "zoom": []}
    _fetch_fakes(monkeypatch, seen)
    pid = _images_project(project, _fixture_calls(monkeypatch), monkeypatch)
    ap.skip_plan(pid, 5)
    ap.start_fetch(pid); ap.run_fetch(pid)
    first = ap.load(pid)["storyboard"]["plans"]
    ap.back_to_images(pid)
    ap.choose_pick(pid, 2, "https://www.tiktok.com/@a/video/9", 3, 9)       # only plan 3 changes
    ap.start_fetch(pid); ap.run_fetch(pid)

    assert seen["review"] == [["P1", "P2", "P3", "P4", "P5"], ["P3"]]
    assert seen["decide"] == [["P1", "P2", "P3", "P4", "P5"], ["P3"]] and seen["zoom"][1] == ["P3"]
    assert seen["left"][1] == ["P3"]                                        # the kept clips were cleaned already
    now = ap.load(pid)["storyboard"]["plans"]
    assert now[0]["annotation"] == first[0]["annotation"] and now[0]["effets"] == first[0]["effets"]


def test_a_changed_sentence_on_a_kept_clip_is_looked_at_again(project, monkeypatch):
    from test_adaptation_storyboard import _images_project
    seen = {"left": [], "review": [], "decide": [], "zoom": []}
    _fetch_fakes(monkeypatch, seen)
    pid = _images_project(project, _fixture_calls(monkeypatch), monkeypatch)
    ap.skip_plan(pid, 5)
    ap.start_fetch(pid); ap.run_fetch(pid)
    ap.back_to_images(pid)
    p = ap.load(pid)
    p["storyboard"]["plans"][1]["textes"]["fr"]["texte"] = "Une autre phrase pour ce même clip."
    ap.save(p)
    ap.start_fetch(pid); ap.run_fetch(pid)

    assert seen["review"][1] == ["P2"] and seen["decide"][1] == ["P2"]      # its words changed: a stale result is worse
    assert seen["left"][1] == []                                            # its clip did not: nothing to clean again


def _fixture_calls(monkeypatch):
    """The storyboard fakes of test_adaptation_storyboard (fixture body, called directly)."""
    import test_adaptation_storyboard as tas
    return tas.fakes.__wrapped__(monkeypatch)
