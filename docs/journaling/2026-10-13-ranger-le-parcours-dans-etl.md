# Ranger le parcours dans `etl/` et nommer ses modules d'après E, T et L

- Date : 2026-10-13
- Branche : `refactor/etl-package`
- Issue : #107
- Fichiers principaux : `src/k_b/etl/` (`extract.py`, `transform.py`, `normalize.py`, `load.py`,
  `sources/`), `src/k_b/core/config.py`, `tests/test_module_dependencies.py`,
  `.claude/rules/conventions.md` (règle 5)

Suite de [2026-10-06-ranger-les-conversions.md](2026-10-06-ranger-les-conversions.md) (décision du
2026-10-06 : renommer après l'import incrémental).

## 1. Le pourquoi

La racine du paquet doit dire ce qui se trouve où, d'un coup d'œil. Elle ne montre plus que les
parties du dépôt : `cli.py` (présentation), `items.py` et `core/` (le vocabulaire commun),
`database/` (la base), `etl/` (le parcours). Dans `etl/`, chaque étape du parcours porte le nom de
sa lettre : le parcours se lit dans l'arborescence, sans ouvrir les fichiers. Aucun comportement ne
change. Seuls les noms des huit loggers suivent le chemin du module (`k_b.collect` devient
`k_b.etl.extract`), parce qu'ils sont tirés de `__name__`.

## 2. Le comment

### Quatre noms pour quatre étapes

| Avant | Après | Ce que fait le module |
|---|---|---|
| `collect.py` | `etl/extract.py` | lance chaque source, garde son brut tel quel |
| `raw_items.py` | `etl/transform.py` | lit le brut et le convertit en items validés |
| `merge.py` | `etl/normalize.py` | met chaque item sous une forme commune |
| `import_items.py` | `etl/load.py` | écrit les items dans la base |

`normalize.py` est sorti de « transform » parce qu'il ne lit rien et n'écrit rien : il prend un item
et le rend normalisé (`src/k_b/etl/normalize.py:16`) :

```python
def normalize_item(item: Item) -> Item:
    """The same item, with its URL without tracking parameters and its dates in UTC, those of
    its highlights too."""
```

Les noms de fonctions ne changent pas (`collect_all_sources`, `read_raw_items`, `import_items`) :
le déménagement ne touche à aucune logique.

### Le test des dépendances, lu à deux niveaux

`tests/test_module_dependencies.py` lit chaque fichier avec `ast`, sans l'exécuter. Il en tire les
modules de K-B importés, coupés à deux niveaux sous `k_b` (`tests/test_module_dependencies.py:70`) :

```python
        imported |= {
            ".".join(name.split(".")[1:3]) for name in names if name.startswith("k_b.")
        }
```

Ainsi, `from k_b.etl.sources.arxiv import ArxivSource` est lu `etl.sources`, et
`from k_b.core.config import X` est lu `core.config`. Le lecteur ne connaît aucun paquet en
particulier. La règle de la future API pourra interdire `database.writers` sans que le lecteur
change.

Quatre règles, une par test :

- `core/` n'importe rien de K-B (`:193`) ;
- `database/` n'importe que `items` et `core` (`:201`) ;
- un module du parcours n'importe ni `etl.sources` ni la composition (`:217`) ;
- une source n'importe pas la composition (`:227`).

La composition, ce sont les modules qui assemblent le tout : `cli` et `etl.source_kinds`
(`:31`). Un dernier test (`:182`) vérifie que chaque module de `etl/` est dans exactement une
liste : un module ajouté sans être rangé fait échouer le test.

### Comparer par préfixe, et voir un paquet qui contient un module interdit

Deux fonctions comparent un nom importé aux listes (`tests/test_module_dependencies.py:76-86`).
`is_within` dit si un nom est dans un module : `core.config` est dans `core`. `reaches` ajoute le
cas inverse, venu de la revue : un import du paquet `etl` donne accès à `etl.sources`.

```python
def reaches(name: str, modules: set[str]) -> bool:
    return is_within(name, modules) or any(
        module.startswith(f"{name}.") for module in modules
    )
```

Sans `reaches`, un module du parcours pouvait écrire `from k_b import etl`, puis appeler
`etl.sources.arxiv`, sans que le test le voie. Avant le déplacement, `from k_b import sources`
était vu.

### Les tests en miroir

`tests/etl/` reflète `src/k_b/etl/`. Trois corrections ont suivi le déplacement :

- **Chemins des fixtures :** les huit chemins vers `tests/fixtures/` prennent un `.parent` de plus.
- **Imports entre tests :** sur les six, cinq changent ; `from test_items` reste juste.
- **`test_cli.py` :** il importe ses aides par `from etl.test_extract import …`
  (`tests/test_cli.py:11`). `tests/` est sur le chemin d'import (par `conftest.py`), et `etl` y est
  un paquet sans `__init__.py`.

## 3. Choix faits et options écartées

- **Préfixe `etl.` dans `test_cli.py`.**
  - Retenu : `uv run pytest tests/test_cli.py` passe aussi lancé seul. Un `from test_extract` nu ne
    marche que si pytest a déjà importé un fichier de `tests/etl/`.
  - Écarté : `pythonpath` dans `pyproject.toml`. On ne modifie pas ce fichier sans demande.
  - Écarté : déplacer les aides dans `conftest.py`. Cela change le code des tests.
  - Contrepartie : `test_transform.py` est chargé deux fois, sous deux noms. Ses tests ne tournent
    pas deux fois : le compte est identique, fichier par fichier.
- **Lecteur générique à deux niveaux**, plutôt qu'un cas particulier pour `etl` (relecture de
  l'architecte). Aucune règle de plus.
- **`items.py` garde sa règle d'aujourd'hui** (ni sources ni composition). Une règle plus stricte
  (« rien de K-B sauf `core` ») a été écartée dans le plan : la règle 5 et #133 en décideront.
- **La règle de `etl/` interdit aussi `etl.source_kinds`.** C'est plus strict que le critère, mais
  égal à la règle d'avant.
- **`tests/core/` n'est pas créé** : il n'existe aucun test de `config.py` (accord de Sabine).

## 4. Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| Test des dépendances lancé sur le code de `main` : 5 échecs, dont la liste des modules | le test est écrit d'abord et voit l'arborescence d'avant |
| `uv run pytest` : 923 passent (907 sur `main` ; ce fichier passe de 16 à 32 tests) | rien n'est cassé |
| Compte des tests fichier par fichier, `main` → branche, anciens noms ramenés : seul ce fichier diffère | aucun test perdu en route |
| Import interdit ajouté à la main dans `core/config.py` : `test_core_imports_nothing_of_k_b` échoue sur `{'etl.extract'}` | la règle de `core/` mord |
| `from k_b import etl` ajouté à la main dans `etl/load.py` : la règle du parcours échoue sur `{'etl'}` | `reaches` voit le paquet |
| `diff` de `kb collect --help` et `kb import --help` avec `main` : identiques | les commandes ne changent pas |
| Les trois greps du critère ne renvoient rien ; `ruff`, `mypy --strict` verts | aucun ancien chemin ne reste |

## 5. Ce que tu dois pouvoir défendre

- **Pourquoi un test plutôt qu'une consigne écrite ?** Une consigne se lit et s'oublie, un test
  échoue. Un import qui remonte le courant casse la CI. Voir `tests/test_module_dependencies.py:217`.
- **Le test exécute-t-il le code qu'il lit ?** Non : `ast.parse` lit le texte. Un import dynamique
  (`importlib.import_module`) n'est pas vu ; il n'y en a aucun dans `k_b` (docstring du lecteur).
- **Pourquoi `normalize` n'est-il pas dans `transform` ?** Transformer, c'est lire le brut et le
  convertir. Normaliser ne lit rien : il rend un item sous une forme commune.
  Voir `src/k_b/etl/normalize.py:1-4`.
- **Qu'est-ce qui change pour l'utilisateur ?** Les commandes, non. Le nom des huit loggers dans
  les lignes de journal, oui.

## 6. Zones non vérifiées

- Aucun outil hors du dépôt ne filtre les journaux par nom de logger, à notre connaissance. Ce n'est
  pas vérifié.
- Des fichiers `__pycache__` ont été emportés par les `git mv` de dossiers ; ils sont ignorés par
  git, et la CI part d'un dépôt propre.

## 7. Ce qui reste

- **Ce que les noms ne tiennent pas encore** (sans correction ici) :
  - `etl/transform.py` ne normalise pas : la normalisation est appelée par `etl/load.py`
    (`src/k_b/etl/load.py:410`) ;
  - le dédoublonnage est dans le SQL (`ON CONFLICT … DO UPDATE` de `etl/load.py`) ;
  - un second parcours de lecture vit dans `etl/sources/gh_archive.py` (`read_trend_files`),
    appelé par `cli.py` (`src/k_b/cli.py:122`).
- **Règles à ajouter au test des dépendances avec l'issue « déplacer le SQL » (#135)** :
  - une source n'importe pas `database` ;
  - ce que `cli` et `etl.source_kinds` peuvent importer.
- **`tests/core/`** attend les tests de `core/config.py`, à écrire plus tard (choix de Sabine).
- **La règle de l'API** (`database`, `items`, `core`, jamais `etl` ni `database.writers`)
  s'ajoutera au test avec le paquet d'API.
