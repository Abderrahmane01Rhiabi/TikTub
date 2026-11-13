"""
Montage pro — how « Idée d'abord » is edited (lab El Guerguerat, 2026-11-07).

An editor does not lay one picture under each sentence: he plays on the sense, the emotion and the
attention — the strongest image first, a cut every 1-3 seconds on the words, never twice the same
look in a row. So, after the storyboard (written in a narrative style of the channel) and the search:

  1. stock     the best checked videos (up to 8, their good moments only) are downloaded and cut into
               shots of ~2.6 s; each shot is described and scored ONCE by Gemini (what it shows, visual
               strength, relevance to the subject); off-subject shots are set aside by the code
               (oranges for a story about tomatoes) — the person reviews the stock before the edit
  2. voice     ElevenLabs (v4), the words' timings kept; a hook longer than 3.4 s is shortened once,
               with the facts checked again
  3. edit      Gemini as the editor: 2-3 cuts per sentence, each cut on the start of a word; the code
               checks it (set-aside shots out, never a shot twice, at least 1 s each)
  4. render    9:16, a slow push-in per shot, the sentence's banner on top (the « Actu » red band) and
               the captions word by word at ONE fixed place, the voice, a whoosh per sentence, the music
               low under it; the preview is the final quality

Kept in the video's recipe: the narrative style, the voice model, the caption place/size/font, the
banner's colour and place, the number of cuts per sentence — to learn later what the audience liked.
"""

import base64
import copy
import json
import os
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional, Tuple

from adaptation import checks, finder, graphiques, montage_doc, render, secours, sources, voices
from adaptation.langs import lang as lang_of

Report = Callable[[str, float], None]

W, H, FPS = 1080, 1920, 30
MAX_SOURCES = 8                 # videos downloaded for the stock (more sources = more variety)
MAX_SOURCES_ALL = 10            # up to this many when the director asked for more visuals (one source each)
ECO_PER_SENTENCE = 8            # « économique »: the shots the free model ranks best for each sentence are described,
ECO_PER_SOURCE = 3              # + each video's best (the Lions of a 4-name sentence), the rest never sent to Gemini
ECO_THINKING = 512              # « économique »: the AI editor's thinking cap (0.15 $ -> 0.02 $, lab 2026-11-12)
SPECIALIST = 2                  # a video showing 1-2 of the scenes was made for them: chosen before a « shows 5 » one
PAD = 3.0                       # seconds kept around each good moment of a long video
SHOT_S = 2.6                    # a long take is cut into pieces about this long
MAX_SHOTS_PER_SOURCE = 24
HOOK_MAX_S = 3.4                # the first sentence, measured on the real voice
MIN_CUT_S = 1.0
RAFALE_S = 0.5                  # a cut on a name of the director's list (one visual a club)
CAPTION_Y = H - 560             # the captions' one place (bottom of the line), never moving
BANNER_MARGIN = 250
MUSIC_GAIN = 0.12
# The sound effects (adaptation/sfx: Réglages → Bibliothèques → Effets sonores) on the story's real moments, as many as
# the narrative family wants (2026-11-08: one same whoosh on every sentence before, and over a whisper)
SONS_FAMILLE = {"actualite": {"max": 2, "types": {"whoosh", "pop"}},
                "explicatif": {"max": 4, "types": None},
                "humour": {"max": 4, "types": None},
                "hype": {"max": 5, "types": None},
                "motivation": {"max": 1, "types": {"whoosh"}},
                "satisfying": {"max": 1, "types": {"pop", "ding"}}}
REVELATION = {"mystere", "fait_surprenant", "vrai_faux", "chute", "revelation_lente", "mythe_realite"}
BURNT_TEXT = re.compile(r"texte|chiffre|sous-titre|titre|ecrit|écrit|filigrane|watermark", re.I)   # its own words, or a
# stock site's mark across the picture (« videoblocks », « Movie About You », 2026-11-12, the flamingos)   # a shot whose own words may say something else
DIGIT = re.compile(r"[0-9\u0660-\u0669]")

# The narrative styles: the app's one catalogue (adaptation/recits.py), each family's rules by style name
from adaptation import recits as _recits
RECITS = {f: {k: v[2] for k, v in x["styles"].items()} for f, x in _recits.FAMILLES.items()}

DESCRIBE = """Tu es monteur video. Voici {n} images, une par plan de rushs (dans l'ordre, ids : {ids}).
Sujet du Short a monter : {sujet}
Pour CHAQUE image, en JSON :
- "desc" : ce qu'on voit, precis, en francais (1 phrase) ;
- "montre" : 3 a 6 mots-cles de ce qu'on voit (objets, lieux, gens, action) ;
- "force" : 1-10, la force visuelle pour un Short (10 = arrete le scroll : grand, net, en mouvement, humain ou
  spectaculaire ; 2 = plan vide, flou, statique, presentateur face camera) ;
- "pertinence" : 0-10, a quel point l'image sert CE sujet (0 = hors sujet, ex. des oranges pour un sujet sur les tomates) ;
- "probleme" : null ou ce qui gene (texte incruste, logo, micro de journaliste, flou, ecran partage, filigrane) ;
- "ia" : true si l'image semble GENEREE PAR IA en se faisant passer pour une vraie prise de vue (chantier, foule,
  ouvriers ou paysage trop parfaits, lisses, details incoherents : mains, visages, textes illisibles, machines
  impossibles) ; false pour une vraie video, et false aussi pour un rendu 3D, une maquette ou une simulation
  d'architecte qui se montre comme tel (le rendu officiel d'un stade n'est pas une image IA) ;
- "x" : ou est le sujet horizontalement (0 gauche - 1 droite), pour recadrer en vertical.
JSON uniquement : {{"plans": [{{"id": "", "desc": "", "montre": [""], "force": 5, "pertinence": 5, "probleme": null, "ia": false, "x": 0.5}}]}}"""

EDIT = """Tu es un monteur PRO de YouTube Shorts. Voici la voix off, phrase par phrase, avec ses mots numerotes et leur
instant (secondes) :
{phrases}

Voici les RUSHS disponibles (id | source « son titre » | duree | force visuelle 1-10 | colle aux phrases | ce qu'on voit |
probleme) :
{plans}
« colle aux phrases » = les phrases dont ce plan fait passer l'IDEE (mesure de l'image contre l'idee de chaque phrase,
la plus haute d'abord ; « - » = aucune).
{realisation}
Monte la video comme un pro (le sens + l'emotion + l'attention), pas du mot a mot :
- 2 ou 3 COUPES par phrase : chaque plan reste 1,2 a 3 secondes a l'ecran. Une coupe tombe sur le DEBUT d'un mot
  (de preference le mot important : un nom, un chiffre, un verbe fort) -> donne l'indice du mot ou le plan commence.
  Une phrase a plusieurs temps du REALISATEUR : autant de coupes que de visuels (4 au plus), chacune sur son mot.
  La 1re coupe d'une phrase commence au mot 0.
- La TOUTE PREMIERE image = la plus forte qui colle au sujet, pour arreter le scroll.
- Pour chaque phrase, prends d'abord des plans dont « colle aux phrases » cite CETTE phrase.
- L'image ne contredit JAMAIS la phrase ; elle montre l'idee ou l'emotion quand le mot a mot est impossible.
- Au plus 2 plans d'une meme source dans toute la video.
- VARIETE : jamais le meme plan deux fois ; deux plans qui se suivent ne se ressemblent pas (alterne large / serre,
  change de lieu ou d'angle) ; evite deux plans de suite de la meme source quand une autre colle aussi.
- Evite les plans a probleme sauf s'il n'y a pas mieux ; un plan avec du TEXTE ou des chiffres incrustes jamais sur
  une phrase qui dit un chiffre, une date ou un montant (il dirait autre chose que la voix).
JSON uniquement : {{"montage": [{{"phrase": 1, "coupes": [{{"plan": "id", "mot": 0}}]}}]}}"""

HOOK_PROMPT = """Raccourcis l'accroche d'un YouTube Short ({langue}) : elle dure {duree:.1f} s a l'oral, il faut 3 s au plus
(environ {mots} mots). Elle doit NOMMER le sujet et donner envie de rester.
Accroche actuelle : {texte}
Phrase suivante (ne pas la repeter) : {suivante}
FAITS (les seuls utilisables, aucun autre fait, chiffre ou nom) : {faits}
Regles de langue : {regles}
JSON uniquement : {{"texte": "la nouvelle accroche"}}"""

FACTS_PROMPT = """Faits verifies :
{faits}
Phrase a controler : {texte}
Cette phrase affirme-t-elle un fait, un chiffre, une cause ou un nom qui n'est PAS dans les faits verifies ?
JSON uniquement : {{"ok": true/false, "hors_faits": "ce qui n'est pas dans les faits, sinon vide"}}"""


class MontageProError(RuntimeError):
    pass


def _gemini():
    from adaptation.script import _gemini as g
    return g()


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise MontageProError((r.stderr or "")[-800:] or f"ffmpeg s'est arrêté ({r.returncode})")
    return r


def _probe(path: str) -> Tuple[float, int, int]:
    d = json.loads(_run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height",
                         "-of", "json", path]).stdout)
    st = next(s for s in d["streams"] if s.get("width"))
    return float(d["format"]["duration"]), int(st["width"]), int(st["height"])


def _jpg(path: str) -> Dict:
    with open(path, "rb") as f:
        return {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(f.read()).decode()}}


def pro_dir(pid: str) -> str:
    from adaptation.pipeline import project_dir
    return os.path.join(project_dir(pid), "pro")


# ---------------------------------------------------------------- narrative style

def family(style: Optional[str]) -> str:
    return _recits.default_family(style)


def recent_recits(channel: str, n: int = 3) -> List[str]:
    return _recits.recent(channel, n)


def choose_recit(reference: Dict, style: Optional[str], recents: List[str], gemini=None,
                 famille: Optional[str] = None, exclus: Optional[List[str]] = None) -> str:
    """The style of the channel's family (else the one its look says) that tells this subject best."""
    return _recits.choose(reference, famille or family(style), exclus, recents, gemini=gemini)


DIALECT_PART = {"darija": """LANGUE DE LA VOIX (arabe, cette regle REMPLACE la regle "arabe standard" donnee plus
haut pour les textes dits) : DARIJA MAROCAINE naturelle, comme un presentateur marocain sur YouTube
(pas l'arabe standard), en lettres arabes, sans voyelles courtes, les NOMBRES EN CHIFFRES ("22", "115000", "5 مليار",
"2026" ; jamais "جوج وعشرين" : choix de l'utilisateur, la voix les lit bien) : c'est vrai pour
"texte", "bandeau" et "mots_cles". MAIS "titre", "description" et "tags" restent en ARABE STANDARD MODERNE (ce que les
gens tapent dans la recherche).

"""}


def dialect(t: Dict) -> Optional[str]:
    return t.get("dialecte") if t.get("language") == "ar" else None


def dialect_part(targets: List[Dict]) -> str:
    """The spoken dialect's rule for the storyboard (one Arabic target in a dialect), else nothing."""
    return next((DIALECT_PART[d] for d in (dialect(t) for t in targets) if d in DIALECT_PART), "")


def recit_part(name: str, style: Optional[str] = None) -> str:
    return _recits.part(name)


# ---------------------------------------------------------------- 1. the stock

def choose_sources(p: Dict, n: Optional[int] = None) -> List[Dict]:
    """The checked videos with good moments: first, one by one, the video that brings the most to the scenes still
    without any (each of the director's visuals gets its source: the Wydad's after the Raja's), the videos made for
    one or two scenes before the ones said to show many (2026-11-11: an explainer said to show « exactly » 5 scenes,
    the moussem tent and the national team among them, took their place from « The Moussem of Tan-Tan » and the
    Lions' celebrations), then the best left: [{url, titre, duree, moments, score}]. As many as the director's
    visuals, between MAX_SOURCES and MAX_SOURCES_ALL."""
    sug = p.get("suggestions") or {}
    if n is None:
        n = min(MAX_SOURCES_ALL, max(MAX_SOURCES, len(sug.get("scenes") or [])))
    cands = {c["url"]: c for c in finder.all_candidates(sug)}
    chosen = {x["url"] for x in p.get("picks") or [] if x and x.get("url")}
    rows = []
    for url, v in (sug.get("verifs") or {}).items():
        if not isinstance(v, dict) or v.get("copie"):
            continue
        good = [e for e in (v.get("par_scene") or {}).values() if isinstance(e, dict) and e.get("niveau") in finder.RANK]
        if not good:
            continue
        c = cands.get(url) or {}
        rows.append({"url": url, "titre": c.get("title") or v.get("title") or url,
                     "duree": c.get("duration") or v.get("duration"),
                     "moments": [m for e in good for m in e.get("moments") or []],
                     "score": sum(3 - finder.RANK[e["niveau"]] for e in good) + (2 if url in chosen else 0),
                     "scenes": {k: 3 - finder.RANK[e["niveau"]] for k, e in (v.get("par_scene") or {}).items()
                                if isinstance(e, dict) and e.get("niveau") in finder.RANK}})
    rows.sort(key=lambda r: -r["score"])
    out, covered = [], {}               # {scene: the best level a chosen video brings it}
    gain = lambda r: sum(max(0, w - covered.get(k, 0)) for k, w in r["scenes"].items())
    for special in (True, False):
        while len(out) < n:
            top = max((r for r in rows if r not in out and gain(r) > 0
                       and (not special or len(r["scenes"]) <= SPECIALIST)), key=gain, default=None)
            if not top:
                break
            out.append(top)
            for k, w in top["scenes"].items():
                covered[k] = max(w, covered.get(k, 0))
    out += [r for r in rows if r not in out][:n - len(out)]
    for r in out:
        r.pop("scenes")
    return out


def spans_of(row: Dict) -> Optional[List[List[float]]]:
    """A long video: only its good moments (padded, merged); a short one (2 min or less): whole."""
    dur = row.get("duree")
    if dur and float(dur) <= 120:
        return None
    spans = []
    for m in row.get("moments") or []:
        try:
            a = float(m.get("debut") or 0)
            b = float(m.get("fin") if m.get("fin") is not None else a + 4)
        except (TypeError, ValueError):
            continue
        a, b = max(0.0, min(a, b) - PAD), max(a, b) + PAD
        if dur:
            b = min(b, float(dur))
        if b - a < 1.0:             # a moment past the video's end (700 s in a 482 s video) made ffmpeg refuse the
            continue                # whole download — and its real good moments were lost with it
        spans.append([a, b])
    spans.sort()
    merged: List[List[float]] = []
    for a, b in spans:
        if merged and a <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return merged or None


def _cuts(path: str, dur: float) -> List[float]:
    """Where the picture changes (ffmpeg scene score > 0.3), with the ends."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-vf", "select='gt(scene,0.3)',showinfo", "-an",
                        "-f", "null", "-"], capture_output=True, text=True)
    ts = sorted(float(m) for m in re.findall(r"pts_time:([\d.]+)", r.stderr or ""))
    return [0.0] + [t for t in ts if 0.4 < t < dur - 0.4] + [dur]


def shots_of(path: str, k: int, thumbs: str) -> List[Dict]:
    """The shots of one downloaded source: each change of picture, long takes cut in ~SHOT_S pieces."""
    dur, w, h = _probe(path)
    out = []
    bounds = _cuts(path, dur)
    for a, b in zip(bounds, bounds[1:]):
        n = max(1, round((b - a) / SHOT_S))
        for j in range(n):
            s, e = a + (b - a) * j / n, a + (b - a) * (j + 1) / n
            if e - s >= 0.8:
                out.append((s, e))
    if len(out) > MAX_SHOTS_PER_SOURCE:                 # a long live: an even sample
        step = len(out) / MAX_SHOTS_PER_SOURCE
        out = [out[int(i * step)] for i in range(MAX_SHOTS_PER_SOURCE)]
    os.makedirs(thumbs, exist_ok=True)
    shots = []
    for j, (s, e) in enumerate(out):
        sid = f"S{k}_{j:02d}"
        thumb = os.path.join(thumbs, f"{sid}.jpg")
        _run(["ffmpeg", "-v", "error", "-y", "-ss", f"{(s + e) / 2:.2f}", "-i", path, "-frames:v", "1",
              "-vf", "scale=480:-2", thumb])
        shots.append({"id": sid, "source": k, "file": path, "start": round(s, 2), "end": round(e, 2),
                      "w": w, "h": h, "thumb": thumb})
    return shots


def describe(shots: List[Dict], sujet: str, gemini=None) -> None:
    """Each shot described and scored once (16 pictures a call)."""
    g = gemini or _gemini()
    for i in range(0, len(shots), 16):
        batch = shots[i:i + 16]
        try:
            r = g._generate_content([{"text": DESCRIBE.format(n=len(batch), ids=", ".join(s["id"] for s in batch),
                                                              sujet=sujet)}] + [_jpg(s["thumb"]) for s in batch],
                                    max_tokens=8000, timeout=180, temperature=0.2)
        except Exception:
            r = {}
        got = {str(d.get("id")): d for d in (r or {}).get("plans") or [] if isinstance(d, dict)}
        for s in batch:
            d = got.get(s["id"]) or {}
            s.update(desc=str(d.get("desc") or ""), montre=[str(x) for x in d.get("montre") or []][:6],
                     force=_num(d.get("force"), 5), pertinence=_num(d.get("pertinence"), 5),
                     probleme=d.get("probleme") or None, ia=d.get("ia") is True,
                     x=min(1.0, max(0.0, _num(d.get("x"), 0.5, float))))


def _num(x, default, kind=int):
    try:
        return kind(x)
    except (TypeError, ValueError):
        return default


def reserved(p: Dict) -> Dict[str, int]:
    """{url: sentence} — a video found in a club's (a company's…) official channel for one sentence of the director
    is kept for that sentence: the editor put the Camp Nou and the Wydad in the sentence before (2026-11-10)."""
    out: Dict[str, set] = {}
    for s in (p.get("suggestions") or {}).get("scenes") or []:
        for c in s.get("candidats") or []:
            if "chaine" in (c.get("origines") or []) and s.get("phrase_n"):
                out.setdefault(c["url"], set()).add(s["phrase_n"])
    return {u: next(iter(ks)) for u, ks in out.items() if len(ks) == 1}


def economique(p: Dict) -> bool:
    """The project's cost mode (adaptation/settings.COUTS); projects made before it: every shot described."""
    return p.get("cout") == "economique"


def presort(shots: List[Dict], n: int) -> set:
    """« économique »: the ids of the shots worth describing, by the free local model's score (shot["colle"],
    adaptation/vision) — each sentence's ECO_PER_SENTENCE best and each video's ECO_PER_SOURCE best (lab
    2026-11-12: 8 a sentence alone lost the Raja and the Lions of « le Raja, le Wydad et l'équipe nationale »)."""
    sc = lambda s, k: (s.get("colle") or [])[k] if k < len(s.get("colle") or []) else 0.0
    keep = set()
    for k in range(n):
        keep |= {s["id"] for s in sorted(shots, key=lambda s: -sc(s, k))[:ECO_PER_SENTENCE]}
    for src in {s["source"] for s in shots}:
        mine = [s for s in shots if s["source"] == src]
        keep |= {s["id"] for s in sorted(mine, key=lambda s: -max(s.get("colle") or [0.0]))[:ECO_PER_SOURCE]}
    return keep


def set_aside(shot: Dict) -> Optional[str]:
    """Why the code keeps a shot out of the edit by itself (the person can bring it back), or None."""
    if shot.get("ia"):                  # 2026-11-13: AI-made « works » shown as the real site
        return "image IA"
    if shot.get("pertinence", 5) <= 3:
        return "hors sujet"
    if not shot.get("desc"):
        return "non décrit"
    return None


def run_stock(pid: str, report: Optional[Report] = None) -> None:
    """Downloads the best checked videos (their good moments), cuts and describes the shots -> stock_review."""
    from adaptation import pipeline as ap
    report = report or (lambda phase, f: None)
    p = ap.load(pid)
    try:
        rows = choose_sources(p)
        if not rows:
            raise MontageProError("Aucune vidéo vérifiée utilisable : cherche d'autres images.")
        base = pro_dir(pid)
        metas: List[Optional[Dict]] = [None] * len(rows)
        lock = threading.Lock()
        done = {"n": 0}
        made = {}                           # the animated graphics (adaptation/graphiques), made beside the downloads
        drawing = threading.Thread(target=lambda: made.update(graphiques.make_all(p, os.path.join(base, "graphiques"))),
                                   daemon=True)
        drawing.start()

        def one(k: int, row: Dict) -> None:
            try:
                path = sources.download(row["url"], os.path.join(base, "src"), f"pro{k}", spans_of(row))
                metas[k] = {**sources.source_meta(path), "path": path, "url": row["url"], "titre": row["titre"]}
            except Exception as e:                  # one dead link must not stop the others
                metas[k] = {"url": row["url"], "failed": str(e)[:200]}
            with lock:
                done["n"] += 1
                report(f"téléchargement des sources ({done['n']}/{len(rows)})", 0.05 + 0.45 * done["n"] / len(rows))
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda kr: one(*kr), enumerate(rows)))
        shots = []
        for k, m in enumerate(metas):
            if m and m.get("path"):
                report(f"découpage en plans ({k + 1}/{len(metas)})", 0.5 + 0.15 * k / len(metas))
                official = reserved(p)
                for s in shots_of(m["path"], k, os.path.join(base, "thumbs")):
                    s.update(credit=m.get("handle") or m.get("uploader") or "", url=m["url"], titre_source=m["titre"])
                    if official.get(m["url"]):
                        s["reserve"] = official[m["url"]]
                    shots.append(s)
        if not shots:
            raise MontageProError("Aucune source n'a pu être téléchargée : " +
                                  " ; ".join(m.get("failed", "") for m in metas if m)[:300])
        pretri, matched = None, False
        if economique(p) and _vision_ok():
            report("tri gratuit des plans", 0.66)
            try:
                from adaptation import vision
                n = len(((p.get("storyboard") or {}).get("plans")) or [])
                vision.match(shots, vision.ideas_of(p), os.path.join(base, "vision"))
                matched = any(s.get("colle") for s in shots)
            except Exception:           # the model would not run: every shot described, as in « qualité »
                matched = False
            if matched:
                keep = presort(shots, n)
                pretri = {"decrits": len(keep), "total": len(shots)}
        todo = [s for s in shots if pretri is None or s["id"] in keep]
        report(f"description des {len(todo)} plans" + (f" sur {len(shots)}" if len(todo) < len(shots) else ""), 0.68)
        describe(todo, (p.get("reference") or {}).get("sujet") or p.get("idee") or "")
        for s in shots:
            why = "pré-tri" if pretri is not None and s["id"] not in keep else set_aside(s)
            s.update(garde=why is None, ecarte=why)
        v2 = images_v2(p, shots, metas, base, report, matched)
        if drawing.is_alive():
            report("graphiques animés", 0.95)
        drawing.join()
        n_sentences = len(((p.get("storyboard") or {}).get("plans")) or [])
        for s in made.get("shots") or []:   # kept for their sentence: seen and removed like any shot
            s["colle"] = (s.get("colle") or [])[:n_sentences] + [0.0] * max(0, n_sentences - len(s.get("colle") or []))
            shots.append(s)
        p = ap.load(pid)
        if v2.get("idees"):                         # kept on the storyboard: the edit and the review use them
            for pl, idea in zip((p.get("storyboard") or {}).get("plans") or [], v2["idees"]):
                pl["idee"] = idea
        secours.mark(p, "images", v2.get("secours"))
        secours.mark(p, "graphiques", made.get("secours"))
        p.update(stock=shots, stock_sources=metas, images_v2=v2.get("bilan"), graphiques=made.get("liste") or [], pretri=pretri,
                 incrustation=made.get("incrustation"), status="stock_review", error=None, failed_step=None)
        ap.save(p)
    except Exception as e:
        ap.fail(pid, "fetching", e)
    report("terminé", 1.0)


def _vision_ok() -> bool:
    from adaptation import vision
    return vision.available()


def images_v2(p: Dict, shots: List[Dict], metas: List[Optional[Dict]], base: str, report: Report,
              matched: bool = False) -> Dict:
    """Images v2 (adaptation/vision): the shots judged against each sentence's idea — the off-topic ones that fit a
    sentence brought back, in the news the videos about another place set aside, a general Pixabay search for the
    sentences nothing fits. -> {idees, bilan, secours (a message when it could not run)}."""
    from adaptation import vision
    if not vision.available():
        return {"secours": "recherche par le sens non installée : les plans sont choisis comme avant."}
    sujet = (p.get("reference") or {}).get("sujet") or p.get("idee") or ""
    family = p.get("famille_recit") or _recits.find(p.get("recit"))
    try:
        if family == "actualite":
            report("contrôle des lieux", 0.8)
            off = vision.other_places(sujet, metas)
            for s in shots:                 # an official channel's video was asked by the director (the Camp Nou)
                if s["source"] in off and s.get("garde") and not s.get("reserve"):
                    s.update(garde=False, ecarte="autre lieu", ailleurs=off[s["source"]])
        report("recherche par le sens", 0.84)
        ideas = vision.ideas_of(p)
        folder = os.path.join(base, "vision")
        if not matched:                 # « économique » scored them already, before the description
            vision.match(shots, ideas, folder)
        vision.rescue([s for s in shots if s.get("ecarte") != "autre lieu"], len(ideas))
        added, used = [], set()
        miss = vision.missing(shots, len(ideas))
        words = vision.searches([ideas[k] for k in miss]) if miss else []
        for n, k in enumerate(miss):
            report(f"recherche de secours (phrase {k + 1})", 0.9)
            try:
                shot = vision.pixabay(ideas[k], os.path.join(base, "pixabay"), n, family == "actualite", used, words[n])
            except Exception:
                shot = None
            if shot:
                shot["secours_pour"] = k + 1
                used.add(shot["pixabay_id"])
                added.append(shot)
        if added:
            describe(added, sujet)
            vision.match(added, ideas, folder)
            shots.extend(added)
        vision.save_scores(folder, shots)
        return {"idees": ideas, "bilan": vision.report_line(shots)}
    except Exception as e:                          # never a stock lost for it: the shots as before
        return {"secours": f"recherche par le sens interrompue ({str(e)[:80]}) : les plans sont choisis comme avant."}


def set_shot(pid: str, sid: str, keep: bool) -> Dict:
    from adaptation import pipeline as ap
    p = ap.load(pid)
    ap._expect(p, "stock_review")
    shot = next((s for s in p.get("stock") or [] if s["id"] == sid), None)
    if not shot:
        raise ap.PipelineError("Plan inconnu.")
    shot["garde"] = bool(keep)
    return ap.save(p)


def approve_stock(pid: str) -> Dict:
    from adaptation import pipeline as ap
    p = ap.load(pid)
    ap._expect(p, "stock_review")
    if sum(1 for s in p.get("stock") or [] if s.get("garde")) < 6:
        raise ap.PipelineError("Garde au moins 6 plans pour monter la vidéo.")
    p["status"] = "voicing"
    return ap.save(p)


# ---------------------------------------------------------------- 2. voice (and the hook)

def _voice(p: Dict, t: Dict, mp3: str, report: Report, at: float) -> Dict:
    from adaptation import voix_casting
    model = t.get("voice_model") or voices.MODEL
    clean = [x["texte"] for x in t["script"]["passages"]]
    manieres = (t.get("manieres") or []) + [""] * len(clean)
    texts = [voix_casting.tagged(x, m) for x, m in zip(clean, manieres)]   # each sentence's manner, as a v4 tag
    v = t.get("voice") or {}
    from adaptation import prononciation
    if v and v.get("voice_id") == t["voice_id"] and v.get("texts") == texts and v.get("model") == model \
            and v.get("prononciation", "[]") == prononciation.signature(t["language"]) \
            and os.path.exists(mp3):
        return v                                    # never pay twice for the same narration
    report(f"voix {t['channel']}", at)
    v = voices.synthesize([{"texte": x} for x in texts], t["voice_id"], t["language"], mp3, model=model,
                          dialect=dialect(t))
    v = voix_casting.strip_tags(v, clean)           # the tags are said to ElevenLabs, never shown in the captions
    v.update(voice_id=t["voice_id"], texts=texts, model=model)
    return v


def check_facts(text: str, facts: List[str], gemini=None) -> Optional[str]:
    """What a sentence says beyond the verified facts, or None when it stays within them."""
    if not facts:
        return None
    try:
        r = (gemini or _gemini())._generate_content([{"text": FACTS_PROMPT.format(
            faits="\n".join(f"- {f}" for f in facts), texte=text)}], max_tokens=1500, timeout=60, temperature=0.0)
    except Exception:
        return None
    if isinstance(r, dict) and r.get("ok") is False:
        return str(r.get("hors_faits") or "un fait non vérifié")
    return None


def shorter_hook(p: Dict, t: Dict, seconds: float, gemini=None) -> Optional[str]:
    """The hook rewritten to 3 s, only if it names the subject and adds no fact; else None."""
    from adaptation.script import LANG_RULES
    ps = t["script"]["passages"]
    lang = lang_of(t["language"])
    facts = (p.get("reference") or {}).get("faits") or []
    words = max(4, int(len(ps[0]["texte"].split()) * 3.0 / max(seconds, 0.1)))
    secours.mark(t, "accroche")
    new = ""
    try:
        r = (gemini or _gemini())._generate_content([{"text": HOOK_PROMPT.format(
            langue=lang["label"], duree=seconds, mots=words, texte=ps[0]["texte"],
            suivante=ps[1]["texte"] if len(ps) > 1 else "", faits="; ".join(facts),
            regles=DIALECT_PART.get(dialect(t)) or LANG_RULES.get(t["language"], LANG_RULES["fr"]))}],
            max_tokens=1500, timeout=60, temperature=0.4)
        new = " ".join(str((r or {}).get("texte") or "").split())
    except Exception as e:
        r = {"error": str(e)}
    if secours.failed(r):
        secours.mark(t, "accroche", f"trop longue ({seconds:.1f} s), pas raccourcie ({secours.why(r)}).")
        return None
    if not new or len(new.split()) >= len(ps[0]["texte"].split()) or check_facts(new, facts, gemini):
        return None
    return new


# ---------------------------------------------------------------- 3. the edit

def _edit_prompt(v: Dict, shots: List[Dict], realisation: Optional[List[Dict]] = None) -> str:
    words = v["words"]
    lines = []
    for i, ps in enumerate(v["passages"], 1):
        ws = " ".join(f"{k}:{words[w]['w']}@{words[w]['start']:.2f}" for k, w in enumerate(ps["words"]))
        lines.append(f"Phrase {i} ({ps['start']:.2f}-{ps['end']:.2f} s) : {ws}")
    rushes = "\n".join(f"{s['id']} | {s.get('source')} « {str(s.get('titre_source') or '')[:50]} »"
                       + (f" (RESERVE a la phrase {s['reserve']})" if s.get("reserve") else "") + " | "
                       f"{s['end'] - s['start']:.1f}s | {s.get('force')} | {_fits(s)} | "
                       f"{s.get('desc')} | {s.get('probleme') or '-'}" for s in shots)
    return EDIT.format(phrases="\n".join(lines), plans=rushes, realisation=_directed(realisation, len(v["passages"])))


def _directed(realisation: Optional[List[Dict]], n: int) -> str:
    """The director's plan for the editor (adaptation/realisateur): each sentence's visuals in the voice's order, from
    their word — measured on 2026-11-10, without it the Camp Nou of « dépassera le Camp Nou et accueillera le Raja, le
    Wydad et l'équipe nationale » went to the sentence before, and that sentence opened on foundations. Every
    sentence, one visual too (2026-11-11: the hanging gardens went to the budget sentence, the stairs and gardens one
    got foundations and a train station)."""
    rows = []
    for e in realisation or []:
        vis = [v for v in e.get("visuels") or [] if v.get("image")]
        if 1 <= e.get("phrase", 0) <= n and vis:
            rows.append(f"Phrase {e['phrase']} : " + " -> ".join(
                (f"« {v['mot']} » " if v.get("mot") and len(vis) > 1 else "") + v["image"] for v in vis))
    if not rows:
        return ""
    return ("\nLe REALISATEUR a decide ce qu'on voit sur chaque phrase ; prends pour chaque visuel le rush qui le montre "
            "(la source le dit souvent : le nom du club, du lieu). Une phrase a plusieurs temps : une coupe PAR visuel, "
            "DANS CET ORDRE, chacune sur son mot (« mot »). Un rush qui montre une AUTRE sorte de chose que le visuel "
            "ne le montre pas (une tente nomade du desert n'est pas une tente de moussem marocaine, un autre stade "
            "n'est pas ce stade) : prends-en un autre ; pour une comparaison sans le bon rush, montre le sujet "
            "lui-meme :\n" + "\n".join(rows) + "\n")


EDIT_MAX = 60               # shots shown to the editor (109 made its answer too long: cut, the montage fell back)


def editable(shots: List[Dict], n_sentences: int) -> List[Dict]:
    """The shots the editor is shown: each sentence's best ones (adaptation/vision) and the strongest, EDIT_MAX at most
    — the code still chooses among all of them when it must replace one (build_edit)."""
    if len(shots) <= EDIT_MAX:
        return shots
    keep = {}
    for src in {s["source"] for s in shots if s.get("reserve")}:     # each official channel's video: its 3 strongest
        for s in sorted((s for s in shots if s["source"] == src), key=lambda s: -(s.get("force") or 0))[:3]:
            keep[s["id"]] = s
    per = max(4, EDIT_MAX // max(1, n_sentences) - 2)
    for k in range(n_sentences):
        for s in sorted(shots, key=lambda s: -((s.get("colle") or [0.0] * n_sentences)[k] if k < len(s.get("colle") or []) else 0.0))[:per]:
            keep[s["id"]] = s
    for s in sorted(shots, key=lambda s: -(s.get("force") or 0)):
        if len(keep) >= EDIT_MAX:
            break
        keep.setdefault(s["id"], s)
    return [s for s in shots if s["id"] in keep]


def _fits(shot: Dict) -> str:
    """« 3:0.35 5:0.29 »: the sentences whose idea this shot conveys (adaptation/vision), the best first."""
    from adaptation.vision import FITS
    sc = shot.get("colle") or []
    best = sorted(((v, k + 1) for k, v in enumerate(sc) if v >= FITS), reverse=True)[:3]
    return " ".join(f"{k}:{v:.2f}" for v, k in best) or "-"


def quick_words(realisation: Optional[List[Dict]], v: Dict) -> Dict[int, set]:
    """{sentence: its words where the director starts a visual} — there a cut may last RAFALE_S only (« الرجاء
    والوداد والمنتخب » : 0.6 s between two clubs, the Wydad was dropped by the 1 s rule)."""
    plain = lambda w: re.sub(r"[^\w]", "", str(w or "")).lower()
    out = {}
    for e in realisation or []:
        i = e.get("phrase", 0)
        if not 1 <= i <= len(v["passages"]) or len(e.get("visuels") or []) < 2:
            continue
        said = [plain(v["words"][w]["w"]) for w in v["passages"][i - 1]["words"]]
        for vis in e["visuels"]:
            m = plain(vis.get("mot"))
            k = next((k for k, w in enumerate(said) if m and w == m), None)
            if k:
                out.setdefault(i, set()).add(k)
    return out


def build_edit(raw: Dict, v: Dict, shots: List[Dict], quick: Optional[Dict[int, set]] = None) -> List[Dict]:
    """Gemini's edit made safe: only kept shots, never one twice, cuts on the words' starts, at least
    MIN_CUT_S each (RAFALE_S on a word where the director starts a visual: quick), the whole voice covered (each
    sentence until the next one starts, the last + 0.6 s). [{phrase, plan, debut, fin}] in video time."""
    from adaptation.vision import FITS, MAX_PER_SOURCE
    by_id = {s["id"]: s for s in shots}
    used, edl = set(), []
    per_source: Dict = {}
    words, ps_all = v["words"], v["passages"]
    asked = {int(m.get("phrase") or 0): m.get("coupes") or [] for m in (raw or {}).get("montage") or [] if isinstance(m, dict)}
    ends = [ps["start"] for ps in ps_all[1:]] + [v["duration"] + 0.6]

    def fit(s: Dict, i: int) -> float:              # how well a shot conveys sentence i (adaptation/vision)
        sc = s.get("colle") or []
        return sc[i - 1] if i - 1 < len(sc) else 0.0

    def free(prefer: Optional[str] = None, i: int = 1) -> Optional[str]:
        mine = lambda s: s.get("reserve") in (None, i)              # an official channel's video: its sentence only
        roomy = lambda s: per_source.get(s["source"], 0) < MAX_PER_SOURCE      # variety: 2 shots a video at most
        if prefer in by_id and prefer not in used and roomy(by_id[prefer]) and mine(by_id[prefer]):
            if not BURNT_TEXT.search(by_id[prefer].get("probleme") or ""):
                return prefer
            clean = next((s["id"] for s in sorted(shots, key=lambda s: -fit(s, i)) if s["id"] not in used
                          and fit(s, i) >= FITS and mine(s) and roomy(s)
                          and not BURNT_TEXT.search(s.get("probleme") or "")), None)
            return clean or prefer      # burnt-in text (« 5,000 2028 » on « 5 billion »): another shot of this sentence
        last = by_id.get(edl[-1]["plan"]) if edl else None
        spare = sorted((s for s in shots if mine(s)), key=lambda s: (-fit(s, i), -(s.get("pertinence") or 0), -(s.get("force") or 0)))
        for ok in (lambda s: roomy(s) and (not last or s["source"] != last["source"]), roomy, lambda s: True):
            sid = next((s["id"] for s in spare if s["id"] not in used and ok(s)), None)
            if sid:                                 # the best unused one for this sentence, another video if possible
                return sid
        return next((s["id"] for s in shots if s["id"] not in used), None)     # only reserved ones left
    for i, (ps, end) in enumerate(zip(ps_all, ends), 1):
        start = 0.0 if i == 1 else ps["start"]
        cuts = sorted((c for c in asked.get(i, []) if isinstance(c, dict)), key=lambda c: _num(c.get("mot"), 0))
        times, plans = [], []
        for c in cuts or [{"mot": 0}]:
            k = min(max(0, _num(c.get("mot"), 0)), len(ps["words"]) - 1) if ps["words"] else 0
            at = start if not times else words[ps["words"][k]]["start"]
            shortest = RAFALE_S if k in (quick or {}).get(i, ()) else MIN_CUT_S
            if times and at - times[-1] < shortest:             # too short: this cut is dropped
                continue
            sid = free(str(c.get("plan") or ""), i)
            if sid is None:
                break
            used.add(sid)
            per_source[by_id[sid]["source"]] = per_source.get(by_id[sid]["source"], 0) + 1
            times.append(at)
            plans.append(sid)
        if not plans:
            sid = free(None, i)
            if sid is None:
                raise MontageProError("Plus assez de plans dans le stock pour monter la vidéo.")
            used.add(sid)
            per_source[by_id[sid]["source"]] = per_source.get(by_id[sid]["source"], 0) + 1
            times, plans = [start], [sid]
        if end - times[-1] < MIN_CUT_S and len(plans) > 1:     # the last piece too short: merged into the one before
            gone = plans.pop()
            used.discard(gone)
            per_source[by_id[gone]["source"]] -= 1
            times.pop()
        if edl:
            times[0] = edl[-1]["fin"]
        for k, sid in enumerate(plans):
            edl.append({"phrase": i, "plan": sid, "debut": round(times[k], 2),
                        "fin": round(times[k + 1] if k + 1 < len(plans) else end, 2)})
    return edl


# ---------------------------------------------------------------- 4. render

def _ass_time(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def _ass_colour(rgb) -> str:
    """'#RRGGBB' or (r, g, b[, a]) -> ASS &H00BBGGRR."""
    if isinstance(rgb, str):
        rgb = tuple(int(rgb.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    r, g, b = rgb[:3]
    return f"&H00{b:02X}{g:02X}{r:02X}"


def banner_text(bandeau: str) -> str:
    """The banner without emoji (libass draws no colour emoji)."""
    return " ".join(w for w in (bandeau or "").split()
                    if any(c.isalnum() or "؀" <= c <= "ۿ" for c in w))


CAPTION_PLACES = {"bas": CAPTION_Y, "milieu": H // 2 + 160, "haut": BANNER_MARGIN + 330}


def doc_words(v: Dict, doc: Optional[Dict]) -> List[Dict]:
    """The voice's words with the person's fixes (the times stay the voice's)."""
    fixes = ((doc or {}).get("sous_titres") or {}).get("mots") or {}
    return [{**w, "w": fixes.get(str(k), w["w"])} for k, w in enumerate(v["words"])]


def caption_groups(v: Dict, doc: Optional[Dict]) -> List[Dict]:
    """The captions' groups of 3 words, sentence by sentence, each with the look it has: the video's (style,
    position, taille) unless the person set this group apart (sous_titres.groupes, keyed by its first word)."""
    st = (doc or {}).get("sous_titres") or {}
    own = st.get("groupes") or {}
    out = []
    for k, vp in enumerate(v["passages"]):
        idx = vp["words"]
        for i in range(0, len(idx), 3):
            g = idx[i:i + 3]
            x = own.get(str(g[0]), {})
            out.append({"mots": g, "phrase": k, "style": x["style"] if "style" in x else st.get("style"),
                        "position": x.get("position") or st.get("position") or "bas",
                        "taille": x.get("taille") or st.get("taille") or 100})
    return out


def captions_ass(v: Dict, passages: List[Dict], path: str, code: str, style: Dict, doc: Optional[Dict] = None) -> Dict:
    """Banner (top, one per sentence) + captions 3 words at a time, the spoken word in the key colour, at ONE
    fixed place (\\pos: libass would push a line up when it overlaps the previous one). Arabic: every word its
    own colour run and the styles right-to-left (render.captions_ass's recipe), else the words come out of order.
    doc (montage_doc): the person's banners and their boxes (each its own or the video's), the words fixed, each group
    of captions at its place and size — or left to a caption library style that draws it."""
    lang = lang_of(code)
    font, enc = lang["caption_font"], -1 if lang["rtl"] else 1
    white, key, box = _ass_colour(style["text"]), _ass_colour(style["key"]), _ass_colour(style["box"])
    btext = white
    cadre = montage_doc.CADRES.get((doc or {}).get("bandeau_cadre") or "")
    if cadre:
        box, btext = _ass_colour(cadre[0]), _ass_colour(cadre[1])
    st = (doc or {}).get("sous_titres") or {}
    size, y = int(96 * (st.get("taille") or 100) / 100), CAPTION_PLACES.get(st.get("position") or "bas", CAPTION_Y)
    bans = (doc or {}).get("bandeaux") or []
    up = (lambda s: s.upper()) if lang["upper"] else (lambda s: s)
    head = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        f"Style: Bandeau,{font},78,{btext},{btext},{box},{box},1,0,0,0,100,100,0,0,3,18,0,8,60,60,{BANNER_MARGIN},{enc}",
        f"Style: Sous,{font},{size},{white},{white},&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,7,3,2,70,70,0,{enc}",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    ev, words = [], doc_words(v, doc)
    nexts = [x["start"] for x in v["passages"][1:]] + [None]
    for k, (vp, sp, nxt) in enumerate(zip(v["passages"], passages, nexts)):
        b = bans[k] if k < len(bans) else {}
        text = "" if b.get("cache") else banner_text(b["texte"] if b.get("texte") is not None else sp.get("bandeau") or "")
        if text:                        # until the next sentence starts, at one place: never two banners stacked
            end = nxt if nxt is not None else vp["end"] + 0.25
            own = montage_doc.CADRES.get(b.get("cadre") or "") or (               # "style": the look's, whatever the video's
                (style["box"] if isinstance(style["box"], str) else "#%02X%02X%02X" % tuple(style["box"][:3]), style["text"])
                if b.get("cadre") == "style" else None)
            tint = (f"\\1c{_ass_colour(own[1])}&\\3c{_ass_colour(own[0])}&\\4c{_ass_colour(own[0])}&" if own else "")
            ev.append(f"Dialogue: 0,{_ass_time(vp['start'])},{_ass_time(end)},Bandeau,,0,0,0,,"
                      f"{{\\an8\\pos({W // 2},{BANNER_MARGIN}){tint}}}{up(text)}")
    groups = caption_groups(v, doc)
    for gi, grp in enumerate(groups):
        if grp["style"]:                # a caption library style draws this group (render_doc)
            continue
        g, gy = grp["mots"], CAPTION_PLACES.get(grp["position"], CAPTION_Y)
        fs = "" if grp["taille"] == (st.get("taille") or 100) else f"\\fs{int(96 * grp['taille'] / 100)}"
        for j, w in enumerate(g):
            a = words[w]["start"]
            follows = gi + 1 < len(groups) and groups[gi + 1]["phrase"] == grp["phrase"]
            nxt = g[j + 1] if j + 1 < len(g) else (groups[gi + 1]["mots"][0] if follows else None)
            b = words[nxt]["start"] if nxt is not None else words[g[-1]]["end"] + 0.12
            line = " ".join(("{\\c" + (key if x == w else white) + "&}") + up(words[x]["w"].replace("{", "").replace("}", ""))
                            for x in g)
            ev.append(f"Dialogue: 1,{_ass_time(a)},{_ass_time(b)},Sous,,0,0,0,,{{\\an2\\pos({W // 2},{gy}){fs}}}{line}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(head + ev) + "\n")
    return {"position": f"{st.get('position') or 'bas'}-centre, fixe", "y": y, "taille": size, "police": font,
            "mots_par_ligne": 3, "mot_dit": style["key"], "style_bibliotheque": st.get("style"),
            "bandeau": {"couleur": cadre[0] if cadre else "#%02X%02X%02X" % tuple(style["box"][:3]), "place": "haut",
                        "taille": 78}}


def sharpness(path: str, at: float) -> float:
    """How sharp the picture is at this second (variance of the Laplacian; ~250 sharp, ~15 a blurred transition)."""
    import cv2
    cap = cv2.VideoCapture(path)
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, at) * 1000)
        ok, frame = cap.read()
        return float(cv2.Laplacian(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()) if ok else 0.0
    finally:
        cap.release()


def sharp_start(s: Dict, need: float) -> float:
    """Where the shot really starts: past the source's own blurred transition (the scene detection misses a
    blur or a fade — El Guerguerat's and Cariane's hooks opened on one), keeping room for `need` seconds."""
    a, b = s["start"], s["end"]
    times = [a + d for d in (0.1, 0.4, 0.8, 1.2) if a + d < b - 0.3]
    if len(times) < 2:
        return a
    try:
        scores = [sharpness(s["file"], t) for t in times] + [sharpness(s["file"], (a + b) / 2)]
    except Exception:
        return a
    best = max(scores)
    for t, v in zip(times, scores):
        if v >= 0.4 * best:
            return t if t > a + 0.15 else a
    return a


def _piece_key(e: Dict, s: Dict) -> str:
    import hashlib
    raw = repr((s["file"], s["start"], s["end"], s.get("x"), round(e["fin"] - e["debut"], 3), e.get("zoom") or 1.0,
                e.get("centre")))
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _piece(e: Dict, s: Dict, out: str) -> str:
    """One shot of the edit: cut from its source, cropped to 9:16 around its subject (or where the person centred
    it, as close as they zoomed), a slow push-in, no sound."""
    need = max(0.2, e["fin"] - e["debut"])
    if s.get("graphique"):                  # drawn for the Short (adaptation/graphiques): no crop, no push-in
        _run(["ffmpeg", "-v", "error", "-y", "-i", s["file"], "-an", "-vf",
              f"scale={W}:{H},fps={FPS},setsar=1,tpad=stop_mode=clone:stop_duration={need:.2f}", "-t", f"{need:.3f}",
              "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", out])
        return out
    dur_src, w, h = _probe(s["file"])
    # past a blurred transition, then a little inside the shot: its first frames are often the source's own cut
    first = sharp_start(s, need)
    start = first + min(0.4, max(0.0, (s["end"] - first - need) / 2))
    start = min(start, max(0.0, dur_src - need - 0.05))
    zoom = max(1.0, float(e.get("zoom") or 1.0))
    ch = int(h / zoom) // 2 * 2
    cw = min(w, int(round(ch * 9 / 16)) // 2 * 2)
    centre = e["centre"] if e.get("centre") is not None else (s.get("x") or 0.5)
    cx = min(max(0, int(round(centre * w - cw / 2))), w - cw)
    cy = (h - ch) // 2
    frames = max(1, round(need * FPS))
    vf = [f"crop={cw}:{ch}:{cx}:{cy}", f"scale={int(W * 1.5)}:{int(H * 1.5)}", f"fps={FPS}",
          f"zoompan=z='1+0.10*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS}",
          "setsar=1", "eq=contrast=1.06:saturation=1.10"]
    _run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.2f}", "-t", f"{need:.3f}", "-i", s["file"], "-an",
          "-vf", ",".join(vf), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", out])
    return out


def music_from(start) -> str:
    """The filters taking a looped song (-stream_loop -1, no -ss) from `start` s on, with one clock through its loops.
    Decoded from its beginning, not sought: a seek with a loop in an mp3 gave 43 s for 27 asked and restarted its
    clock at each loop (a music zone after the loop was never applied, the timeline drew the song shifted)."""
    return f"asetpts=N/SR/TB,atrim=start={max(0.0, float(start or 0)):.3f},asetpts=N/SR/TB"


def music_level(m: Dict, total: float) -> str:
    """The music's volume through the video: its level, the person's zones (a 0.2 s ramp in and out of each)."""
    level = f"{MUSIC_GAIN * (m.get('volume') or 100) / 100:.4f}"
    for z in m.get("zones") or []:
        a, b, g = z["debut"], z["fin"], z["volume"] / 100
        level += f"*(1+{g - 1:.3f}*clip((t-{a:.3f})/0.2,0,1)*clip(({b:.3f}-t)/0.2,0,1))"
    return level


def render_doc(doc: Dict, shots: Dict[str, Dict], v: Dict, passages: List[Dict], code: str, style: Dict,
               voice_mp3: str, out: str, work: str, report: Optional[Report] = None) -> Dict:
    """The video from its montage document (montage_doc), in three parts each kept while it does not change: the
    shots (one file per shot, the same cut and framing reused), the picture with its texts, the sound — so a change
    of the music or the effects only makes the sound again (~10 s instead of ~1 min)."""
    import hashlib
    report = report or (lambda phase, f: None)
    os.makedirs(os.path.join(work, "plans"), exist_ok=True)
    edl, total = doc["plans"], montage_doc.total(doc)
    pieces = []
    for k, e in enumerate(edl):
        report(f"rendu des plans ({k + 1}/{len(edl)})", 0.7 * k / len(edl))
        path = os.path.join(work, "plans", _piece_key(e, shots[e["plan"]]) + ".mp4")
        pieces.append(path if os.path.exists(path) else _piece(e, shots[e["plan"]], path))
    ass = os.path.join(work, "textes.ass")
    caps = captions_ass(v, passages, ass, code, style, doc)
    with open(ass, encoding="utf-8") as f:
        key = hashlib.sha1(repr((pieces, f.read(), (doc.get("sous_titres") or {}), [w["w"] for w in doc_words(v, doc)],
                                 doc.get("incrustation"))).encode()).hexdigest()[:16]
    picture = os.path.join(work, f"image_{key}.mp4")
    from adaptation.render import _filter_path
    from adaptation.langs import FONTS_DIR
    if not os.path.exists(picture):
        report("textes à l'écran", 0.75)
        lst = os.path.join(work, "pieces.txt")
        with open(lst, "w") as f:
            f.write("".join(f"file '{os.path.abspath(x)}'\n" for x in pieces))
        silent = os.path.join(work, "image.mp4")
        _run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", silent])
        inputs = ["-i", silent]

        def add_input(*args) -> int:
            inputs.extend(args)
            return sum(1 for x in inputs if x == "-i") - 1
        g, src = [], "0:v"
        inc = doc.get("incrustation") or {}
        if inc.get("fichier") and not inc.get("cache") and os.path.exists(inc["fichier"]):
            k_in = add_input("-i", inc["fichier"])
            until = next((e["debut"] for e in edl if e["phrase"] > (inc.get("phrase") or 1)), total)
            g.append(f"[0:v][{k_in}:v]overlay=0:0:enable='lt(t,{until:.2f})':eof_action=pass[inc]")
            src = "inc"
        g.append(f"[{src}]ass='{_filter_path(ass)}':fontsdir='{_filter_path(FONTS_DIR)}':shaping=complex[b]")
        cur = "b"
        parts = {}                                  # the groups a caption library style draws, by look
        for grp in caption_groups(v, doc):
            if grp["style"]:
                parts.setdefault((grp["style"], grp["position"], grp["taille"]), []).extend(grp["mots"])
        if parts:
            from captions import render as caption_render
            all_words = doc_words(v, doc)
            for n_part, ((lib_style, pos, size), idx) in enumerate(sorted(parts.items(), key=lambda x: min(x[1]))):
                words = [(all_words[k]["w"], all_words[k]["start"], all_words[k]["end"]) for k in sorted(idx)]
                ctx = caption_render.context(code, (0, 0, W, H), words, None)
                ctx.native_y = CAPTION_PLACES.get(pos, CAPTION_Y)     # a style drawn round the middle: moved there
                built = caption_render.build(lib_style, words, ctx, {"taille": size, "position": pos})
                cap_f, cur, _ = caption_render.filters(built, cur, add_input, os.path.join(work, "captions_lib"), (W, H),
                                                       fps=FPS, tag=f"cap{n_part}")
                g += cap_f
        g.append(f"[{cur}]format=yuv420p[vout]")
        _run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(g), "-map", "[vout]", "-an",
              "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-t", f"{total:.3f}", picture])
        for old in os.listdir(work):                # the picture before this one stays (« Annuler »), not the others
            if old.startswith("image_") and old != os.path.basename(picture):
                full = os.path.join(work, old)
                if os.path.getmtime(full) < os.path.getmtime(picture) - 3600:
                    os.remove(full)
    report("mixage du son", 0.9)
    inputs, mix, n = ["-i", voice_mp3], ["[0:a]volume=1.0[v0]"], 1
    labels = ["v0"]
    for k, e in enumerate(doc.get("effets") or []):
        ms = int(e["start"] * 1000)
        inputs += ["-i", os.path.abspath(e["file"])]
        mix.append(f"[{n}:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={e['gain']},adelay={ms}|{ms}[w{k}]")
        labels.append(f"w{k}")
        n += 1
    m = doc.get("musique") or {}
    if m.get("fichier") and os.path.exists(m["fichier"]):
        # looped: a track shorter than the Short (a 28 s jingle) goes round instead of stopping before the end
        fade = float(m.get("fondu") if m.get("fondu") is not None else 1.2)
        inputs += ["-stream_loop", "-1", "-i", m["fichier"]]
        mix.append(f"[{n}:a]{music_from(m.get('debut'))},volume='{music_level(m, total)}':eval=frame,afade=t=in:d=0.6"
                   + (f",afade=t=out:st={max(0.0, total - fade):.2f}:d={fade:.2f}" if fade > 0 else "") + "[m]")
        labels.append("m")
        n += 1
    mix.append("".join(f"[{x}]" for x in labels) + f"amix=inputs={len(labels)}:normalize=0:duration=first,"
               f"apad,atrim=0:{total:.3f},loudnorm=I=-14:TP=-1.5[a]")
    sound = os.path.join(work, "son.m4a")
    _run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(mix), "-map", "[a]",
          "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}", sound])
    report("assemblage", 0.97)
    _run(["ffmpeg", "-v", "error", "-y", "-i", picture, "-i", sound, "-map", "0:v", "-map", "1:a", "-c", "copy",
          "-movflags", "+faststart", "-t", f"{total:.3f}", out])
    return {"captions": caps, "duree": round(total, 2)}


# ---------------------------------------------------------------- sound effects

def sound_moments(v: Dict, passages: List[Dict], roles: List[str], recit: Optional[str], manieres: List[str],
                  total: float) -> List[Dict]:
    """The story's moments that get a sound, most important first ({"t": where it is loudest, "sons", "pourquoi"}):
    an impact on the hook, a ding on the answer of a story that reveals (else a whoosh), a pop when a banner shows
    a figure (sfx.keep leaves it out when the impact plays at the same instant), a whoosh where the story starts
    after its promise. Never over a whispered sentence."""
    vp = v.get("passages") or []
    quiet = [(vp[k]["start"] - 0.6, vp[k]["end"]) for k, m in enumerate(manieres) if m == "chuchote" and k < len(vp)]
    wanted = []
    if vp:
        wanted.append({"t": vp[0]["start"], "sons": ["impact"], "pourquoi": "accroche"})
    for k, role in enumerate(roles[:len(vp)]):
        if role == "reponse":
            wanted.append({"t": vp[k]["start"], "sons": ["ding" if recit in REVELATION else "whoosh"],
                           "pourquoi": "révélation" if recit in REVELATION else "la réponse"})
    for k, ps in enumerate(passages[:len(vp)]):     # on the hook too: it plays when the impact is turned off
        if DIGIT.search(ps.get("bandeau") or ""):
            wanted.append({"t": vp[k]["start"] + 0.05, "sons": ["pop"], "pourquoi": "chiffre"})
    for k, role in enumerate(roles[:len(vp)]):
        if k and role == "promesse":
            wanted.append({"t": vp[k]["start"], "sons": ["whoosh"], "pourquoi": "le récit commence"})
    return [w for w in wanted if not any(a <= w["t"] <= b for a, b in quiet)]


def sound_effects(p: Dict, t: Dict) -> List[Dict]:
    """The files played ([{"kind", "file", "start", "gain", "pourquoi"}]): the moments the family keeps, with the
    sounds switched on in Réglages, each variant in turn."""
    from adaptation import sfx
    rules = SONS_FAMILLE.get(p.get("famille_recit") or _recits.find(p.get("recit")) or "", SONS_FAMILLE["explicatif"])
    v = t.get("voice") or {}
    vp = v.get("passages") or []
    total = (vp[-1]["end"] + 0.6) if vp else 0.0
    roles = [pl.get("role") or "" for pl in (p.get("storyboard") or {}).get("plans") or []]
    lib = sfx.library()
    moments = sfx.keep(sound_moments(v, t["script"]["passages"], roles, p.get("recit"), t.get("manieres") or [], total),
                       total, rules["max"], rules["types"], {k for k, x in lib.items() if x})
    return sfx.sounds(moments, lib)


# ---------------------------------------------------------------- music

def _music_folders(t: Dict) -> List[str]:
    out = []
    if t.get("music_path"):
        out.append(os.path.dirname(t["music_path"]))
    try:
        from channel_manager import ChannelManager
        out.append(ChannelManager().get_assets_dirs(t["channel"])["music"])
    except Exception:
        pass
    out.append(os.path.join("assets", "musiques"))      # the shared songs (Réglages → Voix → Musiques communes)
    return [d for d in dict.fromkeys(out) if os.path.isdir(d)]


def channel_music_rules(t: Dict) -> Dict:
    """The channel's music casting as set now in Réglages (allowed categories, lyrics or not)."""
    try:
        from channel_manager import ChannelManager
        from adaptation import settings
        s = settings.channel_settings(ChannelManager().get_channel_profile(t["channel"]))
        return {"categories": s["musique_categories"], "sans_paroles": s["musique_sans_paroles"]}
    except Exception:
        return {"categories": [], "sans_paroles": False}


def music_choices(t: Dict) -> List[Dict]:
    """Every song a version may use, the channel's allowed ones flagged (for the preview's menu)."""
    from adaptation import musique_casting as mc
    rules = channel_music_rules(t)
    songs = mc.library(_music_folders(t))
    ok = {s["chemin"] for s in mc.allowed(songs, rules["categories"], rules["sans_paroles"])}
    return [{**s, "permise": s["chemin"] in ok} for s in songs]


OUTRO_S = 8.0                   # the last seconds of a song: it often dies away there


def _need(t: Dict) -> float:
    """How long the music must last: the video (the voice and a little after it)."""
    vp = (t.get("voice") or {}).get("passages") or []
    return (vp[-1]["end"] + 1.0) if vp else 40.0


def fit_start(path: str, start: float, need: float) -> float:
    """Where the song starts so that the whole video is said before it ends and dies away (the orcas: its strongest
    moment was found at 83 s of a 99 s song — the music faded to nothing at 0:07 and came back at 0:15)."""
    try:
        dur = float(_run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]).stdout)
    except Exception:
        return start
    if dur <= 0 or start + need <= dur - OUTRO_S:
        return start
    return round(max(0.0, min(start, dur - need - OUTRO_S if dur - need - OUTRO_S > 0 else dur - need)), 2)


def choose_music(p: Dict, t: Dict) -> None:
    """The music casting: among the songs the channel allows (its categories, without lyrics if it asks), the one
    whose mood fits this Short, from its strongest moment. A song chosen by the person (or already) is kept."""
    from adaptation import musique_casting as mc, pipeline as ap
    if t.get("music_chosen"):
        return
    t["music_chosen"] = True
    songs = mc.library(_music_folders(t))
    if not songs:
        return
    if any(s["par"] is None for s in songs):        # a song never classified: the AI listens to it once
        for s in songs:
            if s["par"] is None:
                try:
                    mc.classify(s["chemin"])
                except Exception:
                    pass
        songs = mc.library(_music_folders(t))
    rules = channel_music_rules(t)
    pool = mc.allowed(songs, rules["categories"], rules["sans_paroles"])
    note = ""
    if not pool:                        # nothing fits the channel's rules: say it, and take the best of all
        pool, note = songs, " (aucune musique ne respecte les règles de la chaîne : choisie parmi toutes)"
    sc = t.get("script") or {}
    r = mc.choose(pool, sc.get("titre", ""), " ".join(x["texte"] for x in sc.get("passages") or []),
                  ap._tone(p, t), p.get("recit"))
    song = r["song"]
    start = song.get("moment_fort")
    if start is None:
        start = ap._track_info(song["chemin"])["debut_fort"]
    start = fit_start(song["chemin"], float(start or 0.0), _need(t))
    t.update(music_path=song["chemin"], music_start=start, music_by="ia",
             music_why=(r["pourquoi"] + note)[:240], music_cats=song["categories"], music_lyrics=song["paroles"])
    secours.mark(t, "musique", f"la première musique permise ({r['secours']}) : choisis-en une autre ci-dessous."
                 if r.get("secours") else None)


def set_music(pid: str, channel: str, fichier: Optional[str]) -> Dict:
    """The person changes the music at the preview (None: no music): the voice and the edit are kept, only the
    render is made again."""
    from adaptation import musique_casting as mc, pipeline as ap
    p = ap.load(pid)
    ap._expect(p, "preview_review")
    t = ap.target(p, channel)
    if fichier:
        song = next((s for s in mc.library(_music_folders(t)) if s["fichier"] == fichier), None)
        if not song:
            raise ap.PipelineError("Musique introuvable.")
        start = song.get("moment_fort")
        start = fit_start(song["chemin"], float(start if start is not None else 0.0), _need(t))
        t.update(music_path=song["chemin"], music_start=start,
                 music_why="choisie par toi", music_cats=song["categories"], music_lyrics=song["paroles"])
    else:
        t.update(music_path=None, music_start=0.0, music_why="sans musique (ton choix)", music_cats=[], music_lyrics=None)
    t.update(music_chosen=True, music_by="toi", keep_edit=True, validated=False)
    secours.mark(t, "musique")
    p["status"] = "voicing"
    return ap.save(p)


# ---------------------------------------------------------------- the step: voice + hook + edit + render

def make_target(p: Dict, t: Dict, report: Report, share: float, offset: float, gemini=None) -> Dict:
    from adaptation import pipeline as ap
    base = os.path.join(ap.project_dir(p["project_id"]), t["channel"])
    os.makedirs(base, exist_ok=True)
    mp3 = os.path.join(base, "voice.mp3")
    t["voice"] = _voice(p, t, mp3, report, offset)
    first = t["voice"]["passages"][0]
    hook_s = first["end"] - first["start"]
    if hook_s > HOOK_MAX_S and not t.get("hook_shortened"):
        report(f"accroche raccourcie ({hook_s:.1f} s)", offset + share * 0.1)
        new = shorter_hook(p, t, hook_s, gemini)
        t["hook_shortened"] = True
        if new:
            t.setdefault("corrections", []).append(f"Accroche raccourcie ({hook_s:.1f} s → 3 s) : « {new} »")
            t["script"]["passages"][0]["texte"] = new
            t["voice"] = _voice(p, t, mp3, report, offset + share * 0.15)
    shots = [s for s in p.get("stock") or [] if s.get("garde")]
    kept_ids = {s["id"] for s in shots}
    old = (t.get("montage") or {}).get("plans") or (t.get("preview") or {}).get("montage") or []
    keep = t.pop("keep_edit", False) and old and all(e["plan"] in kept_ids for e in old)
    if not keep:
        report(f"montage {t['channel']}", offset + share * 0.25)
        footage = [s for s in shots if not s.get("graphique")]     # a graphic is placed on its sentence, not chosen
        raw = (gemini or _gemini())._generate_content([{"text": _edit_prompt(t["voice"], editable(footage, len(t["voice"]["passages"])),
                                                                              p.get("realisation"))}],
                                                      max_tokens=16000, timeout=240, temperature=0.4,
                                                      thinking=ECO_THINKING if economique(p) else None)
        lost = secours.failed(raw) or not (raw or {}).get("montage")
        secours.mark(t, "montage", f"fait sans l'IA ({secours.why(raw)}) : les meilleures images dans l'ordre, sans "
                                   "suivre les mots. Revérifie-le, ou reviens au stock pour le refaire." if lost else None)
        edl = graphiques.with_graphics(build_edit({} if lost else raw, t["voice"], footage,
                                                  quick_words(p.get("realisation"), t["voice"])), shots)
    choose_music(p, t)
    if keep and t.get("montage"):       # only the music changed: the person's montage kept, its song replaced
        doc = copy.deepcopy(t["montage"])
        doc["musique"].update(fichier=t.get("music_path"), debut=float(t.get("music_start") or 0.0))
        montage_doc.push(t, doc)
    else:                               # a new montage by the AI: a new document, no history
        doc = montage_doc.new(old if keep else edl, len(t["voice"]["passages"]), t.get("music_path"),
                              t.get("music_start") or 0.0, sound_effects(p, t))
        inc = p.get("incrustation")         # the hook's number, laid over its real picture
        if inc and os.path.exists(inc.get("fichier") or ""):
            doc["incrustation"] = {"fichier": inc["fichier"], "phrase": 1, "cache": False}
        t["montage"], t["montage_versions"] = doc, []
    made = render_target(p, t, report=lambda ph, f: report(f"{ph} ({t['channel']})", offset + share * (0.35 + 0.6 * f)))
    report(f"relecture du montage ({t['channel']})", offset + share * 0.97)
    try:                                            # the AI's montage read again; the person's own is left as they made it
        t["relecture"] = review(p, t, made, gemini)
    except Exception:
        t["relecture"] = []
    return made


REVIEW = """Tu es chef monteur de YouTube Shorts. Voici le montage fini d'un Short, plan par plan : pour chaque plan,
l'image qu'on voit (dans l'ordre des images jointes) et la phrase dite par la voix pendant ce plan.
Sujet : {sujet}

{plans}

Un monteur humain ne cherche pas la scene exacte : il veut une image qui FAIT PASSER L'IDEE de la phrase, forte,
variee, et qui ne contredit jamais ce qui est dit (en actualite, le vrai lieu ou le vrai evenement quand c'est possible).
Pour CHAQUE plan, juge :
- "exact" : l'image montre ce que dit la phrase ;
- "idee" : pas exact, mais fait passer l'idee ;
- "ne_colle_pas" : ni l'un ni l'autre (hors sujet, trop vague, ennuyeux, deja vu juste avant) ;
- "contredit" : l'image dit autre chose que la phrase (un detail qui la dement compte).
Pour "ne_colle_pas" et "contredit" : "a_la_place" = quoi montrer (en francais, court), "recherche" = ce qu'on voit
dans une video qui ferait l'affaire, en anglais, general (ou "schema" / "chiffre anime" / "carte" si aucune video
reelle ne peut le montrer).
JSON uniquement : {{"plans": [{{"plan": 1, "verdict": "exact", "pourquoi": "", "a_la_place": "", "recherche": ""}}]}}"""
NOT_FOOTAGE = ("schema", "chiffre anime", "carte")


def review(p: Dict, t: Dict, preview: Dict, gemini=None) -> List[Dict]:
    """The finished montage read again like an editor reads his cut (the lab: one picture a shot + its sentence, one
    call, 2-3 cents): the shots that contradict their sentence or do not fit, why, and a shot of the stock that conveys
    the idea better (adaptation/vision). -> [{plan, id, verdict, pourquoi, a_la_place, recherche, proposition}]"""
    edl, out = preview["montage"], preview["path"]
    folder = os.path.join(os.path.dirname(out), "relecture")
    os.makedirs(folder, exist_ok=True)
    lines, imgs = [], []
    drawn = {s["id"] for s in p.get("stock") or [] if s.get("graphique")}
    for k, e in enumerate(edl, 1):
        if e["plan"] in drawn:              # a graphic drawn for its sentence: not footage to judge
            continue
        img = os.path.join(folder, f"r_{k:02d}.jpg")
        _run(["ffmpeg", "-v", "error", "-y", "-ss", f"{(e['debut'] + e['fin']) / 2:.2f}", "-i", out, "-frames:v", "1",
              "-vf", "scale=-2:480", "-q:v", "4", img])
        imgs.append(_jpg(img))
        lines.append(f"Plan {k} ({e['debut']:.1f}-{e['fin']:.1f} s) : « {t['script']['passages'][e['phrase'] - 1]['texte']} »")
    r = (gemini or _gemini())._generate_content([{"text": REVIEW.format(sujet=(p.get("reference") or {}).get("sujet") or "",
                                                                        plans="\n".join(lines))}] + imgs,
                                                max_tokens=8000, timeout=240, temperature=0.2)
    if secours.failed(r):
        secours.mark(t, "relecture", f"pas faite ({secours.why(r)}) : regarde toi-même chaque plan.")
        return []
    secours.mark(t, "relecture")
    found = []
    for x in (r or {}).get("plans") or []:
        try:
            k = int(x.get("plan"))
        except (TypeError, ValueError):
            continue
        if not 1 <= k <= len(edl) or x.get("verdict") not in ("ne_colle_pas", "contredit"):
            continue
        found.append({"plan": k, "id": edl[k - 1]["plan"], "verdict": x["verdict"],
                      "pourquoi": str(x.get("pourquoi") or "")[:200], "a_la_place": str(x.get("a_la_place") or "")[:160],
                      "recherche": str(x.get("recherche") or "")[:120], "proposition": None})
    _propose(p, edl, found)
    return found


def _propose(p: Dict, edl: List[Dict], found: List[Dict]) -> None:
    """For each shot flagged, the kept and unused shot of the stock that best shows what the review asks (if any)."""
    from adaptation import vision
    asks = [f for f in found if f["recherche"] and f["recherche"].lower() not in NOT_FOOTAGE]
    if not asks or not vision.available():
        return
    used = {e["plan"] for e in edl}
    spare = [s for s in p.get("stock") or [] if s.get("garde") and s["id"] not in used]
    if not spare:
        return
    try:
        folder = os.path.join(pro_dir(p["project_id"]), "vision")
        paths, owners = [], []
        for s in spare:
            for x in vision._frames(s, folder):
                paths.append(x)
                owners.append(s["id"])
        sc = (vision.embed_images(paths) @ vision.embed_texts([f["recherche"] for f in asks]).T).tolist()
    except Exception:
        return
    taken = set()
    for j, f in enumerate(asks):
        best = {}
        for o, row in zip(owners, sc):
            best[o] = max(best.get(o, -1.0), row[j])
        for sid, v in sorted(best.items(), key=lambda x: -x[1]):
            if v >= vision.FITS and sid not in taken:
                f["proposition"], f["score"] = sid, round(v, 3)
                taken.add(sid)
                break


def render_target(p: Dict, t: Dict, report: Optional[Report] = None) -> Dict:
    """The preview of a version from its montage document, checked (its sound, each sentence at its place)."""
    from adaptation import pipeline as ap
    base = os.path.join(ap.project_dir(p["project_id"]), t["channel"])
    mp3 = os.path.join(base, "voice.mp3")
    doc, out = t["montage"], os.path.join(base, "preview.mp4")
    edl = doc["plans"]
    style = render.style_of(t.get("style") or "classique")
    by_id = {s["id"]: s for s in p.get("stock") or []}
    made = render_doc(doc, by_id, t["voice"], t["script"]["passages"], t["language"], style, mp3, out,
                      os.path.join(base, "pro_work"), report=report)
    # the voice is laid as it was said, whatever the cuts (a cut moved away from a sentence's start once made the
    # check look for that sentence at the cut: « introuvable »)
    c = checks.verify(out, mp3, t["voice"]["passages"], [vp["start"] for vp in t["voice"]["passages"]])
    credits = list(dict.fromkeys(by_id[e["plan"]].get("credit") for e in edl if by_id[e["plan"]].get("credit")))
    effets = doc.get("effets") or []
    return {"path": out, "checks": c, "montage": edl, "credits": credits, "duree": made["duree"],
            # the cover (pipeline._thumbnail): the hook's image, with its banner
            "summary": {"segments": [{"impact": min(1.0, edl[0]["fin"] / 2), "end": edl[0]["fin"]}]},
            "recette": recipe(p, t, edl, by_id, {**made, "effets": effets}), "cle": "pro", "effets": effets}


def run_montage(pid: str, report: Optional[Report] = None, only: Optional[str] = None) -> None:
    """Voice, edit and render of every target (or one, after a voice change) -> preview_review."""
    from adaptation import pipeline as ap
    report = report or (lambda phase, f: None)
    p = ap.load(pid)
    try:
        todo = [t for t in p["targets"] if (only is None or t["channel"] == only)]
        for i, t in enumerate(todo):
            if t.pop("rerender", False) and t.get("montage"):      # the person's montage: only the render again
                revoice(p, t, report)                               # (and the voice, when they changed a sentence)
                t["preview"] = render_target(p, t, report)
            else:
                t["preview"] = make_target(p, t, report, 1 / len(todo), i / len(todo))
            t["validated"] = False
            used = [c for x in p["targets"] for c in (x.get("preview") or {}).get("credits") or []]
            p["credits"] = p["credits_auto"] = " · ".join(dict.fromkeys(used))
            ap.save(p)
        p.update(status="preview_review", error=None, failed_step=None)
        ap.save(p)
    except Exception as e:
        ap.fail(pid, "voicing", e)
    report("terminé", 1.0)


# ---------------------------------------------------------------- the person's montage (the timeline)

def _before(p: Dict, t: Dict) -> None:
    """The preview about to be replaced, kept for « Avant / Après »."""
    from adaptation import pipeline as ap
    base = os.path.join(ap.project_dir(p["project_id"]), t["channel"])
    cur = os.path.join(base, "preview.mp4")
    if os.path.exists(cur):
        import shutil
        shutil.copyfile(cur, os.path.join(base, "preview_avant.mp4"))


def _voice_edits(p: Dict, t: Dict, voix: Optional[List[Dict]]) -> List[Dict]:
    """The sentences the person changed in the timeline ({i, texte, maniere}), checked: a known sentence, a text,
    a manner the channel's family allows. Only the real changes are kept."""
    from adaptation import pipeline as ap, voix_casting
    passages, manieres = t["script"]["passages"], (t.get("manieres") or []) + [""] * len(t["script"]["passages"])
    allowed, out = voix_casting.manieres_for(p), []
    for x in voix or []:
        try:
            i = int(x.get("i"))
        except (TypeError, ValueError):
            continue
        if not 0 <= i < len(passages):
            raise ap.PipelineError("Cette phrase n'existe pas.")
        texte = " ".join(str(x.get("texte") if x.get("texte") is not None else passages[i]["texte"]).split())
        maniere = x.get("maniere") if x.get("maniere") is not None else manieres[i]
        if not texte:
            raise ap.PipelineError(f"Phrase {i + 1} : le texte ne peut pas être vide.")
        if len(texte) > 400:
            raise ap.PipelineError(f"Phrase {i + 1} : trop longue.")
        if maniere not in allowed:
            raise ap.PipelineError(f"Phrase {i + 1} : cette manière n'est pas permise pour la famille de récit de la chaîne.")
        if texte != passages[i]["texte"] or maniere != manieres[i]:
            out.append({"i": i, "texte": texte, "maniere": maniere})
    return out


def set_montage(pid: str, channel: str, doc: Dict, voix: Optional[List[Dict]] = None) -> Dict:
    """The person's montage from the timeline: made safe, kept (the one before for « Annuler »), then rendered
    again in the background — the AI's choices are not asked again. voix: sentences whose text or manner changed
    (the narration is then said again by ElevenLabs and the montage moved onto it, see revoice)."""
    from adaptation import pipeline as ap, sfx
    p = ap.load(pid)
    ap._expect(p, "preview_review")
    t = ap.target(p, channel)
    if not t.get("montage"):
        raise ap.PipelineError("Ce montage date d'avant la timeline : refais l'aperçu une fois.")
    shot_ids = [s["id"] for s in p.get("stock") or [] if s.get("garde")]
    files = [f for x in sfx.library().values() for f in x]
    try:
        new_doc = montage_doc.clean(doc, t["voice"], shot_ids, files)
    except montage_doc.MontageError as e:
        raise ap.PipelineError(str(e))
    inc = t["montage"].get("incrustation")      # the file stays ours: the person only shows or hides it
    new_doc.pop("incrustation", None)
    if inc:
        new_doc["incrustation"] = {**inc, "cache": bool((doc.get("incrustation") or {}).get("cache"))}
    edits = _voice_edits(p, t, voix)
    if new_doc == t["montage"] and not edits:
        raise ap.PipelineError("Rien n'a changé.")
    t["voix_edits"] = edits
    jumps = ([montage_doc.changed_at(t["montage"], new_doc)] if new_doc != t["montage"] else []) + \
        [t["voice"]["passages"][e["i"]]["start"] for e in edits]
    t["montage_jump"] = min(jumps) if jumps else 0.0
    t["montage_son"] = montage_doc.sound_only(t["montage"], new_doc) and not edits
    _before(p, t)
    montage_doc.push(t, new_doc)
    t.update(rerender=True, validated=False)
    p["status"] = "voicing"
    return ap.save(p)


def revoice(p: Dict, t: Dict, report: Optional[Report] = None) -> None:
    """The sentences the person changed said again: the whole narration by ElevenLabs (one voice, one take), then the
    montage moved onto it — every cut, sound and music zone at the same place of its sentence."""
    from adaptation import pipeline as ap
    edits = t.pop("voix_edits", None) or []
    if not edits:
        return
    n = len(t["script"]["passages"])
    manieres = ((t.get("manieres") or []) + [""] * n)[:n]
    old = t["voice"]
    mp3 = os.path.join(ap.project_dir(p["project_id"]), t["channel"], "voice.mp3")
    versions = t.get("montage_versions") or []
    if versions and os.path.exists(mp3):            # the voice before, kept with the montage it fits (« Annuler »)
        import shutil
        kept = os.path.join(os.path.dirname(mp3), f"voice_{len(versions)}.mp3")
        shutil.copyfile(mp3, kept)
        versions[-1]["_voix"] = {"textes": [x["texte"] for x in t["script"]["passages"]],
                                 "manieres": list(t.get("manieres") or []), "voice": old, "mp3": kept}
    for e in edits:
        t["script"]["passages"][e["i"]]["texte"] = e["texte"]
        manieres[e["i"]] = e["maniere"]
    t.update(manieres=manieres, manieres_by="toi")
    t["voice"] = _voice(p, t, mp3, report or (lambda phase, f: None), 0.1)
    shot_ids = [s["id"] for s in p.get("stock") or [] if s.get("garde")]
    moved = montage_doc.retime(t["montage"], old, t["voice"], [e["i"] for e in edits])
    t["montage"] = montage_doc.clean(moved, t["voice"], shot_ids)
    t.setdefault("corrections", []).append("Voix refaite (timeline) : " + ", ".join(
        f"phrase {e['i'] + 1}" for e in edits))


def undo_montage(pid: str, channel: str) -> Dict:
    """« Annuler »: the montage before the last render, rendered again."""
    from adaptation import pipeline as ap
    p = ap.load(pid)
    ap._expect(p, "preview_review")
    t = ap.target(p, channel)
    cur = t.get("montage")
    try:
        back = montage_doc.undo(t)
    except montage_doc.MontageError as e:
        raise ap.PipelineError(str(e))
    snap = back.pop("_voix", None)
    if snap:                                        # that montage was made on the voice before: it comes back too
        import shutil
        mp3 = os.path.join(ap.project_dir(p["project_id"]), t["channel"], "voice.mp3")
        if os.path.exists(snap["mp3"]):
            shutil.copyfile(snap["mp3"], mp3)
        for x, texte in zip(t["script"]["passages"], snap["textes"]):
            x["texte"] = texte
        t.update(voice=snap["voice"], manieres=snap["manieres"])
    t.pop("voix_edits", None)
    t["montage_jump"] = montage_doc.changed_at(cur, back)
    t["montage_son"] = montage_doc.sound_only(cur, back)
    _before(p, t)
    t.update(rerender=True, validated=False)
    p["status"] = "voicing"
    return ap.save(p)


def music_envelope(path: str, start: float, total: float, per_s: int = 4) -> List[float]:
    """The song's loudness from where it starts, `per_s` values a second (0-1), for the timeline's music track."""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-stream_loop", "-1", "-i", path, "-af", music_from(start),
                          "-t", f"{total:.2f}", "-ac", "1", "-ar", "8000", "-f", "f32le", "-"], capture_output=True).stdout
    y = np.frombuffer(raw, np.float32)
    n = max(1, int(total * per_s))
    if not len(y):
        return [0.0] * n
    chunks = np.array_split(np.abs(y), n)
    v = np.array([float(np.sqrt(np.mean(c ** 2))) if len(c) else 0.0 for c in chunks])
    return [round(float(x), 3) for x in v / (v.max() or 1.0)]


def timeline(p: Dict, t: Dict) -> Dict:
    """Everything the timeline shows and offers for one version: its montage document, the sentences and words,
    the kept shots, the sounds, the caption styles, the music's shape."""
    from adaptation import sfx, voix_casting
    from captions import styles as caption_lib
    doc = t.get("montage")
    if not doc:
        return {}
    v = t["voice"]
    pid = p["project_id"]
    total = montage_doc.total(doc)
    stock = [{"id": s["id"], "desc": s.get("desc"), "duree": round(s["end"] - s["start"], 1), "force": s.get("force"),
              "colle": s.get("colle") or [], "secours": s.get("secours_pour"), "graphique": s.get("graphique"),
              "thumb_url": f"/api/adaptations/{pid}/stock/{s['id']}/thumb"}
             for s in p.get("stock") or [] if s.get("garde")]
    m = doc.get("musique") or {}
    env = []
    if m.get("fichier") and os.path.exists(m["fichier"]):
        try:
            env = music_envelope(m["fichier"], float(m.get("debut") or 0), total)
        except Exception:
            env = []
    manieres = t.get("manieres") or []
    return {
        "doc": doc, "total": total, "versions": len(t.get("montage_versions") or []),
        "phrases": [{"debut": vp["start"], "fin": vp["end"], "texte": sp.get("texte"), "bandeau": banner_text(sp.get("bandeau") or ""),
                     "maniere": voix_casting.MANIERES.get(manieres[k] if k < len(manieres) else "", ("Normale",))[0] or "Normale",
                     "maniere_id": manieres[k] if k < len(manieres) else "", "mots": vp["words"]}
                    for k, (vp, sp) in enumerate(zip(v["passages"], t["script"]["passages"]))],
        "manieres_dispo": {k: voix_casting.MANIERES[k][0] for k in voix_casting.manieres_for(p)},
        "rtl": lang_of(t["language"])["rtl"],
        # the look's colours and places, for the instant demo drawn over the video before « Refaire l'aperçu »
        "look": {k: (lambda c: c if isinstance(c, str) else "#%02X%02X%02X" % tuple(c[:3]))(
                     render.style_of(t.get("style") or "classique")[k]) for k in ("text", "key", "box")}
                | {"cadres": montage_doc.CADRES, "places": CAPTION_PLACES, "bandeau_y": BANNER_MARGIN, "w": W, "h": H,
                   "majuscules": lang_of(t["language"])["upper"]},
        "mots": [[w["w"], w["start"], w["end"]] for w in v["words"]],
        "stock": stock,
        "sons": {k: [{"file": f, "nom": os.path.basename(f)} for f in x] for k, x in sfx.library().items() if x},
        "gains": sfx.GAIN,
        "styles_sous_titres": [{"id": x.id, "label": x.label} for x in caption_lib.STYLES.values() if "adaptation" in x.spaces],
        "cadres": list(montage_doc.CADRES), "positions": list(montage_doc.POSITIONS),
        "musiques": [{"fichier": s["chemin"], "titre": s["titre"], "permise": s["permise"]} for s in music_choices(t)],
        "enveloppe": env, "saut": t.get("montage_jump"), "son_seulement": t.get("montage_son"),
        "relecture": t.get("relecture") or [],          # the shots the review flagged (review)
        "changements": person_changes(t),               # what the person changed from the AI's montage
    }


def back_to_stock(pid: str) -> Dict:
    from adaptation import pipeline as ap
    p = ap.load(pid)
    ap._expect(p, "preview_review", "error")
    for t in p["targets"]:
        t["validated"] = False
    p.update(status="stock_review", error=None, failed_step=None)
    return ap.save(p)


# ---------------------------------------------------------------- recipe

def person_changes(t: Dict) -> List[Dict]:
    """What the person changed from the AI's montage (its first version, its first voice) to now (montage_doc.changes)."""
    versions = t.get("montage_versions") or []
    if not versions or not t.get("montage"):
        return []
    ai = {k: v for k, v in versions[0].items() if k != "_voix"}
    first_voice = next((x["_voix"] for x in versions if x.get("_voix")), None)
    if first_voice and first_voice.get("voice") and t.get("voice"):    # the AI's cuts moved onto the voice said again
        try:
            ai = montage_doc.retime(ai, first_voice["voice"], t["voice"], [])
        except montage_doc.MontageError:
            pass
    now_texts = [x["texte"] for x in (t.get("script") or {}).get("passages") or []]
    now_manners = list(t.get("manieres") or [])
    return montage_doc.changes(ai, t["montage"], first_voice["textes"] if first_voice else now_texts, now_texts,
                               first_voice["manieres"] if first_voice else now_manners, now_manners)


def recipe(p: Dict, t: Dict, edl: List[Dict], shots: Dict[str, Dict], made: Dict) -> Dict:
    """The video's recipe in the common shape (recette.py), with what the montage pro adds: the narrative
    style, the voice model, the captions' place/size/font, the banner's colour and place, the cuts per sentence."""
    import recette
    passages = t["script"]["passages"]
    v = t["voice"]
    n_ph = len(passages) or 1
    total = made.get("duree") or (edl[-1]["fin"] if edl else 0)
    hook = v["passages"][0] if v.get("passages") else {}
    musique = None
    doc = t.get("montage") or {}
    m = doc.get("musique") or {"fichier": t.get("music_path"), "debut": t.get("music_start"), "volume": 100, "zones": []}
    if m.get("fichier"):
        musique = {"fichier": os.path.basename(m["fichier"]), "debut_s": m.get("debut"),
                   "pourquoi": t.get("music_why"), "volume": round(MUSIC_GAIN * (m.get("volume") or 100) / 100, 4),
                   "niveau": "constant sous la voix" + (", zones réglées par toi" if m.get("zones") else ""),
                   "zones": m.get("zones") or [],
                   "categories": t.get("music_cats") or [], "paroles": t.get("music_lyrics"),
                   "choisie_par": t.get("music_by") or "ia",
                   "archive": recette.archive(m["fichier"], "musique")}
    return recette.make(
        "adaptation", t["channel"], langue=t["language"], accroche=passages[0]["texte"] if passages else None,
        accroche_s=round(hook.get("end", 0) - hook.get("start", 0), 2) if hook else None, duree_s=round(total, 2),
        plans=len(edl), musique=musique,
        voix={"id": t.get("voice_id"), "modele": v.get("model"), "choisie_par": t.get("voice_by") or "principale",
              "pourquoi": t.get("voice_why"), "manieres": [m or "normale" for m in t.get("manieres") or []],
              "manieres_par": t.get("manieres_by")},
        style={"visuel": t.get("style"), "montage": "pro", "recit": p.get("recit"), "famille_recit": p.get("famille_recit"),
               "recit_par": p.get("recit_par"),
               "dialecte": dialect(t) or ("fusha" if t["language"] == "ar" else None),
               "sous_titres": {"type": "mot par mot, mot dit en couleur", **{k: made["captions"][k] for k in
                               ("position", "y", "taille", "police", "mots_par_ligne", "mot_dit")}},
               "bandeau": made["captions"]["bandeau"], "bandeaux": True, "zoom": "lent par plan",
               "effets_sonores": [{k: e[k] for k in ("kind", "pourquoi", "start")} | {"fichier": os.path.basename(e["file"])}
                                  for e in made.get("effets") or []]},
        details={"projet": p["project_id"], "mode": "idee", "idee": p.get("idee"), "angle": (p.get("angle") or {}).get("titre"),
                 "recit": p.get("recit"), "titre": (t.get("script") or {}).get("titre"),
                 "structure": {"phrases": n_ph, "coupes_par_phrase": round(len(edl) / n_ph, 2),
                               "plan_moyen_s": round(total / max(1, len(edl)), 2)},
                 "plans": [{"phrase": e["phrase"], "debut": e["debut"], "fin": e["fin"],
                            "image": shots[e["plan"]].get("desc"), "source": shots[e["plan"]].get("url"),
                            "force": shots[e["plan"]].get("force")} for e in edl],
                 "corrections": t.get("corrections") or [],
                 # the person's own changes in the timeline (montage_doc): how many renders, and what the last one has
                 "montage_par": "toi" if t.get("montage_versions") else "ia",
                 "modifications": len(t.get("montage_versions") or []),
                 "cadrages": [{"plan": k + 1, "zoom": e.get("zoom"), "centre": e.get("centre")} for k, e in enumerate(edl)
                              if (e.get("zoom") or 1.0) != 1.0 or e.get("centre") is not None],
                 "bandeau_cadre": doc.get("bandeau_cadre"), "sous_titres_regles": doc.get("sous_titres"),
                 # the journal: what the person changed from the AI's montage, element by element
                 "changements": person_changes(t)})
