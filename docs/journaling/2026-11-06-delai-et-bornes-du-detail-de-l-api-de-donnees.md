# Un délai par requête et les bornes du détail de l'API de données

- **Date** : 2026-11-06
- **Branche** : `feat/data-api-bounds`
- **Issue** : #331
- **Fichiers principaux** : `src/k_b/data_api/dependencies.py`, `src/k_b/data_api/errors.py`,
  `src/k_b/data_api/routers/item_router.py`, `src/k_b/data_api/schemas/item_schema.py`,
  `src/k_b/core/config.py`, `docs/specs-api.md`
- **Série** : suite de [les bornes OWASP des deux API](2026-11-05-bornes-owasp-des-deux-api.md) et de
  [le droit par route et le débit](2026-11-05-droit-par-route-et-debit-des-deux-api.md) (#161).

## Le pourquoi

L'API de données sera en ligne au 08/11. OWASP API4:2023 (*Unrestricted Resource Consumption*)
demande qu'une requête ne puisse pas coûter sans limite. Avant cette PR, deux choses n'avaient pas
de borne.

- **Le temps d'une requête dans la base.** Une recherche `q` est un `LIKE '%…%'`, qui lit tout le
  corps des releases, jusqu'à 125 000 caractères chacun. Mesuré le 06/11 avec la pire recherche
  possible (199 « a » puis un « b ») sur 400 corps de 125 000 « a » : environ 10 s. Une recherche
  ordinaire sur 50 millions de caractères prend 0,03 s. Le pire cas est donc 300 fois plus lent que
  le cas courant, et il suffit d'une clé valide pour le déclencher.
- **Ce que sert le détail d'un item.** Une entrée Zotero servait tous ses surlignages, sans borne de
  nombre, chacun jusqu'à 10 000 caractères de texte et autant de commentaire. Un clip servait son
  texte entier, jusqu'à 1 000 000 de caractères.

Cette PR pose un délai de 5 s par requête dans la base et deux bornes au détail. La ligne API4 de
`docs/specs-api.md` passe à « Tenue ».

## Le comment

### 1. Le délai : un contrôle que SQLite appelle pendant qu'il lit

SQLite exécute une requête comme un programme : une suite d'instructions de sa machine virtuelle.
`Connection.set_progress_handler(fonction, n)` lui fait appeler une fonction Python toutes les `n`
instructions environ. Si elle rend une valeur non nulle, SQLite arrête la requête, et Python lève
`sqlite3.OperationalError('interrupted')` ([doc de `sqlite3`](https://docs.python.org/3/library/sqlite3.html),
`set_progress_handler`).

`src/k_b/data_api/dependencies.py:20-26` :

```python
    connection = connect_database_read_only(request.app.state.database_path)
    try:
        connection.set_progress_handler(
            make_deadline_check(request.app.state.query_timeout_seconds),
            INSTRUCTIONS_BETWEEN_CHECKS,
        )
        yield connection
```

Le contrôle est posé dans la dépendance `open_database`, qui ouvre la connexion de chaque requête.
Toutes les routes de données passent par elle (`Database`, `dependencies.py:50`). La liste, le
détail et ses trois lectures, les tendances : tout ce qui lit la base passe par cette connexion, et
donc par le contrôle. La fonction est passée par position : le mot-clé `progress_handler=` est
déprécié et deviendra interdit en Python 3.15.

### 2. L'échéance part du premier contrôle

`src/k_b/data_api/dependencies.py:38-45` :

```python
    deadline: float | None = None

    def check_deadline() -> int:
        nonlocal deadline
        now = clock()
        if deadline is None:
            deadline = now + timeout_seconds
        return int(now >= deadline)
```

`check_deadline` est une fermeture : elle garde `deadline` entre ses appels. Au premier appel, donc
quand SQLite a déjà commencé à lire, elle fixe l'échéance. Aux appels suivants, elle compare.

Pourquoi pas l'échéance à l'ouverture de la connexion, comme dans la première version ? La revue de
code l'a relevé (constat 1). Les routes sont des `def` et la dépendance un générateur synchrone :
FastAPI les exécute en deux passages par son pool de fils. Si le pool est occupé, la requête attend
un fil entre la dépendance et la route. Avec l'échéance posée à l'ouverture, ce temps d'attente
comptait dans les 5 s, et une requête saine pouvait recevoir un faux 503 sous charge. Posée au
premier contrôle, l'échéance ne compte que le temps passé dans la base.

`clock` est un paramètre, `time.monotonic` par défaut, comme dans `RateLimiter`
(`core/api_rate_limit.py:26`). Le test lui donne une horloge simulée. `time.monotonic` et non
`time.time` : une horloge monotone ne recule jamais, même si l'heure du système est corrigée.

### 3. L'interruption devient 503 `query_timeout`

`src/k_b/data_api/errors.py:41-43` et `:53-56` :

```python
async def handle_database_error(request: Request, error: sqlite3.Error) -> Response:
    if is_query_timeout(error):
        return respond_to_query_timeout(request)
```

```python
def is_query_timeout(error: sqlite3.Error) -> bool:
    ...
    return getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_INTERRUPT
```

Le gestionnaire des erreurs de SQLite existait déjà (500 `database_error`). L'interruption s'y
reconnaît par son code, `SQLITE_INTERRUPT` (9), et non par son message (`'interrupted'`) : un code
est un fait nommé, un message peut changer. Le `getattr` est là parce qu'une erreur levée par Python
lui-même, comme `ProgrammingError('Cannot operate on a closed database.')`, n'a pas l'attribut
`sqlite_errorcode` (essayé : `AttributeError`). Personne d'autre n'appelle `interrupt()` dans l'API,
donc `SQLITE_INTERRUPT` ne peut venir que du délai.

La réponse est `{"error": "query_timeout"}`, sans le message de SQLite ni la requête. Le journal
(`errors.py:59-66`) écrit `query_timeout: 5 s request_id=…`. La durée observée est déjà sur la ligne
de la requête (`duration_ms`), avec le même `request_id`.

### 4. Les bornes du détail : nombre et taille

`src/k_b/data_api/routers/item_router.py:161-170` :

```python
def bound_highlights(highlights: list[StoredHighlight]) -> list[StoredHighlight]:
    ...
    for highlight in highlights[:MAX_SERVED_HIGHLIGHTS]:
        length += len(highlight.text or "") + len(highlight.comment or "")
        if length > MAX_SERVED_TEXT_LENGTH:
            break
        served.append(highlight)
```

Une entrée Zotero sert ses surlignages dans leur ordre (date de création, retirés compris) tant que
deux bornes tiennent :
- leur nombre, 100 au plus ;
- la somme de leurs `text` et `comment`, 125 000 caractères au plus.

Le premier qui ne tient plus arrête la liste, et ceux qui suivent ne sont pas servis non plus.
`text` et `comment` peuvent être `None`, d'où le `or ""`.

Le texte d'un clip est coupé par une tranche, `details.body[:MAX_SERVED_TEXT_LENGTH]`
(`item_router.py:155`). Une tranche de `str` compte en points de code : elle ne coupe jamais au
milieu d'un caractère, mais elle peut séparer un emoji composé ou une lettre de son accent combiné.
La spec le dit.

Chaque coupe est dite par un booléen toujours présent, `highlights_truncated` ou `body_truncated`
(`item_router.py:150` et `:156`), déclaré dans le schéma de sa sorte (`item_schema.py`). Le
discriminateur `kind` choisit toujours le schéma, si bien que les deux champs n'apparaissent que
dans leur sorte.

### 5. 125 000, écrit à part et gardé égal

`src/k_b/data_api/routers/item_router.py:47-48` :

```python
MAX_SERVED_HIGHLIGHTS = 100
MAX_SERVED_TEXT_LENGTH = 125_000
```

125 000 est la longueur maximale du corps d'une release (`MAX_LENGTH_BY_KIND["release"]["summary"]`,
`items.py:319`, la limite de GitHub), que le détail sert déjà entier. Aucun détail ne sert donc un
texte plus long que le plus long qu'il servait déjà. La première version tirait la valeur de
`MAX_LENGTH_BY_KIND`. La revue de code (constat 5) a relevé que le contrat de l'API aurait alors
changé en silence avec une borne de l'import. La valeur est maintenant écrite en clair, et un test
la compare à celle d'une release : si l'une bouge sans l'autre, le test échoue, et la décision se
prend en voyant le contrat.

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Le mécanisme du délai | `set_progress_handler` : déterministe, synchrone, dans le fil de la requête ; la façon écrite le 05/11 dans la spec (#404). Plan validé par Sabine le 06/11. | `interrupt()` par un minuteur de la boucle (`call_later`) : une échéance tombée entre deux instructions n'arrête pas la suivante, un test à 0 s ferait courir le minuteur contre la requête, et il faut une dépendance async. Un délai asyncio autour de la route : la route tourne dans un fil, SQLite continuerait. |
| La valeur, 5 s | Au-dessus de la pire recherche honnête (0,03 s), sous les 10 s que le client de l'API IA attend chaque morceau d'une réponse (`DATA_API_READ_TIMEOUT_SECONDS`). Un test tient l'écart. | Une variable d'environnement : c'est une borne de protection, comme le débit (`DATA_API_RATE_LIMITS`), pas un réglage de déploiement (règle 2 de `poc.md`). |
| Le pas du contrôle, 100 instructions | Dépassement d'environ 70 ms ; à 1 000, environ 750 ms, et le détail et `/trends` ne passent jamais le contrôle sur la base de test. **En attente** : la revue de code (constat 2) propose 1 000 en production (chaque contrôle reprend le GIL), 1 dans les tests ; Sabine décide. | — |
| L'erreur | 503 `query_timeout`, comme l'écrivait la spec. Le client de l'API IA lit déjà tout statut ≥ 500 comme `data_api_unavailable` (`data_api_client.py:372`) : rien à changer chez lui. | 504 : il dit qu'une passerelle n'a pas eu de réponse en amont. |
| Les bornes du détail | Nombre et taille (choix de Sabine du 06/11) : sans la taille, 100 surlignages de 10 000 + 10 000 caractères feraient 2 000 000 de caractères, 16 fois le clip. | Le nombre seul, que l'issue demandait. Refuser le détail : le client ne lirait plus rien de l'item. Paginer : une route de plus, hors de la taille S. Servir le nombre total : aucun client ne le lit. |
| Où couper | Dans la route, après la lecture : `database/` appartient à l'axe PostgreSQL (#416), qui le réécrit en même temps. | Un `LIMIT` et un `substr` dans le SQL : à faire après #416, dans une issue à part (constat 4, écarté de cette PR par time-knight). |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_request_beyond_its_deadline_gives_503_query_timeout_without_detail` (`/items`, `/items/14`, `/trends`) | Chaque route lit par la connexion qui porte le délai : à 0 s, sa première lecture est arrêtée. Le corps est exactement `{"error": "query_timeout"}`, et le journal ne contient ni `interrupted` ni `SELECT`. |
| `test_the_deadline_starts_at_the_first_check_of_sqlite_not_at_the_opening` | Une attente de 30 s avant le premier contrôle ne compte pas : l'échéance tombe 5 s après lui, pas avant. |
| `test_the_deadline_of_a_request_is_below_the_read_timeout_of_the_ai_api_client` | L'app prend bien la constante, et 5 s < 10 s. |
| `test_the_highlights_beyond_their_number_are_cut_and_the_cut_is_said` | Borne à 2 : les deux premiers par date, drapeau vrai ; à 3 : les trois, drapeau faux. |
| `test_the_highlights_beyond_their_length_are_cut_and_the_cut_is_said` | Borne de taille sous la somme des trois : les deux premiers, le retiré compris dans l'ordre ; à la somme : tous. |
| `test_the_text_of_a_clip_beyond_its_length_is_cut_and_the_cut_is_said` | Borne à la longueur − 1 : `body[:longueur − 1]`, vrai ; à la longueur : entier, faux. |
| `test_the_longest_text_a_detail_serves_is_the_longest_body_of_a_release` | 125 000 reste égal à la limite d'une release. |
| `test_each_kind_has_its_detail` (zotero_entry, clip) | Les deux drapeaux sont servis, faux sans coupe ; les autres sortes n'ont pas changé. |
| Mesure du 06/11 (scratchpad, SQLite 3.50.4, Python 3.13.13) | Pire recherche sur 400 corps : environ 10 s sans délai, arrêtée vers 5,05 à 5,2 s avec. |
| `uv run pytest` (3 458 passés), `ruff check --no-cache`, `ruff format --check`, `mypy --strict` | Contrôles du dépôt verts. |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas mettre un `asyncio.wait_for` autour de la route ?** La route est un `def` :
   FastAPI la lance dans un fil du pool. Un délai asyncio rendrait la main au client, mais le fil,
   lui, continuerait sa requête SQLite jusqu'au bout. Il n'y aurait plus d'attente côté client,
   mais toujours la même consommation côté serveur. `set_progress_handler` arrête SQLite lui-même
   (`dependencies.py:22-25`).
2. **Une requête peut-elle dépasser 5 s ?** Oui, de peu. Le contrôle ne passe qu'entre deux paquets
   d'instructions : environ 70 ms de dépassement mesuré. Une instruction seule ne s'interrompt pas :
   un `LIKE` sur le texte le plus long, un clip de 1 000 000 de caractères, prend environ 0,2 s
   (extrapolé). C'est écrit dans les limites de la ligne API4.
3. **Que reçoit un client dont le détail est coupé ?** Le début de la liste ou du texte, et un drapeau
   à vrai (`item_router.py:150`, `:156`). La suite n'est pas servie. La coupe garde un début stable :
   un surlignage fait plus tard, donc daté plus tard, ne décale pas ceux déjà servis.
4. **Où est la sécurité de l'erreur ?** Le corps est fixe, sans message de SQLite, sans requête, sans
   valeur reçue (`errors.py:59-67`), comme les autres erreurs de l'API (« Erreurs » de la spec). Le
   test vérifie que le journal ne contient ni `interrupted` ni `SELECT`.
5. **Et en PostgreSQL ?** `statement_timeout` à 5 000 ms pour le rôle de l'API
   (`ALTER ROLE … SET statement_timeout`). Son dépassement donne SQLSTATE 57014 `query_canceled`, à
   traduire en même 503. Différence : il compte par instruction, pas par requête. Le détail fait
   jusqu'à trois instructions, donc 15 s en théorie. C'est noté pour #418, dans la PR et au journal
   ADR.

## Zones non vérifiées

- **Les 0,2 s d'un `LIKE` sur un clip de 1 000 000 de caractères** sont extrapolées de la mesure sur
  125 000 caractères (24 ms par corps), pas mesurées.
- **Le coût du GIL sous charge** vient des essais du relecteur du plan (une requête de 3 ms devient
  plusieurs secondes à côté d'un fil qui calcule sans pause ; 46 → 70 ms sous une charge par
  à-coups). Ils n'ont pas été refaits ici. C'est l'objet du constat 2, en attente.
- **PostgreSQL** : rien n'est essayé. `statement_timeout` et son comptage par instruction viennent de
  la doc de PostgreSQL 17 (`runtime-config-client.html`, par Context7). Le code 57014 vient de
  l'annexe A (`errcodes-appendix.html`), lue dans une version ancienne seulement. Le refus du
  paramètre `options` par PgBouncer n'est pas vérifié.
- **Les valeurs 100 et 125 000** ne reposent sur aucune mesure de la bibliothèque Zotero réelle : la
  base de test a 6 surlignages.

## Ce qui reste

- **Borner la lecture elle-même** (`LIMIT 101` des surlignages, `substr` du texte d'un clip) : après
  #416, dans une issue à part (constat 4 de la revue de code). Aujourd'hui, la lecture n'est bornée
  qu'en temps, par le délai.
- **Le pas du contrôle** (100 ou 1 000) : en attente de la décision de Sabine (constat 2).
- **Un plafond de requêtes simultanées** pour l'API de données, que l'API IA a déjà (« une demande à
  la fois »). Le délai se multiplie par le débit (120 listes par minute, 5 s chacune au plus). C'est
  la décision ouverte « Une limite de connexions du serveur » du journal ADR, au jalon ACA.
- **Le délai en PostgreSQL** : #418.
