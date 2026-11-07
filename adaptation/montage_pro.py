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
import json
import os
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional, Tuple

from adaptation import checks, finder, render, sources, voices
from adaptation.langs import lang as lang_of

Report = Callable[[str, float], None]

W, H, FPS = 1080, 1920, 30
MAX_SOURCES = 8                 # videos downloaded for the stock (more sources = more variety)
PAD = 3.0                       # seconds kept around each good moment of a long video
SHOT_S = 2.6                    # a long take is cut into pieces about this long
MAX_SHOTS_PER_SOURCE = 24
HOOK_MAX_S = 3.4                # the first sentence, measured on the real voice
MIN_CUT_S = 1.0
CAPTION_Y = H - 560             # the captions' one place (bottom of the line), never moving
BANNER_MARGIN = 250
MUSIC_GAIN = 0.12
WHOOSH = "assets/sfx/whoosh_little_2.mp3"

# The narrative styles a channel may use: its family is chosen by its look (« actu » = a news channel)
RECITS = {
    "actualite": {
        "news": "NEWS : la phrase 1 dit QUI + QUOI + OU tout de suite (jamais une question sans le sujet) ; puis dans "
                "l'ordre : quand et quoi exactement, pourquoi, ce qui est concerne et ce qui ne l'est pas, la suite.",
        "decryptage": "DECRYPTAGE : la nouvelle en une phrase (qui, quoi, ou), puis ce qu'elle change concretement et "
                      "pourquoi c'est important ; la fin dit la consequence principale.",
        "vrai_faux": "VRAI OU FAUX : part d'une affirmation qui circule sur le sujet, puis les faits verifies un par "
                     "un, et le verdict clair a la fin (vrai, faux, ou en partie).",
        "pour_les_gens": "CE QUE CA CHANGE POUR LES GENS : la nouvelle en une phrase, puis ses effets concrets sur la vie "
                         "de tous les jours (prix, transport, ecole...), la fin dit ce qu'il faut retenir.",
    },
    "explicatif": {
        "mystere": "MYSTERE / REVELATION : une accroche intrigante, des indices qui avancent, la revelation a la fin.",
        "fait_surprenant": "FAIT SURPRENANT : le fait peu connu des la 1re phrase, puis pourquoi il est vrai, preuve par preuve.",
        "origine": "ORIGINE : d'ou vient la chose (objet, invention, habitude), raconte dans l'ordre jusqu'a aujourd'hui.",
        "explication": "EXPLICATION : le phenomene montre, puis comment il marche etape par etape, la fin resume en une phrase.",
    },
}

RECIT_PART = """STYLE DE RECIT IMPOSE (il prime sur les regles generales quand elles different) : {regle}
L'accroche (plan 1) tient en 2 a 3 secondes de voix et NOMME le sujet. Ton {ton}.

"""

CHOOSE_PROMPT = """Sujet d'un YouTube Short : {sujet}
Question : {question}
Faits : {faits}
Styles de recit possibles pour cette chaine :
{styles}
Deja utilises recemment (a eviter si un autre convient aussi bien) : {recents}
Choisis le style qui raconte le MIEUX ce sujet avec ces faits.
JSON uniquement : {{"style": "nom", "pourquoi": "une phrase"}}"""

DESCRIBE = """Tu es monteur video. Voici {n} images, une par plan de rushs (dans l'ordre, ids : {ids}).
Sujet du Short a monter : {sujet}
Pour CHAQUE image, en JSON :
- "desc" : ce qu'on voit, precis, en francais (1 phrase) ;
- "montre" : 3 a 6 mots-cles de ce qu'on voit (objets, lieux, gens, action) ;
- "force" : 1-10, la force visuelle pour un Short (10 = arrete le scroll : grand, net, en mouvement, humain ou
  spectaculaire ; 2 = plan vide, flou, statique, presentateur face camera) ;
- "pertinence" : 0-10, a quel point l'image sert CE sujet (0 = hors sujet, ex. des oranges pour un sujet sur les tomates) ;
- "probleme" : null ou ce qui gene (texte incruste, logo, micro de journaliste, flou, ecran partage, filigrane) ;
- "x" : ou est le sujet horizontalement (0 gauche - 1 droite), pour recadrer en vertical.
JSON uniquement : {{"plans": [{{"id": "", "desc": "", "montre": [""], "force": 5, "pertinence": 5, "probleme": null, "x": 0.5}}]}}"""

EDIT = """Tu es un monteur PRO de YouTube Shorts. Voici la voix off, phrase par phrase, avec ses mots numerotes et leur
instant (secondes) :
{phrases}

Voici les RUSHS disponibles (id | duree | force visuelle 1-10 | pertinence 0-10 | ce qu'on voit | probleme) :
{plans}

Monte la video comme un pro (le sens + l'emotion + l'attention), pas du mot a mot :
- 2 ou 3 COUPES par phrase : chaque plan reste 1,2 a 3 secondes a l'ecran. Une coupe tombe sur le DEBUT d'un mot
  (de preference le mot important : un nom, un chiffre, un verbe fort) -> donne l'indice du mot ou le plan commence.
  La 1re coupe d'une phrase commence au mot 0.
- La TOUTE PREMIERE image = la plus forte qui colle au sujet, pour arreter le scroll.
- L'image ne contredit JAMAIS la phrase ; elle montre l'idee ou l'emotion quand le mot a mot est impossible.
- VARIETE : jamais le meme plan deux fois ; deux plans qui se suivent ne se ressemblent pas (alterne large / serre,
  change de lieu ou d'angle) ; evite deux plans de suite de la meme source quand une autre colle aussi.
- Evite les plans a probleme sauf s'il n'y a pas mieux.
JSON uniquement : {{"montage": [{{"phrase": 1, "coupes": [{{"plan": "id", "mot": 0, "pourquoi": "court"}}]}}]}}"""

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
    return "actualite" if style == "actu" else "explicatif"


def recent_recits(channel: str, n: int = 3) -> List[str]:
    """The narrative styles of the channel's last montage-pro videos (newest first)."""
    import db
    out = []
    for v in db.query_videos(channel=channel):
        r = (((v.get("recette") or {}).get("style") or {}).get("recit"))
        if r:
            out.append((v.get("added_at") or "", r))
    return [r for _, r in sorted(out, reverse=True)[:n]]


def choose_recit(reference: Dict, style: Optional[str], recents: List[str], gemini=None) -> str:
    """The style of the family that tells this subject best, not one of the last ones when another fits."""
    fam = RECITS[family(style)]
    try:
        r = (gemini or _gemini())._generate_content([{"text": CHOOSE_PROMPT.format(
            sujet=reference.get("sujet"), question=reference.get("question"),
            faits="; ".join(reference.get("faits") or [])[:1500],
            styles="\n".join(f"- {k} : {v}" for k, v in fam.items()), recents=", ".join(recents) or "aucun")}],
            max_tokens=800, timeout=60, temperature=0.3)
        name = str((r or {}).get("style") or "").strip()
    except Exception:
        name = ""
    if name not in fam:
        name = next((k for k in fam if k not in recents), next(iter(fam)))
    return name


def recit_part(name: str, style: Optional[str]) -> str:
    regle = RECITS[family(style)].get(name) or next(iter(RECITS[family(style)].values()))
    return RECIT_PART.format(regle=regle, ton="factuel et neutre (information)" if family(style) == "actualite"
                             else "pose et intrigant")


# ---------------------------------------------------------------- 1. the stock

def choose_sources(p: Dict, n: int = MAX_SOURCES) -> List[Dict]:
    """The checked videos with good moments, best first: [{url, titre, duree, moments, score}]."""
    sug = p.get("suggestions") or {}
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
                     "score": sum(3 - finder.RANK[e["niveau"]] for e in good) + (2 if url in chosen else 0)})
    rows.sort(key=lambda r: -r["score"])
    return rows[:n]


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
        spans.append([a, min(b, float(dur)) if dur else b])
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
                     probleme=d.get("probleme") or None, x=min(1.0, max(0.0, _num(d.get("x"), 0.5, float))))


def _num(x, default, kind=int):
    try:
        return kind(x)
    except (TypeError, ValueError):
        return default


def set_aside(shot: Dict) -> Optional[str]:
    """Why the code keeps a shot out of the edit by itself (the person can bring it back), or None."""
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
                for s in shots_of(m["path"], k, os.path.join(base, "thumbs")):
                    s.update(credit=m.get("handle") or m.get("uploader") or "", url=m["url"], titre_source=m["titre"])
                    shots.append(s)
        if not shots:
            raise MontageProError("Aucune source n'a pu être téléchargée : " +
                                  " ; ".join(m.get("failed", "") for m in metas if m)[:300])
        report(f"description des {len(shots)} plans", 0.68)
        describe(shots, (p.get("reference") or {}).get("sujet") or p.get("idee") or "")
        for s in shots:
            why = set_aside(s)
            s.update(garde=why is None, ecarte=why)
        p = ap.load(pid)
        p.update(stock=shots, stock_sources=metas, status="stock_review", error=None, failed_step=None)
        ap.save(p)
    except Exception as e:
        ap.fail(pid, "fetching", e)
    report("terminé", 1.0)


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
    model = t.get("voice_model") or voices.MODEL
    passages = t["script"]["passages"]
    texts = [x["texte"] for x in passages]
    v = t.get("voice") or {}
    if v and v.get("voice_id") == t["voice_id"] and v.get("texts") == texts and v.get("model") == model \
            and os.path.exists(mp3):
        return v                                    # never pay twice for the same narration
    report(f"voix {t['channel']}", at)
    v = voices.synthesize(passages, t["voice_id"], t["language"], mp3, model=model)
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
    try:
        r = (gemini or _gemini())._generate_content([{"text": HOOK_PROMPT.format(
            langue=lang["label"], duree=seconds, mots=words, texte=ps[0]["texte"],
            suivante=ps[1]["texte"] if len(ps) > 1 else "", faits="; ".join(facts),
            regles=LANG_RULES.get(t["language"], LANG_RULES["fr"]))}], max_tokens=1500, timeout=60, temperature=0.4)
        new = " ".join(str((r or {}).get("texte") or "").split())
    except Exception:
        return None
    if not new or len(new.split()) >= len(ps[0]["texte"].split()) or check_facts(new, facts, gemini):
        return None
    return new


# ---------------------------------------------------------------- 3. the edit

def _edit_prompt(v: Dict, shots: List[Dict]) -> str:
    words = v["words"]
    lines = []
    for i, ps in enumerate(v["passages"], 1):
        ws = " ".join(f"{k}:{words[w]['w']}@{words[w]['start']:.2f}" for k, w in enumerate(ps["words"]))
        lines.append(f"Phrase {i} ({ps['start']:.2f}-{ps['end']:.2f} s) : {ws}")
    rushes = "\n".join(f"{s['id']} | {s['end'] - s['start']:.1f}s | {s.get('force')} | {s.get('pertinence')} | "
                       f"{s.get('desc')} | {s.get('probleme') or '-'}" for s in shots)
    return EDIT.format(phrases="\n".join(lines), plans=rushes)


def build_edit(raw: Dict, v: Dict, shots: List[Dict]) -> List[Dict]:
    """Gemini's edit made safe: only kept shots, never one twice, cuts on the words' starts, at least
    MIN_CUT_S each, the whole voice covered (each sentence until the next one starts, the last + 0.6 s).
    [{phrase, plan, debut, fin}] in video time."""
    by_id = {s["id"]: s for s in shots}
    spare = sorted(shots, key=lambda s: (-(s.get("pertinence") or 0), -(s.get("force") or 0)))
    used, edl = set(), []
    words, ps_all = v["words"], v["passages"]
    asked = {int(m.get("phrase") or 0): m.get("coupes") or [] for m in (raw or {}).get("montage") or [] if isinstance(m, dict)}
    ends = [ps["start"] for ps in ps_all[1:]] + [v["duration"] + 0.6]

    def free(prefer: Optional[str] = None) -> Optional[str]:
        if prefer in by_id and prefer not in used:
            return prefer
        last = by_id.get(edl[-1]["plan"]) if edl else None
        for s in spare:                             # the best unused one, from another source when possible
            if s["id"] not in used and (not last or s["source"] != last["source"]):
                return s["id"]
        return next((s["id"] for s in spare if s["id"] not in used), None)
    for i, (ps, end) in enumerate(zip(ps_all, ends), 1):
        start = 0.0 if i == 1 else ps["start"]
        cuts = sorted((c for c in asked.get(i, []) if isinstance(c, dict)), key=lambda c: _num(c.get("mot"), 0))
        times, plans = [], []
        for c in cuts or [{"mot": 0}]:
            k = min(max(0, _num(c.get("mot"), 0)), len(ps["words"]) - 1) if ps["words"] else 0
            at = start if not times else words[ps["words"][k]]["start"]
            if times and at - times[-1] < MIN_CUT_S:            # too short: this cut is dropped
                continue
            sid = free(str(c.get("plan") or ""))
            if sid is None:
                break
            used.add(sid)
            times.append(at)
            plans.append(sid)
        if not plans:
            sid = free()
            if sid is None:
                raise MontageProError("Plus assez de plans dans le stock pour monter la vidéo.")
            used.add(sid)
            times, plans = [start], [sid]
        if end - times[-1] < MIN_CUT_S and len(plans) > 1:     # the last piece too short: merged into the one before
            used.discard(plans.pop())
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


def captions_ass(v: Dict, passages: List[Dict], path: str, code: str, style: Dict) -> Dict:
    """Banner (top, one per sentence) + captions 3 words at a time, the spoken word in the key colour, at ONE
    fixed place (\\pos: libass would push a line up when it overlaps the previous one). Arabic: every word its
    own colour run and the styles right-to-left (render.captions_ass's recipe), else the words come out of order."""
    lang = lang_of(code)
    font, enc = lang["caption_font"], -1 if lang["rtl"] else 1
    white, key, box = _ass_colour(style["text"]), _ass_colour(style["key"]), _ass_colour(style["box"])
    up = (lambda s: s.upper()) if lang["upper"] else (lambda s: s)
    head = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        f"Style: Bandeau,{font},78,{white},{white},{box},{box},1,0,0,0,100,100,0,0,3,18,0,8,60,60,{BANNER_MARGIN},{enc}",
        f"Style: Sous,{font},96,{white},{white},&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,7,3,2,70,70,0,{enc}",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    ev, words = [], v["words"]
    nexts = [x["start"] for x in v["passages"][1:]] + [None]
    for vp, sp, nxt in zip(v["passages"], passages, nexts):
        text = banner_text(sp.get("bandeau") or "")
        if text:                        # until the next sentence starts, at one place: never two banners stacked
            end = nxt if nxt is not None else vp["end"] + 0.25
            ev.append(f"Dialogue: 0,{_ass_time(vp['start'])},{_ass_time(end)},Bandeau,,0,0,0,,"
                      f"{{\\an8\\pos({W // 2},{BANNER_MARGIN})}}{up(text)}")
        idx = vp["words"]
        groups = [idx[i:i + 3] for i in range(0, len(idx), 3)]
        for gi, g in enumerate(groups):
            for j, w in enumerate(g):
                a = words[w]["start"]
                nxt = g[j + 1] if j + 1 < len(g) else (groups[gi + 1][0] if gi + 1 < len(groups) else None)
                b = words[nxt]["start"] if nxt is not None else words[g[-1]]["end"] + 0.12
                line = " ".join(("{\\c" + (key if x == w else white) + "&}") + up(words[x]["w"].replace("{", "").replace("}", ""))
                                for x in g)
                ev.append(f"Dialogue: 1,{_ass_time(a)},{_ass_time(b)},Sous,,0,0,0,,{{\\an2\\pos({W // 2},{CAPTION_Y})}}{line}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(head + ev) + "\n")
    return {"position": "bas-centre, fixe", "y": CAPTION_Y, "taille": 96, "police": font, "mots_par_ligne": 3,
            "mot_dit": style["key"], "bandeau": {"couleur": "#%02X%02X%02X" % tuple(style["box"][:3]), "place": "haut",
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


def _piece(e: Dict, s: Dict, out: str) -> str:
    """One shot of the edit: cut from its source, cropped to 9:16 around its subject, a slow push-in, no sound."""
    need = max(0.2, e["fin"] - e["debut"])
    dur_src, w, h = _probe(s["file"])
    # past a blurred transition, then a little inside the shot: its first frames are often the source's own cut
    first = sharp_start(s, need)
    start = first + min(0.4, max(0.0, (s["end"] - first - need) / 2))
    start = min(start, max(0.0, dur_src - need - 0.05))
    cw = min(w, int(round(h * 9 / 16)) // 2 * 2)
    cx = min(max(0, int(round((s.get("x") or 0.5) * w - cw / 2))), w - cw)
    frames = max(1, round(need * FPS))
    vf = [f"crop={cw}:{h}:{cx}:0", f"scale={int(W * 1.5)}:{int(H * 1.5)}", f"fps={FPS}",
          f"zoompan=z='1+0.10*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS}",
          "setsar=1", "eq=contrast=1.06:saturation=1.10"]
    _run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.2f}", "-t", f"{need:.3f}", "-i", s["file"], "-an",
          "-vf", ",".join(vf), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", out])
    return out


def render_video(edl: List[Dict], shots: Dict[str, Dict], v: Dict, passages: List[Dict], code: str, style: Dict,
                 voice_mp3: str, out: str, work: str, music: Optional[Tuple[str, float]] = None,
                 report: Optional[Report] = None) -> Dict:
    report = report or (lambda phase, f: None)
    os.makedirs(work, exist_ok=True)
    pieces = []
    for k, e in enumerate(edl):
        report(f"plan {k + 1}/{len(edl)}", k / len(edl))
        pieces.append(_piece(e, shots[e["plan"]], os.path.join(work, f"piece_{k:02d}.mp4")))
    lst = os.path.join(work, "pieces.txt")
    with open(lst, "w") as f:
        f.write("".join(f"file '{os.path.abspath(x)}'\n" for x in pieces))
    silent = os.path.join(work, "image.mp4")
    _run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", silent])
    ass = os.path.join(work, "textes.ass")
    caps = captions_ass(v, passages, ass, code, style)
    total = edl[-1]["fin"] if edl else v["duration"]
    inputs, mix, n = ["-i", voice_mp3], ["[1:a]volume=1.0[v0]"], 2
    labels = ["v0"]
    starts = [ps["start"] for ps in v["passages"][1:]]
    if os.path.exists(WHOOSH):
        for k, t0 in enumerate(starts):             # a short whoosh on each new sentence (not on every cut)
            ms = int(max(0.0, t0 - 0.25) * 1000)
            inputs += ["-i", os.path.abspath(WHOOSH)]
            mix.append(f"[{n}:a]volume=0.35,adelay={ms}|{ms}[w{k}]")
            labels.append(f"w{k}")
            n += 1
    if music and music[0] and os.path.exists(music[0]):
        inputs += ["-ss", f"{max(0.0, float(music[1] or 0)):.2f}", "-i", music[0]]
        mix.append(f"[{n}:a]volume={MUSIC_GAIN},afade=t=in:d=0.6,afade=t=out:st={max(0.0, total - 1.2):.2f}:d=1.2[m]")
        labels.append("m")
        n += 1
    mix.append("".join(f"[{x}]" for x in labels) + f"amix=inputs={len(labels)}:normalize=0:duration=first,"
               f"apad,atrim=0:{total:.3f},loudnorm=I=-14:TP=-1.5[a]")
    from adaptation.render import _filter_path
    from adaptation.langs import FONTS_DIR
    report("assemblage", 0.95)
    _run(["ffmpeg", "-v", "error", "-y", "-i", silent] + inputs +
         ["-filter_complex", f"[0:v]ass='{_filter_path(ass)}':fontsdir='{_filter_path(FONTS_DIR)}':shaping=complex,"
          f"format=yuv420p[vout];" + ";".join(mix),
          "-map", "[vout]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}", out])
    return {"captions": caps, "duree": round(total, 2)}


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


def choose_music(p: Dict, t: Dict) -> None:
    """Like the other videos: a track of the channel's library or the shared songs, chosen by the AI for the
    Short's tone, from its strongest part. A track chosen by hand (or already chosen) is kept."""
    from adaptation import pipeline as ap, tone, script as sc_mod
    if t.get("music_chosen") and t.get("music_path"):
        return
    tracks = [os.path.join(d, f) for d in _music_folders(t) for f in sorted(os.listdir(d))
              if f.lower().endswith((".mp3", ".wav", ".m4a"))]
    t["music_chosen"] = True
    if not tracks:
        return
    if len(tracks) == 1:
        t.update(music_path=tracks[0], music_start=ap._track_info(tracks[0])["debut_fort"])
        return
    try:
        infos = [ap._track_info(x) for x in tracks]
        listing = "\n".join(f"{n}. {os.path.basename(x)} / {i['bpm'] or '?'} BPM / energie {i['energie']}"
                            for n, (x, i) in enumerate(zip(tracks, infos), 1))
        sc = t.get("script") or {}
        r = sc_mod._gemini()._generate_content([{"text": ap.MOOD_PROMPT.format(
            titre=sc.get("titre", ""), resume=" ".join(x["texte"] for x in sc.get("passages") or [])[:600],
            morceaux=listing, ton=tone.music_hint(ap._tone(p, t)))}], max_tokens=1000, timeout=60, temperature=0.2)
        n = int(r.get("morceau")) - 1
    except Exception:
        return
    if 0 <= n < len(tracks):
        t.update(music_path=tracks[n], music_start=infos[n]["debut_fort"], music_why=str(r.get("pourquoi") or "")[:200])


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
    report(f"montage {t['channel']}", offset + share * 0.25)
    raw = (gemini or _gemini())._generate_content([{"text": _edit_prompt(t["voice"], shots)}],
                                                  max_tokens=16000, timeout=240, temperature=0.4)
    edl = build_edit(raw if isinstance(raw, dict) else {}, t["voice"], shots)
    choose_music(p, t)
    style_name = t.get("style") or "classique"
    style = render.style_of(style_name)
    out = os.path.join(base, "preview.mp4")
    by_id = {s["id"]: s for s in p.get("stock") or []}
    made = render_video(edl, by_id, t["voice"], t["script"]["passages"], t["language"], style, mp3, out,
                        os.path.join(base, "pro_work"),
                        music=(t["music_path"], t.get("music_start") or 0.0) if t.get("music_path") else None,
                        report=lambda ph, f: report(f"{ph} ({t['channel']})", offset + share * (0.35 + 0.6 * f)))
    starts = []
    for ph in range(1, len(t["voice"]["passages"]) + 1):
        starts.append(next(e["debut"] for e in edl if e["phrase"] == ph))
    c = checks.verify(out, mp3, t["voice"]["passages"], starts)
    credits = list(dict.fromkeys(by_id[e["plan"]].get("credit") for e in edl if by_id[e["plan"]].get("credit")))
    return {"path": out, "checks": c, "montage": edl, "credits": credits, "duree": made["duree"],
            # the cover (pipeline._thumbnail): the hook's image, with its banner
            "summary": {"segments": [{"impact": min(1.0, edl[0]["fin"] / 2), "end": edl[0]["fin"]}]},
            "recette": recipe(p, t, edl, by_id, made), "cle": "pro"}


def run_montage(pid: str, report: Optional[Report] = None, only: Optional[str] = None) -> None:
    """Voice, edit and render of every target (or one, after a voice change) -> preview_review."""
    from adaptation import pipeline as ap
    report = report or (lambda phase, f: None)
    p = ap.load(pid)
    try:
        todo = [t for t in p["targets"] if (only is None or t["channel"] == only)]
        for i, t in enumerate(todo):
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


def back_to_stock(pid: str) -> Dict:
    from adaptation import pipeline as ap
    p = ap.load(pid)
    ap._expect(p, "preview_review", "error")
    for t in p["targets"]:
        t["validated"] = False
    p.update(status="stock_review", error=None, failed_step=None)
    return ap.save(p)


# ---------------------------------------------------------------- recipe

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
    if t.get("music_path"):
        musique = {"fichier": os.path.basename(t["music_path"]), "debut_s": t.get("music_start"),
                   "pourquoi": t.get("music_why"), "volume": MUSIC_GAIN, "niveau": "constant sous la voix",
                   "archive": recette.archive(t["music_path"], "musique")}
    return recette.make(
        "adaptation", t["channel"], langue=t["language"], accroche=passages[0]["texte"] if passages else None,
        accroche_s=round(hook.get("end", 0) - hook.get("start", 0), 2) if hook else None, duree_s=round(total, 2),
        plans=len(edl), musique=musique, voix={"id": t.get("voice_id"), "modele": v.get("model")},
        style={"visuel": t.get("style"), "montage": "pro", "recit": p.get("recit"),
               "sous_titres": {"type": "mot par mot, mot dit en couleur", **{k: made["captions"][k] for k in
                               ("position", "y", "taille", "police", "mots_par_ligne", "mot_dit")}},
               "bandeau": made["captions"]["bandeau"], "bandeaux": True, "zoom": "lent par plan",
               "effets_sonores": "whoosh à chaque phrase"},
        details={"projet": p["project_id"], "mode": "idee", "idee": p.get("idee"), "angle": (p.get("angle") or {}).get("titre"),
                 "recit": p.get("recit"), "titre": (t.get("script") or {}).get("titre"),
                 "structure": {"phrases": n_ph, "coupes_par_phrase": round(len(edl) / n_ph, 2),
                               "plan_moyen_s": round(total / max(1, len(edl)), 2)},
                 "plans": [{"phrase": e["phrase"], "debut": e["debut"], "fin": e["fin"],
                            "image": shots[e["plan"]].get("desc"), "source": shots[e["plan"]].get("url"),
                            "force": shots[e["plan"]].get("force")} for e in edl],
                 "corrections": t.get("corrections") or []})
