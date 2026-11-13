"""
What is said in a few videos (adaptation/pretri), in its own process: the CUDA libraries must be on the library path
when it starts, and Whisper's memory goes back to the system when it ends.

  python adaptation/parole_worker.py <jobs.json> <folder>
  jobs.json  [{url, vid}]; for each: its audio alone (the lightest), Whisper medium on the graphics card (small on the
             processor if the card refuses), every word's instant; <folder>/<vid>.json = {vid, langue, parole_s, cues};
             the audio deleted. Prints « FAIT <vid> » after each (the progress), never stops on one video's failure.
"""

import glob
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # the app's code, whatever the cwd


def _model():
    from faster_whisper import WhisperModel
    try:
        return WhisperModel("medium", device="cuda", compute_type="int8_float16")
    except Exception:
        return WhisperModel("small", device="cpu", compute_type="int8")


def _audio(url: str, vid: str, folder: str) -> str:
    import yt_dlp
    from adaptation.sources import ytdlp_opts
    o = ytdlp_opts(format="worstaudio[acodec=opus]/worstaudio/worst", ratelimit=1_000_000, retries=2,
                   outtmpl=os.path.join(folder, vid + ".%(ext)s"))
    with yt_dlp.YoutubeDL(o) as y:
        y.extract_info(url, download=True)
    files = [f for f in glob.glob(os.path.join(folder, vid + ".*")) if not f.endswith(".json")]
    if not files:
        raise RuntimeError("audio absent")
    return files[0]


def main(jobs_path: str, folder: str) -> None:
    jobs = json.load(open(jobs_path))
    model = None
    for k, job in enumerate(jobs):
        vid, out = job["vid"], os.path.join(folder, job["vid"] + ".json")
        if os.path.exists(out):
            print("FAIT", vid, flush=True)
            continue
        audio = None
        try:
            audio = _audio(job["url"], vid, folder)
            model = model or _model()
            segs, info = model.transcribe(audio, word_timestamps=True, vad_filter=True, beam_size=5)
            cues = [{"t": round(s.start, 2), "d": round(s.end - s.start, 2), "text": s.text.strip(),
                     "words": [[round(w.start, 2), w.word.strip()] for w in (s.words or []) if w.word.strip()]}
                    for s in segs]
            rec = {"vid": vid, "langue": info.language, "parole_s": round(sum(c["d"] for c in cues), 1), "cues": cues}
        except Exception as e:
            rec = {"vid": vid, "erreur": str(e)[:200], "parole_s": 0, "cues": []}
        finally:
            if audio and os.path.exists(audio):
                os.remove(audio)
        tmp = out + ".tmp"
        json.dump(rec, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
        os.replace(tmp, out)
        print("FAIT", vid, flush=True)
        if k + 1 < len(jobs):
            time.sleep(random.uniform(3, 6))        # gently: the other downloads of the app go on


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
