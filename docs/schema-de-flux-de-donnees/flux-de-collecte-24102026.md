# Flux de données de la collecte : `kb collect`

Instantané du code au commit `4626e24` (`main`, 2026-10-24). Fondé sur la lecture du code seul :
aucune commande de K-B n'a été exécutée. Les chemins sont relatifs à `src/k_b/` ; les numéros de
ligne valent pour ce commit ; ce qui ne se tranche qu'en exécutant est marqué **non vérifié**.

Flux générique, valable pour toutes les sources, des sources jusqu'à `raw/` et
`collection_state.json`. Vue d'ensemble : [flux complet](flux-de-donnees-complet-24102026.md).
Suite : [l'import](flux-de-import-24102026.md).

## Légende

| Couleur | Sens |
|---|---|
| Orange | **Échec de la source** : l'exception remonte jusqu'à `collect_all_sources` (`etl/extract.py:46-60`), qui la journalise une fois, avec ses notes, puis passe à la source suivante ; la date de dernière collecte de la source reste. |
| Rouge | **Fin de la commande** sur un code de sortie nommé (`commands/exit_codes.py`). |
| Vert | Succès de la source : sa date de dernière collecte devient l'heure de la collecte. |

## 1. De la commande à la boucle des sources

```mermaid
flowchart TD
    A["kb collect<br/>main, cli.py:46"] --> B{"read_data_dir, read_log_to_file<br/>cli.py:96-99"}
    B -- "KB_DATA_DIR absent ou pas un dossier,<br/>KB_LOG_TO_FILE invalide" --> X2a["exit 2 NOT_STARTED<br/>message sur stderr"]:::stop
    B -- ok --> C{"logging_to<br/>cli.py:105"}
    C -- OSError --> X2b["exit 2 NOT_STARTED<br/>error: log file not opened<br/>cli.py:106-112"]:::stop
    C -- ok --> D["stopping_on_sigterm, run_collect<br/>cli.py:114, commands/collect_command.py:35"]
    D --> E{"read_collect_only_or_refusal<br/>etl/collected_sources.py:47"}
    E -- "KB_COLLECT_ONLY vide, nom inconnu,<br/>ou source choisie sans sa variable" --> X2c["exit 2 NOT_STARTED<br/>value_or_log_refusal<br/>collect_command.py:39-43"]:::stop
    E -- ok --> G["list_collected_sources<br/>etl/collected_sources.py:94<br/>sortes de SOURCE_KINDS choisies, puis Zotero,<br/>clips et GH Archive si leur variable est posée"]
    G --> G2["log_collection_start<br/>collect_command.py:61<br/>avertit si KB_GITHUB_TOKEN manque"]
    G2 --> H["collect, collect_all_sources<br/>etl/pipeline.py:47, etl/extract.py:33"]
    H --> I{"load_last_collection_dates<br/>etl/raw_store.py:155"}
    I -- "illisible ou invalide :<br/>InvalidCollectionStateError" --> X2d["exit 2 NOT_STARTED<br/>aucune source lancée<br/>collect_command.py:50-52"]:::stop
    I -- "absent : aucune date,<br/>ou dates lues" --> J["collect_one_source, pour chaque source, dans l'ordre<br/>etl/extract.py:41-45<br/>détail en 2"]
    J -- "toute Exception" --> K["échec de la source<br/>logger.exception : collection failed for source<br/>date inchangée<br/>etl/extract.py:46-60"]:::fail
    J -- "fichier écrit, ou None" --> L["date de la source = now<br/>etl/extract.py:61-63"]:::ok
    K -- "source suivante" --> J
    L -- "source suivante" --> J
    K -- "dernière source" --> M{"save_last_collection_dates<br/>etl/raw_store.py:186"}
    L -- "dernière source" --> M
    M -- OSError --> N["state_error<br/>collection state not written<br/>etl/extract.py:64-70"]:::fail
    M -- ok --> O["print, une ligne par source : ok, ou failed et le type d'erreur ;<br/>une ligne par source non lancée : skipped<br/>collect_command.py:53-57, 80-89"]
    N --> O
    O --> P{"find_collection_exit_code<br/>collect_command.py:92-101"}
    P -- "état non écrit" --> X1a["exit 1 FAILED"]:::stop
    P -- "toutes les sources en échec" --> X1b["exit 1 FAILED"]:::stop
    P -- "échecs et succès mêlés" --> X4["exit 4 PARTIAL_FAILURE"]:::stop
    P -- "aucun échec" --> X0["exit 0 SUCCEEDED"]:::ok

    classDef stop fill:#f8d7da,stroke:#b02a37,color:#000
    classDef fail fill:#fde2c4,stroke:#c2410c,color:#000
    classDef ok fill:#d3f9d8,stroke:#2b8a3e,color:#000
```

## 2. La collecte d'une source

```mermaid
flowchart TD
    A["collect_one_source<br/>etl/extract.py:74"] --> B{"acquisition_dir_name dans RAW_DIR_NAMES ;<br/>name et extension en a-z0-9_<br/>etl/extract.py:79-83"}
    B -- non --> E1["ValueError<br/>not a folder of raw, not a safe path segment"]:::fail
    B -- oui --> F["source.fetch, avec la date de dernière collecte<br/>etl/extract.py:84"]
    F -- "rien à demander :<br/>GH Archive sans fenêtre due" --> N["None : rien n'est écrit<br/>etl/extract.py:85-86"]:::ok
    F --> ACC{"accès de la source"}
    ACC -- "HTTP : arXiv, CISA KEV, TLDR" --> DL["download<br/>etl/http_download.py:22<br/>détail en 3"]
    ACC -- "API GitHub : releases, advisories,<br/>most starred, most forked" --> GA["get_from_github_api<br/>etl/sources/github_api.py:17-31"]
    GA --> DL
    ACC -- "BigQuery : GH Archive" --> BQ["create_client, check_day_table_closed,<br/>drop_windows_over_the_cap, query<br/>etl/sources/gh_archive.py:138-147"]
    ACC -- "Zotero" --> ZO["remove_left_copies, copy_library,<br/>extract_documents, dans un TemporaryDirectory<br/>etl/sources/zotero.py:204-210"]
    ACC -- "clips du coffre" --> CL["list_clip_files, read_clip_files<br/>etl/sources/clipping.py:99-125"]
    DL -- "HTTP 304 : CISA KEV" --> N
    DL -- "erreur réseau ou HTTP, préfixe refusé,<br/>redirection hors préfixe, réponse trop grande" --> E2["échec de la source"]:::fail
    BQ -- "DayTableNotClosedError, DryRunOverLimitError,<br/>DryRunVolumeUnknownError, erreur du client" --> E3["échec de la source"]:::fail
    ZO -- "ZoteroChangedDuringCopyError, ZoteroCopyInconsistentError,<br/>ZoteroQueryFailedError" --> E4["échec de la source"]:::fail
    CL -- "ClippingsFolderMissingError, ClipTooLargeError" --> E5["échec de la source"]:::fail
    DL --> CK
    BQ --> CK
    ZO --> CK
    CL --> CK
    CK{"contrôle du contenu, lu comme à l'import<br/>détail en 4"}
    CK -- "page illisible ; classement ou tendances<br/>refusés en entier" --> E6["ValueError : échec de la source"]:::fail
    CK -- "catalogue sans entrée : empty_catalog<br/>CISA KEV, Zotero" --> E7["échec de la source<br/>etl/source_contract.py:61-65"]:::fail
    CK -- "toutes les entrées invalides :<br/>all_items_invalid" --> E8["échec de la source<br/>etl/source_contract.py:51-58"]:::fail
    CK -- "rien de nouveau : condition propre<br/>à la source, tableau 4" --> N
    CK -- "contenu accepté" --> R{"forme rendue par fetch"}
    R -- bytes --> W1["write_new_raw_file<br/>raw/RANGÉ_SOUS/NOM/COLLECTION.EXT<br/>etl/extract.py:89-93"]
    R -- "dict de pages : TLDR, clips" --> P{"chaque nom de page en a-z0-9_-<br/>etl/extract.py:96-98"}
    P -- non --> E10["ValueError not a safe page name<br/>aucune page écrite"]:::fail
    P -- oui --> W2["write_new_raw_file, page par page<br/>raw/RANGÉ_SOUS/NOM/COLLECTION/PAGE.EXT<br/>etl/extract.py:99-102"]
    W1 --> EX{"le fichier existe déjà ?<br/>etl/raw_store.py:150-151"}
    W2 --> EX
    EX -- oui --> E11["FileExistsError raw file already exists"]:::fail
    EX -- non --> AT["write_file_atomically<br/>etl/raw_store.py:105-145<br/>temporaire caché, fsync, os.replace, fsync des dossiers"]
    AT -- "erreur d'écriture, Ctrl-C, SIGTERM" --> E12["temporaire supprimé, erreur relevée<br/>etl/raw_store.py:128-136 ;<br/>les pages déjà écrites restent"]:::fail
    AT -- ok --> OK["succès de la source"]:::ok

    classDef fail fill:#fde2c4,stroke:#c2410c,color:#000
    classDef ok fill:#d3f9d8,stroke:#2b8a3e,color:#000
```

`COLLECTION` est l'heure de la collecte au format `AAAA-MM-JJTHHMMSSZ` (`COLLECTION_NAME_FORMAT`,
`etl/raw_files.py:10`), la même pour toutes les sources d'une collecte. `RANGÉ_SOUS` vaut
`automated_watch` ou `selected_library` (`etl/raw_store.py:19-24`).

## 3. Le téléchargement, commun à HTTP et à l'API GitHub

```mermaid
flowchart TD
    A["download : url, préfixe de confiance, taille maximale<br/>etl/http_download.py:22"] --> B{"check_trusted_url_prefix<br/>etl/http_download.py:49-69"}
    B -- "préfixe pas https://hôte/chemin, ou avec @" --> E1["ValueError trusted prefix ... refused"]:::fail
    B -- "URL hors du préfixe" --> E2["ValueError url outside its trusted prefix"]:::fail
    B -- ok --> C["Request : en-têtes, User-Agent K-B ;<br/>en-tête non redirigé : jeton GitHub<br/>etl/http_download.py:36-38"]
    C --> D["urlopen, délai 30 s<br/>etl/http_download.py:39"]
    D -- "HTTPError, laissée à l'appelant" --> H{"l'appelant la traite ?"}
    H -- "304 : CISA KEV" --> N["None : rien de nouveau<br/>etl/sources/cisa_kev.py:78-81"]:::ok
    H -- "autre code, autre source" --> E3["échec de la source"]:::fail
    D -- "URLError, délai dépassé" --> E4["échec de la source<br/>types exacts non vérifiés"]:::fail
    D -- réponse --> R1{"URL finale sous le préfixe ?<br/>etl/http_download.py:41"}
    R1 -- non --> RO{"RedirectedOutsideError<br/>etl/http_download.py:42"}
    RO -- "TLDR : redirigé vers la page de l'édition" --> T["jour sans édition, ignoré<br/>etl/sources/tldr.py:114-123"]:::ok
    RO -- "autre cas" --> E5["échec de la source"]:::fail
    R1 -- oui --> R2{"plus d'octets que le maximum ?<br/>etl/http_download.py:43-45"}
    R2 -- oui --> E6["ValueError response larger than ... refused"]:::fail
    R2 -- non --> OK["octets de la réponse"]:::ok

    classDef fail fill:#fde2c4,stroke:#c2410c,color:#000
    classDef ok fill:#d3f9d8,stroke:#2b8a3e,color:#000
```

Tailles maximales : arXiv 6 Mio (`arxiv.py:31`), CISA KEV 10 Mio (`cisa_kev.py:36`), une page TLDR
1 Mio (`tldr.py:25`), une réponse de l'API GitHub 5 Mio (`github_api.py:14`).

## 4. Ce que chaque source contrôle avant d'écrire

Chaque `fetch` relit son contenu comme l'import le lira, pour qu'une page fausse fasse échouer la
source au lieu d'être gardée (`conventions.md`, règle 1).

| Source | Contrôle du contenu dans `fetch` | `None` quand |
|---|---|---|
| CISA KEV | `read_catalog`, `check_not_empty`, `check_not_all_invalid` (`cisa_kev.py:83-85`) | HTTP 304 sur `If-Modified-Since` (`cisa_kev.py:70-81`) |
| GitHub Releases | `read_releases`, `check_not_all_invalid`, chaque release du dépôt suivi (`github_releases.py:59-68`) | aucune release publiée après la dernière collecte (`github_releases.py:73-77`) |
| GitHub Advisories | `read_advisories`, `check_not_all_invalid` (`github_advisories.py:67-68`) | aucun avis valide ; ou aucun revu depuis la dernière collecte et aucun rejet (`github_advisories.py:69-79`) |
| GitHub most starred, most forked | `read_ranking` : classement plus court que demandé ou incomplet refusé en entier (`github_most_starred.py:43`, `github_most_forked.py:40`) | jamais |
| arXiv | `count_papers`, `read_total_results`, `check_not_all_invalid` (`arxiv.py:83-94`) | aucun papier dans la fenêtre (`arxiv.py:90-91`) |
| TLDR | `find_refusal` par page : un refus après la dernière édition lue fait échouer la source, un refus avant est abandonné, celui du jour est relu à la collecte suivante (`tldr.py:62-95`) | aucune page d'édition (`tldr.py:96-100`) |
| Zotero | `check_document`, `check_not_empty`, `check_not_all_invalid` (`zotero.py:211-213`) | extrait identique, octet pour octet, au dernier brut (`zotero.py:222-224`) |
| Clips | `find_rejection_reason` par clip, `check_not_all_invalid` (`clipping.py:128-138`) | aucun clip changé depuis la dernière collecte et stable depuis `CLIP_CHANGE_MARGIN` (`clipping.py:106-127`) |
| GH Archive | `read_trends` : l'extrait est refusé en entier (`TrendsExtractInvalidError`, `gh_archive.py:148`, `286-320`) | aucune fenêtre due (`gh_archive.py:135-137`) |

## 5. Erreurs de la collecte

| Erreur | Levée par | Traitée par | Effet |
|---|---|---|---|
| `KB_DATA_DIR` absent ou pas un dossier ; `KB_LOG_TO_FILE` ni `true` ni `false` | `read_data_dir`, `read_log_to_file` (`commands/environment.py:16-45`) | `main` (`cli.py:96-99`) | exit 2, rien n'est lancé |
| Fichier de journal non ouvert (`OSError`) | `logging_to` | `main` (`cli.py:106-112`) | exit 2 |
| `KB_COLLECT_ONLY` vide, nom inconnu, ou source choisie sans sa variable | `find_collect_only_refusal` (`etl/collected_sources.py:63-85`) | `run_collect` (`collect_command.py:39-43`) | exit 2 |
| `collection_state.json` illisible ou invalide (`InvalidCollectionStateError`) | `load_last_collection_dates` (`etl/raw_store.py:163-183`) | `run_collect` (`collect_command.py:50-52`) | exit 2, aucune source lancée |
| Dossier, nom ou extension de source non sûrs ; nom de page non sûr | `collect_one_source` (`etl/extract.py:79-83`, `96-98`) | `collect_all_sources` (`etl/extract.py:46-60`) | échec de la source, rien d'écrit |
| Préfixe ou URL refusés, redirection hors préfixe, réponse trop grande | `download` (`etl/http_download.py:34-45`) | `collect_all_sources` | échec de la source |
| Erreur réseau ou HTTP (`urllib`) non traitée par la source | `urlopen` (`etl/http_download.py:39`) | `collect_all_sources` | échec de la source ; types exacts **non vérifiés** |
| Erreur propre à une source : `DayTableNotClosedError`, `DryRunOverLimitError`, `DryRunVolumeUnknownError` (GH Archive), `ZoteroChangedDuringCopyError`, `ZoteroCopyInconsistentError`, `ZoteroQueryFailedError` (Zotero), `ClippingsFolderMissingError`, `ClipTooLargeError` (clips), refus d'une page TLDR | la source (`etl/sources/`) | `collect_all_sources` | échec de la source |
| Page illisible, classement ou tendances refusés, `empty_catalog`, `all_items_invalid` | lecteur de la source, `check_not_empty`, `check_not_all_invalid` (`etl/source_contract.py:51-65`) | `collect_all_sources` | échec de la source |
| Une partie seulement des entrées invalides | `read_each_entry` (`etl/source_contract.py:32-48`) | — | le brut est écrit entier ; les entrées invalides sont rejetées à l'import |
| Brut déjà présent (`FileExistsError`) ; erreur d'écriture | `write_new_raw_file`, `write_file_atomically` (`etl/raw_store.py:105-152`) | `collect_all_sources` | échec de la source ; le temporaire est supprimé ; pour un dossier de pages, celles déjà écrites restent (`etl/extract.py:94-95`) |
| État non écrit (`OSError`) | `save_last_collection_dates` (`etl/raw_store.py:186-197`) | `collect_all_sources` (`etl/extract.py:64-70`) | exit 1 ; les bruts écrits restent, la collecte suivante repart des anciennes dates |
| Exception hors de la boucle des sources, non traitée | — | `main` (`cli.py:120-124`) | exit 1, `kb stopped by an exception it does not handle` |
| SIGTERM | `raise_stopped_by_sigterm` (`commands/sigterm.py:43-46`) | `main` (`cli.py:116-119`) | exit 143. `StoppedBySigtermError` est une `SystemExit`, que `except Exception` (`etl/extract.py:46`) ne rattrape pas : la boucle s'arrête, l'état n'est pas écrit, les bruts déjà écrits restent |
