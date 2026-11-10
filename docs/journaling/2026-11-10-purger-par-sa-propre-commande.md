# La purge par sa propre commande, `kb purge`

- Date : 2026-11-10
- Branche : `feat/purge-command`
- Issue : #540
- Fichiers principaux : `src/k_b/commands/purge_command.py` (nouveau), `src/k_b/purge/all_purges.py` (ex
  `after_import.py`), `src/k_b/commands/import_command.py`, `src/k_b/commands/daily_routine_command.py`
- Suite de : [2026-11-04, purger la base et le brut hors de l'ETL](2026-11-04-purger-la-base-et-le-brut-hors-de-l-etl.md)

## Le pourquoi

Jusqu'ici, la purge (supprimer ce qui a passé sa durée de conservation : base, brut, registre, logs, journaux)
tournait à la fin de `kb import`, après la validation de l'import. Sabine veut « qu'elle soit appelée en dehors du
script d'import à proprement parler » : des briques qui marchent chacune seule, puis un chapeau par-dessus, la
routine quotidienne. La purge devient donc une commande à part, et la routine la lance juste après l'import. Sans
cette étape, plus rien ne purgerait en ligne, et les durées du registre des traitements ne seraient plus tenues.

## Le comment

### Une commande qui marche seule

```python
    purged_at = datetime.now(UTC).replace(microsecond=0)
    logger.info("purge started")
    started = monotonic()
    try:
        count = purge_all(
            data_dir, database, purged_at, STATE_CATALOGS, GITHUB_TRACKED_REPOSITORIES
        )
```
`src/k_b/commands/purge_command.py:52-58`

La date de référence est l'heure de lancement de `kb purge`, à la seconde, en UTC : chaque purge calcule sa borne
à partir d'elle (3 ans pour la veille de la base, 6 mois pour le brut, les logs et les journaux). `STATE_CATALOGS`
(Zotero, CISA KEV) a quitté `import_command.py` : seule la purge s'en servait.

### Les erreurs : nommées, et jamais un nom de fichier

```python
    except MissingDatabaseError as error:
        logger.error("%s; create it with kb create-db", error)
        return ExitCode.NOT_STARTED
    ...
    except (*ENGINE_ERRORS, OSError, ValueError) as error:
        # The type, and the reason of an OSError, never the name of a raw file.
```
`src/k_b/commands/purge_command.py:60-67`

`MissingDatabaseError` est une `FileNotFoundError`, donc une `OSError` : elle doit être rattrapée avant, sinon
une base absente sortirait en 1 (« purge failed ») au lieu de 2 (« rien n'a été lancé »). Le message d'échec garde
la forme qu'il avait dans `kb import` : le type de l'erreur, ou le motif d'une `OSError` (`describe_os_error`),
jamais le chemin, qui nommerait un fichier brut (règle 3 de `conventions.md`).

### Le résultat sur la sortie standard, le déroulé au journal

```python
    return (
        f"purge: {count.superseded_count} superseded raw files, {base.item_count} items,"
```
`src/k_b/commands/purge_command.py:90-91`

Chaque purge journalise déjà son compte. Mais une commande donne son résultat par `print`, et le déroulé par le
journal (règle 3) : `purge_all` rend donc les comptes (`PurgeCount`, `src/k_b/purge/all_purges.py:29-36`), que
`kb purge` affiche sur une ligne, entre deux lignes vides, comme `kb import`. Ce point vient de la revue de code.

### `kb import` ne purge plus

`run_import` finit par `return ExitCode.SUCCEEDED` après son bilan (`src/k_b/commands/import_command.py:64-65`).
Le critère de l'issue se vérifie par `git grep -n "purge" src/k_b/commands/import_command.py`, qui ne rend rien.

### Dans la routine : sans règle d'arrêt

```python
    # Even after an import that fails or is not run: it committed nothing, and the purge reads the
    # base of the last import committed (decision of Sabine of 2026-11-10, #540).
    RoutineStep(
        "kb purge", lambda settings: run_purge(settings.data_dir, settings.environ)
    ),
```
`src/k_b/commands/daily_routine_command.py:60-64`

Pas de `NotRunAfter` : l'étape tourne quel que soit le code de `kb import`. C'est sans danger parce que l'import
est une seule transaction, et parce que la purge des catalogues prend sa liste dans le registre, jamais dans le
dossier : « a raw file not imported is never deleted » (`src/k_b/purge/catalogs.py:19-20`). La `lambda` appelle
`run_purge` par son nom dans le module, au moment où l'étape tourne : un test peut ainsi la remplacer.

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Date de référence | L'heure de lancement de `kb purge` : la commande marche seule, et les durées sont des maxima. | L'heure du dernier import, lue en base : sans import nouveau, ce qui a expiré depuis ne serait jamais supprimé. |
| La purge après un import en échec | Elle tourne (décision de Sabine) : la base et le registre restent ceux du dernier import validé. | `NotRunAfter("kb import", {1, 2})` : un import en échec chaque jour bloquerait toute purge, et la purge tournerait quand l'import est sauté mais pas quand il échoue. |
| Les noms | `purge/all_purges.py`, `purge_all`, `purged_at` : la purge ne suit plus l'import. `purge_all` plutôt que `run_purges`, qui ne différait que d'une lettre de `run_purge` (revue). | Garder `after_import` et `imported_at`, faux une fois la purge détachée. |
| Un verrou contre un `kb import` simultané | Aucun : la limite est écrite au registre, avec sa parade (les lancer l'un après l'autre). Tri de time-knight. | Un verrou de fichier : du code pour un cas que la routine et `make` évitent déjà. |
| Factoriser l'ouverture de `run_purge` et de `run_import` | Non : deux occurrences, `code.md` factorise à la troisième. | Une fonction commune dès maintenant. |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_purge_alone_deletes_what_is_past_its_durations_without_an_import_that_day` | `kb purge` seule, 3 ans après un import, vide la base, le brut, le registre, les logs et les journaux, et affiche son bilan. |
| `test_import_deletes_no_raw_file_and_runs_no_purge` | `kb import` ne supprime plus rien. |
| `test_a_failed_purge_exits_1_names_no_raw_file_and_the_next_purge_purges` | Un échec dit « run kb purge again », ne cite aucun fichier, et le `kb purge` suivant purge. |
| `test_purge_refuses_a_missing_database_does_not_create_it_and_exits_2` | Sans base, le code est 2 et la base n'est pas créée. |
| `test_kb_purge_comes_right_after_kb_import_without_a_rule`, `test_kb_purge_runs_after_kb_import_exits_with_1_or_2` | La place de l'étape dans la routine, et la décision D2. |
| `test_a_sigterm_during_the_purge_of_the_base_undoes_the_purge_and_exits_with_143`, `test_a_ctrl_c_during_the_purge_of_the_base_undoes_it_and_exits_with_130` | Un signal annule la purge de la base en cours. Le test Ctrl-C est passé dès son écriture : l'annulation existait déjà (`purge/base.py`). |
| `uv run kb daily-routine --dry-run` | Six étapes, `kb purge` en 4e. |

## Ce que tu dois pouvoir défendre

1. **Purger après un import en échec, n'est-ce pas risqué ?** Non : l'import n'a rien validé, et un brut pas encore
   importé n'est jamais supprimé comme catalogue remplacé (`purge/catalogs.py:19-20`). Le seul brut jamais importé
   qui part a plus de 6 mois, ce qui était déjà vrai avant (registre, étape 3).
2. **Pourquoi l'heure de lancement, pas celle de l'import ?** Parce que la commande doit marcher seule
   (`purge_command.py:52`). Une durée de conservation est un maximum : elle se compte depuis maintenant.
3. **Que se passe-t-il si la purge de la base échoue ?** Les purges suivantes ne tournent pas, `kb purge` sort en 1
   avec « run kb purge again », et la base reste telle qu'elle était, la transaction étant annulée
   (`test_a_failed_purge_of_the_base_stops_the_purges_after_it`).
4. **Où est la protection des données personnelles ?** Aucun journal ne cite un nom de fichier brut ni un auteur
   (`purge_command.py:67`), et la durée de conservation reste tenue en ligne par l'étape de la routine.

## Zones non vérifiées

- Les tests marqués `postgresql` (`tests/etl/test_import_on_both_engines.py` lance maintenant `kb purge` après
  chaque import) n'ont pas tourné sur le Mac : le serveur local demande un mot de passe. Le job `tests-postgresql`
  de la CI fait foi.
- La routine n'a pas tourné en ligne : l'image avec `kb purge` n'est pas déployée.

## Ce qui reste

- La sauvegarde de la base avant la purge, et la purge du brut couvert par deux sauvegardes : #390, qui ajoutera
  `pg_dump` avant l'étape `kb purge` de la routine.
- `.claude/rules/conventions.md:108` a été corrigé à part, par #543.
