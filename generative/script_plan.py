"""
What each new script is made of, decided BEFORE the AI writes it: a format,
a topic, a kind of hook and a kind of ending — each the one the channel used
least lately. The AI only writes inside that plan.

Why: left free, with the same six examples every time, the AI wrote the same
few scripts. On lungtemotivates (Sept.-Oct. 2026): 8 titles opening with
"J'ai testé", 5 with "3 signes", 4 with "Répète ceci/ces", nearly every
ending "dis-le en commentaire" — and YouTube stopped showing the channel.
A plan chosen by rotation gives each video a different shape.

    FORMATS   code -> label, length, how it is built, one example (style only)
    TOPICS    the niche's subjects (a channel can set its own: "script_topics")
    HOOKS     how the first sentence grabs
    ENDINGS   how the video closes

No fake first-person testimony: "J'ai testé X pendant 72h" read by a
synthetic voice tells an experience that never happened — misleading for
the viewer, and the "inauthentic content" YouTube downranks.
"""

import random
import re
import unicodedata
from typing import Dict, List, Optional

FORMATS: Dict[str, Dict] = {
    "A": {"label": "Affirmations", "duree": "20-25 s",
          "regle": "2 à 4 affirmations courtes à la 1re personne, que le spectateur répète, après une phrase d'entrée.",
          "exemple": '[softly] Ferme les yeux, respire doucement... <break time="1.0s" />\n\n'
                     '[calm, warm] Aujourd\'hui, je choisis d\'attirer l\'abondance dans ma vie. <break time="0.6s" />\n'
                     'Je mérite le succès, <break time="0.4s" /> et chaque effort me rapproche de ma meilleure version. <break time="0.6s" />\n\n'
                     '[confident] L\'univers travaille en ma faveur.'},
    "D": {"label": "Liste éducative", "duree": "30-35 s",
          "regle": "une liste numérotée de 3 points concrets (signes, étapes, erreurs, habitudes...).",
          "exemple": '[curious] 3 signes que l\'univers essaie de te dire quelque chose : <break time="0.8s" />\n\n'
                     '[calm] 1. Tu vois le même chiffre partout, 11h11, 22h22... <break time="0.5s" />\n'
                     '2. Une idée te vient sans effort, comme une évidence. <break time="0.5s" />\n'
                     '3. Une coïncidence tellement précise que ça ne peut pas être un hasard.'},
    "B": {"label": "Histoire", "duree": "40-55 s",
          "regle": "une courte histoire racontée à la 3e personne (un prénom, un âge, une situation), avec un début, "
                   "un moment difficile et un retournement ; on comprend que c'est une histoire, pas un témoignage. "
                   "JAMAIS « j'ai testé », « j'ai essayé » ni « j'ai arrêté... pendant X jours ».",
          "exemple": '[calm] Martine avait 61 ans quand sa fille a déménagé à l\'autre bout du pays. <break time="0.6s" />\n'
                     'Chaque soir, elle fixait le téléphone en attendant qu\'il sonne. <break time="0.6s" />\n\n'
                     '[softly] Un matin, elle a décidé d\'arrêter d\'attendre. <break time="0.5s" />\n'
                     'Elle a écrit trois choses qu\'elle aimait dans sa journée. Puis le lendemain. Puis le surlendemain. <break time="0.6s" />\n\n'
                     '[warm] Trois semaines plus tard, c\'est sa fille qui a appelé : « Maman, tu as l\'air tellement bien. »'},
    "M": {"label": "Mythe ou réalité", "duree": "25-35 s",
          "regle": "une idée reçue très répandue dans la niche, annoncée comme telle, puis ce qui est vrai et ce qui ne l'est pas, avec nuance.",
          "exemple": '[curious] « Il suffit de penser positif pour que ça arrive. » Mythe ou réalité ? <break time="0.8s" />\n\n'
                     '[calm] À moitié vrai. <break time="0.5s" /> Penser positif change ce que tu remarques autour de toi. <break time="0.5s" />\n'
                     'Mais sans un petit geste concret, rien ne bouge. <break time="0.6s" />\n\n'
                     '[confident] La pensée ouvre la porte. C\'est toi qui la passes.'},
    "C": {"label": "Citation expliquée", "duree": "25-35 s",
          "regle": "une citation TRÈS connue dont tu es certain de l'auteur et des mots exacts, ce qu'elle veut dire pour nous aujourd'hui, "
                   "et un geste simple pour l'appliquer. Si tu as le moindre doute sur l'auteur ou les mots, choisis-en une autre.",
          "exemple": '[calm] Marc Aurèle écrivait : « Notre vie est ce que nos pensées en font. » <break time="0.8s" />\n\n'
                     '[warm] Ça ne veut pas dire que tout va bien. <break time="0.4s" /> Ça veut dire que tu choisis où poser ton regard. <break time="0.6s" />\n'
                     'Ce soir, avant de dormir, cherche une seule chose qui t\'a fait du bien aujourd\'hui. <break time="0.6s" />\n\n'
                     '[softly] Une seule. C\'est comme ça que ça commence.'},
    "E": {"label": "Exercice guidé", "duree": "25-40 s",
          "regle": "un exercice à faire MAINTENANT pendant la vidéo (respiration, visualisation, ancrage), guidé pas à pas, avec des pauses.",
          "exemple": '[softly] Pose ta main sur ta poitrine. <break time="1.0s" />\n'
                     'Inspire en comptant jusqu\'à quatre... <break time="2.0s" />\n'
                     'Retiens... <break time="1.5s" />\n'
                     'Et relâche, doucement. <break time="1.5s" />\n\n'
                     '[calm, warm] Pense à quelqu\'un qui t\'aime. <break time="1.0s" /> Garde cette chaleur. C\'est à toi, pour toute la journée.'},
    "L": {"label": "Lettre à toi", "duree": "25-35 s",
          "regle": "une lettre adressée au spectateur (« Chère toi », « À toi qui... »), tendre et précise, qui nomme ce qu'il vit.",
          "exemple": '[softly] À toi qui fais semblant que tout va bien. <break time="0.8s" />\n\n'
                     '[calm, warm] Je sais que tu portes beaucoup. <break time="0.5s" /> Pour les autres, toujours en premier. <break time="0.6s" />\n'
                     'Aujourd\'hui, tu as le droit de poser ce poids une minute. <break time="0.6s" />\n\n'
                     '[warm] Tu n\'as rien à prouver. Tu es déjà assez.'},
    "P": {"label": "Le saviez-vous (psycho)", "duree": "25-35 s",
          "regle": "UN phénomène de psychologie connu et établi (biais de négativité, effet Zeigarnik, effet placebo, "
                   "effet de simple exposition...), expliqué simplement et relié à la vie du spectateur. "
                   "Aucun chiffre inventé, aucune étude précise citée.",
          "exemple": '[curious] Ton cerveau retient plus les mauvaises nouvelles que les bonnes. Et ce n\'est pas ta faute. <break time="0.8s" />\n\n'
                     '[calm] Les psychologues appellent ça le biais de négativité. <break time="0.5s" />\n'
                     'Pour nos ancêtres, repérer le danger était une question de survie. <break time="0.6s" />\n\n'
                     '[warm] Alors aujourd\'hui, rééquilibre : pour chaque souci qui te revient, note deux choses qui vont bien.'},
}

TOPICS: List[str] = [
    "la gratitude au quotidien", "la confiance en soi", "lâcher prise sur ce qu'on ne contrôle pas",
    "l'argent et l'abondance", "les relations et les personnes qui nous vident", "le sommeil et les pensées du soir",
    "les enfants devenus grands, le nid vide", "la retraite, une nouvelle vie", "le deuil et le manque",
    "la solitude choisie ou subie", "le pardon (aux autres, à soi)", "le corps qui change avec l'âge",
    "la peur du changement", "les signes et les coïncidences", "la patience quand rien ne bouge",
    "dire non sans culpabilité", "la loi de l'assomption", "la visualisation", "les matins et la façon de commencer la journée",
    "l'amitié", "l'amour après 50 ans", "les regrets", "la santé et la paix intérieure", "oser recommencer",
]

HOOKS: Dict[str, str] = {
    "question": "une question directe que le spectateur se pose déjà",
    "fait": "un fait surprenant, simple et vrai",
    "choc": "une phrase contre-intuitive qui contredit une idée reçue",
    "scene": "une scène précise qu'on visualise (« Il est 3 h du matin... »)",
    "adresse": "une adresse directe au spectateur (« Si tu vois cette vidéo, c'est que... »)",
    "promesse": "une promesse courte et tenue dans la vidéo (« En 20 secondes, tu vas... »)",
}

ENDINGS: Dict[str, str] = {
    "question": "une question qui invite à répondre en commentaire",
    "phrase": "une phrase courte à garder pour la journée",
    "defi": "un petit défi concret pour demain",
    "partage": "une invitation à envoyer la vidéo à quelqu'un précis (« à quelqu'un qui en a besoin »)",
    "repeter": "une affirmation finale à répéter à voix haute",
    "chute": "une chute, un retournement final qui donne envie de revoir la vidéo",
}

FAKE_TESTIMONY = re.compile(r"\bj'?\s?ai\s+(test|essay|arr[êe]t)", re.IGNORECASE)


def _norm(text: str) -> str:
    text = re.sub(r"['’]", "", unicodedata.normalize("NFKD", (text or "").lower()))     # "j'ai" stays one word
    return " ".join(re.findall(r"[a-z0-9]+", "".join(c for c in text if not unicodedata.combining(c))))


def opening(title: str) -> str:
    """The first two words of a title, normalized ("3 signes", "jai teste")."""
    return " ".join(_norm(title).split()[:2])


def overused_openings(titles: List[str], at_least: int = 2) -> List[str]:
    """Title openings used at least twice lately, as first written."""
    seen: Dict[str, List[str]] = {}
    for t in titles:
        if t and opening(t):
            seen.setdefault(opening(t), []).append(" ".join(t.split()[:2]))
    return [v[0] for v in seen.values() if len(v) >= at_least]


def _least_used(options: List[str], used: List[str], rng: random.Random) -> str:
    counts = {o: used.count(o) for o in options}
    low = min(counts.values())
    return rng.choice([o for o in options if counts[o] == low])


def choose(history: List[Dict], topics: Optional[List[str]] = None, fmt: Optional[str] = None,
           rng: Optional[random.Random] = None) -> Dict:
    """The next script's plan {format, sujet, accroche, fin}: each the least
    used in `history` (the channel's recent plans, newest first). `fmt`
    imposes the format (a winning recipe's)."""
    rng = rng or random.Random()
    topics = topics or TOPICS
    pick = lambda key, options: _least_used(options, [h.get(key) for h in history if h.get(key)], rng)
    return {"format": fmt if fmt in FORMATS else pick("format", list(FORMATS)),
            "sujet": pick("sujet", topics), "accroche": pick("accroche", list(HOOKS)), "fin": pick("fin", list(ENDINGS))}


def describe(plan: Dict) -> str:
    """The plan, as the prompt states it."""
    f = FORMATS[plan["format"]]
    return (f"FORMAT « {f['label']} » ({f['duree']}) : {f['regle']}\n"
            f"SUJET : {plan['sujet']}\n"
            f"ACCROCHE (première phrase) : {HOOKS[plan['accroche']]}\n"
            f"FIN : {ENDINGS[plan['fin']]}")


def examples(plan: Dict, rng: Optional[random.Random] = None) -> List[str]:
    """Two examples: the plan's format, and one other for the tone and tags."""
    rng = rng or random.Random()
    other = rng.choice([k for k in FORMATS if k != plan["format"]])
    return [FORMATS[plan["format"]]["exemple"], FORMATS[other]["exemple"]]
