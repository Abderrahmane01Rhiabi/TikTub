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
    assert p["grand"] == 200 and p["petit"] == 80 and p["couleur"] == "#ffffff" and p["position"] == "bas" and "x" not in p
    assert S.STYLES["surligneur"].clean({"contour": "true"})["contour"] is True


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
