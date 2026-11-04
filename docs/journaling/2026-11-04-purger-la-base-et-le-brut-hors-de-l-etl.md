# Purger la base à 3 ans et le brut à 6 mois, hors de l'ETL

- **Date** : 2026-11-04
- **Branche** : `feat/retention-purge`
- **Issue** : #83 (cite #276)
- **Fichiers principaux** : `src/k_b/purge/` (`after_import.py`, `base.py`, `catalogs.py`, `raw.py`,
  `registry.py`), `src/k_b/database/purge.py`, `src/k_b/etl/raw_store.py`,
  `src/k_b/commands/import_command.py`
- **Série** : suit `2026-10-19-ne-garder-que-le-dernier-brut-des-catalogues-d-etat.md`

## Le pourquoi

Le registre des traitements annonçait des durées de conservation que rien n'appliquait : la veille
restait en base et dans le brut sans limite. Le critère C4 d'E1 demande des procédures de tri ; une
procédure décrite mais pas codée n'en est pas une.

Tes décisions du 2026-11-04 fixent la règle :

| Source | Brut | Base |
|---|---|---|
| arXiv, TLDR, releases et alertes GitHub | 6 mois | 3 ans |
| GH Archive | 6 mois | `trend` : 3 ans depuis la collecte |
| CISA KEV, Zotero | dernier fichier importé seul | sans limite |
| Tops GitHub | dernier relevé lisible, 6 mois au plus | pas en base |
| Clips | 6 mois | sans limite |

Ta raison pour les 6 mois : « Une veille de plus de six mois n'est plus de première fraîcheur. Ça
minimise aussi le stockage et retire des données inutilisées. » La base devient la source de vérité :
le brut ne la reconstruit plus que sur ses 6 derniers mois.

## Le comment

### 1. Un paquet à part, lancé par la commande

La purge n'est ni une extraction, ni une transformation, ni un chargement. Elle vit dans
`src/k_b/purge/`, à côté de `post/`, et `kb import` l'appelle après avoir affiché son bilan
(`commands/import_command.py:75`, puis `:87-91`) :

```python
purge_after_import(
    data_dir, imported_at, STATE_CATALOGS, GITHUB_TRACKED_REPOSITORIES
)
```

La commande nomme les catalogues d'état et la liste des dépôts ; `purge/` ne connaît aucune source.
Le SQL reste dans `database/purge.py` (règle 5 de `conventions.md`) et l'accès aux fichiers dans
`RawStore` (règle 3 de `poc.md`). Les tests d'architecture tiennent ces frontières.

### 2. Quatre étapes, le registre en dernier

`purge/after_import.py:44-52` :

```python
delete_superseded_raw_files(store, imported_paths, folder_keys)
purge_expired_rows(
    database_path,
    imported_at,
    source_codes,
    [repository.name for repository in tracked_repositories],
)
delete_expired_raw(store, imported_at, folder_keys, imported_paths)
purge_registry(database_path, store, source_codes)
```

Le registre (`raw_data`) passe en dernier, parce qu'une de ses lignes ne part que si son fichier a
disparu et que plus rien ne la cite. Il faut donc que le brut et la base aient déjà été purgés. La
première erreur arrête la suite : `kb import` sort en 1, et l'import suivant relance tout. L'import
reste enregistré dans tous les cas : la purge a sa propre transaction, ouverte après le commit
(`purge/base.py:36-50`).

### 3. Supprimer dans l'ordre des clés étrangères

Le schéma n'a pas de cascade vers les sous-types. `database/purge.py:132-145` lit donc une seule fois
les items expirés, puis supprime les sous-types avant les items :

```python
for statement in (
    DELETE_RELEASE_OF_ITEM,
    DELETE_ADVISORY_OF_ITEM,
    DELETE_NEWSLETTER_ARTICLE_OF_ITEM,
    EMPTY_PAPER_OF_ITEM,
):
    connection.executemany(statement, item_ids)
return connection.executemany(DELETE_ITEM, item_ids).rowcount
```

Un papier n'est pas supprimé mais **vidé** (`database/purge.py:26-30`) : le `CHECK` de `publication`
impose que `item_id`, le titre, le résumé, les auteurs et les deux dates soient vides ensemble. La
ligne ne garde alors que l'identifiant arXiv. Si une entrée Zotero ou un article de newsletter la
cite, elle reste comme référence ; sinon, `DELETE_UNCITED_PUBLICATIONS` la supprime. Dans les deux
cas, les auteurs sont partis.

Aucun code ne supprime un item `vulnerability`, car CISA KEV n'expire jamais. S'il en expirait un
par erreur, la clé étrangère refuserait la suppression et toute la purge de la base serait annulée :
c'est un échec fermé, et un test le prouve.

### 4. La borne : le calendrier, en UTC, stricte

`core/dates.py:28-35` recule dans le calendrier, sans compter de jours : 3 ans depuis un 29/02
tombent le 28/02. `purge/base.py:88-92` calcule la borne source par source :

```python
years = RETENTION_YEARS_BY_ACQUISITION_MODE[source.acquisition_mode]
if years is None or source.source_code in state_catalog_source_codes:
    return None
bound = subtract_months(imported_at.astimezone(UTC), years * 12)
return bound.strftime(DATABASE_DATE_FORMAT)
```

Le test est strict (`collected_at < bound`) : une donnée collectée pile à la borne reste. Le passage
en UTC compte : sans lui, un changement d'heure décale la borne d'une heure (un test le montre avec
`Europe/Paris`).

### 5. Le brut : lu dans le dossier, et jamais suivre un lien

La liste vient du dossier, pas du registre (`purge/raw.py:28-39`), parce que 6 mois est un maximum
et que les relevés des tops n'entrent jamais au registre. `RawStore.delete_collection`
(`etl/raw_store.py:97-115`) refuse de toucher à ce qu'il ne maîtrise pas :

```python
if path.is_symlink():
    return "kept"
if not path.is_dir():
    path.unlink()
    return "deleted"
entries = list(path.iterdir())
if any(is_kept_in_a_collection(entry) for entry in entries):
    return "kept"
```

Un lien, un dossier dans un dossier de pages, ou un nom contenant `\` gardent la collection. Sur
macOS et Linux, `\` est un caractère ordinaire d'un nom, mais les clés de `RawStore` le refusent : ce
nom ne peut venir que d'un fichier posé à la main.

### 6. Le registre : trois gardes avant de supprimer une ligne

`purge/registry.py:56-65` :

```python
if row.raw_file_path.partition("/")[0] in mounted_dir_names
and not (
    row.source_id in state_catalog_source_ids
    and row.collected_at == last_collections[row.source_id]
)
and is_file_gone(store, row.raw_file_path)
```

- **Le dossier d'acquisition doit exister** : un volume non monté ferait croire que tous ses fichiers
  ont disparu, et ils seraient réimportés à son retour.
- **Le dernier catalogue d'un catalogue d'état reste**, même sans item qui le cite : l'import y lit
  quel catalogue est le dernier (`SELECT_LATEST_CATALOG`, `database/writers/catalog.py:17-23`). Le
  supprimer ferait prendre un catalogue tardif pour plus récent.
- **Un chemin que le store refuse reste** (`is_file_gone`, `purge/registry.py:68-74`).

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Paquet `purge/` hors de l'ETL | ta décision ; la purge n'est ni E, ni T, ni L | `etl/raw_purge.py` et `etl/pipeline.py` (décision du 23/10, révisée) |
| Lancée à la fin de `kb import` | sur le Mac rien n'est planifié : elle tourne dès qu'un import tourne | `kb purge` ou `cron_jobs/` : le cron vit hors du code, et une commande à part pourrait ne jamais tourner |
| `trend` datée par `collected_at` | ta décision ; une seule règle pour toute la veille | `window_end` : une seconde règle pour quelques jours d'écart |
| CISA KEV sans limite en base | ta décision ; la base porte l'état du catalogue | 3 ans : une entrée encore au catalogue serait purgée, puis réécrite |
| Copies des clips à 6 mois | ta décision (option b) ; le clip reste dans le coffre et en base | les garder sans limite : une troisième copie |
| Une donnée republiée est une nouvelle collecte | ta décision (option a) | écarter un item trop ancien à l'import : perdrait la mise à jour d'une alerte |
| Un fichier jamais importé part, et le journal le compte | ta décision (option b) | le garder sans limite ; ne pas le compter |
| Dépôt suivi supprimé hors de la liste et sans release | ta décision ; la clé étrangère l'impose | tout supprimer dès le retrait de la liste : des releases perdues avant 3 ans |
| Items expirés lus une fois, supprimés par identifiant | constat de revue : la condition était copiée 5 fois ; mesuré à 0,012 s pour 1 290 items | une sous-requête par instruction (doublon) |
| `RawStore` laissé dans `etl/` | le déplacer touche 21 modules, hors de #83 | un paquet de stockage : piste à revoir avec le passage à Blob |
| Rien de codé pour les tags | seuls les clips en portent, et ils ne sont pas purgés | une suppression sans effet |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_watch_collected_more_than_three_years_ago_leaves_with_its_subtypes` | la veille expirée part avec ses sous-types ; CISA, TLDR plus récent, Zotero et clips restent |
| `test_a_paper_still_cited_keeps_only_its_arxiv_identifier` | les auteurs partent, l'identifiant reste |
| `test_the_state_catalogs_and_the_library_are_kept_without_limit` | ce que tu déposes n'est pas purgé en base |
| `test_a_trend_row_leaves_three_years_after_the_collection_of_its_file` | `collected_at`, pas `window_end` ; la borne est stricte |
| `test_an_expired_item_of_a_state_catalog_fails_the_purge_and_changes_nothing` | l'échec fermé annule toute la purge de la base |
| `test_a_link_is_never_followed` | rien n'est supprimé hors de `raw/` à travers un lien |
| `test_the_bound_is_computed_in_utc_whatever_the_time_zone_given` | la borne ne dépend pas du fuseau |
| `test_the_last_catalog_of_a_state_catalog_stays_without_its_file` | l'import garde son repère |
| `test_without_its_acquisition_folder_no_row_of_it_is_deleted` | un volume non monté n'efface pas le registre |
| `test_a_sigterm_during_the_purge_of_the_base_keeps_the_import_and_undoes_the_purge` | code 143, import gardé, purge annulée |
| `test_a_purge_stopped_midway_is_finished_by_the_next_one` | une purge du brut interrompue reprend |
| `test_import_purges_what_it_committed_once_past_its_durations` | de bout en bout : la purge suit le commit |
| `uv run pytest` : 3 327 verts ; `ruff`, `mypy --strict` verts | les contrôles du dépôt |
| Mutations sur une copie : 23/24, puis 13/14 tuées | survivant 1 : le `rollback` explicite, équivalent (`close()` annule) ; survivant 2 : une garde inutile, retirée |
| Compteurs de la règle 1 de `poc.md` : 36 / 8 / 49 ; règle 3 : 12 fichiers | inchangés par rapport à `main` |

Les tests ont été écrits avant le code. Le premier rouge était surtout un échec d'import (modules
absents) ; ceux des corrections de revue étaient des échecs de comportement.

**Tri des revues.** 1re `/code-review` (10 constats) : 1, 4, 5, 8, 9 et 10 corrigés ; 2, 6 et 7
écartés (tes décisions, garantie du `CHECK`) ; 3 : ton option b. 2e `/code-review` (7 constats) : 1,
2, 4 et 5 corrigés ; 3 hors de cette PR (déjà sur `main`) ; 6 écarté (mesure) ; 7 écarté (annoncé au
choix b).

## Ce que tu dois pouvoir défendre

1. **Pourquoi garder la veille 3 ans en base, mais le brut 6 mois ?** La base sert à interroger la
   veille ; le brut n'a plus d'usage une fois importé, et aucune collecte ne le relit. Moins de
   stockage, et les logins qui ne sont que dans le brut partent plus tôt. (`core/config.py`,
   `RAW_RETENTION_MONTHS`.)
2. **Que se passe-t-il si la purge échoue ?** L'import reste enregistré et son bilan est affiché. Le
   journal dit `import committed, purge failed`, `kb import` sort en 1, et l'import suivant relance
   la purge. (`commands/import_command.py:87-100`.)
3. **Où est la sécurité ?** Les clés de `RawStore` refusent `..`, un chemin absolu et `\`
   (`find_path`) ; un lien n'est jamais suivi ; le SQL est paramétré, sans valeur dans le texte ; le
   journal ne donne que des nombres.
4. **La base est la seule copie au-delà de 6 mois : n'est-ce pas un risque ?** Si, tant que la
   sauvegarde n'existe pas, et c'est une limite écrite au registre. Une fois la sauvegarde en place,
   le brut partira dès que deux sauvegardes saines le couvrent.
5. **Pourquoi un item purgé peut-il revenir ?** Une release encore parmi les 100 dernières de son
   dépôt, ou une alerte mise à jour, est collectée à nouveau : c'est une nouvelle collecte, et ses 3
   ans repartent. Tu as accepté cette limite. (Registre, étape 2.)

## Zones non vérifiées

- **PostgreSQL** : le SQL est écrit pour être portable (règle 1 de `poc.md`), mais il n'a tourné que
  sur SQLite. La somme de `executemany(...).rowcount` est observée sur `sqlite3` ; elle n'est pas
  vérifiée sur un pilote PostgreSQL.
- **`kb import` n'a pas tourné en vrai avec des données expirées** : les preuves sont les tests, et
  une mesure de `purge_expired_rows` sur une copie de la base d'essai du 29/10, datée de 2099.
- **Bibliothèque standard** : `calendar.monthrange`, `pathlib` et `executemany` n'ont pas été relus
  dans Context7 ; leur comportement est prouvé par les tests.
- **Le compte « never imported » est approché pour un dossier de pages** : le dossier compte comme
  importé dès qu'une de ses pages l'est.
- **`raw/` et les dossiers d'acquisition** : un lien à ce niveau est suivi, comme partout dans K-B ;
  seuls les dossiers de source et ce qu'ils contiennent sont protégés.
- **Un fichier ajouté à un dossier de pages pendant sa suppression** ferait échouer `rmdir`, donc la
  purge de ce passage : ce cas n'a pas de test.
- **Revue de sécurité** : son résultat est dans le compte rendu de la PR.

## Ce qui reste

- **La sauvegarde de la base**, et la purge du brut après deux sauvegardes saines : règle écrite au
  registre (étape 3), en attente de « La base au temps 3 » ; issue à créer.
- **Des migrations** : dès que le plus ancien brut a 6 mois, un changement de schéma ne peut plus
  passer par une reconstruction (journal ADR, 2026-10-09, W7).
- **#267** : les journaux gardés 30 jours, dans une PR à part.
- **#268 et la liste d'exclusion** (#20) : l'effacement à la demande d'une personne.
- **`list_file_keys`** ne filtre pas les noms contenant `\` : défaut déjà sur `main`, hors de cette PR.
- **Le déplacement de `RawStore`** hors de `etl/`.
- **La règle 5 de `.claude/rules/conventions.md`** ne cite ni `purge/` ni `database/purge`, et son
  `grep` cite encore `raw_purge` : à compléter par Sabine.
