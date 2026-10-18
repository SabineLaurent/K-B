# Nommer les codes de sortie de `kb` et arrêter collecte et import sur SIGTERM

- Date : 2026-10-18
- Branche : `feat/named-exit-codes`
- Issue : #193 (« Nommer et documenter les codes de sortie de kb »)
- Fichiers principaux : `src/k_b/cli.py`, `src/k_b/etl/load.py`, `tests/test_cli.py`,
  `tests/etl/test_load.py`, `tests/data_api/test_serve.py`, `tests/conftest.py`, `README.md`,
  `docs/specs-collecte.md`, `docs/ADR/journal-decisions-projet.md`
- Commits : `e418649` (codes nommés, SIGTERM), `a27d490` (journal d'import gardé quand la base a
  validé), `ffae1cd` (corrections des deux revues de code), `1190123` (ADR)

## Le pourquoi

Au POC du 25/10, `kb collect` et `kb import` tournent comme des **jobs** en conteneur : une
exécution qui se termine. Pour qui les lance (à la main, `docker compose`, puis Azure Container
Apps), le **code de sortie** est la seule façon de savoir ce qui s'est passé sans lire le journal.
Jusqu'ici ces codes étaient des chiffres bruts dans `cli.py` (17 `return N`), et leur convention
n'était écrite nulle part ensemble.

Deux manques s'y ajoutaient :

- `kb collect` sortait en 1 dès qu'une source échouait, que les autres aient réussi ou non : on ne
  distinguait pas « rien collecté » de « presque tout collecté ».
- `docker stop` envoie SIGTERM, puis SIGKILL après un délai. Sans gestionnaire, Python meurt
  sur SIGTERM sans exécuter aucun nettoyage, et un processus en PID 1 l'ignore même (règle 6 de
  `poc.md`).

En chemin, un défaut plus ancien est apparu : une interruption reçue **pendant** la validation de
l'import supprimait le journal d'un import pourtant validé. Sabine a décidé de le corriger dans la
même PR (commit à part, `a27d490`).

## Le comment

### 1. Une énumération où chaque code porte son sens

`src/k_b/cli.py:67-75` :

```python
class ExitCode(IntEnum):
    ...
    meaning: str

    def __new__(cls, value: int, meaning: str) -> Self:
        member = int.__new__(cls, value)
        member._value_ = value
        member.meaning = meaning
```

Chaque membre s'écrit `NOM = valeur, "sens"` (par exemple `SUCCEEDED = 0, "the command
succeeded"`). Sans `__new__`, un `IntEnum` recevrait le tuple entier et appellerait
`int(0, "the command succeeded")`, qui échoue. `__new__` sépare la valeur (`_value_`) du sens
(`meaning`). C'est le motif « Coordinate » du guide `enum` de Python. `IntEnum` fait que
`ExitCode.FAILED == 1` et que `sys.exit(ExitCode.FAILED)` sort bien en 1 : les fonctions gardent
leur type de retour `int`.

Les six membres : 0 `SUCCEEDED`, 1 `FAILED`, 2 `NOT_STARTED`, 3 `SERVER_NOT_STARTED` (rendu par
uvicorn, jamais par `kb`, nommé pour que personne ne reprenne sa valeur), 4 `PARTIAL_FAILURE`,
143 `STOPPED_BY_SIGTERM`.

### 2. L'aide générée depuis l'énumération

`src/k_b/cli.py:261-263` :

```python
def describe_exit_codes() -> str:
    lines = [f"  {code.value:>3}  {code.meaning}" for code in ExitCode]
    return "exit codes:\n" + "\n".join(lines)
```

Ce texte devient l'épilogue de `kb --help`. `formatter_class=argparse.RawDescriptionHelpFormatter`
(`cli.py:202`) est indispensable : le formateur par défaut d'`argparse` recolle toutes les lignes
en un seul paragraphe. Le sens de chaque code vit donc à un seul endroit, l'énumération. Le
`README.md` garde les **cas** de chaque commande (quand sort-on en 2 ?), plus détaillés.

### 3. Le code de la collecte : une recette

`src/k_b/cli.py:434-445` :

```python
    if outcome.state_error is not None:
        return ExitCode.FAILED
    if all(error is None for error in errors):
        return ExitCode.SUCCEEDED
    if any(error is None for error in errors):
        return ExitCode.PARTIAL_FAILURE
    return ExitCode.FAILED
```

On la lit dans l'ordre :

1. État de collecte non écrit : échec. La collecte suivante repartira des mêmes dates (#60, #64).
2. Aucune source en échec : succès. Une collecte sans aucune source rend aussi 0, comme avant.
3. Au moins une source a réussi : partiel.
4. Sinon, toutes les sources ont échoué : échec.

### 4. SIGTERM devient une exception, pour `collect` et `import` seulement

`src/k_b/cli.py:277-291` :

```python
    previous_handler = signal.signal(signal.SIGTERM, raise_stopped_by_sigterm)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_DFL if previous_handler is None else previous_handler)
...
def raise_stopped_by_sigterm(signal_number: int, frame: FrameType | None) -> None:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    raise StoppedBySigtermError
```

(La ligne du `finally` est condensée ici ; le code la coupe en quatre.)

- **Le gestionnaire lève une exception.** `StoppedBySigtermError` hérite de `SystemExit`
  (`cli.py:100`). Elle remonte donc à travers tout le code : `collect_all_sources` et `main`
  n'attrapent que `Exception`, et `SystemExit` n'en est pas une. Tous les nettoyages déjà écrits
  pour une exception quelconque s'exécutent en chemin :
  - le `rollback` de l'import et la suppression de son journal (`etl/load.py`) ;
  - la suppression du temporaire (`write_file_atomically`, `except BaseException`, #62).
- **`main` n'attrape que cette sous-classe** (`cli.py:250-253`). Elle journalise
  `kb stopped by SIGTERM` et rend 143. Un `SystemExit` large aurait aussi avalé le
  `sys.exit(3)` d'uvicorn quand `kb serve` ne démarre pas.
- **Ce qui est remis à la sortie.** Le context manager remet le gestionnaire trouvé, car pytest
  lance `kb` des centaines de fois dans le même processus. Il remplace `None` (un gestionnaire
  posé hors de Python, que `signal.signal` refuse) par `SIG_DFL`.
- **Un second SIGTERM est ignoré** (`SIG_IGN`) pendant le nettoyage. Docker enverra de toute
  façon SIGKILL après son délai.
- **`kb serve` garde le gestionnaire d'uvicorn**, qui arrête le serveur proprement.

### 5. Le journal d'import suit l'import qu'il décrit

`src/k_b/etl/load.py:226-237` :

```python
    except BaseException as error:
        if isinstance(error, sqlite3.Error) or connection.in_transaction:
            log_path.unlink(missing_ok=True)
        else:
            logger.info("import committed, log kept: %s", quote_value(log_path.name))
        raise
```

Le journal est écrit **avant** la validation (`commit`). Un fichier inscrit au registre n'est plus
relu, donc un journal perdu après la validation serait perdu pour toujours (décision du
2026-10-12). Avant, toute exception supprimait le journal. Or Python ne lève l'exception d'un
signal qu'**une fois l'appel C du `commit` revenu**, encore dans le `try`. Un SIGTERM reçu pendant
le `commit` supprimait donc le journal d'un import validé. Désormais :

| Ce qui s'est passé | Indice | Journal |
|---|---|---|
| Le `commit` a échoué (SQLite garde ou annule la transaction) | `sqlite3.Error` | supprimé |
| Interruption avant le `commit` | transaction encore ouverte (`in_transaction`) | supprimé |
| Interruption pendant ou après le `commit` | ni l'un ni l'autre | gardé, et dit au journal |

Le nom du journal est cité, pas son chemin : `quote_value` coupe à 100 caractères, et un chemin
long perdrait justement le nom.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Un code partiel (4) pour `kb collect` seul | L'import écrit tout ou rien (une transaction) ; un import avec rejets va au bout et sort en 0. Décision de Sabine, écart à la lettre de #193 | Import avec rejets → 4 : change le sens de 0, et un fichier illisible, relu à chaque import, ferait sortir chaque import en 4. Erreur d'import → 4 : rien n'est écrit, ce n'est pas partiel |
| État non écrit → 1, même si des sources ont réussi | Ce qu'écrivent #60 et #64 ; une panne de disque ou de droits revient au lancement suivant (décision de Sabine) | État non écrit → 4 : contredit #60 et #64 |
| 4 pour l'échec partiel | Première valeur libre après 3 (uvicorn) | 3 (pris par uvicorn) ; 64 à 78 (`sysexits.h`, d'autres sens) ; 23 (propre à rsync) |
| 143 pour SIGTERM | 128 + 15, le code d'un processus tué par SIGTERM : un job lu de l'extérieur garde le même sens qu'un processus tué | 1 : indistinct d'un échec |
| Le sens dans l'énumération (`__new__`) | Un seul endroit, lu par `kb --help` | Un dictionnaire à côté (deux endroits à tenir) ; des commentaires (illisibles par `--help`) |
| `kb --help` généré, le README garde les cas | Un sens écrit une fois ; les cas par commande sont plus détaillés que l'énumération | Le README seul (une seconde copie des sens, qui divergera) |
| Une exception levée par le gestionnaire | Réutilise tous les nettoyages déjà écrits pour une exception, sans toucher à la collecte ni à l'import | Un drapeau consulté par la boucle (chaque étape longue devrait le lire). Le prix de ce choix est écrit en section 7 |
| SIGTERM pour `collect` et `import` seulement | Périmètre de l'issue, validé dans le plan | Toutes les commandes : la règle 6 de `poc.md` le dit, signalé à part |
| Journal supprimé seulement si la base n'a pas validé (`sqlite3.Error` ou transaction ouverte) | Conception de l'architecte de données de time-knight, décision de Sabine | `signal.pthread_sigmask` autour du `commit` (plus de mécanique, Unix et thread principal seulement, mêlée au gestionnaire) ; journal écrit après le `commit` (choix de #105, inversé par #106) ; journal en base (taille L, à rouvrir si un programme lit un jour le journal) |
| Tests de signal dans le processus de pytest, plus un en sous-processus | `signal.raise_signal` est livré avant son retour : déterministe. Le sous-processus prouve le câblage réel (`sys.exit(main())`), comme le demande la règle 6 de `poc.md` | Un sous-processus tué après un délai fixe (dépend de la machine) |
| `dump_database` recopiée dans `test_cli.py` | `tests/etl/test_load.py` importe ses voisins par leur nom nu et ne s'importe pas depuis `test_cli.py` ; deux copies seulement (`code.md` : factoriser à la troisième) | Un module d'aide partagé, sans troisième usage |
| Une fixture `connect_with_factory` dans `tests/conftest.py` | Quatre fermetures recopiaient le corps de `connect_database` : troisième occurrence et au-delà | Garder les fermetures (elles divergeraient de `connect_database`) |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_each_exit_code_keeps_its_value` (`tests/test_cli.py:656`) | Les six valeurs sont figées ; 0, 1 et 2 n'ont pas changé |
| `test_the_server_not_started_code_is_the_one_uvicorn_exits_with` (`:667`) | 3 est bien `uvicorn.config.STARTUP_FAILURE` |
| `test_kb_help_lists_each_exit_code_with_its_meaning_on_its_own_line` (`:671`) | Une ligne par code dans `kb --help` (un texte recollé échouerait) |
| `test_collect_reports_a_failure_but_still_stores_the_other_sources` (`:60`) | Une source en panne, une qui marche : 4 |
| Tests existants `:90`, `:163`, `:350`, `:404`, `:240` inchangés | État non écrit, sources seules en panne, exception non gérée : 1 ; aucune source : 0 |
| `test_a_sigterm_after_the_import_log_is_written_leaves_neither_the_import_nor_its_log` (`:722`) | SIGTERM après l'écriture du journal, avant le `commit` : 143, base identique, aucun journal ni temporaire caché, gestionnaire d'origine remis |
| `test_a_sigterm_once_the_base_has_committed_keeps_the_import_and_its_log` (`:760`) | SIGTERM après le `commit` : 143, import inscrit, journal gardé et daté de cet import, ligne `import committed, log kept`, pas de résumé affiché |
| `test_a_sigterm_during_a_source_stops_kb_collect_and_keeps_the_collection_state` (`:794`) | SIGTERM pendant une source : 143, état inchangé, la source suivante n'est pas lancée |
| `test_kb_collect_sent_sigterm_in_its_own_process_exits_with_143` (`:842`) | Un vrai processus reçoit SIGTERM et sort en 143. Mutation « pas de gestionnaire pour collect » : il sort en -15, et le test échoue |
| `test_serve_exits_with_the_code_of_uvicorn_when_it_does_not_start_and_sets_no_sigterm_handler` (`tests/data_api/test_serve.py:347`) | Le `SystemExit(3)` d'uvicorn traverse `main` intact ; `kb serve` ne pose aucun gestionnaire |
| `test_a_ctrl_c_once_the_base_has_committed_keeps_the_import_and_its_log` (`tests/etl/test_load.py:1041`) | Base et journal identiques, octet pour octet, à ceux d'un import non interrompu |
| `test_a_commit_undone_by_sqlite_leaves_neither_the_import_nor_its_log` (`:1015`) | Un `commit` que SQLite annule lui-même ne laisse pas de journal (la clause `sqlite3.Error`) |
| Deux mutations de la condition de `load.py` | Sans `isinstance(…)`, un test échoue ; sans `in_transaction`, deux échouent |
| Essai hors du dépôt, avec un vrai SIGTERM envoyé d'un autre thread pendant 300 `commit` | 44 fois, l'exception est levée alors que la base est validée et qu'il n'y a plus de transaction : l'hypothèse de la section 5 est observée, pas supposée |
| `grep -cE "return [0-9]+\b\|else [0-9]+\b" src/k_b/cli.py` → 0 (17 au départ) | Plus aucun code de sortie en chiffres |
| `uv run pytest` → 1742 tests verts ; `ruff check`, `ruff format --check`, `mypy --strict` verts | Les contrôles du dépôt |

## Ce que tu dois pouvoir défendre

1. **Pourquoi 143 et pas 1 ?** 143 = 128 + 15 : c'est ce que rapportent un shell et Docker pour
   un processus tué par SIGTERM. Un job arrêté par `docker stop` garde ainsi le sens connu de tout
   opérateur, et n'est pas confondu avec un échec (`cli.py:93-97`).
2. **Pourquoi l'import n'a-t-il pas de code partiel ?** Il écrit tout ou rien, dans une seule
   transaction (`etl/load.py:5-10`). Un rejet est un résultat normal, écrit au journal, et l'import
   sort en 0 (`README.md`, `kb import`).
3. **Que se passe-t-il si SIGTERM arrive pendant le `commit` ?** Python lève l'exception une fois
   le `commit` revenu. La base est validée, il n'y a plus de transaction ouverte : le journal est
   gardé et une ligne le dit (`load.py:231-236`). `kb` sort en 143 : « arrêté par SIGTERM ; ce
   qui a été fait avant est gardé ».
4. **Pourquoi une sous-classe de `SystemExit` et pas un `except SystemExit` ?** Pour que le
   `sys.exit(3)` d'uvicorn traverse `main` sans être pris pour un SIGTERM
   (`tests/data_api/test_serve.py:347`).
5. **Où est la robustesse face au signal lui-même ?** Le gestionnaire passe SIGTERM à `SIG_IGN`
   avant de lever : un second signal n'interrompt pas le nettoyage. L'ancien gestionnaire est
   remis à la sortie. Les tests posent d'abord leur propre gestionnaire, pour qu'un `kb` qui n'en
   poserait pas ne tue pas pytest (`tests/test_cli.py:688`).

## Zones non vérifiées

- **Lever une exception depuis un gestionnaire de signal.** La documentation Python dit qu'une
  telle exception « may be raised after any bytecode instruction ». Elle conseille aux
  applications « complex or require high reliability » de l'éviter. Le choix retenu l'accepte pour
  un job court, mais les fenêtres connues restent :
  - un signal entre la création du temporaire et le `try` qui le supprime (`etl/raw_store.py:60-63`,
    limite écrite dans sa docstring) ;
  - un `commit` refusé suivi d'un signal dans la même instruction : si SQLite a annulé de
    lui-même, le journal reste sans import (limite écrite dans l'ADR).
- **Le cas où SQLite annule lui-même un `commit`** (disque plein, I/O) n'a pas été reproduit sur
  une vraie base, faute de VFS dans la bibliothèque standard. Le test le simule (`rollback` puis
  `OperationalError`).
- **`kb serve` en PID 1.** uvicorn remet `SIG_DFL` puis renvoie SIGTERM
  (`uvicorn/server.py:339-349`, 0.54.0), qu'un PID 1 ignore : `kb serve` sortirait alors en 0, pas
  en 143. Lu dans la source, non vérifié en conteneur.
- **`uv run` en conteneur** : relaie-t-il SIGTERM à `kb` ? Non vérifié. Le test en sous-processus
  lance l'interpréteur directement, pas par `uv run` ni en PID 1.
- **La phrase du manuel GNU Bash** n'a pas pu être relue sur la page le 18/10 (HTTP 429). Elle est
  citée d'après le résultat de la recherche du jour.

## Ce qui reste

- **SIGTERM pour `kb create-db` et `kb openapi`.** La règle 6 de `poc.md` dit « chaque commande »,
  et #193 dit « collect et import seulement ». Signalé, pas fait.
- **Les dates des sources déjà collectées.** Un SIGTERM pendant la collecte les perd, et elles
  sont recollectées au lancement suivant (déjà vrai sans gestionnaire). Le coût est le RGESN, plus
  la fenêtre d'arXiv qui s'élargit (#71). Inscrit par time-knight dans les points à découper.
- **`docs/specs-collecte.md`.** Ses codes de sortie (lignes 17-19) restent à aligner par #64. Seul
  le passage sur le journal d'import (lignes 513-521) est corrigé ici.
- **Un SIGTERM tardif**, reçu après l'écriture de l'état ou la validation de l'import, sort aussi
  en 143. C'est assumé, et dit par le sens du code (ADR).

## Sources

| Source | Consultée le | Ce qu'elle appuie dans cette note |
|---|---|---|
| [Bash Reference Manual, « Simple Commands »](https://www.gnu.org/software/bash/manual/html_node/Simple-Commands.html) | 2026-10-18 (recherche web ; la page a répondu HTTP 429 à la relecture) | « 143 = 128 + 15, le code d'un processus tué par SIGTERM ». Phrase du manuel, d'après la recherche : « The return status […] of a simple command is its exit status as provided by the POSIX 1003.1 waitpid function, or 128+n if the command was terminated by signal n. » |
| [Python, `signal` : « Execution of Python signal handlers »](https://docs.python.org/3/library/signal.html#execution-of-python-signal-handlers) | 2026-10-18 (page lue) | « Python ne lève l'exception d'un signal qu'une fois l'appel C du `commit` revenu ». Phrase : « the low-level signal handler sets a flag which tells the virtual machine to execute the corresponding Python signal handler at a later point (for example, at the next bytecode instruction) » |
| [Python, `signal` : « Note on Signal Handlers and Exceptions »](https://docs.python.org/3/library/signal.html#note-on-signal-handlers-and-exceptions) | 2026-10-18 (page lue) | Section 7, première puce. Phrase : « applications that are complex or require high reliability should avoid raising exceptions from signal handlers » |
| [Python, guide `enum`](https://docs.python.org/3/howto/enum.html) (lu par Context7, `/python/cpython` v3.13.9, `Doc/howto/enum.rst`) | 2026-10-18 | « C'est le motif "Coordinate" du guide `enum` de Python » : `__new__` qui pose `_value_` et des attributs (`label`, `unit`) |
| uvicorn 0.54.0, source installée : `uvicorn/config.py:81` | 2026-10-18 | « 3 `SERVER_NOT_STARTED` (rendu par uvicorn) ». Ligne : `STARTUP_FAILURE = 3` |
| uvicorn 0.54.0, source installée : `uvicorn/server.py:339-349` | 2026-10-18 | « uvicorn remet `SIG_DFL` puis renvoie SIGTERM ». Lignes : `signal.signal(sig, handler)` sur les gestionnaires d'origine, puis `signal.raise_signal(captured_signal)` |
| [#60](https://github.com/SabineLaurent/K-B/issues/60) (fermée) | 2026-10-18 | « État de collecte non écrit : échec ». Phrase : « sort avec le code **1** (la collecte a eu lieu) » |
| [#64](https://github.com/SabineLaurent/K-B/issues/64) | 2026-10-18 | Même point. Phrase : « Les codes de sortie sont décrits, comme #193 les nomme : 0, 1 (dont l'état non écrit), le code de l'échec partiel, et 2… » |
