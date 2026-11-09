"""The AI director (2026-11-09): how to show each sentence — the kind of picture, 1 or 2 visuals with their English
and local searches, a graphic to draw for figures, places and mechanisms — and the search follows it."""

from adaptation import realisateur as rz

SB = [{"image": "le chantier", "idee": "construction site", "plans_modele": [], "textes": {"ar": {"texte": "بداو الأشغال"}, "fr": {"texte": "Les travaux ont commencé."}}},
      {"image": "le stade", "idee": "", "plans_modele": [], "textes": {"ar": {"texte": "على شكل خيمة"}, "fr": {"texte": "En forme de tente."}}},
      {"image": "Mansouria", "idee": "", "plans_modele": [], "textes": {"ar": {"texte": "فالمنصورية"}}}]
ANSWER = {"plans": [
    {"phrase": 1, "type": "reel", "visuels": [{"image": "Engins sur le chantier de Benslimane", "idee": "excavators on a huge site",
                                               "anglais": ["Benslimane stadium works"], "pays": "Maroc", "locales": ["أشغال ملعب بنسليمان"]}]},
    {"phrase": 2, "type": "comparaison", "visuels": [
        {"image": "Rendu 3D du Grand Stade", "idee": "a stadium with a tent-shaped roof", "anglais": ["Grand Stade Hassan II 3D"]},
        {"image": "Une tente de moussem marocaine", "idee": "a traditional Moroccan tent", "anglais": ["moroccan tent moussem"]},
        {"image": "de trop", "idee": "x"}]},
    {"phrase": 3, "type": "carte", "visuels": [], "graphique": {"genre": "carte", "contenu": "Mansouria, près de Casablanca"}},
    {"phrase": 9, "type": "reel", "visuels": [{"image": "hors du script"}]}]}


def test_the_director_s_answer_is_made_safe():
    out = rz.clean(ANSWER, 3, SB)
    assert [e["type"] for e in out] == ["reel", "comparaison", "carte"]
    assert len(out[1]["visuels"]) == 2                                  # 2 visuals at most
    assert out[2]["visuels"][0]["image"] == "Mansouria" and out[2]["graphique"]["contenu"].startswith("Mansouria")
    assert rz.clean({"error": "x"}, 3, SB) is None


def test_the_search_looks_for_every_visual_with_the_local_searches_and_the_meaning_search_uses_them_all():
    out = rz.clean(ANSWER, 3, SB)
    w = rz.wanted(out, SB)
    assert [x["scene"] for x in w] == ["Engins sur le chantier de Benslimane", "Rendu 3D du Grand Stade",
                                       "Une tente de moussem marocaine", "Mansouria"]
    assert w[1]["phrase"] == "En forme de tente." and w[2]["phrase_n"] == 2
    assert rz.local_of(out) == {0: {"pays": "Maroc", "langue": "", "recherches": ["أشغال ملعب بنسليمان"]}}
    assert rz.ideas(out)[1] == "a stadium with a tent-shaped roof, a traditional Moroccan tent"
    assert rz.ideas([{"visuels": [{"idee": ""}]}]) == [""] and rz.ideas(None) is None


def test_the_ideas_follow_the_director_when_there_is_one():
    from adaptation import vision
    p = {"realisation": rz.clean(ANSWER, 3, SB), "storyboard": {"plans": SB}}
    sb = [dict(x, idee=x["idee"] or "the place") for x in SB]
    p["storyboard"]["plans"] = sb
    assert vision.ideas_of(p) == ["excavators on a huge site", "a stadium with a tent-shaped roof, a traditional Moroccan tent",
                                  "the place"]                          # the storyboard's where the director has none
