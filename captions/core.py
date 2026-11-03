"""Fonts, measures, context and common settings of the caption library."""

import os
import shutil
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H, FPS = 1080, 1920, 30
MS = 1000 / FPS

Words = List[Sequence]                       # [(text, start, end)], in the video's own time

_MONTAGE_FONTS = os.path.join(ROOT, "montage", "fonts")
_ADAPT_FONTS = os.path.join(ROOT, "adaptation", "fonts")
LATIN = {"semi": (os.path.join(_MONTAGE_FONTS, "Montserrat-SemiBold.ttf"), "Montserrat SemiBold"),
         "xbold": (os.path.join(_ADAPT_FONTS, "Montserrat-ExtraBold.ttf"), "Montserrat ExtraBold"),
         "black": (os.path.join(_ADAPT_FONTS, "Montserrat-Black.ttf"), "Montserrat Black"),
         "serif": (os.path.join(_MONTAGE_FONTS, "InstrumentSerif-Italic.ttf"), "Instrument Serif")}
# no Arabic serif or italic: the accent font is the heaviest Tajawal (Arabic is never slanted)
ARABIC = {"semi": (os.path.join(_ADAPT_FONTS, "Tajawal-ExtraBold.ttf"), "Tajawal ExtraBold"),
          "xbold": (os.path.join(_ADAPT_FONTS, "Tajawal-ExtraBold.ttf"), "Tajawal ExtraBold"),
          "black": (os.path.join(_ADAPT_FONTS, "Tajawal-Black.ttf"), "Tajawal Black"),
          "serif": (os.path.join(_ADAPT_FONTS, "Tajawal-Black.ttf"), "Tajawal Black")}
RTL_LANGS = {"ar"}
SYSTEM_FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"]     # the Génération styles'
PUNCT = ".,!?\"'«»:;،؟…"


def rtl(lang: Optional[str]) -> bool:
    return (lang or "").split("-")[0] in RTL_LANGS


def fonts_dir() -> str:
    """libass reads ONE fonts folder: every caption font gathered in temp/caption_fonts (kept by the storage cleanup)."""
    d = os.path.abspath(os.path.join("temp", "caption_fonts"))
    os.makedirs(d, exist_ok=True)
    for path in [p for p, _ in LATIN.values()] + [p for p, _ in ARABIC.values()] + SYSTEM_FONTS + \
            [os.path.join(_MONTAGE_FONTS, "LilitaOne-Regular.ttf")]:
        dst = os.path.join(d, os.path.basename(path))
        if os.path.exists(path) and not os.path.exists(dst):
            shutil.copy(path, dst)
    return d


def _win_metrics(path: str) -> Tuple[int, int]:
    """(unitsPerEm, usWinAscent + usWinDescent): libass sizes a font so that the second equals Fontsize."""
    with open(path, "rb") as fh:
        data = fh.read()
    tables = {}
    for i in range(struct.unpack(">H", data[4:6])[0]):
        tag, _, off, length = struct.unpack(">4sIII", data[12 + 16 * i: 28 + 16 * i])
        tables[tag] = data[off: off + length]
    upm = struct.unpack(">H", tables[b"head"][18:20])[0]
    asc, desc = struct.unpack(">HH", tables[b"OS/2"][74:78])
    return upm, asc + desc


class Font:
    """A font of the library at a size, for one language: its .ass style line and its widths, measured with the real
    shaping (raqm: joined Arabic letters, right to left) at the size the text is drawn."""

    def __init__(self, key: str, size: float, lang: Optional[str] = None):
        self.rtl = rtl(lang)
        self.path, self.family = (ARABIC if self.rtl else LATIN)[key]
        self.size = size
        self.pil = ImageFont.truetype(self.path, max(1, int(round(size))), layout_engine=ImageFont.Layout.RAQM)
        upm, win = _win_metrics(self.path)
        self.ass_size = round(size * win / upm, 1)

    def width(self, text: str, scale: float = 1.0, spacing: float = 0.0) -> float:
        w = self.pil.getlength(text, direction="rtl") if self.rtl else self.pil.getlength(text)
        return (w + spacing * max(0, len(text) - 1)) * scale

    def style(self, name: str, colour=(255, 255, 255, 255), outline=(0, 0, 0, 255), border: float = 0.0,
              shadow: float = 0.0, spacing: float = 0.0, back=(0, 0, 0, 160), italic: bool = False) -> str:
        enc = -1 if self.rtl else 1                       # right-to-left base for Arabic (adaptation/render.py)
        return (f"Style: {name},{self.family},{self.ass_size},{ass_colour(colour)},{ass_colour(colour)},"
                f"{ass_colour(outline)},{ass_colour(back)},0,{-1 if italic and not self.rtl else 0},0,0,100,100,"
                f"{spacing:g},0,1,{border:g},{shadow:g},5,0,0,0,{enc}")


# ---------------------------------------------------------------- colours, times, events

def rgb(value, default=(255, 255, 255)) -> Tuple[int, int, int]:
    """"#rrggbb" (a colour input) -> (r, g, b); anything else -> default."""
    if isinstance(value, (tuple, list)) and len(value) >= 3:
        return tuple(int(v) for v in value[:3])
    h = str(value or "").lstrip("#")
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)) if len(h) == 6 else default
    except ValueError:
        return default


def ass_colour(c) -> str:
    r, g, b = c[:3]
    a = 255 - (c[3] if len(c) > 3 else 255)
    return f"&H{a:02X}{b:02X}{g:02X}{r:02X}"


def tag_colour(c) -> str:
    r, g, b = c[:3]
    return f"&H{b:02X}{g:02X}{r:02X}&"


def ass_time(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def esc(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def event(a: float, b: float, style: str, text: str, layer: int = 0) -> str:
    return f"Dialogue: {layer},{ass_time(a)},{ass_time(max(b, a + 0.05))},{style},,0,0,0,,{text}"


def header(styles: List[str], size=(W, H)) -> str:
    w, h = size
    return ("[Script Info]\nScriptType: v4.00+\n"
            f"PlayResX: {w}\nPlayResY: {h}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n" + "\n".join(styles) +
            "\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")


# ---------------------------------------------------------------- words

def bare(text: str) -> str:
    return str(text).strip(PUNCT).lower()


def groups(words: Words, n: int = 3) -> List[Tuple[list, float, float]]:
    """Phrases of up to n words, a new one after punctuation; each with the time it stays on screen."""
    out, cur = [], []
    for w in words:
        cur.append(list(w))
        if len(cur) >= n or str(w[0])[-1:] in PUNCT:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return [(g, g[0][1], (out[i + 1][0][1] if i + 1 < len(out) else g[-1][2] + 0.5)) for i, g in enumerate(out)]


STOP = {"the", "and", "that", "this", "with", "have", "from", "they", "were", "what", "your", "about", "would",
        "there", "their", "which", "quand", "dans", "pour", "avec", "mais", "comme", "elle", "ils", "nous", "vous",
        "cette", "sont", "était", "être", "avoir", "tout", "plus", "fait", "faire", "aussi", "alors", "parce", "quoi",
        "عندما", "الذي", "التي", "هذا", "هذه", "ذلك", "على", "إلى", "كان", "كانت", "لكن", "لأن"}


def strong_words(words: Words, given: Optional[Sequence[str]] = None, every: int = 4) -> set:
    """The words to bring out: the ones given (Gemini's key words), else the longest meaningful word of every few."""
    if given:
        return {bare(x) for g in given for x in str(g).split() if bare(x)}
    out = set()
    for i in range(0, len(words), every):
        cands = [bare(w[0]) for w in words[i:i + every] if len(bare(w[0])) >= 5 and bare(w[0]) not in STOP]
        if cands:
            out.add(max(cands, key=len))
    return out


# ---------------------------------------------------------------- context

@dataclass
class Ctx:
    """Where and for whom a style is drawn. zone: the picture the captions belong to (x, y, w, h) on the canvas."""
    lang: str = "fr"
    zone: Tuple[int, int, int, int] = (87, 507, 906, 906)
    strong: set = field(default_factory=set)
    impact: Optional[str] = None
    colour: str = "#FF7A00"                       # the channel's colour (channels/channel_config.json)
    faces: List[Tuple[float, Tuple[float, float, float, float]]] = field(default_factory=list)
    size: Tuple[int, int] = (W, H)

    @property
    def rtl(self) -> bool:
        return rtl(self.lang)

    @property
    def cx(self) -> int:
        x, _, w, _ = self.zone
        return int(x + w / 2)

    def y(self, position: str) -> int:
        x, y, w, h = self.zone
        if position == "haut":
            return int(y + h * 0.16)
        if position == "milieu":
            return int(y + h * 0.5)
        if position == "sous":
            return int(min(self.size[1] - 160, y + h + 110))
        return int(y + h * 0.80)

    def max_w(self, position: str) -> float:
        return (self.size[0] - 160) if position == "sous" else max(300, self.zone[2] - 80)

    def is_strong(self, word) -> bool:
        return bare(word[0] if isinstance(word, (list, tuple)) else word) in self.strong


# ---------------------------------------------------------------- settings

@dataclass
class Param:
    name: str
    label: str
    kind: str                                     # "int" | "choice" | "colour" | "bool"
    default: object
    lo: Optional[float] = None
    hi: Optional[float] = None
    choices: Optional[List[Tuple[str, str]]] = None

    def clean(self, value):
        if value is None:
            return self.default
        try:
            if self.kind == "int":
                return int(min(self.hi, max(self.lo, round(float(value)))))
            if self.kind == "bool":
                return value in (True, "true", "1", 1, "oui")
            if self.kind == "colour":
                r, g, b = rgb(value, default=None) or rgb(self.default)
                return f"#{r:02x}{g:02x}{b:02x}"
            if self.kind == "choice":
                return value if value in [c for c, _ in self.choices] else self.default
        except (TypeError, ValueError):
            return self.default
        return self.default

    def public(self) -> Dict:
        return {"name": self.name, "label": self.label, "kind": self.kind, "default": self.default, "lo": self.lo,
                "hi": self.hi, "choices": [{"value": c, "label": l} for c, l in self.choices] if self.choices else None}


POSITIONS = [("bas", "Bas de l'image"), ("milieu", "Milieu"), ("haut", "Haut"), ("sous", "Sous l'image")]


def common(position="bas", words=3, colour="#ffffff", accent="#ffd60a", spacing=-2, upper="non") -> List[Param]:
    """The settings every new style has."""
    return [Param("taille", "Taille (%)", "int", 100, 60, 160),
            Param("position", "Position", "choice", position, choices=POSITIONS),
            Param("mots", "Mots à la fois", "int", words, 1, 4),
            Param("couleur", "Couleur du texte", "colour", colour),
            Param("accent", "Couleur d'accent", "colour", accent),
            Param("espacement", "Espacement des lettres", "int", spacing, -8, 8),
            Param("majuscules", "Majuscules", "choice", upper,
                  choices=[("non", "Non"), ("oui", "Tout"), ("mots_forts", "Mots forts seulement")])]


def shown(word, ctx: Ctx, p: Dict) -> str:
    """A word as written on screen (capitals per the setting; never in Arabic)."""
    text = str(word[0])
    if ctx.rtl:
        return text
    if p.get("majuscules") == "oui" or (p.get("majuscules") == "mots_forts" and ctx.is_strong(word)):
        return text.upper()
    return text


def line_layout(font: Font, ws: list, ctx: Ctx, p: Dict, scale_of=lambda w: 1.0, spacing: float = 0.0):
    """Centre x of each word of a centred line, measured as drawn -> ([(word, x, width)], line width). Right to left:
    the first word on the right."""
    sp = font.width(" ")
    widths = [font.width(shown(w, ctx, p), scale_of(w), spacing) for w in ws]
    total = sum(widths) + sp * (len(ws) - 1)
    x, out = ctx.cx - total / 2, []
    for w, wd in zip(ws, widths):
        out.append((w, x + wd / 2, wd))
        x += wd + sp
    if ctx.rtl:
        out = [(w, 2 * ctx.cx - x, wd) for w, x, wd in out]
    return out, total


def fit(width: float, max_w: float) -> float:
    """The scale that keeps a line inside the zone (never enlarged)."""
    return min(1.0, max_w / max(1.0, width))
