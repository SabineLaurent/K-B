# Borner la réponse de l'API IA que lit `kb`

- **Date** : 2026-11-06
- **Branche** : `feat/bounded-response-read`
- **Issue** : #422 (limite restante portée par #436)
- **Fichiers principaux** : `src/k_b/post/ai_api_client.py`, `src/k_b/core/config.py`,
  `src/k_b/core/outbound.py` (lu, non modifié)
- **Série** : la même borne pour la réponse du modèle,
  [2026-11-05-bornes-owasp-des-deux-api.md](2026-11-05-bornes-owasp-des-deux-api.md).

## Le pourquoi

`kb digest` et `kb trend-report` demandent leurs fiches à l'API IA (`POST /digests`,
`POST /trend-reports`). Jusqu'ici, ils lisaient sa réponse entière, sans limite de taille ni de
durée. Sabine avait accepté ce risque pour le POC, le 2026-10-21 puis le 2026-10-30, parce que l'API
IA est son propre service, à une adresse qu'elle règle. Ce risque devait se refermer à la mise en
ligne, et la mise en ligne arrive (#423).

Une réponse sans borne peut remplir la mémoire de `kb`, ou le tenir sans fin si elle arrive au
compte-gouttes (OWASP API4:2023, consommation des ressources ; API10:2023, une réponse d'API est une
entrée non fiable). Les quatre autres clients HTTP de K-B lisaient déjà leurs réponses par une même
fonction, `read_bounded_body` : les trois clients de l'API IA (API de données, modèle, GitHub) et la
collecte. Il restait `kb`.

Les deux commandes passent par une seule fonction, `send_request`. Corriger cette fonction suffit
donc pour les deux.

## Le comment

### 1. Lire en flux plutôt que d'un bloc

Avant, `http_client.post(path, json=body)` lisait tout le corps avant de rendre la main. Désormais,
la réponse est ouverte en flux, puis lue par la borne commune (`src/k_b/post/ai_api_client.py:229-232`) :

```python
        with http_client.stream("POST", path, json=body) as response:
            status = response.status_code
            try:
                content = read_bounded_body(response, MAX_AI_API_ANSWER_BYTES, is_late)
```

Avec `stream`, httpx2 rend la réponse dès qu'il a lu l'en-tête : le statut et les en-têtes sont
connus, mais le corps n'est pas encore lu. Le `with` ferme la connexion sur tous les chemins, y
compris quand on lève une erreur au milieu du corps (doc d'httpx2, « Streaming responses », lue par
Context7 le 2026-11-06).

### 2. La borne commune : la taille et l'échéance

`read_bounded_body` (`src/k_b/core/outbound.py:82-87`) lit le corps morceau par morceau :

```python
    for chunk in response.iter_bytes():
        body += chunk
        if len(body) > max_bytes:
            raise BodyTooLargeError
        if is_late is not None and is_late():
            raise BodyTooLateError
```

Avant cette boucle, un `Content-Length` annoncé au-delà de la borne est refusé sans rien lire
(`outbound.py:73-80`). La taille se compte en octets **décodés** : un corps compressé est compté
une fois décompressé.

L'échéance est une fonction `is_late`, que `send_request` construit à partir d'une horloge
(`ai_api_client.py:223-226`) :

```python
    deadline = clock() + AI_API_REQUEST_DEADLINE_SECONDS

    def is_late() -> bool:
        return clock() >= deadline
```

Pourquoi une échéance en plus du délai de lecture ? Le délai de lecture d'httpx2 borne **chaque**
attente d'un morceau, jamais la réponse entière. Une réponse qui envoie un octet toutes les 239 s ne
le dépasse jamais. L'échéance, elle, compte depuis l'envoi.

### 3. Les deux bornes (`src/k_b/core/config.py:441-454`)

- `MAX_AI_API_ANSWER_BYTES = 8_000_000`. Son nom la distingue de `MAX_AI_API_BODY_BYTES`, qui borne
  le corps d'une **demande** reçue par l'API IA.
- `AI_API_REQUEST_DEADLINE_SECONDS = AI_API_READ_TIMEOUT_SECONDS`, soit 240 s, la limite que
  l'ingress d'Azure Container Apps laisse à une requête. C'est la même connaissance, écrite une
  fois.

### 4. Un état nommé, et jamais le corps

Au-delà de la borne, l'erreur prend l'état du statut HTTP (`ai_api_client.py:233-242`) :

```python
            except BodyTooLargeError:
                # Any status keeps its state; a 200 beyond the bound is an invalid answer.
                raise AiApiError(
                    find_failure_state(status) or "ai_api_invalid_response",
```

`find_failure_state` (`ai_api_client.py:276`) est la correspondance entre le statut et l'état, qui
était écrite en ligne dans `read_response`. Elle en sort pour servir aux deux endroits. Elle rend
`None` pour un 200, et le `or` transforme ce 200 en réponse invalide. Une 5xx reste donc
`ai_api_failed` même si son corps est trop grand.

Le message ne contient que l'état, le statut, `response larger than 8000000 bytes` et deux en-têtes.
Ces en-têtes passent par `describe_headers` (`ai_api_client.py:302`) : `X-Request-ID`, pour retrouver
la demande dans `logs/kb-serve-ai.log`, et `Retry-After`. Une valeur hors de sa règle est tronquée et
échappée par `quote_value` (règle 3 de `conventions.md`). Rien du corps n'entre dans le message,
qui est affiché et journalisé par les commandes (règle 5 de `poc.md`). Une échéance dépassée garde
aussi ses en-têtes (`ai_api_client.py:243-246`).

### 5. `Answer` à la place de `httpx2.Response`

Une fois le flux fermé, un `httpx2.Response` n'a plus de `content`. `send_request` rend donc une
petite dataclass, `Answer(status_code, headers, content)` (`ai_api_client.py:93`), que
`read_response` et `describe_answer` lisent comme avant. `trend_report_client.py` n'a pas changé :
il appelle `read_response(send_request(...))`.

## Choix faits et options écartées

| Choix | Retenu, pourquoi | Écarté, pourquoi |
|---|---|---|
| Valeur de la borne | 8 000 000 d'octets. Le pire que permettent les bornes du code, tous caractères échappés en `\u00XX` (6 octets, sérialisation de FastAPI), est d'environ 5,7 Mo pour `POST /digests` (300 items, titre de 1 024 caractères, URL de 2 000, 12 affirmations de 400 caractères par fiche) et 1,7 Mo pour `POST /trend-reports`. Sans échappement : 1,7 Mo et 1 Mo. | 4 Mo comme l'API de données : sous ce pire. |
| Une borne ou deux | Une seule, pour un seul client. | Une par route : deux constantes, sans gain. |
| Échéance | 240 s depuis l'envoi, la borne de l'ingress d'ACA. | Aucune échéance : une réponse au compte-gouttes tiendrait `kb` sans fin. Déplacer `Deadline` de `ai_api/` vers `core/` : `post` n'importe pas `ai_api` (test d'architecture), et 17 fichiers l'importent. |
| Horloge | Paramètre `*, clock=time.monotonic` de `send_request`, comme `Deadline` et `core/api_rate_limit.py`. | Patcher `time.monotonic` dans les tests : les deux se valent, le paramètre est explicite. |
| État d'une réponse trop grande | Celui de son statut. | Un état nouveau `ai_api_response_too_large` : le code de sortie (1) ne changerait pas, et les autres clients nomment ce cas `…_invalid_response` (API de données, GitHub) ou `llm_unavailable` (modèle). Toujours `ai_api_invalid_response` : on recopierait le défaut que #376 relève, une 5xx nommée réponse invalide. |
| Lien avec #376 | Écart voulu : `kb` lit le corps d'une 5xx, dans sa borne, pour afficher son `error`. time-knight n'y voit pas de contradiction. | Étendre à `kb` la règle de #376 (« ne pas lire le corps d'une 5xx »). |
| Constats de la revue de code écartés (tranchés par time-knight, délégation de Sabine du 15/10) | — | Un corps complet à l'échéance est jeté : sans `Content-Length`, on ne sait qu'un morceau est le dernier qu'en tirant le suivant, et l'ingress coupe à 240 s de toute façon. Une marge plus courte pour le serveur : le pool, la connexion et l'écriture prennent des millisecondes sur la machine. Mettre `Answer` en commun : cela toucherait les connecteurs de l'API IA. |

## Preuve

Tous les tests ci-dessous sont dans `tests/post/test_ai_api_client.py`, sauf les deux derniers.

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_an_answer_of_the_bound_is_read` | Une réponse valide de 8 000 000 d'octets exactement, à la vraie borne, est acceptée. |
| `test_an_answer_announced_beyond_the_bound_is_refused_before_reading` | Un `Content-Length` trop grand est refusé sans lire le corps : le flux `UnreadStream` ferait échouer le test s'il était lu. |
| `test_an_answer_counted_beyond_the_bound_stops_its_reading_and_never_quotes_it` | Sans `Content-Length`, le corps est compté et la lecture s'arrête avant la fin. Le repère placé dans le corps n'est pas cité, et `X-Request-ID` l'est. |
| `test_an_answer_counted_up_to_the_bound_is_read_and_one_byte_more_is_refused` | Un corps compté de 1 000 octets passe, 1 001 sont refusés : la mutation `>` → `>=` meurt. |
| `test_a_failure_beyond_the_bound_keeps_the_state_of_its_status` | Une 503 trop grande reste `ai_api_failed`, avec ses en-têtes. |
| `test_an_answer_still_read_at_its_deadline_is_ai_api_timeout`, `test_an_answer_read_before_its_deadline_is_kept_whole` | L'échéance coupe entre deux morceaux, à 240 s et pas à 239. |
| `test_a_failure_in_the_middle_of_an_answer_gives_its_state_without_the_url` | `ReadError`, `ReadTimeout` ou `DecodingError` au milieu du corps donnent leur état, sans l'URL. |
| `test_digest_on_an_answer_beyond_its_bound_never_shows_nor_logs_it_and_exits_1` (`tests/commands/test_digest_command.py:389`) | Le critère de l'issue pour `kb digest` : code 1, l'état sur la sortie d'erreur, le repère ni sur stdout, ni sur stderr, ni dans `logs/kb.log`, et aucune fiche écrite. |
| `test_an_answer_beyond_its_bound_writes_nothing_never_shows_nor_logs_it` (`tests/commands/test_trend_report_command.py:537`) | Le même critère pour `kb trend-report`, et le registre reste inchangé. |
| Tests écrits d'abord | 7 rouges avant le code (constante absente, paramètre `clock` inconnu), puis 1 rouge avant la correction des en-têtes à l'échéance. |
| `uv run pytest` | 3 471 passés. `ruff check --no-cache`, `ruff format --check` et `mypy --strict` sont verts. |

## Ce que tu dois pouvoir défendre

1. **Pourquoi une échéance, si httpx2 a déjà un délai de lecture ?** Le délai de lecture borne
   chaque attente d'un morceau, pas la réponse entière. Une réponse au compte-gouttes ne le dépasse
   jamais. L'échéance compte depuis l'envoi (`ai_api_client.py:223`).
2. **Le corps d'une réponse refusée peut-il apparaître dans un journal ?** Non. `BodyTooLargeError`
   ne porte rien, l'erreur est levée `from None`, et le message n'est fait que de l'état, du statut,
   de la borne et de deux en-têtes échappés (`ai_api_client.py:233-246`). Les deux tests de commande
   le vérifient avec un repère.
3. **Pourquoi 8 Mo plutôt que 4 ?** Parce que le pire que le code permet, tous caractères échappés,
   approche 5,7 Mo. 4 Mo pourrait refuser une réponse honnête, alors que 8 Mo ne coûtent rien en
   mémoire à `kb`.
4. **La réponse est-elle bornée en temps dans tous les cas ?** Non. Rien ne borne l'attente avant
   le premier morceau décodé : chaque lecture de l'en-tête attend 240 s au plus, mais pas leur
   somme. Rien ne borne non plus un corps compressé fait de blocs vides. C'est un défaut de
   `read_bounded_body` pour ses quatre clients, déjà présent sur `main`, porté par #436. En ligne,
   l'ingress d'ACA coupe une requête à 240 s.
5. **Pourquoi une 5xx trop grande donne-t-elle `ai_api_failed` et non une réponse invalide ?**
   Parce qu'une panne reste une panne, quel que soit son corps. C'est le défaut que #376 relève
   dans deux clients de l'API IA, et il n'est pas recopié ici (`find_failure_state`,
   `ai_api_client.py:276`).

## Zones non vérifiées

- **La taille réelle des réponses** : le chiffre de 8 Mo repose sur les bornes du code, pas sur la
  mesure d'une vraie réponse de `POST /digests` ou de `POST /trend-reports`.
- **La sérialisation de FastAPI** (JSON compact, non-ASCII en UTF-8, contrôle en `\u00XX`) a été
  vérifiée par le relecteur du plan, dans la version installée (0.143.1), pas par un test du dépôt.
- **La coupure à 240 s par l'ingress d'ACA** est reprise de la doc du dépôt. Elle n'a pas été
  observée.
- **Les morceaux de `MockTransport`** : les tests supposent que `httpx2.Response(content=générateur)`
  rend un corps sans `Content-Length`, lu morceau par morceau. Les tests le confirment
  indirectement (la lecture s'arrête avant la fin), sans test sur le réseau réel.

## Ce qui reste

- **#436** : borner l'attente avant le premier morceau décodé, et les morceaux bruts qui ne se
  décodent en rien, dans `read_bounded_body`, pour ses quatre clients.
- **#376** : une 5xx au corps trop grand dans les clients de l'API IA vers l'API de données et
  GitHub. Le commentaire posté sur #376 dit ce que `kb` fait déjà.
- **`Answer`** existe en double (`post/ai_api_client.py` et `ai_api/connectors/github_client.py`) :
  la mise en commun touche les connecteurs de l'API IA, hors de #422.
