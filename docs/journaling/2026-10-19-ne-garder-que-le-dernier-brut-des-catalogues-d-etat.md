# Ne garder que le dernier brut importé de Zotero et de CISA KEV

- **Date** : 2026-10-19
- **Branche** : `feat/keep-latest-state-catalog-raw`
- **Issue** : #139 (critère révisé le 19/10, décisions de Sabine relayées par time-knight)
- **Fichiers principaux** : `src/k_b/etl/raw_store.py`, `src/k_b/etl/raw_purge.py`,
  `src/k_b/commands/import_command.py`, `src/k_b/etl/sources/zotero.py`,
  `src/k_b/etl/source_contract.py`, `src/k_b/etl/sources/cisa_kev.py`,
  `docs/registre-traitements.md`, `docs/ADR/journal-decisions-projet.md`

## Le pourquoi

`conformite.md` demande, pour une donnée personnelle, une durée de conservation écrite au registre
et une purge « codée et testée, pas seulement décrite ». L'extrait Zotero porte des auteurs, les
surlignages et les commentaires de Sabine : chaque collecte en écrivait un de plus, sans durée ni
purge. C'était ce qui restait de cette règle pour E1.

La décision de Sabine du 19/10 range toutes les données de K-B en **trois couches**, chacune avec
sa règle de conservation :

| Couche | Ce qu'elle contient | Règle |
|---|---|---|
| *raw* | la réponse des sources, telle que reçue (`raw/`) | seule couche que la purge touche |
| *cleansed* | l'immuable : la base, et les `.md` normalisés selon les sources | jamais modifiée par une purge (réserve de Sabine : « les vieilles veilles, à voir ») |
| *curated* | fiches de lecture, fiches de veille, wiki, classements et tendances | jamais purgé automatiquement |

Le vocabulaire *cleansed* / *curated* vient du lac de données (la zone *curated* est la donnée
traitée) ; Sabine l'avait déjà posé le 12/10 pour le wiki. À l'oral, l'idée tient en une phrase :
**on peut jeter une réponse de source une fois qu'elle est entrée en base, pas ce que la base ou
un humain en a fait.**

Zotero et CISA KEV sont des **catalogues d'état** : chaque fichier contient tout le catalogue, et
la base garde déjà les dates entre deux imports (`revised_at`, `withdrawn_at`). Sabine : «
L'historique de versions n'a pas d'intérêt pour un catalogue d'état qui est indexé en bdd. » D'où
la règle : **on garde le dernier fichier importé, le nouveau remplace le précédent.** Pour CISA,
sans donnée personnelle, c'est de la sobriété (RGESN 1.6).

Les clips sont hors du code : leur brut ne sera supprimé qu'une fois la base sauvegardée, au
08/11 (règle écrite au registre, étape 8).

## Le comment

### 1. La purge part du registre de la base, jamais du dossier

`src/k_b/etl/raw_purge.py:28-37` :

```python
        imported_keys = sorted(
            key
            for key in (f"{RAW_DIR_NAME}/{path}" for path in imported_paths)
            # Directly in the folder: the pages of a collection are in a subfolder.
            if PurePosixPath(key).parent == PurePosixPath(folder_key)
        )
        # Collection names are times: the last in name order is the last collected.
        if not imported_keys or not store.has_file(imported_keys[-1]):
            continue
        deleted_count += sum(store.delete(key) for key in imported_keys[:-1])
```

`imported_paths` est le contenu de la table `raw_data`, le **registre** des fichiers importés,
écrit dans la même transaction que les items. La liste des candidats à la suppression ne vient
donc que de là : un fichier pas encore importé (collecté après le dernier import) ou illisible
(rejeté par le lecteur, donc jamais enregistré) n'y figure pas, et **ne peut pas** être supprimé.
Le garde-fou tient par construction, pas par un test de plus dans une boucle.

Trois détails :
- Les chemins de `raw_data` sont relatifs à `raw/` (`transform.py:133`) ; les clés du magasin le
  sont au dossier de données. D'où le préfixe `RAW_DIR_NAME`. Sans lui, la purge ne trouvait rien,
  sans erreur : c'est le premier constat bloquant de la relecture du plan.
- Les noms de collection sont des horodatages (`2026-10-05T093000Z`) : l'ordre alphabétique est
  l'ordre chronologique, `imported_keys[-1]` est le dernier importé.
- Si ce dernier a disparu du disque (supprimé à la main), on ne touche à rien : supprimer les
  autres ne laisserait aucun brut de l'état.

### 2. Quand : après le commit de `kb import`

`src/k_b/commands/import_command.py:91-96` relit le registre **après** l'import, puis purge :

```python
        deleted_count = delete_superseded_raw_files(
            RawStore(data_dir),
            read_imported_paths(database_path),
            LATEST_ONLY_FOLDER_KEYS,
        )
    except (sqlite3.Error, OSError, ValueError) as error:
```

« Importé avec succès » veut dire **enregistré dans `raw_data`**, même avec un rejet. Un import
qui échoue n'enregistre rien et ne purge rien. Une purge qui échoue laisse l'import validé, rend
le code `FAILED` (« import committed, raw purge failed ») et l'import suivant reprend : la purge
s'arrête à la première erreur. Le message ne donne que le type et la raison système
(`strerror`), jamais le nom d'un fichier.

La liste des deux dossiers, `LATEST_ONLY_FOLDER_KEYS` (`import_command.py:36`), vit dans la
commande : `etl/raw_purge.py` est une étape du pipeline, et un test d'architecture interdit à une
étape d'importer les sources (`test_no_module_of_the_pipeline_imports_the_sources_or_the_composition`).

### 3. `RawStore` : des clés, pas des chemins (règle 3 du POC)

`src/k_b/etl/raw_store.py:49-92`. La règle 3 de `.claude/rules/poc.md` demande qu'une fonction
nouvelle de `raw_store.py` prenne une clé POSIX relative au dossier de données, jamais un `Path` :
au 08/11, le brut passe dans Azure Blob Storage, qui adresse un objet par une clé. `RawStore` est
une `dataclass` gelée qui garde la racine (`data_dir`) ; ses méthodes `delete`, `has_file` et
`read_latest` ne prennent qu'une clé. Elle refuse une clé qui sortirait du dossier
(`raw_store.py:88-92`) :

```python
            not key_path.parts
            or key_path.is_absolute()
            or ".." in key_path.parts
            or "\\" in key
```

C'est de la défense en profondeur : les clés viennent de la base, que seul l'import écrit.
`PurePosixPath` ne réduit pas `..` (`foo/../bar` reste tel quel, documentation de `pathlib`), donc
le test sur `parts` voit chaque `..`.

### 4. Zotero compare le contenu, plus la date des fichiers

`src/k_b/etl/sources/zotero.py:223-225`, puis `:234-236` :

```python
        checked_documents = read_each_entry(enumerate(documents, 1), check_document)
        check_not_empty(checked_documents)
        check_not_all_invalid(checked_documents)
```
puis
```python
        if raw_extract == self.store.read_latest(RAW_FOLDER_KEY):
            logger.info("zotero: extract identical to the latest raw file, not written")
            return None
```

Avant, `was_modified_since` sautait l'extraction si ni `zotero.sqlite` ni son `-wal` n'avaient
changé de date. Deux défauts : Zotero ouvert touche son `-wal` sans changer la bibliothèque (un
extrait identique était réécrit), et un autre dossier Zotero aux fichiers plus anciens n'était
jamais extrait. Le critère d'origine de #139 demande une comparaison sur le **contenu** : la
bibliothèque est donc extraite à chaque collecte, et l'extrait n'est écrit que s'il diffère, octet
pour octet, du dernier fichier du dossier (pas du dernier importé : sinon une bibliothèque revenue
à un état ancien ne serait pas réécrite). La comparaison par octets est stable : la requête trie
tout par des clés uniques et `json.dumps` sérialise toujours de la même façon.

### 5. Deux refus à la collecte qui protègent la purge

Sans eux, un mauvais fichier deviendrait « le dernier importé » et ferait supprimer le dernier bon.
- `all_items_invalid` (règle 1 de `conventions.md`) : tous les documents Zotero refusés par
  `ZoteroDocument` (`check_document`, `zotero.py:414`). CISA le faisait déjà.
- `empty_catalog` (`source_contract.py:72-77`), pour Zotero et CISA : un catalogue sans entrée.

```python
    if not reading.entries and not reading.rejection_reasons:
        raise ValueError("empty_catalog: 0 entries")
```

L'import tenait déjà un catalogue vide pour suspect : il ne retire rien pour lui
(`load.py:398`, `:419`). Le refus à la collecte applique la même règle plus tôt.

### 6. Ce que la purge fait à la traçabilité d'E1

Un item inchangé n'est pas réécrit : `item.raw_data_id` reste sur le fichier qui l'a écrit en
dernier, souvent un catalogue que la purge supprime ensuite. `raw_data` garde alors le chemin d'un
fichier qui n'existe plus. À l'oral : **le registre dit ce qui a été importé et quand ; il ne
promet plus que le fichier existe.** La base garde l'état et ses dates ; le brut ne garde que le
dernier catalogue. Aucune API ne lit `raw_file_path` (vérifié par `grep` sur `data_api` et
`ai_api`).

## Choix faits et options écartées

| Choix | Retenu | Écarté, et pourquoi |
|---|---|---|
| Forme de la durée | le dernier fichier importé | une durée en années ou les N derniers : un catalogue complet rend chaque fichier plus ancien inutile à la base (décision de Sabine) |
| « Importé avec succès » | enregistré dans `raw_data`, même avec un rejet | « enregistré et sans rejet » : une entrée invalide pour toujours bloquerait la purge pour toujours |
| Source de la liste | le registre de la base | lister le dossier et comparer au registre : un oubli de comparaison supprimerait un brut non importé |
| Moment | fin de `kb import`, après le commit | à la collecte : elle n'ouvre pas la base, donc ne sait pas ce qui est importé |
| Forme de `raw_store` | `RawStore(data_dir)`, méthodes à clé | `delete(data_dir: Path, key)` enfreint la règle 3 ; une racine lue dans l'environnement serait un état caché |
| Place de la liste des dossiers | `commands/import_command.py` | dans `raw_purge.py` : un test d'architecture interdit à une étape d'importer les sources |
| Comparaison Zotero | au dernier fichier visible du dossier | au dernier importé (un retour en arrière ne serait pas écrit) ; dans `extract.py` pour toutes les sources (hors périmètre, « rien ici ») |
| Extrait tout invalide (P1) | refusé à la collecte, comme CISA | prendre pour référence le dernier fichier qui a écrit un item : faux, un catalogue identique n'« écrit » rien (constat 3 de la revue) |
| Constats 5 à 8 de `/code-review` | non corrigés | coût d'une extraction par jour (exigé par le critère) ; filtre « visible » doublé (le déplacer enfreindrait la règle 3) ; clé de dossier tenue par des tests de bout en bout ; registre relu après le commit (plus sûr qu'une liste en mémoire) |

Les tris de la relecture du plan et de `/code-review` sont de time-knight, par délégation de
Sabine du 2026-10-15.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_only_the_last_extract_and_catalog_imported_are_kept` (`tests/etl/test_raw_purge.py`) | après un vrai import, seul le dernier de chaque source reste |
| `test_a_raw_file_not_imported_yet_is_never_deleted`, `test_an_unreadable_raw_file_is_not_imported_so_never_deleted` | un fichier non enregistré, plus ancien ou plus récent, reste |
| `test_nothing_is_deleted_when_the_last_imported_file_is_missing` | le garde-fou du dernier absent |
| `test_the_raw_files_of_another_source_are_never_deleted` | arXiv n'est jamais touché |
| `test_the_log_gives_the_number_of_files_deleted_never_a_name` | le journal : `raw purge: 1 superseded files deleted`, aucun nom |
| `test_import_keeps_only_the_last_extract_and_catalog_imported` (`tests/test_cli.py`) | `kb import` imprime `superseded raw files deleted: 2` |
| `test_a_failed_import_deletes_no_raw_file`, `test_a_failed_purge_keeps_the_import_exits_1_and_the_next_import_purges`, `test_a_failed_purge_without_a_reason_names_its_type_only` | échec de l'import, puis de la purge : code 1, import gardé, reprise, aucun nom ni `None` au journal |
| `test_two_collections_of_an_unchanged_library_write_one_extract` (`tests/etl/sources/test_zotero.py`) | deux collectes, `-wal` touché, un seul extrait |
| `test_another_zotero_folder_with_files_older_than_the_last_collection_is_extracted`, `test_a_library_changed_back_is_compared_with_the_last_extract_only` | la comparaison porte sur le contenu, contre le dernier fichier |
| `test_a_library_without_any_document_writes_no_extract_and_fails`, `test_a_library_whose_documents_are_all_invalid_writes_no_extract_and_fails`, `test_a_catalog_without_any_row_fails_the_collection` | `empty_catalog` et `all_items_invalid` : rien d'écrit, sans valeur citée |
| `test_a_key_that_is_not_relative_to_the_data_directory_is_refused` (`tests/etl/test_raw_store.py`) | clé vide, absolue, avec `..` ou une barre oblique inverse refusée |
| `uv run pytest -q` → 1803 passed ; `ruff check`, `ruff format --check`, `mypy --strict` verts | les contrôles de la CI |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas lister le dossier `raw/…/zotero/` pour savoir quoi supprimer ?** Parce qu'un
   fichier présent n'est pas forcément importé. Le registre `raw_data` est la seule preuve d'import,
   écrite dans la même transaction que les items : ce qui n'y est pas ne peut pas être supprimé
   (`raw_purge.py:28-37`).
2. **Que se passe-t-il si la purge plante au milieu ?** L'import est déjà validé ; la commande sort
   en code 1 avec « import committed, raw purge failed » ; les fichiers non encore supprimés le
   seront au prochain import (`import_command.py:91-110`).
3. **Peut-on encore reconstruire la base depuis le brut ?** Oui, mais seulement l'état du dernier
   catalogue : les lignes retirées avant lui et les dates de révision passées n'existent plus qu'en
   base. C'est la conséquence voulue de « l'historique est abandonné » ; la sauvegarde de la base au
   08/11 couvre ce cas.
4. **Où est la sécurité de la suppression ?** Les clés viennent de la base, pas d'une source ; la
   purge ne garde que les fichiers directement dans les deux dossiers ; `find_path` refuse toute clé
   qui sortirait du dossier de données ; le journal ne donne qu'un nombre (`raw_store.py:84-96`).
5. **La traçabilité d'E1 est-elle cassée ?** Le lien item → `raw_data` existe toujours et dit quel
   fichier a apporté la donnée et quand ; c'est le fichier lui-même qui peut avoir disparu. C'est
   écrit au registre et dans l'ADR.

## Zones non vérifiées

- Le comportement de `Path.unlink` et `Path.is_file` sur un lien symbolique (le lien supprimé, pas
  sa cible ; `is_file` suit le lien) vient de la revue de sécurité ; il n'a pas été relu à la source
  ni testé.
- La concurrence : deux collectes Zotero en parallèle peuvent faire lire à `read_latest` un fichier
  que la purge vient d'effacer (`FileNotFoundError`, la source échoue pour ce tour) ; deux imports en
  même temps sont déjà refusés par la contrainte `UNIQUE` de `raw_data`. Raisonné par la relecture du
  plan, non testé.
- Le coût d'une extraction Zotero complète à chaque collecte (copie, contrôle d'intégrité, requête)
  n'est pas mesuré sur une vraie bibliothèque.
- Aucune exécution sur le dossier de données réel de Sabine : tout est prouvé sur des dossiers
  d'essai.

## Ce qui reste

- **La première purge efface d'un coup** tous les extraits Zotero et catalogues CISA passés, sauf le
  dernier importé, au premier `kb import` après la fusion. La commande de copie préalable est dans la
  PR.
- Le brut des clips : supprimé une fois la base sauvegardée, au 08/11 (registre, étape 8).
- La purge par durée de la veille (#83), au 08/11.
- Les limites écrites, sans code : une bibliothèque vraiment vidée n'est plus collectée ; un extrait
  dont tous les documents passent la collecte mais sont refusés à l'import fait quand même supprimer
  le précédent ; un dossier renommé à la main (`cisa_kev_<suffixe>`) n'est pas purgé ; un extrait
  illisible reste, sans durée.
- La conservation des « vieilles veilles » dans le *cleansed* : question ouverte (journal ADR).

Hors de cette note : les commits et fichiers listés au lancement de la note avant 432cfea
appartiennent à des PR déjà fusionnées sur `main` (#250 à #257) ; cette branche n'a que six commits
(432cfea à fb1b30e), tous couverts ci-dessus. `core/config.py` (une ligne de commentaire) et
`tests/architecture/module_imports.py` (le module de purge déclaré dans le pipeline) sont couverts
par les sections 2 et 3.

## Sources

| Source | URL | Consultée le |
|---|---|---|
| Documentation de `pathlib`, CPython 3.13.9 (`PurePath('foo/../bar')` garde `..`), par Context7 | https://github.com/python/cpython/blob/v3.13.9/Doc/library/pathlib.rst | 2026-10-19 |
| CNIL, « Intérêt légitime : collecte par moissonnage » (référentiel de `conformite.md`) | https://www.cnil.fr/fr/focus-interet-legitime-collecte-par-moissonnage | non relue aujourd'hui (vérifiée le 2026-10-04, `conformite.md`) |
| RGESN v2, critère 1.6 (référentiel de `conformite.md`) | https://ecoresponsable.numerique.gouv.fr/publications/referentiel-general-ecoconception/ | non relu aujourd'hui (vérifié le 2026-10-04, `conformite.md`) |
