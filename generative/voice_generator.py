#!/usr/bin/env python3
"""
Voice Generator - ElevenLabs narration + real, audio-measured word timing.
============================================================================
Turns a script (with inline ElevenLabs v3 delivery tags like [calm] and
<break time="0.6s" />) into narration audio, then measures word-level timing
by transcribing the ACTUAL generated audio with a local Whisper model rather
than trusting ElevenLabs' self-reported alignment.

Why: ElevenLabs' alignment timestamps are the model's own estimate made
*during* synthesis — in particular they don't reflect the real duration a
<break> tag actually inserts into the audio, which made captions drift out
of sync (worse the more break tags a script used). Whisper instead measures
timing directly from the rendered waveform, so there's nothing left to
estimate or correct — it's grounded in what's really in the file.

Whisper's own transcribed wording can have small ASR slips (a mis-heard
word here and there), so it's used ONLY for timing: the displayed caption
text always comes from the original script, aligned word-by-word onto
Whisper's timestamps via a fuzzy sequence match, with linear interpolation
for any script word Whisper didn't clearly detect.
"""

import os
import re
import unicodedata
from difflib import SequenceMatcher
from typing import List, Tuple

from dotenv import load_dotenv
load_dotenv()

from elevenlabs.client import ElevenLabs
from faster_whisper import WhisperModel

# Emotion/pause delivery tags ([calm], <break time="0.6s" />) are part of the
# ElevenLabs input text but are never spoken, so they're stripped before
# building the expected word list.
TAG_PATTERN = re.compile(r"\[[^\]]*\]|<[^>]*>")

WordTimings = List[Tuple[str, float, float]]

_whisper_model = None


def _get_whisper_model() -> WhisperModel:
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
    return _whisper_model


def _normalize(word: str) -> str:
    word = unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", word.lower())


def _align_to_whisper(script_words: List[str], whisper_words: List[Tuple[str, float, float]]) -> WordTimings:
    """Keep the original script wording (authoritative, no ASR typos), timed
    using Whisper's real-audio timestamps via a fuzzy sequence match. Any
    script word Whisper didn't line up with gets its timing linearly
    interpolated from its nearest matched neighbors."""
    a = [_normalize(w) for w in script_words]
    b = [_normalize(w[0]) for w in whisper_words]
    matcher = SequenceMatcher(None, a, b, autojunk=False)

    timings: List[Tuple[float, float]] = [None] * len(script_words)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        n, m = i2 - i1, j2 - j1
        if n == 0:
            continue
        if tag == "equal" or n == m:
            for k in range(n):
                timings[i1 + k] = (whisper_words[j1 + k][1], whisper_words[j1 + k][2])
        elif m > 0:
            # Different word counts in this stretch (e.g. an ASR slip) —
            # spread Whisper's measured span for the stretch evenly across
            # the script words it corresponds to.
            span_start, span_end = whisper_words[j1][1], whisper_words[j2 - 1][2]
            step = (span_end - span_start) / n
            for k in range(n):
                timings[i1 + k] = (span_start + k * step, span_start + (k + 1) * step)
        # else: m == 0, Whisper found nothing at all for this stretch — left
        # None, filled by interpolation below.

    for i in range(len(timings)):
        if timings[i] is not None:
            continue
        prev_i = next((j for j in range(i - 1, -1, -1) if timings[j] is not None), None)
        next_i = next((j for j in range(i + 1, len(timings)) if timings[j] is not None), None)
        prev_end = timings[prev_i][1] if prev_i is not None else 0.0
        next_start = timings[next_i][0] if next_i is not None else prev_end + 0.3
        timings[i] = (prev_end, max(next_start, prev_end + 0.05))

    return [(w, t[0], t[1]) for w, t in zip(script_words, timings)]


def synthesize(script_text: str, voice_id: str, out_mp3_path: str, model_id: str = "eleven_v3") -> WordTimings:
    """Generate narration audio via ElevenLabs; save it to out_mp3_path; return
    word-level (text, start_seconds, end_seconds) timings measured from the
    real generated audio (via local Whisper), for accurate caption sync."""
    client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
    audio_chunks = client.text_to_speech.convert(
        voice_id=voice_id,
        text=script_text,
        model_id=model_id,
        output_format="mp3_44100_128",
    )

    os.makedirs(os.path.dirname(out_mp3_path), exist_ok=True)
    with open(out_mp3_path, "wb") as f:
        for chunk in audio_chunks:
            f.write(chunk)

    script_words = TAG_PATTERN.sub(" ", script_text).split()

    segments, _ = _get_whisper_model().transcribe(out_mp3_path, language="fr", word_timestamps=True)
    whisper_words = [(w.word.strip(), w.start, w.end) for seg in segments for w in seg.words]

    words = _align_to_whisper(script_words, whisper_words)

    # A trailing word with no matched neighbor after it (e.g. dangling
    # punctuation) gets an interpolated guess that can overshoot the real
    # file — clamp so a caption timestamp never points past the actual audio.
    from moviepy.editor import AudioFileClip
    real_duration = AudioFileClip(out_mp3_path).duration
    return [(w, min(s, real_duration), min(e, real_duration)) for w, s, e in words]
