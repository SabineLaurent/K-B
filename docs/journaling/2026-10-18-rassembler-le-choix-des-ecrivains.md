# Rassembler le choix des écrivains dans `database/writing.py`

- Date : 2026-10-18
- Branche : `refactor/database-writing`
- Issue : #251
- Fichiers principaux : `src/k_b/database/writing.py` (nouveau), `src/k_b/etl/load.py`,
  `src/k_b/etl/import_log.py`, `src/k_b/commands/import_command.py`,
  `tests/test_module_dependencies.py`
- Série : suite de [Rassembler les routeurs de l'API de données](2026-10-18-rassembler-les-routeurs-de-l-api-de-donnees.md)
  (#246) et de [Ranger la ligne de commande](2026-10-18-ranger-la-ligne-de-commande.md) (#247).

La liste de fichiers injectée au lancement de la note comptait aussi les fichiers de #246 (routeurs,
`specs-api.md`, ADR) : ils appartiennent à la PR déjà fusionnée, pas à cette branche. Cette note
couvre les deux commits de la branche, `5d1d7f3` (test des `__init__.py`) et `4b603a6`
(déplacement).

## Le pourquoi

L'import (`etl/load.py`) écrit chaque item par l'écrivain de sa sorte : un module de
`database/writers/` par sorte (article, CVE, release…). Jusqu'ici, `load.py` importait lui-même
neuf modules de `writers/` et tenait le registre qui dit quel écrivain écrit quelle sorte. Trois
autres modules hors de `database/` lisaient aussi dans `writers/`.

Sabine a décidé le 18/10 que ce choix appartient à la couche base : c'est la base qui sait quel
écrivain écrit quelle sorte, et l'import ne lui parle que par une seule porte. C'est la même
logique que pour les routeurs (`api_router.py`, #246) et que pour la ligne de commande mince
(#247). Le rangement ne change aucun comportement : même bilan, mêmes journaux, même base.

La même issue range une seconde règle, groupée par décision de Sabine : chaque `__init__.py` de
`src/k_b` reste vide, sans exception, et un seul test le tient.

## Le comment

### 1. Une table de dispatch : `WRITER_BY_KIND`

```python
# The kinds that have a table in the base, each with its writer.
WRITER_BY_KIND: dict[str, Callable[[sqlite3.Connection, Item, int], Discard | None]] = {
    "paper": paper_writer.write,
    "vulnerability": vulnerability_writer.write,
```
(`src/k_b/database/writing.py:57-60`)

Une **table de dispatch** associe une clé (la sorte de l'item, `item.kind`) à la fonction qui la
traite. Elle remplace une suite de `if kind == "paper": … elif kind == "vulnerability": …`. Ajouter
une sorte, c'est ajouter une ligne. Le type dit le contrat commun : chaque écrivain reçoit la
connexion, l'item et l'identifiant de son brut (`raw_data_id`), et rend `None` (écrit) ou un
`Discard` (laissé de côté, avec sa règle).

`write_item` lit la table :

```python
    write_kind = WRITER_BY_KIND.get(item.kind)
    if write_kind is None:
        raise KindWithoutTableError(f"kind without a table in the base: {item.kind}")
    return write_kind(connection, item, raw_data_id)
```
(`src/k_b/database/writing.py:73-76`)

Une sorte sans écrivain (une sorte ajoutée à `items.py` avant sa table) est une erreur qui arrête
l'import, pas un rejet : c'est le code qui est incomplet, pas l'entrée. Ces trois objets
(`WRITER_BY_KIND`, `write_item`, `KindWithoutTableError`) sont déplacés de `load.py` sans changer une
ligne. L'erreur suit `write_item`, qui la lève : restée dans `etl`, elle aurait obligé `database` à
importer `etl`, ce que refuse `test_database_imports_only_items_and_core`.

### 2. La porte d'écriture, en face de `reading.py`

`database/` a maintenant deux portes pour les couches du dessus :

- `reading.py` lit la base. Il est utilisé par l'API de données et par `load.py`
  (`read_raw_file_paths`).
- `writing.py` écrit la base : il est utilisé par `load.py`, `import_log.py` et `import_command.py`.

Le nom suit les voisins (`reading.py`, `creation.py`, `connection.py`) : un nom de rôle, à la
racine de `database/`, à côté du dossier `writers/` qu'il rassemble (décision de Sabine du 18/10).

`writing.py` n'écrit lui-même aucun SQL. Le SQL reste dans chaque écrivain (`conventions.md`,
règle 5) ; `grep -cE "INSERT INTO|SELECT |UPDATE |DELETE FROM|\.execute\(" writing.py` → 0.

### 3. Ce que la porte expose : `__all__` et des alias

```python
from k_b.database.writers.trend_writer import DISCARD_RULE as TREND_DISCARD_RULE
from k_b.database.writers.trend_writer import write as write_trend_rows
from k_b.database.writers.vulnerability_writer import (
    withdraw_absent as mark_withdrawn_vulnerabilities_not_in,
)
```
(`src/k_b/database/writing.py:27-31`)

`writing.py` réexporte les objets des écrivains que l'import lit : `write_raw_data`,
`write_tracked_repositories`, `Discard`, `DiscardRule`, `UnknownSourceError`, plus quatre objets
renommés à l'import. Un alias (`import x as y`) donne un autre nom dans `writing.py` sans renommer
la fonction dans son module. Il en faut un quand le nom d'origine ne dit plus rien hors de son
module :

- `write` serait muet, et se confondrait avec `write_item` : il devient `write_trend_rows` ;
- `DISCARD_RULE` devient `TREND_DISCARD_RULE`, la règle du classement ;
- les deux `withdraw_absent` portent le même nom et ne peuvent pas coexister. Sabine a choisi
  `mark_withdrawn_vulnerabilities_not_in` et `mark_withdrawn_zotero_rows_not_in`. « mark » dit ce
  que fait la fonction : un `UPDATE` qui remplit `withdrawn_at`, pas une suppression. « not_in » dit
  ce qu'elle reçoit : la liste des présents.

La liste `__all__` (`writing.py:37-50`) dit ce que la porte expose. Elle a un second effet, qui est
le vrai garde-fou : `mypy --strict` inclut `--no-implicit-reexport`. Un nom importé dans
`writing.py` mais absent de `__all__` n'est pas exporté. `from k_b.database.writing import
trend_writer` échoue donc au typage (« does not explicitly export attribute »). Les modules
d'écrivains importés pour la table restent ainsi derrière la porte.

### 4. Deux règles tenues par des tests

```python
def test_only_database_imports_its_writers():
    paths = [
        path.relative_to(PACKAGE_DIR).as_posix()
        for path in sorted(PACKAGE_DIR.rglob("*.py"))
        if not path.is_relative_to(PACKAGE_DIR / "database")
        and list_imports_of_the_writers(list_imported_modules(path, find_package(path)))
    ]
```
(`tests/test_module_dependencies.py:274-280`)

Le test lit les imports de chaque fichier de `src/k_b` hors de `database/`, sans l'exécuter (module
`ast`). Il coupe chaque nom importé à deux niveaux : `k_b.database.writers.discard` devient
`database.writers`. `list_imports_of_the_writers` utilise `reaches` et non `is_within`. Avec
`reaches`, `from k_b import database` est aussi refusé, car le paquet `database` contient
`writers`. Le test liste tous les fichiers fautifs en une seule assertion : avant le déplacement, il
en montrait trois (`commands/import_command.py`, `etl/import_log.py`, `etl/load.py`). Ses cas
paramétrés prouvent chaque forme d'import, relatives comprises.

L'API de données ne doit pas écrire : `DATA_API_FORBIDDEN_MODULES` gagne `"database.writing"`
(`tests/test_module_dependencies.py:306`). Sa règle lit maintenant ses interdits avec `reaches`,
comme celle des écrivains (tri de la revue de code) : `from k_b import database` lui est refusé,
alors que son cas de test le permettait, car le paquet `database` donne accès à la porte
d'écriture. `from k_b.database import reading` reste permis. L'API IA refusait déjà tout
`database`.

### 5. Les `__init__.py` vides

```python
def test_every_package_of_k_b_has_an_empty_init():
    paths = sorted(PACKAGE_DIR.rglob("__init__.py"))

    assert paths
    assert [path for path in paths if path.read_text() != ""] == []
```
(`tests/test_module_dependencies.py:242-246`)

Un `__init__.py` qui importerait les modules d'un paquet en ferait une seconde porte, cachée.
`writers/__init__.py` aurait pu rassembler les écrivains, mais `code.md` et la décision de #246 le
refusent. Le test parcourt tous les `__init__.py`, y compris ceux d'un paquet créé plus tard.
`assert paths` l'empêche de passer à vide si le chemin se trompait. Il remplace deux tests partiels :
celui de `routers/__init__.py` (#246) et celui des paquets d'`ai_api` (#242), qui vérifiait qu'ils
n'importent rien d'`ai_api`. Un fichier vide n'importe rien : le nouveau test est plus strict que les
deux.

### 6. Trois « writing » qui ne se gênent pas

- `k_b.database.writing` : la porte d'écriture de la base (ce module).
- `k_b.ai_api.stages.writing` : la rédaction d'une fiche par le modèle (une étape de l'API IA).
  Sabine a gardé le nom malgré l'homonyme (« pour la db on va garder les ing »). Les deux ne se
  croisent jamais : l'API IA n'importe pas `database`.
- La variable `writing` de `load.py` (un `FileWriting`, ce qu'a donné l'écriture d'un fichier,
  `load.py:95`, `join_writings`). Pas de conflit : `load.py` importe des noms de la porte
  (`from k_b.database.writing import write_item, …`), jamais le module lui-même.

## Choix faits et options écartées

| Choix | Retenu, pourquoi | Écarté, pourquoi |
|---|---|---|
| Ce qui part dans `writing.py` | La table, `write_item` et son erreur, et tout ce que l'import lit dans `writers/` : une seule porte. | Ne déplacer que la table : `load.py` aurait encore importé six modules de `writers/`. |
| Ce qui reste dans `load.py` | `write_item_in_savepoint` (utilise `reject` d'`etl`), `register_raw_file` (utilise `find_stream`), les conditions de retrait (lisent un `RawFile`). `database` n'importe pas `etl` (règle 5). | Les mettre dans `writing.py` : `database` importerait `etl`. |
| Forme de la porte | `__all__`, trié (RUF022), tenu par `mypy --strict`. | Import implicite (F401, mypy) ; `import x as x` (PLC0414) ; affectations `y = writer.x` (liste dispersée). Essais de la partie 1. |
| Noms exposés | Quatre alias (décision de Sabine du 18/10) ; les fonctions des écrivains et de `load.py` gardent leur nom. | `withdraw_…_not_in`, `…_not_listed` : « withdraw » laisse croire à une suppression. Renommer partout : hors déplacement, petite issue juste après #251. |
| Porte dans `writers/__init__.py` | Non. | Interdit par `code.md` et par la décision de #246. |
| `import_log.py`, `import_command.py` | Passent aussi par la porte : la règle n'a pas d'exception. | Les laisser lire `writers/` : le test aurait une liste d'exceptions. |
| Test de la règle | Un test, avec ses cas (ADR de #247 : une règle de rangement se tient par un test). | Un `grep` seul : il ne protège pas la suite. |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_only_database_imports_its_writers`, rouge avant le déplacement (3 fichiers), vert après | Plus aucun module hors de `database/` n'atteint `writers/`. |
| `test_the_rule_of_the_writers_refuses_every_way_to_them` (7 cas) | La garde voit chaque forme d'import (absolue, relative, paquet parent) et laisse passer la porte. |
| Deux cas de `test_the_data_api_rule_refuses_etl_and_the_writers`, permis avant l'ajout à `DATA_API_FORBIDDEN_MODULES` ; le cas `from k_b import database` retourné, et `from k_b.database import reading` ajouté | L'API de données ne peut pas importer la porte d'écriture, même par le paquet ; elle lit toujours par `reading.py`. |
| `test_every_package_of_k_b_has_an_empty_init`, rouge quand `writers/__init__.py` contient `import os` | Le test voit un `__init__.py` non vide. |
| `uv run pytest -q` → 1769 passés ; `comm` des tests collectés contre `main` : 2 retirés, 12 ajoutés | Aucun test retiré sans un test plus strict qui le couvre. |
| `mypy --strict` vert ; essai du relecteur : `from k_b.database.writing import paper_writer` refusé | La porte n'expose que des objets. |
| Marche réelle `create-db` + deux `kb import`, branche contre `main` 92658ed (`git archive`) : codes, bilans, journaux, journal d'import et vidage SQL identiques, dates et chemins remplacés | Le comportement n'a pas changé : 14 bruts, 22 items, 10 doublons écartés, 1 CVE retirée. |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas laisser `load.py` choisir l'écrivain ?** Le choix dépend des tables de la base,
   pas du déroulé de l'import. En couches, c'est la base qui sait quelle table reçoit quelle sorte,
   et l'import ne fait qu'orchestrer la transaction et le journal (`conventions.md`, règle 5).
   Voir `writing.py:57-76`.
2. **Qu'est-ce qui empêche quelqu'un de repasser par `writers/` demain ?** Deux contrôles :
   `test_only_database_imports_its_writers` (le test échoue) et `mypy --strict` (un module
   d'écrivain n'est pas exporté par la porte). Voir `test_module_dependencies.py:268-299`.
3. **Pourquoi des alias plutôt que renommer les fonctions ?** L'issue est un déplacement seul : on
   ne change ni comportement ni nom dans les écrivains. L'alias donne un nom lisible à la porte sans
   toucher `writers/` ; le renommage complet vient dans une petite issue juste après celle-ci. Voir
   `writing.py:27-34`.
4. **Que voit l'utilisateur si une sorte n'a pas d'écrivain ?** Le même message qu'avant :
   `KindWithoutTableError: kind without a table in the base: …`, code d'erreur inchangé
   (`test_cli.py:864`). Seul le module de la classe change (`k_b.database.writing`), et dans une
   trace, le cadre de `write_item`.
5. **Pourquoi un `__init__.py` doit-il rester vide ?** Un `__init__.py` qui réexporte crée une porte
   que personne ne voit en lisant le dossier. Ici, chaque porte est un module nommé (`writing.py`,
   `api_router.py`). Voir `test_module_dependencies.py:242-246`.

## Zones non vérifiées

- Le retrait des lignes Zotero (`mark_withdrawn_zotero_rows_not_in`) n'est pas passé dans la marche
  réelle : la fixture Zotero est une base (`zotero_extract.sql`), pas un brut. Il est couvert par les
  tests de `tests/etl/test_load.py`, dont la suite est verte.
- Le refus de mypy pour un module d'écrivain importé par la porte a été essayé par le relecteur du
  plan sur une copie, pas par un test du dépôt. À l'exécution, `writing.py` lie bien chaque module
  d'écrivain (`paper_writer`…) : `from k_b.database.writing import paper_writer` marcherait dans un
  fichier que mypy ne lit pas (`tests/`, un script), et le test des imports ne le voit pas, car
  `database.writing` n'est pas dans `database.writers`. La règle vaut pour `src`, que mypy lit.

## Ce qui reste

- Renommer partout `withdraw_absent…` en `mark_withdrawn…` (écrivains et `load.py`) : une petite
  issue à part, juste après #251 (décision de Sabine du 18/10, 21:20Z).
- Les textes de `.claude/rules/` (`conventions.md` règle 5, `poc.md` règle 7, `code.md`) sont mis à
  jour par Sabine, dans un commit à part de cette PR.
