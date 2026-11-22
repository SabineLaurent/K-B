# K-B

**Une bibliothèque de veille tech qui se range toute seule.**

K-B collecte chaque jour l'actualité tech de sept sources, la range en items datés dans une base, et fait écrire par
un modèle de langage des comptes rendus de veille par sujet et un compte rendu des tendances. Chaque compte rendu de veille
cite ses items, et chacun devient une fiche Markdown datée dans un coffre Obsidian. Une API de données sert la veille, et un site
privé la montre.

Le produit, son périmètre et ses moyens sont décrits dans [Le produit](documentation/produit.md).

## Fonctionnalités

- **Collecte** de sept sources : l'API GitHub (releases des dépôts suivis, alertes de sécurité, dépôts les plus
  étoilés et les plus forkés), l'API arXiv, le catalogue CISA KEV, les newsletters tldr.tech, les clips d'Obsidian
  Web Clipper, une bibliothèque Zotero et GH Archive sur BigQuery. Le brut est gardé tel quel.
- **Import** du brut dans une base, SQLite en local et PostgreSQL en ligne, qui écarte les doublons ; chaque entrée
  refusée est écrite au journal de l'import.
- **API de données**, REST, authentifiée par clé et documentée en OpenAPI : les items, leur détail, les tendances,
  et en ligne les fiches des tops et des comptes rendus.
- **API IA**, authentifiée par clé et documentée en OpenAPI : les comptes rendus de veille par sujet
  (`POST /digests`) et le compte rendu des tendances (`POST /trend-reports`). Le code revalide chaque sortie du
  modèle (schéma fermé, sujets d'une liste fermée, items cités parmi ceux envoyés, ni lien ni balise) avant de
  l'écrire.
- **Fiches dans le coffre** : `kb digest` et `kb trend-report` écrivent les comptes rendus, `kb write-tops` une fiche
  par jour pour les 100 dépôts les plus étoilés et les plus forkés, sans modèle.
- **Site** servi par `kb serve-web`, sans JavaScript : le fil des items, leur détail et les tendances.
- **Monitorage** du modèle : mesures et traces en OpenTelemetry vers Grafana Cloud ; le tableau de bord et les
  alertes sont versionnés dans `observability/grafana/`.
- **Données personnelles** : un [registre des traitements](docs/registre-traitements.md) et leur purge, `kb purge`.

## Architecture

Le code est en Python, dans `src/k_b/`, en couches : les commandes `kb` (`cli.py`, `commands/`), l'ETL (`etl/`),
l'accès à la base (`database/`), puis l'API de données (`data_api/`), l'API IA (`ai_api/`) et le site (`web/`). Les
deux parcours de l'ETL, la collecte et l'import, communiquent par les fichiers bruts.

K-B tourne en local, sur un poste de travail, sans conteneur, et en ligne, sur Azure Container Apps : une même image
sert les trois applications (les deux API et le site) et les jobs (la routine de chaque jour, les comptes rendus, le
test de fumée, la création de la base). L'infrastructure est décrite en Bicep, dans `infra/`. Le détail est dans
[la fiche de l'architecture](documentation/architecture.md).

## Installation

### Prérequis

- Python 3.13 ou plus récent (`requires-python` du `pyproject.toml`) ;
- [uv](https://docs.astral.sh/uv/), qui installe les dépendances et lance les commandes.

### En local

```sh
git clone https://github.com/SabineLaurent/K-B.git
cd K-B
uv sync
uv run kb --help
cp .env.example .env
```

`.env.example` nomme et décrit chaque variable, sans valeur réelle : `.env` se remplit d'après lui, et git l'ignore.
`KB_DATA_DIR` y nomme le dossier des données, hors du dépôt, qui doit exister. Puis la base se crée, une fois :

```sh
uv run --env-file .env kb create-db
```

Sans `KB_DATABASE_URL`, la base est le fichier SQLite `<KB_DATA_DIR>/k-b.sqlite`. Le détail est dans [la fiche de l'installation](documentation/installation.md)
et, pour la base, dans [la fiche des données](documentation/donnees.md).

### En ligne

K-B se déploie sur Azure depuis `infra/main.bicep`, appliqué en deux passes
([infra/README.md](infra/README.md), « Appliquer »). Ensuite, un tag `vX.Y.Z` posé sur `main` met la version en
ligne, une fois la CI de son commit finie et verte ([la fiche de la livraison
continue](documentation/livraison-continue.md)).

## Utilisation

Chaque commande se lance par `uv run --env-file .env kb <commande>` ; `uv run kb --help` les liste, avec leurs codes
de sortie.

| Commande | Ce qu'elle fait |
|---|---|
| `kb create-db` | crée la base : le fichier SQLite, ou les tables de la base PostgreSQL de `KB_DATABASE_URL` |
| `kb migrate-database` | crée la base qui n'a pas ses tables, et laisse telle quelle celle qui les a ; sur PostgreSQL, donne aussi ses tables aux rôles de la base en ligne |
| `kb collect` | lance chaque source, ou celles de `KB_COLLECT_ONLY`, et garde son brut dans `<KB_DATA_DIR>/raw/` |
| `kb import` | lit le brut pas encore importé et écrit ses items dans la base, qui écarte les doublons |
| `kb purge` | supprime de la base, du brut, des journaux et des logs ce qui a passé sa durée de conservation |
| `kb write-tops` | écrit dans le coffre la fiche de chaque classement, puis supprime les relevés qu'elle remplace |
| `kb serve-data` | sert l'API de données, en lecture seule, sur `http://127.0.0.1:8000` par défaut |
| `kb serve-ai` | sert l'API IA, sur `http://127.0.0.1:8001` par défaut |
| `kb serve-web` | sert le site, sur `http://127.0.0.1:8002` par défaut |
| `kb digest` | demande à l'API IA les comptes rendus de veille, puis écrit la fiche de chaque sujet dans le coffre |
| `kb trend-report` | demande à l'API IA le compte rendu des tendances, puis l'écrit dans le coffre |
| `kb download-watch-sheets` | copie dans `veille/` du coffre local chaque fiche publiée en ligne qui lui manque |
| `kb daily-routine` | la commande du job de chaque jour : les clips, `kb collect`, `kb import`, `kb purge`, `kb write-tops`, puis la publication des fiches |
| `kb digest-watch` | la commande du job des comptes rendus : `kb digest`, `kb trend-report`, puis la publication des fiches |
| `kb smoke-test` | la commande du job du test de fumée : vérifie que les deux API et le stockage d'échange répondent |
| `kb openapi` | réécrit l'OpenAPI des deux API dans `docs/api/` |

Chaque client d'une API a sa clé, dans `KB_DATA_API_KEY_<CLIENT>` pour l'API de données et dans
`KB_AI_API_KEY_<CLIENT>` pour l'API IA ; l'API IA lit la veille par l'API de données, qui doit tourner. Leurs contrats
sont versionnés dans `docs/api/openapi-donnees.json` et `docs/api/openapi-ia.json`. Les commandes, leurs réglages, leur
sortie et leurs codes sont décrits dans [Utiliser K-B](documentation/utilisation.md).

## Lancer les tests

```sh
uv run pytest
uv run pytest --cov --cov-report=term-missing
```

La première commande lance la suite sans les tests marqués `postgresql` et `e2e`, qui ne tournent que si `-m` les
nomme. La seconde y ajoute la couverture des lignes et des branches de `src/k_b/`, et échoue sous le seuil du
`pyproject.toml`. Le lint, le format et le typage : `uv run ruff check`, `uv run ruff format --check` et
`uv run mypy --strict`. Le détail est dans [la fiche des tests](documentation/tests.md), et la CI, qui les
lance sur chaque demande de fusion vers `main`, dans [la fiche de l'intégration
continue](documentation/integration-continue.md).

## Documentation

- `documentation/` : la documentation du produit, construite en site par MkDocs
  (`uv run --only-group docs mkdocs serve`), de l'installation à la livraison ;
- `docs/` : les spécifications (collecte, stockage, API, fiches de veille), le registre des traitements et les
  contrats OpenAPI des deux API, dans `docs/api/` ;
- [le journal des décisions](docs/ADR/journal-decisions-projet.md) : chaque décision, son pourquoi et les options
  écartées ;
- [infra/README.md](infra/README.md) : l'infrastructure en ligne, son application et son exploitation.

## Licence

© 2026 Sabine Laurent — sous licence [Creative Commons Attribution - Pas d'Utilisation Commerciale 4.0 International (CC BY-NC 4.0)](https://creativecommons.org/licenses/by-nc/4.0/deed.fr).

- **Réutilisation autorisée**, à condition de citer l'origine : [github.com/SabineLaurent/K-B](https://github.com/SabineLaurent/K-B).
- **Toute utilisation commerciale est interdite** sans mon accord écrit préalable.

Texte complet : voir [LICENSE](LICENSE).

## Contenus de tiers

La licence ci-dessus couvre ce que j'ai écrit. Quelques fichiers de test reprennent des extraits d'autrui, sous
leur propre licence (lues à la source le 2026-11-06) :

| Fichier | Source | Licence |
|---|---|---|
| `tests/fixtures/clipping/page_with_a_rule_in_its_text.md` | [WCAG 2.2](https://www.w3.org/TR/WCAG22/), Copyright © 2020-2024 World Wide Web Consortium | [W3C Document License](https://www.w3.org/copyright/document-license/) |
| `tests/fixtures/clipping/page_without_author_or_date.md` | une page du site de l'[OWASP](https://owasp.org/) | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/deed.fr) |
| `tests/fixtures/github_advisories_extract.json` | [GitHub Advisory Database](https://github.com/github/advisory-database) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.fr) |
| `tests/fixtures/arxiv_extract.xml` | métadonnées de l'API arXiv ([conditions](https://info.arxiv.org/help/api/tou.html)) | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/deed.fr) |
| `tests/fixtures/cisa_kev_extract.csv` | catalogue KEV de la CISA ([`cisagov/kev-data`](https://github.com/cisagov/kev-data)) | CC0 1.0 |
| `tests/fixtures/digests_reference.json` | les réponses d'un modèle réel à `POST /digests` (#479) sur les items des deux fichiers ci-dessus, dont elles citent des passages | passages cités : CC0 1.0 ; texte du modèle et métadonnées du fournisseur : licence non établie |
| `tests/fixtures/zotero_extract.sql` | 15 tables du schéma de Zotero (`resource/schema/userdata.sql` du dépôt [`zotero/zotero`](https://github.com/zotero/zotero)), © 2009 Center for History and New Media, George Mason University ; les valeurs sont inventées | [AGPL v3 ou plus](https://www.gnu.org/licenses/agpl-3.0.html) |
| `tests/fixtures/github_*_extract.json`, `tests/fixtures/gh_archive_extract.json` | métadonnées publiques de dépôts GitHub (noms, descriptions, notes de version), par l'API de GitHub et GH Archive | celle de chaque dépôt ; de courts extraits, gardés pour les tests |

## Crédits

Les papiers viennent de l'API arXiv, qui demande cette mention à chacun de ses utilisateurs
([arXiv API Access](https://info.arxiv.org/help/api/index.html), consulté le 2026-10-25) :

> Thank you to arXiv for use of its open access interoperability.

L'API de données la donne aussi, dans la description de son OpenAPI (`docs/api/openapi-donnees.json`, et `/docs` en `sandbox`).
