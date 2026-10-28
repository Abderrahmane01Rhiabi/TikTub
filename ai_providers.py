#!/usr/bin/env python3
"""
The steps that only write text may be given to another provider than Gemini
(Réglages → Modèles d'IA, ai_models.choices). Both speak the OpenAI format:
the SAME prompt text is sent as one user message, in JSON mode, and the answer
is read like Gemini's. Any failure (no key, an error, a limit, unreadable JSON)
gives None and a reason: gemini_ai_generator then asks the step's own Gemini
model. Each call is logged in the same usage log, priced in ai_models.

Measured before offering it (RESULTATS_MODELES.md, 2026-10-28): DeepSeek Flash
thinks before answering (billed as output), so its answers need room.
"""

import json
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests

import ai_models

# provider: (url, the most it may answer)
ENDPOINTS = {
    "deepseek": ("https://api.deepseek.com/chat/completions", 24000),
    "openai": ("https://api.openai.com/v1/chat/completions", 16000),
}


def read_json(content: str) -> Optional[Dict]:
    """The answer as JSON, like gemini_ai_generator reads Gemini's: the whole text, else its first {...}."""
    try:
        r = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        m = re.search(r"\{.*\}", content or "", re.DOTALL)
        try:
            r = json.loads(m.group(0)) if m else None
        except json.JSONDecodeError:
            r = None
    return r if isinstance(r, (dict, list)) else None


def _log(model: str, step: str, status: int, seconds: float, usage: Dict, **extra) -> None:
    import gemini_ai_generator as gg
    details = usage.get("completion_tokens_details") or {}
    thoughts = details.get("reasoning_tokens", 0) or 0
    prompt = usage.get("prompt_tokens", 0) or 0
    gg.write_usage({"at": datetime.now().isoformat(timespec="seconds"), "model": model, "step": step, "status": status,
                    "s": round(seconds, 1), "prompt": prompt, "output": (usage.get("completion_tokens", 0) or 0) - thoughts,
                    "thoughts": thoughts, "total": usage.get("total_tokens", 0) or 0, "by_kind": {"TEXT": prompt},
                    "cached": usage.get("prompt_cache_hit_tokens") or (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0,
                    "projet": gg.USAGE_CONTEXT.get().get("projet"), **extra})


def ask(model: str, step: str, parts: List[Dict], max_tokens: int, timeout: int,
        temperature: float) -> Tuple[Optional[Dict], Optional[str]]:
    """(answer, None) from the chosen provider, or (None, why it can't) — then Gemini answers."""
    if any(not isinstance(p, dict) or set(p) != {"text"} for p in parts):
        return None, "étape avec image ou vidéo"
    if not ai_models.accepts(step, model):
        return None, "modèle non compatible avec cette étape"
    key = ai_models.key_of(model)
    if not key:
        return None, f"clé {ai_models.MODELS[model]['cle']} absente"
    provider = ai_models.provider_of(model)
    url, most = ENDPOINTS[provider]
    extra = {"tarif": "plein"} if provider == "deepseek" and ai_models.deepseek_peak() else {}
    body = {"model": model, "messages": [{"role": "user", "content": "\n".join(p["text"] for p in parts)}],
            "temperature": temperature, "max_tokens": min(max(max_tokens, 4000), most),   # its thinking needs room
            "response_format": {"type": "json_object"}}
    t0 = time.time()
    try:
        r = requests.post(url, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=max(timeout, 90))
    except requests.RequestException as e:
        _log(model, step, 0, time.time() - t0, {}, erreur=str(e)[:200], **extra)
        return None, "pas de réponse"
    try:
        data = r.json()
    except ValueError:
        data = {}
    _log(model, step, r.status_code, time.time() - t0, data.get("usage") or {}, **extra)
    if r.status_code != 200:
        return None, "limite atteinte" if r.status_code == 429 else f"erreur {r.status_code}"
    try:
        content = data["choices"][0]["message"].get("content") or ""
    except (KeyError, IndexError, TypeError):
        return None, "réponse vide"
    answer = read_json(content)
    if answer is None:
        return None, "réponse illisible (pas du JSON)"
    return answer, None
