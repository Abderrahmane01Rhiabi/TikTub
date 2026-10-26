"""« Ajouter une chaîne » : choose the Google project, connect the Gmail
account, confirm — nothing written under channels/ before confirming.
No real call to Google: the OAuth flow and channels.list are stand-ins."""

import json
from pathlib import Path

import pytest

import db
import quota


def client_secret(client_id="client-A", project_id="tiktub-a", kind="installed", **extra):
    section = {"client_id": client_id, "project_id": project_id, "client_secret": f"secret-{client_id}",
               "auth_uri": "https://accounts.google.com/o/oauth2/auth",
               "token_uri": "https://oauth2.googleapis.com/token",
               "redirect_uris": ["http://localhost"], **extra}
    return {kind: section}


def register(project, name, client_id="client-A", project_id="tiktub-a", display_name=None, **config_fields):
    """An existing, configured channel whose credentials.json comes from that project."""
    folder = project.add_channel(name, client_id=client_id)
    (folder / "credentials.json").write_text(json.dumps(client_secret(client_id, project_id)))
    path = Path("channels/channel_config.json")
    config = json.loads(path.read_text()) if path.exists() else {}
    config[name] = {"display_name": display_name or name.title(), "active": True, **config_fields}
    path.write_text(json.dumps(config))
    return folder


def channel_dirs():
    return sorted(p.name for p in Path("channels").iterdir() if p.is_dir())


def upload(client, content, name="client_secret.json"):
    data = content if isinstance(content, bytes) else json.dumps(content).encode()
    return client.post("/api/channel_drafts/upload", files={"file": (name, data, "application/json")})


# ---- point 1: which Google project (the JSON file)

def test_existing_projects_are_grouped_with_their_channels_and_todays_quota(client, project):
    register(project, "chana", client_id="shared", project_id="projet-partage")
    register(project, "chanb", client_id="shared", project_id="projet-partage")
    register(project, "chanc", client_id="other", project_id="projet-seul")
    db.add_quota_usage(quota.project_key_for_channel("chana"), quota.quota_day(), 100, uploads=1)

    answer = client.get("/api/google_projects")

    assert answer.status_code == 200
    projects = {p["project_id"]: p for p in answer.json()["projects"]}
    assert set(projects) == {"projet-partage", "projet-seul"}
    assert [c["name"] for c in projects["projet-partage"]["channels"]] == ["chana", "chanb"]
    assert projects["projet-partage"]["quota"]["uploads_today"] == 1
    assert projects["projet-seul"]["quota"]["uploads_today"] == 0
    assert "secret-" not in answer.text and '"shared"' not in answer.text      # never the client id/secret


def test_a_valid_google_json_opens_a_draft_and_writes_nothing(client, project):
    before = channel_dirs()

    answer = upload(client, client_secret("new-client", "nouveau-projet"))

    assert answer.status_code == 200 and answer.json()["draft_id"]
    assert answer.json()["project_id"] == "nouveau-projet"
    assert channel_dirs() == before


@pytest.mark.parametrize("content, words", [
    (b"pas du json", "JSON"),
    ({"type": "service_account", "client_email": "x@y"}, "OAuth"),
    ({"installed": {"client_id": "x"}}, "client_secret"),
    (client_secret(kind="web", client_secret=""), "client_secret"),
    (b"{" + b" " * 70_000 + b"}", "trop gros"),
])
def test_an_invalid_file_is_refused_in_french(client, project, content, words):
    answer = upload(client, content)

    assert answer.status_code == 400
    assert words in answer.json()["detail"]


def test_a_draft_can_start_from_an_existing_project(client, project):
    register(project, "chana", client_id="shared", project_id="projet-partage")
    key = client.get("/api/google_projects").json()["projects"][0]["project_key"]

    answer = client.post("/api/channel_drafts/from_project", json={"project_key": key})

    assert answer.status_code == 200 and answer.json()["project_id"] == "projet-partage"
    assert client.post("/api/channel_drafts/from_project", json={"project_key": "inconnu"}).status_code == 404
