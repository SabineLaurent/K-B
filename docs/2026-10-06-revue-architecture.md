# Revue d'architecture et des tests — 2026-10-06

Revue de la chaîne complète (collecte → brut → items → fusion → base), au commit `9544a23`
de `main` (PR #94 fusionnée), avant que #85 (lecteurs en Pydantic) et #86 (httpx) réécrivent
les étapes propres aux sources, et avant que l'API #21 s'appuie sur le schéma.

Les six points sont ceux de la mission du 06/10. Pour chaque constat : ce qui est, avec
`fichier:ligne` à ouvrir, ce qui serait plus simple, puis le coût (une estimation de Claude, non
relue). La colonne **Décision** est à remplir par Sabine. Rien n'a été corrigé ni supprimé.

Ce qui fonde la revue : la lecture de tout `src/k_b/` et de tous les tests, et
`ruff --select C90,SIM` (0 constat : aucune fonction ne dépasse une complexité de 10). Aucune
mesure de volume sur des données réelles n'a été faite.

## 1. Simplicité du workflow

Trois commandes : `kb collect` (télécharger, contrôler, écrire le brut), `kb create-db`, puis
`kb import` (relire tout le brut, le convertir en items, fusionner, écrire la base et le journal
d'import). Le chemin est linéaire et chaque étape a un seul point d'entrée.

| # | Ce qui est | Plus simple | Coût | Décision |
|---|---|---|---|---|
| W1 | Deux horloges. `collect_all_sources` reçoit `now` (`cli.py:105`), mais `ArxivSource.fetch` relit l'heure (`arxiv_source.py:44`), comme `TldrSource` (`tldr_source.py:40`, `73-74`). La fin de la fenêtre arXiv et le nom du fichier brut viennent donc de deux instants différents, et les tests doivent remplacer `datetime` ou `current_day` par un faux. | Passer `now` à `fetch(last_collected_at, now)`, dans le `Protocol` de `collect.py:30-42`. | 1 h : 6 sources et leurs tests. | |
| W2 | `kb import` relit et revalide **tout** le brut à chaque fois (`raw_items.py:64-79`). C'est simple et rejouable (même brut → même base, `import_items.py:4-5`), mais le coût croît avec le brut. Le volume n'a pas été mesuré. | Garder tel quel pour la v0 ; mesurer quand #25 (rodage sur données réelles) aura du brut. | 0 | |
| W3 | Le brut TLDR est collecté chaque jour (3 pages d'environ 80 Ko) mais jamais lu : `raw_items.py:73-78` saute les dossiers de pages (lecture dans #57). | Rien à changer si #57 vient vite ; sinon, suspendre la collecte TLDR jusqu'à #57 (RGESN 1.6 : ne pas collecter ce qui ne sert pas). | 0, ou 5 min | |
| W4 | Chaque source est lue deux fois : à la collecte, pour refuser une page qui n'est pas ce qu'on attend (`cisa_kev_source.py:44`, `github_most_starred_source.py:32`…), puis à l'import. | C'est voulu : échouer avant d'écrire un brut faux. À garder. | 0 | |

## 2. Étapes génériques communes à toutes les sources

Déjà communes : le téléchargement (`http_download.download`), l'écriture immuable du brut
(`raw_store.write_new_raw_file`), la date de dernière collecte par source (`collect.py:66-92`),
l'item commun (`items.Item`), la fusion et l'import.

| # | Ce qui est | Plus simple | Coût | Décision |
|---|---|---|---|---|
| G1 | **Trois traitements différents d'une entrée invalide.** arXiv écarte l'entrée et la journalise en WARNING, mais elle n'entre pas dans le journal d'import (`arxiv_papers.py:41-47`). CISA et GitHub refusent **tout le fichier** pour une seule entrée (`cisa_kev.py:44`, `github_releases.py:31-34`, `github_advisories.py:36`, `github_most_starred.py:44` ; ouvert : #77, #61). Une entrée refusée par `Item` est écartée seule et va dans le journal d'import (`raw_items.py:93-102`). | Une seule règle, générique, dans `raw_items.py` : le lecteur rend les entrées, chaque entrée invalide est écartée seule et tracée dans le journal d'import. Cela couvre #77 et #61, et peut se faire avec #85. | 2 h avec #85 ; ferme #77 et #61. | |
| G2 | **Ajouter une source touche 6 endroits** : `X_source.py`, `X.py` (lecteur), `items.convert_X`, l'aiguillage `raw_items.list_readers_by_source` (`raw_items.py:113-138`), `collect.SOURCES` (`collect.py:45-57`), et pour une nouvelle origine `SourceCode` (`items.py:24-26`) et `seed_sources.sql`. | Que chaque classe source porte son lecteur (par exemple `read_items(raw) -> list[Item]`) : `raw_items` n'aurait plus d'aiguillage, et l'ajout d'une source se ferait en 2 fichiers et une ligne de `SOURCES`. | 2 h, à faire avec #85 qui touche déjà chaque lecteur. | |
| G3 | **La lecture dépend de la collecte** : `raw_items.py:17` importe `collect.SOURCES`. Seul le brut des sources **actuellement suivies** est lu ; un dossier d'une source retirée est sauté (`raw_items.py:65-68`, c'est #87). | Aiguiller par nom de dossier brut, indépendamment de `SOURCES` : par exemple un préfixe (`github_releases_*` → lecteur des releases), avec le dépôt relu dans le brut. | 1 h ; ferme #87. | |
| G4 | « Rien de nouveau → `None` » et l'avertissement « page pleine » sont écrits deux fois, presque à l'identique (`github_releases_source.py:33-48`, `github_advisories_source.py:50-63`). | Deux occurrences : la règle de `code.md` dit de factoriser à la troisième. À garder. | 0 | |

## 3. Étapes spécifiques à chaque source

| # | Ce qui est | Plus simple | Coût | Décision |
|---|---|---|---|---|
| S1 | **Double validation.** Chaque lecteur valide à la main dans une `dataclass` (`github_releases.py:37-70`…), puis `Item` revalide en Pydantic. Une fois #85 fait tel qu'il est écrit, on aura deux modèles Pydantic par source : le modèle du lecteur, puis `Item`. | (a) #85 tel quel : un modèle Pydantic par source, puis `Item`. (b) Pas de modèle intermédiaire : le lecteur passe du dictionnaire brut à `Item`, et les contrôles propres à la source (préfixe d'URL, format GHSA) deviennent des types annotés. (b) supprime les 5 `dataclass` (volume de lignes non mesuré) ; (a) garde un modèle par source, utile seulement si un champ du brut sert ailleurs que dans `Item` (voir S2). | (a) 2,5 h (estimation de #85) ; (b) 3 h. | |
| S2 | **Des champs lus, validés, puis jamais utilisés** : `vendor_project` et `product` (CISA, `cisa_kev.py:23-24`, c'est #84), `is_prerelease` et `tag_name` hors titre (`github_releases.py:18,22`), `severity` et `packages` (`github_advisories.py:23,28`), `version` (`arxiv_papers.py:27`), `rank`, `stars`, `topics` et `created_at` (`github_most_starred.py:16-23`). Le docstring de `github_most_starred_source.py:21-24` annonce une comparaison de classements qui n'existe pas. | Ne lire que ce qui va dans `Item` (RGESN 1.6, YAGNI) ; un champ entre quand une question de veille s'en sert, selon la règle du journal du 02/10. Le brut garde tout de toute façon. | Inclus dans S1 (b) ; sinon 30 min. | |
| S3 | **Code mort** : le filtre par date de CISA (`cisa_kev.py:45-52`, paramètre `last_collected_at`) n'est appelé qu'avec `None` dans `src` (`cisa_kev_source.py:44`, `raw_items.py:123`). Seuls deux tests s'en servent (`test_cisa_kev.py:22`, `:73`). | Supprimer le paramètre, le filtre et les deux tests ; la fusion retire déjà les doublons du catalogue entier. | 15 min | |
| S4 | **#85 et #92 se contredisent.** #85 veut des messages « champ, valeur » ; #92 interdit la valeur reçue dans le motif d'un rejet. Aujourd'hui, les lecteurs recopient des valeurs du brut, qui finissent dans le journal d'import par `raw_items.py:91` : `{full_name!r}` (`github_most_starred.py:56`), `{ghsa_id!r}`, `{cve_id!r}` et `{severity!r}` (`github_advisories.py:44,49,55`), `{cve_id!r}` et `{row['dateAdded']!r}` (`cisa_kev.py:60,65`), `{entry_id!r}` (`arxiv_papers.py:87`). | Proposition pour accorder : une valeur qui vient **de K-B ou du protocole** (URL demandée, code HTTP, nom de fichier brut, nombre attendu / trouvé) peut s'écrire, c'est l'observé que demande `MEMORY.md`. Une valeur qui vient **du contenu collecté** ne s'écrit jamais : on écrit le champ et le type d'erreur (`entry 3: title: string_too_short`). Le critère de #85 devient alors « champ, type d'erreur », et #92 s'étend aux messages des lecteurs. | 15 min pour réécrire les critères ; le code suit avec #85. | |
| S5 | Le motif `owner/name` existe en trois versions : `github_releases_source.py:14`, `github_most_starred.py:10` et `items.RepositoryName` (`items.py:35`, motif différent). | Un seul type, dans `items.py`, que les deux autres réutilisent (connaissance unique, `code.md`). | 15 min | |

## 4. La base de données et son schéma

| # | Ce qui est | Plus simple | Coût | Décision |
|---|---|---|---|---|
| D1 | **L'exclusivité des sous-types n'est vérifiée nulle part.** `docs/stockage.md:206-209` et le journal du 02/10 (PR de #7) disent que le code de fusion vérifie deux contraintes : un item a au plus un sous-type ; DÉPÔT ne concerne que GitHub et GH Archive, VULNÉRABILITÉ que CISA KEV et GitHub. `merge.py` ne vérifie ni l'une ni l'autre. Le seul validateur, `items.py:62-66`, vérifie qu'un CVE implique une vulnérabilité. Aujourd'hui, aucun convertisseur ne produit un item à deux sous-types (`items.py:69-145`), mais rien ne l'empêche. | (a) Un validateur de plus dans `Item` : pas à la fois `is_vulnerability` et `repository_name`, et chaque sous-type limité à ses `source_code`. On corrige alors la doc : « vérifié par `Item` », pas par la fusion. (b) Remplacer `is_vulnerability` et `repository_name` par un champ `kind: Literal["vulnerability", "repository"] \| None` : l'exclusivité est alors portée par le type. (c) Des déclencheurs SQL : plus lourd, et SQLite seulement. | (a) 30 min avec tests et doc ; (b) 1 h 30. | |
| D2 | **Un sous-type n'est jamais retiré.** Si un item change de nature d'un import à l'autre, l'upsert (`import_items.py:93-104`) ajoute la nouvelle ligne de sous-type sans supprimer l'ancienne. Aucune source ne le fait aujourd'hui. | Avec D1 (a) ou (b), supprimer les lignes de sous-type de l'item avant de réécrire la sienne, comme `write_authors` le fait pour les auteurs (`import_items.py:129`). | 20 min | |
| D3 | `source_code = 'github'` regroupe trois natures d'items : releases (identifiant numérique), alertes (GHSA) et dépôts (`owner/name`) (`items.py:106,121,137`). Leurs `source_item_id` partagent la contrainte `UNIQUE (source_code, source_item_id)` (`schema.sql:36`). Les formats ne se chevauchent pas aujourd'hui, mais rien ne le garantit. Une release n'a pas de sous-type : elle n'est reconnaissable que par l'absence des deux autres. | À décider avant #21 : l'API devra filtrer « les releases ». Soit un préfixe dans `source_item_id` (`release:123`), soit une nature explicite (voir D1 (b), avec une valeur `release`). | Avec D1 (b) : + 30 min | |
| D4 | Les tables `highlight` (Zotero, #15) et `star_gain` (GH Archive, #16) existent pour des sources pas encore codées (`schema.sql:58-82`). | C'est un modèle Merise documenté, à garder. Elles ne coûtent rien tant qu'elles sont vides ; les retirer obligerait à remettre à jour le MCD, le MLD et le MPD. | 0 | |
| D5 | Rien n'est jamais supprimé de `item` : un brut retiré ne retire pas ses items. C'est le sujet de #83 (purge). | Rien de plus que #83. | 0 | |

## 5. Organisation des fichiers de code

25 modules à plat dans `src/k_b/`, plus `database/` pour le SQL. Les dépendances vont dans un
seul sens, à une exception près.

| # | Ce qui est | Plus simple | Coût | Décision |
|---|---|---|---|---|
| F1 | `items.py` importe les 5 `dataclass` des lecteurs et porte les 5 `convert_*` (`items.py:17-21`, `69-145`) : le modèle commun connaît chaque source. | Mettre chaque `convert_X` à côté de son lecteur (ou dans la source, voir G2) : `items.py` ne garde que `Item` et ses types. | Inclus dans G2 | |
| F2 | `raw_items.py` (lecture) importe `collect.py` (collecte) : c'est la dépendance qui remonte le courant (G3). | Voir G3. | Inclus dans G3 | |
| F3 | Un module de lecture et un module de collecte par source, à plat, avec des préfixes (`github_*` : 8 fichiers). | (a) Garder à plat, c'est lisible avec 25 fichiers. (b) Un sous-paquet `sources/` avec un fichier par source (collecte et lecture ensemble). (b) se justifie si G2 est retenu ; sinon, le déplacement n'apporte rien. | (b) 1 h, surtout des imports | |

## 6. Pertinence de chaque test

251 tests, 25 fichiers. Verdict par fichier. Seuls les tests à fusionner ou à supprimer sont
nommés.

| Fichier | Verdict | Raison |
|---|---|---|
| `test_package.py` | **supprimer** | Vérifie que `k_b` s'importe ; les 250 autres tests le font déjà. |
| `test_schema.py` | **fusionner** dans `test_database.py` | La liste des tables et les 7 sources doublent `test_database.py:9`. `test_two_sources_can_share_a_cve` est à garder (décision de Sabine). `test_a_cve_is_found_through_its_index` est à **supprimer** : il teste le planificateur de SQLite, pas K-B. |
| `test_database.py` | garder | Création, refus, clés étrangères, échec sans fichier : des risques réels. |
| `test_items.py` | garder, sauf un | `test_an_item_cannot_be_changed` est à **supprimer** : il teste `frozen=True` de Pydantic, donc la bibliothèque. `test_the_source_codes_are_those_of_the_database` est à garder : il tient deux copies d'une même connaissance alignées. |
| `test_tracked_repositories.py` | garder un sur deux | `test_the_tracked_repositories_are_those_of_docs_sources` est à **supprimer** : il recopie la constante, et le changer revient à changer la liste. |
| `test_github_api.py` | garder, sauf un | `test_the_response_is_returned_unchanged` est à **supprimer** : il double `test_http_download.py:46`. |
| `test_http_download.py` | garder | La frontière réseau : préfixe, redirection, taille, en-têtes. |
| `test_arxiv_source.py`, `test_cisa_kev_source.py` | garder, **alléger** | Dans `test_the_request_names_k_b_and_has_a_timeout`, l'agent utilisateur et le délai doublent `test_http_download.py:50`. Garder l'URL et les en-têtes propres à la source, retirer le reste. |
| `test_*_source.py` : `…_is_a_source_of_kb_collect` (5 tests : arxiv, advisories, most_starred, releases, tldr) | **fusionner** en un test dans `test_collect.py` | Un seul test qui liste les noms attendus de `SOURCES`. |
| `test_cisa_kev.py` | garder, sauf deux | `test_only_vulnerabilities_added_since_the_day_before…` et `test_a_vulnerability_dated_the_day_before…` sont à **supprimer avec le code mort** (S3). |
| `test_github_most_starred.py` | garder | Les assertions sur `stars`, `created_at` et `topics` (`:29-31`) tombent si S2 est retenu. |
| `test_github_releases.py`, `test_github_advisories.py`, `test_arxiv_papers.py` | garder | Ils seront adaptés par #85. Les tests « … not kept » (login, personnes créditées) sont des tests RGPD : à garder. |
| `test_github_releases_source.py`, `test_github_advisories_source.py`, `test_github_most_starred_source.py`, `test_tldr_source.py` | garder | La fenêtre de collecte, « rien de nouveau », l'avertissement de page pleine, les redirections TLDR : des règles de K-B. |
| `test_github_dates.py`, `test_raw_store.py`, `test_collect.py`, `test_merge.py`, `test_raw_items.py` | garder | Chaque test porte une règle écrite (fusion, immuabilité du brut, panne isolée). |
| `test_cli.py` | garder | `test_import_refuses_a_missing_database…` recouvre `test_import_items.py:219`. Les deux sont à garder : l'un vérifie le message et le code de sortie, l'autre l'absence de création. |
| `test_import_items.py` | garder | Rejouabilité, journal entier ou rien, auteurs orphelins : des risques réels. |

Bilan si tout est retenu : 6 tests supprimés, 2 fichiers en moins (`test_package.py`,
`test_schema.py`), 5 tests fusionnés en un, et 2 tests allégés.

## Ce qui n'a pas été vérifié

- Le volume du brut et la durée de `kb import` sur des données réelles (W2).
- Les coûts sont des estimations de Claude, non relues par un agent indépendant.
- Le nombre de tests après les suppressions n'a pas été recompté par `pytest`.
