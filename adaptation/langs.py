"""Per-language look of an adaptation: fonts, writing direction, capitals."""

import os
from typing import Dict

FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

LANGS: Dict[str, Dict] = {
    "fr": {
        "label": "Français",
        "rtl": False,
        "upper": True,                       # captions in CAPITALS, like the reference
        "banner_font": "Montserrat-Black.ttf",
        "credit_font": "Montserrat-ExtraBold.ttf",
        "caption_font": "Montserrat Black",  # family name, for libass
        "caption_size": 106,
        "credit_label": "Images :",
        "chars_per_second": 15,              # reading speed, to size sentences to their clip
    },
    "ar": {
        "label": "العربية",
        "rtl": True,
        "upper": False,                      # no capitals in Arabic: heavier weight instead
        "banner_font": "Tajawal-Black.ttf",
        "credit_font": "Tajawal-ExtraBold.ttf",
        "caption_font": "Tajawal Black",
        "caption_size": 118,
        "credit_label": "المصدر:",
        "chars_per_second": 12,
    },
    "en": {
        "label": "English",
        "rtl": False,
        "upper": True,
        "banner_font": "Montserrat-Black.ttf",
        "credit_font": "Montserrat-ExtraBold.ttf",
        "caption_font": "Montserrat Black",
        "caption_size": 106,
        "credit_label": "Footage:",
        "chars_per_second": 15,
    },
}


def lang(code: str) -> Dict:
    """Settings for a language code ('ar-EG' -> 'ar'); French look by default."""
    base = (code or "fr").split("-")[0].lower()
    return {**LANGS.get(base, LANGS["fr"]), "code": base}


def font_path(name: str) -> str:
    return os.path.join(FONTS_DIR, name)
