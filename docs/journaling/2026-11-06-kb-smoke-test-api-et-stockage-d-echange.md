# `kb smoke-test` : joindre les deux API et le stockage d'échange depuis un job

- **Date** : 2026-11-06
- **Branche** : `feat/smoke-test`
- **Issue** : #412
- **Fichiers principaux** : `src/k_b/commands/smoke_test_command.py`, `src/k_b/jobs/exchange_storage.py`,
  `src/k_b/jobs/api_health.py`, `src/k_b/commands/run_log.py`, `tests/jobs/storage_fakes.py`

Note courte (parcours allégé décidé par Sabine le 06/11). Elle couvre les commits ed353b4, a8e4ba7, aa39d22 et
5292ef1 de #412 ; les autres fichiers de la liste de la branche viennent de #440 (PostgreSQL), fusionnée sur
`main` avant le rebase de cette branche, et ont leur propre note.

## Le pourquoi

Avant de mettre en ligne les jobs de K-B, il faut prouver qu'un job d'Azure Container Apps joint les deux API
internes et le stockage d'échange (Blob) par son identité managée. `kb smoke-test` est la commande du job
`caj-kb-smoke-test` (#414) : `GET /health` des deux API, puis le jeton de l'identité du job et la liste d'une page
du conteneur `smoke-test`. Le code d'accès au stockage sert ensuite aux commandes des jobs planifiés (#413).

Le risque à tenir : le nom d'un blob est le titre d'un clip (`etl/sources/clipping.py`), une donnée que la règle 5
de `poc.md` interdit dans un journal. La commande n'écrit que des comptes.

## Le comment

### Un paquet `jobs`, sous `commands`

```python
JOBS_ALLOWED_MODULES = {"jobs", "core"}
JOBS_IMPORTERS = {"jobs", "commands"}
```
(`tests/architecture/test_layers.py:325-326`)

`jobs/` n'importe que `core` ; seul `commands` l'importe. Les deux API n'ont aucun accès au stockage d'échange
(plan de mise en ligne du 06/11) : la règle le rend visible dans le code, et le test refuse tout chemin vers `jobs`
depuis `etl`, `data_api` ou `ai_api`.

### Les bibliothèques n'écrivent ni l'URL d'un transfert ni le texte d'une réponse

```python
LIBRARY_LOG_LEVELS = {
    HTTP_CLIENT_LOGGER_NAME: logging.WARNING,
    AZURE_SDK_LOGGER_NAME: logging.ERROR,
    URLLIB3_LOGGER_NAME: logging.ERROR,
}
```
(`src/k_b/commands/run_log.py:43-47`)

`logging_to` met le journal racine à INFO. Or, à INFO, `HttpLoggingPolicy` d'azure-core écrit
`Request URL: 'https://<compte>.blob.core.windows.net/<conteneur>/<blob>'` : observé avant le plan, puis par le
test rouge `test_the_azure_sdk_writes_no_url_of_a_blob_in_the_log`. Une liste ne cite que le conteneur ; un
transfert cite le blob. Le premier choix, `azure` à WARNING comme `httpx2`, ne suffisait pas (revue de code) : à
WARNING, `azure.identity` écrit deux fois l'échec d'un jeton avec le texte de la réponse, non échappé (un `\n` y
fabrique une fausse ligne de `kb`), et `urllib3` peut écrire une URL entière. Les deux sont tenus à ERROR
(`run_log.py:89`), où ils n'écrivent que des textes fixes, et remis à leur niveau à la sortie ; `kb` écrit lui-même
chaque échec, une fois.

### Une erreur nommée, jamais son message

```python
STATE_BY_STATUS: dict[int, ExchangeStorageState] = {
    401: "exchange_storage_unauthorized",
    403: "exchange_storage_forbidden",
    404: "exchange_storage_not_found",
}
```
(`src/k_b/jobs/exchange_storage.py:57-61`)

Le message d'une `HttpResponseError` recopie le corps de la réponse, qui peut citer le chemin du blob. K-B n'en
garde que l'état, le statut et le code `x-ms-error-code` s'il est un mot de lettres (`ERROR_CODE`, l. 44), et lève
`from None` (l. 179) : une trace ne montrerait pas l'erreur du SDK. L'état se lit au **statut** et non à la classe,
parce que le SDK lève `ClientAuthenticationError` pour une 403 dont le code est `AuthenticationFailed`
(`azure/storage/blob/_shared/response_handlers.py:139-140`).

### Le jeton à part

```python
    try:
        credential.get_token(STORAGE_SCOPE)
    # ValueError and AttributeError: an answer that is not a JSON object (a 500 in HTML, a list),
    # which azure-identity does not turn into an AzureError.
    except (AzureError, ValueError, AttributeError):
        raise ExchangeStorageError("exchange_storage_no_token") from None
```
(`src/k_b/jobs/exchange_storage.py:156-161`)

Le jeton est demandé avant la liste, et tout échec de l'identité est `exchange_storage_no_token`. La classe d'une
erreur d'azure-identity ne dit pas un refus d'une panne : une 500 en JSON lève `CredentialUnavailableError`, comme un
client id inconnu ; une 500 en HTML lève `JSONDecodeError`, une liste `AttributeError`, qui ne sont pas des
`AzureError` et sortaient sinon de `kb` avec leur trace ; et aucune ne porte le statut du point d'accès (400, 401,
403, 404 essayés). Le premier tri de la revue donnait deux états (`…_unauthorized`, `…_identity_unavailable`) ; la
seconde revue a montré qu'ils suivaient la classe, pas ce qu'avait fait le point d'accès. Le diagnostic utile en
ligne reste « l'identité ou le rôle » : `no_token` contre `exchange_storage_forbidden`. La demande ne coûte rien de plus : le crédit garde le jeton pour la suite (une seule demande dans
`test_the_token_is_asked_for_the_identity_of_its_client_id_and_sent_to_the_storage`).

### Le transport, ses délais, ses nouvelles tentatives

`build_transport` (`exchange_storage.py:114`) construit `RequestsTransport(use_env_settings=False, …)` : ni proxy ni
certificat de l'environnement, comme `open_http_client` ; le client du conteneur a `permit_redirects=False`
(l. 145). Donner un transport fait perdre au SDK de stockage ses délais (20 s pour une connexion, 60 s pour une
lecture), qu'il ne pose que s'il construit lui-même le transport (`base_client.py:314-315`) : azure-core donnerait
300 s (relevé par la revue). K-B les repose (`EXCHANGE_STORAGE_*_TIMEOUT_SECONDS`, `core/config.py`). Les nouvelles
tentatives restent celles du SDK : 3, après environ 18, 24 et 42 s (mesuré par un faux transport), soit environ
7 min quand chaque essai attend ses délais. Ce n'est pas une borne : le délai de lecture borne chaque lecture, pas
une réponse, et les nouvelles tentatives d'azure-identity n'y sont pas comptées.

### `/health`, borné et fermé

```python
    deadline = clock() + HEALTH_REQUEST_DEADLINE_SECONDS
    try:
        with http_client.stream("GET", HEALTH_PATH) as response:
            if response.status_code != HEALTHY_STATUS:
                raise HealthCheckError("health_failed", response.status_code)
```
(`src/k_b/jobs/api_health.py:77-81`)

Sans clé (la route est servie sans), sans nouvel essai. Le corps est lu par `read_bounded_body` (1 Kio au plus,
échéance de 65 s : une connexion puis une lecture), puis validé par `HealthAnswer` (`extra="forbid"`, `strict`,
l. 51) : seul `{"status":"ok"}` passe.

## Choix faits et options écartées

| Choix | Retenu parce que | Écarté |
|---|---|---|
| Paquet `jobs` sous `commands` | une couche visible, refusée aux API | `core/` (ouvert aux API) ; `commands/` (présentation et E/S mêlées) ; `post/` (post-traitement) |
| `azure` et `urllib3` à ERROR | seuls des textes fixes à ce niveau ; `kb` écrit chaque échec | WARNING (laissait le texte d'une réponse) ; `azure.identity` seul ; un filtre de masquage |
| État, statut et code de l'erreur | le message peut citer le blob | `quote_value(str(error))`, qui garde le début du nom |
| La liste seule | `kb smoke-test` n'appelle qu'elle | envoi et téléchargement maintenant (sans appelant, `code.md`) : #413 |
| `AZURE_CLIENT_ID` obligatoire | sans lui, l'identité système, que les jobs n'ont pas | une valeur par défaut |
| Conteneur en constante | rien ne le change par déploiement | une variable |
| Ligne de fin à INFO | chaque échec a déjà sa ligne ERROR (« journalisé une fois ») | ERROR en cas d'échec |

Les constats de la revue de code sont tranchés par time-knight (délégation de Sabine du 15/10) ; le compte rendu est
dans la PR.

## Preuve

| Test ou sortie | Ce que ça démontre |
|---|---|
| `test_the_name_of_a_blob_listed_is_written_nowhere` | une liste au nom repérable : rien sur stdout, stderr, `kb.log` |
| `test_a_403_of_the_storage_fails_the_smoke_test_without_the_name_its_body_gives` | une 403 dont le corps cite le blob : code 1, état et code écrits, nom absent |
| `test_the_azure_sdk_writes_no_url_of_a_blob_in_the_log` | un transfert par le SDK : l'URL du blob n'entre pas au journal (rouge avant le garde) |
| `test_a_token_refused_is_logged_once_by_kb_without_what_the_endpoint_says` | une seule ligne, celle de `kb` ; la fausse ligne du point d'identité n'entre ni dans `kb.log` ni sur stderr |
| `test_an_identity_endpoint_that_answers_no_token_gives_no_token` | 500 en HTML, `[]`, une chaîne, 500 en JSON : `exchange_storage_no_token`, sans trace |
| `test_an_identity_endpoint_out_of_reach_gives_no_token`, `test_a_token_refused_by_the_identity_endpoint_is_no_token` | injoignable ou refus : le même état |
| `test_the_token_is_asked_for_the_identity_of_its_client_id_and_sent_to_the_storage` | `client_id` dans la demande de jeton, `X-IDENTITY-HEADER`, `Bearer` vers le stockage, une seule demande |
| `test_the_transport_waits_as_the_sdk_of_the_storage_does_without_one` | 20 s et 60 s (rouge : 300) |
| `test_an_answer_other_than_its_health_fails_with_a_named_state` | 503, 307, HTML, `down`, champ en trop, trop grand : refusés |
| `test_a_sigterm_during_a_check_stops_kb_smoke_test` | 143, aucun appel au stockage, gestionnaire rendu |
| `test_only_commands_import_jobs`, `test_jobs_imports_only_core` | la règle de couche |
| `uv run kb smoke-test --help` → code 0 ; sans `KB_EXCHANGE_BLOB_URL` → code 2 | le critère `--help`, hors image |

**Simulation du SDK.** `FakeTransport` (`tests/jobs/storage_fakes.py:55`) est un vrai `RequestsTransport` sur une
session `requests` dont l'adaptateur répond par une fonction du test : tout le pipeline du SDK tourne (jeton,
nouvelles tentatives, journal), sans réseau ; `sleep` ne dort pas. Le point d'identité est simulé par
`IDENTITY_ENDPOINT` et `IDENTITY_HEADER`, que lit azure-identity. Le nom repérable a des espaces : dans une URL il
s'écrit `%20`, donc `names_the_spotted_blob` (l. 19-21) le cherche brut **et** encodé ; sinon le test du transfert
passerait sans le garde.

## Ce que tu dois pouvoir défendre

- **Pourquoi ne pas citer l'erreur tronquée, comme une valeur observée ?** Le début du nom d'un clip resterait ; un
  état, un statut et un code suffisent au diagnostic (`exchange_storage.py:182-189`).
- **Une liste renvoie tous les noms : où vont-ils ?** Nulle part : comptés à la volée sur une page de 100 au plus
  (`count_listed_blobs`, l. 163-169), jamais gardés.
- **Que se passe-t-il si l'identité n'a pas le rôle ?** Le stockage répond 403 `AuthorizationPermissionMismatch` :
  `exchange_storage_forbidden, HTTP 403, AuthorizationPermissionMismatch`, code 1.
- **Pourquoi `AZURE_CLIENT_ID` alors que le SDK sait trouver une identité ?** Sans `client_id`,
  `ManagedIdentityCredential` demande l'identité système ; un job de K-B n'a qu'une identité attribuée par
  l'utilisateur.
- **Le jeton peut-il partir ailleurs ?** URL refusée hors `https` (`find_url_refusal`), aucune redirection suivie,
  pas de proxy de l'environnement.

## Zones non vérifiées

- Aucun essai contre Azure : le format des réponses (liste, erreurs, point d'identité) vient de la documentation
  REST et du comportement du SDK installé, pas d'une réponse réelle. L'essai réel est #414.
- Les 60 s de lecture de `/health` sont une hypothèse (réveil d'une API à 0 réplique).
- Les avertissements d'`urllib3` sont perdus pour toutes les commandes, les autres sources comprises : aucun n'a
  été relevé comme utile, mais la liste n'a pas été faite.
- Rattraper `ValueError` et `AttributeError` autour de `get_token` range aussi sous `exchange_storage_no_token`,
  sans trace, un bogue de K-B ou du SDK qui lèverait l'une d'elles (seconde revue, constat écarté).
- Les bibliothèques autres qu'`azure` et `urllib3` (BigQuery, OpenTelemetry) peuvent écrire à WARNING le texte d'une
  réponse, non échappé : un défaut déjà sur `main`, porté par #441.
- Le critère `docker run --rm -e KB_DATA_DIR=/var/lib/knowledge_base <image> kb smoke-test --help` attend l'image
  de #200.

## Ce qui reste

- L'envoi et le téléchargement de blobs, avec leurs commandes (#413).
- Le job `caj-kb-smoke-test`, le conteneur `smoke-test` et le rôle Storage Blob Data Reader de son identité (#414).
