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

La base n'est pas le brut : elle se reconstruit en rejouant la lecture et l'import sur `raw/`, à
une limite près : après un catalogue CISA importé en retard, les dates d'une ligne (`revised_at`,
`withdrawn_at`) et le fichier rattaché à son item peuvent différer, pas son contenu (étape 4 de
[specs-collecte.md](specs-collecte.md)). `kb import` n'importe que les fichiers bruts pas encore
importés : leur registre est la table `raw_data`.
Elle ne contient que ce que le brut contient (les papiers arXiv écartés à la requête n'y sont pas).
Elle est lue par l'API de données, lancée par `kb serve` ([specs-api.md](specs-api.md)) : routes
`/items`, `/items/{item_id}` et `/trends` (`src/k_b/data_api/routers/item_router.py`,
`trend_router.py`), qui ouvrent la base en lecture seule (`src/k_b/data_api/dependencies.py`,
`connect_database_read_only`). Le code des fiches de veille (`src/k_b/ai_api/`) n'ouvre pas la
base : il lit la veille par l'API de données (`ai_api/connectors/data_api_client.py`), et n'est
pas encore servi (#156). `kb search` vient après le 08/11 (journal ADR, 2026-10-15, « POC du
25/10 », décision 1).

## Le SGBD : SQLite au POC du 25/10, PostgreSQL au 08/11

Retenu au POC du 25/10 : **SQLite**, un fichier dans le dossier de données, hors du dépôt, lu avec le module
`sqlite3` de la bibliothèque standard. Le dossier de données est donné par la variable
`KB_DATA_DIR` ; le journal ADR du 2026-10-09 le fixe à `~/.knowledge_base`.

| | SQLite (au POC du 25/10) | PostgreSQL (prévu au 08/11) |
|---|---|---|
| Installation | aucune : un fichier, rejouable par un tiers | un serveur à installer, lancer et sécuriser |
| Écritures | une à la fois ; ici un seul écrivain, le pipeline | plusieurs en parallèle (MVCC) |
| Lectures pendant l'écriture | oui, en mode WAL | oui (MVCC) |
| Droits | aucun compte : l'API ouvre la base en lecture seule, le fichier est lisible par sa seule propriétaire | rôles SQL, dont un rôle en lecture seule pour l'API |
| Typage | souple par défaut ; strict avec les tables `STRICT` | strict |
| Dépendance | aucune | un pilote (`psycopg`) |

Pourquoi SQLite au POC du 25/10 : un utilisateur, un écrivain par jour, quelques milliers
d'items par an ; en localhost, un fichier suffit. Limite assumée : pas de rôles dans la base.
Pourquoi PostgreSQL au 08/11 : sur Azure Container Apps, un fichier SQLite n'a pas de disque
fiable (journal ADR, 2026-10-15, « POC du 25/10 », décision 2). D'ici là, aucun SQL propre à
SQLite n'est ajouté (règle 1 de `.claude/rules/poc.md`) ; ce qui l'est déjà est listé plus bas,
avec son équivalent PostgreSQL.

## Spécifications de stockage

- **Clés étrangères** : SQLite les ignore si la connexion n'exécute pas `PRAGMA foreign_keys = ON`.
  `connect_database` et `connect_database_read_only` (`src/k_b/database/connection.py`)
  l'exécutent à chaque ouverture.
- **Mode WAL** (`PRAGMA journal_mode = WAL`, gardé dans le fichier) : le pipeline écrit pendant
  que l'API lit, sans se bloquer. Tous les programmes tournent sur la même machine.
- **Lecture seule** : `connect_database_read_only` ouvre la base en `mode=ro`, pour l'API de
  données. Une lecture en `mode=ro` crée les fichiers `-shm`
  et `-wal` s'ils manquent, dans le dossier de la base, et les laisse à sa fermeture
  (documentation SQLite, WAL, § 5 ; constat sur SQLite 3.50.4).
- **Dates** : du texte `AAAA-MM-JJTHH:MM:SSZ`, en UTC. Un `CHECK` refuse toute autre forme, et
  un jour qui n'existe pas. Exception, `clip` (#14), écrite en SQL portable (règle 1 de
  `.claude/rules/poc.md`, sans `strftime`) : son `CHECK` ne tient que la longueur et la place du
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
  que l'item les compte tous. Les deux contrôles peuvent donc diverger, dans les deux sens : un
  texte qui contient un NUL peut passer le `CHECK` en étant plus long que le maximum ; un
  `tag_name` qui commence par un NUL est accepté par l'item (3 caractères pour `"\0v1"`) et refusé
  par `CHECK (length(tag_name) > 0)`, ce qui annule l'import entier. Ce second cas n'est pas
  traité. Pour `trend`, il l'est : `GLOB` s'arrête lui aussi au premier NUL, et `TrendRow` refuse
  un nom de dépôt qui contient un caractère de contrôle, NUL compris.

### Ce que chaque source met dans l'item, puis dans la base

Les lecteurs écrits à ce jour : arXiv, CISA KEV, releases et alertes GitHub, tldr.tech, Zotero,
Web Clipper. Chaque entrée du brut devient un item (`src/k_b/items.py`), que l'import
(`src/k_b/etl/load.py`) fait écrire dans la table de sa sorte (`kind`) par l'écrivain de cette
sorte (`src/k_b/database/writers/`), choisi par `src/k_b/database/writing.py`. Exception :
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
  - Un texte de surlignage n'est pas contrôlé pour le caractère NUL, comme les autres textes
    (« Limite de SQLite » ci-dessus).
- **Web Clipper** (#14, journal ADR, 2026-10-17) : un clip a un `item.id` technique, comme les
  autres items ; son URL sans `utm_*` est sa clé naturelle. Ne vont pas en base : `author`,
  `description`, `tags` ; ils restent dans la copie brute. Le texte gardé (`clip.body`) peut
  contenir la signature de l'article et les notes de l'utilisatrice
  ([registre des traitements](registre-traitements.md)). Un clip déjà en base n'est jamais
  remplacé : la première version vue d'une URL est gardée.
- Le classement des dépôts les plus étoilés n'entre pas dans la base (journal ADR, 2026-10-07).

## MCD et MLD

Le MCD et le MLD sont dessinés avec draw.io, dans [`docs/merise/`](merise/) (journal ADR,
2026-10-08) : `mcd-k-b.drawio` et `mld-k-b.drawio`. Ils ne sont pas recopiés ici. Leur mise au
niveau des décisions du 2026-10-10 (le mode d'acquisition devient une colonne de SOURCE) est une
tâche à part, qui suit la réécriture du schéma.

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
| `clip` | sous-type d'item : une page gardée avec Web Clipper ; flux de nouveautés ; clé `url` | `id`, `item_id`, `kind`, `url`, `title`, `body`, `saved_at`, `published_at` |
| `highlight` | un surlignage d'un PDF d'une entrée Zotero ; catalogue d'état ; clé `zotero_key` | `highlight_id`, `zotero_key`, `text`, `comment`, `highlighted_at`, `revised_at`, `withdrawn_at`, `item_id` |
| `trend` | TENDANCE : les dépôts qui montent d'un classement GH Archive, une ligne par fenêtre de 3 jours et par dépôt ; pas un item ; clé (`window_end`, `repository_id`) | `id`, `raw_data_id`, `window_end`, `repository_id`, `repository_name`, `stars_gained`, `forks_gained` |

- **Mode d'acquisition** : `source.acquisition_mode` vaut `watch`, `library` ou `wiki`, tenu par
  un `CHECK` (journal ADR, 2026-10-10). La durée de conservation de chaque mode est dans
  `src/k_b/core/config.py` ; un test vérifie que chaque mode du `CHECK` y a sa durée.
- **ITEM minimal** : ce que dit un item est dans son sous-type (`release`, `advisory`) ou dans
  son référentiel (`publication`, `vulnerability`). Un sous-type pointe vers son item par la clé
  étrangère composée (`item_id`, `kind`) : un item n'a qu'un sous-type, celui de sa sorte.
- **Référentiels** : un papier ou une faille existe dès qu'une source le cite. Les colonnes
  données par la source qui fait foi sont remplies si et seulement si `item_id` pointe vers
  l'item de cette source (un `CHECK` de table) ; « exploitée » se lit `item_id IS NOT NULL` dans
  `vulnerability`.
- **Index** : sur les clés étrangères, que SQLite n'indexe pas d'office (`raw_data.source_id`,
  `item.raw_data_id`, `highlight.item_id`, `release.tracked_repository_id`,
  `advisory.vulnerability_id`, `newsletter_article.publication_id`, `trend.raw_data_id`,
  `zotero_entry.publication_id`). Les
  contraintes `UNIQUE` créent
  leur propre index.
- **Suppressions en cascade** : seulement de `item` vers `highlight`. Il n'y en a pas vers `publication`, `vulnerability`, `release`,
  `advisory`, `newsletter_article`, `zotero_entry` ni `clip` : supprimer un item qu'une de ces tables référence est refusé par la clé
  étrangère. La purge n'est pas codée.
- **Formats contrôlés** par un `CHECK` : les dates (ci-dessus) ; `cve_id` (`CVE-AAAA-NNNN…`) ;
  `repository_name` (`owner/repo`) ; `ghsa_id` (`GHSA-…`) ; `url` (`https://…`, ou `http://…`
  pour `zotero_entry` et `clip`) ; `zotero_key` (8 caractères `0-9A-Z`) ; `edition` (lettres minuscules sans accent) ; les listes
  fermées (`source_type`, `acquisition_mode`, `kind`, `ransomware_use`, `ecosystem`) ; les listes
  JSON non vides ; `tag_name` non vide ; dans `trend`, `window_end` à minuit UTC, `repository_id` > 0,
  `stars_gained` et `forks_gained` ≥ 0 ; les longueurs maximales.

### Ce qui est propre à SQLite

Le MPD est écrit pour SQLite. Pour migrer vers un autre SGBD, voici ce qui change, avec
l'équivalent PostgreSQL :

| Dans le script SQLite | Pourquoi | En PostgreSQL |
|---|---|---|
| `STRICT` sur chaque table | sinon SQLite accepte une valeur du mauvais type | inutile : typage strict par défaut |
| dates en `TEXT` + `CHECK (… IS strftime(…))` | SQLite n'a pas de type date | `timestamptz`, sans `CHECK` de format |
| `INTEGER PRIMARY KEY` | numérotation automatique (alias de `rowid`) | `bigint GENERATED ALWAYS AS IDENTITY` |
| `GLOB` dans les `CHECK` (`cve_id`, `repository_name`, `ghsa_id`, `url`, `edition`) | motif simple | `~` (expression régulière) |
| `IS` dans les `CHECK` de date | compare sans que `NULL` fasse passer le contrôle | `IS NOT DISTINCT FROM` |
| `CHECK (length(colonne) <= n)` | SQLite ignore la longueur d'un `VARCHAR(n)` | `varchar(n)` |
| listes en `TEXT` + `json_valid`, `json_type`, `json_array_length` | SQLite n'a pas de type JSON | `jsonb`, `jsonb_typeof`, `jsonb_array_length` |
| `COLLATE NOCASE` sur le nom d'un dépôt suivi | unicité sans tenir compte de la casse | un index unique sur `lower(colonne)` |
| `PRAGMA foreign_keys = ON` à chaque connexion | clés étrangères ignorées sinon | inutile : toujours vérifiées |
| `PRAGMA journal_mode = WAL` | lire pendant l'écriture | inutile : MVCC |
| `UNIQUE` sur `clip.url` (2 000 caractères au plus) | la clé d'un clip | une entrée d'index B-tree ne peut dépasser environ un tiers de page, 2 704 octets ([B-Tree Indexes](https://www.postgresql.org/docs/current/btree.html), PostgreSQL 18, lu le 2026-10-17), et 2 000 caractères UTF-8 peuvent en faire 8 000 : un index unique sur une empreinte de l'URL |
| `CHECK` de forme des dates de `clip` (`length`, `substr`) | SQL portable, sans `strftime` | `timestamptz`, sans `CHECK` de format, comme les autres dates |

Reste identique : les tables, les clés, `UNIQUE`, `ON DELETE CASCADE`, les index, et
`ON CONFLICT (…) DO NOTHING` ou `DO UPDATE`. Le MCD et le MLD ne dépendent d'aucun SGBD.

Vérifié par les tests, sur une base créée par `schema.sql` (`tests/test_schema.py`) : chaque
`CHECK` du script refuse une valeur qu'il interdit, et un `CHECK` ajouté sans sa valeur refusée
fait échouer la suite. Sans `PRAGMA foreign_keys = ON`, une clé étrangère fausse passe : d'où la
règle ci-dessus (`tests/test_database.py`).

## Faire évoluer le schéma

- **En développement, la base est jetable** : un changement de schéma = supprimer la base,
  `kb create-db`, puis `kb import`, qui la reconstruit depuis le brut. Pas de migration.
- **En usage réel, la base est gardée** et l'`id` technique des items reste stable. SQLite au
  25/10, PostgreSQL au 08/11 (journal ADR, 2026-10-15, « POC du 25/10 », décision 2) : les
  migrations Alembic écrites en SQL (journal ADR, 2026-10-10), pas encore codées, sont à reprendre
  pour PostgreSQL seulement, avec #186. `schema.sql` reste le MPD et fait foi.
- **Au passage à PostgreSQL, l'`id` est copié tel quel.** Les lignes de chaque table sont
  copiées avec leur `id` ; un `INSERT` dans une colonne `GENERATED ALWAYS AS IDENTITY` (tableau
  ci-dessus) ne l'accepte qu'avec `OVERRIDING SYSTEM VALUE`. Puis la séquence de chaque table est
  recalée sur le plus grand `id` copié, sans quoi le prochain `INSERT` sans `id` reprendrait à 1
  et heurterait une clé existante :
  `SELECT setval(pg_get_serial_sequence('<table>', '<colonne>'), max(<colonne>)) FROM <table>;`
  pour les 12 tables à `INTEGER PRIMARY KEY` de `schema.sql`, `highlight_id` compris.
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
