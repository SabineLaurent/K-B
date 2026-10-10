# Spécifications de stockage et modèles de la base

La base garde le jeu d'items fusionné (étape 4 de [specs-collecte.md](specs-collecte.md)). Ce
document fixe le SGBD, les règles de stockage, ce que chaque source écrit, et le MPD, qui est le
script [`src/k_b/database/schema.sql`](../src/k_b/database/schema.sql). Il décrit le schéma codé.
Les décisions et leur pourquoi sont dans le [journal ADR](ADR/journal-decisions-projet.md) et
dans [la clarification du modèle](2026-10-07-clarification-modele.md) ; pour la base et le
schéma, l'entrée du 2026-10-10 du journal fait foi.

```
collecte → raw/ (brut intact) → lecture + fusion → base
```

La base n'est pas le brut : elle se reconstruit en rejouant la lecture et la fusion sur `raw/`.
Elle ne contient que ce que le brut contient (les papiers arXiv écartés à la requête n'y sont pas).
Ce qui la lira (les commandes `kb search` et `kb top`, une API REST locale) est décidé et pas
encore codé (journal ADR, 2026-10-08 et 2026-10-09).

## Le SGBD : SQLite

Retenu : **SQLite**, un fichier dans le dossier de données, hors du dépôt, lu avec le module
`sqlite3` de la bibliothèque standard. Le dossier de données est donné par la variable
`KB_DATA_DIR` ; le journal ADR du 2026-10-09 le fixe à `~/.knowledge_base`.

| | SQLite (retenu) | PostgreSQL (écarté pour l'instant) |
|---|---|---|
| Installation | aucune : un fichier, rejouable par un tiers | un serveur à installer, lancer et sécuriser |
| Écritures | une à la fois ; ici un seul écrivain, le pipeline | plusieurs en parallèle (MVCC) |
| Lectures pendant l'écriture | oui, en mode WAL | oui (MVCC) |
| Droits | aucun compte : l'API ouvre la base en lecture seule, le fichier est lisible par sa seule propriétaire | rôles SQL, dont un rôle en lecture seule pour l'API |
| Typage | souple par défaut ; strict avec les tables `STRICT` | strict |
| Dépendance | aucune | un pilote (`psycopg`) |

Pourquoi : un utilisateur, un écrivain par jour, quelques milliers d'items par an. Le besoin
est local et léger : un serveur n'apporterait que de la charge. Limite assumée : pas de rôles
dans la base. Une migration vers PostgreSQL reste possible si le besoin change (plusieurs
écrivains, accès distant) ; ce qui est propre à SQLite est listé plus bas.

## Spécifications de stockage

- **Clés étrangères** : SQLite les ignore si la connexion n'exécute pas `PRAGMA foreign_keys = ON`.
  `connect_database` (`src/k_b/database/connection.py`) l'exécute à chaque ouverture.
- **Mode WAL** (`PRAGMA journal_mode = WAL`, gardé dans le fichier) : le pipeline écrit pendant
  que l'API lit, sans se bloquer. Tous les programmes tournent sur la même machine.
- **Dates** : du texte `AAAA-MM-JJTHH:MM:SSZ`, en UTC. Un `CHECK` refuse toute autre forme, et
  un jour qui n'existe pas. Une source qui ne donne qu'un jour (`dateAdded` de CISA KEV) est
  stockée à minuit UTC : convention d'écriture, pas de donnée ajoutée.
- **Types** : tables `STRICT`, une valeur du mauvais type est refusée.
- **Identifiants** : chaque table du modèle clarifié a un `id` technique pour clé primaire ;
  l'identifiant naturel de chaque chose est tenu par une contrainte `UNIQUE` : `arxiv_id`,
  `cve_id`, `release_id`, `ghsa_id`, `raw_file_path`, `source_code`, le nom d'un dépôt suivi
  (sans tenir compte de la casse), `zotero_key`. Un item n'a plus d'URL commune ni d'URL unique.
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
  `release` et `advisory`.
- **Listes JSON** : le nombre d'éléments est borné deux fois, par l'item et par un
  `CHECK (json_array_length(colonne) <= n)`. La longueur de chaque élément n'est tenue que par
  l'item : un `CHECK` de SQLite ne peut pas parcourir les éléments d'une liste (pas de
  sous-requête dans un `CHECK`).
- **Colonnes sans borne** : celles que le code remplit (`source`, `tracked_repository`, le chemin
  et le flux de `raw_data`) ; les dates et les listes fermées, tenues par leur propre `CHECK` ;
  `highlight`, pas encore remplie, dont les bornes sont à fixer avec son lecteur ; `repository`
  et `star_gain` (voir le MPD).
- **Limite de SQLite** : `length()` compte les caractères jusqu'au premier caractère NUL. Un
  texte qui en contient un peut donc passer le `CHECK` en étant plus long ; l'item, lui, compte
  tous les caractères.

### Ce que chaque source met dans l'item, puis dans la base

Les lecteurs écrits à ce jour : arXiv, CISA KEV, releases et alertes GitHub. Chaque entrée du
brut devient un item (`src/k_b/items.py`), que l'import (`src/k_b/import_items.py`) écrit dans la
table de sa sorte (`kind`).

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
- Pas encore lus : les pages tldr.tech, les clips du Web Clipper, Zotero, GH Archive. Le
  classement des dépôts les plus étoilés n'entre pas dans la base (journal
  ADR, 2026-10-07).

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
| `highlight` | les surlignages Zotero ; pas encore remplie | `highlight_id`, `zotero_key`, `text`, `highlighted_at`, `item_id` |
| `repository`, `star_gain` | tables du modèle précédent, sans écrivain ; la clarification du modèle les remplace par TENDANCE, pas encore codée | `item_id`, `repository_name` ; `item_id`, `window_end`, `stars_gained` |

- **Mode d'acquisition** : `source.acquisition_mode` vaut `watch`, `library` ou `wiki`, tenu par
  un `CHECK` (journal ADR, 2026-10-10). La durée de conservation de chaque mode est dans
  `src/k_b/config.py` ; un test vérifie que chaque mode du `CHECK` y a sa durée.
- **ITEM minimal** : ce que dit un item est dans son sous-type (`release`, `advisory`) ou dans
  son référentiel (`publication`, `vulnerability`). Un sous-type pointe vers son item par la clé
  étrangère composée (`item_id`, `kind`) : un item n'a qu'un sous-type, celui de sa sorte.
- **Référentiels** : un papier ou une faille existe dès qu'une source le cite. Les colonnes
  données par la source qui fait foi sont remplies si et seulement si `item_id` pointe vers
  l'item de cette source (un `CHECK` de table) ; « exploitée » se lit `item_id IS NOT NULL` dans
  `vulnerability`.
- **Index** : sur les clés étrangères, que SQLite n'indexe pas d'office (`raw_data.source_id`,
  `item.raw_data_id`, `highlight.item_id`, `release.tracked_repository_id`,
  `advisory.vulnerability_id`), et sur `star_gain.window_end`. Les contraintes `UNIQUE` créent
  leur propre index.
- **Suppressions en cascade** : seulement de `item` vers `highlight` et `repository`, et de
  `repository` vers `star_gain`. Il n'y en a pas vers `publication`, `vulnerability`, `release`
  ni `advisory` : supprimer un item qu'une de ces tables référence est refusé par la clé
  étrangère. La purge n'est pas codée.
- **Formats contrôlés** par un `CHECK` : les dates (ci-dessus) ; `cve_id` (`CVE-AAAA-NNNN…`) ;
  `repository_name` (`owner/repo`) ; `ghsa_id` (`GHSA-…`) ; `url` (`https://…`) ; les listes
  fermées (`source_type`, `acquisition_mode`, `kind`, `ransomware_use`, `ecosystem`) ; les listes
  JSON non vides ; `tag_name` non vide ; `stars_gained` ≥ 0 ; les longueurs maximales.

### Ce qui est propre à SQLite

Le MPD est écrit pour SQLite. Pour migrer vers un autre SGBD, voici ce qui change, avec
l'équivalent PostgreSQL :

| Dans le script SQLite | Pourquoi | En PostgreSQL |
|---|---|---|
| `STRICT` sur chaque table | sinon SQLite accepte une valeur du mauvais type | inutile : typage strict par défaut |
| dates en `TEXT` + `CHECK (… IS strftime(…))` | SQLite n'a pas de type date | `timestamptz`, sans `CHECK` de format |
| `INTEGER PRIMARY KEY` | numérotation automatique (alias de `rowid`) | `bigint GENERATED ALWAYS AS IDENTITY` |
| `GLOB` dans les `CHECK` (`cve_id`, `repository_name`, `ghsa_id`, `url`) | motif simple | `~` (expression régulière) |
| `IS` dans les `CHECK` de date | compare sans que `NULL` fasse passer le contrôle | `IS NOT DISTINCT FROM` |
| `CHECK (length(colonne) <= n)` | SQLite ignore la longueur d'un `VARCHAR(n)` | `varchar(n)` |
| listes en `TEXT` + `json_valid`, `json_type`, `json_array_length` | SQLite n'a pas de type JSON | `jsonb`, `jsonb_typeof`, `jsonb_array_length` |
| `COLLATE NOCASE` sur le nom d'un dépôt suivi | unicité sans tenir compte de la casse | un index unique sur `lower(colonne)` |
| `PRAGMA foreign_keys = ON` à chaque connexion | clés étrangères ignorées sinon | inutile : toujours vérifiées |
| `PRAGMA journal_mode = WAL` | lire pendant l'écriture | inutile : MVCC |

Reste identique : les tables, les clés, `UNIQUE`, `ON DELETE CASCADE`, les index, et
`ON CONFLICT (…) DO NOTHING` ou `DO UPDATE`. Le MCD et le MLD ne dépendent d'aucun SGBD.

Vérifié par les tests, sur une base créée par `schema.sql` (`tests/test_schema.py`) : chaque
`CHECK` du script refuse une valeur qu'il interdit, et un `CHECK` ajouté sans sa valeur refusée
fait échouer la suite. Sans `PRAGMA foreign_keys = ON`, une clé étrangère fausse passe : d'où la
règle ci-dessus (`tests/test_database.py`).

## Faire évoluer le schéma

- **En développement, la base est jetable** : un changement de schéma = supprimer la base,
  `kb create-db`, puis `kb import`, qui la reconstruit depuis le brut. Pas de migration.
- **En usage réel, la base est gardée** et l'`id` technique des items reste stable : les
  changements de schéma passeront par des migrations Alembic écrites en SQL (journal ADR,
  2026-10-10), pas encore codées. `schema.sql` reste le MPD et fait foi ; un test comparera la
  base créée par `schema.sql` et la base migrée.
- Les champs propres d'une source s'ajoutent quand on traite sa lecture : l'issue de la source
  ajoute ses colonnes, leurs longueurs maximales (dans `items.py` et en `CHECK`), et met à jour ce
  document dans sa PR.

## Sources (consultées le 2026-10-02)

- [Appropriate Uses For SQLite](https://www.sqlite.org/whentouse.html)
- [Write-Ahead Logging](https://www.sqlite.org/wal.html) — SQLite
- [ALTER TABLE](https://www.sqlite.org/lang_altertable.html) — SQLite
- [MVCC](https://www.postgresql.org/docs/current/mvcc-intro.html) — PostgreSQL
