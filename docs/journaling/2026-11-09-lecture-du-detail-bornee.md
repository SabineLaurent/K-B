# Borner la lecture du détail dans la base

- **Date** : 2026-11-09
- **Branche** : `fix/bound-detail-reading`
- **Issue** : #430
- **Fichiers principaux** : `src/k_b/database/reading.py`, `src/k_b/data_api/routers/item_router.py`,
  `tests/data_api/test_item_router.py`, `tests/database/test_reading.py`
- **Série** : suite de `2026-11-06-delai-et-bornes-du-detail-de-l-api-de-donnees.md` (#331), qui a posé les bornes
  de ce que la route sert.

## Le pourquoi

`GET /items/{item_id}` sert le détail d'un item. Depuis #331, la route ne sert que 100 surlignages d'une entrée
Zotero et 125 000 caractères du texte d'un clip, et dit la coupe par `highlights_truncated` et `body_truncated`.
Mais elle coupait **après** avoir tout lu : la base lui rendait tous les surlignages, et le texte entier d'un clip,
jusqu'à 1 000 000 de caractères, pour n'en servir que 125 000. La lecture n'était bornée qu'en temps (5 s par
instruction), pas en taille.

C'est un préalable des fiches de lecture : la lecture d'un clip par l'API de données ne doit pas dépasser le délai
de son client. #430 déplace la borne dans la requête : la base ne lit plus que ce que la route peut servir, plus
un.

## Le comment

### 1. Deux requêtes bornées par un paramètre

```sql
WHERE item_id = ?
ORDER BY highlighted_at, highlight_id
LIMIT ?
```
`src/k_b/database/reading.py:100-102`

```sql
SELECT published_at, substr(body, 1, ?) AS body
```
`src/k_b/database/reading.py:149`

`LIMIT` arrête la lecture des surlignages après n lignes. Le `ORDER BY` passe avant le `LIMIT` : ce sont bien les
n premiers par date de création qui sont lus, les mêmes que la route servait déjà. `substr(body, 1, n)` rend les n
premiers caractères du texte. Les deux bornes sont des **paramètres liés** (`?`), jamais écrites dans le texte SQL :
c'est la règle des requêtes paramétrées (`code.md`), et `LIMIT` comme `substr` existent en SQLite et en PostgreSQL
(règle 1 de `poc.md`).

### 2. `DetailBounds`, passé par la route

```python
class DetailBounds(NamedTuple):
    """The most highlights of a Zotero entry and characters of the text of a clip a detail reads;
    the rest is never read."""

    highlights: int
    body_length: int
```
`src/k_b/database/reading.py:268-273`

Les bornes vivent dans la route (`MAX_SERVED_HIGHLIGHTS`, `MAX_SERVED_TEXT_LENGTH`, `item_router.py:48-49`).
`database/` ne doit pas importer `data_api/`, car les dépendances vont dans un seul sens (`code.md`, SoC). La route
les passe donc en paramètre, sous la forme d'un tuple nommé qui porte les deux valeurs ensemble.

### 3. Un de plus que ce qui est servi

```python
    # One more than served: the cut is seen without reading the rest.
    detail = read_item_detail(
        connection,
        item_id,
        DetailBounds(MAX_SERVED_HIGHLIGHTS + 1, MAX_SERVED_TEXT_LENGTH + 1),
    )
```
`src/k_b/data_api/routers/item_router.py:132-137`

La route demande 101 surlignages et 125 001 caractères. Avec 100 et 125 000, elle ne saurait pas s'il en manque.
Une entrée de 100 surlignages et une entrée de 5 000 rendraient la même liste. En lisant un de plus, la route voit
la coupe sans lire la suite. Les deux calculs des drapeaux de #331 ne changent pas
(`item_router.py:156` et `:162`) : `len(highlights) < len(details.highlights)` est vrai dès que 101 ont été lus et
100 servis, et `len(details.body) > MAX_SERVED_TEXT_LENGTH` est vrai dès que 125 001 caractères ont été lus. Le
contrat de l'API ne bouge pas, il n'y a donc pas de nouvelle version.

### 4. Une signature pour les sept lecteurs

```python
# One signature for every kind; only a Zotero entry and a clip have something to bound.
READ_DETAILS_BY_KIND: dict[
```
`src/k_b/database/reading.py:535-536`, appelé par `READ_DETAILS_BY_KIND[listed.kind](connection, item_id, bounds)`
(`reading.py:445`)

`read_item_detail` choisit le lecteur de la sorte de l'item dans une table. Pour garder cette table, les sept
lecteurs prennent tous `bounds`. Les cinq qui n'ont rien à borner (paper, vulnerability, release, advisory,
newsletter_article) le reçoivent sans s'en servir.

### 5. Le garde-fou des bornes

```python
    # A negative LIMIT reads every row in SQLite.
    check_within_bounds("max_highlights", max_highlights, 0, MAX_INT64)
```
`src/k_b/database/reading.py:414-415`, et `body_length` à `reading.py:523`

Une borne fausse ne se comporterait pas de la même façon sur les deux moteurs. En SQLite, un `LIMIT` négatif veut
dire « aucune limite », alors que PostgreSQL le refuse. De même, seul PostgreSQL refuse une longueur négative de
`substr`. Les deux bornes sont donc vérifiées comme l'est déjà la `limit` de `read_items` (`reading.py:332-335`) :
de 0 à `MAX_INT64`, la plus grande valeur que sqlite3 sait lier. Au-delà, sqlite3 lève une `OverflowError`. Le
message nomme la borne franchie, jamais la valeur reçue.

## Choix faits et options écartées

| Choix | Retenu parce que | Écarté |
|---|---|---|
| Le +1 est ajouté dans la route | La base lit « au plus n », un contrat simple ; c'est la route qui a besoin de voir la coupe | Le +1 dans `database/` : la base connaîtrait la logique de coupe de la route |
| Les bornes sont passées en paramètre | La borne n'est écrite qu'une fois, ce que l'issue demande | Une valeur par défaut dans `database/` : la borne serait écrite une seconde fois |
| Une signature pour les sept lecteurs | La table d'aiguillage reste entière | Un cas à part pour Zotero et le clip, hors de la table (ou `functools.partial`) : il casse la table |
| Le garde-fou va de 0 à `MAX_INT64` | Il refuse ce que les deux moteurs liraient différemment, comme `read_items` | Aucun garde-fou : une borne fausse désactiverait la coupe en SQLite sans erreur |

Le plan a été validé par Sabine le 09/11. Le garde-fou vient du tri de la revue de code (constat 3), tranché par
time-knight sur délégation de Sabine du 15/10.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| Avant le code, `test_the_detail_reads_one_more_than_it_serves_and_says_the_cut[sqlite]` échoue : `assert 102 == 101` | La base lisait les 102 surlignages ; le test vise bien le comportement |
| `test_the_detail_reads_one_more_than_it_serves_and_says_the_cut` (`tests/data_api/test_item_router.py:382`), vert | Sur une base de 102 surlignages et un clip de 125 002 « é », la route lit 101 surlignages (le dernier est `BOUND097`) et 125 001 caractères ; elle en sert 100 et 125 000, et les deux drapeaux sont vrais |
| Mutation : `SELECT_CLIP` sans `substr`, le test échoue sur le texte lu | Le test attrape l'oubli de la borne du texte |
| Le texte du clip est fait de « é », deux octets chacun en UTF-8 | `substr` compte des caractères : s'il comptait des octets, le texte lu serait deux fois plus court |
| Avant le code, `test_a_bound_of_the_detail_out_of_range_is_refused` échoue (`DID NOT RAISE`, `OverflowError`) ; vert après | Une borne négative ou au-delà de 64 bits est refusée par un `ValueError` nommé |
| `uv run pytest -m "not postgresql"` : 4 096 tests passent ; `ruff check`, `ruff format --check`, `mypy --strict` verts | Rien d'autre n'a cassé |
| `/security-review` (sous-agent neuf, lecture seule) : aucun constat ; second `/code-review` sur le delta : aucun | Les revues après correction |

## Ce que tu dois pouvoir défendre

- **Pourquoi lire 101 et pas 100 ?** Pour savoir qu'il en manque sans lire le reste. Avec 100 lus, une entrée de
  100 et une de 5 000 rendent la même liste, et `highlights_truncated` serait faux à tort (`item_router.py:132`).
- **Que se passe-t-il pour une entrée de 101 surlignages de 20 000 caractères ?** La base en lit au plus 101, soit
  2 020 000 caractères de texte et de commentaire. La route en sert 125 000 au plus. `LIMIT` borne le nombre, pas la
  taille : la borne de taille reste dans la route, comme l'issue le prévoit.
- **Où est l'injection SQL ?** Nulle part : les deux bornes sont des paramètres liés, et elles viennent de
  constantes du code, pas du client (`reading.py:102`, `:149`).
- **`substr` coupe-t-il au milieu d'un caractère ?** Non. Il compte des caractères en SQLite et en PostgreSQL,
  parce que la base PostgreSQL est en UTF8 (`creation.py:22` ; `kb create-db` refuse une autre base). Il peut couper
  un graphème (un emoji composé, un accent combiné), comme la coupe de la route le faisait déjà
  (`docs/specs-api.md`, « Bornes du détail »).
- **Pourquoi cinq lecteurs reçoivent-ils un paramètre qu'ils n'utilisent pas ?** Pour garder une seule table de
  lecteurs, avec une signature. Un cas à part pour deux sortes aurait cassé cette table : c'est le choix du plan.

## Zones non vérifiées

- **PostgreSQL n'a pas été lancé en local.** Le serveur de test refuse la connexion sans mot de passe
  (`fe_sendauth: no password supplied`), et aucun secret n'a été lu ni demandé. Le second moteur est prouvé par le job
  `tests-postgresql` de la CI.
- **En SQLite, la mémoire n'a pas été mesurée.** Le moteur tourne dans le processus de l'API : la borne vaut pour ce
  que Python reçoit, mais ce que SQLite charge pour calculer `substr` n'est pas mesuré. En PostgreSQL, c'est le
  serveur qui coupe le texte.
- **Les bornes que psycopg lie en PostgreSQL** (`int4` pour 125 001) n'ont pas été lues dans sa documentation : seul
  le job de la CI le dira.

## Ce qui reste

- Le temps du détail reste borné par instruction, comme avant (5 s, #418 ; `MEMORY.md`, « Problèmes connus »).
- Constats 4 à 8 de la revue, écartés par time-knight (raisons dans la PR) : le +1 et le calcul des drapeaux se
  tiennent sans lien écrit, ce que le test protège ; les cinq paramètres non utilisés ; `read_clip_detail` hors de
  `fetch_row` ; la fixture qui reconstruit sa base ; la constante `BOUNDS` des tests écrite dans quatre modules.
