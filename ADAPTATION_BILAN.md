# Adaptation : le bilan

Ce qu'on a construit, **pourquoi**, et **comment ça marche en bref**.
Le mode d'emploi détaillé (chaque bouton, chaque écran) est dans [ADAPTATION.md](ADAPTATION.md).

État au 23/10/2026 : la partie Adaptation est **presque terminée**. Il reste un test (Google Lens via SerpApi, voir la fin).

---

## Le but

Refaire un **Short viral « explicatif »** (une voix off qui explique des images) pour nos chaînes, en **français** et en **arabe standard**, avec nos voix ElevenLabs.

On ne copie pas la vidéo :
- on reprend sa **recette** : la question, le déroulé, le rythme ;
- on repart des **vidéos d'origine** des images ;
- on écrit **notre propre script**.

**Pourquoi :** les vidéos explicatives marchent, et l'app peut mesurer ce qui marche (Dashboard). La localisation FR/AR touche un public que le Short d'origine ne touche pas.

---

## Comment ça marche, en bref

```
Short modèle ──► 1. Analyse ──► 2. Script ──► 3. Images ──► 4. Montage ──► 5. Publication
                (Gemini)       (par chaîne)   (recherche,   (voix, effets,
                                               vérification) règles, contrôle)
```

1. **Analyse** : Gemini regarde le Short. Il en tire les plans, la question, les crédits visibles, et les affirmations douteuses à ne pas reprendre.
2. **Script** : en mode **Script d'abord** (par défaut), l'IA écrit d'abord le meilleur script pour la rétention, avec **l'image voulue** pour chaque phrase. Un modèle plus puissant le relit. **Tu valides.**
3. **Images** : pour chaque plan, l'app cherche des vidéos, l'IA les **regarde** et les juge (exacte, équivalente, partielle, rien), puis l'app choisit le meilleur moment. **Tu valides**, ou tu changes.
4. **Montage** : seuls les moments choisis sont téléchargés et nettoyés. Ensuite viennent la voix ElevenLabs, les sous-titres, les bandeaux, les flèches, les effets, les sons et la musique, puis un contrôle automatique.
5. **Publication** : la vidéo arrive dans la file avec son titre, sa description, ses tags et ses crédits.

L'autre mode, **Sources d'abord**, trouve d'abord les vidéos et écrit le script ensuite avec les clips trouvés.

Le code est dans `adaptation/` :

| Fichier | Rôle |
|---|---|
| `pipeline.py` | les étapes du projet |
| `reference.py` | l'analyse du Short modèle |
| `storyboard.py`, `script.py` | l'écriture et la relecture |
| `finder.py`, `imagesearch.py` | la recherche et la vérification des vidéos |
| `sources.py` | le téléchargement, le découpage, le nettoyage |
| `render.py`, `effects.py`, `annotate.py`, `sfx.py` | le montage |
| `checks.py` | le contrôle final |

---

## Ce qu'on a construit, et pourquoi

### 1. La base (17/10)
Le parcours complet : modèle → sources → script (relecture obligatoire) → aperçu → rendu → publication. Il y a aussi les voix par chaîne (Réglages → Voix) et l'arabe de droite à gauche.
**Pourquoi :** le prototype fait à la main sur le tram (16/10) avait plu (7,5/10). Il fallait le rendre répétable.

### 2. Trouver les vidéos d'origine (17-18/10)
L'app lance quatre recherches à la fois : le **compte crédité**, **YouTube**, la **langue du pays**, et la **recherche par image** (Yandex). Ensuite **Gemini regarde** les meilleures vidéos et dit, plan par plan, si elles conviennent. Une longue compilation n'est téléchargée qu'autour des bons moments.
**Pourquoi :** chaque méthode a gagné sur un cas réel. La compilation du tram a été trouvée par le compte crédité, les puits au Vietnam par la langue locale, les compilations VK par l'image.

### 3. Script d'abord (18/10)
L'app écrit d'abord le script, avec l'image voulue pour chaque phrase, puis cherche ces images. C'est devenu le mode par défaut.
**Pourquoi :** en partant des clips trouvés, le script subissait les images. En partant du script, on écrit pour la **rétention** (accroche, promesse, montée, réponse), puis on cherche ce qu'il faut.

### 4. Une version différente par chaîne (18-19/10)
Chaque chaîne reçoit un **angle** différent (« Arnaque ou coup de génie ? », « L'erreur fatale »…), avec sa propre accroche et sa propre fin. Le modèle n'est analysé qu'une fois, et les recherches sont partagées entre les versions.
**Pourquoi :** une traduction de la même vidéo n'apprend rien. Deux angles différents font un **test A/B** (onglet Versions FR / AR du Dashboard).

### 5. Le montage qui retient (18-21/10)
- **Flèches et cercles** sur la cible, qui la suivent jusqu'au moment fort.
- **Effets choisis par l'IA** : ralenti, zoom, arrêt sur image, transition.
- **14 règles automatiques** : pas de temps mort, accroche juste avant l'instant fort, cadrage sur le sujet, lumière, coupes sur le rythme, fin en boucle, miniature…
- **Le juge phrase ↔ image** : l'IA vérifie qu'on voit ce qu'on entend.
- **5 styles visuels**, un par chaîne.

**Pourquoi :** les Shorts qui marchent sont montés comme ça. Chaque règle vient d'un défaut vu sur une vraie vidéo.

### 6. L'extrait du modèle, en dernier recours (18/10)
On peut prendre **3 secondes au plus** du Short modèle, nettoyées et créditées, avec **2 extraits au plus** et jamais pour l'accroche.
**Pourquoi :** une scène introuvable ne doit pas bloquer la vidéo. Les limites évitent de copier le modèle.

### 7. Télécharger sans cookies (22/10)
L'app utilise yt-dlp avec **bgutil** (des jetons « PO token », servis en local sur le port 4416) et yt-dlp-ejs. YouTube est essayé **sans cookies d'abord**.
**Pourquoi :** des vidéos marquées « bloquées » se téléchargeaient en fait sans cookies, en 1080p. Les cookies s'abîmaient et posaient des risques.

### 8. Les effets sonores (22-23/10)
15 sons **CC0** (`assets/sfx/`), placés par des **règles**, pas par l'IA :

| Moment | Son |
|---|---|
| flèche ou cercle, transition principale | whoosh |
| arrêt sur image | déclic |
| ralenti sur le moment fort | montée puis impact |
| un chiffre apparaît | pop |

Il y a **4 sons au plus** par vidéo, à 3 s d'écart. Le moment le plus fort de chaque son tombe sur l'évènement, et les variantes passent à tour de rôle. La page **Réglages → Effets sonores** permet d'écouter, de désactiver, et d'ajouter ses propres sons d'un type qui a une règle.
**Pourquoi :** l'ancien « whoosh » de l'app ne s'entendait pas, ou sonnait comme un souffle. Des règles fixes donnent un résultat prévisible et ne coûtent rien.

### 9. La recette et le Dashboard (22-23/10)
Chaque vidéo garde sa **recette** : mode, angle, voix, musique, style, plans, effets, sons.
- **Ce qui marche** compare les vues et la rétention selon les critères de la recette.
- **Où ils décrochent** montre la courbe de rétention plan par plan.
- **Versions FR / AR** dit quelle version a gagné.
- La **Fiche vidéo** regroupe tout sur une page.
- **Refaire ce style** relance une Adaptation sur un nouveau Short avec la même voix, la même musique et le même style.

**Pourquoi :** on ne devine pas ce qui marche, on le mesure, puis on refait ce qui a marché.

### 10. Les coûts (23/10)
Gemini coûte environ **1,50 $ par projet FR + AR**. Deux réglages font gagner environ 14 % sans perte de qualité :
- les vérifications de vidéos à **0,5 image par seconde** ;
- le tri des titres **sans « thinking »**.

Chaque appel est noté dans `temp/usage/gemini.jsonl`.
**Pourquoi :** les prix de Gemini doublent le 1er janvier 2027.

### 11. Les remontages et l'original (23/10)
- Quand l'app trouve le **remontage d'un autre créateur** qui montre nos scènes, elle lit ce qu'il **crédite** : sa description, et les filigranes à l'image, y compris les filigranes Douyin « nom + 抖音号 ». Elle remonte ainsi jusqu'à l'original : une chaîne YouTube est cherchée et vérifiée, un compte TikTok ou Douyin est donné à ouvrir à la main.
- **S'il n'y a pas d'original**, l'app prend l'**image** d'un remontage exact : uniquement l'image, avec notre voix, notre script et notre montage. Elle la **crédite à l'original** quand un filigrane le nomme. Les textes incrustés du remontage sont effacés.

**Pourquoi :** sur les gouttières, la vidéo d'Insider a mené à la chaîne de The Gutter Guyz, avec 2 vidéos exactes. Sur le cactus, la mode vient de **Douyin**, et seul un remontage avait gardé les filigranes : 微蓝 et 米合勒, les vrais créateurs. Prendre quelques secondes d'image avec notre propre contenu est une pratique normale (décision du 23/10).

### 12. Déposer un fichier (23/10)
Le bouton **📁 Déposer un fichier** existe pour un plan (Script d'abord) ou comme source (Sources d'abord), avec **le crédit** à afficher.
- Le fichier est converti en H.264 (une vidéo d'iPhone en HEVC marche aussi).
- Il est vérifié par l'IA comme un lien, puis découpé et crédité.
- Une recherche écrite en chinois ouvre aussi Douyin, Xiaohongshu et Bilibili.

**Pourquoi :** Douyin, Xiaohongshu, Instagram et les comptes TikTok bloquent l'accès automatique par des CAPTCHA. Toi, tu y as accès : tu enregistres la vidéo depuis l'appli, et l'app fait le reste.

---

## Décisions prises (à ne pas refaire sans nouvelle raison)

| Sujet | Décision | Pourquoi |
|---|---|---|
| Voix arabe | **sans tashkeel** (voyelles) | testé : 30 à 50 % plus lent, moins naturel |
| Son « ding » | **retiré** | il sonnait faux sur une conclusion simple (le cactus) |
| Nouveaux moteurs (DuckDuckGo, SerpApi Google Vidéos) | **pas intégrés** | testés sur 4 Shorts, gain presque nul : surtout des remontages |
| Pré-tri par miniature (CLIP, empreintes d'image) | **pas intégré** | il économisait seulement 3 % des vérifications |
| Modèles Gemini moins chers (Lite, 3 Flash Preview) | **refusés** | ils trouvaient 50 % des bonnes vidéos au lieu de 90 % |
| CAPTCHA (Google, TikTok, Douyin) | **jamais contournés** | c'est tromper une protection, avec un risque de blocage de l'IP ou des comptes. On passe par toi (fichier déposé) ou par une API autorisée |
| Bilibili, Douyin automatiques | **pas intégrés** | depuis ce PC : erreurs 412 et cookies exigés. Le fichier déposé les remplace |
| Image d'un remontage | **autorisée** si aucun original | seule l'image, notre contenu par-dessus, créditée |
| Films, séries, TV | **jamais** | droits d'auteur, et Content ID |
| `git push` | **jamais par Claude** | tu pousses toi-même |

---

## Ce qui reste

- **Test Google Lens via SerpApi** sur des captures propres des plans (environ 6 recherches sur les 250 gratuites du mois). C'est la seule recherche par image autorisée qu'on n'a pas encore vraiment testée.
- **Limites connues** :
  - un léger flou peut rester là où un texte a été effacé ;
  - environ 1 remontage sur 6 seulement cite sa source ;
  - les sujets qui viennent de Douyin demandent ta main (fichier déposé).
- **Hors Adaptation, plus tard si besoin** (Montage auto) : « Refaire ce style », coupes sur le rythme, musique choisie par l'IA, plus de styles de sous-titres, recette « Ranking ».
