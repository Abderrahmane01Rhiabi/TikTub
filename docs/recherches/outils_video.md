# Recherche : outils et skills vidéo pour améliorer TikTub

*8 novembre 2026. Liens trouvés par toi, lus et résumés. L'app est pour un usage personnel, jamais commercial : les licences « non commerciales » ou « gratuites pour les particuliers » nous conviennent.*

## Le problème de départ

Les images choisies par le montage pro ne ressemblent pas toujours à ce que ferait un monteur humain. Trois causes :

1. **L'image n'existe pas dans ce qu'on trouve** : on n'utilise que des vidéos (YouTube, Pixabay). Un humain utilise aussi des cartes, des photos, des captures d'articles, des chiffres animés, des images générées.
2. **L'IA voit mal** : Gemini regarde les vidéos en basse qualité, décrit chaque plan en une phrase, et le monteur IA choisit sur ce texte.
3. **Personne ne relit le montage fini.**

## Les plus utiles pour nous

| Outil | Ce que c'est | Pour TikTub | Licence |
|---|---|---|---|
| [OpenMontage](https://openmontage.video/) · [GitHub](https://github.com/calesthio/OpenMontage) | Système de production vidéo piloté par Claude Code : 12 pipelines, 100+ outils (78 600 étoiles). App Windows en alpha privée. | Son pipeline « Documentary Montage » cherche les images **par le sens (CLIP)** dans Pexels, Archive.org, NASA, Wikimedia Commons, Unsplash. Mixeur avec ducking (musique baissée sous la voix). | AGPLv3 (s'en inspirer ; usage perso possible) |
| [map-animation-skills (iart-ai)](https://github.com/iart-ai/motion-skills) | Cartes animées : trajets, zoom sur un lieu, cartes style Vox. | Les plans « pays / ville » quand aucun clip n'existe. | MIT (selon un annuaire) |
| [earshot](https://github.com/Leonxlnx/earshot) | « Oreilles » pour l'IA, sur CPU : décrit un son, dit s'il colle à une description (CLAP), 252 effets sonores. | Choisir les effets, vérifier que la musique colle au sujet, ingénieur son automatique. | MIT (modèles Apache-2.0 / BSD-3) |
| [take-one](https://github.com/talsiach/take-one) | Skill Claude « studio complet » avec un relecteur qui note et renvoie le montage (3 tours). | L'idée de la relecture du montage fini. | MIT |
| [video-director](https://github.com/win4r/video-director) | Skill Claude pour planifier, construire et vérifier des vidéos ; script de contrôle qualité (taille et contraste du texte, flashs, coupes, volume). | Contrôle qualité automatique du rendu. | MIT |

## Sources d'images

| Outil | Ce que c'est |
|---|---|
| [Unsplash](https://unsplash.com/fr) | Photos gratuites (pas de vidéos), API disponible. |
| [Vecteezy](https://fr.vecteezy.com/) | Photos, vidéos, vecteurs : gratuit avec attribution, ou payant. |
| [Payhip Ofluminary](https://payhip.com/Ofluminary) | Boutique de packs pour monteurs : effets sonores (9 $), LUTs (15 $), b-roll (20 $), « système de montage » (33 $). Contenu non décrit : à vérifier avant d'acheter. |

## Bons à connaître

| Outil | Ce que c'est |
|---|---|
| [Remotion](https://www.remotion.dev/) | Vidéos en code (React). Gratuit pour un particulier. On a déjà HyperFrames. |
| OpenTimelineIO | Format ouvert (Apache 2.0) pour échanger une timeline : ouvrir notre montage dans Premiere ou DaVinci. |
| [explainroo](https://github.com/vincentsch/explainroo) | Explications style « tableau blanc », voix locale (Kokoro), MIT. Idée de style pour une chaîne explicative. |
| [huashu-art-motion](https://github.com/alchaincyf/huashu-art-motion) | Animation dans 36 styles d'art et 8 grammaires d'explication (Kurzgesagt, Vox…), MIT. |
| [huashu-motion](https://github.com/alchaincyf/huashu-motion) | Films de lancement de produit, MIT. Pas notre sujet. |
| [argo](https://github.com/shreyaskarnik/argo) | Démos d'apps (Playwright + voix), MIT. Pas notre sujet. |
| [reanimate](https://github.com/NiazMorshed2007/reanimate) | Copier une animation vue sur un site, MIT. Pas utile. |
| [rossark-motion-skill](https://github.com/rossark0/rossark-motion-skill) | Animer des SVG dans des apps mobiles, MIT. Pas utile. |
| [awesomeclaude.ai — motion graphics](https://awesomeclaude.ai/claude-motion-graphics) | 17 styles d'animation prêts à copier pour Claude. |
| [awesome-claude-video-skills](https://github.com/zhuyansen/awesome-claude-video-skills) | Annuaire de skills vidéo pour Claude, avec une note de sécurité. Le meilleur endroit pour chercher d'autres outils. |

Déjà disponibles dans Claude Code ici : **motion-graphics** (cartes, chiffres, titres animés), **hyperframes**, **media-use**, **hyperframes-audio** (mixage), **code-review**, **skill-creator**. Connecté : **vidIQ** (tendances, mots-clés, outliers, notes de titres).

**Prudence :** un skill d'Internet est du code qui tourne sur le PC. Le lire avant de l'installer.

## Ce qu'on en tire (plan proposé)

Un labo **« qualité des images »** sur 2 ou 3 projets ratés : pour chaque mauvais plan, noter la cause (image introuvable, mal vue, mal choisie), puis mesurer combien chaque idée en corrige :

1. recherche **par le sens** (CLIP / SigLIP, gratuit sur le PC) ;
2. **sources en plus** : Pexels (vidéos), Wikimedia Commons et Unsplash (photos) ;
3. **cartes animées** et chiffres animés (motion-graphics) ;
4. **relecture du montage fini** par l'IA, qui remplace les plans qui ne collent pas.

On construit ensuite ce qui corrige le plus.
