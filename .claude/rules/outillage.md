# Outillage — ce que ruff vérifie à la place du texte

Pendant de `code.md` : ce qu'un outil bloque n'a pas besoin d'être répété en consigne. À ajouter à
`extend-select` dans le `pyproject.toml` de chaque dépôt Python, **d'office** (décidé par Sabine le
2026-10-05). Préfixes vérifiés dans la documentation ruff (Context7, 2026-09-30).

| Préfixe | Famille | Principe de `code.md` |
|---|---|---|
| `S` | flake8-bandit | Sécurité : `eval`, `pickle`, `shell=True`, secrets en dur |
| `N` | pep8-naming | Lisibilité : nommage PEP 8 |
| `SIM` | flake8-simplify | Simplicité : constructions inutilement compliquées |
| `C90` | mccabe | Une fonction fait une chose : complexité > 10 (valeur par défaut) |

```toml
[tool.ruff.lint]
extend-select = ["I", "B", "UP", "S", "N", "SIM", "C90"]  # I, B, UP : déjà dans T-O

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101"]  # assert est l'outil des tests
```

La CI lance aussi `uv run ruff check`, `uv run ruff format --check` et `uv run mypy --strict`.

Activation : rapporter les constats de ruff et de mypy avant de les corriger (15 min de mesure),
Sabine décide de ce qui se corrige tout de suite.
