"""Tendances (2026-11-17): subjects that work right now for a channel, only from real signals, once in 6 hours."""

import json

import pytest

from adaptation import tendances as td

BRIEF = {"nom": "Prince", "objectif": "actualité marocaine", "langue": "ar", "dialecte": "darija", "famille": "actualite",
         "titres_recents": ["هل كانت شفشاون دائما زرقاء"]}
PLAN = {"pays": "MA", "hl": "fr", "recherches": ["ولي العهد"], "graines": ["مولاي الحسن"], "actualites": ["Maroc"]}


class G:
    def __init__(self, answers):
        self.answers, self.prompts = list(answers), []

    def _generate_content(self, parts, **kw):
        self.prompts.append(parts[0]["text"])
        return self.answers.pop(0)


def test_the_watch_plan_is_read_from_the_channel_line():
    g = G([{"pays": "ma", "hl": "fr", "recherches": ["a", "b", " ", "c", "d", "e"], "graines": ["x"], "actualites": ["n"]}])
    p = td.veille(BRIEF, gemini=g)
    assert p["pays"] == "MA" and p["recherches"] == ["a", "b", "c", "d"] and "actualité marocaine" in g.prompts[0]
    assert td.veille(BRIEF, gemini=G([{"pays": "Maroc!"}]))["pays"] == "MA"          # a strange country: Morocco


def test_subjects_only_from_signals_and_never_a_recent_one():
    sig = {"items": [{"source": "youtube", "titre": "مولاي الحسن في جامع الفنا", "vues": 473834, "lien": "u1", "id": "1"},
                     {"source": "actualites", "titre": "Minurso : retrait fixé", "lien": "u2"},
                     {"source": "trends", "titre": "gta 6", "trafic": "200+", "lien": "u3"}],
           "suggestions": {"مولاي الحسن": ["مولاي الحسن اليوم"]}, "erreurs": []}
    g = G([{"sujets": [{"titre": "ظهور عفوي", "idee": "La sortie du prince", "pourquoi": "473 000 vues", "signaux": [1], "force": 10},
                       {"titre": "Sans signal", "idee": "Un sujet inventé", "pourquoi": "?", "signaux": [], "force": 9},
                       {"titre": "Hors liste", "idee": "x", "pourquoi": "?", "signaux": [99], "force": 9},
                       {"titre": "Minurso", "idee": "Le retrait de la Minurso", "pourquoi": "actualité", "signaux": [2], "force": 6}]}])
    out = td.subjects(BRIEF, sig, gemini=g)
    assert [s["titre"] for s in out] == ["ظهور عفوي", "Minurso"]                     # no signal: never shown
    assert out[0]["signaux"][0]["vues"] == 473834 and out[0]["signaux"][0]["lien"] == "u1"
    assert "شفشاون" in g.prompts[0] and "473 834 vues" in g.prompts[0]              # its last subjects, the views
    with pytest.raises(td.TendancesError):
        td.subjects(BRIEF, sig, gemini=G([{"sujets": [{"idee": "x", "signaux": []}]}]))


def test_one_failing_source_never_stops_the_others(monkeypatch):
    monkeypatch.setattr(td, "_youtube", lambda ch: (_ for _ in ()).throw(td.TendancesError("pas connectée")))
    monkeypatch.setattr(td, "google_news", lambda pays, hl, q=None: [{"source": "actualites", "titre": f"n {q}", "lien": ""}])
    monkeypatch.setattr(td, "google_trends", lambda pays: (_ for _ in ()).throw(OSError("503")))
    monkeypatch.setattr(td, "autocomplete", lambda s, hl: ["مولاي الحسن اليوم"])
    monkeypatch.setattr(td.time, "sleep", lambda s: None)
    sig = td.signals("c", PLAN, "ar")
    assert len(sig["items"]) == 2 and sig["suggestions"] == {"مولاي الحسن": ["مولاي الحسن اليوم"]}
    assert any("pas connectée" in e for e in sig["erreurs"]) and any("Trends" in e for e in sig["erreurs"])


def test_the_rss_readers(monkeypatch):
    rss = b"""<?xml version="1.0"?><rss xmlns:ht="https://trends.google.com/trending/rss"><channel>
      <item><title>gta 6</title><link>l1</link><pubDate>Tue, 17 Nov 2026 10:00:00</pubDate><ht:approx_traffic>200+</ht:approx_traffic></item>
      <item><title>Minurso &amp; Sahara</title><link>l2</link></item></channel></rss>"""

    class R:
        content, status_code = rss, 200

        def raise_for_status(self):
            pass
    asked = []
    monkeypatch.setattr(td.requests, "get", lambda url, **kw: asked.append(url) or R())
    t = td.google_trends("MA")
    assert t[0]["trafic"] == "200+" and t[1]["titre"] == "Minurso & Sahara"
    td.google_news("MA", "fr", "Prince Moulay Hassan")
    assert "q=Prince%20Moulay%20Hassan+when:7d" in asked[-1] and "gl=MA" in asked[-1] and "ceid=MA:fr" in asked[-1]


def test_a_channel_is_searched_once_in_six_hours(project, monkeypatch):
    calls = []
    monkeypatch.setattr(td, "channel_brief", lambda ch: BRIEF)
    monkeypatch.setattr(td, "veille", lambda b, gemini=None: PLAN)
    monkeypatch.setattr(td, "signals", lambda ch, plan, langue, report=None: calls.append(1) or
                        {"items": [{"source": "trends", "titre": "x"}], "suggestions": {}, "erreurs": []})
    monkeypatch.setattr(td, "subjects", lambda b, s, gemini=None: [{"titre": "t", "idee": "i", "force": 7, "signaux": []}])
    first = td.search("chanA")
    assert first["deja"] is False and calls == [1] and td.last("chanA")["sujets"][0]["idee"] == "i"
    again = td.search("chanA")
    assert again["deja"] is True and calls == [1]                     # within 6 h: the last search, nothing paid
    td.search("chanA", force=True)
    assert calls == [1, 1]
    monkeypatch.setattr(td, "signals", lambda *a, **k: {"items": [], "suggestions": {}, "erreurs": ["tout en panne"]})
    with pytest.raises(td.TendancesError, match="tout en panne"):
        td.search("chanA", force=True)


def test_the_routes(client, monkeypatch):
    assert client.get("/api/tendances/chanA").json() == {"resultat": None}
    monkeypatch.setattr(td, "search", lambda ch, force=False, report=None, gemini=None: {"chaine": ch, "sujets": [], "deja": False})
    assert client.post("/api/tendances/chanA", json={}).json()["chaine"] == "chanA"
    monkeypatch.setattr(td, "search", lambda *a, **k: (_ for _ in ()).throw(td.TendancesError("Chaîne inconnue.")))
    r = client.post("/api/tendances/zz", json={})
    assert r.status_code == 400 and "inconnue" in r.json()["detail"]
