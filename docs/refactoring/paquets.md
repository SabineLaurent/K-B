# Regrouper `etl/` en paquets — relevé

Relevé du 2026-10-23, branche `refactoring/etl`, commit `7abb73b`. Analyse en lecture seule :
aucun fichier du dépôt n'a été modifié pour l'écrire, celui-ci excepté.

**L'idée évaluée.** Regrouper les modules de `src/k_b/etl/` en quatre paquets — `etl/extract/`,
`etl/transform/`, `etl/load/` (chaque stage avec ses aides, dont les modules du chantier 11) et
`etl/raw/` (la zone d'atterrissage : l'accès au brut et à l'état de collecte, la purge, le format
des noms de collecte) — comme `database/` pour la base, le reste (`pipeline.py`, le vocabulaire
partagé, la composition, `sources/`) restant à la racine de `etl/`.

Le relevé du chantier 11 (`lisibilite.md`, et le compte rendu du 2026-10-23) avait écarté
`etl/load/` seul ; ce document reprend la question à l'échelle de tout `etl/`. Les constats sont
factuels, les propositions de la partie 6 sont des propositions.

**État de départ.** `etl/` tient 17 modules à sa racine (1 924 lignes) plus le paquet `sources/`.
Les trois autres couches de K-B sont bâties de la même façon : une racine de modules plats, et des
paquets qui rassemblent des **pairs d'une même sorte**.

| Couche | Modules à la racine | Paquets |
|---|---|---|
| `etl/` | 17 | `sources/` (11 sources + 2 modules partagés) |
| `ai_api/` | 9 | `routers/`, `schemas/`, `connectors/`, `stages/` |
| `database/` | 6 | `writers/` (un module par sorte d'item) |
| `data_api/` | 5 | `routers/`, `schemas/` |

Aucun paquet de K-B ne rassemble aujourd'hui **un module et ses aides** : tous rassemblent des
pairs interchangeables (une source, un écrivain, un routeur, un schéma, une étape de l'API IA).
L'idée introduirait donc un second principe de rangement, dont `database/` est le seul précédent —
et `database/` est une **couche**, pas une étape à l'intérieur d'une couche. `etl/` est déjà
l'équivalent de `database/` : c'est la couche métier et ETL de la règle 5 de `conventions.md`.

## 1. Classement de chaque module

`src` = fichiers de `src/` qui l'importent, `tests` = fichiers de `tests/` qui l'importent (relevé
par `grep` sur `k_b.etl.<module>` et `k_b.etl import <module>`).

| Module | l. | src | tests | Classement | Raison |
|---|---|---|---|---|---|
| `extract.py` | 112 | 1 | 4 | `extract/` | le stage 1 lui-même |
| `http_download.py` | 74 | 4 | 6 | **hésite** | aide **des sources**, pas du stage : `extract.py` ne l'importe pas |
| `user_agent.py` | 5 | 1 | 2 | avec `http_download.py` | son seul importateur |
| `transform.py` | 158 | 1 | 6 | `transform/` | le stage 2 lui-même |
| `raw_reading.py` | 211 | 1 | 0 | `transform/` | importé par `transform.py` seul ; classement net |
| `normalize.py` | 33 | 2 | 4 | **hésite** | étape du transform, mais aussi importée par `sources/clipping.py` |
| `load.py` | 384 | 1 | 5 | `load/` | le stage 3 lui-même |
| `import_log.py` | 89 | 1 | 2 | `load/` | importé par `load.py` seul ; classement net |
| `file_loading.py`, `withdrawals.py` (chantier 11) | 146 + 59 | 1 | 0 | `load/` | créés par le chantier 11, appelés par le load seul |
| `raw_store.py` | 212 | **24** | 11 | **hésite** | trois rôles dans un module (ci-dessous) |
| `raw_purge.py` | 39 | 1 | 1 | `raw/` | la rétention, hors des trois stages (cible, §1) |
| `COLLECTION_NAME_FORMAT`, `parse_collection_name` | 10 | 4 | — | `raw/` | le nom d'une collecte ; aujourd'hui dans `raw_files.py` |
| `raw_files.py` (le reste) | 63 | 8 | 4 | racine | vocabulaire des trois stages **et** de `post/top_sheets.py` |
| `pipeline.py` | 111 | 2 | 1 | racine | la porte des deux parcours pour `commands/` |
| `rejections.py` | 20 | 3 | 1 | racine | chemin unique d'un rejet, partagé par deux stages |
| `source_contract.py` | 140 | 15 | 13 | racine | contrat lu par les sources, les stages, la composition |
| `tops.py` | 33 | 4 | 5 | racine | partagé avec `post/` et la composition |
| `source_kinds.py`, `collected_sources.py` | 109 + 121 | 3 + 4 | 13 + 4 | racine | la composition (déjà sa propre liste) |

### Les classements qui hésitent

**`raw_store.py` — le vrai point dur.** Vingt-quatre fichiers de `src/` l'importent : c'est le
module le plus importé de tout `etl/`, et ses clients ne sont pas ceux d'une zone
d'atterrissage. Il porte trois choses :

1. `write_file_atomically` — l'**unique** fonction d'écriture de fichier du dépôt (règle 2 de
   `conventions.md`), appelée par `post/vault_files.py`, `commands/openapi_command.py` et
   `etl/import_log.py` ;
2. `RawStore`, `RAW_DIR_NAME(S)`, `find_stream`, l'état de collecte — la zone d'atterrissage
   proprement dite : `pipeline.py`, `extract.py`, `load.py`, `raw_reading.py`, `raw_purge.py`,
   `collected_sources.py`, `post/top_sheets.py`, et 3 commandes ;
3. `AUTOMATED_WATCH_DIR_NAME`, `SELECTED_LIBRARY_DIR_NAME`, `make_source_folder_key` — le nom du
   dossier où une source écrit, importé par **10 des 11 sources** et par `source_kinds.py`.

Un paquet `etl/raw/` serait donc importé par `post/`, par quatre commandes et par presque chaque
source. L'analogie avec `database/` se rompt là : `database/` n'est importé que par la couche
immédiatement au-dessus, alors que la zone d'atterrissage est lue par tout ce qui nomme un dossier
de `raw/` ou écrit un fichier. Avant de faire `etl/raw/`, il faut décider où vont (1) et (3) :
sinon le paquet naît avec 24 clients, dont deux couches qui n'ont rien à y faire.

**`raw_files.py` et son nom à côté d'un paquet `raw/`.** Le module ne contient aucun fichier :
c'est le vocabulaire de ce que l'import a **lu** (`Rejection`, `RawFile`, `RawReading`,
`TrendFile`, `TrendReading`, les deux jointures) plus le format du nom d'une collecte. Avec un
paquet `etl/raw/` à côté, le dépôt aurait deux « raw » au même niveau, dont celui qui ne stocke
rien s'appellerait `raw_files` : c'est exactement la faute que le relevé de lisibilité reproche à
`RawReading`/`RawReadings`, un nom qui oblige à aller voir sa définition. Trois conséquences, à
accepter ensemble ou à renoncer au paquet :

- le format du nom (`COLLECTION_NAME_FORMAT`, `parse_collection_name`) part dans `etl/raw/` :
  4 sites (`extract.py`, `pipeline.py`, `raw_reading.py`, `post/top_sheets.py`) ;
- le reste est renommé, par exemple `etl/readings.py` (ce que l'import a lu) : 8 fichiers de
  `src/`, 4 de `tests/` ;
- la règle 1 de `conventions.md` cite `etl/raw_files.py` deux fois comme le foyer de `Rejection` :
  amendement obligatoire.

**`http_download.py` et `user_agent.py` — mal classés par la cible.** `plan.md` §1 les annonce
« aide à l'extract », mais l'import dit autre chose : `extract.py` ne les importe pas ; ce sont
`sources/{tldr,cisa_kev,arxiv,github_api}.py` qui importent `http_download`, et
`http_download` seul qui importe `user_agent`. Les mettre dans `etl/extract/` ferait importer le
paquet du stage **par les sources**, c'est-à-dire par la couche au-dessus de lui — sans cycle (le
stage n'importe jamais les sources, règle 2 du plan), mais à contresens de la lecture. Leur place
est `sources/`, à côté de `sources/github_api.py` que la cible qualifie déjà de « partagé entre
sources ». `etl/extract/` ne tiendrait alors qu'un module : `extract.py`, 112 lignes.

**`normalize.py`** est une étape du transform (cible, §1) mais `sources/clipping.py` l'importe
aussi — c'est la « double normalisation des clips » que `plan.md` §4 garde à vérifier à part. Le
paquet ne la règle pas ; il la rend visible, ce qui est un petit gain.

**`raw_purge.py`** va dans `raw/` sans hésitation, mais son logger `k_b.etl.raw_purge` est lu par
un test (partie 4).

## 2. Les modules d'entrée des paquets

Contrainte dure : `test_every_package_of_k_b_has_an_empty_init`
(`tests/architecture/test_packages.py`) impose un `__init__.py` **vide** dans tout paquet — « a
package gathers its modules, it never re-exports them ». Donc `from k_b.etl.load import
import_items` cesse de fonctionner dès que `load` devient un paquet : la porte descend dans un
module nommé, et ce nom entre dans tous les imports, dans le nom du logger et dans les tests.

| Nommage | Exemple d'import | Logger | Apporte | Coûte |
|---|---|---|---|---|
| (a) `<paquet>/stage.py` | `from k_b.etl.load.stage import import_items` | `k_b.etl.load.stage` | symétrie parfaite : la question « où est le stage ? » a une réponse unique ; précédent maison des deux `app.py` (`ai_api`, `data_api`) | trois fichiers homonymes (`grep`, onglets, traces d'erreur ambigus) ; « stage » entre dans le vocabulaire des noms de fichiers, où il n'est pas |
| (b) `<paquet>/<métier>.py` : `collection.py`, `reading.py`, `transaction.py` | `from k_b.etl.load.transaction import import_items` | `k_b.etl.load.transaction` | chaque nom dit le travail : `transaction.py` est juste, le stage 3 **est** la transaction | deux des trois noms collisionnent avec des mots déjà pris : une « collection » est un dossier de `raw/`, et `transform/reading.py` voisinerait `transform/raw_reading.py` et `database/reading.py` ; plus de symétrie entre les paquets |
| (c) `<paquet>/<paquet>.py` : `load/load.py` | `from k_b.etl.load.load import import_items` | `k_b.etl.load.load` | rien | bégaiement que « nommer pour le lecteur » (`code.md`) refuse ; écarté d'emblée |
| (d) paquets suffixés : `load_stage/load.py` | `from k_b.etl.load_stage.load import import_items` | `k_b.etl.load_stage.load` | les modules **gardent leur nom** : `git log --follow` suit, les diffs et les citations de docs sont plus petits ; supprime la collision avec `sources/<source>/extract.py` (ci-dessous) | le mot est répété une fois dans le chemin pointé ; un suffixe de type dans un nom de paquet, qu'aucun paquet de K-B n'emploie (`writers/`, `routers/`, `schemas/`, `connectors/`, `stages/`, `sources/` : tous des noms de rôle au pluriel) |

**Une collision que (a), (b) et (c) créent et que (d) évite.** Les étapes 6 et 7 du plan créent
`etl/sources/<source>/extract.py` et `transform.py`, un couple par source. Avec `etl/extract/` et
`etl/transform/`, les mots « extract » et « transform » nommeraient deux choses différentes à deux
niveaux : le stage, et le côté E ou T d'**une** source. C'est la faute que le relevé de lisibilité
compte trois fois ailleurs (trois `read_ranking`, deux `read_text`, trois sens de `read_`). Le
paquet `etl/load/` n'a pas ce problème : aucune source n'a de `load.py`, c'est la règle 1 du plan.

**Verdict de la partie 2.** Aucun nommage n'est bon partout : (a) est le seul symétrique mais
multiplie les homonymes et alourdit tous les loggers ; (b) ne vaut que pour le load
(`transaction.py`) ; (d) est le moins cher et le seul compatible avec les étapes 6-7, au prix d'un
suffixe sans précédent maison. Le fait qu'un nommage uniforme n'existe pas est en soi un indice :
les quatre paquets ne sont pas quatre choses de même nature.

## 3. Ce que gagnent les tests d'architecture

### La règle des stages couvrirait les aides

Aujourd'hui, `ETL_STAGE_MODULES = {"etl.extract", "etl.transform", "etl.load"}`
(`tests/architecture/test_layers.py:119`) ne lie que **trois** modules : rien n'empêche
`import_log.py` d'importer `transform.py`, ni `raw_reading.py` d'importer `load.py`. Les aides
sont hors de la règle de l'étape 5, et les deux modules du chantier 11 le seraient aussi.

Avec des paquets, la couverture devient **structurelle** et gratuite : `list_python_files`
(`module_imports.py`) fait un `rglob` sur un paquet, et `parse_imported_modules` coupe les noms à
deux niveaux, donc `from k_b.etl.load.import_log import …` se lit `etl.load` — le stage lui-même,
autorisé, tandis que `etl.transform` reste refusé. La règle passerait de 3 à 10 modules sans une
ligne de test nouvelle, et un fichier ajouté dans un paquet serait lié d'office.

**Mais le même gain s'obtient sans déplacer un fichier**, par une liste déclarée. Essayé sur une
copie des deux fichiers de test, hors du dépôt :

```python
# module_imports.py — les modules de chaque stage : le stage et les aides qui tournent sous lui.
ETL_STAGE_MODULES_BY_STAGE = {
    "etl.extract": {"etl.extract", "etl.http_download", "etl.user_agent"},
    "etl.transform": {"etl.transform", "etl.raw_reading", "etl.normalize"},
    "etl.load": {"etl.load", "etl.import_log"},  # + file_loading, withdrawals au chantier 11
}
```

`list_imports_of_another_stage` prend alors l'union des modules des **autres** stages, et
`test_no_stage_of_the_etl_imports_another_stage` boucle sur les modules de chaque stage.
Résultat : **35 tests de `test_layers.py` passés**, et la contre-épreuve donne 8 cas sur 8
attendus — `etl.load` important `etl.normalize` ou `etl.raw_reading` est refusé, `etl.load`
important `etl.import_log` (son aide), `etl.raw_files` ou `etl.raw_store` reste permis.

Différence honnête entre les deux : avec un paquet, l'appartenance est **structurelle** (personne
ne peut l'oublier) ; avec la liste, elle est **déclarée** (un module nouveau doit y être inscrit,
et `test_every_module_of_etl_is_in_exactly_one_list` ne force que son inscription dans
`ETL_PIPELINE_MODULES`, pas dans un stage). Le trou subsiste, mais il est nommé, et il coûte
quinze lignes au lieu de quarante-huit fichiers.

### « Seul `raw/` touche le brut » : la règle visée n'est pas celle qui est atteignable

La règle 3 de `poc.md` se vérifie aujourd'hui par un `grep` de primitives de système de fichiers
(`read_bytes`, `write_text`, `glob`, `unlink`, `exists`, `open(`, `shutil.`…) avec
`grep -v etl/raw_store.py`, et une liste de fichiers à comparer à l'œil. Sa sortie du jour tient
**dix** fichiers, dont les six entrés depuis `9e6e2e8` sans la justification que la règle demande
(`plan.md` §8).

Un paquet `etl/raw/` ne suffit pas à en faire la règle annoncée, pour une raison qui ne dépend pas
du rangement : **neuf des dix fichiers touchent légitimement des fichiers qui ne sont pas le
brut** — la base (`database/creation.py`), la base source d'une source (`sources/zotero.py`), les
clips qui *sont* la source (`sources/clipping.py`), le coffre et le dossier de données
(`commands/`), le rejeu (`ai_api/connectors/llm_replay.py`). Un `grep` de primitives ne sait pas
quel chemin un appel touche ; il ne peut donc jamais dire « seul `raw/` touche le brut ».

Deux formulations atteignables, et ce qu'elles demandent :

- **« Seul `etl/raw/` nomme le brut »** — un test qui vérifie qu'aucun module hors du paquet ne
  porte `RAW_DIR_NAME`, les noms de dossiers d'acquisition ni `COLLECTION_STATE_FILENAME`. C'est
  la bonne règle, et elle **échoue aujourd'hui** : dix sources importent
  `AUTOMATED_WATCH_DIR_NAME`. Elle suppose donc d'abord de décider où vit ce vocabulaire (partie 1,
  point 3 de `raw_store.py`), ce qui est un chantier à part entière, pas un déplacement.
- **« Seul `etl/raw/` touche le système de fichiers, sauf cette liste »** — le `grep` d'aujourd'hui
  transformé en test : la liste des exceptions devient une constante nommée, chacune avec sa
  justification en commentaire, et un fichier nouveau **fait échouer un test** au lieu d'entrer
  dans une sortie que personne ne relit. C'est le vrai gain, il corrige le trou de `plan.md` §8 —
  et **il ne demande aucun paquet** : il s'écrit aujourd'hui contre `etl/raw_store.py`.

## 4. Le coût

### Imports à réécrire

| Paquet | Modules déplacés | `src/` | `tests/` |
|---|---|---|---|
| `etl/load/` | `load.py`, `import_log.py` (+ les 2 du chantier 11) | 2 fichiers / 2 lignes | 6 fichiers / 9 lignes |
| `etl/transform/` | `transform.py`, `raw_reading.py`, `normalize.py` | 3 fichiers / 4 lignes | 7 fichiers / 13 lignes |
| `etl/extract/` | `extract.py`, `http_download.py`, `user_agent.py` | 6 fichiers / 6 lignes | 8 fichiers / 16 lignes |
| `etl/raw/` | `raw_store.py`, `raw_purge.py` | **24 fichiers / 25 lignes** | 11 fichiers / 14 lignes |
| **Les quatre** | | **27 fichiers / 37 lignes** | **21 fichiers / 52 lignes** |

Soit 48 fichiers et 89 lignes d'import, plus 4 sites si le format du nom de collecte part dans
`raw/`. `etl/raw/` pèse à lui seul 38 des 48 fichiers. Les fichiers de `tests/` n'ont pas besoin de
changer de place : rien ne lie l'arborescence des tests à celle de `src/`, et les tests s'importent
entre eux par nom nu (`from test_items import …`).

Hors de `etl/`, les importateurs touchés sont `post/vault_files.py`, `post/top_sheets.py`, et
`commands/{collect,import,write_tops,openapi}_command.py` — tous par `raw_store`.

### Noms de logger qui changent, et tests qui les lisent

Cinq modules de `etl/` tiennent un `logging.getLogger(__name__)` : `extract.py`, `load.py`,
`raw_reading.py`, `raw_purge.py`, `rejections.py`. Trois changeraient de nom, et **cinq sites de
test les lisent** :

| Aujourd'hui | Après | Lu par |
|---|---|---|
| `k_b.etl.extract` | `k_b.etl.extract.<entrée>` | `tests/etl/test_extract.py:217`, `:391` (`caplog`), **`:263` (`assert error_record.name == "k_b.etl.extract"`)** |
| `k_b.etl.load` | `k_b.etl.load.<entrée>` | `tests/etl/test_load.py:1056` (`caplog`), **`tests/test_cli.py:1299`** : la chaîne exacte `INFO k_b.etl.load: import committed, log kept: '<nom>'` sur la sortie d'erreur |
| `k_b.etl.raw_purge` | `k_b.etl.raw.purge` | `tests/etl/test_raw_purge.py:143` (`caplog`) |
| `k_b.etl.rejections` | inchangé | — (la règle 1 de `conventions.md` fixe ce nom) |
| `k_b.etl.raw_reading` | `k_b.etl.transform.raw_reading` | aucun test |

`test_cli.py:1299` est la ligne qu'une utilisatrice lit dans son terminal : la changer est un
**changement de comportement**, pas un déplacement. Le précédent existe et donne la marche à
suivre : la note du 2026-10-23 (point 8) a assumé un changement de nom de logger parce qu'il
rendait le « où » plus exact, et l'a écrit. Ici le nom deviendrait plus exact aussi
(`k_b.etl.load.transaction` dit où le commit a lieu) — mais il faut la décision de Sabine et une
entrée de journal, pas un commit mécanique.

Un dernier site, à part : `tests/etl/test_load.py:976` remplace une cible **par chaîne**,
`monkeypatch.setattr("k_b.etl.import_log.write_file_atomically", …)`. Elle devient
`"k_b.etl.load.import_log.write_file_atomically"` — un `monkeypatch` par chaîne échoue bruyamment,
donc sans risque de passer inaperçu.

### Listes de `module_imports.py`

`ETL_PIPELINE_MODULES` passe de 15 entrées à 8 (`etl.pipeline`, `etl.extract`, `etl.transform`,
`etl.load`, `etl.raw`, `etl.raw_files`, `etl.rejections`, `etl.source_contract`, `etl.tops`),
`ETL_COMPOSITION_MODULES` et `ETL_SOURCES_PACKAGE` ne bougent pas.
`test_every_module_of_etl_is_in_exactly_one_list` continue de fonctionner tel quel :
`pkgutil.iter_modules` annonce un paquet comme un module. `ETL_STAGE_MODULES` reste un ensemble de
trois noms, et couvre désormais les paquets entiers.

### Amendements de `.claude/`

**Vingt-sept citations**, dans deux fichiers que seule Sabine modifie (`poc.md` ≈ 17,
`conventions.md` ≈ 10) :

- `conventions.md` règle 5 : la liste des modules d'`etl` (ligne 150-151, cinq noms), la puce de
  `pipeline.py` (ligne 170-171, quatre noms), et la commande
  `grep -c "execute" src/k_b/etl/load.py` (ligne 187) ;
- `conventions.md` règle 5, commande des commandes :
  `grep -nE "etl\.(extract|transform|load|normalize|import_log|raw_purge)" src/k_b/commands` —
  **friction nouvelle** : quatre commandes importent légitimement `etl.raw_store` ; si `raw` entre
  dans l'alternation, la commande se met à renvoyer des lignes et la convention est enfreinte à la
  lettre ; si `raw` n'y entre pas, le trou reste. À trancher avec la règle, pas après ;
- `conventions.md` règle 1 : `etl/raw_files.py`, deux fois, si ce module est renommé ;
- `poc.md` règle 3 : l'exclusion `grep -v etl/raw_store.py`, la liste des six fichiers de départ,
  les commentaires sur `etl/transform.py` et `etl/raw_reading.py`, et
  `grep -nA3 "^def " src/k_b/etl/raw_store.py` ;
- `poc.md` règle 4 : `etl/raw_store.py:39` ;
- `poc.md` règle 5 : `etl/raw_reading.py` (`read_collection`), `etl/transform.py:149`.

### Amendements du plan et des documents vivants

- `plan.md` §1 : l'arbre de la cible en entier ; §2 règles 1 à 4, qui nomment `etl/load.py`,
  `extract.py` et `transform.py` ; §4 étapes 3 bis, 6 et 7 ; §7 (la liste des règles à amender) ;
  §9 (chantiers 13 et 16).
- `docs/specs-collecte.md` (8 citations de chemins), `docs/registre-traitements.md` (3, dont
  `etl/raw_purge.py` : le registre RGPD nomme le fichier de la purge, que `conformite.md` exige
  « codée et testée »), `docs/requetes-extraction.md` (2), `docs/stockage.md` (1), `MEMORY.md` (1 :
  `src/k_b/etl/extract.py`, dans le problème connu des collectes simultanées).
- `lisibilite.md`, `inventaire.md`, `orchestration.md`, le journal d'ADR et les notes de
  journaling : documents datés, jamais réécrits (`plan.md` §6).

## 5. L'ordre le plus économique

**Par rapport au chantier 11.** Le chantier 11 crée deux modules (`file_loading`, `withdrawals`).
S'ils naissent à la racine puis déménagent dans `etl/load/`, ils bougent deux fois ; s'ils naissent
dans le paquet, une fois. La décision sur `etl/load/` doit donc être prise **avant** le chantier 11,
même si le paquet n'est pas fait : c'est le seul endroit de la séquence où le choix n'a pas de
surcoût. Dans l'autre sens, faire `etl/load/` d'abord et le chantier 11 ensuite ajoute un
déplacement de `load.py` et de `import_log.py` sans rien simplifier.

**Par rapport à l'étape 3 bis.** Le paquet n'apporte rien à l'étape 3 bis, et l'inverse non plus.
L'étape 3 bis change des **signatures** (une clé POSIX au lieu d'un `Path`), pas l'endroit où le
module vit ; tous les appelants passent déjà par `etl.raw_store`, et les déplacer dans
`etl/raw/store.py` n'en retire aucun. En revanche l'étape 3 bis, elle, prépare `etl/raw/` : elle
tranche le sort des quatre fonctions à `Path` (`lisibilite.md` §6), c'est-à-dire une partie de la
question « que contient la zone d'atterrissage ». Faire le paquet avant l'étape 3 bis réécrirait
les mêmes lignes deux fois.

**Ordre le moins cher, si l'idée est retenue en entier :**

1. le chantier 11, dans la forme choisie (plat ou `etl/load/`) ;
2. `write_file_atomically` hors de la zone d'atterrissage (partie 6), qui retire 3 clients à
   `raw_store` ;
3. l'étape 3 bis, qui fixe les signatures et le sort des fonctions à `Path` ;
4. la décision sur le vocabulaire des dossiers de `raw/` (10 sources) ;
5. `etl/raw/`, puis le renommage de `raw_files.py` ;
6. `etl/transform/` et `etl/extract/` — après les étapes 6 et 7, qui créent
   `sources/<source>/extract.py` : le nom des paquets dépend de cette collision.

Les points 5 et 6 arrivent donc après le 08/11, c'est-à-dire après la mise en ligne. Les faire
avant déplacerait des fichiers que les étapes 3 bis, 6 et 7 réécrivent.

## 6. Recommandation : faire en partie

**Ne pas faire** `etl/extract/` ni `etl/transform/`. Les deux paquets tiendraient surtout des
aides qui ne sont pas celles du stage (`http_download` et `user_agent`, appelés par quatre sources
et pas par `extract.py` ; `normalize`, appelée aussi par `sources/clipping.py`), `etl/extract/` ne
garderait qu'un module propre, et le mot « extract » entrerait en collision avec le
`sources/<source>/extract.py` des étapes 6 et 7. Coût : 10 fichiers de `src/`, 29 lignes de test,
un logger lu par trois sites. Gain : la couverture de la règle des stages, qui s'obtient autrement.

**Ne pas faire `etl/raw/` maintenant.** C'est 38 des 48 fichiers du coût total, son analogie avec
`database/` ne tient pas (24 clients, dont `post/` et quatre commandes), il n'apporte rien à
l'étape 3 bis, et la règle qu'il est censé rendre possible (« seul `raw/` touche le brut ») n'est
pas atteignable par un rangement. À reprendre après l'étape 3 bis, et seulement si les deux
questions de la partie 1 sont tranchées d'abord.

**Faire tout de suite les trois choses qui portent le gain sans le coût :**

1. **La règle des stages par liste déclarée** (`ETL_STAGE_MODULES_BY_STAGE`, partie 3) : la règle
   de l'étape 5 passe de 3 à 8 modules, puis 10 avec le chantier 11, pour une quinzaine de lignes
   dans `module_imports.py` et `test_layers.py`, zéro import réécrit, zéro logger changé. Vérifié :
   35 tests verts, contre-épreuve 8 cas sur 8. C'est le gain principal de l'idée, détaché d'elle.
2. **Le `grep` de la règle 3 de `poc.md` transformé en test**, avec sa liste d'exceptions nommées
   et justifiées (partie 3). Corrige le trou de `plan.md` §8 — six fichiers entrés sans
   justification — et ne demande aucun paquet.
3. **`write_file_atomically` (et `REFUSED_FOLDER_SYNC_ERRORS`) hors de `raw_store.py`**, vers
   `core/` : la fonction n'utilise que la bibliothèque standard, et `core/` est « le vocabulaire
   commun à toutes les couches » (règle 5 de `conventions.md`), donc le classement est juste.
   `post/vault_files.py` cesse d'importer `etl` pour écrire un fichier,
   `commands/openapi_command.py` et `etl/import_log.py` aussi : trois clients de moins pour la
   zone d'atterrissage, et un
   prérequis gratuit de tout futur `etl/raw/`. Coût : 4 fichiers de `src/`, et la règle 2 de
   `conventions.md` n'a pas besoin d'amendement (sa commande de vérification ne cite aucun chemin).

**Sur `etl/load/`, la seule part de l'idée qui soit défendable telle quelle : décider maintenant,
appliquer au chantier 11.** Les quatre modules du paquet seraient tous internes au load
(`import_log` n'a qu'un importateur, `file_loading` et `withdrawals` naissent au chantier 11), et
c'est le seul stage sans collision de nom avec les sources. Mais il change le nom du logger
`k_b.etl.load`, donc une ligne que l'utilisatrice lit, et il oblige à nommer un module d'entrée
dont aucun candidat n'est bon partout (partie 2).

Ma recommandation est **le découpage B à plat** (`etl/load.py`, `etl/file_loading.py`,
`etl/withdrawals.py`, `etl/import_log.py` à la racine) : il donne la même lisibilité, garde le
logger, ne touche aucune ligne de test, et laisse `etl/load/` possible plus tard, au prix d'un
déplacement de quatre modules que la liste déclarée rend de toute façon non urgent. Si Sabine
préfère le paquet, c'est au chantier 11 qu'il coûte le moins, avec `transaction.py` comme module
d'entrée, et il faut alors une entrée de journal pour le nom du logger.

## 7. Ce que je n'ai pas vérifié

- **Lint, format et typage** : `uv` échoue dans le bac à sable de la session
  (`Failed to initialize cache at /Users/sabine/.cache/uv: Operation not permitted`). Les tests
  ont été lancés par `.venv/bin/python3 -m pytest` : `tests/etl/test_load*.py`,
  `tests/architecture/` et `tests/etl/test_import_log.py`, 236 passés.
- **Aucun déplacement n'a été essayé** : les coûts d'imports sont des comptes de `grep`
  (`k_b.etl.<module>` et `k_b.etl import <module>`), pas des diffs. Un import que ces deux motifs
  ne voient pas (import dynamique, chaîne de caractères) m'échappe, sauf les deux cibles de
  `monkeypatch` par chaîne, cherchées à part.
- **La liste déclarée a été essayée sur une copie** de `module_imports.py` et `test_layers.py` dans
  le dossier temporaire de la session, contre le `src/` réel : 35 tests passés et 8 contre-épreuves
  conformes. Elle n'a pas été essayée avec les deux modules du chantier 11, qui n'existent pas.
- **Les tests de bout en bout** (`-m e2e`) n'ont pas été lancés.
- **Je n'ai pas cherché** si un classement proposé ici contredit une entrée du journal d'ADR
  antérieure au 2026-10-23 autre que celles que `plan.md` reprend.
