# Requêtes d'extraction

Ce que K-B demande à chaque source, et pourquoi : les deux requêtes SQL d'extraction (Zotero,
GH Archive sur BigQuery), puis les paramètres des requêtes faites aux API. Pour chaque requête :
les tables et les colonnes lues, les filtres, les jointures, le regroupement, et ce qui la rend
économe.

**Règle du document** : il cite. Aucune requête n'y est recopiée : le SQL vit dans le code, sous le
nom de sa constante, et seules des clauses courtes (un filtre, un nom de colonne) sont citées en
ligne pour le décrire. Les mesures, les plafonds et les valeurs de réglage vivent dans le code et
dans [specs-collecte.md](specs-collecte.md) ou [bigquery.md](bigquery.md), où ce document renvoie.
Une référence au code donne le fichier et le nom de la constante, de la fonction ou de la méthode,
jamais un numéro de ligne. Seule la mesure de la section 2 est écrite ici, parce qu'elle n'existe
nulle part ailleurs.

**Hors de ce document** : le SQL de la base K-B (aujourd'hui dans `src/k_b/import_items.py` ; la
règle 5 de `.claude/rules/conventions.md` le range sous `src/k_b/database/`) ;
la panne des tables GH Archive constatée depuis le 2026-10-06
([bigquery.md](bigquery.md#anomalie-constatée--les-tables-de-gh-archive-incomplètes-depuis-le-2026-10-06)).

**Où vivent ces requêtes** : chacune dans le module de sa source, `src/k_b/sources/<source>.py`.
Une requête qui lit une source externe, en lecture seule, n'est pas du SQL de la base K-B : elle
reste avec sa source (règle 5 de `.claude/rules/conventions.md`, « Couche d'accès aux données »).

## 1. Zotero — `EXTRACTION_QUERY`

Fichier : `src/k_b/sources/zotero.py`. Spécifications de la source :
[specs-collecte.md](specs-collecte.md#zotero--base-de-données).

### Où elle tourne

`ZoteroSource.fetch` retire d'abord les copies qu'un processus tué aurait laissées
(`remove_left_copies`). Il s'arrête là, sans copie ni requête, si ni la base ni son journal
d'écriture n'ont été modifiés depuis la dernière collecte (`was_modified_since`). Sinon, il copie
la base (`copy_library`) dans un dossier temporaire, puis `extract_documents` ouvre la copie en
lecture seule (`mode=ro`), la vérifie (`check_integrity`), et lance `EXTRACTION_QUERY`. La base de
Zotero elle-même n'est jamais ouverte par SQLite.

### Tables et colonnes lues

| Table | Colonnes lues | Rôle |
|---|---|---|
| `items` | `itemID`, `key`, `itemTypeID`, `libraryID`, `dateAdded` | le document ; sous l'alias `attachment`, la clé d'un PDF ; sous l'alias `annotation`, la clé et la date d'un surlignage |
| `itemTypes` | `itemTypeID`, `typeName` | le type du document |
| `libraries` | `libraryID`, `type` | la bibliothèque (personnelle ou de groupe) |
| `deletedItems` | `itemID` | la corbeille |
| `itemData` | `itemID`, `fieldID`, `valueID` | le lien entre un document, un champ et une valeur |
| `fields` | `fieldID`, `fieldName` | le nom du champ |
| `itemDataValues` | `valueID`, `value` | la valeur du champ |
| `itemCreators` | `itemID`, `creatorID`, `creatorTypeID`, `orderIndex` | les créateurs d'un document, dans leur ordre |
| `creators` | `creatorID`, `firstName`, `lastName` | le nom d'un créateur |
| `creatorTypes` | `creatorTypeID`, `creatorType` | son rôle (auteur, éditeur…) |
| `itemTags` | `itemID`, `tagID`, `type` | les étiquettes d'un document, et leur type |
| `tags` | `tagID`, `name` | le nom d'une étiquette |
| `itemAttachments` | `itemID`, `parentItemID`, `contentType`, `path` | les fichiers d'un document |
| `itemAnnotations` | `itemID`, `parentItemID`, `type`, `text`, `comment`, `pageLabel`, `sortIndex` | les annotations d'un PDF |

### Colonnes rendues

`key`, `item_type`, `title`, `date`, `date_added`, `url`, `archive_id`, et quatre listes en JSON,
nommées par `JSON_COLUMNS` : `authors`, `tags`, `pdfs`, `highlights`.

### Filtres

Tous écrits dans le SQL :
- **bibliothèque personnelle** : `libraries.type = 'user'` ; les bibliothèques de groupe ne sont
  pas lues ;
- **un document, pas une pièce** : `typeName NOT IN ('attachment', 'note', 'annotation')` ;
- **hors corbeille** : `NOT IN (SELECT itemID FROM deletedItems)`, appliqué au document, au PDF
  et au surlignage ;
- **les seuls champs utiles** : `fieldName IN ('title', 'date', 'url', 'archiveID')`, les autres
  champs de Zotero ne sont pas lus ;
- **les auteurs** : `creatorType = 'author'` ;
- **les PDF rangés par Zotero** : `contentType = 'application/pdf'` et `path LIKE 'storage:%'` ;
  un fichier lié ailleurs sur le disque n'est pas lu ;
- **les surlignages** : `itemAnnotations.type = 1`.

Ce qui n'est pas lu : [specs-collecte.md](specs-collecte.md#zotero--base-de-données).

### Jointures

- **La CTE `document`** joint `items`, `itemTypes` et `libraries` : elle définit une fois ce
  qu'est un document, et chaque liste s'y rattache.
- **La CTE `field_value`** joint `itemData`, `fields` et `itemDataValues`. Zotero ne range pas le
  titre ou l'URL dans des colonnes de `items`, mais en lignes, une par champ rempli (modèle
  entité-attribut-valeur) : la jointure retrouve le nom du champ et sa valeur, puis une
  sous-requête par champ en fait une colonne du résultat.
- **Auteurs** : `itemCreators` × `creators` × `creatorTypes`. **Étiquettes** : `itemTags` × `tags`.
- **PDF et surlignages** : `itemAttachments` × `items` (alias `attachment`, pour la clé du PDF),
  puis `itemAnnotations` × `items` (alias `annotation`, pour la clé et la date du surlignage).

### Regroupement

Pas de `GROUP BY` : chaque liste est une sous-requête corrélée au document, qui agrège ses lignes
par `json_group_array(json_object(...) ORDER BY ...)`. Un document sans ligne reçoit `[]`.
L'ordre de chaque liste est fixé dans l'agrégat :
- auteurs : `itemCreators.orderIndex`, l'ordre de Zotero ;
- étiquettes : `tags.name` ;
- PDF : `attachment.itemID` ;
- surlignages : `attachment.itemID`, puis `itemAnnotations.sortIndex` (la position dans le PDF),
  puis `annotation.itemID`.

Le résultat est trié par `document.dateAdded`, puis `document.itemID` : la même bibliothèque
donne le même extrait.

SQLite construit chaque liste en texte JSON ; `extract_documents` relit ce texte (`json.loads`
sur les colonnes de `JSON_COLUMNS`), et `ZoteroSource.fetch` rend l'extrait entier en JSON
(`json.dumps`) ; l'écriture au brut est faite par la collecte (`write_new_raw_file`,
`src/k_b/collect.py`).

### Ce qui la rend économe

- **Une instruction pour toute la bibliothèque**, au lieu d'une requête par document lancée depuis
  Python : la définition d'un document n'est écrite qu'une fois, et SQLite fait les jointures.
- **Seuls les champs utiles sont nommés**, et tous les filtres sont dans le SQL : rien n'est lu
  pour être jeté ensuite en Python.
- **Une copie, lue seule** : la requête ne prend aucun verrou sur la base de Zotero.
- **Rien quand rien n'a changé** : sans modification des fichiers de la bibliothèque depuis la
  dernière collecte, il n'y a ni copie ni requête (`was_modified_since`, dans
  `ZoteroSource.fetch`).

Cette économie n'est **pas mesurée** : ni plan d'exécution, ni temps.

### Ce qu'elle suppose

- Une version minimale de SQLite pour `ORDER BY` à l'intérieur d'un agrégat : elle est donnée par
  la docstring de `ZoteroQueryFailedError`.
- Le schéma de Zotero : s'il change, la requête échoue (`ZoteroQueryFailedError`). Le message
  nomme la table ou la colonne absente, ou la syntaxe refusée (`MESSAGE_ABOUT_THE_QUERY`) ; sinon,
  il donne le type de l'erreur et le nom que SQLite lui donne (`describe_query_error`).

## 2. GH Archive sur BigQuery — `TRENDS_QUERY`

Fichier : `src/k_b/sources/gh_archive.py`. Spécifications de la source :
[specs-collecte.md](specs-collecte.md#gh-archive-sur-bigquery--big-data) ; bac à sable, plafond
et mesures : [bigquery.md](bigquery.md#le-plafond-de-la-collecte).

### Où elle tourne

`GhArchiveSource.fetch` calcule les fenêtres dues (`list_window_ends`), vérifie que la table de la
veille est close (`check_day_table_closed`, par les métadonnées de la table, `get_table`, sans
requête), fait le `dry_run` (`drop_windows_over_the_cap`), puis lance la requête. Les paramètres
sont posés par `configure_query`.

### Table et colonnes lues

- **Table** : `githubarchive.day.20*`, une table par jour, désignée par un joker. La table est
  écrite dans le texte de la requête, car BigQuery n'accepte pas une table en paramètre ; un test
  la tient égale à `TABLE_PREFIX` (`tests/sources/test_gh_archive.py`).
- **Colonnes lues** : `repo.id`, `repo.name`, `type`, `created_at`, et la pseudo-colonne
  `_TABLE_SUFFIX` (la fin du nom de la table, qui donne le jour). Jamais `actor` (le login de qui
  a mis l'étoile), `payload` ni `org`.

### Filtres

Dans la CTE `events` :
- **les jours voulus** : `_TABLE_SUFFIX BETWEEN @first_suffix AND @last_suffix` ;
- **les étoiles et les forks** : `type IN ('WatchEvent', 'ForkEvent')` ;
- **un dépôt identifié** : `repo.id IS NOT NULL` et `repo.name IS NOT NULL`.

### Jointure

`UNNEST(@window_ends)` fait une ligne par fin de fenêtre ; chaque événement y est joint quand son
jour tombe dans la fenêtre, c'est-à-dire entre la fin de fenêtre moins `@window_days` jours, plus
un, et la fin de fenêtre. Un événement compte ainsi dans chaque fenêtre qui couvre son jour, et un
rattrapage de plusieurs fenêtres lit chaque jour une fois.

### Regroupement

- La CTE `counts` regroupe par `window_end, repository_id` : `COUNTIF` compte les étoiles et les
  forks ; le dernier nom vu du dépôt est pris par `ARRAY_AGG`, trié par date d'événement
  décroissante, puis par nom décroissant.
- La CTE `ranked` classe les dépôts de chaque fenêtre deux fois, par `ROW_NUMBER()` : par étoiles,
  puis par forks, départagés par `repository_id`.
- La requête garde les dépôts dont l'un des deux rangs ne dépasse pas `@top_size`, triés par
  `window_end`, puis `stars_gained` décroissant, puis `repository_id` : les mêmes tables donnent
  le même résultat.

### Paramètres

Posés par `configure_query`, jamais collés dans le texte :
- `@first_suffix`, `@last_suffix` : premier et dernier jour lus, au format `TABLE_SUFFIX_FORMAT` ;
- `@window_ends` : les fins de fenêtre ;
- `@window_days` : `WINDOW_DAYS` ;
- `@top_size` : `TOP_SIZE`.

Les jours et les fenêtres changent d'une collecte à l'autre. `@window_days` et `@top_size` ne
changent pas : ils sont des paramètres pour que `WINDOW_DAYS` et `TOP_SIZE` ne soient écrits qu'à un
endroit (un test de `tests/sources/test_gh_archive.py` vérifie que la taille du classement n'est
pas dans le texte de la requête). Restent écrits dans le texte : la table, les types d'événement,
et ce qui reconstruit le jour à partir du nom de la table (le préfixe du siècle, le format de
date).

### Ce qui la rend économe

- **Stockage par colonnes** : BigQuery ne lit que les colonnes nommées par la requête, pas la
  ligne entière.
- **Élagage par suffixe** : le filtre sur `_TABLE_SUFFIX` fait que BigQuery n'ouvre que les tables
  des jours voulus.
- **Une requête pour toutes les fenêtres dues** : chaque jour est lu une fois, même quand
  plusieurs fenêtres le couvrent.
- **`dry_run` d'abord** : `drop_windows_over_the_cap` demande le volume sans rien lire. Au-delà
  du plafond, la source retire les fenêtres les plus anciennes quand la borne s'applique, ou
  échoue sans rien exécuter (`DryRunOverLimitError`). Si le `dry_run` ne rend aucun volume, elle
  échoue aussi sans rien exécuter (`DryRunVolumeUnknownError`).
- **Puis l'exécution plafonnée** : `maximum_bytes_billed` vaut `compute_bytes_cap`
  (`MAX_BYTES_PER_WINDOW` par fenêtre, `MAX_BYTES_BILLED` au plus), et `job_timeout_ms` arrête le
  job chez BigQuery (`QUERY_TIMEOUT_SECONDS`).
- **Un rattrapage borné** : `MAX_CATCH_UP_WINDOWS` fenêtres au plus.
- **Le bac à sable** : sans facturation, un dépassement du quota est refusé, jamais facturé.

Les chiffres (volume par fenêtre et par rattrapage, calcul des bornes) sont dans
[bigquery.md](bigquery.md#mesures-du-2026-10-11) et
[bigquery.md](bigquery.md#le-calcul-des-bornes). Une requête sur des tables à joker n'est pas mise
en cache : [specs-collecte.md](specs-collecte.md#gh-archive-sur-bigquery--big-data).

### Mesure : les colonnes lues contre toutes les colonnes

[bigquery.md](bigquery.md#mesures-du-2026-10-11) compare déjà le poids d'une journée entière
(métadonnées de la table) au volume lu par la requête sur trois jours. La mesure ci-dessous compare
à conditions égales : **mêmes tables, même filtre**, `TRENDS_QUERY` contre la même sélection de
toutes les colonnes. Deux `dry_run` : rien n'est lu, aucun quota n'est consommé.

- **Fenêtre** : celle qui finit le 2026-09-25 (tables du 23, 24 et 25/09). Elle n'est pas mesurée
  seule dans `bigquery.md`, et elle précède la panne des tables du 2026-10-06.
- **Requête de comparaison** : `SELECT *`, suivi du `FROM` et du `WHERE` de la CTE `events`,
  découpés dans le texte de `TRENDS_QUERY` par le script (le filtre n'est pas recopié à la main),
  avec ses deux seuls paramètres, `first_suffix` et `last_suffix`.
- **Date** : 2026-10-11, 17:26 UTC.

Commande, depuis la racine du dépôt : `uv run --env-file .env python -I <script>`, avec ce script
(gardé hors du dépôt) :

```python
"""Two dry runs (issue #17): TRENDS_QUERY, then SELECT * with the same FROM and WHERE."""

from datetime import date

from google.cloud import bigquery

from k_b.sources import gh_archive as g

WINDOW_END = date(2026, 9, 25)

events = g.TRENDS_QUERY.split("WITH events AS (", 1)[1].split("),\ncounts AS (", 1)[0]
ALL_COLUMNS_QUERY = "SELECT *\n" + events[events.index("  FROM ") :]
assert "counts" not in ALL_COLUMNS_QUERY and "UNNEST" not in ALL_COLUMNS_QUERY

trends_config = g.configure_query([WINDOW_END], dry_run=True)
all_columns_config = bigquery.QueryJobConfig(
    dry_run=True,
    use_query_cache=False,
    query_parameters=[
        parameter
        for parameter in trends_config.query_parameters
        if parameter.name in ("first_suffix", "last_suffix")
    ],
)
assert trends_config.dry_run is True and all_columns_config.dry_run is True

client = g.create_bigquery_client()
for label, query, config in (
    ("trends_query", g.TRENDS_QUERY, trends_config),
    ("all_columns", ALL_COLUMNS_QUERY, all_columns_config),
):
    job = client.query(query, job_config=config, timeout=g.QUERY_TIMEOUT_SECONDS)
    print(WINDOW_END, label, job.total_bytes_processed)
```

Sortie :

```
2026-09-25 trends_query 298886057
2026-09-25 all_columns 4199985564
```

| Requête | Octets lus selon BigQuery |
|---|---|
| `TRENDS_QUERY` | 298 886 057 |
| toutes les colonnes, même filtre | 4 199 985 564 |

En ne nommant que ses colonnes, `TRENDS_QUERY` lit **14 fois moins** (7,1 % du volume) que la même
sélection de toutes les colonnes.

## 3. Paramètres des requêtes aux API

Chaque source construit ses requêtes dans son module ; les valeurs des constantes (tailles de page,
plafonds, délais) sont dans le code, et leur justification dans la section de la source de
[specs-collecte.md](specs-collecte.md). Chaque téléchargement passe par `download`
(`src/k_b/http_download.py`) : délai (`TIMEOUT_SECONDS`), taille maximale, préfixe d'URL de
confiance
([règles communes](specs-collecte.md#règles-communes)).

| Source | Fichier | Construite par | Paramètres | Filtre à la requête | Spécifications |
|---|---|---|---|---|---|
| arXiv | `src/k_b/sources/arxiv.py` | `ArxivSource.fetch`, `build_search_query`, `download_papers` | URL `API_URL` ; `search_query` ; `start` ; `max_results` (`PAPERS_PER_PAGE`) ; `sortBy` et `sortOrder` (date de soumission, croissante) ; réponse plafonnée par `MAX_RESPONSE_BYTES` | `cat:cs.CR AND cat:cs.AI`, un mot-clé de `KEYWORDS` dans le résumé (`abs:`), `submittedDate` depuis la dernière collecte moins `ANNOUNCEMENT_DELAY_MARGIN` (première collecte : `FIRST_COLLECTION_START`) | [API arXiv](specs-collecte.md#api-arxiv--service-web) |
| GitHub, releases | `src/k_b/sources/github_releases.py` | `GithubReleasesSource.fetch` | chemin `repos/<dépôt>/releases`, dépôt pris dans `TRACKED_REPOSITORIES` (`tracked_repositories.py`) ; `per_page` (`RELEASES_PER_PAGE`) | aucun : `fetch` compare les dates de la page à la dernière collecte | [API GitHub](specs-collecte.md#api-github--service-web) |
| GitHub, alertes | `src/k_b/sources/github_advisories.py` | `GithubAdvisoriesSource.fetch` | chemin `advisories` ; `type=reviewed` ; `ecosystem` (un de `ECOSYSTEMS`) ; `affects` ; `per_page` (`ADVISORIES_PER_PAGE`) ; `reviewed`, seulement s'il y a une dernière collecte | `affects` : les paquets suivis, donnés par `list_packages_by_ecosystem` (`tracked_repositories.py`) ; `reviewed` : relues depuis la veille de la dernière collecte, puis `fetch` compare les dates de revue à la dernière collecte | [API GitHub](specs-collecte.md#api-github--service-web) |
| GitHub, dépôts les plus étoilés | `src/k_b/sources/github_most_starred.py` | `GithubMostStarredSource.fetch` | chemin `search/repositories` ; `q` (`SEARCH_QUERY`) ; `sort=stars` ; `order=desc` ; `per_page` (`RANKING_SIZE`) | aucun : la recherche exige un critère, et `SEARCH_QUERY` garde tout le classement (commentaire de la constante) | [API GitHub](specs-collecte.md#api-github--service-web) |
| GitHub, commun aux trois | `src/k_b/sources/github_api.py` | `get_from_github_api` | URL `API_URL` ; en-têtes `Accept` et `X-GitHub-Api-Version` (`API_VERSION`) ; jeton (`TOKEN_VARIABLE`) en `Authorization`, jamais transmis à une redirection ; réponse plafonnée par `MAX_RESPONSE_BYTES` | — | [jeton-github.md](jeton-github.md) |
| CISA KEV | `src/k_b/sources/cisa_kev.py` | `CisaKevSource.fetch` | URL `CATALOG_URL` ; en-tête `If-Modified-Since` (date de la dernière collecte), seulement s'il y en a une ; réponse plafonnée par `MAX_CATALOG_BYTES`, servie sous `TRUSTED_URL_PREFIX` | aucun : le catalogue entier, ou rien s'il n'a pas changé (`HTTP_NOT_MODIFIED`) | [Catalogue CISA KEV](specs-collecte.md#catalogue-cisa-kev--fichier) |
| tldr.tech | `src/k_b/sources/tldr.py` | `TldrSource.fetch` | URL `SITE_URL` + édition (une de `TRACKED_EDITIONS`) + jour ; jours donnés par `list_days_to_collect` (première collecte : `FIRST_COLLECTION_DAYS`) ; `PAUSE_BETWEEN_PAGES_SECONDS` entre deux pages ; page plafonnée par `MAX_PAGE_BYTES` | le jour, dans l'URL | [tldr.tech](specs-collecte.md#tldrtech--scraping) |

Par défaut, K-B filtre à la lecture, pas à la requête
([règles communes](specs-collecte.md#règles-communes)). Deux exceptions décidées posent le filtre
dans la requête : arXiv et les alertes GitHub ; leur raison est dans la section de chaque source
des specs. Deux autres économies : une requête conditionnelle (`If-Modified-Since`), qui ne
retélécharge pas un catalogue inchangé, et une pause entre deux pages de tldr.tech.
