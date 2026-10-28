# Arrêter kb sur Ctrl-C par une ligne datée et le code 130, sans la trace de Python

- **Date** : 2026-10-28
- **Branche** : `fix/stop-on-sigint`
- **Issue** : #352
- **Fichiers principaux** :
  - `src/k_b/cli.py` ;
  - `src/k_b/commands/exit_codes.py` ;
  - `tests/commands/test_sigint.py` (neuf).
- **Commits** : `0c6a664` (le code et ses tests), `e602292` (README, `specs-collecte.md`,
  `fiches-veille.md`), puis l'entrée du journal ADR et cette note.
- **Série** : suit [Nommer les codes de sortie de `kb`](2026-10-18-nommer-les-codes-de-sortie-de-kb.md)
  (SIGTERM, 143) et [Montrer que kb digest attend](2026-10-28-montrer-l-attente-de-kb-digest.md)
  (l'essai qui a montré la trace).

## Le pourquoi

À l'essai de #351, un Ctrl-C pendant `kb digest` a imprimé une quarantaine de lignes de
`Traceback … KeyboardInterrupt`. Toutes les commandes qui travaillent faisaient de même : `kb`
traitait SIGTERM (`docker stop`) et les exceptions, pas Ctrl-C. Une trace effraie, se lit mal et
n'entre pas dans le journal daté. Le but : la même sortie que pour SIGTERM, une ligne datée et un
code nommé, pour `kb collect`, `kb import`, `kb write-tops`, `kb digest` et `kb create-db`.

## Le comment

### 1. Ctrl-C est une exception, mais pas une `Exception`

Sur Ctrl-C, le terminal envoie SIGINT au processus ; le gestionnaire que Python pose au démarrage
le transforme en `KeyboardInterrupt`, levée dans le fil principal. `KeyboardInterrupt` hérite de
`BaseException`, pas d'`Exception` : le `except Exception` de `cli.py` ne la voyait pas, et Python
imprimait sa trace en sortant. D'où le nouveau bloc (`src/k_b/cli.py:127-131`) :

```python
        except KeyboardInterrupt:
            # The same for SIGINT (Ctrl-C), which Python raises as KeyboardInterrupt, not an
            # Exception: uncaught, Python would print its whole traceback.
            logger.error("kb stopped by SIGINT")
            return ExitCode.STOPPED_BY_SIGINT
```

Il est placé entre `except StoppedBySigtermError` et `except Exception`, dans le même `try` : le
journal (`kb.log`) est encore ouvert, la ligne y est donc écrite, datée comme les autres.

### 2. Le nettoyage était déjà là

Rien n'a été ajouté pour défaire un travail interrompu : chaque endroit qui doit défaire attrape
déjà `BaseException`, donc aussi `KeyboardInterrupt`, puis relève. Exemple, l'import
(`src/k_b/etl/load.py:69-72`) :

```python
        except BaseException:
            # BaseException: Ctrl-C must not leave half an import either.
            connection.rollback()
            raise
```

De même : l'écriture atomique supprime son temporaire (`core/atomic_write.py`), la création de la
base supprime son fichier (`database/creation.py`), la copie de Zotero vit dans un
`TemporaryDirectory` supprimé à la sortie. L'exception remonte ensuite jusqu'au bloc du point 1.
Pour `kb digest`, le fil d'attente bloque SIGINT et SIGTERM (`commands/wait_display.py:29`, #349) :
le système les donne au fil principal, qui lève `KeyboardInterrupt`, arrête l'attente et efface sa
ligne en sortant.

### 3. Un code nommé : 130

`src/k_b/commands/exit_codes.py:44-50` ajoute un membre à l'énumération `ExitCode` :

```python
    STOPPED_BY_SIGINT = (
        130,
        (
            "kb collect, kb import, kb write-tops, kb digest: stopped by SIGINT (Ctrl-C); what was"
            " done before it is kept; kb create-db: stopped by SIGINT, no database left"
        ),
    )
```

130 = 128 + 2 (SIGINT est le signal 2), la convention des shells, comme 143 = 128 + 15 pour
SIGTERM. Le sens est porté par le membre : `kb --help` le liste sans qu'on touche à l'aide (règle 6
de `poc.md` : un code de sortie est une constante nommée).

### 4. Les serveurs ne changent pas

`kb serve-data` et `kb serve-ai` lancent `uvicorn.run`, qui attrape lui-même `KeyboardInterrupt` et
rend la main normalement : une fois le serveur démarré, la commande sort en 0, sans trace (observé
par Sabine, lu dans `uvicorn/main.py`, 0.54.0). Pendant le démarrage, le code dépend du moment
(lecture du code d'uvicorn, non essayé) : avant `uvicorn.run`, ou pendant le chargement de
l'application, le nouveau bloc rend 130 avec la ligne ; dans `uvicorn.run`, avant qu'uvicorn ne pose
ses gestionnaires de signaux, il avale l'interruption puis sort en 3 (`STARTUP_FAILURE`,
`main.py:633-640`) ; une fois ses gestionnaires posés (`server.py:89`), il finit de démarrer, puis
s'arrête en 0.

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Comment sortir | **Sortie normale en 130**, comme 143 pour SIGTERM. | Finir le processus par SIGINT (`os.kill` sur soi, ce que Python fait depuis la 3.8 pour un Ctrl-C non attrapé), pour qu'un script bash qui lance `kb` s'arrête aussi. Sous `uv run kb …`, la façon de lancer `kb` du README, uv sort lui-même en 130 : le gain ne vaudrait que pour `.venv/bin/kb` lancé à la main, au prix d'une sortie standard à vider avant le signal et d'un remplacement dans les tests. |
| Texte de la ligne | **`kb stopped by SIGINT`** : le signal observé, qui vient aussi de `kill -INT` (`code.md`, « Journalisation »). | « Ctrl-C » dans la ligne : une supposition sur l'origine ; il reste dans la doc et le commentaire. |
| Niveau | **`ERROR`**, comme pour SIGTERM : la commande n'a pas fini. | — |
| Où attraper | **Dans `cli.py`, une fois**, pour toutes les commandes. | Dans chaque commande : cinq copies du même bloc. |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_sigint_during_a_source_stops_kb_collect_and_keeps_the_collection_state` (`tests/commands/test_sigint.py:48`) | une source qui lève `KeyboardInterrupt` : code 130, la ligne datée sur la sortie d'erreur et dans `kb.log`, aucun `Traceback`, l'état de collecte inchangé, la source suivante pas lancée, aucun temporaire caché |
| `test_a_sigint_while_kb_digest_waits_stops_it_and_its_wait` (`:73`) | la fausse API IA lève pendant l'attente : code 130, la ligne, et le fil `wait-display` arrêté |
| `test_kb_collect_sent_sigint_in_its_own_process_exits_with_130` (`:95`) | un vrai SIGINT envoyé à un `kb collect` dans son propre processus : code 130, la ligne, aucun `Traceback`, aucun état écrit |
| `test_each_exit_code_keeps_its_value` (`tests/commands/test_exit_codes.py`) | 130 est la valeur de `STOPPED_BY_SIGINT` |
| Mutation : le bloc du point 1 retiré | pytest s'arrête au premier test (le `KeyboardInterrupt` s'échappe) ; le test en processus seul échoue, `assert -2 == 130` (le processus meurt du signal) |
| `uv run pytest` | 2 750 verts ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` verts |
| `grep -rnE "return [0-9]+\b" src/k_b/cli.py src/k_b/commands/*.py` | rien : aucun code en chiffres (règle 6 de `poc.md`) |
| Essai : un script bash qui lance un programme qui sort en 130 sur `KeyboardInterrupt`, SIGINT au groupe | le script continue (`after kb: 130`) : la limite de l'option retenue, mesurée |

## Ce que tu dois pouvoir défendre

1. **Pourquoi `except Exception` ne suffisait pas ?** `KeyboardInterrupt` hérite de
   `BaseException` pour qu'un `except Exception` ordinaire ne l'avale pas par mégarde ; il faut
   l'attraper par son nom (`cli.py:127`).
2. **Le travail interrompu est-il défait ?** Oui, avant d'arriver au bloc : chaque écriture qui doit
   être défaite attrape `BaseException` et relève (`etl/load.py:69`, `database/creation.py:29`,
   `core/atomic_write.py:40`). Ce qui était fini avant le signal (une source collectée, une fiche
   écrite) est gardé.
3. **Pourquoi 130 et pas 1 ?** 1 dit « échec » ; 130 dit « arrêté par SIGINT », la convention que
   lit un shell ou un orchestrateur (128 + numéro du signal), comme 143 pour SIGTERM.
4. **Pourquoi une sortie normale et pas une mort par le signal ?** Sous `uv run`, uv sort en 130
   de toute façon ; mourir du signal ne servirait qu'à un script bash lancé hors de uv, au prix de
   code de plus. Limite mesurée : un tel script continue après le Ctrl-C.
5. **Et un second Ctrl-C pendant le nettoyage ?** Il lève un second `KeyboardInterrupt` dans le
   nettoyage, qu'il coupe (un fichier de base à moitié créé, un temporaire caché) : s'il tombe dans
   le `try`, il finit au même bloc ; s'il tombe pendant le `logger.error` du bloc, la trace de
   Python revient. Contrairement à SIGTERM, rien n'ignore un second SIGINT, comme sur `main`. Choix
   de Sabine sur la revue : laissé, car un Ctrl-C suppose quelqu'un devant l'écran ; sur Azure,
   l'arrêt vient par SIGTERM, dont le second est ignoré.

## Zones non vérifiées

- Le second Ctrl-C (question 5) n'est pas testé : le comportement décrit vient de la lecture du
  code.
- `kb import`, `kb write-tops` et `kb create-db` interrompus par SIGINT ne sont pas testés de bout
  en bout : ils passent par le même bloc de `cli.py`. Leur nettoyage l'est à part : l'import et
  l'écriture atomique avec un `KeyboardInterrupt` (`tests/etl/test_load_commit.py`,
  `tests/test_atomic_write.py`), la création de la base avec une autre exception, par le même
  `except BaseException` (`tests/test_database.py:43`).
- Le code 0 des serveurs sur Ctrl-C vient de l'observation de Sabine et de la lecture
  d'uvicorn 0.54.0, pas d'un test ; les codes 130, 3 ou 0 pendant leur démarrage, de la lecture
  seule.

## Ce qui reste

- Un Ctrl-C avant l'ouverture du journal (l'import des modules, environ 240 ms, la lecture de
  l'environnement) et `kb openapi` gardent la trace de Python : hors périmètre de #352.
- `kb create-db` sort en 130 sur SIGINT mais n'a toujours pas de gestionnaire de SIGTERM (limite
  de #193).
- Le signal que reçoit un job Azure Container Apps arrêté n'est pas écrit dans la doc de Microsoft :
  à vérifier à la mise en ligne du 08/11, par la ligne `kb stopped by …` du journal.
