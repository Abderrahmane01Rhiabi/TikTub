"""
A « Discours » project (mode "discours" of adaptation/pipeline.py), step by step:

    analysing        the speech downloaded whole, its words (faster-whisper, this PC), Gemini's 2-3 strongest passages
    passage_review   the person picks a passage and may move its first / last word; or asks for other passages
    searching        the passage cut, its pauses tightened (Demucs voice), the cut-away moments (Gemini), each one's
                     video found and watched (finder.check, strict), its extracts downloaded; the captions translated
                     into every language of the channels, with the YouTube texts                         (background)
    plans_review     the person sees each cut-away: keeps it, takes it out, or gives a link (and its second) or a file
    voicing          per channel: the video made (the speaker, the cut-aways, the captions in its language, the
                     sound chosen) — no AI, except the smart music chosen once                         (background)
    preview_review   the person watches, may change the settings (frame, captions, sound…): made again, no AI;
                     validates
    rendering        the validated videos join Publication, with the speaker's name in the credits    (background)
    done

The settings, in 3 layers: the « style Discours » (discours.DEFAULTS), the channel's (profile["discours"], Réglages →
Discours, with whether its cut-aways may be films), the video's (p["discours"]["reglages"], the preview panel).
The sound, for every channel: "intelligente" (a song of the shared list chosen by Gemini, its rise on the punchline —
every channel here, the person's choice 2026-11-04), "choisie" (a shared song the person picked, its rise on the
punchline), "notre_musique" (the channel's track), "sans_musique".
"""

import json
import os
import shutil
from datetime import datetime
from typing import Callable, Dict, List, Optional

from adaptation import discours as D, langs, musique
from adaptation.pipeline import PipelineError

Report = Callable[[str, float], None]

SONS = ("intelligente", "choisie", "notre_musique", "sans_musique")
SHARED_MUSIC = os.path.join("assets", "musiques")


class DiscoursPipelineError(PipelineError):
    pass


def _ap():
    from adaptation import pipeline
    return pipeline


def work_dir(p: Dict, *parts: str) -> str:
    d = os.path.join(_ap().project_dir(p["project_id"]), *parts)
    os.makedirs(d, exist_ok=True)
    return d


def _codes(p: Dict) -> List[str]:
    out: List[str] = []
    for t in p["targets"]:
        c = langs.lang(t["language"])["code"]
        if c not in out:
            out.append(c)
    return out


def settings_for(p: Dict, t: Dict) -> Dict:
    """The channel's « style Discours » under the video's own settings."""
    return D.clean_settings(p["discours"].get("reglages") or {}, base=D.clean_settings(t.get("discours") or {}))


def films_ok(p: Dict) -> bool:
    """The cut-aways may be films only when every channel of the project allows them."""
    return all((t.get("discours") or {}).get("films") is True for t in p["targets"])


def son_for(p: Dict, t: Dict) -> str:
    d = p["discours"]
    son = d.get("son") or "intelligente"
    if son == "choisie" and not (d.get("chanson") and os.path.exists(os.path.join(SHARED_MUSIC, d["chanson"]))):
        son = "intelligente"
    if son == "notre_musique" and not t.get("music_path"):
        son = "sans_musique"
    return son


# ---------------------------------------------------------------- creation

def new_project(base: Dict, targets: List[Dict], son: str = "intelligente", chanson: Optional[str] = None,
                duree: int = 45) -> Dict:
    if not base.get("reference_url"):
        raise DiscoursPipelineError("Il faut le lien de la vidéo du discours.")
    if son not in SONS:
        raise DiscoursPipelineError("Choix du son inconnu.")
    if son == "choisie" and not (chanson and os.path.exists(os.path.join(SHARED_MUSIC, os.path.basename(chanson)))):
        raise DiscoursPipelineError("Choisis la musique dans la liste.")
    return {**base, "mode": "discours", "source_urls": [], "targets": targets,
            "discours": {"son": son, "chanson": os.path.basename(chanson) if chanson else None,
                         "duree": duree if duree in D.DURATIONS else 45, "video": None, "titre_video": "",
                         "langue": None, "mots": None, "orateur": "", "passages": None, "choix": None,
                         "segment": None, "parts": None, "local": None, "moments": None, "mots_forts": [],
                         "mot_fort": None, "traduction": None, "musique": None, "reglages": {}, "journal": []}}


# ---------------------------------------------------------------- analysing -> passage_review

def run_analysis(pid: str, report: Optional[Report] = None):
    ap = _ap()
    report = report or (lambda phase, f: None)
    p = ap.load(pid)
    try:
        d = p["discours"]
        from adaptation import sources
        if not d.get("video") or not os.path.exists(d["video"]):
            report("téléchargement de la vidéo", 0.02)
            d["video"] = sources.download(p["reference_url"], work_dir(p, "src"), "discours")
            d["titre_video"] = (sources.source_meta(d["video"]) or {}).get("title") or ""
            ap.save(p)
        if not d.get("mots"):
            report("transcription (sur ce PC)", 0.15)
            d["mots"], d["langue"] = D.transcribe(d["video"])
            ap.save(p)
        if not d.get("passages"):
            report("choix des passages forts", 0.8)
            r = D.passages(d["mots"], d["duree"], title=d.get("titre_video") or "")
            d.update(orateur=r["orateur"], passages=r["passages"], choix=dict(r["passages"][0]))
        p.update(status="passage_review", error=None, failed_step=None)
        ap.save(p)
    except Exception as e:
        ap.fail(pid, "analysing", e)
    report("terminé", 1.0)


def choose_passage(pid: str, index: int, i0: Optional[int] = None, i1: Optional[int] = None,
                   orateur: Optional[str] = None) -> Dict:
    """The passage kept, its first and last word moved by the person (word indices of the whole transcript)."""
    ap = _ap()
    p = ap.load(pid)
    ap._expect(p, "passage_review")
    d = p["discours"]
    if not 0 <= index < len(d["passages"] or []):
        raise DiscoursPipelineError("Passage inconnu.")
    c = dict(d["passages"][index], index=index)
    n = len(d["mots"])
    if i0 is not None:
        c["i0"] = max(0, min(n - 1, int(i0)))
    if i1 is not None:
        c["i1"] = max(0, min(n - 1, int(i1)))
    if c["i1"] - c["i0"] < 5:
        raise DiscoursPipelineError("Le passage est trop court.")
    c["debut"], c["fin"] = D.span(d["mots"], c["i0"], c["i1"])
    if c["fin"] - c["debut"] > 150:
        raise DiscoursPipelineError("Le passage dépasse 2 min 30 : un Short dure au plus 3 min, avec ses pauses.")
    d["choix"] = c
    if orateur is not None:
        d["orateur"] = " ".join(orateur.split())[:80]
    return ap.save(p)


def more_passages(pid: str) -> Dict:
    """« Chercher d'autres passages »: Gemini proposes others (the ones seen are not proposed again)."""
    ap = _ap()
    p = ap.load(pid)
    ap._expect(p, "passage_review")
    d = p["discours"]
    r = D.passages(d["mots"], d["duree"], title=d.get("titre_video") or "", avoid=d["passages"])
    d["passages"] = d["passages"] + r["passages"]
    return ap.save(p)


def approve_passage(pid: str) -> Dict:
    ap = _ap()
    p = ap.load(pid)
    ap._expect(p, "passage_review")
    if not p["discours"].get("choix"):
        raise DiscoursPipelineError("Choisis un passage.")
    p["discours"].update(segment=None, parts=None, local=None, moments=None, traduction=None, musique=None)
    p["status"] = "searching"
    return ap.save(p)


# ---------------------------------------------------------------- searching -> plans_review

def prepare(p: Dict, report: Report) -> None:
    """The passage cut, its words on its own time, its pauses found (kept: the setting « pauses » uses them)."""
    d = p["discours"]
    c = d["choix"]
    seg = os.path.join(work_dir(p, "passage"), "passage.mp4")
    report("découpe du passage", 0.03)
    D.cut_passage(d["video"], c["debut"], c["fin"], seg)
    total = D.duration(seg)
    d["local"] = [[w, round(s - c["debut"], 3), round(e - c["debut"], 3)] for w, s, e in d["mots"][c["i0"]:c["i1"] + 1]]
    report("voix séparée (carte graphique)", 0.06)
    from roblox import voix
    vocals = voix.separate(seg, work_dir(p, "passage", "demucs"))["voix"]
    d.update(segment=seg, total=round(total, 3), parts=D.tightened(vocals, total))


def run_search(pid: str, report: Optional[Report] = None):
    ap = _ap()
    report = report or (lambda phase, f: None)
    p = ap.load(pid)
    try:
        d = p["discours"]
        if not d.get("segment") or not os.path.exists(d["segment"]):
            prepare(p, report)
            ap.save(p)
        speech = sum(b - a for a, b in d["parts"])
        density = settings_for(p, p["targets"][0])["densite"]
        if not d.get("moments"):
            report("moments d'illustration", 0.12)
            m = D.moments(d["local"], speech, films_ok(p), density, d.get("orateur") or "")
            d.update(moments=m["moments"], mots_forts=m["mots_forts"], mot_fort=m["mot_fort"])
            ap.save(p)
        if not d.get("traduction"):
            report("sous-titres traduits", 0.18)
            d["traduction"] = D.translate(d["local"], d.get("langue") or "en", _codes(p), d.get("orateur") or "")
            ap.save(p)
        from adaptation import finder
        used = {finder.same_video(c["url"]) for c in (m.get("clip") for m in d["moments"]) if c and c.get("url")}
        stock_used = stock_used_by(p)
        todo = [m for m in d["moments"] if "clip" not in m]
        missing = [m for m in todo if not m.get("ambiance")]
        if missing:                                  # a project made before the mood shots
            for m, q in zip(missing, D.ambiance_for(missing)):
                m["ambiance"] = q
        for k, m in enumerate(todo):
            report(f"plans de coupe ({k + 1}/{len(todo)})", 0.22 + 0.75 * k / max(1, len(todo)))
            log: List[str] = []
            got = None
            if m.get("type") != "ambiance":          # a person, a place, an event: shown, found on YouTube and watched
                got = D.find_clip(m, films_ok(p), used, work_dir(p, "plans"), exclude=p["reference_url"], log=log)
            if not got:                              # an idea, an emotion, or nothing found: a mood shot (Pixabay)
                try:
                    m["propositions"] = D.stock_search(m.get("ambiance") or "", stock_used)
                    got = D.stock_clip(m.get("ambiance") or "", stock_used, work_dir(p, "plans"),
                                       candidates=m["propositions"])
                except Exception as e:
                    log.append(f"✗ Pixabay : {str(e)[:80]}")
                if got:
                    log.append(f"✓ plan d'ambiance « {m.get('ambiance')} »")
            m.update(clip=got, action="garder" if got else "retirer", journal=log[-4:])
            if got and got.get("stock"):
                stock_used.add(got["stock"])
            elif got:
                used.add(finder.same_video(got["url"]))
            ap.save(p)
        p.update(status="plans_review", error=None, failed_step=None)
        ap.save(p)
    except Exception as e:
        ap.fail(pid, "searching", e)
    report("terminé", 1.0)


def stock_used_by(p: Dict) -> set:
    """The mood shots not to take again: those any channel of the project used (broll_usage, like the drones: the
    same shot again and again reads as repetitive content), and those already in this project."""
    import db
    out = {(m.get("clip") or {}).get("stock") for m in p["discours"].get("moments") or []}
    for t in p["targets"]:
        out |= set(db.broll_last_used(t["channel"]))
    return {x for x in out if x}


def set_moment(pid: str, index: int, action: str) -> Dict:
    ap = _ap()
    p = ap.load(pid)
    ap._expect(p, "plans_review", "preview_review")
    ms = p["discours"]["moments"]
    if not 0 <= index < len(ms) or action not in ("garder", "retirer"):
        raise DiscoursPipelineError("Plan ou choix inconnu.")
    if action == "garder" and not ms[index].get("clip"):
        raise DiscoursPipelineError("Ce plan n'a pas d'image : donne un lien ou un fichier.")
    ms[index]["action"] = action
    if p["status"] == "preview_review":
        _again(p)
    return ap.save(p)


def link_moment(pid: str, index: int, url: str, start: float = 0.0) -> Dict:
    """The person's own image for this moment: a link (and the second it starts at) or a dropped file — taken as it
    is, not checked."""
    ap = _ap()
    p = ap.load(pid)
    ap._expect(p, "plans_review", "preview_review")
    ms = p["discours"]["moments"]
    if not 0 <= index < len(ms):
        raise DiscoursPipelineError("Plan inconnu.")
    url = (url or "").strip()
    if not url:
        raise DiscoursPipelineError("Il faut un lien ou un fichier.")
    from adaptation import sources
    a = max(0.0, float(start or 0))
    try:
        path = sources.download(url, work_dir(p, "plans"), f"lien_{index}_{int(a * 10)}", sections=[[a, a + D.CLIP_LEN]])
    except Exception as e:
        raise DiscoursPipelineError(f"Téléchargement impossible : {str(e)[:200]}")
    ms[index].update(clip={"url": url, "titre": (sources.source_meta(path) or {}).get("title") or url, "niveau": "choisi",
                           "film": False, "extraits": [{"path": path, "debut": a}], "a_la_main": True},
                     action="garder")
    if p["status"] == "preview_review":
        _again(p)
    return ap.save(p)


def _moment(p: Dict, index: int) -> Dict:
    _ap()._expect(p, "plans_review", "preview_review")
    ms = p["discours"]["moments"]
    if not 0 <= index < len(ms):
        raise DiscoursPipelineError("Plan inconnu.")
    return ms[index]


def search_stock(pid: str, index: int, query: str) -> Dict:
    """« Chercher sur Pixabay » for one moment, with the person's own words: new propositions, the shot unchanged."""
    ap = _ap()
    p = ap.load(pid)
    m = _moment(p, index)
    query = (query or "").strip()
    if not query:
        raise DiscoursPipelineError("Écris ce qu'on doit voir (en anglais, c'est mieux).")
    try:
        found = D.stock_search(query, stock_used_by(p))
    except Exception as e:
        raise DiscoursPipelineError(f"Pixabay ne répond pas : {str(e)[:150]}")
    if not found:
        raise DiscoursPipelineError(f"Rien de neuf sur Pixabay pour « {query} » : essaie d'autres mots.")
    m.update(ambiance=query, propositions=found)
    return ap.save(p)


def pick_stock(pid: str, index: int, stock: str) -> Dict:
    """One of the moment's Pixabay propositions taken instead of its shot."""
    ap = _ap()
    p = ap.load(pid)
    m = _moment(p, index)
    cand = next((c for c in m.get("propositions") or [] if c["stock"] == stock), None)
    if not cand:
        raise DiscoursPipelineError("Proposition inconnue : relance la recherche.")
    try:
        clip = D.stock_take(cand, m.get("ambiance") or "", work_dir(p, "plans"))
    except Exception as e:
        raise DiscoursPipelineError(f"Téléchargement impossible : {str(e)[:200]}")
    m.update(clip=clip, action="garder")
    if p["status"] == "preview_review":
        _again(p)
    return ap.save(p)


def move_moment(pid: str, index: int, word: int) -> Dict:
    """A shot moved onto another word of the passage (the timeline): the moments kept in the speech's order."""
    ap = _ap()
    p = ap.load(pid)
    m = _moment(p, index)
    local = p["discours"]["local"]
    if not 0 <= word < len(local):
        raise DiscoursPipelineError("Mot inconnu.")
    m.update(mot=local[word][0], temps=local[word][1])
    p["discours"]["moments"].sort(key=lambda x: float(x["temps"]))
    if p["status"] == "preview_review":
        _again(p)
    return ap.save(p)


def frise(p: Dict) -> Optional[Dict]:
    """The timeline as the video will have it (pauses cut, the 1st target's settings): the words (with their passage
    time, for the player), the speaker's blocks between the cut-aways ({start, end, "source": the passage time
    of its image}), the cut-aways ({"index" of the moment, start, end}), the moments taken out, where the music rises."""
    d = p["discours"]
    if not d.get("local") or not d.get("parts") or not d.get("moments"):
        return None
    s = settings_for(p, p["targets"][0])
    parts = timeline(p, s)
    total = round(sum(b - a for a, b in parts), 3)
    hit = _hit(p, parts, total, s)
    anchors, off = [], []
    for i, m in enumerate(d["moments"]):
        t = D.remap(float(m["temps"]), parts)
        n = len((m.get("clip") or {}).get("extraits") or [])
        if m.get("action") == "garder" and n:
            anchors.append((t, [i] * n))
        else:
            off.append({"index": i, "temps": round(t, 3)})
    starts = [D.remap(w[1], parts) for w in d["local"]]
    plans = [{"index": c, "debut": a, "fin": b} for a, b, c, _ in D.shots(anchors, starts, total, hit)]
    speaker, free = [], 0.0
    for b in plans + [{"debut": total, "fin": total}]:
        if b["debut"] - free > 0.05:
            speaker.append({"debut": round(free, 3), "fin": round(b["debut"], 3),
                            "source": round(D.unmap((free + b["debut"]) / 2, parts), 2)})
        free = max(free, b["fin"])
    return {"total": total, "montee": round(hit, 3), "accroche": D.HOOK_S, "parts": parts,
            "mots": [[w[0], round(t, 3), w[1]] for w, t in zip(d["local"], starts)], "plans": plans,
            "orateur": speaker, "retires": off}


def approve_plans(pid: str) -> Dict:
    ap = _ap()
    p = ap.load(pid)
    ap._expect(p, "plans_review")
    p["status"] = "voicing"
    for t in p["targets"]:
        t["validated"] = False
    return ap.save(p)


# ---------------------------------------------------------------- voicing (the videos) -> preview_review

def _hit(p: Dict, parts: List[List[float]], total: float, s: Dict) -> float:
    """Where the music rises: on the punchline's word (« mot fort »), else at DROP_AT of the Short."""
    mf = p["discours"].get("mot_fort")
    if s["drop_punchline"] and mf:
        return max(1.0, min(total - 1.0, D.remap(float(mf["temps"]), parts)))
    return D.DROP_AT * total


def _smart_choice(p: Dict, parts: List[List[float]], total: float, report: Report) -> Dict:
    """The song, chosen once for the project by Gemini among the shared list (musique.plan: it hears the phrases)."""
    d = p["discours"]
    if d.get("musique"):
        return d["musique"]
    phrases = [{"role": "phrase", "numero": None, "texte": " ".join(w[0] for w in d["local"][r["i0"]:r["i1"] + 1]),
                "debut": D.remap(d["local"][r["i0"]][1], parts)} for r in d["traduction"]["phrases"]]
    report("choix de la musique", 0.0)
    d["musique"] = musique.plan(SHARED_MUSIC, d.get("orateur") or "un discours", "inspirant", phrases, total)
    _ap().save(p)
    return d["musique"]


def timeline(p: Dict, s: Optional[Dict] = None) -> List[List[float]]:
    """The parts of the passage kept: its pauses tightened, or all of it (setting « pauses » : gardées)."""
    d = p["discours"]
    if s and s.get("pauses") == "gardees":
        first = d["local"][0][1] if d.get("local") else 0.0
        return [[max(0.0, first - 0.1), d["total"]]]
    return d["parts"]


def bed_for(p: Dict, t: Dict, s: Dict, parts: List[List[float]], total: float, work: str,
            report: Report) -> Optional[str]:
    son = son_for(p, t)
    gap = float(s["volume_db"])
    out = os.path.join(work, f"fond_{son}.wav")
    hit = _hit(p, parts, total, s)
    if son == "sans_musique":
        return None
    if son == "notre_musique":
        return D.song_bed(t["music_path"], hit, total, out, gap, on_rise=s["drop_punchline"])
    if son == "choisie":
        return D.song_bed(os.path.join(SHARED_MUSIC, p["discours"]["chanson"]), hit, total, out, gap,
                          on_rise=s["drop_punchline"])
    choice = dict(_smart_choice(p, parts, total, report))
    song = musique.listen(os.path.join(SHARED_MUSIC, choice["fichier"]))
    choice["montee"], _ = musique.peak_for(song, hit, total, choice["montee"])
    choice["a"] = hit
    return musique.placed_bed(SHARED_MUSIC, choice, total, out, gap=gap)


def plan_of(p: Dict, parts: List[List[float]], total: float, hit: float) -> List:
    anchors = []
    for m in p["discours"]["moments"] or []:
        clip = m.get("clip") or {}
        paths = [x["path"] for x in clip.get("extraits") or [] if os.path.exists(x.get("path") or "")]
        if m.get("action") == "garder" and paths:
            anchors.append((D.remap(float(m["temps"]), parts), paths))
    starts = [D.remap(w[1], parts) for w in p["discours"]["local"]]
    return D.shots(anchors, starts, total, hit)


def make_video(p: Dict, t: Dict, report: Report) -> Dict:
    d = p["discours"]
    code = langs.lang(t["language"])["code"]
    s = settings_for(p, t)
    work = work_dir(p, "cibles", t["channel"])
    parts = timeline(p, s)
    key = ["v1", parts]
    cut = d.get("coupe") or {}
    pic, speech = os.path.join(work_dir(p, "passage"), "orateur.mp4"), os.path.join(work_dir(p, "passage"), "parole.wav")
    if cut.get("key") != key or not (os.path.exists(pic) and os.path.exists(speech)):
        report(f"{t['channel']} : pauses", 0.05)
        D.cut(d["segment"], parts, pic, speech)
        d["coupe"] = {"key": key}
    total = D.duration(speech)
    words = D.caption_words(d["local"], parts, d.get("traduction"), code, d.get("langue") or "en")
    strong = set((d.get("traduction") or {}).get("langues", {}).get(code, {}).get("mots_forts") or []) \
        if code != (d.get("langue") or "en") else set(d.get("mots_forts") or [])
    hit = _hit(p, parts, total, s)
    bed = bed_for(p, t, s, parts, total, work, report)
    out = os.path.join(work, f"discours_{t['channel']}.mp4")
    plan = plan_of(p, parts, total, hit)
    signature = t.get("display_name") or t["channel"]
    from captions import render as caption_render
    music = [bed is not None, t.get("music_path"), d.get("chanson"), d.get("musique"), hit, total]  # the bed itself:
    key = _ap().render_key("v1", pic, speech, plan, words, code, s, music, strong, t["channel"],     # made each time
                           signature, son_for(p, t), D.__file__, caption_render.__file__)
    if _ap().kept_video(t.get("preview"), key):
        return t["preview"]                          # back from the plans, nothing changed: not made again
    report(f"{t['channel']} : montage", 0.4)
    import render_slot
    with render_slot.SLOT:
        D.render(pic, speech, plan, words, code, s, bed, out, os.path.join(work, "travail"),
                 strong=strong, channel=t["channel"], signature=signature)
    made = D.duration(out)
    ok = abs(made - total) < 0.6
    try:                                             # what this montage saw, ready for the live preview
        report(f"{t['channel']} : aperçu direct", 0.95)
        live_seen(p, t["channel"], D.frame_box(s), made_zone=D.frame_box(s))
        live_voice(p)                                # and « Écouter »: the voice, this choice's music
        live_bed(p, t["channel"], son_for(p, t), d.get("chanson"), s["drop_punchline"])
    except Exception as e:
        print(f"⚠️ Analyse pour l'aperçu direct impossible ({e})")
    return {"path": out, "son": son_for(p, t), "duree": round(made, 1), "reglages": s, "mot_fort_a": round(hit, 2),
            "cle": key, "checks": {"ok": ok, "problems": [] if ok else ["La vidéo n'a pas la durée de la parole."]}}


def run_voices(pid: str, report: Optional[Report] = None, only: Optional[str] = None):
    ap = _ap()
    report = report or (lambda phase, f: None)
    p = ap.load(pid)
    try:
        todo = [t for t in p["targets"] if only is None or t["channel"] == only]
        for i, t in enumerate(todo):
            t["preview"] = make_video(p, t, lambda ph, f: report(ph, (i + f) / len(todo)))
            t["validated"] = False
            ap.save(p)
        p.update(status="preview_review", error=None, failed_step=None)
        ap.save(p)
    except Exception as e:
        ap.fail(pid, "voicing", e)
    report("terminé", 1.0)


def _again(p: Dict):
    for t in p["targets"]:
        t["validated"] = False
    p["status"] = "voicing"


LIVE_S = 3.5                         # the live preview's captions: about this long a phrase


def live_words(p: Dict, code: str) -> Optional[tuple]:
    """The live preview's captions: the words in `code` (translated) from the Short's start to the end of a phrase
    said after the speaker's first seconds, its strong words, and when that phrase starts (s). None before the cut."""
    d = p["discours"]
    if not d.get("local") or not d.get("parts"):
        return None
    words = D.caption_words(d["local"], timeline(p, settings_for(p, p["targets"][0])), d.get("traduction"), code,
                            d.get("langue") or "en")
    start = next((k for k, w in enumerate(words) if w[1] >= D.HOOK_S), 0)
    end = start
    while end + 1 < len(words) and words[end + 1][2] - words[start][1] <= LIVE_S:
        end += 1
    tr = (d.get("traduction") or {}).get("langues", {}).get(code, {})
    strong = set(tr.get("mots_forts") or []) if code != (d.get("langue") or "en") else set(d.get("mots_forts") or [])
    return ([list(w) for w in words[:end + 1]], strong, words[start][1]) if words else None


def live_seen(p: Dict, channel: str, zone, made_zone=None) -> Optional[tuple]:
    """What the real montage saw of its frame (the faces, the busy bands), for the live captions: analysed once per
    montage at that montage's size (~20 s, kept beside it), then fitted to `zone` (another size, the same picture
    stretched; `made_zone`: that montage's frame, else its preview's) -> (a key, faces, scene), or None before one."""
    import pickle
    from captions import render as R
    from captions.core import Scene
    work = os.path.join(work_dir(p, "cibles", channel), "travail")
    made, kept = os.path.join(work, "cadre.mp4"), os.path.join(work, "analyse.pkl")
    if not os.path.exists(made):
        return None
    mtime = os.path.getmtime(made)
    got = None
    if os.path.exists(kept):
        try:
            got = pickle.load(open(kept, "rb"))
        except Exception:
            got = None
    if not got or got.get("mtime") != mtime:
        t = next(x for x in p["targets"] if x["channel"] == channel)
        z = tuple(made_zone or D.frame_box((t.get("preview") or {}).get("reglages") or settings_for(p, t)))
        sc = R.scene(made, z, fit="stretch")
        got = {"mtime": mtime, "zone": z, "faces": R.faces(made, z, fit="stretch"),
               "frames": sc.frames if sc else [], "scale": sc.scale if sc else 4}
        pickle.dump(got, open(kept, "wb"))
    (ax, ay, aw, ah), (bx, by, bw, bh) = got["zone"], tuple(zone)
    fx, fy = bw / aw, bh / ah
    faces = [(t, (bx + (x0 - ax) * fx, by + (y0 - ay) * fy, bx + (x1 - ax) * fx, by + (y1 - ay) * fy))
             for t, (x0, y0, x1, y1) in got["faces"]]
    scene = None
    if got["frames"]:
        import cv2
        size = (max(2, bw // got["scale"]), max(2, bh // got["scale"]))
        scene = Scene([(t, cv2.resize(f, size)) for t, f in got["frames"]], tuple(zone), got["scale"])
    return (f"{made}|{mtime}", faces, scene)


LIVE_GAP = 3.0                       # the live listening's music: made this many dB under the voice, lowered by the page


def live_voice(p: Dict) -> Optional[str]:
    """The speech as in the video (its pauses cut, at the montage's level): what « Écouter » plays."""
    speech = os.path.join(work_dir(p, "passage"), "parole.wav")
    if not os.path.exists(speech):
        return None
    out = os.path.join(work_dir(p, "passage"), "ecoute_voix.wav")
    if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(speech):
        D._run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", speech, "-af",
                f"loudnorm=I={D.SPEECH_LUFS}:TP=-1.5:LRA=11,aresample=48000", out])
    return out


def live_bed(p: Dict, channel: str, son: str, chanson: Optional[str], drop: bool) -> Optional[str]:
    """This channel's music for « Écouter », as the montage would place it (its rise on the punchline or not), LIVE_GAP
    dB under the voice; None: no music. Made once per choice. A smart song not chosen yet is never asked for here."""
    import hashlib
    d = p["discours"]
    t = next((x for x in p["targets"] if x["channel"] == channel), None)
    speech = os.path.join(work_dir(p, "passage"), "parole.wav")
    if not t or not os.path.exists(speech):
        raise DiscoursPipelineError("Fais les vidéos une fois avant d'écouter.")
    if son not in SONS:
        raise DiscoursPipelineError("Choix du son inconnu.")
    if son == "intelligente" and not d.get("musique"):
        raise DiscoursPipelineError("La musique intelligente n'est pas encore choisie : refais les vidéos une fois.")
    q = {**p, "discours": {**d, "son": son, "chanson": os.path.basename(chanson or d.get("chanson") or "")}}
    son = son_for(q, t)
    if son == "sans_musique":
        return None
    s = {**settings_for(p, t), "volume_db": LIVE_GAP, "drop_punchline": bool(drop)}
    parts = timeline(q, s)
    total = D.duration(speech)
    key = hashlib.md5(json.dumps([son, q["discours"]["chanson"], drop, d.get("musique"), t.get("music_path"), parts,
                                  os.path.getmtime(speech)], sort_keys=True, default=str).encode()).hexdigest()[:12]
    work = work_dir(p, "cibles", channel, "ecoute")
    out = os.path.join(work, f"musique_{key}.wav")
    if not os.path.exists(out):
        made = bed_for(q, t, s, parts, total, work, lambda phase, f: None)
        if not made:
            return None
        os.replace(made, out)
    return out


def back_to_plans(pid: str) -> Dict:
    """From the previews back to the Plans screen (its timeline, its propositions): the videos made again after."""
    ap = _ap()
    p = ap.load(pid)
    ap._expect(p, "preview_review")
    for t in p["targets"]:
        t["validated"] = False
    p["status"] = "plans_review"
    return ap.save(p)


def change_settings(pid: str, reglages: Optional[Dict] = None, son: Optional[str] = None,
                    chanson: Optional[str] = None) -> Dict:
    """The video's own settings and sound: every channel's video made again (no AI; a new smart song only when the
    sound becomes « intelligente » without one chosen)."""
    ap = _ap()
    p = ap.load(pid)
    ap._expect(p, "preview_review", "plans_review")
    d = p["discours"]
    if reglages is not None:
        mine = dict(d.get("reglages") or {})
        mine.update({k: v for k, v in reglages.items() if k in D.DEFAULTS})
        d["reglages"] = {k: v for k, v in D.clean_settings(mine).items()
                         if k in mine or (k == "sous_titres_params" and "sous_titres" in mine)}
    if son is not None:
        if son not in SONS:
            raise DiscoursPipelineError("Choix du son inconnu.")
        if son == "choisie":
            name = os.path.basename(chanson or d.get("chanson") or "")
            if not name or not os.path.exists(os.path.join(SHARED_MUSIC, name)):
                raise DiscoursPipelineError("Choisis la musique dans la liste.")
            d["chanson"] = name
        d["son"] = son
    if p["status"] == "preview_review":
        _again(p)
    return ap.save(p)


def validate_preview(pid: str, channel: str) -> Dict:
    ap = _ap()
    p = ap.load(pid)
    ap._expect(p, "preview_review")
    t = ap.target(p, channel)
    if not (t.get("preview") or {}).get("checks", {}).get("ok"):
        raise DiscoursPipelineError("Le contrôle automatique a trouvé un problème : refais la vidéo avant de valider.")
    t["validated"] = True
    return ap.save(p)


# ---------------------------------------------------------------- final -> Publication

def credit(p: Dict) -> str:
    return p["discours"].get("orateur") or ""


def publication_record(p: Dict, t: Dict, path: str) -> Dict:
    d = p["discours"]
    code = langs.lang(t["language"])["code"]
    yt = ((d.get("traduction") or {}).get("langues", {}).get(code) or {}).get("youtube") or D.youtube_of(None, credit(p))
    title, desc = yt["titre"], yt["description"]
    label = langs.lang(t["language"])["credit_label"]
    if credit(p) and credit(p).lower() not in desc.lower():
        desc = f"{desc}\n\n{label} {credit(p)}".strip()
    vid = f"{t['channel']}_{p['project_id']}"
    now = datetime.now().isoformat()
    ai = {"optimized_title": title, "title": title, "description_suggestions": [desc], "description": desc,
          "tags": yt["tags"]}
    s = (t.get("preview") or {}).get("reglages") or settings_for(p, t)
    return {"video_id": vid, "batch_id": p["project_id"], "channel": t["channel"], "url": p["reference_url"],
            "status": "ready_for_upload", "priority": "normal", "source": "adaptation",
            "adaptation_project": p["project_id"], "original_title": title, "video_path": path, "ai_data": ai,
            "recette": {"type": "adaptation", "mode": "discours", "son": son_for(p, t),
                        "musique": (d.get("musique") or {}).get("fichier") if son_for(p, t) == "intelligente"
                        else d.get("chanson") if son_for(p, t) == "choisie" else None,
                        "sous_titres": D.caption_style_for(s, code), "cadre": s["cadre"], "fond": s["fond"],
                        "orateur": credit(p)},
            "added_at": now, "updated_at": now}


def start_render(pid: str) -> Dict:
    ap = _ap()
    p = ap.load(pid)
    ap._expect(p, "preview_review")
    if not any(t["validated"] for t in p["targets"]):
        raise DiscoursPipelineError("Valide au moins une vidéo avant le rendu final.")
    p["status"] = "rendering"
    return ap.save(p)


def run_final(pid: str, report: Optional[Report] = None):
    ap = _ap()
    report = report or (lambda phase, f: None)
    p = ap.load(pid)
    try:
        import db
        todo = [t for t in p["targets"] if t["validated"] and not t.get("video_id")]
        os.makedirs("processed_videos", exist_ok=True)
        for i, t in enumerate(todo):
            report(f"{t['channel']} : publication", i / max(1, len(todo)))
            dest = os.path.join("processed_videos", f"{t['channel']}_{pid}.mp4")
            shutil.copy(t["preview"]["path"], dest)
            rec = publication_record(p, t, dest)
            thumb = D.thumbnail(dest, float(t["preview"].get("mot_fort_a") or 1.0), os.path.splitext(dest)[0] + ".jpg")
            if thumb:
                rec["thumbnail_path"] = thumb
            db.upsert_video(rec["video_id"], rec)
            shots = [m["clip"]["stock"] for m in p["discours"]["moments"] or []
                     if m.get("action") == "garder" and (m.get("clip") or {}).get("stock")]
            if shots:                                # remembered per channel, like the drones
                db.record_broll_usage(t["channel"], shots, rec["video_id"])
            t.update(video_id=rec["video_id"], final={"path": dest})
            ap.save(p)
        waiting = [t for t in p["targets"] if not t.get("video_id")]
        p.update(status="preview_review" if waiting else "done", error=None, failed_step=None)
        ap.save(p)
    except Exception as e:
        ap.fail(pid, "rendering", e)
    report("terminé", 1.0)


RUNNERS = {"analysing": run_analysis, "searching": run_search, "voicing": run_voices, "rendering": run_final}


def _no_script(*_args, **_kw):
    raise DiscoursPipelineError("Pas de script ni de voix en mode Discours : c'est la voix de l'orateur.")


approve_script = start_voices = change_voice = _no_script
