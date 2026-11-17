# K-B — mémoire du projet

Ce que le code et le README ne disent pas : le contexte, les estimations et les consignes. Les
décisions sont dans `docs/ADR/journal-decisions-projet.md`. Chargé à chaque session par le
`CLAUDE.md`. Le dépôt devient public le 08/11 : rien de personnel ici.

## Contexte

- K-B est le projet support de la certification Développeur IA (RNCP37827) : E1 (pipeline de
  données) et E3 (API IA) d'abord, hors machine learning. K-B tourne en trois temps : d'abord sur le
  Mac, sans conteneur (retour en CLI, fiches `.md`) ; puis en conteneurs en local, avant le 29/10 si
  le temps le permet ; puis sur Azure Container Apps au 08/11 (journal ADR, 2026-10-20,
  « Squelette E1 E3 : cadrage du 20/10 », décision 1). Le suivi de la certif vit dans un dépôt
  séparé, pas ici. Les dates sont tenues par time-knight.
- Les critères de la certif deviennent des exigences de K-B seulement là où ils servent le produit.
- **Binôme** : Sabine travaille avec Claude Code. Claude écrit l'essentiel du code et de la doc ;
  Sabine pilote, relit, teste et décide. Les estimations en tiennent compte : les comptes, la prise
  en main d'outils nouveaux, les décisions et la relecture ne s'accélèrent pas.
- **Refactorisation de l'ETL** (branche `refactoring/etl`, PR du 2026-10-24) :
  `docs/refactoring/plan.md` fait foi pour la cible et les étapes restantes (3 bis avant la mise
  en ligne du 08/11, puis 6 à 9), une branche et une PR par étape (sa partie 6). Ce qui en est
  acté est au journal ADR (2026-10-22 : `post/` hors de l'ETL ; 2026-10-23 : `etl/pipeline.py`,
  porte des deux parcours pour `commands/`) et à la règle 5 de `conventions.md`.

## Estimations

- Une issue porte sa taille seule (label `size:*` et champ `Size` du board), sans heures (règle
  de l'utilisatrice du 2026-10-20).
- La surveillance du modèle est portée par #163 (comparaison des outils), puis #162 et #164, au
  jalon « POC 25/10 » : métriques en OpenTelemetry vers Grafana Cloud dès le premier temps
  (journal ADR, 2026-10-20, décision 4).
- Coupes du 15/10 (journal ADR, « POC du 25/10 ») : la compilation des clips en wiki passe après
  le 29/10, `kb search` après le 08/11. arXiv et Zotero vont ensemble ; l'ingester arXiv est
  repris de brief09.

## Problèmes connus

- **Le détail et la liste de l'API de données sont bornés en temps, par instruction en PostgreSQL**
  (#331, #418, #550) : depuis #430, la
  lecture du détail est bornée à 101 surlignages (2 020 000 caractères de texte et de commentaire au
  plus) et à 125 001 caractères du texte d'un clip ; en SQLite, ce que le moteur charge pour calculer
  `substr` n'est pas mesuré (`docs/specs-api.md`, « Bornes du détail »). Le temps reste
  borné ainsi : 5 s par requête en SQLite, que la page de la liste et son total se partagent ; en
  PostgreSQL, 5 s par instruction (`statement_timeout`, #418) : le détail en fait jusqu'à trois, 15 s
  en théorie, et la liste deux, la page et son total, 10 s en théorie ; plus 2 s d'attente du pool,
  c'est au-delà des 10 s du client de l'API IA (limites choisies aux plans de #418 et de #550).
- **La base est la seule copie au-delà de 6 mois, et K-B n'a pas de migration** (#83, décision de
  Sabine du 2026-11-04) : la purge supprime le brut de plus de 6 mois, et la base n'a pas encore de
  sauvegarde (règle du 2026-10-19 écrite au registre, étape 3, pas codée). Dès que le plus ancien
  brut a 6 mois, un changement de schéma ne se fait plus par `kb create-db` et `kb import` : il lui
  faut une migration (journal ADR, 2026-10-09, W7).
- **Une donnée que la source republie revient après sa purge** (limite acceptée par Sabine le
  2026-11-04, registre, étape 2) : une release encore parmi les 100 dernières de son dépôt, une
  alerte que GitHub met à jour sont une collecte nouvelle, et leurs 3 ans repartent.
- **arXiv bloqué au-delà de 2 000 papiers** (constat du 2026-10-05, porté par #71, hors E1 et
  non planifié). Si la fenêtre de collecte contient plus de
  2 000 papiers, la source échoue et sa date reste (`src/k_b/etl/sources/arxiv.py:85-89`). La fenêtre
  suivante part du même point et finit plus tard : elle dépasse encore le plafond, la source
  échoue à chaque collecte. Cela contredit la consigne du 05/10 : lancée tous les jours, K-B
  rattrape les jours manqués (#65).
- **Deux collectes en même temps perdent des dates** (relevé par la revue de #201, le 2026-10-18,
  porteur à désigner par Sabine). `collect_all_sources` lit tout `collection_state.json` au début
  et le réécrit en entier à la fin (`src/k_b/etl/extract.py`) : la dernière collecte qui écrit
  l'emporte. Avec `KB_COLLECT_ONLY`, le Mac (`zotero,clipping`) et les conteneurs (le reste)
  collectent à part ; s'ils partagent l'état (#200), leurs collectes ne doivent pas se chevaucher.
- **La ligne « Sécurité » du registre** (fiche 1) ne dit encore, de ce qui est en ligne, que la base
  (#421, section « Base en ligne ») : les autres données hébergées sur Azure (stockage d'échange, #412
  à #414) y entrent avec la PR qui les héberge (revue de #5, le 2026-10-18).
- **Deux pourquoi de `.claude/rules/poc.md` contredisent le cadrage du 20/10** (revue de #275, le
  2026-10-20 ; signalé à Sabine, qui modifie `.claude/`) : la règle 1 dit « La base passe à
  PostgreSQL au 08/11 (décision 2) », décision en attente de « La base au temps 3 » ; la règle 6
  dit « Le POC en conteneurs », alors que le premier temps se fait sans conteneur (journal ADR,
  2026-10-20, décision 1). La règle 1 est de nouveau juste depuis le 2026-11-06 : PostgreSQL en ligne
  (journal ADR, « Base : PostgreSQL en ligne, par un adaptateur maison (#417) »).
- **GH Archive ne voit qu'environ 1 % des étoiles** (mesure de time-knight du 2026-10-29, cause
  inconnue) : `trend` est un échantillon. Ne jamais écrire « étoiles gagnées » tirées de GH Archive
  sans le dire (`docs/specs-collecte.md`, « Limite mesurée le 2026-10-29 »).
- **`read_bounded_body` ne borne rien avant le premier morceau décodé** (#436, revue de #422, le
  2026-11-06) : un en-tête envoyé octet par octet, ou un corps gzip fait de blocs vides, échappe à
  l'échéance chez ses quatre clients (`kb`, API de données, modèle, GitHub), et chez `read_body_head`, la
  lecture de la tête d'un README, qui partage sa boucle (`read_pieces`, #369). En ligne, l'ingress
  d'ACA coupe une requête à 240 s ; en local, rien ne la coupe.

## Interface

- Au premier temps : sur le Mac, sans conteneur, retour dans la console, par les commandes
  `kb`, et fiches `.md` ; ni interface CLI dédiée ni front (journal ADR, 2026-10-20, décision 1).
  `kb search` vient après le 08/11 ; un front écoconçu, plus tard (journal ADR, 2026-10-15,
  « POC du 25/10 »). Une commande de plus, `kb write-tops` (#265), écrit les fiches des tops dans
  le coffre, après `kb import` (journal ADR, 2026-10-19, « Tops : les fiches par `kb write-tops` »).
- L'API IA est servie par `kb serve-ai` (#156), à côté de `kb serve-data`, sur `127.0.0.1:8001` ; ses
  clients ont leur clé dans `KB_AI_API_KEY_<CLIENT>`, ceux de l'API de données dans
  `KB_DATA_API_KEY_<CLIENT>` (journal ADR, 2026-10-21, « API IA : servir les fiches par
  `POST /digests` »).
- Le site (#562 à #564) est servi par `kb serve-web`, sur `127.0.0.1:8002`, FastAPI et Jinja2 sans
  JavaScript (`docs/site-web.md`) : le paquet `web` n'importe que `core` et `items` et lit l'API de
  données par HTTP, comme son client `WEB` (`KB_DATA_API_KEY_WEB`). Il est privé : chaque requête sauf
  `/health` porte l'identifiant d'objet de Sabine (`KB_WEB_OPERATOR_ID`) dans l'en-tête
  `X-MS-CLIENT-PRINCIPAL-ID` posé par Azure Container Apps ; `KB_WEB_AUTH=off` seulement sur
  `127.0.0.1` et hors d'Azure (`CONTAINER_APP_NAME` absente). Un gabarit n'écrit jamais `|safe`,
  `url_for`, un script ni un style en ligne (tests de `tests/web/`).
- Depuis #559, l'API de données lit aussi le conteneur `watch` (`data_api/watch_reading.py`, ouvert par `kb serve-data`
  avec `KB_EXCHANGE_BLOB_URL` et `AZURE_CLIENT_ID`, sinon 503 `watch_unconfigured`) : `GET /tops/{top}` et
  `GET /tops/{top}/days`, réservées au client `WEB` (`DATA_API_CLIENT_BY_ROUTE`, `check_client_allowed` sur leur
  routeur). Elles lisent le jumeau JSON que `kb write-tops` écrit à côté de chaque fiche d'un top, `TopProduction`
  (`items.py`). Son heure est `ranked_at`, jamais `collected_at`, que l'API ne sert pas
  (`test_no_route_documents_a_raw_file_path_or_a_collection_date`). Depuis #560, de même `GET /digests/{subject}` et
  `GET /digests/{subject}/days`, du jumeau que `kb digest` écrit après chaque fiche, `DigestProduction` : un seul
  lecteur, une `TwinKind` par sorte (`TOP_TWINS`, `DIGEST_TWINS`, chacune son cache). Un sujet nouveau de
  `DIGEST_SUBJECTS` s'écrit aussi dans `DigestSubjectName` (`data_api/schemas/watch_digest_schema.py`, tenu par un test).
- `kb digest` (#209) demande les fiches à l'API IA, puis les écrit dans le coffre,
  `veille/<sujet>/AAAA-MM-JJ.md` ; `kb serve-data` et `kb serve-ai` doivent tourner (journal ADR,
  2026-10-21, « Fiches de veille : `kb digest` les écrit dans le coffre »).
- `kb serve-ai` exporte les mesures du modèle en OpenTelemetry vers Grafana Cloud (#162), pile
  `prod-eu-west-2` (Allemagne), quand `KB_OTLP_ENDPOINT`, `KB_OTLP_HEADERS` et
  `KB_DEPLOYMENT_ENVIRONMENT` sont réglées ; il refuse de démarrer avec une variable `OTEL_*`
  (le SDK la lirait en silence). OpenTelemetry ne s'importe que dans
  `ai_api/connectors/metrics_export.py` et `ai_api/observability/metric_instruments.py` (décision de Sabine du
  2026-10-24), et depuis #345 dans `ai_api/tracing.py` (la façade des traces) et
  `ai_api/connectors/trace_export.py` (seul à importer les modules privés du SDK). Dans Grafana,
  les séries de K-B se lisent par `{job="k-b-ai-api"}`. L'essai gratuit
  de 14 jours de la pile finit vers le 07/11 : l'offre gratuite garde 14 jours et 10 000 séries.
- Depuis #345, chaque `POST /digests` est une trace sans texte (`docs/fiches-veille.md`, « Traces de
  `POST /digests` ») : Tempo, `{resource.service.name="k-b-ai-api"}` ; les raisons d'une affirmation
  retirée sous « Logs for this span » d'un `chat`. Une fonction d'`ai_api` qui prend `tracing` le
  reçoit toujours par `tracing=` (test AST) : une étape nouvelle ouvre son span par `tracing.step`
  et passe `tracing=` plus bas. Le jeton porte `metrics:write`, `traces:write` et `logs:write`.
  OpenTelemetry est borné sous 1.46 : une montée relit `trace_export.py`.
- Depuis #347, le contenu d'un appel au modèle (consigne, items, sortie) peut partir avec les traces,
  sous `KB_TRACE_CONTENT` (`none` par défaut, `anomalies`, `all` refusé en production) : une exception
  à la règle 5 de `poc.md`, des données personnelles chez Grafana. Ne jamais poser `anomalies` ni
  `all` : leur condition, le DPA de Grafana Labs, est portée à Sabine depuis la réponse de Grafana
  Labs du 2026-10-29 (registre, « Envoi des mesures à Grafana Cloud », ligne « Contrat » ; #163).
  Ce qu'est une anomalie (D1, précisée le 2026-10-28) ne se change que par Sabine, dans
  `is_anomaly` (`ai_api/connectors/llm_client.py`) ; une étape nouvelle qui appelle le modèle appelle
  `trace_contents(llm_call, tracing=tracing)` après avoir jugé l'appel.
- Depuis #627, l'API IA appelle les modèles du banc de C7 : `KB_LLM_REASONING_EFFORT` à `none`, `minimal` ou `low`
  (gpt-6.1-sol demande `low`), `KB_LLM_MODEL` en `<éditeur>/<modèle>`. Ne jamais poser
  `KB_LLM_SEND_PROMPT_CACHE_OPTIONS=false` pour un modèle sans sa ligne au registre des traitements : le fournisseur
  peut alors garder les items dans son cache de prompt (`docs/fiches-veille.md`, « Réglages d'appel »).
- Le compte rendu des tendances (`kb trend-report`, #364 à #370) : contrat dans `docs/tendances.md`,
  écrit avant le code ; #365 à #370 sont codées par time-knight (organisation de Sabine du
  2026-10-30). Sortie dans `veille/tendances/<date>.md` ; période tenue par
  `KB_DATA_DIR/trend_reports.json`, jamais par une relecture du coffre. `kb trend-report` est le
  client `KB_TREND_REPORT` de l'API IA (`KB_AI_API_KEY_KB_TREND_REPORT`, une clé distincte de celle
  de `kb digest`).
- Depuis #367, `kb serve-ai` ne démarre pas sans `KB_AI_GITHUB_TOKEN`, un second jeton
  *fine-grained* (`github_pat_`, `docs/jeton-github.md`) : l'API IA lit la fiche GitHub de chaque
  candidat d'un compte rendu. Aucun test n'appelle GitHub : `make_app` des tests de la route sert la
  fixture par un GitHub simulé.
- Depuis #412, `kb smoke-test` (job `caj-kb-smoke-test`) et le paquet `jobs/`, le code commun aux commandes des
  jobs (ce qu'ils font du stockage d'échange, `/health`) : seul `commands` l'importe, il n'importe que `exchange`
  et `core` (`test_layers`). Depuis #558, le client du stockage d'échange (identité managée, transport, erreurs
  nommées, téléchargement d'une version listée) est le paquet `exchange/` : seuls `jobs`, `commands` et `data_api`
  l'importent, il n'importe que `core`, jamais `core.atomic_write`. Le nom d'un blob est le titre d'un clip :
  jamais dans un journal. `logging_to` tient `azure` et `urllib3` à ERROR (`LIBRARY_LOG_LEVELS`) ; une erreur du
  SDK passe par `naming_storage_errors`, jamais par `str(error)`. Un transport donné au SDK de stockage lui fait
  perdre ses délais (300 s au lieu de 20 et 60) : toujours `build_transport`. Les tests simulent le SDK par
  `FakeTransport` et le point d'identité par `IDENTITY_ENDPOINT` (`tests/exchange/storage_fakes.py`), sans réseau ; un
  nom repérable se cherche brut et encodé dans une URL (`names_the_spotted_blob`). L'envoi et le téléchargement
  viennent avec #413.
- Depuis #413, `kb daily-routine` et `kb digest-watch` enchaînent les commandes `kb` dans le même processus
  (`commands/job_routine.py`), jamais par sous-processus : `kb` est le PID 1, seul à recevoir SIGTERM. Une étape
  nouvelle est une `RoutineStep` de la liste de sa routine, appelée par une `lambda` (un test remplace la fonction
  dans le module) ; une règle `NotRunAfter` nomme une étape antérieure (tenu par un test). Une commande nouvelle
  lancée en job entre dans `COMMANDS_STOPPED_BY_SIGTERM`. Un blob refusé se cite par sa position
  (`blob 12 of 120`). `FakeContainer` (`tests/exchange/storage_fakes.py`) simule liste, téléchargement et envoi ; un test
  qui lit le journal capte `caplog.at_level(logging.INFO, logger="k_b")`, car à INFO le SDK écrit l'URL d'un blob.
  En ligne, `kb purge`, l'étape de `kb daily-routine` qui suit `kb import`, purge le brut à 6 mois jusqu'à #390
  (journal ADR, 2026-11-06 et 2026-11-10).

## Consignes de travail

- **Mise en ligne sur Azure** (#414, 2026-11-06) : `infra/main.bicep` s'applique en deux passes (sans `imageTag`,
  puis avec), par Sabine à la main, en suivant `infra/README.md`, « Appliquer ». Une session donne les commandes
  et lit l'état en lecture seule (`az … show`, `log-kb`), sans rien appliquer elle-même. Une API au repos met
  20 à 26 s à se réveiller (journal ADR, 2026-11-06, « Mise en ligne »).
- **Site privé** (#571, 2026-11-11) : `ca-kb-web` derrière la connexion Entra de la plateforme. Toute passe porte
  `webAuthClientId`, et tire `exposeWeb` de la connexion en ligne (`infra/README.md`, étape 5) : un site à créer naît
  fermé et ne s'ouvre qu'à la passe suivante, sa connexion lue ; jamais `exposeWeb=true` en dur. Entra reste son seul
  fournisseur d'identité. Le secret client de l'inscription « K-B site » **expire le 2027-05-11** : la rotation se fait avant,
  avec `--append` (`infra/README.md`, « La rotation du secret client »).
- **Tags de version** (#415, décision de Sabine du 2026-11-06) : aucune session ne pose ni ne pousse de tag sans une
  demande explicite de Sabine, et aucune n'approuve un déploiement en attente (`pending_deployments`). Un tag `vX.Y.Z` sur `main` déploie en ligne (`.github/workflows/deploy.yml`), sans
  validation jusqu'au 08/11 (risque accepté, registre, « Déploiement continu »). Après un déploiement par tag, une
  passe 2 à la main prend la version en ligne pour `imageTag`. Un job nouveau s'ajoute à `infra/deployment.json`
  (`infra/README.md`, « Déployer une version »).
- **Accès à la base** (#416, puis #417, 2026-11-06) : seuls `database/engine.py` (`Connection`,
  `connect_database`, `lock_for_writing`, `connect_database_read_only`, `set_query_timeout`), `database/errors.py`
  (`ENGINE_ERRORS`, refus d'une entrée, `describe_engine_error`, `is_query_timeout`) et `etl/sources/zotero.py` (la
  base de Zotero) importent `sqlite3` ; seuls `database/postgresql.py` et `database/errors.py` importent psycopg,
  et `database/postgresql.py` seul `psycopg_pool` (#418). Un module nouveau passe par eux. L'API de données lit par
  `connect_reader(readers, …)` (`database/engine.py`) : `Readers` est le fichier SQLite ou le pool de lecture
  PostgreSQL, ouvert par `open_readers` dans `kb serve-data` ; une lecture de plusieurs requêtes s'ouvre par
  `begin_reading`, jamais par `execute("BEGIN")`. `psycopg` et `psycopg_pool` sont tenus à ERROR
  (`LIBRARY_LOG_LEVELS`) : à WARNING, ils citent le texte de libpq et la connexion (hôte, utilisateur, base). `Connection` est l'union `sqlite3.Connection | PostgresConnection` ; une erreur
  du moteur se rattrape par `except ENGINE_ERRORS` (un tuple), jamais par `EngineError`, l'alias des annotations.
  Tenu par `tests/architecture/test_engine_imports.py`.
- **Jeu de référence de `POST /digests`** (#479, 2026-11-08) : `tests/fixtures/digests_reference.json`, des sorties
  de gpt-6-luna enregistrées par Sabine, rejouées par `tests/ai_api/test_digests_reference.py`. Une session ne lance
  jamais l'enregistrement (`tests/ai_api/digests_reference.py`, un appel payant, qui refuse d'écraser le jeu). Un
  changement du nombre de requêtes au modèle (lots, nouvelle tentative, étape) décale le rejeu et fait échouer ce
  test : seul un nouvel enregistrement par Sabine le répare. Un changement de `prompt_version` ne le fait pas
  échouer (péremption laissée à #482).
- **Tests sur PostgreSQL** (#417, 2026-11-06) : marqués `postgresql`, écartés par `uv run pytest` comme `e2e`,
  lancés par `KB_TEST_POSTGRESQL_URL=<URL d'un serveur> uv run pytest -m postgresql` ; sans cette variable, un test
  marqué échoue, jamais sauté. Une base neuve par test qui écrit par `kb`, une transaction
  annulée par test pour les autres (`tests/conftest.py`). En CI : le job `tests-postgresql` de `ci.yml`, PostgreSQL 18 par son
  digest, mis à jour à la main. Sur le Mac : un PostgreSQL de Homebrew, sans conteneur. Un SQL nouveau de
  `database/` passe par le traducteur de marqueurs (test de `tests/database/test_postgresql.py`) ; une table ou un
  `CHECK` nouveau s'écrit dans `schema.sql` et `schema_postgresql.sql`. Un test de lecture prend la fixture `engine` (`tests/conftest.py`, #418) :
  une moitié SQLite, une moitié marquée `postgresql` ; ses fixtures PostgreSQL se prennent par
  `request.getfixturevalue` dans la seule moitié PostgreSQL, sinon `uv run pytest` demande le serveur. La
  structure des deux schémas est comparée par `tests/test_schema_structures.py` : un écart nouveau voulu
  s'écrit dans `WANTED_DIFFERENCES`.
- **Base en ligne** (#421, 2026-11-06) : `KB_DATABASE_AUTH=entra` (défaut `libpq`) ouvre la base PostgreSQL par
  le jeton de l'identité managée d'`AZURE_CLIENT_ID`, demandé à chaque connexion nouvelle, pool compris
  (`database/entra.py`) ; K-B refuse alors une URL sans `sslmode=verify-full` ou qui porte un mot de passe.
  `kb migrate-database` (job `caj-kb-migrate-database`) crée la base qui n'a pas ses tables, et laisse telle quelle
  celle qui les a : ce n'est pas une migration (#186). La base `kb` et les rôles se créent à la main
  (`infra/postgresql/`, `infra/README.md`). Les droits sur les tables (`grants_postgresql.sql`) ne se posent qu'à
  la création : une table ajoutée à une base en ligne existante n'a de droits que par une migration (#186). Les
  tests créent les rôles des identités sur leur serveur et y passent `grant-roles.sql` tel quel
  (`tests/database/online_roles.py`, fixture `administered_base`).
- Pour la documentation d'une bibliothèque ou d'un service, utiliser Context7 plutôt qu'une
  lecture de page web. Ce que Context7 ne couvre pas : WebSearch, source et date à l'appui ;
  WebFetch seulement sur une URL qu'une recherche du jour vient de rendre.
- Une décision actée ne se repose pas, sauf si Sabine demande à la réviser ou si elle est notée
  « à revoir » : chercher d'abord dans `MISSION.md`, le journal ADR et la conversation, et citer
  d'où vient la réponse. Redemander un accord (commit, push) reste permis.
- Un essai sur un fichier non committé ne s'annule jamais par `git checkout` (il efface aussi le
  travail du fichier) : committer d'abord, essayer sur une copie dans le scratchpad, ou annuler
  par une édition inverse.
- Vérifier les faits avant de les présenter comme sûrs, sources à l'appui.
- `brief09_assistant-veille-tech` est indicatif, il ne fait pas autorité : une décision concertée
  qui fait mieux, ou plus conforme aux pratiques reconnues, l'emporte.
- **Mutations sur une copie du dépôt** (constat du 2026-10-17, #14) : les lancer avec
  `PYTHONDONTWRITEBYTECODE=1` et sans `__pycache__`. Une mutation qui garde la taille du fichier,
  restaurée dans la même seconde, laisse sinon Python exécuter le bytecode de la version mutée :
  les mutations suivantes semblent tuées ou survivantes à tort. Une copie qui garde le `.venv` du
  dépôt lit le `src` du dépôt d'origine (`k_b.pth` y pointe ; constat du 2026-10-18, #242) :
  vérifier d'abord que `import k_b; print(k_b.__file__)` donne le chemin de la copie.
- **Fichiers d'environnement et Bash** (constat du 2026-10-21, #156) : l'outil refuse toute
  commande Bash qui nomme un fichier `.env*`, `.env.example` compris : `cat`, `grep`, `git add`, et
  même un message de commit qui en cite le nom. `.env.example` et `.env.e2e_test.example` se lisent
  et se modifient par Read et Edit ; Sabine tape `! git add <fichier>`. Ne pas contourner (pas de
  `git add -u`).
- **Échappements `\u` et `\x` dans un fichier écrit par Write ou Edit** (constat du 2026-10-21,
  #209) : un `"\u202e"` écrit dans le contenu est arrivé dans le fichier comme le caractère
  lui-même, un contrôle bidirectionnel invisible (Write dans le code, Edit dans ce fichier même ;
  Write a fait de même d'un `\x1b`), alors que `\\` et `\n` restaient tels quels. Écrire ces
  caractères par `chr(0x202E)`, ou par un script Python ou un heredoc `<<'EOF'`, et vérifier
  qu'aucun fichier modifié ne contient de caractère des catégories Unicode `Cc` ou `Cf` hors
  tabulation, retour à la ligne et U+200D.
- **`ruff` sans son cache** (constat du 2026-10-19, revue de #265) : `uv run ruff check` a passé,
  puis `uv run ruff check --no-cache` a trouvé trois imports non triés. Cause non établie : le cache
  est supposé (le `pyproject.toml` ne fixe ni `src` ni `known-first-party`, la détection des imports
  internes est une autre piste). Avant de déclarer les contrôles verts :
  `uv run ruff check --no-cache`.
- **Tests de bout en bout** (#25, 2026-10-21) : un par source, dans `tests/e2e/`, marqués
  `e2e` ; `uv run pytest` (la CI) les écarte (`tests/conftest.py`). Les rejouer sur le Mac, avec
  leur rapport HTML (#290), depuis un terminal sans `.env` exporté :
  `uv run --env-file .env.e2e_test pytest -m e2e -rs --html=reports/e2e-report.html --self-contained-html`
  (une source : `-k <source>`). `.env.e2e_test` ne porte que leurs variables
  (`.env.e2e_test.example`) ; une autre variable de `.env.example` dans l'environnement les arrête
  avant tout `kb`. Le rapport (`reports/`, ignoré par git, en `0600`) donne les résultats, pas leur
  interprétation : le compte rendu reste écrit à la main. Celui de `gh_archive`
  lance une requête BigQuery réelle : ne pas le relancer à la légère. Sans `--basetemp` : pytest
  garde ses 3 dernières sessions (registre, étape 10 de la procédure de tri) ; un `--basetemp`
  n'a plus de rotation et est effacé par pytest s'il existe déjà.
- **Liste des tests collectés** (constat du 2026-10-18, #247) : elle n'est pas stable d'une
  exécution à l'autre. `test_a_key_refused_is_never_quoted` (`tests/ai_api/test_data_api_settings.py`)
  est paramétré par une clé tirée par `secrets.token_urlsafe(32)` au chargement du module. Pour
  comparer deux listes, remplacer d'abord cette clé par un repère :
  `sed -E 's/(never_quoted)\[[A-Za-z0-9_-]{43} /\1[<random key> /'`.
- **Fixtures** (consigne de Sabine, 2026-10-10) : une fixture part toujours d'un exemple issu de
  la collecte. Quand la licence de son texte ne permet pas de le publier, elle garde la forme de
  l'exemple, avec un texte écrit pour l'occasion ; un auteur arXiv y prend un nom fictif (journal
  ADR, 2026-11-06, « Mise en public du dépôt (#278) » ; licences au README, « Contenus de tiers »).
- **Espaces avant « : » et « ; »** (règle de Sabine du 2026-11-11) : aucune, ni normale ni insécable, dans
  le texte du site (`src/k_b/web/templates/`, tenu par `tests/web/test_accessibility.py`) et dans
  `documentation/`. `docs/`, le journal ADR et les notes pédagogiques gardent l'usage du dépôt.
- **K-B est déterministe** dans sa conception, son code et ses journaux (consigne de Sabine,
  2026-10-04) : un journal ou un message d'erreur dit ce qui a été observé (URL de redirection,
  code HTTP, titre trouvé et titre attendu), jamais une supposition ni une interprétation
  (« probablement », « structure changée ? »). Le pourquoi d'un choix va dans les commentaires
  et la doc, pas dans les journaux.
- **Docstrings** (#300, 2026-10-24) : une PR qui ne touche que des docstrings se prouve par
  `ast.dump` sans docstrings et par les jetons `COMMENT` de `tokenize`, comparés sur tous les `.py`
  entre `origin/main` et `HEAD` (0 différence attendue). La preuve ne voit pas le texte : raccourcir a
  retiré 17 pourquoi que le code suppose, retrouvés seulement par la revue. Les docstrings des routes
  et des schémas des API sont l'OpenAPI versionnée (`docs/api/*.json`). Les renvois `fichier:ligne` de
  `.claude/rules/poc.md` visent le commit de départ `9e6e2e8`, pas `main` : ne pas les « corriger ».

## Revue, PR et GitHub

- Ordre fixe : commit → revue → rapport à Sabine → corrections sur accord → push → PR. Pas de
  push tant que la revue n'a pas rendu son rapport.
- `/code-review` est lancé directement par la session, jamais enveloppé dans un sous-agent : le
  skill tourne déjà dans le sien.
- Chaque constat de `/code-review` et `/security-review` est rapporté dans la conversation, avec
  un avis (corriger ou non, pourquoi), avant d'ouvrir la PR. Le budget se signale ; il ne fait
  sauter ni une étape ni ce rapport.
- Un plan non trivial est relu par un sous-agent sans contexte avant d'être soumis, son verdict
  rapporté en entier, sauf si la mission dit autrement.
- Titre, description et commentaires d'une PR (compte rendu de revue compris) : en anglais. Une
  issue et ses commentaires : en français.
- Tout texte publié sur GitHub (description et commentaire de PR, commentaire d'issue) finit par
  une ligne vide, `--`, puis `*Written by Claude Code*`. Un message de commit ne porte ni
  `Co-Authored-By` ni `Claude-Session:` ; une PR ne porte pas de lien de session.
- **Labels d'une issue** (consigne de Sabine, 2026-10-19) : une session K-B pose `size:*` et le
  label de périmètre, jamais un label de livrable (`E1`, `hors E1`…) : « si kb n'a pas
  connaissance du livrable, qu'elle ne mette pas de label livrable ».
