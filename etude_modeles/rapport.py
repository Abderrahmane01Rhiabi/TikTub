"""Écrit etude_modeles/A_LIRE.md (les textes côte à côte) et RESULTATS_MODELES.md (les mesures) à partir des résultats
enregistrés : aucun appel payant. Les mesures sont recalculées sur les sorties (même code que l'app)."""
import glob
import json
import os
from collections import defaultdict
from datetime import datetime

import commun as c
import ai_models
from adaptation import storyboard

R = os.path.join(c.ICI, "resultats")
MODELES = ["gemini-flash", "groq-gpt-oss-120b", "deepseek-flash"]
NOMS = {"gemini-flash": "Gemini Flash (témoin)", "groq-gpt-oss-120b": "Groq gpt-oss-120b", "deepseek-flash": "DeepSeek Flash"}
ETAPES = ["storyboard.write", "storyboard.critique", "storyboard.revise", "script_generator.generate_script"]
ETAPE_FR = {"storyboard.write": "Écrire le storyboard", "storyboard.critique": "Relire le storyboard",
            "storyboard.revise": "Corriger le storyboard", "script_generator.generate_script": "Script de la Génération"}


def lignes(nom):
    try:
        return [json.loads(l) for l in open(os.path.join(R, nom), encoding="utf-8") if l.strip()]
    except OSError:
        return []


def sortie(etape, cas, modele):
    try:
        return json.load(open(os.path.join(R, "sorties", f"{etape}__{cas}__{modele}.json"), encoding="utf-8"))
    except OSError:
        return None


CAS = {os.path.basename(f)[:-5]: json.load(open(f, encoding="utf-8")) for f in glob.glob(os.path.join(c.ICI, "cas", "*.json"))}
CAS = {(v["id"]): v for v in CAS.values()}


def remesure(x):
    """Problèmes et chiffres recalculés sur la sortie enregistrée (l'extracteur de chiffres a été corrigé après coup)."""
    if x["etape"] == "script_generator.generate_script" or not x.get("complet"):
        return x
    b, cas = sortie(x["etape"], x["cas"], x["modele"]), CAS[x["cas"]]
    codes, ref = cas["codes"], cas["reference"]
    prob = [f"[{k}] {p}" for k in codes for p in storyboard.problems(b, k)] + storyboard.unfilmable(b)
    textes = [((p.get("textes") or {}).get(k) or {}).get("texte", "") for p in b["plans"] for k in codes] + \
             [((b.get("meta") or {}).get(k) or {}).get("titre", "") for k in codes]
    hors = c.chiffres_hors_faits(textes, ref.get("faits") or []) if ref.get("origine") == "idee" else None
    return {**x, "nb_problemes": len(prob), "problemes": prob, "hors_faits": None if hors is None else len(hors),
            "chiffres_hors_faits": hors}


ECR = [remesure(x) for x in lignes("ecriture.jsonl")]
VID = lignes("video.jsonl")
pct = lambda a, b: f"{round(100 * a / b)} %" if b else "—"


def table_ecriture():
    out = []
    for e in ETAPES:
        out += [f"\n**{ETAPE_FR[e]}** (`{e}`)\n", "| Modèle | Sorties | JSON valide | Complet | Contrôles réussis (0 problème) | Problèmes en moyenne | "
                "Chiffres hors des faits (mode Idée) | Temps moyen | Refus « limite » (429) |", "|---|---|---|---|---|---|---|---|---|"]
        for m in MODELES:
            xs = [x for x in ECR if x["etape"] == e and x["modele"] == m]
            if not xs:
                out.append(f"| {NOMS[m]} | — | *pas testé* | | | | | | |")
                continue
            ok = [x for x in xs if x.get("complet")]
            idee = [x for x in ok if x.get("hors_faits") is not None]
            out.append(f"| {NOMS[m]} | {len(xs)} | {pct(sum(x.get('json') in ('direct', 'extrait') for x in xs), len(xs))} | "
                       f"{pct(len(ok), len(xs))} | {pct(sum(x.get('nb_problemes') == 0 for x in ok), len(xs))} | "
                       f"{sum(x.get('nb_problemes') or 0 for x in ok) / max(1, len(ok)):.1f} | "
                       + (f"{sum(x['hors_faits'] for x in idee)} chiffre(s) sur {len(idee)} sorties" if idee else "—")
                       + f" | {sum(x.get('s', 0) for x in xs) / len(xs):.1f} s | {sum(x.get('limite', 0) for x in xs)} |")
    return "\n".join(out)


def table_video():
    out = ["| Modèle | Vidéos | Même niveau par scène | Même verdict | Scène choisie devenue « rien » | Coût réel par vidéo "
           "(moyenne / max) | Temps par vidéo (moyenne) | dont téléchargement | Erreurs |", "|---|---|---|---|---|---|---|---|---|"]
    for m, nom in (("gemini", "Gemini Flash aujourd'hui (lien YouTube)"), ("qwen", "Qwen3-VL-Plus (fichier téléchargé)")):
        xs = [x for x in VID if x["modele"] == m]
        if not xs:
            out.append(f"| {nom} | — | *pas encore testé (clé DASHSCOPE_API_KEY absente)* | | | | | | |")
            continue
        ok = [x for x in xs if x.get("scenes")]
        perdue = sum(1 for x in ok for k in x["choisies"] if x["scenes_base"][str(k)] != "rien" and x["scenes"][str(k)] == "rien")
        choisies = sum(1 for x in ok for k in x["choisies"] if x["scenes_base"][str(k)] != "rien")
        dl = [x.get("telechargement_s", 0) for x in xs]
        couts = [x.get("cout") or 0 for x in xs]
        out.append(f"| {nom} | {len(xs)} | {pct(sum(x['accord'] for x in ok), sum(x['n'] for x in ok))} | "
                   f"{sum(x['verdict'] == x['verdict_base'] for x in ok)}/{len(ok)} | {perdue} sur {choisies} | "
                   f"{sum(couts) / len(xs):.4f} $ / {max(couts):.4f} $ | {sum(x['s'] + x.get('telechargement_s', 0) for x in xs) / len(xs):.0f} s | "
                   f"{sum(dl) / len(xs):.0f} s | {sum(1 for x in xs if x.get('erreur'))} |")
    return "\n".join(out)


def table_transcription():
    t = json.load(open(os.path.join(R, "transcription.json"), encoding="utf-8"))
    out = ["| Vidéo | Durée | Modèle | Temps | Coût | Écart de mots avec whisper-1 |", "|---|---|---|---|---|---|"]
    for v, x in t.items():
        for k in ("whisper-1", "groq-whisper-large-v3", "faster-whisper-medium", "faster-whisper-small"):
            y = x[k]
            temps = f"{y['s']} s" + (f" (+ {y['chargement_s']} s de chargement du modèle)" if y.get("chargement_s") else "")
            out.append(f"| {v} | {x['duree_s']:.0f} s | {k} | {temps} | {y['cout']:.4f} $ | "
                       f"{'—' if k == 'whisper-1' else (str(round(100 * y['ecart_avec_whisper1'])) + ' %')} |")
    return "\n".join(out), t


def journal():
    rows = [json.loads(l) for l in open(os.path.join(c.RACINE, "temp", "usage", "gemini.jsonl"), encoding="utf-8") if l.strip()]
    t0, t1 = datetime.fromisoformat(rows[0]["at"]), datetime.fromisoformat(rows[-1]["at"])
    jours = (t1 - t0).total_seconds() / 86400
    texte = {s for s in {r["step"] for r in rows}
             if all(k == "TEXT" for r in rows if r["step"] == s for k in (r.get("by_kind") or {"TEXT": 0}))}
    texte -= {"script.critique", "idee.research", "<stdin>.<module>", "ai_tags_generator.__init__"}
    agg = defaultdict(lambda: [0, 0.0, 0.0, 0])
    for r in rows:
        if r["step"] in texte:
            rr = {**r, "model": ai_models.FLASH}          # la relecture du storyboard est passée sur Flash depuis
            a = agg[r["step"]]
            a[0] += r.get("prompt", 0) + r.get("output", 0) + r.get("thoughts", 0)
            a[1] += ai_models.cost(rr)
            a[2] += ai_models.cost(rr, "2027-01-02")
            a[3] += 1
    total = sum(ai_models.cost(r) for r in rows)
    return jours, agg, total


def capacite():
    """Jetons Groq mesurés par storyboard (écrire + relire + corriger une fois) et par script de Génération."""
    g = [x for x in ECR if x["modele"] == "groq-gpt-oss-120b"]
    par = lambda e: [x.get("tokens_entree", 0) + x.get("tokens_sortie", 0) for x in g if x["etape"] == e]
    sb = sum(sum(par(e)) / max(1, len(par(e))) for e in ETAPES[:3])
    gen = sum(par(ETAPES[3])) / max(1, len(par(ETAPES[3])))
    return round(sb), round(gen)


def a_lire():
    L = ["# À lire : les textes côte à côte", "",
         "Mêmes cas, mêmes prompts que l'app. Seul le modèle change. Aucun avis de ma part : les mesures sont dans "
         "`RESULTATS_MODELES.md`. Pour la relecture et la correction, tous les modèles reçoivent **le même brouillon** "
         "(celui écrit par Gemini).", ""]
    present = [m for m in MODELES if any(x["modele"] == m for x in ECR)]
    for e in ETAPES[:3]:
        L.append(f"## {ETAPE_FR[e]}\n")
        for cid, cas in sorted(CAS.items()):
            if cid.startswith("lungte"):
                continue
            code = cas["codes"][0]
            outs = {m: sortie(e, cid, m) for m in present}
            if not any(outs.values()):
                continue
            mode = "mode Idée" if cas["reference"].get("origine") == "idee" else "d'après un Short modèle"
            L.append(f"### {cid} — {'arabe' if code == 'ar' else 'français'}, {mode}\n")
            x0 = next((x for x in ECR if x["etape"] == e and x["cas"] == cid and x.get("demande")), None)
            if x0:
                L.append(f"*Demande de correction envoyée :* {x0['demande'][:400]}\n")
            L.append("| # | " + " | ".join(NOMS[m] for m in present) + " |")
            L.append("|---|" + "---|" * len(present))
            titre = lambda b: (((b or {}).get("meta") or {}).get(code) or {}).get("titre", "")
            L.append("| titre | " + " | ".join(titre(outs[m]).replace("|", "/") for m in present) + " |")
            n = max(len((outs[m] or {}).get("plans") or []) for m in present)
            for k in range(n):
                cell = []
                for m in present:
                    ps = (outs[m] or {}).get("plans") or []
                    if k < len(ps):
                        t = (ps[k].get("textes") or {}).get(code) or {}
                        cell.append(f"{t.get('texte', '')}<br>*image : {ps[k].get('image', '')}*".replace("|", "/").replace("\n", " "))
                    else:
                        cell.append("")
                L.append(f"| {k + 1} | " + " | ".join(cell) + " |")
            for m in present:
                x = next((x for x in ECR if x["etape"] == e and x["cas"] == cid and x["modele"] == m), None)
                if x and (x.get("problemes") or x.get("chiffres_hors_faits")):
                    L.append(f"\n- **{NOMS[m]}** : contrôles de l'app : {'; '.join(x.get('problemes') or []) or 'aucun problème'}"
                             + (f" ; chiffres absents des faits : {', '.join(str(int(n)) if n == int(n) else str(n) for n, _ in x['chiffres_hors_faits'])}"
                                if x.get("chiffres_hors_faits") else ""))
            L.append("")
    L.append(f"## {ETAPE_FR[ETAPES[3]]} (lungtemotivates, la seule chaîne qui l'utilise)\n")
    for cid in sorted(k for k in CAS if k.startswith("lungte")):
        L.append(f"### {cid}\n")
        for m in present:
            d = sortie(ETAPES[3], cid, m) or {}
            L.append(f"**{NOMS[m]}** — *{d.get('title', '(réponse inutilisable)')}*\n\n> " + (d.get("script_text") or "").replace("\n", "\n> ") + "\n")
    tt, t = table_transcription()
    L.append("## Transcription (les textes complets)\n")
    for v, x in t.items():
        L.append(f"### {v}\n")
        for k in ("whisper-1", "groq-whisper-large-v3", "faster-whisper-medium", "faster-whisper-small"):
            L.append(f"**{k}** : {x[k]['texte'] or '(vide)'}\n")
    open(os.path.join(c.ICI, "A_LIRE.md"), "w", encoding="utf-8").write("\n".join(L))


if __name__ == "__main__":
    a_lire()
    jours, agg, total_periode = journal()
    mois = 30 / jours
    testees = ETAPES
    cout_t = sum(agg[s][1] for s in testees) * mois
    cout_t27 = sum(agg[s][2] for s in testees) * mois
    cout_all = sum(a[1] for a in agg.values()) * mois
    cout_all27 = sum(a[2] for a in agg.values()) * mois
    tok_jour_t = sum(agg[s][0] for s in testees) / jours
    tok_jour_all = sum(a[0] for a in agg.values()) / jours
    sb, gen = capacite()
    tt, _ = table_transcription()
    nb = {e: sum(a[3] for s_, a in agg.items() if s_ == e) for e in ETAPES}
    moy = {e: (lambda xs: sum(x["cout"] for x in xs) / len(xs) if xs else 0)([x for x in ECR if x["modele"] == "deepseek-flash" and x["etape"] == e]) for e in ETAPES}
    ds_creux = sum(nb[e] * moy[e] for e in ETAPES) * mois
    ds_pleine = ds_creux * 2
    raf = json.load(open(os.path.join(R, "groq_rafale.json"), encoding="utf-8"))
    vids = json.load(open(os.path.join(R, "videos_telechargees.json"), encoding="utf-8"))
    whisper_cout = sum(x["whisper-1"]["cout"] for x in json.load(open(os.path.join(R, "transcription.json"))).values())
    ds = c.depense_deepseek()
    qwen_tok = sum((x.get("tokens_entree") or 0) + (x.get("tokens_sortie") or 0) for x in VID if x["modele"] == "qwen")
    out = open(os.path.join(c.RACINE, "RESULTATS_MODELES.md"), "w", encoding="utf-8")
    out.write(f"""# Des modèles gratuits peuvent-ils remplacer Gemini pour écrire ?

Étude du {datetime.now():%d/%m/%Y}, branche `etude/autres-modeles`. Aucun module de l'app n'a été modifié. Les textes
sont côte à côte dans `etude_modeles/A_LIRE.md` : la qualité, c'est à toi de la juger. Ici, seulement des mesures.

Mistral a été écarté à ta demande (seul `ministral-14b`, un petit modèle, est ouvert gratuitement).
**DeepSeek est testé. Qwen ne l'est pas** : `DASHSCOPE_API_KEY` n'est pas dans `.env` (seule l'adresse
`DASHSCOPE_BASE_URL` l'est). Tout est prêt pour Qwen : il suffit d'ajouter la clé puis de lancer les commandes en fin de
fichier.

## 1. Les offres gratuites

| | Groq | DeepSeek (payant, très bon marché) | Qwen3-VL-Plus (Alibaba, Singapour) |
|---|---|---|---|
| Modèle | `openai/gpt-oss-120b` | `deepseek-flash` (V4.1 Flash) | `qwen3-vl-plus` |
| Gratuit ? | oui | non : 0,15 $ / 0,60 $ par million (entrée / sortie) en heure creuse, le double en heure pleine | 1 million de tokens offerts, 90 jours ; puis 0,20 $ / 1,60 $ par million |
| Limites | 30 requêtes/min, 1 000/jour, **8 000 tokens/min**, **200 000 tokens/jour** | — | vidéo en base64 : fichier < 7 Mo |
| Tes données | pas d'entraînement sans ton accord (contrat §4.2) | ⚠️ stockées **en Chine** ; la politique dit utiliser les saisies pour « entraîner et améliorer » ses modèles, avec un droit de refus (pas de précision propre à l'API) | à vérifier quand tu ouvres le compte |
| Usage commercial | les textes t'appartiennent (§8.1) ; ⚠️ le contrat interdit un usage « destiné à éviter de payer » (§6.3(d)(iii)) | payant : pas de question | payant après l'essai |
| Heures | — | heures pleines 01-04 h et 06-10 h UTC en semaine : l'étude refuse d'y appeler | — |

**Ce qui pourrait poser problème** : (1) la limite de Groq par minute (mesurée : dès le 3ᵉ storyboard d'affilée, Groq
refuse et impose 25 à 33 s d'attente ; deux versions FR+AR lancées ensemble : l'une attend 12 s) ; (2) la clause
« éviter de payer » de Groq, floue pour un usage en production ; (3) la vidéo chez Qwen doit être téléchargée puis
réduite sous 7 Mo (temps mesuré plus bas), alors que Gemini lit le lien YouTube directement.

## 2. Les étapes qui écrivent

Étapes testées : les 4 étapes texte les plus coûteuses (sans image, sans vidéo, sans recherche Google ;
`script.critique` exclue). 5 vrais cas par étape : pour l'Adaptation 3 en arabe, 2 en français, 3 en mode Idée ;
pour la Génération, 5 scripts de lungtemotivates (aucune chaîne arabe n'utilise la Génération).
« Contrôles réussis » = aucun problème trouvé par les contrôles de l'app (`storyboard.problems`, `unfilmable`, durées
25-35 s ; pour la Génération : `_script_problems`, qui comprend la répétition). « Chiffres hors des faits » : en mode
Idée, les nombres du texte qu'on ne retrouve pas dans les faits sourcés (détection automatique en chiffres et en
lettres, français et arabe ; chaque cas est listé dans `A_LIRE.md`).
{table_ecriture()}

Remarques mesurées :
- Gemini : 1 script de Génération sur 5 inutilisable (réponse illisible) : l'app serait passée à OpenAI.
- La correction de Gemini a produit jusqu'à 15 000 tokens de réponse (réflexion comprise) et 106 s pour un cas ; Groq
  reste entre 4 et 9 s.
- Pendant le test, les appels Groq étaient espacés par ceux de Gemini (≈ 20 s) : aucun refus. Le test de rafale
  ci-dessous montre ce qui arrive sans cet espace.

**Groq en rafale** (gratuit, `storyboard.write`) :

| Situation | Résultat |
|---|---|
| 4 storyboards d'affilée | 1ᵉʳ et 2ᵉ : immédiats ; 3ᵉ : refusé puis {raf['d_affilee'][2]['attente_s']} s d'attente ; 4ᵉ : {raf['d_affilee'][3]['attente_s']} s d'attente |
| 2 en même temps (FR + AR) | l'un passe, l'autre attend {max(x['attente_s'] for x in raf['en_meme_temps'])} s |

**Combien de vidéos par jour Groq pourrait vraiment écrire** (tokens Groq mesurés : ≈ {f'{sb:,}'.replace(',', ' ')} par storyboard — écrire,
relire, corriger une fois — et ≈ {f'{gen:,}'.replace(',', ' ')} par script de Génération) :

| | Par jour |
|---|---|
| Limite de Groq | 200 000 tokens, 1 000 requêtes, et ≈ 2 storyboards par minute |
| Storyboards seuls | ≈ **{200000 // max(sb, 1)} storyboards/jour** (≈ {200000 // max(sb, 1) // 2} Shorts en FR + AR) |
| Scripts de Génération seuls | ≈ {200000 // max(gen, 1)} scripts/jour |
| Ton volume réel (journal du {datetime.fromisoformat(json.loads(open(os.path.join(c.RACINE, 'temp', 'usage', 'gemini.jsonl')).readline())['at']):%d/%m} sur {jours:.1f} jours) | ≈ {tok_jour_t / 1000:.0f} 000 tokens/jour Gemini pour ces 4 étapes (Gemini pense plus que Groq : en tokens Groq, ≈ {round((8 / jours) * sb + (10 / jours) * gen) // 1000} 000) |
| Part qui resterait sur Gemini | **≈ 0 % à ton volume actuel** pour la limite par jour ; seuls les pics passent en secours (ou attendent ≈ 30 s) à cause de la limite par minute. Avec toutes les étapes texte (≈ {tok_jour_all / 1000:.0f} 000 tokens Gemini/jour), on approche la limite : un jour chargé (≥ {200000 // max(sb, 1)} storyboards) basculerait le reste sur Gemini |

## 3. La vidéo : Gemini contre Qwen3-VL-Plus (`finder._watch`)

8 vidéos déjà vérifiées par Gemini (3 avions, 3 chameau, 2 projet du 20/10 ; 6 choisies, 2 rejetées). Le repère est le
verdict **en base**. Gemini a été relancé aujourd'hui sur les mêmes vidéos pour connaître son vrai coût et sa variation
naturelle (un même modèle ne répond pas deux fois pareil).

{table_video()}

Téléchargement pour Qwen (Gemini n'en a pas besoin) : {sum(v['telechargement_s'] for v in vids):.0f} s pour les 8 vidéos
({min(v['telechargement_s'] for v in vids)} à {max(v['telechargement_s'] for v in vids)} s chacune), plus
{sum(v['reduction_s'] for v in vids):.0f} s pour les réduire sous 7 Mo (360p, 2 images/s, sans le son ; jusqu'à
{max(v['reduction_s'] for v in vids)} s pour une vidéo de 9 min). Qwen-VL ne reçoit pas le son ; Gemini l'écoute.

## 4. La transcription : whisper-1 contre les gratuits

Pas de texte de référence : l'écart est mesuré par rapport à whisper-1 (celui de l'app). Les textes complets sont dans
`A_LIRE.md`.

{tt}

Constats : la vidéo de lungtemotivates n'a que de la musique : whisper-1 rend un texte vide (juste), Groq invente
« The The The… » et faster-whisper écrit « Music ». En anglais (meme_culture), les quatre disent presque la même chose.
En darija marocaine (prince_moulay_hassan), aucun n'est fiable et ils ne s'accordent pas entre eux. faster-whisper
« medium » est lent sur ce PC (375 s pour 69 s de son en arabe).

## 5. L'économie possible par mois

Projection du journal réel ({jours:.1f} jours, {total_periode:.2f} $ au total) sur 30 jours, au prix de Flash (la relecture
du storyboard comptée sur Flash, comme aujourd'hui) :

| Si on remplaçait Gemini sur… | Aujourd'hui | Au 1ᵉʳ janvier 2027 (Flash ×2) |
|---|---|---|
| les 4 étapes testées | **≈ {cout_t:.2f} $/mois** | **≈ {cout_t27:.2f} $/mois** |
| **si c'est DeepSeek Flash qui remplace Gemini** sur ces 4 étapes (coût mesuré, heures creuses ; ×2 en heures pleines) | ≈ {ds_creux:.2f} $/mois (≈ {ds_pleine:.2f} $ si tout tombe en heures pleines) | pas de changement de prix annoncé |
| toutes les étapes texte (sauf recherche Google et relecture du script) | ≈ {cout_all:.2f} $/mois | ≈ {cout_all27:.2f} $/mois |

Pour comparer : sur la même période, tout Gemini coûte ≈ {total_periode * mois:.0f} $/mois (avant les économies du 28/10) ;
les étapes texte n'en sont qu'une petite part : l'essentiel est la vidéo (`finder._watch` ≈ 42 %).
Avec Groq (gratuit) l'économie est totale (5,64 $ → 0 $) ; avec DeepSeek elle est de Gemini moins le coût DeepSeek de la ligne ci-dessus. La réflexion de DeepSeek (≈ 6 000 à 8 000 tokens par étape) est facturée comme sortie.

## 6. Ce qu'il faudrait changer dans le code (non fait)

1. **`ai_models.STEPS`** : chaque étape reçoit une liste ordonnée de (fournisseur, modèle), par exemple
   `"storyboard.write": [("groq", "openai/gpt-oss-120b"), ("gemini", FLASH)]`. `model_for` reste pour Gemini ;
   une nouvelle `providers_for(step)` rend la liste.
2. **Un client par fournisseur** (`providers.py`) au format OpenAI (Groq, DeepSeek) : même texte de prompt, mode JSON
   (`response_format`), `max_tokens`, température ; la réflexion (`thinking`) de Gemini n'a pas d'équivalent direct.
3. **Dans `GeminiAIGenerator._generate_content`**, avant l'appel Google : si l'étape a un premier fournisseur autre que
   Gemini **et** que les `parts` ne contiennent que du texte, on l'essaie. **Secours automatique sur Gemini** si :
   erreur réseau, délai dépassé, 429 (limite) ou 413, JSON illisible, ou réponse jugée inutilisable par l'étape (le
   test qui existe déjà, ex. `_is_usable`). Toutes les étapes de l'app passent par cette méthode : aucune autre
   ne change.
4. **Un compteur de limites** : lire les en-têtes `x-ratelimit-remaining-*` de Groq ; si la minute ou le jour est
   épuisé, passer directement à Gemini (pas d'attente de 30 s pendant un montage).
5. **Le journal d'usage** (`log_usage`) note le fournisseur ; `ai_models.PRICES` reçoit les prix (0 pour Groq,
   DeepSeek en heure creuse / pleine) : le coût du mois reste juste.
6. **Les clés** dans `.env` ; si une clé manque, l'étape va directement sur Gemini.
7. **Tests** : un faux Groq qui répond 429 → l'appel finit sur Gemini ; une étape avec image → jamais envoyée à Groq ;
   JSON cassé → secours.

## 7. Coût réel de l'étude

| Fournisseur | Coût |
|---|---|
| Gemini | **{c.depense_gemini():.3f} $** (budget 0,50 $) |
| OpenAI whisper-1 | {whisper_cout:.3f} $ |
| Groq | 0 $ (offre gratuite) |
| DeepSeek | {ds:.3f} $ (budget 1 $) {'— pas testé' if not ds else ''} |
| Qwen | {'0 $ — pas encore testé' if not qwen_tok else f'{qwen_tok:,} tokens de l’essai gratuit'} |

## Pour finir Qwen

1. Ajoute `DASHSCOPE_API_KEY=…` dans `.env` (`DASHSCOPE_BASE_URL` y est déjà).
2. Lance `python etude_modeles/video.py qwen` puis `python etude_modeles/rapport.py`. Les tableaux se complètent seuls.
""")
    out.close()
    print("ok", round(cout_t, 2), round(cout_t27, 2), sb, gen)
