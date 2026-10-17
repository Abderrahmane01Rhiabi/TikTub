"""
Reverse image search of the reference Short's pictures, automatic part.

Measured on two Shorts (2026-10-18), from this machine, through
PicImageSearch: Yandex answers (about 100 results per picture, no captcha
over 22 searches) and found two real sources of the tram Short (a Turkish
compilation with 5 exact shots, a VK compilation with 3); Google Lens
refused every automatic search (it works by hand in a browser, and found the
wells' source there), Bing's page no longer parses, TinEye only knows exact
copies of images. So: Yandex here, the others as buttons for a manual search.

Only video pages are kept, from the sites yt-dlp can read (ok.ru can't).
A video found by several pictures of the same scene ranks higher — a good
sign, not a proof: the Gemini check decides.
"""

import asyncio
import re
import time
from typing import Dict, List, Optional
from urllib.parse import urlsplit

VIDEO = re.compile(r"(youtube\.com/(watch|shorts/)|youtu\.be/|tiktok\.com/@[\w.-]+/video/|vk(video)?\.(com|ru)/video"
                   r"|rutube\.ru/video/|dailymotion\.com/video/|coub\.com/view/|facebook\.com/(.+/videos?/|reel/|watch)|fb\.watch/"
                   r"|instagram\.com/(reel|p)/|(x|twitter)\.com/[\w]+/status/)")
PLATFORMS = {"youtube": "YouTube", "youtu.be": "YouTube", "tiktok": "TikTok", "vk": "VK", "rutube": "Rutube",
             "dailymotion": "Dailymotion", "coub": "Coub", "facebook": "Facebook", "fb.watch": "Facebook",
             "instagram": "Instagram", "twitter": "X", "x.com": "X"}


class ImageSearchError(RuntimeError):
    pass


def _title(t: str) -> str:
    """Yandex's page titles carry the site: "Трамвай - Видео от X VK Видео", "… - YouTube"."""
    t = re.sub(r"\s+-\s+Видео от .*$", "", t)
    t = re.sub(r"\s+-\s+(YouTube|VK Видео|Dailymotion( Video)?|Coub|смотреть видео онлайн.*)$", "", t)
    return t.strip()


def platform(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    return next((v for k, v in PLATFORMS.items() if k in host), host)


def canonical(url: str) -> Optional[str]:
    """One spelling per video (Yandex adds tracking and mobile hosts), or None
    when the page is not a video yt-dlp can read."""
    url = re.sub(r"[?&]utm_[^&]*", "", url).rstrip("?&")
    if not VIDEO.search(url):
        return None
    yt = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", url)
    if yt:
        return f"https://www.youtube.com/watch?v={yt.group(1)}"
    vk = re.search(r"vk(?:video)?\.(?:com|ru)/(video-?\d+_\d+)", url)
    if vk:
        return f"https://vkvideo.ru/{vk.group(1)}"
    return url.replace("://m.", "://").split("#")[0]


async def _yandex(files: List[str], pause: float) -> Dict[str, List[Dict]]:
    from PicImageSearch import Network, Yandex
    out = {}
    async with Network(timeout=60) as client:
        engine = Yandex(client=client)
        for k, f in enumerate(files):
            if k:
                await asyncio.sleep(pause)
            try:
                r = await engine.search(file=f)
            except Exception as e:                        # one refused picture must not stop the others
                out[f] = {"error": str(e)[:200]}
                continue
            out[f] = [{"url": getattr(i, "url", "") or "", "title": (getattr(i, "title", "") or "")[:140],
                       "thumb": getattr(i, "thumbnail", "") or ""} for i in (r.raw or [])]
    return out


def search(files: List[str], pause: float = 1.5) -> Dict[str, List[Dict]]:
    """{file: [video hits]} — raises when Yandex answered nothing at all
    (blocked): the manual buttons are then the way."""
    raw = asyncio.run(_yandex(files, pause))
    if files and all(isinstance(v, dict) for v in raw.values()):
        raise ImageSearchError("Yandex n'a répondu à aucune image (blocage ou captcha) : "
                               + next(iter(raw.values()))["error"][:120])
    hits = {}
    for f, items in raw.items():
        seen, kept = set(), []
        for it in items if isinstance(items, list) else []:
            url = canonical(it["url"])
            if url and url not in seen:
                seen.add(url)
                kept.append({"url": url, "title": _title(it["title"]),
                             "thumb": it["thumb"] if it["thumb"].startswith("http") else "",
                             "platform": platform(url)})
        hits[f] = kept
    return hits


def rank(hits_by_frame: Dict[str, List[Dict]], frames_of: Dict[str, List[str]], limit: int = 8) -> Dict[str, List[Dict]]:
    """Per group (a scene), the videos found by its pictures, most pictures first.
    frames_of: {group: [frame files]}."""
    out = {}
    for group, files in frames_of.items():
        count, first = {}, {}
        for f in files:
            for k, h in enumerate(hits_by_frame.get(f) or []):
                count[h["url"]] = count.get(h["url"], 0) + 1
                if h["url"] not in first or k < first[h["url"]][0]:
                    first[h["url"]] = (k, h)
        best = sorted(count, key=lambda u: (-count[u], first[u][0]))[:limit]
        out[group] = [{**first[u][1], "hits": count[u]} for u in best]
    return out


def timed_search(files: List[str]) -> Dict:
    t = time.time()
    try:
        return {"hits": search(files), "error": None, "seconds": round(time.time() - t, 1)}
    except ImageSearchError as e:
        return {"hits": {}, "error": str(e), "seconds": round(time.time() - t, 1)}
