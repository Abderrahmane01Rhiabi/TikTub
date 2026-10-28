"""Étape 3 : les étapes qui écrivent, avec les VRAIES fonctions de l'app (mêmes prompts, même lecture de la réponse) ;
seul le fournisseur change. Reprend là où il s'est arrêté (resultats/ecriture.jsonl).
Usage : python etude_modeles/ecriture.py [gemini-flash groq-gpt-oss-120b deepseek-flash]"""
import glob
import json
import os
import sys
import time

import commun as c
from adaptation import storyboard
from adaptation.pipeline import FIX_HOW
from generative import script_generator
from generative.pipeline import GenerativePipeline

JOURNAL = os.path.join(c.ICI, "resultats", "ecriture.jsonl")
SORTIES = os.path.join(c.ICI, "resultats", "sorties")
ESTIMATION = {"storyboard.write": 0.02, "storyboard.critique": 0.04, "storyboard.revise": 0.03,
              "script_generator.generate_script": 0.015}
DEMANDE_DEFAUT = "Rends l'accroche plus forte et raccourcis les phrases qui depassent 5 secondes de voix."


def faits_de(ref):
    return ref.get("faits") or []


def fait(cle):
    try:
        return any(json.loads(l)["cle"] == cle for l in open(JOURNAL, encoding="utf-8") if l.strip())
    except OSError:
        return False


def sortie(etape, cas, modele):
    try:
        return json.load(open(os.path.join(SORTIES, f"{etape}__{cas}__{modele}.json"), encoding="utf-8"))
    except OSError:
        return None


def noter(etape, cas, modele, mesures, out):
    os.makedirs(SORTIES, exist_ok=True)
    json.dump(out, open(os.path.join(SORTIES, f"{etape}__{cas}__{modele}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    with open(JOURNAL, "a", encoding="utf-8") as f:
        f.write(json.dumps({"cle": f"{etape}|{cas}|{modele}", "etape": etape, "cas": cas, "modele": modele, **mesures},
                           ensure_ascii=False) + "\n")
    print(etape, cas[-12:], modele, {k: mesures.get(k) for k in ("json", "complet", "nb_problemes", "hors_faits", "s", "limite")}, flush=True)


def appel_total(f):
    a = f.appels
    return {"s": round(sum(x.get("s", 0) for x in a), 1), "limite": sum(x.get("limite", 0) for x in a),
            "attente_s": sum(x.get("attente_s", 0) for x in a), "json": (a[-1].get("json") if a else "echec"),
            "erreur": next((x.get("erreur") for x in a if x.get("erreur")), None),
            "tokens_entree": sum(x.get("tokens_entree", 0) for x in a), "tokens_sortie": sum(x.get("tokens_sortie", 0) for x in a),
            "cout": round(sum(x.get("cout", 0) or 0 for x in a), 5), "appels": len(a)}


def mesure_sb(b, cas, f):
    codes, ref = cas["codes"], cas["reference"]
    plans = b.get("plans") or []
    complet = (3 <= len(plans) <= 12 and all(((p.get("textes") or {}).get(k) or {}).get("texte") for p in plans for k in codes)
               and all(((b.get("meta") or {}).get(k) or {}).get("titre") for k in codes))
    prob = [f"[{k}] {x}" for k in codes for x in storyboard.problems(b, k)] + storyboard.unfilmable(b)
    textes = [((p.get("textes") or {}).get(k) or {}).get("texte", "") for p in plans for k in codes] + \
             [((b.get("meta") or {}).get(k) or {}).get("titre", "") for k in codes]
    hors = c.chiffres_hors_faits(textes, faits_de(ref)) if ref.get("origine") == "idee" else None
    duree = {k: round(sum(storyboard.seconds(((p.get("textes") or {}).get(k) or {}).get("texte", ""), k) for p in plans)) for k in codes}
    return {**appel_total(f), "complet": bool(complet), "plans": len(plans), "nb_problemes": len(prob), "problemes": prob,
            "duree_s": duree, "hors_faits": None if hors is None else len(hors), "chiffres_hors_faits": hors,
            "corrections": len(b.get("corrections") or [])}


def fournisseur(modele, etape):
    if modele == "gemini-flash":
        return c.Gemini(etape, ESTIMATION[etape])
    return c.groq() if modele.startswith("groq") else c.deepseek()


def adaptation(modeles):
    for chemin in sorted(glob.glob(os.path.join(c.ICI, "cas", "ad_*.json"))):
        cas = json.load(open(chemin, encoding="utf-8"))
        cid, codes, ref = cas["id"], cas["codes"], cas["reference"]
        for modele in modeles:                              # 1. écrire
            if fait(f"storyboard.write|{cid}|{modele}"):
                continue
            f = fournisseur(modele, "storyboard.write")
            try:
                b = storyboard.write(ref, codes, gemini=f, angle=cas.get("angle"))
            except c.BudgetDepasse:
                raise
            except Exception as e:
                noter("storyboard.write", cid, modele, {**appel_total(f), "complet": False, "exception": str(e)[:200]}, {})
                continue
            noter("storyboard.write", cid, modele, mesure_sb(b, cas, f), b)
        brouillon = sortie("storyboard.write", cid, "gemini-flash")
        if not brouillon or not brouillon.get("plans"):
            print("pas de brouillon Gemini pour", cid, ": relecture et correction sautées")
            continue
        prob = [f"[{k}] {x}" for k in codes for x in storyboard.problems(brouillon, k)] + storyboard.unfilmable(brouillon)
        demande = ("Corrige ces problemes : " + " ".join(prob) + FIX_HOW) if prob else DEMANDE_DEFAUT
        for etape in ("storyboard.critique", "storyboard.revise"):      # 2. relire, 3. corriger : le MÊME brouillon (Gemini)
            for modele in modeles:
                if fait(f"{etape}|{cid}|{modele}"):
                    continue
                f = fournisseur(modele, etape)
                try:
                    if etape == "storyboard.critique":
                        b = storyboard.critique(json.loads(json.dumps(brouillon)), codes, gemini=f)
                    else:
                        b = storyboard.revise(json.loads(json.dumps(brouillon)), codes, demande, gemini=f)
                except c.BudgetDepasse:
                    raise
                except Exception as e:
                    noter(etape, cid, modele, {**appel_total(f), "complet": False, "exception": str(e)[:200], "demande": demande}, {})
                    continue
                m = mesure_sb(b, cas, f)
                if etape == "storyboard.critique" and m["json"] == "echec":
                    m["complet"] = False             # l'app garde alors le brouillon tel quel : la relecture n'a pas eu lieu
                noter(etape, cid, modele, {**m, "demande": demande if etape == "storyboard.revise" else None}, b)


def generation(modeles):
    etape = "script_generator.generate_script"
    for chemin in sorted(glob.glob(os.path.join(c.ICI, "cas", "gen_*.json"))):
        cas = json.load(open(chemin, encoding="utf-8"))
        for modele in modeles:
            if fait(f"{etape}|{cas['id']}|{modele}"):
                continue
            f = fournisseur(modele, etape)
            g0, o0 = script_generator.GeminiAIGenerator, script_generator.OpenAIGenerator

            class SansSecours:              # pas de repli sur OpenAI : on mesure le fournisseur seul
                def __init__(self, *a):
                    pass

                def call_openai_api(self, *a, **k):
                    return {}
            script_generator.GeminiAIGenerator, script_generator.OpenAIGenerator = (lambda key: f), SansSecours
            t0 = time.time()
            try:
                d = script_generator.generate_script(cas["profile"], cas["plan"], recent_titles=cas["recent_titles"],
                                                     inspiration=cas["inspiration"])
                prob = GenerativePipeline._script_problems(d, cas["others"], cas["recent_titles"])
                m = {**appel_total(f), "complet": script_generator._is_usable(d), "nb_problemes": len(prob), "problemes": prob,
                     "mots": len((d.get("script_text") or "").split()), "hors_faits": None}
            except c.BudgetDepasse:
                raise
            except Exception as e:
                d, m = {}, {**appel_total(f), "complet": False, "exception": str(e)[:200]}
            finally:
                script_generator.GeminiAIGenerator, script_generator.OpenAIGenerator = g0, o0
            m["s_total"] = round(time.time() - t0, 1)
            noter(etape, cas["id"], modele, m, d)


if __name__ == "__main__":
    modeles = sys.argv[1:] or ["gemini-flash", "groq-gpt-oss-120b"]
    if "deepseek-flash" in modeles and not os.getenv("DEEPSEEK_API_KEY"):
        print("DEEPSEEK_API_KEY absente : DeepSeek sauté")
        modeles.remove("deepseek-flash")
    try:
        adaptation(modeles)
        generation(modeles)
    except c.BudgetDepasse as e:
        print("ARRÊT BUDGET :", e)
    print("Gemini dépensé :", round(c.depense_gemini(), 4), "$ ; DeepSeek :", round(c.depense_deepseek(), 4), "$")
