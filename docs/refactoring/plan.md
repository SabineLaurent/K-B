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
  raw_files.py          # vocabulaire partagé entre les stages, et les
                        # jointures de leurs lectures
  rejections.py         # reject : le chemin unique d'un rejet, de l'étape qui
                        # le trouve au journal d'import
  tops.py               # types partagés des classements, partie collecte ;
                        # la partie rendu va dans post/top_sheets.py (étape 8)
  raw_store.py          # zone d'atterrissage : seul accès au brut et à l'état
  (raw_purge.py)        # rétention : sortie de l'ETL le 2026-11-04, dans
                        # src/k_b/purge/catalogs.py (décision de Sabine, #83)
  extract.py            # stage 1 : parcourt la liste, contrôle, écrit raw/
  http_download.py      # aide à l'extract : téléchargement commun
  user_agent.py         # aide à l'extract : en-tête HTTP
  transform.py          # stage 2 : parcours des items et des tendances,
                        #           puis filtre, normalise, rejette
  raw_reading.py        # aide au transform : seul à lister raw/ et à lire ses
                        # octets (une collecte, une page, un fichier de tendances)
  normalize.py          # étape du transform
  load.py               # stage 3 : une transaction, via database/writers
  file_writing.py       # aide au load : écrire en base ce qu'un fichier lu
                        # porte, par l'écrivain de chaque sorte
  withdrawals.py        # aide au load : règles de retrait CISA et Zotero
  import_log.py         # aide au load : journal d'import (audit)
  pipeline.py           # parcours collecte (1) et import (2 + 3) ; porte
                        # unique des deux parcours pour commands/
post/                   # post-traitement, hors de l'ETL
```

## 2. Règles de la cible, et pourquoi

1. Pas de load.py par source. Le chargement est organisé par type
   d'item (database/writers/), pas par source ; plusieurs sources
   produisent le même type ; les classements (most_starred, most_forked)
   ne vont pas en base ; les tendances de GH Archive, si (table trend,
   trend_writer). Les règles propres à une source (retrait CISA, retrait
   Zotero) restent dans le stage de chargement, jamais dans la source :
   elles sont dans etl/withdrawals.py (chantier 11).
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
   pipeline.py nomme les deux parcours et en est la porte unique pour
   commands/ ; leur enchaînement reste la suite de commandes
   (kb collect ; kb import, documentation/utilisation.md) tant qu'aucun job en conteneur ne
   l'appelle.
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
  post-traitement hors de l'ETL, rétention hors de l'ETL (src/k_b/purge/, depuis le 2026-11-04).

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
| 1 | Créer etl/raw_files.py (types partagés, déplacement mécanique) ; ajouter le module à ETL_PIPELINE_MODULES (tests/architecture/module_imports.py) | fait |
| 2 | Filtre des releases non suivies et normalize_item dans le transform, avant le load | fait |
| 3 | Décision de conception d'abord : comment le lecteur des tendances parvient à transform.py par la composition (second champ de SourceKind, ou contrat de lecteur de classement). Relevé en lecture seule, puis choix de Sabine. Lecture des tendances de gh_archive appelée par transform.py, par le lecteur que porte sa sorte, sans accès direct au brut ; gh_archive.py sort de la liste de la règle 3 de poc.md | fait |
| 3 bis | Tout raw_reading.py lit le brut via RawStore, prérequis du passage du brut à Azure Blob Storage (règle 3 de poc.md) ; raw_reading.py sort alors de la liste de la règle 3 | à faire, après le jalon des étapes 4 et 5, avant la mise en ligne du 08/11 |
| 4 | Créer pipeline.py ; les commandes passent par lui ; ajouter le module à ETL_PIPELINE_MODULES (tests/architecture/module_imports.py) | fait (purge en étape à part ; raw_reading.py sort la relecture du brut de transform.py) |
| 5 | Règle d'architecture : extract, transform, load ne s'importent pas entre eux | fait (reject dans rejections.py, puis test_no_stage_of_the_etl_imports_another_stage) |
| 6 | Pilote : la source Zotero en paquet extract.py / transform.py | à faire |
| 7 | Si le pilote est validé : généraliser aux autres sources, une par commit | à décider |
| 8 | Séparer dans Top ce qui relève de la collecte et du rendu | à faire |
| 9 | Réduire les docstrings longues et les commentaires qui décrivent d'autres modules (décision de l'utilisatrice du 2026-10-24) | docstrings faites (#300) ; commentaires à faire |

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

- Une étape par branche et par PR vers main, selon le cycle de
  .claude/rules/methode.md (issue, tests d'abord, revue, note par
  /note-pedago-ls, ADR par /adr-ls) ; les étapes restantes de la partie 4
  y restent tenues.
- Un relevé en lecture seule avant toute décision de conception.
- Les déplacements mécaniques sont séparés des changements de
  comportement, dans des commits distincts.
- L'agent s'arrête au moindre conflit et le signale au lieu de le
  contourner. L'utilisatrice relit chaque PR et la fusionne.
- Les documents historiques (journaling, entrées d'ADR déjà écrites,
  inventaire, orchestration) ne sont jamais réécrits.

## 7. Règles à amender

L'agent rédige le texte exact de chaque amendement dans son compte
rendu ; Sabine l'applique dans .claude/ et le commite avec l'étape.
conventions.md prime sur poc.md.

conventions.md :

- Règle 1 : le chemin de reject, qui a quitté transform.py pour
  etl/rejections.py (étape 5, texte rédigé) ; l'exception des
  classements, à préserver dans le contrôle à la collecte (étape 6).
- Règle 4 : le modèle Pydantic d'une source dans
  etl/sources/<source>/transform.py (étape 6).
- Règle 5 : la liste des modules d'etl, et pipeline.py comme porte des
  deux parcours (étape 4, texte rédigé) ; le chemin des requêtes Zotero
  et GH Archive, et les --exclude de sa commande de vérification
  (étape 6).

poc.md :

- Règle 3 : gh_archive.py hors de la liste des fichiers qui touchent le
  brut (étape 3) ; transform.py hors de cette liste, remplacé par
  raw_reading.py (étape 4, texte rédigé ; la lecture par RawStore reste
  l'étape 3 bis) ; les chemins de zotero.py dans les références de
  départ (étape 6).
- Règle 4 : son contrôle ne cite que etl/raw_store.py et
  etl/sources/zotero.py ; seul le chemin de zotero.py change (étape 6).
- Règle 5 : le numéro de ligne de describe_validation_error, et la
  citation des lignes de read_page, qui se périment à chaque
  changement de leur fichier : remplacés par le nom des fonctions
  (étape 3) ; le chemin de read_page, passé dans raw_reading.py
  (étape 4, texte rédigé) ; le chemin de describe_validation_error
  (étape 6).

## 8. Points ouverts

Chacun relève d'une étape future, qui le tranche : aucun ne bloque le
plan ni les étapes d'avant.

Réglés par les étapes 4 et 5 : la liste des dépôts suivis, que
pipeline.import_raw_files prend une seule fois et passe au filtre du
transform comme à la table de la base ; reject, sorti dans
etl/rejections.py, le type Rejection restant dans raw_files.py
(vocabulaire pur, décision du 2026-10-23) ; le nom du logger, vérifié,
qu'aucun test ne lit.

- Étape 6 : le contrôle à la collecte passe de la source à
  etl/extract.py, mais une sorte sans aucun lecteur (reader et
  trend_reader None : les deux classements GitHub) n'a rien à contrôler,
  et l'exception des classements de la règle 1 de conventions.md est
  aujourd'hui portée par la source elle-même (check_not_empty, dans
  cisa_kev.py et zotero.py). Le contrôle générique doit traiter les deux
  cas.
- Étape 8 : Top porte les mots de sa fiche (count_heading, subject) et
  son lecteur (read_entries), et c'est la composition qui les fournit
  (TOPS, source_kinds.py) ; TopEntry est lui-même décrit « as its sheet
  shows it ». Séparer collecte et rendu touche donc etl/tops.py, la
  composition et post/top_sheets.py.
- Hors étapes : le motif d'un fichier de tendances que la base refuse
  dit encore « ranking refused by the base » (write_trend_file, dans
  etl/file_writing.py), alors que le code dit « trend » pour GH Archive
  et réserve « ranking » aux tops GitHub. C'est un message, lu par un test (tests/etl/test_load.py) et
  écrit au journal d'import : le changer touche le code, le test et le
  journal. À traiter à part.
- Hors étapes : release_writer.py:71-75 dépaquette fetchone() sans
  garde ; une liste incohérente entre le filtre et la table lèverait
  une TypeError au lieu d'une erreur nommée. À traiter à part.
- Hors étapes : six fichiers sont entrés dans la sortie du grep de la
  règle 3 de poc.md depuis le commit 9e6e2e8, sans la justification que
  la règle demande (« un fichier nouveau dans la liste se justifie dans
  la PR ») : etl/sources/clipping.py, commands/environment.py,
  commands/write_tops_command.py, commands/digest_command.py,
  commands/openapi_command.py et ai_api/connectors/llm_replay.py ;
  cli.py en est sorti. Aucun ne touche raw/ (relevé du 2026-10-22,
  fichier par fichier : coffre, dossier de données, base, journal
  d'import, fichiers du paquet, rejeu). À justifier ou à écarter de la
  liste, hors de cette refactorisation.

## 9. Chantiers de lisibilité

Le relevé du 2026-10-23, docs/refactoring/lisibilite.md, mesure les 29
modules de etl/ et etl/sources/ et classe 17 chantiers par rapport gain
de clarté / coût. Cette section tient l'état de chaque ligne de son
tableau (sa partie 5) ; le relevé lui-même n'est pas réécrit.

Un chantier sans étape est indépendant de la cible : il se fait avant ou
après n'importe laquelle. Le chantier 6 portait quatre renommages, dont
l'un est écarté et l'autre reporté : il tient trois lignes.

| # | Chantier | État | Étape |
|---|---|---|---|
| 1 | Docstring de list_file_keys : elle nommait etl/transform.py, qui ne porte plus list_visible_entries ni d'import de raw_store | fait, commit A (73421c1) | — |
| 2 | Docstring de module de cisa_kev : elle annonçait une collecte incrémentale, alors que son lecteur lit le catalogue entier | fait, commit A (73421c1) | — |
| 3 | Trois lignes de plus de 100 caractères, quatre docstrings coupées en plein milieu | fait, commit A (73421c1) | — |
| 4 | Docstrings des huit portes qui n'en avaient pas | fait, commit A (73421c1) | — |
| 5 | Valeurs par défaut de FileWriting : 44 lignes de littéraux ramenées à 23 | fait, commit C (618d9d8) | — |
| 6 | RawReadings -> ImportReadings ; read_collected_at -> find_collected_at, avec sa docstring | fait, commit B (b501e5a) | — |
| 6 | read_absent, qui ne dit pas ce qu'il fait | reporté, voir ci-dessous | — |
| 6 | to_ns -> to_nanoseconds | écarté le 2026-10-23, voir ci-dessous | — |
| 7 | Les deux read_text, de règle inverse sur une absence, devenus read_required_text et read_text_or_empty | fait, commit B (b501e5a) | portait l'étape 7, fait avant |
| 8 | L'horloge nommée qui manque à arxiv, seul à lire datetime.now(UTC) dans son fetch | à faire | hors étapes ; avec l'étape 7, qui déplace ce fetch |
| 9 | Les trois noms de lecture d'un top (read_most_starred, read_ranking, read_top_entries) et les trois read_ranking du dépôt, de signatures différentes | à faire | étape 8 |
| 10 | Sortir de collect_one_source le contrôle des noms de chemin | à faire | hors étapes ; avant l'étape 6, qui ajoutera le contrôle générique des entrées au même module |
| 11 | Couper les cinq niveaux de load.py : transaction, ordre des fichiers, aiguillage par type, écriture d'un fichier, règle d'une source | fait, 090ae1e (withdrawals.py) et f8b6d33 (file_writing.py) : trois modules, aucun de plus de trois niveaux | hors étapes ; la partie 5 décide de ce qui reste dans le load, jamais de la façon dont le module se lit |
| 12 | read_trends de gh_archive : séparer la validation Pydantic des quatre contrôles de cohérence | à faire | étape 7 |
| 13 | raw_store.py : une seule façon de nommer un fichier, les quatre fonctions à Path comprises | à faire | étape 3 bis |
| 14 | Le paramètre last_collected_at de read_new_vulnerabilities, mort en production | reporté, voir ci-dessous | — |
| 15 | Rompre le lien E -> T dans les dix fetch | à faire | étapes 6 et 7 |
| 16 | Découper zotero.py, puis les autres sources, en extract.py / transform.py | à faire | étapes 6 et 7 |
| 17 | Séparer dans Top ce qui relève de la collecte et du rendu | à faire | étape 8 |

Trois états demandent leur raison :

- Écarté, to_ns (chantier 6), le 2026-10-23 : le relevé invoquait
  l'interdiction d'abréviation de code.md, et le relevé des occurrences
  la contredit. Le suffixe des nanosecondes est de maison, emprunté à
  os.stat_result : changed_at_ns, read_changed_at_ns, modified_at_ns,
  settled_before_ns, newest_ns, à côté de st_mtime_ns et st_ctime_ns,
  que Python fournit. Renommer la seule fonction en ferait l'exception
  dans une famille cohérente ; renommer la famille entière est hors de
  proportion avec le gain.
- Reporté, read_absent (chantier 6) : un découpage à part, après le
  commit C. Le nom est trompeur (la fonction rend None pour un marqueur
  d'absence, la valeur sinon), mais deux de ses trois appels la comparent
  à None, « is None » puis « is not None » : elle fait deux choses, un
  prédicat et un validateur. C'est un découpage (is_absent, qui rend un
  booléen comme code.md le demande d'un prédicat, plus le validateur),
  pas un renommage ; le renommer d'abord obligerait à toucher les trois
  mêmes sites deux fois.
- Reporté, le paramètre last_collected_at de read_new_vulnerabilities
  (chantier 14) : décision de Sabine, hors étapes. Son unique appelant
  de production, read_catalog, passe toujours None : la branche de
  filtre n'est atteinte que par les tests (11 appels dans
  tests/etl/sources/test_cisa_kev.py). Le retirer change les tests ; le
  garder garde une branche que la production n'exécute jamais. Le
  commit A n'a corrigé que la docstring de module qui le décrivait comme
  le comportement de la source.

Les chantiers 13, 15, 16 et 17 sont les étapes de ce plan : 13 est
l'étape 3 bis, 15 et 16 les étapes 6 et 7, 17 l'étape 8. Leur avancement
est tenu par la partie 4, et ce que le relevé a précisé de ces étapes
est dans sa partie 6, pas ici.

Les anciens noms (RawReadings, read_collected_at) restent cités par
lisibilite.md, par le journal d'ADR et par des notes de journaling.
Décision de Sabine du 2026-10-23 : ces documents sont datés, ils ne sont
pas réécrits (partie 6). Le message du commit B nomme les quatre anciens
noms, pour qu'on les retrouve dans l'historique.
