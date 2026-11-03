"""The shared caption library (captions/): catalogue, settings, Arabic, extras, ffmpeg filters, previews, and the spaces
that use it (Génération, Montage auto, Adaptation), plus its routes."""

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from captions import render as R, styles as S
from captions.core import Ctx, Font, bare, line_layout

NEW = {"pop", "pyramide", "escalier", "editorial", "resserre", "hierarchie", "difference", "double_police", "neon",
       "slide_up", "rebond", "degrade", "biseau", "surligneur", "reflet", "flou_net", "emojis", "signature", "clic",
       "evite_visage", "soft_light", "fusion_difference", "perspective", "derriere"}
EXISTING = {"karaoke", "mrbeast", "hormozi", "bounce", "typewriter", "minimal", "cascade", "accent",
            "adaptation_classique", "adaptation_flamme", "adaptation_neon", "adaptation_or", "adaptation_clair"}


def ctx_for(lang, faces=()):
    words, strong = R.sample_words(lang)
    return words, Ctx(lang=lang, strong=strong, impact=sorted(strong, key=len)[-1], faces=list(faces))


def test_the_catalogue_has_every_style_of_the_lab_and_of_the_spaces():
    assert NEW | EXISTING == set(S.STYLES)
    numbered = sorted(s.number for s in S.STYLES.values() if s.number)
    assert numbered == list(range(14, 34))                       # n°14-33 of the catalogue of 2026-11-03


@pytest.mark.parametrize("style_id", sorted(NEW | EXISTING))
@pytest.mark.parametrize("lang", ["en", "fr", "ar"])
def test_every_style_builds_in_every_language(style_id, lang):
    words, ctx = ctx_for(lang)
    built = R.build(style_id, words, ctx)
    assert "[Events]" in built.ass and "Dialogue:" in built.ass
    if lang == "ar" and S.STYLES[style_id].native is None:     # right-to-left base on every style line of ours
        styles_part = built.ass.split("[Events]")[0]
        assert all(line.endswith(",-1") for line in styles_part.splitlines() if line.startswith("Style:"))


def test_settings_are_cleaned_never_trusted():
    p = S.STYLES["hierarchie"].clean({"grand": 999, "petit": "abc", "couleur": "red", "position": "nowhere", "x": 1})
    assert p["grand"] == 200 and p["petit"] == 80 and p["couleur"] == "#ffffff" and p["position"] == "auto" and "x" not in p
    assert S.STYLES["surligneur"].clean({"contour_seul": "true"})["contour_seul"] is True
    assert S.STYLES["surligneur"].clean({"contour": 99})["contour"] == 10


def test_an_arabic_line_is_laid_out_right_to_left_with_the_real_shaping():
    words, ctx = ctx_for("ar")
    f = Font("xbold", 66, "ar")
    lay, _ = line_layout(f, words[:3], ctx, {})
    xs = [x for _, x, _ in lay]
    assert xs[0] > xs[1] > xs[2]                                 # the first word on the right
    joined, alone = f.width("الجائزة"), sum(f.width(c) for c in "الجائزة")
    assert joined < alone                                        # measured joined (raqm), not letter by letter


def test_the_marker_is_drawn_on_its_own_word_in_arabic():
    words, ctx = ctx_for("ar")
    built = R.build("surligneur", words[:3], ctx)
    f = Font("xbold", 66, "ar")
    lay, width = line_layout(f, words[:3], ctx, S.STYLES["surligneur"].clean({}))
    target = next(x for w, x, _ in lay if bare(w[0]) in ctx.strong)
    box = next(l for l in built.ass.splitlines() if ",Box," in l)
    xs = [float(v) for v in box.split("\\p0")[0].split("}")[-1].split()[1::3][:2]]
    assert abs((xs[0] + xs[1]) / 2 - target) < 30


def test_the_extras_of_each_kind():
    words, ctx = ctx_for("fr")
    assert R.build("fusion_difference", words, ctx).extras["blend"] == "difference"
    assert R.build("soft_light", words, ctx).extras["blend"] == "softlight"
    assert R.build("perspective", words, ctx).extras["perspective"] == 12
    marks = R.build("emojis", words, ctx).extras["emojis"]
    assert {m[0] for m in marks} >= {"🏆", "🎭"}                 # prix, coulisses
    (sound, at, vol), = R.build("clic", words, ctx).extras["sounds"]
    assert sound.endswith("click_ui_click.mp3") and at == next(w[1] for w in words if bare(w[0]) == ctx.impact)
    behind = R.build("derriere", words, ctx)
    assert behind.needs == ("mask",) and len(behind.extras["behind"]) == len(ctx.strong) and "behind_ass" in behind.extras


def test_captions_leave_a_face_that_sits_low():
    words, ctx = ctx_for("fr", faces=[(t / 4, (400, 1180, 680, 1420)) for t in range(20)])    # a face in the bottom band
    lines = [l for l in R.build("evite_visage", words, ctx).ass.splitlines() if l.startswith("Dialogue")]
    assert lines and all(f"\\pos({ctx.cx},{ctx.y('haut')})" in l for l in lines)


def test_the_filters_burn_with_complex_shaping_and_bring_their_inputs(tmp_path):
    words, ctx = ctx_for("ar")
    inputs = []

    def add_input(*args):
        inputs.extend(args)
        return sum(1 for x in inputs if x == "-i")
    g, out, audio = R.filters(R.build("fusion_difference", words, ctx), "v", add_input, str(tmp_path))
    text = ";".join(g)
    assert "shaping=complex" in text and "blend=all_mode=difference" in text and out
    g, out, audio = R.filters(R.build("emojis", words, ctx), "v", add_input, str(tmp_path / "e"))
    assert "overlay" in ";".join(g) and any(str(x).endswith(".png") for x in inputs)
    g, out, audio = R.filters(R.build("clic", words, ctx), "v", add_input, str(tmp_path / "c"))
    assert len(audio) == 1 and "adelay" in ";".join(g)


def probe(path):
    return subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type:format=duration", "-of", "json",
                           str(path)], capture_output=True, text=True).stdout


@pytest.mark.parametrize("style_id, lang", [("surligneur", "ar"), ("fusion_difference", "fr"), ("emojis", "ar"),
                                            ("karaoke", "fr"), ("cascade", "en"), ("adaptation_or", "ar")])
def test_real_gallery_previews(style_id, lang):
    info = json.loads(probe(R.preview(style_id, lang)))
    assert 3.0 < float(info["format"]["duration"]) < 6.0


def test_a_preview_plays_its_style_s_sound_and_is_cached():
    path = R.preview("clic", "fr")
    assert "audio" in probe(path)
    mtime = Path(path).stat().st_mtime
    assert R.preview("clic", "fr") == path and Path(path).stat().st_mtime == mtime


# ---------------------------------------------------------------- the spaces

@pytest.fixture(scope="module")
def media(tmp_path_factory):
    from moviepy.editor import AudioClip, ColorClip
    d = tmp_path_factory.mktemp("captions_compose")
    ColorClip(size=(320, 240), color=(200, 160, 90), duration=1).write_videofile(str(d / "bg.mp4"), fps=10, codec="libx264", audio=False, logger=None)
    tone = lambda t: np.sin(2 * np.pi * 440 * np.atleast_1d(t))
    AudioClip(lambda t: tone(t).reshape(-1, 1) * 0.3, duration=2.2, fps=44100).write_audiofile(str(d / "voice.mp3"), fps=44100, nbytes=2, logger=None)
    AudioClip(lambda t: np.column_stack([tone(t), tone(t)]) * 0.3, duration=1, fps=44100).write_audiofile(str(d / "music.mp3"), fps=44100, nbytes=2, logger=None)
    return d


WORDS = [("Quand", 0.0, 0.4), ("ils", 0.4, 0.6), ("ont", 0.6, 0.8), ("créé", 0.8, 1.2), ("ce", 1.2, 1.4), ("prix.", 1.4, 2.2)]


@pytest.mark.parametrize("style", ["hierarchie", "clic", "soft_light"])
def test_generation_renders_a_library_style_for_real(media, tmp_path, style):
    from generative import ffmpeg_composer
    out = tmp_path / f"{style}.mp4"
    ffmpeg_composer.render_video_ffmpeg(str(media / "voice.mp3"), WORDS, str(media / "bg.mp4"), str(media / "music.mp3"),
                                        str(out), size=(1080, 1920), caption_style=style, captions_lang="fr")
    info = json.loads(probe(out))
    assert 2.0 < float(info["format"]["duration"]) < 2.6


def test_a_library_style_never_falls_back_to_moviepy(monkeypatch):
    from generative import ffmpeg_composer, video_composer

    def broken(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(ffmpeg_composer, "render_video_ffmpeg", broken)
    monkeypatch.setattr(video_composer, "render_video_moviepy", lambda *a, **k: pytest.fail("moviepy can't draw it"))
    with pytest.raises(RuntimeError):
        video_composer.render_video("n", WORDS, "b", "m", "out", caption_style="neon")


def test_the_generation_s_own_styles_keep_their_path_and_drop_the_library_settings(monkeypatch):
    from generative import ffmpeg_composer, video_composer
    seen = {}
    monkeypatch.setattr(ffmpeg_composer, "render_video_ffmpeg", lambda *a, **k: seen.update(k) or "out")
    video_composer.render_video("n", WORDS, "b", "m", "out", caption_style="karaoke", captions_lang="fr")
    assert seen["caption_style"] == "karaoke"


def test_the_montage_accepts_the_library_styles_it_can_draw():
    from montage import recipes
    assert recipes.clean_settings({"caption_style": "neon"}) == {"caption_style": "neon"}
    assert recipes.clean_settings({"caption_style": "derriere"}) == {}        # needs a person's mask: Discours only
    assert recipes.clean_settings({"caption_style": "comic-sans"}) == {}


def test_the_adaptation_draws_a_library_style_at_the_output_times():
    from adaptation import render as ar
    words = [{"w": w, "start": a, "end": b} for w, a, b in WORDS]
    passages = [{"words": list(range(len(words))), "mots_cles": ["prix"]}]
    segs = [{"va": 0.0, "vb": 2.2, "out": 1.0}]                  # the narration starts 1 s into the video
    built, n = ar._library_captions("hierarchie", {}, passages, words, segs, "fr", ".")
    first = next(l for l in built.ass.splitlines() if l.startswith("Dialogue"))
    assert n > 0 and first.split(",")[1] == "0:00:01.00"
    assert "fscx150" in built.ass                                # « prix » is a strong word: 150 %


def test_old_temp_folders_of_the_library_are_kept_by_the_cleanup():
    import storage
    assert {"caption_fonts", "caption_previews"} <= storage.PROTECTED_TEMP_DIRS


# ---------------------------------------------------------------- routes

def test_the_catalogue_route_filters_by_space_and_language(client):
    every = client.get("/api/captions/styles").json()
    assert len(every["styles"]) == len(S.STYLES) and "Adaptation (existants)" in every["groups"]
    ar = {s["id"] for s in client.get("/api/captions/styles?space=adaptation&lang=ar").json()["styles"]}
    assert "hierarchie" in ar and "typewriter" not in ar and "derriere" not in ar


def test_a_channel_s_caption_choice(client, project):
    project.add_channel("chanA")
    assert client.get("/api/channels/chanA/sous_titres").json()["style"] is None
    r = client.put("/api/channels/chanA/sous_titres", json={"style": "signature", "params": {"epaisseur": 99}})
    assert r.status_code == 200 and r.json()["style"] == "signature" and r.json()["params"]["epaisseur"] == 16
    assert R.channel_choice("chanA")["style"] == "signature"
    assert client.put("/api/channels/chanA/sous_titres", json={"style": "derriere"}).status_code == 400
    assert client.put("/api/channels/chanA/sous_titres", json={"style": None}).json()["style"] is None


def test_an_arabic_channel_can_t_pick_a_latin_only_style(client, project):
    project.add_channel("chanAr")
    from channel_manager import ChannelManager
    cm = ChannelManager()
    prof = cm.get_channel_profile("chanAr")
    prof["language_hint"] = "ar"
    cm.save_channel_profile("chanAr", prof)
    assert client.put("/api/channels/chanAr/sous_titres", json={"style": "typewriter"}).status_code == 400
    assert client.put("/api/channels/chanAr/sous_titres", json={"style": "hierarchie"}).status_code == 200


def test_the_preview_route(client):
    r = client.get("/api/captions/preview/rebond?lang=ar")
    assert r.status_code == 200 and r.headers["content-type"] == "video/mp4"
    assert client.get("/api/captions/preview/nope").status_code == 404
    assert client.get("/api/captions/preview/rebond?params={bad").status_code == 400


# ---------------------------------------------------------------- smart placement, legibility, common settings

def fake_scene(zone, busy_rows=None, bright=False, seconds=6):
    """A Scene of flat frames; busy_rows (canvas y0, y1): a checkerboard there (lots of details); bright: white."""
    from captions.core import Scene
    zx, zy, zw, zh = zone
    h, w = zh // 4, zw // 4
    img = np.full((h, w), 235.0 if bright else 40.0, np.float32)
    if busy_rows:
        r0, r1 = (busy_rows[0] - zy) // 4, (busy_rows[1] - zy) // 4
        img[r0:r1] = (np.indices((r1 - r0, w)).sum(axis=0) % 2) * 255.0
    return Scene([(t / 3, img) for t in range(seconds * 3)], zone, 4)


def positions(built):
    import re
    return [int(m) for m in re.findall(r"\\pos\(\d+,(\d+)\)", "\n".join(l for l in built.ass.splitlines() if l.startswith("Dialogue")))]


def test_auto_leaves_a_busy_band_and_keeps_its_place():
    words, ctx = ctx_for("fr")
    ctx.scene = fake_scene(ctx.zone, busy_rows=(ctx.y("bas") - 80, ctx.y("bas") + 80))
    ys = set(positions(R.build("resserre", words, ctx)))
    assert ctx.y("bas") not in ys and len(ys) == 1                 # never on the busy band, always the same band


def test_auto_without_any_picture_uses_the_preferred_band():
    words, ctx = ctx_for("fr")
    assert set(positions(R.build("resserre", words, ctx))) == {ctx.y("bas")}
    assert set(positions(R.build("resserre", words, ctx, {"preferee": "haut"}))) == {ctx.y("haut")}


def test_a_fixed_position_its_offset_and_the_reprise_anchor():
    words, ctx = ctx_for("fr")
    x, y, w, h = ctx.zone
    assert set(positions(R.build("resserre", words, ctx, {"position": "milieu", "decalage": 10}))) == {ctx.y("milieu") + h // 10}
    ctx.anchor_y = 1449
    assert set(positions(R.build("resserre", words, ctx))) == {1449}


def test_readability_thickens_the_outline_over_a_bright_picture():
    words, ctx = ctx_for("fr")
    ctx.scene = fake_scene(ctx.zone, bright=True)
    built = R.build("resserre", words, ctx, {"position": "bas"})
    assert "\\bord3" in built.ass and "\\p1" in built.ass         # very bright: a soft block too
    assert "\\bord3" not in R.build("resserre", words, ctx, {"position": "bas", "lisibilite": False}).ass


def test_the_common_settings_reach_the_style_line_and_the_events():
    words, ctx = ctx_for("fr")
    built = R.build("pop", words, ctx, {"police": "lilita", "contour": 6, "contour_couleur": "#ff0000", "ombre": 4,
                                        "fond": "bloc", "fond_opacite": 100, "animation": "aucune"})
    style_line = next(l for l in built.ass.splitlines() if l.startswith("Style: Pop"))
    assert "Lilita One" in style_line and ",6,4,5," in style_line and "&H000000FF" in style_line
    assert "\\1a&H00&" in built.ass and "\\t(" not in built.ass  # opaque box, no animation
    ar = R.build("pop", *ctx_for("ar")[:1], ctx_for("ar")[1], {"police": "lilita"})
    assert "Tajawal" in next(l for l in ar.ass.splitlines() if l.startswith("Style: Pop"))


def test_the_scene_of_a_real_video(tmp_path):
    clip = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25", "-t", "2", str(clip)], check=True)
    sc = R.scene(str(clip), (87, 507, 906, 906))
    assert sc and len(sc.frames) == 6
    busy, luma = sc.band(0, 2, 507 + 453)
    assert 0 < busy <= 1 and 0 < luma < 255
    looped = R.scene(str(clip), (87, 507, 906, 906), until=5.0)
    assert looped.frames[-1][0] > 4.0                               # a short background loops


def test_analyse_looks_only_when_the_style_needs_it(tmp_path, monkeypatch):
    clip = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25", "-t", "1", str(clip)], check=True)
    monkeypatch.setattr(R, "faces", lambda *a, **k: [(0.1, (1, 2, 3, 4))])
    words, ctx = ctx_for("fr")
    R.analyse(ctx, "hierarchie", {}, str(clip))
    assert ctx.faces and ctx.scene                                  # « Auto » avoiding faces: both
    words, ctx = ctx_for("fr")
    R.analyse(ctx, "hierarchie", {"position": "bas", "lisibilite": False}, str(clip))
    assert not ctx.faces and ctx.scene is None
    words, ctx = ctx_for("fr")
    R.analyse(ctx, "karaoke", {}, str(clip))
    assert ctx.scene is None                                        # the spaces' own styles: nothing to look at
