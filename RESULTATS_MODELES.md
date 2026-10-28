# Des modèles gratuits peuvent-ils remplacer Gemini pour écrire ?

Étude du 28/10/2026, branche `etude/autres-modeles`. Aucun module de l'app n'a été modifié. Les textes
sont côte à côte dans `etude_modeles/A_LIRE.md` : la qualité, c'est à toi de la juger. Ici, seulement des mesures.

Mistral a été écarté à ta demande (seul `ministral-14b`, un petit modèle, est ouvert gratuitement).
**DeepSeek est testé. Qwen ne l'est pas** : `DASHSCOPE_API_KEY` n'est pas dans `.env` (seule l'adresse
`DASHSCOPE_BASE_URL` l'est). Tout est prêt pour Qwen : il suffit d'ajouter la clé puis de lancer les commandes en fin de
fichier.

## 1. Les offres gratuites

| | Groq | DeepSeek (payant, très bon marché) | Qwen3-VL-Plus (Alibaba, Singapour) |
|---|---|---|---|
| Modèle | `openai/gpt-oss-120b` | `deepseek-flash` (V4.1 Flash) | `qwen3-vl-plus` |
| Gratuit ? | oui | non : 0,15 $ / 0,60 $ par million (entrée / sortie) en heure creuse, le double en heure pleine | 1 million de tokens offerts, 90 jours ; puis 0,20 $ / 1,60 $ par million |
| Limites | 30 requêtes/min, 1 000/jour, **8 000 tokens/min**, **200 000 tokens/jour** | — | vidéo en base64 : fichier < 7 Mo |
| Tes données | pas d'entraînement sans ton accord (contrat §4.2) | ⚠️ stockées **en Chine** ; la politique dit utiliser les saisies pour « entraîner et améliorer » ses modèles, avec un droit de refus (pas de précision propre à l'API) | à vérifier quand tu ouvres le compte |
| Usage commercial | les textes t'appartiennent (§8.1) ; ⚠️ le contrat interdit un usage « destiné à éviter de payer » (§6.3(d)(iii)) | payant : pas de question | payant après l'essai |
| Heures | — | heures pleines 01-04 h et 06-10 h UTC en semaine : l'étude refuse d'y appeler | — |

**Ce qui pourrait poser problème** : (1) la limite de Groq par minute (mesurée : dès le 3ᵉ storyboard d'affilée, Groq
refuse et impose 25 à 33 s d'attente ; deux versions FR+AR lancées ensemble : l'une attend 12 s) ; (2) la clause
« éviter de payer » de Groq, floue pour un usage en production ; (3) la vidéo chez Qwen doit être téléchargée puis
réduite sous 7 Mo (temps mesuré plus bas), alors que Gemini lit le lien YouTube directement.

## 2. Les étapes qui écrivent

Étapes testées : les 4 étapes texte les plus coûteuses (sans image, sans vidéo, sans recherche Google ;
`script.critique` exclue). 5 vrais cas par étape : pour l'Adaptation 3 en arabe, 2 en français, 3 en mode Idée ;
pour la Génération, 5 scripts de lungtemotivates (aucune chaîne arabe n'utilise la Génération).
« Contrôles réussis » = aucun problème trouvé par les contrôles de l'app (`storyboard.problems`, `unfilmable`, durées
25-35 s ; pour la Génération : `_script_problems`, qui comprend la répétition). « Chiffres hors des faits » : en mode
Idée, les nombres du texte qu'on ne retrouve pas dans les faits sourcés (détection automatique en chiffres et en
lettres, français et arabe ; chaque cas est listé dans `A_LIRE.md`).

**Écrire le storyboard** (`storyboard.write`)

| Modèle | Sorties | JSON valide | Complet | Contrôles réussis (0 problème) | Problèmes en moyenne | Chiffres hors des faits (mode Idée) | Temps moyen | Refus « limite » (429) |
|---|---|---|---|---|---|---|---|---|
| Gemini Flash (témoin) | 5 | 100 % | 100 % | 0 % | 3.8 | 0 chiffre(s) sur 3 sorties | 23.3 s | 0 |
| Groq gpt-oss-120b | 5 | 100 % | 100 % | 0 % | 3.4 | 0 chiffre(s) sur 3 sorties | 6.3 s | 0 |
| DeepSeek Flash | 5 | 100 % | 100 % | 0 % | 3.2 | 0 chiffre(s) sur 3 sorties | 45.3 s | 0 |

**Relire le storyboard** (`storyboard.critique`)

| Modèle | Sorties | JSON valide | Complet | Contrôles réussis (0 problème) | Problèmes en moyenne | Chiffres hors des faits (mode Idée) | Temps moyen | Refus « limite » (429) |
|---|---|---|---|---|---|---|---|---|
| Gemini Flash (témoin) | 5 | 100 % | 100 % | 40 % | 1.0 | 2 chiffre(s) sur 3 sorties | 22.5 s | 0 |
| Groq gpt-oss-120b | 5 | 100 % | 100 % | 20 % | 3.8 | 0 chiffre(s) sur 3 sorties | 5.6 s | 0 |
| DeepSeek Flash | 5 | 100 % | 100 % | 80 % | 0.4 | 0 chiffre(s) sur 3 sorties | 43.0 s | 0 |

**Corriger le storyboard** (`storyboard.revise`)

| Modèle | Sorties | JSON valide | Complet | Contrôles réussis (0 problème) | Problèmes en moyenne | Chiffres hors des faits (mode Idée) | Temps moyen | Refus « limite » (429) |
|---|---|---|---|---|---|---|---|---|
| Gemini Flash (témoin) | 5 | 100 % | 100 % | 0 % | 1.0 | 0 chiffre(s) sur 3 sorties | 48.6 s | 0 |
| Groq gpt-oss-120b | 5 | 100 % | 100 % | 0 % | 3.2 | 0 chiffre(s) sur 3 sorties | 5.7 s | 0 |
| DeepSeek Flash | 5 | 100 % | 100 % | 100 % | 0.0 | 0 chiffre(s) sur 3 sorties | 32.1 s | 0 |

**Script de la Génération** (`script_generator.generate_script`)

| Modèle | Sorties | JSON valide | Complet | Contrôles réussis (0 problème) | Problèmes en moyenne | Chiffres hors des faits (mode Idée) | Temps moyen | Refus « limite » (429) |
|---|---|---|---|---|---|---|---|---|
| Gemini Flash (témoin) | 5 | 80 % | 80 % | 80 % | 0.0 | — | 16.9 s | 0 |
| Groq gpt-oss-120b | 5 | 100 % | 100 % | 100 % | 0.0 | — | 3.7 s | 0 |
| DeepSeek Flash | 5 | 100 % | 100 % | 100 % | 0.0 | — | 8.4 s | 0 |

Remarques mesurées :
- Gemini : 1 script de Génération sur 5 inutilisable (réponse illisible) : l'app serait passée à OpenAI.
- La correction de Gemini a produit jusqu'à 15 000 tokens de réponse (réflexion comprise) et 106 s pour un cas ; Groq
  reste entre 4 et 9 s.
- Pendant le test, les appels Groq étaient espacés par ceux de Gemini (≈ 20 s) : aucun refus. Le test de rafale
  ci-dessous montre ce qui arrive sans cet espace.

**Groq en rafale** (gratuit, `storyboard.write`) :

| Situation | Résultat |
|---|---|
| 4 storyboards d'affilée | 1ᵉʳ et 2ᵉ : immédiats ; 3ᵉ : refusé puis 25 s d'attente ; 4ᵉ : 33 s d'attente |
| 2 en même temps (FR + AR) | l'un passe, l'autre attend 12 s |

**Combien de vidéos par jour Groq pourrait vraiment écrire** (tokens Groq mesurés : ≈ 12 367 par storyboard — écrire,
relire, corriger une fois — et ≈ 2 808 par script de Génération) :

| | Par jour |
|---|---|
| Limite de Groq | 200 000 tokens, 1 000 requêtes, et ≈ 2 storyboards par minute |
| Storyboards seuls | ≈ **16 storyboards/jour** (≈ 8 Shorts en FR + AR) |
| Scripts de Génération seuls | ≈ 71 scripts/jour |
| Ton volume réel (journal du 25/10 sur 2.1 jours) | ≈ 71 000 tokens/jour Gemini pour ces 4 étapes (Gemini pense plus que Groq : en tokens Groq, ≈ 60 000) |
| Part qui resterait sur Gemini | **≈ 0 % à ton volume actuel** pour la limite par jour ; seuls les pics passent en secours (ou attendent ≈ 30 s) à cause de la limite par minute. Avec toutes les étapes texte (≈ 128 000 tokens Gemini/jour), on approche la limite : un jour chargé (≥ 16 storyboards) basculerait le reste sur Gemini |

## 3. La vidéo : Gemini contre Qwen3-VL-Plus (`finder._watch`)

8 vidéos déjà vérifiées par Gemini (3 avions, 3 chameau, 2 projet du 20/10 ; 6 choisies, 2 rejetées). Le repère est le
verdict **en base**. Gemini a été relancé aujourd'hui sur les mêmes vidéos pour connaître son vrai coût et sa variation
naturelle (un même modèle ne répond pas deux fois pareil).

| Modèle | Vidéos | Même niveau par scène | Même verdict | Scène choisie devenue « rien » | Coût réel par vidéo (moyenne / max) | Temps par vidéo (moyenne) | dont téléchargement | Erreurs |
|---|---|---|---|---|---|---|---|---|
| Gemini Flash aujourd'hui (lien YouTube) | 8 | 90 % | 7/8 | 1 sur 7 | 0.0104 $ / 0.0303 $ | 12 s | 0 s | 0 |
| Qwen3-VL-Plus (fichier téléchargé) | — | *pas encore testé (clé DASHSCOPE_API_KEY absente)* | | | | | | |

Téléchargement pour Qwen (Gemini n'en a pas besoin) : 92 s pour les 8 vidéos
(5.5 à 23.9 s chacune), plus
119 s pour les réduire sous 7 Mo (360p, 2 images/s, sans le son ; jusqu'à
47.7 s pour une vidéo de 9 min). Qwen-VL ne reçoit pas le son ; Gemini l'écoute.

## 4. La transcription : whisper-1 contre les gratuits

Pas de texte de référence : l'écart est mesuré par rapport à whisper-1 (celui de l'app). Les textes complets sont dans
`A_LIRE.md`.

| Vidéo | Durée | Modèle | Temps | Coût | Écart de mots avec whisper-1 |
|---|---|---|---|---|---|
| lungtemotivates_en | 59 s | whisper-1 | 14.7 s | 0.0059 $ | — |
| lungtemotivates_en | 59 s | groq-whisper-large-v3 | 1.2 s | 0.0000 $ | 700 % |
| lungtemotivates_en | 59 s | faster-whisper-medium | 57.9 s (+ 49.8 s de chargement du modèle) | 0.0000 $ | 100 % |
| lungtemotivates_en | 59 s | faster-whisper-small | 29.3 s (+ 2.7 s de chargement du modèle) | 0.0000 $ | 200 % |
| meme_culture_x | 48 s | whisper-1 | 2.7 s | 0.0048 $ | — |
| meme_culture_x | 48 s | groq-whisper-large-v3 | 1.6 s | 0.0000 $ | 12 % |
| meme_culture_x | 48 s | faster-whisper-medium | 43.2 s (+ 42.3 s de chargement du modèle) | 0.0000 $ | 9 % |
| meme_culture_x | 48 s | faster-whisper-small | 13.9 s (+ 7.1 s de chargement du modèle) | 0.0000 $ | 10 % |
| prince_moulay_hassan | 69 s | whisper-1 | 8.6 s | 0.0069 $ | — |
| prince_moulay_hassan | 69 s | groq-whisper-large-v3 | 1.7 s | 0.0000 $ | 93 % |
| prince_moulay_hassan | 69 s | faster-whisper-medium | 375.4 s (+ 6.9 s de chargement du modèle) | 0.0000 $ | 111 % |
| prince_moulay_hassan | 69 s | faster-whisper-small | 87.2 s (+ 21.6 s de chargement du modèle) | 0.0000 $ | 107 % |

Constats : la vidéo de lungtemotivates n'a que de la musique : whisper-1 rend un texte vide (juste), Groq invente
« The The The… » et faster-whisper écrit « Music ». En anglais (meme_culture), les quatre disent presque la même chose.
En darija marocaine (prince_moulay_hassan), aucun n'est fiable et ils ne s'accordent pas entre eux. faster-whisper
« medium » est lent sur ce PC (375 s pour 69 s de son en arabe).

## 5. L'économie possible par mois

Projection du journal réel (2.1 jours, 5.78 $ au total) sur 30 jours, au prix de Flash (la relecture
du storyboard comptée sur Flash, comme aujourd'hui) :

| Si on remplaçait Gemini sur… | Aujourd'hui | Au 1ᵉʳ janvier 2027 (Flash ×2) |
|---|---|---|
| les 4 étapes testées | **≈ 5.64 $/mois** | **≈ 11.27 $/mois** |
| **si c'est DeepSeek Flash qui remplace Gemini** sur ces 4 étapes (coût mesuré, heures creuses ; ×2 en heures pleines) | ≈ 1.75 $/mois (≈ 3.49 $ si tout tombe en heures pleines) | pas de changement de prix annoncé |
| toutes les étapes texte (sauf recherche Google et relecture du script) | ≈ 9.25 $/mois | ≈ 18.50 $/mois |

Pour comparer : sur la même période, tout Gemini coûte ≈ 82 $/mois (avant les économies du 28/10) ;
les étapes texte n'en sont qu'une petite part : l'essentiel est la vidéo (`finder._watch` ≈ 42 %).
Avec Groq (gratuit) l'économie est totale (5,64 $ → 0 $) ; avec DeepSeek elle est de Gemini moins le coût DeepSeek de la ligne ci-dessus. La réflexion de DeepSeek (≈ 6 000 à 8 000 tokens par étape) est facturée comme sortie.

## 6. Ce qu'il faudrait changer dans le code (non fait)

1. **`ai_models.STEPS`** : chaque étape reçoit une liste ordonnée de (fournisseur, modèle), par exemple
   `"storyboard.write": [("groq", "openai/gpt-oss-120b"), ("gemini", FLASH)]`. `model_for` reste pour Gemini ;
   une nouvelle `providers_for(step)` rend la liste.
2. **Un client par fournisseur** (`providers.py`) au format OpenAI (Groq, DeepSeek) : même texte de prompt, mode JSON
   (`response_format`), `max_tokens`, température ; la réflexion (`thinking`) de Gemini n'a pas d'équivalent direct.
3. **Dans `GeminiAIGenerator._generate_content`**, avant l'appel Google : si l'étape a un premier fournisseur autre que
   Gemini **et** que les `parts` ne contiennent que du texte, on l'essaie. **Secours automatique sur Gemini** si :
   erreur réseau, délai dépassé, 429 (limite) ou 413, JSON illisible, ou réponse jugée inutilisable par l'étape (le
   test qui existe déjà, ex. `_is_usable`). Toutes les étapes de l'app passent par cette méthode : aucune autre
   ne change.
4. **Un compteur de limites** : lire les en-têtes `x-ratelimit-remaining-*` de Groq ; si la minute ou le jour est
   épuisé, passer directement à Gemini (pas d'attente de 30 s pendant un montage).
5. **Le journal d'usage** (`log_usage`) note le fournisseur ; `ai_models.PRICES` reçoit les prix (0 pour Groq,
   DeepSeek en heure creuse / pleine) : le coût du mois reste juste.
6. **Les clés** dans `.env` ; si une clé manque, l'étape va directement sur Gemini.
7. **Tests** : un faux Groq qui répond 429 → l'appel finit sur Gemini ; une étape avec image → jamais envoyée à Groq ;
   JSON cassé → secours.

## 7. Coût réel de l'étude

| Fournisseur | Coût |
|---|---|
| Gemini | **0.371 $** (budget 0,50 $) |
| OpenAI whisper-1 | 0.018 $ |
| Groq | 0 $ (offre gratuite) |
| DeepSeek | 0.075 $ (budget 1 $)  |
| Qwen | 0 $ — pas encore testé |

## Pour finir Qwen

1. Ajoute `DASHSCOPE_API_KEY=…` dans `.env` (`DASHSCOPE_BASE_URL` y est déjà).
2. Lance `python etude_modeles/video.py qwen` puis `python etude_modeles/rapport.py`. Les tableaux se complètent seuls.
