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

from generative import script_plan


def _build_prompt(
    channel_profile: Dict, plan: Dict, recent_titles: Optional[List[str]] = None,
    inspiration: Optional[Dict] = None, feedback: Optional[List[str]] = None,
    examples: Optional[List[str]] = None,
) -> str:
    """The prompt for one script written inside `plan` (script_plan.choose):
    the channel's general style, the plan (which wins over it), two examples
    for the tone only, what was done lately, and — on a retry — why the
    previous attempt was refused."""
    style_prompt = channel_profile.get("script_style_prompt", "")
    audience = channel_profile.get("script_audience")
    audience_block = f"\nPublic de la chaîne : {audience}. Parle à ces personnes-là, de leur vie à elles.\n" if audience else ""
    examples_block = "\n\n---\n\n".join(examples or script_plan.examples(plan))
    fmt = plan["format"]

    history_block = ""
    if recent_titles:
        titles_list = "\n".join(f"- {t}" for t in recent_titles)
        history_block = f"""

Titres DÉJÀ publiés récemment sur cette chaîne — n'en refais AUCUN, ni le même angle reformulé,
ni le même schéma de titre :
{titles_list}"""
        banned = script_plan.overused_openings(recent_titles)
        if banned:
            history_block += "\n\nN'ouvre PAS le titre par : " + ", ".join(f"« {b} »" for b in banned) + "."

    inspiration_block = ""
    if inspiration and inspiration.get("script_text"):
        inspiration_block = f"""

Cette vidéo de la chaîne a TRÈS BIEN marché :
Titre : {inspiration.get("title") or ""}
Script :
{inspiration.get("script_text") or ""}

Reprends ce qui l'a fait marcher — la FORCE de son accroche, son rythme, sa durée — mais PAS sa
structure, PAS son schéma de titre (si elle commence par « 3 signes... », le tien ne commence pas
pareil), PAS son sujet. YouTube cesse de montrer une chaîne qui publie des copies d'une même vidéo."""

    feedback_block = ""
    if feedback:
        feedback_block = "\n\nTON ESSAI PRÉCÉDENT A ÉTÉ REFUSÉ :\n" + "\n".join(f"- {f}" for f in feedback) + \
                         "\nÉcris quelque chose de vraiment différent."

    return f"""{style_prompt}
{audience_block}
LE PLAN DE CE SCRIPT (il prime sur la description générale ci-dessus, formats compris) :
{script_plan.describe(plan)}

Règles :
- Jamais de faux témoignage à la première personne (« j'ai testé », « j'ai essayé », « j'ai arrêté... pendant
  72h ») : la voix est synthétique, l'expérience n'aurait pas eu lieu. Ça trompe le spectateur.
- Le titre suit le format et l'accroche du plan, pas les habitudes de la chaîne.
- Tutoie toujours le spectateur, comme dans les exemples (jamais « vous »).
- Phrases courtes, à l'oral, avec les tags ElevenLabs v3 ([calm], [curious], [warm], [softly], [confident]...)
  avant la phrase concernée et des pauses <break time="0.6s" /> entre les temps forts.

Exemples, pour le TON et les TAGS uniquement (n'en copie ni le sujet, ni les phrases, ni la structure) :

---
{examples_block}
---
{history_block}{inspiration_block}{feedback_block}

Réponds UNIQUEMENT avec un objet JSON valide de cette forme exacte, rien d'autre avant ou après :
{{
  "script_text": "le script complet en français, avec les tags [emotion] et <break time=\\"Xs\\" /> inline",
  "format": "{fmt}",
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
    channel_profile: Dict, plan: Dict, recent_titles: Optional[List[str]] = None,
    inspiration: Optional[Dict] = None, feedback: Optional[List[str]] = None,
) -> Dict:
    """Generate one new script + title/description/tags inside `plan`
    (format, topic, hook, ending — script_plan.choose). recent_titles: this
    channel's latest titles, to diverge from; feedback: why a previous
    attempt was refused (too close to a published video...).

    Tries Gemini first (free tier), falls back to OpenAI — same provider
    order as ai_tags_generator.AITagsGenerator.generate_ai_content, but
    calling call_gemini_api/call_openai_api directly with images=None since
    there is no video to analyze yet at this stage.
    """
    prompt = _build_prompt(channel_profile, plan, recent_titles, inspiration, feedback)
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
