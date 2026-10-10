# Tables de référence, mode d'acquisition et `config.py`

- **Date** : 2026-10-10
- **Branche** : `feat/schema-reference-tables`
- **Issue** : #119 (réécrire le schéma, 1/4)
- **Fichiers principaux** : `src/k_b/database/schema.sql`, `src/k_b/database/seed_sources.sql`,
  `src/k_b/config.py`, `src/k_b/import_items.py`, `src/k_b/raw_store.py`,
  `src/k_b/database/creation.py`
- **Série** : fait suite à [Sortir le code de `database/__init__.py`](2026-10-10-sortir-le-code-du-init-de-database.md),
  dont le commentaire de clôture (#119, 10/10) demandait de revoir le nom `connection`.

## Le pourquoi

Le modèle clarifié du 07 au 10/10 remplace le schéma codé. Cette première étape pose les tables
sur lesquelles les trois suivantes s'appuient :

- **SOURCE** reçoit un `id` technique, et son **mode d'acquisition** (`watch` pour la veille,
  `library` pour la bibliothèque choisie, `wiki` pour le futur wiki LLM). La purge (#83) en a
  besoin : sans le mode, un document de la bibliothèque purgé à 2 ans serait recréé à la collecte
  suivante.
- **DONNÉE BRUTE** (`raw_data`) remplace `collection` : un fichier de `raw/`, fourni par une
  source (association FOURNIR), avec son flux. Avant, rien en base ne reliait un fichier brut à sa
  source.
- **`config.py`** accueille la durée de conservation par mode : c'est un réglage, pas un fait du
  code (ADR du 10/10, « Configuration »).

ITEM et ses sous-types ne changent pas ici (#120), ni les règles de dédoublonnage (#105).

## Le comment

### 1. Le mode d'acquisition : une colonne tenue par un `CHECK`

`src/k_b/database/schema.sql:16`

```sql
acquisition_mode TEXT NOT NULL CHECK (acquisition_mode IN ('watch', 'library', 'wiki'))
```

La base refuse toute autre valeur, et une source sans mode. C'est la décision du 10/10, qui
remplace la table ACQUISITION_MODE du 09/10 : une table, un modèle et une jointure pour trois
lignes qui ne portaient plus qu'un code et un libellé, une fois la durée sortie vers `config.py`.
Le seed (`seed_sources.sql:4-12`) donne `watch` aux sources de `raw/automated_watch/` et `library`
à `clipper` et `zotero`, destinées à `raw/selected_library/` (ADR du 09/10).

### 2. Un `id` technique, l'identifiant naturel en `UNIQUE`

`src/k_b/database/schema.sql:9-10`

```sql
id               INTEGER PRIMARY KEY,
source_code      TEXT NOT NULL UNIQUE,
```

`source_code` reste unique et lisible (CLI, `SourceCode` de `items.py`), mais les jointures
nouvelles passent par `id` (règle de la séance 2). `item.source_code REFERENCES source
(source_code)` reste valide : SQLite accepte une clé étrangère vers une colonne `UNIQUE`. ITEM
garde son `item_id` ; son `id` technique viendra avec #120.

### 3. `raw_data` : la donnée brute reliée à sa source

`src/k_b/database/schema.sql:21-25`

```sql
CREATE TABLE raw_data (
    id            INTEGER PRIMARY KEY,
    source_id     INTEGER NOT NULL REFERENCES source (id),
    raw_file_path TEXT NOT NULL UNIQUE,
    stream        TEXT NOT NULL,
```

`source_id NOT NULL` traduit FOURNIR (1,1 côté donnée brute : une donnée brute a une seule
source). `stream` est le flux du MCD, nommé comme au MLD. Rien n'oblige une donnée brute à avoir
un item : CONTENIR est en 0,n de ce côté. `item.collection_id` devient `raw_data_id`
(`schema.sql:45`) : seule conséquence du renommage sur ITEM.

### 4. L'import remplit `raw_data`, et échoue fermé sur une source inconnue

`src/k_b/import_items.py:127-131`

```python
source_row = connection.execute(
    "SELECT id FROM source WHERE source_code = ?", (source_code,)
).fetchone()
if source_row is None:
    raise UnknownSourceError(f"source_code not in the source table: {source_code}")
```

Deux requêtes plutôt qu'un `INSERT … SELECT … FROM source` : ce dernier n'insère rien, sans
erreur, quand le code manque, et la ligne suivante aurait levé un `TypeError` sur `None`. Ici,
l'échec est un état nommé, testable (`UnknownSourceError`). Comme toute l'écriture est dans une
transaction (`import_items.py`, `with connection:`), rien n'est écrit.

### 5. Le flux se lit dans le chemin, là où le rangement du brut est connu

`src/k_b/raw_store.py:15-21`

```python
def find_stream(raw_file_path: str) -> str:
    ...
    parts = PurePosixPath(raw_file_path).parts
    if len(parts) < 3:
        raise ValueError(f"raw file path without a source folder: {raw_file_path}")
    return parts[1]
```

Le flux est, par définition, le nom du dossier brut de la source : `automated_watch/<flux>/…`.
`raw_store.py` définit déjà `AUTOMATED_WATCH_DIR_NAME` : la connaissance du rangement reste en un
seul endroit. Un chemin trop court est refusé plutôt que deviné.

### 6. `config.py` et le test qui le tient à `schema.sql`

`src/k_b/config.py:8-12`

```python
RETENTION_YEARS_BY_ACQUISITION_MODE: dict[str, int | None] = {
    "watch": 2,
    "library": None,
    "wiki": None,
}
```

La même liste de modes est écrite deux fois (le `CHECK` et ce dictionnaire). Le test
`tests/test_schema.py:44` lit les valeurs du `CHECK` dans `schema.sql` par expression régulière
et les compare aux clés : ajouter un mode d'un seul côté fait échouer la CI.

Le découpage demandé par le commentaire du 10/10 : `database/connection.py` ne fait plus qu'ouvrir
la base (`connect_database`), `database/creation.py` la crée (`create_database`,
`DATABASE_SCRIPTS`). `tests/test_schema.py` importe `DATABASE_SCRIPTS` au lieu de le redéfinir.

## Choix faits et options écartées

| Choix | Retenu, pourquoi | Écarté, pourquoi |
|---|---|---|
| Mode d'acquisition | colonne + `CHECK` (ADR du 10/10, décision de Sabine) | table ACQUISITION_MODE : trois lignes, une jointure, plus rien à porter |
| Forme de la durée | nombre d'années (`int`) : la décision dit « 2 ans » | `timedelta(days=730)` : pas exactement 2 ans (années bissextiles) |
| `library`, `wiki` | `None`, pas de durée fixée par K-B (Sabine, 10/10 ; registre, fiche 2) | 2 ans pour tous ; une valeur non numérique (« dernière copie », règle propre aux bruts Zotero, #15) |
| Nom du flux | `stream` (MLD, identifiants en anglais) ; validé par Sabine | `flux` (texte de l'issue) |
| Origine du flux | lu dans le chemin, dans `raw_store.py` | un champ `stream` dans `Item` (touche tous les lecteurs, #120) ; découper le chemin dans `import_items.py` (troisième copie du rangement) |
| Écriture de `raw_data` | deux requêtes, erreur nommée | `INSERT … SELECT` : n'insère rien sans le dire |
| Module de la base | `connection.py` + `creation.py` (Sabine, 10/10) | garder `connection.py` (le nom ne dit pas la création) ; `setup.py` (se confond avec l'empaquetage) |
| Type des modes en Python | aucun `Literal` | une troisième copie de la liste, sans usage avant la purge |

Imposé par les consignes : requêtes paramétrées (`code.md`), une connaissance à un seul endroit
(`code.md`, DRY), `config` déclaré module générique (`tests/test_module_dependencies.py`).

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_each_acquisition_mode_of_the_schema_has_a_retention_in_the_config` | chaque valeur du `CHECK` a une durée dans `config.py`, et l'inverse (critère 1) |
| `tests/test_items.py::test_the_source_codes_are_those_of_the_database` | `SourceCode` = codes du seed (critère 2, test existant, vert avec le nouveau seed) |
| `test_an_acquisition_mode_outside_the_list_is_refused` | `'archive'` est refusé par la base (critère 3) |
| `test_each_seeded_source_has_its_acquisition_mode` | le mode de chaque source du seed |
| `test_a_raw_data_of_an_unknown_source_is_refused` | FOURNIR tenu par la clé étrangère |
| `test_an_item_points_to_the_raw_file_and_date_of_its_collection` | l'import remplit `stream` et `source_id` |
| `test_an_item_of_a_source_missing_from_the_database_is_refused` | `UnknownSourceError`, et aucun item écrit |
| `tests/test_raw_store.py` (3 cas de `find_stream`) | flux d'un fichier et d'une page TLDR ; chemin trop court refusé |
| Casse volontaire : `wiki` retiré de `config.py`, puis du `CHECK`, puis le `CHECK` entier, puis une source du seed | le test du critère 1 échoue dans les trois premiers cas, le test du critère 3 dans le troisième, 4 tests dans le dernier |
| `kb create-db` puis `kb import` sur la collecte du 2026-10-07 | 2 500 items (arxiv 511, cisa_kev 1 734, github 255), 5 lignes `raw_data`, comme sur `main` |

## Ce que tu dois pouvoir défendre

1. **Pourquoi un `CHECK` et pas une table de référence ?** Trois valeurs stables, plus rien à
   porter une fois la durée en configuration ; le coût est qu'ajouter un mode demande de recréer
   SOURCE (migration), ce qui est rare (`wiki` en v1). `schema.sql:16`, ADR du 10/10.
2. **Que se passe-t-il si on ajoute un mode au `CHECK` sans durée ?** Le test de
   `tests/test_schema.py:44` échoue en CI : la PR ne se fusionne pas.
3. **Pourquoi `item.source_code` et `raw_data.source_id` coexistent-ils ?** ITEM est hors
   périmètre ; la redondance est temporaire, la base ne vérifie pas encore leur accord (#120
   réécrit ITEM). `schema.sql:23`, `schema.sql:45`.
4. **Où est la sécurité ?** Requêtes paramétrées (`import_items.py:127-145`) ; échec fermé et
   nommé sur une source inconnue ou un chemin sans dossier de source ; le chemin du brut est
   calculé par K-B depuis le dossier lu, pas tiré du contenu d'un fichier.
5. **Pourquoi `None` pour la bibliothèque ?** Le registre (fiche 2) dit que Zotero et le coffre
   sont gérés par l'utilisatrice dans ces outils, pas par K-B ; c'est la décision de Sabine du
   10/10, à revoir avec la purge.

## Zones non vérifiées

- Le test du critère 1 lit le `CHECK` par expression régulière : il suppose que `schema.sql`
  garde la forme `acquisition_mode IN (…)` sur une ligne. Une écriture différente ferait échouer
  le test (il ne passerait pas en silence : `(allowed_values,) = …` exige exactement une
  correspondance).
- Aucune base existante n'est migrée : une base créée avant cette PR est à supprimer puis
  recréer (base jetable en développement, issue #119).

## Ce qui reste

- ITEM minimal, `id` technique d'ITEM, accord entre `item.source_code` et la source de sa donnée
  brute : #120.
- Enregistrer aussi les bruts qui n'apportent aucun item (CONTENIR 0,n) : non demandé, non codé ;
  aujourd'hui, comme avant, seuls les bruts qui apportent un item entrent dans `raw_data`.
- La purge qui lit `config.py` : #83. Les autres paramètres de `config.py` : issue à part.
- Docs en retard sur l'ADR du 10/10, laissées en l'état : `clarification-modele.md` et les deux
  schémas draw.io (table ACQUISITION_MODE), `docs/stockage.md` (`collection`).
