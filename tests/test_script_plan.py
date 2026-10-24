"""Génération scripts: a plan chosen by rotation, and a script sent back when it repeats."""

import random

from generative import script_plan
from generative.script_generator import _build_prompt


def test_each_part_of_the_plan_is_the_least_used_lately():
    history = [{"format": f, "sujet": "la gratitude au quotidien", "accroche": "question", "fin": "question"}
               for f in ("A", "D", "B", "M", "C", "E", "L")]                 # every format but P
    plan = script_plan.choose(history, rng=random.Random(1))
    assert plan["format"] == "P"
    assert plan["sujet"] != "la gratitude au quotidien" and plan["accroche"] != "question" and plan["fin"] != "question"


def test_a_winning_recipe_imposes_its_format_and_older_rows_count_by_format():
    assert script_plan.choose([{"format": "D"}] * 5, fmt="D")["format"] == "D"
    assert script_plan.choose([{"format": "D"}], fmt="Z", rng=random.Random(0))["format"] != "D"   # unknown: rotated


def test_worn_out_title_openings():
    titles = ["J'ai testé la loi du vide", "J'ai testé ce défi", "3 signes que...", "Tu n'es pas en retard"]
    assert script_plan.overused_openings(titles) == ["J'ai testé"]
    assert script_plan.opening("J’ai testé autre chose") == script_plan.opening("J'ai testé")


def test_the_prompt_states_the_plan_and_forbids_fake_testimony():
    plan = {"format": "E", "sujet": "le sommeil et les pensées du soir", "accroche": "promesse", "fin": "phrase"}
    prompt = _build_prompt({"script_style_prompt": "STYLE", "script_audience": "des femmes de plus de 55 ans"}, plan,
                           ["J'ai testé A", "J'ai testé B"], examples=["ex1", "ex2"])
    assert "Exercice guidé" in prompt and "le sommeil" in prompt and "promesse courte" in prompt
    assert "faux témoignage" in prompt and "N'ouvre PAS le titre par : « J'ai testé »" in prompt
    assert "des femmes de plus de 55 ans" in prompt and prompt.index("STYLE") < prompt.index("LE PLAN")


def test_a_repeating_script_is_sent_back_with_the_reason(project, monkeypatch):
    import db
    import generative.pipeline as gp_mod
    project.add_video("old", channel="chanA", source="generated", status="uploaded", youtube_id="Y",
                      title="Le calme avant la tempête", script_text="Respire. Tout va bien se passer, tu es en sécurité ici.")
    project.add_video("new", channel="chanA", source="generated", status="awaiting_script")
    answers = [{"script_text": "Respire. Tout va bien se passer, tu es en sécurité ici.", "title": "Autre titre", "tags": []},
               {"script_text": "J'ai testé le silence pendant 72h.", "title": "J'ai testé le silence", "tags": []},
               {"script_text": "Une histoire neuve, rien à voir.", "title": "Martine et la lettre", "tags": []}]
    feedbacks = []
    def fake(profile, plan, recent_titles=None, inspiration=None, feedback=None):
        feedbacks.append(feedback)
        return answers[len(feedbacks) - 1]
    monkeypatch.setattr(gp_mod, "generate_script", fake)

    gp_mod.GenerativePipeline().generate_script_for("new")

    assert feedbacks[0] is None and "script trop proche" in feedbacks[1][0] and "faux témoignage" in feedbacks[2][0]
    v = db.get_video("new")
    assert v["title"] == "Martine et la lettre" and v["script_warnings"] == []
    assert v["script_format"] == v["script_plan"]["format"] and v["script_plan"]["sujet"]
