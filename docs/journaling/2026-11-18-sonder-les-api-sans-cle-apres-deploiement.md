# Sonder les deux API sans clé après chaque déploiement

- **Date** : 2026-11-18
- **Branche** : `feat/smoke-test-probes`
- **Issue** : #499
- **Fichiers principaux** : `src/k_b/jobs/api_probes.py`, `src/k_b/commands/smoke_test_command.py`,
  `src/k_b/core/config.py` (`PROBE_*`), `tests/commands/test_smoke_test_command.py`, `tests/jobs/test_api_probes.py`,
  les tests de contrat de `tests/ai_api/test_digest_router.py` et `tests/data_api/test_api_keys.py`,
  `infra/modules/smoke-test-job.bicep` (commentaire seul)
- **Série** : suite de [`kb smoke-test`, les API et le stockage d'échange](2026-11-06-kb-smoke-test-api-et-stockage-d-echange.md)
  (#412), qui a créé le test de fumée.

Les commits de #499 sont `1492a0e` (code et tests), `64a2393` (doc), `718b69c` (journal ADR), `1368a15`
(corrections de la revue), `9b4e03c` (cette note), `33eba04` (l'auto-évaluation), puis le commit des corrections de
la seconde revue. `1f2abbf` est un correctif de #498, porté par cette branche parce que #643 a été fusionnée sans lui :
la note de #498 le couvre. Les autres commits que liste `git log` sur cette branche sont ceux de `main` et ses
fusions, déjà fusionnés par leurs propres PR : la note ne les couvre pas.

## Le pourquoi

L'auto-évaluation OWASP API Security Top 10 (2023) de l'API IA (`docs/fiches-veille.md`, API8 « Security
Misconfiguration ») compte la mesure « évaluation automatisée et continue dans tous les environnements » parmi les
non tenues. #498 en tient une moitié, le scan de l'image dans la CI. L'autre moitié est l'environnement déployé : après
chaque mise en ligne, `deploy.yml` lance le job `caj-kb-smoke-test`, qui ne demandait que `GET /health` aux deux API.
Il prouvait que la version déployée **répond**, pas qu'elle **refuse ce qu'elle doit refuser**.

#499 ajoute au test de fumée des sondes sans clé : des requêtes qu'une API bien configurée doit refuser, chacune avec
le statut qu'elle doit rendre. Si une version en ligne servait une route à clé sans clé, exposait `/docs`, ou répondait
à `HEAD`, le test de fumée échouerait, et `deploy.yml` avec lui.

## Le comment

### 1. Une sonde : une requête et le statut qu'elle attend

```python
    return (
        Probe(method, path, WITHOUT_KEY_STATUS),
        Probe("GET", DOCS_PATH, docs_status),
        Probe("HEAD", HEALTH_PATH, METHOD_NOT_ALLOWED_STATUS),
    )
```

`src/k_b/jobs/api_probes.py:81-85`. Trois sondes par API, sur les deux API :

- une route à clé, appelée sans clé, doit rendre **401** : `GET /items` pour l'API de données, `POST /digests` pour
  l'API IA (`api_probes.py:30-31`). La clé est une dépendance FastAPI de la route. FastAPI lit le JSON du corps
  avant elle : un corps illisible rend 422 sans clé, mais une requête sans corps, comme la sonde, reçoit 401
  (`tests/ai_api/test_digest_router.py:519-526`, `test_without_key_only_a_body_that_cannot_be_read_gets_422`,
  paramètre `None`) ;
- `GET /docs` doit rendre **404** hors `sandbox`, **200** en `sandbox` : les API ne servent Swagger UI qu'en
  `sandbox` (`read_openapi_url`, `core/api_settings.py`) ;
- `HEAD /health` doit rendre **405** : les deux API retirent le `HEAD` que Starlette ajoute à toute route `GET`
  (`remove_implicit_head`, `core/api_methods.py`).

Le statut attendu de `/docs` suit la variable `KB_DEPLOYMENT_ENVIRONMENT` **du job** :

```python
    return SmokeTestSettings(
        data_api_url, ai_api_url, is_sandbox(environ), exchange_storage
    )
```

`src/k_b/commands/smoke_test_command.py:140-142`. C'est la même fonction `is_sandbox` que celle qui décide, dans les
API, de servir `/docs`. En ligne, ni le job ni les API n'ont `sandbox` : le job n'a pas la variable
(`infra/main.bicep`, module `smokeTestJob`), et les API ont `production`.

### 2. Envoyer une sonde sans lire la réponse

```python
    try:
        with http_client.stream(probe.method, probe.path) as response:
            status = response.status_code
    except httpx2.TimeoutException:
        raise ProbeError("probe_timeout") from None
    except httpx2.TransportError:
        raise ProbeError("probe_unavailable") from None
    if status != probe.expected_status:
        raise ProbeError("probe_unexpected_status", status)
```

`src/k_b/jobs/api_probes.py:91-99`. `stream` rend la réponse dès que ses en-têtes sont arrivés ; on lit le statut, et
la sortie du `with` ferme la réponse **sans lire son corps**. Seul le statut prouve le refus : un corps qu'on ne lit
pas n'a rien à valider ni à citer au journal. L'ordre des `except` compte : `TimeoutException` est une sous-classe de
`TransportError`, il faut l'attraper d'abord. L'échec est un **état nommé** (`probe_unexpected_status` avec le statut
reçu, `probe_timeout`, `probe_unavailable`), jamais l'URL ni le message de l'exception (`from None` coupe la chaîne),
comme `HealthCheckError` pour `/health` (règle 3 de `conventions.md`).

### 3. Les sondes dans le test de fumée

```python
    # The /health of an API first: it wakes the API before its probes.
    results = [
        check_api(DATA_API_NAME, settings.data_api_url),
        *probe_api(
            DATA_API_NAME,
            settings.data_api_url,
            list_probes(DATA_API_ROUTE_WITH_KEY, settings.is_sandbox),
        ),
```

`src/k_b/commands/smoke_test_command.py:94-101`. Les API en ligne tombent à 0 réplique au repos ; leur `/health`
peut attendre le réveil (20 à 26 s mesurés le 06/11). Chaque sonde vient donc après le `/health` de son API. Chaque
contrôle rend un `CheckResult` et attrape sa propre erreur (`check_probe`, `smoke_test_command.py:163-173`) : un échec
n'arrête pas les autres, et le résumé compte neuf contrôles au lieu de trois (`9 of 9 checks passed`).

### 4. Un client aux délais d'une API éveillée

```python
PROBE_CONNECT_TIMEOUT_SECONDS = 5
PROBE_POOL_TIMEOUT_SECONDS = 5
PROBE_WRITE_TIMEOUT_SECONDS = 10
PROBE_READ_TIMEOUT_SECONDS = 10
```

`src/k_b/core/config.py:691-694`, utilisés par `build_probe_client` (`api_probes.py:59-73`). Le premier code
réutilisait le client du `/health`, dont la lecture attend 60 s pour couvrir le réveil. La revue a calculé le pire
cas : deux `/health` et six sondes de 65 s chacun, plus les nouvelles tentatives du stockage, environ 966 s, au-delà
des 900 s du `replicaTimeout` du job. Azure aurait coupé la réplique avant qu'elle écrive son résumé. Une sonde suit
le `/health` qui a réveillé son API : 10 s de lecture suffisent, et le pire cas descend à environ 666 s (commentaire de
`infra/modules/smoke-test-job.bicep`, recalculé ; aucune passe d'infra).

### 5. Un test de contrat : la sonde contre l'API elle-même

```python
    environ = {DEPLOYMENT_ENVIRONMENT_VARIABLE: deployment_environment}
    client, transport = make_ai_api([], openapi_url=read_openapi_url(environ))
    probes = list_probes(AI_API_ROUTE_WITH_KEY, is_sandbox(environ))
```

`tests/ai_api/test_digest_router.py:1282-1296`, et son pendant dans `tests/data_api/test_api_keys.py:149-163`. Les
chemins et les statuts des sondes sont une **seconde copie** de ce que les API répondent. Les tests de
`kb smoke-test` simulent les API (`answer_as_the_apis`) : ils répondent ce que le test leur dit, et ne verraient pas
une sonde fausse. Le test de contrat envoie chaque sonde à la vraie application, construite en `sandbox` puis en
`production`, avec le même `environ` pour l'application et pour la liste des sondes ; pour l'API IA, il vérifie aussi
qu'aucune requête n'atteint le modèle. Les fixtures `make_ai_api` et `make_client` reçoivent pour cela `openapi_url`,
leur défaut inchangé.

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Quelles API | les deux (plan du 13/11, point 7, validé par Sabine) : `docs/specs-api.md` renvoie l'API de données aux mêmes issues | l'API IA seule, le texte de l'issue |
| Quoi prouver en ligne | des refus sans clé : 401, 404, 405 | une clé de test en ligne : un secret de plus, qui fait dépenser le modèle ; les routes à clé sont couvertes par les tests de la CI |
| `/docs` | son statut suit `is_sandbox` du job, la règle de `read_openapi_url` | un statut fixe à 404 : le test de fumée échouerait dans le compose du bac à sable |
| La réponse | statut seul, corps jamais lu | lire et valider le corps : rien à en tirer, et un texte de plus à tenir hors du journal |
| L'ordre | chaque sonde après le `/health` de son API, qui la réveille | les sondes d'abord : la première porterait le réveil |
| Un `/health` en échec | les sondes de l'API tournent quand même (« un échec n'arrête pas les autres », revue, tranché par time-knight) | les sauter : une sonde dit autre chose que `/health`, et leur coût est borné (45 s par API) |
| Les délais des sondes | leur client, lecture 10 s (revue, tranché par time-knight) | le client du `/health` (pire cas au-delà du `replicaTimeout`) ; monter le `replicaTimeout` (une passe d'infra, aucune avant la fusion de #630) |
| Le contrat | un test par API contre l'application (écart au plan, tranché par time-knight) | les seuls tests sur API simulées : une sonde fausse ne se verrait qu'en ligne |
| `ProbeError` | une classe à part, comme `HealthCheckError` | une classe commune : deux occurrences, `code.md` factorise à la troisième |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| Avant le code, le 18/11 à 03:40 UTC : 12 tests de `test_smoke_test_command.py` en échec ; `test_api_keys.py` et `test_digest_router.py` refusés à la collecte (`ModuleNotFoundError: No module named 'k_b.jobs.api_probes'`) | les tests précèdent le code |
| `test_smoke_test_passes_once_both_apis_answer_and_the_container_is_listed` | les huit requêtes, dans l'ordre, sans en-tête `Authorization` ; le résumé de neuf lignes ; `9 of 9 checks passed` |
| `test_a_probe_that_gets_another_status_fails_and_the_other_checks_still_run` (6 cas, un par sonde) | une sonde qui reçoit 200 échoue seule, nommée `probe_unexpected_status, HTTP 200` ; les huit autres contrôles tournent ; `8 of 9` |
| `test_a_probe_without_answer_fails_by_its_state_without_the_url` (2 cas) | un délai dépassé rend `probe_timeout`, une connexion refusée `probe_unavailable`, sans l'hôte ni le message de l'exception |
| `test_the_body_of_an_answer_to_a_probe_is_never_read` | un corps qui fait échouer le test s'il est lu n'est jamais lu |
| `test_in_the_sandbox_a_docs_not_served_fails_its_probe` et `test_smoke_test_reaches_the_compose_services_in_http_in_the_sandbox` | en `sandbox`, `/docs` doit rendre 200 |
| `test_each_probe_of_kb_smoke_test_gets_the_status_it_expects` (API IA et API de données, `sandbox` et `production`) | chaque sonde reçoit, de l'application elle-même, le statut qu'elle attend ; aucun appel au modèle |
| `test_smoke_test_reaches_the_health_of_both_apis_served` (`tests/commands/test_live_apis.py`) | sur les deux API servies par uvicorn, construites par `kb serve-data` et `kb serve-ai`, les neuf contrôles passent |
| `test_a_probe_waits_a_read_shorter_than_the_wake_of_an_api` | le client des sondes lit 10 s, moins que les 60 s du réveil |
| L'API de données construite hors `sandbox`, le 18/11 : `request method='GET' route=/items status=401`, `method='GET' route=/docs status=404`, `method='HEAD' route=/health status=405`, `client=-` | les lignes que les sondes laissent dans le journal des API, écrites dans `infra/README.md` |
| `uv run pytest` → 5636 passed ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` verts ; site MkDocs en mode strict construit | la branche ne casse rien |
| Après la fusion d'`origin/main` à `1bef80f2`, le 18/11 : `uv run pytest` → 5643 passed ; mêmes contrôles verts | la branche, à jour de `main`, ne casse rien |

## Ce que tu dois pouvoir défendre

1. **Pourquoi des sondes sans clé, et pas un essai avec une vraie clé en ligne ?** Une clé de test serait un secret
   de plus en ligne, et un `POST /digests` accepté fait appeler (et payer) le modèle. Ce qu'on vérifie en ligne, c'est
   la configuration déployée : les refus. Le comportement avec clé est couvert par les tests de la CI, sur le code de
   l'image (`api_probes.py:30-31`, journal ADR du 18/11).
2. **Que se passe-t-il si une version en ligne servait `/docs` ?** La sonde reçoit 200 au lieu de 404 :
   `probe_unexpected_status, HTTP 200`, le job rend 1, `deploy.yml` échoue sur `Runs the smoke test`
   (`test_a_probe_that_gets_another_status_fails_and_the_other_checks_still_run`, cas `GET /docs`).
3. **Comment sais-tu que les statuts attendus sont les bons ?** Le test de contrat envoie chaque sonde à
   l'application elle-même, en `sandbox` et hors `sandbox` (`test_digest_router.py:1282`, `test_api_keys.py:149`) ;
   et le test des API servies par uvicorn passe neuf contrôles sur neuf.
4. **Pourquoi 10 s de lecture pour une sonde, et 60 s pour `/health` ?** `/health` porte le réveil d'une API à 0
   réplique ; une sonde vient juste après, sur une API éveillée. Avec 60 s, six sondes portaient le pire cas au-delà
   du `replicaTimeout` de 900 s, et Azure aurait coupé le job avant son résumé (`config.py:691-694`,
   `smoke-test-job.bicep`).
5. **Une sonde peut-elle fuiter une donnée dans le journal ?** Non : le corps n'est jamais lu, et l'échec ne dit que
   son état et le statut, jamais l'URL ni le message de l'exception (`api_probes.py:91-99`,
   `test_a_probe_without_answer_fails_by_its_state_without_the_url`).

## Zones non vérifiées

- **En ligne, rien n'est encore constaté.** Les statuts viennent des applications ; qu'ils traversent l'entrée
  d'Azure Container Apps (Envoy) sans changer, en particulier le 405 de `HEAD` et le 404 de `/docs`, n'est pas
  observé. Le constat attend un tag, posé après la fusion de #630.
- **Les lignes de journal de l'API IA** : relevées sur l'API de données seule. L'API IA est supposée écrire les
  mêmes, par le même module (`core/api_request_log.py`), avec `route=/digests` ; non observé.
- **Le pire cas de 666 s** est un calcul sur les délais configurés et sur l'estimation de 7 min des nouvelles
  tentatives du stockage reprise du commentaire du Bicep, pas une mesure.
- **Des en-têtes qui arrivent octet par octet** ne sont pas coupés par le délai de lecture, comme pour `/health`
  (limite connue, #436).

## Ce qui reste

- **L'auto-évaluation** n'attend plus que le constat en ligne. Elle est écrite dans `33eba04`
  (`docs/fiches-veille.md`, API8 « Évaluation automatisée », la ligne du tableau et le compte ; `docs/specs-api.md`,
  API8) : la mesure y reste « non tenue, en partie » jusqu'à ce constat (règle des preuves du plan).
- **Le constat en ligne** : après la fusion de #630, un tag, puis dans `log-kb` la ligne
  `smoke test finished in … s: 9 of 9 checks passed` (`infra/README.md`, « 6. Vérifier la mise en ligne ») ;
  commentaire sur #499, et la mesure passe à « tenue » dans la PR suivante qui touche l'auto-évaluation.
- **Le push et la PR**, sur l'accord de Sabine.
