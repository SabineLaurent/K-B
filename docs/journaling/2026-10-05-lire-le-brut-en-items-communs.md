# Lire le brut en items communs

- **Date** : 2026-10-05
- **Branche** : `feat/raw-items`
- **Issue** : #79, sous-issue de l'épic #20 « Fusion et base »
- **Fichiers principaux** : `src/k_b/items.py`, `src/k_b/raw_items.py`, `src/k_b/github_releases.py`
- **Dans la même série** : [lire CISA et les releases avant l'écriture](2026-10-05-lire-cisa-et-releases-avant-ecriture.md), qui a mis en place les lecteurs repris ici.

## 1. Le pourquoi

`kb collect` écrit chaque réponse de source telle quelle dans
`raw/automation/<source>/<horodatage>.<ext>`. Ces fichiers ont cinq formats différents : un flux
Atom pour arXiv, un CSV pour CISA, trois formes de JSON pour GitHub. La fusion (#80), puis la
base (#82), ont besoin d'un seul format.

Cette PR fait l'étape 2 de `docs/specs-collecte.md`, « Lecture ». Elle parcourt tout le brut,
lit chaque fichier avec le lecteur de sa source, et convertit chaque entrée en un `Item` commun,
validé par Pydantic. Elle ne retire aucun doublon, ce qui est le rôle de #80, et n'écrit rien en
base, ce qui est le rôle de #82. Elle rend deux listes, les items et les rejets, que #82 écrira
au journal.

## 2. Le comment

### 2.1 L'item commun : un modèle Pydantic fermé

```python
class Item(BaseModel):
    # strict: a date given as text is refused, not parsed.
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
```
`src/k_b/items.py:30-32`

Les trois options de configuration ont chacune un rôle :

- `frozen=True` : un item ne se modifie pas après sa création. Le test
  `test_an_item_cannot_be_changed` le vérifie.
- `extra="forbid"` : un champ inconnu est refusé. C'est le « type fermé » que demande
  `.claude/rules/code.md`.
- `strict=True` : Pydantic ne convertit rien. Une date passée en texte
  (`"2026-10-01T18:00:22Z"`) est refusée au lieu d'être interprétée, parce que les conversions
  vers `Item` doivent toujours lui donner un `datetime`.

Les dates sont typées `AwareDatetime` (`items.py:39-45`). Pydantic refuse alors une date sans
fuseau horaire, ce qui applique la règle « toutes les dates sont en UTC, avec fuseau » de
`specs-collecte.md`.

### 2.2 Des contraintes sur le texte, pas des types URL

```python
HttpsUrl = Annotated[str, StringConstraints(pattern=r"^https://\S+$")]
CveId = Annotated[str, StringConstraints(pattern=r"^CVE-\d{4}-\d{4,}$")]
```
`src/k_b/items.py:25-26`

`url` reste un `str`, auquel on impose de commencer par `https://` et de ne contenir aucun
espace. Le commentaire `items.py:23-24` dit pourquoi on n'a pas pris le type `HttpUrl` de
Pydantic : il réécrit l'URL, par exemple en ajoutant un `/` final, alors que #80 retirera les
doublons en comparant les URL comme du texte. `cve` et `repository_name` ont aussi un motif
fermé. Ils servent aux sous-types `vulnerability` et `repository` de la base
(`docs/stockage.md`).

### 2.3 Les conversions : une fonction pure par famille de source

```python
def convert_vulnerability(
    vulnerability: Vulnerability, collected_at: datetime, raw_file_path: str
) -> Item:
    ...
        url=NVD_PAGE_URL + vulnerability.cve_id,
        # dateAdded is a day: stored at midnight UTC, a writing convention (docs/stockage.md).
        published_at=datetime.combine(vulnerability.date_added, time(), tzinfo=UTC),
```
`src/k_b/items.py:68-80`

Chaque fonction `convert_*` prend ce que rend un lecteur existant (une `dataclass`) et le range
dans les champs de l'item, comme le dit le tableau « Ce que chaque source met dans l'item » de
`docs/stockage.md`. Ces fonctions n'ouvrent aucun fichier et ne font aucun appel réseau. C'est la
séparation des responsabilités de `code.md`.

Pour une release GitHub, l'identifiant est l'`id` numérique que renvoie l'API. Le lecteur
`read_releases` ne le lisait pas : il le lit maintenant et le valide (`github_releases.py:37-40`).
Le contrôle `isinstance(release_id, bool)` est là parce qu'en Python, `True` est un `int`.

### 2.4 Le parcours du brut et ses rejets

```python
        try:
            collected_at = datetime.strptime(path.stem, COLLECTION_NAME_FORMAT).replace(tzinfo=UTC)
            entries = reader.read_entries(path.read_bytes())
        except (ValueError, csv.Error, OSError) as error:
            rejections.append(reject(raw_file_path, f"{type(error).__name__}: {error}"))
            continue
        for position, entry in enumerate(entries):
            try:
                items.append(reader.convert(entry, collected_at, raw_file_path))
            except ValidationError as error:
```
`src/k_b/raw_items.py:84-93`

Il y a deux niveaux de rejet :

1. **Le fichier entier** : son nom n'est pas un horodatage, il est illisible, ou son lecteur le
   refuse (CSV sans les colonnes attendues, JSON qui n'est pas une liste). On passe au fichier
   suivant.
2. **Une entrée** : le lecteur l'a acceptée, mais `Item` la refuse (titre vide, par exemple). On
   rejette cette entrée seule, avec sa position, et on lit les autres entrées du fichier.

Le second niveau vient du constat 1 de la revue de code. Avant la correction, une seule ligne
CISA au nom vide faisait perdre tout le catalogue, environ 1 500 vulnérabilités, et cela à
chaque collecte, puisque la ligne reste dans le catalogue.

La date de collecte vient du **nom** du fichier (`2026-10-05T093000Z`), écrit par `collect.py`
avec le même format. Le chemin est gardé **relatif** au dossier `raw` (`raw_items.py:83`), pour
que la base puisse se reconstruire depuis une copie du brut placée ailleurs.

### 2.5 Les lecteurs viennent de la liste des sources

```python
            case GithubReleasesSource(repository=repository):
                readers[source.name] = SourceReader(
                    lambda raw, repository=repository: read_releases(raw, repository),
                    convert_release,
                )
```
`src/k_b/raw_items.py:120-124`

`list_readers_by_source` parcourt `SOURCES`, la liste des sources de `collect.py`, et associe à
chaque nom de dossier un `SourceReader` : une fonction qui lit les entrées et une fonction qui les
convertit. Le nom du dossier n'est donc écrit qu'à un seul endroit, dans la source elle-même.
`case GithubReleasesSource(repository=repository)` est un filtrage par motif sur une classe : il
vérifie le type et lit l'attribut `repository` en même temps.

Le `repository=repository` dans la `lambda` fige la valeur au moment de la création. Sans lui,
toutes les `lambda` créées dans la boucle verraient le dernier dépôt de la boucle : c'est la
liaison tardive (*late binding*) des fermetures en Python.

## 3. Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Format de l'item | **Modèle Pydantic** : décision de Sabine du 05/10. FastAPI l'utilisera avec #21, et `specs-collecte.md` le demandait déjà. | `dataclass` validée à la main, comme les lecteurs : plus de code de validation, et un second format le jour de l'API. |
| Lecteurs existants | **Restent en `dataclass`** dans cette PR (décision de Sabine). Leur migration est #85. | Les migrer ici : environ 2,5 h de plus, hors du budget d'ici le 07/10. |
| Type de `url` | **`str` contraint à `https://`** : l'URL est gardée telle quelle. | `HttpUrl` : il réécrit l'URL et fausserait la comparaison des doublons dans #80. |
| Identifiant d'une release | **`id` de l'API** (option a, choix de Sabine) : c'est ce que dit `docs/stockage.md`. | `owner/repo@tag` : lisible, mais il aurait fallu corriger la doc. |
| CISA à la lecture | **Catalogue entier** (`last_collected_at=None`) : les doublons entre collectes sont retirés par #80. | Filtrer par date : pour cela, la lecture aurait besoin de l'état de collecte. |
| Niveau de rejet | **Fichier, puis entrée** (après revue). | Fichier seul (première version) : une entrée invalide coûtait tout le fichier. |
| Fichiers cachés | **Ignorés en silence** (après revue) : `.DS_Store` n'est pas un brut. | Les rejeter : le rapport des rejets n'aurait jamais été vide sous macOS. |
| Où trouver les lecteurs | **`SOURCES`**, une seule liste des sources. | Reconstruire les noms de dossiers dans `raw_items.py` : la même connaissance à deux endroits. |
| Liste des codes de source | **`Literal` dans `items.py`**, tenu égal au `seed_sources.sql` par un test (`test_items.py:43`). | Lire le fichier SQL au chargement : une entrée/sortie dans le modèle. |

## 4. Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_every_source_with_a_reader_gives_its_items` | Les 5 familles sont lues, avec le bon nombre d'items par fichier, et la date de collecte tirée du nom. |
| `test_an_unreadable_file_is_rejected_and_the_others_are_read` | Un CSV qui n'est pas un catalogue est rejeté et journalisé avec son chemin, et l'arXiv voisin est lu. |
| `test_an_entry_refused_as_an_item_is_rejected_and_the_others_of_its_file_are_read` | Une ligne CISA au nom vide est rejetée seule (`entry 2`), et les 3 autres sont lues. |
| `test_hidden_files_are_ignored` | Un `.DS_Store` ne produit ni item ni rejet. |
| `test_a_file_name_that_is_not_a_collection_time_is_rejected` | Un nom de fichier qui n'est pas un horodatage est rejeté. |
| `test_a_source_without_reader_and_page_folders_are_skipped_and_logged` | TLDR, qui n'a pas encore de lecteur (#57), est sauté avec une ligne de journal. |
| `test_files_are_read_in_collection_order` | Les items sortent dans l'ordre des collectes, ce que #80 utilisera pour appliquer les révisions. |
| `test_an_invalid_item_is_refused` (11 cas) | Le modèle refuse une source inconnue, un texte vide, du `http://`, une date sans fuseau, une date en texte, une CVE ou un dépôt mal formés, un champ inconnu. |
| `test_the_source_codes_are_those_of_the_database` | `SourceCode` et `seed_sources.sql` contiennent les mêmes 7 sources. |
| `test_a_release_is_identified_by_its_release_id`, `test_an_invalid_release_is_refused_with_its_position` | L'`id` d'une release est lu, et un `id` absent, en texte ou booléen est refusé. |
| `uv run pytest` | 211 tests passent. |

## 5. Ce que tu dois pouvoir défendre

1. **Pourquoi deux niveaux de rejet ?** Un fichier illisible ne donne aucune entrée à lire : on
   ne peut que le rejeter en bloc. Une entrée refusée par `Item` n'empêche pas de lire les
   autres : la rejeter seule évite de perdre tout un catalogue pour une ligne
   (`raw_items.py:84-96`).
2. **Où est la sécurité ?** Le brut est une donnée non fiable. Il est validé une fois, à la
   frontière, par un type fermé : `strict`, `extra="forbid"`, motifs sur `url`, `cve` et
   `repository_name`. Seuls les noms de fichiers créés par `collect.py` servent à lire le
   disque, jamais le contenu téléchargé. La revue de sécurité n'a rien trouvé.
3. **Pourquoi `strict=True`, si les conversions donnent déjà des `datetime` ?** Pour qu'une
   erreur de conversion se voie : un texte qui passerait pour une date serait interprété sans
   bruit. En mode strict, il est refusé (`test_items.py:70`).
4. **Que se passe-t-il si on retire un dépôt de `TRACKED_REPOSITORIES` ?** Son brut passé n'a
   plus de lecteur : il est sauté, avec une ligne INFO, et ses releases disparaissent si on
   reconstruit la base. C'est une limite connue, portée par #87.
5. **Pourquoi garder le chemin relatif du brut ?** La base doit pouvoir se reconstruire depuis le
   brut. Un chemin absolu la lierait à une machine et à un dossier précis.

## 6. Zones non vérifiées

- La **position** donnée dans un rejet (`entry 2`) est l'indice dans la liste rendue par le
  lecteur, en partant de 0. Pour CISA, ce n'est pas le numéro de ligne du CSV. Je n'ai pas
  vérifié que ce repère suffira pour retrouver la ligne en pratique.
- Les rejets d'entrées arXiv faits **par le lecteur lui-même** (`read_papers`, entrée mal formée)
  sont journalisés par ce lecteur, mais ne sont pas dans la liste `rejections`. Le journal de
  #82 ne les contiendra donc pas.
- Le **texte d'une `ValidationError`** est sur plusieurs lignes : il s'écrira ainsi dans le
  journal. Je n'ai pas vérifié que le format du journal de #82 s'en accommode.
- Aucun **brut réel** n'a été lu : seulement les fixtures du dépôt.

## 7. Ce qui reste

- La fusion (doublons, `utm_*`, révisions arXiv, trace des règles) : #80.
- La création de la base et le test du schéma : #81 et #67. L'import et le journal des rejets :
  #82.
- TLDR entre dans la lecture avec #57.
- La lecture du brut des sources qui ne sont plus suivies, et des anciens classements : #87.
- La migration des lecteurs vers Pydantic : #85.
- L'écart d'une entrée invalide **à la collecte**, pour GitHub et CISA : #61 et #77.
