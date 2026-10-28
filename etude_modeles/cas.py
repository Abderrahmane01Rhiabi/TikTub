"""Copie les cas réels de l'étude (lecture seule de la base) dans etude_modeles/cas/. Rien n'est écrit ailleurs."""
import json, os, sqlite3

ICI = os.path.dirname(os.path.abspath(__file__))
ADAPT = ["ad_20261027_195556_6dea",    # FR, mode Idée (chameau)
         "ad_20261027_191758_b571",    # AR, mode Idée (glace de mer)
         "ad_20261027_195556_8e50",    # AR, mode Idée (sang du chameau)
         "ad_20261026_232951_9882",    # AR, d'après un Short modèle (cordes)
         "ad_20261026_232951_64b4"]    # FR, d'après un Short modèle (cordes)
GEN_CHAINE = "lungtemotivates"         # la seule chaîne qui utilise la Génération

if __name__ == "__main__":
    c = sqlite3.connect(f"file:{os.path.join(ICI, '..', 'database', 'tiktub.db')}?mode=ro", uri=True)
    for pid in ADAPT:
        d = json.loads(c.execute("select data from adaptations where project_id=?", (pid,)).fetchone()[0])
        cas = {"id": pid, "codes": [t["language"] for t in d["targets"]], "reference": d["reference"],
               "angle": d.get("angle"), "storyboard_en_base": d.get("storyboard")}
        json.dump(cas, open(os.path.join(ICI, "cas", f"{pid}.json"), "w"), ensure_ascii=False, indent=1)
    vids = [json.loads(x) for (x,) in c.execute("select data from videos where channel=?", (GEN_CHAINE,))]
    gen = sorted((v for v in vids if v.get("source") == "generated" and v.get("title")), key=lambda v: v.get("updated_at") or "", reverse=True)
    with_plan = sorted((v for v in gen if v.get("script_plan") and v.get("script_text")), key=lambda v: v.get("added_at") or "", reverse=True)[:5]
    profile = json.load(open(os.path.join(ICI, "..", "channels", GEN_CHAINE, "profile.json"), encoding="utf-8"))
    for v in with_plan:
        others = [{k: o.get(k) for k in ("video_id", "title", "script_text", "script_plan", "script_format", "updated_at")}
                  for o in gen if o["video_id"] != v["video_id"] and (o.get("added_at") or "") < (v.get("added_at") or "~")]
        insp = None
        if v.get("inspired_by"):
            w = next((x for x in vids if x.get("video_id") == v["inspired_by"]), None)
            if w and w.get("script_text"):
                insp = {"title": w.get("title"), "script_text": w.get("script_text")}
        cas = {"id": v["video_id"], "profile": profile, "plan": v["script_plan"], "others": others,
               "recent_titles": [o["title"] for o in others[:15]], "inspiration": insp,
               "en_base": {"title": v.get("title"), "script_text": v.get("script_text")}}
        json.dump(cas, open(os.path.join(ICI, "cas", f"gen_{v['video_id']}.json"), "w"), ensure_ascii=False, indent=1)
    print(sorted(os.listdir(os.path.join(ICI, "cas"))))
