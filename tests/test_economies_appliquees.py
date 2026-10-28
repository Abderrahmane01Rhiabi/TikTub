"""TEST_ECONOMIES.md, the ✅ applied: limited thinking (Y1), one look per downloaded file (Y3), the judge's
pictures at medium resolution (Y7), the storyboard re-read by Flash (Y6). No real call: the request sent to
Google is caught and looked at."""

import json

import pytest
import requests

import ai_models
import gemini_ai_generator as gg
from adaptation import finder, script, sources


class Sent:
    """requests.post stand-in: keeps each payload, answers an empty JSON."""
    def __init__(self, answer='{"plans": []}'):
        self.payloads, self.answer = [], answer

    def __call__(self, url, **kw):
        self.payloads.append({"url": url, **kw["json"]})
        answer = self.answer

        class R:
            status_code = 200
            text = ""

            def json(self):
                return {"candidates": [{"content": {"parts": [{"text": answer}]}}], "usageMetadata": {}}
        return R()


@pytest.fixture
def sent(monkeypatch, tmp_path):
    s = Sent()
    monkeypatch.setattr(requests, "post", s)
    monkeypatch.setattr(gg, "USAGE_LOG", str(tmp_path / "u.jsonl"))
    return s


def thinking_of(payload):
    return ((payload["generationConfig"].get("thinkingConfig") or {}).get("thinkingBudget"))


# ---- Y1: the thinking budget of the validated steps, set in one place

def test_the_validated_looking_steps_think_at_most_256_tokens(sent, monkeypatch):
    g = gg.GeminiAIGenerator(api_key="k")
    finder._watch("https://www.youtube.com/watch?v=aaaaaaaaaaa", g, "prompt")
    g._generate_content([{"text": "x"}])                     # a step that is not in the table: unchanged
    assert thinking_of(sent.payloads[0]) == 256
    assert thinking_of(sent.payloads[1]) is None
    assert ai_models.THINKING["finder._watch"] == 256 and ai_models.THINKING["sources.find_boxes"] == 256


def test_a_budget_set_by_the_call_itself_wins(sent):
    g = gg.GeminiAIGenerator(api_key="k")
    finder._sort_one(0, {"scene": "x", "candidats": [{"title": "t"}]}, g, finder.SORT_PROMPT)      # thinking=0
    assert thinking_of(sent.payloads[0]) == 0


def test_the_logos_step_thinks_at_most_256_tokens(sent, monkeypatch, tmp_path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    g = gg.GeminiAIGenerator(api_key="k")
    monkeypatch.setattr(sources, "_gemini", lambda: g)
    sources.find_boxes([str(img)])
    assert thinking_of(sent.payloads[0]) == 256


# ---- Y3: one look per downloaded file for the re-timing and the check (the orientation stays apart)

def test_the_retiming_and_the_check_are_one_request(sent):
    sent.answer = json.dumps({"plans": [{"plan": 1, "visible": True, "debut": 7.1, "fin": 8.3, "fort": 7.5,
                                         "ce_qu_on_voit": "il glisse"}, {"plan": 2, "visible": False, "ce_qu_on_voit": "un toit"}],
                              "passages": [{"visuel": "un mat", "utilisable": True}, {"utilisable": False,
                                                                                      "pourquoi_pas": "presentateur"}]})
    g = gg.GeminiAIGenerator(api_key="k")
    asks = [{"image": "glisse le long du mat", "phrase": "Ce frottement…", "a": 6, "b": 9},
            {"image": "saute du toit", "phrase": "Puis il saute", "a": 10, "b": 12}]
    found, seen = sources.retime_and_check("f.mp4", asks, [(6, 9), (10, 12)], 15.0, (g, {"file_data": {"file_uri": "u"}}))
    assert len(sent.payloads) == 1
    assert found == [{"visible": True, "debut": 7.1, "fin": 8.3, "fort": 7.5, "vu": "il glisse"}, {"visible": False, "vu": "un toit"}]
    assert seen == [{"visuel": "un mat", "utilisable": True}, {"utilisable": False, "pourquoi_pas": "presentateur"}]
    parts = sent.payloads[0]["contents"][0]["parts"]
    assert parts[0]["video_metadata"] == {"fps": 4}
    assert "6.0-9.0 s" in parts[1]["text"] and "1. 6.00-9.00" in parts[1]["text"] and "rotation" not in parts[1]["text"]
    assert thinking_of(sent.payloads[0]) == 256


def test_a_check_that_cannot_be_read_is_asked_again_alone(sent):
    sent.answer = json.dumps({"plans": [{"plan": 1, "visible": True, "debut": 7.1, "fin": 8.3}]})
    g = gg.GeminiAIGenerator(api_key="k")
    found, seen = sources.retime_and_check("f.mp4", [{"image": "x", "a": 6, "b": 9}], [(6, 9)], 15.0, (g, {"file_data": {}}))
    assert found[0]["debut"] == 7.1 and seen is None


# ---- Y7: the judge's pictures at medium resolution (560 tokens each instead of 1120)

def test_the_judge_sends_its_stills_at_medium_resolution(sent, tmp_path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    sent.answer = json.dumps({"passages": [{"passage": 1, "note": "bon"}]})
    g = gg.GeminiAIGenerator(api_key="k")
    sc = {"passages": [{"clip": "P1", "texte": "Il glisse"}]}
    script.match(sc, {"P1": {"start": 0.0, "end": 3.0, "desc": "glisse"}}, "fr", gemini=g, stills={0: [str(img)] * 3})
    pics = [x for x in sent.payloads[0]["contents"][0]["parts"] if "inline_data" in x]
    assert len(pics) == 3 and all(x["mediaResolution"] == {"level": "MEDIA_RESOLUTION_MEDIUM"} for x in pics)


def test_the_logos_keep_their_full_resolution(sent, monkeypatch, tmp_path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    g = gg.GeminiAIGenerator(api_key="k")
    monkeypatch.setattr(sources, "_gemini", lambda: g)
    sources.find_boxes([str(img)])
    assert not any("mediaResolution" in x for x in sent.payloads[0]["contents"][0]["parts"])
