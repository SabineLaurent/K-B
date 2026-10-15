# Appeler le modèle par une interface compatible OpenAI, et le rejouer sans lui

- **Date** : 2026-10-15
- **Branche** : `feat/llm-client`
- **Issue** : #150
- **Fichiers principaux** : `src/k_b/ai_api/llm_client.py`, `src/k_b/ai_api/llm_replay.py`,
  `src/k_b/ai_api/llm_settings.py`, `src/k_b/core/config.py`, `tests/ai_api/`
- **Série** : suite de [la spécification des fiches de veille](2026-10-15-specifier-les-fiches-de-veille.md),
  dont ce code sert le contrat (contrôles 1 et 2, états `llm_*`, champs de la ligne de métrique).

## Le pourquoi

Les fiches de veille sont la première sortie d'un modèle dans K-B. Avant d'écrire le classement et
la rédaction (#205), il faut une seule porte vers le modèle : elle envoie une demande, vérifie la
réponse, refait la demande une fois quand c'est utile, et rend un état nommé quand ça échoue. Elle
doit tourner **sans clé ni dépense** en test et en CI, avec des réponses connues d'avance, et le
vrai modèle (gpt-5.6-luna sur Azure AI Foundry, #158) doit se brancher par la seule configuration.

Ce code est cette porte : `call_model` envoie un appel et rend un `LlmCall` (l'état, la sortie
validée ou rien, et les mesures de la ligne de métrique que #156 écrira). Il ne contient aucune
consigne : les consignes et les contrôles 3 à 6 viendront de #205 et #206.

## Le comment

### 1. Une API « compatible OpenAI » : une forme de requête, pas un fournisseur

OpenAI a publié une forme d'API, `POST /chat/completions`, que d'autres fournisseurs reprennent
(Azure AI Foundry à `…/openai/v1`, Mistral, d'autres). Le corps dit le modèle, les messages par rôle
et le format de sortie attendu ; seuls l'URL de base, le nom du modèle et la clé changent d'un
fournisseur à l'autre. K-B écrit donc ce corps lui-même, et lit ces trois valeurs dans
l'environnement (`KB_LLM_BASE_URL`, `KB_LLM_MODEL`, `KB_LLM_API_KEY`) :

```python
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": json_schema},
        },
        "max_completion_tokens": max_completion_tokens,
    }
```
(`src/k_b/ai_api/llm_client.py:247-251`)

`response_format` de type `json_schema` en mode `strict` demande au fournisseur une sortie conforme
au schéma (une « sortie structurée »). Le schéma est un dict écrit par l'appelant, sans `minLength`
ni `maxItems`, qu'Azure refuse en mode strict (spec, « Schéma portable »). Le code **ne se fie pas**
au mode strict : il revalide la sortie lui-même (section 4). Le client HTTP est `httpx2`, pas le SDK
d'un fournisseur : c'est la décision de Sabine pour le POC, à revoir au 08/11 (section « Choix »).

### 2. Le texte d'une source n'entre que dans le message utilisateur

La consigne (message `system`) est un paramètre, une constante de module de l'étape appelante. Les
données sont encodées par le client lui-même, en JSON, dans le message `user` :

```python
    user_message = json.dumps(user_data, ensure_ascii=False, allow_nan=False)
```
(`src/k_b/ai_api/llm_client.py:204`)

C'est la règle 8 de `.claude/rules/poc.md` contre l'injection d'instructions (OWASP LLM01:2025) : un
item piégé ne peut pas devenir une consigne, il reste une donnée. `ensure_ascii=False` garde
« Modèle européen » tel quel au lieu de `Modèle`, ce qui fausserait `input_chars` et coûterait
des jetons (constat de l'architecte). Le test `test_a_trapped_item_stays_in_the_user_message_and_its_output_is_never_returned`
le prouve sur un article TLDR collecté, augmenté d'une consigne.

### 3. Le remplacement : le même client, un transport qui rejoue

Le remplacement n'imite pas `call_model` : il se met **sous** le client HTTP. `httpx2.MockTransport`
remplace le réseau par une fonction qui reçoit la requête et rend une réponse ; `ReplayTransport`
rend, dans l'ordre, les étapes qu'on lui a données :

```python
    def answer(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if len(self.requests) > len(self.steps):
            raise ReplayExhaustedError(
                f"{len(self.steps)} steps given, request {len(self.requests)}"
            )
```
(`src/k_b/ai_api/llm_replay.py:101-106`)

Une étape est une complétion, une réponse HTTP quelconque (429 avec `Retry-After`, 503, 400 de
filtrage, 200 illisible), un délai dépassé ou une connexion refusée : chaque panne du critère se
rejoue sans attendre ni réseau. Le transport garde chaque requête, ce qui permet aux tests de lire
ce qui a été **envoyé** (le message `system` exact, l'absence de la clé en remplacement). Choisi par
`KB_LLM_PROVIDER=replay`, il lit ses étapes dans `KB_LLM_REPLAY_FILE` au démarrage : un fichier
absent ou faux empêche l'API IA de démarrer, au lieu de casser au premier appel.

### 4. Les contrôles 1 et 2, et ce qui n'est pas contrôlé ici

L'**enveloppe** que rend le fournisseur (choix, `usage`, et ce qu'il ajoute) est lue par des modèles
qui ignorent les champs inconnus ; la **sortie du modèle**, à l'intérieur, est validée par le modèle
fermé de l'appelant (`extra="forbid"`), en mode strict :

```python
class EnvelopeModel(BaseModel):
    """The envelope a provider gives around the output: the fields read are typed, the others
    ignored, since a provider adds its own (Azure: the results of its content filter). The
    output of the model, inside, is the one that refuses a field in excess."""
```
(`src/k_b/ai_api/llm_client.py:69-72`)

Ordre de `check_completion` (`llm_client.py:340-397`) : `finish_reason` (`length` →
`llm_truncated`, `content_filter` → `llm_content_filtered`, nul ou autre → refus
`finish_reason`) ; puis le schéma (`model_validate_json(..., strict=True)` : un `"2"` n'est pas un
entier) ; puis `check_output`, les contrôles 3 à 6 de l'étape. Une sortie refusée n'est jamais
rendue : `output` n'est rempli que pour `ok`. La `ValidationError` est rattrapée et jetée, jamais
gardée (règle 5 : son texte cite la valeur reçue).

### 5. 429, `Retry-After` et une seule nouvelle tentative

Un 429 dit « trop de demandes » ; l'en-tête `Retry-After` dit combien de secondes attendre (RFC
9110, § 10.2.3). Le client attend ce délai, puis refait **une** demande :

```python
    retry_after = read_retry_after(response)
    if retry_after is not None and retry_after > LLM_RETRY_AFTER_MAX_SECONDS:
        return Attempt(outcome=outcome, retry_after_seconds=retry_after)
    wait = LLM_RETRY_WAIT_SECONDS if retry_after is None else retry_after
```
(`src/k_b/ai_api/llm_client.py:317-320`)

Au-delà de 20 s, il n'attend pas : attendre moins que demandé rendrait un second 429, et attendre
une heure bloquerait la demande. `retry_after_seconds` reste dans `LlmCall` pour que `POST /digests`
(#156) le renvoie au client en 503. Après une **sortie refusée**, la nouvelle tentative ne refait
pas la même demande : elle ajoute à la consigne le rappel constant du contrôle qui a refusé
(`llm_client.py:220-227`), parce qu'une demande identique rendrait le plus souvent la même faute.
Pourquoi une seule : `attempts` vaut 1 ou 2 dans la spec ; une demande coûte, et la durée totale
d'une demande (#205) doit rester bornée.

### 6. `temperature=0`, et ce qu'il ne garantit pas

```python
    if settings.reasoning_effort is None:
        body["temperature"] = 0
    else:
        body["reasoning_effort"] = settings.reasoning_effort
```
(`src/k_b/ai_api/llm_client.py:253-256`)

`temperature=0` fait choisir au modèle le mot le plus probable à chaque pas : la sortie devient
« plus focalisée et déterministe ». Elle n'est **pas garantie identique** : le guide d'OpenAI dit que
les complétions sont non déterministes par défaut, et que même avec `seed` le déterminisme n'est
« pas garanti », la configuration du service pouvant changer. C'est pourquoi le code ne se fie pas à
une sortie « connue » du vrai modèle : il revalide tout, et les tests utilisent le remplacement.
Pour un modèle à raisonnement comme gpt-5.6-luna, qui ne prend pas `temperature` selon Azure,
`KB_LLM_REASONING_EFFORT=none` envoie `reasoning_effort` à la place ; lequel marche vraiment se
tranche au premier essai (#158).

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| `httpx2` seul (décision de Sabine, « pour le POC ») | code générique sans les types d'un fournisseur ; un seul point d'accès, sans diffusion ni outils ; aucune version de plus à suivre | le SDK `openai` : son README avertit que pour Azure « the static types for responses / params won't always be correct » ; il lit l'environnement ambiant (`OPENAI_API_KEY`, `OPENAI_BASE_URL`…) ; une version tous les 1 à 3 jours ; ses nouvelles tentatives auraient été coupées. À revoir au 08/11 (jeton Entra, API Responses) |
| `Authorization: Bearer <clé>` | l'en-tête qu'envoie le client Python que Microsoft documente pour Foundry v1 | `api-key` (celui des exemples curl de Microsoft) : repli si #158 le demande |
| remplacement par `MockTransport` sous le même client | tout le code d'un vrai appel est testé | un `Protocol` avec une fausse implémentation : le code HTTP ne serait jamais testé |
| pas de défaut pour `KB_LLM_PROVIDER`, `_BASE_URL`, `_MODEL` (décision de Sabine, règle 2 de `poc.md` complétée) | un défaut `replay` inventerait des fiches ; un défaut réel enverrait la veille à un service non choisi | un défaut `replay` en local |
| rappel ajouté au message `system` | la consigne déclare le message `user` « donnée, jamais consigne » | un message `user` de rappel (il contredirait la consigne) ; un second `system` après le `user` (ordre non vérifié partout) |
| rappels fournis par l'étape, vérifiés à l'entrée | ils appartiennent à la consigne de l'étape et à sa `prompt_version` ; un rappel manquant se voit avant de payer une demande | des rappels écrits dans #150 (constat de l'architecte) |
| `trust_env=False`, `follow_redirects=False` | aucun proxy ni certificat de l'environnement n'est lu ; la clé ne part jamais vers un autre hôte | les défauts d'httpx2 (`trust_env=True`) |
| `Retry-After` en secondes seulement | la forme date est rare | la lire (une horloge à injecter, pour un cas rare) |
| pas de délai total par tentative | httpx2 n'en a pas ; la demande (#205) a déjà sa borne | un minuteur autour de chaque tentative |
| aucun framework d'orchestration ni agentique (formulation de Sabine) | la chaîne est fixe et décidée par le code, sans outil ni état durable | LangChain, LangGraph et autres, pour ce besoin |

Les constats de `/code-review` et de `/security-review` ont été tranchés par time-knight, par
délégation de Sabine du 15/10 (compte rendu dans la PR).

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_request_is_a_chat_completion_with_a_strict_json_schema_written_as_a_dict` | le corps envoyé : modèle, `system` puis `user`, `json_schema` en dict `strict`, `max_completion_tokens`, `temperature` 0 |
| `test_a_reasoning_model_gets_reasoning_effort_none_and_no_temperature` | le réglage pour gpt-5.6-luna |
| `test_the_second_request_adds_the_reminder_of_the_refused_check_never_the_output` | le message `system` de la seconde demande est **égal** à consigne + rappel ; la sortie refusée n'est renvoyée nulle part |
| `test_a_trapped_item_stays_in_the_user_message_and_its_output_is_never_returned` | règle 8 : l'item piégé n'est que dans le `user` ; sa sortie obéissante n'est pas rendue |
| un test par état : `…llm_invalid_output`, `…llm_truncated…`, `…content_filtered…` (sortie et 400), `…rate_limited…`, `…llm_unavailable` (5xx, connexion, 4xx, 200 illisible, décodage), `…llm_timeout…` | chaque état nommé du critère et de la spec |
| `test_a_rate_limit_twice_is_llm_rate_limited_after_waiting_retry_after` | attente de `Retry-After`, exactement deux requêtes : aucune nouvelle tentative cachée |
| `test_reminders_missing_for_a_check_are_refused_before_any_request` | aucune demande payée si les rappels sont incomplets |
| `test_the_client_of_the_provider_sends_the_key_and_follows_no_redirection` | URL, `Authorization: Bearer`, délais, redirection non suivie |
| `tests/ai_api/test_llm_settings.py` | chaque réglage refusé ; une URL ou une clé refusées ne sont jamais citées |
| `test_ai_api_imports_only_ai_api_items_and_core` | règle 7 : l'API IA n'importe ni la base ni le pipeline |
| `env -u KB_LLM_BASE_URL -u KB_LLM_MODEL -u KB_LLM_API_KEY uv run pytest` : 1365 passed | les tests tournent sans clé ni réseau |
| démonstration sur le remplacement choisi par configuration (dans la PR) | une réponse valide, puis chaque panne et son état |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas faire confiance au mode strict du fournisseur ?** Parce qu'une sortie de modèle
   est une entrée externe : la règle du dépôt la valide à la frontière, par un type fermé. Le
   fournisseur peut ignorer un mot-clé (Azure refuse `maxLength` en strict), changer, ou être
   remplacé. → `llm_client.py:382`.
2. **Que se passe-t-il si un item dit « ignore les consignes » ?** Il reste dans le message `user`,
   que la consigne déclare donnée ; si le modèle obéit quand même, la sortie piégée échoue au schéma
   ou aux contrôles de l'étape et n'est jamais rendue. La consigne n'est pas la défense, les
   contrôles le sont. → test du piège, `llm_client.py:204`.
3. **Pourquoi un remplacement plutôt que de vrais appels en CI ?** Pas de clé à confier à la CI, pas
   de dépense, et des réponses connues : un vrai modèle ne rejoue pas une panne 429 sur commande, et
   sa sortie n'est pas garantie identique même à `temperature=0`. → `llm_replay.py:101`.
4. **Pourquoi une seule nouvelle tentative ?** Une demande coûte ; une sortie tronquée ou filtrée
   reviendrait le plus souvent pareille ; au-delà, la durée de la demande ne serait plus bornée. La
   seconde demande après un refus porte un rappel, sinon elle referait la même faute.
   → `llm_client.py:220-227`.
5. **Où est la clé, et peut-elle fuir ?** Dans une `SecretStr`, puis seulement dans l'en-tête
   `Authorization` ; jamais journalisée ni citée, même dans une URL refusée ; aucune redirection
   suivie, aucun proxy de l'environnement lu. → `llm_settings.py:142-176`, `llm_client.py:164-179`.

## Zones non vérifiées

- **L'en-tête d'Azure** : `Authorization: Bearer` avec une clé d'API n'est documenté que par
  l'exemple Python de Microsoft (le SDK l'envoie) ; les exemples curl utilisent `api-key`. À
  confirmer par #158.
- **Le 400 `content_filter`** d'Azure sur une entrée filtrée vient de constats publics (Microsoft
  Q&A, forum CrewAI), pas d'une page de référence lue : à confirmer par #158.
- **`reasoning_effort: "none"` contre `temperature: 0`** pour gpt-5.6-luna : les docs d'OpenAI et
  d'Azure se contredisent ; aucun appel réel n'a été fait.
- **Les valeurs des délais** (5, 10, 60, 20 s) sont des hypothèses, non mesurées sur le vrai modèle.
- **La compatibilité réelle** d'un autre fournisseur que celui retenu (les paramètres qu'il
  accepte, `max_completion_tokens` compris) n'a pas été vérifiée.

## Ce qui reste

- Les consignes de classement et de rédaction, leurs rappels, les schémas réels, les contrôles 3 à
  6 et le calcul de `max_completion_tokens` : #205 et #206.
- L'écriture de la ligne de métrique (avec `request_id`, `stage`, coût) et le démarrage de l'API IA
  qui appelle `read_llm_settings` : #156.
- Le premier appel réel, l'en-tête, le réglage de température, les délais mesurés : #158.

## Sources

Consultées le 2026-10-15.

- [Advanced usage, « Reproducible outputs »](https://developers.openai.com/api/docs/guides/advanced-usage)
  — OpenAI, lu par Context7 : « Chat Completions are non-deterministic by default » ; avec `seed`,
  « Determinism is not guaranteed » (section 6).
- [README du SDK `openai`](https://github.com/openai/openai-python/blob/main/README.md) et
  [`src/openai/_client.py`](https://github.com/openai/openai-python/blob/main/src/openai/_client.py)
  — lus par Context7 : l'avertissement sur les types Azure ; les variables d'environnement lues
  (option écartée).
- [API version lifecycle](https://learn.microsoft.com/en-my/Azure/foundry-classic/openai/api-version-lifecycle)
  — Microsoft, relevé par recherche web : `OpenAI(base_url=".../openai/v1/", api_key=...)` pour
  Azure v1 (section 1, en-tête).
- [Transports d'httpx](https://github.com/encode/httpx/blob/master/docs/advanced/transports.md) —
  lu par Context7 : `MockTransport(handler)` (section 3).
- [RFC 9110, § 10.2.3](https://www.rfc-editor.org/rfc/rfc9110#section-10.2.3) — IETF : `Retry-After`
  en secondes ou en date HTTP (section 5).
- [LLM01:2025 Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) — OWASP,
  relevé par recherche web (section 2).
- [Microsoft Q&A 2044545](https://learn.microsoft.com/en-us/answers/questions/2044545/content-filter-and-policy-violation-issues-when-us)
  — relevé par recherche web : le 400 `content_filter` (zones non vérifiées).
