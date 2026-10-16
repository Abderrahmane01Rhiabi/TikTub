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

### Si tu n'as pas les sources : « Ce qu'il faut télécharger »

L'app analyse le modèle, puis te montre :
- **chaque scène à chercher**, décrite simplement : « Cherche : conductrice de tramway avec lunettes heurtant un break sombre », avec les **indices** vus à l'écran (date, filigrane, lieu) ;
- pour chaque scène, des **recherches toutes prêtes** (clique pour copier) et des liens directs vers YouTube, TikTok et Google vidéos ;
- des **vidéos trouvées sur YouTube**, déjà triées par l'IA (les résultats hors sujet sont retirés) ;
- les **comptes crédités** dans le modèle (souvent l'auteur des vidéos d'origine) : leur profil YouTube, TikTok et Instagram, et leurs vidéos YouTube sur le sujet.

**Vérifier avec l'IA** (30 secondes environ) : l'IA regarde la vidéo et cherche **toutes les scènes d'un coup**. Pour chacune, elle répond :
- **« vidéo exacte »** : c'est la vidéo d'origine ;
- **« images équivalentes »** : une autre vidéo qui montre la même action, par exemple une autre piscine qui cède, et peut la remplacer ;
- **« rien pour cette scène »**.

Elle donne aussi **les moments** où on voit la scène, et signale si la vidéo est « utile aussi pour la scène 3 ». Pour une longue compilation vérifiée, l'app ne télécharge que **les passages utiles**, et pas les 10 minutes.

Coche les vidéos qui conviennent, ajoute tes propres liens si besoin (TikTok, Instagram…), puis **Télécharger et analyser**. Pas besoin des vidéos exactes : des images équivalentes suffisent, puisque ton script est réécrit.

Plus tard, à l'étape Sources, **« Il manque des images ? »** permet d'ajouter d'autres vidéos. Seules les nouvelles sont analysées, et tes corrections de crédits sont gardées.

**Si YouTube bloque le téléchargement** (« confirme que tu n'es pas un robot ») : ça passe souvent tout seul après une heure. Sinon, exporte les cookies de ton navigateur, connecté à YouTube, avec l'extension « Get cookies.txt LOCALLY », dans un fichier `youtube_cookies.txt` à la racine de TikTub. Ou prends la même vidéo sur TikTok.

### Étape 2 · Sources (à vérifier)

L'app a **analysé le modèle** : sa question, et les **affirmations douteuses** à ne pas reprendre telles quelles. Elle a aussi **découpé les sources en clips** :
- chaque clip a sa miniature, prise au **moment fort** (le choc) et **déjà nettoyée** : seule la vraie image est gardée, et les filigranes sont effacés ;
- les clips inutilisables sont **décochés**, avec leur raison : interview, écran de fin, texte incrusté, trop court… Tu peux en cocher ou en décocher d'autres ;
- **la basse résolution** est signalée ;
- les **crédits** proposés viennent des filigranes, par exemple « @azzamyreal · 9News ». Corrige-les si besoin : ils s'affichent en haut de la vidéo et à la fin de la description.

Clique ensuite sur **Écrire les scripts**.

### Étape 3 · Script (relecture obligatoire)

Pour chaque chaîne, l'IA a écrit un script, puis un **modèle plus puissant l'a relu et corrigé** : phrases complètes, fin qui se suffit à elle-même, faits prudents, longueur adaptée à chaque clip. Ses corrections sont listées.

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

- **Le format de la vidéo** : un cadre arrondi sur fond noir, un **bandeau différent pour chaque clip**, de gros **sous-titres** avec un mot-clé coloré (jaune, rose, vert, une couleur par phrase), un petit zoom et un tremblement à chaque choc, la musique de fond et les **vrais bruits de choc**. Si le son d'un clip contient une voix, on emprunte le bruit de choc d'un autre clip.
- **L'arabe** s'écrit de droite à gauche, en arabe standard (fusha), avec la police Tajawal.
- **Durées** : l'analyse prend 3 à 6 minutes selon le nombre de sources, les scripts 1 à 2 minutes, chaque aperçu environ 1 minute. Tu peux changer d'écran pendant ce temps.
- **Si une étape échoue** (lien mort, service indisponible, serveur redémarré), le projet l'affiche, et **Réessayer** reprend cette étape.
- Les fichiers de travail d'un projet (`temp/adaptations/`) sont **gardés** tant que le projet est en cours, puis nettoyés une fois toutes ses vidéos publiées.
- **Ce qui manque encore** : les flèches et cercles qui pointent la voiture avant le choc. Ils sont prévus pour une 2ᵉ version.
- Le moteur est dans le dossier `adaptation/` du projet.
