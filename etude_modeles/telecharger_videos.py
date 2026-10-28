"""Les 8 vidéos déjà vérifiées par Gemini, téléchargées comme le fait l'app (sources.download),
puis réduites sous 7 Mo pour Qwen (base64 < 10 Mo). Les deux temps sont mesurés."""
import json, os, subprocess, time
import commun as c
import yt_dlp
from adaptation import sources

VIDEOS = [("ad_20261027_183840_ff28", "https://www.youtube.com/watch?v=iSiWrZvT3hE"),
          ("ad_20261027_183840_ff28", "https://www.youtube.com/watch?v=WNs2IFUezPg"),
          ("ad_20261027_183840_ff28", "https://www.youtube.com/watch?v=zPGEH0WGqK8"),
          ("ad_20261027_195556_8e50", "https://www.youtube.com/watch?v=bcOLmC29ZEo"),
          ("ad_20261027_195556_8e50", "https://www.youtube.com/watch?v=BKpCwRVZCtk"),
          ("ad_20261027_195556_8e50", "https://www.youtube.com/watch?v=Nx5hEoxvSac"),
          ("ad_20261020_164128_c0f0", "https://www.youtube.com/watch?v=EWfuSroUGGM"),
          ("ad_20261020_164128_c0f0", "https://www.youtube.com/watch?v=DLL8WhY_lDw")]
D = os.path.join(c.ICI, "videos")


def duree(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                                capture_output=True, text=True).stdout or 0)


if __name__ == "__main__":
    out = []
    for pid, url in VIDEOS:
        vid = url.split("v=")[1]
        brut, petit = os.path.join(D, vid + ".mp4"), os.path.join(D, vid + "_qwen.mp4")
        t = time.time()
        if not os.path.exists(brut):          # le vrai téléchargeur de l'app
            got = sources.download(url, D, vid)
            if got != brut and os.path.exists(got):
                os.replace(got, brut)
        t_dl = round(time.time() - t, 1)
        t = time.time()
        d = duree(brut)
        kbps = max(80, int(7 * 8 * 1024 * 0.85 / max(d, 1)))        # sous 7 Mo, sans le son (Qwen-VL ne l'écoute pas)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", brut, "-an", "-vf", "scale=-2:360,fps=2", "-c:v", "libx264",
                        "-preset", "veryfast", "-b:v", f"{kbps}k", "-maxrate", f"{kbps}k", "-bufsize", f"{2 * kbps}k", petit], check=True)
        out.append({"projet": pid, "url": url, "duree_s": round(d, 1), "telechargement_s": t_dl,
                    "reduction_s": round(time.time() - t, 1), "taille_mo": round(os.path.getsize(brut) / 2**20, 1),
                    "taille_qwen_mo": round(os.path.getsize(petit) / 2**20, 2)})
        print(out[-1], flush=True)
    c.ecrire("videos_telechargees.json", out)
