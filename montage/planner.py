"""
Gemini decides the edit; this module only asks and parses.

Gemini watches the raw clip (image + audio) with the Whisper word list and
answers in WORD INDICES (black screen, drones, punchline), so every cut lands
between two words. Durations, order and limits are enforced later by
render.resolve_plan — whatever comes back here is a proposal.
"""

import os
import subprocess
from typing import Dict, List, Optional

from montage.transcribe import Words

PLAN_PROMPT = """Tu es monteur de YouTube Shorts. Tu dois remonter cette video brute
selon une recette precise, tiree d'un createur qu'on veut imiter.

LA RECETTE (10 a 30 s au total) :
1. Plan sur la personne : mise en place.
2. ECRAN NOIR 1 a 3 s : l'image disparait, la VOIX CONTINUE, seuls les sous-titres restent.
3. Retour sur la personne.
4. DEUX PLANS DE DRONE (paysages sans rapport) a la suite, 2 a 4 s au total, JUSTE AVANT la chute.
   La voix continue dessous. Ca cree une fausse tension.
5. La CHUTE, toujours sur l'image d'origine, jusqu'a la fin.
Le son d'origine n'est jamais coupe a l'interieur d'un passage garde.

REGLE D'OR : l'ecran noir et les drones CACHENT l'image. Ne les place QUE sur des
mots ou l'image n'apporte rien (quelqu'un explique, pose une question, raconte).
JAMAIS sur une reaction, une grimace, une action visuelle drole.

Voici les mots prononces (index: mot [debut-fin en s]) :
{words}

Duree totale de la video : {duration:.1f} s.

Reponds en JSON uniquement :
{{
  "humour_porte_par": "parole | image | les deux",
  "resume": "ce qui se passe et ou est le drole",
  "garder": [{{"debut_s": nombre, "fin_s": nombre}}],
  "chute_mot": index du premier mot de la chute (ou null si la chute est visuelle),
  "chute_s": instant ou commence la chute (secondes, video d'origine),
  "noir": {{"debut_mot": index, "fin_mot": index}} ou null,
  "drones": {{"debut_mot": index, "fin_mot": index}} ou null,
  "accroches": ["3 titres courts DIFFERENTS en anglais pour le haut de l'ecran, 7 mots max chacun, emoji 😂 a la fin seulement si c'est drole"],
  "texte_incruste": [{{"debut_s": nombre, "fin_s": nombre, "texte": "texte deja grave dans la video d'origine"}}],
  "risques": "ce qui pourrait rater dans ce montage"
}}

Pour "garder" : 1 a 3 passages (dans l'ordre) qui forment une histoire complete de
12 a 30 s, avec la mise en place et la chute. Garde la reaction apres la chute
(rire, silence) 1 a 2 s. Si la video fait deja moins de 30 s, garde-la presque entiere.
Un passage peut commencer/finir entre les mots (silence, action sans parole).
"""

KEYWORDS_PROMPT = """Voici la transcription d'un Short, mot par mot (index: mot).
Dans les sous-titres, certains mots seront mis en valeur (jaune, italique) comme le
ferait un bon monteur : les mots qui portent le sens ou la blague (noms, chiffres,
mots forts, mot-cle de la chute). Pas les petits mots (the, a, to, is, I, you...).
Environ 1 mot sur 5, jamais deux phrases de suite sans accent, et un groupe de 2 mots
max a la suite (ex. "credit card").
{words}
JSON uniquement : {{"mots_cles": [index, ...]}}"""


class PlanError(RuntimeError):
    pass


def _gemini():
    from gemini_ai_generator import GeminiAIGenerator
    return GeminiAIGenerator(api_key=os.getenv("GEMINI_API_KEY"))


def video_duration(path: str) -> float:
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]))


def plan_video(video_path: str, words: Words, gemini=None) -> Dict:
    """Gemini's edit proposal for one clip. Raises PlanError when there is no
    speech to edit on, or when Gemini can't be reached / answers garbage."""
    if not words:
        raise PlanError("Aucune parole détectée : ce montage s'appuie sur ce qui est dit.")
    g = gemini or _gemini()
    listing = "\n".join(f"{i}: {w} [{a:.2f}-{b:.2f}]" for i, (w, a, b) in enumerate(words))
    uploaded = g._upload_video_file(video_path)
    if not uploaded:
        raise PlanError("Envoi de la vidéo à Gemini impossible.")
    try:
        if not g._wait_for_file_active(uploaded["name"], timeout=180):
            raise PlanError("Gemini n'a pas fini de lire la vidéo à temps.")
        parts = [{"file_data": {"mime_type": uploaded["mime_type"], "file_uri": uploaded["uri"]}},
                 {"text": PLAN_PROMPT.format(words=listing, duration=video_duration(video_path))}]
        # a big budget: the model thinks before answering, and a short one
        # truncated the JSON mid-way
        plan = g._generate_content(parts, max_tokens=16000, timeout=180, temperature=0.3)
    finally:
        g._delete_file(uploaded["name"])
    if not isinstance(plan, dict) or "error" in plan or plan.get("parsing_error"):
        raise PlanError(f"Réponse de Gemini inutilisable : {str(plan)[:200]}")
    hooks = [h.strip() for h in plan.get("accroches") or [] if isinstance(h, str) and h.strip()]
    plan["accroches"] = hooks[:3]
    return plan


def pick_keywords(words: Words, gemini=None) -> List[int]:
    """Word indices to draw in the accent style. Best effort: [] on failure,
    the captions then simply stay all white."""
    if not words:
        return []
    listing = " ".join(f"{i}:{w}" for i, (w, a, b) in enumerate(words))
    try:
        r = (gemini or _gemini())._generate_content(
            [{"text": KEYWORDS_PROMPT.format(words=listing)}], max_tokens=8000, timeout=120, temperature=0.2)
        return sorted({int(i) for i in r.get("mots_cles", []) if 0 <= int(i) < len(words)})
    except Exception:
        return []


def unsuitable_reason(plan: Dict) -> Optional[str]:
    """Why this clip is a poor fit for the recipe, or None. The joke being in
    the IMAGE means the black screen and drones would hide it."""
    if plan.get("humour_porte_par") == "image":
        return "L'humour est porté par l'image : l'écran noir et les drones risquent de cacher le moment drôle."
    if not plan.get("noir") and not plan.get("drones"):
        return "Gemini n'a trouvé aucun passage où cacher l'image."
    return None
