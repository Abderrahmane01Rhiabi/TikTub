#!/usr/bin/env python3
"""
« Ajouter une chaîne » — adding a YouTube channel from the app instead of
creating channels/<name>/ by hand.

1. the Google project: one already used by a channel (its credentials.json),
   or a new OAuth client JSON dropped in the window (checked here);
2. the Gmail account: the same OAuth flow as "Connexion"
   (youtube_uploader.start_oauth_flow / complete_oauth_flow, same scopes);
3. confirmation, and only then channels/<name>/ is created.

Until the confirmation everything lives in memory (a "draft"): the client
JSON and the token never touch the disk, so cancelling or a failed
connection leaves nothing behind.
"""

import json
import secrets
import time
from typing import Dict, List, Optional

import quota

MAX_CLIENT_SECRET_BYTES = 64 * 1024     # a Google client JSON is ~0.5 KB
DRAFT_TTL_SECONDS = 30 * 60


# ---------------------------------------------------------------------------
# 1. the Google project
# ---------------------------------------------------------------------------

def parse_client_secret(raw: bytes) -> Dict:
    """The OAuth client JSON downloaded from Google Cloud, checked: an
    "installed" (desktop) or "web" client with client_id and client_secret
    (+ the two URLs the OAuth flow needs). ValueError with a French message
    otherwise."""
    if len(raw) > MAX_CLIENT_SECRET_BYTES:
        raise ValueError(f"Fichier trop gros ({len(raw) // 1024} Ko) : un identifiant OAuth Google fait moins de 1 Ko. "
                         "Vérifie que c'est bien le fichier JSON téléchargé depuis Google Cloud → Identifiants.")
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("Ce fichier n'est pas un JSON lisible. Dépose le fichier .json téléchargé depuis "
                         "Google Cloud → Identifiants → ID client OAuth → Télécharger le JSON.")
    if not isinstance(data, dict):
        raise ValueError("Ce JSON n'est pas un identifiant OAuth Google.")
    kind = "installed" if isinstance(data.get("installed"), dict) else "web" if isinstance(data.get("web"), dict) else None
    if not kind:
        hint = (" C'est une clé de « compte de service », qui ne peut pas publier sur une chaîne YouTube."
                if data.get("type") == "service_account" else "")
        raise ValueError("Ce JSON n'est pas un identifiant OAuth (ni « installed » ni « web »)." + hint +
                         " Crée un « ID client OAuth » de type « Application de bureau » dans Google Cloud.")
    section = data[kind]
    missing = [k for k in ("client_id", "client_secret", "auth_uri", "token_uri")
               if not isinstance(section.get(k), str) or not section.get(k).strip()]
    if missing:
        raise ValueError(f"Identifiant OAuth incomplet : il manque {', '.join(missing)}. "
                         "Télécharge à nouveau le JSON depuis Google Cloud (bouton « Télécharger le JSON » de l'ID client).")
    return {kind: section}


def project_id_of(client_config: Dict) -> Optional[str]:
    section = client_config.get("installed") or client_config.get("web") or {}
    return section.get("project_id")


def _read_client_config(path: str) -> Optional[Dict]:
    try:
        with open(path, "rb") as f:
            return parse_client_secret(f.read())
    except (OSError, ValueError):
        return None


def google_projects(manager) -> List[Dict]:
    """The Google projects already in use, from the channels' credentials.json,
    grouped by quota.project_key — the channels of one project share its
    daily YouTube quota. Never returns the client id or secret."""
    projects: Dict[str, Dict] = {}
    for ch in manager.list_channels():
        credentials_path, _ = manager.get_channel_paths(ch["name"])
        key = quota.project_key(credentials_path)
        if not key:
            continue
        project = projects.get(key)
        if project is None:
            config = _read_client_config(credentials_path) or {}
            project = projects[key] = {"project_key": key, "project_id": project_id_of(config),
                                       "channels": [], "quota": quota.status_for_channel(ch["name"])}
        project["channels"].append({"name": ch["name"], "display_name": ch["display_name"]})
    return list(projects.values())


def client_config_for_project(manager, project_key: str) -> Optional[Dict]:
    """The client JSON of an existing project (read from one of its channels)."""
    for ch in manager.list_channels():
        credentials_path, _ = manager.get_channel_paths(ch["name"])
        if quota.project_key(credentials_path) == project_key:
            config = _read_client_config(credentials_path)
            if config:
                return config
    return None


# ---------------------------------------------------------------------------
# Drafts: everything about a channel being added, in memory only
# ---------------------------------------------------------------------------

_drafts: Dict[str, Dict] = {}


def _purge_expired():
    now = time.time()
    for draft_id in [d for d, draft in _drafts.items() if now - draft["created"] > DRAFT_TTL_SECONDS]:
        _drafts.pop(draft_id, None)


def new_draft(client_config: Dict, source: str) -> Dict:
    _purge_expired()
    draft_id = secrets.token_urlsafe(12)
    _drafts[draft_id] = {"id": draft_id, "created": time.time(), "client_config": client_config,
                         "source": source, "token": None, "youtube": None, "error": None}
    return _drafts[draft_id]


def get_draft(draft_id: str) -> Optional[Dict]:
    _purge_expired()
    return _drafts.get(draft_id)


def drop_draft(draft_id: str) -> bool:
    return _drafts.pop(draft_id, None) is not None


def public_draft(draft: Dict) -> Dict:
    """What the window may see of a draft (no client secret, no token)."""
    return {"draft_id": draft["id"], "project_id": project_id_of(draft["client_config"]),
            "source": draft["source"], "connected": draft["token"] is not None,
            "youtube": draft["youtube"], "error": draft["error"]}
