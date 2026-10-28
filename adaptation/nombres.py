"""The numbers of a sentence, in digits or in words (French, Arabic), with the words right after each one.

Arabic voices write numbers in words ("خمسة وثلاثين"), French often too ("cent trente"): a guard on numbers
must read both. Approximate on purpose (no ordinals, no fractions): it is only used to see that a number of
the draft is still there after a re-read. Measured on the storyboards of RESULTATS_MODELES.md."""

import re
from typing import List, Set, Tuple

FR = {"zero": 0, "zéro": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7,
      "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15,
      "seize": 16, "vingt": 20, "vingts": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60}
FR_MULT = {"cent": 100, "cents": 100, "mille": 1000, "million": 10**6, "millions": 10**6, "milliard": 10**9, "milliards": 10**9}
AR = {"واحد": 1, "واحدة": 1, "إحدى": 1, "احدى": 1, "أحد": 1, "اثنان": 2, "اثنين": 2, "اثنتان": 2, "ثلاث": 3, "ثلاثة": 3,
      "أربع": 4, "أربعة": 4, "خمس": 5, "خمسة": 5, "ست": 6, "ستة": 6, "سبع": 7, "سبعة": 7, "ثمان": 8, "ثماني": 8,
      "ثمانية": 8, "تسع": 9, "تسعة": 9, "عشر": 10, "عشرة": 10, "عشرون": 20, "عشرين": 20, "ثلاثون": 30, "ثلاثين": 30,
      "أربعون": 40, "أربعين": 40, "خمسون": 50, "خمسين": 50, "ستون": 60, "ستين": 60, "سبعون": 70, "سبعين": 70,
      "ثمانون": 80, "ثمانين": 80, "تسعون": 90, "تسعين": 90, "مئتين": 200, "مئتان": 200, "مائتين": 200, "مائتان": 200}
AR_MULT = {"مئة": 100, "مائة": 100, "ألف": 1000, "آلاف": 1000, "ألفا": 1000, "مليون": 10**6, "ملايين": 10**6, "مليار": 10**9}
PERCENT = re.compile(r"pour\s*cent|بالمئة|بالمائة|في المئة|في المائة", re.I)
TOKENS = re.compile(r"\d+(?:[.,]\d+)?|[\w؀-ۿ%]+")


def _ar(w: str):
    """An Arabic number word, under its prefixes (و، ب، ل، ال…)."""
    for x in (w, w[1:] if w[:1] in "وبلك" else None, w[2:] if w[:2] in ("وب", "ول", "ال") else None,
              w[3:] if w[:3] in ("بال", "وال", "لل") else None):
        if not x:
            continue
        if x in AR or x in AR_MULT or x == "ألفين":
            return x
        if x.endswith(("مئة", "مائة")) and x[:-3] in AR:          # ثلاثمئة
            return x
    return None


def tokens(text: str) -> List[str]:
    t = (text or "").translate(str.maketrans("٠١٢٣٤٥٦٧٨٩٫", "0123456789."))
    t = re.sub(r"(?<=\d)[   ](?=\d{3}\b)", "", t)        # 10 000 -> 10000
    t = PERCENT.sub(" % ", t)                                      # "pour cent" is not a hundred
    return [w.lower() for w in TOKENS.findall(t.replace("-", " "))]


def occurrences(text: str) -> List[Tuple[float, List[str]]]:
    """Each number of the text, with the six words after it (its unit, a "par kilogramme")."""
    toks = tokens(text) + ["."]
    out, total, cur, start, seen = [], 0, 0, None, False

    def close(end):
        if seen and total + cur:
            out.append((float(total + cur), toks[end:end + 6]))

    for i, w in enumerate(toks):
        if re.fullmatch(r"\d+(?:[.,]\d+)?", w):
            close(i)
            total, cur, seen = 0, 0, False
            out.append((float(w.replace(",", ".")), toks[i + 1:i + 7]))
            continue
        a = _ar(w)
        if w in FR or w in FR_MULT or a:
            seen = True
            if w in FR:
                cur = cur - 4 + 80 if w.startswith("vingt") and cur % 100 == 4 else cur + FR[w]
            elif w in FR_MULT:
                if FR_MULT[w] == 100:
                    cur = max(cur, 1) * 100
                else:
                    total, cur = total + max(cur, 1) * FR_MULT[w], 0
            elif a == "ألفين":
                total, cur = total + 2000, 0
            elif a in AR:
                cur += AR[a]
            elif a in AR_MULT:
                if AR_MULT[a] == 100:
                    cur = max(cur, 1) * 100
                else:
                    total, cur = total + max(cur, 1) * AR_MULT[a], 0
            else:
                cur += AR[a[:-3]] * 100
            continue
        if w == "et" and seen:
            continue
        close(i)
        total, cur, seen = 0, 0, False
    return out


def values(text: str) -> Set[float]:
    return {n for n, _ in occurrences(text)}


def same(a: float, b: float) -> bool:
    return abs(a - b) <= 0.01 * max(abs(b), 1)
