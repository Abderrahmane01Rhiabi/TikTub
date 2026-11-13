"""
A « Reprise » project (mode "reprise" of adaptation/pipeline.py), step by step:

    analysing        the Short downloaded whole (1080x1920 at best), its thumbnail, Gemini's reading of its plans
                     (their times read back as seconds) and of what its creator added; then the cleaning starts in
                     its own lane (below) and the project goes straight on to:
    scripting        one script, every language of the channels: top (reordered, numbered) or story (background)
    script_review    the person reads / edits / approves each language (mandatory)
    settings_review  the person sets the video before it is made: the sound, the song and where it rises, its
                     volume, each channel's voice and model, the captions' style — for every video, or apart for
                     one (par_chaine) — a demo (8 s of the montage, the captions in that style, « Écouter » the voice
                     over the music, the song's strip) shows each change at once
    voicing          per channel: its voice (its model), then the whole video with the sound chosen (background)
    cleaning_wait    the voices made, the videos waiting for the cleaning to be approved
    preview_review   the person watches the video and its timeline, may change any setting (the voice is kept
                     when it is not the one changed) and make again the videos it changed, validates
    rendering        the validated videos join Publication with their thumbnail                   (background)
    done

The cleaning's lane (clean_state, its own file): everything « cacher » erased (reprise.clean, graphics card, 3 to
70 min) while the person writes the script and sets the video — en_cours -> a_verifier (the person compares the
original and the clean video, may turn an element to « garder » / « cacher » and clean again) -> approuve. Only the
montage waits for it. (cleaning / cleaning_review: the statuses of the projects made before the lane.)

The sound (p["reprise"]["son"]), for every channel: "sa_musique" (the original's music, his voice removed by
Demucs), "notre_musique" (the channel's track), "intelligente" (a song of the shared list placed on the strong
moment — only on SMART_CHANNELS for now, the others fall back to their track), "choisie" (a song of the shared
list the person picked, p["reprise"]["chanson"]: no AI, same channels), "sans_musique"; its level in dB under the
voice. p["reprise"]["partie"]: the part the song rises on (None: Gemini's, or the 1st point for a picked song).
p["reprise"]["montee_chanson"]: the rise of the song (s of the song) the person put on that part (None: chosen).
p["reprise"]["sous_titres"]: this video's captions ({"style": a library style or None for ours, "params"}; None:
the channel's choice in Réglages → Sous-titres). p["reprise"]["par_chaine"][channel]: all of these (OWN) for that
channel's video alone, when the person set it apart; opts() gives a video's own.
"""

import json
import os
import shutil
import threading
from datetime import datetime
from typing import Callable, Dict, List, Optional

import db
from adaptation import langs, musique, reprise, reprise_montage as rm, settings
from adaptation.pipeline import PipelineError

Report = Callable[[str, float], None]

SMART_CHANNELS = ("cestpourca", "lihadha_alsabab")   # the person's choice (2026-10-31): the others later
SONS = musique.SONS + ("choisie",)
SHARED_MUSIC = os.path.join("assets", "musiques")    # the songs any channel may use
MODEL = "eleven_v4"                                  # a Reprise's voice model when the channel has none set


class RepriseError(PipelineError):          # said plainly to the person, like the other modes' refusals
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


OWN = ("son", "volume_db", "chanson", "partie", "montee_chanson", "sous_titres")   # what a video may have apart


def opts(p: Dict, t: Dict) -> Dict:
    """This channel's video's settings: its own when the person set it apart (par_chaine), else the project's."""
    r = p.get("reprise") or {}
    own = (r.get("par_chaine") or {}).get(t["channel"])
    return {k: (own if own is not None else r).get(k) for k in OWN}


def son_for(p: Dict, t: Dict) -> str:
    """The sound this channel really gets: the smart music only on SMART_CHANNELS; our track when it has one."""
    r = opts(p, t)
    son = r.get("son") or "notre_musique"
    if son == "choisie" and not (r.get("chanson") and os.path.exists(os.path.join(SHARED_MUSIC, r["chanson"]))):
        son = "intelligente"                          # the picked song gone from the list: chosen for him again
    if son in ("intelligente", "choisie") and t["channel"] not in SMART_CHANNELS:
        son = "notre_musique"
    if son == "notre_musique" and not t.get("music_path"):
        son = "sans_musique"
    return son


# ---------------------------------------------------------------- creation

def new_project(base: Dict, targets: List[Dict], son: str = "notre_musique", volume_db: float = musique.GAP) -> Dict:
    if not base.get("reference_url"):
        raise RepriseError("Il faut le lien du Short à reprendre.")
    if son not in SONS:
        raise RepriseError("Choix du son inconnu.")
    return {**base, "mode": "reprise", "source_urls": [], "targets": targets,
            "reprise": {"son": son, "volume_db": max(6.0, min(30.0, float(volume_db))), "elements": None,
                        "plans": None, "script": None, "video": None, "clean": None, "miniature": None,
                        "musique": None, "chanson": None, "partie": None, "montee_chanson": None,
                        "sous_titres": None, "par_chaine": {}}}


# ---------------------------------------------------------------- analysing -> the script (the cleaning beside)

def run_analysis(pid: str, report: Optional[Report] = None):
    ap = _ap()
    report = report or (lambda phase, f: None)
    p = ap.load(pid)
    try:
        r = p["reprise"]
        from adaptation import reference, sources
        if not r.get("video") or not os.path.exists(r["video"]):
            report("téléchargement du Short", 0.02)
            r["video"] = sources.download_short(p["reference_url"], work_dir(p, "src"), "short")
            r["miniature"] = sources.download_thumbnail(p["reference_url"], work_dir(p, "src"), "miniature")
            ap.save(p)
        info = reprise.probe(r["video"])
        if info["h"] < info["w"]:
            raise RepriseError("La Reprise est faite pour un Short vertical.")
        if not p.get("reference"):
            report("lecture des plans", 0.1)
            p["reference"] = reference.analyse(p["reference_url"])
            ap.save(p)
        if not r.get("plans"):
            r["plans"] = rm.fit_plans(p["reference"].get("plans") or [], info["duree"])
            ap.save(p)
        if r.get("elements") is None:
            report("ce que le créateur a ajouté", 0.2)
            r["elements"] = reprise.find_elements(r["video"])
            ap.save(p)
        p.update(status="scripting", error=None, failed_step=None)
        ap.save(p)
    except Exception as e:
        ap.fail(pid, "analysing", e)
        report("terminé", 1.0)
        return
    start_cleaning(pid)
    run_scripts(pid, report)


# ---------------------------------------------------------------- the cleaning's lane

_CLEAN_LOCK = threading.Lock()


def _spawn(fn: Callable[[], None]):
    threading.Thread(target=fn, daemon=True).start()


def clean_job(pid: str) -> str:
    return f"adapt:{pid}:nettoyage"                  # its progress, apart from the project's step


def _clean_file(p: Dict) -> str:
    return os.path.join(_ap().project_dir(p["project_id"]), "propre", "etat.json")


def clean_state(p: Dict) -> Dict:
    """{"etat": attente | en_cours | a_verifier | approuve | erreur, "choix": {element: action}, "nettoyage",
    "erreur"}. In its own file: the steps running meanwhile save the project, and would write over it."""
    try:
        return json.load(open(_clean_file(p), encoding="utf-8"))
    except (OSError, ValueError):
        pass
    r = p.get("reprise") or {}                       # a project from before the lane
    etat = {"cleaning": "en_cours", "cleaning_review": "a_verifier"}.get(p.get("status"))
    return {"etat": etat or ("approuve" if clean_video(p) else "attente"), "choix": {}, "nettoyage": r.get("nettoyage")}


def _set_clean_state(p: Dict, **kw) -> Dict:
    path = _clean_file(p)
    if not os.path.isdir(os.path.dirname(os.path.dirname(path))):
        return kw                                    # the project deleted meanwhile
    with _CLEAN_LOCK:
        s = {**clean_state(p), **kw}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump(s, open(path + ".tmp", "w", encoding="utf-8"), ensure_ascii=False)
        os.replace(path + ".tmp", path)
    return s


def clean_video(p: Dict) -> Optional[str]:
    """The clean video as last made (approved or not), or None."""
    path = os.path.join(_ap().project_dir(p["project_id"]), "propre", "propre.mp4")
    return path if os.path.exists(path) else None


def clean_ready(p: Dict) -> Optional[str]:
    """The clean video once the person approved it: the only thing the montage waits for."""
    return clean_video(p) if clean_state(p)["etat"] == "approuve" else None


def elements_of(p: Dict) -> List[Dict]:
    """What the creator added, with the person's « garder » / « cacher »."""
    choix = clean_state(p).get("choix") or {}
    return [{**e, "action": choix[str(i)], "raison": "choix de la personne"} if str(i) in choix else e
            for i, e in enumerate((p.get("reprise") or {}).get("elements") or [])]


def clean_running(p: Dict) -> bool:
    import progress
    job = progress.get(clean_job(p["project_id"]))
    return bool(job and not job.get("done"))


def start_cleaning(pid: str):
    """The cleaning started in its own thread (its own progress): nothing else waits for it but the montage."""
    import progress
    p = _ap().load(pid)
    if clean_running(p):
        return
    _set_clean_state(p, etat="en_cours", erreur=None)
    key = clean_job(pid)
    progress.start(key, kind="adaptation", phase="nettoyage")

    def run():
        from gemini_ai_generator import usage_context
        with usage_context(projet=pid):
            run_cleaning(pid, lambda ph, f: progress.update(key, f, phase=ph))
        progress.finish(key)
    _spawn(run)


def run_cleaning(pid: str, report: Optional[Report] = None):
    ap = _ap()
    report = report or (lambda phase, f: None)
    p = ap.load(pid)
    try:
        r = p["reprise"]
        out = os.path.join(work_dir(p, "propre"), "propre.mp4")
        part = out[:-4] + ".part.mp4"                # the demo keeps the last clean video while the next is made
        import render_slot
        report("nettoyage (carte graphique)", 0.02)
        with render_slot.SLOT:                       # one heavy job at a time in the app
            done = reprise.clean(r["video"], elements_of(p), part, work_dir(p, "propre", "travail"),
                                 progress=lambda f: report("nettoyage (carte graphique)", 0.02 + 0.97 * f))
        os.replace(part, out)
        _set_clean_state(p, etat="a_verifier", nettoyage=done, erreur=None)
    except Exception as e:
        _set_clean_state(p, etat="erreur", erreur=str(e)[:300])
    report("terminé", 1.0)


def resume_cleaning(pid: str, report: Optional[Report] = None):
    """The step « cleaning » (a project from before the lane, or retried after its error): the lane started again,
    the project on to its script."""
    ap = _ap()
    p = ap.load(pid)
    p.update(status="scripting" if not p["reprise"].get("script") else "script_review", error=None, failed_step=None)
    ap.save(p)
    start_cleaning(pid)
    if p["status"] == "scripting":
        run_scripts(pid, report)


def _reviewing(p: Dict):
    if p["status"] != "cleaning_review" and clean_state(p)["etat"] not in ("a_verifier", "erreur"):
        raise RepriseError("Le nettoyage n'est pas à vérifier maintenant.")


def set_element(pid: str, index: int, action: str) -> Dict:
    """An element turned to « garder » / « cacher » by the person (cleaned again after)."""
    p = _ap().load(pid)
    _reviewing(p)
    if not 0 <= index < len(p["reprise"]["elements"] or []) or action not in ("garder", "cacher"):
        raise RepriseError("Élément ou choix inconnu.")
    _set_clean_state(p, choix={**(clean_state(p).get("choix") or {}), str(index): action})
    return p


def clean_again(pid: str) -> Dict:
    """Cleaned again (after a change, an error, or a cleaning cut by a restart of the server)."""
    ap = _ap()
    p = ap.load(pid)
    if clean_running(p):
        raise RepriseError("Le nettoyage tourne déjà.")
    if clean_state(p)["etat"] == "approuve" and p["status"] != "cleaning_review":
        raise RepriseError("Le nettoyage est déjà validé.")
    if p["status"] == "cleaning_review":            # a project from before the lane: on to its script
        p.update(status="scripting" if not p["reprise"].get("script") else "script_review")
        ap.save(p)
    start_cleaning(pid)
    return ap.load(pid)


def approve_cleaning(pid: str) -> Dict:
    """The clean video approved: the montage may use it (the voices waiting for it: the videos are made now)."""
    ap = _ap()
    p = ap.load(pid)
    if clean_state(p)["etat"] != "a_verifier" and p["status"] != "cleaning_review":
        raise RepriseError("Le nettoyage n'est pas à vérifier maintenant.")
    _set_clean_state(p, etat="approuve")
    if p["status"] == "cleaning_review":            # a project from before the lane
        p["status"] = "scripting"
    elif p["status"] == "cleaning_wait":
        p["status"] = "voicing"
    return ap.save(p)


# ---------------------------------------------------------------- script

def run_scripts(pid: str, report: Optional[Report] = None, only: Optional[str] = None):
    ap = _ap()
    report = report or (lambda phase, f: None)
    p = ap.load(pid)
    try:
        report("écriture du script", 0.1)
        ref = {**(p.get("reference") or {}), "plans": p["reprise"]["plans"]}
        from adaptation import recits       # the channel's narrative style (once per project)
        if not p.get("recit"):
            recits.for_project(p)
            ap.save(p)
        p["reprise"]["script"] = rm.write_script(ref, _codes(p), **({"recit": recits.part(p["recit"])} if p.get("recit") else {}))
        p["reprise"]["musique"] = None               # its parts may differ: the song's rise placed again
        for t in p["targets"]:
            t.update(approved=False, validated=False, voice=None, preview=None)
        p.update(status="script_review", error=None, failed_step=None)
        ap.save(p)
    except Exception as e:
        ap.fail(pid, "scripting", e)
    report("terminé", 1.0)


def edit_script(pid: str, channel: str, texts: List[str], title: Optional[str] = None,
                youtube: Optional[Dict] = None) -> Dict:
    """The person's texts for this channel's language, part by part, its thumbnail title and its YouTube title,
    description and tags."""
    ap = _ap()
    p = ap.load(pid)
    ap._expect(p, "script_review")
    t = ap.target(p, channel)
    code = langs.lang(t["language"])["code"]
    parts = p["reprise"]["script"]["parties"]
    if len(texts) != len(parts) or any(not (x or "").strip() for x in texts):
        raise RepriseError("Il faut un texte pour chaque partie.")
    for part, x in zip(parts, texts):
        part[code] = " ".join(x.split())
    if title is not None and title.strip():
        p["reprise"]["script"]["titre"][code] = title.strip()
    if youtube:
        sc = p["reprise"]["script"]
        sc.setdefault("youtube", {})[code] = rm.youtube_of(youtube, sc["titre"].get(code) or "")
    for o in p["targets"]:                           # every channel of this language reads it again
        if langs.lang(o["language"])["code"] == code:
            o["approved"] = False
    return ap.save(p)


def approve_script(pid: str, channel: str) -> Dict:
    ap = _ap()
    p = ap.load(pid)
    ap._expect(p, "script_review")
    ap.target(p, channel)["approved"] = True
    return ap.save(p)


def start_voices(pid: str) -> Dict:
    """Every script approved: on to the settings (nothing made yet, nothing paid)."""
    ap = _ap()
    p = ap.load(pid)
    ap._expect(p, "script_review")
    missing = [t["channel"] for t in p["targets"] if not t["approved"]]
    if missing:
        raise RepriseError("Scripts pas encore validés : " + ", ".join(missing))
    p["status"] = "settings_review"
    return ap.save(p)


def make_videos(pid: str) -> Dict:
    """The settings chosen: the voices and the videos made (background)."""
    ap = _ap()
    p = ap.load(pid)
    ap._expect(p, "settings_review")
    p["status"] = "voicing"
    return ap.save(p)


def _clean_opts(r: Dict, s: Dict, base: Dict) -> Dict:
    """base with the settings sent in s (any of OWN), checked."""
    out = {k: base.get(k) for k in OWN}
    if "son" in s:
        if s["son"] not in SONS:
            raise RepriseError("Choix du son inconnu.")
        out["son"] = s["son"]
    if s.get("volume_db") is not None:
        out["volume_db"] = max(6.0, min(30.0, float(s["volume_db"])))
    if "chanson" in s:
        name = os.path.basename(s["chanson"] or "")
        if name and not os.path.exists(os.path.join(SHARED_MUSIC, name)):
            raise RepriseError("Cette musique n'est pas dans la liste commune.")
        out["chanson"] = name or None
    if out.get("son") == "choisie" and not out.get("chanson"):
        raise RepriseError("Choisis la musique dans la liste.")
    if "partie" in s:
        n = len((r.get("script") or {}).get("parties") or [])
        out["partie"] = int(s["partie"]) if s["partie"] is not None and 0 <= int(s["partie"]) < n else None
    if "montee_chanson" in s:
        out["montee_chanson"] = round(max(0.0, float(s["montee_chanson"])), 2) if s["montee_chanson"] is not None else None
    if "sous_titres" in s:
        from captions import styles as caption_lib
        c = s["sous_titres"]
        if c is None:
            out["sous_titres"] = None                 # the channel's choice
        else:
            st = caption_lib.get(c.get("style")) if c.get("style") else None
            if c.get("style") and not (st and "reprise" in st.spaces):
                raise RepriseError("Style de sous-titres inconnu pour une Reprise.")
            out["sous_titres"] = {"style": st.id if st else None, "params": st.clean(c.get("params")) if st else {}}
    if out.get("volume_db") is None:
        out["volume_db"] = musique.GAP
    return out


def _made_of(p: Dict, t: Dict) -> list:
    return [opts(p, t), t["voice_id"], model_for(t)]


def set_settings(pid: str, s: Dict) -> Dict:
    """The person's settings (any of OWN for every video; par_chaine {channel: the OWN of that video alone, None: back
    to every video's}; voix {channel: {voice_id, model}}). Before the videos: kept for them; on the previews: the
    videos they change are made again (a voice only when it changed), the others kept and still validated."""
    ap = _ap()
    p = ap.load(pid)
    if p["status"] not in ("settings_review", "preview_review", "cleaning_wait"):
        ap._expect(p, "settings_review")
    r = p["reprise"]
    before = {t["channel"]: _made_of(p, t) for t in p["targets"]}
    r.update(_clean_opts(r, s, r))
    own = dict(r.get("par_chaine") or {})
    for ch, o in (s.get("par_chaine") or {}).items():
        ap.target(p, ch)
        if o is None:
            own.pop(ch, None)
        else:
            own[ch] = _clean_opts(r, o, own.get(ch) or r)
    r["par_chaine"] = own
    for ch, v in (s.get("voix") or {}).items():
        t = ap.target(p, ch)
        if v.get("voice_id"):
            if not db.get_voice(v["voice_id"]):
                raise RepriseError("Cette voix n'est pas dans la bibliothèque (Réglages → Bibliothèques → Voix).")
            t["voice_id"] = v["voice_id"]
        if v.get("model"):
            if v["model"] not in settings.VOICE_MODELS:
                raise RepriseError("Modèle de voix inconnu.")
            t["voice_model"] = v["model"]
    if p["status"] in ("preview_review", "cleaning_wait"):
        changed = [t for t in p["targets"] if _made_of(p, t) != before[t["channel"]] and not t.get("video_id")]
        for t in changed:
            t["validated"] = False
        if changed:
            p["status"] = "voicing"
    return ap.save(p)


def captions_for(p: Dict, t: Dict) -> Dict:
    """This video's captions: its own choice (the settings), else the channel's (Réglages → Sous-titres)."""
    own = opts(p, t).get("sous_titres")
    if own is not None:
        return own
    from captions import render as caption_render
    return caption_render.channel_choice(t["channel"])


# ---------------------------------------------------------------- voice + video

def model_for(t: Dict) -> str:
    return t.get("voice_model") or MODEL


def _music_choice(p: Dict, t: Dict, v: Dict, report: Report) -> Optional[Dict]:
    """The song and its rise, chosen once for the project (the same story in every language). A song the person
    picked (« choisie »): no AI, it rises on the 1st point (else the hook)."""
    r = p["reprise"]
    if son_for(p, t) == "choisie":
        name = opts(p, t)["chanson"]
        path = os.path.join(SHARED_MUSIC, name)
        return {"fichier": name, "titre": musique.listen(path).get("titre") or name, "montee": None,
                "partie": 1 if len(r["script"]["parties"]) > 1 else 0}
    if r.get("musique"):
        return r["musique"]
    script = r["script"]
    code = langs.lang(t["language"])["code"]
    parts = [{"role": x.get("role"), "numero": x.get("numero"), "texte": x[code], "debut": s}
             for x, s in zip(script["parties"], rm.starts_of(v))]
    report("choix de la musique", 0.0)
    ref = p.get("reference") or {}
    r["musique"] = musique.plan(SHARED_MUSIC, ref.get("sujet") or "", ref.get("ton") or "", parts, v["duration"] + 0.8)
    saved = _ap().load(p["project_id"])             # p may be the demo's trial: only the choice is kept
    saved["reprise"]["musique"] = r["musique"]
    _ap().save(saved)
    return r["musique"]


def bed_for(p: Dict, t: Dict, v: Dict, work: str, report: Report) -> Optional[str]:
    """This channel's music bed for its voice's timing, or None (no music)."""
    r = p["reprise"]
    son = son_for(p, t)
    total = v["duration"] + 0.8
    gap = float(opts(p, t).get("volume_db") or musique.GAP)
    out = os.path.join(work, f"fond_{son}.wav")
    if son == "sans_musique":
        return None
    from adaptation import mixage                     # levelled, its instrumental when it holds up, a hall at the end
    if son == "sa_musique":
        from roblox import voix                       # the cleaning leaves the sound as it is: the Short's own
        rest = voix.separate(r["video"], work_dir(p, "demucs"))["reste"]
        musique.bed(rest, out, total, gap=gap)
        mixage.note(out, entree=0.0, montee=None, coupe=None, fin=round(total, 2))
        return out
    if son == "notre_musique":
        start = float(t.get("music_start") or 0.0)
        return mixage.bed(mixage.music_source(t["music_path"], start, total), out, total, start=start, gap=gap)
    path, start, lift = song_plan(p, t, v, report)
    return mixage.bed(mixage.music_source(path, start, total), out, total, start, 0.0, gap, lift_at=lift)


def song_plan(p: Dict, t: Dict, v: Dict, report: Report) -> tuple:
    """(the shared song, where it starts, when it rises in the video) for this voice's timing: its rise on the part
    chosen (the person's, else Gemini's / the 1st point), the music from the 1st second (its rise earlier rather
    than a silence)."""
    w = _song_place(p, t, v, report)
    return w["path"], w["start"], w["rise"] - w["start"]


QUIET_OPENING_DB = 18.0       # a video opening this much under the song's usual level: heard as « the music is late »
_LEVELS: Dict[tuple, List[float]] = {}


def song_level(path: str) -> List[float]:
    """The song's level (dBFS) every 0.5 s, measured once."""
    from adaptation import mixage
    key = (path, os.path.getmtime(path))
    if key not in _LEVELS:
        _LEVELS[key] = mixage.envelope(path, 0.5)
    return _LEVELS[key]


def rises_of(song: Dict) -> List[float]:
    """Every rise of the song the person may put on the part: its measured rises and its strong moment."""
    return sorted({round(float(x), 2) for x in (song.get("montees") or []) + [song["moment_fort"]]})


def _opens_loud(path: str, start: float, first: float) -> bool:
    try:
        lv = song_level(path)
    except Exception:                                 # not measurable: taken as it is
        return True
    heard = sorted(x for x in lv if x > -60)
    if not heard:
        return True
    usual = heard[len(heard) // 2]
    i = int(max(start, first) / 0.5)
    opening = lv[i:i + 4]                             # its first 2 s in the video
    return not opening or sum(opening) / len(opening) >= usual - QUIET_OPENING_DB


def _song_place(p: Dict, t: Dict, v: Dict, report: Report) -> Dict:
    """Where the song goes in this video: {path, song, total, partie, hit (when that part starts in the video), rise
    (in the song), start (in the song), auto}. The rise the person chose, else Gemini's / the strong moment's —
    unless the video would then open on a whisper of the song (a soft intro): then the nearest rise that opens on
    its real sound."""
    from adaptation import mixage
    total = v["duration"] + 0.8
    o = opts(p, t)
    choice = dict(_music_choice(p, t, v, report))
    starts = rm.starts_of(v)
    part = o.get("partie")
    if part is not None and 0 <= part < len(starts) and part != choice["partie"]:
        choice.update(partie=part, montee=None)       # another part: the song's rise found again for it
    hit = starts[choice["partie"]]                    # this language's moment for the chosen part
    path = os.path.join(SHARED_MUSIC, choice["fichier"])
    song = musique.listen(path)
    try:
        first = mixage.audible(path)[0]
    except Exception:
        first = 0.0
    mine = o.get("montee_chanson")
    if mine is not None and mine >= hit - 2.0:
        rise, auto = float(mine), False
    else:
        rise, auto = musique.peak_for(song, hit, total, choice["montee"])[0], True
        if not _opens_loud(path, rise - hit, first):
            fit = [m for m in rises_of(song) if m >= hit - 2.0 and m - hit + total <= song["duree"]
                   and _opens_loud(path, m - hit, first)]
            rise = min(fit, key=lambda m: abs(m - rise)) if fit else rise
    return {"path": path, "song": song, "total": total, "partie": choice["partie"], "hit": hit, "rise": rise,
            "start": max(0.0, rise - hit), "auto": auto}


def song_window(p: Dict, t: Dict, report: Optional[Report] = None) -> Optional[Dict]:
    """The song's strip in the settings: the whole song (its level), the part of it this video takes (as bed() will
    take it: from its first sound, kept inside the song), where it rises in the song and in the video, and the other
    rises the person may put on the part instead. None: no song for this video; {"attente": True}: Gemini has not
    chosen it yet (the first « Écouter » does)."""
    from adaptation import mixage
    son = son_for(p, t)
    if son not in ("intelligente", "choisie"):
        return None
    if son == "intelligente" and not p["reprise"].get("musique"):
        return {"attente": True}
    v = timings_of(p, t)
    w = _song_place(p, t, v, report or (lambda ph, f: None))
    start, lift, total = w["start"], w["rise"] - w["start"], w["total"]
    start, lift = mixage.placed(w["path"], start, total, 0.0, lift)
    hit, song = w["hit"], w["song"]
    part = (p["reprise"]["script"]["parties"] or [{}])[w["partie"]]
    return {"titre": song.get("titre"), "duree": song["duree"], "pas": 0.5, "niveau": song_level(w["path"]),
            "debut": round(start, 2), "fin": round(min(song["duree"], start + total), 2),
            "montee": round(start + lift, 2) if lift is not None else None,
            "montee_video": round(lift, 2) if lift is not None else None, "partie": w["partie"],
            "partie_role": part.get("role"), "partie_numero": part.get("numero"), "partie_debut": round(hit, 2),
            "auto": w["auto"], "estime": not os.path.exists((t.get("voice") or {}).get("json", "")),
            "montees": [m for m in rises_of(song)        # only those the song lasts after: else it is moved back
                        if m >= hit - 2.0 and max(0.0, m - hit) + total <= song["duree"] - 0.5]}


def frise(p: Dict, t: Dict) -> Optional[Dict]:
    """This channel's video as a timeline: its parts (the voice's times), the original's images under each (as
    rm.render lays them: at the part's speed, the last image held if they end early), where the music comes in,
    rises and ends, and its level (mixage.note beside the bed)."""
    r = p.get("reprise") or {}
    v = t.get("voice") or {}
    if not r.get("script") or not r.get("plans") or not os.path.exists(v.get("json", "")):
        return None
    timings = json.load(open(v["json"], encoding="utf-8"))
    code = langs.lang(t["language"])["code"]
    total = timings["duration"] + 0.8
    parts, images = [], []
    for k, (part, a, d) in enumerate(zip(r["script"]["parties"], rm.starts_of(timings), rm.part_lengths(timings))):
        shots = [(i, r["plans"][i]) for i in part["plans"] if 0 <= i < len(r["plans"])]
        foot = sum(s["fin"] - s["debut"] for _, s in shots) or 1.0
        speed = min(rm.SPEED[1], max(rm.SPEED[0], foot / d))
        at = a
        for i, s in shots:
            if at >= a + d:
                break
            end = min(a + d, at + (s["fin"] - s["debut"]) / speed)
            images.append({"plan": i, "debut": round(at, 2), "fin": round(end, 2), "source": round((s["debut"] + s["fin"]) / 2, 2)})
            at = end
        if at < a + d - 0.1:                         # the images ran out: the last one held
            images.append({"plan": None, "debut": round(at, 2), "fin": round(a + d, 2), "fige": True,
                           "source": images[-1]["source"] if images else 0.0})
        parts.append({"debut": round(a, 2), "fin": round(a + d, 2), "role": part.get("role"), "numero": part.get("numero"),
                      "texte": part.get(code) or "", "vitesse": round(speed, 2)})
    son = son_for(p, t)
    music = None
    placed = os.path.join(_ap().project_dir(p["project_id"]), "cibles", t["channel"], f"fond_{son}.wav.json")
    if son != "sans_musique" and os.path.exists(placed):
        music = json.load(open(placed, encoding="utf-8"))
        music["titre"] = ((r.get("musique") or {}).get("titre") if son == "intelligente" else opts(p, t).get("chanson")
                          if son == "choisie" else "sa musique" if son == "sa_musique"
                          else os.path.basename(t.get("music_path") or ""))
    return {"total": round(total, 2), "parties": parts, "images": images, "musique": music, "son": son}


def make_voice(p: Dict, t: Dict, report: Report) -> Dict:
    """This channel's voice (kept while the voice, its model and the texts are the same)."""
    r = p["reprise"]
    code = langs.lang(t["language"])["code"]
    key = [t["voice_id"], model_for(t), [x[code] for x in r["script"]["parties"]]]
    v = t.get("voice")
    if not v or v.get("key") != key or not os.path.exists(v.get("mp3", "")):
        report(f"{t['channel']} : voix", 0.1)
        mp3 = os.path.join(work_dir(p, "cibles", t["channel"]), "voix.mp3")
        rm.voice(r["script"], code, t["voice_id"], mp3, model=model_for(t), dialect=t.get("dialecte"))
        v = {"mp3": mp3, "json": mp3[:-4] + ".json", "key": key}
        t["voice"] = v
    return v


def make_video(p: Dict, t: Dict, report: Report) -> Dict:
    """The voice and the whole video, on the clean video approved."""
    r = p["reprise"]
    clean = clean_ready(p)
    if not clean:
        raise RepriseError("Le nettoyage n'est pas encore validé.")
    code = langs.lang(t["language"])["code"]
    work = work_dir(p, "cibles", t["channel"])
    v = make_voice(p, t, report)
    timings = json.load(open(v["json"], encoding="utf-8"))
    bed = bed_for(p, t, timings, work, report)
    out = os.path.join(work, f"reprise_{t['channel']}.mp4")
    from adaptation import mixage
    from captions import render as caption_render
    captions = captions_for(p, t)                         # this video's own, else the channel's (Réglages)
    o = opts(p, t)
    music = [bed is not None, t.get("music_path"), t.get("music_start"), r.get("musique"), o["volume_db"],
             o["chanson"], o["partie"], o["montee_chanson"]]
    els = elements_of(p)
    key = _ap().render_key("v3", clean, os.path.getmtime(clean), r["plans"], r["script"], code, timings, v["mp3"],
                           music, rm.caption_y(els), captions, son_for(p, t), rm.__file__, mixage.__file__,
                           caption_render.__file__)
    if _ap().kept_video(t.get("preview"), key):
        return t["preview"]                          # nothing changed since this preview: not made again
    report(f"{t['channel']} : son", 0.45)                  # the voice cleaned, the music giving way to it, mastered
    sound = mixage.track(v["mp3"], bed, os.path.join(work, "son.wav"), carve=True)
    report(f"{t['channel']} : montage", 0.5)
    import render_slot
    with render_slot.SLOT:
        rm.render(clean, r["plans"], r["script"], code, timings, sound, None, out, os.path.join(work, "parties"),
                  rm.caption_y(els), captions=captions, mastered=True)
    made = reprise.probe(out)
    ok = abs(made["duree"] - (timings["duration"] + 0.8)) < 1.0
    return {"path": out, "son": son_for(p, t), "duree": round(made["duree"], 1), "cle": key,
            "checks": {"ok": ok, "problems": [] if ok else ["La vidéo n'a pas la durée de la voix."]}}


def run_voices(pid: str, report: Optional[Report] = None, only: Optional[str] = None):
    ap = _ap()
    report = report or (lambda phase, f: None)
    p = ap.load(pid)
    try:
        todo = [t for t in p["targets"] if (only is None or t["channel"] == only) and not t.get("video_id")]
        if not clean_ready(p):                       # the voices now, the videos once the cleaning is approved
            for i, t in enumerate(todo):
                make_voice(p, t, lambda ph, f: report(ph, (i + f) / len(todo)))
                ap.save(p)
            p.update(status="cleaning_wait", error=None, failed_step=None)
            ap.save(p)
            report("terminé", 1.0)
            return
        for i, t in enumerate(todo):
            made = make_video(p, t, lambda ph, f: report(ph, (i + f) / len(todo)))
            if made is not t.get("preview"):         # a video kept as it was stays validated
                t["preview"], t["validated"] = made, False
            ap.save(p)
        p.update(status="preview_review", error=None, failed_step=None)
        ap.save(p)
    except Exception as e:
        ap.fail(pid, "voicing", e)
    report("terminé", 1.0)


def change_voice(pid: str, channel: str, voice_id: Optional[str] = None, model: Optional[str] = None) -> Dict:
    ap = _ap()
    p = ap.load(pid)
    ap._expect(p, "preview_review")
    t = ap.target(p, channel)
    if voice_id:
        if not db.get_voice(voice_id):
            raise RepriseError("Cette voix n'est pas dans la bibliothèque (Réglages → Bibliothèques → Voix).")
        t["voice_id"] = voice_id
    if model:
        if model not in settings.VOICE_MODELS:
            raise RepriseError("Modèle de voix inconnu.")
        t["voice_model"] = model
    t["validated"] = False
    p["status"] = "voicing"
    return ap.save(p)


def change_sound(pid: str, son: str, volume_db: Optional[float] = None) -> Dict:
    """Another sound for every channel: the videos made again, their voices kept (no new ElevenLabs credits)."""
    ap = _ap()
    p = ap.load(pid)
    ap._expect(p, "preview_review")
    if son not in SONS:
        raise RepriseError("Choix du son inconnu.")
    p["reprise"]["son"] = son
    if volume_db is not None:
        p["reprise"]["volume_db"] = max(6.0, min(30.0, float(volume_db)))
    for t in p["targets"]:
        t["validated"] = False
    p["status"] = "voicing"
    return ap.save(p)


def validate_preview(pid: str, channel: str) -> Dict:
    ap = _ap()
    p = ap.load(pid)
    ap._expect(p, "preview_review")
    t = ap.target(p, channel)
    if not (t.get("preview") or {}).get("checks", {}).get("ok"):
        raise RepriseError("Le contrôle automatique a trouvé un problème : refais la vidéo avant de valider.")
    t["validated"] = True
    return ap.save(p)


# ---------------------------------------------------------------- final -> Publication

def credit(p: Dict) -> str:
    """The friend whose images these are: the account of the Short's page (shown on the screen; not written in the
    description — the person took that line out of the first ones)."""
    meta = (p["reprise"].get("video") or "") + ".meta.json"
    try:
        m = json.load(open(meta, encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return m.get("handle") or m.get("uploader") or ""


def publication_record(p: Dict, t: Dict, path: str) -> Dict:
    code = langs.lang(t["language"])["code"]
    sc = p["reprise"]["script"]
    yt = (sc.get("youtube") or {}).get(code) or rm.youtube_of(None, (sc.get("titre") or {}).get(code) or "")
    title, desc = yt["titre"], yt["description"]
    vid = f"{t['channel']}_{p['project_id']}"
    now = datetime.now().isoformat()
    ai = {"optimized_title": title, "title": title, "description_suggestions": [desc], "description": desc,
          "tags": yt["tags"]}
    return {"video_id": vid, "batch_id": p["project_id"], "channel": t["channel"], "url": p["reference_url"],
            "status": "ready_for_upload", "priority": "normal", "source": "adaptation",
            "adaptation_project": p["project_id"], "original_title": title, "video_path": path, "ai_data": ai,
            "recette": {"type": "adaptation", "mode": "reprise", "son": son_for(p, t), "recit": p.get("recit"),
                        "famille_recit": p.get("famille_recit"),
                        "musique": (p["reprise"].get("musique") or {}).get("fichier") if son_for(p, t) == "intelligente" else None,
                        "voix": t["voice_id"], "modele_voix": model_for(t)},
            "added_at": now, "updated_at": now}


def start_render(pid: str) -> Dict:
    ap = _ap()
    p = ap.load(pid)
    ap._expect(p, "preview_review")
    if not any(t["validated"] for t in p["targets"]):
        raise RepriseError("Valide au moins une vidéo avant le rendu final.")
    p["status"] = "rendering"
    return ap.save(p)


def run_final(pid: str, report: Optional[Report] = None):
    ap = _ap()
    report = report or (lambda phase, f: None)
    p = ap.load(pid)
    try:
        r = p["reprise"]
        todo = [t for t in p["targets"] if t["validated"] and not t.get("video_id")]
        os.makedirs("processed_videos", exist_ok=True)
        for i, t in enumerate(todo):
            report(f"{t['channel']} : publication", i / max(1, len(todo)))
            dest = os.path.join("processed_videos", f"{t['channel']}_{pid}.mp4")
            shutil.copy(t["preview"]["path"], dest)
            rec = publication_record(p, t, dest)
            code = langs.lang(t["language"])["code"]
            title = (r["script"].get("titre") or {}).get(code)
            if r.get("miniature") and title:
                try:
                    rec["thumbnail_path"] = rm.thumbnail_apart(r["miniature"], title, code,
                                                              os.path.splitext(dest)[0] + ".jpg")
                except Exception:
                    pass                         # Publication takes its picture from the video
            db.upsert_video(rec["video_id"], rec)
            t.update(video_id=rec["video_id"], final={"path": dest})
            ap.save(p)
        waiting = [t for t in p["targets"] if not t.get("video_id")]
        p.update(status="preview_review" if waiting else "done", error=None, failed_step=None)
        ap.save(p)
    except Exception as e:
        ap.fail(pid, "rendering", e)
    report("terminé", 1.0)


# ---------------------------------------------------------------- the settings' demo

DEMO_S = 8.0                         # the demo: the video's first seconds
LIVE_GAP = 3.0                       # its music made this many dB under the voice, lowered by the page to the slider


def _key(*parts) -> str:
    import hashlib
    return hashlib.md5(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:12]


def timings_of(p: Dict, t: Dict) -> Dict:
    """This channel's voice timings ({"words", "passages", "duration"}): the voice's own once it is made, else
    estimated from the script (each word by its length, at the language's pace) — the demo before any voice."""
    v = t.get("voice") or {}
    if os.path.exists(v.get("json", "")):
        return json.load(open(v["json"], encoding="utf-8"))
    code = langs.lang(t["language"])["code"]
    lo, hi = rm.WPS.get(code, (2.2, 2.6))
    pace = 2 / (lo + hi)                              # s a word, on average
    words, passages, at = [], [], 0.0
    for part in p["reprise"]["script"]["parties"]:
        passages.append({"start": round(at, 2)})
        toks = (part.get(code) or "").split()
        mean = sum(len(x) for x in toks) / max(1, len(toks))
        for x in toks:
            d = pace * (0.6 + 0.4 * len(x) / max(1.0, mean))
            words.append({"w": x, "start": round(at, 3), "end": round(at + d * 0.9, 3)})
            at += d
        at += 0.35
    return {"words": words, "passages": passages, "duration": round(at, 2)}


def demo_clip(p: Dict) -> str:
    """The demo's picture: the montage's first DEMO_S s — the clean video's plans in the script's order (at their own
    pace; the original's while the cleaning runs) — light (540 wide, no sound), cut once."""
    r = p.get("reprise") or {}
    clean = clean_video(p) or r.get("video")
    if not clean or not os.path.exists(clean):
        raise RepriseError("La vidéo n'est pas encore téléchargée.")
    shots, left = [], DEMO_S
    for part in (r.get("script") or {}).get("parties") or []:
        for i in part["plans"]:
            if left > 0 and 0 <= i < len(r.get("plans") or []):
                a, b = r["plans"][i]["debut"], r["plans"][i]["fin"]
                shots.append((a, min(b, a + left)))
                left -= shots[-1][1] - a
    shots = shots or [(0.0, DEMO_S)]
    out = os.path.join(work_dir(p, "demo"), f"clip_{_key(shots, clean)}.mp4")
    if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(clean):
        inputs = [x for a, b in shots for x in ("-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", clean)]   # each sought
        g = "".join(f"[{k}:v]setpts=PTS-STARTPTS,scale=540:960:force_original_aspect_ratio=increase,crop=540:960,"
                    f"setsar=1,fps=30[s{k}];" for k in range(len(shots)))
        g += "".join(f"[s{k}]" for k in range(len(shots))) + f"concat=n={len(shots)}:v=1:a=0[v]"
        rm._run(["ffmpeg", "-nostdin", "-v", "error", "-y", *inputs, "-filter_complex", g, "-map", "[v]", "-an",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-movflags", "+faststart", out + ".part.mp4"])
        os.replace(out + ".part.mp4", out)
    return out


def demo_captions(p: Dict, channel: str, captions: Optional[Dict]) -> str:
    """The demo's captions for this channel's language, as the video will have them (captions None: the channel's
    choice), on black: the page lays them over the picture."""
    t = _ap().target(p, channel)
    r = p["reprise"]
    v = timings_of(p, t)
    code = langs.lang(t["language"])["code"]
    captions = captions if captions is not None else captions_for(p, t)
    words = [w for w in v["words"] if w["start"] < DEMO_S - 0.3]
    numbers = [x.get("numero") if r["script"].get("genre") == "top" and x.get("role") == "point" else None
               for x in r["script"]["parties"]]
    y = rm.caption_y(elements_of(p))
    from captions import render as caption_render
    key = _key(words, rm.starts_of(v), numbers, code, y, captions, os.path.getmtime(rm.__file__),
               os.path.getmtime(caption_render.__file__))
    out = os.path.join(work_dir(p, "demo"), f"sous_titres_{key}.mp4")
    if not os.path.exists(out):
        rm.caption_layer(words, rm.starts_of(v), numbers, code, DEMO_S, y, captions, out, work_dir(p, "demo", key))
        shutil.rmtree(work_dir(p, "demo", key), ignore_errors=True)
    return out


def demo_voice(p: Dict, channel: str, voice_id: Optional[str] = None, model: Optional[str] = None) -> tuple:
    """(the voice for « Écouter », what it is): this channel's voice as made (its first seconds, cleaned and set
    like the video's), or — another voice, or none made yet — that voice's sample from the library."""
    from adaptation import mixage
    t = _ap().target(p, channel)
    voice_id = voice_id or t["voice_id"]
    v = t.get("voice") or {}
    made = os.path.exists(v.get("mp3", "")) and (v.get("key") or [None])[0] == voice_id \
        and (model or model_for(t)) == (v.get("key") or [None, None])[1]
    src = v["mp3"] if made else settings.preview_path(voice_id)
    if not os.path.exists(src):
        raise RepriseError("Pas d'extrait pour cette voix (Réglages → Bibliothèques → Voix).")
    out = os.path.join(work_dir(p, "demo"), f"voix_{_key(src, os.path.getmtime(src), os.path.getmtime(mixage.__file__))}.wav")
    if not os.path.exists(out):
        cut = out + ".cut.wav"
        rm._run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", src, "-t", f"{DEMO_S + 4:.2f}", cut])
        mixage.clean_voice(cut, out)
        os.remove(cut)
    return out, "voix" if made else "extrait"


def trying(p: Dict, channel: str, son: str, chanson: Optional[str], partie: Optional[int],
           montee: Optional[float] = None) -> Dict:
    """The project as if this channel's video had these settings (the demo's, not saved)."""
    if son not in SONS:
        raise RepriseError("Choix du son inconnu.")
    t = _ap().target(p, channel)
    r = p["reprise"]
    own = {**opts(p, t), "son": son, "chanson": os.path.basename(chanson or "") or opts(p, t).get("chanson"),
           "partie": partie, "montee_chanson": montee}
    return {**p, "reprise": {**r, "par_chaine": {**(r.get("par_chaine") or {}), channel: own}}}


def demo_song(p: Dict, channel: str, son: str, chanson: Optional[str], partie: Optional[int],
              montee: Optional[float] = None) -> Optional[Dict]:
    """The song's strip for these settings (song_window)."""
    q = trying(p, channel, son, chanson, partie, montee)
    return song_window(q, _ap().target(q, channel))


def demo_music(p: Dict, channel: str, son: str, chanson: Optional[str], partie: Optional[int],
               report: Optional[Report] = None, montee: Optional[float] = None) -> Optional[str]:
    """This channel's music for « Écouter », placed as the video will have it (its start, its rise on the part chosen),
    LIVE_GAP dB under the voice; None: no music. A smart song not chosen yet is chosen now (Gemini, once)."""
    from adaptation import mixage
    q = trying(p, channel, son, chanson, partie, montee)
    r = p["reprise"]
    t = _ap().target(q, channel)
    son = son_for(q, t)
    if son == "sans_musique":
        return None
    v = timings_of(p, t)
    if son == "intelligente" and not r.get("musique"):
        _music_choice(q, t, v, report or (lambda ph, f: None))      # saved on the project: the video uses it too
    total = DEMO_S + 4
    if son == "sa_musique":
        from roblox import voix
        src, start, lift = voix.separate(r["video"], work_dir(p, "demucs"))["reste"], 0.0, None
    elif son == "notre_musique":
        src, start, lift = t["music_path"], float(t.get("music_start") or 0.0), None
    else:
        src, start, lift = song_plan(q, t, v, report or (lambda ph, f: None))
    out = os.path.join(work_dir(p, "demo"), f"musique_{_key(src, start, lift, os.path.getmtime(mixage.__file__))}.wav")
    if not os.path.exists(out):
        mixage.bed(src if son == "sa_musique" else mixage.music_source(src, start, total), out, total,
                   start, 0.0, LIVE_GAP, lift_at=lift, end=False)
    return out


RUNNERS = {"analysing": run_analysis, "cleaning": resume_cleaning, "scripting": run_scripts, "voicing": run_voices,
           "rendering": run_final}
