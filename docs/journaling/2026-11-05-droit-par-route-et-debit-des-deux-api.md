# Un client par route, une demande à la fois, un débit par client

- **Date** : 2026-11-05
- **Branche** : `feat/api-rights-and-rates`
- **Issue** : #161, en partie : ni `HEAD` ni le délai du SQL (PR 2B), ni la revue des 10 points (PR 3)
- **Série** : suit [les bornes des deux API](2026-11-05-bornes-owasp-des-deux-api.md) (PR 1 de #161)
- **Fichiers principaux** : `src/k_b/core/api_rate_limit.py`, `src/k_b/core/api_access.py`,
  `src/k_b/core/config.py`, `src/k_b/ai_api/app.py`, `src/k_b/data_api/app.py`,
  `src/k_b/post/ai_api_client.py`, `src/k_b/ai_api/connectors/data_api_client.py`

## Le pourquoi

La revue OWASP API Security Top 10 (édition 2023) de la certification, le 05/11, relève sur l'API IA
le manque qui pèse le plus : **rien ne limite le nombre d'appels au modèle**, qui est payant. Elle en
relève deux autres :

- **Toute clé valide ouvre les deux routes** : la clé de `kb trend-report` peut demander des fiches,
  et l'inverse (API5).
- **Aucune limite de débit**, ni sur l'API IA ni sur l'API de données (API4, API6).

#161 demande aussi de borner les demandes simultanées : une demande de fiches dure jusqu'à 200 s et
fait plusieurs appels au modèle, si bien qu'une limite par minute ne suffit pas. Les deux API
doivent être en ligne au 08/11 : c'est avant cette date que ces garde-fous comptent.

Cette PR ne change rien pour un usage normal. `make digest` et `make trend-report` passent comme
avant ; seuls un client qui n'est pas celui de la route, une seconde demande lancée pendant la
première, ou une boucle qui s'emballe sont refusés.

## Le comment

### Quatre contrôles, dans un ordre qui ne fait rien consommer

FastAPI exécute les dépendances de l'app dans l'ordre où elles sont déclarées, avant celles de la
route. L'ordre est donc une décision :

```python
        dependencies=[
            Depends(check_api_key),
            Depends(check_client_allowed),
            Depends(hold_route_slot),
            Depends(check_rate_limit),
        ],
```
(`src/k_b/ai_api/app.py:61-66`)

Chaque contrôle qui refuse lève une `ApiError`, et les suivants ne s'exécutent pas. Une requête
sans clé valide reçoit donc 401 sans avoir pris le verrou ni compté dans le débit. Une requête
refusée parce qu'une autre tourne (429) n'est pas comptée non plus. Sur l'API de données, il n'y a
que deux contrôles : la clé, puis le débit (`src/k_b/data_api/app.py`).

L'ordre complet, middlewares compris : 413 (corps trop gros), 404 ou 405 (routage), 422 d'un corps
illisible, 401, 403, 429 de concurrence, 429 de débit, 422 de schéma, puis la route.

### Le droit par route : une table, et un refus par défaut

```python
    route = find_route_template(request)
    if request.app.state.client_by_route.get(route) != request.state.client_name:
        raise ApiError(403, CLIENT_NOT_ALLOWED)
```
(`src/k_b/core/api_access.py:47-49`)

- **La route lue est son gabarit, pas le chemin reçu.** `find_route_template` lit
  `request.scope["route"].path`, que FastAPI écrit avant d'exécuter la route : `/digests`, ou
  `/items/{item_id}` et non `/items/42`. Une variante d'écriture du chemin ne peut donc pas se faire
  passer pour une autre route.
- **Le client vient de la clé**, écrit par `check_api_key` dans `request.state.client_name`, jamais
  d'une valeur que l'appelant envoie.
- **Refus par défaut** : pour une route absente de la table, `.get` rend `None`, qui n'est le nom
  d'aucun client : 403 pour tous.

La table vit dans `core/config.py` (`AI_API_CLIENT_BY_ROUTE`), et les commandes en tirent le nom de
leur variable de clé (`DIGEST_KEY_VARIABLE`, `TREND_REPORT_KEY_VARIABLE`) : un seul endroit dit
quel client ouvre quelle route.

### Une demande à la fois : un verrou pris sans attendre

```python
    slot = request.app.state.slot_by_route[find_route_template(request)]
    if not slot.acquire(blocking=False):
        raise ApiError(
            429,
            REQUEST_ALREADY_RUNNING,
            {"Retry-After": str(RUNNING_REQUEST_RETRY_AFTER_SECONDS)},
        )
    try:
        yield
    finally:
        slot.release()
```
(`src/k_b/core/api_rate_limit.py:62-72`)

- **Une dépendance à `yield`** : le code avant `yield` s'exécute avant la route, celui du `finally`
  après. Le `finally` rend le verrou quelle que soit l'issue : réponse 200, 422 de schéma, panne
  d'un service appelé, exception inattendue (un test pour chacune).
- **`acquire(blocking=False)`** essaie de prendre le verrou et rend `False` sans attendre s'il est
  pris. Il n'y a pas de file : la seconde demande est refusée tout de suite.
- **`threading.Lock` plutôt qu'`asyncio.Lock`** : il se prend sans attendre, et il n'est lié à
  aucune boucle d'événements (chaque test en crée une).
- **Un verrou par route** (`slot_by_route`, `src/k_b/ai_api/app.py:79`) : une demande de fiches et
  un compte rendu peuvent tourner ensemble.
- **Quand est-il rendu ?** Une fois la réponse remise au serveur, pas une fois lue par le client :
  sur une app d'essai aux mêmes versions, avec une réponse de 50 Mo que le client ne lisait pas, le
  verrou a été rendu à 0,1 s. Si le client est parti en cours de route, la route continue jusqu'à
  son échéance (environ 200 s au plus), et le verrou avec elle.

### La fenêtre glissante

```python
        while calls and now - calls[0] >= limit.window_seconds:
            calls.popleft()
        if len(calls) >= limit.requests:
            return math.ceil(limit.window_seconds - (now - calls[0]))
        calls.append(now)
        return None
```
(`src/k_b/core/api_rate_limit.py:39-44`)

Pour chaque couple (client, route), une `deque` garde l'heure des appels admis, du plus ancien au
plus récent.

1. Les appels sortis de la fenêtre sont retirés par la gauche.
2. Si la fenêtre est pleine, l'appel est refusé **sans être compté**, et l'attente rendue est le
   temps avant que le plus ancien sorte, arrondi au-dessus (jamais 0). Elle part en `Retry-After`.
3. Sinon l'appel est compté et admis.

La taille de chaque `deque` est bornée par la limite, et il n'y a de couple que pour les clients
qu'une clé valide nomme : la mémoire est bornée. L'horloge est `time.monotonic`, qui ne recule
jamais quand on change l'heure du système ; elle est passée en paramètre, et les tests en donnent
une qu'ils avancent à la main. Pas de verrou : `check_rate_limit` est une fonction `async`,
exécutée dans la seule boucle d'événements, jamais dans deux fils à la fois.

### Les chiffres, dans `core/config.py`

```python
AI_API_RATE_LIMITS = {
    "/digests": RateLimit(requests=20, window_seconds=86_400),
    "/trend-reports": RateLimit(requests=20, window_seconds=86_400),
}
```
(`src/k_b/core/config.py:276-279`)

Ils viennent des journaux d'essai du 26 au 29/10 : au plus 7 demandes de fiches par jour (20 en
fait environ 3 fois), au plus 804 détails et 21 listes lus en une minute par l'API de données.
D'où 1 200 détails, 120 listes et 120 lectures de tendances par minute et par client. Un test
vérifie que les limites de l'API de données laissent passer une demande de fiches à son plafond
(300 items) et un compte rendu à ses 32 lectures.

### Les clients nomment les nouveaux refus

```python
    if status == httpx2.codes.FORBIDDEN:
        raise AiApiError("ai_api_forbidden", status, describe_answer(answer))
    if status == httpx2.codes.TOO_MANY_REQUESTS:
        raise AiApiError("ai_api_rate_limited", status, describe_answer(answer))
```
(`src/k_b/post/ai_api_client.py:221-224`)

Avant cette PR, un 403 ou un 429 de l'API IA serait tombé dans `ai_api_invalid_response`, ce qui
aurait été faux. `describe_answer` affiche déjà l'état, l'`X-Request-ID` et le `Retry-After`, et
`describe_remedy` nomme la variable de clé sur un 403, jamais la clé. Côté API IA, un 429 de l'API
de données devient `data_api_rate_limited`, rendu en 503 (`ai_api/connectors/data_api_client.py:370`,
`ai_api/errors.py`).

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Compteur | Écrit dans K-B, une trentaine de lignes, sans dépendance | `slowapi` 0.1.10 : un décorateur et un paramètre `request` sur chaque route, et il ajoute `limits` ; `limits` 5.8.0 : 3 dépendances, et son atout (Redis) ne sert pas ici ; une limite d'Azure : rien en local ni dans le dépôt |
| Forme de la fenêtre | Glissante : `Retry-After` exact | Fixe : une double rafale possible à la frontière de deux fenêtres |
| Droit par route | Une table et une dépendance d'app, refus par défaut | Une dépendance par routeur : une route oubliée passerait |
| Concurrence | Un verrou par route, sans file | Une file : le client attendrait jusqu'à 200 s pour rien ; `limit_concurrency` d'uvicorn : il compte aussi les connexions muettes, et 31 sockets sans clé couperaient l'API, `/health` compris (essai du relecteur du plan). Renvoyé au jalon ACA |
| Où vivent les limites | Constantes de `core/config.py` | Variables d'environnement : aucun environnement n'en demande une autre valeur (YAGNI). La « fenêtre de temps » de la règle 2 de `poc.md` est celle des données lues, pas celle d'un débit |
| Ce qui est compté | Les tentatives admises, 422 de schéma et pannes rapides compris | Les seuls appels au modèle : du code dans chaque route. Écart écrit, que Sabine a gardé |
| Limite sans clé | Aucune | Par adresse IP : derrière ACA, elle passerait par `X-Forwarded-For`, à valider ; à justifier avec la revue des 10 points |

Ces choix ont été validés par Sabine avec le plan de la PR, relu par un sous-agent. Le journal ADR
les reprend (2026-11-05, « API : un client par route, une demande à la fois, un débit par client »),
avec le revirement sur « Pas de limite de débit : le client est local ».

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_call_beyond_the_limit_gets_the_wait_of_the_oldest_call`, `test_the_wait_is_rounded_up_never_to_zero`, `test_a_call_refused_is_not_counted`, `test_the_window_slides_a_call_at_its_end_is_gone`, `test_each_client_and_each_route_has_its_own_count` (`tests/test_api_rate_limit.py`) | La fenêtre, sur une horloge réglée par le test |
| `test_every_data_route_has_its_limit`, `test_every_route_of_the_model_has_its_limit` | Chaque route a sa limite, et sur l'API IA son client ; une route ajoutée sans eux fait échouer le test |
| `test_beyond_its_limit_a_client_gets_429_before_any_reading`, `test_beyond_its_limit_a_client_gets_429_with_its_wait_and_its_id` | Au-delà de la limite : 429 avec `Retry-After` et `X-Request-ID`, sans lecture ni appel au modèle |
| `test_a_request_without_a_valid_key_consumes_no_call_of_the_limit`, `test_a_request_without_a_valid_key_counts_for_nothing` | Une requête sans clé valide ne consomme rien |
| `test_a_client_is_refused_403_on_a_route_that_is_not_its_own`, `test_the_client_of_the_digests_is_refused_on_the_trend_reports`, `test_a_route_absent_from_the_table_is_refused_to_every_client` | Le droit par route, refus par défaut compris |
| `test_while_a_request_runs_the_next_one_on_its_route_gets_429_without_a_queue` | Une vraie demande tenue dans un fil : la suivante reçoit 429 tout de suite |
| `test_the_route_is_free_again_after_*` (réponse, 422, panne amont, exception) | Le verrou est rendu dans chaque cas |
| `test_a_request_under_way_on_a_route_leaves_the_other_route_free`, `test_a_refusal_while_a_request_runs_consumes_no_call_of_the_limit`, `test_while_a_request_runs_the_key_and_the_right_are_checked_first` | Un verrou par route, et l'ordre des contrôles |
| `test_two_requests_at_once_write_whole_metric_lines_on_a_real_pipe` | Demandé par #161 : deux demandes simultanées écrivent leurs lignes `llm_call` entières, sur un vrai tube. Il passe sans code nouveau : **aucun rouge possible** |
| Tests des clients (`tests/post/test_ai_api_client.py`, `tests/commands/test_digest_command.py`, `tests/ai_api/test_data_api_client.py`) | `ai_api_forbidden` avec la variable nommée, `ai_api_rate_limited` avec son attente, `data_api_rate_limited` en 503 |
| 3 455 tests verts ; ruff, format, `mypy --strict` verts | Rien d'autre n'a cassé |
| 23 mutations sur 23 tuées (frontière de la fenêtre, arrondi, ordre des dépendances, verrou jamais rendu, un seul verrou pour deux routes, statuts des clients…) | Les tests mordent |
| Revue de sécurité (sous-agent, essais sur les vraies apps : 17 chemins × 7 méthodes × 5 clés, ASGI brut, fuites dans réponses, journal, traces et OpenAPI) | Aucune vulnérabilité ; aucun refus n'appelle le modèle, l'API de données ni GitHub |

## Ce que tu dois pouvoir défendre

1. **« 20 par jour, c'est un budget ? »** Non. Le compte vit en mémoire : redémarrer `kb serve-ai`
   ou passer à zéro réplique le remet à zéro, et il ne vaut que pour une réplique. Il arrête une
   boucle qui s'emballe, car elle garde la réplique en vie ; il n'arrête pas un voleur patient de
   clé. Le plafond de dépense reste à demander à l'école, qui tient l'abonnement.
2. **« Un attaquant sans clé peut-il épuiser la limite de `kb digest` ? »** Non : la clé est
   contrôlée en premier, et une requête refusée en 401 ne compte pas
   (`test_a_request_without_a_valid_key_consumes_no_call_of_the_limit`).
3. **« Pourquoi pas une bibliothèque comme `slowapi` ? »** Elle demande un décorateur et un
   paramètre `request` sur chaque route, et apporte `limits` et ses dépendances, pour une trentaine
   de lignes ; son atout, un compteur partagé dans Redis, ne sert pas avec une réplique.
4. **« Pourquoi refuser la seconde demande au lieu de la mettre en attente ? »** Une demande dure
   jusqu'à 200 s : le client attendrait pour rien. Un 429 avec `Retry-After: 200` lui dit quand
   revenir. Un digest et un compte rendu, eux, tournent ensemble : un verrou par route.
5. **« Que se passe-t-il après un Ctrl-C sur `make digest` ? »** L'API IA ne voit pas le départ
   du client et finit la demande jusqu'à son échéance ; la relance reçoit 429
   `request_already_running` tant qu'elle n'a pas fini, environ 200 s au plus. C'est écrit dans le
   `README.md`.

## Zones non vérifiées

- **Derrière l'entrée d'ACA** : rien n'est essayé (une réplique, passage à zéro réplique, adresse
  du client). Les limites assument `maxReplicas: 1`, à poser au jalon ACA (#317).
- **Le moment où le verrou est rendu** : observé sur une app d'essai (0,1 s avec 50 Mo non lus),
  mais le mécanisme d'uvicorn qui le permet (le tampon de son transport) n'a pas été lu dans son
  code.
- **L'horloge** : sur le Mac, `time.monotonic` lit `mach_absolute_time()` (vérifié), qui ne compte
  pas la veille ; la fenêtre s'allonge d'autant. Sur Linux, dans le conteneur, elle n'est pas
  vérifiée.
- **Les chiffres** : `/trends` et `POST /trend-reports` n'ont aucune mesure dans les journaux ;
  l'origine des 804 détails du 26/10 à 20:11 n'est pas établie (aucun `POST /digests` au journal à
  cette minute).
- **L'essai réel par Sabine** (deux `make digest` ensemble, `make trend-report` pendant un digest,
  clé des tendances sur `/digests`) n'est pas encore fait.

## Ce qui reste

- **PR 2B** de #161 : `HEAD` refusé sur `/health` et `/docs` (API8) ; un délai pour le SQL de l'API
  de données (API4).
- **PR 3** de #161 : l'auto-évaluation des 10 points de l'API IA, avec les écarts justifiés
  (anti-force brute, limite par adresse, `TrustedHostMiddleware`, Cheat Sheet, 400 d'uvicorn en
  texte brut) ; elle fermera #161.
- **Jalon ACA** : TLS, ressources du conteneur, `limit_concurrency`, `minReplicas` (décision
  ouverte au journal ADR), fichiers de déploiement.
- **Non fait, volontairement** : transmettre le `Retry-After` d'un 429 de l'API de données (presque
  impossible : 300 lectures par demande, une demande à la fois, pour une limite de 1 200 par
  minute) ; ne compter que les appels au modèle (gardé tel quel par Sabine).
