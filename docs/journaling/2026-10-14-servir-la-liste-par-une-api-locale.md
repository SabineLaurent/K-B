# Servir la liste des items par une API locale fermée par une clé par client

- **Date** : 2026-10-14
- **Branche** : `feat/data-api-item-list`
- **Issue** : #184 (critère corrigé par deux commentaires datés du 2026-10-14)
- **Fichiers principaux** : `src/k_b/data_api/` (`app.py`, `dependencies.py`, `errors.py`,
  `request_log.py`, `routers/item_router.py`, `schemas/item_schema.py`), `src/k_b/cli.py`
  (`kb serve`, `kb openapi`), `docs/api/openapi-donnees.json`, `docs/specs-api.md`
- **Série** : suit [la lecture en lecture seule](2026-10-14-lire-les-items-en-lecture-seule.md)
  (#183, la requête que l'API appelle) et [les journaux horodatés](2026-10-14-journaux-horodates-et-fichier-de-journal.md)
  (#134, le format de chaque ligne).

## 1. Le pourquoi

K-B range la veille dans une base SQLite. Jusqu'ici, la lire demandait d'ouvrir la base. Une
**API locale** sert ce contenu par HTTP, sur la machine de Sabine seulement (`127.0.0.1`) :
un script, le terminal, un agent ou la future API IA demandent `GET /items` et reçoivent du
JSON, sans connaître le schéma de la base ni pouvoir y écrire.

Pourquoi **une clé par client** plutôt qu'une seule : chaque programme qui appelle a un nom
(`TERMINAL`, `AGENT`…). Le journal dit qui a appelé, et l'on retire un client en retirant sa
variable, sans toucher aux autres (décision de Sabine du 2026-10-14, journal ADR). La clé
authentifie un *programme*, pas une personne : c'est l'usage qu'OWASP admet pour une clé d'API.

Cette PR sert la liste et « quoi de neuf » (`GET /items`). Le détail d'un item et les tendances
viennent avec #185.

## 2. Le comment

### 2.1 Un dossier par rôle : l'organisation apprise en DWWM

```
src/k_b/data_api/
├── app.py            create_app : rassemble la clé, les erreurs, le journal et les routers
├── dependencies.py   ce que les routes reçoivent : le client de la clé, la connexion
├── errors.py         chaque erreur devient un état nommé, écrit une fois
├── request_log.py    une ligne de journal par requête
├── routers/item_router.py    la route GET /items et les bornes de ses paramètres
└── schemas/item_schema.py    les modèles de la réponse (liste blanche des champs)
```

Ce qui est où se lit d'un coup d'œil, et l'API IA pourra reprendre le même plan. En FastAPI, la
fonction de route *est* le contrôleur : un dossier `controllers/` ne ferait que passer l'appel à
`database/reading.py` (ADR, « Paquet `src/k_b/data_api/` »). Les couches restent dans un seul
sens : `data_api` n'importe que `database`, `items` et `core`, jamais `etl` ni
`database.writers`. Un test le vérifie (`tests/test_module_dependencies.py`).

### 2.2 `create_app` : une app par appel, la clé posée sur l'app

`src/k_b/data_api/app.py:24-30`

```python
app = FastAPI(
    title="K-B data API",
    version=API_VERSION,
    # On the app, not on a router: no data route can leave it out. […]
    dependencies=[Depends(check_api_key)],
```

- La vérification de la clé est une **dépendance de l'app**. FastAPI l'ajoute en tête de chaque
  route qu'on lui donne, y compris une route écrite plus tard : aucune ne peut l'oublier.
- `/docs` et `/openapi.json` sont des routes que FastAPI ajoute lui-même, hors de ces
  dépendances. Elles restent publiques et ne contiennent aucune donnée.
- `create_app` reçoit le chemin de la base et les clés au lieu de les lire dans l'environnement.
  Un test crée ainsi sa propre app, avec ses propres clés. Le cas « clé retirée » se teste en
  recréant l'app sans cette clé.

Les middlewares s'emboîtent **dans l'ordre inverse de leur ajout** (`app.py:39-44`) : le dernier
ajouté est le plus extérieur. `log_request` est donc ajouté en dernier, pour voir passer toutes
les réponses, même le 400 de `TrustedHostMiddleware` et le 500 d'une erreur imprévue.

### 2.3 Comment FastAPI enchaîne dépendances, validation et réponse

Pour `GET /items`, FastAPI résout **d'abord les dépendances, dans l'ordre**, puis valide les
paramètres de requête. On l'a lu dans le code installé :
`fastapi/dependencies/utils.py:619-690`, la boucle `for sub_dependant in
dependant.dependencies` vient avant `request_params_to_args(dependant.query_params, …)`.
Dans l'ordre :

1. `check_api_key` (dépendance de l'app). Sans clé valide, elle lève `ApiError(401)` et rien
   d'autre ne se fait.
2. `open_database` (dépendance `yield`, `dependencies.py:50-56`) ouvre une connexion en lecture
   seule, que la route reçoit, puis la ferme dans le `finally`.
3. La validation des paramètres, par les types de la signature
   (`routers/item_router.py:46-53`). Une erreur devient `RequestValidationError`, puis un 422.
4. La route appelle `read_items` (#183). Son type de retour, `ItemPageSchema`, filtre et
   sérialise la réponse.

Conséquences assumées, chacune testée :
- sans clé, un paramètre faux rend **401**, pas 422 : un appelant inconnu n'apprend rien du
  contrat ;
- avec une clé, sans base, un paramètre faux rend **503**.

La validation de `since` (`item_router.py:36-40`) :

```python
Since = Annotated[
    UtcDatetime,
    BeforeValidator(read_since_text),
    AfterValidator(check_since_can_be_read),
]
```

- `read_since_text` passe le texte à `parse_aware_datetime`, la fonction de date du projet
  (règle 4). Laissé à pydantic, un nombre comme `since=20261007` serait lu comme une date Unix
  (le 23/08/1970) : c'est le constat de la seconde revue.
- `check_since_can_be_read` refuse une date qui, arrondie à la seconde supérieure, sortirait du
  calendrier (`9999-12-31T23:59:59.5Z`). Sans ce contrôle, la requête finirait en 500.
- Le type reste `UtcDatetime` : l'OpenAPI déclare toujours `since` en `string`,
  `format: date-time`.

### 2.4 La clé : temps constant, même 401

`src/k_b/data_api/dependencies.py:42-47`

```python
received = received_key.encode()
client_name = None
for name, key in api_keys.items():
    if hmac.compare_digest(received, key.get_secret_value().encode()):
        client_name = name
return client_name
```

- `hmac.compare_digest` compare en temps constant : la durée de la réponse ne dit pas combien
  de caractères du début étaient justes, ce qu'un `==` dévoilerait.
- La boucle **ne s'arrête pas** à la clé qui correspond. Toutes les clés sont comparées, et le
  temps ne dit pas laquelle a répondu.
- Les deux côtés sont convertis en `bytes`, parce que `compare_digest` lève une `TypeError` sur
  un `str` non ASCII. Une clé reçue `clé` rendrait sinon un 500 ; elle rend 401 (testé).
- `HTTPBearer(auto_error=False)` rend `None` dans trois cas : sans en-tête, avec un schéma autre
  que `Bearer`, ou avec un en-tête vide. Ces trois cas et la clé inconnue mènent au même
  `ApiError(401, "invalid_api_key")`, au même corps et au même `WWW-Authenticate: Bearer`.
- Les clés sont gardées en `SecretStr` : un `repr` ou un journal accidentel affiche `**********`.

Au démarrage, `kb serve` lit les variables `KB_API_KEY_<CLIENT>`. `find_api_key_refusal`
(`cli.py:338-357`) refuse, en code 2 :
- un nom de client hors `[A-Z0-9_]+` ;
- une clé de moins de 32 caractères ;
- une clé hors de l'alphabet de `token_urlsafe` : `HTTPBearer` retire les espaces autour de la
  clé reçue, donc une clé qui en porte ne serait jamais reconnue ;
- deux clients qui ont la même clé.

Le message nomme la variable, citée par `quote_value`, jamais sa valeur.

### 2.5 Les erreurs : un état nommé, rien d'interne

`errors.py` fait de chaque erreur un corps `{"error": "<état>"}` :
- `invalid_parameter` donne aussi la liste des **noms** refusés, tirée de `loc`, jamais la
  valeur (`errors.py:63-70`) ;
- `database_error` est journalisé par le seul type de l'exception, parce que le message de
  SQLite peut contenir un chemin.

Le cas particulier, `errors.py:94-107` :

```python
try:
    return await call_next(request)
except Exception as error:  # noqa: BLE001 — every exception no handler takes
    logger.error("internal_error: %s", type(error).__name__)
    return respond_with_error(500, "internal_error")
```

Pourquoi un middleware, et pas un gestionnaire de `Exception` ? Après un tel gestionnaire,
Starlette **relance toujours** l'exception (`starlette/middleware/errors.py:183-186`), et uvicorn
écrirait alors la pile, avec un message qui peut citer une valeur reçue. Le middleware rattrape
l'exception avant : une ligne avec le type seul, et une réponse JSON nommée.

### 2.6 Le journal de chaque requête, dans un fichier à part

`request_log.py` écrit une ligne par requête :

```
2026-10-14T17:24:20Z INFO k_b.data_api.request_log: request method='GET' route=/items status=200 duration_ms=2 client=DEMO
```

- `route` est le **gabarit** (`scope["route"].path`), jamais le chemin reçu. Un chemin inconnu
  donne `-`, et un chemin secret ne finit pas au journal.
- La méthode est la seule valeur reçue de la ligne. Elle passe par `quote_value` (règle 3).
- `status=-` veut dire « aucune réponse envoyée » (client parti, serveur arrêté), pour ne pas
  inventer un 500.
- Pour `/docs` et `/openapi.json`, FastAPI 0.143 ne met pas la route dans le scope
  (`fastapi/routing.py:1840-1847`). `find_route_template` les nomme par le chemin que l'app
  leur donne (`request_log.py:42-53`).

La ligne va dans `logs/kb-serve.log`, pas dans `kb.log` (`cli.py:65`).
`TimedRotatingFileHandler.doRollover` (Python 3.13, `logging/handlers.py:448-450`) ne fait rien
si le fichier daté existe déjà, et ne recalcule pas sa prochaine rotation. Si `kb collect` fait
la rotation de minuit, un `kb serve` qui tourne depuis la veille continuerait d'écrire dans
`kb.log.<veille>`. Un fichier par processus long évite ce partage.

## 3. Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| `data_api/` par rôle : `routers/`, `schemas/` | décision de Sabine (organisation apprise en DWWM), ADR du 2026-10-14 | `routes.py` et `responses.py` à plat : moins lisibles quand l'API grandit ; `controllers/` : la route est déjà le contrôleur |
| Clé en dépendance **de l'app** | aucune route ne peut l'oublier (critère) | sur chaque router : une route oubliée serait ouverte |
| 401 avant 422 | un appelant inconnu n'apprend rien du contrat | 422 d'abord : dévoile les paramètres |
| `next_offset` nul au-delà de 10 000 | la page suivante n'est pas demandable (422) | rendre 10 100 : renvoie le client sur un 422 ; un champ `truncated` : un champ de plus pour un cas qu'un filtre règle |
| `logs/kb-serve.log` à part | `kb serve` est le seul processus long (décision de Sabine) | même fichier, limite écrite : lignes sous la mauvaise date ; rotation externe : défait #134 |
| Contrôle des clés dans `cli.py` | il lit l'environnement comme `KB_DATA_DIR` (critère) ; l'app reste recréable par un test | lire l'environnement dans `data_api` |
| Port 8000 en constante | le critère ne demande pas d'option ; un seul `kb serve` à la fois | `--port` : un second `kb serve` écrirait le même fichier |
| Types de `items.py` pour `q` et `since` | règle 4 : un type défini une fois | recomposer les contrôles dans le router |
| 500 imprévu rattrapé par un middleware | Starlette relance l'exception après un gestionnaire | un gestionnaire `Exception` : la pile irait quand même au journal |
| `redirect_slashes=False`, `redoc_url=None`, `swagger_ui_oauth2_redirect_url=None` | `/items/` doit rendre 404 ; rien de public hors `/docs` et `/openapi.json` | les défauts de FastAPI : un 307 et deux pages de plus |
| `httpx2` pour le client de test | Starlette 1.8 déprécie `httpx` (décision de Sabine, critère corrigé) | `httpx` : un avertissement de dépréciation à chaque test |
| `kb openapi` écrit dans `docs/api/` du dossier courant, et refuse si ce dossier manque | même chemin sur toute machine ; ailleurs, il n'écrit rien | un chemin tiré du paquet : faux hors installation éditable |
| `.claude/skills/fastapi` committé (lien relatif), `.agents/` et les copies de `library-skills` supprimées | décision de Sabine : seul l'exemplaire lu par Claude Code sert | committer tout : un exemplaire pour des agents non utilisés |

## 4. Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_every_data_route_refuses_a_missing_and_a_wrong_key_with_the_same_body` | toute route documentée rend le même 401, sans clé, avec une fausse clé, avec `Basic` ou un `Bearer` vide |
| `test_each_client_is_served_with_its_key`, `test_a_removed_key_gives_401_and_the_other_clients_are_still_served` | une clé par client ; un retrait n'affecte que son client |
| `test_a_non_ascii_key_gives_401_not_500` | les `bytes` évitent la `TypeError` de `compare_digest` |
| `test_without_a_key_a_wrong_parameter_gives_401` | l'ordre 401 avant 422 |
| `test_a_parameter_out_of_bounds_gives_422_with_its_name_only` (14 cas, dont `since=20261007`) | les bornes de la spec, et un corps sans la valeur reçue |
| `test_the_list_serves_only_the_six_fields` | API3 : six clés exactes ; ni surlignage, ni auteur, ni résumé, ni `raw_file_path`, ni `collected_at` |
| `test_next_offset_stops_at_the_offset_bound` | 9 980 + 20 → 10 000 ; 10 000 + 100 → nul |
| `test_an_unexpected_error_gives_500_internal_error_and_logs_its_type_only` | 500 nommé, type au journal, ni message ni `Traceback` |
| `test_a_request_line_names_the_client_never_the_key_a_value_or_the_path` | la ligne de journal nomme le client, sans clé, valeur ni chemin |
| `test_serve_exits_2_and_names_the_variable_without_its_value` (6 cas) et `…_same_key` | les refus de démarrage, sans valeur citée |
| `test_serve_writes_its_own_log_file` | `kb-serve.log` écrit, `kb.log` absent |
| `test_the_versioned_openapi_is_the_one_the_app_produces`, `…_is_valid_and_declares_its_security_scheme`, `test_since_is_declared_a_date_time` | l'OpenAPI versionnée est celle de l'app, valide en 3.1, avec `HTTPBearer` |
| `test_data_api_imports_only_data_api_database_items_and_core`, `test_the_data_api_rule_refuses_etl_and_the_writers` | la règle 5 des couches, et que le test refuse un import interdit ajouté exprès |
| `kb serve` réel sur une base d'essai d'un dossier temporaire, puis `curl` | sans clé : 401 `{"error":"invalid_api_key"}` ; avec clé : 200 et la liste ; `limit=101` : 422 `{"error":"invalid_parameter","parameters":["limit"]}` ; `Host: evil.example` : 400 ; une ligne datée par requête dans `logs/kb-serve.log` ; la clé absente du journal (`grep` : 0) |
| second `kb serve` sur le port pris | `[Errno 48] … address already in use`, code de sortie 3 |
| `uv run pytest` (1138), `ruff check`, `ruff format --check`, `mypy --strict`, `pip-audit` | les contrôles de la CI, verts en local |

## 5. Ce que tu dois pouvoir défendre

**Pourquoi des clés fixes et pas un JWT ?** L'API est locale, en lecture seule, et n'a qu'une
propriétaire. La clé identifie un programme, pas une personne : c'est l'usage qu'OWASP API2
admet. Un JWT demanderait une route de connexion à protéger, une clé de signature et un
renouvellement, pour environ 5 h, et l'API IA (#160) porte déjà l'expiration des jetons (ADR du
2026-10-14). Voir `dependencies.py:19-47`.

**Un attaquant peut-il deviner une clé par le temps de réponse ?** Non, ni la clé ni le client.
`compare_digest` ne s'arrête pas au premier caractère faux, et la boucle compare toutes les clés
(`dependencies.py:42-47`). Seule la longueur peut théoriquement se lire, voir la section 6.

**Que se passe-t-il si une page web tente d'appeler l'API ?** Il n'y a pas de CORS : le
navigateur ne laisse pas la page lire la réponse. `TrustedHostMiddleware` refuse un `Host`
autre que `127.0.0.1` ou `localhost`, ce qui bloque le « DNS rebinding ». Et la clé reste
exigée. Voir `app.py:40`.

**Où la liste refuse-t-elle les données personnelles ?** Dans `ListedItemSchema`
(`schemas/item_schema.py`) : six champs, rien d'autre. Un champ ajouté à la lecture n'est pas
servi. Les auteurs, les surlignages et les chemins du brut ne sont pas dans le modèle (API3 ;
testé).

**Pourquoi une exception imprévue ne passe-t-elle pas par un gestionnaire d'exception ?**
Starlette relance l'exception après un tel gestionnaire, et uvicorn écrirait la pile au journal.
Le middleware `respond_to_unexpected_error` l'arrête avant (`errors.py:94-107`).

### OWASP API Security Top 10 (2023) : ce que chaque point change dans le code

| Exigence | Dans le code |
|---|---|
| API1 (autorisation par objet) | une seule propriétaire : tout client authentifié lit tous les items ; le 404 du détail vient avec #185 |
| API2 (authentification) | `check_api_key` en dépendance de l'app ; `compare_digest` ; contrôles au démarrage ; même 401 ; 401 testé sur chaque route documentée |
| API3 (propriétés exposées) | `ListedItemSchema` en liste blanche, testée sur l'entrée Zotero avec surlignages |
| API4 (consommation) | bornes `limit ≤ 100`, `offset ≤ 10 000`, `q ≤ 200` dans `item_router.py` ; aucun délai de requête (limite écrite dans la spec) |
| API5 (fonctions) | GET seulement : `POST /items` → 405 `method_not_allowed` ; aucune route d'administration |
| API6, API7 | sans objet : aucun flux métier, aucune adresse demandée par un client |
| API8 (configuration) | hôte `127.0.0.1` en dur, `TrustedHostMiddleware`, pas de CORS, erreurs sans pile, ReDoc et redirection OAuth2 coupés, `/items/` en 404 |
| API9 (inventaire) | `kb openapi` et `docs/api/openapi-donnees.json`, comparé au schéma de l'app par un test |
| API10 (consommation d'API tierces) | rien de neuf ici : le contenu servi vient de tiers, il a été validé à la collecte, et c'est une donnée pour le client, jamais une consigne |

### Lancer et appeler l'API

```sh
uv run python -c "import secrets; print(secrets.token_urlsafe(32))"   # une clé, à ranger dans .env
KB_DATA_DIR=~/K-B-data uv run --env-file .env kb serve
curl -H "Authorization: Bearer <la clé>" "http://127.0.0.1:8000/items?kind=paper&limit=5"
```

La documentation interactive est sur `http://127.0.0.1:8000/docs`. Le README détaille les codes
de sortie et les limites.

## 6. Zones non vérifiées

- **La longueur d'une clé** : `compare_digest` pourrait laisser lire la longueur de deux valeurs
  de longueurs différentes. C'est une hypothèse, ni lue dans la documentation de Python ni mesurée ici. Les clés de
  `token_urlsafe(32)` font toutes 43 caractères.
- **Les versions de FastAPI entre 0.122 et 0.143** (borne du `pyproject.toml`) ne sont pas
  vérifiées. `uv.lock` fixe 0.143.1, et le cas de `/docs` repose sur un comportement interne de
  cette version.
- **Une exception levée après le `yield`** (`connection.close()`) partirait après la réponse :
  uvicorn écrirait sa pile dans `kb-serve.log`. Ce cas a été vérifié par simulation en revue ;
  son déclencheur réel n'est pas observé (constat S3, écarté).
- **Une vraie déconnexion de client** pendant une requête n'a pas été provoquée. Seule la
  fonction qui écrit `status=-` est testée.
- **Swagger UI** (`/docs`) charge ses fichiers depuis un CDN, sans empreinte d'intégrité. C'est le
  défaut de FastAPI, déjà écrit comme limite dans la spec (API8).
- **Le skill `.claude/skills/fastapi`** est un texte livré par un paquet tiers, lu comme consigne
  par Claude Code. Le lien vise `python3.13` : il est cassé avant `uv sync`, ou si le dépôt passe
  à une autre version de Python.

## 7. Ce qui reste

- `GET /items/{item_id}` (le détail, les surlignages, `exploited`) et `GET /trends`, ainsi que la
  colonne « Tenue, par quel test » du tableau OWASP de la spec : #185.
- La recherche FTS5 triée par pertinence, qui changera l'ordre des résultats avec `q` : #188.
- Ne pas écrire un auteur refusé dans les journaux : #194.
- Signalés sans issue :
  - `write_file_atomically` ne tient pas la règle 2 (temporaire non caché, seul `OSError`
    rattrapé) ;
  - une `HTTPException` autre que 404 ou 405 rendrait `{"detail": …}`, alors qu'aucune route n'y
    mène aujourd'hui ;
  - le délai de requête d'API4.

## Sources (consultées le 2026-10-14)

- [Global Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/global-dependencies)
  — FastAPI, lu par Context7 : `FastAPI(dependencies=[…])` applique une dépendance à toutes les
  routes (la clé posée sur l'app).
- [Handling Errors](https://fastapi.tiangolo.com/tutorial/handling-errors) — FastAPI, lu par
  Context7 : remplacer les gestionnaires de `RequestValidationError` et de l'`HTTPException` de
  Starlette (les états nommés de `errors.py`).
- [TestClient](https://www.starlette.dev/testclient/) — Starlette, relevé par time-knight :
  le client de test repose sur httpx2, httpx est déprécié (passage à `httpx2`).
- [Release notes](https://starlette.dev/release-notes/) — Starlette, par recherche web :
  1.2.0 ajoute le support de httpx2 au client de test (#3291).
- [pydantic/httpx2](https://github.com/pydantic/httpx2) et
  [le profil PyPI de Kludex](https://pypi.org/user/Kludex/), par recherche web : httpx2 est un
  fork de httpx, publié par le mainteneur de Starlette (vérification avant l'ajout).
- [OWASP API Security Top 10 — 2023](https://api-security.owasp.org/editions/2023/en/0x11-t10/)
  et [API2:2023](https://api-security.owasp.org/editions/2023/en/0xa2-broken-authentication/)
  — consultés le 2026-10-14 pour la spec (#182), qui fixe les exigences tenues ici.
- Code des bibliothèques installées, lu le 2026-10-14 :
  - `fastapi/dependencies/utils.py:619-690` (les dépendances avant les paramètres) ;
  - `fastapi/routing.py:1840-1847` (la route dans le scope) ;
  - `starlette/middleware/errors.py:183-186` (l'exception relancée) ;
  - `starlette/testclient.py:25-43` (httpx2 d'abord) ;
  - `logging/handlers.py:448-450` de Python 3.13.13 (la rotation qui revient sans rouvrir).
