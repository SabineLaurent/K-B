# Émettre les métriques du modèle en OpenTelemetry vers Grafana Cloud

- **Date** : 2026-10-24
- **Branche** : `feat/otel-metrics`
- **Issue** : #162
- **Fichiers principaux** : `src/k_b/ai_api/connectors/metrics_export.py`,
  `src/k_b/ai_api/metric_instruments.py`, `src/k_b/ai_api/app.py`,
  `src/k_b/ai_api/routers/digest_router.py`, `src/k_b/commands/serve_ai_command.py`,
  `tests/ai_api/test_metrics_export.py`, `tests/e2e/test_real_export.py`
- **Série** : suit [Servir les fiches par l'API IA](2026-10-21-servir-les-fiches-par-l-api-ia.md),
  qui a créé la ligne JSON `llm_call`.

Les commits de la branche sont `736c46c` à `536db46`. Les autres commits listés par l'outil qui
a préparé cette note sont ceux de `main`, déjà fusionnés : ils ne sont pas couverts ici.

## Le pourquoi

Chaque appel de l'API IA au modèle écrit déjà une ligne JSON sur la sortie standard : durées,
jetons, coût, état. Une ligne se lit, mais elle ne se trace pas en courbe et ne déclenche pas
d'alerte. La certification juge la surveillance du modèle (C11) absente : aucun outil intégré,
aucune restitution, aucune chaîne en marche. Le cadrage du 20/10 (journal ADR, « Squelette E1 E3 »,
décision 4) a choisi OpenTelemetry et Grafana Cloud, en région UE, dès le premier temps.

#162 est le premier maillon de cette chaîne. `kb serve-ai` émet les mêmes mesures en métriques
OpenTelemetry et les envoie en OTLP à Grafana Cloud quand l'URL et l'en-tête d'authentification
sont réglés. Sans eux, rien ne part. La ligne JSON reste, inchangée. Les tableaux de bord et les
alertes viendront avec #164.

## Le comment

### 1. OpenTelemetry en quatre pièces

OpenTelemetry est un standard ouvert pour émettre des mesures, des traces et des journaux. K-B
n'utilise ici que les mesures. Le SDK Python se monte en quatre pièces.

- **La ressource** dit qui émet : le nom du service, son environnement. Elle accompagne chaque
  envoi.
- **Le fournisseur de mesures** (`MeterProvider`) relie la ressource, les lecteurs et les
  instruments. Il donne un `Meter`, qui fabrique les instruments.
- **Les instruments** reçoivent les mesures. Un *Counter* additionne : jetons, coût, appels. Un
  *Histogram* range chaque valeur dans des seaux : c'est ce qui permet de tracer une médiane ou un
  95e centile des durées.
- **Le lecteur périodique et l'exporteur** : toutes les 60 s, le lecteur agrège les mesures et
  l'exporteur OTLP les envoie en HTTP (protobuf, gzip).

L'assemblage tient dans `build_meter_provider` :

```python
    reader = PeriodicExportingMetricReader(
        build_exporter(settings),
        export_interval_millis=METRICS_EXPORT_INTERVAL_SECONDS
        * MILLISECONDS_PER_SECOND,
```
(`src/k_b/ai_api/connectors/metrics_export.py:160-163`)

Sans réglage d'export, le fournisseur est créé **sans lecteur**
(`metrics_export.py:158-159`) : les instruments existent, le routeur les appelle de la même
façon, mais les mesures sont jetées. Le code du routeur ne connaît donc pas la différence.

### 2. Les mesures d'un appel, avec des attributs fermés

`ModelMetrics.record_calls` reprend les champs de la ligne JSON, appel par appel :

```python
            attributes: dict[str, str | bool] = {
                "gen_ai.operation.name": OPERATION_NAME,
                # What K-B knows: openai_compatible or replay, not the company behind the URL.
                "gen_ai.provider.name": llm_settings.provider,
                "gen_ai.request.model": llm_settings.model,
                "k_b.stage": stage_call.stage,
            }
```
(`src/k_b/ai_api/metric_instruments.py:112-118`)

Un **attribut** est une étiquette de la mesure : Grafana s'en sert pour filtrer et regrouper.
Chaque valeur vient d'une liste fermée : le fournisseur est `openai_compatible` ou `replay`,
l'étape `classify` ou `write`, l'état un des états `llm_*`. Jamais le sujet, le `request_id`, un
titre ni un texte : la règle 5 de `poc.md` interdit le texte et l'auteur dans une métrique, et une
valeur libre multiplierait les séries. Un appel en échec ajoute `error.type`, qui reprend son état
(`metric_instruments.py:120-124`).

Les noms suivent les conventions d'OpenTelemetry pour l'IA générative quand elles en ont un
(`gen_ai.client.inference.duration`, `gen_ai.client.inference.usage.input_tokens`), et l'espace
`k_b.` sinon (`k_b.llm.cost`, `k_b.llm.calls`). Ces conventions ont le statut *Development* et ont
déménagé dans le dépôt `semantic-conventions-genai`. Le paquet Python installé avec le SDK a encore
les anciens noms : K-B suit le texte des conventions.

La durée de lecture de la veille (`k_b.digest.data_fetch.duration`) est enregistrée à chaque
demande lue, même sans appel au modèle (`digest_router.py:65`). C'est une décision de Sabine du
24/10 : la ligne JSON ne la portait pas dans ce cas.

### 3. Les réglages : trois variables à K-B, aucune variable `OTEL_*`

Le SDK sait lire seul ses variables standard (`OTEL_EXPORTER_OTLP_ENDPOINT`,
`OTEL_EXPORTER_OTLP_HEADERS`…). K-B ne s'en sert pas, et refuse même de démarrer si l'une est
présente :

```python
    opentelemetry_names = sorted(
        name for name in environ if name.startswith(OPENTELEMETRY_VARIABLE_PREFIX)
    )
    if opentelemetry_names:
```
(`src/k_b/ai_api/connectors/metrics_export.py:74-77`)

La raison est dans le code du SDK 1.45.1 : même quand K-B lui passe l'en-tête, il relit
l'environnement et y fusionne ce qu'il trouve (`_resolve_headers`). Un en-tête mal formé y est
journalisé tel quel, donc avec le jeton. D'autres variables changent son comportement en silence :
`OTEL_SDK_DISABLED`, l'intervalle d'envoi, les attributs de ressource. Refuser tout le préfixe est
une règle fermée, qui ne prend pas de retard sur la version suivante du SDK.

K-B lit donc ses trois variables, les contrôle et passe chaque valeur à l'exporteur :

- `KB_OTLP_ENDPOINT` : l'URL de base, `https` seulement, sans utilisateur, requête ni fragment
  (`find_url_refusal`, la règle de `core/outbound.py`). K-B ajoute `/v1/metrics`, et refuse une
  URL qui le porte déjà (`metrics_export.py:94-96`).
- `KB_OTLP_HEADERS` : les paires `nom=valeur` au format OTLP, comme Grafana Cloud les donne
  (`Authorization=Basic%20…`). Le lecteur `parse_headers` (`metrics_export.py:120-135`) décode
  chaque valeur, puis exige un nom de jeton HTTP et une valeur ASCII imprimable. Il est plus strict
  que celui du SDK et que le contrôle de `requests`, qui citerait la valeur refusée. Les valeurs
  restent en `SecretStr` : jamais journalisées, jamais citées dans un refus.
- `KB_DEPLOYMENT_ENVIRONMENT` : `sandbox` ou `production`, sans défaut, exigée dès que l'export est
  réglé. Décision de Sabine du 24/10 : avec un défaut `sandbox`, une production oubliée serait mal
  étiquetée sans message.

Les deux premières vont ensemble : une seule présente arrête le démarrage (`NOT_STARTED`).

### 4. Une ressource fermée, une session HTTP aveugle à l'environnement

La ressource est construite par son constructeur, avec trois attributs seulement :

```python
    attributes: dict[str, str] = {
        "service.name": SERVICE_NAME,
        "service.instance.id": str(uuid.uuid4()),
    }
```
(`src/k_b/ai_api/connectors/metrics_export.py:145-148`, puis l'environnement s'il est réglé)

`Resource.create`, la voie que la doc du SDK présente d'abord, lit `OTEL_RESOURCE_ATTRIBUTES` et
lance les détecteurs listés dans `OTEL_EXPERIMENTAL_RESOURCE_DETECTORS`. Le détecteur `process`
ajoute la ligne de commande et le propriétaire du processus. Le critère de #162 les interdit, avec
`host.name` et tout chemin. `service.instance.id` est un UUID tiré à chaque démarrage : sans lui,
deux processus qui exportent en même temps écriraient les mêmes séries cumulées (constat de la
revue). Ce n'est pas une donnée personnelle.

L'exporteur envoie par `requests`. La session lui est passée avec `trust_env = False`
(`metrics_export.py:177-178`) : elle ne lit ni proxy, ni certificat, ni `.netrc` de
l'environnement, comme le client `httpx2` de `core/outbound.py`. Le `.netrc` pourrait sinon
remplacer l'en-tête `Authorization`.

### 5. Le dernier envoi à l'arrêt

Les mesures attendent jusqu'à 60 s en mémoire. À l'arrêt, `shutdown()` du fournisseur les envoie.
Le premier plan l'appelait après le retour de `uvicorn.run`. La relecture du plan a montré que ce
code n'est jamais atteint sur SIGTERM : uvicorn finit les demandes en cours, termine le `lifespan`
de l'app, puis relance le signal, qui tue le processus (`uvicorn/server.py:290-311` et `343-349`).
L'arrêt est donc dans le `lifespan` :

```python
async def stop_metrics_on_shutdown(app: FastAPI) -> AsyncIterator[None]:
    yield
    await run_in_threadpool(app.state.model_metrics.stop)
```
(`src/k_b/ai_api/app.py:82-87`, docstring retirée)

`run_in_threadpool` : le dernier envoi attend le réseau, et un appel bloquant dans une fonction
`async` bloquerait la boucle d'événements. `stop` borne l'envoi à 5 s
(`metric_instruments.py:149-154`). Le fournisseur est créé avec `shutdown_on_exit=False`
(`metrics_export.py:169`) : sinon un `atexit` l'arrêterait une seconde fois, après le retrait des
journaux de `kb`.

### 6. Où OpenTelemetry a le droit d'entrer

`app.py`, le routeur et les commandes ne voient que `ModelMetrics` : `record_calls`,
`record_data_fetch`, `stop`. OpenTelemetry ne s'importe que dans `metrics_export.py` et
`metric_instruments.py`, et `requests` que dans le premier. Un test d'architecture le tient
(`tests/architecture/test_opentelemetry.py`). C'est une décision de Sabine du 24/10 : les règles de
l'export restent en un seul endroit.

La télémétrie native de FastAPI 0.143 est coupée dans les **deux** API, par une valeur partagée
(`src/k_b/core/api_telemetry.py`). Allumée, elle enverrait traces, métriques HTTP et messages
d'erreur aux fournisseurs globaux. Avec `FASTAPI_OTEL_AUTO_CONFIGURE=true`, elle les poserait
elle-même, d'après les variables `OTEL_*`. Une trace de l'API de données porterait alors la requête
brute d'un client vers un destinataire absent du registre. Le risque est né de cette PR : avant
elle, l'exporteur OTLP n'était pas installé et la configuration automatique échouait. Le test
`tests/test_api_telemetry.py` lance chaque app dans un sous-processus avec la variable, et vérifie
qu'aucun fournisseur global n'est posé (constat de la revue de code, vérifié par time-knight).

### 7. Les journaux de l'exporteur, cités comme ceux de K-B

Quand un envoi échoue, le client OTLP journalise le code HTTP et la phrase d'état du serveur. Cette
phrase peut porter un retour chariot ou un caractère de contrôle. Un filtre est posé sur le journal
de l'exporteur lui-même (`EXPORTER_LOGGER`, `metrics_export.py`) :

```python
def quote_argument(argument: object) -> object:
    if isinstance(argument, BaseException):
        return type(argument).__name__
    if isinstance(argument, str):
        return quote_value(argument)
    return argument
```
(`src/k_b/ai_api/connectors/metrics_export.py:188-193`)

Chaque texte passe par `quote_value` (règle 3 de `conventions.md`), chaque exception est réduite à
son type, et la ligne reste : l'échec demeure visible. Le filtre est sur le journal de l'exporteur
et non sur `opentelemetry` : un filtre de journal ne voit pas les lignes que ses enfants lui
remontent.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Variables `KB_OTLP_ENDPOINT` et `KB_OTLP_HEADERS` | Le SDK relit les variables `OTEL_*` et peut journaliser l'en-tête | Noms standard `OTEL_EXPORTER_OTLP_*` : constat de la relecture du plan |
| Refus de toute variable `OTEL_*` | Règle fermée, à jour quelle que soit la version du SDK | Une liste de variables à refuser, toujours en retard |
| `KB_DEPLOYMENT_ENVIRONMENT` sans défaut, exigée avec l'export | Décision de Sabine du 24/10 : une production mal étiquetée ne dirait rien | Défaut `sandbox` (règle 2 de `poc.md`) |
| Ressource par le constructeur | Rien d'autre que le service, son instance et son environnement | `Resource.create`, qui lit l'environnement et des détecteurs |
| Noms GenAI là où la convention en a, `k_b.` sinon | Lecture standard visée par #163 | Tout en `k_b.` ; tout en GenAI, qui n'a rien pour le coût ni les contrôles |
| Arrêt dans le `lifespan` | Seul moment atteint sur SIGTERM | Après `uvicorn.run` : jamais exécuté |
| Fournisseur passé à l'app | Les tests passent un lecteur en mémoire | Fournisseur global `set_meter_provider` : posé une fois par processus |
| Exporteur OTLP en HTTP | La passerelle de Grafana Cloud le reçoit | gRPC : `grpcio`, plus lourd |
| Intervalle de 60 s, constante de `core/config.py` | Défaut du SDK, aucun besoin de le régler | Une variable de plus (YAGNI) |
| `data_fetch` mesuré à chaque demande lue | Décision de Sabine du 24/10 | Seulement quand la ligne JSON le porte |
| Durée des contrôles seulement si la réponse est arrivée (HTTP 200) | Un appel sans réponse n'a passé aucun contrôle ; un 0 tirerait les centiles vers le bas | Un attribut d'état de plus sur l'histogramme |
| DPA de Grafana Labs lu, non signé | Décision de Sabine du 24/10 : aucune donnée personnelle envoyée | Le signer avant le premier envoi |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_without_endpoint_nor_headers_the_export_is_off`, `test_without_settings_no_exporter_is_built` | Sans réglage, aucun exporteur n'est construit : rien ne part |
| `test_a_setting_of_the_export_refused_is_named_without_its_headers` (17 cas) | Chaque réglage refusé est nommé, sans le jeton |
| `test_any_variable_of_opentelemetry_is_refused_by_its_name_only` | Une variable `OTEL_*` arrête le démarrage, nommée sans sa valeur |
| `test_the_exporter_gets_the_settings_and_a_session_blind_to_the_environment` | URL, en-tête, délai, gzip, temporalité cumulative, `trust_env` faux |
| `test_the_resource_names_the_service_and_the_environment_only` | Avec `OTEL_RESOURCE_ATTRIBUTES=host.name=…` et le détecteur `process`, la ressource n'a que ses trois attributs |
| `test_each_call_is_measured_in_opentelemetry_as_on_its_line` | Chaque instrument porte la valeur de la ligne JSON |
| `test_a_measure_carries_closed_attributes_never_a_text` | Clés et valeurs d'attributs dans une liste fermée, sans `request_id` |
| `test_an_empty_window_measures_its_reading_without_a_call` | `data_fetch` mesuré sans appel au modèle |
| `test_the_measures_are_sent_when_the_app_stops` | La fin du `lifespan` appelle `stop` |
| `test_auto_configure_sets_no_global_provider` (les deux API, en sous-processus) | Avec `FASTAPI_OTEL_AUTO_CONFIGURE=true`, aucun fournisseur global n'est posé ; une app FastAPI sans la coupure en pose un (vérifié le 24/10) |
| `test_a_failed_export_is_logged_with_its_reason_quoted` | Un 400 dont la phrase d'état porte un CR et un échappement est journalisé cité ; rouge sans le filtre |
| `test_a_library_of_the_export_is_imported_by_its_modules_only` | OpenTelemetry et `requests` restent dans leurs deux modules |
| Test `e2e` vers `https://otlp.invalid` (le 24/10) | Demande 200, export en échec ; le journal du SDK cite l'hôte et le chemin, jamais l'en-tête |
| `uv run pytest` : 2347 réussis ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` | Contrôles du dépôt verts |
| Nouveaux tests lancés sur `736c46c` (dépendances seules) | Rouges : `ImportError` à la collecte des trois modules de test |

## Ce que tu dois pouvoir défendre

1. **Pourquoi refuser les variables standard d'OpenTelemetry, alors que Grafana les donne
   toutes prêtes ?** Le SDK 1.45.1 relit l'environnement même quand on lui passe l'en-tête, et
   journalise tel quel un en-tête mal formé : le jeton finirait au journal. K-B lit ses propres
   variables, les contrôle, puis passe chaque valeur. Les mêmes valeurs se collent sous un autre
   nom (`metrics_export.py:74-80`).
2. **Que se passe-t-il sans URL ni jeton ?** Le fournisseur n'a aucun lecteur : les instruments
   reçoivent les mesures et les jettent, aucun exporteur n'est construit. La ligne JSON reste
   (`metrics_export.py:158-159`, `test_without_settings_no_exporter_is_built`).
3. **Comment sais-tu qu'aucune donnée personnelle ne part ?** Attributs à valeurs fermées, tenus
   par un test qui compare chaque clé et chaque valeur à une liste. Ressource construite sans
   détecteur, tenue par un test qui pose `host.name` dans l'environnement
   (`metric_instruments.py:112-118`, `build_resource`).
4. **Pourquoi l'arrêt dans le `lifespan` et pas après `uvicorn.run` ?** uvicorn relance le SIGTERM
   après la fin du `lifespan` : le code qui suit `uvicorn.run` ne s'exécute jamais
   (`uvicorn/server.py:343-349`, `app.py:82-87`).
5. **Pourquoi un `service.instance.id` aléatoire, alors qu'on refuse `Resource.create` ?** On
   refuse ce que `Resource.create` lit de l'environnement, pas l'identifiant d'instance. Sans lui,
   deux processus écriraient les mêmes séries cumulées, et Grafana lirait des totaux mêlés. Le prix :
   chaque redémarrage ouvre de nouvelles séries.

## Zones non vérifiées

- **L'essai réel vers Grafana Cloud n'est pas fait à l'écriture de cette note.** Il attend le
  jeton de Sabine (`tests/e2e/test_real_export.py`, lancé par elle), puis la série lue dans Grafana
  Explore par `{job="k-b-ai-api"}`.
- **Le nom des séries dans Grafana** : la règle de traduction (points en soulignés, `_total` sur
  un compteur, suffixe d'unité) vient de la doc de Grafana Cloud. Le sort d'une unité entre
  accolades (`{token}`, `{USD}`) n'y est pas écrit.
- **Un 3xx compte comme un succès** pour le transport du SDK : le test de bout en bout ne le
  distingue pas d'un envoi reçu. La série vue dans Grafana est la preuve finale.
- **La rétention de 14 jours et les 10 000 séries** de l'offre gratuite viennent des pages
  commerciales de Grafana, lues le 24/10, pas d'un contrat.
- **Le texte du DPA** a été lu sur les pages 1 à 14 du PDF ; la fin du Schedule 3 (juridictions
  hors UE) n'a pas été lue.
- **Le filtre des journaux** ne couvre que le journal de l'exporteur OTLP. Une ligne d'un autre
  module du SDK (le lecteur périodique, par exemple) n'est pas citée par `quote_value`.

## Ce qui reste

- **#207** émettra `facts_checked` et `facts_found`, dans `metric_instruments.py` (commentaire
  du 24/10 sur #207).
- **#164** : les tableaux de bord et les alertes, dans Grafana, après la comparaison de **#163**,
  qui ajoute Honeycomb (commentaire du 24/10).
- **#281** : les traces (`trace_id`, `traceparent`). La télémétrie native de FastAPI, coupée ici,
  est une piste pour elle, en dehors des variables `OTEL_*` que K-B refuse.
- **#200** : le délai d'arrêt du conteneur. Un arrêt pendant une demande perd le dernier envoi
  (commentaire du 24/10 sur #200).
- Les conversions `* 1000` déjà sur `main` (`digest_router.py:63`, `llm_client.py:482-483`) ne
  passent pas par `MILLISECONDS_PER_SECOND` : signalées, hors de cette PR.

## Sources

| Source | Lue le | Pour |
|---|---|---|
| [OpenTelemetry Python, doc du SDK](https://opentelemetry-python.readthedocs.io/en/stable/) (Context7) | 2026-10-24 | `OTLPMetricExporter`, `PeriodicExportingMetricReader`, `InMemoryMetricReader`, `Resource.create`, `MeterProvider.shutdown`, `Counter.add`, `Histogram.record` |
| Code des roues PyPI 1.45.1 ([exporteur OTLP HTTP](https://pypi.org/project/opentelemetry-exporter-otlp-proto-http/1.45.1/), SDK) | 2026-10-24 | `_resolve_endpoint`, `_resolve_headers`, `shutdown_on_exit` |
| [PyPI, opentelemetry-sdk](https://pypi.org/pypi/opentelemetry-sdk/json) | 2026-10-24 | Version 1.45.1 du 2026-10-06 |
| [Conventions GenAI, métriques](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-metrics.md), [inférence côté client](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/client-inference.md), [jetons](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-token-metrics.md) | 2026-10-24 | Noms, attributs requis, seaux |
| [Ancienne page des conventions, « moved »](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/) | 2026-10-24 | Le déménagement des conventions |
| [FastAPI, lifespan](https://fastapi.tiangolo.com/advanced/events/) et [tests du lifespan](https://fastapi.tiangolo.com/advanced/testing-events/) (Context7) | 2026-10-24 | `lifespan`, `TestClient` en contexte |
| Skill `fastapi` du dépôt et code de FastAPI 0.143.1 (`applications.py`, `telemetry/`) | 2026-10-24 | Télémétrie native, `FASTAPI_OTEL_AUTO_CONFIGURE` |
| Code d'uvicorn installé, `uvicorn/server.py:290-311`, `335-349` | 2026-10-24 | Ordre de l'arrêt, signal relancé |
| [requests, authentification et `.netrc`](https://requests.readthedocs.io/en/latest/user/authentication) et [`merge_environment_settings`](https://requests.readthedocs.io/en/latest/_modules/requests/sessions) (Context7) | 2026-10-24 | `trust_env` |
| [Grafana Cloud, formats d'URL par région](https://grafana.com/docs/grafana-cloud/security-and-account-management/region-url-formats/) | 2026-10-24 | `prod-eu-west-2` : AWS, Allemagne |
| [Grafana Cloud, OTLP format considerations](https://grafana.com/docs/grafana-cloud/send-data/otlp/otlp-format-considerations/) et [promote resource attributes](https://grafana.com/docs/grafana-cloud/send-data/otlp/promote-resource-attributes/) | 2026-10-24 | Noms Prometheus, `job`, `target_info` |
| [Grafana Cloud Free](https://grafana.com/products/cloud/free-tier/) et [Metrics](https://grafana.com/products/cloud/metrics/) | 2026-10-24 | 14 jours de rétention, 10 000 séries actives par mois |
| [Grafana Labs, Data Processing Agreement](https://grafana.com/legal/data-processing-agreement) et [son PDF, ver. 2026.04.02](https://a-us.storyblok.com/f/1022730/x/ec1d2a9efe/grafana-labs-data-processing-agreement-pre-signed-ver-20260402.pdf) | 2026-10-24 | Prise d'effet à la signature, transferts, clauses types |
