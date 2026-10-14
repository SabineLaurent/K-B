# Journaux horodatés en UTC, gardés dans un fichier, et n'écrivant que l'observé

- **Date** : 2026-10-14
- **Branche** : `feat/log-timestamps-and-file`
- **Issue** : #134
- **Fichiers principaux** : `src/k_b/cli.py`, `src/k_b/core/quoting.py`, `src/k_b/etl/extract.py`,
  `src/k_b/etl/sources/tldr.py`, `src/k_b/etl/sources/github_releases.py`,
  `src/k_b/etl/sources/github_advisories.py`, `.claude/rules/conventions.md` (règles 2 et 3)
- **Série** : la journalisation sur la sortie d'erreur est née avec la collecte TLDR
  (`2026-10-04-collecte-tldr-pages-brutes.md`, `configure_logging`), remplacée ici par `logging_to`.

## 1. Le pourquoi

Avant cette PR, les lignes de journal n'avaient pas de date et n'allaient que sur la sortie
d'erreur. Elles étaient donc perdues à la fermeture du terminal. Deux lignes supposaient au lieu
de dire l'observé (« some may be missing »), et l'échec d'une page TLDR était journalisé deux fois.

Le journal de fonctionnement sert à relire un lancement après coup : quand il a eu lieu, ce qui a
réussi, ce qui a échoué et pourquoi. Pour cela, il lui faut :
- une date que l'on peut comparer d'une machine à l'autre ;
- un fichier qui survit au terminal ;
- une seule ligne par échec ;
- des valeurs citées sans risque d'écrire une fausse ligne.

## 2. Le comment

### 2.1 Une date en UTC, avec sa zone

`src/k_b/cli.py:76-78` :

```python
formatter = logging.Formatter(LOG_LINE_FORMAT, datefmt=DATABASE_DATE_FORMAT)
# The Z of the format says UTC: the time is read in UTC, not in local time.
formatter.converter = time.gmtime
```

- `%(asctime)s` (`cli.py:55`) est formaté par `Formatter.formatTime`. Celle-ci calcule l'heure avec
  `self.converter`, qui vaut `time.localtime` par défaut, puis applique `datefmt` avec `strftime`.
- Remplacer `converter` par `time.gmtime` sur **cette** instance fait lire l'heure en UTC.
- `datefmt` est `DATABASE_DATE_FORMAT` (`database/dates.py:6`, `%Y-%m-%dT%H:%M:%SZ`), le format
  des dates de la base. Le `Z` y est écrit en dur : il n'est vrai que parce que l'heure est lue en
  UTC.
- Avec un `datefmt`, `logging` n'ajoute pas les millisecondes.

Une ligne ressemble donc à ceci :

```
2026-10-14T14:41:29Z ERROR k_b.cli: …/k-b.sqlite does not exist; create it with kb create-db
```

**Pourquoi l'UTC et le Z** : c'est la décision de Sabine du 2026-10-12, d'après l'OWASP (« Log date
and time (international format) »). Une heure locale sans zone est ambiguë. Elle change avec
l'heure d'été et ne se compare pas aux dates de la base, qui sont en UTC. Le `Z` dit la zone dans
la ligne même.

### 2.2 Un fichier tourné chaque jour, ouvert avant la commande

`src/k_b/cli.py:69-75` :

```python
file_handler = TimedRotatingFileHandler(
    log_path,
    when="midnight",
    utc=True,
    backupCount=LOG_FILES_KEPT,
```

- Le fichier est `<KB_DATA_DIR>/logs/kb.log` (`cli.py:54`).
- À minuit UTC, `logging` le renomme en `kb.log.AAAA-MM-JJ` et en ouvre un neuf.
- Il garde `LOG_FILES_KEPT` = 30 fichiers tournés (`core/config.py:31`, à côté des autres durées
  de conservation) et supprime les plus vieux.
- La rotation marche aussi entre deux lancements courts de `kb` : à l'ouverture, la prochaine
  rotation est calculée à partir de la date de modification du fichier existant (source de
  Python 3.13, `logging/handlers.py:284-288`).

`logging_to` (`cli.py:59`) est un *context manager* :
- en entrée, il attache au logger racine deux gestionnaires, la sortie d'erreur et le fichier,
  avec le même formateur ;
- en sortie, il les retire et les ferme.
Il les retire parce que les tests appellent `cli.main` des dizaines de fois dans le même
interpréteur : sans retrait, les gestionnaires s'accumuleraient.

`main` (`cli.py:113-129`) ouvre le journal **avant** la commande. Une `OSError` à l'ouverture
donne `error: log file not opened: …` puis le code 2, et aucune commande n'est lancée. C'est
« échouer fermé » : une collecte sans son journal perdrait justement les échecs que le journal
doit garder. Ce message reste un `print`, puisqu'il n'y a pas encore de journal.

### 2.3 Un échec journalisé une fois, là où il est traité

L'échec d'une source est traité dans `etl/extract.py`, qui le rattrape et l'inscrit dans
`errors_by_source`. C'est là qu'il est journalisé. `tldr.py` ne journalise plus : il ajoute à
l'exception une **note** (Python 3.11 et plus), puis relève l'exception (`tldr.py:81`) :

```python
error.add_note(f"{self.name} {day}, from {page_url}")
```

`extract.py:48-58` met sur la ligne datée le type de l'erreur, son message et ses notes, chacun
cité par `quote_value`. La trace de Python suit cette ligne :

```python
logger.exception(
    "collection failed for source %r: %s %s%s",
    source.name,
    type(error).__name__,
    quote_value(str(error)),  # noqa: TRY401
```

Le module générique ne sait rien de TLDR : il recopie les notes de n'importe quelle source. Le
jour et l'URL de la page restent donc sur la ligne datée, comme avant (`tldr.py:79` sur `main`).

Les erreurs que la CLI traite (base absente ou verrouillée, état de collecte invalide…) passent
désormais par `logger.error` au lieu de `print` : elles sont datées et entrent dans le fichier.
Une exception que `kb` ne traite pas est journalisée par `main` (`cli.py:125-129`), qui renvoie
ensuite 1 sans relever l'exception, sinon Python aurait affiché la trace une seconde fois.

### 2.4 Le mesuré à la place du supposé

`github_releases.py:74-83` (et l'équivalent dans `github_advisories.py`) :

```
anthropics/claude-code: 3 releases read, page size 3; oldest published at
2026-09-29T19:27:30+00:00, after the last collection at 2026-09-29T00:00:00+00:00; next pages not read
```

« some may be missing » était une déduction. On observe seulement ceci :
- la page est pleine (nombre lu, taille de page) ;
- sa date la plus ancienne est postérieure à la dernière collecte ;
- les pages suivantes n'ont pas été lues.
La ligne donne ces trois mesures. Conclure qu'il manque des éléments revient au lecteur
(`code.md`, « Journalisation »). Pour la même raison, le commentaire de `schema.sql:180` et la
docstring de `items.py:78` ont été reformulés.

### 2.5 Citer une valeur sans écrire une fausse ligne

`src/k_b/core/quoting.py:7-10` :

```python
def quote_value(value: object) -> str:
    """The value with its line breaks and control characters escaped by repr, cut to a fixed
    length: it cannot write a line of its own in a log."""
    return repr(value)[:MAX_QUOTED_VALUE_LENGTH]
```

Un nom de dossier `x\n2026-…Z ERROR …` écrit tel quel produirait une fausse ligne datée dans un
fichier gardé 30 jours. `repr` échappe le `\n`, et la troncature borne la longueur. Le motif
`repr(...)[:100]` existait en trois copies (`tldr`, `gh_archive`, et celle ajoutée dans
`transform`) ; il vit désormais à un seul endroit. Il sert aussi aux noms de dossier de
`transform.py`, au message et aux notes d'`extract.py`, et aux valeurs du fichier d'état
(`raw_store.py:71`, `items.py:127`).

## 3. Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Heure UTC avec `Z` | attribut d'instance `converter = time.gmtime` et `datefmt` de la base : documenté (cookbook Python), une connaissance à un seul endroit | sous-classe `UTCFormatter` (une classe pour un attribut) ; `Formatter.converter` au niveau de la classe (change tous les formateurs du processus, ceux de pytest compris) |
| Fichier | `logs/kb.log` dans le dossier de données, séparé des journaux d'import | `kb.log` à la racine (jusqu'à 31 fichiers mêlés aux `import-log-*.jsonl`) |
| Rotation et conservation | `TimedRotatingFileHandler`, minuit UTC, 30 fichiers (décision de Sabine, borne RGESN 1.6) | fichier unique (grossit sans fin) ; rotation par taille (borne le volume, pas la durée) ; un fichier par jour nommé à la main (refait ce que fait `logging`) |
| Fichier non ouvrable | code 2, aucune commande lancée | continuer sur la seule sortie d'erreur (les échecs seraient perdus) |
| Mise en place | *context manager* qui ajoute puis retire ses gestionnaires | `basicConfig` (ne fait rien sous pytest, et le fichier ne serait jamais fermé) ; `basicConfig(force=True)` (fermerait les gestionnaires de pytest) |
| Échec TLDR | une note, journalisée par `extract.py` | une nouvelle exception enveloppante (le résumé `failed (<type>)` perdrait `HTTPError`) ; garder le log de `tldr` (extract traite toutes les sources) |
| Exception non traitée | journalisée par `main`, code 1, pas relevée | `raise` après journalisation (trace affichée deux fois) |
| Ctrl-C | pas de ligne : c'est un acte de l'utilisatrice ; tout plantage laisse une ligne, donc une collecte sans ligne d'erreur a été interrompue (décision de Sabine) | `except KeyboardInterrupt` qui écrit une ligne |
| Journal d'import | inchangé : déjà ISO 8601 UTC avec `Z` (`import_log.py:50`) | — |

**Décisions de Sabine écrites ici** :
- **Q1** : la règle « chaque ligne est horodatée » vaut **par enregistrement**. La trace d'une
  erreur suit sa ligne datée et lui appartient.
- **Q2a** : le message d'une exception, dans la trace, est gardé tel quel, sans troncature ni
  échappement. Le corriger demanderait un formateur de trace maison, et `/security-review` n'a
  rien relevé au-dessus du seuil. La ligne datée, elle, cite le message par `quote_value`.
- **Règle 2** : le journal de fonctionnement, ajouté ligne à ligne par `logging`, est hors de la
  règle d'écriture atomique : il n'est jamais lu comme une page.
- **OpenTelemetry** est mis de côté pour l'instant, pas rejeté. Il sert à suivre une requête à
  travers plusieurs services ; K-B est aujourd'hui un seul programme local, pour qui un fichier
  suffit. Il sera reconsidéré quand plusieurs services de K-B s'appelleront.

**Pourquoi deux journaux qui ne se mélangent pas** : ils ne décrivent pas la même chose.
- Le journal d'import (`import-log-<date>.jsonl`) décrit **l'état de la base** : ses rejets et ses
  écarts n'ont de sens que si l'écriture a eu lieu. Il n'est écrit que si l'import va au bout.
- Le journal de fonctionnement décrit **le lancement**. Un échec y est justement ce qu'on vient
  relire (OWASP : journaliser les échecs), donc il garde aussi les lancements qui échouent.

## 4. Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_log_line_is_dated_in_utc_with_its_zone` (sous-processus en `TZ=Asia/Kolkata`) | la ligne suit `AAAA-MM-JJTHH:MM:SSZ`, et son heure lue en UTC tombe entre l'avant et l'après du lancement : ce n'est pas l'heure locale |
| `test_an_error_log_line_is_written_to_the_log_file_in_the_same_format` | une ligne ERROR de `kb collect` est dans `logs/kb.log` et identique sur la sortie d'erreur |
| `test_an_error_handled_by_kb_is_a_dated_log_line_of_the_log_file` | une erreur traitée par la CLI est datée et dans le fichier |
| `test_an_exception_kb_does_not_handle_is_logged_once_and_exits_1` | code 1, et la trace une seule fois sur la sortie d'erreur |
| `test_collect_refuses_to_run_when_the_log_file_cannot_be_opened` | code 2, rien de collecté |
| `test_a_log_file_of_an_earlier_utc_day_is_rotated_at_the_first_line` | un `kb.log` daté de la veille devient `kb.log.<veille>` à la première ligne |
| `test_a_failed_tldr_page_is_logged_once_with_its_day_and_url` | un seul enregistrement ERROR pour une page TLDR en échec, avec type, message, jour et URL (sur `main` : deux) |
| `test_the_error_and_the_notes_of_a_failed_source_are_quoted_escaped`, `test_quoting.py`, `test_the_name_of_a_folder_of_no_source_kind_is_logged_escaped_and_truncated`, `test_a_long_source_name_and_date_of_the_state_are_quoted_cut_in_the_refusal` | un `\n` reçu ne produit pas de nouvelle ligne ; une valeur longue est coupée |
| `grep -rniE "may be\|maybe\|probably\|perhaps" src/k_b` | vide |
| `kb import` réel, dans un dossier temporaire, à 16 h 41 heure locale | `2026-10-14T14:41:29Z ERROR k_b.cli: …` et `… INFO k_b.etl.transform: … 'unknown_folder'`, sur la sortie d'erreur et dans `logs/kb.log` |

## 5. Ce que tu dois pouvoir défendre

1. **Pourquoi pas l'heure locale ?** Elle change avec l'heure d'été et ne dit pas sa zone. Le
   `Z` rend la ligne comparable aux dates de la base et d'une machine à l'autre (`cli.py:76-78`).
2. **Que se passe-t-il si `logs/` n'est pas inscriptible ?** Au lancement : code 2, rien n'est
   lancé (`cli.py:116-122`). En cours de route, par exemple quand la rotation échoue : `logging`
   écrit « Logging error » sur la sortie d'erreur et la commande continue, mais les lignes
   manquent au fichier. Cette limite est connue (section 6).
3. **Pourquoi l'échec TLDR n'est-il plus journalisé dans `tldr.py` ?** Il est traité dans
   `extract.py` : c'est là qu'il devient un résultat (`errors_by_source`). Un échec journalisé à
   deux endroits apparaîtrait deux fois. La note transporte le jour et l'URL jusqu'au point de
   traitement.
4. **Où est la sécurité ?** `quote_value` empêche une valeur reçue d'écrire une fausse ligne
   (OWASP, injection de journal). Le fichier ne contient ni secret (le jeton GitHub ne passe que
   dans un en-tête) ni auteur, sauf le cas signalé en section 7.
5. **Pourquoi le résultat de `kb import` n'est-il pas dans le fichier ?** La règle 3 sépare le
   résultat d'une commande (`print`, sur la sortie standard) du déroulé (`logger`). Le fichier
   garde le déroulé, réussites et échecs.

## 6. Zones non vérifiées

- **Rotation par plusieurs processus** : deux `kb` qui tournent le même jour le même fichier.
  Je ne l'ai pas vérifié dans la documentation de `logging` pendant cette session ; la relecture
  de code décrit un scénario où un processus écrit dans `kb.log.<veille>`, non reproduit.
- **Rotation qui échoue en cours de route** : lu dans `handlers.py` par l'architecte, non
  reproduit.
- **Droits du fichier** : ceux d'`open()` sous l'umask (0644 en général), non mesurés sur
  d'autres machines.
- **Messages venus du serveur** : je n'ai pas vérifié qu'une URL de redirection ou une raison
  HTTP ne peut pas porter de caractère de contrôle. Sur la ligne datée, `quote_value` les échappe
  quand même ; dans la trace, ils sont écrits tels quels (Q2a).
- **Page de l'OWASP Logging Cheat Sheet** : WebSearch n'a rendu que des copies de la page pour
  le passage « Log date and time (international format) » ; la page officielle n'a pas été lue
  en entier.

## 7. Ce qui reste

- **Auteur dans une erreur de validation** : une `ValidationError` sur `Item` porte
  `input_value`, et un auteur refusé y apparaît en clair. Ce texte entre dans le journal
  d'import, dans la sortie d'erreur (`transform.py`, `reject`) et, depuis cette PR, dans
  `logs/kb.log`. Issue créée à la suite de #134.
- **Codes de sortie** : 0, 1 et 2 sont des nombres bruts dans `cli.py`, et leur convention n'est
  écrite nulle part. Issue créée à la suite de #134.
- **Plusieurs processus** (API, #184) : un fichier par processus, ou un autre gestionnaire.
- **Marque de coupure** dans `quote_value` (par exemple `… (312 characters)`) : idée gardée sans
  issue.
- **Rejet arXiv journalisé dans la source** (`arxiv.py:144`, règle 1) : couvert par #61.

## Sources

| Page | Ce qu'elle fonde | Consultée le |
|---|---|---|
| Python 3.13, *Logging Cookbook*, « Formatting times using UTC (GMT) via configuration » (`UTCFormatter`, `converter = time.gmtime`), par Context7 : https://docs.python.org/3.13/howto/logging-cookbook.html | l'heure UTC par `converter` | 2026-10-14 |
| Python 3.13, `logging.handlers`, `TimedRotatingFileHandler`, par Context7 : https://docs.python.org/3.13/library/logging.handlers.html#timedrotatingfilehandler | rotation à minuit UTC, `backupCount` | 2026-10-14 |
| Source de Python 3.13.13 installée, `logging/handlers.py:284-288` (prochaine rotation calculée depuis la date de modification du fichier) | rotation entre deux lancements courts | 2026-10-14 |
| OWASP, *Logging Cheat Sheet* : https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html (passage lu par WebSearch, sur des copies de la page) | date au format international ; journaliser les échecs ; nettoyer les données d'événement contre l'injection | 2026-10-14 |
| OWASP, *Logging Vocabulary Cheat Sheet* : https://cheatsheetseries.owasp.org/cheatsheets/Logging_Vocabulary_Cheat_Sheet.html | ISO 8601 avec le décalage UTC | 2026-10-14 |
