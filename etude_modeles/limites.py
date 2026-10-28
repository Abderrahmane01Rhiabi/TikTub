"""Les modèles et les limites réelles du compte (en-têtes des API), avec un appel minuscule par modèle."""
import json, os, time, requests
from dotenv import load_dotenv
load_dotenv()
G, M = os.environ["GROQ_API_KEY"], os.environ["MISTRAL_API_KEY"]
out = {}
r = requests.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {G}"}, timeout=30)
out["groq_modeles"] = sorted((m["id"], m.get("context_window")) for m in r.json().get("data", []) if r.ok) if r.ok else r.text[:300]
r = requests.get("https://api.mistral.ai/v1/models", headers={"Authorization": f"Bearer {M}"}, timeout=30)
out["mistral_modeles"] = sorted({m["id"] for m in r.json().get("data", [])} ) if r.ok else r.text[:300]
print(json.dumps(out, indent=0, ensure_ascii=False)[:4000])
def essai(url, key, model):
    t = time.time()
    r = requests.post(url, headers={"Authorization": f"Bearer {key}"}, json={"model": model, "max_tokens": 5,
                      "messages": [{"role": "user", "content": "Dis juste: ok"}]}, timeout=60)
    h = {k: v for k, v in r.headers.items() if "ratelimit" in k.lower()}
    return {"modele": model, "statut": r.status_code, "s": round(time.time() - t, 2), "entetes": h, "erreur": None if r.ok else r.text[:200]}
res = []
for m in ("openai/gpt-oss-120b", "qwen/qwen3.8-27b", "llama-3.3-70b-versatile", "moonshotai/kimi-k2-instruct"):
    res.append(essai("https://api.groq.com/openai/v1/chat/completions", G, m))
for m in ("mistral-large-latest", "mistral-medium-latest", "magistral-medium-latest"):
    res.append(essai("https://api.mistral.ai/v1/chat/completions", M, m))
for x in res: print(json.dumps(x, ensure_ascii=False))
json.dump({**out, "essais": res}, open("etude_modeles/limites.json", "w"), ensure_ascii=False, indent=1)
