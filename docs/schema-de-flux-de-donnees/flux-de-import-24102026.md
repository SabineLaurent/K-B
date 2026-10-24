# Flux de données de l'import : `kb import`

Instantané du code au commit `4626e24` (`main`, 2026-10-24). Fondé sur la lecture du code seul :
aucune commande de K-B n'a été exécutée. Les chemins sont relatifs à `src/k_b/` ; les numéros de
ligne valent pour ce commit.

Flux générique, valable pour toutes les sources : de `raw/` jusqu'aux fichiers lus, prêts à
écrire. Vue d'ensemble : [flux complet](flux-de-donnees-complet-24102026.md). Avant :
[la collecte](flux-de-collecte-24102026.md). L'écriture elle-même, de la transaction au commit :
[l'écriture en base](flux-de-ecriture-en-base-24102026.md).

## Légende

| Couleur | Sens |
|---|---|
| Jaune | **Rejet nommé** : `reject` (`etl/rejections.py:11-13`) écrit `rejected from <fichier>: <motif>` au journal de fonctionnement, puis le rejet devient une ligne `rejection` du journal d'import ; l'import continue. |
| Rouge | **Fin de la commande** sur un code de sortie nommé (`commands/exit_codes.py`) ; rien n'est écrit en base. |
| Vert | Succès. |

## 1. La commande

```mermaid
flowchart TD
    A["kb import<br/>main, cli.py:46-99"] --> B["stopping_on_sigterm, run_import<br/>cli.py:114, commands/import_command.py:36"]
    B --> C["imported_at : heure UTC à la seconde<br/>import_command.py:39"]
    C --> D["import_raw_files<br/>etl/pipeline.py:53-80"]
    D --> E{"read_imported_paths<br/>etl/load.py:42-48"}
    E -- "k-b.sqlite absent :<br/>MissingDatabaseError" --> X2a["exit 2 NOT_STARTED<br/>create it with kb create-db<br/>import_command.py:44-46"]:::stop
    E -- "chemins inscrits dans raw_data<br/>database/reading.py:269" --> F["read_raw_files<br/>etl/transform.py:34<br/>détail en 2"]
    F -- "ValidationError à la normalisation" --> X1a["exit 1 FAILED<br/>kb stopped by an exception it does not handle<br/>cli.py:120-124"]:::stop
    F -- "OSError en listant raw/" --> X1b["exit 1 FAILED<br/>import_command.py:50-57"]:::stop
    F -- "ImportReadings : items, tendances" --> G["import_items<br/>etl/load.py:51<br/>flux de l'écriture en base"]
    G -- "ImportLogExistsError" --> X2b["exit 2 NOT_STARTED<br/>run kb import again<br/>import_command.py:47-49"]:::stop
    G -- "sqlite3.Error, OSError,<br/>UnknownSourceError, KindWithoutTableError" --> X1c["exit 1 FAILED<br/>rien n'est écrit<br/>import_command.py:50-57"]:::stop
    G -- "transaction validée" --> H["print_import_summary<br/>import_command.py:58, 74-89<br/>fichiers lus, items écrits, lignes de tendance,<br/>écartés, retirés, rejets, chemin du journal"]
    H --> P{"purge_superseded_raw<br/>etl/pipeline.py:83, etl/raw_purge.py:13<br/>dossiers zotero et cisa_kev seulement"}
    P -- "sqlite3.Error, OSError, ValueError" --> X1d["exit 1 FAILED<br/>import committed, raw purge failed<br/>import_command.py:61-69"]:::stop
    P -- "ok : superseded raw files deleted" --> X0["exit 0 SUCCEEDED"]:::ok

    classDef stop fill:#f8d7da,stroke:#b02a37,color:#000
    classDef ok fill:#d3f9d8,stroke:#2b8a3e,color:#000
```

La purge ne garde, de chaque dossier de `LATEST_ONLY_FOLDER_KEYS` (`import_command.py:30-33`),
que le dernier brut importé ; elle lit la liste des bruts dans `raw_data`, jamais dans le dossier :
un brut non importé n'est jamais supprimé (`etl/raw_purge.py:16-33`).

## 2. La lecture de `raw/`

```mermaid
flowchart TD
    A["read_raw_files<br/>etl/transform.py:34-47"] --> B["list_collections<br/>etl/raw_reading.py:45-81<br/>chaque dossier de raw/automated_watch, puis raw/selected_library"]
    B --> K{"find_source_kind par le nom du dossier<br/>etl/source_contract.py:111-120"}
    K -- "aucune sorte" --> K1["ignoré, logger.info<br/>folder without a source kind, skipped"]
    K -- "sorte sans lecteur :<br/>classements GitHub" --> K2["ignoré, logger.info<br/>source without a reader, skipped"]
    K -- "lecteur d'items : SourceReader" --> I["read_raw_items<br/>etl/transform.py:50-68"]
    K -- "lecteur de tendances : TrendReader" --> T["read_raw_trends<br/>etl/transform.py:120-133"]

    I --> C["read_collection, par collection<br/>etl/raw_reading.py:84-113"]
    C --> C1{"fichier, ou dossier de pages ?<br/>parse_collection_name<br/>etl/raw_files.py:13-18"}
    C1 -- "nom hors AAAA-MM-JJTHHMMSSZ,<br/>ou OSError" --> R1["rejet de la collecte<br/>non enregistrée<br/>etl/raw_reading.py:100-106"]:::reject
    C1 -- "dossier : list_pages<br/>sous-dossier ignoré" --> C2["pages, en ordre de nom<br/>etl/raw_reading.py:176-186"]
    C1 -- "fichier : une page" --> C2
    C2 -- "page déjà dans raw_data" --> C3["non ouverte<br/>etl/raw_reading.py:111"]
    C2 -- "page nouvelle" --> D["read_page<br/>etl/raw_reading.py:116-152"]
    D --> D1{"read_bytes, reader.read_entries<br/>lecteur de la source<br/>etl/raw_reading.py:126"}
    D1 -- "ValueError, OSError,<br/>RecursionError, csv.Error" --> R2["rejet de la page<br/>non enregistrée, relue au prochain import<br/>etl/raw_reading.py:128-132"]:::reject
    D1 -- "EntryReading : entrées, motifs de rejet" --> D2["chaque motif du lecteur<br/>etl/raw_reading.py:134-136"]
    D2 --> R3["rejet de l'entrée"]:::reject
    D1 --> D3{"reader.convert, par entrée lue<br/>Item, items.py:345-403<br/>etl/raw_reading.py:138-140"}
    D3 -- ValidationError --> R4["rejet de l'entrée, sans la valeur reçue<br/>without_values<br/>etl/raw_reading.py:141-148"]:::reject
    D3 -- Item --> E["RawFile : chemin, source_code, collected_at,<br/>items, rejection_count<br/>etl/raw_reading.py:149-152"]
    E --> F["tri stable par collected_at<br/>etl/transform.py:65"]
    F --> G{"reject_untracked_releases<br/>etl/transform.py:71-104"}
    G -- "release d'un dépôt hors de la liste suivie" --> R5["rejet de l'item ;<br/>le fichier garde sa place"]:::reject
    G -- "autres items" --> H{"normalize_items, normalize_item<br/>etl/transform.py:107-117, etl/normalize.py:10-16<br/>retrait des paramètres utm_ de l'URL"}
    H -- "ValidationError" --> X1["exit 1 FAILED<br/>l'import entier s'arrête"]:::stop
    H -- "Item normalisé" --> OUT["ImportReadings.items : RawReading<br/>fichiers, rejets, pages ouvertes"]

    T --> T0{"fichier déjà dans raw_data ?<br/>etl/transform.py:131"}
    T0 -- oui --> T00["non ouvert"]
    T0 -- non --> T1["read_trend_file<br/>etl/raw_reading.py:155-173"]
    T1 -- "un dossier, pas un fichier" --> R6["rejet<br/>etl/raw_reading.py:159-160"]:::reject
    T1 -- "nom hors AAAA-MM-JJTHHMMSSZ" --> R7["rejet<br/>etl/raw_reading.py:161-165"]:::reject
    T1 -- "reader.read_rows : ValueError, OSError" --> R8["rejet du fichier entier, non enregistré<br/>etl/raw_reading.py:166-171"]:::reject
    T1 -- "lignes de tendance" --> T2["TrendFile : RawFile sans item, lignes<br/>etl/raw_reading.py:172-173"]
    T2 --> OUT2["ImportReadings.trends : TrendReading"]

    classDef stop fill:#f8d7da,stroke:#b02a37,color:#000
    classDef reject fill:#fff3bf,stroke:#b08800,color:#000
```

`rejection_count` compte les entrées rejetées par le lecteur ou refusées comme items, pas les
releases hors liste (`etl/transform.py:91-95`) : il sert ensuite aux retraits d'un catalogue
([l'écriture en base](flux-de-ecriture-en-base-24102026.md), section 4). Un fichier lu, même
sans item, est inscrit dans `raw_data` à l'écriture ; ses entrées rejetées ne sont donc pas relues.
Une page ou un fichier de tendances illisible n'est pas inscrit : il est relu à l'import suivant.

## 3. Lecteurs des sources

Le lecteur d'une sorte est la constante `READER` (ou `TREND_READER`) de son module, passée à
`SourceKind` dans `etl/source_kinds.py`.

| Dossier de `raw/` | Lecteur | `read_entries` ou `read_rows` | `convert` |
|---|---|---|---|
| `cisa_kev` | `cisa_kev.READER` (`cisa_kev.py:196`) | `read_catalog` | `convert_vulnerability`, item `vulnerability` |
| `github_releases_<dépôt>` | `github_releases.READER` (`github_releases.py:185`) | `read_releases` | `convert_release`, item `release` |
| `github_advisories_<écosystème>` | `github_advisories.READER` (`github_advisories.py:194`) | `read_advisories` | `convert_advisory`, item `advisory` |
| `arxiv_cscr_x_csai` | `arxiv.READER` (`arxiv.py:227`) | `read_papers` | `convert_paper`, item `paper` |
| `tldr_<édition>` | `tldr.READER` (`tldr.py:300`) | `read_articles` | `convert_article`, item `newsletter_article` |
| `zotero` | `zotero.READER` (`zotero.py:441`) | `read_documents` | `convert_document`, item `zotero_entry` |
| `clipping` | `clipping.READER` (`clipping.py:375`) | `read_clip` | `convert_clip`, item `clip` |
| `gh_archive` | `gh_archive.TREND_READER` (`gh_archive.py:363`) | `read_trend_rows` | — (lignes de tendance) |
| `github_most_starred`, `github_most_forked` | aucun | — | — |

## 4. Erreurs de l'import, avant l'écriture

| Erreur | Levée par | Traitée par | Effet |
|---|---|---|---|
| `KB_DATA_DIR`, `KB_LOG_TO_FILE`, journal non ouvert | `read_data_dir`, `read_log_to_file`, `logging_to` | `main` (`cli.py:96-112`) | exit 2 |
| Base absente (`MissingDatabaseError`) | `check_database_exists` (`database/connection.py:13-16`) | `run_import` (`import_command.py:44-46`) | exit 2 |
| `OSError` en listant `raw/` | `list_collections`, `list_visible_entries` (`etl/raw_reading.py:45-81`, `189-192`) | `run_import` (`import_command.py:50-57`) | exit 1 |
| Dossier sans sorte, sorte sans lecteur, sous-dossier dans une collection | `list_collections`, `list_pages` | — | ignoré, `logger.info` |
| Nom de collection hors format | `parse_collection_name` (`etl/raw_files.py:13-18`) | `read_collection` (`etl/raw_reading.py:100-106`) | rejet ; non inscrit |
| Page illisible | lecteur de la source, `read_bytes` | `read_page` (`etl/raw_reading.py:128-132`) | rejet ; page non inscrite, relue au prochain import |
| Entrée invalide | lecteur de la source, par `read_each_entry` (`etl/source_contract.py:42-46`) | `read_page` (`etl/raw_reading.py:134-136`) | rejet de l'entrée ; le fichier sera inscrit |
| Item refusé par Pydantic (`ValidationError`) | `Item` (`items.py:345-403`) | `read_page` (`etl/raw_reading.py:141-148`) | rejet de l'entrée, motif sans la valeur reçue |
| Release d'un dépôt hors de la liste suivie | `is_untracked_release` (`etl/transform.py:99-104`) | `reject_untracked_releases` (`etl/transform.py:82-89`) | rejet de l'item ; le fichier sera inscrit |
| Fichier de tendances : dossier, nom hors format, lignes refusées | `read_trend_file`, lecteur de tendances | `read_trend_file` (`etl/raw_reading.py:159-171`) | rejet du fichier entier ; non inscrit |
| Item refusé à la normalisation (`ValidationError`) | `normalize_item` (`etl/normalize.py:16`) | `main` (`cli.py:120-124`) | exit 1 ; rien n'est écrit |
| SIGTERM pendant la lecture | `raise_stopped_by_sigterm` (`commands/sigterm.py:43-46`) | `main` (`cli.py:116-119`) | exit 143 ; rien n'est écrit |

Les erreurs de l'écriture, du commit et de la purge sont dans
[l'écriture en base](flux-de-ecriture-en-base-24102026.md), section 5.
