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


def _build_prompt(channel_profile: Dict, style_examples: List[str]) -> str:
    style_prompt = channel_profile.get("script_style_prompt", "")
    examples_block = "\n\n---\n\n".join(style_examples)
    return f"""{style_prompt}

Voici des exemples de scripts déjà publiés sur cette chaîne, à titre de référence de STYLE UNIQUEMENT
(ton, rythme, tags de délivrance ElevenLabs, longueur) — n'en copie ni le sujet ni le texte,
écris un script sur un sujet neuf :

---
{examples_block}
---

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


def generate_script(channel_profile: Dict, style_examples: Optional[List[str]] = None) -> Dict:
    """Generate one new script + title/description/tags in the channel's style.

    Tries Gemini first (free tier), falls back to OpenAI — same provider
    order as ai_tags_generator.AITagsGenerator.generate_ai_content, but
    calling call_gemini_api/call_openai_api directly with images=None since
    there is no video to analyze yet at this stage.
    """
    prompt = _build_prompt(channel_profile, style_examples or STYLE_EXAMPLES)

    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        try:
            result = GeminiAIGenerator(gemini_key).call_gemini_api(prompt, max_tokens=3500)
            if _is_usable(result):
                return result
            print(f"⚠️ Gemini script generation returned an unusable result: {result}")
        except Exception as e:
            print(f"⚠️ Gemini script generation failed: {e}")

    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        try:
            result = OpenAIGenerator(openai_key).call_openai_api(prompt, max_tokens=3500)
            if _is_usable(result):
                return result
            print(f"⚠️ OpenAI script generation returned an unusable result: {result}")
        except Exception as e:
            print(f"⚠️ OpenAI script generation failed: {e}")

    raise RuntimeError(
        "Script generation failed: no AI provider produced a usable script "
        "(check GEMINI_API_KEY / OPENAI_API_KEY)."
    )
