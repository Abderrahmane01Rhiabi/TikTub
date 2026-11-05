"""The sound of a Short, shared by Discours, Reprise and Adaptation.

Studied 2026-11-05 on 3 motivation Shorts that work (their voice and music split by Demucs, measured) and 2 sound
tutorials: in this niche the music sits 3-8 dB under the voice, steady, without ducking; what made ours weak was a
music faded out by its own quiet start (its level set on the whole song's average). So:
  - instrumental(): the song without its singing (Demucs): a singer under a speech fights the voice in its own band;
  - level()   : the song kept audible all along (short-term levelling), before it is set under the voice;
  - the bed   : under the voice by `gap` dB, its rise on the punchline (or the music entering there, « entrée »);
  - ending()  : the music cut on a strong beat near the end, a hall reverb carrying it out (no flat fade);
  - track()   : the voice cleaned (80 Hz - 14 kHz) and set by measure (no compression), room carved in the music
                around 2.9 kHz only while he speaks (the voice drives it), « punch » if asked, and a master measured
                in two passes (-14 LUFS integrated, -1 dBTP).
Everything is FFmpeg on this PC: no AI."""
import os
import re
import subprocess
from typing import Dict, List, Optional

import numpy as np

RATE = 48000
VOICE_LUFS = -16.0                  # the voice before the master (the music is set under it)
TARGET_LUFS = -14.0                 # the Short's integrated loudness (YouTube's reference)
TRUE_PEAK = -1.5                    # dBTP before the AAC encoding (it overshoots a little): -1 dBTP in the Short
CARVE = (1200, 5500)                # the voice's band in the music (the tutorial: centre 2.9 kHz, ~5.6 kHz wide)
CARVE_RATIO = 3.0                   # how much that band gives way while he speaks (~6-8 dB at a normal voice)
REVERB_S = 2.4                      # the hall's tail at the end
IR = os.path.join("assets", "sfx", "salle.wav")


class MixageError(RuntimeError):
    pass


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode:
        raise MixageError(r.stderr.decode(errors="replace")[-600:])
    return r


def measure(path: str) -> Dict[str, float]:
    """{"lufs", "peak" (dBTP), "lra"} of a file (EBU R128)."""
    err = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    tail = err[err.rfind("Summary:"):]

    def get(key):
        m = re.search(key + r":\s+(-?[\d.]+|-inf)", tail)
        return float(m.group(1)) if m and m.group(1) != "-inf" else -70.0
    return {"lufs": get("I"), "peak": get("Peak"), "lra": get("LRA")}


def level(src: str, out: str) -> str:
    """The music's quiet passages brought up (a window of ~4 s, at most +18 dB), its loud ones kept: heard all along."""
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", src, "-af", "dynaudnorm=f=250:g=17:m=8:p=0.9:s=12", out])
    return out


def _ir(path: str = IR) -> str:
    """A hall's impulse (noise falling over REVERB_S s, darker as it goes), made once."""
    if os.path.exists(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    n = int(RATE * REVERB_S)
    t = np.arange(n) / RATE
    rng = np.random.default_rng(7)
    ir = rng.standard_normal((n, 2)) * np.exp(-t / (REVERB_S / 6.9))[:, None]      # -60 dB at REVERB_S
    k = np.ones(24) / 24                                                           # a little darker
    ir = np.stack([np.convolve(ir[:, c], k, "same") for c in range(2)], 1)
    ir[: int(RATE * 0.012)] *= np.linspace(0, 1, int(RATE * 0.012))[:, None]
    ir /= np.abs(ir).max()
    raw = (ir * 32767 * 0.5).astype("<i2").tobytes()
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "s16le", "-ar", str(RATE), "-ac", "2", "-i", "-",
                    path], input=raw, check=True)
    return path


def strong_beat(path: str, lo: float, hi: float) -> Optional[float]:
    """The strongest attack of the music between lo and hi s (where to cut it), or None."""
    raw = _run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{max(0.0, lo):.2f}", "-t", f"{max(0.1, hi - lo):.2f}",
                "-i", path, "-ac", "1", "-ar", "8000", "-f", "f32le", "-"]).stdout
    x = np.frombuffer(raw, np.float32)
    hop = 160                                                                       # 20 ms
    if len(x) < hop * 10:
        return None
    env = np.array([np.sqrt(np.mean(x[i:i + hop] ** 2) + 1e-12) for i in range(0, len(x) - hop, hop)])
    rise = np.diff(20 * np.log10(env + 1e-9))
    i = int(np.argmax(rise))
    return lo + (i + 1) * 0.02 if rise[i] > 3.0 else None


def _read(path: str) -> np.ndarray:
    raw = _run(["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-ac", "2", "-ar", str(RATE), "-f", "f32le", "-"]).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()


def _write(x: np.ndarray, path: str) -> str:
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "f32le", "-ar", str(RATE), "-ac", "2", "-i", "-",
                    path], input=x.astype(np.float32).tobytes(), check=True)
    return path


def ending(bed: str, out: str, total: float) -> str:
    """The music cut on a strong beat 1.6-3.2 s before the end (else 2.2 s before), its hall tail carrying it out:
    the last second before the cut convolved with the hall (numpy: FFmpeg's afir gave a silent tail here)."""
    from scipy.signal import fftconvolve
    cut = strong_beat(bed, total - 3.2, total - 1.6) or total - 2.2
    x = _read(bed)
    n, c = len(x), int(cut * RATE)
    if c <= RATE or c >= n:
        _write(x, out)
        return out
    ir = _read(_ir())
    src = x[c - RATE:c]
    wet = np.stack([fftconvolve(src[:, k], ir[:, k])[:n - (c - RATE)] for k in range(2)], 1)
    at = wet[RATE - int(0.25 * RATE):RATE + int(0.5 * RATE)]                      # the hall round the cut
    wet *= 0.5 * np.sqrt((src ** 2).mean() / max((at ** 2).mean(), 1e-12))          # 6 dB under the music
    rise = np.clip((np.arange(len(wet)) - (RATE - int(0.25 * RATE))) / (0.25 * RATE), 0, 1)[:, None]
    y = x.copy()
    y[c:] = 0.0
    y[c - int(0.03 * RATE):c] *= np.linspace(1, 0, int(0.03 * RATE))[:, None]
    y[c - RATE:c - RATE + len(wet)] += wet * rise
    tail = int(0.6 * RATE)
    y[-tail:] *= np.linspace(1, 0, tail)[:, None]
    return _write(y, out)


INSTRUMENTALS = os.path.join("assets", "musiques", ".instrumental")


INSTRUMENTAL_MEAN_DB = 6.0          # the instrumental kept when it is at most this much under the song on the part used
INSTRUMENTAL_QUIET_DB = 10.0        # … and in its quiet moments (Past Lives: 19 dB there, nearly empty: refused)


def _rms(path: str, start: float, length: float) -> tuple:
    raw = _run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{max(0.0, start):.2f}", "-t", f"{max(0.5, length):.2f}", "-i",
                path, "-ac", "1", "-ar", "8000", "-f", "f32le", "-"]).stdout
    x = np.frombuffer(raw, np.float32)
    hop = 800
    e = np.array([np.mean(x[i:i + hop] ** 2) for i in range(0, max(0, len(x) - hop), hop)]) if len(x) > hop else np.zeros(1)
    return 10 * np.log10(np.mean(e) + 1e-12), 10 * np.log10(np.percentile(e, 25) + 1e-12)


def music_source(song: str, start: float, length: float) -> str:
    """The song's instrumental when it holds up on its own on the part used (the blind test: 4/5 on a full instrumental,
    1/5 on a nearly empty one raised), else the song itself (its singing then given way by the carve)."""
    try:
        inst = instrumental(song)
        s_mean, s_quiet = _rms(song, start, length)
        i_mean, i_quiet = _rms(inst, start, length)
    except Exception as e:
        print(f"⚠️ Instrumental impossible ({e}) : la chanson entière")
        return song
    if s_mean - i_mean <= INSTRUMENTAL_MEAN_DB and s_quiet - i_quiet <= INSTRUMENTAL_QUIET_DB:
        return inst
    return song


def instrumental(song: str) -> str:
    """The song without its singing (Demucs, graphics card, about a minute, once per song): a singer under a speech
    sings in the voice's own band, which no level or EQ can fix; the reference Shorts have no singing under the voice."""
    out = os.path.join(INSTRUMENTALS, os.path.splitext(os.path.basename(song))[0] + ".wav")
    if os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(song):
        return out
    from roblox import voix
    import shutil
    import tempfile
    os.makedirs(INSTRUMENTALS, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        shutil.move(voix.separate(song, tmp)["reste"], out)
    return out


def bed(src: str, out: str, total: float, start: float = 0.0, pad: float = 0.0, gap: float = 7.0,
        lift_at: Optional[float] = None, levelled: bool = True, end: bool = True, lift: float = 1.33) -> str:
    """The music under the voice: from `start` s of the song after `pad` s of silence (« entrée »: pad = the moment it
    comes in), levelled, `gap` dB under VOICE_LUFS measured on what is heard, `lift` from `lift_at` (its rise), faded
    in, and ended on a strong beat with a hall tail (else faded out)."""
    work = out + ".parts"
    os.makedirs(work, exist_ok=True)
    long = float(_run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src]).stdout or 0)
    if long and start + total - pad > long - 0.5:                # the song would end and start again: taken earlier
        moved_by = min(start, start + total - pad - (long - 0.5))
        start -= moved_by
        lift_at = lift_at - moved_by if lift_at is not None else None
    raw = os.path.join(work, "brut.wav")
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-stream_loop", "-1", "-i", src, "-af",
          f"atrim=start={start:.2f},asetpts=PTS-STARTPTS,atrim=0:{max(0.5, total - pad):.2f}", "-ar", str(RATE), "-ac", "2",
          raw])
    music = level(raw, os.path.join(work, "nivele.wav")) if levelled else raw
    heard = measure(music)["lufs"]
    gain = 10 ** ((VOICE_LUFS - gap - heard) / 20) if heard > -60 else 1.0
    rise = f",volume='if(gte(t,{lift_at - pad:.2f}),{lift},1)':eval=frame" if lift_at is not None and lift_at > pad else ""
    fade_in = 0.12 if pad > 0 else 1.2                                             # « entrée »: it drops in
    placed = os.path.join(work, "place.wav")
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", music, "-af",
          f"volume={gain:.4f}{rise},afade=t=in:st=0:d={fade_in},adelay={int(pad * 1000)}:all=1,apad=whole_dur={total:.3f},"
          f"atrim=0:{total:.3f}" + ("" if end else f",afade=t=out:st={max(0.0, total - 2.0):.2f}:d=2"), placed])
    if end:
        ending(placed, out, total)
    else:
        os.replace(placed, out)
    for f in os.listdir(work):
        os.remove(os.path.join(work, f))
    os.rmdir(work)
    return out


def carve_filters(music: str, key: str, out: str, tag: str = "cv") -> List[str]:
    """FFmpeg filters giving way in the music `music` to the voice `key` (labels, without brackets): its voice band
    (CARVE) pressed down while he speaks, the rest of it untouched -> `out`."""
    lo, hi = CARVE
    return [f"[{music}]acrossover=split={lo} {hi}[{tag}_lo][{tag}_mid][{tag}_hi]",
            f"[{tag}_mid][{key}]sidechaincompress=threshold=0.05:ratio={CARVE_RATIO}:attack=15:release=250:makeup=1[{tag}_mc]",
            f"[{tag}_lo][{tag}_mc][{tag}_hi]amix=inputs=3:normalize=0[{out}]"]


def master_file(path: str, target: float = TARGET_LUFS) -> str:
    """A finished video (or sound file) mastered in place: its sound measured, brought to `target` LUFS linearly, true
    peak under TRUE_PEAK; the picture copied as it is."""
    gain = target - measure(path)["lufs"]
    limit = 10 ** (TRUE_PEAK / 20)
    tmp = path + ".master" + os.path.splitext(path)[1]
    video = path.lower().endswith((".mp4", ".mov", ".mkv"))
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", path, "-af",
          f"volume={gain:.2f}dB,alimiter=limit={limit:.3f}:attack=2:release=60:level=disabled",
          *(["-map", "0:v?", "-map", "0:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]
            if video else []), tmp])
    os.replace(tmp, path)
    return path


def _voice_chain(voice: str) -> str:
    return f"aresample={RATE},highpass=f=80,lowpass=f=14000,volume={VOICE_LUFS - measure(voice)['lufs']:.2f}dB"


def clean_voice(voice: str, out: str) -> str:
    """The voice as track() sets it (cleaned, at VOICE_LUFS): « Écouter » plays it."""
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", voice, "-af", _voice_chain(voice), "-ac", "2", out])
    return out


def carved(voice: str, music: str, out: str) -> str:
    """The music as track() lays it under this voice (its voice band giving way while he speaks), alone: « Écouter »
    plays it beside clean_voice() and lowers it live."""
    g = [f"[0:a]{_voice_chain(voice)}[key]", f"[1:a]aresample={RATE}[m_in]"] + carve_filters("m_in", "key", "mu")
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", voice, "-i", music, "-filter_complex", ";".join(g),
          "-map", "[mu]", "-ac", "2", out])
    return out


def track(voice: str, music: Optional[str], out: str, carve: bool = True, punch: bool = False, duck: bool = False,
          sounds: Optional[List[str]] = None, target: float = TARGET_LUFS) -> str:
    """The Short's sound: the voice cleaned and set to VOICE_LUFS by measure (linear: his nuances kept), the music under
    it with its voice band giving way while he speaks (`carve`), or all of it a little (`duck`), sound effects added,
    then « punch » (denser, like the loud motivation edits) if asked, and the master: measured, brought to `target`
    LUFS linearly, true peak under TRUE_PEAK."""
    pre = out + ".mix.wav"
    inputs = ["-i", voice] + (["-i", music] if music else [])
    for s in sounds or []:
        inputs += ["-i", s]
    g = [f"[0:a]{_voice_chain(voice)}" + (",asplit[vo][key]" if music else "[vo]")]
    mix = ["[vo]"]
    if music:
        if carve:
            g += [f"[1:a]aresample={RATE}[m_in]"] + carve_filters("m_in", "key", "mu")
        elif duck:
            g += [f"[1:a]aresample={RATE}[m_in]",
                  "[m_in][key]sidechaincompress=threshold=0.05:ratio=2:attack=120:release=600:makeup=1[mu]"]
        else:
            g += [f"[1:a]aresample={RATE}[mu]", "[key]anullsink"]
        mix.append("[mu]")
    for k in range(len(sounds or [])):
        g.append(f"[{k + (2 if music else 1)}:a]aresample={RATE}[sx{k}]")
        mix.append(f"[sx{k}]")
    tail = ",acompressor=threshold=0.125:ratio=3:attack=5:release=80:makeup=2" if punch else ""
    g.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=first{tail}" if len(mix) > 1 else f"[vo]anull{tail}")
    _run(["ffmpeg", "-nostdin", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(g), "-ar", str(RATE), "-ac", "2",
          pre])
    os.replace(pre, out)
    return master_file(out, target)
