# L'installation et l'environnement de développement de K-B

« Rédaction de documentation technique pour la configuration de l'environnement et pour l'exécution des tests. » — C12

« Rédaction de la documentation technique. » — C17

Cette fiche dit comment installer l'environnement de développement de K-B sur une machine, le configurer, quelles
dépendances il installe, puis comment y ajouter l'environnement de test, dont le détail est dans
[la fiche des tests](tests_pour_docu.md). Elle est écrite d'après le code de `main` au commit `875c638` (2026-11-08).
Les chemins du code de K-B (`commands/…`, `core/…`, `database/…`) partent de `src/k_b/`, les autres de la racine du
dépôt.

## Prérequis

| Outil | Ce qu'il fait | Où sa version est fixée |
|---|---|---|
| git | clone le dépôt | — |
| [uv](https://docs.astral.sh/uv/) | installe Python, l'environnement virtuel et les dépendances, et lance `kb` | la CI installe uv 0.13.6 (`astral-sh/setup-uv`, `.github/workflows/ci.yml`), le `Dockerfile` prend l'image `ghcr.io/astral-sh/uv:0.13.6`, et `build-system.requires` du `pyproject.toml` demande `uv_build>=0.13.6,<0.14.0` |
| Python 3.13 | fait tourner K-B | `requires-python = ">=3.13"` (`pyproject.toml`); `.python-version` donne `3.13`, la version que uv prend pour créer l'environnement. S'il ne la trouve pas sur la machine, uv la télécharge (documentation de uv, « Automatic Python downloads », lue par Context7 le 2026-11-08) |

Facultatifs, chacun pour ce qui le demande:

| Outil | Ce qui le demande |
|---|---|
| PostgreSQL | une base PostgreSQL au lieu du fichier SQLite (`KB_DATABASE_URL`), et les tests marqués `postgresql` (« L'environnement de test », plus bas). Sans lui, K-B tourne sur SQLite, par le module `sqlite3` de Python |
| make | les cibles du `Makefile` (`make test`, `make serve-data`…), qui lancent `uv run` |
| Docker, avec buildx | la construction de l'image (`docker buildx build --platform linux/amd64 --tag k-b .`, `Dockerfile`) |
| l'outil `sqlite3` | la lecture de la base sans l'API (`sqlite3 -readonly <KB_DATA_DIR>/k-b.sqlite`) |

## Installer l'environnement de développement

```sh
git clone https://github.com/SabineLaurent/K-B.git
cd K-B
uv sync
uv run kb --help
```

- `uv sync` crée l'environnement virtuel `.venv` à la racine du dépôt (ignoré par git, `.gitignore`). Il y installe
  K-B en mode éditable (`source = { editable = "." }` dans `uv.lock`: une modification de `src/` se voit sans
  réinstaller), ses dépendances et le groupe `dev` du `pyproject.toml`, aux versions de `uv.lock` (documentation de
  uv, « Syncing the environment » et « Default groups », lue par Context7 le 2026-11-08).
- `uv sync --locked`, la commande de la CI, n'écrit jamais `uv.lock`: si `uv.lock` ne correspond plus au
  `pyproject.toml`, elle échoue au lieu de le mettre à jour. `uv lock --check` fait le même contrôle sans rien
  installer (documentation de uv 0.13.5, la dernière que donne Context7, « Automatic lock and sync » et « Checking
  the lockfile », lue le 2026-11-09; `.github/workflows/ci.yml`). Lancé le 2026-11-08 au commit `875c638`,
  `uv lock --check` a répondu `Resolved 96 packages` et est sorti en code 0.
- `uv run <commande>` met l'environnement à jour avant de lancer la commande (documentation de uv, « Automatic lock
  and sync »): après un `git pull` qui change `uv.lock`, `uv run kb …` installe d'abord les nouvelles versions.
- `uv run kb --help` contrôle l'installation. Il liste les 13 commandes de `kb` et leurs codes de sortie, sans lire
  l'environnement: `main` lit la ligne de commande (`read_command`) avant l'environnement (`read_environment`,
  `cli.py`). `kb` est le point d'entrée que déclare `[project.scripts]` (`kb = "k_b.cli:main"`, `pyproject.toml`).

## Configurer

### Le dossier de données et la base

`KB_DATA_DIR` nomme le dossier des données, hors du dépôt. Toutes les commandes le lisent, sauf `kb openapi`
(`main`, `cli.py`). **`kb` ne crée pas ce dossier** (#356, encore ouverte le 2026-11-09): s'il n'existe pas, la
commande s'arrête en code 2, avant tout travail, sur `error: KB_DATA_DIR is not an existing directory`
(`read_data_dir`, `commands/environment.py`). Il se crée donc à la main, puis la base, une fois:

```sh
mkdir -p ~/.knowledge_base
KB_DATA_DIR=~/.knowledge_base uv run kb create-db
```

`kb create-db` affiche `database created: <KB_DATA_DIR>/k-b.sqlite` et sort en code 0. Sans `KB_DATABASE_URL`, la
base est ce fichier SQLite; avec elle, `kb create-db` crée les tables dans la base PostgreSQL de l'URL, qui doit déjà
exister, en UTF8 et en collation C ([docs/stockage.md](../docs/stockage.md), « Le SGBD »).

Chaque commande écrit aussi son journal dans `<KB_DATA_DIR>/logs/`: `kb.log`, ou `kb-serve-data.log` et
`kb-serve-ai.log` pour les deux API (`core/config.py`). Deux exceptions n'écrivent aucun journal: `kb openapi`, et
`--dry-run` de `kb daily-routine` et `kb digest-watch`, qui affiche les étapes sans en lancer aucune (`main`,
`cli.py`). Avec `KB_LOG_TO_FILE=false`, le journal ne va que sur la
sortie d'erreur.

### Le fichier `.env`

```sh
cp .env.example .env
```

- `.env.example` est le modèle: il nomme et décrit chaque variable, sans valeur réelle. `.env` est ignoré par git
  (`.gitignore` ignore `.env` et `.env.*`, sauf les deux modèles `.env.example` et `.env.e2e_test.example`).
- `kb` ne charge jamais un `.env` lui-même: il lit l'environnement du processus, une fois, au démarrage
  (`read_environment`, `commands/environment.py`, appelée par `cli.py`). Le `.env` se donne à uv:
  `uv run --env-file .env kb collect`.
- Les cibles du `Makefile` qui lancent une commande `kb` (`make collect`, `make serve-data`…) lui donnent le `.env`
  du dépôt principal, que ses worktrees partagent (`ENV_FILE`, `Makefile`). `make test`, `make test-ai-api`,
  `make test-data-api`, `make test-etl` et `make test-cov` n'en donnent aucun; `make sandbox-alerts` donne le
  `.env.e2e_test` du dépôt principal (`E2E_ENV_FILE`).
- Une clé d'API se fabrique par
  `uv run python -c "import secrets; print(secrets.token_urlsafe(32))"`: une clé de moins de 32 caractères est
  refusée (`MIN_API_KEY_LENGTH`, `core/config.py`).

### Les variables d'environnement

Le rôle et la forme de chaque variable sont dans `.env.example`. Ce tableau dit qui la lit, et si elle est
obligatoire. `kb daily-routine` et `kb digest-watch` lisent en plus les variables des commandes qu'ils enchaînent;
avec `--dry-run`, ils ne lisent que `KB_DATA_DIR` et `KB_LOG_TO_FILE` (`main`, `cli.py`).

| Variable | Lue par | Obligatoire |
|---|---|---|
| `KB_DATA_DIR` | toutes les commandes, sauf `kb openapi` | oui |
| `KB_LOG_TO_FILE` | toutes les commandes, sauf `kb openapi` | non |
| `KB_DATABASE_URL`, `KB_DATABASE_AUTH` | `kb create-db`, `kb migrate-database`, `kb import`, `kb serve-data` | non: sans `KB_DATABASE_URL`, la base est `<KB_DATA_DIR>/k-b.sqlite` |
| `KB_ZOTERO_DIR`, `GOOGLE_APPLICATION_CREDENTIALS`, `KB_GITHUB_TOKEN`, `KB_COLLECT_ONLY` | `kb collect` | non: sans les deux premières, Zotero et GH Archive sont sautés; sans le jeton, l'API GitHub accepte 60 requêtes par heure au lieu de 5 000 |
| `KB_VAULT_DIR` | `kb collect`, `kb write-tops`, `kb digest`, `kb trend-report`, `kb daily-routine`, `kb digest-watch` | non pour `kb collect`, qui saute alors les clips; oui pour les cinq autres (`read_vault_dir_or_refusal`, `etl/collected_sources.py`) |
| `KB_DATA_API_KEY_<CLIENT>` | `kb serve-data` | oui, une au moins |
| `KB_DATA_API_HOST`, `KB_DATA_API_PORT`, `KB_DATA_API_ALLOWED_HOSTS` | `kb serve-data` | non |
| `KB_AI_API_KEY_<CLIENT>` | `kb serve-ai`; `kb digest` lit `KB_AI_API_KEY_KB_DIGEST`, `kb trend-report` lit `KB_AI_API_KEY_KB_TREND_REPORT` | oui: une au moins pour `kb serve-ai`, la sienne pour `kb digest` et `kb trend-report` |
| `KB_LLM_PROVIDER`, `KB_DATA_API_KEY_AI_DIGEST`, `KB_AI_GITHUB_TOKEN` | `kb serve-ai` | oui |
| `KB_LLM_BASE_URL`, `KB_LLM_MODEL`, `KB_LLM_API_KEY` | `kb serve-ai` | oui avec `KB_LLM_PROVIDER=openai_compatible` |
| `KB_LLM_REPLAY_FILE` | `kb serve-ai` | oui avec `KB_LLM_PROVIDER=replay`, qui répond par les réponses d'un fichier, sans réseau ni clé |
| `KB_LLM_REASONING_EFFORT`, `KB_AI_API_HOST`, `KB_AI_API_PORT`, `KB_DIGEST_WINDOW_DAYS` | `kb serve-ai` | non |
| `KB_DATA_API_URL` | `kb serve-ai`, `kb smoke-test`, `kb digest-watch` | non |
| `KB_OTLP_ENDPOINT`, `KB_OTLP_HEADERS`, `KB_TRACE_CONTENT` | `kb serve-ai` | non: sans les deux premières, rien n'est exporté, et `kb serve-ai` refuse de démarrer avec `KB_TRACE_CONTENT` autre que `none` (`find_content_without_export_refusal`, `ai_api/connectors/metrics_export.py`) |
| `KB_DEPLOYMENT_ENVIRONMENT` | `kb serve-data`, `kb serve-ai`; les commandes qui lisent `KB_AI_API_URL` ou `KB_DATA_API_URL`, pour une URL `http` vers un service de compose (`find_internal_api_url_refusal`, `core/outbound.py`) | non, sauf avec l'export (`sandbox` ou `production`). Seul `sandbox` sert `/docs` et `/openapi.json` (`read_openapi_url`, `core/api_settings.py`) |
| `KB_AI_API_URL` | `kb digest`, `kb trend-report`, `kb smoke-test`, `kb digest-watch` | non |
| `KB_EXCHANGE_BLOB_URL`, `AZURE_CLIENT_ID` | `kb smoke-test`, `kb daily-routine`, `kb digest-watch`; `AZURE_CLIENT_ID` aussi avec `KB_DATABASE_AUTH=entra` | oui pour ces commandes |
| toute variable `OTEL_*` | `kb serve-ai` | à ne jamais poser: `kb serve-ai` refuse de démarrer avec une seule (`read_metrics_export_settings_or_refusal`, `ai_api/connectors/metrics_export.py`) |

## Les dépendances

`pyproject.toml` déclare les 16 dépendances de K-B (`[project]`, `dependencies`) et le groupe `dev`
(`[dependency-groups]`), qui ne sert qu'au développement et aux tests. `uv.lock` fixe la version exacte de chaque
paquet, dépendances indirectes comprises: 96 paquets, K-B compris. Chacun porte l'empreinte `sha256` de ses fichiers,
sauf K-B, installé depuis le dépôt (`source = { editable = "." }`).
L'image n'installe pas le groupe `dev`: ses deux `uv sync` portent `--no-dev` (`Dockerfile`).

| Paquet | Plancher | Borne haute | Version de `uv.lock` | Rôle dans K-B |
|---|---|---|---|---|
| `azure-identity` | 1.27.0 | — | 1.27.0 | le jeton de l'identité managée, en ligne: la base PostgreSQL avec `KB_DATABASE_AUTH=entra` (`database/entra.py`) et le stockage d'échange des jobs (`exchange/storage.py`) |
| `azure-storage-blob` | 12.31.1 | — | 12.31.1 | le stockage d'échange des jobs: le miroir des clips, la publication de `veille/`, la liste de `kb smoke-test` (`jobs/`) |
| `beautifulsoup4` | 4.15.0 | — | 4.15.0 | la lecture des pages HTML de TLDR (`etl/sources/tldr.py`) |
| `defusedxml` | 0.7.1 | — | 0.7.1 | la lecture du flux Atom d'arXiv, sans développer une entité déclarée dans le flux (`etl/sources/arxiv.py`) |
| `fastapi` | 0.122 | — | 0.143.1 | les deux API, leurs routes et leurs dépendances (`data_api/`, `ai_api/`, `core/api_*.py`) |
| `google-cloud-bigquery` | 3.46 | < 4 | 3.46.1 | la requête de GH Archive sur BigQuery (`etl/sources/gh_archive.py`) |
| `httpx2` | 2.13.1 | — | 2.13.1 | les requêtes HTTP sortantes: la collecte (`etl/http_download.py`), l'API IA vers le modèle, l'API de données et GitHub (`ai_api/connectors/`), `kb digest` et `kb trend-report` vers l'API IA (`post/`), les `/health` des jobs (`jobs/api_health.py`) |
| `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http` | 1.45.1 | < 1.46 | 1.45.2 | l'export des mesures, des traces et des journaux de l'API IA en OTLP (`ai_api/connectors/metrics_export.py`, `ai_api/connectors/trace_export.py`, `ai_api/tracing.py`, `ai_api/observability/metric_instruments.py`). La borne: `trace_export.py` importe des modules privés du SDK et de son exportateur, qui changent d'une version à l'autre |
| `psycopg[binary]` | 3.3.8 | — | 3.3.8, avec `psycopg-binary` 3.3.8 | la connexion à PostgreSQL (`database/postgresql.py`, `database/errors.py`). L'option `binary` apporte libpq: la machine n'a pas à l'installer (documentation de psycopg, « Installation », lue par Context7 le 2026-11-08) |
| `psycopg-pool` | 3.3.3 | — | 3.3.3 | le pool des connexions de lecture de l'API de données sur PostgreSQL (`database/postgresql.py`) |
| `pydantic` | 2.13.5 | — | 2.13.5 | la validation des entrées: les items des sources (`items.py`, `etl/sources/`), les schémas et les réglages des API (`data_api/`, `ai_api/`), les réponses que lisent `kb digest` et `kb trend-report` (`post/`) |
| `pyyaml` | 6.0.3 | — | 6.0.3 | la lecture du frontmatter des clips (`etl/sources/clipping.py`) |
| `requests` | 2.34.2 | — | 2.34.2 | la session HTTP des exportateurs OTLP, qui ne lit ni proxy, ni certificat, ni `.netrc` de l'environnement (`build_session`, `ai_api/connectors/metrics_export.py`) |
| `uvicorn` | 0.54.0 | — | 0.54.0 | le serveur des deux API (`commands/serve_data_command.py`, `commands/serve_ai_command.py`) |

Les paquets du groupe `dev` (pytest, ruff, mypy…) et leur rôle sont dans [la fiche des tests](tests_pour_docu.md),
« Les dépendances installées ».

## L'environnement de test

`uv sync` (plus haut) installe déjà le groupe `dev`, donc les outils des tests: rien d'autre n'est à installer pour
la suite par défaut, qui ne lit aucun `.env`.

```sh
uv sync
uv run pytest
uv run ruff check --no-cache
uv run ruff format --check
uv run mypy --strict
```

`uv run pytest` lance toute la suite, sauf les tests marqués `e2e` et `postgresql` (`MARKERS_LEFT_OUT_BY_DEFAULT`,
`tests/conftest.py`). Les trois commandes suivantes sont le lint, le format et le typage, que la CI vérifie aussi;
elle lance `uv run ruff check` sans `--no-cache`, une précaution prise sur la machine (fiche des tests,
« Lancer les tests »).

Les tests marqués `postgresql` demandent un serveur PostgreSQL de test, jamais la base de production. Sur le Mac,
c'est le PostgreSQL de Homebrew, sans conteneur; la formule `postgresql@18` (18.6 selon
`brew info --json=v2 postgresql@18`, observé le 2026-11-08) est de la version majeure du service de la CI
(`postgres:18.6`, job `tests-postgresql` de `.github/workflows/ci.yml`):

```sh
brew install postgresql@18
brew services start postgresql@18
KB_TEST_POSTGRESQL_URL=postgresql://<rôle>@127.0.0.1:5432/postgres uv run pytest -m postgresql
```

`<rôle>` est un rôle du serveur qui peut créer et supprimer une base, et créer des rôles. Sans
`KB_TEST_POSTGRESQL_URL`, chaque test marqué `postgresql` échoue: il n'est jamais sauté.

Le détail est dans [la fiche des tests](tests_pour_docu.md): l'installation de l'environnement de test, dont les tests
de bout en bout et leur `.env.e2e_test` (« Installer l'environnement de test »), les dépendances installées, les
commandes et les rapports (« Lancer les tests »), la couverture, et ce que lance la CI.

## Limites

- `uv run --env-file .env` charge tout le `.env`: chaque commande reçoit aussi des secrets dont elle n'a pas besoin
  (le jeton GitHub et les identifiants Google pour `kb serve-data`, par exemple). Le moindre privilège n'est pas tenu
  sur la machine.
- `read_environment` rend l'environnement du processus tel quel (`os.environ`): une variable exportée par le profil du
  shell (`~/.zshrc`) est lue comme une variable du `.env`, et le reste quand elle est retirée du `.env`. Une clé d'API
  retirée du `.env` mais exportée par le profil reste donc valide. Avec `KB_DATABASE_URL`, une variable de libpq
  (`PGHOST`, `PGPASSWORD`…), du `.env` ou du profil, fait refuser la base: libpq la lirait à côté de l'URL
  (`LIBPQ_VARIABLES`, `read_database_location_or_refusal`, `database/location.py`).
