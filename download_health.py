#!/usr/bin/env python3
"""
Download health — is downloading still working from here?

YouTube and TikTok change without warning; yt-dlp (and its JavaScript
solver yt-dlp-ejs) follow within days. Without a check, a break shows only in
the middle of a project ("le téléchargement a échoué"). So, once a day:
three seconds of three test videos, by the app's own download path —

    a plain YouTube video            the first YouTube video ever: never removed
    a YouTube video "blocked" here   it needs the PO tokens (bgutil) to come down
    a TikTok video

The result is on the home page. "Mettre à jour yt-dlp" installs the newest
yt-dlp + yt-dlp-ejs, checks again, and puts the old ones back by itself if
fewer tests pass (a copy of their files is taken first: a nightly build
can't always be reinstalled from PyPI). bgutil is never updated here: its
plugin and its local server must keep the same version (see requirements.txt).

The check runs in a separate Python process: it tests the version installed
on disk, not the one already loaded in the server (a server keeps the old
yt-dlp until it is restarted).
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

STATE_FILE = os.path.join("database", "download_health.json")
BACKUP_DIR = os.path.join("database", "yt_dlp_backup")
PACKAGES = ("yt-dlp", "yt-dlp-ejs")       # what "Mettre à jour" updates
SHOWN = PACKAGES + ("bgutil-ytdlp-pot-provider",)
EVERY = timedelta(hours=24)
KEEP = 30
TESTS = [
    {"label": "YouTube", "url": "https://www.youtube.com/watch?v=jNQXAC9IVRw"},
    # refused to the web client from here ("This video is not available"), downloaded with a PO token
    {"label": "YouTube (jetons bgutil)", "url": "https://www.youtube.com/watch?v=wtwaCCK4_fk"},
    {"label": "TikTok", "url": "https://www.tiktok.com/@scout2015/video/6718335390845095173"},
]
ROOT = os.path.dirname(os.path.abspath(__file__))


# ------------------------------------------------------------------ the check itself

def versions() -> Dict[str, Optional[str]]:
    from importlib import metadata
    out = {}
    for name in SHOWN:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = None
    return out


def _pot_server_up(port: int = 4416) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except OSError:
        return False


def run_tests(tests: List[Dict] = None) -> Dict:
    """The three downloads, in this process. Each result: ok, seconds, height or the error."""
    from adaptation import sources
    try:
        sources.start_pot_server()
    except Exception:
        pass
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        for k, t in enumerate(tests or TESTS):
            t0 = time.time()
            try:
                path = sources.download(t["url"], tmp, f"t{k}", [[1.0, 4.0]])
                info = sources.probe(path)
                results.append({**t, "ok": True, "secondes": round(time.time() - t0, 1), "hauteur": info["h"]})
            except Exception as e:
                results.append({**t, "ok": False, "secondes": round(time.time() - t0, 1), "erreur": str(e)[:300]})
    return {"le": datetime.now().isoformat(timespec="seconds"), "resultats": results,
            "ok": sum(r["ok"] for r in results), "total": len(results),
            "versions": versions(), "bgutil_actif": _pot_server_up()}


def check_in_subprocess(timeout: int = 300) -> Dict:
    """run_tests in a fresh Python: what is installed on disk, not what the server has loaded."""
    env = {**os.environ, "PYTHONPATH": ROOT + os.pathsep + os.environ.get("PYTHONPATH", "")}
    try:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "download_health.py"), "--json"], cwd=os.getcwd(),
                           env=env, capture_output=True, text=True, timeout=timeout)
        line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("{")), None)
        if line:
            return json.loads(line)
        err = (r.stderr or r.stdout).strip()[-300:]
    except subprocess.TimeoutExpired:
        err = f"le contrôle a dépassé {timeout} s"
    return {"le": datetime.now().isoformat(timespec="seconds"), "resultats": [], "ok": 0, "total": len(TESTS),
            "versions": versions(), "bgutil_actif": _pot_server_up(), "erreur": err}


# ------------------------------------------------------------------ what is kept

def load() -> Dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(state: Dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_FILE)


def record(result: Dict, why: str = "auto") -> Dict:
    state = load()
    state["dernier"] = {**result, "pourquoi": why}
    if result.get("ok") == result.get("total") and result.get("total"):
        state["dernier_ok"] = result["le"]
    elif "casse_depuis" not in state or state.get("dernier_ok", "") > state.get("casse_depuis", ""):
        state["casse_depuis"] = result["le"]          # the first failed check after a good one
    state["historique"] = ([{"le": result["le"], "ok": result.get("ok"), "total": result.get("total")}]
                           + state.get("historique", []))[:KEEP]
    _save(state)
    return state


def check_and_record(why: str = "auto") -> Dict:
    return record(check_in_subprocess(), why)


def is_due(now: Optional[datetime] = None) -> bool:
    last = (load().get("dernier") or {}).get("le")
    if not last:
        return True
    try:
        return (now or datetime.now()) - datetime.fromisoformat(last) >= EVERY
    except ValueError:
        return True


# ------------------------------------------------------------------ update, with a way back

def _site_files(name: str) -> List[str]:
    """The files of an installed package, relative to site-packages."""
    from importlib import metadata
    dist = metadata.distribution(name)
    return [str(f) for f in dist.files or []]


def _site_root(name: str) -> str:
    from importlib import metadata
    return str(metadata.distribution(name).locate_file(""))


def _copy_installed(dest: str) -> Dict[str, str]:
    """A copy of the installed yt-dlp + yt-dlp-ejs files, to put them back.
    A package also owns files outside site-packages (bin/yt-dlp, its shell
    completions: "../../../bin/yt-dlp"): every file is kept INSIDE dest under
    a number, a manifest says where it goes back. Returns {package: version}."""
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(os.path.join(dest, "files"))
    kept, where = {}, {}
    for name in PACKAGES:
        v = versions().get(name)
        if not v:
            continue
        root = _site_root(name)
        for rel in _site_files(name):
            src = os.path.normpath(os.path.join(root, rel))
            if os.path.isfile(src) and "__pycache__" not in rel:
                key = str(len(where))
                shutil.copy2(src, os.path.join(dest, "files", key))
                where[key] = src
        kept[name] = v
    with open(os.path.join(dest, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"versions": kept, "files": where}, f, ensure_ascii=False)
    return kept


def _put_back(backup: str) -> None:
    """The copied versions back in place: the new ones removed, the old files copied where they were."""
    with open(os.path.join(backup, "manifest.json"), encoding="utf-8") as f:
        where = json.load(f)["files"]
    _pip("uninstall", "-y", *PACKAGES)
    for key, target in where.items():
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(os.path.join(backup, "files", key), target)


def _pip(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "pip", "--disable-pip-version-check", "-q", *args],
                          capture_output=True, text=True, timeout=600)


def update(check=check_in_subprocess, pip=_pip, put_back=_put_back, copy=_copy_installed) -> Dict:
    """Newest yt-dlp + yt-dlp-ejs; kept only if at least as many tests pass as before."""
    before = check()
    old = copy(BACKUP_DIR)
    r = pip("install", "-U", "--pre", *PACKAGES)
    if r.returncode != 0:
        put_back(BACKUP_DIR)
        out = {"fait": False, "annule": True, "avant": old, "apres": old, "ok_avant": before["ok"],
               "message": "La mise à jour n'a pas pu s'installer ; rien n'a changé.", "detail": (r.stderr or "")[-300:]}
        record(before, "mise à jour échouée")
        return out
    after = check()
    new = after.get("versions") or {}
    if after["ok"] < before["ok"]:
        put_back(BACKUP_DIR)
        again = check()
        record(again, "mise à jour annulée")
        return {"fait": False, "annule": True, "avant": old, "apres": new, "ok_avant": before["ok"], "ok_apres": after["ok"],
                "message": f"La nouvelle version marchait moins bien ({after['ok']}/{after['total']} au lieu de "
                           f"{before['ok']}/{before['total']}) : l'ancienne est remise."}
    record(after, "mise à jour")
    changed = {k: (old.get(k), new.get(k)) for k in PACKAGES if old.get(k) != new.get(k)}
    return {"fait": True, "annule": False, "avant": old, "apres": new, "ok_avant": before["ok"], "ok_apres": after["ok"],
            "change": bool(changed), "redemarrer": bool(changed),
            "message": ("Mis à jour : " + ", ".join(f"{k} {a} → {b}" for k, (a, b) in changed.items())
                        + ". Redémarre le serveur pour l'utiliser.") if changed else "Déjà à jour."}


if __name__ == "__main__":
    if "--json" in sys.argv:
        print(json.dumps(run_tests(), ensure_ascii=False))
    else:
        res = run_tests()
        for t in res["resultats"]:
            print(("✅" if t["ok"] else "❌"), t["label"], t.get("secondes"), "s", t.get("hauteur") or t.get("erreur", ""))
        print(f"{res['ok']}/{res['total']}", res["versions"], "bgutil", "actif" if res["bgutil_actif"] else "arrêté")
