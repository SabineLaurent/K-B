# Créer la base et y importer en PostgreSQL, par l'adaptateur

- **Date** : 2026-11-06
- **Branche** : `feat/postgresql-import`
- **Issue** : #417 (I5 du plan de mise en ligne, première partie : l'écriture)
- **Série** : suite de [Faire passer la base par une couche d'accès](2026-11-06-faire-passer-la-base-par-une-couche-d-acces.md)
  (#416), qui a préparé `database/engine.py` et `database/errors.py` sans changer le comportement.
- **Fichiers principaux** : `src/k_b/database/location.py`, `postgresql.py`, `engine.py`, `errors.py`,
  `creation.py`, `schema_postgresql.sql`, `writers/catalog.py`, `src/k_b/etl/load.py`,
  `.github/workflows/postgresql.yml`.

## 1. Le pourquoi

En ligne, sur Azure Container Apps, K-B n'a pas de disque fiable pour un fichier SQLite : un partage
Azure Files ne garantit pas les verrous de SQLite, et un conteneur Blob ne se monte pas. Ton cadre
du 05/11 est le suivant : « En production c'est postgresql qui est le porteur de la base de donnée.
Comme ça je garde sqlite fonctionnel dans le cas où je fais une installation locale de kb ». Il faut
donc deux moteurs, choisis par une variable, avec le même code au-dessus.

Cette PR fait la moitié **écriture** : `kb create-db` crée la base PostgreSQL, et `kb import`, purges
comprises, y écrit les mêmes lignes qu'en SQLite. La lecture (l'API de données, `read_items`) reste en
SQLite jusqu'à #418. Le critère de l'issue : « `kb create-db`, puis `kb import` sur PostgreSQL
écrivent les mêmes lignes que sur SQLite (un test), retraits de Zotero et de KEV compris, liste vide
comprise » ; « un test par SQLSTATE rejeté, et un où une erreur du système arrête l'import » ; « le
job CI sur PostgreSQL est vert pour les tests d'écriture ».

## 2. Le comment

### 2.1 Où est la base : une variable, deux formes, aucune fuite du secret

`KB_DATABASE_URL` choisit le moteur. Absente, la base reste le fichier SQLite du dossier de données,
comme avant : rien ne change pour le Mac.

```python
# src/k_b/database/location.py:96
    if not value.startswith(POSTGRESQL_URL_PREFIXES):
        return (
            f"{DATABASE_URL_VARIABLE} is neither a postgresql:// nor a postgres:// URL"
        )
    libpq_variables_set = sorted(LIBPQ_VARIABLES & environ.keys())
```

Trois points de sécurité tiennent dans ce module :
- **Une valeur vide est refusée**, et ne retombe pas sur SQLite. Un secret qu'Azure n'aurait pas
  injecté ne doit pas faire écrire l'import dans un fichier du conteneur, qui disparaîtrait à son
  arrêt. C'est l'« échouer fermé » de `code.md`.
- **Une variable que libpq lit en silence** (`PGHOST`, `PGPASSWORD`…, les 42 noms de sa doc) est
  refusée quand la base est PostgreSQL. libpq la lirait sans que `kb` le sache, contre la règle 2 de
  `poc.md`. `PGDATA`, que pose Homebrew, n'en fait pas partie.
- **L'URL ne s'affiche jamais.** `PostgresUrl.value` est déclaré `field(repr=False)`
  (`location.py:71`), et `describe_location` rend une phrase constante (`location.py:115`) :

```python
# src/k_b/database/location.py:113
    if isinstance(location, Path):
        return str(location)
    return f"the PostgreSQL base of {DATABASE_URL_VARIABLE}"
```

Une première version citait le nom de la base, lu par `urlsplit`. La revue de sécurité a montré
deux fuites. Avec un `/` non encodé dans le mot de passe, `urlsplit` coupe l'hôte trop tôt, et la fin
du mot de passe passe dans le « chemin ». Avec un `／` pleine chasse, `urlsplit` lève une
`ValueError` qui cite le mot de passe entier, et `cli.py` la journalisait avec sa trace. D'où la
phrase constante.

### 2.2 Le traducteur : le SQL de `sqlite3` lu par psycopg

Le SQL de K-B est écrit pour `sqlite3`, avec les marqueurs `?` et `:nom`. psycopg attend `%s` et
`%(nom)s`. La connexion PostgreSQL traduit chaque texte avant de l'envoyer :

```python
# src/k_b/database/postgresql.py:24
NAMED_PLACEHOLDER = re.compile(r"(?<![:\w\\]):(\w+)(?![:\w])")
...
# src/k_b/database/postgresql.py:44
    escaped = sql.replace("%", "%%").replace("?", "%s")
    return NAMED_PLACEHOLDER.sub(r"%(\1)s", escaped)
```

- **Le `%` est doublé d'abord** : pour psycopg, `%` ouvre un marqueur. Un `LIKE '%a%'` serait sinon
  lu comme un marqueur.
- **La règle de `:nom` est celle de SQLAlchemy 2.0.55** pour son `text()` : un nom précédé d'un
  `:` qui ne suit ni un `:`, ni une lettre, ni un chiffre, ni un `\`. Ainsi `x::text` (un cast
  PostgreSQL) et `'09:30:00'` ne sont pas touchés.
- **Toujours des paramètres** : `execute(sql, parameters=())`. psycopg ne rend `%%` en `%` que si
  des paramètres sont passés (observé).

La sécurité ne vient pas du traducteur : il ne voit que des constantes de K-B, et chaque valeur part
en paramètre lié. Deux tests le tiennent. `test_each_sql_text_of_database_passes_through_the_translator`
relève par AST chaque texte SQL de `database/` et le fait passer dans le traducteur, sur le job
SQLite. `test_each_sql_text_of_database_is_accepted_by_postgresql` demande à PostgreSQL de préparer
chacun.

### 2.3 Une connexion, deux moteurs : l'union et `in_transaction`

```python
# src/k_b/database/engine.py:16
Connection = SqliteConnection | PostgresConnection
```

`PostgresConnection` n'a que les méthodes de `sqlite3.Connection` dont K-B se sert : `execute`,
`executemany`, `executescript`, `commit`, `rollback`, `close` et `in_transaction`. La branche SQLite
reste la classe de `sqlite3` elle-même, sans enveloppe. Le point délicat est `in_transaction` :

```python
# src/k_b/database/postgresql.py:100
    def in_transaction(self) -> bool:
        """Whether a transaction is open, an error in it included (#302)."""
        return self._connection.info.transaction_status in OPEN_TRANSACTION_STATUSES
```

`OPEN_TRANSACTION_STATUSES` vaut `{INTRANS, INERROR}`. Après une erreur, PostgreSQL met la
transaction en `INERROR` : elle est encore ouverte, à défaire. Si `in_transaction` valait faux dans
cet état, `savepoint.py` sauterait le `ROLLBACK TO` de l'entrée refusée, et tout l'import tomberait.
C'est le cœur de la règle 1 de `conventions.md` (une entrée refusée seule).

### 2.4 Ce que la base refuse : une entrée seule, ou tout l'import

```python
# src/k_b/database/errors.py:28
ENTRY_SQLSTATES = frozenset({"23514", "23505", "23502", "22003"})
...
# src/k_b/database/errors.py:40
        return error.sqlstate in ENTRY_SQLSTATES and not is_primary_key_refusal(error)
```

Ces SQLSTATE sont les équivalents de `sqlite3.IntegrityError` : `CHECK`, `UNIQUE`, `NOT NULL`, et
22003, un entier au-delà de 64 bits. Une clé primaire refusée (`<table>_pkey`) arrête l'import, comme
`SQLITE_CONSTRAINT_PRIMARYKEY` en SQLite : c'est l'écrivain qui choisit la clé, pas l'entrée.

Le motif écrit au journal est passé deux fois par la revue de sécurité. Le `DETAIL` de PostgreSQL
recopie la ligne refusée. Le message principal, lui, peut citer la valeur : `value
"987654321098765432109876543210" is out of range for type bigint`, ou `invalid input syntax for type
bigint: "…"`. Or un titre, un auteur ou le texte d'un clip sont des données personnelles ou du texte
d'item, que la règle 5 de `poc.md` interdit dans un journal. Le motif ne garde donc que des noms du
schéma :

```python
# src/k_b/database/errors.py:82
    names = [
        f"{label} {quote_value(name)}"
        for label, name in (
            ("table", error.diag.table_name),
            ("column", error.diag.column_name),
            ("type", error.diag.datatype_name),
            ("constraint", error.diag.constraint_name),
        )
        if name is not None
    ]
```

Ce qui donne, par exemple, `CheckViolation 23514: table 'note', constraint 'note_text_check'`. La
même fonction sert au journal d'import (un refus) et au journal de la commande (une erreur qui
arrête tout).

### 2.5 Le schéma PostgreSQL : le même contrat, écrit autrement

`schema.sql` fait foi ; `schema_postgresql.sql` le suit table par table. Deux exemples montrent la
méthode.

```sql
-- src/k_b/database/schema_postgresql.sql:20
CREATE DOMAIN utc_date AS text
    CHECK (VALUE ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z$'
        AND pg_input_is_valid(VALUE, 'timestamptz'));
```

Les dates restent du **texte**, comme en SQLite. Avec `timestamptz`, psycopg rendrait des
`datetime`, et une ligne lue sur PostgreSQL différerait de la même ligne lue sur SQLite. La forme est
tenue par l'expression régulière, l'heure bornée à 23 (PostgreSQL accepte `24:00:00`, observé). Un
jour qui existe est tenu par `pg_input_is_valid`, qui rend faux là où un cast lèverait une erreur
(22007 ou 22008), et cette erreur arrêterait l'import au lieu de refuser l'entrée.

```sql
-- src/k_b/database/schema_postgresql.sql:67
        CHECK (CASE WHEN authors IS NOT JSON ARRAY THEN false
            ELSE json_array_length(authors::json) > 0 END)
```

Une liste JSON est encore du texte. Le `CASE` garantit que le cast `::json` ne tourne que sur un
tableau JSON valide : PostgreSQL n'assure pas l'ordre d'évaluation d'un `AND`.

Autres traductions : `COLLATE NOCASE` → `citext`, dans une base en collation C (la casse des seules
lettres ASCII, comme `NOCASE`) ; `UNIQUE` sur `clip.url` → un index unique sur `md5(url)`, une entrée
de B-tree ne tenant pas 2 000 caractères UTF-8 ; `INTEGER PRIMARY KEY` → `bigint GENERATED BY
DEFAULT AS IDENTITY`. Le tableau complet est dans `docs/stockage.md`, « Ce qui est propre à SQLite ».

`kb create-db` refuse une base hors UTF8 ou hors collation C, et cite chaque réglage lu
(`creation.py:101-108`). Il crée le schéma et les sources en une transaction : sur une erreur,
rien ne reste.

### 2.6 L'import : les retraits, le verrou, le commit interrompu

**Les retraits** (une CVE sortie du catalogue KEV, une entrée ou un surlignage disparu de Zotero) se
calculaient par `json_each`, propre à SQLite. Ils se calculent maintenant en Python :

```python
# src/k_b/database/writers/catalog.py:99
    absent_keys = find_absent_keys(connection, select_not_withdrawn, present_keys)
    return connection.executemany(
        mark_withdrawn,
        [{"collected_at": collected_at, "key": key} for key in absent_keys],
    ).rowcount
```

L'issue demandait un `IN` généré. Mais un `IN` de plus de 32 766 paramètres lève « too many SQL
variables » en SQLite (observé), une erreur du système qui arrêterait chaque import. La différence en
Python n'a pas cette borne. La liste vide est traitée avant l'appel, par les deux écrivains : sans
CVE présente, rien n'est retiré.

**Le verrou** : sur PostgreSQL, deux imports pourraient écrire en même temps. `lock_for_writing`
(`load.py:76`) prend `pg_advisory_xact_lock` au début de la transaction, attendu 5 s au plus, le délai
de `sqlite3`.

**Le commit interrompu** : c'est la subtilité principale. En SQLite, un SIGTERM reçu pendant le
commit n'est levé par Python qu'une fois le commit rendu : l'import est validé. Sur PostgreSQL,
psycopg attend la réponse à `COMMIT` en Python. Sur le signal, il demande au serveur d'annuler, et le
serveur peut l'avoir validé ou défait (psycopg 3.3.8, `Connection.wait`). K-B ne sait donc pas :

```python
# src/k_b/etl/load.py:144
        if isinstance(error, ENGINE_ERRORS) or connection.in_transaction:
            journal_path.unlink(missing_ok=True)
        elif is_commit_finished_before_a_signal(connection):
            logger.info("import committed, journal kept: %s", ...)
        else:
            logger.info("import commit interrupted, outcome unknown, journal kept: %s", ...)
```

Le journal est gardé : un journal en double coûte moins qu'un import validé sans journal (#302). Le
journal de fonctionnement dit ce qui a été vu (`code.md`), et non « import committed ».

## 3. Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Un adaptateur maison sur psycopg 3 | garde le SQL et le code SQLite décrits dans E1 | SQLAlchemy Core : sa doc décrit, avec pysqlite, un « Incorrect behavior for SAVEPOINT », et ses remèdes changent le moment du `BEGIN` (ADR du 06/11) |
| L'union `sqlite3.Connection \| PostgresConnection` | deux moteurs connus, la branche SQLite intacte | un `Protocol` (abstraction ouverte) ; envelopper aussi SQLite |
| `ENGINE_ERRORS`, un tuple, pour `except` | `except` n'accepte pas une union de types | une classe d'erreur K-B par erreur psycopg (envelopper chaque appel, perdre la classe du SQLSTATE) |
| Dates et listes JSON en texte | mêmes valeurs lues sur les deux moteurs | `timestamptz` et `jsonb` (des `datetime` et des listes Python) |
| Base créée hors de K-B, en UTF8 et en C | `citext` plie la casse selon la collation de la base | `COLLATE "C"` par colonne : ne règle pas `citext` |
| Retraits par différence en Python | aucune borne de paramètres | `IN` généré, que demandait l'issue : 32 766 paramètres en SQLite |
| Motif d'une erreur PostgreSQL par les noms de `diag` | un message peut citer la valeur | `message_primary` (revue de sécurité) ; une liste blanche par classe de SQLSTATE (un jugement de sécurité de plus) |
| `table_name` en plus des trois noms demandés | un 23502 nommerait la colonne sans sa table | — |
| Une URL que libpq ne lit pas : sortie 2, un réglage refusé | c'est un réglage faux, pas une panne | la vérifier dans `location.py` par `psycopg.conninfo` (un troisième module importerait psycopg) |
| `psycopg[binary]` seul | une dépendance entre avec la PR qui s'en sert | `psycopg-pool` ici : il sert à #418 |
| PostgreSQL 17 au moins, 18 en CI | `datlocale` et le fournisseur builtin datent de 17 | 16, d'abord écrit : `kb create-db` y échouerait (revue de code) |
| Un workflow à part, `postgresql.yml` | deux PR ouvertes ne touchent pas le même fichier (règle des axes) | un job de plus dans `ci.yml` |

Choix imposés par une consigne du dépôt : refuser les variables de libpq (règle 2 de `poc.md`) ;
les SQLSTATE de refus (règle 1 de `conventions.md`, modifiée sur ton accord) ; aucun texte d'item ni
auteur dans un journal (règle 5 de `poc.md`) ; les actions épinglées par SHA et l'image par digest
(mission).

## 4. Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_kb_create_db_then_kb_import_write_the_same_rows_on_postgresql_as_on_sqlite` (`tests/etl/test_import_on_both_engines.py:250`) | le critère de fin : mêmes lignes, chaque `id` remplacé par son rang, retraits KEV et Zotero, extrait sans surlignage, puis un import 4 ans plus tard qui fait tourner les purges |
| `test_an_error_due_to_the_entry_is_refused_alone_and_the_import_goes_on` (`tests/database/test_postgresql.py:251`), un cas par SQLSTATE | un test par SQLSTATE rejeté ; l'entrée suivante est écrite et validée |
| `test_a_foreign_key_postgresql_refuses_stops_the_import_writes_nothing_and_logs_no_row` | une erreur du système arrête l'import, sans rien écrire |
| `test_each_sql_text_of_database_passes_through_the_translator`, `…_is_accepted_by_postgresql` | chaque constante SQL passe dans le traducteur, et PostgreSQL la prépare |
| `test_a_connection_is_in_a_transaction_while_it_writes_and_after_an_error` | `in_transaction` vrai en `INTRANS` et en `INERROR` |
| `test_a_sigterm_during_the_commit_on_postgresql_keeps_the_journal_and_says_the_outcome_is_unknown` | le vrai chemin de psycopg : un déclencheur différé rend le `COMMIT` lent, le SIGTERM arrive pendant, le serveur défait l'import ; sortie 143, journal gardé |
| `test_a_connection_closed_by_psycopg_during_the_commit_still_exits_with_the_code_of_sigterm` | si psycopg ferme la connexion, la sortie reste 143 (contrat de #193) |
| `tests/commands/test_postgresql_errors_in_logs.py` | une valeur repère absente du journal d'import et de `kb.log`, pour un refus (22003) comme pour un arrêt (22P02) ; un troisième test prouve que PostgreSQL cite bien ces repères |
| `test_kb_create_db_never_shows_a_part_of_a_password_the_url_does_not_encode` | `/` et `／` dans le mot de passe : rien sur stdout, stderr ni `kb.log` |
| `test_the_variables_refused_cover_every_one_the_libpq_installed_reads` | la liste des 42 variables couvre celles que la libpq installée déclare |
| `test_only_the_access_layer_imports_a_driver_of_the_base` | psycopg n'est importé que par `postgresql.py` et `errors.py` |
| Essai réel du 2026-11-06, lancé par toi, sur deux copies de ton `raw/` (45 fichiers) : un import neuf en SQLite, un en PostgreSQL 18.4 ; sorties console gardées telles quelles dans la PR #440, section « Real run » | les deux imports rendent `import: 40 raw read, 3207 written, 763 trend rows, 1 left out, 0 rejected, 0 withdrawn` et la sortie 0 ; les 15 tables ont les mêmes comptes (`0 difference(s)`), et les deux journaux d'import, sans leur date, sont identiques. Ni retrait ni clip tagué dans ce brut : le test « mêmes lignes » les couvre |
| `uv run pytest` → 3592 passed, 146 deselected ; `uv run pytest -m postgresql` → 135 passed (rebasé sur `2e8b5d7`) | la suite SQLite existante reste verte, et les tests PostgreSQL passent sur le 18.4 local |

## 5. Ce que tu dois pouvoir défendre

1. **« Pourquoi ne pas avoir pris SQLAlchemy, la solution standard ? »** — Avec pysqlite, SQLAlchemy
   change le moment du `BEGIN` et le traitement des savepoints. Il aurait fallu réécrire
   `savepoint.py`, le `BEGIN` de la lecture et la prise des erreurs de `load.py`, soit le code décrit
   dans E1. L'adaptateur fait 138 lignes (`postgresql.py`) et reprend la règle de marqueurs de
   SQLAlchemy.
2. **« Votre traducteur réécrit le SQL avec des expressions régulières : n'est-ce pas une porte à
   l'injection ? »** — Non. Il ne lit que des constantes de K-B (`postgresql.py:41-45`), et chaque
   valeur part en paramètre lié. Un test fait passer chaque texte SQL de `database/` dans le
   traducteur, et un autre les fait préparer par PostgreSQL (`tests/database/test_postgresql.py:102`,
   `:131`).
3. **« Que se passe-t-il si une entrée viole une contrainte au milieu de l'import ? »** — Un
   `SAVEPOINT` par item. L'erreur reste dans la transaction (`INERROR`) ; `in_transaction` reste vrai,
   le `ROLLBACK TO` défait l'item seul, et l'import continue (`errors.py:35-41`,
   `postgresql.py:100-102`).
4. **« Le conteneur est arrêté pendant le commit : la base et le journal sont-ils cohérents ? »** —
   L'issue est inconnue. Le journal est gardé, et la ligne `outcome unknown` le dit (`load.py:144-160`).
   Si le serveur a défait l'import, l'import suivant relit les fichiers et écrit un second journal.
   Lever le doute en interrogeant la base est l'objet de #302.
5. **« Où est le mot de passe de la base, et peut-il fuir ? »** — Dans `KB_DATABASE_URL` seulement.
   Il n'est jamais affiché (`repr=False`, `describe_location` constant), jamais cité dans une erreur
   (l'erreur de libpq est remplacée, `from None`, `postgresql.py:126-129`), et une variable `PG*` posée à
   côté est refusée. Les tests cherchent un repère du mot de passe dans stdout, stderr et `kb.log`.

## 6. Zones non vérifiées

- **PostgreSQL 17** : c'est le minimum annoncé, mais seul le 18 a tourné (18.4 en local, 18.6 en CI).
  Que `datlocale` date de 17 vient des notes de version citées par la revue, non relues ici.
- **Un `COMMIT` validé malgré l'annulation** : le test passe par le cas où le serveur défait l'import.
  Le cas inverse (le serveur valide, puis psycopg relève le signal) suit la même branche, mais aucun
  test ne le produit.
- **psycopg** : son comportement sur un signal vient de la lecture de son code (3.3.8,
  `connection.py:479-516`, `_connection_base.py:597-617`) et des tests. Les pages de doc de psycopg
  lues au plan, avant le `/clear`, ne sont pas recopiées ici : je ne les ai plus sous les yeux.
- **Le serveur flexible d'Azure** : rien n'a tourné dessus (`citext` permis, collation C, Entra) :
  c'est #421.
- **Le volume réel** : le test « mêmes lignes » porte sur les fixtures, pas sur la base du Mac. Le
  coût de la différence en Python sur toute la bibliothèque Zotero n'a pas été mesuré.
- Le coût de l'import de psycopg à chaque commande `kb` (environ 50 ms selon la revue) n'a pas été
  mesuré.

## 7. Ce qui reste

- **#418** : la lecture sur PostgreSQL (`read_items`, l'API de données, le délai des requêtes,
  `psycopg-pool`) ; le verrou en tête des purges ; la comparaison de structure des deux schémas ; les
  scénarios du test « mêmes lignes » au-delà des retraits ; `docs/specs-api.md:372`.
- **#419, #202** : le compose de préproduction avec PostgreSQL.
- **#421** : la base en ligne, ses rôles Entra, `kb migrate-database`, qui pose le schéma sur une
  base vide ; `sslmode=verify-full` dans `KB_DATABASE_URL` ; une base sans ses tables qui sort en 2
  et non en 1.
- **#302** : savoir, après un commit interrompu, si l'import a été validé.
- **#186** : les migrations, qui attendent le premier changement de schéma de la base en ligne (ta
  décision du 06/11 : « On repart d'une base de prod vierge »).
- Jusqu'à #418, `kb serve-data` lit le fichier SQLite pendant que `kb import` écrit dans PostgreSQL.
