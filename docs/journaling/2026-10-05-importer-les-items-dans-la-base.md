# Importer les items dans la base — `kb import`

- **Date** : 2026-10-05
- **Branche** : `feat/import-items`
- **Issue** : #82 (sous-issue de l'épic #20)
- **Fichiers principaux** : `src/k_b/import_items.py`, `src/k_b/cli.py`, `src/k_b/items.py`,
  `tests/test_import_items.py`
- **Série** : suite de [fusionner les items](2026-10-05-fusionner-les-items.md) et de
  [créer la base](2026-10-05-creer-la-base.md).

## Le pourquoi

Le pipeline a quatre étapes (`docs/specs-collecte.md`) : collecter le brut, le lire en items,
fusionner, stocker. Les trois premières existaient ; il manquait la dernière. La base est la sortie
du pipeline, celle que l'API (#21) lira : sans import, la base créée par `kb create-db` reste vide.

Le critère de fin de #82 : « une commande `kb` lit le brut, le fusionne et insère dans la base les
items, auteurs, dépôts, vulnérabilités et leur collecte ; rejouée sur le même brut, elle donne la
même base. Le journal des rejets et doublons est écrit à côté du brut. Test de bout en bout sur
fixtures. »

Pour la certification, c'est la case C4 « base créée et alimentée par une commande rejouable ».

## Le comment

### 1. Une seule transaction pour la base

`src/k_b/import_items.py:61-69`

```python
connection = connect_database(database_path)
try:
    # The context manager commits on success and rolls back on any error.
    with connection:
        for item in merged.items:
            write_item(connection, item)
        delete_orphan_authors(connection)
```

`with connection:` est le gestionnaire de contexte de `sqlite3` : à la sortie normale du bloc, il
valide (`COMMIT`) ; si une exception sort du bloc, il annule (`ROLLBACK`). Tous les items sont donc
écrits, ou aucun. Une base à moitié importée serait pire qu'une base inchangée : elle aurait l'air
valide. Attention, ce gestionnaire **ne ferme pas** la connexion : d'où le `finally` qui appelle
`connection.close()`.

### 2. L'upsert : réécrire un item sous le même identifiant

`src/k_b/import_items.py:30-38`

```sql
ON CONFLICT (source_code, source_item_id) DO UPDATE SET
    title = excluded.title,
    ...
RETURNING item_id
```

Un « upsert » insère la ligne, ou la met à jour si elle existe déjà. Le conflit est détecté sur la
contrainte `UNIQUE (source_code, source_item_id)` du schéma : c'est l'identité d'un item.
`excluded` désigne la ligne qu'on tentait d'insérer. `RETURNING item_id` renvoie l'identifiant de
la ligne, nouvelle ou existante (SQLite ≥ 3.35 ; 3.50.4 ici).

Pourquoi c'est important : l'`item_id` ne change pas d'un import à l'autre, alors que l'API
l'exposera. Une révision arXiv (v2 après v1) réécrit le titre, la date de révision et la
collecte, sous le même `item_id`.

Les sous-types suivent le même schéma : `repository` et `vulnerability` font
`ON CONFLICT (item_id) DO UPDATE` (`import_items.py:91-102`), `collection` fait
`ON CONFLICT (raw_file_path) DO NOTHING` puis relit son identifiant (`import_items.py:108-116`).

### 3. Les auteurs : effacer puis remettre, et ne pas garder d'orphelins

`src/k_b/import_items.py:125-126` et `142-144`

```python
connection.execute("DELETE FROM item_author WHERE item_id = ?", (item_id,))
for position, name in enumerate(dict.fromkeys(authors), start=1):
```

```python
"DELETE FROM author WHERE author_id NOT IN (SELECT author_id FROM item_author)"
```

Les liens d'un item vers ses auteurs sont effacés puis réécrits dans l'ordre : c'est plus simple
que comparer l'ancienne et la nouvelle liste, et le résultat est le même. `dict.fromkeys` retire
les noms répétés en gardant l'ordre de première apparition : la base interdit de lier deux fois le
même auteur au même item (clé primaire `(item_id, author_id)`).

Effet de bord : si une révision arXiv retire un auteur, son nom reste dans `author` sans aucun
item. C'est une donnée personnelle sans usage (RGPD, minimisation), et `docs/stockage.md` exige
qu'un auteur ait au moins un item. La seconde requête les supprime, dans la même transaction.

### 4. La nature « vulnérabilité » portée par l'item

`src/k_b/items.py:51-56`

```python
is_vulnerability: bool = False

@model_validator(mode="after")
def check_a_cve_is_a_vulnerability(self) -> "Item":
    if self.cve is not None and not self.is_vulnerability:
```

Une alerte GitHub sans CVE est une vulnérabilité (le modèle dit `cve` « facultatif »). Sans ce
champ, l'import ne pouvait pas la distinguer d'une release : les deux ont `cve = None`. Le
validateur Pydantic refuse l'incohérence inverse : un item avec CVE qui ne serait pas une
vulnérabilité. `convert_vulnerability` (CISA) et `convert_advisory` (GitHub) le mettent à vrai
(`items.py:90`, `117`).

### 5. Le journal : entier ou pas du tout

`src/k_b/import_items.py:176-185`

```python
temporary_path = log_path.with_name(log_path.name + ".tmp")
try:
    temporary_path.write_text(...)
    os.replace(temporary_path, log_path)
except BaseException:
    temporary_path.unlink(missing_ok=True)
    raise
```

`write_text` vide le fichier avant d'écrire : interrompu, il laisserait un journal tronqué. Le
journal est donc écrit à côté, puis renommé par `os.replace`, qui remplace la destination en une
seule opération sur un même système de fichiers. En cas d'échec, le fichier temporaire est
supprimé (même `Ctrl-C`, d'où `BaseException`), et l'ancien journal reste entier.

Ordre à connaître : la base est validée **avant** l'écriture du journal. Si le journal échoue, la
base garde l'import, la commande sort en code 1, et le journal précédent reste. C'est écrit dans
la docstring, le README et `specs-collecte.md`.

### 6. La commande et ses codes de sortie

`src/k_b/cli.py:70-79`

```python
except MissingDatabaseError as error:
    print(f"error: {error}; create it with kb create-db", file=sys.stderr)
    return 2
except (sqlite3.Error, OSError) as error:
    ...
    return 1
```

`sqlite3.connect` **crée** un fichier vide s'il n'existe pas : `import_items` vérifie donc d'abord
que la base existe, et lève une exception dédiée. Elle hérite de `FileNotFoundError`, mais la CLI
l'attrape à part : seule l'absence de la base renvoie à `kb create-db`, pas n'importe quel
fichier introuvable. Code 2 : mauvaise configuration ; code 1 : l'import a échoué.

## Choix faits et options écartées

| Décision | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Rejouer l'import | Upsert sur `(source_code, source_item_id)` : `item_id` stable pour l'API | Vider la base et tout réinsérer : plus simple, mais les `item_id` changeraient à chaque import |
| Nature vulnérabilité | `Item.is_vulnerability` (option A, décision de Sabine du 2026-10-05) : conforme au modèle | Vulnérabilité seulement si CVE (B) : contredit « cve facultatif », perd les alertes sans CVE |
| Nom répété parmi les auteurs | Lié une fois, à sa première position | Laisser l'insertion échouer : un seul papier bloquerait tout l'import |
| Auteurs orphelins | Supprimés à chaque import, même transaction (constat de revue M2, accord de Sabine) | Les laisser à la purge (#8) : un nom sans usage resterait d'ici là |
| Écriture du journal | Fichier temporaire puis `os.replace` (constat de revue M1) | `write_text` direct : journal tronqué possible |
| Emplacement du journal | `<KB_DATA_DIR>/import-log.jsonl`, réécrit à chaque import : même brut, même journal | Un journal par import, horodaté : le rejeu ne donnerait plus le même fichier |
| Base absente | Refus, exception dédiée, code 2 | Créer la base à la volée : mélange deux commandes, et masque une erreur de chemin |
| `star_gain` | Pas importé : `Item` ne porte pas les étoiles gagnées, le critère n'en parle pas | — |

Imposé par le dépôt : tests d'abord, une transaction et un échec fermé (`code.md`, « Échouer
fermé »), journal qui dit l'observé (règle, identifiant, URL), Python et `uv`.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_raw_files_go_into_the_database` | Bout en bout sur fixtures : 113 items, 5 collectes, 11 liens d'auteur, 100 dépôts, 7 vulnérabilités |
| `test_an_import_run_again_on_the_same_raw_gives_the_same_database_and_log` | Rejouable : dump SQL complet (`iterdump`) et journal identiques |
| `test_a_new_collection_keeps_the_identifier_of_an_item_already_imported` | `item_id` stable quand une collecte ramène le même item |
| `test_a_newer_revision_rewrites_the_paper_under_the_same_identifier` | L'upsert réécrit vraiment : nouvelle date de révision, nouvelle collecte, nouveaux auteurs, même `item_id` |
| `test_an_author_left_without_item_is_deleted` | Aucun auteur orphelin après une révision |
| `test_a_failed_import_leaves_the_database_and_the_log_unchanged` | `ROLLBACK` : un conflit d'URL n'écrit rien, ni base ni journal |
| `test_a_log_that_cannot_be_written_keeps_the_previous_log_whole` | Journal écrit après la base ; l'ancien journal reste entier, pas de `.tmp` |
| `test_an_advisory_without_cve_is_a_vulnerability_without_cve` | Option A : ligne `vulnerability` avec `cve` vide |
| `test_each_duplicate_removed_is_written_to_the_log_with_its_rule`, `test_each_rejected_file_is_written_to_the_log` | Le journal trace doublons et rejets |
| `test_a_missing_database_is_refused_and_not_created`, tests `test_import_*` de `test_cli.py` | Codes de sortie 0, 1 et 2 ; la base n'est pas créée par erreur |
| `uv run pytest` : 251 tests verts | Rien de cassé ailleurs |
| `kb import` réel sur deux collectes CISA identiques | Sans base : code 2 ; après `kb create-db` : 4 items, 4 doublons tracés |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas vider la base et tout réinsérer ?** Ce serait rejouable aussi, mais les
   `item_id` changeraient à chaque import ; l'API les exposera, un lien vers un item casserait.
   L'upsert garde l'identifiant (`import_items.py:30-38`).
2. **Que se passe-t-il si l'import plante au milieu ?** Le `ROLLBACK` du gestionnaire de contexte
   annule tout ; la base est celle d'avant (`import_items.py:64`, test d'échec). Si c'est le
   journal qui échoue, la base est déjà validée, et l'ancien journal reste entier (`:176-185`).
3. **Où est la sécurité ?** Le brut est une donnée non fiable : il est validé à la frontière par
   `Item`, modèle Pydantic strict (`items.py`). Toutes les requêtes sont paramétrées (`?`), aucune
   n'est construite par concaténation : pas d'injection SQL. Le journal est sérialisé par
   `json.dumps`, qui échappe les retours à la ligne.
4. **Et le RGPD ?** Seuls les noms d'auteurs arXiv entrent dans la base, comme prévu par le
   registre ; un auteur qui n'a plus d'item est supprimé à chaque import (`:140-144`). La purge
   par durée de conservation reste à #83.
5. **Comment sait-on qu'une alerte GitHub est une vulnérabilité sans CVE ?** Par
   `is_vulnerability`, fixé par le convertisseur de la source, et un validateur refuse un CVE sur
   un item qui n'est pas une vulnérabilité (`items.py:51-56`).

## Zones non vérifiées

- **Import pendant qu'une API lit la base** : le mode WAL le permet en principe ; non testé, il n'y
  a pas encore d'API.
- **Noms d'auteurs en Unicode** : « é » composé (NFC) ou décomposé (NFD) donnerait deux auteurs ;
  non vérifié sur des données réelles.
- **`os.replace` atomique** : garanti par la documentation Python sur un même système de fichiers
  (POSIX) ; le test simule son échec, il ne prouve pas l'atomicité.
- **Microsecondes des dates** : tronquées par le format `%S`. Les sources actuelles donnent des
  secondes ; non vérifié pour toutes.
- Constats de revue non retenus par Sabine (pas d'issue) : base supprimée entre le contrôle et
  la connexion, message de conflit sans l'item fautif, valeurs du brut recopiées dans le motif d'un
  rejet (`raw_items.py`), relecture complète du brut à chaque import.

## Ce qui reste

- Mesures d'étoiles (`star_gain`) et surlignages Zotero : sources ou champs pas encore lus en items.
- Purge par durée de conservation : #83.
- Lecture de la base par l'API : #21.
