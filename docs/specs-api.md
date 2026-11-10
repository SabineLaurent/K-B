# Spécifications de l'API de données

L'API de données sert la veille et la bibliothèque de K-B, en lecture seule, sur la machine de
Sabine. Elle est appelée par les programmes de Sabine (terminal, scripts), par des agents, et par
l'API IA si celle-ci lit la base. Ce document fixe ce qu'elle sert, la règle de « quoi de neuf », l'accès par clé, les
erreurs et les exigences de sécurité. Les décisions et leur pourquoi sont dans le
[journal ADR](ADR/journal-decisions-projet.md) (entrées du 2026-10-14) ; la collecte, dans
[specs-collecte.md](specs-collecte.md) ; la base, dans [stockage.md](stockage.md).

**Version de la spec : 0.11.0**, la même que `info.version` de l'OpenAPI
(`docs/api/openapi-donnees.json`, que #184 écrit). Un changement de comportement visible par un client, comme
l'ordre des résultats, change la version.

| Version | Ce qui change pour un client |
|---|---|
| 0.1.0 | `GET /items` (#184) |
| 0.2.0 | `GET /items/{item_id}` et `GET /trends` servis (#185) ; un `item_id` au-delà de 64 bits répond 422 |
| 0.3.0 | `GET /health` servi sans clé ; hôte, port et hôtes permis réglables (#199) |
| 0.4.0 | la sorte `clip` (pages gardées avec Web Clipper) servie par `GET /items` et `GET /items/{item_id}` (#14) |
| 0.5.0 | l'en-tête `X-Request-ID` sur chaque réponse ; les tags `items` et `trends` dans l'OpenAPI ; les clés des clients lues dans `KB_DATA_API_KEY_<CLIENT>`, et non plus `KB_API_KEY_<CLIENT>` (#156) |
| 0.6.0 | `/docs` et `/openapi.json` servis seulement si `KB_DEPLOYMENT_ENVIRONMENT=sandbox` ; 404 sinon (#393) |
| 0.7.0 | `kind` pris 7 fois au plus, autant que de sortes ; au-delà, 422 (#161) |
| 0.8.0 | une limite de débit par client et par route ; au-delà, 429 `rate_limit_exceeded` (#161) |
| 0.9.0 | `HEAD` refusé sur `/health`, et sur `/docs` et `/openapi.json` en `sandbox`, comme il l'était déjà sur les routes de données : 405 `method_not_allowed`, `Allow: GET` (#161) |
| 0.10.0 | une requête a 5 s dans la base ; au-delà, 503 `query_timeout` ; le détail d'une entrée Zotero sert 100 surlignages et 125 000 caractères de leur texte et commentaire au plus, et celui d'un clip 125 000 caractères de son texte, la coupe dite par `highlights_truncated` et `body_truncated` (#331) |
| 0.11.0 | la base PostgreSQL que nomme `KB_DATABASE_URL` servie, et non plus le fichier SQLite ; sur elle, une base injoignable ou sans tables répond 500 `database_error`, et non 503 `database_missing` ; au-delà de 4 lectures en même temps, une requête attend 2 s puis répond 500 `database_error` ; la recherche `q` rend les mêmes résultats qu'en SQLite (#418) |

## Règles communes

- **Locale par défaut** : l'API écoute sur `127.0.0.1:8000` ; `TrustedHostMiddleware` n'accepte
  que les hôtes `127.0.0.1` et `localhost`. Les défauts sont nommés dans `core/config.py` ; chacun
  se change par une variable d'environnement (règle 2 de `.claude/rules/poc.md`) :
  - `KB_DATA_API_HOST` : l'hôte d'écoute, une adresse IPv4 (`0.0.0.0` en conteneur : le
    `127.0.0.1` d'un conteneur est le sien, injoignable d'ailleurs). Pas d'IPv6 : le `Host` d'un
    client en IPv6 garde ses crochets (`[::1]`), qu'aucun hôte permis ne peut nommer ;
  - `KB_DATA_API_PORT` : le port, des chiffres seuls, de 1 à 65535 ;
  - `KB_DATA_API_ALLOWED_HOSTS` : les hôtes permis, séparés par des virgules (`api-donnees,localhost`
    pour qu'un autre conteneur l'appelle par son nom de service). Chaque entrée est un nom en
    minuscules, sans `*` ni port : `TrustedHostMiddleware` compare le `Host` reçu tel quel, et `*`
    laisserait passer tout hôte.

  Une valeur refusée (hôte hors adresse IPv4, port hors bornes, liste ou entrée vide, entrée avec
  `*`, entrée hors motif) fait sortir `kb serve-data` en code 2 avant d'écouter, avec un message qui
  nomme la variable et la position de l'entrée. En conteneur, le port est publié sur `127.0.0.1`
  de la machine (#200). Pas de CORS.
- **Lecture seule** : GET seulement. La base est celle que nomme `KB_DATABASE_URL`
  ([stockage.md](stockage.md), « Le SGBD »), lue en lecture seule sur les deux moteurs, par
  `connect_reader` (`database/engine.py`) :
  - en SQLite, le fichier est ouvert en `mode=ro`, une connexion par requête ;
  - en PostgreSQL, `kb serve-data` ouvre au démarrage un pool de 1 à 4 connexions
    (`psycopg-pool`, `READING_POOL_MIN_SIZE` et `READING_POOL_MAX_SIZE`, `core/config.py`), qui se
    connecte en arrière-plan : `kb serve-data` démarre sans attendre la base, comme en SQLite. Chaque
    connexion lit en `REPEATABLE READ READ ONLY` : une écriture est refusée par le serveur (SQLSTATE
    25006), et les lectures du détail voient un seul état de la base. Une requête attend une
    connexion 2 s au plus (`READING_POOL_WAIT_SECONDS`), puis répond 500 `database_error`
    (`PoolTimeout` au journal) ; une connexion coupée (redémarrage, bascule du serveur) n'est pas
    prêtée. Chaque connexion revient au pool sans transaction, sur un succès comme sur une erreur ;
    une session que le serveur a finie avant (redémarrage, coupure) laisse à la requête sa réponse ou
    sa propre erreur, se journalise `reader_session_lost: <type de l'erreur>`, sans message, et le
    pool remplace la connexion.
    Les lignes de `psycopg` et `psycopg_pool` sous ERROR ne sont pas journalisées
    (`LIBRARY_LOG_LEVELS`, `commands/run_log.py`) : elles citent le texte de libpq et la connexion
    (hôte, utilisateur, base). Une base injoignable ne se voit donc qu'à la requête, par
    `database_error: PoolTimeout`.
- **Délai** : une requête a 5 s dans la base (`DATA_API_QUERY_TIMEOUT_SECONDS`, `core/config.py`).
  En SQLite, elles sont comptées depuis le premier contrôle de sa première lecture, le temps de
  Python entre deux lectures compris ; l'attente d'un fil (le pool de fils de Starlette), avant la
  dépendance et avant la route, ne compte pas. Au-delà,
  SQLite arrête la lecture et l'API répond 503 `query_timeout`, sans le message de SQLite. Le
  contrôle passe toutes les 1 000 instructions de SQLite (`set_progress_handler`,
  `database/engine.py`) : chaque contrôle reprend le GIL de Python, et 1 000 en font dix fois
  moins que 100 pour les autres requêtes (revue de code, tranché par time-knight, que Sabine a
  laissé trancher le 2026-11-06). 5 s, mesuré par l'API le 2026-11-06 : la pire recherche `q`
  (199 « a » puis « b ») sur 400 corps de release de 125 000 « a » prend environ 10 s sans délai ;
  avec lui, l'API répond 503 à 5,75 s (5,10 s à 100 instructions) ; une recherche ordinaire prend
  0,02 s. 5 s reste sous les 10 s que le client de l'API IA attend chaque morceau d'une réponse
  (`DATA_API_READ_TIMEOUT_SECONDS`). Limites :
  - le dépassement croît avec le coût d'une instruction, et une instruction seule ne s'interrompt
    pas : mesuré, 0,75 s sur des releases, le texte d'un tiers ; non mesuré sur des clips de
    1 000 000 de caractères, le texte de Sabine, où un `LIKE` prend environ 0,2 s (extrapolé) et
    un paquet de 1 000 instructions plusieurs secondes ;
  - sous charge, l'attente du pool, non comptée, peut porter la réponse au-delà des 10 s du client
    de l'API IA, qui lit alors `data_api_timeout` au lieu du 503 : une erreur dans les deux cas ;
  - à côté d'un fil Python qui calcule sans pause, une requête de 3 ms en prend 1,5 s à 1 000
    instructions (essai du relecteur du plan).

  En PostgreSQL, le même délai est le `statement_timeout` de chaque connexion du pool, posé par
  K-B à son ouverture (`SET_STATEMENT_TIMEOUT`, `database/postgresql.py`), pas par le serveur : une
  base installée sans réglage n'est jamais lue sans délai, et la valeur est dans le dépôt, la même
  pour les deux moteurs. Au-delà, le serveur arrête l'instruction (SQLSTATE 57014) et l'API répond
  le même 503 `query_timeout`. Un délai de moins d'1 ms est refusé au démarrage : à 0,
  `statement_timeout` n'arrête plus rien. Écartés : `ALTER ROLE … SET statement_timeout` (la valeur
  hors du dépôt, et un oubli à l'installation laisse la lecture sans délai) ;
  `options=-c statement_timeout` dans l'URL (refusé par un pooler comme PgBouncer) ; `SET LOCAL` à
  chaque requête (utile derrière un pooler en mode transaction seulement) ; `transaction_timeout`
  (il ferme la session). Journal ADR, 2026-11-06, « API de données sur PostgreSQL ». Limites :
  - le délai compte par instruction, pas par requête : la liste et les tendances en font une, le
    détail jusqu'à trois (15 s au plus en théorie) ;
  - l'attente d'une connexion (2 s au plus) s'ajoute : avec une instruction, 7 s, sous les 10 s du
    client de l'API IA ;
  - une instruction annulée par un administrateur (`pg_cancel_backend`) lève aussi 57014 et
    répond aussi 503 `query_timeout`.
- **Clé** : chaque route de données demande `Authorization: Bearer <clé>`. `/health` est public,
  `/docs` et `/openapi.json` aussi quand ils sont servis : ils ne contiennent aucune donnée.
- **Documentation** : `/docs` et `/openapi.json` ne sont servis que si
  `KB_DEPLOYMENT_ENVIRONMENT=sandbox`. Avec `production`, une autre valeur ou rien, ils répondent
  404 : une variable oubliée ou mal écrite ne montre rien (décision de Sabine du 2026-11-04, #393).
  Ce n'est pas une mesure de sécurité : la clé protège les données. Le contrat reste versionné :
  `kb openapi` l'écrit depuis l'application, que la route soit servie ou non.
- **Santé** : `GET /health` répond 200 `{"status": "ok"}`, sans clé, pour la sonde d'un conteneur,
  qui doit envoyer `GET` : `HEAD` y répond 405, comme sur toute route.
  Il dit que le processus répond, rien d'autre : ni version, ni chemin, ni état de la base (une
  sonde qui ouvrirait la base ferait redémarrer le conteneur en boucle tant que la base manque).
  C'est une route de Starlette, comme `/docs` : la clé reste posée sur toute l'app, et aucune route
  de données ne peut l'oublier. Elle est hors de l'OpenAPI, comme `/docs` ; ce document
  l'inventorie. Le `Host` de la sonde doit être un hôte permis. Un appel de `/health` qui répond
  200 n'est pas journalisé (une sonde toutes les quelques secondes noierait les requêtes des
  clients) ; tout autre statut l'est, si bien qu'une sonde mal réglée se voit.
- **Réponses** : JSON, champs en liste blanche (modèles de réponse propres à l'API, jamais le
  modèle de lecture des sources).
- **OpenAPI** : `kb openapi` (#184) écrit `docs/api/openapi-donnees.json`, versionné ; la CI le compare
  au schéma produit par l'app.
- **Journal** : une ligne par requête, horodatée en ISO 8601 UTC, à la seconde. Elle donne la
  méthode, le gabarit de route (`/items/{item_id}`, pas l'identifiant), le statut, la durée en ms
  et le nom du client (`-` pour un statut sans réponse envoyée, une route inconnue ou un client
  sans clé valide), puis l'identifiant de la requête (`request_id`, un UUID), rendu aussi dans
  l'en-tête `X-Request-ID` de chaque réponse et repris par chaque autre ligne de la requête
  (`database_error`, `query_timeout`, `internal_error`) ; jamais la clé, une valeur de paramètre ni un chemin brut.
  Le journal est commun aux deux API (`core/api_request_log.py`). Elle va dans
  `<KB_DATA_DIR>/logs/kb-serve-data.log`, à part de `kb.log` : `kb serve-data` tourne longtemps, et la rotation
  de minuit faite par `kb collect` ou `kb import` dans un fichier partagé le laisserait écrire dans
  le fichier de la veille (constat sur `TimedRotatingFileHandler`, Python 3.13). Limite : un seul
  `kb serve-data` par `KB_DATA_DIR`. Le port étant réglable, un second `kb serve-data` sur un autre port ne
  bute plus sur le `bind` et écrirait le même fichier (journal ADR, 2026-10-15). Avec
  `KB_LOG_TO_FILE=false`, le journal va sur la sortie d'erreur seule, sans fichier : en conteneur,
  la sortie d'erreur est le journal du conteneur.
- **Organisation du code** : paquet `src/k_b/data_api/`, un dossier par rôle (`routers/`,
  `schemas/`) ; `api_router.py` rassemble les routeurs, et chacun déclare son préfixe et ses tags
  (`items`, `trends`), qui regroupent les routes dans `/docs` et l'OpenAPI ; ce qui est commun à l'API IA est dans
  `core/` : la clé (`api_keys.py`, `api_access.py`), les erreurs (`api_errors.py`), le journal
  (`api_request_log.py`), la santé (`api_health.py`), la règle de l'hôte et du port
  (`api_settings.py`) ; le détail et les options écartées sont
  au journal ADR (2026-10-14, « Paquet `src/k_b/data_api/` »).

## Accès par clé

- **Un client nommé, une clé** : la variable d'environnement `KB_DATA_API_KEY_<CLIENT>` porte la clé du
  client `<CLIENT>` (`[A-Z0-9_]+`, par exemple `KB_DATA_API_KEY_TERMINAL`, `KB_DATA_API_KEY_AGENT`).
  La clé identifie le programme qui appelle (le terminal ou un script de Sabine, un agent, l'API
  IA) ; aucune personne ne se connecte.
- **Clé générée en 256 bits** par `secrets.token_urlsafe(32)` ; le minimum contrôlé est de
  32 caractères. Au démarrage, `kb serve-data` refuse un
  nom de client vide ou hors `[A-Z0-9_]+`, une clé de moins de 32 caractères, une clé hors de
  l'alphabet de `token_urlsafe` (`[A-Za-z0-9_-]` : les espaces autour de la clé reçue sont retirées,
  une clé qui en porte ne serait jamais reconnue), deux clients de
  même clé, et l'absence de toute clé (code de sortie 2, message qui nomme la variable sans sa valeur).
- **Révocable seule** : retirer la variable d'un client et redémarrer l'API ; les autres clients
  restent servis. Un retrait ne prend effet qu'au redémarrage.
- **Vérification** : comparaison en temps constant (`hmac.compare_digest`). Sans clé, ou avec une
  clé inconnue, la réponse est la même : 401 `invalid_api_key`.
- **Pas de route de connexion**, pas de jeton à durée de vie : voir l'entrée « Clés par client »
  du journal.
- **Journal** : il nomme le client, jamais la clé. Un 401 est journalisé sans nom ni valeur reçue.

## Débit

Chaque client a sa limite sur chaque route de données, sur une fenêtre glissante
(`DATA_API_RATE_LIMITS`, `core/config.py` ; `core/api_rate_limit.py`). Au-delà, 429
`rate_limit_exceeded`, avec `Retry-After` : les secondes avant que l'appel le plus ancien sorte de la
fenêtre. Un appel refusé ne compte pas.

| Route | Par client | Repère |
|---|---|---|
| `GET /items` | 120 par minute | 21 par minute au plus dans les journaux d'essai du 26 au 29/10 |
| `GET /items/{item_id}` | 1 200 par minute | 804 par minute au plus dans les mêmes journaux ; 4 demandes de fiches à 300 items |
| `GET /trends` | 120 par minute | 3 comptes rendus à 32 lectures, sans mesure dans ces journaux |

- **Ordre** : le 401 d'abord, une requête sans clé valide ne compte donc pas. Un paramètre refusé
  (422) compte. `/health`, `/docs` et `/openapi.json` n'ont pas de limite.
- **Limites** : le compte vit en mémoire. Un redémarrage ou un passage à zéro réplique le remet à
  zéro, et il ne vaut que pour une réplique (`maxReplicas: 1` au déploiement, #317). Les requêtes sans
  clé valide n'ont pas de limite : par adresse, elle passerait par `X-Forwarded-For`, à valider
  derrière l'entrée d'ACA (à justifier avec la revue des 10 points de #161). Sur le Mac, la veille ne
  compte pas dans la fenêtre (`time.monotonic`, `mach_absolute_time()`) : elle s'allonge d'autant.

## Les parcours P1–P9

Les parcours de [la clarification du modèle](2026-10-07-clarification-modele.md) (section 2), et
la route qui répond à chacun.

| Parcours | Question | Route | Hors API, et pourquoi |
|---|---|---|---|
| P1 | Quoi de neuf depuis N jours, toutes sources ou par thème ? | `GET /items?since=…`, avec `kind` ou `q` pour un thème | — |
| P2 | Quelles nouvelles versions de mes outils ? | `GET /items?kind=release&q=<dépôt>` : le titre d'une release commence par son dépôt | — |
| P3 | Quelles failles touchent mes outils, mes paquets ? | `GET /items?kind=advisory` : les alertes ne sont collectées que pour les paquets suivis (`affects=`, [specs-collecte.md](specs-collecte.md)) | le filtre par paquet : non planifié |
| P4 | Cette faille est-elle exploitée activement ? | `GET /items/{item_id}` d'une alerte : `cve_id` et `exploited` | — ; limite : la liste n'a pas de `cve_id` et `q` ne cherche pas dans `cve_id`, on le lit au détail de l'alerte |
| P5 | Quels dépôts ont le vent en poupe ? | `GET /trends?window_end=…` | — |
| P6 | Quels papiers récents sur un sujet ? | `GET /items?kind=paper&q=…&since=…` | — |
| P7 | Quels sont les dépôts les plus étoilés (top 10) ? | — | hors API : les tops sont hors base (journal ADR, 2026-10-07) ; `kb write-tops` en écrit une fiche par jour dans le coffre, `veille/tops/most_starred/` (#265) ; la commande `kb top`, décidée le 2026-10-08, n'est pas codée |
| P8 | Quels sont les dépôts les plus forkés (top 10) ? | — | hors API : les tops sont hors base (journal ADR, 2026-10-07) ; le top des plus forkés est collecté depuis #264 (`github_most_forked`, recherche triée par `forks`) ; `kb write-tops` en écrit une fiche par jour dans le coffre, `veille/tops/most_forked/` (#265) ; la commande `kb top`, décidée le 2026-10-08, n'est pas codée |
| P9 | Quoi de neuf dans l'écosystème LangChain ? | `GET /items?q=langchain`, puis `GET /items?q=langgraph` : un seul morceau de texte par `q` | — |

Les chemins du brut (`raw_file_path`) ne sont servis par aucune route : un chemin local dévoile le
dossier personnel (API3, ci-dessous).

## `GET /items` : la liste et « quoi de neuf »

### Paramètres

| Paramètre | Forme | Bornes | Défaut | Hors bornes |
|---|---|---|---|---|
| `kind` | une valeur d'`ItemKind`, répétable (`kind=paper&kind=release`) | valeurs exactes : `kind=vulnerability` ne ramène pas les alertes (`advisory`) ; 7 valeurs au plus, autant que de sortes (`MAX_KINDS`, OWASP API4:2023) | toutes les sortes | 422 |
| `since` | date-heure ISO 8601 **avec fuseau** (`2026-10-07T00:00:00Z`, `2026-10-07T00:00:00%2B02:00`) ; dans l'URL, `+` s'écrit `%2B`, sinon il est lu comme une espace | — | aucun filtre de date | 422, sans fuseau compris, et pour un nombre (jamais lu comme une date Unix) |
| `q` | texte | de 1 à 200 caractères | aucune recherche | 422 |
| `limit` | entier | de 1 à 100 | 20 | 422 |
| `offset` | entier | de 0 à 10 000 | 0 | 422 |

### Règle de « quoi de neuf »

`since` porte sur **la date que la source donne**, propre à chaque sorte (tableau ci-dessous). Il
est converti en UTC, puis comparé en `>=` à cette date. Une date de jour (`date_added` de CISA,
`edition_date` de TLDR) est écrite à minuit UTC : `since=2026-10-07T00:00:00%2B02:00`
(soit `2026-10-06T22:00:00Z`) prend le 2026-10-07 et pas le 2026-10-06.

Ni la date de collecte ni une date de révision n'entrent dans la règle : un item ancien découvert
cette semaine n'apparaît pas dans « quoi de neuf » (limite assumée, journal ADR).

### Date, titre et résumé par sorte

| Sorte (`kind`) | Date de `since` (`source_date`) | Titre (`title`) | Résumé, cherché par `q` |
|---|---|---|---|
| `paper` | `publication.submitted_at` | `publication.title` | `publication.summary` |
| `vulnerability` | `vulnerability.date_added` | `vulnerability.name` | `vulnerability.description` |
| `release` | `release.published_at` | `<dépôt> <nom ou tag>` : `tracked_repository.repository_name`, une espace, puis `release.name`, ou `release.tag_name` si le nom est vide | `release.body` |
| `advisory` | `advisory.published_at` | `advisory.summary` | aucun : K-B ne lit et ne garde que `summary` |
| `newsletter_article` | `newsletter_article.edition_date` | `newsletter_article.title` | `newsletter_article.summary` |
| `zotero_entry` | `zotero_entry.saved_at` | `zotero_entry.title` | aucun |
| `clip` | `clip.saved_at` (jour d'ajout, à minuit UTC) | `clip.title` | `clip.body` (le texte gardé) |

### Tri et pagination

- Tri par `source_date` décroissante, puis par `id` décroissant.
- La réponse donne `next_offset`, l'`offset` de la page suivante, nul à la dernière page, ou quand
  l'offset suivant dépasserait 10 000 : les items au-delà ne sont pas servis par la liste ; affiner
  par `since`, `kind` ou `q`.
- Limite : un import qui écrit entre deux pages décale la pagination par `offset`.

### Réponse

```json
{
  "items": [
    {
      "id": 1234,
      "kind": "paper",
      "title": "…",
      "source_date": "2026-10-07T14:03:00Z",
      "url": "https://arxiv.org/abs/…",
      "withdrawn_at": null
    }
  ],
  "next_offset": 20
}
```

| Champ | Contenu |
|---|---|
| `id` | `item.id`, l'identifiant du détail |
| `kind` | la sorte |
| `title` | le titre (tableau ci-dessus) |
| `source_date` | la date de `since`, texte UTC `AAAA-MM-JJTHH:MM:SSZ`, comme en base |
| `url` | l'adresse de l'item ; nulle pour une entrée Zotero sans URL |
| `withdrawn_at` | date K-B du retrait d'une ligne de catalogue (vulnérabilité, entrée Zotero) ; nulle sinon |

Les lignes retirées sont servies avec leur `withdrawn_at`, pas filtrées.

**Pas dans la liste** : le résumé, la description, le corps d'une release, le texte d'un clip, les
auteurs (texte long ou donnée personnelle, servis au détail), `raw_file_path` et `collected_at` (jamais servis).

## `GET /items/{item_id}` : le détail

`item.id` dans le chemin ; les clés naturelles sont des champs de la réponse. `item_id` est un
entier écrit en chiffres, sans zéro en tête, sans `+`, sans espace ni décimale (`1`, `-1`, pas
`01`, `1.0` ni `+1` : une seule URL par item), tenu sur 64 bits ; sinon 422 `invalid_parameter`.
Un entier qu'aucun item ne porte rend 404 `item_not_found`. La réponse reprend les six champs de
la liste et, selon la sorte (`kind`, qui dit le schéma suivi : `oneOf` et `discriminator` dans
l'OpenAPI), exactement ceux-ci :

| Sorte | Clés naturelles | En plus de la liste |
|---|---|---|
| `paper` | `arxiv_id` | `authors` (les noms, dans l'ordre d'arXiv), `summary`, `arxiv_updated_at` (colonne `publication.revised_at`, date arXiv) |
| `vulnerability` | `cve_id` | `description`, `vendor`, `product`, `ransomware_use`, `revised_at` (date K-B) |
| `release` | `release_id` | `repository_name`, `tag_name`, `body` (le corps) |
| `advisory` | `ghsa_id` | `cve_id` (nul si l'alerte ne cite aucune CVE), `exploited`, `packages` (les paquets touchés) |
| `newsletter_article` | `edition`, `edition_date`, `rank` | `summary` |
| `zotero_entry` | `zotero_key` | `item_type`, `arxiv_id` (lu par `publication_id`, nul hors arXiv), `revised_at` (date K-B), `highlights` : les surlignages, retirés compris, par date de création, dans les bornes du détail ; `highlights_truncated` |
| `clip` | `url` (déjà dans la liste) | `published_at` (date de la page gardée, un jour à minuit UTC, nulle si la page n'en donne pas), `body` (le texte gardé, Markdown, dans les bornes du détail) ; `body_truncated` |

Un surlignage sert `text`, `comment`, `highlighted_at` (date Zotero), `revised_at` et
`withdrawn_at` (dates K-B) ; sa clé Zotero n'est pas servie. Le `name` d'une release n'est pas
servi : il est dans `title`. Les dates sont servies comme en base (`AAAA-MM-JJTHH:MM:SSZ`).
L'OpenAPI décrit chaque date par son origine : date K-B (la collecte qui a vu le changement),
date arXiv ou date Zotero.

**Bornes du détail** (OWASP API4:2023 ; `item_router.py`) : un détail sert 125 000 caractères
de texte long au plus, la longueur maximale du corps d'une release, qu'il sert déjà entier
(`MAX_LENGTH_BY_KIND`, `items.py`) ; écrite à part, un test la garde égale à celle-ci, si bien
qu'un changement de la borne d'une release se voit avec le contrat. La coupe se fait au caractère
(point de code), sans égard à un graphème ni à la syntaxe Markdown : un texte coupé peut finir
par un emoji composé, une lettre sans son accent combiné ou un lien incomplet.
- Une entrée Zotero sert ses surlignages dans l'ordre (date de création, retirés compris : un
  retiré prend une place) tant qu'ils sont 100 au plus et que leurs `text` et `comment` font
  ensemble 125 000 caractères au plus ; `highlights_truncated` dit qu'il en manque. La coupe
  garde un début de la liste : un surlignage fait plus tard, donc daté plus tard, ne décale pas
  ceux déjà servis. Sans la borne de taille, 100 surlignages de 10 000 caractères de texte et
  autant de commentaire feraient 2 000 000 de caractères (choix de Sabine du 2026-11-06).
- Un clip sert les 125 000 premiers caractères de son texte ; `body_truncated` dit qu'il est
  coupé.

Les deux drapeaux sont toujours servis, faux sans coupe. La suite n'est pas servie : ni
pagination, ni nombre total.

La lecture dans la base est bornée elle aussi (#430) : 101 surlignages au plus (`LIMIT`) et les
125 001 premiers caractères du texte d'un clip (`substr`), un de plus que ce qui est servi, pour
que la route voie la coupe. La route passe ces bornes à la lecture (`DetailBounds`,
`database/reading.py`) ; elles ne sont écrites qu'une fois, dans `item_router.py`. `substr` compte
des caractères sur les deux moteurs, la base PostgreSQL étant en UTF8.
- `LIMIT` borne le nombre des surlignages, pas leur taille : la base en lit au plus
  101 × (10 000 + 10 000) = 2 020 000 caractères de texte et de commentaire, et la route en sert
  125 000 au plus.
- En SQLite, le moteur tourne dans le processus de l'API : la borne vaut pour ce que Python reçoit,
  et ce que SQLite charge pour calculer `substr` n'est pas mesuré. En PostgreSQL, le serveur coupe.

`exploited` vaut vrai si la CVE de l'alerte est au catalogue CISA KEV
(`vulnerability.item_id IS NOT NULL`) : faux veut dire « absente du catalogue KEV », pas « non
exploitée ». Il est nul pour une alerte sans CVE. Il reste vrai si la CVE a été retirée du
catalogue depuis : le retrait se lit dans `withdrawn_at`, au détail de la vulnérabilité, que
le détail de l'alerte ne désigne pas encore (« Hors de cette version »).

`source_date` et `arxiv_updated_at` sont des noms de champs de l'API : ils ne renomment aucune
colonne (décision ouverte « Noms des colonnes de date », journal ADR).

## `GET /trends` : les dépôts qui montent

| Paramètre | Forme | Défaut | Hors bornes |
|---|---|---|---|
| `window_end` | date écrite `AAAA-MM-JJ` exactement, le dernier jour d'une fenêtre de 3 jours | la fenêtre la plus récente en base | 422 : une autre forme (`20261012`, `2026-10-12T00:00:00Z`), un nombre (jamais lu comme une date Unix), une date qui n'existe pas (`2026-02-30`) |

```json
{
  "window_end": "2026-10-12",
  "trends": [
    {
      "repository_id": 123456,
      "repository_name": "owner/repo",
      "stars_gained": 1500,
      "forks_gained": 120
    }
  ]
}
```

- Une ligne par dépôt : les 30 premiers par étoiles gagnées et les 30 premiers par forks gagnés,
  réunis, soit 60 lignes au plus ; pas de pagination.
- Tri par `stars_gained` décroissant, puis `forks_gained` décroissant, puis `repository_id`.
- `window_end` est stocké à minuit UTC et rendu en `AAAA-MM-JJ`.
- **Fenêtre absente : 404 `trend_window_not_found`**, dans les deux cas du tableau des erreurs.
  Pourquoi (choix de la session K-B, validé par Sabine le 2026-10-14) : une fenêtre n'existe en
  base que par ses lignes : une liste vide ne décrirait aucune fenêtre
  réelle, et le client ne distinguerait pas une date sans fenêtre d'une réponse valide. L'état
  nommé dit ce qui est observé, comme `item_not_found`.
- Limite : les fenêtres glissent d'un jour et aucune route ne les liste ; sans `window_end`, la
  route rend la plus récente.

## Erreurs

Corps : `{"error": "<état>"}`. Aucune erreur ne renvoie de pile, de requête SQL, de chemin ni la
valeur reçue.

| État | Statut | Quand |
|---|---|---|
| `invalid_api_key` | 401 | route de données appelée sans clé, ou avec une clé inconnue (même corps) |
| `item_not_found` | 404 | `GET /items/{item_id}` : aucun item de cet identifiant |
| `trend_window_not_found` | 404 | `GET /trends?window_end=…` : aucune tendance pour cette fenêtre |
| `trend_window_not_found` | 404 | `GET /trends` sans `window_end` : aucune tendance en base |
| `route_not_found` | 404 | chemin inconnu |
| `method_not_allowed` | 405 | méthode autre que GET |
| `invalid_parameter` | 422 | paramètre hors bornes ou mal formé ; le corps ajoute `"parameters": [<noms>]`, sans les valeurs |
| `rate_limit_exceeded` | 429 | client au-delà de la limite de la route (« Débit »), avec `Retry-After` |
| `query_timeout` | 503 | la requête a passé 5 s dans la base (« Délai »), sans détail |
| `database_missing` | 503 | le fichier SQLite de la base n'existe pas ; en PostgreSQL, une base injoignable ou sans tables répond 500 `database_error` |
| `database_error` | 500 | toute autre erreur de la base, sans détail |
| `internal_error` | 500 | toute autre erreur, sans détail ; journalisée par son type seul, sans pile ni message |

Exception : un `Host` hors des hôtes permis (`127.0.0.1` et `localhost` par défaut) reçoit le 400
de `TrustedHostMiddleware`, qui répond avant l'app, en texte.

## Recherche `q`

- `q` cherche un morceau de texte dans le titre et le résumé (tableau « Date, titre et résumé par
  sorte »), jamais dans le texte des surlignages (journal ADR, 2026-10-09).
- Moyen : `lower(champ) LIKE lower(q) ESCAPE '\'`, le même SQL sur les deux moteurs
  (`LIST_FILTERS`, `database/reading.py`) ; `%`, `_` et `\` sont cherchés tels quels. `lower()` des
  deux côtés : `LIKE` ignore la casse des lettres ASCII en SQLite seulement ; `lower()` ne plie
  qu'elles, en SQLite comme en PostgreSQL dans la collation C que `kb create-db` exige
  ([stockage.md](stockage.md)). Écartés : `ILIKE`, propre à PostgreSQL (règle 1 de
  `.claude/rules/poc.md`) ; plier `q` en Python, qui plierait aussi `É`, alors que la base ne le
  plie pas.
  Coût de `lower()`, qui copie chaque titre et résumé à chaque recherche, mesuré le 2026-11-06 sur
  SQLite, base en mémoire de 400 corps de release de 125 000 « a » et 5 textes de 1 000 000 de
  caractères, sans délai : une recherche ordinaire passe de 0,017 s à 0,029 s, la pire recherche
  (« Délai ») de 9,66 s à 9,72 s.
- Comportement relevé le 2026-10-14 sur SQLite 3.50.4 (module `sqlite3` de Python) et 3.51.0
  (commande `sqlite3`), base en mémoire, et le 2026-11-06 sur PostgreSQL 18.4, en collation C, par
  la même expression ; les mêmes résultats sur les deux moteurs sont tenus par
  `test_read_items_gives_the_same_results_on_postgresql_as_on_sqlite` :

  | Recherche | Texte | Trouvé |
  |---|---|---|
  | `vuln` | « Vulnérabilités », « vulnerability » | oui (morceau de mot) |
  | `abc` | « ABC » | oui (casse ignorée, lettres sans accent) |
  | `vulnerabilite` | « Vulnérabilité » | non (accents exacts) |
  | `É` | « é » | non |

- Tri par date, comme sans `q`.
- `q` cherche dans tout le texte d'un clip, au-delà des 125 000 caractères que son détail sert
  (« Bornes du détail ») : un clip peut être listé pour un morceau que son détail ne montre pas.
- **Écart temporaire** à la recherche plein texte triée par pertinence (journal ADR,
  2026-10-09) : elle changera l'ordre des résultats avec `q`, et passera la spec et l'OpenAPI à
  une nouvelle version. Elle était prévue avec PostgreSQL (`tsvector`) après le 08/11 (journal
  ADR, 2026-10-15, « POC du 25/10 », décision 2). Son moteur est choisi : PostgreSQL en ligne,
  SQLite en local (journal ADR, 2026-11-06, « Base : PostgreSQL en ligne, par un adaptateur
  maison (#417) »), qui ferme « La base au temps 3 ».

## Données personnelles

Selon le [registre des traitements](registre-traitements.md) :

- les noms des auteurs d'un papier et les logins écrits dans le corps d'une release : au détail
  seulement, jamais dans la liste ni au journal ;
- le login du propriétaire d'un dépôt, dans le nom du dépôt : servi par `/trends`
  (`repository_name`), dans le titre d'une release (liste) et dans son `repository_name`
  (détail) ;
- les titres et dates des entrées Zotero de Sabine : dans la liste ; ses surlignages et
  commentaires : au détail de leur entrée ;
- les titres et dates des clips de Sabine : dans la liste ; le texte d'un clip, qui peut nommer
  des personnes (la signature de l'article) et porter les notes de Sabine : au détail seulement,
  jamais au journal. L'auteur d'un clip (`author`) n'est pas en base. `q` cherche aussi dans ce
  texte, comme dans le corps d'une release, au-delà des 125 000 caractères que le détail sert : la
  liste dit quels clips contiennent la chaîne cherchée, sans servir le texte.

Un agent qui lit ces données les envoie au fournisseur de son modèle : décision ouverte
« Transfert hors UE par les agents » (journal ADR).

## Sécurité : OWASP API Security Top 10 (2023)

Ce que l'API vise pour chaque exigence. La dernière colonne est remplie par l'issue qui sert le
détail et les tendances (#185 : « chaque ligne dit si l'exigence est tenue, et par quel test »).
La grille, son édition (2023, quand le référentiel de la certification renvoie à 2019) et le sens
de « non tenue » et d'« écart voulu, justifié » sont ceux de l'API IA
([fiches-veille.md](fiches-veille.md), « Sécurité : OWASP API Security Top 10 (2023) »).

| Exigence | Intention | Tenue, par quel test |
|---|---|---|
| API1:2023 Broken Object Level Authorization | Une seule propriétaire, Sabine : tout client authentifié lit tous les items. Un identifiant inconnu rend 404, jamais une erreur qui dirait autre chose. `item.id`, séquentiel, est dans l'URL : la recommandation d'identifiants difficiles à deviner est écartée tant que l'API n'a qu'une propriétaire (journal ADR, 2026-10-15). | **Tenue.** `test_each_client_is_served_with_its_key`, `test_an_unknown_item_id_gives_404_item_not_found`, `test_an_unknown_window_gives_404` |
| API2:2023 Broken Authentication | Une clé par client, générée en 256 bits (minimum contrôlé : 32 caractères) ; pas de route de connexion ; comparaison en temps constant ; 401 testé sur chaque route de données. | **Écart voulu, justifié** pour l'anti-force brute et le TLS mutuel (« Ce qui manque, et comment le tenir ») ; le reste tenu : `test_every_data_route_refuses_a_missing_and_a_wrong_key_with_the_same_body` (chaque route, lue dans l'app par le parcours de FastAPI, routes hors OpenAPI comprises), `test_only_the_public_routes_answer_without_a_key` (`/docs`, `/openapi.json` et `/health`, aucune autre), `test_an_app_without_key_refuses_every_data_route`, `test_a_removed_key_gives_401_and_the_other_clients_are_still_served`, `test_serve_exits_2_and_names_the_variable_without_its_value` ; le temps constant n'est pas mesuré par un test (`hmac.compare_digest`, `src/k_b/core/api_access.py`) |
| API3:2023 Broken Object Property Level Authorization | Réponses en liste blanche : ni `raw_file_path`, ni `collected_at`, ni texte long dans la liste ; au détail, les champs du tableau de sa sorte et rien d'autre. | **Tenue.** `test_the_list_serves_only_the_six_fields`, `test_each_kind_has_its_detail` (corps entier, une sorte par cas), `test_no_detail_serves_a_raw_file_path_or_a_collection_date`, `test_trends_without_window_end_give_the_latest_window`, `test_no_error_body_holds_a_raw_file_path_or_a_path`, `test_no_route_documents_a_raw_file_path_or_a_collection_date` |
| API4:2023 Unrestricted Resource Consumption | Bornes de `limit` (100), `offset` (10 000), `q` (200 caractères) et du nombre de `kind` (7) ; `/trends` rend 60 lignes au plus, sans pagination. Une limite de débit par client et par route (« Débit »). Un délai de 5 s par requête dans la base (« Délai ») ; au détail, 100 surlignages et 125 000 caractères de texte long au plus (« Bornes du détail »). | **Tenue.** Le délai : `test_a_request_beyond_its_deadline_gives_503_query_timeout_without_detail` (la liste, le détail, les tendances : chaque route lit par la connexion qui porte le délai), `test_the_deadline_of_a_request_is_below_the_read_timeout_of_the_ai_api_client` ; sur PostgreSQL, `test_on_postgresql_a_request_beyond_its_deadline_gives_503_query_timeout_without_detail` (les trois routes), `test_a_reading_past_its_deadline_is_stopped_and_its_connection_given_back_idle`, `test_a_deadline_below_one_millisecond_is_refused_as_statement_timeout_0_disables_it`, `test_serve_reads_the_postgresql_base_of_kb_database_url_with_the_deadline_it_logs` (le délai appliqué est celui du journal), et l'attente d'une connexion, `test_the_pool_lends_no_connection_beyond_its_wait`, `test_the_wait_for_a_connection_and_one_reading_hold_below_the_read_timeout_of_the_client` ; les bornes du détail : `test_the_highlights_beyond_their_number_are_cut_and_the_cut_is_said`, `test_the_highlights_beyond_their_length_are_cut_and_the_cut_is_said`, `test_the_text_of_a_clip_beyond_its_length_is_cut_and_the_cut_is_said` ; les bornes et la taille de page, `test_a_parameter_out_of_bounds_gives_422_with_its_name_only`, `test_next_offset_stops_at_the_offset_bound`, `test_an_item_id_not_written_as_an_integer_gives_422`, `test_a_malformed_window_end_gives_422` ; le débit, pour les clients authentifiés, `test_beyond_its_limit_a_client_gets_429_with_its_wait_and_its_id`, `test_the_limit_is_per_client_and_per_route`, `test_every_data_route_has_its_limit` ; les 60 lignes d'une fenêtre sont bornées à la collecte (`gh_archive.py`), pas par l'API. Limites : les surlignages sont tous lus avant la coupe, bornés en temps par le délai, pas en mémoire ; une instruction seule de SQLite ne s'interrompt pas, et chaque contrôle du délai reprend le GIL ; sur PostgreSQL, le délai compte par instruction, et le détail en fait jusqu'à trois (« Délai ») ; le délai se multiplie par le débit (120 listes par minute, 5 s chacune au plus), sans plafond de requêtes en même temps en SQLite ; en PostgreSQL, 4 lectures en même temps au plus, les connexions du pool, et une requête de plus attend 2 s puis répond 500 `database_error`. Les redémarrages, les descripteurs et les processus : écart voulu, justifié comme dans l'API IA (« Ce qui manque, et comment le tenir ») ; la dépense : aucun fournisseur payé à l'appel, et l'app et le serveur PostgreSQL, étiquetés `project=k-b` (`infra/main.bicep:187`, `:286`), sont comptés par `budget-kb`, qui alerte par e-mail (`infra/modules/budget.bicep:16-56`) |
| API5:2023 Broken Function Level Authorization | GET seulement, 405 sinon, `HEAD` compris ; aucune route d'administration. | **Tenue.** `test_every_route_answers_get_only_and_405_to_any_other_method`, `test_the_routes_are_listed`, `test_docs_openapi_and_health_are_public_and_no_other_page_is_served`, `test_health_refuses_another_method_with_405` |
| API6:2023 Unrestricted Access to Sensitive Business Flows | Sans objet : l'API n'a aucun flux métier à protéger (ni achat, ni réservation, ni création de compte), seulement des lectures. | Sans objet, sans test |
| API7:2023 Server Side Request Forgery | Sans objet : l'API ne va chercher aucune adresse fournie par un client. | Sans objet, sans test |
| API8:2023 Security Misconfiguration | Hôte d'écoute réglable (`KB_DATA_API_HOST`, une adresse IPv4), `127.0.0.1` par défaut ; hôtes permis réglables (`KB_DATA_API_ALLOWED_HOSTS`), `127.0.0.1` et `localhost` par défaut ; `*`, une liste ou une entrée vide et un nom hors motif refusés au démarrage ; en conteneur, écoute sur `0.0.0.0` (`infra/main.bicep:202`), derrière l'entrée interne d'ACA ; pas de CORS ; erreurs sans pile ; `/health` ne dit que `ok` ; chaque route n'accepte que `GET` : `HEAD`, que Starlette ajoute à toute route `GET`, est retiré, et toute autre méthode sur le chemin d'une route, `TRACE` et `CONNECT` compris, rend 405 ; `CONNECT hôte:port` et `OPTIONS *`, qui ne visent aucun chemin, rendent 404 `route_not_found` avec un hôte permis, 400 sinon (essayé sous uvicorn le 2026-11-05). `/docs` et `/openapi.json` servis en `sandbox` seulement (#393). Limites : Swagger UI (`/docs`) charge ses fichiers depuis un CDN ; pas de TLS sur la machine, où l'écoute sur `127.0.0.1` n'admet que ses programmes ; en ligne, le TLS de l'entrée interne d'ACA et du chiffrement entre apps (relu le 2026-11-08, #454). | **Non tenue**, comme dans l'API IA : le durcissement répétable, la revue périodique et l'évaluation automatisée, communs aux deux API (`infra/`, la CI), sont des mesures nécessaires non intégrées (#496 à #499). Ports publiés sur `127.0.0.1` : *s.o.* ; chaîne Envoy → uvicorn : écart voulu, justifié comme dans l'API IA ; le TLS est tenu en ligne (« Ce qui manque, et comment le tenir », API8). Ce qui est tenu : `test_serve_listens_on_127_0_0_1_8000_by_default_without_uvicorn_logging_config`, `test_serve_listens_on_the_host_and_port_of_the_environment`, `test_serve_exits_2_on_a_host_or_port_refused`, `test_serve_exits_2_and_names_the_allowed_hosts_refused`, `test_serve_allows_the_hosts_of_the_environment_and_no_other`, `test_a_host_other_than_localhost_gives_400`, `test_a_host_other_than_the_allowed_ones_gives_400_on_health`, `test_health_answers_ok_without_key`, `test_every_route_answers_get_only_and_405_to_any_other_method`, `test_no_route_answers_cors`, `test_an_unexpected_error_gives_500_internal_error_and_logs_its_type_only`, `test_a_database_error_gives_500_without_detail_and_logs_its_type` |
| API9:2023 Improper Inventory Management | OpenAPI versionnée (`docs/api/openapi-donnees.json`), comparée en CI au schéma produit ; hors `sandbox`, la route ne la sert pas, le contrat reste dans le dépôt (#393). `/health`, hors OpenAPI comme `/docs`, est inventoriée par ce document (« Santé »). | **Écart voulu, justifié** pour la documentation en `sandbox` et les protections externes (« Ce qui manque, et comment le tenir ») ; le reste tenu : `test_the_versioned_openapi_is_the_one_the_app_produces`, `test_the_versioned_openapi_is_valid_and_declares_its_security_scheme`, `test_each_data_route_documents_its_errors` |
| API10:2023 Unsafe Consumption of APIs | Le contenu servi vient de tiers (arXiv, GitHub, CISA, TLDR, Zotero, pages gardées avec Web Clipper) : pour un client, et d'abord pour un agent, c'est une donnée, jamais une consigne. Côté K-B, la réponse d'une source est validée à la collecte (modèles de `items.py`, `CHECK` de `schema.sql`). | **Tenue côté K-B** : `tests/test_schema.py` (chaque type refusé par l'item et par la base) et les tests de chaque source. Côté client, une consigne, sans test |

### Ce qui manque, et comment le tenir

Rien de ce qui suit n'est codé : décision de Sabine du 2026-11-05, dire comment on tiendrait chaque
mesure manquante, sans la faire maintenant. Tailles : XS ≤ 1 h, S ≤ 3 h, M ≈ 6 h, L ≈ 15 h. Ce qui
touche à Azure Container Apps (ACA) est dans la même section de [fiches-veille.md](fiches-veille.md),
avec ses sources.

- **API1, identifiants aléatoires et imprévisibles** (mesure écartée le 2026-10-15, ligne API1 ;
  Sabine a décidé le 2026-11-05 de la tenir, #403) : conçu le 2026-11-05, environ 20 à 24 h en
  trois PR.
  1. L'API IA ne montre plus au modèle l'identifiant de la base, mais la place de l'item dans la
     lecture (`i1` à `i300`), comme `c1…cN` pour les tendances : ni les consignes, ni les schémas,
     ni les bornes du modèle ne changent. S.
  2. Une colonne `item.public_id`, un UUID v4 tiré en Python (`uuid.uuid4()`) à chaque insertion,
     `NOT NULL UNIQUE`, avec un `CHECK` de sa forme en SQL portable (règle 1 de `.claude/rules/poc.md`) ; l'entier
     reste la clé interne et départage toujours l'ordre de la liste. M.
  3. `GET /items/{item_id}` ne prend plus qu'un UUID sous sa forme canonique, 422 sinon ; chaque
     identifiant d'item servi devient l'UUID, dans les deux API et chez `kb digest` ;
     `repository_id`, l'identifiant de GitHub, reste un entier. L.

  Pas de migration : la base de développement est recréée (son fichier retiré, car `kb create-db`
  refuse une base existante, puis `kb create-db` et `kb import`). Elle ne retrouve que ce que garde
  le brut ([stockage.md](stockage.md) : la base est la source de vérité, le brut est gardé 6 mois
  au plus) : pas l'historique des extraits Zotero et CISA KEV remplacés, perte que Sabine juge sans
  conséquence pour sa base de développement (2026-11-05). Une recréation tire aussi de nouveaux
  UUID, qu'aucune fiche ne voit (elles n'écrivent aucun identifiant).
- **API2, essais de clé sans limite** : la limite de débit ne compte que les clients à clé valide
  (« Débit »). Écart voulu, justifié, par l'argument de l'API IA
  ([fiches-veille.md](fiches-veille.md), API2, « Anti-force brute, plus strict que la limite de
  débit ») : une clé générée en 256 bits par `secrets.token_urlsafe(32)`, 192 au minimum contrôlé
  (« Accès par clé »), rend la recherche exhaustive impraticable ; en ligne, seules les pièces de
  l'environnement atteignent l'entrée interne, et sur la machine, l'écoute sur `127.0.0.1` n'admet
  que ses programmes. Le TLS mutuel n'y est pas plus nécessaire : en ligne, son seul client à clé
  est l'API IA, dans le même environnement (même section, « authentification TLS mutuelle entre
  programmes »). Limite et « Pour réduire le risque » : ceux de l'API IA. Pour tenir l'anti-force
  brute, si la limite est franchie : comme dans l'API IA. S.
- **API8, TLS** : tenu en ligne, relu le 2026-11-08 (#454). L'API de données n'a qu'une entrée
  interne, en HTTPS (`external: false`, `allowInsecure: false`,
  `infra/modules/api-container-app.bicep:74-80`), joignable des seules apps et jobs de son
  environnement : les clients `TERMINAL` et `AGENT` ne la joignent plus de l'extérieur. Le chiffrement
  entre apps est activé (`infra/modules/container-apps-environment.bicep:32-36`) : le réseau est
  chiffré jusqu'à la réplique, et le dernier pas, d'Envoy à uvicorn dans la réplique, n'est ni décrit
  par la documentation ni essayé. Son nom interne est
  le seul hôte permis (`KB_DATA_API_ALLOWED_HOSTS`, `infra/main.bicep:205`), et elle lit PostgreSQL
  en `sslmode=verify-full` (l. 279). Relu en ligne sur `ca-kb-data-api` : `external` false,
  `allowInsecure` false, `transport` Http ; les commandes, l'environnement et la version de TLS sont
  dans [fiches-veille.md](fiches-veille.md), API8, « TLS, même pour une API interne ». Reste sans TLS
  sur la machine, où l'écoute sur `127.0.0.1` n'admet que ses programmes.
- **API8, ports publiés sur `127.0.0.1`** : *s.o.*, aucun compose dans le dépôt
  (`git ls-files | grep -i compose` ne rend rien le 2026-11-10 ; #200, fermée, n'en a pas versé) ;
  en ligne, le conteneur ne publie aucun port, derrière l'entrée interne.
- **API8, durcissement, revue et évaluation** : non tenus, communs aux deux API, comme dans l'API IA
  ([fiches-veille.md](fiches-veille.md), API8), avec leurs « Pour la tenir » et « Pour réduire le
  risque » (#496 à #499) ; la chaîne Envoy → uvicorn, écart voulu, justifié de même.
- **API9, documentation en `sandbox`** : `/docs` et `/openapi.json` sans clé en `sandbox`, écart
  voulu, justifié comme dans l'API IA (#393 ; [fiches-veille.md](fiches-veille.md), API9,
  « Documentation réservée aux utilisateurs autorisés ») ; pour le lever, ne plus les servir du tout, ce qui ferme les deux
  API ensemble (`read_openapi_url`, `core/api_settings.py`). XS.
- **API9, protections externes** : écart voulu, justifié comme dans l'API IA
  ([fiches-veille.md](fiches-veille.md), API9) : une seule révision active
  (`infra/modules/api-container-app.bicep:73`), derrière l'entrée interne ; limite et « Pour réduire
  le risque » : ceux de l'API IA.

## Hors de cette version

- Les filtres `source` et `in` : options de `kb search` seulement (#187).
- Le filtre par paquet (P3).
- Les tops P7 et P8.
- **D'une alerte à sa vulnérabilité** : le détail d'une alerte dit `cve_id` et `exploited`, pas
  l'`id` de l'item vulnérabilité ; la liste n'a pas `cve_id` et `q` ne le cherche pas. Un client
  ne peut donc pas lire au détail de la vulnérabilité si elle a été retirée du catalogue KEV.
  Signalé ; une issue sera créée.

## Sources (consultées le 2026-10-14, sauf mention)

- [OWASP Top 10 API Security Risks — 2023](https://api-security.owasp.org/editions/2023/en/0x11-t10/) : les noms et
  le périmètre des dix exigences du tableau de sécurité.
- [API2:2023 Broken Authentication](https://api-security.owasp.org/editions/2023/en/0xa2-broken-authentication/), section
  « How To Prevent » — OWASP : une clé d'API authentifie un programme client, pas une personne
  (accès par clé).
- [Bigger Applications — Multiple Files](https://fastapi.tiangolo.com/tutorial/bigger-applications/) — FastAPI,
  lu par Context7 : un `APIRouter` par module, `include_router` (organisation du paquet).
- [Advanced Middleware, `TrustedHostMiddleware`](https://fastapi.tiangolo.com/advanced/middleware/) — FastAPI,
  lu par Context7 : un `Host` non permis reçoit un 400 (erreurs).
- [API8:2023 Security Misconfiguration](https://owasp.org/API-Security/editions/2023/en/0xa8-security-misconfiguration/),
  section « How To Prevent » — OWASP, relevé par recherche web le 2026-10-15 : TLS pour tout
  échange, interne ou public ; seules les méthodes utiles, les autres désactivées, `HEAD` cité en
  exemple (relu le 2026-11-05) ; CORS ; erreurs sans détail interne (ligne API8).
- [Global Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/global-dependencies/) —
  FastAPI, lu par Context7 le 2026-10-15 : les dépendances de l'app s'appliquent à toutes les
  *path operations* ; `/health`, route de Starlette ajoutée par `add_route` comme `/docs`
  (`fastapi/applications.py`, 0.143.1), n'en est pas une (santé).
- [Middleware, `TrustedHostMiddleware`](https://www.starlette.io/middleware/#trustedhostmiddleware)
  — Starlette, lu par Context7 le 2026-10-15 : `["*"]` permet tout hôte, un `Host` non permis
  reçoit un 400 (hôtes permis) ; la comparaison telle quelle, sans mise en minuscules, est lue
  dans le code installé (`starlette/middleware/trustedhost.py`, 1.8.0).
