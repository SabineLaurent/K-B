# Lire un dossier de pages brutes dans la transformation générique

- Date : 2026-10-06
- Branche : `feat/read-page-folders`
- Issue : #101 (plan ETL, étape 5 : `docs/2026-10-06-plan-etl.md`)
- Fichiers : `src/k_b/raw_items.py`, `tests/test_raw_items.py`
- Série : suite de [une seule liste des sources](2026-10-06-une-seule-liste-des-sources.md)
  (#99, qui a donné `SourceKind` et le lecteur par sorte)

## Le pourquoi

La collecte (E) écrit le brut de deux façons. Une source d'API écrit **un fichier** par collecte :
`automation/arxiv/2026-10-05T093000Z.xml`. Une source qui lit plusieurs pages (TLDR) écrit **un
dossier** par collecte, une page par fichier : `automation/tldr_ai/2026-10-05T093000Z/2026-10-04.html`
(`src/k_b/collect.py:69-83`).

La transformation générique (T, `read_raw_items`) ne savait lire que la première forme : elle
journalisait les dossiers « folder of pages without a reader » et les sautait. Sans ce travail, le
lecteur TLDR (#57) n'aurait aucun moyen d'entrer dans la chaîne. Cette PR ne lit pas TLDR : elle
rend la partie générique capable de lire un dossier, et le prouve avec une sorte factice. TLDR
reste sauté (« source without a reader ») jusqu'à #57.

## Le comment

### 1. L'unité de lecture est la collecte, pas le fichier

`list_collections` renvoie chaque entrée visible d'un dossier de source, fichier ou dossier, avec
le lecteur de sa sorte :

```python
        collections.extend((path, reader) for path in list_visible_entries(source_dir))
```
(`src/k_b/raw_items.py:120`)

Avant, la même boucle sautait les dossiers. Maintenant elle les garde : décider « fichier ou
dossier » revient à `read_collection`, une seule fois par collecte.

### 2. La date vient du nom de la collecte

```python
        if collection_path.is_dir():
            # A folder name is taken whole: a file name without its extension.
            collected_at = parse_collection_name(collection_path.name)
            pages = list_pages(collection_path, raw_dir)
        else:
            collected_at = parse_collection_name(collection_path.stem)
            pages = [collection_path]
```
(`src/k_b/raw_items.py:53-59`)

Un fichier perd son extension (`.stem`), un dossier n'en a pas : son nom est pris entier (`.name`).
Avec `.stem`, un dossier `2026-10-05T093000Z.old` serait lu comme `2026-10-05T093000Z` et accepté ;
avec `.name`, il est rejeté. Un fichier seul devient une collecte d'une page : la suite du code ne
connaît plus que des pages.

### 3. Un rejet au bon niveau

Trois niveaux d'échec, trois portées de rejet :

- la **collecte** : nom qui n'est pas une date, ou dossier qu'on ne peut pas lister →
  un seul rejet, au chemin de la collecte (`src/k_b/raw_items.py:60-64`) ;
- la **page** : illisible (`OSError`), ou que le lecteur refuse (`ValueError`, `csv.Error`) → un
  rejet au chemin de la page, les autres pages sont lues (`src/k_b/raw_items.py:84-89`) ;
- l'**entrée** : refusée comme item par Pydantic → un rejet « entry n », les autres entrées sont
  lues (`src/k_b/raw_items.py:92-101`).

Le `try` qui entoure la liste des pages (`:52-60`) a été ajouté après la revue : sans lui, un
dossier sans droit de lecture levait `PermissionError` et arrêtait tout l'import.

### 4. Ce qui est sauté dans un dossier de pages

```python
    for path in list_visible_entries(collection_dir):
        if path.is_dir():
            logger.info(
                "folder inside a collection folder, skipped: %s",
                path.relative_to(raw_dir).as_posix(),
            )
            continue
```
(`src/k_b/raw_items.py:127-133`)

`list_visible_entries` (`:138-141`) écarte les noms qui commencent par un point (`.DS_Store` de
macOS) et trie par nom. Elle sert aux deux niveaux, dossier de source et dossier de collecte :
« un fichier caché n'est pas du brut » est une connaissance, écrite une fois. Un sous-dossier n'est
pas une page : il est journalisé (ce qui est observé, son chemin), pas rejeté, puisque la collecte
n'en écrit jamais.

### 5. L'ordre des items

```python
    # Stable sort: within a collection, the items keep their page and source order.
    items.sort(key=lambda item: item.collected_at)
```
(`src/k_b/raw_items.py:44-45`)

Le tri de Python est stable : à date de collecte égale, l'ordre d'arrivée est gardé. Les pages
arrivent triées par nom (donc par date de page pour TLDR), et les entrées dans l'ordre de leur page.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Option écartée, et pourquoi |
|---|---|---|
| La collecte comme unité (`read_collection`) | Un dossier mal nommé donne **un** rejet : le critère dit « rejeté entier » | Aplatir les dossiers en pages dès la liste, date lue dans `page.parent.name` : un dossier mal nommé donnerait un rejet par page |
| `raw_file_path` = chemin de la page | Imposé par le critère de #101 ; un rejet pointe la page fautive | Chemin du dossier : on ne saurait plus quelle page a donné quel item |
| Fonctions qui **renvoient** un `RawReading` (`read_collection`, `read_page`) | Le flux de données se lit dans l'appelant ; chaque fonction est testable seule | Remplir un `RawReading` passé en paramètre (première version) : la revue a relevé que la mutation cachait le flux |
| Fichier caché sauté sans journal, sous-dossier journalisé | Un `.DS_Store` est attendu et sans intérêt ; un sous-dossier est un état anormal qu'un humain doit voir | Rejeter le sous-dossier : il n'est pas une donnée mal formée, juste hors de la forme prévue |
| Une sorte factice dans les tests | Imposé par le critère ; le lecteur TLDR est #57 | Tester avec TLDR : hors périmètre, et il n'a pas encore de lecteur |

**Conséquence en base, voulue** : `import_items.write_collection` écrit une ligne `collection` par
`raw_file_path`, qui est `UNIQUE` (`src/k_b/database/schema.sql:19`). Une collecte TLDR de 7 pages
donnera donc **7 lignes** `collection`, toutes à la même `collected_at`. `docs/stockage.md:235`
décrit la table par ses colonnes sans dire « une par collecte » ; la ligne correspond désormais à
un fichier brut lu.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_folder_of_pages_is_read_page_by_page` (`tests/test_raw_items.py:254`) | Pages écrites hors ordre, lues par nom ; date = nom du dossier ; `raw_file_path` = chemin de la page |
| `test_a_hidden_file_in_a_folder_of_pages_is_skipped` (`:276`) | Un `.DS_Store` aux lignes valides ne donne rien |
| `test_a_folder_inside_a_folder_of_pages_is_skipped_and_logged` (`:287`) | Le sous-dossier, qui contient une page valide, ne donne rien et son chemin est journalisé |
| `test_a_folder_of_pages_not_named_by_a_collection_time_is_rejected_whole` (`:303`) | Deux pages, un seul rejet au chemin du dossier, raison `ValueError: time data 'latest'…` |
| `test_an_unreadable_page_is_rejected_and_the_others_of_its_folder_are_read` (`:317`) | Une page non UTF-8 rejetée seule ; la voisine lue |
| `test_an_unreadable_folder_of_pages_is_rejected_and_the_others_are_read` (`:337`) | Un dossier en `chmod 0` : un rejet `PermissionError`, l'autre collecte lue |
| `test_a_source_without_reader_is_skipped_and_logged` (`:147`, renommé) | TLDR reste sauté tant qu'il n'a pas de lecteur |
| `uv run pytest` : 313 passed ; `ruff check`, `ruff format --check`, `mypy --strict` verts | Pas de régression sur les fichiers seuls ; complexité sous C90 = 10 |

## Ce que tu dois pouvoir défendre

1. **Pourquoi un dossier mal nommé est-il rejeté entier, et pas page par page ?** La date de toutes
   ses pages vient de ce nom : s'il est faux, aucune page n'a de date. Un rejet par page dirait N
   fois la même chose. Code : `src/k_b/raw_items.py:60-64`.
2. **Que se passe-t-il si une page sur sept est illisible ?** Elle est rejetée avec son chemin, les
   six autres donnent leurs items. Code : `:84-89` ; test `:317`.
3. **Où est la sécurité ?** Aucun chemin n'est construit à partir du contenu collecté : on ne lit que
   ce que `iterdir` trouve sous `raw/`. Les noms de pages sont contrôlés à l'écriture
   (`collect.py:21`, `[a-z0-9_-]+`). Le contenu reste une donnée non fiable, validée par Pydantic
   dans `convert`. La revue de sécurité n'a relevé aucune vulnérabilité.
4. **Pourquoi `.name` pour un dossier et `.stem` pour un fichier ?** `.stem` retire ce qui suit le
   dernier point : pour un dossier, il accepterait `2026-10-05T093000Z.old`. Code : `:53-59`.
5. **Pourquoi 7 lignes `collection` pour une collecte TLDR ?** Le critère veut `raw_file_path` égal
   au chemin de la page, et la table a une ligne par `raw_file_path` unique. Chaque item garde ainsi
   la trace exacte de la page qui l'a donné.

## Zones non vérifiées

- Le test du dossier illisible repose sur `chmod 0` : il suppose que les tests ne tournent pas en
  `root` (qui lit tout). Vérifié en local (macOS) ; en CI, à confirmer sur la PR.
- Le comportement sur un lien symbolique dans un dossier de pages n'est pas testé (suivi, comme
  pour un fichier seul avant cette PR).
- mypy ne vérifie pas les tests (`pyproject.toml:42`, `files = ["src"]`) : la sorte factice n'est
  pas contrôlée par lui.

## Ce qui reste

- **Le lecteur TLDR** : #57.
- **Constats de revue laissés, hors périmètre** :
  - un rejet de dossier porte un chemin de dossier dans un champ nommé `raw_file_path` ; le renommer
    toucherait `import_items` et le journal d'import ;
  - le format du nom de collecte vit à deux endroits (`collect.py:69` l'écrit, `raw_items.py:18`
    le lit), avant cette PR déjà ;
  - si un même article figure dans deux pages d'une collecte, la fusion garde le premier vu
    (`merge.py:33`), donc celui de la page au nom le plus petit : à trancher avec #57.
- **Collecte partielle ou vide, fichier temporaire laissé par une écriture interrompue** : #112.
