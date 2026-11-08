"""
When an AI step could not answer (credits out, network, a broken answer), the app goes on with a plain choice —
and now says so (the Dead Sea Short, 2026-11-08: Gemini's credits ran out at 12:40, the edit and the music were
made « en secours » and nothing on the screen told it).

Each warning is kept under its step's key in a "secours" dict — on the project (style), its storyboard (facts) or
one version (casting, hook, edit, music) — set when the step falls back, removed when it runs well again.
"""

from typing import Any, Dict, List, Optional

LABELS = {"recit": "Style du récit", "faits": "Vérification des faits", "casting": "Voix et manières",
          "accroche": "Accroche", "montage": "Montage", "musique": "Musique"}


def failed(r: Any) -> bool:
    """A Gemini answer that is not one: an error, or nothing usable."""
    return not isinstance(r, dict) or bool(r.get("error")) or bool(r.get("parsing_error"))


def why(r: Any) -> str:
    from gemini_ai_generator import CREDITS_OUT
    if isinstance(r, dict) and CREDITS_OUT in str(r.get("error") or ""):
        return "crédits Gemini épuisés"
    return "l'IA n'a pas répondu"


def mark(holder: Optional[Dict], key: str, message: Optional[str] = None) -> None:
    """Sets (message) or clears (None) one step's warning."""
    if holder is None:
        return
    s = holder.get("secours") or {}
    if message:
        s[key] = message
    else:
        s.pop(key, None)
    if s:
        holder["secours"] = s
    else:
        holder.pop("secours", None)


def listing(*holders: Optional[Dict]) -> List[str]:
    """Every warning of these holders, « Step : what was done instead »."""
    return [f"{LABELS.get(k, k)} : {m}" for h in holders if h for k, m in (h.get("secours") or {}).items()]
