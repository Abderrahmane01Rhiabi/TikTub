"""
The channels whose videos are never used (Réglages → Bibliothèques → Chaînes à éviter). The user, 2026-11-13: an
explainer channel (« عين على مشاريع الغد ») showed AI-made pictures of the Kenitra–Marrakech works as if they were the
real site — neither the free model, nor the speech, nor a blind vote by eye caught it.

  entry     {nom: the channel's name as YouTube shows it, note}; compared without case, accents nor spaces
  drop      takes their videos out of a search's candidates (finder.suggest's result) before any check is paid
"""

import json
import os
import re
import time
import unicodedata
from typing import Dict, List

FILE = "chaines_evitees.json"            # in the data folder (the app's working directory)
DEFAULT = [{"nom": "عين على مشاريع الغد", "note": "images générées par IA présentées comme le vrai chantier (13/11)"}]


def _key(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name or "")).lower()
    s = "".join(c for c in s if not unicodedata.combining(c) or "؀" <= c <= "ۿ")
    return re.sub(r"[\W_]+", "", s)


def entries() -> List[Dict]:
    """The list; the default one when there is no file yet. A file that can't be read is read again, then refused
    (never taken for empty: the list would be rewritten with one channel)."""
    for k in range(4):
        try:
            with open(FILE, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("pas une liste")
            return [e for e in data if isinstance(e, dict) and str(e.get("nom") or "").strip()]
        except FileNotFoundError:
            return [dict(e) for e in DEFAULT]
        except (OSError, ValueError) as e:
            if k == 3:
                raise ValueError(f"La liste des chaînes à éviter ({FILE}) ne se lit pas ({str(e)[:80]}) : "
                                 "rien n'a été changé, réessaie dans un instant.")
            time.sleep(0.2 * (k + 1))
    return []


def _save(data: List[Dict]) -> None:
    tmp = FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, FILE)


def add(nom: str, note: str = "") -> List[Dict]:
    nom = " ".join(str(nom or "").split())[:120]
    if not _key(nom):
        raise ValueError("Écris le nom de la chaîne, tel que YouTube l'affiche.")
    data = [e for e in entries() if _key(e["nom"]) != _key(nom)]
    data.append({"nom": nom, "note": " ".join(str(note or "").split())[:200]})
    _save(data)
    return data


def remove(nom: str) -> List[Dict]:
    data = entries()
    left = [e for e in data if _key(e["nom"]) != _key(nom)]
    if len(left) == len(data):
        raise ValueError("Chaîne introuvable dans la liste.")
    _save(left)
    return left


def avoided(channel: str, names=None) -> bool:
    keys = {_key(e["nom"]) for e in (entries() if names is None else names)}
    return bool(channel) and _key(channel) in keys


def drop(sug: Dict) -> List[str]:
    """Takes the avoided channels' videos out of every scene's candidates (and the credited accounts' videos);
    returns the urls taken out (noted in sug["evitees"])."""
    names = entries()
    gone = []
    for s in sug.get("scenes") or []:
        keep = []
        for c in s.get("candidats") or []:
            (gone.append(c["url"]) if avoided(c.get("channel"), names) else keep.append(c))
        s["candidats"] = keep
    for a in sug.get("comptes") or []:
        vids = a.get("videos") or []
        a["videos"] = [v for v in vids if not avoided(v.get("channel"), names)]
        gone += [v["url"] for v in vids if avoided(v.get("channel"), names)]
    for u in set(gone):                                 # a check kept from an earlier run: not used either
        (sug.get("verifs") or {}).pop(u, None)
    if gone:
        sug["evitees"] = sorted(set(gone) | set(sug.get("evitees") or []))
    return sorted(set(gone))
