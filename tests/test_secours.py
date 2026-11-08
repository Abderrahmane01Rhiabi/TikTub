"""An AI step that could not answer (the Dead Sea Short, 2026-11-08: Gemini's credits ran out at 12:40) goes on with a
plain choice — and says so on the screen, until the step runs well again or the person chooses."""

from adaptation import montage_pro as mp
from adaptation import musique_casting as mc
from adaptation import recits, secours
from adaptation import storyboard as sb
from adaptation import voix_casting as vc
from gemini_ai_generator import CREDITS_OUT

OUT = {"error": f"{CREDITS_OUT} : recharge-les sur AI Studio"}


class G:
    def __init__(self, *answers):
        self.answers = list(answers)

    def _generate_content(self, parts, **kw):
        return self.answers.pop(0)


def bundle():
    return {"plans": [{"textes": {"fr": {"texte": "Seuls 10 sur 160."}}}]}


def test_a_fact_check_that_could_not_run_says_not_checked_and_clears_once_it_runs():
    b = bundle()
    assert sb.fact_check(b, ["fr"], ["10 sur 160"], gemini=G(OUT)) == {}
    assert secours.listing(b) == ["Vérification des faits : pas faite (crédits Gemini épuisés) : relis toi-même "
                                  "les chiffres et les noms."]
    sb.fact_check(b, ["fr"], ["10 sur 160"], gemini=G({"fautes": []}))
    assert secours.listing(b) == []


def test_a_style_chosen_without_the_ai_is_said_on_the_project():
    p = {}
    name = recits.choose({"sujet": "s"}, "explicatif", recents=["mystere"], gemini=G(OUT), project=p)
    assert name != "mystere" and "choisi sans l'IA (crédits Gemini épuisés)" in secours.listing(p)[0]
    recits.choose({"sujet": "s"}, "explicatif", gemini=G({"style": "top"}), project=p)
    assert "secours" not in p


def test_the_music_and_the_hook_say_when_they_fell_back():
    songs = [{"titre": t, "categories": [], "paroles": False} for t in ("a", "b")]
    assert mc.choose(songs, "T", "r", "calme", None, gemini=G(OUT))["secours"] == "crédits Gemini épuisés"
    assert "secours" not in mc.choose(songs, "T", "r", "calme", None, gemini=G({"musique": 2, "pourquoi": "x"}))

    t = {"language": "fr", "channel": "c", "script": {"passages": [{"texte": "une accroche bien trop longue ici"}]}}
    assert mp.shorter_hook({}, t, 5.0, gemini=G({"error": "API error: 500"})) is None
    assert secours.listing(t) == ["Accroche : trop longue (5.0 s), pas raccourcie (l'IA n'a pas répondu)."]


def test_a_casting_without_the_ai_is_said_and_the_person_s_choice_clears_it(monkeypatch, project):
    from adaptation import pipeline as ap
    monkeypatch.setattr(vc, "rules_of", lambda ch: {"main": "m", "allowed": [], "mode": "principale", "dialect": None,
                                                    "language": "fr"})
    monkeypatch.setattr(ap, "_tone", lambda p, t: "calme")
    t = {"channel": "chanA", "language": "fr", "voice_id": "m", "script": {"passages": [{"texte": "a"}, {"texte": "b"}]}}
    vc.cast({"recit": "mystere"}, t, gemini=G(OUT))
    assert t["manieres"] == ["", ""] and "Voix et manières : faits sans l'IA" in secours.listing(t)[0]

    ap.save({"project_id": "ad_s", "status": "plan_review", "recit": "mystere", "targets": [t]})
    assert "secours" not in vc.set_casting("ad_s", "chanA", manieres=["curieux", ""])["targets"][0]


def test_the_screen_gets_the_warnings_of_the_project_and_of_each_version(project):
    from adaptation import pipeline as ap
    from webapp.adaptation_routes import _serialize_adaptation
    t = {"channel": "chanA", "language": "fr", "voice_id": "m", "secours": {"montage": "fait sans l'IA"}}
    ap.save({"project_id": "ad_v", "status": "preview_review", "secours": {"recit": "choisi sans l'IA"},
             "storyboard": {"plans": [], "secours": {"faits": "pas faite"}}, "targets": [t]})
    out = _serialize_adaptation(ap.load("ad_v"), full=False)
    assert out["secours"] == ["Style du récit : choisi sans l'IA", "Vérification des faits : pas faite"]
    assert out["targets"][0]["secours"] == ["Montage : fait sans l'IA"]
