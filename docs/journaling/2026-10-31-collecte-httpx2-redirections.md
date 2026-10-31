# La collecte par httpx2, chaque redirection contrôlée avant d'être demandée

- **Date** : 2026-10-31
- **Branche** : `fix/collect-httpx2`
- **Issue** : #86 (« Passer http_download.py et ses tests de urllib à httpx »), qui reprend le
  contrat de #54 (une redirection hors du préfixe refusée avant d'être suivie)
- **Fichiers principaux** : `src/k_b/etl/http_download.py`, `src/k_b/etl/http_retry.py`,
  `src/k_b/core/outbound.py`, `src/k_b/etl/source_contract.py`, `src/k_b/etl/sources/cisa_kev.py`,
  `src/k_b/etl/sources/github/api.py`, `src/k_b/etl/extract.py`, les deux connecteurs de l'API IA,
  `tests/etl/http_helpers.py`, `tests/etl/conftest.py`, `tests/etl/test_http_download.py`
- **Série** : suit [le flux arXiv lu par defusedxml](2026-10-31-flux-arxiv-defusedxml.md) (#69),
  la première PR de la même mission.

La PR tient en cinq commits sur `b989888` : `fe4e88b` (le code et les tests), `fc15a86` (la
documentation et l'entrée du journal ADR), `bef170a` (la règle 3 de `conventions.md`, texte accepté
par Sabine), `2120795` et `c4451f4` (corrections des revues). Les autres commits et fichiers que
liste `git log` depuis la branche de départ appartiennent aux PR #377, #378 et #380, déjà fusionnées
sur `main` : ils ne font pas partie de celle-ci.

## Le pourquoi

Quatre sources (tldr, arXiv, CISA KEV, l'API GitHub) passent par une seule fonction,
`download` : la frontière réseau de la collecte. Elle tenait sur `urllib`, et `urlopen` **suit les
redirections lui-même**, jusqu'à 10 sauts, `http://` compris. K-B ne contrôlait que l'adresse
finale : un saut hors de l'adresse attendue avait déjà été demandé, et sa réponse lue, quand le
contrôle le voyait (constat de #54). Un serveur de la source pouvait donc faire contacter par K-B
n'importe quelle adresse, et le jeton GitHub ne partait qu'à la première requête par une règle
d'`urllib` (`unredirected_hdrs`) qu'on ne voyait pas dans le code.

#86 remplace `urllib` par `httpx2`, déjà le client de l'API IA, et en profite pour tenir ce
contrat : **K-B suit lui-même les redirections, et contrôle chacune avant de la demander**. Les
garde-fous d'avant restent : préfixe de confiance, `User-Agent`, délai, taille maximale, jeton
jamais renvoyé.

## Le comment

### 1. Un client qui ne suit rien, et le code qui suit

Le client vient d'`open_http_client` (`src/k_b/core/outbound.py:51-52`) :

```python
        follow_redirects=False,
        trust_env=False,
```

`follow_redirects=False` : httpx2 rend la réponse 3xx telle quelle, sans demander la cible.
`trust_env=False` : ni proxy ni certificat lus dans l'environnement (`HTTPS_PROXY`, `.netrc`…) ;
c'est un changement de comportement par rapport à `urllib`, qui lisait les proxys, écrit dans
`docs/specs-collecte.md:129-130`. Un client est ouvert par tentative (`download_once`,
`src/k_b/etl/http_download.py:78`) et fermé à sa fin.

### 2. Le contrôle porte sur l'URL que httpx2 va demander

C'est le cœur de la PR (`src/k_b/etl/http_download.py:119-133`) :

```python
        location = response.headers["Location"]
        try:
            target = urljoin(str(request.url), location)
            request = build_request(client, target, headers)
        ...
        if not str(request.url).startswith(trusted_url_prefix):
            raise RedirectedOutsideError(trusted_url_prefix, target)
        response = client.send(request, stream=True)
```

Trois points :

- **La requête est construite, puis contrôlée, puis envoyée : la même.** Contrôler la chaîne
  `target` ne suffirait pas : `https://tldr.tech/ai/2026-10-04/../../login` commence bien par le
  préfixe `https://tldr.tech/ai/2026-10-04`, mais httpx2 résout les `..` et demanderait
  `https://tldr.tech/login`. `str(request.url)` est l'URL normalisée que httpx2 enverra ; c'est
  elle qui est comparée. La première requête suit la même règle (`:103-104`).
- **Le saut est construit avec `headers` seulement**, jamais avec `unredirected_headers` (le jeton),
  et jamais par `response.next_request`, que httpx2 prépare aussi : il garde `Authorization` pour
  une redirection de même origine, donc renverrait le jeton.
- **Au plus `HTTP_MAX_REDIRECTS = 10` sauts** (`core/config.py`, la valeur d'`urllib`), puis
  `PageRefusedError`. Chaque 3xx est fermé (`response.close()`, `:111`) sans que son corps soit lu.

Une cible hors préfixe lève `RedirectedOutsideError`, qui garde `redirect_url` entière : tldr la
compare à la page d'accueil de l'édition pour reconnaître un jour sans édition. Son message cite la
cible sans sa requête ni son fragment (`without_query`) : une redirection peut porter un jeton de
session.

### 3. Une `Location` lisible par httpx2, mais pas une fois résolue

Ajouté par les revues (`src/k_b/etl/http_download.py:123-130`) :

```python
        except (ValueError, httpx2.InvalidURL) as error:
            ...
            cut_location = location.partition("?")[0].partition("#")[0]
            raise PageRefusedError(
                f"redirection to an unreadable location {quote_value(cut_location)}, "
                f"refused ({type(error).__name__})"
            ) from None
```

Deux analyseurs d'URL se croisent ici : httpx2 lit la `Location` dans `client.send` (il prépare
`next_request`), puis `urljoin` la résout. Ils ne sont pas d'accord sur tout : `https://a]b/` passe
httpx2 mais fait lever `ValueError: Invalid IPv6 URL` à `urljoin`. Sans ce bloc, l'erreur n'était
pas une erreur prévue de la collecte et finissait avec une trace complète, comme un défaut du code.
Elle devient un refus nommé, cible jamais demandée. La `Location` vient du serveur : elle est
citée par `quote_value` (règle 3 de `conventions.md`), coupée avant `?` et `#` à la main, parce
que `urlsplit`, derrière `without_query`, la refuse aussi.

Une `Location` que httpx2 lui-même ne sait pas lire (une tabulation) n'arrive jamais ici :
`client.send` lève `httpx2.RemoteProtocolError`, une erreur réseau, relancée une fois, puis la
source échoue sur une ligne sans trace.

### 4. Un statut d'erreur à nous : `SourceStatusError`

`src/k_b/etl/source_contract.py:36-43` :

```python
class SourceStatusError(ExpectedSourceError):
    ...
        super().__init__(
            f"HTTP {status} {httpx2.codes.get_reason_phrase(status)}".rstrip()
        )
```

Elle remplace `HTTPError` d'`urllib`. Elle porte `status` et `headers`, un `httpx2.Headers`
**insensible à la casse** : avec un `dict`, `retry-after: 3600` serait invisible sous
`Retry-After`, et un 429 serait relancé à 60 s au lieu d'être laissé. La raison du statut vient de
`httpx2.codes`, jamais du serveur, qui peut y écrire n'importe quoi. Elle vit dans
`source_contract.py`, à côté de `PageRefusedError`, et non dans `http_download.py` : `http_retry.py`
la lit, et `http_download.py` importe déjà `http_retry.py` (un import en cycle sinon).

CISA KEV lit son 304 sur `error.status` (`src/k_b/etl/sources/cisa_kev.py`) ; l'API GitHub calcule
sa pause sur les mêmes en-têtes. `is_served_from` disparaît de `http_retry.py` : il vérifiait qu'une
réponse d'erreur venait du préfixe après les redirections d'`urlopen` ; le préfixe étant contrôlé
avant chaque requête, il était vrai par construction.

### 5. Le corps borné, une seule fois pour trois appelants

`src/k_b/core/outbound.py:65-88`, `read_bounded_body(response, max_bytes, is_late=None)` :
`Content-Length` au-delà du maximum → `BodyTooLargeError` avant toute lecture ; sinon les octets
**décodés** sont lus par morceaux (`iter_bytes`, `:82`) et refusés dès le maximum dépassé ; `is_late`
arrête la lecture quand une échéance passe. La collecte (sans échéance) change l'erreur en
`PageRefusedError` ; les deux connecteurs de l'API IA en `DataApiError` et `GithubError`, avec le
statut, comme avant. C'était la troisième copie du même code (`code.md` : factoriser à la
troisième), décision de Sabine (Q-B).

### 6. Des tests qui ne peuvent pas sortir sur le réseau

`tests/etl/conftest.py:23-27` :

```python
@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    ...
    monkeypatch.setattr(http_download, "open_http_client", open_offline_http_client)
```

Chaque test de `tests/etl/` reçoit un client dont le transport lève : un test qui oublie son faux
réseau échoue au lieu de contacter un vrai site. `FakeNetwork` (`tests/etl/http_helpers.py`)
remplace le transport par un `httpx2.MockTransport` qui enregistre chaque requête : un test peut
donc affirmer qu'une cible **n'a jamais été demandée** (`network.requested_urls() == [URL]`), ce
que `urlopen` ne permettait pas sans réseau. `CountedStream` sert un corps morceau par morceau,
sans `Content-Length`, et compte les morceaux lus : il prouve qu'un corps trop grand est refusé
avant sa fin.

## Choix faits et options écartées

| Choix | Retenu, pourquoi | Écarté, pourquoi |
|---|---|---|
| Qui suit les redirections | Le code, chaque saut contrôlé avant d'être demandé (contrat de #54) | `follow_redirects=True` : httpx2 suivrait avant tout contrôle, l'écart même de #54 |
| Sur quoi porte le contrôle | `str(request.url)` de la requête construite, puis envoyée | La chaîne `urljoin` seule : les `..` la font passer, httpx2 les résout ensuite |
| Construction d'un saut | `build_request` avec `headers` seuls | `response.next_request` : renverrait `Authorization` à une redirection de même origine |
| Une `Location` lisible par httpx2 mais pas par `urljoin` | `PageRefusedError`, jamais demandée (repli tranché par time-knight) | Prendre la cible dans `next_request.url` : dépend d'un calcul interne fait pour suivre les redirections, et le plan écarte `next_request` |
| Statut d'erreur | `SourceStatusError` dans `source_contract.py` | `HttpStatusError` (trop proche de `httpx2.HTTPStatusError`) ; laisser l'erreur de httpx2 (les sources dépendraient du client) ; rendre `bytes \| None` pour le 304 (le téléchargement saurait ce que CISA veut dire) |
| En-têtes de l'erreur | `httpx2.Headers`, insensibles à la casse | `dict` : `Retry-After` invisible sous une autre casse |
| Erreurs réseau | `httpx2.TransportError` remonte telle quelle jusqu'à `extract.py` ; un délai n'est pas relancé, le reste une fois | L'emballer : une classe de plus pour rien |
| `ConnectionError` dans `download` | Retirée (httpx2 change toute `OSError` en `ConnectError`, `ReadError`…) ; gardée dans `EXPECTED_SOURCE_ERRORS`, que d'autres chemins lèvent | La garder partout : code mort |
| Client | Un par tentative, fermé à la fin (choix 1 du plan) | Un client partagé par la collecte : un état de module de plus pour quelques requêtes |
| Corps borné | Une fonction dans `core/outbound.py`, trois appelants (Q-B, Sabine) | Une troisième copie, réunie plus tard |

### Le tri des revues

Tranché par time-knight, délégation de Sabine du 15/10.

**`/code-review high`** (6 constats) :

1. `urljoin` lève `ValueError` sur une `Location` que httpx2 accepte (`https://a]b/`) → **corrigé**
   par le repli : `ValueError` ou `httpx2.InvalidURL` → `PageRefusedError` (`2120795`).
2. tldr compare le premier saut hors préfixe, plus l'URL finale → écarté : choix écrit au plan,
   vérifié par l'essai de bout en bout de Sabine sur le vrai site.
3. `RemoteProtocolError` relancée alors qu'elle échouera de nouveau → écarté : écart déjà accepté,
   et une connexion coupée sans réponse est aussi une `RemoteProtocolError`.
4. Les cookies d'un saut renvoyés aux sauts suivants → écarté : le client est ouvert par tentative,
   son stock de cookies ne vit que le temps d'une chaîne de redirections, et chaque saut de cette
   chaîne est dans le préfixe. Aucun cookie ne quitte l'adresse de confiance.
5. Un client neuf par tentative → écarté : choix 1 du plan, relance rare.
6. `source_contract.py` importe httpx2 pour le type `Headers` → écarté : correction tranchée du plan.

**`/security-review`** : aucun constat (un sous-agent de recherche, aucun de filtrage). Il a essayé,
contre le vrai httpx2, les identifiants dans l'URL (`@`), l'hôte préfixé
(`api.github.com.evil.com`), `http://`, `//evil.com`, l'antislash, `#@`, la tabulation, le NUL, les
`..`, un domaine IDNA, et l'écart entre la requête contrôlée et la requête envoyée : chaque URL qui
passe le contrôle reste sur l'hôte de confiance.

**`/code-review medium`** sur la correction (6 constats) :

1. Le message ne citait ni la `Location` ni le type d'erreur → **corrigé** (`c4451f4`).
2. Le `try` couvre aussi `build_request`, une `ValueError` d'en-tête deviendrait un refus → écarté :
   les en-têtes d'un saut sont déjà passés par la première requête.
3. Deux voies pour une `Location` inutilisable → écarté : comme le 3 ci-dessus.
4. Docstring de `send_following_redirections` muette sur le refus → **corrigé** (`c4451f4`).
5. La première requête lève `httpx2.InvalidURL` brut sur une URL de source mauvaise → écarté :
   l'URL de départ est construite par le code, pas lue d'une source.
6. Le test ne vérifie ni le chemin pris ni le message → **corrigé** avec le 1 (`c4451f4`).

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_redirection_outside_the_prefix_is_refused_without_requesting_it` (`http://`, autre hôte, hôte préfixé, `\@`) | Une cible hors préfixe n'est jamais demandée : le faux réseau n'a reçu que la 1re URL |
| `test_a_redirection_whose_dot_segments_leave_the_prefix_is_refused` | Le contrôle porte sur l'URL normalisée, pas sur la chaîne |
| `test_a_redirection_inside_the_prefix_is_followed_without_the_token`, `test_a_token_is_not_sent_again_to_the_same_url_after_a_redirection` | Le jeton ne part qu'à la 1re requête, même vers la même URL |
| `test_the_last_redirection_allowed_is_followed`, `test_one_redirection_too_many_is_refused` | 10 sauts suivis, le 11e refusé |
| `test_the_body_of_a_redirection_is_never_read` | Le corps d'un 3xx n'est jamais lu |
| `test_a_redirection_httpx2_reads_but_not_its_resolution_is_refused` (3 cas) | Refus nommé, `Location` citée sans `?token=secret#part`, type d'erreur cité, cible jamais demandée. Rouge sur `bef170a` (`ValueError: Invalid IPv6 URL`), puis sur `2120795` (message sans valeur) |
| `test_a_compressed_body_too_large_once_decoded_is_refused_before_its_end` | Le corps est borné une fois décompressé, avant sa fin |
| `test_the_headers_of_a_status_error_are_read_whatever_their_case` | `retry-after` en minuscules est lu |
| `test_an_unmodified_catalog_returns_nothing`, `test_a_redirection_out_of_cisa_is_refused_not_read_as_unmodified` | Le 304 est lu sur le statut ; une redirection de CISA hors préfixe fait échouer la source |
| `uv run pytest` : 3112 verts ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` verts | La suite entière, avec les tests inchangés des deux connecteurs de l'API IA |
| `git grep -nE "urllib\.(request\|error)\|urlopen\|HTTPError\|URLError" src tests` : vide | Plus rien d'`urllib` ne télécharge ; seul `urllib.parse` reste (il analyse) |

Tests rouges d'abord, avec une réserve : sur l'ancien code, les tests du contrat de #54 n'ont été
rouges que par l'`ImportError` de `SourceStatusError`. `urlopen` n'offre aucun point d'injection
sans réseau, donc aucun test n'a pu montrer l'ancien comportement fautif lui-même. Une `ImportError`
ne prouve pas le comportement : c'est le faux réseau, sur le nouveau code, qui le prouve.

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas laisser httpx2 suivre les redirections et contrôler l'URL finale ?** Parce
   qu'à ce moment chaque saut a déjà été demandé : un serveur de la source fait contacter par K-B
   l'adresse de son choix. Le contrôle doit précéder la requête
   (`src/k_b/etl/http_download.py:131-133`).
2. **Pourquoi comparer `str(request.url)` plutôt que l'URL calculée ?** Parce que httpx2 normalise
   (segments `..`, casse de l'hôte, port par défaut) avant d'envoyer : on contrôle ce qui part
   réellement, pas une chaîne qui peut différer (`:122`, `:131`).
3. **Comment le jeton GitHub ne fuit-il jamais vers une redirection ?** Il est dans
   `unredirected_headers`, mis à la seule première requête (`:103`) ; chaque saut est reconstruit
   avec `headers` seuls, jamais par `next_request`, qui garde `Authorization` pour la même origine.
   Le test vers la même URL le prouve.
4. **Que se passe-t-il si un serveur renvoie une `Location` piégée (`https://a]b/`) ?** Refus nommé,
   `PageRefusedError`, ligne de journal sans trace, `Location` citée tronquée et échappée, rien
   demandé (`:123-130`).
5. **Pourquoi `SourceStatusError` porte-t-elle un `httpx2.Headers` et pas un `dict` ?** Les noms
   d'en-têtes HTTP ne tiennent pas compte de la casse ; un `dict` raterait `retry-after` et
   relancerait un 429 que le service demande d'attendre une heure
   (`src/k_b/etl/source_contract.py:36-48`, `test_the_headers_of_a_status_error_are_read_whatever_their_case`).

## Zones non vérifiées

- **Le comportement des vrais sites** : la PR n'a été testée que contre le faux réseau. tldr lit
  désormais la cible du premier saut hors préfixe, plus l'URL finale. Si tldr.tech passait par un
  saut intermédiaire avant `https://tldr.tech/ai`, chaque jour sans édition ferait échouer la
  source. L'essai de bout en bout de Sabine (`uv run --env-file .env.e2e_test pytest -m e2e`, deux
  fois pour le 304 de CISA) le vérifie avant la fusion ; son résultat va dans la PR.
- **Le cas `httpx2.InvalidURL`** du bloc de la section 3 n'a été trouvé qu'avec une `Location` qui
  commence par une espace (` //` suivi d'un trait d'union conditionnel) : `urljoin` retire l'espace
  et y lit un hôte, httpx2 y lit un chemin. 300 000 `Location` tirées au hasard, sans espace en tête
  ni en fin, n'en ont donné aucun autre. Sur le vrai réseau, h11 retire ces espaces : ce cas n'est
  atteint que par le faux transport. Gardé sur le tri de time-knight, côté sûr.
- **L'intérieur de httpx2 et de httpcore** : la revue de sécurité a vérifié que `request.url.host`
  est l'hôte contacté, pas le transport plus bas. Le comportement de `client.send` sur une
  `Location` illisible (il lève avant de rendre la réponse) est constaté sur httpx2 2.13.1, lu dans
  `_client.py:497-522` ; une autre version pourrait changer.
- **Les cookies** : gardés par le client entre les sauts d'une même chaîne, comportement nouveau
  par rapport à `urllib`, non écrit dans `docs/specs-collecte.md`.
- **Le pic mémoire** `max_bytes` + 1 Mio d'un corps compressé repose sur la taille des morceaux que
  httpx2 décompresse, reprise du plan de time-knight, ni lue dans le code de httpx2 ni mesurée.

## Ce qui reste

- **L'essai de bout en bout de Sabine**, avant la fusion (étape 10 de la mission).
- **La durée totale d'un téléchargement** n'est pas bornée : 30 s par opération réseau seulement
  (`docs/specs-collecte.md`), comme avec `urllib`. Non demandé ici.
- **Un client par collecte** plutôt que par tentative : écarté pour l'instant, à reconsidérer si le
  nombre de requêtes GitHub par collecte grandit.
