"""
Images v2 — the shots judged against each SENTENCE's idea, like a human editor (the lab of 2026-11-08,
docs/recherches/labo_images.md: of 41 shots of 3 Shorts, the wrong ones were judged against the whole subject —
« Casablanca being rebuilt » set aside as off-topic for a Cariane story —, missing — no footage of « families
receiving keys » —, from another place — NEOM shown as Benslimane — or all from one video).

  idea        every sentence gets a short English description of what any footage conveying it would show
              (the storyboard writes it: plan["idee"]; else one cheap call) — not the exact scene: « tomatoes are
              enough, no need for tomatoes in a precise place »
  match       a CLIP model on this PC scores every shot (3 pictures of it) against every sentence's idea:
              shot["colle"] = [score per sentence]. Measured: the right shot ~0.30-0.35, nothing fitting ~0.19
  rescue      a shot set aside as « off-topic » but fitting a sentence well is brought back
  place       news: the videos about another place or subject (their title, their description) are set aside —
              the real place first when it exists
  fallback    a sentence nothing fits: a general search on Pixabay, reranked by the same model; no AI-generated
              clip for the news family
Free (no Gemini but the ideas of an old storyboard and the place check: two short text calls). Without the model
installed the montage goes on as before.
"""

import json
import os
import subprocess
import threading
from typing import Dict, List, Optional

MODEL = ("ViT-B-16", "datacomp_xl_s13b_b90k")
FITS = 0.27                 # a shot that conveys a sentence's idea
NOTHING = 0.24              # no shot reaches it for a sentence: nothing fits, the fallback search is tried
MAX_PER_SOURCE = 2          # shots of one video in a montage (7 of 14 from one video felt the same)
PIXABAY_PER_IDEA = 20
THUMB_FITS = 0.22           # a Pixabay video's small picture that conveys the idea (a thumbnail scores lower)
_lock = threading.Lock()
_proc: Dict = {}
CALL_TIMEOUT = 600          # seconds for one request: the first loads torch and the model (~4 min on WSL)


def available() -> bool:
    try:
        import open_clip  # noqa: F401
        import torch  # noqa: F401
        return True
    except Exception:
        return False


def _worker(conn) -> None:
    """The model's own process: loaded once, it turns pictures and texts into vectors. Kept out of the web server —
    loading and running it there froze the app for a few seconds (« Le serveur ne répond pas »)."""
    import open_clip
    import torch
    from PIL import Image
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    model, _, pre = open_clip.create_model_and_transforms(MODEL[0], pretrained=MODEL[1], device=dev)
    model.eval()
    tok = open_clip.get_tokenizer(MODEL[0])
    while True:
        msg = conn.recv()
        if msg is None:
            break
        kind, data = msg
        try:
            with torch.no_grad():
                if kind == "img":
                    out = []
                    for i in range(0, len(data), 32):
                        batch = torch.stack([pre(Image.open(x).convert("RGB")) for x in data[i:i + 32]]).to(dev)
                        f = model.encode_image(batch)
                        out.append(f / f.norm(dim=-1, keepdim=True))
                    res = torch.cat(out)
                else:
                    f = model.encode_text(tok(data).to(dev))
                    res = f / f.norm(dim=-1, keepdim=True)
            conn.send(("ok", res.float().cpu().numpy()))
        except Exception as e:
            conn.send(("err", str(e)[:300]))


def _call(kind: str, data: List[str]):
    """One request to the model's process (started on first use, started again if it died)."""
    import multiprocessing as mp
    with _lock:
        if not _proc or not _proc["p"].is_alive():
            ctx = mp.get_context("spawn")
            parent, child = ctx.Pipe()
            proc = ctx.Process(target=_worker, args=(child,), daemon=True, name="tiktub-vision")
            proc.start()
            _proc.update(p=proc, conn=parent)
        _proc["conn"].send((kind, data))
        waited = 0
        while not _proc["conn"].poll(1):            # never waiting for ever on a process that died
            waited += 1
            if not _proc["p"].is_alive() or waited > CALL_TIMEOUT:
                _proc["p"].kill()
                _proc.clear()
                raise RuntimeError("recherche par le sens : le processus du modèle s'est arrêté")
        status, res = _proc["conn"].recv()
    if status != "ok":
        raise RuntimeError(f"recherche par le sens : {res}")
    return res


def warm() -> None:
    """Starts the model's process in the background (it takes ~4 min to load on WSL): called when a montage pro
    starts its search, it is ready by the time the stock is downloaded."""
    if not available():
        return

    def go():
        try:
            embed_texts(["warm up"])
        except Exception:
            pass
    threading.Thread(target=go, daemon=True, name="tiktub-vision-warm").start()


def embed_images(paths: List[str]):
    return _call("img", list(paths)) if paths else None


def embed_texts(texts: List[str]):
    return _call("txt", list(texts))


def _frames(shot: Dict, folder: str) -> List[str]:
    """3 pictures of a shot (its start, middle and end): one still missed what the shot shows."""
    os.makedirs(folder, exist_ok=True)
    out = []
    for j, at in enumerate((shot["start"] + 0.25, (shot["start"] + shot["end"]) / 2, shot["end"] - 0.25)):
        img = os.path.join(folder, f"{shot['id']}_{j}.jpg")
        if not os.path.exists(img):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.0, at):.2f}", "-i", shot["file"],
                            "-frames:v", "1", "-vf", "scale=-2:300", img], capture_output=True)
        if os.path.exists(img):
            out.append(img)
    return out or [shot["thumb"]]


def match(shots: List[Dict], ideas: List[str], folder: str) -> None:
    """shot["colle"] = its score against every sentence's idea (the best of its 3 pictures)."""
    if not shots or not ideas:
        return
    owners, paths = [], []
    for s in shots:
        for x in _frames(s, folder):
            owners.append(s["id"])
            paths.append(x)
    f = embed_images(paths)
    sc = (f @ embed_texts(ideas).T).tolist()
    best: Dict[str, List[float]] = {}
    worst: Dict[str, List[float]] = {}
    for o, row in zip(owners, sc):
        best[o] = [max(a, b) for a, b in zip(best.get(o, [-1.0] * len(ideas)), row)]
        worst[o] = [min(a, b) for a, b in zip(worst.get(o, [9.0] * len(ideas)), row)]
    for s in shots:
        s["colle"] = [round(v, 3) for v in best.get(s["id"], [0.0] * len(ideas))]
        # its worst picture: a shot whose content changes on the way (a Spanish stadium, then black-and-white
        # archives) fits with one picture only — never brought back for that
        s["colle_min"] = [round(v, 3) for v in worst.get(s["id"], [0.0] * len(ideas))]


def rescue(shots: List[Dict], n_sentences: int) -> List[str]:
    """Shots set aside as off-topic (or not described) that fit a sentence well with ALL their pictures (among its 3
    best) come back."""
    back = []
    for k in range(n_sentences):
        ranked = sorted((s for s in shots if s.get("colle")), key=lambda s: -s["colle"][k])[:3]
        for s in ranked:
            # off-topic for the whole subject, or never described (one still the describe could not read): the model
            # sees what the shot shows (« non décrit » S1_00 fitted « the city's works » at 0.32)
            # a shot with a defect stays out (the Raja TV logo over the supporters, 2026-11-10: it fits « supporters »),
            # and an official channel's shot never described too (its « Subscribe » card fitted « the Camp Nou »)
            if not s.get("garde") and s.get("ecarte") in ("hors sujet", "non décrit") and not s.get("probleme") \
                    and not (s.get("reserve") and not s.get("desc")) \
                    and s["colle"][k] >= FITS and (s.get("colle_min") or s["colle"])[k] >= NOTHING:
                s.update(garde=True, ecarte=None, repeche=k + 1)
                back.append(s["id"])
    return back


def missing(shots: List[Dict], n_sentences: int) -> List[int]:
    """The sentences (0-based) no kept shot conveys well — half-fitting shots too (contrails kept showing « the
    ceiling traps the Earth's heat »): the fallback search adds a choice, the editor still picks."""
    kept = [s for s in shots if s.get("garde") and s.get("colle")]
    return [k for k in range(n_sentences) if max((s["colle"][k] for s in kept), default=0.0) < FITS]


IDEAS_PROMPT = """Short video, voice-over sentences (any language):
{phrases}
For EACH sentence, write in English what a stock video conveying its MEANING would show — what the sentence makes
you understand or feel, not its words taken literally: the things and the action you SEE, general, not the exact
place or event, and no way of filming (no timelapse, close-up, drone, slow motion).
« new apartment buildings, a hand giving keys », not « families in El Harrouyine receiving keys » ;
« construction machines working on roads in a big city », not « timelapse of high-rise construction » ;
« this ceiling traps the Earth's heat » -> « the Earth heating up, heat waves shimmering over a hot city », not
« a thick cloud cover ».
5 to 12 words. JSON only: {{"idees": ["...", "..."]}}"""


def ideas_of(p: Dict, gemini=None) -> List[str]:
    """Every sentence's idea in English: the storyboard's, else written once now and kept on it."""
    from adaptation import realisateur
    plans = (p.get("storyboard") or {}).get("plans") or []
    directed = realisateur.ideas(p.get("realisation"))   # the director's visuals (all of a sentence's together)
    if directed and len(directed) == len(plans) and all(directed):
        return directed
    if plans and all(pl.get("idee") for pl in plans):
        own = [pl["idee"] for pl in plans]
        return [d or o for d, o in zip(directed, own)] if directed and len(directed) == len(plans) else own
    t = p["targets"][0]
    code = t["language"]
    phrases = [((pl.get("textes") or {}).get(code) or {}).get("texte") or "" for pl in plans] or \
        [x["texte"] for x in (t.get("script") or {}).get("passages") or []]
    from adaptation.script import _gemini
    try:
        r = (gemini or _gemini())._generate_content([{"text": IDEAS_PROMPT.format(
            phrases="\n".join(f"{k}. {x}" for k, x in enumerate(phrases, 1)))}], max_tokens=2000, timeout=60,
            temperature=0.2)
        ideas = [str(x) for x in (r or {}).get("idees") or []]
    except Exception:
        ideas = []
    if len(ideas) != len(phrases):                      # the precise image (French) rather than nothing
        ideas = [pl.get("image") or ph for pl, ph in zip(plans or [{}] * len(phrases), phrases)]
    if directed and len(directed) == len(ideas):        # the director's where it has one
        ideas = [d or x for d, x in zip(directed, ideas)]
    for pl, x in zip(plans, ideas):
        pl["idee"] = x
    return ideas


PLACE_PROMPT = """News Short about: {sujet}
Videos found for it (number | title | uploader):
{videos}
Give the COUNTRY the Short is about, then for EACH video the country it shows (in English, e.g. "Morocco", "Spain",
"Saudi Arabia", "France") and its place. Use "" for the country when you cannot tell or when the footage is generic
(machines, crowds, a city that could be anywhere). A title in another language about the same place has the same country.
JSON only: {{"pays_du_short": "...", "videos": [{{"n": 0, "pays": "...", "lieu": "short"}}]}}"""


def _country(x) -> str:
    return " ".join(str(x or "").lower().replace("the ", "").split())


def _places_once(sujet: str, rows, gemini) -> Dict[int, str]:
    """{video index: its place} for the videos of ANOTHER country than the Short's — compared here, not asked as
    yes/no (« another place? » set aside the live of another neighbourhood of Casablanca, and once let a Spanish
    stadium through)."""
    r = gemini._generate_content([{"text": PLACE_PROMPT.format(sujet=sujet, videos="\n".join(
        f"{k} | {m.get('titre') or ''} | {m.get('uploader') or m.get('handle') or ''}" for k, m in rows))}],
        max_tokens=2000, timeout=60, temperature=0.0)
    if not isinstance(r, dict) or not _country(r.get("pays_du_short")):
        return {}
    home, out = _country(r["pays_du_short"]), {}
    for v in r.get("videos") or []:
        try:
            c = _country(v.get("pays"))
            if c and c != home:
                out[int(v.get("n"))] = f"{v.get('lieu') or ''}, {v.get('pays')}".strip(" ,")[:80]
        except (TypeError, ValueError, AttributeError):
            continue
    return out


def other_places(sujet: str, metas: List[Optional[Dict]], gemini=None) -> Dict[int, str]:
    """News: the downloaded videos about another COUNTRY -> {index: that place}. Asked twice, a video set aside only
    when both answers agree, and never more than half of them (the real place first when it exists; another
    neighbourhood or city of the same country stays — it conveys the idea)."""
    rows = [(k, m) for k, m in enumerate(metas) if m and m.get("path")]
    if not rows:
        return {}
    from adaptation.script import _gemini
    g = gemini or _gemini()
    try:
        a, b = _places_once(sujet, rows, g), _places_once(sujet, rows, g)
    except Exception:
        return {}
    both = {k: a[k] for k in a if k in b}
    return both if len(both) * 2 <= len(rows) else {}


def _pixabay_key() -> Optional[str]:
    key = os.getenv("PIXABAY_API_KEY")
    if not key and os.path.exists(".env"):
        try:
            from dotenv import dotenv_values
            key = dotenv_values(".env").get("PIXABAY_API_KEY")
        except Exception:
            key = None
    return key or None


STOP = {"a", "an", "the", "of", "on", "in", "to", "and", "with", "at", "by", "for", "from", "into", "onto", "its", "their"}


def queries(idea: str) -> List[str]:
    """Short searches from an idea: its first words, its last words, and each part between commas."""
    words = [w.strip(",.;").lower() for w in idea.split()]
    words = [w for w in words if w and w not in STOP]
    parts = [" ".join(w for w in x.lower().split() if w not in STOP)[:60] for x in idea.split(",")]
    out = [" ".join(words[:3]), " ".join(words[-3:])] + [x for x in parts if x]
    return list(dict.fromkeys(q for q in out if q))[:4]


SEARCH_PROMPT = """Stock-footage searches (Pixabay works with 1 to 3 plain keywords, not sentences).
For each idea below, give 3 short searches that would find a video conveying it — the key THINGS you would see
(« house keys », « apartment building », « hand giving keys »), never a verb alone or a filler word.
{idees}
JSON only: {{"recherches": [["...", "...", "..."], ...]}} (one list per idea, same order)"""


def searches(ideas: List[str], gemini=None) -> List[List[str]]:
    """3 short keyword searches per idea, as a person would type them (one small call for all the ideas); the
    idea's own words when the call fails."""
    from adaptation.script import _gemini
    try:
        r = (gemini or _gemini())._generate_content([{"text": SEARCH_PROMPT.format(
            idees="\n".join(f"{k}. {x}" for k, x in enumerate(ideas, 1)))}], max_tokens=1500, timeout=60, temperature=0.2)
        got = [[str(q)[:40] for q in x if str(q).strip()][:3] for x in (r or {}).get("recherches") or []]
    except Exception:
        got = []
    return got if len(got) == len(ideas) and all(got) else [queries(x) for x in ideas]


def pixabay(idea: str, folder: str, n: int, no_ai: bool, used: set, words: Optional[List[str]] = None) -> Optional[Dict]:
    """The Pixabay video that best conveys an idea (its search reranked by the model), downloaded -> a shot."""
    import requests
    key = _pixabay_key()
    if not key:
        return None
    hits, seen = [], set()
    for q in words or queries(idea):                    # Pixabay searches by tags: short words find, a sentence does not
        for h in requests.get("https://pixabay.com/api/videos/", params={"key": key, "q": q, "per_page": PIXABAY_PER_IDEA,
                                                                         "safesearch": "true"}, timeout=30).json().get("hits") or []:
            if h["id"] not in seen:
                seen.add(h["id"])
                hits.append(h)
    os.makedirs(folder, exist_ok=True)
    cands = []
    for h in hits:
        if h["id"] in used or (no_ai and "ai generated" in (h.get("tags") or "").lower()):
            continue
        thumb = (h["videos"].get("small") or {}).get("thumbnail") or (h["videos"].get("tiny") or {}).get("thumbnail")
        if not thumb:
            continue
        path = os.path.join(folder, f"px_{h['id']}.jpg")
        try:
            if not os.path.exists(path):
                with open(path, "wb") as f:
                    f.write(requests.get(thumb, timeout=30).content)
            cands.append((h, path))
        except Exception:
            continue
    if not cands:
        return None
    sc = (embed_images([c[1] for c in cands]) @ embed_texts([idea]).T).squeeze(1).tolist()
    (h, thumb), score = max(zip(cands, sc), key=lambda x: x[1])
    if score < THUMB_FITS:
        return None
    v = h["videos"].get("medium") or h["videos"].get("small") or {}
    if not v.get("url"):
        return None
    mp4 = os.path.join(folder, f"pixabay_{h['id']}.mp4")
    if not os.path.exists(mp4):
        with requests.get(v["url"], stream=True, timeout=120) as r, open(mp4, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
    dur = float(h.get("duration") or 6)
    return {"id": f"PX_{n:02d}", "source": 1000 + n, "file": mp4, "start": 0.3, "end": round(min(dur - 0.2, 7.0), 2),
            "w": v.get("width"), "h": v.get("height"), "thumb": thumb, "credit": f"Pixabay — {h.get('user') or ''}".strip(" —"),
            "url": h.get("pageURL"), "titre_source": f"Pixabay : {h.get('tags') or ''}"[:120], "pixabay_id": h["id"],
            "garde": True, "ecarte": None, "secours_pour": None, "score_secours": round(score, 3)}


def report_line(shots: List[Dict]) -> Dict:
    """What Images v2 did to the stock, for the recipe and the screen."""
    return {"repeches": [s["id"] for s in shots if s.get("repeche")],
            "ailleurs": [s["id"] for s in shots if s.get("ecarte") == "autre lieu"],
            "secours": [s["id"] for s in shots if str(s.get("id", "")).startswith("PX_")]}


def save_scores(folder: str, shots: List[Dict]) -> None:
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "colle.json"), "w", encoding="utf-8") as f:
        json.dump({s["id"]: s.get("colle") for s in shots}, f)
