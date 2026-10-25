# Conventions d'architecture — K-B

Une règle par famille, décidée par Sabine le 2026-10-11 (revue d'homogénéité,
[note de revue](../../docs/2026-10-11-revue-homogeneite.md)). Chaque règle se vérifie par la
commande donnée ; un plan ou une PR qui touche une famille cite la règle et montre la sortie de
la commande. Complète `code.md` (comment coder) et `conformite.md` (selon quelle norme).

## 1. Rejet d'une entrée invalide

**Règle.**
- Un lecteur (`read_entries`) ne lève que pour une **page illisible** (pas du JSON, pas du CSV,
  colonnes manquantes, pas un flux Atom). Une **entrée** invalide devient un rejet nommé, rendu
  avec les entrées lues, et suit un seul chemin (`reject`, `etl/rejections.py`) jusqu'au journal
  d'import. Ce chemin est le même pour les trois sortes de rejet, quelle que soit l'étape qui
  les trouve : l'entrée qu'un lecteur refuse ou que l'item refuse, la release hors de la liste
  suivie, et l'entrée que la base refuse ; la ligne de journal d'un rejet porte donc toujours
  `k_b.etl.rejections`. Le type `Rejection` reste dans `etl/raw_files.py`, le vocabulaire
  partagé par les étapes.
- À la collecte, une source n'échoue que si sa page est illisible ou si toutes ses entrées sont
  invalides (`all_items_invalid`) ; sa date de dernière collecte reste alors inchangée.
  Exception : un classement (instantané dont la complétude compte) refuse sa page entière.
- À l'écriture en base, chaque item et son sous-type sont écrits dans un `SAVEPOINT`. Si la base
  refuse l'entrée, `ROLLBACK TO` de cet item seul : il devient un rejet de `import-log.jsonl`
  (motif : ce que la base refuse) et l'import continue. Ne sont rattrapées que les erreurs dues
  à l'entrée : `sqlite3.IntegrityError` (`CHECK`, `UNIQUE`, `NOT NULL`) et les erreurs de
  conversion Python → SQLite (`OverflowError`, `UnicodeEncodeError`), liste tenue par un test
  par cas. Une erreur du système (disque plein, base verrouillée) arrête tout l'import.

**Vérifier.**
- `grep -n "logger.warning" src/k_b/etl/sources/*.py` ne renvoie aucun rejet d'entrée.
- `grep -rn "SAVEPOINT" src/k_b` renvoie l'écriture d'un item, sous `src/k_b/database/`.
- `uv run pytest` : un test par erreur rattrapée, et un test où une erreur du système arrête
  l'import.
- `grep -rn "Rejection(" src/k_b --include='*.py'` ne renvoie que la classe, dans
  `etl/raw_files.py`, et sa seule construction, dans `etl/rejections.py`.

**Pourquoi.** Une seule entrée mal formée ne doit bloquer ni une source à chaque collecte, ni
tout l'import à chaque import ; tout rejet doit laisser une trace lisible au journal d'import.
Le `SAVEPOINT` est le filet derrière la règle 4 : ce que l'item laisse passer et que la base
refuse.

**Écarté.** Valider seulement à la conversion (la collecte n'aurait plus vérifié ce qu'elle
écrit) ; garder une façon par source (arXiv écartait sans trace, les autres bloquaient tout).

## 2. Fichier temporaire

**Règle.** Tout fichier que K-B écrit lui-même (brut, état de collecte, journal d'import) passe
par une seule fonction, `write_file_atomically` : un temporaire **caché** dans le dossier cible
(nom commençant par `.`), renommé sur la cible, et supprimé sur toute exception, Ctrl-C compris
(`except BaseException`). Le temporaire est vidé sur le disque (`fsync`) avant le renommage, puis
le dossier, et chaque dossier créé pour l'écriture dans son parent ; un dossier dont le système
de fichiers refuse le `fsync` (`EBADF`, `EINVAL`, comme PostgreSQL) ne fait pas échouer
l'écriture (décision de Sabine du 2026-10-16, #62). Limite : sur macOS, `fsync` vide les données
vers le disque, pas le cache du disque ; `F_FULLFSYNC` n'est pas utilisé, la cible étant Linux
en conteneur ([man fsync d'Apple](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/fsync.2.html),
lu le 2026-10-16). La base SQLite, que SQLite écrit lui-même, est hors de cette règle.
La copie temporaire d'une base source (Zotero) est hors de cette règle elle aussi : elle vit dans
un `tempfile.TemporaryDirectory` du système, hors du dossier de données, supprimé sur un succès,
une erreur ou un Ctrl-C ; chaque extraction retire d'abord les copies qu'un processus tué aurait
laissées. Le journal de fonctionnement (`logs/kb.log`, `logs/kb-serve-data.log` pour `kb serve-data` et
`logs/kb-serve-ai.log` pour `kb serve-ai`),
ajouté ligne à ligne par `logging`, est hors de cette règle : il n'est jamais lu comme une page.

**Vérifier.**
- `grep -rn "NamedTemporaryFile\|\.tmp\|os\.replace" src/k_b` ne renvoie que
  `write_file_atomically`.
- `grep -rn "TemporaryDirectory" src/k_b` ne renvoie que la copie d'une base source.
- `uv run pytest tests/test_atomic_write.py` : `os.fsync` est appelé sur le temporaire avant le
  renommage, puis sur le dossier, puis sur le parent de chaque dossier créé.

**Pourquoi.** Un nom caché est déjà sauté par l'import (`list_visible_entries`) : un reste
d'écriture interrompue n'est jamais lu comme une page. Une seule fonction à corriger pour trois
fichiers. Le `fsync` : le brut est écrit avant l'état de collecte ; sans lui, une coupure de
courant peut laisser l'état à jour et le brut vide ou tronqué, et la collecte suivante repart de
la date avancée sans que rien ne le dise.

**Écarté.** Nettoyer au démarrage (le reste reste visible entre-temps, une étape de plus à
chaque lancement) ; garder deux fonctions (elles divergeaient déjà).

## 3. Journaux

**Règle.**
- Un message dit le champ ou la position, l'état ou le type d'erreur, et la mesure (longueur
  reçue, maximum, nombre attendu). Un échec est un état nommé (`code.md`).
- Une valeur observée (identifiant, URL, code HTTP, titre trouvé) est citée **tronquée** à une
  longueur fixe et **échappée** (retours à la ligne et caractères de contrôle), par une seule
  fonction, `quote_value` (`core/quoting.py`). `import-log.jsonl` est protégé par le JSON.
- Un champ qui porte une donnée personnelle au registre des traitements (les auteurs) n'est
  jamais cité : sa position et sa mesure seulement.
- Chaque ligne de journal est **horodatée** (quand, où, qui, quoi) en ISO 8601, en UTC, à la
  seconde, avec la zone (`2026-10-14T11:30:00Z`, le format des dates de la base ; décision du
  2026-10-12). La règle vaut par enregistrement : la trace d'une erreur suit sa ligne datée et
  lui appartient (décision du 2026-10-14).
- `print` donne le résultat d'une commande ; `logger` donne le déroulé. Un échec est journalisé
  une fois, là où il est traité.
- Le journal de fonctionnement (le déroulé, réussites et échecs) va sur la sortie d'erreur et
  dans `<KB_DATA_DIR>/logs/kb.log` (`logs/kb-serve-data.log` pour `kb serve-data`, `logs/kb-serve-ai.log` pour `kb serve-ai`), tourné chaque jour à minuit UTC, `LOG_FILES_KEPT` fichiers
  gardés (`core/config.py`), sauf `KB_LOG_TO_FILE=false` : sortie d'erreur seule, sans fichier (en
  conteneur, la sortie d'erreur est le journal ; décision du 2026-10-15, #199) ; le résultat d'une commande reste un `print`. Le journal d'import garde sa règle : écrit seulement si l'import va au
  bout de l'écriture en base.

**Vérifier.**
- `grep -nE "asctime|gmtime|DATABASE_DATE_FORMAT" src/k_b/commands/run_log.py` renvoie le format
  des journaux, l'horloge UTC et le format de date de la base.
- `uv run pytest tests/commands/test_run_log.py -k log_line` : une ligne émise est datée en UTC avec sa zone,
  sur la sortie d'erreur et, pour une erreur, dans le fichier, au même format.
- `grep -rniE "may be|maybe|probably|perhaps" src/k_b` ne renvoie rien.
- `uv run pytest` : un test donne une entrée refusée qui contient une valeur repérable sur
  plusieurs lignes et un auteur, et vérifie le message (valeur tronquée et échappée, auteur
  absent).

**Pourquoi.** Dire ce qui a été observé (`code.md`, « Journalisation ») sans recopier une
donnée personnelle (RGPD, minimisation) ; une valeur non échappée permet d'injecter une fausse
ligne de journal ([OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) :
« Perform sanitization on all event data to prevent log injection attacks », « when, where, who
and what »). Garde la décision du 2026-10-08 (champ, longueur et maximum).

**Écarté.** Jamais de valeur (perd la longueur, le maximum et l'URL observée) ; toujours la
valeur, tronquée (un nom d'auteur finit au journal).

## 4. Validation des entrées

**Règle.**
- Un type qui sert à plus d'un module, ou que la base contraint, est défini **une fois**, dans
  `items.py` : identifiants (`CveId` en chiffres ASCII, `GhsaId`, `RepositoryName`), date UTC
  avec fuseau, texte sans NUL ni surrogate isolé, entier tenu sur 64 bits.
- Chaque source garde son modèle Pydantic dans son module (`etl/sources/<source>.py`).
- Tout ce que la base refuse, l'item le refuse avant ; un test compare chaque type à son
  `CHECK`, comme pour les longueurs.

**Vérifier.**
- `grep -rnE "^(CVE_ID|CveId|GHSA_ID|GhsaId|OWNER_SLASH_NAME|RepositoryName) *=" src/k_b`
  ne renvoie que des lignes de `items.py`.
- `grep -rnE "def (parse_[a-z_]*date[a-z_]*|read_date)\(" src/k_b` renvoie une seule fonction.
- `uv run pytest tests/test_schema.py` : chaque type a sa valeur refusée par l'item et par la
  base.

**Pourquoi.** Une même règle écrite trois fois avait trois formes (nom de dépôt), et l'écart
entre l'item et la base faisait tomber tout l'import. Le motif des longueurs (une table, un test
contre le `CHECK`) marche déjà.

**Écarté.** Un module commun qui porte tous les modèles (une source ne se lit plus dans son
module, le module grossit à chaque source) ; une validation par source sans types communs (le
statu quo).

## 5. Couche d'accès aux données

**Règle.**
- **Architecture en couches** : présentation (`cli.py` et `commands/`, routes de l'API), métier et
  ETL (`etl/` : `pipeline.py`, `extract.py`, `transform.py`, `raw_reading.py`, `normalize.py`,
  `load.py`, les sources dans `etl/sources/`), accès aux données (`database/`). Une couche
  n'appelle que celle du dessous.
- `items.py` et `core/` sont le vocabulaire commun à toutes les couches : chacune peut les
  importer.
- Une API importe `database`, `items` et `core`, jamais `etl`, `database/writers` ni
  `database/writing` (sa ligne dans `tests/architecture/test_apis.py` s'ajoute à la création du
  paquet d'API).
- Le SQL **de la base K-B** vit dans `src/k_b/database/` : un dossier d'écriture, `writers/` (un
  module par sorte d'item et un pour le classement, `<sorte>_writer.py`, chacun avec une fonction
  `write`), et un module de lecture (la requête `UNION ALL`, partagée par `kb search`, « quoi de
  neuf » et l'API). Les migrations Alembic aussi.
- `database/writing.py` est la seule porte vers `writers/` hors de `database/` : il choisit
  l'écrivain de chaque sorte (`WRITER_BY_KIND`, `write_item`) et expose par `__all__` les objets
  des écrivains que lit l'import, jamais un module de `writers/` (`mypy --strict` refuse tout
  autre nom).
- La requête d'extraction d'une source qui est elle-même une base (Zotero, GH Archive sur
  BigQuery) vit dans le module de cette source, `src/k_b/etl/sources/<source>.py`, comme la
  requête d'une API : elle lit une source externe, en lecture seule, pas la base K-B.
- **Un module de source est construit d'une seule façon** (Sabine, 2026-10-25) : son identité
  (`logger`, `SOURCE_CODE`, `FOLDER_PREFIX`, et les constantes que les deux blocs partagent), puis
  `# === EXTRACT ===` (constantes de la requête, erreurs de l'extraction, la classe `…Source` et
  `fetch`, ses aides), puis `# === TRANSFORM ===` (constantes de la lecture, ce qui est gardé,
  `read_…` et `parse_…`, `convert_…`, `READER`). Le LOAD n'y est pas : il est commun à toutes les
  sources (`etl/load.py`, `database/writers/`). `github_api.py` et `tracked_repositories.py` ne
  sont pas des sources.
- `etl/pipeline.py` enchaîne les étapes des deux parcours, qui communiquent par `raw/` : la
  collecte (`extract.py`) et l'import (`transform.py`, qui lit le brut par `raw_reading.py`, puis
  `load.py`). C'est le seul module d'`etl` qui les enchaîne, et la seule porte des deux parcours
  pour `commands/` : `__all__` liste ce qui passe, comme `database/writing.py` pour les écrivains.
  Il reçoit en paramètre ce qui nomme les sources (sortes, dépôts suivis, dossiers à ne garder
  qu'au dernier import), ne lit pas l'environnement, n'affiche rien et ne rend aucun code de
  sortie : il rend un résultat nommé que la commande affiche. Le module de chargement garde la
  transaction et le journal d'import, sans SQL.

**Vérifier.**
- `grep -rlE "INSERT INTO|SELECT |UPDATE |DELETE FROM" src/k_b --include='*.py' --exclude=zotero.py --exclude=gh_archive.py`
  ne renvoie que des fichiers de `src/k_b/database/`.
- `grep -rlE "INSERT INTO|UPDATE |DELETE FROM" src/k_b/etl/sources --include='*.py'` ne renvoie
  rien (une source ne fait que lire).
- `uv run pytest tests/architecture/test_layers.py` : les dépendances, lues à deux niveaux
  (`core`, `database`, `etl`, `etl/sources`) ; aucun module de `database/`, sous-dossiers
  compris, n'importe de K-B autre chose que `database`, `items` et `core` ; hors de `database/`,
  aucun module n'atteint `database/writers` (`test_only_database_imports_its_writers`).
- `grep -c "execute" src/k_b/etl/load.py` renvoie 0.
- `grep -nE "etl\.(extract|transform|load|normalize|import_log|raw_purge)" src/k_b/commands` ne
  renvoie rien : les commandes passent par `etl/pipeline.py`.
- `uv run pytest tests/architecture/test_layers.py -k "pipeline or stage"` : `etl/pipeline.py`
  n'importe ni les sources ni la composition, et les trois stages ne s'importent pas entre eux.
- `uv run pytest tests/architecture/test_source_modules.py` : chaque module de source a ses deux
  bandeaux, dans l'ordre, la classe `…Source` sous EXTRACT, sa lecture, sa conversion et son
  `READER` sous TRANSFORM.

**Pourquoi.** Un module par écrivain : les modules de `writers/` font 851 lignes à eux tous
(relevé du 2026-10-14), et chaque sorte a assez de code pour son module (`code.md`). Une seule
requête de lecture partagée : un module suffit, et la requête ne dépend pas de son premier
appelant (décision du 2026-10-10 : `sqlite3` et SQL, pas d'ORM).

**Écarté.**
- Un module par objet métier pour la lecture : la requête `UNION ALL` n'appartient à aucun.
- Un seul module d'écriture : sept écrivains dans un fichier (écarté le 2026-10-13).
- Un CRUD par table : K-B écrit un item et son sous-type ensemble, par upsert, ne supprime que
  par la purge et lit par une requête ; la plupart des fonctions seraient sans appelant (YAGNI).
- MVC comme nom : K-B n'a ni vue à rafraîchir ni contrôleur d'événements ; le principe utile,
  séparer les couches, est gardé ci-dessus.
