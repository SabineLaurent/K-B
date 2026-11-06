# Lire la base en PostgreSQL comme en SQLite : `read_items`, l'API de données et les purges

- **Date** : 2026-11-06
- **Branche** : `feat/postgresql-read`
- **Issue** : #418 (PR à venir)
- **Série** : suit [l'écriture sur PostgreSQL (#417)](2026-11-06-creer-la-base-et-importer-en-postgresql.md)
  et [le délai et les bornes du détail (#331)](2026-11-06-delai-et-bornes-du-detail-de-l-api-de-donnees.md).
- **Fichiers principaux** : `src/k_b/database/reading.py`, `src/k_b/database/postgresql.py`,
  `src/k_b/database/engine.py`, `src/k_b/commands/serve_data_command.py`, `src/k_b/purge/base.py`,
  `src/k_b/purge/registry.py` ; tests : `tests/database/test_reading_pool.py`,
  `tests/database/test_reading_on_both_engines.py`, `tests/conftest.py`.

## Le pourquoi

#417 a fait écrire K-B sur les deux moteurs : `kb create-db` et `kb import` créent et remplissent une
base PostgreSQL quand `KB_DATABASE_URL` est posée. Il restait la lecture. `kb serve-data` lisait
encore le fichier SQLite, même avec `KB_DATABASE_URL`. Et la requête de la liste, `read_items`,
échouait sur PostgreSQL à chaque appel : constaté le 06/11 sur PostgreSQL 18.4, `json_each(:kinds)`
lève 42883 (`text = json`).

Cette PR fait lire à l'API de données la base que nomme `KB_DATABASE_URL`, avec les mêmes résultats
qu'en SQLite. Elle garde les protections de l'API : lecture seule, délai de 5 s, aucun texte de libpq
au journal. Elle prépare #421 (la base en ligne, sur Azure). Elle fait aussi prendre aux purges le
verrou des écrivains, que #417 avait laissé à #418.

Le critère de fin de l'issue :
- le job CI sur PostgreSQL est vert, sans test sauté ;
- la comparaison des résultats de `read_items` sur les deux moteurs est égale.

## Le comment

### 1. Une seule requête de liste pour les deux moteurs

Trois écarts entre SQLite et PostgreSQL ont été trouvés en lançant la requête de `main` sur
PostgreSQL :

```python
WHERE (CAST(:since AS TEXT) IS NULL OR listed.source_date >= :since)
    AND (CAST(:pattern AS TEXT) IS NULL
        OR lower(listed.title) LIKE lower(:pattern) ESCAPE '\'
```
(`src/k_b/database/reading.py:77-79`)

- **`CAST(:x AS TEXT) IS NULL`** : `:since IS NULL` seul ne dit pas à PostgreSQL le type du
  paramètre, qui refuse alors la requête (42P08, observé). Le `CAST` le lui donne. SQLite l'accepte
  sans rien changer.
- **`lower(…) LIKE lower(…)`** : `LIKE` ignore la casse des lettres ASCII en SQLite, pas en
  PostgreSQL. `lower()` ne plie que les lettres ASCII sur les deux moteurs, à condition que la base
  PostgreSQL soit en collation C, ce que `kb create-db` exige. Les résultats restent donc ceux de
  SQLite, accents compris : `É` ne trouve pas `é` sur aucun des deux (vérifié le 06/11 sur
  PostgreSQL 18.4).
- **Les sortes, par un `IN` généré**, à la place de `json_each` :

```python
    distinct_kinds = list(dict.fromkeys(kinds))
    if not distinct_kinds:
        return "", {}
    names = [f"kind_{position}" for position in range(len(distinct_kinds))]
```
(`src/k_b/database/reading.py:351-355`)

Un marqueur par sorte demandée (`:kind_0`, `:kind_1`…), sans doublon. Les noms viennent de la
position seule, jamais d'une valeur : aucune valeur n'entre dans le texte SQL, les sortes sont liées
en paramètres. Une liste vide n'ajoute aucun filtre. Il y a 7 marqueurs au plus : l'API refuse plus
de 7 `kind`.

### 2. Les lecteurs : un fichier ou un pool

L'API ne reçoit plus un chemin, mais des « lecteurs » :

```python
Readers = Path | ReadingPool
```
(`src/k_b/database/engine.py:21`)

- `open_readers` (`engine.py:59`) rend le chemin tel quel en SQLite. En PostgreSQL, il ouvre un pool
  `psycopg_pool.ConnectionPool` de 1 à 4 connexions.
- `connect_reader` (`engine.py:72`) prête une connexion pour une requête. En SQLite, c'est une
  connexion neuve en `mode=ro`, avec son délai, fermée après. En PostgreSQL, c'est une connexion du
  pool, rendue après.
- `kb serve-data` ouvre les lecteurs autour de `uvicorn.run` et les passe à `create_app`.

Le pool se connecte en arrière-plan (`pool.open(wait=False)`, `postgresql.py:200`) : `kb serve-data`
démarre sans attendre la base, comme en SQLite. Une requête attend une connexion 2 s au plus, puis
répond 500 `database_error` (`PoolTimeout` au journal).

### 3. Chaque connexion du pool : lecture seule, un seul état de la base, un délai

```python
    connection.isolation_level = IsolationLevel.REPEATABLE_READ
    connection.read_only = True
    reader = PostgresConnection(connection)
    reader.execute(SET_STATEMENT_TIMEOUT, (statement_timeout,))
    # A rollback would undo the setting.
    reader.commit()
```
(`src/k_b/database/postgresql.py:214-219`, `configure_reader`)

Le pool appelle `configure_reader` sur chaque connexion neuve.

- **Les deux attributs d'abord** : psycopg les refuse une fois une transaction ouverte. Ensuite,
  chaque transaction s'ouvre en `REPEATABLE READ READ ONLY`. Une écriture est refusée par le
  serveur (SQLSTATE 25006, testé). Les trois lectures d'un détail voient un seul état de la base,
  même si un import commite entre elles (testé).
- **Puis `statement_timeout`**, par `set_config(…, false)`, pour toute la session : c'est le délai
  de 5 s de l'API. Il est posé par K-B, pas par le serveur, si bien qu'une base installée sans
  réglage n'est jamais lue sans délai. Au-delà, PostgreSQL arrête l'instruction (SQLSTATE 57014),
  et `is_query_timeout` (`errors.py:102`) donne le même 503 `query_timeout` qu'en SQLite.
- **Puis `commit()`**, qui sert à deux choses. Un `rollback` annulerait le réglage. Et le pool
  écarte une connexion qu'on lui rend en transaction.

Un délai de moins d'1 ms est refusé (`postgresql.py:180`) : à 0, `statement_timeout` n'arrête plus
rien.

### 4. Finir chaque lecture à un seul endroit, même quand le serveur a coupé la session

`borrow_reader` finit lui-même la transaction de chaque requête, sur un succès comme sur une erreur.
Sans cela, le pool ferait le `rollback` lui-même et journaliserait la connexion (hôte, utilisateur).

```python
        try:
            # A connection psycopg knows closed has no transaction left to end.
            if reader.in_transaction:
                reader.rollback()
        except psycopg.Error as error:
            # The type only: the message of libpq may name the server.
            logger.warning("%s: %s", READER_SESSION_LOST, type(error).__name__)
            connection.close()
        finally:
            pool.putconn(connection)
```
(`src/k_b/database/postgresql.py:236-245`)

Les deux revues de code ont trouvé le cas que ce `except` traite. Si le serveur a fini la session
(redémarrage, coupure du réseau), le `rollback` lève. Cette erreur levée dans un `finally` remplaçait
celle de la requête : un 503 `query_timeout` devenait un 500. Elle faisait aussi échouer une requête
qui avait déjà lu ses lignes. Maintenant, la requête garde sa réponse ou sa propre erreur. La perte
est journalisée une fois, par le type de l'erreur seul (règle 3 de `conventions.md`), et le pool
remplace la connexion fermée.

Le détail ouvrait et fermait lui-même sa transaction. Il passe maintenant par deux fonctions du
moteur, l'une pendant de l'autre :

```python
def end_reading(connection: Connection) -> None:
    ...
    if isinstance(connection, SqliteConnection) and connection.in_transaction:
        connection.rollback()
```
(`src/k_b/database/engine.py:98-103`)

En SQLite, `begin_reading` envoie `BEGIN` et `end_reading` envoie `ROLLBACK`. En PostgreSQL, les deux
ne font rien : psycopg ouvre la transaction à la première instruction, et `borrow_reader` la finit.
Le `rollback` d'une lecture PostgreSQL n'existe ainsi qu'à un endroit, `borrow_reader`, qui sait
traiter une session perdue.

### 5. Ni l'URL ni un texte de libpq au journal

- **Une URL illisible** : elle est lue par `conninfo_to_dict` avant d'ouvrir le pool. Une URL que
  libpq ne lit pas est refusée par `make_unreadable_url_error()` (`postgresql.py:150`), en code 2,
  sans le texte de libpq, qui cite toute l'URL, mot de passe compris. La même fonction sert la
  connexion de #417 : le refus n'est écrit qu'une fois.
- **Les loggers des bibliothèques** : `psycopg` et `psycopg_pool` sont tenus à ERROR
  (`LIBRARY_LOG_LEVELS`, `commands/run_log.py:46-54`). À WARNING, le pool recopie le texte de libpq
  et le `repr` des connexions (hôte, utilisateur, base). Une base injoignable ne se voit donc qu'à la
  requête, par `database_error: PoolTimeout request_id=…`.

### 6. Le verrou des écrivains en tête des purges, et des tests sur les deux moteurs

`purge_expired_rows` et `purge_registry` appellent `lock_for_writing(connection)` en tête de leur
transaction (`purge/base.py:37`). En PostgreSQL, une purge attend donc un import en cours, 5 s au
plus, puis échoue sans rien supprimer. Leur `rollback` ne tourne que sur une transaction ouverte
(`purge/base.py:49`), comme celui de l'import. Sinon, une connexion fermée par psycopg sur un signal
ferait sortir la commande en 1 au lieu de 143.

Côté tests, une fixture paramétrée fait tourner chaque test de lecture sur les deux moteurs :

```python
ENGINES = ("sqlite", pytest.param("postgresql", marks=pytest.mark.postgresql))
```
(`tests/conftest.py:45`)

La moitié PostgreSQL porte le marqueur `postgresql` : `uv run pytest` l'écarte, et `-m postgresql`
la lance. Ses fixtures sont prises par `request.getfixturevalue` dans la seule branche PostgreSQL
(`tests/conftest.py:276`). Sans cela, la moitié SQLite demanderait le serveur, et `uv run pytest`
échouerait sans `KB_TEST_POSTGRESQL_URL`. `tests/test_postgresql_selection.py` vérifie cette
sélection en lançant pytest dans un sous-processus.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écartés, et pourquoi |
|---|---|---|
| `IN` généré, un marqueur par sorte | le même SQL sur les deux moteurs, aucune valeur dans le texte | `= ANY(:kinds)` : un tableau propre à PostgreSQL ; garder `json_each` en SQLite : deux SQL |
| `CAST(:x AS TEXT) IS NULL` | 42P08 observé sans | une requête par combinaison de filtres (8 textes) |
| `lower() LIKE lower()` | mêmes résultats qu'en SQLite, la base étant en collation C | `ILIKE` : propre à PostgreSQL (règle 1 de `poc.md`) ; `citext` : un changement de schéma ; plier en Python : `str.lower` plie aussi `É`, la base non |
| Un pool `psycopg-pool` 3.3.3 (publiée le 2026-09-22, `uv.lock`), 1 à 4 connexions, 2 s d'attente | sans pool, chaque requête referait TLS et l'authentification ; 2 s plus 5 s restent sous les 10 s du client de l'API IA | une connexion par requête ; un 503 propre à l'attente (un code de plus au contrat) |
| `REPEATABLE READ READ ONLY` par les attributs de psycopg | un seul état de la base pour le détail ; écriture refusée par le serveur | `SET TRANSACTION` après le `BEGIN` : l'isolement écrit à deux endroits |
| `statement_timeout` de session, posé par K-B | une seule valeur pour les deux moteurs, dans le dépôt, prouvée en CI | `ALTER ROLE … SET` : la valeur hors du dépôt, et un oubli laisse la lecture sans délai ; `options=-c` : refusé par PgBouncer ; `SET LOCAL` par requête ; `transaction_timeout` : il ferme la session (FATAL) |
| `check_connection` à chaque prêt | une connexion coupée par un redémarrage n'est pas servie | (coût : un aller-retour par requête, à mesurer sur Azure, « For #421 ») |
| `borrow_reader` finit la transaction, et le pool reste tenu à ERROR | défense en profondeur : le niveau de journal est une couche, le `rollback` de K-B une seconde | laisser `putconn` faire le `rollback` (constat 6 de la seconde revue, écarté par time-knight) |
| `psycopg` et `psycopg_pool` à ERROR dans `LIBRARY_LOG_LEVELS` | la façon déjà posée pour `azure` et `urllib3` (#412) | un `NullHandler` dans `postgresql.py` : une seconde façon de taire une bibliothèque |
| Sur SIGTERM, pas de fermeture du pool | uvicorn relance le signal et le processus meurt ; une lecture seule n'a rien à perdre | fermer le pool dans le `lifespan` de FastAPI : chaque test de l'API devrait entrer dans le `TestClient` |
| Version de l'API 0.11.0 | sur PostgreSQL, une base injoignable répond 500, et non plus 503 `database_missing` : « un changement visible par un client change la version » (spec) | garder 0.10.0 (constat 10 de la première revue) |

Le délai par session révise une recommandation de la session de #331 (`ALTER ROLE`), avec l'accord de
time-knight. C'est écrit au journal ADR, 2026-11-06, « API de données : la lecture sur PostgreSQL
(#418) ». Les tris des deux revues ont été tranchés par time-knight (délégation de Sabine du 15/10).

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_read_items_gives_the_same_results_on_postgresql_as_on_sqlite` (`tests/database/test_reading_on_both_engines.py`) | **critère** : chaque filtre seul et ensemble, chaque page, chaque détail et les tendances, égaux sur les deux moteurs |
| `import_on_both` (`tests/etl/test_import_on_both_engines.py`), avec un clip au titre accentué | après chaque import, toutes les pages et chaque détail égaux ; `école` ne trouve pas `École`, `ÉCOLE` le trouve, sur les deux |
| `uv run pytest -m postgresql` → 301 passed, 3684 deselected, aucun skipped (local, 18.4) | **critère** : la moitié PostgreSQL passe, sans test sauté |
| `test_a_write_through_a_connection_of_the_pool_is_refused` | lecture seule par le serveur (25006) |
| `test_the_detail_reads_one_state_of_the_base_while_a_writer_commits` | `REPEATABLE READ` : un seul état de la base au détail |
| `test_on_postgresql_a_request_beyond_its_deadline_gives_503_query_timeout_without_detail` | 57014 → 503 `query_timeout` sur les trois routes, sans détail |
| `test_serve_reads_the_postgresql_base_of_kb_database_url_with_the_deadline_it_logs` | `kb serve-data` lit `KB_DATABASE_URL`, et le délai appliqué (`SHOW statement_timeout`) est celui du journal |
| `test_serve_on_a_base_out_of_reach_answers_500_and_writes_no_text_of_libpq` | serveur injoignable : démarrage, `/health` 200, 500 `PoolTimeout`, ni URL ni texte de libpq écrits |
| `test_serve_without_base_answers_health_and_503_database_missing_without_pool` | sans base (en ligne avant #421) : `/health` 200, 503 `database_missing`, aucun pool |
| `test_a_request_that_read_is_served_…`, `test_a_detail_that_read_is_served_…` et les deux tests de l'erreur qui passe (`test_reading_pool.py`) | une session finie par le serveur (`pg_terminate_backend`) ne remplace ni la réponse ni l'erreur ; une ligne `reader_session_lost: AdminShutdown` |
| `tests/purge/test_purge_lock.py` | une purge attend le verrou des écrivains, puis échoue sans rien supprimer |
| `test_schema_postgresql_has_the_structure_of_schema_sql` | colonnes, `NOT NULL`, clés, `UNIQUE`, clés étrangères et index égaux, un écart voulu (`md5(url)` d'un clip) |
| Essai réel du 06/11 (section « Real run » de la PR) | sur les copies du brut de Sabine : mêmes comptes, mêmes journaux, `read_items`, 3207 détails, tendances et API égaux, `0 difference(s)` |

## Ce que tu dois pouvoir défendre

1. **Pourquoi le délai est-il posé par K-B et non par le serveur ?** Une valeur posée par le serveur
   (`ALTER ROLE`) vit hors du dépôt. Un oubli à l'installation laisserait la lecture sans délai, et
   rien ne le verrait. Posée par `configure_reader`, la valeur est la même que pour SQLite, et un test
   la lit sur une connexion du pool (`SHOW statement_timeout`).
2. **Le délai de 5 s borne-t-il une requête entière ?** En SQLite, oui. En PostgreSQL, non : il
   borne chaque instruction. Le détail en fait jusqu'à trois, soit 15 s en théorie, plus 2 s
   d'attente du pool, au-delà des 10 s du client de l'API IA. C'est une limite choisie au plan et
   écrite (specs-api « Délai », `MEMORY.md`). `transaction_timeout` bornerait la requête entière,
   mais il ferme la session.
3. **Où est la sécurité de la lecture ?** Il y en a plusieurs couches :
   - lecture seule refusée par le serveur (`READ ONLY`) ;
   - paramètres toujours liés, même les sortes (`make_kinds_filter`) ;
   - délai par instruction ;
   - URL jamais citée (`make_unreadable_url_error`) ;
   - loggers des bibliothèques à ERROR ;
   - erreurs servies sans détail (`data_api/errors.py`).
   
   Le rôle en lecture seule côté serveur vient avec #421.
4. **Que se passe-t-il si le serveur redémarre pendant une requête ?** La requête garde sa réponse ou
   sa propre erreur. `reader_session_lost: <type>` est journalisé. Le pool remplace la connexion, et
   `check_connection` ne prêtera pas une connexion morte à la requête suivante
   (`postgresql.py:196`, `:236-245`).
5. **Pourquoi `lower()` des deux côtés, alors que SQLite ignorait déjà la casse ?** Pour écrire un
   seul SQL qui rende les mêmes résultats sur les deux moteurs. Le coût a été mesuré sur SQLite : une
   recherche ordinaire passe de 0,017 s à 0,029 s, la pire de 9,66 s à 9,72 s sans délai.

## Zones non vérifiées

- **Ce que les bibliothèques journalisent** à ERROR (rien pour `psycopg_pool` 3.3.3, seulement
  l'échec d'un rappel de notice pour psycopg) a été lu dans leur code installé, pas observé ligne
  par ligne. Les tests vérifient seulement qu'aucun texte de libpq n'arrive dans la sortie d'erreur
  ni dans `kb-serve-data.log`, sur un serveur injoignable.
- **Le coût de `check_connection`** (un aller-retour par requête) n'a été mesuré nulle part, ni en
  local ni sur Azure.
- **Le dépassement du délai sur une instruction PostgreSQL** n'est prouvé que par une table
  verrouillée, avec un délai de 100 ms. Il n'a pas été mesuré sur une vraie recherche lente : l'essai
  réel n'a atteint aucun délai.
- **Le comportement derrière un pooler** (PgBouncer en mode transaction) n'est pas essayé : un `SET`
  de session n'y tiendrait pas.
- **La CI** : le job `postgresql.yml` est vert en local par la même commande, mais son exécution sur
  la PR reste à voir.

## Ce qui reste

- **#421 (la base en ligne)** :
  - `sslmode` dans l'URL ;
  - le rôle en lecture seule de l'API ;
  - une ligne de K-B qui nomme la cause d'un échec de connexion du pool (aujourd'hui, seulement
    `PoolTimeout`) ;
  - la question d'un 503 `database_unavailable` et d'une sonde qui lit la base ;
  - la mesure de `check_connection` ;
  - pas de PgBouncer en mode transaction, ou bien `ALTER ROLE … SET statement_timeout` en plus.
- **#445** : les scénarios de « mêmes lignes » au-delà du critère (`revision_not_newer`,
  `already_seen`, KEV importé en retard…), et la preuve que chaque constante des écrivains a tourné
  sur PostgreSQL.
- **#430** : borner la lecture des surlignages et du texte d'un clip, aujourd'hui bornée en temps
  seulement.
- **La PR qui fera entrer `tests-postgresql` dans `ci.yml`** : après #418, sur décision à part.
