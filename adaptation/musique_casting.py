"""
The music « casting » (user's idea, 2026-11-07): the person prepares, the AI picks, the person can change.

  songs      every song (the shared ones, assets/musiques, and a channel's own) has categories — its moods, from
             CATEGORIES — and says whether a voice sings or speaks words in it. The AI proposes them when it listens
             to the song (once); the person's own tags (.categories.json beside the songs) always win.
  channel    allows some categories (none ticked = every one) and may want songs without lyrics only (a voice
             over a sung chorus fights the narration — the Cariane news had « Past Lives », with lyrics).
  video      the AI picks, among the allowed songs, the one whose mood fits the video (subject, tone, narrative
             style); started on its strongest moment. Changed at the preview: kept, the edit is not made again.
"""

import base64
import json
import os
from typing import Dict, List, Optional

CATEGORIES = {"actu": "Actu / info", "tension": "Tension", "epique": "Épique", "triste": "Triste / émouvant",
              "joyeux": "Joyeux", "calme": "Calme", "mystere": "Mystère", "motivant": "Motivant", "drole": "Drôle"}
TAGS = ".categories.json"

CLASSIFY = """Ecoute ce morceau comme un monteur qui le mettra SOUS UNE VOIX OFF de YouTube Short.
- "categories" : 1 a 3 parmi {cats} — les ambiances qu'il porte vraiment ;
- "paroles" : true si une voix chante ou parle des mots (meme seulement au refrain), false si c'est instrumental.
JSON uniquement : {{"categories": [""], "paroles": true}}"""

CHOOSE = """Choisis la musique de fond d'un YouTube Short (voix off par-dessus, musique basse).
Le Short : titre « {titre} » ; ce qui est dit : {resume}
Ton : {ton}. Style de recit : {recit}.
Musiques permises (numero. titre — categories — humeur — avec ou sans paroles) :
{musiques}
Choisis celle dont l'AMBIANCE colle le mieux au Short (une musique triste sous une video drole est un contresens ;
sous une info, une ambiance actu, tension ou calme ; a ambiance egale, sans paroles).
JSON uniquement : {{"musique": numero, "pourquoi": "une phrase"}}"""


def _tags_path(folder: str) -> str:
    return os.path.join(folder, TAGS)


def person_tags(folder: str) -> Dict[str, Dict]:
    try:
        with open(_tags_path(folder), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def set_tags(path: str, categories: Optional[List[str]] = None, paroles: Optional[bool] = None) -> Dict:
    """The person's own tags for one song (kept beside it, never overwritten by the AI)."""
    folder, name = os.path.dirname(path), os.path.basename(path)
    tags = person_tags(folder)
    cur = dict(tags.get(name) or {})
    if categories is not None:
        cur["categories"] = [c for c in dict.fromkeys(categories) if c in CATEGORIES]
    if paroles is not None:
        cur["paroles"] = bool(paroles)
    tags[name] = cur
    from atomic_write import write_file_atomic
    write_file_atomic(_tags_path(folder), json.dumps(tags, ensure_ascii=False, indent=1))
    return song_info(path)


def _analysis(path: str) -> Dict:
    from adaptation import musique
    cache = musique._cache(path)
    try:
        with open(cache, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def classify(path: str, gemini=None) -> Dict:
    """The AI's categories and lyrics for a song (asked once, kept in its analysis)."""
    from adaptation import musique
    a = _analysis(path) or musique.listen(path, gemini)
    if "categories" in a and "paroles" in a:
        return a
    r = {}
    if os.path.getsize(path) < 18 * 1024 * 1024:
        from adaptation.sources import _gemini
        try:
            with open(path, "rb") as f:
                audio = base64.b64encode(f.read()).decode()
            r = (gemini or _gemini())._generate_content(
                [{"inline_data": {"mime_type": "audio/mp3", "data": audio}},
                 {"text": CLASSIFY.format(cats=", ".join(CATEGORIES))}], max_tokens=1500, timeout=180, temperature=0.1) or {}
        except Exception:
            r = {}
    a["categories"] = [c for c in (r.get("categories") or []) if c in CATEGORIES][:3]
    a["paroles"] = bool(r.get("paroles")) if "paroles" in r else None
    with open(musique._cache(path), "w", encoding="utf-8") as f:
        json.dump(a, f, ensure_ascii=False, indent=1)
    return a


def song_info(path: str) -> Dict:
    """What the casting knows of a song: the person's tags first, else the AI's."""
    a = _analysis(path)
    mine = person_tags(os.path.dirname(path)).get(os.path.basename(path)) or {}
    cats = mine.get("categories") if "categories" in mine else a.get("categories")
    paroles = mine.get("paroles") if "paroles" in mine else a.get("paroles")
    return {"fichier": os.path.basename(path), "chemin": path, "titre": a.get("titre") or os.path.splitext(os.path.basename(path))[0],
            "humeur": a.get("humeur"), "moment_fort": a.get("moment_fort"), "duree": a.get("duree"),
            "categories": cats or [], "paroles": paroles,
            "par": "toi" if ("categories" in mine or "paroles" in mine) else ("ia" if "categories" in a else None)}


def library(folders: List[str]) -> List[Dict]:
    from adaptation import musique
    return [song_info(p) for d in folders for p in musique.songs_of(d)]


def allowed(songs: List[Dict], categories: Optional[List[str]], sans_paroles: bool) -> List[Dict]:
    """The songs a channel allows: one of its categories (none ticked = every one), and no lyrics if it asks so
    (a song never listened to — lyrics unknown — is not taken then)."""
    out = []
    for s in songs:
        if categories and not set(s["categories"]) & set(categories):
            continue
        if sans_paroles and s["paroles"] is not False:
            continue
        out.append(s)
    return out


def choose(songs: List[Dict], titre: str, resume: str, ton: str, recit: Optional[str], gemini=None) -> Dict:
    """{"song": the chosen one, "pourquoi"} among `songs` (one: it, no question)."""
    if len(songs) == 1:
        return {"song": songs[0], "pourquoi": "la seule musique permise pour cette chaîne"}
    from adaptation.script import _gemini
    listing = "\n".join(f"{k}. {s['titre']} — {', '.join(CATEGORIES[c] for c in s['categories']) or '?'} — "
                        f"{s.get('humeur') or '?'} — {'avec paroles' if s['paroles'] else 'sans paroles' if s['paroles'] is False else '?'}"
                        for k, s in enumerate(songs, 1))
    try:
        r = (gemini or _gemini())._generate_content([{"text": CHOOSE.format(
            titre=titre, resume=resume[:600], ton=ton, recit=recit or "-", musiques=listing)}],
            max_tokens=1000, timeout=60, temperature=0.2)
        n = int(r.get("musique")) - 1
        if 0 <= n < len(songs):
            return {"song": songs[n], "pourquoi": str(r.get("pourquoi") or "")[:200]}
    except Exception:
        pass
    return {"song": songs[0], "pourquoi": "la première musique permise (l'IA n'a pas su choisir)"}
