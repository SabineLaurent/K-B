# Rejeter l'item que la base refuse sans arrêter l'import

- **Date** : 2026-10-16
- **Branche** : `fix/reject-items-the-database-refuses`
- **Issue** : #136
- **Fichiers principaux** : `src/k_b/database/savepoint.py` (nouveau), `src/k_b/etl/load.py`,
  `docs/specs-collecte.md` ; tests : `tests/database/test_savepoint.py`, `tests/etl/test_load.py`,
  `tests/etl/test_load_zotero.py`
- **Note précédente de la série** : [Écarter une entrée invalide d'une source](2026-10-16-ecarter-une-entree-invalide-d-une-source.md)
  (#61, la même règle à la lecture)

## Le pourquoi

La règle 1 de `.claude/rules/conventions.md` (« Rejet d'une entrée invalide ») a trois étages : le
lecteur, la collecte, l'écriture en base. #61 a tenu les deux premiers. Restait le troisième.
`kb import` écrivait tous les items dans **une seule transaction, sans point de reprise** : si la
base refusait un seul item (une contrainte `CHECK` violée, par exemple), l'exception remontait,
`load.py` annulait tout (`connection.rollback()`), et rien n'était écrit. Au prochain import, le
même fichier était relu, le même item refusé, et tout tombait encore. Une entrée suffisait à
bloquer l'import pour toujours.

L'item est déjà validé avant d'arriver à la base (règle 4 : types communs de `items.py`, chaque
type comparé à son `CHECK` par un test). Les quatre cas relevés par la PR #131 sont refusés par
l'item depuis #133. Le `SAVEPOINT` n'est donc pas le contrôle principal : c'est **le filet
derrière la règle 4**, pour ce que l'item laisserait passer un jour et que la base refuserait
(défense en profondeur, `code.md`).

## Le comment

### 1. Transaction et `SAVEPOINT`

Une transaction rend un ensemble d'écritures atomique : tout est validé (`COMMIT`) ou tout est
annulé (`ROLLBACK`). Un `SAVEPOINT` est une marque **à l'intérieur** d'une transaction :
`ROLLBACK TO SAVEPOINT` revient à cette marque sans annuler la transaction, et `RELEASE
SAVEPOINT` retire la marque en gardant ce qui a été écrit après elle. Rien n'est écrit sur le
disque avant le `COMMIT` de la transaction extérieure (doc SQLite, *lang_savepoint*).

`src/k_b/database/savepoint.py:44-54` :

```python
    connection.execute("SAVEPOINT entry")
    try:
        yield
    except BaseException as error:
        if connection.in_transaction:
            connection.execute("ROLLBACK TO SAVEPOINT entry")
            connection.execute("RELEASE SAVEPOINT entry")
        if is_entry_refusal(error):
            raise EntryRefusedError(describe_refusal(error)) from error
        raise
    connection.execute("RELEASE SAVEPOINT entry")
```

C'est un *context manager* (`@contextmanager`) : ce qui est écrit dans le bloc `with` est gardé,
ou annulé seul si une exception sort du bloc. Trois détails :
- **`ROLLBACK TO` puis `RELEASE`** : `ROLLBACK TO` laisse la marque sur la pile (doc SQLite) ; le
  `RELEASE` la retire, pour que l'item suivant reparte d'une pile propre.
- **`if connection.in_transaction`** : sur certaines erreurs (disque plein, erreur d'entrée-sortie),
  SQLite annule toute la transaction lui-même. Il n'y a plus de marque, et `ROLLBACK TO` lèverait
  « no such savepoint », qui masquerait l'erreur d'origine. Sans transaction, on ne fait rien et
  l'erreur d'origine remonte.
- **Hors transaction, il refuse** (`savepoint.py:40-43`, `NoTransactionError`) : un `SAVEPOINT`
  hors transaction vaut `BEGIN DEFERRED`, et son `RELEASE` vaut `COMMIT` (doc SQLite). L'item
  serait validé avant le journal d'import. Aucun chemin actuel n'y mène : le module `sqlite3` de
  Python ouvre la transaction avant la première écriture (`INSERT`, `UPDATE`…), et l'import en
  fait toujours une d'abord (`write_tracked_repositories`). Sondé le 16/10 : même un
  `executemany` avec une liste vide ouvre la transaction (`in_transaction = True`). C'est le
  contrat du module, écrit pour échouer fermé.

### 2. Les erreurs « dues à l'entrée »

`src/k_b/database/savepoint.py:18-20` et `57-60` :

```python
ENTRY_CONSTRAINT_ERROR_NAMES = frozenset(
    {"SQLITE_CONSTRAINT_CHECK", "SQLITE_CONSTRAINT_UNIQUE", "SQLITE_CONSTRAINT_NOTNULL"}
)
...
    if isinstance(error, sqlite3.IntegrityError):
        return error.sqlite_errorname in ENTRY_CONSTRAINT_ERROR_NAMES
    return isinstance(error, (OverflowError, UnicodeEncodeError))
```

La question à se poser : **qui a choisi la valeur refusée ?**
- `CHECK`, `UNIQUE`, `NOT NULL` portent sur **les valeurs de l'entrée** : un titre vide, une CVE
  mal formée, un champ absent, un identifiant déjà présent. C'est la source qui les a apportées.
- `OverflowError` (entier au-delà de 64 bits) et `UnicodeEncodeError` (surrogate isolé) : Python
  refuse de passer la valeur à SQLite, avant même l'exécution. C'est encore la valeur de l'entrée.
- `FOREIGN KEY`, `PRIMARY KEY`, type d'une table `STRICT` : ce n'est pas la source qui choisit vers
  quelle ligne pointe un item (`raw_data_id`), sa clé technique ou le type de ses colonnes, c'est
  **l'écrivain**. Si la base les refuse, le code ou le schéma est faux. En faire un rejet
  inscrirait le fichier et validerait l'import : chaque item serait écarté pour toujours, en
  silence, jusqu'à une reconstruction. L'import doit s'arrêter, comme sur une erreur du système
  (disque plein, base verrouillée).

Le tri se fait par `sqlite_errorname`, le **code étendu** de SQLite (exposé par Python depuis
3.11). C'est un état nommé, pas un texte à analyser.

### 3. Le motif du rejet, sans la valeur

`src/k_b/database/savepoint.py:63-75` (`describe_refusal`) décrit le refus sans citer la valeur
reçue (règle 3 de `conventions.md`, règle 5 de `poc.md`) :
- `IntegrityError` : son état puis le message de SQLite, les blancs ramenés à un espace (un
  `CHECK` écrit sur plusieurs lignes dans `schema.sql` donnerait sinon un motif avec des retours à
  la ligne). Le message de SQLite nomme la contrainte (`CHECK constraint failed: length(tag_name)
  > 0`, `NOT NULL constraint failed: release.tag_name`), jamais la valeur. Aucun trigger ni `RAISE`
  n'existe dans `schema.sql` qui pourrait en écrire une.
- `UnicodeEncodeError` : son texte cite le caractère refusé. On ne garde que `reason` et la
  position (`surrogates not allowed at position 5`).
- `OverflowError` : message fixe (`Python int too large to convert to SQLite INTEGER`).

Le libellé de l'item est construit dans `load.py:314-319` :
`f"{item.kind} {quote_value(item.source_item_id)} refused by the base: {refusal}"`.
L'identifiant passe toujours par `quote_value` (tronqué, échappé), comme dans les rejets de #61.
Quand l'identifiant est lui-même la valeur refusée (un `release_id` au-delà de 64 bits), il est
cité comme identifiant ; le motif, lui, ne la cite pas.

### 4. Ce que devient l'item refusé

`src/k_b/etl/load.py:311-319` :

```python
    try:
        with write_in_savepoint(connection):
            return write_item(connection, item, raw_data_id)
    except EntryRefusedError as refusal:
        return reject(
            item.raw_file_path,
            f"{item.kind} {quote_value(item.source_item_id)} refused by the base: "
            f"{refusal}",
        )
```

`reject` (`etl/transform.py:216-218`) est le **chemin unique** des rejets (règle 1). Il fait deux
choses :
- **Journal de fonctionnement** : une ligne `logger.warning("rejected from %s: %s", …)`, horodatée
  en UTC, sur la sortie d'erreur et dans `logs/kb.log`.
- **Journal d'import** : le `Rejection` rendu rejoint les autres et finit en ligne
  `{"kind": "rejection", "raw_file_path": …, "reason": …}` de `import-log-<date>.jsonl`, écrit
  avant le `COMMIT`.

Le **fichier reste inscrit** au registre `raw_data` (son inscription est hors du `SAVEPOINT`,
`load.py:278`) : il ne sera pas relu, comme un fichier dont une entrée a été rejetée à la lecture.
Seule une reconstruction de la base le relit. Un item refusé compte aussi comme un rejet de son
fichier (`load.py:286-288`, `raw_file._replace(rejection_count=…)`) : un catalogue (CISA KEV,
Zotero) dont un item est refusé ne retire rien, car l'item refusé est dans le catalogue, pas
absent de lui.

**Exception : le classement GH Archive** (`load.py:353-361`). Son inscription et toutes ses lignes
sont dans **un seul** `SAVEPOINT`. Une ligne refusée annule le classement entier, inscription
comprise : il n'entre pas au registre et sera **relu à l'import suivant**, comme une page
illisible. C'est la décision de Sabine du 2026-10-13 : un classement est un instantané dont la
complétude compte (règle 1).

**Zotero** : l'écrivain écrit l'entrée, ses surlignages et la publication citée en un seul appel ;
ils partagent donc le même `SAVEPOINT`. Un surlignage refusé annule aussi l'entrée et la
publication.

### 5. `import_items()` en étapes

La fonction faisait 75 lignes sur cinq niveaux d'imbrication. Elle se lit maintenant comme une
recette (`load.py:105-141`) : écrire les dépôts suivis, écrire chaque fichier (`write_files` →
`write_file` → `write_items_file` ou `write_trend_file`), valider avec le journal
(`commit_with_log`), rendre le résumé. Chaque fichier rend un `FileWriting` (un `NamedTuple`
construit par arguments nommés), et `join_writings` les additionne. Il n'y a pas d'accumulateur
modifié par chaque étape.

### 6. SQLite et PostgreSQL : même SQL, comportement différent

Le SQL du module (`SAVEPOINT`, `ROLLBACK TO SAVEPOINT`, `RELEASE SAVEPOINT`) s'écrit pareil dans
les deux bases (règle 1 de `poc.md`). Leur comportement après une erreur diffère :
- **SQLite** : l'algorithme par défaut, `ABORT`, annule **la seule instruction fautive** ; les
  instructions précédentes de la transaction sont gardées et la transaction reste active (doc
  SQLite, *lang_conflict*). Sans `SAVEPOINT`, l'item serait donc à moitié écrit (sa ligne `item`
  sans son sous-type), d'où le `SAVEPOINT` autour de tout l'item.
- **PostgreSQL** : après une erreur, la transaction entière passe à l'état « aborted » (statut `E`
  du message `ReadyForQuery` : « in a failed transaction block (queries will be rejected until
  block is ended) »). Toute instruction est refusée jusqu'à un `ROLLBACK`, ou un `ROLLBACK TO
  SAVEPOINT`. Le `SAVEPOINT` y est **indispensable** : sans lui, une seule erreur perdrait tout
  l'import. `psql` fait d'ailleurs la même chose avec `ON_ERROR_ROLLBACK` : un `SAVEPOINT`
  implicite avant chaque commande (doc PostgreSQL 18).

Au portage (08/11), ce qui changera : la liste des erreurs d'entrée (les erreurs de `psycopg` à la
place de `sqlite3.IntegrityError` et de ses codes étendus), au seul endroit où elle est écrite.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Un module `database/savepoint.py`, un context manager | Imposé par le critère de #136 ; ce qui vaut pour toutes les entités s'écrit une fois (`code.md`) | Un `try/except` dans chaque écrivain : sept copies |
| Tri des erreurs **dans** le savepoint, qui lève `EntryRefusedError` chaînée à l'erreur d'origine | Une seule place pour la liste et la description ; `load.py` n'attrape qu'elle (constats 1 et 8 de la revue de code, tranchés par time-knight) | Le tri dans `load.py`, écrit deux fois (item, classement) |
| Seules `CHECK`, `UNIQUE`, `NOT NULL` parmi les `IntegrityError` | Lettre du critère de #136 et de la règle 1 ; voir « Le comment », 2 | Toute `IntegrityError` : un bogue d'écrivain deviendrait un rejet en masse silencieux |
| `ROLLBACK TO` seulement si la transaction est ouverte | Ne pas masquer « disk is full » par « no such savepoint » (constat de l'architecte) | Toujours `ROLLBACK TO` |
| Hors transaction : `NoTransactionError` | Échouer fermé ; aucun chemin réel n'y mène (sonde du 16/10) | Ouvrir soi-même `BEGIN` : le savepoint prendrait la main sur la transaction de `load.py` |
| Inscription d'un fichier d'items **hors** `SAVEPOINT` | Le critère ne vise que l'item ; comportement inchangé | La mettre dedans : un refus de `raw_data` deviendrait un rejet (constat 2 de la revue, écarté) |
| Classement : inscription **dans** le `SAVEPOINT` | Décision du 13/10 : refusé entier, non inscrit, relu | — |
| Un `NamedTuple` par fichier, additionné | Le dépôt n'a que des `NamedTuple` et des dataclasses `frozen` (constat 8 de l'architecte) | Un accumulateur mutable passé aux étapes |
| Motif : état nommé + message SQLite sur une ligne | `sqlite_errorname` est un état nommé (`code.md`) ; le message nomme la contrainte | Citer `str(error)` brut : un `UnicodeEncodeError` citerait le caractère |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_an_item_the_base_refuses_is_rejected_and_logged_and_the_others_are_imported` (5 cas : `release_id` > 2⁶³, CVE en chiffres arabes-indiens, surrogate isolé, `tag_name` qui commence par NUL, `tag_name` absent) | Les quatre cas de #131 plus `NOT NULL` : rejet au journal avec le motif exact, sans la valeur ; autres items écrits ; aucune ligne `item` orpheline ; fichier inscrit |
| `test_a_foreign_key_the_base_refuses_stops_the_import_and_writes_nothing` | Une `FOREIGN KEY` refusée arrête l'import : base inchangée, aucun journal |
| `test_a_failed_import_leaves_the_database_and_the_log_unchanged` (`OperationalError("disk I/O error")`) | Une erreur du système arrête tout : rien n'est écrit |
| `test_a_catalog_with_a_row_the_base_refuses_withdraws_nothing`, `test_an_extract_with_a_document_the_base_refuses_withdraws_nothing` | CISA KEV et Zotero : un item refusé, aucun retrait |
| `test_a_document_with_a_highlight_the_base_refuses_is_written_in_none_of_its_parts` | Zotero : entrée, surlignages et publication citée dans le même `SAVEPOINT` |
| `test_a_ranking_with_a_row_the_base_refuses_is_refused_whole_and_read_again` | Classement : aucune ligne, non inscrit, rejet, puis écrit à l'import suivant |
| `tests/database/test_savepoint.py` (13 tests) | Gardé, annulé seul ; `CHECK`/`UNIQUE`/`NOT NULL`/dépassement/surrogate → `EntryRefusedError` avec motif exact ; `FOREIGN KEY`/`PRIMARY KEY`/type `STRICT` remontent tels quels ; « disk is full » après annulation totale remonte inchangé ; hors transaction refusé |
| `uv run pytest` : 1514 passed ; `ruff check`, `ruff format --check`, `mypy --strict` verts | Les contrôles du dépôt |
| `grep -rn "SAVEPOINT" src/k_b` → `database/savepoint.py` seul ; `grep -c "execute" src/k_b/etl/load.py` → 0 | Règles 1 et 5 de `conventions.md` |
| Greps de la règle 1 de `poc.md` : 36, 11, 52 (inchangés) | Aucun SQL propre à SQLite ajouté |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas tout annuler, comme avant ?** Une entrée suffisait à bloquer l'import pour
   toujours : le même fichier était relu et refusé à chaque import. La règle 1 veut qu'une seule
   entrée ne bloque rien et laisse une trace lisible (`savepoint.py`, `load.py:311-319`).
2. **Pourquoi une `FOREIGN KEY` refusée arrête-t-elle tout, alors qu'un `CHECK` ne fait que
   rejeter ?** Le `CHECK` porte sur une valeur apportée par la source. La `FOREIGN KEY` porte sur
   une ligne choisie par le code : si elle est refusée, le code est faux. En faire un rejet
   inscrirait les fichiers et perdrait leurs items en silence (`savepoint.py:12-20`, test
   `test_a_foreign_key_…`).
3. **Que se passe-t-il si le disque est plein au milieu d'un item ?** SQLite peut annuler toute la
   transaction ; le savepoint le voit (`in_transaction` faux), n'essaie pas de `ROLLBACK TO`, et
   laisse remonter l'erreur d'origine ; `load.py` annule tout, aucun journal n'est gardé
   (`savepoint.py:48-50`, test `test_an_error_after_the_base_undid_…`).
4. **Où est la sécurité ?** Le motif ne cite jamais la valeur refusée (règle 3, RGPD :
   minimisation ; OWASP : pas d'injection dans les journaux) ; l'identifiant passe par
   `quote_value` ; on échoue fermé hors transaction et sur toute erreur qui n'est pas due à
   l'entrée.
5. **Et en PostgreSQL ?** Le même SQL marche, et y devient indispensable : une erreur y met toute
   la transaction en état « aborted » jusqu'au `ROLLBACK TO SAVEPOINT`. Seule la liste des erreurs
   d'entrée changera, dans `savepoint.py`.

## Zones non vérifiées

- **Le comportement de PostgreSQL** n'est pas testé : il vient de la documentation (sources
  ci-dessous). Le portage (08/11) devra le prouver par un test.
- **L'annulation de toute la transaction par SQLite** (disque plein, I/O) n'a pas été provoquée :
  le test la simule par `connection.rollback()` puis une `OperationalError`. La page SQLite qui
  décrit ce comportement (*lang_transaction*, « Response To Errors Within A Transaction ») a été
  citée par la relecture de l'architecte ; je ne l'ai pas lue moi-même.
- **`sqlite_errorname` vaut `"unknown"`** pour un type refusé par une table `STRICT`
  (`SQLITE_CONSTRAINT_DATATYPE`, code 3091), observé le 16/10 sous Python 3.13 et SQLite 3.50.4.
  Sans conséquence ici (il n'est pas dans la liste, l'import s'arrête), mais un motif qui le
  citerait dirait « unknown ».
- **`OverflowError` et `UnicodeEncodeError` ne nomment pas le champ** : l'exception de `sqlite3`
  ne porte pas le paramètre. Limite écrite, acceptée au tri des revues.

## Ce qui reste

- Les rejets de lecture qui citent encore la valeur reçue (`etl/transform.py:154`) : #212.
- Un chemin brut non UTF-8 ferait échouer l'inscription d'un fichier d'items et l'écriture du
  journal (`import_log.py:90`) : constat ancien, hors de #136, signalé sans issue.
- Le portage du `SAVEPOINT` et de sa liste d'erreurs vers PostgreSQL : 08/11.

## Sources

- SQLite, *Savepoints* : https://www.sqlite.org/lang_savepoint.html (consultée le 2026-10-16, par
  Context7)
- SQLite, *The ON CONFLICT Clause* : https://www.sqlite.org/lang_conflict.html (consultée le
  2026-10-16, par Context7)
- PostgreSQL 18, *SAVEPOINT* : https://www.postgresql.org/docs/18/sql-savepoint.html (consultée le
  2026-10-16, par Context7)
- PostgreSQL 18, *Message Flow* : https://www.postgresql.org/docs/18/protocol-flow.html, et
  *Message Formats* (`ReadyForQuery`, statut `E`) :
  https://www.postgresql.org/docs/18/protocol-message-formats.html (consultées le 2026-10-16, par
  Context7)
- PostgreSQL 18, *psql*, `ON_ERROR_ROLLBACK` : https://www.postgresql.org/docs/18/app-psql.html
  (consultée le 2026-10-16, par Context7)
- CPython 3.13, `Modules/_sqlite/cursor.c` (transaction implicite seulement avant une instruction
  DML) : https://github.com/python/cpython/blob/main/Modules/_sqlite/cursor.c (consulté le
  2026-10-16, par Context7)
