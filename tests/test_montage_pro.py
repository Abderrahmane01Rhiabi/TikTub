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


def test_every_visual_gets_a_source_before_a_second_one_for_the_same(project):
    g = lambda *ks: {"par_scene": {k: {"niveau": "equivalente", "moments": []} for k in ks}}
    p = {"suggestions": {"scenes": [], "verifs": {
        "stade": {"par_scene": {"0": {"niveau": "exacte", "moments": []}, "1": {"niveau": "exacte", "moments": []}}},
        "nou1": g("2"), "nou2": g("2"), "nou3": g("2"), "raja": g("3"), "wac": {"par_scene": {"4": {"niveau": "partielle", "moments": []}}}}}}
    rows = mp.choose_sources(p, n=4)
    assert [r["url"] for r in rows] == ["stade", "nou1", "raja", "wac"]    # the Wydad before a second Camp Nou
    assert "scenes" not in rows[0]


def test_the_editor_follows_the_director_s_times_in_the_voice_s_order():
    r = [{"phrase": 1, "visuels": [{"mot": "", "image": "le stade"}]},
         {"phrase": 2, "visuels": [{"mot": "كامب", "image": "le Camp Nou"}, {"mot": "الرجاء", "image": "les supporters du Raja"},
                                   {"mot": "والوداد", "image": "les supporters du Wydad"}]},
         {"phrase": 9, "visuels": [{"image": "a"}, {"image": "b"}]}]
    text = mp._directed(r, 2)
    assert "Phrase 2 : « كامب » le Camp Nou -> « الرجاء » les supporters du Raja -> « والوداد » les supporters du Wydad" in text
    assert "Phrase 1 : le stade" in text and "Phrase 9" not in text    # one visual too; not in this voice: left out
    assert "tente nomade" in text                                      # another kind of thing does not show it
    assert mp._directed(None, 2) == "" and mp._directed([{"phrase": 1, "visuels": []}], 2) == ""


def test_a_video_made_for_a_scene_beats_one_said_to_show_many():
    # 2026-11-11: an explainer said to show « exactly » 5 scenes took the moussem tent's and the national team's place
    ex = lambda *ks: {"par_scene": {k: {"niveau": "exacte", "moments": []} for k in ks}}
    eq = lambda *ks: {"par_scene": {k: {"niveau": "equivalente", "moments": []} for k in ks}}
    p = {"suggestions": {"scenes": [{}] * 6, "verifs": {
        "explainer": ex("0", "1", "2", "3", "4"), "moussem": eq("3"), "lions": eq("4"), "chantier": eq("1"),
        "nou": eq("5")}}}
    rows = [r["url"] for r in mp.choose_sources(p, n=5)]
    assert set(rows[:4]) == {"moussem", "lions", "chantier", "nou"} and rows[4] == "explainer"
    assert len(mp.choose_sources({"suggestions": {"scenes": [{}] * 10, "verifs": {
        f"u{k}": eq(str(k)) for k in range(12)}}})) == mp.MAX_SOURCES_ALL     # 10 visuals: 10 sources


def test_a_shot_with_burnt_in_text_gives_way_to_a_clean_one_of_its_sentence():
    v = {"duration": 4.0, "words": [{"w": "خمسة", "start": 0.0}, {"w": "مليار", "start": 2.0}],
         "passages": [{"start": 0.0, "end": 4.0, "words": [0, 1]}]}
    stock = [{"id": "T", "source": 0, "start": 0, "end": 3, "colle": [0.5], "probleme": "texte incruste « 5,000 2028 »"},
             {"id": "C", "source": 1, "start": 0, "end": 3, "colle": [0.4], "probleme": None}]
    raw = {"montage": [{"phrase": 1, "coupes": [{"plan": "T", "mot": 0}]}]}
    assert [e["plan"] for e in mp.build_edit(raw, v, stock)] == ["C"]
    stock[1]["colle"] = [0.0]                                         # nothing else shows it: kept
    assert [e["plan"] for e in mp.build_edit(raw, v, stock)] == ["T"]


def test_a_quick_cut_is_kept_on_a_name_of_the_director_s_list():
    said = [("فالفين", 22.72), ("كامب", 24.68), ("نو", 24.96), ("الرجاء", 25.8), ("والوداد", 26.4), ("والمنتخب.", 27.12)]
    v = {"duration": 28.1, "words": [{"w": w, "start": s} for w, s in said],
         "passages": [{"start": 22.72, "end": 28.1, "words": list(range(6))}]}
    r = [{"phrase": 1, "visuels": [{"mot": "كامب", "image": "Camp Nou"}, {"mot": "الرجاء", "image": "Raja"},
                                   {"mot": "والوداد", "image": "Wydad"}, {"mot": "والمنتخب", "image": "équipe nationale"}]}]
    quick = mp.quick_words(r, v)
    assert quick == {1: {1, 3, 4, 5}}
    stock = [{"id": f"S{k}_0", "source": k, "start": 0, "end": 4, "colle": [0.3]} for k in range(5)]
    raw = {"montage": [{"phrase": 1, "coupes": [{"plan": "S0_0", "mot": 0}, {"plan": "S1_0", "mot": 1},
                                                {"plan": "S2_0", "mot": 3}, {"plan": "S3_0", "mot": 4}, {"plan": "S4_0", "mot": 5}]}]}
    assert [e["plan"] for e in mp.build_edit(raw, v, stock, quick)] == ["S0_0", "S1_0", "S2_0", "S3_0", "S4_0"]
    assert [e["plan"] for e in mp.build_edit(raw, v, stock)] == ["S0_0", "S1_0", "S2_0", "S4_0"]   # the 1 s rule: no Wydad


def test_an_official_channel_s_video_stays_in_its_sentence():
    p = {"suggestions": {"scenes": [
        {"phrase_n": 5, "candidats": [{"url": "route", "origines": ["youtube"]}]},
        {"phrase_n": 6, "candidats": [{"url": "nou", "origines": ["chaine"]}, {"url": "wac", "origines": ["chaine", "youtube"]}]},
        {"phrase_n": 3, "candidats": [{"url": "both", "origines": ["chaine"]}]},
        {"phrase_n": 4, "candidats": [{"url": "both", "origines": ["chaine"]}]}]}}
    assert mp.reserved(p) == {"nou": 6, "wac": 6}                      # found for two sentences: free
    said = [("a", 0.0), ("b", 2.0), ("c", 4.0), ("d", 6.0)]
    v = {"duration": 8, "words": [{"w": w, "start": s} for w, s in said],
         "passages": [{"start": 0.0, "end": 4.0, "words": [0, 1]}, {"start": 4.0, "end": 8.0, "words": [2, 3]}]}
    stock = [{"id": "nou", "source": 0, "start": 0, "end": 4, "colle": [0.4, 0.1], "reserve": 2},
             {"id": "route", "source": 1, "start": 0, "end": 4, "colle": [0.3, 0.1]},
             {"id": "x", "source": 2, "start": 0, "end": 4, "colle": [0.1, 0.3]}]
    raw = {"montage": [{"phrase": 1, "coupes": [{"plan": "nou", "mot": 0}]}, {"phrase": 2, "coupes": [{"plan": "x", "mot": 0}]}]}
    edl = mp.build_edit(raw, v, stock)
    assert [(e["phrase"], e["plan"]) for e in edl] == [(1, "route"), (2, "x")]
    assert "nou | 0 «  » (RESERVE a la phrase 2)" in mp._edit_prompt(v, stock)
    many = [{"id": f"S1_{k}", "source": 1, "start": 0, "end": 2, "force": 5, "colle": [0.3, 0.3]} for k in range(80)]
    nou = [{"id": f"S9_{k}", "source": 9, "start": 0, "end": 2, "force": k, "colle": [0.0, 0.0], "reserve": 2} for k in range(5)]
    ids = {s["id"] for s in mp.editable(many + nou, 2)}
    assert {"S9_4", "S9_3", "S9_2"} <= ids and "S9_0" not in ids         # the editor always sees the Camp Nou


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
    banners = [l for l in text.splitlines() if ",Bandeau," in l]
    assert all("\\an8\\pos(540," in l for l in banners)               # the banner too: one fixed place
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

    assert rec["voix"]["id"] == "v1" and rec["voix"]["modele"] == "eleven_v4"
    assert rec["style"]["recit"] == "news" and rec["style"]["bandeau"]["couleur"] == "#C82424"
    assert rec["style"]["sous_titres"]["position"] == "bas-centre, fixe" and rec["style"]["sous_titres"]["taille"] == 96
    assert rec["details"]["structure"]["coupes_par_phrase"] == 1.5


def test_a_shot_starts_past_the_source_s_blurred_transition(monkeypatch):
    blur = {2.8: 20.0, 3.1: 13.0, 3.5: 180.0, 3.9: 240.0}
    monkeypatch.setattr(mp, "sharpness", lambda path, at: blur.get(round(at, 1), 250.0))

    assert mp.sharp_start({"file": "x", "start": 2.7, "end": 5.4}, 1.4) == pytest.approx(3.5)
    monkeypatch.setattr(mp, "sharpness", lambda path, at: 250.0)
    assert mp.sharp_start({"file": "x", "start": 2.7, "end": 5.4}, 1.4) == 2.7      # sharp from the start: kept


def test_a_darija_channel_speaks_darija_but_keeps_its_title_in_fusha():
    from adaptation import settings
    prof = {"language_hint": "ar", "adaptation": {"dialecte": "darija"}}
    assert settings.channel_settings(prof)["dialecte"] == "darija"
    assert settings.channel_settings({"language_hint": "fr", "adaptation": {"dialecte": "darija"}})["dialecte"] is None
    assert settings.clean_update({"dialecte": "klingon"}) == {"dialecte": None}

    rule = mp.dialect_part([{"language": "ar", "dialecte": "darija"}])
    assert "DARIJA" in rule and "ARABE STANDARD" in rule and "titre" in rule
    assert mp.dialect_part([{"language": "ar", "dialecte": None}]) == ""


# ---- « économique » (lab 2026-11-12: ~4x cheaper, judged as good)

def test_economique_is_every_channel_s_default_and_old_projects_stay_quality():
    from adaptation import settings
    assert settings.channel_settings({})["cout"] == "economique"
    assert settings.channel_settings({"adaptation": {"cout": "qualite"}})["cout"] == "qualite"
    assert settings.clean_update({"cout": "n'importe"}) == {"cout": "economique"}
    assert mp.economique({"cout": "economique"}) and not mp.economique({})      # made before: every shot described


def test_the_free_presort_keeps_each_sentence_s_best_and_each_video_s_best():
    # 3 sentences; source 9 (the Lions of a 4-name sentence) never in a sentence's top: still 3 of its shots kept
    sh = [{"id": f"S{k % 3}_{k:02d}", "source": k % 3, "colle": [0.30 - k / 1000, 0.20, 0.10]} for k in range(30)]
    sh += [{"id": f"S9_{k}", "source": 9, "colle": [0.05, 0.05, 0.05 + k / 100]} for k in range(5)]
    keep = mp.presort(sh, 3)
    assert {f"S9_{k}" for k in (2, 3, 4)} <= keep and "S9_0" not in keep
    assert len(keep) < len(sh) and {"S0_00", "S1_01", "S2_02"} <= keep


def test_an_economique_stock_describes_only_the_presorted_shots(project, monkeypatch):
    from adaptation import graphiques, sources, vision
    p = ap.save({"project_id": "ad_eco", "status": "fetching", "cout": "economique", "targets": [],
                 "storyboard": {"plans": [{}, {}]}, "reference": {"sujet": "le stade"}})
    monkeypatch.setattr(mp, "choose_sources", lambda p: [{"url": f"u{k}", "titre": f"t{k}"} for k in range(2)])
    monkeypatch.setattr(sources, "download", lambda url, d, name, spans=None: f"{d}/{name}.mp4")
    monkeypatch.setattr(sources, "source_meta", lambda path: {})
    monkeypatch.setattr(mp, "shots_of", lambda path, k, thumbs: [{"id": f"S{k}_{i:02d}", "source": k, "start": 0.0,
                                                                  "end": 2.6, "file": path} for i in range(20)])
    monkeypatch.setattr(graphiques, "make_all", lambda p, d: {})
    monkeypatch.setattr(vision, "available", lambda: True)
    monkeypatch.setattr(vision, "ideas_of", lambda p: ["a", "b"])
    monkeypatch.setattr(vision, "match", lambda shots, ideas, folder: [s.update(colle=[int(s["id"][-2:]) / 100, 0.1])
                                                                      for s in shots])
    described, v2 = [], {}
    monkeypatch.setattr(mp, "describe", lambda shots, sujet, gemini=None: [
        described.append(s["id"]) or s.update(desc="vu", pertinence=8) for s in shots])
    monkeypatch.setattr(mp, "images_v2", lambda p, shots, metas, base, report, matched=False: v2.update(matched=matched) or {})

    mp.run_stock("ad_eco")

    q = ap.load("ad_eco")
    assert q["status"] == "stock_review" and v2["matched"] is True       # scored once, before the description
    assert q["pretri"] == {"decrits": len(described), "total": 40} and len(described) < 40
    out = [s for s in q["stock"] if s["id"] not in described]
    assert out and all(s["ecarte"] == "pré-tri" and not s["garde"] for s in out)

    ap.save({**ap.load("ad_eco"), "status": "fetching", "cout": "qualite"})
    described.clear()
    mp.run_stock("ad_eco")
    assert len(described) == 40 and ap.load("ad_eco")["pretri"] is None


def test_the_ai_editor_thinks_less_in_economique():
    import inspect
    src = inspect.getsource(mp.make_target)
    assert "thinking=ECO_THINKING if economique(p) else None" in src and mp.ECO_THINKING <= 1024
