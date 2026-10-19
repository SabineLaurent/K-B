# Garder en base les tags des clips, normalisés, dans une table partagée

- **Date** : 2026-10-19
- **Branche** : `feat/clip-tags`
- **Issue** : #260
- **Fichiers principaux** : `src/k_b/database/schema.sql` (tables `tag` et `item_tag`),
  `src/k_b/items.py` (type `Tag`), `src/k_b/etl/sources/clipping.py` (lecture des tags),
  `src/k_b/database/writers/clip_writer.py` (écriture en *patch*)
- **Série** : suite de [Réécrire un clip dont le contenu a changé](2026-10-19-reecrire-un-clip-dont-le-contenu-a-change.md)
  (#259), dont cette PR revoit l'écriture.

La branche compte seize commits, de `59c547e` à `d0f4698`, tous couverts par cette note. Les
commits plus anciens de la liste fournie (de `53575fd` en descendant) sont déjà sur `main`. De
même, la plupart des fichiers de la liste fournie appartiennent à des PR fusionnées. Ceux de
cette branche sont les onze fichiers de `git diff origin/main...HEAD --stat`. Le commit
`51ce6e9` (registre : le login du propriétaire d'un dépôt suivi) est une demande de Sabine faite
pendant la PR, hors des tags ; la section 8 en parle.

## Le pourquoi

Un clip porte des tags dans son frontmatter. Jusqu'ici, K-B ne les lisait pas : l'ADR du
2026-10-17 les gardait hors de la base. Sabine a décidé le 2026-10-19 de les y faire entrer, pour
deux raisons. Le wiki regroupera les fiches par tag (#148). Et un tag doit pouvoir servir à
plusieurs sortes de `.md` : `clipping` aujourd'hui, `manual_notes` plus tard.

Elle a choisi l'option (a) : une table `tag` partagée et une table de liaison. Elle a aussi
décidé :
- la forme d'un tag (minuscules, sans espaces autour, sans `#` au début) ;
- l'écart du tag `clippings`, que Web Clipper met sur chaque clip ;
- que les tags font partie du contenu d'un clip : un tag ajouté ou retiré date `revised_at` (#259) ;
- que l'écriture se fait en *patch*, pas en *put* ;
- qu'un tag dont la dernière liaison part est supprimé.

## Le comment

### 1. La relation plusieurs-à-plusieurs

`src/k_b/database/schema.sql:324-340`

```sql
CREATE TABLE tag (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
        CHECK (length(name) > 0)
        CHECK (length(name) <= 100)
) STRICT;

CREATE TABLE item_tag (
    item_id INTEGER NOT NULL REFERENCES item (id) ON DELETE CASCADE,
    tag_id  INTEGER NOT NULL REFERENCES tag (id),
    PRIMARY KEY (item_id, tag_id)
) STRICT;

CREATE INDEX item_tag_tag_id ON item_tag (tag_id);
```

Un clip a plusieurs tags, et un tag sert à plusieurs clips. Ni une colonne `tag_id` dans `clip`
(un seul tag par clip) ni une colonne `item_id` dans `tag` (un seul clip par tag) ne peut le
dire. Au MCD, c'est une association « porter » entre ITEM et TAG, de cardinalités 0,n des deux
côtés. Au MLD, une association n,n devient une table, ici `item_tag`. Cette table a pour clé
primaire le couple des deux clés étrangères.

Ce que chaque ligne garantit :
- **`tag.name UNIQUE`** : un tag est une seule ligne. `llm` porté par deux clips, c'est une ligne
  de `tag` et deux lignes de `item_tag`.
- **`PRIMARY KEY (item_id, tag_id)`** : un item porte chaque tag une fois. La clé sert aussi
  d'index pour « les tags d'un item », puisque `item_id` est en tête.
- **`item_tag_tag_id`** : l'index de l'autre sens, « les items d'un tag », la lecture du wiki
  (#148). SQLite n'indexe pas d'office une clé étrangère (`docs/stockage.md`, « Index »).
- **`ON DELETE CASCADE`** : supprimer un item emporte ses liaisons, comme ses surlignages
  (`highlight.item_id`, `schema.sql:97`).
- **Liaison sur `item` et non sur `clip`** : `manual_notes` aura sa propre sorte d'item et
  réutilisera la même liaison sans migration. La provenance d'un tag se lit par `item.kind`.

Les `CHECK` ne tiennent que la longueur, en SQL portable (règle 1 de `poc.md`). Contrôler les
minuscules par un `CHECK (name = lower(name))` dirait deux choses différentes : le `lower` de
SQLite ne connaît que l'ASCII, celui de PostgreSQL tout Unicode.

### 2. La forme d'un tag, tenue à un seul endroit

`src/k_b/items.py:115-118`

```python
def normalize_tag(tag: str) -> str:
    """A tag as the base keeps it (decision of Sabine of 2026-10-19): without the spaces around
    it, without the # Obsidian writes at its start, in lower case."""
    return tag.strip().removeprefix("#").strip().lower()
```

L'ordre des étapes compte. `"# llm"` devient `"llm"` grâce au second `strip()` : la relecture du
plan avait vu qu'avec un seul `strip()`, le résultat gardait une espace. `removeprefix` retire un
seul `#` : `##llm` donne `#llm`.

Le type `Tag` (`items.py:197`) refuse ensuite ce que la base refuserait, et plus :
- vide ;
- plus de 100 caractères, avec la longueur reçue dans le message (`check_tag_length`, règle 3
  de `conventions.md`) ;
- un tag que `normalize_tag` changerait encore (`check_tag_is_normalized`) : `#llm` est refusé ;
- un NUL ou un surrogate isolé (`CAN_BE_STORED`).

L'item refuse aussi plus de 30 tags (`check_tag_count`) et un tag en double (`check_tags_once`).
Sans ce dernier contrôle, la clé primaire de `item_tag` refuserait le doublon, ce que
`savepoint.py` ne rattrape pas : tout l'import s'arrêterait.

### 3. La lecture dans le frontmatter

`src/k_b/etl/sources/clipping.py:346-350`

```python
def normalize_tags(tags: tuple[str, ...]) -> tuple[str, ...]:
    """Each tag normalized (items.py), once, sorted by name: the import is the same whatever the
    order of the vault. ..."""
    return tuple(sorted({normalize_tag(tag) for tag in tags} - {"", TEMPLATE_TAG}))
```

Avant elle, `read_tags` (`clipping.py:334`) remet la valeur YAML en liste :
- un texte seul donne un tag ;
- une valeur absente (vide, `null`, `~`) ne donne aucun tag ;
- un élément absent est ignoré ;
- un dictionnaire ou une liste imbriquée passe tel quel à pydantic, qui le refuse.

Puis `normalize_tags` :
- normalise chaque tag ;
- fond les doublons par un ensemble, et retire le vide et `clippings` ;
- trie par nom.

Le tri rend l'import déterministe, quel que soit l'ordre du coffre.

Un tag refusé (trop long, NUL, `##llm`) fait refuser le clip entier, par la voie de rejet des
autres propriétés. Le message nomme le champ (`tags`) et la mesure, jamais la valeur
(`without_values`, `core/quoting.py`) : un tag peut nommer une personne.

### 4. Le *patch* plutôt que le *put*

`src/k_b/database/writers/clip_writer.py:162-172`

```python
    changed = {
        column: value
        for column, value in content.to_columns().items()
        if value != known_columns[column]
    }
    assignments = [f"{column} = :{column}" for column in [*changed, "revised_at"]]
    connection.execute(
        # The names are the keys of ClipContent.to_columns, written in this module.
        UPDATE_CLIP.format(assignments=", ".join(assignments)),
        changed | {"item_id": item_id, "revised_at": revised_at},
    )
```

En HTTP, un `PUT` remplace la ressource entière, un `PATCH` ne change que ce qu'on lui donne. Ici
le mot désigne l'écriture d'un clip qui a changé. Sabine a choisi le *patch* : « je veux le
patch. C'est plus sobre et propre ».

Le `SET` ne nomme donc que les colonnes qui ont changé, plus `revised_at`. Les noms de colonnes
viennent des clés de `ClipContent.to_columns` (`clip_writer.py:78`), dérivées des champs du
`NamedTuple`. Ils ne viennent jamais d'une valeur lue dans le clip, et chaque valeur est un
paramètre lié. C'est ce qui rend sûre la construction de la requête : `/security-review` l'a
vérifié.

Les tags suivent le même principe (`clip_writer.py:175-187`) :
- la liaison d'un tag retiré est supprimée (`DELETE_ITEM_TAG`) ;
- le tag lui-même part s'il n'a plus aucune liaison (`DELETE_TAG_WITHOUT_LINK`, `NOT EXISTS`) ;
- seule la liaison d'un tag ajouté est écrite ;
- les liaisons inchangées ne bougent pas.

Les tags se comparent comme un ensemble (`frozenset`), sans leur ordre : l'ordre d'un `ORDER BY`
dépend de la collation, qui n'est pas la même en SQLite et en PostgreSQL.

### 5. Les deux exceptions à la règle 5

`src/k_b/database/writers/clip_writer.py:48-59`

La règle 5 de `conventions.md` dit que K-B « ne supprime que par la purge ». Les deux `DELETE`
de cette PR sont les premiers de `src/k_b`, et chacun est une exception nommée par Sabine :

| Suppression | Raison de Sabine | Pourquoi ce n'est pas un item supprimé |
|---|---|---|
| La liaison d'un tag retiré | « Un tag supprimé n'existe plus en base. Je ne vois pas l'utilité qu'aurait le fait de le garder en revised at. » | Une liaison est une valeur d'une version du clip, comme une colonne que l'`UPDATE` écrase. |
| Le tag qui n'a plus de liaison | « on le supprime » ; « Un tag supprimé n'existe plus en base » | Un tag n'est pas un item ; sans liaison, il n'a ni usage ni durée, et il peut nommer une personne. |

Le « retiré, jamais supprimé » des entrées Zotero (2026-10-13) n'est pas touché : il vaut pour des
items.

### 6. L'id d'un tag, lu et non deviné

`src/k_b/database/writers/clip_writer.py:195-204`

```python
    for tag in tags:
        connection.execute(INSERT_TAG, {"name": tag})
        (tag_id,) = connection.execute(SELECT_TAG_ID, (tag,)).fetchone()
        connection.execute(INSERT_ITEM_TAG, {"item_id": item_id, "tag_id": tag_id})
```

`INSERT … ON CONFLICT (name) DO NOTHING` crée le tag s'il est nouveau, sans erreur s'il existe :
c'est portable en SQLite et en PostgreSQL. La première version faisait la liaison par
`INSERT … SELECT … WHERE name = :name`, qui n'insère rien, sans erreur, si le tag manque. Le
premier `/code-review` l'a relevé : le clip aurait perdu son tag en silence. Maintenant l'id est
lu : s'il manque, le dépaquetage lève une erreur et l'import s'arrête (échouer fermé, `code.md`).

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Table `tag` partagée et liaison `item_tag` | Décision de Sabine, option (a) : un tag partagé, prêt pour le wiki (#148). | — |
| Liaison sur `item` | `manual_notes` la réutilisera sans migration. | `clip_tag` : une table de liaison par sorte, à dupliquer. |
| Normaliser à la lecture du clip (T), une fonction dans `items.py` | La décision dit « à l'import » ; la forme est tenue à un seul endroit (règle 4). | Dans `normalize_item` : `clippings` est propre à Web Clipper, et la normalisation doit précéder la validation. Dans l'écrivain : la couche d'accès aux données ne transforme pas (règle 5). |
| `lower()` | La décision dit « en minuscules ». | `casefold()` change aussi `ß` en `ss`. |
| `removeprefix("#")` | La forme d'Obsidian a un seul `#`. | `lstrip("#")` lirait `##llm` comme `llm` sans décision. |
| `CHECK` de longueur seulement | Portable. | Un `CHECK` de casse : le `lower` de SQLite n'est pas celui de PostgreSQL. |
| 100 caractères, 30 tags au plus | Bornes de ressources. Le nombre est né du second `/code-review` (un clip de 1 Mo de tags d'une lettre écrirait environ 750 000 requêtes) ; sa valeur est de Sabine : « un garde-fou de ressources, pas une règle de rangement ». | Pas de nombre maximum (le plan s'appuyait sur la borne de 1 Mo du clip) ; 100, la valeur proposée. |
| `ON DELETE CASCADE` sur `item_tag.item_id` | Comme `highlight` (décidé par time-knight). | Pas de cascade : la purge devrait supprimer les liaisons elle-même. |
| *Patch* | Décision de Sabine : « plus sobre et propre ». | *Put* : plus simple, mais il écrit tout le texte, jusqu'à 1 Mo, pour un tag. |
| Supprimer les liaisons retirées | Décision de Sabine. | Un `withdrawn_at` sur `item_tag` : une colonne et un filtre pour un historique que rien ne demande. |
| Supprimer un tag sans liaison | Décision de Sabine. | Le garder jusqu'à la purge (proposé par time-knight) : un tag qui peut nommer une personne, sans durée. |
| Deux requêtes par tag (`INSERT … DO NOTHING`, `SELECT id`) | Un tag qui existe n'est pas réécrit (*patch*). | `ON CONFLICT DO UPDATE … RETURNING id` en une requête : il réécrit la ligne d'un tag connu. |
| `tag.id` interne, la clé stable est `tag.name` | Rien n'expose l'id. | `AUTOINCREMENT` contre la réutilisation d'un id en SQLite : un mot propre à SQLite (règle 1 de `poc.md`). |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_tags_of_a_clip_are_read_normalized` (10 cas, `tests/etl/sources/test_clipping.py`) | Normalisation (`LLM`, ` llm `, `#llm` → `llm`, `# llm` → `llm`), tri, texte seul, vide, `[]`, `null`, éléments absents, `clippings` sous trois formes écarté. |
| `test_a_clip_with_an_invalid_tag_is_refused_by_its_field` (6 cas) | Liste, mapping, 101 caractères, NUL, `##llm` : clip refusé, `tags` nommé, la valeur jamais citée. |
| `test_a_tag_too_long_is_refused_with_its_length_and_the_maximum`, `test_a_clip_with_too_many_tags_is_refused_with_its_count_and_the_maximum` | Les messages donnent la mesure reçue et le maximum. |
| `test_the_tags_of_a_clip_are_in_the_base_normalized`, `test_a_tag_carried_by_two_clips_is_one_row` (`tests/etl/test_load_clips.py`) | Les tags en base ; un tag partagé est une seule ligne de `tag`. |
| `test_a_clip_copied_again_with_its_tags_in_another_form_is_left_out` | `#Agents` et `LLM` au lieu de `agents` et `llm` : `already_seen`, la normalisation précède la comparaison. |
| `test_a_tag_added_or_removed_writes_the_clip_again` | Un tag ajouté puis retiré : liaisons justes, `revised_at` à chaque collecte. |
| `test_a_title_changed_alone_writes_only_the_title`, `test_a_tag_added_writes_only_its_link`, `test_a_tag_removed_removes_only_its_link`, `test_an_identical_clip_changes_nothing` | Le *patch* : un déclencheur `AFTER UPDATE OF <colonne>`, posé dans la base du test, enregistre chaque colonne que nomme le `SET` ; le `rowid` d'une liaison inchangée ne change pas. |
| `test_the_last_link_of_a_tag_removed_removes_the_tag`, `test_a_tag_another_clip_still_carries_stays` | Un tag sans liaison est supprimé ; un tag encore porté reste. |
| `tests/test_schema.py` : `CHECK` de `tag`, clés étrangères, liaison en double, cascade, `test_a_tag_the_base_refuses_is_refused_by_its_type`, `TAG_MAX_LENGTH` égal au `CHECK` | La base et l'item refusent les mêmes tags. |
| `uv run pytest -q` → 1856 passed ; `ruff check`, `ruff format --check`, `mypy --strict` verts ; comptes de la règle 1 : 36, 11, 52 | Les contrôles de la CI passent ; aucun SQL propre à SQLite ajouté. |

## Ce que tu dois pouvoir défendre

1. **Pourquoi une table de liaison et pas une liste de tags dans le clip ?** Un tag sert à
   plusieurs clips : en table, `llm` est une ligne, et « les clips d'un tag » se lit par un index
   (`item_tag_tag_id`). C'est l'association n,n du MCD, devenue une table au MLD.
   (`schema.sql:324-340`)
2. **Que se passe-t-il si Sabine écrit `LLM` dans un clip et `#llm` dans un autre ?** Les deux
   donnent `llm`, une seule ligne de `tag`, deux liaisons. Si elle réécrit `llm` en `LLM` dans le
   même clip, rien ne change : la comparaison se fait après normalisation. (`items.py:115`, test
   `…in_another_form_is_left_out`)
3. **Le `SET` construit par une f-string, n'est-ce pas une injection SQL ?** Non : les noms
   viennent des champs du `NamedTuple`, écrits dans le module ; les valeurs sont des paramètres
   liés. Aucune donnée du clip n'entre dans le texte SQL. (`clip_writer.py:162-172`)
4. **K-B ne supprime que par la purge : pourquoi ces deux `DELETE` ?** Ce sont deux exceptions
   nommées par Sabine, écrites à l'ADR : une liaison est une valeur d'une version, et un tag sans
   liaison n'a plus d'usage. (`clip_writer.py:48-59`)
5. **Un tag peut-il nommer une personne ?** Oui : c'est du texte libre. Il n'est jamais cité dans
   un journal ; le registre dit sa durée et son effacement (étapes 2 et 5).

## Zones non vérifiées

- **PostgreSQL** : rien ne tourne encore sur PostgreSQL. La portabilité de `ON CONFLICT … DO
  NOTHING`, du `NOT EXISTS` et du `SET` construit est lue, pas exécutée.
- **Le gain du *patch* sur le disque** : en PostgreSQL, la documentation TOAST dit qu'une colonne
  non modifiée garde sa valeur hors ligne. En SQLite, ce n'est pas établi (des essais du forum
  montrent la ligne entière réécrite dans certains cas). Non mesuré.
- **Le coffre réel** n'a pas été lu. Les tests partent des fixtures tirées de clips réels,
  modifiées dans chaque test. Ce que donne un vrai frontmatter de Sabine (virgules, espaces,
  `#tag` sans guillemets) est écrit en hypothèses, dans la spec.
- **Une base existante** : sans les tables `tag` et `item_tag`, l'import s'arrête (« no such
  table »). Il faut recréer la base, comme pour #259 ; ce cas n'est pas testé.
- **Les liaisons des items supprimés par cascade** laissent leurs tags jusqu'à la purge (#83),
  pas codée. Aucun code ne supprime d'item aujourd'hui, donc le cas ne se présente pas encore.

## Ce qui reste

- **Le wiki** regroupe les fiches par tag (#148, #149).
- **Le LLM** créera et reverra des tags par l'API de données, après le 25/10. La provenance d'un
  tag viendra par une migration ; la suppression d'un tag sans liaison sera à revoir alors.
- **L'API de données** n'expose ni les tags ni `clip.revised_at` (signalé, Sabine décide).
- **La purge (#83)** devra supprimer les tags sans liaison après les items.
- **`.claude/rules/conventions.md`** ne nomme pas encore les deux exceptions à la règle 5 :
  Sabine décide de l'y écrire (texte proposé dans la PR).
- **Hors des tags** (`51ce6e9`, demande de Sabine) : le registre dit maintenant que le login du
  propriétaire d'un dépôt suivi est en base (`tracked_repository.repository_name`). Le nom en
  clair dans trois messages d'erreur, et le cas de ce login dans l'étape d'effacement, attendent
  sa décision.

## Sources

| Source | URL | Consultée le |
|---|---|---|
| PostgreSQL, « TOAST » (une valeur hors ligne d'une colonne non modifiée est gardée) | https://www.postgresql.org/docs/8.1/storage-toast.html | 2026-10-19, par recherche web |
| SQLite, check-in « overwrite an existing btree cell … if the old and new cell are the same size » | https://www.sqlite.org/src/info/5887d8beb502ad62 | 2026-10-19, par recherche web |
| SQLite Forum, « Slow update table with large BLOB » (ligne réécrite dans d'autres cas) | https://sqlite.org/forum/forumpost/8019aa22f6?t=h | 2026-10-19, par recherche web |

**Addendum du 2026-10-19** : la table `item_tag` s'appelle désormais `item_has_tag`, et son index `item_has_tag_tag_id`, comme au MLD et au MPD de Sabine (#263) ; le texte ci-dessus garde l'ancien nom.
