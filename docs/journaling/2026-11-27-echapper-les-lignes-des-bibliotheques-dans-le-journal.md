# Échapper dans le journal de `kb` le message d'une ligne écrite par une bibliothèque

- **Date** : 2026-11-27
- **Branche** : `fix/escape-library-log-lines`, sur `4d593c83` : `e063e047` (le code, ses tests et la doc), `e1e60641`
  (deux phrases de la fiche rendues exactes après la revue), `912a96f5` (cette note et l'entrée du journal ADR), puis
  la phrase de la fiche sur l'échec d'un envoi à Grafana et la relecture de cette note
- **Issue** : #441
- **Fichiers principaux** : `src/k_b/commands/run_log.py`, `tests/commands/test_run_log.py`,
  `documentation/monitorage.md` (section « Lire une ligne ») ; renvois `run_log.py:` remis à jour dans
  `documentation/collecte.md`, `architecture.md`, `api-ia.md` et `api-donnees.md`
- **Série** : suite de [Journaux horodatés et fichier de journal](2026-10-14-journaux-horodates-et-fichier-de-journal.md)
  et de [Documenter les journaux de l'application](2026-11-11-documenter-les-journaux-de-l-application.md)

La liste des commits fournie à l'écriture de cette note remontait dans l'historique de `main`. Les commits
ci-dessus sont les seuls de la branche (`git log origin/main..HEAD`), et la note ne traite que d'eux.

## Le pourquoi

Le journal de `kb` est la trace de chaque commande, de `kb collect` aux deux API : une ligne datée par événement, sur
la sortie d'erreur et dans `<KB_DATA_DIR>/logs/kb.log`. En ligne, la sortie d'erreur part dans Log Analytics, et c'est
là qu'on lit l'échec d'un job. Chaque ligne a la forme `<date> <niveau> <module>: <message>`.

`kb` cite lui-même chaque valeur qu'il journalise par `quote_value` : tronquée, retours à la ligne et caractères de
contrôle échappés (règle 3 de `.claude/rules/conventions.md`). Les bibliothèques qui tournent dans le même processus
(uvicorn, OpenTelemetry, le client BigQuery, httpcore…) écrivent par les mêmes sorties, et leurs messages passaient
tels quels. Une bibliothèque qui recopie à WARNING le texte d'une réponse de serveur pouvait y laisser un retour à la
ligne suivi d'une fausse ligne datée, `… ERROR k_b.cli: …`. Dans le fichier comme dans Log Analytics, cette ligne se
lit comme une vraie ligne de `kb` : c'est l'injection de journal que nomme l'OWASP (*Logging Cheat Sheet*, « Perform
sanitization on all event data to prevent log injection attacks »).

#412 avait déjà tenu `azure` et `urllib3` à ERROR (`LIBRARY_LOG_LEVELS`) : à WARNING, `azure` cite le texte d'une
réponse, et `urllib3` peut citer une URL entière, celle d'un blob (`src/k_b/commands/run_log.py:41-48`).
Une liste ne couvre que les bibliothèques qu'on a pensé à y mettre : #441 demande une seule règle, pour toutes.

## Le comment

### Une seule règle, au formateur que partagent les deux sorties

`logging_to` pose sur le logger racine un gestionnaire pour la sortie d'erreur et, sauf `KB_LOG_TO_FILE=false`, un
pour le fichier, et leur donne le même formateur, `TracedFormatter` (`src/k_b/commands/run_log.py:82-107`). C'est là que la règle s'écrit, une fois (`src/k_b/commands/run_log.py:127-134`) :

```python
def format(self, record: logging.LogRecord) -> str:
    trace_id = read_current_trace_id()
    record.trace_field = "" if trace_id is None else f" trace_id={trace_id}"
    if not is_logged_by_kb(record):
        record = with_message_quoted(record)
    return super().format(record)
```

Le formateur posait déjà l'identifiant de trace d'une requête en cours. Il formate désormais une ligne de
bibliothèque à partir d'une copie dont le message est cité, puis laisse `logging.Formatter` faire le reste : la date
en UTC, le niveau, le nom du logger.

### Qui est une bibliothèque : tout logger hors de `k_b`

Chaque module de K-B journalise par `logging.getLogger(__name__)`, ou par `k_b.cli` pour la ligne de commande : son
nom commence par `k_b.`. Tout autre nom vient d'une bibliothèque (`src/k_b/commands/run_log.py:137-139`) :

```python
def is_logged_by_kb(record: logging.LogRecord) -> bool:
    return record.name == KB_LOGGER_NAME or record.name.startswith(f"{KB_LOGGER_NAME}.")
```

Le point compte : un `startswith("k_b")` seul laisserait passer, sans le citer, un logger nommé `k_b_library`. Le test
paramétré le tient (`tests/commands/test_run_log.py:283-290`).

### La copie, et non l'enregistrement d'origine

Un enregistrement (`LogRecord`) est un seul objet, remis tour à tour à chaque gestionnaire du logger racine. En tests,
pytest y pose le sien (`caplog`), qui garde l'objet lui-même. Si le formateur réécrivait le message en place, chaque
gestionnaire servi après lui recevrait le texte cité, et pytest le relirait ainsi après coup. La copie évite cet effet
de bord (`src/k_b/commands/run_log.py:142-151`) :

```python
quoted_record = logging.makeLogRecord(record.__dict__)
quoted_record.msg = quote_value(
    record.getMessage(), MAX_QUOTED_LIBRARY_MESSAGE_LENGTH
)
quoted_record.args = None
```

`makeLogRecord` crée un enregistrement neuf et y recopie les attributs de l'original : son nom, son niveau, son heure,
et le `trace_field` posé juste avant. `getMessage()` assemble le message et ses arguments (`"the server says: %s"` et
sa valeur). Le texte assemblé est cité, puis `args = None` : `logging` ne tente pas un second assemblage, et un `%`
venu du serveur dans le texte cité reste un caractère.

### Citer par `quote_value`, à 300 caractères

`quote_value` est la fonction unique de la règle 3 : `repr(value)[:max_length]` (`src/k_b/core/quoting.py:16-19`).
`repr` d'une chaîne échappe tout caractère non imprimable : `\n`, `\r`, les caractères de contrôle, les contrôles
bidirectionnels, les séparateurs de ligne Unicode. Le message tient donc sur sa ligne. La longueur est une constante
nommée (`src/k_b/commands/run_log.py:66-68`) :

```python
# The length the message of a line of a library is cut to, quotes and escapes included: the line
# is the only copy of the message, as for the failure of a source (etl/extract.py).
MAX_QUOTED_LIBRARY_MESSAGE_LENGTH = 300
```

Une ligne de bibliothèque n'a pas d'autre copie que le journal, comme l'échec d'une source sans sa trace, que
`etl/extract.py` coupe à 300 pour la même raison (`MAX_QUOTED_FAILURE_LENGTH`). Les deux constantes restent séparées :
`commands/` n'importe pas `etl/extract.py`, car `etl/pipeline.py` est sa seule porte vers les deux parcours (règle 5
de `conventions.md`), et elles pourraient changer pour des raisons différentes.

### Ce qui se voit dans le journal

Une ligne de bibliothèque garde sa forme, avec son message cité. Les deux lignes suivantes sont sorties de
`logging_to` dans un interpréteur : la première par le logger `uvicorn.error` et le texte qu'uvicorn y écrit au
démarrage (`uvicorn/lifespan/on.py:62`), la seconde par le message du test du critère de fin.

```text
2026-11-26T23:03:50Z INFO uvicorn.error: 'Application startup complete.'
2026-11-26T23:03:50Z WARNING a.library: 'the server says: refused\n2026-11-26T20:00:00Z ERROR k_b.cli: kb stopped by SIGTERM'
```

La fausse ligne est devenue une partie du message, `\n` compris. Les lignes de l'exporteur OpenTelemetry, dont `QuotingFilter`
(`src/k_b/ai_api/connectors/metrics_export.py:251-276`) cite déjà chaque argument texte et réduit une exception à son
type, sont citées une seconde fois. Le
message d'un échec d'envoi, sorti de même de `logging_to` avec `QuotingFilter` posé, une fois avec une raison sans `"`,
une fois avec une raison qui en porte :

```text
2026-11-26T23:08:37Z ERROR opentelemetry.exporter.otlp.common.http: "Failed to export 'metrics' batch code: 401, reason: 'Unauthorized'"
2026-11-26T23:08:37Z ERROR opentelemetry.exporter.otlp.common.http: 'Failed to export \'metrics\' batch code: 401, reason: \'{"status":"error"}\''
```

`repr` choisit ses guillemets selon le message : quand celui-ci porte à la fois `'` et `"`, il échappe les `'`. La fiche
du monitorage citait `Failed to export 'metrics' batch code: 401`, qui ne se lit plus tel quel dans le second cas : elle
cite désormais `Failed to export … batch code: 401`, qui se lit dans les deux.

La fiche du monitorage le dit, section « Lire une ligne ». Comme le changement décale les lignes de `run_log.py`, ses
renvois `run_log.py:` sont remis à jour dans cinq fiches, dont plusieurs pointaient déjà une ligne trop haut ou trop
bas. L'autre texte d'une bibliothèque que cite une fiche, `address already in use` d'uvicorn
(`documentation/utilisation.md:221`), se lit tel quel dans le message cité.

## Choix faits et options écartées

| Choix | Retenu parce que | Écarté |
|---|---|---|
| Un `Formatter` | les deux sorties le partagent déjà, et il décore déjà l'enregistrement (`trace_field`) : une seule place | un `logging.Filter` par gestionnaire : depuis Python 3.12, il peut rendre une copie au lieu de modifier en place, mais c'est un second objet à poser sur chaque gestionnaire |
| Une copie de l'enregistrement | les autres gestionnaires (pytest, et tout gestionnaire posé plus tard) reçoivent l'enregistrement tel que la bibliothèque l'a écrit | un filtre ou un formateur qui réécrit `msg` en place : effet de bord sur tous les gestionnaires servis après lui |
| Citer les seuls loggers hors de `k_b` | `kb` cite déjà ses valeurs : citer ses lignes les citerait deux fois et changerait chaque ligne de `kb` | tout citer, `k_b.*` compris |
| Une règle pour toutes les bibliothèques | aucune liste à tenir : une bibliothèque ajoutée est couverte d'office (le texte de #441) | étendre `LIBRARY_LOG_LEVELS` : une liste à tenir, bibliothèque par bibliothèque, et le niveau de chacune à vérifier à l'essai, comme pour `azure.identity` (#412) |
| 300 caractères | la ligne est la seule copie du message, comme l'échec d'une source | 100, le défaut de `quote_value`, fait pour une seule valeur, quand une ligne de bibliothèque porte un message entier, qui cite lui-même ses valeurs ; aucune coupe : contraire à la règle 3 |
| Garder `QuotingFilter` | il fait ce que le formateur ne fait pas : il cite chaque argument texte à 100, réduit une exception à son type et retire la trace de l'exporteur | le retirer : la trace de l'exporteur reviendrait dans le journal |
| Le message seul, pas la trace d'une exception | la règle 3 veut que la trace suive sa ligne datée, sur ses lignes : la changer touche aussi les traces de `kb` ; c'est l'objet de #725 | échapper toute la sortie d'un enregistrement de bibliothèque, trace comprise : une trace d'uvicorn (« Exception in ASGI application ») deviendrait une seule ligne de 300 caractères, illisible pour qui cherche la cause |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_line_break_in_what_a_library_logs_writes_no_line_of_its_own` (`tests/commands/test_run_log.py:233`) ; avant le code, il échouait : `ValueError: too many values to unpack (expected 1)`, deux lignes dans `kb.log` | le critère de fin de #441 : `kb.log` et la sortie d'erreur gardent une seule ligne, la même, message cité et `\n` échappé |
| `test_what_a_library_logs_is_cut_to_300_characters` (`:253`) ; avant le code, la ligne gardait ses 1 000 `x` | la coupe à 300, guillemet d'ouverture compris |
| `test_the_record_of_a_library_is_left_as_it_is_for_the_other_handlers` (`:261`) ; avec une réécriture en place simulée dans le processus : `1 failed` | la copie : `caplog` relit le message d'origine |
| `test_only_a_line_of_kb_keeps_its_message_as_kb_wrote_it` (`:283`), trois cas ; avant le code, le cas `k_b_library` échouait | `k_b` et `k_b.test` gardent leur message, `k_b_library` est cité |
| `uv run pytest` : 5866 passed, 365 deselected ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` : verts | rien d'autre ne casse : les tests qui lisent une ligne de bibliothèque la cherchent par une partie de son texte (`tests/ai_api/test_serve_ai.py:520`, `:552`) ou par `record.getMessage()`, que le formateur ne change pas (`tests/ai_api/test_metrics_export.py:468`, `tests/ai_api/test_trace_export.py:253`) |
| `grep` d'`infra/` et d'`observability/` | aucune requête de Log Analytics ni alerte ne lit le texte d'une ligne de bibliothèque ; les requêtes d'`infra/README.md` filtrent par `JobName` |

## Ce que tu dois pouvoir défendre

1. **Pourquoi dans le formateur, et pas dans un filtre ?** Les deux sorties de `kb` partagent déjà ce formateur : la
   règle s'écrit à un seul endroit et vaut pour les deux. Un filtre devrait être posé sur chaque gestionnaire, et un
   filtre qui réécrit l'enregistrement en place le change pour tous les autres (`run_log.py:127-134`).
2. **Pourquoi copier l'enregistrement ?** Le même objet passe par chaque gestionnaire du logger racine. Le copier
   laisse aux autres le message d'origine ; le test de `caplog` échoue si on le réécrit en place
   (`run_log.py:142-151`, `test_run_log.py:261`).
3. **Une bibliothèque peut-elle échapper à la règle en se faisant passer pour `kb` ?** Ce que contrôle un serveur, c'est
   le texte d'un message, pas le nom du logger, que fixe le code de la bibliothèque. Seul du code déjà chargé dans le
   processus pourrait choisir `k_b.x`, et il pourrait alors écrire dans le fichier directement
   (`run_log.py:137-139`).
4. **Pourquoi 300 et pas 100 ?** 100 est la longueur d'une valeur seule. Une ligne de bibliothèque porte un message
   entier, et c'est sa seule copie, comme le message d'échec d'une source, que K-B coupe déjà à 300
   (`run_log.py:66-68`, `etl/extract.py:38`).
5. **Et la trace d'une exception ?** Elle suit sa ligne datée, sur ses propres lignes (règle 3) : seul le message de
   l'enregistrement est cité. Échapper le texte d'une exception dans sa trace vaut pour `kb` comme pour les
   bibliothèques : c'est #725.

## Zones non vérifiées

- Les sorties réelles d'uvicorn, de psycopg, du SDK Azure ou du client BigQuery : les tests simulent une bibliothèque
  par un logger nommé `a.library`. Le mécanisme ne dépend que du nom du logger et du message, pas de la bibliothèque.
- Les suites `postgresql` et `e2e`, écartées par `uv run pytest`, n'ont pas été lancées sur le Mac. Deux tests
  `postgresql` lisent `kb.log` pour y vérifier l'absence d'une valeur que PostgreSQL cite
  (`tests/commands/test_postgresql_errors_in_logs.py:54-55`, `:74`) : citer un message n'ajoute aucun texte. Le job
  `tests-postgresql` de la CI les lance.
- L'effet sur un gestionnaire OpenTelemetry posé sur le logger racine : K-B n'en pose aucun (`grep addHandler` ne
  trouve que `logging_to`), et ses enregistrements partent par un `Logger` d'OpenTelemetry, hors de `logging`
  (`src/k_b/ai_api/connectors/trace_export.py`).

## Ce qui reste

- **#725** : échapper le message d'une exception dans sa trace, pour `kb` comme pour une bibliothèque, en gardant les
  lignes `File …` de la pile.
- La règle 3 de `.claude/rules/conventions.md` pourrait nommer le formateur comme le second endroit où `quote_value`
  s'applique. `.claude/` est tenu à part : la phrase est proposée, pas écrite.
