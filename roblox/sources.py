"""
The long video: its public facts, the moments people replay most (YouTube's
"most replayed" graph), its automatic subtitles timed per word, and only those
windows downloaded — never the whole video (a 2-hour one is read in minutes).
"""

import glob
import json
import os
from typing import Dict, List, Optional, Tuple

WINDOWS = 6             # passages looked at; each gives one to three moments
WINDOW_S = 75.0         # their length: YouTube's graph has 100 points, ~73 s each on a 2-hour video

Words = List[Tuple[str, float, float]]


class SourceError(RuntimeError):
    pass


def info(url: str, work: str) -> Dict:
    """Title, channel, duration, spoken language, the replay graph, the chapters, and the original-language automatic
    subtitles (json3, timed per word) saved in work/."""
    import yt_dlp
    from adaptation.finder import ytdlp_opts
    os.makedirs(work, exist_ok=True)
    opts = ytdlp_opts(quiet=True, skip_download=True, noplaylist=True, writeautomaticsub=True,
                      subtitleslangs=[".*-orig"], subtitlesformat="json3", outtmpl=os.path.join(work, "subs.%(ext)s"))
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            i = y.extract_info(url, download=True)
    except Exception as e:
        from adaptation import sources
        raise SourceError(sources.explain(url, str(e)))
    subs = sorted(glob.glob(os.path.join(work, "subs*.json3")))
    return {"titre": i.get("title") or "", "chaine": i.get("channel") or i.get("uploader") or "",
            "duree": float(i.get("duration") or 0), "langue": (i.get("language") or "en").split("-")[0],
            "vues": i.get("view_count"), "heatmap": i.get("heatmap") or [], "chapitres": i.get("chapters") or [],
            "sous_titres": subs[0] if subs else None}


def windows(meta: Dict, n: int = WINDOWS, size: float = WINDOW_S) -> List[List[float]]:
    """The passages to look at: around the most replayed points; without the graph, the chapters' starts, else
    spread evenly. Never overlapping, inside the video."""
    dur = meta.get("duree") or 0.0
    if dur <= size * 1.2:
        return [[0.0, round(dur, 1)]]
    if meta.get("heatmap"):
        centres = [(p["start_time"] + p["end_time"]) / 2 for p in sorted(meta["heatmap"], key=lambda p: -p["value"])]
    elif meta.get("chapitres"):
        centres = [c["start_time"] + size / 2 for c in meta["chapitres"]]
    else:
        centres = [dur * (k + 0.5) / n for k in range(n)]
    out = []
    for c in centres:
        a = min(max(0.0, c - size / 2), dur - size)
        if all(a + size <= x or a >= y for x, y in out):
            out.append([round(a, 1), round(a + size, 1)])
        if len(out) == n:
            break
    return sorted(out)


def words(path: Optional[str]) -> Words:
    """[(word, start, end)] in seconds of the long video, from YouTube's json3 subtitles; [] without them."""
    if not path or not os.path.exists(path):
        return []
    j = json.load(open(path, encoding="utf-8"))
    out = []
    for e in j.get("events") or []:
        t0 = e.get("tStartMs", 0)
        segs = [s for s in e.get("segs") or [] if s.get("utf8", "").strip()]
        for k, s in enumerate(segs):
            a = (t0 + (s.get("tOffsetMs") or 0)) / 1000
            b = (t0 + (segs[k + 1].get("tOffsetMs") or 0)) / 1000 if k + 1 < len(segs) else (t0 + e.get("dDurationMs", 800)) / 1000
            out.append((s["utf8"].strip(), a, max(b, a + 0.15)))
    return out


def download(url: str, work: str, wins: List[List[float]]) -> List[str]:
    """Each window as its own file (the app's downloader: cookies, formats, fallbacks)."""
    from adaptation import sources
    return [sources.download(url, work, f"w{int(a)}", sections=[[a, b]]) for a, b in wins]
