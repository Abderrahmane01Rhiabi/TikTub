"""
"Script d'abord": the script is written BEFORE any footage is looked for,
built to keep people watching to the end; each sentence says which image it
needs, and the footage is then searched for that image.

One storyboard for every language — the same sequence of plans, each with
the image it needs, its role and the reference shots it draws on — and one
text per language, aligned plan by plan: the footage is searched once.

Retention rules (what keeps a Short watched):
  - a hook in the first 2-3 seconds: a question or something surprising,
    on the most striking image
  - a promise early (an open loop: the answer is coming)
  - a climb: each plan brings something new, concrete
  - the answer at the end, complete — never a relaunch ("Mais au fait…")
Images must be filmable and findable as real videos: concrete (who, what,
where, which camera), preferably shots the reference itself used (their
footage exists somewhere), never an idea, a diagram or a text.
"""

import json
import os
from typing import Dict, List, Optional

from adaptation.langs import lang as lang_of
from adaptation.script import LANG_RULES, ScriptError

ROLES = ("accroche", "promesse", "montee", "reponse")
HOOK_MAX_S = 4.0          # longer, the first sentence loses the scroller (it is asked 2-3 s; 3.6 s was still a good hook)
PLAN_MAX_S = 7.0          # longer, a matching clip is hard to find
TOTAL_S = (20.0, 45.0)

WRITE_PROMPT = """Tu ecris un YouTube Short explicatif (voix off sur des images) AVANT d'avoir les images.
Il reprend la RECETTE d'un Short viral :
- sujet : {sujet}
- question : {question}
- ses plans (numero, role, ce qu'on voit, ce qui est dit) :
{plans}
- faits utilisables : {faits}
- faits DOUTEUX a ne pas reprendre tels quels : {douteux}
- publicite dans le modele (NE PAS reprendre, ni la marque ni l'argument de vente) : {pub}

BUT : que les gens regardent JUSQU'A LA FIN.
- 6 a 8 plans, 25 a 35 secondes de voix en tout.
- Plan 1 "accroche" : une question ou un fait surprenant, TRES court (2 a 3 secondes de voix), sur l'image la plus forte.
- Plan 2 "promesse" : on comprend que la reponse arrive (boucle ouverte), sans cliche du genre "restez jusqu'a la fin".
- Plans du milieu "montee" : chaque plan apporte un element NOUVEAU et concret, la tension monte.
- Dernier plan "reponse" : une phrase COMPLETE qui REPOND a la question du debut. Jamais une relance, une question
  ou des points de suspension ("Mais au fait…", "Et vous ?").
- Chaque plan : au plus 6 secondes de voix (une image trouvee dure rarement plus).
- REECRIS avec tes propres phrases, ne traduis jamais le texte d'origine. Faits exacts et prudents.

IMAGES : pour chaque plan, "image" = la video qu'il faudra TROUVER pour l'illustrer : concrete et filmable
(qui, quoi, ou, quelle camera, quel moment), comme on la chercherait sur YouTube. De preference une image
que le modele montre deja ("plans_modele" = ses numeros) : ces videos existent. Une image nouvelle seulement si
c'est une video tres courante. Jamais une idee, un schema, un texte ou une image impossible a filmer.
Pas deux plans avec la meme image.

TEXTES dans chaque langue demandee, qui disent la meme chose plan par plan, naturels dans chaque langue :
{langues}
- bandeau : 2 a 5 mots percutants + 1 emoji, different a chaque plan, format "SUJET : DETAIL 😐" de preference
- mots_cles : 1 ou 2 mots EXACTS de la phrase, a colorer dans les sous-titres
- titre (100 caracteres max, 1-2 emojis), description (2-3 phrases + 3 a 5 hashtags dont #shorts), tags (8 a 12)

JSON uniquement :
{{"plans": [{{"role": "accroche | promesse | montee | reponse", "image": "...", "plans_modele": [numeros],
             "textes": {{{exemple}}}}}],
  "meta": {{{exemple_meta}}}}}"""

CRITIQUE_PROMPT = """Tu es un relecteur exigeant de YouTube Shorts. Voici un storyboard ecrit avant de chercher les images (JSON) :
{bundle}
Verifie et CORRIGE si besoin, en gardant le meme format JSON :
- RETENTION : plan 1 = accroche tres courte (2-3 s de voix) et intrigante ; une promesse tot ; chaque plan apporte du
  nouveau ; le dernier plan REPOND a la question du debut par une phrase complete (jamais une relance ni "…") ;
- chaque phrase est complete et claire a l'oral, au plus 6 secondes de voix ;
- les images sont concretes, filmables et trouvables en video (pas d'idee abstraite, de schema ni de texte),
  toutes differentes ; garde "plans_modele" quand l'image vient du modele ;
- langues : {regles}
- les textes des differentes langues disent la meme chose au meme plan ;
- faits prudents, aucune marque ni argument de vente.
JSON uniquement, meme format, avec en plus "corrections": ["ce que tu as change et pourquoi"]."""

REVISE_PROMPT = """Voici le storyboard d'un Short (JSON) :
{bundle}
Corrige-le selon cette demande, sans rien changer d'autre, et renvoie le JSON complet au meme format :
{demande}"""


def _gemini(pro: bool = False):
    from adaptation.script import _gemini as g
    return g(pro)


def _plans_listing(reference: Dict) -> str:
    return "\n".join(f"  {k}. [{p.get('role')}] {p.get('visuel')} -> \"{p.get('paroles')}\""
                     for k, p in enumerate(reference.get("plans") or [], 1))


def _languages_listing(codes: List[str]) -> str:
    return "\n".join(f"- {c} ({lang_of(c)['label']}) : {LANG_RULES.get(c, LANG_RULES['fr'])}" for c in codes)


def write(reference: Dict, codes: List[str], gemini=None) -> Dict:
    """{"plans": [...], "meta": {lang: {...}}} — one storyboard, texts for every language."""
    exemple = ", ".join(f'"{c}": {{"bandeau": "", "texte": "", "mots_cles": [""]}}' for c in codes)
    exemple_meta = ", ".join(f'"{c}": {{"titre": "", "description": "", "tags": [""]}}' for c in codes)
    prompt = WRITE_PROMPT.format(sujet=reference.get("sujet"), question=reference.get("question"),
                                 plans=_plans_listing(reference), faits="; ".join(reference.get("faits") or []),
                                 douteux="; ".join(reference.get("faits_douteux") or []) or "aucun",
                                 pub=reference.get("publicite") or "aucune", langues=_languages_listing(codes),
                                 exemple=exemple, exemple_meta=exemple_meta)
    r = (gemini or _gemini())._generate_content([{"text": prompt}], max_tokens=16000, timeout=180, temperature=0.7)
    return normalise(r, codes)


def critique(bundle: Dict, codes: List[str], gemini=None) -> Dict:
    """The stronger model re-reads for retention, language, images and facts;
    on failure (or if it broke the structure) the bundle comes back unchanged."""
    regles = " ; ".join(f"{c} : {LANG_RULES.get(c, LANG_RULES['fr'])}" for c in codes)
    try:
        r = (gemini or _gemini(pro=True))._generate_content(
            [{"text": CRITIQUE_PROMPT.format(bundle=json.dumps(_public(bundle), ensure_ascii=False, indent=1),
                                             regles=regles)}], max_tokens=24000, timeout=240, temperature=0.3)
        fixed = normalise(r, codes)
    except Exception:
        return {**bundle, "corrections": []}
    if not 3 <= len(fixed["plans"]) <= 12:
        return {**bundle, "corrections": []}
    fixed["corrections"] = [str(c) for c in (r.get("corrections") if isinstance(r, dict) else None) or []][:12]
    return fixed


def revise(bundle: Dict, codes: List[str], request: str, gemini=None) -> Dict:
    r = (gemini or _gemini())._generate_content(
        [{"text": REVISE_PROMPT.format(bundle=json.dumps(_public(bundle), ensure_ascii=False, indent=1),
                                       demande=request)}], max_tokens=16000, timeout=180, temperature=0.4)
    out = normalise(r, codes)
    out["corrections"] = bundle.get("corrections", [])
    return out


def _public(bundle: Dict) -> Dict:
    return {"plans": [{k: p.get(k) for k in ("role", "image", "plans_modele", "textes")} for p in bundle["plans"]],
            "meta": bundle.get("meta") or {}}


def normalise(r, codes: List[str]) -> Dict:
    if not isinstance(r, dict) or "error" in r or not isinstance(r.get("plans"), list):
        raise ScriptError(f"Storyboard inutilisable : {str(r)[:200]}")
    plans = []
    for p in r["plans"]:
        if not isinstance(p, dict):
            continue
        textes = p.get("textes") if isinstance(p.get("textes"), dict) else {}
        t = {}
        for c in codes:
            x = textes.get(c) if isinstance(textes.get(c), dict) else {}
            t[c] = {"bandeau": str(x.get("bandeau") or "").strip(), "texte": " ".join(str(x.get("texte") or "").split()),
                    "mots_cles": [str(m) for m in x.get("mots_cles") or [] if str(m).strip()][:3]}
        if not any(v["texte"] for v in t.values()):
            continue
        role = str(p.get("role") or "").lower().strip().replace("é", "e")
        plans.append({"role": role if role in ROLES else "montee", "image": " ".join(str(p.get("image") or "").split()),
                      "plans_modele": [int(i) for i in p.get("plans_modele") or [] if isinstance(i, (int, float))],
                      "textes": t})
    meta = {}
    raw_meta = r.get("meta") if isinstance(r.get("meta"), dict) else {}
    for c in codes:
        m = raw_meta.get(c) if isinstance(raw_meta.get(c), dict) else {}
        meta[c] = {"titre": str(m.get("titre") or "").strip()[:100], "description": str(m.get("description") or "").strip(),
                   "tags": [str(x).strip() for x in m.get("tags") or [] if str(x).strip()][:15]}
    out = {"plans": plans, "meta": meta}
    durations(out, codes)
    return out


def seconds(text: str, code: str) -> float:
    return round(len(text) / lang_of(code)["chars_per_second"], 1)


def durations(bundle: Dict, codes: List[str]) -> None:
    """Each plan needs a clip at least as long as its longest text, in any language."""
    for p in bundle["plans"]:
        p["duree"] = round(max([seconds(p["textes"][c]["texte"], c) for c in codes if c in p["textes"]] or [0]) + 0.3, 1)


def script_for(bundle: Dict, code: str) -> Dict:
    """One language's script, in the format the rest of the app uses (no clips yet)."""
    m = (bundle.get("meta") or {}).get(code) or {}
    return {"titre": m.get("titre", ""), "description": m.get("description", ""), "tags": m.get("tags", []),
            "passages": [{"clip": "", **p["textes"][code]} for p in bundle["plans"]],
            "corrections": bundle.get("corrections", [])}


def problems(bundle: Dict, code: str) -> List[str]:
    """What blocks the approval of one language, in French."""
    out = []
    plans = bundle.get("plans") or []
    if not 3 <= len(plans) <= 12:
        out.append(f"{len(plans)} plans : il en faut entre 3 et 12.")
    images = {}
    for k, p in enumerate(plans, 1):
        t = (p.get("textes") or {}).get(code) or {}
        texte = (t.get("texte") or "").rstrip()
        if not texte:
            out.append(f"Plan {k} : pas de texte.")
            continue
        if texte[-1:] in (",", ":", "،", ";", "…") or texte.endswith("..."):
            out.append(f"Plan {k} : phrase incomplète (elle finit par « {'…' if texte.endswith(('…', '...')) else texte[-1]} »).")
        s = seconds(texte, code)
        if k == 1 and s > HOOK_MAX_S:
            out.append(f"Plan 1 : accroche trop longue ({s} s de voix, viser 2 à 3 s).")
        elif s > PLAN_MAX_S:
            out.append(f"Plan {k} : phrase trop longue ({s} s de voix) : une image aussi longue est rare, coupe-la en deux.")
        image = (p.get("image") or "").strip()
        if len(image.split()) < 4:
            out.append(f"Plan {k} : décris l'image voulue (qui, quoi, où), elle servira à la chercher.")
        elif image.lower() in images:
            out.append(f"Plan {k} : même image que le plan {images[image.lower()]}, choisis-en une autre.")
        images.setdefault(image.lower(), k)
    total = sum(seconds(((p.get("textes") or {}).get(code) or {}).get("texte", ""), code) for p in plans)
    if plans and not TOTAL_S[0] <= total <= TOTAL_S[1]:
        out.append(f"Durée totale : environ {total:.0f} s de voix (viser 25 à 35 s).")
    return out
