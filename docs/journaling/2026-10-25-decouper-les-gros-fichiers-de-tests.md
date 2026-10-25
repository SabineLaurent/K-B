# Découper les deux plus gros fichiers de tests

- **Date** : 2026-10-25
- **Branche** : `refactor/cosmetic-b`
- **Issue** : aucune ; point 5 de la revue d'organisation du code faite par certif le 2026-10-25
- **Fichiers principaux** : `tests/commands/`, `tests/etl/test_load_*.py`, `tests/etl/load_helpers.py`, `tests/etl/conftest.py`

## Le pourquoi

`tests/test_cli.py` (2 030 lignes) et `tests/etl/test_load.py` (2 042 lignes) fonctionnaient, mais étaient difficiles à
parcourir. Un fichier de tests se lit comme une table des matières, au même titre qu'un module (`code.md`,
« Lisibilité »).

## Le comment

### 1. Un fichier par commande

`tests/commands/` suit le même découpage que `src/k_b/commands/`. On y trouve un fichier par commande (`collect`,
`create-db`, `import`, `write-tops`, `digest`), plus le journal de fonctionnement, les codes de sortie et SIGTERM. Les
fixtures `autouse` (aucun réglage du terminal hérité) passent dans `tests/commands/conftest.py` : elles s'appliquent,
comme avant, à tous ces tests.

### 2. Les tests du chargement, par thème

Les tests du chargement suivent le modèle de `test_load_clips.py` et `test_load_zotero.py`, qui existaient déjà :
`test_load_items`, `test_load_seen_again`, `test_load_rejections`, `test_load_commit`, `test_load_registry`,
`test_load_withdrawals`, `test_load_tldr` et `test_load_trends`. Les fonctions qu'ils partagent avec `test_raw_purge.py`
vont dans `load_helpers.py` :

```python
from load_helpers import run_import
```
(`tests/etl/test_raw_purge.py:8`, qui importait avant `from test_load import`.)

### 3. La fixture `data_dir` dans un `conftest.py`

Importer une fixture d'un autre module ne tient pas : `ruff` voit le nom comme inutilisé (il n'apparaît qu'en paramètre)
et le retire. La fixture passe donc dans `tests/etl/conftest.py`. Un fichier qui a besoin d'un autre dossier de données
définit le sien, comme `test_load_zotero.py`, et sa définition locale l'emporte.

## Choix faits et options écartées

| Choix | Retenu parce que | Écarté |
|---|---|---|
| Découpage par un script (`ast`), sans réécrire un test | aucune définition ne peut changer en route | le copier-coller à la main |
| `tests/commands/` | suit `src/k_b/commands/` | `tests/test_cli_<commande>.py` à la racine |
| `data_dir` dans `conftest.py` | `ruff` ne retire pas une fixture de `conftest` | l'importer avec `# noqa` dans chaque fichier |

## Preuve

| Test ou sortie | Ce que ça démontre |
|---|---|
| Arbre syntaxique (`ast.dump`) de chaque définition : 122 sur 122 pour `test_cli.py`, 131 sur 131 pour `test_load.py`, aucune en trop | aucun test ni aucune aide n'a changé |
| `pytest --co` : 104 tests avant et après pour les commandes ; 130 avant et après pour le chargement (avec `test_load_clips`, `test_load_zotero` et `test_raw_purge`) | aucun test perdu |
| `uv run pytest` : 2 466 tests verts, comme sur `main` | la suite entière tourne |
| `ruff check`, `ruff format --check`, `mypy --strict` verts | imports propres |

## Ce que tu dois pouvoir défendre

1. **Comment être sûre qu'aucun test n'a changé ?** Chaque définition a le même arbre syntaxique qu'avant, et le nombre
   de tests collectés est identique.
2. **Pourquoi un `conftest.py` pour `data_dir` ?** C'est le mécanisme de pytest pour partager une fixture, et `ruff` ne
   le casse pas.

## Zones non vérifiées

Aucune : le découpage ne touche pas `src/`. Pas de `/code-review` sur cette PR : la preuve par l'arbre syntaxique est plus
forte qu'une relecture pour un déplacement pur.

## Ce qui reste

D'autres fichiers de tests restent longs, sans avoir été visés par la revue : `tests/test_schema.py` (1 254 lignes),
`tests/ai_api/test_digests.py` (1 111), puis quatre fichiers autour de 900 lignes.
