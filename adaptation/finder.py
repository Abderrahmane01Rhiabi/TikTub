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
  - each scene also gets searches in the language of where it was filmed
  - the Short's pictures are searched by image (Yandex, see imagesearch.py)
  - Gemini watches the most promising candidates (and any other on demand)
    and judges them plan by plan: exact, equivalent, partial or nothing,
    with the moments — a long compilation is then downloaded only around
    those moments
"""

import json
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
    ads = {int(i) for i in (ref.get("plans_pub") or []) if isinstance(i, (int, float))}
    for s in out:                       # the sponsor's demo: not to be found, not to be paid for
        if ads and s["plans"] and set(s["plans"]) <= ads:
            s["pub"] = True
    if not out:
        for i, pl in enumerate(ref.get("plans") or []):
            v = str((pl or {}).get("visuel") or "").strip()
            if v and v.lower() not in {o["scene"].lower() for o in out}:
                out.append({"scene": v, "plans": [i], "indices": "", "recherches": [v[:80]]})
    return out[:8]


# --------------------------------------------------------------- YouTube search

def same_video(url: str) -> str:
    """One key per video, whatever the spelling: http/https, www./m., a
    trailing slash, YouTube's watch/shorts/youtu.be forms."""
    vid = _video_id(url)
    if vid:
        return "youtube:" + vid
    u = re.sub(r"^https?://(www\.|m\.)?", "", (url or "").strip().lower())
    return u.split("?")[0].split("#")[0].rstrip("/")


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

# Found by a picture: the title may be in any language and say little ("Tram Cam", "Железные нервы") —
# only what is plainly about something else goes (measured: "how the broken excavator was transported"
# for a gas-well scene, because an excavator stood in the picture).
SORT_IMAGE_PROMPT = """On cherche les videos d'origine des scenes d'un Short viral. Ces resultats ont ete trouves par
RECHERCHE D'IMAGE (une image du Short ressemble a une image de la video) : le titre peut etre dans n'importe quelle
langue et peu parlant. Retire SEULEMENT ceux dont le titre montre clairement un autre sujet (ex. une machine
transportee, un tutoriel, de la musique, une emission sans rapport) ; garde tout ce qui est ambigu ou peut contenir la scene.
JSON uniquement : {{"garder": {{"<numero de scene>": [numeros des resultats a garder]}}}}

{scenes}"""


def _sort_one(i: int, s: Dict, g, prompt: str) -> Optional[List[int]]:
    text = f"Scene {i}: {s['scene']}\n" + "\n".join(
        f"  {k}. {c['title']} | {c.get('channel') or ''} | {c.get('duration')}" for k, c in enumerate(s["candidats"]))
    try:
        r = g._generate_content([{"text": prompt.format(scenes=text)}], max_tokens=1500, timeout=60, temperature=0.1)
    except Exception:
        return None
    keep = r.get("garder") if isinstance(r, dict) else None
    ks = (keep.get(str(i)) if isinstance(keep, dict) else None) or (keep if isinstance(keep, list) else None)
    return ks if isinstance(ks, list) else None


def sort_out(found: List[Dict], gemini=None, prompt: str = SORT_PROMPT) -> None:
    """Drops the off-topic candidates, one short call per scene, in parallel
    (one call for seven scenes came back cut off and sorted nothing); a scene
    Gemini can't answer for keeps everything."""
    from concurrent.futures import ThreadPoolExecutor
    todo = [(i, s) for i, s in enumerate(found) if s.get("candidats")]
    if not todo:
        return
    try:
        from gemini_ai_generator import GeminiAIGenerator
        g = gemini or GeminiAIGenerator(api_key=os.getenv("GEMINI_API_KEY"))
    except Exception:
        return
    with ThreadPoolExecutor(max_workers=4) as pool:
        answers = list(pool.map(lambda t: _sort_one(t[0], t[1], g, prompt), todo))
    for (i, s), ks in zip(todo, answers):
        if ks is not None:
            s["candidats"] = [s["candidats"][k] for k in dict.fromkeys(ks)
                              if isinstance(k, int) and 0 <= k < len(s["candidats"])]


LOCAL_PROMPT = """Des scenes d'un Short viral (les videos d'origine ont ete filmees quelque part dans le monde) :
{scenes}
1. Devine le pays ou chaque scene a ete filmee (paysage, vegetation, vetements, machines, ecritures, indices).
2. Pour chaque scene, ecris 3 recherches YouTube/TikTok DANS LA LANGUE LOCALE de ce pays, comme un habitant
   titrerait sa video (mots simples, pas de guillemets). Si le pays parle anglais, ecris quand meme 3 recherches
   differentes de celles deja faites.
JSON uniquement : {{"scenes": [{{"scene": numero, "pays": "...", "langue": "nom de la langue en francais",
  "recherches": ["...", "...", "..."]}}]}}"""


def local_queries(found: List[Dict], gemini=None) -> Dict[int, Dict]:
    """{scene: {"pays", "langue", "recherches"}} — the original video's title is
    usually in the language of where it was filmed (measured: the wells Short
    found nothing in English, real Vietnamese and Turkish wells in their
    languages). {} if Gemini can't answer."""
    if not found:
        return {}
    try:
        from gemini_ai_generator import GeminiAIGenerator
        g = gemini or GeminiAIGenerator(api_key=os.getenv("GEMINI_API_KEY"))
        listing = "\n".join(f"{i}. {s['scene']}" + (f" (indices : {s['indices']})" if s.get("indices") else "")
                            for i, s in enumerate(found))
        r = g._generate_content([{"text": LOCAL_PROMPT.format(scenes=listing)}], max_tokens=3000, timeout=90,
                                temperature=0.3)
    except Exception:
        return {}
    out = {}
    for e in (r.get("scenes") if isinstance(r, dict) else None) or []:
        try:
            i = int(e.get("scene"))
        except (TypeError, ValueError, AttributeError):
            continue
        qs = [str(q).strip() for q in (e.get("recherches") or []) if str(q).strip()][:3]
        if 0 <= i < len(found) and qs:
            out[i] = {"pays": str(e.get("pays") or ""), "langue": str(e.get("langue") or ""), "recherches": qs}
    return out


PLAN_QUERIES_PROMPT = """On doit trouver en video (YouTube, TikTok) l'image de chaque plan d'un Short :
{plans}
Pour CHAQUE plan :
- 2 recherches YouTube en ANGLAIS, courtes (3 a 6 mots), comme le titre d'une vraie video qui montrerait cette image ;
- le pays ou une telle video a le plus de chances d'avoir ete filmee, sa langue, et 2 recherches DANS CETTE LANGUE
  (comme un habitant titrerait sa video ; si c'est un pays anglophone, 2 autres recherches en anglais).
JSON uniquement : {{"plans": [{{"plan": numero, "anglais": ["", ""], "pays": "", "langue": "nom en francais",
  "locales": ["", ""]}}]}}"""


ACTION_QUERIES_PROMPT = """On cherche en video une ACTION precise, pour des plans d'un Short ou rien n'a ete trouve
en cherchant le sujet. L'action peut se trouver au milieu d'une video qui parle d'AUTRE CHOSE : compilations
(fails, best of, caught on camera, top 10), videos GoPro / POV / casque, ralentis, vlogs, reportages, highlights
de sport, extraits de tournages amateurs. On prendra juste les 3 secondes utiles.
{plans}
Pour CHAQUE plan, 5 recherches YouTube en ANGLAIS (3 a 6 mots) qui ramenent ces videos-la, pas des tutoriels du
sujet : decris l'action telle qu'un titre de compilation ou de video amateur la nommerait. Jamais de film ni de
serie.
JSON uniquement : {{"plans": [{{"plan": numero, "recherches": ["", "", "", "", ""]}}]}}"""


def action_queries(found: List[Dict], gemini=None) -> Dict[int, List[str]]:
    """Searches by ACTION for plans the subject search left empty: footage
    where it happens inside a video about something else (measured on a
    parkour Short: 5 plans of 7 without footage, every candidate a parkour
    video). {index in found: [queries]}."""
    if not found:
        return {}
    try:
        from gemini_ai_generator import GeminiAIGenerator
        g = gemini or GeminiAIGenerator(api_key=os.getenv("GEMINI_API_KEY"))
        listing = "\n".join(f"{i + 1}. action : {s['scene']}" + (f" | phrase : « {s['phrase']} »" if s.get("phrase") else "")
                            for i, s in enumerate(found))
        r = g._generate_content([{"text": ACTION_QUERIES_PROMPT.format(plans=listing)}], max_tokens=4000, timeout=90,
                                temperature=0.5)
    except Exception:
        return {}
    out = {}
    for e in (r.get("plans") if isinstance(r, dict) else None) or []:
        try:
            i = int(e.get("plan")) - 1
        except (TypeError, ValueError, AttributeError):
            continue
        qs = [str(q).strip() for q in e.get("recherches") or [] if str(q).strip()][:5]
        if 0 <= i < len(found) and qs:
            out[i] = qs
    return out


def plan_queries(found: List[Dict], gemini=None) -> Dict[int, Dict]:
    """Search words for the storyboard's images (written in French, as a person
    would see them): {plan: {"recherches", "pays", "langue", "locales"}}."""
    if not found:
        return {}
    try:
        from gemini_ai_generator import GeminiAIGenerator
        g = gemini or GeminiAIGenerator(api_key=os.getenv("GEMINI_API_KEY"))
        listing = "\n".join(f"{i + 1}. {s['scene']}" for i, s in enumerate(found))
        r = g._generate_content([{"text": PLAN_QUERIES_PROMPT.format(plans=listing)}], max_tokens=4000, timeout=90,
                                temperature=0.3)
    except Exception:
        return {}
    out = {}
    for e in (r.get("plans") if isinstance(r, dict) else None) or []:
        try:
            i = int(e.get("plan")) - 1
        except (TypeError, ValueError, AttributeError):
            continue
        if 0 <= i < len(found):
            out[i] = {"recherches": [str(q).strip() for q in e.get("anglais") or [] if str(q).strip()][:3],
                      "pays": str(e.get("pays") or ""), "langue": str(e.get("langue") or ""),
                      "locales": [str(q).strip() for q in e.get("locales") or [] if str(q).strip()][:3]}
    return out


def wanted_from_storyboard(sb_plans: List[Dict], queries: Dict[int, Dict]) -> List[Dict]:
    """The storyboard's plans as "scenes to find" for suggest(): the image
    is the scene, the reference shots it draws on bring their pictures; the
    sentence said over it goes along (measured on a parkour Short: the exact
    footage of a glass dome was found for "redirect the shock's energy" —
    judged on the image alone, nothing saw that it said something else)."""
    out = []
    for i, pl in enumerate(sb_plans):
        q = queries.get(i) or {}
        textes = pl.get("textes") or {}
        phrase = next((textes[c]["texte"] for c in ("fr", *textes) if c in textes and textes[c].get("texte")), "")
        out.append({"scene": pl["image"], "plans": [k - 1 for k in pl.get("plans_modele") or [] if k >= 1],
                    "indices": "", "phrase": phrase,
                    "recherches": q.get("recherches") or [" ".join(pl["image"].split()[:8])]})
    return out


RANK = {"exacte": 0, "equivalente": 1, "partielle": 2}

# What makes a moment unusable whatever the cleaning does: only what is seen and can't be removed. Not
# burnt-in text or a logo (cropped or painted), not the sound (replaced by the narration), not "a compilation",
# not "an advert" (a brand's promo film shows real footage, its logo is painted: a warning, never a refusal).
REAL_FAULTS = re.compile(r"pr[ée]sentat|presenter|interview|journaliste|plateau|split|[ée]cran (divis|partag|scind)|"
                         r"incrustation d.[ée]cran|[ée]cran de fin|end ?screen|g[ée]n[ée]rique|flou|blur|"
                         r"noir|black|image fixe|photo|diaporama|slide|dessin|anim[ée]|jeu vid[ée]o|t[ée]l[ée]phone film", re.I)
WARNINGS = re.compile(r"publicit|\bpub\b|promo|sponsor", re.I)


def warnings_of(text: str) -> str:
    """Reasons worth a look but not a refusal (an advert's footage)."""
    parts = [x.strip() for x in re.split(r"[,;/]| et ", text or "") if x.strip()]
    return ", ".join(x for x in parts if WARNINGS.search(x) and not REAL_FAULTS.search(x))


def real_faults(text: str) -> str:
    """The reasons, among Gemini's, that really make a moment unusable."""
    parts = [x.strip() for x in re.split(r"[,;/]| et ", text or "") if x.strip()]
    return ", ".join(x for x in parts if REAL_FAULTS.search(x))


def auto_pick(sug: Dict, sb_plans: List[Dict]) -> List[Optional[Dict]]:
    """For each plan, the best checked video and its moment: exact, then
    equivalent, then partial; the longest moment; never the same moment for
    two plans. None when nothing checked fits."""
    verifs, used, picks = sug.get("verifs") or {}, set(), []
    dead = set(sug.get("unavailable") or [])          # could not be downloaded from here: never picked again
    cands = {c["url"]: c for c in all_candidates(sug)}
    for i, pl in enumerate(sb_plans):
        options = []
        for url, v in verifs.items():
            if url in dead or v.get("film") or v.get("remontage"):
                continue                    # a film, or someone else's re-edit: only by hand (rights)
            e = (v.get("par_scene") or {}).get(str(i))
            if not e or e.get("niveau") not in RANK:
                continue
            for m in e.get("moments") or [{"debut": 0}]:
                try:
                    a = float(m.get("debut") or 0)
                    b = float(m.get("fin") if m.get("fin") is not None else a + 3)
                except (TypeError, ValueError):
                    continue
                if (url, round(a)) in used:
                    continue
                # a presenter / split screen at that moment: only when nothing better
                penalty = 6 if real_faults(e.get("defauts")) else 0
                options.append((RANK[e["niveau"]] + penalty, -(b - a), url, a, b, e))
        if not options:
            picks.append(None)
            continue
        _, _, url, a, b, e = min(options, key=lambda o: o[:2])
        used.add((url, round(a)))
        c = cands.get(url) or {}
        picks.append({"url": url, "titre": c.get("title") or verifs[url].get("title") or url, "niveau": e["niveau"],
                      "moment": {"debut": a, "fin": b}, "raison": e.get("raison") or "", "auto": True,
                      "remontage": False, "film": False, "defauts": real_faults(e.get("defauts"))})
    return picks


ORIGINS = {"youtube": "recherche YouTube", "langue": "recherche en langue locale", "image": "trouvée par image",
           "compte": "compte crédité", "action": "recherche par action"}


def _add(cands: List[Dict], c: Dict, origin: str, by_url: Dict[str, Dict]):
    """One card per video, whatever the number of searches that found it."""
    have = by_url.get(c["url"])
    if have:
        if origin not in have["origines"]:
            have["origines"].append(origin)
        have["hits"] = max(have.get("hits") or 0, c.get("hits") or 0)
        for k in ("duration", "views", "channel"):
            have[k] = have.get(k) or c.get(k)
        return
    c = {**c, "origines": [origin]}
    by_url[c["url"]] = c
    cands.append(c)


TEXT_ORIGINS = ("youtube", "langue", "compte")


def score(c: Dict) -> int:
    """How promising an unverified candidate is. Several pictures alone are a
    weak sign (the wells' excavator brought back excavator videos); found by a
    picture AND by words is the strongest."""
    o = c.get("origines") or []
    by_text = any(x in o for x in TEXT_ORIGINS)
    return (2 * min(c.get("hits") or 0, 2) + 2 * ("compte" in o) + ("langue" in o) + ("youtube" in o)
            + (4 if by_text and "image" in o else 0))


def _image_candidate(h: Dict) -> Dict:
    vid = _video_id(h["url"])
    return {"url": h["url"], "id": vid or h["url"], "title": h.get("title") or h["url"], "channel": h.get("platform", ""),
            "duration": None, "views": None, "hits": h.get("hits") or 0, "platform": h.get("platform", ""),
            "thumb": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else (h.get("thumb") or "")}


def suggest(ref: Dict, reference_url: str = "", work_dir: Optional[str] = None, search: Callable = None,
            search_in: Callable = None, sort: Callable = None, local: Callable = None, frames_fn: Callable = None,
            image_search: Callable = None, sort_image: Callable = None, wanted: Optional[List[Dict]] = None,
            report: Optional[Callable[[str, float], None]] = None) -> Dict:
    """The full "what to download" sheet: every way of finding the videos,
    merged per scene. Each part is best effort — one failing (Yandex blocked,
    no download of the Short) leaves the others."""
    from adaptation import frames as frames_mod, imagesearch
    search, search_in = search or search_youtube, search_in or search_channel
    sort, local = sort or sort_out, local or local_queries
    sort_image = sort_image or (lambda pools: sort_out(pools, prompt=SORT_IMAGE_PROMPT))
    frames_fn, image_search = frames_fn or frames_mod.reference_frames, image_search or imagesearch.timed_search
    report = report or (lambda phase, f: None)
    skip = {_video_id(reference_url)} - {None}
    skip_urls = {f"https://www.youtube.com/watch?v={v}" for v in skip} | {reference_url}
    found = wanted if wanted is not None else scenes(ref)      # "Script d'abord": the storyboard's images
    by_url = [{} for _ in found]

    # 1. text, in English then in the language of where it was filmed
    report("recherche : langues des scènes", 0.02)
    langs = local(found)
    for i, s in enumerate(found):
        report(f"recherche texte : scène {i + 1}/{len(found)}", 0.05 + 0.3 * i / max(1, len(found)))
        s["candidats"], s["liens"] = [], search_links(s["recherches"][0])
        if s.get("pub"):
            continue
        for q in s["recherches"][:2]:
            for c in search(q):
                if c["id"] not in skip:
                    _add(s["candidats"], c, "youtube", by_url[i])
        if i in langs:
            s["langue"] = langs[i]
            s["liens_langue"] = search_links(langs[i]["recherches"][0])
            for q in langs[i]["recherches"]:
                for c in search(q):
                    if c["id"] not in skip:
                        _add(s["candidats"], c, "langue", by_url[i])
    report("tri des résultats", 0.38)
    sort(found)
    for i, s in enumerate(found):
        s["candidats"] = s["candidats"][:PER_SCENE + 2]
        by_url[i] = {c["url"]: c for c in s["candidats"]}

    # 2. the Short's pictures, searched by image
    images = {"frames": [], "source": None, "error": None, "search_error": None}
    extra = []
    if work_dir:
        try:
            fr = frames_fn(ref, reference_url, work_dir, found,
                           report=lambda ph, f: report(ph, 0.42 + 0.18 * f))
            images.update(frames=fr["frames"], source=fr["source"], error=fr.get("error"))
        except Exception as e:
            images["error"] = str(e)[:200]
        if images["frames"]:
            report(f"recherche par image : {len(images['frames'])} images", 0.62)
            files = {f["file"]: os.path.join(work_dir, f["file"]) for f in images["frames"]}
            res = image_search(list(files.values()))
            images["search_error"], images["seconds"] = res.get("error"), res.get("seconds")
            hits = {k: res["hits"].get(path) or [] for k, path in files.items()}
            groups = {str(i): [files[f["file"]] for f in images["frames"] if f["scene"] == i] for i in range(len(found))}
            groups["all"] = [files[f["file"]] for f in images["frames"] if f["scene"] is None]
            ranked = imagesearch.rank({files[k]: v for k, v in hits.items()}, groups)
            pools = [{"scene": s["scene"], "candidats": [_image_candidate(h) for h in ranked.get(str(i)) or []
                                                         if h["url"] not in skip_urls]} for i, s in enumerate(found)]
            pools.append({"scene": "n'importe laquelle de ces scenes : " + " ; ".join(s["scene"] for s in found),
                          "candidats": [_image_candidate(h) for h in ranked.get("all") or [] if h["url"] not in skip_urls]})
            report("tri des résultats par image", 0.66)
            sort_image(pools)
            for i, s in enumerate(found):
                for c in [] if s.get("pub") else pools[i]["candidats"]:
                    _add(s["candidats"], c, "image", by_url[i])
            extra = pools[-1]["candidats"]
            for f in images["frames"]:
                f["videos"] = len(hits.get(f["file"]) or [])
    for s in found:
        for c in s["candidats"]:
            c["score"] = score(c)

    # 3. the credited accounts
    report("comptes crédités", 0.7)
    accounts = credit_links(ref.get("credits") or [])
    keyword = str(ref.get("recherche_courte") or "").strip() or \
        (found[0]["recherches"][0].split()[0] if found else "")
    for a in accounts:
        h = _handle(a["name"])
        a["videos"] = [{**v, "origines": ["compte"], "score": 2} for v in (search_in(h, keyword) if h and keyword else [])
                       if v["id"] not in skip]
    for c in extra:                     # a picture tied to no scene (YouTube's public frames): weaker
        c["origines"], c["score"] = ["image"], score({**c, "origines": ["image"]}) - 3
    return {"comptes": accounts, "scenes": found, "verifs": {}, "images": images, "image_videos": extra}


def all_candidates(sug: Dict) -> List[Dict]:
    seen, out = set(), []
    for c in [c for s in sug.get("scenes") or [] for c in s.get("candidats") or []] + \
             [v for a in sug.get("comptes") or [] for v in a.get("videos") or []] + list(sug.get("image_videos") or []) + \
             list(sug.get("perso") or []):
        if c["url"] not in seen:
            seen.add(c["url"])
            out.append(c)
    return out


def verify_best(sug: Dict, ref: Dict, n: int = 8, checker: Callable = None, workers: int = 3,
                report: Optional[Callable[[str, float], None]] = None) -> Dict:
    """Gemini watches the n most promising candidates, in parallel (a YouTube
    link takes ~15 s, a VK/Rutube file ~2 min). Results land in sug["verifs"];
    a failure is noted, never fatal."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    checker = checker or check
    report = report or (lambda phase, f: None)
    verifs = sug.setdefault("verifs", {})
    errors = sug.setdefault("verif_errors", {})
    ok = lambda c: c["url"] not in verifs and (c.get("duration") or 0) <= MAX_DURATION
    best = lambda cs: sorted((c for c in cs if ok(c)), key=lambda c: -(c.get("score") or 0))
    todo, picked = [], set()
    by_text = lambda c: any(x in (c.get("origines") or []) for x in TEXT_ORIGINS)
    account = sorted(best([v for a in sug.get("comptes") or [] for v in a.get("videos") or []]),
                     key=lambda c: -(c.get("views") or 0))       # its most watched: usually the one re-used
    if account and n:                                    # the credited account's best video: the strongest lead
        todo.append(account[0])
        picked.add(account[0]["url"])
    # each scene: its best found by words, then its best found by a picture — half the budget each
    for kind, cap in ((by_text, (n + 1) // 2), (lambda c: not by_text(c), n)):
        for s in sug.get("scenes") or []:
            top = next((c for c in best(s.get("candidats") or []) if kind(c) and c["url"] not in picked), None)
            if top and len(todo) < cap:
                todo.append(top)
                picked.add(top["url"])
    todo += [c for c in best(all_candidates(sug)) if c["url"] not in picked][:n - len(todo)]
    scenes_, plans = sug.get("scenes") or [], ref.get("plans") or []
    model = model_of(ref)
    extra = {"model": model} if model else {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(checker, c["url"], scenes_, plans, **extra): c for c in todo}
        for k, fut in enumerate(as_completed(futures)):
            c = futures[fut]
            report(f"vérification par l'IA : {k + 1}/{len(todo)}", (k + 1) / max(1, len(todo)))
            try:
                verifs[c["url"]] = fut.result()
            except Exception as e:
                errors[c["url"]] = str(e)[:200]
    return sug


# --------------------------------------------------------------- the Gemini check

CHECK_PROMPT = """On refait un Short viral avec d'autres images. Voici ses plans (ce qu'on voit dans chacun) :
{plans}

Regarde cette video et dis, POUR CHAQUE plan, si elle peut servir :
- "exacte" : c'est la video d'origine de ce plan (le meme evenement filme) ;
- "equivalente" : une AUTRE video qui montre la meme action de facon comparable et pourrait remplacer ce plan
  dans le montage (ex. une autre piscine qui cede sous des gens qui sautent). Pas besoin du meme lieu,
  des memes personnes ni des memes indices ;
- "partielle" : le meme evenement ou la meme action, mais pas tout ce que decrit le plan (ex. le jet de gaz
  du puits, sans la tentative de le boucher) : utile, a regarder ;
- "rien" : rien d'utilisable pour ce plan (seulement le meme theme general, ou une action differente).
Quand un plan donne la phrase dite pendant ce plan, le moment doit AUSSI l'illustrer : le spectateur entend la
phrase en regardant ce moment (une roulade pour "la roulade absorbe le choc", pas un simple atterrissage).
Le CADRAGE et la VITESSE ne comptent pas : le montage sait zoomer sur un detail et passer au ralenti. Un
plan demande "serre" ou "au ralenti" et filme ici de loin ou a vitesse normale reste "equivalente" si l'action
y est bien visible.
Pour "exacte", "equivalente" et "partielle", donne les moments ou on le voit (en secondes depuis le debut de la video),
PRECIS : du debut a la fin de l'action elle-meme, pas de la sequence autour.
{modele}"remontage" = true si cette video est elle-meme un montage d'un autre createur PAR-DESSUS les images de quelqu'un
d'autre (voix off, textes incrustes, Short explicatif ou compilation commentee), false si ce sont des images d'origine.
"film" = true si ce sont des images d'un FILM, d'une serie, d'un clip musical ou d'une emission TV (production
professionnelle avec des droits), false pour des videos de particuliers, de sportifs ou de createurs.
JSON uniquement :
{{"copie_du_modele": true/false, "remontage": true/false, "film": true/false,
  "plans": [{{"plan": numero, "niveau": "exacte | equivalente | partielle | rien",
             "moments": [{{"debut": s, "fin": s, "ce_qu_on_voit": "..."}}], "raison": "une phrase en francais",
             "defauts": "ce qui SE VOIT a ces moments et rend l'image inutilisable meme nettoyee : presentateur, interview,
                         ecran partage, ecran de fin, publicite, image fixe, image floue ou noire ; vide si l'image est propre
                         (un logo, un texte incruste ou le son ne sont PAS des defauts : ils sont effaces ou remplaces)"}}],
  "qualite": "bonne | moyenne | mauvaise (resolution, filigranes, texte incruste)",
  "resume": "une phrase en francais : ce que contient la video et a quoi elle peut servir"}}"""

LEVELS = ("exacte", "equivalente", "partielle", "rien")
VERDICT = {"exacte": "oui", "equivalente": "probable", "partielle": "partielle", "rien": "non"}


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


def _units(scenes_: List[Dict], plans: List[Dict]) -> List[Dict]:
    """What Gemini judges: the Short's plans that belong to a scene (a scene
    grouping two moments made a real source fail: "same event, but no
    excavator" -> nothing), or the scenes themselves for an older analysis."""
    units = []
    for k, pl in enumerate(plans or []):
        s = next((i for i, sc in enumerate(scenes_) if k in (sc.get("plans") or [])), None)
        text = str((pl or {}).get("visuel") or "").strip()
        if s is not None and text:
            units.append({"plan": k, "scene": s, "text": text, "indices": scenes_[s].get("indices") or ""})
    if not units:
        units = [{"plan": i, "scene": i, "indices": sc.get("indices") or "",
                  "text": sc.get("scene", "") + (f" — phrase dite pendant ce plan : « {sc['phrase']} »"
                                                 if sc.get("phrase") else "")}
                 for i, sc in enumerate(scenes_)]
    return units


def _youtube_title(url: str) -> str:
    """The title through YouTube's oEmbed (not the player page, which is the
    one that asks "not a bot"); empty on failure."""
    import urllib.request
    from urllib.parse import quote
    try:
        with urllib.request.urlopen(f"https://www.youtube.com/oembed?format=json&url={quote(url, safe='')}",
                                    timeout=10) as r:
            d = json.loads(r.read().decode())
        return " · ".join(x for x in (d.get("title"), d.get("author_name")) if x)
    except Exception:
        return ""


def _watch(url: str, g, prompt: str) -> Dict:
    """Gemini watches a YouTube link directly; anything else (VK, Rutube,
    TikTok…) is downloaded small and sent as a file."""
    if _video_id(url):
        answer = g._generate_content([{"file_data": {"file_uri": url}, "video_metadata": {"fps": 1}},
                                      {"text": prompt}], max_tokens=8000, timeout=240, temperature=0.1)
        if not (isinstance(answer, dict) and "403" in str(answer.get("error", ""))):
            return {"answer": answer, "duration": None, "title": _youtube_title(url)}
        # 403: Gemini may not open this one by its link (age or region limit): downloaded like the others
    import tempfile
    import yt_dlp
    from adaptation import sources
    with tempfile.TemporaryDirectory() as tmp:
        opts = ytdlp_opts(outtmpl=os.path.join(tmp, "c.%(ext)s"), format="best[height<=480]/worst/best",
                          noplaylist=True,          # "<=?": Instagram gives no duration, it must not be refused for that
                          match_filter=yt_dlp.utils.match_filter_func(f"duration <=? {MAX_DURATION}"))
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                path = ydl.prepare_filename(info)
        except Exception as e:
            raise FinderError(sources.explain(url, str(e)))
        if not os.path.exists(path):
            raise FinderError(f"Vidéo trop longue ou introuvable : {url}")
        up = g._upload_video_file(path)
        if not up:
            raise FinderError("Envoi de la vidéo à Gemini impossible.")
        try:
            if not g._wait_for_file_active(up["name"], timeout=240):
                raise FinderError("Gemini n'a pas fini de lire la vidéo à temps.")
            answer = g._generate_content([{"file_data": {"mime_type": up["mime_type"], "file_uri": up["uri"]}},
                                          {"text": prompt}], max_tokens=8000, timeout=240, temperature=0.1)
        finally:
            g._delete_file(up["name"])
        return {"answer": answer, "duration": info.get("duration") or sources.probe(path)["duration"],
                "title": " · ".join(x for x in (info.get("title"), info.get("uploader")) if x)}


MODEL_PART = """ATTENTION : on ne doit JAMAIS reutiliser le Short viral lui-meme. Il dure {duree} s et dit : "{texte}".
"copie_du_modele" = true si cette video EST ce Short ou un repost de son montage (meme suite de plans, memes
textes incrustes ou meme voix, meme duree), meme dans une autre langue ou recadre ; false si c'est une video d'origine
ou une autre video.
"""


def model_of(ref: Optional[Dict]) -> Optional[Dict]:
    """What a check needs to recognise a re-post of the reference itself."""
    if not ref or not (ref.get("script_complet") or "").strip():
        return None
    return {"texte": " ".join(str(ref["script_complet"]).split())[:900], "duree": ref.get("duree_s") or "?"}


def check(url: str, scenes_: List[Dict], plans: Optional[List[Dict]] = None, gemini=None,
          model: Optional[Dict] = None) -> Dict:
    """Gemini watches one candidate and judges it plan by plan (exact /
    equivalent / partial / nothing), with the moments; the plans are then
    summed up per scene for the page and the download."""
    from gemini_ai_generator import GeminiAIGenerator
    g = gemini or GeminiAIGenerator(api_key=os.getenv("GEMINI_API_KEY"))
    units = _units(scenes_, plans or [])
    listing = "\n".join(f"{n}. {u['text']}" + (f" (indices : {u['indices']})" if u["indices"] else "")
                        for n, u in enumerate(units, 1))       # numbered from 1: Gemini's reasons quote them
    seen = _watch(url, g, CHECK_PROMPT.format(plans=listing, modele=MODEL_PART.format(**model) if model else ""))
    r = seen["answer"]
    items = (r.get("plans") or r.get("scenes")) if isinstance(r, dict) else None
    if not isinstance(r, dict) or "error" in r or r.get("parsing_error") or not isinstance(items, list):
        raise FinderError(f"Vérification impossible : {str(r)[:160]}")
    par_plan, par_scene = {}, {}
    for e in items:
        if not isinstance(e, dict):
            continue
        try:
            n = int(e.get("plan", e.get("scene"))) - 1
        except (TypeError, ValueError):
            continue
        if not 0 <= n < len(units):
            continue
        level = str(e.get("niveau") or "").lower().strip().replace("é", "e")
        level = level if level in LEVELS else "rien"
        ms = [m for m in (e.get("moments") or []) if isinstance(m, dict)][:5] if level != "rien" else []
        u = units[n]
        par_plan[str(u["plan"])] = {"niveau": level, "moments": ms, "raison": str(e.get("raison") or ""),
                                    "scene": u["scene"], "defauts": real_faults(str(e.get("defauts") or ""))}
        have = par_scene.get(str(u["scene"]))
        if not have or LEVELS.index(level) < LEVELS.index(have["niveau"]):
            par_scene[str(u["scene"])] = {"niveau": level, "moments": list(ms) + (have or {}).get("moments", []),
                                          "raison": str(e.get("raison") or ""),
                                          "defauts": real_faults(str(e.get("defauts") or ""))}
        else:
            have["moments"] += ms
    copy = bool(model) and r.get("copie_du_modele") is True
    if copy:                            # the reference re-posted: never to be used, whatever it shows
        par_scene = {k: {**e, "niveau": "rien", "moments": [], "raison": "copie du Short modèle"} for k, e in par_scene.items()}
        par_plan = {k: {**e, "niveau": "rien", "moments": []} for k, e in par_plan.items()}
    moments = [m for e in par_plan.values() for m in e["moments"]]
    best = min((LEVELS.index(e["niveau"]) for e in par_plan.values()), default=3)
    return {"verdict": VERDICT[LEVELS[best]], "par_scene": par_scene, "par_plan": par_plan, "moments": moments,
            "copie": copy, "remontage": r.get("remontage") is True, "film": r.get("film") is True,
            "qualite": str(r.get("qualite") or ""), "raison": str(r.get("resume") or ""), "duration": seen["duration"],
            "title": seen.get("title") or ""}
