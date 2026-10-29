"""
The voices of the Roblox Shorts, chosen by ear in the lab (etude_roblox/voix, 2026-10-29): read with Eleven v4 and
its emotion tags, they replace the player's voice and tell the story. Donny (French) and Tyler (English) were the
best; Marcus was rejected. Each has a sample to listen to before choosing: the lab's own recording of the same
POV (assets/roblox_voix/<id>_<lang>.mp3), else ElevenLabs' free preview, kept with the voice library's.
"""

import os
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
