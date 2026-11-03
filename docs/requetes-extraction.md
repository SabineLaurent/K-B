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
jamais un numéro de ligne. Seules les mesures des sections 1 et 2 sont écrites ici, parce qu'elles
n'existent nulle part ailleurs.

**Hors de ce document** : le SQL de la base K-B (sous `src/k_b/database/`, règle 5 de
`.claude/rules/conventions.md`) ;
la panne des tables GH Archive constatée depuis le 2026-10-06
([bigquery.md](bigquery.md#anomalie-constatée--les-tables-de-gh-archive-incomplètes-depuis-le-2026-10-06)).

**Où vivent ces requêtes** : chacune dans le module de sa source,
`src/k_b/etl/sources/<source>.py`. Une requête qui lit une source externe, en lecture seule, n'est
pas du SQL de la base K-B : elle reste avec sa source (règle 5 de `.claude/rules/conventions.md`,
« Couche d'accès aux données »).

## 1. Zotero — `EXTRACTION_QUERY`

Fichier : `src/k_b/etl/sources/zotero.py`. Spécifications de la source :
[specs-collecte.md](specs-collecte.md#zotero--base-de-données).

### Où elle tourne

`ZoteroSource.fetch` retire d'abord les copies qu'un processus tué aurait laissées
(`remove_left_copies`), puis copie la base (`copy_library`) dans un dossier temporaire ;
`extract_documents` ouvre la copie en lecture seule (`mode=ro`), la vérifie
(`check_integrity`), et lance `EXTRACTION_QUERY`. La base de
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
`src/k_b/etl/extract.py`).

### Ce qui la rend économe

- **Une instruction pour toute la bibliothèque**, au lieu d'une requête par document lancée depuis
  Python : la définition d'un document n'est écrite qu'une fois, et SQLite fait les jointures.
  Sur une bibliothèque fabriquée, elle va environ 1,9 fois plus vite qu'une requête par document
  (mesure du temps ci-dessous).
- **Chaque liste est cherchée par la clé du document** : chaque sous-requête corrélée filtre sur
  `itemID` ou `parentItemID`, des colonnes que Zotero indexe. Seule la table `items` est parcourue
  en entier, une fois (mesure du plan ci-dessous).
- **Seuls les champs utiles sont nommés**, et tous les filtres sont dans le SQL : rien n'est lu
  pour être jeté ensuite en Python.
- **Une copie, lue seule** : la requête ne prend aucun verrou sur la base de Zotero.
- **Rien d'écrit quand rien n'a changé** : la copie et la requête ont lieu à chaque collecte,
  mais un extrait identique au dernier du brut n'est pas écrit (`ZoteroSource.fetch`, #139). La
  date des fichiers de Zotero n'est plus comparée : elle ne disait pas si la bibliothèque avait
  changé.

### Mesure : le plan d'exécution

Le plan d'exécution (`EXPLAIN QUERY PLAN`) dit comment SQLite lit chaque table :
- `SEARCH` : une recherche par index ou par clé, qui ne lit que les lignes cherchées ;
- `SCAN` : un parcours de la table entière.

Dans une sous-requête corrélée, rejouée pour chaque document, un `SCAN` relirait toute sa table à
chaque document.

- **Bibliothèque** : une bibliothèque Zotero réelle, 5 documents et 6 surlignages. Elle est lue sur
  une copie faite comme à la collecte (`copy_library`, puis `extract_documents`), ouverte en lecture
  seule.
- **Code** : `main` au commit 236d22c ; SQLite 3.50.4, celui du Python de K-B.
- **Statistiques** : SQLite estime le coût d'une boucle d'après les index disponibles et les
  contraintes du `WHERE`. `ANALYZE` peut affiner ces estimations
  ([The Next-Generation Query Planner](https://www.sqlite.org/queryplanner-ng.html), lu le
  2026-11-03). Cette copie n'a pas de statistiques d'`ANALYZE` : pas de table `sqlite_stat1`.
  Ce relevé vaut pour ce schéma de Zotero, cette requête et SQLite 3.50.4.
- **Temps** : non mesuré ici, car sur 5 documents il ne dirait rien. Il est mesuré sur une
  bibliothèque fabriquée, dans la sous-section suivante.
- **Date** : 2026-11-03.

Commande, depuis la racine du dépôt, avec `KB_ZOTERO_DIR` dans `.env` :
`uv run --env-file .env python -I <script>`. Le script est gardé hors du dépôt :

```python
"""The query plan of EXTRACTION_QUERY on a copy of the library of KB_ZOTERO_DIR, as the collection
reads it. Prints no title, author, key or path, not even in an error: only its type."""

import contextlib
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

from k_b.etl.collected_sources import ZOTERO_DIR_VARIABLE
from k_b.etl.sources import zotero as z


def main() -> None:
    zotero_dir = Path(os.environ[ZOTERO_DIR_VARIABLE])
    with tempfile.TemporaryDirectory(prefix=z.TEMPORARY_DIR_PREFIX) as copy_dir:
        copy_path = z.copy_library(zotero_dir, Path(copy_dir))
        # The collection's own extraction: same opening, same check, its errors without content.
        documents = z.extract_documents(copy_path)
        with contextlib.closing(
            sqlite3.connect(f"{copy_path.as_uri()}?mode=ro", uri=True)
        ) as connection:
            print("sqlite", sqlite3.sqlite_version)
            print("documents", len(documents))
            print("highlights", sum(len(document["highlights"]) for document in documents))
            # With statistics, SQLite also weighs the sizes measured by the last ANALYZE.
            has_statistics = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name = 'sqlite_stat1'"
            ).fetchone()[0]
            print("sqlite_stat1", "yes" if has_statistics else "no")
            if has_statistics:
                for table, index, numbers in connection.execute(
                    "SELECT tbl, idx, stat FROM sqlite_stat1 ORDER BY tbl, idx"
                ):
                    print("  ", table, index, numbers)
            depths = {0: -1}
            for node_id, parent_id, _, detail in connection.execute(
                "EXPLAIN QUERY PLAN " + z.EXTRACTION_QUERY
            ):
                depths[node_id] = depths.get(parent_id, -1) + 1
                print("  " * depths[node_id] + detail)


try:
    main()
except Exception as error:
    # Its message could hold a path or a value of the library: only the type is shown.
    sys.exit(f"failed ({type(error).__name__})")
```

Sortie (les numéros des sous-requêtes sont ceux de SQLite) :

```
sqlite 3.50.4
documents 5
highlights 6
sqlite_stat1 no
SCAN items USING INDEX items_synced
USING ROWID SEARCH ON TABLE deletedItems FOR IN-OPERATOR
SEARCH itemTypes USING INTEGER PRIMARY KEY (rowid=?)
SEARCH libraries USING INTEGER PRIMARY KEY (rowid=?)
CORRELATED SCALAR SUBQUERY 4
  SEARCH itemData USING INDEX sqlite_autoindex_itemData_1 (itemID=?)
  SEARCH fields USING INTEGER PRIMARY KEY (rowid=?)
  SEARCH itemDataValues USING INTEGER PRIMARY KEY (rowid=?)
CORRELATED SCALAR SUBQUERY 5
  SEARCH itemData USING INDEX sqlite_autoindex_itemData_1 (itemID=?)
  SEARCH fields USING INTEGER PRIMARY KEY (rowid=?)
  SEARCH itemDataValues USING INTEGER PRIMARY KEY (rowid=?)
CORRELATED SCALAR SUBQUERY 6
  SEARCH itemData USING INDEX sqlite_autoindex_itemData_1 (itemID=?)
  SEARCH fields USING INTEGER PRIMARY KEY (rowid=?)
  SEARCH itemDataValues USING INTEGER PRIMARY KEY (rowid=?)
CORRELATED SCALAR SUBQUERY 7
  SEARCH itemData USING INDEX sqlite_autoindex_itemData_1 (itemID=?)
  SEARCH fields USING INTEGER PRIMARY KEY (rowid=?)
  SEARCH itemDataValues USING INTEGER PRIMARY KEY (rowid=?)
CORRELATED SCALAR SUBQUERY 8
  USE TEMP B-TREE FOR json_group_array(ORDER BY)
  SEARCH itemCreators USING COVERING INDEX sqlite_autoindex_itemCreators_1 (itemID=?)
  SEARCH creatorTypes USING INTEGER PRIMARY KEY (rowid=?)
  SEARCH creators USING INTEGER PRIMARY KEY (rowid=?)
CORRELATED SCALAR SUBQUERY 9
  USE TEMP B-TREE FOR json_group_array(ORDER BY)
  SEARCH itemTags USING INDEX sqlite_autoindex_itemTags_1 (itemID=?)
  SEARCH tags USING INTEGER PRIMARY KEY (rowid=?)
CORRELATED SCALAR SUBQUERY 11
  USE TEMP B-TREE FOR json_group_array(ORDER BY)
  SEARCH itemAttachments USING INDEX itemAttachments_parentItemID (parentItemID=?)
  USING ROWID SEARCH ON TABLE deletedItems FOR IN-OPERATOR
  SEARCH attachment USING INTEGER PRIMARY KEY (rowid=?)
CORRELATED SCALAR SUBQUERY 14
  USE TEMP B-TREE FOR json_group_array(ORDER BY)
  SEARCH itemAttachments USING INDEX itemAttachments_parentItemID (parentItemID=?)
  USING ROWID SEARCH ON TABLE deletedItems FOR IN-OPERATOR
  SEARCH attachment USING INTEGER PRIMARY KEY (rowid=?)
  SEARCH itemAnnotations USING INDEX itemAnnotations_parentItemID (parentItemID=?)
  USING ROWID SEARCH ON TABLE deletedItems FOR IN-OPERATOR
  SEARCH annotation USING INTEGER PRIMARY KEY (rowid=?)
USE TEMP B-TREE FOR ORDER BY
```

| Partie de la requête | Table | Accès | Par |
|---|---|---|---|
| CTE `document` | `items` | `SCAN`, une fois | parcours complet, par l'index `items_synced` de Zotero |
| CTE `document` | `itemTypes`, `libraries` | `SEARCH` | clé (`rowid`) |
| corbeille (`NOT IN`), partout | `deletedItems` | `SEARCH` | clé (`rowid`) |
| titre, date, URL, `archiveID` (4 à 7) | `itemData` | `SEARCH` | index de sa clé primaire, sur `itemID` |
| titre, date, URL, `archiveID` (4 à 7) | `fields`, `itemDataValues` | `SEARCH` | clé (`rowid`) |
| auteurs (8) | `itemCreators` | `SEARCH` | index couvrant de sa clé primaire, sur `itemID` |
| auteurs (8) | `creatorTypes`, `creators` | `SEARCH` | clé (`rowid`) |
| étiquettes (9) | `itemTags` | `SEARCH` | index de sa clé primaire, sur `itemID` |
| étiquettes (9) | `tags` | `SEARCH` | clé (`rowid`) |
| PDF (11) et surlignages (14) | `itemAttachments` | `SEARCH` | index `itemAttachments_parentItemID`, sur `parentItemID` |
| PDF (11) et surlignages (14) | `items` (alias `attachment`) | `SEARCH` | clé (`rowid`) |
| surlignages (14) | `itemAnnotations` | `SEARCH` | index `itemAnnotations_parentItemID`, sur `parentItemID` |
| surlignages (14) | `items` (alias `annotation`) | `SEARCH` | clé (`rowid`) |

Lecture :

- **Un seul `SCAN`, celui de `items`, une fois pour toute la requête.** Il est attendu : un
  document se reconnaît à son type, à sa bibliothèque et à son absence de la corbeille, donc chaque
  item est examiné. SQLite le fait par l'index `items_synced` de Zotero. Pourquoi cet index plutôt
  que la table, ce relevé ne l'établit pas.
- **Tout le reste est `SEARCH`.** Les huit sous-requêtes corrélées sont rejouées pour chaque
  document. Chacune entre par la clé du document dans un index : `itemID=?` pour les champs, les
  auteurs et les étiquettes, `parentItemID=?` pour les PDF. Les surlignages sont ensuite cherchés
  par la clé de leur PDF (`itemAnnotations.parentItemID`). Pour chaque document, SQLite lit donc
  ses champs, ses auteurs, ses étiquettes, ses PDF et ses surlignages, sans relire les tables
  entières.
- **La CTE `field_value` n'est pas bâtie à part.** `itemData`, `fields` et `itemDataValues`
  apparaissent dans chacune des sous-requêtes de champ (4 à 7) : SQLite y fond la CTE, au lieu de
  bâtir d'abord la table des champs de toute la bibliothèque. Chaque recherche lit les champs du
  document (`itemID=?`), et le filtre sur `fields.fieldName` n'en garde que quatre.
- **La corbeille** : `NOT IN (SELECT itemID FROM deletedItems)` devient une recherche par clé dans
  `deletedItems` (`USING ROWID SEARCH … FOR IN-OPERATOR`).
- **Les cinq `USE TEMP B-TREE` sont des tris** :
  - un par liste triée dans son agrégat (auteurs, étiquettes, PDF, surlignages), sur les lignes
    d'un seul document ;
  - le tri final, par `dateAdded` puis `itemID`.

  Le plan ne dit pas pourquoi SQLite trie ces lignes au lieu de suivre un index.

**Mise en regard.** La bibliothèque inventée des tests (`tests/fixtures/zotero_extract.sql`)
reprend les tables de Zotero sans les index que Zotero crée à part (`CREATE INDEX`). Elle garde
ceux de leurs clés primaires et de leurs `UNIQUE`. On y lance la même requête, avec le même
SQLite :
- la sous-requête des PDF passe à `SCAN itemAttachments` ;
- celle des surlignages passe à `SCAN itemAnnotations`.

Ces deux tables seraient alors parcourues en entier pour chaque document. Les index
`itemAttachments_parentItemID` et `itemAnnotations_parentItemID` de Zotero changent ces parcours
en recherches. La requête en profite parce qu'elle relie un PDF à son document, et un surlignage
à son PDF, par `parentItemID`.

Ce que le plan montre de chaque économie de la liste :

| Économie | Ce que montre le plan |
|---|---|
| Une instruction pour toute la bibliothèque | une instruction, un seul parcours de `items`, chaque liste en sous-requête corrélée ; l'écart avec une requête par document est mesuré dans la sous-section suivante |
| Chaque liste cherchée par la clé du document | montré : `SEARCH` sur `itemID` ou `parentItemID`, aucun autre `SCAN` |
| Seuls les champs utiles nommés | rien : un plan ne dit pas les colonnes lues |
| Une copie, lue seule | rien : c'est un fait du code (`copy_library`, `extract_documents`) |
| Rien d'écrit quand rien n'a changé | rien : c'est un fait du code (`ZoteroSource.fetch`) |

### Mesure : le temps, une instruction contre une requête par document

La mesure du plan ne donne pas de temps : sur 5 documents, il ne dirait rien. Celle-ci chronomètre
`EXTRACTION_QUERY` contre ce qu'elle remplace : une requête par document, lancée depuis Python. La
comparaison porte sur deux bibliothèques fabriquées, de 1 000 et de 10 000 documents. Aucune donnée
réelle n'y entre.

#### Le schéma

C'est la structure des 14 tables lues et de `itemNotes`, avec leurs 15 index créés à part
(`CREATE INDEX`). Elle est relevée sur une copie d'une base Zotero réelle : schéma `userdata` en version 130,
pages de 32 768 octets.

Seuls les `CREATE TABLE` et les `CREATE INDEX` sont relevés : ni ligne, ni trigger, ni vue. Les
triggers n'agissent qu'à l'écriture, et les vues ne sont pas lues.

La bibliothèque inventée des tests ne sert pas ici : elle n'a pas ces index (« Mise en regard »,
mesure précédente).

#### Les données inventées

Pour chaque document de la bibliothèque personnelle :

| Élément | Par document |
|---|---|
| champs (`itemData`) | 10 : les 4 lus (`title`, `date`, `url`, `archiveID`) et 6 autres |
| créateurs | 3 auteurs et 1 éditeur, pris parmi 2 000 créateurs |
| étiquettes | 4, prises parmi 300 |
| pièces jointes | 1 PDF rangé par Zotero (`storage:`), 1 PDF lié hors de Zotero, 1 capture HTML |
| annotations du PDF | 6 surlignages et 2 annotations d'un autre type |
| notes | 1 |

En plus :
- 5 % des documents, 2 % des PDF et 2 % des annotations sont à la corbeille ;
- une bibliothèque de groupe ajoute 10 % de documents, avec leurs pièces.

Chaque filtre de la requête a donc des lignes à écarter.

Les créateurs, les étiquettes et les dates sont pris dans des réservoirs partagés, parce que le
schéma veut uniques ses créateurs, ses étiquettes et ses valeurs. Les autres champs (titre, URL…)
sont propres à chaque document.

`synced` vaut 0 partout, donc le parcours de `items` par l'index `items_synced` suit l'ordre de
`itemID`, et `dateAdded` croît avec `itemID`. Les deux façons de faire lancent donc leurs
recherches dans le même ordre de documents.

#### La variante comparée

- D'abord, la liste des documents : les CTE de `EXTRACTION_QUERY`, puis `SELECT document.itemID`
  avec son `ORDER BY`.
- Puis, pour chaque document, `EXTRACTION_QUERY` avec `WHERE document.itemID = ?` à la place de
  son `ORDER BY`.

Seuls `SELECT document.itemID` et `WHERE document.itemID = ?` sont écrits à la main ; le reste
est découpé dans la constante. Le script
vérifie que les deux façons de faire rendent les mêmes lignes, et que le plan de la variante n'a
aucun `SCAN`.

#### Le chronomètre

- Une connexion en lecture seule, avec `sqlite3.Row`, comme `extract_documents`.
- Un passage de chauffe de chaque façon de faire, puis 7 passages. L'ordre alterne d'un passage à
  l'autre : l'instruction unique d'abord, puis la variante d'abord, et ainsi de suite. Le
  ramasse-miettes de Python est arrêté pendant la mesure.
- Le temps couvre l'exécution et la lecture des lignes, requête de liste comprise pour la variante.
  Il ne couvre ni la fabrication de la base, ni `json.loads`.

#### Conditions

- **Machine** : Apple M4, 16 Go, macOS (Darwin 25.6.0).
- **Logiciels** : Python 3.13.13, SQLite 3.50.4.
- **Code** : `main` au commit bd433db.
- **Date** : 2026-11-03, 16:10 UTC.

#### Commandes et scripts

Depuis la racine du dépôt :
1. relever le schéma, sur une copie de la bibliothèque de `KB_ZOTERO_DIR` :
   `uv run --env-file .env python -I <relevé> <fichier>` ;
2. mesurer, sans `.env` : `uv run python -I <mesure> <fichier>`.

`<relevé>` et `<mesure>` sont les deux scripts ci-dessous, gardés hors du dépôt. `<fichier>` est le
fichier JSON où le relevé écrit le schéma, et où la mesure le lit.

<details><summary>Script du relevé du schéma</summary>

```python
"""Write the structure of the tables EXTRACTION_QUERY reads, taken from a copy of the library of
KB_ZOTERO_DIR: their CREATE TABLE and CREATE INDEX, the page size and the version of Zotero's
schema. No row of the library is written. An error shows only its type."""

import contextlib
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

from k_b.etl.collected_sources import ZOTERO_DIR_VARIABLE
from k_b.etl.sources import zotero as z

# The 14 tables the query reads, and itemNotes, which it must leave alone.
TABLES = (
    "libraries", "itemTypes", "items", "deletedItems", "fields", "itemDataValues", "itemData",
    "creators", "creatorTypes", "itemCreators", "tags", "itemTags", "itemAttachments",
    "itemAnnotations", "itemNotes",
)


def main(output: Path) -> None:
    zotero_dir = Path(os.environ[ZOTERO_DIR_VARIABLE])
    with tempfile.TemporaryDirectory(prefix=z.TEMPORARY_DIR_PREFIX) as copy_dir:
        copy_path = z.copy_library(zotero_dir, Path(copy_dir))
        with contextlib.closing(
            sqlite3.connect(f"{copy_path.as_uri()}?mode=ro", uri=True)
        ) as connection:
            z.check_integrity(connection)
            # Tables first, then indexes; no trigger, no view, no automatic index (sql is NULL).
            statements = [
                sql
                for (sql,) in connection.execute(
                    f"SELECT sql FROM sqlite_master WHERE type IN ('table', 'index')"
                    f" AND sql IS NOT NULL AND tbl_name IN ({', '.join('?' * len(TABLES))})"
                    " ORDER BY type = 'index', name",
                    TABLES,
                )
            ]
            page_size = connection.execute("PRAGMA page_size").fetchone()[0]
            try:
                schema_version = connection.execute(
                    "SELECT version FROM version WHERE schema = 'userdata'"
                ).fetchone()[0]
            except sqlite3.OperationalError:
                schema_version = None
    output.write_text(
        json.dumps(
            {"userdata_version": schema_version, "page_size": page_size, "statements": statements},
            indent=2,
        )
        + "\n"
    )
    print("tables", sum(sql.startswith("CREATE TABLE") for sql in statements))
    print("indexes", sum(sql.startswith("CREATE INDEX") for sql in statements))
    print("page_size", page_size)
    print("userdata_version", schema_version)


try:
    main(Path(sys.argv[1]))
except Exception as error:
    # Its message could hold a path or a value of the library: only the type is shown.
    sys.exit(f"failed ({type(error).__name__})")
```

</details>

<details><summary>Script de la mesure</summary>

```python
"""Time EXTRACTION_QUERY against one query per document, on libraries fabricated from a schema
written by dump_zotero_schema.py. Every value is invented; nothing of a real library is read."""

import contextlib
import gc
import json
import platform
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from k_b.etl.sources import zotero as z

SIZES = (1_000, 10_000)
RUNS = 7
# For each document of the user's library.
OTHER_FIELDS = ("abstractNote", "publicationTitle", "volume", "issue", "pages", "language")
AUTHORS_PER_DOCUMENT = 3
TAGS_PER_DOCUMENT = 4
HIGHLIGHTS_PER_PDF = 6
OTHER_ANNOTATIONS_PER_PDF = 2
# One in ..._TRASH_EVERY documents, PDFs and annotations goes to the trash: 5 %, 2 %, 2 %.
DOCUMENT_TRASH_EVERY = 20
PIECE_TRASH_EVERY = 50
# The group library, never read, holds this share of documents more, with their pieces.
GROUP_SHARE = 0.10
# Pools shared by the documents: itemDataValues.value, tags.name and creators are UNIQUE.
AUTHOR_POOL = 2_000
TAG_POOL = 300
YEAR_POOL = 30

# The variant is cut from the text of EXTRACTION_QUERY, not written by hand: same CTEs, same
# columns, same filters; only the last FROM changes, from every document to one.
FIRST_COLUMN = "\nSELECT\n    document.key,"
ORDER_CLAUSE = "ORDER BY document.dateAdded, document.itemID\n"
LAST_FROM = "FROM document\n" + ORDER_CLAUSE
for anchor in (FIRST_COLUMN, ORDER_CLAUSE, LAST_FROM):
    assert z.EXTRACTION_QUERY.count(anchor) == 1, anchor
IDS_QUERY = (
    z.EXTRACTION_QUERY.split(FIRST_COLUMN)[0]
    + "\nSELECT document.itemID\nFROM document\n"
    + ORDER_CLAUSE
)
ONE_DOCUMENT_QUERY = z.EXTRACTION_QUERY.replace(
    LAST_FROM, "FROM document\nWHERE document.itemID = ?\n"
)


class Library:
    """Fabricates rows, with keys and identifiers that never repeat."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.next_item_id = 1
        self.second = 0
        self.value_ids: dict[str, int] = {}
        self.counts = {"documents": 0, "highlights": 0}

    def add_item(self, library_id: int, type_id: int) -> int:
        item_id = self.next_item_id
        self.next_item_id += 1
        # dateAdded grows with itemID: both variants read the documents in the same order.
        self.second += 1
        date_added = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(1_600_000_000 + self.second))
        self.connection.execute(
            "INSERT INTO items (itemID, itemTypeID, dateAdded, dateModified, clientDateModified,"
            " libraryID, key, synced) VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
            (item_id, type_id, date_added, date_added, date_added, library_id, f"K{item_id:07d}"),
        )
        return item_id

    def value_id(self, value: str) -> int:
        if value not in self.value_ids:
            cursor = self.connection.execute(
                "INSERT INTO itemDataValues (value) VALUES (?)", (value,)
            )
            self.value_ids[value] = cursor.lastrowid or 0
        return self.value_ids[value]

    def trash(self, item_id: int) -> None:
        self.connection.execute("INSERT INTO deletedItems (itemID) VALUES (?)", (item_id,))

    def add_attachment(
        self, library_id: int, parent_id: int, content_type: str, path: str, link_mode: int
    ) -> int:
        item_id = self.add_item(library_id, TYPE_IDS["attachment"])
        self.connection.execute(
            "INSERT INTO itemAttachments (itemID, parentItemID, linkMode, contentType, path)"
            " VALUES (?, ?, ?, ?, ?)",
            (item_id, parent_id, link_mode, content_type, path),
        )
        return item_id

    def add_document(self, library_id: int, number: int) -> None:
        read = library_id == USER_LIBRARY_ID
        document_id = self.add_item(library_id, TYPE_IDS["journalArticle"])
        trashed = number % DOCUMENT_TRASH_EVERY == 0
        if trashed:
            self.trash(document_id)
        fields = {
            "title": f"Invented title {number}",
            "date": f"{2000 + number % YEAR_POOL}-01-01 {2000 + number % YEAR_POOL}-01-01",
            "url": f"https://example.org/paper/{number}",
            "archiveID": f"arXiv:2601.{number:05d}",
        }
        fields.update({name: f"Invented {name} {number}" for name in OTHER_FIELDS})
        for name, value in fields.items():
            self.connection.execute(
                "INSERT INTO itemData (itemID, fieldID, valueID) VALUES (?, ?, ?)",
                (document_id, FIELD_IDS[name], self.value_id(value)),
            )
        creators = [
            (1 + (number * AUTHORS_PER_DOCUMENT + order) % AUTHOR_POOL, CREATOR_TYPE_IDS["author"])
            for order in range(AUTHORS_PER_DOCUMENT)
        ] + [(1 + (number * 7) % AUTHOR_POOL, CREATOR_TYPE_IDS["editor"])]
        for order, (creator_id, creator_type_id) in enumerate(dict.fromkeys(creators)):
            self.connection.execute(
                "INSERT INTO itemCreators (itemID, creatorID, creatorTypeID, orderIndex)"
                " VALUES (?, ?, ?, ?)",
                (document_id, creator_id, creator_type_id, order),
            )
        for tag_number in {(number * TAGS_PER_DOCUMENT + n) % TAG_POOL for n in range(TAGS_PER_DOCUMENT)}:
            self.connection.execute(
                "INSERT INTO itemTags (itemID, tagID, type) VALUES (?, ?, ?)",
                (document_id, 1 + tag_number, tag_number % 2),
            )
        pdf_id = self.add_attachment(
            library_id, document_id, "application/pdf", f"storage:paper-{number}.pdf", 1
        )
        pdf_trashed = number % PIECE_TRASH_EVERY == 1
        if pdf_trashed:
            self.trash(pdf_id)
        # Not read: a linked PDF outside Zotero's storage, an HTML snapshot, a note.
        self.add_attachment(
            library_id, document_id, "application/pdf", f"/invented/linked-{number}.pdf", 2
        )
        self.add_attachment(
            library_id, document_id, "text/html", f"storage:snapshot-{number}.html", 1
        )
        note_id = self.add_item(library_id, TYPE_IDS["note"])
        self.connection.execute(
            "INSERT INTO itemNotes (itemID, parentItemID, note, title) VALUES (?, ?, ?, ?)",
            (note_id, document_id, "<p>Invented note</p>", "Invented note"),
        )
        for order in range(HIGHLIGHTS_PER_PDF + OTHER_ANNOTATIONS_PER_PDF):
            highlight = order < HIGHLIGHTS_PER_PDF
            annotation_id = self.add_item(library_id, TYPE_IDS["annotation"])
            self.connection.execute(
                "INSERT INTO itemAnnotations (itemID, parentItemID, type, text, comment, color,"
                " pageLabel, sortIndex, position, isExternal) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                (
                    annotation_id, pdf_id, 1 if highlight else 2,
                    f"Invented highlighted text {number}-{order}", None, "#ffd400",
                    str(1 + order), f"{order:05d}|000000|00000", '{"pageIndex": 0, "rects": []}',
                ),
            )
            annotation_trashed = (
                number * (HIGHLIGHTS_PER_PDF + OTHER_ANNOTATIONS_PER_PDF) + order
            ) % PIECE_TRASH_EVERY == 3
            if annotation_trashed:
                self.trash(annotation_id)
            if read and highlight and not (trashed or pdf_trashed or annotation_trashed):
                self.counts["highlights"] += 1
        if read and not trashed:
            self.counts["documents"] += 1


USER_LIBRARY_ID, GROUP_LIBRARY_ID = 1, 2
TYPE_IDS = {"annotation": 1, "attachment": 3, "journalArticle": 22, "note": 28}
FIELD_IDS = {
    name: number
    for number, name in enumerate(("title", "date", "url", "archiveID", *OTHER_FIELDS), 1)
}
CREATOR_TYPE_IDS = {"author": 1, "editor": 2}


def build(schema: dict[str, Any], path: Path, size: int) -> dict[str, int]:
    connection = sqlite3.connect(path)
    try:
        connection.execute(f"PRAGMA page_size = {int(schema['page_size'])}")
        connection.execute("PRAGMA journal_mode = WAL")
        for statement in schema["statements"]:
            connection.execute(statement)
        connection.executemany(
            "INSERT INTO libraries (libraryID, type, editable, filesEditable) VALUES (?, ?, 1, 1)",
            [(USER_LIBRARY_ID, "user"), (GROUP_LIBRARY_ID, "group")],
        )
        connection.executemany(
            "INSERT INTO itemTypes (itemTypeID, typeName) VALUES (?, ?)",
            [(type_id, name) for name, type_id in TYPE_IDS.items()],
        )
        connection.executemany(
            "INSERT INTO fields (fieldID, fieldName) VALUES (?, ?)",
            [(field_id, name) for name, field_id in FIELD_IDS.items()],
        )
        connection.executemany(
            "INSERT INTO creatorTypes (creatorTypeID, creatorType) VALUES (?, ?)",
            [(type_id, name) for name, type_id in CREATOR_TYPE_IDS.items()],
        )
        connection.executemany(
            "INSERT INTO creators (creatorID, firstName, lastName, fieldMode) VALUES (?, ?, ?, 0)",
            [(n, f"First{n}", f"Last{n}") for n in range(1, AUTHOR_POOL + 1)],
        )
        connection.executemany(
            "INSERT INTO tags (tagID, name) VALUES (?, ?)",
            [(n, f"invented-tag-{n}") for n in range(1, TAG_POOL + 1)],
        )
        library = Library(connection)
        for number in range(1, size + 1):
            library.add_document(USER_LIBRARY_ID, number)
        for number in range(size + 1, size + 1 + int(size * GROUP_SHARE)):
            library.add_document(GROUP_LIBRARY_ID, number)
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        counts = dict(library.counts)
        counts["items"] = connection.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        return counts
    finally:
        connection.close()


def one_statement(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(z.EXTRACTION_QUERY).fetchall()


def one_query_per_document(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    item_ids = [row[0] for row in connection.execute(IDS_QUERY)]
    return [connection.execute(ONE_DOCUMENT_QUERY, (item_id,)).fetchone() for item_id in item_ids]


def plan_of(
    connection: sqlite3.Connection, query: str, parameters: tuple[int, ...] = ()
) -> list[str]:
    lines, depths = [], {0: -1}
    for node_id, parent_id, _, detail in connection.execute(
        "EXPLAIN QUERY PLAN " + query, parameters
    ):
        depths[node_id] = depths.get(parent_id, -1) + 1
        lines.append("  " * depths[node_id] + detail)
    return lines


def main(schema_path: Path, sizes: tuple[int, ...]) -> None:
    schema = json.loads(schema_path.read_text())
    print("machine", platform.machine(), platform.system(), platform.release())
    print("python", platform.python_version(), "sqlite", sqlite3.sqlite_version)
    print("userdata_version", schema["userdata_version"], "page_size", schema["page_size"])
    variants = {"one_statement": one_statement, "one_query_per_document": one_query_per_document}
    for size in sizes:
        with tempfile.TemporaryDirectory(prefix="kb-zotero-timing-") as directory:
            path = Path(directory) / "zotero.sqlite"
            counts = build(schema, path, size)
            with contextlib.closing(
                sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
            ) as connection:
                connection.row_factory = sqlite3.Row
                assert connection.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE name = 'sqlite_stat1'"
                ).fetchone()[0] == 0
                # The first run of each variant warms the cache and checks the rows.
                rows = one_statement(connection)
                assert [tuple(row) for row in one_query_per_document(connection)] == [
                    tuple(row) for row in rows
                ]
                assert len(rows) == counts["documents"]
                assert sum(len(json.loads(row["highlights"])) for row in rows) == counts["highlights"]
                print()
                print("size", size, "items", counts["items"], "documents", counts["documents"],
                      "highlights", counts["highlights"])
                if size == sizes[-1]:
                    print("plan of EXTRACTION_QUERY:")
                    print("\n".join(plan_of(connection, z.EXTRACTION_QUERY)))
                    one_document_plan = plan_of(connection, ONE_DOCUMENT_QUERY, (1,))
                    assert not any(line.strip().startswith("SCAN") for line in one_document_plan)
                    print("plan of the query for one document:")
                    print("\n".join(one_document_plan))
                durations: dict[str, list[float]] = {name: [] for name in variants}
                gc.disable()
                try:
                    for run in range(RUNS):
                        order = list(variants) if run % 2 == 0 else list(reversed(variants))
                        for name in order:
                            start = time.perf_counter()
                            variants[name](connection)
                            durations[name].append(time.perf_counter() - start)
                finally:
                    gc.enable()
                for name, values in durations.items():
                    print(name, "median_ms", round(statistics.median(values) * 1000, 1),
                          "runs_ms", [round(value * 1000, 1) for value in values])
                ratio = statistics.median(durations["one_query_per_document"]) / statistics.median(
                    durations["one_statement"]
                )
                print("ratio", round(ratio, 2))


main(Path(sys.argv[1]), tuple(int(size) for size in sys.argv[2:]) or SIZES)
```

</details>

#### Sorties

Sortie du relevé :

```
tables 15
indexes 15
page_size 32768
userdata_version 130
```

Sortie de la mesure. Les deux plans, imprimés pour 10 000 documents, sont remplacés ici par `[…]` ;
ils sont lus plus bas :

```
machine arm64 Darwin 25.6.0
python 3.13.13 sqlite 3.50.4
userdata_version 130 page_size 32768

size 1000 items 14300 documents 950 highlights 5470
one_statement median_ms 12.6 runs_ms [14.4, 12.6, 12.6, 12.6, 12.5, 12.4, 12.5]
one_query_per_document median_ms 23.6 runs_ms [24.2, 24.0, 23.3, 23.6, 23.6, 23.5, 23.6]
ratio 1.88

size 10000 items 143000 documents 9500 highlights 54700
plan of EXTRACTION_QUERY:
[…]
plan of the query for one document:
[…]
one_statement median_ms 145.5 runs_ms [144.0, 145.5, 147.8, 142.7, 151.4, 145.0, 160.3]
one_query_per_document median_ms 269.1 runs_ms [270.5, 269.1, 267.4, 266.9, 271.3, 271.1, 264.9]
ratio 1.85
```

#### Résultats

| Documents lus | Items dans la base | `EXTRACTION_QUERY` (médiane) | Une requête par document (médiane) | Rapport |
|---|---|---|---|---|
| 950 | 14 300 | 12,6 ms | 23,6 ms | 1,88 |
| 9 500 | 143 000 | 145,5 ms | 269,1 ms | 1,85 |

#### Lecture

- **Une seule instruction va environ 1,9 fois plus vite** qu'une requête par document, aux deux
  tailles. Chaque passage reste à 15 % au plus de sa médiane ; le plus éloigné est un passage de
  l'instruction unique, 14,4 ms contre 12,6.
- **Le temps des deux grandit comme le nombre de documents.** De 950 à 9 500 documents lus (× 10),
  `EXTRACTION_QUERY` passe de 12,6 à 145,5 ms (× 11,5), et la variante de 23,6 à 269,1 ms
  (× 11,4). Aucune des deux ne relit une table entière par document.
- **Le plan de `EXTRACTION_QUERY` sur 10 000 documents est identique, ligne pour ligne, à celui
  relevé sur 5 documents** dans la mesure précédente (vérifié par `diff`). Ce n'est pas une preuve
  que le plan reste stable ; c'est un contrôle : la base fabriquée a bien le schéma de la vraie. Le
  schéma relevé dit aussi ce qu'est `items_synced` : un index sur `items(synced)`. Pourquoi SQLite
  le préfère à la table pour parcourir `items`, ce relevé ne le dit pas.
- **Le plan de la variante ne diffère que de deux lignes** (vérifié par `diff`) :
  - `SEARCH items USING INTEGER PRIMARY KEY (rowid=?)` au lieu de
    `SCAN items USING INDEX items_synced` ;
  - pas de `USE TEMP B-TREE FOR ORDER BY`, puisque c'est la requête de liste qui trie.

  Les deux façons de faire lancent donc les mêmes recherches. Ce qui les sépare, c'est le nombre
  d'instructions : une seule, ou une par document en plus de la liste.
- **Ce qui joue pour la variante.** Le module `sqlite3` de Python garde en cache les instructions
  préparées d'une connexion, « to avoid parsing overhead » (`cached_statements`, 128 par défaut,
  [documentation de sqlite3](https://docs.python.org/3/library/sqlite3.html), lue le 2026-11-03).
  Le texte de la requête par document n'est donc compilé qu'une fois. L'écart n'est pas décomposé
  par poste : la mesure ne dit pas quelle part revient à chaque instruction lancée, à la boucle
  Python ou à la création d'un curseur par document.

  Ce qui joue pour `EXTRACTION_QUERY` en sens inverse : elle trie à la fin ses lignes entières,
  listes JSON comprises, et ce coût est compté dans son temps.
- **Portée.** Ces temps valent pour ces données inventées, sur cette machine, cache chaud. Ils ne
  disent pas le temps sur la vraie bibliothèque, ni sur une autre machine. Ils ne comparent pas
  non plus `EXTRACTION_QUERY` à une variante qui ferait une requête par champ et par liste.

### Ce qu'elle suppose

- Une version minimale de SQLite pour `ORDER BY` à l'intérieur d'un agrégat : elle est donnée par
  la docstring de `ZoteroQueryFailedError`.
- Le schéma de Zotero : s'il change, la requête échoue (`ZoteroQueryFailedError`). Le message
  nomme la table ou la colonne absente, ou la syntaxe refusée (`MESSAGE_ABOUT_THE_QUERY`) ; sinon,
  il donne le type de l'erreur et le nom que SQLite lui donne (`describe_query_error`).

## 2. GH Archive sur BigQuery — `TRENDS_QUERY`

Fichier : `src/k_b/etl/sources/gh_archive.py`. Spécifications de la source :
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
  la tient égale à `TABLE_PREFIX` (`tests/etl/sources/test_gh_archive.py`).
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
- `@window_days` : `GH_ARCHIVE_WINDOW_DAYS` ;
- `@top_size` : `GH_ARCHIVE_TOP_SIZE`.

Les jours et les fenêtres changent d'une collecte à l'autre. `@window_days` et `@top_size` ne
changent pas : ils sont des paramètres pour que `GH_ARCHIVE_WINDOW_DAYS` et `GH_ARCHIVE_TOP_SIZE` ne soient écrits qu'à un
endroit (un test de `tests/etl/sources/test_gh_archive.py` vérifie que la taille du classement
n'est pas dans le texte de la requête). Restent écrits dans le texte : la table, les types d'événement,
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
- **Un rattrapage borné** : `GH_ARCHIVE_MAX_CATCH_UP_WINDOWS` fenêtres au plus.
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

from k_b.etl.sources import gh_archive as g

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

Chaque source construit ses requêtes dans son module. Les réglages de la veille (mots-clés d'arXiv,
éditions TLDR, dépôts suivis, seuils et taille des tops, délai réseau…) sont dans
`src/k_b/core/config.py`, chacun préfixé par sa source (#123) ; les faits des API (URL, tailles de
page) et les plafonds restent dans le module de la source. Leur justification est dans la section de
la source de [specs-collecte.md](specs-collecte.md). Chaque téléchargement passe par `download`
(`src/k_b/etl/http_download.py`) : délai (`HTTP_TIMEOUT_SECONDS`), taille maximale, préfixe d'URL de
confiance, un seul nouvel essai après un 429, un 5xx ou un échec de connexion
(`src/k_b/etl/http_retry.py` ; l'API GitHub attend 60 s après un 429 sans `Retry-After`)
([règles communes](specs-collecte.md#règles-communes)).

| Source | Fichier | Construite par | Paramètres | Filtre à la requête | Spécifications |
|---|---|---|---|---|---|
| arXiv | `src/k_b/etl/sources/arxiv.py` | `ArxivSource.fetch`, `build_search_query`, `download_papers` | URL `API_URL` ; `search_query` ; `start` ; `max_results` (`PAPERS_PER_PAGE`) ; `sortBy` et `sortOrder` (date de soumission, croissante) ; réponse plafonnée par `MAX_RESPONSE_BYTES` | `cat:cs.CR AND cat:cs.AI`, un mot-clé de `ARXIV_KEYWORDS` dans le résumé (`abs:`), `submittedDate` depuis la dernière collecte moins `ARXIV_ANNOUNCEMENT_DELAY_MARGIN` (première collecte : `ARXIV_FIRST_COLLECTION_START`) | [API arXiv](specs-collecte.md#api-arxiv--service-web) |
| GitHub, releases | `src/k_b/etl/sources/github/releases.py` | `GithubReleasesSource.fetch` | chemin `repos/<dépôt>/releases`, dépôt pris dans `GITHUB_TRACKED_REPOSITORIES` (`core/config.py`) ; `per_page` (`RELEASES_PER_PAGE`) | aucun : `fetch` compare les dates de la page à la dernière collecte | [API GitHub](specs-collecte.md#api-github--service-web) |
| GitHub, alertes | `src/k_b/etl/sources/github/advisories.py` | `GithubAdvisoriesSource.fetch` | chemin `advisories` ; `type=reviewed` ; `ecosystem` (un de `GITHUB_ECOSYSTEMS`) ; `affects` ; `sort=updated` ; `per_page` (`ADVISORIES_PER_PAGE`) ; `updated`, seulement s'il y a une dernière collecte | `affects` : les paquets suivis, donnés par `list_packages_by_ecosystem` (`etl/source_kinds.py`) ; `updated` : mises à jour depuis la veille de la dernière collecte (l'API n'a pas de filtre sur la date de revue, et la mise à jour n'est jamais antérieure à la revue), puis `fetch` compare les dates de revue à la dernière collecte | [API GitHub](specs-collecte.md#api-github--service-web) |
| GitHub, dépôts les plus étoilés | `src/k_b/etl/sources/github/most_starred.py` | `GithubMostStarredSource.fetch` | chemin `search/repositories` ; `q` (`GITHUB_MOST_STARRED_SEARCH_QUERY`) ; `sort=stars` ; `order=desc` ; `per_page` (`GITHUB_RANKING_SIZE`) | aucun : la recherche exige un critère, et `GITHUB_MOST_STARRED_SEARCH_QUERY` garde tout le classement (commentaire de la constante) | [API GitHub](specs-collecte.md#api-github--service-web) |
| GitHub, dépôts les plus forkés | `src/k_b/etl/sources/github/most_forked.py` | `GithubMostForkedSource.fetch` | chemin `search/repositories` ; `q` (`GITHUB_MOST_FORKED_SEARCH_QUERY`) ; `sort=forks` ; `order=desc` ; `per_page` (`GITHUB_RANKING_SIZE`) | aucun : la recherche exige un critère, et `GITHUB_MOST_FORKED_SEARCH_QUERY` garde tout le classement (commentaire de la constante) | [API GitHub](specs-collecte.md#api-github--service-web) |
| GitHub, commun aux quatre | `src/k_b/etl/sources/github/api.py` | `get_from_github_api` | URL `API_URL` (`core/github_api.py`, partagée avec l'API IA) ; en-têtes `Accept` et `X-GitHub-Api-Version` (`API_VERSION`) ; jeton (`TOKEN_VARIABLE`) en `Authorization`, jamais transmis à une redirection ; réponse plafonnée par `MAX_RESPONSE_BYTES` | — | [jeton-github.md](jeton-github.md) |
| CISA KEV | `src/k_b/etl/sources/cisa_kev.py` | `CisaKevSource.fetch` | URL `CATALOG_URL` ; en-tête `If-Modified-Since` (date de la dernière collecte), seulement s'il y en a une ; réponse plafonnée par `MAX_CATALOG_BYTES`, servie sous `TRUSTED_URL_PREFIX` | aucun : le catalogue entier, ou rien s'il n'a pas changé (`HTTP_NOT_MODIFIED`) | [Catalogue CISA KEV](specs-collecte.md#catalogue-cisa-kev--fichier) |
| tldr.tech | `src/k_b/etl/sources/tldr.py` | `TldrSource.fetch` | URL `SITE_URL` + édition (une de `TLDR_TRACKED_EDITIONS`) + jour ; jours donnés par `list_days_to_collect` (première collecte : `TLDR_FIRST_COLLECTION_DAYS`) ; `TLDR_PAUSE_BETWEEN_PAGES_SECONDS` entre deux pages ; page plafonnée par `MAX_PAGE_BYTES` | le jour, dans l'URL | [tldr.tech](specs-collecte.md#tldrtech--scraping) |

Par défaut, K-B filtre à la lecture, pas à la requête
([règles communes](specs-collecte.md#règles-communes)). Deux exceptions décidées posent le filtre
dans la requête : arXiv et les alertes GitHub ; leur raison est dans la section de chaque source
des specs. Deux autres économies : une requête conditionnelle (`If-Modified-Since`), qui ne
retélécharge pas un catalogue inchangé, et une pause entre deux pages de tldr.tech.
