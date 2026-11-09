# Le montage modifiable (la timeline)

*Mis à jour le 9 novembre 2026.*

Dans **Adaptation → Idée d'abord**, à l'étape **Aperçu**, la vidéo est montée par l'IA. Sous l'aperçu, la **timeline** montre tout ce qui la compose, et te laisse **changer n'importe quel morceau avant de publier** : une image, son cadrage, un bandeau, un mot des sous-titres, le volume de la musique sur un passage, un effet sonore, la manière de dire une phrase.

> Pour l'instant, la timeline existe seulement pour le **montage pro** (Idée d'abord), sur ordinateur, et **avant** la publication.

![L'aperçu et sa timeline](img/montage/01_apercu_et_timeline.png)

## 1. Lire la timeline

| Piste | Ce qu'elle montre |
|---|---|
| **Images** | les plans, avec leur miniature et leur numéro (⌖ = un plan recadré) |
| **Voix** | les phrases dites, et la manière de chacune (Curieux, Chuchoté…) |
| **Bandeau** | le texte affiché en haut, phrase par phrase |
| **Sous-titres** | les mots, 3 par 3 |
| **Musique** | la forme de la chanson (plus c'est haut, plus c'est fort) et tes zones de volume |
| **Effets** | les sons (pop, whoosh, ding…), en losanges |

- Le **trait rouge** suit la vidéo pendant la lecture.
- **Clique un élément** : la vidéo va à ce moment, et le panneau en dessous montre ce que tu peux changer.
- **Clique la règle du temps** (en haut) pour aller à une seconde précise.

## 2. Changer un morceau ou toute la vidéo ?

**Ce que tu changes dans le panneau ne touche que le morceau cliqué.** Pour le cadre des bandeaux et le look des sous-titres, un bouton **« Appliquer à tous »** le met sur toute la vidéo.

| Ce qui change **seulement ce morceau** | Ce qui change **toute la vidéo** |
|---|---|
| un plan (le remplacer, zoom, centrer, couper, supprimer, déplacer sa coupe) | le bouton **Appliquer ce cadre à tous les bandeaux** |
| le texte, le **cadre** d'un bandeau, « pas de bandeau » | le bouton **Appliquer… à tous les sous-titres** |
| les mots, le **style**, la **position**, la **taille** d'un groupe de sous-titres | la chanson, son départ, son volume général, le fondu de fin |
| chaque zone de volume de la musique | — |
| chaque effet sonore | — |
| le texte ou la manière d'une phrase | — |

## 3. Comment l'app choisit les images (Images v2)

Un monteur humain ne cherche pas la scène exacte : il prend une image qui **fait passer l'idée** de la phrase, et qui ne la contredit jamais. L'app fait pareil :

| Étape | Ce qu'elle fait |
|---|---|
| **Le réalisateur IA** | avant de chercher, il décide **comment montrer chaque phrase** : vraies images (actualité), image d'idée, **comparaison** (« en forme de tente » → le stade **et** une tente), **projet** (rendu 3D, maquette), chiffre, carte ou schéma ; 1 ou 2 images par phrase, cherchées en anglais **et dans la langue du pays** (en arabe pour le Maroc). Ses choix sont visibles à l'écran du **stock** (« Le réalisateur IA ») ; les cartes, chiffres et schémas y sont notés « à dessiner (bientôt) » |
| **L'idée de chaque phrase** | une courte description, en anglais, de ce que montrerait n'importe quelle vidéo qui fait passer l'idée (« new apartment buildings, a hand giving keys ») |
| **Recherche par le sens** | un modèle sur ton PC compare chaque plan du stock (3 images de lui) à **chaque phrase**, pas au sujet en général |
| **Repêchage** | un plan écarté comme « hors sujet » mais qui colle bien à une phrase revient dans le stock (badge vert *repêché*) |
| **Contrôle du lieu** (actualité) | une vidéo sur **un autre pays ou une autre ville** (NEOM pour Benslimane, Mayotte pour Casablanca) est écartée — l'autre quartier de la même ville reste |
| **Recherche de secours** | pour une phrase que rien ne fait passer, une vidéo est cherchée sur **Pixabay** et choisie par le sens (badge vert *secours*) ; pas de clip généré par IA en actualité |
| **Variété** | au plus **2 plans de la même vidéo** dans un montage |
| **Relecture** | le montage fini est relu (comme un monteur qui se relit) : chaque plan qui **contredit** sa phrase ou **ne colle pas** est entouré d'**orange** dans la piste Images |

À l'écran du **stock**, une ligne « Images v2 » résume ce qui a été fait. Ces étapes coûtent environ 5 centimes de Gemini par vidéo (la recherche par le sens est gratuite).

## 4. Les images

![Le panneau d'un plan](img/montage/02_plan.png)

- **Plan entouré d'orange (⚠)** : la relecture dit pourquoi il ne colle pas et quoi montrer à la place ; quand le stock a mieux, **Mettre le plan proposé** le remplace en un clic.
- **Remplacer** : clique une miniature de ton stock, ou **glisse-la** sur un plan de la piste Images. Les plans sont **rangés du plus adapté à la phrase au moins adapté** ; ✓ = il fait passer l'idée de cette phrase ; *Pixabay* = un plan de secours.
- **Cadrage** : *zoom* pour serrer l'image (jusqu'à ×1,6), *centrer sur* le sujet (choix de l'IA), la gauche, le centre ou la droite.
- **Couper ce plan en deux** : la 2ᵉ moitié prend un autre plan de ton stock (change-le ensuite si tu veux).
- **Supprimer** : le plan d'avant s'allonge pour boucher le trou.
- **Déplacer une coupe** : glisse la **barre blanche** au début d'un plan. Elle se cale sur le mot le plus proche. Un plan dure au moins 1 seconde.

## 5. La voix

![Le panneau d'une phrase](img/montage/03_voix.png)

Tu peux changer le **texte** d'une phrase et sa **manière de dire** (seulement celles permises pour la famille de récit de la chaîne : pas de chuchoté en actualité, par exemple).

- La voix est **refaite en entier** chez ElevenLabs : quelques centimes, environ 1 minute.
- Les coupes, les effets et les zones de musique **se recalent tout seuls** sur la nouvelle voix (chacun garde sa place dans sa phrase).
- Un nouveau texte **n'est pas revérifié contre les faits** : relis-le.
- **Annuler le dernier rendu** remet l'ancienne voix **sans repayer** ElevenLabs.

## 6. Les bandeaux

![Le panneau d'un bandeau](img/montage/04_bandeau.png)

Change le texte (60 caractères au plus), coche **Pas de bandeau sur cette phrase**, ou choisis le **cadre de ce bandeau** : celui du style de la chaîne, noir, rouge actu, blanc ou bleu (par exemple un bandeau rouge seulement sur la révélation). **Appliquer ce cadre à tous les bandeaux** le met partout.

## 7. Les sous-titres

![Le panneau des sous-titres](img/montage/05_sous_titres.png)

- **Corriger les mots** d'un groupe : chaque mot garde le moment où la voix le dit.
- **Style de ce groupe** : *Nos sous-titres* (le mot dit en couleur) ou un des styles de **Réglages → Bibliothèques → Sous-titres** (Karaoké, Hormozi…).
- **Position** (bas, milieu, haut) et **taille** (60 à 160 %) de ce groupe. Les styles de la bibliothèque ont leur propre « bas », un peu plus près du bord.
- **Appliquer… à tous les sous-titres** met ce look sur toute la vidéo ; **Comme le reste de la vidéo** annule le look propre de ce groupe.

## 8. La musique

![Une zone de volume](img/montage/06_musique_zone.png)

- Clique la piste Musique : **chanson**, **départ** dans la chanson (en secondes), **volume général**, **fondu à la fin**.
- **+ Baisser / monter une partie au curseur** : crée une zone de 3 secondes au trait rouge. Règle son volume (0 à 200 %) et ses bornes, ou **glisse-la** sur la piste. Pratique pour laisser entendre une phrase chuchotée.

## 9. Les effets sonores

![Le panneau d'un effet](img/montage/07_effet.png)

- **Glisse un losange** pour déplacer le son.
- Au clic : changer le **son** (ceux allumés dans Réglages → Bibliothèques → Effets sonores), son **moment**, son **volume**, l'**écouter**, le **supprimer**.
- **+ Ajouter un son au curseur** : sans rien sélectionner, le bouton est dans le panneau.

## 10. La démo instantanée

![La démo par-dessus la vidéo](img/montage/08_demo.png)

Dès que tu changes quelque chose, l'aperçu montre une **DÉMO** (étiquette jaune) **par-dessus la vidéo**, sans attendre : lance la lecture ou clique la timeline pour la voir.

| Changement | Dans la démo |
|---|---|
| texte, cadre, bandeau enlevé | ✅ dessiné tel quel |
| mots, position, taille des sous-titres | ✅ très proche (l'ancien texte est flouté) |
| zoom et centrage d'un plan | ✅ très proche |
| plan remplacé | ⚠️ son **image fixe** |
| effet ajouté ou déplacé | ✅ joué à son moment (l'ancien reste audible) |
| zone de volume de la musique, style de la bibliothèque, voix | ❌ seulement après **Refaire l'aperçu** |

La démo est approximative : la vraie vidéo, c'est **Refaire l'aperçu**.

## 11. Appliquer, comparer, annuler

En haut de la timeline :

| Bouton | Ce qu'il fait |
|---|---|
| *compteur* « 3 changement(s) à appliquer » | rien n'est envoyé tant que tu n'as pas cliqué Refaire |
| **Refaire l'aperçu** | la vidéo est refaite avec tous tes changements, le lecteur saute au premier changement. ≈ 5 s si tu n'as touché qu'au son, ≈ 30 s sinon, ≈ 1 min avec la voix |
| **Voir l'avant / Voir l'après** | passe de l'ancienne à la nouvelle vidéo, au même moment (cadre jaune = l'avant) |
| **Annuler le dernier rendu** | revient au montage d'avant (et à sa voix) |
| **Oublier mes changements** | efface ce que tu n'as pas encore appliqué |

Après chaque rendu, le **contrôle automatique** du son repasse (chaque phrase à sa place, volume). Le bouton **Valider cet aperçu** ne s'allume que s'il est vert.

## 12. À savoir

- **« Revenir au stock »** refait un montage neuf par l'IA : tes changements dans la timeline seraient perdus. L'app te le demande avant.
- Un seul rendu à la fois : pendant un rendu, la timeline attend.
- La **recette** de la vidéo (Dashboard) note que le montage a été modifié par toi, combien de fois, les cadrages, les zones de musique et le cadre des bandeaux.
- Tout ça ne coûte **aucun crédit Gemini**. Seul un changement de voix coûte un peu chez ElevenLabs.
