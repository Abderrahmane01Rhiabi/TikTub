from webapp.adaptation_routes import step_of


def test_step_names_drop_counts_and_channel():
    assert step_of("téléchargement des sources (3/8)") == ("téléchargement des sources", 0.375)
    assert step_of("description des 185 plans") == ("description des plans", None)
    assert step_of("recherche de secours (phrase 3)") == ("recherche de secours", None)
    name, local = step_of("rendu des plans (4/16) (cestpourca)")
    assert name == "rendu des plans" and local == 0.25
    assert step_of("") == ("", None)
