"""
The narrative styles of the whole app, in one place (user's idea, 2026-11-07): « you give each channel its
family, the AI picks the style for each video, you can change it ».

  family     a channel's kind of storytelling (Réglages → its card): actualité, explicatif, humour, hype,
             motivation, satisfying. A family's styles can be unticked for one channel.
  style      how one video is told; each has its rule, given to the script writer, which wins over the general
             retention rules. « genre » says what a Reprise's model must be for it: a list ("top"), a story
             ("histoire"), or any.
  choice     the AI reads the subject and picks, among the channel's allowed styles, the one that tells it best —
             not one of the channel's last three when another fits. The person changes it on the script screen.

Used by « Idée d'abord », « Script d'abord », « Sources d'abord » and the Reprise. The Discours keeps the speaker's
words, the Génération (lungtemotivates) and Roblox keep their own formats for now.
"""

from typing import Dict, List, Optional

FAMILLES: Dict[str, Dict] = {
    "actualite": {"label": "Actualité", "styles": {
        "news": ("News", None, "NEWS : la phrase 1 dit QUI + QUOI + OU tout de suite (jamais une question sans le sujet) ; "
                               "puis dans l'ordre : quand et quoi exactement, pourquoi, ce qui est concerne et ce qui ne "
                               "l'est pas, la suite."),
        "decryptage": ("Décryptage", None, "DECRYPTAGE : la nouvelle en une phrase (qui, quoi, ou), puis ce qu'elle change "
                                           "concretement et pourquoi c'est important ; la fin dit la consequence principale."),
        "vrai_faux": ("Vrai ou faux", None, "VRAI OU FAUX : part d'une affirmation qui circule sur le sujet, puis les faits "
                                            "verifies un par un, et le verdict clair a la fin (vrai, faux, ou en partie)."),
        "pour_les_gens": ("Ce que ça change pour les gens", None,
                          "CE QUE CA CHANGE POUR LES GENS : la nouvelle en une phrase, puis ses effets concrets sur la vie de "
                          "tous les jours (prix, transport, ecole...), la fin dit ce qu'il faut retenir."),
    }},
    "explicatif": {"label": "Explicatif", "styles": {
        "mystere": ("Mystère / révélation", "histoire", "MYSTERE / REVELATION : une accroche intrigante, des indices qui "
                                                        "avancent, la revelation a la fin."),
        "fait_surprenant": ("Fait surprenant", None, "FAIT SURPRENANT : le fait peu connu des la 1re phrase, puis pourquoi "
                                                     "il est vrai, preuve par preuve."),
        "origine": ("Origine", "histoire", "ORIGINE : d'ou vient la chose (objet, invention, habitude), raconte dans l'ordre "
                                           "jusqu'a aujourd'hui."),
        "explication": ("Explication", None, "EXPLICATION : le phenomene montre, puis comment il marche etape par etape, la "
                                             "fin resume en une phrase."),
        "top": ("Top / liste", "top", "TOP : plusieurs points independants, du moins fort au plus fort (le meilleur a la fin), "
                                      "chacun annonce par son numero."),
    }},
    "humour": {"label": "Humour", "styles": {
        "pov": ("POV / situation", "histoire", "POV : on met le spectateur DANS la situation (« quand tu... »), on decrit ce "
                                               "qui se passe comme s'il le vivait, la chute arrive sur l'image la plus drole."),
        "reaction": ("Réaction", None, "REACTION : on commente ce qu'on voit comme un pote qui n'en revient pas, phrases "
                                       "courtes, exagerees, avec des pauses avant les moments droles."),
        "chute": ("Chute inattendue", "histoire", "CHUTE INATTENDUE : on installe une situation normale, on fait monter "
                                                  "l'attente, et la derniere phrase la retourne completement."),
        "relatable": ("« Tout le monde a vécu ça »", None, "RELATABLE : un petit moment que tout le monde a vecu, decrit "
                                                           "avec precision, chaque phrase ajoute un detail plus vrai que le precedent."),
    }},
    "hype": {"label": "Hype / épique", "styles": {
        "montee": ("Montée en puissance", "histoire", "MONTEE EN PUISSANCE : on part calme et chaque phrase monte d'un cran "
                                                      "jusqu'au moment le plus fort, a la fin."),
        "top_moments": ("Top moments", "top", "TOP MOMENTS : les meilleurs moments classes, du #3 au #1, chacun avec ce qui le "
                                              "rend enorme."),
        "le_moment_ou": ("« Le moment où… »", "histoire", "LE MOMENT OU : on raconte LE moment cle seconde par seconde, ce qui "
                                                          "le precede, puis l'instant ou tout bascule."),
        "face_a_face": ("Face à face", None, "FACE A FACE : deux forces opposees (personnages, equipes, techniques), leurs "
                                             "atouts alternes, et le verdict a la fin."),
    }},
    "motivation": {"label": "Motivation", "styles": {
        "lettre": ("Lettre à toi", None, "LETTRE A TOI : on parle directement au spectateur (« toi qui... »), doux et "
                                         "personnel, la fin lui dit ce qu'il merite."),
        "affirmations": ("Affirmations", None, "AFFIRMATIONS : quelques phrases courtes a la premiere personne, a repeter, "
                                               "chacune plus forte que la precedente."),
        "histoire_inspirante": ("Histoire inspirante", "histoire", "HISTOIRE INSPIRANTE : une difficulte, un changement, la "
                                                                   "lecon, en peu de phrases et sans morale lourde."),
        "sagesse": ("Sagesse / conseil", None, "SAGESSE : une verite simple sur la vie, illustree par un exemple concret, "
                                               "puis un conseil qu'on peut appliquer aujourd'hui."),
        "mythe_realite": ("Mythe ou réalité", None, "MYTHE OU REALITE : une idee que tout le monde croit, pourquoi elle est "
                                                    "fausse ou incomplete, et ce qui est vrai."),
    }},
    "satisfying": {"label": "Satisfying", "styles": {
        "revelation_lente": ("Révélation lente", "histoire", "REVELATION LENTE : on fait durer l'attente, phrases calmes, et "
                                                             "on montre le resultat seulement a la fin."),
        "avant_apres": ("Avant / après", None, "AVANT / APRES : l'etat de depart decrit precisement, puis le resultat, avec le "
                                               "detail qui fait le plus plaisir."),
        "processus": ("Processus étape par étape", None, "PROCESSUS : chaque etape decrite simplement, dans l'ordre, avec ce "
                                                         "qu'on entend et ce qu'on voit."),
        "asmr_calme": ("ASMR calme", None, "ASMR CALME : peu de mots, doux, on laisse respirer les images et les sons."),
    }},
}

RECIT_PART = """STYLE DE RECIT IMPOSE (il prime sur les regles generales quand elles different) : {regle}
L'accroche (plan 1) tient en 2 a 3 secondes de voix et NOMME le sujet. Ton {ton}.

"""

CHOOSE = """Sujet d'un YouTube Short : {sujet}
Question : {question}
Faits : {faits}
Styles de recit possibles pour cette chaine :
{styles}
Deja utilises recemment (a eviter si un autre convient aussi bien) : {recents}
Choisis le style qui raconte le MIEUX ce sujet avec ces faits.
JSON uniquement : {{"style": "nom", "pourquoi": "une phrase"}}"""

TONS = {"actualite": "factuel et neutre (information)", "explicatif": "pose et intrigant", "humour": "complice et drole",
        "hype": "energique, qui monte", "motivation": "doux et bienveillant", "satisfying": "calme et apaisant"}


def default_family(style: Optional[str]) -> str:
    """A channel that never chose: its look says it (« Actu » = news), else explicatif."""
    return "actualite" if style == "actu" else "explicatif"


def find(name: Optional[str]) -> Optional[str]:
    """The family of a style name, or None."""
    return next((f for f, x in FAMILLES.items() if name in x["styles"]), None)


def allowed(family: str, excluded: Optional[List[str]] = None, genre: Optional[str] = None) -> Dict[str, tuple]:
    """A family's styles a channel allows (all when it untick them all), fitting a Reprise's genre if given."""
    styles = FAMILLES.get(family, FAMILLES["explicatif"])["styles"]
    out = {k: v for k, v in styles.items() if k not in (excluded or [])} or dict(styles)
    if genre:
        fit = {k: v for k, v in out.items() if v[1] in (None, genre)}
        out = fit or out
    return out


def label(name: Optional[str]) -> str:
    f = find(name)
    return FAMILLES[f]["styles"][name][0] if f else (name or "").replace("_", " ")


def choose(reference: Dict, family: str, excluded: Optional[List[str]] = None, recents: Optional[List[str]] = None,
           genre: Optional[str] = None, gemini=None) -> str:
    """The style of the channel's family that tells this subject best, not one of the last ones when another fits."""
    styles = allowed(family, excluded, genre)
    recents = recents or []
    try:
        from adaptation.script import _gemini
        r = (gemini or _gemini())._generate_content([{"text": CHOOSE.format(
            sujet=reference.get("sujet"), question=reference.get("question"),
            faits="; ".join(reference.get("faits") or [])[:1500],
            styles="\n".join(f"- {k} : {v[2]}" for k, v in styles.items()), recents=", ".join(recents) or "aucun")}],
            max_tokens=800, timeout=60, temperature=0.3)
        name = str((r or {}).get("style") or "").strip()
    except Exception:
        name = ""
    if name not in styles:
        name = next((k for k in styles if k not in recents), next(iter(styles)))
    return name


def part(name: str) -> str:
    """The style's rule for the script writer (empty for an unknown style)."""
    f = find(name)
    if not f:
        return ""
    return RECIT_PART.format(regle=FAMILLES[f]["styles"][name][2], ton=TONS[f])


def recent(channel: str, n: int = 3) -> List[str]:
    """The narrative styles of the channel's last videos (newest first), from their recipes."""
    import db
    out = []
    for v in db.query_videos(channel=channel):
        rec = v.get("recette") or {}
        r = (rec.get("style") or {}).get("recit") or (rec.get("details") or {}).get("recit")
        if r:
            out.append((v.get("added_at") or "", r))
    return [r for _, r in sorted(out, reverse=True)[:n]]


def channel_rules(channel: str) -> Dict:
    """{famille, exclus} as set now in Réglages."""
    try:
        from channel_manager import ChannelManager
        from adaptation import settings
        s = settings.channel_settings(ChannelManager().get_channel_profile(channel))
        return {"famille": s["famille_recit"], "exclus": s["styles_exclus"]}
    except Exception:
        return {"famille": "explicatif", "exclus": []}


def for_project(p: Dict, genre: Optional[str] = None) -> str:
    """The project's style: kept when already chosen (by the AI or the person), else chosen now for its first
    channel; written into p ("recit", "famille_recit")."""
    if p.get("recit"):
        return p["recit"]
    channel = p["targets"][0]["channel"]
    rules = channel_rules(channel)
    p["recit"] = choose(p.get("reference") or {}, rules["famille"], rules["exclus"], recent(channel), genre)
    p["famille_recit"] = rules["famille"]
    p.setdefault("recit_par", "ia")
    return p["recit"]
