"""
The voice « casting » (user's idea, 2026-11-07) — like the music's: the person prepares, the AI picks for each
video, the person can change.

  voices     every voice of the library has tones (posée, énergique, dramatique…) proposed by the AI from
             ElevenLabs' own labels, corrected by the person (who wins), an optional mark out of 10 (Ghalia got 8 on
             Moroccan place names) and its reputation (how many people use it, ElevenLabs' public numbers)
  channel    its main voice ★ (the one set in Réglages), the other voices it allows, and a mode: always the main
             one, or the AI may change when the subject asks for it. A channel speaking darija only gets Moroccan voices.
  video      once the script is written, the AI picks the voice (the main one unless it has a real reason, said)
             and the MANNER of each sentence, given to ElevenLabs v4 as an audio tag ([serious], [whispers]…) —
             measured 2026-11-07: v4 follows the tags and never says them, ignores the speed and barely hears
             stability/style; v3 the other way round. Both are shown on the script screen, changed there or at the
             preview (another voice: the voice and the cuts are made again).
"""

import json
import re
from typing import Dict, List, Optional

TONS = {"posee": "Posée", "energique": "Énergique", "dramatique": "Dramatique", "douce": "Douce",
        "chaleureuse": "Chaleureuse", "jeune": "Jeune", "autoritaire": "Autoritaire", "drole": "Drôle"}
# the manner of a sentence -> the ElevenLabs v4 audio tag put before it ("" = said plainly)
MANIERES = {"": ("Normale", ""), "calme": ("Calme", "[calm]"), "serieux": ("Sérieux", "[serious]"),
            "chuchote": ("Chuchoté", "[whispers]"), "excite": ("Excité", "[excited]"),
            "curieux": ("Curieux", "[curious]"), "triste": ("Triste", "[sad]")}
MODES = ("auto", "principale")
TAG = re.compile(r"^\[[a-z ]+\]$")

CLASSIFY = """Voici des voix ElevenLabs (id | nom | genre | age | accent | usage | description). Pour chacune, donne 1 a 3 tons
parmi {tons} — ce qu'elle porte vraiment, d'apres son nom et sa description.
{voix}
JSON uniquement : {{"voix": [{{"id": "", "tons": [""]}}]}}"""

CAST = """Tu es le directeur de casting d'un YouTube Short (voix off). Le script, phrase par phrase :
{phrases}
Style de recit : {recit}. Ton de la video : {ton}.
Voix possibles (★ = la voix principale de la chaine, sa signature) :
{voix}
1. "voix" : {regle_voix}
2. "manieres" : pour CHAQUE phrase, la maniere de la dire parmi {manieres} ("" = normale). Peu de changements : la
   plupart des phrases normales ; une accroche serieuse ou curieuse, une revelation chuchotee, une chute excitee
   ou triste quand le texte le demande vraiment.
JSON uniquement : {{"voix": "id", "pourquoi": "une phrase", "manieres": [""]}}"""


def tons_of(v: Dict) -> List[str]:
    """The person's tones when set, else the AI's."""
    return list(v["tons"]) if isinstance(v.get("tons"), list) else list(v.get("tons_ia") or [])


def card(v: Dict) -> Dict:
    """What the casting (and the screens) know of a voice."""
    from adaptation import settings
    rep = v.get("reputation") or {}
    return {"voice_id": v["voice_id"], "nom": settings.display_name(v), "langue": v.get("language"),
            "accent": v.get("accent"), "genre": v.get("gender"), "age": v.get("age"), "usage": v.get("use_case"),
            "tons": tons_of(v), "tons_par": "toi" if isinstance(v.get("tons"), list) else ("ia" if v.get("tons_ia") else None),
            "note": v.get("note"), "ajoutee_par": rep.get("ajoutee_par"), "lu_1an": rep.get("lu_1an"),
            "lu_7j": rep.get("lu_7j"), "type": rep.get("type")}


def set_tags(voice_id: str, tons: Optional[List[str]] = None, note: Optional[int] = None,
             clear_note: bool = False) -> Optional[Dict]:
    import db
    v = db.get_voice(voice_id)
    if not v:
        return None
    if tons is not None:
        v["tons"] = [t for t in dict.fromkeys(tons) if t in TONS]
    if note is not None:
        v["note"] = max(1, min(10, int(note)))
    if clear_note:
        v.pop("note", None)
    db.upsert_voice({k: x for k, x in v.items() if k != "added_at"})
    return db.get_voice(voice_id)


def reputation(voice_id: str) -> Optional[Dict]:
    """ElevenLabs' public numbers for a voice of its library (None when not found there)."""
    import requests
    from adaptation import voices as el
    r = requests.get(f"{el.API}/v1/shared-voices", headers={"xi-api-key": el._key()},
                     params={"search": voice_id, "page_size": 5}, timeout=30)
    for x in (r.json().get("voices") or []) if r.status_code == 200 else []:
        if x.get("voice_id") == voice_id:
            return {"ajoutee_par": x.get("cloned_by_count"), "lu_1an": x.get("usage_character_count_1y"),
                    "lu_7j": x.get("usage_character_count_7d"),
                    "type": "pro" if x.get("category") == "professional" else "hq" if x.get("category") == "high_quality" else x.get("category")}
    return None


def classify(voices: List[Dict], gemini=None) -> Dict[str, List[str]]:
    """{voice_id: tones} proposed by the AI from ElevenLabs' labels (one call for all of them)."""
    if not voices:
        return {}
    from adaptation.script import _gemini
    lines = "\n".join(f"{v['voice_id']} | {v.get('name')} | {v.get('gender')} | {v.get('age')} | {v.get('accent')} | "
                      f"{v.get('use_case')} | {(v.get('description') or '')[:160]}" for v in voices)
    try:
        r = (gemini or _gemini())._generate_content([{"text": CLASSIFY.format(tons=", ".join(TONS), voix=lines)}],
                                                    max_tokens=6000, timeout=120, temperature=0.1)
    except Exception:
        return {}
    return {str(x.get("id")): [t for t in x.get("tons") or [] if t in TONS][:3]
            for x in (r or {}).get("voix") or [] if isinstance(x, dict)}


def enrich(voice_ids: Optional[List[str]] = None, gemini=None) -> int:
    """Tones (AI) and reputation for the voices that miss them; returns how many were updated."""
    import db
    todo = [v for v in db.list_voices() if (voice_ids is None or v["voice_id"] in voice_ids)
            and (not v.get("tons_ia") or not v.get("reputation"))]
    tones = classify([v for v in todo if not v.get("tons_ia")], gemini)
    for v in todo:
        if v["voice_id"] in tones:
            v["tons_ia"] = tones[v["voice_id"]]
        if not v.get("reputation"):
            try:
                v["reputation"] = reputation(v["voice_id"]) or {}
            except Exception:
                pass
        db.upsert_voice({k: x for k, x in v.items() if k != "added_at"})
    return len(todo)


# ---------------------------------------------------------------- a channel's voices

def eligible(language: str, main: Optional[str], allowed: List[str], dialect: Optional[str]) -> List[Dict]:
    """The voices a channel may use: its main one and the allowed ones, of its language (Moroccan voices only for
    a channel speaking darija; its main one always stays)."""
    import db
    out = []
    for v in db.list_voices(language):
        if v["voice_id"] != main and v["voice_id"] not in (allowed or []):
            continue
        if dialect == "darija" and v["voice_id"] != main and (v.get("accent") or "") != "moroccan":
            continue
        out.append(v)
    out.sort(key=lambda v: v["voice_id"] != main)        # the main one first
    return out


def rules_of(channel: str) -> Dict:
    from channel_manager import ChannelManager
    from adaptation import settings
    s = settings.channel_settings(ChannelManager().get_channel_profile(channel))
    return {"main": s["voice_id"], "allowed": s["voix_permises"], "mode": s["voix_mode"], "dialect": s.get("dialecte"),
            "language": s["language"]}


def cast(p: Dict, t: Dict, gemini=None) -> None:
    """The voice and each sentence's manner for one version, written into it — the person's choices are kept."""
    from adaptation import pipeline as ap
    sc = t.get("script") or {}
    passages = sc.get("passages") or []
    if not passages:
        return
    try:
        rules = rules_of(t["channel"])
    except Exception:
        rules = {"main": t.get("voice_id"), "allowed": [], "mode": "principale", "dialect": t.get("dialecte"),
                 "language": t["language"]}
    main = rules["main"] or t.get("voice_id")
    pool = eligible(t["language"], main, rules["allowed"], rules["dialect"])
    choose_voice = t.get("voice_by") != "toi" and rules["mode"] == "auto" and len(pool) > 1
    if t.get("voice_by") != "toi" and not choose_voice:
        t.update(voice_id=main, voice_by="principale",
                 voice_why="la voix principale de la chaîne" + (" (toujours elle)" if rules["mode"] == "principale" else ""))
    if not choose_voice and t.get("manieres_by") == "toi":
        return
    from adaptation.script import _gemini
    listing = "\n".join(f"{'★ ' if v['voice_id'] == main else ''}{v['voice_id']} | {card(v)['nom']} | {v.get('gender')} | "
                        f"{v.get('age')} | {v.get('accent')} | tons : {', '.join(tons_of(v)) or '?'}"
                        f"{' | ta note ' + str(v['note']) + '/10' if v.get('note') else ''}" for v in pool)
    regle = ("garde la voix ★ SAUF si le sujet demande vraiment une autre voix (une histoire racontee par une femme, "
             "un ton que la ★ ne sait pas porter) : dis pourquoi." if choose_voice else
             f"c'est forcement {main} (la chaine garde sa voix).")
    try:
        r = (gemini or _gemini())._generate_content([{"text": CAST.format(
            phrases="\n".join(f"{k}. {x.get('texte')}" for k, x in enumerate(passages, 1)), recit=p.get("recit") or "-",
            ton=ap._tone(p, t), voix=listing or "-", regle_voix=regle,
            manieres=", ".join(f'"{k}"' for k in MANIERES if k))}], max_tokens=3000, timeout=90, temperature=0.3)
    except Exception:
        r = {}
    r = r if isinstance(r, dict) else {}
    if choose_voice:
        pick = str(r.get("voix") or "")
        ok = pick in {v["voice_id"] for v in pool}
        t.update(voice_id=pick if ok else main, voice_by="ia" if ok and pick != main else "principale",
                 voice_why=str(r.get("pourquoi") or "")[:240] if ok and pick != main else "la voix principale de la chaîne")
    if t.get("manieres_by") != "toi":
        got = [m if m in MANIERES else "" for m in (r.get("manieres") or [])]
        t["manieres"] = (got + [""] * len(passages))[:len(passages)]
        t["manieres_by"] = "ia"


def set_casting(pid: str, channel: str, voice_id: Optional[str] = None, manieres: Optional[List[str]] = None) -> Dict:
    """The person's choice on the script screen: another voice (one of the channel's) and/or the sentences' manners."""
    from adaptation import pipeline as ap
    p = ap.load(pid)
    ap._expect(p, "plan_review", "stock_review", "preview_review")
    t = ap.target(p, channel)
    if voice_id is not None:
        import db
        v = db.get_voice(voice_id)
        if not v or (v.get("language") or "").split("-")[0] != t["language"]:
            raise ap.PipelineError("Cette voix n'est pas de la langue de la chaîne.")
        if voice_id != t.get("voice_id"):
            t.update(voice_id=voice_id, voice=None, voice_by="toi", voice_why="choisie par toi", validated=False)
    if manieres is not None:
        n = len((t.get("script") or {}).get("passages") or [])
        t["manieres"] = ([m if m in MANIERES else "" for m in manieres] + [""] * n)[:n]
        t["manieres_by"] = "toi"
    return ap.save(p)


# ---------------------------------------------------------------- the narration with its manners

def tagged(texte: str, maniere: Optional[str]) -> str:
    tag = MANIERES.get(maniere or "", ("", ""))[1]
    return f"{tag} {texte}" if tag else texte


def strip_tags(v: Dict, clean_texts: List[str]) -> Dict:
    """The tags were said to ElevenLabs, never shown: their 'words' leave the timings and the captions."""
    keep = [i for i, w in enumerate(v["words"]) if not TAG.match(w["w"].lower())]
    new_index = {old: k for k, old in enumerate(keep)}
    words = [v["words"][i] for i in keep]
    passages = []
    for ps, texte in zip(v["passages"], clean_texts):
        idx = [new_index[i] for i in ps["words"] if i in new_index]
        q = {**ps, "texte": texte, "words": idx}
        if idx:
            q["start"] = words[idx[0]]["start"]
        passages.append(q)
    return {**v, "words": words, "passages": passages}
