"""Groq en rafale (gratuit) : 4 storyboard.write d'affilée, puis 2 en même temps (versions FR et AR lancées ensemble).
Mesure les refus (429), l'attente imposée et les jetons restants annoncés par l'API."""
import glob, json, os, time
from concurrent.futures import ThreadPoolExecutor
import commun as c
from adaptation import storyboard

cas = [json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob(os.path.join(c.ICI, "cas", "ad_*.json")))]


def un(x):
    f = c.groq()
    t = time.time()
    storyboard.write(x["reference"], x["codes"], gemini=f, angle=x.get("angle"))
    a = f.appels[-1]
    return {"cas": x["id"][-4:], "s": round(time.time() - t, 1), "refus_429": a.get("limite"), "attente_s": a.get("attente_s"),
            "tokens": a.get("tokens_entree", 0) + a.get("tokens_sortie", 0),
            "restant_minute": a.get("en_tetes", {}).get("x-ratelimit-remaining-tokens"),
            "restant_jour_requetes": a.get("en_tetes", {}).get("x-ratelimit-remaining-requests")}


out = {"d_affilee": [], "en_meme_temps": []}
for x in cas[:4]:
    out["d_affilee"].append(un(x)); print(out["d_affilee"][-1], flush=True)
time.sleep(65)
with ThreadPoolExecutor(2) as p:
    out["en_meme_temps"] = list(p.map(un, cas[:2]))
print(out["en_meme_temps"])
c.ecrire("groq_rafale.json", out)
