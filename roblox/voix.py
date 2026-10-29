"""
The voices of the Roblox Shorts, chosen by ear in the lab (etude_roblox/voix, 2026-10-29): read with Eleven v4 and
its emotion tags, they replace the player's voice and tell the story. Donny (French) and Tyler (English) were the
best; Marcus was rejected. Each has a sample to listen to before choosing: the lab's own recording of the same
POV (assets/roblox_voix/<id>_<lang>.mp3), else ElevenLabs' free preview, kept with the voice library's.

Replacing the player's voice (measured in the lab):
    separate     Demucs splits each passage into his voice and the rest (the game's sounds and music) — ~110 s
                 for a 75-s passage on the processor; the Voice Changer on his voice glitched when he laughed
    write_lines  Gemini listens to his voice and writes his lines whole (the automatic subtitles are cut and
                 wrong), in each language, with the emotions where he laughs or shouts ([laughs], [shouts]…)
    the render   reads them with the chosen voice (render.py), over the rest
"""

import os
import re
import subprocess
import sys
from typing import Dict, List, Optional

from adaptation import settings
from adaptation import voices as el

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(HERE, "assets", "roblox_voix")

# (voice_id, name, what it sounds like) — the best first
CATALOGUE = {
    "fr": [("zZruxT34wOCwRrqvb99N", "Donny", "homme jeune, dynamique"),
           ("Jrq4GqCKqYpigdQsZRkP", "Anatole", "homme jeune, dynamique et clair"),
           ("GPAQQPp9dazaB2bl4zg9", "Victor", "homme jeune, décontracté"),
           ("R89ZQJowZAEgiPNyC3dQ", "Jeunot", "homme jeune, clair et positif"),
           ("EmZGlxI7QPvCEMOkFhB9", "Liam", "homme jeune, vif"),
           ("OPCL81coXM3AEo8gUxHM", "Maxime Lavaud", "homme jeune, joyeux"),
           ("mvhJVdVoTWVUtL4keT7W", "Simon", "homme jeune, rapide et enjoué"),
           ("jsScnYkNNda9Q1NES5nn", "Léo", "homme jeune, énergique"),
           ("QEZnlKYcLy9N2ierwPEc", "Lucas", "homme jeune, dynamique"),
           ("IHngRooVccHyPqB4uQkG", "Corentin", "homme jeune, enthousiaste"),
           ("7pDdnNI6PhXmAp0pXFZm", "Noé", "homme jeune, créateur de contenu"),
           ("pMMW9rLezW8kdNoXPDQX", "Pdz", "homme jeune, créateur de contenu"),
           ("lvzDI3XrCzseDsjZkbOV", "Mike", "ado, hésitant"),
           ("1a3lMdKLUcfcMtvN772u", "Antoine", "homme jeune, posé"),
           ("yG4Uc56cLYQyZFnWaYv2", "Kael", "homme jeune, posé"),
           ("sfJopaWaOtauCD3HKX6Q", "Arthur", "homme jeune, décontracté (voix anglaise)"),
           ("KSyQzmsYhFbuOhqj1Xxv", "Lea", "femme, dynamique"),
           ("OSwaPSNdfituxkWcjlkR", "Kano", "femme jeune, style anime (voix japonaise)")],
    "en": [("SA7eD52NRr8WAehitVt1", "Tyler", "homme, très énergique"),
           ("9yzdeviXkFddZ4Oz8Mok", "Lutz", "homme jeune, rigole beaucoup"),
           ("Sun6GPdivU7N4kTmYtDw", "Echo", "ado, énergique (accent britannique)"),
           ("TX3LPaxmHKxFdv7VOQHJ", "Liam", "homme jeune"),
           ("sfJopaWaOtauCD3HKX6Q", "Arthur", "homme jeune, décontracté"),
           ("bxiObU1YDrf7lrFAyV99", "Ashley", "femme jeune, énergique")],
}
DEFAULTS = {lang: voices[0][0] for lang, voices in CATALOGUE.items()}


def catalogue(lang: str) -> List[Dict]:
    return [{"voice_id": v, "nom": n, "description": d, "meilleure": k == 0}
            for k, (v, n, d) in enumerate(CATALOGUE.get(lang, []))]


def known(lang: str, voice_id: str) -> bool:
    return any(v == voice_id for v, _, _ in CATALOGUE.get(lang, []))


def lab_sample(voice_id: str, lang: str) -> str:
    return os.path.join(SAMPLES, f"{voice_id}_{lang}.mp3")


def sample(voice_id: str, lang: str) -> Optional[str]:
    """The lab's recording of this voice in this language, else ElevenLabs' free preview (fetched once, kept)."""
    if not known(lang, voice_id):
        return None
    if os.path.exists(lab_sample(voice_id, lang)):
        return lab_sample(voice_id, lang)
    path = settings.preview_path(voice_id)
    if os.path.exists(path):
        return path
    return el.download_preview(el.fetch_info(voice_id).get("preview_url"), path)


# ---------------------------------------------------------------- his voice, apart from the game's sounds

DEMUCS = "htdemucs"
TAGS = ["excited", "laughs", "laughing", "chuckles", "shouts", "frustrated", "surprised", "sarcastic", "sighs", "gasps"]
TAG = re.compile(r"\[[^\]]*\]")


class VoixError(RuntimeError):
    pass


def sans_balises(text: str) -> str:
    """The line as shown on screen: without its emotion tags."""
    return " ".join(TAG.sub(" ", text or "").split())


def _run(cmd: List[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise VoixError(f"{os.path.basename(cmd[0])} : {r.stderr.strip()[-300:]}")


def separate(src: str, work: str) -> Dict[str, str]:
    """{"voix": his voice alone, "reste": everything else} for the whole passage (kept: done once)."""
    done = os.path.join(work, DEMUCS, "passage")
    out = {"voix": os.path.join(done, "vocals.wav"), "reste": os.path.join(done, "no_vocals.wav")}
    if all(os.path.exists(x) for x in out.values()):
        return out
    os.makedirs(work, exist_ok=True)
    wav = os.path.join(work, "passage.wav")
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", src, "-vn", "-ac", "2", "-ar", "44100", wav])
    _run([sys.executable, "-m", "demucs", "--two-stems", "vocals", "-n", DEMUCS, "-d", "cpu", "-o", work, wav])
    os.remove(wav)
    return out


LINES_PROMPT = """Ecoute la voix d'un joueur de Roblox qui commente sa partie (sa voix seule, sans le jeu). Ce qui se
passe : {resume}
Ses repliques d'apres les sous-titres automatiques (coupees au hasard, parfois fausses), avec leurs instants :
{lignes}
Une voix de synthese (ElevenLabs v4) va relire ses repliques ; elle comprend des balises d'emotion entre crochets :
{tags}.
Ecris ses phrases ENTIERES (corrige les mots mal reconnus d'apres ce que tu entends), avec son energie de jeune
streamer : place les balises exactement la ou il rit, crie, s'enerve ou s'etonne. Pas plus de 2 balises par phrase.
Chaque phrase doit tenir dans le temps jusqu'a la suivante (environ 3 mots par seconde maximum).
"a" = l'instant ou il commence la phrase, en secondes depuis le debut de CET audio.
Donne chaque phrase dans ces langues : {langues} (parle, comme un jeune gamer de cette langue, memes balises).
S'il ne dit rien, renvoie une liste vide.
JSON uniquement : {{"phrases": [{{"a": s, {schema}}}]}}"""


def write_lines(vocals: str, a: float, b: float, resume: str, dialogue: List[Dict], langs: List[str],
                gemini=None) -> List[Dict]:
    """His lines between a and b (seconds of the passage), each language: [{"a": seconds of the passage, lang: text}]."""
    from roblox.plan import LANG_NAMES
    txt = "\n".join(f"{l['a'] - a:.1f} s : {l['texte']}" for l in dialogue) or "(aucun sous-titre)"
    prompt = LINES_PROMPT.format(resume=resume or "", lignes=txt, tags=", ".join(f"[{t}]" for t in TAGS),
                                 langues=", ".join(f"{l} ({LANG_NAMES.get(l, l)})" for l in langs),
                                 schema=", ".join(f'"{l}": "..."' for l in langs))
    if gemini is not None:
        r = gemini._generate_content([{"text": prompt}], max_tokens=4000, timeout=180, temperature=0.4)
    else:
        from adaptation import sources
        clip = os.path.splitext(vocals)[0] + f"_{int(a)}_{int(b)}.mp4"
        _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "color=black:s=320x240:r=5", "-ss", f"{a:.2f}",
              "-t", f"{b - a:.2f}", "-i", vocals, "-shortest", "-c:v", "libx264", "-c:a", "aac", clip])
        try:
            with sources.gemini_file(clip) as (g, part):
                r = None
                for _ in range(3):                     # Gemini sometimes leaves a trailing comma
                    r = g._generate_content([part, {"text": prompt}], max_tokens=4000, timeout=180, temperature=0.4)
                    if isinstance(r, dict) and isinstance(r.get("phrases"), list):
                        break
        finally:
            os.remove(clip)
    out = []
    for x in (r or {}).get("phrases") or [] if isinstance(r, dict) else []:
        try:
            t = float(x["a"])
        except (KeyError, TypeError, ValueError):
            continue
        texts = {l: " ".join(str(x.get(l) or "").split()) for l in langs}
        if 0 <= t < b - a and all(texts.values()):
            out.append({"a": round(a + t, 2), **texts})
    return sorted(out, key=lambda x: x["a"])


# ---------------------------------------------------------------- his lines read by the chosen voice

MODEL = "eleven_v4"
MAX_TEMPO = 1.2                              # a line that runs over the next one is sped up this much at most


def speak(text: str, voice_id: str, lang: str, out: str) -> str:
    """One line read with Eleven v4, its emotion tags played (kept: an unchanged line is never paid twice)."""
    import requests
    if os.path.exists(out):
        return out
    r = requests.post(f"{el.API}/v1/text-to-speech/{voice_id}", headers={"xi-api-key": el._key()}, timeout=120,
                      params={"output_format": "mp3_44100_128"},
                      json={"text": text, "model_id": MODEL, "language_code": lang.split("-")[0],
                            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}})
    if r.status_code != 200:
        raise VoixError(f"ElevenLabs HTTP {r.status_code} : {r.text[:300]}")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        f.write(r.content)
    return out


def duration(path: str) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def mean_db(path: str, a: Optional[float] = None, b: Optional[float] = None) -> float:
    cut = ["-ss", f"{a:.2f}", "-t", f"{b - a:.2f}"] if a is not None and b is not None else []
    r = subprocess.run(["ffmpeg", "-nostdin", *cut, "-i", path, "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"mean_volume: (-?[\d.]+|-inf) dB", r.stderr)
    return -91.0 if not m or m.group(1) == "-inf" else float(m.group(1))


def _chunks(text: str, a: float, b: float) -> List[Dict]:
    """A line shown five words at a time over its span (time shared by length)."""
    words = sans_balises(text).split()
    parts = [" ".join(words[i:i + 5]) for i in range(0, len(words), 5)]
    total, t, out = sum(len(x) for x in parts) or 1, a, []
    for x in parts:
        end = t + (b - a) * len(x) / total
        out.append({"a": round(t, 3), "b": round(end, 3), "texte": x})
        t = end
    return out


def track(lines: List[Dict], lang: str, voice_id: str, a: float, b: float, work: str, ref_db: float):
    """His lines [{"a": seconds of the passage, "texte"}] read by the voice, from a (the moment's start) to b — each
    at its place, never over the one before, at his voice's level. Returns (wav, the captions in passage seconds)."""
    import hashlib
    placed, end, spans = [], a, []
    for k, l in enumerate(lines):
        mp3 = speak(l["texte"], voice_id, lang, os.path.join(
            work, f"{voice_id[:8]}_{lang}_{hashlib.sha1(l['texte'].encode()).hexdigest()[:12]}.mp3"))
        start = max(l["a"], end)
        slot = (lines[k + 1]["a"] if k + 1 < len(lines) else b) - start
        d = duration(mp3)
        tempo = min(MAX_TEMPO, max(1.0, d / max(0.3, slot)))
        placed.append((mp3, start - a, tempo))
        end = start + d / tempo
        spans += _chunks(l["texte"], start, end)
    total = max(b - a, end - a + 0.2)
    key = hashlib.sha1(repr((placed, ref_db)).encode()).hexdigest()[:12]
    out = os.path.join(work, f"piste_{voice_id[:8]}_{lang}_{key}.wav")
    if not os.path.exists(out):
        raw = out + ".brut.wav"
        cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
        for mp3, _, _ in placed:
            cmd += ["-i", mp3]
        f = "".join(f"[{i + 1}:a]aresample=44100,atempo={t:.3f},adelay={int(s * 1000)}:all=1[v{i}];" for i, (_, s, t) in enumerate(placed))
        f += "[0:a]" + "".join(f"[v{i}]" for i in range(len(placed))) + f"amix=inputs={len(placed) + 1}:normalize=0:duration=first[o]"
        _run(cmd + ["-filter_complex", f, "-map", "[o]", raw])
        gain = max(-20.0, min(15.0, ref_db - mean_db(raw)))
        _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", raw, "-af", f"volume={gain:.1f}dB,alimiter=limit=0.89:level=false", out])
        os.remove(raw)
    return out, spans


def passage_audio(src: str, reste: Optional[str], voices: List, out: str) -> str:
    """The passage with its picture untouched and a new sound: the game's sounds without his voice (or silence when
    the channel's music replaces them) and each [(voice track, from)] at its place."""
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", src]
    if reste:
        cmd += ["-i", reste]
    else:
        cmd += ["-f", "lavfi", "-t", f"{duration(src):.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
    f, mix = "[1:a]aresample=44100[r];", ["[r]"]
    for k, (path, at) in enumerate(voices):
        cmd += ["-i", path]
        f += f"[{k + 2}:a]aresample=44100,adelay={int(at * 1000)}:all=1[v{k}];"
        mix.append(f"[v{k}]")
    f += "".join(mix) + f"amix=inputs={len(mix)}:normalize=0:duration=first,alimiter=limit=0.89:level=false[m]"
    tmp = out + ".part.mp4"
    _run(cmd + ["-filter_complex", f, "-map", "0:v", "-map", "[m]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", tmp])
    os.replace(tmp, out)
    return out
