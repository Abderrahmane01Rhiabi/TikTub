"""
Gemini (text only) gives the moments to the chosen montage styles and writes every text in every chosen language:
the hook, the POV line, the told story, the top's labels, the question, and each Short's title, description and
tags for Publication. Checked before use: a moment that does not exist, or an interval outside it, is dropped.
"""

import json
from typing import Dict, List, Tuple

LANG_NAMES = {"fr": "FRANCAIS", "en": "ANGLAIS", "ar": "ARABE", "es": "ESPAGNOL"}

# style: (name on screen, what Gemini must do, the JSON it answers)
STYLES: Dict[str, Tuple[str, str, str]] = {
    "clip": ("Clip sous-titré",
             "CLIP SOUS-TITRE : le moment le plus drole qui tient seul. Un titre d'accroche court en haut (6 mots max, pas d'emoji).",
             '{{"moment": "id", "titre": {T}}}'),
    "pov": ("POV",
            "POV / MEME : un moment court avec une reaction ; un titre « POV : ... » qui fait rire (10 mots max). Donne debut et fin "
            "DANS le moment (8 a 12 s, la fin 1 a 2 s apres la chute).",
            '{{"moment": "id", "debut": s, "fin": s, "pov": {T}}}'),
    "histoire": ("Histoire racontée",
                 "HISTOIRE RACONTEE : une petite histoire avec une voix off (25 a 30 s de voix en tout), en 4 a 6 passages ; chaque "
                 "passage dit ce qu'on VOIT pendant son extrait (un moment et un intervalle dedans, 2 a 6 s). Accroche des la 1re "
                 "phrase, une montee, une chute ou un retournement. Ton : narrateur complice, phrases courtes, pas de « dans cette "
                 "video ». Les langues racontent la meme chose, sans traduction mot a mot.",
                 '{{"titre": {T}, "passages": [{{"moment": "id", "debut": s, "fin": s, "textes": {T}}}]}}'),
    "top3": ("Top 3",
             "TOP 3 : trois moments differents classes du moins fort (#3) au plus fort (#1), chacun avec une etiquette courte (5 mots "
             "max), et un titre d'accroche. Pour chaque rang, un intervalle de 5 a 8 s DANS le moment qui finit 1 s apres la chute.",
             '{{"titre": {T}, "rangs": [{{"rang": 3, "moment": "id", "debut": s, "fin": s, "label": {T}}}]}}'),
    "devine": ("Devine la suite",
               "DEVINE LA SUITE : un moment dont la suite surprend ; l'image s'arrete juste avant la chute (« arret », secondes depuis "
               "le debut du moment) avec une question (8 mots max), puis la reponse est montree. Un texte final court.",
               '{{"moment": "id", "arret": s, "question": {T}, "final": {T}}}'),
}

PROMPT = """Tu montes des YouTube Shorts a partir d'une longue video Roblox (« {titre} », chaine {chaine}). Chaque style est fait dans
chaque langue : {langues}. Voici les moments disponibles (les secondes « debut », « fin », « arret » que tu donnes comptent depuis
le DEBUT DU MOMENT) :
{moments}

Pour chaque style ci-dessous, choisis et ecris, en restant fidele a ce qu'on voit (n'invente rien qui ne soit pas a l'image) :
{consignes}
Pour chaque style et chaque langue, ecris aussi la publication YouTube : un titre (moins de 70 caracteres, peut finir par un ou deux
emojis), une description de 2 phrases, 5 a 8 tags.
Ecris chaque langue avec ses accents et sa ponctuation.
JSON uniquement :
{{{schema}}}"""


def _listing(cat: List[Dict]) -> str:
    return "\n".join(f"- {m['id']} ({m['fin'] - m['debut']:.1f} s ; chute a {m['chute'] - m['debut']:.1f} s du debut du moment) "
                     f"[{m.get('type')}, force {m.get('drole')}/5, suite surprenante : {m.get('suite_surprenante')}] {m.get('resume')} "
                     f"Mise en place : {m.get('mise_en_place')}. Repliques : {m.get('dialogues')}" for m in cat)


def prompt(meta: Dict, cat: List[Dict], styles: List[str], langs: List[str]) -> str:
    t = "{" + ", ".join(f'"{l}": ""' for l in langs) + "}"
    pub = '"publication": {' + ", ".join(f'"{l}": {{"titre": "", "description": "", "tags": [""]}}' for l in langs) + "}"
    schema = ", ".join(f'"{s}": ' + STYLES[s][2].format(T=t)[:-1] + ", " + pub + "}" for s in styles)
    return PROMPT.format(titre=meta.get("titre", ""), chaine=meta.get("chaine", ""), langues=", ".join(LANG_NAMES.get(l, l) for l in langs),
                         moments=_listing(cat), consignes="\n".join(f"- \"{s}\" {STYLES[s][1]}" for s in styles), schema=schema)


def _fit(x: Dict, m: Dict, keys=("debut", "fin")) -> bool:
    """An interval given from the moment's start, kept inside the moment."""
    try:
        a, b = (float(x[k]) for k in keys)
    except (KeyError, TypeError, ValueError):
        return False
    length = m["fin"] - m["debut"]
    a, b = max(0.0, a), min(length, b)
    if b - a < 1.0:
        return False
    x[keys[0]], x[keys[1]] = round(a, 2), round(b, 2)
    return True


def normalise(raw, cat: List[Dict], styles: List[str], langs: List[str]) -> Tuple[Dict, List[str]]:
    """The plan without what can't be made, and why a style was left out."""
    byid, plan, dropped = {m["id"]: m for m in cat}, {}, []
    raw = raw if isinstance(raw, dict) else {}
    texts_ok = lambda d: isinstance(d, dict) and all(str(d.get(l) or "").strip() for l in langs)
    for s in styles:
        p = raw.get(s)
        ok = isinstance(p, dict)
        if ok and s in ("clip", "pov", "devine"):
            ok = p.get("moment") in byid
        if ok and s == "pov":
            ok = _fit(p, byid[p["moment"]]) and texts_ok(p.get("pov"))
        if ok and s == "clip":
            ok = texts_ok(p.get("titre"))
        if ok and s == "devine":
            m = byid[p["moment"]]
            try:
                p["arret"] = round(min(max(0.5, float(p["arret"])), m["chute"] - m["debut"]), 2)
            except (KeyError, TypeError, ValueError):
                p["arret"] = round(max(0.5, m["chute"] - m["debut"] - 0.4), 2)
            ok = texts_ok(p.get("question")) and texts_ok(p.get("final"))
        if ok and s == "histoire":
            p["passages"] = [x for x in p.get("passages") or [] if isinstance(x, dict) and x.get("moment") in byid
                             and _fit(x, byid[x["moment"]]) and texts_ok(x.get("textes"))]
            ok = len(p["passages"]) >= 2 and texts_ok(p.get("titre"))
        if ok and s == "top3":
            p["rangs"] = sorted((x for x in p.get("rangs") or [] if isinstance(x, dict) and x.get("moment") in byid
                                 and _fit(x, byid[x["moment"]]) and texts_ok(x.get("label"))), key=lambda x: -int(x.get("rang") or 0))
            for k, x in enumerate(p["rangs"]):
                x["rang"] = len(p["rangs"]) - k
            ok = len(p["rangs"]) >= 2 and texts_ok(p.get("titre"))
        pub = (p or {}).get("publication") if ok else None
        if ok and not all(isinstance((pub or {}).get(l), dict) and (pub[l].get("titre") or "").strip() for l in langs):
            ok = False
        if ok:
            plan[s] = p
        else:
            dropped.append(f"{STYLES[s][0]} : pas de moment qui convienne dans cette vidéo.")
    return plan, dropped


def write(meta: Dict, cat: List[Dict], styles: List[str], langs: List[str], gemini=None) -> Tuple[Dict, List[str]]:
    from gemini_ai_generator import GeminiAIGenerator
    import os
    g = gemini or GeminiAIGenerator(api_key=os.getenv("GEMINI_API_KEY"))
    raw = g._generate_content([{"text": prompt(meta, cat, styles, langs)}], max_tokens=16000, timeout=240, temperature=0.6)
    return normalise(raw, cat, styles, langs)


def translate(lines: List[str], lang: str, gemini=None) -> List[str]:
    """Subtitles of the original lines in another language, one for one (the original ones on failure)."""
    if not lines:
        return []
    import os
    from gemini_ai_generator import GeminiAIGenerator
    g = gemini or GeminiAIGenerator(api_key=os.getenv("GEMINI_API_KEY"))
    r = g._generate_content([{"text": f"Traduis en {LANG_NAMES.get(lang, lang).lower()} familier et naturel, comme des sous-titres de "
                                      "sketch, chaque ligne, dans l'ordre, meme nombre de lignes. JSON uniquement : "
                                      "{\"lignes\": [\"...\"]}\n" + "\n".join(f"{k + 1}. {x}" for k, x in enumerate(lines))}],
                            max_tokens=3000, timeout=60, temperature=0.2)
    out = (r or {}).get("lignes") if isinstance(r, dict) else None
    return [str(x) for x in out] if isinstance(out, list) and len(out) == len(lines) else list(lines)


def publication(plan: Dict, style: str, lang: str) -> Dict:
    p = ((plan.get(style) or {}).get("publication") or {}).get(lang) or {}
    return {"titre": str(p.get("titre") or "").strip(), "description": str(p.get("description") or "").strip(),
            "tags": [str(t).strip() for t in p.get("tags") or [] if str(t).strip()][:12]}


def dumps(plan: Dict) -> str:
    return json.dumps(plan, ensure_ascii=False)
