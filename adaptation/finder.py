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


ORIGINS = {"youtube": "recherche YouTube", "langue": "recherche en langue locale", "image": "trouvée par image",
           "compte": "compte crédité"}


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
            image_search: Callable = None, sort_image: Callable = None,
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
    found = scenes(ref)
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
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(checker, c["url"], scenes_, plans): c for c in todo}
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
Pour "exacte", "equivalente" et "partielle", donne les moments ou on le voit (en secondes depuis le debut de la video).
JSON uniquement :
{{"plans": [{{"plan": numero, "niveau": "exacte | equivalente | partielle | rien",
             "moments": [{{"debut": s, "fin": s, "ce_qu_on_voit": "..."}}], "raison": "une phrase en francais"}}],
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
        units = [{"plan": i, "scene": i, "text": sc.get("scene", ""), "indices": sc.get("indices") or ""}
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
        return {"answer": g._generate_content([{"file_data": {"file_uri": url}, "video_metadata": {"fps": 1}},
                                               {"text": prompt}], max_tokens=8000, timeout=240, temperature=0.1),
                "duration": None, "title": _youtube_title(url)}
    import tempfile
    import yt_dlp
    from adaptation import sources
    with tempfile.TemporaryDirectory() as tmp:
        opts = ytdlp_opts(outtmpl=os.path.join(tmp, "c.%(ext)s"), format="best[height<=480]/worst/best",
                          noplaylist=True, match_filter=yt_dlp.utils.match_filter_func(f"duration <= {MAX_DURATION}"))
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
        return {"answer": answer, "duration": info.get("duration"),
                "title": " · ".join(x for x in (info.get("title"), info.get("uploader")) if x)}


def check(url: str, scenes_: List[Dict], plans: Optional[List[Dict]] = None, gemini=None) -> Dict:
    """Gemini watches one candidate and judges it plan by plan (exact /
    equivalent / partial / nothing), with the moments; the plans are then
    summed up per scene for the page and the download."""
    from gemini_ai_generator import GeminiAIGenerator
    g = gemini or GeminiAIGenerator(api_key=os.getenv("GEMINI_API_KEY"))
    units = _units(scenes_, plans or [])
    listing = "\n".join(f"{n}. {u['text']}" + (f" (indices : {u['indices']})" if u["indices"] else "")
                        for n, u in enumerate(units, 1))       # numbered from 1: Gemini's reasons quote them
    seen = _watch(url, g, CHECK_PROMPT.format(plans=listing))
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
                                    "scene": u["scene"]}
        have = par_scene.get(str(u["scene"]))
        if not have or LEVELS.index(level) < LEVELS.index(have["niveau"]):
            par_scene[str(u["scene"])] = {"niveau": level, "moments": list(ms) + (have or {}).get("moments", []),
                                          "raison": str(e.get("raison") or "")}
        else:
            have["moments"] += ms
    moments = [m for e in par_plan.values() for m in e["moments"]]
    best = min((LEVELS.index(e["niveau"]) for e in par_plan.values()), default=3)
    return {"verdict": VERDICT[LEVELS[best]], "par_scene": par_scene, "par_plan": par_plan, "moments": moments,
            "qualite": str(r.get("qualite") or ""), "raison": str(r.get("resume") or ""), "duration": seen["duration"],
            "title": seen.get("title") or ""}
