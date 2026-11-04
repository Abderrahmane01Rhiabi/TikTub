"""Choosing the model of each step (Réglages → Modèles d'IA): a text step may go to DeepSeek or OpenAI, with the
step's own Gemini model behind it when that fails; a picture or a video never leaves Gemini. No real call: the
requests sent are caught and looked at."""

import json
import sys

import pytest
import requests

import ai_models
import gemini_ai_generator as gg


class Net:
    """requests.post stand-in: answers per host, keeps every call."""
    def __init__(self):
        self.calls, self.deepseek, self.gemini = [], None, {"ok": True}

    def __call__(self, url, **kw):
        self.calls.append({"url": url, **kw})
        if "deepseek" in url or "openai.com" in url:
            status, body = self.deepseek if self.deepseek else (200, {"choices": [{"message": {"content": '{"via": "autre"}'}}],
                                                                       "usage": {"prompt_tokens": 1000, "completion_tokens": 500,
                                                                                 "completion_tokens_details": {"reasoning_tokens": 300},
                                                                                 "prompt_cache_hit_tokens": 200}})
        else:
            status, body = 200, {"candidates": [{"content": {"parts": [{"text": json.dumps(self.gemini)}]}}],
                                 "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 2}}

        class R:
            status_code = status
            text = json.dumps(body)

            def json(self):
                return body
        return R()


@pytest.fixture
def net(monkeypatch, tmp_path):
    n = Net()
    monkeypatch.setattr(requests, "post", n)
    monkeypatch.setattr(gg, "USAGE_LOG", str(tmp_path / "usage.jsonl"))
    monkeypatch.setattr(ai_models, "OVERRIDES", str(tmp_path / "ai_models.json"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    n.log = tmp_path / "usage.jsonl"
    n.choose = lambda d: (tmp_path / "ai_models.json").write_text(json.dumps(d))
    return n


def step_module(tmp_path, monkeypatch, module, function, parts="[{'text': 'Ecris le JSON'}]"):
    """A function named like an app step (the step is read from the caller's module.function)."""
    (tmp_path / f"{module}.py").write_text(f"def {function}(g):\n    return g._generate_content({parts}, max_tokens=900)\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop(module, None)
    mod = __import__(module)
    sys.modules.pop(module, None)
    return getattr(mod, function)


def logged(net):
    return [json.loads(x) for x in open(net.log)]


def test_by_default_every_step_keeps_todays_model(net):
    for step, (model, _) in ai_models.STEPS.items():
        assert ai_models.model_for(step) == model
    assert ai_models.model_for("storyboard.critique") == ai_models.FLASH and ai_models.model_for("script.critique") == ai_models.PRO
    assert ai_models.model_for("script_generator.generate_script") == ai_models.FLASH
    assert ai_models.transcription_model() == "whisper-1"


def test_a_text_step_chosen_on_deepseek_goes_there_and_its_cost_is_logged(net, tmp_path, monkeypatch):
    net.choose({"storyboard.write": ai_models.DEEPSEEK})
    write = step_module(tmp_path, monkeypatch, "storyboard", "write")
    assert write(gg.GeminiAIGenerator(api_key="g")) == {"via": "autre"}
    assert len(net.calls) == 1 and net.calls[0]["url"].startswith("https://api.deepseek.com")
    body = net.calls[0]["json"]
    assert body["model"] == "deepseek-flash" and body["messages"] == [{"role": "user", "content": "Ecris le JSON"}]
    assert body["response_format"] == {"type": "json_object"}
    line = logged(net)[0]
    assert line["model"] == ai_models.DEEPSEEK and line["step"] == "storyboard.write" and line["status"] == 200
    assert line["prompt"] == 1000 and line["output"] == 200 and line["thoughts"] == 300 and line["cached"] == 200
    assert ai_models.cost(line) > 0


@pytest.mark.parametrize("failure", [(429, {"error": "limite"}), (200, {"choices": [{"message": {"content": "pas du JSON"}}]}),
                                     (500, {"error": "panne"})])
def test_when_the_chosen_model_fails_the_steps_own_gemini_model_answers(net, tmp_path, monkeypatch, failure):
    net.deepseek = failure
    net.choose({"script.critique": ai_models.DEEPSEEK})
    critique = step_module(tmp_path, monkeypatch, "script", "critique")
    assert critique(gg.GeminiAIGenerator(api_key="g")) == {"ok": True}
    assert "/gemini-pro-latest:" in net.calls[-1]["url"]            # the re-read of the script stays on Pro, not Flash
    lines = logged(net)
    assert lines[-1]["model"] == ai_models.PRO and lines[-1]["relais_de"] == ai_models.DEEPSEEK and lines[-1]["raison"]


def test_without_its_key_the_chosen_model_is_skipped(net, tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    monkeypatch.setattr(ai_models, "_dotenv_key", lambda name: None)
    net.choose({"storyboard.write": ai_models.DEEPSEEK})
    write = step_module(tmp_path, monkeypatch, "storyboard", "write")
    assert write(gg.GeminiAIGenerator(api_key="g")) == {"ok": True}
    assert all("generativelanguage" in c["url"] for c in net.calls)


def test_a_picture_or_a_video_never_leaves_gemini(net, tmp_path, monkeypatch):
    net.choose({"finder._watch": ai_models.DEEPSEEK, "script.match": ai_models.OPENAI})     # a hand-made file
    watch = step_module(tmp_path, monkeypatch, "finder", "_watch",
                        "[{'file_data': {'file_uri': 'https://youtu.be/x'}}, {'text': 'regarde'}]")
    assert watch(gg.GeminiAIGenerator(api_key="g")) == {"ok": True}
    match = step_module(tmp_path, monkeypatch, "script", "match", "[{'text': 'juge'}]")     # a looking step, even in text
    assert match(gg.GeminiAIGenerator(api_key="g")) == {"ok": True}
    assert all("generativelanguage" in c["url"] for c in net.calls)
    assert ai_models.DEEPSEEK not in ai_models.choices("finder._watch") and ai_models.DEEPSEEK in ai_models.choices("storyboard.write")


def test_openai_can_serve_a_text_step(net, tmp_path, monkeypatch):
    net.choose({"ai_scheduler._ask_ai_for_slots": ai_models.OPENAI})
    ask = step_module(tmp_path, monkeypatch, "ai_scheduler", "_ask_ai_for_slots")
    assert ask(gg.GeminiAIGenerator(api_key="g")) == {"via": "autre"}
    assert net.calls[0]["url"] == "https://api.openai.com/v1/chat/completions" and net.calls[0]["json"]["model"] == "gpt-4o-mini"


def test_deepseek_costs_twice_as_much_in_its_peak_hours():
    line = {"at": "2026-10-28T15:00:00", "model": ai_models.DEEPSEEK, "prompt": 1_000_000, "output": 1_000_000, "thoughts": 0}
    assert round(ai_models.cost(line), 2) == 0.75                              # 0.15 + 0.60 off-peak
    assert round(ai_models.cost({**line, "tarif": "plein"}), 2) == 1.50
    assert round(ai_models.cost({**line, "model": ai_models.OPENAI}), 2) == 0.75
    assert ai_models.deepseek_peak(__import__("datetime").datetime(2026, 10, 28, 7, 0)) is True       # Wednesday 07:00 UTC
    assert ai_models.deepseek_peak(__import__("datetime").datetime(2026, 10, 31, 7, 0)) is False      # Saturday


def test_local_transcription_hears_no_speech_in_music(monkeypatch, tmp_path):
    import audio_transcriber
    (tmp_path / "ai_models.json").write_text(json.dumps({"transcription": "faster-whisper-small"}))
    monkeypatch.setattr(ai_models, "OVERRIDES", str(tmp_path / "ai_models.json"))
    said = {"text": " Music"}

    class Seg:
        def __init__(self, t):
            self.text = t

    class Model:
        def transcribe(self, path):
            return iter([Seg(said["text"])]), None
    monkeypatch.setattr(audio_transcriber, "_local_model", lambda size: Model())
    t = audio_transcriber.AudioTranscriber(api_key="k")
    monkeypatch.setattr(t, "extract_audio", lambda p: str(tmp_path / "a.mp3"))
    (tmp_path / "a.mp3").write_bytes(b"x")
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("whisper-1 called"))
    assert t.transcribe("v.mp4") is None                        # music only: no speech, like whisper-1's empty answer
    said["text"] = " Il fait beau aujourd'hui."
    assert t.transcribe("v.mp4") == "Il fait beau aujourd'hui."


# ---- Réglages → Modèles d'IA

def test_the_screen_lists_every_step_by_part_with_its_choices(net, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    monkeypatch.setattr(ai_models, "_dotenv_key", lambda name: None)
    from datetime import datetime, timedelta
    old = (datetime.now() - timedelta(days=40)).isoformat(timespec="seconds")
    new = datetime.now().isoformat(timespec="seconds")
    net.log.write_text("\n".join(json.dumps(x) for x in [
        {"at": new, "model": ai_models.FLASH, "step": "storyboard.write", "status": 200, "prompt": 1_000_000, "output": 0, "thoughts": 0},
        {"at": new, "model": ai_models.DEEPSEEK, "step": "storyboard.write", "status": 200, "prompt": 1_000_000, "output": 0, "thoughts": 0},
        {"at": old, "model": ai_models.FLASH, "step": "storyboard.write", "status": 200, "prompt": 9_000_000, "output": 0, "thoughts": 0},
    ]) + "\n")
    v = ai_models.settings_view()
    parts = {p["nom"]: p for p in v["parties"]}
    assert list(parts) == ["Adaptation et Idée", "Génération", "Import et Montage auto", "Planning"]
    seen = [e["etape"] for p in v["parties"] for e in p["etapes"]]
    assert sorted(seen) == sorted(ai_models.STEPS) and len(seen) == len(set(seen))       # every step, once
    gen = parts["Génération"]["etapes"][0]
    assert gen["etape"] == "script_generator.generate_script" and gen["quoi"] == "écrire le script (Génération)"
    ds = next(c for c in gen["choix"] if c["modele"] == ai_models.DEEPSEEK)
    assert ds["cle_ok"] is False and ds["note"].startswith("testé") and not ds["recommande"]
    assert next(c for c in gen["choix"] if c["modele"] == ai_models.FLASH)["recommande"]
    sw = next(e for e in parts["Adaptation et Idée"]["etapes"] if e["etape"] == "storyboard.write")
    assert sw["cout_30j"] == 0.9 and sw["appels_30j"] == 2                       # 0.75 + 0.15, the old line left out
    research = next(e for e in parts["Adaptation et Idée"]["etapes"] if e["etape"] == "idee.research")
    assert research["verrou"] and [c["modele"] for c in research["choix"]] == [ai_models.FLASH]
    assert [c["modele"] for c in v["transcription"]["choix"]] == ai_models.TRANSCRIPTION and v["transcription"]["actuel"] == "whisper-1"


def test_a_choice_is_kept_in_the_file_and_a_reset_brings_back_todays_models(net):
    ai_models.set_choice("script_generator.generate_script", ai_models.DEEPSEEK)
    ai_models.set_choice("transcription", "faster-whisper-small")
    assert ai_models.model_for("script_generator.generate_script") == ai_models.DEEPSEEK
    assert ai_models.transcription_model() == "faster-whisper-small"
    ai_models.set_choice("script_generator.generate_script", ai_models.FLASH)        # back to the recommended one
    assert "script_generator.generate_script" not in ai_models._overrides()
    with pytest.raises(ValueError):
        ai_models.set_choice("finder._watch", ai_models.DEEPSEEK)                   # a video step: Gemini only
    with pytest.raises(ValueError):
        ai_models.set_choice("nimporte.quoi", ai_models.FLASH)
    ai_models.reset_choices()
    assert ai_models._overrides() == {} and ai_models.transcription_model() == "whisper-1"


def test_the_api_of_the_screen(client, monkeypatch, tmp_path):
    monkeypatch.setattr(ai_models, "OVERRIDES", str(tmp_path / "ai_models.json"))
    monkeypatch.setattr(gg, "USAGE_LOG", str(tmp_path / "u.jsonl"))
    assert client.get("/api/ai-models").json()["parties"][1]["nom"] == "Génération"
    r = client.post("/api/ai-models", json={"etape": "storyboard.write", "modele": ai_models.DEEPSEEK})
    assert r.status_code == 200 and ai_models.model_for("storyboard.write") == ai_models.DEEPSEEK
    assert client.post("/api/ai-models", json={"etape": "finder._watch", "modele": ai_models.OPENAI}).status_code == 400
    assert client.post("/api/ai-models/reset").status_code == 200 and ai_models.model_for("storyboard.write") == ai_models.FLASH


def test_the_choices_are_in_the_daily_backup(project):
    import backup
    import zipfile
    import os
    os.makedirs("database", exist_ok=True)
    open(os.path.join("database", "ai_models.json"), "w").write('{"storyboard.write": "deepseek-flash"}')
    info = backup.create_backup("manuelle")
    assert "database/ai_models.json" in zipfile.ZipFile(os.path.join(backup.BACKUP_DIR, info["name"])).namelist()


def test_the_screen_is_in_reglages():
    import os
    static = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "webapp", "static")
    html = open(os.path.join(static, "index.html"), encoding="utf-8").read()
    core = open(os.path.join(static, "js", "core.js"), encoding="utf-8").read()
    js = open(os.path.join(static, "js", "reglages.js"), encoding="utf-8").read()
    assert 'data-idx="15"' in html and 'data-i="15" data-space="settings">Modèles d\'IA' in html
    assert "15: [() => loadAiModels()" in core and "settings: [0, 1, 11, 12, 13, 14, 16, 17, 15, 8, 9]" in core
    assert "async function loadAiModels" in js and "esc(" in js.split("async function loadAiModels")[1][:3000]
