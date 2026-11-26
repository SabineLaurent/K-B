# Garder le code et le paramètre d'une erreur du fournisseur dans la ligne `llm_call`

- **Date** : 2026-11-26
- **Branche** : `feat/provider-error-fields-in-llm-call`, commits `769ba0af` (le code et ses tests) et
  `25098ba3` (les constats des revues), sur `2b8aaed0`
- **Issue** : #710
- **Fichiers principaux** : `src/k_b/ai_api/connectors/llm_client.py`, `src/k_b/ai_api/observability/metrics.py`,
  `tests/ai_api/test_llm_client.py`, `tests/ai_api/test_digest_router.py`, `tests/ai_api/provider_errors.py`,
  `docs/fiches-veille.md` (section « Métriques »)
- **Série** : suite de [Émettre les métriques en OpenTelemetry](2026-10-24-emettre-les-metriques-en-opentelemetry.md)
  et de [Restituer les métriques du modèle et alerter](2026-11-08-restituer-les-metriques-du-modele-et-alerter.md)

## Le pourquoi

Quand le modèle de production est passé de gpt-6-luna à gpt-6.1-sol, l'effort de raisonnement est resté à `none`.
Azure a refusé chaque appel par un 400 dont le corps dit la cause : `code` `unsupported_value`, `param`
`reasoning_effort` (#710, étape 5). La ligne `llm_call` de l'API IA ne disait que `outcome: llm_unavailable` et
`http_status: 400`. Elle désignait le fournisseur, pas la cause, et il a fallu rejouer la demande à la main pour lire
le paramètre refusé.

La ligne `llm_call` est la mesure de chaque appel au modèle : une ligne JSON sur la sortie standard, que Log Analytics
recueille en ligne, et que l'on retrouve par le `request_id` d'une demande (`documentation/monitorage.md`). Elle porte
désormais deux champs de plus, `provider_error_code` et `provider_error_param`. Le refus de #710 s'y lit en une ligne :
`"provider_error_code": "unsupported_value", "provider_error_param": "reasoning_effort"`.

## Le comment

### Ce qu'on lit d'une erreur, et ce qu'on ne lit jamais

L'enveloppe d'une réponse du fournisseur est lue par des modèles Pydantic qui ignorent les champs non déclarés
(`extra="ignore"`). L'erreur ne déclare que deux champs :

```python
class ErrorDetail(EnvelopeModel):
    code: ProviderErrorField = None
    param: ProviderErrorField = None
```

(`src/k_b/ai_api/connectors/llm_client.py:150-152`.) Le `message` et le `type` ne sont pas déclarés : Pydantic les
laisse tomber à la lecture, et ils n'existent dans aucun objet de K-B. C'est voulu. Le message d'Azure cite la valeur
refusée, et le message d'un autre refus peut citer l'entrée, c'est-à-dire le texte des items (règle 5 de `poc.md` : ni
texte d'un item ni auteur dans une mesure). Le `type` (`invalid_request_error`) ne fait que redire le statut d'un 400.

### Une forme fermée, contrôlée sur la valeur entière

```python
MAX_PROVIDER_ERROR_FIELD_LENGTH = 64
PROVIDER_ERROR_FIELD = re.compile(r"[A-Za-z0-9_.\[\]-]+")
OTHER_PROVIDER_ERROR_FIELD = "other"
```

```python
    if value is None:
        return None
    if not isinstance(value, str) or PROVIDER_ERROR_FIELD.fullmatch(value) is None:
        return OTHER_PROVIDER_ERROR_FIELD
    return value[:MAX_PROVIDER_ERROR_FIELD_LENGTH]
```

(`llm_client.py:93-95` et `138-142`.) Une valeur n'est gardée que si elle a, en entier, la forme d'un identifiant : au
moins un caractère, pris parmi les lettres et chiffres ASCII, `_`, `.`, `-`, `[` et `]`. C'est assez pour
`unsupported_value`, `reasoning_effort` ou `messages[0].content`. Une telle valeur est ensuite coupée à 64 caractères,
comme `finish_reason`. Toute autre valeur s'écrit `other` : une chaîne avec un autre caractère, une chaîne vide, un
nombre, une liste. Seule l'absence du champ, ou sa valeur `null`, donne nul.

Pourquoi ne pas compter sur le JSON ? La ligne est écrite par `json.dumps(line, ensure_ascii=False)`
(`src/k_b/ai_api/observability/metrics.py:50`). Le JSON échappe le retour à la ligne et les contrôles C0, si bien
qu'une valeur ne peut pas écrire une fausse ligne. Mais avec `ensure_ascii=False`, il écrit tels quels U+2028,
U+2029, les contrôles C1 (U+0080 à U+009F) et les contrôles bidirectionnels comme U+202E, qui changent l'affichage
d'une ligne lue dans un terminal. La forme fermée les écarte tous : seul de l'ASCII d'identifiant arrive à
`json.dumps`.

`fullmatch` et non `match` : `match` accepterait un début conforme suivi de n'importe quoi. Et `fullmatch` ne tolère
pas un retour à la ligne final, contrairement à un motif terminé par `$`.

### Le validateur passe avant la validation stricte

```python
type ProviderErrorField = Annotated[
    str | None, BeforeValidator(keep_provider_error_field)
]
```

(`llm_client.py:145-147`.) L'enveloppe est en mode strict (`strict=True`). Un `BeforeValidator` reçoit la valeur
brute avant la validation du type, et Pydantic valide ensuite ce qu'il rend contre `str | None` (documentation
Pydantic, « Before validators », lue par Context7 le 2026-11-26). `keep_provider_error_field` rend toujours une chaîne
ou `None`, et ne lève jamais d'erreur. Un `param` qui n'est pas une chaîne n'empêche donc plus de lire le corps
entier. Le code qui reconnaît `content_filter` ne dépend pas de la forme du `param`.

### Toute réponse autre que 200, une seule lecture

```python
    error = read_error(content)
    attempt: Attempt[OutputT] = name_failure(response, error.code)
    return replace(
        attempt, provider_error_code=error.code, provider_error_param=error.param
    )
```

(`llm_client.py:512-516`.) `read_failure` lit l'erreur une fois, pour un 400, un 401, un 429 ou un 5xx. Elle laisse
`name_failure` nommer l'état, avec la même logique qu'avant, puis pose les deux champs sur la tentative.
`name_failure` compare le code déjà mis en forme à `content_filter` (`llm_client.py:529`) : `content_filter` a la
forme d'un identifiant, il passe tel quel. `read_error` rend une erreur vide quand le corps n'est pas une erreur de
l'enveloppe (HTML d'une passerelle, JSON d'une autre forme, `llm_client.py:552-557`) : les deux champs restent nuls.

### De la tentative à la ligne

`summarize` garde les champs de la dernière tentative, comme `http_status` (`llm_client.py:690-691`), et
`build_llm_call_line` les écrit juste après lui (`metrics.py:92-93`). Le code et le statut se lisent ainsi sur la même
tentative. Après un 503 suivi d'une réponse 200, les deux champs sont nuls. Après un 503 suivi d'un délai, ils sont
nuls aussi, comme `http_status`, puisque la dernière tentative n'a pas eu de réponse.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Une forme fermée d'identifiant | Elle écarte tous les caractères que `json.dumps(ensure_ascii=False)` laisse passer, et ne garde qu'un nom choisi par le fournisseur (code.md, « type fermé à la frontière ») | La coupe seule à 64 caractères, comme `finish_reason` : elle laisse passer U+2028, C1 et bidirectionnels. `quote_value` (règle 3 de `conventions.md`) : il ajoute les guillemets de `repr` dans un champ JSON, et le JSON protège déjà des fausses lignes, comme pour le journal d'import |
| Le contrôle sur la valeur entière, puis la coupe | Une valeur qui n'est pas un identifiant n'est jamais gardée, même en partie (constat de la revue) | La coupe puis le contrôle : 64 caractères d'identifiant suivis d'un texte gardaient leurs 64 premiers |
| `other` pour une valeur hors forme | Nul dit « le fournisseur n'en a pas donné » ; `other` dit « il en a donné une, non gardée », et invite à rejouer la demande. Même mot que `OTHER_FINISH_REASON` des spans | Nul : il effacerait la présence d'un code |
| Un caractère au moins (`+`) | Une chaîne vide n'est pas un identifiant : `other` (constat de la revue) | `*` : la chaîne vide était gardée telle quelle, ni nulle ni `other` |
| `provider_error_code`, `provider_error_param` | La ligne porte déjà `outcome` et `failed_check`, des états de K-B ; le préfixe dit d'où vient la valeur | `error_code` : il se confondrait avec un état de K-B |
| `code` et `param` seulement | Ce que propose #710 ; le `param` nomme le champ refusé | `type`, qui redit le statut ; `message`, qui peut citer l'entrée |
| Toute réponse autre que 200 | Un 429 ou un 5xx d'Azure porte aussi un code, et une seule lecture sert à tous | Les seuls 4xx : deux lectures pour un même corps |
| La dernière tentative, comme `http_status` | Le code et le statut d'une ligne décrivent la même réponse | Porter le dernier code non nul d'une tentative à l'autre : il décrirait une autre réponse que `http_status` |
| Un code numérique s'écrit `other` | Azure rend des chaînes (corps cités dans #710) ; en Python, un `bool` est aussi un `int` | Le garder en décimal : une branche de plus pour un fournisseur que K-B n'appelle pas |
| Aucun attribut OpenTelemetry | Une valeur ouverte en attribut de métrique multiplie les séries ; les spans ne portent que des valeurs fermées (`TRACED_FINISH_REASONS`) | Un attribut `k_b.provider_error_code` |
| La réponse Azure des tests dans `tests/ai_api/provider_errors.py` | Une connaissance à un seul endroit (code.md), importée par les deux modules de tests, comme `tests/exchange/storage_fakes.py` | Deux copies, dont les messages divergeaient déjà (constat de la revue) |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| Avant le code : 21 tests nouveaux en échec (19 `AttributeError` sur `provider_error_code`, 1 `KeyError`, la liste des champs de la ligne) | Les tests échouaient sans le changement, pour la raison attendue |
| `test_the_code_and_the_param_of_a_refused_request_are_kept_never_its_message` (`tests/ai_api/test_llm_client.py:845`) | Le 400 de #710 garde `unsupported_value` et `reasoning_effort`, reste `llm_unavailable` en une tentative, et ni le repère du message ni le `type` ne sont dans l'appel |
| `test_the_code_and_the_param_of_any_answer_but_a_200_are_kept` (`:877`, cas 401, 429, 503) | La lecture vaut pour toute réponse autre que 200 |
| `test_a_code_or_a_param_out_of_the_shape_of_an_identifier_is_kept_as_other` (`:918`, 11 cas) | Un identifiant est gardé, coupé à 64 ; une valeur plus longue suivie d'un texte, une chaîne vide, un retour à la ligne suivi d'une fausse ligne, U+202E, un C1, une espace, un nombre et une liste donnent `other` ; `null` donne nul |
| `test_a_filtered_prompt_whose_param_is_not_a_string_is_still_filtered` (`:928`) | Un `param` objet ne casse plus la lecture : le 400 reste `llm_content_filtered` |
| `test_a_last_answer_without_code_nor_param_keeps_none` (`:951`, 5 cas) | Un 200, un 503 suivi d'un 200, un délai, un 400 sans code et un 400 qui n'est pas du JSON laissent les deux champs nuls |
| `test_a_request_refused_by_the_provider_writes_its_code_and_param_never_its_message` (`tests/ai_api/test_digest_router.py:681`) | De bout en bout : la demande répond 502 `llm_unavailable`, sa ligne porte les deux champs, et le repère du message n'est ni sur la sortie standard, ni sur la sortie d'erreur, ni dans le journal |
| `METRIC_FIELDS` dans `test_each_call_writes_one_json_line_on_stdout_without_a_text` | Les deux champs suivent `http_status`, dans l'ordre de la table de `docs/fiches-veille.md` |
| Après les revues : les 2 cas nouveaux (`too-long-then-text`, `empty`) en échec, puis `uv run pytest` 5 860 passés ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` verts | Les constats corrigés sont tenus par un test |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas garder le message, qui est le plus parlant ?** Il peut citer l'entrée, donc le texte d'un item,
   et la règle 5 de `poc.md` l'interdit dans une mesure. Le `code` et le `param` suffisent à nommer la cause : le
   paramètre refusé et le motif du refus. `ErrorDetail` ne déclare pas `message`, si bien qu'il n'est jamais lu
   (`llm_client.py:150-152`).
2. **Un fournisseur malveillant peut-il écrire une fausse ligne dans le journal ?** Non. Le JSON échappe déjà le
   retour à la ligne, et la forme fermée ne laisse passer que de l'ASCII d'identifiant. Tout autre caractère, y compris
   U+2028 ou U+202E, donne `other` (`llm_client.py:138-142`, test des formes).
3. **La règle 3 de `conventions.md` demande `quote_value` : pourquoi ne pas s'en servir ?** Cette règle protège une
   ligne de texte. La ligne `llm_call` est du JSON, protégé par son encodage, comme le journal d'import que nomme la
   même règle. `quote_value` y ajouterait les guillemets de `repr`, et la forme fermée va plus loin que l'échappement.
4. **Que se passe-t-il si Azure rend une page HTML pour un 502 ?** `read_error` ne peut pas la lire comme une erreur
   de l'enveloppe et rend une erreur vide. Les deux champs sont nuls, l'état reste `llm_unavailable` avec une nouvelle
   tentative, comme avant (`llm_client.py:552-557`, cas `400-not-json`).
5. **Pourquoi `other` plutôt que nul ?** Nul et `other` ne disent pas la même chose. Nul veut dire que le fournisseur
   n'a rien donné. `other` veut dire qu'il a donné une valeur que K-B ne garde pas, et qu'il faut rejouer la demande
   pour la lire.

## Zones non vérifiées

- Les corps d'erreur d'un 429 et d'un 5xx d'Azure ne sont pas rejoués : les tests leur donnent un corps écrit pour
  eux, de la même enveloppe que le 400 observé dans #710. Un corps d'une autre forme laisse les deux champs nuls, ce
  que vérifie le cas `400-not-json`.
- La preuve de bout en bout rejoue le corps du 400 relevé dans #710 (étape 5), par le fournisseur `replay`. Aucun
  appel au fournisseur réel n'a été fait : un appel est payant, et la sortie d'Azure est déjà citée dans l'issue.

## Ce qui reste

- Le journal de fonctionnement de la demande (la ligne `request … status=502`) ne porte pas les deux champs : son
  `request_id` mène à la ligne `llm_call`, qui les porte.
- Aucune mesure OpenTelemetry ni aucun span ne porte le code ou le paramètre (choix ci-dessus) : une alerte reste
  fondée sur `k_b_llm_calls_total` et son `k_b_outcome`, et la cause se lit dans la ligne `llm_call`.
