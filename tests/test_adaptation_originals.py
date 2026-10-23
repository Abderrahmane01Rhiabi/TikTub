"""From a useful re-edit (somebody else's montage over the footage we want)
to the original it credits."""

from adaptation import finder

DESC = """Why you should clean your gutters 🍂
🎥 Follow @thegutterguyz on TikTok https://www.tiktok.com/@thegutterguyz · https://www.instagram.com/the_gutter_guyz/
Original: https://youtu.be/ES2EMAUlspM  More from us: https://www.youtube.com/c/Insider @insider @peopleareawesome.com"""


def test_what_a_re_edit_credits_and_not_its_own_channel():
    c = finder.cited_in(DESC, own="Insider", skip={"https://www.youtube.com/watch?v=gJTjg53mqAo"})
    assert c["videos"] == ["https://www.youtube.com/watch?v=ES2EMAUlspM"]
    names = {a["name"]: a["where"] for a in c["comptes"]}
    assert names == {"@thegutterguyz": "tiktok", "@peopleareawesome": ""}      # one account, its own channel left out
    assert finder.cited_in("🎥 Credit: Respective Owner")["comptes"] == []


def verif(verdict, remontage=True, scenes=None, credits=None, title="re-edit"):
    return {"verdict": verdict, "remontage": remontage, "title": title, "credits_vus": credits or [],
            "par_scene": scenes or {}}


def test_a_useful_re_edit_leads_to_checked_originals_offered_on_their_scenes():
    sug = {"scenes": [{"candidats": [], "recherches": ["gutter cleaning"]}, {"candidats": []}],
           "verifs": {"https://www.youtube.com/watch?v=EDIT1234567": verif("oui", credits=["@leafblower_mike"]),
                      "https://www.youtube.com/watch?v=USELESS0000": verif("non")}}
    about = lambda url: {"text": DESC, "own": "Insider"}
    searched = []

    def search_in(handle, keyword):
        searched.append((handle, keyword))
        return [{"url": f"https://www.youtube.com/watch?v={handle[:11]:_<11}", "id": "x", "title": f"{handle} video"}]
    checked = []

    def checker(url, scenes, plans, **kw):
        checked.append(url)
        return {"verdict": "oui", "remontage": False, "title": "The original",
                "par_scene": {"1": {"niveau": "exacte", "moments": [{"debut": 2, "fin": 6}]}}}

    finder.follow_remontages(sug, {"recherche_courte": "gutter"}, "https://youtube.com/shorts/MODEL", n=3,
                             checker=checker, about=about, search_in=search_in)
    o = sug["originaux"]
    assert {a["name"] for a in o["comptes"]} == {"@thegutterguyz", "@peopleareawesome", "@leafblower_mike"}
    assert ("thegutterguyz", "gutter") not in searched                 # a TikTok account: to open by hand
    assert ("leafblower_mike", "gutter") in searched                   # seen on the pictures: its YouTube searched
    assert checked[0] == "https://www.youtube.com/watch?v=ES2EMAUlspM" and len(checked) == 3   # the budget
    assert all(c["via"].endswith("EDIT1234567") for c in o["videos"])
    assert sug["scenes"][1]["candidats"][0]["url"] == checked[0]       # offered where it shows the scene
    assert sug["scenes"][0]["candidats"] == []
    picks = finder.auto_pick(sug, [{}, {}])
    assert picks[1]["url"] == checked[0] and not picks[1]["remontage"]   # an original: picked by itself


def test_nothing_happens_without_a_useful_re_edit():
    sug = {"scenes": [], "verifs": {"u": verif("oui", remontage=False), "v": verif("non")}}
    finder.follow_remontages(sug, {}, about=lambda u: 1 / 0, checker=lambda *a, **k: 1 / 0)
    assert "originaux" not in sug


INSIDER = """How Clogged Gutters Are Deep Cleaned | Deep Cleaned
For more, visit:
https://www.tiktok.com/@thegutterguyz
https://www.youtube.com/channel/UCJzHdz_mAprDUEEJnB0GLuA
MORE DEEP CLEANED VIDEOS:
How The Bottoms Of Pools Are Professionally Deep Cleaned
https://www.youtube.com/watch?v=t7VN7eaQODE
Original video: https://www.youtube.com/watch?v=ORIGINAL123
Filmed by:
https://www.tiktok.com/@someone/video/7400000000000000000"""


def test_its_own_other_videos_are_not_credits_but_the_originals_channel_is():
    c = finder.cited_in(INSIDER, own="Insider", site="YouTube")
    assert c["videos"] == ["https://www.youtube.com/watch?v=ORIGINAL123",                  # said "original"
                           "https://www.tiktok.com/@someone/video/7400000000000000000"]    # "filmed by", line before
    ch = next(a for a in c["comptes"] if a.get("chaine"))
    assert ch["chaine"] == "channel/UCJzHdz_mAprDUEEJnB0GLuA" and ch["where"] == "youtube"


def test_a_douyin_watermark_without_at_is_kept_with_search_links():
    sug = {"scenes": [], "verifs": {"https://www.youtube.com/watch?v=WILDHEART01": verif(
        "oui", credits=["微蓝 (抖音 69627156)", "米合勒 (抖音 Maicy161105)"])}}
    finder.follow_remontages(sug, {}, about=lambda u: {"text": "Why burn a cactus", "own": "Wild Heart"},
                             checker=lambda *a, **k: 1 / 0)
    a = {x["name"]: x for x in sug["originaux"]["comptes"]}
    assert set(a) == {"微蓝 (抖音 69627156)", "米合勒 (抖音 Maicy161105)"}
    assert a["微蓝 (抖音 69627156)"]["links"][0]["url"].endswith("/search/69627156")
