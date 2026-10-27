"""« Idée d'abord » : a Short from an idea, no model video — what people
search on YouTube, facts found with Google Search (each with its sources),
then the usual Script d'abord. No real call: Gemini and Google are stand-ins."""

import json

import pytest

from adaptation import idee
from adaptation import pipeline as ap
from adaptation import storyboard as sb
from test_adaptation_storyboard import channel, fakes  # noqa: F401  (fixture)


# ---- Google Search through Gemini: each sentence kept with the pages that support it

GROUNDED_TEXT = ("- Le ronronnement vibre entre 25 et 150 Hz.\n"
                 "- Les chats ronronnent aussi quand ils ont mal.\n"
                 "- Un chat qui ronronne fait baisser votre tension.\n"
                 "- Les lions ne ronronnent pas.\n"
                 "- Les chatons ronronnent dès 2 jours.")


def grounded_answer(text=GROUNDED_TEXT):
    """What GeminiAIGenerator.grounded returns: the text, and Google's sentence → pages links."""
    chunks = [{"title": "researchgate.net", "uri": "https://vertexaisearch.cloud.google.com/r/1"},
              {"title": "purina.fr", "uri": "https://vertexaisearch.cloud.google.com/r/2"},
              {"title": "reddit.com", "uri": "https://vertexaisearch.cloud.google.com/r/3"},
              {"title": "scienceworld.ca", "uri": "https://vertexaisearch.cloud.google.com/r/4"}]
    supports = [("Le ronronnement vibre entre 25 et 150 Hz.", [0]),
                ("Les chats ronronnent aussi quand ils ont mal.", [1, 0]),
                ("Un chat qui ronronne fait baisser votre tension.", [2]),           # a forum only: fragile
                ("Les chatons ronronnent dès 2 jours.", [3])]                       # "les lions": no source at all
    return {"text": text, "queries": ["why cats purr"],
            "supports": [{"text": t, "sources": [chunks[i] for i in idx]} for t, idx in supports]}


class FakeGemini:
    def __init__(self, grounded=None, plan=None):
        self.grounded_calls, self.plan_prompts = [], []
        self._grounded, self._plan = grounded or grounded_answer(), plan

    def grounded(self, prompt, **kw):
        self.grounded_calls.append(prompt)
        return self._grounded

    def _generate_content(self, parts, **kw):
        self.plan_prompts.append(parts[0]["text"])
        return self._plan or {"sujet": "pourquoi les chats ronronnent", "question": "pourquoi ?", "ton": "calme",
                              "duree_s": 35, "recherche_courte": "cat purr",
                              "plans": [{"role": "accroche", "visuel": "un chat ronronne contre une main", "paroles": "?"},
                                        {"role": "montee", "visuel": "un vétérinaire examine un chat", "paroles": "..."},
                                        {"role": "reponse", "visuel": "des chatons contre leur mère", "paroles": "!"}]}


def no_redirects(url):
    return url.replace("https://vertexaisearch.cloud.google.com/r/", "https://real.example/")


def test_facts_keep_their_sources_and_unsourced_ones_are_dropped():
    facts = idee.research("pourquoi les chats ronronnent", "fr", gemini=FakeGemini(), resolve=no_redirects)

    by_text = {f["fait"]: f for f in facts}
    assert "Les lions ne ronronnent pas." not in by_text                         # no page behind it: never used
    assert [s["url"] for s in by_text["Les chats ronronnent aussi quand ils ont mal."]["sources"]] == \
        ["https://real.example/2", "https://real.example/1"]
    assert by_text["Un chat qui ronronne fait baisser votre tension."]["fragile"]  # backed by a forum only
    assert not by_text["Le ronronnement vibre entre 25 et 150 Hz."]["fragile"]


def test_build_gives_the_same_sheet_as_a_model_short_with_only_sourced_facts(monkeypatch):
    monkeypatch.setattr(idee, "youtube_suggestions", lambda text, lang: ["pourquoi les chats ronronnent la nuit"])
    g = FakeGemini()

    ref = idee.build("pourquoi les chats ronronnent", "fr", gemini=g, resolve=no_redirects)

    assert ref["origine"] == "idee" and ref["idee"] == "pourquoi les chats ronronnent" and ref["plans"]
    assert ref["faits"] == ["Le ronronnement vibre entre 25 et 150 Hz.", "Les chats ronronnent aussi quand ils ont mal.",
                            "Les chatons ronronnent dès 2 jours."]
    assert ref["faits_douteux"] == ["Un chat qui ronronne fait baisser votre tension."]
    assert ref["suggestions_youtube"] == ["pourquoi les chats ronronnent la nuit"]
    assert "Les lions" not in g.plan_prompts[0] and "la nuit" in g.plan_prompts[0]   # the plan sees only sourced facts


def test_too_few_sourced_facts_stops_instead_of_inventing(monkeypatch):
    monkeypatch.setattr(idee, "youtube_suggestions", lambda text, lang: [])
    thin = {"text": "- Un fait.\n- Un autre.", "queries": [], "supports": [
        {"text": "Un fait.", "sources": [{"title": "site.org", "uri": "https://site.org/a"}]}]}

    with pytest.raises(idee.IdeeError) as e:
        idee.build("une idée floue", "fr", gemini=FakeGemini(grounded=thin), resolve=no_redirects)

    assert "faits sourcés" in str(e.value)


def test_youtube_suggestions_are_best_effort():
    class Answer:
        def __init__(self, data): self.data = data
        def raise_for_status(self): pass
        def json(self): return self.data
    asked = {}

    def get(url, params, timeout):
        asked.update(params)
        return Answer(["chats", ["chats ronronnent pourquoi", "chats ronronnent la nuit"]])
    assert idee.youtube_suggestions("chats", "fr", get=get) == ["chats ronronnent pourquoi", "chats ronronnent la nuit"]
    assert asked["ds"] == "yt" and asked["hl"] == "fr"

    def down(*a, **k):
        raise OSError("blocked")
    assert idee.youtube_suggestions("chats", "fr", get=down) == []


def test_grounded_call_reads_googles_sentence_to_page_links(monkeypatch):
    import gemini_ai_generator as gag
    body = {"candidates": [{"content": {"parts": [{"text": "- A est vrai.\n- B aussi."}]},
                            "groundingMetadata": {"webSearchQueries": ["a b"],
                                                  "groundingChunks": [{"web": {"title": "x.org", "uri": "https://r/1"}}],
                                                  "groundingSupports": [{"segment": {"text": "A est vrai."},
                                                                         "groundingChunkIndices": [0]}]}}],
            "usageMetadata": {"promptTokenCount": 10}}
    sent = {}

    class Response:
        status_code = 200
        text = ""
        def json(self): return body

    def post(url, **kw):
        sent.update(kw)
        return Response()
    monkeypatch.setattr(gag.requests, "post", post)

    out = gag.GeminiAIGenerator(api_key="k").grounded("cherche")

    assert sent["json"]["tools"] == [{"google_search": {}}]
    assert out["supports"] == [{"text": "A est vrai.", "sources": [{"title": "x.org", "uri": "https://r/1"}]}]
    assert out["queries"] == ["a b"] and out["text"].startswith("- A")


# ---- the project

def test_an_idea_project_needs_no_model_link_and_is_a_script_first_project(project):
    p = ap.create("", [], [channel(project, "chanA", "fr", "v_fr")], mode="sources", idea="  pourquoi les chats ronronnent ")

    assert p["mode"] == "script" and p["idee"] == "pourquoi les chats ronronnent" and p["reference_url"] == ""
    with pytest.raises(ap.PipelineError):
        ap.create("", [], [channel(project, "chanB", "fr", "v_fr2")], mode="script")    # neither a link nor an idea


def test_the_analysis_builds_the_sheet_from_the_idea_then_writes_the_storyboard(project, fakes, monkeypatch):
    from adaptation import reference
    built = []
    monkeypatch.setattr(idee, "build", lambda text, lang: built.append((text, lang)) or
                        {"sujet": "chats", "question": "pourquoi", "plans": [{}], "faits": ["f1"], "origine": "idee",
                         "idee": text, "faits_sources": [{"fait": "f1", "sources": [{"titre": "x.org", "url": "https://x.org"}],
                                                          "fragile": False}]})
    p = ap.create("", [], [channel(project, "chanA", "fr", "v_fr")], mode="script", idea="pourquoi les chats ronronnent")

    ap.run_analysis(p["project_id"])

    p = ap.load(p["project_id"])
    assert built == [("pourquoi les chats ronronnent", "fr")] and fakes["reference"] == 0   # no model video read
    assert p["status"] == "plan_review" and p["storyboard"]["plans"] and p["angles"]


def test_the_storyboard_of_an_idea_may_use_only_the_sourced_facts():
    seen = {}

    class G:
        def _generate_content(self, parts, **kw):
            seen["prompt"] = parts[0]["text"]
            from test_adaptation_storyboard import GOOD
            return json.loads(json.dumps(GOOD))
    sb.write({"sujet": "chats", "question": "?", "plans": [{"role": "accroche", "visuel": "un chat"}],
              "faits": ["f1"], "origine": "idee"}, ["fr"], gemini=G())
    assert "AUCUN autre fait" in seen["prompt"]
    sb.write({"sujet": "trams", "question": "?", "plans": [{"role": "accroche", "visuel": "un tram"}]}, ["fr"], gemini=G())
    assert "AUCUN autre fait" not in seen["prompt"]                               # a model Short: unchanged


def test_no_picture_search_without_a_model_short(project):
    from adaptation import finder
    asked = []
    finder.suggest({"plans": []}, "", work_dir=str(project.root / "f"), wanted=[{"scene": "un chat", "recherches": ["cat"]}],
                   search=lambda q: [], local=lambda found: {}, sort=lambda found: None,
                   frames_fn=lambda *a, **k: asked.append(a) or {"frames": [], "source": None})
    assert asked == []


def test_no_excerpt_of_a_model_short_in_an_idea_project(project):
    p = ap.create("", [], [channel(project, "chanA", "fr", "v_fr")], mode="script", idea="pourquoi les chats ronronnent")
    with pytest.raises(ap.PipelineError):
        ap._short_file(ap.load(p["project_id"]))


def test_api_creates_an_idea_project_and_shows_the_facts_with_their_sources(client, project, monkeypatch):
    monkeypatch.setattr("webapp.adaptation_routes._start_adaptation_step", lambda pid, step, **kw: None)
    channel(project, "chanA", "fr", "v_fr")

    made = client.post("/api/adaptations", json={"idea": "pourquoi les chats ronronnent", "mode": "idee", "channels": ["chanA"]})

    assert made.status_code == 200, made.text
    p = made.json()
    assert p["idee"] == "pourquoi les chats ronronnent" and p["mode"] == "script"
    stored = ap.load(p["project_id"])
    stored["reference"] = {"sujet": "chats", "origine": "idee", "suggestions_youtube": ["chats la nuit"],
                           "faits_sources": [{"fait": "f1", "sources": [{"titre": "x.org", "url": "https://x.org"}], "fragile": False}]}
    ap.save(stored)
    shown = client.get(f"/api/adaptations/{p['project_id']}").json()["reference"]
    assert shown["faits_sources"][0]["sources"][0]["url"] == "https://x.org"
    assert shown["suggestions_youtube"] == ["chats la nuit"] and shown["origine"] == "idee"
    assert client.post("/api/adaptations", json={"idea": "", "reference_url": "", "channels": ["chanA"]}).status_code == 400


def test_a_long_idea_is_shortened_until_youtube_suggests_something():
    """Measured: "pourquoi les avions de ligne volent…" → nothing, "pourquoi les avions" → 9 suggestions."""
    class Answer:
        def __init__(self, data): self.data = data
        def raise_for_status(self): pass
        def json(self): return self.data
    asked = []

    answers = {"Pourquoi les avions de": ["pourquoi les avions de la fumée blanche"],
               "Pourquoi les avions": ["pourquoi les avions sont blancs", "pourquoi les avions volent si haut"]}

    def get(url, params, timeout):
        asked.append(params["q"])
        return Answer([params["q"], answers.get(params["q"], [])])

    out = idee.youtube_suggestions("Pourquoi les avions de ligne volent à 10 000 mètres d'altitude", "fr", get=get)

    assert out[0] == "pourquoi les avions volent si haut"            # the closest to the idea first
    assert set(out) == {"pourquoi les avions volent si haut", "pourquoi les avions sont blancs",
                        "pourquoi les avions de la fumée blanche"}
    assert len(asked) <= 8


def test_angles_of_an_idea_see_what_people_search_on_youtube():
    seen = {}

    class G:
        def _generate_content(self, parts, **kw):
            seen["prompt"] = parts[0]["text"]
            return {"angles": [{"titre": "Le vrai secret", "idee": "x"}]}
    sb.angles({"sujet": "avions", "question": "?", "faits": ["f1"],
               "suggestions_youtube": ["pourquoi les avions volent si haut"]}, 3, gemini=G())
    assert "pourquoi les avions volent si haut" in seen["prompt"]
    sb.angles({"sujet": "trams", "question": "?", "faits": ["f1"]}, 3, gemini=G())
    assert "tapent sur YouTube" not in seen["prompt"]                       # a model Short: unchanged


def test_a_passage_google_ties_across_two_lines_sources_both():
    two = {"text": "- Premier fait vérifié ici.\n- Second fait vérifié là.", "queries": [], "supports": [
        {"text": "Premier fait vérifié ici.\n- Second fait vérifié là.",
         "sources": [{"title": "noaa.gov", "uri": "https://noaa.gov/a"}]}]}
    facts = idee.research("x", "fr", gemini=FakeGemini(grounded=two), resolve=no_redirects)
    assert [f["fait"] for f in facts] == ["Premier fait vérifié ici.", "Second fait vérifié là."]


def test_too_few_facts_the_first_time_the_search_is_made_once_more(monkeypatch):
    """Measured on an Arabic idea: one search gave 2 sourced facts, the same one again gave 8."""
    monkeypatch.setattr(idee, "youtube_suggestions", lambda text, lang: [])
    thin = {"text": "- Un seul fait sourcé.", "queries": [],
            "supports": [{"text": "Un seul fait sourcé.", "sources": [{"title": "a.org", "uri": "https://a.org"}]}]}

    class Twice(FakeGemini):
        def grounded(self, prompt, **kw):
            self.grounded_calls.append(prompt)
            return thin if len(self.grounded_calls) == 1 else grounded_answer()
    g = Twice()

    ref = idee.build("pourquoi les chats ronronnent", "fr", gemini=g, resolve=no_redirects)

    assert len(g.grounded_calls) == 2
    assert "Un seul fait sourcé." in ref["faits"] and len(ref["faits"]) == 4       # both searches merged


def test_suggestions_that_only_share_the_first_words_are_dropped():
    """Measured: « لماذا لا » (why not) completed to TikTok, Play Store… — nothing about the sea."""
    class Answer:
        def __init__(self, data): self.data = data
        def raise_for_status(self): pass
        def json(self): return self.data

    def get(url, params, timeout):
        return Answer([params["q"], ["لماذا لا تتجمد اقدام البطريق", "لماذا لا يعمل متجر بلاي", "لماذا لا يشتغل التيك توك"]])

    assert idee.youtube_suggestions("لماذا لا تتجمد مياه البحر بسهولة", "ar", get=get) == ["لماذا لا تتجمد اقدام البطريق"]


def test_the_sheet_of_an_idea_describes_its_images_in_french_whatever_the_channel_language():
    """Measured on an Arabic channel: Arabic facts gave Arabic wanted images — but an image is shared
    by every language of the project (a French version added later must read it too)."""
    g = FakeGemini()
    idee.plan("لماذا لا تتجمد مياه البحر", ["حقيقة"], [], gemini=g)
    assert "EN FRANCAIS" in g.plan_prompts[0]
