"""
What is measured on a render before a person ever sees it.

Born from a real miss: the sound once stopped 3 s before the picture, and
only volume had been checked. Every check here is a measurement, not a guess.
"""

import json
import re
import subprocess
from typing import Dict, List

import numpy as np

from adaptation.render import GAP


def _probe(path: str) -> Dict[str, float]:
    out = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration",
                                              "-of", "json", path]))
    return {s["codec_type"]: float(s.get("duration") or 0) for s in out.get("streams", [])}


def _pcm(path: str, ss: float, t: float) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(ss, 0):.3f}", "-t", f"{t:.3f}", "-i", path,
                          "-ac", "1", "-ar", "8000", "-f", "s16le", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.int16).astype(float)


def loudness(path: str) -> float:
    err = subprocess.run(["ffmpeg", "-i", path, "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    vals = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
    return float(vals[-1]) if vals else float("nan")


def sentence_offsets(out_path: str, voice_path: str, passages: List[Dict]) -> List[float]:
    """Where each sentence of the narration really starts in the render,
    minus where it should: cosine match of its first 1.2 s (skipping the
    quiet attack), searched ±0.5 s around the planned spot."""
    offsets, t = [], 0.0
    for p in passages:
        a, b = max(0.0, p["start"] - 0.04), p["end"] + 0.10
        ref = _pcm(voice_path, a + 0.2, 1.2)
        win = _pcm(out_path, t - 0.3, 2.0)
        if len(ref) and len(win) > len(ref):
            nr = np.linalg.norm(ref) + 1e-9
            scores = [np.dot(win[i:i + len(ref)], ref) / ((np.linalg.norm(win[i:i + len(ref)]) + 1e-9) * nr)
                      for i in range(0, len(win) - len(ref), 8)]
            found = (t - 0.3 if t >= 0.3 else 0.0) + int(np.argmax(scores)) * 8 / 8000
            offsets.append(round(found - (t + 0.2), 3) if max(scores) > 0.5 else None)
        else:
            offsets.append(None)
        t += (b - a) + GAP
    return offsets


def verify(out_path: str, voice_path: str, passages: List[Dict]) -> Dict:
    """{"ok": bool, "problems": [...], "measures": {...}} — problems are in French,
    for the person reviewing the preview."""
    problems = []
    d = _probe(out_path)
    v, a = d.get("video", 0.0), d.get("audio", 0.0)
    if abs(v - a) > 0.15:
        problems.append(f"Le son ({a:.1f} s) ne dure pas autant que l'image ({v:.1f} s).")
    lufs = loudness(out_path)
    if not (-17.0 <= lufs <= -11.0):
        problems.append(f"Volume global hors norme : {lufs:.1f} LUFS (attendu entre -17 et -11).")
    offs = sentence_offsets(out_path, voice_path, passages)
    for k, o in enumerate(offs):
        if o is None:
            problems.append(f"Phrase {k + 1} introuvable dans le son de la vidéo.")
        elif abs(o) > 0.12:
            problems.append(f"Phrase {k + 1} décalée de {o:+.2f} s.")
    return {"ok": not problems, "problems": problems,
            "measures": {"video_s": round(v, 2), "audio_s": round(a, 2), "lufs": round(lufs, 1), "offsets": offs}}
