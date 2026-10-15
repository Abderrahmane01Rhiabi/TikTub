"""
The montage inside the Import flow.

    Cadrage    the video is set to edit_mode 'montage' (or its channel
               defaults to it)
    Traiter    prepare_review(): Whisper + Gemini plan + keywords + two drone
               shots -> status 'montage_review', nothing rendered yet
    Montage    the person checks the plan (hook, keywords, drones, preview)
               and validates -> back to 'selected' with montage.validated
    Traiter    render_final(): the real render, then the usual AI pass

Everything the review step needs lives in video["montage"]:
    words, plan, keywords, hooks, hook, brolls (clip ids), validated,
    unsuitable (why the clip may be a poor fit), error, preview_path
"""

import os
import time
from typing import Callable, Dict, List, Optional

from montage import broll, planner, recipes, render
from montage.transcribe import transcribe

Report = Callable[[str, float], None]


def work_dir(video_id: str) -> str:
    """Kept under temp/<video_id>/ so storage cleanup treats it with the rest
    of that video's files."""
    path = os.path.join("temp", video_id, "montage")
    os.makedirs(path, exist_ok=True)
    return path


def music_path(settings: Dict, music_dir: Optional[str]) -> Optional[str]:
    name = settings.get("music_file")
    if not name or not music_dir:
        return None
    path = os.path.join(music_dir, os.path.basename(name))
    return path if os.path.exists(path) else None


def prepare_review(video: Dict, channel: str, report: Optional[Report] = None) -> Dict:
    """Transcribes and plans one clip. Returns the montage record to store —
    with 'error' set (and no exception) when it can't be planned, so the
    review step can say why and offer a retry or the simple mode."""
    report = report or (lambda phase, f: None)
    raw = video["raw_video_path"]
    montage = {"validated": False, "planned_at": time.time(), "error": None}
    try:
        report("transcription", 0.0)
        words = transcribe(raw)
        montage["words"] = words
        report("plan IA", 0.5)
        plan = planner.plan_video(raw, words)
        report("plan IA", 0.85)
        montage["plan"] = plan
        montage["keywords"] = planner.pick_keywords(words)
        montage["hooks"] = plan.get("accroches") or []
        montage["hook"] = montage["hooks"][0] if montage["hooks"] else ""
        montage["brolls"] = [c["id"] for c in broll.pick(channel, 2, seed=video["video_id"],
                                                         video_id=video["video_id"])]
        montage["unsuitable"] = planner.unsuitable_reason(plan)
        if len(montage["brolls"]) < 2:
            montage["unsuitable"] = (montage["unsuitable"] or "") + \
                " Bibliothèque de drones vide : ajoute des plans dans Réglages → Drones."
    except planner.PlanError as e:
        montage["error"] = str(e)
    report("plan IA", 1.0)
    return montage


def _broll_files(montage: Dict, channel: str, video_id: str) -> List[str]:
    """Paths of the chosen shots; a shot deleted from the library since the
    review is replaced by a fresh pick instead of failing the render."""
    files, ids = [], []
    for clip_id in montage.get("brolls") or []:
        clip = broll.get_clip(clip_id)
        if clip and os.path.exists(broll.clip_path(clip)):
            files.append(broll.clip_path(clip))
            ids.append(clip["id"])
    if len(files) < 2:
        for clip in broll.pick(channel, 2 - len(files), seed=time.time(), exclude=ids, video_id=video_id):
            files.append(broll.clip_path(clip))
            ids.append(clip["id"])
    montage["brolls"] = ids
    return files


def _render(video: Dict, profile: Dict, music_dir: Optional[str], out_path: str,
            preview: bool, progress_cb=None) -> Dict:
    m = video.get("montage") or {}
    if not m.get("plan"):
        raise RuntimeError("Pas de plan de montage : relance l'analyse.")
    settings = recipes.resolve_settings(profile, video)
    channel = video.get("channel", "default")
    return render.render(
        video["raw_video_path"], [tuple(w) for w in m.get("words") or []], m["plan"], settings, out_path,
        broll_paths=_broll_files(m, channel, video["video_id"]), keywords=m.get("keywords") or [], hook=m.get("hook"),
        music_path=music_path(settings, music_dir), work_dir=work_dir(video["video_id"]),
        preview=preview, progress_cb=progress_cb)


def render_preview(video: Dict, profile: Dict, music_dir: Optional[str]) -> str:
    out = os.path.join(work_dir(video["video_id"]), "preview.mp4")
    _render(video, profile, music_dir, out, preview=True)
    return out


def render_final(video: Dict, profile: Dict, music_dir: Optional[str], out_path: str,
                 progress_cb=None) -> Dict:
    summary = _render(video, profile, music_dir, out_path, preview=False, progress_cb=progress_cb)
    broll.record_usage(video.get("channel", "default"), video["montage"]["brolls"], video["video_id"])
    return summary


def swap_broll(video: Dict, slot: int) -> List:
    """Replaces the drone shot in `slot` (0 or 1) with another one."""
    m = video.get("montage") or {}
    ids = list(m.get("brolls") or [])
    while len(ids) < 2:
        ids.append(None)
    fresh = broll.pick(video.get("channel", "default"), 1, seed=time.time(), exclude=[i for i in ids if i],
                       video_id=video["video_id"])
    if fresh:
        ids[slot] = fresh[0]["id"]
    return [i for i in ids if i is not None]


def timeline(video: Dict, profile: Dict) -> Optional[Dict]:
    """What the review step draws: the output timeline with the black
    screen, drone and punchline segments, plus notes on refused parts."""
    m = video.get("montage") or {}
    if not m.get("plan"):
        return None
    settings = recipes.resolve_settings(profile, video)
    words = [tuple(w) for w in m.get("words") or []]
    edit = render.resolve_plan(m["plan"], words, recipes.recipe(settings))
    segments = []
    noir = edit.out_range(edit.noir)
    if noir:
        segments.append({"kind": "noir", "start": round(noir[0], 2), "end": round(noir[1], 2)})
    for k, (s, e) in enumerate(render.drone_slots(edit, recipes.recipe(settings)["drones"]["count"])):
        segments.append({"kind": "drone", "slot": k, "start": round(s, 2), "end": round(e, 2)})
    chute = edit.to_out(edit.chute) if edit.chute is not None else None
    return {"total": round(edit.total, 2), "segments": segments,
            "chute": round(chute, 2) if chute is not None else None,
            "cuts": [round(edit.to_out(a), 2) for a, _ in edit.keep[1:]], "notes": edit.notes,
            # words still heard in the montage (the review only offers those as keywords)
            "kept_words": [i for i, (w, a, b) in enumerate(words) if _heard(edit, a, b)]}


def _heard(edit, a: float, b: float) -> bool:
    """Same rule as the captions: the word fits inside a kept range."""
    oa, ob = edit.to_out(a), edit.to_out(b)
    return oa is not None and ob is not None and ob > oa
