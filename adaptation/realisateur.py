"""
The AI director of the montage pro — what a human editor decides in his head before searching: « how do I show
this sentence? » (the user's remarks of 2026-11-09 on the lab's Shorts: a location shown without a map, « shaped
like a moussem tent » without the stadium's render nor a tent, « the agents paint red numbers » searched only in
French, « this ceiling traps the Earth's heat » shown as one more plane).

For every sentence, one call chooses the KIND of picture and writes 1 or 2 visuals to find:
  reel         the real place or event (news): its footage, searched in the country's language too
  idee         a picture that conveys the meaning when the exact scene does not exist
  comparaison  « shaped like », « as big as »: the thing AND what it is compared to (2 visuals)
  projet       something designed or not built yet: its official render, model or plans
  chiffre / carte / schema
               a figure, a place to locate, a mechanism: noted as a graphic to draw ("graphique") — until the app
               draws them, a footage visual conveying the idea is searched as well
Each visual: "image" (French, what the video shows — the search and the checks), "idee" (English meaning — the
meaning search, adaptation/vision), short searches in English and in the country's language.
One call, in place of the search-words call it replaces (finder.plan_queries).

v2 (lab of 2026-11-10, docs/recherches/labo_realisateur.md): an editor's guide (what to show for each kind of
sentence, the real over the generic, the voice's order, the precise details, the visible result of a rare action),
up to 4 visuals for a sentence in several times, each with the word it starts on ("mot"), and the named clubs,
companies and institutions searched in their official YouTube channel too ("entite", checked by channels()).
"""

import json
import re
from typing import Dict, List, Optional

KINDS = ("reel", "idee", "comparaison", "projet", "chiffre", "carte", "schema")
GRAPHICS = ("chiffre", "carte", "schema")
MAX_VISUALS = 4         # a sentence in several times (a list of clubs, a comparison): one visual a time
ENTITY_KINDS = ("club", "entreprise", "institution")

PROMPT = """Tu es le realisateur d'un YouTube Short (voix off sur des images trouvees en video). Sujet : {sujet}
Famille : {famille}. Faits verifies (pour savoir ou et quoi) : {faits}
Les phrases dites par la voix :
{phrases}

Pour CHAQUE phrase, decide COMMENT la montrer, comme un monteur pro (le sens, l'emotion, l'attention ; jamais une
image qui contredit la phrase ; varie les images d'une phrase a l'autre) :
- "reel" : la phrase raconte un fait reel (actualite) : les vraies images du lieu ou de l'evenement ;
- "idee" : la scene exacte n'existe pas en video : une image qui fait passer le SENS (« les familles recoivent les
  cles » -> des immeubles neufs, une main qui tend des cles) ;
- "comparaison" : « en forme de », « aussi grand que », « depasse », « comme » : 2 visuels, la chose ET ce a quoi on
  la compare, dans l'ordre de la phrase (le stade, puis une vraie tente marocaine de moussem) ;
- "projet" : quelque chose de dessine ou pas encore construit : son rendu 3D officiel, sa maquette, ses plans ;
- "chiffre" : un chiffre a frapper (« 370 millions », « deux fois plus ») ; "carte" : un lieu a situer (« a Mansouria,
  pres de Casablanca ») ; "schema" : un mecanisme invisible (« emprisonne la chaleur ») : l'app dessine le "graphique"
  (au plus 2 par video), ET donne quand meme un visuel video qui fait passer l'idee (si le graphique n'est pas fait).
  "graphique" selon le type (les mots a l'ecran dans la langue de la video, {langue}) :
    chiffre : {{"contenu": "ce qu'on voit", "valeur": "le nombre EXACTEMENT comme dans les faits, en chiffres (115000,
      54, 5.3)", "unite": "les mots apres le nombre (مقعد, مليار درهم, millions de tonnes)", "titre": "2-4 mots au-dessus,
      tires des faits, ou vide"}}
    carte : {{"contenu": "...", "lieu": "le lieu precis EN ANGLAIS pour une recherche de carte (Betoya Bay, Nador,
      Morocco)", "nom": "son nom a l'ecran", "pays": "le pays en anglais", "pays_nom": "le pays a l'ecran",
      "reperes": [{{"lieu": "une grande ville proche connue, en anglais", "nom": "son nom a l'ecran"}}] (1 ou 2),
      "chiffre": {{"valeur": "", "unite": ""}} ou null (un chiffre des faits sur ce lieu)}}
    schema : {{"contenu": "ce que le schema montre, etape par etape"}}
GUIDE DU MONTEUR (applique-le a chaque phrase, apres avoir lu TOUT le script : de quoi, ou, quand) :
1. Une phrase simple (une seule idee) : UN visuel. Une phrase a plusieurs TEMPS (deux idees, une liste de noms, une
   comparaison) : un visuel par temps, jusqu'a {max_visuels}, TOUJOURS dans l'ordre ou la voix les dit ; "mot" = le
   premier mot de la phrase (ecrit comme dans la phrase) ou ce visuel commence.
2. Ce qu'on montre selon ce que dit la phrase :
   - un lieu reel -> CE lieu (vue aerienne, facade, plan d'ensemble), pas un lieu qui lui ressemble ;
   - une personne nommee -> elle EN TRAIN de faire ce que dit la phrase (le MOMENT : match, discours, inauguration),
     jamais un portrait fige ; recherche = nom + contexte + annee, jamais le nom seul ;
   - un club, une equipe, une entreprise, une marque, une institution -> SES vraies images (ses supporters, son stade,
     son usine, son produit), cherchees aussi dans SA chaine YouTube officielle ("entite") ;
   - une liste de 2 a 4 noms -> un visuel court PAR NOM, dans l'ordre de la phrase (une seule liste par video) ;
   - une date passee, une epoque -> des images d'archives de CETTE epoque (jamais des images recentes pour un fait ancien) ;
   - une metaphore (« le poumon de la region ») -> ce qu'elle VEUT DIRE (l'activite reelle), jamais l'objet de la metaphore ;
   - une emotion, une consequence -> la reaction humaine ou la preuve concrete.
3. Le vrai bat le generique : si la phrase nomme une chose reelle et filmee, cherche CETTE chose ; une image generique
   (foule, drapeaux, bureau, rendu 3D vague) seulement pour une idee abstraite.
4. Garde les details precis de la phrase dans "image" (un nombre, les objets nommes : « les 32 escaliers geants et les
   jardins suspendus », pas « les facades du stade »).
5. Cherche ce qui existe en video : une action rare a filmer -> son RESULTAT visible (« les agents peignent des numeros
   rouges » -> des portes de baraques marquees de numeros rouges).
6. Jamais une image qui contredit la phrase ; varie les images d'une phrase a l'autre.
Chaque visuel :
- "mot" : voir 1 ;
- "image" : en francais, ce qu'on voit dans la video a trouver (concret, filmable, sans facon de filmer) ;
- "idee" : en ANGLAIS, 5 a 12 mots, ce que montrerait n'importe quelle video qui fait passer le SENS (generale) ;
- "anglais" : 2 recherches YouTube en anglais, courtes (2 a 5 mots), comme le titre d'une vraie video ;
- "pays" et "locales" : le pays ou une telle video a ete filmee et 2 recherches DANS SA LANGUE (en arabe pour le
  Maroc : les reportages marocains titrent en arabe ; vide si generique) ;
- "entite" : quand le visuel montre un club, une equipe, une entreprise, une marque ou une institution nommee :
  {{"nom": "son nom officiel, en lettres latines s'il en a un", "genre": "club|entreprise|institution",
  "chaine": "le @handle de sa chaine YouTube officielle si tu le connais, sinon vide", "requete": "2 a 5 mots a chercher
  DANS cette chaine, dans la langue de la chaine (une chaine marocaine : en arabe ou en francais comme ses titres)"}} ;
  sinon null.
JSON uniquement : {{"plans": [{{"phrase": 1, "type": "reel", "pourquoi": "court",
  "visuels": [{{"mot": "", "image": "", "idee": "", "anglais": ["", ""], "pays": "", "locales": ["", ""],
  "entite": null}}],
  "graphique": null}}]}}"""


def _phrases(p: Dict) -> List[str]:
    plans = (p.get("storyboard") or {}).get("plans") or []
    code = p["targets"][0]["language"] if p.get("targets") else "fr"
    out = []
    for pl in plans:
        t = pl.get("textes") or {}
        fr = (t.get("fr") or {}).get("texte")
        own = (t.get(code) or {}).get("texte")
        out.append(f"{own}" + (f"  (fr : {fr})" if fr and fr != own else ""))
    return out


def plan(p: Dict, gemini=None) -> Optional[List[Dict]]:
    """[{phrase, type, pourquoi, visuels: [{mot, image, idee, anglais, pays, locales, entite}], graphique}] — one per sentence,
    or None when the call fails (the search then goes on as before, one image a sentence)."""
    from adaptation import recits
    from adaptation.langs import lang as lang_of
    from adaptation.script import _gemini
    phrases = _phrases(p)
    if not phrases:
        return None
    ref = p.get("reference") or {}
    fam = p.get("famille_recit") or recits.find(p.get("recit")) or "explicatif"
    try:
        r = (gemini or _gemini())._generate_content([{"text": PROMPT.format(
            sujet=ref.get("sujet") or p.get("idee") or "", famille=recits.FAMILLES.get(fam, {}).get("label", fam),
            faits="; ".join(ref.get("faits") or [])[:1500],
            phrases="\n".join(f"{k}. {x}" for k, x in enumerate(phrases, 1)),
            langue=lang_of(p["targets"][0]["language"])["label"] if p.get("targets") else "francais",
            max_visuels=MAX_VISUALS)}],
            max_tokens=12000, timeout=150, temperature=0.4)
    except Exception:
        return None
    return clean(r, len(phrases), (p.get("storyboard") or {}).get("plans") or [])


def clean(r, n: int, sb_plans: List[Dict]) -> Optional[List[Dict]]:
    """The director's answer made safe: one entry per sentence, 1 to 4 visuals each (the storyboard's image when
    a sentence came back empty)."""
    if not isinstance(r, dict) or not isinstance(r.get("plans"), list):
        return None
    by = {}
    for x in r["plans"]:
        try:
            k = int(x.get("phrase")) - 1
        except (TypeError, ValueError, AttributeError):
            continue
        if 0 <= k < n and k not in by:
            by[k] = x
    out = []
    for k in range(n):
        x = by.get(k) or {}
        kind = x.get("type") if x.get("type") in KINDS else "idee"
        vis = []
        for v in (x.get("visuels") or [])[:MAX_VISUALS]:
            if not isinstance(v, dict) or not str(v.get("image") or "").strip():
                continue
            vis.append({"mot": " ".join(str(v.get("mot") or "").split())[:40],
                        "image": " ".join(str(v["image"]).split())[:200],
                        "idee": " ".join(str(v.get("idee") or "").split())[:160],
                        "anglais": [str(q).strip()[:60] for q in v.get("anglais") or [] if str(q).strip()][:3],
                        "pays": str(v.get("pays") or "")[:40],
                        "locales": [str(q).strip()[:60] for q in v.get("locales") or [] if str(q).strip()][:3],
                        "entite": _entity(v.get("entite"))})
        if not vis:                                 # the storyboard's own image, as before
            pl = sb_plans[k] if k < len(sb_plans) else {}
            vis = [{"mot": "", "image": pl.get("image") or "", "idee": pl.get("idee") or "", "anglais": [], "pays": "",
                    "locales": [], "entite": None}]
        g = x.get("graphique") if kind in GRAPHICS and isinstance(x.get("graphique"), (dict, str)) else None
        out.append({"phrase": k + 1, "type": kind, "pourquoi": str(x.get("pourquoi") or "")[:160], "visuels": vis,
                    "graphique": _graphic(g) if isinstance(g, dict) else ({"contenu": str(g)[:200]} if g else None)})
    return out


def _entity(e) -> Optional[Dict]:
    """A named club, company or institution: its name, its official channel's handle as the director guessed it
    (checked by channels()) and the words to search there."""
    if not isinstance(e, dict) or not str(e.get("nom") or "").strip():
        return None
    short = lambda x, n: " ".join(str(x or "").split())[:n]
    genre = short(e.get("genre"), 20)
    if genre not in ENTITY_KINDS:
        return None
    return {"nom": short(e["nom"], 80), "genre": genre, "chaine": short(e.get("chaine"), 60).lstrip("@"),
            "requete": short(e.get("requete"), 80)}


def _words(name: str) -> set:
    import unicodedata
    plain = unicodedata.normalize("NFKD", name.lower())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return {w for w in re.findall(r"\w{2,}", plain)} - {"officiel", "official", "officielle", "tv", "the", "de", "du", "la", "le"}


def same_name(name: str, channel: str) -> bool:
    """Is this channel named after the entity? 3/4 of the entity's words in the channel's name, and 3/4 of the
    channel's words (those in the entity's alphabet) in the entity's name: « Wydad Athletic Club » is
    « Wydad Athletic Club ● نادي الوداد الرياضي », not « Wydad Athletic Fassi » nor « HAMDI | أمسية كروية »;
    « AS FAR » is not « as far as the corners »."""
    arabic = lambda w: bool(re.search(r"[؀-ۿ]", w))
    a = _words(name)
    b = {w for w in _words(channel) if arabic(w) == any(arabic(x) for x in a)}
    return bool(a) and bool(b) and len(a & b) / len(a) >= 0.75 and len(a & b) / len(b) >= 0.75


def channels(realisation: Optional[List[Dict]], info=None, find=None, report=None) -> int:
    """Each entity's official channel, checked: the director's @handle when it exists and is named after the
    entity (7 of its 12 guesses existed in the lab), else the channel search's best named after it, the one with
    the most subscribers (it found the right one in the 5 cases tested); none found: no channel search for it.
    Sets entite["chaine_ok"] ("channel/UC…") and entite["chaine_nom"]; returns how many were found."""
    from adaptation import finder
    info, find = info or finder.channel_info, find or finder.search_channels
    report = report or (lambda phase: None)
    seen, found = {}, 0
    for e in realisation or []:
        for v in e["visuels"]:
            ent = v.get("entite")
            if not ent:
                continue
            key = ent["nom"].lower()
            if key not in seen:
                report(f"chaîne officielle : {ent['nom']}")
                best = None
                got = info(ent["chaine"]) if ent["chaine"] else None
                if got and same_name(ent["nom"], got["nom"]):
                    best = got
                else:
                    named = [c for c in find(ent["nom"]) if same_name(ent["nom"], c["nom"])]
                    best = max(named, key=lambda c: c.get("abonnes") or 0, default=None)
                seen[key] = best
            best = seen[key]
            if best:
                ent["chaine_ok"], ent["chaine_nom"] = best["id"], best["nom"]
                found += 1
            else:
                ent.pop("chaine_ok", None)
                ent.pop("chaine_nom", None)
    return found


def _graphic(g: Dict) -> Dict:
    """The director's graphic kept to its fields, each short (adaptation/graphiques draws it)."""
    short = lambda x, n: " ".join(str(x or "").split())[:n]
    out = {"contenu": short(g.get("contenu"), 300)}
    for key, n in (("valeur", 20), ("unite", 40), ("titre", 40), ("lieu", 120), ("nom", 40), ("pays", 60),
                   ("pays_nom", 30)):
        if g.get(key) not in (None, ""):
            out[key] = short(g[key], n)
    reps = [{"lieu": short(r.get("lieu"), 120), "nom": short(r.get("nom"), 30)}
            for r in g.get("reperes") or [] if isinstance(r, dict) and r.get("lieu") and r.get("nom")][:2]
    if reps:
        out["reperes"] = reps
    c = g.get("chiffre")
    if isinstance(c, dict) and c.get("valeur") not in (None, ""):
        out["chiffre"] = {"valeur": short(c["valeur"], 20), "unite": short(c.get("unite"), 30)}
    return out


def wanted(realisation: List[Dict], sb_plans: List[Dict]) -> List[Dict]:
    """The visuals as « scenes to find » for the search (finder.suggest): each with the sentence said over it and
    its English searches (the local ones go through local_of), and its checked official channel ("chaine")."""
    out = []
    for e in realisation:
        k = e["phrase"] - 1
        pl = sb_plans[k] if k < len(sb_plans) else {}
        textes = pl.get("textes") or {}
        phrase = next((textes[c]["texte"] for c in ("fr", *textes) if c in textes and textes[c].get("texte")), "")
        for v in e["visuels"]:
            ent = v.get("entite") or {}
            out.append({"scene": v["image"], "plans": [i - 1 for i in pl.get("plans_modele") or [] if i >= 1],
                        "indices": "", "phrase": phrase, "phrase_n": e["phrase"],
                        "recherches": v["anglais"] or [" ".join(v["image"].split()[:8])],
                        **({"chaine": {"id": ent["chaine_ok"], "nom": ent.get("chaine_nom") or ent["nom"],
                                       "requete": ent["requete"] or ent["nom"]}} if ent.get("chaine_ok") else {})})
    return out


def local_of(realisation: List[Dict]) -> Dict[int, Dict]:
    """{scene index: {pays, langue, recherches}} — the searches in the country's language (finder.suggest's local)."""
    out, i = {}, 0
    for e in realisation:
        for v in e["visuels"]:
            if v["locales"]:
                out[i] = {"pays": v["pays"], "langue": "", "recherches": v["locales"]}
            i += 1
    return out


def ideas(realisation: Optional[List[Dict]]) -> Optional[List[str]]:
    """Each sentence's meaning in English for the meaning search: its visuals' ideas together."""
    if not realisation:
        return None
    return [", ".join(v["idee"] for v in e["visuels"] if v.get("idee")) for e in realisation]   # "" = none for it


def summary(realisation: Optional[List[Dict]]) -> str:
    return json.dumps([{"phrase": e["phrase"], "type": e["type"], "visuels": [v["image"] for v in e["visuels"]],
                        "graphique": e.get("graphique")} for e in realisation or []], ensure_ascii=False)


# ---------------------------------------------------------------- the person's say (« Le plan du réalisateur »)

def key(p: Dict) -> str:
    """What the plan was made for: the sentences. The plan is made again only when they change (2026-11-14: every
    search made a new plan — 2 graphics one time, none the next — and the person's own versions would be lost)."""
    return json.dumps(_phrases(p), ensure_ascii=False)


def is_current(p: Dict) -> bool:
    return bool(p.get("realisation")) and p.get("realisation_cle") == key(p)


USER_PROMPT = """Tu es le realisateur d'un YouTube Short (voix off sur des images trouvees en video). Sujet : {sujet}
Faits verifies : {faits}
La phrase {n} dite par la voix : {phrase}
Ce que tu avais prevu pour elle : {avant}
Le MONTEUR HUMAIN veut autre chose, avec ses mots : « {souhait} »{genre}
Reecris le plan de CETTE phrase pour faire EXACTEMENT ce qu'il demande (ses mots priment ; garde ce qu'il ne change pas).
Types : "reel" (vraies images d'un lieu, d'un evenement), "idee" (une image qui fait passer le sens), "comparaison",
"projet" (rendu 3D, maquette), "chiffre" (compteur anime), "carte" (lieu ou trajet a situer), "schema" (mecanisme).
Pour "chiffre", "carte" ou "schema", ecris aussi le "graphique" (les mots a l'ecran en {langue}) :
  chiffre : {{"contenu": "", "valeur": "le nombre en chiffres", "unite": "", "titre": ""}}
  carte : {{"contenu": "", "lieu": "le lieu EN ANGLAIS", "nom": "son nom a l'ecran", "pays": "en anglais", "pays_nom": "",
    "reperes": [{{"lieu": "une ville EN ANGLAIS", "nom": "son nom a l'ecran"}}] (1 ou 2 : pour un trajet, ses deux bouts),
    "chiffre": {{"valeur": "", "unite": ""}} ou null}}
  schema : {{"contenu": "ce que le schema montre, etape par etape"}}
et quand meme 1 visuel video qui fait passer l'idee.
Chaque visuel : "mot" (le mot de la phrase ou il commence, ecrit comme dans la phrase), "image" (en francais, ce qu'on
voit, concret et filmable), "idee" (en ANGLAIS, 5 a 12 mots, le sens general), "anglais" (2 recherches YouTube courtes en
anglais), "pays" et "locales" (le pays et 2 recherches dans sa langue, en arabe pour le Maroc ; vide si generique),
"entite" (null, ou {{"nom": "", "genre": "club|entreprise|institution", "chaine": "", "requete": ""}}). 1 a 4 visuels.
JSON uniquement : {{"plans": [{{"phrase": {n}, "type": "reel", "pourquoi": "court", "visuels": [{{"mot": "", "image": "",
"idee": "", "anglais": ["", ""], "pays": "", "locales": ["", ""], "entite": null}}], "graphique": null}}]}}"""

GENRES = {"reel": "vraies images", "carte": "une carte animee", "chiffre": "un chiffre anime", "schema": "un schema anime",
          "idee": "une image d'idee", "projet": "un rendu 3D ou une maquette", "comparaison": "une comparaison"}


def from_user(p: Dict, phrase: int, souhait: str, genre: Optional[str] = None, gemini=None) -> Dict:
    """One sentence's plan rewritten from what the person typed (and the kind they ticked): the director's own
    format, so the search, the graphics and the editor take it as theirs. Raises ValueError when it can't."""
    from adaptation import recits  # noqa: F401  (same imports as plan())
    from adaptation.langs import lang as lang_of
    from adaptation.script import _gemini
    phrases = _phrases(p)
    if not 1 <= phrase <= len(phrases):
        raise ValueError("Phrase inconnue.")
    souhait = " ".join(str(souhait or "").split())[:400]
    if not souhait:
        raise ValueError("Écris ce que tu veux pour cette phrase.")
    ref = p.get("reference") or {}
    before = next((e for e in p.get("realisation") or [] if e.get("phrase") == phrase), {})
    r = (gemini or _gemini())._generate_content([{"text": USER_PROMPT.format(
        sujet=ref.get("sujet") or p.get("idee") or "", faits="; ".join(ref.get("faits") or [])[:1500], n=phrase,
        phrase=phrases[phrase - 1], avant=summary([before]) if before else "rien", souhait=souhait,
        genre=f"\nIl a coche : {GENRES[genre]}." if genre in GENRES else "",
        langue=lang_of(p["targets"][0]["language"])["label"] if p.get("targets") else "francais")}],
        max_tokens=4000, timeout=90, temperature=0.3)
    if isinstance(r, dict) and isinstance(r.get("plans"), list):
        r["plans"] = [dict(x, phrase=phrase) for x in r["plans"][:1] if isinstance(x, dict)]
    got = clean(r, len(phrases), (p.get("storyboard") or {}).get("plans") or [])
    entry = got[phrase - 1] if got else None
    if not entry or not (r or {}).get("plans"):
        raise ValueError("L'IA n'a pas compris ta version : reformule-la un peu.")
    if genre in KINDS and entry["type"] != genre and (genre not in GRAPHICS or entry.get("graphique")):
        entry["type"] = genre               # the kind they ticked (a graphic only with its drawing written)
    entry["ta_version"] = souhait + (f" [{GENRES[genre]}]" if genre in GENRES else "")
    return entry
