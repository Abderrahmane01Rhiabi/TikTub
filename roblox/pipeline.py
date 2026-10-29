"""
A Montage Roblox project: one long video -> one Short per chosen style and language.

    analysing    the video's facts and subtitles, the most replayed passages downloaded, their moments found,
                 the plan written (which moment for which style, every text in every language); his voice
                 replaced: each passage used split into his voice and the game's sounds, his lines written
    plan_review  the person reads and corrects the texts (nothing rendered or paid for yet but Gemini)
    rendering    every Short made (the told story's voice is the only ElevenLabs cost)
    review       the person watches them and sends the ones kept to Publication
    done         every Short sent

The Shorts reach Publication like an Adaptation's videos: ready_for_upload, with their title, description,
tags and the credit of the original video.
"""

import os
import shutil
import subprocess
import uuid
from datetime import datetime
from typing import Callable, Dict, List, Optional

import db
from roblox import moments, plan, render, sources, voix

Report = Callable[[str, float], None]
LANGS = ("fr", "en", "ar", "es")
MUSIC = ("original", "chaine")              # keep the original sound, or a track of the channel instead
PLAYER = ("remplacer", "originale")         # the player's voice replaced by the chosen one (etude_roblox/voix), or kept


class PipelineError(RuntimeError):
    pass


def project_dir(pid: str) -> str:
    return os.path.join("temp", "roblox", pid)


def load(pid: str) -> Dict:
    p = db.get_roblox(pid)
    if not p:
        raise PipelineError("Projet introuvable.")
    return p


def save(p: Dict) -> Dict:
    return db.save_roblox(p)


def fail(pid: str, step: str, e: Exception) -> None:
    p = load(pid)
    p.update(status="error", error=str(e)[:500], failed_step=step)
    save(p)


def _expect(p: Dict, *statuses: str) -> None:
    if p["status"] not in statuses:
        raise PipelineError("Ce projet n'est pas à cette étape (" + p["status"] + ").")


def voice_for(lang: str, channel_settings: Dict, chosen: Optional[str] = None) -> Optional[str]:
    """The voice chosen in the catalogue, else its best one; a language without a catalogue: the channel's voice."""
    if chosen:
        if not voix.known(lang, chosen):
            raise PipelineError("Cette voix n'est pas dans la liste des voix de cette langue.")
        return chosen
    return voix.DEFAULTS.get(lang) or channel_settings.get("voice_id")


def create(url: str, styles: List[str], targets: List[Dict], music: str = "original", voix_joueur: str = "remplacer") -> Dict:
    """targets: [{"langue", "channel", "profile", "music_dir", "voice_id" (optional)}] — one channel per language."""
    from adaptation import settings
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise PipelineError("Colle le lien de la vidéo longue (YouTube…).")
    styles = [s for s in plan.STYLES if s in (styles or [])]
    if not styles:
        raise PipelineError("Choisis au moins un style.")
    if not targets or any(t.get("langue") not in LANGS for t in targets) or len({t["langue"] for t in targets}) < len(targets):
        raise PipelineError("Choisis une chaîne par langue (français, anglais…).")
    if music not in MUSIC:
        raise PipelineError("Musique inconnue.")
    if voix_joueur not in PLAYER:
        raise PipelineError("Choix inconnu pour la voix du joueur.")
    tg = []
    for t in targets:
        s = settings.channel_settings(t.get("profile"))
        track = os.path.join(t["music_dir"], s["music_file"]) if s.get("music_file") and t.get("music_dir") else None
        first = voice_for(t["langue"], s, t.get("voice_id"))
        players = {"1": first}
        if voix.CATALOGUE.get(t["langue"]):       # the 2nd player's voice, chosen or the default one
            players["2"] = voice_for(t["langue"], s, t.get("voix_2")) if t.get("voix_2") else voix.default_for(t["langue"], "2", players)
        tg.append({"langue": t["langue"], "channel": t["channel"], "voice_id": first, "voix_joueurs": players,
                   "music_path": track if track and os.path.exists(track) else None})
    if music == "chaine" and not all(t["music_path"] for t in tg):
        raise PipelineError("Pour remplacer la musique, choisis d'abord une musique pour chaque chaîne (Réglages → Voix).")
    pid = "rb_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]
    return save({"project_id": pid, "status": "analysing", "url": url, "styles": styles, "targets": tg, "musique": music,
                 "voix_joueur": voix_joueur, "meta": None, "catalogue": [], "plan": {}, "absents": [], "traductions": {}, "videos": {}, "error": None})


def _catalogue(p: Dict) -> Dict[str, Dict]:
    return {m["id"]: m for m in p["catalogue"]}


def styles_of_moments(made: Dict) -> Dict[str, List[str]]:
    """Which styles show each moment."""
    out: Dict[str, List[str]] = {}
    for style, st in made.items():
        for mid in [st["moment"]] if st.get("moment") else [x["moment"] for x in st.get("passages") or st.get("rangs") or []]:
            if style not in out.setdefault(mid, []):
                out[mid].append(style)
    return out


MARGIN = 1.5                                # his lines are read from a little before the moment to a little after


def _his_voice(p: Dict, cat: List[Dict], made: Dict, meta: Dict, report: Report) -> Dict:
    """Each passage the Shorts use split (his voice / the rest), and his lines in every moment where he is heard —
    the told story covers him with its narrator: only its passages' game sounds are needed."""
    by_id = {m["id"]: m for m in cat}
    used = styles_of_moments(made)
    files = sorted({by_id[mid]["fichier"] for mid in used})
    parts = {}
    for k, f in enumerate(files):
        report(f"sa voix séparée des bruits du jeu ({k + 1}/{len(files)})", 0.86 + 0.08 * k / len(files))
        parts[f] = voix.separate(f, os.path.join(project_dir(p["project_id"]), "voix", os.path.splitext(os.path.basename(f))[0]))
    words, langs, lines = sources.words(meta.get("sous_titres")), [t["langue"] for t in p["targets"]], {}
    talking = [mid for mid, sts in used.items() if sts != ["histoire"]]
    players: Dict[str, str] = {}                     # the same person keeps the same number from moment to moment
    for k, mid in enumerate(talking):
        report(f"l'IA écoute ses répliques ({k + 1}/{len(talking)})", 0.94 + 0.05 * k / len(talking))
        m = by_id[mid]
        a, b = max(0.0, m["debut"] - MARGIN), min(m["fichier_duree"], m["fin"] + MARGIN)
        said = [{**l, "a": l["a"] - m["t0"]} for l in render.dialogue_lines(words, m["t0"] + a, m["t0"] + b)]
        got = voix.write_lines(parts[m["fichier"]]["voix"], a, b, m.get("resume") or "", said, langs, joueurs=players)
        for l in got:
            if not players.get(l["qui"]):
                players[l["qui"]] = l.get("nom") or ""
        lines[mid] = {"a": a, "b": b, "lignes": got}
    return {"fichiers": parts, "repliques": lines, "joueurs": players}


def run_analysis(pid: str, report: Optional[Report] = None) -> None:
    report = report or (lambda phase, f: None)
    p = load(pid)
    try:
        work = project_dir(pid)
        report("lecture de la vidéo", 0.03)
        meta = sources.info(p["url"], work)
        wins = sources.windows(meta)
        if not wins:
            raise PipelineError("Vidéo vide ou sans durée.")
        cat = []
        for k, (a, b) in enumerate(wins):
            report(f"passage {k + 1}/{len(wins)} : téléchargement", 0.05 + 0.75 * k / len(wins))
            path = sources.download(p["url"], os.path.join(work, "src"), [[a, b]])[0]
            dur = render_duration(path)
            report(f"passage {k + 1}/{len(wins)} : l'IA cherche les moments", 0.05 + 0.75 * (k + 0.5) / len(wins))
            for i, m in enumerate(moments.find(path, dur)):
                cat.append({**m, "id": f"w{int(a)}#{i}", "fichier": path, "fichier_duree": dur, "t0": a})
        if not cat:
            raise PipelineError("Aucun moment exploitable trouvé dans cette vidéo.")
        report("l'IA écrit les textes de chaque style", 0.85)
        made, dropped = plan.write(meta, cat, p["styles"], [t["langue"] for t in p["targets"]])
        if not made:
            raise PipelineError("Aucun style n'a trouvé de moment qui convienne. " + " ".join(dropped))
        his = _his_voice(p, cat, made, meta, report) if p.get("voix_joueur") == "remplacer" else None
        p = load(pid)
        p.update(meta={k: meta[k] for k in ("titre", "chaine", "duree", "langue", "vues", "sous_titres")},
                 catalogue=cat, plan=made, absents=dropped, voix=his, status="plan_review", error=None, failed_step=None)
        save(p)
    except Exception as e:
        fail(pid, "analysing", e)
    report("terminé", 1.0)


def render_duration(path: str) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise PipelineError(f"Passage téléchargé illisible : {os.path.basename(path)}")


# ---------------------------------------------------------------- the texts, read and corrected

EDITABLE = {"clip": ("titre",), "pov": ("pov",), "histoire": ("titre",), "top3": ("titre",), "devine": ("question", "final")}


def set_texts(pid: str, style: str, lang: str, edit: Dict) -> Dict:
    """edit: {"titre"/"pov"/"question"/"final": text, "passages": [text], "labels": [text],
    "publication": {"titre", "description", "tags"}}. A Short already made with older texts is made again."""
    p = load(pid)
    _expect(p, "plan_review", "review")
    st = p["plan"].get(style)
    if not st or lang not in {t["langue"] for t in p["targets"]}:
        raise PipelineError("Style ou langue absent de ce projet.")
    clean = lambda x: " ".join(str(x or "").split())
    for k in EDITABLE[style]:
        if k in edit and clean(edit[k]):
            st[k][lang] = clean(edit[k])
    for key, field, items in (("passages", "textes", st.get("passages")), ("labels", "label", st.get("rangs"))):
        for x, text in zip(items or [], edit.get(key) or []):
            if clean(text):
                x[field][lang] = clean(text)
    pub = edit.get("publication")
    if isinstance(pub, dict):
        cur = st["publication"][lang]
        cur.update({k: clean(pub[k]) for k in ("titre", "description") if clean(pub.get(k))})
        if isinstance(pub.get("tags"), list):
            cur["tags"] = [clean(t) for t in pub["tags"] if clean(t)][:12]
    v = p["videos"].get(f"{style}_{lang}")
    if v and not v.get("video_id"):
        v["a_refaire"] = True
    return save(p)


def player_voice(t: Dict, qui: str) -> Optional[str]:
    """The voice reading player qui in t's language (the 1st is also the told story's narrator)."""
    players = t.get("voix_joueurs") or {"1": t.get("voice_id")}
    if qui not in players:
        players[qui] = voix.default_for(t["langue"], qui, players) or t.get("voice_id")
    return players[qui]


def set_voice(pid: str, lang: str, qui: str, voice_id: str) -> Dict:
    """Another voice for one player in one language; the unsent Shorts where he speaks are made again."""
    p = load(pid)
    _expect(p, "plan_review", "review")
    t = next((x for x in p["targets"] if x["langue"] == lang), None)
    if not t:
        raise PipelineError("Langue absente de ce projet.")
    if not voix.known(lang, voice_id):
        raise PipelineError("Cette voix n'est pas dans la liste des voix de cette langue.")
    t.setdefault("voix_joueurs", {"1": t.get("voice_id")})[qui] = voice_id
    if qui == "1":
        t["voice_id"] = voice_id
    uses = styles_of_moments(p["plan"])
    styles = {s for mid, r in ((p.get("voix") or {}).get("repliques") or {}).items()
              if any(l.get("qui", "1") == qui for l in r["lignes"]) for s in uses.get(mid, [])}
    if qui == "1" and "histoire" in p["plan"]:
        styles.add("histoire")
    for style in styles:
        v = p["videos"].get(f"{style}_{lang}")
        if v and not v.get("video_id"):
            v["a_refaire"] = True
    return save(p)


def set_lines(pid: str, mid: str, lang: str, texts: List[str]) -> Dict:
    """His lines in one language for one moment, corrected (one text per line, in order; an empty one is kept as
    it was). The unsent Shorts showing that moment in that language are made again."""
    p = load(pid)
    _expect(p, "plan_review", "review")
    moment = ((p.get("voix") or {}).get("repliques") or {}).get(mid)
    if not moment:
        raise PipelineError("Ce moment n'a pas de répliques à corriger.")
    if lang not in {t["langue"] for t in p["targets"]}:
        raise PipelineError("Langue absente de ce projet.")
    for line, text in zip(moment["lignes"], texts or []):
        text = " ".join(str(text or "").split())
        if text:
            line[lang] = text
    for style in styles_of_moments(p["plan"]).get(mid, []):
        v = p["videos"].get(f"{style}_{lang}")
        if v and not v.get("video_id"):
            v["a_refaire"] = True
    return save(p)


# ---------------------------------------------------------------- the Shorts

def start_render(pid: str) -> Dict:
    p = load(pid)
    _expect(p, "plan_review", "review")
    p["status"] = "rendering"
    return save(p)


def _new_sound(p: Dict, t: Dict) -> tuple:
    """His voice replaced, in t's language: each passage with its new sound (the game's sounds and his lines read
    by t's voice) and those lines' captions. -> (catalogue with the new passages, {moment: captions})."""
    import hashlib
    import json
    cat, his = _catalogue(p), p.get("voix")
    if p.get("voix_joueur") != "remplacer" or not his:
        return cat, {}
    lang, work = t["langue"], os.path.join(project_dir(p["project_id"]), "voix")
    os.makedirs(os.path.join(work, "lu"), exist_ok=True)
    tracks: Dict[str, List] = {}
    captions = {}
    for mid, r in his["repliques"].items():
        m = cat[mid]
        lines = [{"a": l["a"], "texte": l[lang], "voice": player_voice(t, l.get("qui", "1"))} for l in r["lignes"] if l.get(lang)]
        captions[mid] = []
        if lines:
            ref = voix.mean_db(his["fichiers"][m["fichier"]]["voix"], r["a"], r["b"])
            path, captions[mid] = voix.track(lines, lang, t["voice_id"], r["a"], r["b"], os.path.join(work, "lu"), ref)
            tracks.setdefault(m["fichier"], []).append((path, r["a"]))
    files = {}
    for f, parts in his["fichiers"].items():
        reste = None if p["musique"] == "chaine" else parts["reste"]
        key = hashlib.sha1(json.dumps([reste, tracks.get(f, [])]).encode()).hexdigest()[:10]
        out = os.path.join(work, f"{os.path.splitext(os.path.basename(f))[0]}_{lang}_{key}.mp4")
        files[f] = out if os.path.exists(out) else voix.passage_audio(f, reste, tracks.get(f, []), out)
    return {k: {**m, "fichier": files.get(m["fichier"], m["fichier"])} for k, m in cat.items()}, captions


def run_render(pid: str, report: Optional[Report] = None) -> None:
    """Every style x language not made yet (or whose texts changed), sent ones left alone."""
    report = report or (lambda phase, f: None)
    p = load(pid)
    try:
        words = sources.words((p["meta"] or {}).get("sous_titres"))
        out_dir = os.path.join(project_dir(pid), "out")
        todo = [(s, t) for s in p["styles"] if s in p["plan"] for t in p["targets"]
                if not (p["videos"].get(f"{s}_{t['langue']}") or {}).get("path") or p["videos"][f"{s}_{t['langue']}"].get("a_refaire")]
        sound = {}
        for k, (style, t) in enumerate(todo):
            lang, key = t["langue"], f"{style}_{t['langue']}"
            if lang not in sound:
                report(f"sa voix lue par la voix choisie ({lang})", 0.05 + 0.9 * k / max(1, len(todo)))
                sound[lang] = _new_sound(p, t)
            moments_, captions = sound[lang]
            report(f"{plan.STYLES[style][0]} ({lang}) : montage", 0.05 + 0.9 * (k + 0.3) / max(1, len(todo)))
            cache = p["traductions"].setdefault(lang, {})

            def translate(lines, to, cache=cache):
                missing = [l for l in lines if l not in cache]
                for src, dst in zip(missing, plan.translate(missing, to)):
                    cache[src] = dst
                return [cache.get(l, l) for l in lines]
            replaced = p.get("voix_joueur") == "remplacer" and bool(p.get("voix"))
            ctx = render.Context(moments_, words, lang, (p["meta"] or {}).get("langue") or "en", t["voice_id"],
                                 out_dir, translate, lines=captions, son_refait=replaced,
                                 voice_model=voix.MODEL if voix.known(lang, t["voice_id"]) else None)
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, f"{key}.mp4")
            music = t["music_path"] if p["musique"] == "chaine" else None
            duration = render.make(style, p["plan"][style], ctx, path, music)
            fresh = load(pid)
            fresh["traductions"] = p["traductions"]
            fresh["videos"][key] = {"style": style, "langue": lang, "channel": t["channel"], "path": path,
                                    "duree": duration, "video_id": None}
            p = save(fresh)
        p = load(pid)
        p.update(status="review", error=None, failed_step=None)
        save(p)
    except Exception as e:
        fail(pid, "rendering", e)
    report("terminé", 1.0)


def _thumbnail(video: str) -> Optional[str]:
    out = os.path.splitext(video)[0] + ".jpg"
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1.0", "-i", video, "-frames:v", "1", "-q:v", "2", out])
    return out if r.returncode == 0 and os.path.exists(out) else None


def send(pid: str, keys: List[str]) -> Dict:
    """The chosen Shorts to Publication, like an Adaptation's: ready_for_upload, with their texts and the credit."""
    p = load(pid)
    _expect(p, "review", "done")               # sending again what was sent changes nothing
    if not keys:
        raise PipelineError("Choisis au moins une vidéo à envoyer.")
    meta = p["meta"] or {}
    for key in keys:
        v = p["videos"].get(key)
        if not v or v.get("a_refaire"):
            raise PipelineError(f"La vidéo {key} n'est pas prête (refais le rendu après une correction).")
        if v.get("video_id"):
            continue
        pub = plan.publication(p["plan"], v["style"], v["langue"])
        credit = {"fr": "Images :", "en": "Footage:", "ar": "المقاطع :", "es": "Imágenes:"}.get(v["langue"], "Footage:")
        desc = f"{pub['description']}\n\n{credit} {meta.get('chaine') or ''} — {p['url']}".strip()
        os.makedirs("processed_videos", exist_ok=True)
        dest = os.path.join("processed_videos", f"{v['channel']}_{pid}_{key}.mp4")
        shutil.copy(v["path"], dest)
        now = datetime.now().isoformat()
        vid = f"{v['channel']}_{pid}_{key}"
        rec = {"video_id": vid, "batch_id": pid, "channel": v["channel"], "url": f"roblox:{pid}:{key}",
               "status": "ready_for_upload", "priority": "normal", "source": "roblox", "roblox_project": pid,
               "original_title": pub["titre"], "video_path": dest, "added_at": now, "updated_at": now,
               "ai_data": {"optimized_title": pub["titre"], "title": pub["titre"], "description": desc,
                           "description_suggestions": [desc], "tags": pub["tags"]},
               "recette": {"type": "roblox", "style": v["style"], "langue": v["langue"], "source": p["url"]}}
        thumb = _thumbnail(dest)
        if thumb:
            rec["thumbnail_path"] = thumb
        db.upsert_video(vid, rec)
        v["video_id"] = vid
    if all(v.get("video_id") for v in p["videos"].values()):
        p["status"] = "done"
    return save(p)


def delete(pid: str) -> None:
    load(pid)
    shutil.rmtree(project_dir(pid), ignore_errors=True)
    db.delete_roblox(pid)


RUNNERS = {"analysing": run_analysis, "rendering": run_render}
