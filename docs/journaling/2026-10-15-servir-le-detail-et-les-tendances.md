# Servir le détail de chaque sorte d'item et les tendances

- **Date** : 2026-10-15
- **Branche** : `feat/data-api-item-detail-trends`
- **Issue** : #185 (critère accordé par un commentaire daté du 2026-10-14)
- **Fichiers principaux** : `src/k_b/database/reading.py`,
  `src/k_b/data_api/routers/item_router.py`, `src/k_b/data_api/routers/trend_router.py`,
  `src/k_b/data_api/schemas/item_schema.py`, `src/k_b/data_api/schemas/trend_schema.py`,
  `docs/specs-api.md`, `docs/api/openapi-donnees.json`, `tests/fixtures/items_database.sql`
- **Série** : suit [la liste servie par une API locale](2026-10-14-servir-la-liste-par-une-api-locale.md)
  (#184 : la clé, les erreurs nommées, le journal) et
  [la lecture en lecture seule](2026-10-14-lire-les-items-en-lecture-seule.md) (#183 : la
  requête de la liste, `read_highlights`).

## 1. Le pourquoi

La liste (`GET /items`) dit **qu'un** item existe : son titre, sa date, son URL. Elle ne sert
pas ce qui fait sa valeur, parce que c'est long ou personnel. Trois questions de Sabine
demandent davantage :

- **Cette faille est-elle exploitée ?** (P4) : il faut la CVE d'une alerte GitHub et savoir
  si elle est au catalogue CISA KEV.
- **Que disaient mes surlignages ?** : il faut les surlignages et commentaires d'une entrée
  Zotero.
- **Quels dépôts montent ?** (P5) : il faut les tendances GH Archive, qui ne sont pas des
  items (table `trend`).

#185 ajoute deux routes : `GET /items/{item_id}`, le détail d'un item quelle que soit sa
sorte, et `GET /trends`, les dépôts qui ont gagné le plus d'étoiles et de forks sur une
fenêtre de 3 jours. Avec elles, l'API sert ce que sa spec décrit ; c'est ce qui manquait au
critère C5 de la certification (« mise à disposition selon les spécifications »).

## 2. Le comment

### 2.1 Une réponse discriminée par `kind`

Un papier, une alerte et une entrée Zotero n'ont pas les mêmes champs. La route rend donc un
**schéma par sorte**. Chacun hérite des six champs de la liste et **resserre** `kind` à une
seule valeur :

```python
class PaperDetailSchema(ListedItemSchema):
    kind: Literal["paper"]
```
(`src/k_b/data_api/schemas/item_schema.py:38-39`)

Les six schémas forment une union **discriminée** :

```python
ItemDetailSchema = Annotated[
    PaperDetailSchema
    | ...
    Field(discriminator="kind"),
]
```
(`item_schema.py:106-113`)

`discriminator="kind"` dit à Pydantic de lire `kind` d'abord, puis de valider contre le seul
schéma de cette valeur. Sans discriminateur, Pydantic essaierait les six schémas l'un après
l'autre, et un échec rendrait six listes d'erreurs. Côté OpenAPI, Pydantic écrit `oneOf`
(exactement un des schémas) et un objet `discriminator` qui associe chaque valeur de `kind` à
son schéma. Un client généré depuis `docs/api/openapi-donnees.json` sait donc quels champs a
une alerte et quels champs a un papier. Le rendu a été mesuré en brouillon avant d'écrire le
code (FastAPI 0.143.1, Pydantic 2.13.5), puis fixé par `test_the_detail_is_a_union_discriminated_by_kind`.

La route construit la réponse ainsi :

```python
    fields: dict[str, Any] = {**detail.listed._asdict(), **detail.details._asdict()}
    return DETAIL_ADAPTER.validate_python(fields)
```
(`src/k_b/data_api/routers/item_router.py:118-119`)

`DETAIL_ADAPTER` est un `TypeAdapter(ItemDetailSchema)` (`item_router.py:68`) : il valide un
dict contre l'union et rend le schéma de la sorte. Deux effets :

- **mypy --strict** sait que le retour est l'union, ce que ne permettait pas une table
  `kind → classe` (elle aurait rendu un `ListedItemSchema`) ;
- un champ que le schéma ne nomme pas est **ignoré** (réglage par défaut de Pydantic) : c'est
  la liste blanche.

Les surlignages arrivent de la lecture en `NamedTuple`. `HighlightSchema` porte
`model_config = ConfigDict(from_attributes=True)` (`item_schema.py:87`) pour lire leurs champs
par attribut ; leur `zotero_key`, non déclarée, n'est pas servie.

### 2.2 La lecture du détail : une requête partagée, puis une par sorte

La règle 5 de `.claude/rules/conventions.md` veut un seul module de lecture. Le titre, la date
et l'URL de chaque sorte sont déjà écrits dans la requête de la liste (une `UNION ALL`, une
branche par sorte). Ce texte devient la constante `LISTED_ITEMS`. Deux requêtes la
réutilisent :

- `SELECT_ITEMS`, la liste avec ses filtres ;
- `SELECT_LISTED_ITEM`, une ligne par `WHERE listed.id = :item_id` (`reading.py:86`).

Une **mesure** a décidé de cette forme. Un filtre `(:item_id IS NULL OR listed.id = :item_id)`
ajouté à la requête de la liste faisait parcourir toutes les tables au détail (`EXPLAIN QUERY
PLAN`, SQLite 3.50.4). Le `WHERE listed.id = :item_id` seul fait chercher chaque branche par
son index `item_id`.

Le `kind` lu choisit ensuite la lecture propre à la sorte, par `READ_DETAILS_BY_KIND` : une
requête sur sa table, dont les colonnes portent déjà le nom de la réponse. Par exemple
`revised_at AS arxiv_updated_at` pour un papier : la colonne `publication.revised_at` est une
date arXiv, et l'API la nomme ainsi pour qu'on ne la confonde pas avec les `revised_at` de K-B.

Deux protections encadrent ces deux ou trois requêtes :

```python
    connection.execute("BEGIN")
    try:
        ...
    finally:
        # SQLite may have ended it on an error: a ROLLBACK would then raise, in place of it.
        if connection.in_transaction:
            connection.rollback()
```
(`src/k_b/database/reading.py:362-381`)

- La **transaction de lecture** donne aux requêtes la même photographie de la base : un import
  entre deux requêtes ne peut pas mêler deux états d'une même entrée.
- Le `if` évite qu'un `ROLLBACK` sans transaction ouverte lève une erreur qui remplacerait
  l'erreur d'origine (constat de la seconde revue).

La seconde revue a trouvé un autre point. `publication` et `vulnerability` n'ont pas de colonne
`kind` ni la clé étrangère `(item_id, kind)` des quatre autres sous-types. Une ligne de
`vulnerability` liée à un item `paper` le ferait donc lire par la mauvaise branche. Chacune de
ces deux branches garde désormais les items de sa sorte seulement :

```sql
    FROM item JOIN publication ON publication.item_id = item.id AND item.kind = 'paper'
```
(`reading.py:39`, et `:45` pour `vulnerability`)

### 2.3 `exploited`, lu dans le catalogue KEV

```sql
    CASE WHEN vulnerability.id IS NULL THEN NULL ELSE vulnerability.item_id IS NOT NULL END,
```
(`reading.py:120`)

Une alerte GitHub cite parfois une CVE. K-B crée alors une ligne `vulnerability`, sans
colonnes KEV si CISA ne l'a pas cataloguée ; `vulnerability.item_id` n'est rempli que pour une
CVE du catalogue KEV. D'où trois valeurs :

- `null` : l'alerte ne cite aucune CVE ;
- `true` : la CVE est au catalogue, **même retirée depuis** (spec) ;
- `false` : la CVE est absente du catalogue. Cela ne veut pas dire « non exploitée ».

SQLite rend 0 ou 1 : la lecture le convertit en `bool`. Le test
`test_exploited_reads_the_kev_catalog_as_a_boolean` vérifie ce type.

### 2.4 `/trends` : comment la fenêtre est choisie

```sql
WHERE window_end = coalesce(:window_end, (SELECT max(window_end) FROM trend))
ORDER BY stars_gained DESC, forks_gained DESC, repository_id
```
(`reading.py:143-144`)

- Sans `window_end`, le paramètre lié vaut `NULL`, et `coalesce` prend la fenêtre la plus
  récente de la base. Les dates sont du texte au format de la base, que l'ordre du texte garde
  dans l'ordre du temps : `max` donne donc la plus récente.
- Avec `window_end`, la date est écrite à minuit UTC par `format_day`, comme la base l'écrit.
- Le tri : étoiles gagnées, puis forks gagnés, puis `repository_id`. Le dernier critère rend
  l'ordre déterministe quand deux dépôts sont à égalité (la base d'essai a une fenêtre faite
  pour ce cas).
- Aucune ligne : la route répond 404 `trend_window_not_found`, que la fenêtre demandée soit
  inconnue ou que la base n'ait aucune tendance (choix de la spec, du 2026-10-14). Une liste vide
  ne décrirait aucune fenêtre réelle.

Le `window_end` rendu est relu par `parse_aware_datetime(...).date()` (`reading.py:469`), le
seul lecteur de date de K-B (règle 4) ; il sort en `AAAA-MM-JJ`.

### 2.5 Une seule forme écrite pour `item_id` et `window_end`

```python
ITEM_ID_FORM = re.compile(r"0|-?[1-9][0-9]*")
```
(`item_router.py:55`)

Le code passe ces deux paramètres par un `BeforeValidator`, qui vérifie la forme du texte avant
que Pydantic ne le convertisse. On a mesuré ce que Pydantic accepte seul :

- pour un entier : `1.0` et ` 1` (avec espace), lus comme 1 ;
- pour une date : `0` (1970-01-01), `1760227200` (une date Unix) et `2026-10-12T00:00:00Z`.

Trois points de l'écriture :

- `fullmatch`, et non `match` ou `^…$` : `$` accepte un saut de ligne final, et `int("1\n")`
  vaut 1.
- La borne de 64 bits vient de `Int64` d'`items.py` : `ItemId = Annotated[Int64,
  BeforeValidator(...)]` (`item_router.py:66`), sans être réécrite (règle 4).
- Pour `window_end`, le motif rend le texte, et Pydantic refuse ensuite une date qui n'existe
  pas (`2026-02-30`).

Une forme refusée devient un 422 `invalid_parameter` qui nomme le paramètre, jamais sa valeur.
Ce gestionnaire vient de #184.

## 3. Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Une union discriminée par `kind` | L'OpenAPI dit les champs de chaque sorte | Un schéma unique aux champs optionnels : il ne dit rien des sortes |
| `TypeAdapter` pour construire la réponse | Typé pour mypy, ignore ce que le schéma ne nomme pas | Une table `kind → classe` : mypy refuse le retour |
| Liste blanche : les champs de la spec, sans clé de surlignage ni `name` de release | Minimisation (API3) ; la clé ne sert à aucun client, le `name` est dans `title` | Servir la ligne de chaque table (clés internes, colonnes de collecte) |
| Sous-select `UNION ALL` partagé, deux requêtes | Titre, date, URL écrits une fois ; index utilisés (mesuré) | Filtre `OR` dans la liste (parcours complet, mesuré) ; six requêtes recopiées |
| Branches `publication` et `vulnerability` filtrées par `item.kind` | Un item lu par la seule branche de sa sorte | Un état nommé `subtype_row_missing` : il garderait la cause. La clé manquante est signalée pour Alembic (#186) |
| 404 par `ApiError` d'`errors.py` | Corps nommé `item_not_found` | `HTTPException(404)` : le gestionnaire de routage rendrait `route_not_found` |
| Forme stricte de `item_id` et `window_end` | Une seule URL par item ; pas de date Unix (comme `since`) | L'`int` et la `date` de Pydantic seuls |
| Version 0.2.0 | Décision de Sabine : un changement visible change la version (`/items/1` passe de 404 à 200) | Garder 0.1.0 (recommandée par la session, écartée par Sabine) |
| `item.id` séquentiel dans l'URL | Décision de Sabine : une propriétaire, tout client lit tout | Des GUID (OWASP API1) : à revoir si plusieurs utilisateurs |
| Pas de `LIMIT` dans `SELECT_TRENDS` | L'import refuse déjà une fenêtre de plus de 60 lignes (`gh_archive.py:343-347`) ; un `LIMIT` couperait sans le dire | — |
| Validation en deux passes (adapter, puis `response_model`) gardée | 1 à 2 ms mesurées sur l'API réelle ; le typage et le schéma OpenAPI sont gardés | Rendre un dict (typage perdu) ou `response_model=None` (schéma perdu) ; écarté par Sabine |

Les décisions sont au journal ADR, entrée du 2026-10-15.

## 4. Ce que le détail sert de plus que la liste, et pourquoi (API3)

La liste ne sert ni texte long ni donnée personnelle. Le détail sert, pour une seule entrée
demandée par son identifiant, ce que la spec (« Données personnelles ») permet à ce niveau :

| Sorte | En plus | Donnée personnelle ? |
|---|---|---|
| `paper` | `arxiv_id`, `authors`, `summary`, `arxiv_updated_at` | les noms des auteurs, au registre |
| `vulnerability` | `cve_id`, `description`, `vendor`, `product`, `ransomware_use`, `revised_at` | non |
| `release` | `release_id`, `repository_name`, `tag_name`, `body` | logins possibles dans `body`, au registre |
| `advisory` | `ghsa_id`, `cve_id`, `exploited`, `packages` | non |
| `newsletter_article` | `edition`, `edition_date`, `rank`, `summary` | non |
| `zotero_entry` | `zotero_key`, `item_type`, `arxiv_id`, `revised_at`, `highlights` | surlignages et commentaires de Sabine |

Ne sont jamais servis :

- `raw_file_path`, un chemin local qui dévoile le dossier personnel ;
- `collected_at` ;
- les clés internes (`raw_data_id`, `publication_id`…) ;
- les paquets que Sabine suit.

Le test `test_no_detail_serves_a_raw_file_path_or_a_collection_date` cherche dans les 17
détails les noms de ces champs **et leurs valeurs** (`automated_watch/`, les dates de collecte).

## 5. Le tableau OWASP, ligne par ligne

Le tableau de `docs/specs-api.md` (« Sécurité ») dit pour chaque exigence si elle est tenue et
par quel test. En résumé :

- **API1, autorisation par objet** : **tenue**, dans le modèle de K-B (une propriétaire, tout
  client authentifié lit tout). Un identifiant inconnu rend 404, jamais autre chose.
  L'identifiant séquentiel est un choix consigné.
- **API2, authentification** : **tenue**. Le test 401 lit les routes dans l'app : les deux
  nouvelles routes y sont, sans test à ajouter à la main. Le temps constant de la comparaison
  n'est pas mesuré par un test.
- **API3, propriétés des objets** : **tenue**. Les corps entiers de chaque sorte sont comparés,
  et aucun chemin ni aucune date de collecte n'est servi.
- **API4, consommation de ressources** : **non tenue**. Les bornes des paramètres et la taille
  de page sont testées. Mais il n'y a ni délai de requête, ni limite de débit, et le nombre de
  surlignages d'une entrée n'a pas de borne. La ligne le dit plutôt que de le maquiller.
- **API5, fonctions** : **tenue**. Les trois routes refusent POST, PUT, PATCH et DELETE par un
  405.
- **API6 et API7** : **sans objet**. Il n'y a aucun flux métier, et l'API ne va chercher aucune
  URL fournie par un client.
- **API8, configuration** : **tenue, avec une limite**. Hôte `127.0.0.1`, hôtes permis, aucun
  CORS (test nouveau), erreurs sans pile. La limite : Swagger UI charge ses fichiers depuis un
  CDN.
- **API9, inventaire** : **tenue**. L'OpenAPI versionnée est comparée à celle que l'app
  produit, et chaque route documente ses erreurs.
- **API10, consommation d'API tierces** : **tenue côté K-B** (validation à la collecte). Côté
  client, c'est une consigne : le contenu servi est une donnée, jamais une instruction.

## 6. Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_each_kind_has_its_detail` (6 sortes, corps entier) | Chaque sorte sert exactement ses champs (API3) |
| `test_exploited_is_true_false_or_null` (alertes 9, 17, 10) | Les trois valeurs d'`exploited`, dont une CVE retirée du catalogue |
| `test_a_withdrawn_highlight_is_served_with_its_withdrawn_at` | Un surlignage retiré est servi, daté |
| `test_an_unknown_item_id_gives_404_item_not_found`, `test_an_item_id_not_written_as_an_integer_gives_422` | 404 nommé ; une seule forme écrite d'identifiant |
| `test_trends_without_window_end_give_the_latest_window`, `test_trends_of_a_given_window` | La fenêtre la plus récente par défaut ; le tri et le départage |
| `test_an_unknown_window_gives_404`, `test_a_base_without_trend_gives_404`, `test_a_malformed_window_end_gives_422` | Les cas d'erreur de la spec |
| `test_an_item_is_read_by_the_branch_of_its_kind_only` | Une base incohérente ne mêle pas deux tables |
| `test_each_data_route_documents_its_errors`, `test_the_dates_of_k_b_and_of_the_sources_are_described` | L'OpenAPI dit les erreurs de chaque route et l'origine de chaque date |
| `grep -c raw_file_path docs/api/openapi-donnees.json` → `0` | Le contrat publié ne nomme pas le chemin du brut |
| `kb serve` sur une base d'essai, `curl` de chaque cas | L'API répond pour de vrai (corps dans la PR) ; `kb-serve.log` donne `route=/items/{item_id}`, jamais l'identifiant ni la clé |
| `uv run pytest` (1 232), `ruff check`, `ruff format --check`, `mypy --strict`, `pip-audit` | Les contrôles de la CI passent |

## 7. Ce que tu dois pouvoir défendre

1. **Pourquoi une union discriminée plutôt qu'un seul schéma ?** Le contrat dit, sorte par
   sorte, quels champs existent ; Pydantic valide contre le bon schéma au premier coup
   (`item_schema.py:106-113`).
2. **Un client peut-il lire `raw_file_path` par le détail ?** Non. Aucune requête du détail ne
   le sélectionne. Et même si une lecture le rendait un jour, le schéma ne le nomme pas :
   `TypeAdapter` l'ignorerait, puis FastAPI revalide la réponse. Un test le vérifie sur les 17
   items.
3. **Pourquoi `/items/01` répond 422 et pas l'item 1 ?** Une ressource, une seule URL ;
   `fullmatch` du motif `0|-?[1-9][0-9]*` (`item_router.py:55`).
4. **Que se passe-t-il si un import écrit pendant qu'on lit un détail ?** Les requêtes du
   détail partagent une transaction de lecture (`reading.py:362`), pour voir la base d'un seul
   instant ; non testé par un import concurrent (section 8).
5. **`exploited: false` veut-il dire « pas exploitée » ?** Non : « absente du catalogue KEV ».
   L'OpenAPI le dit dans la description du champ.

## 8. Zones non vérifiées

- **Le coût du filtre par `kind` sur une base réelle.** Sur la base vide, sans `ANALYZE`,
  `EXPLAIN QUERY PLAN` montre que les branches `publication` et `vulnerability` de la liste
  parcourent maintenant `item` au lieu de leur table. Il n'a pas été mesuré sur la base de
  Sabine (non ouverte).
- **La garantie de cohérence par `BEGIN`.** Qu'une transaction de lecture voie la base d'un
  seul instant est le comportement de SQLite tel que nous le comprenons ; nous ne l'avons ni
  relu dans sa documentation dans cette session, ni testé par un import concurrent. Le test
  vérifie seulement qu'aucune transaction ne reste ouverte.
- **Le temps constant de la comparaison des clés** (API2) : toujours non mesuré, comme à #184.

## 9. Ce qui reste

- **D'une alerte à sa vulnérabilité** : le détail d'une alerte ne donne pas l'identifiant de
  l'item vulnérabilité. Une issue sera créée en fin de mission (décision de Sabine).
- **Signalé, sans issue** :
  - le nombre de surlignages n'a pas de borne, à la collecte comme dans l'API ;
  - `publication` et `vulnerability` n'ont pas la clé étrangère `(item_id, kind)` (Alembic,
    #186) ;
  - un jour est écrit sous deux formes, à regrouper avec le futur identifiant public de l'item
    (version 0.3.0) ;
  - le délai de requête (API4).
- La recherche FTS5 (#188) et les filtres `source` et `in` (#187) restent à venir.

## Sources

- [Unions, « Discriminated Unions »](https://docs.pydantic.dev/latest/concepts/unions/#discriminated-unions)
  — Pydantic, lu par Context7 le 2026-10-14 : `Field(discriminator=…)` sur un champ `Literal`,
  et l'objet `discriminator` de l'OpenAPI dans le schéma produit (l'union du détail).
- [Extra Models, « Union or anyOf »](https://fastapi.tiangolo.com/tutorial/extra-models/) —
  FastAPI, lu par Context7 le 2026-10-14 : une union de modèles comme modèle de réponse (le type
  de retour de la route).
- [Additional Responses in OpenAPI](https://fastapi.tiangolo.com/advanced/additional-responses/)
  — FastAPI, lu par Context7 le 2026-10-14 : `responses={404: {"model": …}}` documente une
  réponse d'erreur avec son modèle (le 404 nommé de chaque route).
- [API1:2023 Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
  — OWASP, section « How To Prevent », relevée par recherche web le 2026-10-15 : les
  identifiants aléatoires (GUID) sont l'une des mesures de prévention, à côté du contrôle
  d'autorisation par objet (le choix de garder `item.id`).
