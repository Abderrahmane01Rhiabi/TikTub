# Économies sur l'IA — phase 1 : analyse

> Analyse seulement : aucun fichier de l'app modifié, aucun appel payant.
> Sources : le code (lignes citées) et le journal `temp/usage/gemini.jsonl`.
> Journal : **523 appels, 5,78 $**, du 25/10 18:46 au 27/10 21:15 (10 appels de plus que les 513 / 5,71 $ cités :
> des scripts de Génération faits ce soir). Avant le 25/10 le journal était effacé chaque jour (bug corrigé).

## En bref

| | Économie estimée sur la période |
|---|---|
| 🟢 Sans risque (ne pas refaire, garder un résultat) | **≈ 0,15 $ (≈ 3 %)** + des économies à chaque retour en arrière ou relance |
| 🟢 + 🟡 (après tests) | **≈ 2,0 $ (≈ 35 %)**, jusqu'à **≈ 2,3 $ (≈ 40 %)** si les relectures passent de Pro à Flash |

**La conclusion honnête :** l'app refait peu de travail en double « pur » (≈ 3 %). Elle a déjà les bons
réflexes à plusieurs endroits (voir « Ce qui est déjà bien fait »). L'argent part surtout dans deux choses :
1. **les vidéos regardées en pleine résolution** (49 % du coût total : les « médias ») ;
2. **la réflexion du modèle** (*thoughts*, payée au prix de la réponse) : **30 % du coût total**, alors
   qu'aucune étape qui regarde des images n'a de limite de réflexion.

Ce sont des 🟡 : très probablement sans perte de qualité, mais à vérifier sur de vrais projets avant.

### D'où vient chaque dollar (journal)

| Part du coût | Montant | % |
|---|---|---|
| Vidéos et images envoyées (entrée « médias ») | 2,85 $ | 49 % |
| Réflexion du modèle (*thoughts*) | 1,72 $ | 30 % |
| Réponses écrites | 0,89 $ | 15 % |
| Texte envoyé (consignes) | 0,33 $ | 6 % |

---

## Réponses aux 8 questions

### 1. Une vidéo vérifiée est-elle regardée à nouveau après le téléchargement ? — **OUI, mais pas en double inutile**

- La vérification (`finder.check` → `_watch`, `adaptation/finder.py` l. 914 et 863) regarde le **lien YouTube entier**
  à **0,5 image/s** (`CHECK_FPS`, l. 37) et donne un moment approximatif par plan.
- Après le téléchargement (`run_fetch`, `adaptation/pipeline.py` l. 981), le **morceau téléchargé** est regardé à
  nouveau par `sources.retime` (l. 1065) à **2 ou 4 images/s** pour **recaler** le moment exact.
- Les moments de la vérification **sont réutilisés** : ils servent de point de départ (« moment approximatif ») et
  décident quoi télécharger. Ils ne sont pas recalculés de zéro.
- Ce second regard est **voulu et utile** : le commentaire de `retime` (`adaptation/sources.py` l. 558) cite une
  mesure où le moment de la vérification était faux de quelques secondes deux fois sur un même Short. → 🔴 ne pas
  le supprimer.

### 2. Combien de fois le même fichier téléchargé part-il chez Gemini ? — **3 fois en vidéo, plus des images**

Dans `run_fetch`, **un seul envoi** du fichier (`sources.gemini_file`, `pipeline.py` l. 1055), puis **trois questions**
sur ce même fichier :

| Appel | Ligne | Images/s | Tokens vidéo moyens | Coût moyen |
|---|---|---|---|---|
| `sources.retime` (recaler) | `pipeline.py` 1065, `sources.py` 572 | 4 ou 2 | 12 361 | 0,0133 $ |
| `sources.orientation` (à l'endroit ?) | `pipeline.py` 1076, `sources.py` 919 | 0,5 | 3 992 | 0,0036 $ |
| `sources.describe` (contrôle) | `pipeline.py` 1102, `sources.py` 613 | 1 (défaut, non fixé) | 6 273 | 0,0070 $ |

- **Chaque appel repaie toute la vidéo** en tokens d'entrée : l'envoi unique évite de retransférer le fichier, pas
  de repayer ses tokens.
- **Cache de contexte de Gemini** : possible en théorie (la vidéo dépasse largement la taille minimale), mais pour
  trois questions posées dans la même minute, **les fusionner en une seule question** est plus simple et plus
  rentable (pas de frais de stockage du cache). Le cache « implicite » automatique de Google ne peut pas jouer ici :
  les trois appels envoient la vidéo à des cadences différentes, donc des tokens différents. *À vérifier dans la
  documentation Google avant de choisir : prix exact du cache pour Gemini 3.*
- **Point de mesure** : le journal n'enregistre pas `cachedContentTokenCount` (`gemini_ai_generator.py` l. 38).
  Si Google a déjà appliqué des remises de cache, la vraie facture est un peu **inférieure** aux 5,78 $ calculés.

Les **images fixes** des clips partent aussi plusieurs fois, chacune pour une question différente :

| Appel | Images par clip | Ligne |
|---|---|---|
| `find_boxes` (logos à effacer) | 1 (au milieu) | `pipeline.py` 1097 |
| `leftover_text` (texte resté après nettoyage, via `find_boxes`) | 2 (5 si déjà nettoyé) | `sources.py` 658 |
| `annotate.review` (flèches) | 1 (`clip_still`) | `pipeline.py` 1179 |
| `effects.decide` (effets) | **la même** 1 (`clip_still`) | `pipeline.py` 1186 |
| `effects.auto_zoom` (taille du sujet) | **la même** 1 (`clip_still`) | `pipeline.py` 1187 |
| `_judge` → `script.match` (phrase ↔ image) | 3 | `pipeline.py` 1239 |
| `annotate.locate` (placer une flèche, au rendu) | 4 | `annotate.py` 224 |

→ La même image (`clip_still`) part dans **3 appels séparés** juste l'un après l'autre (revue des flèches, effets,
zoom).

### 3. Une vérification est-elle gardée quand la vidéo revient ? — **OUI dans le même projet, NON ailleurs**

| Cas | Gardée ? | Preuve |
|---|---|---|
| Même projet, « Chercher plus » | **Oui** | `finder.py` l. 578 : une vidéo déjà dans `verifs` n'est pas revérifiée |
| Même projet, changement d'angle | Sans objet | l'angle change avant la recherche d'images |
| Même projet, **relance après une erreur** de la recherche d'images | **Non** | `run_images` (`pipeline.py` l. 699) recrée `sug` à vide (l. 729) : tout est revérifié |
| Autre version FR/AR du même Short | **Non** | chaque version a ses propres plans : la vidéo est regardée à nouveau |
| Autre projet | **Non** | aucun cache entre projets |

Mesuré dans la base (24 projets) : **336 vérifications pour 291 vidéos distinctes → 45 regards en trop (13 %)**, dont
**21 entre les versions FR et AR d'un même Short**. Depuis le 25/10 : **107 vérifications** (= les 107 appels du
journal) dont **8 en trop (7,5 %)**.

Attention : une vérification juge la vidéo **par rapport aux plans du projet**. Pour un autre projet, ou une autre
version, les plans sont différents : on ne peut pas réutiliser le verdict tel quel (🔴 pour un simple cache), mais
on peut **regarder une fois pour les plans de toutes les versions** (🟡 ci-dessous).

### 4. Quel budget de réflexion par étape ? — **presque partout : aucun (le modèle décide)**

Fixé seulement à 3 endroits : `finder._sort_one` = 0 (`finder.py` l. 193), `tone.guess` = 0, `script.revise` = 1024
(`script.py` l. 173, commentaire : « mesuré : 56 s → 10 s, aussi bon »). Partout ailleurs : réflexion libre.

| Étape | Appels | Coût réflexion | Part de la réflexion dans l'étape | Réflexion moyenne / appel |
|---|---|---|---|---|
| finder._watch | 107 | 0,352 $ | 14 % | 877 tokens |
| storyboard.critique (Pro) | 8 | 0,215 $ | **57 %** | 2 238 |
| script.match | 23 | 0,197 $ | **47 %** | 2 281 |
| sources.find_boxes | 65 | 0,134 $ | 29 % | 550 |
| annotate.locate | 32 | 0,097 $ | **52 %** | 805 |
| sources.retime | 30 | 0,095 $ | 24 % | 846 |
| script.critique (Pro) | 2 | 0,078 $ | **75 %** | 3 242 |
| storyboard.revise | 8 | 0,067 $ | 56 % | 2 220 |
| planner.plan_video (Import) | 5 | 0,067 $ | 74 % | 3 556 |
| annotate.review | 8 | 0,043 $ | 43 % | 1 432 |
| (toutes les autres) | — | 0,47 $ | — | — |
| **Total** | 523 | **1,72 $** | **30 % du coût total** | |

Les étapes qui **regardent** (vérification, logos, recalage, contrôle, flèches, effets, zoom) dépensent **0,82 $ de
réflexion** pour des questions surtout visuelles (« où est l'action ? », « y a-t-il un logo ? »).

### 5. Combien de relectures n'ont rien changé ? — **aucune pour le storyboard ; corrections relancées souvent**

Dans la base (17 storyboards) :
- La relecture Pro du storyboard (`storyboard.critique`) a **toujours** changé quelque chose : **2 à 6 corrections
  par storyboard, 0 relecture inutile**. → 🔴 ne pas la supprimer.
- La correction automatique (`storyboard.revise`) a été lancée dans **13 storyboards sur 17**, et **deux fois** dans 4
  d'entre eux.
- Le juge phrase ↔ image du storyboard (`storyboard.illustration`, `pipeline.py` l. 429) est appelé **avant chaque
  tentative de correction** : 14 appels pour 8 storyboards depuis le 25/10. Au 2ᵉ tour il **rejuge tous les plans**,
  même ceux que la correction n'a pas touchés.
- Le juge après téléchargement (`_judge`, l. 1239) : **9 appels avec images pour 6 projets** → 3 rejugements, dont les
  cas `_swap_clips` (l. 1637 : un clip échangé → **tout** le script rejugé) et `_rejudge` (l. 1696 : une phrase changée
  à la main → **toutes** les phrases rejugées, avec 3 images chacune).

### 6. Que refait-on alors que c'était déjà réussi ? — **4 cas**

| Situation | Ce qui est refait sans raison | Preuve |
|---|---|---|
| Une phrase ou un clip changé à la main, ou un clip échangé par le juge | le jugement de **toutes** les phrases (3 images chacune) | `_rejudge` l. 1696, l. 1637 |
| 2ᵉ tour de correction du storyboard | le jugement de **tous** les plans | l. 429 |
| « Revenir aux images » puis retélécharger | les clips inchangés sont gardés (bien), **mais** passe de nettoyage, revue des flèches, effets et zoom **refaits pour tous les plans** | l. 1172, 1179, 1186, 1187 |
| Relance de la recherche d'images après une erreur | **toutes** les vidéos déjà regardées | l. 729 |
| « Refaire avec cette voix » | le placement des flèches (la fenêtre du clip bouge un peu → le cache exige une fenêtre identique) | `annotate.py` l. 224 |

Déjà bien gardés : le choix de la musique (`_choose_music` l. 2007, `music_chosen`), les flèches entre l'aperçu et
le rendu final (`annotate.py` l. 224), la zone de zoom (l. 1920), les clips inchangés au retéléchargement, l'analyse
du Short modèle pour une nouvelle version, la fiche d'une idée.

### 7. Images/s et résolution par étape — **où c'est plus que nécessaire**

| Étape | Ce qui est envoyé | Nécessaire ? |
|---|---|---|
| finder._watch | lien YouTube entier, 0,5 img/s, **résolution par défaut** (≈ 20 600 tokens vidéo / appel) | 0,5 img/s déjà réduit (chantier « modèles moins chers »). La **résolution** peut sans doute baisser : on demande « cette scène existe-t-elle ? », pas un détail fin. 🟡 |
| sources.retime | morceau téléchargé, 4 ou 2 img/s | Oui : il faut la seconde exacte. |
| sources.describe | même morceau, 1 img/s (défaut) | Redondant avec retime qui le regarde déjà à 2-4 img/s. 🟡 fusion |
| sources.orientation | même morceau, 0,5 img/s | Question minuscule, posée séparément. 🟡 fusion |
| Images fixes (`sources.still`, l. 844) | 640 px de large, résolution par défaut | `find_boxes` : garder (coordonnées précises). Juge phrase ↔ image : une résolution moyenne suffit sans doute. 🟡 |

### 8. Autres appels identiques possibles

- **Versions FR/AR** : la même vidéo candidate regardée une fois par version (21 fois dans l'historique).
- **Même image dans 3 appels** : `annotate.review`, `effects.decide`, `effects.auto_zoom` (l. 1179-1187).
- **Seconde passe de nettoyage** (`leftover_text`, l. 1172) sur des clips **gardés** d'un téléchargement précédent,
  déjà vérifiés la première fois.
- **Journal** : il ne note ni l'adresse de la vidéo, ni le projet, ni les tokens en cache : impossible de compter
  exactement les doublons après coup. Le compléter (🟢) rendra les prochaines mesures exactes.
- Déjà corrigé : l'appel de test d'`AITagsGenerator` à chaque démarrage (3 appels le 25/10, audit point 6).

---

## Le tableau des doublons et des propositions

Coûts réels = journal du 25 au 27/10. Économies = sur cette même période.

### 🟢 Sans risque pour la qualité (ne pas refaire, garder un résultat)

| # | Proposition | Preuve | Coût concerné (journal) | Économie estimée |
|---|---|---|---|---|
| G1 | Rejuger **seulement** les phrases changées (garder le verdict des autres) | `_rejudge` l. 1696, swaps l. 1637 | juge avec images : 0,29 $, dont ≈ 1/3 de rejugements | **≈ 0,10 $ (1,7 %)** |
| G2 | 2ᵉ tour du storyboard : rejuger seulement les plans corrigés | l. 429 | juge sans images : 0,13 $ | **≈ 0,05 $ (0,8 %)** |
| G3 | Retéléchargement : garder flèches revues, effets, zoom et nettoyage des **clips inchangés** (même clé que les clips gardés) | l. 1172-1187 | ≈ 0,04 $ par retour en arrière | **≈ 0,03 $ par « Revenir aux images »** |
| G4 | Relance de la recherche d'images : garder les vérifications déjà faites (même lien + mêmes plans) | l. 729 | 14 à 18 regards × 0,023 $ | **≈ 0,30-0,40 $ par relance** (rare) |
| G5 | Journal : noter projet, lien vidéo et tokens en cache | `gemini_ai_generator.py` l. 38 | 0 $ | mesure exacte de la vraie facture et des doublons |
| | **Total 🟢 sur la période** | | | **≈ 0,15 $ (≈ 3 %)** + G3/G4 à chaque occurrence |

### 🟡 À tester (très probablement sans perte, à vérifier avant)

| # | Proposition | Preuve | Coût concerné | Économie estimée | Risque à mesurer |
|---|---|---|---|---|---|
| Y1 | **Limiter la réflexion** des étapes qui *regardent* (vérification, logos, recalage, contrôle, orientation, flèches, effets, zoom) à un petit budget | Q4 | réflexion de ces étapes : 0,82 $ | **≈ 0,57 $ (10 %)** | verdicts moins justes sur les cas difficiles |
| Y2 | **Résolution basse** pour `finder._watch` (paramètre de résolution des médias de Gemini) | `finder.py` l. 867 | vidéo regardée : 1,65 $ | **≈ 1,1 $ (19 %)** | petits détails ratés → mauvais « équivalente » ; *paramètre à vérifier dans la doc Google pour Gemini 3* |
| Y3 | **Un seul regard** sur chaque vidéo téléchargée : recalage + orientation + contrôle dans le même appel | Q2 | orientation 0,12 $ + contrôle 0,24 $ | **≈ 0,30 $ (5 %)** | une consigne plus longue peut moins bien répondre à l'une des 3 questions |
| Y4 | Revue des flèches + effets + zoom **en un seul appel** (même image) | l. 1179-1187 | 0,25 $ | **≈ 0,13 $ (2,3 %)** | idem |
| Y5 | Versions FR/AR : **regarder chaque vidéo une fois** pour les plans de toutes les versions | Q3 | 7,5 % des regards | **≈ 0,18 $ (3 %)** | liste de plans plus longue dans un seul appel |
| Y6 | Relectures **Pro → Flash** (storyboard et script) | `ai_models.py` l. 31 | 0,48 $ | **≈ 0,32 $ (5,5 %)** | **le plus risqué** : ces relectures corrigent toujours 2 à 6 choses ; à tester en dernier |
| Y7 | Images du juge phrase ↔ image en **résolution moyenne** | l. 1239 | images du juge : 0,16 $ | **≈ 0,08 $ (1,4 %)** | images ambiguës mal jugées |

Les économies se recouvrent en partie (Y1, Y2 et Y5 touchent toutes la vérification) : les totaux ci-dessous en
tiennent compte.

### 🔴 À écarter

| Idée | Pourquoi |
|---|---|
| Supprimer le recalage (`retime`) | Mesuré : le moment de la vérification était faux de quelques secondes (commentaire `sources.py` l. 558). |
| Supprimer la relecture du storyboard | Elle a corrigé 2 à 6 choses sur **chacun** des 17 storyboards. |
| Supprimer la seconde passe de nettoyage | Elle a été ajoutée après un texte resté à l'image (commentaire `sources.py` l. 658). |
| Descendre la vérification sous 0,5 image/s | Une action courte (un saut, un impact) tombe entre deux images. |
| Un cache des vérifications **entre projets** tel quel | Le verdict dépend des plans du projet : réutilisé ailleurs, il serait faux. |
| Les modèles « Lite » | Déjà testés et rejetés (chantier « modèles moins chers », 23/10). |
| Le cache de contexte de Gemini pour les 3 regards du même fichier | Inutile si Y3 est fait (un seul appel), et ajoute des frais de stockage. |

---

## Plan de test des 🟡 (avant / après sur 3 vrais projets)

**Les 3 projets** (leurs fichiers de travail existent encore) :

| Projet | Sujet | Clips | Vérifications en base |
|---|---|---|---|
| `ad_20261027_183840_ff28` | avions (cestpourca, FR) | 10 | 18 |
| `ad_20261027_195556_8e50` | chameau (lihadha_alsabab, AR) | 7 | 17 |
| `ad_20261020_164128_c0f0` | projet du 20/10 (cestpourca) | 9 | 26 |

**Principe** : le « avant » est **déjà en base** (verdicts, moments, logos, contrôles, flèches, effets, relectures) :
on ne le repaie pas. On rejoue seulement le « après » sur les mêmes entrées, puis on compare.

| Test | Ce qu'on rejoue | Ce qu'on compare au « avant » | Seuil pour adopter | Coût du test |
|---|---|---|---|---|
| Y2 + Y1 (vérification) | les 8 meilleures vidéos vérifiées de chaque projet (24), résolution basse + réflexion limitée | même niveau par plan (exacte / équivalente / partielle / rien) ; moments à ± 2 s | ≥ 90 % d'accord, **0** vidéo choisie qui deviendrait « rien » | ≈ 0,20 $ |
| Y1 (recalage, logos, contrôle) | retime, find_boxes, describe sur les fichiers des 26 clips, réflexion limitée | moments ± 0,5 s ; zones des logos (recouvrement) ; « utilisable » identique | ≥ 90 % identique | ≈ 0,20 $ |
| Y3 (un seul regard) | l'appel fusionné sur les mêmes fichiers | les 3 réponses séparées en base | idem Y1 | ≈ 0,05 $ |
| Y4 (flèches + effets + zoom) | l'appel fusionné sur les mêmes images | flèches et effets en base | ≥ 90 % identique | ≈ 0,03 $ |
| Y7 (juge) | le juge avec images en résolution moyenne | notes bon / moyen / non en base | ≥ 90 % identique, aucun « bon » qui devient « non » | ≈ 0,05 $ |
| Y5 (versions) | 5 vidéos partagées par les versions FR/AR d'anciens groupes (liens YouTube, encore en ligne), plans des deux versions dans un appel | les deux verdicts séparés en base | ≥ 90 % d'accord | ≈ 0,10 $ |
| Y6 (Pro → Flash) | écrire 3 storyboards puis les relire avec Pro **et** avec Flash (le brouillon avant relecture n'est pas gardé en base) | **toi** : tu lis les 3 paires et tu choisis | ta préférence | ≈ 0,25 $ |
| **Total des tests** | | | | **≈ 0,90 $** |

Ordre conseillé : Y2+Y1 d'abord (le plus gros gain), puis Y3/Y4/Y7, puis Y5, et Y6 en dernier.

---

## Économie totale estimée (sur la période du 25 au 27/10, base 5,78 $)

| Ensemble | Économie | Coût restant |
|---|---|---|
| 🟢 seules | **≈ 0,15 $ (≈ 3 %)** + à chaque retour en arrière ou relance | ≈ 5,63 $ |
| 🟢 + 🟡 sans Y6 (les relectures restent en Pro) | **≈ 2,0 $ (≈ 35 %)** | ≈ 3,8 $ |
| 🟢 + 🟡 avec Y6 | **≈ 2,3 $ (≈ 40 %)** | ≈ 3,5 $ |

À garder en tête : le prix de Gemini Flash **double le 1ᵉʳ janvier 2027** (`ai_models.py`). Sans ces économies, la
même activité coûterait environ **11 $** au lieu de 5,78 $ ; avec 🟢 + 🟡 (sans Y6), environ **7 $**.
