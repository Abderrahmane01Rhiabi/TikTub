# TikTub

Application locale pour alimenter plusieurs chaînes YouTube Shorts :

- **Import** : vidéos TikTok / Instagram / Facebook → cadrage 9:16, ou **Montage auto** (écran noir, drones, sous-titres en cascade, musique — voir [MONTAGE_AUTO.md](MONTAGE_AUTO.md)) → titre, description et tags par IA.
- **Génération** : scripts écrits par IA → voix ElevenLabs → montage avec sous-titres animés (6 styles) et musique.
- **Publication** : planning (fixe, analytics ou IA), envoi sur YouTube, suivi du quota.
- **Dashboard** : statistiques à 24 h / 7 j / 30 j, « Ce qui marche » (vues et rétention comparées au même âge), « Refaire ce style ».
- **Accueil** : ce qui attend une action, idée de la semaine, alertes (connexion expirée, quota atteint, publication échouée).
- **Réglages** : connexion des chaînes, fonds, style du Montage auto, plans de drone, sauvegardes quotidiennes avec restauration, stockage et nettoyage.

## Lancer

```bash
cd TikTub
source .venv/bin/activate
uvicorn webapp.main:app --reload --port 8000
```

Puis ouvrir http://127.0.0.1:8000 (après une mise à jour : **Ctrl + F5**).

Première installation : `python -m venv .venv`, puis `pip install -r requirements.txt`, et copier `config.yaml.example` vers `config.yaml`. ffmpeg doit être installé.

## Organisation

| Fichier | Rôle |
| --- | --- |
| `webapp/main.py`, `webapp/static/index.html` | Serveur FastAPI et interface (une seule page) |
| `batch_processor.py` | Import : téléchargement, traitement, contenu IA, planning |
| `video_processor.py` | Traitement vidéo de l'import (cadrage, fonds, coins arrondis) |
| `generative/` | Génération : scripts, voix, sous-titres, montage ffmpeg (repli moviepy) |
| `montage/` | Montage auto de l'import : transcription Whisper, plan Gemini, plans de drone (`assets/broll/`), rendu ffmpeg |
| `youtube_uploader.py`, `quota.py` | Envoi YouTube, connexion OAuth, statistiques, quota |
| `stats_tracker.py` | Tâche horaire : statuts YouTube, statistiques, rétention, sauvegarde, nettoyage, alertes |
| `performance.py` | « Ce qui marche » et idée de la semaine |
| `alerts.py`, `backup.py`, `storage.py` | Alertes, sauvegardes, stockage |
| `db.py`, `url_manager.py` | Base SQLite (`database/tiktub.db`) |
| `channels/<chaîne>/` | Profil, identifiants OAuth et médias de chaque chaîne |
| `setup_channels.py`, `setup_openai.py`, `channel_profiles_seed.py` | Outils de configuration ponctuels |

## Tests

```bash
python -m pytest -q
```
