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


# ---- point 2: Gmail account, then creation — stand-ins for Google's OAuth and channels.list

class FakeFlow:
    """google_auth_oauthlib Flow: an authorization URL, then a token."""
    made = []

    def __init__(self, client_config, redirect_uri):
        self.client_config, self.redirect_uri = client_config, redirect_uri
        self.state = f"state{len(FakeFlow.made)}"
        FakeFlow.made.append(self)

    @classmethod
    def from_client_config(cls, client_config, scopes, redirect_uri):
        import youtube_uploader as yu                              # the same scopes as "Connexion": YouTube's
        assert scopes == yu.SCOPES + yu.EMAIL_SCOPES               # 4, and the account's e-mail
        return cls(client_config, redirect_uri)

    def authorization_url(self, **kw):
        return f"https://accounts.google.com/o/oauth2/auth?state={self.state}", self.state

    def fetch_token(self, authorization_response):
        section = self.client_config.get("installed") or self.client_config.get("web")

        class Creds:
            def to_json(_):
                return json.dumps({"token": "t", "refresh_token": "r", "token_uri": section["token_uri"],
                                   "client_id": section["client_id"], "client_secret": section["client_secret"],
                                   "scopes": ["https://www.googleapis.com/auth/youtube.upload"]})
        self.credentials = Creds()


@pytest.fixture
def google(monkeypatch):
    """Google's side: the OAuth flow, and the YouTube channel behind the token."""
    import youtube_uploader as yu
    FakeFlow.made = []
    seen = {"channel": {"id": "UCnew", "snippet": {"title": "Ma Belle Chaîne", "customUrl": "@MaBelleChaine"}}}

    class Service:
        def channels(self):
            return self

        def list(self, part, mine):
            assert mine is True
            return self

        def execute(self):
            return {"items": [seen["channel"]] if seen["channel"] else []}
    monkeypatch.setattr(yu, "Flow", FakeFlow)
    monkeypatch.setattr(yu, "build", lambda *a, **k: Service())
    return seen


def connect(client, draft_id, **callback):
    auth_url = client.post(f"/api/channel_drafts/{draft_id}/connect").json()["auth_url"]
    state = auth_url.split("state=")[1]
    params = {"state": state, **(callback or {"code": "abc"})}
    return client.get("/api/oauth/callback", params=params)


def test_whole_flow_creates_the_channel_only_once_confirmed(client, project, google):
    register(project, "chana", client_id="shared", project_id="projet-partage")
    before = channel_dirs()
    draft = upload(client, client_secret("new-client", "nouveau-projet")).json()["draft_id"]

    page = connect(client, draft)

    assert page.status_code == 200 and "Ma Belle Chaîne" in page.text
    seen = client.get(f"/api/channel_drafts/{draft}").json()
    assert seen["youtube"]["id"] == "UCnew" and seen["youtube"]["title"] == "Ma Belle Chaîne"
    assert seen["youtube"]["suggested_name"] == "mabellechaine" and seen["error"] is None
    assert channel_dirs() == before                                            # nothing written yet

    done = client.post(f"/api/channel_drafts/{draft}/confirm",
                       json={"name": "belle_ar", "display_name": "Belle (AR)", "language": "ar"})

    assert done.status_code == 200
    folder = Path("channels/belle_ar")
    assert json.loads((folder / "credentials.json").read_text()) == client_secret("new-client", "nouveau-projet")
    assert json.loads((folder / "token.json").read_text())["refresh_token"] == "r"
    config = json.loads(Path("channels/channel_config.json").read_text())
    assert config["belle_ar"]["youtube_channel_id"] == "UCnew" and config["belle_ar"]["display_name"] == "Belle (AR)"
    profile = json.loads((folder / "profile.json").read_text())
    assert profile["language_hint"] == "ar" and profile["generation_mode"] is False
    assert "belle_ar" in [c["name"] for c in client.get("/api/channels").json()]   # no restart needed
    assert client.get(f"/api/channel_drafts/{draft}").status_code == 404          # the draft is gone


def test_a_channel_already_in_the_app_is_refused(client, project, google):
    register(project, "chana", youtube_channel_id="UCnew", display_name="Déjà là")
    draft = upload(client, client_secret()).json()["draft_id"]

    connect(client, draft)

    assert "déjà" in client.get(f"/api/channel_drafts/{draft}").json()["error"]
    refused = client.post(f"/api/channel_drafts/{draft}/confirm", json={"name": "autre", "display_name": "x", "language": "fr"})
    assert refused.status_code == 400 and not Path("channels/autre").exists()


def test_a_channel_known_only_by_its_token_is_found_too(client, project, google):
    folder = register(project, "chana")                                      # older channel: no id stored yet
    (folder / "token.json").write_text(json.dumps({"token": "t", "refresh_token": "r", "client_id": "client-A",
                                                   "client_secret": "s", "token_uri": "https://oauth2.googleapis.com/token",
                                                   "expiry": "2099-01-01T00:00:00Z"}))   # not expired: no refresh call
    draft = upload(client, client_secret()).json()["draft_id"]

    connect(client, draft)

    assert "chana" in client.get(f"/api/channel_drafts/{draft}").json()["error"]


def test_access_refused_by_google_is_explained_in_french(client, project, google):
    before = channel_dirs()
    draft = upload(client, client_secret()).json()["draft_id"]

    page = connect(client, draft, error="access_denied")

    error = client.get(f"/api/channel_drafts/{draft}").json()["error"]
    assert "utilisateur de test" in error and "utilisateur de test" in page.text
    assert channel_dirs() == before


def test_an_account_without_youtube_channel_is_explained(client, project, google):
    google["channel"] = None
    draft = upload(client, client_secret()).json()["draft_id"]

    connect(client, draft)

    assert "pas de chaîne YouTube" in client.get(f"/api/channel_drafts/{draft}").json()["error"]


def test_cancel_forgets_the_draft_and_its_pending_connection(client, project, google):
    import youtube_uploader as yu
    before = channel_dirs()
    draft = upload(client, client_secret()).json()["draft_id"]
    client.post(f"/api/channel_drafts/{draft}/connect")

    assert client.delete(f"/api/channel_drafts/{draft}").json() == {"cancelled": True}

    assert client.get(f"/api/channel_drafts/{draft}").status_code == 404
    assert not any(name.endswith(draft) for _, name in yu._pending_oauth_flows.values())
    assert channel_dirs() == before


@pytest.mark.parametrize("name", ["chana", "default", "Ma Chaine", "../evil", "a"])
def test_confirm_never_overwrites_nor_accepts_a_bad_name(client, project, google, name):
    register(project, "chana")
    draft = upload(client, client_secret("new-client")).json()["draft_id"]
    google["channel"] = {"id": "UCother", "snippet": {"title": "Autre"}}
    connect(client, draft)
    credentials_before = Path("channels/chana/credentials.json").read_text()

    answer = client.post(f"/api/channel_drafts/{draft}/confirm", json={"name": name, "display_name": "x", "language": "fr"})

    assert answer.status_code == 400 and answer.json()["detail"]
    assert Path("channels/chana/credentials.json").read_text() == credentials_before
    assert not Path("channels/default").exists() and not Path("evil").exists()


def test_suggested_names_are_unique_and_valid(project):
    import channel_setup
    assert channel_setup.suggest_name("@LungTe-Motivates", "x", taken={"lungte_motivates"}) == "lungte_motivates_2"
    assert channel_setup.suggest_name(None, "Mon Été Chaîne!", taken=set()) == "mon_ete_chaine"
    assert channel_setup.suggest_name(None, "لهذا السبب", taken=set()) == "chaine"
    assert channel_setup.suggest_name(None, "default", taken=set()) == "default_2"
