"""
ElevenLabs: the voice library and the narration.

The key needs "Text to Speech" (narration) and "Voices: Read" (names,
accents, previews). A voice from the public library that isn't in "My Voices"
is still readable through /shared-voices and still speaks (both tested).
"""

import base64
import os
from typing import Dict, List, Optional

import requests

API = "https://api.elevenlabs.io"
MODEL = "eleven_multilingual_v2"


class VoiceError(RuntimeError):
    pass


def _key() -> str:
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        raise VoiceError("ELEVENLABS_API_KEY manquante dans .env")
    return key


def fetch_info(voice_id: str) -> Dict:
    """{voice_id, name, language, accent, gender, age, use_case, description, preview_url}
    from "My Voices", else from the public library."""
    h = {"xi-api-key": _key()}
    r = requests.get(f"{API}/v1/voices/{voice_id}", headers=h, timeout=30)
    if r.status_code == 200:
        d = r.json()
        labels = d.get("labels") or {}
        verified = d.get("verified_languages") or []
        language = labels.get("language") or (verified[0].get("language") if verified else None)
        return {"voice_id": voice_id, "name": d.get("name"), "language": language,
                "accent": labels.get("accent") or (verified[0].get("accent") if verified else None),
                "gender": labels.get("gender"), "age": labels.get("age"), "use_case": labels.get("use_case"),
                "description": labels.get("descriptive") or d.get("description"), "preview_url": d.get("preview_url")}
    if r.status_code in (401, 403):
        raise VoiceError("La clé ElevenLabs n'a pas la permission « Voices : Read ».")
    s = requests.get(f"{API}/v1/shared-voices", headers=h, params={"search": voice_id, "page_size": 10}, timeout=30)
    for v in (s.json().get("voices") or []) if s.status_code == 200 else []:
        if v.get("voice_id") == voice_id:
            return {"voice_id": voice_id, "name": v.get("name"), "language": v.get("language"),
                    "accent": v.get("accent"), "gender": v.get("gender"), "age": v.get("age"),
                    "use_case": v.get("use_case"), "description": v.get("descriptive") or v.get("description"),
                    "preview_url": v.get("preview_url")}
    raise VoiceError(f"Voix {voice_id} introuvable chez ElevenLabs.")


def download_preview(url: str, path: str) -> Optional[str]:
    """The official sample (free: no credits)."""
    if not url:
        return None
    r = requests.get(url, timeout=60)
    if r.status_code != 200:
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(r.content)
    return path


def synthesize(passages: List[Dict], voice_id: str, lang_code: str, out_mp3: str) -> Dict:
    """Narrates every passage['texte'] in one take (natural flow between
    sentences) and returns the word timings and each passage's span:
    {"words": [{w, start, end}], "passages": [{..., start, end, words: [i]}], "duration": s}."""
    text, spans = "", []
    for p in passages:
        if text:
            text += " "
        spans.append((len(text), len(text) + len(p["texte"])))
        text += p["texte"]
    r = requests.post(f"{API}/v1/text-to-speech/{voice_id}/with-timestamps", headers={"xi-api-key": _key()},
                      timeout=300, json={"text": text, "model_id": MODEL, "language_code": lang_code.split("-")[0],
                                         "voice_settings": {"stability": 0.5, "similarity_boost": 0.8,
                                                            "style": 0.15, "speed": 1.0}})
    if r.status_code != 200:
        raise VoiceError(f"ElevenLabs HTTP {r.status_code} : {r.text[:300]}")
    d = r.json()
    os.makedirs(os.path.dirname(out_mp3), exist_ok=True)
    with open(out_mp3, "wb") as f:
        f.write(base64.b64decode(d["audio_base64"]))
    al = d["alignment"]
    chars, st, en = al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]
    return align(passages, spans, chars, st, en)


def align(passages, spans, chars, st, en) -> Dict:
    """Character timings -> word timings + each passage's [start, end] and words."""
    words, cur = [], None
    for i, ch in enumerate(chars):
        if ch.isspace():
            if cur:
                words.append(cur)
                cur = None
            continue
        if cur is None:
            cur = {"w": "", "start": st[i], "end": en[i], "char": i}
        cur["w"] += ch
        cur["end"] = en[i]
    if cur:
        words.append(cur)
    out = []
    for p, (a, b) in zip(passages, spans):
        q = dict(p)
        q["start"], q["end"] = st[a], en[b - 1]
        q["words"] = [i for i, w in enumerate(words) if a <= w["char"] < b]
        out.append(q)
    return {"words": words, "passages": out, "duration": en[-1] if en else 0.0}
