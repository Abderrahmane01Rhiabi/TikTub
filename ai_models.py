#!/usr/bin/env python3
"""
Which AI model does each step — in one table — and what it costs.

Every call to Gemini goes through GeminiAIGenerator._generate_content; there,
the step asking (module.function, as the usage log names it) gets its model
from STEPS. Changing a step's model is one line here, or, without touching
the code, an entry in database/ai_models.json: {"finder._watch": "<model>"}.

A step not listed uses the generator's own model (gemini-flash-latest).
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
OVERRIDES = os.path.join("database", "ai_models.json")

# step: (model, what it does) — every step of the app that asks the AI
STEPS: Dict[str, tuple] = {
    "reference.analyse":     (FLASH, "regarder le Short modèle"),
    "storyboard.angles":     (FLASH, "proposer les angles (une version par chaîne)"),
    "storyboard.write":      (FLASH, "écrire le storyboard"),
    "storyboard.critique":   (PRO,   "relire le storyboard"),
    "storyboard.revise":     (FLASH, "corriger le storyboard"),
    "finder.plan_queries":   (FLASH, "écrire les recherches de chaque plan"),
    "finder.local_queries":  (FLASH, "écrire les recherches dans la langue du pays"),
    "finder.action_queries": (FLASH, "écrire les recherches « par action »"),
    "finder._sort_one":      (FLASH, "trier les résultats de recherche"),
    "finder._watch":         (FLASH, "regarder une vidéo candidate (YouTube)"),
    "finder._send_file":     (FLASH, "regarder une vidéo candidate (fichier)"),
    "sources.retime":        (FLASH, "recaler le moment exact"),
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
}

# model: [(from date, $ input, $ output)] per million tokens
PRICES: Dict[str, List[tuple]] = {
    FLASH: [("2000-01-01", 0.75, 3.75), ("2027-01-01", 1.50, 7.50)],
    PRO: [("2000-01-01", 2.00, 12.00)],
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


def price(model: str, day: str) -> tuple:
    """($ input, $ output) per million tokens for this model on this day (an unknown model: Flash's)."""
    rows = PRICES.get(model) or PRICES[FLASH]
    return next(((i, o) for start, i, o in reversed(rows) if day >= start), rows[0][1:])


def cost(line: Dict, day: Optional[str] = None) -> float:
    """One logged call's cost in dollars (day: price it at another date)."""
    i, o = price(line.get("model") or FLASH, day or (line.get("at") or "")[:10])
    return (line.get("prompt", 0) * i + (line.get("output", 0) + line.get("thoughts", 0)) * o) / 1e6


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
