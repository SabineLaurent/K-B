# Un module par source

- **Date** : 2026-10-06
- **Branche** : `refactor/one-module-per-source`
- **Issue** : #100 (plan ETL, étape 4 : `docs/2026-10-06-plan-etl.md`)
- **Fichiers principaux** : `src/k_b/sources/` (nouveau paquet), `src/k_b/source_kinds.py`,
  `tests/sources/`, `tests/test_module_dependencies.py`
- **Série** : suit `2026-10-06-une-seule-liste-des-sources.md` (#99).

## Le pourquoi

Avant cette PR, chaque source avait deux fichiers à plat dans `src/k_b/` : un pour télécharger
(`cisa_kev_source.py`, l'étape E) et un pour lire le brut (`cisa_kev.py`, l'étape T). Ces
fichiers côtoyaient les modules génériques du pipeline (`collect`, `raw_items`, `import_items`…),
sans rien qui les distingue à la lecture de `ls`.

Le plan ETL vise une structure explicite : les étapes génériques d'un côté, les sources de
l'autre, chaque source en un seul module. Pour ajouter ou comprendre une source, on ouvre alors un
seul fichier. Cette PR ne change aucun comportement : elle déplace et regroupe du code.

## Le comment

### Un paquet `k_b.sources`, avec un `__init__.py` vide

`src/k_b/sources/__init__.py` fait 0 ligne. Il fait de `sources` un paquet Python importable
(`from k_b.sources import arxiv`) sans y mettre de code, comme le demande le critère de #100.
Tout ce que les sources partagent entre elles a été déplacé avec elles : `github_api.py`,
`github_dates.py` et `tracked_repositories.py` ne servent qu'aux sources GitHub. Les modules
génériques (`http_download`, `items`, `source`…) restent dans `k_b`.

### Un module = téléchargement (E), puis lecture (T)

Chaque module fusionné ouvre sur une docstring qui reprend les deux anciennes, dans l'ordre du
pipeline (`src/k_b/sources/arxiv.py:1-6`) :

```python
"""The arXiv source: its download (E), then its reader (T).

Download the AI security papers submitted to arXiv, as the API returns them.

Read the papers of a raw arXiv API response (an Atom feed), and convert each one into an item.
"""
```

Après les imports viennent `logger` (`arxiv.py:19`) et toutes les constantes du module, celles du
téléchargement puis celles de la lecture, et enfin `FOLDER_PREFIX` (`:59`). C'est l'usage courant
en Python, dans l'ordre que donne PEP 8 (docstring, imports, puis variables du module) : un
lecteur trouve toute la configuration en tête. Puis les fonctions, dans l'ordre E puis T : la
partie téléchargement (`ArxivSource` en `:62`), la partie lecture (`read_papers` en `:125`), et
enfin le lecteur déclaré (`arxiv.py:231`) :

```python
READER: SourceReader[Paper] = SourceReader(read_papers, convert_paper)
```

`READER` est en dernier parce qu'il référence des fonctions définies plus haut : à l'import,
Python exécute le module de haut en bas. À l'inverse, `ArxivSource.fetch` appelle
`count_papers` (défini plus bas, en `:139`) : ce n'est pas un problème, car le nom n'est cherché
qu'à l'appel de la méthode, quand tout le module est chargé.

Les fonctions, classes et constantes **gardent leur nom** : aucun nom d'un fichier de la paire
n'existait dans l'autre (vérifié par commande avant la fusion). L'import interne
(`from k_b.cisa_kev import read_catalog` dans l'ancien `cisa_kev_source.py`) disparaît, puisque
les deux parties sont désormais dans le même fichier.

### La composition importe les modules de `k_b.sources`

`source_kinds.py` reste le seul endroit où les sources sont déclarées (#99). Seuls ses imports
changent (`src/k_b/source_kinds.py:8`, `:51`) :

```python
from k_b.sources import (
...
    SourceKind(arxiv.FOLDER_PREFIX, (ArxivSource(),), arxiv.READER),
```

Avant, la même ligne devait nommer deux modules : `arxiv_source.FOLDER_PREFIX` et
`arxiv_papers.READER`.

### Le test de dépendances porte sur le paquet

`tests/test_module_dependencies.py` vérifie le sens des dépendances : composition → sources →
générique. La couche des sources n'est plus une liste de quatorze modules, mais le paquet entier
(`SOURCES_PACKAGE = "sources"`, ligne 26). Un import de `k_b.sources.arxiv` est donc vu comme un
import de `sources`.

Le point délicat est l'import relatif. Dans un module de `k_b.sources`, `from .. import cli`
remonte d'un cran, à `k_b`. Le test résout donc chaque import relatif à partir du paquet du
module (`tests/test_module_dependencies.py:54-55`) :

```python
base = ".".join(package_parts[: len(package_parts) - node.level + 1])
origin = f"{base}.{node.module}" if node.module else base
```

Avec `package="k_b.sources"`, `.` (level 1) donne `k_b.sources` et `..` (level 2) donne `k_b`.
Ce cas est testé à la ligne 90 : `("from .. import cli", {"cli"})`. Aucun module de K-B n'utilise
d'import relatif aujourd'hui. Le test le prévoit quand même, parce que sinon un import interdit de
`cli` écrit ainsi passerait inaperçu.

Deux garde-fous viennent de la revue de code :
- **Un import qui remonte au-dessus de `k_b` est refusé.** `from ... import cli` depuis
  `k_b.sources` lève une `ValueError` au lieu d'être ignoré : le test échoue fermé
  (`tests/test_module_dependencies.py:50-53`).
- **Un module générique qui est un paquet est lu avec son propre paquet.** `database/__init__.py`
  est résolu contre `k_b.database`, et non contre `k_b`. C'est le rôle de `list_generic_modules`.

Le test vérifie aussi deux choses :
- les modules de premier niveau sont exactement les génériques, plus `sources`, plus la
  composition (ligne 107). Un module de source oublié à plat le fait donc échouer ;
- la liste des fichiers de `sources/` n'est pas vide (ligne 134), pour que la vérification ne
  passe pas « à vide ».

### Les tests suivent le code

`tests/sources/test_<module>.py` est le pendant de `src/k_b/sources/<module>.py` : les deux
fichiers de test d'une source sont fusionnés, ceux du téléchargement d'abord. Les fixtures
restent dans `tests/fixtures/`, que `tests/test_raw_items.py` utilise aussi. Les tests déplacés y
remontent par `Path(__file__).parent.parent / "fixtures"`
(`tests/sources/test_arxiv.py:20`). Les deux tests CISA lisaient le même fichier sous deux noms
(`CATALOG`, `EXTRACT`) : le fichier fusionné ne garde que `EXTRACT`
(`tests/sources/test_cisa_kev.py:17`).

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Nom des journaux | `logging.getLogger(__name__)` inchangé : `k_b.tldr_source` devient `k_b.sources.tldr` (et de même pour arxiv, github_releases, github_advisories). Le nom dit où est le code. Validé par Sabine le 06/10. | Figer les anciens noms en dur : la sortie ne changerait pas, mais elle désignerait des modules qui n'existent plus. |
| Ordre dans un module | `logger` et toutes les constantes en tête (usage courant, ordre de PEP 8), puis les fonctions du téléchargement, puis celles de la lecture, puis `READER` : l'ordre E puis T du pipeline. Constat 8 de la revue de code, validé par Sabine. | Chaque partie avec ses constantes, ce qui place une partie des constantes au milieu du fichier : c'était le premier jet, relevé par la revue. Lecture d'abord : aussi valide pour Python, moins lisible. |
| Fusion des tests | Un fichier de test par module, en miroir de `src/`. | Garder deux fichiers de test par source : le miroir module ↔ test serait perdu. |
| Fixtures | Restent dans `tests/fixtures/`. | Les déplacer dans `tests/sources/fixtures/` : `test_raw_items.py` s'en sert aussi. |
| `__init__.py` | Vide, selon le critère de #100. | Y réexporter les sources : du code dans un `__init__`, ce que Sabine veut éviter. |
| `database/__init__.py` | Non touché, selon la mission (issue à part). | — |
| Imports | Absolus (`from k_b.sources.x import …`), comme le reste du dépôt. | Relatifs : pas l'usage du dépôt. |
| Outil de fusion | Un script jetable (hors dépôt) pour la fusion, puis `ruff --select I --fix` pour trier les imports. Le résultat est relu et testé. | Fusion à la main de cinq paires : plus long, plus d'erreurs de copie. |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run pytest` : 307 passed (301 avant la PR) | Rien ne casse. +6 = un cas de forme d'import, quatre cas d'import relatif et le refus d'un import au-dessus de `k_b`, ajoutés au test de dépendances. Aucun test n'est perdu. |
| Lignes `def`/`assert`/`@pytest` des anciens fichiers de test toutes retrouvées dans les nouveaux, sauf 3 lignes CISA | Les 3 lignes ne diffèrent que par les renommages (`CATALOG` → `EXTRACT`, `cisa_kev_source.` → `cisa_kev.`). |
| `test_every_module_is_in_exactly_one_list` | Plus aucun module de source à plat dans `src/k_b/`. |
| `test_no_module_of_the_sources_imports_the_composition` | Le test de dépendances porte sur le paquet `k_b.sources`. |
| `test_relative_imports_inside_sources_are_resolved` | `from .. import cli` depuis une source est bien vu comme un import de `cli`. |
| Le test de dépendances, avant le déplacement : 2 failed | Le test échouait tant que les modules étaient à plat (tests d'abord). |
| `ruff check`, `ruff format --check`, `mypy --strict` verts | Imports triés et types inchangés. |
| `git diff --cached -M --name-status` : `R` pour chaque module de `src/k_b/sources/` | Git suit chaque fusion comme un déplacement du fichier de lecture. |
| Le grep du critère de #100 sur le README et les docs non datées ne renvoie rien | Plus aucun ancien chemin dans la doc vivante. |

## Ce que tu dois pouvoir défendre

1. **« Vous dites qu'aucun comportement ne change, mais les journaux changent ? »** Seul le nom
   du logger change, parce qu'il suit le chemin du module (`__name__`). Les messages, les
   niveaux et le format sont identiques (`tests/test_cli.py:139`). C'est un choix assumé, validé
   avant le code.
2. **« Pourquoi `github_api` est-il dans `sources/`, et pas dans le générique ? »** Seules les
   trois sources GitHub l'importent. Le générique ne doit rien savoir d'une source : c'est ce que
   vérifie `test_no_generic_module_imports_the_sources_or_the_composition`.
3. **« Qu'est-ce qui empêche une source d'importer `cli` ? »**
   `test_no_module_of_the_sources_imports_the_composition` parcourt chaque fichier de
   `sources/` et résout aussi les imports relatifs (`tests/test_module_dependencies.py:54-55`).
4. **« Comment savez-vous qu'aucun test n'a été perdu dans la fusion ? »** Le décompte (301 + 6
   ajoutés = 307) et la comparaison ligne à ligne des `def` et `assert` des anciens fichiers.
5. **« Un fichier fusionné de 230 lignes, ce n'est pas trop long ? »** Le module le plus long est
   `arxiv.py`, avec 231 lignes, pour une seule source. Une fonction fait toujours une chose. Le
   critère était « un module par source », pas une taille.

## Zones non vérifiées

- `git log --follow tests/sources/test_github_advisories.py` ne remonte pas aux anciens fichiers :
  Git voit ce fichier comme un ajout (`A`), parce que sa partie lecture fait 117 lignes sur 249
  (47 %, sous le seuil de 50 %). Pour l'historique, il faut lire
  `tests/test_github_advisories.py` et `tests/test_github_advisories_source.py` avant ce commit.
- Personne n'a vérifié si un outil externe (supervision, `grep` dans des journaux) cherche les
  anciens noms de logger. K-B n'a pas encore de surveillance des exécutions (reportée, voir
  `MEMORY.md`).

## Ce qui reste

- Les issues ouvertes #61, #69, #71 et #77 citent encore les anciens noms de modules dans leur
  texte. Il faut les mettre à jour à leur reprise.
- `src/k_b/database/__init__.py` contient encore du code : une issue à part.
- La suite du plan ETL : #101, puis #105, #106, #107.
