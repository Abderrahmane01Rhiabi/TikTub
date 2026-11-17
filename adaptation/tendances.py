"""
Tendances (labs of 2026-11-06, the user's decisions; coded 2026-11-17): subjects that work right now for a channel,
found from what people watch and search — never invented — then handed to « Idée d'abord ».

  veille      one small text call reads the channel's objective (its profile, family, language) -> the country, the
              languages, 4 YouTube searches, 6 autocomplete seeds, 2 news searches
  signaux     free or cheap, each kept with its link:
                - the Shorts most watched in the last 7 days for those searches (YouTube Data API, the channel's own
                  connection: ~100 units a search, 4 searches; then their views, 1 unit)
                - the country's most popular videos (1 unit)
                - Google News RSS of the country (Morocco in French: « hl=fr gl=MA » — in Arabic it gives Egypt) and
                  for the 2 news searches
                - Google Trends RSS of the country (mostly football in Morocco)
                - YouTube's autocomplete for the 6 seeds (what people type)
              and the channel's own last titles (never the same subject twice)
  sujets      one call: 5 subjects ONLY from those signals ({titre, idee, pourquoi, signaux, nouveaute}); a fact that
              is in no signal is never written
  cache       a channel is searched at most once in 6 hours (the user's rule): the last result is shown again
"""

import html
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from urllib.parse import quote

import requests

CACHE_DIR = os.path.join("temp", "tendances")
EVERY_S = 6 * 3600                      # the same channel: once in 6 hours
UA = {"User-Agent": "Mozilla/5.0 (TikTub; personal use)"}
SEARCHES, SEEDS, NEWS = 4, 6, 2
DAYS = 7


class TendancesError(RuntimeError):
    pass


def _gemini():
    from adaptation.script import _gemini as g
    return g()


# ---------------------------------------------------------------- the channel

def channel_brief(channel: str) -> Dict:
    """What the channel is about, as the app knows it: {nom, objectif, langue, dialecte, famille, titres_recents}."""
    from channel_manager import ChannelManager
    from adaptation import settings
    cm = ChannelManager()
    ch = next((c for c in cm.list_channels() if c["name"] == channel), None)
    if not ch:
        raise TendancesError("Chaîne inconnue.")
    prof = cm.get_channel_profile(channel) or {}
    s = settings.channel_settings(prof)
    return {"nom": ch.get("display_name") or channel, "objectif": (prof.get("ai_style_prompt") or ch.get("description") or "")[:1200],
            "langue": s.get("language"), "dialecte": s.get("dialecte"), "famille": s.get("famille_recit"),
            "titres_recents": recent_titles(channel)}


def recent_titles(channel: str, n: int = 30) -> List[str]:
    """The channel's last subjects: its published videos and its projects (never the same subject twice)."""
    out = []
    try:
        import db
        for p in sorted(db.list_adaptations(), key=lambda p: p.get("created_at") or "", reverse=True):
            if any(t.get("channel") == channel for t in p.get("targets") or []):
                s = (p.get("reference") or {}).get("sujet") or p.get("idee")
                if s:
                    out.append(str(s)[:120])
        from url_manager import URLManager
        for v in URLManager().list_videos(channel=channel)[:n]:
            t = ((v.get("ai_data") or {}).get("optimized_title") or v.get("title") or "")
            if t:
                out.append(t[:120])
    except Exception:
        pass
    return list(dict.fromkeys(out))[:n]


VEILLE_PROMPT = """Une chaine YouTube Shorts cherche des sujets qui marchent EN CE MOMENT. Sa ligne :
Nom : {nom}. Langue : {langue}{dialecte}. Famille de recit : {famille}.
Objectif : {objectif}
Ecris son plan de veille :
- "pays" : le code pays (2 lettres) de son public principal (MA pour une chaine marocaine) ;
- "hl" : la langue des actualites a lire pour ce pays (pour le Maroc : "fr" — en arabe, Google donne l'Egypte) ;
- "recherches" : {searches} recherches YouTube courtes (2 a 4 mots), dans la langue de son public, sur ses themes ;
- "graines" : {seeds} debuts de recherche (1 a 2 mots) pour l'autocompletion YouTube, dans la langue de son public ;
- "actualites" : {news} recherches Google Actualites (2 a 4 mots) sur ses themes, dans la langue "hl".
JSON uniquement : {{"pays": "MA", "hl": "fr", "recherches": [""], "graines": [""], "actualites": [""]}}"""


def veille(brief: Dict, gemini=None) -> Dict:
    from adaptation.langs import lang as lang_of
    r = (gemini or _gemini())._generate_content([{"text": VEILLE_PROMPT.format(
        nom=brief["nom"], langue=lang_of(brief["langue"] or "fr")["label"],
        dialecte=f" ({brief['dialecte']})" if brief.get("dialecte") else "", famille=brief.get("famille") or "?",
        objectif=brief.get("objectif") or "?", searches=SEARCHES, seeds=SEEDS, news=NEWS)}],
        max_tokens=2000, timeout=60, temperature=0.3)
    if not isinstance(r, dict):
        raise TendancesError("L'IA n'a pas pu lire la ligne de la chaîne.")
    clean = lambda xs, n: [" ".join(str(x).split())[:60] for x in (xs or []) if str(x).strip()][:n]
    pays = str(r.get("pays") or "MA").upper()[:2]
    return {"pays": pays if re.fullmatch(r"[A-Z]{2}", pays) else "MA", "hl": str(r.get("hl") or "fr")[:5],
            "recherches": clean(r.get("recherches"), SEARCHES), "graines": clean(r.get("graines"), SEEDS),
            "actualites": clean(r.get("actualites"), NEWS)}


# ---------------------------------------------------------------- the signals

def _youtube(channel: str):
    from youtube_uploader import authenticate_youtube
    yt = authenticate_youtube(channel, interactive=False)
    if yt is None:
        raise TendancesError("La chaîne n'est pas connectée à YouTube (Réglages → Chaînes).")
    return yt


def youtube_shorts(yt, query: str, pays: str, langue: str, days: int = DAYS, n: int = 10) -> List[Dict]:
    """The Shorts most watched in the last days for this search (≈100 quota units)."""
    after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = yt.search().list(part="snippet", q=query, type="video", videoDuration="short", order="viewCount",
                         publishedAfter=after, regionCode=pays, relevanceLanguage=langue, maxResults=n).execute()
    return [{"source": "youtube", "recherche": query, "id": it["id"]["videoId"],
             "titre": html.unescape(it["snippet"]["title"]), "chaine": it["snippet"].get("channelTitle"),
             "date": it["snippet"].get("publishedAt", "")[:10], "lien": f"https://www.youtube.com/shorts/{it['id']['videoId']}"}
            for it in r.get("items") or [] if it.get("id", {}).get("videoId")]


def youtube_popular(yt, pays: str, n: int = 20) -> List[Dict]:
    """The country's most popular videos right now (1 unit)."""
    r = yt.videos().list(part="snippet,statistics", chart="mostPopular", regionCode=pays, maxResults=n).execute()
    return [{"source": "populaire", "id": it["id"], "titre": html.unescape(it["snippet"]["title"]),
             "chaine": it["snippet"].get("channelTitle"), "vues": int((it.get("statistics") or {}).get("viewCount") or 0),
             "lien": f"https://www.youtube.com/watch?v={it['id']}"} for it in r.get("items") or []]


def add_views(yt, items: List[Dict]) -> None:
    ids = [x["id"] for x in items if x.get("source") == "youtube"][:50]
    if not ids:
        return
    r = yt.videos().list(part="statistics", id=",".join(ids)).execute()
    views = {it["id"]: int((it.get("statistics") or {}).get("viewCount") or 0) for it in r.get("items") or []}
    for x in items:
        if x.get("id") in views:
            x["vues"] = views[x["id"]]


def _rss(url: str, source: str, n: int = 15) -> List[Dict]:
    r = requests.get(url, headers=UA, timeout=20)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    out = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        if not title:
            continue
        x = {"source": source, "titre": html.unescape(title), "lien": (it.findtext("link") or "").strip(),
             "date": (it.findtext("pubDate") or "")[:16]}
        traffic = next((c.text for c in it if c.tag.endswith("approx_traffic")), None)
        if traffic:
            x["trafic"] = traffic
        out.append(x)
        if len(out) >= n:
            break
    return out


def google_news(pays: str, hl: str, query: Optional[str] = None) -> List[Dict]:
    base = "https://news.google.com/rss"
    path = f"/search?q={quote(query)}+when:7d&" if query else "?"
    return _rss(f"{base}{path}hl={hl}&gl={pays}&ceid={pays}:{hl}", "actualites" + (f":{query}" if query else ""))


def google_trends(pays: str) -> List[Dict]:
    return _rss(f"https://trends.google.com/trending/rss?geo={pays}", "trends", n=20)


def autocomplete(seed: str, hl: str) -> List[str]:
    r = requests.get("https://suggestqueries.google.com/complete/search", headers=UA, timeout=15,
                     params={"client": "firefox", "ds": "yt", "q": seed, "hl": hl})
    try:
        return [str(x) for x in r.json()[1]][:10]
    except (ValueError, IndexError, TypeError):
        return []


def signals(channel: str, plan: Dict, langue: str, report=None) -> Dict:
    """Every signal of the plan, each source on its own (one failing never stops the others): {items, suggestions,
    erreurs}."""
    report = report or (lambda ph: None)
    items, sugg, errors = [], {}, []
    try:
        yt = _youtube(channel)
        for q in plan["recherches"]:
            report(f"YouTube : {q}")
            try:
                items += youtube_shorts(yt, q, plan["pays"], (langue or "fr")[:2])
            except Exception as e:
                errors.append(f"YouTube « {q} » : {str(e)[:120]}")
        try:
            add_views(yt, items)
        except Exception:
            pass
        try:
            items += youtube_popular(yt, plan["pays"])
        except Exception as e:
            errors.append(f"YouTube populaires : {str(e)[:120]}")
    except TendancesError as e:
        errors.append(str(e))
    report("Google Actualités et Google Trends")
    for q in [None] + plan["actualites"]:
        try:
            items += google_news(plan["pays"], plan["hl"], q)
        except Exception as e:
            errors.append(f"Google Actualités {q or ''} : {str(e)[:100]}")
    try:
        items += google_trends(plan["pays"])
    except Exception as e:
        errors.append(f"Google Trends : {str(e)[:100]}")
    report("suggestions de recherche YouTube")
    for s in plan["graines"]:
        try:
            sugg[s] = autocomplete(s, (langue or "fr")[:2])
        except Exception:
            pass
        time.sleep(0.3)
    return {"items": items, "suggestions": sugg, "erreurs": errors}


# ---------------------------------------------------------------- the subjects

SUJETS_PROMPT = """Tu es redacteur en chef d'une chaine YouTube Shorts. Sa ligne : {objectif}
Langue des videos : {langue}{dialecte}. Famille de recit : {famille}.
Ses derniers sujets (NE JAMAIS les refaire, ni un sujet presque pareil) :
{recents}

Voici les SIGNAUX de cette semaine (numerotes) — ce que les gens regardent, lisent et cherchent :
{signaux}
Ce que les gens tapent sur YouTube (autocompletion) :
{suggestions}

Propose les 5 MEILLEURS sujets de Short pour cette chaine, a partir de ces signaux SEULEMENT :
- un sujet qui monte (plusieurs signaux, beaucoup de vues, recent) et qui colle a la ligne de la chaine ;
- AUCUN fait qui n'est pas dans un signal (pas de chiffre, de date ou de nom invente) : les faits seront cherches
  ensuite ; dis seulement de quoi parler et pourquoi maintenant ;
- varie les sujets (pas 5 fois le meme evenement).
Pour chacun :
"titre" : 4 a 10 mots, dans la langue des videos ;
"idee" : une phrase en francais pour lancer « Idee d'abord » (le sujet + l'angle : ce que le Short explique ou raconte) ;
"pourquoi" : en francais, 1 phrase : pourquoi maintenant (quels signaux, combien de vues) ;
"signaux" : les numeros des signaux qui le soutiennent ;
"force" : 1-10, a quel point il monte et colle a la chaine.
JSON uniquement : {{"sujets": [{{"titre": "", "idee": "", "pourquoi": "", "signaux": [1], "force": 7}}]}}"""


def _signal_lines(items: List[Dict], n: int = 90) -> List[Dict]:
    """The signals shown to the AI: the most watched Shorts first, then news and trends (90 at most)."""
    yt = sorted((x for x in items if x["source"] == "youtube"), key=lambda x: -(x.get("vues") or 0))
    pop = [x for x in items if x["source"] == "populaire"]
    rest = [x for x in items if x["source"] not in ("youtube", "populaire")]
    seen, out = set(), []
    for x in yt[:40] + rest[:35] + pop[:15]:
        k = x["titre"].lower()
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out[:n]


def subjects(brief: Dict, sig: Dict, gemini=None) -> List[Dict]:
    from adaptation.langs import lang as lang_of
    lines = _signal_lines(sig["items"])
    def line(k, x):
        extra = [f"{x['vues']:,} vues".replace(",", " ")] if x.get("vues") else []
        extra += [x["trafic"]] if x.get("trafic") else []
        extra += [x["date"]] if x.get("date") else []
        return f"{k}. [{x['source']}] {x['titre']}" + (f" ({', '.join(extra)})" if extra else "")
    r = (gemini or _gemini())._generate_content([{"text": SUJETS_PROMPT.format(
        objectif=brief.get("objectif") or brief["nom"], langue=lang_of(brief["langue"] or "fr")["label"],
        dialecte=f" ({brief['dialecte']})" if brief.get("dialecte") else "", famille=brief.get("famille") or "?",
        recents="\n".join(f"- {t}" for t in brief["titres_recents"][:30]) or "(aucun)",
        signaux="\n".join(line(k, x) for k, x in enumerate(lines, 1)) or "(aucun)",
        suggestions="\n".join(f"- {s} → {', '.join(v[:8])}" for s, v in sig["suggestions"].items() if v) or "(aucune)")}],
        max_tokens=6000, timeout=120, temperature=0.4)
    out = []
    for x in (r or {}).get("sujets") or [] if isinstance(r, dict) else []:
        try:
            idx = [int(i) for i in x.get("signaux") or [] if 1 <= int(i) <= len(lines)]
        except (TypeError, ValueError):
            idx = []
        if not idx or not str(x.get("idee") or "").strip():
            continue                    # a subject no signal supports is never shown
        out.append({"titre": str(x.get("titre") or "")[:120], "idee": str(x["idee"])[:400],
                    "pourquoi": str(x.get("pourquoi") or "")[:300],
                    "force": max(1, min(10, int(x.get("force") or 5))) if str(x.get("force") or "").isdigit() else 5,
                    "signaux": [{k: lines[i - 1].get(k) for k in ("source", "titre", "lien", "vues", "trafic", "date")}
                                for i in idx[:6]]})
    if not out:
        raise TendancesError("L'IA n'a trouvé aucun sujet soutenu par les signaux : réessaie plus tard.")
    return sorted(out, key=lambda x: -x["force"])[:5]


# ---------------------------------------------------------------- the whole search

def _cache_path(channel: str) -> str:
    return os.path.join(CACHE_DIR, f"{channel}.json")


def last(channel: str) -> Optional[Dict]:
    try:
        with open(_cache_path(channel), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def search(channel: str, force: bool = False, report=None, gemini=None) -> Dict:
    """The 5 subjects for this channel: {chaine, quand, plan, sujets, erreurs, nb_signaux, deja}. Within 6 hours of the
    last search, that one is given back (deja=True) — the user's rule, the quota and the bill."""
    old = last(channel)
    if old and not force and time.time() - old.get("ts", 0) < EVERY_S:
        return {**old, "deja": True}
    brief = channel_brief(channel)
    plan = veille(brief, gemini)
    sig = signals(channel, plan, brief["langue"], report)
    if not sig["items"]:
        raise TendancesError("Aucun signal récolté : " + "; ".join(sig["erreurs"])[:300])
    res = {"chaine": channel, "ts": time.time(), "quand": datetime.now().strftime("%d/%m à %H:%M"), "plan": plan,
           "sujets": subjects(brief, sig, gemini), "erreurs": sig["erreurs"], "nb_signaux": len(sig["items"])}
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = _cache_path(channel) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _cache_path(channel))
    return {**res, "deja": False}
