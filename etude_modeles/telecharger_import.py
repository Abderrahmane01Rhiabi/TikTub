"""3 vidéos importées récemment (publiées), retéléchargées en copie : l'app efface les fichiers après publication."""
import os, sys, time
import commun as c  # noqa: F401  (chemins, .env)
import yt_dlp
from adaptation.finder import ytdlp_opts

URLS = {"lungtemotivates_en": "https://www.instagram.com/p/Db_vqf8y73b/",
        "prince_moulay_hassan": "https://www.instagram.com/p/DeKGC2XPTf-/",
        "meme_culture_x": "https://x.com/TheNewsJunkiesC/status/2113762576895225859/video/1"}
D = os.path.join(c.ICI, "transcription")
for nom, url in URLS.items():
    if any(f.startswith(nom + ".") for f in os.listdir(D)):
        continue
    t = time.time()
    try:
        with yt_dlp.YoutubeDL(ytdlp_opts(outtmpl=os.path.join(D, nom + ".%(ext)s"), format="best", noplaylist=True, quiet=True)) as y:
            y.extract_info(url, download=True)
        print(nom, "ok", round(time.time() - t, 1), "s")
    except Exception as e:
        print(nom, "ÉCHEC", str(e)[:200])
