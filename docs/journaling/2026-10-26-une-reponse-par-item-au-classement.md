# Une réponse par item au classement (`classify-2`)

- **Date** : 2026-10-26
- **Branche** : `feat/classify-one-answer-per-item`
- **Issue** : #210 (essais des fiches sur la veille réelle)
- **Suite de** : [2026-10-17-classer-les-items-et-rediger-les-fiches.md](2026-10-17-classer-les-items-et-rediger-les-fiches.md)
- **Fichiers principaux** :
  - `src/k_b/ai_api/stages/classification.py` : la consigne, le schéma, la sortie et ses contrôles ;
  - `src/k_b/ai_api/connectors/llm_client.py` : le refus d'une clé JSON présente deux fois ;
  - `src/k_b/ai_api/digests.py` : la lecture de la nouvelle sortie ;
  - `src/k_b/core/config.py` : le nom réservé `not_retained` ;
  - `docs/fiches-veille.md`, `docs/ADR/journal-decisions-projet.md` : le contrat et la décision.

## Le pourquoi

Le classement est la première étape d'une fiche : l'API IA envoie les items de la fenêtre au
modèle par lots de 50, et lui demande le sujet de chacun, ou « non retenu ». Un lot refusé deux
fois fait échouer toute la demande : aucune fiche n'est écrite.

C'est ce qui s'est passé à l'essai 1 de #210, le 2026-10-26, sur la veille réelle (268 items,
gpt-6-luna). Avec `classify-1`, la sortie était deux listes : `assignments` (`item_id`, `subject`)
et `not_retained`. Dans le 4e lot, 50 articles TLDR, le modèle a cité deux items deux fois, à la
fois avec un sujet et dans « non retenu » (`i2838` : `models` et `not_retained` ; `i2902` :
`coding_assistants` et `not_retained`). Le contrôle 5 (complétude) a refusé la sortie aux deux
tentatives, et la demande a rendu un 502 `llm_invalid_output`. Un rejeu du lot, qui n'affichait
que les identifiants, l'a montré.

Le mode strict des sorties structurées ne pouvait pas l'empêcher : il ne prend pas en charge
`uniqueItems`, le mot-clé qui interdirait un doublon dans une liste. Cette PR change la forme de la
sortie pour que le doublon ne puisse plus s'écrire.

## Le comment

### 1. Une propriété obligatoire par item

`src/k_b/ai_api/stages/classification.py:159-165`

```python
    answer = {"type": "string", "enum": [*subject_names, NOT_RETAINED_ANSWER]}
    return {
        "type": "object",
        "properties": {item_ref: answer for item_ref in item_refs},
        "required": list(item_refs),
        "additionalProperties": False,
    }
```

Le schéma envoyé au modèle n'a plus de liste. Il a une propriété par item du lot (`"i2838"`),
toutes dans `required`, et aucune autre (`additionalProperties: false`). Chaque valeur est prise
dans une liste fermée : les sujets, plus `not_retained`. En mode strict, le fournisseur contraint
la génération au schéma : un objet JSON n'a qu'une valeur par propriété, et une propriété
obligatoire ne peut pas manquer. Le modèle ne peut donc ni répondre deux fois pour un item, ni en
oublier un. D'après la doc Azure, la sortie suit aussi l'ordre des propriétés du schéma, donc
l'ordre du lot.

La consigne passe à `classify-2` (`classification.py:27`) et dit la même chose en prose
(« Answer once for each item, under its "item_id" », l. 36). Elle ne fait pas la sécurité : c'est
le schéma et les contrôles qui la font.

### 2. La sortie lue comme un dictionnaire

`src/k_b/ai_api/stages/classification.py:73`

```python
class ClassificationOutput(RootModel[dict[str, str]]):
```

Les noms des propriétés changent à chaque lot (les identifiants des items). Le modèle Pydantic ne
peut donc pas les déclarer : un `RootModel` lit l'objet entier comme un dictionnaire
identifiant → réponse. Les listes fermées sont dans le schéma envoyé, et les contrôles 3 à 5 les
revérifient.

### 3. Les contrôles 3 à 5 revérifient tout

`src/k_b/ai_api/stages/classification.py:175-185`

```python
    answers = output.root
    if any(
        answer not in subject_names and answer != NOT_RETAINED_ANSWER
        for answer in answers.values()
    ):
        return "subject"
    if any(ref not in item_refs for ref in answers):
        return "item_id"
    if any(ref not in answers for ref in item_refs):
        return "completeness"
```

Le code ne se fie pas au mode strict (défense en profondeur, OWASP LLM01) : un fournisseur sans
mode strict, ou le modèle de remplacement des tests, peut rendre n'importe quoi. Trois contrôles,
dans l'ordre :

- 3, une réponse qui n'est ni un sujet de la liste ni `not_retained` donne `subject` ;
- 4, un identifiant qui n'est pas du lot donne `item_id` ;
- 5, un item du lot sans réponse donne `completeness`.

Le dernier est nouveau : avec `classify-1`, un item absent était compté « non retenu ».

### 4. Une clé présente deux fois est refusée

`src/k_b/ai_api/connectors/llm_client.py:440-457`

```python
    try:
        json.loads(content, object_pairs_hook=refuse_key_twice)
    except KeyTwiceError:
        return True
    except (ValueError, RecursionError):
        return False
```

En JSON, rien n'interdit d'écrire deux fois la même clé dans un objet (`{"i1": "a", "i1": "b"}`).
Pydantic garde alors la dernière valeur **sans rien signaler** : c'est vérifié en séance avec
Pydantic 2.13.5. Un item répondu deux fois passerait donc pour un item répondu une fois, et le
doublon de l'essai 1 serait réparé en silence.

`has_key_twice` relit le texte avec la bibliothèque standard : `object_pairs_hook` reçoit les
paires (clé, valeur) de chaque objet, à toutes les profondeurs, avant qu'elles ne deviennent un
dictionnaire. `refuse_key_twice` lève une exception dès qu'une clé revient. Un texte qui n'est pas
du JSON (`ValueError`), ou trop imbriqué pour `json` (`RecursionError`), est laissé au contrôle 2,
que fait ensuite Pydantic. Sans le `RecursionError`, une sortie `[[[[…` aurait remonté jusqu'à la
route et donné un 500 au lieu d'un refus.

L'appel se fait avant la validation, aux deux étapes (`llm_client.py:414`) : le refus devient
`schema`, avec une nouvelle tentative, comme un JSON mal formé.

### 5. `not_retained`, un nom réservé

`src/k_b/core/config.py:276`

```python
NOT_RETAINED_ANSWER = "not_retained"
```

Si un sujet s'appelait `not_retained`, ses items seraient lus comme non retenus. Le nom est donc
réservé, comme `tops` l'est pour les dossiers du coffre, et un test le tient
(`test_no_subject_takes_the_answer_of_no_subject`). Le parcours lit la sortie en écartant cette
valeur (`digests.py:252-258`) ; un item sans sujet reste compté « non retenu » par le code, comme
avant.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Options écartées, et pourquoi |
|---|---|---|
| Une propriété obligatoire par item | L'état fautif ne peut plus s'écrire en mode strict | Dédoublonner par le code : il réparerait en silence ce que le modèle écrit, et choisirait à sa place. Laisser un lot échouer sans faire tomber la demande : utile en plus, mais ne corrige pas la cause, et les items du lot seraient perdus. Des lots plus petits : la probabilité baisse, le cas reste. Une phrase de plus dans la consigne : une règle en prose ne tient pas (veille de l'existant, 2026-09-23, « Ce qui converge », point 3) |
| Un item sans réponse est un échec (`completeness`) | Le mode strict ne laisse plus en omettre un : un oubli ne vient plus que d'un fournisseur sans mode strict ou du replay, où échouer fermé vaut mieux (`code.md`) | Garder « absent = non retenu ». **Inverse** la décision du 2026-10-15 (PR de #203), prise quand la sortie était une liste où un petit modèle oubliait un item sur 60 |
| `RootModel[dict[str, str]]` | Les noms de propriétés changent à chaque lot ; le schéma envoyé est déjà écrit à la main | Un modèle Pydantic créé à chaque lot (`create_model`) : plus lourd, pour la même vérification |
| Le refus d'une clé en double dans `llm_client.py`, aux deux étapes | Pydantic garde la dernière valeur sans le dire | Le seul classement : une clé en double dans la sortie de la rédaction serait aussi une sortie fautive |
| Un seul sujet par item | Décision de Sabine : « pour le moment on met une case pour avancer » | Un sujet secondaire par item : idée de Sabine, à décider après les essais de #210 (décisions encore ouvertes du journal ADR) |

## Preuve

| Test | Ce que ça démontre |
|---|---|
| `test_an_item_answered_twice_at_the_classification_is_llm_invalid_output` (`tests/ai_api/test_digests.py:314`) | Le cas de l'essai 1 (un item avec un sujet, puis `not_retained`) est refusé en `schema`, et la demande échoue fermée |
| `test_an_item_without_answer_is_llm_invalid_output` (`test_digests.py:304`) | Un item oublié est maintenant un échec `completeness` |
| `test_a_subject_out_of_the_list_is_refused` (`test_digests.py`) | Une réponse hors liste donne `subject` ; chaque propriété du schéma porte les sujets plus `not_retained` |
| le paramètre `TRAPPED_TWICE` du test de l'item piégé (`test_digests.py`) | Le doublon que demande le piège de #206 est refusé en `schema` |
| `test_an_output_out_of_its_model_fails_the_schema_check[key-twice]` (`tests/ai_api/test_llm_client.py`) | Une clé en double est refusée même quand la dernière valeur serait valide |
| `test_a_key_twice_is_found_at_any_depth` et `test_an_output_nested_too_deep_fails_the_schema_check` (`test_llm_client.py`) | La clé en double est trouvée à toute profondeur ; un JSON trop imbriqué donne `schema`, pas un 500 |
| `test_the_schema_of_a_full_batch_is_within_the_bounds_of_strict_mode` (`tests/ai_api/test_stages.py:244`) | Un lot plein (50 items, les 8 vrais sujets) tient sous 100 propriétés et 1 000 valeurs d'`enum` |
| `test_the_schemas_carry_the_enums_of_the_call` (`test_stages.py`) | Les propriétés sont les items du lot, dans leur ordre |
| `uv run pytest` : 2 622 tests ; `ruff check`, `ruff format --check`, `mypy --strict` | Rien d'autre n'est cassé |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas demander `uniqueItems` dans le schéma ?** Le mode strict ne le prend pas en
   charge : il figure dans la table des mots-clés refusés d'Azure et dans la liste du guide
   OpenAI. Il fallait une forme où le doublon est impossible, d'où l'objet.
2. **Si le mode strict garantit déjà tout, pourquoi les contrôles ?** Parce que le code ne s'y fie
   pas : un autre fournisseur, ou le replay, rend ce qu'il veut. Les contrôles 2 à 5 refusent un
   doublon, une réponse hors liste, un item inventé, un item oublié (`classification.py:175-185`,
   `llm_client.py:440`).
3. **Pourquoi refuser une clé en double, puisque le JSON l'accepte ?** Parce que Pydantic garderait
   la dernière valeur sans rien dire. Le doublon serait réparé en silence, et on ne saurait pas que
   le modèle a hésité.
4. **Pourquoi avoir changé d'avis sur l'item oublié ?** Le 15/10, la sortie était une liste, et un
   petit modèle en oubliait un sur 60 : un échec pour chaque oubli aurait fait tomber la demande.
   Avec une propriété obligatoire par item, l'oubli n'est plus possible en mode strict. L'accepter
   en silence ne protégerait plus que les cas anormaux, où il vaut mieux échouer fermé.
5. **Et si la liste des sujets grandit ?** Chaque item porte toute la liste fermée : 50 items et
   8 sujets font 450 valeurs d'`enum`. À 20 sujets, on dépasserait 1 000, et le test de bornes
   échouerait avant tout appel réel. Il faudrait alors des lots plus petits ou une définition
   partagée (`$defs`), dont le décompte n'est pas vérifié.

## Zones non vérifiées

- **`classify-2` n'a pas encore tourné sur gpt-6-luna.** L'essai 1 de #210 sera rejoué après la
  fusion. La garantie « une propriété obligatoire ne manque jamais » vient de la doc du mode
  strict, pas d'une mesure.
- **La limite de 1 000 valeurs d'`enum`** vient de la spec (lecture d'OpenAI du 15/10), non relue
  aujourd'hui ; la page Azure lue aujourd'hui ne donne aucune limite d'`enum`. Le test de bornes
  compte 50 × 9 valeurs, en supposant qu'un même sous-schéma répété est compté à chaque fois :
  c'est le pire cas.
- **Le coût en jetons de la nouvelle sortie** (environ 10 jetons par item, estimé) n'est pas
  mesuré ; `CLASSIFICATION_MAX_COMPLETION_TOKENS` reste à 2 048, une large marge.

## Ce qui reste

- Rejouer l'essai 1 de #210 sur la base du 26/10, puis les essais 2 et 3, et les consigner dans
  `docs/fiches-veille.md`.
- Le sujet secondaire par item : décision ouverte, après les essais.
- Le rejeu de l'item piégé sur gpt-6-luna (#210), qui attend l'accord de Sabine.

## Sources

| Source | Consultée | Ce qu'elle établit |
|---|---|---|
| [Azure, structured outputs](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs) (page du 2026-08-24) | 2026-10-26 | 100 propriétés d'objet par schéma, 5 niveaux ; `uniqueItems` refusé ; la sortie suit l'ordre du schéma |
| [OpenAI, prompt generation (méta-schéma des sorties structurées)](https://developers.openai.com/api/docs/guides/prompt-generation), via Context7 | 2026-10-26 | `uniqueItems` n'est pas pris en charge en mode strict |
