"""AITagsGenerator: building it never calls an AI (AUDIT.md §8.3)."""

import requests

import ai_tags_generator
from ai_tags_generator import AITagsGenerator


def test_building_with_keys_makes_no_network_call(project, monkeypatch):
    calls = []
    monkeypatch.setattr(requests, "post", lambda *a, **k: calls.append(a[0] if a else k.get("url")))
    monkeypatch.setattr(requests, "get", lambda *a, **k: calls.append(a[0] if a else k.get("url")))
    monkeypatch.setattr(ai_tags_generator, "GEMINI_AVAILABLE", True)
    monkeypatch.setattr(ai_tags_generator, "OPENAI_AVAILABLE", True)

    gen = AITagsGenerator(api_key="fake-gemini", openai_key="fake-openai")

    assert calls == []                                 # no paid "are you there?" request per construction
    assert gen.use_gemini and gen.use_openai           # a key present is enough to count the provider in


def test_without_keys_no_provider(project, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    gen = AITagsGenerator()

    assert not gen.use_gemini and not gen.use_openai
