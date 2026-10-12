# K-B

**Une bibliothèque de veille tech qui se range toute seule.**

## Objectif

K-B a deux portes d'entrée :

- **La veille** : un pipeline collecte chaque jour l'actualité tech venue de plusieurs sources (une
  collecte manquée est rattrapée à la suivante), la range en items datés dans une base, puis
  répond à « quoi de neuf cette semaine ? ».
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

- Le wiki compilé par l'IA : c'est la v1.
- Les livres en PDF, le texte intégral des PDF, et leurs images, tableaux et pages scannées.
- Le serveur MCP et le tableau de bord.
- Tout entraînement de modèle.

## Périmètre de la v1 — le wiki

La v1 ouvre la porte « base de connaissance », pour les papiers que je garde dans Zotero :

- **Ingest** : de chaque papier, le modèle écrit une note de lecture, comme après une lecture de
  l'article entier, à partir du texte intégral de son PDF. Il renvoie des opérations JSON ; le
  code les valide (liste fermée d'opérations, citations, nombres et dates retrouvés mot pour mot
  dans la source, liens et frontmatter), puis écrit dans le wiki si tout passe. Sinon, la
  proposition attend dans une file « à voir ».
- **API IA authentifiée**, distincte de l'API de données et documentée en OpenAPI. La commande
  `kb` en est le client. L'inférence passe par Azure, en API compatible OpenAI : le modèle se
  choisit en configuration.
- **Métriques** de chaque appel (durée, jetons, coût, erreurs, fidélité, propositions
  acceptées), émises en OpenTelemetry, gardées sur ma machine et restituées en temps réel, avec
  une alerte sur seuil, par un outil à choisir.

## Hors périmètre de la v1

- Les contradictions signalées entre pages, l'interrogation du wiki, le lint par l'IA.
- Les clips Obsidian et mes notes comme entrées du wiki.
- Les images, tableaux et pages scannées des PDF ; les livres.
- Le serveur MCP et tout entraînement de modèle.

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
| `KB_DATA_DIR` | oui | dossier des données, hors du dépôt ; il doit exister. La collecte écrit le brut dans `<KB_DATA_DIR>/raw/` et son état dans `<KB_DATA_DIR>/collection_state.json`. |
| `KB_ZOTERO_DIR` | non | dossier de données de Zotero, celui qui contient `zotero.sqlite`, en chemin complet (un `~` écrit dans `.env` n'est pas développé). Sans elle, `kb collect` saute Zotero et l'affiche (`zotero: skipped (KB_ZOTERO_DIR not set)`). Avec elle, les papiers et leurs surlignages sont extraits dans `<KB_DATA_DIR>/raw/selected_library/zotero/`, sans que K-B ouvre la base de Zotero : il en lit une copie temporaire. |
| `KB_GITHUB_TOKEN` | non | jeton GitHub en lecture seule ([docs/jeton-github.md](docs/jeton-github.md)). Sans lui, l'API GitHub accepte 60 requêtes par heure au lieu de 5 000. |

**Créer la base** (une fois) :

```sh
mkdir -p ~/K-B-data
KB_DATA_DIR=~/K-B-data uv run kb create-db
```

`kb create-db` crée `<KB_DATA_DIR>/k-b.sqlite` : les tables, les 7 sources, le mode WAL. Code de
sortie :

- 0 : la base est créée ;
- 1 : la création a échoué (dossier en lecture seule, disque plein…). Le message dit l'erreur, et
  aucun fichier de base ne reste ;
- 2 : `KB_DATA_DIR` manque ou n'est pas un dossier existant, ou la base existe déjà. Une base
  existante n'est pas touchée : pour repartir de zéro, supprimer le fichier.

**Lancer une collecte** (une par jour, voir [docs/specs-collecte.md](docs/specs-collecte.md)) :

```sh
KB_DATA_DIR=~/K-B-data uv run kb collect
```

Avec le jeton rangé dans le `.env` à la racine du dépôt, ignoré par git :
`KB_DATA_DIR=~/K-B-data uv run --env-file .env kb collect`.

`kb collect` affiche une ligne par source (`ok` ou `failed`, avec le type de l'erreur ; `skipped`
pour Zotero sans `KB_ZOTERO_DIR`). Code de
sortie : 0 si tout a réussi, 1 si au moins une source a échoué ou si l'état de collecte n'a pas
pu être écrit, 2 si `KB_DATA_DIR` manque, n'est pas un dossier existant, ou si l'état de collecte
est illisible.

**Importer le brut dans la base** (après une collecte) :

```sh
KB_DATA_DIR=~/K-B-data uv run kb import
```

`kb import` lit `<KB_DATA_DIR>/raw/automated_watch/`, fusionne les items et les écrit dans la base ; rejoué
sur le même brut, il donne la même base. Il affiche le nombre d'items importés, de doublons
retirés et de rejets, détaillés dans `<KB_DATA_DIR>/import-log.jsonl`. Code de sortie :

- 0 : l'import a réussi ;
- 1 : l'import a échoué. Une erreur dans la base n'y écrit rien. Le journal est écrit après la
  base : s'il ne peut pas l'être, la base garde l'import et le journal précédent reste entier ;
- 2 : `KB_DATA_DIR` manque, ou la base n'existe pas (`kb create-db`).

**Lancer les tests** :

```sh
uv run pytest
```

## Licence

© 2026 Sabine Laurent — sous licence [Creative Commons Attribution - Pas d'Utilisation Commerciale 4.0 International (CC BY-NC 4.0)](https://creativecommons.org/licenses/by-nc/4.0/deed.fr).

- **Réutilisation autorisée**, à condition de citer l'origine : [github.com/SabineLaurent/K-B](https://github.com/SabineLaurent/K-B).
- **Toute utilisation commerciale est interdite** sans mon accord écrit préalable.

Texte complet : voir [LICENSE](LICENSE).
