"""detect_cuts on a long source without holding the whole video in memory
(AUDIT.md §8.3-9: a 20-minute source decoded at once took ~2 GB, twice)."""

import subprocess
import tracemalloc

from adaptation import sources


def three_shots(path, seconds=20):
    """A 1-minute video made of 3 very different shots: cuts at 20 s and 40 s."""
    parts = ["testsrc2=size=160x160:rate=25", "mandelbrot=size=160x160:rate=25", "smptebars=size=160x160:rate=25"]
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for p in parts:
        cmd += ["-f", "lavfi", "-t", str(seconds), "-i", p]
    cmd += ["-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1[v]", "-map", "[v]",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", path]
    subprocess.run(cmd, check=True)


def test_cuts_are_found_without_decoding_the_whole_video_at_once(tmp_path):
    video = str(tmp_path / "three.mp4")
    three_shots(video)

    tracemalloc.start()
    segs = sources.detect_cuts(video, {"duration": 60.0}, None)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()

    starts = [a for a, _ in segs]
    assert len(segs) == 3 and abs(starts[1] - 20) < 0.3 and abs(starts[2] - 40) < 0.3
    assert peak < 40 * 1024 * 1024, f"{peak / 1e6:.0f} MB held at once"
