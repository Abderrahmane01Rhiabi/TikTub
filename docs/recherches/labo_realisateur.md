# Labo — réalisateur v2 (10 novembre 2026)

Question : un « guide de monteur » donné au réalisateur IA (quoi montrer selon le type de phrase,
le vrai plutôt que le générique, les entités cherchées sur leur chaîne officielle, jusqu'à 4 visuels
par phrase, le mot où chaque visuel commence) donne-t-il de meilleurs plans que le réalisateur actuel ?

Rien n'a changé dans l'app : tout est dans le script du labo et dans
`Downloads/montage_test/realisateur_v2/` (`plans.json`, `chaines.txt`).

## Banc d'essai

34 phrases :
- 4 vrais projets : Grand Stade, Nador West Med, Karian, Traînées ;
- 3 séries de pièges : foot (fr), économie (fr), darija (ar).

L'ancien et le nouveau réalisateur ont fait chacun un plan pour chaque phrase.

## Résultats

| Juge | Nouveau gagne | Ancien gagne | Pareil |
|---|---|---|---|
| Gemini Pro (à l'aveugle, grille notée) | 31 | 3 | 0 |
| L'utilisateur (à l'aveugle, page de vote) | 11 | 6 | 17 |

Le juge IA a beaucoup surestimé l'écart. Pour l'utilisateur, la moitié des phrases donnent la
même chose. Le nouveau gagne nettement là où il y a plusieurs choses à montrer :
- pièges foot et économie, et darija : 6 victoires, 0 défaite ;
- Traînées : 5 victoires, 0 défaite.

Il ne gagne rien sur les phrases simples : sur Nador, 7 phrases et 7 « pareil ».

**Leçon : ne pas se fier au seul juge IA, qui préfère les plans plus longs et plus détaillés.**

## Pourquoi l'ancien a gagné 6 fois

Les 6 défaites sont sur le Grand Stade (phrases 1, 4, 5) et sur Karian (phrases 2, 4, 5).

- **Le nouveau perd le détail précis de la phrase.**
  - Phrase : « 32 درج ضخم وحدائق معلقة » (32 escaliers géants et des jardins suspendus).
  - Ancien : les 32 escaliers et les jardins.
  - Nouveau : « façades… escaliers monumentaux », plus vague.
- **Le nouveau décrit une action rare au lieu du résultat visible.**
  - Phrase : « يضع الأعوان أرقاما حمراء » (les agents posent des numéros rouges).
  - Ancien : des portes déjà marquées de numéros rouges, qu'on trouve facilement en vidéo.
  - Nouveau : des agents en train de peindre, presque introuvable.
- Sur les autres défaites, les deux plans sont presque identiques. Les petites différences ont joué
  en faveur de l'ancien.

## Ce qu'on garde pour l'intégration

1. **Garder du nouveau :**
   - plusieurs visuels quand la phrase cite plusieurs choses (listes, comparaisons) ;
   - les entités cherchées sur leur chaîne officielle ;
   - le vrai plutôt que le générique (pièges darija : 57 → 96,5 au juge, et voté).
2. **Ajouter au guide :**
   - suivre l'ordre de la voix (dans une comparaison, la chose comparée ne vient pas en premier) ;
   - garder les détails précis de la phrase (chiffres, objets nommés) ;
   - quand une action est rare à filmer, montrer son résultat visible.
3. **Chaînes officielles :**
   - 7 des 12 noms de chaîne proposés existent ;
   - l'app vérifie chaque chaîne ; si le nom est faux, elle cherche la chaîne au nom le plus proche
     et aux abonnés les plus nombreux (bon résultat dans les 5 cas testés) ;
   - la recherche dans une chaîne se fait dans la langue de la chaîne (en français, rien trouvé
     sur FRMF).
4. **Phrase simple : un seul visuel, comme avant.** Le guide ne doit pas compliquer ce qui marchait.

## Prochaine mesure

Le vrai juge, ce sont les images qu'on trouve : un projet complet monté avec le nouveau réalisateur,
comparé au montage actuel.
