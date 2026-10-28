"""Outils communs de l'étude « autres modèles » : les fournisseurs (Gemini, Groq, DeepSeek) derrière la même méthode
_generate_content que l'app, le budget, le contrôle des chiffres. Rien ici ne modifie un module de l'app."""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
sys.path.insert(0, RACINE)
os.chdir(RACINE)
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(RACINE, ".env"))
import requests  # noqa: E402
import ai_models  # noqa: E402
import gemini_ai_generator as gg  # noqa: E402

gg.USAGE_LOG = os.path.join(ICI, "usage_gemini.jsonl")       # le coût de l'étude, à part du vrai journal
BUDGET_GEMINI, BUDGET_DEEPSEEK = 0.50, 1.00
DEEPSEEK_PRIX = {"creux": (0.15, 0.6), "plein": (0.3, 1.2)}      # $/M (entrée hors cache, sortie), doc 2026-10-28
DEEPSEEK_LOG = os.path.join(ICI, "usage_deepseek.jsonl")


class BudgetDepasse(RuntimeError):
    pass


def depense_gemini() -> float:
    try:
        return sum(ai_models.cost(json.loads(l)) for l in open(gg.USAGE_LOG, encoding="utf-8") if l.strip())
    except OSError:
        return 0.0


def depense_deepseek() -> float:
    try:
        return sum(json.loads(l)["cout"] for l in open(DEEPSEEK_LOG, encoding="utf-8") if l.strip())
    except OSError:
        return 0.0


def heure_pleine_deepseek(t=None) -> bool:
    """Heures pleines DeepSeek (api-docs.deepseek.com/quick_start/pricing) : 01-04 h et 06-10 h UTC, lundi-vendredi."""
    t = t or datetime.now(timezone.utc)
    return t.weekday() < 5 and (1 <= t.hour < 4 or 6 <= t.hour < 10)


def lire_json(content: str):
    """Comme l'app (gemini_ai_generator) : JSON direct, sinon le premier {...}. Renvoie (réponse, 'direct'|'extrait'|'echec')."""
    try:
        return json.loads(content), "direct"
    except (json.JSONDecodeError, TypeError):
        m = re.search(r"\{.*\}", content or "", re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0)), "extrait"
            except json.JSONDecodeError:
                pass
    return {"raw_response": content, "parsing_error": True}, "echec"


class Gemini(gg.GeminiAIGenerator):
    """Le témoin : le vrai générateur de l'app. L'étape est donnée par le banc (l'app la lit dans la pile d'appels) :
    même modèle, même réflexion qu'en vrai."""
    nom = "gemini-flash"

    def __init__(self, etape: str, estimation: float):
        super().__init__(api_key=os.getenv("GEMINI_API_KEY"))
        self.etape, self.estimation, self.appels = etape, estimation, []

    def _generate_content(self, parts, max_tokens=1000, timeout=30, temperature=0.7, thinking=None):
        if depense_gemini() + self.estimation > BUDGET_GEMINI:
            raise BudgetDepasse(f"Gemini : déjà {depense_gemini():.3f} $")
        old = gg._asking_step
        gg._asking_step = lambda: self.etape
        t0 = time.time()
        try:
            r = super()._generate_content(parts, max_tokens=max_tokens, timeout=max(timeout, 120),
                                          temperature=temperature, thinking=thinking)
        finally:
            gg._asking_step = old
        last = json.loads(open(gg.USAGE_LOG, encoding="utf-8").readlines()[-1])
        json_etat = "echec" if (not isinstance(r, dict) or r.get("parsing_error") or "error" in r) else "direct"
        self.appels.append({"s": round(time.time() - t0, 1), "json": json_etat, "limite": 0, "attente_s": 0,
                            "tokens_entree": last.get("prompt", 0), "tokens_sortie": last.get("output", 0) + last.get("thoughts", 0),
                            "cout": round(ai_models.cost(last), 5), "erreur": r.get("error") if isinstance(r, dict) else None})
        return r


class Compatible:
    """Un fournisseur au format OpenAI (Groq, DeepSeek) : le MÊME texte de prompt, envoyé seul comme message."""

    def __init__(self, nom, url, cle, modele, max_sortie=None, champ_max="max_completion_tokens", extra=None):
        self.nom, self.url, self.cle, self.modele = nom, url, cle, modele
        self.max_sortie, self.champ_max, self.extra, self.appels = max_sortie, champ_max, extra or {}, []

    def _generate_content(self, parts, max_tokens=1000, timeout=30, temperature=0.7, thinking=None):
        texte = "\n".join(p["text"] for p in parts if "text" in p)
        if any("text" not in p for p in parts):
            raise ValueError("étape avec image ou vidéo : hors étude")
        if self.nom.startswith("deepseek"):
            if heure_pleine_deepseek():
                raise RuntimeError("DeepSeek : heure pleine, appel refusé par l'étude")
            if depense_deepseek() + 0.02 > BUDGET_DEEPSEEK:
                raise BudgetDepasse(f"DeepSeek : déjà {depense_deepseek():.3f} $")
        corps = {"model": self.modele, "messages": [{"role": "user", "content": texte}], "temperature": temperature,
                 self.champ_max: min(max_tokens, self.max_sortie or max_tokens),
                 "response_format": {"type": "json_object"}, **self.extra}
        t0, limite, attente, r = time.time(), 0, 0.0, None
        for _ in range(8):
            try:
                r = requests.post(self.url, headers={"Authorization": f"Bearer {self.cle}"}, json=corps,
                                  timeout=max(timeout, 180))
            except requests.RequestException as e:
                self.appels.append({"s": round(time.time() - t0, 1), "json": "echec", "limite": limite,
                                    "attente_s": round(attente), "erreur": str(e)[:200]})
                return {"error": str(e)}
            if r.status_code != 429:
                break
            limite += 1                               # une limite gratuite atteinte : on attend ce que l'API demande
            pause = min(float(r.headers.get("retry-after") or 20), 120)
            attente += pause
            time.sleep(pause)
        info = {"s": round(time.time() - t0, 1), "limite": limite, "attente_s": round(attente),
                "en_tetes": {k: v for k, v in r.headers.items() if "ratelimit" in k.lower()}}
        if r.status_code != 200:
            self.appels.append({**info, "json": "echec", "erreur": f"{r.status_code} {r.text[:300]}"})
            return {"error": f"API error: {r.status_code}"}
        data = r.json()
        u = data.get("usage") or {}
        content = data["choices"][0]["message"].get("content") or ""
        rep, etat = lire_json(content)
        info.update(json=etat, tokens_entree=u.get("prompt_tokens", 0), tokens_sortie=u.get("completion_tokens", 0),
                    fin=data["choices"][0].get("finish_reason"), erreur=None, cout=0.0)
        if self.nom.startswith("deepseek"):
            ent, sor = DEEPSEEK_PRIX["creux"]
            hit = u.get("prompt_cache_hit_tokens", 0)
            info["cout"] = round(((u.get("prompt_tokens", 0) - hit) * ent + hit * ent / 50 + u.get("completion_tokens", 0) * sor) / 1e6, 6)
            with open(DEEPSEEK_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps({"at": datetime.now().isoformat(timespec="seconds"), **u, "cout": info["cout"]}) + "\n")
        self.appels.append(info)
        return rep

    def call_gemini_api(self, prompt, max_tokens=1000, temperature=0.7, images=None):     # la Génération l'appelle ainsi
        return self._generate_content([{"text": prompt}], max_tokens, temperature=temperature)


def groq():
    return Compatible("groq-gpt-oss-120b", "https://api.groq.com/openai/v1/chat/completions",
                      os.getenv("GROQ_API_KEY"), "openai/gpt-oss-120b")


def deepseek():
    return Compatible("deepseek-flash", "https://api.deepseek.com/chat/completions", os.getenv("DEEPSEEK_API_KEY"),
                      "deepseek-flash", max_sortie=24000, champ_max="max_tokens")


# ------------------------------------------------------------------ les chiffres d'un texte (FR / AR)

FR = {"zero": 0, "zéro": 0, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9,
      "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16, "vingt": 20,
      "vingts": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60, "un": 1, "une": 1}
FR_MULT = {"cent": 100, "cents": 100, "mille": 1000, "million": 10**6, "millions": 10**6, "milliard": 10**9, "milliards": 10**9}
AR = {"واحد": 1, "واحدة": 1, "إحدى": 1, "أحد": 1, "احدى": 1, "اثنان": 2, "اثنين": 2, "اثنتان": 2, "ثلاث": 3, "ثلاثة": 3, "أربع": 4, "أربعة": 4, "خمس": 5,
      "خمسة": 5, "ست": 6, "ستة": 6, "سبع": 7, "سبعة": 7, "ثمان": 8, "ثماني": 8, "ثمانية": 8, "تسع": 9, "تسعة": 9,
      "عشر": 10, "عشرة": 10, "عشرون": 20, "عشرين": 20, "ثلاثون": 30, "ثلاثين": 30, "أربعون": 40, "أربعين": 40,
      "خمسون": 50, "خمسين": 50, "ستون": 60, "ستين": 60, "سبعون": 70, "سبعين": 70, "ثمانون": 80, "ثمانين": 80,
      "تسعون": 90, "تسعين": 90, "مئتين": 200, "مئتان": 200, "مائتين": 200, "مائتان": 200}
AR_MULT = {"مئة": 100, "مائة": 100, "ألف": 1000, "آلاف": 1000, "ألفا": 1000, "ألفين": 2000, "مليون": 10**6,
           "ملايين": 10**6, "مليار": 10**9}
CHIFFRES = re.compile(r"\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?")


def _mot_ar(w: str):
    for x in (w, w[1:] if w[:1] in "وبلك" else None, w[2:] if w[:2] in ("وب", "ول", "ال") else None, w[3:] if w[:3] in ("بال", "وال", "لل") else None):
        if x and (x in AR or x in AR_MULT):
            return x
        if x and x.endswith(("مئة", "مائة")) and x[:-3] in AR:          # ثلاثمئة
            return x
    return None


def nombres(texte: str) -> set:
    """Les nombres d'un texte, en chiffres ou en lettres (français, arabe) ; approximatif, pour repérer un chiffre
    qui n'est pas dans les faits."""
    t = (texte or "").translate(str.maketrans("٠١٢٣٤٥٦٧٨٩٫", "0123456789."))
    t = re.sub(r"pour\s*cent|بالمئة|بالمائة|في المئة|في المائة", " % ", t, flags=re.I)        # « pour cent » n'est pas 100
    out = set()
    for m in CHIFFRES.findall(t):
        try:
            out.add(float(re.sub(r"[   ]", "", m).replace(",", ".")))
        except ValueError:
            pass
    total, cur, vu = 0, 0, False
    for w in re.findall(r"[\w؀-ۿ]+", t.lower().replace("-", " ")) + ["."]:
        a = _mot_ar(w)
        if w in FR or w in FR_MULT or a:
            vu = True
            if w in FR:
                cur = cur - 4 + 80 if w.startswith("vingt") and cur % 100 == 4 else cur + FR[w]
            elif w in FR_MULT:
                k = FR_MULT[w]
                if k == 100:
                    cur = max(cur, 1) * 100
                else:
                    total, cur = total + max(cur, 1) * k, 0
            elif a in AR:
                cur += AR[a]
            elif a in AR_MULT:
                k = AR_MULT[a]
                if k == 100:
                    cur = max(cur, 1) * 100
                else:
                    total, cur = total + max(cur, 1) * (k if a != "ألفين" else 1000) * (1 if a != "ألفين" else 2), 0
            else:                                                # ثلاثمئة
                cur += AR[a[:-3]] * 100
            continue
        if w == "et" and vu:
            continue
        if vu and total + cur:
            out.add(float(total + cur))
        total, cur, vu = 0, 0, False
    return out


def chiffres_hors_faits(textes, faits) -> list:
    """Les nombres des textes (plus de 10, ou à virgule) qu'on ne retrouve dans aucun fait (à 1 % près)."""
    sources = set().union(*(nombres(f) for f in faits)) if faits else set()
    hors = []
    for t in textes:
        for n in sorted(nombres(t)):
            if (n > 10 or n != int(n)) and not any(abs(n - s) <= 0.01 * max(abs(s), 1) for s in sources):
                hors.append((n, t))
    return hors


def ecrire(nom: str, data):
    with open(os.path.join(ICI, "resultats", nom), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
