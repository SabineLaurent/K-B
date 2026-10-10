# Sortir le code de `database/__init__.py`

- **Date** : 2026-10-10
- **Branche** : `refactor/database-module`
- **Issue** : #118
- **Fichiers principaux** : `src/k_b/database/connection.py` (nouveau),
  `src/k_b/database/__init__.py`, `tests/test_module_dependencies.py`

## Le pourquoi

Un `__init__.py` se lit comme la porte d'un paquet : on y cherche ce que le paquet contient, pas
le code lui-même. Celui de `k_b.database` contenait tout le code de la base (ouvrir une
connexion, créer la base). Sabine a demandé de le placer dans un module nommé, sans changer aucun
comportement. Le schéma (`schema.sql`, `seed_sources.sql`) n'est pas touché : sa réécriture est
l'issue suivante (#119).

## Le comment

### 1. Un déplacement à l'identique

`connection.py` reprend le contenu de l'ancien `__init__.py` ligne pour ligne : constantes,
`connect_database`, `create_database`, commentaires.

```python
DATABASE_FILE_NAME = "k-b.sqlite"
DATABASE_SCRIPTS = files("k_b.database")
```
(`src/k_b/database/connection.py:7-8`)

`files("k_b.database")` désigne le **paquet**, pas le module qui l'appelle. Les deux scripts SQL
restent dans le dossier `k_b/database/` : la constante pointe toujours au bon endroit, même
déplacée dans `connection.py`.

### 2. Un `__init__.py` réduit à sa docstring

```python
"""The items database: SQL scripts, and connection.py, which creates and opens it."""
```
(`src/k_b/database/__init__.py:1`)

Le fichier reste : il fait de `k_b.database` un paquet régulier, celui que `files("k_b.database")`
lit. Il ne réexporte rien : le critère de fin de #118 exige que plus aucun code n'importe
`connect_database` ni `create_database` depuis `k_b.database`.

### 3. Les imports suivent

`cli.py:12`, `import_items.py:16`, `tests/test_database.py:5-6` et `tests/test_import_items.py:9`
importent désormais depuis `k_b.database.connection`. Le test d'échec de création remplace la
constante à son nouvel emplacement :

```python
monkeypatch.setattr(k_b.database.connection, "DATABASE_SCRIPTS", scripts_dir)
```
(`tests/test_database.py:52`)

`create_database` lit `DATABASE_SCRIPTS` dans son propre module : c'est là qu'il faut la
remplacer. Laissé sur `k_b.database`, `setattr` aurait levé `AttributeError` (`raising=True` par
défaut), puisque l'attribut n'y existe plus.

### 4. Le garde-fou des dépendances lit tous les fichiers du paquet

`tests/test_module_dependencies.py` vérifie qu'un module générique n'importe ni les sources ni la
composition (`cli`). Pour un paquet, il ne lisait que `__init__.py`. Après le déplacement, il
n'aurait plus rien vérifié pour `database`, et sans échouer. Il lit maintenant chaque fichier
`.py` du paquet :

```python
            module_paths = sorted((PACKAGE_DIR / module).glob("*.py"))
            assert module_paths, f"no Python file in {PACKAGE_DIR / module}"
            for module_path in module_paths:
                modules.append((module_path, f"k_b.{module}"))
```
(`tests/test_module_dependencies.py:119-122`)

- `f"k_b.{module}"` : une importation relative écrite dans `connection.py` part du paquet
  `k_b.database`, comme une importation écrite dans `__init__.py`. Le même paquet de départ vaut
  donc pour tous les fichiers.
- `assert module_paths` : l'ancien code échouait si `__init__.py` manquait (`read_text` lève une
  erreur). `glob` sur un dossier vide ou absent ne renvoie rien, sans erreur. L'`assert` rétablit
  l'échec : un module listé sans fichier fait échouer le test au lieu de le laisser passer à vide.
  Ajouté après `/code-review`.
- `sorted` : un ordre stable, donc les mêmes messages d'une exécution à l'autre.

## Choix faits et options écartées

| Choix | Retenu | Écarté, et pourquoi |
|---|---|---|
| Nom du module | `connection.py`, suggéré par l'issue ; `create_database` passe par `connect_database` | `database.py` : `k_b.database.database`, redondant. `sqlite.py` : dit la technique, pas le rôle. `lifecycle.py` : vague. Deux modules (`connection.py`, `creation.py`) : un fichier par fonction, plus de structure que l'issue n'en demande |
| Réexport dans `__init__.py` | Aucun | Un réexport garderait `from k_b.database import …` valide, ce que le critère de fin interdit |
| Garde-fou | Étendu dans cette PR (accord de Sabine) | Le laisser : il deviendrait aveugle pour `database` sans qu'aucun test n'échoue |
| Sous-paquets dans le garde-fou (`rglob`) | Non | Aucun sous-paquet n'existe ; l'ancien code avait la même limite ; ce serait du code pour plus tard |
| `tests/test_schema.py:6` (sa propre constante `files("k_b.database")`) | Non touché | Antérieur à la PR, hors périmètre ; à reprendre avec #119, qui déplacera les scripts |

Le nom `connection` cache la création de la base (réserve des deux relecteurs). Sabine le garde
pour y revenir avec la réécriture du schéma (#119).

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `grep -c "def " src/k_b/database/__init__.py` → `0` | Plus de code dans `__init__.py` (critère de fin) |
| `grep -rn "from k_b.database import" src tests` → aucune ligne | Plus aucun import depuis l'ancien emplacement (critère de fin) |
| `uv run pytest` → `316 passed` ; `ruff check`, `ruff format --check`, `mypy --strict` verts | Aucun comportement changé, contrôles du dépôt verts |
| Casse 1 : ancien import remis dans `cli.py` → `1 error during collection` | Les tests détectent un import vers l'ancien emplacement |
| Casse 2 : `import k_b.cli` ajouté à `connection.py` → `assert {'cli'} == set()` | Le garde-fou voit maintenant `connection.py` |
| Casse 3 : `database/` vidé de ses `.py` → `AssertionError: no Python file in …/database` | L'`assert` fait échouer un paquet sans fichier |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas réexporter les fonctions depuis `__init__.py`, pour ne rien casser ?**
   Le critère de l'issue l'interdit, et un seul chemin d'import évite deux façons d'écrire la
   même chose. Aucun code du dépôt n'utilise l'ancien chemin ; une branche ouverte qui l'utilise
   cassera, ce que dit la PR.
2. **`files("k_b.database")` marche-t-il encore depuis `connection.py` ?** Oui : il vise le
   paquet, et les `.sql` n'ont pas bougé (`connection.py:8`). Les tests de création le prouvent.
3. **Pourquoi avoir touché le test des dépendances, absent de l'issue ?** Sans ce changement, il
   ne vérifiait plus rien pour `database` tout en restant vert (`test_module_dependencies.py:119`).
   Sabine a validé l'ajout. La casse 2 le prouve.
4. **Pourquoi `assert` dans une fonction utilitaire de test ?** Pour échouer fermé : un paquet
   listé sans fichier doit faire échouer le test, pas le laisser passer à vide (casse 3).
5. **Le nom `connection` est-il juste ?** En partie : il dit bien `connect_database`, moins bien
   `create_database`. Le choix est assumé et sera revu avec la réécriture du schéma.

## Zones non vérifiées

- Le paquet construit par `uv_build` (wheel) n'a pas été construit ni inspecté. Le relecteur du
  plan a vérifié que `pyproject.toml` ne déclare ni include ni exclude, et les `.sql` n'ont pas
  bougé : rien n'indique un changement, mais ce n'est pas observé.
- L'outil installé (`uv tool install --editable`) n'a pas été relancé ; en mode éditable, il lit
  les sources directement.

## Ce qui reste

- Le nom `connection` et le découpage création / connexion : à revoir avec #119.
- `tests/test_schema.py:6` redéfinit `DATABASE_SCRIPTS` : à reprendre avec #119.
- Le garde-fou ne descend pas dans les sous-paquets : à étendre le jour où un sous-paquet
  apparaît (par exemple des migrations en Python).
