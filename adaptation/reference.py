"""
The viral reference Short, read by Gemini as a blueprint: what happens shot
by shot, what is said, the banners, the credits. Its footage is never used —
only its recipe.
"""

import os
import tempfile
from typing import Dict

PROMPT = """Tu analyses un YouTube Short viral de type "explication" (une voix off explique des images).
On veut reproduire sa RECETTE (pas ses images) dans d'autres langues, a partir des videos d'origine de ses clips.
Dans "a_chercher", regroupe les plans qui viennent de la meme video d'origine (meme camera, meme evenement) en une seule scene.
JSON uniquement :
{"sujet": "de quoi parle la video, en une phrase",
 "question": "la question implicite a laquelle la video repond",
 "duree_s": nombre,
 "langue": "langue de la voix",
 "credits": ["comptes ou medias credites a l'ecran, ex. @adrenalinejunkie4661"],
 "plans": [{"debut": s, "fin": s, "role": "accroche | mise en place | explication | suspense | chute",
            "visuel": "ce qu'on voit", "bandeau": "texte du bandeau en haut ou null", "paroles": "ce qui est dit"}],
 "script_complet": "tout le texte dit, dans l'ordre",
 "faits": ["chaque affirmation factuelle du script, une par ligne"],
 "faits_douteux": ["affirmations exagerees ou fausses a ne pas reprendre telles quelles"],
 "fin_reboucle": true/false,
 "recherche_courte": "1 ou 2 mots anglais du theme, pour chercher dans la chaine des comptes credites (ex. tram)",
 "a_chercher": [{"scene": "en francais, la video d'origine a retrouver, concrete et visuelle (ex. un tram qui percute une voiture noire, filme depuis la cabine du conducteur, de nuit)",
                 "plans": [indices des plans de cette scene, 0 = premier],
                 "indices": "filigranes, logos de media, lieu, date ou textes visibles qui aident a retrouver l'original",
                 "recherches": ["2 ou 3 recherches YouTube en anglais pour retrouver cette video ou une equivalente"]}],
 "style": {"cadre": "", "bandeaux": "", "sous_titres": "", "musique": "", "bruitages": ""}}"""


class ReferenceError(RuntimeError):
    pass


def _is_youtube(url: str) -> bool:
    return any(h in url for h in ("youtube.com/", "youtu.be/"))


def analyse(url: str, gemini=None) -> Dict:
    """Gemini reads a YouTube link directly (no download); any other platform
    is downloaded and sent as a file."""
    from gemini_ai_generator import GeminiAIGenerator
    g = gemini or GeminiAIGenerator(api_key=os.getenv("GEMINI_API_KEY"))
    if _is_youtube(url):
        r = g._generate_content([{"file_data": {"file_uri": url}, "video_metadata": {"fps": 4}}, {"text": PROMPT}],
                                max_tokens=16000, timeout=240, temperature=0.2)
    else:
        from adaptation.sources import download
        with tempfile.TemporaryDirectory() as tmp:
            path = download(url, tmp, "reference")
            up = g._upload_video_file(path)
            if not up:
                raise ReferenceError("Envoi du Short modèle à Gemini impossible.")
            try:
                if not g._wait_for_file_active(up["name"], timeout=180):
                    raise ReferenceError("Gemini n'a pas fini de lire le Short modèle à temps.")
                r = g._generate_content([{"file_data": {"mime_type": up["mime_type"], "file_uri": up["uri"]}},
                                         {"text": PROMPT}], max_tokens=16000, timeout=240, temperature=0.2)
            finally:
                g._delete_file(up["name"])
    if not isinstance(r, dict) or "error" in r or r.get("parsing_error") or not r.get("plans"):
        raise ReferenceError(f"Analyse du Short modèle inutilisable : {str(r)[:200]}")
    return r
