# Une seule liste des sources

- **Date** : 2026-10-06
- **Branche** : `refactor/declare-sources-once`
- **Issue** : #99 (plan ETL, étape 3 : `docs/2026-10-06-plan-etl.md`)
- **Fichiers principaux** : `src/k_b/source.py`, `src/k_b/source_kinds.py`, `src/k_b/raw_items.py`,
  `tests/test_module_dependencies.py`
- **Série** : suit `2026-10-06-ranger-les-conversions.md` (#97) et `2026-10-06-releases-autonomes.md`
  (#98).

## Le pourquoi

Le but est un ETL explicite : E, T et L sont faits de fonctions génériques, et chaque source porte
ce qui lui est propre. Avant cette PR, trois défauts l'empêchaient :

- **Chaque source était déclarée deux fois** : une fois dans la liste de collecte
  (`collect.SOURCES`), une fois dans l'aiguillage qui choisissait un lecteur
  (`raw_items.list_readers_by_source`). Ajouter une source obligeait à toucher les deux.
- **Les modules génériques importaient les sources par leur nom**, et `raw_items.py` contenait
  des réglages propres à CISA et au classement des dépôts les plus étoilés.
- **La lecture dépendait de la collecte** : T trouvait ses lecteurs en parcourant les sources
  suivies. Le brut d'un dépôt ou d'un écosystème retiré de la liste n'avait donc plus de lecteur
  (#87).

## Le comment

### 1. Le contrat commun : `source.py`

`src/k_b/source.py:40-49` :

```python
class SourceKind(NamedTuple):
    """A kind of source, declared once: its raw folders, its instances, its reader.
    ...
    """

    # The name of its raw folders, alone or followed by _ (github_releases_<repository>).
    folder_prefix: str
    sources: tuple[Source, ...]
```

Une **sorte** de source regroupe ce qui est commun à toutes ses instances : le début du nom de ses
dossiers bruts, les instances à collecter (E), et un lecteur (T). Par exemple, les releases forment
une sorte, avec une instance par dépôt suivi. `source.py` porte aussi le `Protocol Source`, que
`collect.py` contenait auparavant, et `SourceReader`, qui vient de `raw_items.py`. Il n'importe
que `items` : c'est un module générique.

### 2. Une seule déclaration : `source_kinds.py`

`src/k_b/source_kinds.py:28-29` :

```python
SOURCE_KINDS = (
    SourceKind(cisa_kev_source.FOLDER_PREFIX, (CisaKevSource(),), cisa_kev.READER),
```

Une sorte par ligne, dans l'ordre de collecte d'avant cette PR. Seul `cli.py` importe ce module.
Il donne la liste à la collecte (`cli.py:108`, `list_sources(SOURCE_KINDS)`) et à l'import
(`cli.py:91`). Les modules génériques la reçoivent **en paramètre** : ils ne savent pas quelles
sources existent. Chaque module de collecte écrit son préfixe une fois, dans `FOLDER_PREFIX`, qui
sert au nom de ses instances et à sa sorte.

### 3. Le lecteur est retrouvé par le nom du dossier brut

`src/k_b/source.py:58-66` (`find_source_kind`) et `src/k_b/raw_items.py:71-77` :

```python
        kind = find_source_kind(source_dir.name, kinds)
        if kind is None:
            logger.info("folder without a source kind, skipped: %s", source_dir.name)
            continue
```

Un dossier appartient à la sorte dont le préfixe est son nom entier (`arxiv`), ou son début suivi
de `_` (`github_releases_someone_untracked`). La liste des sources suivies n'intervient plus :
le brut d'une source retirée est lu. Les deux cas de dossier sauté ont maintenant chacun leur
message : « pas de sorte » et « sorte sans lecteur », comme TLDR jusqu'à #57. La recherche des
fichiers est sortie dans `list_raw_files` (`raw_items.py:64`) : avec elle, `read_raw_items`
dépassait la complexité de 10 que ruff impose au dépôt.

### 4. Le lecteur d'une source est une constante typée

`src/k_b/arxiv_papers.py:145` :

```python
READER: SourceReader[Paper] = SourceReader(read_papers, convert_paper)
```

`SourceReader[EntryT]` (`source.py:29`) est générique : `read_entries` doit produire des `EntryT`,
et `convert` doit les accepter. L'annotation `SourceReader[Paper]` fixe `EntryT`. mypy refuse
alors `SourceReader(read_papers, convert_release)`. Une constante non annotée, écrite directement
dans la `SourceKind`, aurait laissé passer l'erreur : `SourceKind.reader` est typé
`SourceReader[Any]`, et `Any` accepte tout. Le second passage de la conception l'a montré par un
prototype.

Les réglages propres à une source quittent `raw_items.py` pour son module : `read_catalog`
(`cisa_kev.py:99`, le catalogue entier) et `read_ranking` (`github_most_starred.py:101`, la taille
du classement). La collecte les réutilise : la règle n'est écrite qu'une fois.

### 5. Un test garde le sens des dépendances

`tests/test_module_dependencies.py` lit les imports de chaque module avec `ast`, l'analyseur de
syntaxe de Python, sans exécuter le code. Il couvre `import k_b.x`, `from k_b import x`,
`from k_b.x import y` et leurs formes relatives (`from .x import y`), chacune testée
(`:89`). Trois règles :
- aucun module générique n'importe une source ou la composition (`:101`) ;
- aucun module de source n'importe la composition (`:109`) ;
- chaque module du paquet est rangé dans exactement une des trois listes (`:93`). Un nouveau module
  fait donc échouer le test tant qu'il n'est pas classé.

## Choix faits et options écartées

| Choix | Retenu parce que | Écarté |
|---|---|---|
| Lecteur par **sorte**, retrouvé par préfixe | Le brut d'une source retirée reste lisible (#87, plan ETL). | Parcourir les instances suivies : #87 resterait ouvert. |
| `READER` en constante annotée par module | Seule forme que mypy contrôle (prototype vérifié). | `SourceReader(...)` écrit dans `SOURCE_KINDS` : erreur invisible. Une fabrique générique : non plus. |
| Noms explicites `read_catalog`, `read_ranking` | Ils disent ce qu'ils lisent ; l'interface commune est `READER`. | Un `read_entries` par module (plan) : nom vague, et sans utilité une fois `READER` là. |
| `RANKING_SIZE` dans `github_most_starred.py` | Le lecteur en a besoin, et le module de collecte importe déjà le lecteur : pas de cycle. | Le laisser dans `github_most_starred_source.py` : le lecteur importerait le module de collecte. |
| Paramètre nommé `kinds` dans les modules génériques | Le critère de fin veut que seul `cli.py` cite `source_kinds`. | `source_kinds` : plus parlant, mais il faisait échouer ce critère. |
| Critère `lambda raw` au lieu de `lambda` | Décision de Sabine : le tri générique `lambda item:` reste. | Réécrire le tri avec `attrgetter` pour satisfaire un `grep`. |
| `list_raw_files` à part | Complexité ≤ 10 (`code.md`, `C90`). | Ignorer la règle. |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_sources_are_collected_in_the_order_of_2026_10_06` (`tests/test_source_kinds.py:7`) | Les 12 sources sont collectées dans le même ordre qu'avant. |
| `test_each_source_belongs_to_its_own_kind`, `test_no_folder_prefix_covers_another` (`:24`, `:30`) | Aucune ambiguïté de préfixe sur les sources réelles. |
| `test_the_raw_files_of_an_untracked_repository_and_ecosystem_are_read` (`tests/test_raw_items.py:144`) | Le premier cas de #87 est réglé. |
| `test_a_folder_of_no_source_kind_is_skipped_and_logged` (`:133`), et le test TLDR (`:118`) | Les deux messages de dossier sauté sont distincts. |
| Tests de `tests/test_module_dependencies.py`, rouges avant le code (`raw_items` importait les sources) | Le sens des dépendances est contrôlé. |
| Revue de code : deux préfixes égaux n'étaient pas détectés (comparaison par identité), et les imports relatifs n'étaient pas lus ; corrigés, avec un test par forme d'import | Les deux gardes font ce que dit leur nom. |
| Mutant : `arxiv_papers.READER` associé à `convert_release` → `mypy --strict` : `arxiv_papers.py:146: error: Argument 2 to "SourceReader" has incompatible type …` | La garde de typage fonctionne. |
| `grep -rln source_kinds src/k_b` → `cli.py` ; `grep -nE "k_b\.collect\|partial\|lambda raw\|RANKING_SIZE\|last_collected_at=None" src/k_b/raw_items.py` → rien | Les deux `grep` du critère de fin. |
| 301 tests, ruff, format et mypy verts | Rien d'autre n'a cassé. |

## Ce que tu dois pouvoir défendre

1. **Pourquoi une sorte, et pas seulement une liste de sources ?** Parce que T lit des dossiers, pas
   des instances. Un dossier `github_releases_x` doit trouver son lecteur, même si le dépôt `x`
   n'est plus suivi (`source.py:58-66`).
2. **Pourquoi passer `SOURCE_KINDS` en paramètre plutôt que l'importer ?** Pour que les modules
   génériques ne connaissent aucune source. C'est l'injection de dépendances que demande `code.md`
   (« le métier reçoit ses dépendances en paramètre »), et c'est ce que le test de dépendances
   vérifie.
3. **Que se passe-t-il pour un dossier `cisa_kev_old` ?** Il est lu comme du CISA, puisque son nom
   commence par `cisa_kev_`. C'est voulu et écrit dans la docstring de `find_source_kind`.
4. **Pourquoi des constantes `READER` annotées ?** Parce qu'un `NamedTuple` générique ne contrôle
   l'association lecteur-conversion que si son type d'entrée est fixé. Avec `Any`, mypy laisse
   tout passer (question 4 du « comment »).
5. **Comment sait-on que rien n'a changé pour l'utilisateur ?** L'ordre de collecte est figé par un
   test, les tests de la CLI passent sans changer leurs sorties, et les commandes sont les mêmes.

## Zones non vérifiées

- Le test de dépendances analyse les imports écrits ; un import dynamique lui échapperait.
  `grep -rn importlib src/k_b` ne trouve que `importlib.resources` (`database/__init__.py:4`), qui
  lit le fichier du schéma et n'importe aucun module. Aucun test ne le garde.
- Les `# type: ignore[arg-type]` de `tests/test_source.py` ne sont pas contrôlés : mypy ne vérifie
  pas encore les tests (#93).
- Aucune collecte réelle n'a été lancée avec cette branche.

## Ce qui reste

- **Regrouper chaque source en un module, dans `sources/`** (#100). Le test de dépendances passera
  alors de ses listes explicites au paquet.
- **Lire un dossier de pages** (#101), puis TLDR aura son lecteur (#57).
- **#87, deuxième cas** : le classement relu avec la taille courante. Il n'est pas réglé ici, et
  #87 reste ouverte.
