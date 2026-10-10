# ITEM minimal, PUBLICATION et VULNÉRABILITÉ

- **Date** : 2026-10-10
- **Branche** : `feat/minimal-item-publication-vulnerability`
- **Issue** : #120 (réécrire le schéma, 2/4) ; Refs #84
- **Fichiers principaux** : `src/k_b/database/schema.sql`, `src/k_b/items.py`,
  `src/k_b/import_items.py`, `src/k_b/sources/cisa_kev.py`, `src/k_b/source_kinds.py`
- **Série** : suit [Tables de référence, mode d'acquisition et `config.py`](2026-10-10-tables-de-reference-et-mode-acquisition.md) (#119).

## Le pourquoi

Le modèle clarifié du 07/10 au 10/10 sépare deux choses que l'ancienne table `item` mêlait : ce
qui est propre à la **collecte** (de quel fichier brut vient l'item, de quelle sorte il est) et ce
que dit la **chose collectée** (le titre d'un papier, le nom d'une faille). L'option D (ADR du
07/10) garde un ITEM minimal ; le contenu va dans des **référentiels** : PUBLICATION pour les
papiers (arXiv fait foi) et VULNÉRABILITÉ pour les failles (CISA KEV fait foi). Un référentiel
existe dès qu'une source le cite ; il pointe vers l'item de la source qui fait foi quand elle l'a
vu. « Exploitée » se lit donc `vulnerability.item_id IS NOT NULL`.

Cette PR pose ces trois tables, fait importer arXiv et CISA dedans, supprime les tables d'auteurs
(les auteurs deviennent une liste JSON de PUBLICATION, ADR du 07/10) et, en attendant #121, saute
à l'import les bruts GitHub (recul accepté par Sabine le 10/10).

## Le comment

### 1. ITEM ne garde que l'identité de la collecte

```sql
CREATE TABLE item (
    id          INTEGER PRIMARY KEY,
    kind        TEXT NOT NULL
        CHECK (kind IN ('paper', 'vulnerability', 'newsletter_article', 'release', 'advisory')),
    raw_data_id INTEGER NOT NULL REFERENCES raw_data (id)
) STRICT;
```

(`src/k_b/database/schema.sql:35-40`)

Plus de `source_code`, de titre, d'URL ni de dates. La source d'un item se lit par
`item.raw_data_id → raw_data.source_id`. Cela règle le commentaire du 10/10 sur #120 : la source
n'est plus portée deux fois (`item.source_code` et `raw_data.source_id`), donc il n'y a plus de
concordance à contrôler. `kind` prend les cinq valeurs de la liste du document de clarification ;
un test (`tests/test_schema.py`, `test_the_kinds_of_the_schema_are_those_of_the_items`) garde
cette liste égale à `ItemKind` dans `items.py`.

### 2. Un référentiel : colonnes remplies si et seulement si `item_id` l'est

```sql
    CHECK ((item_id IS NULL) = (title IS NULL)
        AND (item_id IS NULL) = (summary IS NULL)
        AND (item_id IS NULL) = (authors IS NULL)
```

(`src/k_b/database/schema.sql:60-62`)

`(item_id IS NULL) = (title IS NULL)` compare deux booléens : vrai si les deux sont vides ou les
deux remplis. Une PUBLICATION citée sans que la collecte arXiv l'ait vue (demain : par un article
TLDR) n'a que son `arxiv_id` ; une PUBLICATION vue par arXiv a toutes ses colonnes. Un titre sans
`item_id` est refusé par la base : c'est le cas du critère de fin. VULNÉRABILITÉ applique la même
règle aux colonnes KEV (`schema.sql:114-120`) ; `revised_at` et `withdrawn_at` peuvent rester vides
même avec un `item_id` (leurs règles sont à #105 et #106), mais doivent être vides sans lui.
`item_id` est `UNIQUE` : deux publications ne peuvent pas pointer vers le même item ; plusieurs
`NULL` restent permis (SQLite ne compare pas deux `NULL` entre eux pour l'unicité). Les auteurs
sont vérifiés en base comme un tableau JSON non vide (`json_valid`, `json_type`,
`json_array_length`, `schema.sql:53-55`).

### 3. L'import : retrouver le référentiel par son identifiant officiel

```python
    row = connection.execute(
        "SELECT item_id FROM publication WHERE arxiv_id = ?", (item.source_item_id,)
    ).fetchone()
    item_id = upsert_item(connection, "paper", raw_data_id, row and row[0])
```

(`src/k_b/import_items.py:113-116`)

ITEM n'a plus de clé naturelle : c'est le référentiel qui sait si l'item existe. Sans ligne, ou
avec une ligne sans `item_id`, `upsert_item` crée l'item ; sinon il pointe l'item connu vers le
brut de sa version actuelle (`UPDATE item SET raw_data_id`). Puis `UPSERT_PUBLICATION`
(`import_items.py:27-37`) insère ou réécrit les colonnes arXiv par `ON CONFLICT (arxiv_id)`. Une
révision arXiv plus récente garde donc le même `item.id`. VULNÉRABILITÉ suit la même forme, par
`cve_id` (`import_items.py:131-151`), et n'écrit jamais `revised_at` ni `withdrawn_at`.

### 4. Une sorte, un écrivain ; les autres sortes échouent fermé

```python
WRITER_BY_KIND: dict[str, Callable[[sqlite3.Connection, Item, int], None]] = {
    "paper": write_paper,
    "vulnerability": write_vulnerability,
}
```

(`src/k_b/import_items.py:174-177`)

La liste des sortes qui ont une table vit à un seul endroit (constat 8 de `/code-review`).
`write_item` y cherche l'écrivain ; une sorte absente (`release`, `advisory`,
`newsletter_article`) lève `KindWithoutTableError` avant toute écriture, et la transaction annule
tout l'import (`import_items.py:101-108`). Aucun lecteur n'en produit aujourd'hui ; Sabine a choisi
d'échouer plutôt que d'ignorer. La CLI l'affiche avec le code 1 (`src/k_b/cli.py`).

### 5. L'item commun refuse à la lecture ce que la base refuserait

```python
def check_source(item: Item) -> None:
    source_code = SOURCE_BY_KIND.get(item.kind, item.source_code)
    if item.source_code != source_code:
        raise ValueError(f"a {item.kind} item from {item.source_code}")
```

(`src/k_b/items.py:93-96`)

`Item` (le modèle Pydantic commun, avant la fusion) reçoit `kind` et les champs KEV `vendor`,
`product`, `ransomware_use`. Trois règles le complètent : la sorte va avec sa source qui fait foi
(`paper` ↔ `arxiv`, `vulnerability` ↔ `cisa_kev`, constat 4 de `/code-review` : sinon une autre
source marquerait une CVE exploitée) ; chaque sorte remplit ses champs (`REQUIRED_FIELDS_BY_KIND`,
`items.py:40`) ; les champs KEV et le CVE ne vont qu'aux sortes prévues. Pourquoi ici et pas
seulement en base : une `ValidationError` à la conversion fait **rejeter une ligne** (journal
`import-log.jsonl`), alors qu'une `IntegrityError` en base fait **échouer tout l'import**.

### 6. CISA lit `knownRansomwareCampaignUse` ; GitHub est sauté

```python
        # Not checked here: the item refuses a value outside RansomwareUse (strict Literal).
        ransomware_use=cast(RansomwareUse, vulnerability.known_ransomware_campaign_use),
```

(`src/k_b/sources/cisa_kev.py:152-153`)

La colonne entre dans `REQUIRED_COLUMNS` : un catalogue sans elle est refusé, à l'import comme à
la collecte (`fetch` lit le catalogue pour le valider). La valeur est vérifiée par le `Literal`
strict de `Item` ; le `cast` ne sert qu'à mypy. Côté GitHub, `source_kinds.py:34-52` met
`reader=None` pour les releases, les alertes et le top 100 : leurs bruts passent par le chemin
existant « source without a reader, skipped » (`raw_items.py:120`, journal en INFO), comme TLDR.
Les convertisseurs GitHub et leurs tests sont retirés ; les fonctions de lecture restent, car le
téléchargement s'en sert.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Noms de colonnes du MLD (`submitted_at`, `vendor`, `ransomware_use`…) | Le MLD suit l'ADR | — |
| `date_added` à minuit UTC | Convention existante (`docs/stockage.md`) | Une date sans heure : changerait la convention sans décision |
| `item_id` des référentiels sans `ON DELETE` | `SET NULL` violerait le `CHECK` | Choisir une règle de suppression : c'est la purge (#20, #83) |
| `UQ (id, kind)` sur `item` non posé | Pas de sous-type dans #120 | Le poser dès maintenant : sert #121 seulement |
| Convertisseurs GitHub supprimés | Plus aucun chemin ne les appelle (pas de code mort, `code.md`) | Les adapter au nouvel `Item` : #121 les réécrit |
| Règles par sorte dans `Item`, une fonction chacune | Rejet d'une ligne au lieu d'un import raté ; complexité C90 | Laisser la base seule refuser |
| `KindWithoutTableError` | Décision de Sabine : échouer fermé | Ignorer silencieusement la sorte |
| `cast` dans `cisa_kev.py` | Garde le rejet ligne par ligne validé au plan | Contrôle dans `parse_vulnerability` : ferait refuser tout le catalogue (le cas va à #77) |
| Auteurs gardés tels que donnés, sans dédoublonnage | arXiv fait foi ; le dédoublonnage venait de la clé de `item_author` | — |
| `merge.py` : seul un commentaire change | Règle commune des quatre issues ; #105 change la fusion | — |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_an_arxiv_item_gives_an_item_and_its_publication` | Un papier → une ligne ITEM `paper` + une PUBLICATION reliée, auteurs en JSON dans l'ordre (critère) |
| `test_a_cisa_row_gives_an_item_and_its_vulnerability` | Une ligne CISA → ITEM `vulnerability` + VULNÉRABILITÉ avec les colonnes KEV (critère) |
| `test_a_publication_without_item_but_with_a_title_is_refused` | Le `CHECK` refuse un titre sans item (critère) |
| `test_a_raw_file_of_releases_is_skipped_and_logged` | Un brut de releases est sauté et journalisé (critère) |
| Code cassé exprès : `CHECK` de PUBLICATION retiré → 2 tests échouent ; remis → 355 verts | Les tests détectent la perte de la règle |
| `check_source` retiré à la main → 2 tests de `test_items.py` échouent | La règle sorte ↔ source est testée |
| `test_a_newer_revision_rewrites_the_paper_under_the_same_identifier` | Une révision garde le même `item.id` |
| `test_a_failed_import_leaves_the_database_and_the_log_unchanged` | Une erreur en base annule tout l'import |
| `kb create-db` puis `kb import` sur la collecte du 07/10 : arxiv 511, cisa_kev 1 734, github 0, 0 rejet | L'import réel passe ; GitHub tombe comme prévu (255 à #119) |
| `uv run pytest`, `ruff check`, `ruff format --check`, `mypy --strict` | Contrôles du dépôt verts |

## Ce que tu dois pouvoir défendre

1. **Pourquoi le titre n'est-il pas dans ITEM, alors que la recherche en a besoin ?** Décision du
   10/10 : chaque sorte porte ses informations ; la recherche passera par une requête `UNION ALL`,
   une branche par sorte (#122). Recopier le titre dans ITEM serait un doublon à tenir à jour à
   chaque révision (`schema.sql:35`).
2. **Comment l'import sait-il qu'un papier est déjà en base, sans clé dans ITEM ?** Par
   `publication.arxiv_id`, unique ; l'item est retrouvé par `publication.item_id`
   (`import_items.py:113-116`).
3. **Que se passe-t-il si CISA écrit `Yes` dans `knownRansomwareCampaignUse` ?** Pydantic refuse
   l'entrée à la conversion : la ligne est rejetée et écrite dans `import-log.jsonl`, les autres
   sont importées. La base la refuserait aussi (`CHECK`). Le traitement fin des lignes invalides
   relève de #77 (`cisa_kev.py:152-153`).
4. **Une alerte GitHub pourrait-elle marquer une CVE comme exploitée ?** Non : `check_source`
   refuse une `vulnerability` qui ne vient pas de `cisa_kev` (`items.py:93-96`).
5. **Où est la sécurité ?** Requêtes paramétrées (`?`) partout ; entrée validée à la frontière par
   des types fermés (`Literal`, `NonEmptyText`) ; doublée en base par des `CHECK` ; une sorte
   inconnue fait échouer fermé. `/security-review` n'a relevé aucune faille.

## Zones non vérifiées

- Comportement de `UNIQUE` avec plusieurs `NULL` en SQLite : vérifié par le relecteur du plan en
  mémoire, pas par un test du dépôt.
- `row and row[0]` (`import_items.py:116`, `:138`) : mypy l'accepte parce que la ligne lue est
  typée `Any` ; la lecture suppose qu'une ligne a toujours une première colonne.
- Les chaînes vides en base (`vendor = ''`) sont acceptées par la base, refusées par Pydantic :
  le test du comportement des `CHECK` est à #122.

## Ce qui reste

- Releases, alertes GitHub, DÉPÔT SUIVI et la clé composée (`item_id`, `kind`) : #121.
- Longueurs maximales, requête `UNION ALL`, mise à jour des MCD/MLD, de `docs/stockage.md` et du
  registre des traitements (auteurs en JSON, `item_author` disparu) : #122 et la tâche des
  documents.
- Règle « dernière version » de CISA (`revised_at`) : #105 ; retrait (`withdrawn_at`) : #106.
- Suppression d'un item pointé par un référentiel : purge, #20 et #83.
- Une valeur hors `Known`/`Unknown` : un cas de plus pour #77.
- `Item.saved_at` n'est plus écrit en base ; gardé pour `merge.py` et pour clips et Zotero.
