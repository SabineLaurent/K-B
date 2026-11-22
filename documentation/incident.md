# L'incident de l'arrêt de kb sur Ctrl-C

!!! note "Compétences de la certification"

    > Documentation de l'erreur et de la solution implémentée.

    — C21

Cette fiche documente un incident de K-B, de l'erreur jusqu'à la solution fusionnée: un Ctrl-C pendant une commande
`kb` imprimait toute la trace de Python au lieu d'une ligne du journal. Elle dit l'erreur, sa cause, chaque étape de
sa résolution puis de son implémentation, ce que le code en garde aujourd'hui et ses limites. La procédure de débogage
pas à pas est dans l'outil de suivi, sur [l'issue n° 352](https://github.com/SabineLaurent/K-B/issues/352), l'issue de
l'incident. La fiche est écrite d'après le code de `main` au commit `9658225a` (2026-11-22). Un renvoi au code d'avant
le correctif nomme son commit, `503dcd0d`, et un renvoi au correctif, celui de sa fusion, `d76b731a`. Les chemins du
code de K-B (`commands/…`, `core/…`, `etl/…`) partent de `src/k_b/`, les autres de la racine du dépôt.

## L'erreur

### Le message

L'erreur a été reproduite le 2026-11-22 sur `503dcd0d`, le `main` d'avant le correctif, avec Python 3.13.13 et
uv 0.13.6. Un faux serveur, `nc`, à l'écoute sur `127.0.0.1:8099`, tenait le rôle de l'API IA: il reçoit la demande et
ne répond jamais. `kb digest` a été lancé par `uv run`, puis il a reçu SIGINT, le signal qu'envoie un Ctrl-C, pendant
qu'il attendait la réponse. La sortie d'erreur compte 64 lignes: la ligne datée d'avant l'interruption, puis
63 lignes de trace, en 20 cadres. Voici le début et la fin de cette sortie, les chemins de la copie du dépôt remplacés
par `…`:

```text
2026-11-22T18:15:13Z INFO k_b.cli: digests asked of the AI API, read timeout 240 seconds
Traceback (most recent call last):
  File "…/.venv/bin/kb", line 12, in <module>
    sys.exit(main())
             ~~~~^^
  File "…/src/k_b/cli.py", line 122, in main
    return run_command(arguments.command, data_dir, environ)
  File "…/src/k_b/cli.py", line 151, in run_command
    return run_digest(environ)
  File "…/src/k_b/commands/digest_command.py", line 67, in run_digest
    response = request_digests(http_client, subject_names)
  File "…/src/k_b/post/ai_api_client.py", line 188, in request_digests
    answer = http_client.post(DIGESTS_PATH, json={})
[… 47 lignes omises: 14 cadres de httpx2 et de httpcore2 …]
  File "…/.venv/lib/python3.13/site-packages/httpcore2/_backends/sync.py", line 127, in read
    return self._sock.recv(max_bytes)
           ~~~~~~~~~~~~~~~^^^^^^^^^^^
KeyboardInterrupt
```

La trace n'entre pas dans le journal daté: `kb.log` ne garde que la première ligne, celle de niveau `INFO`. Les
commandes de la reproduction et leurs sorties entières sont dans l'issue de l'incident.

### Le déclenchement

Un Ctrl-C pendant qu'une commande `kb` travaille. Sabine l'a vu le 2026-10-28, pendant l'essai de
[l'issue n° 351](https://github.com/SabineLaurent/K-B/issues/351), qui affiche l'attente de `kb digest`: la commande
s'est arrêtée aussitôt, mais Python a imprimé toute sa pile, de `cli.py` jusqu'à `sock.recv`. Elle l'a reproduit le
même jour d'une seule touche: avec `nc` comme API IA, avant et après #351, et avec les vrais serveurs (#352).

### Le périmètre touché

- **Toutes les commandes `kb` qui ne sont pas des serveurs**: à `503dcd0d`, `kb collect`, `kb import`,
    `kb write-tops`, `kb digest`, `kb create-db` et `kb openapi`. Chacune imprimait la trace, hors du journal daté.
- **Pas les serveurs**: `kb serve-data` et `kb serve-ai` lancent `uvicorn.run`, qui attrape lui-même l'interruption.
    Une fois démarrés, ils sortaient en 0, sans trace.
- **Le terminal local seulement**: en ligne, sur Azure Container Apps, l'arrêt d'un conteneur vient par SIGTERM, que
    `kb` traitait déjà (`kb stopped by SIGTERM`, code 143).

Le code de sortie que lit un shell ne change pas avec le correctif: il vaut 130 avant comme après. Seul un processus
qui lance `kb` lui-même, sans uv, voit une différence de code. Le tableau suivant donne, pour chaque façon de lancer `kb digest`, ce
qu'ont donné les deux versions le 2026-11-22.

| Ce qui est observé | Avant le correctif (`503dcd0d`) | Après (`9658225a`) |
|---|---|---|
| La sortie d'erreur | la trace de 63 lignes | une ligne, `ERROR k_b.cli: kb stopped by SIGINT` |
| `kb.log` | la ligne `INFO` seule, sans la trace | les lignes `INFO`, puis la même ligne `ERROR` |
| Le code de `uv run kb digest` | 130, rendu par uv | 130 |
| Le code de `.venv/bin/kb digest`, lu par le processus qui le lance | -2: `kb` est tué par le signal | 130: `kb` sort normalement |

## La cause

Sur Ctrl-C, le terminal envoie SIGINT aux processus du premier plan. Le gestionnaire que Python pose au démarrage en
fait une exception, `KeyboardInterrupt`, levée dans le fil principal. Or `KeyboardInterrupt` hérite de
`BaseException`, et non d'`Exception`:

```sh
python3 -c "print(issubclass(KeyboardInterrupt, Exception), KeyboardInterrupt.__mro__)"
# False (<class 'KeyboardInterrupt'>, <class 'BaseException'>, <class 'object'>)
```

À `503dcd0d`, le bloc qui lance chaque commande, `cli.py:120-131`, attrapait `StoppedBySigtermError` (SIGTERM) et
`Exception`, rien d'autre. L'interruption remontait donc jusqu'à Python, qui imprimait sa trace, puis finissait le
processus par SIGINT: c'est le -2 du tableau.

## La résolution, étape par étape

1. **Observer.** Le 2026-10-28, à l'essai de #351, Sabine voit la trace au lieu d'une ligne du journal. Le constat
    ouvre [l'issue n° 352](https://github.com/SabineLaurent/K-B/issues/352).
2. **Reproduire.** Elle le reproduit le même jour, d'une seule touche, avec `nc` comme API IA et avec les vrais
    serveurs, avant et après #351: l'erreur ne vient pas de #351.
3. **Trouver la cause.** La trace part de `cli.py` et finit sur `sock.recv`, l'attente de la réponse: l'interruption
    a traversé `kb` sans être attrapée. `cli.py` traite SIGTERM et `Exception`, mais `KeyboardInterrupt` n'est ni l'un
    ni l'autre. Les serveurs n'ont pas de trace, parce que `uvicorn.run` attrape l'interruption
    (`uvicorn/main.py:633-634`, uvicorn 0.54.0).
4. **Chercher la pratique courante.** Le guide des interfaces en ligne de commande
    [clig.dev](https://clig.dev/), lu le 2026-10-28, demande sur Ctrl-C de
    <q><span lang="en">exit as soon as possible</span></q> et de <q><span lang="en">Say something immediately</span></q>,
    sans <q><span lang="en">scary-looking stack traces</span></q> pour un cas attendu. Depuis Python 3.8, un Ctrl-C qui
    n'est pas attrapé finit le processus par le signal ([bpo-1054041](https://bugs.python.org/issue1054041)).
5. **Concevoir.** `kb` attrape l'interruption à un seul endroit, `cli.py`, pour toutes les commandes. Il écrit une ligne
    datée du journal, `kb stopped by SIGINT`, au niveau `ERROR` comme pour SIGTERM, puis sort normalement avec un code
    nommé, 130. Les options écartées sont dans le tableau suivant.
6. **Faire relire le plan, puis le faire valider.** Le plan est relu par un sous-agent, puis validé par Sabine le
    2026-10-28. Il est écrit dans l'issue n° 352, sous « Conception ».

Le tableau suivant donne chaque choix de la conception, l'option retenue et l'option écartée, avec leur raison.

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Comment sortir | Une sortie normale en 130, comme 143 pour SIGTERM: 130 est 128 + 2, le code qu'un shell lit pour SIGINT. | Finir le processus par SIGINT, ce que fait Python, pour qu'un script bash qui lance `kb` s'arrête aussi. Sous `uv run kb …`, la façon de lancer `kb` de la documentation, uv sort déjà en 130: le gain ne vaudrait que pour `.venv/bin/kb` lancé directement. |
| Le texte de la ligne | `kb stopped by SIGINT`: le signal observé, qui vient aussi de `kill -INT`. | « Ctrl-C » dans la ligne: une supposition sur l'origine du signal. Le mot reste dans la documentation. |
| Où attraper | Dans `cli.py`, une fois, pour toutes les commandes. | Dans chaque commande: cinq copies du même bloc. |

## L'implémentation, étape par étape

1. **Les tests d'abord.** Trois tests dans `tests/commands/test_sigint.py`, neuf: une source qui lève
    `KeyboardInterrupt` pendant `kb collect`, la fausse API IA qui lève pendant l'attente de `kb digest`, et un vrai
    SIGINT envoyé à `kb collect` dans son propre processus. Chacun attend le code 130 et la ligne datée; le premier et
    le troisième, aucune trace. Le code 130 entre dans `tests/commands/test_exit_codes.py`. Avant le code, ces tests
    sont rouges: l'interruption arrête pytest lui-même.
2. **Le code.** Un bloc `except KeyboardInterrupt`, entre celui de SIGTERM et celui d'`Exception`, dans le même `try`:
    le journal est encore ouvert, la ligne y est écrite, datée comme les autres (`cli.py:127-131` à `d76b731a`). Le
    membre `STOPPED_BY_SIGINT = 130` de `ExitCode` (`commands/exit_codes.py`) donne le code à `kb --help`.
3. **Le nettoyage, vérifié.** Rien n'est ajouté: l'import annule sa transaction (`etl/load.py`), l'écriture atomique
    supprime son fichier temporaire (`core/atomic_write.py`), la création de la base supprime son fichier
    (`database/creation.py`), et la copie de la base de Zotero vit dans un dossier temporaire supprimé à la sortie.
    Chacun attrape `BaseException`, puis relève l'exception.
4. **La documentation et la décision.** Le README, `docs/specs-collecte.md` et `docs/fiches-veille.md` donnent le
    code 130. La décision est écrite au journal des décisions d'architecture (ADR,
    <span lang="en">Architecture Decision Record</span>), et le travail dans une note pédagogique.
5. **La revue.** Deux revues de code, chacune par un sous-agent sans contexte, sur la demande de fusion (PR,
    <span lang="en">pull request</span>) n° 353: la première relève 8 constats, la seconde aucun. Trois sont corrigés:
    le texte du code 130 pour `kb create-db`, qui supprime sa base; le code des serveurs interrompus pendant leur
    démarrage; une phrase du README sur `kb import`. Les autres sont laissés ou écartés avec leur raison, par Sabine.
6. **L'essai de Sabine.** `nc -lk 8099` comme API IA, `kb digest`, un Ctrl-C pendant l'attente: la ligne datée,
    aucune trace, la ligne d'attente effacée, et le code de sortie 130.
7. **La fusion.** Sabine fusionne la [PR n° 353](https://github.com/SabineLaurent/K-B/pull/353) le 2026-10-28
    (commit `d76b731a`), qui ferme l'issue n° 352.

## Ce que le code de main en garde

- Le bloc est à `cli.py:256-260`, dans `run_with_safety_nets` (`cli.py:244-265`), que `run_with_log` lance une fois le
    journal ouvert (`cli.py:224-241`). Toutes les commandes y passent, sauf `kb openapi`, qui sort avant
    (`cli.py:110-111`).
- `commands/exit_codes.py:58-72` donne le code 130 et son sens, que `kb --help` affiche. Les commandes venues
    depuis le correctif s'arrêtent de même; une routine de job n'en lance pas l'étape suivante. Le code de chaque
    commande est dans [Utiliser K-B](utilisation.md).
- Les serveurs, `kb serve-web` compris, sortent en 0 sur un Ctrl-C une fois démarrés (le commentaire de
    `commands/exit_codes.py:58-62`).
- `git grep -c KeyboardInterrupt origin/main -- tests/` trouve six fichiers de tests: `commands/test_sigint.py`,
    `commands/test_job_routine.py`, `commands/test_purge_command.py`, `etl/test_load_commit.py`,
    `purge/test_purge_raw.py` et `test_atomic_write.py`.
- La reproduction du 2026-11-22 sur `9658225a` donne la ligne `kb stopped by SIGINT`, sur la sortie d'erreur et dans
    `kb.log`, et le code 130.

## Les limites

- **Un second Ctrl-C pendant le nettoyage peut le couper**: un fichier de base à moitié créé, un temporaire caché.
    SIGTERM ignore un second signal, SIGINT non. Sabine l'a laissé ainsi le 2026-10-28, plutôt qu'un gestionnaire de
    SIGINT qui ignore le second: un Ctrl-C suppose quelqu'un devant l'écran, qui voit l'erreur. Ce cas n'est pas
    testé.
- **Un Ctrl-C avant l'ouverture du journal**, pendant l'import des modules ou la lecture de l'environnement, et
    `kb openapi` gardent la trace de Python.
- **Les serveurs pendant leur démarrage** sortent en 130 avec la ligne, en 3 ou en 0, selon le moment: c'est lu dans
    le code d'uvicorn 0.54.0, et non essayé.
- **Un script bash qui lance `.venv/bin/kb` continue après un Ctrl-C**: c'est le prix de la sortie normale, mesuré le
    2026-10-28 avec un programme qui sort en 130 sur `KeyboardInterrupt`.
- **`kb create-db` s'arrête en 130 sur SIGINT, mais ne traite toujours pas SIGTERM**: il n'est pas dans
    `COMMANDS_STOPPED_BY_SIGTERM` (`commands/sigterm.py:22-36`).
- **Après un Ctrl-C de `kb digest`, l'API IA finit la demande en cours**: une relance reçoit 429 tant qu'elle n'a pas
    fini ([Utiliser K-B](utilisation.md#ses-limites-de-debit)).
- **Le signal que reçoit un job Azure Container Apps arrêté** n'est pas écrit dans la documentation de Microsoft, qui
    donne pour un conteneur SIGTERM, puis SIGKILL 30 s plus tard
    ([<span lang="en">Application lifecycle management in Azure Container Apps</span>](https://learn.microsoft.com/en-us/azure/container-apps/application-lifecycle-management),
    lue le 2026-10-28). Il devait être vérifié à la mise en ligne du 08/11: `git grep -n "job stop"` ne trouve que l'entrée du journal
    des décisions qui le demande.

## Pour aller plus loin

- [L'issue n° 352](https://github.com/SabineLaurent/K-B/issues/352): l'incident, sa conception et la procédure de
    débogage pas à pas.
- [La PR n° 353](https://github.com/SabineLaurent/K-B/pull/353): le correctif, ses tests et le compte rendu de ses deux
    revues.
- [La note pédagogique du correctif](https://github.com/SabineLaurent/K-B/blob/main/docs/journaling/2026-10-28-arreter-kb-sur-ctrl-c.md):
    le pourquoi, le comment, les choix et les preuves.
- [Le journal des décisions](https://github.com/SabineLaurent/K-B/blob/main/docs/ADR/journal-decisions-projet.md):
    son entrée du 2026-10-28 sur le code de sortie de SIGINT (#352).
- [Utiliser K-B](utilisation.md): les codes de sortie de chaque commande.
