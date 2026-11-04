"""
A « Discours » Short (mode "discours" of the Adaptation, adaptation/discours_pipeline.py): a speech taken as it is,
the speaker's own voice and picture, cut to its strongest passage, illustrated, captioned in the channel's language.
The recipe measured in the lab (Downloads/montage_test/alex/test_montage_v4.py, 2026-11-03) on 4 @ofluminary Shorts
and the Grow with Alex tutorial:

    words        faster-whisper medium on the whole speech, word by word (this PC, free)
    passages     Gemini (text only) proposes the 2-3 strongest continuous passages, each from the start of a sentence
                 to the end of one; the person picks one and moves its ends word by word
    pauses       every pause over 0.45 s brought down to 0.25 s (the Demucs voice finds them, the cut keeps the room)
    cut-aways    about one every 2.5 s of speech, each a moment of a YouTube video WATCHED by Gemini (finder.check,
                 strict: nothing is erased here, a logo left on screen is a fault, one in a corner is cropped away);
                 films only on the channels that allow them (profile["discours"]["films"], the person's call)
    frame        the speaker framed on his face (square, 4:5 or 16:9), rounded, on black / his blurred picture / a
                 gradient of the channel's colour; dark grade (contrast 1.12, saturation 1.1) and a little grain
    captions     the caption library (captions/), the speaker's words, or their translation when the channel speaks
                 another language: each phrase's translation spread over that phrase's time, by length
    music        7 dB under the voice by default, its biggest rise on the punchline (« mot fort »)
"""

import json
import os
import re
import shutil
import subprocess
from typing import Callable, Dict, List, Optional, Tuple

W, H, FPS = 1080, 1920, 30
FRAMES = {"carre": (1, 1), "4:5": (4, 5), "16:9": (16, 9)}
FONDS = ("noir", "flou", "degrade")
GRADES = {"dark": "eq=contrast=1.12:saturation=1.1", "vivid": "eq=contrast=1.08:saturation=1.35", "aucun": ""}
DENSITY = {"faible": 3.5, "normale": 2.5, "forte": 1.7}       # seconds of speech per cut-away moment
DURATIONS = (30, 45, 60)
PAUSE_MIN, PAUSE_KEEP = 0.45, 0.25          # a pause longer than PAUSE_MIN is brought down to PAUSE_KEEP (s)
PLAN_S, PLAN_FAST_S, CLIP_LEN = 1.9, 0.8, 2.0   # a cut-away before / after the rise; the extract downloaded
HOOK_S = 2.0                                # the speaker alone first: no cut-away before this (s)
MAX_CHECKS = 2                              # videos watched per moment at most (the person's call, 2026-11-04: ~$0.25
                                            # a Discours instead of ~$0.50 with 4)
DROP_AT = 0.45                              # the rise without a punchline: this part of the Short
SPEECH_LUFS = -16.0                         # musique.bed sets the music under this level
FONT = os.path.join("montage", "fonts", "Montserrat-SemiBold.ttf")

# the « style Discours »: the base, then the channel's (profile["discours"]), then the video's (preview panel)
DEFAULTS = {"cadre": "carre", "taille": 84, "arrondi": 40, "fond": "noir", "ombre": False,
            "sous_titres": "escalier", "sous_titres_params": {}, "pauses": "resserrees", "densite": "normale",
            "etalonnage": "dark", "grain": True, "volume_db": 7.0, "drop_punchline": True, "identite": False}
CHANNEL_ONLY = {"films": False}             # a channel's own: may its cut-aways be films (Content ID risk)


class DiscoursError(RuntimeError):
    pass


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise DiscoursError((r.stderr or "")[-800:] or f"{os.path.basename(cmd[0])} s'est arrêté ({r.returncode})")
    return r


def _venc() -> List[str]:
    has = "h264_nvenc" in subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    return ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "19"] if has else ["-c:v", "libx264", "-preset", "fast", "-crf", "18"]


def duration(path: str) -> float:
    return float(_run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]).stdout.strip())


def size_of(path: str) -> Tuple[int, int]:
    out = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                "-of", "csv=p=0", path]).stdout.strip().split(",")
    return int(out[0]), int(out[1])


# ---------------------------------------------------------------- settings

def clean_settings(raw: Optional[Dict], base: Optional[Dict] = None) -> Dict:
    """`raw` over `base` (DEFAULTS when None), every value checked; what is unknown or wrong keeps the base's."""
    out = dict(base or DEFAULTS)
    raw = raw or {}
    if raw.get("cadre") in FRAMES:
        out["cadre"] = raw["cadre"]
    if raw.get("fond") in FONDS:
        out["fond"] = raw["fond"]
    if raw.get("etalonnage") in GRADES:
        out["etalonnage"] = raw["etalonnage"]
    if raw.get("densite") in DENSITY:
        out["densite"] = raw["densite"]
    if raw.get("pauses") in ("resserrees", "gardees"):
        out["pauses"] = raw["pauses"]
    for k, lo, hi in (("taille", 60, 100), ("arrondi", 0, 120)):
        if isinstance(raw.get(k), (int, float)) and not isinstance(raw.get(k), bool):
            out[k] = int(max(lo, min(hi, raw[k])))
    if isinstance(raw.get("volume_db"), (int, float)) and not isinstance(raw.get("volume_db"), bool):
        out["volume_db"] = float(max(3.0, min(30.0, raw["volume_db"])))
    for k in ("ombre", "grain", "drop_punchline", "identite"):
        if isinstance(raw.get(k), bool):
            out[k] = raw[k]
    if "sous_titres" in raw:
        from captions import styles as S
        st = S.get(raw.get("sous_titres") or "")
        if st and not st.native and "discours" in st.spaces:
            if st.id != out.get("sous_titres"):
                out["sous_titres_params"] = {}
            out["sous_titres"] = st.id
    if isinstance(raw.get("sous_titres_params"), dict):
        from captions import styles as S
        st = S.get(out["sous_titres"])
        out["sous_titres_params"] = st.clean(raw["sous_titres_params"]) if st else {}
    return out


def channel_settings(profile: Optional[Dict]) -> Dict:
    """A channel's « style Discours » (DEFAULTS + its own) and whether its cut-aways may be films."""
    own = (profile or {}).get("discours") or {}
    out = clean_settings(own)
    out["films"] = own.get("films") is True
    return out


def caption_style_for(settings: Dict, lang: str) -> str:
    """The style kept, or a style that works in Arabic when the chosen one does not (Escalier)."""
    from captions import styles as S
    from captions.core import rtl
    st = S.get(settings.get("sous_titres") or "")
    if st and (st.arabic or not rtl(lang)):
        return st.id
    return "escalier"


# ---------------------------------------------------------------- words

def transcribe(video: str) -> Tuple[List[List], str]:
    """([[word, start, end]...], the language Whisper heard: "en", "fr"...)."""
    from montage import transcribe as T
    segments, info = T._get_model().transcribe(video, word_timestamps=True)
    words = [[w.word.strip(), round(w.start, 2), round(w.end, 2)]
             for seg in segments for w in (seg.words or []) if w.word.strip()]
    return words, (info.language or "en")


def bare(word: str) -> str:
    return re.sub(r"^[\W_]+|[\W_]+$", "", str(word)).lower()


def listing(words: List[List], offset: float = 0.0) -> str:
    return " ".join(f"[{s - offset:.1f}] {w}" for w, s, _ in words)


# ---------------------------------------------------------------- passages

PASSAGES = """Voici la transcription mot a mot d'une video{titre} (chaque mot : [secondes] mot) :
{transcript}

On en fait un YouTube Short d'environ {duree} secondes (entre {mini} et {maxi} s de parole), avec la voix et l'image de
l'orateur. Propose les {n} MEILLEURS passages CONTINUS et DIFFERENTS (ils ne se chevauchent pas) : chacun garde les gens
jusqu'au bout tout seul (une idee complete, une chute forte), commence au debut d'une phrase et finit a la fin d'une
phrase. Classe-les du plus fort au moins fort. Pour chacun : "debut" et "fin" (secondes de la transcription), "titre"
(5 mots au plus, en francais), "pourquoi" (une phrase en francais), "note" (sur 10 : sa force pour un Short).
Dis aussi qui parle : "orateur" (son nom si la transcription, le titre ou la chaine le disent, sinon "").
JSON uniquement : {{"orateur": "...", "passages": [{{"debut": s, "fin": s, "titre": "...", "pourquoi": "...", "note": n}}]}}"""


def snap(words: List[List], a: float, b: float) -> Optional[Tuple[int, int]]:
    """The words from the first said at or after `a` to the last starting before `b` -> (i0, i1), or None."""
    idx = [i for i, w in enumerate(words) if a - 0.3 <= w[1] < b]
    if len(idx) < 3:
        return None
    return idx[0], idx[-1]


def span(words: List[List], i0: int, i1: int) -> Tuple[float, float]:
    """A passage's cut points: just before its first word, just after its last."""
    return max(0.0, words[i0][1] - 0.15), words[i1][2] + 0.25


def passages(words: List[List], target: int = 45, n: int = 3, title: str = "", avoid: Optional[List[Dict]] = None,
             gemini=None) -> Dict:
    """{"orateur", "passages": [{"i0", "i1", "debut", "fin", "titre", "pourquoi", "note"}]} — the strongest first.
    avoid: passages already proposed (« Chercher un autre passage »): not proposed again."""
    if len(words) < 20:
        raise DiscoursError("La vidéo n'a presque pas de parole : il faut un discours.")
    from adaptation.sources import _gemini
    g = gemini or _gemini()
    text = listing(words)
    if avoid:
        text += "\n\nDEJA PROPOSES (n'en propose AUCUN qui les chevauche) : " + "; ".join(
            f"{x['debut']:.0f}-{x['fin']:.0f} s" for x in avoid)
    prompt = PASSAGES.format(titre=f" (« {title} »)" if title else "", transcript=text, duree=target,
                             mini=int(target * 0.75), maxi=int(target * 1.35), n=n)
    for _ in range(3):
        r = g._generate_content([{"text": prompt}], max_tokens=8000, timeout=180, temperature=0.3)
        found = []
        for x in (r.get("passages") if isinstance(r, dict) else None) or []:
            try:
                got = snap(words, float(x["debut"]), float(x["fin"]))
            except (KeyError, TypeError, ValueError):
                continue
            if not got or any(not (got[1] < o["i0"] or got[0] > o["i1"]) for o in found + (avoid or [])):
                continue
            a, b = span(words, *got)
            if b - a < 8:
                continue
            try:
                note = max(0, min(10, int(float(x.get("note") or 0))))
            except (TypeError, ValueError):
                note = 0
            found.append({"i0": got[0], "i1": got[1], "debut": round(a, 2), "fin": round(b, 2),
                          "titre": str(x.get("titre") or "")[:60], "pourquoi": str(x.get("pourquoi") or ""), "note": note})
        if found:
            return {"orateur": str((r or {}).get("orateur") or "")[:80], "passages": found[:n]}
    raise DiscoursError("Gemini n'a pas trouvé de passage fort dans cette vidéo.")


# ---------------------------------------------------------------- the passage cut, its pauses tightened

def cut_passage(src: str, a: float, b: float, out: str) -> str:
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", src, "-c:v", "libx264",
          "-crf", "14", "-preset", "fast", "-c:a", "aac", "-b:a", "256k", out])
    return out


def tightened(vocals: str, total: float, keep: float = PAUSE_KEEP) -> List[List[float]]:
    """The parts kept: every pause over PAUSE_MIN brought down to `keep` (half on each side); the silence before
    the first word gone."""
    from adaptation import musique
    level = musique.lufs(vocals)
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", vocals, "-af",
                          f"silencedetect=noise={level - 22:.0f}dB:d={PAUSE_MIN}", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)] + [total]
    parts, at = [], 0.0
    for s, e in zip(starts, ends):
        s, e = max(0.0, s), min(total, e)
        if s <= 0.05:
            at = max(at, e - 0.08)
            continue
        a, b = s + keep / 2, e - keep / 2
        if b > a:
            parts.append([round(at, 3), round(a, 3)])
            at = b
    parts.append([round(at, 3), round(total, 3)])
    return [p for p in parts if p[1] - p[0] > 0.05]


def remap(t: float, parts: List[List[float]]) -> float:
    """A time of the passage -> its time once the pauses are cut (a time inside a cut pause: the next part's start)."""
    out = 0.0
    for a, b in parts:
        if t < a:
            return out
        if t <= b:
            return out + t - a
        out += b - a
    return out


def cut(seg: str, parts: List[List[float]], pic: str, snd: str) -> Tuple[str, str]:
    """The passage's picture and sound with only `parts` kept (15 ms fades on the sound: no click)."""
    n = len(parts)
    v = "".join(f"[0:v]trim={s:.3f}:{e:.3f},setpts=PTS-STARTPTS[v{i}];" for i, (s, e) in enumerate(parts))
    a = "".join(f"[0:a]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.015,"
                f"afade=t=out:st={max(0.0, e - s - 0.015):.3f}:d=0.015[a{i}];" for i, (s, e) in enumerate(parts))
    g = (v + a + "".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v];"
         + "".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[a]")
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", seg, "-filter_complex", g, "-map", "[v]", "-c:v", "libx264",
          "-crf", "14", "-preset", "fast", "-an", pic, "-map", "[a]", "-ar", "48000", snd])
    return pic, snd


# ---------------------------------------------------------------- cut-away moments

MOMENTS = """Voici un passage de discours (chaque mot : [secondes] mot) :
{transcript}
{orateur}
On le monte comme les Shorts « dark aesthetic » (@ofluminary) : un plan d'illustration presque a chaque phrase,
pendant que la voix continue. Donne {n} moments d'illustration DISTINCTS sur tout le passage (au moins 2 s entre deux
debuts). Chacun : {quoi}
Seulement des images qui EXISTENT sur YouTube ({ou}), jamais une scene a tourner.
Pour chacun : "mot" (le mot exact prononce ou le plan commence, tel qu'il est ecrit), "temps", "scene" (ce qu'on doit
voir, une phrase), "type" ("precis" quand la phrase cite une personne, un film, un lieu ou un evenement qu'il faut
MONTRER ; "ambiance" quand elle dit une idee ou une emotion : la grandeur, l'echec, n'abandonne jamais...),
"recherches" (2 recherches YouTube en anglais, la 2e plus large) et "ambiance" (une recherche en anglais pour une
banque d'images libres, 3 a 6 mots, un plan d'ambiance cinematographique de chaine de motivation qui porte l'emotion
de la phrase : une personne seule qui marche, un sportif qui s'entraine, une silhouette face a la ville, la pluie, une
route vide, un lever de soleil... ex. "man walking alone night city", "boxer training dark gym").
Environ la moitie des moments en "ambiance", jamais deux recherches "ambiance" identiques.
Puis "mots_forts" : 3 a 6 mots du passage (tels qu'ils sont ecrits) qui portent l'idee, et "mot_fort" : LE mot de la
chute, celui ou la musique doit monter.
JSON uniquement : {{"moments": [{{"mot": "...", "temps": s, "scene": "...", "type": "precis|ambiance",
"recherches": ["...", "..."], "ambiance": "..."}}],
"mots_forts": ["..."], "mot_fort": {{"mot": "...", "temps": s}}}}"""
WHAT = {True: ("une personne / un film / un lieu cite, OU une metaphore visuelle forte tiree d'un film connu (ex. « life "
               "is coming from you » -> Wonka qui souffle une bougie).", "extrait de film, ceremonie, archive, sport"),
        False: ("une personne / un lieu / un evenement cite (ceremonie, archive, emission TV, sport), OU une image concrete "
                "qui illustre la phrase. JAMAIS d'extrait de film de fiction, de serie ni de clip musical.",
                "ceremonie, emission TV, archive, sport, reportage, nature")}


def nearest_word(words: List[List], text: str, near: float) -> Optional[List]:
    """The word matching `text` closest to the time Gemini gave (its times can be a little off)."""
    t = bare((text or "").split()[0]) if (text or "").strip() else ""
    hits = [w for w in words if bare(w[0]) == t]
    return min(hits, key=lambda w: abs(w[1] - near)) if hits else None


def moments(local: List[List], speech_s: float, films: bool, density: str = "normale", speaker: str = "",
            gemini=None) -> Dict:
    """{"moments": [{"mot", "temps" (a word's start, passage time), "scene", "recherches"}], "mots_forts", "mot_fort"}."""
    from adaptation.sources import _gemini
    g = gemini or _gemini()
    n = max(4, min(16, round(speech_s / DENSITY.get(density, 2.5))))
    quoi, ou = WHAT[bool(films)]
    prompt = MOMENTS.format(transcript=listing(local), orateur=f"(l'orateur : {speaker})" if speaker else "",
                            n=n, quoi=quoi, ou=ou)
    for _ in range(3):
        r = g._generate_content([{"text": prompt}], max_tokens=8000, timeout=180, temperature=0.4)
        if not isinstance(r, dict) or not isinstance(r.get("moments"), list):
            continue
        out, last = [], -9.0
        for m in sorted((m for m in r["moments"] if isinstance(m, dict)), key=lambda m: float(m.get("temps") or 0)):
            try:
                w = nearest_word(local, str(m.get("mot") or ""), float(m.get("temps") or 0))
            except (TypeError, ValueError):
                continue
            qs = [str(q) for q in (m.get("recherches") or []) if str(q).strip()][:2]
            if not w or not qs or w[1] - last < 1.5:
                continue
            last = w[1]
            out.append({"mot": w[0], "temps": w[1], "scene": str(m.get("scene") or ""), "recherches": qs,
                        "type": "ambiance" if m.get("type") == "ambiance" else "precis",
                        "ambiance": " ".join(str(m.get("ambiance") or "").split())[:80]})
        if out:
            strong = [bare(x) for x in (r.get("mots_forts") or []) if bare(x)][:6]
            mf = r.get("mot_fort") if isinstance(r.get("mot_fort"), dict) else {}
            try:
                hit = nearest_word(local, str(mf.get("mot") or ""), float(mf.get("temps") or 0))
            except (TypeError, ValueError):
                hit = None
            return {"moments": out, "mots_forts": strong, "mot_fort": {"mot": hit[0], "temps": hit[1]} if hit else None}
    raise DiscoursError("Gemini n'a pas proposé de plans d'illustration.")


def _search(query: str, n: int = 5) -> List[Dict]:
    from adaptation import finder
    return finder.search_youtube(query, n)


def find_clip(item: Dict, films: bool, used: set, work: str, exclude: str = "", log: Optional[List[str]] = None,
              checker: Optional[Callable] = None, search: Optional[Callable] = None,
              download: Optional[Callable] = None) -> Optional[Dict]:
    """The first YouTube result Gemini sees matching (exact / equivalent, nothing left on screen, not a film when
    the channel refuses them; a ceremony or a TV show is not one), MAX_CHECKS watched at most
    -> {"url", "titre", "niveau", "film" (fiction), "extraits": [{"path", "debut"}]}, or None."""
    from adaptation import finder, sources
    checker = checker or (lambda url, scene, phrase: finder.check(url, [{"scene": scene, "phrase": phrase, "indices": ""}],
                                                                  strict=True))
    search = search or _search
    download = download or (lambda url, a, name: sources.download(url, work, name, sections=[[a, a + CLIP_LEN]]))
    log = log if log is not None else []
    seen, cands = set(), []
    for q in item.get("recherches") or []:
        for c in search(q)[:4]:
            url = c.get("url") or ""
            key = finder.same_video(url) if url else ""
            title = (c.get("title") or "").strip().lower()
            if not url or key in seen or title in seen:
                continue
            seen |= {key, title}
            cands.append(c)
    checks = 0
    for c in cands:
        if checks >= MAX_CHECKS:
            break
        url = c["url"]
        vid = finder.same_video(url)
        dur = c.get("duration")
        if vid in used or (exclude and vid == finder.same_video(exclude)) or (dur and not 5 <= float(dur) <= 1800):
            continue
        checks += 1
        try:
            v = checker(url, item.get("scene") or "", item.get("mot") or "")
        except Exception as e:
            log.append(f"✗ {(c.get('title') or url)[:50]} : {str(e)[:80]}")
            continue
        e = (v.get("par_scene") or {}).get("0") or {}
        level, ms = e.get("niveau", "rien"), e.get("moments") or []
        if level not in ("exacte", "equivalente") or e.get("defauts") or not ms or v.get("telechargeable") is False:
            log.append(f"✗ {(c.get('title') or url)[:50]} : {level}{' · ' + e['defauts'] if e.get('defauts') else ''}")
            continue
        if v.get("fiction") and not films:
            log.append(f"✗ {(c.get('title') or url)[:50]} : film, série ou clip (pas autorisé sur cette chaîne)")
            continue
        got = []
        for k, m in enumerate(ms[:2]):
            try:
                a = round(max(0.0, float(m.get("debut", 0))), 1)
                path = download(url, a, f"{re.sub(r'[^A-Za-z0-9_-]', '', vid)[:20]}_{k}")
            except Exception as err:
                log.append(f"✗ extrait {a} s : {str(err)[:80]}")
                continue
            if path and os.path.exists(path):
                got.append({"path": path, "debut": a})
        if got:
            log.append(f"✓ {(c.get('title') or url)[:50]} : {level}, {len(got)} moment(s)")
            return {"url": url, "titre": c.get("title") or v.get("title") or "", "niveau": level,
                    "film": bool(v.get("fiction")), "extraits": got}
    return None


# ---------------------------------------------------------------- mood shots (Pixabay: free, no logo, nothing to watch)

STOCK_DIR = os.path.join("assets", "stock_discours")   # every clip downloaded once, shared by the projects
STOCK_MIN_W = 1920
STOCK_STOP = {"the", "and", "with", "into", "from", "cinematic", "shot", "footage", "dramatic", "lighting", "slow",
              "motion", "video", "scene"}
AMBIANCE = """Voici des moments d'un discours de motivation, chacun avec ce qu'on devait y voir :
{lignes}
Pour chacun, une recherche en anglais pour une banque d'images libres (3 a 6 mots) : un plan d'ambiance
cinematographique de chaine de motivation qui porte l'emotion de la phrase (une personne seule qui marche, un sportif
qui s'entraine, une silhouette face a la ville, la pluie, une route vide, un lever de soleil...). Toutes differentes.
JSON uniquement : {{"recherches": ["...", ...]}} (dans l'ordre, une par moment)"""


def ambiance_for(items: List[Dict], gemini=None) -> List[str]:
    """The stock searches of moments that have none (a project made before them): one short text call."""
    from adaptation.sources import _gemini
    g = gemini or _gemini()
    lines = "\n".join(f"{k + 1}. « {m.get('mot')} » : {m.get('scene')}" for k, m in enumerate(items))
    r = g._generate_content([{"text": AMBIANCE.format(lignes=lines)}], max_tokens=2000, timeout=120, temperature=0.5)
    qs = [" ".join(str(q).split())[:80] for q in ((r or {}).get("recherches") or [])] if isinstance(r, dict) else []
    return [qs[k] if k < len(qs) and qs[k] else "person walking alone cinematic" for k in range(len(items))]


STOCK_CHOICES = 12                   # the propositions kept per moment, for the person to choose from


def stock_search(query: str, used: set, api_key: Optional[str] = None, get: Optional[Callable] = None) -> List[Dict]:
    """The Pixabay shots for `query` the channels have not used yet (Full HD at least), best tag match first:
    [{"stock": "pixabay:<id>", "tags", "page", "image", "apercu" (a small preview), "src", "duree"}]. Free: no Gemini."""
    import requests
    key = os.getenv("PIXABAY_API_KEY") if api_key is None else api_key
    if not key or not query:
        return []
    get = get or requests.get
    r = get("https://pixabay.com/api/videos/", params={"key": key, "q": query, "per_page": 30, "safesearch": "true"},
            timeout=30)
    r.raise_for_status()
    words = {w for w in re.findall(r"[a-z]+", query.lower()) if len(w) > 2 and w not in STOCK_STOP}

    def fit(hit):                     # the shot whose tags say the most of the search (Pixabay ranks by popularity)
        tags = set(re.findall(r"[a-z]+", (hit.get("tags") or "").lower()))
        return len(words & tags)
    out = []
    for hit in sorted(r.json().get("hits", []), key=lambda h: -fit(h)):     # stable: Pixabay's order between equals
        sid = f"pixabay:{hit['id']}"
        vids = hit.get("videos") or {}
        v = next((vids[k] for k in ("medium", "large", "small")
                  if vids.get(k, {}).get("url") and vids[k].get("width", 0) >= STOCK_MIN_W), None)
        if sid in used or not v or hit.get("isLowQuality"):
            continue
        tiny = vids.get("tiny") or vids.get("small") or {}
        out.append({"stock": sid, "tags": hit.get("tags") or "", "page": hit.get("pageURL") or "",
                    "image": tiny.get("thumbnail") or v.get("thumbnail") or "", "apercu": tiny.get("url") or v["url"],
                    "src": v["url"], "duree": float(hit.get("duration") or 6)})
        if len(out) >= STOCK_CHOICES:
            break
    return out


def stock_take(cand: Dict, query: str, work: str, fetch: Optional[Callable] = None) -> Dict:
    """One proposition downloaded once into STOCK_DIR, its 2 s taken a third of the way in -> a clip like
    find_clip's ({"stock": "pixabay:<id>"})."""
    import requests
    pid = cand["stock"].split(":", 1)[1]
    os.makedirs(STOCK_DIR, exist_ok=True)
    src = os.path.join(STOCK_DIR, f"{pid}.mp4")
    if not os.path.exists(src):
        if fetch:
            fetch(cand["src"], src)
        else:
            with requests.get(cand["src"], timeout=300, stream=True) as dl:
                dl.raise_for_status()
                with open(src + ".part", "wb") as fh:
                    for chunk in dl.iter_content(1 << 20):
                        fh.write(chunk)
            os.replace(src + ".part", src)
    os.makedirs(work, exist_ok=True)
    a = round(max(0.0, cand.get("duree", 6) / 3), 1)
    out = os.path.join(work, f"pixabay_{pid}.mp4")
    if not os.path.exists(out):
        _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{a:.1f}", "-t", f"{CLIP_LEN + 0.3:.1f}", "-i", src,
              "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", out])
    return {"url": cand.get("page") or "", "titre": cand.get("tags") or query, "niveau": "ambiance", "film": False,
            "stock": cand["stock"], "recherche": query, "extraits": [{"path": out, "debut": 0.0}]}


def stock_clip(query: str, used: set, work: str, api_key: Optional[str] = None, get: Optional[Callable] = None,
               fetch: Optional[Callable] = None, candidates: Optional[List[Dict]] = None) -> Optional[Dict]:
    """The best Pixabay shot for `query` not used yet (from `candidates` when already searched), or None."""
    cands = stock_search(query, used, api_key, get) if candidates is None else candidates
    cand = next((c for c in cands if c["stock"] not in used), None)
    return stock_take(cand, query, work, fetch) if cand else None


def shots(anchors: List[Tuple[float, List[str]]], word_starts: List[float], total: float, drop: float) -> List[Tuple]:
    """The cut-aways on the cut timeline: [(start, end, clip, offset in the clip)], none before HOOK_S (the speaker
    first). Each extract up to PLAN_S s, ending
    on a word like their cuts; after the rise, two quick plans of PLAN_FAST_S; two moments at once: one after the other."""
    out, starts, free = [], [], 0.0
    anchors = sorted(((max(t, HOOK_S), c) for t, c in anchors), key=lambda x: x[0])
    for t, _ in anchors:
        starts.append(max(t, free))
        free = starts[-1] + 1.0
    for i, ((_, clips), t) in enumerate(zip(anchors, starts)):
        nxt = starts[i + 1] if i + 1 < len(starts) else total - 0.05
        s = t
        for clip in clips:
            fast = s >= drop
            e = s + (PLAN_FAST_S * 2 if fast else PLAN_S)
            on_word = [x for x in word_starts if s + 0.6 <= x <= e]
            if on_word:
                e = max(on_word)
            e = min(e, nxt - 0.02, total - 0.05)
            if e - s < 0.5:
                break
            if fast and e - s > PLAN_FAST_S + 0.3:
                mid = s + (e - s) / 2
                out += [(round(s, 3), round(mid, 3), clip, 0.0), (round(mid, 3), round(e, 3), clip, round(mid - s, 3))]
            else:
                out.append((round(s, 3), round(e, 3), clip, 0.0))
            s = e
    return out


# ---------------------------------------------------------------- captions in the channel's language

def phrases_of(words: List[List]) -> List[Tuple[int, int]]:
    """The passage cut into phrases for the translation: at a sentence's end, at a comma after 4 words, at 10 words."""
    out, start = [], 0
    for i, (w, _, _) in enumerate(words):
        n = i - start + 1
        if w[-1:] in ".!?…" or (w[-1:] in ",;:" and n >= 4) or n >= 10 or i == len(words) - 1:
            out.append((start, i))
            start = i + 1
    return out


TRANSLATE = """Voici un passage de discours en {source}, phrase par phrase (numerotees) :
{phrases}

Pour des sous-titres, traduis CHAQUE phrase en {langues} : fidele au sens et au ton de l'orateur, naturel a lire, pas plus
long que l'original. Le francais avec tous ses accents (é, è, à, ç...) ; l'arabe en arabe standard moderne, sans voyelles.
Pour chaque langue aussi : "mots_forts" (3 a 6 mots de TA traduction, ecrits comme dans ta traduction, qui portent
l'idee) et "youtube" = {{"titre" (100 caracteres max, 1-2 emojis, qui donne envie de regarder), "description" (2-3 phrases
qui nomment l'orateur{orateur} + 3 a 5 hashtags dont #shorts), "tags" (8 a 12)}}.
JSON uniquement : {{"phrases": [{{"n": numero, {cles}}}], "langues": {{{cles_langues}}}}}"""
LANG_NAMES = {"fr": "francais", "ar": "arabe standard moderne (sans voyelles)", "en": "anglais", "es": "espagnol",
              "de": "allemand", "it": "italien", "pt": "portugais"}


def translate(local: List[List], source: str, codes: List[str], speaker: str = "", gemini=None) -> Dict:
    """{"phrases": [{"i0", "i1", code: text}], "langues": {code: {"mots_forts", "youtube"}}} — the phrases in every
    language of the channels (the speaker's own words for his language), the YouTube texts of each."""
    from adaptation.sources import _gemini
    g = gemini or _gemini()
    groups = phrases_of(local)
    lines = "\n".join(f"{k + 1}. {' '.join(w[0] for w in local[a:b + 1])}" for k, (a, b) in enumerate(groups))
    prompt = TRANSLATE.format(source=LANG_NAMES.get(source, source), phrases=lines,
                              langues=", ".join(f"{LANG_NAMES.get(c, c)} (cle \"{c}\")" for c in codes),
                              orateur=f" ({speaker})" if speaker else "",
                              cles=", ".join(f'"{c}": "..."' for c in codes),
                              cles_langues=", ".join(f'"{c}": {{"mots_forts": [], "youtube": {{}}}}' for c in codes))
    for _ in range(3):
        r = g._generate_content([{"text": prompt}], max_tokens=16000, timeout=240, temperature=0.3)
        if not isinstance(r, dict) or not isinstance(r.get("phrases"), list):
            continue
        by_n = {}
        for x in r["phrases"]:
            try:
                by_n[int(x.get("n"))] = x
            except (TypeError, ValueError, AttributeError):
                continue
        out = []
        for k, (a, b) in enumerate(groups):
            x = by_n.get(k + 1) or {}
            own = " ".join(w[0] for w in local[a:b + 1])
            row = {"i0": a, "i1": b}
            for c in codes:
                row[c] = own if c == source else " ".join(str(x.get(c) or "").split())
            out.append(row)
        if any(not row[c] for row in out for c in codes):
            continue
        langs_ = r.get("langues") if isinstance(r.get("langues"), dict) else {}
        info = {}
        for c in codes:
            d = langs_.get(c) if isinstance(langs_.get(c), dict) else {}
            info[c] = {"mots_forts": [bare(x) for x in (d.get("mots_forts") or []) if bare(x)][:6],
                       "youtube": youtube_of(d.get("youtube"), speaker)}
        return {"phrases": out, "langues": info}
    raise DiscoursError("Gemini n'a pas réussi à traduire le passage.")


def youtube_of(raw, speaker: str = "") -> Dict:
    raw = raw if isinstance(raw, dict) else {}
    title = " ".join(str(raw.get("titre") or speaker or "Discours").split())[:100]
    desc = str(raw.get("description") or "").strip()
    if "#shorts" not in desc.lower():
        desc = (desc + " #shorts").strip()
    tags = [str(t).strip() for t in (raw.get("tags") or []) if str(t).strip()][:12]
    return {"titre": title, "description": desc, "tags": tags}


def spread(text: str, a: float, b: float) -> List[List]:
    """A translated phrase's words over [a, b], each given time by its length (+1 for the space)."""
    ws = text.split()
    if not ws:
        return []
    total = sum(len(w) + 1 for w in ws)
    out, t = [], a
    for w in ws:
        d = (b - a) * (len(w) + 1) / total
        out.append([w, round(t, 3), round(t + d - 0.02, 3)])
        t += d
    return out


def caption_words(local: List[List], parts: List[List[float]], translation: Optional[Dict], code: str,
                  source: str) -> List[List]:
    """The captions' words on the cut timeline: the speaker's own (his language), or each phrase's translation spread
    over that phrase's time."""
    if code == source or not translation:
        return [[w, remap(s, parts), remap(e, parts)] for w, s, e in local]
    out = []
    for row in translation["phrases"]:
        a = remap(local[row["i0"]][1], parts)
        b = remap(local[row["i1"]][2], parts)
        out += spread(row.get(code) or "", a, max(b, a + 0.3))
    return out


# ---------------------------------------------------------------- the frame

def frame_box(settings: Dict) -> Tuple[int, int, int, int]:
    """(x, y, w, h) of the speaker's frame on the 1080x1920 canvas, centred."""
    aw, ah = FRAMES.get(settings.get("cadre"), (1, 1))
    fw = int(W * settings.get("taille", 84) / 100) // 2 * 2         # 84 %: 906, the lab's
    fh = int(round(fw * ah / aw / 2) * 2)
    if fh > 1500:
        fh = 1500
        fw = int(round(fh * aw / ah / 2) * 2)
    return (W - fw) // 2, (H - fh) // 2, fw, fh


def speaker_crop(pic: str, fw: int, fh: int) -> str:
    """The crop of the speaker's picture at the frame's shape, centred on his face (the middle when none is seen)."""
    vw, vh = size_of(pic)
    cw = min(vw, int(vh * fw / fh))
    ch = min(vh, int(cw * fh / fw))
    cw, ch = cw - cw % 2, ch - ch % 2
    cx, cy = vw / 2, vh * 0.4
    try:
        from captions import render as R
        found = R.faces(pic, (0, 0, vw, vh), fps=1.0, fit="stretch")
        if found:
            xs = sorted((b[0] + b[2]) / 2 for _, b in found)
            ys = sorted((b[1] + b[3]) / 2 for _, b in found)
            cx, cy = xs[len(xs) // 2], ys[len(ys) // 2]
    except Exception:
        pass
    x = int(max(0, min(vw - cw, cx - cw / 2)))
    y = int(max(0, min(vh - ch, cy - ch * 0.38)))
    return f"crop={cw}:{ch}:{x}:{y}"


def _mask(fw: int, fh: int, radius: int, path: str) -> str:
    from PIL import Image, ImageDraw
    img = Image.new("L", (fw, fh), 0)
    ImageDraw.Draw(img).rounded_rectangle([0, 0, fw - 1, fh - 1], max(0, radius), fill=255)
    img.save(path)
    return path


def _shadow(box, radius: int, path: str) -> str:
    from PIL import Image, ImageDraw, ImageFilter
    x, y, fw, fh = box
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([x, y + 18, x + fw, y + fh + 18], radius, fill=(0, 0, 0, 200))
    img.filter(ImageFilter.GaussianBlur(28)).save(path)
    return path


def _gradient(colour: str, path: str) -> str:
    from PIL import Image
    c = colour.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4)) if len(c) == 6 else (40, 40, 40)
    img = Image.new("RGB", (1, 256))
    for i in range(256):
        k = max(0.0, 1 - i / 200) * 0.55
        img.putpixel((0, i), (int(r * k), int(g * k), int(b * k)))
    img.resize((W, H)).save(path)
    return path


def _fp(path: str) -> str:
    from captions.render import _fp as fp
    return fp(path)


# ---------------------------------------------------------------- render

def render(pic: str, speech: str, plan: List[Tuple], words: List[List], lang: str, settings: Dict, bed: Optional[str],
           out: str, work: str, strong: Optional[set] = None, channel: Optional[str] = None,
           signature: str = "") -> str:
    """The Short: the frame (the speaker, the cut-aways over him, graded) on its background, the captions of the
    library, the speech with the music bed under it."""
    from captions import render as R
    from captions.core import Ctx
    os.makedirs(work, exist_ok=True)
    total = duration(speech)
    box = frame_box(settings)
    fx, fy, fw, fh = box
    # 1. the frame alone, at its size: the speaker framed on his face, the cut-aways, the grade and the grain
    fg = os.path.join(work, "cadre.mp4")
    inputs = ["-i", pic]
    g = [f"[0:v]{speaker_crop(pic, fw, fh)},scale={fw}:{fh},setsar=1,fps={FPS}[c0]"]
    cur = "c0"
    for i, (s, e, clip, off) in enumerate(plan):
        inputs += ["-i", clip]
        g.append(f"[{i + 1}:v]trim={off:.3f}:{off + e - s + 0.05:.3f},setpts=PTS-STARTPTS+{s:.3f}/TB,"
                 f"scale={fw}:{fh}:force_original_aspect_ratio=increase,crop={fw}:{fh},setsar=1,fps={FPS}[b{i}]")
        g.append(f"[{cur}][b{i}]overlay=enable='between(t,{s:.3f},{e:.3f})':eof_action=pass[c{i + 1}]")
        cur = f"c{i + 1}"
    look = [x for x in (GRADES.get(settings.get("etalonnage"), ""), "noise=alls=5:allf=t" if settings.get("grain") else "") if x]
    g.append(f"[{cur}]{','.join(look + ['format=yuv420p'])}[fg]")
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(g), "-map", "[fg]",
          "-t", f"{total:.3f}", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", fg])
    # 2. the captions, placed on what the frame shows (faces, busy bands)
    style = caption_style_for(settings, lang)
    params = settings.get("sous_titres_params") or {}
    ctx = R.context(lang, box, words, keywords=sorted(strong or []), channel=channel)
    ctx = R.analyse(ctx, style, params, fg, fit="stretch", until=total)
    built = R.build(style, words, ctx, params)
    mask_video = None
    if built.extras.get("behind") and ctx.faces:
        try:                                          # « Derrière » : the big words under the speaker (SAM 2.1)
            canvas = os.path.join(work, "cadre_canvas.mp4")
            _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", fg, "-vf", f"pad={W}:{H}:{fx}:{fy}", "-c:v", "libx264",
                  "-preset", "veryfast", "-crf", "18", canvas])
            m = R.person_mask(canvas, box, ctx.faces, os.path.join(work, "personne.mp4"))
            mask_video = (m, box) if m else None
        except Exception as e:
            print(f"⚠️ Masque de l'orateur impossible ({e}) : les grands mots devant lui")
    # 3. background + rounded frame + captions + signature, speech + music
    inputs = ["-i", fg, "-i", speech, "-loop", "1", "-i", _mask(fw, fh, settings.get("arrondi", 40), os.path.join(work, "masque.png"))]
    count = [3]

    def add_input(*args):
        inputs.extend(args)
        count[0] += 1
        return count[0] - 1
    g = ["[2:v]format=gray[m]", "[0:v]split[f1][f2]", "[f1]format=yuva420p[fa]", "[fa][m]alphamerge[fr]"]
    fond = settings.get("fond")
    if fond == "flou":
        g.append(f"[f2]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=40:3,"
                 f"eq=brightness=-0.22,setsar=1[bg]")
    elif fond == "degrade":
        gi = add_input("-loop", "1", "-i", _gradient(R.channel_colour(channel), os.path.join(work, "degrade.png")))
        g += ["[f2]nullsink", f"[{gi}:v]scale={W}:{H},fps={FPS},setsar=1[bg]"]
    else:
        g += ["[f2]nullsink", f"color=black:s={W}x{H}:r={FPS}[bg]"]
    base = "bg"
    if settings.get("ombre"):
        si = add_input("-loop", "1", "-i", _shadow(box, settings.get("arrondi", 40), os.path.join(work, "ombre.png")))
        g.append(f"[{base}][{si}:v]overlay=0:0:shortest=1[bgs]")
        base = "bgs"
    g.append(f"[{base}][fr]overlay={fx}:{fy}:shortest=1,format=yuv420p[pic]")
    cap_g, cur, sounds = R.filters(built, "pic", add_input, os.path.join(work, "sous_titres"), mask=mask_video)
    g += cap_g
    if signature and settings.get("identite"):
        name = signature.replace("\\", "").replace("'", "’").replace(":", "\\:").replace("%", "\\%")
        g.append(f"[{cur}]drawtext=fontfile='{_fp(os.path.abspath(FONT))}':text='{name}':fontsize=30:"
                 f"fontcolor=white@0.7:x={fx + fw}-tw-24:y={fy + fh}-th-22[sig]")
        cur = "sig"
    g.append(f"[1:a]loudnorm=I={SPEECH_LUFS}:TP=-1.5:LRA=11,aresample=48000[vo]")
    mix = ["[vo]"]
    if bed:
        bi = add_input("-i", bed)
        g.append(f"[{bi}:a]aresample=48000,atrim=0:{total:.3f}[mu]")
        mix.append("[mu]")
    for k, lab in enumerate(sounds):
        g.append(f"{lab}aresample=48000[sx{k}]")
        mix.append(f"[sx{k}]")
    g.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=first,volume=1.26,alimiter=limit=0.93[aout]"
             if len(mix) > 1 else "[vo]volume=1.26,alimiter=limit=0.93[aout]")
    tmp = out + ".part.mp4"
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(g), "-map", f"[{cur}]",
          "-map", "[aout]", "-t", f"{total:.3f}", "-r", str(FPS), *_venc(), "-c:a", "aac", "-b:a", "192k",
          "-movflags", "+faststart", tmp])
    os.replace(tmp, out)
    return out


# ---------------------------------------------------------------- music

def biggest_rise(song: str) -> float:
    """The second where the song gets much louder than the 4 s before it (its drop)."""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", song, "-ac", "1", "-ar", "8000", "-f", "f32le", "-"],
                         capture_output=True).stdout
    x = np.frombuffer(raw, np.float32)
    hop = 4000                                          # 0.5 s
    if len(x) < hop * 20:
        return 0.0
    env = np.array([np.sqrt(np.mean(x[i:i + hop] ** 2) + 1e-12) for i in range(0, len(x) - hop, hop)])
    db = 20 * np.log10(env + 1e-9)
    best, at = -1e9, 0.0
    for i in range(8, len(db) - 8):
        rise = db[i:i + 8].mean() - db[i - 8:i].mean()
        if rise > best:
            best, at = rise, i * 0.5
    return at


def song_bed(song: str, hit: float, total: float, out: str, gap: float, on_rise: bool = True) -> str:
    """A song under the speech, its biggest rise on `hit` (else from its start)."""
    from adaptation import musique
    if not on_rise:
        return musique.bed(song, out, total, gap=gap)
    start = biggest_rise(song) - hit
    pad = 0.0
    if start < 0:
        pad, start = -start, 0.0
    return musique.bed(song, out, total, start, pad, gap, lift_at=hit)


def thumbnail(video: str, at: float, out: str) -> Optional[str]:
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.0, at):.2f}", "-i", video, "-frames:v", "1",
                        "-q:v", "2", out])
    return out if r.returncode == 0 and os.path.exists(out) else None


def remove(path: Optional[str]):
    if path and os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)


def save_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
