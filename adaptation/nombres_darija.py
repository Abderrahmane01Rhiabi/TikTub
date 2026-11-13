"""
The numbers of a darija narration said in words (the user's ears, 2026-11-13: a blind test of 7 takes, Ghalia v4
with the numbers in words 4/5 against 3/5 with digits, then the corrected take 9/10 — « 110 » sent as digits is read
the fusha way or stumbled on), and their short units said in full.

  words     2 -> جوج, 22 -> تنين وعشرين, 110 -> مية وعشرة, 430 -> ربعمية وتلاتين, 1400 -> ألف وربعمية,
            2029 -> ألفين وتسعة وعشرين, 3000 -> تلت آلاف, 115000 -> مية وخمسطاش ألف,
            2000000 -> جوج ملايين (« ملايين » from 2 to 10, the user's rule), 3,5 -> تلاتة ونص (a « ,5 » is « ونص »,
            other decimals « فاصلة »), 30% -> تلاتين فالمية
  groups    « 11 000 » (thousands written apart) is one number: the first group says it all, the next ones nothing
  after     a number word written after digits takes the darija plural: « 2 مليون » -> جوج ملايين, « 5 ألف » ->
            خمسة آلاف
  units     كلم -> كيلومتر, كلغ -> كيلو, م³ -> متر مكعب, م² -> متر مربع, كلم/س -> كيلومتر فالساعة, م -> متر (only right
            after a number, never after a year 1900-2100: « 2029 م » is a date), also stuck to the number (« 3كلم »)
  reading   (the written words, i) -> what ElevenLabs reads for word i, None when it is left as it is (a time
            « 14:30 », a score « 2-1 », a « 07 »); a prefix stuck to the number (ف / و / ب / ل / د) stays stuck
Only the text sent to the voice changes: the captions, the script and the banners keep the digits (voices.synthesize
gives the timings back to the written words, like the pronunciation dictionary).
"""

import re
from typing import List, Optional

UNITS = ["صفر", "واحد", "جوج", "تلاتة", "ربعة", "خمسة", "ستة", "سبعة", "تمنية", "تسعود"]
IN_TENS = ["", "واحد", "تنين", "تلاتة", "ربعة", "خمسة", "ستة", "سبعة", "تمنية", "تسعة"]   # « تنين وعشرين »
TEENS = ["عشرة", "حداش", "طناش", "تلطاش", "ربعطاش", "خمسطاش", "سطاش", "سبعطاش", "تمنطاش", "تسعطاش"]
TENS = ["", "", "عشرين", "تلاتين", "ربعين", "خمسين", "ستين", "سبعين", "تمانين", "تسعين"]
HUNDREDS = ["", "مية", "ميتين", "تلتمية", "ربعمية", "خمسمية", "ستمية", "سبعمية", "تمنمية", "تسعمية"]
FEW = {3: "تلت", 4: "ربع", 5: "خمس", 6: "ست", 7: "سبع", 8: "تمن", 9: "تسع", 10: "عشر"}   # « تلت آلاف »
PLURAL = {"ألف": "آلاف", "الف": "آلاف", "مليون": "ملايين"}           # after 2 to 10 written in digits

UNIT_WORDS = {"كلم": "كيلومتر", "كلغ": "كيلو", "م³": "متر مكعب", "م3": "متر مكعب", "م²": "متر مربع",
              "م2": "متر مربع", "كلم/س": "كيلومتر فالساعة", "كلم/ساعة": "كيلومتر فالساعة", "كم/س": "كيلومتر فالساعة"}
AFTER_NUMBER = {"م": "متر"}                                            # alone, « م » is only a metre after a number

DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬", "01234567890123456789.,")
PREFIX = "وفبلد"
SUFFIXES = sorted(list(UNIT_WORDS) + list(AFTER_NUMBER) + ["%"], key=len, reverse=True)
TOKEN = re.compile(r"^([" + PREFIX + r"]?)(\d[\d.,]*)(" + "|".join(re.escape(x) for x in SUFFIXES) + r")?$")
GROUP = re.compile(r"^\d{3}$")
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
    if n == 1:
        return word
    if word == "مليون" and 2 <= n <= 10:
        return f"{_below_1000(n)} ملايين"
    return f"{_below_1000(n)} {word}"


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


def value(text: str) -> Optional[float]:
    """« 110 », « 5,000 », « 115.000 », « 3,5 » -> its value; None when it isn't a plain number (« 07 », « 2-1 »)."""
    text = text.translate(DIGITS)
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", text) and len({c for c in text if c in ".,"}) == 1:
        return float(re.sub(r"[.,]", "", text))                      # thousands separators: « 5,000 » « 115.000 »
    m = re.fullmatch(r"(\d+)(?:[.,](\d+))?", text)
    if not m or len(m.group(1)) > 1 and m.group(1).startswith("0") or int(m.group(1)) >= LIMIT:
        return None
    return float(text.replace(",", "."))


def number(text: str) -> Optional[str]:
    """A plain number in words; None when it isn't one."""
    v = value(text)
    if v is None:
        return None
    text = text.translate(DIGITS)
    whole = int(v)
    frac = re.fullmatch(r"\d+[.,](\d+)", text)
    if not frac or v == whole and re.fullmatch(r"\d{1,3}([.,]\d{3})+", text):
        return words(whole)
    f = frac.group(1)
    if f.rstrip("0") == "5":                                         # « 3,5 » -> تلاتة ونص, « 0,5 » -> نص
        return "نص" if whole == 0 else f"{words(whole)} ونص"
    f_said = words(int(f)) if not f.startswith("0") and len(f) <= 3 else " ".join(UNITS[int(c)] for c in f)
    return f"{words(whole)} فاصلة {f_said}"


def _is_group_start(cores: List[str], i: int) -> bool:
    """« 11 » in « 11 000 »: 1-3 digits followed by groups of 3 digits."""
    return bool(re.fullmatch(r"\d{1,3}", cores[i].translate(DIGITS))) and i + 1 < len(cores) \
        and bool(GROUP.match(cores[i + 1].translate(DIGITS))) \
        and not (i > 0 and _is_group_start(cores, i - 1))


def _in_group(cores: List[str], i: int) -> bool:
    """« 000 » in « 11 000 »: said with the first group."""
    j = i
    while j > 0 and GROUP.match(cores[j].translate(DIGITS)):
        j -= 1
        if _is_group_start(cores, j):
            return True
        if not GROUP.match(cores[j].translate(DIGITS)):
            return False
    return False


def _number_before(cores: List[str], i: int) -> Optional[float]:
    """The value written right before word i (« 2 000 » counted whole), None when it isn't a number."""
    if i == 0:
        return None
    j = i - 1
    while j > 0 and _in_group(cores, j):
        j -= 1
    if _is_group_start(cores, j):
        k = j + 1
        digits = cores[j]
        while k < i and GROUP.match(cores[k].translate(DIGITS)):
            digits += cores[k]
            k += 1
        return value(digits)
    m = TOKEN.match(cores[j].translate(DIGITS).replace("٪", "%"))
    return value(m.group(2)) if m and not m.group(3) else None


def _is_year(v: float) -> bool:
    return v == int(v) and 1900 <= v <= 2100


def reading(cores: List[str], i: int) -> Optional[str]:
    """What the voice reads for written word i (its punctuation already taken off), None when it is left alone;
    « » (nothing) for a group said with the one before (« 000 » of « 11 000 »)."""
    core = cores[i]
    if core in ("%", "٪"):
        return "فالمية"
    if core in UNIT_WORDS:
        return UNIT_WORDS[core]
    before = _number_before(cores, i)
    if core in AFTER_NUMBER:
        return AFTER_NUMBER[core] if before is not None and not _is_year(before) else None
    if core in PLURAL:
        return PLURAL[core] if before is not None and before == int(before) and 2 <= before <= 10 else None
    if _in_group(cores, i):
        return ""
    if _is_group_start(cores, i):
        k, digits = i + 1, core
        while k < len(cores) and GROUP.match(cores[k].translate(DIGITS)):
            digits += cores[k]
            k += 1
        return number(digits)
    m = TOKEN.match(core.translate(DIGITS).replace("٪", "%"))
    if not m:
        return None
    prefix, digits, unit = m.groups()
    said = number(digits)
    if said is None:
        return None
    if unit == "%":
        return f"{prefix}{said} فالمية"
    if unit:
        v = value(digits)
        if unit in AFTER_NUMBER and _is_year(v):
            return None                                              # « 2029م » : a date, left as written
        return f"{prefix}{said} {UNIT_WORDS.get(unit) or AFTER_NUMBER[unit]}"
    return prefix + said


def token(core: str) -> Optional[str]:
    """One word read alone (no neighbours)."""
    return reading([core], 0)
