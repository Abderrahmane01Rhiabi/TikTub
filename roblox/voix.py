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
