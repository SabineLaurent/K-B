# La collecte des releases GitHub : un brut par dépôt, sans rien perdre en silence

Suite de [la commande `kb collect`](2026-09-30-commande-kb-collect.md) et de
[la collecte CISA KEV](2026-09-30-collecte-cisa-kev.md).

- **Date** : 2026-10-02
- **Branche** : `feat/github-releases` (commit `23afcc8`)
- **Issue** : #10 « Collecter les releases GitHub des dépôts choisis »
- **Fichiers principaux** : `src/k_b/github_api.py` (connexion), `src/k_b/github_releases_source.py`
  (collecte), `src/k_b/github_releases.py` (lecture), et leurs tests ; la fixture
  `tests/fixtures/github_releases_extract.json`.
- **Autres fichiers** : `src/k_b/user_agent.py` (constante commune), `src/k_b/cisa_kev_source.py`
  (l'importe), `src/k_b/collect.py` (déclare les nouvelles sources), `docs/specs-collecte.md`
  (nouvelle valeur du `User-Agent`, état de la source).

## Le pourquoi

K-B fait de la veille sur les outils qu'utilise Sabine. Une nouvelle version de LangChain, de
LangGraph, de LlamaIndex ou de Claude Code se publie comme une *release* GitHub. Ce code récupère
ces releases à chaque `kb collect` et les range dans `raw/`, sans rien modifier. Il fournit aussi
le lecteur qui, plus tard, en fera des items.

C'est la première des trois collectes GitHub. Les deux autres, les alertes de sécurité et les
dépôts les plus étoilés, viennent avec #11. La connexion à l'API est donc écrite pour être
partagée.

## Le comment

### 1. Une source par dépôt

`collect.py` sait déjà gérer des sources indépendantes : chacune a sa date de dernière collecte,
son dossier, et sa panne n'arrête pas les autres. Il suffit donc de déclarer une source par
dépôt :

```python
SOURCES: list[Source] = [
    CisaKevSource(),
    *(GithubReleasesSource(repository) for repository in TRACKED_REPOSITORIES),
]
```
(`src/k_b/collect.py:30`)

Chaque source reçoit un nom sûr, construit à partir du dépôt :

```python
        if not OWNER_SLASH_NAME.fullmatch(repository) or ".." in repository:
            raise ValueError(f"not an owner/name repository: {repository!r}")
        self.repository = repository
        self.name = "github_releases_" + re.sub(r"[^a-z0-9]+", "_", repository.lower())
```
(`src/k_b/github_releases_source.py:28`)

`langchain-ai/langchain` devient `github_releases_langchain_ai_langchain`. Ce nom sert à la fois
de nom de dossier dans `raw/automation/` et de clé dans `collection_state.json`. Le contrôle du
format `owner/name` et le refus de `..` sont une défense en profondeur : la liste est écrite dans
le code et `collect.py` revérifie le nom (`SAFE_PATH_SEGMENT`), mais une erreur de frappe est
arrêtée dès la création de la source.

### 2. La connexion : jeton, délai, taille, redirection

```python
    token = os.environ.get(TOKEN_VARIABLE)
    if token:
        # urlopen follows redirections: an unredirected header never leaves the first request.
        request.add_unredirected_header("Authorization", f"Bearer {token}")
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        if not response.url.startswith(API_URL):
            raise ValueError(f"response redirected outside {API_URL}, refused")
        body = response.read(MAX_RESPONSE_BYTES + 1)
```
(`src/k_b/github_api.py:29`)

- **Le jeton est facultatif.** Sans jeton, GitHub accepte 60 requêtes par heure, ce qui suffit
  pour 4 dépôts. Avec `KB_GITHUB_TOKEN`, la limite monte à 5 000.
- **`add_unredirected_header`** : `urlopen` suit les redirections automatiquement. Les en-têtes
  ajoutés normalement (`Request(headers=...)`) sont **recopiés** dans la requête redirigée. Les
  en-têtes « non redirigés » ne le sont pas. Si GitHub, ou un intermédiaire, renvoyait vers un
  autre domaine, le jeton ne partirait donc pas avec la requête. La revue de sécurité l'a vérifié
  dans le code de `urllib` (`HTTPRedirectHandler.redirect_request` ne recopie que `req.headers`).
- **Le contrôle de `response.url`** vient après, et protège la donnée : une réponse servie
  ailleurs que sur `https://api.github.com/` est refusée.
- **`read(MAX_RESPONSE_BYTES + 1)`** : on lit au plus un octet de plus que la limite. S'il est
  là, la réponse est trop grosse et elle est refusée, sans jamais charger plus que 5 Mo et un
  octet en mémoire.

Les autres en-têtes suivent la doc GitHub. `Accept: application/vnd.github+json` est recommandé.
`X-GitHub-Api-Version: 2026-03-10` fige la version de l'API, pour qu'un changement de GitHub ne
casse pas la lecture en silence. Le `User-Agent` est obligatoire : sans lui, GitHub répond `403`.

### 3. Rien de neuf, rien d'écrit

```python
        if last_collected_at is None:
            return raw_response
        publication_dates = [
            release.published_at for release in read_releases(raw_response, self.repository)
        ]
        if not any(published_at > last_collected_at for published_at in publication_dates):
            return None
```
(`src/k_b/github_releases_source.py:38`)

À la première collecte (`None`), on garde la page telle quelle. Ensuite, on regarde si au moins
une release a été publiée après la dernière collecte réussie. Si ce n'est pas le cas, on renvoie
`None`, et `collect.py` n'écrit aucun fichier, conformément à la règle « une source qui n'a rien
de neuf n'écrit rien ». Quand il y a du neuf, c'est **la réponse entière, octet pour octet**, qui
est écrite : le filtrage se fera à la lecture (règle du brut intact).

Aucune release n'est perdue entre deux collectes. `now`, la date enregistrée comme dernière
collecte, est fixée **avant** les appels réseau. Une release publiée pendant la collecte est plus
récente que `now` : elle sera revue la fois suivante, au pire en double, et la fusion retire les
doublons.

### 4. L'avertissement de pagination

```python
        is_page_full = len(publication_dates) >= RELEASES_PER_PAGE
        if is_page_full and min(publication_dates) > last_collected_at:
            logger.warning(
```
(`src/k_b/github_releases_source.py:45`)

On ne lit que la première page, les 100 releases les plus récentes. Le risque est qu'il y ait eu
plus de 100 releases depuis la dernière collecte. Le signe : la page est pleine **et** même sa
release la plus ancienne est plus récente que la dernière collecte. On ne peut alors pas savoir
si la page 2 contient des releases jamais vues. Le message sort sur la sortie d'erreur : faute de
configuration du journal, Python affiche les `WARNING` par défaut. Il dit qu'il est temps de
gérer la pagination.

### 5. La lecture : des types contrôlés, sans le login de l'auteur

`read_releases` transforme le brut en `Release`. Chaque champ est contrôlé à la frontière,
parce que la réponse d'une API est une entrée non fiable :

```python
    if not isinstance(url, str) or not url.startswith(RELEASE_URL_PREFIX):
```
(`src/k_b/github_releases.py:38`)

```python
    if parsed_date.tzinfo is None:
        raise ValueError(f"release {position}: published_at without a time zone")
```
(`src/k_b/github_releases.py:66`)

Une URL hors de `https://github.com/` est refusée : un lien vers un autre site n'entrera jamais
dans un item. Une date sans fuseau est refusée, parce que Python ne sait pas comparer une date
sans fuseau à `last_collected_at`, qui en a un (il lèverait une `TypeError`). GitHub écrit ses dates
en UTC avec un `Z` final, que `datetime.fromisoformat` comprend depuis Python 3.11.

La dataclass `Release` n'a **aucun champ auteur**. Le login de l'auteur est une donnée personnelle
dont la veille n'a pas besoin (RGPD art. 5.1.c, minimisation). Il reste dans le brut, comme le
prévoit le registre des traitements (« Login GitHub : brut seulement »).

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Brut | **Un fichier par dépôt**, la réponse octet pour octet (décidé avec Sabine) | Un JSON commun aux 4 dépôts : il réécrit les octets reçus (le brut n'est plus intact), une panne bloque les 4, et le fichier est réécrit dès qu'un seul dépôt a du neuf |
| Forme | **Une instance de source par dépôt** : `collect.py` est inchangé | Des sous-dossiers `github_releases/<owner>/<repo>/` : il faudrait modifier `collect.py` et le contrôle des noms, pour un gain seulement visuel |
| Incrémental | **Comparer les dates de publication** | Requête conditionnelle avec `ETag` : il faudrait garder 4 ETag dans l'état, pour économiser 4 requêtes sur 5 000 par heure |
| Pagination | **Première page seulement, avec un avertissement** quand elle est entièrement neuve (proposé par Sabine, critère affiné ensemble) | Avertir dès que `Link: rel="next"` existe : c'est toujours le cas, puisque les 4 dépôts ont plus de 100 releases au total ; le message n'aurait rien signifié |
| Modules | **Trois modules** : connexion, collecte, lecture (règle SoC de `code.md`, même découpage que CISA) | Un seul module : le lecteur ne pourrait plus être testé sans simuler le réseau, et la connexion n'aurait pas pu servir aux deux collectes de #11 |
| Version d'API | **`2026-03-10`**, la plus récente (`GET /versions`) | Pas de version : GitHub prend `2022-11-28` par défaut, et un changement de défaut casserait la lecture sans prévenir |
| `User-Agent` | **`K-B (+https://github.com/SabineLaurent)`**, dans `user_agent.py`, partagé avec CISA (décidé avec Sabine) | L'ancienne URL du dépôt : il est privé, donc elle mène à un 404. `K-B` seul : accepté par GitHub, mais ne donne aux sites sans compte aucun moyen de savoir qui les interroge |
| Modèle | **`dataclass`**, comme `Vulnerability` dans `cisa_kev.py` | Pydantic, prévu par `specs-collecte.md` pour les items : ce n'est pas encore une dépendance du projet, et l'item commun n'existe pas encore |
| Taille maximale | **5 Mo**, mesuré : une page de 100 releases de `claude-code` pèse 2,2 Mo | Une limite plus serrée échouerait sur une page normale |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_request_follows_the_github_conventions_and_has_a_timeout` | URL, `User-Agent`, `Accept`, version d'API et délai sont bien envoyés |
| `test_the_token_is_sent_but_never_forwarded_to_a_redirection` | Le jeton est envoyé, mais pas parmi les en-têtes recopiés vers une redirection |
| `test_without_a_token_the_request_is_anonymous` | Sans variable, aucun en-tête `Authorization` |
| `test_a_redirection_away_from_https_api_github_com_is_refused` (2 cas) | `http://` et un domaine sosie (`api.github.com.example.com`) sont refusés |
| `test_a_response_larger_than_the_limit_is_refused` | La limite de taille fonctionne |
| `test_a_recorded_response_gives_one_release_per_entry_newest_first` | Une vraie réponse enregistrée donne les bonnes `Release`, avec une date UTC |
| `test_the_author_login_is_not_kept` | `Release` n'a pas de champ auteur |
| `test_an_invalid_release_is_refused_with_its_position` (6 cas) | Tag absent, date absente, illisible ou sans fuseau, URL étrangère, `prerelease` non booléen : refusés |
| `test_a_page_without_any_new_release_returns_nothing` | Rien de neuf, rien d'écrit |
| `test_a_full_page_of_new_releases_warns_that_some_may_be_missing` et `test_no_warning_when_the_page_reaches_back_to_the_last_collection` | L'avertissement sort quand il le faut, et seulement à ce moment-là |
| `test_each_tracked_repository_is_a_source_of_kb_collect` | Les 4 dépôts sont bien des sources de `kb collect` |
| `uv run pytest` : 67 tests verts | Rien de l'existant n'est cassé (CISA lit le `User-Agent` déplacé) |
| Vrai `kb collect` dans un dossier temporaire : 5 sources `ok`, 5 bruts écrits, code 0 ; deuxième passage : `ok` partout, aucun brut de plus | Le tout fonctionne sur la vraie API, et l'incrémental aussi |
| `/code-review` et `/security-review` en sous-agent sans contexte | Aucun bug, aucune faille rapportés |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas mettre le jeton directement dans `headers=` ?** Parce que `urllib` recopie
   ces en-têtes vers une redirection. Avec `add_unredirected_header`, le jeton ne quitte jamais la
   première requête (`github_api.py:32`).
2. **Que se passe-t-il si langchain publie 150 releases entre deux collectes ?** On garde les 100
   plus récentes, et un avertissement nomme le dépôt : on sait qu'il faut gérer la pagination
   (`github_releases_source.py:45`). Rien n'est perdu en silence.
3. **Où est la donnée personnelle, et que devient-elle ?** Dans `author.login` du brut. Elle
   n'entre pas dans `Release` (minimisation), comme le prévoit le registre des traitements
   (`github_releases.py`, classe `Release`).
4. **Pourquoi lire la réponse dans `fetch` alors que le brut doit rester intact ?** On la lit
   seulement pour décider s'il faut l'écrire. Ce qui est écrit est la réponse d'origine, non
   modifiée (`github_releases_source.py:53`).
5. **Si un dépôt est supprimé ou devient privé ?** GitHub répond `404` : la requête échoue
   pour ce dépôt seul. Sa date de
   dernière collecte n'avance pas, les autres dépôts continuent, et `kb collect` sort avec le code 1
   en nommant la source.

## Zones non vérifiées

- **Le tri de GitHub** : la liste est triée par date de **création**, pas de publication. Une
  release restée longtemps en brouillon puis publiée pourrait se trouver au-delà de la première
  page sans déclencher l'avertissement. Signalé par la revue comme spéculatif ; non testé, pas de
  cas réel connu.
- **La redirection d'un dépôt renommé** (GitHub répond `301` vers `api.github.com/repositories/<id>`) :
  l'URL reste sur le bon domaine, mais le jeton n'est pas renvoyé. La requête redirigée part donc
  sans jeton. Ça fonctionne sur des données publiques, mais n'a pas été observé en vrai.
- **Le message d'avertissement en conditions réelles** : il n'est vérifié qu'en test (page
  réduite à 3), jamais sur une vraie collecte.

## Ce qui reste

- **La pagination** : seulement si l'avertissement apparaît un jour.
- **Les dépôts « sous le coude »** de `docs/sources.md` : à ajouter à `TRACKED_REPOSITORIES` à
  l'usage.
- **Le passage des `Release` à l'item commun** (Pydantic) et à la base : avec la fusion et le
  stockage (`docs/specs-collecte.md`, « Du brut au jeu d'items »).
- **Les alertes de sécurité et les dépôts les plus étoilés** : #11, qui réutilisera `github_api.py`.
