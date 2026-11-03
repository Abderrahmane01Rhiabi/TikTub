"""The catalogue of caption styles. Each style: a name, its group, a description, its settings (core.Param), the spaces
that can use it, whether it works in Arabic, and a builder (words, ctx, settings) -> (style lines, events, extras).

extras (render.py burns them): "blend" ("softlight" | "difference"), "perspective" (degrees), "emojis"
[(char, start, end, x, y)], "sounds" [(file, at, volume)], "behind" (the big words' events, drawn under the person).
needs: "faces" (where the faces are, render.faces) or "mask" (the person's mask, render.person_mask).

Every new style shares the same settings (core.common): its fonts, outline, shadow, a box behind the text, the
animation's speed, and where it goes — « Auto » by default: each group of words in the band that touches no face and
the fewest details, staying where it is unless that band turns bad (Placer); « Lisibilité auto » thickens the outline
over a bright picture.

The spaces' own styles (Génération, Montage auto) are delegated to their code, so they stay identical; the
Adaptation's five looks are shown in the gallery (they are chosen in Réglages → Voix, with the banner).
"""

import contextvars
import os
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from captions.core import (MS, ROOT, Ctx, Font, Param, Words, bare, common, esc, event, fit, groups, line_layout,
                           rgb, shown, tag_colour)

ALL = ("generation", "montage", "adaptation", "reprise", "discours")
SFX_DIR = os.path.join(ROOT, "assets", "sfx")
SPEED = contextvars.ContextVar("caption_speed", default=1.0)       # set by render.build from « Animation »
SPEED_OF = {"normale": 1.0, "rapide": 0.7, "lente": 1.6, "aucune": 0.0}


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


# ---------------------------------------------------------------- timing, sizes, looks

def ms(frames: float) -> int:
    """frames of 30 i/s in ms, at the « Animation » speed (0 when there is no animation)."""
    return int(frames * MS * SPEED.get())


def pop(k: float = 1.0, small: float = 80, big: float = 106) -> str:
    """A quick pop (small -> big -> 100 %), times the line's fit k; none without animation."""
    if not SPEED.get():
        return f"\\fscx{100 * k:.0f}\\fscy{100 * k:.0f}"
    return (f"\\fscx{small * k:.0f}\\fscy{small * k:.0f}\\t(0,{ms(2)},\\fscx{big * k:.0f}\\fscy{big * k:.0f})"
            f"\\t({ms(2)},{ms(4)},\\fscx{100 * k:.0f}\\fscy{100 * k:.0f})")


def size(p: Dict, base: float) -> float:
    return base * p.get("taille", 100) / 100


def colour(value, alpha: int = 255):
    return (*rgb(value), alpha)


def main_font(p: Dict, ctx: Ctx, base: float, key: Optional[str] = None) -> Font:
    return Font(key or p.get("police", "xbold"), size(p, base), ctx.lang)


def accent_font(p: Dict, ctx: Ctx, base: float) -> Font:
    return Font(p.get("police_forts", "serif"), size(p, base), ctx.lang)


def line_style(f: Font, name: str, p: Dict, text=None, **kw) -> str:
    """A style line with the common settings: text colour, outline, shadow, letter spacing."""
    kw.setdefault("border", p.get("contour", 0))
    kw.setdefault("shadow", p.get("ombre", 0))
    kw.setdefault("spacing", p.get("espacement", 0))
    kw.setdefault("outline", colour(p.get("contour_couleur", "#000000")))
    kw.setdefault("back", colour(p.get("ombre_couleur", "#000000"), 180))
    return f.style(name, colour(text or p.get("couleur", "#ffffff")), **kw)


def rrect(x0: float, y0: float, x1: float, y1: float, r: float) -> str:
    """ASS drawing of a rounded rectangle, absolute coordinates."""
    r = max(0.0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    k = r * 0.4477
    return (f"m {x0 + r:.0f} {y0:.0f} l {x1 - r:.0f} {y0:.0f} b {x1 - k:.0f} {y0:.0f} {x1:.0f} {y0 + k:.0f} {x1:.0f} {y0 + r:.0f} "
            f"l {x1:.0f} {y1 - r:.0f} b {x1:.0f} {y1 - k:.0f} {x1 - k:.0f} {y1:.0f} {x1 - r:.0f} {y1:.0f} "
            f"l {x0 + r:.0f} {y1:.0f} b {x0 + k:.0f} {y1:.0f} {x0:.0f} {y1 - k:.0f} {x0:.0f} {y1 - r:.0f} "
            f"l {x0:.0f} {y0 + r:.0f} b {x0:.0f} {y0 + k:.0f} {x0 + k:.0f} {y0:.0f} {x0 + r:.0f} {y0:.0f}")


class Placer:
    """Where each group of words goes. A fixed position: there, moved by « Décalage ». « Auto »: the band (bas, haut,
    milieu, sous l'image when there is room) that touches no face (« Éviter les visages ») and the fewest details of
    the picture, the preferred band first; a group keeps the band of the one before unless it turns clearly worse,
    so the text does not jump around. With ctx.anchor_y (the Reprise: where his captions were) « Auto » goes there."""

    MARGIN = 0.3

    def __init__(self, ctx: Ctx, p: Dict):
        self.ctx, self.p, self.last = ctx, p, None

    def _base(self, band: str) -> int:
        return self.ctx.anchor_y if band == "anchor" else self.ctx.y(band)

    def _score(self, band: str, a: float, b: float, pref: str) -> float:
        y = self._base(band)
        s = 0.0 if band == pref else 0.35 + (0.15 if band == "milieu" else 0.0)
        if self.p.get("eviter_visages", True):
            seen = [box for t, box in self.ctx.faces if a - 0.2 <= t <= b + 0.2]
            if seen:
                touching = sum(1 for x0, y0, x1, y1 in seen if y0 - 40 < y + 60 and y1 + 20 > y - 60)
                s += 3.0 * touching / len(seen)
        if band != "sous" and self.ctx.scene:
            st = self.ctx.scene.band(a, b, y)
            if st:
                s += st[0]
        return s

    def band(self, a: float, b: float) -> str:
        pos = self.p.get("position", "bas")
        if pos != "auto":
            return pos
        if self.ctx.anchor_y is not None:
            return "anchor"
        cands = ["bas", "haut", "milieu"] + (["sous"] if self.ctx.room_below else [])
        pref = self.p.get("preferee", "bas")
        pref = pref if pref in cands else "bas"
        scores = {c: self._score(c, a, b, pref) for c in cands}
        best = min(cands, key=lambda c: scores[c])
        if self.last in scores and scores[self.last] <= scores[best] + self.MARGIN:
            best = self.last
        self.last = best
        return best

    def y(self, a: float, b: float) -> Tuple[int, str]:
        band = self.band(a, b)
        return int(self._base(band) + self.p.get("decalage", 0) * self.ctx.zone[3] / 100), band

    def max_w(self, band: str) -> float:
        return self.ctx.max_w("bas" if band == "anchor" else band)

    def light(self, a: float, b: float, y: float) -> Tuple[str, bool]:
        """« Lisibilité auto »: over a bright picture, a thicker outline and shadow -> (tags, a soft box needed)."""
        if not self.p.get("lisibilite", True) or not self.ctx.scene:
            return "", False
        st = self.ctx.scene.band(a, b, y, half=55, width=0.7)
        if not st or st[1] < 140:
            return "", False
        border = max(self.p.get("contour", 0), 3)
        return (f"\\bord{border}\\3c{tag_colour(rgb(self.p.get('contour_couleur', '#000000')))}"
                f"\\shad{max(self.p.get('ombre', 0), 2)}"), st[1] > 195


def box_events(a: float, b: float, cx: float, y: float, width: float, f: Font, k: float, p: Dict, ctx: Ctx, name: str,
               auto: bool) -> List[str]:
    """The box behind a line: the « Fond » chosen, or (Lisibilité auto) a soft black block over a very bright picture."""
    kind = p.get("fond", "aucun")
    if kind == "aucun" and not auto:
        return []
    h = f.size * 1.3 * k
    pad = f.size * 0.45 * k
    if kind == "bande":
        x0, x1 = ctx.zone[0], ctx.zone[0] + ctx.zone[2]
    else:
        x0, x1 = cx - width * k / 2 - pad, cx + width * k / 2 + pad
    col = rgb(p.get("fond_couleur", "#000000")) if kind != "aucun" else (0, 0, 0)
    opacity = p.get("fond_opacite", 55) if kind != "aucun" else 45
    alpha = 255 - round(opacity * 255 / 100)
    shape = rrect(x0, y - h / 2, x1, y + h / 2, 0 if kind == "bande" else h * 0.3)
    return [event(a, b, name, f"{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c{tag_colour(col)}\\1a&H{alpha:02X}&}}{shape}{{\\p0}}", 0)]


def reveal(words: Words, ctx: Ctx, p: Dict, font: Font, name: str, tags=lambda w, now, k: "",
           n: Optional[int] = None, scale_of=lambda w: 1.0, P: Optional[Placer] = None, band_fixed: Optional[str] = None
           ) -> Tuple[List[str], List[Tuple]]:
    """The base of most styles: groups of n words on one line, each shown when said (the hidden ones keep their place
    so the line never jumps), placed by the Placer, shrunk to fit, its box behind if any -> (events, [(group, a, b, y,
    k, layout)]) for the styles that draw something more on the words."""
    P = P or Placer(ctx, p)
    out, lines = [], []
    for g, a, b in groups(words, n or p.get("mots", 3)):
        y, band = P.y(a, b)
        lay, width = line_layout(font, g, ctx, p, scale_of, p.get("espacement", 0))
        k = fit(width, P.max_w(band))
        light, auto_box = P.light(a, b, y)
        boxes = box_events(a, b, ctx.cx, y, width, font, k, p, ctx, name, auto_box)
        out += boxes
        base = (f"\\fscx{100 * k:.0f}\\fscy{100 * k:.0f}" if k < 1 else "") + light
        for i, (_, s, _) in enumerate(g):
            e = g[i + 1][1] if i + 1 < len(g) else b
            parts = [f"{{\\alpha&H{'00' if j <= i else 'FF'}&{base}{tags(w, j == i, k)}}}{esc(shown(w, ctx, p))}"
                     for j, w in enumerate(g)]
            out.append(event(s, e, name, f"{{\\an5\\pos({ctx.cx},{y})}}" + " ".join(parts), 1 if boxes else 0))
        lines.append((g, a, b, y, k, lay))
    return out, lines


def strong_or(w, ctx, yes: str, no: str = "") -> str:
    return yes if ctx.is_strong(w) else no


def scaled(x: float, k: float, ctx: Ctx) -> float:
    return ctx.cx + (x - ctx.cx) * k


# ---------------------------------------------------------------- the lab's styles (montage_test/alex, v1-v4)

@style("pop", "Pop orange", "Discours", "Mots blancs qui popent quand ils sont dits, les mots forts en orange (labo v1/v2).",
       common(accent="#ff7a00", spacing=0, border=2))
def _pop(words, ctx, p):
    f = main_font(p, ctx, 64)
    acc = tag_colour(rgb(p["accent"]))
    tags = lambda w, now, k: strong_or(w, ctx, f"\\c{acc}") + (pop(k, 70, 110) if now else "")
    ev, _ = reveal(words, ctx, p, f, "Pop", tags)
    return [line_style(f, "Pop", p)], ev, {}


@style("pyramide", "Pyramide", "Discours", "1 à 3 mots par ligne empilés sous l'image, gris clair, les mots forts en blanc pur (labo v3).",
       common(position="sous", words=3, colour="#e0e0e0", accent="#ffffff", spacing=0, font="semi", border=0, line=False))
def _pyramide(words, ctx, p):
    f = main_font(p, ctx, 62)
    P = Placer(ctx, p)
    lh = int(f.size * 1.25)
    shapes = {1: [1], 2: [2], 3: [1, 2], 4: [1, 3]}
    out = []
    key, base = tag_colour(rgb(p["accent"])), tag_colour(rgb(p["couleur"]))
    for g, a, b in groups(words, p["mots"]):
        y0, _ = P.y(a, b)
        light, _ = P.light(a, b, y0)
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
                    parts.append(f"{{\\c{key if ctx.is_strong(w) else base}\\alpha&H{'00' if j <= i else 'FF'}&{light}"
                                 f"{pop(1.0, 70, 110) if j == i else ''}}}{esc(shown(w, ctx, p))}")
                    j += 1
                out.append(event(s, e, "Py", f"{{\\an5\\pos({ctx.cx},{y0 + r * lh})}}" + " ".join(parts)))
    return [line_style(f, "Py", p)], out, {}


@style("escalier", "Escalier serif", "Discours", "Mots empilés (1 à 2 par ligne) sur l'image, pop rapide, les mots forts dans la police d'accent, plus grands (labo v4).",
       common(words=3, spacing=0, font="semi", border=1, line=False) + [Param("grand", "Taille des mots forts (%)", "int", 125, 100, 180, section="Texte")])
def _escalier(words, ctx, p):
    f, s = main_font(p, ctx, 68), accent_font(p, ctx, 68)
    P = Placer(ctx, p)
    lh = int(size(p, 84))
    out = []
    for g, a, b in groups(words, p["mots"]):
        y0, _ = P.y(a, b)
        light, _ = P.light(a, b, y0)
        rows = [[w] for w in g] if len(g) <= 2 else [g[:1], g[1:]]
        for i, (_, st, _) in enumerate(g):
            e = g[i + 1][1] if i + 1 < len(g) else b
            j = 0
            for r, row in enumerate(rows):
                parts = []
                for w in row:
                    look = (f"\\fn{s.family}" + ("" if ctx.rtl or p["police_forts"] != "serif" else "\\i1") +
                            f"\\fscx{p['grand']}\\fscy{p['grand']}\\c{tag_colour(rgb(p['accent']))}") if ctx.is_strong(w) else ""
                    parts.append(f"{{\\alpha&H{'00' if j <= i else 'FF'}&{light}{look}{pop() if j == i else ''}}}{esc(shown(w, ctx, p))}")
                    j += 1
                yy = y0 + (r - (len(rows) - 1) / 2) * lh
                out.append(event(st, e, "Es", f"{{\\an5\\pos({ctx.cx},{yy:.0f})}}" + " ".join(parts)))
    return [line_style(f, "Es", p)], out, {}


@style("editorial", "Éditorial", "Discours", "Tout en serif élégante, chaque mot apparaît en fondu, les mots forts en majuscules espacées (Chalamet chez @ofluminary).",
       common(words=3, colour="#f5eee1", accent="#f5eee1", spacing=0, font="serif", border=0))
def _editorial(words, ctx, p):
    f = main_font(p, ctx, 90)
    def tags(w, now, k):
        fade = f"\\alpha&HFF&\\t(0,{ms(5)},\\alpha&H00&)" if now and SPEED.get() else ""
        return fade + (f"\\fsp6\\c{tag_colour(rgb(p['accent']))}" if ctx.is_strong(w) else "")
    pc = dict(p, majuscules="mots_forts" if p["majuscules"] == "non" else p["majuscules"])
    ev, _ = reveal(words, ctx, pc, f, "Ed", tags)
    return [line_style(f, "Ed", p)], ev, {}


# ---------------------------------------------------------------- the catalogue's new styles (n°14-33)

@style("resserre", "Lettres resserrées", "Typographie", "Gras, lettres serrées (espacement -3) : l'aspect « pro » des Shorts viraux.",
       common(spacing=-3), number=14)
def _resserre(words, ctx, p):
    f = main_font(p, ctx, 70)
    ev, _ = reveal(words, ctx, p, f, "Re", lambda w, now, k: pop(k) if now else "")
    return [line_style(f, "Re", p)], ev, {}


@style("hierarchie", "Hiérarchie de taille", "Typographie", "Les mots secondaires petits, les mots forts très grands.",
       common() + [Param("grand", "Taille des mots forts (%)", "int", 150, 110, 200, section="Texte"),
                   Param("petit", "Taille des autres mots (%)", "int", 80, 50, 100, section="Texte")], number=15)
def _hierarchie(words, ctx, p):
    f = main_font(p, ctx, 64)
    scale_of = lambda w: (p["grand"] if ctx.is_strong(w) else p["petit"]) / 100
    tags = lambda w, now, k: f"\\fscx{100 * k * scale_of(w):.0f}\\fscy{100 * k * scale_of(w):.0f}"
    ev, _ = reveal(words, ctx, p, f, "Hi", tags, scale_of=scale_of)
    return [line_style(f, "Hi", p)], ev, {}


def _difference_events(words, ctx, p, small, big):
    P, out = Placer(ctx, p), []
    for g, a, b in groups(words, max(2, p["mots"] + 1)):
        y, band = P.y(a, b)
        y -= 30
        light, _ = P.light(a, b, y)
        strong = [w for w in g if ctx.is_strong(w)]
        key = strong[-1] if strong else max(g, key=lambda w: len(bare(w[0])))
        ctx_words = [w for w in g if w is not key]
        k = fit(big.width(shown(key, ctx, p).strip(".,،"), spacing=-6), P.max_w(band))
        if ctx_words:
            out.append(event(ctx_words[0][1], b, "D1", f"{{\\an2\\pos({ctx.cx},{y}){light}}}" + " ".join(esc(shown(w, ctx, p)) for w in ctx_words)))
        out.append(event(key[1], b, "D2", f"{{\\an8\\pos({ctx.cx},{y})\\fscx{100 * k:.0f}\\fscy{100 * k:.0f}{light}}}"
                                          f"{esc(shown(key, ctx, p).strip('.,،'))}"))
    return out


@style("difference", "Difference", "Typographie", "2 lignes : le contexte petit en haut, le mot fort énorme et gras dessous (Ben Kaluza).",
       common(words=3, font="semi", accent_font="black", border=0, shadow=1, line=False), number=16)
def _difference(words, ctx, p):
    small, big = main_font(p, ctx, 46), accent_font(p, ctx, 150)
    return ([line_style(small, "D1", p, spacing=-1), line_style(big, "D2", p, spacing=-6)],
            _difference_events(words, ctx, p, small, big), {})


@style("double_police", "Double police", "Typographie", "Gras pour la phrase, la police d'accent (serif italique, Tajawal Black en arabe) plus grande pour les mots forts.",
       common(spacing=-2, border=1) + [Param("grand", "Taille des mots forts (%)", "int", 140, 100, 180, section="Texte")], number=17)
def _double_police(words, ctx, p):
    f, s = main_font(p, ctx, 66), accent_font(p, ctx, 66)
    scale_of = lambda w: p["grand"] / 100 if ctx.is_strong(w) else 1.0
    def tags(w, now, k):
        look = ""
        if ctx.is_strong(w):
            look = (f"\\fn{s.family}" + ("" if ctx.rtl or p["police_forts"] != "serif" else "\\i1") +
                    f"\\fscx{p['grand'] * k:.0f}\\fscy{p['grand'] * k:.0f}\\c{tag_colour(rgb(p['accent']))}")
        return look + (pop(k * scale_of(w)) if now else "")
    ev, _ = reveal(words, ctx, p, f, "Dp", tags, scale_of=scale_of)
    return [line_style(f, "Dp", p)], ev, {}


@style("neon", "Néon qui grésille", "Animations", "Les mots forts s'allument comme un tube néon qui grésille (3 clignotements), avec une lueur.",
       common(accent="#00e5ff", font="semi", border=0, shadow=0) + [Param("clignotements", "Clignotements", "int", 3, 1, 6, section="Animation")], number=18)
def _neon(words, ctx, p):
    f = main_font(p, ctx, 68)
    glow = rgb(p["accent"])
    light = tuple(min(255, int(c + (255 - c) * 0.7)) for c in glow)
    def tags(w, now, k):
        if not ctx.is_strong(w):
            return ""
        look = f"\\c{tag_colour(light)}\\3c{tag_colour(glow)}\\bord3\\blur6"
        if now and SPEED.get():
            look += "".join(f"\\t({ms(j)},{ms(j) + 1},\\alpha&H{'FF' if j % 2 else '00'}&)"
                            for j in range(1, 2 * p["clignotements"] + 1))
        return look
    ev, _ = reveal(words, ctx, p, f, "Ne", tags)
    return [line_style(f, "Ne", p)], ev, {}


@style("slide_up", "Slide up", "Animations", "Une ligne : chaque mot glisse vers le haut à sa place, l'un après l'autre.",
       common(words=4, border=0, line=False), number=19)
def _slide_up(words, ctx, p):
    f = main_font(p, ctx, 62)
    P, out = Placer(ctx, p), []
    acc = tag_colour(rgb(p["accent"]))
    for g, a, b in groups(words, p["mots"]):
        y, band = P.y(a, b)
        light, _ = P.light(a, b, y)
        lay, width = line_layout(f, g, ctx, p, spacing=p["espacement"])
        k = fit(width, P.max_w(band))
        top, bottom = y - int(f.size * 0.75), y + int(f.size * 0.7)
        for w, x, wd in lay:
            x = scaled(x, k, ctx)
            col = f"\\c{acc}" if ctx.is_strong(w) else ""
            move = f"\\move({x:.0f},{y + 70},{x:.0f},{y},0,{ms(9)})" if SPEED.get() else f"\\pos({x:.0f},{y})"
            out.append(event(w[1], b, "Su", f"{{\\an5{move}\\clip(0,{top},{ctx.size[0]},{bottom})"
                                            f"\\fscx{100 * k:.0f}\\fscy{100 * k:.0f}{col}{light}}}{esc(shown(w, ctx, p))}"))
    return [line_style(f, "Su", p)], out, {}


@style("rebond", "Rebond Apple", "Animations", "1 à 2 mots qui montent vite, redescendent, remontent un peu et se posent (rebond amorti).",
       common(words=2, font="semi", border=0, shadow=1, line=False), number=20)
def _rebond(words, ctx, p):
    f = main_font(p, ctx, 84)
    P, out = Placer(ctx, p), []
    t1, t2, t3 = ms(4) / 1000, ms(9) / 1000, ms(13) / 1000
    for g, a, b in groups(words, p["mots"]):
        y, band = P.y(a, b)
        light, _ = P.light(a, b, y)
        _, width = line_layout(f, g, ctx, p, spacing=p["espacement"])
        k = fit(width, P.max_w(band))
        sc = f"\\fscx{100 * k:.0f}\\fscy{100 * k:.0f}{light}"
        text = " ".join(esc(shown(w, ctx, p)) for w in g)
        if t3 > 0:
            for s, e, y0, y1 in [(a, a + t1, y + 70, y - 14), (a + t1, a + t2, y - 14, y + 5), (a + t2, a + t3, y + 5, y)]:
                out.append(event(s, min(e, b), "Rb", f"{{\\an5\\move({ctx.cx},{y0},{ctx.cx},{y1}){sc}}}{text}"))   # one \\move a line
        if b > a + t3:
            out.append(event(a + t3, b, "Rb", f"{{\\an5\\pos({ctx.cx},{y}){sc}}}{text}"))
    return [line_style(f, "Rb", p)], out, {}


@style("degrade", "Dégradé", "Luxe", "Le texte passe d'une couleur en haut à une autre en bas (serif, Tajawal en arabe).",
       common(spacing=-1, font="serif", border=0, shadow=0, line=False) + [Param("haut", "Couleur du haut", "colour", "#ffffff", section="Texte"),
                                                                            Param("bas", "Couleur du bas", "colour", "#8c8c8c", section="Texte")], number=21)
def _degrade(words, ctx, p):
    f = main_font(p, ctx, 104)
    P, out = Placer(ctx, p), []
    top_c, bot_c = rgb(p["haut"]), rgb(p["bas"])
    h, bands = f.size * 1.1, 8
    for g, a, b in groups(words, p["mots"]):
        y, band = P.y(a, b)
        _, width = line_layout(f, g, ctx, p, spacing=p["espacement"])
        k = fit(width, P.max_w(band))
        text = " ".join(esc(shown(w, ctx, p)) for w in g)
        top = y - h * 0.55
        for j in range(bands):
            y0, y1 = top + j * h / bands, top + (j + 1) * h / bands + 1
            c = tuple(int(top_c[i] + (bot_c[i] - top_c[i]) * j / (bands - 1)) for i in range(3))
            out.append(event(a, b, "Dg", f"{{\\an5\\pos({ctx.cx},{y})\\clip(0,{y0:.0f},{ctx.size[0]},{y1:.0f})\\c{tag_colour(c)}"
                                         f"{pop(k)}}}{text}", j))
    return [line_style(f, "Dg", p, text=p["haut"])], out, {}


@style("biseau", "Biseau premium", "Luxe", "Très gras, couleur pleine, une ombre claire d'un pixel qui fait un biseau, un halo doux derrière.",
       common(words=2, colour="#7c3aed", spacing=-3, upper="oui", font="black", border=0, shadow=1, line=False) +
       [Param("biseau", "Couleur du biseau", "colour", "#ffffff", section="Contour et ombre"),
        Param("halo", "Halo", "bool", True, section="Contour et ombre")], number=22)
def _biseau(words, ctx, p):
    f = main_font(p, ctx, 78)
    P, out = Placer(ctx, p), []
    for g, a, b in groups(words, p["mots"]):
        y, band = P.y(a, b)
        text = " ".join(esc(shown(w, ctx, p)) for w in g)
        _, width = line_layout(f, g, ctx, p, spacing=p["espacement"])
        k = fit(width, P.max_w(band))
        if p["halo"]:
            hw = width * k * 0.38
            out.append(event(a, b, "Ha", f"{{\\an5\\pos({ctx.cx},{y})\\p1\\blur28\\alpha&HB0&\\c&HFFFFFF&}}"
                                         f"m {-hw:.0f} -40 l {hw:.0f} -40 l {hw:.0f} 40 l {-hw:.0f} 40{{\\p0}}", 0))
        out.append(event(a, b, "Bi", f"{{\\an5\\pos({ctx.cx},{y}){pop(k)}}}{text}", 1))
    bevel = line_style(f, "Bi", p, outline=colour(p["biseau"]), shadow=max(1.0, p["ombre"] * 1.4), back=colour(p["biseau"]))
    return [bevel, f.style("Ha")], out, {}


@style("surligneur", "Surligneur animé", "Animations", "Un rectangle (plein ou en contour) se dessine derrière chaque mot fort, dans le sens de la lecture.",
       common(accent="#ff3b30", border=0, shadow=0) + [Param("contour_seul", "Rectangle en contour seulement", "bool", False, section="Texte")], number=23)
def _surligneur(words, ctx, p):
    f = main_font(p, ctx, 66)
    ev, lines = reveal(words, ctx, p, f, "Su", lambda w, now, k: "")
    out = [e.replace("Dialogue: 0,", "Dialogue: 1,", 1) for e in ev]
    acc = rgb(p["accent"])
    for g, a, b, y, k, lay in lines:
        for w, x, wd in lay:
            if not ctx.is_strong(w):
                continue
            x, wd = scaled(x, k, ctx), wd * k
            x0, x1, y0, y1 = x - wd / 2 - 14, x + wd / 2 + 14, y - f.size * 0.68 * k, y + f.size * 0.7 * k
            box = f"m {x0:.0f} {y0:.0f} l {x1:.0f} {y0:.0f} l {x1:.0f} {y1:.0f} l {x0:.0f} {y1:.0f}"
            look = f"\\1a&HFF&\\bord5\\3c{tag_colour(acc)}" if p["contour_seul"] else ""
            # right to left: the marker runs from the word's right edge
            c0 = (f"\\clip({x1 + 6:.0f},{y0 - 6:.0f},{x1 + 6:.0f},{y1 + 6:.0f})" if ctx.rtl else
                  f"\\clip({x0 - 6:.0f},{y0 - 6:.0f},{x0 - 6:.0f},{y1 + 6:.0f})")
            full = f"\\clip({x0 - 6:.0f},{y0 - 6:.0f},{x1 + 6:.0f},{y1 + 6:.0f})"
            draw = f"{c0}\\t(0,{ms(8)},{full})" if SPEED.get() else full
            out.append(event(w[1], b, "Box", f"{{\\an7\\pos(0,0)\\p1{look}{draw}}}{box}{{\\p0}}", 0))
    return [line_style(f, "Su", p), f.style("Box", (*acc, 235), border=0, shadow=0)], out, {}


@style("reflet", "Reflet lumineux", "Luxe", "Les mots forts en couleur ; une bande de lumière les balaie quand ils sont dits.",
       common(accent="#00c8ff", font="black", border=0, shadow=1) + [Param("bande", "Couleur du reflet", "colour", "#ffffff", section="Texte")], number=24)
def _reflet(words, ctx, p):
    f = main_font(p, ctx, 72)
    acc = tag_colour(rgb(p["accent"]))
    out, lines = reveal(words, ctx, p, f, "Rf", lambda w, now, k: strong_or(w, ctx, f"\\c{acc}"))
    if not SPEED.get():
        return [line_style(f, "Rf", p)], out, {}
    for g, a, b, y, k, lay in lines:
        for w, x, wd in lay:
            if not ctx.is_strong(w):
                continue
            x, wd = scaled(x, k, ctx), wd * k
            x0, x1 = x - wd / 2 - 40, x + wd / 2 + 40
            start, stop = ((x1 - 34, x1), (x0, x0 + 34)) if ctx.rtl else ((x0, x0 + 34), (x1 - 34, x1))
            text = " ".join(f"{{\\alpha&H{'00' if v is w else 'FF'}&}}{esc(shown(v, ctx, p))}" for v in g)
            sc = f"\\fscx{100 * k:.0f}\\fscy{100 * k:.0f}" if k < 1 else ""
            out.append(event(w[1] + 0.05, w[1] + 0.6, "Rf", f"{{\\an5\\pos({ctx.cx},{y}){sc}\\c{tag_colour(rgb(p['bande']))}\\blur2"
                                                             f"\\clip({start[0]:.0f},0,{start[1]:.0f},{ctx.size[1]})"
                                                             f"\\t(0,{ms(14)},\\clip({stop[0]:.0f},0,{stop[1]:.0f},{ctx.size[1]}))}}{text}", 2))
    return [line_style(f, "Rf", p)], out, {}


@style("flou_net", "Flou → net", "Animations", "Chaque mot apparaît flou et transparent, puis devient net.", common(border=1), number=25)
def _flou_net(words, ctx, p):
    f = main_font(p, ctx, 68)
    tags = lambda w, now, k: f"\\blur12\\alpha&H80&\\t(0,{ms(7)},\\blur0\\alpha&H00&)" if now and SPEED.get() else ""
    ev, _ = reveal(words, ctx, p, f, "Fl", tags)
    return [line_style(f, "Fl", p)], ev, {}


@style("emojis", "Emojis", "Animations", "Un emoji au-dessus de chaque mot fort qui en a un (dictionnaire français, anglais, arabe).",
       common(), number=26)
def _emojis(words, ctx, p):
    from captions.emojis import emoji_of
    f = main_font(p, ctx, 66)
    out, lines = reveal(words, ctx, p, f, "Em", lambda w, now, k: pop(k) if now else "")
    marks = []
    for g, a, b, y, k, lay in lines:
        for w, x, wd in lay:
            ch = emoji_of(w[0]) if ctx.is_strong(w) or not ctx.strong else None
            if ch:
                marks.append((ch, w[1], b, scaled(x, k, ctx), y - f.size * 1.6))
    return [line_style(f, "Em", p)], out, {"emojis": marks}


@style("signature", "Signature de chaîne", "Identité", "Un trait fin à la couleur de la chaîne se dessine sous chaque mot fort : on reconnaît nos vidéos.",
       common(accent="#000000", border=1) + [Param("chaine", "Trait à la couleur de la chaîne", "bool", True, section="Texte"),
                                              Param("epaisseur", "Épaisseur du trait", "int", 8, 3, 16, section="Texte")], number=27)
def _signature(words, ctx, p):
    f = main_font(p, ctx, 66)
    out, lines = reveal(words, ctx, p, f, "Sg", lambda w, now, k: pop(k) if now else "")
    bar_c = rgb(ctx.colour) if p["chaine"] else rgb(p["accent"])
    for g, a, b, y, k, lay in lines:
        for w, x, wd in lay:
            if not ctx.is_strong(w):
                continue
            x, wd = scaled(x, k, ctx), wd * k
            x0, x1 = x - wd / 2, x + wd / 2
            y0 = y + f.size * 0.62 * k
            bar = f"m {x0:.0f} {y0:.0f} l {x1:.0f} {y0:.0f} l {x1:.0f} {y0 + p['epaisseur']:.0f} l {x0:.0f} {y0 + p['epaisseur']:.0f}"
            c0 = f"\\clip({x1:.0f},0,{x1:.0f},{ctx.size[1]})" if ctx.rtl else f"\\clip({x0:.0f},0,{x0:.0f},{ctx.size[1]})"
            full = f"\\clip({x0:.0f},0,{x1:.0f},{ctx.size[1]})"
            draw = f"{c0}\\t(0,{ms(7)},{full})" if SPEED.get() else full
            out.append(event(w[1], b, "Bar", f"{{\\an7\\pos(0,0)\\p1{draw}}}{bar}{{\\p0}}", 2))
    return [line_style(f, "Sg", p), f.style("Bar", (*bar_c, 255), border=0, shadow=0)], out, {}


def _sounds():
    try:
        return sorted(x for x in os.listdir(SFX_DIR) if x.endswith(".mp3"))
    except OSError:
        return ["click_ui_click.mp3"]


@style("clic", "Clic sonore sur le mot fort", "Son", "La hiérarchie de taille, plus un seul son discret pile sur le mot le plus fort.",
       common() + [Param("grand", "Taille des mots forts (%)", "int", 150, 110, 200, section="Texte"),
                   Param("petit", "Taille des autres mots (%)", "int", 80, 50, 100, section="Texte"),
                   Param("son", "Son", "choice", "click_ui_click.mp3", choices=[(s, s.rsplit(".", 1)[0]) for s in _sounds()], section="Son"),
                   Param("volume", "Volume du son (%)", "int", 60, 10, 100, section="Son")], number=28)
def _clic(words, ctx, p):
    styles_, events_, _ = _hierarchie(words, ctx, p)
    key = ctx.impact or next((bare(w[0]) for w in reversed(words) if ctx.is_strong(w)), None)
    at = next((w[1] for w in words if bare(w[0]) == key), None)
    sounds = [(os.path.join(SFX_DIR, p["son"]), at, p["volume"] / 100)] if at is not None else []
    return styles_, events_, {"sounds": sounds}


@style("evite_visage", "Évite le visage", "Placement", "Le placement Auto qui évite toujours les visages : chaque groupe de mots va dans la bande qui ne touche pas le visage.",
       common(), needs=("faces",), spaces=("generation", "montage", "adaptation", "discours"), number=29)
def _evite_visage(words, ctx, p):
    f = main_font(p, ctx, 70)
    forced = dict(p, position="auto", eviter_visages=True)
    ev, _ = reveal(words, ctx, forced, f, "Vi", lambda w, now, k: pop(k) if now else "")
    return [line_style(f, "Vi", p)], ev, {}


@style("soft_light", "Fusion Soft light", "Fusion", "Le texte se fond dans les teintes de l'image (beau sur les plans clairs, discret sur les sombres).",
       common(words=2, spacing=-4, font="black", border=0, shadow=0), number=30)
def _soft_light(words, ctx, p):
    f = main_font(p, ctx, 96)
    ev, _ = reveal(words, ctx, dict(p, lisibilite=False), f, "Sl", lambda w, now, k: pop(k) if now else "")
    return [line_style(f, "Sl", p)], ev, {"blend": "softlight"}


@style("fusion_difference", "Fusion Différence", "Fusion", "La mise en page « Difference », le texte inverse les couleurs de l'image derrière lui.",
       common(words=3, font="semi", accent_font="black", border=0, shadow=0, line=False), number=31)
def _fusion_difference(words, ctx, p):
    small, big = main_font(p, ctx, 46), accent_font(p, ctx, 150)
    return ([line_style(small, "D1", p, spacing=-1), line_style(big, "D2", p, spacing=-6)],
            _difference_events(words, ctx, dict(p, lisibilite=False), small, big), {"blend": "difference"})


@style("perspective", "Perspective 3D", "Fusion", "Mots empilés (les forts plus grands), le bloc incliné en perspective.",
       common(spacing=-4, font="black", border=0, shadow=0, line=False) + [Param("angle", "Inclinaison", "int", 12, 4, 30, section="Texte")], number=32)
def _perspective(words, ctx, p):
    f = main_font(p, ctx, 76)
    P, out = Placer(ctx, p), []
    for g, a, b in groups(words, p["mots"]):
        y, band = P.y(a, b)
        y0 = y - int(f.size * 1.2)
        for i, (_, s, _) in enumerate(g):
            e = g[i + 1][1] if i + 1 < len(g) else b
            for j, w in enumerate(g[:i + 1]):
                big = 135 if ctx.is_strong(w) else 100
                k = fit(f.width(shown(w, ctx, p)) * big / 100, P.max_w(band))
                sc = big * k
                zoom = (f"\\fscx{60 * k:.0f}\\fscy{60 * k:.0f}\\t(0,{ms(9)},\\fscx{sc:.0f}\\fscy{sc:.0f})" if j == i and SPEED.get()
                        else f"\\fscx{sc:.0f}\\fscy{sc:.0f}")
                out.append(event(s, e, "Pe", f"{{\\an5\\pos({ctx.cx},{y0 + j * int(f.size * 1.25)}){zoom}}}{esc(shown(w, ctx, p))}"))
    return [line_style(f, "Pe", p)], out, {"perspective": p["angle"]}


@style("derriere", "Texte derrière la personne", "Profondeur", "Un grand mot (les mots forts) posé derrière la personne, sa silhouette passe devant (SAM 2.1, carte graphique).",
       common(font="xbold", accent_font="black", line=False) + [Param("hauteur", "Hauteur du grand mot (% de l'image)", "int", 30, 10, 60, section="Placement")],
       needs=("mask",), spaces=("discours",), number=33)
def _derriere(words, ctx, p):
    big, small = accent_font(p, ctx, 300), main_font(p, ctx, 58)
    x, y, w, h = ctx.zone
    yy = int(y + h * p["hauteur"] / 100)
    strong = [wd for wd in words if ctx.is_strong(wd)] or [max(words, key=lambda wd: len(bare(wd[0])))]
    behind = []
    for i, wd in enumerate(strong):
        e = strong[i + 1][1] if i + 1 < len(strong) else words[-1][2] + 0.5
        word = bare(wd[0]) if ctx.rtl else bare(wd[0]).upper()
        k = fit(big.width(word, spacing=-8), w - 70)
        grow = f"\\fscx{70 * k:.0f}\\fscy{70 * k:.0f}\\t(0,{ms(5)},\\fscx{100 * k:.0f}\\fscy{100 * k:.0f})" if SPEED.get() \
            else f"\\fscx{100 * k:.0f}\\fscy{100 * k:.0f}"
        behind.append(event(wd[1], e, "Big", f"{{\\an5\\pos({ctx.cx},{yy})\\clip({x},{y},{x + w},{y + h}){grow}}}{esc(word)}"))
    P = Placer(ctx, p)
    front = []
    for g, a, b in groups(words, p["mots"]):
        yb, _ = P.y(a, b)
        light, _ = P.light(a, b, yb)
        front.append(event(a, b, "Sm", f"{{\\an5\\pos({ctx.cx},{yb}){light}}}" + " ".join(esc(shown(wd, ctx, p)) for wd in g), 2))
    return ([line_style(big, "Big", p, border=0, shadow=0, spacing=-8, text=p["couleur"]), line_style(small, "Sm", p)],
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
                        [Param("accent", "Couleur d'accent", "colour", "#ffd60a", section="Texte")] if _accent else [],
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
