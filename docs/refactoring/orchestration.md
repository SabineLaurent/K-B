# Où vit l'orchestration de l'ETL

Relevé du 2026-10-22, branche `refactoring/etl`, commit `9895ff0`, arbre de travail propre.
Aucun fichier du dépôt n'a été modifié pour l'écrire. Il prolonge
[l'inventaire](inventaire.md) : l'inventaire dit ce que les modules contiennent, celui-ci dit qui
décide quoi, et dans quel ordre.

Référence vérifiée avant le relevé : `uv run pytest tests/architecture/ -q` → 102 tests passés.
C'est le filet de la refactorisation ; la partie 4 dit ce que chaque organisation lui ferait.

## Vocabulaire

Repris de `.claude/rules/conventions.md`, règle 5, et du docstring de
`tests/architecture/test_layers.py` :

- **couches** sous `k_b` : `core` et `items` sont le vocabulaire commun ; `database` lit et écrit
  la base (ses écrivains sous `database/writers`, derrière `database/writing`) ; `etl` fait
  tourner le pipeline ; `post` écrit les fiches au-dessus ; `data_api` sert la base ; `ai_api`
  appelle le modèle ; `cli` et `commands` **composent**.
- sous `k_b.etl` : la **composition** (`source_kinds`, `collected_sources`) → les **sources**
  (`etl/sources/`) → les **modules du pipeline** (`extract`, `transform`, `load`, `normalize`,
  `import_log`, `raw_store`, `raw_purge`, `tops`, `source_contract`, `http_download`,
  `user_agent`). Les trois listes sont tenues dans `tests/architecture/module_imports.py:21-35`,
  et `test_every_module_of_etl_is_in_exactly_one_list` vérifie que chaque module de `etl/` est
  dans exactement une.

Ce document n'emploie « pipeline » que dans ce sens-là : les modules du pipeline, par opposition
à la composition et aux sources. Le fichier `etl/pipeline.py` de la cible annoncée n'existe pas
encore ; il est nommé ici `pipeline.py`, entre guillemets de code, quand il s'agit de lui.

## 1. Les chaînes d'appels, commande par commande

### Tronc commun des quatre commandes

`cli.main` (`src/k_b/cli.py:50`) lit les arguments, puis :

1. `read_data_dir()` (`commands/environment.py:16`) — `KB_DATA_DIR`, sans défaut ; absent →
   `ExitCode.NOT_STARTED`.
2. `read_log_to_file()` (`commands/environment.py:33`) — `KB_LOG_TO_FILE`.
3. `logging_to(data_dir, log_file_path)` (`cli.py:109`) — ouvre le journal de fonctionnement ;
   un `OSError` ici arrête tout : `NOT_STARTED`.
4. `stopping_on_sigterm(arguments.command)` (`cli.py:118`) — le gestionnaire SIGTERM, posé pour
   toutes les commandes au même endroit.
5. `run_command(command, data_dir)` (`cli.py:135-149`) — un `if` par commande, vers
   `run_collect`, `run_import`, `run_write_tops`, `run_digest`.

Les écritures citées ci-dessous passent toutes par `write_file_atomically`
(`etl/raw_store.py:113`), sauf la base, que SQLite écrit lui-même (règle 2 de `conventions.md`).

### `kb collect`

`commands/collect_command.py:35` `run_collect(data_dir)`

```
run_collect
├─ read_collect_only_or_refusal(os.environ, SOURCE_KINDS)   etl/collected_sources.py:50
│  └─ find_collect_only_refusal                             etl/collected_sources.py:66
│     (refus → value_or_log_refusal → NOT_STARTED)
├─ list_collected_sources(collect_only, environ, SOURCE_KINDS, RawStore(data_dir))
│                                                           etl/collected_sources.py:99
│  ├─ list_sources(kinds)                                   etl/source_contract.py:110
│  └─ ZoteroSource / ClippingSource / GhArchiveSource       etl/sources/*.py
├─ log_collection_start(sources, environ)                   commands/collect_command.py:66
├─ collect_all_sources(sources, data_dir/raw, data_dir, now) etl/extract.py:32
│  ├─ load_last_collection_dates(data_dir)                  etl/raw_store.py:165   ← lecture état
│  ├─ pour chaque source : collect_one_source               etl/extract.py:73
│  │  ├─ contrôle de acquisition_dir_name, name, extension  etl/extract.py:76-80
│  │  ├─ source.fetch(last_collected_at)                    etl/sources/<source>.py
│  │  │  └─ (la plupart) read_*  + check_not_all_invalid    etl/source_contract.py:61,72
│  │  └─ write_new_raw_file(...)                            etl/raw_store.py:158   ← ÉCRIT raw/
│  └─ save_last_collection_dates(data_dir, dates)           etl/raw_store.py:192   ← ÉCRIT l'état
├─ print par source : describe_outcome                      commands/collect_command.py:112
├─ print_skipped_sources(collect_only, environ)             commands/collect_command.py:86
└─ find_collection_exit_code(outcome)                       commands/collect_command.py:100
```

Écritures : un fichier par collecte (ou un par page) sous `raw/<dossier>/<source>/`, puis
`collection_state.json`. Aucune écriture en base, aucune fiche.

### `kb import`

`commands/import_command.py:42` `run_import(data_dir)`

```
run_import
├─ imported_at = now(UTC).replace(microsecond=0)            commands/import_command.py:47
├─ log_path = data_dir/import-log-<imported_at>.jsonl        commands/import_command.py:48
│     (nom construit avec COLLECTION_NAME_FORMAT, défini dans etl/transform.py:21)
├─ read_imported_paths(database_path)                       etl/load.py:86   ← lit raw_data
│  └─ check_database_exists, connect_database, read_raw_file_paths
├─ read_raw_items(raw_dir, SOURCE_KINDS, imported_paths)    etl/transform.py:63   ← LIT raw/
│  ├─ list_collections(raw_dir, kinds)                      etl/transform.py:164  (glob)
│  │  └─ find_source_kind                                   etl/source_contract.py:114
│  ├─ read_collection → parse_collection_name, list_pages   etl/transform.py:94,124,197
│  └─ read_page                                             etl/transform.py:130
│     ├─ page_path.read_bytes()                                                  ← LIT raw/
│     ├─ reader.read_entries(bytes)                         etl/sources/<source>.py
│     └─ reader.convert(entry, collected_at, path)          etl/sources/<source>.py
├─ read_trend_files(raw_dir, imported_paths)                etl/sources/gh_archive.py:389 ← LIT raw/
│  ├─ list_visible_entries, parse_collection_name           etl/transform.py:211,124
│  └─ read_trends(path.read_bytes())                        etl/sources/gh_archive.py:316
├─ import_items(reading, trend_reading, database_path, log_path, imported_at,
│               TRACKED_REPOSITORIES)                       etl/load.py:107
│  ├─ check_database_exists, connect_database               database/connection.py:19
│  ├─ write_tracked_repositories(connection, repositories)  database/writing.py   ← ÉCRIT base
│  ├─ write_files(connection, reading, trend_reading, repos) etl/load.py:146
│  │  ├─ list_files_in_collection_order                     etl/load.py:235  (tri pur)
│  │  ├─ write_file → write_items_file                      etl/load.py:187,277
│  │  │  ├─ reject_untracked_releases(items, repositories)  etl/load.py:249  (filtre pur)
│  │  │  ├─ register_raw_file → write_raw_data              etl/load.py:333   ← ÉCRIT base
│  │  │  ├─ map(normalize_item, items)                      etl/normalize.py:14 (pur)
│  │  │  ├─ write_item_in_savepoint → write_in_savepoint    etl/load.py:313
│  │  │  │  └─ write_item → WRITER_BY_KIND[kind]            database/writing.py:69 ← ÉCRIT base
│  │  │  ├─ mark_withdrawn_vulnerabilities                  etl/load.py:385   ← ÉCRIT base
│  │  │  └─ mark_withdrawn_zotero_rows                      etl/load.py:410   ← ÉCRIT base
│  │  ├─ write_file → write_trend_file                      etl/load.py:344
│  │  │  └─ write_trend_rows (dans un savepoint)            database/writing.py  ← ÉCRIT base
│  │  └─ join_writings                                      etl/load.py:172  (somme pure)
│  ├─ commit_with_log(connection, log_path, imported_at, writing)  etl/load.py:197
│  │  ├─ check_log_absent(log_path)                         etl/load.py:427
│  │  ├─ write_import_log(...)                              etl/import_log.py:35  ← ÉCRIT .jsonl
│  │  ├─ connection.commit()                                                      ← VALIDE base
│  │  └─ sur exception : log_path.unlink(missing_ok=True)                          ← DÉFAIT .jsonl
│  └─ ImportSummary(...)                                    etl/load.py:136-143
├─ 7 print du résumé                                        commands/import_command.py:77-89
└─ delete_superseded_raw_files(RawStore, read_imported_paths(...), LATEST_ONLY_FOLDER_KEYS)
                                                            etl/raw_purge.py:15   ← SUPPRIME raw/
```

Écritures : la base (dépôts suivis, `raw_data`, items et sous-types, lignes de tendance,
colonnes de retrait), un `import-log-<seconde>.jsonl` sous `KB_DATA_DIR`, et des suppressions
dans `raw/` après le commit.

### `kb write-tops`

`commands/write_tops_command.py:20` `run_write_tops(data_dir)`

```
run_write_tops
├─ read_vault_dir(os.environ)                               etl/collected_sources.py:92
│     (absent, ou pas un dossier → NOT_STARTED)
├─ store = RawStore(data_dir)                               etl/raw_store.py:49
└─ pour chaque top de TOPS                                  etl/source_kinds.py:89
   └─ write_top_sheets(store, vault_dir, top)               post/top_sheets.py:48
      ├─ find_sheets_dir(vault_dir, top)                    post/top_sheets.py:125
      ├─ store.list_file_keys(top.folder_key)               etl/raw_store.py:76
      ├─ refuse_linked_folders / refuse_linked_sheets       post/vault_files.py:59 ; :133
      ├─ pour chaque clé : read_ranking                     post/top_sheets.py:87
      │  ├─ find_collection_time → parse_collection_name    post/top_sheets.py:111 ;
      │  │                                                  etl/transform.py:124
      │  └─ top.read_entries(store.read(key))               etl/sources/github_most_*.py ← LIT raw/
      ├─ write_sheet → render_sheet → write_new_sheet        post/top_sheets.py:158,171 ;
      │                                                     post/vault_files.py:47  ← ÉCRIT la fiche
      ├─ refuse_linked_folders, refuse_missing_sheets        post/top_sheets.py:75-76
      ├─ store.delete(key) pour readable_keys[:-1]           etl/raw_store.py:57  ← SUPPRIME raw/
      └─ TopSheetsOutcome(...)                              post/top_sheets.py:79
   puis print describe_outcome, et find_exit_code            commands/write_tops_command.py:47,52
```

Écritures : une fiche `veille/tops/<top>/AAAA-MM-JJ.md` par jour de collecte, et des
suppressions dans `raw/`. Aucune écriture en base.

### `kb digest`

`commands/digest_command.py:32` `run_digest()` — ne reçoit pas `data_dir` : il ne lit ni `raw/`
ni la base.

```
run_digest
├─ read_vault_dir(os.environ)                               etl/collected_sources.py:92
│     (absent, ou pas un dossier → NOT_STARTED)
├─ read_ai_api_client_settings_or_refusal(os.environ)       post/ai_api_client.py:156
├─ refuse_written_sheets(vault_dir, subject_names, today)    post/digest_sheets.py:71
│     (une fiche du jour déjà là → NOT_STARTED, rien n'est demandé au modèle)
├─ build_ai_api_client(settings)                            post/ai_api_client.py:175
├─ request_digests(http_client, subject_names)              post/ai_api_client.py:191  ← HTTP
│  └─ read_response → refuse_out_of_lists                   post/ai_api_client.py:211,260
│     (l'API IA interroge l'API de données ; etl n'est pas sur ce chemin)
└─ write_digest_sheets(vault_dir, response)                 commands/digest_command.py:77
   └─ par sujet : write_digest_sheet                        post/digest_sheets.py:98
      ├─ render_digest_sheet                                post/digest_sheets.py:116
      └─ write_new_sheet                                    post/vault_files.py:47  ← ÉCRIT la fiche
   puis print, et find_exit_code                            commands/digest_command.py:101,104
```

Écritures : une fiche `veille/<sujet>/AAAA-MM-JJ.md` par sujet rendu.

**`kb digest` ne touche `etl` que par `read_vault_dir`** (`etl/collected_sources.py:92`), une
lecture de `KB_VAULT_DIR`. `kb write-tops` ne le touche que par `read_vault_dir`, `RawStore` et
`TOPS`. C'est le seul lien entre ces deux commandes et `etl` : `read_vault_dir` vit dans la
composition de `etl` parce que c'est de là que la source `clipping` lit le coffre
(`etl/collected_sources.py:93-94`), et deux commandes de `post` s'en servent au passage.

## 2. Où se trouve chaque décision d'orchestration

| Décision | `kb collect` | `kb import` | `kb write-tops` | `kb digest` |
|---|---|---|---|---|
| **Ordre des étapes** | `extract.collect_all_sources` (état → sources → état) ; le choix des sources est dans la commande | partagé : la commande enchaîne registre → lecture des items → lecture des classements → `import_items` → purge ; `load.import_items` enchaîne dépôts suivis → fichiers → journal+commit ; `load.write_files` enchaîne les rejets de lecture puis les fichiers triés | la commande boucle sur `TOPS` ; `post.write_top_sheets` enchaîne lecture → fiches → contrôles → suppressions | la commande : coffre → réglages → refus des fiches du jour → requête → fiches |
| **Transaction** | sans objet | `load.import_items:121-135` : `connect_database`, `except BaseException: rollback`, `finally: close`. Le `BEGIN` n'est **pas** écrit : la transaction s'ouvre implicitement à la première écriture (`sqlite3` de Python), et `database/savepoint.py:40-43` lève `NoTransactionError` si elle n'est pas ouverte. Par entrée : `write_in_savepoint` (`database/savepoint.py:32`) | sans objet (pas de base) | sans objet |
| **Journal de fonctionnement** | `logging_to` posé par `cli.py:109` ; les lignes sont émises dans `extract.py:51` (échec d'une source), `collect_command.py:70-78` | idem ; lignes dans `load.py:231`, `raw_purge.py:38`, `transform.py:179,189,202,218`, `import_command.py:64-103` | idem ; lignes dans `top_sheets.py:78,92,100,165,167`, `write_tops_command.py:44` | idem ; lignes dans `digest_command.py:38-98` |
| **Journal d'import (`.jsonl`)** | sans objet | nom et chemin : `import_command.py:34,48` ; existence et écriture : `load.commit_with_log:197-232` ; contenu : `import_log.write_import_log:35` | sans objet | sans objet |
| **Gestion des rejets** | aucun rejet nommé : une source lève, `extract.py:41-62` attrape `Exception`, journalise et garde l'erreur par source | trois chemins qui convergent vers `transform.reject` (`transform.py:217`) : entrée refusée à la lecture (`transform.py:143-157`), release hors liste (`load.reject_untracked_releases:249`), entrée refusée par la base (`load.write_item_in_savepoint:325`) ; tous finissent dans `FileWriting.rejections` puis au journal d'import | pas de rejet nommé : un classement illisible est compté `unreadable_count` et journalisé (`top_sheets.py:98-107`) ; un refus du coffre lève `VaultEntryRefusedError` | un sujet en échec vient de l'API IA (`response.failed_subjects`) ou d'une fiche non écrite ; compté dans `digest_command.py:82-100` |
| **Résumé rendu** | `print` par source dans `run_collect:58-62`, à partir de `CollectionOutcome` (`extract.py:26`) | `ImportSummary` construit dans `load.import_items:136-143` ; les sept `print` dans `import_command.py:77-89` | `TopSheetsOutcome` construit dans `top_sheets.py:79` ; le `print` dans `write_tops_command.py:47,63` | compteurs tenus dans `digest_command.py:80-103` |
| **Code de sortie** | `find_collection_exit_code` (`collect_command.py:100`) | les `except` de `run_import` (`import_command.py:63-104`) ; `SUCCEEDED` en fin | `find_exit_code` (`write_tops_command.py:52`) | `find_exit_code` (`digest_command.py:104`) |

Ce que la table montre : **l'orchestration de `kb import` est à deux endroits**, la commande et
`load.import_items`, avec la frontière au milieu d'un parcours — la lecture du registre
(`read_imported_paths`) est dans `load.py`, la lecture du brut dans `transform.py` et
`gh_archive.py`, et c'est la commande qui les met dans l'ordre. Pour les trois autres commandes,
l'orchestration est entière dans la commande, sauf `collect_all_sources`, qui tient la boucle des
sources et l'état.

Une connaissance est écrite deux fois : le format du nom d'une collecte. `extract.py:85` écrit
`f"{now:%Y-%m-%dT%H%M%SZ}"` en clair, alors que `transform.py:21` en tient la constante
`COLLECTION_NAME_FORMAT`, dont le commentaire dit « The name etl/extract.py gives every raw file
of a collection ». Trois modules lisent la constante (`transform.py:125`,
`import_command.py:49`, `post/top_sheets.py:120`), un l'écrit en clair.

## 3. Les étapes qui tournent dans la mauvaise phase

Relevé par lecture des appels, pas par exécution.

1. **`normalize_item` tourne pendant le load.** `load.write_items_file:292` applique
   `map(normalize_item, items)` entre l'enregistrement du fichier et l'écriture des items. Le
   module `etl/normalize.py` est l'étape 3 de `docs/specs-collecte.md`, le load l'étape 4 ; son
   propre docstring (`normalize.py:3-4`) dit « les items viennent de `etl/transform.py` ».
2. **`reject_untracked_releases` tourne pendant le load.** `load.write_items_file:288`, un filtre
   pur sur les items lus (`load.py:249-274`) : il décide quels items existent, ce que fait le
   transform, et il produit des rejets par `transform.reject`.
3. **`normalize_item` tourne aussi pendant le transform, pour une seule source.**
   `etl/sources/clipping.py:380` appelle `remove_tracking_parameters` dans `convert_clip`, pour
   construire `source_item_id` ; son commentaire dit « the URL normalize_item will give the
   item ». Pour les douze autres sources, la normalisation n'a lieu qu'au load. Un clip est donc
   normalisé deux fois, à deux phases, et c'est le seul.
4. **La lecture du brut (extract) tourne pendant le transform.** `transform.read_page:135` fait
   `page_path.read_bytes()`, et `list_collections:173` fait un `glob` de `raw/`,
   `list_pages:200` et `list_visible_entries:214` un `iterdir`. `etl/transform.py` est l'un des
   deux fichiers que la règle 3 de `poc.md` nomme comme « touchant le brut » hors de
   `raw_store.py` — l'autre est `etl/sources/gh_archive.py`.
5. **`read_trend_files` fait extract et transform dans une source.**
   `etl/sources/gh_archive.py:389-425` liste `raw/`, lit les octets (`path.read_bytes()`) **et**
   construit les `TrendFile`/`TrendRow` ; il importe pour cela sept noms de `etl/transform.py`
   (`gh_archive.py:29-37`). C'est le miroir de `transform.read_raw_items`, écrit dans la source.
6. **Trois fonctions pures vivent dans le load** : `join_writings` (`load.py:172`),
   `list_files_in_collection_order` (`load.py:235`), `reject_untracked_releases`
   (`load.py:249`). Déjà relevé par l'inventaire, partie 3.3 ; repris ici parce que c'est la
   même frontière.
7. **Le load écrit deux cibles.** `load.commit_with_log:197-232` écrit un fichier `.jsonl`
   (par `import_log` → `write_file_atomically`) puis commite la base, et supprime le fichier si
   le commit échoue. L'ordre entre les deux porte une règle (le journal avant le commit,
   `load.py:203-208`) : ce n'est pas une étape déplaçable sans la décider.
8. **Le load lit une règle de nommage du brut.** `load.register_raw_file:339` appelle
   `find_stream` (`raw_store.py:34`), qui lit le nom du dossier source dans le chemin relatif.
9. **`post` lit le transform.** `post/top_sheets.py:20` importe `COLLECTION_NAME_FORMAT` et
   `parse_collection_name` de `etl/transform.py`. Permis aujourd'hui (`post` est au-dessus
   d'`etl`), mais c'est du vocabulaire de nommage du brut, pas du transform.

Dans l'autre sens, deux choses qui **ne sont pas** des mélanges de phase, mais s'en approchent, et
qui sont décidées :

- Une source **lit ses entrées pendant son `fetch`** (`check_not_all_invalid`,
  `check_not_empty` : `arxiv.py:100`, `cisa_kev.py:101-102`, `clipping.py:144`,
  `github_advisories.py:74`, `github_releases.py:64`, `zotero.py:224-225`). C'est la règle 1 de
  `conventions.md` : une source n'échoue que si sa page est illisible ou si toutes ses entrées
  sont invalides. Le transform tourne donc à la collecte, exprès, sans rien écrire.
- `write_item_in_savepoint` **rend un rejet** construit par `transform.reject` (`load.py:325`) :
  le chemin unique des rejets de la règle 1, pas une étape de transform.

## 4. Trois organisations possibles

Aucune n'est choisie ici. Les trois supposent **une décision préalable** qui vaut pour toutes :

> **Les types partagés.** `RawFile`, `RawReading`, `TrendFile`, `TrendReading`, `Rejection` et
> `COLLECTION_NAME_FORMAT` sont définis dans `etl/transform.py` et importés par `etl/load.py:57`,
> `etl/import_log.py:12`, `etl/sources/gh_archive.py:29`, `post/top_sheets.py:20` et
> `commands/import_command.py:29`. La règle annoncée « `extract`, `transform` et `load` ne
> s'importent pas entre eux » les rend inatteignables depuis le load : il faut un endroit neutre
> (un module `etl/raw_files.py`, ou `items.py`, ou `core/`). Sans cette décision, aucune des
> trois options ne tient.
>
> **`raw_store` n'est pas une phase.** Il est écrit par l'extract (`extract.py:87,97`), lu par le
> transform (`transform.py:14`), par le load (`load.py:56`), par `import_log` (`import_log.py:11`),
> par `raw_purge`, par la composition (`collected_sources.py:12`, `source_kinds.py:10`) et par
> `post` (`top_sheets.py:18`). La règle 3 de `poc.md` lui réserve tout accès au brut et à l'état.
> Le ranger dans `etl/extract/` le rendrait importable par le transform et le load, ce que la
> règle annoncée interdit : il reste à `etl/raw_store.py`, ou passe dans `core/`.
>
> **La règle 5 de `conventions.md` dit aujourd'hui** « Le module de chargement orchestre la
> transaction et le journal, sans SQL ». Les options A et B la contredisent sur ce point, l'option
> C la contredit autrement (voir plus bas). Elle est à amender quelle que soit l'option, par la PR
> qui touche la famille.

### Option A — `etl/pipeline.py`, les modules restant à plat

**Ce qu'elle déplace.**
- `collect_all_sources` + `collect_one_source` (`extract.py:32-99`) et `import_items`
  (`load.py:107-143`) → `etl/pipeline.py`, un parcours par fonction. `extract.py` disparaît ou
  ne garde que les contrôles de nom.
- `join_writings`, `list_files_in_collection_order`, `reject_untracked_releases` (63 lignes,
  `load.py:172-274`) → `etl/transform.py`.
- L'appel à `normalize_item` sort de `write_items_file` et remonte dans `pipeline.py` (ou dans
  `read_page`) ; `write_items_file` reçoit des items déjà normalisés et déjà filtrés.
- `read_imported_paths` (`load.py:86`) reste dans le load, ou passe dans `database/`.
- Les types partagés vont dans le module neutre décidé plus haut.

**Ce qu'elle casse dans les tests d'architecture.**
- `tests/architecture/module_imports.py:23-35` : ajouter `etl.pipeline` (et le module neutre) à
  `ETL_PIPELINE_MODULES`, sinon `test_every_module_of_etl_is_in_exactly_one_list`
  (`test_packages.py:20`) échoue.
- `test_no_module_of_the_pipeline_imports_the_sources_or_the_composition`
  (`test_layers.py:102`) : `pipeline.py` est dans la liste du pipeline, donc il ne peut
  **pas** importer `etl/sources/` ni `source_kinds` / `collected_sources`. Il doit recevoir les
  sources, les `SourceKind` et les lectures en paramètres, comme `collect_all_sources` et
  `import_items` le font déjà. Tenable sans changer le test.
- Rien d'autre : `test_only_database_imports_its_writers`,
  `test_etl_imports_neither_the_data_api_nor_the_ai_api`,
  `test_etl_imports_nothing_of_the_post_processing` restent vrais.
- Les tests de `tests/etl/` importent `import_items`, `read_imported_paths`, `read_raw_items`,
  `normalize_item` par leur module (`test_load.py:28-38`, `test_extract.py:9`,
  `test_raw_purge.py:12`, `tests/etl/sources/test_zotero.py:13`, `test_arxiv.py:10`,
  `test_gh_archive.py:24`, `test_tldr.py:11,21`) : à mettre à jour, mécaniquement.

**Risques.**
- `pipeline.py` tiendrait deux parcours sans rapport (collecte et import) : un module qui
  mélange deux niveaux, ce que `code.md` refuse. Un `pipeline.py` par parcours, ou une fonction
  par parcours dans un module qui ne fait que les enchaîner, est à décider.
- `commit_with_log` reste mixte (fichier + base) : l'option ne le traite pas. Le déplacer vers
  `pipeline.py` sortirait la transaction du load, et c'est la règle 5 qui tombe.
- `read_trend_files` reste dans `gh_archive.py` : le point 5 de la partie 3 n'est pas réglé.

### Option B — les trois paquets `etl/extract/`, `etl/transform/`, `etl/load/` + `etl/pipeline.py`

La cible annoncée dans l'inventaire, prise à la lettre.

**Ce qu'elle déplace.** Tout ce que l'option A déplace, plus la répartition des douze modules du
pipeline en trois paquets. Un rattachement possible, à décider :

| Paquet | Modules |
|---|---|
| `etl/extract/` | `http_download`, `user_agent`, et les contrôles de nom de `extract.py` |
| `etl/transform/` | `transform` (découpé : lecture des pages, conversion), `normalize`, les trois fonctions pures de `load.py` |
| `etl/load/` | `load` (sans l'orchestration), `import_log` |
| hors des trois | `raw_store`, `raw_purge`, `source_contract`, `tops`, le module des types partagés, `pipeline.py` |

`raw_purge` est le cas douteux : il supprime du brut après le commit, donc ni extract, ni
transform, ni load au sens de la cible.

**Ce qu'elle casse dans les tests d'architecture.**
- `module_imports.py:23-35` : les trois noms de paquets remplacent `etl.extract`, `etl.transform`,
  `etl.load` dans `ETL_PIPELINE_MODULES`. `pkgutil.iter_modules` (`test_packages.py:22`) voit un
  paquet comme un module de même nom : `test_every_module_of_etl_is_in_exactly_one_list` passe si
  les listes suivent. `parse_imported_modules` coupe à deux niveaux
  (`module_imports.py:44-72`), donc `from k_b.etl.transform.reading import …` donne
  `etl.transform` : les règles par préfixe continuent de fonctionner sans être réécrites.
- `test_every_package_of_k_b_has_an_empty_init` (`test_packages.py:33`) : les trois
  `__init__.py` doivent rester **vides**, donc aucun ré-export. Chaque appelant importe le module
  précis (`from k_b.etl.transform.reading import read_raw_items`), et chaque chemin d'import
  change dans le code et dans les tests.
- `test_no_module_of_the_pipeline_imports_the_sources_or_the_composition` interdit aux trois
  paquets d'importer `etl/sources/`. Or `etl/sources/gh_archive.py` importe le transform, et
  `etl/sources/clipping.py:33` importe `normalize` : ce sens-là reste permis (une source est
  au-dessus du pipeline). Mais `read_trend_files` devient un transform écrit dans une source,
  en face d'un `etl/transform/` qui fait la même chose : à trancher dans la même PR.

**Risques.**
- Le plus de mouvement des trois : chaque import de `etl.transform` / `etl.load` change dans
  `src/` et dans `tests/`. Le diff est large, et une revue y lit mal ce qui a changé de
  comportement.
- `raw_store` hors des trois paquets rend la cible moins lisible qu'annoncée : l'arborescence
  promet trois phases, et il reste cinq ou six modules à côté. À dire dans l'ADR, sinon la cible
  et le code divergent.
- Trois `__init__.py` vides et des imports à trois niveaux allongent chaque ligne d'import, pour
  des paquets dont certains n'auront qu'un ou deux modules (`etl/load/` : deux).

### Option C — l'orchestration dans `commands/`, sans `pipeline.py`

**Ce qu'elle déplace.**
- Le corps de `import_items` (`load.py:107-143`) → `commands/import_command.py`, qui enchaîne
  déjà la moitié du parcours. `load.py` ne garde que des fonctions qui écrivent, chacune
  recevant la connexion.
- L'ouverture de la connexion, le `rollback` sur `BaseException` et l'ordre journal-puis-commit
  partent avec : soit dans la commande, soit dans un gestionnaire de contexte de `database/`
  (`database/transaction.py`, à créer), appelé par la commande.
- `collect_all_sources` reste où il est, ou remonte dans `commands/collect_command.py` par
  symétrie.
- Les trois fonctions pures et `normalize_item` sortent du load comme dans l'option A.

**Ce qu'elle casse dans les tests d'architecture.**
- **Rien.** `commands/` est de la composition : `COMPOSITION_MODULES`
  (`module_imports.py:36`) l'autorise à importer `database.writing`
  (`test_layers.py:66`), et `import_command.py:11` le fait déjà.
  `test_neither_commands_nor_the_composition_of_etl_imports_the_command_line_above`
  (`test_layers.py:87`) ne concerne pas ce sens. Aucune liste à mettre à jour, aucun paquet
  créé. C'est l'option que le filet ne voit pas passer — ce qui est aussi son défaut.
- Les tests de `tests/etl/test_load.py` qui appellent `import_items` de bout en bout
  (`test_load.py:28`) deviennent des tests de commande : à déplacer vers `tests/test_cli.py` ou
  un `tests/commands/`, ou à réécrire autour des fonctions d'écriture.

**Risques.**
- Elle contredit la règle 5 de `conventions.md` sur deux points, pas un : « Le module de
  chargement orchestre la transaction et le journal, sans SQL », et « une couche n'appelle que
  celle du dessous » — la commande ouvrirait la connexion et conduirait la transaction, alors
  que la couche d'accès aux données est deux crans plus bas. L'option n'est jouable qu'avec une
  règle 5 réécrite, et c'est la décision la plus structurante des trois.
- `commands/import_command.py` passerait de 106 à ~160 lignes et tiendrait, dans un seul
  module, les réglages, l'ordre des étapes, la transaction, les sept `print` et les codes de
  sortie : plusieurs niveaux de détail dans un module, ce que `code.md` refuse.
- Aucun test d'architecture ne garderait la frontière : rien n'empêcherait la commande suivante
  d'appeler un écrivain directement. Il faudrait un test nouveau pour la tenir.

**Ce qu'elle gagne.** Les quatre commandes s'orchestreraient de la même façon — ce qui est déjà
le cas de trois sur quatre (partie 2) — et `etl/load.py` ne ferait plus que du load, sans
module nouveau ni paquet nouveau.

## 5. Ce que je n'ai pas pu vérifier

- **Les chaînes d'appels sont lues, pas exécutées.** Je n'ai lancé aucune commande `kb`, aucun
  test autre que `tests/architecture/` (102 passés). Un appel atteint par une branche que je n'ai
  pas suivie (une exception rattrapée plus haut, par exemple) peut manquer aux arbres de la
  partie 1.
- **Les arbres s'arrêtent à la frontière de `database/` et de `ai_api/`.** `write_item`,
  `write_trend_rows`, `write_raw_data`, `mark_withdrawn_*` sont donnés par leur porte
  (`database/writing.py`) sans leurs écrivains ; le parcours interne de l'API IA appelée par
  `kb digest` n'est pas relevé. L'inventaire les met hors périmètre (partie 4), je ne l'ai pas
  élargi.
- **Les sources ne sont détaillées que là où elles touchent l'orchestration**
  (`check_not_all_invalid` au `fetch`, `read_trend_files`, `convert_clip`). Les treize modules de
  `etl/sources/` n'ont pas été lus en entier ; une autre étape de transform ou de normalize
  appelée dans un `fetch` ou un `convert` peut m'avoir échappé.
- **Le rattachement des modules aux paquets, dans l'option B, est une proposition**, comme celui
  de l'inventaire : je n'ai pas vérifié que chaque module se range sans importer un de ses pairs.
  `raw_purge` et `source_contract` sont les deux cas que je sais douteux ; il peut en rester.
- **Le coût en lignes de l'option C** (~160 lignes pour `import_command.py`) est une estimation
  faite en comptant les 37 lignes de `import_items` ajoutées aux 106 actuelles, sans écrire le
  module.
- **Je n'ai pas vérifié ce que les tests hors `tests/architecture/` exigent des signatures
  déplacées.** Les imports relevés par `grep` (partie 4, option A) disent quels fichiers de tests
  nomment ces fonctions, pas ce que chacun en attend.
- **La transaction implicite** : je conclus de l'absence de `BEGIN` dans le chemin de l'import
  (`grep -rn "isolation_level\|BEGIN\|autocommit" src/k_b` ne renvoie que
  `database/reading.py:380`) et de `NoTransactionError` (`database/savepoint.py:40`) que
  `sqlite3` ouvre la transaction à la première écriture. Je n'ai pas lu la documentation de
  `sqlite3` pour cette version de Python afin de le confirmer.
