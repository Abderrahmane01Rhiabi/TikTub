# La Reprise — reprendre le Short d'un ami (4e mode d'Adaptation)

Chantier du 30 et 31 octobre 2026. Fusionné dans `main` le 31/10 (commit `d7c73a8`).

## 1. L'idée

Un ami (un autre créateur) te donne son Short vertical. On **garde ses images**, mais on refait tout le reste pour
nos chaînes :

- on **efface ce qu'il a ajouté** par-dessus : ses sous-titres, ses titres, ses numéros, son pseudo, ses
  filigranes, ses boutons « follow / like », ses autocollants ;
- on **garde ce qui aide à comprendre** : une croix rouge, une flèche ou un cercle qui montre un détail ;
- on **ne touche jamais à ce qui a été filmé** : les maillots, les dossards, les panneaux, les couleurs, la lumière ;
- on écrit **notre texte** (en français et en arabe), avec **notre voix**, **nos sous-titres** et **notre son** ;
- on prépare le **titre YouTube, la description, les tags** et la **miniature** de chaque langue.

## 2. Le parcours dans l'application

Adaptation → Nouveau projet → **Reprise** → le lien du Short → les chaînes → le son.

| Étape | Ce qui se passe | Qui |
|---|---|---|
| 1. Analyse | Le Short est téléchargé en entier (jusqu'à 1080 sur le petit côté, en H.264), avec sa miniature. Gemini découpe ses plans et liste ce que le créateur a ajouté. | automatique |
| 2. Nettoyage | Tout ce qui est « à cacher » est effacé, image par image, sur la carte graphique. | automatique (3 à 45 min) |
| 3. Vérification | L'original et la version propre côte à côte. Chaque élément peut passer en **garder / cacher**, puis « Nettoyer à nouveau ». | toi |
| 4. Script | Gemini dit si c'est un **top** (points réordonnés si c'est logique, numérotés) ou une **histoire** (ordre gardé, pas de numéros), et écrit chaque langue. | automatique |
| 5. Relecture | Titre YouTube, description, tags, titre de la miniature et texte de chaque partie : modifiables puis validés, langue par langue. | toi |
| 6. Voix et vidéos | La voix de chaque chaîne (modèle ElevenLabs au choix), puis la vidéo complète avec le son choisi. | automatique |
| 7. Aperçu | Changer la voix, le modèle ou le son. Changer seulement le son ne repaie pas la voix. | toi |
| 8. Publication | Les vidéos validées partent dans Publication avec leur titre, leur description, leurs tags et leur miniature. | toi |

## 3. Le nettoyage : comment il marche

Le principe : **Gemini dit quoi effacer et où, les outils exécutent.**

1. **Gemini regarde la vidéo** et liste chaque élément ajouté, avec son type, son moment et son cadre.
   Un élément par phrase de sous-titres, pas un par mot, sinon sa réponse est coupée sur une longue vidéo.
2. **Gemini revérifie chaque élément sur une image fixe**, où il est bien plus précis que sur la vidéo
   (un filigrane placé à 3 % de la hauteur au lieu de 13 %, un titre à 70 % au lieu de 60 %).
3. **Gemini décide « garder » ou « cacher »** pour chaque dessin, avec sa raison. Les textes, logos, pseudos et
   boutons sont toujours cachés.
4. **L'effacement, image par image :**
   - la **lecture des textes** (EasyOCR), **seulement dans les zones du créateur**, pour ne pas effacer ce qui est
     filmé (« KENYA » sur un maillot) ;
   - la **recherche par couleur** : les couleurs de ses lettres sont apprises, ce qui rattrape un « A » ou un « IT »
     que la lecture rate (lettres colorées avec un contour noir ou blanc, lettres blanches avec un contour noir) ;
   - la **forme exacte** des dessins à cacher, suivie par **SAM 2** : on n'efface jamais un grand rectangle ;
   - la **reconstruction** de l'image à la place (inpainting), avec un léger flou si la zone est grande.
5. **La relecture de contrôle** : la vidéo propre est relue en taille réelle. Un mot oublié est effacé, ainsi que
   sur les 2 images avant et après.

**Limite connue :** quand le texte du créateur est posé **pile sur** un texte filmé (son titre sur le dossard d'un
coureur), on ne peut pas effacer l'un sans toucher l'autre. Il reste alors une petite tache floue.

## 4. Le son

| Choix | Ce que c'est |
|---|---|
| Notre musique | la musique de la chaîne |
| Sa musique | la musique de la vidéo d'origine, sa voix enlevée (Demucs). ⚠️ YouTube peut réclamer les droits si c'est un son connu |
| **Musique intelligente** | une chanson de la **liste commune**, dont la **montée** (refrain, drop) tombe sur le **moment fort** du montage |
| Sans musique | la voix seule |

Le volume se règle à **16 dB sous la voix** par défaut. C'est le niveau choisi sur le Short 5 : la musique reste en
fond et la voix reste claire.

**La musique intelligente, comme un monteur :**
- Gemini **écoute chaque chanson une seule fois** et note son humeur, ce qu'elle porte bien et son moment fort ;
- le **volume est mesuré** pour trouver les **vraies montées** : un passage calme suivi d'un passage fort, pas un
  simple coup de batterie ;
- Gemini choisit **la chanson** qui colle au ton (pas de chanson triste sur une vidéo drôle) et **la partie** qui
  doit tomber sur la montée (la révélation, le n°1, le geste héroïque). La chanson est décalée pour que les deux
  tombent ensemble.

Pour l'instant, la musique intelligente est réservée à **C'est pour ça** et **لهذا السبب**. Les autres chaînes
prennent leur propre musique.

## 5. Les Réglages ajoutés (Réglages → Voix)

- **Le modèle de voix** de chaque chaîne : `eleven_v4` (le plus naturel dans nos essais), `eleven_v3`,
  `eleven_multilingual_v2`, `eleven_flash_v2_5` (rapide et moins cher). L'Adaptation classique s'en sert aussi. On
  peut aussi le changer projet par projet, à l'aperçu d'une Reprise.
- **Les musiques communes**, partagées par toutes les chaînes : ajout par **lien YouTube** ou par **fichier**. L'IA
  écoute chaque chanson une fois, pour quelques centimes. Elles sont rangées dans `assets/musiques/`, hors de git.

## 6. Ce qu'on a testé

| Short | Sujet | Ce qu'il a appris au système |
|---|---|---|
| 1, 2 | malinois, perroquet | le nettoyage de base, la recherche par couleur, le recadrage sur image fixe |
| 3 | panthère (160 s) | Gemini coupe sa réponse sur une longue vidéo → un élément par phrase |
| 4 | claviers (60 images/s) | la vidéo propre doit garder la vitesse d'origine ; un top réordonné et numéroté |
| 5 | cochon | lettres rouges au contour blanc ; une histoire n'a pas de numéros ; les voix v4 |
| 6 | beurre de cacahuète | garder le X rouge ; la forme exacte au lieu d'un rectangle ; la relecture |
| 7 | Titanic | le texte blanc au contour noir |
| 8 | fair-play (@Klimt, 47 s) | l'essai complet dans l'application, **publié en FR et en AR** |

## 7. Les problèmes trouvés et corrigés en route

- **Les temps de Gemini écrits « 1:62.2 »** : il colle les minutes et les secondes (162,2 veut dire 122,2 s ;
  240 veut dire 2:40). Les fins de vidéos étaient fausses. Les temps sont maintenant relus en secondes, **pour tous
  les modes d'Adaptation**.
- **Les Shorts téléchargés en 608x1080** : le format demandait une hauteur d'au plus 1080, alors qu'un Short vertical
  fait 1920 de haut. On trie maintenant par le petit côté → 1080x1920.
- **La voix en avance sur les images** : une partie fait maintenant exactement la durée de sa phrase.
- **Le montage qui saturait la mémoire** (27 plans ouverts d'un coup) : les parties sont montées une par une.
- **La lecture des textes qui effaçait les maillots** : elle n'agit plus que dans les zones du créateur.
- **Le français sans accents et des textes trop courts** : la consigne demande les accents, et une vitesse de parole
  qui remplit les images.
- **Le titre et la description trop pauvres** : un vrai titre YouTube, une description avec hashtags et 8 à 12 tags
  par langue, comme les autres modes. Plus de ligne de crédit automatique.

## 8. Ce que ça coûte et combien de temps ça prend

- **Gemini** : quelques centimes par Short (analyse, éléments, script, choix de la musique).
- **ElevenLabs** : environ 16 caractères par seconde de vidéo en français, 11 en arabe (environ 1 300 caractères
  pour un Short de 47 s dans les deux langues).
- **La carte graphique** : de 3 à 45 minutes de nettoyage selon la longueur et la taille du Short (35 min pour
  47 s en 1080x1440).

## 9. Les fichiers

| Fichier | Rôle |
|---|---|
| `adaptation/reprise.py` | le nettoyage |
| `adaptation/reprise_montage.py` | le script, la voix, le montage, les sous-titres, la miniature |
| `adaptation/reprise_pipeline.py` | les étapes d'un projet Reprise |
| `adaptation/musique.py` | la musique intelligente |
| `webapp/static/js/reprise.js` | les écrans |
| `tests/test_adaptation_reprise*.py` | les tests |
| `archive/etude_reprise/` | les scripts du labo (hors de git) |

## 10. Plus tard

- La musique intelligente pour les autres chaînes.
- Couper les plans sur le rythme de la musique, et baisser la musique quand la voix parle.
