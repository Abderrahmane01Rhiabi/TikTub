"""
An adaptation project, step by step.

    analysing        Gemini reads the reference Short (once) and lists the
                     scenes to find, with YouTube candidates; the sources
                     given are downloaded and cut into clips         (background)
    sources_search   no source yet: the person picks candidates / pastes links
                     (sources can also be added later, at sources_review)
    sources_review   the person unticks clips, fixes the credits
    scripting        one script per target channel, re-read by gemini-pro (background)
    script_review    the person reads/edits/approves EVERY script (mandatory)
    voicing          narration + a quick preview + automatic checks  (background)
    preview_review   the person watches each preview, may change the voice
    rendering        final renders, then each video joins Publication (background)
    done
    error            with the step to retry

A target = one channel: its language, voice and music come from its
settings (Réglages → Voix / channel), the voice can be changed per project.
"""

import os
import re
import shutil
import uuid
from datetime import datetime
from typing import Callable, Dict, List, Optional

import db
from adaptation import checks, finder, langs, reference, render, script, settings, sources, voices

BUSY = {"analysing", "scripting", "voicing", "rendering"}
Report = Callable[[str, float], None]


class PipelineError(RuntimeError):
    pass


def project_dir(pid: str) -> str:
    return os.path.join("temp", "adaptations", pid)


def load(pid: str) -> Dict:
    p = db.get_adaptation(pid)
    if not p:
        raise PipelineError("Projet introuvable.")
    return p


def save(p: Dict) -> Dict:
    return db.save_adaptation(p)


def target(p: Dict, channel: str) -> Dict:
    t = next((t for t in p["targets"] if t["channel"] == channel), None)
    if not t:
        raise PipelineError(f"La chaîne {channel} ne fait pas partie de ce projet.")
    return t


def _expect(p: Dict, *statuses: str):
    if p["status"] not in statuses:
        raise PipelineError(f"Étape impossible maintenant (le projet est à l'état « {p['status']} »).")


# ---------------------------------------------------------------- creation

def create(reference_url: str, source_urls: List[str], channels: List[Dict]) -> Dict:
    """channels: [{"channel": name, "profile": profile.json dict, "music_dir": path}]"""
    urls = [u.strip() for u in source_urls if u and u.strip()]
    if not reference_url.strip():
        raise PipelineError("Il faut le lien du Short modèle.")
    if not channels:
        raise PipelineError("Choisis au moins une chaîne cible.")
    targets = []
    for c in channels:
        s = settings.channel_settings(c["profile"])
        if not s["voice_id"]:
            raise PipelineError(f"La chaîne {c['channel']} n'a pas de voix : choisis-en une dans Réglages → Voix.")
        music = os.path.join(c["music_dir"], s["music_file"]) if s["music_file"] else None
        targets.append({"channel": c["channel"], "language": s["language"], "voice_id": s["voice_id"],
                        "music_path": music if music and os.path.exists(music) else None,
                        "music_start": s["music_start"], "script": None, "approved": False,
                        "validated": False, "video_id": None})
    pid = "ad_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]   # two in one second
    return save({"project_id": pid, "status": "analysing", "reference_url": reference_url.strip(),
                 "source_urls": urls, "reference": None, "suggestions": None, "sources": [], "clips": {},
                 "credits": "", "credits_auto": "",
                 "targets": targets, "error": None, "failed_step": None})


def fail(pid: str, step: str, err: Exception):
    p = load(pid)
    p.update(status="error", error=str(err)[:500], failed_step=step)
    save(p)


# ---------------------------------------------------------------- 1. analysis

def guess_credits(metas: List[Dict], clips: Dict[str, Dict]) -> str:
    """Handles seen in the watermarks first (often the real author), then the
    media names in logos, then the accounts the sources came from."""
    seen, out = set(), []

    def add(name):
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    used = [c for c in clips.values() if c.get("usable")]
    for c in used:
        for m in c.get("marks") or []:
            for h in re.findall(r"@[\w.]{3,}", m):
                add(h.rstrip("."))
    for c in used:
        for m in c.get("marks") or []:
            hit = re.search(r"logo\s+(?:de\s+)?([A-Z0-9][\w]+)", m, re.I)
            if hit and hit.group(1).lower() not in {"tiktok", "instagram", "youtube", "facebook", "de", "la", "du"}:
                add(hit.group(1))
    if not out:
        for i in sorted({c["source"] for c in used}):
            add((metas[i] if i < len(metas) else {}).get("handle"))
    return " · ".join(out[:4])


def run_analysis(pid: str, report: Optional[Report] = None):
    """The reference and the suggestions are made once; only the sources not
    analysed yet are downloaded (sources can be added in several goes)."""
    report = report or (lambda phase, f: None)
    p = load(pid)
    try:
        if not p.get("reference"):
            report("analyse du Short modèle", 0.02)
            p["reference"] = reference.analyse(p["reference_url"])
            save(p)
        if not p.get("suggestions"):
            p["suggestions"] = finder.suggest(p["reference"], p["reference_url"],
                                              report=lambda ph, f: report(ph, 0.1 + 0.1 * f))
            save(p)
        if not p["source_urls"]:
            p.update(status="sources_search", error=None, failed_step=None)
            save(p)
            report("terminé", 1.0)
            return
        base = project_dir(pid)
        clips, metas = dict(p.get("clips") or {}), list(p.get("sources") or [])
        ids = (i for i in sources._ids() if i not in clips)
        todo = list(range(len(metas), len(p["source_urls"])))
        for k, i in enumerate(todo):
            url, n = p["source_urls"][i], len(todo)
            report(f"source {k + 1}/{n} : téléchargement", 0.2 + 0.75 * k / n)
            path = sources.download(url, os.path.join(base, "src"), f"src{i}",
                                    (p.get("source_sections") or {}).get(url))
            meta = sources.source_meta(path)
            report(f"source {k + 1}/{n} : découpage et analyse", 0.2 + 0.75 * (k + 0.3) / n)
            for c in sources.analyse_source(path, i, os.path.join(base, "work"), ids):
                clips[c["id"]] = c
            metas.append(meta)
        p = load(pid)
        guess = guess_credits(metas, clips)
        if not p.get("credits") or p.get("credits") == p.get("credits_auto"):     # never overwrite a correction
            p["credits"] = guess
        p.update(clips=clips, sources=metas, credits_auto=guess, status="sources_review", error=None,
                 failed_step=None)
        if not any(c["usable"] for c in clips.values()):
            p.update(status="error", error="Aucun clip utilisable dans ces sources.", failed_step="analysing")
        save(p)
    except Exception as e:
        fail(pid, "analysing", e)
    report("terminé", 1.0)


def add_sources(pid: str, urls: List[str]) -> Dict:
    """Links picked among the suggestions (or pasted): analysed on top of the
    clips already there."""
    p = load(pid)
    _expect(p, "sources_search", "sources_review")
    have = set(p["source_urls"])
    new = []
    for u in urls:
        u = (u or "").strip()
        if u and u not in have:
            have.add(u)
            new.append(u)
    if not new:
        raise PipelineError("Aucun nouveau lien : coche une vidéo proposée ou colle un lien.")
    p["source_urls"] = p["source_urls"] + new
    sug = p.get("suggestions") or {}
    durations = {c["url"]: c.get("duration") for s in sug.get("scenes") or [] for c in s.get("candidats") or []}
    durations.update({v["url"]: v.get("duration") for a in sug.get("comptes") or [] for v in a.get("videos") or []})
    for u in new:                       # a long video checked by Gemini: only its good moments
        sec = finder.sections((sug.get("verifs") or {}).get(u), durations.get(u))
        if sec:
            p.setdefault("source_sections", {})[u] = sec
    p["status"] = "analysing"
    return save(p)


def check_candidate(pid: str, scene: int, url: str) -> Dict:
    """Gemini watches one suggested video: does it really contain the scene
    (scene -1: any scene of the model — for a credited account's videos)?"""
    p = load(pid)
    scenes = (p.get("suggestions") or {}).get("scenes") or []
    if scene == -1 and scenes:
        wanted = {"scene": " ; OU ".join(s["scene"] for s in scenes),
                  "indices": " ; ".join(s["indices"] for s in scenes if s.get("indices"))}
    elif 0 <= scene < len(scenes):
        wanted = scenes[scene]
    else:
        raise PipelineError("Scène inconnue.")
    try:
        result = finder.check(url, wanted)
    except finder.FinderError as e:
        raise PipelineError(str(e))
    p = load(pid)
    p["suggestions"].setdefault("verifs", {})[url] = {**result, "scene": scene}
    return save(p)


def set_sources(pid: str, usable: Optional[Dict[str, bool]] = None, credits: Optional[str] = None) -> Dict:
    p = load(pid)
    _expect(p, "sources_review")
    for cid, ok in (usable or {}).items():
        if cid in p["clips"]:
            p["clips"][cid]["usable"] = bool(ok)
    if credits is not None:
        p["credits"] = " ".join(credits.split())[:120]
    return save(p)


# ---------------------------------------------------------------- 2. scripts

def run_scripts(pid: str, report: Optional[Report] = None):
    report = report or (lambda phase, f: None)
    p = load(pid)
    try:
        clips = {k: c for k, c in p["clips"].items() if c.get("usable")}
        n = len(p["targets"])
        for i, t in enumerate(p["targets"]):
            label = langs.lang(t["language"])["label"]
            report(f"script {label}", (i + 0.1) / n)
            sc = script.write(p["reference"], clips, t["language"])
            report(f"relecture {label}", (i + 0.6) / n)
            sc = script.critique(sc, t["language"], clips)
            t.update(script=sc, problems=script.problems(sc, p["clips"], t["language"]), approved=False,
                     validated=False, preview=None, voice=None)
        p.update(status="script_review", error=None, failed_step=None)
        save(p)
    except Exception as e:
        fail(pid, "scripting", e)
    report("terminé", 1.0)


def start_scripts(pid: str) -> Dict:
    p = load(pid)
    _expect(p, "sources_review")
    if not any(c.get("usable") for c in p["clips"].values()):
        raise PipelineError("Garde au moins un clip.")
    p["status"] = "scripting"
    return save(p)


def edit_script(pid: str, channel: str, new: Dict) -> Dict:
    p = load(pid)
    _expect(p, "script_review")
    t = target(p, channel)
    sc = script.normalise({**(t["script"] or {}), **new}, p["clips"])
    t.update(script={**sc, "corrections": (t["script"] or {}).get("corrections", [])},
             problems=script.problems(sc, p["clips"], t["language"]), approved=False)
    return save(p)


def revise_script(pid: str, channel: str, request: str) -> Dict:
    p = load(pid)
    _expect(p, "script_review")
    t = target(p, channel)
    sc = script.revise(t["script"], {k: c for k, c in p["clips"].items() if c.get("usable")}, request)
    t.update(script=sc, problems=script.problems(sc, p["clips"], t["language"]), approved=False)
    return save(p)


def approve_script(pid: str, channel: str) -> Dict:
    p = load(pid)
    _expect(p, "script_review")
    t = target(p, channel)
    problems = script.problems(t["script"] or {}, p["clips"], t["language"])
    if problems:
        raise PipelineError("À corriger avant de valider : " + " ".join(problems))
    t["approved"] = True
    return save(p)


# ---------------------------------------------------------------- 3. voice + preview

def _make(p: Dict, t: Dict, preview: bool, report: Report, share: float, offset: float) -> Dict:
    base = os.path.join(project_dir(p["project_id"]), t["channel"])
    voice_mp3 = os.path.join(base, "voice.mp3")
    if not t.get("voice") or t["voice"].get("voice_id") != t["voice_id"]:     # never pay twice for the same narration
        report(f"voix {t['channel']}", offset)
        t["voice"] = voices.synthesize(t["script"]["passages"], t["voice_id"], t["language"], voice_mp3)
        t["voice"]["voice_id"] = t["voice_id"]
    out = os.path.join(base, "preview.mp4" if preview else "final.mp4")
    report(f"{'aperçu' if preview else 'rendu'} {t['channel']}", offset + share * 0.3)
    r = render.render(t["voice"]["passages"], t["voice"]["words"], p["clips"], voice_mp3, t["language"], out,
                      os.path.join(base, "work"), credit=p["credits"],
                      music=(t["music_path"], t["music_start"]) if t.get("music_path") else None, preview=preview,
                      progress_cb=lambda f: report(f"{'aperçu' if preview else 'rendu'} {t['channel']}",
                                                   offset + share * (0.3 + 0.6 * f)))
    c = checks.verify(out, voice_mp3, t["voice"]["passages"])
    return {"path": out, "summary": r, "checks": c}


def run_voices(pid: str, report: Optional[Report] = None, only: Optional[str] = None):
    """Narration + preview + checks, for every target (or one, after a voice change)."""
    report = report or (lambda phase, f: None)
    p = load(pid)
    try:
        todo = [t for t in p["targets"] if (only is None or t["channel"] == only)]
        for i, t in enumerate(todo):
            t["preview"] = _make(p, t, True, report, 1 / len(todo), i / len(todo))
            t["validated"] = False
            save(p)
        p.update(status="preview_review", error=None, failed_step=None)
        save(p)
    except Exception as e:
        fail(pid, "voicing", e)
    report("terminé", 1.0)


def start_voices(pid: str) -> Dict:
    p = load(pid)
    _expect(p, "script_review")
    missing = [t["channel"] for t in p["targets"] if not t["approved"]]
    if missing:
        raise PipelineError("Scripts pas encore validés : " + ", ".join(missing))
    p["status"] = "voicing"
    return save(p)


def change_voice(pid: str, channel: str, voice_id: str) -> Dict:
    p = load(pid)
    _expect(p, "preview_review")
    if not db.get_voice(voice_id):
        raise PipelineError("Cette voix n'est pas dans la bibliothèque (Réglages → Voix).")
    t = target(p, channel)
    t.update(voice_id=voice_id, voice=None, validated=False)
    p["status"] = "voicing"
    return save(p)


def validate_preview(pid: str, channel: str) -> Dict:
    p = load(pid)
    _expect(p, "preview_review")
    t = target(p, channel)
    if not (t.get("preview") or {}).get("checks", {}).get("ok"):
        raise PipelineError("Le contrôle automatique a trouvé un problème : refais l'aperçu avant de valider.")
    t["validated"] = True
    return save(p)


# ---------------------------------------------------------------- 4. final render -> Publication

def publication_record(p: Dict, t: Dict, path: str) -> Dict:
    sc = t["script"]
    label = langs.lang(t["language"])["credit_label"]
    desc = sc.get("description") or ""
    if p.get("credits"):
        desc = f"{desc}\n\n{label} {p['credits']}".strip()
    vid = f"{t['channel']}_{p['project_id']}"
    now = datetime.now().isoformat()
    ai = {"optimized_title": sc["titre"], "title": sc["titre"], "description_suggestions": [desc],
          "description": desc, "tags": sc.get("tags") or []}
    return {"video_id": vid, "batch_id": p["project_id"], "channel": t["channel"], "url": p["reference_url"],
            "status": "ready_for_upload", "priority": "normal", "source": "adaptation",
            "adaptation_project": p["project_id"], "original_title": sc["titre"], "video_path": path,
            "ai_data": ai, "added_at": now, "updated_at": now}


def start_render(pid: str) -> Dict:
    p = load(pid)
    _expect(p, "preview_review")
    if not any(t["validated"] for t in p["targets"]):
        raise PipelineError("Valide au moins un aperçu avant le rendu final.")
    p["status"] = "rendering"
    return save(p)


def run_final(pid: str, report: Optional[Report] = None):
    report = report or (lambda phase, f: None)
    p = load(pid)
    try:
        todo = [t for t in p["targets"] if t["validated"] and not t.get("video_id")]
        for i, t in enumerate(todo):
            made = _make(p, t, False, report, 1 / len(todo), i / len(todo))
            if not made["checks"]["ok"]:
                raise PipelineError(f"{t['channel']} : " + " ".join(made["checks"]["problems"]))
            dest = os.path.join("processed_videos", f"{t['channel']}_{pid}.mp4")
            os.makedirs("processed_videos", exist_ok=True)
            shutil.copy(made["path"], dest)
            rec = publication_record(p, t, dest)
            db.upsert_video(rec["video_id"], rec)
            t.update(video_id=rec["video_id"], final=made)
            save(p)
        waiting = [t for t in p["targets"] if not t.get("video_id")]
        p.update(status="preview_review" if waiting else "done", error=None, failed_step=None)
        save(p)
    except Exception as e:
        fail(pid, "rendering", e)
    report("terminé", 1.0)


RUNNERS = {"analysing": run_analysis, "scripting": run_scripts, "voicing": run_voices, "rendering": run_final}


def retry(pid: str) -> str:
    """Puts a failed project back on the step that failed; returns that step."""
    p = load(pid)
    _expect(p, "error")
    step = p.get("failed_step") or "analysing"
    p.update(status=step, error=None)
    save(p)
    return step


def recover_interrupted() -> int:
    """A server restart kills background steps: mark them as failed so they can be retried."""
    n = 0
    for p in db.list_adaptations():
        if p["status"] in BUSY:
            p.update(error="Interrompu par un redémarrage du serveur : relance l'étape.", failed_step=p["status"],
                     status="error")
            save(p)
            n += 1
    return n
