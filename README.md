# K-B

**Une bibliothèque de veille tech qui se range toute seule.**

## Objectif

K-B a deux portes d'entrée :

- **La veille** : un pipeline collecte chaque semaine l'actualité tech venue de plusieurs sources,
  la range en items datés dans une base, puis répond à « quoi de neuf cette semaine ? ».
- **La base de connaissance** : je dépose à la main les documents qui comptent. Une IA les
  compile en un wiki Markdown durable, à la façon du LLM wiki d'Andrej Karpathy : les sources
  restent immuables, et le wiki relie les pages, signale les contradictions et date ce qu'il
  affirme.

Les données restent sur ma machine, et l'inférence passe par une API. Je lis dans Obsidian et
j'interroge depuis le terminal. La revue des implémentations existantes est dans
[docs/2026-09-23-veille-existant.md](docs/2026-09-23-veille-existant.md). Le constat principal :
aucune ne fait de veille datée.

## Utilisateurs

1. Moi, d'abord : un seul utilisateur.
2. Des agents (Claude Code…), qui interrogent la base par l'API REST.
3. Plus tard, les mêmes agents via un serveur MCP.

## Périmètre de la v0 — le pipeline de veille

La v0 couvre la porte « veille » :

- **Collecte**, avec un point de lancement unique, une panne isolée par source et une sauvegarde
  brute :
  - API GitHub (dépôts et sujets suivis : liste à venir) ;
  - API arXiv (sélection à venir) : métadonnées et résumé ;
  - newsletters reçues sur une adresse Gmail dédiée (analyse du corps du mail) ;
  - Markdown produit par Obsidian Web Clipper, dans un coffre Obsidian dédié (à créer) ;
  - au moins une page web sans flux ni API, lue par scraping (changelog, blog d'éditeur) ;
  - l'historique d'un profil Brave réservé à K-B (base SQLite existante) ;
  - les dépôts GitHub qui montent chaque semaine, calculés depuis GH Archive sur BigQuery.
- **Fusion** en un seul jeu d'items : dates normalisées, doublons retirés, rejets tracés, règles
  écrites.
- **Stockage** dans une base modélisée avec Merise, avec une installation qu'un tiers peut rejouer.
- **API REST authentifiée**, documentée en OpenAPI, qui sert les items et répond à « quoi de neuf
  cette semaine ».
- **Données personnelles** : un registre des traitements et une procédure de purge.

## Hors périmètre de la v0

- Le wiki compilé par l'IA (ingest, liens, contradictions, lint) : c'est la v1.
- Les livres en PDF, le texte intégral des PDF, et leurs images, tableaux et pages scannées.
- Le serveur MCP et le tableau de bord.
- Tout entraînement de modèle.

## Licence

© 2026 Sabine Laurent — sous licence [Creative Commons Attribution - Pas d'Utilisation Commerciale 4.0 International (CC BY-NC 4.0)](https://creativecommons.org/licenses/by-nc/4.0/deed.fr).

- **Réutilisation autorisée**, à condition de citer l'origine : [github.com/SabineLaurent/K-B](https://github.com/SabineLaurent/K-B).
- **Toute utilisation commerciale est interdite** sans mon accord écrit préalable.

Texte complet : voir [LICENSE](LICENSE).
