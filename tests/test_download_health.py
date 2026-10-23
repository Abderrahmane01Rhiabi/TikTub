"""Download health: the daily check, what is kept, and an update of yt-dlp
that puts the old one back when it works less well."""

import json
import os
import subprocess
from datetime import datetime, timedelta

import pytest

import download_health as dh


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(dh, "STATE_FILE", str(tmp_path / "health.json"))
    monkeypatch.setattr(dh, "BACKUP_DIR", str(tmp_path / "backup"))
    return tmp_path


def result(ok, total=3, at="2026-10-23T10:00:00"):
    return {"le": at, "ok": ok, "total": total, "resultats": [], "versions": {"yt-dlp": "1"}}


def test_a_break_is_dated_from_the_first_failed_check(state):
    dh.record(result(3, at="2026-10-20T10:00:00"))
    dh.record(result(2, at="2026-10-21T10:00:00"))
    st = dh.record(result(1, at="2026-10-22T10:00:00"))
    assert st["casse_depuis"] == "2026-10-21T10:00:00" and st["dernier_ok"] == "2026-10-20T10:00:00"
    dh.record(result(3, at="2026-10-23T10:00:00"))
    st = dh.record(result(0, at="2026-10-24T10:00:00"))
    assert st["casse_depuis"] == "2026-10-24T10:00:00"                  # a new break, not the old one
    assert [h["ok"] for h in st["historique"]] == [0, 3, 1, 2, 3]


def test_the_check_is_due_once_a_day(state):
    assert dh.is_due()
    dh.record(result(3, at=datetime.now().isoformat(timespec="seconds")))
    assert not dh.is_due()
    assert dh.is_due(datetime.now() + timedelta(hours=25))


def test_the_check_reads_what_the_separate_process_printed(monkeypatch):
    out = json.dumps(result(3))
    monkeypatch.setattr(dh.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "noise\n" + out + "\n", ""))
    assert dh.check_in_subprocess()["ok"] == 3
    monkeypatch.setattr(dh.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "Traceback: boom"))
    r = dh.check_in_subprocess()
    assert r["ok"] == 0 and "boom" in r["erreur"]


class Calls:
    def __init__(self, oks, pip_code=0):
        self.oks, self.pip_code, self.put_back, self.pips = list(oks), pip_code, 0, []

    def check(self):
        ok = self.oks.pop(0)
        return {**result(ok), "versions": {"yt-dlp": "new" if self.pips else "old", "yt-dlp-ejs": "0.8.0"}}

    def pip(self, *args):
        self.pips.append(args)
        return subprocess.CompletedProcess(args, self.pip_code, "", "no network")

    def back(self, folder):
        self.put_back += 1

    def copy(self, folder):
        return {"yt-dlp": "old", "yt-dlp-ejs": "0.8.0"}


def test_an_update_that_works_less_well_is_undone(state):
    c = Calls([3, 2, 3])
    out = dh.update(check=c.check, pip=c.pip, put_back=c.back, copy=c.copy)
    assert out["annule"] and not out["fait"] and c.put_back == 1
    assert "2/3 au lieu de 3/3" in out["message"]
    assert dh.load()["dernier"]["pourquoi"] == "mise à jour annulée"


def test_an_update_that_works_as_well_is_kept_and_asks_for_a_restart(state):
    c = Calls([2, 3])
    out = dh.update(check=c.check, pip=c.pip, put_back=c.back, copy=c.copy)
    assert out["fait"] and out["redemarrer"] and c.put_back == 0
    assert "yt-dlp old → new" in out["message"]


def test_an_update_that_cannot_install_changes_nothing(state):
    c = Calls([3], pip_code=1)
    out = dh.update(check=c.check, pip=c.pip, put_back=c.back, copy=c.copy)
    assert out["annule"] and c.put_back == 1 and "rien n'a changé" in out["message"]


def test_the_copy_puts_the_old_files_back(tmp_path, monkeypatch):
    site = tmp_path / "site"
    (site / "yt_dlp").mkdir(parents=True)
    (site / "yt_dlp" / "__init__.py").write_text("old")
    (site / "yt_dlp-1.dist-info").mkdir()
    (site / "yt_dlp-1.dist-info" / "METADATA").write_text("Version: 1")
    monkeypatch.setattr(dh, "_site_root", lambda name: str(site))
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "yt-dlp").write_text("old script")
    monkeypatch.setattr(dh, "_site_files", lambda name: ["yt_dlp/__init__.py", "yt_dlp-1.dist-info/METADATA", "../bin/yt-dlp"]
                        if name == "yt-dlp" else [])
    monkeypatch.setattr(dh, "versions", lambda: {"yt-dlp": "1", "yt-dlp-ejs": None})
    kept = dh._copy_installed(str(tmp_path / "backup"))
    assert kept == {"yt-dlp": "1"}
    (site / "yt_dlp" / "__init__.py").write_text("new, broken")         # the update replaced it
    monkeypatch.setattr(dh, "_pip", lambda *a: subprocess.CompletedProcess(a, 0, "", ""))
    dh._put_back(str(tmp_path / "backup"))
    assert (site / "yt_dlp" / "__init__.py").read_text() == "old"
    assert (site / "yt_dlp-1.dist-info" / "METADATA").read_text() == "Version: 1"
    assert (tmp_path / "bin" / "yt-dlp").read_text() == "old script"     # outside site-packages: back too
    backup = tmp_path / "backup"
    assert all(str(p).startswith(str(backup)) for p in backup.rglob("*"))   # and the copy never wrote outside it


def test_the_api(client, project, monkeypatch, state):
    monkeypatch.setattr(dh, "check_in_subprocess", lambda timeout=300: result(3, at=datetime.now().isoformat()))
    assert client.get("/api/health/downloads").json().get("dernier") is None
    r = client.post("/api/health/downloads/check").json()
    assert r["dernier"]["ok"] == 3 and r["dernier"]["pourquoi"] == "à la demande" and "yt-dlp" in r["versions"]
    project.add_video("v1", status="downloading")
    r = client.post("/api/health/downloads/update")
    assert r.status_code == 409 and "import" in r.json()["detail"]     # never under a running download
