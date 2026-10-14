"""Daily backups: what's inside, retention, restore (undoable)."""

import json
import os
import zipfile
from datetime import datetime, timedelta

import pytest

import backup
import db


def make_channel(project, name="chanA"):
    d = project.add_channel(name)
    (d / "profile.json").write_text(json.dumps({"display_name": name}))
    (d / "token.json").write_text("SECRET-TOKEN")
    return d


def test_backup_contains_the_irreplaceable_parts_and_no_secrets(project):
    make_channel(project)
    project.add_video("v1", status="uploaded")
    project.write_schedule([])

    info = backup.create_backup("manuelle")

    names = zipfile.ZipFile(os.path.join(backup.BACKUP_DIR, info["name"])).namelist()
    assert "database/tiktub.db" in names and "upload_schedule.json" in names
    assert "channels/chanA/profile.json" in names
    assert not any(n.endswith(("token.json", "credentials.json")) for n in names)
    assert info["reason"] == "manuelle"


def test_only_the_last_14_are_kept(project):
    for _ in range(16):
        backup.create_backup()
    assert len(backup.list_backups()) == backup.KEEP


def test_automatic_backup_runs_once_a_day(project, monkeypatch):
    assert backup.backup_if_due() is not None          # none yet → made
    assert backup.backup_if_due() is None              # fresh one exists → skipped
    monkeypatch.setattr(backup, "latest_backup_age", lambda: timedelta(hours=25))
    assert backup.backup_if_due() is not None          # over a day old → made again


def test_restore_brings_old_data_back_and_can_be_undone(project):
    make_channel(project)
    project.add_video("v1", status="ready_for_upload", note="before")
    snapshot = backup.create_backup("manuelle")["name"]
    project.add_video("v1", status="uploaded", note="after")
    project.add_video("v2", status="selected")

    result = backup.restore_backup(snapshot)

    assert db.get_video("v1")["note"] == "before" and db.get_video("v2") is None
    names = [b["name"] for b in backup.list_backups()]
    assert result["safety_backup"] in names                      # the state just replaced is kept
    backup.restore_backup(result["safety_backup"])                # ... and the restore can be undone
    assert db.get_video("v1")["note"] == "after" and db.get_video("v2") is not None


@pytest.mark.parametrize("name", ["../tiktub.db", "evil.zip", "tiktub-x/../../y.zip", ""])
def test_restore_refuses_anything_but_a_backup_name(project, name):
    with pytest.raises((ValueError, FileNotFoundError)):
        backup.restore_backup(name)


def test_backup_endpoints(client, project):
    make_channel(project)
    created = client.post("/api/backups").json()
    listing = client.get("/api/backups").json()
    assert listing["backups"][0]["name"] == created["name"] and listing["last_age_hours"] < 1
    dl = client.get(f"/api/backups/{created['name']}/download")
    assert dl.status_code == 200 and dl.headers["content-type"] == "application/zip"
    assert client.post("/api/backups/nope.zip/restore").status_code in (400, 404)
