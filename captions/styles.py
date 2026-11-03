"""The catalogue of caption styles. Each style: a name, its group, a description, its settings (core.Param), the spaces
that can use it, whether it works in Arabic, and a builder (words, ctx, settings) -> (style lines, events, extras).

extras (render.py burns them): "blend" ("softlight" | "difference"), "perspective" (degrees), "emojis"
[(char, start, end, x, y)], "sounds" [(file, at, volume)], "behind" (the big words' events, drawn under the person).
needs: "faces" (where the faces are, render.faces) or "mask" (the person's mask, render.person_mask).

The spaces' own styles (Génération, Montage auto) are delegated to their code, so they stay identical; the
Adaptation's five looks are shown in the gallery (they are chosen in Réglages → Voix, with the banner).
"""

import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from captions.core import (FPS, MS, ROOT, Ctx, Font, Param, Words, bare, common, esc, event, fit, groups, line_layout,
                           rgb, shown, tag_colour)

ALL = ("generation", "montage", "adaptation", "reprise", "discours")
SFX_DIR = os.path.join(ROOT, "assets", "sfx")


@dataclass
class Style:
    id: str
    label: str
    group: str
    description: str
    params: List[Param]
    build: Callable
    arabic: bool = True
    spaces: Tuple[str, ...] = ALL
    needs: Tuple[str, ...] = ()
    native: Optional[str] = None                 # the space whose own code draws it ("generation", "montage", "adaptation")
    number: Optional[int] = None                 # its number in the catalogue of 2026-11-03 (n°14-33)

    def clean(self, raw: Optional[Dict]) -> Dict:
        raw = raw or {}
        return {p.name: p.clean(raw.get(p.name)) for p in self.params}

    def public(self) -> Dict:
        return {"id": self.id, "label": self.label, "group": self.group, "description": self.description,
                "params": [p.public() for p in self.params], "arabic": self.arabic, "spaces": list(self.spaces),
                "needs": list(self.needs), "native": self.native, "number": self.number}


STYLES: Dict[str, Style] = {}


def style(id, label, group, description, params=None, **kw):
    def register(fn):
        STYLES[id] = Style(id, label, group, description, list(params if params is not None else common()), fn, **kw)
        return fn
    return register


# ---------------------------------------------------------------- shared pieces

def pop(k: float = 1.0, small: float = 80, big: float = 106) -> str:
    """A quick pop on 4 frames (small -> big -> 100 %), times the line's fit k."""
    return (f"\\fscx{small * k:.0f}\\fscy{small * k:.0f}\\t(0,{2 * MS:.0f},\\fscx{big * k:.0f}\\fscy{big * k:.0f})"
            f"\\t({2 * MS:.0f},{4 * MS:.0f},\\fscx{100 * k:.0f}\\fscy{100 * k:.0f})")


def size(p: Dict, base: float) -> float:
    return base * p.get("taille", 100) / 100


def colour(value, alpha: int = 255):
    return (*rgb(value), alpha)


def reveal(words: Words, ctx: Ctx, p: Dict, font: Font, name: str, tags=lambda w, now, k: "",
           n: Optional[int] = None, y: Optional[int] = None, scale_of=lambda w: 1.0, layer: int = 0) -> List[str]:
    """The base of most styles: groups of n words on one line, each shown when said (the hidden ones keep their place
    so the line never jumps), the whole line shrunk to fit the zone."""
    out = []
    y = y if y is not None else ctx.y(p.get("position", "bas"))
    for g, a, b in groups(words, n or p.get("mots", 3)):
        _, width = line_layout(font, g, ctx, p, scale_of, p.get("espacement", 0))
        k = fit(width, ctx.max_w(p.get("position", "bas")))
        base = f"\\fscx{100 * k:.0f}\\fscy{100 * k:.0f}" if k < 1 else ""
        for i, (_, s, _) in enumerate(g):
            e = g[i + 1][1] if i + 1 < len(g) else b
            parts = [f"{{\\alpha&H{'00' if j <= i else 'FF'}&{base}{tags(w, j == i, k)}}}{esc(shown(w, ctx, p))}"
                     for j, w in enumerate(g)]
            out.append(event(s, e, name, f"{{\\an5\\pos({ctx.cx},{y})}}" + " ".join(parts), layer))
    return out


def strong_or(w, ctx, yes: str, no: str = "") -> str:
    return yes if ctx.is_strong(w) else no


# ---------------------------------------------------------------- the lab's styles (montage_test/alex, v1-v4)

@style("pop", "Pop orange", "Discours", "Mots blancs qui popent quand ils sont dits, les mots forts en orange (labo v1/v2).",
       common(accent="#ff7a00", spacing=0))
def _pop(words, ctx, p):
    f = Font("xbold", size(p, 64), ctx.lang)
    acc = tag_colour(rgb(p["accent"]))
    tags = lambda w, now, k: strong_or(w, ctx, f"\\c{acc}") + (pop(k, 70, 110) if now else "")
    return [f.style("Pop", colour(p["couleur"]), border=2.5, spacing=p["espacement"])], reveal(words, ctx, p, f, "Pop", tags), {}


@style("pyramide", "Pyramide", "Discours", "1 à 3 mots par ligne empilés sous l'image, gris clair, les mots forts en blanc pur (labo v3).",
       common(position="sous", words=3, colour="#e0e0e0", accent="#ffffff", spacing=0))
def _pyramide(words, ctx, p):
    f = Font("semi", size(p, 62), ctx.lang)
    y0 = ctx.y(p["position"])
    lh = int(f.size * 1.25)
    shapes = {1: [1], 2: [2], 3: [1, 2], 4: [1, 3]}
    out = []
    key, base = tag_colour(rgb(p["accent"])), tag_colour(rgb(p["couleur"]))
    for g, a, b in groups(words, p["mots"]):
        rows, j = [], 0
        for n in shapes[len(g)]:
            rows.append(g[j:j + n])
            j += n
        for i, (_, s, _) in enumerate(g):
            e = g[i + 1][1] if i + 1 < len(g) else b
            j = 0
            for r, row in enumerate(rows):
                parts = []
                for w in row:
                    parts.append(f"{{\\c{key if ctx.is_strong(w) else base}\\alpha&H{'00' if j <= i else 'FF'}&"
                                 f"{pop(1.0, 70, 110) if j == i else ''}}}{esc(shown(w, ctx, p))}")
                    j += 1
                out.append(event(s, e, "Py", f"{{\\an5\\pos({ctx.cx},{y0 + r * lh})}}" + " ".join(parts)))
    return [f.style("Py", colour(p["couleur"]), border=0, shadow=2, spacing=p["espacement"])], out, {}


@style("escalier", "Escalier serif", "Discours", "Mots empilés (1 à 2 par ligne) sur l'image, pop rapide, les mots forts en serif italique plus grands (labo v4).",
       common(words=3, spacing=0) + [Param("grand", "Taille des mots forts (%)", "int", 125, 100, 180)])
def _escalier(words, ctx, p):
    f, s = Font("semi", size(p, 68), ctx.lang), Font("serif", size(p, 68), ctx.lang)
    y0, lh = ctx.y(p["position"]), int(size(p, 84))
    out = []
    for g, a, b in groups(words, p["mots"]):
        rows = [[w] for w in g] if len(g) <= 2 else [g[:1], g[1:]]
        for i, (_, st, _) in enumerate(g):
            e = g[i + 1][1] if i + 1 < len(g) else b
            j = 0
            for r, row in enumerate(rows):
                parts = []
                for w in row:
                    look = (f"\\fn{s.family}" + ("" if ctx.rtl else "\\i1") + f"\\fscx{p['grand']}\\fscy{p['grand']}"
                            f"\\c{tag_colour(rgb(p['accent']))}") if ctx.is_strong(w) else ""
                    parts.append(f"{{\\alpha&H{'00' if j <= i else 'FF'}&{look}{pop() if j == i else ''}}}{esc(shown(w, ctx, p))}")
                    j += 1
                yy = y0 + (r - (len(rows) - 1) / 2) * lh
                out.append(event(st, e, "Es", f"{{\\an5\\pos({ctx.cx},{yy:.0f})}}" + " ".join(parts)))
    return [f.style("Es", colour(p["couleur"]), (0, 0, 0, 170), border=1.2, shadow=2, spacing=p["espacement"])], out, {}


@style("editorial", "Éditorial", "Discours", "Tout en serif élégante, chaque mot apparaît en fondu, les mots forts en majuscules espacées (Chalamet chez @ofluminary).",
       common(words=3, colour="#f5eee1", accent="#f5eee1", spacing=0))
def _editorial(words, ctx, p):
    f = Font("serif", size(p, 90), ctx.lang)
    def tags(w, now, k):
        fade = f"\\alpha&HFF&\\t(0,{5 * MS:.0f},\\alpha&H00&)" if now else ""
        return fade + (f"\\fsp6\\c{tag_colour(rgb(p['accent']))}" if ctx.is_strong(w) else "")
    pc = dict(p, majuscules="mots_forts" if p["majuscules"] == "non" else p["majuscules"])
    return [f.style("Ed", colour(p["couleur"]), border=0, shadow=2, spacing=p["espacement"])], reveal(words, ctx, pc, f, "Ed", tags), {}


# ---------------------------------------------------------------- the catalogue's new styles (n°14-33)

@style("resserre", "Lettres resserrées", "Typographie", "Gras, lettres serrées (espacement -3) : l'aspect « pro » des Shorts viraux.",
       common(spacing=-3), number=14)
def _resserre(words, ctx, p):
    f = Font("xbold", size(p, 70), ctx.lang)
    tags = lambda w, now, k: pop(k) if now else ""
    return [f.style("Re", colour(p["couleur"]), border=1.5, spacing=p["espacement"])], reveal(words, ctx, p, f, "Re", tags), {}


@style("hierarchie", "Hiérarchie de taille", "Typographie", "Les mots secondaires petits, les mots forts très grands.",
       common() + [Param("grand", "Taille des mots forts (%)", "int", 150, 110, 200),
                   Param("petit", "Taille des autres mots (%)", "int", 80, 50, 100)], number=15)
def _hierarchie(words, ctx, p):
    f = Font("xbold", size(p, 64), ctx.lang)
    scale_of = lambda w: (p["grand"] if ctx.is_strong(w) else p["petit"]) / 100
    tags = lambda w, now, k: f"\\fscx{100 * k * scale_of(w):.0f}\\fscy{100 * k * scale_of(w):.0f}"
    return ([f.style("Hi", colour(p["couleur"]), border=1.5, spacing=p["espacement"])],
            reveal(words, ctx, p, f, "Hi", tags, scale_of=scale_of), {})


def _difference_events(words, ctx, p, small, big):
    out = []
    y = ctx.y(p["position"]) - 30
    for g, a, b in groups(words, max(2, p["mots"] + 1)):
        strong = [w for w in g if ctx.is_strong(w)]
        key = strong[-1] if strong else max(g, key=lambda w: len(bare(w[0])))
        ctx_words = [w for w in g if w is not key]
        k = fit(big.width(shown(key, ctx, p).strip(".,،"), spacing=-6), ctx.max_w(p["position"]))
        if ctx_words:
            out.append(event(ctx_words[0][1], b, "D1", f"{{\\an2\\pos({ctx.cx},{y})}}" + " ".join(esc(shown(w, ctx, p)) for w in ctx_words)))
        out.append(event(key[1], b, "D2", f"{{\\an8\\pos({ctx.cx},{y})\\fscx{100 * k:.0f}\\fscy{100 * k:.0f}}}"
                                          f"{esc(shown(key, ctx, p).strip('.,،'))}"))
    return out


@style("difference", "Difference", "Typographie", "2 lignes : le contexte petit en haut, le mot fort énorme et gras dessous (Ben Kaluza).",
       common(words=3), number=16)
def _difference(words, ctx, p):
    small, big = Font("semi", size(p, 46), ctx.lang), Font("black", size(p, 150), ctx.lang)
    return ([small.style("D1", colour(p["couleur"]), spacing=-1), big.style("D2", colour(p["couleur"]), spacing=-6)],
            _difference_events(words, ctx, p, small, big), {})


@style("double_police", "Double police", "Typographie", "Gras pour la phrase, serif italique (Tajawal Black en arabe) plus grande pour les mots forts.",
       common(spacing=-2) + [Param("grand", "Taille des mots forts (%)", "int", 140, 100, 180)], number=17)
def _double_police(words, ctx, p):
    f, s = Font("xbold", size(p, 66), ctx.lang), Font("serif", size(p, 66), ctx.lang)
    scale_of = lambda w: p["grand"] / 100 if ctx.is_strong(w) else 1.0
    def tags(w, now, k):
        look = ""
        if ctx.is_strong(w):
            look = f"\\fn{s.family}" + ("" if ctx.rtl else "\\i1") + f"\\fscx{p['grand'] * k:.0f}\\fscy{p['grand'] * k:.0f}" \
                   f"\\c{tag_colour(rgb(p['accent']))}"
        return look + (pop(k * scale_of(w)) if now else "")
    return ([f.style("Dp", colour(p["couleur"]), border=1.2, shadow=2, spacing=p["espacement"])],
            reveal(words, ctx, p, f, "Dp", tags, scale_of=scale_of), {})


@style("neon", "Néon qui grésille", "Animations", "Les mots forts s'allument comme un tube néon qui grésille (3 clignotements), avec une lueur.",
       common(accent="#00e5ff") + [Param("clignotements", "Clignotements", "int", 3, 1, 6)], number=18)
def _neon(words, ctx, p):
    f = Font("semi", size(p, 68), ctx.lang)
    glow = rgb(p["accent"])
    light = tuple(min(255, int(c + (255 - c) * 0.7)) for c in glow)
    def tags(w, now, k):
        if not ctx.is_strong(w):
            return ""
        look = f"\\c{tag_colour(light)}\\3c{tag_colour(glow)}\\bord3\\blur6"
        if now:
            look += "".join(f"\\t({int(j * MS)},{int(j * MS) + 1},\\alpha&H{'FF' if j % 2 else '00'}&)"
                            for j in range(1, 2 * p["clignotements"] + 1))
        return look
    return [f.style("Ne", colour(p["couleur"]), border=0, shadow=0, spacing=p["espacement"])], reveal(words, ctx, p, f, "Ne", tags), {}


@style("slide_up", "Slide up", "Animations", "Une ligne : chaque mot glisse vers le haut à sa place, l'un après l'autre.",
       common(words=4), number=19)
def _slide_up(words, ctx, p):
    f = Font("xbold", size(p, 62), ctx.lang)
    out = []
    y = ctx.y(p["position"])
    acc = tag_colour(rgb(p["accent"]))
    for g, a, b in groups(words, p["mots"]):
        lay, width = line_layout(f, g, ctx, p, spacing=p["espacement"])
        k = fit(width, ctx.max_w(p["position"]))
        top, bottom = y - int(f.size * 0.75), y + int(f.size * 0.7)
        for w, x, wd in lay:
            x = ctx.cx + (x - ctx.cx) * k
            col = f"\\c{acc}" if ctx.is_strong(w) else ""
            out.append(event(w[1], b, "Su", f"{{\\an5\\move({x:.0f},{y + 70},{x:.0f},{y},0,{int(9 * MS)})"
                                            f"\\clip(0,{top},{ctx.size[0]},{bottom})\\fscx{100 * k:.0f}\\fscy{100 * k:.0f}{col}}}"
                                            f"{esc(shown(w, ctx, p))}"))
    return [f.style("Su", colour(p["couleur"]), border=0, shadow=2, spacing=p["espacement"])], out, {}


@style("rebond", "Rebond Apple", "Animations", "1 à 2 mots au milieu qui montent vite, redescendent, remontent un peu et se posent (rebond amorti).",
       common(words=2, position="milieu"), number=20)
def _rebond(words, ctx, p):
    f = Font("semi", size(p, 84), ctx.lang)
    y = ctx.y(p["position"])
    out = []
    t1, t2, t3 = 4 * MS / 1000, 9 * MS / 1000, 13 * MS / 1000
    for g, a, b in groups(words, p["mots"]):
        _, width = line_layout(f, g, ctx, p, spacing=p["espacement"])
        k = fit(width, ctx.max_w(p["position"]))
        sc = f"\\fscx{100 * k:.0f}\\fscy{100 * k:.0f}"
        text = " ".join(esc(shown(w, ctx, p)) for w in g)
        steps = [(a, a + t1, y + 70, y - 14), (a + t1, a + t2, y - 14, y + 5), (a + t2, a + t3, y + 5, y)]
        for s, e, y0, y1 in steps:           # libass keeps one \move per line: one short line per step
            out.append(event(s, min(e, b), "Rb", f"{{\\an5\\move({ctx.cx},{y0},{ctx.cx},{y1}){sc}}}{text}"))
        if b > a + t3:
            out.append(event(a + t3, b, "Rb", f"{{\\an5\\pos({ctx.cx},{y}){sc}}}{text}"))
    return [f.style("Rb", colour(p["couleur"]), border=0, shadow=1.5, spacing=p["espacement"])], out, {}


@style("degrade", "Dégradé", "Luxe", "Serif (Tajawal en arabe), le texte passe d'une couleur en haut à une autre en bas.",
       common(spacing=-1) + [Param("haut", "Couleur du haut", "colour", "#ffffff"),
                             Param("bas", "Couleur du bas", "colour", "#8c8c8c")], number=21)
def _degrade(words, ctx, p):
    f = Font("serif", size(p, 104), ctx.lang)
    y = ctx.y(p["position"])
    top_c, bot_c = rgb(p["haut"]), rgb(p["bas"])
    h = f.size * 1.1
    top = y - h * 0.55
    out = []
    bands = 8
    for g, a, b in groups(words, p["mots"]):
        _, width = line_layout(f, g, ctx, p, spacing=p["espacement"])
        k = fit(width, ctx.max_w(p["position"]))
        text = " ".join(esc(shown(w, ctx, p)) for w in g)
        for j in range(bands):
            y0, y1 = top + j * h / bands, top + (j + 1) * h / bands + 1
            c = tuple(int(top_c[i] + (bot_c[i] - top_c[i]) * j / (bands - 1)) for i in range(3))
            out.append(event(a, b, "Dg", f"{{\\an5\\pos({ctx.cx},{y})\\clip(0,{y0:.0f},{ctx.size[0]},{y1:.0f})\\c{tag_colour(c)}"
                                         f"{pop(k)}}}{text}", j))
    return [f.style("Dg", colour(p["haut"]), border=0, shadow=0, spacing=p["espacement"])], out, {}


@style("biseau", "Biseau premium", "Luxe", "Très gras, couleur pleine, une ombre claire d'un pixel qui fait un biseau, un halo doux derrière.",
       common(words=2, colour="#7c3aed", spacing=-3, upper="oui") + [Param("biseau", "Couleur du biseau", "colour", "#ffffff"),
                                                                    Param("halo", "Halo", "bool", True)], number=22)
def _biseau(words, ctx, p):
    f = Font("black", size(p, 78), ctx.lang)
    y = ctx.y(p["position"])
    out = []
    for g, a, b in groups(words, p["mots"]):
        text = " ".join(esc(shown(w, ctx, p)) for w in g)
        _, width = line_layout(f, g, ctx, p, spacing=p["espacement"])
        k = fit(width, ctx.max_w(p["position"]))
        if p["halo"]:
            hw = width * k * 0.38
            out.append(event(a, b, "Ha", f"{{\\an5\\pos({ctx.cx},{y})\\p1\\blur28\\alpha&HB0&\\c&HFFFFFF&}}"
                                         f"m {-hw:.0f} -40 l {hw:.0f} -40 l {hw:.0f} 40 l {-hw:.0f} 40{{\\p0}}", 0))
        out.append(event(a, b, "Bi", f"{{\\an5\\pos({ctx.cx},{y}){pop(k)}}}{text}", 1))
    bevel = f.style("Bi", colour(p["couleur"]), colour(p["biseau"]), border=0, shadow=1.4, spacing=p["espacement"],
                    back=colour(p["biseau"]))
    return [bevel, f.style("Ha")], out, {}


@style("surligneur", "Surligneur animé", "Animations", "Un rectangle (plein ou en contour) se dessine de gauche à droite derrière chaque mot fort.",
       common(accent="#ff3b30") + [Param("contour", "Contour seulement", "bool", False)], number=23)
def _surligneur(words, ctx, p):
    f = Font("xbold", size(p, 66), ctx.lang)
    y = ctx.y(p["position"])
    out = reveal(words, ctx, p, f, "Su", lambda w, now, k: "", layer=1)
    acc = rgb(p["accent"])
    for g, a, b in groups(words, p["mots"]):
        lay, width = line_layout(f, g, ctx, p, spacing=p["espacement"])
        k = fit(width, ctx.max_w(p["position"]))
        for w, x, wd in lay:
            if not ctx.is_strong(w):
                continue
            x, wd = ctx.cx + (x - ctx.cx) * k, wd * k
            x0, x1, y0, y1 = x - wd / 2 - 14, x + wd / 2 + 14, y - f.size * 0.68 * k, y + f.size * 0.7 * k
            box = f"m {x0:.0f} {y0:.0f} l {x1:.0f} {y0:.0f} l {x1:.0f} {y1:.0f} l {x0:.0f} {y1:.0f}"
            look = f"\\1a&HFF&\\bord5\\3c{tag_colour(acc)}" if p["contour"] else ""
            # right to left: the marker runs from the word's right edge
            c0 = f"\\clip({x1 + 6:.0f},{y0 - 6:.0f},{x1 + 6:.0f},{y1 + 6:.0f})" if ctx.rtl else f"\\clip({x0 - 6:.0f},{y0 - 6:.0f},{x0 - 6:.0f},{y1 + 6:.0f})"
            out.append(event(w[1], b, "Box", f"{{\\an7\\pos(0,0)\\p1{look}{c0}"
                                             f"\\t(0,{int(8 * MS)},\\clip({x0 - 6:.0f},{y0 - 6:.0f},{x1 + 6:.0f},{y1 + 6:.0f}))}}{box}{{\\p0}}", 0))
    return [f.style("Su", colour(p["couleur"]), border=0, shadow=0, spacing=p["espacement"]),
            f.style("Box", (*acc, 235), border=0, shadow=0)], out, {}


@style("reflet", "Reflet lumineux", "Luxe", "Les mots forts en couleur ; une bande de lumière blanche les balaie quand ils sont dits.",
       common(accent="#00c8ff") + [Param("bande", "Couleur du reflet", "colour", "#ffffff")], number=24)
def _reflet(words, ctx, p):
    f = Font("black", size(p, 72), ctx.lang)
    y = ctx.y(p["position"])
    acc = tag_colour(rgb(p["accent"]))
    out = reveal(words, ctx, p, f, "Rf", lambda w, now, k: strong_or(w, ctx, f"\\c{acc}"))
    for g, a, b in groups(words, p["mots"]):
        lay, width = line_layout(f, g, ctx, p, spacing=p["espacement"])
        k = fit(width, ctx.max_w(p["position"]))
        for w, x, wd in lay:
            if not ctx.is_strong(w):
                continue
            x, wd = ctx.cx + (x - ctx.cx) * k, wd * k
            x0, x1 = x - wd / 2 - 40, x + wd / 2 + 40
            start, end = (x1 - 34, x1) if ctx.rtl else (x0, x0 + 34)
            stop = (x0, x0 + 34) if ctx.rtl else (x1 - 34, x1)
            text = " ".join(f"{{\\alpha&H{'00' if v is w else 'FF'}&}}{esc(shown(v, ctx, p))}" for v in g)
            sc = f"\\fscx{100 * k:.0f}\\fscy{100 * k:.0f}" if k < 1 else ""
            out.append(event(w[1] + 0.05, w[1] + 0.6, "Rf", f"{{\\an5\\pos({ctx.cx},{y}){sc}\\c{tag_colour(rgb(p['bande']))}\\blur2"
                                                             f"\\clip({start:.0f},0,{end:.0f},{ctx.size[1]})"
                                                             f"\\t(0,{int(14 * MS)},\\clip({stop[0]:.0f},0,{stop[1]:.0f},{ctx.size[1]}))}}{text}", 1))
    return [f.style("Rf", colour(p["couleur"]), border=0, shadow=1, spacing=p["espacement"])], out, {}


@style("flou_net", "Flou → net", "Animations", "Chaque mot apparaît flou et transparent, puis devient net.", common(), number=25)
def _flou_net(words, ctx, p):
    f = Font("xbold", size(p, 68), ctx.lang)
    tags = lambda w, now, k: f"\\blur12\\alpha&H80&\\t(0,{int(7 * MS)},\\blur0\\alpha&H00&)" if now else ""
    return [f.style("Fl", colour(p["couleur"]), border=1, shadow=2, spacing=p["espacement"])], reveal(words, ctx, p, f, "Fl", tags), {}


@style("emojis", "Emojis", "Animations", "Un emoji au-dessus de chaque mot fort qui en a un (dictionnaire français, anglais, arabe).",
       common(), number=26)
def _emojis(words, ctx, p):
    from captions.emojis import emoji_of
    f = Font("xbold", size(p, 66), ctx.lang)
    out = reveal(words, ctx, p, f, "Em", lambda w, now, k: pop(k) if now else "")
    y = ctx.y(p["position"])
    marks = []
    for g, a, b in groups(words, p["mots"]):
        lay, width = line_layout(f, g, ctx, p, spacing=p["espacement"])
        k = fit(width, ctx.max_w(p["position"]))
        for w, x, wd in lay:
            ch = emoji_of(w[0]) if ctx.is_strong(w) or len(ctx.strong) == 0 else None
            if ch:
                marks.append((ch, w[1], b, ctx.cx + (x - ctx.cx) * k, y - f.size * 1.6))
    return [f.style("Em", colour(p["couleur"]), border=1.5, shadow=2, spacing=p["espacement"])], out, {"emojis": marks}


@style("signature", "Signature de chaîne", "Identité", "Un trait fin à la couleur de la chaîne se dessine sous chaque mot fort : on reconnaît nos vidéos.",
       common(accent="#000000") + [Param("chaine", "Trait à la couleur de la chaîne", "bool", True),
                                   Param("epaisseur", "Épaisseur du trait", "int", 8, 3, 16)], number=27)
def _signature(words, ctx, p):
    f = Font("xbold", size(p, 66), ctx.lang)
    y = ctx.y(p["position"])
    out = reveal(words, ctx, p, f, "Sg", lambda w, now, k: pop(k) if now else "")
    bar_c = rgb(ctx.colour) if p["chaine"] else rgb(p["accent"])
    for g, a, b in groups(words, p["mots"]):
        lay, width = line_layout(f, g, ctx, p, spacing=p["espacement"])
        k = fit(width, ctx.max_w(p["position"]))
        for w, x, wd in lay:
            if not ctx.is_strong(w):
                continue
            x, wd = ctx.cx + (x - ctx.cx) * k, wd * k
            x0, x1 = x - wd / 2, x + wd / 2
            y0 = y + f.size * 0.62 * k
            bar = f"m {x0:.0f} {y0:.0f} l {x1:.0f} {y0:.0f} l {x1:.0f} {y0 + p['epaisseur']:.0f} l {x0:.0f} {y0 + p['epaisseur']:.0f}"
            c0 = f"\\clip({x1:.0f},0,{x1:.0f},{ctx.size[1]})" if ctx.rtl else f"\\clip({x0:.0f},0,{x0:.0f},{ctx.size[1]})"
            out.append(event(w[1], b, "Bar", f"{{\\an7\\pos(0,0)\\p1{c0}\\t(0,{int(7 * MS)},\\clip({x0:.0f},0,{x1:.0f},{ctx.size[1]}))}}"
                                             f"{bar}{{\\p0}}", 0))
    return [f.style("Sg", colour(p["couleur"]), border=1.2, shadow=2, spacing=p["espacement"]),
            f.style("Bar", (*bar_c, 255), border=0, shadow=0)], out, {}


def _sounds():
    try:
        return sorted(x for x in os.listdir(SFX_DIR) if x.endswith(".mp3"))
    except OSError:
        return ["click_ui_click.mp3"]


@style("clic", "Clic sonore sur le mot fort", "Son", "La hiérarchie de taille, plus un seul son discret pile sur le mot le plus fort.",
       common() + [Param("grand", "Taille des mots forts (%)", "int", 150, 110, 200),
                   Param("petit", "Taille des autres mots (%)", "int", 80, 50, 100),
                   Param("son", "Son", "choice", "click_ui_click.mp3", choices=[(s, s.rsplit(".", 1)[0]) for s in _sounds()]),
                   Param("volume", "Volume du son (%)", "int", 60, 10, 100)], number=28)
def _clic(words, ctx, p):
    styles_, events_, _ = _hierarchie(words, ctx, p)
    key = ctx.impact or next((bare(w[0]) for w in reversed(words) if ctx.is_strong(w)), None)
    at = next((w[1] for w in words if bare(w[0]) == key), None)
    sounds = [(os.path.join(SFX_DIR, p["son"]), at, p["volume"] / 100)] if at is not None else []
    return styles_, events_, {"sounds": sounds}


@style("evite_visage", "Évite le visage", "Placement", "Chaque groupe de mots va dans la bande (bas, haut, milieu) qui ne touche pas le visage pendant qu'il est affiché.",
       common(), needs=("faces",), spaces=("generation", "montage", "adaptation", "discours"), number=29)
def _evite_visage(words, ctx, p):
    f = Font("xbold", size(p, 70), ctx.lang)
    out = []
    order = ["bas", "haut", "milieu"]
    for g, a, b in groups(words, p["mots"]):
        seen = [box for t, box in ctx.faces if a - 0.2 <= t <= b + 0.2]
        def hits(y):
            return sum(1 for x0, y0, x1, y1 in seen if y0 - 60 < y + 60 and y1 + 30 > y - 60)
        band = min(order, key=lambda k: (hits(ctx.y(k)), order.index(k)))
        out += reveal(g, ctx, dict(p, position=band), f, "Vi", lambda w, now, k: pop(k) if now else "", n=len(g), y=ctx.y(band))
    return [f.style("Vi", colour(p["couleur"]), border=1.5, shadow=3, spacing=p["espacement"])], out, {}


@style("soft_light", "Fusion Soft light", "Fusion", "Le texte se fond dans les teintes de l'image (beau sur les plans clairs, discret sur les sombres).",
       common(words=2, spacing=-4), number=30)
def _soft_light(words, ctx, p):
    f = Font("black", size(p, 96), ctx.lang)
    return ([f.style("Sl", colour(p["couleur"]), spacing=p["espacement"])],
            reveal(words, ctx, p, f, "Sl", lambda w, now, k: pop(k) if now else ""), {"blend": "softlight"})


@style("fusion_difference", "Fusion Différence", "Fusion", "La mise en page « Difference », le texte inverse les couleurs de l'image derrière lui.",
       common(words=3), number=31)
def _fusion_difference(words, ctx, p):
    small, big = Font("semi", size(p, 46), ctx.lang), Font("black", size(p, 150), ctx.lang)
    return ([small.style("D1", colour(p["couleur"]), spacing=-1), big.style("D2", colour(p["couleur"]), spacing=-6)],
            _difference_events(words, ctx, p, small, big), {"blend": "difference"})


@style("perspective", "Perspective 3D", "Fusion", "Mots empilés (les forts plus grands), le bloc incliné en perspective.",
       common(spacing=-4) + [Param("angle", "Inclinaison", "int", 12, 4, 30)], number=32)
def _perspective(words, ctx, p):
    f = Font("black", size(p, 76), ctx.lang)
    y0 = ctx.y(p["position"]) - int(f.size * 1.2)
    out = []
    for g, a, b in groups(words, p["mots"]):
        for i, (_, s, _) in enumerate(g):
            e = g[i + 1][1] if i + 1 < len(g) else b
            for j, w in enumerate(g[:i + 1]):
                big = 135 if ctx.is_strong(w) else 100
                k = fit(f.width(shown(w, ctx, p)) * big / 100, ctx.max_w(p["position"]))
                sc = big * k
                zoom = f"\\fscx{60 * k:.0f}\\fscy{60 * k:.0f}\\t(0,{int(9 * MS)},\\fscx{sc:.0f}\\fscy{sc:.0f})" if j == i \
                    else f"\\fscx{sc:.0f}\\fscy{sc:.0f}"
                out.append(event(s, e, "Pe", f"{{\\an5\\pos({ctx.cx},{y0 + j * int(f.size * 1.25)}){zoom}}}{esc(shown(w, ctx, p))}"))
    return [f.style("Pe", colour(p["couleur"]), spacing=p["espacement"])], out, {"perspective": p["angle"]}


@style("derriere", "Texte derrière la personne", "Profondeur", "Un grand mot (les mots forts) posé derrière la personne, sa silhouette passe devant (SAM 2.1, carte graphique).",
       common() + [Param("hauteur", "Hauteur du grand mot (% de l'image)", "int", 30, 10, 60)],
       needs=("mask",), spaces=("discours",), number=33)
def _derriere(words, ctx, p):
    big, small = Font("black", size(p, 300), ctx.lang), Font("xbold", size(p, 58), ctx.lang)
    x, y, w, h = ctx.zone
    yy = int(y + h * p["hauteur"] / 100)
    strong = [wd for wd in words if ctx.is_strong(wd)] or [max(words, key=lambda wd: len(bare(wd[0])))]
    behind = []
    for i, wd in enumerate(strong):
        e = strong[i + 1][1] if i + 1 < len(strong) else words[-1][2] + 0.5
        word = bare(wd[0]) if ctx.rtl else bare(wd[0]).upper()
        k = fit(big.width(word, spacing=-8), w - 70)
        behind.append(event(wd[1], e, "Big", f"{{\\an5\\pos({ctx.cx},{yy})\\clip({x},{y},{x + w},{y + h})"
                                             f"\\fscx{70 * k:.0f}\\fscy{70 * k:.0f}\\t(0,{int(5 * MS)},\\fscx{100 * k:.0f}\\fscy{100 * k:.0f})}}"
                                             f"{esc(word)}"))
    front = [event(a, b, "Sm", f"{{\\an5\\pos({ctx.cx},{ctx.y(p['position'])})}}" + " ".join(esc(shown(wd, ctx, p)) for wd in g), 2)
             for g, a, b in groups(words, p["mots"])]
    return ([big.style("Big", colour(p["couleur"], 235), spacing=-8), small.style("Sm", colour(p["couleur"]), border=1.5, shadow=3)],
            front, {"behind": behind})


# ---------------------------------------------------------------- the spaces' own styles (delegated: identical)

def _generation(name, accent):
    def build(words, ctx, p):
        from generative import ffmpeg_composer
        text = ffmpeg_composer.build_ass([tuple(w) for w in words], ctx.size, name, p.get("accent") if accent else None)
        return None, text, {}
    return build


for _id, _label, _desc, _accent, _arabic in [
        ("karaoke", "Karaoké", "Une ligne, le mot dit en couleur.", True, True),
        ("mrbeast", "MrBeast", "Ligne entière en majuscules, police très grasse.", False, True),
        ("hormozi", "Hormozi", "2-3 mots en majuscules sur un bloc de couleur arrondi.", False, True),
        ("bounce", "Spring / Bounce", "Un mot à la fois qui rebondit (40 % → 110 % → 100 %).", True, True),
        ("typewriter", "Typewriter", "La phrase se construit, les lettres du mot tapées une à une (police mono).", True, False),
        ("minimal", "Minimaliste / Cinéma", "Sobre et discret, façon sous-titre de film.", False, False)]:
    STYLES[_id] = Style(_id, _label, "Génération (existants)", _desc,
                        [Param("accent", "Couleur d'accent", "colour", "#ffd60a")] if _accent else [],
                        _generation(_id, _accent), arabic=_arabic, native="generation")


def _montage(accent):
    def build(words, ctx, p):
        import tempfile
        from montage import recipes, render as mr
        keys = [i for i, w in enumerate(words) if ctx.is_strong(w)] if accent else []
        edit = mr.Edit(keep=[(0.0, words[-1][2] + 1.0)], noir=None, drones=None, chute=None)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "c.ass")
            mr.captions_ass([tuple(w) for w in words], edit, path, recipes.RECIPES["hopecore"], keywords=keys)
            return None, open(path, encoding="utf-8").read(), {}
    return build


STYLES["cascade"] = Style("cascade", "Cascade", "Montage auto (existants)",
                          "Chaque mot sur sa ligne, en zigzag ; le bloc se vide en fin de phrase.", [], _montage(False),
                          arabic=False, native="montage")
STYLES["accent"] = Style("accent", "Accent", "Montage auto (existants)",
                         "La cascade, les mots-clés en serif italique jaune avec une lueur.", [], _montage(True),
                         arabic=False, native="montage")


def _adaptation(look):
    def build(words, ctx, p):
        import tempfile
        from adaptation import langs, render as ar
        ws = [{"w": w[0], "start": w[1], "end": w[2]} for w in words]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "c.ass")
            ar.captions_ass([{"words": list(range(len(ws))), "mots_cles": sorted(ctx.strong)}], ws,
                            [{"va": 0.0, "vb": 9999.0, "out": 0.0}], path, langs.lang(ctx.lang), ar.STYLES[look])
            return None, open(path, encoding="utf-8").read(), {}
    return build


for _look, _label in [("classique", "Classique"), ("flamme", "Flamme"), ("neon", "Néon"), ("or", "Or"), ("clair", "Clair")]:
    STYLES[f"adaptation_{_look}"] = Style(f"adaptation_{_look}", f"Adaptation · {_label}", "Adaptation (existants)",
                                          "Le style visuel de l'Adaptation (bandeau + sous-titres), choisi dans Réglages → Voix.",
                                          [], _adaptation(_look), spaces=(), native="adaptation")


def get(style_id: Optional[str]) -> Optional[Style]:
    return STYLES.get(style_id or "")


def for_space(space: str, lang: Optional[str] = None) -> List[Style]:
    """The styles a space can use (in Arabic, only those that work in Arabic)."""
    from captions.core import rtl
    return [s for s in STYLES.values() if space in s.spaces and (s.arabic or not rtl(lang))]
