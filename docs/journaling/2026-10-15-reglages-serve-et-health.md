# Régler `kb serve` par variables d'environnement, et servir `/health` sans clé

- **Date** : 2026-10-15
- **Branche** : `feat/serve-settings-and-health`
- **Issue** : #199
- **Fichiers principaux** : `src/k_b/cli.py`, `src/k_b/core/config.py`, `src/k_b/data_api/app.py`,
  `src/k_b/data_api/health.py`, `src/k_b/data_api/request_log.py`
- **Série** : suit [Servir la liste par une API locale](2026-10-14-servir-la-liste-par-une-api-locale.md)
  (la clé, `TrustedHostMiddleware`) et
  [Journaux horodatés et fichier de journal](2026-10-14-journaux-horodates-et-fichier-de-journal.md)
  (`logging_to`).

## 1. Le pourquoi

Le 25/10, K-B tourne en conteneurs Docker, et doit passer sur Azure Container Apps (ACA) au 08/11
sans refonte (journal ADR, 2026-10-15, « POC du 25/10 », décision 1). Avant cette PR, l'API de
données ne pouvait pas tourner dans un conteneur :

- elle écoutait sur `127.0.0.1`, en dur (`cli.py:80` avant la PR). Dans un conteneur, cette adresse
  est celle **du conteneur lui-même** : ni la machine ni un autre conteneur ne la joignent ;
- elle n'acceptait que les en-têtes `Host` `127.0.0.1` et `localhost` (`app.py:18` avant la PR).
  L'API IA, qui l'appellera par son nom de service (`http://api-donnees:8000`), aurait reçu un
  400 ;
- un conteneur a besoin d'une sonde de santé, et toute route demandait la clé ;
- le journal allait toujours dans un fichier du dossier de données, alors qu'en conteneur, la
  sortie d'erreur **est** le journal (`docker compose logs`, puis Log Analytics sur ACA).

La PR rend ces quatre réglages lisibles dans l'environnement, garde des défauts locaux, refuse au
démarrage toute valeur dangereuse ou injoignable, et ajoute `GET /health`.

## 2. Le comment

### 2.1 Un défaut nommé, une variable qui le change

La règle 2 de `.claude/rules/poc.md` exige que tout réglage de déploiement ait un défaut local
nommé dans `core/config.py`, et nulle part ailleurs :

```python
DATA_API_HOST = "127.0.0.1"
DATA_API_PORT = 8000
DATA_API_ALLOWED_HOSTS = ("127.0.0.1", "localhost")
```
(`src/k_b/core/config.py:36-38`)

`cli.py` lit la variable et retombe sur le défaut si elle manque. Une variable **posée mais vide**
n'est pas une variable absente : elle est vérifiée, donc refusée. `read_serve_settings`
(`cli.py:374`) lit les trois réglages de l'API, les vérifie, puis rend un `ServeSettings` ou
`None` après avoir journalisé le refus. `run_serve` sort en code 2 sur la ligne qui existait déjà
pour les clés :

```python
    if api_keys is None or settings is None:
        return 2
```
(`src/k_b/cli.py:356-357`)

Ce n'est pas un détail : la règle 6 de `poc.md` interdit d'ajouter un code de sortie écrit en
chiffres (le compte reste 17 ; #193 les nommera). Les refus réutilisent donc les lignes en place.

### 2.2 L'hôte d'écoute : une adresse IPv4, rien d'autre

```python
    try:
        ipaddress.IPv4Address(host)
    except ValueError:
        return f"{DATA_API_HOST_VARIABLE}: {quote_value(host)} not an IPv4 address"
```
(`src/k_b/cli.py:401-404`)

Un type fermé à la frontière (`code.md`, « Sécurité dès la conception ») ferme trois cas d'un coup :

- la valeur vide, qu'uvicorn lierait à **toutes** les interfaces (comportement de `bind("")` des
  sockets) ;
- un nom (`api-donnees`), que seul uvicorn refuserait, après le démarrage, en code 3 ;
- une IPv6 (`::1`) : le `Host` envoyé par un client IPv6 garde ses crochets (`[::1]`), et le motif
  des hôtes permis ne peut pas les écrire. Le réglage serait accepté mais injoignable. Constat de
  `/code-review`, tranché par time-knight (délégation de Sabine du 15/10) : un refus fermé vaut
  mieux.

En conteneur, l'hôte sera `0.0.0.0` (toutes les interfaces **du conteneur**) ; c'est la
publication du port qui le limitera à `127.0.0.1` de la machine (#200).

Le port, lui, passe par `PORT_DIGITS = re.compile(r"[0-9]{1,5}")` (`cli.py:95`) avant la borne
1-65535 : `int()` accepterait `" 8000"`, `"+8000"` ou `"8_000"`.

### 2.3 Les hôtes permis : ce que protège la liste, et pourquoi `*` est refusé

`TrustedHostMiddleware` compare l'en-tête `Host` de chaque requête à une liste, et répond 400 à
tout autre hôte, avant l'app. C'est une défense contre les attaques par en-tête `Host` (la doc de
Starlette le dit), et une ligne de l'exigence OWASP API8:2023 (« Security Misconfiguration ») :
l'API ne répond qu'aux noms sous lesquels on l'a déployée.

Avec `["*"]`, Starlette met `allow_any` à vrai et ne regarde plus rien
(`starlette/middleware/trustedhost.py`, 1.8.0). Un `*` dans la variable désactiverait donc le
contrôle sans bruit. D'où un motif fermé pour chaque entrée :

```python
ALLOWED_HOST = re.compile(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?")
```
(`src/k_b/cli.py:100`)

et quatre refus nommés, dans l'ordre de `find_allowed_hosts_refusal` (`cli.py:422-436`) :
- valeur vide → `empty, set the hosts separated by commas` ;
- entrée vide (`localhost,`) → `entry 2 of 2 empty` ;
- entrée avec `*` → `entry 1 of 1 '*' with '*', name each host` ;
- autre entrée hors motif (majuscule, port, espace, retour à la ligne) → `not a lowercase host name`.

**Pas de mise en minuscules** : Starlette compare le `Host` tel quel, et `urllib` garde la casse de
l'URL. Transformer `API-Donnees` en `api-donnees` ferait dire à la liste autre chose que ce qui
est écrit, sans rendre joignable un client qui envoie des majuscules. Le motif a un second
avantage : une entrée acceptée n'a rien à échapper, si bien que la ligne
`API allowed hosts: api-donnees, localhost` du démarrage ne peut pas injecter une fausse ligne de
journal.

La liste est découpée **une seule fois** (`cli.py:380-385`), et c'est ce tuple qui est vérifié puis
servi : la liste vérifiée est celle qui est servie (constat 6 de `/code-review`).

### 2.4 `/health` : sans clé, sans affaiblir la clé

La clé est posée **sur l'app**, pas sur les routeurs :

```python
        dependencies=[Depends(check_api_key)],
```
(`src/k_b/data_api/app.py:36`)

FastAPI applique une dépendance de l'app à chaque *path operation* (doc « Global Dependencies »),
donc à toute route de données présente ou future. `/health` est ajoutée autrement :

```python
    app.add_route(HEALTH_PATH, answer_health, methods=["GET"], include_in_schema=False)
```
(`src/k_b/data_api/app.py:55`)

`add_route` crée une `Route` de Starlette, pas une *path operation* : c'est exactement ainsi que
FastAPI ajoute `/docs` et `/openapi.json` (`fastapi/applications.py`, 0.143.1). La clé n'y est pas
appliquée, et elle reste sur tout le reste.

`/health` ne dit **rien** d'autre que `ok` :

```python
async def answer_health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})
```
(`src/k_b/data_api/health.py:13-14`)

Ni version (un attaquant y lirait les failles connues de la version), ni chemin, ni état de la
base. C'est une sonde de **vivacité** (le processus répond), pas de disponibilité : une sonde qui
ouvrirait la base ferait redémarrer le conteneur en boucle tant que la base n'est pas créée.
`/health` passe toujours par `TrustedHostMiddleware` : la sonde doit envoyer un hôte permis.

Un test parcourt toutes les routes de l'app et vérifie que seules `/docs`, `/openapi.json` et
`/health` répondent sans clé (`tests/data_api/test_api_keys.py:43`). Le piège : `app.routes` ne
contient pas les routes des routeurs inclus (des `_IncludedRouter` sans chemin), si bien qu'un
parcours naïf passerait à vide. Le test lit donc les routes par `iter_route_contexts`, le parcours
dont FastAPI se sert pour son OpenAPI (`test_api_keys.py:21`), et un autre test fige la liste
attendue : si FastAPI change ce parcours, le test échoue au lieu de passer sans rien tester.

### 2.5 Le journal : un `/health` réussi n'écrit rien

```python
        if not (request.url.path == HEALTH_PATH and status_code == 200):
```
(`src/k_b/data_api/request_log.py:33`)

Une sonde toutes les 10 s écrirait ≈ 8 640 lignes par jour, noierait les requêtes des clients et,
au 08/11, coûterait dans Log Analytics, facturé au volume. Une sonde qui **échoue** (400 d'un
`Host` non permis, 405) garde sa ligne : une sonde mal réglée se voit. Constat 3 de
`/code-review`, tranché par time-knight.

`KB_LOG_TO_FILE=false` retire le fichier de journal, pour toutes les commandes : `logging_to`
garde la sortie d'erreur et n'ajoute le `TimedRotatingFileHandler` que si un chemin est donné.
Une valeur autre que `true` ou `false` est refusée par un `print` (`read_log_to_file`,
`cli.py:229`), car le journal n'est pas encore ouvert : on lit justement son réglage.

## 3. Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Préfixe `KB_DATA_API_` pour l'hôte, le port et les hôtes permis | vocabulaire du code (`DATA_API_HOST`) et de la doc ; `KB_DATA_API_ALLOWED_HOSTS` est le choix de Sabine, au lieu de `KB_ALLOWED_HOSTS` de l'issue | `KB_HOST`/`KB_PORT` : ambigus dès que l'API IA tourne sur la même machine ; `KB_SERVE_HOST` : nomme la commande, pas ce qu'on règle |
| Hôte : IPv4 seulement | refus fermé du vide, d'un nom et d'une IPv6 injoignable | accepter toute IP (IPv6 acceptée mais jamais joignable) ; un hôte libre (code 3 au `bind`, trop tard) |
| Hôtes permis : motif fermé, `*` et joker refusés, pas de minuscules | `*` désactive le contrôle ; un joker ne sert à aucun service nommé ; ce qui est écrit est ce qui est servi | mettre en minuscules ; refuser `*` seul ; refuser seulement l'entrée avec port (signalé, pas codé : remplacé par le motif) |
| `/health` par `add_route`, hors OpenAPI | la clé reste sur l'app : aucune route de données ne peut l'oublier | la clé sur chaque routeur (un routeur ajouté plus tard pourrait l'oublier) ; un sous-app monté (une couche de plus) |
| `/health` sonde de vivacité, corps `{"status": "ok"}` | rien qui révèle l'intérieur ; pas de redémarrage en boucle | ouvrir la base (disponibilité) |
| Un `/health` en 200 n'est pas journalisé | minimisation (RGESN), coût de Log Analytics ; un échec reste visible | tout journaliser en écrivant la limite |
| `/health` reste derrière le filtre d'hôte | ne pas affaiblir un contrôle pour une sonde qui n'existe pas encore ; au 25/10, le healthcheck compose choisit son `Host` (#200) | servir `/health` avant le filtre (constat 1, écarté par time-knight ; à revoir au 08/11 avec la sonde ACA) |
| `KB_LOG_TO_FILE`, `true` ou `false` | en conteneur, la sortie d'erreur est le journal (règle 4 de `poc.md`) | un chemin de fichier réglable (tout état sous `KB_DATA_DIR`) |
| La lecture dans `cli.py`, à côté de `read_api_keys` | même niveau que la lecture des clés | un module `serve_settings.py` pour ~60 lignes |
| Aucun nouveau `return 2` | règle 6 de `poc.md` (compte de 17) ; #193 nomme les codes | une constante de code de sortie (le travail de #193) |
| Un seul `kb serve` par `KB_DATA_DIR`, écrit, pas codé | le port réglable lève la garantie du `bind` (ADR « Journaux », révisée) ; compose lance un conteneur par service | un verrou (code pour plus tard) |
| Version 0.3.0 | une route nouvelle visible d'un client (`docs/specs-api.md`, version) | 0.2.1 (une correction ne change pas ce qu'un client voit) |

## 4. Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_serve_listens_on_127_0_0_1_8000_by_default_without_uvicorn_logging_config` | sans variable, l'écoute reste locale ; uvicorn sans sa propre config de journal |
| `test_serve_listens_on_the_host_and_port_of_the_environment` | l'hôte et le port des variables arrivent à uvicorn |
| `test_serve_exits_2_on_a_host_or_port_refused` (10 cas, dont `""`, `::1`, `api-donnees`, `+8000`, `65536`) | chaque valeur refusée sort en 2, avec son message, sans lancer uvicorn |
| `test_serve_exits_2_and_names_the_allowed_hosts_refused` (9 cas, dont `*`, `localhost,`, `API-donnees`, `localhost:8000`, un retour à la ligne) | chaque refus de la liste, avec sa position, la valeur échappée |
| `test_serve_allows_the_hosts_of_the_environment_and_no_other` | `api-donnees` reçoit 200, un autre hôte 400, sur l'app que reçoit uvicorn |
| `test_serve_reads_the_base_and_writes_its_own_log_file_under_kb_data_dir`, `tests/test_cli.py:70-77` | la base, le journal et l'état de collecte suivent `KB_DATA_DIR` |
| `test_without_log_file_kb_logs_on_stderr_only`, `test_a_log_to_file_value_refused_exits_2` | sans fichier, aucun dossier `logs/` ; une valeur fausse sort en 2 |
| `test_health_answers_ok_without_key`, `test_health_refuses_another_method_with_405`, `test_a_host_other_than_the_allowed_ones_gives_400_on_health` | `/health` : 200 sans clé, rien d'autre que `ok`, GET seulement, filtre d'hôte |
| `test_the_routes_are_listed`, `test_only_the_public_routes_answer_without_a_key`, `test_every_data_route_refuses_a_missing_and_a_wrong_key_with_the_same_body` | seules les trois routes publiques répondent sans clé ; le parcours des routes ne peut pas passer à vide |
| `test_a_health_check_that_answers_200_is_not_logged`, `test_a_health_check_that_fails_is_logged_by_its_path` | une sonde réussie n'écrit rien, une sonde qui échoue écrit sa ligne |
| `kb serve` réel, base d'essai : `curl /health` → 200 ; `/items` sans clé → 401 ; `Host: evil.example` → 400 ; `KB_DATA_API_ALLOWED_HOSTS='*'` → code 2 ; `KB_DATA_API_HOST=::1` → code 2 ; port 8765 avec `api-donnees` permis → 200, `127.0.0.1:8000` ne répond plus | le comportement tient hors des tests, sur un vrai socket |
| `uv run pytest` (1265), `ruff check`, `ruff format --check`, `mypy --strict` | contrôles du dépôt verts |

## 5. Ce que tu dois pouvoir défendre

1. **Pourquoi l'API n'écoute-t-elle pas sur `0.0.0.0` par défaut, puisque le conteneur en a
   besoin ?** Parce que sur la machine de Sabine, `0.0.0.0` exposerait l'API au réseau local. Le
   défaut est sûr (`127.0.0.1`), et le conteneur pose `KB_DATA_API_HOST=0.0.0.0` exprès ; c'est la
   publication du port sur `127.0.0.1` de la machine (#200) qui limite l'accès.
2. **`/health` sans clé, n'est-ce pas une faille ?** Non : il ne sert aucune donnée, ne dit ni
   version, ni chemin, ni état de la base, n'accepte que GET, et passe par le filtre d'hôte. La clé
   reste posée sur l'app (`app.py:36`) ; un test vérifie que seules trois routes, nommées,
   répondent sans clé (`test_api_keys.py:43`).
3. **Que se passe-t-il si quelqu'un met `*` dans les hôtes permis ?** `kb serve` refuse de
   démarrer (code 2, `entry 1 of 1 '*' with '*', name each host`). Sinon, Starlette désactiverait
   le contrôle (`allow_any`) et l'API répondrait à n'importe quel `Host`.
4. **Pourquoi un conteneur ne joint-il pas le `127.0.0.1` d'un autre ?** Chaque conteneur a son
   propre espace réseau, avec sa propre interface de bouclage : `127.0.0.1` y désigne le conteneur
   lui-même. Un autre conteneur le joint par son nom de service sur le réseau compose, d'où
   `api-donnees` dans les hôtes permis.
5. **Pourquoi ne pas journaliser `/health` ?** Une sonde réussie n'apprend rien et se répète des
   milliers de fois par jour ; une sonde qui échoue est journalisée, car c'est elle qui signale une
   mauvaise configuration.

## 6. Zones non vérifiées

- **La sonde d'ACA et son `Host`** : on lit qu'une sonde `httpGet` de Kubernetes envoie par défaut
  l'IP du pod comme `Host`. Ce n'est pas vérifié pour ACA. La doc d'ACA dit qu'une sonde `httpGet`
  accepte des en-têtes : la réponse prévue au 08/11 est une sonde qui porte un `Host` permis.
  Signalé pour le 08/11.
- **`iter_route_contexts`** n'est pas documentée par FastAPI ; le test qui en dépend échoue (et ne
  passe pas à vide) si elle change, mais une montée de FastAPI pourra demander de le réécrire.
- **La démonstration réelle** n'a pas écouté sur `0.0.0.0` (le réseau local de la machine aurait
  été exposé, même brièvement) : l'hôte changé a été montré sur `::1` avant la correction IPv4,
  puis le port changé sur `127.0.0.1:8765`. L'écoute sur `0.0.0.0` sera vue en conteneur (#200).
- **Le `bind("")` sur toutes les interfaces** est le comportement connu des sockets, repris de la
  relecture ; il n'a pas été observé ici, puisque la valeur vide est refusée avant.

## 7. Ce qui reste

- Dockerfile, compose, healthcheck avec un `Host` permis, publication du port sur `127.0.0.1` :
  #200.
- Codes de sortie nommés et arrêt sur SIGTERM : #193.
- La sonde ACA et TLS (l'entrée HTTPS d'ACA) : au 08/11 ; la ligne API8 est « tenue en partie »
  d'ici là.
- Un `print` sans date pour les erreurs d'avant l'ouverture du journal (`read_data_dir`,
  `read_log_to_file`) : motif existant, signalé sans issue.

## Sources

- [Global Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/global-dependencies/) —
  FastAPI, lu par Context7 le 2026-10-15 : une dépendance de l'app s'applique à toutes les *path
  operations*.
- [Middleware, `TrustedHostMiddleware`](https://www.starlette.io/middleware/#trustedhostmiddleware)
  — Starlette, lu par Context7 le 2026-10-15 : `["*"]` permet tout hôte ; un `Host` non permis
  reçoit un 400 ; défense contre les attaques par en-tête `Host`.
- [API8:2023 Security Misconfiguration](https://owasp.org/API-Security/editions/2023/en/0xa8-security-misconfiguration/)
  — OWASP, relevé par recherche web le 2026-10-15 : TLS même en interne, seules les méthodes
  utiles, erreurs sans détail interne.
- [Port publishing and mapping](https://docs.docker.com/engine/network/port-publishing/) et
  [Networking overview](https://docs.docker.com/engine/network/) — Docker, relevés par recherche
  web le 2026-10-15 : un conteneur a son propre espace réseau, et `127.0.0.1` y désigne le
  conteneur ; un port publié sur `127.0.0.1` n'est joignable que de la machine.
- [Networking in Compose](https://docs.docker.com/compose/how-tos/networking/) — Docker, relevé
  par recherche web le 2026-10-15 : les services d'un compose se joignent par leur nom.
- [Health probes in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/health-probes)
  — Microsoft, relevé par recherche web le 2026-10-15 : sondes de démarrage, de vivacité et de
  disponibilité ; une sonde `httpGet` prend un chemin, un port et des en-têtes.
- [Manage environment variables on Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/environment-variables)
  — Microsoft, relevé par recherche web le 2026-10-15 : un conteneur ACA se règle par ses
  variables d'environnement, une valeur secrète par référence à un secret.
- Code installé, lu le 2026-10-15 : `starlette/middleware/trustedhost.py` (1.8.0, `allow_any`,
  comparaison sans mise en minuscules), `fastapi/applications.py` et `fastapi/routing.py` (0.143.1,
  `add_route`, `iter_route_contexts`), `uvicorn/server.py` (0.54.0, code 3 au `bind` manqué).
