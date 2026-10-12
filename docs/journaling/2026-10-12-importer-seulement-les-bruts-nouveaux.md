# N'importer que les fichiers bruts pas encore importés

- **Date** : 2026-10-12
- **Branche** : `feat/incremental-import`
- **Issue** : #106
- **Fichiers principaux** : `src/k_b/import_items.py`, `src/k_b/raw_items.py`, `src/k_b/cli.py`,
  `src/k_b/database/reading.py`
- **Note précédente de la série** :
  [laisser la base dédoublonner les items](2026-10-12-laisser-la-base-dedoublonner-les-items.md)
  (#105), qui rendait cette PR possible.

## Le pourquoi

Avant cette PR, `kb import` relisait et revalidait tout `raw/` à chaque exécution. La collecte,
elle, est incrémentale : elle n'écrit que du brut nouveau. Relire tout le brut refaisait le
travail des imports précédents et remplissait le journal de doublons attendus. #105 avait posé la
condition : la base reconnaît elle-même un item déjà vu, il n'est plus nécessaire de tout charger
en mémoire pour dédoublonner.

Cette PR fait trois choses :

1. Elle tient un **registre** des fichiers bruts déjà importés, dans la base.
2. Elle ne lit que les fichiers absents de ce registre.
3. Elle tire parti du fait qu'un catalogue CISA nouveau se compare désormais au précédent : une
   ligne qui disparaît du catalogue est marquée **retirée**, comme le prévoit le MCD.

Elle sépare aussi la lecture du brut (T) de l'écriture en base (L), qui étaient réunies dans
`import_items`.

## Le comment

### 1. Le registre est la table `raw_data`

Il n'y a pas de nouvelle table (décision du 2026-10-10) : `raw_data` a déjà une ligne par fichier
brut, avec `raw_file_path UNIQUE`. Ce qui change, c'est qu'un fichier lu y entre **même sans
item**. Avant, la ligne n'était écrite qu'avec le premier item du fichier. La lecture du registre
est une requête de la base K-B : elle vit donc dans `database/` (règle 5 des conventions).

```python
SELECT_RAW_FILE_PATHS = "SELECT raw_file_path FROM raw_data"
```
`src/k_b/database/reading.py:5`

Pour inscrire un fichier sans item, il faut connaître sa source (`raw_data.source_id` est
NOT NULL). Or le `source_code` n'était connu que par l'item. `SourceReader` reçoit donc un champ
`source_code`. Chaque source le déclare une fois, dans la constante `SOURCE_CODE` que son
`convert` utilise aussi. Pour GitHub, une seule constante (`sources/github_api.py`) sert aux
releases et aux alertes.

### 2. La chaîne : L lit le registre, T lit le reste, L écrit

```python
        imported_paths = read_imported_paths(database_path)
        reading = read_raw_items(data_dir / "raw", SOURCE_KINDS, imported_paths)
        summary = import_items(
            reading, database_path, log_path, imported_at, TRACKED_REPOSITORIES
        )
```
`src/k_b/cli.py:115-118`

`run_import` enchaîne les trois étapes. `import_items` ne lit plus `raw/` : il reçoit la lecture
en paramètre. `read_raw_items` ne touche pas à la base : il reçoit les chemins déjà importés, sous
forme de `frozenset` immuable, et saute chaque page dont le chemin y figure :

```python
            if page_path.relative_to(raw_dir).as_posix() not in imported_paths
```
`src/k_b/raw_items.py:101`

La lecture rend des `RawFile` (chemin, source, date de collecte, items, nombre de rejets) et le
nombre de pages ouvertes (`read_count`, affiché `raw files read`). Une page illisible ne donne
pas de `RawFile` : elle n'est pas inscrite, et elle sera relue au prochain import (décision de
Sabine, option A).

```python
    except (ValueError, csv.Error, OSError) as error:
        # Not a file read: it is not registered, and is read again at the next import.
```
`src/k_b/raw_items.py:118-119`

### 3. Une seule transaction : registre, items, journal

Pour chaque `RawFile`, `import_items` inscrit d'abord le fichier (`write_raw_data`,
`src/k_b/import_items.py:248`), puis écrit ses items avec cet identifiant, puis applique le
retrait CISA. Le journal est écrit **avant** la validation, et non plus après :

```python
            check_log_absent(log_path)
            try:
                write_import_log(log_path, imported_at, rejections, discards)
                connection.commit()
            except BaseException:
                # The log at log_path can only be this import's: it was absent above.
                log_path.unlink(missing_ok=True)
                raise
```
`src/k_b/import_items.py:260-267`

Pourquoi : un fichier inscrit n'est plus relu. Si le journal se perdait après le commit, la trace
de ses rejets et de ses écarts serait perdue pour toujours. Ici, tout échec annule la base
(`rollback` du `except` englobant), et supprime le journal de cet import, Ctrl-C compris. Le
journal ne peut être que celui de cet import : `check_log_absent` a vérifié juste avant qu'il
n'existait pas. Le `commit()` est explicite, et non plus le `with connection:` d'avant. Ce n'est
pas un choix de style : le test qui simule l'échec du commit en a besoin.

### 4. Le retrait CISA, et la réapparition

Le retrait s'applique après les items d'un fichier qui contient au moins une `vulnerability`, si
ce fichier est collecté après le dernier catalogue importé :

```sql
UPDATE vulnerability SET withdrawn_at = :collected_at
WHERE item_id IS NOT NULL
    AND withdrawn_at IS NULL
    AND cve_id NOT IN (SELECT value FROM json_each(:present_cve_ids))
```
`src/k_b/import_items.py:105-110`

- `item_id IS NOT NULL` : seule une ligne KEV peut être retirée. Un CVE créé par une alerte
  GitHub n'a pas d'item KEV, et le `CHECK` du schéma l'interdit de toute façon.
- `withdrawn_at IS NULL` : la première absence garde sa date.
- `json_each` : la liste des CVE présents arrive en **un seul paramètre lié**, une liste JSON que
  SQLite déplie. Il n'y a ni concaténation dans le SQL, ni requête par CVE.

« Présent » veut dire lu comme item, écrit ou écarté (`unchanged`) : sinon, un catalogue
identique retirerait tout. Un catalogue avec une ligne rejetée, ou sans item, ne retire rien :

```python
    if not present_cve_ids or raw_file.rejection_count:
        return 0
```
`src/k_b/import_items.py:516-517`

La réapparition est une clause de plus dans l'upsert de #105 (`src/k_b/import_items.py:94`) :
une ligne retirée qui revient dans un catalogue plus récent est réécrite, même à contenu
identique. `withdrawn_at` est alors vidé et `revised_at` daté.

### 5. Le catalogue importé en retard

Un catalogue plus ancien que le dernier importé ne change pas une ligne connue (règle de #105).
Mais s'il apporte un CVE que la base ne connaît pas, ce CVE est absent du dernier catalogue. Il
est donc écrit **retiré**, à la date de ce dernier catalogue :

```python
            "withdrawn_at": None
            if is_after_latest_catalog or latest_collected_at is None
            else latest_collected_at,
```
`src/k_b/import_items.py:407-409`

Sans cela, ce CVE serait actif. Une base reconstruite, qui lit tout dans l'ordre des collectes,
le trouverait retiré : les deux bases différeraient par leur contenu. Le constat vient de la
relecture du plan, simulé sur le vrai schéma.

### 6. Un journal par import, chaque ligne datée

Le nom du journal porte la seconde de l'import, au format des noms de bruts :
`import-log-2026-10-12T152409Z.jsonl` (`src/k_b/cli.py:38`, `:109-111`). Chaque ligne porte
`imported_at` au format des dates de la base. Un journal de la même seconde arrête l'import (code
de sortie 2). L'écriture passe par `write_file_atomically` (règle 2 des conventions).

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Un fichier illisible n'est pas inscrit (Sabine, A) | il signale un défaut à corriger ; relu, il est lu dès la correction | l'inscrire (B) : seule une reconstruction l'aurait relu, et un catalogue illisible serait devenu « le dernier catalogue » |
| Journal écrit avant le commit (Sabine) | un fichier inscrit n'est plus relu : son journal ne doit pas se perdre | journal après la base (#105) : la perte du journal devenait définitive |
| `imported_at` = l'instant de l'import | un instant lu une fois, injecté, testable ; le même que le nom du fichier | l'heure de chaque constat : elle n'est pas mesurée, tout se passe dans une transaction |
| Catalogue avec rejet : ne retire rien (Sabine, écart au MCD) | une ligne rejetée est présente, pas absente : on échoue fermé | retirer quand même : retrait faux |
| Retrait déclenché par la sorte `vulnerability` | la règle de la nature reste dans l'écrivain de sa sorte (ADR du 12/10) | tester `source_code == "cisa_kev"` : la règle en Python, ailleurs |
| `source_code` dans `SourceReader`, une constante par source | une seule écriture de la valeur | un champ de `SourceKind` : la valeur aurait été écrite deux fois |
| Lecture du registre dans `database/reading.py` | règle 5, revue d'homogénéité du 11/10 | `cli.py` appelant `database/` : il aurait sauté une couche |
| SQL d'écriture nouveau dans `import_items.py` | #135 déplacera tout le SQL d'écriture ensemble | le déplacer ici : hors périmètre |
| La présence du journal se vérifie après le premier écrit en base | le verrou d'écriture SQLite sérialise deux imports de la même seconde | une vérification avant la transaction : deux imports la passaient tous les deux |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_raw_file_already_imported_is_not_opened_and_a_new_one_is` (lecteur espion) | T n'ouvre pas une page déjà importée |
| `test_a_file_read_without_item_is_registered_and_not_read_again` | un fichier sans item est inscrit, et ne retire rien |
| `test_an_unreadable_file_and_a_file_without_reader_are_not_registered` | décision A : relu à chaque import (`read_count == 1`) |
| `test_a_failed_import_leaves_the_database_and_the_log_unchanged` | un échec n'inscrit aucun fichier |
| `test_a_commit_that_fails…`, `test_a_ctrl_c_after_the_log_is_written…`, `test_a_log_that_cannot_be_written…` | base et journal : tout ou rien |
| `test_only_a_new_raw_file_is_read_and_the_log_of_the_first_import_stays_whole` | un seul fichier lu, premier journal intact octet pour octet |
| `test_a_kev_row_absent…`, `…back in a newer catalog…`, `…absent from two catalogs…` | retrait, réapparition, date de la première absence |
| `test_a_catalog_with_a_rejected_row_withdraws_nothing`, `test_a_catalog_older_than_the_latest_imported_withdraws_nothing` | les gardes du retrait |
| `test_a_rebuilt_database_equals_the_one_kept_import_after_import` | reconstruction = base tenue (dump égal) |
| `kb create-db` puis 3 `kb import` sur un dossier d'essai : `raw files read: 2`, puis `0`, puis `1`, et `vulnerabilities withdrawn: 1` ; la reconstruction donne un dump identique | le critère, par la commande |
| Casses volontaires : sans le filtre des chemins, 8 tests échouent ; registre hors transaction, 4 ; sans la garde des rejets, 1 | les tests détectent ces régressions |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas inscrire le fichier illisible, pour ne pas le relire ?** Parce qu'il
   signale un défaut, pas une donnée. Relu, il est importé dès que le lecteur ou le brut est
   corrigé, sans reconstruction. Inscrit, un catalogue CISA illisible deviendrait « le dernier
   catalogue » et bloquerait les catalogues valides plus anciens (`src/k_b/raw_items.py:118`).
2. **Que se passe-t-il si on coupe l'import au milieu ?** La transaction est annulée et le
   journal de cet import supprimé (`src/k_b/import_items.py:260-271`) : aucun fichier n'est
   inscrit, tout sera relu. Deux limites, acceptées par Sabine : un `SIGKILL` peut laisser
   un journal orphelin, et une interruption juste après le `commit()`, avant la sortie du
   `try`, supprime le journal d'un import validé.
3. **Le retrait d'une CVE n'est-il pas dangereux sur un catalogue partiel ?** Si. C'est pour cela
   qu'un catalogue avec un rejet, ou sans item, ne retire rien
   (`src/k_b/import_items.py:516`). Le lecteur CISA refuse aussi la page entière sur une ligne
   mal formée.
4. **Où est l'injection SQL possible avec la liste des CVE ?** Il n'y en a pas : la liste est un
   seul paramètre lié, JSON, déplié par `json_each` (`src/k_b/import_items.py:109`).
   `/security-review` n'a relevé aucun constat.
5. **La base reconstruite est-elle la même ?** Oui pour le contenu et les lignes retirées (test de
   dump égal). Après un catalogue en retard, les dates (`revised_at`, `withdrawn_at`) et le
   fichier rattaché peuvent différer. Une exception est écrite comme limite dans
   `docs/specs-collecte.md` : la ligne rejetée dans le dernier catalogue.

## Zones non vérifiées

- **Le verrou d'écriture qui sérialise deux imports de la même seconde** : il est déduit du
  comportement documenté du module `sqlite3`, qui ouvre une transaction avant le premier
  `INSERT`, et de SQLite. Aucun test ne lance deux processus en même temps.
- **L'échec du commit** est simulé par une connexion dont `commit` lève. Un vrai échec (disque
  plein au moment du `COMMIT`) n'a pas été provoqué.
- **Le coût de la requête du dernier catalogue**, lancée pour chaque ligne CISA, n'a pas été
  mesuré. Elle ne tourne plus que pour les nouveaux catalogues.
- **`write_file_atomically`** ne supprime son temporaire que sur `OSError`, et ne le cache pas
  (écart de `main` à la règle 2, porté par #62). Le journal hérite de cette limite.

## Ce qui reste

- Le renommage en E, T, L (#107) et le déplacement du SQL d'écriture dans `database/` (#135),
  après TLDR, les dépôts qui montent et Zotero (ordre de Sabine du 12/10).
- Le `SAVEPOINT` par item (#136) : une entrée que la base refuse annule encore tout l'import.
- La conservation des journaux d'import (un fichier par import, gardé) : rattachée à la purge
  (#83).
- Les releases d'un dépôt hors de la liste suivie : leur fichier est inscrit, seule une
  reconstruction les relit (#87 ne couvre que la reconstruction).
