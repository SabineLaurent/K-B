# Collecter le top 100 des dépôts les plus forkés

- **Date** : 2026-10-19
- **Branche** : `feat/github-most-forked`
- **Issue** : #264
- **Fichiers principaux** : `src/k_b/etl/sources/github_most_forked.py`,
  `src/k_b/etl/source_kinds.py`, `tests/etl/sources/test_github_most_forked.py`,
  `tests/fixtures/github_most_forked_extract.json`, `docs/ADR/journal-decisions-projet.md`
- **Série** : le jumeau de [la collecte des dépôts étoilés](2026-10-02-collecte-depots-etoiles.md)
  (2026-10-02, PR de #11).

## Le pourquoi

Sabine a décidé le 19/10 que les fiches du top 100 des plus étoilés et du top 100 des plus forkés
seront les deux premiers outputs de K-B. Le premier top était collecté depuis le 02/10, le second
ne l'était pas : `docs/specs-api.md` (P8) le disait (« la recherche des plus étoilés trie par
`stars` »). Cette PR ajoute la collecte du second. Elle ne fait que collecter : la fiche `.md` est
#265, l'affichage `kb top` est #266. Les deux liront ce que cette PR écrit dans `raw/`.

Un classement n'entre pas en base (journal ADR, 2026-10-07, « Tops GitHub (P7, P8) ») : le JSON
reçu est à la fois le brut et le top du jour.

## Le comment

### Une source de plus dans la liste unique

`kb collect` lance chaque source déclarée dans `SOURCE_KINDS`. Ajouter une source, c'est une
entrée de plus, placée juste après les étoilés (`src/k_b/etl/source_kinds.py:59-64`) :

```python
    SourceKind(
        github_most_forked.FOLDER_PREFIX,
        (GithubMostForkedSource(),),
        # No reader: the ranking does not enter the base (decision "Tops", 2026-10-07).
        None,
    ),
```

Le troisième champ, `None`, est le lecteur d'items. Sans lecteur, `kb import` saute le dossier et
le dit au journal (`source without a reader of items, skipped by the item reader`). Le nom du
dossier sous `raw/` vient de `FOLDER_PREFIX`, et le dossier d'acquisition de
`acquisition_dir_name = AUTOMATED_WATCH_DIR_NAME`. Le brut tombe donc sous
`raw/automated_watch/github_most_forked/<horodatage>.json`.

### La requête : la recherche REST triée par forks

`src/k_b/etl/sources/github_most_forked.py:26` et `:40-48` :

```python
SEARCH_QUERY = "forks:>10000"
...
            "sort": "forks",
...
        raw_response = get_from_github_api(f"search/repositories?{urlencode(query)}")
        read_ranking(raw_response)
        return raw_response
```

La recherche de GitHub exige un critère `q`. `forks:>10000` doit garder **tout** le top 100 et ne
rien couper. Je l'ai mesuré par un appel réel le 2026-10-19 : 533 dépôts, et le 100e
(scikit-learn/scikit-learn) a 27 552 forks, loin au-dessus du seuil. Le commentaire de la
constante garde cette mesure et sa date, comme `stars:>10000` chez les étoilés. `sort=forks` est
une valeur documentée du paramètre (`stars|forks|help-wanted-issues|updated`, voir les sources).

`fetch` lit la réponse **avant** de la rendre. Si la lecture lève, l'extraction n'écrit rien et la
date de dernière collecte ne bouge pas. Sinon, `fetch` rend les octets reçus tels quels : c'est le
brut.

### Refuser la page entière : l'exception du classement

`src/k_b/etl/sources/github_most_forked.py:66-71` :

```python
    response = json.loads(raw_response)
    items = response.get("items") if isinstance(response, dict) else None
    if not isinstance(items, list):
        raise ValueError("expected a search response with a list of items")
    if response.get("incomplete_results") is not False:
        raise ValueError("incomplete search results, refused")
```

En général, une source garde les entrées valides et rejette les invalides une à une (règle 1 de
`conventions.md`). Un classement fait exception : il refuse sa page entière. Un top de 99 dépôts,
ou marqué incomplet par GitHub, ferait croire qu'un dépôt est sorti du top alors qu'il manque
seulement à la réponse. `is not False` refuse aussi un `incomplete_results` absent ou non booléen,
pas seulement `True`. Une réponse qui n'est pas du JSON lève `json.JSONDecodeError`, qui hérite de
`ValueError` : un test le prouve.

### Valider chaque dépôt, et ne citer du nom que sa longueur

`src/k_b/etl/sources/github_most_forked.py:83-89` et `:101` :

```python
    if not isinstance(full_name, str):
        raise ValueError(f"repository {rank}: full_name is not a string")
    # Its length only: the name carries the owner's login.
    if not is_repository_name(full_name):
        raise ValueError(
            f"repository {rank}: not an owner/name, length {len(full_name)}"
        )
...
    if not isinstance(forks, int) or isinstance(forks, bool):
```

- **Le nom** `owner/name` porte le login du propriétaire. Dans 36 dépôts sur 100, ce propriétaire
  est une personne (relevé du 2026-10-19). Le login est donc une donnée personnelle au registre.
  La règle 3 de `conventions.md` interdit de citer un tel champ dans un message : on n'en donne
  que la position (le rang) et la mesure (la longueur). GH Archive fait déjà de même.
  `is_repository_name` refuse aussi `..` et `.`, parce que #265 construira un chemin et une URL
  depuis ce nom.
- **Le nombre de forks** : `bool` est une sous-classe de `int` en Python, donc
  `isinstance(True, int)` est vrai. Sans le second test, `"forks_count": true` passerait pour 1.
- **`html_url`** est vérifié par son préfixe `https://github.com/`, puis jeté. #265 construit
  l'URL depuis le nom (journal ADR, 2026-10-08).

Le lecteur rend des `ForkedRepository(rank, full_name, description, forks)`
(`github_most_forked.py:51-57`). Ce sont les quatre champs que #265 (la fiche) et #266
(`kb top`) liront. Ni `topics` ni `created_at`, que les étoilés lisent : rien ne s'en sert (RGESN
1.6). Le brut, lui, garde tout.

### Une fixture tirée d'une vraie collecte, sans personne dedans

`tests/fixtures/github_most_forked_extract.json` garde trois dépôts, intacts, d'un appel réel du
2026-10-19, avec `total_count` et `incomplete_results`. Ce sont les **rangs 4 à 6**, et non 1 à 3 :
les trois premiers appartiennent à des personnes (`owner.type == "User"`), et chaque dépôt brut
porte le login, l'identifiant et l'URL d'avatar de son propriétaire. Le dépôt devient public le
25/10. Les rangs 4 à 6 sont trois organisations consécutives. Le choix est de Sabine (option A,
2026-10-19). Le troisième dépôt n'a pas de description (`null`), ce qui donne un cas de test réel.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| REST (`GET /search/repositories`) | Décision de Sabine du 19/10 : la date du 25/10. Aucun POST n'existe dans K-B, et #86 (httpx) venait avant. Les étoilés sont en REST depuis le 02/10 : un seul chemin de collecte. Entrée d'ADR datée du 19/10, qui révise celle du 07/10 pour la méthode seule. | GraphQL au POC : il fallait un client POST avant #86. Il reste plus sobre (facteur 33 sur les étoilés, 28 sur les forkés) ; #269 le portera. |
| Module jumeau, contrôles recopiés | Deux occurrences : `code.md` factorise à la troisième, et #269 réécrit les deux classements d'un coup. Choix validé par time-knight (délégation de Sabine). | Une fonction partagée `read_search_ranking` : elle toucherait les étoilés, hors du périmètre. |
| `RANKING_SIZE` et `REPOSITORY_URL_PREFIX` importés des étoilés | Une connaissance à un seul endroit (`code.md`, DRY). C'est le premier import d'un module de source vers un autre, temporaire jusqu'à #269. | Recopier les constantes : deux valeurs qui pourraient diverger. |
| Nom refusé cité par sa longueur, dans les deux classements | Règle 3 de `conventions.md` : un champ porteur d'une donnée personnelle n'est jamais cité. La revue a relevé que les étoilés le citaient encore par `{full_name!r}` : le login arrivait dans `kb.log`, coupé à 100 caractères sur la ligne datée et en entier dans la trace. Corrigé dans cette PR, décision de Sabine (option A) : les journaux partent en ligne le 08/11 et #269 n'a pas de jalon. | Renvoyer la correction des étoilés à #269 (option B). |
| Fixture : rangs 4 à 6 | Minimisation (RGPD), décision de Sabine. | Rangs 1 à 3 : trois logins de personnes dans un dépôt public. |
| Nom du test d'ordre gardé (`..._order_of_2026_10_06`) | Changement chirurgical : l'ordre du 06/10 reste, avec une entrée de plus. | Le renommer : une ligne de plus sans gain. |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_most_forked_repositories_are_a_source_of_kb_collect` | `kb collect` lance la source. |
| `test_its_snapshots_are_written_under_automated_watch` | Le brut va sous `raw/automated_watch/github_most_forked/`. |
| `test_the_request_asks_for_the_100_most_forked_repositories` | `q=forks:>10000`, `sort=forks`, `order=desc`, `per_page=100`. |
| `test_a_ranking_shorter_than_100_is_not_written`, `test_an_incomplete_ranking_is_not_written` | `fetch` lève : rien n'est écrit. |
| `test_a_response_that_is_not_json_is_refused`, `..._without_a_list_of_items_is_refused` | Une page illisible est refusée. |
| `test_an_invalid_repository_is_refused_with_its_rank` (7 cas), `..._not_an_object_...` | Un dépôt invalide fait refuser le classement, avec son rang. |
| `test_a_refused_name_is_quoted_by_its_length_only`, `test_a_name_that_is_not_a_string_is_refused_by_its_type`, dans les tests des forkés et des étoilés | Le message exact ne contient pas le nom. |
| `test_a_github_ranking_is_skipped_and_logged[github_most_forked]` (`tests/etl/test_transform.py`) | L'import saute le classement et le dit. |
| `test_the_sources_are_collected_in_the_order_of_2026_10_06`, test du quota (`tests/etl/test_source_kinds.py`) | Ordre de collecte ; la source appelle la recherche, hors du quota principal. |
| `uv run pytest -q` → 1881 passed ; `ruff check`, `ruff format --check`, `mypy --strict` verts | Rien d'autre n'a cassé. |
| Appel réel du 2026-10-19, 17:40:43Z → 200, `total_count` 533, `incomplete_results` false, 100 dépôts | Le critère garde le top 100. |

## Ce que tu dois pouvoir défendre

1. **Pourquoi REST, alors que l'ADR du 07/10 avait choisi GraphQL ?** La méthode seule est révisée,
   par une entrée datée du 19/10 : il fallait un client POST avant le 25/10, et #86 venait avant.
   Le coût est mesuré (brut environ 30 fois plus lourd) et porté par #269.
2. **Que se passe-t-il si GitHub renvoie 99 dépôts ?** `read_most_forked` lève, `fetch` aussi,
   l'extraction n'écrit rien et la date ne bouge pas. La collecte suivante prend un nouvel
   instantané (`github_most_forked.py:72-75`).
3. **Où sont les données personnelles ?** Le login du propriétaire, dans le nom. Il est au brut, pas
   en base (aucun lecteur). Il n'est jamais cité dans un message (`:86-89`, et de même chez les
   étoilés depuis cette PR), et la fixture n'en contient aucun de personne.
4. **Pourquoi `forks:>10000` ?** La recherche exige un critère. Celui-ci a été mesuré pour ne rien
   couper du top 100 (100e à 27 552). S'il coupait un jour, la réponse aurait moins de 100 dépôts
   et serait refusée : l'erreur se verrait.
5. **Pourquoi `isinstance(forks, bool)` ?** `True` est un `int` en Python ; sans ce test, un
   booléen passerait pour 1 fork.

## Zones non vérifiées

- Le quota de la recherche (nombre de requêtes par minute) n'a pas été relu pour cette PR : la
  source fait une requête par collecte.
- La spec OpenAPI de GitHub déclare `description` comme `string` obligatoire, mais la réponse réelle
  porte `null` pour un dépôt sans description (rang 6). Le lecteur accepte les deux ; c'est la
  réponse observée qui fait foi.
- Le seuil `forks:>10000` peut un jour couper le top 100 si les forks baissent : non surveillé, mais
  visible (classement refusé, voir la question 4).

## Ce qui reste

- **#265** : la fiche `.md` de chaque top en fin de `kb import`, et la purge du JSON précédent.
- **#266** : `kb top`, l'affichage du dernier relevé.
- **#269** : les deux tops en GraphQL, et la réécriture commune des deux lecteurs.
- **Signalé, non fait ici** : les tests des étoilés gardent trois constantes mortes
  (`COLLECTED_AT`, `RAW_FILE_PATH`, `PUBLISHED_AT`) et un test au nom faux
  (`..._keeps_an_empty_description` vérifie `None`).

Hors de cette note : les autres commits et fichiers listés au lancement de la note appartiennent à
des PR déjà fusionnées sur `main` ; cette branche n'en a que cinq (93929b6, fc4ee99, 42f2a95, 9b4d372, et celui de cette note).

## Sources

| Source | URL | Consultée le |
|---|---|---|
| GitHub REST API, description OpenAPI, `GET /search/repositories` (`sort` : `stars`, `forks`, `help-wanted-issues`, `updated` ; `per_page` max 100 ; `incomplete_results` booléen), lue par Context7 | https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json | 2026-10-19 |
| Appel réel `GET https://api.github.com/search/repositories?q=forks:>10000&sort=forks&order=desc&per_page=100`, sans jeton | https://api.github.com/search/repositories | 2026-10-19 |
