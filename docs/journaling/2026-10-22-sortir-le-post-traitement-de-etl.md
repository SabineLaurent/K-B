# Sortir le post-traitement de l'ETL

- **Date** : 2026-10-22
- **Branche** : `refactoring/etl`
- **Issue** : aucune ; refactorisation conduite directement par Sabine, sur la cible de
  [l'inventaire](../refactoring/inventaire.md)
- **Fichiers principaux** : `src/k_b/post/` (quatre modules déplacés et un `__init__.py` vide),
  `src/k_b/etl/tops.py`, `tests/post/` (quatre tests déplacés),
  `tests/architecture/test_layers.py`, `tests/architecture/module_imports.py`
- **Série** : première étape de la refactorisation de l'ETL, après
  [l'inventaire avant refactorisation](../refactoring/inventaire.md) (commit `cfe1dae`).

Trois commits sont couverts : `58e372e` (`ai_api_client` et `digest_sheets`), `575a63d` (`Top` et
`TopEntry` dans `etl/tops.py`) et `96aaa2b` (`top_sheets` et `vault_files`). Aucun corps de
fonction n'a changé : les quatre déplacements sont des `git mv`, et les seules lignes de code
modifiées sont des lignes d'`import`.

## Le pourquoi

`src/k_b/etl/` contenait quatre modules qui ne relèvent pas du pipeline. L'ETL *extrait* d'une
source, *transforme* en items communs et *charge* en base. Or ces quatre-là font autre chose :
demander des fiches à l'API IA, rendre une fiche en Markdown, l'écrire dans le coffre Obsidian.
C'est du **post-traitement** : ça part de ce que le pipeline a produit et ça le présente à un
humain. Mélangés aux modules du pipeline, ils rendaient `etl/` illisible comme table des matières
(`code.md`, « Lisibilité ») : on ne pouvait plus dire ce que `etl` fait sans énumérer des
exceptions.

Le rangement sert aussi la suite. La cible annoncée par Sabine sépare `etl/extract`,
`etl/transform`, `etl/load` et `etl/pipeline.py` d'un côté, `post/` de l'autre, avec une règle :
`etl` n'importe jamais `post`. Tant que les deux vivaient dans le même paquet, cette règle était
intenable — et invérifiable.

## Le comment

### 1. Un paquet `post/`, sans sous-dossiers pour l'instant

`src/k_b/post/` reçoit les quatre modules, à plat :

| Module | Lignes | Ce qu'il fait |
|---|---|---|
| `ai_api_client.py` | 299 | la demande de `kb digest` à l'API IA, et la réponse |
| `digest_sheets.py` | 207 | la fiche de veille rendue en Markdown |
| `top_sheets.py` | 200 | les fiches des tops, et la purge des relevés qu'elles remplacent |
| `vault_files.py` | 116 | l'écriture sûre dans le coffre, partagée par les deux sortes de fiches |

La cible de l'inventaire prévoit `post/digest/` et `post/render/`. Ils ne sont pas créés : avec
quatre modules, deux sous-dossiers de deux fichiers ne font gagner aucune lisibilité, et
`digest_sheets.py` relèverait des deux à la fois. Décision de Sabine pour cette passe.

`post/__init__.py` est vide, comme tous les autres (`test_every_package_of_k_b_has_an_empty_init`).

### 2. `Top` et `TopEntry` restent dans `etl/`

Le déplacement de `top_sheets.py` s'est heurté à un blocage : trois modules qui restent dans
`etl/` importaient ce module.

| Module qui reste dans `etl/` | Ce qu'il importait de `top_sheets.py` |
|---|---|
| `etl/source_kinds.py` | `Top`, pour bâtir le tuple `TOPS` |
| `etl/sources/github_most_starred.py` | `TopEntry`, type de retour de `read_top_entries` |
| `etl/sources/github_most_forked.py` | `TopEntry`, idem |

Déplacer `top_sheets.py` tel quel aurait donc créé trois imports `etl` → `post`, exactement ce que
la règle interdit. Les deux classes sont sorties dans `src/k_b/etl/tops.py` (33 lignes), telles
quelles — aucun champ, nom ni signature changé :

```python
@dataclass(frozen=True)
class Top:
    """A top ranking: the folder of its sheets under veille/tops/, the raw folder of its
    rankings and their reader, and the words of its sheet."""

    name: str
    folder_key: str
    read_entries: Callable[[bytes], list[TopEntry]]
    count_heading: str
    # What it ranks, after "Top <n> des".
    subject: str
```

Le partage se lit maintenant dans le sens des couches : `etl/tops.py` porte le vocabulaire, les
sources le produisent, `post/top_sheets.py` le consomme. `post` importe `etl` ; `etl` n'importe
pas `post`.

`vault_files.py` a été bloqué par le même nœud, un commit de plus : tant que `top_sheets.py`
restait dans `etl/`, il ne pouvait pas partir, puisque `top_sheets.py` lit sept de ses noms. Il est
parti avec lui.

### 3. La règle, tenue par un test

`tests/architecture/test_layers.py:138-162` :

```python
# etl runs below the post-processing: post reads the pipeline, the pipeline never reads post.
def list_imports_of_the_post_processing(imported: set[str]) -> set[str]:
    return {name for name in imported if reaches(name, {"post"})}


def test_etl_imports_nothing_of_the_post_processing():
    for path in list_python_files("etl"):
        imported = list_imported_modules(path, find_package(path))
        assert list_imports_of_the_post_processing(imported) == set(), path
```

Le test lit les imports de chaque fichier de `etl/`, sous-dossiers compris, par `ast` et sans
exécuter les modules. `reaches` refuse aussi le paquet qui donne accès à `post` : `from k_b import
post` est vu, pas seulement `from k_b.post.x import y`. Un second test, paramétré, vérifie que le
détecteur refuse bien chaque forme d'import (absolue, par le paquet, relative) et laisse passer un
module de `etl` — même motif que la règle des API juste au-dessus, et que celle des écrivains
(#251).

Les deux listes partagées de `tests/architecture/module_imports.py` suivent : `"post"` entre dans
`TOP_LEVEL_MODULES`, les quatre modules sortent d'`ETL_PIPELINE_MODULES`, et `"etl.tops"` y entre.
Ces listes ne sont pas décoratives : `test_every_module_of_k_b_is_listed` et
`test_every_module_of_etl_is_in_exactly_one_list` échouent si un module nouveau n'y figure pas.
C'est ce qui empêche un module d'arriver dans `etl/` ou dans `post/` sans que personne ne décide
où il va.

### 4. Les chemins périmés dans la doc, triés avant d'être changés

Quatorze mentions de `etl/ai_api_client.py`, `etl/digest_sheets.py`, `etl/top_sheets.py` et
`etl/vault_files.py` restaient dans le dépôt après les déplacements. Elles ont été classées avant
d'être touchées :

- **vivantes** — elles décrivent l'état actuel : les commentaires de `core/config.py`, les
  docstrings de `post/` et des deux sources de tops, `docs/fiches-veille.md` (le contrat des
  fiches) et `docs/registre-traitements.md` (le registre en vigueur). Corrigées.
- **historiques** — elles racontent un état passé : `docs/journaling/` (notes datées),
  les entrées déjà écrites du journal ADR, `docs/refactoring/inventaire.md` (« Relevé du
  2026-10-22, commit `51bb7ea` ») et `docs/2026-10-21-collecte-reelle.md` (« Compte rendu de
  #25 … commit 431637a »). **Pas touchées** : ce sont des instantanés, comme l'avait déjà posé la
  note du 18/10 sur les tests d'architecture.

Dans les deux docstrings de `read_top_entries`, le renvoi ne devient pas `post/top_sheets.py` mais
`(TopEntry, etl/tops.py)` : décision de Sabine, un module de `etl` se décrit par ce qu'il produit,
pas par son consommateur dans `post`.

## Choix faits et options écartées

- **Un paquet `post/` à plat** (retenu) ; écarté : `post/digest/` et `post/render/` tout de suite
  (deux fichiers chacun, et `digest_sheets.py` à cheval sur les deux).
- **`Top` et `TopEntry` dans `etl/tops.py`** (retenu) : `etl` garde le vocabulaire que ses sources
  produisent ; écarté : les mettre dans `items.py` (ce n'est pas un item de la base, il n'entre
  jamais en base) ; écarté : laisser `top_sheets.py` dans `etl/` (le post-traitement resterait
  mélangé au pipeline) ; écarté : déplacer `top_sheets.py` sans extraire les types et renoncer à la
  règle, ou lui faire une exception.
- **Le nom `tops.py`** (retenu, Sabine) : le pluriel dit une famille de types, à côté de
  `top_sheets.py` qui dit un traitement.
- **La règle vérifiée par un test, pas par un `grep`** (retenu) : une règle d'architecture qu'un
  test ne tient pas n'est qu'un texte (entrée de #247, reprise à #251).
- **Les historiques non réécrits** (retenu, Sabine) ; écarté : corriger partout, ce qui aurait fait
  mentir des notes datées sur ce qu'elles ont observé.
- **Deux passes séparées par un commit** (retenu, Sabine) : l'extraction des types d'abord, tests
  verts, puis le déplacement ; chaque commit est relisible seul.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run pytest` → 2263 passed avant, 2269 après | aucun test perdu ; les 6 de plus sont la règle nouvelle (1 test + 5 cas paramétrés) |
| `grep -rn "k_b.post" src/k_b/etl` → rien | aucun `etl` → `post` dans le code |
| un `from k_b.post import top_sheets` ajouté à `etl/user_agent.py` → `test_etl_imports_nothing_of_the_post_processing` **FAILED**, puis annulé par édition inverse | la règle mord : elle n'est pas creuse |
| bloc des classes retiré de `top_sheets.py` comparé ligne à ligne au contenu de `etl/tops.py` → `diff` vide | `Top` et `TopEntry` sont déplacées à l'identique |
| `git status` : les 8 déplacements vus comme `renamed` par git | aucun fichier réécrit |
| `ruff check --no-cache`, `ruff format --check`, `mypy --strict` | contrôles du dépôt verts |

## Ce que tu dois pouvoir défendre

1. **Pourquoi `post/` et pas un module de plus dans `etl/` ?** Parce que `etl` nomme un parcours
   précis — extraire, transformer, charger — et que rendre une fiche Markdown dans un coffre
   Obsidian n'en fait pas partie. Un paquet dont le nom ne prédit plus le contenu ne sert plus de
   table des matières.
2. **Pourquoi la règle va-t-elle dans un sens seulement ?** Parce que le post-traitement part de ce
   que le pipeline a produit : il doit pouvoir lire `etl` (`post/top_sheets.py` lit le brut par
   `RawStore`). L'inverse signifierait que la collecte dépend de la façon de présenter ses
   résultats — et un cycle d'imports.
3. **Qu'est-ce qui empêche quelqu'un de recréer l'import interdit ?**
   `test_etl_imports_nothing_of_the_post_processing`, qui lit tous les fichiers de `etl/` par
   `ast`. La contre-épreuve de la table « Preuve » montre qu'il échoue quand l'import existe.
4. **Pourquoi avoir extrait `Top` et `TopEntry` au lieu de déplacer `top_sheets.py` directement ?**
   Parce que trois modules qui restent dans `etl/` en ont besoin. Sans l'extraction, le
   déplacement créait l'import interdit ; l'extraction est le seul changement de structure de
   cette refactorisation.
5. **Pourquoi ne pas avoir corrigé les chemins dans `docs/journaling/` ?** Parce qu'une note datée
   dit ce qui a été observé ce jour-là, numéros de ligne compris. La réécrire la ferait mentir. La
   vérité d'aujourd'hui vit dans les documents de référence et dans le code.

## Zones non vérifiées

- **Le comportement de `kb digest` et de `kb write-tops` en marche réelle** n'a pas été rejoué :
  la preuve repose sur la suite de tests et sur le fait que seules des lignes d'`import` changent.
  Les tests de bout en bout (`-m e2e`) n'ont pas été lancés.
- **La cible complète de l'inventaire** (`etl/extract/`, `etl/transform/`, `etl/load/`,
  `etl/pipeline.py`) n'est pas entamée : cette passe ne sort que le post-traitement.
- **Le tri vivant/historique des quatorze mentions** est un jugement, validé par Sabine le
  2026-10-22, pas un critère automatique : un document nouveau devra être classé à la main.

## Ce qui reste

- **`Top` mélange collecte et rendu** : `folder_key` et `read_entries` servent la collecte,
  `count_heading` et `subject` uniquement le rendu de la fiche, `name` les deux. Signalé, non
  traité : une passe dédiée après celle-ci.
- **`post/top_sheets.py` lit le brut** par `read_entries` et par `RawStore` : le post-traitement
  descend dans le brut du pipeline. Même passe.
- **`Top` est instancié dans `etl/source_kinds.py`** alors que ses cinq champs sont tous lus
  depuis `post/`. Même passe.
- La suite de la cible : découper `etl/` en `extract`, `transform`, `load` et `pipeline.py`.
