# Laisser la base dédoublonner les items

- **Date** : 2026-10-12
- **Branche** : `feat/database-deduplicates-items`
- **Issue** : #105 (ferme aussi #84, les champs propres à CISA KEV)
- **Fichiers principaux** : `src/k_b/import_items.py`, `src/k_b/merge.py`,
  `tests/test_import_items.py`, `docs/specs-collecte.md` (étapes 3 et 4)
- **Dans la même série** : [fusionner les items](2026-10-05-fusionner-les-items.md) (#80), dont
  cette PR retire la fusion en mémoire.

## 1. Le pourquoi

Jusqu'ici, `kb import` lisait tout `raw/`, puis `merge_items` retirait les doublons en mémoire.
Cette fusion ne voyait que ce qu'elle avait chargé. Pour reconnaître un item déjà importé, il
fallait donc tout relire à chaque import. L'import incrémental (#106) veut au contraire ne lire
que les fichiers nouveaux. Il faut alors que **la base** reconnaisse un item déjà vu : c'est la
condition de #106.

« Déjà vu » ne veut pas dire la même chose pour toutes les sources. Chacune a une **nature**
(décidée le 2026-10-07, précisée le 2026-10-12) :

- **flux de nouveautés** (releases, alertes GitHub) : un élément publié ne change plus, on garde
  la première version vue ;
- **catalogue d'état** (CISA KEV) : chaque collecte redonne le catalogue entier, et une ligne
  peut être modifiée sur place ; seule la collecte la plus récente compte ;
- **flux avec révisions** (arXiv) : un papier a une date de révision (`updated`), et on garde la
  plus récente.

Un item écarté laisse une ligne au journal d'import, avec la condition observée et la date
contre laquelle il a été comparé.

## 2. Le comment

### 2.1 La fusion disparaît, la normalisation reste

`merge.py` ne garde que `normalize_item` et `remove_tracking_parameters` : les dates en UTC et
l'URL sans `utm_*`, ce qu'aucune contrainte de base ne sait faire. L'import normalise chaque item
puis l'écrit, un par un, dans la transaction (`src/k_b/import_items.py:218`) :

```python
for item in map(normalize_item, items):
    discard = write_item(connection, item)
    if discard is None:
        written_count += 1
    else:
        discards.append(discard)
```

Chaque écrivain rend `None` (écrit) ou un `Discard` (écarté, avec sa règle). Les items arrivent
dans l'ordre des collectes (`read_raw_items`, tri stable) : le premier fichier lu est le plus
ancien.

### 2.2 Flux avec révisions : `ON CONFLICT … DO UPDATE … WHERE … RETURNING`

`src/k_b/import_items.py:52` :

```sql
WHERE publication.item_id IS NULL OR excluded.revised_at > publication.revised_at
RETURNING id
```

`ON CONFLICT (arxiv_id) DO UPDATE` transforme l'insertion en mise à jour quand le papier existe
déjà. Le `WHERE` filtre cette mise à jour : elle n'a lieu que pour une révision strictement plus
récente. `excluded` désigne la ligne qu'on tentait d'insérer. **`RETURNING id` ne rend rien
quand le `WHERE` est faux**, ce qui a été vérifié sur SQLite 3.50.4. C'est ainsi que l'écrivain
sait, sans relire la ligne, que la base a écarté l'item. Les dates sont comparées comme du texte,
ce qui est juste parce que le `CHECK` du schéma impose `YYYY-MM-DDTHH:MM:SSZ`, dont l'ordre
alphabétique est l'ordre chronologique.

`publication.item_id IS NULL` couvre un papier cité avant qu'arXiv ne le donne : aucune source
ne le fait encore, #138 le fera.

### 2.3 Catalogue d'état : comparer au dernier catalogue importé

Deux requêtes. D'abord la date du dernier catalogue de la source déjà importé
(`src/k_b/import_items.py:58-64`) :

```sql
WHERE source.source_code = :source_code
    AND (raw_data.id <> :raw_data_id
        OR raw_data.id = (SELECT raw_data_id FROM item WHERE id = :item_id))
```

Le fichier en cours est enregistré dans `raw_data` avant ses items : sans l'exclure, il serait
toujours « le dernier », et rien ne pourrait plus être écrit. Mais au rejeu, si la version en base
vient de ce fichier même, il compte : sinon, la date comparée serait vide (NULL).

Puis l'upsert, dont le `WHERE` porte la règle (`src/k_b/import_items.py:83-90`) :

```sql
revised_at = iif(vulnerability.item_id IS NULL, NULL, :collected_at)
WHERE vulnerability.item_id IS NULL
    OR (:collected_at > :latest_collected_at
        AND (vulnerability.name, …) IS NOT (excluded.name, …))
```

Une ligne connue n'est réécrite que si son fichier est plus récent **et** que son contenu
diffère ; `revised_at` prend alors la date de cette collecte. `vulnerability.item_id IS NULL`
désigne un CVE qu'une alerte a créé sans colonnes KEV : sa première ligne CISA n'est pas une
révision, d'où `iif(…, NULL, …)`. Dans `SET`, `vulnerability.item_id` désigne bien l'ancienne
valeur, ce que le test 6 vérifie. `IS NOT` sur un groupe de colonnes compare ligne à ligne, et
traite NULL comme une valeur.

Quand rien n'est rendu, l'écrivain nomme la condition qui a échoué
(`src/k_b/import_items.py:357`) : fichier plus récent → `unchanged` (le contenu était le même),
sinon `no_newer_version`. Une écriture sur un item connu rattache celui-ci au nouveau brut
(`point_item_at_raw_data`).

### 2.4 Flux de nouveautés : `INSERT … WHERE NOT EXISTS`

`src/k_b/import_items.py:96-100` :

```sql
INSERT INTO item (kind, raw_data_id)
SELECT 'release', ? WHERE NOT EXISTS (SELECT 1 FROM release WHERE release_id = ?)
RETURNING id
```

Une release exige son item (`item_id NOT NULL`, clé étrangère `(item_id, kind)`), et ITEM n'a pas
de clé naturelle sur laquelle porter un `ON CONFLICT`. L'item n'est donc créé que si la release
est absente. Rien rendu → `already_seen`. La contrainte `UNIQUE (release_id)` reste le filet :
l'étape 8 l'a montré, en neutralisant le `WHERE NOT EXISTS`, l'import échoue sur
`UNIQUE constraint failed`. L'alerte suit la même forme sur `ghsa_id`, et ne crée le CVE cité
qu'une fois reconnue nouvelle.

### 2.5 Le journal dit la date comparée

`Discard` porte la règle, l'item et la date comparée. Le nom du champ au journal dépend de la
règle (`COMPARED_FIELD_BY_RULE`, `src/k_b/import_items.py:532`) : `compared_with_collected_at`
pour une date de collecte, `compared_with_revised_at` pour une révision arXiv. Un nom de date dit
d'où vient la date (décision de Sabine).

## 3. Choix faits et options écartées

| Choix | Retenu, pourquoi | Écarté, pourquoi |
|---|---|---|
| Où vit la nature | Dans le SQL de l'écrivain de chaque sorte (option C, Sabine) | Colonne `source.nature` : rien ne la lirait, et elle changeait le MCD/MLD. Constante Python : redit le SQL sans contrôle |
| Flux de nouveautés | `INSERT … WHERE NOT EXISTS` (imposé par le schéma) | Item, puis `ON CONFLICT DO NOTHING`, puis `DELETE` de l'item : `DELETE` hors purge (règle 5 des conventions) |
| Référence du catalogue | Le dernier catalogue de la source déjà importé (Sabine) | La collecte de la version en base : un fichier en retard pouvait réécrire une version périmée |
| Étiquettes du catalogue | `unchanged` et `no_newer_version` (Sabine) | Une seule étiquette : le journal dirait le contraire de ce qui s'est passé |
| Champ de date | Un par sens (Sabine) | Un champ neutre `compared_with` : ne dit pas d'où vient la date |
| Où écrire le SQL | `import_items.py`, comme l'existant (décision 4) | Un module de `database/` maintenant : c'est #135, plus tard dans la file |
| `same_url`, `same_cve` | Supprimées : ITEM n'a plus d'URL, `cve_id` est unique (modèle du 2026-10-10) | — |

## 4. Preuve

| Test ou sortie | Ce que ça démontre |
|---|---|
| `test_a_release_seen_again_keeps_its_first_collection_and_is_logged_already_seen` | une release revue (`body` modifié) garde sa 1re version ; `already_seen` avec la date de 1re collecte |
| `test_an_advisory_seen_again_…` | idem pour une alerte |
| `test_two_advisories_of_the_same_cve_are_both_kept_and_share_one_vulnerability` | deux alertes d'un CVE, une vulnérabilité, aucun écart |
| `test_a_modified_kev_row_replaces_the_previous_one_and_dates_revised_at` | même `item_id`, contenu nouveau, `revised_at` daté, item rattaché au nouveau brut |
| `test_an_identical_kev_row_of_a_newer_catalog_…_unchanged` | rien ne change, `unchanged` avec la date de la version gardée |
| `test_a_kev_row_of_an_older_catalog_…_no_newer_version` | un catalogue plus ancien, même différent, ne change rien |
| `test_an_advisory_and_a_kev_row_of_the_same_cve_share_one_vulnerability` | CVE créé par une alerte, puis ligne CISA : `revised_at` vide |
| `test_an_arxiv_revision_not_newer_…[older, equal]` | révision plus ancienne ou égale écartée, `compared_with_revised_at` |
| `test_an_import_run_again_gives_the_same_database_and_logs_every_item_as_a_discard` | rejeu avec deux catalogues différents : même base, un écart par item |
| Étape 8, code cassé à la main puis remis | `>=` pour arXiv → 2 échecs ; garde d'ordre retirée → 2 ; `revised_at` toujours daté → 1 ; une colonne hors comparaison → 2 ; `WHERE NOT EXISTS` neutralisé → `IntegrityError` |
| `uv run pytest` : 598 passés ; `ruff check`, `ruff format --check`, `mypy --strict` : verts | les contrôles de la CI |

## 5. Ce que tu dois pouvoir défendre

1. **Pourquoi la règle dans le SQL plutôt qu'en Python ?** La base est la seule à voir tout ce
   qui a été importé. Un test en Python avant l'écriture redirait la règle à deux endroits. Ici,
   le `WHERE` décide, et Python ne fait que nommer la condition observée
   (`import_items.py:357`).
2. **Que se passe-t-il au rejeu d'un vieux catalogue CISA ?** Sa date n'est pas plus récente que
   le dernier catalogue importé : rien n'est écrit, et la ligne est `no_newer_version`
   (test du rejeu ; avant la garde, il réécrivait l'ancienne version, constat de la relecture).
3. **Pourquoi pas `ON CONFLICT` pour les releases ?** Le sous-type exige un item existant, et
   ITEM n'a pas de clé naturelle. Supprimer l'item après coup serait un `DELETE` hors purge.
4. **Comparer des dates comme du texte, c'est sûr ?** Oui, parce que le `CHECK` impose un format
   fixe en UTC dont l'ordre du texte est celui du temps (`schema.sql`, `strftime`).
5. **Où est la sécurité ?** Requêtes paramétrées (`?`, `:nom`). Le journal ne cite que des
   identifiants de source, un chemin et une date, jamais un auteur. L'item est validé en amont,
   et la contrainte `UNIQUE` reste le filet.

## 6. Zones non vérifiées

- **Coût de la requête du dernier catalogue** : elle est lancée pour chaque ligne CISA (chaque
  ligne de chaque catalogue relu). Non mesuré. Elle passe par l'index `raw_data_source_id`.
- **L'étape 8 n'a pas cassé la règle des alertes**, seulement celle des releases : la symétrie
  est supposée, et le test 2 la couvre en fonctionnement normal.
- **Un CVE en double dans un même catalogue** : le raisonnement dit `no_newer_version`, mais ce
  n'est pas testé (CISA n'a pas de doublon dans le brut du 2026-10-07).
- **`docs/specs-collecte.md`, étape 4** : deux puces sur les auteurs, gardées telles quelles («
  un auteur qui n'a plus d'item est supprimé »), ne correspondent plus au schéma, où les auteurs
  sont une liste JSON de `publication`. Écart hors de l'issue, signalé, non corrigé.

## 7. Ce qui reste

- L'import incrémental, et `withdrawn_at` pour une ligne retirée du catalogue : #106.
- Le déplacement du SQL dans `src/k_b/database/` : #135. Le rejet par la base, par `SAVEPOINT` :
  #136.
- Les articles TLDR, leur table et leur règle de flux de nouveautés : #57.
- La nature de Zotero et de GH Archive : #138, #142. Le quasi-doublon (empreinte de contenu) :
  #57, #138.
- Les noms des colonnes de date : une décision ouverte, à prendre avec le modèle des
  publications.
