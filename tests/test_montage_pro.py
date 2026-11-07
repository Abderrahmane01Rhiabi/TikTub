"""Montage pro (« Idée d'abord »): the stock of shots, the AI editor made safe, the captions that stay in
place and in reading order, the narrative style, the recipe. No real call: Gemini is a stand-in."""

import pytest

from adaptation import montage_pro as mp
from adaptation import pipeline as ap
from adaptation import render
from test_adaptation_storyboard import channel, fakes  # noqa: F401  (fixture)


def voice(sentences):
    """A voice like voices.synthesize's: sentences of words, each word 0.5 s, 0.2 s between sentences."""
    words, passages, t = [], [], 0.0
    for s in sentences:
        idx = []
        for w in s.split():
            idx.append(len(words))
            words.append({"w": w, "start": round(t, 2), "end": round(t + 0.45, 2)})
            t += 0.5
        passages.append({"texte": s, "start": words[idx[0]]["start"], "end": words[idx[-1]]["end"], "words": idx})
        t += 0.2
    return {"words": words, "passages": passages, "duration": words[-1]["end"]}


def shots(n, sources=3, **kw):
    return [{"id": f"S{k % sources}_{k:02d}", "source": k % sources, "start": 0.0, "end": 2.6, "desc": f"plan {k}",
             "force": 9 - k % 5, "pertinence": 8, "garde": True, **kw} for k in range(n)]


# ---- the stock

def test_the_sources_are_the_checked_videos_with_good_moments_best_first():
    p = {"picks": [{"url": "u2"}], "suggestions": {"scenes": [], "verifs": {
        "u1": {"par_scene": {"0": {"niveau": "partielle", "moments": [{"debut": 10, "fin": 14}]}}},
        "u2": {"par_scene": {"0": {"niveau": "equivalente", "moments": [{"debut": 1, "fin": 3}]},
                             "1": {"niveau": "partielle", "moments": []}}},
        "u3": {"par_scene": {"0": {"niveau": "rien", "moments": []}}},                 # nothing good: not taken
        "u4": {"copie": True, "par_scene": {"0": {"niveau": "exacte", "moments": []}}}}}}  # a copy: never

    rows = mp.choose_sources(p)

    assert [r["url"] for r in rows] == ["u2", "u1"]


def test_a_long_video_is_downloaded_around_its_good_moments_only():
    assert mp.spans_of({"duree": 90, "moments": [{"debut": 5, "fin": 8}]}) is None          # short: whole
    spans = mp.spans_of({"duree": 900, "moments": [{"debut": 100, "fin": 104}, {"debut": 106, "fin": 110},
                                                   {"debut": 600, "fin": 602}]})
    assert spans == [[97.0, 113.0], [597.0, 605.0]]                                        # padded, merged


def test_an_off_subject_shot_is_set_aside_by_the_code_not_only_by_the_prompt():
    assert mp.set_aside({"desc": "des oranges en caisses", "pertinence": 2}) == "hors sujet"
    assert mp.set_aside({"desc": "une file de camions", "pertinence": 8}) is None


def test_the_stock_needs_six_kept_shots_before_the_edit(project, monkeypatch):
    p = ap.save({"project_id": "ad_x", "status": "stock_review", "targets": [], "stock": shots(8)})
    for s in p["stock"][:3]:
        mp.set_shot("ad_x", s["id"], False)
    with pytest.raises(ap.PipelineError):
        mp.approve_stock("ad_x")
    mp.set_shot("ad_x", p["stock"][0]["id"], True)

    assert mp.approve_stock("ad_x")["status"] == "voicing"


# ---- the edit

def test_the_editor_s_cuts_fall_on_words_and_cover_the_whole_voice():
    v = voice(["les camions sont bloques a la frontiere", "le prix des tomates monte encore", "les exportateurs ont peur"])
    raw = {"montage": [{"phrase": 1, "coupes": [{"plan": "S0_00", "mot": 0}, {"plan": "S1_01", "mot": 3}]},
                       {"phrase": 2, "coupes": [{"plan": "S2_02", "mot": 0}, {"plan": "S0_03", "mot": 2}]},
                       {"phrase": 3, "coupes": [{"plan": "S1_04", "mot": 0}]}]}

    edl = mp.build_edit(raw, v, shots(10))

    assert edl[0]["debut"] == 0.0 and edl[-1]["fin"] == pytest.approx(v["duration"] + 0.6)
    assert all(a["fin"] == b["debut"] for a, b in zip(edl, edl[1:]))                       # no hole, no overlap
    assert edl[1]["debut"] == v["words"][3]["start"]                                        # the cut on "bloques"
    assert [e["plan"] for e in edl] == ["S0_00", "S1_01", "S2_02", "S0_03", "S1_04"]


def test_the_editor_never_uses_a_set_aside_shot_nor_one_twice_nor_a_flash():
    v = voice(["un deux trois quatre cinq six", "sept huit neuf dix"])
    stock = shots(6)
    raw = {"montage": [{"phrase": 1, "coupes": [{"plan": "S0_00", "mot": 0}, {"plan": "S0_00", "mot": 2},
                                                 {"plan": "S1_01", "mot": 3}]},       # the same shot twice
                       {"phrase": 2, "coupes": [{"plan": "ORANGES", "mot": 0},      # not in the kept stock
                                                {"plan": "S2_02", "mot": 1}]}]}    # 0.5 s after: too short

    edl = mp.build_edit(raw, v, stock)

    ids = [e["plan"] for e in edl]
    assert len(ids) == len(set(ids)) and "ORANGES" not in ids
    assert all(e["fin"] - e["debut"] >= mp.MIN_CUT_S for e in edl)


# ---- the captions

def test_arabic_captions_keep_their_reading_order_and_one_fixed_place(tmp_path):
    v = voice(["جاء الإجراء إثر ارتفاع الأسعار"])
    path = tmp_path / "t.ass"

    info = mp.captions_ass(v, [{"bandeau": "أزمة طماطم 🍅", "texte": "x"}], str(path), "ar", render.style_of("actu"))

    text = path.read_text(encoding="utf-8")
    styles = [l for l in text.splitlines() if l.startswith("Style:")]
    lines = [l for l in text.splitlines() if ",Sous," in l]
    assert all(s.endswith(",-1") for s in styles)                       # right-to-left styles
    assert all("\\an2\\pos(540," in l for l in lines)                    # one fixed place: never pushed up
    assert all(l.split(",,", 1)[1].count("{\\c") == l.count(" ") - l.split(",,", 1)[0].count(" ") + 1 for l in lines)
    assert "🍅" not in text and "أزمة طماطم" in text                     # no emoji in the banner (libass)
    assert info["bandeau"] == {"couleur": "#C82424", "place": "haut", "taille": 78}


def test_a_caption_group_ends_when_the_next_one_starts():
    v = voice(["un deux trois quatre"])
    import re
    import tempfile
    with tempfile.NamedTemporaryFile("r", suffix=".ass", delete=False, encoding="utf-8") as f:
        mp.captions_ass(v, [{"bandeau": "", "texte": "x"}], f.name, "fr", render.style_of("classique"))
        lines = [l for l in open(f.name, encoding="utf-8") if ",Sous," in l]
    times = [re.match(r"Dialogue: 1,([^,]+),([^,]+),", l).groups() for l in lines]
    assert times[2][1] == times[3][0]                                    # "trois" hands over to "quatre": no overlap


# ---- the narrative style and the steps

def test_a_news_channel_gets_news_styles_and_avoids_the_last_ones():
    class G:
        def _generate_content(self, parts, **kw):
            self.prompt = parts[0]["text"]
            return {"style": "inconnu"}
    g = G()

    name = mp.choose_recit({"sujet": "tomates", "faits": ["f"]}, "actu", ["news"], gemini=g)

    assert "vrai_faux" in g.prompt and "mystere" not in g.prompt
    assert name in mp.RECITS["actualite"] and name != "news"           # an unknown answer: an unused style


def test_an_idea_project_is_a_montage_pro_and_its_steps_are_the_pro_ones(project):
    p = ap.create("", [], [channel(project, "chanA", "fr", "v_fr")], mode="sources", idea="pourquoi les chats ronronnent")

    assert p["pro"] is True
    assert ap.runner_for(p["project_id"], "fetching") is mp.run_stock
    assert ap.runner_for(p["project_id"], "voicing") is mp.run_montage
    assert ap.runner_for(p["project_id"], "rendering") is ap.run_final


def test_the_recipe_keeps_what_makes_a_montage_pro(project):
    v = voice(["les camions sont bloques", "le prix monte"])
    t = {"channel": "chanA", "language": "fr", "voice_id": "v1", "style": "actu", "voice": {**v, "model": "eleven_v4"},
         "script": {"titre": "T", "passages": [{"texte": "les camions sont bloques"}, {"texte": "le prix monte"}]}}
    edl = [{"phrase": 1, "plan": "a", "debut": 0, "fin": 1.2}, {"phrase": 1, "plan": "b", "debut": 1.2, "fin": 2.2},
           {"phrase": 2, "plan": "c", "debut": 2.2, "fin": 3.6}]
    made = {"duree": 3.6, "captions": {"position": "bas-centre, fixe", "y": 1360, "taille": 96, "police": "Tajawal Black",
                                       "mots_par_ligne": 3, "mot_dit": "#FFE500",
                                       "bandeau": {"couleur": "#C82424", "place": "haut", "taille": 78}}}
    rec = mp.recipe({"project_id": "ad_x", "recit": "news"}, t, edl, {k: {"desc": k} for k in "abc"}, made)

    assert rec["voix"] == {"id": "v1", "modele": "eleven_v4"}
    assert rec["style"]["recit"] == "news" and rec["style"]["bandeau"]["couleur"] == "#C82424"
    assert rec["style"]["sous_titres"]["position"] == "bas-centre, fixe" and rec["style"]["sous_titres"]["taille"] == 96
    assert rec["details"]["structure"]["coupes_par_phrase"] == 1.5
