"""Reprise (4th Adaptation mode): the cleaning's pure parts, the music placement and the script / captions rules —
on drawn images and made-up loudness, no Gemini, no graphics card."""

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from adaptation import musique, reprise, reprise_montage as rm  # noqa: E402


# ---------------------------------------------------------------- what the creator added

def test_a_box_in_fractions_thousandths_or_pixels():
    assert reprise.box_of({"gauche": 0.1, "haut": 0.2, "droite": 0.5, "bas": 0.3}, (720, 1280)) == [0.1, 0.2, 0.5, 0.3]
    assert reprise.box_of({"gauche": 100, "haut": 200, "droite": 500, "bas": 300}, (720, 1280)) == [0.1, 0.2, 0.5, 0.3]
    assert reprise.box_of({"gauche": 1440, "haut": 384, "droite": 2880, "bas": 768}, (2880, 1920)) == \
        pytest.approx([0.5, 0.2, 1.0, 0.4])
    assert reprise.box_of({"gauche": 0.5, "haut": 0.5, "droite": 0.505, "bas": 0.6}, (720, 1280)) is None   # too thin
    assert reprise.box_of({"gauche": "x"}, (720, 1280)) is None


def test_elements_times_are_read_back_or_not_trusted():
    els = [{"type": "sous_titres", "debut": 0, "fin": 238, "cadre": [0.1, 0.6, 0.9, 0.8]}]
    assert reprise.read_elements({"elements": els}, (1440, 1920), 160.0)[0]["fin"] == 158   # "2:38" run together
    assert reprise.read_elements({"elements": [{**els[0], "debut": 70, "fin": 300}]}, (1440, 1920), 160.0) is None
    assert reprise.read_elements({"elements": []}, (1440, 1920), 160.0) is None
    ok = reprise.read_elements({"elements": [{**els[0], "fin": 159}]}, (1440, 1920), 160.0)
    assert ok and ok[0]["cadre"] == [0.1, 0.6, 0.9, 0.8]


def test_only_text_boxes_make_the_colour_zones():
    els = [{"type": "autocollant", "debut": 0, "fin": 5, "cadre": [0.1, 0.1, 0.9, 0.9]},
           {"type": "sous_titres", "debut": 0, "fin": 5, "cadre": [0.4, 0.4, 0.6, 0.5]}]
    z = reprise.zones_at(els, 2.0, 100, 100)
    assert z[45, 50] and not z[15, 15]                   # the big "X" box did not let the colour in
    assert not reprise.zones_at(els, 6.0, 100, 100).any()


# ---------------------------------------------------------------- his letters the OCR missed

def _frame():
    return np.full((1280, 720, 3), (60, 140, 200), np.uint8)   # a Short's size (the "thin" limit follows it), warm


def _letter(img, outline, fill):
    """An "A" drawn stroke by stroke: its outline 22 px wide, its letter 10 px (as on a Short)."""
    segs = [((300, 900), (360, 760)), ((360, 760), (420, 900)), ((325, 850), (395, 850))]
    for a, b in segs:
        cv2.line(img, a, b, outline, 22)
    for a, b in segs:
        cv2.line(img, a, b, fill, 10)


def _hue_of(bgr):
    return int(cv2.cvtColor(np.uint8([[bgr]]), cv2.COLOR_BGR2HSV)[0, 0, 0])


def test_a_red_letter_in_a_white_outline_is_found():
    img = _frame()
    _letter(img, (255, 255, 255), (30, 30, 230))           # red in a white outline (5th Short: "A", "THE")
    zones = np.ones(img.shape[:2], bool)
    m = reprise.colour_mask(img, [_hue_of((30, 30, 230))], zones)
    assert m[750:910, 290:430].any()
    assert not reprise.colour_mask(img, [_hue_of((30, 30, 230))], np.zeros(img.shape[:2], bool)).any()


def test_a_thick_red_blob_is_scenery_not_text():
    img = _frame()
    cv2.circle(img, (360, 800), 90, (255, 255, 255), 8)
    cv2.circle(img, (360, 800), 86, (30, 30, 230), -1)      # a strawberry: red, thick
    m = reprise.colour_mask(img, [_hue_of((30, 30, 230))], np.ones(img.shape[:2], bool))
    assert not m[760:840, 320:400].any()


def test_white_letters_need_a_black_outline():
    img = _frame()
    _letter(img, (0, 0, 0), (255, 255, 255))               # white in black (6th Short: "IT")
    zones = np.ones(img.shape[:2], bool)
    assert reprise.colour_mask(img, [reprise.WHITE], zones)[750:910, 290:430].any()
    assert not reprise.colour_mask(img, [], zones).any()      # white text not learned: nothing white taken
    bone = _frame()
    cv2.line(bone, (150, 1000), (550, 1040), (250, 250, 250), 10)   # a white bone on the floor, no black around
    assert not reprise.colour_mask(bone, [reprise.WHITE], zones).any()


# ---------------------------------------------------------------- music

def _loudness(parts):
    """[(seconds, dB)] -> a loudness curve every 0.1 s."""
    return np.concatenate([np.full(int(s * 10), db, float) for s, db in parts])


def test_a_real_rise_comes_from_a_calmer_part_into_a_loud_one():
    e = _loudness([(20, -30), (30, -14), (20, -30), (30, -14)])
    ups = [t for t, _ in musique.rises(e)]
    assert any(abs(t - 20) < 1 for t in ups) and any(abs(t - 70) < 1 for t in ups)


def test_drum_hits_inside_a_loud_part_and_bumps_in_a_calm_one_are_not_rises():
    hits = np.tile(np.r_[np.full(5, -14.0), np.full(5, -17.0)], 60)          # a drop: 3 dB hits
    calm = _loudness([(30, -30)]) + np.tile(np.r_[np.zeros(30), np.full(30, 5.0)], 5)   # bumps in a calm part
    assert musique.rises(np.r_[_loudness([(10, -14)]), hits, _loudness([(10, -14)])]) == []
    assert musique.rises(np.r_[calm, calm]) == []


def test_the_rise_goes_where_the_song_can_already_play():
    song = {"moment_fort": 47.4, "montees": [15.6, 47.4, 110.0], "duree": 153.0}
    assert musique.peak_for(song, 48.2, 86.0)[0] == 47.4                     # 0.8 s of silence first: nothing
    assert musique.peak_for(song, 73.1, 86.0)[0] == 110.0                    # the end: a later real rise
    assert musique.peak_for(song, 22.7, 86.0, want=15.6)[0] == 47.4          # 15.6 can't land at 22.7
    assert musique.peak_for(song, 10.0, 86.0, want=15.6) == (15.6, "la montée choisie par Gemini")
    late = {"moment_fort": 20.0, "montees": [20.0], "duree": 60.0}
    assert "silence" in musique.peak_for(late, 40.0, 50.0)[1]


# ---------------------------------------------------------------- script and captions

def test_a_story_has_no_numbers_left():
    r = {"genre": "histoire", "titre": {"fr": "T", "ar": "ع"},
         "parties": [{"role": "accroche", "plans": [0], "fr": "Ce porcelet !", "ar": "هذا"},
                     {"role": "point", "numero": 1, "plans": [1, 2], "fr": "1. Tombé sur le bitume", "ar": "1. بعد"}]}
    s = rm.check_script(r, 3, ["fr", "ar"])
    assert s["genre"] == "histoire"
    assert s["parties"][1]["numero"] is None and s["parties"][1]["role"] == "etape"
    assert s["parties"][1]["fr"] == "Tombé sur le bitume" and s["parties"][1]["ar"] == "بعد"


def test_a_top_keeps_its_numbers_and_a_bad_script_is_refused():
    top = {"genre": "top", "parties": [{"role": "point", "numero": 1, "plans": [3], "fr": "Numéro un, ce clavier"}]}
    assert rm.check_script(top, 4, ["fr"])["parties"][0]["numero"] == 1
    assert rm.check_script({**top, "parties": [{**top["parties"][0], "plans": [9]}]}, 4, ["fr"]) is None   # unknown plan
    assert rm.check_script(top, 4, ["fr", "ar"]) is None                     # a language missing
    assert rm.check_script(None, 4, ["fr"]) is None


def test_a_lone_exclamation_mark_sticks_to_the_word_before(tmp_path):
    words = [{"w": "avec", "start": 0.0, "end": 0.3}, {"w": "!", "start": 0.3, "end": 0.4},
             {"w": "Numéro", "start": 0.5, "end": 0.8}, {"w": "un,", "start": 0.8, "end": 1.0}]
    assert [w["w"] for w in rm.glued(words)] == ["avec!", "Numéro", "un,"]
    ass = open(rm.captions(str(tmp_path / "t.ass"), words, [0.0, 0.5], [None, 1], "fr", 2.0), encoding="utf-8").read()
    assert "! Numéro" not in ass and "#1" in ass


def test_part_lengths_follow_the_voice():
    v = {"duration": 10.0, "passages": [{"start": 0.2}, {"start": 4.0}, {"start": 7.5}]}
    assert rm.part_lengths(v) == pytest.approx([4.0, 3.5, 3.3])


def test_the_title_goes_in_the_calmer_band():
    img = np.full((300, 200, 3), 120, np.uint8)
    rng = np.random.default_rng(1)
    img[:100] = rng.integers(0, 255, (100, 200, 3), dtype=np.uint8)          # the subject at the top
    assert rm.title_band(img) == "bas"
    assert rm.title_band(img[::-1].copy()) == "haut"


def test_gemini_minutes_and_seconds_run_together_are_read_back():
    # the 5th Short (122.6 s): "1:00.7" written 100.7 and "1:62.2" 162.2; every time then fell on a real cut
    assert reprise.as_seconds([0, 56.7, 100.7, 162.2], 122.6) == [0, 56.7, 60.7, 122.2]
    assert reprise.as_seconds([0, 158, 240], 160) == [0, 118, 160]           # the 3rd Short at 2 images/s
    assert reprise.as_seconds([5, 50], 60) == [5, 50]                         # times that fit: as they are
    assert reprise.as_seconds([10, 70, 130], 100) is None                     # 70 can't be written so: not trusted
    plans = [{"debut": 0, "fin": 56.7}, {"debut": 56.7, "fin": 100.7}, {"debut": 100.7, "fin": 162.2}]
    assert [p["fin"] for p in rm.fit_plans(plans, 122.6)] == [56.7, 60.7, 122.2]
    with pytest.raises(rm.MontageError):
        rm.fit_plans([{"debut": 0, "fin": 70}, {"debut": 70, "fin": 130}], 100)


def test_the_ocr_erases_only_in_his_text_places():
    class Reader:                                   # a caption in his place, "KENYA" on a shirt elsewhere
        def readtext(self, img):
            return [([[10, 10], [50, 10], [50, 20], [10, 20]], "LOOK", 0.9),
                    ([[60, 60], [90, 60], [90, 70], [60, 70]], "KENYA", 0.95)]
    zones = np.zeros((100, 100), bool)
    zones[5:25, 5:55] = True
    m = reprise.read_in(Reader(), np.zeros((100, 100, 3), np.uint8), zones, 1, 0.2)
    assert m[15, 30] and not m[65, 75]
    assert not reprise.read_in(Reader(), np.zeros((100, 100, 3), np.uint8), np.zeros((100, 100), bool), 1, 0.2).any()


def test_our_captions_go_where_his_were_erased(tmp_path):
    els = [{"type": "sous_titres", "cadre": [0.1, 0.72, 0.9, 0.83], "action": "cacher"},
           {"type": "sous_titres", "cadre": [0.1, 0.73, 0.9, 0.84], "action": "cacher"},
           {"type": "sous_titres", "cadre": [0.2, 0.12, 0.8, 0.19], "action": "cacher"}]     # a title up: not ours
    assert rm.caption_y(els) == pytest.approx(0.78, abs=0.01)
    assert rm.caption_y([]) == rm.CAPTION_Y
    words = [{"w": "un", "start": 0.0, "end": 0.5}]
    ass = open(rm.captions(str(tmp_path / "a.ass"), words, [0.0], [None], "fr", 1.0, 0.78), encoding="utf-8").read()
    assert f",60,60,{int(1920 * 0.22 - 50)}," in ass


def test_the_script_asks_for_accents_and_a_text_that_fills_its_images():
    seen = {}

    class G:
        def _generate_content(self, parts, **kw):
            seen["prompt"] = parts[0]["text"]
            return {"genre": "histoire", "parties": [{"role": "accroche", "plans": [0], "fr": "Ému."}], "titre": {"fr": "T"}}
    rm.write_script({"plans": [{"debut": 0, "fin": 3, "role": "accroche", "visuel": "x", "paroles": "y"}]}, ["fr"], G())
    assert "accents" in seen["prompt"] and "entre 2.2 et 2.6 mots par seconde" in seen["prompt"]
    assert "\"tags\" (8 a 12)" in seen["prompt"] and '"fr": {"titre": "", "description": "", "tags": [""]}' in seen["prompt"]


def test_each_language_gets_its_youtube_title_description_and_tags():
    r = rm.check_script({"genre": "top", "titre": {"fr": "Claviers"},
                         "youtube": {"fr": {"titre": "x" * 120, "description": "Des claviers fous. #shorts",
                                            "tags": ["#clavier"] + [f"t{i}" for i in range(20)]}},
                         "parties": [{"role": "point", "numero": 1, "plans": [0], "fr": "Numéro un."}]}, 1, ["fr"])
    yt = r["youtube"]["fr"]
    assert len(yt["titre"]) == 100 and yt["tags"][0] == "clavier" and len(yt["tags"]) == 15
    old = rm.check_script({"genre": "top", "titre": {"fr": "Claviers"},                  # no "youtube": the short title
                           "parties": [{"role": "point", "plans": [0], "fr": "Un."}]}, 1, ["fr"])
    assert old["youtube"]["fr"] == {"titre": "Claviers", "description": "Claviers", "tags": []}


@pytest.mark.parametrize("style", [None, "clic"])
def test_a_reprise_render_with_or_without_a_caption_library_style(tmp_path, style):
    """The channel's style from Réglages → Sous-titres draws the words; the top's numbers stay ours either way."""
    import json
    import subprocess
    clean, voice = tmp_path / "clean.mp4", tmp_path / "voice.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=360x640:rate=30", "-t", "8",
                    "-c:v", "libx264", str(clean)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=color=pink:seed=3:duration=4:sample_rate=44100",
                    str(voice)], check=True)
    plans = [{"debut": 0.0, "fin": 3.0}, {"debut": 3.0, "fin": 6.0}]
    script = {"genre": "top", "parties": [{"plans": [0], "role": "accroche"}, {"plans": [1], "role": "point", "numero": 1}]}
    words = [{"w": w, "start": i * 0.5, "end": i * 0.5 + 0.4} for i, w in enumerate("le grand prix de la course final".split())]
    v = {"duration": 4.0, "passages": [{"start": 0.0}, {"start": 2.0}], "words": words}
    out = tmp_path / "out.mp4"
    rm.render(str(clean), plans, script, "fr", v, str(voice), None, str(out), str(tmp_path / "w"),
              captions={"style": style, "params": {}} if style else None)
    info = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type:format=duration",
                                               "-of", "json", str(out)]))
    assert float(info["format"]["duration"]) == pytest.approx(4.8, abs=0.2)
    numbers = (tmp_path / "w" / "textes_fr.ass").read_text(encoding="utf-8")
    assert "#1" in numbers and (("Mot,,0" in numbers) == (style is None))      # our words only without a library style
    if style:                       # « Auto » goes where his captions were erased: y = CAPTION_Y of the height
        lib = (tmp_path / "w" / "captions_lib" / "cap.ass").read_text(encoding="utf-8")
        assert f",{int(1920 * rm.CAPTION_Y)})" in lib
