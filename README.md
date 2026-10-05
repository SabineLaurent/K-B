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
[docs/veille/2026-09-23-veille-existant.md](docs/veille/2026-09-23-veille-existant.md). Le constat principal :
aucune ne fait de veille datée.

## Utilisateurs

1. Moi, d'abord : un seul utilisateur.
2. Des agents (Claude Code…), qui interrogent la base par l'API REST.
3. Plus tard, les mêmes agents via un serveur MCP.

## Périmètre de la v0 — le pipeline de veille

La v0 couvre la porte « veille » :

- **Collecte**, avec un point de lancement unique, une panne isolée par source et une sauvegarde
  brute :
  - API GitHub : releases des dépôts suivis, alertes de sécurité, dépôts les plus étoilés ;
  - API arXiv : papiers sur la sécurité de l'IA, métadonnées et résumé ;
  - catalogue CISA des vulnérabilités activement exploitées (fichier CSV) ;
  - Markdown produit par Obsidian Web Clipper, dans un coffre Obsidian dédié (à créer) ;
  - newsletters tldr.tech, lues par scraping ;
  - mes papiers lus dans Zotero et leurs surlignages (base SQLite) ;
  - les dépôts GitHub qui montent sur 3 jours, calculés depuis GH Archive sur BigQuery.

  Les sources suivies sont dans [docs/sources.md](docs/sources.md), leur accès et leurs limites
  dans [docs/specs-collecte.md](docs/specs-collecte.md).
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

## Installer et lancer

**Prérequis** : Python 3.13 ou plus récent (`requires-python` du `pyproject.toml`) et
[uv](https://docs.astral.sh/uv/).

**Installer** :

```sh
git clone https://github.com/SabineLaurent/K-B.git
cd K-B
uv sync
```

**Variables d'environnement** :

| Variable | Obligatoire | Rôle |
|---|---|---|
| `KB_DATA_DIR` | oui | dossier des données, hors du dépôt ; il doit exister. La collecte écrit dans `<KB_DATA_DIR>/raw/`. |
| `KB_GITHUB_TOKEN` | non | jeton GitHub en lecture seule ([docs/jeton-github.md](docs/jeton-github.md)). Sans lui, l'API GitHub accepte 60 requêtes par heure au lieu de 5 000. |

**Lancer une collecte** (une par jour, voir [docs/specs-collecte.md](docs/specs-collecte.md)) :

```sh
mkdir -p ~/K-B-data
KB_DATA_DIR=~/K-B-data uv run kb collect
```

Avec le jeton rangé dans le `.env` à la racine du dépôt, ignoré par git :
`KB_DATA_DIR=~/K-B-data uv run --env-file .env kb collect`.

`kb collect` affiche une ligne par source (`ok` ou `failed`, avec le type de l'erreur). Code de
sortie : 0 si toutes les sources ont réussi, 1 si au moins une a échoué, 2 si `KB_DATA_DIR`
manque, n'est pas un dossier existant, ou si l'état de collecte est illisible.

**Lancer les tests** :

```sh
uv run pytest
```

## Licence

© 2026 Sabine Laurent — sous licence [Creative Commons Attribution - Pas d'Utilisation Commerciale 4.0 International (CC BY-NC 4.0)](https://creativecommons.org/licenses/by-nc/4.0/deed.fr).

- **Réutilisation autorisée**, à condition de citer l'origine : [github.com/SabineLaurent/K-B](https://github.com/SabineLaurent/K-B).
- **Toute utilisation commerciale est interdite** sans mon accord écrit préalable.

Texte complet : voir [LICENSE](LICENSE).
