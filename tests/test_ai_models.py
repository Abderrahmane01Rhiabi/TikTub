"""One table for which model does each step, and what the AI cost this month."""

import json
import sys

import ai_models
import gemini_ai_generator as gg


def test_each_step_has_its_model_and_a_file_can_change_one(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_models, "OVERRIDES", str(tmp_path / "ai_models.json"))
    assert ai_models.model_for("script.critique") == ai_models.PRO              # the re-reads on Pro
    assert ai_models.model_for("finder._watch") == ai_models.FLASH
    assert ai_models.model_for("montage.unknown_step", "custom-model") == "custom-model"
    (tmp_path / "ai_models.json").write_text(json.dumps({"finder._watch": "gemini-3-flash-preview"}))
    assert ai_models.model_for("finder._watch") == "gemini-3-flash-preview"   # no code change needed


def test_prices_double_in_january_for_flash():
    assert ai_models.price(ai_models.FLASH, "2026-12-31") == (0.75, 3.75)
    assert ai_models.price(ai_models.FLASH, "2027-01-01") == (1.50, 7.50)
    line = {"at": "2026-10-23T10:00:00", "model": ai_models.FLASH, "prompt": 1_000_000, "output": 100_000, "thoughts": 100_000}
    assert round(ai_models.cost(line), 3) == 0.75 + 0.75                          # thinking billed as output
    assert round(ai_models.cost(line, "2027-01-01"), 3) == 3.0


def test_the_months_report(tmp_path):
    log = tmp_path / "gemini.jsonl"
    rows = [{"at": "2026-10-02T10:00:00", "model": ai_models.FLASH, "step": "finder._watch", "status": 200,
             "prompt": 2_000_000, "output": 0, "thoughts": 0},
            {"at": "2026-10-03T10:00:00", "model": ai_models.PRO, "step": "script.critique", "status": 200,
             "prompt": 0, "output": 100_000, "thoughts": 0},
            {"at": "2026-10-04T10:00:00", "model": ai_models.FLASH, "step": "finder._watch", "status": 429,
             "prompt": 0, "output": 0, "thoughts": 0},
            {"at": "2026-09-30T10:00:00", "model": ai_models.FLASH, "step": "finder._watch", "status": 200,
             "prompt": 9_000_000, "output": 0, "thoughts": 0}]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    r = ai_models.month_report("2026-10", str(log))
    assert r["appels"] == 3 and r["echecs"] == 1 and r["total"] == 2.7           # 1.50 + 1.20, September left out
    assert r["au_prix_de_janvier"] == 4.2                                          # Flash doubled, Pro the same
    assert r["par_etape"][0]["etape"] == "finder._watch" and r["par_etape"][0]["quoi"].startswith("regarder")
    assert ai_models.month_report("2026-10", str(tmp_path / "none.jsonl"))["appels"] == 0


def test_a_call_goes_to_the_model_of_the_step_asking(tmp_path, monkeypatch):
    """A call made from storyboard.critique is sent to Pro and logged as Pro."""
    monkeypatch.setattr(gg, "USAGE_LOG", str(tmp_path / "usage.jsonl"))
    sent = []

    class Answer:
        status_code = 200
        text = ""

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "{\"ok\": true}"}]}}],
                    "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 2}}
    monkeypatch.setattr(gg.requests, "post", lambda url, **kw: sent.append(url) or Answer())
    (tmp_path / "storyboard.py").write_text("def critique(g):\n    return g._generate_content([{'text': 'x'}])\n"
                                            "def write(g):\n    return g._generate_content([{'text': 'x'}])\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("storyboard", None)
    import storyboard as fake_step
    g = gg.GeminiAIGenerator(api_key="k")
    assert fake_step.critique(g) == {"ok": True} and fake_step.write(g) == {"ok": True}
    assert "/gemini-pro-latest:" in sent[0] and "/gemini-flash-latest:" in sent[1]
    logged = [json.loads(x) for x in open(tmp_path / "usage.jsonl")]
    assert [(x["step"], x["model"]) for x in logged] == [("storyboard.critique", ai_models.PRO),
                                                        ("storyboard.write", ai_models.FLASH)]
    sys.modules.pop("storyboard", None)


def test_the_api(client, monkeypatch, tmp_path):
    log = tmp_path / "g.jsonl"
    log.write_text(json.dumps({"at": "2026-10-02T10:00:00", "model": ai_models.FLASH, "step": "finder._watch",
                               "status": 200, "prompt": 1_000_000, "output": 0, "thoughts": 0}) + "\n")
    monkeypatch.setattr(gg, "USAGE_LOG", str(log))
    r = client.get("/api/usage/ai?month=2026-10").json()
    assert r["total"] == 0.75 and r["par_etape"][0]["modele_actuel"] == ai_models.FLASH
