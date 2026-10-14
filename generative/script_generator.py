#!/usr/bin/env python3
"""
Script Generator - writes one new "loi de l'attraction" script (+ title,
description, tags) in a channel's style, using the same Gemini-first /
OpenAI-fallback cascade as ai_tags_generator.py, but as a text-only call
(no video/images involved, since there's no video yet at this stage).
"""

import os
from typing import Dict, List, Optional

from dotenv import load_dotenv
load_dotenv()

from gemini_ai_generator import GeminiAIGenerator
from openai_ai_generator import OpenAIGenerator

# Reference scripts (style only — topic/wording must NOT be reused) covering
# the three formats this channel already publishes manually: D (educational
# list), A (short affirmations), B (storytime).
STYLE_EXAMPLES: List[str] = [
    '[curious] 3 signes que l\'univers essaie de te manifester quelque chose : <break time="0.8s" />\n\n'
    '[calm] 1. Tu vois le même chiffre partout, 11h11, 22h22... <break time="0.5s" />\n'
    '2. Une idée te vient sans effort, comme une évidence. <break time="0.5s" />\n'
    '3. Une coïncidence tellement précise que ça ne peut pas être un hasard.\n\n'
    '[warm, excited] Lequel tu as déjà vécu ? Dis-le en commentaire !',

    '[softly] Ferme les yeux, respire doucement... <break time="1.0s" />\n\n'
    '[calm, warm] Aujourd\'hui, je choisis d\'attirer l\'abondance dans ma vie. <break time="0.6s" />\n'
    'Je mérite le succès, <break time="0.4s" /> et chaque effort que je fais me rapproche de ma meilleure version. <break time="0.6s" />\n\n'
    '[confident] L\'univers travaille en ma faveur.',

    '[curious] J\'ai testé la méthode SATS de Neville Goddard pendant 7 jours, voici ce qui s\'est passé. <break time="0.8s" />\n\n'
    '[calm] Jour 1 : je visualise avant de dormir, comme si c\'était déjà réel. <break time="0.6s" />\n'
    'Jour 3 : je remarque que je pense moins au "comment", et plus au "quand". <break time="0.6s" />\n'
    'Jour 5 : une coïncidence troublante se produit, liée exactement à ce que je visualisais. <break time="0.6s" />\n'
    'Jour 7 : <break time="0.4s" /> [warm] je ne dirais pas que tout a changé... mais quelque chose, oui.',

    '[confident] La loi de l\'assomption expliquée en 30 secondes. <break time="0.6s" />\n\n'
    '[calm] Un : agis comme si ton souhait était déjà réalisé. <break time="0.5s" />\n'
    'Deux : ne cherche pas le "comment", laisse l\'univers s\'en charger. <break time="0.5s" />\n'
    'Trois : ressens l\'émotion du résultat, maintenant, pas plus tard.\n\n'
    '[warm] C\'est aussi simple, et aussi difficile, que ça.',

    '[calm, warm] Je suis capable. <break time="0.6s" />\n'
    'Je n\'ai pas besoin de l\'approbation des autres pour avancer. <break time="0.6s" />\n\n'
    '[confident] Ma valeur ne dépend de personne d\'autre que moi.',

    '[curious] Personne ne parle de ce détail dans la manifestation. <break time="0.8s" />\n\n'
    '[calm] Tout le monde répète "pense positif et ça arrive". <break time="0.6s" />\n'
    'Mais la vérité, c\'est que la manifestation ne marche jamais sans une action alignée derrière. <break time="0.6s" />\n\n'
    '[warm, confident] Visualiser, c\'est la moitié du travail. L\'autre moitié, c\'est bouger.',
]


def _build_prompt(
    channel_profile: Dict, style_examples: List[str],
    recent_titles: Optional[List[str]] = None, recent_formats: Optional[List[str]] = None,
    inspiration: Optional[Dict] = None,
) -> str:
    style_prompt = channel_profile.get("script_style_prompt", "")
    examples_block = "\n\n---\n\n".join(style_examples)

    history_block = ""
    if recent_titles:
        titles_list = "\n".join(f"- {t}" for t in recent_titles)
        history_block = f"""

Sujets/angles DÉJÀ traités récemment sur cette chaîne — n'en refais AUCUN, ni le même angle
reformulé différemment (ex: ne refais pas "3 signes que X" si la liste ci-dessous en contient déjà
plusieurs, ne refais pas "j'ai testé X pendant Nh" si déjà présent) :
{titles_list}"""
        if recent_formats and not inspiration:
            counts = {f: recent_formats.count(f) for f in ("A", "B", "D")}
            least_used = min(counts, key=counts.get)
            history_block += (
                f"\n\nFormats récemment utilisés (A/B/D) : {', '.join(recent_formats)}. "
                f"Le format \"{least_used}\" est sous-représenté — privilégie-le cette fois, "
                f"sauf si un autre format sert clairement mieux le nouvel angle choisi."
            )

    inspiration_block = ""
    if inspiration and not inspiration.get("script_text"):
        fmt = inspiration.get("format") or ""
        inspiration_block = f"""

Le format "{fmt}" est celui qui marche le mieux sur cette chaîne : écris ce script dans ce format,
sur un sujet neuf. Indique "{fmt}" dans le champ "format"."""
    elif inspiration:
        fmt = inspiration.get("format") or ""
        inspiration_block = f"""

Cette vidéo de la chaîne a TRÈS BIEN marché — c'est le modèle à suivre :
Titre : {inspiration.get("title") or ""}
Format : {fmt}
Script :
{inspiration.get("script_text") or ""}

Écris un NOUVEAU script qui reprend ce qui la fait marcher : même format ("{fmt}"), même structure,
même type d'accroche dans la première phrase, même rythme et même longueur approximative.
Mais le SUJET doit être différent (ni le même thème reformulé, ni les mêmes phrases), et le titre aussi.
Indique "{fmt}" dans le champ "format"."""

    return f"""{style_prompt}

Voici des exemples de scripts déjà publiés sur cette chaîne, à titre de référence de STYLE UNIQUEMENT
(ton, rythme, tags de délivrance ElevenLabs, longueur) — n'en copie ni le sujet ni le texte,
écris un script sur un sujet neuf :

---
{examples_block}
---
{history_block}{inspiration_block}

Réponds UNIQUEMENT avec un objet JSON valide de cette forme exacte, rien d'autre avant ou après :
{{
  "script_text": "le script complet en français, avec les tags [emotion] et <break time=\\"Xs\\" /> inline",
  "format": "A ou B ou D",
  "title": "titre YouTube accrocheur en français, sans hashtags, moins de 100 caractères",
  "description": "description YouTube en français (2-4 phrases + quelques hashtags pertinents)",
  "tags": ["tag1", "tag2", "tag3"]
}}"""


def _is_usable(result: Dict) -> bool:
    return (
        isinstance(result, dict)
        and isinstance(result.get("script_text"), str) and result["script_text"].strip()
        and isinstance(result.get("title"), str) and result["title"].strip()
        and isinstance(result.get("tags"), list)
    )


SCRIPT_TEMPERATURE = 0.95  # higher than the app's shared 0.7 default — this call
                            # is pure creative writing, not extraction/analysis,
                            # and needs more spread across topics/wording to
                            # actually vary run to run, on top of the recent-
                            # topics list telling it what NOT to repeat.


def generate_script(
    channel_profile: Dict, style_examples: Optional[List[str]] = None,
    recent_titles: Optional[List[str]] = None, recent_formats: Optional[List[str]] = None,
    inspiration: Optional[Dict] = None,
) -> Dict:
    """Generate one new script + title/description/tags in the channel's style.

    recent_titles/recent_formats (this channel's own generation history) are
    threaded into the prompt so the model has something concrete to diverge
    from, instead of just a vague "be original" instruction repeated
    identically on every call — without them, the same fixed style examples
    on every call made outputs converge to the same handful of angles.

    Tries Gemini first (free tier), falls back to OpenAI — same provider
    order as ai_tags_generator.AITagsGenerator.generate_ai_content, but
    calling call_gemini_api/call_openai_api directly with images=None since
    there is no video to analyze yet at this stage.
    """
    prompt = _build_prompt(channel_profile, style_examples or STYLE_EXAMPLES, recent_titles, recent_formats, inspiration)

    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        try:
            result = GeminiAIGenerator(gemini_key).call_gemini_api(prompt, max_tokens=3500, temperature=SCRIPT_TEMPERATURE)
            if _is_usable(result):
                return result
            print(f"⚠️ Gemini script generation returned an unusable result: {result}")
        except Exception as e:
            print(f"⚠️ Gemini script generation failed: {e}")

    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        try:
            result = OpenAIGenerator(openai_key).call_openai_api(prompt, max_tokens=3500, temperature=SCRIPT_TEMPERATURE)
            if _is_usable(result):
                return result
            print(f"⚠️ OpenAI script generation returned an unusable result: {result}")
        except Exception as e:
            print(f"⚠️ OpenAI script generation failed: {e}")

    raise RuntimeError(
        "Script generation failed: no AI provider produced a usable script "
        "(check GEMINI_API_KEY / OPENAI_API_KEY)."
    )
