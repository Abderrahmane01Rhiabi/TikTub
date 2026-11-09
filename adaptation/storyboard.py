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
import re
import os
from typing import Dict, List, Optional, Tuple

from adaptation.langs import lang as lang_of
from adaptation.script import LANG_RULES, ScriptError

ROLES = ("accroche", "promesse", "montee", "reponse")
HOOK_MAX_S = 4.0          # longer, the first sentence loses the scroller (it is asked 2-3 s; 3.6 s was still a good hook)
PLAN_MAX_S = 7.0          # longer, a matching clip is hard to find
TOTAL_S = (20.0, 38.0)    # of voice (estimated): 45 let a 41 s Arabic Short through, the aim is 25-35 s

WRITE_PROMPT = """Tu ecris un YouTube Short explicatif (voix off sur des images) AVANT d'avoir les images.
Il reprend la RECETTE d'un Short viral :
- sujet : {sujet}
- question : {question}
- ses plans (numero, role, ce qu'on voit, ce qui est dit) :
{plans}
- faits utilisables : {faits}
- faits DOUTEUX a ne pas reprendre tels quels : {douteux}
- publicite dans le modele (NE PAS reprendre, ni la marque ni l'argument de vente) : {pub}

{angle}BUT : que les gens regardent JUSQU'A LA FIN.
- 6 a 8 plans, 25 a 35 secondes de voix en tout.
- Plan 1 "accroche" : une question ou un fait surprenant, TRES court (2 a 3 secondes de voix), sur l'image la plus forte.
- Plan 2 "promesse" : on comprend que la reponse arrive (boucle ouverte), sans cliche du genre "restez jusqu'a la fin".
- Plans du milieu "montee" : chaque plan apporte un element NOUVEAU et concret, la tension monte.
- Dernier plan "reponse" : une phrase COMPLETE qui REPOND a la question du debut. Jamais une relance, une question
  ou des points de suspension ("Mais au fait…", "Et vous ?").
- Chaque plan : au plus 6 secondes de voix (une image trouvee dure rarement plus).
- Chaque plan = UNE OU DEUX PHRASES COMPLETES, qui se lisent seules. JAMAIS une phrase coupee entre deux plans,
  jamais de points de suspension ("…", "...") ni au debut ni a la fin d'un plan, jamais un plan qui commence par
  "et", "mais", "qui", "car" pour continuer la phrase du plan d'avant (chaque plan a son propre clip).
- REECRIS avec tes propres phrases, ne traduis jamais le texte d'origine. Faits exacts et prudents.

IMAGES : pour chaque plan, "image" = la video qu'il faudra TROUVER pour l'illustrer : concrete et filmable
(qui, quoi, ou, quelle camera, quel moment), comme on la chercherait sur YouTube. De preference une image
que le modele montre deja ("plans_modele" = ses numeros) : ces videos existent. Une image nouvelle seulement si
c'est une video tres courante. Jamais une idee, un schema, un texte ou une image impossible a filmer.
Pas deux plans avec la meme image. Decris l'ACTION, pas la facon de filmer : le montage sait ralentir et zoomer,
n'exige donc ni "au ralenti" ni "plan serre" (ces videos sont rares) ; et l'image montre ce que dit SA phrase.
"idee" = en ANGLAIS, ce que montrerait n'importe quelle video qui fait passer le SENS de la phrase (ce qu'elle fait
comprendre ou ressentir, pas ses mots pris a la lettre), generale et filmable, ce qu'on VOIT (les choses et l'action),
sans lieu ni nom precis ni facon de filmer (pas de timelapse, gros plan, drone) : 5 a 12 mots ; "new apartment
buildings, a hand giving keys", pas "les familles d'El Harrouyine recoivent les cles" ; "ce plafond emprisonne la
chaleur" -> "the Earth heating up, heat waves over a hot city", pas "a thick cloud cover". Un monteur prend une image
qui fait passer l'idee quand la scene exacte manque.

FLECHES ET CERCLES : sur 2 ou 3 plans seulement (jamais plus), ceux ou le spectateur doit ANTICIPER une action
(la voiture qui va etre percutee, le tuyau qui va exploser) ou VOIR un detail qu'il raterait, donne "annotation" :
{{"type": "fleche" (pour anticiper un mouvement) ou "cercle" (pour un detail), "cible": "ce qu'il faut pointer,
visible a l'image, decrit pour etre trouve (ex. la voiture noire a droite)"}}. Sinon "annotation": null.

TEXTES dans chaque langue demandee, qui disent la meme chose plan par plan, naturels dans chaque langue :
{langues}
- bandeau : 2 a 5 mots percutants + 1 emoji, different a chaque plan, format "SUJET : DETAIL 😐" de preference
- mots_cles : 1 ou 2 mots EXACTS de la phrase, a colorer dans les sous-titres
- titre (100 caracteres max, 1-2 emojis), description (2-3 phrases + 3 a 5 hashtags dont #shorts), tags (8 a 12)

JSON uniquement :
{{"plans": [{{"role": "accroche | promesse | montee | reponse", "image": "...", "idee": "...", "plans_modele": [numeros],
             "annotation": null, "textes": {{{exemple}}}}}],
  "meta": {{{exemple_meta}}}}}"""

CRITIQUE_PROMPT = """Tu es un relecteur exigeant de YouTube Shorts. Voici un storyboard ecrit avant de chercher les images (JSON) :
{bundle}
Verifie et CORRIGE si besoin, en gardant le meme format JSON :
- RETENTION : plan 1 = accroche tres courte (2-3 s de voix) et intrigante ; une promesse tot ; chaque plan apporte du
  nouveau ; le dernier plan REPOND a la question du debut par une phrase complete (jamais une relance ni "…") ;
- chaque plan est fait de phrases COMPLETES qui se lisent seules, au plus 6 secondes de voix : une phrase coupee
  entre deux plans ("… patiner sur place…" / "…et leur evite…") est reecrite en deux phrases completes, sans "…" ;
- les images sont concretes, filmables et trouvables en video (pas d'idee abstraite, de schema ni de texte),
  toutes differentes ; garde "plans_modele" quand l'image vient du modele ;
- chaque phrase COMMENTE SON IMAGE : le spectateur entend la phrase en voyant l'image, il doit voir ce qu'elle dit.
  Une phrase abstraite (physique, energie, "le secret c'est…") sur une image d'action est reecrite pour parler
  de ce qu'on voit ("ses jambes plient et absorbent le choc"), ou l'image est changee pour montrer ce que dit la phrase ;
- langues : {regles}
- les textes des differentes langues disent la meme chose au meme plan ;
- faits prudents, aucune marque ni argument de vente.
JSON uniquement, meme format, avec en plus "corrections": ["ce que tu as change et pourquoi"]."""

REVISE_PROMPT = """Voici le storyboard d'un Short (JSON) :
{bundle}
Corrige-le selon cette demande, sans rien changer d'autre, et renvoie le JSON complet au meme format :
{demande}"""


def _gemini():
    from adaptation.script import _gemini as g
    return g()


def _plans_listing(reference: Dict) -> str:
    return "\n".join(f"  {k}. [{p.get('role')}] {p.get('visuel')} -> \"{p.get('paroles')}\""
                     for k, p in enumerate(reference.get("plans") or [], 1))


def _languages_listing(codes: List[str]) -> str:
    return "\n".join(f"- {c} ({lang_of(c)['label']}) : {LANG_RULES.get(c, LANG_RULES['fr'])}" for c in codes)


ANGLE_PART = """ANGLE IMPOSE (cette version doit etre DIFFERENTE du modele, pas une traduction) : "{titre}" — {idee}
L'histoire suit cet angle : sa propre question d'accroche, son propre ordre de plans, sa propre fin. Ne reprends ni
l'accroche ni la fin du modele ; garde seulement le sujet et les faits.

"""

ANGLES_PROMPT = """Un Short viral explique : {sujet}
Question du modele : {question}
Faits : {faits}
Propose {n} ANGLES vraiment differents pour refaire une video sur ce sujet (autre question d'accroche, autre fil de
l'histoire, autre fin), chacun capable de garder le spectateur jusqu'a la fin, avec les memes images disponibles.
{deja}Ex. pour une machine a raviolis : "Le test honnete", "Les 3 erreurs que tout le monde fait", "Ca vaut le coup ?".
JSON uniquement : {{"angles": [{{"titre": "2 a 6 mots", "idee": "1 ou 2 phrases : la question posee, le fil, la fin"}}]}}"""


STRICT_FACTS = """FAITS (video sans modele, faite a partir d'une idee) : n'utilise AUCUN autre fait que les "faits
utilisables" ci-dessus (chacun vient d'une page web verifiee). Aucun chiffre, date ou nom qui n'y est pas.

"""


def angles(reference: Dict, n: int = 3, avoid: Optional[List[str]] = None, gemini=None) -> List[Dict]:
    """n different angles on the reference's subject, none of the ones already used."""
    deja = ("Angles DEJA utilises, a ne pas reprendre : " + " ; ".join(avoid) + "\n") if avoid else ""
    said = reference.get("suggestions_youtube") or []        # « Idée d'abord »: what people really search
    if said:
        deja += ("Ce que les gens tapent sur YouTube a ce sujet (un angle qui repond a l'une de ces recherches "
                 "accroche mieux) : " + " ; ".join(said[:10]) + "\n")
    r = (gemini or _gemini())._generate_content([{"text": ANGLES_PROMPT.format(
        sujet=reference.get("sujet"), question=reference.get("question"), faits="; ".join(reference.get("faits") or []),
        n=n, deja=deja)}], max_tokens=3000, timeout=90, temperature=0.9)
    items = (r.get("angles") if isinstance(r, dict) else None) or []
    out, seen = [], {a.lower() for a in avoid or []}
    for a in items:
        if isinstance(a, dict) and str(a.get("titre") or "").strip() and str(a.get("titre")).strip().lower() not in seen:
            seen.add(str(a["titre"]).strip().lower())
            out.append({"titre": str(a["titre"]).strip()[:80], "idee": " ".join(str(a.get("idee") or "").split())[:400]})
    if not out:
        raise ScriptError(f"Aucun angle proposé : {str(r)[:160]}")
    return out


def write(reference: Dict, codes: List[str], gemini=None, angle: Optional[Dict] = None,
          recit: Optional[str] = None) -> Dict:
    """{"plans": [...], "meta": {lang: {...}}} — one storyboard, texts for every language;
    angle: {"titre", "idee"} this version follows, so that it differs from the reference;
    recit: a narrative style's rules (montage pro), they win over the general ones."""
    exemple = ", ".join(f'"{c}": {{"bandeau": "", "texte": "", "mots_cles": [""]}}' for c in codes)
    exemple_meta = ", ".join(f'"{c}": {{"titre": "", "description": "", "tags": [""]}}' for c in codes)
    prompt = WRITE_PROMPT.format(sujet=reference.get("sujet"), question=reference.get("question"),
                                 plans=_plans_listing(reference), faits="; ".join(reference.get("faits") or []),
                                 douteux="; ".join(reference.get("faits_douteux") or []) or "aucun",
                                 pub=reference.get("publicite") or "aucune", langues=_languages_listing(codes),
                                 angle=(recit or "") + (ANGLE_PART.format(**angle) if angle else "")
                                 + (STRICT_FACTS if reference.get("origine") == "idee" else ""),
                                 exemple=exemple, exemple_meta=exemple_meta)
    r = (gemini or _gemini())._generate_content([{"text": prompt}], max_tokens=16000, timeout=180, temperature=0.7)
    return normalise(r, codes)


def unfilmable(bundle: Dict) -> List[str]:
    """Images a search will hardly find (an animation, a diagram): sent to the
    automatic fix when the storyboard is written, never a block — an existing
    3D animation was found and chosen for one once."""
    return [f"Plan {k} : une animation ou un schema se trouve rarement en video : decris une scene reelle filmee."
            for k, p in enumerate(bundle.get("plans") or [], 1) if UNFILMABLE.search(p.get("image") or "")]


def illustration(bundle: Dict, code: str, gemini=None, only: Optional[List[int]] = None) -> List[str]:
    """Each sentence against its own image, before any search (the same judge
    as after the download, on the wanted image): what a viewer would hear
    without seeing it. Empty when it can't be judged. only: the plans to judge
    (0-based, e.g. those a fix changed); the messages keep the storyboard's numbers."""
    from adaptation import script
    plans = bundle.get("plans") or []
    ks = list(range(len(plans))) if only is None else [k for k in only if 0 <= k < len(plans)]
    if not ks:
        return []
    clips = {f"P{k + 1}": {"start": 0.0, "end": max(float(p.get("duree") or 4), 2.0), "desc": p.get("image") or ""}
             for k, p in enumerate(plans)}
    sc = {"passages": [{"clip": f"P{k + 1}", "texte": (plans[k].get("textes") or {}).get(code, {}).get("texte", "")}
                       for k in ks], "clips_utilises": list(clips)}
    try:
        verdicts = script.match(sc, clips, code, gemini=gemini)
    except Exception:
        return []
    return [f"Plan {k + 1} : la phrase ne se voit pas dans son image ({a['pourquoi'] or 'autre chose a l ecran'}) : "
            f"reecris la phrase pour qu'elle commente ce qu'on voit, ou change l'image pour montrer ce qu'elle dit."
            for k, a in zip(ks, verdicts) if a["note"] == "non" or (a["note"] == "moyen" and k == 0)]


def critique(bundle: Dict, codes: List[str], gemini=None, recit: Optional[str] = None) -> Dict:
    """The stronger model re-reads for retention, language, images and facts;
    on failure (or if it broke the structure) the bundle comes back unchanged."""
    regles = " ; ".join(f"{c} : {LANG_RULES.get(c, LANG_RULES['fr'])}" for c in codes)
    try:
        r = (gemini or _gemini())._generate_content(
            [{"text": CRITIQUE_PROMPT.format(bundle=json.dumps(_public(bundle), ensure_ascii=False, indent=1),
                                             regles=regles) + ("\n" + recit if recit else "")}],
            max_tokens=24000, timeout=240, temperature=0.3)
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
    return {"plans": [{k: p.get(k) for k in ("role", "image", "idee", "plans_modele", "annotation", "textes")} for p in bundle["plans"]],
            "meta": bundle.get("meta") or {}}


def normalise(r, codes: List[str]) -> Dict:
    if not isinstance(r, dict) or "error" in r or not isinstance(r.get("plans"), list):
        from gemini_ai_generator import plain_error
        raise ScriptError(plain_error(r) or f"Storyboard inutilisable : {str(r)[:200]}")
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
                      "idee": " ".join(str(p.get("idee") or "").split())[:160],     # the idea in English (adaptation/vision)
                      "plans_modele": [int(i) for i in p.get("plans_modele") or [] if isinstance(i, (int, float))],
                      "annotation": clean_annotation(p.get("annotation")), "textes": t})
    meta = {}
    raw_meta = r.get("meta") if isinstance(r.get("meta"), dict) else {}
    for c in codes:
        m = raw_meta.get(c) if isinstance(raw_meta.get(c), dict) else {}
        meta[c] = {"titre": str(m.get("titre") or "").strip()[:100], "description": str(m.get("description") or "").strip(),
                   "tags": [str(x).strip() for x in m.get("tags") or [] if str(x).strip()][:15]}
    out = {"plans": plans, "meta": meta}
    durations(out, codes)
    return out


def clean_annotation(a) -> Optional[Dict]:
    """{"type": "fleche" | "cercle", "cible": "…"} or None."""
    if not isinstance(a, dict) or not str(a.get("cible") or "").strip():
        return None
    kind = str(a.get("type") or "").lower().replace("è", "e").strip()
    return {"type": kind if kind in ("fleche", "cercle") else "fleche", "cible": " ".join(str(a["cible"]).split())[:120]}


def seconds(text: str, code: str) -> float:
    return round(len(text) / lang_of(code)["chars_per_second"], 1)


def durations(bundle: Dict, codes: List[str]) -> None:
    """Each plan needs a clip at least as long as its longest text, in any language."""
    for p in bundle["plans"]:
        p["duree"] = round(max([seconds(p["textes"][c]["texte"], c) for c in codes if c in p["textes"]] or [0]) + 0.3, 1)


LENGTH_AIM = 33.0                 # seconds of voice a too long storyboard is cut down to (TOTAL_S: aim 25-35)
LENGTH_FIX = ("DUREE IMPOSEE : la voix doit tenir en 25 a 35 secondes, raccourcis les phrases. Raccourcir l'accroche ne "
              "supprime JAMAIS son chiffre frappant (\"10 presents sur 160\") : enleve plutot un autre mot.")

FACTS_PROMPT = """Faits verifies (les SEULS vrais pour cette video, chacun vient d'une page web) :
{faits}

Phrases d'un script de Short (plan | langue | phrase) :
{phrases}

Pour CHAQUE phrase : affirme-t-elle un fait, un chiffre, une cause, une action ou un nom qui n'est PAS dans les faits
verifies, ou qui les CONTREDIT (ex. les faits disent que les cameras n'ont pas pu etre utilisees, la phrase dit qu'ils
ont trompe les cameras) ? Une formulation, une image, une question ou un resume fidele ne sont pas des fautes.
JSON uniquement : {{"fautes": [{{"plan": 1, "langue": "ar", "quoi": "ce qui n'est pas dans les faits, en francais"}}]}}"""


def fact_check(bundle: Dict, codes: List[str], facts: List[str], gemini=None) -> Dict[Tuple[int, str], str]:
    """{(plan index, language): what a sentence says beyond the verified facts} — every sentence of every language
    in ONE call (about 1 cent, made again after each rewrite). Empty without facts, or when the check itself fails —
    then the bundle says so (adaptation/secours: « not checked », not « no fault »)."""
    from adaptation import secours
    secours.mark(bundle, "faits")
    if not facts:
        return {}
    lines = [f"{k} | {c} | {((p.get('textes') or {}).get(c) or {}).get('texte', '')}"
             for k, p in enumerate(bundle.get("plans") or [], 1) for c in codes]
    try:
        r = (gemini or _gemini())._generate_content([{"text": FACTS_PROMPT.format(
            faits="\n".join(f"- {f}" for f in facts), phrases="\n".join(lines))}], max_tokens=4000, timeout=90,
            temperature=0.0)
    except Exception as e:
        r = {"error": str(e)}
    if secours.failed(r) or "fautes" not in r:
        secours.mark(bundle, "faits", f"pas faite ({secours.why(r)}) : relis toi-même les chiffres et les noms.")
        return {}
    out = {}
    for f in ((r or {}).get("fautes") or []) if isinstance(r, dict) else []:
        try:
            k, c = int(f.get("plan")) - 1, str(f.get("langue") or codes[0])
        except (TypeError, ValueError, AttributeError):
            continue
        if 0 <= k < len(bundle.get("plans") or []) and c in codes and str(f.get("quoi") or "").strip():
            out[(k, c)] = str(f["quoi"]).strip()[:200]
    return out


def mark_facts(bundle: Dict, found: Dict[Tuple[int, str], str]) -> Dict:
    """The check's faults written on their plans ("hors_faits": {language: what}), the old ones cleared."""
    for k, p in enumerate(bundle.get("plans") or []):
        marks = {c: q for (i, c), q in found.items() if i == k}
        if marks:
            p["hors_faits"] = marks
        else:
            p.pop("hors_faits", None)
    return bundle


def total_seconds(bundle: Dict, code: str) -> float:
    return sum(seconds(((p.get("textes") or {}).get(code) or {}).get("texte", ""), code) for p in bundle.get("plans") or [])


def length_budgets(bundle: Dict, codes: List[str]) -> str:
    """For a language whose voice is too long, the most each plan may say (its share of LENGTH_AIM): given with the
    fix from the start — measured, asked only "25 to 35 s", Gemini's fixes still ran 38 to 48 s (RESULTATS_MODELES.md)."""
    out = []
    for c in codes:
        texts = [((p.get("textes") or {}).get(c) or {}).get("texte", "") for p in bundle.get("plans") or []]
        total = sum(seconds(t, c) for t in texts)
        if total <= TOTAL_S[1]:
            continue
        f = LENGTH_AIM / total
        out.append(f"[{c}] la voix fait environ {total:.0f} s, il faut 25 a 35 s : " + ", ".join(
            f"plan {k} : {max(15, int(len(t) * f))} caracteres au plus" for k, t in enumerate(texts, 1) if t) + ".")
    return (" Longueurs : " + " ".join(out) + " Coupe des mots, garde chaque fait et chaque chiffre avec son unite.") if out else ""


RATE = {"par", "per", "chaque", "كل", "لكل"}       # "35 grammes PAR kilogramme": the unit that gives the number its meaning


def _stem(w: str) -> str:
    for pre in ("بال", "وال", "لل", "ال"):
        if w.startswith(pre) and len(w) > len(pre) + 3:
            w = w[len(pre):]
            break
    return w[:5]


FILLERS = {"de", "d", "du", "des", "en", "plus", "environ", "من", "نحو", "حوالي"}


def _unit(after: List[str]) -> Optional[str]:
    """The word a number counts ("130 litres", "35 غراماً", "240 %"), past the small words."""
    return next((w for w in after if w not in FILLERS and w != "."), None)


def _same_word(a: str, b: str) -> bool:
    a, b = _stem(a), _stem(b)
    n = min(len(a), len(b))
    return n >= 1 and a[:max(n, 1)] == b[:max(n, 1)] and (n >= 3 or a == b)


def lost_numbers(before: Dict, after: Dict, codes: List[str], facts: List[str]) -> List[str]:
    """A sourced number of the draft (one of the facts) that a re-read or a fix DISTORTED, in French: changed for
    another of the same unit ("130 litres" → "plus de 100 litres"), or kept but cut from what gives it its meaning
    ("35 grammes par kilogramme" → "35 grammes"). Moved, in words or in digits, or a fact left out altogether
    (choosing what to tell is the re-read's job, measured on RESULTATS_MODELES.md): fine. Only numbers of the
    facts: a doubtful one the re-read changed must stay changed."""
    from adaptation import nombres
    sourced = set().union(*(nombres.values(f) for f in facts)) if facts else set()
    out = []
    for c in codes:
        texts_after = [((p.get("textes") or {}).get(c) or {}).get("texte", "") for p in after.get("plans") or []]
        found_after = [(m, nxt) for t in texts_after for m, nxt in nombres.occurrences(t)]
        for k, p in enumerate(before.get("plans") or [], 1):
            text = ((p.get("textes") or {}).get(c) or {}).get("texte", "")
            for n, nxt in nombres.occurrences(text):
                if (n <= 10 and n == int(n)) or not any(nombres.same(n, x) for x in sourced):
                    continue
                where = [t for t in texts_after if any(nombres.same(n, v) for v in nombres.values(t))]
                unit = _unit(nxt)
                if not where:
                    other = next((m for m, nxt2 in found_after if unit and not any(nombres.same(m, x) for x in sourced)
                                  and _unit(nxt2) and _same_word(_unit(nxt2), unit)), None)     # not another sourced fact
                    if other is not None:
                        out.append(f"Plan {k} [{c}] : le fait sourcé dit {n:g} {unit}, le texte dit maintenant {other:g} : "
                                   f"remets {n:g} (« {text} »).")
                    continue
                rate = next((nxt[i + 1] for i, w in enumerate(nxt[:-1]) if w in RATE), None)
                if rate and not any(_same_word(w, rate) for t in where for w in nombres.tokens(t)):
                    out.append(f"Plan {k} [{c}] : le chiffre {n:g} a perdu son unité ({nxt[nxt.index(rate) - 1]} {rate}) : "
                               "remets-la, sinon le chiffre n'a plus de sens.")
    return out


def script_for(bundle: Dict, code: str) -> Dict:
    """One language's script, in the format the rest of the app uses (no clips yet)."""
    m = (bundle.get("meta") or {}).get(code) or {}
    return {"titre": m.get("titre", ""), "description": m.get("description", ""), "tags": m.get("tags", []),
            "passages": [{"clip": "", **p["textes"][code], "annotation": p.get("annotation"), "effets": p.get("effets")}
                         for p in bundle["plans"]],
            "corrections": bundle.get("corrections", [])}


UNFILMABLE = re.compile(r"\banimation|sch[ée]ma|infographi|graphique|mod[ée]lisation|\b3d\b|dessin anim|illustration", re.I)


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
        if texte.lstrip().startswith(("…", "...")):
            out.append(f"Plan {k} : la phrase commence par « … » : elle continue celle d'avant, écris une phrase complète.")
        s = seconds(texte, code)
        if k == 1 and s > HOOK_MAX_S:
            out.append(f"Plan 1 : accroche trop longue ({s} s de voix, viser 2 à 3 s).")
        elif s > PLAN_MAX_S:
            out.append(f"Plan {k} : phrase trop longue ({s} s de voix) : une image aussi longue est rare, coupe-la en deux.")
        if (p.get("hors_faits") or {}).get(code):
            out.append(f"Plan {k} : dit une chose absente des faits vérifiés ({p['hors_faits'][code]}) : corrige la phrase.")
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


ADAPT_PROMPT = """Storyboard d'un Short (JSON) :
{bundle}
Le plan {num} ({role}) n'a pas de video : personne n'a filme "{image}".
Voici des images DEJA TROUVEES et verifiees, disponibles :
{options}
Choisis l'option qui sert le mieux l'histoire a cet endroit, et REECRIS seulement le plan {num} pour qu'il colle a cette
image : le spectateur entend la phrase EN REGARDANT l'image, elle dit donc ce qu'on y VOIT (ou le commente) et ne
parle d'aucune action absente de l'image (pas d'oeufs sur un thon qui nage seul). Garde le role dans l'histoire et ce
que le plan apprend quand l'image le permet ; l'enchainement avec les plans voisins reste naturel, phrases completes,
dans chaque langue ({langues}), AU PLUS : {longueurs}. Ne change aucun autre plan.{encore}
JSON uniquement : {{"choix": numero de l'option, "image": "ce qu'on voit dans l'option choisie",
  "textes": {{{exemple}}}}}"""


def adapt_to(bundle: Dict, k: int, options: List[Dict], codes: List[str], gemini=None) -> Tuple[int, Dict]:
    """Plan k rewritten around one of the images already found: (option index, new plan)."""
    if not options:
        raise ScriptError("Aucune image trouvée à proposer : vérifie d'abord quelques vidéos.")
    exemple = ", ".join(f'"{c}": {{"bandeau": "", "texte": "", "mots_cles": [""]}}' for c in codes)
    listing = "\n".join(f"{n}. {o['vu']}" for n, o in enumerate(options, 1))
    plan = bundle["plans"][k]
    limit = HOOK_MAX_S if k == 0 else PLAN_MAX_S      # measured: an adapted hook of 4.6 s blocked the download
    longueurs = ", ".join(f"{int(limit * lang_of(c)['chars_per_second']) - 2} caracteres en {c}" for c in codes)
    encore = ""
    for _attempt in range(2):
        r = (gemini or _gemini())._generate_content([{"text": ADAPT_PROMPT.format(
            bundle=json.dumps(_public(bundle), ensure_ascii=False, indent=1), num=k + 1, role=plan["role"],
            image=plan["image"], options=listing, langues=", ".join(codes), exemple=exemple, longueurs=longueurs,
            encore=encore)}], max_tokens=4000, timeout=120, temperature=0.5)
        try:
            choice = int(r.get("choix")) - 1
        except (TypeError, ValueError, AttributeError):
            from gemini_ai_generator import plain_error
            raise ScriptError(plain_error(r) or f"Réponse inutilisable : {str(r)[:160]}")
        if not 0 <= choice < len(options):
            raise ScriptError("L'IA a choisi une image qui n'existe pas.")
        # the old plan's arrow pointed at what its image showed (measured: "the white cloud" kept over a tuna swimming)
        fixed = normalise({"plans": [{**plan, "image": r.get("image") or options[choice]["vu"], "textes": r.get("textes"),
                                      "annotation": None}],
                           "meta": {}}, codes)
        if not fixed["plans"]:
            raise ScriptError("L'IA n'a pas réécrit le plan.")
        long = [c for c in codes if seconds(fixed["plans"][0]["textes"][c]["texte"], c) > limit]
        if not long:
            break
        encore = f"\nTa premiere reponse etait trop longue en {', '.join(long)} : respecte ces longueurs."
    return choice, fixed["plans"][0]
