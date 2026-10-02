# La collecte des dépôts les plus étoilés : une photo du top 100 à chaque collecte

Suite de [la collecte des alertes GitHub](2026-10-02-collecte-alertes-github.md) et de
[celle des releases](2026-10-02-collecte-releases-github.md), dont elle reprend la connexion.

- **Date** : 2026-10-02
- **Branche** : `feat/github-most-starred` (commits `711819c` pour le code et le registre,
  `9a3d0b2` pour les specs ; l'entrée d'ADR et cette note entrent avec la PR)
- **Issue** : #11, **partie dépôts les plus étoilés** ; la partie alertes est dans la PR #45
- **Fichiers principaux** : `src/k_b/github_most_starred_source.py` (collecte),
  `src/k_b/github_most_starred.py` (lecture), `src/k_b/github_dates.py` (dates GitHub, commun),
  et leurs tests ; la fixture `tests/fixtures/github_most_starred_extract.json`.
- **Autres fichiers** : `src/k_b/collect.py` (déclare la source), `src/k_b/github_releases.py` et
  `src/k_b/github_advisories.py` (passent au contrôle de dates commun), `docs/specs-collecte.md`,
  `docs/registre-traitements.md` (login du propriétaire).

## Le pourquoi

La veille doit dire quels projets dominent GitHub, et surtout lesquels **viennent d'y entrer**.
Sabine a choisi le classement général, sans filtre par thème : mesuré le 2026-10-02, 36 des 100
dépôts les plus étoilés touchent à l'IA et 13 ont moins d'un an. Un nouvel entrant dans ce
classement est donc un vrai signal. À plus de 116 000 étoiles pour le 100e, ce classement ne
s'achète pas.

Cette source dit **ce qui s'est installé au sommet**. Ce qui **monte** en ce moment relève de #16,
avec GH Archive sur BigQuery, puisque l'API ne sait trier que par total d'étoiles.

## Le comment

### 1. La requête : « les 100 dépôts les plus étoilés »

```python
        query = {"q": SEARCH_QUERY, "sort": "stars", "order": "desc", "per_page": RANKING_SIZE}
        raw_response = get_from_github_api(f"search/repositories?{urlencode(query)}")
        read_most_starred(raw_response)
        return raw_response
```
(`src/k_b/github_most_starred_source.py:25`)

L'API de recherche exige un critère `q` et refuse une recherche vide. `SEARCH_QUERY` vaut
`stars:>10000`, un critère qui ne retire rien du top 100 : le 100e a 116 161 étoiles. Le tri
`stars` décroissant et `per_page=100`, le maximum d'une page, donnent le classement en **une
seule requête**.

`read_most_starred(raw_response)` ne sert ici qu'à **valider** la réponse avant de l'écrire. Son
résultat n'est pas gardé : ce qui est écrit, c'est la réponse d'origine, octet pour octet.

### 2. Une photo à chaque collecte

Les releases et les alertes n'écrivent rien quand il n'y a rien de neuf. Ici, `fetch` renvoie
**toujours** la réponse, jamais `None`, et `last_collected_at` n'est pas utilisé. Un classement
change toujours, puisque les étoiles bougent chaque jour. Chaque collecte écrit donc une photo
datée du top 100, dans `raw/automation/github_most_starred/`. En comparant deux photos, on obtient
l'information de veille : qui est entré, qui est sorti, qui a le plus monté. Cette comparaison se
fera à la lecture. C'est une exception à la règle « une source qui n'a rien de neuf n'écrit
rien », décidée par Sabine et consignée dans l'ADR.

### 3. Refuser un classement incomplet

```python
    if response.get("incomplete_results") is not False:
        raise ValueError("incomplete search results, refused")
```
(`src/k_b/github_most_starred.py:33`)

Quand la recherche de GitHub prend trop de temps, elle s'arrête et renvoie ce qu'elle a trouvé,
avec `incomplete_results: true`. Un classement partiel ferait croire, à la comparaison, que des
dépôts sont **sortis** du top. On refuse donc la réponse : `fetch` lève une erreur, rien n'est
écrit, la date de dernière collecte n'avance pas, et la collecte suivante réessaiera. Le test
`is not False` refuse aussi un champ absent ou mal typé : on échoue fermé.

### 4. La lecture : des champs contrôlés

`read_most_starred` produit des `StarredRepository` : rang, `owner/repo`, URL, description,
étoiles, topics, date de création. Deux contrôles méritent d'être expliqués :

```python
    is_owner_slash_name = isinstance(full_name, str) and bool(OWNER_SLASH_NAME.fullmatch(full_name))
    if not is_owner_slash_name or ".." in full_name:
```
(`src/k_b/github_most_starred.py:42`)

Le nom doit avoir la forme `owner/repo`, sans `..`. Le test l'a montré : `../escape` passait
l'expression régulière seule, puisque `.` est un caractère permis. Ce nom n'écrit aucun chemin
aujourd'hui, mais un futur usage (un nom de fichier, une URL construite) serait à l'abri.

```python
    if not isinstance(stars, int) or isinstance(stars, bool):
```
(`src/k_b/github_most_starred.py:53`)

En Python, `True` est un `int` (`bool` est une sous-classe d'`int`). Sans le second test,
`"stargazers_count": true` passerait pour 1 étoile.

Le **login du propriétaire** reste dans `owner/repo`. Quand le propriétaire est une personne,
c'est une donnée personnelle, mais elle est l'identifiant même du dépôt : sans elle, l'item ne
désigne plus rien. Le registre des traitements la déclare désormais. La fixture ne contient que
des dépôts d'**organisations**, pour ne pas mettre de login de personne dans les tests.

### 5. Les dates GitHub, contrôlées à un seul endroit

```python
    if parsed_date.tzinfo is None:
        raise ValueError(f"{label} has no time zone")
```
(`src/k_b/github_dates.py:17`)

Les releases (#10), les alertes et maintenant les étoilés contrôlaient chacun les dates GitHub
avec le même code. À la **troisième** occurrence, `code.md` demande de factoriser :
`parse_github_date` vit dans `github_dates.py`, et les trois lecteurs l'appellent avec une
étiquette (`"release 0: published_at"`, `"repository 1: created_at"`…) qui garde des messages
d'erreur précis. Les tests des releases et des alertes, inchangés et verts, montrent que leur
comportement n'a pas bougé.

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Périmètre | **Tout GitHub, sans topic** (choix de Sabine) | Filtre par topic : étiquettes libres, sans taxonomie, et plus de 14 000 nouveaux dépôts `llm` par mois. Dépôts récents les plus étoilés : plus exposés aux étoiles achetées. Couper la source au profit de #16 |
| Taille | **100** : une requête, et assez de profondeur pour voir un dépôt entrer par le bas (choix de Sabine) | 30 : on ne verrait les nouveaux qu'une fois installés. 50 : compromis, jugé moins utile |
| Écriture | **Une photo à chaque collecte** (exception consignée dans l'ADR) | N'écrire que si la liste des 100 change : on perdrait l'évolution des étoiles |
| Réponse incomplète | **Refusée** : une erreur, rien d'écrit, nouvel essai à la collecte suivante | L'écrire : de fausses sorties du top à la comparaison |
| Login du propriétaire | **Gardé** dans `owner/repo`, déclaré au registre | Le retirer : l'item ne désignerait plus le dépôt |
| Dates | **`github_dates.py` commun** (règle de factorisation à la 3e occurrence, `code.md`) | Une troisième copie |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_request_asks_for_the_100_most_starred_repositories` | La requête exacte : `q`, `sort`, `order`, `per_page` |
| `test_every_collection_writes_a_snapshot_of_the_ranking` | Deux collectes écrivent deux photos, même sans changement |
| `test_an_incomplete_ranking_is_refused`, `test_an_incomplete_ranking_is_not_written` | Une réponse incomplète lève une erreur, donc rien n'est écrit |
| `test_a_recorded_response_gives_the_repositories_by_rank` | Une vraie réponse donne rang, nom, URL, étoiles, topics, date UTC |
| `test_an_invalid_repository_is_refused_with_its_rank` (6 cas) | `../escape`, URL étrangère, étoiles non entières ou booléennes, topics mal typés, date sans fuseau : refusés |
| `test_github_dates.py` (5 cas) | Le contrôle commun accepte une date UTC et refuse tout le reste |
| `uv run pytest` : 111 tests verts | Les releases et les alertes passent toujours après la factorisation |
| Vrai `kb collect` : 8 sources `ok`, photo de 100 dépôts lue sans erreur (1er à 551 156 étoiles, 100e à 116 163) | Fonctionne sur la vraie API |

## Ce que tu dois pouvoir défendre

1. **Pourquoi écrire à chaque collecte, alors que la règle dit « rien de neuf, rien d'écrit » ?**
   Parce qu'un classement change toujours, et que l'information de veille vient de la
   comparaison de deux photos. C'est une exception décidée et tracée dans l'ADR.
2. **Pourquoi `stars:>10000` ?** Parce que l'API exige un critère de recherche. Celui-ci ne
   retire aucun dépôt du top 100 (`github_most_starred_source.py:9`).
3. **Que se passe-t-il si GitHub coupe la recherche ?** La réponse porte
   `incomplete_results: true`, elle est refusée, et la collecte suivante réessaie
   (`github_most_starred.py:33`). Pas de fausse sortie du top.
4. **Où sont les données personnelles ?** Le login du propriétaire, quand c'est une personne,
   dans `owner/repo`. Il est gardé parce qu'il identifie le dépôt, et il est déclaré au registre.
5. **Pourquoi avoir retouché les releases et les alertes dans cette PR ?** Parce que les étoilés
   apportaient la troisième copie du contrôle des dates. La règle DRY du dépôt la fait
   factoriser à ce moment-là, et leurs tests prouvent qu'elles fonctionnent comme avant.

## Zones non vérifiées

- **Le comportement de `incomplete_results`** vient de la documentation et de l'usage connu de
  l'API. Je n'ai jamais observé de réponse incomplète réelle : le cas n'est testé qu'en
  simulation.
- **La stabilité du classement d'une semaine à l'autre** n'est pas mesurée : une seule photo
  existe. Le nombre d'entrées par mois annoncé (« environ un ») est une estimation tirée des 13
  dépôts de moins d'un an, pas une mesure.
- **Le seuil `stars:>10000`** suppose que le 100e restera au-dessus de 10 000 étoiles. Il a
  aujourd'hui plus de dix fois ce seuil, mais rien ne le vérifie automatiquement.

## Ce qui reste

- **La comparaison de deux photos** (entrées, sorties, montées) : à la lecture, avec l'item
  commun et la fusion.
- **Ce qui monte en ce moment** : #16, GH Archive sur BigQuery.
- **La purge des photos** au bout de 2 ans : avec celle des autres bruts (#20).
