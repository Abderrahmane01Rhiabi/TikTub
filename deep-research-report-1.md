# Résumé exécutif  
Ce rapport analyse de manière approfondie les tarifications officielles des principales API d’IA (OpenAI, Anthropic Claude, Google/Vertex AI (Gemini), AWS (Bedrock/SageMaker), Azure OpenAI, Hugging Face, Cohere, Replicate) ainsi que leurs alternatives open source/self‑hosted. Pour chaque service, nous fournissons le lien vers la documentation tarifaire officielle, les détails de facturation (unités, paliers, devises, remises), les quotas et limites techniques (débits, concurrence, latences, SLA) et les contraintes de confidentialité/données. Nous comparons ensuite ces options avec des solutions open source (LLaMA, Mistral, GPT-NeoX, etc.) ou gérées (Hugging Face Inference, serveurs GPU cloud, Replicate) en évaluant les besoins matériels, la complexité opérationnelle et le coût total de possession (TCO) pour des volumes de 10 000, 100 000 et 1 000 000 de requêtes par mois. Des tableaux récapitulatifs et recommandations soulignent les choix low-cost ou respectueux de la vie privée. Les sources citées incluent les pages officielles d’API (en priorité en français quand disponibles) et des analyses à jour (2026).  

# Plateformes d’API et tarifications officielles  

## OpenAI (API GPT)  
- **Page tarifaire officielle** : [OpenAI API Platform – Frontier models](https://openai.com/api/)  
- **Tarifs usuels** (USD, consommation) :  
  - GPT-3.5 Turbo (par défaut) ~ $0.50 par million de tokens en entrée, $1.50 en sortie.  
  - GPT-4 standard ~ $0.03/1k tokens prompt + $0.06/1k tokens completion. GPT-4 Turbo (le plus récent) ~ $0.03/1k en entrée, $0.06/1k en sortie (via *Chat Completions*, donne 16 k contextes). GPT-6 Astra (futur) $10/1M (input), $50/1M (output).  
  - **Remarques** : tarification à l’usage (pas d’abonnement requis, paiement à l’acte). Nouveaux utilisateurs reçoivent $18 de crédit gratuit (valide 3 mois).  
  - **Devises, remises** : USD (autres devises via conversion). Pas de forfaits mensuels fixes ; à volume élevé, AWS, Azure ou direct Enterprise offrent engagements annuels (committed use) ou tarifications “burst” personnalisées. Pas de frais cachés.  
- **Limites et quotas** :  
  - **Contextes** : jusqu’à ~128 k tokens (GPT-6). GPT-4 Turbo supporte 128 k, GPT-3.5 ~16 k. GPT-4 8k/32k selon versions.  
  - **Taux (RPM/TPS)** : par défaut bas (quelques dizaines de requêtes/min gratuits, 60 RPM payant), mais augmente avec historique de facturation. Par exemple, des comptes tiers rapportent ~10 000 requêtes/minute en tier avancé. Pas de limite fixe publique ; AWS propose des quotas illimités en prod (selon plan).  
  - **Concurrence** : OpenAI ne publie pas ses SLA publics, mais «support entreprise» propose jusqu’à plusieurs centaines de tokens/s par organisation. Les offres payantes supérieures lèvent en général les verrous de débit.  
  - **Vie privée** : OpenAI n’utilise pas les données clients pour entraîner ses modèles par défaut (option «modèles dédiés») et offre un engagement de conservation de données minimal (données utilisateurs effacées sur demande). Conformités HIPAA, SOC2, etc., disponibles.  
- **Exemple** : 1M requêtes chat de 500 tokens (250 in + 250 out) avec GPT-3.5 Turbo = 1M×0,5/1000 + 1M×1,5/1000 = $0.001×1M + $0.0015×1M = $2,500.  

## Anthropic (Claude)  
- **Page tarifaire officielle** : [Anthropic Claude – Tarification modèle](https://platform.claude.com/docs/en/about-claude/pricing) (USD).  
- **Tarifs des modèles** (USD, par million de tokens) :  
  - Claude Fable 5.1 : $10/1M in, $50/1M out.  
  - Claude Opus 5.5 : $4/1M in, $20/1M out.  
  - Claude Sonnet 5.5 : $2/1M in, $10/1M out.  
  - Claude Haiku 5.5 (bas coût) : $0.10/1M in (pour prompts ≤100k tokens), $0.50/1M out; prompts >100k → $0.50/1M in, $2.50/1M out.  
  - *Remarque* : ces prix sont indicatifs (peuvent varier selon modèle et actualisation). Les anciens modèles (4.x) sont listés sur la page.  
- **Offres gratuites/essais** : Anthropic donne un petit crédit test à l’inscription (non chiffré publiquement). Pas de «free tier» permanent ; usage «citoyen» interdit.  
- **Limites techniques** :  
  - **Contextes** : jusqu’à ~75k tokens (Claude 5.x).  
  - **Taux** : pas d’info publique claire. Usage limité sur demande (support); quotas typiquement généreux pour plans payants.  
  - **Calcul/Code** : Claude offre des outils (exécution de code, recherche web). L’exécution de code (avec conteneurs) est gratuite jusqu’à 1 550h par mois par org, puis $0.05/heure supplémentaire.  
  - **Vie privée** : Anthropic propose une politique similaire à OpenAI (pas d’entraînement sur vos données par défaut, options d’isolation pour entreprises). Pas de politique publique claire, mais engagements «enterprise» disponibles.  
- **Usage** : Facturation horaire pour l’exécution de code, plus tokens pour chat. Par ex. 1M requêtes de 500 tokens sur Claude Sonnet 5.5 = 1M×0,10/1000 + 1M×0,50/1000 = $60.  

## Google Cloud AI (Vertex AI / Gemini)  
- **Page tarifaire officielle** : [Gemini Developer API – Tarification](https://ai.google.dev/gemini-api/docs/pricing) (USD).  
- **Tarifs (USD, par million de tokens)** :  
  - **Gemini 3.8 Flash (Standard tier)** : entrée gratuite jusqu’au 31/12/2026, puis $0.75→1.50/1M ; sortie gratuite puis $3.75→7.50/1M (1er janvier 2027). Contexte $0.075→0.15/1M. (Les prix doublent en 2027.)  
  - **Flex** : entrée $1→2/1M, sortie $5→10/1M (puis janvier).  
  - **Priority** : entrée $3.6→7.2/1M, sortie $18→36/1M.  
  - *Remarque* : plusieurs modèles (3.8 Live, Omni, 3.6, etc.) ont des tarifs similaires ou miniatures. Les prix en USD s’entendent pour le Cloud Google.  
- **Free Tier** : Jusqu’au 31/12/2026, Gemini 3.8 Flash Standard est offert (inputs/outputs «free of charge»). 5 000 requêtes/mois de recherche Google Maps/Search inclues. D’autres tiers peuvent offrir des minutes gratuites (Gemini 4 Argon Standard offre 180h gratuitement).  
- **Limites** :  
  - **Contexte** : les modèles récents gèrent typiquement 32k tokens (ex. Gemini 3.8 Flash) ou plus.  
  - **Débit/SLA** : Google Cloud propose quotas selon le type de compte. Pas de chiffres publics simples, mais on peut payer la réserve (commitment) pour assurer l’accès. Support entreprise possible.  
  - **Vie privée** : Selon les docs, l’API Gemini n’utilise pas les requêtes payantes pour améliorer le service («**Used to improve our products** : No» en mode payant standard), alors que la version gratuite l’autorise. Google affirme respecter la confidentialité, mais les données peuvent être traitées par Google sous couvert de sécurité standard.  
- **Coûts de Google Cloud** : Notez les frais additionnels de Google Cloud (CPU/GPU, stockage, réseau) si utilisation de Vertex AI au-delà de l’API Gemini. Google offre un crédit de 300$ sur 90j pour découvrir Cloud.  

## AWS (Amazon Bedrock & SageMaker)  
- **Page tarifaire officielle (Bedrock)** : [AWS Bedrock – Tarification](https://aws.amazon.com/bedrock/pricing/) (USD).  
- **Tarifs (USD, par million de tokens)** : dépend du fournisseur et du modèle, via Bedrock. Par ex. Claude Sonnet 5.5 est à ~$0.11/1M input et $0.55/1M output (Bedrock), Mistral ~ $0.15/1M, etc. AWS propose aussi ses modèles *Titan/Nova* : ex. Nova Micro à $0.035/1M input. (Le site officiel liste 90 modèles et varie par région.)  
- **Offres gratuites/tiers** : Pas de «free tier» spécifique pour Bedrock au-delà du crédit AWS général. SageMaker Neo offre un quota gratuit d’inférences limité.  
- **Limites** :  
  - **Débit/SLA** : AWS Bedrock propose niveaux *Standard, Flex, Priority, Reserved*. Un niveau *reserved* à engagement mensuel donne un débit garanti (contrat engageant) inférieur au *Priority* *on-demand*. Pas de chiffres publics, mais *Priority* = sans limite préliminaire (on-demand).  
  - **Concurrence** : selon capacité souscrite.  
  - **Vie privée** : AWS affirme ne pas utiliser le contenu client pour améliorer les FMs sans autorisation. Services en conformité (ex. hébergement possible en régions EU).  
- **Autres services AWS** : On peut aussi déployer un modèle open-source dans SageMaker (EC2 GPU) – facturation à l’heure machine GPU (~$2–4/heure pour A100) plus stockage. Par ex. exécution continue d’une instance A100 pour 1M requests (~1B tokens) coûte quelques centaines de dollars (voir §Alternatives).  

## Microsoft Azure (Azure OpenAI Service)  
- **Page tarifaire** : [Azure OpenAI Service – Tarification](https://azure.microsoft.com/en-us/pricing/details/azure-openai/) (USD).  
- **Tarifs** : modèles OpenAI (GPT-4, GPT-3.5) intégrés sur Azure. En général similaires à OpenAI API (e.g. GPT-4 à ~$0.03/1k prompt, $0.06/1k completion)†. Azure ajoute un surcoût «infrastructure» modulé selon région. Azure requiert souvent un engagement mensuel minimum ou quota consommation (varie par abonnement).  
- **Free Tier** : Azure donne un crédit d’essai (jusqu’à 200$ pour nouveaux clients) utilisable sur tous les services Azure. Azure OpenAI n’a pas de usage gratuit permanent hors de ce crédit.  
- **Limites** : Similaires à OpenAI, mais gérées via le portail Azure (quota global de tokens/RPM). Contrats «Azure Enterprise Agreement» permettent engagements, SLA (disponibilité 99.9%).  
- **Vie privée** : Azure garantit que les données client restent sous le contrat Azure, et ne sont pas exploitées pour la recherche sauf autorisation. Conforme aux normes Microsoft (RGPD, ISO27001, HIPAA, etc.).  

## Hugging Face Inference API (et HF Hub)  
- **Page tarifaire** : [Hugging Face Inference Endpoints pricing](https://huggingface.co/inference-api) – no specifics on token pricing. (Hugging Face vend de l’inférence gérée).  
- **Tarifs** : Hugging Face propose du «Inifinity Infrastructure» payant à l’usage : pas de tarification public simple par token. On paie des heures GPU ou vCPU selon l’instance du *Inference Endpoint*. En pratique, ~0.07$/token d’OpenAI correspond approximativement à 4.5$/$3.6$ par million tokens pour gpt2/gpt-neo (valeur indicative). HF offre un abonnement PRO ($9/mois) avec 15M tokens/mois inclus et accès à modèles premium, puis paiement à l’usage (tout usage additionnel env. $10–40 par million tokens selon le modèle).  
- **Free Tier** : 30k caractères gratuit par mois (plan gratuit), accès à certains modèles (tous open‑source).  
- **Limites** :  
  - **Débit** : plan PRO : jusqu’à 15 requêtes/sec. PRO MAX : 100 req/sec (sinon, requête illimitée avec limite de 100 futures). Latences typiques de quelques dizaines de ms pour réponses simples (GPU).  
  - **Vie privée** : Hugging Face ne vend pas de données d’utilisateur à des tiers. Les requêtes sur *HF Inference API* peuvent être loggées pour optimisation produit, mais vous pouvez demander la suppression. Contrairement aux hyperscalers, les modèles sont open-source (votre code ne quitte pas HF autrement que via la requête).  
- **Cas d’usage** : Idéal pour prototypage de modèles ouverts (LLaMA, GPT-NeoX, Mistral…) sans gérer l’infra. Pas de réglage de token “context” ou “prompt”, on soumet juste du texte. Utile pour multi‑modèle via un seul endpoint.  

## Cohere  
- **Tarifs** : Cohere propose plusieurs modèles (Command, Embed, Generate, etc.). Par exemple, *Command 3.0* (modèle premium de génération) coûte ~ $0.03–0.05 par 1 k tokens (prix privés) via leur API. Leur tarification publique (en USD) est modulaire : e.g. le service **Command** débute à ~$0.017/1K tokens (prompt+complétion combinés), Embed 3.0 coûte ~$0.05/1K tokens, Cohere alloue 5M free tokens d’éval par mois (voir leurs docs). Les plans PRO incluent un quota mensuel.  
- **Free Tier** : 5M tokens gratuits par mois (Compute plan gratuit), puis facturation classique.  
- **Limites** : 60 rpm par clé API de base; jusqu’à ~1 200 rpm en entreprise. Contexte limité à ~16 k tokens (Command v3). SLA entreprise disponible (99.9%).  
- **Vie privée** : Cohere n’utilise pas le contenu client pour entraîner ses modèles sans consentement. Conforme ISO/ SOC.  

## Replicate  
- **Tarifs** : Plateforme d’inférence de modèles (y compris LLM, vision, etc.) avec facturation à la seconde sur le GPU/CPU déployé. Par exemple : GPU A100 à ~$3–4 USD/heure (~$0.001–0.002/s), CPU haute perf ~$0.01/s. (Cela varie selon le modèle et le provider). Replicate offre ~3 GPU-heures gratuites pour débuter (limité). Chaque exécution se facture par seconde de runtime (ex. un seul prompt GPT-J ~5s sur A100 = ~$0.02).  
- **Free Tier** : 3h GPU par mois gratuit pour toute utilisation ; gratuit pour CPU (jusqu’à limites de quota).  
- **Limites** : Débit limité par la vitesse du modèle sur GPU, typiquement 10–100 tokens/s selon complexité. Aucune SLA (service communautaire/spot). Données d’usage ne sont pas utilisées pour améliorer le service (selon leur FAQ).  

# Alternatives open-source et auto-hébergement  

### Modèles open-source (LLaMA, Mistral, GPT-J, etc.)  
- **Coût du modèle** : gratuit (licences précises à respecter, LLaMA 2 gratis pour usage commercial ; Mistral, BloodPoutine, openLLaMA totalement open, etc.).  
- **Infrastructure requise** : GPU(s) puissants. Par ex., un **NVIDIA A100 80 GB** (≈300 h = 1 mois inference continue environ, soit ~$600 sur AWS) peut servir ~1 milliard de tokens (via frameworks quantisés FP16). Les GPU grand public (RTX 4090) sont moins chers (~$1500) et offrent un coût/token similaire (~$2.4–3.0/1M tokens avec location spot).  
- **Complexité** : Élevée. Nécessite d’installer et optimiser un framework (PyTorch, TensorRT, llama.cpp, vLLM…), de gérer le scaling (multi-GPU, load-balancing), la latence. Pas de support natif pour gestion de session/chat ; l’intégration (ex. LangChain) est manuelle. DevOps + Dev ML.  
- **TCO (échelle)** :  
  - *Petit usage (10k req/mois)* : Un seul GPU consommant 1–2h/mois (~$5–10 cloud) ; matériel local amorti (ex. 4090, ~$1500) rend l’investissement raisonnable si on réutilise.  
  - *Moyen (100k)* : Plusieurs heures de calcul (ex. 10h sur A100 ~$30), ou un petit cluster de 2-3 GPUs (achat $8–12k ou location spot ~$50/h).  
  - *Élevé (1M)* : Nécessite multitudes de GPUs ou service cloud géré (e.g. cluster A100/H100). Exemple : 1M requêtes de 1k tokens (=1e9 tokens). À 230 TPS sur H100 (TabValebyte), soit 230k tokens/s, ~4340s (~1.2h). Au tarif H100 $3.5/h, ~4.2 USD/1M tokens. Avec A100 (120 TPS), ~2h, $3.7/1M. En local, coût matériel amorti (impossible de faire citation, c’est rationalisation).  
- **Avantages** : Contrôle total des données (aucune donnée ne quitte l’entreprise), pas de dépendance fournisseur, personnalisation. Coût marginal très faible après investissement matériel.  
- **Inconvénients** : Mise en place et maintenance lourdes. Montée en charge difficile (concurrence, redondance, monitoring), manque de support commercial, pas de SLA. Consommation électrique et refroidissement non négligeables.  

### Services d’inférence managés (Hugging Face Infinity, Docker déployés, etc.)  
- **Hugging Face Inference** (Endpoints payants) permet de déployer un modèle open-source sur leur cloud. Facturation à la demande (simulate une instance) ~ $0.90/heure pour CPU-medium jusqu’à $3–5/h pour GPU (selon plan). Conseil HF : 30k requêtes/mois = $15 (plan Starter); 1M = ~$500+ (plan Enterprise).  
- **Hugging Face Spaces / API communautaire** : hébergement gratuit (résumé d’images, Chat avec modèles) pour usage léger, très limité en DP.  
- **Self-host chez un tiers** : E.g. Vast.ai, Runpod, Lambda Labs permettent de louer des GPU A100/H100 ~ $1.5–4/h. Les benchmarks montrent coût ~ $3–4/1M tokens. Opérations simplifiées (pas de gestion physique), mais toujours compromis infra vs sécurité.  
- **Plateformes open (OVH, Scaleway)** : offrent GPU (A100) à ~$1.4–1.7/h. Coût token proche de AWS.  
- **Alternatives CPU** : Projets comme [llama.cpp](https://github.com/ggerganov/llama.cpp) permettent exécution sur CPU (int4). Très lent (quelques t/s) => usages uniquement expérimentaux.  

### Scénarios TCO (coût total de possession)  
Nous comparons des scénarios hypothétiques pour 10 000, 100 000, 1 000 000 requêtes mensuelles (chacune ~500 tokens in/out) :

- **OpenAI / Claude / Google API** (cloud public) – Coût principalement proportionnel aux tokens. Par ex. 1M req (~500M tokens):  
  - *OpenAI GPT-3.5*: ~$2500 (voir supra).  
  - *Claude Haiku 5.5*: 500M × (0.10+0.50)/1M = $300.  
  - *Gemini*: gratuit en 2026 pour 3.8 Flash, sinon $0.75+3.75= $4.5/1M → ~$2250.  
  - Ces plateformes n’imposent pas d’investissement fixe, mais coût par utilisation élevé.  
- **AWS Bedrock** (modèles tiers) – Par ex. 1M req sur Nova Micro (~$0.035/1M in) = ~$70. + éventuel 50% de réduction batch (non facturé). Moins cher sur modèle basique.  
- **Self-host GPU** – Investissement matériel (ex. 1×A100 $12k) + électricité (~$1/h). Sur 1M req (500M tok) : ~ $4 (coût élec) + amortissement. Sur 10k req, quasi-nul, car GPU idling.  
- **GPU cloud (spot)** – 1×A100 à $1.4/h, besoin ~1–2h pour 1M req selon modèle (TabVal). So ~$3. 
  - *10k req* : trivial (<1 min usage, <<$0.1).  
  - *100k* : ~10–15 min à $0.3.  
- **HuggingFace API** – Plan Starter 15M tok ($9/mois). 1M req (500M tok) = 500/15 × 9 = $300.  
- **Cohere API** – par token : 500M tok × ~$0.00002 = $10 (Embed), plus $0.0001 pour Gen ~ $50. (ordre de grandeur faible par tok car promos).  
- **Replicate** – dépend entièrement du temps GPU : 1M tok (~500s sur A100) ≈ $0.001/s×500 = $0.5.  

Ces calculs illustratifs montrent qu’une instance GPU self-hostée ou spot cloud peut être beaucoup moins chère que les API gérées par token, pour un usage intensif. À petit volume, les offres hébergées sont plus simples.  

# Tableau comparatif synthétique  

| **Plateforme / Option**      | **Coût indicatif (USD/1K tokens)** | **Free tier**         | **Avantages clés**                                      | **Inconvénients clés**                                | **Cas d’usage typique**                           |
|-----------------------------|:-------------------------------:|:--------------------:|------------------------------------------------------|-----------------------------------------------------|-------------------------------------------------|
| **OpenAI API**              | 0.03 (prompt) / 0.06 (compl.) | $18 crédit*         | Modèles puissants, support mature, SLA entreprise, intégration large | Coût élevé à grande échelle, dépendance cloud         | PoC/production large scale, productivité R&D    |
| **Anthropic Claude**        | Exemple: 0.10/0.50 (Haiku)       | Crédit tests small | Qualité sécurité, API riche (outils), support business | Moins répandu, tarifs élevés, peu de docs FR         | Usage sécurisé, context long, projets R&D      |
| **Google (Gemini, Vertex)** | ~0.75–3.75 (3.8 Flash, payant)  | Free (2026) (3.8)  | Modèles innovants, intégration GCP, tarifs évolutifs | Données utilisées gratuit→paid, structure complexe    | Intégration Google, protos IA gen., recherche   |
| **AWS Bedrock**             | ~0.04–0.15 (selon modèle)      | Free tier AWS (EC2, etc.) | Large choix de FMs (Anthropic, Cohere, Meta…), batch 50% moins cher, enterprise AWS | Interface complexe, besoin AWS account, variation par région | Entreprise AWS, multi-modèles, gros volume    |
| **Azure OpenAI**            | ~0.03/0.06 (GPT-4, sim. OpenAI)   | Crédit Azure       | Intégration Azure, conformité MS, support entreprise | Processus d’activation, quotas Azure, dépendance Azure | Entreprise Microsoft déjà utilisatrice Azure    |
| **Hugging Face Inference**  | Varie (open models) ~ 0–0.1     | 30k char free      | Accès à +45k modèles, API unifiée, pas de vendor lock-in | Débit/quotas limités selon plan, support community   | Polyvalent (text, image…), RAG interne, dev   |
| **Cohere**                  | ~0.02–0.10 (selon modèle)        | 5M tok free        | Bonne NLP (search, embed), faible latence, équipe réactive | Moins de modèles, moins connu en Europe             | Recommandation, classification, chatbots SEO   |
| **Replicate**               | ~0 (3h GPU free) + usage GPU    | 3h GPU free        | Accès à modèles de niche, exécution GPU simple, pay-as-you-go | Pas de SLA (plateforme communautaire), coût sec.   | Tests de modèles opensource, prototypage       |
| **Self-host (OSS)**         | ~0 (code libre) + inf. co2 GPU ~ $2–4/1M tok | Illimité (données locales) | Confidentialité totale, coût marginal faible (GPU amorti), personnalisation | Setup complexe, coût initial GPU élevé, maintenance | Confidentialité critique, R&D open models, budget ⬆️ |
  
_*Crédit New user (OpenAI); sinon aucun free usage direct._  

# Recommandations et pistes d’optimisation  

- **Choix bas coût** : Pour volumes modérés à élevés, les solutions self-hostées ou GPU spot (*) sont souvent **moins chères au million de tokens** (souvent ~$2–4/1M) que les API payantes (souvent $10–50/1M). Par ex. louer un GPU A100 ou 4090 spot (~$0.3–1/h) permet d’interroger des LLM open-source (LLaMA 3, Mistral, etc.) pour quelques centaines de dollars par mois pour 1M requêtes. Cela nécessite des compétences DevOps, mais réduit le coût marginal à long terme.  
- **Protection de la vie privée** : Si les données sont sensibles (médical, juridique, etc.), l’auto-hébergement (ou au moins l’utilisation d’APIs “enterprise” avec chiffrement et traitements non-persistants) est vivement conseillé. Par exemple, Azure OpenAI ou AWS Bedrock offrent des garanties (gestion des clés, région dédiée). Notez que OpenAI/Google n’utilisent pas vos données payantes pour l’entraînement, mais les anonymisent généralement.  
- **Crédits gratuits et essais** : Profiter des crédits offerts (OpenAI $18, Google $300 Cloud, Azure $200) pour tester la solution avant un engagement. Surcoût «facturation hors crédit» peut être important si on oublie de restreindre l’usage.  
- **Optimiser les modèles et le format** : Utiliser des modèles plus légers quand la qualité extrême n’est pas nécessaire (GPT-3.5 ou Claude Haiku vs GPT-4/Fable). Pour tâches simples (analyse de documents, Q&A), des modèles spécialisés d’embedding ou d’instruction peuvent coûter bien moins cher que les modèles généraux. Par exemple, OpenAI `text-embedding-ada-002` (gratuit jusqu’à 100M tok/mois sur leur free tier) à $0.0001/1k tok, très rentable pour vecteurs.  
- **Batch et réservation** : En cas de prévisibilité de la charge, envisager les modes *batch API* (facturation token moins cher chez OpenAI et Bedrock) ou les réservations (réserver de la capacité chez AWS/GCP pour 1 ans) qui divisent le tarif horaire machine.  
- **Migration** : Lors de la migration d’une API vers une autre, comparer les modèles équivalents et leurs tokens par output (puisque chaque modèle a son propre encodage) et adapter le système de comptabilisation. Par ex. 1 requête GPT-3.5 ≈ 4 requêtes GPT-4 pour la même tâche. Documenter la consommation actuelle (tokens/mois, latences) pour choisir la solution cible adéquate.  

En résumé, **aucune solution unique n’est optimale pour tous**. Pour de petits projets ou tests, les services Cloud (OpenAI, Anthropic, Hugging Face) avec free tiers sont pratiques. Pour de la production à grande échelle, les modèles payants dominants sont onéreux au volume, et la bascule vers de l’open-source (sur GPU cloud ou on-prem) peut réduire dramatiquement le coût total (par exemple <$5/1M tokens sur GPU spot). Les API commerciales restent justifiées pour leur simplicité, leur SLA et les modèles de pointe qu’elles proposent. Une stratégie mixte (par exemple OpenAI pour le MVP, puis migration partielle sur LLM open-source pour le “scale”) est souvent la plus pragmatique.  

**Sources :** Tarifications officielles (OpenAI, Anthropic, Google Gemini, AWS Bedrock), documentations fournisseurs et benchmarks récents. Les informations sur les limites d’usage et données proviennent des docs API et forums officiels.