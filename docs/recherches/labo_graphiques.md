# Labo : graphiques animés (point 6)

*9 novembre 2026. Les clips sont dans `Downloads/montage_test/graphiques/out/`.*

## La question

Le réalisateur IA note déjà, pour certaines phrases, un **graphique à dessiner** (chiffre, carte, schéma), mais l'app ne sait pas encore le dessiner. Peut-on les fabriquer **automatiquement**, sans personne, assez vite et assez beaux pour un Short ?

Outil testé : **HyperFrames** 0.9.26. Il fait une vidéo à partir d'une page HTML animée (GSAP). Il tourne en local avec `npx`, sans compte et sans internet au moment du rendu.

## Les demandes réelles du réalisateur

| Projet | Phrase | Type | Ce qu'il veut |
|---|---|---|---|
| Grand Stade | 1 | chiffre | compteur jusqu'à « 115 000 مقعد » |
| Grand Stade | 2 | carte | côte atlantique, zoom sur El Mansouria, les 100 ha |
| Grand Stade | 5 | chiffre | « 5 000 000 000 DH » |
| Nador West Med | 1 | chiffre | « 54 MMDH » en doré |
| Nador West Med | 2 | carte | Maroc et Méditerranée, baie de Betoya, routes maritimes |

## 1. Chiffre : un modèle rempli par l'app

`chiffre.html` : un compteur qui monte jusqu'au chiffre, un petit rebond, une barre, puis le mot (« مقعد »), sur un fond sombre avec des rayons dorés.

- Rendu : **27 s** pour un clip de 3,6 s.
- L'arabe s'affiche bien (police Tajawal de l'app).
- **Les mots doivent venir des faits** : le titre « ملعب الحسن الثاني » du test est un nom que la vérification des faits avait refusé.

## 2. Carte : un modèle rempli par l'app

`carte.html` : vue large (Espagne, Maroc, le détroit), puis zoom fluide jusqu'à la baie de Betoya. Ensuite : le point rouge qui pulse, le nom « الناظور غرب المتوسط », la route maritime en pointillés, et « 120 000 سفينة فالعام » (un chiffre des faits) dans un cadre sombre.

- **Les côtes seulement, pas de frontières** : on évite la question de la frontière Maroc / Sahara. Les terres sont d'une seule couleur, et les noms (المغرب, إسبانيا, طنجة) donnent les repères.
- Données : Natural Earth 1:10 m (world-atlas), sur le PC.
- Deux pièges corrigés :
  - des morceaux de côte tournés à l'envers coloraient toute la mer : ils sont remis à l'endroit ;
  - redessiner toutes les côtes de la planète à chaque image prenait **3 min** pour 5 s : la carte est maintenant dessinée une fois puis agrandie, soit **34 s**.

## 3. Schéma : écrit par Gemini

Il y a trop de cas possibles pour des modèles tout faits. Gemini écrit donc l'animation entière : une page HTML avec ses règles (nos polices, aucune ressource extérieure, une seule timeline, les mots de la phrase et des faits, le haut et le bas laissés libres pour le bandeau et les sous-titres).

| Cas | Flash | Pro |
|---|---|---|
| A. « Ce plafond artificiel emprisonne la chaleur » | **clair** : flèches qui montent de la Terre, plafond, « CHALEUR PIÉGÉE » qui redescend | confus : soleil, avion, bloc rouge |
| B. « Gaz à 600° contre air à −50° » | **réacteur**, jet chaud et jet froid qui se croisent, cristaux qui apparaissent | tuyau en Y abstrait, texte qui chevauche |
| C. « Quais profonds de 22 m » (darija) | **coupe** du quai et de l'eau, le navire, cadre « 22 ميترو » | coque en forme de seau, moins lisible |
| Temps d'écriture | 30-55 s | 75-125 s |
| Coût par schéma | ~2-3 centimes | ~20-25 centimes |

- **Flash gagne les 3**, pour 10 fois moins cher.
- Les 6 schémas se rendent en **20-28 s** chacun.
- Défauts vus :
  - des étiquettes trop petites pour un téléphone (il faudra un minimum de 48 px) ;
  - un schéma déborde un peu dans la zone du haut ;
  - 1 erreur sur 6 que l'outil de contrôle (`hyperframes lint`) attrape. Dans ce cas, on redemanderait à Gemini une fois.

## Ce qu'on en tire (proposé)

1. **Chiffre** et **carte** : des modèles fixes, remplis par l'app. Le réalisateur donnerait des champs précis : chiffre, unité, lieu. Les coordonnées viendraient d'OpenStreetMap (Nominatim), pas de l'IA.
2. **Schéma** : Gemini Flash l'écrit, le contrôle tourne, une seule nouvelle demande s'il y a une erreur, puis le rendu.
3. Dans le montage pro, le graphique devient **un plan comme un autre** : sous-titres et bandeau par-dessus, visible et remplaçable dans la timeline. Il est fabriqué en parallèle de la recherche d'images (20-35 s chacun).
4. HyperFrames est figé à la version 0.9.26 (`npx hyperframes@0.9.26`). Il faut Node, qui est déjà installé.
