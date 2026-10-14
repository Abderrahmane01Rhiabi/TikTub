#!/usr/bin/env python3
"""
Quota YouTube - suivi de la consommation de l'API YouTube Data par projet
Google Cloud.

Le quota est compté par PROJET Google Cloud (celui d'où vient le
credentials.json d'une chaîne), pas par chaîne : plusieurs chaînes dont les
credentials viennent du même projet se partagent le même quota journalier.
Il se réinitialise à minuit, heure du Pacifique (≈ 9h à Paris).

Deux choses distinctes ici :
- une ESTIMATION (unités consommées par nos uploads, coût réglable dans
  config.yaml → youtube.quota) — uniquement informative, affichée dans l'UI.
  Le coût réel d'un upload a changé côté Google (≈1600 unités historiquement,
  ≈100 annoncé depuis fin 2025), d'où le réglage plutôt qu'un chiffre en dur.
- un signal RÉEL : quand YouTube répond "quotaExceeded", le projet est marqué
  épuisé pour la journée → plus aucun upload n'est tenté sur ce projet avant
  la réinitialisation. Seul ce signal bloque des uploads, jamais l'estimation
  (qui pourrait être fausse et bloquer à tort).
"""

import hashlib
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Optional

import pytz
import yaml

import db as _db

PACIFIC = pytz.timezone("America/Los_Angeles")
DEFAULT_UPLOAD_COST = 100
DEFAULT_DAILY_UNITS = 10000


def quota_day(now: Optional[datetime] = None) -> str:
    """Le "jour de quota" YouTube courant (date en heure du Pacifique)."""
    now = now or datetime.now(PACIFIC)
    return now.astimezone(PACIFIC).strftime("%Y-%m-%d")


def next_reset(now: Optional[datetime] = None) -> datetime:
    """Prochain minuit, heure du Pacifique (avec fuseau)."""
    now = (now or datetime.now(PACIFIC)).astimezone(PACIFIC)
    tomorrow = (now + timedelta(days=1)).date()
    return PACIFIC.localize(datetime(tomorrow.year, tomorrow.month, tomorrow.day))


def load_settings(config_path: str = "config.yaml") -> Dict[str, int]:
    """youtube.quota.upload_cost / daily_units depuis config.yaml, sinon défauts."""
    settings = {"upload_cost": DEFAULT_UPLOAD_COST, "daily_units": DEFAULT_DAILY_UNITS}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        configured = (config.get("youtube") or {}).get("quota") or {}
        for key in settings:
            if isinstance(configured.get(key), int) and configured[key] > 0:
                settings[key] = configured[key]
    except (OSError, yaml.YAMLError):
        pass
    return settings


def project_key(credentials_path: str) -> Optional[str]:
    """Identifiant stable du projet Google Cloud d'un credentials.json : un
    hash de son client_id (le client_id lui-même n'est jamais stocké ni
    affiché). None si le fichier est absent ou illisible."""
    try:
        with open(credentials_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        section = data.get("installed") or data.get("web") or {}
        client_id = section.get("client_id")
        if not client_id:
            return None
        return hashlib.sha1(client_id.encode("utf-8")).hexdigest()[:12]
    except (OSError, json.JSONDecodeError, AttributeError):
        return None


def project_key_for_channel(channel_name: str) -> str:
    """Projet d'une chaîne ; à défaut de credentials lisibles, la chaîne est
    traitée comme son propre projet (estimation isolée, rien de partagé)."""
    from channel_manager import ChannelManager
    credentials_path, _ = ChannelManager().get_channel_paths(channel_name)
    return project_key(credentials_path) or f"channel:{channel_name}"


def record_upload(channel_name: str, config_path: str = "config.yaml"):
    """À appeler après chaque upload réussi."""
    cost = load_settings(config_path)["upload_cost"]
    _db.add_quota_usage(project_key_for_channel(channel_name), quota_day(), cost, uploads=1)


def mark_exhausted(channel_name: str):
    """À appeler quand YouTube a RÉELLEMENT répondu quotaExceeded."""
    key, day = project_key_for_channel(channel_name), quota_day()
    _db.set_quota_exhausted(key, day)
    try:
        import alerts
        alerts.quota_exhausted(channel_name, key, day)
    except Exception:
        pass  # an alert must never break the upload flow


def is_exhausted(channel_name: str) -> bool:
    return _db.get_quota_usage(project_key_for_channel(channel_name), quota_day())["exhausted"]


def status_for_channel(channel_name: str, config_path: str = "config.yaml") -> Dict:
    """État du quota du projet de cette chaîne, pour l'UI."""
    settings = load_settings(config_path)
    key = project_key_for_channel(channel_name)
    usage = _db.get_quota_usage(key, quota_day())
    units_left = max(settings["daily_units"] - usage["units"], 0)
    return {
        "project_key": key,
        "uploads_today": usage["uploads"],
        "units_used_estimate": usage["units"],
        "estimated_uploads_left": units_left // settings["upload_cost"],
        "exhausted": usage["exhausted"],
        "resets_at": next_reset().isoformat(),
    }
