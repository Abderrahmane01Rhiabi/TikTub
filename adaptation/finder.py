"""
"What should I download?" — from the reference Short to the source videos.

The reference analysis already lists the scenes to find ("a_chercher": one
entry per original video, described in plain French, with English search
queries and the clues seen on screen). From there:
  - each credited account gets direct profile links (YouTube, TikTok,
    Instagram) and, when it has a YouTube channel, its videos on the subject
    (the original author is often credited on screen)
  - each scene gets ready-made search links (YouTube, TikTok, Google) and a
    few YouTube candidates found automatically (yt-dlp search, no API key),
    sorted out by Gemini on their titles (one cheap text call)
  - on demand, Gemini watches one candidate and says whether it really
    contains the scene, and where — a long compilation is then downloaded
    only around those moments
"""

import os
import re
from typing import Callable, Dict, List, Optional
from urllib.parse import quote_plus

from adaptation.sources import ytdlp_opts

PER_QUERY = 5
PER_SCENE = 6
MAX_DURATION = 20 * 60          # longer videos are compilations/livestreams: rarely the original


class FinderError(RuntimeError):
    pass


# --------------------------------------------------------------- links

def _handle(credit: str) -> Optional[str]:
    m = re.search(r"@([\w.\-]{2,})", credit or "")
    return m.group(1).rstrip(".") if m else None


def credit_links(credits: List[str]) -> List[Dict]:
    """A credited account -> its profile on each platform; a media name -> a search."""
    out, seen = [], set()
    for c in credits or []:
        c = str(c).strip()
        if not c or c.lower() in seen:
            continue
        seen.add(c.lower())
        h = _handle(c)
        if h:
            links = [{"label": "YouTube", "url": f"https://www.youtube.com/@{h}"},
                     {"label": "TikTok", "url": f"https://www.tiktok.com/@{h}"},
                     {"label": "Instagram", "url": f"https://www.instagram.com/{h}/"}]
        else:
            links = [{"label": "YouTube", "url": "https://www.youtube.com/results?search_query=" + quote_plus(c)},
                     {"label": "Google", "url": "https://www.google.com/search?q=" + quote_plus(c)}]
        out.append({"name": c, "links": links})
    return out


def search_links(query: str) -> List[Dict]:
    q = quote_plus(query)
    return [{"label": "YouTube", "url": f"https://www.youtube.com/results?search_query={q}"},
            {"label": "TikTok", "url": f"https://www.tiktok.com/search?q={q}"},
            {"label": "Google vidéos", "url": f"https://www.google.com/search?tbm=vid&q={q}"}]


# --------------------------------------------------------------- scenes

def scenes(ref: Dict) -> List[Dict]:
    """The scenes to find, cleaned; falls back on the reference's shots when
    Gemini gave no list."""
    raw = ref.get("a_chercher") if isinstance(ref.get("a_chercher"), list) else []
    out = []
    for s in raw:
        if not isinstance(s, dict) or not str(s.get("scene") or "").strip():
            continue
        queries = [str(q).strip() for q in (s.get("recherches") or []) if str(q).strip()][:3]
        out.append({"scene": str(s["scene"]).strip(), "plans": [int(i) for i in (s.get("plans") or [])
                                                                 if isinstance(i, (int, float))],
                    "indices": str(s.get("indices") or "").strip(), "recherches": queries or [str(s["scene"])[:80]]})
    if not out:
        for i, pl in enumerate(ref.get("plans") or []):
            v = str((pl or {}).get("visuel") or "").strip()
            if v and v.lower() not in {o["scene"].lower() for o in out}:
                out.append({"scene": v, "plans": [i], "indices": "", "recherches": [v[:80]]})
    return out[:8]


# --------------------------------------------------------------- YouTube search

def _video_id(url: str) -> Optional[str]:
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", url or "")
    return m.group(1) if m else None


def search_youtube(query: str, n: int = PER_QUERY) -> List[Dict]:
    import yt_dlp
    opts = ytdlp_opts(extract_flat=True)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{n}:{query}", download=False) or {}
    except Exception:
        return []
    out = []
    for e in info.get("entries") or []:
        vid = e.get("id")
        if not vid or (e.get("duration") or 0) > MAX_DURATION:
            continue
        out.append({"url": f"https://www.youtube.com/watch?v={vid}", "id": vid, "title": e.get("title") or "",
                    "channel": e.get("channel") or e.get("uploader") or "", "duration": e.get("duration"),
                    "views": e.get("view_count"), "thumb": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                    "query": query})
    return out


def search_channel(handle: str, query: str, n: int = 8) -> List[Dict]:
    """A credited account's own YouTube videos on the subject (none if it has no channel)."""
    import yt_dlp
    opts = ytdlp_opts(extract_flat=True, playlistend=n)
    url = f"https://www.youtube.com/@{handle}/search?query={quote_plus(query)}"
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False) or {}
    except Exception:
        return []
    return [{"url": f"https://www.youtube.com/watch?v={e['id']}", "id": e["id"], "title": e.get("title") or "",
             "channel": info.get("channel") or "@" + handle, "duration": e.get("duration"),
             "views": e.get("view_count"), "thumb": f"https://i.ytimg.com/vi/{e['id']}/hqdefault.jpg",
             "query": query} for e in (info.get("entries") or [])[:n] if e.get("id")]


SORT_PROMPT = """On cherche les videos d'origine des scenes d'un Short viral. Pour chaque scene, voici des resultats
de recherche YouTube (numero, titre, chaine, duree en s). Garde seulement ceux qui peuvent plausiblement contenir
la scene (le meme type d'evenement filme : une compilation du bon theme est bonne, un sujet voisin ne l'est pas).
JSON uniquement : {{"garder": {{"<numero de scene>": [numeros des resultats a garder, du plus probable au moins probable]}}}}

{scenes}"""


def sort_out(found: List[Dict], gemini=None) -> None:
    """Drops the off-topic candidates (one text call for every scene); keeps
    everything if Gemini can't answer."""
    if not any(s.get("candidats") for s in found):
        return
    try:
        from gemini_ai_generator import GeminiAIGenerator
        g = gemini or GeminiAIGenerator(api_key=os.getenv("GEMINI_API_KEY"))
        text = "\n\n".join(f"Scene {i}: {s['scene']}\n" + "\n".join(
            f"  {k}. {c['title']} | {c['channel']} | {c.get('duration')}" for k, c in enumerate(s["candidats"]))
            for i, s in enumerate(found))
        r = g._generate_content([{"text": SORT_PROMPT.format(scenes=text)}], max_tokens=2000, timeout=60,
                                temperature=0.1)
        keep = r.get("garder") if isinstance(r, dict) else None
        if not isinstance(keep, dict):
            return
    except Exception:
        return
    for i, s in enumerate(found):
        ks = keep.get(str(i))
        if isinstance(ks, list):
            s["candidats"] = [s["candidats"][k] for k in dict.fromkeys(ks)
                              if isinstance(k, int) and 0 <= k < len(s["candidats"])]


def suggest(ref: Dict, reference_url: str = "", search: Callable = None, search_in: Callable = None,
            sort: Callable = None, report: Optional[Callable[[str, float], None]] = None) -> Dict:
    """The full "what to download" sheet for a reference analysis."""
    search, search_in = search or search_youtube, search_in or search_channel
    sort = sort or sort_out
    report = report or (lambda phase, f: None)
    skip = {_video_id(reference_url)} - {None}
    found = scenes(ref)
    for i, s in enumerate(found):
        report(f"recherche : scène {i + 1}/{len(found)}", i / max(1, len(found)))
        cands, seen = [], set(skip)
        for q in s["recherches"][:2]:
            for c in search(q):
                if c["id"] not in seen:
                    seen.add(c["id"])
                    cands.append(c)
        s["candidats"] = cands[:PER_SCENE * 2]
        s["liens"] = search_links(s["recherches"][0])
    report("tri des résultats", 0.85)
    sort(found)
    for s in found:
        s["candidats"] = s["candidats"][:PER_SCENE]
    accounts = credit_links(ref.get("credits") or [])
    keyword = str(ref.get("recherche_courte") or "").strip() or \
        (found[0]["recherches"][0].split()[0] if found else "")
    for a in accounts:
        h = _handle(a["name"])
        a["videos"] = [v for v in search_in(h, keyword) if v["id"] not in skip] if h and keyword else []
    return {"comptes": accounts, "scenes": found, "verifs": {}}


# --------------------------------------------------------------- the Gemini check

CHECK_PROMPT = """On cherche la video d'origine de cette scene, vue dans un Short viral :
"{scene}"
Indices vus a l'ecran : {indices}

Regarde cette video. Contient-elle CETTE scene (le meme evenement filme, pas juste le meme sujet) ?
JSON uniquement :
{{"verdict": "oui | probable | non",
  "moments": [{{"debut": s, "fin": s, "ce_qu_on_voit": "..."}}],
  "qualite": "bonne | moyenne | mauvaise (resolution, filigranes, texte incruste)",
  "raison": "une phrase en francais"}}"""


def sections(verif: Optional[Dict], duration: Optional[float], pad: float = 6.0) -> Optional[List[List[float]]]:
    """A long video verified by Gemini: only the moments it found (padded,
    merged) are downloaded. None = the whole video."""
    if not verif or verif.get("verdict") == "non" or not duration or duration < 150:
        return None
    spans = []
    for m in verif.get("moments") or []:
        try:
            a, b = float(m.get("debut")), float(m.get("fin", m.get("debut")))
        except (TypeError, ValueError):
            continue
        a, b = max(0.0, min(a, b) - pad), min(float(duration), max(a, b) + pad)
        if b > a:
            spans.append([a, b])
    spans.sort()
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1] + 2:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return merged or None


def check(url: str, scene: Dict, gemini=None) -> Dict:
    """Gemini watches a YouTube candidate (by link, nothing downloaded)."""
    if not _video_id(url):
        raise FinderError("La vérification ne marche que sur un lien YouTube.")
    from gemini_ai_generator import GeminiAIGenerator
    g = gemini or GeminiAIGenerator(api_key=os.getenv("GEMINI_API_KEY"))
    prompt = CHECK_PROMPT.format(scene=scene.get("scene", ""), indices=scene.get("indices") or "aucun")
    r = g._generate_content([{"file_data": {"file_uri": url}, "video_metadata": {"fps": 1}}, {"text": prompt}],
                            max_tokens=4000, timeout=240, temperature=0.1)
    if not isinstance(r, dict) or "error" in r or r.get("parsing_error") or "verdict" not in r:
        raise FinderError(f"Vérification impossible : {str(r)[:160]}")
    verdict = str(r.get("verdict")).lower().strip()
    return {"verdict": verdict if verdict in {"oui", "probable", "non"} else "probable",
            "moments": [m for m in (r.get("moments") or []) if isinstance(m, dict)][:5],
            "qualite": str(r.get("qualite") or ""), "raison": str(r.get("raison") or "")}
