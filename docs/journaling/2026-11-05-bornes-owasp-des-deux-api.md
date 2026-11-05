# Borner le corps des requêtes, la réponse du modèle et le nombre de `kind`

- **Date** : 2026-11-05
- **Branche** : `fix/bound-request-bodies-and-model-answers`
- **Issue** : #161, en partie (ni le débit ni la revue des 10 points, qui viennent ensuite)
- **Fichiers principaux** : `src/k_b/core/api_body_limit.py`, `src/k_b/ai_api/app.py`,
  `src/k_b/ai_api/connectors/llm_client.py`, `src/k_b/data_api/routers/item_router.py`,
  `src/k_b/core/config.py`

## Le pourquoi

La certification a passé les deux API au crible de l'OWASP API Security Top 10 (édition 2023) le
05/11 : 3 entrées sur 10 pour l'API IA, 4 sur 10 pour l'API de données. Trois manques se corrigent
par une simple borne :

- **Le corps d'une requête à l'API IA n'avait pas de taille maximale**, et il est lu avant la clé :
  un appelant sans clé pouvait faire lire au serveur un corps de n'importe quelle taille (API4).
- **La réponse du fournisseur du modèle était lue sans borne**, alors que celles de l'API de
  données et de GitHub en ont une. Une réponse d'un tiers est une entrée non fiable (API10).
- **Le paramètre `kind` de `GET /items` acceptait autant de valeurs qu'on voulait** (API4).

Cette PR est la première de trois. Elle borne ; elle ne limite pas encore le débit.

## Le comment

### Un middleware ASGI, et l'ordre de la pile

Un middleware ASGI enveloppe l'application : il voit la requête avant elle et peut répondre à sa
place. Dans FastAPI, le dernier ajouté est le plus extérieur :

```python
    bound_request_bodies(app, MAX_AI_API_BODY_BYTES)
    app.middleware("http")(respond_to_unexpected_error)
    app.middleware("http")(log_request)
```
(`src/k_b/ai_api/app.py:75-77`)

Une requête traverse donc `log_request`, `respond_to_unexpected_error`, puis les deux middlewares
de la borne, puis le routage et la clé. Conséquence voulue : un 413 a sa ligne de journal, et il
arrive avant la vérification de la clé.

### Pourquoi la borne doit passer avant la clé

FastAPI lit le corps de la requête avant de résoudre les dépendances, et `check_api_key` est une
dépendance : `await request.body()` est à `fastapi/routing.py:446`, `solve_dependencies` à `:499`
(FastAPI 0.143.1). Une borne posée après la clé ne protégerait donc de rien : le corps aurait déjà
été lu. Un appelant sans clé peut encore faire lire au serveur un corps sous la borne, mais plus au
delà.

### Le middleware de Starlette et son piège

Starlette 1.8.0 fournit `RequestBodyLimitMiddleware`, qui compte les octets réellement reçus, même
sans `Content-Length` :

```python
        message = await self.receive()
        if message["type"] == "http.request":
            self.total_size += len(message.get("body", b""))
            if self.total_size > self.max_body_size:
                raise _RequestBodyTooLarge
```
(`starlette/middleware/body_limit.py:108-112`)

FastAPI 0.143.1 réécrit sa pile de middlewares (`fastapi/applications.py:1054`) sans y mettre le
`max_body_size` de Starlette : il faut donc l'ajouter par `add_middleware`.

Ce comptage lève une `HTTPException` de Starlette, que FastAPI relance telle quelle
(`fastapi/routing.py:480`) au lieu d'en faire un 400 comme pour toute autre erreur de lecture
(`:483-486`). Elle arrive donc à notre `handle_http_error`, qui la rend en `{"error":
"content_too_large"}` (`src/k_b/core/api_errors.py:20-27`).

**Le piège**, trouvé en essayant : quand `Content-Length` dépasse la borne, Starlette remplace toute
réponse par un 413 en texte brut, y compris notre JSON :

```python
            if self.content_length is not None and self.content_length > self.max_body_size:
                response = PlainTextResponse("Content Too Large", status_code=413)
                await response(self.scope, self.receive, self.send)
                raise _RequestBodyLimitResponseSent
```
(`starlette/middleware/body_limit.py:118-121`)

C'est le cas courant : httpx, le client de `kb digest`, envoie `Content-Length` pour un corps JSON ou
en octets (essayé). Ce texte brut sortirait du schéma d'erreur commun, une mesure qu'API8 demande et que la certif coche aujourd'hui.

### Notre contrôle devant celui de Starlette

Pour que Starlette ne voie jamais une telle requête, K-B répond avant lui :

```python
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and is_announced_beyond(scope, self.max_bytes):
            await respond_with_error(413, CONTENT_TOO_LARGE)(scope, receive, send)
            return
        await self.app(scope, receive, send)
```
(`src/k_b/core/api_body_limit.py:29-33`)

La longueur se lit par `int()`, exactement comme Starlette (`_get_content_length`,
`body_limit.py:125-132`) : toute valeur que Starlette jugerait trop grande, K-B la refuse d'abord
en JSON. Une valeur qu'`int()` refuse reste au comptage de Starlette
(`src/k_b/core/api_body_limit.py:36-45`).

uvicorn, lui, refuse déjà ces formes exotiques : h11, seul analyseur HTTP installé, n'accepte que
`[0-9]+` (`h11/_headers.py:72`). `+2000` ne peut donc pas atteindre l'application derrière
`kb serve-ai` ; lire par `int()` garantit le JSON quel que soit le serveur devant.

### La réponse du modèle, lue au fil du flux

`http_client.post` lit toute la réponse en mémoire avant de nous la rendre : trop tard pour la
refuser. La réponse passe donc par `stream`, puis par `read_bounded_body`, déjà utilisé pour l'API de
données et GitHub :

```python
    is_late = None if deadline is None else deadline.is_passed
    try:
        with http_client.stream(
            "POST", CHAT_COMPLETIONS_PATH, json=body, timeout=timeout
        ) as response:
            try:
                content = read_bounded_body(response, MAX_LLM_ANSWER_BYTES, is_late)
            except BodyTooLargeError:
                return Attempt(
                    outcome="llm_unavailable", http_status=response.status_code
                )
            except BodyTooLateError:
                return Attempt(outcome="llm_timeout", http_status=response.status_code)
```
(`src/k_b/ai_api/connectors/llm_client.py:434-446`)

`read_bounded_body` s'arrête entre deux morceaux dès que la taille dépasse la borne ou que
l'échéance est passée (`src/k_b/core/outbound.py:81-87`). Trop gros donne `llm_unavailable`, le
même état qu'une réponse illisible, et comme elle sans nouvelle tentative. L'échéance passée donne `llm_timeout`. Les délais de httpx bornent chaque attente, pas la
lecture entière : `is_late` borne le total.

### `max_length` sur une liste

```python
MAX_KINDS = len(get_args(ItemKind))
```
(`src/k_b/data_api/routers/item_router.py:34`)

Le maximum se déduit de la liste des sortes : ajouter une sorte l'ajuste sans rien changer d'autre.
`Query(max_length=MAX_KINDS)` (`:84`) porte sur le nombre de valeurs de la liste, pas sur leur
longueur : Pydantic applique `max_length` à une séquence, et l'OpenAPI l'écrit `"maxItems": 7`.

## Choix faits et options écartées

**La borne du corps.**
- Retenu (option B, choisie par Sabine le 05/11) : notre contrôle de `Content-Length` devant le
  middleware de Starlette. Le comptage reste à la bibliothèque, et la réponse reste en JSON.
- Écarté (A) : le middleware de Starlette seul. 3 lignes, mais un 413 en texte brut dans le cas
  courant.
- Écarté (C) : un middleware entièrement à K-B. Il referait le comptage que Starlette fournit.
- Écarté : intercepter `receive` et lever une exception quelconque. FastAPI en ferait un 400
  (`fastapi/routing.py:483-486`), puis K-B un faux 422.
- Écarté : une borne posée par ACA. Rien n'est dans le dépôt, et le corps resterait sans borne en
  local.

**Les valeurs.**
- `MAX_AI_API_BODY_BYTES = 1024` : le plus gros corps légitime mesure 62 octets (les deux dates de
  `POST /trend-reports`), soit une marge d'environ ×16. Une constante et non une variable
  d'environnement : ce n'est pas un réglage de déploiement (règle 2 de `poc.md`).
- `MAX_LLM_ANSWER_BYTES = 1_000_000` : 8 192 jetons de sortie au plus, environ 65 Ko à 4 octets par
  jeton doublés par l'échappement du JSON dans le JSON. C'est une **hypothèse, non mesurée** ; la
  marge couvre les annotations du filtre de contenu d'Azure.

**La réponse du modèle.**
- Retenu : passer le contenu lu à part à `read_answer`, `read_failure` et `read_error_code`.
- Écarté : reconstruire une `httpx2.Response` à partir du corps lu. Avec l'en-tête
  `Content-Encoding` recopié, httpx2 décoderait le corps une seconde fois (essayé : `DecodingError`).

**Le périmètre.** L'API de données ne reçoit pas le middleware : elle ne lit aucun corps. Les
versions montent, car un client voit le changement : API IA 0.9.0, API de données 0.7.0.

**Le tri des 7 constats de la première revue de code** (les raisons complètes sont dans la PR) :
- Corrigé : 3, la lecture de `Content-Length` par `int()`, avec le test de 7 qui s'y rapporte.
- Écartés : 1, l'échéance après le dernier morceau (même comportement que l'API de données et
  GitHub) ; 2, un 429 de plus d'1 Mo (improbable, la demande échoue quand même) ; 4, l'usage d'une
  réponse trop grosse (le lire demanderait de lire tout le corps) ; 5, la lecture en double (les
  deux règles diffèrent désormais) ; 6, un seul middleware (l'option C) ; le reste de 7, un test à
  la borne sur `/trend-reports` (la borne vaut pour toute l'application).

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_body_beyond_the_bound_is_refused_413_before_the_key` (2 routes, annoncé ou en flux) | 413 JSON sans clé, rien de lu ni d'envoyé au modèle |
| `test_a_body_at_the_bound_is_read` | 1 024 octets passent, annoncés ou en flux |
| `test_a_body_announced_beyond_the_bound_gets_the_413_of_k_b_on_any_route` | le JSON de K-B sur une route qui ne lit pas de corps |
| `test_a_length_starlette_reads_beyond_the_bound_gets_the_413_of_k_b` | `+2000` et `2_000` reçoivent le JSON ; rouge avant la correction (`JSONDecodeError`) |
| `test_a_length_that_is_not_a_number_is_left_to_the_count_of_starlette` | une longueur illisible ne fait pas échouer la requête, et le comptage refuse quand même un corps trop gros |
| `test_an_answer_up_to_the_bound_is_read`, `test_an_answer_above_the_bound_is_llm_unavailable_without_retry` | la borne au mot près, annoncée ou comptée, sans relance |
| `test_an_answer_still_read_at_the_deadline_is_llm_timeout` | l'échéance arrête la lecture |
| `test_a_parameter_out_of_bounds_gives_422_with_its_name_only`, `test_every_kind_at_once_is_read` | 8 valeurs refusées, 7 acceptées |
| Essai sur un vrai uvicorn, par sockets bruts, sans envoyer le corps annoncé | 413 JSON immédiat sur `/digests`, `/trend-reports` et `/health` |
| Même essai, corps en flux de 2 × 600 octets | 413 JSON |
| Même essai, `Content-Length: +2000` | 400 en texte brut, d'uvicorn : la requête n'atteint pas l'application |
| Même essai, 1 024 octets sans clé | 401 : la borne laisse passer, la clé refuse |
| Tests rouges lancés avant le code | l'ordre test puis code |
| 19 mutations du nouveau code, toutes tuées | les tests mordent |
| `/security-review` | aucun constat |

## Ce que tu dois pouvoir défendre

**Pourquoi ne pas vérifier la clé avant de lire le corps ?** FastAPI lit le corps avant les
dépendances (`fastapi/routing.py:446` puis `:499`), et la clé en est une. La borne agit donc avant
les deux : un appelant sans clé ne fait lire que 1 024 octets, au plus un morceau de plus en flux.

**Peut-on contourner la borne en ne déclarant pas de longueur, ou en mentant ?** Non : Starlette
compte les octets reçus, quel que soit l'en-tête (`body_limit.py:108-112`). L'en-tête ne sert qu'à
refuser plus tôt. L'essai en flux sur un vrai serveur le montre.

**Pourquoi deux contrôles pour une seule borne ?** Starlette seul répond en texte brut quand la
longueur annoncée dépasse la borne (`body_limit.py:118-121`). Le schéma d'erreur commun est lui-même
une exigence (API8). Le premier contrôle garde le contrat, le second garde le comptage.

**Que se passe-t-il si le fournisseur renvoie 2 Mo ?** La lecture s'arrête dès la borne dépassée, et
le sujet échoue en `llm_unavailable`, sans relance (`llm_client.py:441-444`). Une réponse compressée
est bornée sur ses octets décodés (`core/outbound.py:70-72`).

**Pourquoi 1 024 octets ?** Le plus gros corps légitime en fait 62, et le schéma est fermé : aucun
autre champ n'est accepté. La borne ne gêne donc aucun usage.

## Zones non vérifiées

- **Aucun appel réel au modèle n'a traversé la nouvelle lecture** : le rejeu et des transports
  simulés seulement. Un `make digest` réel reste à faire.
- **La taille réelle d'une réponse du modèle n'est pas mesurée** : les 65 Ko sont une estimation, et
  la taille des annotations du filtre de contenu d'Azure est supposée.
- **Le volume lu au-delà de la borne, en flux, n'est pas mesuré** : le comptage intervient après
  chaque message reçu, et sa taille dépend de ce qu'uvicorn délivre d'un coup.
- **Rien n'a été essayé derrière l'entrée HTTPS d'ACA** (08/11).
- **Le remplacement en texte brut est observé sur Starlette 1.8.0** : la version qui l'a introduit
  n'a pas été lue. Une version future pourrait le changer, sans effet ici puisque K-B répond avant.
- **Le 400 d'uvicorn sur un en-tête malformé reste en texte brut**, hors du schéma d'erreur : il
  naît avant l'application, et existait déjà avant cette PR.

## Ce qui reste

- Le débit, pas la taille : droits par route, concurrence, limite par client, délai de requête de
  l'API de données (PR 2).
- L'auto-évaluation des 10 points pour l'API IA, avec ses écarts justifiés (PR 3) : #161 reste
  ouverte.
- TLS, ressources et fichiers de déploiement, au jalon ACA du 08/11.
- Des réponses de l'API de données restent sans borne de taille : tous les surlignages d'une entrée
  Zotero, un clip jusqu'à 1 000 000 de caractères. À trancher par Sabine.
- L'identifiant public aléatoire des items (décision « A » du 05/11), après ces PR.
