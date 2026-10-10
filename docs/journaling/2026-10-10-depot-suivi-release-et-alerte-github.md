# Dépôt suivi, release et alerte GitHub en base

- Date : 2026-10-10
- Branche : `feat/tracked-repository-release-advisory`
- Issue : #121 (réécrire le schéma, 3/4)
- Fichiers principaux : `src/k_b/database/schema.sql`, `src/k_b/import_items.py`,
  `src/k_b/items.py`, `src/k_b/sources/github_releases.py`, `src/k_b/sources/github_advisories.py`
- Note précédente de la série : [ITEM minimal, publication et vulnérabilité](2026-10-10-item-minimal-publication-et-vulnerabilite.md) (#120)

## Le pourquoi

Depuis #120, l'import sautait les releases et les alertes GitHub : ITEM était devenu minimal
(`id`, `kind`, donnée brute) et ces deux sortes n'avaient plus de table où ranger leur contenu.
Cette PR leur rend une place dans le modèle décidé du 07/10 au 10/10 :

- **DÉPÔT SUIVI** est une table de référence, comme SOURCE : ce n'est pas un item. La liste du
  code (`TRACKED_REPOSITORIES`) fait foi, et chaque release s'y rattache.
- **RELEASE** et **ALERTE** sont des sous-types d'ITEM : chacun porte son contenu (titre, notes,
  dates, URL telle que GitHub la donne) et pointe vers son item.
- Une alerte qui cite un CVE le **crée** dans VULNÉRABILITÉ s'il n'y est pas, sans les colonnes
  de CISA KEV. « Exploitée » reste réservé à KEV (`vulnerability.item_id IS NOT NULL`).

Sur la collecte réelle du 2026-10-07, l'import passe de 0 à 155 items GitHub (100 releases et
55 alertes). Le top 100 des dépôts étoilés, qui en donnait 100 de plus avant #120, reste hors
de la base (décision « Tops » du 07/10).

## Le comment

### 1. Une clé étrangère composée pour qu'un item n'ait qu'un sous-type

```sql
    raw_data_id INTEGER NOT NULL REFERENCES raw_data (id),
    -- The target of the (item_id, kind) foreign key of each subtype: an item has one subtype.
    UNIQUE (id, kind)
```
`src/k_b/database/schema.sql:39-41`

```sql
    kind                  TEXT NOT NULL CHECK (kind = 'release'),
    ...
    FOREIGN KEY (item_id, kind) REFERENCES item (id, kind)
```
`src/k_b/database/schema.sql:144` et `:155`

Une release répète le `kind` de son item, et ne peut le répéter qu'avec la valeur `'release'`.
La clé étrangère composée exige qu'il existe un item avec **ce même `id` et ce même `kind`**.
Une release ne peut donc pas pointer vers un item `paper`, et un item ne peut avoir qu'un seul
sous-type : c'est l'exclusivité de l'option D (ADR du 07/10). SQLite n'accepte une clé
étrangère que vers une clé primaire ou un `UNIQUE` : d'où le `UNIQUE (id, kind)` sur `item`,
redondant en apparence, puisque `id` est déjà unique.

`NOT NULL` sur `kind` n'est pas décoratif. Avec un `kind` NULL, le `CHECK` donne NULL, ce qui
passe, et SQLite ne vérifie pas une clé étrangère dont une colonne est NULL : la release
pourrait pointer n'importe où. Le relecteur du plan l'a montré par une sonde, et un test le
prouve (`test_a_release_whose_kind_is_not_release_is_refused[None]`).

### 2. La table des dépôts suivis, remplie à chaque import

```python
            write_tracked_repositories(connection, tracked_repositories)
            for item in merged.items:
                write_item(connection, item)
```
`src/k_b/import_items.py:118-120`

La liste vit dans le code. À chaque import, dans la même transaction que les items, chaque dépôt
de la liste est inséré ou mis à jour (`INSERT … ON CONFLICT (repository_name) DO UPDATE`). La
table suit donc la liste sans qu'on recrée la base. Relancer l'import donne la même base (le
test de réimport identique le vérifie). Le nom est déclaré `UNIQUE COLLATE NOCASE`
(`schema.sql:130`) : GitHub ne distingue pas `Anthropics/Claude-Code` de
`anthropics/claude-code`, et la collecte comparait déjà les noms en minuscules.

Un détail de dépendances : `import_items.py` est un module générique et ne doit pas importer
`k_b.sources` (`tests/test_module_dependencies.py`). Le type `TrackedRepository` a donc été
déplacé dans `config.py` (`config.py:11`), où #123 rangera aussi la liste. C'est `cli.py`, module
de composition, qui passe `TRACKED_REPOSITORIES` à l'import.

### 3. Une release d'un dépôt hors de la liste : rejetée, l'import continue

```python
        if (
            # A release always has its repository (items.py): str() only satisfies the typing.
            item.kind == "release"
            and str(item.repository_name).lower() not in tracked_names
        ):
            rejections.append(
                reject(
                    item.raw_file_path,
                    f"repository not in the tracked list: {item.repository_name}",
```
`src/k_b/import_items.py:138-145`

Le brut d'un dépôt retiré de la liste reste sur le disque, et son dossier est encore reconnu
comme un dossier de releases. Sans ce filtre, `write_release` ne trouverait pas le dépôt en
table. Sabine a décidé que l'import continue, comme pour une ligne CVE malformée : la release
est rejetée, écrite dans `import-log.jsonl` et comptée dans les rejets. Le filtre passe **avant**
la fusion, comme les rejets de lecture. Le motif dit ce qui est observé (« pas dans la liste »)
et non une interprétation (« plus suivi » : le dépôt ne l'a peut-être jamais été). C'est une
correction de la revue de code.

### 4. Premier vu, et la CVE créée par une alerte

```python
    if connection.execute(
        "SELECT 1 FROM release WHERE release_id = ?", (int(item.source_item_id),)
    ).fetchone():
        return
```
`src/k_b/import_items.py:225-228`

Les releases et les alertes sont des flux de nouveautés : la première version vue est gardée
(ADR du 07/10, « premier vu ou dernier vu » réglé par nature de source). Dans un même import,
`merge.py` a déjà gardé la première. Ce test ne sert que lorsqu'on importe une seconde fois dans
une base déjà remplie : l'item garde alors sa donnée brute d'origine. C'est l'inverse d'arXiv
(révision plus récente) et de CISA KEV (dernière version du catalogue), qui réécrivent.

```python
            "INSERT INTO vulnerability (cve_id) VALUES (?) ON CONFLICT (cve_id) DO NOTHING",
```
`src/k_b/import_items.py:264`

Une alerte qui cite un CVE l'insère s'il manque, puis relit son `id`. La ligne créée n'a que
`cve_id` : le `CHECK` existant de `vulnerability` (#120) interdit toute colonne KEV sans
`item_id`. Si CISA KEV apporte ce CVE, avant ou après l'alerte, son upsert remplit la même
ligne : une seule ligne par CVE, et l'alerte y pointe. Les deux ordres sont testés.

### 5. L'item commun connaît les champs des deux nouvelles sortes

```python
FIELDS_OF_ONE_KIND = {
    "vulnerability": ("vendor", "product", "ransomware_use"),
    "release": ("repository_name", "tag_name", "release_name"),
    "advisory": ("package_names",),
}
```
`src/k_b/items.py:65-69`

Pour écrire une release, l'import a besoin du dépôt, de l'étiquette et du `name` GitHub ; pour
une alerte, de ses paquets. `Item` gagne ces quatre champs. Trois contrôles les tiennent :
- `REQUIRED_FIELDS_BY_KIND` impose les champs obligatoires de chaque sorte ;
- `SOURCE_BY_KIND` réserve `release` et `advisory` à la source `github` (règle « sorte ↔ source »
  de #120, `items.py:61`) ;
- `check_fields_of_other_kinds` (`items.py:134`) refuse qu'une sorte remplisse les champs d'une
  autre.

Avant, seul KEV avait ce troisième contrôle (`check_kev_fields`). Avec release et alerte,
c'était la troisième occurrence du même motif : il a été factorisé (règle DRY de `code.md`).
« Vide » s'y lit `None` **ou** `()`, sinon le tuple vide par défaut de `package_names` ferait
refuser tout item. Le principe ne change pas : ce que la base refuserait est refusé dès la
lecture, sinon une seule ligne refusée ferait échouer tout l'import.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Paquets d'une alerte en **liste JSON**, avec le même `CHECK` que `publication.authors` | Décision du 08/10 : la liste est affichée, pas filtrée (P3 non planifié). Sabine l'a rappelée le 10/10, et l'issue a été corrigée | Table `advisory_package` : la proposition écartée le 08/10, reprise par erreur dans l'issue |
| Paquets suivis du dépôt en liste JSON | Même raison ; aucun filtre en base | Une table `tracked_package` |
| Alerte : `summary` et `published_at` gardés | ADR du 10/10 : titre, résumé et dates restent dans chaque sous-type | Les omettre (l'issue ne les citait pas) |
| `severity`, `description`, `prerelease` non gardés | Hors périmètre (palier 2) ou hors des colonnes décidées le 08/10 | Les ajouter maintenant (débordement relevé par la revue, écarté) |
| Dépôts suivis écrits **à chaque import** | La liste du code fait foi ; idempotent | Les écrire à `kb create-db` : une liste modifiée demanderait de recréer la base |
| `TrackedRepository` dans `config.py` | Générique, et futur emplacement de la liste (#123) | `source_contract.py` (type propre à GitHub dans le contrat de toutes les sources) ; des tuples nus (type illisible) ; un `Protocol` (abstraction sans second usage) |
| Release d'un dépôt hors liste : **rejet**, l'import continue | Décision de Sabine (comme une ligne CVE malformée) | Une erreur qui arrête tout l'import ; créer le dépôt depuis la release (écosystème inventé) |
| `release.name` stocké tel que GitHub le donne, `NULL` compris | ADR du 08/10 : RELEASE garde `name` | Y stocker le titre « dépôt + nom ou étiquette » (perdrait un `name` nul) |
| Pas de `ON DELETE` | La purge (#20, #83) n'est pas codée ; les tables de #120 n'en ont pas | `ON DELETE CASCADE` dès maintenant |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_release_gives_an_item_and_its_release_of_its_tracked_repository` | Critère 1 : une release donne ITEM + RELEASE reliée à son DÉPÔT SUIVI |
| `test_an_advisory_citing_an_absent_cve_creates_it_without_kev_columns` | Critère 2 : la CVE est créée sans colonnes KEV |
| `test_the_packages_of_an_advisory_are_kept_once_each` | Critère 3 (corrigé) : les paquets sont dans la liste JSON, chacun une fois (`langsmith` apparaît deux fois dans la fixture) |
| `test_an_advisory_and_a_kev_row_of_the_same_cve_share_one_vulnerability` (2 ordres) | Une seule ligne par CVE, quel que soit l'ordre de collecte |
| `test_a_release_of_a_repository_no_longer_tracked_is_rejected_and_logged` | Rejet journalisé avec son motif, et l'import des autres items continue |
| `test_a_release_seen_again_keeps_its_first_collection` | Premier vu |
| `test_a_release_pointing_to_an_item_of_another_kind_is_refused`, `…_kind_is_not_release_is_refused[None]` | L'exclusivité tient, `kind` NULL compris |
| Test « brut de releases sauté » de #120 | Retiré (critère de fin) |
| `uv run pytest` : 403 réussis ; `ruff check`, `ruff format --check`, `mypy --strict` verts | Contrôles du dépôt |
| `kb create-db` puis `kb import` sur une copie de `temp/.knowledge_base/` : arxiv 511, cisa_kev 1 734, github 155, 0 rejet, `PRAGMA foreign_key_check` vide | La collecte réelle passe ; 1 789 CVE = 1 734 KEV + 55 citées par les alertes, sans recouvrement |
| `UNIQUE` retiré de `release_id` à la main, puis `NOT NULL` retiré de `advisory.kind` | Chaque fois, un test échoue ; code remis à la main |

## Ce que tu dois pouvoir défendre

1. **Pourquoi `UNIQUE (id, kind)` sur `item`, alors que `id` est déjà unique ?** SQLite n'accepte
   une clé étrangère que vers une clé primaire ou un `UNIQUE` portant exactement ces colonnes. Il
   le faut pour la clé composée `(item_id, kind)` des sous-types (`schema.sql:41`, `:155`).
2. **Que se passe-t-il si on retire un dépôt de la liste ?** Dans une base neuve, il n'est pas en
   table. Ses anciennes releases sont rejetées avec le motif
   `repository not in the tracked list: …`, et le reste s'importe (`import_items.py:138`). Relire
   ce brut est le travail de #87 (commentaire laissé sur l'issue).
3. **Une alerte peut-elle faire passer une CVE pour exploitée ?** Non. Elle n'écrit que `cve_id`,
   et le `CHECK` de `vulnerability` refuse une colonne KEV sans `item_id`. « Exploitée » se lit
   `item_id IS NOT NULL`, rempli par CISA KEV seul (`SOURCE_BY_KIND`, `items.py:61`).
4. **Pourquoi une liste JSON et non une table pour les paquets, contre la 1re forme normale ?**
   Décision du 08/10 : en v0 la liste est seulement affichée, aucun filtre par paquet n'est
   prévu. Si P3 arrive, une migration la découpe en table. Le `CHECK` garantit au moins un
   tableau JSON non vide.
5. **Où est la sécurité ?** Les champs GitHub sont validés à la lecture (expressions strictes pour
   `ghsa_id`, CVE, URL, nom de dépôt, puis Pydantic). Toutes les requêtes sont paramétrées (`?`),
   et le `/security-review` n'a rien relevé. Le login de l'auteur d'une release n'est pas lu.

## Zones non vérifiées

- Le `body` d'une release est du Markdown libre et peut contenir des logins (« by @login »). Rien
  de tel n'a été observé dans les 100 releases de claude-code (22 contiennent un « @ », aucun
  login). Le registre des traitements n'écarte que le login de l'auteur : à reporter au registre.
- Seul le brut de `anthropics/claude-code` et des alertes `pip` existe dans la collecte du 07/10.
  Les trois autres dépôts et l'écosystème `npm` n'ont pas été importés sur du réel.
- `COLLATE NOCASE` ne replie que l'ASCII. Les noms de dépôts sont ASCII par l'expression de
  lecture, ce qui n'a pas été éprouvé au-delà.

## Ce qui reste

- `merge.py` écarte une 2e alerte GitHub qui porte le même CVE (`same_cve`, par source), alors que
  le schéma en admettrait plusieurs. Aucun cas dans le brut réel ; relève de #105.
- La relecture du brut d'un dépôt retiré de la liste : #87.
- La liste des dépôts et des écosystèmes dans `config.py` : #123.
- `severity` et `description` des alertes : issue à part (palier 2).
- Requête `UNION ALL` et longueurs maximales : #122.
- Mise à jour de `clarification-modele.md` (annexe GitHub), de `stockage.md`, des MCD/MLD et du
  registre (`author`, `item_author`, logins dans `body`) : tâche de la file après #122.
