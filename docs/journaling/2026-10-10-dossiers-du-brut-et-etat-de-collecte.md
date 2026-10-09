# Renommer le dossier du brut et sortir l'état de collecte de `raw/`

- **Date** : 2026-10-10
- **Branche** : `refactor/raw-folders-and-collection-state`
- **Issue** : #116
- **Fichiers principaux** : `src/k_b/raw_store.py`, `src/k_b/collect.py`, `src/k_b/raw_items.py`,
  `src/k_b/cli.py`, `tests/test_cli.py`, `tests/test_collect.py`, `docs/specs-collecte.md`
- **Notes liées** : [la commande `kb collect`](2026-09-30-commande-kb-collect.md),
  [le résumé de collecte quand l'état ne s'écrit pas](2026-10-05-resume-collecte-etat-non-ecrit.md)

Le commit `573d6de` de la branche ne touche que `MEMORY.md` : il consigne une règle de travail
sur les fixtures et n'est pas expliqué ici.

## Le pourquoi

Deux décisions de Sabine du 2026-10-09 (journal ADR) n'étaient pas encore dans le code.

La première porte sur un nom. Le dossier du brut disait le moyen (`raw/automation/`) ; il dit
maintenant la finalité : `raw/automated_watch/` reçoit la veille collectée par K-B. Son pendant,
`raw/selected_library/`, recevra ce que Sabine choisit ; aucun code ne l'écrit encore.

La seconde porte sur un emplacement. `raw/` suit une règle : un fichier y est écrit une fois et
n'est jamais réécrit. Un seul fichier la contredisait, `collection_state.json`, qui garde la date
de la dernière collecte réussie de chaque source et qui est réécrit à chaque `kb collect`. Il va
à la racine du dossier de données, à côté de `k-b.sqlite` et de `import-log.jsonl`. `raw/` pourra
alors être mis en lecture seule, et synchronisé sans l'état propre à chaque machine.

L'état ne peut pas être supprimé au profit du brut : une source qui n'a rien de neuf n'écrit
aucun fichier brut, mais sa date avance quand même (`src/k_b/collect.py:48`).

## Le comment

### 1. Le nom du dossier vit à un seul endroit

```python
# src/k_b/raw_store.py:10-12
# The folder of raw/ that holds what the watch collects, one folder per source.
AUTOMATED_WATCH_DIR_NAME = "automated_watch"
COLLECTION_STATE_FILENAME = "collection_state.json"
```

Avant, le mot `"automation"` était écrit deux fois : là où la collecte écrit, et là où l'import
lit. Les deux devaient rester identiques sans que rien ne le garantisse. La constante est placée
dans `raw_store.py`, le module qui porte déjà le nom du fichier d'état, et les deux autres
modules l'importent :

```python
# src/k_b/collect.py:69
source_dir = raw_dir / AUTOMATED_WATCH_DIR_NAME / source.name
```

```python
# src/k_b/raw_items.py:113
for source_dir in sorted((raw_dir / AUTOMATED_WATCH_DIR_NAME).glob("*/")):
```

### 2. La collecte reçoit deux dossiers au lieu d'un

```python
# src/k_b/collect.py:31-33
def collect_all_sources(
    sources: list[Source], raw_dir: Path, data_dir: Path, now: datetime
) -> CollectionOutcome:
```

`raw_dir` sert au brut, `data_dir` à l'état. L'état est lu avant les sources
(`collect.py:37`, `load_last_collection_dates(data_dir)`) et écrit après
(`collect.py:51`, `save_last_collection_dates(data_dir, …)`). Si l'écriture échoue, le journal
donne le chemin réel du fichier, donc le nouveau (`collect.py:53-55`).

Dans `raw_store.py`, seul le nom du paramètre change (`raw_dir` devient `data_dir`,
lignes 38-39 et 63-73) : les deux fonctions prenaient déjà « le dossier qui contient le fichier
d'état ».

### 3. La ligne de commande décide où est chaque dossier

```python
# src/k_b/cli.py:107-112
outcome = collect_all_sources(
    list_sources(SOURCE_KINDS),
    data_dir / "raw",
    data_dir,
    datetime.now(UTC),
)
```

`cli.py` est le seul module qui connaît `KB_DATA_DIR` et le nom `raw`. L'appel de l'import
(`cli.py:91`) ne change pas : `import_items` lit le brut et n'a jamais lu l'état.

### 4. Les tests distinguent les deux dossiers

Les tests de `tests/test_collect.py` passaient un seul dossier. Ils passent maintenant
`tmp_path / "raw"` pour le brut et `tmp_path` pour l'état. Les deux paramètres ont le même type
(`Path`) : mypy ne verrait pas une inversion, ce sont donc les tests qui la détectent, puisque les
fichiers bruts sont attendus sous `tmp_path / "raw" / "automated_watch"` et l'état sous
`tmp_path`.

Les deux tests « l'état ne peut pas s'écrire » retiraient le droit d'écriture sur `raw/`. Ils le
retirent maintenant sur le dossier de données, après avoir créé `raw/automated_watch` :

```python
# tests/test_cli.py:66-67
(tmp_path / "raw" / "automated_watch").mkdir(parents=True)
tmp_path.chmod(0o500)
```

Le brut s'écrit donc encore (son dossier existe et reste modifiable), l'état non.

### 5. Les fichiers déjà collectés se déplacent à la main

K-B ne contient aucun code de migration. Pour un dossier de données existant :

```sh
mv "$KB_DATA_DIR/raw/automation" "$KB_DATA_DIR/raw/automated_watch"
mv "$KB_DATA_DIR/raw/collection_state.json" "$KB_DATA_DIR/collection_state.json"
```

Puis recréer la base et réimporter : le chemin du brut stocké en base
(`collection.raw_file_path`) est relatif à `raw/` et passe de `automation/…` à
`automated_watch/…`.

## Choix faits et options écartées

| Décision | Retenu | Écarté, et pourquoi |
|---|---|---|
| Signature de `collect_all_sources` | deux paramètres, `raw_dir` et `data_dir` | Un seul `data_dir`, la fonction calculant `data_dir / "raw"` : le nom `raw` serait écrit dans `cli.py` (pour l'import) et dans `collect.py`. Passer `data_dir` aussi à `import_items` : l'import ne lit pas l'état, ses tests auraient été réécrits sans besoin. |
| Nom du dossier dans le code | une constante dans `raw_store.py` (validé par Sabine le 2026-10-10) | Le littéral répété dans `collect.py` et `raw_items.py` : contraire à « une connaissance vit à un seul endroit » (`.claude/rules/code.md`). |
| Anciens emplacements | K-B ne les lit plus | Lire l'ancien emplacement en secours, ou déplacer les fichiers au lancement : l'issue demande une commande `mv`, « pas du code dans K-B ». |
| Fixture `tests/fixtures/arxiv_extract.xml` | inchangée (validé par Sabine) | Retirer le mot « automation » du résumé d'un vrai papier arXiv pour satisfaire `grep -rn "automation" src tests` : ce serait altérer une donnée collectée. Le critère se vérifie sur les fichiers `.py`. |
| `docs/stockage.md` (`raw/manual/`) | inchangé (validé par Sabine) | Le renommer en `raw/selected_library/` : ces lignes décrivent l'ancien modèle, où ces documents restaient hors de la base ; la décision du 2026-10-09 dit l'inverse. |
| `.env.example`, `docs/sources.md` | alignés sur le README (validé par Sabine) | Les laisser : ils auraient dit que seul `raw/` est écrit dans le dossier de données. |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_collect_writes_its_state_at_the_root_of_the_data_directory_not_in_raw` (`tests/test_cli.py:47`), rouge sur `main`, vert sur la branche | après `kb collect`, `collection_state.json` est à la racine du dossier de données et absent de `raw/` |
| `test_only_successful_sources_advance_their_last_collection_date` (`tests/test_collect.py:48`) | l'état écrit sous le dossier de données se relit depuis ce même dossier, le brut étant ailleurs |
| `test_collect_still_prints_the_summary_and_exits_1_when_the_state_cannot_be_written` (`tests/test_cli.py:63`) | dossier de données en lecture seule : le brut est écrit, la ligne `collection_state: failed (PermissionError)` s'affiche, code 1 |
| `test_a_state_that_cannot_be_written_is_returned_and_logged_with_its_path` (`tests/test_collect.py:155`) | le journal cite le chemin du fichier d'état à son nouvel emplacement |
| `uv run pytest` : 314 tests verts ; `ruff check`, `ruff format --check`, `mypy --strict` verts | rien d'autre n'est cassé |
| `kb create-db` puis `kb import` sur la collecte réelle du 2026-10-07 déplacée : 2 500 items, 0 rejet, tous les `raw_file_path` commencent par `automated_watch/` | l'import lit le dossier renommé |

## Ce que tu dois pouvoir défendre

- **Pourquoi sortir l'état de `raw/` ?** `raw/` est écrit une fois, jamais réécrit
  (`write_new_raw_file`, `src/k_b/raw_store.py:31-35`). L'état est réécrit à chaque collecte
  (`save_last_collection_dates`, `raw_store.py:63`). Séparés, `raw/` peut être protégé en
  lecture seule et synchronisé seul.
- **Pourquoi garder un fichier d'état, alors que le brut est daté ?** Une source sans nouveauté
  n'écrit pas de brut mais avance sa date (`src/k_b/collect.py:48`). Déduire la date du dernier
  fichier brut ferait recollecter une fenêtre déjà vue.
- **Que se passe-t-il si on met à jour K-B sans déplacer les fichiers ?** L'état est absent du
  nouvel emplacement, donc `load_last_collection_dates` renvoie `{}` (`raw_store.py:40-41`) : la
  collecte repart de zéro pour chaque source. L'import ne trouve pas `raw/automated_watch/` et
  importe 0 item. Rien n'est supprimé.
- **Et la base déjà remplie ?** Ses lignes `collection` gardent les chemins `automation/…`. La
  base est jetable (décision du 2026-10-09) : on la recrée et on réimporte depuis le brut.
- **Comment sait-on que les deux dossiers ne sont pas inversés dans le code ?** Par les tests de
  `tests/test_collect.py`, qui donnent deux dossiers différents et vérifient où tombent le brut
  et l'état.

## Zones non vérifiées

- Aucun vrai `kb collect` (réseau) n'a été lancé sur `temp/.knowledge_base` : seul l'import l'a
  été, sur une copie par lien du brut.
- La commande `mv` de la PR n'a été exécutée que sur `temp/raw` ; aucun autre dossier de données
  n'existait sur la machine (`~/K-B-data` et `~/.knowledge_base` absents).
- `kb collect` ne crée plus `raw/` quand aucune source n'écrit de brut (c'était l'écriture de
  l'état qui le créait). `kb import` sur un dossier sans `raw/` est couvert par
  `test_import_writes_the_raw_items_into_the_database` (0 item importé).

## Ce qui reste

- `raw/selected_library/` n'est écrit par aucun code : il viendra avec les sources que Sabine
  choisit.
- Le nom du flux arXiv et le nom des modules (`raw_store.py` porte encore les fonctions de
  l'état, qui n'est plus dans `raw/`) relèvent d'autres issues (#117, #107).
- Les documents datés (`docs/2026-10-04-flux-donnees.md`, `docs/2026-10-06-revue-architecture.md`,
  les notes de `docs/journaling/`, le journal ADR) citent encore les anciens noms : ils décrivent
  l'état à leur date. Dans `docs/2026-10-07-clarification-modele.md`, seuls les six exemplaires
  et les lignes 363 et 725 ont été mis à jour ; les passages qui racontent la décision gardent
  l'ancien nom.
- La mise en lecture seule de `raw/` et sa synchronisation ne sont pas faites.
