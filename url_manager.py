#!/usr/bin/env python3
"""
URL Manager - Gestion des URLs TikTok avec métadonnées
====================================================
Format du fichier URLs:
url | titre_custom | background_mode | priority | custom_description

Stockage : SQLite (db.py), pas de JSON — voir db.py pour le détail du schéma.
Migration automatique et unique depuis l'ancien database/videos_status.json
si trouvé (rien à faire à la main, l'historique existant est repris tel quel).
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

import db as _db

class URLManager:
    def __init__(self, database_path="database/videos_status.json"):
        # Kept for backward compat (some callers still pass/read this path),
        # but it is no longer read from directly except for the one-time
        # migration below — SQLite (db.py) is the real store now.
        self.database_path = database_path
        self.db_path = _db.DB_PATH
        self.ensure_database()

    def ensure_database(self):
        """Crée la base SQLite si besoin, et migre l'ancien JSON une seule fois."""
        _db.init_db(self.db_path)
        self._migrate_legacy_json_if_present()

    def _migrate_legacy_json_if_present(self):
        """Reprend database/videos_status.json dans SQLite la toute première
        fois (si la base SQLite est vide et que l'ancien fichier existe), puis
        renomme le JSON en backup pour ne pas le remigrer/relire par erreur."""
        legacy_path = Path(self.database_path)
        if not legacy_path.exists():
            return

        existing = _db.load_all(self.db_path)
        if existing["videos"] or existing["batches"]:
            return  # SQLite already has data — never overwrite with the old file

        try:
            with open(legacy_path, 'r', encoding='utf-8') as f:
                legacy_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return

        if not legacy_data.get("videos") and not legacy_data.get("batches"):
            return

        _db.replace_all(legacy_data, self.db_path)
        backup_path = legacy_path.with_suffix(".json.migrated_backup")
        legacy_path.rename(backup_path)
        print(f"✅ Migré {len(legacy_data.get('videos', {}))} vidéo(s) de l'ancien "
              f"{legacy_path} vers SQLite ({self.db_path}) — backup: {backup_path}")

    def parse_url_file(self, file_path: str) -> List[Dict]:
        """Parse un fichier d'URLs avec métadonnées"""
        videos = []

        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                # Parse format: url | titre | background | priority | description
                parts = [p.strip() for p in line.split('|')]

                video_data = {
                    'url': parts[0] if len(parts) > 0 else '',
                    'custom_title': parts[1] if len(parts) > 1 and parts[1] else None,
                    'background_mode': parts[2] if len(parts) > 2 and parts[2] else 'random',
                    'priority': parts[3] if len(parts) > 3 and parts[3] else 'normal',
                    'custom_description': parts[4] if len(parts) > 4 and parts[4] else None,
                    'line_number': line_num,
                    'source_file': file_path,
                    'status': 'pending'
                }

                if video_data['url']:
                    videos.append(video_data)

        return videos

    def create_example_url_file(self, filename="urls_input/example_batch.txt"):
        """Crée un fichier d'exemple"""
        example_content = """# Format: URL | Titre Custom | Background Mode | Priority | Description Custom
# Background modes: random, blur, solid, gradient, specific, same_for_all
# Priority: high, normal, low

https://www.tiktok.com/@user/video/123 | Mon Super Titre | random | high | Description personnalisée pour cette vidéo
https://www.tiktok.com/@user/video/456 | | blur | normal |
https://www.tiktok.com/@user/video/789 | Titre Anime | specific | high | Contenu anime épique !

# Ligne avec juste l'URL (utilise les defaults)
https://www.tiktok.com/@user/video/999
"""

        Path(filename).parent.mkdir(exist_ok=True)
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(example_content)

        print(f"✅ Fichier d'exemple créé: {filename}")

    def load_database(self) -> Dict:
        """Charge un instantané complet {"videos": {...}, "batches": {...}}.

        Gardée pour compatibilité avec le code existant qui manipule le dict
        directement — mais pour un besoin ciblé (un statut, une url...),
        préférer list_videos()/find_duplicate() qui interrogent l'index SQLite
        au lieu de tout charger en mémoire."""
        return _db.load_all(self.db_path)

    def save_database(self, data: Dict):
        """Réécrit tout l'instantané en une transaction atomique (tout ou rien —
        contrairement à un fichier JSON, un crash en cours d'écriture ne peut
        pas laisser une base à moitié écrite/corrompue)."""
        _db.replace_all(data, self.db_path)

    def add_batch(self, batch_name: str, videos: List[Dict]):
        """Ajoute un batch de vidéos à la base (une seule transaction atomique)"""
        batch_id = f"{batch_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        batch = {
            'name': batch_name,
            'created_at': datetime.now().isoformat(),
            'total_videos': len(videos),
            'status': 'pending'
        }

        video_rows = {}
        for video in videos:
            video_id = f"{batch_id}_{video['line_number']}"
            video['batch_id'] = batch_id
            video['video_id'] = video_id
            video['added_at'] = datetime.now().isoformat()
            video_rows[video_id] = video

        _db.insert_batch(batch_id, batch, video_rows, self.db_path)
        print(f"✅ Batch '{batch_name}' ajouté avec {len(videos)} vidéos")
        return batch_id

    def get_pending_videos(self, limit: Optional[int] = None) -> List[Dict]:
        """Récupère les vidéos en attente (requête indexée sur status)"""
        pending = _db.query_videos(status='pending', db_path=self.db_path)

        # Tri par priorité
        priority_order = {'high': 0, 'normal': 1, 'low': 2}
        pending.sort(key=lambda x: priority_order.get(x['priority'], 1))

        return pending[:limit] if limit else pending

    def list_videos(self, status: str = None, channel: str = None, batch_id: str = None) -> List[Dict]:
        """Requête indexée directe — ne charge que les lignes qui correspondent,
        pas toute la table."""
        return _db.query_videos(status=status, channel=channel, batch_id=batch_id, db_path=self.db_path)

    def update_video_status(self, video_id: str, status: str, **kwargs):
        """Met à jour le statut d'une vidéo — lecture + écriture ciblées sur cette
        seule ligne (pas de réécriture de toute la base à chaque appel, contrairement
        à l'ancien fichier JSON)."""
        video = _db.get_video(video_id, self.db_path)
        if video:
            video['status'] = status
            video['updated_at'] = datetime.now().isoformat()
            video.update(kwargs)
            _db.upsert_video(video_id, video, self.db_path)

    def delete_video(self, video_id: str):
        """Supprime définitivement une ligne vidéo — utilisé pour abandonner un
        brouillon de génération (jamais pour une vidéo déjà publiée/planifiée)."""
        _db.delete_video(video_id, self.db_path)

    def record_publish_decision(self, video_id: str, method: str, scheduled_time: str, context: Optional[Dict] = None):
        """Persists WHY a publish date was chosen, ON the video itself — not
        just in the ephemeral upload_schedule.json — so it survives past
        publish and can later be cross-referenced with real performance
        (video_stats_history) to see whether analytics/AI scheduling
        actually did better than static. method: 'static' | 'analytics' |
        'ai' | 'manual'. context: method-specific detail (e.g. the
        channel's analytics peak hours at the time this was decided)."""
        video = _db.get_video(video_id, self.db_path)
        if not video:
            return
        self.update_video_status(
            video_id, video['status'],
            publish_decision={
                'method': method,
                'scheduled_time': scheduled_time,
                'decided_at': datetime.now().isoformat(),
                'context': context or {},
            },
        )

    def add_stats_snapshot(self, video_id: str, checkpoint: Optional[str], data: Dict):
        """Appends one performance snapshot (views/likes/status/...) to this
        video's history — never overwrites a previous one."""
        _db.insert_stats_snapshot(video_id, checkpoint, data, self.db_path)

    def get_stats_history(self, video_id: str) -> List[Dict]:
        """Every snapshot ever taken for this video, oldest first."""
        return _db.get_stats_history(video_id, self.db_path)

    def get_captured_checkpoints(self, video_id: str) -> set:
        """Which named checkpoints already have a snapshot for this video."""
        return _db.get_captured_checkpoints(video_id, self.db_path)

    def find_duplicate(self, url: str, exclude_video_id: str = None) -> Optional[Dict]:
        """Cherche une vidéo déjà connue avec la même URL (toutes chaînes/batches
        confondus) qui a réellement avancé — pas juste une tentative en attente,
        échouée ou rejetée, qui ne compte pas comme "déjà traitée". Requête
        indexée sur url, pas un scan de toute la base."""
        ignorable_statuses = ('pending', 'download_failed', 'error', 'rejected', 'duplicate')
        return _db.find_duplicate_by_url(url, exclude_video_id, ignorable_statuses, self.db_path)

    def get_status_summary(self) -> Dict:
        """Résumé des statuts"""
        db = self.load_database()
        statuses = {}
        for video in db['videos'].values():
            status = video['status']
            statuses[status] = statuses.get(status, 0) + 1
        return statuses

# Exemple d'utilisation
if __name__ == "__main__":
    manager = URLManager()

    # Crée un fichier d'exemple
    manager.create_example_url_file()

    print("URL Manager initialisé ✅")
    print("Structure créée:")
    print(f"- {manager.db_path} (SQLite)")
    print("- urls_input/example_batch.txt")
    print("\n📝 Édite le fichier example_batch.txt avec tes URLs TikTok")
