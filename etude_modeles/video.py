"""La vérification d'une vidéo candidate (finder.check, le MÊME prompt) : Gemini comme dans l'app (lien YouTube), Qwen3-VL-Plus
sur le fichier téléchargé (Qwen ne lit pas les liens YouTube). Comparé au verdict de Gemini déjà en base.
Usage : python etude_modeles/video.py gemini|qwen"""
import base64
import json
import os
import sys
import time

import commun as c
import requests
from adaptation import finder, sources

JOURNAL = os.path.join(c.ICI, "resultats", "video.jsonl")
QWEN_URL = (os.getenv("DASHSCOPE_BASE_URL") or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1") + "/chat/completions"
QWEN_PRIX = [(32_000, 0.2, 1.6), (128_000, 0.3, 2.4), (256_000, 0.6, 4.8)]     # Singapour, $/M (entrée, sortie) par palier


def projet(pid):
    return json.load(open(os.path.join(c.RACINE, "etude_economies", "projets", f"{pid}.json"), encoding="utf-8"))


def qwen_cout(entree, sortie):
    _, pe, ps = next((x for x in QWEN_PRIX if entree <= x[0]), QWEN_PRIX[-1])
    return (entree * pe + sortie * ps) / 1e6


def deja():
    try:
        return {json.loads(l)["cle"] for l in open(JOURNAL, encoding="utf-8") if l.strip()}
    except OSError:
        return set()


def regarder_qwen(fichier, info):
    def _watch(url, g, prompt):
        data = base64.b64encode(open(fichier, "rb").read()).decode()
        corps = {"model": "qwen3-vl-plus", "temperature": 0.1, "max_tokens": 8000,
                 "messages": [{"role": "user", "content": [
                     {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{data}"}, "fps": finder.CHECK_FPS},
                     {"type": "text", "text": prompt}]}]}
        t = time.time()
        r = requests.post(QWEN_URL, headers={"Authorization": f"Bearer {os.getenv('DASHSCOPE_API_KEY')}"}, json=corps, timeout=600)
        info["appel_s"] = round(time.time() - t, 1)
        if r.status_code != 200:
            info["erreur"] = f"{r.status_code} {r.text[:300]}"
            return {"answer": {"error": info["erreur"]}, "duration": None, "title": ""}
        d = r.json()
        u = d.get("usage") or {}
        info.update(tokens_entree=u.get("prompt_tokens", 0), tokens_sortie=u.get("completion_tokens", 0),
                    cout=round(qwen_cout(u.get("prompt_tokens", 0), u.get("completion_tokens", 0)), 5))
        rep, info["json"] = c.lire_json(d["choices"][0]["message"].get("content") or "")
        return {"answer": rep, "duration": None, "title": ""}
    return _watch


if __name__ == "__main__":
    modele = sys.argv[1]
    if modele == "qwen" and not os.getenv("DASHSCOPE_API_KEY"):
        sys.exit("DASHSCOPE_API_KEY absente")
    videos = json.load(open(os.path.join(c.ICI, "resultats", "videos_telechargees.json"), encoding="utf-8"))
    fait = deja()
    for v in videos:
        cle = f"{modele}|{v['url']}"
        if cle in fait:
            continue
        p = projet(v["projet"])
        scenes, ref = p["suggestions"]["scenes"], p["reference"]
        model_part = finder.model_of(ref)
        info = {"json": "direct", "erreur": None}
        sources.reachable = lambda url: True          # pas de 2e téléchargement pour savoir s'il est possible
        t = time.time()
        if modele == "gemini":
            if c.depense_gemini() + 0.05 > c.BUDGET_GEMINI:
                print("ARRÊT BUDGET Gemini"); break
            avant = c.depense_gemini()
            g = c.gg.GeminiAIGenerator(api_key=os.getenv("GEMINI_API_KEY"))
            old = c.gg._asking_step
            c.gg._asking_step = lambda: "finder._watch"          # même modèle et même réflexion (256) que l'app
            try:
                r = finder.check(v["url"], scenes, [], gemini=g, **({"model": model_part} if model_part else {}))
            except Exception as e:
                r, info["erreur"] = None, str(e)[:300]
            finally:
                c.gg._asking_step = old
            info["cout"] = round(c.depense_gemini() - avant, 5)
        else:
            fichier = os.path.join(c.ICI, "videos", v["url"].split("v=")[1] + "_qwen.mp4")
            old = finder._watch
            finder._watch = regarder_qwen(fichier, info)
            try:
                r = finder.check(v["url"], scenes, [], gemini=object(), **({"model": model_part} if model_part else {}))
            except Exception as e:
                r, info["erreur"] = None, str(e)[:300]
            finally:
                finder._watch = old
            info["telechargement_s"] = v["telechargement_s"] + v["reduction_s"]
        info["s"] = round(time.time() - t, 1)
        base = p["suggestions"]["verifs"][v["url"]]
        choisis = [k for k, x in enumerate(p["picks"]) if (x or {}).get("url") == v["url"]]
        n = len(scenes)
        avant_ = {str(k): (base["par_scene"].get(str(k)) or {}).get("niveau", "rien") for k in range(n)}
        apres = {str(k): ((r or {}).get("par_scene", {}).get(str(k)) or {}).get("niveau", "rien") for k in range(n)} if r else None
        ligne = {"cle": cle, "modele": modele, "projet": v["projet"], "url": v["url"], "duree_video_s": v["duree_s"], **info,
                 "verdict_base": base["verdict"], "verdict": (r or {}).get("verdict"), "scenes_base": avant_, "scenes": apres,
                 "accord": None if apres is None else sum(avant_[k] == apres[k] for k in avant_), "n": n,
                 "choisies": choisis, "choisie_devenue_rien": [k for k in choisis if apres and apres[str(k)] == "rien"] if apres else None}
        with open(JOURNAL, "a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
        print({k: ligne[k] for k in ("modele", "url", "verdict_base", "verdict", "accord", "n", "choisie_devenue_rien", "s", "cout", "erreur")}, flush=True)
    print("Gemini dépensé (étude) :", round(c.depense_gemini(), 4))
