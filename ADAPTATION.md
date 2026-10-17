# Adaptation

L'Adaptation refait un **Short viral « explicatif »** (une voix off qui explique des images) pour **tes chaînes**, dans **leur langue**, avec **ta voix ElevenLabs**.

L'app ne copie jamais la vidéo d'origine :
- elle reprend sa **recette** : la question, le déroulé, les bandeaux, le rythme ;
- elle repart des **vidéos sources** des clips ;
- elle écrit **ton propre script**, avec des phrases à toi.

Tu valides à chaque étape importante.

---

## À régler une fois : Réglages → Voix

- **Ajouter des voix** : colle un ou plusieurs identifiants ElevenLabs (un par ligne), puis clique **Ajouter**. Le nom, la langue, l'accent, le genre et l'**extrait officiel** sont récupérés tout seuls. Écouter un extrait est gratuit, cela ne consomme pas de crédits.
- **Toutes les voix sont gardées**, accents régionaux compris. L'accent est affiché : en vert pour l'arabe standard et le français standard ou parisien.
- Tu peux **renommer** une voix (le champ du nom) ou la **retirer** (✕).
- **Chaque chaîne** se règle en bas de l'écran :
  - **sa langue**, qui est aussi celle des titres écrits par l'IA ;
  - **sa voix**, choisie parmi les voix de cette langue ;
  - **sa musique de fond** et **son point de départ**, avec le bouton **Prendre l'instant du lecteur**.

Une chaîne sans voix ne peut pas recevoir d'adaptation.

La clé ElevenLabs doit avoir les permissions **Text to Speech** et **Voices : Read**.

---

## Un projet : espace Adaptation → Nouveau projet

1. **Modèle** : colle le lien du Short viral (YouTube, TikTok…).
2. **Sources (facultatif)** : si tu as déjà les liens des **vidéos d'origine** des clips, colle-les, un par ligne. Sinon, **laisse vide** : l'app te dira quoi chercher (voir plus bas).
3. Coche les **chaînes** qui recevront une version, puis clique **Analyser**.

### Deux façons de construire la vidéo

À la création du projet, choisis :
- **Sources d'abord** : trouver les vidéos, puis écrire le script avec les clips trouvés (décrit ci-dessous) ;
- **Script d'abord** (nouveau) : écrire d'abord **le meilleur script pour la rétention**, avec **l'image voulue** de chaque phrase, puis chercher ces images.

#### Script d'abord : le storyboard

L'IA écrit **un storyboard commun à toutes les langues** et **un texte par langue**, aligné plan par plan :
- **Accroche** (2 à 3 secondes : une question ou un fait surprenant), **Promesse** (la réponse arrive), **Montée** (chaque plan apporte du nouveau), **Réponse** (une phrase complète qui répond à la question) ;
- pour chaque plan, **🎬 l'image voulue** : une vidéo concrète, filmable et trouvable, de préférence une image du modèle (« plan 3 du modèle ») ; et sa **durée minimale** (la phrase la plus longue, toutes langues confondues).

Un modèle plus puissant relit (rétention, langue, images, faits, pas de publicité), puis une correction automatique passe s'il reste un problème. **Tu relis et tu valides chaque langue** : modifier le texte d'une langue ne touche pas les autres ; modifier **une image** (commune) demande de revalider toutes les langues. La validation est refusée si l'accroche dépasse 4 secondes, si une phrase dépasse 7 secondes, si deux plans ont la même image, ou si une phrase est incomplète.

#### Script d'abord : les images, plan par plan

Quand chaque langue est validée, **Chercher les images** (3 à 6 minutes). Pour chaque plan, l'app :
- transforme l'image voulue en recherches, **en anglais et dans la langue du pays** où une telle vidéo a été filmée ;
- lance les 4 recherches (YouTube, langue locale, **par image** quand le plan vient du modèle, compte crédité) ;
- fait **vérifier par l'IA** les meilleures vidéos (deux fois plus que de plans) ;
- **choisit le meilleur moment** pour chaque plan : vidéo exacte, puis équivalente, puis partielle, jamais deux fois le même moment.

Tu vois, plan par plan, **la vidéo choisie et son moment** (« voir ce moment ↗ »), et les autres vidéos trouvées avec un bouton **Choisir · 0:12** pour chaque moment vérifié.

Deux protections :
- une **copie du Short modèle** (un repost, même dans une autre langue) est marquée en rouge et **jamais choisie** : ce serait reprendre son montage ;
- un **remontage d'un autre créateur** (son Short explicatif avec voix off sur les mêmes images) est signalé en jaune et choisi **seulement s'il n'y a rien d'autre**.

Pour chaque plan, tu peux aussi :
- coller **ton lien** et cliquer **Vérifier pour ce plan** : s'il convient, il devient le choix du plan ;
- pour un plan **sans vidéo** : **Adapter la phrase à une image trouvée** (l'IA réécrit la phrase, dans toutes les langues, autour d'une image déjà trouvée et vérifiée), ou **Retirer ce plan** (la vidéo se fait sans lui, il en faut au moins 3).

#### Script d'abord : télécharger et monter

Quand chaque plan a sa vidéo, **Télécharger les images choisies** (2 à 5 minutes) :
- seuls **les moments choisis** sont téléchargés (une vidéo courte entière), image **et** son ;
- chaque plan reçoit **son clip**, coupé sur son moment et assez long pour sa phrase, **nettoyé** comme d'habitude (recadrage, logos effacés) ;
- l'IA **contrôle chaque clip** : un présentateur, un texte incrusté, un écran partagé, une interview… le refusent (un simple logo non, il est effacé) ;
- les **crédits** citent les chaînes de toutes les vidéos utilisées.

Tu arrives à l'écran **Script** habituel : chaque phrase a déjà son clip. Si un clip est refusé, change-le dans la liste ou clique **← Revenir aux images** pour choisir un autre moment. Ensuite : voix, aperçu, rendu, comme d'habitude. En « Script d'abord », l'effet de secousse et les bruitages ne s'appliquent qu'aux vrais chocs.

### Si tu n'as pas les sources : « Ce qu'il faut télécharger »

L'app analyse le modèle, puis **cherche les vidéos de quatre façons à la fois**. Chaque méthode a gagné sur un cas réel :

| Méthode | Ce qu'elle fait | Elle a trouvé… |
|---|---|---|
| **Compte crédité** | les vidéos du compte cité à l'écran (« Credits: @… ») | la compilation d'origine du tram (6 scènes sur 7) |
| **Recherche YouTube** | des recherches en anglais, écrites par l'IA | d'autres compilations de trams |
| **Langue locale** | l'IA devine **le pays** de chaque scène et cherche **dans sa langue** (vietnamien, turc, russe…) | de vraies vidéos de puits au Vietnam et en Turquie, que l'anglais ne trouvait pas |
| **Par image** | une image propre de **chaque plan** du Short est cherchée sur **Yandex** | des compilations VK et turques avec les scènes exactes |

Puis l'IA **vérifie automatiquement les 8 meilleures vidéos** (la vidéo du compte crédité d'abord, puis la meilleure de chaque scène). Compte **3 à 5 minutes** en tout.

**Pour chaque scène, tu vois :**
- ce qu'il faut chercher, et les **indices** vus à l'écran (date, filigrane, lieu) ;
- **les images du Short** (une par plan, trois pour un plan long), déjà nettoyées des bandeaux et sous-titres, avec **Copier** et **Enregistrer** ;
- les boutons **Google Lens, Yandex et Bing** : copie l'image, colle-la (Ctrl + V) dans le moteur, puis **agrandis le cadre à toute l'image** (Google zoome tout seul sur un détail, par exemple un t-shirt). Google Lens trouve souvent ce que l'automatique ne trouve pas, surtout sur **TikTok et Facebook** : c'est lui qui a trouvé la vidéo d'origine des puits ;
- les recherches en anglais **et dans la langue du pays** (clique pour copier), avec leurs liens YouTube, TikTok et Google vidéos ;
- **toutes les vidéos trouvées**, avec leur origine (« YouTube », « langue locale », « par image ×3 », « compte crédité ») : **les vérifiées en premier**.

**Vérifier avec l'IA** : l'IA regarde la vidéo (15 secondes sur YouTube, 1 à 2 minutes sur VK, Rutube, Dailymotion ou TikTok, qu'elle doit d'abord télécharger) et la compare **plan par plan** au modèle :
- **« vidéo exacte »** : c'est la vidéo d'origine ;
- **« images équivalentes »** : une autre vidéo qui montre la même action et peut la remplacer ;
- **« partielle : à regarder »** : le même évènement, mais pas tout ce que montre la scène (par exemple le jet de gaz sans la pelleteuse) ;
- **« rien pour cette scène »**.

Elle donne **les moments** (« à 2:24 ») et signale si la vidéo est « utile aussi pour les scènes 3, 5 ». Pour une longue compilation vérifiée, l'app ne télécharge que **les passages utiles**, en une seule demande.

**Tes propres liens** (TikTok, Instagram, VK… trouvés par exemple avec Google Lens) : colle-les, puis **Vérifier mes liens avec l'IA** (1 à 2 minutes). Ils sont jugés comme les vidéos proposées, apparaissent dans **« Tes liens vérifiés »**, et **ceux qui servent sont cochés tout seuls** : seuls leurs passages utiles seront téléchargés. Tu peux aussi les télécharger sans les vérifier.

Une scène marquée **« Publicité dans le modèle »** (la démonstration d'un produit de marque) n'est pas cherchée, et ton script ne reprend ni la marque ni l'argument de vente.

Coche les vidéos qui conviennent, puis **Télécharger et analyser**. Pas besoin des vidéos exactes : des images équivalentes suffisent, puisque ton script est réécrit. Pour aller plus loin à la main, l'extension **InVID-WeVerify** découpe une vidéo en images et lance toutes les recherches par image.

Plus tard, à l'étape Sources, **« Il manque des images ? »** permet d'ajouter d'autres vidéos. Seules les nouvelles sont analysées, et tes corrections de crédits sont gardées. Une vidéo qui ne se télécharge pas est **ignorée avec un avertissement**, et **Réessayer** la retente.

**Si YouTube bloque le téléchargement** (« confirme que tu n'es pas un robot ») : l'app réessaie toute seule une fois. Sinon, ça passe souvent après une heure. La vraie solution : un fichier de cookies YouTube, `youtube_cookies.txt`, à la racine de TikTub :
1. utilise un **compte Google secondaire** (jamais celui de tes chaînes) ;
2. dans une **fenêtre privée**, connecte-toi à YouTube, va sur `youtube.com/robots.txt`, exporte avec l'extension « Get cookies.txt LOCALLY » ;
3. **ferme la fenêtre privée sans te déconnecter** ; renomme le fichier `youtube_cookies.txt` et place-le à la racine de TikTub ;
4. ne le colle jamais dans une conversation : il donne accès au compte. Refais-le quand le blocage revient.

### Étape 2 · Sources (à vérifier)

L'app a **analysé le modèle** : sa question, et les **affirmations douteuses** à ne pas reprendre telles quelles. Elle a aussi **découpé les sources en clips** :
- chaque clip a sa miniature, prise au **moment fort** (le choc) et **déjà nettoyée** : seule la vraie image est gardée, et les filigranes sont effacés ;
- les clips inutilisables sont **décochés**, avec leur raison : interview, écran de fin, texte incrusté, trop court (moins d'1 seconde)… Tu peux en cocher ou en décocher d'autres. Un clip court ne sert qu'à une phrase courte : le contrôle du script refuse une phrase trop longue pour son clip ;
- **la basse résolution** est signalée ;
- les **crédits** proposés viennent des filigranes, par exemple « @azzamyreal · 9News » (jamais un numéro de compte TikTok). Corrige-les si besoin : ils s'affichent en haut de la vidéo et à la fin de la description, et ta correction est gardée si tu ajoutes des sources.

Clique ensuite sur **Écrire les scripts**.

### Étape 3 · Script (relecture obligatoire)

Pour chaque chaîne, l'IA a écrit un script, puis un **modèle plus puissant l'a relu et corrigé** : phrases complètes, **une fin qui répond à la question** (jamais « Mais au fait… »), faits prudents, pas de publicité, **jamais deux fois le même clip**, longueur adaptée à chaque clip. S'il reste un problème après la relecture, l'IA le corrige encore une fois toute seule. Ses corrections sont listées.

Tu peux tout modifier :
- le titre, la description et les tags ;
- pour chaque phrase : **le clip** qui passe dessous (avec sa miniature), **le bandeau**, **le texte** et **les mots en couleur**.

Tu peux aussi **demander une modification à l'IA**, par exemple « la phrase 3 est trop longue ».

**Valider ce script** est refusé tant qu'il reste un problème (phrase trop longue pour son clip, phrase incomplète…). Quand tous les scripts sont validés, clique sur **Générer les voix et les aperçus**.

### Étape 4 · Aperçu

Pour chaque chaîne, tu as :
- un **aperçu** de la vidéo ;
- le résultat du **contrôle automatique** : le son dure autant que l'image, chaque phrase est à sa place, le volume est conforme ;
- la **voix** utilisée, avec son extrait. Tu peux **en essayer une autre** pour cette vidéo seulement (« Refaire avec cette voix »).

**Valide** chaque aperçu, puis clique sur **Rendu final des aperçus validés**.

### Étape 5 · Rendu

Les vidéos finales passent à nouveau le contrôle, puis arrivent dans **Publication → Résultats IA**, chacune sur sa chaîne, avec son titre, sa description (crédits inclus) et ses tags.

---

## Bon à savoir

- **Le format de la vidéo** : un cadre arrondi sur fond noir, un **bandeau différent pour chaque clip**, de gros **sous-titres** avec un mot-clé coloré (jaune, rose, vert, une couleur par phrase), un petit zoom et un tremblement à chaque choc, la musique de fond et, **seulement quand un vrai choc s'entend** (collision, coup de marteau, explosion), son **vrai bruit**. Si le son de ce clip contient une voix, on emprunte le bruit d'un autre clip de choc. Une vidéo sans choc (paysages, récolte…) n'a aucun bruitage ajouté.
- **L'arabe** s'écrit de droite à gauche, en arabe standard (fusha), avec la police Tajawal.
- **Durées** : l'analyse prend 3 à 6 minutes selon le nombre de sources, les scripts 1 à 2 minutes, chaque aperçu environ 1 minute. Tu peux changer d'écran pendant ce temps.
- **Si une étape échoue** (lien mort, service indisponible, serveur redémarré), le projet l'affiche, et **Réessayer** reprend cette étape.
- Les fichiers de travail d'un projet (`temp/adaptations/`) sont **gardés** tant que le projet est en cours, puis nettoyés une fois toutes ses vidéos publiées.
- **Ce qui manque encore** : les flèches et cercles qui pointent la voiture avant le choc. Ils sont prévus pour une 2ᵉ version.
- Le moteur est dans le dossier `adaptation/` du projet.
