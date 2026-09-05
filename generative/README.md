# Pipeline génératif — script → voix → vidéo

Ce dossier contient le second pipeline de la chaîne `lungtemotivates` : au lieu de télécharger et re-publier des vidéos existantes (pipeline de curation historique de TikTub), il **génère des vidéos originales** "loi de l'attraction / manifestation" de A à Z :

```
script IA (Gemini)  →  voix (ElevenLabs)  →  timing réel (Whisper)  →  montage (moviepy)
```

Le résultat rejoint ensuite le pipeline existant (planning, upload YouTube, dashboard) sans aucune modification de ce côté — une vidéo générée n'est qu'une ligne de plus dans la même base, avec `status='ready_for_upload'`.

## Fichiers

| Fichier | Rôle |
|---|---|
| `script_generator.py` | Écrit un nouveau script (+ titre/description/tags) via Gemini, dans le style de la chaîne, sur un nouveau sujet à chaque fois |
| `voice_generator.py` | Génère la voix (ElevenLabs) et mesure le timing réel de chaque mot (Whisper) |
| `video_composer.py` | Assemble fond vidéo + musique + voix + sous-titres karaoké en un mp4 final |
| `pipeline.py` | Orchestration : `GenerativePipeline` relie les trois étapes ci-dessus au reste de TikTub (`url_manager`, statuts, `processed_videos/`) |

## Le problème principal : synchroniser les sous-titres sur la voix

C'est la partie qui a demandé plusieurs itérations, donc voici l'historique complet — pas seulement la solution finale, mais pourquoi les deux premières tentatives ne suffisaient pas.

### Tentative 1 — faire confiance aux timestamps d'ElevenLabs

`convert_with_timestamps` renvoie, en plus de l'audio, un alignement caractère par caractère (à quelle seconde chaque lettre du texte envoyé est prononcée). En théorie, il suffit de découper ça en mots avec leurs horaires. En pratique, deux soucis :

1. Les tags de style envoyés dans le texte (`[calm]`, `[curious]`...) et les balises de pause (`<break time="0.7s" />`) ne sont pas prononcés, mais l'API leur assigne quand même un timestamp — quasi instantané, pas la vraie durée demandée.
2. Une balise `<break time="0.7s" />` demande **une vraie pause de 0.7s dans l'audio**, mais son entrée dans l'alignement ne dure que ~0.03s. Résultat : chaque `<break>` rendait tous les mots suivants un peu plus en retard par rapport à l'audio réel — et ça s'accumulait sur toute la longueur du script (visible surtout après plusieurs `<break>`, typiquement après le 5e-6e).

### Tentative 2 — corriger l'écart des `<break>`

Pour chaque balise `<break>`, on mesure l'écart entre la durée déclarée (`0.7s`) et celle réellement comptée dans l'alignement (`~0.03s`), et on reporte cet écart en cumulé sur tous les mots suivants. Ça a nettement amélioré les choses, mais restait une **estimation** — pas une mesure. Toute autre source d'imprécision du modèle d'alignement (accumulation de petites erreurs sur les mots eux-mêmes, pas seulement sur les pauses) restait non corrigée. Le décalage devenait moins grave, mais pas nul.

### Solution finale — mesurer l'audio réel avec Whisper

Le vrai problème de fond : on faisait confiance à une **estimation** produite par ElevenLabs *pendant* la génération, jamais à une mesure du fichier audio final. C'est exactement le problème que les outils de sous-titrage professionnels (CapCut, Descript...) évitent en ne se fiant jamais aux métadonnées du moteur de synthèse — ils mesurent le son généré après coup.

La solution retenue :

1. ElevenLabs ne sert plus qu'à générer l'audio (`client.text_to_speech.convert`, sans timestamps).
2. Le fichier audio réellement produit est retranscrit **en local** avec [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (modèle `small`, CPU, gratuit) — `word_timestamps=True` donne des horaires mesurés sur le vrai son, plus aucune estimation à corriger.
3. Whisper peut mal entendre un mot de temps en temps (ex: "Raconte-moi" → "Racontement"), donc son propre texte transcrit n'est **jamais affiché**. On garde le texte du script original (celui écrit par l'IA, sans fautes) et on l'aligne mot à mot sur les timestamps de Whisper via une comparaison floue (`difflib.SequenceMatcher` sur des mots normalisés — minuscules, sans accents/ponctuation). Les rares mots du script sans correspondance claire (une liste "1." transcrite "1." ou parfois décalée) récupèrent un timing interpolé entre leurs voisins les plus proches.

Concrètement, dans `voice_generator.py` :
- `synthesize()` génère l'audio, lance Whisper dessus, puis appelle `_align_to_whisper()`.
- `_align_to_whisper()` fait le mapping texte-script ↔ timing-Whisper décrit ci-dessus.
- Un dernier garde-fou clampe tout timestamp à la durée réelle du fichier audio (un mot final sans voisin après lui pourrait sinon recevoir un timing extrapolé légèrement au-delà de la fin du fichier).

**Coût :** aucun changement — ElevenLabs facture toujours la génération de la voix comme avant (inchangé), et Whisper tourne 100% en local, gratuitement (le modèle `small` est téléchargé une fois puis mis en cache).

## Le rendu des sous-titres (style "karaoké")

Dans `video_composer.py`, une fois qu'on a les mots avec leur timing réel :

1. **Découpage en blocs** aux frontières fortes (`.` `!` `?` `:`) — pour qu'un numéro de liste ("1.", "2.") ou la fin d'une clause avant `:` n'atterrisse jamais collé au morceau de phrase suivant juste parce qu'il restait de la place sur la ligne.
2. **Découpage en lignes** par largeur réelle mesurée (pas un nombre de mots fixe), avec une marge de sécurité de chaque côté de l'écran — aucun mot ne peut plus déborder ou toucher les bords.
3. **Rendu** : chaque ligne est dessinée une fois par mot mis en avant (police DejaVu Sans Bold, contour noir, mot courant en jaune vif `#FFE000`, tous les autres en blanc) — toujours sur **une seule référence de hauteur commune à toute la ligne**, sinon les mots avec/sans accent ou hampe ("à" vs "se") ne s'alignaient pas à la même hauteur.
4. **Durée d'affichage** : chaque mot reste surligné jusqu'au début du mot suivant — y compris à travers un changement de ligne — pour qu'il n'y ait jamais de trou noir au milieu d'une phrase.

Les captions sont dessinées avec PIL (pas `TextClip` de moviepy, qui nécessite ImageMagick — non installé sur cet environnement).

## Comment tester

Depuis la racine du projet :

```python
from generative.pipeline import GenerativePipeline

p = GenerativePipeline()
batch_id = p.create_script_batch('lungtemotivates', n_scripts=1)   # écrit un script (Gemini, gratuit)
video_id = p.list_awaiting_assets('lungtemotivates')[-1]['video_id']

p.assign_assets(
    video_id,
    'channels/lungtemotivates/assets/backgrounds/<fichier>.mp4',
    'channels/lungtemotivates/assets/music/<fichier>.mp3',
)
p.render(video_id)   # seul appel qui facture ElevenLabs — sortie dans processed_videos/
```

Ou via l'interface web : onglet **"🪄 Génération"** (`webapp/static/index.html`), visible pour toute chaîne dont le `profile.json` a `"generation_mode": true`.
