"""
An adaptation project, step by step.

    analysing        Gemini reads the reference Short (once) and lists the
                     scenes to find, with YouTube candidates; the sources
                     given are downloaded and cut into clips         (background)
    sources_search   no source yet: the person picks candidates / pastes links
                     (sources can also be added later, at sources_review)
    sources_review   the person unticks clips, fixes the credits
    plan_review      "Script d'abord" mode: the storyboard (one image per plan,
                     shared by every language) and its texts, written before any
                     footage, reviewed and approved per language (mandatory)
    searching        the footage for each plan: the four searches on the plan's
                     image, Gemini's checks, the best moment picked   (background)
    images_review    the person sees, plan by plan, the video and moment picked; may
                     give a link for a plan, adapt a plan to an image found, set it aside
    fetching         only the picked moments are downloaded, one clip per plan
                     (background), then the usual script_review with clips
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
from typing import Callable, Dict, List, Optional, Tuple

import db
from adaptation import annotate, checks, finder, langs, reference, render, script, settings, sources, storyboard, voices

BUSY = {"analysing", "searching", "fetching", "scripting", "voicing", "rendering"}
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

MODES = ("sources", "script")


def create(reference_url: str, source_urls: List[str], channels: List[Dict], mode: str = "sources") -> Dict:
    """channels: [{"channel": name, "profile": profile.json dict, "music_dir": path}]
    mode: "sources" (find the footage, then write) or "script" (write, then find the footage)."""
    urls = [u.strip() for u in source_urls if u and u.strip()]
    if mode not in MODES:
        raise PipelineError("Mode inconnu.")
    if mode == "script":
        urls = []                       # the footage is searched for the script, plan by plan
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
    return save({"project_id": pid, "status": "analysing", "reference_url": reference_url.strip(), "mode": mode,
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
    media names in logos, then the accounts the sources came from. Never a
    bare account number (TikTok shows one when a user has no name)."""
    seen, out = set(), []

    def add(name):
        if not name or re.fullmatch(r"@?[-\d_.]*", name):   # "@7315046821897962529", VK's "@-201897941": numbers, not names
            return
        if name.lower() not in seen:
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
        if p.get("mode") == "script":
            write_storyboard(p, report)
            report("terminé", 1.0)
            return
        if not p.get("suggestions"):
            alone = not p["source_urls"]            # nothing given: the search is the step, give it more room
            share = 0.6 if alone else 0.1
            p["suggestions"] = finder.suggest(p["reference"], p["reference_url"],
                                              work_dir=os.path.join(project_dir(pid), "finder"),
                                              report=lambda ph, f: report(ph, 0.1 + share * f))
            save(p)
            if alone:
                finder.verify_best(p["suggestions"], p["reference"],
                                   report=lambda ph, f: report(ph, 0.7 + 0.28 * f))
                save(p)
        if not p["source_urls"]:
            p.update(status="sources_search", error=None, failed_step=None)
            save(p)
            report("terminé", 1.0)
            return
        base = project_dir(pid)
        clips, metas = dict(p.get("clips") or {}), list(p.get("sources") or [])
        ids = (i for i in sources._ids() if i not in clips)
        metas += [None] * (len(p["source_urls"]) - len(metas))
        todo = [i for i, m in enumerate(metas) if m is None or m.get("failed")]    # new ones, and the failed ones again
        for k, i in enumerate(todo):
            url, n = p["source_urls"][i], len(todo)
            report(f"source {k + 1}/{n} : téléchargement", 0.2 + 0.75 * k / n)
            try:
                path = sources.download(url, os.path.join(base, "src"), f"src{i}",
                                        (p.get("source_sections") or {}).get(url))
            except sources.SourceError as e:        # one dead link must not block the others
                metas[i] = {"url": url, "failed": str(e)}
                continue
            meta = sources.source_meta(path)
            report(f"source {k + 1}/{n} : découpage et analyse", 0.2 + 0.75 * (k + 0.3) / n)
            for c in sources.analyse_source(path, i, os.path.join(base, "work"), ids):
                clips[c["id"]] = c
            metas[i] = meta
        p = load(pid)
        guess = guess_credits(metas, clips)
        if not p.get("credits") or p.get("credits") == p.get("credits_auto"):     # never overwrite a correction
            p["credits"] = guess
        p.update(clips=clips, sources=metas, credits_auto=guess, status="sources_review", error=None,
                 failed_step=None)
        if not any(c["usable"] for c in clips.values()):
            failed = [m["failed"] for m in metas if m.get("failed")]
            p.update(status="error", failed_step="analysing",
                     error=" ".join(failed) if failed and not clips else "Aucun clip utilisable dans ces sources.")
        save(p)
    except Exception as e:
        fail(pid, "analysing", e)
    report("terminé", 1.0)


# ---------------------------------------------------------------- "Script d'abord": the storyboard

def _codes(p: Dict) -> List[str]:
    return list(dict.fromkeys(t["language"] for t in p["targets"]))


def _refresh_plan(p: Dict, keep_approved: Optional[str] = None):
    """Durations, each language's script and its problems, from the storyboard."""
    b, codes = p["storyboard"], _codes(p)
    storyboard.durations(b, codes)
    for t in p["targets"]:
        t["script"] = storyboard.script_for(b, t["language"])
        t["problems"] = storyboard.problems(b, t["language"])
        if t["channel"] != keep_approved:
            t["approved"] = False


def write_storyboard(p: Dict, report: Report):
    codes = _codes(p)
    report("écriture du storyboard", 0.35)
    b = storyboard.write(p["reference"], codes)
    report("relecture (rétention, langue, images)", 0.65)
    b = storyboard.critique(b, codes)
    left = [f"[{c}] {x}" for c in codes for x in storyboard.problems(b, c)]
    if left:                            # what the re-read missed is fixed once more, then shown
        report("correction", 0.85)
        try:
            fixed = storyboard.revise(b, codes, "Corrige ces problemes : " + " ".join(left))
            if sum(len(storyboard.problems(fixed, c)) for c in codes) < len(left):
                b = {**fixed, "corrections": b.get("corrections", []) + ["Correction automatique : " + " ".join(left)]}
        except script.ScriptError:
            pass
    p = load(p["project_id"])
    p["storyboard"] = b
    _refresh_plan(p)
    p.update(status="plan_review", error=None, failed_step=None)
    save(p)


def edit_plan(pid: str, channel: str, new: Dict) -> Dict:
    """new: {titre, description, tags, passages: [{image, bandeau, texte, mots_cles}]} — the
    images belong to every language: changing one asks every language to be approved again."""
    p = load(pid)
    _expect(p, "plan_review")
    t = target(p, channel)
    b, code = p["storyboard"], t["language"]
    passages = new.get("passages") or []
    if len(passages) != len(b["plans"]):
        raise PipelineError("Le nombre de plans ne peut pas changer ici : demande-le à l'IA.")
    images_changed = False
    for plan, x in zip(b["plans"], passages):
        if "annotation" in x:           # an arrow/circle is shared by every language, like the image
            plan["annotation"] = storyboard.clean_annotation(x.get("annotation"))
        image = " ".join(str(x.get("image", plan["image"])).split())
        images_changed |= image != plan["image"]
        plan["image"] = image
        plan["textes"][code] = {"bandeau": str(x.get("bandeau") or "").strip(), "texte": " ".join(str(x.get("texte") or "").split()),
                                "mots_cles": [str(m) for m in x.get("mots_cles") or [] if str(m).strip()][:3]}
    b["meta"][code] = {"titre": str(new.get("titre") or "").strip()[:100], "description": str(new.get("description") or "").strip(),
                       "tags": [str(x).strip() for x in new.get("tags") or [] if str(x).strip()][:15]}
    approved = {x["channel"] for x in p["targets"] if x.get("approved")} - {channel}
    _refresh_plan(p)
    if not images_changed:              # only this language's text changed: the others stay approved
        for x in p["targets"]:
            x["approved"] = x["channel"] in approved
    return save(p)


def revise_plan(pid: str, channel: str, request: str) -> Dict:
    p = load(pid)
    _expect(p, "plan_review")
    target(p, channel)
    b = storyboard.revise(p["storyboard"], _codes(p), request)
    p["storyboard"] = b
    _refresh_plan(p)
    return save(p)


def approve_plan(pid: str, channel: str) -> Dict:
    p = load(pid)
    _expect(p, "plan_review")
    t = target(p, channel)
    left = storyboard.problems(p["storyboard"], t["language"])
    if left:
        raise PipelineError("À corriger avant de valider : " + " ".join(left))
    t["approved"] = True
    return save(p)


def _judged_plans(p: Dict) -> Optional[List[Dict]]:
    """What a check compares a video with: the reference's shots, or in
    "Script d'abord" the storyboard's images themselves (the scenes)."""
    return None if p.get("mode") == "script" else (p.get("reference") or {}).get("plans")


def start_images(pid: str) -> Dict:
    p = load(pid)
    _expect(p, "plan_review", "images_review")
    missing = [t["channel"] for t in p["targets"] if not t.get("approved")]
    if missing:
        raise PipelineError("Scripts pas encore validés : " + ", ".join(missing))
    p["status"] = "searching"
    return save(p)


def run_images(pid: str, report: Optional[Report] = None):
    """Every plan's footage: search words from its image, the four searches,
    Gemini's checks (twice as many as plans: each plan's best by words, then
    by picture), then the best checked moment picked for each plan."""
    report = report or (lambda phase, f: None)
    p = load(pid)
    try:
        plans = p["storyboard"]["plans"]
        report("recherches pour chaque plan", 0.02)
        queries = finder.plan_queries(finder.wanted_from_storyboard(plans, {}))
        local = lambda found: {i: {"pays": q["pays"], "langue": q["langue"], "recherches": q["locales"]}
                               for i, q in queries.items() if q.get("locales")}
        sug = finder.suggest(p["reference"], p["reference_url"], work_dir=os.path.join(project_dir(pid), "finder"),
                             wanted=finder.wanted_from_storyboard(plans, queries), local=local,
                             report=lambda ph, f: report(ph, 0.05 + 0.55 * f))
        finder.verify_best(sug, {"plans": [], **{k: p["reference"].get(k) for k in ("script_complet", "duree_s")}},
                           n=min(14, 2 * len(plans)),
                           report=lambda ph, f: report(ph, 0.62 + 0.36 * f))
        p = load(pid)
        p.update(suggestions=sug, picks=finder.auto_pick(sug, plans), status="images_review", error=None,
                 failed_step=None)
        save(p)
    except Exception as e:
        fail(pid, "searching", e)
    report("terminé", 1.0)


def choose_pick(pid: str, plan: int, url: Optional[str], debut: float = 0.0, fin: Optional[float] = None) -> Dict:
    """The person's choice for one plan (url None: no video for this plan)."""
    p = load(pid)
    _expect(p, "images_review")
    picks = p.get("picks") or []
    if not 0 <= plan < len(picks):
        raise PipelineError("Plan inconnu.")
    if url is None:
        picks[plan] = None
    else:
        v = ((p.get("suggestions") or {}).get("verifs") or {}).get(url) or {}
        e = (v.get("par_scene") or {}).get(str(plan)) or {}
        c = next((c for c in finder.all_candidates(p.get("suggestions") or {}) if c["url"] == url), {})
        picks[plan] = {"url": url, "titre": c.get("title") or v.get("title") or url, "niveau": e.get("niveau") or "choisie",
                       "moment": {"debut": float(debut), "fin": float(fin if fin is not None else debut + 4)},
                       "raison": e.get("raison") or "", "auto": False, "remontage": bool(v.get("remontage")),
                       "defauts": e.get("defauts") or ""}
    p["picks"] = picks
    return save(p)


def _active(p: Dict) -> List[int]:
    return [k for k, pl in enumerate(p["storyboard"]["plans"]) if not pl.get("retire")]


def skip_plan(pid: str, plan: int, skip: bool = True) -> Dict:
    """Set a plan aside (the video is made without it) or bring it back."""
    p = load(pid)
    _expect(p, "images_review")
    plans = p["storyboard"]["plans"]
    if not 0 <= plan < len(plans):
        raise PipelineError("Plan inconnu.")
    if skip and len(_active(p)) <= 3:
        raise PipelineError("Il faut garder au moins 3 plans.")
    plans[plan]["retire"] = bool(skip)
    return save(p)


def _best_moment(v: Dict, plan: int) -> Optional[Dict]:
    e = (v.get("par_scene") or {}).get(str(plan)) or {}
    if v.get("copie") or e.get("niveau") not in finder.RANK:
        return None
    ms = e.get("moments") or [{"debut": 0}]
    m = max(ms, key=lambda m: float(m.get("fin") or 0) - float(m.get("debut") or 0))
    a = float(m.get("debut") or 0)
    return {"debut": a, "fin": float(m["fin"]) if m.get("fin") is not None else a + 4, "niveau": e["niveau"],
            "raison": e.get("raison") or ""}


def check_plan_link(pid: str, plan: int, url: str, checker=None) -> Dict:
    """Your link for one plan: judged like the others; if it fits this plan,
    it becomes the plan's pick."""
    p = load(pid)
    _expect(p, "images_review")
    sug = p["suggestions"]
    if not 0 <= plan < len(sug["scenes"]):
        raise PipelineError("Plan inconnu.")
    url = (url or "").strip()
    if not url.startswith("http"):
        raise PipelineError("Colle un lien (https://…).")
    known = {finder.same_video(c["url"]): c["url"] for c in finder.all_candidates(sug)}
    url = known.get(finder.same_video(url), url)
    model = finder.model_of(p.get("reference"))
    try:
        r = (checker or (lambda u, sc, pl: finder.check(u, sc, pl, **({"model": model} if model else {}))))(
            url, sug["scenes"], None)
    except finder.FinderError as e:
        raise PipelineError(str(e))
    p = load(pid)
    sug = p["suggestions"]
    sug.setdefault("verifs", {})[url] = r
    cands = sug["scenes"][plan].setdefault("candidats", [])
    if not any(c["url"] == url for c in cands):
        from adaptation.imagesearch import platform
        vid = finder._video_id(url)
        cands.insert(0, {"url": url, "id": vid or url, "title": r.get("title") or url, "origines": ["perso"],
                         "platform": platform(url), "duration": r.get("duration"),
                         "thumb": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else ""})
    m = _best_moment(r, plan)
    if m:
        p["picks"][plan] = {"url": url, "titre": r.get("title") or url, "niveau": m["niveau"],
                            "moment": {"debut": m["debut"], "fin": m["fin"]}, "raison": m["raison"], "auto": False}
    return save(p)


def adapt_plan(pid: str, plan: int) -> Dict:
    """A plan nobody filmed: rewritten (every language) around an image
    already found and checked, which becomes its pick."""
    p = load(pid)
    _expect(p, "images_review")
    b, sug, picks = p["storyboard"], p["suggestions"], p["picks"]
    used = {(x["url"], round(x["moment"]["debut"])) for k, x in enumerate(picks) if x and k != plan}
    options = []
    for url, v in (sug.get("verifs") or {}).items():
        if v.get("copie"):
            continue
        for e in (v.get("par_scene") or {}).values():
            if e.get("niveau") not in finder.RANK:
                continue
            for m in e.get("moments") or []:
                a = float(m.get("debut") or 0)
                if (url, round(a)) in used or any(o["url"] == url and abs(o["debut"] - a) < 2 for o in options):
                    continue
                options.append({"url": url, "debut": a, "fin": float(m["fin"]) if m.get("fin") is not None else a + 4,
                                "vu": m.get("ce_qu_on_voit") or e.get("raison") or v.get("raison") or url})
    options = options[:15]
    try:
        choice, new = storyboard.adapt_to(b, plan, options, _codes(p))
    except script.ScriptError as e:
        raise PipelineError(str(e))
    p = load(pid)
    old = p["storyboard"]["plans"][plan]
    p["storyboard"]["plans"][plan] = {**new, "role": old["role"], "plans_modele": [], "adapte": True}
    o = options[choice]
    p["picks"][plan] = {"url": o["url"], "titre": next((c.get("title") for c in finder.all_candidates(p["suggestions"])
                                                        if c["url"] == o["url"]), o["url"]),
                        "niveau": "adaptée", "moment": {"debut": o["debut"], "fin": o["fin"]}, "raison": o["vu"], "auto": False}
    _refresh_plan(p)
    for t in p["targets"]:              # reviewed before: only the adapted plan changed, shown on the next screen
        t["approved"] = True
    return save(p)


def start_fetch(pid: str) -> Dict:
    p = load(pid)
    _expect(p, "images_review")
    missing = [k + 1 for k in _active(p) if not p["picks"][k]]
    if missing:
        raise PipelineError("Plans sans vidéo : " + ", ".join(map(str, missing)) +
                            ". Choisis une vidéo, adapte la phrase ou retire le plan.")
    left = [x for t in p["targets"] for x in storyboard.problems(       # a plan set aside may make it short: not a blocker
        {**p["storyboard"], "plans": [pl for pl in p["storyboard"]["plans"] if not pl.get("retire")]}, t["language"])
        if not x.startswith("Durée totale")]
    if left:
        raise PipelineError("À corriger d'abord : " + " ".join(left))
    p["status"] = "fetching"
    return save(p)


def _spans(items: List[Tuple[int, float, float]]) -> List[List[float]]:
    spans = []
    for _, a, b in sorted(items, key=lambda x: x[1]):
        a, b = max(0.0, a - 1.0), b + 1.0
        if spans and a <= spans[-1][1] + 2:
            spans[-1][1] = max(spans[-1][1], b)
        else:
            spans.append([a, b])
    return spans


def run_fetch(pid: str, report: Optional[Report] = None):
    """Only the picked moments are downloaded (a short video whole), then one
    clean clip per plan, cut on its moment and long enough for its sentence;
    each language's script gets its clips and goes to the usual review. Back
    from the script to change one plan, the clips of the unchanged plans are
    kept (their pick is the same, their file still there)."""
    report = report or (lambda phase, f: None)
    p = load(pid)
    try:
        plans, picks, sug = p["storyboard"]["plans"], p["picks"], p.get("suggestions") or {}
        durations = {c["url"]: c.get("duration") for c in finder.all_candidates(sug)}
        durations.update({u: v.get("duration") for u, v in (sug.get("verifs") or {}).items() if v.get("duration")})
        def pick_key(k: int) -> List:
            m = picks[k]["moment"]
            end = m["fin"] if picks[k].get("extrait") else max(m["fin"], m["debut"] + plans[k]["duree"])
            return [picks[k]["url"], round(m["debut"], 2), round(end, 2)]
        old = p.get("clips") or {}
        clips = {f"P{k + 1}": old[f"P{k + 1}"] for k in _active(p)
                 if (old.get(f"P{k + 1}") or {}).get("pick_key") == pick_key(k) and os.path.exists(old[f"P{k + 1}"]["src"])}
        by_url: Dict[str, List[Tuple[int, float, float]]] = {}
        for k in _active(p):
            if f"P{k + 1}" in clips:
                continue
            m = picks[k]["moment"]
            end = m["fin"] if picks[k].get("extrait") else max(m["fin"], m["debut"] + plans[k]["duree"])   # an excerpt stays short
            by_url.setdefault(picks[k]["url"], []).append((k, m["debut"], end))
        if clips:
            report(f"{len(clips)} plan(s) inchangé(s) : clips gardés", 0.03)
        base, stamp = project_dir(pid), datetime.now().strftime("%H%M%S") + "_" + uuid.uuid4().hex[:4]   # two in one second
        for i, (url, items) in enumerate(by_url.items()):
            report(f"vidéo {i + 1}/{len(by_url)} : téléchargement des moments choisis", 0.05 + 0.8 * i / len(by_url))
            dur = durations.get(url)
            spans = None if (dur and dur <= 120) else _spans(items)
            name = f"src{stamp}_{i}"           # never over a file a kept clip still uses
            try:
                path = sources.download(url, os.path.join(base, "src"), name, spans)
            except sources.SourceError:
                if spans is None:
                    raise
                spans = None                    # some sites refuse a section: the whole video, then
                path = sources.download(url, os.path.join(base, "src"), name)
            meta = sources.source_meta(path)

            def file_time(t: float) -> float:
                if not spans:
                    return t
                offset = 0.0
                for a, b in spans:
                    if a <= t <= b:
                        return offset + (t - a)
                    offset += b - a
                return t
            report(f"vidéo {i + 1}/{len(by_url)} : nettoyage des images", 0.05 + 0.8 * (i + 0.6) / len(by_url))
            times = [(k, file_time(a), file_time(a) + (b - a)) for k, a, b in items]
            work = os.path.join(base, "work")
            os.makedirs(work, exist_ok=True)
            found = sources.find_boxes([sources.still(path, (a + b) / 2, None, os.path.join(work, f"p{k}.jpg"))
                                        for k, a, b in times])
            report(f"vidéo {i + 1}/{len(by_url)} : contrôle des moments par l'IA", 0.05 + 0.8 * (i + 0.8) / len(by_url))
            try:                        # the same check as an analysed source: a presenter, a title, a logo… is refused
                seen = sources.describe(path, [(a, b) for _, a, b in times])
            except Exception:
                seen = [{} for _ in times]
            for (k, a, b), f, d in zip(times, found, seen):
                c = sources.clip_at(path, i, f"P{k + 1}", a, b, f, desc=plans[k]["image"])
                why = _real_faults(d.get("pourquoi_pas") or "")
                c.update(desc=d.get("visuel") or c["desc"], usable=bool(d.get("utilisable", True)) or not why,
                         why_not=why, shock=bool(d.get("choc_sonore")), pick_key=pick_key(k), meta=meta)
                if picks[k].get("extrait"):     # the reference's own captions are cleaned: not a reason to refuse
                    c.update(extrait=True, usable=True, why_not="")
                clips[f"P{k + 1}"] = c
        srcs = list(dict.fromkeys(c["src"] for c in clips.values()))        # one entry per file, kept clips included
        metas = [next(c.get("meta") or {} for c in clips.values() if c["src"] == src) for src in srcs]
        for c in clips.values():
            c["source"] = srcs.index(c["src"])
        p = load(pid)
        p.update(clips=dict(sorted(clips.items(), key=lambda kv: int(kv[0][1:]))), sources=metas,
                 source_urls=list(dict.fromkeys(picks[k]["url"] for k in _active(p))),
                 status="script_review", error=None, failed_step=None)
        guess = guess_credits(metas, clips)
        names = [n for n in guess.split(" · ") if n] + [m.get("handle") for m in metas if m.get("handle")]
        guess = " · ".join(list(dict.fromkeys(n for n in names if n and not re.fullmatch(r"@?[-\d_.]*", n)))[:4])
        p["credits"], p["credits_auto"] = guess, guess        # every channel whose footage is used, not only watermarks
        for t in p["targets"]:
            full = storyboard.script_for(p["storyboard"], t["language"])
            sc = {**full, "passages": [{**full["passages"][k], "clip": f"P{k + 1}"} for k in _active(p)]}
            t.update(script=sc, problems=_fetched_problems(sc, clips, t["language"]))
            t["approved"] = not t["problems"]
        save(p)
    except Exception as e:
        fail(pid, "fetching", e)
    report("terminé", 1.0)


REAL_FAULTS = finder.REAL_FAULTS
_real_faults = finder.real_faults          # what really refuses a chosen moment (shared with the search)


def _fetched_problems(sc: Dict, clips: Dict[str, Dict], code: str) -> List[str]:
    out = script.problems(sc, clips, code)
    for k, x in enumerate(sc["passages"], 1):
        c = clips.get(x["clip"]) or {}
        why = _real_faults(c.get("why_not") or "") if c and not c.get("usable", True) else ""
        if c and not c.get("usable", True) and (why or not c.get("why_not")):
            out.append(f"Passage {k} : le moment choisi ne convient pas ({why or 'refusé par le contrôle'}) : "
                       f"choisis un autre clip ou « Revenir aux images ».")
    return out


def back_to_images(pid: str) -> Dict:
    """"Script d'abord": from the script screen back to the plan-by-plan
    picks (a moment refused by the check, another one wanted)."""
    p = load(pid)
    _expect(p, "script_review")
    if p.get("mode") != "script":
        raise PipelineError("Seulement en « Script d'abord ».")
    p["status"] = "images_review"
    return save(p)


# ---------------------------------------------------------------- last resort: an excerpt of the reference itself

EXCERPT_MAX = 3.0          # seconds: a short piece under our own voice, banners and arrows stays our creation
EXCERPTS_PER_VIDEO = 2


def _short_file(p: Dict) -> Optional[str]:
    """The reference Short on disk (downloaded for the picture search), or downloaded now."""
    d = os.path.join(project_dir(p["project_id"]), "finder")
    for name in ("short.mp4", "short.webm", "short.mkv"):
        if os.path.exists(os.path.join(d, name)):
            return os.path.join(d, name)
    try:
        return sources.download(p["reference_url"], d, "short")
    except sources.SourceError:
        return None


def excerpt_window(p: Dict, ref_plans: List[int]) -> Tuple[float, float]:
    """Where a scene is in the reference (its shots' times), narrowed to one
    real shot of the downloaded Short and to EXCERPT_MAX seconds from its middle."""
    plans = (p.get("reference") or {}).get("plans") or []
    spans = []
    for i in ref_plans:
        if 0 <= i < len(plans):
            try:
                spans.append((float(plans[i]["debut"]), float(plans[i]["fin"])))
            except (KeyError, TypeError, ValueError):
                continue
    if not spans:
        raise PipelineError("Cette scène n'a pas de plan repéré dans le Short modèle.")
    a, b = min(x for x, _ in spans), max(y for _, y in spans)
    path = _short_file(p)
    if path:
        try:                            # the longest real shot inside the scene: no cut in the excerpt
            shots = [(max(x, a), min(y, b)) for x, y in sources.detect_cuts(path, sources.probe(path), None, min_len=0.8)
                     if min(y, b) - max(x, a) > 0.8]
            longest = max(shots, key=lambda s: s[1] - s[0]) if shots else None
            if longest and longest[1] - longest[0] >= 2.0:
                a, b = longest
            # else: a scene cut in quick shots (measured: 1 s at most) — its cuts all show the same scene, keep them
        except Exception:
            pass
    mid = (a + b) / 2
    half = min(EXCERPT_MAX, b - a) / 2
    return round(mid - half, 2), round(mid + half, 2)


def _excerpts_used(p: Dict) -> int:
    return sum(1 for x in p.get("picks") or [] if x and x.get("extrait")) + \
        sum(1 for c in (p.get("clips") or {}).values() if c.get("extrait") and not str(c.get("id", "")).startswith("P"))


def use_excerpt_for_plan(pid: str, plan: int) -> Dict:
    """"Script d'abord", last resort: a plan nobody filmed takes a few seconds
    of the reference itself (never the hook, two per video at most)."""
    p = load(pid)
    _expect(p, "images_review")
    plans = p["storyboard"]["plans"]
    if not 0 <= plan < len(plans):
        raise PipelineError("Plan inconnu.")
    if plan == 0 or plans[plan]["role"] == "accroche":
        raise PipelineError("Pas pour l'accroche : c'est la scène la plus reconnaissable du modèle.")
    if _excerpts_used(p) >= EXCERPTS_PER_VIDEO and not (p["picks"][plan] or {}).get("extrait"):
        raise PipelineError(f"Déjà {EXCERPTS_PER_VIDEO} extraits du Short modèle : c'est le maximum par vidéo.")
    ref_plans = [k - 1 for k in plans[plan].get("plans_modele") or [] if k >= 1]
    a, b = excerpt_window(p, ref_plans)
    need = plans[plan]["duree"]
    p = load(pid)
    p["picks"][plan] = {"url": p["reference_url"], "titre": "Extrait du Short modèle", "niveau": "extrait",
                        "moment": {"debut": a, "fin": b}, "auto": False, "extrait": True,
                        "raison": (f"La phrase dure {need} s pour {b - a:.1f} s d'extrait : raccourcis-la."
                                   if need > b - a + 0.2 else "Un court extrait, nettoyé, sous ta voix et ton montage.")}
    return save(p)


def add_excerpt_source(pid: str, scene: int) -> Dict:
    """"Sources d'abord", last resort: a scene nobody filmed gets a clip of a
    few seconds from the reference itself, cleaned, credited."""
    p = load(pid)
    _expect(p, "sources_search", "sources_review")
    scenes = (p.get("suggestions") or {}).get("scenes") or []
    if not 0 <= scene < len(scenes):
        raise PipelineError("Scène inconnue.")
    if _excerpts_used(p) >= EXCERPTS_PER_VIDEO:
        raise PipelineError(f"Déjà {EXCERPTS_PER_VIDEO} extraits du Short modèle : c'est le maximum par vidéo.")
    a, b = excerpt_window(p, scenes[scene].get("plans") or [])
    path = _short_file(p)
    if not path:
        raise PipelineError("Le Short modèle n'a pas pu être téléchargé (YouTube refuse) : réessaie plus tard.")
    work = os.path.join(project_dir(pid), "work")
    os.makedirs(work, exist_ok=True)
    found = sources.find_boxes([sources.still(path, (a + b) / 2, None, os.path.join(work, f"excerpt{scene}.jpg"))])
    p = load(pid)
    metas = p.get("sources") or []
    idx = next((i for i, m in enumerate(metas) if m and m.get("url") == p["reference_url"]), None)
    if idx is None:                     # the reference becomes one more (already downloaded) source
        meta = {**sources.source_meta(path), "url": p["reference_url"]}
        metas.append(meta)
        p["source_urls"] = p.get("source_urls", []) + [p["reference_url"]]
        idx = len(metas) - 1
    n = sum(1 for c in p["clips"].values() if c.get("extrait")) + 1
    c = sources.clip_at(path, idx, f"M{n}", a, b, found[0], desc=scenes[scene]["scene"] + " (extrait du Short modèle)")
    c.update(extrait=True, usable=True)
    p["clips"][c["id"]] = c
    p["sources"] = metas
    guess = guess_credits(metas, p["clips"])
    if not p.get("credits") or p.get("credits") == p.get("credits_auto"):
        handle = (metas[idx] or {}).get("handle")
        p["credits"] = " · ".join(x for x in dict.fromkeys([*guess.split(" · "), handle or ""]) if x)[:120]
        p["credits_auto"] = p["credits"]
    p.update(status="sources_review", error=None, failed_step=None)
    return save(p)


def add_sources(pid: str, urls: List[str]) -> Dict:
    """Links picked among the suggestions (or pasted): analysed on top of the
    clips already there."""
    p = load(pid)
    _expect(p, "sources_search", "sources_review")
    dead = [i for i, m in enumerate(p.get("sources") or []) if m and m.get("failed")]
    have = {finder.same_video(u) for u in p["source_urls"]} - {finder.same_video(p["source_urls"][i]) for i in dead}
    new = []
    for u in urls:
        u = (u or "").strip()
        if u and finder.same_video(u) not in have:      # the same video spelled http/https, with/without www
            have.add(finder.same_video(u))
            new.append(u)
    if not new:
        raise PipelineError("Aucun nouveau lien : coche une vidéo proposée ou colle un lien.")
    p["source_urls"] = p["source_urls"] + new
    sug = p.get("suggestions") or {}
    durations = {c["url"]: c.get("duration") for c in finder.all_candidates(sug)}
    durations.update({u: v["duration"] for u, v in (sug.get("verifs") or {}).items() if v.get("duration")})
    for u in new:                       # a long video checked by Gemini: only its good moments
        sec = finder.sections((sug.get("verifs") or {}).get(u), durations.get(u))
        if sec:
            p.setdefault("source_sections", {})[u] = sec
    p["status"] = "analysing"
    return save(p)


def check_candidate(pid: str, url: str) -> Dict:
    """Gemini watches one suggested video against every plan of the model:
    the original, equivalent or partial footage, and where."""
    p = load(pid)
    scenes = (p.get("suggestions") or {}).get("scenes") or []
    if not scenes:
        raise PipelineError("Aucune scène à chercher dans ce projet.")
    try:
        model = finder.model_of(p.get("reference"))
        result = finder.check(url, scenes, _judged_plans(p), **({"model": model} if model else {}))
    except finder.FinderError as e:
        raise PipelineError(str(e))
    p = load(pid)
    p["suggestions"].setdefault("verifs", {})[url] = result
    (p["suggestions"].get("verif_errors") or {}).pop(url, None)
    for c in p["suggestions"].get("perso") or []:          # one of your links: its real title now
        if c["url"] == url:
            c.update(title=result.get("title") or c.get("title"), duration=result.get("duration") or c.get("duration"))
    return save(p)


def check_own(pid: str, urls: List[str], checker=None) -> Dict:
    """The person's own links, judged like the suggestions (plan by plan,
    with the moments), in parallel; the useful ones come back ticked."""
    from concurrent.futures import ThreadPoolExecutor
    p = load(pid)
    _expect(p, "sources_search", "sources_review")
    sug = p.get("suggestions")
    if not sug or not sug.get("scenes"):
        raise PipelineError("Aucune scène à chercher dans ce projet.")
    known = {finder.same_video(u): u for u in p["source_urls"] + [c["url"] for c in finder.all_candidates(sug)]}
    new = list(dict.fromkeys(known.get(finder.same_video(u.strip()), u.strip())     # spelled like the copy already here
                             for u in urls if u and u.strip().startswith("http")))
    if not new:
        raise PipelineError("Colle au moins un lien (https://…).")
    model = finder.model_of(p.get("reference"))
    checker = checker or (lambda u, sc, pl: finder.check(u, sc, pl, **({"model": model} if model else {})))
    plans = _judged_plans(p)

    def one(u):
        try:
            return u, checker(u, sug["scenes"], plans), None
        except Exception as e:
            return u, None, str(e)[:200]
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(one, new))
    p = load(pid)
    sug = p["suggestions"]
    perso = {c["url"]: c for c in sug.get("perso") or []}
    for u, r, err in results:
        from adaptation.imagesearch import platform
        vid = finder._video_id(u)
        card = perso.get(u) or {"url": u, "id": vid or u, "origines": ["perso"], "platform": platform(u),
                                "thumb": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else ""}
        if r:
            sug.setdefault("verifs", {})[u] = r
            (sug.get("verif_errors") or {}).pop(u, None)
            card.update(title=r.get("title") or card.get("title") or u, duration=r.get("duration") or card.get("duration"))
        else:
            sug.setdefault("verif_errors", {})[u] = err
            card.setdefault("title", u)
        perso[u] = card
    sug["perso"] = list(perso.values())
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
            left = script.problems(sc, p["clips"], t["language"])
            if left:                                   # what the re-read missed is fixed once more, then shown
                report(f"correction {label}", (i + 0.85) / n)
                try:
                    fixed = script.revise(sc, clips, "Corrige ces problemes : " + " ".join(left))
                    if len(script.problems(fixed, p["clips"], t["language"])) < len(left):
                        sc = {**fixed, "corrections": sc.get("corrections", []) + ["Correction automatique : " + " ".join(left)]}
                except script.ScriptError:
                    pass
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
             problems=_fetched_problems(sc, p["clips"], t["language"]), approved=False)
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
    problems = _fetched_problems(t["script"] or {}, p["clips"], t["language"])
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
    anns = _annotations(p, t, os.path.join(base, "work"), report, offset + share * 0.2)
    report(f"{'aperçu' if preview else 'rendu'} {t['channel']}", offset + share * 0.3)
    r = render.render(t["voice"]["passages"], t["voice"]["words"], p["clips"], voice_mp3, t["language"], out,
                      os.path.join(base, "work"), credit=p["credits"],
                      music=(t["music_path"], t["music_start"]) if t.get("music_path") else None, preview=preview,
                      progress_cb=lambda f: report(f"{'aperçu' if preview else 'rendu'} {t['channel']}",
                                                   offset + share * (0.3 + 0.6 * f)), annotations=anns)
    c = checks.verify(out, voice_mp3, t["voice"]["passages"])
    return {"path": out, "summary": r, "checks": c}


def _annotations(p: Dict, t: Dict, work: str, report: Report, at: float) -> List[Dict]:
    """The arrows/circles the script asks for, located once (the final render
    reuses the preview's track); a target not found is simply left out."""
    passages = (t.get("script") or {}).get("passages") or []
    wanted = [(k, x["annotation"]) for k, x in enumerate(passages) if (x.get("annotation") or {}).get("cible")]
    if not wanted:
        return []
    report(f"flèches et cercles {t['channel']}", at)
    segs, _ = render.build_timeline(t["voice"]["passages"], p["clips"])
    cache, out = t.setdefault("ann_cache", {}), []
    os.makedirs(work, exist_ok=True)
    for k, ann in wanted:
        if k >= len(segs):
            continue
        try:
            r = annotate.prepare(segs[k], p["clips"][segs[k]["clip"]], ann, work, k, cached=cache.get(str(k)))
        except Exception:
            r = None
        if r:
            cache[str(k)] = r.pop("cache")
            out.append(r)
    return out


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


RUNNERS = {"analysing": run_analysis, "searching": run_images, "fetching": run_fetch, "scripting": run_scripts,
           "voicing": run_voices, "rendering": run_final}


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
