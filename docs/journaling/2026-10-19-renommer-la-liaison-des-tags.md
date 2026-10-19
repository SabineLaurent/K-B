# Renommer la liaison des tags : `item_tag` devient `item_has_tag`

- **Date** : 2026-10-19
- **Branche** : `refactor/item-has-tag`
- **Issue** : #263
- **Fichiers principaux** : `src/k_b/database/schema.sql`, `src/k_b/database/writers/clip_writer.py`,
  `tests/test_schema.py`, `tests/etl/test_load_clips.py`
- **Série** : suite de [Garder les tags des clips](2026-10-19-garder-les-tags-des-clips.md) (#260),
  qui a créé la table.

## Le pourquoi

#260 a créé la table de liaison d'un item à ses tags sous le nom `item_tag`. Sabine garde le
nom `item_has_tag` au MLD et au MPD (décision du 2026-10-19 : « je préfère garder item_has_tag
en mld et mpd ») : le nom de la table dans le code suit. Le changement ne touche aucun
comportement : mêmes colonnes, mêmes contraintes, même cascade. C'est la première des cinq PR
de la mission du jour, la plus petite.

## Le comment

### 1. La table et son index

```sql
CREATE TABLE item_has_tag (
    item_id INTEGER NOT NULL REFERENCES item (id) ON DELETE CASCADE,
```
(`src/k_b/database/schema.sql:334-335`)

```sql
CREATE INDEX item_has_tag_tag_id ON item_has_tag (tag_id);
```
(`src/k_b/database/schema.sql:340`)

L'index porte un nom au format `<table>_<colonne>`, comme les huit autres du schéma
(`raw_data_source_id`, `item_raw_data_id`…) : renommer la table sans l'index aurait laissé le
seul nom qui ne suit pas ce format. Un `grep "item_tag\b"` ne voit pas l'ancien nom de l'index
(`item_tag_tag_id` continue après `item_tag` par un `_`, qui est un caractère de mot) : il a été
relevé et renommé à part.

### 2. Les constantes SQL de l'écrivain des clips

```python
INSERT_ITEM_HAS_TAG = (
    "INSERT INTO item_has_tag (item_id, tag_id) VALUES (:item_id, :tag_id)"
)
```
(`src/k_b/database/writers/clip_writer.py:41-43`)

Les deux constantes qui nomment la table (`INSERT_ITEM_TAG`, `DELETE_ITEM_TAG`) prennent son
nouveau nom ; `SELECT_ITEM_TAGS` garde le sien, parce qu'il dit ce qu'il rend (les tags d'un
item), pas la table qu'il lit. Le passage à la ligne entre parenthèses vient de `ruff format` :
la ligne dépassait la longueur permise. Dans `DELETE_TAG_WITHOUT_LINK`, la condition
`NOT EXISTS` passe à la ligne pour la même raison (`clip_writer.py:61-63`).

### 3. Les tests d'abord

Les tests nomment la table : la liste des tables attendues (`EXPECTED_TABLES`,
`tests/test_schema.py:48`), comparée au schéma chargé par
`test_the_schema_and_the_sources_load_with_every_expected_table` (`tests/test_schema.py:77`), et
le message de SQLite attendu pour un doublon :

```python
        sqlite3.IntegrityError, match="UNIQUE constraint failed: item_has_tag"
```
(`tests/test_schema.py:1222`)

Renommés avant le schéma, ils échouaient (14 en rouge), puis passaient avec lui. Aucun test ne
lit le nom d'un index : le renommage de l'index se prouve par `grep` (section « Preuve »).

### 4. Une base existante : recréée, sans migration

`kb create-db` refuse un fichier existant (`src/k_b/database/creation.py:17-18`) et le dépôt n'a
aucune migration avant Alembic (08/11). Une base créée avant cette PR a encore `item_tag` :
l'import y échouerait sur `no such table: item_has_tag`. La base du POC est donc supprimée
(`k-b.sqlite` et ses `-wal`, `-shm`) puis recréée, comme pour #259 et #260. Ce qu'elle perd, le
registre le dit (`docs/registre-traitements.md:67`) : « une base reconstruite depuis le brut n'a
que l'état du dernier extrait : ni les documents et surlignages retirés avant lui, ni les dates
de révision passées ».

### 5. Ce qui garde l'ancien nom

Les écrits datés racontent leur jour : l'entrée d'ADR « Collecte : tags des `.md` importés » et la
note de #260 gardent `item_tag`. La note reçoit une ligne d'addendum ; le renommage a sa propre
entrée d'ADR datée (« Base : nom de la liaison des tags »). Les docs vivantes, qui décrivent le
schéma d'aujourd'hui, suivent : `docs/stockage.md`, `docs/registre-traitements.md`,
`docs/specs-collecte.md`. La table `itemTags` de `src/k_b/etl/sources/zotero.py` est celle de
Zotero : elle n'a rien à voir et ne change pas.

## Choix faits et options écartées

| Choix | Pourquoi | Écarté |
|---|---|---|
| `item_has_tag` | Décision de Sabine (MLD et MPD). | Garder `item_tag`, le nom de #260. |
| Renommer l'index | Les neuf index suivent `<table>_<colonne>` (critère de #263). | Garder `item_tag_tag_id` : seul nom hors format. |
| `SELECT_ITEM_TAGS` inchangé | Il nomme ce qu'il rend (critère de #263). | Le renommer en `SELECT_ITEM_HAS_TAGS` : nom qui dit la table, pas le résultat. |
| Base recréée, sans migration | Aucune migration dans le dépôt ; coût accepté par Sabine. | Un `ALTER TABLE … RENAME` écrit dans la PR : pas proposé cette fois ; pour #259, Sabine avait écarté l'`ALTER TABLE` à la main. |
| Pas de test du nom de l'index | Le `grep` le prouve ; un test pour un nom serait du code sans second usage. | Un test qui lit `sqlite_master` (relecture du plan, constat 2, décidé par time-knight). |
| Note et ADR datés non réécrits | Un écrit daté raconte son jour (décision de time-knight). | Réécrire l'ancien nom partout. |
| Consigne des labels dans `MEMORY.md` | Demandée avec cette PR par time-knight ; une PR de doc à part coûterait un cycle pour trois lignes. | Une PR de documentation séparée. |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run pytest -q` avant le schéma : 14 échecs dans `test_schema.py` et `test_load_clips.py` | Les tests lisent bien le nom de la table. |
| `uv run pytest -q` → `1856 passed` | Le renommage ne change aucun comportement. |
| `git grep -n "item_tag" -- src tests` → rien | Plus aucun ancien nom dans le code ni les tests. |
| `grep -n "CREATE INDEX" src/k_b/database/schema.sql` → 9 index, tous `<table>_<colonne>` | L'index suit le format. |
| `ruff check`, `ruff format --check`, `mypy --strict` verts | Contrôles de la CI. |

## Ce que tu dois pouvoir défendre

- **Pourquoi pas une migration ?** Il n'en existe aucune avant Alembic (08/11) ; la base du POC
  se reconstruit depuis le brut, et Sabine a accepté la perte (section 4, registre l.67).
- **Que se passe-t-il sur une base créée avant cette PR ?** L'import s'arrête sur
  `no such table: item_has_tag` : il faut recréer la base.
- **Pourquoi `SELECT_ITEM_TAGS` n'a-t-il pas changé ?** Une constante se nomme par ce qu'elle
  fait : celle-ci rend les tags d'un item (`clip_writer.py:45-48`).
- **Pourquoi l'index n'est-il couvert par aucun test ?** Son nom ne change aucun comportement ;
  le `grep` du schéma suffit à le prouver.

## Zones non vérifiées

- La recréation de la base du POC n'a pas été faite ici : elle se fait chez Sabine, après la
  fusion (la session n'ouvre pas sa base).
- Le MLD du dépôt (`docs/merise/mld-k-b.drawio`) n'a pas encore les tables de tags : le nom
  `item_has_tag` n'y est pas vérifiable (#211).

## Ce qui reste

- Ajouter `tag` et `item_has_tag` au MLD : #211, avec Sabine.

Note sur la liste des commits fournie à l'écriture de cette note : seuls `f530874`, `55e4fc7` et
`cf5eb7b` sont de cette branche ; les autres sont déjà dans `main` (PR précédentes).

## Sources

Aucune source externe : le renommage ne s'appuie sur aucune documentation de bibliothèque.
