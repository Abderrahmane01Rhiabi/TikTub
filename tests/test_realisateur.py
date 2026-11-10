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
        {"image": "de trop", "idee": "x"}, {"image": "encore", "idee": "y"}, {"image": "cinq", "idee": "z"}]},
    {"phrase": 3, "type": "carte", "visuels": [], "graphique": {"genre": "carte", "contenu": "Mansouria, près de Casablanca"}},
    {"phrase": 9, "type": "reel", "visuels": [{"image": "hors du script"}]}]}


def test_the_director_s_answer_is_made_safe():
    out = rz.clean(ANSWER, 3, SB)
    assert [e["type"] for e in out] == ["reel", "comparaison", "carte"]
    assert len(out[1]["visuels"]) == 4                                  # 4 visuals at most (one a time of the sentence)
    assert out[2]["visuels"][0]["image"] == "Mansouria" and out[2]["graphique"]["contenu"].startswith("Mansouria")
    assert rz.clean({"error": "x"}, 3, SB) is None


def test_the_search_looks_for_every_visual_with_the_local_searches_and_the_meaning_search_uses_them_all():
    out = rz.clean(ANSWER, 3, SB)
    w = rz.wanted(out, SB)
    assert [x["scene"] for x in w] == ["Engins sur le chantier de Benslimane", "Rendu 3D du Grand Stade",
                                       "Une tente de moussem marocaine", "de trop", "encore", "Mansouria"]
    assert w[1]["phrase"] == "En forme de tente." and w[2]["phrase_n"] == 2
    assert rz.local_of(out) == {0: {"pays": "Maroc", "langue": "", "recherches": ["أشغال ملعب بنسليمان"]}}
    assert rz.ideas(out)[1] == "a stadium with a tent-shaped roof, a traditional Moroccan tent, x, y"
    assert rz.ideas([{"visuels": [{"idee": ""}]}]) == [""] and rz.ideas(None) is None


def test_the_ideas_follow_the_director_when_there_is_one():
    from adaptation import vision
    p = {"realisation": rz.clean(ANSWER, 3, SB), "storyboard": {"plans": SB}}
    sb = [dict(x, idee=x["idee"] or "the place") for x in SB]
    p["storyboard"]["plans"] = sb
    assert vision.ideas_of(p) == ["excavators on a huge site", "a stadium with a tent-shaped roof, a traditional Moroccan tent, x, y",
                                  "the place"]                          # the storyboard's where the director has none


# v2 (lab of 2026-11-10): the clubs named in a sentence, each searched in its checked official channel
CLUBS = {"plans": [{"phrase": 1, "type": "reel", "visuels": [
    {"mot": "الرجاء", "image": "Supporters du Raja en tifo", "idee": "Raja fans", "anglais": ["Raja fans tifo"],
     "entite": {"nom": "Raja Club Athletic", "genre": "club", "chaine": "@RajaClubAthleticOfficiel", "requete": "جمهور الرجاء"}},
    {"mot": "والوداد", "image": "Supporters du Wydad", "idee": "Wydad fans", "anglais": ["Wydad fans"],
     "entite": {"nom": "Wydad Athletic Club", "genre": "club", "chaine": "WydadAthleticClubOfficial", "requete": "جمهور الوداد"}},
    {"mot": "والجيش", "image": "Supporters de l'AS FAR", "idee": "fans",
     "entite": {"nom": "AS FAR", "genre": "club", "chaine": "", "requete": ""}},
    {"mot": "", "image": "Regragui sur le banc", "idee": "coach", "entite": {"nom": "Walid Regragui", "genre": "personne"}}]}]}
SB1 = [{"image": "", "idee": "", "plans_modele": [], "textes": {"ar": {"texte": "الرجاء والوداد والجيش"}}}]
HANDLES = {"RajaClubAthleticOfficiel": {"id": "channel/UCraja", "nom": "Raja Club Athletic", "abonnes": 637000}}
SEARCH = {"Wydad Athletic Club": [{"id": "channel/UChamdi", "nom": "HAMDI | أمسية كروية", "abonnes": 54700},
                                  {"id": "channel/UCwaf", "nom": "Wydad Athletic Fassi", "abonnes": 698},
                                  {"id": "channel/UCwac", "nom": "Wydad Athletic Club", "abonnes": 326000},
                                  {"id": "channel/UCfan", "nom": "Wydad Athletic Club ● نادي الوداد الرياضي", "abonnes": 1}]}


def test_an_entity_keeps_its_word_and_only_clubs_companies_and_institutions_get_a_channel():
    out = rz.clean(CLUBS, 1, SB1)
    v = out[0]["visuels"]
    assert [x["mot"] for x in v] == ["الرجاء", "والوداد", "والجيش", ""]
    assert v[0]["entite"]["chaine"] == "RajaClubAthleticOfficiel" and v[3]["entite"] is None


def test_the_official_channel_is_checked_and_a_wrong_handle_found_again_by_name():
    out = rz.clean(CLUBS, 1, SB1)
    asked = []
    found = rz.channels(out, info=lambda h: HANDLES.get(h), find=lambda n: asked.append(n) or SEARCH.get(n, []))
    v = out[0]["visuels"]
    assert found == 2
    assert v[0]["entite"]["chaine_ok"] == "channel/UCraja"              # the director's handle exists: kept
    assert v[1]["entite"]["chaine_ok"] == "channel/UCwac"               # wrong handle: the named one with most subscribers
    assert "chaine_ok" not in v[2]["entite"]                             # nothing named after it: no channel search
    assert asked == ["Wydad Athletic Club", "AS FAR"]
    w = rz.wanted(out, SB1)
    assert w[0]["chaine"] == {"id": "channel/UCraja", "nom": "Raja Club Athletic", "requete": "جمهور الرجاء"}
    assert "chaine" not in w[2] and "chaine" not in w[3]


def test_a_handle_named_after_someone_else_is_not_trusted():
    assert rz.same_name("Renault Group", "Renault Group Officiel") and not rz.same_name("Renault Group", "renault fan 92")
    assert not rz.same_name("AS FAR", "as far as the corners")          # seen live: a short name inside another one
    assert not rz.same_name("Wydad Athletic Club", "Wydad Athletic Fassi") and not rz.same_name("", "x")


def test_the_search_looks_inside_the_official_channel_too():
    from adaptation import finder
    wanted = [{"scene": "Supporters du Raja", "plans": [], "indices": "", "recherches": ["Raja fans"],
               "chaine": {"id": "channel/UCraja", "nom": "Raja Club Athletic", "requete": "جمهور الرجاء"}},
              {"scene": "un stade", "plans": [], "indices": "", "recherches": ["stadium"]}]
    calls = []

    def search_in(h, q, n=8):
        calls.append((h, q, n))
        return [{"url": "https://www.youtube.com/watch?v=rajarajaraj", "id": "rajarajaraj", "title": "جمهور الرجاء"}]
    sug = finder.suggest({}, wanted=wanted, search=lambda q: [], search_in=search_in, sort=lambda f: None,
                         local=lambda f: {})
    assert calls == [("channel/UCraja", "جمهور الرجاء", 4)]
    c = sug["scenes"][0]["candidats"][0]
    assert c["origines"] == ["chaine"] and c["score"] == finder.score({"origines": ["compte"]})
    assert sug["scenes"][1]["candidats"] == []
