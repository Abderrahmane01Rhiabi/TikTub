"""The animated graphics of the montage pro (adaptation/graphiques): the rules agreed with the user (2 full-screen at
most, never two sentences in a row, the hook keeps its real picture with the number over it), numbers from the
facts only, places from OpenStreetMap only, a graphic taking its sentence in the edit, the incrustation kept ours."""

import json

from adaptation import graphiques as gx
from adaptation import montage_doc
from adaptation import realisateur

FACTS = ["سيصبح أكبر ملعب بطاقة استيعابية تصل إلى 115 ألف متفرج.", "Les gaz rejetés à 500-700 °C.",
         "خُصصت ميزانية تبلغ 5 مليارات درهم", "120.000 navires par an", "une capacité de 5,3 millions de conteneurs"]


def entry(k, kind, **g):
    return {"phrase": k, "type": kind, "visuels": [], "graphique": {"contenu": "x", **g} if g or kind in gx.KINDS else None}


def test_numbers_come_from_the_facts_only():
    assert gx.in_facts("115", FACTS) and gx.in_facts("5", FACTS) and gx.in_facts("120000", FACTS)
    assert gx.in_facts("5.3", FACTS) and gx.in_facts("5,3", FACTS)
    assert not gx.in_facts("370", FACTS) and not gx.in_facts("", FACTS) and not gx.in_facts(None, FACTS)
    assert gx.numbers_in("١٢٠ ألف") == [120.0, 120000.0]
    assert gx.in_facts("115000", FACTS) and gx.in_facts("5000000000", FACTS) and gx.in_facts("5300000", FACTS)


def test_the_rules_two_at_most_never_in_a_row_hook_keeps_its_picture():
    r = [entry(1, "chiffre", valeur="115"), entry(2, "carte", lieu="Betoya Bay"), entry(3, "schema"),
         entry(4, "reel"), entry(5, "chiffre", valeur="5"), entry(6, "schema"), entry(7, "chiffre", valeur="120000")]
    got = gx.plan(r, FACTS, ["ar"])
    assert [(g["phrase"], g["mode"]) for g in got] == [(1, "incrustation"), (2, "plan"), (5, "plan")]

    assert gx.plan([entry(1, "carte", lieu="x"), entry(1, "schema")], FACTS, ["ar"]) == []       # no map on the hook
    assert gx.plan([entry(2, "chiffre", valeur="999")], FACTS, ["ar"]) == []                       # not in the facts
    assert gx.plan([entry(2, "carte")], FACTS, ["ar"]) == []                                        # no place to look up
    assert gx.plan(r, FACTS, ["ar", "fr"]) == []             # versions in two languages: the words would be wrong


def test_a_map_is_placed_by_openstreetmap_and_shows_verified_numbers_only():
    places = {"Betoya Bay, Nador, Morocco": (-3.06, 35.24), "Morocco": (-7.3, 31.2), "Tangier, Morocco": (-5.8, 35.76),
              "Nador": (-2.93, 35.17)}
    g = {"lieu": "Betoya Bay, Nador, Morocco", "nom": "الناظور غرب المتوسط", "pays": "Morocco", "pays_nom": "المغرب",
         "reperes": [{"lieu": "Tangier, Morocco", "nom": "طنجة"}, {"lieu": "Nador", "nom": "الناظور"}],
         "chiffre": {"valeur": "120000", "unite": "سفينة"}}
    d = gx.carte_data(g, FACTS, True, find=places.get)
    assert d["place"]["at"] == [-3.06, 35.24] and d["close"]["center"] == [-3.06, 35.24]
    assert [x["text"] for x in d["labels"]] == ["المغرب", "طنجة"]      # Nador, too close to the place: left out
    assert d["stat"] == {"valeur": "120000", "unite": "سفينة"}
    assert gx.carte_data({**g, "chiffre": {"valeur": "7"}}, FACTS, True, find=places.get)["stat"] is None
    assert gx.carte_data({**g, "lieu": "Atlantis"}, FACTS, True, find=places.get) is None


def test_the_template_gets_its_data_safely():
    html = gx.fill("chiffre.html", gx.chiffre_data({"valeur": "5,3", "unite": "</script>"}, False, "plein"))
    data = json.loads(html.split("const DATA = ")[1].split(";\n")[0].replace("<\\/", "</"))
    assert data["valeur"] == "5.3" and "</script>\"" not in html


def test_a_written_schema_may_use_nothing_from_the_web():
    assert gx.outside('<svg xmlns="http://www.w3.org/2000/svg"></svg><script src="vendor/gsap.min.js">') is None
    assert gx.outside('<script src="https://cdn.x.com/a.js">')
    assert gx.outside("fetch('data.json')") and gx.outside('<img src="a.png">')


def test_a_graphic_takes_its_whole_sentence_in_the_edit():
    edl = [{"phrase": 1, "plan": "S0_01", "debut": 0, "fin": 2.0}, {"phrase": 2, "plan": "S1_01", "debut": 2.0, "fin": 3.5},
           {"phrase": 2, "plan": "S2_01", "debut": 3.5, "fin": 5.0}, {"phrase": 3, "plan": "S3_01", "debut": 5.0, "fin": 7.0}]
    shots = [{"id": "G2", "graphique": "carte", "pour": 2, "garde": True}, {"id": "G3", "graphique": "chiffre", "pour": 3,
                                                                              "garde": False}]
    out = gx.with_graphics(edl, shots)
    assert [(e["phrase"], e["plan"], e["debut"], e["fin"]) for e in out] == [
        (1, "S0_01", 0, 2.0), (2, "G2", 2.0, 5.0), (3, "S3_01", 5.0, 7.0)]      # G3 removed by the person: not used


def test_a_graphic_is_a_shot_of_its_sentence(tmp_path):
    s = gx.shot_of({"phrase": 3, "type": "schema", "spec": {"contenu": "la chaleur piégée"}, "fichier": "x.mp4"}, 5,
                   str(tmp_path))
    assert s["id"] == "G3" and s["source"] == "graphiques" and s["garde"] and s["colle"] == [0, 0, 1.0, 0, 0]
    assert s["desc"].startswith("schéma animé")


def test_the_director_gives_the_fields_a_graphic_needs():
    r = {"plans": [{"phrase": 1, "type": "carte", "visuels": [{"image": "le port"}], "graphique": {
        "contenu": "la baie", "lieu": "Betoya Bay", "nom": "بطوية", "reperes": [{"lieu": "Tangier", "nom": "طنجة"}, {"x": 1}],
        "chiffre": {"valeur": "120000", "unite": "سفينة"}, "autre": "?"}}]}
    g = realisateur.clean(r, 1, [])[0]["graphique"]
    assert g == {"contenu": "la baie", "lieu": "Betoya Bay", "nom": "بطوية", "reperes": [{"lieu": "Tangier", "nom": "طنجة"}],
                 "chiffre": {"valeur": "120000", "unite": "سفينة"}}
    assert "valeur" in realisateur.PROMPT and "OpenStreetMap" not in realisateur.PROMPT


def test_hiding_the_hooks_number_is_in_the_journal():
    a = {"plans": [], "incrustation": {"fichier": "g1.mov", "phrase": 1, "cache": False}}
    b = {"plans": [], "incrustation": {"fichier": "g1.mov", "phrase": 1, "cache": True}}
    assert any("Chiffre animé de l'accroche enlevé" in c["quoi"] for c in montage_doc.changes(a, b))
