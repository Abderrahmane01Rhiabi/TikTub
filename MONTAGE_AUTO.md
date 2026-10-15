# Montage auto

Le Montage auto transforme une vidéo importée en Short au style « hopecore » :
- l'image est cachée par un **écran noir**, puis par **deux plans de drone**, juste avant la chute ;
- la voix continue dessous ;
- des **sous-titres en cascade** et une **accroche** sont ajoutés en haut ;
- une **musique** se coupe sur l'écran noir et revient sur son meilleur moment.

L'IA prépare le montage. **Rien n'est monté avant que tu l'aies validé.**

---

## Ce que fait le montage

| Moment | Image | Son |
| --- | --- | --- |
| Début | La vidéo, dans un cadre aux coins arrondis sur fond noir | Voix + musique de fond |
| Écran noir (1 à 3 s) | Noir, seuls les sous-titres restent | Voix seule : la musique est **coupée** |
| Retour | La vidéo revient | Le **moment choisi du morceau** démarre (ex. Dramamine à 0:34) |
| Drones (2 à 4 s) | Deux paysages vus du ciel, juste avant la chute | Voix + musique, même volume |
| Chute | La vidéo, jusqu'à la fin | Voix + musique |

- **Sous-titres** : un mot par ligne, qui apparaît au moment où il est dit, en zigzag.
  - **Cascade** : tous les mots en blanc.
  - **Accent** : les mots importants en jaune, en italique, avec une lueur. C'est l'IA qui les choisit, et tu peux les changer.
- **Musique** : son volume se règle automatiquement **par rapport à la voix** de chaque vidéo.
  - **Doux** : la musique reste environ 9 dB sous la voix.
  - **Marqué** : la musique reste environ 5 dB sous la voix.

---

## À régler une seule fois

### Réglages → Montage

Pour chaque chaîne :
- **Montage auto par défaut** : si la case est cochée, les vidéos téléchargées pour cette chaîne arrivent au Cadrage déjà en Montage auto.
- **Sous-titres** : Cascade ou Accent.
- **Musique de fond** : choisis un morceau, ou clique **Ajouter** pour en envoyer un (mp3, wav, m4a…).
- **Moment du morceau** : c'est l'instant qui démarre quand l'image revient après l'écran noir. Lance le lecteur, puis clique **Prendre l'instant du lecteur** au bon moment. Tu peux aussi taper les secondes et cliquer **▶ Écouter ce moment** pour vérifier.
- **Volume** : Doux ou Marqué.
- **Accroche en haut de l'écran** : activée ou non.

### Réglages → Drones

La bibliothèque des plans de drone, partagée par toutes les chaînes.
- Clique sur un plan pour le voir bouger, et sur **✕** pour le supprimer.
- Pour en ajouter : tape un thème en anglais (ex. `drone mountain lake`) ou clique une idée, puis **Ajouter 3 plans**. Les plans viennent de Pixabay : ils sont gratuits et utilisables commercialement.
- Il faut la clé `PIXABAY_API_KEY` dans le fichier `.env`.
- Chaque miniature indique **« neuf »** ou combien de fois le plan a servi (**×2**). Passe la souris dessus pour voir quelles chaînes l'ont utilisé.
- Chaque chaîne évite les plans de ses **10 dernières vidéos**, ainsi que ceux déjà réservés par ses autres vidéos en attente de validation : deux vidéos d'un même lot ne tombent pas sur le même plan.
- Si la bibliothèque a **moins de 30 plans**, un message te dit combien en ajouter pour que chaque chaîne attende au moins 10 vidéos avant de revoir un plan. Sinon, un spectateur qui enchaîne tes Shorts remarquerait les répétitions, et YouTube pourrait juger les vidéos répétitives.

---

## Pour chaque vidéo

1. **Import → 1 · URLs** et **2 · Sélection** : comme d'habitude.
2. **3 · Cadrage** : choisis **Montage auto** (ou garde **Habillage simple**). Tu peux changer le style de cette vidéo seulement ; le bouton **↺** remet le style de la chaîne.
3. Clique **Suivant (lancer l'IA)**. L'IA transcrit la vidéo, puis prépare le montage. Ça prend **1 à 3 minutes par vidéo**, et l'app t'emmène à l'étape 4.
4. **4 · Montage**, pour chaque vidéo :
   - la **frise** montre où tombent l'écran noir, les drones et la chute ;
   - choisis une des **3 accroches** proposées, ou écris la tienne ;
   - en style Accent, clique les mots pour les mettre en jaune ou les remettre en blanc ;
   - **⟳** sur un plan de drone le remplace par un autre ;
   - **Aperçu rapide** : une version légère de la vraie vidéo, en 15 secondes environ ;
   - **Nouveau plan (IA)** : l'IA propose un autre montage. Elle en donne rarement deux identiques ;
   - **Valider ce montage**.
5. **Monter les vidéos validées** : le vrai montage, puis le titre, la description et les tags par l'IA, comme d'habitude. La vidéo arrive ensuite dans **Publication → Résultats IA**.

---

## Quand l'IA prévient

- **« L'humour est porté par l'image »** : la vidéo est drôle par ce qu'on **voit** (une grimace, une action). L'écran noir et les drones risquent de cacher le moment drôle. Regarde l'aperçu ; si besoin, clique **Passer en habillage simple**.
- **« Aucune parole détectée »** : ce montage s'appuie sur ce qui est dit. Une vidéo sans parole ne s'y prête pas.
- Si une partie du plan est refusée (écran noir trop court, drones qui cacheraient la chute…), la frise l'indique en petit. Le montage se fait quand même, simplement sans cette partie.

---

## Bon à savoir

- Le moteur est dans le dossier `montage/` du projet. Les plans de drone sont dans `assets/broll/`, qui n'est pas dans git (trop lourd).
- La transcription utilise Whisper **medium** : plus lent que small, mais nettement plus juste. Il a par exemple bien entendu « Carolina Reaper », que small transformait en « Carolina repurchased ».
- Les utilisations des plans de drone sont notées dans la base (table `broll_usage`) : elles sont donc incluses dans les sauvegardes.
- Les fichiers de travail de chaque vidéo (`temp/<vidéo>/montage/`) sont supprimés par le nettoyage automatique une fois la vidéo publiée.
- **Idée gardée pour plus tard** : caler le passage entre les deux drones sur un temps fort de la musique.
