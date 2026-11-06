# Faire passer tout accès à la base par une couche d'accès, en SQLite seul

- **Date** : 2026-11-06
- **Branche** : `refactor/database-access-layer`, commits `c329a3a` et `f9f36d2`, sur `main` à `9725dc4`
- **Issue** : #416 (I4 du plan de mise en ligne du 06/11)
- **Fichiers principaux** : `src/k_b/database/engine.py` (nouveau), `src/k_b/database/errors.py` (nouveau),
  `src/k_b/database/connection.py`, `src/k_b/database/savepoint.py`, `src/k_b/data_api/dependencies.py`,
  `src/k_b/data_api/errors.py`
- **Série** : la lecture de l'erreur due à l'entrée vient de
  [2026-10-16-rejeter-l-item-que-la-base-refuse.md](2026-10-16-rejeter-l-item-que-la-base-refuse.md) ; le délai
  par requête vient de [2026-11-06-delai-et-bornes-du-detail-de-l-api-de-donnees.md](2026-11-06-delai-et-bornes-du-detail-de-l-api-de-donnees.md) (#331).

La liste des fichiers que le skill a injectée compte aussi les commits de #331 (`9039391` à `ca5680c`, PR #429) :
ils sont déjà sur `main` et ont leur propre note. Cette note ne couvre que `c329a3a` et `f9f36d2`.

## Le pourquoi

En production, K-B tournera sur PostgreSQL ; en local, SQLite doit rester pleinement fonctionnel (cadre posé par
Sabine les 05 et 06/11). Le moteur sera choisi par une adresse de connexion (#417). Pour que #417 n'ait à toucher
qu'un endroit, il faut d'abord que tout le code de K-B atteigne la base par des noms qui lui appartiennent, et non
par `sqlite3` directement.

Au départ, 25 fichiers de `src/k_b` importaient `sqlite3` : les écrivains, la lecture, la purge, l'import, deux
commandes et l'API de données. Chacun disait `sqlite3.Connection` dans ses signatures, ou `sqlite3.Error` dans ses
`except`. Après cette PR, trois fichiers seulement l'importent :
- `database/engine.py`, qui ouvre la base ;
- `database/errors.py`, qui dit ce qu'est une erreur de la base ;
- `etl/sources/zotero.py`, qui lit la base de Zotero, une base source et non celle de K-B.

L'issue impose une contrainte forte : **ne rien changer au comportement**. Aucun test n'est ajouté, et aucun
attendu ne change.

## Le comment

### 1. Deux noms, qui sont les objets de `sqlite3` eux-mêmes

`src/k_b/database/engine.py:11-12` :

```python
# The class of sqlite3 itself, not a wrapper: the SQLite path stays as it is.
Connection = sqlite3.Connection
```

`src/k_b/database/errors.py:8` :

```python
EngineError = sqlite3.Error
```

Ce ne sont pas des classes nouvelles : ce sont deux noms de plus pour les mêmes objets. Observé le 2026-11-06 :
`EngineError is sqlite3.Error` et `Connection is sqlite3.Connection` donnent `True`. Les conséquences :
- `except EngineError` attrape exactement ce qu'attrapait `except sqlite3.Error` ;
- `type(error).__name__`, écrit dans les journaux, ne change pas (`OperationalError`, `IntegrityError`…) ;
- mypy lit `Connection` comme un alias de type, et vérifie les appels comme avant.

C'est ce qui rend le déplacement sûr **par construction**, et pas seulement par les tests.

### 2. Les signatures et les `except` passent à ces noms

Dans 19 fichiers (`savepoint.py` compris), `connection: sqlite3.Connection` devient `connection: Connection`, et `import sqlite3` devient
`from k_b.database.engine import Connection`. Exemple, `src/k_b/database/writers/clip_writer.py:89` :

```python
def write(connection: Connection, item: Item, raw_data_id: int) -> Discard | None:
```

`ruff format` a remis certaines signatures sur une seule ligne, maintenant qu'elles tiennent dans 88 caractères :
c'est la seule différence de forme.

Quatre `except sqlite3.Error` deviennent `EngineError`. Exemple, `src/k_b/commands/import_command.py:93` :

```python
    except (EngineError, OSError, ValueError) as error:
```

Ils sont dans `etl/load.py:133`, `commands/create_db_command.py:22` et `commands/import_command.py:63` et `:93`.

### 3. Ce qui lit une erreur va dans `errors.py`, le savepoint reste où il est

`is_entry_refusal`, `describe_refusal` et `ENTRY_CONSTRAINT_ERROR_NAMES` passent de `savepoint.py` à `errors.py`,
sans changement, avec leur commentaire. Ce sont eux qui disent si la base a refusé l'entrée seule (règle 1 de
`conventions.md`), et ils lisent `sqlite3.IntegrityError` et son `sqlite_errorname`. `savepoint.py` les importe
(`src/k_b/database/savepoint.py:7-8`) :

```python
from k_b.database.engine import Connection
from k_b.database.errors import describe_refusal, is_entry_refusal
```

`write_in_savepoint` reste dans `savepoint.py` : son SQL (`SAVEPOINT`, `ROLLBACK TO`, `RELEASE`) est le même en
SQLite et en PostgreSQL. Seule la lecture de l'erreur dépend du moteur, et c'est elle que #417 complétera, par
les SQLSTATE 23514, 23505, 23502 et 22003.

### 4. Ouvrir la base : `connection.py:19-39` passe dans `engine.py`

`connect_database` et `connect_database_read_only` passent dans `engine.py`, corps inchangé ; seul leur type de
retour s'écrit `Connection`. `connection.py` garde ce qui concerne le fichier de la base : `DATABASE_FILE_NAME`,
`MissingDatabaseError` et `check_database_exists`. `engine.py` importe ce dernier (`src/k_b/database/engine.py:9`) :

```python
from k_b.database.connection import check_database_exists
```

Les appelants des deux fonctions importent désormais `k_b.database.engine` : `database/creation.py`,
`etl/load.py`, `purge/base.py`, `purge/registry.py`, `purge/after_import.py` et `data_api/dependencies.py`.

### 5. Le délai par requête de l'API de données entre dans la couche

#331, fusionnée le 06/11 à 08:46 UTC, a posé dans `data_api/dependencies.py` un délai de 5 s par requête, par
`set_progress_handler` de `sqlite3`. Elle a aussi posé, dans `data_api/errors.py`, sa reconnaissance par le code
`SQLITE_INTERRUPT`. Les deux sont propres à SQLite. Ils passent dans la couche :
- `INSTRUCTIONS_BETWEEN_CHECKS` et `make_deadline_check` passent tels quels dans `engine.py`, derrière une fonction
  qui ne nomme pas le moteur (`src/k_b/database/engine.py:43-48`) :

  ```python
  def set_query_timeout(connection: Connection, timeout_seconds: float) -> None:
      """Stop the readings of the connection once its deadline is passed: the error raised is one
      is_query_timeout (database/errors.py) recognizes."""
      connection.set_progress_handler(
          make_deadline_check(timeout_seconds), INSTRUCTIONS_BETWEEN_CHECKS
      )
  ```

- `is_query_timeout` passe dans `errors.py` (`src/k_b/database/errors.py:39`), sous le même nom, corps inchangé.

L'API de données appelle `set_query_timeout` au même endroit, dans le `try`, avant de rendre la connexion
(`src/k_b/data_api/dependencies.py:20`) :

```python
        set_query_timeout(connection, request.app.state.query_timeout_seconds)
```

`set_query_timeout` lit `INSTRUCTIONS_BETWEEN_CHECKS` à chaque appel, comme le faisait le code de #331 : le
commentaire « Read at each request: a test lowers it » reste vrai.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Des alias de `sqlite3` | Le même objet : rien ne change, par construction (section 1). | Un `Protocol` des méthodes utilisées : `code.md` n'admet une abstraction qu'avec deux implémentations, et la seconde (PostgreSQL) vient avec #417, qui le posera. Une classe qui enveloppe la connexion : elle change le type des objets, la pile d'appel et les traces, un risque pour un déplacement qui ne doit rien changer. |
| Le nom `EngineError` | `sqlite3.DatabaseError` et `psycopg.DatabaseError` existent, et sont plus étroits que `sqlite3.Error`. Observé : `sqlite3.InterfaceError` descend d'`Error`, pas de `DatabaseError` (PEP 249). | `DatabaseError`, un homonyme qui tromperait le lecteur. `DriverError`, car l'erreur peut venir du moteur lui-même (disque plein, contrainte). |
| Seules les lignes 19-39 de `connection.py` passent dans `engine.py` | C'est la lettre de l'issue, et le plus chirurgical : `cli.py` (partagé avec l'axe API), `etl/pipeline.py` et quatre commandes ne changent pas. | Fondre tout `connection.py` dans `engine.py` (première version du plan) : neuf fichiers de plus, dont `cli.py`, pour un nom de module. Écarté sur avis du sous-agent qui a relu le plan. |
| La lecture de l'erreur dans `errors.py`, le savepoint dans `savepoint.py` | L'issue : `errors.py` tient les erreurs dues à l'entrée ; le SQL du savepoint est portable. | Tout laisser dans `savepoint.py` : `sqlite3` y serait resté. |
| Le délai derrière `set_query_timeout`, la reconnaissance sous `is_query_timeout` | Demande de time-knight du 06/11, et le critère de l'issue : seuls trois fichiers importent `sqlite3`. Le nom `is_query_timeout` est celui que proposait la piste B. Nom et signature annoncés à time-knight, qui a donné son « go ». | Laisser `set_progress_handler` dans `data_api/` : un accès à SQLite hors de la couche. |
| Deux commits | Le premier ne touche ni `data_api/` ni `connection.py` (avant la fusion de #331, consigne de la mission) ; chacun est vert. | Un seul commit après #331 : il aurait fallu attendre pour tout. |
| Pas de test d'architecture sur `sqlite3` | L'issue ne le demande pas (choix 6 du plan validé par Sabine). | Un test AST ou une règle ruff `TID251` : proposés pour #417, où le critère risque de régresser. |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run pytest -q` : 3446 passed à `90b7383` et après `c329a3a` ; 3458 passed sur `main` à `9725dc4` et après `f9f36d2` | La suite est verte avant et après chaque commit, avec le même nombre de tests. |
| Liste des tests collectés (clé tirée au hasard remplacée par un repère) : diff vide avec `90b7383`, puis avec `9725dc4` | Aucun test ajouté, retiré ou renommé. |
| `uv run pytest --collect-only -m e2e -q` : 11 collectés | Les tests de bout en bout, que `uv run pytest` écarte après les avoir importés, s'importent toujours. |
| `git diff --name-status origin/main HEAD -- tests` : que des `M` | Aucun fichier de test supprimé ni renommé. |
| Les lignes de test changées, hors imports de `k_b.database.connection` et `k_b.database.engine` : dans `tests/data_api/test_api_errors.py`, les deux imports retirés de `k_b.data_api` (`dependencies`, `make_deadline_check`), l'import ajouté `from k_b.database import engine` (`:13`), et la ligne 94, `monkeypatch.setattr(engine, "INSTRUCTIONS_BETWEEN_CHECKS", 1)` au lieu de `dependencies` | Seule la cible d'un remplacement change, parce que la constante a changé de module ; aucun `assert` ne bouge (écart accepté par time-knight). |
| `grep -rlE "^import sqlite3\|^from sqlite3" src/k_b` : `database/engine.py`, `database/errors.py`, `etl/sources/zotero.py` | Le critère de fin de l'issue. |
| `uv run ruff check --no-cache`, `uv run ruff format --check`, `uv run mypy --strict` : verts | Les contrôles du dépôt. |
| `tests/data_api/test_openapi.py` vert | L'OpenAPI produite par l'application est toujours celle de `docs/api/openapi-donnees.json`. |
| `uv run python -c …` : `EngineError is sqlite3.Error` → `True`, `sqlite3.Error in ERROR_HANDLERS` → `True` | Le gestionnaire d'erreurs de l'API de données a gardé la même clé. |
| Règle 1 de `poc.md` (`grep … PRAGMA` sous `src/k_b/database`) : 8 sur `main` et sur la branche ; règle 3 : même liste de fichiers | Le `PRAGMA` déplacé reste sous `database/` ; aucun fichier nouveau ne touche au disque. |
| `/security-review` : aucun constat ; `/code-review high` : 7 constats, aucun bug de justesse, tous écartés par time-knight (délégation de Sabine du 15/10) | Les revues ne trouvent aucun changement de comportement ; le tri des constats est dans la PR. |

## Ce que tu dois pouvoir défendre

1. **« Un alias, ce n'est pas une couche d'accès. »** Si. Une couche d'accès, c'est le seul endroit par où le
   reste du code atteint la base. Aujourd'hui, ce point d'entrée nomme les objets de `sqlite3` ; demain, #417 y
   mettra un adaptateur PostgreSQL derrière les mêmes noms. Ce qui compte pour la suite, c'est que 24 des 25
   fichiers de départ ne disent plus `sqlite3` : #417 ne touchera qu'`engine.py` et `errors.py`, plus les quelques sites où
   `EngineError` sert de clé ou d'annotation (`data_api/errors.py:41` et `:67`).
2. **« Comment sais-tu que rien n'a changé ? »** Par construction, puisque les noms nouveaux sont les mêmes objets
   (section 1). Par les tests aussi : la même suite, la même liste de tests, aucun attendu modifié. Enfin par la
   lecture du diff avec `git diff --color-moved` : chaque bloc déplacé apparaît comme déplacé, et le reste n'est
   fait que d'imports, d'annotations et de docstrings.
3. **« Pourquoi pas SQLAlchemy Core, fait pour ça ? »** Écarté par l'issue et par le plan validé : avec le pilote
   `pysqlite`, sa documentation décrit un « Incorrect behavior for SAVEPOINT », et ses remèdes changent le code
   SQLite. Or le savepoint porte la règle 1 de `conventions.md`.
4. **« Pourquoi `connection.py` existe-t-il encore ? »** L'issue ne déplace que ses lignes 19-39. Le reste
   (`DATABASE_FILE_NAME`, `MissingDatabaseError`, `check_database_exists`) concerne le fichier de la base, et
   déplacer ces noms aurait touché neuf fichiers de plus, dont `cli.py`, partagé avec l'autre axe. #417
   reviendra sur ce point quand `KB_DATABASE_URL` remplacera le chemin du fichier.
5. **« Et la sécurité ? »** Aucune requête SQL n'est touchée : les marqueurs `?` et les liaisons de paramètres
   sont inchangés. Le gestionnaire d'erreurs de l'API de données attrape la même classe, et ne journalise toujours
   que le type de l'erreur, jamais le message de SQLite (`src/k_b/data_api/errors.py:41-50`). La connexion de
   l'API reste en lecture seule, et son délai est posé avant toute lecture.

## Zones non vérifiées

- `mypy --strict` accepte `Connection = sqlite3.Connection` comme alias implicite. Je n'ai pas vérifié s'il le
  ferait encore sous une autre forme, comme l'instruction `type` de Python 3.12. Ce n'est pas la forme écrite, et
  FastAPI n'a pas été essayé avec elle dans `Annotated[Connection, Depends(…)]`.
- Le `__module__` des trois fonctions et de la constante déplacées change (`k_b.database.errors`,
  `k_b.database.engine`). Seule une trace le montre : aucun test ni journal ne le lit (`grep` de `__module__` et
  de leurs noms dans `src` et `tests`, le 2026-11-06).

## Ce qui reste

- **#417** : la branche PostgreSQL d'`engine.py` (psycopg 3, traduction des marqueurs `?` et `:nom`,
  `in_transaction` vrai en `INTRANS` comme en `INERROR`), les SQLSTATE d'une entrée refusée dans `errors.py`, la
  forme d'`EngineError` pour deux moteurs, et le test d'architecture sur `sqlite3` (tri de time-knight : à mettre
  dans le plan de #417, avec les outils de `tests/architecture/module_imports.py`). #417 revoit aussi le partage
  entre `connection.py` et `engine.py`, quand `KB_DATABASE_URL` remplace le chemin du fichier.
- **#418** : le délai sur PostgreSQL (`statement_timeout`, SQLSTATE 57014 → le même 503 `query_timeout`), derrière
  `set_query_timeout` et `is_query_timeout`.
- Les docstrings de `make_deadline_check` et d'`is_query_timeout` parlent encore de l'API de données, leur seul
  appelant aujourd'hui : la PR qui leur en donne un autre les reformulera.
