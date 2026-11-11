# Attendre le pool de lecture avant qu'un test lise la base PostgreSQL

- Date : 2026-11-11
- Branche : `test/wait-for-the-reading-pool`
- Issue : #581
- Fichiers principaux : `tests/database/connected_readers.py` (nouveau), `tests/conftest.py`,
  `tests/data_api/test_serve_data.py`, et huit autres modules de `tests/`
- Série : [lire la base en PostgreSQL](2026-11-06-lire-la-base-en-postgresql.md), où le pool qui se connecte en
  arrière-plan a été choisi

Les commits de la branche, après son rebase sur `main` (`ab4fde7`), sont `c4f9d04` (l'aide et les 12 premiers sites)
et `9f1135a` (le test de `kb serve-data`, relevé par la revue). Les autres commits de la liste viennent de `main` :
cette note n'en traite pas.

## Le pourquoi

Le 2026-11-11, la CI de la PR #579 est sortie rouge. Cette PR ne changeait pourtant que trois fichiers `.md`. Un seul
test avait échoué sur 350, dans le job `tests-postgresql` :
`test_on_postgresql_a_database_error_gives_500_without_detail_and_logs_its_type`. Il attendait au journal une erreur
de la base, `UndefinedTable`, et y a trouvé `PoolTimeout`. Relancé sur le même commit, le job est passé.

Un test qui échoue au hasard coûte cher. Une PR rouge ne se fusionne pas (`CLAUDE.md`), et chaque relance retarde la
fusion. Surtout, on finit par ne plus croire un rouge. Cette PR rend ces tests indépendants du temps que met le runner
à ouvrir une connexion, sans rien changer à ce que fait l'API de données en ligne. Rien ne change sous `src/`.

## Le comment

### Le pool se connecte en arrière-plan, et une requête n'attend que 2 s

L'API de données lit PostgreSQL par un pool de connexions, que `open_reading_pool` ouvre sans attendre la base :

```python
        timeout=READING_POOL_WAIT_SECONDS,
        ...
    pool.open(wait=False)
```

(`src/k_b/database/postgresql.py:257` et `:264`.) Le délai vaut 2 s, et le pool garde au moins une connexion :

```python
READING_POOL_MIN_SIZE = 1
READING_POOL_MAX_SIZE = 4
READING_POOL_WAIT_SECONDS = 2
```

(`src/k_b/core/config.py:207-209`.) `open(wait=False)` rend la main tout de suite : le pool ouvre sa première
connexion dans un fil à lui. Si une requête arrive avant, elle attend au plus `timeout`, puis reçoit `PoolTimeout`.
C'est voulu en production : `kb serve-data` démarre sans attendre la base, comme sur SQLite (docstring de
`open_reading_pool`, `src/k_b/database/postgresql.py:240-242`).

Les tests, eux, ouvraient le pool et lisaient aussitôt. Leur première requête faisait donc la course avec la
connexion en arrière-plan. Sur un runner rapide, la connexion gagne toujours. Sur un runner lent, la requête peut
attendre plus de 2 s et échouer avant même d'atteindre la base.

### Une aide de `tests/` qui attend la première connexion

```python
@contextmanager
def open_connected_readers(location, query_timeout_seconds):
    ...
    with open_readers(location, query_timeout_seconds) as readers:
        if not isinstance(readers, Path):
            readers.wait()
        yield readers
```

(`tests/database/connected_readers.py:9-19`.) L'aide ouvre les lecteurs par la même fonction que `kb serve-data`
(`open_readers`). Puis, sur PostgreSQL, elle appelle `ConnectionPool.wait()`, qui bloque jusqu'à ce que le pool ait
`min_size` connexions, ici une. Au-delà de 30 s (le défaut de `wait`), `wait()` ferme le pool et lève `PoolTimeout`.
Une fois l'aide passée, la première requête du test trouve une connexion prête : elle ne dépend plus du runner.

Sur SQLite, `open_readers` rend le fichier lui-même (`src/k_b/database/engine.py:64-66`) : il n'y a rien à attendre.
L'aide fait le même test de type que `connect_reader`. Trois des sites tournent sur les deux moteurs
(`tests/database/test_reading.py:47`, `tests/database/test_reading_on_both_engines.py:82`,
`tests/etl/test_import_on_both_engines.py:184`).

Treize sites ouvrent le pool puis lisent aussitôt. Douze appellent l'aide à la place d'`open_readers`. Les deux tests
de refus (`tests/database/test_reading_pool.py:31-51`) gardent `open_readers` : ils refusent un délai ou une URL avant
toute connexion.

### `conftest.py` importe l'aide dans sa fixture

```python
    # Imported here: tests/test_e2e_selection.py runs this file without the rest of tests/.
    from database.connected_readers import open_connected_readers
```

(`tests/conftest.py:313-314`.) `tests/test_e2e_selection.py` charge `conftest.py` seul, sans le reste de `tests/`. Un
import en tête du module y échouerait. Les deux autres aides que `conftest.py` utilise sont importées de la même façon
(`tests/conftest.py:221`, `:243`).

### Le test de `kb serve-data` : remplacer `open_readers` dans la commande

Le treizième site n'ouvre pas le pool lui-même : il lance `kb serve-data`, qui l'ouvre. Le test remplace donc
`open_readers` dans le module de la commande :

```python
    monkeypatch.setattr(serve_data_command, "open_readers", open_connected_readers)
```

(`tests/data_api/test_serve_data.py:374`.) `serve_data_command` importe `open_readers` en tête de module
(`src/k_b/commands/serve_data_command.py:16`) et l'appelle à la ligne 44. Le `monkeypatch` remplace ce nom-là, pour ce
test seul. Le reste de la commande tourne tel quel.

## Choix faits et options écartées

- **Retenu : attendre dans les tests, par `ConnectionPool.wait()`.** C'est la méthode que la documentation de
  psycopg donne pour s'assurer, au démarrage, que le pool a ses connexions (« Pool startup check »).
- **Écarté : allonger `READING_POOL_WAIT_SECONDS` dans les tests.** Les tests ne tourneraient plus avec le délai de
  production, et un runner encore plus lent échouerait de nouveau.
- **Écarté : `open(wait=True)` dans `src/`.** `kb serve-data` attendrait alors la base au démarrage, ce qu'il ne fait
  pas sur SQLite. Le critère de #581 l'interdit aussi : le délai de l'API en ligne ne change pas sans accord de
  Sabine.
- **Écarté : corriger ce seul test (option A du plan).** Sabine a retenu l'option B : douze autres sites ont la même
  course.
- **Écarté : `readers.wait()` dans la fixture partagée `requests_while_serving`.** Essayé, puis retiré. Le test d'une
  base injoignable (`test_serve_on_a_base_out_of_reach_answers_500_and_writes_no_text_of_libpq`,
  `tests/data_api/test_serve_data.py:449`) partage cette fixture et attend son `PoolTimeout`. `wait()` le bloquait
  30 s, puis fermait le pool : `1 failed, 4492 passed`. Le mécanisme retenu a été accepté par time-knight.
- **Écarté : un rouge provoqué sur le Mac.** Un greffon pytest, jamais versionné, devait ralentir chaque connexion de
  2,5 s. Sabine n'a pas le mot de passe de son PostgreSQL local : le rouge est l'échec réel de la CI (décision de
  Sabine).

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| CI de #579, run 43078319143, tentative 1, `tests-postgresql` : `database_error: PoolTimeout`, `1 failed, 349 passed, 4508 deselected in 52.94s` | le rouge : la requête n'a pas reçu de connexion dans les 2 s |
| Même run, tentative 2, même commit : `350 passed, 4508 deselected in 27.20s` ; la ligne de `test_api_errors.py` prend 10,5 s en tentative 1 et 2,7 s en tentative 2 | le même code passe sur un runner plus rapide : l'échec dépend du temps |
| `uv run pytest` après le rebase sur `ab4fde7` : `4757 passed, 365 deselected` | la moitié SQLite, dont la branche `Path` de l'aide, passe |
| `uv run pytest -m postgresql --collect-only -q` : `350/5122 tests collected` | les tests marqués `postgresql` se chargent avec leurs nouveaux imports, autant que la CI en lance |
| `wait()` dans `requests_while_serving` : `1 failed, 4492 passed` | pourquoi l'attente ne va pas dans la fixture partagée |
| `uv run ruff check --no-cache`, `ruff format --check`, `mypy --strict` : verts | les contrôles du dépôt |
| CI de la PR de #581, job `tests-postgresql` | le vert des 350 tests sur PostgreSQL, à lire dans la PR |

## Ce que tu dois pouvoir défendre

1. **Comment sais-tu que la cause est le délai du pool ?** `PoolTimeout` est l'erreur que lève le pool quand aucune
   connexion n'est prêtée dans son `timeout`, ici 2 s (`src/k_b/database/postgresql.py:257`). La relance du même
   commit passe, sur un runner deux fois plus rapide (27,20 s contre 52,94 s). Ce qui a ralenti le runner, en
   revanche, reste inconnu.
2. **Pourquoi corriger les tests et pas l'API ?** En production, démarrer sans attendre la base est un choix
   (docstring de `open_reading_pool`). Le délai de 2 s est une décision de Sabine, que le critère de #581 protège. Le
   défaut venait de tests qui lisaient avant que le pool soit prêt.
3. **Que se passe-t-il si le serveur de test est injoignable ?** `wait()` bloque 30 s, ferme le pool et lève
   `PoolTimeout` : le test échoue avec cette erreur, sans être sauté. Les fixtures de base se connectent au serveur
   avant (`tests/conftest.py`), donc un serveur injoignable les fait échouer d'abord.
4. **Pourquoi un `monkeypatch` pour `kb serve-data` ?** La fixture qui sert la requête est partagée avec le test de
   la base injoignable, qui a besoin du `PoolTimeout`. Le `monkeypatch` ne touche que le test qui lit
   (`tests/data_api/test_serve_data.py:374`). L'attente reste ainsi dans une seule aide.
5. **L'instabilité a-t-elle disparu ?** Pour la première connexion de chaque pool, oui, par construction. Le vert
   de la CI ne prouve qu'un passage. Deux tests dépendent encore d'une connexion ouverte à la demande (voir
   ci-dessous).

## Zones non vérifiées

- Pas de rouge à la demande : le greffon qui ralentit les connexions n'a pas tourné, faute de serveur local
  accessible. La correction n'a donc pas été vue verte sous ce ralentissement.
- Ce qui a ralenti le runner de la tentative 1 n'est pas connu.
- `wait()` n'est appelé qu'à l'ouverture du pool, son usage documenté (« after creation »). Une connexion que le pool
  rouvre plus tard n'est pas attendue. Cela laisse deux tests dépendants du runner :
  `tests/database/test_postgresql.py:479` (deux connexions à la fois) et `tests/database/test_reading_pool.py:174`
  (la relecture après une fin de session). Les deux sont écrits dans #581.
- En ligne, la même course est possible au réveil de l'API de données : la première requête peut arriver avant la
  première connexion, jeton de l'identité managée compris. C'est une hypothèse, jamais observée.

## Ce qui reste

- Les deux tests ci-dessus. Les couvrir demanderait un autre mécanisme, par exemple `pool.connection(timeout=…)` :
  hors du plan, accord de time-knight.
- La mesure de la course au démarrage en ligne : une issue à part, « Vérifier la course du pool au démarrage de kb
  serve-data en ligne » (S). Son brouillon est écrit ; elle s'ouvre par Sabine. La suite, et le délai de 2 s, restent
  à Sabine.
