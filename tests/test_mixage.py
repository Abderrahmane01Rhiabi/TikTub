"""The shared sound engine (adaptation/mixage.py), on real sounds made here: a speech-like voice (bursts), a music."""
import subprocess

import numpy as np
import pytest

from adaptation import mixage as X

SR = X.RATE


def _write(x, path):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", str(path)],
                   input=np.asarray(x, np.float32).tobytes(), check=True)
    return str(path)


def _voice(path, seconds=8.0):
    """1 s talking, 1 s silent, … (noise shaped like speech)."""
    from scipy.signal import butter, lfilter
    rng = np.random.default_rng(1)
    n = int(SR * seconds)
    x = lfilter(*butter(4, [300, 3400], "band", fs=SR), rng.standard_normal(n)) * 0.25
    on = (np.arange(n) // SR) % 2 == 0
    return _write(np.stack([x * on, x * on], 1), path)


def _music(path, seconds=8.0, amp=0.1):
    rng = np.random.default_rng(2)
    t = np.arange(int(SR * seconds)) / SR
    x = amp * (0.6 * np.sin(2 * np.pi * 110 * t) + 0.5 * np.sin(2 * np.pi * 2900 * t)) + amp * 0.2 * rng.standard_normal(len(t))
    return _write(np.stack([x, x], 1), path)


def _band(path, lo=1200, hi=5500):
    """The 1.2-5.5 kHz energy per second (dB)."""
    x = X._read(path)[:, 0]
    out = []
    for i in range(0, len(x) - SR + 1, SR):
        spec = np.abs(np.fft.rfft(x[i:i + SR])) ** 2
        f = np.fft.rfftfreq(SR, 1 / SR)
        out.append(10 * np.log10(spec[(f >= lo) & (f < hi)].sum() + 1e-12))
    return out


def test_the_music_gives_way_to_the_voice_only_while_he_speaks(tmp_path):
    voice, music = _voice(tmp_path / "v.wav"), _music(tmp_path / "m.wav")
    band = _band(X.carved(voice, music, str(tmp_path / "c.wav")))
    talking, silent = np.mean(band[0::2][1:]), np.mean(band[1::2][1:])
    assert silent - talking > 3                                  # the voice's band pressed down under him, not elsewhere


def test_the_track_is_mastered(tmp_path):
    voice, music = _voice(tmp_path / "v.wav"), _music(tmp_path / "m.wav", amp=0.3)
    out = X.track(voice, music, str(tmp_path / "t.wav"))
    m = X.measure(out)
    assert abs(m["lufs"] - X.TARGET_LUFS) < 1.0 and m["peak"] <= X.TRUE_PEAK + 0.3
    dense = X.measure(X.track(voice, music, str(tmp_path / "p.wav"), punch=True))
    assert abs(dense["lufs"] - X.TARGET_LUFS) < 1.0


def test_the_music_ends_on_a_hall_not_a_hole(tmp_path):
    out = X.bed(_music(tmp_path / "m.wav", seconds=12), str(tmp_path / "b.wav"), 10.0, gap=7.0)
    x = X._read(out)[:, 0]
    tail = [10 * np.log10(np.mean(x[i:i + SR // 2] ** 2) + 1e-12) for i in range(int(7.6 * SR), int(9.6 * SR), SR // 2)]
    assert max(tail) > -60 and tail[-1] < tail[0]                # a tail after the cut, dying away
    assert abs(len(x) / SR - 10.0) < 0.05


def test_a_short_song_is_not_looped(tmp_path):
    song = _music(tmp_path / "m.wav", seconds=6)
    out = X.bed(song, str(tmp_path / "b.wav"), 5.0, start=4.0, gap=7.0, end=False)   # 4 s + 5 s > 6 s: taken earlier
    x = X._read(out)[:, 0]
    per = [10 * np.log10(np.mean(x[i:i + SR // 4] ** 2) + 1e-12) for i in range(SR // 2, int(4 * SR), SR // 4)]
    assert min(per) > -50                                        # no hole where it would have started again


def test_the_instrumental_only_when_it_holds_up(tmp_path, monkeypatch):
    song = _music(tmp_path / "song.wav", amp=0.2)
    full = _music(tmp_path / "full.wav", amp=0.12)                # ~4 dB under the song: kept
    empty = _music(tmp_path / "empty.wav", amp=0.01)              # ~26 dB under: refused
    monkeypatch.setattr(X, "instrumental", lambda s: full)
    assert X.music_source(song, 0, 6) == full
    monkeypatch.setattr(X, "instrumental", lambda s: empty)
    assert X.music_source(song, 0, 6) == song
    monkeypatch.setattr(X, "instrumental", lambda s: (_ for _ in ()).throw(RuntimeError("pas de carte")))
    assert X.music_source(song, 0, 6) == song                    # Demucs unavailable: the song


def test_a_video_is_mastered_in_place(tmp_path):
    v = str(tmp_path / "v.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25:duration=4",
                    "-f", "lavfi", "-i", "sine=f=440:d=4", "-af", "volume=-25dB", "-c:v", "libx264", "-preset", "ultrafast",
                    "-shortest", v], check=True)
    X.master_file(v)
    assert abs(X.measure(v)["lufs"] - X.TARGET_LUFS) < 1.0
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", v],
                           capture_output=True, text=True).stdout.split()
    assert probe.count("video") == 1 and probe.count("audio") == 1


def test_a_song_with_a_silent_start_is_heard_from_the_first_second(tmp_path):
    x = X._read(_music(tmp_path / "m.wav", seconds=14))
    x[: int(3.5 * SR)] = 0.0                                     # a « Lyrics » video: 3.5 s of silence first
    song = X._write(x, str(tmp_path / "lyrics.wav"))
    assert abs(X.audible(song)[0] - 3.5) < 0.1
    out = X.bed(song, str(tmp_path / "b.wav"), 8.0, start=1.0, gap=7.0, lift_at=4.0)
    y = X._read(out)[:, 0]
    assert 10 * np.log10(np.mean(y[int(0.5 * SR):SR] ** 2) + 1e-12) > -50   # music at 0.5 s, not 3 s of nothing
    import json
    place = json.load(open(out + ".json"))
    assert place["debut_chanson"] >= 3.4 and abs(place["montee"] - 1.5) < 0.15  # its rise 2.5 s earlier
    assert place["niveau"] and place["coupe"] and place["entree"] == 0.0
