"""The subject's tone: what it changes in the montage (effects, sounds, music), and who sets it."""

from adaptation import effects, sfx, tone
from adaptation import pipeline as ap


def test_the_tone_is_read_or_guessed_once():
    assert tone.of({"ton": "Drôle"}) == "drole" and tone.of({}) == tone.DEFAULT and tone.of(None) == tone.DEFAULT

    class G:
        calls = 0

        def _generate_content(self, parts, **kw):
            G.calls += 1
            return {"ton": "calme"}
    assert tone.guess({"sujet": "un aquarium", "script_complet": "..."}, G()) == "calme" and G.calls == 1
    assert tone.guess({"ton": "spectaculaire"}, G()) == "spectaculaire" and G.calls == 1     # already said: no call
    assert tone.guess({"sujet": "x"}, object()) == tone.DEFAULT                               # no answer: the default


def test_explicatif_keeps_the_montage_as_it_was():
    assert tone.effect_limits("explicatif") == effects.MAX
    assert tone.sound_rules("explicatif") == {"max": sfx.MAX, "types": None}


def test_a_calm_subject_keeps_few_effects_and_a_funny_one_two_freezes():
    fx = [{"ralenti": True, "transition": True, "arret": True}, {"ralenti": True, "transition": True, "arret": True},
          {"ralenti": True, "transition": True, "arret": True}]
    calm = effects.cap(fx, tone.effect_limits("calme"))
    assert sum(bool(e and e["ralenti"]) for e in calm) == 1 and not any(e and e["arret"] for e in calm)
    funny = effects.cap(fx, tone.effect_limits("drole"))
    assert sum(bool(e and e["arret"]) for e in funny) == 2


def seg(k, out, **fx):
    return {"k": k, "out": out, "dur": 4.0, "impact_out": out + 1.0, "fx": fx}


def test_a_calm_subject_has_no_whoosh():
    segs = [seg(0, 0.0), seg(1, 4.0, transition=True), seg(2, 8.0, arret=True)]
    arrows = [{"start": 1.0}]
    every = sfx.plan(segs, arrows, [], 20.0)
    assert {s for w in every for s in w["sons"]} >= {"whoosh", "shutter"}
    calm = sfx.plan(segs, arrows, [], 20.0, rules=tone.sound_rules("calme"))
    assert [w["sons"] for w in calm] == [["shutter"]]                         # the freeze's click only


def test_a_moment_whose_sounds_are_all_off_takes_no_place():
    """A slow motion (riser + impact, both switched off) no longer blocks the whoosh 1 s later."""
    segs = [seg(0, 0.0), seg(1, 4.0, ralenti=True), seg(2, 6.0, transition=True)]
    on = {"whoosh", "pop", "shutter"}
    kept = sfx.plan(segs, [], [], 20.0, available=on)
    assert [w["pourquoi"] for w in kept] == ["transition principale"]


def test_the_tone_set_by_hand_reaches_every_version_and_the_music_is_chosen_again(project):
    from tests.test_adaptation_flow import channel
    p = ap.create("https://youtube.com/shorts/x", [], [channel(project), channel(project, "chanB", "ar", "v_ar")],
                  "script", True)
    members = [p] + ap.group_of(p)
    for m in members:
        m["reference"] = {"sujet": "x", "ton": "explicatif"}
        m["targets"][0].update(music_chosen=True, music_why="choisi par l'IA")
        ap.save(m)
    p = ap.set_tone(p["project_id"], "calme")
    assert p["reference"]["ton"] == "calme" and not p["targets"][0]["music_chosen"]
    assert all(ap.load(m["project_id"])["reference"]["ton"] == "calme" for m in members)
    try:
        ap.set_tone(p["project_id"], "triste")
        assert False
    except ap.PipelineError:
        pass


def test_the_api(client, project):
    from tests.test_adaptation_flow import channel
    p = ap.create("https://youtube.com/shorts/x", [], [channel(project)])
    p["reference"] = {"sujet": "x"}
    ap.save(p)
    r = client.patch(f"/api/adaptations/{p['project_id']}/ton", json={"ton": "spectaculaire"})
    assert r.status_code == 200 and r.json()["ton"] == "spectaculaire" and len(r.json()["tons"]) == 4
    assert client.patch(f"/api/adaptations/{p['project_id']}/ton", json={"ton": "x"}).status_code == 400
