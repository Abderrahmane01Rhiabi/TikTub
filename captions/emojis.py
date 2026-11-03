"""The emoji of a strong word (style « Emojis »), without AI: a word starting like one of these stems, in English,
French or Arabic, gets its emoji; any other word gets none (an emoji on every word is noise)."""

from typing import Optional

from captions.core import bare

STEMS = {
    "🏆": ["award", "trophy", "win", "victor", "champion", "prix", "trophée", "gagn", "vainq", "victoire", "الجائزة", "جائزة", "فوز", "بطل"],
    "✨": ["creat", "magic", "dream", "créé", "créa", "magie", "rêve", "أنشأ", "سحر", "حلم"],
    "⏳": ["wait", "time", "patien", "attend", "temps", "ينتظر", "انتظار", "وقت", "صبر"],
    "🎭": ["wing", "stage", "theat", "actor", "act", "coulisse", "scène", "théât", "acteur", "الكواليس", "مسرح", "ممثل"],
    "🔥": ["fire", "burn", "hot", "passion", "feu", "brûl", "نار", "شغف"],
    "💰": ["money", "rich", "dollar", "cash", "argent", "riche", "euro", "مال", "غني", "فلوس"],
    "❤️": ["love", "heart", "amour", "coeur", "cœur", "aime", "حب", "قلب"],
    "🧠": ["brain", "mind", "think", "smart", "cerveau", "esprit", "pens", "intellig", "عقل", "تفكير", "ذكي"],
    "💪": ["strong", "power", "force", "fort", "puissan", "قوة", "قوي"],
    "🚀": ["rocket", "launch", "fast", "speed", "fusée", "vite", "vitesse", "صاروخ", "سرعة"],
    "🌍": ["world", "earth", "planet", "monde", "terre", "planète", "عالم", "أرض"],
    "👑": ["king", "queen", "great", "legend", "roi", "reine", "légende", "ملك", "أسطورة"],
    "⚡": ["energy", "lightning", "électr", "énergie", "éclair", "طاقة", "برق"],
    "🎯": ["goal", "target", "focus", "but", "objectif", "cible", "هدف", "تركيز"],
    "💡": ["idea", "light", "idée", "lumière", "فكرة", "ضوء"],
    "😱": ["fear", "scar", "shock", "peur", "choc", "خوف", "صدمة"],
    "🤝": ["friend", "together", "ami", "ensemble", "صديق", "معا"],
    "📈": ["grow", "success", "rise", "croiss", "succès", "réuss", "نجاح", "نمو"],
}


def emoji_of(word: str) -> Optional[str]:
    w = bare(word)
    if len(w) < 3:
        return None
    for emoji, stems in STEMS.items():
        if any(w.startswith(s.lower()) for s in stems):
            return emoji
    return None
