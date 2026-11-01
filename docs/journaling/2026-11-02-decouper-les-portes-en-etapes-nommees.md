# Découper les portes de `kb collect` et `kb import` en étapes nommées

- **Date** : 2026-11-02
- **Branche** : `refactor/readable-collect-import` (pas d'issue : rangement de la session cosmétique)
- **Fichiers** : `src/k_b/cli.py`, `src/k_b/commands/collect_command.py`, `src/k_b/etl/extract.py`,
  `src/k_b/commands/import_command.py`
- **Série** : suite de [Ranger la ligne de commande](2026-10-18-ranger-la-ligne-de-commande.md) (#247), qui avait sorti
  chaque commande de `cli.py` sans découper `main`.

## Le pourquoi

Le script d'extraction (`kb collect`) et le script d'agrégation (`kb import`) se montrent à l'oral. Quatre fonctions
de leur trajet mélangeaient plusieurs niveaux de détail : `main` (90 lignes : les 9 commandes, les réglages, le
journal, les filets de sécurité), `run_collect`, `collect_all_sources` et `run_import`. On ne pouvait pas les lire
comme une suite d'étapes. La règle du dépôt le demande pourtant (`.claude/rules/code.md`, Lisibilité : « Une fonction
fait une chose », « Un seul niveau de détail par module et par fonction »).

C'est un **rangement seul** : aucun message, aucun code de sortie, aucune ligne de journal ne change. Sept fonctions
nouvelles portent chacune une étape, et sont placées juste après la fonction qui les appelle.

## Le comment

### 1. `main` se lit comme une recette

`src/k_b/cli.py:52-63`
```python
def main(argv: list[str] | None = None) -> int:
    command = read_command(argv)
    ...
    environ = read_environment()
    data_dir = read_data_dir(environ)
    log_to_file = read_log_to_file(environ)
    if data_dir is None or log_to_file is None:
        return ExitCode.NOT_STARTED
    return run_with_log(command, data_dir, environ, log_to_file)
```
Les étapes s'enchaînent : lire la commande, lire les réglages, lancer avec le journal. Chaque détail descend d'un
étage : l'`argparse` et ses 9 commandes dans `read_command` (`cli.py:66-118`), l'ouverture du journal dans
`run_with_log` (`:121-138`), les trois filets dans `run_with_safety_nets` (`:141-162`). On lit le chemin sans ouvrir
les étapes (`code.md` : « Un parcours s'écrit comme une suite d'étapes nommées »).

### 2. Les filets de sécurité tournent journal ouvert

`src/k_b/cli.py:128-138`
```python
    with ExitStack() as log_stack:
        try:
            log_stack.enter_context(logging_to(data_dir, log_file_path))
        except OSError as error:
            ...
            return ExitCode.NOT_STARTED
        return run_with_safety_nets(command, data_dir, environ)
```
`run_with_safety_nets` est appelée **à l'intérieur** du `with`. Ses trois `except` (SIGTERM, Ctrl-C, exception
imprévue) écrivent donc leur ligne pendant que le fichier de journal est encore ouvert. `ExitStack` existait déjà avant
ce changement : il permet que le `try` n'attrape **que** l'échec d'ouverture du journal, et pas une `OSError` levée par
la commande elle-même.

### 3. Une exception attrapée largement se journalise là où elle est attrapée

`src/k_b/etl/extract.py:63-73`
```python
        except Exception as error:
            ...
            logger.error(
                "collection failed for source %r: %s",
                source.name,
                describe_source_failure(error),
                exc_info=not isinstance(error, EXPECTED_SOURCE_ERRORS),
            )
```
Seule la mise en forme du texte descend, dans `describe_source_failure` (`extract.py:94-100`) : le type, le message
et les notes de l'erreur, chacun cité. L'appel à `logger.error` reste dans l'`except`, parce que ruff (règle
BLE001) refuse un `except Exception` qui ne journalise pas lui-même l'erreur : une erreur attrapée aussi largement ne
doit jamais pouvoir disparaître en silence. La ligne écrite reste mot pour mot la même, et `exc_info` vaut toujours
`True` ou `False` (`tests/etl/test_extract.py:81`).

### 4. Les deux commandes ont la même forme

`src/k_b/commands/collect_command.py:56-58` et `src/k_b/commands/import_command.py:63-68`
```python
    logger.info("collection finished in %s", describe_duration(monotonic() - started))
    print_collection_result(outcome, collect_only, environ)
    return find_collection_exit_code(outcome)
```
```python
    logger.info("import finished in %s", describe_duration(monotonic() - started))
    ...
    print_import_result(outcome)
    return purge_raw_after_import(data_dir)
```
Dans les deux cas : la durée au journal, le bilan à l'écran, puis le code de sortie. Les trois `except` de l'import
restent dans `run_import`, parce que ce sont eux qui décident quel code de sortie va avec quelle erreur : c'est la
décision de la commande.

### 5. Un détail de typage

`src/k_b/cli.py:116-118`
```python
    arguments = parser.parse_args(argv)
    command: str = arguments.command
    return command
```
`argparse` rend un `Namespace` dont les attributs sont de type `Any`. `mypy --strict` refuse de renvoyer un `Any`
depuis une fonction annoncée `-> str` (`no-any-return`). La variable annotée lui dit ce qu'on attend, sans
conversion.

## Choix faits et options écartées

| Choix | Pourquoi | Écarté |
|---|---|---|
| `describe_source_failure` (texte seul) | BLE001 : le `logger.error` doit rester dans l'`except` ; `describe_` est le vocabulaire du dépôt (`describe_outcome`, `describe_os_error`) | `log_source_failure`, qui aurait sorti le `logger.error` et fait échouer ruff ; un `# noqa: BLE001`, qui cache une règle au lieu de la suivre |
| `purge_raw_after_import` | dans `commands/`, `run_` est réservé aux commandes `kb` (`run_collect`, `run_import`…) | `run_purge`, qui laisserait croire qu'une commande `kb purge` existe |
| `print_import_result` (bilan seul) | même forme que `print_collection_result` | `report_import`, qui aurait aussi pris les deux lignes de journal, sans pendant côté collecte |
| Chaque fonction juste après celle qui l'appelle | le module se lit de haut en bas (`code.md` : « table des matières ») | les regrouper en fin de module |
| Aucun test nouveau | aucun comportement nouveau à décrire ; une mutation par fonction prouve que les tests existants couvrent le code déplacé | un test par fonction nouvelle, qui aurait figé le découpage lui-même |
| Pas d'ADR | rien qui engage la suite du projet | — |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run pytest` : 3 249 verts avant, 3 249 verts après | aucun test existant ne voit de différence |
| `ruff check`, `ruff format --check`, `mypy --strict` : verts | les règles du dépôt tiennent, BLE001 comprise |
| 7 mutations, une par fonction nouvelle (corps vidé, `except` changé, mauvais code rendu) : 7 attrapées, chacune par un test nommé dans la PR, qui passe sans la mutation | le code déplacé est réellement couvert par les tests |
| 8 captures de `kb` (aide, commande inconnue, sans `KB_DATA_DIR`, import sans base, `KB_COLLECT_ONLY=nope`, `create-db` puis `import`, `clipping` sans `Clippings/`), hors réseau, sortie standard + sortie d'erreur + code : `diff` vide avant/après, dates masquées | ce que voit l'utilisatrice est identique, octet pour octet |

## Ce que tu dois pouvoir défendre

1. **Pourquoi changer du code qui marchait ?** Pour qu'il se lise comme une suite d'étapes : un relecteur ou un
   mainteneur comprend `main` en 10 lignes au lieu de 90. Le comportement est garanti identique par les tests, les
   mutations et les captures (tableau « Preuve »).
2. **Comment sais-tu que rien n'a changé ?** Trois preuves indépendantes : les 3 249 tests, une faute volontaire par
   fonction nouvelle que les tests attrapent, et la comparaison des sorties réelles de `kb` avant et après.
3. **Pourquoi le `logger.error` est-il resté dans l'`except` de la boucle des sources ?** Parce qu'un
   `except Exception` attrape presque tout. ruff exige qu'il journalise lui-même, pour qu'aucune erreur ne disparaisse
   en silence (`extract.py:63-73`).
4. **Que se passe-t-il si le journal ne s'ouvre pas ?** Rien n'est lancé : message sur la sortie d'erreur, code 2
   (`cli.py:129-137`). Une exécution sans journal perdrait les échecs qu'il sert à garder.
5. **Qu'est-ce qui a changé de visible ?** Seulement la trace d'une exception imprévue : elle nomme
   `run_with_safety_nets` au lieu de `main`, avec d'autres numéros de ligne. Le format du journal n'affiche ni
   fonction ni ligne (`commands/run_log.py:25`).

## Zones non vérifiées

- **La règle exacte de BLE001** (un `except Exception` qui journalise est accepté) vient du comportement observé de
  ruff 0.16.10, sur la version écartée puis sur le code final. La documentation de ruff n'a pas été lue.
- **La trace qui nomme `run_with_safety_nets`** a été vérifiée par le relecteur du plan, en Python sur un cas réduit,
  pas en provoquant une exception imprévue dans `kb`.
- **Les captures** ne couvrent ni `serve-data`, ni `serve-ai`, ni `digest`, ni `trend-report`, ni `write-tops`. Ces
  commandes passent aussi par `run_with_log` et `run_with_safety_nets` ; elles ne sont couvertes que par la suite de
  tests.

## Ce qui reste

- Les renommages de `commands/` (sans le suffixe `_command`, outils rangés dans un sous-dossier) et la configuration
  du journal dans `core/logging_config.py` : décidés pour après l'oral du 02/11, dans la session cosmétique.
- `etl/pipeline.py` et `etl/load.py` (`commit_with_log`) ne sont pas touchés : ils sont déjà découpés, et leur
  difficulté tient au sujet lui-même (journal et commit atomiques).
- Les renvois `chemin:ligne` du dossier de certification vers ces fichiers sont à mettre à jour avec les renommages.
