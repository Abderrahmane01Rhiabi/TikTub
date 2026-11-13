"""
The numbers of a darija narration said in words (the user's ears, 2026-11-13: a blind test of 7 takes, Ghalia v4
with the numbers in words 4/5 against 3/5 with digits, then the corrected take 9/10 — « 110 » sent as digits is read
the fusha way or stumbled on).

  words     2 -> جوج, 22 -> تنين وعشرين, 110 -> مية وعشرة, 430 -> ربعمية وتلاتين, 1400 -> ألف وربعمية,
            2029 -> ألفين وتسعة وعشرين, 3000 -> تلت آلاف, 115000 -> مية وخمسطاش ألف, 2000000 -> جوج مليون,
            3,5 -> تلاتة فاصلة خمسة, 30% -> تلاتين فالمية
  token     one written word -> what ElevenLabs reads, or None when it isn't a number (a time « 14:30 », a score
            « 2-1 », a « 07 » are left as they are); a prefix stuck to it (ف / و / ب / ل / د) stays stuck
Only the text sent to the voice changes: the captions, the script and the banners keep the digits (voices.synthesize
gives the timings back to the written word, like the pronunciation dictionary).
"""

import re
from typing import Optional

UNITS = ["صفر", "واحد", "جوج", "تلاتة", "ربعة", "خمسة", "ستة", "سبعة", "تمنية", "تسعود"]
IN_TENS = ["", "واحد", "تنين", "تلاتة", "ربعة", "خمسة", "ستة", "سبعة", "تمنية", "تسعة"]   # « تنين وعشرين »
TEENS = ["عشرة", "حداش", "طناش", "تلطاش", "ربعطاش", "خمسطاش", "سطاش", "سبعطاش", "تمنطاش", "تسعطاش"]
TENS = ["", "", "عشرين", "تلاتين", "ربعين", "خمسين", "ستين", "سبعين", "تمانين", "تسعين"]
HUNDREDS = ["", "مية", "ميتين", "تلتمية", "ربعمية", "خمسمية", "ستمية", "سبعمية", "تمنمية", "تسعمية"]
FEW = {3: "تلت", 4: "ربع", 5: "خمس", 6: "ست", 7: "سبع", 8: "تمن", 9: "تسع", 10: "عشر"}   # « تلت آلاف »

DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬", "01234567890123456789.,")
PREFIX = "وفبلد"
TOKEN = re.compile(r"^([" + PREFIX + r"]?)(\d[\d.,]*)(%?)$")
LIMIT = 10 ** 12


def _below_100(n: int) -> str:
    if n < 10:
        return UNITS[n]
    if n < 20:
        return TEENS[n - 10]
    u, t = n % 10, n // 10
    return TENS[t] if not u else f"{IN_TENS[u]} و{TENS[t]}"


def _below_1000(n: int) -> str:
    h, r = divmod(n, 100)
    parts = ([HUNDREDS[h]] if h else []) + ([_below_100(r)] if r or not h else [])
    return " و".join(parts)


def _thousands(t: int) -> str:
    if t == 1:
        return "ألف"
    if t == 2:
        return "ألفين"
    if t in FEW:
        return f"{FEW[t]} آلاف"
    return f"{_below_1000(t)} ألف"


def _big(n: int, word: str) -> str:
    return word if n == 1 else f"{_below_1000(n)} {word}"


def words(n: int) -> str:
    """A whole number (0 ≤ n < 10^12) in darija words."""
    if n < 0 or n >= LIMIT:
        raise ValueError(n)
    if n < 1000:
        return _below_1000(n)
    milliards, rest = divmod(n, 10 ** 9)
    millions, rest = divmod(rest, 10 ** 6)
    thousands, rest = divmod(rest, 1000)
    parts = []
    if milliards:
        parts.append(_big(milliards, "مليار"))
    if millions:
        parts.append(_big(millions, "مليون"))
    if thousands:
        parts.append(_thousands(thousands))
    if rest:
        parts.append(_below_1000(rest))
    return " و".join(parts)


def number(text: str) -> Optional[str]:
    """« 110 », « 5,000 », « 115.000 », « 3,5 » -> words; None when it isn't a plain number."""
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", text) and len({c for c in text if c in ".,"}) == 1:
        return words(int(re.sub(r"[.,]", "", text)))                 # thousands separators: « 5,000 » « 115.000 »
    m = re.fullmatch(r"(\d+)(?:[.,](\d+))?", text)
    if not m:
        return None
    whole, frac = m.groups()
    if len(whole) > 1 and whole.startswith("0") or int(whole) >= LIMIT:
        return None                                                  # « 07 », a phone number…
    said = words(int(whole))
    if frac:
        frac_said = words(int(frac)) if not frac.startswith("0") and len(frac) <= 3 else \
            " ".join(UNITS[int(c)] for c in frac)
        said += f" فاصلة {frac_said}"
    return said


def token(core: str) -> Optional[str]:
    """One written word (punctuation already taken off) -> what the voice reads, None when it isn't a number."""
    if core in ("%", "٪"):
        return "فالمية"
    m = TOKEN.match(core.translate(DIGITS).replace("٪", "%"))
    if not m:
        return None
    prefix, digits, percent = m.groups()
    said = number(digits)
    if said is None:
        return None
    return prefix + said + (" فالمية" if percent else "")
