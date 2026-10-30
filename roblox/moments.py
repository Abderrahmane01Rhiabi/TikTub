"""Gemini watches each downloaded passage and notes every moment that stands alone: where it starts, the exact
instant of the punchline, the face that reacts, where the action is in the picture."""

import os
from typing import Dict, List

PROMPT = """Ce passage vient d'une longue video Roblox (sketchs, jeu de role, compilation). Les secondes comptent depuis le debut
de CE fichier. On veut en tirer des YouTube Shorts. Repere chaque moment qui tient tout seul (un gag, un quiproquo, une dispute,
une surprise, une reaction, une emotion) et decris-le precisement.
JSON uniquement :
{"moments": [{"debut": s, "fin": s, "chute": s (l'instant exact de la punchline ou de la reaction la plus forte),
  "resume": "ce qui se passe, en francais, en une phrase",
  "mise_en_place": "ce qu'il faut voir avant la chute pour comprendre",
  "type": "gag | quiproquo | dispute | surprise | reaction | emotion",
  "dialogues": "les repliques entendues ou lues (bulles), dans leur langue",
  "drole": 1 a 5, "tient_seul": true/false (compris sans le reste de la video),
  "visage_reaction": s ou null (un gros plan ou un personnage qui reagit, a zoomer),
  "action_x": 0 a 1 (ou est l'action principale horizontalement : 0 = gauche, 0.5 = centre, 1 = droite),
  "suite_surprenante": true/false (on pourrait arreter l'image juste avant la chute et demander « que va-t-il se passer ? »)}]}"""


def find(path: str, duration: float, gemini=None) -> List[Dict]:
    """The moments of one passage, those inside the file only (Gemini once gave 101-113 s in a 73-s file)."""
    from adaptation import sources
    if gemini is not None:
        r = gemini._generate_content([{"text": PROMPT}], max_tokens=12000, timeout=240, temperature=0.2)
    else:
        with sources.gemini_file(path) as (g, part):
            r = g._generate_content([{**part, "video_metadata": {"fps": 3}}, {"text": PROMPT}],
                                    max_tokens=12000, timeout=240, temperature=0.2)
    items = r if isinstance(r, list) else ((r or {}).get("moments") if isinstance(r, dict) else None)
    out = []
    for m in items if isinstance(items, list) else []:
        try:
            a, b, c = float(m["debut"]), float(m["fin"]), float(m.get("chute", m["fin"]))
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= a < b <= duration + 0.5:
            out.append({**m, "debut": a, "fin": min(b, duration), "chute": min(max(c, a), b)})
    return out
