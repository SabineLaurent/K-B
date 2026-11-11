# Écrire la fiche de l'agrégation, de l'import et de la base

- **Date** : 2026-11-11
- **Branche** : `docs/import-and-base-sheet`, partie de `main` au commit `94e3f4e`
- **Issue** : #504
- **Fichiers** : `documentation/import_et_base_pour_docu.md` (nouveau), `docs/specs-collecte.md` (trois puces)
- **Série** : suit `2026-11-09-ecrire-la-fiche-de-l-installation.md`, qui installe l'environnement ; cette fiche-ci
  part de là pour la base et l'import.

## Le pourquoi

La certification demande quatre documentations que K-B n'avait qu'éparpillées entre le README, `docs/specs-collecte.md`,
`docs/stockage.md` et `infra/README.md` : celle des scripts, celle de l'installation du système de gestion de base de
données, celle du script d'import, et celle de l'accès à la base dans chaque environnement. La fiche les réunit en
un seul fichier, écrit d'après le code de `main`, chaque fait avec son `fichier:ligne`. Le README garde sa section
« Installer et lancer » : la fiche la reprend et la détaille, elle ne la remplace pas (décision de Sabine du 08/11).

Aucun code n'a changé. Les trois commits de la branche sont la fiche (`7de6d26`), puis les corrections des deux
relectures (`8838487`, `1fd0e65`). Les autres commits que liste le skill sont l'histoire de `main` : la note ne les
couvre pas.

## Le comment

### Une fiche qui se vérifie ligne à ligne

Chaque affirmation renvoie au code, et chaque renvoi a été contrôlé par un script du scratchpad qui ouvre le fichier
cité et affiche la première et la dernière ligne de la plage : 231 renvois, tous dans la longueur de leur fichier.
C'est ce contrôle qui a trouvé les plages décalées d'une ligne (une ligne vide, un commentaire voisin) avant les
relectures. Un chemin sans préfixe part de `src/k_b/`, comme dans les autres fiches.

### L'enchaînement de `kb import`, lu dans `etl/pipeline.py`

```python
    imported_paths = read_imported_paths(database)
    readings = read_raw_files(
        data_dir / RAW_DIR_NAME, kinds, imported_paths, tracked_repositories
```

(`src/k_b/etl/pipeline.py:70-72`). Le parcours tient en trois appels : le registre de la base (les fichiers déjà
importés), un seul passage dans `raw/` qui lit le reste, puis `import_items`, qui écrit tout dans une transaction. La
fiche suit cet ordre en dix étapes numérotées, qui sont aussi le texte équivalent de son schéma Mermaid.

### Ce que l'import garde quand il s'arrête

```python
    check_journal_absent(journal_path)
    try:
        write_import_journal(
```

(`src/k_b/etl/load.py:129-131`). Le contrôle du journal vient **après** la lecture et l'écriture de tous les
fichiers, une fois le verrou des écrivains pris. Un journal de la même seconde fait donc annuler une transaction
entière : tout a été lu, rien n'est gardé. La première version de la fiche disait « rien n'est lu » ; la relecture l'a
trouvé, et c'est la correction la plus importante. Il en va de même pour un signal : reçu avant le `COMMIT`, il annule
tout, et le sens générique du code 143 (« ce qui est fait avant est gardé ») ne vaut pas pour l'import.

### Les dates en UTC à la lecture, pas à la normalisation

`UtcDatetime = Annotated[AwareDatetime, AfterValidator(convert_to_utc)]` (`src/k_b/items.py:245`) : la date est
convertie quand le lecteur construit l'item. `normalize_item` dit lui-même « its dates are in UTC already »
(`src/k_b/etl/normalize.py:11`). `docs/specs-collecte.md` plaçait la conversion à la normalisation ; sa puce est
corrigée dans la même PR, sur l'accord de Sabine.

### Ce que retire la normalisation d'une URL

```python
    query = "&".join(
        parameter
        for parameter in parts.query.split("&")
        if parameter and not parameter.startswith(TRACKING_PARAMETER_PREFIX)
    )
```

(`src/k_b/etl/normalize.py:22-26`). `if parameter` retire les morceaux vides entre deux `&`, pas un paramètre sans
valeur : `x=` reste. `startswith("utm_")` tient compte de la casse : `UTM_x` reste. Une requête vide disparaît avec son
`?`. Les trois faits ont été essayés, puis reportés dans la fiche et dans les deux puces de `docs/specs-collecte.md`
qui décrivaient la règle (la normalisation, et la clé d'un clip).

### Lire la base sans l'API

```python
    connection = sqlite3.connect(
        f"{database_path.absolute().as_uri()}?mode=ro",
        uri=True,
```

(`src/k_b/database/engine.py:113-115`). C'est l'ouverture en lecture seule de l'API de données, et la fiche donne la
même forme en une commande `uv run python -`. La commande du README, `sqlite3 -readonly`, a échoué à l'essai (voir la
preuve) : la fiche dit ce qui a été observé, et une issue de suite porte la correction du README.

## Choix faits et options écartées

- **Une fiche qui reprend, sans toucher au README** : imposé par le critère de #504. Écarté : déplacer la section du
  README dans la fiche.
- **Écrite sur le dernier `main`** (décision de Sabine du 11/11), repointée sur `94e3f4e` quand #577 a été fusionnée.
  Écarté : un commit figé.
- **La forme Python pour lire la base**, essayée. Écartées : `sqlite3 -readonly` et `sqlite3 "file:…?mode=ro"` (erreur
  14), `python -m sqlite3` (n'ouvre pas une URI `file:`).
- **Corriger `docs/specs-collecte.md` dans la même PR** : le critère de #504 voulait `docs/` intact ; Sabine a accepté
  la correction de la phrase des dates, et time-knight celle des URL (« une phrase fausse vue dans `docs/` ne reste
  pas »). Écarté : une PR à part.
- **Les commandes d'accès en ligne reprises d'`infra/README.md`, sans les lancer** : aucune commande `az` dans cette
  mission. Elles sont écrites comme une procédure non essayée.
- **L'installation de PostgreSQL sur le Mac n'est pas décrite** : le dépôt ne la décrit pas, et le critère ne vise que
  SQLite sur le Mac et PostgreSQL en ligne. Elle est écrite comme une limite.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `kb create-db` sur un dossier neuf : code 0, puis code 2, `… already exists` | la création et le refus d'une base existante |
| `kb import` sans brut : `import: 0 raw read, 0 written, 0 trend rows, 0 left out, 0 rejected, 0 withdrawn`, code 0, journal en `0600` | la commande, son bilan et son journal |
| lecture par `sqlite3` de Python en `mode=ro` : les 7 sources ; une écriture : `attempt to write a readonly database` | la commande de lecture seule de la fiche |
| `/usr/bin/sqlite3 -readonly` (3.51.0) sur la base au repos : `unable to open database file (14)` | la limite écrite, et l'issue de suite |
| `remove_tracking_parameters` sur `?a=1&&b=2`, `?x=&utm_source=z&y=2`, `?`, `?UTM_x=1&utm_y=2` | la règle des URL de la fiche et de `docs/specs-collecte.md` |
| script des renvois : 231 renvois dans leur fichier ; aucune espace avant « : » ni « ; » ; aucun `Cc` ni `Cf` | les contrôles de la mission |
| relecture 1 (24 constats, dont 4 faux) puis relecture du delta (13 constats, aucun faux sur le fond), tous corrigés sur le tri de time-knight | la justesse du texte face au code |

## Ce que tu dois pouvoir défendre

- **Pourquoi deux SGBD ?** SQLite sur le Mac, sans serveur, un seul écrivain par jour ; PostgreSQL en ligne, parce
  qu'un fichier SQLite n'a pas de disque fiable sur Azure Container Apps (`docs/stockage.md`, « Le SGBD »). Le même SQL
  passe sur les deux (`src/k_b/database/creation.py:119-124` pour le schéma PostgreSQL).
- **Que se passe-t-il si l'import est coupé ?** Avant le `COMMIT`, rien n'est gardé et le journal est supprimé ; après,
  tout est gardé ; pendant, sur PostgreSQL, l'issue est inconnue et le journal reste (`src/k_b/etl/load.py:139-160`).
- **Comment les doublons sont-ils écartés ?** Par l'écrivain de chaque sorte, selon la nature de la source : première
  version gardée, révision plus récente, catalogue plus récent (`src/k_b/database/writers/`). Seul le doublon exact est
  trouvé (`src/k_b/etl/file_writing.py:4-5`).
- **Où est la sécurité de l'accès à la base ?** Lecture seule par `mode=ro` sur le Mac
  (`src/k_b/database/engine.py:113-115`) ; en ligne, Entra seul, mot de passe coupé, `sslmode=verify-full` exigé
  (`src/k_b/database/postgresql.py:178-192`), et des rôles distincts pour lire et écrire
  (`src/k_b/database/grants_postgresql.sql:6-7`).
- **Pourquoi la fiche ne donne-t-elle pas la commande du README ?** Elle a échoué à l'essai sur une base au repos ;
  la fiche donne une commande essayée, et l'écart est porté par une issue.

## Zones non vérifiées

- Les commandes d'accès en ligne (`az containerapp exec`, `admin_psql`) : reprises d'`infra/README.md`, jamais
  lancées.
- La commande `psql` sur un PostgreSQL du Mac : non essayée.
- La cause de l'échec de `sqlite3 -readonly` : seul le constat est établi (base sans `-wal` ni `-shm`, `sqlite3` de
  macOS 3.51.0), pas son mécanisme.
- La première relecture a été coupée par le quota : elle n'a pas rejoué les essais. La relecture du delta n'a relu que
  les lignes changées.

## Ce qui reste

- L'issue de suite du README (`sqlite3 -readonly`), à créer par Sabine.
- Le format accessible des fiches (#167, tâche suivante de la mission) touchera la forme de celle-ci : liens
  explicites, publication.
- `docs/journaling/2026-10-05-fusionner-les-items.md` dit aussi « les dates sont ramenées en UTC » : une note datée,
  laissée telle quelle.
