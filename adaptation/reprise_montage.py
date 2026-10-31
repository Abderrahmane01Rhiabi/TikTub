"""
A Reprise's montage, once its video is clean (reprise.py): our script, our voice, our captions, the sound chosen.

    script       Gemini cuts the Short into parts (hook, points or steps, ending) and says if it is a TOP (points
                 that can move: reordered, the strongest first, renumbered, our numbers on screen) or a STORY (a
                 chain of events: never reordered, no numbers — #1..#6 on a rescue story made no sense), then writes
                 each part in every language of the channels, our own words, the same facts, sized to its images
    voice        ElevenLabs eleven_v4, one take, the words' timings kept with the mp3
    montage      each part made on its own at its sentence's exact length (its images a bit faster or slower,
                 0.8-1.35, then cut or its last image held: with the speed at its limit the voice ran ahead of the
                 images, more at each point), then put end to end (27 plans opened in one ffmpeg took 6.9 GB);
                 3 words of captions at a time where his were, the word said in yellow; the voice at -16 LUFS over
                 the music bed (musique.py)
    thumbnail    his thumbnail's texts erased, our title in the calmer band (top or bottom: not over the subject)
"""

import json
import os
import re
import subprocess
from typing import Dict, List, Optional

from adaptation import langs

W, H, FPS = 1080, 1920, 30
SPEED = (0.8, 1.35)
NAMES = {"fr": "francais", "ar": "arabe standard moderne (sans voyelles)", "en": "anglais"}
WPS = {"fr": (2.2, 2.6), "ar": (1.8, 2.2), "en": (2.4, 2.8)}   # words a second, to FILL a part's images: at most
# only, the French of the 8th Short said 47 s of images in 29 s (its images cut)


class MontageError(RuntimeError):
    pass


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode:
        raise MontageError(r.stderr.decode(errors="replace")[-800:] or f"ffmpeg s'est arrêté ({r.returncode})")
    return r


# ---------------------------------------------------------------- script

SCRIPT = """Voici un YouTube Short, plan par plan, avec ce qu'on voit et ce qui est dit :
{plans}
IMPORTANT : tout ce que le createur a ecrit sur l'image (sous-titres, numeros 1-2-3, autocollants) est EFFACE puis
refait par nous : les numeros incrustes n'empechent donc PAS de permuter des points.
On garde EXACTEMENT ces images mais on refait le texte pour nos chaines, en {langues}, avec nos propres mots (pas une
traduction mot a mot) et les memes faits (rien d'invente). Le francais est ecrit CORRECTEMENT, avec tous ses accents
(é, è, à, ç, ô... : "choqué", "Indonésien", "ému"), meme si cette consigne est ecrite sans accents.
1. Dis si c'est un "top" (une liste de points independants : des objets, des faits, des lieux) ou une "histoire" (une
   suite d'evenements ou chaque etape decoule de la precedente).
2. Decoupe en parties : une accroche, chaque point (ou etape) avec ses plans, une chute.
3. Un top : propose un NOUVEL ORDRE si c'est logique (le plus fort en premier) ; l'accroche reste au debut et la chute
   a la fin ; les points sont RENUMEROTES et la phrase de chaque point commence par son nouveau numero. Une histoire :
   garde l'ordre, PAS de numero (role "etape", numero null, pas de "1." dans le texte).
4. Pour chaque langue, la publication YouTube, comme nos autres Shorts : "youtube" = {{"titre" (100 caracteres max,
   avec 1-2 emojis, qui donne envie de regarder), "description" (2-3 phrases + 3 a 5 hashtags dont #shorts),
   "tags" (8 a 12)}} ; et "titre" = un titre COURT pour la miniature (6 mots au plus, sans emoji).
5. Ecris le texte de chaque partie : une accroche percutante, une phrase par point ou etape, et une chute qui invite a
   commenter. Chaque texte doit REMPLIR la duree de ses images sans la depasser ({vitesses}) : un texte trop court
   coupe ses images (on ne les accelere que jusqu'a x1,35), un texte trop long les ralentit.
JSON uniquement : {{"genre": "top" | "histoire", "reordonne": true/false, "pourquoi": "une phrase",
 "titre": {{{cles}}}, "youtube": {{{cles_youtube}}},
 "parties": [{{"role": "accroche|point|etape|chute", "numero": null ou n, "plans": [indices des plans d'origine],
              {cles}}}]}}"""


def check_script(r, n_plans: int, codes: List[str]) -> Optional[Dict]:
    """Gemini's script, or None when unusable: every part has its plans (known ones) and a text in every language;
    a story has no numbers left (on screen nor said)."""
    if not isinstance(r, dict) or not r.get("parties"):
        return None
    parts = []
    for p in r["parties"]:
        plans = [int(i) for i in p.get("plans") or [] if str(i).lstrip("-").isdigit() and 0 <= int(i) < n_plans]
        if not plans or any(not (p.get(c) or "").strip() for c in codes):
            return None
        parts.append({**p, "plans": plans})
    story = r.get("genre") != "top"
    if story:
        parts = [{**p, "numero": None, "role": "etape" if p.get("role") == "point" else p.get("role"),
                  **{c: re.sub(r"^\s*\d+\s*[.)\-:]\s*", "", p[c]) for c in codes}} for p in parts]
    titre = r.get("titre") if isinstance(r.get("titre"), dict) else {}
    titre = {c: (titre.get(c) or "").strip() for c in codes}
    yt = r.get("youtube") if isinstance(r.get("youtube"), dict) else {}
    return {**r, "genre": "histoire" if story else "top", "parties": parts, "titre": titre,
            "youtube": {c: youtube_of(yt.get(c), titre[c]) for c in codes}}


def youtube_of(y, short: str) -> Dict:
    """A language's YouTube title (100 characters at most), description and tags (15 at most) — the short
    thumbnail title when Gemini gave none (the first Reprises had only it: no tags, the title as description)."""
    y = y if isinstance(y, dict) else {}
    tags = [str(t).strip().lstrip("#") for t in y.get("tags") or [] if str(t).strip()]
    title = str(y.get("titre") or short).strip()[:100]
    return {"titre": title, "description": str(y.get("description") or title).strip(), "tags": tags[:15]}


def write_script(analyse: Dict, codes: List[str], gemini=None) -> Dict:
    from adaptation.sources import _gemini
    g = gemini or _gemini()
    plans = analyse.get("plans") or []
    lines = "\n".join(f"{i}. {p['debut']:.1f}-{p['fin']:.1f} s ({p['fin'] - p['debut']:.1f} s) [{p.get('role')}] on voit : "
                      f"{p.get('visuel')} | dit : {p.get('paroles')}" for i, p in enumerate(plans))
    prompt = SCRIPT.format(plans=lines, langues=", ".join(f"{NAMES.get(c, c)} (cle \"{c}\")" for c in codes),
                           vitesses="; ".join(f"{NAMES.get(c, c)} : entre {WPS.get(c, (2.0, 2.5))[0]} et "
                                              f"{WPS.get(c, (2.0, 2.5))[1]} mots par seconde" for c in codes),
                           cles=", ".join(f'"{c}": "..."' for c in codes),
                           cles_youtube=", ".join(f'"{c}": {{"titre": "", "description": "", "tags": [""]}}' for c in codes))
    for _ in range(3):
        r = check_script(g._generate_content([{"text": prompt}], max_tokens=8000, timeout=180, temperature=0.6),
                         len(plans), codes)
        if r:
            return r
    raise MontageError("Gemini n'a pas réussi à écrire le script de la Reprise.")


def fit_plans(plans: List[Dict], length: float) -> List[Dict]:
    """The model Short's plans with their times as seconds of the video (reprise.as_seconds), never past its end."""
    from adaptation.reprise import as_seconds
    flat = as_seconds([float(p[k]) for p in plans for k in ("debut", "fin")], length)
    if flat is None:
        raise MontageError("Les temps des plans donnés par Gemini ne correspondent pas à la vidéo.")
    return [{**p, "debut": min(flat[2 * i], length), "fin": min(flat[2 * i + 1], length)} for i, p in enumerate(plans)]


# ---------------------------------------------------------------- voice

MODEL = "eleven_v4"


def voice(script: Dict, code: str, voice_id: str, mp3: str, model: str = MODEL) -> Dict:
    """The parts said in one take -> the timings (words, each part's span), kept beside the mp3 (.json)."""
    from adaptation import voices
    v = voices.synthesize([{"texte": p[code]} for p in script["parties"]], voice_id, code, mp3, model=model)
    json.dump(v, open(mp3[:-4] + ".json", "w", encoding="utf-8"), ensure_ascii=False)
    return v


def starts_of(v: Dict) -> List[float]:
    return [x["start"] if k else 0.0 for k, x in enumerate(v["passages"])]


# ---------------------------------------------------------------- captions

def ass_time(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def glued(words: List[Dict]) -> List[Dict]:
    """A French " !" / " ?" said as a word of its own stuck to the one before (a caption began "! Numéro un,")."""
    out: List[Dict] = []
    for wd in words:
        if out and not re.search(r"\w", wd["w"]):
            out[-1] = {**out[-1], "w": out[-1]["w"] + wd["w"].strip(), "end": wd["end"]}
        else:
            out.append(wd)
    return out


CAPTION_Y = 0.755                                # our captions' middle, as a fraction of the height, by default


def caption_y(elements: List[Dict]) -> float:
    """Where our captions go: on the band his bottom captions were erased from (a blur showed under ours when his sat
    lower), else CAPTION_Y. Vertical fractions are kept by the 9:16 crop (scaled on the height, cut at the sides)."""
    low = [e["cadre"] for e in elements if e.get("type") == "sous_titres" and e.get("action", "cacher") == "cacher"
           and (e["cadre"][1] + e["cadre"][3]) / 2 > 0.5]
    if not low:
        return CAPTION_Y
    mids = sorted((c[1] + c[3]) / 2 for c in low)
    return round(min(0.86, max(0.6, mids[len(mids) // 2])), 3)


def captions(path: str, words: List[Dict], starts: List[float], numbers: List[Optional[int]], code: str,
             total: float, y: float = CAPTION_Y) -> str:
    """Our captions where the creator's were (~72 % down), 3 words at a time, the word said in yellow; our numbers
    big at the start of each point of a top."""
    L = langs.lang(code)
    font = L["caption_font"]
    enc = -1 if L["rtl"] else 1                      # right-to-left base (adaptation/render.captions_ass)
    # Bold 0: the font is already Black, libass's made-up bold lost the final alif
    head = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0", "", "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
            "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Mot,{font},92,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,0,0,0,0,100,100,0,0,1,8,3,2,60,60,"
            f"{int(H * (1 - y) - 50)},{enc}",                  # its bottom margin: the line's middle at y
            f"Style: Num,{font},300,&H0000E5FF,&H0000E5FF,&H00000000,&H90000000,0,0,0,0,100,100,0,0,1,12,4,8,40,40,330,{enc}",
            "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    words = glued(words)
    ev = []
    for i in range(0, len(words), 3):
        chunk = words[i:i + 3]
        for j, wd in enumerate(chunk):
            nxt = chunk[j + 1]["start"] if j + 1 < len(chunk) else (words[i + 3]["start"] if i + 3 < len(words) else wd["end"] + 0.4)
            # every word its own colour run: one run of several Arabic words came out unjoined, left to right
            text = " ".join(("{\\c&H0000E5FF&}" if c is wd else "{\\c&H00FFFFFF&}") + c["w"] for c in chunk)
            ev.append(f"Dialogue: 0,{ass_time(wd['start'])},{ass_time(min(nxt, total))},Mot,,0,0,0,,{text}")
    for t, n in zip(starts, numbers):
        if n:
            ev.append(f"Dialogue: 1,{ass_time(t)},{ass_time(t + 1.6)},Num,,0,0,0,,"
                      f"{{\\fad(80,200)\\fscx130\\fscy130\\t(0,160,\\fscx100\\fscy100)}}#{n}")
    open(path, "w", encoding="utf-8").write("\n".join(head + ev) + "\n")
    return path


# ---------------------------------------------------------------- montage

def part_lengths(v: Dict) -> List[float]:
    total = v["duration"] + 0.8
    st = starts_of(v)
    return [(st[k + 1] if k + 1 < len(st) else total) - st[k] for k in range(len(st))]


def render(clean: str, plans: List[Dict], script: Dict, code: str, v: Dict, mp3: str, bed: Optional[str],
           out: str, work: str, y: float = CAPTION_Y) -> str:
    """The Reprise video in one language: clean's images in the script's order at the voice's pace, our captions,
    the voice over the bed (None: no music) -> out."""
    from adaptation.musique import VOICE_LUFS, lufs
    os.makedirs(work, exist_ok=True)
    parts = script["parties"]
    total = v["duration"] + 0.8
    files = []
    for k, (part, d) in enumerate(zip(parts, part_lengths(v))):
        shots = [plans[i] for i in part["plans"] if 0 <= i < len(plans)]
        foot = sum(p["fin"] - p["debut"] for p in shots) or 1.0
        speed = min(SPEED[1], max(SPEED[0], foot / d))
        inputs, g = [], []
        for n, p in enumerate(shots):
            inputs += ["-ss", f"{p['debut']:.3f}", "-t", f"{p['fin'] - p['debut']:.3f}", "-i", clean]
            g.append(f"[{n}:v]setpts=(PTS-STARTPTS)/{speed:.4f},fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,"
                     f"crop={W}:{H},setsar=1[v{n}]")
        g.append("".join(f"[v{n}]" for n in range(len(shots))) + f"concat=n={len(shots)}:v=1:a=0,"
                 f"tpad=stop_mode=clone:stop_duration={d:.3f},trim=0:{d:.3f},setpts=PTS-STARTPTS[pv]")
        f = os.path.join(work, f"partie_{k:02d}.mp4")
        _run(["ffmpeg", "-nostdin", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(g), "-map", "[pv]",
              "-c:v", "h264_nvenc", "-cq", "18", f])
        got = float(_run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f]).stdout or 0)
        if got < d - 0.25:          # shots past the video's end gave a frozen, then missing, end (5th Short)
            raise MontageError(f"La partie {k + 1} fait {got:.1f} s au lieu de {d:.1f} s : ses plans sortent de la vidéo.")
        files.append(f)
    lst = os.path.join(work, "parties.txt")
    open(lst, "w").write("".join(f"file '{os.path.abspath(f)}'\n" for f in files))
    numbers = [p.get("numero") if script.get("genre") == "top" and p.get("role") == "point" else None for p in parts]
    ass = captions(os.path.join(work, f"textes_{code}.ass"), v["words"], starts_of(v), numbers, code, total, y)
    gain = 10 ** ((VOICE_LUFS - lufs(mp3)) / 20)
    inputs = ["-f", "concat", "-safe", "0", "-i", lst, "-i", mp3]
    g = [f"[0:v]tpad=stop_mode=clone:stop_duration=1,trim=0:{total:.3f},setpts=PTS-STARTPTS,"
         f"ass='{os.path.abspath(ass)}':fontsdir='{langs.FONTS_DIR}':shaping=complex,format=yuv420p[vout]"]
    if bed:
        inputs += ["-i", bed]
        g.append(f"[1:a]volume={gain:.4f}[vo];[vo][2:a]amix=inputs=2:normalize=0:duration=longest,"
                 f"atrim=0:{total:.3f},alimiter=limit=0.95[aout]")
    else:
        g.append(f"[1:a]volume={gain:.4f},apad,atrim=0:{total:.3f},alimiter=limit=0.95[aout]")
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(g), "-map", "[vout]",
          "-map", "[aout]", "-c:v", "h264_nvenc", "-cq", "20", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out])
    return out


# ---------------------------------------------------------------- thumbnail

def title_band(img) -> str:
    """"haut" or "bas": the band of the picture with less detail (the subject is where the detail is: the title
    over the piglet's head, 5th Short)."""
    import cv2
    import numpy as np
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = np.abs(cv2.Laplacian(gray, cv2.CV_32F))
    h = gray.shape[0]
    return "haut" if edges[:int(h * 0.35)].mean() <= edges[int(h * 0.65):].mean() else "bas"


def thumbnail(src_img: str, title: str, code: str, out: str, reader=None) -> str:
    """His thumbnail with its texts erased and our title (3 lines at most, big, yellow on a black outline)."""
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    img = cv2.cvtColor(np.array(Image.open(src_img).convert("RGB")), cv2.COLOR_RGB2BGR)
    if reader is None:
        from roblox import nettoyage as N
        reader = N.ocr()
    mask = np.zeros(img.shape[:2], np.uint8)
    for pts, _, conf in reader.readtext(img):
        if conf >= 0.2:
            cv2.fillPoly(mask, [np.array(pts).astype(np.int32)], 255)
    if mask.any():
        img = cv2.inpaint(img, cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))), 9, cv2.INPAINT_TELEA)
    band = title_band(img)
    im = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    L = langs.lang(code)
    size = int(im.width * 0.085)
    font = ImageFont.truetype(langs.font_path(L["banner_font"]), size)
    d = ImageDraw.Draw(im)
    lines: List[str] = []
    for wd in title.split():
        if lines and d.textlength(lines[-1] + " " + wd, font=font) < im.width * 0.9:
            lines[-1] += " " + wd
        else:
            lines.append(wd)
    lines = lines[:3]
    kw = {"direction": "rtl", "language": "ar"} if L["rtl"] else {}
    step = int(size * 1.2)
    y = int(im.height * 0.08) if band == "haut" else int(im.height * 0.92) - step * len(lines)
    for line in lines:
        try:
            tw = d.textlength(line, font=font, **kw)
        except Exception:                            # no raqm (complex layout) here: the plain layout
            kw = {}
            tw = d.textlength(line, font=font)
        d.text(((im.width - tw) / 2, y), line, font=font, fill=(255, 229, 0), stroke_width=max(4, size // 10),
               stroke_fill=(0, 0, 0), **kw)
        y += step
    im.save(out)
    return out
