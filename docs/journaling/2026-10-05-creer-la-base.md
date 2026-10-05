# Créer la base par une commande rejouable

- **Date** : 2026-10-05
- **Branche** : `feat/create-db`
- **Issues** : #81 (créer la base) et #67 (tester le chargement du schéma), sous-issues de l'épic
  #20 « Fusion et base »
- **Fichiers principaux** : `src/k_b/database/__init__.py`, `src/k_b/cli.py`,
  `src/k_b/database/schema.sql`, `docs/stockage.md`, `README.md`
- **Dans la même série** : [fusionner les items](2026-10-05-fusionner-les-items.md) (#80), qui
  a décidé qu'une même CVE dans deux sources donne deux items.

## 1. Le pourquoi

Le schéma de la base (`schema.sql`) et ses données de référence (`seed_sources.sql`) existent
depuis le 02/10, mais rien ne les exécutait. Aucun test ne les chargeait non plus : une erreur de
syntaxe ou de contrainte n'aurait été vue qu'à l'installation. Il faut aussi qu'un tiers puisse
créer la base en une commande et en obtenir le même résultat que nous.

Cette PR ajoute :

- `kb create-db`, qui crée la base dans le dossier de données ;
- `connect_database`, la seule façon d'ouvrir la base, qui active les clés étrangères ;
- le test de #67 ;
- un changement de schéma décidé le même jour avec #80 : la CVE n'est plus unique.

Elle n'importe aucun item, ce que fera #82.

## 2. Le comment

### 2.1 Une connexion qui vérifie les clés étrangères

```python
def connect_database(database_path: Path) -> sqlite3.Connection:
    """Open the database; SQLite ignores foreign keys unless each connection turns them on."""
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
```
`src/k_b/database/__init__.py:11-14`

Par défaut, SQLite **n'applique pas** les clés étrangères. Le réglage ne se garde pas dans le
fichier : il vaut pour une connexion. `docs/stockage.md` l'imposait déjà (« le code de connexion
l'exécute à chaque ouverture »). Tout accès à la base passe donc par cette fonction, y compris
l'import (#82) et plus tard l'API. Le test `test_a_connection_checks_the_foreign_keys` insère un
item d'une source inconnue (`rss`) et vérifie qu'il est refusé.

### 2.2 Créer, ou refuser sans toucher

```python
    if database_path.exists():
        raise FileExistsError(f"{database_path} already exists")
```
`src/k_b/database/__init__.py:24-25`

« Rejouable » veut dire ici qu'une seconde exécution ne casse rien. Si `k-b.sqlite` existe, la
commande refuse, avec le code 2 et le message `error: <chemin> already exists`, et elle ne touche
pas au fichier (option a, choix de Sabine). Pour repartir de zéro, on supprime le fichier, et la
base se reconstruit depuis le brut (#82).

La création exécute `PRAGMA journal_mode = WAL`, que SQLite garde dans le fichier, puis les deux
scripts (`__init__.py:30-32`). Les scripts sont lus avec `importlib.resources` (`files("k_b.database")`) :
ils sont trouvés dans le paquet installé, quel que soit le dossier courant. J'ai vérifié que le
wheel construit par `uv build` les contient.

### 2.3 Un échec ne laisse pas de base à moitié construite

```python
    except BaseException:
        # BaseException: Ctrl-C during the creation must not leave a half-built file either.
        for suffix in ("", "-wal", "-shm"):
            Path(f"{database_path}{suffix}").unlink(missing_ok=True)
        raise
```
`src/k_b/database/__init__.py:35-39`

Ce bloc vient du constat 1 de la revue de code. `sqlite3.connect` crée le fichier tout de suite,
et `executescript` valide chaque instruction l'une après l'autre. Si une erreur survient en cours
de route (disque plein, erreur d'E/S, Ctrl-C), il resterait des tables sans sources. Le
`kb create-db` suivant refuserait alors ce fichier comme « already exists », et la base aurait
l'air valide sans l'être. On supprime donc le fichier et ses deux fichiers compagnons du mode
WAL, puis on relève l'erreur d'origine (`raise` sans argument).

`BaseException`, et pas `Exception`, parce que `KeyboardInterrupt` (Ctrl-C) n'hérite pas
d'`Exception`.

### 2.4 La commande et ses codes de sortie

```python
    except FileExistsError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except (sqlite3.Error, OSError) as error:
        print(f"error: {database_path}: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
```
`src/k_b/cli.py:55-60`

Les codes suivent la convention de `kb collect` :

- 0 : la base est créée ;
- 1 : l'opération a été tentée et a échoué ;
- 2 : rien n'a été tenté, parce que `KB_DATA_DIR` est invalide ou que la base existe déjà.

Le code 1 vient du constat 2 de la revue. Avant la correction, un dossier en lecture seule
faisait sortir sur une trace Python. `FileExistsError` est une sous-classe d'`OSError` : il est
attrapé avant, sinon il sortirait avec le code 1.

Le contrôle de `KB_DATA_DIR` est sorti de `main` dans `read_data_dir` (`cli.py:39`), commun à
`collect` et `create-db`. C'est une seule connaissance (« qu'est-ce qu'un dossier de données
valide »), qui doit vivre à un seul endroit (`code.md`).

### 2.5 Une CVE n'est plus unique, mais elle est indexée

```sql
    cve     TEXT CHECK (cve GLOB 'CVE-[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9]*')
) STRICT;

CREATE INDEX vulnerability_cve ON vulnerability (cve);
```
`src/k_b/database/schema.sql:88-91`

C'est la décision de Sabine prise avec #80 (journal ADR du 2026-10-05) : une entrée CISA et une
alerte GitHub de même CVE sont deux items, reliés par leur CVE. Le `UNIQUE` les aurait refusées.
L'index remplace celui que `UNIQUE` créait d'office. Sans lui, retrouver les items d'une CVE,
pour le croisement CISA ↔ GitHub, demanderait de lire toute la table. `docs/stockage.md` est mis
à jour partout où la CVE et la connexion sont décrites : le dédoublonnage porté par la base, le
rôle de la CVE, le MLD, la liste des index, et `connect_database` comme code de connexion.

## 3. Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Base existante | **Refuser sans toucher** (option a, choix de Sabine). | `CREATE TABLE IF NOT EXISTS` partout : une table déjà là avec un autre schéma passerait sans erreur. |
| Échec de création | **Supprimer le fichier et relever l'erreur** (après revue). | Créer sous un nom temporaire puis renommer : plus de code, et le mode WAL crée des fichiers compagnons qu'il faudrait aussi renommer. |
| Lecture des scripts | **`importlib.resources`** : marche depuis le paquet installé. | Un chemin relatif à `__file__` : il marche aussi, mais il suppose que le paquet est un dossier ordinaire. |
| Unicité de la CVE | **Retirée, remplacée par un index** (décision de Sabine, #80). | La garder : deux sources de même CVE ne pourraient pas coexister. |
| Contrôle de `KB_DATA_DIR` | **`read_data_dir`, partagé** par les deux commandes. | Le recopier dans `create-db` : la même règle à deux endroits. |
| Nom du fichier | **`k-b.sqlite`**, une constante (`DATABASE_FILE_NAME`). | Une variable d'environnement de plus : aucun besoin aujourd'hui (`code.md`, pas de paramètre « pour plus tard »). |

## 4. Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_schema_and_the_sources_load_with_every_expected_table` (#67) | En mémoire, avec `foreign_keys = ON`, `schema.sql` puis `seed_sources.sql` s'exécutent sans erreur, les 9 tables attendues existent, et les 7 sources sont là. |
| `test_two_sources_can_share_a_cve` | Une alerte GitHub et une entrée CISA de même CVE entrent toutes les deux. |
| `test_a_cve_is_found_through_its_index` | `EXPLAIN QUERY PLAN` d'une recherche par CVE utilise `vulnerability_cve`. |
| `test_a_new_database_has_the_sources_and_the_wal_mode` | Le fichier créé contient les 7 sources et reste en mode `wal`. |
| `test_an_existing_database_is_refused_and_left_untouched` | Un fichier existant fait lever `FileExistsError`, et son contenu ne change pas. |
| `test_a_connection_checks_the_foreign_keys` | `connect_database` refuse un item d'une source inconnue. |
| `test_a_failed_creation_leaves_no_database_behind` | Un script SQL fautif fait lever l'erreur, et aucun `k-b.sqlite*` ne reste. |
| `test_create_db_*` (4 tests) | Les codes de sortie 0, 2 (base existante, `KB_DATA_DIR` absent) et 1 (dossier en lecture seule). |
| `KB_DATA_DIR=… uv run kb create-db`, lancé deux fois | Observé : `database created: …`, code 0 ; puis `error: … already exists`, code 2 ; `sqlite3` lit `wal` et 7 sources. |
| `uv run pytest` | 222 tests passent. |

## 5. Ce que tu dois pouvoir défendre

1. **Pourquoi `PRAGMA foreign_keys = ON` à chaque connexion ?** SQLite ne garde pas ce réglage
   dans le fichier. Sans lui, une clé étrangère fausse passe, ce qui a été vérifié le 02/10
   (`stockage.md`). D'où une fonction unique d'ouverture (`__init__.py:11-14`).
2. **Que se passe-t-il si on relance `kb create-db` ?** Le code 2, un message, et le fichier
   n'est pas touché (`__init__.py:24-25`, `cli.py:55-57`).
3. **Et si la création plante à mi-chemin ?** Le fichier et ses compagnons `-wal` et `-shm` sont
   supprimés, puis l'erreur remonte. La commande sort avec le code 1 et un message, pas une trace
   (`__init__.py:35-39`, `cli.py:58-60`).
4. **Pourquoi la CVE n'est-elle pas unique ?** Une même CVE vient de deux sources qui disent des
   choses différentes : l'exploitation active chez CISA, le paquet et les versions chez GitHub.
   On garde les deux, et on les relie par un index (`schema.sql:88-91`).
5. **Où est la sécurité ?** Aucune donnée externe n'entre ici. Le chemin vient de `KB_DATA_DIR`,
   une variable d'environnement de confiance, et les scripts sont ceux du paquet. Les requêtes
   des tests sont paramétrées (`?`). La protection de la base contre les données collectées
   viendra avec l'import (#82), par des requêtes paramétrées.

## 6. Zones non vérifiées

- **Un fichier créé entre le contrôle et la connexion.** Si un autre programme créait
  `k-b.sqlite` juste entre `exists()` et `connect`, la création échouerait (« table already
  exists »), et le nettoyage supprimerait ce fichier, qui n'est pas le nôtre. Avec un seul
  utilisateur qui lance la commande à la main, le cas est improbable. Il n'est pas traité.
- **Le nettoyage sur Ctrl-C** n'est pas testé : seul l'échec par une erreur SQL l'est.
- **Le dossier en lecture seule** n'est testé que sous macOS, et le test est sauté si on lance
  les tests en root.
- **`executescript` valide instruction par instruction** : c'est ce que dit la documentation de
  `sqlite3` (« No other implicit transaction control is performed »), lue de mémoire et non
  revérifiée pour cette note. Le comportement observé dans le test (aucun fichier ne reste)
  ne dépend pas de ce détail.

## 7. Ce qui reste

- Remplir la base à partir du brut, et écrire le journal des rejets et des écartés : #82.
- La purge et la durée de conservation : #83.
- Les champs propres à CISA KEV (fournisseur, produit, rançongiciel) : #84.
