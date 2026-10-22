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
from adaptation import annotate, checks, effects, finder, langs, reference, render, script, settings, sources, storyboard, voices

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


def _new_pid() -> str:
    return "ad_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]   # two in one second


def create(reference_url: str, source_urls: List[str], channels: List[Dict], mode: str = "sources",
           versions: bool = False) -> Dict:
    """channels: [{"channel": name, "profile": profile.json dict, "music_dir": path}]
    mode: "sources" (find the footage, then write) or "script" (write, then find the footage).
    versions (script mode, several channels): one project per channel, a group — the reference
    is read once, each channel gets its own angle, so its video differs from the others."""
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
                        "music_start": s["music_start"], "style": s["style"], "script": None, "approved": False,
                        "validated": False, "video_id": None})
    base = {"status": "analysing", "reference_url": reference_url.strip(), "mode": mode,
            "source_urls": urls, "reference": None, "suggestions": None, "sources": [], "clips": {},
            "credits": "", "credits_auto": "", "error": None, "failed_step": None}
    if mode == "sources" and versions and len(targets) > 1:
        base["versions"] = True         # one project, the same clips, an angle per channel at the script step
    if mode == "script" and versions and len(targets) > 1:
        leader = _new_pid()
        for k, t in enumerate(targets):     # the leader's run reads the reference and writes every member
            pid = leader if k == 0 else _new_pid()
            save({**base, "project_id": pid, "targets": [t], "group": leader, "await_leader": k > 0})
        return load(leader)
    return save({**base, "project_id": _new_pid(), "targets": targets})


def group_of(p: Dict) -> List[Dict]:
    """The other projects of p's group (other channels' versions of the same reference)."""
    g = p.get("group")
    return [x for x in db.list_adaptations() if g and x.get("group") == g and x["project_id"] != p["project_id"]]


def new_version(pid: str, channel: Dict) -> Dict:
    """One more channel's version of an analysed project: the reference is
    not read again, a new angle (never used in the group) is written."""
    src = load(pid)
    if not src.get("reference"):
        raise PipelineError("Le Short modèle de ce projet n'est pas encore analysé.")
    if any(t["channel"] == channel["channel"] for x in [src] + group_of(src) for t in x["targets"]):
        raise PipelineError(f"La chaîne {channel['channel']} a déjà sa version de ce Short.")
    fresh = create(src["reference_url"], [], [channel], mode="script")
    if not src.get("group"):
        src["group"] = src["project_id"]
        save(src)
    fresh.update(group=src["group"], reference=src["reference"])
    return save(fresh)


def change_angle(pid: str, index: Optional[int] = None, custom: Optional[str] = None) -> Dict:
    """Another angle for this version: the storyboard is written again (background)."""
    p = load(pid)
    _expect(p, "plan_review")
    if custom and custom.strip():
        p["angle"] = {"titre": custom.strip()[:80], "idee": custom.strip()[:400]}
    elif index is not None and 0 <= index < len(p.get("angles") or []):
        p["angle"] = p["angles"][index]
    else:
        raise PipelineError("Choisis un angle.")
    p["status"] = "analysing"
    return save(p)


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
    marks = {id(c): [h.rstrip(".") for m in c.get("marks") or [] for h in re.findall(r"@[\w.]{3,}", m)] for c in used}
    logos = {id(c): [hit.group(1) for m in c.get("marks") or []
                     # a name, written as one: "logo ampoule" (SpotLight's light bulb) once took @spotlight's place
                     if (hit := re.search(r"(?i:logo)\s+(?:(?i:de)\s+)?([A-Z0-9][\w]+)", m))
                     and hit.group(1).lower() not in {"tiktok", "instagram", "youtube", "facebook", "de", "la", "du"}]
             for c in used}
    for c in used:
        for name in marks[id(c)]:
            add(name)
    for c in used:
        for name in logos[id(c)]:
            add(name)
    for c in used:                      # a clip with no name on it: its source's account (one clip's watermark
        if not marks[id(c)] and not logos[id(c)]:    # once took the place of every source's account)
            i = c.get("source")
            add((metas[i] if isinstance(i, int) and i < len(metas) else {}).get("handle"))
    return " · ".join(out[:6])


def credits_for_scripts(p: Dict) -> str:
    """The credits of the clips the scripts really use (every version)."""
    used = {x["clip"] for t in p["targets"] for x in (t.get("script") or {}).get("passages") or []}
    return guess_credits(p.get("sources") or [], {k: c for k, c in p["clips"].items() if k in used})


ANALYSE_WORKERS = 2      # whole source videos analysed at once (cut detection is CPU-heavy)


class _SafeIds:
    """A clip-name generator several threads can draw from."""

    def __init__(self, gen):
        import threading
        self._gen, self._lock = gen, threading.Lock()

    def __iter__(self):
        return self

    def __next__(self):
        with self._lock:
            return next(self._gen)


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
            members = _angles(p, report)
            write_storyboard(load(pid), report)
            for th in members:          # the other channels' storyboards, written at the same time
                th.join()
            report("terminé", 1.0)
            return
        if not p.get("suggestions"):
            alone = not p["source_urls"]            # nothing given: the search is the step, give it more room
            share = 0.6 if alone else 0.1
            p["suggestions"] = finder.suggest(p["reference"], p["reference_url"],
                                              work_dir=os.path.join(project_dir(pid), "finder"),
                                              report=lambda ph, f: report(ph, 0.1 + share * f))
            save(p)
            if alone:                   # two per scene: each one's best by words AND by picture (measured: 8 for
                n = min(14, max(8, 2 * len(p["suggestions"].get("scenes") or [])))   # 6 scenes left scene 5's
                finder.verify_best(p["suggestions"], p["reference"], n=n,          # eight obvious videos unchecked)
                                   report=lambda ph, f: report(ph, 0.7 + 0.28 * f))
                save(p)
        if not p["source_urls"] and not p.get("pending_excerpts"):
            p.update(status="sources_search", error=None, failed_step=None)
            save(p)
            report("terminé", 1.0)
            return
        base = project_dir(pid)
        clips, metas = dict(p.get("clips") or {}), list(p.get("sources") or [])
        ids = _SafeIds(i for i in sources._ids() if i not in clips)    # clip names drawn by several sources at once
        metas += [None] * (len(p["source_urls"]) - len(metas))
        todo = [i for i, m in enumerate(metas) if m is None or m.get("failed")]    # new ones, and the failed ones again

        def one(k: int, i: int) -> None:      # one source: download, turn upright, cut, describe, clean
            url, n = p["source_urls"][i], len(todo)
            report(f"source {k + 1}/{n} : téléchargement", 0.2 + 0.75 * k / n)
            try:
                path = sources.download(url, os.path.join(base, "src"), f"src{i}",
                                        (p.get("source_sections") or {}).get(url))
            except sources.SourceError as e:        # one dead link must not block the others
                metas[i] = {"url": url, "failed": str(e)}
                return
            meta = sources.source_meta(path)
            try:                        # a video posted lying on its side is turned upright first (as in Script d'abord)
                with sources.gemini_file(path) as gf:
                    deg = sources.orientation(gf)
                if deg:
                    report(f"source {k + 1}/{n} : remise à l'endroit", 0.2 + 0.75 * (k + 0.2) / n)
                    path = sources.rotated(path, deg)
            except Exception:
                pass
            report(f"source {k + 1}/{n} : découpage et analyse", 0.2 + 0.75 * (k + 0.3) / n)
            made = sources.analyse_source(path, i, os.path.join(base, "work"), ids)
            try:                        # added text the first cleaning missed is painted over too
                sources.leftover_text({c["id"]: c for c in made if c["usable"]}, os.path.join(base, "work"))
            except Exception:
                pass
            for c in made:
                clips[c["id"]] = c
            metas[i] = meta
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=ANALYSE_WORKERS) as pool:   # whole videos are analysed: two at once
            for f in [pool.submit(one, k, i) for k, i in enumerate(todo)]:
                f.result()
        p = load(pid)
        guess = guess_credits(metas, clips)
        if not p.get("credits") or p.get("credits") == p.get("credits_auto"):     # never overwrite a correction
            p["credits"] = guess
        p.update(clips=clips, sources=metas, credits_auto=guess, status="sources_review", error=None,
                 failed_step=None)
        for scene in p.pop("pending_excerpts", None) or []:     # the excerpts planned while choosing the videos
            report("extrait du Short modèle", 0.97)
            try:
                _make_excerpt(p, scene)
            except PipelineError:
                pass
        if not any(c["usable"] for c in clips.values()):
            failed = [m["failed"] for m in metas if m.get("failed")]
            p.update(status="error", failed_step="analysing",
                     error=" ".join(failed) if failed and not clips else "Aucun clip utilisable dans ces sources.")
        save(p)
    except Exception as e:
        fail(pid, "analysing", e)
    report("terminé", 1.0)


# ---------------------------------------------------------------- "Script d'abord": the storyboard

FIX_HOW = (" Pour une phrase coupee entre deux plans (\"… patiner sur place…\" / \"…et leur evite…\"), ecris DEUX "
           "phrases completes, une par plan, sans aucun \"…\" : par exemple \"…patiner sur place.\" puis \"Elle leur evite "
           "aussi…\". Ne change que les plans en cause.")


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


def _angles(p: Dict, report: Report) -> List:
    """Angles proposed once per project, never one already used in its group;
    the leader of a new group also gives each waiting member its angle and
    writes its storyboard (the reference is read once for all)."""
    if p.get("angles"):
        return []
    group = group_of(p)
    waiting = [x for x in group if x.get("await_leader")] if p.get("group") == p["project_id"] else []
    used = [x["angle"]["titre"] for x in group if x.get("angle")]
    report("angles de la vidéo", 0.25)
    found = storyboard.angles(p["reference"], max(3, 1 + len(waiting)), avoid=used)
    p.update(angles=found, angle=found[0])
    save(p)
    import threading
    threads = []

    def write_member(m):
        try:
            write_storyboard(m, lambda ph, f: None)
        except Exception as e:
            fail(m["project_id"], "analysing", e)
    for k, m in enumerate(waiting, 1):
        m.update(reference=p["reference"], angles=found, angle=found[k % len(found)], await_leader=False)
        save(m)
        th = threading.Thread(target=write_member, args=(m,), daemon=True)
        th.start()
        threads.append(th)
    return threads


def write_storyboard(p: Dict, report: Report):
    codes = _codes(p)
    report("écriture du storyboard" + (f" : « {p['angle']['titre']} »" if p.get("angle") else ""), 0.35)
    b = storyboard.write(p["reference"], codes, angle=p.get("angle"))
    report("relecture (rétention, langue, images)", 0.65)
    b = storyboard.critique(b, codes)
    for attempt in (1, 2):              # what the re-read missed is fixed (twice at most), then shown
        hard = [f"[{c}] {x}" for c in codes for x in storyboard.problems(b, c)]
        report("chaque phrase comparée à son image", 0.8)
        seen = storyboard.illustration(b, codes[0]) + storyboard.unfilmable(b)   # images are shared: one language
        left = hard + seen
        if not left:
            break
        report("correction", 0.85)
        try:
            fixed = storyboard.revise(b, codes, "Corrige ces problemes : " + " ".join(left) + FIX_HOW)
        except script.ScriptError:
            break
        now = sum(len(storyboard.problems(fixed, c)) for c in codes)
        if now > len(hard) or (not seen and now >= len(hard)):     # a fix that breaks more than it mends: kept out
            break
        b = {**fixed, "corrections": b.get("corrections", []) + ["Correction automatique : " + " ".join(left)]}
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


class SharedSearch:
    """What every version of a group searches the same way, done once: the
    reference Short's pictures, their Yandex results, the YouTube searches
    with the same words. Kept on the group's leader; the Gemini checks stay
    per version (they judge a video against that version's own plans)."""

    def __init__(self, p: Dict, wanted: List[Dict]):
        self.p, self.wanted, self.reused = p, wanted, []
        self.leader = p.get("group") or p["project_id"]
        try:
            self.cache = dict((load(self.leader).get("search_cache") or {}))
        except PipelineError:
            self.cache = {}
        self.cache.setdefault("queries", {})
        self.cache.setdefault("hits", {})

    def search(self, q: str) -> List[Dict]:
        if q in self.cache["queries"]:
            if "recherches YouTube" not in self.reused:
                self.reused.append("recherches YouTube")
            return [dict(c) for c in self.cache["queries"][q]]
        out = finder.search_youtube(q)
        self.cache["queries"][q] = out
        return out

    def frames(self, ref: Dict, url: str, work_dir: str, scenes: List[Dict], report=None) -> Dict:
        from adaptation import frames as frames_mod
        got = self.cache.get("frames")
        if got and got.get("frames") and all(os.path.exists(os.path.join(got["dir"], f["file"])) for f in got["frames"]):
            os.makedirs(work_dir, exist_ok=True)
            if os.path.abspath(got["dir"]) != os.path.abspath(work_dir):
                for f in got["frames"]:
                    shutil.copy(os.path.join(got["dir"], f["file"]), os.path.join(work_dir, f["file"]))
            self.reused.append("images du Short")
            return {**got, "frames": [{**f, "scene": frames_mod._scene_of(f.get("plan"), scenes)} for f in got["frames"]]}
        out = frames_mod.reference_frames(ref, url, work_dir, scenes, report=report)
        if out.get("frames"):
            self.cache["frames"] = {**out, "dir": work_dir}
        return out

    def image_search(self, files: List[str]) -> Dict:
        from adaptation import imagesearch
        names = [os.path.basename(f) for f in files]
        if names and all(n in self.cache["hits"] for n in names):
            self.reused.append("recherche par image")
            return {"hits": {f: self.cache["hits"][n] for f, n in zip(files, names)}, "error": None, "seconds": 0}
        out = imagesearch.timed_search(files)
        if not out.get("error"):
            self.cache["hits"].update({os.path.basename(f): h for f, h in out["hits"].items()})
        return out

    def save(self):
        try:
            leader = load(self.leader)
        except PipelineError:
            return
        mine = leader.get("search_cache") or {}
        mine.setdefault("queries", {}).update(self.cache["queries"])
        mine.setdefault("hits", {}).update(self.cache["hits"])
        if self.cache.get("frames") and not mine.get("frames"):
            mine["frames"] = self.cache["frames"]
        leader["search_cache"] = mine
        save(leader)


def wanting(p: Dict) -> List[int]:
    """The plans still without good footage: no pick, or only a partial one
    (Sources d'abord: the scenes no checked video shows well)."""
    if p.get("mode") != "script":
        sug = p.get("suggestions") or {}
        good = {int(i) for v in (sug.get("verifs") or {}).values()
                for i, e in (v.get("par_scene") or {}).items() if e.get("niveau") in ("exacte", "equivalente")}
        return [i for i in range(len(sug.get("scenes") or [])) if i not in good]
    picks = p.get("picks") or []
    return [k for k in _active(p) if k >= len(picks) or not picks[k] or picks[k].get("niveau") == "partielle"]


def start_more_images(pid: str) -> Dict:
    p = load(pid)
    _expect(p, "images_review", "sources_search")
    todo = wanting(p)
    if not todo:
        raise PipelineError("Chaque plan a déjà une vidéo exacte ou équivalente.")
    p.update(status="searching", search_more=todo, search_more_back=p["status"])
    return save(p)


def _more_images(p: Dict, report: Report):
    """The plans left without footage, searched again by ACTION (compilations,
    GoPro, vlogs: videos about something else where it happens), the new
    videos checked by Gemini against every plan, and a pick given only where
    there was none — the other plans' choices stay."""
    from concurrent.futures import ThreadPoolExecutor
    pid, todo = p["project_id"], p["search_more"]
    sug = p["suggestions"]
    script_first = p.get("mode") == "script"
    plans = p["storyboard"]["plans"] if script_first else []
    wanted = finder.wanted_from_storyboard(plans, {}) if script_first else sug["scenes"]
    report(f"recherches par action pour {len(todo)} {'plan' if script_first else 'scène'}(s)", 0.03)
    qs = finder.action_queries([wanted[k] for k in todo])
    jobs = [(k, q) for n, k in enumerate(todo) for q in qs.get(n, [])]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda kq: (kq[0], kq[1], finder.search_youtube(kq[1])), jobs))
    known = {c["url"] for c in finder.all_candidates(sug)}
    fresh: Dict[int, List[Dict]] = {}
    for k, q, hits in results:
        sc = sug["scenes"][k]
        sc.setdefault("actions", [])
        if q not in sc["actions"]:
            sc["actions"].append(q)
        by_url = {c["url"]: c for c in sc.setdefault("candidats", [])}
        for h in hits:
            if h["url"] not in known:
                fresh.setdefault(k, []).append(h["url"])
            finder._add(sc["candidats"], h, "action", by_url)
    # four per plan, the most likely first: the new videos AND the ones found before but never looked at
    # (measured: the exact source of a plan sat unchecked while four off-topic "how to bleed a tuna" were checked)
    done_urls = set(sug.get("verifs") or {}) | set(sug.get("verif_errors") or {})
    pools = [{"scene": wanted[k]["scene"], "candidats": [c for c in sug["scenes"][k].get("candidats") or []
                                                        if c["url"] not in done_urls
                                                        and (c.get("duration") or 0) <= finder.MAX_DURATION]}
             for k in todo]
    finder.sort_out(pools)              # Gemini keeps the plausible titles, most likely first
    # what the AI found useful for another channel's version of the same Short comes first (measured: the
    # French version had the original "unclog by hand" video, exact; the Arabic one, same scenes, never saw it)
    shared = []
    for other in group_of(p):
        for url, v in ((other.get("suggestions") or {}).get("verifs") or {}).items():
            if url not in done_urls and not (v.get("film") or v.get("copie") or v.get("telechargeable") is False) \
                    and any((e or {}).get("niveau") in finder.RANK for e in (v.get("par_scene") or {}).values()):
                shared.append(url)
    order = shared[:6]
    for pool in pools:
        order += [c["url"] for c in pool["candidats"]][:4]
    order = list(dict.fromkeys(order))
    model = finder.model_of(p.get("reference"))
    verifs, errors = sug.setdefault("verifs", {}), sug.setdefault("verif_errors", {})

    ref_plans = None if script_first else (p.get("reference") or {}).get("plans")

    def look(url):
        try:
            return url, finder.check(url, sug["scenes"], ref_plans, **({"model": model} if model else {})), None
        except Exception as e:
            return url, None, str(e)[:200]
    done = 0
    with ThreadPoolExecutor(max_workers=3) as pool:
        for url, r, err in pool.map(look, order):
            done += 1
            report(f"vérification par l'IA : {done}/{len(order)}", 0.1 + 0.85 * done / max(1, len(order)))
            if r:
                verifs[url] = r
            else:
                errors[url] = err
    if not script_first:                # the person ticks the videos: the useful ones are shown, nothing is picked
        helped = sorted({int(i) + 1 for u in order if u in verifs
                         for i, e in (verifs[u].get("par_scene") or {}).items()
                         if e.get("niveau") in ("exacte", "equivalente") and int(i) in todo})
        p["fetch_note"] = (f"Recherche par action : {len(order)} nouvelle(s) vidéo(s) regardée(s) par l'IA ; "
                           + (f"utile(s) pour la/les scène(s) {', '.join(map(str, helped))} : coche-les."
                              if helped else "rien de mieux pour ces scènes : donne ton lien ou un extrait du Short."))
        return
    picks = p.get("picks") or [None] * len(plans)
    taken = {(x["url"], round(x["moment"]["debut"])) for x in picks if x}
    best = finder.auto_pick(sug, plans)
    found = []
    for k in todo:
        b = best[k] if k < len(best) else None
        better = b and (not picks[k] or finder.RANK[b["niveau"]] < finder.RANK.get(picks[k]["niveau"], 9))
        if better and (b["url"], round(b["moment"]["debut"])) not in taken:
            if picks[k]:                # its old moment is free for the next plans (measured: a plan left empty
                taken.discard((picks[k]["url"], round(picks[k]["moment"]["debut"])))    # by a moment just let go)
            picks[k] = b
            taken.add((b["url"], round(b["moment"]["debut"])))
            found.append(k + 1)
    p["picks"] = picks
    p["fetch_note"] = (f"Recherche par action : {len(order)} nouvelle(s) vidéo(s) regardée(s) par l'IA ; "
                       + (f"vidéo trouvée pour le(s) plan(s) {', '.join(map(str, found))}." if found
                          else "rien de mieux pour ces plans : donne ton lien, adapte la phrase ou retire le plan."))


def run_images(pid: str, report: Optional[Report] = None):
    """Every plan's footage: search words from its image, the four searches,
    Gemini's checks (twice as many as plans: each plan's best by words, then
    by picture), then the best checked moment picked for each plan."""
    report = report or (lambda phase, f: None)
    p = load(pid)
    if p.get("search_more") is not None:      # "Chercher plus": only the plans still without footage
        back = p.get("search_more_back") or "images_review"
        try:
            _more_images(p, report)
            p.pop("search_more", None)
            p.pop("search_more_back", None)
            p.update(status=back, error=None, failed_step=None)
            save(p)
        except Exception as e:              # the picks already made are worth more than this extra search
            p = load(pid)
            p.pop("search_more", None)
            p.pop("search_more_back", None)
            p.update(status=back, fetch_note=f"Recherche par action impossible : {str(e)[:200]}")
            save(p)
        report("terminé", 1.0)
        return
    try:
        plans = p["storyboard"]["plans"]
        report("recherches pour chaque plan", 0.02)
        queries = finder.plan_queries(finder.wanted_from_storyboard(plans, {}))
        local = lambda found: {i: {"pays": q["pays"], "langue": q["langue"], "recherches": q["locales"]}
                               for i, q in queries.items() if q.get("locales")}
        wanted = finder.wanted_from_storyboard(plans, queries)
        shared = SharedSearch(p, wanted)
        sug = finder.suggest(p["reference"], p["reference_url"], work_dir=os.path.join(project_dir(pid), "finder"),
                             wanted=wanted, local=local, search=shared.search, frames_fn=shared.frames,
                             image_search=shared.image_search, report=lambda ph, f: report(ph, 0.05 + 0.55 * f))
        shared.save()
        if shared.reused:
            report("réutilisé des autres versions : " + ", ".join(shared.reused), 0.6)
        finder.verify_best(sug, {"plans": [], **{k: p["reference"].get(k) for k in ("script_complet", "duree_s")}},
                           n=min(14, 2 * len(plans)), words_share=1.0,
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
                       "film": bool(v.get("film")),
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
    dead = set(sug.get("unavailable") or [])
    for url, v in (sug.get("verifs") or {}).items():
        if v.get("copie") or v.get("film") or v.get("remontage") or v.get("telechargeable") is False or url in dead:
            continue                    # what auto_pick never takes either (measured: a BBC film was proposed)
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
    p.pop("fetch_note", None)
    return save(p)


FETCH_WORKERS = 3        # source videos handled at once (memory: one segment-sized ffmpeg each)
CUT_VERSION = 4          # how clips are cut; a clip cut an older way is cut again (4: leftover text painted over)
ACTION_LEAD, ACTION_TAIL, MIN_ACTION = 0.6, 0.8, 1.2    # seconds kept before / after the action; shortest clip


def fit_window(a: float, b: float, need: float, shots: List[Tuple[float, float]],
               length: Optional[float] = None) -> Tuple[float, float]:
    """The clip for a sentence of `need` seconds from the moment [a, b] the AI
    checked: when it is too short, lengthened forward then backward but only
    inside the shots the moment is in — never into the next shot (measured:
    blindly lengthened, a clip took an interview after the bump, another the
    black end screen of its video). Still short: kept short, the script check
    then asks for a shorter sentence instead of showing the wrong picture."""
    if need <= 0 or b - a >= need:
        return round(a, 2), round(b, 2)
    lo, hi = 0.0, length if length else b + need
    for s, e in shots:              # detect_cuts trims its shots by 0.08 s: a moment edge on a cut still matches
        if s - 0.15 <= a <= e + 0.15:
            lo = max(lo, s)
        if s - 0.15 <= b - 0.05 <= e + 0.15:
            hi = min(hi, e)
    if not shots:
        lo, hi = max(0.0, a - need), (min(length, b + need) if length else b + need)
    lo, hi = min(lo, a), max(hi, b)
    end = min(hi, a + need)
    start = max(lo, end - need)
    return round(start, 2), round(end, 2)


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
            return [picks[k]["url"], round(m["debut"], 2), round(m["fin"], 2), 0 if picks[k].get("extrait") else plans[k]["duree"],
                    CUT_VERSION]
        old = p.get("clips") or {}
        clips = {f"P{k + 1}": old[f"P{k + 1}"] for k in _active(p)
                 if (old.get(f"P{k + 1}") or {}).get("pick_key") == pick_key(k) and os.path.exists(old[f"P{k + 1}"]["src"])}
        by_url: Dict[str, List[Tuple[int, float, float]]] = {}
        for k in _active(p):
            if f"P{k + 1}" in clips:
                continue
            m = picks[k]["moment"]
            need = 0.0 if picks[k].get("extrait") else plans[k]["duree"]       # an excerpt stays as it is
            by_url.setdefault(picks[k]["url"], []).append((k, m["debut"], max(m["fin"], m["debut"] + 0.5), need))
        if clips:
            report(f"{len(clips)} plan(s) inchangé(s) : clips gardés", 0.03)
        failed: Dict[str, Tuple[str, List[int]]] = {}
        base, stamp = project_dir(pid), datetime.now().strftime("%H%M%S") + "_" + uuid.uuid4().hex[:4]   # two in one second
        def one(i: int, url: str, items: List) -> None:      # one source video: download, clean, check, cut
            report(f"vidéo {i + 1}/{len(by_url)} : téléchargement des moments choisis", 0.05 + 0.8 * i / len(by_url))
            dur = durations.get(url)
            room = lambda need: min(need, 6.0)                 # around the moment: room to lengthen it, both ways
            spans = None if (dur and dur <= 120) else _spans([(k, max(0.0, a - room(n)), b + room(n)) for k, a, b, n in items])
            name = f"src{stamp}_{i}"           # never over a file a kept clip still uses
            try:
                try:
                    path = sources.download(url, os.path.join(base, "src"), name, spans)
                except sources.SourceError:
                    if spans is None:
                        raise
                    spans = None                # some sites refuse a section: the whole video, then
                    path = sources.download(url, os.path.join(base, "src"), name)
            except sources.SourceError as e:
                failed[url] = (str(e), [k for k, _, _, _ in items])
                return
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
            try:                        # the shots of the file: a clip is lengthened inside them, never across one
                shots = sources.detect_cuts(path, sources.probe(path), None, min_len=0.1)
                length = sources.probe(path)["duration"]
            except Exception:
                shots, length = [], None
            if spans:                   # the spans are joined in one file: a join is a cut too, seen or not
                joins, at = [], 0.0
                for a, b in spans[:-1]:
                    at += b - a
                    joins.append(at)
                bounds = [0.0] + joins + [length or at + spans[-1][1] - spans[-1][0]]
                shots = [(max(s, x), min(e, y)) for s, e in (shots or [(0.0, bounds[-1])])
                         for x, y in zip(bounds, bounds[1:]) if min(e, y) > max(s, x)]
            upload = None
            try:                        # one upload for the two looks below
                upload = sources.gemini_file(path)
                gfile = upload.__enter__()
            except Exception:
                upload, gfile = None, None
            moments = [(k, file_time(a), file_time(a) + (b - a), need) for k, a, b, need in items]
            absent, seen_moving, action_at = {}, {}, {}
            asks = [(n, m) for n, m in enumerate(moments) if m[3] > 0]        # an excerpt stays where it was cut
            if gfile and asks:
                report(f"vidéo {i + 1}/{len(by_url)} : l'IA recale chaque moment", 0.05 + 0.8 * (i + 0.5) / len(by_url))
                code = p["targets"][0]["language"]
                found_at = sources.retime(path, [{"image": plans[m[0]]["image"], "a": m[1], "b": m[2],
                                                  "phrase": (plans[m[0]].get("textes") or {}).get(code, {}).get("texte")}
                                                 for _, m in asks], length or moments[-1][2] + 10, gfile)
                for (n, (k, fa, fb, need)), r in zip(asks, found_at):
                    if r and r["visible"]:
                        moments[n] = (k, r["debut"], r["fin"], need)
                        seen_moving[k] = r["vu"]
                        action_at[k] = (r["debut"], r["fin"], r.get("fort"))
                    elif r:
                        absent[k] = r["vu"] or "autre chose"
            if gfile:                   # a video posted lying on its side is turned upright before anything is cut
                deg = sources.orientation(gfile)
                if deg:
                    report(f"vidéo {i + 1}/{len(by_url)} : remise à l'endroit", 0.05 + 0.8 * (i + 0.55) / len(by_url))
                    try:
                        path = sources.rotated(path, deg)
                    except Exception:
                        pass
            times, compact = [], set()
            for k, fa, fb, need in moments:
                start, end = fit_window(fa, fb, need, shots, length)
                if k in action_at:          # no dead time: around the action only; the render slows it to fill
                    ra, rb = action_at[k][:2]
                    s2, e2 = max(start, ra - ACTION_LEAD), min(end, rb + ACTION_TAIL)
                    if e2 - s2 >= MIN_ACTION and e2 - s2 < end - start - 0.3:
                        start, end = round(s2, 2), round(e2, 2)
                        compact.add(k)
                times.append((k, start, end))
            work = os.path.join(base, "work")
            os.makedirs(work, exist_ok=True)
            stills = [sources.still(path, (a + b) / 2, None, os.path.join(work, f"p{k}.jpg")) for k, a, b in times]
            ok = [st for st in stills if os.path.exists(st)]          # a missing still: no cleaning, never a crash
            boxes = iter(sources.find_boxes(ok)) if ok else iter([])
            found = [next(boxes, (None, [], [])) if os.path.exists(st) else (None, [], []) for st in stills]
            report(f"vidéo {i + 1}/{len(by_url)} : contrôle des moments par l'IA", 0.05 + 0.8 * (i + 0.8) / len(by_url))
            try:                        # the same check as an analysed source: a presenter, a title, a logo… is refused
                segs = [(a, b) for _, a, b in times]
                seen = sources.describe(path, segs, file=gfile) if gfile else sources.describe(path, segs)
            except Exception:
                seen = [{} for _ in times]
            finally:
                if upload:
                    upload.__exit__(None, None, None)
            for (k, a, b), f, d in zip(times, found, seen):
                c = sources.clip_at(path, i, f"P{k + 1}", a, b, f, desc=plans[k]["image"])
                why = _real_faults(d.get("pourquoi_pas") or "")
                c.update(desc=d.get("visuel") or c["desc"], usable=bool(d.get("utilisable", True)) or not why,
                         why_not=why, shock=bool(d.get("choc_sonore")), pick_key=pick_key(k), meta=meta,
                         note=finder.warnings_of(d.get("pourquoi_pas") or ""))
                if k in absent:                 # the wanted action is nowhere in what was downloaded
                    c["absent"] = absent[k]
                if seen_moving.get(k):          # what the re-timing saw, in motion: the judge trusts it over stills
                    c["action"] = seen_moving[k]
                if k in action_at:              # the strong moment is IN the action (arrow, ramp, freeze follow it)
                    ra, rb = max(action_at[k][0], c["start"]), min(action_at[k][1], c["end"])
                    fort = action_at[k][2]
                    if fort is not None and c["start"] <= fort <= c["end"]:
                        c["impact"] = round(fort, 2)        # the most spectacular instant, as Gemini saw it moving
                    elif rb > ra and not ra <= c["impact"] <= rb:
                        c["impact"] = round(ra + 0.6 * (rb - ra), 2)
                    c["action_at"] = [round(action_at[k][0], 2), round(action_at[k][1], 2)]
                if k in compact:                # cut around its action: slowed down to fill its sentence
                    c["compact"] = True
                if picks[k].get("extrait"):     # the reference's own captions are cleaned: not a reason to refuse
                    c.update(extrait=True, usable=True, why_not="")
                clips[f"P{k + 1}"] = c
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:     # several sources at once (9 min -> about 4)
            for f in [pool.submit(one, i, url, items) for i, (url, items) in enumerate(by_url.items())]:
                f.result()
        if failed:                      # a video that won't download: replaced where possible, back to the picks
            p = load(pid)
            sug = p["suggestions"]
            sug["unavailable"] = list(dict.fromkeys((sug.get("unavailable") or []) + list(failed)))
            plans_hit = sorted(k for _, ks in failed.values() for k in ks)
            fresh = finder.auto_pick(sug, p["storyboard"]["plans"])
            for k in plans_hit:
                p["picks"][k] = fresh[k]
            p["clips"] = {**(p.get("clips") or {}), **clips}       # the clips made are kept for the next try
            names = ", ".join(str(k + 1) for k in plans_hit)
            replaced = [str(k + 1) for k in plans_hit if p["picks"][k]]
            p["fetch_note"] = (f"Vidéo impossible à télécharger d'ici (supprimée, privée ou bloquée dans ton pays) pour "
                               f"le(s) plan(s) {names}. " + (f"Une autre vidéo vérifiée a été choisie pour le(s) plan(s) "
                               f"{', '.join(replaced)} : vérifie-la. " if replaced else "") +
                               ("Les autres plans n'ont plus de vidéo : choisis-en une, adapte la phrase ou retire le plan."
                                if len(replaced) < len(plans_hit) else "Puis relance « Télécharger les images choisies ».")).strip()
            p.update(status="images_review", error=None, failed_step=None)
            save(p)
            report("terminé", 1.0)
            return
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
        guess = " · ".join(list(dict.fromkeys(n for n in names if n and not re.fullmatch(r"@?[-\d_.]*", n)))[:6])
        # 6, not 4: measured, the 4 first names left out the aquarium that filmed 4 clips of 10
        p["credits"], p["credits_auto"] = guess, guess        # every channel whose footage is used, not only watermarks
        report("texte encore visible après nettoyage ?", 0.91)
        try:                            # added text the first cleaning missed is painted over too
            sources.leftover_text(clips, os.path.join(project_dir(pid), "work"))
        except Exception:
            pass
        report("flèches et cercles revus avec les vrais clips", 0.92)
        active = _active(p)
        code = p["targets"][0]["language"]
        rough = [{**storyboard.script_for(p["storyboard"], code)["passages"][k], "clip": f"P{k + 1}"} for k in active]
        seen = annotate.review(rough, clips, os.path.join(project_dir(pid), "work"))
        if seen is not None:            # shared by every language, like the images
            for k, a in zip(active, seen):
                p["storyboard"]["plans"][k]["annotation"] = a
            p["annotations_reviewed"] = True
        report("effets de montage choisis avec les vrais clips", 0.94)
        rough = [{**x, "annotation": p["storyboard"]["plans"][k].get("annotation")} for k, x in zip(active, rough)]
        fx = effects.decide(rough, clips, os.path.join(project_dir(pid), "work"))
        fx = effects.auto_zoom(rough, clips, fx or [], os.path.join(project_dir(pid), "work"))   # a small subject: zoomed
        for k, e in zip(active, fx):        # shared by every language, like the arrows
            p["storyboard"]["plans"][k]["effets"] = e
        for t in p["targets"]:
            full = storyboard.script_for(p["storyboard"], t["language"])
            sc = {**full, "passages": [{**full["passages"][k], "clip": f"P{k + 1}"} for k in _active(p)]}
            sc = _shorten(p, sc, clips, t["language"], report)
            report("chaque phrase comparée à son image", 0.97)
            t["accords"] = _judge(sc, clips, t["language"], os.path.join(project_dir(pid), "work"))
            t.update(script=sc, problems=_fetched_problems(sc, clips, t["language"], t["accords"]))
            t["approved"] = not t["problems"]
        save(p)
    except Exception as e:
        fail(pid, "fetching", e)
    report("terminé", 1.0)


TOO_LONG = re.compile(r"Passage (\d+) : phrase trop longue pour son clip \(\d+ caract[eè]res, le clip \S+ en laisse environ (\d+)\)")


def _shorten(p: Dict, sc: Dict, clips: Dict[str, Dict], code: str, report: Report) -> Dict:
    """A clip kept inside its shot can be shorter than the sentence written for
    the plan: the AI shortens only those sentences (twice at most), the others
    stay word for word; the new sentence is kept in the storyboard too."""
    for _ in range(2):
        long = {int(n) - 1: int(room) for n, room in TOO_LONG.findall(" ".join(script.problems(sc, clips, code)))}
        if not long:
            break
        report("phrases raccourcies pour leur clip", 0.95)
        asks = " ".join(f"Passage {k + 1} : {max(room - 3, 12)} caracteres au plus." for k, room in long.items())
        try:
            new = script.revise(sc, clips, "Raccourcis UNIQUEMENT ces phrases, sans changer leur sens ni les autres "
                                "passages (meme texte, meme clip) ; chaque phrase reste complete. " + asks)
        except Exception:
            break
        if len(new["passages"]) != len(sc["passages"]):
            break
        sc = {**sc, "passages": [{**x, "texte": new["passages"][k]["texte"]} if k in long else x
                                 for k, x in enumerate(sc["passages"])]}
    plans = p["storyboard"]["plans"]
    for k, x in zip(_active(p), sc["passages"]):       # the storyboard says the same: a new fetch keeps it
        textes = plans[k].get("textes") or {}
        if code in textes:
            textes[code]["texte"] = x["texte"]
    return sc


REAL_FAULTS = finder.REAL_FAULTS
_real_faults = finder.real_faults          # what really refuses a chosen moment (shared with the search)


def _judge(sc: Dict, clips: Dict[str, Dict], code: str, work: Optional[str] = None) -> Optional[List[Dict]]:
    """Measured on the speed-bump Short: the French hook said "this bump
    forgives nothing" over a man punching a tub in a lab — nothing checked that
    a clip shows its sentence. Three pictures of each clip go with it. Best
    effort: no verdict never blocks."""
    stills = {}
    if work:
        os.makedirs(work, exist_ok=True)
        for k, x in enumerate(sc.get("passages") or []):
            c = clips.get(x.get("clip"))
            if not c:
                continue
            try:
                stills[k] = [sources.still(c["src"], c["start"] + (c["end"] - c["start"]) * f, c.get("crop"),
                                           os.path.join(work, f"judge_{x['clip']}_{j}.jpg"), c.get("delogo"),
                                           (c["w"], c["h"])) for j, f in enumerate((0.2, 0.5, 0.8))]
            except Exception:
                continue
    try:
        return script.match(sc, clips, code, stills=stills)
    except Exception:
        return None


def _accord(accords: Optional[List[Dict]], k: int, x: Dict) -> Optional[Dict]:
    """The verdict on passage k, if it still judges this sentence on this clip."""
    a = accords[k] if accords and k < len(accords) else None
    return a if a and a["clip"] == x["clip"] and a["texte"] == x["texte"] else None


def _fetched_problems(sc: Dict, clips: Dict[str, Dict], code: str, accords: Optional[List[Dict]] = None) -> List[str]:
    out = script.problems(sc, clips, code)
    for k, x in enumerate(sc.get("passages") or []):
        a = _accord(accords, k, x)
        if a and a["note"] == "non" and not a.get("garde"):
            out.append(f"Passage {k + 1} : la phrase ne correspond pas à l'image ({a['pourquoi'] or 'autre chose à l’écran'}) : "
                       f"prends la phrase proposée, change de clip ou « Garder quand même ».")
    for k, x in enumerate(sc["passages"], 1):
        c = clips.get(x["clip"]) or {}
        why = _real_faults(c.get("why_not") or "") if c and not c.get("usable", True) else ""
        if c and not c.get("usable", True) and (why or not c.get("why_not")):
            out.append(f"Passage {k} : le moment choisi ne convient pas ({why or 'refusé par le contrôle'}) : "
                       f"choisis un autre clip ou « Revenir aux images ».")
        elif c and c.get("absent") and not c.get("forced") and not (_accord(accords, k - 1, x) or {}).get("note") == "bon":
            # the final judge saw the clip's pictures and found the sentence shown: the re-timing was too literal
            out.append(f"Passage {k} : l'action voulue ne se voit pas dans la vidéo téléchargée (on y voit : "
                       f"{c['absent']}) : choisis un autre clip, « Revenir aux images » ou « Utiliser quand même ».")
    return out


def force_clip(pid: str, cid: str) -> Dict:
    """The person has the last word: a clip refused by the check (blur,
    presenter…) is used anyway; it stays marked as forced."""
    p = load(pid)
    _expect(p, "script_review", "sources_review")
    c = (p.get("clips") or {}).get(cid)
    if not c:
        raise PipelineError("Clip inconnu.")
    c.update(usable=True, forced=c.get("why_not") or (f"action introuvable : {c['absent']}" if c.get("absent")
                                                      else "refusé par le contrôle"), why_not="")
    for t in p["targets"]:
        if t.get("script"):
            t["problems"] = _fetched_problems(t["script"], p["clips"], t["language"], t.get("accords"))
            if t["problems"]:
                t["approved"] = False
    return save(p)


def back_to_script(pid: str) -> Dict:
    """From the previews back to the scripts: a clip to change, a sentence to
    fix. The narration is kept and only made again if a sentence changes."""
    p = load(pid)
    if not (p["status"] == "error" and p.get("failed_step") in ("voicing", "rendering")):   # a failed render too
        _expect(p, "preview_review")
    if any(t.get("video_id") for t in p["targets"]):
        raise PipelineError("Une version est déjà rendue : fais une nouvelle version plutôt.")
    p.update(status="script_review", error=None, failed_step=None)
    for t in p["targets"]:
        t["validated"] = False
    return save(p)


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
    return len(p.get("pending_excerpts") or []) + sum(1 for x in p.get("picks") or [] if x and x.get("extrait")) + \
        sum(1 for c in (p.get("clips") or {}).values() if c.get("extrait") and not str(c.get("id", "")).startswith("P"))


def use_excerpt_for_plan(pid: str, plan: int, ref: Optional[int] = None) -> Dict:
    """"Script d'abord", last resort: a plan nobody filmed takes a few seconds
    of the reference itself (never the hook, two per video at most). ref: the
    reference's shot to take (1-based), chosen by the person — any plan can
    have one, not only those the storyboard drew from the reference."""
    p = load(pid)
    _expect(p, "images_review")
    plans = p["storyboard"]["plans"]
    if not 0 <= plan < len(plans):
        raise PipelineError("Plan inconnu.")
    if plan == 0 or plans[plan]["role"] == "accroche":
        raise PipelineError("Pas pour l'accroche : c'est la scène la plus reconnaissable du modèle.")
    if _excerpts_used(p) >= EXCERPTS_PER_VIDEO and not (p["picks"][plan] or {}).get("extrait"):
        raise PipelineError(f"Déjà {EXCERPTS_PER_VIDEO} extraits du Short modèle : c'est le maximum par vidéo.")
    ref_plans = [ref - 1] if ref else [k - 1 for k in plans[plan].get("plans_modele") or [] if k >= 1]
    if not ref_plans:
        raise PipelineError("Choisis le moment du Short modèle à prendre pour ce plan.")
    a, b = excerpt_window(p, ref_plans)
    need = plans[plan]["duree"]
    p = load(pid)
    p["picks"][plan] = {"url": p["reference_url"], "titre": "Extrait du Short modèle", "niveau": "extrait",
                        "moment": {"debut": a, "fin": b}, "auto": False, "extrait": True,
                        "raison": (f"La phrase dure {need} s pour {b - a:.1f} s d'extrait : raccourcis-la."
                                   if need > b - a + 0.2 else "Un court extrait, nettoyé, sous ta voix et ton montage.")}
    return save(p)


def _make_excerpt(p: Dict, scene: int):
    """The excerpt clip of one scene, added to p in memory (clip, source, credits)."""
    scenes = (p.get("suggestions") or {}).get("scenes") or []
    a, b = excerpt_window(p, scenes[scene].get("plans") or [])
    path = _short_file(p)
    if not path:
        raise PipelineError("Le Short modèle n'a pas pu être téléchargé (YouTube refuse) : réessaie plus tard.")
    work = os.path.join(project_dir(p["project_id"]), "work")
    os.makedirs(work, exist_ok=True)
    found = sources.find_boxes([sources.still(path, (a + b) / 2, None, os.path.join(work, f"excerpt{scene}.jpg"))])
    metas = p.get("sources") or []
    idx = next((i for i, m in enumerate(metas) if m and m.get("url") == p["reference_url"]), None)
    if idx is None:                     # the reference becomes one more (already downloaded) source
        metas.append({**sources.source_meta(path), "url": p["reference_url"]})
        p["source_urls"] = p.get("source_urls", []) + [p["reference_url"]]
        idx = len(metas) - 1
    n = sum(1 for c in p["clips"].values() if c.get("extrait")) + 1
    c = sources.clip_at(path, idx, f"M{n}", a, b, found[0], desc=scenes[scene]["scene"] + " (extrait du Short modèle)")
    c.update(extrait=True, usable=True, scene=scene)
    try:                                # the model's own text left after the cleaning, and its arrows (measured:
        sources.leftover_text({c["id"]: c}, os.path.join(project_dir(p["project_id"]), "work"))   # "TRIGGER…LOWERS")
    except Exception:
        sources.erase_drawn_marks({c["id"]: c}, os.path.join(project_dir(p["project_id"]), "work"))
    p["clips"][c["id"]] = c
    p["sources"] = metas
    guess = guess_credits(metas, p["clips"])
    if not p.get("credits") or p.get("credits") == p.get("credits_auto"):
        handle = (metas[idx] or {}).get("handle")
        p["credits"] = " · ".join(x for x in dict.fromkeys([*guess.split(" · "), handle or ""]) if x)[:120]
        p["credits_auto"] = p["credits"]


def add_excerpt_source(pid: str, scene: int) -> Dict:
    """"Sources d'abord", last resort: a scene nobody filmed gets a clip of a
    few seconds from the reference itself, cleaned, credited. While the
    videos are being chosen, it is only planned (made with the downloads, the
    step stays the same); clicked again, the plan is cancelled. At the clip
    review, it is made at once."""
    p = load(pid)
    _expect(p, "sources_search", "sources_review")
    scenes = (p.get("suggestions") or {}).get("scenes") or []
    if not 0 <= scene < len(scenes):
        raise PipelineError("Scène inconnue.")
    pending = p.setdefault("pending_excerpts", [])
    if p["status"] == "sources_search" and scene in pending:
        pending.remove(scene)
        return save(p)
    if any(c.get("extrait") and c.get("scene") == scene for c in p["clips"].values()):
        raise PipelineError("Cette scène a déjà son extrait.")
    if _excerpts_used(p) >= EXCERPTS_PER_VIDEO:
        raise PipelineError(f"Déjà {EXCERPTS_PER_VIDEO} extraits du Short modèle : c'est le maximum par vidéo.")
    if p["status"] == "sources_search":
        plans = (p.get("reference") or {}).get("plans") or []
        if not any(0 <= i < len(plans) and plans[i].get("fin") is not None for i in scenes[scene].get("plans") or []):
            raise PipelineError("Cette scène n'a pas de plan repéré dans le Short modèle.")
        pending.append(scene)           # instant: the Short is looked at when the videos are downloaded
        return save(p)
    _make_excerpt(p, scene)
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
    if not new and not p.get("pending_excerpts"):
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
    p.pop("fetch_note", None)          # the search note was for the step just left
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


def set_credits(pid: str, credits: str) -> Dict:
    """The credits line, corrected by hand until the final render (Script
    d'abord never showed it: a source could be left out unseen)."""
    p = load(pid)
    _expect(p, "sources_review", "script_review", "preview_review")
    p["credits"] = " ".join((credits or "").split())[:160]
    return save(p)


# ---------------------------------------------------------------- 2. scripts

def run_scripts(pid: str, report: Optional[Report] = None, only: Optional[str] = None):
    """Every channel's script (or one, after an angle change). A project made
    with "une version différente par chaîne" gives each channel its angle."""
    report = report or (lambda phase, f: None)
    p = load(pid)
    try:
        clips = {k: c for k, c in p["clips"].items() if c.get("usable")}
        if p.get("versions") and not p.get("angles"):
            report("angles des versions", 0.02)
            p["angles"] = storyboard.angles(p["reference"], max(3, len(p["targets"])))
            for i, t in enumerate(p["targets"]):
                t.setdefault("angle", p["angles"][i % len(p["angles"])])
            save(p)
        todo = [t for t in p["targets"] if only is None or t["channel"] == only]
        n = len(todo)

        def one(i, t):                  # every channel's script at the same time
            label = langs.lang(t["language"])["label"]
            report(f"script {label}" + (f" : « {t['angle']['titre']} »" if t.get("angle") else ""), (i + 0.1) / n)
            sc = script.write(p["reference"], clips, t["language"], angle=t.get("angle"))
            report(f"relecture {label}", (i + 0.6) / n)
            sc = script.critique(sc, t["language"], clips)
            seen = annotate.review(sc["passages"], p["clips"], os.path.join(project_dir(pid), "work", t["channel"]))
            if seen is not None:        # the arrows decided again looking at the clips themselves
                for x, a in zip(sc["passages"], seen):
                    x["annotation"] = a
            fx = effects.decide(sc["passages"], p["clips"], os.path.join(project_dir(pid), "work", t["channel"]))
            fx = effects.auto_zoom(sc["passages"], p["clips"], fx or [], os.path.join(project_dir(pid), "work", t["channel"]))
            for x, e in zip(sc["passages"], fx):
                x["effets"] = e
            for attempt in (1, 2):                     # what the re-read missed is fixed (twice at most), then shown
                left = script.problems(sc, p["clips"], t["language"])
                if not left:
                    break
                report(f"correction {label}", (i + 0.85) / n)
                try:
                    fixed = script.revise(sc, clips, "Corrige ces problemes : " + " ".join(left) + FIX_HOW)
                except script.ScriptError:
                    break
                if len(script.problems(fixed, p["clips"], t["language"])) >= len(left):
                    break
                sc = {**fixed, "corrections": sc.get("corrections", []) + ["Correction automatique : " + " ".join(left)]}
            report(f"chaque phrase comparée à son image ({label})", (i + 0.95) / n)
            work = os.path.join(project_dir(pid), "work", t["channel"])
            t["accords"] = _judge(sc, p["clips"], t["language"], work)
            swaps = _swap_clips(sc, t["accords"])
            if swaps:                   # a sentence over the wrong picture: another clip that shows it, the words kept
                sc = {**sc, "corrections": sc.get("corrections", []) + swaps}
                t["accords"] = _judge(sc, p["clips"], t["language"], work)
            t.update(script=sc, problems=_fetched_problems(sc, p["clips"], t["language"], t["accords"]), approved=False,
                     validated=False, preview=None, voice=None)
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max(1, n)) as pool:
            for f in [pool.submit(one, i, t) for i, t in enumerate(todo)]:
                f.result()
        p.update(status="script_review", error=None, failed_step=None)
        if not p.get("credits") or p.get("credits") == p.get("credits_auto"):     # never over a correction
            p["credits"] = p["credits_auto"] = credits_for_scripts(p) or p.get("credits")
        save(p)
    except Exception as e:
        fail(pid, "scripting", e)
    report("terminé", 1.0)


def change_target_angle(pid: str, channel: str, index: Optional[int] = None, custom: Optional[str] = None) -> Dict:
    """"Sources d'abord" with versions: another angle for one channel, its script is written again."""
    p = load(pid)
    _expect(p, "script_review")
    t = target(p, channel)
    if custom and custom.strip():
        t["angle"] = {"titre": custom.strip()[:80], "idee": custom.strip()[:400]}
    elif index is not None and 0 <= index < len(p.get("angles") or []):
        t["angle"] = p["angles"][index]
    else:
        raise PipelineError("Choisis un angle.")
    p["status"] = "scripting"
    return save(p)


def start_scripts(pid: str) -> Dict:
    p = load(pid)
    _expect(p, "sources_review")
    if not any(c.get("usable") for c in p["clips"].values()):
        raise PipelineError("Garde au moins un clip.")
    p["status"] = "scripting"
    return save(p)


def _swap_clips(sc: Dict, accords: Optional[List[Dict]]) -> List[str]:
    """Each passage judged "non" takes the other clip the judge says shows its
    sentence, when no other passage uses it (measured in Sources d'abord: the
    proposed sentences fitted the picture but lost the story — an Arabic hook
    turned to "how does the tuna eat?"). Returns what was changed."""
    used, done = {x["clip"] for x in sc["passages"]}, []
    for k, (x, a) in enumerate(zip(sc["passages"], accords or [])):
        other = (a or {}).get("autre_clip")
        if a and a["note"] == "non" and other and other not in used and _accord(accords, k, x):
            used.discard(x["clip"])
            done.append(f"Passage {k + 1} : clip {x['clip']} remplacé par {other} ({a['pourquoi']})")
            x["clip"] = other
            used.add(other)
    return done


def _rejudge(p: Dict, t: Dict) -> None:
    """A clip or a sentence changed by hand: judged again (it escaped the check)."""
    sc = t.get("script") or {}
    if any(not _accord(t.get("accords"), k, x) for k, x in enumerate(sc.get("passages") or [])):
        fresh = _judge(sc, p["clips"], t["language"], os.path.join(project_dir(p["project_id"]), "work", t["channel"]))
        if fresh is not None:
            old = t.get("accords") or []
            for k, a in enumerate(fresh):           # "garder quand même" survives for an unchanged passage
                if k < len(old) and old[k] and old[k].get("garde") and old[k]["clip"] == a["clip"] \
                        and old[k]["texte"] == a["texte"]:
                    a["garde"] = True
            t["accords"] = fresh


def _commit(pid: str, channel: str, done: Dict) -> Dict:
    """A slow check (the judge, the chat: 20 s to minutes) ran on a copy:
    written on the project as it is now, never over a step started meanwhile
    (measured: a save still judging wrote "script_review" over the voicing
    that had just begun)."""
    p = load(pid)
    if p["status"] != "script_review":
        raise PipelineError("Une étape a démarré pendant la vérification : ta modification n'est pas enregistrée.")
    target(p, channel).update({k: done.get(k) for k in ("script", "accords", "problems", "approved")})
    return save(p)


def use_clip_proposal(pid: str, channel: str, k: int) -> Dict:
    """The other clip the check found for a sentence: the sentence stays."""
    p = load(pid)
    t, x, a = _passage_accord(p, channel, k)
    other = a.get("autre_clip")
    if not other or other not in p["clips"]:
        raise PipelineError("Pas d'autre clip proposé pour ce passage.")
    x["clip"] = other
    _rejudge(p, t)
    t.update(problems=_fetched_problems(t["script"], p["clips"], t["language"], t.get("accords")), approved=False)
    return _commit(pid, channel, t)


def edit_script(pid: str, channel: str, new: Dict) -> Dict:
    p = load(pid)
    _expect(p, "script_review")
    t = target(p, channel)
    sc = script.normalise({**(t["script"] or {}), **new}, p["clips"])
    t["script"] = {**sc, "corrections": (t["script"] or {}).get("corrections", [])}
    _rejudge(p, t)                      # a clip changed by hand is checked too
    t.update(problems=_fetched_problems(sc, p["clips"], t["language"], t.get("accords")), approved=False)
    return _commit(pid, channel, t)


def _passage_accord(p: Dict, channel: str, k: int) -> Tuple[Dict, Dict, Dict]:
    _expect(p, "script_review")
    t = target(p, channel)
    ps = (t.get("script") or {}).get("passages") or []
    if not 0 <= k < len(ps):
        raise PipelineError("Passage inconnu.")
    a = _accord(t.get("accords"), k, ps[k])
    if not a:
        raise PipelineError("Ce passage n'a pas de contrôle phrase/image en cours (la phrase ou le clip a changé).")
    return t, ps[k], a


def keep_passage(pid: str, channel: str, k: int) -> Dict:
    """You have the last word: the sentence stays on its clip."""
    p = load(pid)
    t, _, a = _passage_accord(p, channel, k)
    a["garde"] = True
    t.update(problems=_fetched_problems(t["script"], p["clips"], t["language"], t["accords"]), approved=False)
    return save(p)


def use_proposal(pid: str, channel: str, k: int) -> Dict:
    """The sentence the check wrote for what the clip really shows."""
    p = load(pid)
    t, x, a = _passage_accord(p, channel, k)
    if not a.get("proposition"):
        raise PipelineError("Pas de phrase proposée pour ce passage.")
    x["texte"] = a["proposition"]
    if a.get("bandeau"):                # measured: "wet leaves: heavy mud" stayed over "the blower only works dry"
        x["bandeau"] = a["bandeau"]
    x["mots_cles"] = [m for m in x.get("mots_cles") or [] if m.lower() in x["texte"].lower()]   # words of the old one
    a.update(texte=x["texte"], note="bon", proposition="", pourquoi="phrase réécrite pour son image")
    if p.get("mode") == "script" and k < len(_active(p)):  # the storyboard says the same: a new fetch keeps it
        textes = p["storyboard"]["plans"][_active(p)[k]].get("textes") or {}
        if t["language"] in textes:
            textes[t["language"]].update(texte=x["texte"], bandeau=x.get("bandeau", ""), mots_cles=x["mots_cles"])
    t.update(problems=_fetched_problems(t["script"], p["clips"], t["language"], t["accords"]), approved=False)
    return save(p)


def revise_script(pid: str, channel: str, request: str) -> Dict:
    p = load(pid)
    _expect(p, "script_review")
    t = target(p, channel)
    sc = script.revise(t["script"], {k: c for k, c in p["clips"].items() if c.get("usable")}, request)
    t["script"] = sc
    _rejudge(p, t)                      # measured: a sentence the chat rewrote lost its ❌ and was never checked
    t.update(problems=_fetched_problems(sc, p["clips"], t["language"], t.get("accords")), approved=False)
    return _commit(pid, channel, t)


def approve_script(pid: str, channel: str) -> Dict:
    p = load(pid)
    _expect(p, "script_review")
    t = target(p, channel)
    problems = _fetched_problems(t["script"] or {}, p["clips"], t["language"], t.get("accords"))
    if problems:
        raise PipelineError("À corriger avant de valider : " + " ".join(problems))
    t["approved"] = True
    return save(p)


# ---------------------------------------------------------------- 3. voice + preview

def _make(p: Dict, t: Dict, preview: bool, report: Report, share: float, offset: float) -> Dict:
    base = os.path.join(project_dir(p["project_id"]), t["channel"])
    voice_mp3 = os.path.join(base, "voice.mp3")
    texts = [x["texte"] for x in t["script"]["passages"]]
    v = t.get("voice") or {}
    if not v or v.get("voice_id") != t["voice_id"] or v.get("texts", texts) != texts:   # never pay twice for the same narration
        report(f"voix {t['channel']}", offset)
        t["voice"] = voices.synthesize(t["script"]["passages"], t["voice_id"], t["language"], voice_mp3)
        t["voice"].update(voice_id=t["voice_id"], texts=texts)
    for vp, sp in zip(t["voice"]["passages"], t["script"]["passages"]):      # back from the preview: a clip or a banner changed
        vp.update({k: sp[k] for k in ("clip", "bandeau", "mots_cles") if k in sp})
    out = os.path.join(base, "preview.mp4" if preview else "final.mp4")
    _choose_music(p, t)
    beats = _beats(t)
    fx = _effects(p, t, os.path.join(base, "work"))
    anns = _annotations(p, t, os.path.join(base, "work"), report, offset + share * 0.2, fx, beats)
    report(f"{'aperçu' if preview else 'rendu'} {t['channel']}", offset + share * 0.3)
    r = render.render(t["voice"]["passages"], t["voice"]["words"], p["clips"], voice_mp3, t["language"], out,
                      os.path.join(base, "work"), credit=p["credits"],
                      music=(t["music_path"], t["music_start"]) if t.get("music_path") else None, preview=preview,
                      progress_cb=lambda f: report(f"{'aperçu' if preview else 'rendu'} {t['channel']}",
                                                   offset + share * (0.3 + 0.6 * f)), annotations=anns,
                      style=_style_of(t), effects=fx, beats=beats)
    t["style"] = _style_of(t)           # the look really used (the channel's may have changed since the project began)
    r["recette"] = _recipe(p, t, r.get("recette") or {})
    c = checks.verify(out, voice_mp3, t["voice"]["passages"], [x["start"] for x in r.get("segments") or []] or None)
    return {"path": out, "summary": r, "checks": c, "recette": r["recette"]}


def _recipe(p: Dict, t: Dict, rendered: Dict) -> Dict:
    """Everything that made this video, in one place: kept with the final
    render and its publication record, to compare with how the audience
    liked it and to make another video the same way."""
    sc, plans = t.get("script") or {}, rendered.get("plans") or []
    segs = [x for x in plans]
    total = round(sum(x.get("duree", 0) for x in segs), 2)
    return {
        "projet": p["project_id"], "mode": p.get("mode") or "sources", "angle": (t.get("angle") or p.get("angle") or {}).get("titre"),
        "langue": t["language"], "chaine": t["channel"], "voix": t.get("voice_id"), "style": rendered.get("style"),
        "musique": {"fichier": os.path.basename(t.get("music_path") or "") or None, "debut_s": t.get("music_start"),
                    "pourquoi": t.get("music_why"), "tempo": rendered.get("tempo_musique"),
                    "niveau": rendered.get("musique_niveau"), "gain": rendered.get("musique_gain"),
                    "silence_avant_choc_s": rendered.get("silence_avant_choc")},
        "effets_sonores": rendered.get("effets_sonores") or [],
        "structure": {"duree_s": total, "plans": len(segs), "accroche_s": segs[0]["duree"] if segs else None,
                      "plan_moyen_s": round(total / len(segs), 2) if segs else None,
                      "coupes_sur_le_temps": sum(1 for x in segs if x.get("coupe_sur_le_temps")),
                      "fin_en_boucle": rendered.get("fin_en_boucle")},
        "titre": sc.get("titre"),
        "plans": [{**x, "texte": ps.get("texte"), "bandeau": ps.get("bandeau"), "mots_cles": ps.get("mots_cles"),
                   "fleche": ps.get("annotation"), "effets_demandes": ps.get("effets"),
                   "image": (p["clips"].get(ps.get("clip")) or {}).get("desc"),
                   "source": _source_url(p, p["clips"].get(ps.get("clip")) or {})}
                  for x, ps in zip(segs, sc.get("passages") or [])],
    }


def _source_url(p: Dict, c: Dict) -> Optional[str]:
    """The video a clip was cut from: its pick (Script d'abord), else the
    project's source list (Sources d'abord)."""
    if c.get("pick_key"):
        return c["pick_key"][0]
    urls, i = p.get("source_urls") or [], c.get("source")
    return urls[i] if isinstance(i, int) and 0 <= i < len(urls) else None


def _style_of(t: Dict) -> str:
    """The channel's look as set now in Réglages → Voix (a change applies to the
    projects under way), else the one it had when the project was made."""
    try:
        from channel_manager import ChannelManager
        return settings.channel_settings(ChannelManager().get_channel_profile(t["channel"]))["style"]
    except Exception:
        return t.get("style") or "classique"


def _effects(p: Dict, t: Dict, work: str) -> List[Optional[Dict]]:
    """The montage effects of each passage, ready for render: a zoom's target
    found once on the clip at its strong moment (kept for the final render)."""
    passages = (t.get("script") or {}).get("passages") or []
    cache, out = t.setdefault("fx_cache", {}), []
    os.makedirs(work, exist_ok=True)
    for k, x in enumerate(passages):
        e, c = effects.clean(x.get("effets")), p["clips"].get(x.get("clip"))
        if not e or not c:
            out.append(None)
            continue
        e = dict(e)
        if e.get("zoom") and (x.get("annotation") or {}).get("cible"):
            e["zoom"] = None                    # the arrow is placed on the unzoomed picture: it wins
        if e.get("zoom"):
            key = f"{x['clip']}|{round(c['impact'], 2)}|{e['zoom']}"
            if key not in cache:
                try:
                    still = sources.still(c["src"], c["impact"], c.get("crop"), os.path.join(work, f"zoom{k}.jpg"),
                                          c.get("delogo"), (c["w"], c["h"]))
                    cache[key] = annotate.locate([still], e["zoom"])[0]
                except Exception:
                    cache[key] = None
            e["zoom"] = effects.zoom_of(c, cache[key])     # not found: no zoom, never a wrong one
        out.append(e)
    return out


MOOD_PROMPT = """Choisis la musique de fond d'un YouTube Short parmi les morceaux de la chaine.
Le Short : « {titre} » — {resume}
Morceaux (nom du fichier / tempo / energie mesures) :
{morceaux}
Prends celui dont l'ambiance colle le mieux au ton du Short (tension, danger, humour, emotion, science calme...).
JSON uniquement : {{"morceau": numero, "pourquoi": "une phrase en francais"}}"""


def _track_info(path: str) -> Dict:
    """Tempo, energy and the strongest 40 s of a track (cached next to it)."""
    import json as _json, hashlib
    os.makedirs(os.path.join("temp", "music_info"), exist_ok=True)   # never a file in the person's music folder
    cache = os.path.join("temp", "music_info", hashlib.md5(os.path.abspath(path).encode()).hexdigest() + ".json")
    if os.path.exists(cache):
        try:
            return _json.load(open(cache, encoding="utf-8"))
        except Exception:
            pass
    import numpy as np
    raw = __import__("subprocess").run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "4000", "-f", "f32le", "-"],
                                       capture_output=True).stdout
    y = np.frombuffer(raw, np.float32)
    dur = len(y) / 4000
    rms = np.sqrt(np.convolve(np.square(y), np.ones(4000) / 4000, mode="valid")[::4000]) if len(y) > 4000 else np.array([0.0])
    win = 40
    best = max(range(max(1, len(rms) - win)), key=lambda i: float(rms[i:i + win].mean())) if len(rms) > win else 0
    beats = render.beats_of(path, max(0.0, best), 20)
    info = {"duree": round(dur, 1), "energie": round(float(rms.mean()) * 100, 1), "debut_fort": float(best),
            "bpm": round(60 / (beats[1] - beats[0])) if len(beats) > 1 else None}
    try:
        _json.dump(info, open(cache, "w", encoding="utf-8"))
    except OSError:
        pass
    return info


def _choose_music(p: Dict, t: Dict) -> None:
    """With several tracks in the channel's library, the AI picks the one that
    fits this Short's tone (once per version) and its strongest part; with a
    single track nothing changes. A track chosen by hand is kept."""
    if t.get("music_chosen") or not t.get("music_path"):
        return
    folder = os.path.dirname(t["music_path"])
    tracks = sorted(f for f in os.listdir(folder) if f.lower().endswith((".mp3", ".wav", ".m4a"))) if os.path.isdir(folder) else []
    t["music_chosen"] = True
    if len(tracks) < 2:
        return
    try:
        infos = [_track_info(os.path.join(folder, f)) for f in tracks]
        listing = "\n".join(f"{n}. {f} / {i['bpm'] or '?'} BPM / energie {i['energie']}" for n, (f, i) in enumerate(zip(tracks, infos), 1))
        sc = t.get("script") or {}
        r = script._gemini()._generate_content(
            [{"text": MOOD_PROMPT.format(titre=sc.get("titre", ""), resume=" ".join(x["texte"] for x in sc.get("passages") or [])[:600],
                                         morceaux=listing)}], max_tokens=1000, timeout=60, temperature=0.2)
        n = int(r.get("morceau")) - 1
    except Exception:
        return
    if 0 <= n < len(tracks):
        t.update(music_path=os.path.join(folder, tracks[n]), music_start=infos[n]["debut_fort"],
                 music_why=str(r.get("pourquoi") or "")[:200])


def _beats(t: Dict) -> Optional[List[float]]:
    """The music's beats in video time, for the cuts (none without music)."""
    if not t.get("music_path") or not os.path.exists(t["music_path"]):
        return None
    try:
        return render.beats_of(t["music_path"], float(t.get("music_start") or 0), 90) or None
    except Exception:
        return None


def _annotations(p: Dict, t: Dict, work: str, report: Report, at: float,
                 fx: Optional[List[Optional[Dict]]] = None, beats: Optional[List[float]] = None) -> List[Dict]:
    """The arrows/circles the script asks for, located once (the final render
    reuses the preview's track); a target not found is simply left out."""
    passages = (t.get("script") or {}).get("passages") or []
    wanted = [(k, x["annotation"]) for k, x in enumerate(passages) if (x.get("annotation") or {}).get("cible")]
    if not wanted:
        return []
    report(f"flèches et cercles {t['channel']}", at)
    segs, _ = render.build_timeline(t["voice"]["passages"], p["clips"], fx, beats)
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

def _thumbnail(made: Dict, video: str) -> Optional[str]:
    """The cover picture: the hook's strongest instant (the most spectacular
    second the re-timing saw), taken from the final video with its banner."""
    segs = (made.get("summary") or {}).get("segments") or []
    if not segs:
        return None
    at = min(max(segs[0].get("impact", 0.5), 0.2), max(0.2, segs[0]["end"] - 0.1))
    out = os.path.splitext(video)[0] + ".jpg"
    import subprocess as _sp
    r = _sp.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.2f}", "-i", video, "-frames:v", "1", "-q:v", "2", out])
    return out if r.returncode == 0 and os.path.exists(out) else None


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
            try:                        # the common shape (recette.py), the Adaptation's own one inside
                import recette
                rec["recette"] = recette.from_adaptation(made.get("recette") or {}, t.get("music_path"))
            except Exception:
                rec["recette"] = made.get("recette")
            thumb = _thumbnail(made, dest)
            if thumb:
                rec["thumbnail_path"] = thumb
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
