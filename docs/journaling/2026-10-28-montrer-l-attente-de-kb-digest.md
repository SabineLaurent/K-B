# Montrer que kb digest attend pendant la demande à l'API IA

- **Date** : 2026-10-28
- **Branche** : `feat/digest-waiting-display`
- **Issue** : #349 (l'avancement par sujet, plus tard : #350)
- **Fichiers principaux** :
  - `src/k_b/commands/wait_display.py` (neuf) ;
  - `src/k_b/commands/digest_command.py` ;
  - `src/k_b/core/config.py`.
- **Commits** : `adf13e9` (le code et ses tests), `14478df` (la doc « Console », le README, la règle 3
  de `conventions.md`), `e083470` (deux corrections de la revue), puis cette note.

## Le pourquoi

Après `digests asked of the AI API, read timeout 240 seconds`, `kb digest` ne disait plus rien jusqu'à
la réponse : environ une minute, 240 s au plus. Tu l'as dit le 28/10 : « la minute où rien ne se passe
qui fait se demander si ça tourne ou c'est coincé ». La demande est un seul `POST /digests`, et l'API IA
répond d'un bloc à la fin : `kb` ne sait pas où elle en est. Il ne peut montrer qu'une chose : qu'il
attend toujours, et depuis combien de temps, sous un délai qui garantit que l'attente finit.

Les outils en ligne de commande font ainsi (sources du plan, lues le 28/10) : une animation qui se
réécrit sur une ligne dans un terminal (npm, gh, Docker), des lignes simples quand la sortie part dans
un journal (le `Still creating... [10s elapsed]` de Terraform), car une animation dans un fichier n'est
que du bruit (clig.dev : « If `stdout` is not an interactive terminal, don't display any animations »).
Tu as choisi les deux, et gardé pour plus tard l'avancement par sujet (#350).

## Le comment

### Un gestionnaire de contexte autour de la seule demande

```python
with (
    build_ai_api_client(settings) as http_client,
    showing_the_wait("the digests", AI_API_READ_TIMEOUT_SECONDS),
):
    response = request_digests(http_client, subject_names)
```
(`src/k_b/commands/digest_command.py:63-67`)

L'affichage commence quand la demande part et s'arrête quand le bloc se termine, quelle qu'en soit la
raison : la réponse, une `AiApiError`, un Ctrl-C ou SIGTERM. Tout ce qui précède (réglages, contrôle du
coffre) et tout ce qui suit (écriture des fiches) est inchangé. Le module vit dans `commands/`, la
couche de présentation (règle 5 de `conventions.md`), à côté de `run_log.py` et `sigterm.py` : il
pourra servir à `kb collect` et `kb import` si tu le décides.

### Le mode se choisit sur le flux où l'on écrit

```python
stream = sys.stderr
display = (
    SpinnerRow(stream, waited_for, read_timeout_seconds)
    if stream.isatty()
    else WaitLogLine(waited_for, read_timeout_seconds)
)
```
(`src/k_b/commands/wait_display.py:90-95`)

`isatty()` dit si le flux est relié à un terminal. On teste la sortie d'erreur, là où l'attente
s'écrit, et on la lit une seule fois : c'est le même objet que le `StreamHandler` du journal
(`run_log.py:42`). Deux classes, une interface commune : `period_seconds`, `show(elapsed)`, `clear()`.

- `SpinnerRow` réécrit la même ligne toutes les 0,1 s : `\r` ramène le curseur en début de ligne sans
  en ouvrir une nouvelle. Elle n'est jamais écrite dans `kb.log`.
- `WaitLogLine` écrit une ligne de journal datée toutes les `WAIT_LOG_INTERVAL_SECONDS` (10 s,
  `core/config.py`), sur la sortie d'erreur et dans `kb.log`.

### La ligne qui tourne : la coupe et l'effacement

```python
self.write("\r" + line[: self.read_columns() - 1])
...
self.write("\r" + " " * (self.read_columns() - 1) + "\r")
...
return get_terminal_size(self.stream.fileno()).columns or FALLBACK_COLUMNS
```
(`src/k_b/commands/wait_display.py:50`, `:54`, `:62`)

Une ligne plus large que le terminal passerait à la ligne : `\r` ne remonterait qu'au début de la
dernière rangée, et chaque image en ajouterait une. Le texte est donc coupé à la largeur moins une
colonne, lue sur le descripteur du flux lui-même (`shutil.get_terminal_size` lirait d'abord la variable
`COLUMNS`). Un terminal qui annonce 0 colonne est pris pour 80, le repli de `shutil`. L'effacement
couvre toute la rangée, pour emporter aussi le `^C` que le terminal affiche lui-même au Ctrl-C ; il
n'utilise que `\r` et des espaces, sans séquence d'échappement.

### Un fil d'exécution, un `Event`, un `join`

```python
try:
    start_without_stop_signals(thread)
    yield
finally:
    stopped.set()
    if thread.is_alive():
        thread.join()
    display.clear()
```
(`src/k_b/commands/wait_display.py:103-114`)

La demande bloque le fil principal dans la lecture de la réponse : l'affichage tourne donc dans un
second fil, `wait-display`. Sa boucle est `while not stopped.wait(display.period_seconds)` (`:130`) :
`Event.wait(t)` dort au plus `t` secondes et rend `True` dès que l'événement est levé. Le `finally`
lève l'événement, attend la fin du fil, puis efface la ligne. Le `join` compte : sans lui, une image
pourrait s'écrire après l'effacement, ou une ligne de journal après que `run_log.py` a retiré ses
gestionnaires (ce qui rouvrirait `kb.log`). Il n'est pas borné, à la différence de l'arrêt des traces
(`trace_export.py`) : `Event.wait` rend la main aussitôt et rien ne passe par le réseau. Le fil est
`daemon` en filet : il ne retiendrait pas la fin du processus.

### Les signaux restent au fil principal

```python
previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, STOP_SIGNALS)
try:
    thread.start()
finally:
    signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
```
(`src/k_b/commands/wait_display.py:120-124`)

C'est le point le plus subtil. Un signal envoyé au processus (Ctrl-C, `docker stop`) est remis par le
système à **un** fil qui ne le bloque pas. Python exécute toujours son gestionnaire dans le fil
principal, mais si le système a remis le signal au fil d'attente, la lecture bloquante du fil principal
n'est pas interrompue : `kb` attendrait jusqu'aux 240 s du délai, bien au-delà des 10 s que
`docker stop` laisse avant SIGKILL (règle 6 de `poc.md`). Le fil d'attente doit donc bloquer SIGINT et
SIGTERM. Il les bloque **dès sa naissance** : le fil principal les bloque juste le temps de
`thread.start()`, le nouveau fil hérite de ce masque (`man pthread_create` : « The signal mask is
inherited from the creating thread »), puis le fil principal reprend le sien. Un signal arrivé pendant
cet instant reste en attente et part au rétablissement du masque ; c'est pourquoi le démarrage est dans
le `try` : l'exception qu'il lève passe par le même `finally`.

## Choix faits et options écartées

- **Animation dans un terminal, ligne datée ailleurs** : ton choix du 28/10, la pratique courante.
  Écarté : la ligne datée seule (ma première proposition, plus simple, moins agréable à l'œil) ; une
  animation partout (illisible dans `kb.log` et en conteneur).
- **10 s hors terminal** : le rythme de Terraform et la limite d'attention de NN/g. 15 s, la première
  idée, laissait plus de silence.
- **Un fil d'exécution**. Écartés : `asyncio` (il faudrait passer le client `httpx2` et la commande en
  asynchrone) ; `SIGALRM` (écrire au journal depuis un gestionnaire de signal) ; la demande dans un fil
  à part (la fermeture du client attendrait la fin de la demande) ; `threading.Timer` (relancé à chaque
  image, pas plus court).
- **Aucune dépendance** : `rich` a été écarté le 21/10 (#291) ; le module fait une centaine de lignes.
- **Le message garde son maximum** (`read timeout 240`) : la règle 3 de `conventions.md` demande l'état
  et la mesure ; on voit d'un coup d'œil que l'attente est bornée.
- **La règle 3 reçoit une phrase** (ton accord du 28/10) : l'animation n'est ni un résultat (`print`)
  ni une ligne de journal (`logger`) ; elle ne laisse rien, et hors terminal une ligne datée la remplace.
- **Le mode se choisit par `isatty()` seulement**. Écarté : lire `TERM` ou `CI` (il faudrait lire
  l'environnement dans ce module, ce que `test_environment.py` réserve à d'autres).

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_on_a_terminal_a_spinner_turns_then_its_row_is_cleared` | dans un terminal : la première image, puis en dernier la rangée effacée ; rien au journal |
| `test_on_a_narrow_terminal_each_frame_is_cut_to_its_width` | à 20 colonnes, chaque image fait au plus 19 caractères |
| `test_a_terminal_that_says_0_columns_is_taken_as_80_wide` | le repli à 80 colonnes (rouge avant la correction) |
| `test_the_thread_is_born_with_sigint_and_sigterm_blocked_and_the_main_thread_keeps_its_mask` | le masque du fil dès sa première instruction, celui du fil principal inchangé (rouge avant la correction) |
| `test_out_of_a_terminal_the_wait_is_a_log_line_and_no_frame` | hors terminal : la ligne au journal, aucune image |
| `test_the_wait_stops_and_clears_its_row_when_the_block_raises` | le fil vit dans le bloc, plus après, et la rangée est effacée, même sur une exception |
| `test_a_slow_request_logs_that_the_digests_are_still_awaited` | `kb digest` entier : la ligne datée sur la sortie d'erreur et dans `kb.log` pendant une demande lente |
| `test_kb_digest_sent_sigterm_while_it_waits_exits_with_143` | un SIGTERM envoyé de l'extérieur pendant l'attente : code 143, `kb stopped by SIGTERM` |
| trois mutations du module (sans effacement, sans coupe, sans `join`) | chacune fait échouer un ou deux tests : les tests voient ce qu'ils disent voir |
| tests de l'attente rejoués 20 et 30 fois | aucun échec : pas d'attente par `sleep`, chaque test attend un `Event` (5 s au plus) |
| `uv run pytest` : 2 747 verts ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` | les contrôles de la CI |

Les tests remplacent `sys.stderr` par un faux flux (qui dit être un terminal ou non), la taille du
terminal et l'horloge (`monotonic`, pour que chaque image dise « 0 s »). Aucun `assert` dans un fil : un
`assert` qui échoue dans un fil n'est qu'un avertissement de pytest ; le résultat de `wait(5)` est gardé,
puis affirmé dans le test.

## Ce que tu dois pouvoir défendre

1. **Pourquoi un fil, et pas `asyncio` ?** La demande est synchrone (`httpx2.Client`) et bloque le fil
   principal ; un second fil qui ne fait qu'écrire est le plus petit changement. `asyncio` obligerait à
   réécrire le client et la commande (`wait_display.py:97-102`).
2. **Que se passe-t-il sur un Ctrl-C pendant l'attente ?** Le signal ne peut arriver qu'au fil principal
   (masque hérité, `:120-124`) ; il interrompt la lecture ; le `finally` arrête le fil et efface la
   ligne (`:107-114`) ; Python affiche sa trace habituelle, comme avant.
3. **Pourquoi l'animation n'est-elle pas dans `kb.log` ?** Elle n'est ni un résultat ni un déroulé à
   relire : elle ne vit que le temps de l'attente (règle 3 de `conventions.md`). Hors terminal, la ligne
   datée la remplace, et va, elle, dans `kb.log` (`:73-79`).
4. **La ligne prouve-t-elle que l'API IA avance ?** Non : elle prouve que `kb` attend toujours, et le
   délai de 240 s garantit que l'attente finit. Seule l'API IA pourrait dire « sujet 3 sur 8 » : c'est
   #350.
5. **Et dans un conteneur ?** Sans TTY, c'est la ligne datée. Avec un TTY (`docker run -t`,
   `tty: true`), `isatty()` est vrai et le journal du conteneur recevrait l'animation : à régler par #200
   (pas de TTY pour `kb digest`).

## Zones non vérifiées

- **Le rendu réel dans ton terminal** n'est pas encore vu : c'est l'essai sans modèle (`nc -l 8099`,
  `KB_AI_API_URL=http://127.0.0.1:8099`) prévu avec la PR.
- **Le test SIGTERM ne prouve pas le masque** : le système remet en général le signal au fil principal
  de lui-même ; ce test passerait donc aussi sans masque. Le masque est prouvé par le test qui lit le
  masque du fil, pas par un signal réel remis au mauvais fil (impossible à provoquer à coup sûr).
- **Un terminal à 0 colonne** : constat plausible de la revue, sans terminal de ce type pour l'observer ;
  le repli est testé avec une taille simulée.
- **Hors UTF-8**, les images braille sortent en `⠋` et la ligne déborde. Vérifié : en locale `C`,
  Python passe de lui-même en UTF-8 ; il faudrait forcer un autre encodage. Accepté, cosmétique.
- **Un terminal raccroché** (descripteur inutilisable alors que `isatty()` est vrai) : l'effacement
  lèverait `OSError` dans le `finally` et remplacerait le vrai résultat. Constat plausible des deux
  revues, écarté : les `print` des fiches, sur le même terminal, échoueraient de même.

## Ce qui reste

- L'avancement par sujet, renvoyé par l'API IA : #350, sans jalon.
- Le résumé de fin de `kb digest` (durée, fenêtre, items lus) : « ensuite on voit ».
- `kb collect` et `kb import` : le module est prêt à servir, rien n'est branché.
- Un conteneur avec TTY : à régler avec #200.
