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
