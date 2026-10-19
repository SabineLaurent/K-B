# Réécrire en base un clip dont le contenu a changé, et dater sa révision

- **Date** : 2026-10-19
- **Branche** : `feat/rewrite-changed-clip`
- **Issue** : #259
- **Fichiers principaux** : `src/k_b/database/writers/clip_writer.py`, `src/k_b/database/schema.sql`
  (table `clip`), `tests/etl/test_load_clips.py`
- **Série** : suite de [Collecter les clips du coffre Obsidian](2026-10-17-collecter-les-clips-du-coffre-obsidian.md)
  (#14), qui gardait la première version d'une URL.

La branche compte cinq commits, de `4df46d9` à `8c59055`. Les commits plus anciens de la liste
fournie (de `08f8fdb` en descendant) sont déjà sur `main` : ce sont ceux de #258 et des PR qui
l'ont précédée, et cette note ne les couvre pas. De même, la plupart des fichiers de la liste
fournie appartiennent à ces PR ; ceux de cette branche sont les douze fichiers de
`git diff origin/main...HEAD --stat`. La relation plusieurs-à-plusieurs des tags n'est pas ici :
elle vient avec #260 et sa note.

## Le pourquoi

Jusqu'ici, un clip était un **flux de nouveautés** : la première version vue d'une URL restait
en base, et une recopie était écartée `already_seen`. Si Sabine modifiait un clip dans son coffre,
la collecte en copiait bien la nouvelle version dans le brut, mais la base ne la voyait jamais.

Sabine a tranché le 2026-10-19 : « Ma décision du 17/10 concernait la création d'un vrai doublon.
Là si le contenu du fichier a changé il faudrait un update. » La règle vaut pour tous les `.md`
importés : `clipping` aujourd'hui, `manual_notes` plus tard (nommé dans l'ADR, sans code).

Ce code fait trois choses :
- il compare ce que la base garde du clip avec la version qui arrive ;
- il réécrit le clip si ce contenu a changé, et date la révision dans `clip.revised_at`, comme
  pour `zotero_entry` et `vulnerability` ;
- il refuse qu'une version plus ancienne écrase une plus récente.

## Le comment

### 1. Une colonne pour la date de révision

`src/k_b/database/schema.sql:314-317`

```sql
    -- A date of K-B: the collection that saw the change; empty until the clip changes.
    revised_at   TEXT
        CHECK (length(revised_at) = 20 AND substr(revised_at, 11, 1) = 'T'
            AND substr(revised_at, 20, 1) = 'Z'),
```

`revised_at` est une date **de K-B**, celle de la collecte qui a vu le changement. Ce n'est pas
une date de Web Clipper. Elle reste vide tant que le clip n'a pas changé. Le `CHECK` est écrit
comme ceux de `saved_at` et `published_at` de la même table : il contrôle la longueur et la place
du `T` et du `Z` par `substr`, sans fonction de date propre à SQLite. C'est la règle 1 de
`.claude/rules/poc.md` : le SQL nouveau doit passer en PostgreSQL au 08/11. La forme complète de
la date est garantie par Python : `format_date` (`src/k_b/database/dates.py`) l'écrit.

### 2. Ce que veut dire « contenu »

`src/k_b/database/writers/clip_writer.py:44-53`

```python
class ClipContent(NamedTuple):
    """What the base keeps of a clip, in the format of the base: a change of it is a new
    version. A property the base does not keep (author, description) is not compared."""

    title: str
    # Required of a clip by the item (REQUIRED_FIELDS_BY_KIND, items.py), typed as the item.
    body: str | None
    saved_at: str | None
    published_at: str | None
```

Le contenu, c'est **ce que la base garde**, et rien d'autre : le titre, le texte, `created`
(devenu `saved_at`) et `published` (devenu `published_at`). `author` et `description` ne sont
même pas lus (`ClipFrontmatter`, `src/k_b/etl/sources/clipping.py`) : les changer ne déclenche
rien. C'était la condition de Sabine : « un champ que la base ne garde pas ne déclenche rien ».

Les valeurs sont gardées **au format de la base**, en chaînes. Elles sont donc comparées telles
que SQLite les rend. Un `datetime` comparé à une chaîne serait toujours différent, et chaque
recopie deviendrait une révision.

Le type de `body` et `saved_at` est `str | None` parce que `Item` les déclare ainsi ; pour un
clip, l'item les exige (`REQUIRED_FIELDS_BY_KIND`).

### 3. La recette de l'écriture

`src/k_b/database/writers/clip_writer.py:65-69`

```python
    row = connection.execute(
        INSERT_ITEM_OF_NEW_CLIP, {"raw_data_id": raw_data_id, "url": item.url}
    ).fetchone()
    if row is None:
        return write_known_clip(connection, item, raw_data_id, content)
```

Le début ne change pas. L'item n'est créé que si aucun clip n'a cette URL
(`INSERT … SELECT … WHERE NOT EXISTS … RETURNING id`). Si rien n'est rendu, le clip est connu, et
`write_known_clip` décide.

`src/k_b/database/writers/clip_writer.py:104-115`

```python
    if known_content == content:
        if not is_file_before:
            shared_rows.point_item_at_raw_data(connection, known_item_id, raw_data_id)
        return Discard("already_seen", item, known_collected_at)
    if is_file_before:
        return Discard("no_newer_version", item, known_collected_at)
    connection.execute(
        UPDATE_CLIP,
        content._asdict() | {"item_id": known_item_id, "revised_at": collected_at},
    )
    shared_rows.point_item_at_raw_data(connection, known_item_id, raw_data_id)
    return None
```

La fonction voit trois cas, dans l'ordre :
1. **Même contenu** : la copie est écartée `already_seen`, comme avant (critère de #259).
2. **Contenu différent, mais fichier plus ancien** que le brut du clip : la copie est écartée
   `no_newer_version`. La base ne revient pas en arrière.
3. **Contenu différent, fichier de la même collecte ou plus récent** : `UPDATE` du clip,
   `revised_at` daté, et l'item pointe sur le brut de la nouvelle version (`item.raw_data_id`).
   L'item garde ainsi la trace du fichier d'où vient ce qui est en base.

Une réécriture ne va pas au journal d'import. Ce n'est pas un rejet, et une révision Zotero n'y
va pas non plus.

### 4. La garde d'ordre, et le bogue qu'a trouvé la revue

`src/k_b/database/writers/clip_writer.py:27-34`

```python
SELECT_KNOWN_CLIP = """
SELECT clip.item_id, clip.title, clip.body, clip.saved_at, clip.published_at,
    raw_data.collected_at, :collected_at < raw_data.collected_at
FROM clip
JOIN item ON item.id = clip.item_id
JOIN raw_data ON raw_data.id = item.raw_data_id
WHERE clip.url = :url
"""
```

Comparer les dates en SQL plutôt qu'en Python a deux raisons. Les deux valeurs sont du texte au
format de la base, dont l'ordre est celui du temps (`dates.py`). Et `catalog.py` compare déjà
ainsi (`:collected_at > max(raw_data.collected_at)`).

Le `<` est strict, et ce n'est pas un détail. Deux fichiers d'une même URL dans une même
collecte ont la même date. Avec `<`, aucun n'est « avant » l'autre : le second, dans l'ordre des
noms de pages, réécrit le premier. C'est la limite écrite dans l'issue.

**Le bogue trouvé par `/code-review`.** La première version ne déplaçait l'item que lors d'une
réécriture. Supposons trois fichiers :
- v1, collectée le 17, importée ;
- une copie identique du 19, écartée `already_seen` ; l'item restait sur le 17 ;
- v2, collectée le 18, importée en retard.

Le 18 n'est pas avant le 17 : v2 était écrite, alors que la copie la plus récente portait v1. Le
correctif (ligne 105-106) : une copie au même contenu, si elle n'est pas plus ancienne, déplace
l'item sur son brut. L'item pointe donc toujours sur **le brut le plus récent de son contenu**, et
la garde se compare à lui. Le test
`test_an_older_version_imported_after_a_newer_copy_of_the_same_content_is_left_out` a échoué avant
le correctif, et passe après.

### 5. Lire la ligne connue par nom

`src/k_b/database/writers/clip_writer.py:87-103` : la ligne lue est dépaquetée colonne par
colonne, puis `ClipContent` est construit par ses champs nommés (`title=known_title`, …). La
première version utilisait `known_item_id, *known_content, …` et `ClipContent._make` : l'ordre
du `SELECT` devait alors suivre celui des champs, sans rien pour le garantir. La revue l'a
relevé, et #260 ajoutera les tags à cette comparaison : le lien est maintenant visible dans la
fonction.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Comparaison en Python, puis `UPDATE clip` | Le SQL reste portable. L'item reste créé seulement si le clip est absent. #260 comparera un ensemble de tags lu dans une table de liaison. | Un upsert `ON CONFLICT (url) DO UPDATE … WHERE (…) IS NOT (…)`, comme Zotero : comparer deux lignes par `IS NOT` est une forme de SQLite, PostgreSQL écrit `IS DISTINCT FROM` ; et les tags échapperaient à ce `WHERE`. |
| Garde d'ordre `no_newer_version` | La base ne revient pas à une version plus ancienne (deux imports à la fois, un brut importé en retard), comme pour les catalogues d'état et arXiv. | Pas de garde : plus court, mais une régression silencieuse possible. |
| L'item pointe sur le brut le plus récent de son contenu, copie identique comprise | Corrige le bogue de la revue (tri de time-knight, délégation de Sabine du 2026-10-15). | Comparer à la collecte la plus récente de tous les bruts de l'URL : `raw_data` ne relie pas un fichier à une URL, il faudrait une colonne de plus. |
| `revised_at` posé même quand le changement est vu dans la collecte qui a créé le clip | La date dit « la collecte qui a vu le changement ». | Un cas à part : une branche de plus pour un cas limite. |
| Règle `no_newer_version` existante, pas de règle nouvelle | Même sens, et même champ au journal (`compared_with_collected_at`). | Une règle `older_clip` : un nom de plus pour la même chose. |
| Base du POC recréée, sans migration | Décision de Sabine : « je n'ai rien changé dans zotero. Et pour cisa on ne perdrait que des dates de retraits […] Donc pas grave ». | Un `ALTER TABLE` à la main, sans perte (la recommandation de la session). |

Ce qu'impose une consigne du dépôt : le SQL portable (règle 1 de `poc.md`), les tests d'abord à
partir des fixtures tirées de clips réels (`tests/fixtures/clipping/`, consigne du 2026-10-10),
et la correction de l'ancienne règle partout où elle était écrite (règle 7 de `code.md`).

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_clip_copied_again_with_the_same_content_is_left_out` | Même contenu : `already_seen`, `revised_at` vide, l'item pointe sur la copie la plus récente. |
| `test_a_clip_whose_content_changed_is_written_again`, six cas (`text`, `title`, `created`, `published`, `published_removed`, `published_added`) | Chaque champ gardé, y compris le passage de `published_at` à `NULL` et l'inverse, réécrit le clip : `revised_at` = la collecte du changement, l'item pointe sur le nouveau brut, rien au journal. |
| `test_a_change_of_a_property_the_base_does_not_keep_is_left_out` (`author`, `description`) | Un champ que la base ne garde pas ne déclenche rien. |
| `test_an_older_version_imported_after_a_newer_one_is_left_out` | Un fichier plus ancien au contenu différent est écarté `no_newer_version`, comparé à la collecte de la version gardée. |
| `test_an_older_version_imported_after_a_newer_copy_of_the_same_content_is_left_out` | Le cas du bogue : il échouait avant `8fac214`, il passe après. |
| `test_of_two_files_of_one_url_in_a_collection_the_second_is_written_again` | Dans une même collecte, le second fichier réécrit le premier, `revised_at` = cette collecte. |
| `test_a_rebuilt_base_is_the_same` (inchangé, vert) | Une base reconstruite depuis le brut est identique. |
| `tests/test_schema.py`, ligne `("clip", "length(revised_at) = 20", …)` | La base refuse une `revised_at` mal formée. |
| `uv run pytest -q` → 1814 passed ; `ruff check`, `ruff format --check`, `mypy --strict` verts | Les contrôles de la CI passent. |
| Comptes de la règle 1 de `poc.md` : 36, 11, 52 | Aucun SQL propre à SQLite ajouté. |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas comparer dans un `UPDATE … WHERE` comme pour Zotero ?** Comparer deux
   lignes par `IS NOT` est une forme de SQLite ; PostgreSQL écrit `IS DISTINCT FROM`. La base passe
   à PostgreSQL au 08/11 (règle 1 de `poc.md`). Et les tags de #260 vivront dans une autre table :
   un `WHERE` sur la ligne du clip ne les voit pas. (`clip_writer.py:104`)
2. **Que se passe-t-il si Sabine change seulement l'auteur d'un clip ?** Rien en base : `author`
   n'est pas lu, il n'est pas dans `ClipContent`. La copie est écartée `already_seen`, et l'item
   pointe sur ce dernier brut. (`clip_writer.py:44-53`, test `[author]`)
3. **Un import en retard peut-il remettre une vieille version ?** Non : un fichier plus ancien
   que le brut du clip est écarté `no_newer_version`. Une copie identique plus récente déplace
   l'item, donc la garde voit toujours la date la plus récente du contenu gardé.
   (`clip_writer.py:27-34`, `:104-109`)
4. **Pourquoi `<` et pas `<=` ?** Deux fichiers d'une même collecte ont la même date : avec `<=`,
   le second serait écarté et le premier gagnerait. Avec `<`, le second réécrit le premier,
   comme l'écrit l'issue. (`test_of_two_files_of_one_url_in_a_collection_the_second_is_written_again`)
5. **Ce texte « immuable » du *cleansed*, il change donc ?** Selon la précision de Sabine du
   2026-10-19 : le *cleansed* n'est jamais purgé ; le texte d'un clip est immuable **par usage**
   (Sabine ne le modifie pas) ; s'il change quand même, la même règle le prend. Journal ADR,
   « Collecte : mise à jour des `.md` importés ».

## Zones non vérifiées

- **PostgreSQL** : aucun test ne tourne sur PostgreSQL. La portabilité de `SELECT_KNOWN_CLIP` et
  d'`UPDATE_CLIP` est lue, pas exécutée. En particulier, `:collected_at < raw_data.collected_at`
  rend un booléen en PostgreSQL et 0 ou 1 en SQLite ; le code le lit comme une vérité, ce qui
  vaut pour les deux, mais ce n'est pas testé.
- **Le comportement de PostgreSQL** pour `IS NOT` entre deux lignes : je me fonde sur la liste
  des opérateurs de la page « Row and Array Comparisons », sans l'avoir exécuté.
- **Une base existante** : sans la colonne `revised_at`, l'`UPDATE` lève `OperationalError`, et
  l'import s'arrête. La base du POC doit être recréée (décision de Sabine). Ce cas n'est pas testé.

## Ce qui reste

- **Les tags** du clip, dans la comparaison et en base : #260.
- **L'API de données** n'expose pas `clip.revised_at`, alors que Zotero et les vulnérabilités
  exposent le leur : signalé dans la PR, Sabine décidera où le traiter.
- **« Quoi de neuf »** (filtre `since`) date un clip par `saved_at` : un clip réécrit n'y revient
  pas. Limite écrite à l'ADR ; la suite après la mise à jour d'un `.md` relève de #148.
- **`manual_notes`** : nommé dans l'ADR, sans code.

## Sources

| Source | URL | Consultée le |
|---|---|---|
| PostgreSQL 18, « 9.25. Row and Array Comparisons » (comparaison de constructeurs de lignes : `=`, `<>`, `IS DISTINCT FROM`…) | https://www.postgresql.org/docs/current/functions-comparisons.html | 2026-10-19, par recherche web |
| SQLite, « Row Values » (deux lignes de même taille se comparent par `IS` et `IS NOT`) | https://www.sqlite.org/rowvalue.html | 2026-10-19, par recherche web |
