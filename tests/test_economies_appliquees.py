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
