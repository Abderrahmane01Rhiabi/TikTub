"""
The subject's tone, and what it changes in the montage.

One montage for every subject sounded wrong: a "boom" on a burning cactus, the
same music for a calm aquarium and a parkour jump. The reference analysis now
says the Short's tone (no extra call); a project analysed before gets it from
one short text call, once. The person can change it.

    calme          satisfying, soothing, nature: few effects, no whoosh
    explicatif     a fact explained (the default — the montage as it was)
    spectaculaire  danger, speed, impact: the slow motions on the strong moments
    drole          absurd, funny: a freeze frame on the gag

"explicatif" keeps every limit as it was before the tone existed.
"""

import os
from typing import Dict, List, Optional

DEFAULT = "explicatif"

TONES: Dict[str, Dict] = {
    "calme": {
        "label": "Calme / satisfaisant",
        "musique": "douce, posee, sans percussion forte",
        "effets": {"ralenti": 1, "zoom": 2, "arret": 0, "transition": 1, "chiffre": 1},
        "sons": {"max": 1, "types": {"pop", "shutter"}},
    },
    "explicatif": {
        "label": "Explicatif",
        "musique": "neutre, curieuse, qui laisse la place a la voix",
        "effets": {"ralenti": 2, "zoom": 3, "arret": 1, "transition": 3, "chiffre": 2},
        "sons": {"max": 4, "types": None},
    },
    "spectaculaire": {
        "label": "Spectaculaire",
        "musique": "tendue, energique, avec du rythme",
        "effets": {"ralenti": 3, "zoom": 3, "arret": 1, "transition": 3, "chiffre": 2},
        "sons": {"max": 4, "types": None},
    },
    "drole": {
        "label": "Drôle",
        "musique": "legere, bondissante, decalee",
        "effets": {"ralenti": 2, "zoom": 3, "arret": 2, "transition": 2, "chiffre": 1},
        "sons": {"max": 4, "types": None},
    },
}

# Every Short we adapt explains something: asked "its tone", the AI answered "explicatif" for 11 of 13 (parkour
# down skyscrapers included). The tone is the mood of its PICTURES and story, the explaining aside.
TONE_RULE = ("le ton dit l'AMBIANCE des images et de l'histoire (ces Shorts expliquent tous quelque chose : ce n'est pas "
             "le critere) : spectaculaire = danger, vitesse, hauteur, choc, feu, explosion, exploit ; calme = images "
             "apaisantes ou satisfaisantes (nettoyage, nature, artisanat lent, animaux paisibles, eau) ; drole = absurde, "
             "gag, situation ridicule ; explicatif = seulement si rien de tout cela (un objet ou un procede neutre)")

GUESS_PROMPT = """Quel est le ton de ce YouTube Short ? Un seul mot parmi : spectaculaire, calme, drole, explicatif.
Regle : """ + TONE_RULE + """.
Sujet : {sujet}
Texte dit : {texte}
JSON uniquement : {{"ton": "..."}}"""


def valid(t: Optional[str]) -> Optional[str]:
    t = (t or "").strip().lower().replace("ô", "o").replace("é", "e")
    return t if t in TONES else None


def of(ref: Optional[Dict]) -> str:
    """The tone set on the reference (by the analysis or by hand), else the default."""
    return valid((ref or {}).get("ton")) or DEFAULT


def guess(ref: Dict, gemini=None) -> str:
    """A project analysed before the tone existed: one short text call, from what the analysis kept."""
    if valid(ref.get("ton")):
        return ref["ton"]
    try:
        if gemini is None:
            from gemini_ai_generator import GeminiAIGenerator
            gemini = GeminiAIGenerator(api_key=os.getenv("GEMINI_API_KEY"))
        r = gemini._generate_content([{"text": GUESS_PROMPT.format(
            sujet=ref.get("sujet") or "", texte=" ".join(str(ref.get("script_complet") or "").split())[:900])}],
            max_tokens=200, timeout=40, temperature=0.1, thinking=0)
        return valid((r or {}).get("ton")) or DEFAULT
    except Exception:
        return DEFAULT


def effect_limits(tone: str) -> Dict[str, int]:
    return dict(TONES[valid(tone) or DEFAULT]["effets"])


def sound_rules(tone: str) -> Dict:
    return dict(TONES[valid(tone) or DEFAULT]["sons"])


def music_hint(tone: str) -> str:
    t = valid(tone) or DEFAULT
    return f"{TONES[t]['label']} : musique {TONES[t]['musique']}"


def choices() -> List[Dict]:
    return [{"ton": k, "label": v["label"]} for k, v in TONES.items()]
