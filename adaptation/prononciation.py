"""
The pronunciation dictionary (the user's ears, 2026-11-09: ElevenLabs v4 said « جرادي » with a G, « المعلمة »
m3alma instead of ma3lama, « المستافدين » mastafdin, « فبرطمات » bartamat).

  entry     {mot: the word as the script writes it, dire: how ElevenLabs must read it (a spelling with tashkeel, or
            any spelling that sounds right), langue, note}; Réglages → Bibliothèques → Prononciation
  apply     before a narration goes to ElevenLabs, each WHOLE word of the list (punctuation around it kept) is replaced
            by its « dire » — never a piece of a word, never another word; nothing else in the text changes
  restore   the word timings come back on the replaced spelling: each is given its written word again, so the captions,
            the script and the banners never show the « dire » spelling
A wrong entry is undone by deleting it: the next narration goes back to the plain word. The diacritics stay limited
to the listed words (the user keeps the Arabic narration without tashkeel: +30-50 % slower with it everywhere).
"""

import json
import os
import re
import time
from typing import Callable, Dict, List, Optional, Tuple

FILE = "prononciation.json"                  # in the data folder (the app's working directory)
PUNCT = "،؛؟.,!?;:«»\"'()[]…-"  # around a word: kept where it is


def entries() -> List[Dict]:
    """The listed words; [] only when there is no file yet. A file that can't be read (the Windows disk busy, a write
    half done) is read again 3 times, then refused: before 2026-11-13 it counted as empty, and the next add() wrote
    the file back with that one word — the dictionary lost every other word (and a narration whose signature
    suddenly read « [] » would have been paid again)."""
    for k in range(4):
        try:
            with open(FILE, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("pas une liste")
            return [e for e in data if isinstance(e, dict) and e.get("mot") and e.get("dire")]
        except FileNotFoundError:
            return []
        except (OSError, ValueError) as e:
            if k == 3:
                raise ValueError(f"Le dictionnaire de prononciation ({FILE}) ne se lit pas ({str(e)[:80]}) : "
                                 "rien n'a été changé, réessaie dans un instant.")
            time.sleep(0.2 * (k + 1))
    return []


def _save(data: List[Dict]) -> None:
    tmp = FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, FILE)


def _clean_word(x: str) -> str:
    return " ".join(str(x or "").split())[:60]


def add(mot: str, dire: str, langue: str = "ar", note: str = "") -> Dict:
    """Adds (or replaces) a word's reading. One word only for « mot » (as written in the scripts)."""
    mot, dire = _clean_word(mot).strip(PUNCT), _clean_word(dire).strip(PUNCT)
    if not mot or not dire:
        raise ValueError("Il faut le mot et la façon de le dire.")
    if " " in mot:
        raise ValueError("Un seul mot à la fois (tel qu'il est écrit dans le script, avec و / ف / ال s'ils sont collés).")
    if mot == dire:
        raise ValueError("La façon de le dire doit être différente du mot.")
    data = [e for e in entries() if not (e["mot"] == mot and e.get("langue", "ar") == langue)]
    e = {"mot": mot, "dire": dire, "langue": langue or "ar", "note": _clean_word(note)}
    data.append(e)
    _save(sorted(data, key=lambda x: (x.get("langue", ""), x["mot"])))
    return e


def remove(mot: str, langue: str = "ar") -> None:
    data = entries()
    left = [e for e in data if not (e["mot"] == mot and e.get("langue", "ar") == langue)]
    if len(left) == len(data):
        raise ValueError("Mot introuvable dans le dictionnaire.")
    _save(left)


def table(lang: str) -> Dict[str, str]:
    code = (lang or "").split("-")[0]
    return {e["mot"]: e["dire"] for e in entries() if e.get("langue", "ar") == code}


def _split(token: str) -> Tuple[str, str, str]:
    """« (المعلمة، » -> ("(", "المعلمة", "،")."""
    a = len(token) - len(token.lstrip(PUNCT))
    b = len(token.rstrip(PUNCT))
    return token[:a], token[a:b], token[b:]


def apply(text: str, lang: str, words: Optional[Dict[str, str]] = None,
          other: Optional[Callable[[str], Optional[str]]] = None) -> Tuple[str, List[int]]:
    """The text ElevenLabs reads, and for each written word how many spoken words it became (to give the timings
    back to the written words). Only whole listed words change — and, with « other », the words it gives a reading
    (adaptation/nombres_darija: a darija narration's numbers in words)."""
    words = table(lang) if words is None else words
    out, sizes = [], []
    for token in text.split():
        pre, core, post = _split(token)
        said = words.get(core) or (other(core) if other and core else None)
        if said:
            parts = (pre + said + post).split()
            out.extend(parts)
            sizes.append(len(parts))
        else:
            out.append(token)
            sizes.append(1)
    return " ".join(out), sizes


def restore(v: Dict, written: List[str], sizes: List[List[int]]) -> Dict:
    """The narration's word timings (on the spoken text) given back to the written words: a written word said as
    several words takes the first one's start and the last one's end."""
    words, passages, k = [], [], 0
    for ps, text, sz in zip(v["passages"], written, sizes):
        tokens = text.split()
        spoken = ps["words"]
        if len(spoken) != sum(sz) or len(tokens) != len(sz):     # ElevenLabs split words its own way: as they are
            idx = []
            for i in spoken:
                words.append(v["words"][i])
                idx.append(len(words) - 1)
            passages.append({**ps, "words": idx})
            continue
        idx, j = [], 0
        for tok, n in zip(tokens, sz):
            group = [v["words"][i] for i in spoken[j:j + n]]
            j += n
            words.append({**group[0], "w": tok, "end": group[-1]["end"]})
            idx.append(len(words) - 1)
        passages.append({**ps, "words": idx})
    return {**v, "words": words, "passages": passages}


def signature(lang: str) -> str:
    """Changes when the dictionary of this language changes: a narration made before is said again."""
    return json.dumps(sorted(table(lang).items()), ensure_ascii=False)
