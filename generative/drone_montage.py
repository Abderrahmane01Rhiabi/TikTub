"""
Génération's "Drones, un plan par phrase" décor: instead of one background
looped for the whole video, a different drone / nature shot for every
sentence, cut on the music's beat with a short dissolve, each shot slowly
moving (pan or zoom), and one colour look for the whole video. Validated on
a test of "3 signes contre-intuitifs" (2026-10-24): 11 shots in 35 s.

Why: lungtemotivates put the same background under 18 of its 32 videos and
YouTube stopped showing the channel; with a shot per sentence no two videos
look alike.

    shots   a cut at each sentence start, shots 1.8-5 s (a long sentence is
            split), snapped to a beat within 0.3 s
    clips   the shared Pixabay library (montage/broll.py), skipping the
            channel's last RECENT shots; reserved as soon as chosen, so two
            videos rendered together never share one; when too few fresh
            shots are left, more are downloaded from Pixabay first
    look    one of LOOKS, at random per video

The result is a plain 1080x1920 mp4 handed to the usual composer (voice,
ducked music, the chosen caption style) like any other background.
"""

import os
import random
import subprocess
from typing import Dict, List, Optional, Tuple

DRONES = "drones"                 # bg_video_path of a video using this décor
RECENT = 30                       # the channel's last shots kept out (~3 videos)
SHOT_MIN, SHOT_MAX = 1.8, 5.0
BEAT_SNAP = 0.3
FADE = 0.4
W, H = 1080, 1920
LOOKS = {
    "doré": "colorbalance=rs=.06:gs=.02:bs=-.06:rm=.04:bm=-.04,eq=saturation=1.08:contrast=1.04",
    "froid": "colorbalance=rs=-.05:bs=.07:bm=.04,eq=saturation=.95:contrast=1.05",
    "bleu-vert": "colorbalance=rs=-.06:bs=.06:rh=.08:bh=-.06,eq=saturation=1.1:contrast=1.06",
    "pastel": "eq=saturation=.82:contrast=.94:brightness=.03:gamma=1.05",
}
MOVES = ["pan_r", "pan_l", "zoom_in", "zoom_out"]
# calm, wide themes for the library's top-up (Pixabay search terms)
THEMES = ["aerial forest river", "drone mountain cliff", "aerial snowy forest", "drone coastline waves",
          "aerial winding road hills", "drone lake", "aerial waterfall", "drone canyon", "aerial sunrise clouds",
          "drone ocean sunset", "aerial lavender field", "drone autumn forest", "aerial beach turquoise",
          "drone misty mountains", "aerial flower field", "drone countryside village"]


def shot_bounds(starts: List[float], total: float, beats: List[float]) -> List[Tuple[float, float]]:
    """(start, end) of each shot: a cut at each sentence start at least
    SHOT_MIN after the previous cut, long ones split, cuts moved onto a beat
    when one is within BEAT_SNAP."""
    cuts = [0.0]
    for t in starts[1:]:
        if t - cuts[-1] >= SHOT_MIN and total - t >= SHOT_MIN:
            cuts.append(t)
    k = 0
    while k < len(cuts):
        end = cuts[k + 1] if k + 1 < len(cuts) else total
        if end - cuts[k] > SHOT_MAX:
            cuts.insert(k + 1, cuts[k] + (end - cuts[k]) / 2)
        else:
            k += 1
    snapped = [0.0]
    for t in cuts[1:]:
        b = min(beats, key=lambda x: abs(x - t)) if beats else t
        t = b if abs(b - t) < BEAT_SNAP and b - snapped[-1] >= SHOT_MIN * 0.8 else t
        snapped.append(t)
    return list(zip(snapped, snapped[1:] + [total]))


def choose_clips(channel: str, n: int, video_id: str, rng: random.Random, fetch_more: bool = True) -> List[Dict]:
    """n different library shots this channel hasn't used lately, reserved
    for video_id at once. Tops the library up from Pixabay when short."""
    from montage import broll
    import db

    def fresh():
        recent = set(db.recent_broll_clips(channel, RECENT))
        return [c for c in broll.list_clips() if str(c["id"]) not in recent]

    clips = fresh()
    themes = THEMES[:]
    rng.shuffle(themes)
    while fetch_more and len(clips) < n and themes:
        try:
            broll.fetch(themes.pop(), count=4)
        except Exception as e:                  # no key, no network: use what there is
            print(f"⚠️ Pixabay: {e}")
            break
        clips = fresh()
    rng.shuffle(clips)
    chosen = clips[:n]
    if len(chosen) < n:                         # library still short: the shots used longest ago
        last = db.broll_last_used(channel)
        rest = sorted((c for c in broll.list_clips() if c not in chosen), key=lambda c: last.get(str(c["id"]), ""))
        chosen += rest[: n - len(chosen)]
    broll.record_usage(channel, [c["id"] for c in chosen], video_id)
    return chosen


def build(words: List[Tuple[str, float, float]], music: Optional[str], channel: str, video_id: str,
          out_path: str, seed=None, ffmpeg: str = "ffmpeg") -> Dict:
    """Renders the background for one video and returns what it's made of:
    {"look", "plans": [{"debut", "fin", "clip", "theme", "mouvement"}]}."""
    from montage import broll
    from generative.caption_styles import group_into_blocks
    from adaptation.render import beats_of

    rng = random.Random(seed if seed is not None else video_id)
    total = words[-1][2] + 0.4
    beats = beats_of(music, 0.0, total) if music else []
    bounds = shot_bounds([b[0][1] for b in group_into_blocks(words)], total, beats)
    clips = choose_clips(channel, len(bounds), video_id, rng)
    # the longest shots get the longest clips (a 5 s clip under a 4.6 s shot ran out and
    # cut the whole chain at 6 s: the composer then looped two shots for 40 s)
    order = sorted(range(len(bounds)), key=lambda k: bounds[k][1] - bounds[k][0], reverse=True)
    by_length = sorted(clips, key=lambda c: c.get("duration") or 0, reverse=True)
    clips = [None] * len(bounds)
    for k, c in zip(order, by_length):
        clips[k] = c
    look = rng.choice(list(LOOKS))
    work = os.path.join(os.path.dirname(out_path), "drone_shots")
    os.makedirs(work, exist_ok=True)

    parts, plans = [], []
    for i, ((a, b), c) in enumerate(zip(bounds, clips)):
        dur = b - a + FADE + 0.1
        avail = max(0.5, (c.get("duration") or 10) - 1.2)
        stretch = min(2.0, dur / avail) if avail < dur else 1.0     # too short: gently slowed down
        off = rng.uniform(1.0, max(1.0, (c.get("duration") or 10) - dur - 1.0)) if stretch == 1.0 else 0.6
        mv = "zoom_in" if i == 0 else MOVES[(i + rng.randrange(4)) % len(MOVES)]
        if mv.startswith("pan"):
            x = f"(iw-{W})*{'t' if mv == 'pan_r' else f'({dur:.2f}-t)'}/{dur:.2f}"
            vf = f"scale=-2:{H},crop={W}:{H}:'{x}':0"
        else:
            z = f"(1+0.10*t/{dur:.2f})" if mv == "zoom_in" else f"(1.10-0.10*t/{dur:.2f})"
            vf = f"scale=w='trunc({H * 16 / 9:.0f}*{z}/2)*2':h='trunc({H}*{z}/2)*2':eval=frame,crop={W}:{H}"
        vf += f",fps=25,{LOOKS[look]},vignette=PI/5,setsar=1,format=yuv420p"
        if stretch > 1.0:
            vf = f"setpts={stretch:.3f}*PTS," + vf
        p = os.path.join(work, f"shot{i}.mp4")
        # looped as a last resort, so a shot always lasts its full length
        subprocess.run([ffmpeg, "-v", "error", "-y", "-stream_loop", "-1", "-ss", f"{off:.2f}", "-i", broll.clip_path(c),
                        "-an", "-vf", vf, "-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", p],
                       check=True)
        parts.append(p)
        plans.append({"debut": round(a, 2), "fin": round(b, 2), "clip": c["id"], "theme": c.get("query"), "mouvement": mv})

    inputs, chain, prev = [], [], "[0:v]"
    for p in parts:
        inputs += ["-i", p]
    for i in range(1, len(parts)):
        chain.append(f"{prev}[{i}:v]xfade=transition=fade:duration={FADE}:offset={bounds[i][0] - FADE / 2:.3f}[x{i}]")
        prev = f"[x{i}]"
    graph = ";".join(chain) if chain else "[0:v]null[x0]"
    subprocess.run([ffmpeg, "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", prev if chain else "[x0]",
                    "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", out_path], check=True)
    for p in parts:
        os.remove(p)
    length = _duration(out_path, ffmpeg)
    if length < total - 0.2:                    # never hand a short background to the composer (it would loop it)
        raise RuntimeError(f"fond drones trop court : {length:.1f} s pour {total:.1f} s de voix")
    return {"look": look, "plans": plans}


def _duration(path: str, ffmpeg: str = "ffmpeg") -> float:
    probe = ffmpeg.replace("ffmpeg", "ffprobe") if ffmpeg.endswith("ffmpeg") else "ffprobe"
    out = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0
