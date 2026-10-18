"""
Our own script, one language at a time, clip by clip.

Rules learned on the tram prototype (rated 7.5/10):
  - rewrite, never translate the reference word for word
  - facts stay cautious (the reference's "they never face charges" became
    "presque toujours la faute de l'automobiliste")
  - a question in the first second, in the banner AND the voice
  - the last sentence is COMPLETE on its own (the Arabic ending only made
    sense on a loop; a "Mais au fait…" relaunch slipped through once): a
    script still ending in suspense after the re-read is fixed once more
  - each sentence fits the clip under it; no clip twice (reusing the first
    clip at the end "for the loop" looked like a mistake)
  - a reference that advertises a product: neither the brand nor the sales
    pitch is taken (a pool Short ended on its sponsor's "ultra-resistant pool")
A person always reviews and can edit the script before any voice is made.
"""

import json
import os
from typing import Dict, List, Optional, Tuple

from adaptation.langs import lang as lang_of

LANG_RULES = {
    "fr": "francais naturel et oral, phrases courtes, ton pose et un peu intrigant. Bandeaux EN MAJUSCULES.",
    "ar": "ARABE STANDARD MODERNE (fusha) clair, simple et oral, sans dialecte. Pas de harakat sauf si un mot est ambigu.",
    "en": "natural spoken English, short sentences, calm and intriguing. Banners IN CAPITALS.",
}

PROMPT = """Tu ecris le script d'un YouTube Short explicatif (voix off) pour une chaine en {langue}.
Il reprend la RECETTE d'un Short viral (a garder) :
- sujet : {sujet}
- question : {question}
- deroule : {plans}
- faits utilisables : {faits}
- faits DOUTEUX a ne pas reprendre tels quels : {douteux}
- publicite dans le modele (NE PAS reprendre, ni la marque ni l'argument de vente) : {pub}

Clips disponibles (lettre: contenu, duree utilisable, instant du moment fort depuis le debut du clip) :
{clips}
{angle}
REGLES
- Langue : {regles}
- REECRIS avec tes propres phrases, ne traduis jamais le texte d'origine mot a mot.
- Faits exacts et prudents, jamais absolus quand ce n'est pas certain.
- 6 a 8 passages. Chaque passage = UN clip (sa lettre) qui illustre la phrase. JAMAIS deux fois le meme clip.
  Un clip marque "(extrait du Short modele)" ne sert JAMAIS au 1er passage, et sa phrase tient en 3 secondes.
- Chaque passage = UNE OU DEUX PHRASES COMPLETES qui se lisent seules : jamais une phrase coupee entre deux passages,
  jamais de "…" ni au debut ni a la fin d'un passage.
- 1er passage : une QUESTION qui donne envie de rester, dans le bandeau ET dans la phrase, sur un clip dont le moment fort arrive vite.
- Dernier passage : une phrase COMPLETE qui REPOND a la question du debut et conclut seule. Jamais une relance,
  une question ou une phrase en suspens ("Mais au fait…", "Et vous ?", "…").
- Si le modele fait la publicite d'une marque ou d'un produit : ne cite pas la marque, ne reprends pas l'argument
  de vente ; termine plutot sur un fait ou un conseil utile.
- Chaque phrase tient dans la duree de son clip : au plus {cps} caracteres par seconde de clip.
- Duree totale de lecture : 27 a 33 secondes.
- Bandeau : 2 a 5 mots percutants + 1 emoji, different a chaque passage, format "SUJET : DETAIL 😐" de preference.
- mots_cles : 1 ou 2 mots EXACTS de la phrase, a colorer dans les sous-titres.
- FLECHES ET CERCLES : sur 2 ou 3 passages seulement, ceux ou il faut ANTICIPER une action (la voiture qui va
  etre percutee) ou VOIR un detail, "annotation": {{"type": "fleche" ou "cercle", "cible": "ce qu'il faut pointer,
  visible dans le clip (ex. la voiture noire a droite)"}} ; sinon "annotation": null.
- titre (100 caracteres max, avec 1-2 emojis), description (2-3 phrases + 3 a 5 hashtags dont #shorts), tags (8 a 12).

JSON uniquement :
{{"titre": "", "description": "", "tags": [""],
  "passages": [{{"clip": "A", "bandeau": "", "texte": "", "mots_cles": [""], "annotation": null}}]}}"""

REVISE_PROMPT = """Voici le script d'un Short (JSON) :
{script}
Clips (lettre: duree utilisable en secondes) : {durees}
Corrige-le selon cette demande, sans rien changer d'autre, et renvoie le JSON complet au meme format :
{demande}"""


CRITIQUE_PROMPT = """Tu es un relecteur exigeant de scripts de YouTube Shorts, langue : {langue}.
Script (JSON) :
{script}
Verifie et CORRIGE si besoin, sans changer les clips ni l'ordre :
- chaque passage est fait de phrases COMPLETES et claires a l'oral (jamais un fragment, jamais une fin en ":" ou ",",
  jamais de "…" au debut ou a la fin, jamais une phrase coupee entre deux passages) ;
- le dernier passage conclut seul et repond a la question du debut : jamais une relance, une question ou des
  points de suspension ("Mais au fait…") ;
- aucune marque ni argument de vente d'un produit (si le modele etait une publicite) ;
- {regles}
- les faits restent prudents (pas de "jamais"/"toujours" non verifie) ;
- les mots_cles sont des mots EXACTS de leur phrase ;
- LONGUEUR MAXIMALE de chaque phrase (elle doit tenir dans son clip), a respecter strictement :
{budgets}
JSON uniquement, au meme format que le script, avec en plus "corrections": ["ce que tu as change et pourquoi"]."""


class ScriptError(RuntimeError):
    pass


def _gemini(pro: bool = False):
    from gemini_ai_generator import GeminiAIGenerator
    g = GeminiAIGenerator(api_key=os.getenv("GEMINI_API_KEY"))
    if pro:     # the stronger model, for the critical re-read (the Arabic endings slipped past flash twice)
        g.model_name = "gemini-pro-latest"
        g.base_url = f"https://generativelanguage.googleapis.com/v1beta/models/{g.model_name}:generateContent"
    return g


def clip_listing(clips: Dict[str, Dict]) -> str:
    return "\n".join(f"- {cid}: {c.get('desc') or 'clip'} ({c['end'] - c['start']:.1f}s, moment fort a "
                     f"{c['impact'] - c['start']:.1f}s)" for cid, c in clips.items() if c.get("usable", True))


ANGLE_PART = """
ANGLE IMPOSE pour CETTE chaine (sa video doit etre differente du modele et des autres chaines) : "{titre}" — {idee}
Le script suit cet angle : sa propre accroche, son propre ordre de clips, sa propre fin. Ne reprends ni l'accroche
ni la fin du modele.
"""


def write(reference: Dict, clips: Dict[str, Dict], lang_code: str, gemini=None, angle: Optional[Dict] = None) -> Dict:
    lang = lang_of(lang_code)
    plans = " | ".join(f"[{p.get('role')}] {p.get('visuel')} -> \"{p.get('paroles')}\"" for p in reference.get("plans", []))
    prompt = PROMPT.format(langue=lang["label"], sujet=reference.get("sujet"), question=reference.get("question"),
                           plans=plans, faits="; ".join(reference.get("faits") or []),
                           douteux="; ".join(reference.get("faits_douteux") or []) or "aucun",
                           pub=reference.get("publicite") or "aucune",
                           clips=clip_listing(clips), regles=LANG_RULES.get(lang["code"], LANG_RULES["fr"]),
                           cps=lang["chars_per_second"], angle=ANGLE_PART.format(**angle) if angle else "")
    r = (gemini or _gemini())._generate_content([{"text": prompt}], max_tokens=16000, timeout=180, temperature=0.6)
    return normalise(r, clips)


def budgets(script: Dict, clips: Dict[str, Dict], lang_code: str) -> str:
    cps = lang_of(lang_code)["chars_per_second"]
    return "\n".join(f"  passage {k}: {int((clips[p['clip']]['end'] - clips[p['clip']]['start']) * cps)} caracteres"
                     for k, p in enumerate(script.get("passages") or [], 1) if p.get("clip") in clips)


def critique(script: Dict, lang_code: str, clips: Dict[str, Dict], gemini=None) -> Dict:
    """A stronger model re-reads the script and fixes incomplete sentences,
    the ending, the language level and over-confident facts. Returns the
    corrected script with its "corrections" list (shown to the person); on
    failure, the script unchanged with an empty list."""
    lang = lang_of(lang_code)
    try:
        r = (gemini or _gemini(pro=True))._generate_content(
            [{"text": CRITIQUE_PROMPT.format(langue=lang["label"], script=json.dumps(script, ensure_ascii=False, indent=1),
                                             regles=LANG_RULES.get(lang["code"], LANG_RULES["fr"]),
                                             budgets=budgets(script, clips, lang_code))}],
            max_tokens=24000, timeout=240, temperature=0.3)
        fixed = normalise(r, clips)
    except Exception:
        return {**script, "corrections": []}
    if len(fixed["passages"]) != len(script["passages"]):          # it was told not to restructure
        return {**script, "corrections": []}
    for new, old in zip(fixed["passages"], script["passages"]):
        new["clip"] = old["clip"]
    fixed["corrections"] = [str(c) for c in r.get("corrections") or []][:12]
    return fixed


def revise(script: Dict, clips: Dict[str, Dict], request: str, gemini=None) -> Dict:
    durees = {cid: round(c["end"] - c["start"], 1) for cid, c in clips.items()}
    r = (gemini or _gemini())._generate_content(
        [{"text": REVISE_PROMPT.format(script=json.dumps(script, ensure_ascii=False, indent=1),
                                       durees=json.dumps(durees), demande=request)}],
        max_tokens=16000, timeout=180, temperature=0.4)
    return normalise(r, clips)


def normalise(r, clips: Dict[str, Dict]) -> Dict:
    if not isinstance(r, dict) or "error" in r or not isinstance(r.get("passages"), list):
        raise ScriptError(f"Script inutilisable : {str(r)[:200]}")
    passages = []
    for p in r["passages"]:
        if not isinstance(p, dict) or not str(p.get("texte", "")).strip():
            continue
        from adaptation.storyboard import clean_annotation
        passages.append({"clip": str(p.get("clip", "")).strip().upper(), "bandeau": str(p.get("bandeau", "")).strip(),
                         "texte": " ".join(str(p["texte"]).split()),
                         "mots_cles": [str(m) for m in p.get("mots_cles") or [] if str(m).strip()][:3],
                         "annotation": clean_annotation(p.get("annotation"))})
    tags = [str(t).strip() for t in r.get("tags") or [] if str(t).strip()]
    return {"titre": str(r.get("titre", "")).strip()[:100], "description": str(r.get("description", "")).strip(),
            "tags": tags[:15], "passages": passages}


def problems(script: Dict, clips: Dict[str, Dict], lang_code: str) -> List[str]:
    """What blocks the voice step, in French, for the review screen."""
    lang = lang_of(lang_code)
    out = []
    ps = script.get("passages") or []
    if not 3 <= len(ps) <= 12:
        out.append(f"{len(ps)} passages : il en faut entre 3 et 12.")
    usable = sum(1 for c in clips.values() if c.get("usable", True))
    seen = {}
    for k, p in enumerate(ps, 1):
        end = p["texte"].rstrip()
        if end[-1:] in (",", ":", "،", ";", "…") or end.endswith("..."):
            shown = "…" if end.endswith(("…", "...")) else end[-1]
            out.append(f"Passage {k} : phrase incomplète (elle finit par « {shown} »).")
        if end.lstrip().startswith(("…", "...")):
            out.append(f"Passage {k} : la phrase commence par « … » : elle continue celle d'avant, écris une phrase complète.")
        if k == 1 and (clips.get(p["clip"]) or {}).get("extrait"):
            out.append("Passage 1 : l'accroche ne peut pas être un extrait du Short modèle, choisis un autre clip.")
        if p["clip"] in seen and usable >= len(ps):           # with too few clips, a repeat is the only way
            out.append(f"Passage {k} : le clip {p['clip']} est déjà utilisé au passage {seen[p['clip']]}, choisis-en un autre.")
        seen.setdefault(p["clip"], k)
        c = clips.get(p["clip"])
        if not c:
            out.append(f"Passage {k} : le clip « {p['clip']} » n'existe pas.")
            continue
        room = (c["end"] - c["start"]) * lang["chars_per_second"]
        if len(p["texte"]) > room * 1.15:
            out.append(f"Passage {k} : phrase trop longue pour son clip ({len(p['texte'])} caractères, "
                       f"le clip {p['clip']} en laisse environ {int(room)}).")
    total = sum(len(p["texte"]) for p in ps) / lang["chars_per_second"]
    if total > 45:
        out.append(f"Script trop long : environ {total:.0f} s de lecture (viser 27-33 s).")
    return out


def estimated_seconds(script: Dict, lang_code: str) -> float:
    return round(sum(len(p["texte"]) for p in script.get("passages") or []) / lang_of(lang_code)["chars_per_second"], 1)
