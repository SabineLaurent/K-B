# Nommer et borner les échecs de connexion à la base, et servir `GET /health/database`

- **Date** : 2026-11-27
- **Branche** : `fix/database-connection-failures`, de `533e6fe8` à `fa27cb25` (cinq étapes de code, une fusion
  d'`origin/main`, deux commits de fiches, puis les corrections des revues)
- **Issue** : #458
- **Fichiers principaux** : `src/k_b/database/postgresql.py`, `src/k_b/database/entra.py`,
  `src/k_b/database/engine.py`, `src/k_b/data_api/errors.py`, `src/k_b/data_api/database_health.py`,
  `src/k_b/commands/smoke_test_command.py`, `src/k_b/core/config.py`, `docs/specs-api.md` (« Santé de la base »)
- **Série** : suite de [Mettre la base PostgreSQL en ligne](2026-11-06-mettre-la-base-postgresql-en-ligne.md), de
  [Lire la base en PostgreSQL](2026-11-06-lire-la-base-en-postgresql.md) et de
  [kb smoke-test](2026-11-06-kb-smoke-test-api-et-stockage-d-echange.md)

## Le pourquoi

Depuis #421, l'API de données lit une base PostgreSQL en ligne, par un pool de connexions, avec un jeton de
l'identité managée (Entra). Les revues de #421 et des PR qui l'ont suivie ont relevé huit points où un échec de la
base était mal nommé ou mal borné. Un pool épuisé rendait 500, comme une erreur imprévue. La cause d'une connexion
refusée ne se lisait nulle part, puisque K-B tient au silence le journal de psycopg, qui cite l'hôte et
l'utilisateur. Un échec de jeton pouvait durer 45 s, au-delà des 10 s du client de l'API IA. Sur une base sans
tables, l'API rendait 500 (constaté à l'application de #421), et `kb import` échouait à sa première requête, comme
sur une panne quelconque.

C'est du monitorage de l'application : un échec doit porter un nom stable, que l'on cherche au journal, et une
réponse que le client sait traiter (503 : réessayer plus tard ; 500 : un défaut à corriger). La route
`GET /health/database` répond à une seule question, « l'API lit-elle sa base ? », pour l'opératrice, pour
`kb smoke-test` et pour la surveillance. Les sondes d'ACA ne l'appellent jamais. Une sonde qui échoue fait
redémarrer le conteneur, et une panne de la base relancerait l'API en boucle sans rien réparer.

## Le comment

### Un état nommé par cause, jamais le texte de libpq

Le pool ouvre ses connexions en arrière-plan. Quand l'une échoue, psycopg_pool journalise le texte de libpq sous un
logger que K-B tient à ERROR (`LIBRARY_LOG_LEVELS`, `src/k_b/commands/run_log.py`). Ce texte n'est donc jamais
écrit, et il ne doit pas l'être, car il cite l'hôte, le port et l'utilisateur. K-B donne au pool sa propre classe
de connexion, qui écrit la cause avant de rendre l'erreur au pool :

```python
    @classmethod
    def connect(cls, conninfo: str = "", **kwargs: Any) -> Self:
        try:
            return super().connect(conninfo, **kwargs)
        except psycopg.OperationalError as error:
            log_connection_failure(error)
            raise
```

(`src/k_b/database/postgresql.py:333-340`, branchée par `connection_class=ReaderConnection` à la ligne 292.) La
cause se lit d'abord par la classe de l'erreur : `database_no_token` pour un jeton absent, `database_connect_timeout`
pour un délai dépassé. Sinon, elle se lit par un fragment du texte, pris dans une table fermée,
`CONNECTION_FAILURE_FRAGMENTS` (`postgresql.py:76`). Le premier fragment trouvé donne la cause ; si aucun ne s'y
trouve, la cause est `database_connection_failed`. Le texte sert à choisir un mot d'une liste ; il n'est jamais
cité. L'authentification vient en premier : le refus de `pg_hba.conf` nomme aussi le chiffrement du client
(« SSL encryption »), et il reste un refus d'authentification quel que soit le fragment de TLS que la table recevra.

Le jeton pose un cas à part. psycopg_pool 3.3.3 calcule les paramètres d'une connexion, donc demande le jeton, avant
d'appeler `connection_class.connect` et hors de son `try` (`psycopg_pool/pool.py:618`, `_resolve_kwargs` ; `:624`,
`connection_class.connect`). La classe ne verrait donc jamais l'échec du jeton. `logging_token_failures`
(`postgresql.py:343`) enveloppe pour cela les paramètres eux-mêmes et écrit la même ligne,
`database_connection_failed: database_no_token`.

### Deux réponses de plus : 503 `database_unavailable` et 503 `database_missing`

L'API de données traduit chaque erreur de la base en une réponse, au même endroit, quelle que soit la route :

```python
    if is_pool_timeout(error):
        logger.warning("%s: %s request_id=%s", DATABASE_UNAVAILABLE, type(error).__name__, ...)
        return respond_with_error(503, DATABASE_UNAVAILABLE)
    if is_missing_table(error):
        logger.error("%s: %s request_id=%s", DATABASE_MISSING, describe_engine_error(error), ...)
        return respond_with_error(503, DATABASE_MISSING)
```

(extrait resserré de `src/k_b/data_api/errors.py:94-111`.) Un `PoolTimeout` dit que le pool n'a prêté aucune
connexion dans son attente de 2 s : toutes sont prêtées, ou aucune n'a pu s'ouvrir, et la cause a alors sa propre
ligne, écrite plus tôt. Le SQLSTATE 42P01 (`undefined_table`) dit qu'une table de K-B manque : c'est une base que
`kb migrate-database` n'a pas encore créée. Les deux sont des 503, une indisponibilité, et non des 500, des défauts
du code. Le message de PostgreSQL nomme la table : la ligne ne garde que la classe et le SQLSTATE
(`describe_engine_error`).

### Un jeton demandé une fois, en 7 s au plus, pour le pool seul

azure-core réessaie trois fois une demande de jeton échouée, et attendrait 300 s chaque réponse sans délai fixé. Avant
#458, K-B fixait déjà 5 s et 10 s, mais gardait ces nouvelles tentatives : la mesure locale a donné 44,82 s (4
requêtes) pour un point d'identité muet. Le pool reçoit maintenant un credential qui ne réessaie pas :

```python
    if is_asked_once:
        return ManagedIdentityCredential(
            client_id=client_id, transport=transport, retry_total=DATABASE_TOKEN_RETRIES
        )
    return ManagedIdentityCredential(client_id=client_id, transport=transport)
```

(`src/k_b/database/entra.py:46-50`.) `DATABASE_TOKEN_RETRIES` vaut 0, avec 2 s pour se connecter au point d'identité
et 5 s pour lire sa réponse (`src/k_b/core/config.py:203-205`). Ces 7 s restent sous les 10 s du client de l'API IA
(`DATA_API_READ_TIMEOUT_SECONDS`), comme l'issue le demande. Le pool n'a pas besoin des nouvelles tentatives
d'azure-core : il retente seul d'ouvrir une connexion, et une requête n'attend que ses 2 s pour en obtenir une. Une
connexion directe de `kb` (import, purge, `kb migrate-database` en job) garde les nouvelles tentatives, avec les
mêmes délais : aucun client n'attend derrière elle, et une erreur passagère du point d'identité n'y fait pas échouer
tout le job.

### Une base sans tables refusée avant le premier SQL

`kb import` et `kb purge` ouvraient la base par `connect_database`. Sur PostgreSQL, `check_database_exists` ne
vérifiait rien : la première requête échouait sur une table absente, comme une panne quelconque. Les deux commandes
passent désormais par une porte unique :

```python
    connection = postgresql.connect_postgresql(location)
    try:
        if not postgresql.has_tables(connection):
            raise MissingDatabaseError(f"{describe_location(location)} has no tables of K-B")
        connection.rollback()
    except BaseException:
        connection.close()
        raise
```

(extrait resserré de `src/k_b/database/engine.py:48-59`.) `has_tables` lit `to_regclass('source')`
(`postgresql.py:52`). Une seule table suffit, car `kb create-db` et `kb migrate-database` écrivent toutes les tables
dans une même transaction : une base les a toutes, ou n'en a aucune. Le `rollback` termine la lecture, pour que le
verrou de l'écrivain soit la première instruction de sa transaction. Le `except BaseException` ferme la connexion
même sur un Ctrl-C. `MissingDatabaseError` existait déjà pour un fichier SQLite absent : les commandes la traduisent
en code 2 (`ExitCode.NOT_STARTED`), avec un remède, « create it with kb create-db, or online with kb migrate-database ».

### `GET /health/database` : une ligne lue, une vérification à la fois

```python
    slot: Lock = request.app.state.database_health_slot
    if not slot.acquire(blocking=False):
        return respond_with_error(429, REQUEST_ALREADY_RUNNING, {"Retry-After": str(DATABASE_HEALTH_RETRY_AFTER_SECONDS)})
    try:
        with connect_reader(request.app.state.readers, request.app.state.query_timeout_seconds) as connection:
            check_reading(connection)
    finally:
        slot.release()
```

(extrait resserré de `src/k_b/data_api/database_health.py:23-36`.) La route n'a pas de clé : la surveillance doit
pouvoir l'appeler sans secret. Chaque appel tient une connexion du pool, donc un seul appel passe à la fois, et le
suivant reçoit 429 avec `Retry-After: 7`, soit l'attente du pool (2 s) plus une instruction (5 s). La lecture est
`SELECT 1 FROM source LIMIT 1` (`src/k_b/database/reading.py:27`) et passe par `connect_reader`, comme une route de
données. Ses erreurs remontent donc aux mêmes gestionnaires et donnent la même réponse pour la même cause. La
réponse ne contient que `{"status": "ok"}`, jamais une valeur de la base. La route est ajoutée par `add_route`, hors
de l'OpenAPI et hors des dépendances de l'application, la clé et le limiteur de débit
(`src/k_b/data_api/app.py:86-94`).

`kb smoke-test` l'appelle après les contrôles de l'API IA, par le client des sondes
(`src/k_b/commands/smoke_test_command.py:97-112`). Le `/health` de l'API de données réveille l'API. Pendant les
contrôles de l'API IA, son pool ouvre sa première connexion.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Cause lue par la classe, puis par une table fermée de fragments | Un état stable, cherchable, sans le texte qui cite l'hôte et l'utilisateur (règle 3 de `conventions.md`) | Citer le texte, même tronqué par `quote_value` : il porte l'hôte, le port et l'utilisateur |
| Fragments sensibles à la casse, et seulement des textes observés le 2026-11-26 (libpq 18, psycopg 3.3.8) | Un texte observé se rejoue dans un test ; un texte supposé n'a pas de preuve | Un fragment pour « SSL error: », jamais observé : écarté à la seconde revue |
| Le jeton intercepté sur les paramètres du pool, en plus de la classe | psycopg_pool demande le jeton hors du `try` de la classe (`pool.py:618`, `:624`) | La classe seule : elle ne voit jamais l'échec du jeton |
| « SSL SYSCALL error » nommé `database_connection_failed`, pas `database_tls_refused` | C'est une coupure de la connexion pendant TLS, pas un refus de TLS | Le fragment « SSL » seul, de la première version : il nommait une coupure comme un refus |
| 0 nouvelle tentative du jeton pour le pool seul | La raison du plan, les 10 s du client de l'API IA, ne vaut que pour le pool | 0 nouvelle tentative pour tout credential de la base, le texte du plan : une connexion directe de `kb` n'a pas de client qui attend, et une erreur passagère du point d'identité y ferait échouer le job |
| `SELECT 1 FROM source LIMIT 1` pour la santé | Une base sans tables y répond 503 `database_missing`, comme toute route | `SELECT 1` : il répondait 200 sur une base sans tables, que toute autre route refuse |
| Une vérification à la fois (429), par un `threading.Lock` pris sans attente, comme dans l'API IA | La route n'a ni clé ni limiteur de débit, qui sont des dépendances de l'app : un appel en boucle ne doit pas tenir les connexions du pool | Aucune autre option discutée |
| La santé de la base après les contrôles de l'API IA, dans `kb smoke-test` | Le pool d'une API à peine réveillée ouvre sa connexion pendant ces contrôles | Juste après le `/health` de l'API de données, la première version : la revue a relevé que le pool n'y a pas encore sa connexion |
| Le journal des requêtes nomme le chemin d'une route de Starlette seulement si l'app l'a (`src/k_b/core/api_request_log.py:65-70`) | Sur l'API IA, `GET /health/database` est noté `route=- status=404` : aucune route que l'app n'a pas | Ajouter `/health/database` à la liste fixe de chemins : l'API IA, qui n'a pas la route, l'aurait nommée |
| `check_connection` gardé (point 4), si la mesure sur Azure donne un p95 ≤ 20 ms | Le seuil est fixé avant de mesurer | Le retirer, ou le garder, sur une estimation |

Le contrat de l'API de données passe en 0.15.0 (`docs/api/openapi-donnees.json`, `docs/specs-api.md`) : deux codes
d'erreur nouveaux en 503, et une route.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_cause_of_a_failed_connection_is_named_by_its_class_or_a_fragment_of_libpq` (`tests/database/test_reading_pool.py:151`) | Chaque texte observé donne sa cause, une coupure TLS donne `database_connection_failed` |
| `test_the_pool_names_the_cause_of_a_failed_connection_without_the_text_of_libpq`, `test_under_entra_the_pool_names_an_identity_without_token` | Le pool écrit la cause, sans le texte de libpq, y compris pour un jeton absent |
| `test_under_entra_the_pool_asks_each_token_once`, `test_under_entra_a_direct_connection_lets_azure_core_ask_again_for_its_token` | Le pool demande une fois, une connexion directe réessaie |
| `test_a_token_that_does_not_come_fails_before_the_client_of_the_ai_api_stops_waiting` (`tests/database/test_entra.py:136`) | 2 + 5 < 10 |
| Mesure locale, faux point d'identité sur 127.0.0.1, credential réel | Point muet : 44,82 s (4 requêtes) avant, 5,00 s (1 requête) après ; 500 : 4,82 s avant, 0,00 s après |
| `test_a_pool_that_lends_no_connection_within_its_wait_gives_503_database_unavailable`, `test_serve_on_a_base_out_of_reach_answers_503_and_writes_no_text_of_libpq` | Pool épuisé → 503 nommé ; aucun texte de libpq au journal |
| `test_on_postgresql_a_base_without_its_tables_gives_503_database_missing_and_logs_its_state` (marqué `postgresql`) | 42P01 → 503 `database_missing` |
| `test_import_refuses_a_postgresql_base_without_its_tables_and_exits_2`, `test_purge_refuses_…_exits_2`, `test_a_postgresql_base_without_its_tables_is_refused_and_its_connection_closed` | Code 2, remède nommé, connexion fermée |
| `test_the_pool_and_its_scheduler_write_nothing_below_error` | `psycopg.pool` et `psycopg_pool.sched` tenus à ERROR (point 7) |
| `tests/data_api/test_database_health.py` (16 tests : 13 en local, 3 marqués `postgresql`) | 200 sur chaque moteur, sans clé ; réponse sans valeur de la base ; même erreur qu'une route ; 429 puis le verrou rendu après un échec |
| `test_no_probe_of_azure_container_apps_asks_the_database_health`, `test_the_database_health_is_out_of_the_openapi` | Aucune sonde d'ACA ne l'appelle ; elle n'est pas dans l'OpenAPI |
| `test_a_base_the_data_api_does_not_read_fails_the_smoke_test_and_the_other_checks_still_run` | `kb smoke-test` échoue sur une base illisible, sans arrêter ses autres contrôles |
| `test_a_route_of_starlette_refused_before_routing_is_logged_by_its_path`, `test_a_400_of_the_host_is_logged` | `route=/health status=400`, et `route=-` pour une route de FastAPI refusée avant le routage |
| `uv run pytest` : 5 909 passés ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` verts | Les contrôles du dépôt |

## Ce que tu dois pouvoir défendre

1. **Pourquoi lire le texte de libpq si on ne le cite jamais ?** psycopg lève `OperationalError` aussi bien pour un
   mot de passe refusé que pour un hôte injoignable : hors du délai et du jeton, que leur classe nomme, le texte est
   la seule source de la cause. On n'en garde qu'un mot d'une liste fermée, et le texte reste en
   mémoire, jamais au journal (`postgresql.py:365-376`).
2. **Pourquoi la sonde d'ACA ne lit-elle pas la base ?** Une sonde qui échoue fait redémarrer le conteneur. Pendant
   une panne de la base, l'API redémarrerait en boucle, sans rien réparer, et ne servirait même plus ses 503. `/health`
   dit que le processus répond ; `/health/database` dit que la base se lit (`src/k_b/core/api_health.py:1-5`).
3. **Une route sans clé, n'est-ce pas une porte ouverte ?** Elle ne rend que `{"status": "ok"}` ou un code d'erreur
   nommé, jamais une donnée. Un seul appel passe à la fois, et l'entrée de `ca-kb-data-api` est interne
   (`infra/modules/api-container-app.bicep:40`). OWASP API4 : la consommation est bornée par le verrou et par les
   délais du pool et de l'instruction.
4. **Pourquoi 503 et pas 500 ?** 503 dit au client « indisponible, réessaie » : la base n'est pas joignable ou pas
   encore créée. 500 dit « défaut du code » et reste pour une erreur imprévue (`errors.py:94-111`).
5. **Que se passe-t-il si le point d'identité ne répond plus ?** La demande de jeton du pool attend 2 s la connexion
   au point d'identité et 5 s sa réponse, sans nouvelle tentative, puis le pool écrit
   `database_connection_failed: database_no_token`. Une requête qui attend une connexion reçoit 503
   `database_unavailable` après les 2 s d'attente du pool. Mesuré en local : 5,00 s au lieu de 44,82 s
   (`entra.py:46-50`, `config.py:203-205`).

## Zones non vérifiées

- **Sur Azure** : la latence d'un échec de jeton (point 3), le coût de `check_connection` (point 4 : 200 appels,
  médiane, p95, maximum, gardé si p95 ≤ 20 ms) et la langue des messages de libpq. Les commandes, en lecture seule,
  sont écrites ; leurs résultats entrent dans la PR quand elles sont lancées.
- requests borne chaque tentative de connexion par adresse et chaque lecture, pas une durée totale. La borne de 5 s
  est mesurée en local pour un point d'identité muet.
- Les tests marqués `postgresql` se lisent dans la CI (job `tests-postgresql`).
- Le premier appel de `GET /health/database` après un réveil peut rendre 503 `database_unavailable` si le pool n'a
  pas sa connexion en 2 s. `kb smoke-test` l'appelle après l'API IA ; le cas d'une API IA déjà éveillée n'est pas
  mesuré.
- Le `kb smoke-test` du prochain tag appelle une route qui n'existe qu'avec la même image. `deploy.yml` pose la même
  version sur l'API et sur les jobs ; c'est à constater en ligne.

## Ce qui reste

- La cause d'un échec de connexion directe d'une commande `kb` : une issue de suite.
- La page 500 du site quand l'API de données est en panne, à rendre en 502 ou 503 nommé : une issue de suite.
- Un échec de `configure_reader` sur une connexion neuve du pool (son `SET`, son commit) n'a pas de ligne
  `database_connection_failed` : le point 2 visait l'ouverture.
- Un fichier SQLite vide répond 500 `database_error`, là où une base PostgreSQL sans tables répond 503
  `database_missing` : la route répond comme une route de données pour la même cause, comme sur `main`.
- L'amorçage et la routine quotidienne (#330), les migrations (#186), hors du périmètre de l'issue.
