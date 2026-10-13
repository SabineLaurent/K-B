# Mettre les dépôts qui montent en base : la table `trend`

- **Date** : 2026-10-13
- **Branche** : `feat/trend-table`
- **Issue** : #142
- **Fichiers principaux** : `src/k_b/database/schema.sql`, `src/k_b/items.py`,
  `src/k_b/sources/gh_archive.py`, `src/k_b/import_items.py`, `src/k_b/cli.py`,
  `tests/test_schema.py`, `tests/test_import_items.py`, `tests/sources/test_gh_archive.py`,
  `docs/specs-collecte.md`, `docs/stockage.md`
- **Dans la même série** : [repérer les dépôts qui montent avec GH
  Archive](2026-10-11-reperer-les-depots-qui-montent-gh-archive.md) (#16), qui s'arrêtait au
  fichier brut ; [laisser la base dédoublonner les
  items](2026-10-12-laisser-la-base-dedoublonner-les-items.md) (#105), dont cette PR applique une
  variante ; [importer seulement les bruts
  nouveaux](2026-10-12-importer-seulement-les-bruts-nouveaux.md) (#106), dont elle reprend le
  registre.

## Le pourquoi

GH Archive est la seule source « big data » de K-B : une requête BigQuery compte, pour chaque
fenêtre de 3 jours, les étoiles et les forks que chaque dépôt GitHub a gagnés, et garde les 30
premiers par étoiles et les 30 premiers par forks, réunis (60 dépôts au plus). Depuis #16, ce
résultat était écrit dans un fichier brut, et s'arrêtait là : il n'entrait pas dans la base. Or le
jeu de données stocké doit agréger toutes les sources.

Cette PR fait entrer ce classement dans la base, dans une table `trend`. Une ligne de classement
n'est pas un item (décision du 2026-10-08) : ce n'est pas une chose publiée qu'on lit, c'est une
mesure sur un dépôt pendant une fenêtre. Elle a donc sa propre table, rattachée directement à son
fichier brut, et son propre chemin de lecture.

Deux tables du modèle précédent, `repository` et `star_gain`, gardaient la même idée sous une
autre forme, sans que rien ne les écrive : elles sont retirées.

## Le comment

### 1. La table, et ce qu'elle refuse

`src/k_b/database/schema.sql:91`

```sql
CREATE TABLE trend (
    id              INTEGER PRIMARY KEY,
    raw_data_id     INTEGER NOT NULL REFERENCES raw_data (id),
    window_end      TEXT NOT NULL
        CHECK (window_end IS strftime('%Y-%m-%dT00:00:00Z', window_end)),
    repository_id   INTEGER NOT NULL CHECK (repository_id > 0),
    ...
    UNIQUE (window_end, repository_id)
) STRICT;
```

- Une ligne par fenêtre et par dépôt : c'est la contrainte `UNIQUE (window_end, repository_id)`.
- `raw_data_id` rattache chaque ligne au fichier brut qui l'a produite : toute donnée de la base
  remonte à un fichier de `raw/`.
- `window_end` est le dernier jour de la fenêtre. SQLite n'a pas de type date : c'est un texte,
  écrit à minuit UTC. Le `CHECK` recalcule ce texte avec `strftime` en forçant l'heure à
  `00:00:00` : si le résultat diffère de ce qu'on a écrit (une heure non nulle, un 30 février),
  la ligne est refusée. Sans cela, `2026-10-10T00:00:00Z` et `2026-10-10T09:30:00Z` seraient deux
  clés pour le même jour.
- `repository_id` est l'identifiant numérique du dépôt chez GitHub (`repo.id`) ; il identifie le
  dépôt même s'il est renommé. `repository_name` est le dernier nom vu dans la fenêtre.

### 2. `TrendRow` : valider avant la base

`src/k_b/items.py:292`

```python
class TrendRow(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    window_end: date
    repository_id: Annotated[int, Field(gt=0, le=MAX_INT64)]
    repository_name: Annotated[
        RepositoryName,
        Field(max_length=TREND_REPOSITORY_NAME_MAX_LENGTH),
        AfterValidator(check_text_has_no_control_character),
    ]
    stars_gained: Annotated[int, Field(ge=0, le=MAX_INT64)]
    forks_gained: Annotated[int, Field(ge=0, le=MAX_INT64)]
```

Le fichier brut est une entrée externe : `TrendRow` la valide à la frontière. La règle du projet
(règle 4 des conventions) est que **tout ce que la base refuse, le modèle le refuse avant**.
Pourquoi : l'import écrit tout dans une seule transaction, sans `SAVEPOINT`. Une seule ligne que
la base refuserait annulerait l'import entier, et à chaque import, tant que le fichier est là.

Trois cas concrets que ce modèle ferme :

- **Un entier au-delà de 64 bits.** SQLite ne sait pas le stocker : `sqlite3` lève
  `OverflowError`. D'où `le=MAX_INT64` sur les trois entiers (`stars_gained` et `forks_gained` ne
  l'avaient pas).
- **Un nom trop long.** 255 caractères au plus, tenus deux fois : ici, et par
  `CHECK (length(repository_name) <= 255)`.
- **Un caractère de contrôle dans le nom.** Le motif de `RepositoryName` (`owner/name`, sans
  espace) accepte un NUL. Mais le `GLOB` de SQLite s'arrête au premier NUL : pour lui,
  `"own\0er/name"` est `"own"`, sans `/`, donc refusé. Un autre caractère de contrôle (une
  séquence d'échappement, `\x1b[31m`) passerait la base et partirait un jour au terminal qui
  affiche le nom. `check_text_has_no_control_character` (`src/k_b/items.py:64`) les refuse tous
  côté modèle, avec un type d'erreur nommé (`control_character`), que le motif du rejet cite.

Un classement est refusé **entier** si une ligne est invalide (règle 1 : un classement est un
instantané dont la complétude compte).

### 3. Lire les fichiers bruts pas encore importés

`src/k_b/sources/gh_archive.py:390`

```python
for path in list_visible_entries(source_dir):
    raw_file_path = path.relative_to(raw_dir).as_posix()
    if raw_file_path in imported_paths:
        continue
    try:
        collected_at = parse_collection_name(path.stem)
    except ValueError as error:
        rejections.append(reject(raw_file_path, f"{type(error).__name__}: {error}"))
        continue
    read_count += 1
```

`read_trend_files` parcourt `raw/automated_watch/gh_archive/` et applique les règles du lecteur
des items (`raw_items.py`), avec ses fonctions :

- un fichier déjà inscrit au registre (`imported_paths`) n'est pas ouvert ;
- un fichier dont le nom n'est pas une date de collecte est rejeté sans être ouvert ;
- un fichier illisible, ou que `read_trends` refuse, est rejeté, compté comme ouvert, et **pas
  inscrit au registre** : le prochain import le relira ;
- un dossier est rejeté sans être ouvert, et son chemin n'est pas cité (la source écrit un
  fichier par collecte, jamais un dossier de pages) ;
- un fichier lu donne un `TrendFile` : le fichier à inscrire, et ses lignes.

Chaque rejet passe par `reject`, le seul chemin vers le journal d'import.

Ce lecteur est appelé par `run_import` (`src/k_b/cli.py:122`), à côté du lecteur des items.

### 4. Écrire, avec la règle « par fenêtre »

`src/k_b/import_items.py:156`

```sql
INSERT INTO trend (...)
SELECT :raw_data_id, :window_end, :repository_id, ...
WHERE NOT EXISTS (
    SELECT 1 FROM trend WHERE window_end = :window_end AND raw_data_id <> :raw_data_id
)
ON CONFLICT (window_end, repository_id) DO NOTHING
RETURNING id
```

C'est le cœur de la PR. La question : que faire si une fenêtre arrive une seconde fois, dans un
fichier collecté plus tard, avec d'autres chiffres ?

La décision : GH Archive est un **flux de nouveautés appliqué à la fenêtre entière**. Le premier
classement vu d'une fenêtre est gardé entier ; le second est écarté entier.

- `WHERE NOT EXISTS (… raw_data_id <> :raw_data_id)` : la ligne n'est écrite que si **aucun
  autre fichier** n'a déjà apporté sa fenêtre. Les 48 lignes d'un même fichier partagent son
  `raw_data_id` : elles ne s'écartent donc pas entre elles.
- `ON CONFLICT … DO NOTHING` : si le **même** fichier est relu (deux imports en même temps, une
  base sans registre), ses lignes rencontrent la clé unique et ne sont pas réécrites.
- `RETURNING id` : la base dit si elle a écrit. Pas de ligne rendue : la ligne a été écartée.

Pourquoi comparer par fenêtre et non par clé, comme les autres flux de nouveautés ? Parce qu'un
classement est un tout. Un dépôt entré dans le classement à la seconde collecte aurait une clé
nouvelle : comparé par clé, il serait ajouté, et la fenêtre mélangerait deux comptages.

`write_trend_file` (`src/k_b/import_items.py:640`) inscrit le fichier au registre, écrit ses
lignes, et rend les fenêtres écartées. Chacune fait **une** ligne au journal d'import
(`already_seen`), où la fenêtre est nommée par son dernier jour ; aucun dépôt n'y est nommé.

### 5. Un seul ordre : celui des collectes

`src/k_b/import_items.py:375`

```python
return sorted([*reading.files, *trend_reading.files], key=read_collected_at)
```

Les fichiers d'items et les classements sont écrits en une seule suite, du plus ancien au plus
récent. Sans cela, les classements auraient été inscrits au registre après tous les items de
l'import. Une base tenue jour après jour inscrit alors : items du jour 1, classement du jour 1,
items du jour 2, classement du jour 2. Une base reconstruite d'un coup aurait inscrit : items des
jours 1 et 2, puis les classements. Les `raw_data.id` auraient différé entre les deux. Le tri est
stable : à date égale, les fichiers d'items passent d'abord, dans leur ordre de lecture.

## Choix faits et options écartées

| Choix | Retenu | Écarté, et pourquoi |
|---|---|---|
| Nature de la source | flux de nouveautés, par fenêtre (décision de Sabine) | catalogue d'état : il faut retirer les dépôts sortis du classement, donc une colonne nouvelle ou une suppression hors purge. Flux avec révisions : GH Archive ne donne pas de date de révision, et les dépôts sortis resteraient avec leurs anciens chiffres |
| Où compare la règle | par fenêtre | par clé (`window_end`, `repository_id`) : mélange deux comptages |
| Où vit l'écrivain | `import_items.py` (décision de Sabine : les sources avant le rangement) | `src/k_b/database/` : c'est la règle 5, que le déplacement du SQL d'écriture (#135) appliquera à tous les écrivains |
| Chemin de lecture | un lecteur à part, `read_trend_files` (décision de Sabine : le plus petit chemin) | étendre le contrat `SourceReader`, qui rend un `Item`, à autre chose qu'un item |
| Où vit `TrendRow` | `items.py` (décision de Sabine, écart à la 2e puce de la règle 4) | dans `gh_archive.py` : `import_items.py` est un module générique, un test lui interdit d'importer une source. Un second type de 5 champs : les champs écrits deux fois. Un `Protocol` : une abstraction sans second usage |
| `window_end` | minuit UTC, et un `CHECK` qui n'accepte que minuit | le `CHECK` de date commun, qui accepte une heure |
| Borne du nom | 255 caractères, modèle et base (décision du 2026-10-10 appliquée : la borne tient ce qu'une source peut écrire) | pas de borne. 255 n'est pas la limite de GitHub, qui n'a pas été confirmée par une source officielle ; le plus long nom collecté fait 38 caractères |
| Journal d'une fenêtre écartée | une ligne par fenêtre, sans dépôt | une ligne par dépôt : jusqu'à 60 lignes, avec `repo.id` |
| Tables `repository`, `star_gain` | retirées (décision de Sabine) | les garder : deux modèles de la même donnée, dont un sans écrivain |
| `SAVEPOINT` par ligne | non : `main` n'en a pas (#136) | — |
| Écrire le jour | `date.isoformat()`, qui écrit toujours l'année sur 4 chiffres (constat des deux revues) | `strftime("%Y")`, qui laisse le format de l'année à la bibliothèque C de la plateforme |
| Une clé inconnue dans une ligne | citée tronquée et échappée dans le motif du rejet (constat de la revue de sécurité) | recopiée telle quelle : un retour à la ligne y forgeait une fausse ligne de journal |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run pytest` : 772 passés | la suite entière, dont 54 tests nouveaux |
| `test_a_ranking_gives_a_trend_row_per_repository_of_its_window_and_no_item` | les 5 lignes d'un fichier, de la même fenêtre, sont toutes écrites ; aucun item n'est créé |
| `test_a_window_collected_again_keeps_its_first_ranking_whole_and_is_logged` | une fenêtre recollectée, autres chiffres et un dépôt nouveau : la base ne change pas, une ligne au journal, sans nom de dépôt |
| Clause `WHERE NOT EXISTS` retirée à la main : ce test échoue, seul | c'est bien cette clause, et pas la clé unique, qui écarte le dépôt nouveau |
| `test_a_ranking_with_a_known_window_and_a_new_one_writes_the_new_one_only` | la règle est par fenêtre, pas par fichier |
| `test_two_rankings_of_a_window_in_one_import_keep_the_one_collected_first` | dans un même import, le plus ancien classement est gardé |
| `test_a_rebuilt_database_with_rankings_equals_the_one_kept_import_after_import` | une base reconstruite est identique à une base tenue import après import |
| `test_a_value_a_check_of_trend_refuses_is_refused_by_the_trend_row` et les tests voisins de `tests/test_schema.py` | chaque `CHECK` de `trend` face à `TrendRow` : même refus, mêmes bornes acceptées |
| `CHECK (stars_gained >= 1)` écrit à la main à la place de `>= 0` : 13 tests échouent | un `CHECK` désaccordé du modèle est vu |
| `test_a_repository_name_with_a_control_character_is_refused_by_the_trend_row` | un caractère de contrôle, NUL compris, est refusé par le modèle |
| `test_the_message_quotes_an_unknown_field_name_truncated_and_escaped` | une clé inconnue ne peut pas forger une ligne de journal |
| `test_a_window_of_the_year_1_is_written_with_a_year_of_four_digits` | l'année est écrite sur 4 chiffres ; ce test passait déjà sur macOS avant la correction, c'est la CI Linux qui le rend probant |
| `test_a_ranking_refused_is_rejected_logged_and_read_again_at_the_next_import` | un brut refusé : un rejet au journal, pas d'inscription au registre |
| `kb import` sur le brut réel du 2026-10-11, base neuve dans un dossier temporaire : `trend rows written: 48` | les 48 dépôts de la collecte entrent en base ; une fenêtre (2026-10-10), 43 lignes avec des étoiles, 45 avec des forks |
| `kb collect` réel du 2026-10-13, avec ce code : `gh_archive: ok`, 2 fenêtres (11/10 et 12/10), 287 455 627 octets lus, 97 lignes | la collecte accepte un vrai résultat BigQuery avec le modèle resserré (bornes, caractères de contrôle) |
| `kb import` de tout le brut réel, base neuve à part : 37 fichiers lus, 3 078 items, 145 lignes de `trend` (48, 48 et 49 par fenêtre), 0 rejet ; un second import ne lit rien | le bout en bout sur données réelles, items et classements dans la même transaction |
| Les deux commandes de la règle 5 : `import_items.py` et `database/reading.py` ; rien | aucun fichier de plus ne porte de SQL ; aucune source n'écrit |

## Ce que tu dois pouvoir défendre

1. **Pourquoi `trend` n'est pas un item ?** Un item est une chose publiée (papier, release,
   article). Une tendance est une mesure sur un dépôt pendant 3 jours. Décision du 2026-10-08 ;
   d'où une table à part, rattachée à son fichier brut (`schema.sql:91`).
2. **Que se passe-t-il si la même fenêtre est collectée deux fois ?** Le premier classement est
   gardé entier, le second écarté entier et tracé au journal d'import (`import_items.py:156`).
   Limite : si le premier compte était faux, il reste.
3. **Pourquoi les 48 lignes d'un fichier ne s'écartent-elles pas entre elles ?** La clause compare
   à `raw_data_id` : elle écarte une ligne seulement si sa fenêtre vient d'un **autre** fichier
   (`import_items.py:163`).
4. **Où est la sécurité ?** Le fichier brut est une entrée non fiable : `TrendRow` le valide en
   mode strict, champs inconnus refusés (`items.py:292`) ; le SQL est paramétré ; le nom d'un
   dépôt, qui porte le login de son propriétaire, n'est écrit dans aucun journal (un message
   d'erreur n'en donne que la longueur, le journal d'import ne nomme que la fenêtre).
5. **Pourquoi le SQL est-il dans `import_items.py` alors que la règle 5 le veut dans
   `database/` ?** Écart temporaire, décidé : les sources manquantes d'abord, le rangement
   ensuite. Le déplacement du SQL d'écriture (#135) le rattrapera, avec les autres écrivains.

## Zones non vérifiées

- **La limite de longueur d'un nom de dépôt chez GitHub** : non confirmée par une source
  officielle. 255 est une borne large choisie, pas une valeur de GitHub.
- **`strftime` avec une année de moins de 4 chiffres sur Linux** : non essayé. Pour `trend`, le
  jour n'est plus écrit par `strftime` ; les autres colonnes de date (`format_date`) le sont
  encore, et gardent cette exposition.
- **Un fichier brut très gros** : la lecture n'a pas de taille maximale propre ; un classement de
  plus de 60 lignes par fenêtre est refusé, mais après avoir été lu en entier.
- **Les heures des tables du 11/10 et du 12/10** : leur nombre de lignes par jour est revenu au
  niveau d'avant l'anomalie, mais elles n'ont pas été recomptées heure par heure.

## Ce qui reste

- **Les totaux lus par GraphQL** (`stars_total`, `forks_total`) : #143.
- **Le SQL de `trend` dans `database/`** : #135.
- **Un seul chemin de lecture** pour les items et les classements : aujourd'hui deux, et la sorte
  `gh_archive` reste déclarée sans lecteur d'items. Aucune issue ne le porte.
- **Recollecter une fenêtre déjà prise** : les fenêtres du 2026-10-10, du 2026-10-11 et du
  2026-10-12 ont été comptées, en tout ou en partie, sur des tables appauvries, et leurs chiffres
  restent. Les corriger demande de retirer leur fichier brut et de reconstruire la base. Aucune issue ne le porte ; la détection d'une table incomplète (#141)
  concerne les collectes à venir.
- **La purge de `trend`** : pas définie (journal ADR, « Décisions encore ouvertes »). Le critère
  de l'issue de la purge (#83) dit « une commande supprime de la base et du brut ce qui a plus de
  2 ans », sans nommer les tables.
- **Un `SAVEPOINT` par entrée** : #136.
