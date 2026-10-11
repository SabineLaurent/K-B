# Revue d'homogénéité de l'architecture — 2026-10-11

Une session par issue ne voit jamais l'ensemble : cette revue regarde cinq familles de
problèmes traitées à des endroits différents, propose une convention par famille, et consigne la
décision de Sabine. Les règles retenues sont dans
[`.claude/rules/conventions.md`](../.claude/rules/conventions.md). Cette note est l'entrée du
découpage qui suit.

Code de `main` au commit 8721646. Chaque `fichier:ligne` et chaque compte viennent d'une
commande (`grep -n`, `grep -c`). Un second passage indépendant a revérifié chaque fait par
commande : 13 écarts relevés, tous corrigés ici ; aucune recommandation ne contredit le journal
ADR.

Les sections « Options » gardent la recommandation telle que présentée à Sabine ; la décision
suit chacune.

## Famille 1 — Rejet d'une entrée invalide

### Constat
Trois façons de traiter une entrée invalide coexistent.

1. **Lever, et toute la source ou toute la page tombe.** Les lecteurs de CISA, des releases, des
   alertes et du classement GitHub construisent leur liste par compréhension et lèvent au
   premier élément invalide :
   - `src/k_b/sources/cisa_kev.py:101`, `src/k_b/sources/github_releases.py:101`,
     `src/k_b/sources/github_advisories.py:106`, `src/k_b/sources/github_most_starred.py:82`.
   - À la collecte, `fetch` les appelle (`cisa_kev.py:71`, `github_releases.py:55`,
     `github_advisories.py:67`, `github_most_starred.py:48`) : une entrée invalide fait échouer
     la source (`collect.py:44`).
   - À l'import, `read_page` attrape l'erreur (`raw_items.py:87-88`) et rejette la page entière,
     entrées valides comprises (CISA, releases, alertes ; le classement n'a pas de lecteur
     d'import, `source_kinds.py:49-50`).
   - Le classement refuse à dessein une page incomplète (`github_most_starred.py:78-81`) : un
     classement à 99 dépôts montrerait des sorties qui n'en sont pas.
2. **Écarter et journaliser, sans trace au journal d'import.** arXiv : `read_papers` écarte
   l'entrée invalide par `logger.warning` (`arxiv.py:135`) ; elle n'entre pas dans
   `import-log.jsonl`. À la collecte, arXiv ne valide pas les entrées, il les compte
   (`arxiv.py:77`).
3. **Écarter, journaliser et tracer.** Un item refusé par `Item` (`ValidationError`,
   `raw_items.py:97`) ou une release d'un dépôt non suivi (`import_items.py:127`) devient un
   `Rejection` : `reject` le journalise (`raw_items.py:146`), puis `write_import_log` l'écrit
   dans `import-log.jsonl` (`import_items.py:348`), si la transaction de la base a réussi.

Deux cas qui passent la frontière et font échouer tout l'import :
- une exception hors de `(ValueError, csv.Error, OSError)` (`raw_items.py:88`), comme
  `RecursionError` (#103) ;
- une entrée que l'item accepte et que la base refuse : l'écriture est une seule transaction
  (`import_items.py:117`, `:120`), donc tout l'import est annulé, à chaque import (PR #131,
  « Out of #122 », quatre cas). `KindWithoutTableError` (`import_items.py:173`) et
  `UnknownSourceError` (`import_items.py:323`) lèvent aussi dans la transaction ; aucun lecteur
  d'aujourd'hui ne les atteint.

### Options
- **A. Le motif d'arXiv et de `Item`, partout (recommandée).** Un lecteur ne lève que pour une
  page illisible (pas du JSON, pas du CSV, colonnes manquantes) ; une entrée invalide devient un
  rejet nommé, porté par un seul chemin (`reject`, `raw_items.py:146`) jusqu'au journal
  d'import. À la collecte, la même lecture : la source n'échoue que si la page est illisible ou
  si toutes ses entrées sont invalides (`all_items_invalid`, critères de #61 et #77). Exception
  écrite : un classement (instantané dont la complétude compte) refuse la page entière, comme
  aujourd'hui. Coût : le contrat `SourceReader` change (`read_entries` renvoie aujourd'hui les
  seules entrées, `source_contract.py:36`) pour rendre aussi les rejets, sinon un rejet de
  lecteur reste un simple `logger.warning`, absent du journal d'import, comme pour arXiv ;
  #61 et #77 sont à préciser en ce sens, et arXiv ramené au même chemin. Le code le fait déjà à
  l'étape `convert`.
- **B. Valider seulement à la conversion.** `read_entries` ne fait que découper la page en
  entrées brutes ; toute la validation passe dans `convert` (Pydantic, #85), et la
  `ValidationError` suit le chemin existant (`raw_items.py:97`). Plus uniforme, mais la collecte
  ne vérifierait plus ce qu'elle écrit (le motif « un brut illisible n'est pas écrit »,
  `cisa_kev.py` docstring de `fetch`), sauf à convertir aussi à la collecte.
- **C. Statu quo par source.** Écarté : une seule release mal formée bloque une source à
  chaque collecte (#61), et arXiv écarte sans laisser de trace au journal d'import.

**Décision de Sabine : A, plus un `SAVEPOINT` par item à l'écriture en base.** Si la base
refuse un item, `ROLLBACK TO` de cet item seul ; il devient un rejet de `import-log.jsonl` et
l'import continue. Ne sont rattrapées que les erreurs dues à l'entrée (`sqlite3.IntegrityError`,
erreurs de conversion Python → SQLite comme `OverflowError`), liste établie sur les quatre cas de
la PR #131, un test par cas ; une erreur du système (disque plein, base verrouillée) arrête tout.
C'est le filet derrière la famille 4.

**Piste après E1, non retenue maintenant** : traiter chaque source en flux, de bout en bout
(E → T → L), au lieu du traitement par lots actuel (toute la collecte, puis tout l'import). Le
`SAVEPOINT` reste valable dans les deux cas.

## Famille 2 — Fichier temporaire

### Constat
Trois écritures « sans fichier à moitié écrit », trois façons de faire. Aucune n'appelle
`fsync`.
- `write_file_atomically` (`raw_store.py:28`) : `NamedTemporaryFile(dir=…, delete=False)`
  (`raw_store.py:31`), nom `tmp…` non caché ; supprimé seulement si `os.replace` échoue
  (`raw_store.py:34`, `:36`). Sert au brut (`raw_store.py:44`) et à l'état de collecte, à la
  racine du dossier de données (`raw_store.py:80`). Un échec de `write` (#62) ou un arrêt brutal
  (#112) laisse le fichier.
- `write_import_log` : son propre temporaire, nom fixe `<journal>.tmp`
  (`import_items.py:375`), supprimé sur toute exception, Ctrl-C compris
  (`except BaseException`, `import_items.py:381`, `:383`).
- `create_database` : écrit la base en place et la supprime si la création échoue
  (`except BaseException`, `database/creation.py:32`, `:35`). SQLite écrit lui-même son
  fichier : ce cas reste hors de la convention.
- L'import saute déjà les fichiers cachés (`raw_items.py:143`).
- Une collecte en pages qui échoue au milieu laisse les pages déjà écrites
  (`collect.py:77`, limite écrite).

### Options
- **A. Un seul `write_file_atomically` pour tout fichier que K-B écrit lui-même, la base SQLite
  exceptée (recommandée).**
  Temporaire caché dans le dossier cible (`.<nom>.…tmp`), supprimé sur `BaseException` ; le
  journal d'import l'utilise aussi. Couvre #62 (échec de `write`), #112 (l'import saute un nom
  caché, `raw_items.py:143`) et l'état de collecte, en une PR. Reprend la façon de
  `write_import_log`, la plus complète des deux.
- **B. Nettoyage au démarrage** des `tmp…` laissés. Couvre l'arrêt brutal (#112) mais pas le
  temporaire visible entre-temps, et ajoute une étape à chaque lancement.
- **C. Garder les deux fonctions, corriger chacune.** Deux façons de faire la même chose,
  qui divergent déjà.

**Décision de Sabine : A.**

## Famille 3 — Journaux

### Constat
- Format sans horodatage : `cli.py:31-32` (#68).
- Deux canaux : 13 appels `logger.*` dans 6 fichiers, et 14 `print(` dans `cli.py` (résultat par
  source, résumé d'import, erreurs fatales).
- L'échec d'une source s'affiche par le nom de l'exception (`cli.py:145`), pas par un état nommé.
- Trois issues donnent trois règles différentes sur la valeur observée dans un message :
  - #85 : les messages des lecteurs donnent « champ, valeur » ;
  - #92 : le motif d'un rejet « sans la valeur reçue », seulement champ et type d'erreur ;
  - #103 : une valeur citée « est tronquée à une longueur fixe ».
- Le code fait encore autrement : les lecteurs citent la valeur entière par `!r`
  (ex. `github_advisories.py:114`), le motif d'un rejet recopie le message de Pydantic, valeur
  comprise (`raw_items.py:101`), et le refus pour longueur donne champ, longueur et maximum
  (`items.py:204`), comme le demande l'ADR du 2026-10-08. Appliqué tel quel, #92 effacerait la
  longueur et le maximum (PR #131).
- Absence du jeton GitHub : rien n'est journalisé (`sources/github_api.py:19`, #63).
- Deux lignes de journal supposent et conseillent, contre `code.md` (« Journalisation ») :
  « some may be missing; time to read the next pages » (`github_releases.py:74`,
  `github_advisories.py:78`).
- Un même échec journalisé deux fois : `tldr.py:66` (`logger.error`, puis relance) et
  `collect.py:45` (`logger.exception`).

### Options
- **A. Un message dit le champ, l'état et la mesure ; une valeur observée est citée tronquée,
  sauf une donnée personnelle (recommandée).** Champ ou position de l'entrée, type d'erreur
  (Pydantic : `loc` et `type`), mesure (longueur reçue, maximum, nombre attendu). Une valeur
  observée (identifiant, URL, code HTTP, titre trouvé) est citée, tronquée à une longueur fixe
  (#103), comme le veut la consigne « titre trouvé et titre attendu » (`MEMORY.md`). Un champ
  qui porte une donnée personnelle au registre (auteurs) n'est jamais cité : sa position et sa
  mesure seulement. Accorde #85, #92 et #103, et garde l'ADR du 2026-10-08. Les deux lignes qui
  supposent sont réécrites en observé (« 100 releases, toutes plus récentes que la dernière
  collecte »).
- **B. Jamais de valeur** (#92 tel quel). Contredit l'ADR du 2026-10-08 (longueur et maximum) et
  la consigne « un journal dit ce qui a été observé (URL de redirection, code HTTP…) ».
- **C. Toujours la valeur, tronquée** (#103 tel quel). Laisse un fragment de nom d'auteur ou de
  texte dans le journal (#92, RGPD minimisation).

Pour le canal : garder `print` pour le résultat d'une commande (ce que Sabine lit), `logger`
pour le déroulé ; « fichier écrit / rien de nouveau » par source reste #68 (hors E1).

**Décision de Sabine : A, avec deux ajouts** tirés de
l'[OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
(« Perform sanitization on all event data to prevent log injection attacks » ; « when, where,
who and what ») :
1. une valeur citée dans un message du logger est **échappée** (retours à la ligne, caractères de
   contrôle, par exemple par `repr()`), en plus d'être tronquée ; `import-log.jsonl` est déjà
   protégé par le JSON ;
2. l'**horodatage** entre dans la convention et remonte dans E1 : il sort de #68.

## Famille 4 — Validation des entrées

### Constat
- Un modèle Pydantic, `Item` (`items.py:111`) ; cinq lecteurs en `dataclass` validés à la main
  (`arxiv.py:111`, `cisa_kev.py:75`, `github_advisories.py:86`, `github_releases.py:82`,
  `github_most_starred.py:52`) : la limite assumée par l'ADR du 2026-10-05, jusqu'à #85.
- Une même règle écrite plusieurs fois :
  - CVE : `items.py:30` et `items.py:36` (deux regex `\d`), `schema.sql:106` (`GLOB [0-9]`).
    `\d` accepte des chiffres non ASCII que le `GLOB` refuse (« Out of #122 », n° 2).
  - Nom de dépôt : `tracked_repositories.py:12` (`[A-Za-z0-9_.-]`), `items.py:38`
    (`[^/\s]`), `schema.sql:87` et `:136` (`GLOB '?*/?*'`) : trois règles différentes.
  - GHSA : `github_advisories.py:27` (forme exacte) ; `Item` borne seulement la longueur à 19
    (`items.py:93`) ; `schema.sql:177` (`GLOB 'GHSA-*'`). D'où « `Item` seul accepte un
    identifiant hors `GHSA-…` » (PR #131), qu'aucune entrée collectée n'atteint aujourd'hui :
    le lecteur vérifie la forme avant (`github_advisories.py:113`).
  - Date avec fuseau : trois fonctions pour la même règle, `raw_store.py:85`, `arxiv.py:204`,
    `sources/github_dates.py:6`.
  - « `bool` n'est pas un entier » : `github_releases.py:109`, `github_most_starred.py:101`.
- Les longueurs, elles, ont une seule source Python et un test qui la compare au `CHECK`
  (`items.py`, ADR du 2026-10-10) : c'est le motif qui marche.
- Ce que l'item accepte et que la base refuse fait tomber l'import (famille 1) : identifiant de
  release au-delà de 64 bits, CVE à chiffres non ASCII, surrogate isolé, `tag_name` qui
  commence par NUL (PR #131, quatre cas).
- Frontière réseau : la redirection est contrôlée après avoir été suivie
  (`http_download.py:43`, `:45`, #54) ; le flux arXiv est lu par `ElementTree`
  (`arxiv.py:163`, `noqa: S314`, #69). Le commentaire `arxiv.py:47` dit expat sûr, alors que #69
  constate qu'une entité interne déclarée est développée : à accorder.
- Une exception hors `ValueError` (`RecursionError`, #103) traverse `raw_items.py:88`.

### Options (question de Sabine : un module commun, ou la validation dans chaque source ?)
- **A. Types communs dans un module, modèles dans chaque source (recommandée).** Les types
  partagés par plusieurs sources ou par la base (`CveId`, `GhsaId`, `RepositoryName`,
  date UTC avec fuseau, texte sans NUL ni surrogate, entier 64 bits) vivent une seule fois, dans
  `items.py` (déjà le module des types, plan ETL) ; chaque source garde son modèle Pydantic
  dans son module (#85). Règle : tout ce que la base refuse, l'item le refuse avant ; un test
  compare chaque type à son `CHECK`, comme pour les longueurs.
- **B. Un module commun de validation qui porte tous les modèles.** Une source n'est plus lisible
  dans son seul module (le plan ETL a regroupé E et T par source, #100) ; le module grossit à
  chaque source.
- **C. Validation dans chaque source, sans types communs.** Le statu quo : trois règles pour un
  nom de dépôt.

**Décision de Sabine : A.**

## Famille 5 — Couche d'accès aux données

### Constat
- Tout le SQL Python est dans `import_items.py` (20 lignes trouvées par
  `grep -cE 'INSERT INTO|SELECT |UPDATE |DELETE FROM'`), hors des `PRAGMA` de `database/` :
  cinq constantes (`:28`, `:41`, `:57`, `:65`, `:71`) et des requêtes en ligne (`:183` à
  `:335`), dont 8 `SELECT` de recherche faits pendant l'écriture. Aucune requête de lecture pour
  un utilisateur n'existe encore (`kb search`, API #21).
- Il est déjà rangé par objet métier : un écrivain par sorte, `WRITER_BY_KIND`
  (`import_items.py:305`).
- `database/` ne contient que la connexion, la création et les scripts SQL.
- `import sqlite3` : `import_items.py:10`, `cli.py:6` (pour attraper `sqlite3.Error`),
  `database/connection.py:3`.
- ADR du 2026-10-10 : `sqlite3` et SQL, pas d'ORM ; un seul écrivain (l'import) ; la requête
  `UNION ALL` « écrite une fois et partagée » entre `kb search`, « quoi de neuf » et l'API.
- #106 sépare T et L : « `grep -n sqlite3 src/k_b/raw_items.py` ne renvoie rien » ; #107 renomme
  `import_items.py` en `load.py`.

### Options
- **A. Le SQL vit dans `database/` : un module d'écriture (un écrivain par sorte, comme
  aujourd'hui) et un module de lecture (la requête `UNION ALL`) (recommandée).** `load.py`
  orchestre la transaction et le journal, sans SQL ; `kb search` et l'API appellent la même
  fonction de lecture. Vérifiable : `grep -rlE 'INSERT INTO|SELECT |UPDATE |DELETE FROM'
  src/k_b --include='*.py'` ne renvoie que des fichiers de `src/k_b/database/` (les migrations
  Alembic, écrites en SQL, iront aussi sous `database/`).
- **B. Un module par objet métier dans `database/`** (publication, vulnérabilité, release,
  alerte, donnée brute), chacun avec son écriture et sa lecture. La requête `UNION ALL` traverse
  tous les objets et n'appartient à aucun ; cinq modules pour une vingtaine de requêtes.
- **C. Statu quo** : SQL d'écriture dans le module de chargement, requête de lecture à côté de
  son premier appelant. La requête partagée finirait dans le module de `kb search` ou de l'API.

**Décision de Sabine : A.**

Idées de Sabine, décidées :
- **CRUD par table : écarté.** K-B écrit un item et son sous-type ensemble, dans une
  transaction, par upsert ; il ne met jamais à jour une table seule, ne supprime que par la
  purge, et lit par une seule requête. Un CRUD par table ferait environ quatre fonctions par
  table, presque toutes sans appelant (`code.md`, YAGNI), et couperait le couple
  item + sous-type que l'écriture tient ensemble.
- **MVC : écarté comme nom, gardé dans son principe.** Le principe utile, séparer la
  présentation (`cli.py`, routes de l'API), le métier (`items.py`, `merge.py`) et l'accès aux
  données (`database/`), est déjà la règle « Séparation des responsabilités » de `code.md`.
  K-B n'a ni vue à mettre à jour ni contrôleur d'événements : le vocabulaire MVC ajouterait des
  noms sans ajouter de séparation. La page de conventions nomme ce principe « architecture en
  couches » (présentation, métier, accès aux données).

## Issues ouvertes des cinq familles : sort proposé

À décider au découpage (`/split-project-ls`). Aucune issue n'a été créée, modifiée ni fermée par
cette revue. Le critère de fin de chaque issue a été relu avant d'écrire ce qu'elle couvre.

| Issue | Famille | Sort proposé |
|---|---|---|
| #61 Écarter une release ou une alerte GitHub invalide | 1 | **À regrouper avec #77, et à modifier** : le critère dit « écarté et journalisé » ; ajouter que le rejet est rendu par le lecteur (contrat `SourceReader`) et entre dans `import-log.jsonl`, et qu'arXiv rejoint ce chemin (`arxiv.py:135`). Le classement garde son refus en bloc. |
| #77 Écarter une ligne invalide du catalogue CISA | 1 | **À regrouper avec #61**, même modification. |
| — | 1 | **À créer** : `SAVEPOINT` par item à l'écriture en base ; les quatre cas de la PR #131 (identifiant de release au-delà de 64 bits, CVE à chiffres non ASCII, surrogate isolé, `tag_name` qui commence par NUL) deviennent des rejets, un test par cas ; un test où une erreur du système arrête l'import. |
| #103 Rejeter un brut trop imbriqué | 1, 3 | **À modifier** : le premier point (rejet de la page sur `RecursionError`) reste ; le second (« une valeur observée citée dans un message de refus de lecteur est tronquée ») devient « tronquée et échappée » (convention 3). |
| #62 Aucun fichier temporaire dans `raw/` après une erreur d'écriture | 2 | **À regrouper avec #112**, une PR : temporaire caché, supprimé sur `BaseException`, utilisé aussi par l'état de collecte et le journal d'import (`import_items.py:375`). |
| #112 Ne pas lire le temporaire d'une écriture interrompue | 2 | **À regrouper avec #62** ; son critère, « à écrire à la conception », devient : le temporaire est caché, et un test simule le reste d'une écriture interrompue que l'import saute. |
| #92 Le motif d'un rejet recopie des valeurs du brut | 3 | **À modifier** : remplacer « sans la valeur reçue » par la convention 3 (champ, type d'erreur, mesure ; valeur tronquée et échappée ; jamais un auteur). Ferme la décision ouverte « Motif d'un rejet pour longueur » du journal ADR. Le message de Pydantic tient sur plusieurs lignes (`raw_items.py:101`) : l'échappement s'applique au motif. |
| #68 Rendre les journaux de collecte complets (hors E1) | 3 | **À modifier** : l'horodatage en sort (décision de Sabine) ; restent « fichier écrit / rien de nouveau » par source et l'URL dans chaque erreur réseau. |
| — | 3 | **À créer, dans E1** : journaux horodatés (`cli.py:32`) ; réécrire en observé les deux lignes qui supposent (`github_releases.py:74`, `github_advisories.py:78`) ; un seul journal par échec (`tldr.py:66` et `collect.py:45`). |
| #63 Signaler au lancement l'absence du jeton GitHub | 3 | **Gardée telle quelle** : son critère (une ligne au lancement, le jeton jamais dans un message) suit la convention. |
| #85 Migrer les lecteurs vers Pydantic | 3, 4 | **À modifier** : « les messages d'erreur disent toujours ce qui a été observé (champ, valeur) » renvoie à la convention 3 ; ajouter que les types partagés viennent de `items.py` (convention 4). |
| — | 4 | **À créer, avant #85** : types communs dans `items.py` (`CveId` en chiffres ASCII, `GhsaId`, `RepositoryName`, date UTC avec fuseau, texte sans NUL ni surrogate, entier 64 bits), utilisés par les lecteurs et par `Item`, et un test qui compare chacun à son `CHECK`. Remplace les trois fonctions de date et les trois règles de nom de dépôt. |
| #69 Lire le flux arXiv sans développer les entités XML (hors E1) | 4 | **À modifier** : ajouter la correction du commentaire `arxiv.py:47` (« expat … refuses entity expansion attacks »), que l'issue contredit par son constat. |
| #54 Refuser une redirection hors du préfixe avant de la suivre | 4 | **Gardée telle quelle.** |
| #107 Nommer les modules d'après E, T et L | 5 | **Gardée telle quelle** (renommage seul). |
| — | 5 | **À créer, après #107** : déplacer le SQL d'écriture de `import_items.py` (futur `load.py`) dans un module d'écriture de `database/` ; `load.py` garde la transaction et le journal. Vérifié par la commande de la convention 5. |
| #106 N'importer que les fichiers bruts pas encore importés | 5 | **Gardée** ; la lecture du registre des fichiers importés est une requête : elle va dans `database/`. Son journal par import (`import-log-<date>.jsonl`) passe par `write_file_atomically` (convention 2). |
| #21 Epic : API « quoi de neuf » | 5 | **À noter au détail** : la requête `UNION ALL` vit dans le module de lecture de `database/`, partagé avec `kb search`. |
| #83 Purger les données au-delà de leur durée de conservation | 5 | **À modifier** : retirer « les auteurs orphelins », qui n'existent plus (ADR du 2026-10-07 : les auteurs sont une liste JSON de la publication) ; la suppression est une requête de `database/`. |

## Écarts du code de `main` à la convention retenue

| Famille | Écart | Où |
|---|---|---|
| 1 | Le lecteur lève au premier élément invalide | `cisa_kev.py:101`, `github_releases.py:101`, `github_advisories.py:106` |
| 1 | Une entrée écartée sans rejet au journal d'import | `arxiv.py:135` |
| 1 | Le contrat ne rend pas de rejets | `source_contract.py:36` |
| 1 | Une seule transaction, sans `SAVEPOINT` par item | `import_items.py:117`, `:120` |
| 1 | `RecursionError` traverse la lecture | `raw_items.py:88` |
| 2 | Temporaire non caché, nettoyé seulement si le renommage échoue | `raw_store.py:31`, `:36` |
| 2 | Second mécanisme de temporaire | `import_items.py:375` |
| 3 | Journaux sans horodatage | `cli.py:32` |
| 3 | Motif de rejet = message entier de l'exception, valeur comprise, sur plusieurs lignes pour Pydantic | `raw_items.py:65`, `:90`, `:101` |
| 3 | Valeurs citées par `!r` sans troncature : 22 occurrences dans 10 fichiers (`grep -rc '[!]r}'`) | ex. `github_advisories.py:114` |
| 3 | Valeur externe citée sans échappement (`%s`) | `tldr.py:62` (URL de redirection) |
| 3 | Lignes qui supposent | `github_releases.py:74`, `github_advisories.py:78` |
| 3 | Un échec journalisé deux fois | `tldr.py:66`, `collect.py:45` |
| 3 | Échec affiché par le nom de l'exception, pas par un état nommé | `cli.py:145` |
| 4 | Règle CVE en `\d` (chiffres non ASCII acceptés), deux fois | `items.py:30`, `:36` |
| 4 | Trois règles de nom de dépôt | `tracked_repositories.py:12`, `items.py:38`, `schema.sql:136` |
| 4 | Forme GHSA hors de `items.py` ; `Item` borne seulement la longueur | `github_advisories.py:27`, `items.py:93` |
| 4 | Trois fonctions de date avec fuseau | `raw_store.py:85`, `arxiv.py:204`, `github_dates.py:6` |
| 4 | Cinq lecteurs en `dataclass` (limite assumée jusqu'à #85) | `arxiv.py:111`, `cisa_kev.py:75`, `github_advisories.py:86`, `github_releases.py:82`, `github_most_starred.py:52` |
| 5 | SQL hors de `database/` | `import_items.py` (20 lignes, `:28` à `:335`) |

## Hors des cinq familles

Rien de nouveau relevé. Les lignes périmées du registre des traitements et les citations de la
clarification du modèle restent celles listées par la PR #131 (« Out of #122 »).
