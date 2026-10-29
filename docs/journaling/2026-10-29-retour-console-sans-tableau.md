# Le retour console sans tableau : kb collect, kb import, kb write-tops

- **Date** : 2026-10-29
- **Branche** : `feat/console-results-without-table`
- **Issue** : #359
- **Fichiers principaux** :
  - `src/k_b/commands/collect_command.py`, `import_command.py`, `write_tops_command.py` ;
  - `src/k_b/etl/load.py`, `extract.py`, `raw_reading.py`, `raw_files.py`, `transform.py`, `pipeline.py` ;
  - `src/k_b/post/top_sheets.py`.

## Le pourquoi

#291 (PR #358) avait mis un tableau à la fin de `kb collect` et de `kb import`. Sabine l'a vu en vrai
le 29/10 et ne l'a pas gardé : « la version initiale avec source et ok me convient mieux », « pas
besoin de tableau ». `kb digest` garde le sien (#357), qui lui convenait.

Ces trois commandes sont les étapes de la chaîne de veille. Ce qu'elles affichent, c'est ce que lit
la personne qui les lance, ou l'automatisation qui les enchaînera en ligne. Les lignes de journal de
#358 restent : `collection started`, le départ et la fin de chaque source, les durées.

## Le comment

### 1. collect revient au rendu d'avant #291

`collect_command.py:57-61` reprend la boucle de `31444ac` :

```python
for source_name, source_error in outcome.errors_by_source.items():
    print(f"{source_name}: {describe_outcome(source_error)}")
print_skipped_sources(collect_only, environ)
if outcome.state_error is not None:
    print(f"collection_state: {describe_outcome(outcome.state_error)}")
```

La ligne affiche une source et son état, rien de plus. Le nombre de bruts écrits n'y est pas : il
est déjà sur la ligne de journal de chaque source collectée (`extract.py:67-71`). C'est la règle de
Sabine du 28/10 : aucune source silencieuse.

### 2. import tient en une ligne, et nomme son journal

`import_command.py:63-67` :

```python
logger.info("import finished in %s", describe_duration(monotonic() - started))
logger.info("import log kept: %s", quote_value(outcome.log_path.name))
print(describe_import_summary(outcome))
```

`describe_import_summary` (l. 82) met les six totaux d'`ImportSummary` sur une ligne. Ces totaux
existaient avant #291 : il n'y a aucune nouvelle mesure. La ligne `import log kept` est nouvelle.
Sur un import normal, seule la ligne `Log:` du tableau donnait le journal d'import, c'est-à-dire
l'endroit où les rejets sont détaillés. Sabine a choisi d'en faire une ligne de journal.

### 3. write-tops : trois cas, imprimés à la fin

`write_tops_command.py:47-66` garde, comme sur `main`, le calcul du code de sortie dans la boucle
(`has_failed`, `has_done`). La boucle range en plus la ligne de chaque top dans `lines`, puis les
imprime après `write-tops finished`, comme collect :

```python
except (OSError, VaultEntryRefusedError) as error:
    ...
    lines.append(f"{top.name}: failed ({type(error).__name__})")
    has_failed = True
    deleted_count = None
```

`describe_outcome` (l. 81) suit l'ordre décidé par Sabine. Un relevé illisible donne
`failed (ranking_unreadable)`. Sinon, `ok, N sheet(s) written` si des fiches sont écrites,
`… the sheet of the day already exists` si la fiche du jour existe déjà, et `no ranking` s'il n'y a
aucun relevé. Le chemin `veille/tops/` vient de `SHEETS_VAULT_PATH` (`top_sheets.py:31`), que
`find_sheets_dir` utilise aussi : il est écrit à un seul endroit.

### 4. Le code qui ne servait qu'aux tableaux est retiré

Les fichiers de l'ETL reviennent à leur état de `31444ac` : `SourceImport`, `count_by_source`,
`opened_paths` et `unread_sources`. Le sous-agent de relecture a relu tout le diff de #358 sur ces
fichiers : il ne servait qu'aux tableaux. Disparaissent aussi :
- `raw_file_counts` ;
- la liste `written_paths`, car `collect_one_source` rend son compte (`extract.py:114`) ;
- `right_aligned` dans `render_table` ;
- le compte que renvoyait `purge_superseded_raw`, que plus rien ne lisait.

## Choix faits et options écartées

- **Partir de `main`, pas d'un revert de #358.** Un revert retirait aussi les lignes de journal
  gardées, qu'il aurait fallu recoder.
- **Le bilan de l'import en `print`, pas en ligne de journal.** C'est imposé par la règle 3 de
  `conventions.md` : `print` donne le résultat d'une commande, `logger` son déroulé.
- **Le nom du journal d'import, pas son chemin.** Le chemin nomme le dossier des données. Le nom
  passe par `quote_value`, comme dans `load.py`, et ne laisse donc pas injecter une fausse ligne
  (OWASP, Logging Cheat Sheet).
- **Le type d'une erreur seul dans `failed (<type>)`.** Le message d'une `OSError` contient le
  chemin du coffre. Un test le vérifie : `str(vault_dir)` n'est pas dans la sortie.
- **Écarté : le tableau de write-tops**, validé le matin même, avant que Sabine renonce aux autres
  tableaux.

## Preuve

| Test ou sortie | Ce que ça démontre |
|---|---|
| `test_import_writes_the_raw_items_into_the_database` | la ligne unique, puis les lignes `import started`, `finished` et `log kept` datées |
| `test_a_failed_purge_leaves_the_summary_of_the_import_it_committed` | le bilan est affiché avant la purge, même si elle échoue |
| `test_a_sheet_not_written_keeps_its_rankings_exits_4_…` | `failed (PermissionError)`, aucun chemin du coffre, pas de `Older raw files deleted` |
| `test_an_unreadable_ranking_is_kept_…` | un relevé illisible l'emporte sur les fiches écrites |
| `test_collect_still_prints_the_summary_and_exits_1_…` | l'ordre de collect : sources, `skipped`, `collection_state` |
| `uv run pytest` (2 759 tests), `ruff`, `mypy --strict` | rien d'autre n'a bougé |

## Ce que tu dois pouvoir défendre

1. **Pourquoi la ligne de l'import n'est-elle pas dans `kb.log` ?** C'est un résultat, et la règle 3
   donne le résultat à `print`. `kb.log` garde le déroulé, et maintenant le nom du journal d'import
   (`import_command.py:66`).
2. **Un top a écrit 4 fiches et garde un relevé illisible : pourquoi `failed` ?** Pour échouer
   fermé. Un relevé gardé illisible n'est jamais une réussite, et le code de sortie 4 dit qu'il y a
   eu un travail partiel (`write_tops_command.py:58-61`).
3. **Pourquoi pas de ligne `Older raw files deleted` après une erreur ?** La commande ne sait pas
   si l'erreur est venue pendant les suppressions, la dernière étape d'un top
   (`top_sheets.py:73`). Mieux vaut ne pas donner de compte qu'un compte faux.
4. **Où est la sécurité ?** Aucune valeur venue de l'extérieur n'est affichée. On n'affiche que des
   noms fixés dans le code, des types d'erreur et des comptes. Le seul nom de fichier journalisé
   passe par `quote_value`.

## Zones non vérifiées

- **La sortie réelle des trois commandes sur les données d'essai de Sabine** : elle sera vue à
  l'essai réel, avant la fusion.

## Ce qui reste

- **Lignes perdues sur un signal** : write-tops imprime ses lignes une fois tous les tops finis. Un
  SIGINT ou un SIGTERM pendant le second top fait donc perdre la ligne du premier. Limite assumée,
  dans l'ADR du 29/10.
- **Source en échec** : une source qui échoue au milieu de ses pages garde dans `raw/` les pages déjà
  écrites, mais leur nombre n'est donné nulle part, comme avant #291.
- **Traces des erreurs prévues** : Sabine a choisi le 29/10 une famille d'erreurs prévues, qui
  s'écriront en une ligne sans trace. Ce sera une issue à part.
