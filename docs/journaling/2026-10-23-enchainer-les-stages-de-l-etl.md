# Enchaîner les stages de l'ETL, et rendre à chaque module son niveau

- **Date** : 2026-10-23
- **Branche** : `refactoring/etl`
- **Issue** : aucune ; refactorisation conduite directement par Sabine, sur
  [le plan](../refactoring/plan.md), qui fait foi pour la cible et les étapes
- **Fichiers principaux** : `src/k_b/etl/pipeline.py`, `src/k_b/etl/raw_reading.py`,
  `src/k_b/etl/rejections.py` (nouveaux), `src/k_b/etl/transform.py`, `src/k_b/etl/load.py`,
  `src/k_b/etl/raw_files.py`, `src/k_b/commands/import_command.py`,
  `src/k_b/commands/collect_command.py`, `tests/architecture/test_layers.py`,
  `tests/architecture/module_imports.py`
- **Série** : étapes 2 à 5 de la refactorisation de l'ETL, après
  [l'étape 0](2026-10-22-sortir-le-post-traitement-de-etl.md) (paquet `post/`) et l'étape 1
  (`etl/raw_files.py`).

Commits couverts, dans l'ordre : `4609d7a`, `6a46726`, `fdb2b1f` (étape 2), `b0d3b65` et `8b9a2bb`
(étape 3), `679f548` (étape 4), `b6bbadf`, `b0b9d6e` (relecture du brut et rejets), `b828d0f`
(étape 5) et `3a191f8` (vocabulaire). Les décisions sont au
[journal ADR](../ADR/journal-decisions-projet.md), 2026-10-22 (« Tendances : un lecteur porté par
la sorte ») et 2026-10-23 (« ETL : `pipeline.py` enchaîne les stages »).

## Le pourquoi

Le relevé d'orchestration du 22/10 a mis un mot sur un malaise : **l'ETL avait les bonnes étapes,
mais pas aux bons endroits.**

Trois symptômes, mesurés et non supposés :

1. **Le load décidait ce que l'import contient.** `normalize_item` (étape 3 de
   [specs-collecte.md](../specs-collecte.md)) et le filtre des releases hors liste tournaient
   dans `load.write_items_file`, c'est-à-dire pendant l'étape 4, entre l'enregistrement du fichier
   et l'écriture des items. Un module qui écrit en base décidait quels items existent.
2. **Une source refaisait le travail du transform.** `read_trend_files` vivait dans
   `etl/sources/gh_archive.py` : il listait `raw/`, lisait les octets et construisait les objets —
   le miroir de `transform.read_raw_items`, écrit dans une source, qui importait pour cela sept
   noms de `transform.py`.
3. **L'orchestration de `kb import` était à deux endroits**, la commande et `load.import_items`,
   avec la frontière au milieu d'un parcours : le registre lu dans `load.py`, le brut dans
   `transform.py`, et la commande qui mettait les trois dans l'ordre.

Aucun de ces trois n'est un bug : les tests passaient, la base était juste. Ce sont des défauts de
**lisibilité et de couches** — et ils coûtaient cher pour la suite, parce que la cible du 08/11
(brut dans Azure Blob Storage, conteneurs, base PostgreSQL) demande de pouvoir changer une couche
sans toucher aux autres.

## Le comment

### 1. Étape 2 — chaque étape dans sa phase

Deux déplacements, un commit chacun, sans changement de comportement :

| Ce qui bouge | D'où | Vers |
|---|---|---|
| le filtre des releases hors liste (`reject_untracked_releases`) | `load.write_items_file` | `transform.read_raw_items` |
| la normalisation (`normalize_item` sur chaque item) | `load.write_items_file` | `transform.normalize_items` |

L'ordre compte et il est écrit dans le code : **le filtre d'abord**, qui lit chaque item tel que sa
source l'a donné, **la normalisation ensuite**. Et la normalisation reste **hors** de la lecture
d'une page : une `ValidationError` levée par la seconde validation de `normalize_item` doit arrêter
tout l'import, pas rejeter un item — un item refuse d'avance ce que la normalisation casserait
(`check_url_can_be_normalized`, `items.py`).

Un détail décidé plutôt que subi : une release écartée **ne compte pas** dans `rejection_count`.
Ce compteur sert au load pour savoir si un catalogue d'état est complet (une entrée rejetée ⇒ on ne
retire rien) ; or un fichier de releases a bien été lu en entier, et aucun catalogue d'état ne
contient de release.

### 2. Étape 3 — le lecteur des tendances arrive par la composition

`transform.py` est un module du pipeline : un test d'architecture lui **interdit** d'importer une
source (`test_no_module_of_the_pipeline_imports_the_sources_or_the_composition`). Le lecteur des
tendances devait donc arriver par paramètre. La sorte d'une source (`SourceKind`) est déjà
l'endroit où une source dit comment lire son dossier brut : elle porte désormais un second lecteur,
`trend_reader`, à `None` par défaut — les vingt constructions de `SourceKind` du dépôt restent
intactes, seule la ligne de GH Archive change.

Résultat : **un seul parcours de `raw/`** rend les deux lectures. `list_collections` parcourait
déjà tous les dossiers et trouvait la sorte de chacun, y compris celle de GH Archive, qu'il
journalisait et sautait ; il classe maintenant au lieu de sauter, et `read_raw_files` rend
`RawReadings(items, trends)`.

### 3. Étape 4 — `pipeline.py`, porte unique des deux parcours

```python
def collect(sources, data_dir, now) -> CollectionOutcome          # stage 1
def import_raw_files(data_dir, kinds, tracked_repositories, imported_at) -> ImportOutcome
                                                                  # stages 2 puis 3
def purge_superseded_raw(data_dir, latest_only_folder_keys) -> int # rétention, à part
```

Le partage est net : **`pipeline.py` tient l'ordre des étapes**, la commande garde l'environnement,
l'horloge, le résumé affiché, les codes de sortie et SIGTERM (posé une fois pour toutes dans
`cli.py`). `pipeline.py` ne lit aucun réglage, n'affiche rien, ne rend aucun code.

Trois contraintes **imposées par les tests et les couches**, pas choisies :

- `SOURCE_KINDS`, `TRACKED_REPOSITORIES` et `LATEST_ONLY_FOLDER_KEYS` **nomment des sources** :
  ils restent dans la commande et entrent par paramètre, sinon le test d'architecture ci-dessus
  échoue dès que `pipeline.py` entre dans `ETL_PIPELINE_MODULES`.
- `describe_os_error` vit dans `commands/run_log.py`, et `etl` n'importe jamais `commands` : la
  ligne de journal de la purge reste donc dans la commande.
- `__all__` fait de `pipeline.py` une **porte**, comme `database/writing.py` l'est pour les
  écrivains : `commands/` n'importe plus aucun des trois stages ni `raw_purge`.

Effet mesurable, et c'était un point ouvert du plan : la liste des dépôts suivis n'entre plus
**qu'une fois** dans l'import, et `pipeline.py` la passe au filtre du transform comme à la table de
la base. Les deux ne peuvent plus différer.

La purge, elle, reste une étape **appelée par la commande, après l'affichage du résumé**. La
rétention n'est pas un stage (plan, §1), et surtout : un import qui a commité doit dire ce qu'il a
écrit, même si la purge qui suit échoue. Un test le fige
(`test_a_failed_purge_leaves_the_summary_of_the_import_it_committed`).

### 4. L'enchaînement des deux parcours : hors périmètre, et pourquoi

Le plan annonçait que `pipeline.py` fournirait aussi l'enchaînement, « que le job appelle ». Il ne
le fournit pas, et le plan est amendé. Trois raisons :

- **aucun appelant** : `code.md` refuse l'abstraction sans second usage et la couche « pour plus
  tard » ;
- **l'enchaînement en ligne n'est pas un appel Python** : un job ACA enchaîne des exécutions de
  conteneur ; aujourd'hui c'est la ligne du README, `kb collect ; kb import ; kb write-tops` ;
- **il demanderait une décision que personne n'a prise** : un seul code de sortie pour deux
  parcours, alors que le README garantit qu'« chaque étape tourne même si la précédente a échoué en
  partie […] et garde son propre code de sortie ».

À rouvrir au temps 2 (conteneurs), avec la question du code de sortie posée à Sabine.

### 5. `rejections.py` et `raw_reading.py` — un blocage qui a rendu service

Après l'étape 4, `transform.py` faisait 334 lignes et mélangeait **quatre niveaux** : le parcours,
les étapes pures (filtre, normalisation), la relecture du brut (lister `raw/`, ouvrir une page), et
un `read_raw_trends` qui faisait à la fois parcours et détail. Ce n'est plus une table des matières
(`code.md`).

Sortir la relecture du brut dans `etl/raw_reading.py` a buté sur une dépendance : les fonctions
déplacées appellent `reject`, qui vivait dans `transform.py` — or `transform.py` importe désormais
`raw_reading.py`. Garder `reject` là où il était formait un **cycle d'imports**. La session s'est
arrêtée et a posé la question (règle de la branche : s'arrêter au moindre conflit, ne pas le
contourner). Décision de Sabine : créer tout de suite `etl/rejections.py`, la destination que le
plan prévoyait déjà, plutôt que de déplacer deux fois une fonction qui journalise.

```
etl/rejections.py   20 lignes : reject, le chemin unique d'un rejet
etl/raw_reading.py 196 lignes : lister raw/, lire une collecte, une page, un fichier de tendances
etl/transform.py   159 lignes : deux parcours, trois étapes pures  (334 avant)
```

Le type `Rejection` **ne suit pas** : il reste dans `raw_files.py`, le vocabulaire pur ; `reject`,
qui journalise, n'y a pas sa place. Et `load.py` appelle `reject` lui aussi, ce qui interdisait de
le ranger dans le module de relecture du brut.

Deux bénéfices qui n'étaient pas le but :

- `load.py:63` était le **seul** import de `transform` par `load` : après le déplacement, les trois
  stages ne s'importent plus entre eux — la règle de l'étape 5 était vraie avant d'être testée ;
- `transform.py` **sort** de la liste des fichiers qui touchent le brut (`poc.md`, règle 3), où
  `raw_reading.py` le remplace : l'étape 3 bis (brut lu par `RawStore`, prérequis d'Azure Blob
  Storage) ne réécrira plus qu'un seul module.

La séparation de `read_raw_trends` est le seul changement non mécanique de ce commit : le parcours
reste dans `transform.py`, écrit comme celui des items (une compréhension filtrée, puis une
jointure), et la lecture d'**un** fichier part dans `read_trend_file`. Les cinq autres fonctions
sont déplacées telles quelles, vérifié bloc par bloc contre `HEAD`.

### 6. Étape 5 — la règle tenue par un test

```python
ETL_STAGE_MODULES = {"etl.extract", "etl.transform", "etl.load"}


def list_imports_of_another_stage(imported: set[str], stage: str) -> set[str]:
    return {name for name in imported if reaches(name, ETL_STAGE_MODULES - {stage})}
```

Le détecteur **retire du jeu l'étape qui interroge** : contrairement aux règles voisines, la liste
interdite dépend de qui demande. `reaches` refuse aussi le paquet qui donne accès
(`from k_b import etl`), et `pipeline.py`, qui n'est pas un stage, garde le droit d'importer les
trois. Un test sur les fichiers réels, un test paramétré de neuf formes d'import, et une
contre-épreuve (table « Preuve »).

### 7. Le vocabulaire : « trend » pour GH Archive, « ranking » pour les tops

Le mot « ranking » désignait deux choses dans `etl/` : les classements des tops GitHub, et les
tendances de GH Archive, que le code appelle « trend » partout ailleurs (`TrendFile`,
`TrendReading`, `TrendReader`, `read_trend_file`). Vingt-six docstrings et commentaires ont été
corrigés ; rien qui concerne les tops n'a bougé. **Aucun code exécutable** : vérifié en comparant
l'AST de chaque fichier, docstrings retirées, à celui de `HEAD`.

Une occurrence reste, assumée : le motif de rejet `"ranking refused by the base"` (`load.py:324`)
est un **message**, lu par un test et écrit au journal d'import. Le changer touche le code, le test
et le journal : c'est un point « hors étapes » du plan.

## Choix faits et options écartées

- **`pipeline.py` orchestre** (retenu) ; écartés : l'orchestration dans `commands/` (elle
  contredit la règle 5 de `conventions.md` sur deux points, et aucun test d'architecture ne la
  tiendrait) ; trois paquets `etl/extract/`, `etl/transform/`, `etl/load/` (le diff le plus large,
  pour des paquets de un ou deux modules).
- **La boucle des sources reste dans `extract.py`** (retenu, cible du plan §1) : `pipeline.collect`
  ne fait que nommer le parcours ; écarté : remonter la boucle dans `pipeline.py`.
- **La purge en étape à part** (retenu, Sabine) : zéro changement de comportement ; écartée : la
  purge dans `import_raw_files`, son erreur portée par `ImportOutcome` — l'invariant « la purge ne
  tourne qu'après le commit » devenait structurel, mais un SIGTERM pendant la purge faisait perdre
  le résumé.
- **`etl/rejections.py` tout de suite** (retenu, Sabine) ; écarté : `reject` dans
  `raw_reading.py`, puis un second déplacement à l'étape 5 (le « où » du journal aurait changé deux
  fois).
- **`join_readings` dans `raw_files.py`**, à côté de `RawReading` (retenu, Sabine) ; écarté :
  dans `raw_reading.py` avec les fonctions qui l'appellent.
- **`read_trend_file`** (retenu, Sabine) ; écarté : `read_ranking`, qui existait déjà trois fois
  pour les tops GitHub.
- **L'enchaînement hors périmètre** (retenu, Sabine) ; écarté : `collect_then_import` et une
  commande `kb run` maintenant.
- **Le vocabulaire corrigé dans les docstrings seulement** (retenu, Sabine) ; écarté : aligner
  aussi le message de rejet (code, test et journal).

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `pytest -q` → 2277 passés avant l'étape 4, **2288** après l'étape 5 | aucun test perdu ; +1 (purge en échec) et +10 (la règle des stages : 1 test réel et 9 cas) |
| `pytest tests/architecture -q` → 102 puis **112** | les listes de modules suivent : `etl.pipeline`, `etl.rejections`, `etl.raw_reading` |
| `grep -nE "etl\.(extract\|transform\|load\|normalize\|import_log\|raw_purge)" src/k_b/commands` → rien | les commandes passent par `pipeline.py` |
| `grep -nE "from k_b\.etl\.(extract\|transform\|load) import" src/k_b/etl/{extract,transform,load}.py` → rien | les trois stages ne s'importent plus entre eux |
| `from k_b.etl.transform import reject` remis dans `etl/load.py` → `test_no_stage_of_the_etl_imports_another_stage` **FAILED**, nommant le fichier et `etl.transform` ; puis retiré, fichier vérifié identique | la règle mord |
| liste du `grep -rl` de la règle 3 de `poc.md` : `etl/transform.py` **sorti**, `etl/raw_reading.py` entré, toujours 10 fichiers | un seul fichier du transform touche encore le brut, prêt pour 3 bis |
| cinq blocs déplacés comparés caractère par caractère à `HEAD` → identiques | le déplacement est mécanique |
| AST des 8 fichiers du commit de vocabulaire, docstrings retirées, comparé à `HEAD` → identique | aucun code exécutable changé |
| `ruff check --no-cache`, `ruff format --check`, `mypy --strict` | contrôles du dépôt verts |

## Ce que tu dois pouvoir défendre

1. **Pourquoi `pipeline.py`, alors que la commande marchait déjà ?** Parce qu'un parcours doit se
   lire d'un seul endroit. L'ordre « registre → transform → load » était écrit dans la commande, et
   la transaction dans `load.py` : la frontière passait au milieu du parcours. Maintenant
   `pipeline.py` tient l'ordre, `load.py` tient la transaction et le journal, la commande tient
   l'environnement, l'affichage et les codes de sortie. Chacun une seule chose.
2. **Qu'est-ce qui garantit que la liste des dépôts suivis est la même pour le filtre et pour la
   base ?** `import_raw_files` la prend en **un** paramètre et la passe aux deux étapes. Avant,
   la commande la passait deux fois : deux appels, donc deux listes possibles. C'était un point
   ouvert du plan ; il est clos par construction, pas par vigilance.
3. **Pourquoi la purge n'est-elle pas dans le parcours d'import ?** Parce que la rétention n'est pas
   un stage, et surtout parce que le résumé doit sortir avant elle : un import qui a commité doit
   dire ce qu'il a écrit même si la suppression des bruts périmés échoue. Mettre la purge dans le
   parcours rendait l'invariant « après le commit » structurel, au prix du résumé perdu si un
   SIGTERM tombe pendant la purge. Le choix est donc : garantie d'affichage > garantie structurelle,
   parce que l'ordre est déjà protégé par un test.
4. **Pourquoi ne pas avoir écrit l'enchaînement des deux parcours, que le plan annonçait ?** Parce
   qu'aucun appelant ne l'appellerait : en local c'est `kb collect ; kb import`, en ligne ce sera un
   job ACA qui enchaîne des conteneurs. Et parce qu'il faudrait décider ce qu'un seul code de sortie
   veut dire pour deux parcours, alors que le README garantit un code par étape. Écrire du code pour
   un besoin futur mal défini, c'est exactement ce que `code.md` interdit.
5. **Pourquoi un module entier pour une fonction de trois lignes (`reject`) ?** Parce que c'est le
   chemin unique des rejets de la règle 1 de `conventions.md`, appelé par le transform, par le
   filtre des releases et par le load. Il ne pouvait pas rester dans `transform.py` (cycle avec
   `raw_reading.py`), ni aller dans `raw_files.py` (il journalise, ce vocabulaire est pur), ni dans
   `raw_reading.py` (le load aurait importé le module de relecture du brut). Un module de 20 lignes
   qui tient un invariant vaut mieux qu'un import qui remonte le courant.
6. **Qu'est-ce que `raw_reading.py` fait gagner, concrètement ?** Deux choses mesurables :
   `transform.py` passe de 334 à 159 lignes et ne contient plus qu'un niveau de détail ; et un seul
   fichier touche encore le brut, ce qui réduit l'étape 3 bis (passage à `RawStore`, prérequis
   d'Azure Blob Storage) à un module au lieu de deux moitiés de module.
7. **Qu'est-ce qui empêche quelqu'un de recoupler les stages ?**
   `test_no_stage_of_the_etl_imports_another_stage`, qui lit les imports par `ast`, toutes formes
   comprises, et nomme le fichier fautif. La contre-épreuve le prouve : l'import retiré, remis en
   place, fait échouer le test.
8. **Les noms de logger ont changé : est-ce acceptable ?** Oui, et c'est même plus juste. Un rejet
   se journalise sous `k_b.etl.rejections` et non plus sous `k_b.etl.transform` — y compris les
   rejets émis pendant l'écriture en base, qui annonçaient un transform qui ne tournait pas. La
   règle 3 de `conventions.md` demande le « où » exact. Le texte des lignes, lui, n'a pas changé, et
   aucun test ne lit le nom du logger (vérifié avant de décider).
9. **Qu'est-ce qui a changé pour l'utilisatrice ?** Rien, sauf le nom du logger de ces lignes :
   mêmes items, mêmes rejets, mêmes compteurs, mêmes codes de sortie, même journal d'import, mêmes
   messages. C'est le critère d'une refactorisation : si le comportement avait changé, il faudrait
   une décision, pas un déplacement.
10. **Pourquoi « trend » et pas « ranking » ?** Parce que « ranking » désigne déjà les classements
    des tops GitHub, qui ne vont jamais en base, alors que les tendances de GH Archive vont dans la
    table `trend`. Un même mot pour deux choses dans le même paquet, c'est un nom qui oblige à aller
    voir sa définition — ce que `code.md` refuse en premier.

## Zones non vérifiées

- **Aucune commande `kb` réelle n'a été lancée** : ni collecte, ni import sur un vrai dossier de
  données. La preuve repose sur la suite de tests, qui passe par `cli.main(["collect"])` et
  `cli.main(["import"])` de bout en bout sur `tmp_path`.
- **Les tests de bout en bout (`-m e2e`) n'ont pas été rejoués** : ils interrogent de vraies
  sources, et celui de `gh_archive` lance une requête BigQuery réelle.
- **Un test échoue dans l'environnement de la session**,
  `test_serve_ai_stops_on_sigterm_with_the_code_of_a_process_stopped_by_it` : il lie un port local
  (`socket.bind`), que le bac à sable de l'outil refuse. Sans rapport avec ces commits, identique
  avant et après.
- **`uv run` n'a pas pu servir** (cache `uv` hors du bac à sable) : les contrôles ont tourné par
  les exécutables du `.venv` du dépôt, identiques à ceux de la CI.

## Ce qui reste

- **Étape 3 bis** : `raw_reading.py` lit le brut par `RawStore`, par clés et non par `Path` —
  après le jalon, avant la mise en ligne du 08/11.
- **Étape 6** : le pilote Zotero en paquet `extract.py` / `transform.py`, avec la question du
  contrôle à la collecte pour une sorte sans aucun lecteur.
- **Étape 8** : séparer dans `Top` ce qui relève de la collecte et du rendu.
- **Hors étapes** : le motif `"ranking refused by the base"` ; `release_writer.py:71-75`, qui
  dépaquette `fetchone()` sans garde ; les six fichiers entrés dans la liste de la règle 3 de
  `poc.md` sans justification écrite.
