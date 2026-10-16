# Nouveautés TikTub

Ce document présente les 8 améliorations ajoutées à TikTub (branches `feature/backup-and-growth`, `feature/montage-auto` et `feature/adaptation`) : ce que fait chacune, où la trouver et comment s'en servir.

---

## 1. Sauvegardes automatiques

**Où :** Réglages → Sauvegardes

**Pourquoi :** toutes les données importantes (vidéos, décisions de planning, statistiques) sont dans un seul fichier, `database/tiktub.db`. S'il est abîmé ou effacé, tout est perdu.

**Ce que ça fait :**
- Une fois par jour, l'app fait une copie de :
  - la base de données ;
  - le planning (`upload_schedule.json`) ;
  - les réglages et l'image de fond de chaque chaîne.
- Les **14 dernières copies** sont gardées dans `database/backups/`. Les plus anciennes sont supprimées.
- Le bouton **Sauvegarder maintenant** crée une copie à la demande.
- Le bouton **Restaurer** remet une sauvegarde en place. Juste avant, l'app sauvegarde l'état actuel (« avant restauration ») : une restauration peut donc toujours s'annuler.
- Chaque sauvegarde peut être téléchargée en `.zip`.

**Pas inclus volontairement :** les identifiants de connexion YouTube (`credentials.json`, `token.json`), pour ne pas multiplier les copies de secrets. Si besoin, on reconnecte simplement la chaîne. Les vidéos et musiques ne sont pas incluses non plus : trop lourdes, et ce n'est pas la partie irremplaçable.

---

## 2. Stockage et nettoyage

**Où :** Réglages → Stockage

**Pourquoi :** chaque vidéo téléchargée ou montée laisse des fichiers sur le disque (`temp/` et `processed_videos/`). Rien ne les supprimait, donc ils s'accumulaient.

**Ce que ça fait :**
- L'écran montre ce qui prend de la place, rangé par catégorie :

| Catégorie | Signification | Supprimé ? |
| --- | --- | --- |
| Déjà publiées | La vidéo est sur YouTube, les fichiers ne servent plus | Oui, automatiquement |
| Orphelins | Fichiers rattachés à aucune vidéo (de plus de 24 h) | Oui, automatiquement |
| Décochées | Vidéos refusées à l'étape Sélection | Seulement si tu le demandes |
| En cours | Vidéos à trier, prêtes, en génération… | Jamais |

- Le nettoyage automatique tourne **une fois par jour**.
- Le bouton **Libérer X Mo** lance le nettoyage tout de suite.
- La case **Effacer aussi les vidéos décochées** les supprime en plus. Elles quittent alors définitivement la Sélection.

---

## 3. Rétention dans « Ce qui marche »

**Où :** Dashboard → Ce qui marche

**Pourquoi :** les vues disent combien de personnes sont venues, pas si elles sont restées. Or YouTube pousse surtout les vidéos que les gens regardent jusqu'au bout.

**Ce que ça fait :**
- Pour chaque vidéo publiée, l'app mesure le **% moyen regardé pendant sa première semaine**. La mesure se fait une seule fois, 9 jours après la publication (le temps que YouTube Analytics ait les chiffres).
- Toutes les vidéos sont comparées au même âge, comme pour les vues à 7 jours.
- La rétention s'affiche :
  - dans le résumé (« En moyenne, les gens regardent 81 % d'une vidéo ») ;
  - sur chaque carte (format, fond, musique…) ;
  - sous chaque vidéo du classement.

**Bon à savoir :**
- Un chiffre au-dessus de 100 % est normal sur les Shorts : la vidéo tourne en boucle.
- La chaîne doit avoir autorisé l'accès aux statistiques YouTube.

---

## 4. Idée de la semaine

**Où :** Accueil, sous les compteurs

**Pourquoi :** « Ce qui marche » montre les tendances, mais il fallait encore les lire et décider soi-même. Là, l'app propose directement quoi refaire.

**Ce que ça fait :**
- Sur les chaînes en mode génération, l'app repère le style qui bat le plus nettement les vues habituelles.
- Elle propose la **recette gagnante complète**, critère par critère :

| Critère | Exemple (LungTeMotivates) | Score |
| --- | --- | --- |
| Format | D · Liste éducative | ×4,9 · 98 % regardé |
| Fond | 186714-878826932_medium.mp4 | ×5,8 · 98 % regardé |
| Musique | i was only temporary.mp3 | ×4,8 · 93 % regardé |
| Sous-titres | karaoke | ×1,9 · 90 % regardé |
| Heure | 18h–21h | ×1,9 · conseil pour le planning |

« ×4,9 » veut dire 4,9 fois plus de vues qu'une vidéo habituelle de la chaîne.

**Les boutons :**
- **Lancer 3 vidéos** : l'IA écrit 3 nouveaux scripts, sur des sujets différents, avec le format gagnant. Le décor (fond, musique, sous-titres) est déjà pré-rempli avec la recette et reste modifiable à l'étape Décor. Rien n'est envoyé à ElevenLabs avant que tu valides les scripts.
- **Voir « Ce qui marche »** : ouvre l'analyse détaillée.
- **Pas cette semaine** : masque la carte jusqu'à la semaine suivante.

**Règles de prudence :**
- Un critère n'entre dans la recette que s'il repose sur **au moins 3 vidéos** et fait mieux que d'habitude. Sinon, la carte affiche « celui du modèle ».
- La vidéo modèle, dont l'IA copie la structure du script, est celle qui a le plus de points communs avec la recette.
- L'heure est un conseil : elle n'est pas appliquée automatiquement au planning.

---

## 5. Alertes

**Où :** bandeau en haut de tous les écrans, plus une notification Windows en option

**Pourquoi :** certains problèmes arrivent quand on ne regarde pas, et bloquent tout en silence.

**Ce que ça signale :**

| Alerte | Quand | Bouton |
| --- | --- | --- |
| Connexion YouTube expirée | Vérifiée chaque heure | Reconnecter |
| Quota YouTube atteint | YouTube refuse les envois du jour | (disparaît à minuit, heure du Pacifique, soit 9 h en France) |
| Échec de publication | Un envoi a échoué pour une vraie raison | Voir Publier |
| Vidéo disparue de YouTube | Une vidéo publiée n'existe plus | Voir le Dashboard |

**Comment ça se comporte :**
- Une alerte n'apparaît **qu'une fois** : pas de répétition toutes les heures.
- Le bouton **OK** la masque. Elle ne revient que si le problème est réglé puis se reproduit.
- Elle disparaît toute seule quand le problème est réglé (chaîne reconnectée, envoi réussi…).
- Le bouton **Recevoir aussi ces alertes en notification Windows** active les notifications du navigateur. Elles ne fonctionnent que si l'onglet TikTub est ouvert, même en arrière-plan.

---

## 6. Nettoyage du code

Cette partie ne change rien de visible, mais le projet devient plus clair et plus sûr.

- **Suppression de l'ancien mode terminal** : le menu en ligne de commande de `batch_processor.py` faisait doublon avec l'interface web. Le fichier passe de 1 853 à 691 lignes.
- **Suppression de 9 vieux scripts de 2025** : ils utilisaient l'ancienne base JSON et ne fonctionnaient plus. Ils restent récupérables dans l'historique git.
- **`test3_script.py` devient `video_processor.py`** : malgré son nom, ce n'était pas un test mais le moteur vidéo de l'import.
- **README réécrit en français**, court et à jour.
- **Démarrage du serveur modernisé** (FastAPI `lifespan`) : plus aucun avertissement.

---

## 7. Montage auto

**Où :** Import → 3 · Cadrage et 4 · Montage ; Réglages → Montage et Drones

**Pourquoi :** reproduire automatiquement le style d'un créateur de Shorts, sur des vidéos importées, sans savoir monter.

**Ce que ça fait :** l'IA prépare un montage (écran noir, puis deux plans de drone avant la chute, sous-titres en cascade, accroche, musique coupée sur l'écran noir puis relancée sur son meilleur moment). Tu le vérifies et tu le valides avant le vrai rendu.

Le mode d'emploi complet est dans **[MONTAGE_AUTO.md](MONTAGE_AUTO.md)**.

---

## 8. Adaptation

**Où :** espace Adaptation ; Réglages → Voix

**Pourquoi :** refaire un Short viral « explicatif » pour tes chaînes, dans leur langue (français, arabe standard…), avec ta voix ElevenLabs, sans copier la vidéo d'origine.

**Ce que ça fait :** l'app analyse le Short modèle, découpe ses vidéos sources en clips propres, écrit et fait relire un script par chaîne, génère la voix, et contrôle automatiquement chaque vidéo. Tu valides les sources, chaque script et chaque aperçu. Les vidéos arrivent ensuite dans Publication.

Le mode d'emploi complet est dans **[ADAPTATION.md](ADAPTATION.md)**.

---

## Tester

```bash
uvicorn webapp.main:app --reload --port 8000
```

Puis **Ctrl + F5** sur http://127.0.0.1:8000.

À vérifier :
1. Réglages → Sauvegardes et Stockage.
2. Dashboard → Ce qui marche : le « % regardé ».
3. Accueil : la carte « Idée de la semaine » et son bouton « Lancer 3 vidéos ».
4. Le bandeau d'alertes, s'il y a un problème en cours.
5. Réglages → Montage et Drones, puis une vidéo en Montage auto de l'import jusqu'à Publication.
6. Réglages → Voix, puis un projet dans l'espace Adaptation jusqu'à Publication.
