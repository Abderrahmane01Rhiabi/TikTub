"""
Word-level transcription of a clip with faster-whisper.

"medium", not the "small" model the generative pipeline uses: here there is
no script to align against, so Whisper's own words ARE the captions and
Gemini's edit points — "small" heard "Carolina repurchased" for "Carolina
Reaper" and missed half the words of a mumbled interview.
"""

from typing import List, Tuple

Words = List[Tuple[str, float, float]]

_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel("medium", device="cpu", compute_type="int8")
    return _model


def transcribe(video_path: str) -> Words:
    """[(word, start_s, end_s), ...] in speaking order; [] when nothing is said."""
    segments, _info = _get_model().transcribe(video_path, word_timestamps=True)
    return [(w.word.strip(), round(w.start, 2), round(w.end, 2))
            for seg in segments for w in (seg.words or []) if w.word.strip()]
