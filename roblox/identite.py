"""
The channel's identity on the Roblox Shorts (labs etude_roblox/style, 2026-10-29/30): what the creator added on top of
the game is found, then hidden (roblox/nettoyage.py), and the Short gets our look —

    detect   Gemini watches a moment and lists the creator's elements (avatars, stickers, captions, logo, webcam,
             names), each with its box given by NAMED sides (a list was read y-first) and, for an avatar, the pose of
             our mascot closest to it, how it comes in and how it moves
    events   our mascot where the Short shows his avatars (on their side, about their size, for as long as they are
             there, never the same pose twice in a row), on the emotions of the lines and on the punchline
    overlay  the mascot popping in (overshoot, settle, its own small move, a "pop"), a white flash on the punchline
    texts    render.Ass(theme="identite"): Lilita One, white on a dark purple outline, the key words in orange

Assets: assets/roblox_mascotte/<pose>.png (the person's character, 16 poses, cut from a green background), the
mirrored ones made by ffmpeg (hflip).
"""

import os
import re
import subprocess
from typing import Dict, List, Optional

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASCOT = os.path.join(HERE, "assets", "roblox_mascotte")
POP = os.path.join(HERE, "assets", "sfx", "pop_pop.mp3")
POSES = ["rire", "montre", "choque", "colere", "pleure", "peur", "facepalm", "reflechit", "sarcastique", "victoire", "ko",
         "pouce", "fier", "machiavelique", "hausse_epaules", "gene"]
# the closest other pose: never the same one twice in a row (lab: "sarcastique" from 6 to 13 s)
ALT = {"sarcastique": "fier", "fier": "sarcastique", "rire": "montre", "montre": "rire", "choque": "peur", "peur": "choque",
       "colere": "machiavelique", "machiavelique": "sarcastique", "pleure": "gene", "gene": "facepalm", "facepalm": "gene",
       "reflechit": "hausse_epaules", "hausse_epaules": "reflechit", "victoire": "pouce", "pouce": "victoire", "ko": "choque"}
TAG_POSE = {"laughs": "rire", "laughing": "montre", "chuckles": "rire", "shouts": "colere", "frustrated": "colere",
            "surprised": "choque", "gasps": "choque", "sarcastic": "sarcastique", "sighs": "facepalm", "excited": "victoire"}
ORANGE, VIOLET = "&H001A7AFF", "&H003A0F2B"            # ASS colours (BGR): the headphones, the hoodie's line
FONT = "Lilita One"
SHOW, GAP, EMOTION_H, PUNCH_POSE = 1.6, 0.6, 470.0, "ko"
TYPES = ("avatar", "autocollant", "sous_titres_incrustes", "logo", "webcam", "pseudo", "texte_effet")

PROMPT = """Cette video est un moment d'une video YouTube Roblox (les secondes comptent depuis le debut de CE fichier).
On va en faire un Short pour une autre chaine et on doit CACHER tout ce que le CREATEUR a ajoute par-dessus le jeu
au montage, et tout ce qui montre un nom. Liste CHAQUE apparition de ces elements, meme courte ou partielle :
- "avatar" : un personnage dessine ou une image de personnage colle par-dessus le jeu
- "autocollant" : emoji, point d'interrogation, fleche, effet dessine, image collee
- "sous_titres_incrustes" : mots ou sous-titres ecrits par le createur
- "logo" : logo, nom de chaine, filigrane, abonne-toi
- "webcam" : la camera d'une vraie personne
- "pseudo" : un pseudo de joueur ecrit dans le jeu (au-dessus d'un personnage, dans un tableau, dans le chat)
- "texte_effet" : un mot d'effet ajoute au montage
NE PAS lister l'interface normale du jeu (boutons, inventaire, chrono, carte) ni les personnages du jeu eux-memes.
Pour chacune : "type", "description" courte en francais (avec le pseudo exact s'il y en a un), "debut" et "fin" en
secondes au dixieme (du premier au dernier instant ou on le voit), "cadre" = {{"gauche", "haut", "droite", "bas"}}
entre 0 et 1 (0 = bord gauche / haut, 1 = bord droit / bas) englobant TOUT l'element (tete, mains, accessoires) ;
s'il bouge beaucoup, fais une apparition par position. Pour un avatar : "pose" = la pose de notre mascotte qui lui
ressemble le plus parmi : {poses} ; "entree" = pop | glisse_gauche | glisse_droite | glisse_bas | fixe ;
"mouvement" = rebond | tremble | balance | fixe.
JSON uniquement : {{"elements": [{{"type": "...", "description": "...", "debut": s, "fin": s,
"cadre": {{"gauche": 0.0, "haut": 0.0, "droite": 0.0, "bas": 0.0}}, "pose": "...", "entree": "...", "mouvement": "..."}}]}}"""


class IdentiteError(RuntimeError):
    pass


def _run(cmd: List[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise IdentiteError(f"{os.path.basename(cmd[0])} : {r.stderr.strip()[-400:]}")


# ---------------------------------------------------------------- what the creator added

def parse(raw, a: float) -> List[Dict]:
    """Gemini's elements, times moved to seconds of the passage (the clip it saw starts at a)."""
    out = []
    for e in (raw or {}).get("elements") or [] if isinstance(raw, dict) else []:
        try:
            c = e["cadre"]
            box = [min(1.0, max(0.0, float(c[k]))) for k in ("gauche", "haut", "droite", "bas")]
            d, f = float(e["debut"]) + a, float(e["fin"]) + a
        except (KeyError, TypeError, ValueError):
            continue
        if box[2] > box[0] and box[3] > box[1] and f > d and e.get("type") in TYPES:
            out.append({"type": e["type"], "description": str(e.get("description") or ""), "debut": round(d, 2),
                        "fin": round(f, 2), "cadre": box, "pose": e.get("pose") if e.get("pose") in POSES else "sarcastique",
                        "entree": e.get("entree") or "pop", "mouvement": e.get("mouvement") or "fixe"})
    return out


def detect(src: str, a: float, b: float, gemini=None) -> List[Dict]:
    """The creator's elements seen between a and b (seconds of the passage file)."""
    prompt = PROMPT.format(poses=", ".join(POSES))
    if gemini is not None:
        return parse(gemini._generate_content([{"text": prompt}], max_tokens=8000, timeout=300, temperature=0.1), a)
    from adaptation import sources
    cut = os.path.splitext(src)[0] + f"_vu_{int(a)}_{int(b)}.mp4"
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{a}", "-t", f"{b - a}", "-i", src, "-vf", "scale=960:-2",
          "-c:v", "libx264", "-preset", "veryfast", "-an", cut])
    try:
        r = None
        with sources.gemini_file(cut) as (g, part):
            for _ in range(3):                         # Gemini sometimes leaves a trailing comma
                r = g._generate_content([{**part, "video_metadata": {"fps": 4}}, {"text": prompt}], max_tokens=8000,
                                        timeout=300, temperature=0.1)
                if isinstance(r, dict) and isinstance(r.get("elements"), list):
                    break
        return parse(r, a)
    finally:
        os.remove(cut)


# ---------------------------------------------------------------- the mascot in the Short

def _to_frame(box, x: Optional[float], keep: float):
    """A box of the 16:9 passage -> pixels of the Short's picture frame (render.py: the top `keep` of the picture,
    cropped 4:3 at x, in a 1080x810 frame at y = FG_Y)."""
    from roblox.render import FG_H, FG_Y
    src_h = 1080 * keep
    crop_w = min(1920, src_h * 4 / 3)
    xoff = (1920 - crop_w) * min(1.0, max(0.0, float(x if x is not None else 0.5)))
    k = FG_H / src_h
    x0, y0, x1, y1 = box
    return (x0 * 1920 - xoff) * k, y0 * 1080 * k + FG_Y, (x1 * 1920 - xoff) * k, min(y1 * 1080, src_h) * k + FG_Y


def _ratio(pose: str) -> float:
    from PIL import Image
    with Image.open(os.path.join(MASCOT, f"{pose}.png")) as im:
        return im.width / im.height


def events(segs: List[Dict], apps: Dict[str, List[Dict]], emotions: Dict[str, List], punchlines: List[float],
           keep: Optional[Dict[str, float]] = None) -> List[Dict]:
    """The mascot's appearances in the Short's seconds. segs: render.py's segments (fichier, a, b, x, gel);
    apps: the creator's elements per file; emotions: per file [(second of the passage, pose)]; punchlines: Short
    seconds. -> [{t0, t1, pose, cx, bas, h, w, entree, mouvement, droite, couvre}]"""
    from roblox.render import FG_H, FG_Y, W
    keep = keep or {}
    bottom = FG_Y + FG_H + 30
    starts, t = [], 0.0
    for s in segs:
        starts.append(t)
        t += s["b"] - s["a"] + s.get("gel", 0.0)
    total = t

    def mapped(fichier, d, f):
        for s, off in zip(segs, starts):
            if s["fichier"] == fichier and f > s["a"] and d < s["b"]:
                yield s, off + max(d, s["a"]) - s["a"], off + min(f, s["b"]) - s["a"]

    out: List[Dict] = []
    covers = []
    for fichier, els in apps.items():
        for e in sorted((e for e in els if e["type"] == "avatar"), key=lambda e: e["debut"]):
            for s, t0, t1 in mapped(fichier, e["debut"] - 0.15, e["fin"] + 0.15):
                x0, y0, x1, y1 = _to_frame(e["cadre"], s.get("x"), keep.get(fichier, 1.0))
                x0, x1, y0 = max(0.0, x0), min(float(W), x1), max(float(FG_Y), y0)
                if x1 - x0 < 20:
                    continue                                    # outside what the Short shows
                covers.append((t0, t1, e, x0, x1, y0))
    last = None
    for t0, t1, e, x0, x1, y0 in sorted(covers, key=lambda c: c[0]):
        pose = ALT.get(e["pose"], e["pose"]) if last and last["couvre"] and last["pose"] == e["pose"] else e["pose"]
        ratio = _ratio(pose)
        h = min(620.0, max(420.0, bottom - y0, (x1 - x0) * 0.95 / ratio))     # about the avatar's size, never the game
        w = h * ratio
        cx = min(max((x0 + x1) / 2, w / 2), W - w / 2)                       # always whole on screen
        if x0 < 8:
            cx = w / 2                                                       # the avatar at an edge: so is the mascot
        elif x1 > W - 8:
            cx = W - w / 2
        last = {"t0": round(t0, 3), "t1": round(t1, 3), "pose": pose, "cx": cx, "bas": bottom, "h": h, "w": w,
                "entree": e.get("entree", "pop"), "mouvement": e.get("mouvement", "fixe"), "droite": cx > W / 2, "couvre": True}
        out.append(last)
    taken = [(e["t0"], e["t1"]) for e in out]
    free = lambda t, d=SHOW: not any(a - GAP < t < b + GAP for a, b in taken) and t + 0.3 < total
    feelings = sorted((t0, pose) for fichier, lst in emotions.items() for td, pose in lst
                      for _, t0, _ in mapped(fichier, td, td + 0.01))
    side, last_pose = True, None
    for t, pose in feelings:
        if pose == last_pose or not free(t):
            continue
        out.append(_free_event(t, min(t + SHOW, total), pose, side, EMOTION_H))
        taken.append((t, t + SHOW))
        side, last_pose = not side, pose
    for t in punchlines:
        if 0 <= t < total and not any(a - 0.3 < t < b for a, b in taken):
            out.append({**_free_event(t, min(t + SHOW, total), PUNCH_POSE, False, 520.0), "cx": W / 2, "mouvement": "tremble"})
            taken.append((t, t + SHOW))
    return sorted(out, key=lambda e: e["t0"])


def _free_event(t0, t1, pose, right, h):
    from roblox.render import FG_H, FG_Y, W
    w = h * _ratio(pose)
    return {"t0": round(t0, 3), "t1": round(t1, 3), "pose": pose, "cx": W - w / 2 - 10 if right else w / 2 + 10,
            "bas": FG_Y + FG_H + 30, "h": h, "w": w, "entree": "pop", "mouvement": "rebond", "droite": right, "couvre": False}


def emotions_of(lines: List[Dict]) -> List:
    """[(second of the passage, pose)] from the emotion tags of the lines read ([laughs] -> rire…)."""
    out = []
    for l in lines:
        pose = next((TAG_POSE[t] for t in re.findall(r"\[(\w+)\]", l.get("texte") or "") if t in TAG_POSE), None)
        if pose:
            out.append((l["a"], pose))
    return out


def overlay(base: str, evs: List[Dict], flashes: List[float], out: str) -> str:
    """The mascot's appearances and the punchline flashes on a rendered Short, its sound kept, a pop on each."""
    inputs, g, mix, v = ["-i", base], [], [], "0:v"
    if flashes:
        g.append(f"[{v}]eq=brightness=0.45:enable='" + "+".join(f"between(t,{t:.2f},{t + 0.07:.2f})" for t in flashes) + "'[fl]")
        v = "fl"
    for k, e in enumerate(evs):
        png = os.path.join(MASCOT, f"{e['pose']}.png")
        h = int(e["h"]) // 2 * 2
        w = int(e.get("w") or e["h"] * _ratio(e["pose"])) // 2 * 2
        d, t0 = e["t1"] - e["t0"], e["t0"]
        inputs += ["-loop", "1", "-t", f"{d:.2f}", "-itsoffset", f"{t0:.2f}", "-i", png]
        T = f"(t-{t0:.2f})"
        sc = (f"if(lt(T,0.12),1.15*T/0.12,if(lt(T,0.22),1.15-0.15*(T-0.12)/0.10,if(gt(T,{d - 0.12:.2f}),"
              f"max(0.02,({d:.2f}-T)/0.12),1)))").replace("T", T) if e["entree"] == "pop" else "1"
        flip = ",hflip" if e["droite"] else ""                          # turned towards the middle
        g.append(f"[{k + 1}:v]format=rgba{flip},scale=w='max(2,{w}*{sc})':h=-1:eval=frame[p{k}]")
        x = f"{e['cx'] - w / 2:.0f}+({w}-overlay_w)/2"
        y = f"{e['bas'] - h:.0f}+({h}-overlay_h)"
        slide = {"glisse_gauche": f"-{w}*max(0,1-{T}/0.2)", "glisse_droite": f"+{w}*max(0,1-{T}/0.2)"}.get(e["entree"], "")
        rise = f"+{h}*max(0,1-{T}/0.2)" if e["entree"] == "glisse_bas" else ""
        move = {"rebond": f"-14*abs(sin({T}*6))", "tremble": f"+6*sin({T}*60)", "balance": f"+10*sin({T}*3)"}.get(e["mouvement"], "")
        xs = x + slide + (move if e["mouvement"] in ("tremble", "balance") else "")
        ys = y + rise + (move if e["mouvement"] == "rebond" else "")
        g.append(f"[{v}][p{k}]overlay=x='{xs}':y='{ys}':eof_action=pass:enable='between(t,{t0:.2f},{e['t1']:.2f})'[o{k}]")
        v = f"o{k}"
    g.append(f"[{v}]format=yuv420p[vout]")
    n = len(evs) + 1
    for k, e in enumerate(evs):
        inputs += ["-i", POP]
        ms = int(e["t0"] * 1000)
        g.append(f"[{n + k}:a]volume=0.5,adelay={ms}|{ms}[s{k}]")
        mix.append(f"[s{k}]")
    g.append("[0:a]" + "".join(mix) + f"amix=inputs={len(mix) + 1}:normalize=0:duration=first,alimiter=limit=0.95[aout]")
    tmp = out + ".part.mp4"
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(g), "-map", "[vout]", "-map", "[aout]",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", tmp])
    os.replace(tmp, out)
    return out
