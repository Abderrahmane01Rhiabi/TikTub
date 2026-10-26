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


# ---------------------------------------------------------------------------
# 2. the Gmail account, then the confirmation
# ---------------------------------------------------------------------------

LANGUAGES = ("fr", "ar", "en")
NEW_NAME_RE = r"^[a-z0-9_]{2,40}$"     # a channel created here: lowercase, digits, _

TEST_USER_HELP = ("Ajoute ce compte Gmail comme « utilisateur de test » du projet : Google Cloud → "
                  "Google Auth Platform → Audience → Utilisateurs test → Ajouter des utilisateurs.")

GOOGLE_ERRORS = {
    "access_denied": "Google a refusé l'accès : soit tu as cliqué « Annuler », soit ce compte Gmail n'est pas "
                     "« utilisateur de test » du projet. " + TEST_USER_HELP,
    "admin_policy_enforced": "L'administrateur de ce compte Google interdit cette application.",
    "invalid_client": "Google ne reconnaît pas cet identifiant OAuth (client supprimé, ou secret modifié). "
                      "Télécharge à nouveau le JSON depuis Google Cloud.",
    "redirect_uri_mismatch": "L'adresse de retour n'est pas autorisée pour cet identifiant. Utilise un ID client "
                             "de type « Application de bureau », ou ajoute http://localhost:8000/api/oauth/callback "
                             "aux URI de redirection autorisés.",
    "invalid_grant": "L'autorisation a expiré avant d'être enregistrée — recommence la connexion.",
    "org_internal": "Ce projet Google est réservé aux comptes de son organisation (type « Interne »).",
}


def google_error_fr(error) -> str:
    """A Google OAuth error (code from the callback, or the exception raised
    while fetching the token), in French."""
    text = str(error or "")
    for code, message in GOOGLE_ERRORS.items():
        if code in text:
            return message
    return f"La connexion Google a échoué ({text[:200]}). " + TEST_USER_HELP


def _slug(text: str) -> str:
    import re
    import unicodedata
    ascii_text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", ascii_text.lower())).strip("_")[:40]


def suggest_name(custom_url: Optional[str], title: Optional[str], taken) -> str:
    """Technical name proposed for a new channel: from its @handle, else its
    title; lowercase, digits and _ only; never "default" nor a name taken."""
    base = _slug((custom_url or "").lstrip("@")) or _slug(title) or "chaine"
    if len(base) < 2:
        base = "chaine"
    name, k = base, 2
    while name in taken or name == "default":
        suffix = f"_{k}"
        name, k = base[:40 - len(suffix)] + suffix, k + 1
    return name


def _existing_owner(manager, youtube_id: str) -> Optional[str]:
    """The app channel already linked to this YouTube channel, if any. Channels
    created before the id was stored get it looked up once from their token
    (and saved), so an older channel is recognised too."""
    import youtube_uploader
    config = manager.get_config()
    for name, info in config.items():
        if info.get("youtube_channel_id") == youtube_id:
            return name
    changed = False
    for name, info in config.items():
        if info.get("youtube_channel_id"):
            continue
        try:
            identity = youtube_uploader.get_connected_channel_identity(name)
        except Exception:
            continue            # expired / unreachable: can't be checked now
        if identity and identity.get("id"):
            info["youtube_channel_id"] = identity["id"]
            changed = True
            if identity["id"] == youtube_id:
                manager.save_config(config)
                return name
    if changed:
        manager.save_config(config)
    return None


def _language_guess(title: str) -> str:
    return "ar" if any("؀" <= c <= "ۿ" for c in title or "") else "fr"


def identify(manager, draft: Dict, token_json: str):
    """After Google's window: the YouTube channel behind the new token, the
    proposed name / display name / language — or the reason it can't be added."""
    import youtube_uploader
    draft["token"] = token_json
    try:
        identity = youtube_uploader.channel_identity_from_token(token_json)
    except Exception as e:
        draft["error"] = google_error_fr(e)
        return
    if not identity:
        draft["error"] = "Ce compte Google n'a pas de chaîne YouTube. Choisis le compte (ou la chaîne de marque) qui gère la chaîne."
        return
    owner = _existing_owner(manager, identity["id"])
    if owner:
        shown = manager.get_config().get(owner, {}).get("display_name", owner)
        draft["error"] = f"La chaîne YouTube « {identity['title']} » est déjà dans l'app (« {shown} », nom technique {owner})."
        return
    taken = set(manager.get_config()) | {p for p in _channel_dirs(manager)}
    draft["youtube"] = {**identity,
                        "suggested_name": suggest_name(identity.get("custom_url"), identity.get("title"), taken),
                        "display_name": identity.get("title") or "",
                        "language": _language_guess(identity.get("title"))}


def _channel_dirs(manager):
    import os
    root = manager.channels_dir
    return [d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))] if os.path.isdir(root) else []


def create_channel(manager, draft: Dict, name: str, display_name: str, language: str) -> Dict:
    """The confirmation: channels/<name>/ with credentials.json (the project's
    JSON) and token.json, its channel_config.json entry and a default profile.
    Never overwrites anything; ValueError (French) when it can't."""
    import os
    import re
    import shutil
    name, display_name = (name or "").strip(), (display_name or "").strip()
    if not draft.get("token") or not draft.get("youtube") or draft.get("error"):
        raise ValueError(draft.get("error") or "La connexion Google n'est pas terminée.")
    if not re.match(NEW_NAME_RE, name):
        raise ValueError("Nom technique : 2 à 40 caractères, lettres minuscules, chiffres et _ uniquement.")
    if name == "default":
        raise ValueError("« default » est réservé : choisis un autre nom technique.")
    if name in manager.get_config() or os.path.exists(os.path.join(manager.channels_dir, name)):
        raise ValueError(f"Une chaîne « {name} » existe déjà : choisis un autre nom technique.")
    if not display_name or len(display_name) > 100:
        raise ValueError("Nom affiché : obligatoire, 100 caractères au plus.")
    if language not in LANGUAGES:
        raise ValueError("Langue : fr, ar ou en.")
    youtube = draft["youtube"]
    owner = _existing_owner(manager, youtube["id"])          # checked again: another tab may have added it
    if owner:
        raise ValueError(f"La chaîne YouTube « {youtube['title']} » est déjà dans l'app ({owner}).")

    if not manager.add_channel(name, display_name, description=f"Chaîne YouTube « {youtube['title']} »"):
        raise ValueError(f"Impossible de créer la chaîne « {name} ».")
    folder = os.path.join(manager.channels_dir, name)
    try:
        with open(os.path.join(folder, "credentials.json"), "w", encoding="utf-8") as f:
            json.dump(draft["client_config"], f, indent=2)
        with open(os.path.join(folder, "token.json"), "w", encoding="utf-8") as f:
            f.write(draft["token"])
        config = manager.get_config()
        config[name].update({"youtube_channel_id": youtube["id"], "youtube_title": youtube.get("title"),
                             "youtube_custom_url": youtube.get("custom_url")})
        manager.save_config(config)
        profile = manager.get_channel_profile(name)
        profile.update({"language_hint": language, "generation_mode": False})
        manager.save_channel_profile(name, profile)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)            # only what was just created
        config = manager.get_config()
        config.pop(name, None)
        manager.save_config(config)
        raise
    return {"name": name, "display_name": display_name, "youtube_title": youtube.get("title")}
