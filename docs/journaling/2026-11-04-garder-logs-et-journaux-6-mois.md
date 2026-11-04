# Garder les logs et les journaux 6 mois

- Date : 2026-11-04
- Branche : `feat/logs-and-journals-kept-6-months`
- Issue : #267
- Suite de : [Purger la base et le brut hors de l'ETL](2026-11-04-purger-la-base-et-le-brut-hors-de-l-etl.md) (#83)
- Fichiers principaux : `src/k_b/purge/run_records.py`, `src/k_b/core/config.py`,
  `src/k_b/commands/run_log.py`, `src/k_b/etl/import_journal.py`, `docs/registre-traitements.md`

## Le pourquoi

Avant cette PR, les logs de fonctionnement gardaient 30 *fichiers*, pas une durée : un jour sans
commande ne crée pas de fichier, donc 30 fichiers pouvaient couvrir des mois. Les fichiers JSON de
l'import n'étaient jamais purgés. Le RGPD demande une durée de conservation, et le registre ne
pouvait pas en écrire une.

Deux décisions de Sabine du 2026-11-04 : un **log** dit ce qu'un programme a fait, un **journal** dit
ce qu'un import a décidé sur les données ; et les deux sont gardés **6 mois**, le bas de la
fourchette que recommande la CNIL (délibération n° 2021-122, non contraignante).

## Le comment

### Une seule purge, la rotation ne supprime plus rien

`backupCount` de `TimedRotatingFileHandler` compte des fichiers et ne supprime qu'à une rotation.
Il passe à 0 : seule la purge supprime un log.

```python
# A rotation deletes nothing: backupCount counts files, not days. Only the purge
# deletes a log (purge/run_records.py).
backupCount=0,
```
`src/k_b/commands/run_log.py:56-58`

La purge est la dernière étape de `purge_after_import` (`src/k_b/purge/after_import.py:55`), après
la base, le brut et le registre, une fois l'import commité. Une erreur y rend l'import `FAILED`,
comme les autres étapes de #83.

### Le jour vient du nom, jamais de l'heure du fichier

Une copie ou une restauration change l'heure d'un fichier, pas son nom. Chaque dossier a son motif :

```python
DATED_NAME_BY_FOLDER = {
    LOGS_DIR_NAME: re.compile(
        rf"(?:{LOG_NAMES_PATTERN})\.([0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}})"
    ),
    JOURNALS_DIR_NAME: re.compile(
        r"import-journal-([0-9]{4}-[0-9]{2}-[0-9]{2})T[0-9]{6}Z\.jsonl"
    ),
}
```
`src/k_b/purge/run_records.py:28-35`

`fullmatch` exige le nom entier (`is_dated_before`, ligne 65). Un nom qui ne correspond pas, ou dont
la date n'existe pas (`2020-13-45`, `ValueError`), n'est jamais supprimé. Le log en cours
(`kb.log`, sans date) non plus.

### Seuls les logs que K-B écrit (correction de la revue, constat 8)

Le premier motif, `[a-z-]+\.log\.<jour>`, acceptait n'importe quel préfixe : un
`incident.log.2026-01-01` posé à la main aurait été supprimé. Les trois noms vivent maintenant à un
seul endroit, `core/config.py`, lus par `run_log.py` qui écrit les logs et par la purge qui les
supprime :

```python
LOG_NAMES_PATTERN = "|".join(
    re.escape(name)
    for name in (LOG_FILE_NAME, SERVE_DATA_LOG_FILE_NAME, SERVE_AI_LOG_FILE_NAME)
)
```
`src/k_b/purge/run_records.py:21-24`

`re.escape` rend littéral le point de `kb.log` : sans lui, `kb_log.2020-01-01` serait accepté.

### Ne lire que deux dossiers, ne suivre aucun lien

`list_files` (`src/k_b/purge/run_records.py:56`) renvoie une liste vide si le dossier manque ou est un
lien. Elle écarte aussi un sous-dossier ou un lien posé dans le dossier. Rien n'est lu hors de
`logs/` et `journals/`.

### Les journaux dans leur dossier

`import-log-<date>.jsonl`, à la racine du dossier de données, devient
`journals/import-journal-<date>.jsonl` (`src/k_b/etl/pipeline.py:63-69`). Le module
`etl/import_log.py` devient `etl/import_journal.py`. Les logs ne changent ni de nom, ni de place,
ni de format.

## Choix faits et options écartées

| Choix | Retenu | Écarté, et pourquoi |
|---|---|---|
| Durée | 6 mois, logs et journaux (Sabine) | 30 jours : sous la recommandation de la CNIL. 30 fichiers : pas une durée |
| Mesure de l'âge | jour lu dans le nom | `mtime` : changé par une copie ou une restauration |
| Rangement | `logs/` et `journals/` (Sabine) | tout dans `logs/` : un journal y aurait recréé la confusion des mots, et les tests de bout en bout, qui gardent `logs/`, auraient gardé les journaux |
| Noms des logs | trois constantes de `core/config.py` | les recopier dans le motif de la purge : un même savoir à deux endroits, un 4e log jamais purgé. `purge/` n'a pas le droit d'importer `commands/` (`tests/architecture/test_layers.py:257`) |
| Moment | fin de `kb import` | une rotation à chaque commande : `backupCount` ne compte pas des jours |
| Nom de la constante | `RECORD_RETENTION_MONTHS` (constat 10) | `LOG_RETENTION_MONTHS` : elle règle aussi les journaux |
| `/security-review` | non lancée (proposé dans le plan) | deux dossiers nommés, des noms vérifiés strictement, aucun lien suivi, aucune entrée externe |

## Preuve

| Test ou sortie | Ce que ça démontre |
|---|---|
| `test_a_log_or_a_journal_leaves_after_6_months_and_stays_at_6_months` | 6 mois et un jour : supprimé. 6 mois pile, ou moins : gardé. Vaut pour les trois logs et pour un journal |
| `test_any_other_name_is_never_deleted` (14 cas) | log en cours, nom sans date, date impossible, temporaire caché, nom de l'autre dossier, ancien nom, `incident.log.<jour>`, `kb_log.<jour>` : gardés |
| Test rouge du constat 8, avant la correction | `assert 1 == 0` : `incident.log.2020-01-01` était supprimé |
| Mutation : `kb-serve-ai.log` retiré de la liste | 1 test en échec |
| Mutation : `re.escape` retiré | 1 test en échec (`kb_log.2020-01-01`) |
| `test_a_folder_and_a_link_are_never_deleted_nor_followed`, `test_a_link_in_place_of_a_folder_is_not_followed` | ni dossier ni lien supprimé, aucun lien suivi |
| `test_the_bound_is_computed_in_utc_whatever_the_time_zone_given` | la borne est calculée en UTC |
| `test_a_rotation_deletes_no_log_file_only_the_purge_does` (`tests/commands/test_run_log.py`) | 40 anciens logs survivent à une rotation |
| `test_the_log_gives_numbers_never_a_name` | le log donne un nombre, jamais un nom de fichier |
| `uv run pytest` : 3 367 verts ; ruff, format, `mypy --strict` verts | rien d'autre n'est cassé |

## Ce que tu dois pouvoir défendre

1. **Pourquoi pas `backupCount=180` ?** Il compte des fichiers, pas des jours, et ne supprime qu'à
   une rotation. La durée n'est donc pas garantie (`run_log.py:56`).
2. **Pourquoi 6 mois ?** C'est le bas de la fourchette de la CNIL pour une journalisation (six mois à
   un an), et la durée du brut. C'est une recommandation, pas une obligation : l'appliquer aux
   logs techniques est un choix de K-B, écrit dans le registre (étape 11).
3. **Un fichier que je dépose dans `logs/` peut-il disparaître ?** Non, seuls les trois noms que K-B
   écrit sont supprimés (`run_records.py:21-31`, test `incident.log`).
4. **Et si je n'importe plus ?** Rien n'est purgé : c'est une limite écrite dans le registre
   (« Limites de la purge »).
5. **Pourquoi lire la date dans le nom ?** Une copie ou une restauration change le `mtime`, pas le
   nom. Le nom, c'est K-B qui l'écrit, à la rotation ou à l'import.

## Zones non vérifiées

- La rotation au lancement suivant suit le `mtime` du log en cours : c'est le comportement de
  `TimedRotatingFileHandler`, tenu par `test_a_log_file_of_an_earlier_utc_day_is_rotated_at_the_first_line`.
  Le code de CPython n'a pas été relu pour cette PR.
- La recommandation de la CNIL : la page de présentation a été lue, pas le PDF complet.
- La 1re `/code-review` (medium) a été coupée par le quota : une partie du code n'a pas été relue.

## Ce qui reste

- Les limites écrites au registre : sans `kb import`, rien n'est purgé ; le log en cours d'un serveur
  arrêté et jamais relancé n'est jamais daté ; un temporaire caché laissé dans `journals/` par un
  arrêt brutal reste ; les anciens `import-log-*.jsonl` d'avant `journals/` sont à retirer à la main.
- Les règles de `.claude/` (`conventions.md`) citent encore `import-log.jsonl`, `LOG_FILES_KEPT` et
  `import_log` : Sabine les modifie, le texte est dans la PR.
- Le tracé de bout en bout, avec l'envoi des logs à un outil de suivi : la cible de Sabine, que
  #267 ne code pas ; #281 (suivre une demande de l'API IA jusqu'à l'API de données) en porte une
  partie.
