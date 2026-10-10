# Longueurs maximales, contrôle des `CHECK` et documents

- **Date** : 2026-10-10
- **Branche** : `feat/max-lengths-and-check-tests`
- **Issue** : #122 (réécrire le schéma, 4/4)
- **Fichiers principaux** : `src/k_b/items.py`, `src/k_b/database/schema.sql`,
  `tests/test_schema.py`, `tests/test_import_items.py`, `docs/stockage.md`,
  `docs/registre-traitements.md`
- **Série** : dernière des quatre notes de la réécriture du schéma ; fait suite à
  [Dépôt suivi, release et alerte GitHub](2026-10-10-depot-suivi-release-et-alerte-github.md).

## Le pourquoi

Ce que K-B collecte vient de l'extérieur (arXiv, CISA, GitHub) : c'est une entrée non fiable.
Jusqu'ici, rien ne limitait la taille d'un texte qu'une source pouvait écrire en base, à part le
plafond de taille de la réponse téléchargée. La décision du 2026-10-08 demande qu'une longueur
maximale soit **tenue deux fois** (défense en profondeur) : à la lecture du brut, puis dans la
base. Une valeur trop longue fait refuser l'entrée, et le journal dit quel champ dépasse et de
combien ; rien n'est tronqué.

Deux contrôles écrits à deux endroits peuvent diverger sans bruit. Cette PR ajoute donc aussi les
tests qui les tiennent ensemble, et un test qui prouve que **chaque** `CHECK` du schéma refuse
bien ce qu'il interdit : c'est ce test qui dira, le jour des migrations Alembic, si une migration
a perdu un `CHECK`.

Enfin, les deux documents qui décrivaient encore l'ancien modèle (`stockage.md`, le registre des
traitements) sont remis au niveau du schéma codé.

## Le comment

### 1. Une table des bornes par sorte d'item

`Item` est un modèle commun aux quatre lecteurs. Son champ `summary` reçoit le résumé d'un papier,
la description d'une faille ou la note d'une release, qui vont dans trois colonnes différentes. Les
bornes sont donc rangées par sorte (`kind`), puis par champ :

```python
# src/k_b/items.py:77
MAX_LENGTH_BY_KIND: dict[ItemKind, dict[str, int]] = {
    "paper": {"source_item_id": 20, "title": 500, "summary": 5_000},
    "vulnerability": {
        "cve": CVE_MAX_LENGTH,
```

Chaque valeur est la borne de la colonne que ce champ remplit pour cette sorte : `title` d'un
`paper` va dans `publication.title`, `title` d'une `vulnerability` dans `vulnerability.name`.
`CVE_MAX_LENGTH` est une constante à part parce que deux sortes (la faille CISA et l'alerte
GitHub) écrivent dans la même colonne `vulnerability.cve_id` : une seule connaissance, un seul
endroit. Une sorte absente de la table (`newsletter_article`, qui n'a pas encore de table en
base) n'a pas de borne. Les clés sont typées `ItemKind` : mypy refuse une sorte mal écrite.

### 2. Le contrôle, dans le validateur du modèle

```python
# src/k_b/items.py:198
def list_texts_too_long(item: Item) -> list[str]:
    too_long = []
    for field, maximum in MAX_LENGTH_BY_KIND.get(item.kind, {}).items():
        text = getattr(item, field)
        if text is not None and len(text) > maximum:
            too_long.append(
                f"{field} too long: {len(text)} characters, maximum {maximum}"
            )
    return too_long
```

`check_lengths` (`items.py:190`) réunit les textes et les listes trop longs et lève une seule
`ValueError` qui les nomme tous. Elle est appelée en dernier par le `model_validator` d'`Item`
(`items.py:149`), après les contrôles de sorte déjà en place. Pydantic transforme cette erreur en
`ValidationError`, que la lecture du brut attrape déjà (`raw_items.py:97`) : l'entrée est rejetée,
journalisée, et les autres entrées du fichier sont lues. Aucune ligne n'a été ajoutée dans
`raw_items.py`, `import_items.py` ni `merge.py`.

Le message dit ce qui est observé : le champ, la longueur reçue, le maximum. Il ne recopie pas le
texte.

### 3. Les `CHECK` de la base

```sql
-- src/k_b/database/schema.sql:57
    summary      TEXT CHECK (length(summary) <= 5000),
```

SQLite ignore la longueur d'un `VARCHAR(n)` : la colonne reste en `TEXT` et la borne est un
`CHECK`. `length(NULL)` vaut `NULL`, et un `CHECK` qui vaut `NULL` passe : une colonne vide n'est
donc pas refusée. Quinze colonnes ont leur `CHECK` de longueur.

Une colonne peut porter plusieurs `CHECK`. Quand une règle s'ajoute à une colonne qui en avait
déjà une, elle a son propre `CHECK` :

```sql
-- src/k_b/database/schema.sql:154
        CHECK (length(tag_name) > 0)
        CHECK (length(tag_name) <= 255),
```

Raison : quand il refuse, SQLite écrit le texte du `CHECK` fautif dans son message
(`CHECK constraint failed: length(tag_name) <= 255`). Un `CHECK` par règle permet au test de
savoir lequel a refusé.

### 4. Les listes JSON

Les auteurs d'un papier et les paquets d'une alerte sont une liste JSON dans une colonne texte. Un
`CHECK` de SQLite ne peut pas parcourir les éléments d'une liste (pas de sous-requête dans un
`CHECK`). Le **nombre** d'éléments est donc tenu deux fois :

```sql
-- src/k_b/database/schema.sql:62
        CHECK (json_array_length(authors) <= 1000),
```

et par `MAX_COUNT_BY_KIND` (`items.py:101`). La **longueur de chaque nom** n'est tenue que par
l'item (`MAX_ELEMENT_LENGTH_BY_KIND`, `items.py:105`) : c'est la seule borne qui déroge à « tenue
deux fois ». Ce `CHECK` vient après celui de la forme JSON : SQLite les évalue dans l'ordre et
s'arrête au premier qui refuse, donc une valeur qui n'est pas du JSON est refusée par le premier.

### 5. Le test de concordance

```python
# tests/test_schema.py:482
def test_each_maximum_length_of_the_items_is_the_check_of_its_column():
    # \b: not the length( inside json_array_length(.
    assert read_maximums_of_the_schema(
        r"\blength\((\w+)\) <= (\d+)"
    ) == list_maximums_of_the_items(MAX_LENGTH_BY_KIND)
```

À gauche, les bornes lues dans le texte de `schema.sql`, table par table (`packages` existe dans
deux tables). À droite, les bornes de `items.py`, traduites en (table, colonne) par une table de
correspondance écrite dans le test (`COLUMN_BY_KIND_AND_FIELD`, `test_schema.py:432`). L'égalité
de deux dictionnaires joue dans les deux sens : une borne changée d'un seul côté, un `CHECK` sans
borne dans l'item, ou une borne sans `CHECK`, font échouer le test.

Cette table de correspondance recopie ce que fait l'import. Un second test évite de la croire
sur parole : `test_an_item_with_every_text_and_list_at_its_maximum_goes_into_the_database`
(`tests/test_import_items.py:560`) fabrique un item de chaque sorte, chaque champ à son maximum,
et le fait passer par le vrai import dans une base créée par `schema.sql`. Chaque texte nomme sa
sorte et son champ (`release.tag_name-release.tag_name-…`, `text_at_its_maximum`,
`test_import_items.py:534`), et le test compare les **valeurs** écrites dans chaque colonne, pas
leur longueur. Si un écrivain de `import_items.py` met un champ dans une autre colonne, même de
même borne (`tag_name` et `name` d'une release, à 255 toutes les deux), ce test échoue. La
première version du test ne comparait que des longueurs de textes identiques et ne voyait pas
cet échange : la seconde revue de code l'a montré par mutation.

### 6. Le test de comportement des `CHECK`, et sa garde

```python
# tests/test_schema.py:688
@pytest.mark.parametrize("table, check, changes", REFUSED_VALUES)
def test_a_value_each_check_forbids_is_refused(filled_database, table, check, changes):
    with pytest.raises(
        sqlite3.IntegrityError, match=re.escape(f"CHECK constraint failed: {check}")
    ):
        insert_row(filled_database, table, **changes)
```

`REFUSED_VALUES` (`test_schema.py:591`) donne, pour chacun des 47 `CHECK`, sa table, le début de
son texte, et le changement qui rend interdite une seule valeur d'une ligne valide. Le test attend
le texte de **ce** `CHECK` dans le message : une valeur refusée par un autre `CHECK` ne compte pas.

La garde (`test_each_check_of_the_schema_has_its_refused_value`, `test_schema.py:696`) vérifie
trois choses : le texte attendu figure une fois, et une seule, dans la définition de sa table ;
aucun `CHECK` n'a deux cas ; le nombre de cas égale le nombre de `CHECK` de `schema.sql`. Un
`CHECK` ajouté sans sa valeur refusée fait donc échouer la suite.

Deux `CHECK` de table portent plusieurs clauses réunies par `AND` : « les colonnes de la source
qui fait foi sont remplies si et seulement si `item_id` l'est », dans `publication` et
`vulnerability`. Un cas par `CHECK` ne suffit pas pour eux : une clause peut disparaître sans que
le `CHECK` disparaisse. Chaque colonne nommée a donc son propre cas
(`test_a_reference_row_with_its_item_but_without_one_of_its_columns_is_refused`,
`test_schema.py:736`), et une seconde garde compare les colonnes lues dans le `CHECK` à la liste
des colonnes testées (`test_each_clause_of_the_reference_checks_has_its_refused_value`,
`test_schema.py:761`).

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Où vivent les bornes côté Pydantic | Une table par sorte, lue par un contrôle du modèle : chaque colonne garde sa borne, et le message dit la longueur reçue (décision de Sabine, 2026-10-10). | Un `max_length` par champ : une seule borne (125 000) pour le résumé arXiv, la description CISA et la note de release, et un message sans la longueur reçue. Un modèle Pydantic par sorte : refonte d'`Item`, hors de l'issue. |
| Les valeurs | Proposées d'après la collecte du 2026-10-07, validées par Sabine ; aucune n'écarte un item de cette collecte. Le dictionnaire de données Merise ne donnait que 19 pour la référence GHSA. | Une borne serrée sur `release.body` : à 10 000 caractères, 22 des 100 releases collectées seraient écartées. |
| Listes JSON | Nombre d'éléments tenu deux fois, longueur d'un nom par l'item seul. | Borner la longueur du texte JSON : aucune borne égale côté item, ce texte est produit par l'import. |
| Trop long | L'entrée est refusée (décision du 2026-10-08). | Tronquer : modifie la donnée sans le dire. |
| Relier un cas de test à son `CHECK` | Le texte du `CHECK` dans le message de SQLite. | Nommer les contraintes (`CONSTRAINT nom`) : la relecture du plan a vu un nom ressortir pour un autre `CHECK`. Compter seulement les cas : deux cas pourraient tomber sur le même `CHECK`. |
| Les 11 tests de refus déjà écrits | Laissés en place : ces `CHECK` sont testés deux fois (doublon assumé). | Les déplacer dans la table des cas : retouche de code qui marche. |
| Les valeurs dans `stockage.md` | Le document donne la règle et renvoie à `items.py`. | Recopier le tableau : une troisième copie, qu'aucun test ne tient. |
| Colonnes sans borne | Celles que le code remplit (`source`, `tracked_repository`, chemin et flux de `raw_data`), les dates, `highlight`, `repository`, `star_gain`. | Tout borner : ces colonnes n'ont pas de modèle Pydantic en face, donc pas de concordance possible. |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run pytest` : 502 tests passent (403 avant la PR) | Rien d'existant n'est cassé ; aucune fixture ne dépassait une borne. |
| `test_a_text_is_accepted_up_to_its_maximum_length_and_refused_beyond` (16 cas) | Chaque borne accepte la valeur au maximum et refuse un caractère de plus, avec le champ, la longueur et le maximum dans le message. |
| `test_a_title_too_long_is_rejected_and_logged_and_the_other_papers_are_read` | Un titre trop long dans un flux arXiv issu de la collecte est écarté, journalisé, et les deux autres papiers sont lus. |
| `test_each_maximum_length_of_the_items_is_the_check_of_its_column`, et son pendant pour les nombres | Les bornes de `items.py` et les `CHECK` de `schema.sql` sont égaux. |
| `test_a_value_each_check_forbids_is_refused` (47 cas) et sa garde | Chaque `CHECK` refuse une valeur interdite, et aucun n'est sans cas. |
| `test_an_item_with_every_text_and_list_at_its_maximum_goes_into_the_database` | Un item à ses maximums passe le vrai import : item, écrivain et `CHECK` disent la même chose. |
| Casse volontaire, faite à la main puis défaite : borne du titre à 600 dans `items.py` seul | Le test de concordance échoue (4 tests rouges). |
| Casse volontaire : `CHECK` de `publication.summary` retiré, puis `CHECK` de date de `raw_data` retiré | Le test de comportement et la garde échouent. |
| `test_a_reference_row_with_its_item_but_without_one_of_its_columns_is_refused` (11 cas), le cas des deux dates sans item, et leur garde | Chaque clause des deux `CHECK` « si et seulement si » refuse une valeur interdite. |
| Casse volontaire : l'écrivain met le titre dans `release.name`, puis échange `tag_name` et `name` | Le test d'import aux maximums échoue dans les deux cas. |
| Casse volontaire : clause `authors` retirée du `CHECK` de `publication`, clause `description` puis `withdrawn_at` retirées de celui de `vulnerability` | Le cas de la colonne et la garde des clauses échouent. |
| `kb create-db` puis `kb import` sur une copie neuve de la collecte du 2026-10-07 | 2 400 items (github 155, arxiv 511, cisa_kev 1 734), 0 rejet : comme avant la PR. |

## Ce que tu dois pouvoir défendre

1. **Pourquoi deux contrôles pour la même limite ?** Défense en profondeur : Pydantic refuse à la
   lecture, entrée par entrée, sans faire tomber l'import ; le `CHECK` tient la base même si un
   autre code y écrit un jour. Le coût est la même valeur écrite deux fois, tenu par le test de
   concordance (`test_schema.py:482`).
2. **Pourquoi un `CHECK` et pas `VARCHAR(500)` ?** SQLite ignore la longueur déclarée d'un
   `VARCHAR`. En PostgreSQL, ce serait `varchar(n)` (`stockage.md`, « Ce qui est propre à
   SQLite »).
3. **Que se passe-t-il si une source envoie un texte trop long ?** L'entrée est rejetée à la
   lecture, avec une ligne dans le journal d'import (`title too long: 612 characters, maximum
   500`) ; les autres entrées du fichier entrent en base. Conséquence assumée : pour une ligne
   CISA refusée, son CVE reste lu comme non exploité (journal ADR, 2026-10-10).
4. **Comment sais-tu qu'un `CHECK` n'a pas été oublié dans les tests ?** La garde compte les
   `CHECK` de `schema.sql` et exige un cas pour chacun, identifié par son texte
   (`test_schema.py:696`) ; pour les deux `CHECK` à plusieurs clauses, une seconde garde exige
   un cas par colonne (`test_schema.py:761`).
5. **Pourquoi la longueur d'un nom d'auteur n'est-elle pas en base ?** Un `CHECK` de SQLite ne
   peut pas parcourir une liste JSON. Le nombre d'auteurs, lui, est tenu des deux côtés
   (`schema.sql:62`).

## Zones non vérifiées

- Les limites de GitHub pour `tag_name` et `name` ne sont pas vérifiées. 1 024 pour le résumé
  d'une alerte vient d'une copie tierce du schéma de l'API, 125 000 pour le corps d'une release
  d'un message d'erreur rapporté par des tiers : ni l'un ni l'autre n'est vérifié dans la
  documentation de GitHub.
- La collecte mesurée ne contient que les releases d'`anthropics/claude-code` et les alertes
  `pip` : les longueurs des trois autres dépôts suivis et des alertes `npm` sont inconnues.
- `length()` de SQLite s'arrête au premier caractère NUL, alors que Python les compte tous. Le
  comportement est constaté (SQLite 3.50.4), pas traité : un texte avec un NUL peut diverger entre
  les deux contrôles.
- Pendant une casse volontaire, un test est resté rouge après la remise en place du fichier :
  Python relisait le bytecode en cache de la version cassée (même taille, même seconde de
  modification). Constaté, puis levé en changeant la date du fichier ; à savoir pour rejouer ces
  casses.
- L'ordre d'évaluation des `CHECK` d'une colonne (le premier écrit refuse d'abord) est constaté
  par un essai, pas lu dans la documentation de SQLite.

## Ce qui reste

- **Entrées que l'item accepte et que la base refuse**, ce qui annule l'import entier : un
  identifiant de release au-delà de 64 bits, un CVE à chiffres non ASCII, un caractère de
  substitution isolé venu du JSON, un `tag_name` qui commence par un caractère NUL. Hors #122 :
  ils vont à la revue d'homogénéité de l'architecture (validation des entrées).
- **Le motif d'un rejet** recopie encore un extrait de l'item refusé (issue #92), dont le critère
  est à accorder avec la longueur et le maximum demandés par la décision du 2026-10-08.
- **Le MCD et le MLD** (`docs/merise/*.drawio`) et `clarification-modele.md` ne sont pas mis à
  jour ici : c'est la tâche Merise qui suit.
- **Le registre** cite encore `author` et `item.saved_at` pour Web Clipper et Zotero, le top 100
  GitHub gardé en base, et `~/K-B-data/` (comme le `README.md`) : lignes laissées à une autre
  tâche.
- **Les tables `repository` et `star_gain`**, sans écrivain, restent dans `schema.sql` ; les
  bornes de `highlight` sont à fixer avec son lecteur.
- **La comparaison avec une base migrée** viendra avec les migrations Alembic.
