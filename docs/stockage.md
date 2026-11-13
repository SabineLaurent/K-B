# Spécifications de stockage et modèles de la base

La base garde les items, dédoublonnés par ses règles (étape 4 de [specs-collecte.md](specs-collecte.md)). Ce
document fixe le SGBD, les règles de stockage, ce que chaque source écrit, et le MPD, qui est le
script [`src/k_b/database/schema.sql`](../src/k_b/database/schema.sql). Il décrit le schéma codé.
Les décisions et leur pourquoi sont dans le [journal ADR](ADR/journal-decisions-projet.md) et
dans [la clarification du modèle](2026-10-07-clarification-modele.md) ; pour la base et le
schéma, l'entrée du 2026-10-10 du journal fait foi.

```
collecte → raw/ (brut intact) → lecture + normalisation → base (qui dédoublonne)
```

La base est la source de vérité (décision de Sabine du 2026-11-04) : le brut n'est gardé que 6 mois
au plus, sauf le dernier fichier importé d'un catalogue d'état (Zotero, CISA KEV), et la base garde
la veille 3 ans, la bibliothèque et les catalogues d'état sans limite
([registre-traitements.md](registre-traitements.md), « Procédure de tri »). La base ne se
reconstruit donc en rejouant la lecture et l'import sur `raw/` que pour les 6 derniers mois, à une
limite près : après un catalogue CISA importé en retard, les dates d'une ligne (`revised_at`,
`withdrawn_at`) et le fichier rattaché à son item peuvent différer, pas son contenu (étape 4 de
[specs-collecte.md](specs-collecte.md)). `kb import` n'importe que les fichiers bruts pas encore
importés : leur registre est la table `raw_data`.
Elle ne contient que ce que le brut contient (les papiers arXiv écartés à la requête n'y sont pas).
Elle est lue par l'API de données, lancée par `kb serve-data` ([specs-api.md](specs-api.md)) : routes
`/items`, `/items/{item_id}` et `/trends` (`src/k_b/data_api/routers/item_router.py`,
`trend_router.py`), qui lisent la base en lecture seule, sur l'un ou l'autre moteur
(`src/k_b/data_api/dependencies.py`, `connect_reader` de `src/k_b/database/engine.py`). Le code des comptes rendus de veille (`src/k_b/ai_api/`) n'ouvre pas la
base : il lit la veille par l'API de données (`src/k_b/ai_api/connectors/data_api_client.py`), et
est servi par `kb serve-ai` (#156). `kb search` vient après le 08/11 (journal ADR, 2026-10-15, « POC du
25/10 », décision 1).

## Pourquoi un SGBD relationnel

Le modèle de données de K-B est relationnel : le MCD et le MLD de [`docs/merise/`](merise/) et
`schema.sql`, le MPD, décrivent le même modèle, aux écarts près que liste « MCD et MLD »,
ci-dessous ; `schema.sql` fait foi pour le code. Un SGBD relationnel tient lui-même les clés,
l'exclusion des sous-types et les `CHECK` à chaque écriture, et l'import entier par sa
transaction ; sans lui, ils seraient à coder et à tester dans K-B, et les contrôles de l'item
perdraient leur second filet. Ce qu'il ne tient pas est listé plus bas (« Ce que la base ne tient
pas »).

- **Les clés étrangères relient ce que le modèle associe.** Un fichier brut vise sa source, un item
  le fichier brut de sa version actuelle (`src/k_b/database/schema.sql:30`, `:47`) ; une release
  vise son dépôt suivi (`:178`), un surlignage son item (`:97`), et la liaison `item_has_tag` un
  item et un tag (`:337-338`). La base refuse une ligne qui viserait une ligne absente ; en SQLite,
  à condition que la connexion l'active, ce que K-B fait à chaque ouverture (« Spécifications de
  stockage », « Clés étrangères », ci-dessous ; test : `tests/test_database.py:31`).
- **La clé `(item_id, kind)` tient l'exclusion des sous-types.** `item` porte la sorte de chaque
  item, et `UNIQUE (id, kind)` fait de ce couple la cible d'une clé étrangère (`schema.sql:42-50`).
  Chacun des cinq sous-types, `release`, `advisory`, `newsletter_article`, `zotero_entry` et
  `clip`, fixe sa sorte par un `CHECK` (`kind = 'release'`…), a un `item_id` unique et vise `item`
  par la clé étrangère composée `(item_id, kind)` (`schema.sql:176-177` et `:192`, `:201-202` et
  `:219`, `:229-230` et `:250`, `:262-263` et `:284`, `:295-296` et `:319`). Un item a donc un
  sous-type au plus, celui de sa sorte : la base refuse tout autre rattachement d'un sous-type.
  `kind` y est `NOT NULL` : un `kind` nul passerait son `CHECK` et échapperait à la clé étrangère
  (`schema.sql:173`). C'est l'option D du journal ADR (2026-10-07). Tests : un sous-type qui vise
  un item d'une autre sorte, qui porte une autre sorte que la sienne ou aucune, est refusé
  (`tests/test_schema.py:372`, `:384`, `:416`, `:426`, `:877`, `:896`, `:901`).
- **Les contraintes `CHECK` refusent ce que le modèle ne permet pas** : une valeur hors de sa liste
  (`source_type`, `acquisition_mode`, `kind` : `schema.sql:21`, `:23`, `:45-46`), une date hors de
  la forme `AAAA-MM-JJTHH:MM:SSZ` (`release.published_at`, `:186-187` ; les dates de `clip` sont
  l'exception, « Spécifications de stockage », ci-dessous), un texte trop long (« Longueurs
  maximales », ci-dessous), une liste JSON qui n'est pas un tableau non vide ou qui dépasse son
  nombre maximal d'éléments (`:64-66`). Un test compare chaque type de l'item à son `CHECK`
  (règle 4 de `.claude/rules/conventions.md`).
- **La transaction de l'import.** `kb import` écrit les dépôts suivis, puis inscrit chaque fichier
  lu au registre (`raw_data`) et écrit ses items, dans une seule transaction, sous le verrou des
  écrivains (`src/k_b/etl/load.py:60-88`). Chaque item s'y écrit dans un `SAVEPOINT`
  (`src/k_b/database/savepoint.py:19-40`) : une entrée que la base refuse pour ses propres valeurs
  (`CHECK`, `UNIQUE` hors clé primaire, `NOT NULL`), ou que Python ne peut pas lui passer (un entier
  au-delà de 64 bits, un surrogate isolé), est annulée seule et devient un rejet du journal
  d'import, et l'import continue (règle 1). Une clé étrangère, une
  clé primaire ou un type refusés viennent de l'écrivain ou du schéma : ils arrêtent l'import,
  comme une erreur du système (`src/k_b/database/errors.py:17-28`). Une erreur qui arrête l'import,
  ou une interruption (Ctrl-C, SIGTERM) avant le `commit`, annule l'import entier
  (`load.py:80-85`, `:138`) : la base ne garde jamais un import à moitié écrit.

Ce que la base ne tient pas :

- les deux dénormalisations voulues du MPD, le classement dans `trend` et les listes JSON (« MCD et
  MLD », ci-dessous) : la règle « une fenêtre, une donnée brute » de `trend` est tenue par
  l'écriture ; d'une liste, la base tient la forme et, pour les auteurs et les paquets touchés, le
  nombre maximal d'éléments, pas chaque élément ;
- `publication` et `vulnerability` sont des tables de référence, pas des sous-types : elles visent
  leur item par une clé étrangère simple (`schema.sql:59`, `:134`), et la base ne vérifie pas la
  sorte de l'item visé ;
- un surlignage vise `item`, pas l'entrée Zotero : son rattachement à une entrée Zotero est tenu par
  le code (« MCD et MLD », ci-dessous).

Le choix du moteur vient ensuite : SQLite et PostgreSQL sont tous deux relationnels, et
`schema_postgresql.sql` garde les mêmes clés étrangères (17 `REFERENCES` dans chaque script, dont
les cinq clés `(item_id, kind)`) et la même cible `UNIQUE (id, kind)` ;
`tests/test_schema_structures.py` compare les deux structures table par table. Ce que chaque schéma
écrit à sa façon est listé dans « Ce qui est propre à SQLite », ci-dessous.

## Le SGBD : SQLite en local, PostgreSQL en ligne

La variable `KB_DATABASE_URL` choisit le moteur (journal ADR, 2026-11-06, « Base : PostgreSQL en
ligne, par un adaptateur maison (#417) »).

- **Sans elle, SQLite** : un fichier hors du dépôt, `<KB_DATA_DIR>/k-b.sqlite`, lu avec le module
  `sqlite3` de la bibliothèque standard. C'est la base des deux premiers temps, le Mac puis les
  conteneurs en local (journal ADR, 2026-10-20, « Squelette E1 E3 : cadrage du 20/10 »,
  décision 1). Le dossier de données est donné par `KB_DATA_DIR`, que le journal ADR du 2026-10-09
  fixe à `~/.knowledge_base` ; dans les conteneurs du deuxième temps, le fichier sera dans un volume
  nommé (journal ADR, 2026-10-15, « POC du 25/10 », décision 2 ; #200).
- **Avec elle, PostgreSQL** : une URL `postgresql://` ou `postgres://`, lue par psycopg 3
  (`src/k_b/database/postgresql.py`). C'est la base en ligne, au troisième temps. Une autre valeur,
  vide comprise, ou une URL que libpq ne lit pas, est refusée (code 2), sans être citée : elle peut
  porter un mot de passe. Une
  variable que libpq lit en plus de l'URL (`PGHOST`, `PGPASSWORD`… : les 42 noms de la
  [doc de libpq](https://www.postgresql.org/docs/18/libpq-envars.html), lue le 2026-11-06) est
  refusée de même : libpq la lirait en silence (règle 2 de `.claude/rules/poc.md`).

`kb create-db`, `kb import` et `kb purge` écrivent sur les deux moteurs ; `kb serve-data`
lit la base que nomme `KB_DATABASE_URL`, sur l'un ou l'autre (#418).

| | SQLite (en local) | PostgreSQL (en ligne) |
|---|---|---|
| Installation | aucune : un fichier, rejouable par un tiers | un serveur à installer, lancer et sécuriser |
| Écritures | une à la fois ; ici un seul écrivain, le pipeline | plusieurs en parallèle (MVCC) |
| Lectures pendant l'écriture | oui, en mode WAL | oui (MVCC) |
| Droits | aucun compte : l'API ouvre la base en lecture seule, le fichier est lisible par sa seule propriétaire | rôles SQL, dont un rôle en lecture seule pour l'API (#421) ; en attendant, chaque connexion de l'API lit en `READ ONLY`, une écriture est refusée par le serveur |
| Typage | souple par défaut ; strict avec les tables `STRICT` | strict |
| Dépendance | aucune | un pilote (`psycopg`) et, pour l'API, son pool (`psycopg-pool`) |

Pourquoi SQLite en local : un utilisateur, un écrivain par jour, quelques milliers d'items par
an ; en localhost, un fichier suffit, sans serveur à lancer. Limite assumée : pas de rôles dans la
base. Pourquoi PostgreSQL en ligne : sur Azure Container Apps, un fichier SQLite n'a pas de disque
fiable (journal ADR, « POC du 25/10 », décision 2). Sabine l'a tranché les 05 et 06/11, contre
SQLite et Blob (journal ADR, 2026-11-06, qui ferme « La base au temps 3 »). Les deux moteurs
lisent le même SQL : aucun SQL propre à SQLite n'est ajouté (règle 1 de `.claude/rules/poc.md`),
et la branche PostgreSQL traduit les marqueurs de `sqlite3` (`?`, `:nom`) en ceux de psycopg.
Ce que chaque schéma écrit à sa façon est listé plus bas.

## Spécifications de stockage

- **Clés étrangères** : SQLite les ignore si la connexion n'exécute pas `PRAGMA foreign_keys = ON`.
  `connect_database` et `connect_database_read_only` (`src/k_b/database/engine.py`)
  l'exécutent à chaque ouverture.
- **Mode WAL** (`PRAGMA journal_mode = WAL`, gardé dans le fichier) : le pipeline écrit pendant
  que l'API lit, sans se bloquer. Tous les programmes tournent sur la même machine.
- **Lecture seule** : `connect_database_read_only` ouvre la base en `mode=ro`, pour l'API de
  données. Une lecture en `mode=ro` crée les fichiers `-shm`
  et `-wal` s'ils manquent, dans le dossier de la base, et les laisse à sa fermeture
  (documentation SQLite, WAL, § 5 ; constat sur SQLite 3.50.4). En PostgreSQL, l'API lit par un
  pool de connexions, chacune en `REPEATABLE READ READ ONLY`, chaque instruction sous son
  `statement_timeout` ([specs-api.md](specs-api.md), « Lecture seule » et « Délai »).
- **La base PostgreSQL est créée hors de K-B** (compose, Azure : #419, #421), en UTF8 et en
  collation C, PostgreSQL 17 ou plus récent (`IS JSON` et `pg_input_is_valid` depuis 16,
  `pg_database.datlocale`, que lit `kb create-db`, et le fournisseur builtin depuis 17).
  `kb create-db` refuse une autre base, puis crée dans celle de l'URL les tables de
  `schema_postgresql.sql` et les 7 sources, en une transaction : sur une erreur, rien ne reste.
  Pourquoi UTF8 : en `SQL_ASCII`, psycopg rend des octets et `length()` compte des octets.
  Pourquoi C (fournisseur libc, ou builtin à `C`) : le texte se trie et se compare octet par
  octet, comme en SQLite, et `citext` ne plie la casse que des lettres ASCII, comme
  `COLLATE NOCASE` (observé le 2026-11-06). Une base qui a déjà la table `source` est refusée,
  comme un fichier SQLite qui existe (code 2).
- **Un import à la fois** : en SQLite, par le verrou d'écriture du fichier ; en PostgreSQL, par un
  verrou consultatif (`pg_advisory_xact_lock`) pris au début de la transaction de l'import et
  rendu à sa fin. Un import qui attend ce verrou plus de 5 s (`DATABASE_LOCK_TIMEOUT_SECONDS`, le
  délai de `sqlite3`) échoue, comme sur « database is locked » ; une connexion attend le serveur
  10 s au plus (`DATABASE_CONNECT_TIMEOUT_SECONDS`). Les deux purges de `kb purge` qui écrivent en base
  (`purge/base.py`, `purge/registry.py`) le prennent aussi, en tête de leur transaction : une purge
  attend un import en cours, 5 s au plus, puis échoue sans rien supprimer.
- **Dates** : du texte `AAAA-MM-JJTHH:MM:SSZ`, en UTC. Un `CHECK` refuse toute autre forme, et
  un jour qui n'existe pas. Exception, `clip` (#14), écrite en SQL portable (règle 1 de
  `.claude/rules/poc.md`, sans `strftime`) : le `CHECK` de chacune de ses dates (`saved_at`,
  `published_at`, `revised_at`) ne tient que la longueur et la place du
  `T` et du `Z` ; la forme complète est tenue par l'item. Une source qui ne donne qu'un jour
  (`dateAdded` de CISA KEV, `created` et `published` de Web Clipper) est stockée à minuit UTC :
  convention d'écriture, pas de donnée ajoutée.
- **Types** : tables `STRICT`, une valeur du mauvais type est refusée.
- **Identifiants** : chaque table du modèle clarifié a un `id` technique pour clé primaire ;
  l'identifiant naturel de chaque chose est tenu par une contrainte `UNIQUE` : `arxiv_id`,
  `cve_id`, `release_id`, `ghsa_id`, `raw_file_path`, `source_code`, le nom d'un dépôt suivi
  (sans tenir compte de la casse), `zotero_key`, l'URL d'un clip (`clip.url`, sans ses `utm_*`),
  la fenêtre et le dépôt d'une tendance (`window_end`, `repository_id`). Un item n'a plus d'URL
  commune ; seule l'URL d'un clip est unique, parce qu'elle est sa clé (journal ADR, « Collecte :
  clips »).
- **Une absence reste une absence** : une date ou un nom manquant n'est pas remplacé.
- **Listes** : les auteurs d'un papier et les paquets d'une alerte ou d'un dépôt suivi sont une
  liste JSON dans une colonne texte, non vide, dans l'ordre reçu.

### Longueurs maximales

Un texte qu'une source écrit en base a une longueur maximale, en caractères, tenue deux fois
(journal ADR, 2026-10-08) :

1. à la lecture du brut, par l'item (`src/k_b/items.py`, `MAX_LENGTH_BY_KIND`) : une entrée dont
   un texte dépasse est écartée, les autres entrées du fichier sont lues ; le motif du rejet,
   écrit dans le journal d'import, dit le champ, la longueur reçue et le maximum
   (`title too long: 612 characters, maximum 500`) ;
2. dans la base, par un `CHECK (length(colonne) <= n)` de la colonne.

Rien n'est tronqué. Les valeurs sont dans `items.py`, seul endroit à lire pour les connaître :
elles ne sont pas recopiées ici. Un test (`tests/test_schema.py`) vérifie que chaque maximum de
`items.py` est égal au `CHECK` de sa colonne, dans les deux sens.

- **Colonnes bornées** : celles qu'une source remplit, dans `publication`, `vulnerability`,
  `release`, `advisory`, `newsletter_article`, `zotero_entry` et `clip` (le texte d'un clip, au
  plus `CLIP_MAX_BYTES` caractères, la taille maximale d'un clip copié) ; `trend.repository_name`, dont
  le maximum est tenu par `TrendRow` (`TREND_REPOSITORY_NAME_MAX_LENGTH`, même fichier), une
  ligne de classement n'étant pas un item : un nom plus long fait refuser le classement entier ;
  `highlight.text` et `highlight.comment`, tenus par `Highlight`
  (`HIGHLIGHT_MAX_LENGTH_BY_FIELD`, même fichier) : un surlignage trop long fait rejeter son
  document entier. La clé Zotero (`zotero_key`, 8 caractères) est tenue par sa forme
  (`GLOB`), pas par une longueur.
- **Listes JSON** : le nombre d'éléments est borné deux fois, par l'item et par un
  `CHECK (json_array_length(colonne) <= n)`. La longueur de chaque élément n'est tenue que par
  l'item : un `CHECK` de SQLite ne peut pas parcourir les éléments d'une liste (pas de
  sous-requête dans un `CHECK`).
- **Colonnes sans borne** : celles que le code remplit (`source`, `tracked_repository`, le chemin
  et le flux de `raw_data`) ; les dates et les listes fermées, tenues par leur propre `CHECK`.
- **Limite de SQLite** : `length()` compte les caractères jusqu'au premier caractère NUL, alors
  que l'item les compte tous. Un `CHECK` seul laisserait donc passer un texte qui contient un NUL
  en étant plus long que le maximum, et refuserait un `tag_name` qui commence par un NUL
  (`"\0v1"`). L'item refuse tout NUL avant la base (`check_text_can_be_stored`,
  `src/k_b/items.py:118-124` ; `tests/test_schema.py:1092`) : aucun des deux cas n'atteint la base.
  Pour `trend`, `GLOB` s'arrête lui aussi au premier NUL, et `TrendRow` refuse un nom de dépôt qui
  contient un caractère de contrôle, NUL compris.

### Ce que chaque source met dans l'item, puis dans la base

Les lecteurs écrits à ce jour : arXiv, CISA KEV, releases et alertes GitHub, tldr.tech, Zotero,
Web Clipper. Chaque entrée du brut devient un item (`src/k_b/items.py`), que l'import
(`src/k_b/etl/file_writing.py`) fait écrire dans la table de sa sorte (`kind`) par l'écrivain
de cette sorte (`src/k_b/database/writers/`), choisi par `src/k_b/database/writing.py`.
Exception :
GH Archive, dont chaque ligne de classement (`TrendRow`, `src/k_b/items.py`) devient une ligne de
`trend`, sans item.

| Source (`kind`) | Champ de l'item | Vient de | Colonne |
|---|---|---|---|
| arXiv (`paper`) | `source_item_id` | identifiant sans version (`2609.31282`) | `publication.arxiv_id` |
| | `title`, `summary` | `title`, `summary` | `publication.title`, `publication.summary` |
| | `authors` | noms des auteurs, dans l'ordre d'arXiv | `publication.authors` (liste JSON) |
| | `published_at`, `revised_at` | `published`, `updated` | `publication.submitted_at`, `publication.revised_at` |
| CISA KEV (`vulnerability`) | `cve` | `cveID` | `vulnerability.cve_id` |
| | `title`, `summary` | `vulnerabilityName`, `shortDescription` | `vulnerability.name`, `vulnerability.description` |
| | `vendor`, `product` | `vendorProject`, `product` | `vulnerability.vendor`, `vulnerability.product` |
| | `published_at` | `dateAdded`, à minuit UTC | `vulnerability.date_added` |
| | `ransomware_use` | `knownRansomwareCampaignUse` | `vulnerability.ransomware_use` |
| GitHub, release (`release`) | `source_item_id` | `id` | `release.release_id` |
| | `repository_name` | le dépôt, lu dans `html_url` | `release.tracked_repository_id` |
| | `tag_name`, `release_name`, `summary` | `tag_name`, `name`, `body` | `release.tag_name`, `release.name`, `release.body` |
| | `published_at`, `url` | `published_at`, `html_url` | `release.published_at`, `release.url` |
| GitHub, alerte (`advisory`) | `source_item_id` | `ghsa_id` | `advisory.ghsa_id` |
| | `cve` | `cve_id`, s'il existe | `advisory.vulnerability_id` |
| | `title` | `summary` | `advisory.summary` |
| | `published_at`, `url` | `published_at`, `html_url` | `advisory.published_at`, `advisory.url` |
| | `package_names` | paquets touchés, chacun une fois | `advisory.packages` (liste JSON) |
| tldr.tech (`newsletter_article`) | `edition` | nom du dossier brut sans `tldr_` (`ai`) | `newsletter_article.edition` |
| | `published_at` | date du premier `h1` de la page, à minuit UTC | `newsletter_article.edition_date` |
| | `rank` | position de l'entrée parmi les `<article>` de la page, à partir de 1 | `newsletter_article.rank` |
| | `title`, `summary` | texte de `a.font-bold`, texte de `div.newsletter-html` | `newsletter_article.title`, `newsletter_article.summary` |
| | `url` | `href` de `a.font-bold`, sans ses `utm_*` | `newsletter_article.url` |
| Zotero (`zotero_entry`) | `source_item_id` | `key` du document | `zotero_entry.zotero_key` |
| | `item_type`, `title` | `item_type`, `title` | `zotero_entry.item_type`, `zotero_entry.title` |
| | `url` | `url`, `http` ou `https`, sans ses `utm_*` ; peut manquer | `zotero_entry.url` |
| | `saved_at` | `date_added` (date de Zotero, UTC) | `zotero_entry.saved_at` |
| | `arxiv_id` | `archive_id` `arXiv:<id>`, sans préfixe ni version, forme d'après 2007 (`2609.31282`) ou d'avant (`hep-th/9901001`) | `zotero_entry.publication_id` (`publication.arxiv_id`) |
| | `highlights` (`Highlight`) | `key`, `text`, `comment`, `date_added` de chaque surlignage | `highlight.zotero_key`, `highlight.text`, `highlight.comment`, `highlight.highlighted_at` |
| Web Clipper (`clip`) | `source_item_id`, `url` | `source`, `http` ou `https`, sans ses `utm_*` | `clip.url` |
| | `title` | `title` | `clip.title` |
| | `saved_at`, `published_at` | `created`, `published` (jours `AAAA-MM-JJ`), à minuit UTC ; `published` peut manquer | `clip.saved_at`, `clip.published_at` |
| | `summary` | le texte après le frontmatter, tel quel | `clip.body` |
| GH Archive (pas un item : `TrendRow`) | `window_end` | dernier jour de la fenêtre de 3 jours, à minuit UTC | `trend.window_end` |
| | `repository_id`, `repository_name` | `repo.id`, dernier `repo.name` vu dans la fenêtre | `trend.repository_id`, `trend.repository_name` |
| | `stars_gained`, `forks_gained` | nombre de `WatchEvent` et de `ForkEvent` de la fenêtre | `trend.stars_gained`, `trend.forks_gained` |
| toutes | `source_code`, `collected_at`, `raw_file_path` | le fichier brut lu | `raw_data` (`source_id`, `collected_at`, `raw_file_path`, `stream`) |

- L'URL d'un papier arXiv (`https://arxiv.org/abs/<id>`) et d'une faille
  (`https://nvd.nist.gov/vuln/detail/<CVE>`) se déduit de son identifiant : elle est dans l'item,
  pas dans la base. Celle d'une release ou d'une alerte est gardée telle que GitHub la donne.
- Le titre de l'item d'une release (dépôt et nom) est calculé à la lecture et n'est pas stocké.
- Une alerte qui cite un CVE inconnu de la base le crée dans `vulnerability`, sans ses colonnes
  CISA KEV.
- Une release d'un dépôt qui n'est pas dans la liste des dépôts suivis est rejetée et journalisée.
- Le login de l'auteur d'une release ou d'une alerte n'est pas lu (minimisation, voir
  specs-collecte.md). Le texte d'une release (`body`) est gardé tel que reçu : il peut contenir un
  login ou une @mention écrits par ses auteurs (voir le
  [registre des traitements](registre-traitements.md)).
- L'identifiant d'un article TLDR dans l'item (`ai/2026-10-08#3` : édition, date, rang) n'est
  pas stocké : ses trois parties sont les colonnes de sa clé. `newsletter_article.publication_id`
  (le papier cité) n'est pas encore rempli.
- **Zotero** (#138, journal ADR, 2026-10-13) :
  - Un document dont `archive_id` est une référence arXiv pointe vers sa `publication`, créée
    avec sa seule référence si arXiv ne l'a pas encore donnée (ses colonnes arXiv restent vides
    jusque-là). Un document sans référence arXiv n'a pas de publication. Deux entrées du même
    papier arXiv pointent vers la même publication.
  - Ne vont pas en base : le champ `date` du document, ses auteurs, ses étiquettes, ses PDF
    (chemin et clé), la page d'un surlignage ; ils restent dans l'extrait brut. Un document hors
    arXiv n'a donc ni date de publication ni auteurs en base, et `kb search` ne peut pas filtrer
    par étiquette.
  - Un `archive_id` qui commence par `arXiv:` sans en avoir l'une des deux formes (chiffres
    ASCII seulement), une date d'une autre forme que `AAAA-MM-JJ HH:MM:SS` ou un titre absent
    font rejeter le document entier, au journal d'import. Un surlignage sans texte est gardé
    pour son commentaire (`highlight.text` absent) ; sans texte ni commentaire, il n'entre pas
    en base, et son document n'est pas rejeté (un `CHECK` de `highlight` exige l'un des deux).
    Un texte ou un commentaire vide est rangé absent (NULL) : un extrait qui donnerait l'autre
    forme ne date pas de révision. Un extrait qui n'est pas une liste JSON, ou trop imbriqué
    pour être lu (`RecursionError`, pour toutes les sources, #103), est rejeté entier. Le motif du rejet nomme le champ, l'erreur et la
    mesure, jamais la valeur : un titre ou un surlignage est une donnée personnelle.
  - L'URL est gardée en `http` si Zotero la donne ainsi (les 5 documents de l'extrait du
    2026-10-13) ; les autres sortes exigent `https`, sauf `clip` (Web Clipper garde l'URL de la
    page, `http` ou `https`).
  - Un texte ou un commentaire de surlignage qui contient un NUL est refusé par l'item
    (`src/k_b/items.py:373-388`), comme les autres textes (« Limite de SQLite » ci-dessus).
- **Web Clipper** (#14, journal ADR, 2026-10-17) : un clip a un `item.id` technique, comme les
  autres items ; son URL sans `utm_*` est sa clé naturelle. Ne vont pas en base : `author`,
  `description` ; ils restent dans la copie brute. Les `tags` y vont depuis #260 (journal ADR,
  2026-10-19) : normalisés (`normalize_tag`, `items.py` : en minuscules, sans espaces autour,
  sans `#` au début), une ligne par tag dans `tag`, partagée par tous les items qui le portent,
  et une liaison plusieurs-à-plusieurs `item_has_tag` ; le tag `clippings` du gabarit est écarté. Le texte gardé (`clip.body`) peut
  contenir la signature de l'article et les notes de l'utilisatrice
  ([registre des traitements](registre-traitements.md)). La dernière version d'une URL est
  gardée : un clip dont le contenu a changé est réécrit, et `clip.revised_at` prend la date de la
  collecte qui a vu le changement (journal ADR, 2026-10-19, #259).
- Les classements des dépôts les plus étoilés et les plus forkés n'entrent pas dans la base
  (journal ADR, 2026-10-07).

## MCD et MLD

Le MCD et le MLD sont dessinés avec draw.io, dans [`docs/merise/`](merise/) (journal ADR,
2026-10-08) : [`mcd-k-b_20261020.drawio`](merise/mcd-k-b_20261020.drawio) et
[`mld-k-b_20261020.drawio`](merise/mld-k-b_20261020.drawio), tirés de
[`schema.sql`](../src/k_b/database/schema.sql) le 2026-10-20 (#211). Leurs images, exportées en
SVG : [`mcd-k-b_20261020.svg`](merise/mcd-k-b_20261020.svg) et
[`mld-k-b_20261020.svg`](merise/mld-k-b_20261020.svg). Une vue d'ensemble du MCD, avec les mêmes
entités, associations, cardinalités et disposition, mais sans propriétés :
[`mcd-k-b_20261020_vue-ensemble.drawio`](merise/mcd-k-b_20261020_vue-ensemble.drawio), et son image
[`mcd-k-b_20261020_vue-ensemble.svg`](merise/mcd-k-b_20261020_vue-ensemble.svg). Chaque élément du MCD renvoie
à ses lignes de `schema.sql` ; le MLD se déduit du MCD par les règles de passage, et chacune de ses
tables et colonnes renvoie à sa ligne de `schema.sql` quand elle y est. Le MPD est `schema.sql`.
Les modèles ne sont pas recopiés ici ; la disposition du MCD suit
[`positions-mcd.md`](merise/positions-mcd.md).

Le MPD s'écarte du MLD par deux dénormalisations voulues (décision de Sabine du 2026-10-20) ;
aucune issue ne les aligne :

- **Le classement dans `trend` (2FN).** Au MLD, `ranking` garde une fenêtre et la donnée brute
  qui l'a apportée, et `trend` une ligne par dépôt de la fenêtre. Au MPD, `trend` seule porte
  `window_end` et `raw_data_id` : `raw_data_id` ne dépend que de `window_end`, une partie de la
  clé naturelle `(window_end, repository_id)`, ce que la 2FN refuse. Un classement n'a pas
  d'autre attribut que sa donnée brute. La règle « une fenêtre, une donnée brute »
  (`schema.sql:105-106`) est tenue par l'écriture : une ligne n'est écrite que si aucune autre
  donnée brute n'a apporté sa fenêtre (`src/k_b/database/writers/trend_writer.py:15-31`).
- **Les listes JSON (1FN).** Au MLD, `author`, `tracked_package` et `affected_package` ont une
  ligne par élément. Au MPD, ce sont trois listes JSON : `publication.authors`,
  `tracked_repository.packages` et `advisory.packages`, ce que la 1FN refuse (une valeur non
  atomique). Raison : une liste n'est jamais cherchée ni filtrée en base ; elle s'écrit entière,
  avec sa ligne. Les auteurs et les paquets touchés se lisent entiers et sont servis en liste par
  l'API (`src/k_b/database/reading.py:394, 420`). Les paquets suivis sont une copie de la liste du
  code (`GITHUB_TRACKED_REPOSITORIES` de `src/k_b/core/config.py`), réécrite entière à chaque import
  (`src/k_b/database/writers/release_writer.py:24-29`) et jamais relue en base. Un `CHECK` tient sa forme
  (tableau JSON non vide) et, pour les auteurs et les paquets touchés, son nombre maximum
  (1 000 et 100) ; la longueur de ses éléments est tenue par les items (`schema.sql:10-14`).

Les autres écarts sont propres au MPD et annotés dans le MLD : chaque sous-type d'item y a sa
colonne `id`, la colonne `kind` et la clé étrangère `(item_id, kind)`, qui tiennent l'exclusion
des sous-types ; la clé étrangère de `highlight` vise `item`, l'entrée Zotero étant tenue par le
code (`src/k_b/database/writers/zotero_entry_writer.py:89-103, 139`).

## MPD

Deux scripts, exécutés dans cet ordre à la création de la base :

- [`schema.sql`](../src/k_b/database/schema.sql) crée les tables, contraintes et index ;
- [`seed_sources.sql`](../src/k_b/database/seed_sources.sql) insère les 7 sources (données de
  référence). Il se rejoue sans risque : une source déjà présente est laissée telle quelle.
  Sans lui, aucun item ne peut entrer : un item pointe vers un fichier brut (`raw_data`), qui
  pointe vers sa source.

La structure et les données de référence changent pour des raisons différentes : ajouter une
source ne touche pas aux tables.

| Table | Ce qu'elle garde | Colonnes |
|---|---|---|
| `source` | les 7 sources (table de référence) | `id`, `source_code`, `label`, `source_type`, `acquisition_mode` |
| `raw_data` | un fichier de `raw/`, fourni par une source | `id`, `source_id`, `raw_file_path`, `stream`, `collected_at` |
| `item` | une entrée collectée, minimale (option D) | `id`, `kind`, `raw_data_id` |
| `publication` | référentiel des papiers ; arXiv fait foi | `id`, `arxiv_id`, `item_id`, `title`, `summary`, `authors`, `submitted_at`, `revised_at` |
| `vulnerability` | référentiel des failles (CVE) ; CISA KEV fait foi | `id`, `cve_id`, `item_id`, `name`, `description`, `vendor`, `product`, `date_added`, `ransomware_use`, `revised_at`, `withdrawn_at` |
| `tracked_repository` | les dépôts GitHub suivis (table de référence) | `id`, `repository_name`, `ecosystem`, `packages` |
| `release` | sous-type d'item : une release d'un dépôt suivi | `id`, `item_id`, `kind`, `tracked_repository_id`, `release_id`, `tag_name`, `name`, `body`, `published_at`, `url` |
| `advisory` | sous-type d'item : une alerte de sécurité GitHub | `id`, `item_id`, `kind`, `ghsa_id`, `vulnerability_id`, `summary`, `published_at`, `url`, `packages` |
| `newsletter_article` | sous-type d'item : un article résumé par une édition TLDR ; clé (édition, date, rang) | `id`, `item_id`, `kind`, `edition`, `edition_date`, `rank`, `title`, `summary`, `url`, `publication_id` |
| `zotero_entry` | sous-type d'item : un document de la bibliothèque Zotero ; catalogue d'état ; clé `zotero_key` | `id`, `item_id`, `kind`, `zotero_key`, `item_type`, `title`, `url`, `saved_at`, `publication_id`, `revised_at`, `withdrawn_at` |
| `clip` | sous-type d'item : une page gardée avec Web Clipper ; la dernière version d'une URL est gardée ; clé `url` | `id`, `item_id`, `kind`, `url`, `title`, `body`, `saved_at`, `published_at`, `revised_at` |
| `tag` | un tag d'un `.md` importé, normalisé, partagé par les items qui le portent ; clé `name` (#260) ; `id` interne, que SQLite peut redonner après une suppression | `id`, `name` |
| `item_has_tag` | la liaison plusieurs-à-plusieurs d'un item à ses tags ; clé (`item_id`, `tag_id`) | `item_id`, `tag_id` |
| `highlight` | un surlignage d'un PDF d'une entrée Zotero ; catalogue d'état ; clé `zotero_key` | `highlight_id`, `zotero_key`, `text`, `comment`, `highlighted_at`, `revised_at`, `withdrawn_at`, `item_id` |
| `trend` | TENDANCE : les dépôts qui montent d'un classement GH Archive, une ligne par fenêtre de 3 jours et par dépôt ; pas un item ; clé (`window_end`, `repository_id`) | `id`, `raw_data_id`, `window_end`, `repository_id`, `repository_name`, `stars_gained`, `forks_gained` |

- **Mode d'acquisition** : `source.acquisition_mode` vaut `watch`, `library` ou `wiki`, tenu par
  un `CHECK` (journal ADR, 2026-10-10). La durée de conservation de chaque mode est dans
  `src/k_b/core/config.py` ; un test vérifie que chaque mode du `CHECK` y a sa durée.
- **ITEM minimal** : ce que dit un item est dans son sous-type (`release`, `advisory`) ou dans
  son référentiel (`publication`, `vulnerability`). Un sous-type pointe vers son item par la clé
  étrangère composée (`item_id`, `kind`) : un item a un sous-type au plus, celui de sa sorte.
- **Référentiels** : un papier ou une faille existe dès qu'une source le cite. Les colonnes
  données par la source qui fait foi sont remplies si et seulement si `item_id` pointe vers
  l'item de cette source (un `CHECK` de table) ; « exploitée » se lit `item_id IS NOT NULL` dans
  `vulnerability`.
- **Index** : sur les clés étrangères, que SQLite n'indexe pas d'office (`raw_data.source_id`,
  `item.raw_data_id`, `highlight.item_id`, `release.tracked_repository_id`,
  `advisory.vulnerability_id`, `newsletter_article.publication_id`, `trend.raw_data_id`,
  `zotero_entry.publication_id`, `item_has_tag.tag_id` ; `item_has_tag.item_id` est en tête de sa clé
  primaire). Les
  contraintes `UNIQUE` créent
  leur propre index.
- **Suppressions en cascade** : seulement de `item` vers `highlight` et vers `item_has_tag` (#260 ;
  aucun item que la purge supprime ne porte de tag : seuls les clips en portent, et la bibliothèque
  n'est pas purgée, #83 ; un tag dont une réécriture retire la dernière liaison est supprimé avec
  elle, journal ADR, 2026-10-19). Il n'y en a pas vers `publication`, `vulnerability`, `release`,
  `advisory`, `newsletter_article`, `zotero_entry` ni `clip` : supprimer un item qu'une de ces tables référence est refusé par la clé
  étrangère. La purge (`src/k_b/purge/base.py`, SQL dans `src/k_b/database/purge.py`) supprime donc
  les sous-types avant leurs items, et vide un papier encore cité avant de supprimer son item.
- **Formats contrôlés** par un `CHECK` : les dates (ci-dessus) ; `cve_id` (`CVE-AAAA-NNNN…`) ;
  `repository_name` (`owner/repo`) ; `ghsa_id` (`GHSA-…`) ; `url` (`https://…`, ou `http://…`
  pour `zotero_entry` et `clip`) ; `zotero_key` (8 caractères `0-9A-Z`) ; `edition` (lettres minuscules sans accent) ; les listes
  fermées (`source_type`, `acquisition_mode`, `kind`, `ransomware_use`, `ecosystem`) ; les listes
  JSON non vides ; `tag_name` et `tag.name` non vides ; dans `trend`, `window_end` à minuit UTC, `repository_id` > 0,
  `stars_gained` et `forks_gained` ≥ 0 ; les longueurs maximales.

### Ce qui est propre à SQLite

Le MPD est écrit pour SQLite : `schema.sql` fait foi. `schema_postgresql.sql` le suit table par
table, colonne par colonne, chaque `CHECK` traduit ; voici ce qui change, et pourquoi :

| Dans le script SQLite | Pourquoi | En PostgreSQL |
|---|---|---|
| `STRICT` sur chaque table | sinon SQLite accepte une valeur du mauvais type | retiré : typage strict par défaut |
| dates en `TEXT` + `CHECK (… IS strftime(…))` | SQLite n'a pas de type date | `text` encore, typé par le domaine `utc_date` (`utc_day` pour `trend.window_end`) : la forme `AAAA-MM-JJTHH:MM:SSZ` par `~`, l'heure de 00 à 23 (PostgreSQL accepte `24:00:00`), et un jour qui existe par `pg_input_is_valid(…, 'timestamptz')`, qui rend faux là où un cast lèverait une erreur |
| `INTEGER PRIMARY KEY` | numérotation automatique (alias de `rowid`) | `bigint GENERATED BY DEFAULT AS IDENTITY` : comme SQLite, la colonne accepte un `id` donné, ce que font les fixtures des tests |
| `GLOB` dans les `CHECK` (`cve_id`, `repository_name`, `ghsa_id`, `url`, `edition`) | motif simple | `~` (expression régulière), ancrée par `^` et `$` quand `GLOB` couvre toute la valeur |
| `IS` dans les `CHECK` de date | compare sans que `NULL` fasse passer le contrôle | inutile : `~` et `pg_input_is_valid` ne rendent jamais `NULL` pour une valeur donnée |
| `CHECK (length(colonne) <= n)` | SQLite ignore la longueur d'un `VARCHAR(n)` | le même `CHECK` : `varchar(n)` refuserait une valeur trop longue en SQLSTATE 22001, qui arrête l'import au lieu de rejeter l'entrée (`database/errors.py`) |
| listes en `TEXT` + `json_valid`, `json_type`, `json_array_length` | SQLite n'a pas de type JSON | `text` encore, contrôlé par `IS JSON ARRAY`, puis `json_array_length(colonne::json)` dans un `CASE` : le cast ne tourne que sur un tableau JSON |
| `COLLATE NOCASE` sur le nom d'un dépôt suivi | unicité sans tenir compte de la casse | `citext`, dans une base en collation C : la casse des lettres ASCII seules, comme `NOCASE` |
| `PRAGMA foreign_keys = ON` à chaque connexion | clés étrangères ignorées sinon | inutile : toujours vérifiées |
| `PRAGMA journal_mode = WAL` | lire pendant l'écriture | inutile : MVCC |
| `UNIQUE` sur `clip.url` (2 000 caractères au plus) | la clé d'un clip | une entrée d'index B-tree ne peut dépasser environ un tiers de page, 2 704 octets ([B-Tree Indexes](https://www.postgresql.org/docs/current/btree.html), PostgreSQL 18, lu le 2026-10-17), et 2 000 caractères UTF-8 peuvent en faire 8 000 : un index unique sur l'empreinte de l'URL, `md5(url)` |
| `CHECK` de forme des dates de `clip` (`length`, `substr`) | SQL portable, sans `strftime` | les mêmes `CHECK` |

Pourquoi les dates et les listes restent du texte, et non `timestamptz` et `jsonb` : psycopg rendrait
des `datetime` et des listes Python, et une ligne lue sur PostgreSQL différerait de la même ligne lue
sur SQLite ; le SQL de K-B compare les dates en texte (`collected_at < :bound`, `max(…)`), ce qui
reste juste pour des dates UTC d'une seule forme.

Reste identique : les tables, les clés, `UNIQUE`, `ON DELETE CASCADE`, les index, et
`ON CONFLICT (…) DO NOTHING` ou `DO UPDATE`. Le MCD et le MLD ne dépendent d'aucun SGBD.

Vérifié par les tests, sur une base créée par `schema.sql` (`tests/test_schema.py`) : chaque
`CHECK` du script refuse une valeur qu'il interdit, et un `CHECK` ajouté sans sa valeur refusée
fait échouer la suite. Sans `PRAGMA foreign_keys = ON`, une clé étrangère fausse passe : d'où la
règle ci-dessus (`tests/test_database.py`). Sur PostgreSQL (`tests/test_schema_postgresql.py`,
marqué `postgresql`), la ligne valide de chaque table est acceptée, chaque valeur refusée de
`tests/test_schema.py` l'est aussi, en SQLSTATE 23514, et chaque longueur et chaque nombre maximal
de `items.py` est le `CHECK` de sa colonne. La structure des deux scripts est comparée table par
table (`tests/test_schema_structures.py`, marqué `postgresql`) : les mêmes colonnes dans le même
ordre, les mêmes `NOT NULL`, clés primaires, `UNIQUE`, clés étrangères avec leur `ON DELETE`, et
les mêmes index ; seul écart voulu, l'unicité de l'URL d'un clip, tenue par `md5(url)` en
PostgreSQL.

## Faire évoluer le schéma

- **En développement, la base est jetable** : un changement de schéma = supprimer la base,
  `kb create-db`, puis `kb import`, qui la reconstruit depuis le brut. Pas de migration. Cela ne
  vaut que tant que le brut couvre toute la base : dès que le plus ancien brut a 6 mois, la purge le
  supprime (décision de Sabine du 2026-11-04), la base garde des données que le brut n'a plus, et un
  changement de schéma passe par une migration (journal ADR, 2026-10-09, W7), que K-B n'a pas
  encore.
- **En usage réel, la base est gardée** et l'`id` technique des items reste stable : SQLite en
  local, PostgreSQL en ligne (journal ADR, 2026-11-06). Les migrations Alembic écrites en SQL
  (journal ADR, 2026-10-10), pas encore codées, sont à reprendre pour PostgreSQL seulement, avec
  #186, qui attend le premier changement de schéma de la base en ligne : celle-ci part vierge, et
  `kb migrate-database` (#421) n'y pose le schéma que sur une base vide (décision de Sabine du
  2026-11-06, journal ADR). `schema.sql` reste le MPD et fait foi ; un changement de schéma s'écrit aussi dans
  `schema_postgresql.sql`.
- **La base du Mac ne passe pas en ligne** (décision de Sabine du 2026-11-06, journal ADR,
  « Base : la base du Mac est jetable »), **ni son brut** (décision de Sabine du 2026-11-10 : les
  données du Mac sont des essais de développement, pas à garder). La base PostgreSQL en ligne part
  vide : `kb migrate-database` y crée les tables (`caj-kb-migrate-database`, #421), puis la routine
  quotidienne la remplit (#330), en partant de zéro. Les `id` viennent de la séquence de la base en
  ligne. Une colonne
  `GENERATED BY DEFAULT AS IDENTITY` accepte un `id` donné sans avancer sa séquence : une copie de
  lignes avec leur `id`, si elle devenait nécessaire, se finirait par
  `SELECT setval(pg_get_serial_sequence('<table>', '<colonne>'), max(<colonne>)) FROM <table>;`
  pour chaque table, sans quoi le prochain `INSERT` sans `id` heurterait une clé existante.
- Les champs propres d'une source s'ajoutent quand on traite sa lecture : l'issue de la source
  ajoute ses colonnes, leurs longueurs maximales (dans `items.py` et en `CHECK`), et met à jour ce
  document dans sa PR.

## Sources (consultées le 2026-10-02)

- [Appropriate Uses For SQLite](https://www.sqlite.org/whentouse.html)
- [Write-Ahead Logging](https://www.sqlite.org/wal.html) — SQLite ; § 5 « Read-Only Databases »
  consulté le 2026-10-14 : une base WAL se lit sans droit d'écriture si `-shm` et `-wal` existent
  déjà, ou si le dossier permet de les créer (lecture seule).
- [ALTER TABLE](https://www.sqlite.org/lang_altertable.html) — SQLite
- [MVCC](https://www.postgresql.org/docs/current/mvcc-intro.html) — PostgreSQL
- [CREATE SEQUENCE](https://www.postgresql.org/docs/18/sql-createsequence.html) — PostgreSQL 18 ;
  exemple `COPY` puis `SELECT setval('serial', max(id))` (consulté le 2026-10-15, par Context7).
- [Sequence Manipulation Functions](https://www.postgresql.org/docs/18/functions-sequence.html) —
  PostgreSQL 18 ; `setval` (consulté le 2026-10-15, par Context7).
- [INSERT](https://www.postgresql.org/docs/current/sql-insert.html) — PostgreSQL 18 ;
  `OVERRIDING SYSTEM VALUE` pour une colonne `GENERATED ALWAYS` (relevé par recherche web le
  2026-10-15 ; confirmé par Context7 le 2026-10-15, avec
  [Identity Columns](https://www.postgresql.org/docs/18/ddl-identity-columns.html)).
- [System Information Functions](https://www.postgresql.org/docs/current/functions-info.html) —
  PostgreSQL 18 ; `pg_get_serial_sequence` rend aussi la séquence d'une colonne d'identité
  (relevé par recherche web le 2026-10-15 ; Context7 ne rend pas ce passage, le 2026-10-15).
