# Tester la chaîne des fiches sur les deux API servies pour de vrai

- **Date** : 2026-11-08
- **Branche** : `test/live-api-chain`
- **Issue** : #26 (sœur : #462, la même chaîne pour `kb trend-report`)
- **Fichier principal** : `tests/commands/test_live_apis.py` (seul fichier de code de la PR ; `src/` n'est pas touché)

Note qui couvre les commits 574dc19 (le test) et 3a6ef85 (les deux API construites par `kb serve-data` et
`kb serve-ai`, après la revue).

## Le pourquoi

Jusqu'ici, chaque maillon de la chaîne des fiches avait ses tests, mais jamais les trois ensemble :
`kb digest` simulait l'API IA par `httpx2.MockTransport` (`tests/commands/test_digest_command.py`), et l'API IA
simulait son client de l'API de données par une surcharge de dépendance (`tests/ai_api/test_digest_router.py`).
Personne ne vérifiait qu'une requête partie de `kb digest` traverse vraiment l'API IA, puis l'API de données, et
revient en fiche. La certif l'a relevé pour C10 d'E3 : le critère « les tests d'intégration couvrent tous les
points de terminaison exploités » est jugé partiel tant que le client simule l'API IA.

Ce test lance les deux API pour de vrai, sur des ports de la machine, et fait passer par elles `kb digest`
(`POST /digests`, puis les routes de lecture de l'API de données) et `kb smoke-test` (`GET /health` des deux).
Seuls restent simulés le modèle (le rejeu, prévu par le critère de #26) et, pour `kb smoke-test`, l'identité
managée et le stockage d'échange, qui sont des services d'Azure.

## Le comment

### Servir une app dans un fil, sur un port libre

```python
listening = socket.create_server(("127.0.0.1", 0))
port = listening.getsockname()[1]
server = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False))
thread = threading.Thread(target=server.run, kwargs={"sockets": [listening]}, daemon=True)
```
`tests/commands/test_live_apis.py:75-81`

Le port 0 demande au système un port libre : deux tests, ou deux CI, ne se gênent jamais. La socket est ouverte
par le test et donnée à uvicorn (`sockets=`) : le port est connu avant le démarrage, sans le lire dans
uvicorn. Le serveur tourne dans un fil, pas dans un processus : uvicorn n'y pose aucun gestionnaire de signal
(`uvicorn/server.py:332-335` vérifie le fil principal), et pytest garde les siens. Le test attend
`server.started`, puis, en sortie, met `server.should_exit` et vérifie que le fil s'est bien arrêté
(`test_live_apis.py:84-93`) ; sinon le test échoue au lieu de laisser un serveur tourner sous les tests suivants.

### Les apps telles que `kb serve-*` les construisent

```python
monkeypatch.setattr(uvicorn, "run", lambda app, **options: apps.append(app))
assert run_command() == cli.ExitCode.SUCCEEDED
[app] = apps
```
`tests/commands/test_live_apis.py:101-103`

Au lieu de recopier l'appel de `create_app`, le test lance `run_serve_data` et `run_serve_ai` sur leurs
variables d'environnement, avec un `uvicorn.run` remplacé qui garde l'app au lieu de la servir. Le même procédé
existe déjà dans `tests/ai_api/test_serve_ai.py:89-97`. L'app servie passe donc par tout ce que fait le vrai
démarrage : la lecture des clés, du rejeu (`KB_LLM_PROVIDER=replay`, `KB_LLM_REPLAY_FILE`), de la fenêtre
(`KB_DIGEST_WINDOW_DAYS`), de l'URL et de la clé de l'API de données, le refus d'une clé partagée entre les deux
API. Les noms des variables sont repris des constantes du code (`DATA_API_KEY_VARIABLE`, `DIGEST_KEY_VARIABLE`…) :
un renommage dans `src/` casse le test au lieu de le laisser vert à tort.

### Les réglages propres au test, nommés

```python
monkeypatch.setattr(serve_ai_command, "DIGEST_SUBJECTS", TEST_SUBJECTS)
...
ai_app.dependency_overrides[read_request_time] = lambda: REQUEST_TIME
```
`tests/commands/test_live_apis.py:127` et `:141`

Côté API, deux réglages seulement : les sujets des tests, jamais les vrais (une modification de la vraie liste
ne casse aucun test, comme dans `test_digest_router.py`), et l'horloge de l'API IA, figée au 2026-10-08, pour
que la fenêtre de 14 jours tombe sur les items de la base de test. Côté `kb digest`, deux réglages aussi
(`test_live_apis.py:152-153`) : les mêmes sujets, et le jour de la fiche (`read_today`), pour que son nom
(`2026-10-08.md`) ne dépende pas du jour où le test tourne.

### Ce que vérifie le test des fiches

```python
assert SECURITY_CLAIM["text"] in security_sheet
assert SECURITY_SOURCE_TITLE in security_sheet
```
`tests/commands/test_live_apis.py:173-174`

L'affirmation vient du rejeu ; le titre de la source (`Apple Multiple Products Out-of-Bounds Write
Vulnerability`) ne vient que de la base de test, lue par l'API de données. Les deux dans la même fiche prouvent
que la fiche a traversé les trois maillons. Le résumé de `kb digest` est vérifié aussi : la fenêtre, les
10 items lus, le modèle `replay` (`test_live_apis.py:178-179`).

## Choix faits et options écartées

| Choix | Retenu, pourquoi | Écarté, pourquoi |
|---|---|---|
| Comment lancer les API | uvicorn dans un fil, sur une vraie socket : du vrai HTTP, en local | Sous-processus `kb serve-ai` et `kb serve-data` : leur horloge ne peut pas être figée, il faudrait une base datée par rapport au jour du test. `ASGITransport` de httpx : pas de vrai HTTP, trop proche du `MockTransport` relevé par la certif |
| Comment construire les apps | par `run_serve_data` et `run_serve_ai`, l'app gardée à `uvicorn.run` (constat 1 de la revue, tranché par time-knight) | Recopier `create_app` : le démarrage de `kb serve-*` (lecture des variables, refus d'une clé partagée) n'aurait pas été couvert |
| Le modèle | le rejeu (`replay`), lu d'un fichier comme en vrai | Un modèle réel : il faudrait une clé et le réseau, et le critère de #26 les exclut |
| La portée des fixtures | une paire de serveurs par test | Portée module : l'état de l'API IA (limiteur de débit) serait partagé entre les tests ; le gain est d'environ 1 s |
| Où mettre le test | `tests/commands/`, dont les fixtures autouse retirent les réglages du terminal | Un dossier neuf : il faudrait recopier ces fixtures |
| `kb trend-report` | hors de cette PR, issue #462 | Dans #26 : #369 change `POST /trend-reports` en ce moment |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run pytest tests/commands/test_live_apis.py` : `2 passed` | `kb digest` écrit ses fiches par les deux API servies, et `kb smoke-test` joint leur `/health` |
| Chaîne cassée (l'API IA pointée sur `http://127.0.0.1:9`, un port fermé) : `ERROR k_b.cli: digests not received: ai_api_failed, HTTP 502, error data_api_unavailable`, `1 failed` | Le test dépend vraiment de l'API de données : sans elle, il échoue |
| Les deux URL des API de `kb smoke-test` sur `http://127.0.0.1:9` : `2 failed` (sur la première construction, 574dc19) | Le test de `kb smoke-test` dépend vraiment des serveurs |
| `uv run pytest` : `3833 passed, 328 deselected` ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` verts | Rien d'autre n'est cassé |

## Ce que tu dois pouvoir défendre

1. **« Le modèle est simulé : est-ce encore un test d'intégration ? »** Oui, de K-B : tous ses points de
   terminaison exploités par la chaîne sont appelés en vrai HTTP, de `kb digest` jusqu'à la base. Le modèle est
   un service externe ; le critère de #26 demande le rejeu, pour tourner en CI sans clé
   (`test_live_apis.py:130-131`).
2. **« Vous surchargez l'horloge : la chaîne est-elle encore la vraie ? »** L'horloge n'est pas un maillon :
   elle fixe seulement la fenêtre. Sans elle, il faudrait une base datée par rapport au jour du test. C'est la
   seule surcharge de l'API IA, nommée dans la docstring (`test_live_apis.py:109-112`, `:141`).
3. **« Que se passe-t-il si un serveur ne s'arrête pas ? »** Le test échoue (`assert not thread.is_alive()`,
   `test_live_apis.py:93`), au lieu de laisser un serveur sous les tests suivants.
4. **« Le test sort-il de la machine ? »** Non : les deux serveurs écoutent sur `127.0.0.1`, le modèle est le
   rejeu, l'identité et le stockage de `kb smoke-test` sont simulés par `FakeTransport`
   (`test_live_apis.py:193-207`), et le jeton GitHub, lu au démarrage, n'est jamais envoyé : aucune route des
   fiches n'appelle GitHub.
5. **« Où est la sécurité ? »** Les clés sont tirées au hasard à chaque test (`secrets.token_urlsafe(32)`),
   jamais écrites en dur ; l'API IA garde son contrôle de clé et la vérification qu'elle ne partage pas celle
   de l'API de données, puisque le test passe par `run_serve_ai`.

## Zones non vérifiées

- `Server.run(sockets=…)`, `Server.started` et `Server.should_exit` viennent du code source d'uvicorn 0.54.0
  (`uvicorn/server.py:72-73`, `:85`, `:205`), pas de sa documentation : Context7 (0.54.0, consulté le
  2026-11-08) ne montre que `server.run()` et `server.serve()`. Une montée d'uvicorn peut les changer ; le test
  le dirait en échouant.
- L'API de données ne tourne que sur la base de test SQLite : la même chaîne sur PostgreSQL n'est pas testée.
- La CI de la PR n'a pas encore tourné au moment d'écrire cette note : le vert ci-dessus est celui du Mac.

## Ce qui reste

- La même chaîne pour `kb trend-report` → `POST /trend-reports` (rejeu et GitHub simulé) : #462, après #369.
- Une variante PostgreSQL de l'API de données, si Sabine la juge utile : aucune issue pour l'instant.
