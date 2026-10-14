"""ffmpeg composer: the native one-pass render used for the karaoke style."""

import subprocess
from pathlib import Path

import numpy as np
import pytest

from generative import ffmpeg_composer, video_composer

WORDS = [("Bonjour", 0.0, 0.5), ("{le}", 0.5, 1.0), ("monde.", 1.0, 1.6), ("Suite", 1.6, 2.2)]


def test_ass_has_one_event_per_word_with_the_spoken_word_highlighted():
    ass = ffmpeg_composer.build_karaoke_ass(WORDS, (1080, 1920), accent_color="#ff0000")
    events = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
    assert len(events) == 4
    # "monde." ends a sentence → "Suite" starts a new line, alone on it
    assert "Suite" in events[3] and "Bonjour" not in events[3]
    assert events[0].split(",")[1:3] == ["0:00:00.00", "0:00:00.50"]
    assert "{\\c&H0000FF&}monde." in ass                 # #ff0000 as an inline tag: &HBBGGRR&
    assert "{le}" not in ass and "(le)" in ass          # braces would be read as ASS tags
    assert "PlayResX: 1080" in ass and "WrapStyle: 2" in ass


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    """Real tiny inputs: a background video, a MONO narration, stereo music."""
    from moviepy.editor import AudioClip, ColorClip
    d = tmp_path_factory.mktemp("compose")
    ColorClip(size=(320, 240), color=(30, 60, 90), duration=1).write_videofile(str(d / "bg.mp4"), fps=10, codec="libx264", audio=False, logger=None)
    tone = lambda t: np.sin(2 * np.pi * 440 * np.atleast_1d(t))
    AudioClip(lambda t: tone(t).reshape(-1, 1) * 0.3, duration=2.2, fps=44100).write_audiofile(str(d / "voice.mp3"), fps=44100, nbytes=2, logger=None)
    AudioClip(lambda t: np.column_stack([tone(t), tone(t)]) * 0.3, duration=1, fps=44100).write_audiofile(str(d / "music.mp3"), fps=44100, nbytes=2, logger=None)
    return d


def probe(path):
    return subprocess.run([ffmpeg_composer.ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr


@pytest.mark.parametrize("frame_mode, rounded", [("fill", False), ("full_border", True)])
def test_real_ffmpeg_render(media, tmp_path, frame_mode, rounded):
    out = tmp_path / f"{frame_mode}.mp4"
    steps = []
    ffmpeg_composer.render_video_ffmpeg(
        str(media / "voice.mp3"), WORDS, str(media / "bg.mp4"), str(media / "music.mp3"), str(out),
        size=(360, 640), frame_mode=frame_mode, rounded_corners=rounded, progress_cb=steps.append)

    info = probe(out)
    assert "Duration: 00:00:02.2" in info            # trimmed to the narration, background/music looped
    assert "360x640" in info and "stereo" in info
    assert steps and steps[-1] == 1.0 and all(b >= a for a, b in zip(steps, steps[1:]))


def test_karaoke_goes_through_ffmpeg_and_falls_back_to_moviepy_on_failure(monkeypatch):
    calls = []
    monkeypatch.setattr(video_composer, "render_video_moviepy", lambda *a, **k: calls.append("moviepy") or "out")

    monkeypatch.setattr(ffmpeg_composer, "render_video_ffmpeg", lambda *a, **k: calls.append("ffmpeg") or "out")
    video_composer.render_video("n", WORDS, "b", "m", "out", caption_style="karaoke")
    assert calls == ["ffmpeg"]

    def broken(*a, **k):
        calls.append("ffmpeg-failed")
        raise RuntimeError("no libass")
    monkeypatch.setattr(ffmpeg_composer, "render_video_ffmpeg", broken)
    video_composer.render_video("n", WORDS, "b", "m", "out", caption_style="karaoke")
    assert calls[1:] == ["ffmpeg-failed", "moviepy"]  # a broken ffmpeg never breaks a creation


def test_unknown_style_and_the_override_stay_on_moviepy(monkeypatch):
    calls = []
    monkeypatch.setattr(video_composer, "render_video_moviepy", lambda *a, **k: calls.append("moviepy") or "out")
    monkeypatch.setattr(ffmpeg_composer, "render_video_ffmpeg", lambda *a, **k: calls.append("ffmpeg") or "out")

    video_composer.render_video("n", WORDS, "b", "m", "out", caption_style="some-future-style")
    monkeypatch.setenv("TIKTUB_RENDERER", "moviepy")
    video_composer.render_video("n", WORDS, "b", "m", "out", caption_style="karaoke")
    assert calls == ["moviepy", "moviepy"]


def test_every_caption_style_has_an_ffmpeg_builder():
    from generative import caption_styles
    assert set(caption_styles.STYLES) == ffmpeg_composer.ASS_STYLES == set(ffmpeg_composer.BUILDERS)


@pytest.mark.parametrize("style, signature", [
    ("mrbeast", "BONJOUR"),                 # all caps
    ("hormozi", "\\p1"),                    # the rounded color box is a vector drawing
    ("bounce", "\\t(0,"),                    # pop-in animation
    ("typewriter", "\\an4"),               # left-anchored growing text + cursor
    ("minimal", "\\fad("),                   # fade-in
])
def test_each_style_builds_its_signature_effect(style, signature):
    ass = ffmpeg_composer.build_ass(WORDS, (1080, 1920), style)
    assert signature in ass and ass.count("Dialogue:") >= 2


def test_font_size_matches_the_moviepy_glyph_size():
    """libass sizes by usWinAscent+usWinDescent; PIL by em. FreeSans has very
    different metrics: using PIL's ascent+descent made it 18 % too small."""
    from generative import caption_styles as cs
    f = ffmpeg_composer.FontSpec(cs.FONT_HEAVY, 72)
    upm, win = ffmpeg_composer._win_metrics(cs.FONT_HEAVY)
    assert f.ass_size == pytest.approx(72 * win / upm, abs=0.1) and f.ass_size > sum(f.pil.getmetrics()) + 10


def test_typewriter_steps_never_overlap_even_with_overlapping_word_timings():
    """Regression: a 50 ms minimum per letter and Whisper timings where a
    word 'ends' after the next starts (plus zero-length « tokens) showed two
    versions of the line at once — in the moviepy version too."""
    words = [("Le", 0.0, 0.2), ("«", 0.2, 0.2), ("commencement", 0.2, 0.55), ("arrive", 0.5, 0.9), ("vite.", 0.9, 1.2)]
    def t(x):
        h, m, sec = x.split(":"); return int(h) * 3600 + int(m) * 60 + float(sec)
    ev = [l.split(",") for l in ffmpeg_composer.build_ass(words, (1080, 1920), "typewriter").splitlines() if l.startswith("Dialogue")]
    texts = [(t(e[1]), t(e[2])) for e in ev if "\\an4" in ",".join(e[9:])]
    assert all(b0 >= a1 - 1e-9 for (_, a1), (b0, _) in zip(texts, texts[1:]))

    from generative import caption_styles
    spans = sorted((c.start, c.end) for c in caption_styles.typewriter_build_clips(words, (1080, 1920)))
    assert all(b0 >= a1 - 1e-6 for (_, a1), (b0, _) in zip(spans, spans[1:]))


def test_short_music_is_chained_with_crossfades():
    assert ffmpeg_composer.music_copies_needed(100, 40) == 1
    n = ffmpeg_composer.music_copies_needed(15, 40)
    xf = ffmpeg_composer.LOOP_CROSSFADE
    assert n == 3 and 15 + (n - 1) * (15 - xf) >= 40
    filters = ";".join(ffmpeg_composer._music_filters([2, 3, 4], 15, 40))
    assert filters.count("acrossfade") == 2 and "afade=t=in" in filters and "afade=t=out" in filters


@pytest.mark.parametrize("style", ["hormozi", "bounce", "typewriter"])
def test_real_render_of_the_animated_styles(media, tmp_path, style):
    out = tmp_path / f"{style}.mp4"
    ffmpeg_composer.render_video_ffmpeg(str(media / "voice.mp3"), WORDS, str(media / "bg.mp4"), str(media / "music.mp3"),
                                        str(out), size=(360, 640), caption_style=style)
    assert "Duration: 00:00:02.2" in probe(out)


def test_no_caption_ever_leaves_the_safe_area():
    """Regression: wrapping measured plain lowercase text with normal spaces
    while styles draw capitals / stroke-inclusive word boxes — on real
    scripts half the MrBeast lines left the frame. Measured as drawn now,
    and a single unit too long for the frame is shrunk to fit."""
    from generative import caption_styles as cs
    text = ("et autorise-toi à relâcher toute tension. je n'ai plus besoin de forcer les portes fermées, "
            "anticonstitutionnellement extraordinairement inconditionnellement").split()
    words = [(w, i * 0.4, i * 0.4 + 0.35) for i, w in enumerate(text)]
    limit = 1080 - 2 * cs.MARGIN

    f = cs._font(cs.FONT_HEAVY, cs._MRBEAST_FONT_SIZE)
    m = lambda t: cs.drawn_words_width(t, f, cs._MRBEAST_STROKE, upper=True)
    for line in cs.group_into_lines(words, f, cs._MRBEAST_STROKE, limit, m):
        joined = " ".join(w[0] for w in line)
        assert m(joined) * cs.fit_scale(m(joined), limit) <= limit + 0.5

    f = cs._font(cs.FONT_BOLD, cs._KARAOKE_FONT_SIZE)
    m = lambda t: cs.drawn_words_width(t, f, cs._KARAOKE_STROKE)
    assert all(m(" ".join(w[0] for w in l)) * cs.fit_scale(m(" ".join(w[0] for w in l)), limit) <= limit + 0.5
               for l in cs.group_into_lines(words, f, cs._KARAOKE_STROKE, limit, m))

    # the longest word, popping in at 110 %, gets a shrink factor in both renderers
    ass = ffmpeg_composer.build_ass(words, (1080, 1920), "bounce")
    long_word_event = next(l for l in ass.splitlines() if "INCONDITIONNELLEMENT" in l)
    assert "\\fscx40.0" not in long_word_event  # scaled below the normal 40 % start
