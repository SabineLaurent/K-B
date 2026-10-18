# Marquer le retrait, ranger les tests d'architecture

- **Date** : 2026-10-18
- **Branche** : `refactor/mark-withdrawn-and-architecture-tests`
- **Issue** : #253
- **Fichiers principaux** : `src/k_b/database/writers/vulnerability_writer.py`,
  `src/k_b/database/writers/zotero_entry_writer.py`, `src/k_b/database/writing.py`,
  `src/k_b/etl/load.py`, `tests/architecture/` (cinq fichiers, qui remplacent
  `tests/test_module_dependencies.py`)
- **Série** : suite de [Rassembler le choix des écrivains](2026-10-18-rassembler-le-choix-des-ecrivains.md)
  (#251), qui avait donné le verbe `mark_withdrawn` aux alias de `database/writing.py` et laissé le
  renommage des fonctions pour cette issue.

Deux commits de la branche sont couverts : `dc72011` (le renommage) et `c9883df` (le déplacement
des tests). La liste de fichiers fournie à la note s'étendait plus loin en arrière (#250, #252) :
ces changements sont fusionnés et ont leurs propres notes.

## Le pourquoi

Deux harmonisations décidées par Sabine le 18/10, sans changement de comportement.

**Un retrait n'est pas une suppression.** Quand un catalogue d'état (CISA KEV, l'extrait Zotero)
ne liste plus une ligne qu'il listait, K-B ne l'efface pas : il note la date où elle a disparu,
dans la colonne `withdrawn_at`. La ligne reste lisible, avec son histoire. Or la fonction qui fait
ce marquage s'appelait `withdraw_absent`, « retirer les absents », et le nom a fait croire à une
suppression. Le nouveau nom, `mark_withdrawn`, dit ce que fait le code : il marque.

**Les tests d'architecture à part.** `tests/test_module_dependencies.py` (517 lignes, 27 tests,
88 identifiants collectés) ne vérifie pas ce que K-B fait, mais comment son code est rangé : quel
module a le droit d'importer quel autre. Rangé au milieu des tests du comportement, il ne se
distinguait pas d'eux, et un seul fichier mêlait quatre sujets. Il est réparti dans
`tests/architecture/`, un fichier par thème.

## Le comment

### 1. Le retrait est un `UPDATE`, pas un `DELETE`

`src/k_b/database/writers/vulnerability_writer.py:46-55` :

```python
# State catalog (CISA KEV): a CVE of a KEV item absent from a catalog collected after the
# latest one imported is withdrawn at that collection; the first absence keeps its date.
MARK_WITHDRAWN_VULNERABILITIES = """
UPDATE vulnerability SET withdrawn_at = :collected_at
WHERE item_id IS NOT NULL
    AND withdrawn_at IS NULL
    AND cve_id NOT IN (SELECT value FROM json_each(:present_cve_ids))
"""
```

La requête écrit une date dans `withdrawn_at` pour chaque CVE absente de la liste des présentes
(`NOT IN`). Trois gardes :

- `item_id IS NOT NULL` : seule une CVE venue du catalogue KEV peut en être retirée ; une CVE créée
  par un avis GitHub n'a jamais été dans ce catalogue.
- `withdrawn_at IS NULL` : une CVE déjà retirée garde la date de sa **première** absence. C'est ce
  que prouve `test_a_kev_row_absent_from_two_catalogs_keeps_the_date_of_the_first`
  (`tests/etl/test_load.py:1361`).
- La liste des présentes est passée en JSON et lue par `json_each`, pour un nombre de CVE
  quelconque dans une seule requête paramétrée.

Rien n'est effacé : si la CVE revient dans un catalogue plus récent, l'upsert de `write` remet
`withdrawn_at` à vide et date son retour dans `revised_at`
(`test_a_withdrawn_kev_row_back_in_a_newer_catalog_is_written_again_and_dated`,
`tests/etl/test_load.py:1337`). Le retrait Zotero suit le même modèle sur `zotero_entry` et
`highlight` (`zotero_entry_writer.py:68-82`).

### 2. Le même verbe dans chaque écrivain

`src/k_b/database/writers/vulnerability_writer.py:96` et `zotero_entry_writer.py:166` définissent
toutes deux `def mark_withdrawn(`. Chaque écrivain a déjà `write` ; la règle de `code.md`
(« Lisibilité ») veut qu'une même action porte le même verbe pour chaque entité, sans répéter ce
que le module dit déjà : `vulnerability_writer.mark_withdrawn`, pas
`vulnerability_writer.mark_withdrawn_vulnerabilities`. Les constantes SQL suivent :
`MARK_WITHDRAWN_VULNERABILITIES`, `MARK_WITHDRAWN_ZOTERO_ENTRIES`, `MARK_WITHDRAWN_HIGHLIGHTS`.

### 3. Les alias de la porte ne changent pas

`src/k_b/database/writing.py:29-34` :

```python
from k_b.database.writers.vulnerability_writer import (
    mark_withdrawn as mark_withdrawn_vulnerabilities_not_in,
)
from k_b.database.writers.zotero_entry_writer import (
    mark_withdrawn as mark_withdrawn_zotero_rows_not_in,
)
```

Seul le nom importé change. `writing.py` est la seule porte vers `writers/` (`conventions.md`,
règle 5) ; comme les deux écrivains ont maintenant le même nom de fonction, la porte doit les
renommer pour les exposer côte à côte, et ces alias portaient déjà le verbe choisi (#251). Le
suffixe `_not_in` dit ce qu'ils reçoivent, la liste des présents, et les distingue des deux
fonctions de `etl/load.py`, `mark_withdrawn_vulnerabilities` et `mark_withdrawn_zotero_rows`
(`load.py:384`, `:409`), qui décident d'abord si un fichier peut retirer quelque chose (un
fichier avec une entrée rejetée ne retire rien) puis appellent la porte.

### 4. Ce qu'est un test d'architecture

Un test d'architecture ne lance pas K-B : il lit son code source et vérifie une règle de
rangement. `tests/architecture/test_layers.py:50-56` :

```python
def test_only_database_imports_its_writers():
    paths = [
        path.relative_to(PACKAGE_DIR).as_posix()
        for path in sorted(PACKAGE_DIR.rglob("*.py"))
        if not path.is_relative_to(PACKAGE_DIR / "database")
        and list_imports_of_the_writers(list_imported_modules(path, find_package(path)))
    ]
```

Pour chaque fichier de `k_b` hors de `database/`, le test lit les imports (par `ast`, sans
exécuter le module) et garde ceux qui atteignent `database/writers`. La liste attendue est vide.
Si quelqu'un importe demain un écrivain depuis `etl/`, aucun test du comportement n'échoue (le
code marche), mais celui-ci échoue : il protège une décision d'architecture, pas un résultat.

Le lecteur des imports a ses propres tests (`test_import_reading.py`) : chaque forme d'import
(`import k_b.x`, `from k_b.x import y`, import relatif, import dans une fonction) doit être vue,
sinon une règle d'architecture pourrait passer sans rien vérifier.

### 5. Le découpage en quatre thèmes, et un module partagé

| Fichier | Ce qu'il vérifie | Tests / identifiants |
|---|---|---|
| `module_imports.py` | rien : le lecteur des imports et les listes de modules partagées | — |
| `test_import_reading.py` | le lecteur et le listage des fichiers | 8 / 31 |
| `test_packages.py` | chaque module listé une fois, `__init__.py` vides | 3 / 3 |
| `test_layers.py` | le sens des imports sous `k_b` et `k_b.etl`, la porte des écrivains | 8 / 14 |
| `test_apis.py` | ce qu'importent l'API de données et l'API IA, les couches de l'API IA | 8 / 40 |

Chaque fichier de test commence par `from module_imports import (...)`. Cet import marche sans
`__init__.py` : pytest, dans son mode d'import par défaut (`prepend`), ajoute au chemin d'import
le dossier de chaque fichier de test qui n'est pas dans un paquet, ici `tests/architecture/`. Le
dépôt fait déjà ainsi (`tests/etl/test_load_clips.py:8`, `from test_load import ...`).
`module_imports.py` n'est pas collecté : son nom ne commence pas par `test_`.

Les outils propres à un thème (`list_imports_of_the_writers`, `DATA_API_*`, `AI_API_*`,
`name_module`, `COMMAND_LINE_FORBIDDEN_MODULES`) restent dans le fichier de leurs tests : ils n'ont
qu'un usager chacun.

## Choix faits et options écartées

- **`mark_withdrawn` dans chaque écrivain** (retenu) : le même verbe partout, comme `write`
  (`code.md`). Imposé pour le verbe par la décision de Sabine du 18/10, 21:20Z.
- **Garder les alias de `writing.py`** (retenu) : ils portaient déjà le verbe ; écarté : les
  renommer, sans gain.
- **Garder `withdrawn`, `withdrawal`, `withdrawn_count` et les tests `…_withdraws_nothing`**
  (retenu) : ils décrivent l'état (la colonne `withdrawn_at`), pas une suppression ; écarté : tout
  renommer, ce qui aurait touché la colonne, les messages et le journal d'import, donc le
  comportement.
- **Quatre fichiers par thème** (retenu) ; écarté : un fichier par règle, une dizaine de fichiers
  pour 27 tests.
- **Les outils dans `module_imports.py`** (retenu) ; écarté : `tests/architecture/conftest.py`, qui
  porte des fixtures, pas des fonctions qu'on importe.
- **Pas de `tests/architecture/__init__.py`** (retenu) ; écarté : avec lui, pytest ajouterait
  `tests/` au chemin d'import et non `tests/architecture/`, et l'import changerait de forme. Aucun
  dossier de `tests/` n'en a.
- **Découpe par tranches de lignes** (retenu) : les corps des tests sont recopiés tels quels du
  fichier d'origine par un script, puis comparés ligne à ligne ; écarté : une recopie à la main.
- **La docstring du module d'origine partagée** entre `test_layers.py` (couches de `k_b` et de
  `k_b.etl`) et `test_apis.py` (couches de `k_b.ai_api`) : chaque partie suit les tests qu'elle
  décrit.
- **Pas d'ADR** : aucune décision d'architecture nouvelle ; le verbe est consigné dans le journal
  ADR depuis #251, le rangement est décidé dans l'issue.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `git grep -niE "withdraw_absent" HEAD -- src tests` → rien | le renommage est complet dans le code et les tests |
| `uv run pytest -q` → 1769 passed, comme sur 991a384 | aucun test perdu ni cassé |
| `uv run pytest --collect-only -q`, clé aléatoire et chemins d'architecture remplacés par un repère, `comm -3` avec 991a384 → rien | les 1769 identifiants sont les mêmes ; seuls les chemins des tests déplacés changent |
| lignes non vides de l'ancien fichier (`:19-517`) et des cinq nouveaux, sans les en-têtes, triées → `diff` vide | aucun corps de test, paramètre ni nom n'a changé |
| marche réelle `kb create-db` puis deux `kb import`, branche contre 991a384 (`git archive`), dates et chemins remplacés | même comportement : codes 0, 0, 0 ; sorties, journaux d'import (10 lignes, puis 0) et dump SQL (321 lignes) identiques ; 14 bruts, 22 items, 1 CVE retirée (CVE-2020-29583, absente du second catalogue) |
| `ruff check`, `ruff format --check`, `mypy --strict` | contrôles du dépôt verts |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas supprimer une CVE que le catalogue ne liste plus ?** Parce que l'absence est
   une information : K-B garde la date du retrait, et la ligne revient si le catalogue la relit.
   Une suppression perdrait l'histoire et le lien vers l'item. Voir
   `vulnerability_writer.py:49-55` et `tests/etl/test_load.py:1337`.
2. **Que se passe-t-il si un catalogue arrive vide ?** Rien n'est retiré :
   `mark_withdrawn` rend 0 sans liste de présentes (`vulnerability_writer.py:110`), sinon le
   `NOT IN` d'une liste vide retirerait toutes les CVE. Testé par
   `test_a_cisa_kev_withdrawal_without_cve_withdraws_nothing` (`tests/database/test_writers.py`).
3. **Un test d'architecture, c'est utile si tous les tests du comportement passent ?** Oui : il
   échoue quand le code marche mais viole une règle de rangement (un import qui remonte les
   couches). Sans lui, la règle 5 de `conventions.md` ne serait qu'un texte. Voir
   `tests/architecture/test_layers.py:50`.
4. **Comment sais-tu que le déplacement n'a rien perdu ?** Les identifiants collectés sont
   comparés avant et après (`comm -3` vide), et les corps des tests ligne à ligne.
5. **Pourquoi `from module_imports import` marche-t-il sans paquet ?** Le mode `prepend` de pytest
   met le dossier du fichier de test dans le chemin d'import ; voir la section 5 du comment.

## Zones non vérifiées

- **Le retrait Zotero dans la marche réelle** : la fixture Zotero est une base
  (`zotero_extract.sql`), pas un brut ; le retrait Zotero reste couvert par
  `tests/etl/test_load_zotero.py`, pas par la marche.
- **Le mode d'import de pytest** : l'explication du mode `prepend` vient de la documentation de
  pytest telle que le dépôt l'applique déjà ; elle n'a pas été relue à la source pour cette note.
  Le résultat, lui, est observé : les 88 identifiants d'architecture sont collectés et passent.

## Ce qui reste

- La limite signalée par #251 : le test des `__init__.py` ne voit pas un dossier de modules sans
  `__init__.py`. Signalée, sans règle nouvelle.
- Le nommage des modules par l'objet : après le 25/10.
- Les notes datées et le journal ADR citent encore `withdraw_absent` et
  `tests/test_module_dependencies.py` : ce sont des instantanés, on ne les réécrit pas.
