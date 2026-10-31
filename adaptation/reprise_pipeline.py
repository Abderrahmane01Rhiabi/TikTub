"""
A « Reprise » project (mode "reprise" of adaptation/pipeline.py), step by step:

    analysing        the Short downloaded whole (1080x1920 at best), its thumbnail, Gemini's reading of its plans
                     (their times read back as seconds) and of what its creator added, then straight on to:
    cleaning         everything « cacher » erased (reprise.clean, graphics card, 3 to 45 min)   (background)
    cleaning_review  the person compares the original and the clean video, may turn an element to « garder » /
                     « cacher » and clean again, then approves
    scripting        one script, every language of the channels: top (reordered, numbered) or story (background)
    script_review    the person reads / edits / approves each language (mandatory)
    voicing          per channel: its voice (its model), then the whole video with the sound chosen (background)
    preview_review   the person watches, may change the voice, the model or the sound (the voice is kept when
                     only the sound changes), validates
    rendering        the validated videos join Publication with their thumbnail                   (background)
    done

The sound (p["reprise"]["son"]), for every channel: "sa_musique" (the original's music, his voice removed by
Demucs), "notre_musique" (the channel's track), "intelligente" (a song of the shared list placed on the strong
moment — only on SMART_CHANNELS for now, the others fall back to their track), "sans_musique"; its level in dB
under the voice.
"""

import json
import os
import shutil
from datetime import datetime
from typing import Callable, Dict, List, Optional

import db
from adaptation import langs, musique, reprise, reprise_montage as rm, settings
from adaptation.pipeline import PipelineError

Report = Callable[[str, float], None]

SMART_CHANNELS = ("cestpourca", "lihadha_alsabab")   # the person's choice (2026-10-31): the others later
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


def son_for(p: Dict, t: Dict) -> str:
    """The sound this channel really gets: the smart music only on SMART_CHANNELS; our track when it has one."""
    son = (p.get("reprise") or {}).get("son") or "notre_musique"
    if son == "intelligente" and t["channel"] not in SMART_CHANNELS:
        son = "notre_musique"
    if son == "notre_musique" and not t.get("music_path"):
        son = "sans_musique"
    return son


# ---------------------------------------------------------------- creation

def new_project(base: Dict, targets: List[Dict], son: str = "notre_musique", volume_db: float = musique.GAP) -> Dict:
    if not base.get("reference_url"):
        raise RepriseError("Il faut le lien du Short à reprendre.")
    if son not in musique.SONS:
        raise RepriseError("Choix du son inconnu.")
    return {**base, "mode": "reprise", "source_urls": [], "targets": targets,
            "reprise": {"son": son, "volume_db": max(6.0, min(30.0, float(volume_db))), "elements": None,
                        "plans": None, "script": None, "video": None, "clean": None, "miniature": None,
                        "musique": None}}


# ---------------------------------------------------------------- analysing -> cleaning

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
        p.update(status="cleaning", error=None, failed_step=None)
        ap.save(p)
    except Exception as e:
        ap.fail(pid, "analysing", e)
        report("terminé", 1.0)
        return
    run_cleaning(pid, report)


def run_cleaning(pid: str, report: Optional[Report] = None):
    ap = _ap()
    report = report or (lambda phase, f: None)
    p = ap.load(pid)
    try:
        r = p["reprise"]
        out = os.path.join(work_dir(p, "propre"), "propre.mp4")
        import render_slot
        report("nettoyage (carte graphique)", 0.25)
        with render_slot.SLOT:                       # one heavy job at a time in the app
            done = reprise.clean(r["video"], r["elements"], out, work_dir(p, "propre", "travail"),
                                 progress=lambda f: report("nettoyage (carte graphique)", 0.25 + 0.7 * f))
        p = ap.load(pid)
        p["reprise"].update(clean=out, nettoyage=done)
        p.update(status="cleaning_review", error=None, failed_step=None)
        ap.save(p)
    except Exception as e:
        ap.fail(pid, "cleaning", e)
    report("terminé", 1.0)


def set_element(pid: str, index: int, action: str) -> Dict:
    """An element turned to « garder » / « cacher » by the person (cleaned again after)."""
    ap = _ap()
    p = ap.load(pid)
    ap._expect(p, "cleaning_review")
    els = p["reprise"]["elements"]
    if not 0 <= index < len(els) or action not in ("garder", "cacher"):
        raise RepriseError("Élément ou choix inconnu.")
    els[index] = {**els[index], "action": action, "raison": "choix de la personne"}
    return ap.save(p)


def clean_again(pid: str) -> Dict:
    ap = _ap()
    p = ap.load(pid)
    ap._expect(p, "cleaning_review")
    p["status"] = "cleaning"
    return ap.save(p)


def approve_cleaning(pid: str) -> Dict:
    ap = _ap()
    p = ap.load(pid)
    ap._expect(p, "cleaning_review")
    p["status"] = "scripting"
    return ap.save(p)


# ---------------------------------------------------------------- script

def run_scripts(pid: str, report: Optional[Report] = None, only: Optional[str] = None):
    ap = _ap()
    report = report or (lambda phase, f: None)
    p = ap.load(pid)
    try:
        report("écriture du script", 0.1)
        ref = {**(p.get("reference") or {}), "plans": p["reprise"]["plans"]}
        p["reprise"]["script"] = rm.write_script(ref, _codes(p))
        for t in p["targets"]:
            t.update(approved=False, validated=False, voice=None, preview=None)
        p.update(status="script_review", error=None, failed_step=None)
        ap.save(p)
    except Exception as e:
        ap.fail(pid, "scripting", e)
    report("terminé", 1.0)


def edit_script(pid: str, channel: str, texts: List[str], title: Optional[str] = None) -> Dict:
    """The person's texts for this channel's language, part by part (and its title)."""
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
    ap = _ap()
    p = ap.load(pid)
    ap._expect(p, "script_review")
    missing = [t["channel"] for t in p["targets"] if not t["approved"]]
    if missing:
        raise RepriseError("Scripts pas encore validés : " + ", ".join(missing))
    p["status"] = "voicing"
    return ap.save(p)


# ---------------------------------------------------------------- voice + video

def model_for(t: Dict) -> str:
    return t.get("voice_model") or MODEL


def _music_choice(p: Dict, t: Dict, v: Dict, report: Report) -> Optional[Dict]:
    """The song and its rise, chosen once for the project (the same story in every language)."""
    r = p["reprise"]
    if r.get("musique"):
        return r["musique"]
    script = r["script"]
    code = langs.lang(t["language"])["code"]
    parts = [{"role": x.get("role"), "numero": x.get("numero"), "texte": x[code], "debut": s}
             for x, s in zip(script["parties"], rm.starts_of(v))]
    report("choix de la musique", 0.0)
    ref = p.get("reference") or {}
    r["musique"] = musique.plan(SHARED_MUSIC, ref.get("sujet") or "", ref.get("ton") or "", parts, v["duration"] + 0.8)
    _ap().save(p)
    return r["musique"]


def bed_for(p: Dict, t: Dict, v: Dict, work: str, report: Report) -> Optional[str]:
    """This channel's music bed for its voice's timing, or None (no music)."""
    r = p["reprise"]
    son = son_for(p, t)
    total = v["duration"] + 0.8
    gap = float(r.get("volume_db") or musique.GAP)
    out = os.path.join(work, f"fond_{son}.wav")
    if son == "sans_musique":
        return None
    if son == "sa_musique":
        from roblox import voix
        rest = voix.separate(r["clean"], work_dir(p, "demucs"))["reste"]
        return musique.bed(rest, out, total, gap=gap)
    if son == "notre_musique":
        return musique.bed(t["music_path"], out, total, start=float(t.get("music_start") or 0.0), gap=gap)
    choice = dict(_music_choice(p, t, v, report))
    hit = rm.starts_of(v)[choice["partie"]]          # this language's moment for the chosen part
    song = musique.listen(os.path.join(SHARED_MUSIC, choice["fichier"]))
    choice["montee"], _ = musique.peak_for(song, hit, total, choice["montee"])
    choice["a"] = hit
    return musique.placed_bed(SHARED_MUSIC, choice, total, out, gap=gap)


def make_video(p: Dict, t: Dict, report: Report) -> Dict:
    """The voice (kept while the voice, its model and the texts are the same) and the whole video."""
    r = p["reprise"]
    code = langs.lang(t["language"])["code"]
    work = work_dir(p, "cibles", t["channel"])
    key = [t["voice_id"], model_for(t), [x[code] for x in r["script"]["parties"]]]
    v = t.get("voice")
    if not v or v.get("key") != key or not os.path.exists(v.get("mp3", "")):
        report(f"{t['channel']} : voix", 0.1)
        mp3 = os.path.join(work, "voix.mp3")
        rm.voice(r["script"], code, t["voice_id"], mp3, model=model_for(t))
        v = {"mp3": mp3, "json": mp3[:-4] + ".json", "key": key}
        t["voice"] = v
    timings = json.load(open(v["json"], encoding="utf-8"))
    bed = bed_for(p, t, timings, work, report)
    report(f"{t['channel']} : montage", 0.5)
    out = os.path.join(work, f"reprise_{t['channel']}.mp4")
    import render_slot
    with render_slot.SLOT:
        rm.render(r["clean"], r["plans"], r["script"], code, timings, v["mp3"], bed, out, os.path.join(work, "parties"))
    made = reprise.probe(out)
    ok = abs(made["duree"] - (timings["duration"] + 0.8)) < 1.0
    return {"path": out, "son": son_for(p, t), "duree": round(made["duree"], 1),
            "checks": {"ok": ok, "problems": [] if ok else ["La vidéo n'a pas la durée de la voix."]}}


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


def change_voice(pid: str, channel: str, voice_id: Optional[str] = None, model: Optional[str] = None) -> Dict:
    ap = _ap()
    p = ap.load(pid)
    ap._expect(p, "preview_review")
    t = ap.target(p, channel)
    if voice_id:
        if not db.get_voice(voice_id):
            raise RepriseError("Cette voix n'est pas dans la bibliothèque (Réglages → Voix).")
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
    if son not in musique.SONS:
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
    """The friend whose images these are: the account of the Short's page."""
    meta = (p["reprise"].get("video") or "") + ".meta.json"
    try:
        m = json.load(open(meta, encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return m.get("handle") or m.get("uploader") or ""


def publication_record(p: Dict, t: Dict, path: str) -> Dict:
    code = langs.lang(t["language"])["code"]
    title = (p["reprise"]["script"].get("titre") or {}).get(code) or ""
    who = credit(p)
    desc = f"{title}\n\n{langs.lang(code)['credit_label']} {who}".strip() if who else title
    vid = f"{t['channel']}_{p['project_id']}"
    now = datetime.now().isoformat()
    ai = {"optimized_title": title, "title": title, "description_suggestions": [desc], "description": desc, "tags": []}
    return {"video_id": vid, "batch_id": p["project_id"], "channel": t["channel"], "url": p["reference_url"],
            "status": "ready_for_upload", "priority": "normal", "source": "adaptation",
            "adaptation_project": p["project_id"], "original_title": title, "video_path": path, "ai_data": ai,
            "recette": {"type": "adaptation", "mode": "reprise", "son": son_for(p, t),
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
                    rec["thumbnail_path"] = rm.thumbnail(r["miniature"], title, code, os.path.splitext(dest)[0] + ".jpg")
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


RUNNERS = {"analysing": run_analysis, "cleaning": run_cleaning, "scripting": run_scripts, "voicing": run_voices,
           "rendering": run_final}
