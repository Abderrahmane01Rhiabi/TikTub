# Résumé exécutif

TikTub exige une **recherche automatisée multi-source** pour retrouver les vidéos originales et tout l’écosystème de montage. Voici les points clés du rapport :

- **API/Moteurs vidéo** : YouTube Data API (gratuite, quotas limités), Google Custom Search (vidéo) facturée ($5/1000 requêtes), SerpApi (fournit Google Vidéos et Lens : 250 requêtes/mois gratuites, puis 25 $/mois pour 1 000), Bing Video Search (Azure, forfait gratuit ~1 000 requêtes, puis ≈3 $ pour 1 000 requêtes), DuckDuckGo via bibliothèques non officielles (ex. `ddgs`, avec 0$/mois mais fiabilité moindre), TikTok/Douyin (pas d’API publique de recherche – seuls des “research tools” très restreints pour chercheurs agrées), X/Twitter (plus d’accès gratuit – seules offres payantes coûteuses). Bilibili/Yandex ne proposent pas d’API de recherche ouvertes (il faudrait extraire via scraping ou outils tiers). 

- **Téléchargement de vidéos** : outils open source comme **yt-dlp** (fork de youtube-dl) peuvent obtenir la meilleure qualité possible sur YouTube et d’autres plateformes, souvent jusqu’à 1080p voire 4K si disponible. L’utilisation de cookies/session permet d’accéder à du contenu restreint (vidéos 18+, vidéos restreintes par région). Les “client Android” ou “client TV” de yt-dlp changent les endpoints vidéo (permettant parfois plus de formats), mais peuvent nécessiter un **PO Token** comme preuve d’origine pour éviter les refus 403. Par exemple, sans PO Token, on peut être limité à 360p, mais avec l’extension BgUtils (PoToken) on récupère les flux HD. D’autres outils existent (ex. plugins Android, Invidious pour YT, ou sites tiers), mais présentent des risques légaux potentiels (contrevenant aux TOS) et techniques (blocages).

- **Vérification et matching** : pour confirmer qu’une vidéo trouvée correspond à la source, on utilise des méthodes automatiques. L’**analyse d’image inversée** (via Google Vision, TinEye, Yandex, etc.) peut trouver des copies à partir de captures. L’**empreinte audio** (fingerprinting) permet de comparer la piste sonore à une base (ex. Chromaprint/AcoustID, librarie open source ou la bibliothèque Python *dejavu*). L’**empreinte vidéo perceptuelle** (perceptual hashing) peut détecter des vidéos similaires même transformées : par exemple **pHash** (bibliothèque C++ GPL) calcule des hachages robustes. OpenCV ou FFmpeg offrent aussi des outils pour extraire des clés d’images/frames à comparer.

- **Effets sonores & musiques libres** : on dispose de nombreuses bibliothèques gratuites. Par exemple, *Freesound* (CC-BY) propose une API riche; *Pixabay* et *Pexels* offrent sons/musiques CC0 via API; *Free Music Archive* et *Incompetech* fournissent des pistes CC-BY par catalogue web. Chacune a ses propres formats (MP3, WAV…) et licences (souvent attribution requise). Un tableau détaillé récapitule ces bibliothèques, leur licence (CC0, CC-BY), présence d’API et qualités audio.

- **Outils de montage & amélioration** : la post-production est assurée par des outils libres et commerciaux. **FFmpeg/libav** (CLI) est incontournable pour convertions et filtrage; **VapourSynth/Avisynth** pour scripts de traitement vidéo avancés; **HandBrake** pour transcodage; **Shotcut** ou **DaVinci Resolve** pour montage visuel (free). L’**upscaling AI** se fait avec Real-ESRGAN ou Video2X (haute qualité AI super-résolution). Des plugins de filtrage (dénosage, stabilisation) existent dans ces frameworks (p. ex. *VinCE* pour démonter et reassembler). On peut automatiser toute la chaîne (CI/CD) en combinant ces outils en ligne de commande (par exemple, exécution dans un conteneur Docker ou un pipeline CI hébergé avec GPU).

- **Coûts estimés** : les recherches video peuvent être très économiques : YouTube et DuckDuckGo sont gratuits, Google CSE coûte environ 5 $/1000. SerpApi propose 250 requêtes/mois gratuites puis 25 $/1000, etc.. Pour le traitement vidéo, un serveur CPU coûte quelques cents par heure (Linux VM ~0,05 $-0,20 $/h), un GPU ~1-3 $/h (selon la machine). Des tableaux illustrent ces coûts pour 100/1 000/10 000 requêtes par mois et pour des charges de traitement (par ex. 100h CPU vs 10h GPU). 

- **Architecture recommandée** : un pipeline *quotidien* ou *en continu* combinant toutes les sources de recherche, avec agrégation et filtrage préalable. Ensuite, un module IA évalue la pertinence (ex. GPT/Gemini pour décrire les vidéos candidates) et une déduplication (hachage, métadonnées). La vidéo la plus pertinente est téléchargée (yt-dlp + cookies/PoToken selon la source), puis passée en post-traitement (montage et amélioration qualité). Le flux global est schématisé ci-dessous en mermaid. On prévoit des modes dégradés (ex. basculer sur un autre moteur de recherche si l’un est bloqué), la gestion sécurisée des tokens/cookies, et la conformité aux TOS. 

```mermaid
graph LR
    A[Recherche multi-sources<br/>(YouTube API, Google Video, SerpApi, DDG, TikTok scrap, X API, etc.)] --> B[Agrégation & Filtrage]
    B --> C[Vérification & IA (matching image/audio, analyse de contenu)]
    C --> D[Téléchargement vidéo<br/>(yt-dlp + cookies/PoToken, clients Android, etc.)]
    D --> E[Post-traitements<br/>(FFmpeg, upscaling AI, montage, eff. sonores)]
    E --> F[Stockage & Diffusion]
```

- **Risques légaux & conformité** : il faut veiller aux droits d’auteur et aux **conditions d’utilisation** des plateformes. Télécharger ou republier une vidéo sans autorisation peut violer le copyright. Les API officielles (YouTube, TikTok) imposent des quotas et interdisent certains usages (scraping intensif, re-distribution). Il faudra gérer finement les quotas et prévoir un système de rotation d’IP/cookies pour réduire le blocage. En cas d’API payantes (SerpApi, Azure), vérifier l’utilisation autorisée. En résumé, privilégier les contenus libres ou bien citer les sources, et intégrer des mécanismes de respect de la loi (ex. suppression automatique si identification de contenu protégé).  

Les sections suivantes détaillent ces points avec des tableaux comparatifs et références officielles.

## 1. Recherche de vidéos : APIs et moteurs

| Plateforme / Outil        | API dispo ?                    | Gratuit / Quota                   | Tarification                                    | Fiabilité pour source originale | Notes d’intégration                             |
|---------------------------|--------------------------------|-----------------------------------|-------------------------------------------------|-------------------------------|-------------------------------------------------|
| **YouTube Data API**      | Oui (officielle)               | **100 appels search/jour**        | Aucun coût $; quotas gratuits (10k unités/jour) | Très fiable (accès direct aux données YT) | Clé API Google requise. Par défaut 100 requêtes/jour pour `search.list`. Dépassement possible via augmentation du quota (gratuit). Facile à intégrer (Google API REST).  |
| **Google Custom Search**  | Oui (JSON API)                 | 100 requêtes/jour gratuites      | 5 $ par 1 000 requêtes          | Excellente (Google index)          | Nécessite un moteur de recherche (CSE). Permet `type=video` pour Google Vidéos. Légèrement aride à configurer.                                       |
| **SerpApi (Google)**      | Oui (Google Search, Google Videos, Google Lens) | 250 recherches/mois gratuites | Starter: 25$/mois pour 1 000 recherches  | Très fiable (données Google non modifiées) | Permet récupérer Google Vidéo (engine=google_video) et Google Lens. Intègre IP rotation. Tarification fixe  (pas de frais par requête).|
| **Google Lens**           | Oui via SerpApi               | (inclus avec SerpApi)            | (idem SerpApi ci-dessus)                       | Nombreux résultats image; utile pour recherche inversée | Pas d’API publique directe ; SerpApi ou scripts non officiels.                                          |
| **TikTok / Douyin**       | Recherche : **non**           | –                                 | –                                               | Faible (pas d’accès standard)       | Aucune API publique de recherche de contenus. *TikTok Research API* existe pour chercheurs agréés (sinon scraping/détournement risqué).             |
| **X (Twitter) Vidéos**    | Recherche : **non**           | –                                 | Aucune offre gratuite (plans payants très chers) | Limité (accès restreint)             | L’API officielle nécessite un compte payant (Essential ≥100$/mois pour accès basique). Plus de tier gratuit depuis 2023.                              |
| **DuckDuckGo (via ddgs)** | Non officielle (bibliothèques Python) | Illimité (gratuite)               | –                                               | Modérée (selon fiabilité scraping)  | `ddgs` (Dux) peut scrapper DuckDuckGo vidéos. Gratuit, mais risque de blocage si usage intensif. Pas d’API officielle.                   |
| **Bing Video Search**     | Oui (Azure Cognitive Service) | ~1 000 requêtes gratuites (Free tier) | ~$3-$5 par 1 000 requêtes (Standard S1)       | Bonne (résultats MS/Bing)           | API Bing Search v7 (Azure) supporte recherche vidéo (nous donnerà JSON avec miniatures). Nécessite abonnement Azure.                                      |
| **Bilibili / Youku**      | Non (pas d’API publique)      | –                                 | –                                               | Faible / N/A                       | Recherche par scraping ou par DDG/Serpapi sur `site:bilibili.com`. Intégration complexe (site chinois).                                                |
| **Yandex Video Search**   | Non (pas d’API publique)      | –                                 | –                                               | Faible / N/A                       | (On peut tenter via ddgs ou scraping de `yandex video`, mais pas d’API ouverte). |

*Sources* : Google Data API (docs quotas par défaut), SerpApi pricing, guides TikTok dev (recherche réservée aux chercheurs), ddgs GitHub (utilise DuckDuckGo pour vidéo).

## 2. Outils de téléchargement

| Outil / Méthode        | Compatible plateformes         | Qualité maxi récupérable      | Cookies/Session nécessaires | Risques / Notes                                  |
|------------------------|--------------------------------|------------------------------|-----------------------------|--------------------------------------------------|
| **yt-dlp (CLI)**       | YouTube, TikTok, X, Invidious, etc. (3000+ sites) | Jusqu’à 1080p ou 4K (selon contenu) | Parfois oui (pour YT Premium ou majeurs) | ★★★★☆ Solution la plus courante. Gère les cookies. Nécessite parfois un *PO Token* pour YT (voir ci-dessous). Active par défaut la meilleure qualité disponible. |
| **youtube-dl**         | Similaire à yt-dlp (fork)      | jusqu’à 1080p (souvent 720p)  | Oui                         | ★★☆☆☆ Moins maintenu que yt-dlp. Peut manquer certaines améliorations récentes (PO token, sécurité). |
| **Plugins Android**    | YT-dlp mode `--player_client android`  | 720p-1080p (selon vidéo)     | Souvent oui                 | ★★★☆☆ En imitant un client Android, on obtient parfois des formats MP4 via l’app mobile YouTube. Requiert des mods (po_token) pour hauts débits. |
| **TV (yt-dlp)**        | YT-dlp mode `--player_client tv`       | 1080p (et flux HLS)          | Moins (pas d’authentification) | ★★★☆☆ Simule l’app TV (ex: Android TV). Évite en général les tokens PO, mais certaines vidéos restent DRM. Formats HLS disponibles. |
| **bgutil / PO-Token**  | Plugin pour yt-dlp (BgUtils) | Indispensable pour >360p sur YT | N/A                         | ★★☆☆☆ *BgUtils* ou plugins associées génèrent un *Proof-of-Origin* Token, nécessaire pour débloquer les flux HD sur certains clients YouTube. Complexe à configurer, mais permet d’accéder au mode premium sans premium. |
| **Clients mobiles / Web** | (p.ex. Invidious, TikTok API clients) | Variable (selon app)         | Souvent oui                | ★★★☆☆ On peut utiliser certaines apps mobiles ou Invidious (YT alternatif) pour obtenir des liens directs. Ces solutions contournent les restrictions mais peuvent être instables. |
| **DDOWNR, SnapTik, etc.** | Sites tiers de téléchargement TikTok/YouTube | 1080p (rarement plus)         | Non (certains stockent cookies) | ★★☆☆☆ Webapps (ex. Snaptik.app pour TikTok) offrent des téléchargements sans code, mais sont non-officiels et souvent limités. Risque de publicités ou de blocage. |

*Notes* : Selon les tests pratiques, télécharger directement via mobile (sans plugin) ne donne souvent que du 360p (formats “ABR”). L’utilisation d’un PO Token (via *yt-dlp* + plugin *BgUtils*) permet d’accéder aux flux GVS internes en haute résolution. Concernant la légalité, le téléchargement de vidéos sans autorisation peut violer les ToS ou droits d’auteur – cibler d’abord les vidéos libres de droits ou publiques.

## 3. Vérification et matching

- **Recherche inversée d’images** : outils web/API (Google Vision, TinEye, Yandex Images) permettent d’identifier des copies visuelles d’une image extraite de la vidéo. Google Vision propose un *Web Detection* (API Cloud Vision) pour trouver où une image (frame) apparaît en ligne. Ces services sont précis mais limités en volume (Google Cloud : ~1,50 $ pour 1000 requêtes; free tier faible). On peut aussi passer par des alternatives open-source (yandexapi, etc.), ou simplement faire une recherche Google classique avec une capture.

- **Empreinte audio (fingerprinting)** : on peut extraire l’empreinte sonore d’une vidéo puis la comparer à une base. Par exemple, la bibliothèque open-source **Chromaprint** (AcoustID) calcule des empreintes audio. Sa base en ligne *AcoustID* contient des millions de pistes musicales identifiées. La lib Python *pyacoustid* ou *dejavu* (basée sur pHash audio) facilitent cela. La robustesse est élevée pour la musique ou dialogues clair, moins pour bruit. Derrière, il faut stocker/fuzzer les empreintes (faible coût CPU, open source).

- **Empreinte vidéo perceptuelle** : pour comparer vidéos visuellement, on peut recourir à un algorithme de *perceptual hash*. La bibliothèque **pHash** (C++ GPL) le fait pour images, audio, vidéo. En découpant la vidéo en keyframes et en calculant un hash d’image (DCT, etc.), on peut comparer des vidéos modifiées (re-codées, redimensionnées). La tolérance peut être ajustée pour bruit. Autre approche : utiliser OpenCV pour comparer des images-clé (par similarité pixel ou SIFT).

- **Métadonnées et autres** : on peut aussi vérifier le titre, description, sous-titres (s’ils existent) pour confirmer le match. Parfois une simple comparaison des 5 premières secondes (audio+image) suffit. 

Tableau simplifié des méthodes :

| Méthode                  | Outils/libs (Open Source)           | Usage typique                         | Précision / Notes                           |
|--------------------------|-------------------------------------|---------------------------------------|---------------------------------------------|
| **Image inversée**       | Google Vision API, TinEye, Yandex   | Capturer frame clé (JPEG) et rechercher sur web | Bien adapté si image exportée. Rapide, mais API payantes au-delà du free. |
| **Audio fingerprint**    | Chromaprint/AcoustID, dejavu | Extraire mp3 du clip (ffmpeg) puis fingerprinter | Excellente pour musique et dialogues clairs (base large). Doit disposer ou créer base de références. |
| **Hash vidéo (perceptuel)** | pHash, ffmpeg (vhakie), OpenCV | Générer hash par frame ou bloc vidéo            | Peut détecter mêmes contenus malgré recompression. Doit gérer les faux positifs selon tolérance. |
| **Métadonnées / texte**  | N/A (imdb, OCR, NER)             | Vérifier titres, descriptions, sous-titres    | Approche faible seule, mais aide à confirmer. |

## 4. Effets sonores & musiques libres

De nombreuses bibliothèques de sons libres existent (souvent sous licence Creative Commons) :

| Bibliothèque       | Type / Licence       | API disponible | Qualité / Formats        | Remarques                                  |
|--------------------|----------------------|----------------|--------------------------|--------------------------------------------|
| **Freesound**      | CC BY 3.0 (Attribution requise) | Oui (REST API)  | WAV/MP3 (~44kHz)         | Large base de bruitages/samples (étendu). API bien documentée (mot-clef, tags). Nécessite clef API gratuite. |
| **Pixabay Audio**  | CC0 (Domaine public) | Oui (REST)     | MP3 (320kbps), WAV       | Musiques et effets gratuits. API qui renvoie liens MP3/WAV. Très simple d’utilisation (HTTPS JSON).|
| **Pexels Audio**   | Licence Pexels (similaire CC0) | Oui          | MP3/WAV                  | Encore plus récente qu’images; Sons & musiques libres. API documentée (nécessite clé API) – audio illimité. |
| **Free Music Archive** | CC-BY / CC-BY-SA (variable) | Non officiel (RSS/JSON) | MP3/AAC (320kbps)        | Archive de musique gratuite par divers artistes. Site web (certains contenus CC0). Pas d’API officiel accessible public. |
| **Incompetech**    | CC BY (Attribution)  | Non (site web) | MP3 (320kbps)            | Catalogue de Kevin MacLeod (compositions). Licence CC BY (nécessite mention crédit). Téléchargement manuel (pas d’API). |

*(D’autres sources libres : *Jamendo*, *CCMixter*, *SoundBible*, *Mixkit*, etc., souvent aussi CC-BY ou CC0.)*

Ces bibliothèques fournissent majoritairement des formats haute qualité (souvent 44,1-48kHz, 320kbps MP3 ou WAV). Elles couvrent bruitages (Freesound), musiques instrumentales (Incompetech, Pixabay), et permettent souvent le filtrage par genre ou tag via leur API.

## 5. Outils de montage et amélioration qualité

- **FFmpeg / Libav** (open source) : incontournable pour toute manipulation (transcodage, découpage, enchaînement, filtre vidéo/audio). Supporte énormément de codecs. Exemple de filtres : *unsharp*, *hqdn3d* (dénosage), *scale* (upscaling conventionnel), etc.

- **OpenCV** (open source, C++/Python) : pour traitement vidéo par image (stabilisation, détection de contours, interpolation). Permet coder des algorithmes de restauration ou d’analyse (détection de contours flous, correction couleur, etc.).

- **VapourSynth / Avisynth** (open source) : frameworks scriptés (Python-like ou langage spécifique) pour filigrane vidéo, dégrainage (par ex. plugins de débruitage, sharpening, désentrelacement). Hautement automatisables.

- **HandBrake** (open source) : UI/CLI pour encoder et compresser facilement. Prise en charge H.264/265 avec presets, options de décodeur/encodeur rapide. Bon pour lot de conversions, mais moins configurable que FFmpeg en ligne de commande.

- **DaVinci Resolve (Free)** : puissante station de montage vidéo et d’étalonnage (supports Linux/Win/Mac). Intègre des outils d’amélioration (Denoise, AI SuperScale, Stabilization). L’automatisation est limitée (scriptable via Studio payante).

- **Shotcut** (open source) : éditeur vidéo multiplateforme avec effets (filtres audio/vidéo, transitions, correction couleurs). Gratuit, supporte OpenGL & encodages modernes.

- **Plugins d’amélioration IA** : *Real-ESRGAN* (images super-résolution, utilisable sur vidéos image par image) et *Video2X* (amélioration avec Waifu2X/ESRGAN). Ils nécessitent GPU (CUDA) et fournissent un **upscaling AI** remarquable (x2 à x4 la résolution). Ces outils sont open-source (GitHub) et intégrables en script. Par exemple, Real-ESRGAN reconstruit le détail d’image, Video2X automatise pour vidéos complètes.

- **Intégration CI/CD** : tous les outils CLI ci-dessus (FFmpeg, ffmpeg, ytdlp, Real-ESRGAN, etc.) peuvent être orchestrés en pipeline (Docker + script bash/Python). On peut prévoir par exemple un pipeline GitLab/GitHub Actions/Drone pour lancer le traitement dès qu’une nouvelle vidéo est détectée. L’usage de GPU dans le pipeline (via runners dédiés) accélère l’IA.

## 6. Estimation des coûts

Les coûts dépendent du volume de requêtes et de l’infrastructure. Voici des ordres de grandeur (*indicatifs*) :

- **Recherches vidéo** : 
  - YouTube, DuckDuckGo : 0 $ (API non facturée, juste quota limité).  
  - Google CSE : 0 $ pour 100 requêtes/jour, puis ~5 $ pour 1 000 requêtes.  
  - SerpApi : 0 $ pour 250/mois (gratuit), 25 $ pour 1 000, 150 $ pour 15 000 (tarif mensuel fixe).  
  - Bing (Azure) : ~0 $ pour 1 000/mois (Free tier), puis env. 3 $/1 000 en Standard.  
  - X/TikTok APIs : accès très cher (ex. Twitter payant ~100 $+/mois) – on considère qu’on évite ou scrap.  

  *Exemple pour 1000 recherches/mois* : Google CSE ~5 $, SerpApi ~25 $, Bing ~3 $. Pour 10 000 recherches, SerpApi ~150 $, Google CSE ~50 $, Bing ~30 $.

- **Téléchargement vidéo** : gratuit (outils open-source) ; peut nécessiter un serveur pour tourner. Le seul coût peut être du trafic réseau ou un hébergement.  

- **Traitement / montage** : 
  - **CPU** : une machine cloud standard (Intel) coûte ~0,10–0,20 $/heure. 100 heures de traitement (FFmpeg, encode) ~10–20 $.  
  - **GPU** : une instance GPU (NVIDIA) ~1–3 $/heure. Un film court transformé par IA (par ex. 5 min avec Real-ESRGAN) peut prendre 0,5–1 h GPU (~1–3 $). Pour 10 heures de montage/IA, compter ~30 $.  

En résumé, les coûts fixes pour commencer sont minimes (environ 0$ pour 100 recherches mensuelles) et évolutifs selon l’usage. Les tableaux suivants illustrent ces ordres de grandeur :

| Volume recherche | Google CSE (USD) | SerpApi (USD) | Bing (USD) | Remarques                |
|------------------|------------------|---------------|------------|--------------------------|
| 100 / mois       | 0 (grâce au free)| 0 (free 250)  | 0 (free)   | Frais de setup quasi nuls |
| 1 000 / mois     | 5 $              | 25 $          | 3 $        | Séries d’API à considérer |
| 10 000 / mois    | 50 $             | 150 $         | 30 $       | Prévoir forfaits adaptés |

| Chargement CPU | Coût estimé | Usage typique                   |
|----------------|-------------|---------------------------------|
| 1 heure        | 0,10 $      | Conversion/transcodage basique  |
| 10 heures      | 1 $         | Lot de montage vidéo simple     |
| 100 heures     | 10 $        | Workflow complet sur CPU        |

| Chargement GPU | Coût estimé | Usage typique                       |
|----------------|-------------|-------------------------------------|
| 1 heure        | 1,50 $      | Upscaling AI (Real-ESRGAN) ~5 min vidéo |
| 10 heures      | 15 $        | Montage accéléré ou IA intensif    |

## 7. Architecture recommandée (pipeline TikTub)

Le schéma suivant illustre l’architecture proposée pour TikTub. La chaîne commence par une **recherche multi-source** (Youtube Data API, SerpApi, ddgs, etc.), agrège et filtre les résultats, puis vérifie la pertinence par IA et correspondances (images/audio). La vidéo sélectionnée est téléchargée (avec gestion cookies et tokens), puis traitée en post (montage/filtre/upscale). Chaque étape est automatisée, redondante et respecte les quotas/législations.

```mermaid
graph LR
    A[Sources multiples de recherche (YouTube API, Google Video, DuckDuckGo, TikTok scrap, etc.)] --> B[Fusion & Filtrage des résultats]
    B --> C[Validation IA/Matching (images, audio, contenu)]
    C --> D[Téléchargement (yt-dlp + cookies/PoToken, clients variés)]
    D --> E[Post-traitements (montage, stabilisation, Denoise, Upscale AI)]
    E --> F[Stockage final & Publication]
    style A fill:#eef,stroke:#444
    style E fill:#efe,stroke:#444
```

Cette architecture prévoit aussi des **mécanismes de secours** : si une source API est indisponible, on bascule sur une autre. L’accès sécurisé aux sessions (cookies) et tokens est géré en interne pour respecter les TOS (ex. limiter les requêtes par projet Google). 

## 8. Risques légaux et conformité

- **Copyright** : Télécharger/reposter une vidéo protégée peut violer les droits d’auteur. Prioriser les contenus **libres de droits** (CC0, CC-BY) ou dont on a l’accord. Mentionner l’auteur lors de la réutilisation (pour CC-BY). Éviter la réutilisation automatique de contenus récents sans permission.  
- **Conditions des APIs** : Les ToS (YouTube, Google, TikTok, etc.) interdisent souvent le scraping intensif ou la diffusion non autorisée. Par exemple, l’usage de YouTube Data API est soumis à quota mais gratuit; son utilisation hors de son champ (ex. user data) est interdite. Le respect des quotas et l’absence de stockage excessif sont impératifs.  
- **Limites de taux** : Respecter les limites d’appels (ex. 100 requêtes YT/jour, ou plan SerpApi). Mettre en place un système de **gestion des quotas** (back-off, file d’attente). Eviter le ban IP.  
- **Sécurité** : Protéger les cookies/sessions (ne pas exposer tokens). Utiliser la **ZeroTrace Mode** ou équivalent sur SerpApi pour minimiser les logs utilisateurs.  
- **Vie privée** : Les données recherchées (vidéos publiques) ne contiennent généralement pas de données privées, mais veiller à ne pas indexer les vidéos privées des utilisateurs.  
- **Conformité au RGPD** (si applicable) : Ne pas collecter de données personnelles. Étiqueter clairement si un contenu est protégé ou libre.  

En conclusion, l’approche TikTub proposée combine des APIs officielles (gratuites ou payantes) et des outils libres. Elle est conçue pour optimiser le coût tout en maximisant la couverture des recherches. Les tableaux ci-dessus aident à choisir la combinaison la plus rentable selon le volume de requêtes. Chaque choix technique se fait en tenant compte de la fiabilité (officielle vs scraping) et des conditions légales (respect des licences et TOS). Les sources officielles et documentations citées garantissent la fiabilité des chiffres et informations présentés. 

**Sources principales** : documentation Google/YouTube (quotas API), prix SerpApi, guides TikTok Research, guides yt-dlp (PO Token), documentation Chromaprint/AIS and perceptual hashing.