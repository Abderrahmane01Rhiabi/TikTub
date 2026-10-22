"""What the end-to-end run of Sources d'abord (tuna Short, 2026-10-21) showed and
was fixed: the judge's other clip, a hand change judged again, the credits of
the clips really used, a video Gemini saw but that can't be downloaded here."""

import pytest

from adaptation import finder, script
from adaptation import pipeline as ap


def _clips():
    return {f"P{k}": {"id": f"P{k}", "source": k - 1, "start": 0, "end": 4, "impact": 1, "usable": True, "marks": [],
                      "desc": f"plan {k}"} for k in (1, 2, 3, 4)}


def test_the_judge_names_another_clip_only_among_the_unused_ones():
    class G:
        def _generate_content(self, parts, **kw):
            G.prompt = parts[0]["text"]
            return {"passages": [{"note": "non", "pourquoi": "x", "autre_clip": "p3"},
                                 {"note": "non", "pourquoi": "x", "autre_clip": "P1"},       # used by passage 1
                                 {"note": "bon", "autre_clip": "P4"}]}                      # a good match keeps its clip
    sc = {"passages": [{"clip": "P1", "texte": "A."}, {"clip": "P2", "texte": "B."}, {"clip": "P4", "texte": "C."}]}
    out = script.match(sc, _clips(), "fr", gemini=G())
    assert "AUTRES CLIPS" in G.prompt and "P3 : plan 3" in G.prompt and "P1 : plan 1" not in G.prompt
    assert [a["autre_clip"] for a in out] == ["P3", None, None]


def test_a_sentence_over_the_wrong_picture_takes_the_clip_that_shows_it():
    sc = {"passages": [{"clip": "P1", "texte": "A."}, {"clip": "P2", "texte": "B."}, {"clip": "P3", "texte": "C."}]}
    accords = [{"clip": "P1", "texte": "A.", "note": "non", "pourquoi": "on voit un labo", "autre_clip": "P4"},
               {"clip": "P2", "texte": "B.", "note": "non", "pourquoi": "y", "autre_clip": "P4"},  # taken just before
               {"clip": "P3", "texte": "C.", "note": "bon", "pourquoi": "", "autre_clip": None}]
    done = ap._swap_clips(sc, accords)
    assert [x["clip"] for x in sc["passages"]] == ["P4", "P2", "P3"]
    assert [x["texte"] for x in sc["passages"]] == ["A.", "B.", "C."]                  # the words never change
    assert len(done) == 1 and "P1 remplacé par P4" in done[0]
    assert ap._swap_clips(sc, None) == []


def test_a_clip_changed_by_hand_is_judged_again_and_keep_survives_elsewhere(monkeypatch):
    calls = []

    def judge(sc, clips, code, work=None):
        calls.append([x["clip"] for x in sc["passages"]])
        return [{"clip": x["clip"], "texte": x["texte"], "note": "bon", "pourquoi": "", "proposition": "",
                 "autre_clip": None} for x in sc["passages"]]
    monkeypatch.setattr(ap, "_judge", judge)
    p = {"project_id": "x", "clips": _clips()}
    t = {"channel": "c", "language": "fr",
         "script": {"passages": [{"clip": "P1", "texte": "A."}, {"clip": "P2", "texte": "B."}]},
         "accords": [{"clip": "P1", "texte": "A.", "note": "non", "pourquoi": "", "garde": True},
                     {"clip": "P2", "texte": "B.", "note": "bon", "pourquoi": ""}]}
    ap._rejudge(p, t)
    assert calls == []                                                   # nothing changed: no new call
    t["script"]["passages"][1]["clip"] = "P3"
    ap._rejudge(p, t)
    assert calls == [["P1", "P3"]]
    assert t["accords"][0].get("garde") and not t["accords"][1].get("garde")


def test_the_proposed_clip_is_taken_with_one_click(monkeypatch):
    store = {}
    p = {"project_id": "x", "status": "script_review", "clips": _clips(),
         "targets": [{"channel": "c", "language": "fr",
                      "script": {"passages": [{"clip": "P1", "texte": "A."}]},
                      "accords": [{"clip": "P1", "texte": "A.", "note": "non", "pourquoi": "", "autre_clip": "P2"}]}]}
    monkeypatch.setattr(ap, "load", lambda pid: p)
    monkeypatch.setattr(ap, "save", lambda q: store.setdefault("p", q))
    monkeypatch.setattr(ap, "_judge", lambda sc, clips, code, work=None: [
        {"clip": x["clip"], "texte": x["texte"], "note": "bon", "pourquoi": ""} for x in sc["passages"]])
    out = ap.use_clip_proposal("x", "c", 0)
    t = out["targets"][0]
    assert t["script"]["passages"][0] == {"clip": "P2", "texte": "A."} and t["accords"][0]["note"] == "bon"
    assert not any("ne correspond pas" in x for x in t["problems"])
    with pytest.raises(ap.PipelineError):
        ap.use_clip_proposal("x", "c", 0)                                # nothing proposed any more


def test_credits_name_each_used_clip_once_its_watermark_or_its_account():
    metas = [{"handle": "@source_a"}, {"handle": "@source_b"}, {"handle": "@source_c"}, {"handle": "@source_d"}]
    clips = _clips()
    clips["P1"]["marks"] = ["texte @fishing_guy en bas"]
    clips["P3"]["marks"] = ["logo de NEWS9"]
    credits = ap.guess_credits(metas, clips)
    assert credits == "@fishing_guy · NEWS9 · @source_b · @source_d"   # a watermark never hides the other sources
    p = {"sources": metas, "clips": clips,
         "targets": [{"script": {"passages": [{"clip": "P2"}]}}, {"script": {"passages": [{"clip": "P3"}]}}]}
    assert ap.credits_for_scripts(p) == "NEWS9 · @source_b"            # only the clips the videos show


def test_a_video_that_cannot_be_downloaded_from_here_is_never_picked_by_itself():
    seen = {"par_scene": {"0": {"niveau": "exacte", "moments": [{"debut": 1, "fin": 5}]}}}
    sug = {"verifs": {"https://y/blocked": {**seen, "telechargeable": False},
                      "https://y/ok": {"par_scene": {"0": {"niveau": "equivalente", "moments": [{"debut": 0, "fin": 3}]}},
                                       "telechargeable": None}}}
    assert finder.auto_pick(sug, [{}])[0]["url"] == "https://y/ok"     # None: unknown, YouTube was just touchy


def test_a_sentence_the_chat_rewrote_is_judged_again(monkeypatch):
    p = {"project_id": "x", "status": "script_review", "clips": _clips(),
         "targets": [{"channel": "c", "language": "fr", "script": {"passages": [{"clip": "P1", "texte": "A."}]},
                      "accords": [{"clip": "P1", "texte": "A.", "note": "non", "pourquoi": ""}]}]}
    monkeypatch.setattr(ap, "load", lambda pid: p)
    monkeypatch.setattr(ap, "save", lambda q: q)
    monkeypatch.setattr(script, "revise", lambda sc, clips, req: {"passages": [{"clip": "P1", "texte": "B."}]})
    monkeypatch.setattr(ap, "_judge", lambda sc, clips, code, work=None: [
        {"clip": x["clip"], "texte": x["texte"], "note": "non", "pourquoi": "toujours pas"} for x in sc["passages"]])
    t = ap.revise_script("x", "c", "réécris")["targets"][0]
    assert t["accords"][0]["texte"] == "B." and any("toujours pas" in x for x in t["problems"])


def test_a_slow_check_never_writes_over_a_step_started_meanwhile(monkeypatch):
    p = {"project_id": "x", "status": "script_review", "clips": _clips(),
         "targets": [{"channel": "c", "language": "fr", "approved": True,
                      "script": {"passages": [{"clip": "P1", "texte": "A."}]},
                      "accords": [{"clip": "P1", "texte": "A.", "note": "bon", "pourquoi": ""}]}]}
    import copy
    store = {"p": p}
    monkeypatch.setattr(ap, "load", lambda pid: copy.deepcopy(store["p"]))
    monkeypatch.setattr(ap, "save", lambda q: store.update(p=q) or q)

    def slow_judge(sc, clips, code, work=None):          # meanwhile, the voices were started
        store["p"] = {**store["p"], "status": "voicing"}
        return [{"clip": x["clip"], "texte": x["texte"], "note": "bon", "pourquoi": ""} for x in sc["passages"]]
    monkeypatch.setattr(ap, "_judge", slow_judge)
    with pytest.raises(ap.PipelineError, match="étape a démarré"):
        ap.edit_script("x", "c", {"passages": [{"clip": "P2", "texte": "A."}]})
    assert store["p"]["status"] == "voicing" and store["p"]["targets"][0]["approved"]


def test_the_credits_can_be_corrected_until_the_final_render(monkeypatch):
    p = {"project_id": "x", "status": "script_review", "credits": "@a"}
    monkeypatch.setattr(ap, "load", lambda pid: p)
    monkeypatch.setattr(ap, "save", lambda q: q)
    assert ap.set_credits("x", "  @a ·  @TokyoSeaLifePark ")["credits"] == "@a · @TokyoSeaLifePark"
    p["status"] = "rendering"
    with pytest.raises(ap.PipelineError):
        ap.set_credits("x", "@b")


def test_the_chat_sees_what_each_clip_shows_and_answers_quickly():
    class G:
        def _generate_content(self, parts, **kw):
            G.prompt, G.kw = parts[0]["text"], kw
            return {"passages": [{"clip": "P1", "texte": "Une phrase naturelle."}]}
    out = script.revise({"passages": [{"clip": "P1", "texte": "A."}]}, _clips(), "le clip montre plan 1", gemini=G())
    assert out["passages"][0]["texte"] == "Une phrase naturelle."
    assert "P1: plan 1" in G.prompt and "ne les recopie pas" in G.prompt and G.kw["thinking"] == 1024
    assert "Le bandeau d'une phrase changee doit aller avec elle" in G.prompt


def test_a_logo_described_in_words_is_not_taken_for_a_name():
    metas = [{"handle": "@viralhog"}, {"handle": "@spotlight9923"}]
    clips = _clips()
    clips = {"A": {**clips["P1"], "source": 1, "marks": ["logo ampoule"]}, "B": {**clips["P2"], "source": 0},
             "C": {**clips["P3"], "source": 0, "marks": ["logo de NEWS9"]}}
    assert ap.guess_credits(metas, clips) == "NEWS9 · @spotlight9923 · @viralhog"


def test_gemini_credits_run_out_is_said_plainly(monkeypatch):
    import requests
    from gemini_ai_generator import GeminiAIGenerator

    class R:
        status_code, text = 402, '{"error": {"message": "Your prepayment credits are depleted."}}'
    monkeypatch.setattr(requests, "post", lambda *a, **k: R())
    g = GeminiAIGenerator(api_key="x")
    with pytest.raises(script.ScriptError, match="Crédits Gemini épuisés"):
        script.revise({"passages": [{"clip": "P1", "texte": "A."}]}, _clips(), "x", gemini=g)


def test_an_excerpt_of_the_model_always_credits_its_creator():
    metas = [{"handle": "@Klimt-YT"}, {"handle": "@source_b"}]
    clips = {"M1": {"id": "M1", "source": 0, "usable": True, "extrait": True, "marks": ["Credits: @jeffthegutterguy"]},
             "P2": {"id": "P2", "source": 1, "usable": True, "marks": []}}
    assert ap.guess_credits(metas, clips) == "@jeffthegutterguy · @Klimt-YT · @source_b"
