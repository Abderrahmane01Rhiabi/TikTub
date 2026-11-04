#!/usr/bin/env python3
"""
Which AI model does each step — in one table — and what it costs.

Every call to Gemini goes through GeminiAIGenerator._generate_content; there,
the step asking (module.function, as the usage log names it) gets its model
from STEPS. Changing a step's model is one line here, or, without touching
the code, an entry in database/ai_models.json: {"finder._watch": "<model>"}.

A step not listed uses the generator's own model (gemini-flash-latest).
A step that only sends text may also be given to DeepSeek or OpenAI
(Réglages → Modèles d'IA); when that model fails, the step's own Gemini
model answers instead (gemini_ai_generator, ai_providers).
Measured 2026-10-22/23 (see ADAPTATION_BILAN.md): Flash-Lite and 3 Flash
Preview judged videos worse; the two re-reads stay on Pro (the Arabic
endings slipped past Flash twice).

Prices: dollars per million tokens, as Google bills them (the thinking is
billed as output), with the date each price starts — gemini-flash-latest
(3.8 Flash) doubles on 2027-01-01.
"""

import json
import os
from collections import defaultdict
from datetime import date, datetime
from typing import Dict, List, Optional

FLASH = "gemini-flash-latest"
PRO = "gemini-pro-latest"
DEEPSEEK = "deepseek-flash"
OPENAI = "gpt-4o-mini"          # the model openai_ai_generator already uses as the second choice
OVERRIDES = os.path.join("database", "ai_models.json")

# step: (model, what it does) — every step of the app that asks the AI
STEPS: Dict[str, tuple] = {
    "reference.analyse":     (FLASH, "regarder le Short modèle"),
    "idee.research":         (FLASH, "chercher les faits sur le web (Google), « Idée d'abord »"),
    "idee.plan":             (FLASH, "construire le plan à partir de l'idée"),
    "storyboard.angles":     (FLASH, "proposer les angles (une version par chaîne)"),
    "storyboard.write":      (FLASH, "écrire le storyboard"),
    "storyboard.critique":   (FLASH, "relire le storyboard"),     # Pro before; Flash read as well (TEST_ECONOMIES.md, Y6)
    "storyboard.revise":     (FLASH, "corriger le storyboard"),
    "finder.plan_queries":   (FLASH, "écrire les recherches de chaque plan"),
    "finder.local_queries":  (FLASH, "écrire les recherches dans la langue du pays"),
    "finder.action_queries": (FLASH, "écrire les recherches « par action »"),
    "finder._sort_one":      (FLASH, "trier les résultats de recherche"),
    "finder._watch":         (FLASH, "regarder une vidéo candidate (YouTube)"),
    "finder._send_file":     (FLASH, "regarder une vidéo candidate (fichier)"),
    "sources.retime":        (FLASH, "recaler le moment exact"),
    "sources.retime_and_check": (FLASH, "recaler le moment et contrôler le clip (un seul regard)"),
    "sources.orientation":   (FLASH, "redresser une vidéo tournée"),
    "sources.describe":      (FLASH, "contrôler les clips téléchargés"),
    "sources.find_boxes":    (FLASH, "trouver l'image utile et les logos à effacer"),
    "script.write":          (FLASH, "écrire le script"),
    "script.critique":       (PRO,   "relire le script"),
    "script.revise":         (FLASH, "corriger le script"),
    "script.match":          (FLASH, "juger phrase ↔ image"),
    "effects.decide":        (FLASH, "choisir les effets (ralenti, zoom…)"),
    "effects.auto_zoom":     (FLASH, "mesurer la taille du sujet"),
    "annotate.locate":       (FLASH, "placer les flèches et cercles"),
    "annotate.review":       (FLASH, "revoir les flèches sur les vrais clips"),
    "storyboard.adapt_to":   (FLASH, "réécrire un plan pour une image déjà trouvée"),
    "tone.guess":            (FLASH, "deviner le ton du sujet"),
    "pipeline._choose_music": (FLASH, "choisir la musique"),
    "discours.passages":     (FLASH, "proposer les passages forts d'un discours"),
    "discours.moments":      (FLASH, "proposer les plans d'illustration d'un discours"),
    "discours.translate":    (FLASH, "traduire les sous-titres d'un discours"),
    "script_generator.generate_script": (FLASH, "écrire le script (Génération)"),
    "planner.plan_video":    (FLASH, "regarder le clip et choisir les moments (Montage auto)"),
    "planner.pick_keywords": (FLASH, "choisir les mots à mettre en valeur (Montage auto)"),
    "ai_tags_generator.generate_ai_content": (FLASH, "titre, description et tags d'une vidéo importée"),
    "ai_scheduler._ask_ai_for_slots": (FLASH, "proposer les heures de publication (planning « IA »)"),
}

# the steps that send ONLY text (no video, picture, YouTube link or Google search): the only ones another
# provider may serve. Anything else stays on Gemini, whatever database/ai_models.json says.
TEXT_ONLY = {"idee.plan", "storyboard.angles", "storyboard.write", "storyboard.critique", "storyboard.revise",
             "storyboard.adapt_to", "finder.plan_queries", "finder.local_queries", "finder.action_queries",
             "finder._sort_one", "script.write", "script.critique", "script.revise", "tone.guess",
             "pipeline._choose_music", "script_generator.generate_script", "planner.pick_keywords",
             "discours.passages", "discours.moments", "discours.translate",
             "ai_scheduler._ask_ai_for_slots"}
GROUNDED = {"idee.research"}            # Google Search: Gemini Flash only

# model: who serves it, its name on screen, the key it needs (in .env)
MODELS: Dict[str, Dict[str, str]] = {
    FLASH: {"fournisseur": "gemini", "nom": "Gemini Flash", "cle": "GEMINI_API_KEY"},
    PRO: {"fournisseur": "gemini", "nom": "Gemini Pro", "cle": "GEMINI_API_KEY"},
    DEEPSEEK: {"fournisseur": "deepseek", "nom": "DeepSeek Flash", "cle": "DEEPSEEK_API_KEY"},
    OPENAI: {"fournisseur": "openai", "nom": "OpenAI GPT-4o mini", "cle": "OPENAI_API_KEY"},
}

# what was measured before offering a choice (TEST_ECONOMIES.md, RELECTURE_SCRIPT_PRO_FLASH.md, RESULTATS_MODELES.md)
TESTED: Dict[tuple, str] = {
    ("storyboard.critique", PRO): "testé : relisait le storyboard avant le 28/10",
    ("script.critique", FLASH): "testé sur 2 scripts (FR, AR) : à lire dans RELECTURE_SCRIPT_PRO_FLASH.md",
    ("storyboard.write", DEEPSEEK): "testé sur 5 cas : brouillons parfois trop longs",
    ("storyboard.critique", DEEPSEEK): "testé sur 5 cas : respecte la durée, coupe parfois une explication",
    ("storyboard.revise", DEEPSEEK): "testé sur 5 cas : respecte la durée, coupe parfois une explication",
    ("script_generator.generate_script", DEEPSEEK): "testé sur 5 scripts : le plus vivant ; données stockées en Chine",
}

# the screen's parts (Réglages → Modèles d'IA); every step not listed elsewhere belongs to Adaptation et Idée
PARTS = [("Génération", ["script_generator.generate_script"]),
         ("Import et Montage auto", ["planner.plan_video", "planner.pick_keywords", "ai_tags_generator.generate_ai_content"]),
         ("Planning", ["ai_scheduler._ask_ai_for_slots"])]

TRANSCRIPTION = ["whisper-1", "faster-whisper-small", "faster-whisper-medium"]
TRANSCRIPTION_NOTES = {
    "whisper-1": "OpenAI, payant (0,006 $/min) : utilisé aujourd'hui",
    "faster-whisper-small": "sur ce PC, gratuit : testé en anglais, pas en français ; peu fiable en darija",
    "faster-whisper-medium": "sur ce PC, gratuit mais lent et ≈ 1,5 Go de mémoire pendant les rendus",
}

# step: the most it may think (thinkingBudget), for steps that LOOK rather than write. Measured
# (TEST_ECONOMIES.md, Y1): at 256 the checks agree with the uncapped ones as often as two uncapped runs
# agree with each other, and their thinking (paid as output) falls to 0. A call that sets its own wins.
THINKING: Dict[str, int] = {
    "finder._watch": 256,        # verification of a candidate video (YouTube link)
    "finder._send_file": 256,    # the same verification, for a file sent
    "sources.retime": 256,       # re-timing the moment in a downloaded file
    "sources.retime_and_check": 256,    # the same, with the check of the clips (Y3)
    "sources.find_boxes": 256,   # logos to erase (also the second cleaning pass, leftover_text)
}

# model: [(from date, $ input, $ output, $ cached input)] per million tokens
# (ai.google.dev/gemini-api/docs/pricing, read 2026-10-27: cached input = a tenth of the input price)
PRICES: Dict[str, List[tuple]] = {
    FLASH: [("2000-01-01", 0.75, 3.75, 0.075), ("2027-01-01", 1.50, 7.50, 0.15)],
    PRO: [("2000-01-01", 2.00, 12.00, 0.20)],
    # api-docs.deepseek.com/quick_start/pricing (2026-10-28): off-peak; twice that in its peak hours ("tarif": "plein")
    DEEPSEEK: [("2000-01-01", 0.15, 0.60, 0.003)],
    OPENAI: [("2000-01-01", 0.15, 0.60, 0.075)],
}


def _overrides() -> Dict[str, str]:
    try:
        with open(OVERRIDES, encoding="utf-8") as f:
            data = json.load(f)
        return {str(k): str(v) for k, v in data.items() if v}
    except (OSError, ValueError, AttributeError):
        return {}


def model_for(step: str, fallback: str = FLASH) -> str:
    """The model for this step: database/ai_models.json, then STEPS, then the caller's."""
    return _overrides().get(step) or (STEPS.get(step) or (None,))[0] or fallback


def gemini_default(step: str, fallback: str = FLASH) -> str:
    """The step's own Gemini model (STEPS, never the file): it answers when the chosen model fails."""
    m = (STEPS.get(step) or (None,))[0] or fallback
    return m if provider_of(m) == "gemini" else FLASH


def provider_of(model: str) -> str:
    return (MODELS.get(model) or {}).get("fournisseur", "gemini")


def choices(step: str) -> List[str]:
    """The models this step may use: a step that looks at pictures or videos, or searches Google, stays on Gemini."""
    if step in GROUNDED:
        return [FLASH]
    if step in TEXT_ONLY:
        return [FLASH, PRO, DEEPSEEK, OPENAI]
    return [FLASH, PRO]


def accepts(step: str, model: str) -> bool:
    return model in choices(step)


def _dotenv_key(name: str) -> Optional[str]:
    """A key added to .env while the server runs (os.environ was read at start)."""
    try:
        from dotenv import dotenv_values
        return dotenv_values(".env").get(name) or None
    except Exception:
        return None


def key_of(model: str) -> Optional[str]:
    name = (MODELS.get(model) or {}).get("cle")
    return (os.getenv(name) or _dotenv_key(name)) if name else None


def deepseek_peak(t: Optional[datetime] = None) -> bool:
    """DeepSeek's peak hours (twice the price): 01-04 h and 06-10 h UTC, Monday to Friday."""
    from datetime import timezone
    t = t or datetime.now(timezone.utc)
    return t.weekday() < 5 and (1 <= t.hour < 4 or 6 <= t.hour < 10)


def transcription_model() -> str:
    m = _overrides().get("transcription")
    return m if m in TRANSCRIPTION else TRANSCRIPTION[0]


def _row(model: str, day: str) -> tuple:
    rows = PRICES.get(model) or PRICES[FLASH]
    return next((r for r in reversed(rows) if day >= r[0]), rows[0])


def price(model: str, day: str) -> tuple:
    """($ input, $ output) per million tokens for this model on this day (an unknown model: Flash's)."""
    return _row(model, day)[1:3]


def cost(line: Dict, day: Optional[str] = None) -> float:
    """One logged call's cost in dollars (day: price it at another date): the
    tokens Google served from its cache are billed at the cached-input price."""
    _, i, o, c = _row(line.get("model") or FLASH, day or (line.get("at") or "")[:10])
    cached = min(line.get("cached", 0) or 0, line.get("prompt", 0))
    peak = 2 if line.get("tarif") == "plein" else 1
    return peak * ((line.get("prompt", 0) - cached) * i + cached * c + (line.get("output", 0) + line.get("thoughts", 0)) * o) / 1e6


def month_report(month: Optional[str] = None, path: Optional[str] = None) -> Dict:
    """What the AI cost this month (YYYY-MM): total, per step, and the same calls at January 2027 prices."""
    from gemini_ai_generator import USAGE_LOG
    month = month or date.today().strftime("%Y-%m")
    steps = defaultdict(lambda: {"appels": 0, "cout": 0.0, "modeles": set()})
    total, later, calls, failed = 0.0, 0.0, 0, 0
    try:
        with open(path or USAGE_LOG, encoding="utf-8") as f:
            lines = [json.loads(x) for x in f if x.strip()]
    except (OSError, ValueError):
        lines = []
    for ln in lines:
        if not str(ln.get("at", "")).startswith(month):
            continue
        calls += 1
        if ln.get("status") != 200:
            failed += 1
        c = cost(ln)
        total += c
        later += cost(ln, "2027-01-01")
        s = steps[ln.get("step") or "?"]
        s["appels"] += 1
        s["cout"] += c
        s["modeles"].add(ln.get("model") or "?")
    rows = sorted(({"etape": k, "quoi": (STEPS.get(k) or (None, ""))[1], "appels": v["appels"],
                    "cout": round(v["cout"], 3), "modeles": sorted(v["modeles"]), "modele_actuel": model_for(k)}
                   for k, v in steps.items()), key=lambda r: -r["cout"])
    return {"mois": month, "total": round(total, 2), "appels": calls, "echecs": failed,
            "au_prix_de_janvier": round(later, 2), "par_etape": rows,
            "le": datetime.now().isoformat(timespec="seconds")}


# ------------------------------------------------------------------ Réglages → Modèles d'IA

def _write_overrides(data: Dict[str, str]) -> None:
    os.makedirs(os.path.dirname(OVERRIDES) or ".", exist_ok=True)
    tmp = OVERRIDES + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, OVERRIDES)


def set_choice(step: str, model: str) -> None:
    """The person's choice for a step (or "transcription"); the recommended one removes the entry."""
    data = _overrides()
    if step == "transcription":
        if model not in TRANSCRIPTION:
            raise ValueError(f"Transcription inconnue : {model}")
        default = TRANSCRIPTION[0]
    else:
        if step not in STEPS:
            raise ValueError(f"Étape inconnue : {step}")
        if not accepts(step, model):
            raise ValueError(f"{(MODELS.get(model) or {}).get('nom', model)} ne peut pas faire cette étape "
                             "(elle envoie une image, une vidéo ou cherche sur Google).")
        default = STEPS[step][0]
    if model == default:
        data.pop(step, None)
    else:
        data[step] = model
    _write_overrides(data)


def reset_choices() -> None:
    """Back to the recommended models (those of STEPS)."""
    _write_overrides({})


def costs_by_step(days: int = 30, path: Optional[str] = None) -> Dict[str, tuple]:
    """step: (dollars, calls) over the last days, every provider together."""
    from datetime import timedelta
    from gemini_ai_generator import USAGE_LOG
    since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    out = defaultdict(lambda: [0.0, 0])
    try:
        with open(path or USAGE_LOG, encoding="utf-8") as f:
            for x in f:
                if not x.strip():
                    continue
                ln = json.loads(x)
                if str(ln.get("at", "")) >= since:
                    out[ln.get("step") or "?"][0] += cost(ln)
                    out[ln.get("step") or "?"][1] += 1
    except (OSError, ValueError):
        pass
    return {k: (round(v[0], 2), v[1]) for k, v in out.items()}


def settings_view() -> Dict:
    """What the screen shows: each part, its steps, their possible models (with key, test note, recommended)."""
    over, costs = _overrides(), costs_by_step()
    keys = {m: bool(key_of(m)) for m in MODELS}
    listed = {s for _, steps in PARTS for s in steps}

    def step_view(step: str) -> Dict:
        default = STEPS[step][0]
        current = over.get(step) if accepts(step, over.get(step, "")) else default
        return {"etape": step, "quoi": STEPS[step][1], "actuel": current, "recommande": default,
                "verrou": len(choices(step)) == 1, "cout_30j": costs.get(step, (0.0, 0))[0],
                "appels_30j": costs.get(step, (0.0, 0))[1],
                "choix": [{"modele": m, "nom": MODELS[m]["nom"], "cle_ok": keys[m], "recommande": m == default,
                           "note": "utilisé aujourd'hui" if m == default else TESTED.get((step, m), "non testé")}
                          for m in choices(step)]}
    parts = [("Adaptation et Idée", [s for s in STEPS if s not in listed])] + PARTS
    return {"parties": [{"nom": n, "etapes": [step_view(s) for s in steps]} for n, steps in parts],
            "transcription": {"actuel": transcription_model(), "recommande": TRANSCRIPTION[0],
                              "choix": [{"modele": m, "nom": m, "note": TRANSCRIPTION_NOTES[m], "recommande": m == TRANSCRIPTION[0],
                                         "cle_ok": keys[OPENAI] if m == "whisper-1" else True} for m in TRANSCRIPTION]}}
