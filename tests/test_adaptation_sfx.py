"""Sound effects that follow the picture: rules, no AI."""

from adaptation import sfx


def seg(k, out, dur=4.0, impact=None, **fx):
    return {"k": k, "out": out, "dur": dur, "impact_out": out + 1.0 if impact is None else impact, "fx": fx}


def test_each_effect_on_screen_has_its_sound_and_one_transition_only():
    segs = [seg(0, 0.0), seg(1, 4.0, transition=True), seg(2, 8.0, arret=True), seg(3, 12.0, transition=True),
            seg(4, 16.0, ralenti=True), seg(5, 20.0, transition=True)]
    moments = sfx.plan(segs, [{"start": 0.4}], [], 24.0)
    assert [m["pourquoi"] for m in moments] == ["flèche / cercle", "arrêt sur image", "transition principale",
                                                "ralenti sur le moment fort"]
    assert moments[2]["t"] == 12.0                        # the transition nearest 40 % of the video, alone
    assert moments[3]["sons"] == ["riser", "impact"]


def test_at_most_four_moments_three_seconds_apart():
    segs = [seg(k, 4.0 * k, arret=True) for k in range(8)]
    moments = sfx.plan(segs, [{"start": 1.2}], [], 32.0)
    assert len(moments) == sfx.MAX
    assert all(b["t"] - a["t"] >= sfx.GAP for a, b in zip(moments, moments[1:]))
    assert sfx.plan([seg(0, 0.0, ralenti=True)], [], [], 6.0, own_crash={0})[0]["sons"] == ["riser"]   # its own crash


def test_variants_in_turn_and_the_loudest_instant_on_the_event(monkeypatch):
    monkeypatch.setattr(sfx, "peak_of", lambda f: 0.5 if "riser" in f else 0.05)
    lib = {"whoosh": ["w1.mp3", "w2.mp3"], "riser": ["riser.mp3"]}
    out = sfx.sounds([{"t": 1.0, "sons": ["whoosh"], "pourquoi": "a"}, {"t": 5.0, "sons": ["whoosh"], "pourquoi": "b"},
                      {"t": 9.0, "sons": ["riser", "impact"], "pourquoi": "c"}], lib)
    assert [o["file"] for o in out] == ["w1.mp3", "w2.mp3", "riser.mp3"]   # no impact file: left out
    assert out[0]["start"] == 0.95 and out[2]["start"] == 8.5
    monkeypatch.setattr(sfx, "peak_of", lambda f: {"long.mp3": 0.63}.get(f, 0.05))
    early = sfx.sounds([{"t": 0.48, "sons": ["whoosh"], "pourquoi": "cercle"}], {"whoosh": ["long.mp3", "short.mp3"]})
    assert early[0]["file"] == "short.mp3" and early[0]["start"] == 0.43            # on time at the very start


def test_the_library_is_the_folder_of_the_app():
    lib = sfx.library()
    assert {"whoosh", "pop", "shutter", "riser", "impact", "ding"} <= set(lib)
    assert len(lib["whoosh"]) >= 3
    assert 1.5 < sfx.peak_of(lib["riser"][0]) < 2.0       # a riser is loudest at its end


def test_the_recipe_keeps_the_sound_effects_used():
    from adaptation import pipeline as ap
    p = {"project_id": "x", "clips": {}}
    t = {"language": "fr", "channel": "c", "script": {"passages": []}}
    rec = ap._recipe(p, t, {"plans": [], "effets_sonores": [{"son": "pop_pop.mp3", "a_s": 3.2, "pourquoi": "chiffre"}]})
    assert rec["effets_sonores"][0]["son"] == "pop_pop.mp3"


def test_a_variant_comes_back_only_when_all_were_heard(monkeypatch):
    monkeypatch.setattr(sfx, "peak_of", lambda f: {"long.mp3": 0.63}.get(f, 0.05))
    lib = {"whoosh": ["long.mp3", "a.mp3", "b.mp3"]}
    out = sfx.sounds([{"t": t, "sons": ["whoosh"], "pourquoi": "x"} for t in (0.48, 5.0, 9.0, 13.0)], lib)
    assert [o["file"] for o in out] == ["a.mp3", "long.mp3", "b.mp3", "long.mp3"]   # all heard once, then again


def test_no_ding_on_a_plain_last_sentence():
    moments = sfx.plan([seg(0, 0.0), seg(1, 4.0), seg(2, 8.0)], [], [], 12.0)
    assert not any("ding" in m["sons"] for m in moments)


# ------------------------------------------------------------------ Réglages → Effets sonores

import re
import subprocess

import pytest


def tone(path, silence=0.6, length=0.4, volume=0.1):
    """A quiet beep after some silence."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=800:duration={length}",
                    "-af", f"adelay={int(silence * 1000)}:all=1,volume={volume}", str(path)], check=True)
    return str(path)


def max_db(path):
    err = subprocess.run(["ffmpeg", "-i", path, "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True).stderr
    return float(re.search(r"max_volume:\s*(-?[\d.]+) dB", err).group(1))


@pytest.fixture
def mine(tmp_path, monkeypatch):
    monkeypatch.setattr(sfx, "USER_FOLDER", str(tmp_path / "sfx_perso"))
    return tmp_path


def test_an_added_sound_is_made_like_the_apps_own_and_played_by_its_rule(mine):
    name = sfx.add(tone(mine / "beep.wav"), "pop", "Mon Beep!", "https://freesound.org/x", "CC0")
    assert name == "pop_mon_beep.mp3"
    path = sfx.path_of(name)
    assert sfx.peak_of(path) < 0.15                         # the silence before it is cut
    assert -1.6 < max_db(path) < -0.4                       # as loud as the others
    assert path in sfx.library()["pop"]
    row = next(x for x in sfx.catalog() if x["name"] == name)
    assert row["perso"] and row["actif"] and row["regle"] == sfx.RULES["pop"] and row["source"].endswith("/x")
    assert sfx.add(tone(mine / "b2.wav"), "pop", "Mon Beep!") == "pop_mon_beep_2.mp3"   # never overwrites


def test_only_a_type_with_a_rule_can_be_added(mine):
    with pytest.raises(ValueError):
        sfx.add(tone(mine / "beep.wav"), "rire", "haha")
    (mine / "junk.mp3").write_bytes(b"not a sound")
    with pytest.raises(ValueError):
        sfx.add(str(mine / "junk.mp3"), "pop", "junk")


def test_a_sound_turned_off_is_never_played_and_the_apps_own_are_not_deleted(mine):
    whooshes = sfx.library()["whoosh"]
    first = whooshes[0].rsplit("/", 1)[-1]
    sfx.set_active(first, False)
    assert len(sfx.library()["whoosh"]) == len(whooshes) - 1
    assert not next(x for x in sfx.catalog() if x["name"] == first)["actif"]
    sfx.set_active(first, True)
    assert len(sfx.library()["whoosh"]) == len(whooshes)
    with pytest.raises(ValueError):
        sfx.remove(first)
    name = sfx.add(tone(mine / "beep.wav"), "impact", "boum")
    sfx.remove(name)
    assert name not in {x["name"] for x in sfx.catalog()}


def test_the_settings_screen_api(client, mine):
    d = client.get("/api/sfx").json()
    assert set(d["regles"]) == {"whoosh", "shutter", "riser", "impact", "pop"}
    assert any(x["type"] == "ding" and x["regle"] is None for x in d["sons"])      # said unused
    with open(tone(mine / "beep.wav"), "rb") as f:
        r = client.post("/api/sfx", files={"file": ("Clap.wav", f, "audio/wav")}, data={"kind": "shutter", "licence": "CC0"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "shutter_clap.mp3"
    assert client.get("/api/sfx/shutter_clap.mp3/audio").status_code == 200
    assert client.patch("/api/sfx/shutter_clap.mp3", json={"actif": False}).status_code == 200
    assert "shutter_clap.mp3" not in [p.rsplit("/", 1)[-1] for p in sfx.library()["shutter"]]
    assert client.get("/api/sfx/../../.env/audio").status_code in (400, 404)
    assert client.delete("/api/sfx/shutter_clap.mp3").status_code == 200
    with open(mine / "beep.wav", "rb") as f:
        assert client.post("/api/sfx", files={"file": ("x.txt", f)}, data={"kind": "pop"}).status_code == 400


def test_each_sound_of_the_app_links_to_its_page():
    rows = {x["name"]: x["source"] for x in sfx.catalog() if not x["perso"]}
    assert all(v.startswith("https://freesound.org/people/") for v in rows.values()), rows
    assert rows["whoosh_whip_4.mp3"] == rows["whoosh_whip_1.mp3"]          # "… whip_1 … whip_5": one page
