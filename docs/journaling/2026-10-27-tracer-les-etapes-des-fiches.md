# Tracer chaque étape de `POST /digests` vers Grafana Cloud

- **Date** : 2026-10-27
- **Branche** : `feat/trace-digest-steps`
- **Issue** : #345
- **Fichiers principaux** : `src/k_b/ai_api/tracing.py` (nouveau),
  `src/k_b/ai_api/connectors/trace_export.py` (nouveau), `src/k_b/ai_api/connectors/llm_client.py`,
  `src/k_b/ai_api/stages/classification.py`, `src/k_b/ai_api/stages/fidelity.py`,
  `src/k_b/ai_api/stages/checking.py`, `src/k_b/ai_api/digests.py`,
  `src/k_b/ai_api/routers/digest_router.py`, `src/k_b/ai_api/app.py`,
  `tests/ai_api/test_tracing.py`, `tests/ai_api/test_trace_export.py`,
  `tests/architecture/test_apis.py`
- **Série** : suit [Émettre les métriques du modèle en OpenTelemetry](2026-10-24-emettre-les-metriques-en-opentelemetry.md)
  (#162), dont elle reprend l'exportation.

## Le pourquoi

L'essai 1 de #210 (26/10) a retiré 50 affirmations sur 92, et personne ne pouvait dire pourquoi
sans rejouer la demande avec un script. K-B n'émettait que des métriques : des nombres, agrégés par
minute, sans lien entre eux. Une métrique dit « 50 affirmations retirées » ; elle ne dit pas
lesquelles, dans quel sujet, ni quel contrôle les a refusées.

Une **trace** répond à cette question. C'est l'arbre d'une demande : un nœud (un *span*) par
étape, avec son début, sa fin, son état et ses attributs. On l'ouvre dans Grafana (Tempo), on voit
que le sujet `agent_tools` a envoyé les items 6, 7 et 8, que sa rédaction a demandé deux requêtes
au modèle, et que l'affirmation n° 1 a été retirée parce que son fait n° 1 n'est pas dans l'item 6.

Ce travail est la première moitié : la structure et les raisons, **sans aucun texte** (ni
consigne, ni item, ni réponse du modèle), ce que la règle 5 de `poc.md` permet telle quelle. Le
contenu viendra dans une PR à part, après la signature du DPA de Grafana.

## Le comment

### 1. Une façade, passée de main en main comme le délai

Le code des étapes ne parle jamais à OpenTelemetry directement. Il reçoit un objet `Tracing` et
ouvre un span par un bloc `with` :

```python
        error: Exception | None = None
        with trace.use_span(
            span, record_exception=False, set_status_on_exception=False
        ):
            try:
                yield step
            except Exception as raised:
                error = raised
                raise
            finally:
                step.end(error)
```
(`src/k_b/ai_api/tracing.py:125-135`)

`use_span` rend le span *courant* pendant le bloc : tout span ouvert à l'intérieur devient son
enfant, sans qu'on le lui dise. `record_exception=False` est le point de sécurité : par défaut,
OpenTelemetry copie le message de l'exception dans la trace, et le message d'une erreur de K-B
peut citer un item (une `ValidationError` cite la valeur reçue). Ici, une exception laisse
seulement le **nom de son type** dans `error.type` (`Step.end`, `tracing.py:84`). Le `finally`
ferme le span dans tous les cas, même sur une erreur.

`Tracing` arrive dans chaque fonction par un paramètre mot-clé, `tracing=`, avec un défaut,
`TRACING_OFF`, qui n'enregistre rien (`tracing.py:158`). C'est le même procédé que `deadline` ou
`sleep=` : la dépendance est donnée, pas cherchée dans une variable globale. Le défaut a un piège :
une fonction qui oublie de transmettre `tracing` éteint sans bruit tout ce qui est en dessous. Un
test lit donc le code source (`tests/architecture/test_apis.py`,
`test_a_function_of_ai_api_that_takes_tracing_gets_it_by_name`) : dans `ai_api`, tout appel à une
fonction qui déclare `tracing` doit le passer par son nom.

### 2. L'arbre d'une demande

La racine s'ouvre dans la route, et nomme l'état d'un échec :

```python
        except ApiError as error:
            root.fail(error.state)
            root.set({HTTP_STATUS: error.status_code})
            raise
```
(`src/k_b/ai_api/routers/digest_router.py:74-77`)

`ApiError` est l'erreur nommée de K-B (`llm_invalid_output`, `data_api_timeout`…) : la racine en
garde l'état et le code HTTP, puis relance l'erreur pour que FastAPI réponde comme avant. Sous la
racine : `read_watch` (la lecture de la veille), un `classify_batch` par lot de classement, un
`write_subject` par sujet. Ce dernier englobe la rédaction **et** ses contrôles, ce qui permet de
lire, sur un même nœud, les items envoyés (`k_b.items.sent.ids`) et ceux que les contrôles ont fait
tomber (`k_b.items.removed_by_checks.ids`). Un sujet sauté (après un 429, ou faute de temps) est
un `write_subject` en erreur, sans enfant (`find_skipped_state`, `digests.py:149`).

### 3. Un span par requête au modèle

```python
            attempt = send_and_check(
                http_client, body, output_model, check_output, timeout
            )
            trace_attempt(step, attempt)
        span_refs.append(step.ref)
```
(`src/k_b/ai_api/connectors/llm_client.py:262-266`)

Chaque requête HTTP envoyée au modèle est un span `chat <model>`, avec ses jetons, sa fin
(`finish_reasons`), son code HTTP et le contrôle qui l'a refusée. Une relance est donc un second
span, `k_b.attempt = 2`. Sa référence (`step.ref`, un `SpanRef`) est gardée : celle de la dernière
tentative part dans `LlmCall.span_ref`, et sert au point suivant.

### 4. Le pourquoi d'une affirmation retirée

Le contrôle de fidélité ne rendait qu'un booléen. Il rend maintenant des codes :

```python
    refusals = [
        f"{FACT_NOT_FOUND}:{index}:{item_by_ref[fact.item_id].item_id}"
```
(`src/k_b/ai_api/stages/fidelity.py:130-131`)

`fact_not_found:1:6` veut dire : le fait n° 1 de l'affirmation n'est pas dans l'item 6. Les
autres codes sont fixes : `undeclared_identifier`, `cited_item_without_fact`, `disguised_text`, et
`out_of_bounds` pour les bornes (`checking.py`, `list_removal_reasons`). `Digest` garde chaque
affirmation retirée avec sa position et ses codes (`RemovedClaim`). `is_faithful` devient une
propriété : vrai s'il n'y a aucun code, ce qui garde les 151 tests existants de la fidélité.

Chaque affirmation retirée devient un **enregistrement de journal** OpenTelemetry,
`gen_ai.evaluation.result`, rattaché au span de la requête qui l'a écrite :

```python
        self.logger.emit(
            timestamp=ref.ended_ns,
            context=trace.set_span_in_context(NonRecordingSpan(ref.span_context)),
```
(`src/k_b/ai_api/tracing.py:141-143`)

Le span `chat` est déjà fermé quand les contrôles tournent. `NonRecordingSpan` reconstruit un
contexte à partir de ses identifiants, ce qui suffit pour que l'enregistrement porte le bon
`trace_id` et le bon `span_id` : Grafana l'affiche alors sous « Logs for this span ». La date est
celle de la fin du span, pour qu'il tombe dans sa fenêtre de temps.

### 5. L'export et l'arrêt

`connectors/trace_export.py` construit les deux fournisseurs (spans, journaux) sur la même URL de
base que les métriques : `/v1/traces` et `/v1/logs` au lieu de `/v1/metrics`, le même en-tête, une
seule ressource. Chaque envoi attend 3 s au plus. Les lignes que le SDK écrit en cas d'échec passent
par le `QuotingFilter` de #162, posé sur quatre journaux nommés (`trace_export.py:35`).

À l'arrêt, les trois fournisseurs se vident **en même temps** :

```python
    await asyncio.gather(
        run_in_threadpool(app.state.model_metrics.stop),
        run_in_threadpool(app.state.trace_export.stop_traces),
        run_in_threadpool(app.state.trace_export.stop_logs),
    )
```
(`src/k_b/ai_api/app.py:81-85`)

Un arrêt peut envoyer deux fois : le lot en cours, puis le reste. En série, il faudrait 2 × 3 +
2 × 3 + 5 = 17 s, au-delà des 10 s que `docker stop` laisse avant de tuer le processus. En
parallèle, on attend seulement le plus lent : 6 s.

## Choix faits et options écartées

| Choix | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Grafana Cloud seul, en dev et en prod (Sabine, 27/10, 11:23 UTC) | il reçoit déjà les métriques et relie un span à ses journaux | Jaeger en local + Honeycomb (deux outils, un sous-traitant de plus) ; Grafana + Langfuse (un sous-traitant de plus) |
| Spans ouverts en ligne par une façade passée en paramètre | un 500 garde sa trace, tout se voit en direct, OpenTelemetry reste hors des étapes | spans construits après coup (un 500 perd tout) ; API OpenTelemetry dans les étapes ; racine dans un middleware (perd l'état nommé) ; span natif de FastAPI (porte `url.path`, `url.query`, `server.address`) |
| Un span `chat` par requête HTTP | les deux relances de K-B diffèrent (attente, ou rappel après un contrôle raté) | un span par appel, comme la convention GenAI |
| Les raisons en journal OTLP | OpenTelemetry déprécie les événements de span | événements de span |
| Une seule évaluation par affirmation, `k_b.claim_checks` (choix de time-knight au code, à valider) | le critère de #345 en demande une par affirmation ; les codes disent laquelle des deux a refusé | deux évaluations, `k_b.claim_bounds` et `k_b.fidelity` (plan v3) |
| 3 s par envoi, arrêt en parallèle | 6 s au plus, sous les 10 s de `docker stop` | 5 s comme les métriques (2 × 5 = 10 s) ; arrêt en série |
| Le sujet, le `request_id`, les identifiants d'items et les codes envoyés à Grafana (Sabine, 27/10, « je valide ») | sans eux, une trace ne dit pas quelle demande ni quel item ; aucun n'est une donnée personnelle | rien de tout cela (le registre l'interdisait : la décision l'inverse pour les traces) |
| OpenTelemetry borné sous 1.46 (Sabine, 27/10, « je valide ») | les journaux et leur exporteur sont des modules privés qui changent d'une version à l'autre | aucune borne |
| La note sur les angles morts en commentaire, pas dans la docstring de la route | la docstring de la route est sa description dans l'OpenAPI publique (le test de l'OpenAPI l'a montré) | la docstring |

## Preuve

| Test ou sortie | Ce que ça démontre |
|---|---|
| `test_a_request_is_a_trace_of_its_steps` (`tests/ai_api/test_digest_router.py`) | l'arbre a la forme attendue : noms, types, parents, aucun échec |
| `test_a_subject_that_fails_or_is_skipped_is_a_span_in_error` | un 429 met le sujet en erreur, et les sujets suivants, sautés, aussi, sans requête |
| `test_a_request_that_fails_names_its_state_and_its_status_on_the_root` | un `ApiError` donne `error.type = llm_invalid_output` et le code 502 sur la racine |
| `test_an_unexpected_error_names_its_type_never_its_text_on_the_root` | un 500 imprévu donne le nom du type, aucun événement, et son texte n'est nulle part |
| `test_no_value_holds_a_text_of_the_items_or_of_the_output` | aucun mot des titres ni des affirmations n'est dans une valeur ; chaque valeur tient en 2 048 octets |
| `test_each_claim_removed_is_an_evaluation_tied_to_its_last_request` | `fact_not_found:1:6`, rattaché au `span_id` du dernier `chat` du sujet, sans `exception.*` |
| `test_each_request_is_a_chat_span_and_the_call_keeps_the_last` (`test_llm_client.py`) | les attributs de la convention, deux spans pour une relance, `span_ref` = le second |
| `test_a_function_of_ai_api_that_takes_tracing_gets_it_by_name` (`test_apis.py`) | aucun appel n'oublie `tracing=` |
| `test_a_private_module_of_opentelemetry_is_imported_by_the_export_of_the_traces_only` | seul `trace_export.py` importe les modules privés du SDK |
| `test_the_measures_the_spans_and_the_logs_are_sent_at_once_when_the_app_stops` | les trois arrêts tournent en même temps (une barrière à trois : en série, elle casserait) |
| `test_a_stop_against_an_endpoint_that_never_answers_is_bounded_and_quotes_nothing` (`test_trace_export.py`) | contre un point d'entrée local muet, l'arrêt dure 0,30 s pour un délai de 0,3 s |
| `test_an_exporter_that_raises_is_logged_by_the_type_of_its_error_never_its_text` | la ligne du SDK devient `Exception while exporting 'Span'. (ValueError)`, sans le texte |
| `uv run pytest` : 2 669 tests ; `mypy --strict src`, `ruff check`, `ruff format --check` | rien d'autre n'a cassé |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas avoir activé la télémétrie native de FastAPI ?** Son span racine porte
   `url.path`, `url.query` et `server.address`, et reprend un `traceparent` envoyé par le client :
   un client pourrait rattacher nos spans à sa propre trace. Et il ne connaît pas l'état nommé
   d'un échec. La racine est donc ouverte par la route (`digest_router.py:62`).
2. **Que se passe-t-il si Grafana ne répond plus ?** L'envoi se fait dans un fil à part
   (`BatchSpanProcessor`) : la demande n'attend jamais Grafana. Un lot qui ne part pas en 3 s est
   perdu, avec une ligne de l'exporteur, filtrée. À l'arrêt, 6 s au plus
   (`test_trace_export.py`).
3. **Où est la protection des données ?** Aucun texte n'entre dans un attribut : les étapes ne
   posent que des comptes, des états et des identifiants entiers ; les exceptions ne sont jamais
   enregistrées (`record_exception=False`) ; un test cherche les mots des items et des affirmations
   dans toutes les valeurs. Ce que Grafana reçoit est inscrit au registre (décision D0).
4. **Pourquoi un paramètre plutôt qu'un fournisseur global ?** Un global se règle une fois par
   processus : les tests ne pourraient pas lire leurs propres spans sans se gêner, et FastAPI
   pourrait le remplacer (`FASTAPI_OTEL_AUTO_CONFIGURE`, coupé depuis #162). Le paramètre se lit
   dans la signature, et le test AST garantit qu'il n'est pas oublié.
5. **Pourquoi la raison d'un retrait est-elle un journal et pas un attribut du span ?** Il y a une
   raison par affirmation, jusqu'à 12 par sujet, et OpenTelemetry déprécie les événements de span.
   Un enregistrement par affirmation, rattaché au span, se filtre et se compte dans Grafana.

## Zones non vérifiées

- **Rien n'est encore parti vers Grafana.** Tous les tests tournent en mémoire. Restent à voir à
  l'essai réel, lancé par Sabine : que Tempo montre l'arbre, que Loki accepte l'enregistrement
  `gen_ai.evaluation.result`, et que « Logs for this span » l'affiche. Sa fenêtre de temps n'a pas
  été lue.
- **Le délai de 3 s** n'a pas été mesuré contre Grafana Cloud.
- **La coupe d'une liste d'identifiants** suppose que Grafana compte 2 Ko sur la liste écrite avec
  des virgules ; sa doc parle de la longueur d'un attribut, sans dire comment il compte un tableau.
- **Le champ `realm` de la politique d'accès** couvrait, le 27/10, toute l'organisation, et non la
  seule pile (le registre le dit, à vérifier).
- **La durée de conservation des traces et des journaux** de l'offre gratuite n'a pas été relevée.

## Ce qui reste

- **La PR 2** : le contenu des appels au modèle (`KB_TRACE_CONTENT`), après la signature du DPA et
  les décisions D1 (ce qu'est une anomalie) et D2 (le texte de l'amendement de la règle 5). Le
  critère de #163 (« texte des prompts jamais émis ») sera à réécrire à ce moment.
- **#281** : le `traceparent` vers l'API de données, et le `trace_id` dans les lignes de journal.
- **Les angles morts** : un 401 et un 422 n'ont pas de trace ; une erreur après le `return` de la
  route laisse une racine à 200.

## Sources

| Source | Lien | Lue le |
|---|---|---|
| Conventions GenAI, span d'inférence | https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/client-inference.md | 2026-10-27 |
| Conventions GenAI, `gen_ai.evaluation.result` | https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-events.md | 2026-10-27 |
| Dépréciation des événements de span | https://opentelemetry.io/blog/2026/deprecating-span-events/ | 2026-10-27 |
| `Logger.emit` du SDK Python | https://opentelemetry-python.readthedocs.io/en/stable/sdk/_logs.html | 2026-10-27 |
| Grafana Cloud Traces, 2 Ko par attribut | https://grafana.com/docs/grafana-cloud/whats-new/2025-01-17-higher-reliability-for-grafana-cloud-traces-with-new-limits-on-attribute-size | 2026-10-27 |
| Grafana Cloud, un jeton pour les trois signaux | https://grafana.com/docs/grafana-cloud/observe-and-act/agent-observability/get-started/grafana-cloud/ | 2026-10-27 |
