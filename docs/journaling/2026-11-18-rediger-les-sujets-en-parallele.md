# Rédiger les sujets d'un compte rendu de veille en parallèle, et le délai par appel à l'échéance

- **Date** : 2026-11-18
- **Branche** : `feat/parallel-digest-subjects`
- **Issues** : #630 (rédaction en parallèle), #640 (délai par appel)
- **Fichiers principaux** : `src/k_b/ai_api/digests.py`, `src/k_b/core/config.py`, `tests/ai_api/test_digests.py`,
  `tests/ai_api/test_llm_client.py`, `docs/fiches-veille.md`
- **Série** : suit [Passer K-B à gpt-6.1-sol](2026-11-18-passer-k-b-a-gpt-6-1-sol.md), qui laissait #630 ouverte.

Les commits de `main` repris par le rebase (#636, #637 : seuils de gpt-6.1-sol, site MkDocs) ne sont pas de cette PR et
ont leurs propres notes. Cette note couvre les trois commits de la branche : le code et ses tests, la doc, l'entrée ADR.

## Le pourquoi

`POST /digests` rend le compte rendu de veille : l'API IA lit les items de la fenêtre, les **classe** par sujet en
lots, puis **rédige** une fiche par sujet. Tout est borné par une échéance de 200 s par demande, sous les 240 s
qu'Azure Container Apps laisse à une requête.

Le 2026-11-17, l'essai de bout en bout sur gpt-6.1-sol (300 items, 14 jours) a atteint cette échéance avec **4 fiches
sur 9**. Les rédactions se faisaient l'une après l'autre et prenaient 23,4 à 30,7 s chacune. Après les 7 classements
(6,2 à 14,3 s chacun), il ne restait pas assez de temps pour les 9.

Sabine a décidé le 17/11 de **rédiger les sujets en parallèle** : c'est plus simple que de rendre la demande
asynchrone, qui ne viendra que si cela ne suffit pas. En parallèle, la rédaction dure à peu près la plus lente des
rédactions (environ 31 s), non leur somme (environ 250 s).

Second sujet, lié : le **délai de lecture d'une réponse du modèle** (90 s) avait été calculé pour gpt-6-luna.
gpt-6.1-sol est environ trois fois plus lent par jeton. Sabine l'a fixé à 200 s, l'échéance de la demande.

## Le comment

### 1. Séparer « quoi rédiger » de « rédiger »

`build_digests` faisait tout dans une boucle : choisir les items d'un sujet, puis appeler le modèle. Elle est coupée
en deux. La boucle qui reste ne fait que du calcul local (quels items, à partir de quelle date) et produit la liste
`subjects_to_write` ; les appels au modèle partent ensuite tous par `write_subjects`.

```python
    writings = write_subjects(
        http_client, settings, subjects_to_write, deadline, tracing=tracing
    )
    return DigestsResult(
        digests=tuple(w.digest for w in writings if w.digest is not None),
```
(`src/k_b/ai_api/digests.py:113-117`)

Chaque rédaction rend un `SubjectWriting` (fiche ou échec, son appel au modèle, ses comptes d'items). Le résultat
final est assemblé **après**, dans l'ordre de la liste : une rédaction n'écrit dans aucune liste partagée, donc
deux fils ne se marchent jamais dessus.

### 2. Un fil par sujet

```python
    with ThreadPoolExecutor(max_workers=len(subjects_to_write)) as pool:
        futures = [
            pool.submit(
                contextvars.copy_context().run,
                write_one_subject,
```
(`src/k_b/ai_api/digests.py:175-179`)

`ThreadPoolExecutor`, de la bibliothèque standard, lance chaque rédaction dans un fil. Des fils suffisent : un appel
au modèle passe son temps à **attendre** le réseau, et Python relâche le verrou global (GIL) pendant cette attente.
Les 9 requêtes HTTP sont donc vraiment en vol en même temps.

```python
        return [future.result() for future in futures]
```
(`src/k_b/ai_api/digests.py:190`)

Les résultats sont lus **dans l'ordre de soumission**, pas dans l'ordre d'arrivée : la fiche de `vulnerabilities`
reste la première même si elle finit la dernière. `future.result()` relève aussi l'exception d'un fil : un défaut
dans les contrôles n'est pas avalé.

Les 9 fils partagent le même `httpx2.Client`. Son pool de connexions est conçu pour être partagé entre fils (doc
d'httpx2, « Connection pools », « Thread and task safety », lue par Context7 le 2026-11-18), avec 100 connexions par
défaut, bien au-dessus de 9.

### 3. La copie du contexte, pour les traces

C'est le point le plus subtil. OpenTelemetry sait quel span est « courant » (ici, celui de la demande) grâce à
`contextvars`, des variables propres à chaque fil d'exécution. On l'a vérifié dans l'environnement : le contexte
d'OpenTelemetry est un `ContextVarsRuntimeContext`. Or un `ThreadPoolExecutor` ne copie pas ces variables dans ses
fils. Sans précaution, le span `write_subject` d'un fil n'aurait pas de parent : dans Tempo, les rédactions
apparaîtraient comme des traces orphelines, détachées de leur demande.

`contextvars.copy_context().run` règle cela. Au moment de la soumission, dans le fil principal, on copie le contexte
(qui contient le span de la demande), puis le fil exécute la rédaction **dans** cette copie. Une copie par sujet :
chaque fil ouvre ses propres spans sans toucher au contexte des autres.

### 4. Le replay reste en série

```python
    if settings.provider == "replay" or len(subjects_to_write) < 2:
        # In series, stopped by a fault: the answers of the replay follow the order of the
        # requests (connectors/llm_replay.py).
```
(`src/k_b/ai_api/digests.py:160-162`)

Le fournisseur `replay` rejoue des réponses enregistrées **dans l'ordre des requêtes** : la 2e requête reçoit la 2e
réponse. En parallèle, l'ordre d'arrivée des requêtes dépend de l'ordonnanceur, et `agent_frameworks` pourrait
recevoir la fiche de `vulnerabilities`. En série, le jeu de référence de #479 et les tests existants restent
valables sans changement.

L'**enregistrement** de ce jeu, lui, parle à un vrai fournisseur, donc en parallèle : les réponses arrivent dans
n'importe quel ordre. L'enregistreur garde chaque appel avec son sujet, lu dans le message utilisateur
(`read_subject`), et rend les appels dans l'ordre où le replay les enverra : le classement, puis chaque sujet dans
l'ordre de la liste (`order_as_replayed`, `tests/ai_api/digests_reference.py:283`). Constat C1 de la revue.

La série a un second effet, voulu : si une rédaction lève une exception, la boucle s'arrête et les sujets suivants ne
partent pas, comme avant. Avec un pool, même d'un seul fil, les tâches déjà soumises auraient continué.

### 5. Le 429 en parallèle

```python
    if digest is None and llm_call.saw_rate_limit:
        rate_limited.set()
```
(`src/k_b/ai_api/digests.py:236-237`)

La règle de #205 : après un 429 (débit dépassé) qu'une rédaction n'a pas surmonté, plus aucun sujet n'est envoyé,
pour ne pas envoyer des items vers une réponse refusée (minimisation, RGPD art. 5.1.c). En série, un booléen
suffisait. Ici, un `threading.Event`, sûr entre fils, le remplace : un fil le pose, et chaque rédaction le lit avant
d'envoyer (`find_skipped_state(rate_limited.is_set(), deadline)`, `:209`).

Mais en parallèle, les 9 sujets partent **en même temps**, avant qu'un 429 puisse revenir. La règle ne vaut donc
plus que pour un sujet pas encore parti, c'est-à-dire aucun en pratique (sauf en série, pour le replay). Sabine l'a
accepté le 2026-11-18 : les 9 rédactions demandent environ 150 000 jetons estimés, sous le quota de 250 000 par
minute de gpt-6.1-sol.

### 6. Le délai par appel à 200 s

```python
LLM_CALL_TIMEOUT_SECONDS = 200
```
(`src/k_b/core/config.py:253`, le calcul en commentaire à `:238-249`)

Le calcul : au débit mesuré sur gpt-6.1-sol le 17/11 (au plus 19,2 ms par jeton, arrondi à 20), la plus longue
sortie permise, 8 192 jetons, prend environ 164 s. Avec la marge de 40 % de #158, on aurait 229 s. Sabine a choisi
200 s, l'échéance de la demande.

Ce que cela change, et qu'il faut savoir dire : `Deadline.cap` (`src/k_b/ai_api/deadline.py:37`) ramène déjà chaque
délai au temps qui reste. Un délai de 200 s ne coupe donc jamais un appel avant l'échéance : **l'échéance devient la
seule borne d'un appel**. Le revers : un appel bloqué n'est plus coupé à temps pour être relancé. Cela vaut aussi
pour un classement, qui part en premier et fait alors échouer toute la demande (504 `llm_timeout`).

## Choix faits et options écartées

| Choix | Retenu, pourquoi | Écarté, pourquoi |
|---|---|---|
| Parallèle ou asynchrone | Parallèle par fils (décision de Sabine du 17/11) : la route reste synchrone, rien n'est gardé entre deux requêtes | Tâche de fond : un état entre deux requêtes, contraire à la règle 7 de `poc.md` ; à reprendre seulement si le parallèle ne suffit pas |
| Fils ou `asyncio` | `ThreadPoolExecutor` : le code d'appel au modèle est synchrone (`httpx2.Client`), il reste tel quel | `asyncio` : réécrire `llm_client.py` et toute la chaîne en `async` |
| Nombre de fils | Un par sujet, tous à la fois | Borner à 3 : trois vagues d'environ 31 s, soit environ 60 s de plus, pour peu de protection contre un 429 |
| Ce qui reste en série | Le classement (hors du périmètre de la mission) et le replay | Classer en parallèle : à proposer seulement si l'essai ne tient pas l'échéance |
| Le replay | Garder la série, `if settings.provider == "replay"` | Un replay qui choisit sa réponse selon le sujet de la requête : du code et un réenregistrement payant du jeu de référence |
| Le 429 | Accepter que la règle ne vaille plus que pour un sujet pas encore parti (Sabine, 18/11) | Faire stopper les relances des autres fils dès qu'un 429 arrive : modifier `call_model` pour un cas rare |
| Délai par appel | 200 s (Sabine, 18/11) | 230 s (règle des 40 %, sans effet au-delà de l'échéance) ; 170 s (4 % de marge) ; un délai par étape (aucun besoin écrit) |
| Le test du délai | La plus longue sortie au débit mesuré tient dans le délai, et le délai égale l'échéance | Garder la marge de 40 % : contredirait la valeur choisie |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_subjects_of_a_provider_are_written_all_at_once` (`tests/ai_api/test_digests.py:1405`) | Chaque rédaction attend à une `threading.Barrier` de 3 que les trois soient en vol. En série, la première attendrait seule : `BrokenBarrierError` au bout de 5 s (échec observé avant le code, le 18/11 à 03:10Z) |
| `test_the_digests_keep_the_order_of_the_list_when_the_first_is_answered_last` (`:1422`) | Le premier sujet n'est servi qu'après les deux autres ; les fiches et les appels (`stage_calls`) restent dans l'ordre de la liste. Le test ne prouve pas qu'il finit le dernier : l'ordre de fin dépend de l'ordonnanceur |
| `test_a_subject_written_in_its_thread_keeps_its_span_under_the_request` (`:1455`) | Chaque `write_subject` a pour parent le span de la demande, et chaque `chat` de rédaction a pour parent son `write_subject` : la copie du contexte fonctionne |
| `test_a_fault_in_a_thread_is_raised` (`:1483`) | Une exception dans un fil remonte à l'appelant, elle n'est pas perdue |
| `test_the_calls_recorded_in_parallel_are_kept_in_the_order_the_replay_sends_them` (`tests/ai_api/test_digests_reference.py:96`) | Des rédactions enregistrées dans le désordre sont rendues dans l'ordre du replay, les tentatives d'un sujet groupées |
| Les tests existants de `test_digests.py` et `test_digest_router.py`, inchangés | Le replay en série garde l'ordre, le 429 et l'échéance comme avant |
| `test_the_read_timeout_covers_the_longest_output_at_the_measured_rate` et `test_the_read_timeout_is_the_deadline_of_a_request` (`tests/ai_api/test_llm_client.py:686`, `:695`) | 8 192 jetons à 20 ms (163,84 s) tiennent dans le délai, et le délai égale les deux échéances ; échecs observés avant le code (`163.84 <= 90`, `90 == 200`) |
| `uv run pytest` : 5 626 réussis ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` verts | Aucun recul ailleurs |
| Essai de bout en bout sur gpt-6.1-sol | **À faire**, lancé par Sabine : critère 9 sujets sur 9 avant 200 s ; relevé dans `essai-c8/` |

## Ce que tu dois pouvoir défendre

1. **Pourquoi des fils, alors que Python a un GIL ?** Le GIL empêche deux fils d'exécuter du code Python en même
   temps, mais il est relâché pendant une attente réseau. Une rédaction est presque entièrement une attente (environ
   30 s de réponse du modèle, quelques millisecondes de calcul) : les 9 attentes se recouvrent. (`digests.py:175`)
2. **Que se passe-t-il pour les traces dans Grafana ?** Sans la copie du contexte, chaque rédaction serait une trace
   orpheline. `contextvars.copy_context().run` donne à chaque fil le contexte de la demande, et un test le vérifie.
   (`digests.py:178`, `test_digests.py:1455`)
3. **La minimisation RGPD après un 429 tient-elle encore ?** En partie seulement, et c'est écrit : en parallèle, les
   items des 9 sujets partent avant qu'un 429 puisse revenir. Accepté par Sabine, car le quota couvre la demande.
   (`docs/fiches-veille.md`, « Après un 429 » ; journal ADR du 2026-11-18)
4. **Pourquoi ne pas tester le parallèle avec le jeu de référence ?** Parce que le replay donne ses réponses dans
   l'ordre des requêtes, et que cet ordre n'est pas fixe en parallèle. Le parallèle est prouvé par un fournisseur
   simulé qui répond selon le sujet lu dans la requête. (`test_digests.py`, `ProviderInParallel`)
5. **Avec un délai de 200 s, qu'est-ce qui coupe un appel bloqué ?** L'échéance de la demande, par `Deadline.cap`. Il
   n'y a plus de relance possible après un appel bloqué, classement compris : c'est le prix du choix, écrit dans
   `docs/fiches-veille.md` et l'ADR. (`deadline.py:37`, `config.py:238-253`)

## Zones non vérifiées

- **L'enregistrement du jeu de référence** : le tri est testé, mais aucun enregistrement réel n'a été lancé (un appel
  payant, réservé à Sabine).

- **L'essai réel n'est pas encore fait** : les gains (environ 105 s au lieu de 200 s) sont une estimation tirée des
  durées du 17/11. Rien ne dit encore que gpt-6.1-sol répond aussi vite à 9 requêtes simultanées qu'à une seule.
- **Le quota en parallèle** : environ 150 000 jetons estimés pour les 9 rédactions, d'après les plafonds de sortie et
  une entrée estimée, pas mesurée. Le comptage de Foundry par minute glissante n'a pas été lu.
- **Le pourquoi de 200 plutôt que 229 s** n'a pas été donné par Sabine. L'ADR l'écrit comme une déduction, à
  confirmer : un délai au-delà de l'échéance ne change rien.
- **Sécurité des fils côté OpenTelemetry** : le SDK est supposé sûr entre fils pour créer des spans et émettre des
  journaux depuis plusieurs fils (le `BatchSpanProcessor` est fait pour cela). Ce n'est pas vérifié dans sa doc.
- **Les fils de `ThreadPoolExecutor` à l'arrêt** : sur SIGTERM, le `with` attend la fin des fils en cours, chacun
  borné par l'échéance. Ce cas n'a pas de test.

## Ce qui reste

- L'essai de bout en bout sur gpt-6.1-sol (lancé par Sabine), puis la revue, la PR et la fusion.
- Si l'essai ne tient pas l'échéance : classer en parallèle, ou passer en asynchrone. C'est hors de cette mission, à
  proposer à time-knight d'abord.
- Les limites écrites après la revue (C2, C4, C5) : un appel en cours relance encore après le 429 d'un autre sujet ;
  des fils refusés ensemble relancent ensemble ; une sortie proche du plafond peut être coupée par l'échéance, faute
  des 130 s nécessaires. Rien n'est changé dans `llm_client.py`.
- `MIN_SECONDS_FOR_LLM_REQUEST` (10 s) a été calculé sur la rédaction la plus lente de gpt-6-luna (9,3 s). Une
  rédaction de gpt-6.1-sol dure 23 à 31 s : une demande au modèle lancée avec 10 à 30 s restantes peut finir en
  `llm_timeout`, ses items envoyés pour rien. La valeur reste à 10 s (constat D1 de la seconde revue, écarté par
  time-knight) ; l'essai réel le montrera s'il arrive.
- Après la fusion : le passage de la production à gpt-6.1-sol, par les gestes de Sabine.
