# Labo « montage Brut » (14 → 16 novembre 2026)

**But** : comprendre comment Brut et DW montent leurs Shorts d'actualité, puis tester leur méthode sur un vrai projet de l'app, à l'aveugle.

**Résultat** : le style **Brut** est devenu le style **par défaut** du montage pro (commit `62c19a2`, fusion `16af48f`).

## 1. Les 7 Shorts analysés

| Nom | Chaîne | Vidéo YouTube | Durée | Plans | Plan médian | Plan moyen |
|---|---|---|---|---|---|---|
| brut1 | Brut (Darmanin, affaire Lyhanna) | `DUxjrwUamq8` | 96 s | 30 | 3,2 s | 3,2 s |
| brut2 | Brut (Bardella contre Mediapart) | `_zlzQdXwEO4` | 55 s | 12 | 4,1 s | 4,6 s |
| brut3 | Brut (la sentinelle du mémorial) | `QV5_5f4yi1E` | 77 s | 13 | 4,3 s | 5,9 s |
| dw1 | DW arabe (Mercedes, usines) | `P2EoPozmYBI` | 88 s | 16 | 5,3 s | 5,5 s |
| dw2 | DW arabe (Nvidia) | `g28z42r4sY8` | 46 s | 11 | 4,0 s | 4,2 s |
| dw3 | DW arabe (Mada Masr) | `Oplv-ahAhEA` | 104 s | 22 | 4,6 s | 4,7 s |
| dw4 | DW arabe (pièces du F-35) | `fW5sqXnJvYo` | 64 s | 10 | 6,6 s | 6,4 s |

Tous les Shorts sont en 1080×1920 à 25 i/s. **Notre ancien montage** coupait 2 à 3 fois par phrase, avec des plans de **1,2 à 3 s**.

## 2. Comment on a mesuré

1. **Les coupes** : la même détection de plans que l'app (ffmpeg, changement de scène).
2. **La voix** (Brut seulement) : Whisper, avec l'heure de chaque mot, pour mesurer le débit et l'endroit des coupes par rapport aux mots et aux phrases.
3. **Gemini** a regardé chaque vidéo et décrit, pour chaque plan : la valeur de plan, ce qu'il montre, si l'image est réelle ou d'illustration, le mouvement, le texte à l'écran, le son et la raison de la coupe. Il a aussi décrit l'accroche, le moment fort, la fin et les règles.
4. **Planches** : une image par seconde de chaque vidéo, que j'ai regardées moi-même.

⚠️ **Gemini a inventé une voix off** dans des Shorts DW où Whisper n'en a trouvé aucune. **Pour le son, on croit les mesures, pas Gemini.** Pour l'image, Gemini et les planches sont d'accord.

**Fichiers** (dans `Downloads\montage_test\labo_brut\`) :
- `coupes.json` : l'heure de chaque coupe et la durée de chaque plan ;
- `voix.json` : les phrases et les mots Whisper, le débit et l'endroit des coupes ;
- `gemini_<nom>.json` : l'analyse plan par plan ;
- `<nom>.jpg` : les planches.

Les scripts du labo étaient dans le dossier temporaire de la session et ont été perdus. Pour refaire la mesure, il suffit de recombiner la détection de plans de l'app, Whisper (`adaptation/parole_worker.py`) et un appel Gemini vidéo qui renvoie le format JSON décrit au point 3.

## 3. Les règles Brut mesurées

1. **Des plans longs** : une moyenne de 3,2 à 5,9 s chez Brut et de 4 à 6,4 s chez DW. Le plus long plan va jusqu'à 19 s : l'extrait de son réel du soldat.
2. **Une phrase = un plan.** Les coupes tombent au début d'un mot (écart médian de 0,06 à 0,08 s chez brut1 et brut2), et le plus souvent quand une nouvelle phrase commence : 18 coupes sur 29 dans brut1, 10 sur 11 dans brut2.
3. **L'accroche** (de 4 à 10 s) : les vraies images du sujet, avec un **bandeau rouge au milieu** et le titre en blanc et en gras sur 2 ou 3 lignes. Le bandeau n'apparaît que pendant l'accroche. Le logo est en haut à droite tout le long de la vidéo.
4. **Les sous-titres** sont petits, blancs, **au milieu de l'écran**, et montrent une phrase entière à la fois, sans mot surligné. DW met plutôt ses textes **en bas**, dans des cadres bleus.
5. **Les images** :
   - des images réelles dès qu'il y en a (de 40 à 100 % des plans) ;
   - sinon des images symboliques assumées : un marteau de juge, des dossiers, une façade ;
   - des captures d'articles qui défilent quand on parle d'une enquête.
6. **Le moment fort** (brut3) : la voix se tait et on entend **le vrai son de la scène**, pendant 8 s ici. La vidéo démarre aussi sur 3 s de son réel, avant le premier mot.
7. **Aucun effet** : 100 % de coupes franches (sur les 7 Shorts, d'après Gemini et les planches), aucun zoom ajouté, aucun « whoosh ». Il y a un seul bruitage, un marteau de juge dans brut1.
8. **Le son** : une voix continue d'environ 3 mots par seconde (de 2,75 à 3,33), et une musique **basse ou très basse**, ou même absente.
9. **La fin** : « Abonne-toi » avec le nom du ou de la journaliste, ou un écran noir avec le logo.

DW, sans voix off dans les vidéos mesurées : le même rythme de 4 à 6 s, des textes dans des cadres colorés qui changent toutes les 3 à 5 s, une question en grand comme transition, et la musique d'un bout à l'autre.

## 4. Le test à l'aveugle (Chefchaouen, Prince Moulay Hassan)

Les 4 styles sont montés à partir du même projet, avec le même stock, la même voix et les mêmes plans principaux choisis à la main.

| Fichier (`labo_styles\`) | Style | Note de l'utilisateur |
|---|---|---|
| `video_3.mp4` | **A : Brut** : une phrase = un plan, un bandeau d'accroche, les sous-titres au milieu, le nom de la chaîne en haut à droite, pas d'effets, une musique basse | **9/10** |
| `video_4.mp4` | **C : Brut rythmé** : comme A, mais une phrase de plus de 5 s reçoit un 2e plan | **9/10** |
| `video_1.mp4` | **D : DW** : les phrases dans des cadres colorés, une musique plus présente, une question comme accroche | 8 à 8,5/10 |
| `video_2.mp4` | **B : l'ancien montage** (le témoin) | 7/10 |

`brut_dans_l_app.mp4` est le rendu final, fait par l'app elle-même après l'intégration.

**Décisions de l'utilisateur** : la méthode Brut, mais **pas son identité**. Le bandeau prend la couleur de la chaîne, pas le rouge Brut. Le nom de la chaîne est écrit en texte, puisqu'il n'y a pas encore de logo. Ce style est le style par défaut.

## 5. Ce qui est codé dans l'app

Le montage pro, avec la règle C :
- **un plan par phrase** (le plan principal choisi), et un 2e plan seulement si la phrase dure plus de 5 s. Ce 2e plan arrive vers 60 % de la phrase, au début d'un mot ;
- **un titre d'accroche** écrit par l'IA dans la langue de la chaîne, dans un bandeau à la couleur de la chaîne, sur les 2 premières phrases, au-dessus des sous-titres ;
- **les sous-titres au milieu** de l'écran ;
- **la musique à 35 %**, sans aucun effet sonore ;
- **le nom de la chaîne en haut à droite**, en texte.

L'ancien style reste disponible pour une version qui le demande.

## 6. Pas encore fait

- **Le vrai son d'une scène** : la musique et la voix se taisent sur un extrait réel (la règle 6). C'est le prochain chantier montage.
- **Les captures d'articles qui défilent** (la règle 5).
- **Les logos des chaînes**, pour remplacer le nom écrit en texte.
- **Un bouton « ancien style / Brut »** dans l'interface.
- **Une fin « Abonne-toi »** (la règle 9).
- **Wikimedia Commons et les photos animées**, pour avoir plus d'images réelles (à faire en réutilisant le prototype « photos + effets »).
