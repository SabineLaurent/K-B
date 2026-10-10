# Nommer le flux arXiv `arxiv_cscr_x_csai`

- **Date** : 2026-10-10
- **Branche** : `refactor/arxiv-stream-name`
- **Issue** : #117
- **Fichiers principaux** : `src/k_b/sources/arxiv.py`, `tests/sources/test_arxiv.py`
- **Note précédente de la série** : [Renommer le dossier du brut et sortir l'état de collecte de
  `raw/`](2026-10-10-dossiers-du-brut-et-etat-de-collecte.md) (#116)

## Le pourquoi

arXiv n'est pas collecté en entier : K-B ne demande que les papiers à la fois en cs.CR et en
cs.AI qui contiennent l'un des mots-clés de la veille. Le 08/10, Sabine a décidé que ce flux porte
un nom qui le dit, `arxiv_cscr_x_csai` (journal ADR et `docs/2026-10-07-clarification-modele.md`,
« Le MCD de Sabine »). Ce nom laisse de la place à d'autres catégories arXiv plus tard.

Le nom d'une source sert à deux choses : le nom de son dossier de bruts
(`raw/automated_watch/<nom>/`) et la clé de sa date de dernière collecte dans
`collection_state.json`. Les deux changent. Sans précaution, la prochaine collecte ne
retrouverait pas sa date : elle repartirait du 1er mai 2026 (`FIRST_COLLECTION_START`).

## Le comment

### Un seul nom, écrit à un seul endroit

`src/k_b/sources/arxiv.py:58-63`

```python
# The name of its raw folders, written once: its instances and its kind use it.
FOLDER_PREFIX = "arxiv_cscr_x_csai"


class ArxivSource:
    name = FOLDER_PREFIX
```

Le code ne change que sur cette ligne. `ArxivSource.name` en dépend. `SOURCE_KINDS` aussi
(`src/k_b/source_kinds.py:51`, `SourceKind(arxiv.FOLDER_PREFIX, …)`). Le reste suit sans être
modifié.

### Le nom de la source donne le dossier et la clé d'état

`src/k_b/collect.py:41-48` (extraits)

```python
collect_one_source(
    source, raw_dir, now, last_collection_dates.get(source.name)
)
...
last_collection_dates[source.name] = now
```

`src/k_b/collect.py:69` : `source_dir = raw_dir / AUTOMATED_WATCH_DIR_NAME / source.name`.

Changer `name` change donc à la fois le dossier où le brut s'écrit et la clé lue puis écrite dans
`collection_state.json`. Rien d'autre n'est à toucher dans la collecte.

### Le code de source reste `arxiv`

`src/k_b/sources/arxiv.py:216-218`

```python
def convert_paper(paper: Paper, collected_at: datetime, raw_file_path: str) -> Item:
    return Item(
        source_code="arxiv",
```

Le **flux** (la requête et son dossier) et la **source** (arXiv, l'organisme) sont deux notions
distinctes. `source_code` désigne la source. On le retrouve dans `items.py:19`, dans la règle de
révision de `merge.py:98` et dans `database/seed_sources.sql:6`. Il ne change pas, comme le veut
la conception de l'issue.

### À l'import, l'ancien dossier `arxiv/` n'est plus reconnu

`src/k_b/source_contract.py:62-66`

```python
for kind in kinds:
    if folder_name == kind.folder_prefix or folder_name.startswith(
        kind.folder_prefix + "_"
    ):
        return kind
```

Un dossier `arxiv` n'est ni égal à `arxiv_cscr_x_csai`, ni préfixé par `arxiv_cscr_x_csai_`.
L'import l'ignore donc, avec le journal « folder without a source kind, skipped ». C'est la raison
pour laquelle les bruts existants doivent être déplacés avant le prochain import.

### Les données existantes : une commande, pas du code

L'issue l'impose : pas de code de migration dans K-B. Une commande déplace les bruts et renomme
la clé d'état ; elle est écrite dans la PR. Elle vérifie tout avant de toucher à quoi que ce
soit :

- `${KB_DATA_DIR:?}` : sous zsh, `cd ""` réussit et reste dans le dossier courant (constat du
  relecteur). `:?` arrête la commande si la variable est vide.
- la commande vérifie que `arxiv/` existe, que `arxiv_cscr_x_csai/` n'existe pas, et que la clé
  `arxiv` est présente sans `arxiv_cscr_x_csai` ;
- le fichier d'état est écrit dans un fichier temporaire, puis remplacé par `os.replace`, comme
  le fait `write_file_atomically` dans `raw_store.py`. Le JSON a le même format que
  `save_last_collection_dates` (`indent=2, sort_keys=True`, `raw_store.py:70`) ;
- le `mv` vient en dernier. Si une vérification échoue, rien n'a été déplacé.

## Choix faits et options écartées

| Choix | Retenu parce que | Écarté |
|---|---|---|
| Changer `FOLDER_PREFIX` lui-même | conception décidée dans l'issue ; critère de fin : `"arxiv"` n'est plus le préfixe de dossier dans `arxiv.py` | garder le type `arxiv` et nommer la source `arxiv_cscr_x_csai`, comme `tldr_ai`. Les anciens dossiers resteraient lus et une future catégorie entrerait dans le même type, mais cela contredit la conception décidée |
| Migrer les données par une commande dans la PR | imposé par l'issue ; une migration ne sert qu'une fois | du code de migration dans K-B, qui resterait ensuite comme code mort |
| Laisser dans la base les anciennes lignes `collection` en `automated_watch/arxiv/…` | décision de Sabine (10/10) ; l'issue ne touche pas la base | un `DELETE FROM collection …` après le réimport, hors périmètre |
| Tester par `collect_all_sources` avec un faux `urlopen` | le test passe par le vrai chemin, du nom de la source jusqu'au fichier écrit et à la clé lue ; aucun réseau | tester `ArxivSource.name` seul : cela ne prouve ni le dossier écrit ni la date relue |
| Fixture `arxiv_extract.xml` | extrait d'une vraie collecte (consigne du 10/10) | une réponse fabriquée |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_collection_writes_the_arxiv_raw_under_arxiv_cscr_x_csai` (`tests/sources/test_arxiv.py:100`) | la collecte écrit `raw/automated_watch/arxiv_cscr_x_csai/2026-10-05T093000Z.xml` |
| `test_a_collection_state_keyed_arxiv_cscr_x_csai_restarts_arxiv_from_its_date` (`:113`) | une clé `arxiv_cscr_x_csai` au 30/09 10:05 fait partir la requête de `202609231005`, soit la date moins 7 jours, et non du 1er mai ; la collecte réécrit la date sous la même clé |
| Avant le changement de `FOLDER_PREFIX` : 4 échecs (les 2 tests ci-dessus, `test_arxiv_is_a_source_of_kb_collect`, `test_the_sources_are_collected_in_the_order_of_2026_10_06`) | les tests échouaient bien avant le code |
| Après : `316 passed`, `ruff check`, `ruff format --check`, `mypy --strict` verts | rien d'autre n'est cassé |
| `grep -rn '"arxiv"' src/k_b/sources/arxiv.py` → seule la ligne 218 (`source_code`) | critère de fin de #117 |

## Ce que tu dois pouvoir défendre

1. **Pourquoi une seule ligne de code suffit ?** Le nom est écrit une seule fois (`arxiv.py:59`),
   puis réutilisé partout : `name`, `SOURCE_KINDS`, dossier et clé d'état (`collect.py:42,48,69`).
2. **Que se passe-t-il si on collecte sans avoir lancé la commande ?** La clé
   `arxiv_cscr_x_csai` est absente : la collecte repart du 1er mai 2026, retélécharge tous
   les papiers depuis (488 papiers mesurés au 02/10, `arxiv.py:42-43`, davantage aujourd'hui,
   non mesuré) et les écrit dans le nouveau dossier. Les bruts de `arxiv/` restent sur disque
   mais ne sont plus lus par l'import (`source_contract.py:62-66`).
3. **Pourquoi `source_code` ne change pas ?** C'est l'identité de la source dans la base (clé de
   `source`, règle `arxiv_revision`). Le flux est une autre notion. Le changer obligerait à
   modifier la base.
4. **Pourquoi les tests d'import passaient-ils déjà avec un dossier `arxiv_cscr_x_csai` avant le
   changement ?** Avec l'ancien préfixe `arxiv`, ce dossier commence par `arxiv_` : il était
   rattaché au type arXiv comme un dossier d'instance. Ce sont les deux nouveaux tests qui
   prouvent le changement, pas ces tests-là.
5. **Que reste-t-il dans la base après le réimport ?** Les articles arXiv pointent vers de
   nouvelles lignes `collection` (`import_items.py:32`, `ON CONFLICT … DO UPDATE`). Les anciennes
   lignes restent, sans article (`import_items.py:119`, `DO NOTHING`). C'est laissé en l'état, par
   décision.

## Zones non vérifiées

- La commande de migration a été lancée sur `temp/.knowledge_base/` seulement (sortie dans la PR),
  pas sur le vrai dossier de données.
- Le réimport sur une vraie base après migration n'a pas été lancé. Le comportement décrit à la
  question 5 vient de la lecture du SQL, pas d'une exécution.

## Ce qui reste

- Sortir le code de `database/__init__.py` (#118), puis le schéma (#119).
- Un attribut `flux` en base, et d'autres catégories arXiv : sans issue.
- Les anciennes lignes `collection` d'arXiv : laissées, par décision de Sabine.
