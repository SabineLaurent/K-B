# Les tests de K-B

!!! note "Compétences de la certification"

    > Rédaction de documentation technique pour la configuration de l'environnement et pour l'exécution des tests.

    — C12

    > Rédaction de la documentation technique.

    — C17

Cette fiche dit comment installer l'environnement de test, quelles dépendances il installe, comment lancer les
tests et calculer leur couverture, puis donne le plan de tests de `POST /digests`. Elle est écrite d'après le code de
`main` au commit `852dad4` (2026-11-08), et le test de l'export des mesures d'après `main` au commit `fd956430`
(2026-11-18). Les chemins du code de K-B (`ai_api/…`, `core/…`) partent de `src/k_b/`, les autres de la racine du
dépôt.

## Installer l'environnement de test

### Prérequis

Python 3.13 ou plus récent (`requires-python = ">=3.13"`, `pyproject.toml`) et [uv](https://docs.astral.sh/uv/).
L'intégration continue (CI) installe uv 0.13.6 (`astral-sh/setup-uv`, `.github/workflows/ci.yml`).

### Installer

```sh
git clone https://github.com/SabineLaurent/K-B.git
cd K-B
uv sync
```

`uv sync` installe K-B, ses dépendances et le groupe `dev` du `pyproject.toml`, que uv installe par défaut
(documentation de uv, « <span lang="en">Default groups</span> », lue par Context7 le 2026-11-08). La CI lance
`uv sync --locked`: les versions de `uv.lock`, sans le mettre à jour.

### Sans `.env`

Aucun test ne lit de `.env`. Les cibles `make test*` lancent pytest sans `--env-file`
(`Makefile`). Avant chaque test, la fixture `no_kb_setting_of_the_terminal` (`tests/conftest.py`) retire les
réglages de `kb` qu'un terminal peut exporter (`KB_SETTINGS_VARIABLES`, dont `KB_DATABASE_URL` et
`KB_DEPLOYMENT_ENVIRONMENT`) et les variables que lit libpq (`LIBPQ_VARIABLES`): une variable de ces deux listes,
exportée par le terminal, ne change ni ce que les tests vérifient, ni la base où ils écrivent. Cette fixture ne
retire pas les autres variables d'un `.env` exporté; `tests/commands/conftest.py`, `tests/jobs/conftest.py` et
`tests/exchange/conftest.py` en retirent d'autres, pour leurs seuls tests.

### Pour les tests marqués `postgresql`

Un serveur PostgreSQL de test, nommé par `KB_TEST_POSTGRESQL_URL`. C'est
un serveur de la machine (sur le Mac, le PostgreSQL de Homebrew, sans conteneur) ou le service de la CI, jamais la
base de production. Son rôle doit pouvoir créer et supprimer une base (`make_postgresql_base`), et créer des rôles
pour les tests des droits de la base en ligne (`identity_roles`, `tests/conftest.py`). Une base de test est créée
par défaut en UTF8 et en collation C, comme `kb create-db` la demande (`create_postgresql_base`); un test peut en
demander d'autres réglages (`make_postgresql_base`). Dans la CI, le job
`tests-postgresql` démarre `postgres:18.6`, épinglé par son digest, sans mot de passe (`POSTGRES_HOST_AUTH_METHOD:
trust`, joignable du seul runner), avec `KB_TEST_POSTGRESQL_URL=postgresql://kb@127.0.0.1:5432/postgres`.

### Pour les tests de bout en bout

Pour les tests marqués `e2e`, copier `.env.e2e_test.example` en `.env.e2e_test` (ignoré par git, `.gitignore`) et
le remplir. Il ne porte que leurs variables:

| Variable | Sans elle |
|---|---|
| `KB_GITHUB_TOKEN` | les sources GitHub tournent à 60 requêtes par heure au lieu de 5 000 |
| `KB_ZOTERO_DIR` | le test de Zotero est sauté |
| `KB_VAULT_DIR` | le test des clips est sauté |
| `GOOGLE_APPLICATION_CREDENTIALS` | le test de `gh_archive` est sauté; avec elle, il lance une vraie requête BigQuery |
| `KB_OTLP_ENDPOINT`, `KB_OTLP_HEADERS` | le test de l'export des mesures est sauté |
| `KB_DEPLOYMENT_ENVIRONMENT` | avec `KB_OTLP_ENDPOINT` et `KB_OTLP_HEADERS`, le test de l'export échoue (`KB_DEPLOYMENT_ENVIRONMENT: not set, sandbox or production`); posée, elle lui parvient ([Le test de l'export des mesures](#le-test-de-lexport-des-mesures)); `sandbox` dans le modèle |

Ils se lancent depuis un terminal sans `.env` exporté. Si l'environnement porte une autre variable de
`.env.example` (hors de celles que le test pose lui-même, `KB_DATA_DIR` et `KB_COLLECT_ONLY`, et de celles que
`tests/conftest.py` retire), ou la clé d'un client de l'API de données (`KB_DATA_API_KEY_<CLIENT>`), la fixture
`no_variable_beyond_the_end_to_end_tests` (`tests/e2e/conftest.py`) arrête pytest avant tout `kb`, en citant leurs
noms, jamais leurs valeurs.

## Les dépendances installées

Les outils des tests sont le groupe `dev` du `pyproject.toml` (versions planchers dans le tableau suivant; versions exactes dans
`uv.lock`). L'image n'en installe aucun: ses deux `uv sync` portent l'option `--no-dev` (`Dockerfile`).

| Paquet | Version plancher | Rôle |
|---|---|---|
| `pytest` | 9.1.1 | lance les tests; les marqueurs `e2e` et `postgresql` sont déclarés par `tests/conftest.py` |
| `pytest-cov` | 7.1.0 | mesure la couverture (`--cov`) et fait échouer la commande sous le seuil |
| `pytest-html` | 4.2.0 | écrit le rapport HTML d'une exécution (`--html`) |
| `openapi-spec-validator` | 0.9.0 | valide l'OpenAPI de chaque API (`tests/data_api/test_openapi.py`, `tests/ai_api/test_ai_api_openapi.py`) |
| `ruff` | 0.16.10 | le lint et le format |
| `mypy` | 2.4.0 | le typage strict |
| `types-defusedxml`, `types-pyyaml` | 0.7.0.20260504, 6.0.12.20260906 | les annotations de `defusedxml` et de `pyyaml`, pour mypy |

Les tests se servent aussi de dépendances de K-B lui-même: le `TestClient` de FastAPI (une application appelée
sans socket), `uvicorn` (les deux API servies pour de vrai dans `tests/commands/test_live_apis.py`), le
`MockTransport` de `httpx2` (une réponse HTTP écrite par le test), `psycopg` (le serveur de test) et les exportateurs
en mémoire du SDK (le kit de développement, <span lang="en">software development kit</span>) d'OpenTelemetry (`tests/ai_api/conftest.py`).

## Lancer les tests

| Commande | Ce qu'elle lance |
|---|---|
| `uv run pytest` | toute la suite, sauf les tests marqués `e2e` et `postgresql`: `pytest_collection_modifyitems` les écarte tant que `-m` ne les nomme pas (`MARKERS_LEFT_OUT_BY_DEFAULT`, `tests/conftest.py`). Au commit `852dad4`: 4061 tests, 328 écartés |
| `uv run pytest tests/ai_api`, `uv run pytest -k <mot>` | une partie de la suite |
| `KB_TEST_POSTGRESQL_URL=postgresql://<rôle>@127.0.0.1:5432/postgres uv run pytest -m postgresql` | les tests marqués `postgresql` (317 au commit `852dad4`). Sans la variable, chacun échoue, il n'est jamais sauté (`postgresql_server_url`) |
| `uv run --env-file .env.e2e_test pytest -m e2e -rs --html=reports/e2e-report.html --self-contained-html` | les tests de bout en bout (11 au commit `852dad4`); `-rs` donne la raison de chaque test sauté, `-k <source>` n'en lance qu'un |
| `make test` | comme `uv run pytest`, avec le rapport `reports/test.html` |
| `make test-ai-api`, `make test-data-api` | `tests/ai_api` ou `tests/data_api`, puis les tests du code commun aux deux API (`API_COMMON_TESTS` du `Makefile`); rapports `reports/test-ai-api.html` ou `reports/test-data-api.html`, puis `reports/test-api-common.html` |
| `make test-etl` | `tests/etl`, rapport `reports/test-etl.html` |
| `uv run ruff check --no-cache`, `uv run ruff format --check`, `uv run mypy --strict` | le lint, le format et le typage. La CI lance `uv run ruff check` sans `--no-cache`; sur la machine, `--no-cache` est une précaution: `uv run ruff check` a déjà passé là où `uv run ruff check --no-cache` a trouvé trois imports non triés, cause non établie |

### Sur PostgreSQL

Un test qui écrit reçoit une base neuve, `kb_test_<hex>`, supprimée après les tests de son
module (`make_postgresql_base`); les tests de lecture partagent une base, construite une fois par session
(`items_postgresql_base`). Un test de lecture prend la fixture `engine`: sa moitié `[sqlite]` tourne dans
`uv run pytest`, sa moitié `[postgresql]` sous `-m postgresql` (`ENGINES`, `tests/conftest.py`).

### Les rapports

`restrict_report_to_user` (`tests/conftest.py`) crée le rapport de `--html` en `0600`, et son
dossier en `0700` s'il le crée, avant que pytest-html l'écrive: il garde la sortie capturée de chaque test. Un rapport demandé
dans le dépôt hors de `reports/`, que git ne laisserait pas de côté, arrête pytest. Chaque exécution écrase le
rapport précédent.

### Les tests de bout en bout

| Test | Ce qu'il fait |
|---|---|
| `test_kb_collects_and_imports_the_real_source` (`tests/e2e/test_real_sources.py`) | lance `kb` sur la vraie source, un test par source (paramétré par `SOURCE_KINDS`); pour les trois sources qui ont une variable (Zotero, clips, `gh_archive`), sauté sans elle; les autres ne sont jamais sautées |
| `test_the_measures_of_a_request_reach_the_otlp_endpoint` (`tests/e2e/test_real_export.py`) | envoie au vrai point OTLP (Grafana Cloud; OTLP, le protocole d'export d'OpenTelemetry) les mesures d'une demande à l'API IA sur le modèle rejoué, à l'arrêt de l'application; sauté sans `KB_OTLP_ENDPOINT` et `KB_OTLP_HEADERS` |
| les quatre tests du bac à sable des alertes (`tests/e2e/test_sandbox_alerts.py`) | envoient chacun un scénario au bac à sable, dont trois visent une alerte du monitorage du modèle: les mesures de demandes à l'API IA sur le modèle rejoué partent au vrai point OTLP, avec l'environnement `sandbox`; sautés sans `KB_OTLP_ENDPOINT` et `KB_OTLP_HEADERS` ([Le bac à sable des alertes](#le-bac-a-sable-des-alertes)) |

#### Le test de l'export des mesures

Le test lit les réglages de l'export dans `os.environ` (`tests/e2e/test_real_export.py:63`), dont
`KB_DEPLOYMENT_ENVIRONMENT`. La fixture `no_kb_setting_of_the_terminal` retire cette variable des autres tests, mais
la garde pour un test marqué `e2e` (`END_TO_END_SETTINGS`, `tests/conftest.py:50`, `:156-163`). Un réglage refusé
arrête le test avant toute demande (`tests/e2e/test_real_export.py:66`). Sinon, il ouvre l'API IA au client
`DIGEST_CLIENT` (`:82`), le seul client que `POST /digests` accepte (`core/config.py:349`), lui envoie une demande
(`tests/e2e/test_real_export.py:108-112`), et échoue si la réponse n'est pas 200, si aucun envoi de mesures n'a eu
lieu, ou si l'un d'eux n'a pas réussi (`:117-119`).

Il échouait avant la demande de fusion (PR, <span lang="en">pull request</span>) #527, fusionnée le 2026-11-09, qui
a fermé #495: la fixture lui retirait `KB_DEPLOYMENT_ENVIRONMENT` (constaté le 2026-11-08 au commit `852dad4`:
`KB_DEPLOYMENT_ENVIRONMENT: not set, sandbox or production`), et il ouvrait l'API IA au client `TERMINAL`, que
`POST /digests` refuse. Depuis, un test de la suite par défaut, donc de la CI, le lance dans un sous-processus avec
`KB_DEPLOYMENT_ENVIRONMENT=staging` et une adresse factice, et attend son refus nommé,
`KB_DEPLOYMENT_ENVIRONMENT: 'staging' not sandbox nor production`: la variable lui parvient, et il s'arrête avant
toute demande (`test_the_end_to_end_test_of_the_export_gets_the_environment_of_the_terminal`,
`tests/test_e2e_selection.py:175-193`).

Lancé par Sabine le 2026-11-09 sur `9534048`, avec les vraies valeurs de `.env.e2e_test`
(`uv run --env-file .env.e2e_test pytest -m e2e -k real_export -rs`), il a passé: `1 passed, 4422 deselected`
(commentaire de la PR #527). Ce qu'il ne prouve pas: le SDK d'OpenTelemetry compte une réponse 3xx comme un succès,
et les séries de cette exécution n'ont pas été lues dans Grafana Explore (`tests/e2e/test_real_export.py:7-8`;
commentaire de la PR #527). Il n'a pas été relancé sur `fd956430`: son fichier n'a pas changé depuis `9534048`
(`git log 9534048..fd956430 -- tests/e2e/test_real_export.py` ne rend rien), mais l'API IA qu'il sert, si
(`git diff --stat 9534048 fd956430 -- src/k_b/ai_api/`: 9 fichiers).

### Le bac à sable des alertes

Fusionné au commit `1d2f554` (PR #517, 2026-11-08). Il se lance à la main, hors de la CI, depuis un terminal où
le `.env` n'est pas chargé:

```sh
make sandbox-alerts
```

La cible lance les seuls tests de `tests/e2e/test_sandbox_alerts.py`, avec le `.env.e2e_test` de la copie de
travail principale du dépôt, et écrit le rapport `reports/sandbox-alerts.html` (`Makefile:3`, `:64-66`). Les deux
variables à y mettre sont `KB_OTLP_ENDPOINT` et `KB_OTLP_HEADERS`; sans elles, chaque test est sauté
(`read_sandbox_export_settings`). Chaque test pose lui-même `KB_DEPLOYMENT_ENVIRONMENT=sandbox` avant de lire ces
réglages, à la place de toute valeur du terminal (`tests/e2e/test_sandbox_alerts.py:96-98`).

Chaque test sert l'API de données sur la base de test et une API IA sur le modèle rejoué, avec des clés tirées au
hasard, puis envoie ses demandes à `POST /digests` (`run_sandbox_requests`). Il échoue si un envoi de mesures n'est
pas accepté, s'il y a eu moins d'envois que de demandes, ou si l'environnement n'est pas `sandbox`. Le tableau
suivant donne ce que vérifie chacun des quatre tests.

| Test | Ce qu'il vérifie |
|---|---|
| `test_valid_requests_spaced_beyond_an_export_reach_the_sandbox` | 3 demandes valides, espacées de plus d'un envoi de mesures, chacune en 200. Il ne vise aucune alerte: l'écart montre dans Grafana si `increase()` compte la première demande (`tests/e2e/test_sandbox_alerts.py:87-90`) |
| `test_an_invalid_output_reaches_the_sandbox` | un classement refusé deux fois: 502, et une ligne de mesure `llm_invalid_output` |
| `test_a_low_fidelity_reaches_the_sandbox` | 200, avec 3 faits trouvés sur 7, sous le seuil de l'alerte `KbModelLowFidelity` |
| `test_a_cost_over_the_budget_reaches_the_sandbox` | 200, avec un coût estimé au-dessus du seuil de l'alerte `KbModelCostOverBudget` |

Les seuils sont lus dans les règles d'alerte du dépôt (`read_alert_thresholds`, `tests/test_grafana_files.py`).
Les tests prouvent que chaque envoi est accepté et que les valeurs calculées sur la machine sont celles du
scénario, sous ou au-dessus du seuil pour la fidélité et le coût; le déclenchement d'une alerte se lit dans
Grafana, pas dans le test.
`uv run --env-file .env.e2e_test pytest -m e2e` lance aussi ces quatre tests: 15 tests de bout en bout au commit
`1d2f554`, dont les quatre du bac à sable. Ce que montrent les alertes, et le relevé du bac à sable lancé par
Sabine: [la fiche du monitorage](monitoring_pour_docu.md), sections « Le bac à sable » et « Relevé des alertes du
bac à sable ».

### Ce que lance la CI

Le workflow `CI` (`.github/workflows/ci.yml`) tourne sur chaque push sur `main` et chaque pull request vers `main`.
Chaque job installe l'environnement par `uv sync --locked`, puis lance la commande que donne le tableau suivant.

| Job | Commande |
|---|---|
| `tests` | `uv run pytest --cov --cov-report=term-missing:skip-covered`: la suite et sa couverture, sans `e2e` ni `postgresql` |
| `tests-postgresql` | `uv run pytest -m postgresql`, sur le service PostgreSQL 18 du job |
| `tests-data` | `uv run pytest tests/etl tests/test_schema.py tests/test_items.py tests/ai_api/test_watch_items.py`: les tests des données, à part; ils tournent aussi dans `tests` |
| `lint` | `uv run ruff check`, puis `uv run ruff format --check` |
| `types` | `uv run mypy --strict` |
| `audit` | `uvx pip-audit@2.10.1` sur les versions de `uv.lock`, avec leurs empreintes |

Les tests `e2e` ne tournent jamais dans la CI: ils appellent de vraies sources et un vrai service.

## Calculer la couverture

```sh
make test-cov                                   # les fichiers sous 100 % dans la console, le tableau complet dans reports/coverage.md
uv run pytest --cov --cov-report=term-missing   # tous les fichiers dans la console, sans rapport écrit
```

Les réglages sont dans `pyproject.toml`:

| Réglage | Valeur | Effet |
|---|---|---|
| `[tool.coverage.run] source` | `["k_b"]` | mesure le code de `src/k_b/` |
| `branch` | `true` | compte aussi les branches jamais prises d'un `if` |
| `patch` | `["subprocess"]` | mesure aussi les sous-processus que lancent des tests (pytest-cov 7 ne le fait plus) |
| `[tool.coverage.report] fail_under` | `96` | sous 96 %, lignes et branches, la commande échoue: un plancher contre la régression, pas une cible (journal des décisions d'architecture, ou ADR, 2026-11-08) |
| `precision` | `2` | le total est arrondi à deux décimales avant d'être comparé au seuil |

Seules les commandes avec `--cov` vérifient le seuil (`make test` et `uv run pytest`, non). Sur une partie de la
suite, ajouter `--cov-fail-under=0`. La CI vérifie le seuil dans le job `tests`; `tests-postgresql` ne mesure pas
la couverture. Mesure du 2026-11-08 (18:41 UTC) au commit `852dad4`, par la commande du job `tests`: 4061 réussis,
328 écartés, couverture totale 98,42 %.

## Plan de tests de `POST /digests`

`POST /digests` rend les fiches de veille d'une fenêtre: l'API IA lit les items par l'API de données, les classe par
sujet, puis rédige chaque sujet. Son contrat est
[la spécification des comptes rendus de veille](https://github.com/SabineLaurent/K-B/blob/main/docs/fiches-veille.md).
Les sections suivantes du plan disent, composante par composante, les cas testés, le type de test, la stratégie et le
fichier. Les tests de `POST /trend-reports` sont listés dans
[la section « Ce qui le prouve » de la spécification du compte rendu des tendances](https://github.com/SabineLaurent/K-B/blob/main/docs/tendances.md#ce-qui-le-prouve).
Le compte rendu de leur exécution et ce qu'ils ne prouvent pas sont dans
[le compte rendu des tests de l'API IA du 2026-11-08, relancé le 2026-11-18](https://github.com/SabineLaurent/K-B/blob/main/docs/2026-11-08-tests-api-ia.md).

### Types de test

| Type | Ce qu'il exécute |
|---|---|
| unitaire | une fonction ou un module seul, sans application ni réseau |
| intégration | plusieurs parties réelles ensemble, sans socket: la vraie application de l'API IA appelée par le `TestClient` de FastAPI; ou les étapes de l'API IA (`build_digests`, `read_watch`) sur la vraie API de données de la base de test et le modèle rejoué |
| bout en bout, dans la CI | `kb digest`, puis les deux API servies par uvicorn sur `127.0.0.1`, puis la base de test (`tests/commands/test_live_apis.py`) |
| `postgresql` | le même test sur un serveur PostgreSQL (job `tests-postgresql`) |
| `e2e` | un vrai service extérieur, hors de la CI |

### Stratégies

| Stratégie | Ce qu'elle remplace | Où |
|---|---|---|
| modèle rejoué | le fournisseur du modèle: des réponses écrites d'avance, données dans l'ordre par le transport du client HTTP; l'appel tourne en entier, sans réseau, sans clé et sans coût | `ReplayTransport` (`ai_api/connectors/llm_replay.py`); sous `KB_LLM_PROVIDER=replay`, les réponses viennent du fichier de `KB_LLM_REPLAY_FILE` |
| base de test | la base de K-B: un fichier SQLite construit une fois par session à partir de `tests/fixtures/items_database.sql`, en lecture seule; la même sur PostgreSQL | `items_database`, `items_postgresql_base` (`tests/conftest.py`) |
| vraie API de données | l'API de données en ligne: sa vraie application sur la base de test, appelée par le `TestClient` | fixture `data_api` (`tests/ai_api/test_digest_router.py`, `tests/ai_api/test_data_api_client.py`) |
| faux transport | une réponse que la base de test ne peut pas donner (401, 429, délai dépassé, corps hors schéma ou trop gros) | `httpx2.MockTransport` |
| mesures et traces en mémoire | l'export vers Grafana Cloud | `InMemoryMetricReader`, `InMemorySpanExporter`, `InMemoryLogRecordExporter` (`tests/ai_api/conftest.py`, `tests/ai_api/test_digest_router.py`) |

Aucun test de la CI n'appelle le modèle, GitHub ni Grafana Cloud.

### 1. Données lues par l'API de données

Intégration (vraie API de données sur la base de test, faux transport): `tests/ai_api/test_data_api_client.py`.
`postgresql`: la route `GET /items` sur les deux moteurs, `tests/data_api/test_item_router.py`. Le tableau suivant
donne chaque cas, ses tests et leur fichier.

| Cas | Test | Fichier |
|---|---|---|
| les items des cinq sortes de la liste blanche, dans l'ordre de la spec | `test_the_reading_gives_the_items_of_the_whitelist_in_the_order_of_the_spec` | `tests/ai_api/test_data_api_client.py` |
| un clip n'est jamais lu pour la veille | `test_a_clip_is_of_the_library_and_never_read_for_the_watch` | `tests/ai_api/test_data_api_client.py` |
| la lecture suit les pages | `test_the_reading_follows_the_pages` | `tests/ai_api/test_data_api_client.py` |
| un item disparu ou retiré entre la liste et le détail est sauté et compté | `test_an_item_gone_between_the_list_and_the_detail_is_skipped_and_counted`, `test_an_item_withdrawn_between_the_list_and_the_detail_is_skipped_and_counted` | `tests/ai_api/test_data_api_client.py` |
| une clé refusée par l'API de données | `test_a_key_refused_gives_data_api_unauthorized` | `tests/ai_api/test_data_api_client.py` |
| une réponse hors schéma, ou d'une autre sorte que celle demandée | `test_a_list_out_of_its_schema_gives_data_api_invalid_response`, `test_a_kind_other_than_the_one_asked_gives_data_api_invalid_response` | `tests/ai_api/test_data_api_client.py` |
| un corps au-delà de la borne, lu ou annoncé | `test_a_list_above_the_bound_gives_data_api_invalid_response`, `test_a_content_length_above_the_bound_is_refused_before_reading` | `tests/ai_api/test_data_api_client.py` |
| l'échéance de la demande arrête la lecture | `test_a_deadline_passed_stops_the_reading_before_any_request`, `test_a_deadline_passed_while_an_answer_is_read_stops_the_reading` | `tests/ai_api/test_data_api_client.py` |
| l'erreur ne porte ni la clé ni ce qui a été reçu | `test_the_error_carries_neither_the_key_nor_what_was_received` | `tests/ai_api/test_data_api_client.py` |
| une lecture en échec fait échouer la demande sans appeler le modèle | `test_a_reading_that_fails_fails_the_request_without_a_call_to_the_model` | `tests/ai_api/test_digest_router.py` |
| les filtres de `GET /items` (`kind`, `since`, `q`, `limit`, `offset`) sur SQLite et sur PostgreSQL | `test_kind_since_q_limit_offset_filter_as_the_reading` | `tests/data_api/test_item_router.py` |

### 2. Préparation de l'entrée du modèle: coupe et plafond

Unitaire: `tests/ai_api/test_watch_items.py`, `tests/ai_api/test_stages.py`. Intégration:
`tests/ai_api/test_data_api_client.py` (vraie API de données sur la base de test, faux transport);
`tests/ai_api/test_digests.py` (modèle rejoué, base de test). Les bornes sont dans
`core/config.py`: `MAX_ITEMS_PER_DIGEST_REQUEST = 300`, `MAX_ITEMS_PER_DIGEST = 60`,
`MAX_FIELD_CHARS_FOR_WRITING = 2000`, `MAX_ITEMS_PER_CLASSIFICATION_CALL = 45`,
`MAX_CLASSIFICATION_INPUT_CHARS = 36_000`, `MAX_FIELD_CHARS_FOR_CLASSIFICATION = 500`. Le tableau suivant donne
chaque cas, ses tests et leur fichier.

| Cas | Test | Fichier |
|---|---|---|
| le plafond de lecture, dans une sorte et entre deux sortes | `test_the_reading_is_capped_inside_a_kind`, `test_the_reading_capped_between_two_kinds_names_the_next_one` | `tests/ai_api/test_data_api_client.py` |
| une entrée retirée ne prend pas de place sous le plafond | `test_a_withdrawn_entry_takes_no_place_under_the_cap` | `tests/ai_api/test_data_api_client.py` |
| seuls les champs de la liste blanche partent, adresses web et logins des notes d'une release masqués | `test_the_fields_out_of_the_whitelist_are_not_kept`, `test_every_url_of_a_field_sent_is_masked`, `test_a_login_of_a_release_body_is_masked` | `tests/ai_api/test_watch_items.py` |
| la rédaction garde les items les plus récents, coupe chaque champ, et compte ce qu'elle laisse | `test_the_writing_keeps_the_most_recent_items_and_counts_the_others`, `test_the_writing_cuts_each_field_and_counts_the_items_cut` | `tests/ai_api/test_watch_items.py` |
| les items au-delà du plafond d'une fiche sont écartés et comptés | `test_the_items_beyond_the_digest_cap_are_dropped_and_counted` | `tests/ai_api/test_digests.py` |
| le classement envoie le titre et le texte long coupé, par lots bornés en items et en caractères | `test_the_classification_sends_the_title_and_the_long_text_cut`, `test_a_batch_holds_the_maximum_of_items_at_most`, `test_a_batch_holds_the_maximum_of_characters_at_most` | `tests/ai_api/test_stages.py` |
| une fenêtre vide n'appelle pas le modèle | `test_an_empty_window_calls_no_model`, `test_an_empty_window_answers_without_calling_the_model` | `tests/ai_api/test_digests.py`, `tests/ai_api/test_digest_router.py` |

### 3. Consigne

Unitaire: `tests/ai_api/test_stages.py` (fonctions seules), `tests/ai_api/test_llm_client.py` (modèle rejoué).
Intégration: `tests/ai_api/test_digests.py` (modèle rejoué, base de test). Le tableau suivant donne chaque cas, ses
tests et leur fichier.

| Cas | Test | Fichier |
|---|---|---|
| les items vont dans le message utilisateur, jamais dans un message `system` | `test_the_items_go_in_the_user_message_never_in_a_system_message` | `tests/ai_api/test_digests.py` |
| un item piégé reste dans le message utilisateur, et sa sortie n'est jamais rendue | `test_a_trapped_item_stays_in_the_user_message_and_its_output_is_never_returned` | `tests/ai_api/test_llm_client.py` |
| un modèle qui obéit à un item piégé donne un état nommé, sans fiche | `test_a_model_obeying_a_trapped_item_gives_a_named_state_and_no_digest` | `tests/ai_api/test_digests.py` |
| chaque consigne dit que le message utilisateur est une donnée | `test_each_system_prompt_says_the_user_message_is_data` | `tests/ai_api/test_stages.py` |
| la consigne de rédaction dit les bornes que le code vérifie | `test_the_writing_prompt_states_the_bounds_the_code_checks` | `tests/ai_api/test_stages.py` |
| un rappel par contrôle refusé; la seconde demande ajoute le rappel, jamais la sortie refusée | `test_each_stage_gives_a_reminder_per_failed_check`, `test_the_second_request_adds_the_reminder_of_the_refused_check_never_the_output` | `tests/ai_api/test_stages.py`, `tests/ai_api/test_llm_client.py` |
| la demande est un *<span lang="en">chat completion</span>* avec un schéma JSON strict, portable et dans les bornes du mode strict | `test_the_request_is_a_chat_completion_with_a_strict_json_schema_written_as_a_dict`, `test_the_schema_sent_is_portable`, `test_the_schema_of_a_full_batch_is_within_the_bounds_of_strict_mode` | `tests/ai_api/test_llm_client.py`, `tests/ai_api/test_stages.py` |
| chaque appel porte la version de sa consigne | `test_the_stage_calls_carry_their_prompt_version_and_counts` | `tests/ai_api/test_digests.py` |

### 4. Contrôles 1 à 6

Les six contrôles de chaque sortie du modèle (`docs/fiches-veille.md`, « Contrôles »). Unitaire:
`tests/ai_api/test_stages.py` (fonctions seules), `tests/ai_api/test_llm_client.py` (modèle rejoué). Intégration:
`tests/ai_api/test_digests.py` (modèle rejoué, base de test). Le tableau suivant donne, pour chaque contrôle, ses
cas, leurs tests et leurs fichiers.

| Contrôle | Cas | Test | Fichier |
|---|---|---|---|
| 1. `finish_reason` | `length`, `content_filter`, une valeur inconnue, `null` | `test_a_truncated_output_is_llm_truncated_without_retry`, `test_a_filtered_output_is_llm_content_filtered_without_retry`, `test_an_unknown_finish_reason_is_asked_again`, `test_a_finish_reason_null_is_refused_by_check_1_and_asked_again` | `tests/ai_api/test_llm_client.py` |
| 2. schéma | une sortie hors modèle, une clé deux fois, un item répondu deux fois au classement, trop d'affirmations, une affirmation qui cite 0 ou plus de 5 items | `test_an_output_out_of_its_model_fails_the_schema_check`, `test_only_json_without_a_key_twice_is_read`, `test_an_item_answered_twice_at_the_classification_is_llm_invalid_output`, `test_more_claims_than_the_structure_allows_is_a_schema_failure`, `test_a_claim_citing_no_item_or_more_than_five_is_a_schema_failure` | `tests/ai_api/test_llm_client.py`, `tests/ai_api/test_digests.py` |
| 3. sujets | un sujet hors de la liste | `test_a_subject_out_of_the_list_is_refused` | `tests/ai_api/test_digests.py` |
| 4. `item_id` | un identifiant inconnu au classement et à la rédaction, un item d'un autre lot, un fait d'un item que son affirmation ne cite pas | `test_an_unknown_item_id_is_refused_at_the_classification`, `test_an_unknown_item_id_is_refused_at_the_writing_and_the_others_are_returned`, `test_an_item_of_another_batch_is_refused`, `test_a_fact_of_an_item_its_claim_does_not_cite_is_refused` | `tests/ai_api/test_digests.py` |
| 5. complétude | une réponse à aucun item, un item sans réponse | `test_an_answer_to_no_item_is_asked_again_then_fails_the_request`, `test_an_item_without_answer_is_counted_apart_without_failure` | `tests/ai_api/test_digests.py` |
| 6. Markdown | un lien, une image ou une balise; un texte simple; le rappel après un refus | `test_a_text_with_a_link_an_image_or_a_tag_is_refused`, `test_a_plain_text_passes_the_check_of_markup`, `test_the_retry_after_a_markup_sends_its_reminder` | `tests/ai_api/test_stages.py`, `tests/ai_api/test_digests.py` |
| ordre et nouvelle tentative | les contrôles dans leur ordre; une sortie refusée deux fois | `test_the_checks_of_the_writing_go_in_their_order`, `test_an_output_refused_twice_is_llm_invalid_output` | `tests/ai_api/test_digests.py`, `tests/ai_api/test_llm_client.py` |

L'appel lui-même a aussi un test par état nommé (`tests/ai_api/test_llm_client.py`), par exemple
`test_a_rate_limit_twice_is_llm_rate_limited_after_waiting_retry_after`, `test_a_provider_down_twice_is_llm_unavailable`
et `test_a_timeout_is_llm_timeout_without_retry`.

### 5. Fidélité

Une fiche ne dit que ce que disent ses items (`docs/fiches-veille.md`, « Fidélité »). Unitaire:
`tests/ai_api/test_fidelity.py`. Intégration (modèle rejoué, base de test): `tests/ai_api/test_digests.py`. Le
tableau suivant donne chaque cas, ses tests et leur fichier.

| Cas | Test | Fichier |
|---|---|---|
| le texte est normalisé avant toute recherche | `test_a_text_is_normalized_before_any_search` | `tests/ai_api/test_fidelity.py` |
| une valeur n'est trouvée qu'entre ses limites, dans un seul champ | `test_a_value_is_found_only_between_its_limits`, `test_a_fact_is_found_in_one_field_never_across_two` | `tests/ai_api/test_fidelity.py` |
| une CVE (<span lang="en">Common Vulnerabilities and Exposures</span>, l'identifiant public d'une vulnérabilité) du texte égale à son fait par sa forme canonique | `test_a_cve_of_the_text_equals_its_fact_by_its_canonical_form` | `tests/ai_api/test_fidelity.py` |
| un identifiant du texte non déclaré en fait retire l'affirmation | `test_an_identifier_of_the_text_not_declared_removes_the_claim` | `tests/ai_api/test_fidelity.py` |
| le piège écrit en clair, puis déguisé, est retiré | `test_the_trap_written_plainly_is_removed`, `test_the_trap_disguised_is_removed` | `tests/ai_api/test_fidelity.py` |
| un contrôle de direction en tête du texte retire l'affirmation | `test_a_control_of_direction_at_the_start_of_the_text_removes_the_claim` | `tests/ai_api/test_fidelity.py` |
| un masque posé par K-B n'est jamais un fait | `test_a_mask_of_k_b_is_never_a_fact` | `tests/ai_api/test_fidelity.py` |
| dans une demande: un fait introuvable dans l'item cité retire son affirmation, la fiche reste rendue | `test_a_fact_not_found_in_the_item_it_cites_removes_its_claim`, `test_the_trapped_claim_on_a_cve_is_removed_and_the_digest_returned` | `tests/ai_api/test_digests.py` |
| un fait trouvé seulement dans ce qui n'est pas envoyé au modèle n'est pas trouvé | `test_a_fact_found_only_in_what_is_not_sent_is_not_found` | `tests/ai_api/test_digests.py` |

### 6. Routes

Intégration: la vraie application de l'API IA (`create_app`), le `TestClient`, la vraie API de données sur la base
de test et le modèle rejoué, `tests/ai_api/test_digest_router.py`; les étapes (`build_digests`, sans route, modèle
rejoué, base de test), `tests/ai_api/test_digests.py`; l'OpenAPI, `tests/ai_api/test_ai_api_openapi.py`. Bout en
bout, dans la CI: `tests/commands/test_live_apis.py`. Le tableau suivant donne chaque cas, ses tests et leur
fichier.

| Cas | Test | Fichier |
|---|---|---|
| une demande rend une fiche par sujet, avec sa fenêtre et son identifiant | `test_a_request_gives_a_digest_per_subject_with_its_window_and_its_id` | `tests/ai_api/test_digest_router.py` |
| sans fenêtre, celle des réglages | `test_a_request_without_window_takes_the_window_of_the_settings` | `tests/ai_api/test_digest_router.py` |
| une demande mal formée: 422 avant tout appel | `test_a_malformed_request_is_refused_422_before_any_call` | `tests/ai_api/test_digest_router.py` |
| un corps au-delà de la borne: 413 avant la clé; à la borne, lu | `test_a_body_beyond_the_bound_is_refused_413_before_the_key`, `test_a_body_at_the_bound_is_read` | `tests/ai_api/test_digest_router.py` |
| un classement en échec fait échouer la demande; une rédaction en échec nomme son sujet et rend les autres | `test_a_classification_that_fails_fails_the_request_with_its_lines`, `test_a_writing_that_fails_names_its_subject_and_the_others_are_returned` | `tests/ai_api/test_digest_router.py` |
| chaque état qui fait échouer une demande a son statut HTTP | `test_each_state_that_fails_a_request_has_its_status` | `tests/ai_api/test_digest_router.py` |
| chaque route ne répond qu'à sa méthode; une barre finale est une route inconnue | `test_every_route_answers_its_method_only_and_405_to_any_other`, `test_a_final_slash_is_an_unknown_route` | `tests/ai_api/test_digest_router.py` |
| l'échéance de la demande (200 s pour la route, `DIGEST_REQUEST_TIMEOUT_SECONDS`; une échéance d'essai dans ces tests): chaque appel l'attend au plus, un sujet non rédigé à temps est `llm_timeout` | `test_every_call_of_the_request_waits_no_longer_than_its_deadline`, `test_the_subjects_not_written_by_the_deadline_are_llm_timeout` | `tests/ai_api/test_digests.py` |
| l'OpenAPI versionnée est celle que produit l'application, et documente chaque état nommé | `test_the_versioned_openapi_is_the_one_the_app_produces`, `test_the_route_documents_each_named_state` | `tests/ai_api/test_ai_api_openapi.py` |
| `kb digest` écrit les fiches par les deux API servies pour de vrai | `test_digest_writes_the_sheets_through_the_ai_api_and_the_data_api` | `tests/commands/test_live_apis.py` |

### 7. Accès

Intégration: `tests/ai_api/test_digest_router.py`; le démarrage de `kb serve-ai`, `tests/ai_api/test_serve_ai.py`
(les tests cités: `cli.main`, `uvicorn.run` remplacé, il ne tourne pas);
la fenêtre de la limite de débit, code commun aux deux API, en unitaire sur une horloge réglée par le test,
`tests/test_api_rate_limit.py`. Le tableau suivant donne chaque cas, ses tests et leur fichier.

| Cas | Test | Fichier |
|---|---|---|
| sans clé valide, refusée avant toute lecture | `test_a_request_without_a_valid_key_is_refused_before_any_reading` | `tests/ai_api/test_digest_router.py` |
| seules les routes publiques, dont `/health`, répondent sans clé | `test_health_answers_without_key`, `test_only_the_public_routes_answer_without_a_key` | `tests/ai_api/test_digest_router.py` |
| un client refusé en 403 sur une route qui n'est pas la sienne; une route absente de la table des droits refusée à tous | `test_a_client_is_refused_403_on_a_route_that_is_not_its_own`, `test_the_client_of_the_digests_is_refused_on_the_trend_reports`, `test_a_route_absent_from_the_table_is_refused_to_every_client` | `tests/ai_api/test_digest_router.py` |
| la limite de débit: 429 avant toute lecture, une demande sans clé valide ne la consomme pas | `test_every_route_of_the_model_has_its_limit`, `test_beyond_its_limit_a_client_gets_429_before_any_reading`, `test_a_request_without_a_valid_key_consumes_no_call_of_the_limit` | `tests/ai_api/test_digest_router.py` |
| une demande à la fois par route: la suivante reçoit 429, sans file | `test_while_a_request_runs_the_next_one_on_its_route_gets_429_without_a_queue`, `test_the_route_is_free_again_after_a_response` | `tests/ai_api/test_digest_router.py` |
| la fenêtre glissante, un compte par client et par route | `test_the_window_slides_a_call_at_its_end_is_gone`, `test_each_client_and_each_route_has_its_own_count` | `tests/test_api_rate_limit.py` |
| au démarrage: un client qui a la clé envoyée à l'API de données arrête `kb serve-ai`; aucune clé au journal | `test_serve_ai_exits_2_when_a_client_has_the_key_it_sends_to_the_data_api`, `test_serve_ai_logs_its_clients_its_provider_and_its_model_never_a_key` | `tests/ai_api/test_serve_ai.py` |

### 8. Métriques et traces

Intégration, mesures et traces en mémoire: `tests/ai_api/test_digest_router.py`. Unitaire: `tests/ai_api/test_tracing.py`,
`tests/ai_api/test_metrics_export.py`, `tests/ai_api/test_trace_export.py` (sans réseau, sauf une socket locale).
`e2e`, hors de la CI: `tests/e2e/test_real_export.py` ([Le test de l'export des mesures](#le-test-de-lexport-des-mesures)).
Le tableau suivant donne chaque cas, ses tests et leur fichier.

| Cas | Test | Fichier |
|---|---|---|
| chaque appel écrit une ligne JSON sur la sortie standard, sans texte | `test_each_call_writes_one_json_line_on_stdout_without_a_text` | `tests/ai_api/test_digest_router.py` |
| le coût, et le taux de fidélité | `test_the_cost_is_the_tokens_at_the_prices_of_the_config`, `test_the_fidelity_rate_is_the_facts_found_over_the_facts_checked` | `tests/ai_api/test_digest_router.py` |
| les mêmes mesures en OpenTelemetry, à attributs fermés | `test_each_call_is_measured_in_opentelemetry_as_on_its_line`, `test_a_measure_carries_closed_attributes_never_a_text` | `tests/ai_api/test_digest_router.py` |
| une demande est une trace de ses étapes, sans texte des items ni de la sortie | `test_a_request_is_a_trace_of_its_steps`, `test_no_value_holds_a_text_of_the_items_or_of_the_output` | `tests/ai_api/test_digest_router.py` |
| avec le contenu `all` (ce que pose `KB_TRACE_CONTENT=all`), le contenu n'est que dans le corps d'un enregistrement | `test_with_content_all_only_the_body_of_a_content_record_holds_a_text` | `tests/ai_api/test_digest_router.py` |
| chaque affirmation retirée est une évaluation liée à sa dernière requête | `test_each_claim_removed_is_an_evaluation_tied_to_its_last_request` | `tests/ai_api/test_digest_router.py` |
| à l'arrêt de l'application, mesures, spans et journaux partent | `test_the_measures_the_spans_and_the_logs_are_sent_at_once_when_the_app_stops`, `test_stop_sends_the_measures_not_sent_yet` | `tests/ai_api/test_digest_router.py`, `tests/ai_api/test_metrics_export.py` |
| un réglage de l'export refusé est nommé sans ses en-têtes; une variable `OTEL_*` est refusée; `all` en production est refusé | `test_a_setting_of_the_export_refused_is_named_without_its_headers`, `test_any_variable_of_opentelemetry_is_refused_by_its_name_only`, `test_the_content_of_the_requests_all_in_production_quotes_no_value` | `tests/ai_api/test_metrics_export.py` |
| un arrêt contre un point qui ne répond jamais est borné | `test_a_stop_against_an_endpoint_that_never_answers_is_bounded_and_quotes_nothing` | `tests/ai_api/test_trace_export.py` |

## Ce qui reste hors de la CI

| Ce qui n'est pas testé dans la CI | Où c'est porté |
|---|---|
| le vrai modèle: aucun test de la CI ne l'appelle, toutes les sorties sont rejouées | #210 (essai des fiches sur la veille réelle avec gpt-6-luna), ouverte |
| le juge de chaque affirmation, et son étalonnage | #223 et #224, ouvertes |
| les vraies sources et l'envoi réel des mesures | les tests `e2e`, lancés à la main ([Les tests de bout en bout](#les-tests-de-bout-en-bout)); celui de l'export a passé le 2026-11-09, et n'a pas été relancé sur `fd956430` ([Le test de l'export des mesures](#le-test-de-lexport-des-mesures)) |
| le déclenchement des alertes du monitorage du modèle | le bac à sable, `make sandbox-alerts`, lancé à la main ([Le bac à sable des alertes](#le-bac-a-sable-des-alertes)) |

Ce que les tests de l'API IA ne prouvent pas d'autre (le transport réseau hors du bout en bout, les dépendances de
production qu'ils remplacent, la limite de débit sous une vraie charge) est dans
[le compte rendu des tests de l'API IA du 2026-11-08, relancé le 2026-11-18](https://github.com/SabineLaurent/K-B/blob/main/docs/2026-11-08-tests-api-ia.md).
