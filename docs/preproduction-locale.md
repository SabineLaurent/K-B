# Préproduction locale par compose

La préproduction locale lance K-B sur le poste dans les conteneurs de la production : l'image du
`Dockerfile`, construite pour `linux/amd64`, et PostgreSQL 18, avec un durcissement plus strict qu'en
ligne (#419). Elle sert à essayer une version avant sa mise en ligne : la base, la collecte, l'import, l'API de
données et l'API IA, jusqu'à une `POST /digests` réelle. Tout est dans `compose.yaml`, à la racine du
dépôt ; ses règles sont tenues par `tests/test_compose_file.py`.

## Ce qui tourne

| Service | Commande | Port sur le poste | Volume | Démarre après | Délai d'arrêt |
|---|---|---|---|---|---|
| `postgres` | le serveur PostgreSQL 18.6 | aucun | `pg-data` sur `/var/lib/postgresql` | | 20 s |
| `api-donnees` | `kb serve-data` | `127.0.0.1:8000` | aucun | `postgres` sain | 20 s |
| `api-ia` | `kb serve-ai` | `127.0.0.1:8001` | aucun | `api-donnees` saine | 250 s |
| `create-db` (profil `jobs`) | `kb create-db` | aucun | `kb-data` sur `/var/lib/knowledge_base` | `postgres` sain | 20 s |
| `collecte` (profil `jobs`) | `kb collect` | aucun | `kb-data` | | 20 s |
| `import` (profil `jobs`) | `kb import` | aucun | `kb-data` | `postgres` sain | 20 s |

`docker compose up -d` lance les trois services ; un job se lance seul, par `docker compose run --rm <job>`.
Un service est sain quand sa sonde répond : `pg_isready` en TCP pour la base, `GET /health` pour une
API, en `python -c` (l'image n'a pas `curl`), avec un en-tête `Host` que l'API de données permet. La sonde
de la base passe par TCP, car le serveur temporaire qui crée la base au premier démarrage ne répond que
sur le socket (`docker_temp_server_start`, `docker-entrypoint.sh` de l'image).

## Ce que la préproduction prend à la production

- **L'image** : celle du `Dockerfile`, construite en local pour `linux/amd64`, la plateforme d'Azure
  Container Apps (`k-b:preprod`, une seule image pour les cinq services `kb`). Elle tourne sous
  l'utilisateur `10001`, avec `kb` pour point d'entrée et `PYTHONUNBUFFERED=1`.
- **La base** : PostgreSQL 18, la version majeure d'Azure, par l'image et les réglages d'`initdb` du job
  `tests-postgresql` de la CI (`.github/workflows/ci.yml`, même digest, UTF8 et collation C, que
  `kb create-db` exige ; tenu par `test_the_base_runs_the_image_and_the_settings_of_the_ci`).
- **Les ressources** : 0,5 CPU et 1 Gio par service `kb`, la combinaison des apps en ligne
  (`infra/modules/api-container-app.bicep:154-155` ;
  [Azure Container Apps, « Allocations »](https://learn.microsoft.com/en-us/azure/container-apps/containers),
  lu le 2026-11-21) ; 1 CPU et 2 Gio pour la base, la taille du serveur en ligne, `Standard_B1ms`
  (`infra/modules/postgresql-server.bicep:21` ;
  [Azure Database for PostgreSQL, « Compute options »](https://learn.microsoft.com/en-us/azure/postgresql/compute-storage/concepts-compute),
  lu le 2026-11-22).
- **Le dossier de données** : `KB_DATA_DIR=/var/lib/knowledge_base`, sur un volume pour les seuls jobs ;
  les API n'en ont pas, comme en ligne (`infra/main.bicep:69-72`).
- **L'environnement de l'API de données** : `KB_DEPLOYMENT_ENVIRONMENT=production`, comme en ligne
  (`infra/main.bicep:296`) : elle ne sert ni `/docs` ni `/openapi.json`.
- **Le modèle** : gpt-6.1-sol, effort `low`, comme en ligne (`infra/main.bicep:325-331`).
- **L'arrêt** : 250 s pour l'API IA, comme en ligne (`infra/main.bicep:337-339`), la plus longue demande
  que laisse passer l'entrée d'Azure Container Apps, 240 s, et une marge ; une demande de fiches est
  bornée à 200 s (`DIGEST_REQUEST_TIMEOUT_SECONDS`), plus l'appel au modèle en cours. 20 s pour les
  autres services.
- **Aucun service en root** : les services `kb` sous l'utilisateur de l'image, `postgres` sous
  l'utilisateur `postgres` de son image (uid `999`) ; ports publiés sur `127.0.0.1` seulement, la base
  sur aucun.

## Les écarts voulus à la production

- **`KB_DEPLOYMENT_ENVIRONMENT=sandbox` pour l'API IA** : le seul environnement où `kb` appelle un
  service du compose en `http`, ici `http://api-donnees:8000` (`find_internal_api_url_refusal`,
  `src/k_b/core/outbound.py`). En ligne, les apps se parlent en HTTPS. En `sandbox`, l'API IA sert
  `/docs` et `/openapi.json` sans clé ([fiches-veille.md](fiches-veille.md), API9).
- **Un seul rôle, `kb`, propriétaire de la base `k_b`** : l'image de PostgreSQL le crée au premier
  démarrage (`POSTGRES_USER`, `POSTGRES_DB`) ; il se connecte par mot de passe, sur le réseau du compose,
  que `postgres` ne publie pas. La base se crée par `kb create-db`, et non par `kb migrate-database`, qui
  donne les tables aux rôles des identités d'Azure (`infra/postgresql/grant-roles.sql`), absents ici. En
  ligne, chaque identité qui ouvre la base y a son rôle, de lecture ou d'écriture, et s'y connecte par son
  jeton, en `sslmode=verify-full`.
- **Un processus d'init** (`init: true`) : il transmet le signal d'arrêt à `kb` et récupère les
  processus fils. L'arrêt essayé ici est celui de `kb` sous init : `kb serve-data` et `kb serve-ai`
  sortent en `143`, `STOPPED_BY_SIGTERM` (`src/k_b/commands/exit_codes.py`). En ligne, `kb` est le
  PID 1. Un job s'y arrête par son propre gestionnaire de SIGTERM, posé pour chaque commande de
  `COMMANDS_STOPPED_BY_SIGTERM` (`src/k_b/commands/sigterm.py`) et essayé par
  `tests/commands/test_sigterm.py`.
- **Un système de fichiers en lecture seule** (`read_only`), `/tmp` en mémoire (`tmpfs`), plus strict
  qu'en ligne, où le système de fichiers d'un conteneur s'écrit : une écriture hors du volume des
  données et de `/tmp` y échoue. La préproduction vérifie ainsi la règle 4 de
  `.claude/rules/poc.md` : un conteneur n'écrit aucun état hors de `KB_DATA_DIR`.
- **Aucune mesure ni trace vers Grafana Cloud** : `compose.yaml` ne pose pas `KB_OTLP_*`, et `kb serve-ai`
  démarre sans export (`read_metrics_export_settings_or_refusal`,
  `src/k_b/ai_api/connectors/metrics_export.py`) : les demandes de la préproduction ne se mêlent pas aux
  séries de la production.
- **Une source sans sa variable est sautée**, comme le prévoit `kb collect` : à l'essai du 2026-11-22,
  14 sources collectées sur 17 (`zotero` et `clipping`, que le poste collecte, et `gh_archive`, sans clé
  BigQuery, sautées). Le coffre et la bibliothèque Zotero ne sont pas montés.

Hors du compose : le site (`kb serve-web`), les autres jobs (`kb daily-routine`, `kb digest-watch`,
`kb smoke-test`) et le stockage d'échange.

## Prérequis

- **Docker Desktop**, avec 5 Gio de mémoire au moins (Settings → Resources) : 2 Gio pour la base, 1 Gio
  pour chaque API et pour un job. `docker info --format '{{.MemTotal}}'` la donne en octets.
- **Les ports 8000 et 8001 libres** : `lsof -nP -iTCP:8000 -iTCP:8001 -sTCP:LISTEN` ne rend aucune ligne.
  Un `kb serve-data` ou un `kb serve-ai` lancé sur le poste les tient par défaut.
- **Sur un Mac Apple Silicon** : l'image de PostgreSQL tourne en `arm64`, en natif (son index porte
  `linux/arm64/v8`) ; l'image de K-B, en `amd64`, sous émulation.

## Préparer les secrets

Chaque service lit ses secrets dans son fichier, `.env.<service>`, ignoré par git
(`git check-ignore -v .env.api-ia` rend `.gitignore:3:.env.*`) et tenu hors du contexte du build
(`.dockerignore` : `**/.env*`). Chaque fichier est la copie d'un modèle suivi par git,
`.env.<service>.example` ; les trois jobs partagent `.env.jobs`. Les copier, en `0600`, sans écraser une
copie qui existe :

```sh
for s in postgres api-donnees api-ia jobs; do cp -n .env.$s.example .env.$s && chmod 600 .env.$s; done
```

Puis les remplir dans un éditeur. Les secrets propres au compose se tirent au hasard, chacun par
`uv run python -c "import secrets; print(secrets.token_urlsafe(32))"` :

| Variable | Fichiers | Valeur |
|---|---|---|
| `POSTGRES_PASSWORD` | `.env.postgres` | le mot de passe du rôle `kb` |
| `KB_DATABASE_URL` | `.env.api-donnees`, `.env.jobs` | `postgresql://kb:<mot de passe>@postgres:5432/k_b` |
| `KB_DATA_API_KEY_TERMINAL` | `.env.api-donnees` | la clé de l'opératrice, pour les demandes depuis le poste |
| `KB_DATA_API_KEY_AI_DIGEST` | `.env.api-donnees`, `.env.api-ia` | la même valeur dans les deux fichiers : la clé de l'API IA auprès de l'API de données |
| `KB_AI_API_KEY_KB_DIGEST` | `.env.api-ia` | la clé des demandes de fiches depuis le poste |

Les autres viennent de leur service :

- `.env.api-ia` : `KB_LLM_BASE_URL` et `KB_LLM_API_KEY`, la ressource du modèle ; `KB_AI_GITHUB_TOKEN`,
  le jeton *fine-grained* des comptes rendus des tendances ([jeton-github.md](jeton-github.md)) ;
- `.env.jobs` : `KB_GITHUB_TOKEN`, facultatif (sans lui, 60 requêtes par heure à GitHub).

Le compose se lit alors sans erreur :

```sh
docker compose config --quiet; echo $?
```

Attendu : `0`, rien d'autre. Toujours avec `--quiet` : sans lui, compose affiche sa configuration
résolue, secrets compris.

## Lancer

Dans l'ordre, avec la sortie de l'essai du 2026-11-22 :

| Commande | Sortie attendue |
|---|---|
| `docker compose build` | `Image k-b:preprod Built` |
| `docker compose run --rm create-db; echo $?` | `database created: the PostgreSQL base of KB_DATABASE_URL`, puis `0` |
| `docker compose run --rm collecte; echo $?` | une ligne par source, `ok` ou `skipped` et sa raison, puis `0` ; `4` si une source échoue et qu'une autre est collectée |
| `docker compose run --rm import; echo $?` | `import: 28 raw read, 3201 written, 0 trend rows, 0 left out, 0 rejected, 0 withdrawn`, puis `0` |
| `docker compose up -d --wait --wait-timeout 180; echo $?` | `0` une fois les trois services sains |

`kb create-db` se lance une fois par volume : une base qui a déjà ses tables est refusée (code `2`).
Pour essayer sur des volumes neufs sans toucher à ceux d'un autre lancement, chaque commande prend un
nom de projet, `docker compose -p <nom> …` : l'essai a tourné sous `-p kb-essai`. Les volumes
appartiennent au projet, dont le nom est celui du dossier, ou celui de `-p` : le même compose lancé d'un
autre dossier part de volumes vides. Le tag `k-b:preprod`, lui, est commun à tous les projets : un
`docker compose build` lancé d'un autre dossier le remplace pour tous.

## Vérifier

| Commande | Sortie attendue |
|---|---|
| `docker compose ps --format '{{.Service}} {{.Status}}'` | `postgres`, `api-donnees`, `api-ia` : `Up … (healthy)` |
| `curl -fsS 127.0.0.1:8000/health; echo` et de même sur `8001` | `{"status":"ok"}` |
| `curl -sS -o /dev/null -w '%{http_code}\n' 127.0.0.1:8000/items` | `401` : pas de données sans clé ; de même `-X POST 127.0.0.1:8001/digests` |
| `docker compose exec <service> id -u` | `999` pour `postgres`, `10001` pour les deux API |
| `docker compose run --rm --no-deps --entrypoint id collecte -u` | `10001` |
| `docker compose exec postgres psql -U kb -d k_b -tAc 'SELECT count(*) FROM item'` | le nombre d'items de l'import |

Avec la clé de l'opératrice, l'API de données sert la base :

```sh
KEY=$(sed -n 's/^KB_DATA_API_KEY_TERMINAL=//p' .env.api-donnees) \
  && curl -fsS -H "Authorization: Bearer $KEY" '127.0.0.1:8000/items?limit=1' \
  | python3 -c 'import json, sys; print(json.load(sys.stdin)["total"])'
```

Attendu : le même nombre d'items. La chaîne entière, de la base au modèle, répond à une `POST /digests` :

```sh
OUT=$(mktemp -d)/digests.json \
  && KEY=$(sed -n 's/^KB_AI_API_KEY_KB_DIGEST=//p' .env.api-ia) \
  && curl -sS --max-time 240 -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
     -d '{}' -o "$OUT" -w '%{http_code} %{time_total}\n' 127.0.0.1:8001/digests \
  && echo "$OUT"
```

Attendu : `200` et sa durée, sous 200 s, puis le chemin de la réponse, dans un dossier temporaire hors du
dépôt. La demande appelle le modèle de la production : ses jetons
comptent dans la journée de sa ressource, que surveille l'alerte des 400 000 jetons sur 24 h
([infra/README.md](../infra/README.md), « L'alerte sur les jetons du modèle »).

## Arrêter

| Commande | Effet |
|---|---|
| `docker compose stop` | arrête chaque service par le signal d'arrêt de son image : SIGTERM pour les API, qui sortent en `143` ; SIGINT pour la base, son arrêt rapide, qui sort en `0` ; les conteneurs et les volumes restent |
| `docker compose down` | retire les conteneurs et le réseau, garde les volumes : `docker compose up -d` retrouve la base et le brut |
| `docker compose down -v` | retire aussi les volumes, donc la base et le brut ; il ne sert qu'à finir un essai |

## L'essai du 2026-11-22

Sur le commit `8a047e6b`, Docker Engine 29.9.2 (`arm64`), Compose 5.6.1, 7,7 Gio de mémoire, projet
`kb-essai` sur des volumes neufs, avec la clé du modèle de la production :

| Étape | Mesure |
|---|---|
| `build`, sans cache de build | `0`, 17,2 s ; image `amd64`, utilisateur `10001:10001` |
| `create-db` | `0`, 6 s, démarrage de `postgres` compris |
| `collecte`, volume neuf | 14 sources `ok`, 3 `skipped` (`zotero`, `clipping`, `gh_archive`), 1 min 35 s |
| `import` | `0`, 3 s : 28 fichiers bruts lus, 3 201 items écrits, 0 rejeté |
| `collecte`, second passage | `0`, 26 s : la collecte est incrémentale, aucun fichier brut nouveau hors des deux tops et d'arXiv, un chacun |
| `up -d --wait` | `0`, les trois services sains en 11 s |
| `/health` sur 8000 et 8001 | `{"status":"ok"}` ; sans clé, `401` sur `/items` et sur `POST /digests` |
| `id -u` | `999` (`postgres`), `10001` (`api-donnees`, `api-ia`, `collecte`) |
| items, par `psql` et par l'API | 3 201 et 3 201 |
| `POST /digests` | `200` en 32,9 s : gpt-6.1-sol, 75 items sur 3 jours, 9 sujets, aucun en échec |
| `stop` | `0`, 0,83 s ; les API en `143`, la base en `0` |
| `down`, puis `up -d --wait` | `0` et `0`, sains en 14 s, `down` compris ; 3 201 items |
| journaux, après le redémarrage | 27 lignes ; aucune ne porte `postgresql://`, `Bearer `, `github_pat_` ni `password=` ; aucune en `WARNING`, `ERROR` ou `CRITICAL` |
| `git check-ignore -v` des quatre fichiers | quatre lignes `.gitignore:3:.env.*` |
| `git ls-files '.env.*.example'` | les quatre modèles, et `.env.e2e_test.example` |
| `down -v` | `0` ; aucun conteneur ni volume de `kb-essai` ne reste |

## Ce que le test vérifie sans Docker

`tests/test_compose_file.py` lit `compose.yaml`, ses modèles, le `Dockerfile` et `.gitignore` à chaque
`uv run pytest`, donc à chaque PR : les six services ; les ports sur `127.0.0.1`, aucun pour la base ;
`init`, `read_only` et `tmpfs: /tmp` partout ; 0,5 CPU et 1 Gio par service `kb`, 1 CPU et 2 Gio pour la
base ; l'arrêt sous 30 s, sauf les 250 s de l'API IA ; aucun service en root, l'utilisateur du `Dockerfile`
compris ; l'image et les réglages d'`initdb` de la base de la CI ; `sandbox` pour la seule API IA ; un
fichier de secrets par service, à côté de son modèle ; aucun secret dans `compose.yaml`, ni par son nom ni
dans une URL, et aucune valeur dans un modèle ; chaque variable des modèles des services `kb` décrite
dans `.env.example` ; les fichiers de secrets ignorés, puis leurs modèles suivis ; le profil `jobs` des
seuls jobs ; le volume des données pour les seuls jobs ; les sondes de santé, celle de la base en TCP et
celle de l'API de données avec un hôte qu'elle permet ; l'ordre de démarrage.

Le compose n'a pas de job de CI : le test tient ses règles à chaque PR, et l'essai ci-dessus prouve le
lancement.
