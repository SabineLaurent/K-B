# Collecter les clips du coffre Obsidian

- **Date** : 2026-10-17
- **Branche** : `feat/collect-clips`
- **Issue** : #14 (révision du 15/10, accord du critère du 17/10)
- **Fichiers principaux** : `src/k_b/etl/sources/clipping.py`, `src/k_b/database/writers/clip_writer.py`,
  `src/k_b/database/schema.sql` (table `clip`), `src/k_b/database/reading.py`, `src/k_b/items.py`,
  `src/k_b/cli.py`, `docs/specs-collecte.md`
- **Notes liées** : [écarter une entrée invalide d'une source](2026-10-16-ecarter-une-entree-invalide-d-une-source.md),
  [journaliser un rejet sans la valeur reçue](2026-10-16-journaliser-un-rejet-sans-la-valeur-recue.md)

## Le pourquoi

Les clips sont les pages que Sabine garde à la main avec l'extension Web Clipper, dans un coffre
Obsidian. Ils sont une entrée de la **bibliothèque** (`acquisition_mode = 'library'`), jamais de la
veille : aucune fiche de veille ne les lit. Avant cette PR, aucun code ne les collectait, et la spec
renvoyait leur agrégation à « leur issue d'import ».

Le coffre reste à Sabine : K-B le lit, n'y écrit jamais, et copie chaque clip nouveau ou changé dans
le brut, `raw/selected_library/clipping/` (ADR du 09/10). L'import lit ces copies, en fait des items
de sorte `clip`, et l'API de données les sert par `/items`. La compilation des clips en wiki viendra
après le 29/10 (#148 à #155) : elle lira le texte gardé en base.

## Le comment

### 1. Une source qui copie, sans rien interpréter

`ClippingSource.fetch` suit le contrat commun des sources (`etl/source_contract.py`) : elle rend
les pages à écrire, par nom, et `etl/extract.py` les écrit. Elle choisit les clips changés, avec une
marge dans les deux sens :

```python
            or clip_file.changed_at_ns > to_ns(last_collected_at - CLIP_CHANGE_MARGIN)
        ]
        settled_before_ns = to_ns(current_time() - CLIP_CHANGE_MARGIN)
        settled = [
            clip_file
            for clip_file in changed
            if clip_file.changed_at_ns <= settled_before_ns
```
(`src/k_b/etl/sources/clipping.py:95-101`)

- Un clip changé jusqu'à 60 s **avant la dernière collecte** est recopié : l'horloge d'un système de
  fichiers peut être plus grossière ou en retard sur celle de `kb` (hypothèse non mesurée). Sans
  marge, un clip écrit juste après le début d'une collecte serait daté d'avant elle et jamais copié.
- Un clip changé moins de 60 s **avant la collecte en cours** est laissé à la suivante : il peut être
  encore en cours d'écriture, et un clip copié tronqué le resterait (point 4).
- La date retenue est la plus récente de la date de modification et de la date de changement
  (`ctime`) : une copie faite par `cp -p` ou le Finder garde sa date de modification, mais pas sa
  date de changement.

Le nom de chaque page est un hachage du nom de fichier :

```python
    return hashlib.sha256(os.fsencode(path.name)).hexdigest()[:PAGE_NAME_LENGTH]
```
(`clipping.py:179`)

Le nom d'un fichier de clip est son titre. Haché, il n'entre ni dans le chemin du brut ni dans le
journal d'import, et il ne contient jamais un caractère que `SAFE_PAGE_NAME` (`etl/extract.py`)
refuserait. Le même clip garde le même nom d'une collecte à l'autre.

### 2. Lire un fichier du coffre sans faire confiance au coffre

```python
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as clip_file:
        content = clip_file.read(CLIP_MAX_BYTES + 1)
        size = max(len(content), os.fstat(clip_file.fileno()).st_size)
```
(`clipping.py:186-189`)

- La liste (`list_clip_files`, `clipping.py:139`) ne garde que les fichiers réguliers (`lstat`), et
  `O_NOFOLLOW` refuse un fichier remplacé par un lien symbolique entre la liste et la lecture : un
  lien pourrait pointer hors du coffre.
- On lit au plus un octet de plus que le maximum : cela suffit pour savoir que le clip est trop gros,
  sans charger un fichier énorme. Un clip trop gros fait échouer la source (`clip_too_large`), avec
  son nom tronqué et échappé par `quote_value`.

### 3. Lire le frontmatter sans deviner les types

```python
        properties = yaml.load(frontmatter, Loader=yaml.BaseLoader)  # noqa: S506
    except yaml.YAMLError as error:
        raise ValueError(describe_yaml_error(error)) from None
```
(`clipping.py:218-220`)

- `BaseLoader` ne rend que des textes, des listes et des dictionnaires. Une étiquette
  `!!python/object/apply` n'est pas appliquée : sa valeur est lue comme du texte, et un test le
  montre. ruff signale à tort un chargeur dangereux (S506) : le `noqa` porte sa raison en
  commentaire.
- L'erreur de PyYAML cite le texte autour du problème. On n'en garde que la ligne et la colonne
  (`describe_yaml_error`), et `from None` coupe la chaîne d'exceptions : la trace de l'import ne
  montre pas l'erreur d'origine (règle 5 de `poc.md`).
- Le frontmatter s'arrête à la **première** ligne `---` après la première (`split_frontmatter`,
  `clipping.py:226`). Un `---` plus bas est un filet du texte, gardé tel quel. La fixture
  `page_with_a_rule_in_its_text.md` vient d'un vrai clip qui en a un.

Les dates sont lues par K-B, pas par le lecteur YAML :

```python
def check_day_form(value: object) -> object:
    """Let pydantic read the day only in the form of Web Clipper."""
    if not isinstance(value, str) or not DAY.fullmatch(value):
        raise ValueError("not a day of Web Clipper (YYYY-MM-DD)")
```
(`clipping.py:265-268`)

Pydantic, seul, lirait `1696464000` comme une date Unix, ou `2026-10-05T00:00:00Z` comme un jour.
Le motif (`DAY`, `clipping.py:56`) n'accepte que `AAAA-MM-JJ`, avec une année d'au moins 1000 :
`strftime("%Y")` écrirait une année sur 3 chiffres sous Linux. Le jour est ensuite écrit à minuit
UTC par `at_midnight_utc` (`items.py:118`), la fonction désormais commune à CISA KEV, TLDR et aux
clips.

### 4. Une URL, un clip : la première version gardée

```sql
INSERT INTO item (kind, raw_data_id)
SELECT 'clip', :raw_data_id WHERE NOT EXISTS (SELECT 1 FROM clip WHERE url = :url)
```
(`src/k_b/database/writers/clip_writer.py:14-15`)

C'est la règle du « flux de nouveautés » des releases et des articles TLDR : l'item n'est créé que
si aucun clip n'a déjà cette URL ; sinon, l'écrivain rend un écart `already_seen`, écrit au journal
d'import. La clé est l'URL sans ses paramètres `utm_*` (`remove_tracking_parameters`, `clipping.py:298`).
Sabine ne retouche pas ses clips : un clip recopié n'est jamais remplacé.

### 5. Une table en SQL portable

```sql
    url          TEXT NOT NULL UNIQUE
        CHECK (substr(url, 1, 8) = 'https://' OR substr(url, 1, 7) = 'http://')
```
(`src/k_b/database/schema.sql:298-299`)

La règle 1 de `poc.md` interdit tout nouveau `GLOB` ou `strftime`, parce que la base passe à
PostgreSQL au 08/11. Les autres tables testent l'URL par `GLOB 'https://*'` et la forme d'une date
par `strftime` ; `clip` le fait par `substr` et `length`, qui existent dans les deux bases. Le
`CHECK` des dates (`schema.sql:309`) ne tient que la longueur et la place du `T` et du `Z` : il
refuse l'année sur 3 chiffres, et la forme complète est tenue par l'item.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| PyYAML avec `BaseLoader`, et `types-pyyaml` en dev (décision de Sabine) | lit le YAML comme Obsidian, ne devine rien ; sans les types, `mypy --strict` échoue | `yaml.safe_load` (devine `yes` en booléen, un jour en date) ; une lecture faite à la main (~1 h, YAML lu autrement qu'Obsidian) ; une exception mypy |
| Flux de nouveautés par URL, `already_seen` (décision de Sabine) | ses clips restent tels quels | remplacer la version en base (`revised_at`), sans objet ; catalogue d'état comme Zotero (recopier tout le coffre) ; le nom `unchanged` (il veut dire « catalogue plus récent, contenu identique ») |
| En base : titre, URL, `created`, `published`, texte (décision de Sabine) | la spec et la minimisation | garder `author` (donnée personnelle sans usage), `description`, `tags` |
| Texte dans `clip.body` | le plus court chemin | une table CONTENU (question encore ouverte, hors de #14) |
| Nom de page haché | stable, sans titre dans le brut ni le journal | le nom de fichier (refusé par `SAFE_PAGE_NAME`) ; un numéro (instable) |
| `clip_too_large` fait échouer la source (exception à la règle 1 de `conventions.md`, tranchée par time-knight) | un clip est une page, et un plafond dépassé se voit | sauter le clip avec un message (aucune trace au journal d'import, et la date avance : il n'est plus revu) |
| Marge de 60 s dans les deux sens (`CLIP_CHANGE_MARGIN`, `core/config.py:36`) | une perte silencieuse est pire que quelques octets recopiés puis écartés | comparer à la seule dernière collecte ; écrire seulement la limite |
| Frontmatter illisible = page illisible (règle 1 de `conventions.md`, décision du 12/10) | la correction du lecteur la reprend sans reconstruire la base | un rejet d'entrée, qui serait inscrit au registre une fois pour toutes |
| Clip disparu entre la liste et la lecture : sauté et compté | un renommage dans Obsidian ne doit pas faire échouer tous les clips | laisser lever `FileNotFoundError` |
| `KB_VAULT_DIR` sans valeur par défaut (exception à la règle 2 de `poc.md`, comme `KB_ZOTERO_DIR`) | un dossier de la machine de Sabine n'a pas de valeur locale qui ait un sens | un défaut nommé dans `core/config.py` |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_each_clip_is_copied_as_it_is_under_a_name_made_from_its_file_name` | copie octet pour octet, nom haché |
| `test_only_the_clips_modified_since_the_last_collection_are_copied`, `test_a_clip_copied_into_the_vault_with_an_old_modification_date_is_collected` | incrémental, `ctime` compris |
| `test_a_clip_changed_within_the_margin_before_the_last_collection_is_copied_again`, `test_a_clip_changed_less_than_the_margin_ago_is_left_to_the_next_collection`, `test_a_clip_left_to_the_next_collection_is_copied_by_it` | la marge, dans les deux sens |
| `test_hidden_files_other_files_folders_and_links_are_not_copied`, `test_a_file_replaced_by_a_link_after_it_was_listed_is_not_followed` | rien hors des fichiers réguliers du dossier |
| `test_a_clip_larger_than_the_maximum_fails_the_source_naming_it`, `test_a_clip_of_the_maximum_size_is_copied` | le plafond, à l'octet près |
| `test_clips_all_unreadable_fail_the_source_as_all_items_invalid`, `test_clips_all_refused_as_items_fail_the_source_as_all_items_invalid` | règle 1 de `conventions.md` à la collecte, `RecursionError` comprise |
| `test_a_python_tag_builds_no_object_and_its_value_is_refused_as_a_title` | `BaseLoader` n'applique pas d'étiquette |
| `test_a_clip_that_cannot_be_read_is_unreadable_without_its_content` | aucun texte du clip dans le message ni dans la trace |
| `test_a_date_of_another_form_is_refused` (18 cas) | heure, `Z`, nombre, forme compacte, semaine ISO, année < 1000 refusés |
| `test_a_clip_of_a_url_already_seen_keeps_its_first_version`, `test_two_urls_that_differ_by_their_utm_parameters_are_one_clip`, `test_two_urls_are_two_clips_even_for_the_same_article` | la clé et la règle `already_seen` |
| `test_a_value_each_check_forbids_is_refused` (8 cas `clip`), `test_a_url_is_one_clip`, `test_a_clip_pointing_to_an_item_of_another_kind_is_refused` | la table refuse ce que l'item refuse |
| `test_each_kind_has_its_detail[clip]`, `test_the_versioned_openapi_is_the_one_the_app_produces` | `/items` sert les clips, OpenAPI 0.4.0 |
| `test_a_clip_is_of_the_library_and_never_read_for_the_watch` | aucun clip n'entre dans les fiches de veille |
| Mutations sur une copie du dépôt : 23 sur 23 tuées (relecture du diff contre le critère) ; 6 trous trouvés puis couverts | les tests attrapent un code cassé exprès |
| `uv run pytest` 1706 passed ; `ruff check`, `ruff format --check`, `mypy --strict` verts | les contrôles du dépôt |

## Ce que tu dois pouvoir défendre

1. **Pourquoi pas `yaml.safe_load`, le chargeur « sûr » ?** Il est sûr contre l'exécution de code,
   mais il devine les types : `title: yes` deviendrait un booléen, `published: 2026-10-05` une date.
   `BaseLoader` rend du texte, et K-B décide seul de la forme d'un jour (`clipping.py:56`,
   `clipping.py:265`).
2. **Que se passe-t-il si Sabine modifie un clip déjà collecté ?** Il est recopié dans le brut (sa
   date change), puis écarté `already_seen` à l'import : la base garde la première version. C'est sa
   décision (ses clips ne changent pas), écrite comme limite dans la spec.
3. **Un clip de 2 Mo bloque-t-il la collecte ?** Oui, celle des clips, à chaque fois, jusqu'à ce que
   le fichier soit réduit ou retiré : `clip_too_large` le nomme. C'est une exception assumée à la
   règle 1 de `conventions.md` ; les autres sources ne sont pas touchées.
4. **Où est la sécurité, puisque le texte vient du web ?** Le texte est une donnée : il n'est jamais
   journalisé, jamais envoyé au modèle (`WATCH_KINDS` exclut `clip`), et servi seulement au détail,
   derrière la clé d'API. Le YAML ne construit aucun objet ; les chemins viennent d'un hachage ;
   un lien symbolique n'est jamais suivi.
5. **Pourquoi une table propre aux clips, et pas une colonne sur `item` ?** L'item est minimal
   (option D) : ce qu'il dit est dans son sous-type. `clip` a sa clé naturelle (`url`, unique) et
   ses colonnes, comme `release` ou `zotero_entry`.

## Zones non vérifiées

- **La marge de 60 s** repose sur une hypothèse non mesurée : l'horloge du système de fichiers
  serait plus grossière que celle de `kb` ou en retard sur elle (tick de Linux, coffre monté depuis
  l'hôte au #200). La valeur de 60 s est un choix, pas une mesure.
- **Le format de Web Clipper** n'a été relevé que sur 5 clips du 17/10, avec le gabarit par
  défaut. Un autre réglage (type `datetime`) ferait rejeter les dates ; c'est voulu, mais non
  observé sur un vrai coffre (Web Clipper n'écrit pas encore dans le coffre de K-B).
- **L'écriture d'un clip par Obsidian** : on suppose qu'un clip en cours d'écriture a une date de
  changement récente. Une écriture plus longue que 60 s n'est pas couverte.
- **PostgreSQL** : la portabilité du SQL de `clip` (`substr`, `length`) n'est vérifiée que sous
  SQLite ; la limite d'un index B-tree sur `url` est lue dans la documentation, pas testée.

## Ce qui reste

- La durée de conservation des copies de clips, et leur purge : avec les extraits Zotero, dans #139.
- La compilation des clips en wiki (#148 à #155), et le test d'un clip piégé (#206).
- La mise à jour du modèle Merise avec la table `clip` (#211, confiée à Sabine).
- Le montage du coffre en lecture seule dans le conteneur (#200).
- Factoriser l'écriture « flux de nouveautés », désormais en quatre copies (signalé dans la PR).
