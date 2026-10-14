# Lire les items en lecture seule par une requête commune

- Date : 2026-10-14
- Branche : `feat/read-items-read-only`
- Issue : #183 (critère corrigé par ses deux commentaires du 2026-10-14)
- Fichiers principaux : `src/k_b/database/connection.py`, `src/k_b/database/reading.py`,
  `src/k_b/items.py`, `tests/fixtures/items_database.sql` (nouveau), `tests/conftest.py`,
  `tests/database/test_connection.py` et `tests/database/test_reading.py` (nouveaux),
  `docs/stockage.md`

Suite de [2026-10-14-sql-d-ecriture-dans-database-writers.md](2026-10-14-sql-d-ecriture-dans-database-writers.md) :
l'écriture vit dans `database/writers/`, la lecture vit dans `database/reading.py` (règle 5 de
`.claude/rules/conventions.md`).

## Le pourquoi

K-B écrit sa veille dans une base SQLite ; jusqu'ici, rien ne la relisait. Trois lecteurs sont
prévus : l'API de données (#184, #185), `kb search` (#187) et « quoi de neuf » (`GET /items?since=`).
Tous posent la même question : « quels items, de quelles sortes, depuis quand, contenant quel
texte, dans quel ordre ? ». La spec (`docs/specs-api.md`, « `GET /items` ») y répond une fois, et
cette PR l'écrit une fois : **une** requête, dans le seul module de lecture, que les trois lecteurs
appelleront sans écrire de SQL.

Deuxième besoin : lire **sans pouvoir écrire**. Un lecteur ne doit ni modifier la base, ni créer un
fichier vide quand la base manque (ce que fait `sqlite3.connect` sur un chemin absent).

Ce travail ne sert encore aucun utilisateur : il prépare #184, #185 et #187.

## Le comment

### 1. Une connexion qui ne peut pas écrire

`src/k_b/database/connection.py:34-41` :

```python
    check_database_exists(database_path)
    connection = sqlite3.connect(
        f"{database_path.absolute().as_uri()}?mode=ro",
        uri=True,
        check_same_thread=False,
    )
```

- `uri=True` fait lire le premier argument comme une URI `file:` ; `?mode=ro` l'ouvre en lecture
  seule, « as though the SQLITE_OPEN_READONLY flag had been passed to sqlite3_open_v2() »
  (SQLite, « URI Filenames »). Une écriture lève alors
  `sqlite3.OperationalError: attempt to write a readonly database` : c'est l'exemple de la
  documentation Python (« How to work with SQLite URIs »), et le test
  `test_a_read_only_connection_cannot_write` (`tests/database/test_connection.py`) le constate.
- `as_uri()` encode les caractères qui ont un sens dans une URI : un dossier `a b#c?d%e` devient
  `file:///…/a%20b%23c%3Fd%25e/…`. La page SQLite « URI Filenames » (§ 3.1) demande de convertir
  chaque `?` en `%3f` et chaque `#` en `%23` : sans cela, un `?` commencerait les paramètres et un
  `#` couperait l'URI. Pour le `%` écrit `%25`, c'est un constat sur `as_uri()` et sur le test du
  dossier `data dir #1 ?%`, pas une phrase lue dans la doc SQLite. `as_uri()` refuse un chemin
  relatif (`ValueError: relative path can't be expressed as a file URI`) : d'où `absolute()`, car
  `KB_DATA_DIR` peut être relatif.
- `check_database_exists` passe d'abord. En lecture seule, SQLite ne crée pas la base : « If the
  database does not already exist, an error is returned » (SQLite, `sqlite3_open_v2`, à propos de
  `SQLITE_OPEN_READONLY`). Mais c'est une erreur générique (« unable to open database file »), qui
  ne se distingue pas d'une autre. `MissingDatabaseError` est l'état nommé que l'API traduira en
  503 `database_missing`. Elle quitte `etl/load.py` pour
  `database/connection.py`, car un lecteur ne doit pas importer l'ETL (règle 5).

**Ce que `mode=ro` écrit quand même.** Une base en mode WAL a deux fichiers voisins : `-wal` (le
journal des écritures) et `-shm` (l'index partagé du journal, un fichier projeté en mémoire). La
documentation SQLite (WAL, § 5) dit qu'une base WAL sans droit d'écriture se lit si « The -shm and
-wal files already exist and are readable », ou s'il y a « write permission on the directory
containing the database so that the -shm and -wal files can be created ». Constaté le 2026-10-14
(SQLite 3.50.4) : sur une base fermée proprement, une lecture en `mode=ro` crée `-shm`
(32 768 octets) et `-wal` (vide), et les laisse à sa fermeture. « Lecture seule » protège donc le
contenu de la base, pas le dossier : celui-ci doit rester accessible en écriture. C'est écrit dans
`docs/stockage.md`, « Lecture seule ».

### 2. Une requête, six branches réunies par `UNION ALL`

Un item n'a que son `id`, sa sorte et son brut (`item`) ; son titre, sa date et son URL sont dans
la table de sa sorte (`publication`, `vulnerability`, `release`…). Pour lister toutes les sortes
ensemble, chaque branche ramène les mêmes six colonnes, sous les mêmes noms, depuis sa table.
`src/k_b/database/reading.py:43-48`, la branche des releases :

```sql
    SELECT item.id, item.kind, item.raw_data_id,
        tracked_repository.repository_name || ' '
            || coalesce(nullif(release.name, ''), release.tag_name),
        release.body, release.published_at, release.url, NULL
    FROM item JOIN release ON release.item_id = item.id
        JOIN tracked_repository ON tracked_repository.id = release.tracked_repository_id
```

- Le titre d'une release est `<dépôt> <nom ou tag>` (spec) : `nullif(name, '')` change un nom vide
  en `NULL`, puis `coalesce` prend le tag quand le nom est `NULL`. Ainsi `GET /items?q=<dépôt>`
  trouve les releases d'un dépôt (parcours P2).
- `UNION ALL` et non `UNION` : `UNION` retirerait les doublons, ce qui coûte un tri et n'a pas de
  sens ici (un `item.id` n'apparaît que dans une branche).
- Les noms de colonnes sont ceux de la **première** branche (`AS title`, `AS source_date`…) : SQL
  les donne au résultat entier.
- Une sorte sans résumé (alerte, entrée Zotero) met `NULL` : `q` ne cherche alors que dans son titre.
- Le papier et la CVE n'ont pas d'URL en base : la branche la compose, `:arxiv_page_url ||
  publication.arxiv_id`. Le préfixe vient d'`items.py`, le seul endroit où il est écrit
  (`ARXIV_ABSTRACT_PAGE_URL`, `NVD_PAGE_URL`), que les sources arXiv et CISA lisent aussi.

Les filtres et le tri s'appliquent au résultat réuni (`reading.py:64-70`) : on lit d'abord
« une liste d'items de forme unique », puis on la filtre.

### 3. Tous les filtres sont des paramètres liés

```sql
WHERE (:kinds IS NULL OR listed.kind IN (SELECT value FROM json_each(:kinds)))
    AND (:since IS NULL OR listed.source_date >= :since)
```

(`reading.py:64-65`). La requête est une **chaîne constante** : aucune valeur de l'appelant n'entre
dans le texte SQL. Chaque `:nom` est un paramètre lié : `sqlite3` envoie la valeur à part, et
SQLite la lit comme une donnée, jamais comme du SQL. C'est ce qui ferme l'injection SQL.

- **Filtre facultatif** : `(:since IS NULL OR …)`. Sans `since`, le paramètre vaut `None`, la
  condition est vraie pour chaque ligne. Une seule requête sert tous les cas.
- **`kind` répétable** : le nombre de sortes varie (0 à 6). Au lieu d'écrire `IN (?, ?, ?)` selon
  ce nombre (du SQL construit à l'appel), la liste est envoyée comme **un** texte JSON
  (`json.dumps(["paper", "release"])`), que `json_each` déplie en lignes. Une chaîne hostile reste
  une valeur JSON.
- **`since`** est converti en UTC, puis écrit au format de la base (`AAAA-MM-JJTHH:MM:SSZ`) et
  comparé comme texte : ce format garde l'ordre du texte égal à l'ordre du temps
  (`database/dates.py`). `reading.py:171-179` refuse une date sans fuseau, arrondit à la seconde
  supérieure (la base est à la seconde : `since=10:00:00.5` ne doit pas prendre un item de
  `10:00:00`), et écrit par `isoformat`, qui garde l'année sur 4 chiffres.
- **`limit` et `offset`** sont liés aussi. `check_within_bounds` (`reading.py:154-160`) refuse
  `limit < 1` (SQLite lit `LIMIT -1` comme « sans limite ») et les valeurs hors 64 bits, en nommant
  la borne franchie, jamais la valeur reçue.

### 4. `LIKE … ESCAPE` : chercher `%` et `_` tels quels

Dans `LIKE`, `%` veut dire « n'importe quelle suite » et `_` « n'importe quel caractère ». Un
utilisateur qui cherche `v2_1` ne veut pas trouver `v2.1`. `reading.py:189-190` :

```python
    escaped = search_text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
```

et la requête dit `LIKE :pattern ESCAPE '\'` : un `\` devant `%` ou `_` en fait un caractère
ordinaire. C'est la règle de SQLite (« SQL Language Expressions », opérateur `LIKE`) :
l'expression après `ESCAPE` « must evaluate to a string consisting of a single character », et ce
caractère, placé devant `%` ou `_`, les fait chercher tels quels. L'ordre compte : `\` est doublé
**en premier**, sinon les `\` ajoutés devant `%` seraient doublés à leur tour. Les `%` autour
cherchent le texte n'importe où.

Deux pièges relevés par la revue :
- la requête est une chaîne Python **brute** (`r"""…"""`, `reading.py:30`) : dans une chaîne
  ordinaire, `'\'` deviendrait `'` et SQLite recevrait `ESCAPE ''`, une chaîne qui n'a pas un seul
  caractère ;
- un NUL dans le texte cherché : la documentation SQLite (`sqlite3_bind_text`) dit qu'une valeur
  liée peut contenir un NUL et que « The result of expressions involving strings with embedded NULs
  is undefined ». Aucune page ne décrit `LIKE` en particulier. Le cas observé le 2026-10-14 : le
  motif était coupé au NUL, `q="\x00"` devenait `%` et trouvait les 16 items de la base d'essai.
  `check_text_can_be_stored` (`items.py`, la règle de tout texte stocké) refuse le NUL, et aussi le
  surrogate isolé, que `sqlite3` ne sait pas envoyer.

`LIKE` ignore la casse pour les lettres ASCII seulement : « SQLite only understands upper/lower
case for ASCII characters by default » (même page). `vulnerabilite` ne trouve donc pas
« Vulnérabilité ». C'est une limite écrite dans la spec, levée par FTS5 (#188).

### 5. La page suivante, dans la même requête

`reading.py:144-151` : la requête demande `limit + 1` lignes. S'il en vient plus que `limit`, une
page suivante existe, et `next_offset = offset + limit` ; sinon `None`. Un seul aller-retour, et
l'appelant reçoit une page finie (`ItemPage`).

### 6. Une base d'essai écrite à la main, ligne par ligne

`tests/fixtures/items_database.sql` remplit une base créée par `create_database` (le vrai schéma,
avec ses `CHECK` et ses clés étrangères), une fois par session de tests (`tests/conftest.py`). Chaque
ligne reprend un extrait de collecte (`tests/fixtures/*_extract.*`) ; chaque **variante** (un nom
de release différent du tag, nul, vide ; une ligne retirée ; une entrée Zotero sans URL) est
commentée avec le test qui en a besoin. Le dossier de la base s'appelle `data dir #1 ?%` : le test
de l'URI lit cette base-là.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Une requête `UNION ALL` constante | spec et critère : une requête pour tous les lecteurs ; aucune valeur dans le SQL | une requête par sorte (le tri et la pagination communs se feraient en Python) ; ne garder que les branches demandées (SQL construit à l'appel) |
| `kind` par `json_each(:kinds)` | la requête reste une constante (précédent : `vulnerability_writer.py`) | `IN (?, ?, …)` selon le nombre de sortes |
| `next_offset` dans la lecture, par `limit + 1` | une requête ; #184 et #187 reçoivent une page finie | un `count(*)` à part (deux requêtes, qu'un import intercalé désaccorde) ; le calcul dans la route |
| `since` sans fuseau refusé, arrondi à la seconde supérieure, écrit par `isoformat` | la base est à la seconde ; une date naïve serait lue comme l'heure locale, en silence ; `isoformat` garde l'année sur 4 chiffres | `dates.format_date` (passe par `strftime`) ; comparer par `datetime()` en SQL (un appel par ligne, alors que les `CHECK` garantissent déjà le format) |
| `check_same_thread=False` | exigé par le critère : l'API ouvre une connexion par requête dans une dépendance | le réglage par défaut (garde-fou de `sqlite3` contre l'usage d'une connexion par un autre fil) |
| `PRAGMA foreign_keys = ON` aussi en lecture seule | la règle « toute connexion » (`schema.sql:6`, `docs/stockage.md`) | le retirer (la relecture le dit sans effet sur une connexion qui n'écrit pas) : garder la règle sans exception, pour une instruction par ouverture |
| Paramètres nommés, `limit` sans défaut, `kinds` vide = toutes les sortes | sept paramètres ; le défaut 20 est celui de l'API ; FastAPI rend une liste vide pour un paramètre absent | `None` = toutes et vide = rien (une liste vide ne rendrait jamais rien) |
| `NamedTuple` (`ListedItem`, `ItemPage`, `StoredHighlight`) | comme `ImportSummary` ; rien à valider en sortie de la base | Pydantic : l'API aura ses propres modèles de réponse (spec) |
| `SearchableMode` dans `items.py` | règle 4 : un type qui sert à plus d'un module (`reading.py`, `cli.py` avec #187) | dans `reading.py` (#187 aurait dû le déplacer) |
| Surlignages triés par `highlighted_at`, puis `highlight_id` | l'ordre de création s'énonce sans exception | `highlight_id` seul (l'ordre du PDF à la première importation, mais un surlignage ajouté plus tard passe en dernier, quelle que soit sa page) |
| Base d'essai par `INSERT` écrits à la main | chaque cas visible et commenté, les `CHECK` refusent une ligne impossible | la base par l'import réel des extraits : les tests de lecture dépendraient de tout l'ETL, et les variantes demanderaient des extraits modifiés de toute façon |
| Pas de borne de longueur sur `q` dans la lecture | l'API borne `q` à 200 caractères ; une seconde borne dupliquerait cette règle | borner ici ; reporté à `kb search` (#187) |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_read_only_connection_cannot_write` | une écriture lève `OperationalError` « readonly » |
| `test_a_missing_database_is_refused_and_not_created` | base absente → `MissingDatabaseError`, aucun fichier créé |
| `test_a_relative_database_path_is_read` | `absolute()` permet un chemin relatif |
| `test_a_base_in_a_folder_named_with_characters_a_uri_escapes_is_read` | l'URI encode l'espace, `#`, `?` et `%` |
| `test_an_item_of_each_kind_has_its_title_url_and_date`, `test_a_release_without_a_name_is_titled_by_its_tag` | titre, URL et date de chaque sorte ; titre de release avec nom, sans nom, nom vide |
| `test_each_kind_has_its_branch`, `test_without_a_kind_every_kind_is_read` | chaque `ItemKind` a sa branche |
| `test_since_is_converted_to_utc_before_the_comparison` | `since` en `+02:00` est converti en UTC (sans conversion, la release 6 disparaît) |
| `test_a_percent_or_an_underscore_is_searched_as_written` | `%` et `_` ne sont pas des jokers |
| `test_a_search_with_a_nul_or_a_lone_surrogate_is_refused` | `q` avec NUL ou surrogate → `ValueError` |
| `test_the_items_are_sorted_by_date_then_by_id_descending`, `test_the_last_page_has_no_next_offset` | tri et pagination, y compris quand il reste exactement `limit` items |
| `test_the_withdrawn_rows_are_listed_with_their_date`, `test_the_highlights_of_an_entry_withdrawn_ones_included` | les retraits sont rendus, avec leur date |
| Sondes du 2026-10-14 : le code cassé exprès (sans conversion UTC, tag seul, sans `nullif`, sans échappement, `>=` au lieu de `>`, `id` croissant) | chaque sonde fait échouer au moins un test |
| `uv run pytest` : 1 049 tests verts ; `ruff check`, `ruff format --check`, `mypy --strict` verts | |

## Ce que tu dois pouvoir défendre

1. **Où est la protection contre l'injection SQL ?** Le texte de la requête est constant
   (`reading.py:30-71`) ; toute valeur passe par un paramètre lié, `kinds` compris (un seul texte
   JSON). Aucune valeur de l'appelant n'est collée dans le SQL.
2. **Pourquoi `ESCAPE` et une chaîne brute ?** Sans échappement, `_` et `%` reçus seraient des
   jokers : `q=v2_1` trouverait `v2.1`. La chaîne brute garantit que SQLite reçoit `ESCAPE '\'`
   (`reading.py:29-30`, `189`).
3. **« Lecture seule », vraiment ?** Le contenu, oui (`mode=ro`, test d'écriture refusée). Le
   dossier, non : la lecture crée `-shm` et `-wal` s'ils manquent (doc SQLite WAL § 5, constat sur
   3.50.4). La base et son dossier doivent rester accessibles en écriture.
4. **Pourquoi une requête unique plutôt que six ?** Le tri par date et la pagination portent sur
   toutes les sortes à la fois : six requêtes demanderaient de fusionner et de paginer en Python.
   La spec veut une seule requête partagée par l'API, `kb search` et « quoi de neuf ».
5. **Que se passe-t-il avec `since=2026-10-07T00:00:00+02:00` ?** Converti en
   `2026-10-06T22:00:00Z`, il prend les articles du 2026-10-07 (écrits à minuit UTC) et pas ceux
   du 2026-10-05 (`test_since_takes_the_day_of_its_time_zone`).

## Zones non vérifiées

- Le `%` d'un chemin écrit `%25` dans l'URI : constaté sur `as_uri()` et par le test du dossier
  `data dir #1 ?%`. La page « URI Filenames » ne l'a pas confirmé dans la recherche du 2026-10-14
  (un fil du forum SQLite de 2026 dit qu'elle devrait le dire).
- Le texte de l'erreur d'un motif `LIKE` trop long (« LIKE or GLOB pattern too complex ») : rapporté
  par la troisième revue. La limite elle-même est sourcée : 50 000 octets par défaut
  (`SQLITE_MAX_LIKE_PATTERN_LENGTH`, « Implementation Limits For SQLite »).
- La phrase « The use of NUL characters in SQL text strings is not recommended », que l'on attribue
  à la page « NUL Characters In Strings » : la recherche du 2026-10-14 ne l'a trouvée que citée dans
  un fil du forum. Elle n'est pas reprise ici ; le refus du NUL s'appuie sur `sqlite3_bind_text`.
- Le coût de la requête : la première revue rapporte un parcours des six sous-types à chaque appel,
  un index automatique et un tri temporaire (plan `EXPLAIN` relevé par elle). Non mesuré ici ;
  jugé sans enjeu à quelques milliers d'items par an.
- `-shm` et `-wal` : constatés sur macOS seulement, pas sur Linux (la CI).
- La largeur de l'année écrite par `strftime` hors macOS : `isoformat` évite la question pour
  `since`, mais `dates.format_date` (les écrivains) n'a pas été vérifié sous glibc.

## Ce qui reste

- L'API de données (#184 la liste, #185 le détail et les surlignages) et `kb search` (#187)
  appelleront cette lecture ; ils valident leurs paramètres (bornes de la spec) avant.
- `--source` (filtre par source) : à `kb search` (#187), qui étendra la lecture ; la borne de
  longueur de son texte de recherche aussi.
- Signalé, sans issue : le coût de la requête à chaque page ; `dates.format_date` par `strftime` ;
  un nom de release fait d'espaces (gardé à l'import comme à la lecture) ; `next_offset` au-delà de
  10 000, borne d'`offset` de l'API ; une requête de surlignages par entrée dans `kb search` ; la
  règle « dépôt + nom ou tag » écrite deux fois (`github_releases.py` et la requête).

## Sources

Consultées le 2026-10-14 ; chacune fonde un point de la note.

- [Write-Ahead Logging](https://www.sqlite.org/wal.html), § 5 « Read-Only Databases » — SQLite
  (page mise à jour le 2026-08-25) : les conditions de lecture d'une base WAL sans droit
  d'écriture, donc ce que la lecture seule écrit encore (`docs/stockage.md`).
- [SQL Language Expressions](https://www.sqlite.org/lang_expr.html), opérateur `LIKE` — SQLite :
  le caractère d'`ESCAPE` est un seul caractère, devant `%` ou `_` il les fait chercher tels quels ;
  la casse n'est ignorée que pour l'ASCII.
- [Binding Values To Prepared Statements](https://www.sqlite.org/c3ref/bind_blob.html) — SQLite :
  une expression sur un texte qui contient un NUL a un résultat indéfini (refus du NUL dans `q`).
- [URI Filenames In SQLite](https://www.sqlite.org/uri.html), § 3.1 — SQLite : `?` s'écrit `%3f` et
  `#` `%23` dans le chemin ; `mode=ro` vaut `SQLITE_OPEN_READONLY`.
- [Opening A New Database Connection](https://www.sqlite.org/c3ref/open.html) — SQLite : en
  lecture seule, une base absente donne une erreur, sans être créée (`check_database_exists` en fait
  un état nommé).
- [sqlite3 — How to work with SQLite URIs](https://docs.python.org/3/library/sqlite3.html) —
  Python : `connect("file:…?mode=ro", uri=True)` ; une écriture lève
  `OperationalError: attempt to write a readonly database`.
- [Implementation Limits For SQLite](https://www.sqlite.org/limits.html) — SQLite : un motif `LIKE`
  est limité à 50 000 octets par défaut (borne de `q` laissée à l'API et à `kb search`).
