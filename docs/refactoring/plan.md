# Plan de refactorisation de l'ETL

Fait foi pour la cible, les étapes et les décisions de la
refactorisation. Point de départ : docs/refactoring/inventaire.md et
docs/refactoring/orchestration.md.

## 1. Cible

Cette cible remplace celle annoncée dans inventaire.md et
orchestration.md.

```
etl/
  sources/
    <source>/
      extract.py      # interroge la source, rend les octets bruts
      transform.py    # brut -> items (lecteur, conversion)
    # modules partagés entre sources
    github_api.py           # partagé par les sources GitHub
    tracked_repositories.py # la liste des dépôts suivis
  source_kinds.py       # composition : la liste unique des sources
  collected_sources.py  # composition : sources selon l'environnement
  source_contract.py    # le contrat d'une source
  raw_files.py          # vocabulaire partagé entre les stages
  tops.py               # types partagés des classements, partie collecte ;
                        # la partie rendu va dans post/top_sheets.py (étape 8)
  raw_store.py          # zone d'atterrissage : seul accès au brut et à l'état
  raw_purge.py          # rétention : purge du brut, hors des trois stages
  extract.py            # stage 1 : parcourt la liste, contrôle, écrit raw/
  http_download.py      # aide à l'extract : téléchargement commun
  user_agent.py         # aide à l'extract : en-tête HTTP
  transform.py          # stage 2 : relit raw/, appelle chaque transform,
                        #           puis filtre, normalise, rejette
  normalize.py          # étape du transform
  load.py               # stage 3 : une transaction, via database/writers
  import_log.py         # aide au load : journal d'import (audit)
  pipeline.py           # parcours collecte (1) et import (2 + 3)
post/                   # post-traitement, hors de l'ETL
```

## 2. Règles de la cible, et pourquoi

1. Pas de load.py par source. Le chargement est organisé par type
   d'item (database/writers/), pas par source ; plusieurs sources
   produisent le même type ; les classements (most_starred, most_forked)
   ne vont pas en base ; les tendances de GH Archive, si (table trend,
   trend_writer). Les règles propres à une source (retrait CISA, retrait
   Zotero) restent dans etl/load.py.
2. Les modules du pipeline (les stages et leurs aides) n'importent ni
   les sources ni la composition : ils reçoivent la liste des sources en
   paramètre. Seule la composition (cli.py, commands/, source_kinds.py,
   collected_sources.py) nomme les sources. Déjà vérifié par
   test_no_module_of_the_pipeline_imports_the_sources_or_the_composition.
3. Le extract.py d'une source n'importe jamais son transform.py. Le
   contrôle de la règle 1 de conventions.md (une source échoue si toutes
   ses entrées sont invalides) est fait par etl/extract.py, qui appelle
   le lecteur de la source via la liste des sources.
4. extract, transform et load ne s'importent pas entre eux ; seul
   pipeline.py les enchaîne. Ce qu'ils partagent est dans raw_files.py.
5. Le pipeline garde deux parcours, qui communiquent par raw/ :
   kb collect (stage 1) et kb import (stages 2 et 3) tournent séparément.
   pipeline.py fournit aussi leur enchaînement, que le job appelle.
6. etl n'importe jamais post (déjà en vigueur, tests/architecture/).

Chaque règle n'existe vraiment que lorsqu'un test de tests/architecture/
la vérifie.

## 3. Correspondance avec un ETL classique

- Extract : collecte incrémentale (état de collecte), brut horodaté et
  immuable dans raw/ (zone d'atterrissage), contrôle à l'ingestion.
- Transform : part du brut ; parsing par source, puis validation,
  filtrage, normalisation et rejets génériques ; fonctions pures.
- Load : transaction tout ou rien, registre des fichiers chargés
  (idempotence), journal d'import (audit), SQL isolé dans database/.
- Orchestration séparée des stages (pipeline.py, commands/),
  post-traitement hors de l'ETL, rétention à part (raw_purge.py).

Points défendables :
- Un paquet par source : c'est le modèle des connecteurs (Singer : un
  tap par source ; Airbyte : un connecteur par source ; dbt : un modèle
  de staging par source), avec les stages explicites dans les fichiers.
- Un load unique : on charge par destination et par table, pas par
  source.
- Le contrôle pendant la collecte : principe de fail fast, contrôle de
  qualité à l'ingestion, sans rien retirer du brut.
- Deux parcours séparés par raw/ : découplage ingestion / traitement,
  l'import se rejoue sans réinterroger les sources.
- Jobs : la décision 3 du journal ADR (POC du 25/10) conçoit la
  collecte et l'import comme des jobs ; en ligne, un job ACA déclenché
  par cron les enchaîne.
- La déduplication est faite par la base (contraintes d'unicité),
  décision consignée dans le journal.
- pipeline.py applique code.md : « un parcours s'écrit comme une suite
  d'étapes nommées, chacune dans son module ».

## 4. Étapes

| # | Étape | Statut |
|---|---|---|
| 0 | Sortir le post-traitement de etl vers post/, règle etl -> post | fait, tag etl-post-separated |
| 1 | Créer etl/raw_files.py (types partagés, déplacement mécanique) ; ajouter le module à ETL_PIPELINE_MODULES (tests/architecture/module_imports.py) | fait (à commiter) |
| 2 | Filtre des releases non suivies et normalize_item dans le transform, avant le load | à faire |
| 3 | Décision de conception d'abord : comment le lecteur des tendances parvient à transform.py par la composition (second champ de SourceKind, ou contrat de lecteur de classement). Relevé en lecture seule, puis choix de Sabine. Lecture des tendances de gh_archive appelée par transform.py, via RawStore, sans accès direct au brut ; gh_archive.py sort de la liste de la règle 3 de poc.md | à faire |
| 4 | Créer pipeline.py ; les commandes passent par lui ; ajouter le module à ETL_PIPELINE_MODULES (tests/architecture/module_imports.py) | à faire |
| 5 | Règle d'architecture : extract, transform, load ne s'importent pas entre eux | à faire |
| 6 | Pilote : la source Zotero en paquet extract.py / transform.py | à faire |
| 7 | Si le pilote est validé : généraliser aux autres sources, une par commit | à décider |
| 8 | Séparer dans Top ce qui relève de la collecte et du rendu | à faire |

À vérifier à part : la double normalisation des clips (clipping.py),
peut-être voulue ; les tests qui s'importent entre eux (vers conftest.py).

## 5. Décisions en vigueur

- « Un module par source » (2026-10-06) reste en vigueur jusqu'à la
  validation du pilote (étape 6). Elle sera alors remplacée par une
  entrée d'ADR.
- import_items garde la transaction et le journal (règle 5 de
  conventions.md).
- commit_with_log reste intact : l'ordre journal puis commit est un
  invariant.
- join_writings et list_files_in_collection_order restent dans le load :
  fonctions pures, mais utilitaires du load, pas du transform.

## 6. Méthode

- Une étape par session, sur la branche refactoring/etl, avec le cycle
  allégé décrit dans CLAUDE.md.
- Un relevé en lecture seule avant toute décision de conception.
- Les déplacements mécaniques sont séparés des changements de
  comportement, dans des commits distincts.
- L'agent s'arrête au moindre conflit et le signale au lieu de le
  contourner. Sabine relit les diffs et commite.
- Les documents historiques (journaling, entrées d'ADR déjà écrites,
  inventaire, orchestration) ne sont jamais réécrits.

## 7. Règles à amender

L'agent rédige le texte exact de chaque amendement dans son compte
rendu ; Sabine l'applique dans .claude/ et le commite avec l'étape.
conventions.md prime sur poc.md.

conventions.md :

- Règle 1 : le chemin de reject, s'il quitte transform.py (étape 1) ;
  l'exception des classements, à préserver dans le contrôle à la
  collecte (étape 6).
- Règle 4 : le modèle Pydantic d'une source dans
  etl/sources/<source>/transform.py (étape 6).
- Règle 5 : la liste des modules d'etl (étape 4) ; le chemin des
  requêtes Zotero et GH Archive, et les --exclude de sa commande de
  vérification (étape 6).

poc.md :

- Règles 3 et 4 : les chemins de zotero.py et de gh_archive.py dans
  les références de départ (étape 6).
- Règle 5 : le chemin de describe_validation_error (étape 6).

## 8. Points ouverts

Chacun relève d'une étape future, qui le tranche : aucun ne bloque le
plan ni les étapes d'avant.

- Étape 3 : SourceReader est typé pour des items (read_entries rend des
  entrées, convert rend un Item) et ne peut pas porter read_trends ;
  SourceKind.reader vaut None pour GH Archive, et son commentaire dit
  pourquoi (source_contract.py:105-107). La composition n'a donc
  aujourd'hui aucun emplacement pour le lecteur des tendances.
- Étape 6 : le contrôle à la collecte passe de la source à
  etl/extract.py, mais une sorte sans lecteur (reader None : les deux
  classements GitHub, GH Archive) n'a rien à contrôler, et l'exception
  des classements de la règle 1 de conventions.md est aujourd'hui portée
  par la source elle-même (check_not_empty, dans cisa_kev.py et
  zotero.py). Le contrôle générique doit traiter les deux cas.
- Étape 8 : Top porte les mots de sa fiche (count_heading, subject) et
  son lecteur (read_entries), et c'est la composition qui les fournit
  (TOPS, source_kinds.py) ; TopEntry est lui-même décrit « as its sheet
  shows it ». Séparer collecte et rendu touche donc etl/tops.py, la
  composition et post/top_sheets.py.
