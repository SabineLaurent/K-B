# Suivre une demande de l'API IA jusqu'à l'API de données par sa trace

- **Date** : 2026-11-22 (code du 2026-11-21)
- **Branche** : `feat/trace-context-between-apis`
- **Issue** : #281
- **Fichiers principaux** : `src/k_b/core/trace_context.py` (nouveau), `src/k_b/commands/run_log.py`,
  `src/k_b/ai_api/tracing.py`, `src/k_b/ai_api/connectors/trace_export.py`,
  `src/k_b/ai_api/connectors/data_api_client.py`, `src/k_b/ai_api/app.py`, `src/k_b/data_api/app.py` ; tests :
  `tests/ai_api/test_digest_router.py`, `tests/data_api/test_request_log.py`, `tests/ai_api/test_trace_export.py`,
  `tests/ai_api/test_tracing.py`, `tests/commands/test_run_log.py` ; docs : `docs/specs-api.md` (« Journal »),
  `docs/fiches-veille.md`, `documentation/monitoring_pour_docu.md`
- **Série** : [tracer les étapes des fiches](2026-10-27-tracer-les-etapes-des-fiches.md) (#345, les spans de
  `POST /digests`).

## Le pourquoi

Une demande de `kb digest` à l'API IA déclenche une quinzaine de requêtes de l'API IA à l'API de données (une liste
par sorte d'item, puis un détail par item, `data_api_client.py:248`, `:291`). Chaque API tire son `request_id` : jusqu'ici, rien ne reliait la ligne de `POST /digests`
aux lignes des `GET /items` qu'elle a causées, sinon l'heure et le nom du client. #281 donne à la demande un seul
identifiant, l'identifiant de trace de la recommandation W3C Trace Context, que l'API IA envoie à l'API de données
dans l'en-tête `traceparent`, et que chaque ligne de journal des deux API porte (`trace_id=`). Les spans de l'API IA
(#345) portent le même : une ligne de journal mène à sa trace dans Tempo.

## Le comment

### Lire un `traceparent`, ou le refuser

`src/k_b/core/trace_context.py:16` et `:57-67` :

```python
TRACEPARENT_PATTERN = re.compile(r"00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}")
...
    if len(values) != 1:
        return None
    match = TRACEPARENT_PATTERN.fullmatch(values[0])
```

L'en-tête a quatre champs : version, identifiant de trace (16 octets en hexadécimal), identifiant du parent (8
octets), drapeaux. `fullmatch` refuse tout ce qui dépasse ; les deux identifiants à zéro, invalides selon la
recommandation, sont refusés ensuite (`:65`). Une valeur refusée rend `None` et n'est jamais recopiée : un en-tête est
une entrée non fiable, et le citer permettrait d'injecter une fausse ligne de journal (règle 3 de `conventions.md`).
Le module n'importe pas OpenTelemetry : l'API de données s'en sert aussi, et elle ne l'importe pas
(`tests/architecture/test_opentelemetry.py`).

### Une variable de contexte pour la demande en cours

`src/k_b/core/trace_context.py:24` et `:38-44` :

```python
CURRENT_TRACE_ID: ContextVar[str | None] = ContextVar("current_trace_id", default=None)
...
async def start_trace(request, call_next):
    with following_trace(draw_trace_id()):
        return await call_next(request)
```

Une `ContextVar` est une variable globale propre à chaque demande : deux demandes servies en même temps ont chacune
la sienne, et Starlette la copie dans le thread où tourne une route synchrone. L'API IA tire un identifiant neuf pour
chaque demande (`start_trace`) ; l'API de données reprend celui du `traceparent` reçu, sinon en tire un
(`follow_trace`, `:27-35`). Chaque middleware est ajouté en dernier, donc le plus extérieur
(`src/k_b/ai_api/app.py:101`, `src/k_b/data_api/app.py:80`) : la ligne de la requête elle-même, écrite par
`log_request`, est déjà dans la trace.

### Écrire le `trace_id` dans chaque ligne

`src/k_b/commands/run_log.py:36` et `:119-123` :

```python
LOG_LINE_FORMAT = "%(asctime)s %(levelname)s %(name)s:%(trace_field)s %(message)s"
...
        trace_id = read_current_trace_id()
        record.trace_field = "" if trace_id is None else f" trace_id={trace_id}"
        return super().format(record)
```

Le champ est posé par le formateur, au moment où la ligne est écrite, dans le thread qui l'écrit : toute ligne
d'une demande le porte, celle d'une erreur comprise, sans que les modules qui journalisent changent. Hors d'une
demande (`kb import`, par exemple), le champ est vide et la ligne garde son format d'avant.

### Le même identifiant dans les spans de l'API IA

`src/k_b/ai_api/connectors/trace_export.py:57-65` :

```python
class RequestTraceIdGenerator(RandomIdGenerator):
    def generate_trace_id(self) -> int:
        trace_id = read_current_trace_id()
        if trace_id is None:
            return super().generate_trace_id()
        return int(trace_id, 16)
```

Le SDK d'OpenTelemetry (1.45.2) n'appelle `generate_trace_id` que pour un span racine, sans parent valide
(`opentelemetry/sdk/trace/__init__.py`, `Tracer.start_span`) : le span `POST /digests` prend l'identifiant de la demande,
et ses enfants en héritent. Hors d'une demande, le tirage du SDK reste.

### L'envoyer à l'API de données

`src/k_b/ai_api/tracing.py:218-231` et `src/k_b/ai_api/connectors/data_api_client.py:345-353` :

```python
    span_context = trace.get_current_span().get_span_context()
    is_of_the_trace = (
        span_context.is_valid and format(span_context.trace_id, "032x") == trace_id
    )
```

Le parent envoyé est le span en cours, celui de `read_watch`, quand il appartient à la trace de la demande ; sinon, sans span
qui enregistre (traces non exportées) ou avec le span d'une autre trace, un identifiant tiré. Chaque requête de `send` porte l'en-tête : la liste et
chaque détail.

## Choix faits et options écartées

- **Sans dépendance nouvelle.** Retenu : quelques lignes écrites dans `core/`. Écartés : le propagateur
  d'OpenTelemetry, que l'API de données n'importe pas ; l'instrumentation de `httpx`, une dépendance de plus.
- **L'API IA ignore un `traceparent` reçu** (revue du 2026-11-21). Retenu : elle commence la trace de chaque demande.
  Écarté : le suivre, comme la première version de la branche ; un appelant choisirait alors l'identifiant des spans
  de l'API IA et pourrait mêler ses demandes à la trace d'un autre.
- **Version 00 seulement, en minuscules.** La recommandation (§ 3.2.4, REC du 2021-11-23, lue le 2026-11-22) dit
  qu'une version supérieure *devrait* être lue sur ses champs connus. K-B la refuse et commence une trace neuve : son
  seul émetteur, l'API IA, écrit la version 00. Deux `traceparent` sont refusés eux aussi ; la recommandation ne traite
  pas ce cas.
- **Un seul formateur pour toutes les lignes.** Retenu : `TracedFormatter` dans `logging_to`, qui sert `kb` et les
  trois serveurs. Écarté : un filtre posé sur les seuls serveurs, un second chemin pour le même format.
- **Le parent : le span en cours s'il est de la trace** (revue du 2026-11-21). Écarté : le span en cours sans
  condition, qui pourrait appartenir à une autre trace.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_request_and_its_reading_share_the_trace_id_of_the_root_span` (`tests/ai_api/test_digest_router.py:1893`) | la ligne de `POST /digests`, celles des `GET /items` et le span racine ont un seul identifiant |
| la même, avec l'envoi de l'en-tête retiré à la main (`data_api_client.py:345`), le 2026-11-22 | elle échoue : l'en-tête passe bien par le `TestClient` en mémoire |
| `test_a_traceparent_received_by_the_ai_api_is_ignored` (`:1913`) | un `traceparent` valide reçu par l'API IA n'est ni sa trace, ni le parent de son span racine, ni dans son journal (lignes de l'API de données comprises), ni dans ses en-têtes |
| `test_a_span_of_another_trace_is_never_the_parent_sent` (`tests/ai_api/test_tracing.py:311`) | un span en cours d'une autre trace n'est jamais le parent envoyé ; avec la condition retirée à la main (`tracing.py:226`), le 2026-11-22, le test échoue |
| `test_the_traceparent_sent_to_the_data_api_holds_identifiers_only` (`tests/ai_api/test_digest_router.py:1961`) | l'en-tête envoyé : la trace de la demande et le span de `read_watch` ; l'échec de la lecture journalisé dans la même trace |
| `test_a_refused_traceparent_starts_a_new_trace_and_is_never_quoted`, six valeurs (`tests/data_api/test_request_log.py:185`) | majuscules, version 01, identifiants à zéro, champ de trop, texte : trace neuve, valeur jamais citée |
| `test_two_traceparents_start_a_new_trace` (`:201`) | deux en-têtes sont refusés |
| `test_a_line_out_of_a_request_has_no_trace_id` (`tests/commands/test_run_log.py:229`) | une ligne de `kb` hors demande garde son format |
| capture du 2026-11-22 à 00:46 UTC, au commit `e0d87df2`, par `tests/commands/test_live_apis.py` (relevé non versionné) | les deux API servies par uvicorn en HTTP sur 127.0.0.1 : 16 lignes (15 de l'API de données, 1 de l'API IA), un seul `trace_id` |
| `uv run pytest --cov` | 5 681 tests verts, couverture 98,55 % |

## Ce que tu dois pouvoir défendre

- **Pourquoi l'API IA ignore-t-elle un `traceparent` que la recommandation lui permet de suivre ?** Elle est
  exposée à ses clients : suivre leur en-tête leur ferait choisir l'identifiant de ses spans. L'API de données, elle,
  n'est appelée que par l'API IA et les autres clients de K-B (`src/k_b/core/trace_context.py:27-44`).
- **Une donnée personnelle peut-elle passer par la trace ?** Non : l'en-tête envoyé n'est fait que de deux
  identifiants tirés au hasard (`secrets.token_hex`, `:75-82`), et une valeur reçue refusée n'est citée nulle part
  (tests ci-dessus).
- **Deux demandes en même temps mêlent-elles leurs identifiants ?** Non : la valeur d'une `ContextVar` posée pendant
  une demande ne vaut que dans le contexte de cette demande (`:24`, `:47-54`), et elle est remise à son état d'avant
  à la fin du bloc. Deux demandes l'une après l'autre ont deux identifiants
  (`tests/data_api/test_request_log.py:218`).
- **Pourquoi ne pas réutiliser `request_id` ?** Il identifie une requête dans une API ; une demande de l'API IA en
  fait quinze à l'API de données. Les deux restent : `request_id` pour une requête, `trace_id` pour la demande.

## Zones non vérifiées

- La copie de la `ContextVar` dans le thread d'une route synchrone (`post_digests`, `digest_router.py:71`) est un
  comportement de Starlette et d'anyio : il est prouvé par la ligne d'erreur de `read_watch`, journalisée avec le
  `trace_id` (test de `test_digest_router.py:1961`), pas relu dans leur code.
- `draw_trace_id` ne refait pas un tirage nul, à la différence du SDK : une chance sur 2^128, écrite dans sa
  docstring.
- Deux demandes servies en même temps n'ont pas de test : l'isolement repose sur la `ContextVar`.
- La capture tourne dans un seul processus, comme le banc de `test_live_apis.py` ; deux conteneurs en ligne n'ont pas
  été observés.

## Ce qui reste

Rien, dans le périmètre de #281.
