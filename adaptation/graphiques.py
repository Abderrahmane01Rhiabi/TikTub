"""
The animated graphics of the montage pro (point 6; the lab: docs/recherches/labo_graphiques.md) — what the AI
director notes « to draw » (adaptation/realisateur: chiffre / carte / schema), made by the app with HyperFrames (an
animated HTML page rendered to a video, on the PC, no account, no web at render time).

  chiffre   a fixed template (graphiques_modeles/chiffre.html): a counter up to the number, then its words — the
            number must be in the verified facts
  carte     a fixed template (carte.html): the coasts only, never a border; a wide view, a zoom to the place, a pin,
            its name — places found by OpenStreetMap (Nominatim), never placed by the AI
  schema    written by Gemini Flash as a whole animation (the lab: Flash clearer than Pro on 3/3, ~2-3 cents), checked
            by `hyperframes lint`, asked once more when it fails

The rules agreed with the user (2026-11-09): at most MAX_PLANS full-screen graphics a Short, never two sentences in a
row; the hook keeps its real picture — a number there is laid OVER it (transparent), a map or a schema is not made.
A graphic becomes a shot of the stock (source "graphiques"), kept for its sentence: seen, removed or brought back
like any shot; the hook's number is the montage's « incrustation » (adaptation/montage_doc).
"""

import glob
import json
import os
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from typing import Callable, Dict, List, Optional, Tuple

from adaptation.langs import FONTS_DIR

MODELES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "graphiques_modeles")
HYPERFRAMES = "hyperframes@0.9.26"          # pinned: the same render every time
KINDS = ("chiffre", "carte", "schema")
MAX_PLANS = 2
DURATION = 6.0                              # each graphic lasts this long; a sentence takes what it needs
RENDER_TIMEOUT = 420
FONTS = ("Tajawal-Black.ttf", "Tajawal-ExtraBold.ttf", "Montserrat-Black.ttf")
VENDOR = {"chiffre": ("gsap.min.js",), "schema": ("gsap.min.js",),
          "carte": ("gsap.min.js", "d3-array.min.js", "d3-geo.min.js", "topojson-client.min.js", "land10.js")}
WIDE_SPAN, CLOSE_SPAN = 14.0, 1.4          # degrees of longitude across the screen (wide view, then the place)
NEAR = 1.6                                  # degrees: closer labels write over each other in the wide view
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

Report = Callable[[str, float], None]


class GraphiqueError(RuntimeError):
    pass


# ---------------------------------------------------------------- which graphics a Short gets

SCALES = ((r"(?:ألف|آلاف|الف|mille|thousand)", 1e3), (r"(?:مليون|ملايين|millions?)", 1e6),
          (r"(?:مليار|مليارات|milliards?|billions?)", 1e9))


def numbers_in(text: str) -> List[float]:
    """Every number written in a text: « 115 000 », « 5,3 », « 5.3 », « 92.47 », Arabic digits too — and with its
    scale word as well (« 115 ألف » gives 115 and 115000, « 5,3 millions » 5.3 and 5300000)."""
    out = []
    text = str(text or "").translate(ARABIC_DIGITS)
    for m in re.finditer(r"\d[\d\s  .,]*\d|\d", text):
        s = re.sub(r"[\s  ]", "", m.group(0))
        s = re.sub(r"[.,](?=\d{3}(\D|$))", "", s)        # thousands: « 120.000 », « 1,800,000 »
        s = s.replace(",", ".")
        try:
            v = float(s)
        except ValueError:
            continue
        out.append(v)
        after = text[m.end():m.end() + 14].strip()
        for word, k in SCALES:
            if re.match(word, after, re.I):
                out.append(round(v * k, 6))
    return out


def in_facts(valeur, facts: List[str]) -> bool:
    """The number of a graphic is one the verified facts give (never a number the AI made up)."""
    try:
        v = float(str(valeur).translate(ARABIC_DIGITS).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return False
    return any(abs(v - x) < 1e-9 * max(1.0, abs(v)) for f in facts for x in numbers_in(f))


def plan(realisation: Optional[List[Dict]], facts: List[str], codes: List[str]) -> List[Dict]:
    """The graphics this Short gets, by the rules: [{phrase, type, mode (plan | incrustation), spec}]. One language
    for every version (a graphic's words are in it), else none."""
    if not realisation or len(set(codes)) != 1:
        return []
    out, last, full = [], None, 0
    for e in realisation:
        kind, g, k = e.get("type"), e.get("graphique"), e.get("phrase")
        if kind not in KINDS or not isinstance(g, dict) or not isinstance(k, int):
            continue
        if kind == "chiffre" and not in_facts(g.get("valeur"), facts):
            continue
        if kind == "carte" and not str(g.get("lieu") or "").strip():
            continue
        if k == 1:                          # the hook keeps its real picture
            if kind == "chiffre":
                out.append({"phrase": 1, "type": kind, "mode": "incrustation", "spec": g})
            continue
        if full >= MAX_PLANS or (last is not None and k - last <= 1):
            continue
        out.append({"phrase": k, "type": kind, "mode": "plan", "spec": g})
        last, full = k, full + 1
    return out


# ---------------------------------------------------------------- places (OpenStreetMap)

_PLACES: Dict[str, Optional[Tuple[float, float]]] = {}
_LAST_ASK = [0.0]


def geocode(query: str) -> Optional[Tuple[float, float]]:
    """(lon, lat) of a place by OpenStreetMap's Nominatim (free; one question a second, its rule), or None."""
    q = " ".join(str(query or "").split())
    if not q:
        return None
    if q in _PLACES:
        return _PLACES[q]
    time.sleep(max(0.0, 1.1 - (time.time() - _LAST_ASK[0])))
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": q, "format": "json", "limit": 1})
    found = None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TikTub/1.0 (personal video tool)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            rows = json.loads(r.read().decode("utf-8"))
        if rows:
            found = (round(float(rows[0]["lon"]), 4), round(float(rows[0]["lat"]), 4))
    except Exception:
        found = None
    _LAST_ASK[0] = time.time()
    _PLACES[q] = found
    return found


# ---------------------------------------------------------------- what each template is given

def chiffre_data(g: Dict, rtl: bool, mode: str) -> Dict:
    return {"valeur": str(g["valeur"]).translate(ARABIC_DIGITS).replace(" ", "").replace(",", "."),
            "unite": str(g.get("unite") or "")[:40], "titre": str(g.get("titre") or "")[:40], "mode": mode, "rtl": rtl}


def carte_data(g: Dict, facts: List[str], rtl: bool, find=geocode) -> Optional[Dict]:
    """The map: the place (and its country, its landmarks) found on OpenStreetMap — None when the place is not."""
    at = find(g.get("lieu"))
    if not at:
        return None
    labels = []
    country = find(g.get("pays")) if g.get("pays") else None
    if country and g.get("pays_nom"):
        labels.append({"at": list(country), "text": str(g["pays_nom"])[:30], "country": True, "from": "wide"})
    for r in (g.get("reperes") or [])[:2]:
        where = find(r.get("lieu")) if isinstance(r, dict) else None
        apart = lambda x: max(abs(x[0] - where[0]), abs(x[1] - where[1]))
        # far enough to read in the wide view (Casablanca, Rabat and Benslimane wrote over each other)
        if where and r.get("nom") and apart(at) >= NEAR and all(apart(x["at"]) >= NEAR for x in labels):
            labels.append({"at": list(where), "text": str(r["nom"])[:30], "from": "wide"})
    stat = g.get("chiffre") if isinstance(g.get("chiffre"), dict) else None
    if stat and not in_facts(stat.get("valeur"), facts):
        stat = None                          # a number on the map is a verified one too
    return {"wide": {"center": list(at), "span": WIDE_SPAN}, "close": {"center": list(at), "span": CLOSE_SPAN},
            "place": {"at": list(at), "name": str(g.get("nom") or g.get("lieu"))[:40]}, "labels": labels,
            "stat": {"valeur": str(stat["valeur"]).translate(ARABIC_DIGITS).replace(" ", "").replace(",", "."),
                     "unite": str(stat.get("unite") or "")[:30]} if stat else None, "rtl": rtl}


def fill(template: str, data: Dict) -> str:
    with open(os.path.join(MODELES, template), encoding="utf-8") as f:
        html = f.read()
    return html.replace("/*DATA*/{}", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))


# ---------------------------------------------------------------- render

def npx() -> Optional[str]:
    """The npx that runs HyperFrames (the server may start without nvm in its PATH)."""
    found = shutil.which("npx")
    if found:
        return found
    nvm = sorted(glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/npx")))
    return nvm[-1] if nvm else None


def available() -> bool:
    return npx() is not None


def _hf(args: List[str], timeout: int) -> subprocess.CompletedProcess:
    exe = npx()
    if not exe:
        raise GraphiqueError("Node (npx) introuvable : les graphiques animés ont besoin de HyperFrames.")
    env = {**os.environ, "PATH": os.path.dirname(exe) + os.pathsep + os.environ.get("PATH", ""),
           "HYPERFRAMES_TELEMETRY": "0"}
    return subprocess.run([exe, "-y", HYPERFRAMES, *args], capture_output=True, text=True, timeout=timeout, env=env)


def folder_for(work: str, name: str, kind: str, html: str) -> str:
    """One project folder a graphic: its page as index.html, the fonts and the libraries it needs beside it."""
    d = os.path.join(work, name)
    os.makedirs(os.path.join(d, "vendor"), exist_ok=True)
    os.makedirs(os.path.join(d, "fonts"), exist_ok=True)
    for f in VENDOR[kind]:
        if not os.path.exists(os.path.join(d, "vendor", f)):
            shutil.copy(os.path.join(MODELES, "vendor", f), os.path.join(d, "vendor", f))
    for f in FONTS:
        if not os.path.exists(os.path.join(d, "fonts", f)):
            shutil.copy(os.path.join(FONTS_DIR, f), os.path.join(d, "fonts", f))
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    return d


def lint(folder: str) -> List[str]:
    """The errors HyperFrames finds in a page (empty = clean)."""
    r = _hf(["lint", folder], 180)
    text = (r.stdout or "") + (r.stderr or "")
    return [ln.strip() for ln in text.splitlines() if ln.strip().startswith("✗")][:8]


def render(folder: str, out: str, transparent: bool = False) -> str:
    os.makedirs(os.path.dirname(out), exist_ok=True)
    r = _hf(["render", "-o", out, "--format", "mov" if transparent else "mp4", folder], RENDER_TIMEOUT)
    if not os.path.exists(out) or os.path.getsize(out) < 1000:
        tail = " ".join(((r.stderr or "") + (r.stdout or "")).split()[-40:])
        raise GraphiqueError(f"rendu impossible : {tail[:300]}")
    return out


# ---------------------------------------------------------------- the schema, written by Gemini

SCHEMA_PROMPT = """Tu es motion designer. Ecris un SCHEMA ANIME de 6 secondes pour un YouTube Short vertical (1080x1920),
qui fait COMPRENDRE cette phrase dite par la voix off : « {phrase} »
Ce que le realisateur veut montrer : {quoi}
Faits verifies (les seuls chiffres et noms permis) : {faits}
Langue des textes a l'ecran : {langue} (peu de mots : 1 a 6 etiquettes courtes, JAMAIS plus petites que 48 px ; un
chiffre seulement s'il est dans la phrase ou les faits). Le haut (0-320 px) et le bas (1450-1920 px) restent VIDES :
la video y met son bandeau et ses sous-titres.

Style : flat design net, formes SVG simples et lisibles (pas de dessin realiste), fond sombre degrade, 3-4 couleurs
vives, fleches epaisses animees. Tout est en place avant 3,5 s, puis un mouvement doux continue jusqu'a 6 s (rien de
fige). Le sens doit se lire SANS le son.

Regles techniques STRICTES (HyperFrames) — reponds un fichier HTML complet :
- <script src="vendor/gsap.min.js"></script> seul script externe ; aucune autre ressource (ni image, ni web, ni fetch) ;
- polices : @font-face {{ font-family: "Tajawal"; font-weight: 900; src: url("fonts/Tajawal-Black.ttf"); }} et
  @font-face {{ font-family: "Montserrat"; font-weight: 900; src: url("fonts/Montserrat-Black.ttf"); }} (arabe : Tajawal,
  direction rtl ; chiffres et latin : Montserrat) ;
- body {{ margin:0; background:#06080e }} ; racine : <div id="root" data-composition-id="graphique" data-start="0"
  data-width="1080" data-height="1920" data-duration="6"> avec #root {{ position:relative; width:100%; height:100%;
  overflow:hidden }} ; tout dedans en position absolute ; SVG en viewBox="0 0 1080 1920" ;
- UNE timeline : const tl = gsap.timeline({{ paused: true }}); ... window.__timelines["graphique"] = tl; (rien d'autre
  ne bouge : pas de setInterval, requestAnimationFrame, Date, Math.random, animations CSS ni transitions CSS) ;
- etat de depart dans gsap.fromTo (jamais une transform CSS sur un element que GSAP anime, ni translate(-50%,-50%)
  pour centrer : centre avec left/top et des marges) ; pas de <br> ;
- repeat seulement avec un nombre fini ; tout se termine avant 6 s.
JSON uniquement : {{"html": "<!doctype html>..."}}"""

LANGUES = {"fr": "francais", "ar": "arabe (darija marocaine)", "en": "anglais"}


def outside(html: str) -> Optional[str]:
    """A resource from outside the PC in a written page (the render must need nothing from the web)."""
    text = re.sub(r"http://www\.w3\.org/[\w/.-]+", "", html)
    m = re.search(r"(https?:)?//[\w.-]+\.[a-z]{2,}|fetch\(|XMLHttpRequest|<img\b|<link\b", text)
    return m.group(0) if m else None


def schema_html(spec: Dict, phrase: str, facts: List[str], code: str, gemini=None, fix: str = "") -> str:
    from adaptation.script import _gemini
    r = (gemini or _gemini())._generate_content([{"text": SCHEMA_PROMPT.format(
        phrase=phrase, quoi=str(spec.get("contenu") or "")[:400], faits="; ".join(facts)[:2500],
        langue=LANGUES.get(code, code)) + fix}], max_tokens=24000, timeout=240, temperature=0.6)
    html = (r or {}).get("html") if isinstance(r, dict) else None
    if not html or "window.__timelines" not in html:
        raise GraphiqueError("le schéma n'a pas été écrit")
    return html


# ---------------------------------------------------------------- the graphics of a project

def phrase_text(p: Dict, k: int, code: str) -> str:
    plans = (p.get("storyboard") or {}).get("plans") or []
    t = (plans[k - 1].get("textes") or {}) if 0 < k <= len(plans) else {}
    return ((t.get(code) or {}).get("texte") or "")


def make_one(p: Dict, item: Dict, work: str, gemini=None, find=geocode) -> Dict:
    """One graphic made: {..., fichier} — or GraphiqueError saying why not."""
    code = p["targets"][0]["language"]
    rtl = code == "ar"
    facts = (p.get("reference") or {}).get("faits") or []
    kind, spec, k = item["type"], item["spec"], item["phrase"]
    name = f"g{k}_{kind}"
    if kind == "chiffre":
        html = fill("chiffre.html", chiffre_data(spec, rtl, item["mode"]))
    elif kind == "carte":
        data = carte_data(spec, facts, rtl, find)
        if not data:
            raise GraphiqueError(f"lieu introuvable sur la carte : {spec.get('lieu')}")
        html = fill("carte.html", data)
    else:
        html, fix = None, ""
        for _ in range(2):                  # once more when the page breaks a rule
            html = schema_html(spec, phrase_text(p, k, code), facts, code, gemini, fix)
            bad = outside(html)
            errors = [f"ressource exterieure interdite : {bad}"] if bad else lint(folder_for(work, name, kind, html))
            if not errors:
                break
            fix = "\nTA VERSION PRECEDENTE A CES ERREURS, corrige-les : " + " ; ".join(errors)[:800]
            html = None
        if not html:
            raise GraphiqueError("le schéma écrit ne passe pas le contrôle")
    folder = folder_for(work, name, kind, html)
    transparent = item["mode"] == "incrustation"
    out = render(folder, os.path.join(work, name + (".mov" if transparent else ".mp4")), transparent)
    return {**item, "fichier": out}


def shot_of(made: Dict, n_sentences: int, thumbs: str) -> Dict:
    """A full-screen graphic as a shot of the stock, kept for its sentence."""
    k = made["phrase"]
    sid = f"G{k}"
    os.makedirs(thumbs, exist_ok=True)
    thumb = os.path.join(thumbs, f"{sid}.jpg")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "4.5", "-i", made["fichier"], "-frames:v", "1",
                    "-vf", "scale=480:-2", thumb], capture_output=True)
    what = {"chiffre": "chiffre animé", "carte": "carte animée", "schema": "schéma animé"}[made["type"]]
    return {"id": sid, "source": "graphiques", "file": made["fichier"], "start": 0.0, "end": DURATION,
            "w": 1080, "h": 1920, "thumb": thumb, "graphique": made["type"], "pour": k,
            "desc": f"{what} : {str(made['spec'].get('contenu') or '')[:160]}", "montre": [], "force": 8,
            "pertinence": 10, "probleme": None, "x": 0.5, "garde": True, "ecarte": None,
            "colle": [1.0 if i == k - 1 else 0.0 for i in range(n_sentences)],
            "credit": "", "url": "", "titre_source": "Graphiques animés (faits par l'app)"}


def make_all(p: Dict, work: str, gemini=None, report: Optional[Report] = None, find=geocode) -> Dict:
    """Every graphic of a project, one after the other (beside the downloads). -> {shots, incrustation, liste,
    secours (a message when some could not be made)}."""
    report = report or (lambda phase, f: None)
    codes = [t["language"] for t in p.get("targets") or []]
    todo = plan(p.get("realisation"), (p.get("reference") or {}).get("faits") or [], codes)
    if not todo:
        return {"shots": [], "incrustation": None, "liste": [], "secours": None}
    if not available():
        return {"shots": [], "incrustation": None, "liste": [], "secours": "graphiques animés non faits : Node (npx) introuvable."}
    n = len(((p.get("storyboard") or {}).get("plans")) or [])
    shots, liste, failed, inc = [], [], [], None
    for i, item in enumerate(todo):
        report(f"graphiques animés ({i + 1}/{len(todo)})", i / len(todo))
        row = {"phrase": item["phrase"], "type": item["type"], "mode": item["mode"],
               "contenu": str(item["spec"].get("contenu") or "")[:200]}
        try:
            made = make_one(p, item, work, gemini, find)
        except Exception as e:              # a graphic missing: the sentence keeps its real pictures
            failed.append(f"phrase {item['phrase']} ({item['type']}) : {str(e)[:120]}")
            liste.append({**row, "erreur": str(e)[:200]})
            continue
        liste.append({**row, "fichier": made["fichier"]})
        if item["mode"] == "incrustation":
            inc = {"fichier": made["fichier"], "phrase": 1}
        else:
            shots.append(shot_of(made, n, os.path.join(work, "thumbs")))
    return {"shots": shots, "incrustation": inc, "liste": liste,
            "secours": ("graphiques animés non faits — " + " ; ".join(failed)) if failed else None}


def with_graphics(edl: List[Dict], shots: List[Dict]) -> List[Dict]:
    """The AI editor's montage with each kept graphic in place: its sentence shown by it alone (one piece from the
    sentence's first cut to its last)."""
    for s in shots:
        if not s.get("graphique") or not s.get("garde"):
            continue
        mine = [e for e in edl if e["phrase"] == s["pour"]]
        if not mine:
            continue
        first, i = mine[0], edl.index(mine[0])
        edl = edl[:i] + [{"phrase": s["pour"], "plan": s["id"], "debut": first["debut"], "fin": mine[-1]["fin"]}] + \
            [e for e in edl[i:] if e["phrase"] != s["pour"]]
    return edl
