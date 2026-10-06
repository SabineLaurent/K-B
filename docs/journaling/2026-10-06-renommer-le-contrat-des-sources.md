# Renommer le contrat des sources en `source_contract.py`

- **Date** : 2026-10-06
- **Branche** : `refactor/rename-source-contract`
- **Issue** : #109
- **Fichiers principaux** : `src/k_b/source_contract.py` (ex-`source.py`),
  `tests/test_source_contract.py` (ex-`test_source.py`), `tests/test_module_dependencies.py`
- **Série** : suite de [Un module par source](2026-10-06-un-module-par-source.md) (#100), dont la
  revue de code a relevé le problème de nom.

## Le pourquoi

Le package contenait deux noms à une lettre d'écart, pour deux rôles opposés :

- `k_b.source` : le **contrat** que toute source respecte (`Source`, `SourceReader`, `SourceKind`),
  un module générique ;
- `k_b.sources` : les **sources concrètes** (arXiv, GitHub, CISA KEV…), qui dépendent de ce contrat.

Un import mal tapé passait d'un rôle à l'autre sans que le nom alerte le lecteur. Le plan ETL
l'appelait déjà « le contrat » (`docs/2026-10-06-plan-etl.md:87`). Le nom `source_contract` a été
choisi par Sabine le 06/10. Le renommer avant #101, qui modifie `raw_items.py`, un des modules qui
importe le contrat, donne une base stable à #101.

## Le comment

### 1. Un renommage par `git mv`, sans toucher au contenu

`src/k_b/source_contract.py:1-5` garde sa docstring telle quelle :

```python
"""What a source gives the generic steps: how to collect it (E), how to read its raw files (T).

The sources themselves are declared once, in SOURCE_KINDS, that only cli.py imports in the
package.
"""
```

`git mv` enregistre le déplacement, et git le reconnaît comme renommage à 100 %
(`git diff -M main --summary` : `rename src/k_b/{source.py => source_contract.py} (100%)`).
L'historique du fichier reste donc lisible avec `git log --follow`.

### 2. Les 20 imports suivent

Chaque `from k_b.source import …` devient `from k_b.source_contract import …`. On en compte 10
dans `src` et 10 dans `tests`. Exemple, `src/k_b/sources/arxiv.py:17` :

```python
from k_b.source_contract import SourceReader
```

Seul le chemin du module change : les noms importés (`SourceReader`, `SourceKind`,
`list_sources`…) restent les mêmes. Le code appelant ne change donc pas.

### 3. Le test de dépendances connaît le nouveau nom

`tests/test_module_dependencies.py:15` liste le module parmi les génériques :

```python
GENERIC_MODULES = {
    "items",
    "source_contract",
```

Cette liste est vérifiée par `test_every_module_is_in_exactly_one_list`
(`tests/test_module_dependencies.py:103-108`). Le test compare les modules réellement présents
dans le package à l'union des trois listes. Si la liste n'avait pas été mise à jour, il aurait
échoué : `source_contract` présent mais classé nulle part, `source` classé mais absent. Ce test
empêche donc d'oublier ce renommage.

## Choix faits et options écartées

- **Le nom `source_contract`** : choisi par Sabine dans l'issue. Il dit le rôle (« contrat ») et
  garde le préfixe `source`. Le préfixe range le module à côté de `source_kinds` et de `sources`
  dans un listing. Il n'y avait pas d'autre option à arbitrer ici.
- **Pas d'alias `k_b/source.py` qui réexporterait l'ancien nom** : il remettrait en circulation le
  nom ambigu que l'on retire. Aucun code extérieur au dépôt n'importe K-B, donc rien n'oblige à
  garder une compatibilité.
- **Le fichier de test est renommé aussi** : `tests/test_source_contract.py` suit le nom du module
  qu'il teste (consigne de l'issue). Sa seule différence est la ligne d'import, d'où les 92 % de
  similarité vus par git.
- **Les docs datées ne sont pas réécrites** (`docs/2026-10-06-plan-etl.md`, la note de
  `docs/journaling/` du 06/10) : elles disent ce qui était vrai à leur date (consigne de l'issue).
  Aucune doc non datée ni le README ne citait le module (`grep` vide, voir la preuve).

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `git diff -M main --summary` : `rename src/k_b/{source.py => source_contract.py} (100%)` | Le contenu du contrat est inchangé |
| `grep -rnE "k_b\.source\b\|k_b/source\.py" src tests` : aucune sortie | Plus aucun import de l'ancien nom |
| `grep -rnE "(^\|[^_])source\.py\|k_b\.source\b" README.md docs --exclude-dir=journaling --exclude-dir=ADR \| grep -v "^docs/20"` : aucune sortie | Aucune doc non datée ne cite l'ancien nom |
| `uv run pytest` : 307 passed, dont `test_every_module_is_in_exactly_one_list` | Le comportement est inchangé et `GENERIC_MODULES` est à jour |
| `uv run ruff check`, `ruff format --check`, `mypy --strict` : verts | L'ordre des imports et le typage tiennent |

## Ce que tu dois pouvoir défendre

1. **Pourquoi renommer un module qui marchait ?** Deux noms à une lettre d'écart (`source`,
   `sources`) désignaient deux rôles opposés : le contrat générique et ses implémentations. Le
   nom guide le lecteur vers le bon rôle. Ce renommage ne change aucun comportement.
2. **Comment sais-tu qu'aucun comportement n'a changé ?** Le module est renommé à 100 % sans
   modification. Seules les lignes d'import changent, et les 307 tests passent.
3. **Qu'arriverait-il si on oubliait un import ?** Un `ModuleNotFoundError` au chargement. Les
   tests, mypy et la CI le verraient tout de suite. Le `grep` de l'issue le montre aussi sans rien
   exécuter.
4. **Pourquoi pas un alias pour la compatibilité ?** Personne en dehors du dépôt n'importe K-B, et
   un alias garderait le nom ambigu que l'on veut retirer.
5. **Le classement des modules en générique / source / composition reste-t-il juste ?** Oui :
   `test_every_module_is_in_exactly_one_list` (`tests/test_module_dependencies.py:103-108`)
   échouerait si `source_contract` n'était classé nulle part.

## Zones non vérifiées

Aucune.

## Ce qui reste

Les issues ouvertes #61, #69, #71 et #77 citent encore d'anciens noms de modules. Elles sont hors
périmètre de cette PR (ordre de mission) et seront corrigées à part.
