# Économies IA — ce qui a été fait et testé

> Branche `perf/economies-ia` (partie de `main`, qui contient déjà `feature/mode-idee`). Rien n'est fusionné.
> Les 🟢 sont dans le code. Les 🟡 ont seulement été **testés** : aucun n'est appliqué.
> Tests sur des **copies** (`etude_economies/`) : ni la base ni les vrais projets n'ont été modifiés. Les appels de
> l'étude sont notés à part (`etude_economies/usage.jsonl`), pas dans le coût de l'Accueil.

## En bref

| | |
|---|---|
| 🟢 faits | **5** (G1 à G5), un commit chacun, 13 tests ajoutés |
| Suite de tests | `python -m pytest -q` : **552 réussis, 0 échec** |
| 🟡 testés | ✅ **3 à adopter** (Y1, Y3, Y7) · ❌ **2 à rejeter** (Y2, Y4) · ⏸️ **1 non testé** (Y5, voir plus bas) · 📖 **Y6 : à toi de lire** |
| Coût réel de l'étude | **1,06 $** (budget 1,20 $), 61 appels |
| Économie estimée avec les ✅ (+ 🟢) | **≈ 1,10 $ sur 5,78 $ (≈ 19 %)** aujourd'hui ; **≈ 2,2 $ sur ≈ 11,1 $ (≈ 20 %)** aux prix du 1ᵉʳ janvier 2027 |

Le rapport prévoyait ≈ 35 % : l'écart vient de **Y2**, impossible (la vidéo est déjà au minimum de tokens chez
Google), et de **Y4**, qui dégrade les effets.

---

## 1. Les 🟢 faits

| # | Ce qui a changé | Où | Tests ajoutés |
|---|---|---|---|
| G1 | Après une phrase ou un clip changé (à la main, clip proposé, chat, échange automatique), **seules les phrases concernées sont rejugées** ; les autres gardent leur verdict (« garder quand même » compris). Le juge reçoit les clips de tout le script, pour ne jamais proposer un clip déjà pris. | `pipeline._judge_changed`, `_rejudge`, `script.match` | 3 (`tests/test_economies_ia.py`) + 1 test existant adapté (il exigeait de tout rejuger) |
| G2 | Au 2ᵉ tour de correction du storyboard, **seuls les plans corrigés** sont recomparés à leur image ; un plan non touché garde son verdict. | `write_storyboard`, `storyboard.illustration(only=…)` | 2 |
| G3 | Au retéléchargement : nettoyage, flèches, effets et zoom des **clips inchangés** sont gardés. Clé par plan : choix du moment (la même que les clips gardés) + phrase + image voulue + ton. Un seul de ces éléments change → revu. Les effets sont gardés avant le plafond par vidéo, toujours appliqué sur l'ensemble. | `run_fetch` | 2 (dont : phrase changée sur un clip gardé → revue) |
| G4 | Une recherche d'images **relancée** (erreur, redémarrage du serveur) ne revérifie pas les vidéos déjà regardées : chaque vérification est enregistrée dès qu'elle arrive, sous la clé de ce qu'elle juge (scènes, phrases, indices, Short modèle). Un plan modifié → tout est revérifié. | `run_images`, `finder.verify_best(on_result=…)` | 2 (dont : plans changés → revérifiés) |
| G5 | Le journal note le **projet**, la **vidéo** (lien YouTube ou chemin du fichier envoyé), le nombre d'**images** et les tokens **en cache**. Le coût du mois (Accueil) facture le cache au prix de Google (0,075 $/M pour Flash, un dixième). | `gemini_ai_generator.log_usage`, `usage_context`, `in_context`, `ai_models.cost` | 4 |

Économie des 🟢 : ≈ 0,15 $ sur la période + ≈ 0,03 $ à chaque « Revenir aux images » + ≈ 0,30-0,40 $ à chaque
recherche relancée. Surtout, **G5 rend les prochaines mesures exactes** (par projet, par vidéo, cache compris).

---

## 2. Les 🟡 testés

Méthode : on rejoue une étape sur les mêmes données que celles en base (le « avant », non repayé). Quand l'écart
pouvait venir de Gemini lui-même, un **témoin** a été refait **sans** le réglage, pour mesurer sa variation
naturelle. Seuils : ≥ 90 % d'accord, aucune vidéo choisie qui devient « rien », aucun « bon » qui devient « non ».

### Y2 — Résolution basse pour la vérification · ❌ à rejeter (sans test, 0 $)

La documentation officielle de Google (Gemini 3) : une image de **vidéo** coûte **70 tokens** en réglage par défaut
**comme en résolution basse** (`low`) ; seule `high` monte à 280.
- Page : <https://ai.google.dev/gemini-api/docs/media-resolution> (tableau « Gemini 4 and Gemini 3 »).
- Nom exact dans `generateContent` : sur chaque partie, `"mediaResolution": {"level": "MEDIA_RESOLUTION_LOW" |
  "MEDIA_RESOLUTION_MEDIUM" | "MEDIA_RESOLUTION_HIGH" | "MEDIA_RESOLUTION_ULTRA_HIGH"}` —
  <https://ai.google.dev/api/generate-content> (messages `Part.mediaResolution`, `MediaResolution`, `Level`).
- Le journal le confirme : 20 614 tokens vidéo par vérification à 0,5 image/s ≈ 294 images × 70.

**La vidéo est déjà au minimum : rien à gagner.** (Pour les **images fixes**, au contraire : 1 120 tokens par
défaut, 560 en moyenne, 280 en basse → voir Y7.)

### Y1 — Réflexion limitée (256 tokens) sur les étapes qui regardent · ✅ à adopter (vérification, recalage, logos ; contrôle aussi)

| Étape | Accord | Témoin sans limite | Réflexion moyenne : journal → test | Verdict |
|---|---|---|---|---|
| Vérification (9 vidéos choisies, 78 plans) | **94,9 %** même niveau · **96,2 %** même « utilisable » · **0** vidéo choisie devenue « rien » | 96,2 % · le témoin, lui, a perdu 1 vidéo choisie | 877 → **0** | ✅ |
| Recalage (6 clips) | **6/6** moment retrouvé | — | 846 → **0** | ✅ |
| Contrôle (6 clips) | 5/6 « utilisable » (voir l'exemple) → **6/6 en pratique** | — | 246 → **0** | ✅ (inutile si Y3) |
| Logos (6 images) | **6/6 identique au témoin** | — | 550 → **0** | ✅ |

Exemples concrets :
- Vérification, avions, vidéo `WNs2IFUezPg` : plan 3 « rien » → « équivalente » (un plan de plus trouvé).
  Projet du 20/10, `8Vqh1RxCumY` : avec limite, plans 2 et 5 passent de « rien » à « équivalente » ; **sans limite**
  (témoin), la même vidéo perd son plan 1 choisi (« équivalente » → « rien »). Les écarts sont de la même taille avec
  ou sans limite : c'est la variation de Gemini.
- Les **moments** de la vérification diffèrent souvent de plus de 2 s (18 % à ± 2 s avec limite, 0 % pour le
  témoin) : ils sont approximatifs par nature, le recalage les corrige ensuite.
- Contrôle, chameau, clip du cheval : avec limite, « inutilisable — rien de spectaculaire » ; l'app ne retient pas
  cette raison comme un vrai défaut (`_real_faults` → vide) : **le clip reste utilisable**.
- Logos, avions P4 : la base avait effacé « QUEEN VIRAL », « PILOTS EYE.tv », « SUBSCRIBE » ; avec limite **et** sans
  limite, Gemini ne voit que « QUEEN VIRAL » sur cette image : l'écart vient de l'image (la base a regardé d'autres
  instants, et la 2ᵉ passe de nettoyage en ajoute), pas de la limite.

Coût avant / après : la réflexion est payée au prix de la réponse ; à 0 token, une vérification passe de ≈ 0,0227 $
à ≈ 0,0194 $ en moyenne (mesuré sur la même vidéo `8Vqh1RxCumY` : 0,0353 $ sans limite, 0,0288 $ avec).
**Économie estimée : ≈ 0,55 $ sur la période (≈ 10 %)** (réflexion de la vérification, du recalage et des logos).

### Y3 — Un seul regard sur chaque vidéo téléchargée (recalage + orientation + contrôle) · ✅ à adopter

| Mesure (6 fichiers) | Résultat |
|---|---|
| Moment retrouvé | **6/6** |
| « Utilisable » comme en base | **6/6** (le cheval aussi) |
| Orientation | **0** partout (aucune vidéo couchée, comme en base) |

Coût : les 3 appels séparés d'aujourd'hui coûtent en moyenne 0,0133 + 0,0036 + 0,0070 = **0,0239 $ par fichier**
(journal) ; l'appel unique coûte celui du recalage plus une réponse un peu plus longue, **≈ 0,014 $**.
**Économie estimée : ≈ 0,32 $ sur la période (≈ 5,5 %).** Échantillon petit (6 fichiers, tous droits) :
à surveiller sur les premiers vrais projets (une vidéo couchée doit toujours être remise droite).

### Y4 — Flèches + effets + zoom en un seul appel · ❌ à rejeter

| Comparaison (26 plans) | Flèches / cercles | Effets |
|---|---|---|
| Témoin : les 3 appels séparés de l'app, refaits | 88,5 % | 65,4 % |
| **Un seul appel** | **96,2 %** | **38,5 %** |
| Un seul appel vs témoin (même jour) | — | 53,8 % |

Les effets varient déjà beaucoup d'eux-mêmes (65 %), mais la fusion fait nettement pire : elle ajoute des effets que
les appels séparés ne mettent pas. Exemples (avions) : plan 7, base « zoom », séparé « zoom », **fusion « zoom +
ralenti »** ; plan 5, base et séparé rien, **fusion « transition »** ; chameau plan 2, **fusion « chiffre 15 % »**.
La partie flèches, elle, tient très bien : une variante « flèches + zoom ensemble, effets à part » serait possible,
mais l'économie serait faible (≈ 0,05 $ sur la période).

### Y7 — Le juge phrase ↔ image en résolution moyenne · ✅ à adopter

| Comparaison (26 phrases) | Identique | « bon » devenu « non » |
|---|---|---|
| Résolution moyenne vs base | **92,3 %** | **0** |
| Témoin (résolution normale) vs base | 92,3 % | 0 |

Exemples : chameau plan 5, base « moyen » → moyenne « bon » (le témoin garde « moyen ») ; projet du 20/10 plan 2,
base « moyen » → « bon » **dans les deux** (moyenne et témoin) ; avions plan 4, le **témoin** passe à « moyen ».
Coût : les tokens d'image sont **divisés par deux** (ex. 32 640 → 15 873 pour 30 images) ; sur le coût total d'un
appel, l'écart est masqué par la réflexion du juge, très variable (de 1 300 à 11 000 tokens d'un appel à l'autre).
**Économie estimée : ≈ 0,08 $ sur la période (≈ 1,4 %).**

### Y5 — Versions FR/AR : un seul regard par vidéo · ⏸️ non testé

C'est une **fusion** (« un appel au lieu de plusieurs »), comme Y4 qui vient d'échouer nettement : comme demandé, je
ne passe pas au réglage suivant du même type sans ton accord. Coût prévu du test : ≈ 0,10 $ (groupe `a63f`/`cdec`,
5 vidéos vérifiées par les deux versions). Économie possible : ≈ 0,18 $ sur la période (≈ 3 %).

---

## 3. Y6 — Relecture du storyboard : Pro ou Flash ? (à toi de lire)

Même brouillon (écrit par l'app, comme d'habitude), relu une fois par **Pro** (aujourd'hui) et une fois par **Flash**.
Coût mesuré : relecture Pro **0,053 $** en moyenne, Flash **0,023 $** (−57 %). Aucun avis de ma part ci-dessous.

### Avions (FR) — angle « Et si les moteurs coupaient ? »

| # | Brouillon | Relu par Pro | Relu par Flash |
|---|---|---|---|
| titre | Et si les moteurs coupaient en plein vol ? ✈️💀 | Pourquoi les avions ne volent pas plus haut ? ✈️💀 | Pourquoi les avions volent TOUS à 10 000 m ? ✈️💀 |
| 1 | Que se passe-t-il si un avion de ligne perd tous ses moteurs d'un coup ? | Pourquoi les avions de ligne ne volent-ils pas plus haut pour se protéger des pannes ? | Pourquoi les avions de ligne volent-ils tous à dix mille mètres d'altitude ? |
| 2 | À dix mille mètres d'altitude, l'appareil ne s'écrase pas immédiatement au sol. | À dix mille mètres, un avion sans moteur ne s'écrase pas, il devient un immense planeur. | Cette hauteur offre d'abord une marge vitale si les moteurs tombent en panne. |
| 3 | Avec une finesse de 15 à 20, l'avion peut planer en toute sécurité sur 150 à 200 kilomètres pour se dérouter. | Cette altitude lui offre jusqu'à deux cents kilomètres de vol plané pour trouver une piste. | En planant sans aucune poussée, l'avion peut parcourir cent cinquante kilomètres pour se dérouter. |
| 4 | Voler aussi haut permet également d'échapper aux pires orages, qui restent généralement bloqués sous 7 600 mètres. | Voler aussi haut permet également d'échapper aux pires orages, qui restent bloqués plus bas. | Voler aussi haut permet aussi de survoler les orages violents, bloqués bien plus bas. |
| 5 | Mais grimper encore plus haut pour augmenter cette sécurité devient un piège mortel. | Mais grimper encore plus haut pour planer plus loin devient un piège mortel. | Mais grimper encore plus haut sur ces instruments devient extrêmement dangereux. |
| 6 | L'avion entrerait dans le « coffin corner », la limite fatale où sa vitesse de décrochage rejoint celle du mur du son. | L'avion atteint le « coffin corner », une limite fatale où le manque d'air le fait décrocher et chuter. | C'est le plafond absolu : au-delà, dans le « coffin corner », la vitesse de décrochage rejoint celle du mur du son. |

Corrections annoncées — **Pro** : accroche réécrite pour coller à la réponse (le coffin corner) ; phrases plus orales ;
lien logique du plan 5 explicité ; titre et description mis à jour. — **Flash** : sujet recentré dès l'accroche sur
l'altitude ; accroche raccourcie (≈ 2,5 s) ; plans 2, 3, 5 alignés sur leur image ; phrases fermées, < 5 s ; bandeaux
harmonisés.

### Chameau (AR) — angle « Pourquoi son sang n'explose pas ? »

| # | Brouillon | Relu par Pro | Relu par Flash |
|---|---|---|---|
| titre | لماذا لا ينفجر دم الجمل؟ 🐪🩸 | لماذا لا ينفجر دم الجمل؟ 🐪🩸 | لماذا لا ينفجر دم الجمل؟ 🐪🩸 |
| 1 | لماذا لا ينفجر دم الجمل عندما يشرب كميات هائلة من الماء دفعة واحدة؟ | لماذا لا ينفجر دم الجمل حين يشرب كميات هائلة من الماء؟ | لماذا لا ينفجر دم الجمل بعد شرب مئة لتر ماء؟ |
| 2 | يتحمل الجمل فقدان ثلاثين بالمئة من وزنه ماء، بينما نصف هذه النسبة يقتل حصانا فورا. | يتحمل الجمل فقدان ثلث وزنه من الماء، وهي نسبة تقتل معظم الحيوانات فورا. | يتحمل هذا الحيوان خسارة ثلث وزنه من الماء في الصحراء، بينما نصف هذه النسبة يقتل حصانا فورا. |
| 3 | مع هذا العطش الشديد، يصبح دمه كثيفا وشديد اللزوجة بدرجة تعطل الدورة الدموية العادية. | في هذه الحالة، يصبح دمه كثيفا جدا وتبرز أوردته بوضوح لضخ هذا الدم اللزج. | تنبض عروق رقبته بدم لزج وشديد الكثافة بسبب العطش القاتل دون أن يتوقف جريانه. |
| 4 | خلايا دمه الحمراء بيضاوية الشكل، مما يمنع تشكل الجلطات ويبقي الأكسجين متدفقا بحرية. | لكن خلايا دمه الحمراء بيضاوية الشكل، تنزلق بسلاسة وتمنع تشكل الجلطات القاتلة. | يتنفس الجمل بهدوء تام لأن خلايا دمه بيضاوية الشكل، فتنزلق بسلاسة في أضيق أوعيته دون تجلط. |
| 5 | وعندما يجد نبعا، يمكنه ابتلاع مئة وثلاثين لترا من الماء في عشر دقائق فقط. | وعندما يجد الماء أخيرا، يبتلع أكثر من مئة لتر في دقائق معدودة. | عند العثور على الماء، يبتلع الجمل مئة وثلاثين لترا دفعة واحدة في عشر دقائق فقط. |
| 6 | تنتفخ كريات دمه الفريدة حتى مئتين وأربعين بالمئة من حجمها الطبيعي لاستيعاب السوائل دون أن تنفجر. | السر هو أن خلايا دمه تتمدد وتنتفخ لضعفي حجمها لتخزين الماء دون أن تنفجر. | لا ينفجر دمه لأن كرياته الحمراء تتمدد بمرونة حتى مئتين وأربعين بالمئة من حجمها لامتصاص السوائل. |

Corrections annoncées — **Pro** : accroche raccourcie et image « le chameau qui boit » ; plan 2 image « sol craquelé » ;
plan 3 parle des veines visibles ; **plans 4 et 6 : images remplacées par des « animations 3D de globules rouges »** ;
plan 6 reformulé pour répondre à l'accroche. — **Flash** : accroche raccourcie avec le chiffre « cent litres » ;
plan 3 commente la veine qui bat ; plan 4 relié au chameau qui respire calmement ; plan 5 rendu autonome ; plan 6
image différenciée du plan 5 et réponse directe.

### Projet du 20/10 (FR) — angle « La science derrière leurs cascades »

| # | Brouillon | Relu par Pro | Relu par Flash |
|---|---|---|---|
| titre | La physique secrète des sauts de l'extrême 🏢⚡ | La physique secrète des sauts de l'extrême 🏢⚡ | La physique secrète des sauts de l'extrême 🏢⚡ |
| 1 | Comment les athlètes de parkour réussissent-ils à descendre d'immenses bâtiments sans se blesser ? | Comment les athlètes de parkour réussissent-ils à descendre d'immenses bâtiments sans se blesser ? | Comment ces traceurs descendent-ils des façades entières sans se tuer ? |
| 2 | Leur survie ne repose sur aucune chance, mais sur une application ultra précise de la physique. | Pour survivre, ils n'ont pas besoin de chance, mais d'utiliser chaque courbe du décor pour dissiper leur vitesse. | Ici, aucune chance : chaque pente et chaque glissade sont calculées au millimètre. |
| 3 | En se suspendant par les mains avant chaque chute, ils retirent deux mètres à la hauteur réelle de l'étage. | En se suspendant par les mains avant de lâcher prise, ils retirent deux mètres de chute à chaque étage. | En se suspendant par les bras avant de lâcher, ils retirent deux mètres à la chute. |
| 4 | Contre un lampadaire, la force de frottement convertit l'accélération gravitationnelle en chaleur pour freiner net la descente. | En agrippant ce lampadaire en plein vol, le frottement contre le métal freine brutalement leur descente vers le sol. | En enserrant ce mât en plein vol, le frottement freine net leur vitesse de chute. |
| 5 | Au contact du sol, la roulade transforme l'énergie verticale destructrice en vitesse horizontale pour protéger les os. | Et lors de l'impact, cette roulade transforme la violence de la chute verticale en un simple élan vers l'avant. | Dès l'impact, la roulade projette tout le poids vers l'avant au lieu d'écraser les jambes. |
| 6 | Ces cascadeurs domptent la gravité en transférant l'énergie, mais sur une pente lisse sans rebord, la physique redevient impitoyable. | Ils survivent donc en redirigeant l'impact grâce au décor, mais face au vide absolu, la moindre erreur reste fatale. | Ils survivent en découpant le vide en micro-impacts, car sans aucun point d'arrêt, le choc final reste mortel. |

Corrections annoncées — **Pro** : plan 2 rendu concret ; vocabulaire du plan 4 simplifié ; plan 5 visuel ; plan 6
répond à la question. — **Flash** : accroche raccourcie (< 3 s) ; plan 2 ancré dans l'image ; plans 4 et 5 décrits
visuellement ; plan 6 réponse conclusive.

Deux faits utiles pour ta lecture (pas un avis) : l'app refuse ensuite les images d'animation (`storyboard.unfilmable`
les renvoie en correction) ; et dans le mode Idée, le storyboard n'a droit qu'aux faits sourcés (« 130 litres en
10 minutes », « 240 % » sont les chiffres des sources).

Économie si tu choisis Flash : ≈ 0,27 $ sur la période (≈ 4,7 %). **Attention : aux prix de 2027, Flash double et Pro
ne bouge pas** : l'économie tomberait à ≈ 0,07 $.

---

## 4. Le coût réel de la session

| Test | Appels | Coût |
|---|---|---|
| Y1 vérification (limité) + témoin | 9 + 3 | 0,203 $ + 0,100 $ |
| Y1 recalage, contrôle, logos + témoin logos | 6 + 6 + 3 + 1 | 0,030 + 0,015 + 0,007 + 0,008 $ |
| Y3 un seul regard | 6 | 0,048 $ |
| Y4 un seul appel + témoin | 3 + 9 | 0,061 $ + 0,122 $ |
| Y7 juge moyen + témoin | 3 + 3 | 0,096 $ + 0,103 $ |
| Y6 brouillons + relectures Pro + Flash | 3 + 3 + 3 | 0,043 + 0,158 + 0,068 $ |
| **Total** | **61** | **1,06 $** (budget 1,20 $) |

Partie 1 (les 🟢) : **0 appel payant**. Les témoins (0,33 $) ont coûté cher, mais sans eux Y1 (logos) aurait été
rejeté à tort et Y4 mal compris.

---

## 5. L'économie totale estimée avec seulement les ✅

Base : le journal du 25 au 27/10 (5,78 $). Les économies se recouvrent un peu (Y3 supprime le contrôle et
l'orientation, dont Y1 ne compte donc plus la réflexion).

| | Aujourd'hui | Prix du 1ᵉʳ janvier 2027 (Flash ×2) |
|---|---|---|
| Coût de la période sans rien changer | 5,78 $ | ≈ 11,1 $ |
| 🟢 G1-G5 | − 0,15 $ | − 0,30 $ |
| ✅ Y1 (réflexion limitée : vérification, recalage, logos) | − 0,55 $ | − 1,10 $ |
| ✅ Y3 (un seul regard par fichier téléchargé) | − 0,32 $ | − 0,64 $ |
| ✅ Y7 (juge en résolution moyenne) | − 0,08 $ | − 0,16 $ |
| **Total avec les ✅** | **− 1,10 $ (≈ 19 %) → ≈ 4,7 $** | **− 2,2 $ (≈ 20 %) → ≈ 8,9 $** |
| *Si tu choisis Flash pour Y6* | *− 0,27 $ de plus* | *− 0,07 $ de plus* |
| *Si Y5 est testé et adopté* | *− 0,18 $ de plus* | *− 0,36 $ de plus* |

## Prochaines étapes possibles (rien n'est fait)

1. Appliquer Y1, Y3 et Y7 dans le code (sur cette branche ou une autre), avec leurs tests.
2. Me dire pour Y5 (test ≈ 0,10 $) et pour Y6 (ta lecture des 3 paires).
3. Après une semaine d'usage, relire le journal (G5 donne maintenant le coût par projet et le cache réel).
