"""repetition: a near-copy of a published video is refused; close ones are flagged.
alerts.feed_state: a channel YouTube no longer shows in the Shorts feed."""

from datetime import datetime

import alerts
import repetition

SCRIPT = ("[curious] J'ai arrêté de contrôler ma réalité pendant 72h. <break time=\"0.8s\" /> "
          "[calm] Le premier jour, tout semblait vide. Le deuxième, un calme étrange. Le troisième, tout a basculé.")


def video(vid, title, script=SCRIPT, status="uploaded", channel="lung", **kw):
    return {"video_id": vid, "channel": channel, "status": status, "youtube_id": f"Y{vid}" if status != "ready_for_upload" else None,
            "uploaded_at": f"2026-09-{vid[-2:]}T10:00:00", "ai_data": {"optimized_title": title}, "script_text": script, **kw}


def test_the_same_script_again_is_refused():
    old = video("v13", "J'ai arrêté de contrôler ma réalité pendant 72h (voici ce qui s'est passé)")
    new = video("v25", "72h sans contrôler ma réalité : le résultat", status="ready_for_upload",
                script=SCRIPT.replace("[calm]", "[warm]"))       # only the voice tags differ
    r = repetition.check(new, [old])
    assert r["block"] and "script identique" in r["block"][0]
    assert "Doublon" in repetition.blocking_message(r)


def test_the_same_title_again_is_refused_even_with_a_new_script():
    old = video("v06", "Pourquoi tout s'effondre juste avant ta manifestation")
    new = video("v23", "Pourquoi TOUT semble s'effondrer avant ta manifestation", status="ready_for_upload",
                script="Un tout autre texte, sur un autre sujet, avec d'autres mots et une autre idée.")
    assert repetition.check(new, [old])["block"] == [] and repetition.check(new, [old])["warn"]   # close: flagged
    same = video("v24", "Pourquoi tout s'effondre juste avant ta manifestation !", status="ready_for_upload",
                 script="Encore un autre texte qui ne ressemble à rien de ce qui précède, vraiment rien.")
    assert repetition.check(same, [old])["block"]


def test_other_channels_and_unpublished_videos_do_not_count():
    other = video("v13", "Titre", channel="cestpourca")
    draft = video("v14", "Titre", status="ready_for_upload")
    new = video("v15", "Titre", status="ready_for_upload")
    assert repetition.check(new, [other, draft])["block"] == []


def test_the_same_background_too_often_is_flagged_not_refused():
    olds = [video(f"v{10 + i}", f"Sujet numéro {i}", script=f"texte {i} " * 5 + str(i), bg_video_path="/b/136322.mp4")
            for i in range(4)]
    new = video("v20", "Un sujet neuf", script="rien à voir avec les autres", status="ready_for_upload",
                bg_video_path="/b/136322.mp4")
    r = repetition.check(new, olds)
    assert r["block"] == [] and any("fond vidéo" in w for w in r["warn"])
    assert r["empreinte"]["fond"] == "136322.mp4"


def test_feed_stopped_when_no_shorts_view_while_videos_went_out():
    now = datetime(2026, 10, 24, 12)
    days = [{"date": "2026-09-15", "views": 900, "shorts": 850}, {"date": "2026-10-18", "views": 3, "shorts": 0}]
    state = alerts.feed_state("lung", days, [datetime(2026, 10, 16, 18)], now)
    assert state["stopped"] and state["shorts_before"] == 850 and state["since"] == "2026-09-15"


def test_feed_alive_or_nothing_to_judge():
    now = datetime(2026, 10, 24, 12)
    days = [{"date": "2026-10-19", "views": 400, "shorts": 380}]
    assert alerts.feed_state("cpc", days, [datetime(2026, 10, 18)], now)["stopped"] is False
    assert alerts.feed_state("idle", [], [datetime(2026, 8, 1)], now) is None    # nothing published lately
    tiny = [{"date": "2026-10-01", "views": 9, "shorts": 7}]                      # never took off: not "stopped"
    assert alerts.feed_state("tiny", tiny, [datetime(2026, 10, 16)], now)["stopped"] is False
