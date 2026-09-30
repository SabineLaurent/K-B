# Journal de décisions — K-B

Produit, architecture, conception : ce qui a été décidé, pourquoi, et les options écartées. La
méthode de travail n'y entre pas : elle vit dans les règles du dépôt.

## 2026-09-30

### Collecte

- **Le brut de chaque source est stocké complet et intact ; le filtre se fait à la lecture.**
  Chaque collecte écrit dans `raw/automation/<source>/` ce que la source a publié, sans le
  filtrer ni le modifier. La sélection des nouveautés (pour CISA KEV : `dateAdded` depuis la
  dernière collecte) se fait quand on lit ce brut, jamais quand on l'écrit. Pourquoi : pouvoir
  rejouer le traitement sur le brut. Cela prolonge l'immuabilité de `raw/`, retenue lors de la
  revue de l'existant. Option écartée : filtrer à l'écriture. Le brut serait plus petit, mais on
  ne pourrait plus rejouer le traitement ; et si le filtre est faux, ce qu'il écarte est perdu.
  Pour CISA KEV, le catalogue est cumulatif : on perdrait surtout son état à la date de la
  collecte (les lignes modifiées ou retirées depuis). Pour une source non cumulative
  (événements GitHub, TLDR), la perte serait définitive. Limite assumée :
  chaque collecte où le catalogue a changé stocke le catalogue entier (environ 1 Mo en 2026).
  Une collecte sans changement n'écrit rien (réponse HTTP 304). — PR de #23

## Décisions encore ouvertes

_Aucune pour l'instant._
