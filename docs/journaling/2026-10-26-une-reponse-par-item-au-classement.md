# Une réponse par item au classement (`classify-2`)

- **Date** : 2026-10-26
- **Branche** : `feat/classify-one-answer-per-item`
- **Issue** : #210 (essais des fiches sur la veille réelle)
- **Suite de** : [2026-10-17-classer-les-items-et-rediger-les-fiches.md](2026-10-17-classer-les-items-et-rediger-les-fiches.md)
- **Fichiers principaux** :
  - `src/k_b/ai_api/stages/classification.py` : la consigne, le schéma, la sortie et ses contrôles ;
  - `src/k_b/ai_api/digests.py` : les trois cas du classement ;
  - `src/k_b/ai_api/connectors/llm_client.py` : le refus d'une clé JSON présente deux fois ;
  - `src/k_b/ai_api/observability/` : les deux compteurs ;
  - `src/k_b/ai_api/schemas/digest_schema.py`, `docs/api/openapi-ia.json` : le champ `unanswered` ;
  - `src/k_b/core/config.py` : le nom réservé `no_suitable_subject` ;
  - `docs/fiches-veille.md`, `docs/ADR/journal-decisions-projet.md` : le contrat et les décisions.

## Le pourquoi

Le classement est la première étape d'une fiche : l'API IA envoie les items de la fenêtre au
modèle par lots de 50, et lui demande le sujet de chacun. Un lot refusé deux fois fait échouer
toute la demande : aucune fiche n'est écrite.

C'est ce qui s'est passé à l'essai 1 de #210, le 2026-10-26, sur la veille réelle (268 items,
gpt-6-luna). Avec `classify-1`, la sortie était deux listes : `assignments` (`item_id`, `subject`)
et `not_retained`. Dans le 4e lot, 50 articles TLDR, le modèle a cité deux items deux fois, à la
fois avec un sujet et dans « non retenu » (`i2838` : `models` et `not_retained` ; `i2902` :
`coding_assistants` et `not_retained`). Le contrôle 5 a refusé la sortie aux deux tentatives, et
la demande a rendu un 502 `llm_invalid_output`. Un rejeu du lot, qui n'affichait que les
identifiants, l'a montré.

Le mode strict des sorties structurées ne pouvait pas l'empêcher : il ne prend pas en charge
`uniqueItems`, le mot-clé qui interdirait un doublon dans une liste. Cette PR change la forme de la
sortie pour que le doublon ne puisse plus s'écrire. Elle distingue aussi, à la demande de Sabine,
trois cas qui étaient mêlés : l'item catégorisé, l'item auquel aucun sujet ne convient (un jugement
du modèle), et l'item laissé sans réponse (un raté du modèle).

## Le comment

### 1. Une propriété obligatoire par item

`src/k_b/ai_api/stages/classification.py:156-165`

```python
    answers = [*subject_names, NO_SUITABLE_SUBJECT_ANSWER]
    return {
        "type": "object",
        "properties": {
            item_ref: {"type": "string", "enum": list(answers)}
            for item_ref in item_refs
        },
        "required": list(item_refs),
        "additionalProperties": False,
    }
```

Le schéma envoyé au modèle n'a plus de liste. Il a une propriété par item du lot (`"i2838"`),
toutes dans `required`, et aucune autre (`additionalProperties: false`). Chaque valeur est prise
dans une liste fermée : les sujets, plus `no_suitable_subject`. En mode strict, le fournisseur
contraint la génération au schéma : un objet JSON n'a qu'une valeur par propriété, et une propriété
obligatoire ne peut pas manquer. Le modèle ne peut donc ni répondre deux fois pour un item, ni,
en principe, en oublier un. D'après la doc Azure, la sortie suit aussi l'ordre des propriétés du
schéma, donc l'ordre du lot.

Chaque propriété reçoit son propre sous-schéma, et sa propre copie de la liste (`list(answers)`) :
une première version partageait un seul dictionnaire entre les 50 propriétés, et la revue de code
l'a relevé.

La consigne passe à `classify-2` (`classification.py:27`) et dit la même chose en prose (« Answer
once for each item, under its "item_id" », l. 36). Elle ne fait pas la sécurité : c'est le schéma
et les contrôles qui la font.

### 2. La sortie lue comme un dictionnaire

`src/k_b/ai_api/stages/classification.py:72`

```python
class ClassificationOutput(RootModel[dict[str, str]]):
```

Les noms des propriétés changent à chaque lot (les identifiants des items). Le modèle Pydantic ne
peut donc pas les déclarer : un `RootModel` lit l'objet entier comme un dictionnaire
identifiant → réponse. Les listes fermées sont dans le schéma envoyé, et les contrôles 3 et 4 les
revérifient.

### 3. Les contrôles 3 à 5 revérifient

`src/k_b/ai_api/stages/classification.py:176-185`

```python
    answers = output.root
    if any(
        answer not in subject_names and answer != NO_SUITABLE_SUBJECT_ANSWER
        for answer in answers.values()
    ):
        return "subject"
    if any(ref not in item_refs for ref in answers):
        return "item_id"
    if not answers:
        return "completeness"
```

Le code ne se fie pas au mode strict (défense en profondeur, OWASP LLM01) : un fournisseur sans
mode strict, ou le modèle de remplacement des tests, peut rendre n'importe quoi. Une réponse qui
n'est ni un sujet de la liste ni `no_suitable_subject` donne `subject` ; un identifiant qui n'est
pas du lot donne `item_id`. Ces deux cas peuvent venir d'une injection : la sortie est refusée,
avec une nouvelle tentative.

Le contrôle 5 refuse une sortie qui ne répond à **aucun** item (`{}`). Un objet vide passe la
validation du `RootModel` : sans ce contrôle, tout le lot deviendrait « non traité » et la demande
rendrait un 200 sans fiche, sans nouvelle tentative. La revue de code de niveau `high` l'a montré.
Un item oublié parmi d'autres, lui, n'est pas refusé (section suivante) : c'est un raté sur un
item, alors qu'une sortie vide ne trie rien.

### 4. Les trois cas : catégorisé, sans sujet adapté, non traité

`src/k_b/ai_api/digests.py:270-286`

```python
    answer_by_item_id = {
        item.item_id: answer_by_ref.get(to_item_ref(item.item_id)) for item in items
    }
    return Classification(
        subject_by_item_id={
            item_id: answer
            for item_id, answer in answer_by_item_id.items()
            if answer is not None and answer != NO_SUITABLE_SUBJECT_ANSWER
        },
        not_retained=tuple(
            item_id
            for item_id, answer in answer_by_item_id.items()
            if answer == NO_SUITABLE_SUBJECT_ANSWER
        ),
        unanswered=tuple(
            item_id for item_id, answer in answer_by_item_id.items() if answer is None
        ),
```

Après tous les lots, chaque item lu a une réponse, ou aucune (`None`). Trois groupes en sortent,
dans l'ordre de la lecture :

- **catégorisé** : un sujet de la liste ; l'item part à la rédaction de ce sujet ;
- **sans sujet adapté** : `no_suitable_subject`, un **jugement** du modèle ; l'item va dans
  `not_retained` ;
- **non traité** : aucune réponse, un **raté** du modèle ; l'item va dans `unanswered`, champ
  nouveau de la réponse (version 0.3.0 de l'API IA).

Un item non traité ne fait pas échouer le lot : les autres réponses sont bonnes, et une seule
perte ne doit pas faire tomber toutes les fiches. Il est compté à part pour ne pas passer pour un
jugement. Chaque ligne de métrique du classement porte les deux compteurs
(`digests.py:249-254`), et OpenTelemetry les reprend (`k_b.digest.items_not_retained`,
`k_b.digest.items_unanswered`).

### 5. Une clé présente deux fois est refusée

`src/k_b/ai_api/connectors/llm_client.py:442-456`

```python
    try:
        json.loads(content, object_pairs_hook=refuse_key_twice)
    except (ValueError, RecursionError):
        return False
    return True
```

En JSON, rien n'interdit d'écrire deux fois la même clé dans un objet (`{"i1": "a", "i1": "b"}`).
Pydantic garde alors la dernière valeur **sans rien signaler** : c'est vérifié en séance avec
Pydantic 2.13.5. Le doublon de l'essai 1 serait réparé en silence.

`is_json_without_key_twice` relit le texte avec la bibliothèque standard : `object_pairs_hook`
reçoit les paires (clé, valeur) de chaque objet, à toutes les profondeurs, avant qu'elles ne
deviennent un dictionnaire, et `refuse_key_twice` lève `KeyTwiceError` (une `ValueError`) dès
qu'une clé revient. La fonction **échoue fermé** : un texte que `json` ne lit pas (`ValueError`)
ou trop imbriqué pour lui (`RecursionError`) est refusé lui aussi, puisqu'une sortie valide du
modèle est toujours du JSON. Une première version le laissait à Pydantic : la revue de code
(niveau `high`) l'a relevé, et la règle « Échouer fermé » de `code.md` l'impose. Sans le
`RecursionError`, une sortie `[[[[…` aurait remonté jusqu'à la route et donné un 500 au lieu d'un
refus. L'appel se fait avant la validation, aux deux étapes (`llm_client.py:414`) : le refus
devient `schema`, avec une nouvelle tentative.

### 6. `no_suitable_subject`, un nom réservé

`src/k_b/core/config.py:276`

```python
NO_SUITABLE_SUBJECT_ANSWER = "no_suitable_subject"
```

La valeur dit au modèle pourquoi il la choisit (« not suitable category », Sabine), mieux que
`not_retained`. Si un sujet s'appelait ainsi, ses items seraient lus comme sans sujet adapté : le
nom est réservé, comme `tops` l'est pour les dossiers du coffre, et un test le tient
(`test_no_subject_takes_the_answer_of_no_subject`). Dans la réponse de l'API, le champ garde son
nom, `not_retained`, qui est le contrat existant.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Options écartées, et pourquoi |
|---|---|---|
| Une propriété obligatoire par item | L'état fautif ne peut plus s'écrire en mode strict | Dédoublonner par le code : il réparerait en silence ce que le modèle écrit. Laisser un lot échouer sans faire tomber la demande : utile en plus, mais ne corrige pas la cause. Des lots plus petits : la probabilité baisse, le cas reste. Une phrase de plus dans la consigne : une règle en prose ne tient pas (veille de l'existant, 2026-09-23, « Ce qui converge », point 3) |
| Trois cas distincts, l'item non traité compté à part sans échec | Décision de Sabine : un jugement et un raté sont deux choses ; le seuil « aucun item oublié » de #210 devient mesurable | Faire échouer le lot pour un item sans réponse : proposé un temps dans la même PR, il ferait tomber toutes les fiches pour un item perdu. Le compter « non retenu » sans compteur : une panne passerait pour un jugement |
| La valeur `no_suitable_subject`, le champ de réponse `not_retained` gardé | La valeur s'adresse au modèle, le champ est un contrat existant | Renommer aussi le champ de réponse : un changement de contrat sans gain |
| Un champ `unanswered` dans la réponse, version 0.3.0 | Un champ ajouté ne casse aucun client ; `kb digest` ignore les champs qu'il ne connaît pas | Seulement un compteur : l'item raté ne serait pas nommé |
| `RootModel[dict[str, str]]` | Les noms de propriétés changent à chaque lot ; le schéma envoyé est déjà écrit à la main | Un modèle Pydantic créé à chaque lot (`create_model`) : plus lourd, pour la même vérification |
| Le refus d'une clé en double dans `llm_client.py`, aux deux étapes | Pydantic garde la dernière valeur sans le dire | Le seul classement : une clé en double dans la sortie de la rédaction serait aussi une sortie fautive |
| Un seul sujet par item | Décision de Sabine : « pour le moment on met une case pour avancer » | Un sujet secondaire par item : idée de Sabine, à décider après les essais de #210 (décisions encore ouvertes du journal ADR) |

## Preuve

| Test | Ce que ça démontre |
|---|---|
| `test_an_item_answered_twice_at_the_classification_is_llm_invalid_output` (`tests/ai_api/test_digests.py:338`) | Le cas de l'essai 1 (un item avec un sujet, puis sans sujet adapté) est refusé en `schema` |
| `test_an_item_without_answer_is_counted_apart_without_failure` (`test_digests.py:304`) | Un item oublié n'arrête rien : il va dans `unanswered`, séparé de `not_retained`, et les compteurs du lot valent (2, 1) |
| `test_an_answer_to_no_item_is_asked_again_then_fails_the_request` et `test_an_answer_to_no_item_then_a_valid_one_passes` (`test_digests.py:318`) | Une sortie vide est refusée en `completeness`, redemandée une fois, et fait échouer la demande si elle revient |
| `test_each_call_writes_one_json_line_on_stdout_without_a_text` (`tests/ai_api/test_digest_router.py:517`) | La ligne de classement porte `items_not_retained` et `items_unanswered`, dans l'ordre de la spec ; nuls à la rédaction |
| le test des compteurs OpenTelemetry (`test_digest_router.py`) | `k_b.digest.items_not_retained` et `k_b.digest.items_unanswered` reprennent la ligne JSON |
| `test_a_subject_out_of_the_list_is_refused` (`test_digests.py`) | Une réponse hors liste donne `subject` ; chaque propriété du schéma porte les sujets plus `no_suitable_subject` |
| le paramètre `TRAPPED_TWICE` du test de l'item piégé (`test_digests.py`) | Le doublon que demande le piège de #206 est refusé en `schema` |
| `test_an_output_out_of_its_model_fails_the_schema_check[key-twice]`, `test_only_json_without_a_key_twice_is_read`, `test_an_output_nested_too_deep_fails_the_schema_check` (`tests/ai_api/test_llm_client.py`) | Une clé en double est refusée même quand la dernière valeur serait valide, à toute profondeur ; un JSON trop imbriqué donne `schema`, pas un 500 |
| `test_the_classification_model_reads_every_answer_the_schema_allows` (`tests/ai_api/test_stages.py`) | Le schéma envoyé et le modèle qui lit la sortie restent liés : chaque valeur de chaque `enum`, sous chaque propriété obligatoire, passe la validation stricte |
| `test_the_schema_of_a_full_batch_is_within_the_bounds_of_strict_mode` (`tests/ai_api/test_stages.py:254`) | Un lot plein (50 items, les 8 vrais sujets) tient sous 100 propriétés, 500 valeurs d'`enum` et 15 000 caractères |
| `test_the_versioned_openapi_is_the_one_the_app_produces` (`tests/ai_api/test_ai_api_openapi.py`) | `docs/api/openapi-ia.json`, régénéré par `uv run kb openapi`, porte `unanswered` et la version 0.3.0 |
| `uv run pytest` : 2 622 tests ; `ruff check`, `ruff format --check`, `mypy --strict` | Rien d'autre n'est cassé |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas demander `uniqueItems` dans le schéma ?** Le mode strict ne le prend pas en
   charge : il figure dans la table des mots-clés refusés d'Azure et dans la liste du guide
   OpenAI. Il fallait une forme où le doublon est impossible, d'où l'objet.
2. **Si le mode strict garantit déjà tout, pourquoi les contrôles ?** Parce que le code ne s'y fie
   pas : un autre fournisseur, ou le replay, rend ce qu'il veut. Les contrôles refusent un
   doublon, une réponse hors liste, un item inventé, une sortie vide (`classification.py:176-185`,
   `llm_client.py:442`), et l'item oublié est compté (`digests.py:270-286`).
3. **Pourquoi refuser une clé en double, puisque le JSON l'accepte ?** Parce que Pydantic garderait
   la dernière valeur sans rien dire : on ne saurait pas que le modèle a hésité, et le code
   choisirait à sa place.
4. **Pourquoi un item oublié n'arrête-t-il pas la demande, alors qu'un doublon l'arrête ?** Un
   doublon est ambigu, et peut venir d'une injection : le code ne doit pas trancher. Un oubli ne
   fait rien entrer de dangereux : on perd un item, on le dit (`unanswered`, `items_unanswered`),
   et les fiches des autres sont rendues. Faire tomber toute la veille pour un item serait
   disproportionné.
5. **Et si la liste des sujets grandit ?** Chaque item porte toute la liste fermée : 50 items et
   8 sujets font 450 valeurs d'`enum`. Un 10e sujet en ferait 550, au-delà de 500, la limite la
   plus stricte connue, et le test de bornes échouerait avant tout appel réel
   (`tests/ai_api/test_stages.py:254`). Il faudrait alors des lots plus petits, ou une définition
   partagée (`$defs`), dont le décompte n'est pas vérifié.

## Zones non vérifiées

- **`classify-2` n'a pas encore tourné sur gpt-6-luna.** L'essai 1 de #210 sera rejoué après la
  fusion. La garantie « une propriété obligatoire ne manque jamais » vient de la doc du mode
  strict, pas d'une mesure : `items_unanswered` la mesurera.
- **Les limites de 500 valeurs d'`enum` et de 15 000 caractères** viennent d'erreurs rapportées
  sur le forum d'OpenAI (sources secondaires) ; la page Azure ne donne aucune limite d'`enum`, et
  la doc OpenAI relevée le 16/10 disait 1 000 valeurs. Le test applique les chiffres les plus
  stricts, et compte chaque sous-schéma répété une fois par propriété : c'est le pire cas.
- **`json.loads` et Pydantic ne lisent pas exactement les mêmes textes** (`NaN`, lu par `json`
  et refusé par Pydantic, vérifié en séance). L'écart ne laisse plus rien passer : un texte que
  `json` refuse est refusé, et un texte qu'il lit passe ensuite Pydantic.
- **Le coût en jetons de la nouvelle sortie** (environ 10 jetons par item, estimé) n'est pas
  mesuré ; `CLASSIFICATION_MAX_COMPLETION_TOKENS` reste à 2 048, une large marge.

## Ce qui reste

- Rejouer l'essai 1 de #210 sur la base du 26/10, puis les essais 2 et 3, et les consigner dans
  `docs/fiches-veille.md`.
- Une seconde chance ciblée (redemander les seuls items non traités, une fois), si les essais en
  montrent.
- Un lot refusé (sujet ou item inventé, doublon) fait encore échouer toute la demande. Si le
  classement passe en annotation des items en base, item par item (piste du 2026-10-26), ce point
  disparaît de lui-même ; d'ici là, il reste une limite écrite.
- Le sujet secondaire par item : décision ouverte, après les essais.
- Le rejeu de l'item piégé sur gpt-6-luna (#210), qui attend l'accord de Sabine.

## Sources

| Source | Consultée | Ce qu'elle établit |
|---|---|---|
| [Azure, structured outputs](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs) (page du 2026-08-24) | 2026-10-26 | 100 propriétés d'objet par schéma, 5 niveaux ; `uniqueItems` refusé ; la sortie suit l'ordre du schéma |
| [OpenAI, prompt generation (méta-schéma des sorties structurées)](https://developers.openai.com/api/docs/guides/prompt-generation), via Context7 | 2026-10-26 | `uniqueItems` n'est pas pris en charge en mode strict |
| [Forum OpenAI, « 500 Enums Limitation in Structured Output »](https://community.openai.com/t/500-enums-limitation-in-structured-output/974416) | 2026-10-26 | une erreur réelle plafonne un schéma à 500 valeurs d'`enum` (source secondaire) |
| [Forum OpenAI, « Possible Structured Output Schema Length Error »](https://community.openai.com/t/possible-structured-output-schema-length-error-bug-in-api/984509) | 2026-10-26 | une erreur réelle plafonne les chaînes d'un schéma à environ 15 000 caractères (source secondaire) |
