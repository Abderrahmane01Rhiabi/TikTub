# Labo « qualité des images » — bilan

*8 novembre 2026. 3 projets Idée d'abord, montage pro, laissés tels quels jusqu'à l'aperçu. Fichiers de travail dans le dossier du labo (scratchpad). Voir aussi [outils_video.md](outils_video.md).*

## Les 3 projets

| Projet | Chaîne | Type | Plans |
|---|---|---|---|
| Évacuation du Karian Rahamna | prince_moulay_hassan (darija) | actualité, lieux | 12 |
| Pourquoi les avions laissent des traînées blanches | cestpourca (français) | explication, idées abstraites | 14 |
| Le chantier du Grand Stade Hassan II à Benslimane | prince_moulay_hassan (darija) | actualité, lieux | 15 |

## Ce qui ne va pas, et pourquoi

| Cause | Exemple | Projets |
|---|---|---|
| **Mal jugé** : la bonne image existait, mais l'IA l'a écartée | « la ville accélère ses projets pour la Coupe du monde » : les plans « Casablanca en chantier » notés 2/10 « hors sujet » car jugés par rapport au **sujet global**, pas à la phrase | Karian (2 plans) |
| **Introuvable** : aucune vidéo trouvée ne montre la scène exacte | « les familles reçoivent les clés des appartements » ; « les agents peignent des numéros rouges » | Karian (3 plans) |
| **Faux lieu** : une image d'un autre pays présentée comme le lieu du sujet | 3 plans de NEOM (Arabie saoudite) pour « les travaux ont commencé à Benslimane » | Grand Stade (3 plans) |
| **Monotonie** : trop de plans de la même vidéo, presque identiques | 7 plans sur 14 de la même vidéo de traînées ; plan 4 = plan 1 | Traînées, Grand Stade |
| **Idée abstraite** : aucune vidéo réelle ne peut le montrer | « ce plafond emprisonne la chaleur », « doublent l'effet réchauffant », « 600 °C contre −50 °C » | Traînées (5-6 plans) |
| **Détail qui contredit** : un détail de l'image dément la phrase | « à 12 km d'altitude » sur un avion train sorti au décollage | Traînées (2 plans) |

Deux causes de fond : chaque plan du stock est jugé sur **une seule image fixe** et **par rapport au sujet global** ; et la recherche vise la **scène exacte** au lieu de l'**idée** de la phrase.

## Ce que chaque idée a corrigé

| Idée testée | Coût | Résultat |
|---|---|---|
| **Recherche par le sens** dans notre stock (SigLIP multilingue, sur le PC) | 0 $ | a trouvé n°1 les plans « mal jugés » du Karian (2/2). Marche avec une description française de l'image ou de l'idée ; **marche mal avec la phrase en darija** |
| **Recherche générale** sur Pixabay (la « leçon des tomates »), reclassée par le sens | 0 $ | a trouvé une image qui fait passer l'idée pour les 3 « introuvables » du Karian (une main qui tend des clés, un chiffre bombé en rouge, des grues en ville). Les mots-clés seuls de Pixabay donnent du bruit : le reclassement par le sens est indispensable |
| **Relecture du montage fini** par Gemini (1 image par plan + sa phrase, 1 appel) | 2 à 3 centimes par vidéo | a attrapé les contradictions (Karian 9-10), les répétitions, les idées abstraites (en proposant « schéma » ou « chiffre animé »), le train d'atterrissage ; propose une recherche anglaise utile. **N'a pas vu** le faux lieu (NEOM) ni les plans « mal jugés » du Karian |
| Schémas, chiffres, cartes animés (motion-graphics) | 0 $ (sur le PC) | **pas encore testé** — c'est le seul remède aux idées abstraites et aux chiffres |
| Wikimedia, Unsplash, Pexels | 0 $ | **pas encore testés** |

## Ce qu'il faut construire (chantier « Images v2 »), dans l'ordre

1. **Juger chaque plan par rapport à la phrase**, pas au sujet ; classer le stock par le sens (SigLIP) avec une description française de l'idée de chaque phrase. Corrige les « mal jugés ». Gratuit.
2. **Règle de variété** : au plus 2 plans par vidéo source, jamais deux plans presque identiques à la suite. Corrige la monotonie. Gratuit.
3. **Recherche générale de secours** (Pixabay, puis Pexels) quand rien ne fait passer l'idée, reclassée par le sens. Règles : **le vrai lieu d'abord** s'il existe ; **pas de clip généré par IA en actualité** ; jamais une image qui contredit. Corrige les « introuvables ». Gratuit.
4. **Contrôle du lieu en actualité** : la vidéo source doit parler du lieu ou du sujet (son titre, sa description), sinon elle passe après les autres. Corrige les faux lieux (NEOM). Presque gratuit.
5. **Relecture du montage fini** par Gemini (2-3 centimes) : les plans « contredit / ne colle pas » sont remplacés automatiquement avec sa recherche, ou signalés en orange dans la timeline.
6. **Schémas, chiffres et cartes animés** (skill motion-graphics / HyperFrames) pour les phrases abstraites et les chiffres, surtout pour les chaînes d'explication. Le plus long ; à tester d'abord sur « ce plafond emprisonne la chaleur » et « ×2 ».

## Outils et skills retenus

| Pour | Outil | Statut |
|---|---|---|
| Recherche par le sens | open_clip + SigLIP i18n (multilingue), sur la carte graphique | testé ✅ |
| Images de secours | Pixabay (clé déjà là) ; Pexels (clé à créer) ; Wikimedia Commons (lieux, personnes) | Pixabay testé ✅, autres à tester |
| Relecture | Gemini Flash (idée reprise de take-one / video-director) | testé ✅ |
| Schémas, chiffres, cartes | skill motion-graphics (déjà dans Claude Code) ; map-animation-skills (MIT, à lire avant) | à tester |
| Ingénieur son (plus tard) | earshot (MIT, sur le PC) | à tester |

## Retest après le chantier « Images v2 » (9 novembre 2026)

Sur des **copies** des 3 projets (même stock, même voix), avec Images v2 (points 1 à 5) :

| Projet | Avant | Après |
|---|---|---|
| Karian | 5 mauvais plans sur 12 | 3 sur 12, **tous signalés en orange** par la relecture ; nouveaux bons plans Pixabay : grues et immeuble en construction, mur tagué à la bombe, billets comptés |
| Grand Stade | 3 plans de NEOM + 1 répétition | 0 plan de NEOM (vidéo écartée, comme une vidéo sur des stades espagnols), plus de répétition ; plans d'architecte en secours ; 3 plans faibles signalés |
| Traînées | 7 plans sur 14 d'une même vidéo | 2 plans au plus par vidéo, gros plans de réacteurs ; les phrases abstraites restent faibles (signalées) |

Réglages trouvés pendant le retest :
- le contrôle du lieu doit viser **un autre pays ou une autre ville** seulement (sinon il écartait le direct d'un autre quartier de Casablanca), et ne compter que si **deux réponses** sont d'accord ;
- le monteur IA ne doit voir que **60 plans** au plus (avec 109, sa réponse était coupée) ;
- les recherches Pixabay doivent être des **mots courts écrits par Gemini** (« hand giving keys »), pas des morceaux de phrase ;
- les « idées » sans façon de filmer (pas de « timelapse ») ;
- un modèle anglais (CLIP ViT-B-16 DataComp) sépare mieux que le multilingue du labo : ~0,35 le bon plan, ~0,19 rien.

Reste : les phrases abstraites → **schémas, chiffres, cartes animés** (point 6, mini-labo à faire) ; un secours Pixabay peut encore être hors sujet (un marteau de juge pour « les clés ») — la relecture le signale.
