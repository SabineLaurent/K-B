# Extraire la bibliothèque Zotero et ses surlignages

- **Date** : 2026-10-11
- **Branche** : `feat/zotero-extraction`
- **Issue** : #15
- **Fichiers principaux** : `src/k_b/sources/zotero.py` (la source et sa requête),
  `src/k_b/collect.py` et `src/k_b/source_contract.py` (le dossier du brut), `src/k_b/cli.py`
  (`KB_ZOTERO_DIR`), `tests/sources/test_zotero.py`, `tests/fixtures/zotero_extract.sql`.
- **Note liée** : [Dossiers du brut et état de collecte](2026-10-10-dossiers-du-brut-et-etat-de-collecte.md),
  qui a posé `raw/automated_watch/` et `raw/selected_library/`.

## Le pourquoi

Zotero est la source « base de données » de K-B : les papiers que Sabine enregistre et lit, et
ce qu'elle y surligne. Tant qu'elle n'était pas codée, K-B n'avait aucune requête d'extraction
SQL à montrer.

Cette PR fait la première moitié du chemin, l'extraction : `kb collect` lit la bibliothèque et
écrit ce qu'il y trouve dans un fichier JSON, le brut. Rien n'entre encore dans la base K-B :
le modèle qui dira comment un papier Zotero s'y range n'est pas décidé, et lire le brut vers la
base est une issue à part (décision de Sabine du 2026-10-11).

Deux contraintes pèsent sur tout le code :

- **La base de Zotero ne se lit pas en place.** Zotero la verrouille quand il tourne, et sa
  documentation demande un accès en lecture seule. K-B travaille donc sur une copie.
- **La bibliothèque est une donnée privée.** La copie ne doit pas traîner, et le journal ne doit
  citer ni un auteur, ni un titre, ni un texte surligné.

## Le comment

### 1. Le déroulé d'une extraction

`fetch` est la seule méthode que la collecte appelle. Elle enchaîne quatre gestes : ne rien
faire si rien n'a changé, copier, interroger la copie, rendre le JSON.

```python
# src/k_b/sources/zotero.py:170-184
if last_collected_at is not None and not was_modified_since(
    read_file_states(self.zotero_dir), last_collected_at
):
    return None
with tempfile.TemporaryDirectory(prefix=TEMPORARY_DIR_PREFIX) as copy_dir:
    copy_path = copy_library(self.zotero_dir, Path(copy_dir))
    documents = extract_documents(copy_path)
logger.info(
    "zotero: %d documents, %d highlights extracted", ...
)
return (json.dumps(documents, ensure_ascii=False, indent=2) + "\n").encode()
```

- `return None` veut dire « rien de neuf » : la collecte n'écrit alors aucun fichier. La règle
  est la même pour toutes les sources (`source_contract.py`).
- `tempfile.TemporaryDirectory` crée un dossier lisible par la seule utilisatrice, au nom qui
  commence par `kb-zotero-`, et le supprime à la sortie du bloc `with`, que l'on sorte par un
  succès, une erreur ou un Ctrl-C. La copie de la bibliothèque ne survit donc pas à l'extraction.
- Le journal donne deux nombres, rien d'autre.

### 2. Copier sans jamais ouvrir l'original

Zotero écrit en mode WAL (*write-ahead log*) : ses dernières écritures vont d'abord dans un
second fichier, `zotero.sqlite-wal`, et ne rejoignent `zotero.sqlite` que plus tard. Le
2026-10-11, Zotero ouvert, le fichier principal datait du 7 octobre et le `-wal` du jour :
copier le seul fichier principal aurait donné une bibliothèque vieille de quatre jours.

```python
# src/k_b/sources/zotero.py:220-232
states_before = read_file_states(zotero_dir)
copy_path = copy_dir / DATABASE_FILE_NAME
shutil.copyfile(zotero_dir / DATABASE_FILE_NAME, copy_path)
with contextlib.suppress(FileNotFoundError):
    shutil.copyfile(
        zotero_dir / WRITE_AHEAD_LOG_FILE_NAME, copy_dir / WRITE_AHEAD_LOG_FILE_NAME
    )
states_after = read_file_states(zotero_dir)
if states_after != states_before:
    raise ZoteroChangedDuringCopyError(...)
```

- `shutil.copyfile` lit l'original comme un simple fichier. SQLite n'ouvre jamais l'original :
  il n'ouvre que la copie.
- Les deux fichiers ne sont pas copiés au même instant. Si Zotero écrit entre les deux, la copie
  du fichier principal et celle du `-wal` ne vont plus ensemble. La relecture du plan a montré,
  sur une base fabriquée, qu'une telle paire passe `PRAGMA integrity_check` avec `ok`. D'où la
  garde : l'état de chaque fichier (taille, date de modification à la nanoseconde, inode, et le
  fait même que le `-wal` existe) est relevé avant et après, et le moindre écart arrête
  l'extraction. La collecte suivante recommence.
- Le troisième fichier de SQLite, `-shm`, n'est pas copié : SQLite le reconstruit à l'ouverture.

### 3. Vérifier la copie, puis l'ouvrir en lecture seule

```python
# src/k_b/sources/zotero.py:239-248
with contextlib.closing(
    sqlite3.connect(f"{copy_path.as_uri()}?mode=ro", uri=True)
) as connection:
    connection.row_factory = sqlite3.Row
    check_integrity(connection)
    try:
        rows = connection.execute(EXTRACTION_QUERY).fetchall()
    except sqlite3.DatabaseError as error:
        raise ZoteroQueryFailedError(describe_query_error(error)) from None
```

- `mode=ro` ouvre la base en lecture seule : la requête ne peut rien y écrire. `as_uri()` écrit
  le chemin sous forme d'URI, pour qu'un `?` ou un `%` dans le nom du dossier temporaire ne
  casse pas l'adresse.
- `contextlib.closing` ferme la connexion à la sortie. Le `with` d'une connexion `sqlite3`, lui,
  valide ou annule une transaction mais ne ferme pas.
- `check_integrity` lance `PRAGMA integrity_check`, le contrôle de cohérence de SQLite. Une
  réponse autre que `ok`, ou une erreur pendant le contrôle, lève `ZoteroCopyInconsistentError`.
- `from None` coupe le lien avec l'erreur d'origine. Sans lui, la trace écrite au journal par la
  collecte montrerait le message brut de SQLite.

### 4. La requête : une seule instruction pour toute la bibliothèque

Zotero range tout dans une table `items` : un papier, son PDF, une note, un surlignage sont
chacun une ligne, distingués par leur type. La requête commence donc par dire ce qu'est un
document, une fois pour toutes, dans une expression de table nommée (`WITH`) :

```sql
-- src/k_b/sources/zotero.py:45-52
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

Un document est une ligne de la bibliothèque personnelle (pas d'une bibliothèque de groupe), qui
n'est ni un fichier, ni une note, ni une annotation, et qui n'est pas à la corbeille.

Le titre, la date ou l'URL ne sont pas des colonnes de `items`. Zotero les garde dans un modèle
entité-attribut-valeur : une ligne de `itemData` par champ rempli, qui renvoie au nom du champ
(`fields`) et à sa valeur (`itemDataValues`). `field_value` (ligne 54) fait ces deux jointures et
ne garde que quatre champs sur les 123 que Zotero connaît :
`WHERE fields.fieldName IN ('title', 'date', 'url', 'archiveID')`.

Les listes (auteurs, étiquettes, PDF, surlignages) sont construites par SQLite lui-même :

```sql
-- src/k_b/sources/zotero.py:73-83
(
    SELECT json_group_array(
        json_object('first_name', creators.firstName, 'last_name', creators.lastName)
        ORDER BY itemCreators.orderIndex
    )
    FROM itemCreators
    JOIN creators ON creators.creatorID = itemCreators.creatorID
    JOIN creatorTypes ON creatorTypes.creatorTypeID = itemCreators.creatorTypeID
    WHERE itemCreators.itemID = document.itemID
        AND creatorTypes.creatorType = 'author'
) AS authors,
```

- `json_object` fabrique un objet JSON par auteur ; `json_group_array` rassemble les objets d'un
  même document en une liste. Sans ligne, la liste est `[]`.
- `ORDER BY` à l'intérieur de l'agrégat fixe l'ordre de la liste : celui de Zotero
  (`orderIndex`) pour les auteurs, la position dans le PDF (`sortIndex`) pour les surlignages.
- Pour les PDF et leurs surlignages, deux filtres comptent : `path LIKE 'storage:%'`
  (lignes 101 et 122) ne garde que les fichiers rangés dans le stockage de Zotero, dont le chemin
  est relatif ; `itemAnnotations.type = 1` (ligne 124) ne garde que les surlignages.

Ce qui rend la requête économe : une instruction pour toute la bibliothèque, au lieu d'une
requête par document lancée depuis Python ; seules les colonnes utiles sont nommées ; tous les
filtres sont dans le SQL. `EXPLAIN QUERY PLAN`, lancé sur une copie de la base réelle, montre un
seul parcours de table (`items`) ; tout le reste est une recherche par clé primaire ou par un
index que Zotero a déjà.

### 5. Un échec dit ce qui a été observé, pas le contenu de la bibliothèque

```python
# src/k_b/sources/zotero.py:273-283
def describe_query_error(error: sqlite3.DatabaseError) -> str:
    message = str(error)
    if MESSAGE_ABOUT_THE_QUERY.fullmatch(message):
        return message
    sqlite_error_name = getattr(error, "sqlite_errorname", None)
    if sqlite_error_name is None:
        return type(error).__name__
    return f"{type(error).__name__} ({sqlite_error_name})"
```

Un message de SQLite peut citer une valeur de la base : quand un texte n'est pas de l'UTF-8,
`sqlite3` le recopie dans son message. Le message n'est donc gardé que dans deux cas, où il ne
cite que la requête, qui est une constante du code : une table ou une colonne absente
(`no such column: itemAnnotations.pageLabel`) et une erreur de syntaxe. Dans tous les autres
cas, on ne garde que le type de l'erreur et le nom que SQLite lui donne (`SQLITE_ERROR`,
`SQLITE_CORRUPT`), qui ne cite rien.

### 6. Le dossier du brut, et le branchement dans `kb collect`

Jusqu'ici, toute source écrivait sous `raw/automated_watch/`. Zotero est ce que l'utilisatrice
a choisi : son brut va sous `raw/selected_library/` (décision du 2026-10-09). Chaque source dit
donc son dossier, et la collecte le lit :

```python
# src/k_b/collect.py:72
source_dir = raw_dir / source.acquisition_dir_name / source.name
```

Ce nom entre dans un chemin de fichier : il est contrôlé comme le nom et l'extension de la
source (`collect.py:62-67`), par le motif `[a-z0-9_]+`, avant toute écriture.

Le dossier de Zotero n'est pas le même d'une machine à l'autre. `cli.py` le lit dans une
variable d'environnement et n'ajoute la source que si elle est donnée :

```python
# src/k_b/cli.py:128-131
sources = list_sources(SOURCE_KINDS)
zotero_dir = os.environ.get(ZOTERO_DIR_VARIABLE)
if zotero_dir:
    sources.append(ZoteroSource(Path(zotero_dir)))
```

Sans la variable, `kb collect` affiche `zotero: skipped (KB_ZOTERO_DIR not set)` et son code de
sortie ne change pas : une machine sans Zotero ne voit pas sa collecte échouer.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Options écartées, et pourquoi |
|---|---|---|
| Extraction seule, rien en base | le modèle de la bibliothèque n'est pas décidé (décision de Sabine) | aller jusqu'à la base avec un modèle minimal : élargit l'issue ; rattacher les surlignages à l'item arXiv : un papier que la collecte arXiv n'a pas vu les perdrait |
| Le brut est le résultat de la requête, en JSON | minimisation : la base entière contient toute la bibliothèque (ADR du 2026-10-09) | la copie entière comme brut |
| Copier `zotero.sqlite` **et** son `-wal` | documentation de Zotero, et constat du 2026-10-11 | l'API de sauvegarde de SQLite : elle ouvre l'original, que Zotero verrouille ; `immutable=1` sur l'original : ignore le `-wal` |
| Garde avant et après la copie | une paire mal assortie passe `integrity_check` | s'en remettre au seul contrôle d'intégrité |
| Dossier temporaire du système | la source ne connaît pas le dossier de données ; une copie entière n'a pas à passer par un dossier sauvegardé ; la règle 2 des conventions est précisée dans cette PR | un temporaire caché dans le dossier de données, comme pour les fichiers que K-B écrit |
| Une instruction SQL avec agrégats JSON | « document » défini une fois ; le résultat est ce que la requête rend | quatre requêtes assemblées en Python : filtre répété ; une requête par document : N+1 |
| Tous les documents hors corbeille | Zotero n'a pas d'état « lu » | seulement les documents surlignés ; seulement ceux dont le PDF a été ouvert (`lastRead`, sens non vérifié) |
| PDF du stockage de Zotero seulement | un PDF lié garde son propre chemin, qui peut contenir le nom du compte | tous les PDF |
| Surlignages seuls (type 1), avec leur commentaire | seul type observé ; les autres sont remis à plus tard par Sabine | tous les types d'annotation |
| Valeurs gardées telles que Zotero les donne | règle du brut intact ; convertir est le travail du lecteur | convertir les dates à l'extraction |
| La requête vit dans la source | c'est une source externe, pas la base K-B ; règle 5 des conventions précisée | `src/k_b/database/` : le module de la base K-B aurait porté le schéma d'une source |
| Le dossier du brut est un attribut de la source | une ligne par source, signature de la collecte inchangée | le porter par la sorte de source : 14 appels de tests à changer |
| `KB_ZOTERO_DIR`, et Zotero sauté sans elle | un chemin de machine n'a pas sa place dans un dépôt public | une constante dans `config.py` ; un échec sur une machine sans Zotero |
| Base d'essai : un script SQL des 15 tables utiles | les 44 autres tables ne sont jamais lues ; un script se relit dans une PR | un fichier binaire ; les 59 tables ; les `CREATE TABLE` de Zotero recopiés mot pour mot (question de licence) |
| Pas de plafond de taille sur la copie | un disque plein arrête déjà la copie, et le dossier temporaire est supprimé | un plafond arbitraire |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run pytest` : 538 tests passent ; `ruff check`, `ruff format --check`, `mypy --strict` verts | rien d'existant n'est cassé |
| `test_a_paper_is_extracted_with_its_authors_tags_pdf_and_highlights_in_order` | tous les champs du critère, auteurs et surlignages dans l'ordre, alors que la base d'essai les écrit dans un autre ordre |
| `test_only_the_documents_of_the_user_library_out_of_the_trash_are_extracted` | corbeille, bibliothèque de groupe, note, résumé, soulignement, PDF lié et capture web sont écartés |
| `test_what_zotero_has_only_written_to_its_write_ahead_log_is_extracted` | ce qui n'est que dans le `-wal`, Zotero ouvert, est lu |
| `test_the_original_is_left_byte_for_byte_and_nothing_is_created_next_to_it` | l'original n'est ni modifié ni accompagné d'un nouveau fichier |
| `test_the_temporary_copy_is_deleted_after_an_extraction` et `..._after_a_failure` | la copie ne survit ni à un succès ni à un échec |
| `test_the_copy_is_made_in_a_folder_named_after_k_b_and_opened_read_only` | la copie est ouverte avec `mode=ro` |
| `test_a_copy_whose_integrity_check_reports_a_problem_is_refused`, `test_a_copy_that_integrity_check_cannot_read_is_refused` | une copie incohérente est refusée par un état nommé |
| les trois tests `..._during_the_copy_is_refused` | fichier principal modifié, `-wal` modifié, `-wal` apparu : la garde les voit |
| `test_a_library_without_a_column_the_query_reads_fails_naming_the_column` | un changement de schéma de Zotero donne une erreur qui nomme la colonne |
| `test_a_text_that_is_not_utf8_fails_without_its_content_in_the_error` | le message de SQLite qui cite un texte ne sort pas |
| `test_the_log_gives_two_counts_and_no_author_title_or_highlight` | le journal ne contient que deux nombres |
| `test_collect_skips_zotero_and_says_so_without_its_directory` | sans `KB_ZOTERO_DIR` : une ligne, code de sortie 0 |
| `test_a_zotero_extract_is_not_read_into_the_database` | `kb import` n'écrit ni item ni surlignage |
| Collecte sur une copie de la base réelle, le 2026-10-11 | 5 documents, 6 surlignages (4, 0, 0, 0, 2), 5 PDF, aucun chemin absolu, extrait de 8 950 octets ; copie inchangée à l'octet près ; aucun dossier `kb-zotero-…` laissé |
| `PRAGMA table_info` comparé entre la base d'essai et la copie réelle | 15 tables, 0 écart : la base d'essai a les mêmes colonnes, types et clés |
| Code cassé exprès, 17 façons (filtre retiré, `-wal` non copié, garde désactivée, lecture seule retirée…) | les tests échouent les 17 fois |

## Ce que tu dois pouvoir défendre

1. **Pourquoi copier la base au lieu de la lire ?**
   Zotero verrouille sa base quand il tourne, et sa documentation demande un accès en lecture
   seule. La copie se lit sans rien demander à Zotero, et l'original n'est jamais ouvert par
   SQLite (`copy_library`, `zotero.py:213`).
2. **Que se passe-t-il si Zotero écrit pendant la copie ?**
   La garde compare l'état des deux fichiers avant et après (`zotero.py:228`). Au moindre écart,
   `ZoteroChangedDuringCopyError` : rien n'est écrit, la date de dernière collecte reste, et la
   collecte suivante recommence.
3. **Où est la sécurité des données personnelles ?**
   Dans quatre endroits : la requête ne lit que les colonnes utiles (pas les notes, pas les
   résumés) ; la copie vit dans un dossier temporaire supprimé à la sortie ; le journal ne donne
   que deux nombres ; un message d'erreur de SQLite n'est repris que s'il ne cite que la requête
   (`describe_query_error`, `zotero.py:273`).
4. **Pourquoi une seule grosse requête plutôt que plusieurs petites ?**
   La définition d'un document n'est écrite qu'une fois, et le résultat est directement ce que
   la requête rend. Quatre requêtes auraient répété le filtre, ou l'auraient déplacé en Python.
5. **Que se passe-t-il si Zotero change son schéma ?**
   La requête échoue, et l'erreur nomme la table ou la colonne absente
   (`ZoteroQueryFailedError`). Elle ne produit pas un extrait faux. Seul un changement de sens
   sans changement de structure passerait inaperçu.

## Zones non vérifiées

- **« Type 1 = surlignage »** est déduit des 6 annotations que Sabine a faites le 2026-10-11,
  toutes de type 1. La documentation de Zotero consultée ne donne pas ce numéro.
- **`ORDER BY` dans un agrégat demande SQLite 3.44 ou plus** : repris de la documentation de
  SQLite de mémoire, non relu. K-B utilise SQLite 3.50.4 ; la version de la CI n'est pas
  vérifiée, ses tests le diront.
- **Le chemin d'un PDF lié peut être absolu** : relevé par la relecture du plan sur une base
  fabriquée, pas observé dans une vraie bibliothèque. Le filtre `storage:` l'écarte dans les
  deux cas.
- **Les messages de `PRAGMA integrity_check` ne citent pas de valeur** : d'après la revue de
  sécurité, de mémoire. Le message est de toute façon tronqué et échappé.
- **La licence du schéma de Zotero** : le code de Zotero est sous AGPL v3 « sauf fichier qui dit
  autrement », K-B sous CC BY-NC 4.0. La base d'essai réécrit 15 tables aux noms de Zotero ; si
  cela pose une question de licence n'est pas tranché.
- **La comparaison de structure et la collecte réelle** ont été faites sur la machine de Sabine,
  une fois. La CI n'a pas de base Zotero.
- **Les tests ont été écrits avant le code, mais lancés après** : la preuve qu'ils échouent
  vient du code cassé exprès.

## Ce qui reste

- **Lire l'extrait vers la base K-B** : modèle de la bibliothèque, bornes de longueur de
  `highlight`, colonne du chemin du PDF. Une issue à part.
- **Durée de conservation et purge des extraits** : ils sont tous gardés, sans durée au registre
  ni purge codée, ce que `.claude/rules/conformite.md` demande pour une donnée personnelle. Une
  issue à part ; ne pas réécrire un extrait identique au précédent relève de la même issue.
- **Non extraits, volontairement** : les notes et les autres types d'annotation (remis à plus
  tard par Sabine), les PDF liés, les surlignages d'un EPUB ou d'une capture web, un PDF sans
  document parent, un titre rangé sous un autre champ que `title`.
- **`KB_ZOTERO_DIR` dans `.env.example`** : à ajouter par Sabine, hors de cette PR.
