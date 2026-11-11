# Servir les identifiants et le total dans la liste des items

- **Date** : 2026-11-11
- **Branche** : `feat/list-item-identifiers`
- **Issue** : #550
- **Fichiers principaux** : `src/k_b/database/reading.py`, `src/k_b/data_api/schemas/item_schema.py`,
  `src/k_b/data_api/routers/item_router.py`, `docs/specs-api.md`, `docs/api/openapi-donnees.json`
- **Série** : suite de [Servir la liste par une API locale](2026-10-14-servir-la-liste-par-une-api-locale.md) et
  de [Servir le détail et les tendances](2026-10-15-servir-le-detail-et-les-tendances.md).

Les commits de la branche, rebasée sur `origin/main` (`ffff467`), sont `4fc435d` (identifiants, `exploited`,
total), `89b0069` (10 paquets et `packages_truncated`), puis `b2089cf` et `0f943eb` (tri des deux passages de
revue de code). Le diff contre `origin/main` touche les onze fichiers listés en bas de la section « Preuve ». Les autres commits que
liste l'historique (purge, descente des fiches, justifications OWASP, règle des éléments externes) sont ceux de PR
déjà fusionnées : ils ne font pas partie de cette PR.

## Le pourquoi

Sabine a décidé le 2026-11-09 que le livrable E4 aurait une interface web, et ses maquettes sont validées. La
carte du fil affiche, sous le titre de chaque item, ses identifiants (CVE, GHSA, paquets touchés, numéro arXiv,
dépôt et version d'une release, lettre d'un article), une pastille « Exploitée (KEV) », et, en tête du fil,
« n items ».

Avant cette PR, `GET /items` ne servait que six champs : `id`, `kind`, `title`, `source_date`, `url` et
`withdrawn_at`. Les identifiants n'étaient servis que par le détail, `GET /items/{id}`, et aucun total
n'existait. Afficher le fil aurait demandé un appel au détail par carte, soit 100 appels pour une page de 100.
Sabine a choisi de compléter la liste plutôt que d'appauvrir les maquettes.

Le code fait donc trois choses : la liste sert, pour chaque item, les identifiants de sa sorte ; elle sert
`exploited` avec le sens exact qu'il a déjà au détail ; la page sert `total`.

## Le comment

### 1. Une requête, une branche par sorte, les identifiants en colonnes

La liste est une seule requête SQL, `LISTED_ITEMS`, faite de sept `SELECT` unis par `UNION ALL`, un par sorte
d'item. Chaque branche lit sa table de sous-type. Les huit colonnes d'identifiants s'ajoutent à chaque branche :
remplies pour la sorte qui les a, `NULL` pour les autres. Voici la branche des alertes GitHub
(`src/k_b/database/reading.py:58-64`) :

```sql
    SELECT item.id, item.kind, item.raw_data_id, advisory.summary, NULL, advisory.published_at,
        advisory.url, NULL,
        NULL, vulnerability.cve_id,
        CASE WHEN vulnerability.id IS NULL THEN NULL ELSE vulnerability.item_id IS NOT NULL END,
        advisory.ghsa_id, advisory.packages, NULL, NULL, NULL
    FROM item JOIN advisory ON advisory.item_id = item.id
        LEFT JOIN vulnerability ON vulnerability.id = advisory.vulnerability_id
```

Dans l'ordre : pas d'`arxiv_id` (`NULL`), la CVE de l'alerte, `exploited`, le GHSA, les paquets, puis trois
`NULL` (dépôt, tag, lettre). Le `LEFT JOIN` garde l'alerte qui ne cite aucune CVE : `vulnerability.cve_id` est
alors `NULL`. Ce sont les noms donnés dans la première branche (`AS arxiv_id`, `AS cve_id`…) qui nomment les
colonnes de toute l'union : SQLite et PostgreSQL prennent les noms du premier `SELECT`.

Pourquoi une colonne par identifiant plutôt qu'une requête de plus par item ? Parce que la page entière reste
une seule lecture, quelle que soit sa taille.

### 2. `exploited` : une seule règle, celle de l'ADR du 2026-10-07

« Exploitée » se lit `vulnerability.item_id IS NOT NULL` (journal ADR, 2026-10-07) : une ligne de
`vulnerability` a un `item_id` si et seulement si la faille est au catalogue CISA KEV. La branche des alertes
l'écrit en trois cas (ligne 61 ci-dessus) :

- pas de CVE (`vulnerability.id IS NULL`, le `LEFT JOIN` n'a rien trouvé) : `NULL` ;
- une CVE au catalogue : vrai ;
- une CVE absente du catalogue : faux. Faux veut dire « absente du catalogue », pas « non exploitée ».

Pour une faille, la branche des failles écrit `vulnerability.item_id IS NOT NULL` (ligne 45), toujours vrai
puisque la faille est un item du catalogue. Une faille retirée du catalogue depuis reste vraie : son retrait se
lit dans `withdrawn_at` (décision de Sabine du 2026-11-11).

SQLite rend un booléen SQL comme `0` ou `1`, PostgreSQL comme `False` ou `True`. `read_listed_item`
(`reading.py:379`) ramène les deux à `bool`. Il décode aussi `packages`, que les deux moteurs rendent en texte
JSON.

Avant cette PR, la règle était écrite dans une requête du seul détail, `SELECT_ADVISORY`. Elle est désormais
dans les branches de la liste, et le détail la reprend de l'item listé : `SELECT_ADVISORY` disparaît.

### 3. Le total : une requête `count(*)` dans la même transaction que la page

Le total est compté par une seconde requête, construite à partir des mêmes morceaux que la page
(`reading.py:108-110`) :

```python
SELECT_LISTED = f"SELECT {LISTED_FIELDS} FROM ({LISTED_ITEMS}) AS listed {LIST_FILTERS}"  # noqa: S608
# The rows of the filters, every page together: neither ORDER BY nor LIMIT.
COUNT_LISTED = f"SELECT count(*) FROM ({LISTED_ITEMS}) AS listed {LIST_FILTERS}"  # noqa: S608
```

Même union, mêmes filtres (`LIST_FILTERS` : `since`, `q`, `mode`), et le même filtre des sortes ajouté au
moment de l'appel. Seuls `ORDER BY`, `LIMIT` et `OFFSET` manquent : le total compte toutes les pages ensemble.
Le `# noqa: S608` répond à ruff, qui signale une requête construite par f-string. Ici, la f-string ne colle que
des constantes du module, et toute valeur venue du client est liée par un marqueur.

Les deux lectures se font dans une seule transaction (`reading.py:362-371`) :

```python
    begin_reading(connection)
    try:
        # One row more than the page tells whether a next page exists, in the same query.
        rows = connection.execute(
            SELECT_LISTED + kinds_filter + LIST_ORDER,
            {**filters, "limit": limit + 1, "offset": offset},
        ).fetchall()
        (total,) = connection.execute(COUNT_LISTED + kinds_filter, filters).fetchone()
    finally:
        end_reading(connection)
```

`begin_reading` ouvre une transaction : `BEGIN` en SQLite. En PostgreSQL, il ne fait rien : psycopg ouvre la
transaction à la première instruction, en `REPEATABLE READ READ ONLY` pour une connexion de lecture
(`database/engine.py:90-95`). Les deux lectures voient donc le même état de la base : un
import qui écrirait entre elles ne peut pas faire dire à la page 20 items et au total 19.

### 4. Un schéma par sorte : l'union discriminée par `kind`

Côté API, chaque sorte a son schéma Pydantic de liste, qui hérite des six champs communs et ajoute ses
identifiants (`src/k_b/data_api/schemas/item_schema.py:53-63`) :

```python
class ListedAdvisorySchema(ListedItemSchema):
    kind: Literal["advisory"]
    ghsa_id: str
    cve_id: str | None
    exploited: bool | None = Field(description=EXPLOITED)
    packages: list[str] = Field(
        description="The packages affected: the first 10 in the list, every one in the detail."
    )
```

`kind: Literal["advisory"]` fige `kind` à une valeur. Les sept schémas sont réunis en une union marquée
`Field(discriminator="kind")` (`item_schema.py:81-89`) : Pydantic lit `kind` et valide l'item par le seul
schéma de sa sorte. L'OpenAPI le dit par `oneOf` et `discriminator`, ce qui permet à un client généré de savoir
quels champs a chaque sorte.

C'est aussi la protection contre une fuite de champ (OWASP API3:2023). La lecture rend les quatorze colonnes pour
chaque item, `NULL` comprises. Le schéma de la sorte ne garde que ce qu'il nomme : Pydantic ignore par défaut
un champ non déclaré. L'`arxiv_id` d'une entrée Zotero, lu par la liste, n'est donc pas servi dans la liste,
puisque `ListedZoteroEntrySchema` ne le nomme pas.

Le détail de chaque sorte hérite de l'item listé de sa sorte (`class PaperDetailSchema(ListedPaperSchema)`…) :
le détail, c'est la liste plus les champs propres. Un identifiant n'est donc décrit qu'une fois.

### 5. La borne des paquets : 10 dans la liste, tous au détail

Une alerte peut toucher jusqu'à 100 paquets de 255 caractères, ce que l'import permet. Servis entiers, ils
pouvaient ajouter environ 2,58 Mo à une page de 100 alertes. Le client de l'API IA refuse toute réponse de plus
de 4 000 000 octets (`MAX_DATA_API_BODY_BYTES`), et le pire d'une page était déjà estimé à 2 Mo. La route coupe
donc la liste des paquets (`src/k_b/data_api/routers/item_router.py:129-138`) :

```python
def bound_packages(item: ListedItem) -> dict[str, Any]:
    """The fields of a listed item, the packages of an advisory cut at their bound, the cut said."""
    fields = item._asdict()
    if item.packages is None:
        return fields
    return {
        **fields,
        "packages": item.packages[:MAX_LISTED_PACKAGES],
        "packages_truncated": len(item.packages) > MAX_LISTED_PACKAGES,
    }
```

`MAX_LISTED_PACKAGES = 10` (`item_router.py:54`). `packages_truncated` dit au client qu'il en manque, et qu'il
lira le reste au détail. Le détail sert tous les paquets, avec `packages_truncated` toujours faux
(`item_router.py:179-181`). La coupe borne la réponse, pas la lecture : la base lit toujours la liste entière.
C'est le même motif que `highlights_truncated` et `body_truncated` du détail (#331).

## Choix faits et options écartées

| Choix retenu | Pourquoi | Option écartée, et pourquoi |
|---|---|---|
| Une union discriminée par `kind`, un schéma par sorte | Chaque sorte dit exactement ses champs ; un champ non nommé n'est pas servi (API3) | Un schéma plat aux champs tous optionnels : un `null` y dirait à la fois « pas de CVE » et « pas une alerte » |
| Détail = item listé + champs propres | Un identifiant est décrit une fois, et la règle d'`exploited` aussi | Garder `SELECT_ADVISORY` au détail : la règle écrite deux fois |
| `total` par `count(*)` séparé, dans la même transaction | Un total même pour une page au-delà de la fin ; la page et le total ne divergent pas | `count(*) OVER ()` dans la requête de la page : une page vide au-delà de la fin n'a aucune ligne, donc aucun total, et il faudrait un second chemin |
| Le total recompté à chaque page | Le contrat validé : `limit` et `offset` ne le changent pas | Le compter à la seule première page (`offset=0`) : moins de travail pour l'API IA, qui ne le lit pas, mais un autre contrat (revue, tranché par time-knight) |
| `exploited` vrai pour une faille retirée du catalogue | L'ADR du 2026-10-07 : « exploitée » se lit `item_id IS NOT NULL` ; le retrait est dans `withdrawn_at` (décision de Sabine) | Faux après un retrait : `exploited` aurait changé de sens entre la liste et l'ADR |
| 10 paquets dans la liste, la coupe dite | Une page de 100 alertes reste sous les 4 000 000 octets du client de l'API IA (décision de Sabine) | Les servir entiers : jusqu'à 2,58 Mo de plus, au-delà de la borne |
| La borne dans `item_router.py`, le chiffre 10 écrit dans la description | Les bornes du détail y vivent déjà (#430) ; le client lit le chiffre dans l'OpenAPI, et le test `TEN_PACKAGES` échoue si la constante change | Une description sans chiffre, lue comme la borne de `limit` ; la constante dans le schéma, écrite par f-string (revue, tranché par time-knight) |
| L'`arxiv_id` d'une entrée Zotero lu par la liste sans être servi | Un champ de sorte ne doit jamais porter le nom d'un champ de la liste (test de #185) | Le lire au seul détail : retire un `LEFT JOIN` par clé primaire, mais casse cette garde (revue, tranché par time-knight) |
| Le dict de `read_listed_item` | Il ne construit jamais un `ListedItem` dont un champ a le mauvais type | `ListedItem._make(row)._replace(…)` : plus court, mais refusé par `mypy --strict` (le texte JSON dans un champ `list[str]`) |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_an_item_of_each_kind_has_its_title_url_date_and_identifiers` (`tests/database/test_reading.py`) | La lecture rend, pour chaque sorte, l'item entier attendu : un `NULL` décalé dans une branche le ferait échouer |
| `test_exploited_reads_the_kev_catalog_as_a_boolean` (`test_reading.py`) | Les quatre cas d'`exploited` (au catalogue, retirée depuis, absente, sans CVE), en vrai booléen et pas en `0`/`1` |
| `test_the_total_counts_the_items_of_the_filters_on_every_page` (`test_reading.py`) | Le total est le même aux offsets 0, 2 et 100, pour huit combinaisons de filtres, page vide comprise |
| `test_the_list_ends_its_own_transaction_on_sqlite_only` (`test_reading.py`) | La transaction de lecture est fermée en SQLite ; en PostgreSQL, le pool la ferme |
| `test_each_kind_is_listed_with_its_identifiers`, `test_the_list_serves_only_the_fields_of_each_kind` (`tests/data_api/test_item_router.py`) | Le JSON de chaque sorte a ses champs et aucun autre : ni auteur, ni résumé, ni chemin de brut, ni l'`arxiv_id` d'une entrée Zotero (API3) |
| `test_the_total_counts_the_items_of_the_filters_whatever_the_page` (`test_item_router.py`) | `total` par `kind`, `since`, `q`, et inchangé par `limit` et `offset`, jusqu'à l'offset 10 000 |
| `test_the_list_serves_ten_packages_of_an_advisory_and_says_the_cut` (`test_item_router.py`) | 10 paquets servis sur 10 sans coupe ; 10 sur 11 avec `packages_truncated` vrai |
| `test_a_listed_item_is_a_union_discriminated_by_kind_in_a_page_with_its_total` (`tests/data_api/test_openapi.py`) | L'OpenAPI versionnée décrit l'union par `kind`, ses sept sortes, et `total` requis |
| `uv run pytest` → 4226 passed ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` verts (2026-11-11) | Les contrôles du dépôt passent en SQLite |
| `/security-review` : aucune vulnérabilité retenue | SQL fait de constantes et de valeurs liées, aucun auteur dans la liste, total sur les mêmes filtres que la page |

Les tests des modules `test_reading.py` et `test_item_router.py` tournent sur les deux moteurs (fixture
`engine`, `tests/conftest.py`) ; la moitié PostgreSQL est marquée `postgresql`.

Fichiers du diff contre `origin/main` : `MEMORY.md`, `docs/api/openapi-donnees.json`, `docs/fiches-veille.md`,
`docs/specs-api.md`, `src/k_b/data_api/app.py` (version 0.12.0), `src/k_b/data_api/routers/item_router.py`,
`src/k_b/data_api/schemas/item_schema.py`, `src/k_b/database/reading.py`, `tests/data_api/test_item_router.py`,
`tests/data_api/test_openapi.py`, `tests/database/test_reading.py` ; plus l'entrée du journal ADR et cette note.

## Ce que tu dois pouvoir défendre

1. **Le total ne révèle-t-il pas ce que la liste cache ?** Non. Il est compté sur la même union, les mêmes
   jointures et les mêmes filtres que la page (`COUNT_LISTED`, `reading.py:110`) : il ne compte que des items que
   la liste sert, retirés compris. Au-delà de l'offset 10 000, il compte des items que la liste ne sert plus,
   mais qu'un client lit en affinant `since`, `kind` ou `q`.
2. **Pourquoi pas `count(*) OVER ()`, qui ne fait qu'une lecture ?** Une page demandée au-delà de la fin ne
   rend aucune ligne, donc aucun total. Il faudrait alors une seconde requête pour ce cas : deux chemins au lieu
   d'un. C'est aussi la parade écrite de la limite acceptée (ci-dessous), si la lenteur devenait réelle.
3. **Que se passe-t-il si un import écrit entre la page et le total ?** Rien de visible : les deux lectures sont
   dans la même transaction (`begin_reading`, `reading.py:362`) et voient le même état. Seul un import entre
   deux pages change le `total` d'une page à l'autre, comme il décale déjà l'`offset` (limite écrite dans la spec).
4. **`exploited: false` veut-il dire que la faille n'est pas exploitée ?** Non : la CVE est absente du catalogue
   CISA KEV, c'est tout. `null`, c'est une alerte sans CVE. Une faille retirée du catalogue reste `true`, et
   son `withdrawn_at` dit le retrait (`EXPLOITED`, `item_schema.py:13-16`).
5. **Où est la sécurité de cette PR ?** Le SQL n'assemble que des constantes, et toute valeur du client est liée
   (pas d'injection). Un schéma par sorte en liste blanche fait qu'aucun champ non nommé ne sort (API3), et les
   auteurs, donnée personnelle, restent au seul détail. La borne des paquets limite la réponse (API4).
   L'authentification et la limite de débit ne changent pas.

## Zones non vérifiées

- **La moitié PostgreSQL des tests n'a pas tourné sur le Mac** : le serveur Homebrew demande un mot de passe. La
  preuve sur ce moteur est le job `tests-postgresql` de la CI de la PR.
- **Le coût du total n'est pas mesuré.** Qu'il coûte autant que la page est une hypothèse : sur une grande base,
  une recherche `q` lente pourrait répondre 503 en SQLite, où la page et le total se partagent les 5 s. En
  PostgreSQL, le pire théorique est de 12 s (deux instructions de 5 s, plus 2 s d'attente du pool), au-delà des
  10 s du client de l'API IA : limite acceptée par Sabine, parade `count(*) OVER ()` écrite dans
  `docs/specs-api.md`, « Délai ».
- **Le pire d'une page (2 Mo) est l'estimation de `docs/fiches-veille.md`**, pas une mesure de cette PR ; les
  0,26 Mo des 10 paquets sont un calcul (100 alertes × 10 paquets × 258 caractères), pas une mesure.
- **Le SQLite de l'image** n'est pas vérifié : `count(*) OVER ()` a été essayé sur le SQLite 3.50.4 du Python de
  K-B sur le Mac.
- **Pourquoi 10 et pas un autre nombre** : le chiffre est une décision de Sabine. Son effet est calculé (0,26 Mo),
  mais aucune raison de ce choix plutôt que d'un autre n'est écrite.

## Ce qui reste

- **Le tri du fil** : choisir l'ordre de `GET /items`, aujourd'hui du plus récent au plus ancien par la date de la
  source. Sabine doit le préciser ; décision ouverte au journal ADR.
- **Les routes des indicateurs du back office** : étape 3 de la mission, après que Sabine en aura fixé la source.
- **D'une alerte à sa faille** : l'alerte dit `cve_id` et `exploited`, pas l'`id` de l'item faille, et `q` ne
  cherche pas dans `cve_id` (`docs/specs-api.md`, « Hors de cette version »).
- **Le rendu des identifiants par le site** (paquet `web`, session FO) : les échapper à l'affichage relève de sa
  propre revue.
