# Les requêtes d'extraction de K-B

!!! note "Compétences de la certification"

    > La documentation des requêtes met en lumière choix de sélections, filtrages, conditions, jointures, etc., en
    > fonction des objectifs de collecte.

    — C2

    > La documentation explicite les optimisations appliquées aux requêtes.

    — C2

Cette fiche dit ce que K-B demande à chacune de ses sources, et pourquoi. Elle décrit les deux requêtes SQL
d'extraction, sur une copie de la base de Zotero et sur GH Archive dans BigQuery: leurs tables et leurs colonnes,
leurs filtres, leurs jointures, leur regroupement, puis leurs optimisations et leur mesure. Elle donne ensuite les
paramètres des requêtes faites aux API. Les scripts des mesures et leurs sorties entières sont dans
[le document des requêtes d'extraction](https://github.com/SabineLaurent/K-B/blob/main/docs/requetes-extraction.md),
`docs/requetes-extraction.md`. Elle est écrite d'après le code de `main` au commit `39cb5eb9`. Les
chemins du code de K-B (`etl/…`, `core/…`) partent de `src/k_b/`, les autres de la racine du dépôt.

## Les requêtes et leurs objectifs

Le tableau suivant donne chaque requête d'extraction de K-B: la source qu'elle interroge et comment, ce qu'elle
ramène, et l'objectif de collecte qu'elle sert.

| Requête | Source, et comment | Ce qu'elle ramène | Pourquoi |
|---|---|---|---|
| `EXTRACTION_QUERY` (`etl/sources/zotero.py:78-163`) | Zotero: une instruction SQL sur une copie de sa base SQLite, un système de gestion de base de données | chaque document de la bibliothèque personnelle, hors corbeille, avec son titre, sa date, son URL, sa référence arXiv, ses auteurs, ses étiquettes, ses PDF et leurs surlignages | la bibliothèque de lecture: les documents que l'utilisatrice a choisi de garder, et ce qu'elle y a surligné (`etl/sources/zotero.py:1-2`) |
| `TRENDS_QUERY` (`etl/sources/gh_archive.py:55-88`) | GH Archive: une instruction SQL sur BigQuery, un système <span lang="en">big data</span> | pour chaque fenêtre de trois jours UTC complets, les étoiles et les <span lang="en">forks</span> gagnés par dépôt, les 30 premiers par étoiles et les 30 premiers par <span lang="en">forks</span> | les dépôts qui montent, que classe le compte rendu des tendances (`core/config.py:97-101`): la recherche de l'API GitHub trie par total d'étoiles et ne dit pas quels dépôts en gagnent (`docs/specs-collecte.md`, « Pourquoi BigQuery ») |
| `GET /repos/{owner}/{repo}/releases` (`etl/sources/github/releases.py:48-52`) | API GitHub, en REST et en JSON | les 100 dernières <span lang="en">releases</span> de chacun des quatre dépôts suivis (`core/config.py:58-71`) | les nouvelles versions des dépôts que suit la veille (`docs/sources.md`, « Dépôts GitHub ») |
| `GET /advisories` (`etl/sources/github/advisories.py:50-69`) | API GitHub | les alertes de sécurité relues par GitHub qui touchent les paquets publiés par ces dépôts, une requête par écosystème, `pip` et `npm` (`core/config.py:39-42`) | les failles des paquets que suit la veille |
| `GET /search/repositories`, deux fois (`etl/sources/github/most_starred.py:33-43`, `etl/sources/github/most_forked.py:32-42`) | API GitHub | les 100 dépôts les plus étoilés de GitHub, puis les 100 plus forkés | les deux tops: un relevé à chaque collecte, que `kb write-tops` écrit en fiches |
| `GET /api/query` (`etl/sources/arxiv.py:102-111`) | API arXiv, un flux Atom | les papiers de sécurité de l'IA soumis dans la fenêtre de la collecte | la recherche sur la sécurité de l'IA (`etl/sources/arxiv.py:1-2`) |
| le catalogue (`etl/sources/cisa_kev.py:58-79`) | CISA KEV (<span lang="en">Known Exploited Vulnerabilities</span>, de la <span lang="en">Cybersecurity and Infrastructure Security Agency</span> américaine): un fichier CSV téléchargé en HTTPS | le catalogue entier, s'il a changé depuis la dernière collecte | les vulnérabilités activement exploitées (`etl/sources/cisa_kev.py:1-2`) |
| une page par jour et par édition (`etl/sources/tldr.py:108-142`) | tldr.tech: une page HTML | la page d'édition de chaque jour à collecter | les articles de chaque édition suivie (`etl/sources/tldr.py:1-2`) |

La septième source, le Web Clipper, n'a pas de requête: la collecte copie tels quels les clips du coffre Obsidian
(`etl/sources/clipping.py:1-2`).

Chaque requête vit dans le module de sa source, `etl/sources/<source>.py`. Les deux seuls modules de
`etl/sources/` qui écrivent du SQL sont ceux de Zotero et de GH Archive, et leurs requêtes ne font que lire une
source externe. Le SQL de la base de K-B vit dans `database/`.

## Zotero en SQL

### Où elle tourne

`ZoteroSource.fetch` ne lit jamais la base de Zotero en place (`etl/sources/zotero.py:4-5`, `:201-228`):

1. il retire d'abord les copies qu'un processus tué aurait laissées dans le dossier temporaire du système (`:207`,
    `:231-248`);
2. il copie `zotero.sqlite`, puis son journal d'écriture anticipée (<span lang="en">write-ahead log</span>),
    `zotero.sqlite-wal`, qui porte les dernières écritures de Zotero, dans un dossier temporaire. Une copie faite
    pendant que Zotero écrivait est refusée (`:211-212`, `:268-286`);
3. `extract_documents` ouvre la copie en lecture seule (`mode=ro`), la vérifie par `PRAGMA integrity_check`, puis
    lance `EXTRACTION_QUERY` (`:289-298`, `:311-324`);
4. le dossier temporaire est supprimé après un succès, une erreur ou un Ctrl-C (`:208-213`).

### Les tables et les colonnes lues

Le tableau suivant donne les 14 tables de Zotero que lit la requête, les colonnes lues de chacune et leur rôle
(`etl/sources/zotero.py:78-163`).

| Table | Colonnes lues | Rôle |
|---|---|---|
| `items` | `itemID`, `key`, `itemTypeID`, `libraryID`, `dateAdded` | le document; sous l'alias `attachment`, la clé d'un PDF; sous l'alias `annotation`, la clé et la date d'un surlignage |
| `itemTypes` | `itemTypeID`, `typeName` | le type du document |
| `libraries` | `libraryID`, `type` | la bibliothèque, personnelle ou de groupe |
| `deletedItems` | `itemID` | la corbeille |
| `itemData` | `itemID`, `fieldID`, `valueID` | le lien entre un document, un champ et sa valeur |
| `fields` | `fieldID`, `fieldName` | le nom du champ |
| `itemDataValues` | `valueID`, `value` | la valeur du champ |
| `itemCreators` | `itemID`, `creatorID`, `creatorTypeID`, `orderIndex` | les créateurs d'un document, dans leur ordre |
| `creators` | `creatorID`, `firstName`, `lastName` | le nom d'un créateur |
| `creatorTypes` | `creatorTypeID`, `creatorType` | son rôle: auteur, éditeur… |
| `itemTags` | `itemID`, `tagID`, `type` | les étiquettes d'un document, et leur type |
| `tags` | `tagID`, `name` | le nom d'une étiquette |
| `itemAttachments` | `itemID`, `parentItemID`, `contentType`, `path` | les fichiers d'un document |
| `itemAnnotations` | `itemID`, `parentItemID`, `type`, `text`, `comment`, `pageLabel`, `sortIndex` | les annotations d'un PDF |

La requête rend une ligne par document: `key`, `item_type`, `title`, `date`, `date_added`, `url`, `archive_id`, et
quatre listes en JSON, `authors`, `tags`, `pdfs` et `highlights` (`:95-160`, `JSON_COLUMNS`, `:165`). Elle ne lit ni
les résumés, ni les notes, ni les annotations qui ne sont pas des surlignages, ni les fichiers hors du stockage de
Zotero, ni les bibliothèques de groupe (`:76-77`): ces données sont écartées dès la collecte
([le registre des traitements](https://github.com/SabineLaurent/K-B/blob/main/docs/registre-traitements.md),
« Inventaire par source »).

### Les filtres et les conditions

Tous les filtres sont écrits dans le SQL (`etl/sources/zotero.py:84-159`):

- **la bibliothèque personnelle**: `libraries.type = 'user'` (`:84`);
- **un document, pas une pièce**: `itemTypes.typeName NOT IN ('attachment', 'note', 'annotation')` (`:85`);
- **hors de la corbeille**: `NOT IN (SELECT itemID FROM deletedItems)`, pour le document (`:86`), pour le PDF
    (`:136`, `:157`) et pour le surlignage (`:159`);
- **les quatre champs utiles**: `fields.fieldName IN ('title', 'date', 'url', 'archiveID')` (`:93`);
- **les auteurs seuls**, parmi les créateurs: `creatorTypes.creatorType = 'author'` (`:116`);
- **les PDF rangés par Zotero**: `itemAttachments.contentType = 'application/pdf'` et
    `itemAttachments.path LIKE 'storage:%'` (`:134-135`, `:155-156`); un fichier lié ailleurs sur le disque n'est
    pas lu;
- **les surlignages**: `itemAnnotations.type = 1` (`:158`).

Le test `test_only_the_documents_of_the_user_library_out_of_the_trash_are_extracted` le vérifie sur une bibliothèque
inventée: la corbeille, une bibliothèque de groupe, et avec elles chaque annotation, PDF ou capture qui n'est pas un
surlignage d'un document gardé, sont écartés (`tests/etl/sources/test_zotero.py:130-138`).

### Les jointures

La CTE `document` (<span lang="en">common table expression</span>, une sous-requête nommée par `WITH`) définit une
fois ce qu'est un document (`etl/sources/zotero.py:79-87`):

```sql
WITH document AS (
    SELECT items.itemID, items.key, itemTypes.typeName, items.dateAdded
    FROM items
    JOIN itemTypes ON itemTypes.itemTypeID = items.itemTypeID
    JOIN libraries ON libraries.libraryID = items.libraryID
    WHERE libraries.type = 'user'
        AND itemTypes.typeName NOT IN ('attachment', 'note', 'annotation')
        AND items.itemID NOT IN (SELECT itemID FROM deletedItems)
),
```

- **Le document**: `items`, `itemTypes` et `libraries`, dans la CTE `document`; chaque liste s'y rattache
    (`:79-87`).
- **Les champs**: la CTE `field_value` joint `itemData`, `fields` et `itemDataValues` (`:88-94`). Zotero ne range
    pas le titre ou l'URL dans des colonnes de `items`, mais en lignes, une par champ rempli (modèle
    entité-attribut-valeur): la jointure retrouve le nom du champ et sa valeur, puis une sous-requête par champ en
    fait une colonne du résultat (`:98-106`).
- **Les auteurs**: `itemCreators`, `creators` et `creatorTypes` (`:112-116`). **Les étiquettes**: `itemTags` et
    `tags` (`:122-124`).
- **Les PDF**: `itemAttachments` et `items`, sous l'alias `attachment`, pour la clé du PDF (`:131-133`). **Les
    surlignages**: les mêmes, puis `itemAnnotations` et `items`, sous l'alias `annotation`, pour la clé et la date du
    surlignage (`:150-154`).

### Le regroupement et l'ordre

- La requête n'a pas de `GROUP BY`: chaque liste est une sous-requête corrélée au document, qui agrège ses lignes
    en JSON par `json_group_array(json_object(…) ORDER BY …)` (`etl/sources/zotero.py:107-160`). Un document sans
    pièce reçoit des listes vides, `[]` (test `test_a_paper_with_nothing_attached_is_extracted_with_empty_lists`).
- L'ordre de chaque liste est fixé dans son agrégat: les auteurs par `itemCreators.orderIndex`, l'ordre de Zotero
    (`:110`); les étiquettes par `tags.name` (`:120`); les PDF par `attachment.itemID` (`:129`); les surlignages par
    `attachment.itemID`, puis `itemAnnotations.sortIndex`, leur place dans le PDF, puis `annotation.itemID`
    (`:148`). Un `ORDER BY` dans un agrégat demande SQLite 3.44 (`:177-179`).
- Le résultat est trié par `document.dateAdded`, puis `document.itemID` (`:162`): la même bibliothèque donne le même
    extrait, octet pour octet (test `test_the_extract_is_utf8_json_and_the_same_bytes_for_the_same_library`).
- `extract_documents` relit chaque liste JSON (`json.loads`, `:302-308`), et `ZoteroSource.fetch` rend l'extrait
    entier en JSON (`:222-224`).

### Les optimisations

- **Une instruction pour toute la bibliothèque**, au lieu d'une requête par document lancée depuis Python: la
    définition d'un document n'est écrite qu'une fois, et SQLite fait les jointures. Elle va environ 1,9 fois plus
    vite ([Le temps, une instruction contre une requête par document](#le-temps-une-instruction-contre-une-requete-par-document)).
- **Chaque liste est cherchée par la clé du document**: chaque sous-requête corrélée filtre sur `itemID` ou
    `parentItemID` (`etl/sources/zotero.py:99-106`, `:115`, `:124`, `:133`, `:154`), que des index de Zotero
    couvrent. Seule la table `items` est parcourue en entier, une fois ([Le plan d'exécution](#le-plan-dexecution)).
- **Seuls les champs utiles sont nommés**, et tous les filtres sont dans le SQL: rien n'est lu pour être jeté
    ensuite en Python (`:93`).
- **Une copie, lue seule**: la requête ne prend aucun verrou sur la base de Zotero (`:211-213`, `:292-294`).
- **Rien d'écrit quand rien n'a changé**: la copie et la requête ont lieu à chaque collecte, mais un extrait
    identique, octet pour octet, au dernier du brut n'est pas écrit (`:225-227`; test
    `test_two_collections_of_an_unchanged_library_write_one_extract`).

### Leur mesure

Les deux mesures suivantes sont celles de `docs/requetes-extraction.md`, faites le 2026-11-03. Le module
`etl/sources/zotero.py` est le même aux deux commits mesurés et au commit `39cb5eb9` (section
[Vérifier cette fiche](#verifier-cette-fiche)).

#### Le plan d'exécution

Le plan d'exécution (`EXPLAIN QUERY PLAN`) dit comment SQLite lit chaque table: `SEARCH`, une recherche par index ou
par clé, qui ne lit que les lignes cherchées; `SCAN`, un parcours de la table entière. Dans une sous-requête
corrélée, rejouée pour chaque document, un `SCAN` relirait toute sa table à chaque document.

- **La bibliothèque**: une bibliothèque Zotero réelle, de 5 documents et 6 surlignages, copiée comme à la collecte
    (`copy_library`, puis `extract_documents`), ouverte en lecture seule, sans statistiques d'`ANALYZE`.
- **Le code et le logiciel**: `main` au commit `236d22c`, SQLite 3.50.4.
- **La date**: 2026-11-03.

Le tableau suivant donne, pour chaque partie de la requête, comment le plan lit chaque table.

| Partie de la requête | Table | Accès | Par |
|---|---|---|---|
| le document (CTE `document`) | `items` | `SCAN`, une fois | l'index `items_synced` de Zotero |
| le document | `itemTypes`, `libraries` | `SEARCH` | la clé (`rowid`) |
| la corbeille, partout | `deletedItems` | `SEARCH` | la clé (`rowid`) |
| les quatre champs | `itemData` | `SEARCH` | l'index de sa clé primaire, sur `itemID` |
| les quatre champs | `fields`, `itemDataValues` | `SEARCH` | la clé (`rowid`) |
| les auteurs | `itemCreators` | `SEARCH` | l'index couvrant de sa clé primaire, sur `itemID` |
| les auteurs | `creatorTypes`, `creators` | `SEARCH` | la clé (`rowid`) |
| les étiquettes | `itemTags`, puis `tags` | `SEARCH` | l'index de sa clé primaire, sur `itemID`, puis la clé |
| les PDF et les surlignages | `itemAttachments` | `SEARCH` | l'index `itemAttachments_parentItemID`, sur `parentItemID` |
| les surlignages | `itemAnnotations` | `SEARCH` | l'index `itemAnnotations_parentItemID`, sur `parentItemID` |
| les PDF et les surlignages | `items`, sous les alias `attachment` et `annotation` | `SEARCH` | la clé (`rowid`) |

- **Un seul `SCAN`, celui de `items`, une fois pour toute la requête.** Un document se reconnaît à son type, à sa
    bibliothèque et à son absence de la corbeille: chaque item est examiné.
- **Tout le reste est `SEARCH`.** Les huit sous-requêtes corrélées, rejouées pour chaque document, entrent chacune
    par la clé du document dans un index: `itemID=?` pour les champs, les auteurs et les étiquettes,
    `parentItemID=?` pour les PDF, puis la clé du PDF pour ses surlignages.
- **La CTE `field_value` n'est pas bâtie à part.** SQLite la fond dans chacune des quatre sous-requêtes de champ, au
    lieu de bâtir d'abord la table des champs de toute la bibliothèque.
- **La corbeille** devient une recherche par clé dans `deletedItems`.
- **Les cinq `USE TEMP B-TREE` sont des tris**: un par liste triée, sur les lignes d'un seul document, et le tri
    final.

**Mise en regard.** La bibliothèque inventée des tests, `tests/fixtures/zotero_extract.sql`, a les tables de Zotero
sans les index que Zotero crée à part. Sur elle, la même requête parcourt `itemAttachments` et `itemAnnotations` en
entier pour chaque document (`SCAN`). Les index `itemAttachments_parentItemID` et `itemAnnotations_parentItemID` de
Zotero changent ces parcours en recherches: la requête en profite parce qu'elle relie un PDF à son document, et un
surlignage à son PDF, par `parentItemID`.

#### Le temps, une instruction contre une requête par document

Cette mesure chronomètre `EXTRACTION_QUERY` contre ce qu'elle remplace: une requête par document, lancée depuis
Python.

- **Les bibliothèques**: deux bibliothèques fabriquées, de 1 000 et de 10 000 documents, sur le schéma relevé d'une
    base Zotero réelle: les 14 tables lues et `itemNotes`, leurs 15 index créés à part, le schéma `userdata` en
    version 130, des pages de 32 768 octets. Aucune donnée réelle n'y entre.
- **Chaque document**: 10 champs, dont les 4 lus; 3 auteurs et 1 éditeur; 4 étiquettes; 1 PDF rangé par Zotero,
    1 PDF lié hors de Zotero et 1 capture HTML; 6 surlignages et 2 autres annotations; 1 note. 5 % des documents,
    2 % des PDF et 2 % des annotations sont à la corbeille, et une bibliothèque de groupe ajoute 10 % de documents:
    chaque filtre a des lignes à écarter.
- **La variante comparée**: la liste des documents, puis, pour chaque document, `EXTRACTION_QUERY` avec
    `WHERE document.itemID = ?` à la place de son `ORDER BY`, découpée dans la constante. Les deux façons de faire
    rendent les mêmes lignes, et le plan de la variante n'a aucun `SCAN`.
- **Le chronomètre**: un passage de chauffe de chaque façon de faire, puis 7 passages, dans un ordre alterné, le
    ramasse-miettes de Python arrêté. Le temps couvre l'exécution et la lecture des lignes.
- **La machine et les logiciels**: Apple M4, 16 Go, macOS (Darwin 25.6.0); Python 3.13.13, SQLite 3.50.4; `main` au
    commit `bd433db`; le 2026-11-03 à 16:10 UTC, cache chaud.

Le tableau suivant donne les temps médians des deux façons de faire, aux deux tailles.

| Documents lus | Items dans la base | `EXTRACTION_QUERY` (médiane) | Une requête par document (médiane) | Rapport |
|---|---|---|---|---|
| 950 | 14 300 | 12,6 ms | 23,6 ms | 1,88 |
| 9 500 | 143 000 | 145,5 ms | 269,1 ms | 1,85 |

- **Une seule instruction va environ 1,9 fois plus vite** qu'une requête par document, aux deux tailles. Chaque
    passage reste à 15 % au plus de sa médiane.
- **Le temps des deux grandit comme le nombre de documents.** De 950 à 9 500 documents lus (× 10),
    `EXTRACTION_QUERY` passe de 12,6 à 145,5 ms (× 11,5), et la variante de 23,6 à 269,1 ms (× 11,4): aucune des deux
    ne relit une table entière par document.
- **Le plan de `EXTRACTION_QUERY` sur 10 000 documents est identique, ligne pour ligne, à celui relevé sur
    5 documents**: la base fabriquée a le schéma de la vraie.
- **Le plan de la variante ne diffère que de deux lignes**: une recherche de `items` par sa clé au lieu du `SCAN`,
    et pas de tri final. Les deux façons de faire lancent les mêmes recherches; ce qui les sépare est le nombre
    d'instructions, une seule, ou une par document en plus de la liste.

## GH Archive sur BigQuery

### Où elle tourne

`GhArchiveSource.fetch` (`etl/sources/gh_archive.py:114-141`), dans l'ordre:

1. calcule les fenêtres dues depuis la dernière collecte, la plus récente finissant hier (`list_window_ends`,
    `:119`, `:159-180`);
2. vérifie que la table du dernier jour est close, par ses métadonnées (`get_table`), sans requête (`:123`,
    `:183-194`);
3. fait le `dry_run`, qui donne le volume à lire sans rien lire (`drop_windows_over_the_cap`, `:124`, `:202-236`);
4. lance la requête, avec ses paramètres (`configure_query`, `:125-130`, `:239-262`).

Le projet BigQuery est un bac à sable sans compte de facturation, et K-B s'y connecte par un compte de service au
seul rôle d'utilisateur de job BigQuery
([le bac à sable BigQuery de K-B](https://github.com/SabineLaurent/K-B/blob/main/docs/bigquery.md), « Le projet »
et « Le compte de service »).

### La table et les colonnes lues

- **La table**: `githubarchive.day.20*`, une table par jour, désignée par un joker (`etl/sources/gh_archive.py:59`).
    Elle est écrite dans le texte de la requête, car BigQuery n'accepte pas une table en paramètre; un test la tient
    égale à `TABLE_PREFIX` (`:45`, `:53-54`; test
    `test_the_query_reads_its_sizes_from_parameters_and_the_tables_of_the_prefix`).
- **Les colonnes**: `repo.id`, `repo.name`, `type`, `created_at`, et la pseudo-colonne `_TABLE_SUFFIX`, la fin du nom
    de la table, qui donne le jour (`:57-58`). Jamais `actor`, le login de qui a donné l'étoile, ni `payload`, ni
    `org` (`:49`; tests `test_the_query_never_reads_the_actor` et `test_the_raw_result_holds_no_actor`): la requête
    compte des événements, pas des personnes (`:51-52`).

### Les filtres

Les filtres sont dans la CTE `events` (`etl/sources/gh_archive.py:56-64`):

```sql
WITH events AS (
  SELECT repo.id AS repository_id, repo.name AS repository_name, type, created_at,
         PARSE_DATE('%Y%m%d', CONCAT('20', _TABLE_SUFFIX)) AS event_day
  FROM `githubarchive.day.20*`
  WHERE _TABLE_SUFFIX BETWEEN @first_suffix AND @last_suffix
    AND type IN ('WatchEvent', 'ForkEvent')
    AND repo.id IS NOT NULL
    AND repo.name IS NOT NULL
),
```

- **les jours voulus**: `_TABLE_SUFFIX BETWEEN @first_suffix AND @last_suffix` (`:60`);
- **les étoiles et les <span lang="en">forks</span>**: `type IN ('WatchEvent', 'ForkEvent')` (`:61`); un `WatchEvent` est une étoile
    donnée (`:50-51`);
- **un dépôt identifié**: `repo.id IS NOT NULL` et `repo.name IS NOT NULL` (`:62-63`; test
    `test_the_query_leaves_out_the_events_without_a_repository`).

### La jointure

`UNNEST(@window_ends)` fait une ligne par fin de fenêtre. Chaque événement y est joint quand son jour tombe dans la
fenêtre, du jour de fin moins `@window_days - 1` jours au jour de fin (`etl/sources/gh_archive.py:71-73`). Un
événement compte ainsi dans chaque fenêtre qui couvre son jour, et un rattrapage de plusieurs fenêtres lit chaque
jour une fois (test `test_fetch_catches_up_every_missed_window_in_one_query`).

### Le regroupement et le classement

- La CTE `counts` regroupe par `window_end, repository_id` (`etl/sources/gh_archive.py:74`): `COUNTIF` compte les
    étoiles et les <span lang="en">forks</span> (`:69-70`); le dernier nom vu du dépôt est pris par `ARRAY_AGG`, trié par date d'événement
    décroissante, puis par nom décroissant (`:67-68`).
- La CTE `ranked` classe les dépôts de chaque fenêtre deux fois, par `ROW_NUMBER()`: par étoiles, puis par <span lang="en">forks</span>,
    départagés par `repository_id` (`:76-83`).
- La requête garde les dépôts dont l'un des deux rangs ne dépasse pas `@top_size`, triés par `window_end`, puis
    `stars_gained` décroissant, puis `repository_id` (`:84-87`): les mêmes tables donnent le même résultat
    (`:52-53`).

Les comptes que rend la requête sont un échantillon des étoiles et des <span lang="en">forks</span> de GitHub, dont
[la page de la collecte](collecte.md) donne la mesure.

### Les paramètres

Le tableau suivant donne les cinq paramètres de la requête, posés par `configure_query`, jamais collés dans son
texte (`etl/sources/gh_archive.py:239-252`).

| Paramètre | Type | Valeur |
|---|---|---|
| `@first_suffix` | `STRING` | le premier jour lu, au format `AAMMJJ` (`TABLE_SUFFIX_FORMAT`, `:46-47`): la fin de la première fenêtre, moins `GH_ARCHIVE_WINDOW_DAYS - 1` jours (`:241`) |
| `@last_suffix` | `STRING` | le dernier jour lu: la fin de la dernière fenêtre |
| `@window_ends` | tableau de `DATE` | les fins de fenêtre, de la plus ancienne à hier |
| `@window_days` | `INT64` | `GH_ARCHIVE_WINDOW_DAYS`, 3 jours (`core/config.py:84-85`) |
| `@top_size` | `INT64` | `GH_ARCHIVE_TOP_SIZE`, 30 dépôts (`core/config.py:82-83`) |

Les jours et les fenêtres changent d'une collecte à l'autre. `@window_days` et `@top_size` ne changent pas: ce sont
des paramètres pour que leur valeur ne soit écrite qu'à un endroit, `core/config.py`. Un test vérifie que la taille
du classement n'est pas dans le texte de la requête
(`test_the_query_reads_its_sizes_from_parameters_and_the_tables_of_the_prefix`), un autre les cinq valeurs d'une
fenêtre finissant le 2026-10-10: `261008`, `261010`, cette fin, 3 et 30
(`test_fetch_runs_a_dry_run_then_the_query_capped_with_its_parameters`).

### Les optimisations

- **Le stockage par colonnes**: BigQuery ne lit que les colonnes que nomme la requête, pas la ligne entière
    (`docs/requetes-extraction.md`, « Ce qui la rend économe »): quatre colonnes et le jour
    (`etl/sources/gh_archive.py:57-58`).
- **L'élagage des tables par leur suffixe**: le filtre sur `_TABLE_SUFFIX` fait que BigQuery n'ouvre que les tables
    des jours voulus (`:60`).
- **Une requête pour toutes les fenêtres dues**: chaque jour est lu une fois, même quand plusieurs fenêtres le
    couvrent (`:71-73`).
- **Le `dry_run` d'abord**: `drop_windows_over_the_cap` demande le volume sans rien exécuter, ce qui ne consomme pas
    de quota (`dry_run=True`, `use_query_cache=False`, `:211-215`, `:253-256`; `docs/bigquery.md`, « Vérifier »).
    Au-delà du plafond, la source retire ses fenêtres les plus anciennes quand la borne de 2 Go s'applique, ou échoue
    sans rien exécuter (`DryRunOverLimitError`, `:221-236`). Sans volume, elle échoue aussi sans rien exécuter
    (`DryRunVolumeUnknownError`, `:216-220`).
- **Puis l'exécution plafonnée**: `maximum_bytes_billed` vaut 650 Mo par fenêtre, 2 Go au plus (`compute_bytes_cap`,
    `:41-42`, `:149-151`, `:257-258`), et `job_timeout_ms` arrête le job chez BigQuery après 300 s (`:43`,
    `:259-260`).
- **Un rattrapage borné**: 15 fenêtres au plus, les plus récentes (`GH_ARCHIVE_MAX_CATCH_UP_WINDOWS`,
    `core/config.py:86-88`; `etl/sources/gh_archive.py:172-179`).
- **Le bac à sable**: le projet n'a pas de compte de facturation; au-delà de son quota de 1 Tio lu par mois, une
    requête est refusée, jamais facturée (`docs/bigquery.md`, lignes 3 à 5).

### Leur mesure

#### Les colonnes lues contre toutes les colonnes

Deux `dry_run`, sur les mêmes tables et avec le même filtre: `TRENDS_QUERY` contre `SELECT *` suivi du `FROM` et du
`WHERE` de sa CTE `events`, découpés dans son texte, avec ses deux seuls paramètres de jours. La fenêtre finit le
2026-09-25 (tables du 23, du 24 et du 25 septembre). Mesure du 2026-10-11 à 17:26 UTC
(`docs/requetes-extraction.md`, section 2). Le texte de `TRENDS_QUERY` n'a pas changé depuis le commit `f55275f2`
(2026-10-11, 15:31 UTC), qui précède la mesure.

Le tableau suivant donne les octets que chaque requête lirait, selon BigQuery.

| Requête | Octets lus selon BigQuery |
|---|---|
| `TRENDS_QUERY` | 298 886 057 |
| toutes les colonnes, même filtre | 4 199 985 564 |

En ne nommant que ses colonnes, `TRENDS_QUERY` lit 14 fois moins, 7,1 % du volume de la même sélection de toutes les
colonnes.

#### Le plafond d'octets facturés

Le plafond vient de `dry_run` de `TRENDS_QUERY` faits le 2026-10-11
([le bac à sable BigQuery de K-B](https://github.com/SabineLaurent/K-B/blob/main/docs/bigquery.md), « Le plafond de
la collecte »). Le tableau suivant donne les deux mesures qui le fixent.

| Mesure | Octets lus | Ce qu'elle fixe |
|---|---|---|
| la fenêtre la plus lourde des 15 mesurées une à une, finissant le 2026-09-28 | 433 499 230 | le plafond par fenêtre: × 1,5, arrondi à 650 Mo |
| le rattrapage le plus long, 15 fenêtres en une requête, 17 jours lus, du 2026-09-24 au 2026-10-10 | 1 582 987 509 | la borne: le rattrapage tient sous 2 Go, avec une marge de × 1,26 |

- **Chaque jour est lu une fois**: une requête de 7 fenêtres lit 9 jours, une de 15 en lit 17.
- **La borne s'applique dès 4 fenêtres** (4 × 650 Mo > 2 Go). Sous elle, retirer une fenêtre baisse le plafond
    d'une fenêtre entière et le volume d'un seul jour: la source ne retire de fenêtre qu'une fois la borne atteinte
    (`etl/sources/gh_archive.py:205-209`; test `test_fetch_drops_the_oldest_windows_while_the_bound_applies`).
- **Une collecte quotidienne lit une fenêtre**: au plus lourd mesuré, 433 Mo, soit environ 13 Go par mois, sur le
    quota de 1 Tio.
- Le test `test_the_cap_is_650_mb_a_window_up_to_2_gb` tient ces valeurs: 650 Mo pour une fenêtre, 1,95 Go pour
    trois, 2 Go pour quatre et pour quinze.

## Les paramètres des requêtes aux API

Par défaut, K-B filtre à la lecture du brut, pas à la requête: le brut garde ce que la source a rendu
(`docs/specs-collecte.md`, « Règles communes »). Deux exceptions décidées posent le filtre dans la requête: arXiv
et les alertes GitHub (`docs/specs-collecte.md`, « API arXiv » et « API GitHub »). Les
réglages de la veille (mots-clés, éditions, dépôts suivis, tailles des tops, délai réseau) sont dans
`core/config.py`, chacun préfixé par sa source (`core/config.py:8-9`); les faits des API et les plafonds restent dans
le module de la source.

### arXiv

- **La requête**: `GET https://export.arxiv.org/api/query`, construite par `build_search_query` et `download_papers`
    (`etl/sources/arxiv.py:49`, `:90-111`).
- **Le filtre côté serveur**: `search_query` garde les papiers classés à la fois en `cs.CR`
    (<span lang="en">Cryptography and Security</span>) et en `cs.AI` (<span lang="en">Artificial Intelligence</span>),
    dont le résumé contient l'un des huit mots-clés de `ARXIV_KEYWORDS`, entre guillemets s'il a plusieurs mots
    (`abs:"prompt injection" OR abs:jailbreak OR …`) (`:92-95`, `:99`, `core/config.py:11-21`).
- **La fenêtre de dates**: `submittedDate:[<début> TO <fin>]`, en UTC, à la minute (`:96-99`). Le début est la
    dernière collecte moins 7 jours: un papier n'est cherchable qu'une fois annoncé, jusqu'à 3,5 jours après sa
    soumission, plus tard les jours fériés (`ARXIV_ANNOUNCEMENT_DELAY_MARGIN`, `core/config.py:22-26`). À la
    première collecte, le début est le 2026-05-01 (`ARXIV_FIRST_COLLECTION_START`, `core/config.py:29`). La fin est
    l'instant de la collecte (`:69`, `:74`). Ce que deux fenêtres ont en commun est écarté à l'import, par
    l'identifiant arXiv (`core/config.py:24-25`).
- **La pagination**: une seule page, `start=0` et `max_results=2000`, le maximum de l'API (`PAPERS_PER_PAGE`,
    `:52-53`), triée par date de soumission croissante (`sortBy=submittedDate`, `sortOrder=ascending`, `:104-110`).
    La collecte vérifie que la page tient tous les papiers qu'arXiv annonce (`opensearch:totalResults`, `:75-81`);
    [la page de la collecte](collecte.md) dit ce qu'elle fait sinon.
- **La réponse** est plafonnée à 6 Mio (`MAX_RESPONSE_BYTES`, `:51`).

### GitHub

Les quatre requêtes GitHub passent par `get_from_github_api` (`etl/sources/github/api.py:39-66`):

- **l'adresse et les en-têtes**: `https://api.github.com/`, avec `Accept: application/vnd.github+json` et
    `X-GitHub-Api-Version: 2026-03-10`, la version de l'API que K-B demande (`core/github_api.py:3-4`,
    `etl/sources/github/api.py:52-55`; test `test_the_request_follows_the_github_conventions_and_has_a_timeout`);
- **le jeton**: `KB_GITHUB_TOKEN`, envoyé dans `Authorization: Bearer`, jamais transmis à une redirection; sans
    jeton, la requête part anonyme, et GitHub accorde 60 requêtes par heure au lieu de 5 000 (`:16`, `:39-42`,
    `:56-59`; tests `test_the_token_is_sent_but_never_forwarded_to_a_redirection` et
    `test_without_a_token_the_request_is_anonymous`);
- **la réponse**, plafonnée à 5 Mio (`:17-18`);
- **le débit**: un 429 sans `Retry-After` attend 60 s avant son nouvel essai, comme GitHub le demande (`:19-21`,
    `:60`); une pause demandée par GitHub vaut pour toutes les sources GitHub de la collecte, et aucune requête ne
    part avant sa fin (`:22-24`, `:44-45`, `:62-66`).

Chaque requête lit une page de 100 entrées, le maximum de l'API (`etl/sources/github/releases.py:32-33`,
`etl/sources/github/advisories.py:33-34`, `core/config.py:72-74`). Le tableau suivant donne les quatre requêtes,
leurs paramètres, leur filtre côté serveur et leur fenêtre de dates.

| Requête | Paramètres | Filtre côté serveur | Fenêtre de dates |
|---|---|---|---|
| les <span lang="en">releases</span> d'un dépôt suivi | `repos/<dépôt>/releases?per_page=100` (`etl/sources/github/releases.py:50-52`), une requête par dépôt de `GITHUB_TRACKED_REPOSITORIES` (`etl/source_kinds.py:51`) | aucun | aucune à la requête: `fetch` compare les dates de publication de la page à la dernière collecte, et ne rend rien si aucune n'est plus récente (`etl/sources/github/releases.py:69-73`) |
| les alertes d'un écosystème | `advisories?type=reviewed&ecosystem=<pip ou npm>&affects=<paquets>&sort=updated&per_page=100`, et `updated` à `>=<jour>` s'il y a une dernière collecte (`etl/sources/github/advisories.py:58-69`) | les alertes relues par GitHub (`type=reviewed`) des seuls paquets suivis (`affects`), donnés par `list_packages_by_ecosystem` (`etl/source_kinds.py:33-43`): l'écosystème `npm` entier dépasse 100 alertes par semaine, et obligerait à paginer (`docs/specs-collecte.md`, « API GitHub ») | la veille de la dernière collecte: le filtre `updated` ne se lit qu'au jour, d'où un jour de marge (`etl/sources/github/advisories.py:65-68`). L'API n'a pas de filtre sur la date de revue: la requête filtre et trie sur la date de mise à jour, jamais antérieure à la revue, puis `fetch` compare les dates de revue à la dernière collecte (`:54-57`, `:80-83`) |
| les dépôts les plus étoilés | `search/repositories?q=stars:>10000&sort=stars&order=desc&per_page=100` (`etl/sources/github/most_starred.py:35-41`) | `stars:>10000`: la recherche exige un critère, et celui-ci garde tout le top 100 (`core/config.py:75-77`) | aucune: un relevé à chaque collecte (`etl/sources/github/most_starred.py:33-34`) |
| les dépôts les plus forkés | `search/repositories?q=forks:>10000&sort=forks&order=desc&per_page=100` (`etl/sources/github/most_forked.py:34-40`) | `forks:>10000`, de même (`core/config.py:78-80`) | aucune: un relevé à chaque collecte (`etl/sources/github/most_forked.py:32-33`) |

### CISA KEV

- **La requête**: `GET https://www.cisa.gov/sites/default/files/csv/known_exploited_vulnerabilities.csv`
    (`etl/sources/cisa_kev.py:41-43`).
- **L'en-tête de cache**: `If-Modified-Since`, la date de la dernière collecte au format HTTP, s'il y en a une
    (`:63-67`). Un catalogue inchangé répond 304: rien n'est retéléchargé ni écrit (`:48`, `:72-74`; tests
    `test_a_later_collection_asks_only_for_a_catalog_modified_since_the_last_one` et
    `test_an_unmodified_catalog_returns_nothing`).
- **Le filtre**: aucun à la requête. La collecte lit d'abord le catalogue entier, pour refuser une page qui n'en est
    pas un (`:58-62`, `:76-79`); la base écarte ensuite ce qu'elle a déjà (`:108-110`).
- **La réponse** est plafonnée à 10 Mio, et refusée si elle est servie hors de `https://www.cisa.gov/` (`:44-47`;
    test `test_a_redirection_out_of_cisa_is_refused_not_read_as_unmodified`).

### tldr.tech

- **La requête**: `GET https://tldr.tech/<édition>/<AAAA-MM-JJ>`, une par édition suivie, `ai`, `infosec`, `dev` et
    `tech`, et par jour (`etl/sources/tldr.py:35`, `:116`, `core/config.py:31-32`; test
    `test_the_page_of_a_day_is_asked_at_its_edition_and_date_url`).
- **Le filtre**: le jour, dans l'URL.
- **La fenêtre de dates**: chaque jour, du jour de la dernière collecte, relu car son édition peut être sortie après
    elle, à aujourd'hui; à la première collecte, les 7 jours qui précèdent aujourd'hui, et aujourd'hui (`:173-185`,
    `core/config.py:36-37`; tests `test_every_day_from_the_last_collection_day_to_today_is_asked` et
    `test_a_first_collection_asks_the_seven_days_before_today_and_today`).
- **Le rythme**: une pause de 2 s avant chaque page, d'une édition à l'autre aussi, car tldr.tech ne publie pas de
    limite de débit (`:113-115`, `core/config.py:33-35`).
- **La réponse**: plafonnée à 1 Mio (`:37`). L'URL de la page est son propre préfixe de confiance: toute redirection
    se voit, et un jour renvoyé vers la page d'accueil de l'édition est sauté, sans édition (`:118-132`).

### Ce que partagent toutes les requêtes

Chaque téléchargement passe par `download` (`etl/http_download.py:36-68`):

- **un délai** de 30 s par opération réseau, la connexion ou chaque lecture (`HTTP_TIMEOUT_SECONDS`,
    `core/config.py:127-129`, `etl/http_download.py:79`);
- **une taille maximale**, propre à chaque source: au-delà, la réponse est refusée (`:147-156`);
- **un préfixe d'URL de confiance**: chaque redirection est contrôlée avant d'être demandée, 10 au plus (`:93-135`,
    `core/config.py:130-132`);
- **un `User-Agent` qui nomme K-B** (`etl/http_download.py:138-144`);
- **un seul nouvel essai**, après un 429, un 5xx, un 403 qui porte `Retry-After` (la limite secondaire de GitHub) ou
    un échec de connexion. Il attend le `Retry-After`, 3 s au moins, l'écart qu'arXiv demande entre deux requêtes,
    ou 5 s sans lui (`etl/http_retry.py:19-25`, `:33-58`, `:79-86`). Un délai dépassé n'a pas de nouvel essai: il
    doublerait une attente de 30 s (`:19-21`, `:40-44`). Une limite de débit épuisée, ou un `Retry-After` de plus de
    60 s, n'en a pas non plus: la collecte suivante redemande (`:26-30`, `:45-52`).

## Vérifier cette fiche

Depuis la racine du dépôt, au commit `39cb5eb9`:

```bash
# Seuls les modules de Zotero et de GH Archive portent une requête SQL dans etl/sources/: ces deux fichiers attendus.
grep -rlE "SELECT " src/k_b/etl/sources --include='*.py'
# Aucune requête d'extraction n'écrit: aucune ligne attendue.
grep -rlE "INSERT INTO|UPDATE |DELETE FROM" src/k_b/etl/sources --include='*.py'
# Zotero: les documents gardés, l'ordre, la copie lue seule, l'extrait inchangé non écrit: 12 passed attendus.
uv run pytest tests/etl/sources/test_zotero.py -q -k "extracted or same_bytes or unchanged or read_only or naming or identical"
# Le module de Zotero est le même aux commits des deux mesures: aucune ligne attendue.
git diff --stat 236d22c 39cb5eb9 -- src/k_b/etl/sources/zotero.py
git diff --stat bd433db 39cb5eb9 -- src/k_b/etl/sources/zotero.py
# Sans les index de Zotero, la bibliothèque inventée des tests est parcourue: SCAN items, itemAttachments, itemAnnotations attendus.
uv run python -I -c "import sqlite3, pathlib; from k_b.etl.sources.zotero import EXTRACTION_QUERY as q; c = sqlite3.connect(':memory:'); c.executescript(pathlib.Path('tests/fixtures/zotero_extract.sql').read_text()); print(*[d for *_, d in c.execute('EXPLAIN QUERY PLAN ' + q) if 'SCAN' in d], sep='\n')"
# GH Archive: le plafond, le dry_run, la borne, le rattrapage en une requête, les paramètres, ni actor ni dépôt sans nom: 16 passed attendus.
uv run pytest tests/etl/sources/test_gh_archive.py -q -k "cap_is or over_the_cap or dry_run or bound or catches_up or the_query or actor or closed"
# Le délai, la taille, les redirections et le nouvel essai, communs à toutes les requêtes: 97 passed attendus.
uv run pytest tests/etl/test_http_download.py tests/etl/test_http_retry.py -q
```

Un `fichier:ligne` se relit sans changer de commit: `git show 39cb5eb9:<chemin> | sed -n '<début>,<fin>p'`, avec
`src/k_b/` devant un chemin du code de K-B.
