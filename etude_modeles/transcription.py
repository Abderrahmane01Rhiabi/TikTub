"""Étape 4 : la même piste audio (mp3, comme audio_transcriber) transcrite par whisper-1 (OpenAI, payant), faster-whisper
local (medium et small, les modèles de l'app) et whisper-large-v3 de Groq (gratuit). Pas de texte de référence : on
mesure le temps, le coût, et l'écart entre les textes ; les textes sont mis côte à côte pour être lus."""
import glob, json, os, re, subprocess, time
import commun as c
import requests

D = os.path.join(c.ICI, "transcription")
PRIX_WHISPER1 = 0.006          # $ par minute (openai.com/api/pricing)


def mots(t):
    return re.findall(r"[\w؀-ۿ']+", (t or "").lower())


def ecart(a, b):
    """Taux d'erreur de mots de b par rapport à a (distance d'édition / mots de a)."""
    a, b = mots(a), mots(b)
    d = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        prev, d[0] = d[0], i
        for j, y in enumerate(b, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (x != y))
    return round(d[len(b)] / max(1, len(a)), 3)


def api(url, cle, modele, mp3):
    t = time.time()
    with open(mp3, "rb") as f:
        r = requests.post(url, headers={"Authorization": f"Bearer {cle}"}, files={"file": (os.path.basename(mp3), f, "audio/mpeg")},
                          data={"model": modele}, timeout=180)
    return {"texte": r.json().get("text", "").strip() if r.ok else f"ERREUR {r.status_code} {r.text[:150]}", "s": round(time.time() - t, 1)}


def local(taille, path):
    from faster_whisper import WhisperModel
    t = time.time()
    m = WhisperModel(taille, device="cpu", compute_type="int8")
    t1 = time.time()
    segs, info = m.transcribe(path)
    texte = " ".join(s.text.strip() for s in segs)
    return {"texte": texte, "s": round(time.time() - t1, 1), "chargement_s": round(t1 - t, 1), "langue": info.language}


if __name__ == "__main__":
    out = {}
    for v in sorted(glob.glob(os.path.join(D, "*.mp4"))):
        nom = os.path.basename(v)[:-4]
        mp3 = os.path.join(D, nom + ".mp3")
        if not os.path.exists(mp3):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", v, "-vn", "-c:a", "libmp3lame", "-q:a", "4", mp3], check=True)
        duree = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp3],
                                     capture_output=True, text=True).stdout)
        r = {"duree_s": round(duree, 1)}
        r["whisper-1"] = {**api("https://api.openai.com/v1/audio/transcriptions", os.getenv("OPENAI_API_KEY"), "whisper-1", mp3),
                          "cout": round(duree / 60 * PRIX_WHISPER1, 4)}
        r["groq-whisper-large-v3"] = {**api("https://api.groq.com/openai/v1/audio/transcriptions", os.getenv("GROQ_API_KEY"),
                                            "whisper-large-v3", mp3), "cout": 0}
        for taille in ("medium", "small"):
            r[f"faster-whisper-{taille}"] = {**local(taille, mp3), "cout": 0}
        ref = r["whisper-1"]["texte"]
        for k in ("groq-whisper-large-v3", "faster-whisper-medium", "faster-whisper-small"):
            r[k]["ecart_avec_whisper1"] = ecart(ref, r[k]["texte"])
        out[nom] = r
        print(nom, {k: (x.get("s"), x.get("ecart_avec_whisper1")) for k, x in r.items() if isinstance(x, dict)}, flush=True)
    c.ecrire("transcription.json", out)
