# Lisibilité du code de l'ETL — relevé

Relevé du 2026-10-23, branche `refactoring/etl`, commit `75496fb`, jalon `etl-stages-readable`
posé. Analyse en lecture seule : aucun fichier du dépôt n'a été modifié pour l'écrire, celui-ci
excepté. Il porte sur les 29 modules de `src/k_b/etl/` et `src/k_b/etl/sources/` (4 665 lignes).

Il mesure la lisibilité au sens de `.claude/rules/code.md` : un module se lit comme une table des
matières, un seul niveau de détail par module et par fonction, un nom se lit sans aller voir sa
définition, une fonction fait une chose. Les constats sont factuels ; les chantiers de la partie 5
sont des propositions, pas des décisions. La partie 6 les situe par rapport aux étapes 3 bis, 6, 7
et 8 de `plan.md`.

Base de référence des contrôles : `2288 tests passés, 1 échec` ; l'échec unique
(`test_serve_ai_stops_on_sigterm_with_the_code_of_a_process_stopped_by_it`) est un refus du bac à
sable de la session sur `socket.bind(("127.0.0.1", 0))` (`PermissionError: Operation not
permitted`), pas un défaut du code. Lint, format et typage n'ont pas été lancés (voir partie 7).

## 1. Mesures

`prof.` = profondeur de la plus longue chaîne d'appels interne au module (une fonction du module
qui appelle une autre fonction du même module) : c'est l'indicateur du mélange des niveaux. Les
modules sont classés par taille.

| Module | lignes | fonctions | plus longue fonction | prof. | Lecture |
|---|---|---|---|---|---|
| `sources/zotero.py` | 463 | 14 | `convert_document` 36 l. | 4 | niveaux mêlés (3) |
| `sources/clipping.py` | 397 | 19 | `fetch` 51 l. | 4 | niveaux mêlés (3) |
| `load.py` | 392 | 15 | `write_trend_file` 40 l. | 5 | niveaux mêlés (5) |
| `sources/gh_archive.py` | 387 | 16 | `drop_windows_over_the_cap` 36 l. | 4 | niveaux mêlés (3) |
| `sources/tldr.py` | 325 | 13 | `fetch` 54 l. | 5 | niveaux mêlés (3) |
| `sources/arxiv.py` | 237 | 10 | `parse_paper` 30 l. | 3 | niveaux mêlés (2) |
| `sources/cisa_kev.py` | 217 | 6 | `fetch` 35 l. | 3 | niveaux mêlés (2) |
| `sources/github_advisories.py` | 202 | 6 | `fetch` 48 l. | 2 | niveaux mêlés (2) |
| `raw_store.py` | 202 | 12 | `write_file_atomically` 43 l. | 2 | deux vocabulaires |
| `raw_reading.py` | 196 | 6 | `list_collections` 37 l. | 3 | table des matières, portes sans docstring |
| `sources/github_releases.py` | 191 | 6 | `parse_release` 42 l. | 2 | niveaux mêlés (2) |
| `transform.py` | 159 | 6 | `reject_untracked_releases` 30 l. | 4 | niveaux mêlés (3) |
| `sources/github_most_starred.py` | 147 | 5 | `parse_repository` 39 l. | 4 | trois noms pour une lecture |
| `source_contract.py` | 140 | 6 | `read_each_entry` 20 l. | 1 | table des matières |
| `sources/github_most_forked.py` | 126 | 5 | `parse_repository` 27 l. | 4 | jumeau du précédent |
| `collected_sources.py` | 121 | 5 | `find_collect_only_refusal` 24 l. | 2 | table des matières |
| `pipeline.py` | 111 | 3 | `import_raw_files` 30 l. | 1 | table des matières |
| `source_kinds.py` | 108 | 0 | — | 0 | déclaration |
| `extract.py` | 100 | 2 | `collect_all_sources` 39 l. | 2 | niveaux mêlés (2) |
| `import_log.py` | 89 | 1 | `write_import_log` 53 l. | 1 | une fonction, un niveau |
| `http_download.py` | 74 | 3 | `download` 25 l. | 2 | table des matières |
| `raw_files.py` | 71 | 3 | `join_readings` 6 l. | 1 | vocabulaire |
| `sources/tracked_repositories.py` | 47 | 2 | `list_packages_by_ecosystem` 10 l. | 1 | déclaration |
| `raw_purge.py` | 39 | 1 | `delete_superseded_raw_files` 25 l. | 1 | table des matières |
| `tops.py` | 33 | 0 | — | 0 | vocabulaire |
| `sources/github_api.py` | 33 | 1 | `get_from_github_api` 17 l. | 1 | table des matières |
| `normalize.py` | 33 | 2 | `remove_tracking_parameters` 9 l. | 2 | table des matières |
| `rejections.py` | 20 | 1 | `reject` 3 l. | 1 | table des matières |
| `user_agent.py` | 5 | 0 | — | 0 | constante |

Tous les modules ont une docstring de module. 39 fonctions ou méthodes publiques n'ont pas de
docstring ; les portes d'entrée concernées sont relevées ci-dessous, les autres sont des fonctions
d'une ligne dont le nom suffit.

## 2. Modules du pipeline

### `pipeline.py`, `rejections.py`, `normalize.py`, `raw_purge.py`, `http_download.py`, `user_agent.py`

Conformes. `pipeline.py` est la table des matières annoncée : trois fonctions, trois parcours,
chacune déléguant sans rien faire elle-même. Rien à y faire.

Un détail : `IMPORT_LOG_FILE_NAME` est dans `pipeline.py` et `COLLECTION_NAME_FORMAT` dans
`raw_files.py`, alors que les deux nomment un fichier du dossier de données et que le premier
utilise le second (`pipeline.py:80-82`). Sans conséquence de lecture.

### `extract.py` — deux niveaux

`collect_all_sources` (39 l.) tient le parcours : l'état, la boucle, la capture d'erreur, la
sauvegarde. `collect_one_source` (27 l., `extract.py:74`) mêle trois choses : le contrôle des noms
de chemin (`SAFE_PATH_SEGMENT`, `SAFE_PAGE_NAME`), l'aiguillage `bytes` / `dict[str, bytes]`, et
l'écriture. C'est la seule fonction publique du module sans docstring, alors qu'elle porte l'unité
de travail du stage.

À faire : une docstring, et sortir le contrôle des noms dans une fonction nommée
(`check_source_names`). Coût : déplacement mécanique.

### `transform.py` — trois niveaux

Le haut se lit bien (`read_raw_files` → `read_raw_items` / `read_raw_trends`). Puis le module
descend jusqu'au prédicat d'un item (`is_untracked_release`, 7 l.) : stage, étape et prédicat dans
159 lignes.

Deux noms coûtent un aller-retour à la définition :
- `RawReadings` (`transform.py:35`) et `RawReading` (`raw_files.py:36`) diffèrent d'une lettre et
  nomment deux choses différentes : le couple (items, tendances) d'un parcours, et la lecture
  d'items elle-même. `read_raw_files` rend le premier, `read_raw_items` le second.
- La docstring de `read_raw_items` est coupée en plein milieu d'une phrase
  (`transform.py:72-73` : « … are still read. A page / already imported is not opened. »), trace
  d'une édition : `ruff format` ne reformate pas l'intérieur d'une docstring.

À faire : renommer `RawReadings` (par exemple `ImportReadings`, ce que le parcours d'import lit) ;
reformater la docstring. Coût : déplacement mécanique (le nom n'est lu que par `pipeline.py` et
`transform.py`).

### `load.py` — cinq niveaux, le plus gros module du pipeline

La chaîne interne la plus longue de tout l'ETL : `import_items` → `write_files` → `write_file` →
`write_items_file` → `mark_withdrawn_vulnerabilities`. Cinq niveaux dans un module : la
transaction, l'ordre des fichiers, l'aiguillage par type, l'écriture d'un fichier, la règle d'une
source. S'y ajoutent des utilitaires purs (`join_writings`, `list_files_in_collection_order`) et
la garde du journal (`check_log_absent`).

Constats précis :
- **44 des 392 lignes (11 %) sont des littéraux `FileWriting(...)`** : cinq sites
  (`load.py:147, 167, 264, 325, 337`), chacun énonçant les six champs, dont trois mettent quatre
  ou cinq champs à zéro. Des valeurs par défaut sur le `NamedTuple` feraient dire à chaque site ce
  qu'il a produit, et lui seul. Aucun test ne construit `FileWriting` : le changement ne touche
  que `load.py`.
- `FileWriting` est décrit « one file, or the sum of several » (`load.py:96`) : un type qui est à
  la fois un résultat et un agrégat. Même forme que `RawReading`, qui sert pour une page et pour
  la somme des pages.
- `read_collected_at` (`load.py:233`), fonction imbriquée servant de clé de tri, est un accesseur
  nommé avec le verbe `read_`, qui partout ailleurs dans `etl/` signifie lire des octets de
  `raw/`.
- `join_writings` et `write_file` n'ont pas de docstring.
- `load.py:324` dit encore `ranking refused by the base` pour un fichier de tendances. Déjà porté
  par `plan.md` §8, hors étapes.
- La docstring de `write_trend_file` est coupée en plein milieu (`load.py:312-314`).

À faire : les valeurs par défaut de `FileWriting` (mécanique, sans risque), les docstrings
manquantes, le renommage de `read_collected_at` en `find_collection_time` ou `sort_key`. Le
découpage des cinq niveaux est un chantier à part (partie 5).

### `raw_reading.py` — portes sans docstring

Le module est bien celui annoncé à l'étape 4. Deux défauts de lecture :
- `read_collection` (`raw_reading.py:88`) et `read_page` (`raw_reading.py:118`), les deux portes
  du module, n'ont pas de docstring, alors que leur voisin `read_trend_file`
  (`raw_reading.py:152`) en a huit lignes qui expliquent exactement les mêmes cas (fichier non
  nommé par son heure, fichier illisible, ce qui est compté comme ouvert). Le lecteur apprend par
  le chemin des tendances les règles du chemin des items.
- `list_collections` (37 l.) fait trois choses : parcourir les dossiers de `raw/`, choisir le
  lecteur selon la sorte, et journaliser deux cas de dossier sauté. Le type qu'elle rend,
  `Collections` (`raw_reading.py:41`), n'est pas une liste de collections mais deux listes de
  couples `(chemin, lecteur)` dont les membres n'ont pas de nom.

À faire : les deux docstrings, adaptées de celle de `read_trend_file` ; nommer le couple
`(chemin, lecteur)`. Coût : déplacement mécanique.

### `raw_store.py` — deux vocabulaires dans un module

Le module mêle deux façons de nommer un fichier :
- `RawStore` adresse par clé POSIX relative au dossier de données, comme la règle 3 de `poc.md`
  l'exige ;
- quatre fonctions de module prennent un `Path` : `write_file_atomically`, `write_new_raw_file`,
  `load_last_collection_dates`, `save_last_collection_dates`.

C'est exactement l'objet de l'étape 3 bis, mais vu depuis `raw_store.py` et non depuis
`raw_reading.py` : la collecte (`extract.py`) appelle les quatre fonctions à `Path`, pas le
`RawStore`.

**Référence périmée** : la docstring de `list_file_keys` (`raw_store.py:78-80`) dit « as by
`list_visible_entries` of `etl/transform.py`, which imports this module ». Deux faits faux depuis
l'étape 4 : `list_visible_entries` est dans `etl/raw_reading.py`, et `transform.py` n'importe plus
`raw_store` du tout (ses imports : `normalize`, `raw_files`, `raw_reading`, `rejections`,
`source_contract`, `items`).

`load_last_collection_dates`, `save_last_collection_dates`, `has_file` et `read` n'ont pas de
docstring ; les deux premières portent la lecture et l'écriture de l'état de collecte.

### `source_contract.py`, `raw_files.py`, `import_log.py`

Conformes dans leur forme. Trois remarques :
- `check_not_all_invalid` et `check_not_empty` sont définis dans le contrat mais appelés par les
  sources elles-mêmes (sept sources) : c'est le point ouvert de l'étape 6, déjà noté au plan.
- `parse_collection_name`, `join_readings` et `join_trend_readings` n'ont pas de docstring.
  `join_readings` et `join_trend_readings` sont la même fonction écrite deux fois sur deux types ;
  deux occurrences seulement, donc `code.md` dit de les laisser (factorisation à la troisième).
- `write_import_log` fait 53 lignes pour une fonction : trois compréhensions de listes de
  dictionnaires littéraux. Un seul niveau, et les trois formes de ligne se lisent côte à côte.
  Acceptable en l'état.

### `source_kinds.py`, `collected_sources.py`, `tops.py`

La composition se lit bien. Deux détails :
- `source_kinds.py:5` fait 130 caractères : une ligne de docstring allongée quand
  `kb write-tops` y a été ajouté, jamais recoupée.
- `tops.py` expose `Top.read_entries`, qui porte le même nom que `SourceReader.read_entries`
  (`source_contract.py:91`) avec un contrat différent : `list[TopEntry]` contre
  `EntryReading[EntryT]`. Voir aussi les trois `read_ranking` ci-dessous.

## 3. Les sources

Les dix sources ont la même forme : une docstring de module qui annonce « (E) … puis (T) », une
classe `<Source>` avec `fetch`, les fonctions d'extraction, puis le modèle, le lecteur et le
convertisseur, et la constante `READER` en dernière ligne. Chaque fichier est déjà deux modules
dans un seul : c'est ce que l'étape 6 veut séparer.

### Le constat central : les dix `fetch` appellent leur propre côté T

Relevé automatique des appels faits dans chaque `fetch` :

| Source | Ce que `fetch` appelle du côté T |
|---|---|
| `github_most_starred` | `read_ranking` |
| `github_most_forked` | `read_ranking` |
| `cisa_kev` | `read_catalog`, `check_not_empty`, `check_not_all_invalid` |
| `github_advisories` | `read_advisories`, `check_not_all_invalid` |
| `github_releases` | `read_releases`, `check_not_all_invalid` |
| `arxiv` | `read_papers`, `count_papers`, `read_total_results`, `check_not_all_invalid` |
| `gh_archive` | `read_trends` |
| `zotero` | `read_each_entry(check_document)`, `check_not_empty`, `check_not_all_invalid` |
| `tldr` | `find_refusal` → `read_articles` |
| `clipping` | `find_rejection_reason` → `read_clip` + `convert_clip` |

C'est le contrôle à la collecte voulu par la règle 1 de `conventions.md` : une source échoue si sa
page est illisible ou si toutes ses entrées sont invalides. Mais il rend la règle 3 du plan (« le
`extract.py` d'une source n'importe jamais son `transform.py` ») fausse pour **les dix sources**,
et non pour le seul cas des classements que `plan.md` §8 nomme. C'est la véritable charge des
étapes 6 et 7 : le découpage des fichiers est mécanique, la rupture de ce lien ne l'est pas.

Les dix liens ne coûtent pas la même chose. Trois formes, de la plus simple à la plus coûteuse :
1. **Un appel au lecteur, sans rien en faire** (`github_most_starred`, `github_most_forked`,
   `gh_archive`, et `cisa_kev` au contrôle près) : la valeur rendue est jetée, seule l'exception
   compte. Un contrôle générique dans `etl/extract.py` qui appelle le lecteur de la sorte les
   remplace tous.
2. **Un appel au lecteur dont `fetch` lit le résultat** (`arxiv`, `github_advisories`,
   `github_releases`) : `fetch` filtre ou journalise d'après les entrées lues (dates de
   publication, de revue, page pleine). Le contrôle générique ne suffit pas : il faut décider si
   ce filtre reste dans la collecte (et lit alors le lecteur) ou passe à l'import.
3. **Un pré-jugement complet de ce que ferait l'import** (`clipping`, `tldr`, `zotero`) :
   `find_rejection_reason` (`clipping.py:306`) convertit chaque clip avec `EPOCH` comme date de
   collecte pour savoir si l'import le rejetterait ; `find_refusal` (`tldr.py:161`) lit les
   articles pour comparer la date d'édition au jour demandé ; `fetch` de Zotero valide chaque
   document par `check_document`, qui valide le même `ZoteroDocument` que `convert_document`.

### `zotero.py` (463 l.) — trois niveaux

Le plus gros fichier de l'ETL : la requête SQL d'extraction (85 lignes de constante,
`zotero.py:76-161`), la couche d'entrées-sorties (copie du fichier, `integrity_check`, dossier
temporaire), puis les modèles Pydantic et les convertisseurs. La coupe E / T de l'étape 6 est
nette et porte sur des blocs contigus.

`ZoteroDocument` est validé deux fois, avec deux traitements d'erreur : `check_document`
(`zotero.py:414`) transforme la `ValidationError` en `ValueError` avec la position, et
`convert_document` (`zotero.py:423`) relève l'erreur sans valeurs. L'étape 6 doit trancher
laquelle survit.

`check_integrity` et `read_file_state` n'ont pas de docstring.

### `clipping.py` (397 l.) — trois niveaux

`fetch` (51 l.) fait la liste des clips, le filtre de marge dans les deux sens, le filtre des
clips non stabilisés, la lecture, puis le pré-jugement par `find_rejection_reason`. Les trois
niveaux du module : l'entrée-sortie fichier (`list_clip_files`, `read_clip_file`,
`read_changed_at_ns`, `check_clip_size`, `make_page_name`), l'analyse du clip (`read_clip`,
`split_frontmatter`, `describe_yaml_error`), le modèle et ses validateurs.

Deux noms coûtent un aller-retour :
- `read_absent` (`clipping.py:321`) rend `None` si la valeur est un marqueur d'absence, et la
  valeur sinon : le nom dit qu'on lit une absence. Il est d'ailleurs utilisé comme prédicat
  (`if read_absent(value) is None`, `clipping.py:341`). `none_if_absent` dirait ce qu'il fait.
- `to_ns` (`clipping.py:159`) est une abréviation hors des usages établis par `code.md`
  (`id`, `url`).

La docstring du module est coupée en plein milieu (`clipping.py:7-8`), celle de
`ClipTooLargeError` aussi (`clipping.py:76-77`).

### `gh_archive.py` (387 l.) — trois niveaux

La requête BigQuery, la conduite de la requête (sandbox, dry run, plafond d'octets, fenêtres), et
la lecture du résultat brut. `read_trends` (34 l., `gh_archive.py:309`) valide par Pydantic puis
fait quatre contrôles de cohérence (ordre strict des fenêtres, fenêtre annoncée, doublon
`(fenêtre, dépôt)`, nombre de lignes par fenêtre) : le nom dit « lire », la fonction lit et
contrôle. `describe_validation_error`, `describe_location_part` et `describe_value` forment un
troisième petit niveau, celui de la description d'une erreur.

`describe_value(value: object, field: object)` (`gh_archive.py:371`) type `field` en `object`
alors qu'il est comparé à un `frozenset` de noms de champs.

Sept fonctions publiques sans docstring, dont `configure_query`, `encode_result` et
`compute_bytes_cap`.

### `tldr.py` (325 l.) — la chaîne la plus longue des sources

`TldrSource` porte trois méthodes (`fetch`, `read_pages`, `refuse`) alors que toutes les autres
sources n'en portent qu'une. `fetch` (54 l.) jongle avec quatre dictionnaires ou listes
(`read_pages`, `pages`, `refusals`, `today_refusal`) et trois politiques de refus selon la place
du jour refusé dans la fenêtre. La chaîne interne va à 5 : `read_pages` → `find_refusal` →
`read_articles` → `read_article` → `read_text`.

`read_articles` a une ligne de docstring de 122 caractères (`tldr.py:226`), trace d'une édition.

### `arxiv.py` (237 l.)

`parse_feed` est appelé trois fois sur les mêmes octets (`count_papers`, `read_total_results`,
`read_papers`) : le même XML est analysé trois fois par collecte. Lecture : le parcours de `fetch`
ne se lit pas comme une suite d'étapes sur une donnée, mais comme trois questions posées au brut.

`arxiv.py:83` lit l'horloge directement dans `fetch` (`datetime.now(UTC)`), sans fonction nommée,
contrairement aux trois autres sources qui lisent l'heure (voir ci-dessous).

### `cisa_kev.py` (217 l.) — un paramètre mort et une docstring qui dit le contraire du code

`read_new_vulnerabilities(raw_catalog, last_collected_at)` (`cisa_kev.py:117`) filtre les
vulnérabilités ajoutées depuis la dernière collecte. **Son unique appelant de production,
`read_catalog` (`cisa_kev.py:212`), passe toujours `last_collected_at=None`** : le filtre n'est
atteint que par les tests (`tests/etl/sources/test_cisa_kev.py`, 11 appels). La branche de filtre
est donc du code que la production n'exécute jamais.

Et la docstring du module (`cisa_kev.py:5-6`) annonce : « Read the vulnerabilities of a raw CISA
KEV catalog **that were added since the last collection** » — alors que `read_catalog` lit le
catalogue entier et que sa propre docstring le dit (`cisa_kev.py:211`). Le lecteur du module reçoit
d'abord l'affirmation fausse.

### `github_most_starred.py` et `github_most_forked.py` — jumeaux, trois noms pour une lecture

Les deux modules sont presque identiques, au champ compté près (`stars` / `forks`). Deux
occurrences : `code.md` dit de ne pas factoriser avant la troisième. À laisser.

Mais chacun expose trois noms pour lire le même brut :
- `read_most_starred(raw, expected_size)` : la lecture réelle ;
- `read_ranking(raw)` : enveloppe d'une ligne, sans docstring, qui fixe `expected_size` ;
- `read_top_entries(raw, expected_size=RANKING_SIZE)` : la même lecture rendue en `TopEntry`.

`read_ranking` existe en trois exemplaires dans le dépôt, avec trois signatures différentes :
`github_most_starred.py:129`, `github_most_forked.py:109`, et `post/top_sheets.py:87`
(`read_ranking(store, top, key) -> Ranking | None`). Le nom ne dit plus lequel on lit.

### `github_releases.py` (191 l.) et `github_advisories.py` (202 l.) — les plus réguliers

Les deux seules sources dont la lecture reste à deux niveaux. `fetch` y mêle quatre choses (la
requête, la lecture de contrôle, le filtre par date, l'avertissement de page pleine) sur 40 et
48 lignes, mais chaque chose tient en deux ou trois lignes lisibles.

`parse_release` (42 l.) et `parse_advisory` (38 l.) sont de longues suites de contrôles de type
`isinstance` : un seul niveau, répétitif mais explicite. À laisser.

### Vocabulaire incohérent d'une source à l'autre

- **`read_text` défini deux fois, avec des comportements opposés sur une absence** :
  `arxiv.py:214` lève `ValueError` si le champ est vide ou absent ; `tldr.py:288` rend `""` si
  l'élément est absent. Même nom, même rôle apparent, règle inverse.
- **Quatre lectures de l'horloge, trois formes** : `current_day()` identique à l'octet près dans
  `tldr.py:177-178` et `gh_archive.py:181-182` ; `current_time()` dans `clipping.py:155-156` ;
  `datetime.now(UTC)` en ligne dans `arxiv.py:83`. Les tests remplacent ces fonctions par module
  (12 `monkeypatch.setattr` dans `tests/`) : c'est ce découpage par module qui rend chaque source
  testable seule. La duplication est réelle (troisième occurrence atteinte) mais la centraliser
  ferait d'un remplacement le remplacement de toutes les sources à la fois.
- `read_` sert à trois choses dans `etl/` : lire des octets de `raw/` (`read_page`,
  `read_collection`), analyser un brut déjà en mémoire (`read_articles`, `read_catalog`,
  `read_documents`), et accéder à un champ (`read_collected_at`, `read_file_state`,
  `read_absent`).

### Mise en forme

Trois lignes dépassent 100 caractères, toutes dans des docstrings : `source_kinds.py:5` (130),
`sources/tldr.py:226` (122), `sources/cisa_kev.py:124` (113). Quatre docstrings sont coupées en
plein milieu d'une phrase : `transform.py:72-73`, `load.py:312-314`, `clipping.py:7-8`,
`clipping.py:76-77`. Toutes sont des traces d'éditions : `ruff format` ne recoupe pas l'intérieur
d'une docstring, et rien ne le vérifie. Le relevé des coupures est heuristique, il n'est
peut-être pas exhaustif.

## 4. Ce qui est déjà conforme

À ne pas rouvrir : `pipeline.py` est exactement la table des matières que `code.md` demande ;
`rejections.py`, `normalize.py`, `raw_purge.py`, `http_download.py`, `source_contract.py`,
`collected_sources.py` tiennent un seul niveau ; les docstrings de module existent partout et
portent le pourquoi avec sa source datée ; les messages de journal citent l'observé, jamais le
supposé.

## 5. Chantiers, classés par rapport gain / coût

« Mécanique » = déplacement ou réécriture sans changement de comportement, tests inchangés.
« Découpage » = nouvelles fonctions ou nouveaux modules, imports de tests à réécrire.
« Comportement » = ce que fait le code change ; Sabine décide.

| # | Chantier | Gain de clarté | Coût | Étape |
|---|---|---|---|---|
| 1 | Corriger la docstring de `list_file_keys` (`raw_store.py:78-80`) : deux faits faux | fort (une référence fausse égare durablement) | mécanique, 1 ligne | hors étapes |
| 2 | Corriger la docstring de module de `cisa_kev.py` : elle dit le contraire du code | fort | mécanique, 2 lignes | hors étapes |
| 3 | Les 3 lignes trop longues et les 4 docstrings coupées | moyen | mécanique | hors étapes |
| 4 | Docstrings des portes sans docstring : `read_collection`, `read_page`, `collect_one_source`, `join_writings`, `write_file`, `load_last_collection_dates`, `save_last_collection_dates`, `parse_collection_name` | fort (les portes de trois modules) | mécanique | hors étapes |
| 5 | Valeurs par défaut de `FileWriting` : −25 lignes de littéraux dans `load.py` | fort | mécanique (aucun test ne le construit) | hors étapes |
| 6 | Renommer `RawReadings` → `ImportReadings` ; `read_collected_at` → clé de tri nommée ; `read_absent` → `none_if_absent` ; `to_ns` → `to_nanoseconds` | fort | mécanique | hors étapes |
| 7 | Renommer l'un des deux `read_text` (`arxiv` / `tldr`), de règle inverse | fort | mécanique | étape 7 |
| 8 | Donner à `arxiv` la fonction d'horloge nommée que les trois autres sources ont | moyen | mécanique | hors étapes |
| 9 | Les trois noms de lecture des tops (`read_most_starred` / `read_ranking` / `read_top_entries`) et les trois `read_ranking` du dépôt | fort | découpage léger | étape 8 |
| 10 | Sortir le contrôle des noms de chemin de `collect_one_source` | moyen | découpage léger | hors étapes |
| 11 | Couper les cinq niveaux de `load.py` (transaction / ordre / fichier / règle de source) | fort | découpage ; `tests/etl/test_load.py` fait 2 047 lignes mais n'importe que 3 noms de `load` | hors étapes (voir §6) |
| 12 | `read_trends` de `gh_archive` : séparer la validation Pydantic des quatre contrôles de cohérence | moyen | découpage léger | étape 7 |
| 13 | `raw_store.py` : une seule façon de nommer un fichier (clé), les 4 fonctions à `Path` comprises | fort | découpage, touche `extract.py` et `tests/etl/test_raw_store.py` (9 noms importés) | **étape 3 bis** |
| 14 | Le paramètre `last_collected_at` de `read_new_vulnerabilities`, mort en production | moyen (une branche que la production n'atteint pas) | comportement (ou test à réécrire) | hors étapes, décision de Sabine |
| 15 | Rompre le lien E → T dans les dix `fetch` | fort (c'est la condition de la cible) | comportement, source par source | **étapes 6 et 7** |
| 16 | Découper `zotero.py`, puis les autres sources, en `extract.py` / `transform.py` | fort | découpage, après 15 | **étapes 6 et 7** |
| 17 | Séparer dans `Top` la collecte et le rendu | moyen | découpage, touche `etl/tops.py`, la composition et `post/top_sheets.py` | **étape 8** |

Les chantiers 1 à 10 et 12 sont des corrections de lisibilité sans incidence sur la cible : ils
peuvent se faire en un seul commit, avant ou après n'importe quelle étape. Les chantiers 13, 15,
16 et 17 sont les étapes du plan.

## 6. Position par rapport aux étapes 3 bis, 6, 7 et 8

### Étape 3 bis — confirmée, et son périmètre est plus large que ce que le plan écrit

Le plan dit : « Tout `raw_reading.py` lit le brut via `RawStore` ». Le relevé le confirme : c'est
bien `raw_reading.py` qui lit `raw/` aujourd'hui.

Mais la condition que la règle 3 de `poc.md` poursuit — « le stockage change sans toucher aux
appelants » — n'est pas tenue par ce seul passage : `raw_store.py` garde quatre fonctions à `Path`
(`write_file_atomically`, `write_new_raw_file`, `load_last_collection_dates`,
`save_last_collection_dates`), et c'est la **collecte** (`extract.py`) qui les appelle. Après
l'étape 3 bis, l'import lirait par clé et la collecte écrirait par `Path` : le module porterait
toujours deux vocabulaires, et le passage du brut à Azure Blob Storage toucherait encore
`extract.py`.

**Proposition** : l'étape 3 bis décide aussi du sort des quatre fonctions à `Path`, ou le plan
note explicitement que l'écriture reste sur `Path` jusqu'à une étape nommée. La règle 3 de
`poc.md` ne contraint aujourd'hui que les fonctions *nouvelles* de `raw_store.py`, donc rien n'est
enfreint : c'est un choix à écrire, pas une dette.

### Étape 6 (pilote Zotero) — confirmée dans sa cible, son point ouvert est plus gros qu'écrit

La coupe E / T de `zotero.py` est nette : la requête SQL et la couche de copie d'un côté, les
modèles Pydantic de l'autre, sur des blocs contigus. Le déplacement est mécanique.

Le plan §8 nomme un point ouvert : le contrôle à la collecte passe de la source à
`etl/extract.py`, et une sorte sans aucun lecteur n'a rien à contrôler. Le relevé ajoute deux
choses que le plan ne dit pas :

1. Pour Zotero, le contrôle à la collecte n'appelle pas le `READER` de la sorte, mais
   `check_document`, une **seconde validation du même `ZoteroDocument`** avec un autre traitement
   d'erreur. Un contrôle générique dans `etl/extract.py` qui appellerait `READER.read_entries` +
   `READER.convert` remplacerait `check_document` — et changerait le message d'erreur de la
   collecte. L'étape 6 doit le trancher, pas seulement traiter le cas des sortes sans lecteur.
2. `fetch` de Zotero lit aussi le résultat de la lecture pour sa ligne de journal (nombre de
   documents et de surlignages, `zotero.py:226-230`) et compare l'extrait au dernier brut
   (`store.read_latest`, `zotero.py:234`). Le premier usage disparaît si le contrôle part ; le
   second est une dépendance de la collecte au `RawStore`, indépendante du côté T.

**Verdict : l'étape 6 est confirmée ; son point ouvert est à élargir** au choix entre « le
contrôle générique appelle le `READER` » et « chaque source garde son contrôle ». Ce choix
commande le travail des neuf autres sources.

### Étape 7 (généraliser) — confirmée, et le relevé lui donne un ordre

Le plan dit « une par commit », sans ordre. Le coût réel par source est le lien E → T, pas le
déplacement. L'ordre du moins coûteux au plus coûteux, d'après la partie 3 :

1. `github_most_starred`, `github_most_forked`, `gh_archive` : `fetch` jette le résultat du
   lecteur, seule l'exception compte.
2. `cisa_kev` : idem, une fois le chantier 14 tranché.
3. `github_advisories`, `github_releases`, `arxiv` : `fetch` lit les entrées pour filtrer et
   avertir ; il faut décider où va ce filtre.
4. `zotero` (le pilote), puis `tldr` et `clipping` : `fetch` pré-juge ce que ferait l'import.

Faire le pilote sur Zotero reste défendable (c'est la source dont la coupe de fichier est la plus
nette), mais ce n'est pas la source dont le lien E → T est le plus simple : si le but du pilote est
de valider la **règle 3**, un classement GitHub la validerait plus vite.

**Verdict : l'étape 7 est confirmée ; le plan gagne une ligne d'ordre**, et l'étape 7 absorbe
deux chantiers de nommage (7 et 12) qu'il vaut mieux faire au moment du découpage : une fois les
sources en paquets, `arxiv/transform.py:read_text` et `tldr/transform.py:read_text` auront le même
nom à deux endroits, avec des règles inverses — le découpage cache le problème au lieu de le
régler.

### Étape 8 (collecte / rendu dans `Top`) — confirmée, son périmètre s'étend au nommage

Le plan §8 décrit l'étape : `Top` porte les mots de sa fiche et son lecteur, `TopEntry` est décrit
« as its sheet shows it », et la séparation touche `etl/tops.py`, la composition et
`post/top_sheets.py`. Le relevé le confirme et ajoute que le nommage fait partie du même nœud :
`read_most_starred` / `read_ranking` / `read_top_entries` dans chaque source, `Top.read_entries`
homonyme de `SourceReader.read_entries`, et trois `read_ranking` de signatures différentes dans le
dépôt. Ces noms sont précisément la couture collecte / rendu que l'étape 8 doit défaire.

**Verdict : l'étape 8 est confirmée ; elle règle aussi le nommage** (chantier 9).

### Aucune étape n'est remplacée

Le relevé ne contredit ni la cible de `plan.md` §1, ni ses six règles, ni l'ordre des étapes. Il
ajoute un chantier que le plan ne couvre pas et qui ne dépend d'aucune étape : **les cinq niveaux
de `load.py`** (chantier 11). `load.py` est le plus gros module du pipeline et le plus profond de
tout l'ETL, et `plan.md` §5 décide seulement de ce qui **reste** dans le load (`import_items`,
`commit_with_log`, `join_writings`, `list_files_in_collection_order`, les règles de retrait CISA
et Zotero) — jamais de la façon dont le module se lit. À inscrire au plan comme chantier hors
étapes, ou à écarter explicitement.

## 7. Ce que je n'ai pas pu vérifier

- **Lint, format et typage** : `uv run ruff check --no-cache`, `uv run ruff format --check` et
  `uv run mypy --strict` n'ont pas pu être lancés. `uv` échoue dans le bac à sable de la session
  (`Failed to initialize cache at ~/.cache/uv: Operation not permitted`). Les tests
  ont été lancés par `.venv/bin/python3 -m pytest` : 2 288 passés, 1 échec, celui-ci dû au bac à
  sable (voir en tête). Les trois lignes de plus de 100 caractères et les docstrings coupées sont
  relevées par mes propres scripts, pas par `ruff`.
- **Le relevé des docstrings coupées en plein milieu est heuristique** (une ligne nettement plus
  courte que la largeur de coupe suivie d'une ligne qui commence en minuscule) : il peut en
  manquer, et il a produit deux faux positifs que j'ai écartés à la lecture.
- **Les tests de bout en bout** (`-m e2e`) n'ont pas été lancés : ils interrogent les sources
  réelles, et celui de `gh_archive` lance une requête BigQuery facturable.
- **Le coût des chantiers 11, 13, 15, 16 et 17 n'est pas mesuré en diff** : je donne le nombre de
  noms que les tests importent de chaque module (`tests/etl/test_load.py` importe 3 noms de
  `load`, `tests/etl/test_raw_store.py` 9 de `raw_store`, `tests/etl/sources/test_gh_archive.py`
  13 de `gh_archive`, `test_zotero.py` et `test_clipping.py` 9 chacun), pas le nombre de lignes de
  test à réécrire.
- **Je n'ai pas vérifié** si le paramètre `last_collected_at` de `read_new_vulnerabilities` a eu
  un appelant de production dans le passé : `read_catalog` apparaît au commit `6a4213b`
  (« refactor: move the pipeline into etl/ and config into core/ »), et je n'ai pas remonté
  l'historique au-delà.
- **Les docstrings et commentaires qui citent une décision datée** n'ont pas été recoupés avec le
  journal ADR, hormis les références de fichiers (toutes résolues, sauf celle du chantier 1).
