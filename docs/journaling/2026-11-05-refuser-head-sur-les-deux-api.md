# Seules les méthodes déclarées : `HEAD` refusé sur les deux API

- **Date** : 2026-11-05
- **Branche** : `fix/refuse-head-on-both-apis`
- **Issue** : #161, en partie : ni le délai du SQL ni les bornes des réponses de l'API de données
  (#331), ni la revue des 10 points (PR 3)
- **Série** : suit [le droit par route et le débit](2026-11-05-droit-par-route-et-debit-des-deux-api.md)
  (PR 2A de #161)
- **Fichiers principaux** : `src/k_b/core/api_methods.py`, `src/k_b/data_api/app.py`,
  `src/k_b/ai_api/app.py`, `tests/data_api/test_api_errors.py`, `tests/ai_api/test_digest_router.py`,
  `tests/test_api_methods.py`

## Le pourquoi

OWASP API8:2023 (*Security Misconfiguration*) demande qu'une API n'accepte que les méthodes HTTP
dont elle a besoin, et que les autres soient désactivées ; la page cite `HEAD` en exemple. Les
deux revues OWASP de la certification (API IA et API de données, le 05/11) relevaient deux manques :

- `HEAD` répondait 200 sur `/health`, `/docs` et `/openapi.json`, sur les deux API, alors qu'aucun
  client de K-B ne l'envoie (`kb` fait des `GET` à l'API de données et des `POST` à l'API IA) ;
- aucun test ne vérifiait le 405 de chaque méthode qu'une route ne déclare pas.

`HEAD` est un `GET` sans corps de réponse (RFC 9110, section 9.3.2) : il sert à savoir si une
ressource existe, sa taille ou sa date, sans la télécharger. Sur ces trois routes publiques, il
n'apprenait rien de plus que `GET` : le gain de sécurité est faible. Le gain est de tenir la règle
« seules les méthodes déclarées » et de la prouver par un test, pour chaque route et chaque méthode.

Pour un client, rien ne change : `GET` rend toujours 200 sur `/health`, et sur `/docs` et
`/openapi.json` en `sandbox`.

## Le comment

### D'où venait `HEAD` : Starlette l'ajoute à toute route `GET`

Personne ne l'avait déclaré. Starlette, sur lequel FastAPI est bâti, l'ajoute d'office à la
création d'une route qui déclare `GET` (`.venv/.../starlette/routing.py:238-240`, Starlette 1.8.0) :

```python
            self.methods = {method.upper() for method in methods}
            if "GET" in self.methods:
                self.methods.add("HEAD")
```

Les trois routes concernées sont des routes de Starlette : `/docs` et `/openapi.json`, créées par
FastAPI, et `/health`, ajoutée par `app.add_route` (`src/k_b/data_api/app.py:67`). Les routes de
données (`/items`, `/trends`…) sont des `APIRoute` de FastAPI, qui ne l'ajoutent pas : elles
refusaient déjà `HEAD`. Mesuré avant le code : `HEAD /health` 200, `HEAD /items` 405.

### Retirer ce `HEAD`, une fois les routes posées

`src/k_b/core/api_methods.py:11-13` :

```python
    for route in app.routes:
        if isinstance(route, Route) and route.methods and "GET" in route.methods:
            route.methods.discard("HEAD")
```

- `app.routes` est la liste du premier niveau de l'app : les trois routes de Starlette et, pour
  chaque routeur inclus, un objet `_IncludedRouter` de FastAPI 0.143, qui n'est pas une `Route`
  et que la boucle saute.
- `route.methods` est l'ensemble que Starlette consulte à chaque requête
  (`starlette/routing.py:256` et `:274`) : une méthode absente donne un 405, avec l'en-tête
  `Allow` qui liste celles de la route.
- La condition `"GET" in route.methods` ne retire que le `HEAD` implicite (voir « Une route sans
  méthode serait ouverte »).

Les deux `create_app` l'appellent en dernier (`src/k_b/data_api/app.py:69`,
`src/k_b/ai_api/app.py:102`), juste après `add_route` de `/health` : une route ajoutée après
garderait son `HEAD`.

### Le 405 passe par le gestionnaire d'erreurs commun

Starlette lève une `HTTPException(405)` quand la méthode manque, et FastAPI la confie au
gestionnaire de l'app. Le corps est donc celui des autres erreurs, `{"error":
"method_not_allowed"}`, sans détail interne. Pour `HEAD`, uvicorn n'envoie jamais le corps : la
réponse n'a que les en-têtes (`405`, `allow: GET`, `content-length: 30`), comme le veut la RFC.

### Une route sans méthode serait ouverte

Starlette lit un ensemble vide comme « toute méthode » (`if self.methods and …`). Une première
version retirait `HEAD` de toute route : une route qui n'aurait déclaré que `HEAD` se serait
retrouvée avec `set()`, et `POST` y aurait répondu 200. Aucune route de K-B n'est dans ce cas,
mais la revue de sécurité l'a essayé ; le test `tests/test_api_methods.py:14` l'a montré rouge
(`assert 200 == 405`), puis la condition sur `GET` l'a fait passer. C'est la règle « échouer
fermé » de `code.md`.

### Les tests lisent les routes dans l'app

Côté données, toutes les routes ne déclarent que `GET` : le test parcourt l'app et envoie à
chaque route chaque autre méthode (`tests/data_api/test_api_errors.py:137-144`) :

```python
    answers = {
        (route.path, method): read_status_allow_and_body(
            client.request(method, route.path.format(item_id=1), headers=authorization)
        )
        for route in iter_route_contexts(client.app.routes)
        for method in HTTP_METHODS
        if method != "GET"
    }
```

`iter_route_contexts` est le parcours que FastAPI fait pour son OpenAPI : il descend dans les
routeurs inclus, si bien qu'une route ajoutée plus tard est essayée sans toucher au test.
`route.path.format(item_id=1)` remplit le seul paramètre de chemin, `/items/{item_id}`. Le test
attend, pour chaque couple, 405, `Allow: GET` et le corps JSON, sauf pour `HEAD`, sans corps.

Côté IA, les routes déclarent `GET` ou `POST` : une table nomme la méthode de chaque route
(`tests/ai_api/test_digest_router.py:90`), et le test des routes publiques vérifie que l'app a
exactement ces routes et ces méthodes (`:1117`). Le filtre `if method != "HEAD"` de ce test est
retiré : il n'a plus rien à filtrer, et son absence fait échouer le test si `HEAD` revient.

Les méthodes essayées sont celles de la RFC 9110 (section 9) et `PATCH` (RFC 5789), toutes
envoyées par le client de test, `TRACE` et `CONNECT` compris.

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Où refuser `HEAD` | Retirer `HEAD` des routes après leur création : quatre lignes, et le 405 passe par le gestionnaire commun | Un middleware : plus de code pour le même 405, et la réponse sortirait du gestionnaire. Des méthodes explicites à `add_route` : Starlette rajoute `HEAD` malgré elles, et `/docs`, `/openapi.json` sont créées par FastAPI |
| Quelles routes parcourir | Le premier niveau de l'app (`app.routes`) : les trois routes qui ont `HEAD` y sont | Descendre dans les routeurs inclus : aucune route de K-B n'en a besoin. Une route de Starlette ajoutée dans un routeur inclus garderait `HEAD` (essayé : 200), et les tests des deux API, qui lisent toutes les routes, la verraient (essayé : `['GET', 'HEAD']`) |
| Quel `HEAD` retirer | Celui d'une route qui déclare `GET`, le seul qu'ajoute Starlette | Tout `HEAD` : une route à `HEAD` seul serait ouverte à toute méthode |
| Nom | `remove_implicit_head` : il dit ce que fait la fonction | `refuse_head_on_every_route`, premier nom : il promettait toutes les routes, routeurs inclus compris (constat de la revue) |
| Versions | API de données 0.8.0 → 0.9.0, API IA 0.10.0 → 0.11.0 : la spec veut qu'un comportement visible par un client change la version (`docs/specs-api.md:10-12`) | Garder la version : `HEAD` était servi, un client pouvait s'en servir |
| Tests | Un test par API, toutes les routes et 9 méthodes ; il remplace `test_every_data_route_refuses_another_method_with_405` (3 chemins, 4 méthodes) | Garder les deux : le nouveau couvre l'ancien. `HTTP_METHODS` et `read_status_allow_and_body` sont copiés dans deux fichiers de test : deux occurrences, la règle factorise à la troisième |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| Rouge avant le code : `{('/docs', 'HEAD'): (200, None, None)} != (405, 'GET', None)`, et `Allow` à `HEAD, GET` sur les trois routes | Le manque existait sur les deux API |
| `test_every_route_answers_get_only_and_405_to_any_other_method` (données) | Chaque route, chaque méthode autre que `GET` : 405, `Allow: GET`, corps nommé |
| `test_every_route_answers_its_method_only_and_405_to_any_other` (IA) | Idem, avec la méthode propre à chaque route |
| `test_only_the_public_routes_answer_without_a_key` (IA), sans filtre `HEAD` | L'app n'a que ces routes et ces méthodes |
| `test_a_route_declaring_head_only_keeps_it_and_refuses_any_other_method` : rouge (`200 == 405`), puis vert | Le retrait ne vide jamais une route |
| 3 mutations sur fd95f29 (appel retiré de l'une ou l'autre app, `GET` retiré au lieu de `HEAD`) : 1, 2 et 6 tests rouges | Les tests tiennent le code |
| Sous uvicorn, sur les deux API (sonde par socket) : `HEAD /health` 405 sans corps ; `GET /health` 200 ; `CONNECT /health` et `TRACE /health` 405 ; `CONNECT localhost:443` et `OPTIONS *` 404 `route_not_found` avec un hôte permis ; sur l'API de données, 400 `Invalid host header` sinon (`TrustedHostMiddleware`) | Le comportement réel, pas seulement celui du client de test |
| Revue de sécurité (sous-agent, essais) : 4 680 requêtes refusées en 405, `rate_limiter.calls` vide, aucun verrou tenu, `client=-` au journal | Un 405 ne consomme ni clé, ni débit, ni verrou : le routage répond avant les dépendances de l'app |
| Suite entière : 3 446 verts ; ruff, format, `mypy --strict` verts | Rien d'autre n'a bougé |

## Ce que tu dois pouvoir défendre

- **La RFC 9110 dit que tout serveur généraliste doit accepter `GET` et `HEAD` : pourquoi le
  refuser ?** La même section dit que chaque ressource décide si une méthode y est permise. Les API
  de K-B ne sont pas des serveurs généralistes : leurs clients sont connus et n'envoient jamais
  `HEAD`. OWASP API8 demande de désactiver les méthodes inutiles, `HEAD` en exemple.
- **Une sonde de santé peut-elle casser ?** Oui, si elle envoie `HEAD` (`curl -I`, `wget
  --spider`) : 405, le conteneur serait jugé malade. La spec le dit (« Santé », `specs-api.md`) :
  la sonde doit envoyer `GET`. Aucune sonde n'existe encore dans le dépôt.
- **Pourquoi pas un middleware ?** Plus de code pour le même 405, hors du gestionnaire commun ; ici
  quatre lignes modifient l'ensemble que Starlette consulte déjà (`api_methods.py:11-13`).
- **Et si une route est ajoutée plus tard ?** Les tests lisent les routes dans l'app : une route
  nouvelle qui répondrait `HEAD` les ferait échouer. Une route ajoutée après `create_app` garderait
  son `HEAD` ; K-B n'en ajoute aucune.
- **Un 405 coûte-t-il quelque chose ?** Non : le routeur répond avant la clé, le débit et le verrou
  (vérifié par la revue de sécurité). Sans clé, on obtient un 405, pas un 401 : le 405 ne dit que
  la méthode permise, que la spec publie déjà.

## Zones non vérifiées

- uvicorn avec `httptools` (`uvicorn[standard]`), HTTP/2, et une entrée ACA ou un proxy devant
  l'app : ils peuvent répondre eux-mêmes à `HEAD`, `OPTIONS` ou `CONNECT`. À essayer au jalon du
  08/11 (#317).
- Que FastAPI ne reconstruise jamais les routes du premier niveau après `create_app` : constaté
  après le démarrage et après la génération de l'OpenAPI (revue de sécurité), pas lu dans tout le
  code de FastAPI.

## Ce qui reste

- Le délai des requêtes SQL et les bornes des réponses de l'API de données : la PR de #331.
- L'auto-évaluation des 10 points de l'API IA, qui fermera #161 : la PR 3 ; elle dira l'écart à la
  RFC 9110 ci-dessus.
- La sonde de santé de compose (#200) et celle d'ACA (#317) devront envoyer `GET`.
