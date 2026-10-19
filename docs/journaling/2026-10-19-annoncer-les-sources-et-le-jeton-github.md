# `kb collect` annonce ses sources et l'absence du jeton GitHub

- **Date** : 2026-10-19
- **Branche** : `feat/collect-announces-sources`
- **Issue** : #63 (critère élargi par Sabine le 19/10)
- **Fichiers principaux** : `src/k_b/commands/collect_command.py`, `tests/test_cli.py`,
  `tests/etl/test_source_kinds.py`, `docs/specs-collecte.md`

## Le pourquoi

Jusqu'ici, `kb collect` ne parlait qu'à la fin : une ligne par source (`ok`, `failed (…)`,
`skipped (…)`). Rien ne disait au lancement ce qui allait tourner, ni que, sans `KB_GITHUB_TOKEN`,
GitHub n'accorde que 60 requêtes par heure au lieu de 5 000 : seule une docstring le disait
(`github_api.py:20`). C'est la demande n° 4 de la revue certif du 04/10 pour E1 : une collecte qui
dit elle-même ses limites. La sortie de `kb collect` servira de preuve dans le livrable E1 (#25).

## Le comment

### 1. Une seule liste de sources, lue deux fois

`src/k_b/commands/collect_command.py:44`

```python
    sources = list_collected_sources(collect_only, environ, SOURCE_KINDS)
    log_collection_start(sources, environ)
```

Avant, la liste était construite dans l'appel à `collect_all_sources`. Elle est maintenant gardée
dans une variable : l'annonce et la collecte lisent **la même liste**. L'annonce ne peut donc pas
nommer une source qui ne tourne pas, ni en oublier une. La règle « Zotero ne tourne que si
`KB_ZOTERO_DIR` est posé » reste écrite à un seul endroit (`list_collected_sources`) : l'annonce
ne la recopie pas.

### 2. L'annonce va au journal, pas au résultat

`src/k_b/commands/collect_command.py:68`

```python
    logger.info("sources to collect: %s", ", ".join(source.name for source in sources))
```

Règle 3 de `conventions.md` : « `print` donne le résultat d'une commande ; `logger` donne le
déroulé ». Annoncer ce qui va tourner, c'est du déroulé. Le journal date chaque ligne en UTC
(`2026-10-19T08:18:45Z INFO k_b.cli: sources to collect: …`), l'écrit sur la sortie d'erreur et
dans `logs/kb.log`. Chaque nom est celui de la ligne de fin (`source.name`) : l'annonce et le bilan
se répondent un à un (choix de Sabine, option (b)).

### 3. L'avertissement du jeton : présence seulement, jamais la valeur

`src/k_b/commands/collect_command.py:69`

```python
    if not environ.get(TOKEN_VARIABLE) and any(
        is_github_core_quota_source(source) for source in sources
    ):
```

Le jeton n'est lu que pour savoir s'il est posé (une chaîne vide compte comme absente, comme dans
`github_api.py:32`). Le message cite le **nom** de la variable (`TOKEN_VARIABLE`, importé de
`github_api.py`), jamais sa valeur : un secret n'entre dans aucun journal (`code.md`, « Secrets »).
Niveau `WARNING` : c'est une limite, pas un échec ; la collecte continue.

### 4. Quelles sources sont « GitHub » : celles du quota principal

`src/k_b/commands/collect_command.py:27`

```python
# The kinds whose sources call the GitHub REST API on its primary quota, the one KB_GITHUB_TOKEN
# raises from 60 to 5,000 requests per hour. Not github_most_starred: it calls the search, which
# has its own quota, apart. Not gh_archive, which reads BigQuery.
GITHUB_CORE_QUOTA_FOLDER_PREFIXES = frozenset(
    {github_releases.FOLDER_PREFIX, github_advisories.FOLDER_PREFIX}
)
```

Trois sources appellent l'API REST de GitHub. Mais `github_most_starred` appelle
`search/repositories` (`github_most_starred.py:49`), et GitHub compte la recherche sur un quota à
part (objet `search` de `GET /rate_limit`, distinct de `core`). Annoncer « 60 requêtes par heure »
quand elle tourne seule serait faux : la revue de code l'a relevé, time-knight a tranché. Une source
est reconnue par sa sorte : `find_source_kind(source.name, SOURCE_KINDS)` (`collect_command.py:80`).

### 5. Un test de garde, par import et non par texte

`tests/etl/test_source_kinds.py:75`

```python
        and getattr(module, "get_from_github_api", None)
        is github_api.get_from_github_api
```

Le test importe chaque module de `k_b.etl.sources` (`pkgutil.iter_modules`) et retient ceux qui
ont importé la fonction même qui appelle GitHub (`is` : identité de l'objet). L'ensemble de leurs
`FOLDER_PREFIX` doit valoir la constante plus `github_most_starred`. Une 4ᵉ source GitHub ajoutée
sans mettre la constante à jour fait échouer le test. Un module qui ne citerait le nom que dans un
commentaire n'est pas compté (c'était le défaut de la première version, qui cherchait le texte).

## Choix faits et options écartées

| Choix | Retenu | Écarté, et pourquoi |
|---|---|---|
| Canal de l'annonce | Journal (`logger.info`), règle 3 de `conventions.md` | `print` : mêle l'annonce au résultat, lignes non datées, absentes de `kb.log` |
| Niveau du jeton absent | `WARNING` | `ERROR` : rien n'a échoué |
| Noms annoncés | `source.name`, un par ligne de fin (Sabine, option (b)) | Nom de dossier (`github_releases`) : plus court, mais une conversion de plus et un nom absent de la fin |
| Construire l'annonce | Depuis la liste réelle des sources (relecture du plan, constat 5) | Une nouvelle fonction qui aurait recopié une 3ᵉ fois la règle « source à variable » |
| Sources « GitHub » | `github_releases`, `github_advisories` (quota principal) | Les trois : faux pour la recherche ; `startswith("github_")` : rien ne lie un nom à l'appel de l'API ; un attribut sur `SourceKind` : change le contrat des 9 sortes pour un message |
| Où ranger la constante | `collect_command.py` | `github_api.py` : le client ne peut pas importer ses appelants (import circulaire), il faudrait recopier leurs noms |
| Moment de l'annonce | Avant la lecture de l'état de collecte | Après : il faudrait toucher l'ETL (l'état est lu dans `collect_all_sources`) ; dit dans `specs-collecte.md` |

## Preuve

| Test ou sortie | Ce que ça démontre |
|---|---|
| `test_collect_announces_once_the_sources_it_runs_before_the_first_one` (`tests/test_cli.py:600`) | Une seule ligne `sources to collect: broken, working`, datée, avant `collection failed for source 'broken'` ; zotero, clipping, gh_archive (variable absente) non annoncés ; rien sur `stdout` |
| `test_collect_says_once_without_the_github_token_that_github_allows_60_requests` (`:632`, jeton absent puis vide) | Deux sortes GitHub, exactement une ligne `WARNING`, au format attendu |
| `test_collect_says_nothing_of_the_github_token_for_the_search_alone` (`:651`) | `github_most_starred` seul : pas d'avertissement |
| `test_collect_says_nothing_of_the_github_token_when_it_is_set` (`:672`) | Ni le nom ni la valeur du jeton dans `stdout`, `stderr`, `logs/kb.log` |
| `test_collect_only_without_a_github_source_says_nothing_of_the_github_token` (`:689`) | `KB_COLLECT_ONLY=zotero,clipping` (la collecte du Mac) : code 0, `sources to collect: zotero, clipping`, pas de quota |
| `test_the_github_core_quota_kinds_are_those_that_call_the_github_api_but_the_search` (`tests/etl/test_source_kinds.py:65`) | La constante suit les modules qui appellent vraiment l'API |
| `uv run pytest -q` → 1776 passed ; `ruff check`, `ruff format --check`, `mypy --strict` verts | Rien d'autre n'a cassé |

Les tests ont d'abord échoué pour la bonne raison (aucune annonce, constante absente), puis le code
les a fait passer.

## Ce que tu dois pouvoir défendre

1. **Pourquoi sur la sortie d'erreur et pas la sortie standard ?** La sortie standard est le
   résultat de la commande (le bilan par source) ; l'annonce est du déroulé, daté, gardé dans
   `logs/kb.log` (règle 3 de `conventions.md`). En conteneur, la sortie d'erreur est le journal.
2. **Le jeton peut-il fuir dans un journal ?** Non : le code ne lit que sa présence
   (`not environ.get(…)`), et le message cite le nom de la variable. Un test le vérifie sur les
   trois sorties (`tests/test_cli.py:672`).
3. **Pourquoi pas d'avertissement pour les dépôts les plus étoilés ?** Ils appellent la recherche,
   comptée à part par GitHub ; le chiffre de 60 par heure ne la concerne pas. Elle fait un seul
   appel par collecte.
4. **Que se passe-t-il si on ajoute une 4ᵉ source GitHub ?** Le test de garde échoue tant
   qu'elle n'est pas classée (quota principal ou recherche).
5. **Et si `collection_state.json` est illisible ?** L'annonce paraît, puis l'erreur, et la commande
   sort sans collecter : l'annonce dit ce qui *va* tourner, au lancement (écrit dans la spec).

## Zones non vérifiées

- **Le quota chiffré de la recherche** : la doc GitHub dit qu'il est distinct (`search` à côté de
  `core`), mais ses chiffres n'ont pas été confirmés à la source ; ils ne sont écrits nulle part.
- **Le test de garde ne voit que l'import de `get_from_github_api`** : un module qui appellerait
  l'API autrement (par `download` et `API_URL`), ou un module utilitaire sans `FOLDER_PREFIX`, lui
  échapperait ou le ferait échouer. Aucun n'existe aujourd'hui (tri de time-knight).
- **Pas d'exécution réelle** de `kb collect` contre GitHub : la sortie réelle est l'objet de #25.

## Ce qui reste

- La sortie réelle de `kb collect`, comme preuve du livrable E1 : #25.
- La mise en forme générale de la sortie CLI : idée de Sabine, à voir après #25.

Hors de cette note : les autres commits et fichiers listés au lancement de la note appartiennent à
des PR déjà fusionnées sur `main` (#250 à #256) ; cette branche n'en a que trois (76c1d03, cd04be1,
335cdc9).

## Sources

| Source | URL | Consultée le |
|---|---|---|
| GitHub Docs, « Rate limits for the REST API » (60 sans jeton, 5 000 avec) | https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api?apiVersion=2026-03-10 | 2026-10-19 |
| GitHub Docs, « REST API endpoints for rate limits » (objet `search` distinct de `core`) | https://docs.github.com/en/rest/rate-limit/rate-limit | 2026-10-19 |
