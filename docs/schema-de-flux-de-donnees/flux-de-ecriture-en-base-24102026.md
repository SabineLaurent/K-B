# Flux de données de l'écriture en base

Instantané du code au commit `4626e24` (`main`, 2026-10-24). Fondé sur la lecture du code seul :
aucune commande de K-B n'a été exécutée. Les chemins sont relatifs à `src/k_b/` ; les numéros de
ligne valent pour ce commit.

Flux générique, valable pour toutes les sources : de `import_items`, qui reçoit les fichiers lus,
jusqu'au commit de la transaction et au journal d'import. Vue d'ensemble :
[flux complet](flux-de-donnees-complet-24102026.md). Avant : [l'import](flux-de-import-24102026.md),
qui lit `raw/` et rend les fichiers lus.

## Légende

| Couleur | Sens |
|---|---|
| Jaune | **Rejet nommé** : `reject` (`etl/rejections.py:11-13`) écrit `rejected from <fichier>: <motif>` au journal de fonctionnement, puis une ligne `rejection` du journal d'import ; l'import continue. |
| Gris | **Écarté** : la base garde la version qu'elle a ; une ligne `discard` du journal d'import, avec sa règle. |
| Orange | **Rollback** de toute la transaction : rien n'est écrit, aucun journal d'import ne reste. |
| Rouge | **Fin de la commande** sur un code de sortie nommé (`commands/exit_codes.py`). |
| Vert | Écrit. |

## 1. La transaction

```mermaid
flowchart TD
    A["import_items<br/>etl/load.py:51"] --> B{"check_database_exists, connect_database<br/>etl/load.py:62-63, database/connection.py:13-23<br/>PRAGMA foreign_keys = ON"}
    B -- MissingDatabaseError --> X2a["exit 2 NOT_STARTED"]:::stop
    B -- ok --> C["write_tracked_repositories<br/>etl/load.py:66, database/writers/release_writer.py:39-52<br/>upsert des dépôts suivis : premier INSERT,<br/>sqlite3 ouvre la transaction"]
    C --> D["write_files<br/>etl/load.py:85-100<br/>d'abord les rejets de la lecture"]
    D --> E["list_files_in_collection_order<br/>etl/load.py:143-155<br/>du plus ancien au plus récent ;<br/>à collecte égale, les items avant les tendances"]
    E --> F{"write_file<br/>etl/file_writing.py:39-44"}
    F -- "RawFile : fichier d'items" --> FI["write_items_file<br/>détail en 2"]
    F -- "TrendFile : fichier de tendances" --> FT["write_trend_file<br/>détail en 5"]
    FI -- "fichier suivant" --> F
    FT -- "fichier suivant" --> F
    FI -- "erreur qui n'est pas due à l'entrée" --> RB["rollback<br/>etl/load.py:69-72"]:::fail
    FT -- "erreur qui n'est pas due à l'entrée" --> RB
    FI -- "dernier fichier" --> J["join_writings<br/>etl/load.py:158-171"]
    FT -- "dernier fichier" --> J
    J --> CL{"commit_with_log, check_log_absent<br/>etl/load.py:103-114, 138-140"}
    CL -- "import-log de cette seconde déjà là :<br/>ImportLogExistsError" --> RB
    CL -- absent --> LG["write_import_log<br/>etl/import_log.py:37-85<br/>write_file_atomically"]
    LG -- "erreur d'écriture" --> RB
    LG --> CM{"connection.commit<br/>etl/load.py:123"}
    CM -- "sqlite3.Error ; Ctrl-C ou SIGTERM<br/>avant la fin du commit" --> UL["journal supprimé<br/>etl/load.py:129-131"]
    UL --> RB
    CM -- "SIGTERM reçu pendant le commit" --> KEEP["import et journal gardés<br/>import committed, log kept<br/>etl/load.py:132-134"]
    KEEP --> X143["exit 143 STOPPED_BY_SIGTERM"]:::stop
    CM -- ok --> OK["ImportSummary<br/>etl/load.py:75-82"]:::ok
    RB --> X{"run_import<br/>commands/import_command.py:44-57"}
    X -- ImportLogExistsError --> X2b["exit 2 NOT_STARTED<br/>run kb import again"]:::stop
    X -- "sqlite3.Error, OSError,<br/>UnknownSourceError, KindWithoutTableError" --> X1a["exit 1 FAILED"]:::stop
    X -- "SIGTERM" --> X143b["exit 143<br/>cli.py:116-119"]:::stop
    X -- "autre exception" --> X1b["exit 1 FAILED<br/>cli.py:120-124"]:::stop

    classDef stop fill:#f8d7da,stroke:#b02a37,color:#000
    classDef fail fill:#fde2c4,stroke:#c2410c,color:#000
    classDef ok fill:#d3f9d8,stroke:#2b8a3e,color:#000
```

Le journal est écrit avant le commit : un fichier inscrit dans `raw_data` n'est plus relu, son
journal ne doit donc pas se perdre (`etl/load.py:109-111`). `check_log_absent` est appelé une
fois la base verrouillée en écriture : deux imports de la même seconde ne peuvent pas tous deux
trouver le journal absent (`etl/load.py:112-114`).

## 2. Un fichier d'items

```mermaid
flowchart TD
    A["write_items_file<br/>etl/file_writing.py:47-69"] --> B{"register_raw_file, write_raw_data<br/>etl/file_writing.py:97-105, database/writers/shared_rows.py:20-41"}
    B -- "source_code absent de la table source :<br/>UnknownSourceError" --> RB["rollback de la transaction"]:::fail
    B -- "raw_data : INSERT ... ON CONFLICT DO NOTHING,<br/>stream = nom du dossier de la source" --> C["write_item_in_savepoint, pour chaque item<br/>etl/file_writing.py:51-54, 108-121"]
    C --> S{"write_in_savepoint<br/>database/savepoint.py:28-48"}
    S -- "hors transaction : NoTransactionError" --> RB
    S -- "SAVEPOINT entry" --> W{"write_item<br/>database/writing.py:64-71"}
    W -- "sorte absente de WRITER_BY_KIND :<br/>KindWithoutTableError" --> RT2
    W -- "écrivain de la sorte" --> WR["WRITER_BY_KIND : paper, vulnerability, release,<br/>advisory, newsletter_article, zotero_entry, clip<br/>database/writing.py:53-61 ; règles en 3"]
    WR -- "None : écrit" --> RL["RELEASE SAVEPOINT entry<br/>database/savepoint.py:48"]:::ok
    WR -- "Discard : la base garde sa version" --> DS["écarté, avec sa règle"]:::discard
    DS --> RL
    WR -- "IntegrityError CHECK, UNIQUE, NOT NULL ;<br/>OverflowError, UnicodeEncodeError" --> RT["ROLLBACK TO SAVEPOINT entry, RELEASE ;<br/>EntryRefusedError<br/>database/savepoint.py:41-46"]
    RT --> R5["rejet : SORTE ID refused by the base<br/>valeur refusée jamais citée<br/>etl/file_writing.py:116-121"]:::reject
    WR -- "autre erreur : FOREIGN KEY, PRIMARY KEY,<br/>type STRICT, disque plein, base verrouillée" --> RT2["ROLLBACK TO SAVEPOINT entry,<br/>erreur relevée telle quelle<br/>database/savepoint.py:41-47"]
    RT2 --> RB
    RL --> NX{"item suivant ?"}
    R5 --> NX
    NX -- oui --> C
    NX -- non --> CNT["rejection_count += refus de la base<br/>etl/file_writing.py:57-60"]
    CNT --> WD["mark_withdrawn_vulnerabilities,<br/>mark_withdrawn_zotero_rows<br/>etl/file_writing.py:61-63 ; détail en 4"]
    WD --> OUT["FileWriting : items écrits, écartés,<br/>refus, lignes retirées<br/>etl/file_writing.py:64-69"]

    classDef fail fill:#fde2c4,stroke:#c2410c,color:#000
    classDef reject fill:#fff3bf,stroke:#b08800,color:#000
    classDef discard fill:#e9ecef,stroke:#6c757d,color:#000
    classDef ok fill:#d3f9d8,stroke:#2b8a3e,color:#000
```

Le fichier est inscrit dans `raw_data` hors de tout savepoint, même si la base refuse ensuite un
de ses items (`etl/file_writing.py:48-50`). Seules les erreurs dues à l'entrée deviennent un
rejet (`database/savepoint.py:8-16`, `conventions.md` règle 1) ; les autres arrêtent tout l'import.

## 3. Les règles des écrivains

Chaque écrivain trouve l'item par sa clé naturelle, puis applique la règle de sa famille. Il rend
`None` (écrit) ou un `Discard` (écarté), jamais une erreur pour une version déjà connue.

```mermaid
flowchart TD
    A["écrivain de la sorte<br/>database/writers/SORTE_writer.py, write"] --> F{"famille"}
    F -- "flux d'actualité :<br/>release, advisory, newsletter_article" --> N1{"clé naturelle connue ?<br/>INSERT INTO item ... WHERE NOT EXISTS"}
    N1 -- non --> N2["item et sous-type insérés"]:::ok
    N1 -- oui --> N3["already_seen<br/>la première version vue est gardée"]:::discard
    F -- "flux à révisions : paper" --> P1{"UPSERT : publication sans item,<br/>ou révision plus récente ?"}
    P1 -- oui --> P2["colonnes arXiv réécrites,<br/>item pointé sur le nouveau brut"]:::ok
    P1 -- non --> P3["revision_not_newer"]:::discard
    F -- "catalogue d'état :<br/>vulnerability, zotero_entry" --> C0["catalog.read_latest<br/>database/writers/catalog.py:35-53<br/>dernier catalogue importé de la source"]
    C0 --> C1{"fichier collecté après lui,<br/>et contenu changé ou ligne retirée ?"}
    C1 -- oui --> C2["ligne réécrite, revised_at daté,<br/>withdrawn_at vidé"]:::ok
    C1 -- "ligne nouvelle, fichier plus ancien<br/>que le dernier catalogue" --> C4["ligne écrite, retirée à la date<br/>du dernier catalogue<br/>catalog.py:56-61"]:::ok
    C1 -- "non, fichier plus récent" --> C3["unchanged"]:::discard
    C1 -- "non, fichier pas plus récent" --> C5["no_newer_version"]:::discard
    F -- "dernière version d'une URL : clip" --> K1{"URL connue ?"}
    K1 -- non --> K2["item, clip et tags insérés"]:::ok
    K1 -- "oui, même contenu" --> K3["already_seen"]:::discard
    K1 -- "oui, contenu changé,<br/>fichier plus ancien que le brut connu" --> K4["no_newer_version"]:::discard
    K1 -- "oui, contenu changé,<br/>fichier plus récent" --> K5["colonnes et tags changés réécrits,<br/>revised_at daté"]:::ok

    classDef discard fill:#e9ecef,stroke:#6c757d,color:#000
    classDef ok fill:#d3f9d8,stroke:#2b8a3e,color:#000
```

| Sorte | Écrivain | Clé naturelle | Tables écrites | Écarté : règle, date comparée au journal |
|---|---|---|---|---|
| `release` | `release_writer.write` (`:55-90`) | `release_id` | `item`, `release` (le dépôt suivi doit exister dans `tracked_repository`) | `already_seen` (`:67`), `compared_with_collected_at` |
| `advisory` | `advisory_writer.write` (`:25-63`) | `ghsa_id` | `item`, `advisory`, `vulnerability` (CVE créée sans ses colonnes KEV si nouvelle) | `already_seen` (`:37`), `compared_with_collected_at` |
| `newsletter_article` | `newsletter_article_writer.write` (`:36-68`) | édition, date d'édition, rang | `item`, `newsletter_article` | `already_seen` (`:53`), `compared_with_collected_at` |
| `paper` | `paper_writer.write` (`:28-59`) | `arxiv_id` | `item`, `publication` | `revision_not_newer` (`:56`), `compared_with_revised_at` |
| `vulnerability` | `vulnerability_writer.write` (`:57-93`) | `cve_id` | `item`, `vulnerability` | `unchanged` ou `no_newer_version` (`catalog.py:64-72`), `compared_with_collected_at` |
| `zotero_entry` | `zotero_entry_writer.write` (`:84-147`) | `zotero_key` de l'entrée et de chaque surlignage | `item`, `zotero_entry`, `highlight`, `publication` (citée, créée sans ses colonnes arXiv si absente) | `unchanged` ou `no_newer_version` (`:143`), `compared_with_collected_at` |
| `clip` | `clip_writer.write` (`:89-149`) | URL sans paramètres `utm_` | `item`, `clip`, `tag`, `item_has_tag` | `already_seen` ou `no_newer_version` (`:141-143`), `compared_with_collected_at` |

Les lignes de la table renvoient à `database/writers/`. Le champ de date du journal d'import
dépend de la règle : `COMPARED_FIELD_BY_RULE` (`etl/import_log.py:15-25`).

## 4. Les retraits d'un catalogue

```mermaid
flowchart TD
    A["fichier d'items écrit<br/>etl/file_writing.py:61-63"] --> V{"mark_withdrawn_vulnerabilities<br/>etl/withdrawals.py:13-33"}
    V -- "aucun item vulnerability avec CVE,<br/>ou rejection_count > 0" --> V0["0 : rien retiré"]
    V -- "CVE présentes, aucun rejet" --> V1{"mark_withdrawn_vulnerabilities_not_in<br/>vulnerability_writer.py:96-122<br/>fichier collecté après le dernier catalogue ?"}
    V1 -- non --> V0
    V1 -- oui --> V2["UPDATE vulnerability SET withdrawn_at<br/>CVE d'un item KEV absente du fichier,<br/>pas encore retirée"]:::ok
    A --> Z{"mark_withdrawn_zotero_rows<br/>etl/withdrawals.py:36-46"}
    Z -- "aucune entrée zotero_entry,<br/>ou rejection_count > 0" --> Z0["0 : rien retiré"]
    Z -- "entrées présentes, aucun rejet" --> Z1{"mark_withdrawn_zotero_rows_not_in<br/>zotero_entry_writer.py:163-202<br/>extrait collecté après le dernier ?"}
    Z1 -- non --> Z0
    Z1 -- oui --> Z2["UPDATE zotero_entry, highlight SET withdrawn_at<br/>clés absentes de l'extrait, pas encore retirées"]:::ok

    classDef ok fill:#d3f9d8,stroke:#2b8a3e,color:#000
```

Un catalogue qui a une entrée rejetée, par le lecteur, par `Item` ou par la base, ne retire rien :
une entrée rejetée est dans le catalogue, pas absente de lui (`etl/withdrawals.py:18-19`). Une
ligne retirée n'est jamais supprimée ; le premier retrait garde sa date.

## 5. Un fichier de tendances

```mermaid
flowchart TD
    A["write_trend_file<br/>etl/file_writing.py:72-94"] --> S["write_in_savepoint : un seul SAVEPOINT<br/>pour le fichier entier"]
    S --> B["register_raw_file, write_raw_data<br/>etl/file_writing.py:83"]
    B --> W["write_trend_rows : trend_writer.write<br/>database/writers/trend_writer.py:40-56"]
    W --> R{"write_row, par ligne<br/>trend_writer.py:59-73<br/>INSERT ... WHERE NOT EXISTS une ligne de la fenêtre<br/>venue d'un autre fichier"}
    R -- "ligne écrite" --> OK["trend_count += 1"]:::ok
    R -- "fenêtre déjà apportée par un autre fichier" --> DS["fenêtre écartée : TrendDiscard,<br/>règle already_seen<br/>etl/file_writing.py:90-93"]:::discard
    S -- "dans le savepoint : IntegrityError CHECK, UNIQUE,<br/>NOT NULL ; OverflowError, UnicodeEncodeError" --> RJ["ROLLBACK TO SAVEPOINT : fichier entier défait,<br/>non inscrit, relu au prochain import ;<br/>rejet ranking refused by the base<br/>etl/file_writing.py:87-89"]:::reject
    S -- "dans le savepoint : UnknownSourceError,<br/>autre erreur de la base" --> RB["rollback de la transaction"]:::fail

    classDef fail fill:#fde2c4,stroke:#c2410c,color:#000
    classDef reject fill:#fff3bf,stroke:#b08800,color:#000
    classDef discard fill:#e9ecef,stroke:#6c757d,color:#000
    classDef ok fill:#d3f9d8,stroke:#2b8a3e,color:#000
```

Contrairement à un fichier d'items, un fichier de tendances est écrit ou refusé en entier : une
ligne refusée par la base le défait, inscription dans `raw_data` comprise
(`etl/file_writing.py:75-79`).

## 6. Le journal d'import

`import-log-AAAA-MM-JJTHHMMSSZ.jsonl`, dans le dossier de données, un par import, jamais réécrit
(`etl/pipeline.py:36-37`, `65-67`). Une ligne JSON par événement, dans cet ordre
(`etl/import_log.py:44-81`) :

| `kind` | Champs | Origine |
|---|---|---|
| `rejection` | `imported_at`, `raw_file_path`, `reason` | rejets de la lecture (import), puis refus de la base, fichier par fichier |
| `discard` | `imported_at`, `rule`, `source_code`, `source_item_id`, `raw_file_path`, date comparée | items écartés par un écrivain |
| `discard` | idem, `rule` `already_seen`, `source_item_id` = fin de la fenêtre | fenêtres de tendances écartées |

Aucun dépôt n'y est nommé : son nom porte le login de son propriétaire (`etl/import_log.py:44-45`).

## 7. Erreurs de l'écriture en base

| Erreur | Levée par | Traitée par | Effet |
|---|---|---|---|
| Base absente (`MissingDatabaseError`) | `check_database_exists` (`database/connection.py:13-16`) | `run_import` (`commands/import_command.py:44-46`) | exit 2 |
| `source_code` absent de la table `source` (`UnknownSourceError`) | `write_raw_data` (`database/writers/shared_rows.py:31-32`) | `import_items` (`etl/load.py:69-72`), puis `run_import` | rollback, exit 1. La table est remplie par `database/seed_sources.sql` |
| Sorte sans table (`KindWithoutTableError`) | `write_item` (`database/writing.py:69-70`) | `write_in_savepoint`, `import_items`, `run_import` | rollback, exit 1 |
| Savepoint hors transaction (`NoTransactionError`) | `write_in_savepoint` (`database/savepoint.py:34-37`) | `import_items`, puis `main` (`cli.py:120-124`) | rollback, exit 1 |
| Contrainte `CHECK`, `UNIQUE`, `NOT NULL` ; `OverflowError`, `UnicodeEncodeError` sur un item | SQLite, `sqlite3` | `write_in_savepoint` (`database/savepoint.py:41-46`), `write_item_in_savepoint` (`etl/file_writing.py:116-121`) | `ROLLBACK TO` de cet item seul ; rejet ; l'import continue |
| Même erreur sur une ligne de tendance | SQLite, `sqlite3` | `write_trend_file` (`etl/file_writing.py:87-89`) | fichier de tendances défait en entier, non inscrit ; rejet ; l'import continue |
| Version déjà connue | écrivain de la sorte (section 3) | l'écrivain | écarté, ligne `discard` |
| Clé étrangère, clé primaire, type `STRICT`, disque plein, base verrouillée | SQLite | `write_in_savepoint` (relève telle quelle), `import_items` | rollback, exit 1 |
| Journal de la même seconde déjà là (`ImportLogExistsError`) | `check_log_absent` (`etl/load.py:138-140`) | `run_import` (`commands/import_command.py:47-49`) | rollback, exit 2 |
| Journal non écrit (`OSError`) | `write_import_log`, `write_file_atomically` | `commit_with_log`, `import_items`, `run_import` | rollback, exit 1 |
| Commit refusé (`sqlite3.Error`) | `connection.commit` (`etl/load.py:123`) | `commit_with_log` (`etl/load.py:124-135`) | journal supprimé, rollback, exit 1 |
| SIGTERM avant la fin du commit | `raise_stopped_by_sigterm` (`commands/sigterm.py:43-46`) | `write_in_savepoint`, `commit_with_log`, `import_items`, puis `main` (`cli.py:116-119`) | rollback, journal supprimé s'il était écrit, exit 143 |
| SIGTERM pendant le commit | idem | `commit_with_log` (`etl/load.py:132-134`) | import et journal gardés, exit 143 |
| Ctrl-C (`KeyboardInterrupt`) avant la fin du commit | Python | `commit_with_log`, `import_items` (`except BaseException`) | rollback, journal supprimé s'il était écrit ; `main` ne rattrape que `Exception` (`cli.py:120`) : Python s'arrête sur sa trace, code de sortie **non vérifié** |
