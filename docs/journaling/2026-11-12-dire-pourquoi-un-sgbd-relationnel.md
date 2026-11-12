# Dire pourquoi un SGBD relationnel convient au modèle de K-B

- Date : 2026-11-12
- Branche : `docs/relational-dbms-fit`
- Issue : #600
- Fichier : `docs/stockage.md` (section « Pourquoi un SGBD relationnel », et quatre retouches
  ailleurs dans le fichier)
- Commits : `7cd5594` (la section), `cde3315` (les corrections après relecture). Les autres commits
  de la liste injectée sont ceux de `main` avant la branche (`1b6e0b8` et avant) : ils ne sont pas
  de cette PR.
- Série : [créer la base](2026-10-05-creer-la-base.md),
  [clarifier le modèle de la base](2026-10-07-clarifier-le-modele-de-la-base.md),
  [rejeter l'item que la base refuse](2026-10-16-rejeter-l-item-que-la-base-refuse.md),
  [redessiner le modèle Merise](2026-10-20-redessiner-le-modele-merise-depuis-le-schema.md).

## Le pourquoi

`docs/stockage.md` disait pourquoi SQLite en local et PostgreSQL en ligne, mais pas pourquoi un SGBD
**relationnel** : la question venait avant celle du moteur, et le document n'y répondait pas. La
section nouvelle y répond à partir de ce que le schéma et le code tiennent déjà, sans rien ajouter
au code : un SGBD relationnel tient lui-même, à chaque écriture, les clés étrangères, l'exclusion
des sous-types, les `CHECK` et la transaction de l'import. Elle dit aussi ce que la base ne tient
pas.

## Le comment

### Un modèle, trois écritures

Le MCD, le MLD (`docs/merise/`) et `schema.sql` (le MPD) décrivent le même modèle, à des écarts
près déjà listés dans « MCD et MLD » (deux dénormalisations voulues, des écarts propres au MPD).
`schema.sql` fait foi pour le code. La section n'écrit aucun sens de dérivation entre eux : le
modèle a été conçu, puis corrigé par itérations quand celui en place n'était pas adapté.

### L'exclusion des sous-types, tenue par la base

`item` porte la sorte de chaque item, et `UNIQUE (id, kind)` fait de ce couple la cible d'une clé
étrangère (`src/k_b/database/schema.sql:42-50`) :

```sql
    raw_data_id INTEGER NOT NULL REFERENCES raw_data (id),
    -- The target of the (item_id, kind) foreign key of each subtype: an item has one subtype.
    UNIQUE (id, kind)
```

Chaque sous-type fixe sa sorte et vise ce couple (`schema.sql:176-177`, `:192`, ici `release`) :

```sql
    item_id               INTEGER NOT NULL UNIQUE,
    kind                  TEXT NOT NULL CHECK (kind = 'release'),
    ...
    FOREIGN KEY (item_id, kind) REFERENCES item (id, kind)
```

Une ligne de `release` ne peut viser qu'un item dont la sorte est `release` : le `CHECK` fixe
`kind`, la clé composée exige que `(item_id, 'release')` existe dans `item`. `item_id` unique : un
item a une ligne de sous-type au plus. `NOT NULL` sur `kind` : avec un `kind` nul, le `CHECK`
passerait (un `CHECK` nul n'est pas faux) et la clé composée ne serait pas vérifiée
(`schema.sql:173`).

### Ce qui devient un rejet, ce qui arrête l'import

C'est le constat bloquant de la relecture : la première version disait qu'« une entrée que la
base refuse est annulée seule ». Le code dit autre chose (`src/k_b/database/errors.py:17-22`) :

```python
# The constraints an entry breaks by its own values, the only ones an import turns into a
# rejection (conventions.md, rule 1), with a value Python cannot hand to the base (an integer
# beyond 64 bits, a lone surrogate). A FOREIGN KEY, a PRIMARY KEY or a type of a STRICT table
# refused is not due to the entry: its writer chose the rows it points to, its key and the types
```

Un `CHECK`, un `UNIQUE` hors clé primaire ou un `NOT NULL` refusé vient de la valeur reçue, comme
une valeur que Python ne peut pas passer à la base (un entier au-delà de 64 bits, un surrogate
isolé) : le `SAVEPOINT` de l'item l'annule seul (`src/k_b/database/savepoint.py:30-40`), l'entrée devient un
rejet du journal d'import. Une clé étrangère, une clé primaire ou un type refusé vient de
l'écrivain ou du schéma, donc d'un défaut de K-B : l'import s'arrête, et la transaction entière est
annulée (`src/k_b/etl/load.py:80-85`).

### La limite NUL, mise à jour

Le paragraphe « Limite de SQLite » disait qu'un `tag_name` commençant par un NUL passait l'item et
faisait échouer l'import. C'était périmé : l'item refuse tout NUL avant la base
(`src/k_b/items.py:118-124`, `check_text_can_be_stored`). Le paragraphe le dit maintenant.

## Choix faits et options écartées

- **Argumenter à partir du modèle, pas d'une comparaison datée.** Aucune entrée du journal ADR ne
  compare le relationnel à une autre famille de stockage : la section ne l'invente pas, elle dit ce
  que le modèle demande et ce que la base tient. Écarté : comparer à une base documentaire par une
  phrase générale, que rien du dépôt n'appuie.
- **Aucun sens de dérivation** entre MCD, MLD et `schema.sql` (tri de time-knight, d'après ce que
  Sabine a dit le 12/11). Écartés : « le MLD tiré du MCD » (première version) et « le MCD tiré de
  `schema.sql` » (proposé par la relecture, d'après #211).
- **Corriger dans la même PR** trois passages du fichier que la section contredisait ou citait mal
  (limite NUL, deux renvois de ligne, « un item n'a qu'un sous-type ») : même fichier, et la section
  y renvoie. Écarté : une PR à part.
- **Laisser hors de la PR** le glissement des renvois de ligne du MLD (`.drawio`) : issue #603.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run pytest tests/test_schema.py -k "another_kind or kind_is_not or without_kind or starts_with_a_nul" tests/test_database.py::test_a_connection_checks_the_foreign_keys tests/database/test_savepoint.py tests/test_schema_structures.py` → 10 passed | les tests cités par la section existent et passent : exclusion des sous-types, clés étrangères actives, `SAVEPOINT`, deux schémas comparés, NUL refusé |
| `grep -c REFERENCES` → 17 dans `schema.sql`, 17 dans `schema_postgresql.sql` ; `FOREIGN KEY` → 5 et 5 | les deux scripts ont les mêmes clés étrangères en nombre, dont les cinq clés composées |
| Deux relectures neuves (la section, puis le diff des corrections) | chaque renvoi `fichier:ligne` vérifié ; constats triés par time-knight |
| Recherche des caractères `Cc` et `Cf` dans `docs/stockage.md` → aucun | le `"\0v1"` du texte est une barre oblique inverse suivie de 0, pas un NUL |

## Ce que tu dois pouvoir défendre

1. **Pourquoi un SGBD relationnel et pas une base documentaire ?** Le modèle est fait de relations
   que la base doit tenir à chaque écriture : un item et son brut, un item et un seul sous-type de
   sa sorte, un surlignage et son item. Une clé étrangère composée et un `CHECK` les tiennent sans
   code (`schema.sql:42-50`, `:192`). Limite à dire : aucune comparaison chiffrée n'a été faite.
2. **Comment la base empêche-t-elle un item d'avoir deux sous-types ?** `item_id` unique dans chaque
   sous-type, et la clé `(item_id, kind)` vers `UNIQUE (id, kind)` : une `release` ne peut viser
   qu'un item de sorte `release` (`schema.sql:176-177`, `:192` ; `tests/test_schema.py:372`).
3. **Une entrée invalide arrête-t-elle l'import ?** Non si c'est sa valeur (`CHECK`, `UNIQUE`,
   `NOT NULL`) : rejet, l'import continue. Oui si c'est une clé étrangère, une clé primaire ou un
   type : c'est un défaut du code, l'import entier est annulé (`errors.py:17-22`, `load.py:80-85`).
4. **Que ne tient pas la base ?** Chaque élément d'une liste JSON, la règle « une fenêtre, une
   donnée brute » de `trend` (tenue par l'écriture), la sorte de l'item que visent `publication` et
   `vulnerability`, le rattachement d'un surlignage à une entrée Zotero (tenu par le code).

## Zones non vérifiées

- Les tests de la moitié PostgreSQL (`-m postgresql`) n'ont pas été lancés : la section ne cite que
  des tests SQLite et `tests/test_schema_structures.py`.
- Aucune comparaison avec une autre famille de stockage n'a été mesurée ni écrite au journal ADR.

## Ce qui reste

- Recaler les renvois de ligne du MLD sur `schema.sql` : #603.
- Le choix du moteur (SQLite, PostgreSQL) est inchangé, dans la section qui suit.
