"""One heavy render at a time in the whole app (WSL has ~7.8 GB): Adaptation
previews and final renders, Montage auto, Génération share one slot
(AUDIT.md §8.3-9)."""

import json
import threading
import time
from pathlib import Path


class Tracker:
    """Counts renders running at the same moment."""
    def __init__(self):
        self.now, self.max, self.lock = 0, 0, threading.Lock()

    def work(self, *a, **k):
        with self.lock:
            self.now += 1
            self.max = max(self.max, self.now)
        time.sleep(0.3)
        with self.lock:
            self.now -= 1
        return {}


def together(*calls):
    threads = [threading.Thread(target=c) for c in calls]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)


def test_an_adaptation_preview_waits_for_a_final_render(project, monkeypatch):
    from adaptation import render
    tracker = Tracker()
    monkeypatch.setattr(render, "_render", tracker.work)

    together(lambda: render.render(preview=False), lambda: render.render(preview=True),
             lambda: render.render(preview=True))

    assert tracker.max == 1


def test_montage_and_generation_wait_for_an_adaptation_render(project, monkeypatch):
    from adaptation import render
    from montage import pipeline as mp
    import generative.pipeline as gp_mod
    tracker = Tracker()
    monkeypatch.setattr(render, "_render", tracker.work)
    monkeypatch.setattr(mp, "_render", tracker.work)
    monkeypatch.setattr(gp_mod, "render_video", lambda *a, **k: (tracker.work(), Path(a[4]).write_bytes(b"mp4")))
    Path("temp/g1").mkdir(parents=True)
    Path("temp/g1/words.json").write_text(json.dumps([["Bonjour", 0.0, 1.0]]))
    project.add_video("g1", status="assembling", source="generated", words_path="temp/g1/words.json",
                      narration_path="temp/g1/narration.mp3", bg_video_path="bg.mp4", bg_music_path="m.mp3")
    gp = gp_mod.GenerativePipeline()

    together(lambda: render.render(preview=False),
             lambda: mp.render_preview({"video_id": "v1"}, {}, None),
             lambda: mp.render_final({"video_id": "v2"}, {}, None, "processed_videos/v2.mp4"),
             lambda: gp.assemble("g1"))

    assert tracker.max == 1
