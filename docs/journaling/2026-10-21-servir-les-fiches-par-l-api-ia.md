# Servir les fiches de veille par `POST /digests` sur l'API IA fermée par une clé

- **Date** : 2026-10-21
- **Branche** : `feat/ai-api-post-digests`
- **Issue** : #156
- **Fichiers principaux** : `src/k_b/ai_api/app.py`, `src/k_b/ai_api/routers/digest_router.py`,
  `src/k_b/ai_api/metrics.py`, `src/k_b/commands/serve_ai_command.py`, `src/k_b/core/api_access.py`,
  `src/k_b/core/api_errors.py`, `src/k_b/core/api_request_log.py`, `docs/api/openapi-ia.json`
- **Série** : le parcours d'une demande (lecture, classement, rédaction, contrôles) vient de #204,
  #205 et #206 ; la note du 2026-10-21 « refuser un lien ou une balise dans une fiche » est la
  dernière avant celle-ci.

## Le pourquoi

Le parcours qui fabrique les fiches de veille existait déjà dans `ai_api/` (`digests.py` et ses
étapes), mais rien ne l'exposait : aucune route, aucune commande, aucune mesure. #156 en fait **la
seule porte de K-B vers le modèle** : une API HTTP, servie sur le Mac par `kb serve-ai`, qu'un
client n'appelle qu'avec sa clé. C'est là qu'on mesure chaque appel (jetons, durée, coût), et c'est
elle que `kb digest` (#209) appellera pour écrire les fiches dans le coffre. L'API IA ne garde
rien : elle lit la veille par l'API de données, rend les fiches, et oublie (règle 7 de `poc.md`).

Ce que les deux API ont en commun (la clé, les erreurs, le journal, la santé, la règle de l'hôte
et du port) passe dans `core/`, pour n'être écrit qu'une fois. En cours de route, Sabine a ajouté
deux harmonisations : les routeurs de l'API de données déclarent `prefix` et `tags`, et ses clés
s'appellent désormais `KB_DATA_API_KEY_<CLIENT>`, en face de `KB_AI_API_KEY_<CLIENT>`.

## Le comment

### 1. Une app fermée par une clé, sauf trois routes sans donnée

La clé est posée sur l'app entière, comme dans l'API de données : aucune route ajoutée plus tard
ne peut l'oublier.

```python
dependencies=[Depends(check_api_key)],
```
(`src/k_b/ai_api/app.py:39`)

`check_api_key` (`src/k_b/core/api_access.py`) lit le `Bearer`, compare la clé reçue à **chaque**
clé de client avec `hmac.compare_digest`, sans s'arrêter à la première égalité (le temps de réponse
ne dit pas quelle clé est bonne), et lève `ApiError(401, "invalid_api_key")` avec
`WWW-Authenticate: Bearer`. `/health` est ajoutée par `app.add_route` (`app.py:59`) : c'est une
route de Starlette, que la dépendance de l'app n'atteint pas, comme `/docs` et `/openapi.json`. Un
test parcourt toutes les routes et vérifie que ce sont les trois seules à répondre sans clé
(`tests/ai_api/test_digest_router.py`, `test_only_the_public_routes_answer_without_a_key`).

Les clés se lisent au démarrage, par préfixe : `read_api_keys_or_refusal(environ, prefix)`
(`core/api_keys.py`) sert `kb serve` (`KB_DATA_API_KEY_`) et `kb serve-ai` (`KB_AI_API_KEY_`). En
plus, `kb serve-ai` refuse de démarrer si une clé de ses clients est celle qu'il envoie lui-même à
l'API de données (`serve_ai_command.py:51`) : sinon, le client de l'IA pourrait lire toute la base.

### 2. Une route qui se lit comme une recette

```python
reading = read_window(data_api_client, since, deadline, request_id)
data_fetch_ms = round((time.perf_counter() - started) * 1000)
result = build_digests(
    llm_client, state.llm_settings, reading, state.subjects, deadline
)
```
(`src/k_b/ai_api/routers/digest_router.py:62-66`)

La route `def` (pas `async` : les clients httpx2 sont synchrones, FastAPI la lance dans un thread)
fait quatre étapes nommées : la fenêtre (`until` = l'instant de la demande à la seconde, `since` =
`until` − `window_days`), la lecture par l'API de données, le parcours `build_digests`, puis les
lignes de métrique. Un échec de lecture devient l'erreur nommée de son état (`read_window`,
`digest_router.py:113`, et `ai_api/errors.py`, `STATUS_BY_STATE`) ; un classement en échec aussi,
avec le `Retry-After` du fournisseur pour un 503 (`digest_router.py:82`). Une rédaction en échec ne
fait pas échouer la demande : elle va dans `failed_subjects`.

Les clients HTTP sont des **dépendances avec `yield`**, un par requête (`ai_api/dependencies.py:16-21`) :
fermés après la réponse, rien n'est gardé, et le replay repart de son premier pas à chaque demande.
Les tests les remplacent par `app.dependency_overrides`, le mécanisme prévu par FastAPI, ce qui
permet de brancher l'API de données de test et un replay dont on garde chaque requête.

### 3. Une demande validée avant toute lecture

```python
model_config = ConfigDict(extra="forbid", strict=True)
```
(`src/k_b/ai_api/schemas/digest_schema.py:19`)

`extra="forbid"` refuse tout autre champ ; `strict=True` refuse `true`, `3.0` et `"3"`, que le mode
souple de Pydantic aurait pris pour 3. `window_days` est borné de 1 à 14 ; absent ou `null`, c'est
`KB_DIGEST_WINDOW_DAYS`. Le refus est un 422 commun aux deux API, qui nomme le paramètre sans
jamais renvoyer une valeur reçue :

```python
if (
    len(location) < 2
    or not isinstance(location[1], str)
    or detail["type"] == EXTRA_FIELD_ERROR
):
    return BODY
```
(`src/k_b/core/api_errors.py:95-100`)

Le nom d'un champ en trop vient du client : il devient `body`. Avant, `loc[1]` était lu d'office, ce
qui renvoyait ce nom tel quel, et un corps absent (`loc` d'un seul élément) faisait un `IndexError`,
donc un 500.

### 4. Un identifiant par requête, dans le journal commun

```python
request.state.request_id = str(uuid.uuid4())
```
(`src/k_b/core/api_request_log.py:29`)

Le middleware du journal, le plus extérieur, donne à chaque requête un UUID, l'écrit en fin de sa
ligne de journal et le renvoie dans l'en-tête `X-Request-ID` (`:35`). La ligne `internal_error`, la
ligne `database_error` de l'API de données et l'échec `data_api_*` de l'API IA le reprennent ; la
réponse 200 de `/digests` et chaque ligne `llm_call` aussi. Un 502 se relie ainsi à ses lignes.

### 5. Une ligne JSON par appel au modèle, vidée aussitôt

```python
sys.stdout.write(json.dumps(line, ensure_ascii=False) + "\n")
sys.stdout.flush()
```
(`src/k_b/ai_api/metrics.py:49-50`)

Les métriques vont sur la sortie standard, sans fichier (règle 4 de `poc.md`), une ligne par
`StageCall`, avec les champs de la spec dans son ordre. Le `flush` après chaque ligne n'est pas un
détail : sur SIGTERM, uvicorn renvoie le signal une fois arrêté, et une ligne restée dans le tampon
d'un tube serait perdue. `cost_estimated` = jetons × prix au million de `core/config.py`
(`estimate_cost`, `metrics.py:102`) ; `facts_checked` et `facts_found` restent `null` jusqu'à #207.

### 6. Ce qui vient du fournisseur est borné

Une réponse du fournisseur est une entrée non fiable (OWASP API10). Deux bornes, ajoutées à la
seconde revue :

```python
type TokenCount = Annotated[int, Field(ge=0, le=MAX_TOKENS_READ_PER_ANSWER)]
```
(`src/k_b/ai_api/connectors/llm_client.py:97`)

Au-delà de 10 000 000 jetons, la réponse n'est pas lue (`llm_unavailable`) : un compteur de
309 chiffres faisait déborder le calcul du coût. Et un `Retry-After` de plus de 9 chiffres
(`RETRY_AFTER_TOO_LONG`, `:72`) termine l'appel sans nouvelle tentative : `int()` refuse 4 301
chiffres ou plus, et cette erreur sortait de la gestion de la requête.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| La clé, les erreurs, le journal, la santé, l'hôte et le port dans `core/` (`api_access`, `api_keys`, `api_errors`, `api_request_log`, `api_health`, `api_settings`) | critère de #156 : « sans être recopiés » ; l'API IA ne peut importer que `ai_api`, `items` et `core` | un `core/api_app.py` qui câblerait l'app commune : deuxième occurrence seulement, et l'ordre des middlewares diffère (`TrustedHostMiddleware` de l'API de données) |
| La vérification de la clé dans `core/api_access.py`, à part de la lecture (`core/api_keys.py`) | la lecture de l'environnement n'importe pas FastAPI | les deux dans `api_keys.py` (constat du relecteur du plan) |
| `request_id` posé par le journal commun, pour les deux API, et `X-Request-ID` | décision de Sabine (point 2 du plan) : un outil commun ne connaît pas de cas particulier ; l'en-tête relie une erreur à ses lignes | un `request_id` de l'API IA seule ; un `request_id` dans le corps d'erreur (la spec rend `{"error": …}`) |
| `kb serve-ai`, `KB_AI_API_HOST`, `KB_AI_API_PORT` (8001), `logs/kb-serve-ai.log` | décision de Sabine ; un processus long a son fichier, comme `kb serve` | `kb serve-ia`, `kb serve --ai` |
| Pas de `TrustedHostMiddleware` sur l'API IA | décision de Sabine : sans clé, une requête n'atteint que trois routes sans donnée | `KB_AI_API_ALLOWED_HOSTS` ; à revoir en conteneurs (#200) et par #161 |
| `APIRouter(prefix="/digests", tags=["digests"])` et `@router.post("")` | décision de Sabine : suivre la doc FastAPI (skill `fastapi`, `references/path-operations.md`) et le critère du 17/10 ; l'API de données suit la même règle | le chemin entier dans le décorateur sans `prefix` (forme de l'API de données jusque-là) |
| Les clés de l'API de données renommées `KB_DATA_API_KEY_<CLIENT>` ; la constante `API_KEY_VARIABLE_PREFIX` garde son nom | décision de Sabine : tous ses réglages s'écrivent `KB_DATA_API_*` | garder `KB_API_KEY_`, qui faisait lire `KB_API_KEY_AI_DIGEST` comme une clé de l'API IA |
| Les enveloppes `read_llm_settings` et `read_data_api_settings` retirées ; la porte lit `read_*_or_refusal` et journalise par `value_or_log_refusal` sous `k_b.cli` | règle de la « porte mince » (ADR 2026-10-18) ; plus de copie du motif | déplacer `value_or_log_refusal` dans `core/` (la fonction n'a qu'un appelant, `commands/`) |
| Les sujets passés à `create_app` | les tests gardent leurs propres sujets (`fiches-veille.md`, « Sujets ») | `DIGEST_SUBJECTS` en dur dans la route (constat du relecteur) |
| Un 503 `llm_rate_limited` sans `Retry-After` quand le fournisseur n'en donne pas | K-B ne dit que l'observé | envoyer `LLM_RETRY_WAIT_SECONDS`, une attente inventée |
| Prix : 0,12 et 0,60 USD par million, toute requête comptée, replay compris | point 7 du plan, validé ; une formule, testable ; le champ `provider` distingue le replay | 0 pour le replay (une branche de plus) |
| Le journal de `kb` ne garde d'httpx2 que les `WARNING` | constat de la démonstration : ses lignes INFO n'avaient pas de `request_id` et auraient porté l'URL de la ressource Azure | les laisser |
| Le type `LlmFailure`, sans `"ok"` | l'OpenAPI annonçait `"ok"` comme erreur d'un sujet (seconde revue) | garder `LlmOutcome` et un test seul |
| Un corps illisible (400 de FastAPI) devient 422 `["body"]` | critère : une demande mal formée est refusée en 422 ; seul ce 400 existe dans FastAPI 0.143 et Starlette 1.8 hors formulaire | comparer le texte du `detail` (fragile) |

Les constats des revues sont **tranchés par time-knight, délégation de Sabine du 2026-10-15**.

**Écart à la méthode** : le code de la route a été écrit avant ses tests (règle 3 de `methode.md`).
Pour s'assurer que les tests mordent, cinq mutations ont été faites puis annulées, chacune tuée :
le `flush` retiré (1 test en échec), la règle du 400 retirée (2), le nom d'un champ en trop renvoyé
(1), le mode strict retiré (3), le `Retry-After` non transmis (1). Les corrections suivantes ont
toutes été écrites test d'abord.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_request_gives_a_digest_per_subject_with_its_window_and_its_id` | la réponse 200 de la spec, `request_id` = `X-Request-ID`, la fenêtre à la seconde |
| `test_a_malformed_request_is_refused_422_before_any_call` (10 cas) | 422 avant toute requête au modèle ; un champ en trop n'est jamais nommé |
| `test_without_key_only_a_body_that_cannot_be_read_gets_422` | la limite de FastAPI : seul un corps illisible reçoit 422 sans clé |
| `test_a_classification_that_fails_fails_the_request_with_its_lines` (502, 503 avec et sans `Retry-After`, 504) | les erreurs nommées et leurs lignes `llm_call` |
| `test_a_reading_that_fails_fails_the_request_without_a_call_to_the_model` | `data_api_*` → 502/504, journalisé avec le `request_id`, aucune ligne de métrique |
| `test_each_call_writes_one_json_line_on_stdout_without_a_text`, `test_each_metric_line_is_flushed_at_once` | une ligne par appel, champs dans l'ordre, ni texte ni titre, vidée aussitôt |
| `test_serve_ai_exits_2_and_names_the_variable_refused` (12 cas), `test_serve_ai_exits_2_when_a_client_has_the_key_it_sends_to_the_data_api` | aucun démarrage sur un réglage refusé ; jamais une clé au journal |
| `test_serve_ai_stops_on_sigterm_with_the_code_of_a_process_stopped_by_it` | un vrai processus, arrêté par SIGTERM : `-15` (143 pour un shell) |
| `test_the_versioned_openapi_is_the_one_the_app_produces` et suivants (`test_ai_api_openapi.py`) | OpenAPI versionnée, valide, indépendante des réglages, sans `"ok"` |
| `test_each_router_of_an_api_declares_its_prefix_and_its_tags` | la règle des routeurs, dans les deux API |
| Démonstration sur le Mac (replay, base de test aux dates ramenées au 2026-10-20) | `/health` 200 ; 401 sans clé et clé inconnue ; 422 pour 15 jours ; 200 avec 3 fiches et 4 lignes `llm_call` ; second `kb serve-ai` : code 3 ; SIGTERM : 143 ; aucune clé dans les sorties (`grep -F`) |
| `uv run pytest` : 2083 tests ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` | les contrôles de la CI |

## Ce que tu dois pouvoir défendre

1. **Pourquoi la clé sur l'app et pas sur le routeur ?** Une dépendance d'app s'applique à toute
   route ajoutée par FastAPI : un routeur ajouté demain ne peut pas l'oublier. `/health`, `/docs`
   et `/openapi.json` sont des routes de Starlette, hors de son atteinte, et un test le vérifie
   (`app.py:39`, `test_only_the_public_routes_answer_without_a_key`).
2. **Un client sans clé peut-il faire dépenser des appels au modèle ?** Non : la clé est vérifiée
   avant la lecture et avant tout appel ; sans elle, 401. Seul un corps qui n'est pas du JSON passe
   avant la clé, et il est refusé en 422 sans rien lire ni appeler (`fastapi/routing.py`, limite
   écrite dans `fiches-veille.md`, « Demande »).
3. **Comment sait-on ce qu'a coûté une demande ?** Chaque appel écrit sa ligne `llm_call` avec
   jetons et `cost_estimated`, reliée à la demande par son `request_id` (`metrics.py`). Limite : un
   replay est compté au prix de gpt-6-luna, et une demande sans appel n'écrit aucune ligne.
4. **Que se passe-t-il si le fournisseur répond n'importe quoi ?** La réponse est revalidée : son
   enveloppe par un modèle Pydantic strict, ses compteurs bornés, son `Retry-After` borné ; la sortie
   par les contrôles 1 à 6. Hors schéma : un état nommé, jamais un 500 (`llm_client.py:97`,
   `STATUS_BY_STATE` et son test d'exhaustivité).
5. **Pourquoi une clé de client ne peut-elle pas être celle de `AI_DIGEST` ?** L'API de données donne
   tout à chaque client : partager cette clé ouvrirait la base au client de l'IA. Seule celle-là est
   comparée (décision de Sabine) : sur le Mac, `kb digest` lit déjà tout l'environnement.

## Zones non vérifiées

- **SIGTERM en PID 1** (conteneur) : uvicorn renvoie le signal, qu'un PID 1 ignore ; non essayé
  (#200).
- **Prix** : lus dans l'API de prix de détail d'Azure, pas sur une facture ; « contexte court » est
  supposé pour nos appels (environ 9 000 jetons), la frontière exacte du contexte long n'a pas été
  lue.
- **Le vrai modèle** : tout passe par le replay ; le comportement de gpt-6-luna derrière
  `POST /digests` relève de #210.
- **Concurrence** : FastAPI lance la route dans un pool de threads ; deux demandes simultanées
  écriraient leurs lignes sur le même stdout. Une seule demande à la fois est supposée (spec) ; non
  essayé.
- **Le décompte injecté par le skill** (151 fichiers) part d'une base plus ancienne que
  `origin/main` : la branche ne compte que 13 commits et 55 fichiers (`git diff --stat
  origin/main...HEAD`), ceux que cette note couvre ; les autres fichiers de la liste viennent de
  PR déjà fusionnées.

## Ce qui reste

- `kb digest`, l'écriture des fiches dans le coffre, et son comportement sur un 401 (#209).
- La fidélité, et `facts_checked` / `facts_found` (#207).
- Les métriques vers Grafana Cloud (#162, #164) : une ligne de mesures de la demande, le filtre du
  replay dans les tableaux de coût.
- Les bornes de consommation de l'API IA : requêtes simultanées et taille du corps (#161).
- Les conteneurs (#200) : `KB_DATA_DIR` sans volume, une clé distincte par conteneur, l'hôte
  appelant.
- Le format de date à mettre dans `core/` (`format_timestamp` et `format_since` le recopient), et
  l'harmonisation de la lecture de l'environnement (une valeur vide refusée ici, « non réglée »
  là).

## Sources

| Source | Consultée | Pour |
|---|---|---|
| Skill `fastapi` (`.claude/skills/fastapi`, lien vers le paquet installé) : `SKILL.md`, `references/dependencies.md`, `path-operations.md`, `responses.md`, `pydantic.md` | 2026-10-21 | `Annotated`, `yield`, `prefix` et `tags`, type de retour, ni `...` ni `RootModel` |
| [FastAPI, « Testing Dependencies with Overrides »](https://fastapi.tiangolo.com/advanced/testing-dependencies/), lu par Context7 | 2026-10-21 | `app.dependency_overrides` dans les tests |
| Code installé : `fastapi/routing.py:446`, `:464`, `:485`, `:499` (0.143.1) ; `starlette/requests.py:297`, `:311` (1.8.0) ; `uvicorn/server.py` (0.54.0) | 2026-10-21 | le corps lu avant les dépendances ; les seuls 400 ; le signal renvoyé |
| [Azure Retail Prices overview](https://learn.microsoft.com/ar-sa/rest/api/cost-management/retail-prices/azure-retail-prices), Microsoft Learn, rendue par une recherche du jour ; requête à `https://prices.azure.com/api/retail/prices` | 2026-10-21 | 0,12 et 0,60 USD par million (compteurs `6-luna ShortCo Inp Std DZ` et `Opt Std DZ`, France Central, en vigueur au 2026-09-01) |
| [GPT-6 Luna Azure Pricing](https://www.azurespeed.com/AzureAiModelPricing/Models/openai-gpt-6-luna), agrégateur tiers | 2026-10-21 | recoupement des prix |
| [RFC 9110, § 15.6](https://www.rfc-editor.org/rfc/rfc9110#section-15.6) et § 10.2.3 (déjà citée par la spec) | 2026-10-15 | 502, 503, 504 d'une passerelle ; `Retry-After` en secondes |
| [OWASP API Security Top 10 (2023)](https://api-security.owasp.org/), API2, API4, API8, API10 (`conformite.md`) | 2026-10-04 | clé par client, bornes, hôtes permis, réponse d'amont non fiable |
