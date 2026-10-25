# Ctrl-C traité comme SIGTERM, puis mort par SIGINT

- **Date** : 2026-10-25
- **Branche** : `fix/ctrl-c-stop`
- **Issue** : aucune. La demande vient de la vérification n° 2 de la certif, faite à la demande de Sabine
  (`certif-deviaa-rncp37827/verifications-kb/2026-10-25-gestion-erreurs-etl-api-donnees.md`,
  « Limites assumées », point 4). Sabine a décidé de la corriger.
- **Fichiers principaux** : `src/k_b/commands/sigint.py` (nouveau), `src/k_b/cli.py`,
  `src/k_b/commands/exit_codes.py`, `tests/commands/test_sigint.py`

## Le pourquoi

Un Ctrl-C ne perdait rien : l'import annulait sa transaction, et la collecte n'écrivait pas son état. Mais
`kb` ne le traitait pas. Python affichait sa trace hors du journal daté, aucun code de sortie ne le nommait,
et un second Ctrl-C pouvait couper le nettoyage en cours (une copie temporaire de Zotero, par exemple).
SIGTERM, lui, était déjà traité proprement (`commands/sigterm.py`). Ctrl-C reçoit maintenant le même
traitement.

Une première version a été écartée avant d'être poussée. Elle rendait 130 comme une sortie normale, avec deux
défauts :
- **bash** : quand une commande qu'il attend sort normalement après un Ctrl-C, bash croit qu'elle l'a traité,
  et il **continue sa boucle** (« wait and cooperative exit »). Une boucle `for … do kb import; done` ne
  s'arrêtait plus.
- **uvicorn** : il renvoie SIGINT une fois arrêté. Les serveurs auraient journalisé une erreur et rendu 130.

## Le comment

### 1. Le premier Ctrl-C arrête, les suivants sont ignorés

```python
def raise_keyboard_interrupt_once(signal_number: int, frame: FrameType | None) -> None:
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    raise KeyboardInterrupt
```
(`src/k_b/commands/sigint.py:49`). Le gestionnaire est posé par `stopping_on_sigint` (`:17`), seulement pour
collect, import, write-tops et digest : la même liste que pour SIGTERM, importée et non recopiée. Deux
exceptions à la pose et à la remise :
- **SIGINT ignoré dès le lancement** (`:25`), comme pour un `kb` lancé en arrière-plan d'un script : le
  Ctrl-C ne lui est pas destiné, et il reste ignoré ;
- **arrêt par Ctrl-C** (`:34`) : le gestionnaire d'avant n'est pas remis, SIGINT reste ignoré jusqu'à la mort
  de `kb`. Un second Ctrl-C ne coupe ainsi ni la ligne du journal ni sa fermeture.

Dans les autres cas, le gestionnaire d'avant est remis en sortie. Il lève `KeyboardInterrupt`, le type que Python lève déjà sur Ctrl-C. Les nettoyages
existants le traitent donc sans changement : ils attrapent `BaseException`, défont leur travail, puis
relèvent l'erreur (`etl/load.py`, `database/creation.py`, `core/atomic_write.py`).

### 2. La CLI journalise, ferme le journal, puis meurt par SIGINT

```python
        except KeyboardInterrupt:
            if arguments.command not in COMMANDS_STOPPED_BY_SIGINT:
                raise
            ...
            logger.error("kb stopped by Ctrl-C (SIGINT)")
            log_stack.close()
            die_by_sigint()
```
(`src/k_b/cli.py:135-144`). Le cas des serveurs est relevé tel quel : leur comportement ne change pas. Pour
les quatre commandes, SIGINT est déjà ignoré, et l'ordre compte : écrire la ligne au journal daté, fermer le
journal, puis mourir.

### 3. Mourir par le signal, comme Python

`die_by_sigint` (`sigint.py:54`) vide stdout et stderr, remet SIGINT par défaut, puis
`signal.raise_signal(SIGINT)` (`:62`). C'est exactement ce que fait CPython quand un `KeyboardInterrupt`
remonte sans être attrapé (`exit_sigint`, bpo-1054041), et ce que fait uvicorn. Le shell voit alors un
processus tué par SIGINT : il lit 130 et arrête sa boucle. Un processus parent en Python lit -2.

`ExitCode.STOPPED_BY_SIGINT = 130` (`exit_codes.py:43`) nomme cette valeur, sur le modèle du code 3 d'uvicorn :
pour que `kb --help` la décrive (avec ce que lisent un shell, 130, et un processus parent, -2), et que nul autre
code ne la prenne. `main` ne la rend que si le signal n'a pas arrêté le processus.

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Fin du processus | Mourir par SIGINT : le shell arrête sa boucle, comme avec Python seul | Rendre 130 en sortie normale : bash continue la boucle (première version) |
| Commandes | Celles de SIGTERM, une seule liste | Toutes les commandes : uvicorn renvoie SIGINT après l'arrêt des serveurs |
| Exception | `KeyboardInterrupt`, déjà traitée par les nettoyages | Une exception neuve, comme `StoppedBySigtermError` : tous les nettoyages à revoir |
| Second Ctrl-C | Ignoré pendant le nettoyage, comme SIGTERM | Laissé à Python : il couperait le nettoyage (copie temporaire de Zotero laissée) |
| Où vit le code | `commands/sigint.py`, à côté de `sigterm.py` | Dans `sigterm.py` : le nom du module mentirait |
| SIGINT ignoré au lancement | Gardé : un `kb` en arrière-plan d'un script ne doit pas s'arrêter sur le Ctrl-C du terminal | Poser le gestionnaire quand même (première rédaction, relevé par la revue) |

## Preuve

| Test | Ce que ça démontre |
|---|---|
| `test_a_ctrl_c_during_a_source_stops_kb_collect_and_keeps_the_collection_state` (`tests/commands/test_sigint.py:40`) | Un vrai SIGINT pendant une source : l'état est inchangé, le brut d'avant gardé, la source d'après non lancée, une ligne au journal sans trace, une mort demandée |
| `test_a_ctrl_c_during_kb_import_leaves_neither_the_import_nor_its_log` (`:70`) | La base est identique, ligne à ligne, et aucun journal d'import n'est laissé |
| `test_kb_stops_on_the_first_ctrl_c_ignores_the_next_and_sets_the_handler_back` (`:100`) | Pour chacune des quatre commandes : le premier SIGINT lève, le second est ignoré, et le gestionnaire d'avant est remis quand l'exception est attrapée dans le bloc |
| `test_once_stopped_by_ctrl_c_kb_keeps_ignoring_sigint_until_it_dies` (`:115`) | Arrêté par Ctrl-C, SIGINT reste ignoré en sortie |
| `test_a_sigint_ignored_from_the_start_stays_ignored` (`:125`) | Un SIGINT ignoré au lancement le reste |
| `test_the_other_commands_keep_the_sigint_handler_found`, `test_a_ctrl_c_out_of_kb_serve_data_is_left_to_python_as_before` (`:136`, `:143`) | Les serveurs, `create-db` et `openapi` ne changent pas |
| `test_a_ctrl_c_while_a_sheet_is_written_stops_write_tops_and_deletes_no_ranking`, `test_a_ctrl_c_while_a_sheet_is_written_stops_digest_and_keeps_the_sheet` | Les fiches déjà écrites restent, et aucun relevé n'est supprimé, comme le README le promet |
| `test_kb_collect_sent_sigint_in_its_own_process_dies_by_sigint` (`:161`) | Un vrai processus `kb collect` reçoit un vrai SIGINT : il meurt par le signal (`returncode == -2`), avec la ligne et sans trace |
| Contre-épreuve : `die_by_sigint()` retiré de la CLI | 3 tests échouent, dont celui du vrai processus : il attrape le défaut de la première version |
| `uv run pytest` : 2 627 réussis ; mypy, ruff verts | Rien d'autre n'a cassé |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas simplement rendre 130 ?** Parce que bash distingue « sorti avec 130 » de « tué par
   SIGINT ». Dans le premier cas, il croit que la commande a traité le Ctrl-C et poursuit sa boucle. Python
   meurt par le signal pour cette raison depuis bpo-1054041.
2. **Et les serveurs ?** uvicorn traite Ctrl-C lui-même, puis renvoie le signal une fois arrêté. `kb` le
   laisse faire, comme avant.
3. **Un Ctrl-C pendant la validation de l'import ?** Python lève l'exception une fois le `commit` de SQLite
   revenu. L'import est alors gardé avec son journal, comme pour SIGTERM.

## Zones non vérifiées

- Windows : non visé, car K-B tourne sur macOS et en conteneur Linux. Sous Windows, `raise_signal(SIGINT)` ne
  tue pas le processus de la même façon, et le `return 130` sert alors de repli.
- Un SIGTERM pendant le nettoyage d'un Ctrl-C (ou l'inverse) l'interrompt : chaque gestionnaire n'ignore
  que son propre signal. Ce défaut existe déjà à l'identique sur `main`, et il est à porter dans une issue.

## Ce qui reste

- Ctrl-C sur `kb serve-data` affiche aujourd'hui une trace Python : uvicorn renvoie SIGINT, et rien ne
  l'attrape. Ce comportement est inchangé, et il est à traiter à part si on le veut.

## Sources

| Source | URL | Consultée |
|---|---|---|
| CPython, « bpo-1054041: Exit properly after an uncaught ^C » (miroir du commit) | https://git.joshthomas.dev/mirrors/cpython/commit/38f11cc3f62db11a4a24354bd06273322ac91afa | 2026-10-25 |
| bpo-1054041, le rapport d'origine | https://bugs.python.org/msg60590 | 2026-10-25 |
| Vidar Holen, « Why Bash is like that: Signal propagation » | https://www.vidarholen.net/contents/blog/?p=34 | 2026-10-25 |
| BusyBox, « Proper handling of SIGINT/SIGQUIT » (wait and cooperative exit) | https://coral.googlesource.com/busybox/+/refs/tags/1_15_0/docs/sigint.htm | 2026-10-25 |
| uvicorn 0.54.0, `uvicorn/server.py`, `capture_signals` (lu dans l'environnement du projet) | — | 2026-10-25 |
