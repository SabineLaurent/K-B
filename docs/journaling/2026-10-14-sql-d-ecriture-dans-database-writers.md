# Déplacer le SQL d'écriture dans `database/writers/`

- Date : 2026-10-14
- Branche : `refactor/write-sql-in-database-writers`
- Issue : #135
- Fichiers principaux : `src/k_b/database/writers/` (nouveau), `src/k_b/database/dates.py`
  (nouveau), `src/k_b/etl/import_log.py` (nouveau), `src/k_b/etl/load.py`,
  `tests/test_module_dependencies.py`, `tests/database/test_writers.py` et
  `tests/etl/test_import_log.py` (nouveaux),
  `.claude/rules/conventions.md` (règle 5)

Suite de [2026-10-13-ranger-le-parcours-dans-etl.md](2026-10-13-ranger-le-parcours-dans-etl.md),
qui a rangé le parcours dans `etl/` et laissé le SQL d'écriture dans `etl/load.py`.

## Le pourquoi

K-B est rangé en couches : la présentation (`cli.py`), le métier (`etl/`), l'accès aux données
(`database/`). Une couche n'appelle que celle du dessous. `etl/load.py` faisait deux métiers :
décider dans quel ordre et dans quelle transaction on écrit, et écrire, avec 1 083 lignes dont
tout le SQL d'écriture de la base. C'était le seul fichier hors de `database/` que renvoyait la
commande de vérification de la règle 5.

Ce travail est un **déplacement** : `kb import` écrit la même base et le même journal qu'avant.
Il prépare l'issue suivante, qui enveloppera chaque écrivain dans un `SAVEPOINT`.

## Le comment

### 1. Un écrivain par sorte d'item, tous de la même forme

`src/k_b/etl/load.py:298`

```python
WRITER_BY_KIND: dict[str, Callable[[sqlite3.Connection, Item, int], Discard | None]] = {
    "paper": paper_writer.write,
    "vulnerability": vulnerability_writer.write,
    "release": release_writer.write,
```

Chaque module de `database/writers/` porte le SQL d'une sorte d'item et une fonction `write`,
qui reçoit la connexion, l'item et l'identifiant du fichier brut, et rend `None` si l'item est
écrit, ou un `Discard` (la règle et la date comparée) si la base l'a laissé de côté. `load.py`
garde la table « sorte → écrivain » : c'est lui qui choisit, l'écrivain ne connaît que sa sorte.
Le classement GH Archive a son écrivain aussi (`trend_writer.py`), sans être un item.

### 2. Un écrivain ne reçoit que des valeurs simples

`src/k_b/etl/load.py:229`

```python
def register_raw_file(connection: sqlite3.Connection, raw_file: RawFile) -> int:
    """Register the file read under its stream, the name of its source folder."""
    return shared_rows.write_raw_data(
        connection,
        raw_file.source_code,
        raw_file.raw_file_path,
        find_stream(raw_file.raw_file_path),
        raw_file.collected_at,
    )
```

`RawFile` et `find_stream` appartiennent à `etl/`. Si un écrivain les recevait, `database/`
importerait `etl/` : la couche du dessous dépendrait de celle du dessus. `load.py` ouvre donc le
`RawFile` et passe ses valeurs une à une. Pour la même raison, `Discard` est défini dans
`database/writers/discard.py` (les écrivains le rendent), et `TrendDiscard`, qui contient un
`RawFile`, dans `etl/import_log.py`.

### 3. La garde reste dans `load.py`, l'écrivain se protège aussi

`src/k_b/etl/load.py:269` puis `src/k_b/database/writers/vulnerability_writer.py:110`

```python
    if not present_cve_ids or raw_file.rejection_count:
        return 0
```

```python
    if not present_cve_ids:
        return 0
```

Un catalogue (CISA KEV, Zotero) retire de la base ce qu'il ne liste plus. La règle « un
catalogue avec un rejet ne retire rien » a besoin du `RawFile` : elle reste dans `load.py`. La
première revue a relevé que la moitié SQL, une fois séparée, retirait toutes les lignes si on
l'appelait avec une liste vide. Aucun appelant ne le fait, mais chaque écrivain refuse
maintenant la liste vide lui-même (défense en profondeur, `code.md`).

### 4. Un test garde le sens des dépendances

`tests/test_module_dependencies.py:212`

```python
def test_database_imports_only_items_and_core():
    allowed = {"database", "items", "core"}
    for path in list_python_files("database"):
```

Ce test existait, mais `list_python_files` ne lisait pas les sous-dossiers : `writers/` lui
aurait échappé. Il les lit maintenant (`rglob`, ligne 96), et un second test (ligne 195) prouve
qu'un module de `writers/` est bien dans la liste.

## Choix faits et options écartées

- **Un dossier `writers/`, un module par sorte** (décision de Sabine du 2026-10-13). Écarté : un
  seul module d'écriture, sept écrivains dans un fichier.
- **Deux commits, déplacer puis renommer** (critère de l'issue) : le premier se relit comme un
  déplacement, le second comme une liste de noms. `write_paper` devient `paper_writer.write`
  (`code.md` : un nom ne répète pas son module).
- **`UnknownSourceError` dans `shared_rows.py`**, à côté de la seule fonction qui la lève
  (décision de Sabine). Écarté : un module `database/errors.py` pour une classe. Conséquence :
  `cli.py` importe `database/writers`.
- **`ImportLogExistsError` et `check_log_absent` restent dans `load.py`** : la vérification fait
  partie de l'ordre de la transaction. Les lignes du journal, elles, vont dans `import_log.py`.
- **La règle d'une fenêtre de classement écartée est dans `trend_writer.py`**
  (`DISCARD_RULE`), à côté de son SQL. Écarté après la première revue : la laisser dans
  `import_log.py`.
- **Les deux retraits gardent des signatures différentes** : les rapprocher aurait réécrit un
  bloc au lieu de le déplacer.
- **Pas de test par écrivain** : les tests d'import les exercent tous par `import_items`.
  Seuls les deux refus de la liste vide ont leur test, parce que l'import ne peut pas les
  atteindre.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run pytest` : 997 tests passent, les assertions des tests d'import inchangées | la base et le journal écrits sont les mêmes |
| `grep -c "execute" src/k_b/etl/load.py` renvoie 0 (34 avant) | `load.py` n'écrit plus en base |
| `grep -rlE "INSERT INTO\|SELECT \|UPDATE \|DELETE FROM" src/k_b --include='*.py' --exclude=zotero.py --exclude=gh_archive.py` ne renvoie que des fichiers de `src/k_b/database/` | la règle 5 est tenue |
| Comparaison des textes SQL de l'ancien `load.py` et des nouveaux modules : tous retrouvés à l'identique | aucune requête n'a changé |
| Un import de `k_b.etl` ajouté à la main dans `discard.py` fait échouer `test_database_imports_only_items_and_core`, puis est retiré | le test voit `writers/` |
| `tests/database/test_writers.py` : rouges avant la garde (1 ligne retirée pour CISA KEV, 2 pour Zotero), verts après | un retrait sans liste ne retire rien |
| `tests/etl/test_import_log.py` : rouge avec une clé retirée à la main, vert une fois remise | chaque règle d'écart a son champ au journal, bien que la table et les règles soient dans deux couches |

## Ce que tu dois pouvoir défendre

- **Pourquoi le SQL va-t-il dans `database/` ?** Pour que le métier (`etl/`) ne dépende pas de
  la forme des tables, et qu'une API à venir lise la base sans importer le pipeline
  (`.claude/rules/conventions.md`, règle 5).
- **Pourquoi un module par sorte, et pas un seul ?** Chaque sorte a sa règle de dédoublonnage
  dans son SQL (flux d'actualité, catalogue d'état, flux à révisions) : on la lit dans un
  fichier qui porte son nom. Ce qu'ils partagent est écrit une fois (`catalog.py`,
  `shared_rows.py`).
- **Que reste-t-il dans `load.py`, et pourquoi ?** L'ordre, la transaction, le choix de
  l'écrivain, les gardes de retrait et le moment où le journal s'écrit : ce sont des décisions
  du parcours, pas de la base (`src/k_b/etl/load.py:100`, `import_items`).
- **Comment sait-on que rien n'a changé ?** Les textes SQL sont identiques, les assertions des
  tests d'import n'ont pas bougé, et deux revues indépendantes ont relu le code déplacé face à
  l'ancien.
- **Qu'est-ce qui a changé quand même ?** Une chose : `find_stream` est appelé avant la
  recherche de la source. Pour un brut de source inconnue dont le chemin a moins de trois
  parties, l'erreur devient `ValueError` au lieu de `UnknownSourceError`. La lecture des bruts
  ne produit pas un tel chemin (`src/k_b/etl/transform.py:163-167`).

## Zones non vérifiées

- Le comportement sur une base réelle : seules les bases temporaires des tests ont été écrites.
- Le cas `ValueError` ci-dessus : lu dans le code, non exécuté.
- Aucune comparaison table par table entre `main` et la branche sur les mêmes bruts :
  l'équivalence repose sur les tests d'import.

## Ce qui reste

- `import_items()` n'est pas réécrite : l'issue #136 rouvre sa boucle pour écrire chaque item
  dans un `SAVEPOINT`.
- Deux tables sont écrites depuis deux modules (la CVE citée par une alerte, la publication
  citée par une entrée Zotero) : déplacé tel quel, sans issue.
- Rien ne limite encore qui importe `database/writers` ; la ligne de test de l'API s'ajoutera à
  la création de son paquet (règle 5).
