"""
« Idée d'abord » — a Short from an idea, without a model video.

Script d'abord reads a model Short into a sheet (subject, question, plans,
facts) and everything after — angles, storyboard, footage search, voice,
render — only ever sees that sheet. Here the sheet is built from an idea:

1. what people type on YouTube about it (the search box suggestions,
   ds=yt) — free, best effort: the app goes on without them;
2. facts found with Google Search (Gemini grounding): each sentence is kept
   with the pages Google says support it. A sentence no page supports is
   dropped — never written into a video; one backed only by forums or social
   networks is "fragile" (shown, not used as a fact);
3. a plan of filmable shots written from the sourced facts only.
"""

import os
import re
from typing import Callable, Dict, List, Optional
from urllib.parse import urlparse

import requests

MIN_FACTS = 3
WEAK_SOURCES = ("reddit.", "quora.", "facebook.", "tiktok.", "youtube.", "pinterest.", "instagram.", "x.com",
                "twitter.", "medium.com", "forum", "answers.", "blogspot.")


class IdeeError(RuntimeError):
    pass


def _gemini():
    from gemini_ai_generator import GeminiAIGenerator
    return GeminiAIGenerator(api_key=os.getenv("GEMINI_API_KEY"))


# ---------------------------------------------------------------- 1. what people search

def youtube_suggestions(text: str, lang: str, get: Callable = requests.get) -> List[str]:
    """What YouTube's search box suggests for the idea (what people really
    type, in that language), closest to the idea first. The box completes the
    START of a search: a whole sentence gets nothing (measured: "pourquoi les
    avions de ligne volent…" → none, "pourquoi les avions" → 9, "pourquoi les
    avions de" → 1, off topic), so every shorter start is asked and the
    suggestions sharing the most words with the idea come first. Unofficial
    and free: [] whenever it doesn't answer."""
    words = text.split()
    tries = list(dict.fromkeys([" ".join(words[:n]) for n in [len(words), 6, 5, 4, 3, 2]
                                if n <= len(words) and (n >= 2 or n == len(words))]
                               + [" ".join(words[2:n]) for n in (5, 4) if len(words) >= n]))   # the subject alone
    found: List[str] = []
    for q in tries:
        try:
            r = get("https://suggestqueries.google.com/complete/search",
                    params={"client": "firefox", "ds": "yt", "hl": lang, "q": q}, timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception:
            break
        found += [str(x) for x in (data[1] if isinstance(data, list) and len(data) > 1 else []) if str(x) not in found]
    # the subject is in the words AFTER the first two ("pourquoi les", "لماذا لا"): a suggestion sharing
    # none of them is off topic (measured: « لماذا لا » → TikTok, Play Store…)
    words_of = lambda x: set(re.findall(r"\w+", x.lower()))
    core = {w for w in re.findall(r"\w+", " ".join(words[2:]).lower()) if len(w) > 2} or words_of(text)
    kept = [x for x in found if core & words_of(x)]
    return sorted(kept, key=lambda x: len(core & words_of(x)), reverse=True)[:10]


# ---------------------------------------------------------------- 2. facts, each with its pages

RESEARCH_PROMPT = """Recherche sur le web (Google) pour un YouTube Short sur cette idee : {idee}
Ecris 8 faits verifiables, precis et surprenants (chiffres, dates, noms, causes), un par ligne commencant par "- ",
chacun UNE phrase courte et autonome, en {langue}. Seulement ce que les pages trouvees disent, rien de memoire."""

LANG_NAMES = {"fr": "francais", "ar": "arabe", "en": "anglais"}


def resolve(url: str, head: Callable = requests.head) -> str:
    """Google's grounding links are redirects (vertexaisearch…): the real page
    they lead to, to show and open. The redirect itself when that fails."""
    if "vertexaisearch.cloud.google.com" not in (url or ""):
        return url
    try:
        return head(url, allow_redirects=False, timeout=10).headers.get("location") or url
    except Exception:
        return url


def _clean(line: str) -> str:
    return re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()


def _weak(source: Dict) -> bool:
    where = (source.get("titre") or "") + " " + (urlparse(source.get("url") or "").netloc or "")
    return any(w in where.lower() for w in WEAK_SOURCES)


def research(idea: str, lang: str, gemini=None, resolve: Callable = resolve) -> List[Dict]:
    """[{"fait", "sources": [{"titre", "url"}], "fragile"}] — only sentences
    Google ties to at least one page; fragile when all those pages are forums
    or social networks."""
    r = (gemini or _gemini()).grounded(RESEARCH_PROMPT.format(idee=idea, langue=LANG_NAMES.get(lang, "francais")))
    if not isinstance(r, dict) or r.get("error"):
        raise IdeeError(f"Recherche des faits impossible : {(r or {}).get('error') if isinstance(r, dict) else r}")
    lines = [_clean(x) for x in (r.get("text") or "").splitlines()]
    facts = []
    for line in [x for x in lines if len(x) > 5]:
        pages = {}
        for s in r.get("supports") or []:
            seg = _clean(s.get("text") or "")
            if seg and (seg in line or line in seg):
                for src in s.get("sources") or []:
                    pages.setdefault(src.get("uri"), src)
        if not pages:
            continue                    # nothing Google read says it: never in the video
        sources = [{"titre": s.get("title") or urlparse(s.get("uri") or "").netloc, "url": resolve(s.get("uri") or "")}
                   for s in pages.values()]
        facts.append({"fait": line, "sources": sources, "fragile": all(_weak(s) for s in sources)})
    return facts


# ---------------------------------------------------------------- 3. the sheet (same shape as a model Short's)

PLAN_PROMPT = """On prepare un YouTube Short explicatif (voix off sur de VRAIES images filmees) a partir d'une idee.
Idee : {idee}
Ce que les gens tapent sur YouTube a ce sujet (pour choisir la question et les mots qui accrochent) : {suggestions}
Faits VERIFIES, les seuls utilisables (chacun vient d'une page trouvee) :
{faits}
Ecris le plan de la video, comme si on analysait un Short viral sur ce sujet :
- 6 a 8 plans : accroche, mise en place, explication, suspense, chute ;
- "visuel" : une scene REELLE et concrete, qu'on trouve filmee sur YouTube (pas d'animation, pas de schema) ;
- "paroles" : l'idee de ce qui est dit, en n'utilisant QUE les faits ci-dessus.
Ecris "sujet", "question" et chaque "visuel" EN FRANCAIS, quelle que soit la langue de l'idee et des faits (une image
sert a toutes les langues de la video) ; "paroles" peut rester dans la langue des faits.
JSON uniquement :
{{"sujet": "une phrase", "question": "la question a laquelle la video repond",
 "ton": "spectaculaire | calme | drole | explicatif", "duree_s": 35,
 "recherche_courte": "1 ou 2 mots anglais du theme",
 "plans": [{{"role": "accroche", "visuel": "", "paroles": ""}}]}}"""


def plan(idea: str, facts: List[str], suggestions: List[str], gemini=None) -> Dict:
    r = (gemini or _gemini())._generate_content([{"text": PLAN_PROMPT.format(
        idee=idea, suggestions="; ".join(suggestions) or "aucune",
        faits="\n".join(f"- {f}" for f in facts))}], max_tokens=6000, timeout=120, temperature=0.6)
    if not isinstance(r, dict) or r.get("error") or not isinstance(r.get("plans"), list) or not r["plans"]:
        raise IdeeError(f"Plan de la vidéo inutilisable : {str(r)[:200]}")
    return r


def build(idea: str, lang: str, gemini=None, resolve: Callable = resolve) -> Dict:
    """The sheet the rest of Script d'abord uses, made from an idea."""
    g = gemini or _gemini()
    suggestions = youtube_suggestions(idea, lang)
    facts = research(idea, lang, gemini=g, resolve=resolve)
    if sum(not f["fragile"] for f in facts) < MIN_FACTS:
        # one search is uneven (measured on an Arabic idea: 2 sourced facts, then 8 for the same search): once more
        known = {f["fait"] for f in facts}
        facts += [f for f in research(idea, lang, gemini=g, resolve=resolve) if f["fait"] not in known]
    solid = [f["fait"] for f in facts if not f["fragile"]]
    if len(solid) < MIN_FACTS:
        raise IdeeError(f"Pas assez de faits sourcés trouvés sur le web pour cette idée ({len(solid)} sur {MIN_FACTS} "
                        "nécessaires) : précise-la, ou choisis un sujet plus documenté. Rien n'est inventé.")
    sheet = plan(idea, solid, suggestions, gemini=g)
    sheet.update(origine="idee", idee=idea, faits=solid, faits_douteux=[f["fait"] for f in facts if f["fragile"]],
                 faits_sources=facts, suggestions_youtube=suggestions, script_complet="", credits=[],
                 publicite=None, plans_pub=[], a_chercher=[])
    return sheet
