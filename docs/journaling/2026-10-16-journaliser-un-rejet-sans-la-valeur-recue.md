# Journaliser un rejet de l'import sans la valeur reçue

- **Date** : 2026-10-16
- **Branche** : `fix/reject-without-received-value`
- **Issue** : #212
- **Fichiers principaux** : `src/k_b/core/quoting.py`, `src/k_b/etl/transform.py`, `src/k_b/items.py`,
  `src/k_b/etl/sources/tldr.py`, `src/k_b/etl/sources/zotero.py`, `.claude/rules/poc.md` ;
  tests : `tests/test_quoting.py`, `tests/test_items.py`, `tests/etl/test_transform.py`,
  `tests/etl/sources/test_tldr.py`, `tests/etl/sources/test_zotero.py`
- **Note précédente de la série** : [Rejeter l'item que la base refuse](2026-10-16-rejeter-l-item-que-la-base-refuse.md)
  (#136, le même journal d'import, à l'écriture)

## Le pourquoi

À l'import (`kb import`), chaque entrée d'un fichier brut devient un item, un modèle Pydantic. Si
l'item refuse l'entrée, celle-ci devient un **rejet** : son motif part dans le journal de
fonctionnement (`kb.log`, par `logger.warning`) et dans le journal d'import (`import-log.jsonl`,
par `Rejection.reason`). Jusqu'ici, ce motif était le texte complet de la `ValidationError`. Or ce
texte **recopie la valeur reçue**, après `input_value=` : un fragment de résumé ou de corps, et
pour une erreur qui porte sur l'item entier, tous ses champs, auteurs compris.

Trois règles l'interdisent :
- la règle 3 de `conventions.md` : un auteur n'est jamais cité, seulement sa position et sa mesure ;
- la règle 5 de `poc.md` : un journal ne contient ni le texte d'un item ni un auteur ;
- le RGPD, par la **minimisation** : on ne garde que les données qui servent. Un auteur est une
  donnée personnelle, et un journal n'a pas besoin de son nom pour dire ce qui a été refusé.

L'enjeu est daté : le dépôt devient public le 25/10, et au 08/11 les journaux partent vers un
service en ligne (Log Analytics sur Azure).

## Le comment

### 1. Ce que `input_value=` recopie

Pydantic écrit, pour chaque erreur, la valeur reçue, tronquée au milieu. Sondé sur pydantic
2.13.5 : il garde environ 25 caractères au début et 25 à la fin, guillemets compris.

```
input_value='AAAAAAAAAAAAAAAAAAAABBBB...BBBCCCCCCCCCCCCCCCCCCCC', input_type=str]
```

Deux conséquences, vues pendant ce travail :
- la troncature ne protège pas : le début d'un résumé, ou un auteur court, passe en entier ;
- une erreur de `model_validator` (une règle qui porte sur l'item entier) reçoit **le
  dictionnaire de tous les arguments** : `input_value={'source_code': 'arxiv', …}`.

C'était le cas du test du titre trop long d'arXiv, qui passait sans le voir.

C'est aussi pourquoi les tests posent leur repère **au début** du texte : un repère placé au
milieu est coupé par pydantic, et le test passerait sans rien prouver.

### 2. `without_values` : reconstruire l'erreur sans valeur

`src/k_b/core/quoting.py:24-36` :

```python
    for detail in error.errors():
        line_error: InitErrorDetails = {
            "type": detail["type"],
            "loc": detail["loc"],
            "input": None,
        }
        ...
    return ValidationError.from_exception_data(
        error.title, line_errors, hide_input=True
    )
```

La fonction relit chaque erreur et en garde le type (`value_error`), la place (`loc`, par exemple
`summary`) et le contexte (`ctx`, d'où vient le message). Elle remplace la valeur par `None`, puis
reconstruit une `ValidationError`. Le paramètre `hide_input=True` de `from_exception_data` retire
la valeur et son type du texte (documentation de pydantic-core). Le message de K-B reste, avec sa
mesure :

```
summary
  Value error, text with a NUL or a lone surrogate: 22 characters [type=value_error]
```

Deux conditions, écrites dans la docstring (`quoting.py:20-23`), font tenir cette garantie :
- la place vient du modèle, jamais de l'entrée. Aucun champ n'est un dictionnaire, et les items
  sont construits avec des noms d'arguments fixes ;
- le message d'un validateur ne cite jamais la valeur : il donne une mesure, ou passe par
  `quote_value`.

### 3. Pourquoi la fonction a déménagé dans `core/`

`without_values` existait déjà, dans `etl/sources/zotero.py`. Le critère de l'issue demandait de
la réutiliser sans la recopier. Mais `transform` est un module du pipeline, et un module du
pipeline n'importe pas une source : `tests/test_module_dependencies.py` l'interdit (règle 5 de
`conventions.md`, les dépendances vont dans un seul sens).

La fonction passe donc dans `core/`, le vocabulaire commun que toute couche peut importer. Elle va
dans `quoting.py`, dont le thème est déjà « comment une valeur observée est citée dans un journal
ou une erreur ». `transform` l'appelle pour toutes les sources (`transform.py:150-156`) :

```python
        except ValidationError as error:
            rejections.append(
                reject(
                    raw_file_path,
                    f"read entry {position}: {type(error).__name__}: "
                    f"{without_values(error)}",
```

### 4. Le point (b) : une page illisible peut-elle citer son contenu ?

Le premier `except` de `read_page` (`transform.py:134-141`) rejette une page entière avec
`{error}`. Le critère demandait de vérifier si ce message peut recopier du contenu.
`test_an_unreadable_page_is_rejected_without_its_text` (`tests/etl/test_transform.py:649`) donne
cinq pages piégées. Ce qui a été observé :

| Erreur | Ce que dit son message |
|---|---|
| `JSONDecodeError` | une position (`line 1 column 28 (char 27)`) |
| `UnicodeDecodeError` | un octet et sa position (`byte 0xff in position 8`) |
| `ParseError` d'expat (arXiv) | un code et une position (`undefined entity: line 1, column 29`) |
| `csv.Error` | un message fixe (`field larger than field limit (131072)`) |

Un seul cas citait la page : le refus d'`html.parser` dans `tldr.py`. Le message de l'exception
d'origine vient de `_markupbase`. Dans une 3.13 antérieure à 3.13.13, il peut recopier un mot de
la page (`'unknown status keyword %r'`), et `pyproject.toml` admet toute 3.13. En 3.13.13, ce
chemin n'est plus appelé.

### 5. Défense en profondeur : `hide_input_in_errors`

`without_values` reconstruit l'erreur. Une erreur d'un type que pydantic ne connaît pas (une
`PydanticCustomError`) lui ferait lever `KeyError` dans le `except` de `read_page`. Ce `KeyError`
porterait l'erreur d'origine dans son `__context__`. Il remonterait jusqu'à `cli.py:194`
(`logger.exception`), et la trace imprimerait l'`input_value` dans `kb.log` (constat CR1 de la
revue). Ce n'est pas joignable aujourd'hui, mais Sabine a choisi de fermer ce chemin à la source.

`src/k_b/items.py:302-304` :

```python
    model_config = ConfigDict(
        frozen=True, extra="forbid", strict=True, hide_input_in_errors=True
    )
```

Avec ce réglage, l'erreur ne cite plus la valeur dès sa création, quel que soit le chemin qu'elle
prend ensuite : rejet, trace ou `str()`. Il porte sur les quatre modèles qui valident les données
d'une source : `Item` et `Highlight` (`items.py`), `ZoteroDocument` et `ZoteroHighlight`
(`zotero.py`). Pour un modèle imbriqué, c'est le réglage du modèle extérieur qui décide.
`without_values` reste, comme l'exige le critère (a) : deux contrôles valent mieux qu'un
(`code.md`, « Défense en profondeur »).

### 6. `from None` plutôt que `from error`

`tldr.py:148-150` :

```python
    except ParserRejectedMarkup:
        # Its message may quote the page (#212).
        raise ValueError("page rejected by html.parser") from None
```

Retirer le message du texte ne suffisait pas. Avec `from error`, l'exception d'origine reste
attachée comme **cause** (`__cause__`), et toute trace (`logger.exception`) l'imprime en entier.

`from None` met `__cause__` à `None` et `__suppress_context__` à `True` : la trace n'affiche plus
l'exception d'origine. Celle-ci reste dans `__context__` pour le débogage, mais elle n'est pas
imprimée (documentation Python, « Exception context »). Le test vérifie
`refusal.value.__cause__ is None`. `zotero.py` fait déjà de même.

## Choix faits et options écartées

| Décision | Retenu | Écarté, et pourquoi |
|---|---|---|
| La fonction qui retire la valeur | `without_values` | `describe_validation_error` est propre à GH Archive : elle connaît ses champs (`KNOWN_FIELDS`, `rows`), ne garde que la première erreur et cite la valeur d'une date ou d'un nombre. Une copie est interdite par le critère (a). |
| Son emplacement | `core/quoting.py` | `etl/source_contract.py` est permis, mais son thème est le contrat entre une source et le pipeline. Rester dans `zotero.py` est interdit par les dépendances. |
| L'appel de `zotero.convert_document` | gardé | Le retirer serait plus DRY, mais hors de la demande. Deux appels donnent le même résultat. Décision du plan validé par Sabine, confirmée au tri des revues (CR4). |
| Une `PydanticCustomError` ferait lever `KeyError` à `without_values` (CR1) | `hide_input_in_errors=True` sur les quatre modèles, en plus de `without_values` (décision de Sabine du 16/10, recommandée par time-knight) | Rattraper le `KeyError` dans `read_page` : plus de code, et ne protège que ce chemin. Ne rien faire : la trace d'un `KeyError` imprimerait la valeur. |
| Formater `error.errors(include_input=False)` sur une ligne | non | C'est une nouvelle fonction, contraire au critère (a). Signalé, avec le motif sur plusieurs lignes (CR5, CR6). |
| Le refus de `tldr` | message fixe, `from None` | Le signaler seulement : le dépôt devient public le 25/10, et la correction tient en une ligne (décision de Sabine). |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_summary_with_a_nul_is_rejected_without_its_text` | Le cas (c) du critère. Un `body` collecté de release, préfixé de `RECEIVED_TEXT` et terminé par un NUL, est rejeté : le motif nomme `summary` et `text with a NUL`, sans le repère, ni dans `Rejection.reason` ni dans le journal. Il échouait avant la correction. |
| `test_a_title_too_long_…` : `"input_value" not in` | L'erreur d'un `model_validator`, qui recevait tous les champs, n'en cite plus aucun. Échouait avant. |
| `test_an_unreadable_page_is_rejected_without_its_text` (5 cas) | Point (b) : une page illisible ne cite pas son contenu. Passait avant la correction : c'est une vérification, pas une correction. |
| `test_a_page_the_html_parser_rejects_is_refused_whole` | Le message est fixe et `__cause__ is None`. Échouait avant. |
| `test_an_error_without_values_keeps_its_field_and_type_but_not_its_value` | La fonction seule : champ et type gardés, valeur absente. |
| `test_a_refusal_does_not_quote_the_value_received` (`test_items.py`, `test_zotero.py`, 4 cas) | `Item`, `Highlight`, `ZoteroDocument` et `ZoteroHighlight` ne citent pas la valeur reçue dans `str(error)`. Échouait avant le réglage. |
| `grep -rn -A5 "except ValidationError" src/k_b \| grep -E "\{error\}\|str\(error\)"` | Ne rend plus rien (point (d)). |
| `uv run pytest`, `ruff check`, `ruff format --check`, `mypy --strict` | 1525 tests verts, et les autres contrôles verts. |

## Ce que tu dois pouvoir défendre

1. **« Pydantic tronque déjà la valeur : pourquoi ne pas s'en contenter ? »** La troncature garde
   environ 25 caractères au début et 25 à la fin : un auteur court ou le début d'un résumé passent
   en entier. Pour une erreur qui porte sur l'item entier, ce sont tous les champs
   (`test_transform.py:276`).
2. **« Pourquoi déplacer une fonction au lieu de l'importer ? »** `transform` ne peut pas
   importer une source : un test des dépendances l'interdit (`test_module_dependencies.py`).
   `core/` est importable par toutes les couches.
3. **« Que se passe-t-il si un validateur écrit la valeur dans son message ? »** `without_values`
   garde le message : la valeur passerait. La garantie repose sur une règle du dépôt, écrite dans
   la docstring (`quoting.py:20-23`) : un message donne une mesure, ou passe par `quote_value`.
   Derrière, `hide_input_in_errors` empêche le modèle de citer la valeur reçue (`input_value`) ;
   il n'empêche pas un message de la recopier. La règle 3 tient ce cas.
4. **« Pourquoi `from None` ? Le message est déjà retiré. »** Une trace imprime la cause
   chaînée : `from error` aurait gardé le texte du parseur dans `__cause__`
   (`tldr.py:150`, et le test qui vérifie `__cause__ is None`).
5. **« Le chemin d'une page illisible est-il sûr ? »** Ses messages ne donnent que des positions,
   des octets ou des textes fixes (cinq cas testés). Seul `html.parser` citait la page, et il est
   corrigé.

## Zones non vérifiées

- Le chemin de `tldr.py` n'a pas pu être déclenché avec Python 3.13.13. La fuite dans une 3.13
  plus ancienne vient de la lecture du code de `_markupbase`, pas d'une exécution.
- Les types d'erreur pydantic que seules des entrées non sondées produiraient (par exemple une
  sous-classe de `datetime` en mode strict) ne sont pas couverts par la sonde de la revue de
  sécurité.
- La troncature d'`input_value` à environ 25 caractères de chaque côté est mesurée sur pydantic
  2.13.5, pas lue dans sa documentation.
- `hide_input_in_errors` est testé sur un champ par modèle. Les autres types d'erreur ont été
  sondés par time-knight (`PydanticCustomError`, `ValueError` de validateur, `string_type`,
  `extra_forbidden`, `model_validator`, modèle imbriqué), mais ne sont pas tenus par un test.

## Ce qui reste

- **Le motif sur plusieurs lignes** : les lignes suivantes de `kb.log` ne sont pas horodatées, et
  le motif porte une URL `errors.pydantic.dev` par erreur. Signalé sans issue (CR5, CR6).
- **Le chemin absolu** cité par une `OSError` (sous `KB_DATA_DIR`) : à rappeler pour la mise en
  ligne du 08/11.
- Les `!r` non tronqués de quelques lecteurs (noms de dépôt, réglages) et la docstring périmée
  `cisa_kev.py:75` : hors de la règle 5, signalés.

## Sources

- Pydantic, `ValidationError.from_exception_data` (paramètre `hide_input`) et le réglage
  `hide_input_in_errors` (« Hides the input value and type from error messages ») : https://pydantic.dev/docs/validation/latest/api/pydantic-core/pydantic_core
  et https://pydantic.dev/docs/validation/latest/api/pydantic/config, consultées par Context7 le
  2026-10-16.
- Python, *Built-in Exceptions*, « Exception context » (`__cause__`, `__context__`,
  `__suppress_context__`, `raise … from None`) :
  https://docs.python.org/3.13/library/exceptions.html, relevée par recherche web le 2026-10-16.
- CNIL, « intérêt légitime : collecte par moissonnage » (minimisation) :
  https://www.cnil.fr/fr/focus-interet-legitime-collecte-par-moissonnage, référentiel de
  `conformite.md`, vérifié le 2026-10-04.
- Code de la bibliothèque standard installée (CPython 3.13.13) : `_markupbase.py` et
  `html/parser.py`, lus le 2026-10-16.
