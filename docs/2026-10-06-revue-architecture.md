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

**Second passage** : un agent indépendant, sans le contexte de la session, a vérifié chaque
affirmation et cherché ce qui manquait. Ses corrections ont été vérifiées dans le code, puis
reportées ici. Les constats qu'il a ajoutés sont marqués *(2nd passage)*.

## 1. Simplicité du workflow

Trois commandes : `kb collect` (télécharger, contrôler, écrire le brut), `kb create-db`, puis
`kb import` (relire tout le brut, le convertir en items, fusionner, écrire la base et le journal
d'import). Le chemin est linéaire et chaque étape a un seul point d'entrée.

### W0 — L'import rejoue tout le brut : à remplacer par un import incrémental

**Décision de Sabine (2026-10-06)** : le rejeu complet de `raw/` à chaque `kb import` est
abandonné. La collecte est incrémentale ; l'import doit l'être aussi.

**Ce qui est.**
- `kb import` relit et revalide **tout** `raw/` à chaque exécution (`raw_items.py:64-79`).
- La fusion se fait **en mémoire** (`merge.py:30-71`) : elle ne voit que ce qu'elle a chargé, d'où la relecture complète.
- Deux de ses trois règles, « même identifiant de source » et « même URL », sont déjà des contraintes `UNIQUE` de la base (`schema.sql:36`, `:27`) : elles sont donc vérifiées deux fois.
- Chaque import refait le travail des précédents pour aboutir à la même base, plus les nouveautés ; le journal d'import se remplit de doublons attendus (W5).
- La collecte et la base tiennent chacune leur mémoire (`raw/collection_state.json`, et la table `collection`).

**Référence : brief09** (`brief09_assistant-veille-tech`, indicatif selon `MEMORY.md`).
- Chaque exécution ne récupère que les nouveautés, depuis un repère calculé dans la base (`SELECT MAX(published_date) … WHERE source = ?`, `app/data/article_store.py:58`, et `docs/steps/12-ingestion-incrementale-watermark.md` : « Zéro nouvel état, rien à synchroniser »).
- Elle écrit ces articles seuls, avec `INSERT OR IGNORE` : **la base dédoublonne** par sa contrainte d'unicité (`app/ingest/ingester.py:36-63`).
- Rien n'est jamais rejoué.
- Ce que brief09 n'avait pas, et que K-B garde : la couche brute immuable (exigée par la v0, et qui permet de reconstruire la base) et la trace des doublons (`INSERT OR IGNORE` les jetait sans trace).

**Proposition** : la mécanique de brief09, avec le brut en plus.
1. L'import ne lit que les fichiers bruts **pas encore importés**, notés dans un registre en base. Un fichier lu y entre même s'il n'a produit aucun item (sinon il serait relu et rejeté à chaque import) ; un fichier sauté faute de lecteur n'y entre pas (il sera lu quand le lecteur existera, par exemple TLDR avec #57). Aujourd'hui, la table `collection` n'a une ligne que pour un fichier qui a produit un item (`import_items.py:77`) : elle ne suffit pas comme registre.
2. **La base dédoublonne** par ses contraintes (`INSERT … ON CONFLICT DO NOTHING`). Une ligne non écrite est un doublon, tracé dans le journal d'import avec sa règle. Il faut ajouter une contrainte pour « même CVE dans une source », que SQL ne porte pas aujourd'hui. `merge.py` se réduit à ce qu'aucune contrainte ne sait faire : normaliser les URL et les dates, et remplacer un papier arXiv par sa révision plus récente.
3. La **reconstruction complète** reste possible et exceptionnelle : supprimer la base, puis `kb create-db` et `kb import`. Pas d'option à ajouter pour la v0.

**Effets sur les autres constats.**
- W2 disparaît.
- W5 diminue sans disparaître : les anciens fichiers ne sont plus relus, mais chaque **nouveau** fichier d'une source qui republie tout (catalogue CISA, classement, page de 100 releases) redonne presque tous ses items comme doublons.
- D7 se règle : un conflit d'URL devient un doublon tracé, plus une erreur qui fait échouer l'import.
- D6 reste à décider : la base garderait le premier vu, comme aujourd'hui.

**Question ouverte, à trancher par Sabine** : dériver aussi le repère de collecte de la base, comme brief09, plutôt que de `collection_state.json` ? Ce serait une seule mémoire au lieu de deux. Mais la collecte dépendrait alors de la base, alors qu'aujourd'hui on collecte sans base. Pas de recommandation tranchée.

**Coût** : 3 à 4 h avec les tests (estimation non relue), pour réécrire `merge.py`, `import_items.py` et leurs tests, en retirant du code. C'est une décision structurante : `/adr-ls` dans la PR qui la code. Elle change le contrat écrit en tête de `import_items.py:1-6`.

| Décision | Fin du rejeu complet : **retenue**. Proposition 1-3 : à valider. Question du repère de collecte : à trancher. |
|---|---|

### Autres constats

| # | Ce qui est | Plus simple | Coût | Décision |
|---|---|---|---|---|
| W1 | Deux horloges. `collect_all_sources` reçoit `now` (`cli.py:105`), mais `ArxivSource.fetch` relit l'heure (`arxiv_source.py:44`), comme `TldrSource` (`tldr_source.py:40`, `73-74`). La fin de la fenêtre arXiv et le nom du fichier brut viennent donc de deux instants différents. Les tests TLDR remplacent `current_day` par un faux (`test_tldr_source.py:38`) ; le test arXiv `test_the_window_ends_now` lit la vraie horloge avec une tolérance (`test_arxiv_source.py:88-94`), c'est un test qui dépend de l'heure. | Passer `now` à `fetch(last_collected_at, now)`, dans le `Protocol` de `collect.py:30-42`. | 1 h : 6 sources et leurs tests. | |
| W2 | `kb import` relit et revalide **tout** le brut à chaque fois (`raw_items.py:64-79`). C'est simple et rejouable (même brut → même base, `import_items.py:4-5`), mais le coût croît avec le brut. Le volume n'a pas été mesuré. | Remplacé par W0. | — | Voir W0 |
| W3 | Le brut TLDR est collecté chaque jour (3 pages d'environ 80 Ko) mais jamais lu : aucun lecteur `tldr_*` n'est déclaré, et le dossier est sauté comme « source without a reader » (`raw_items.py:65-68`) ; lecture dans #57. | Rien à changer si #57 vient vite ; sinon, suspendre la collecte TLDR jusqu'à #57 (RGESN 1.6 : ne pas collecter ce qui ne sert pas). | 0, ou 5 min | |
| W4 | Chaque source est lue deux fois : à la collecte, pour refuser une page qui n'est pas ce qu'on attend (`cisa_kev_source.py:44`, `github_most_starred_source.py:32`…), puis à l'import. | C'est voulu : échouer avant d'écrire un brut faux. À garder. | 0 | |
| W5 *(2nd passage)* | **Le journal d'import grossit à chaque collecte.** Chaque doublon retiré y est écrit (`import_items.py:174-185`). Or chaque nouveau catalogue CISA, classement ou page de releases relu produit surtout des `same_source_id` attendus : `import-log.jsonl` noiera les vrais rejets. | W0 retire les doublons dus à la relecture des anciens fichiers. Restent ceux des sources qui republient tout : compter les doublons d'un même identifiant de source sans les écrire un par un, et n'écrire que les rejets et les doublons entre sources différentes. | 30 min, après W0 | |
| W6 *(2nd passage)* | **Sobriété de la collecte (RGESN 1.6).** CISA retélécharge et stocke le catalogue entier, environ 1 Mo (`cisa_kev_source.py:13`), à chaque modification. Les releases stockent la page de 100 releases, 2,2 Mo pour claude-code (`github_api.py:10`), dès qu'une seule est nouvelle (`github_releases_source.py:33-48`). Ces volumes viennent des commentaires du code, pas d'une mesure. | Mesurer d'abord avec #25. Si le volume pèse : réduire `per_page` des releases après la première collecte, ou ne garder du brut CISA que les lignes ajoutées. Le second va contre l'immuabilité du brut « tel que publié » : à décider. | Mesure : avec #25 ; correction : 1 h | |
| W7 | **Pas de migration du schéma.** `kb create-db` crée la base d'un bloc et refuse une base existante (`database/__init__.py:18-43`). Tout changement de schéma oblige à supprimer la base, puis à tout réimporter. Avec W0, c'est acceptable tant que la base ne contient que des données d'essai. | Des migrations numérotées en préfixe (`database/migrations/001_create_schema.sql`, `002_seed_sources.sql`, …). Le numéro de la dernière migration appliquée est gardé dans `PRAGMA user_version` (un entier de l'en-tête SQLite). Chaque migration suivante est appliquée dans sa transaction. Environ vingt lignes de Python, sans dépendance : Alembic suppose SQLAlchemy, que K-B n'utilise pas. Ce que ça ne couvre pas : un lecteur corrigé ou enrichi, qui demande de relire le brut, donc une reconstruction. brief09 avait des migrations additives (`docs/steps/16-migration-additive-colonne-db-existante.md`). À introduire au premier changement de schéma une fois la base remplie de données réelles, après #25. | 1 h, au moment voulu | |

## 2. Étapes génériques communes à toutes les sources

Déjà communes : le téléchargement (`http_download.download`), l'écriture immuable du brut
(`raw_store.write_new_raw_file`), la date de dernière collecte par source (`collect.py:66-92`),
l'item commun (`items.Item`), la fusion et l'import.

| # | Ce qui est | Plus simple | Coût | Décision |
|---|---|---|---|---|
| G1 | **Trois traitements différents d'une entrée invalide, à l'import.** arXiv écarte l'entrée et la journalise en WARNING, mais elle n'entre pas dans le journal d'import (`arxiv_papers.py:41-47`). CISA et GitHub refusent **tout le fichier** pour une seule entrée (`cisa_kev.py:44`, `github_releases.py:31-34`, `github_advisories.py:36`). Une entrée refusée par `Item` est écartée seule et va dans le journal d'import (`raw_items.py:93-102`). Exception voulue : un classement des plus étoilés incomplet est refusé en entier, sinon il ferait croire à des sorties du top (`github_most_starred.py:30-32`). | Une règle commune à l'import, dans `raw_items.py` : le lecteur rend les entrées, chaque entrée invalide est écartée seule et tracée dans le journal d'import, sauf pour le classement, qui reste refusé en entier. **Ne ferme ni #61 ni #77** : leurs critères portent sur la collecte (`fetch` : `all_items_invalid`, date inchangée, rien dans `raw/`), qui reste à traiter dans ces issues. | 2 h avec #85, pour l'import seulement. | |
| G2 | **Ajouter une source touche 5 endroits** : `X_source.py`, `X.py` (lecteur), `items.convert_X`, l'aiguillage `raw_items.list_readers_by_source` (`raw_items.py:113-138`) et `collect.SOURCES` (`collect.py:45-57`), avec leurs imports (`items.py:17-21`, `raw_items.py:13-31`). Pour une nouvelle origine, 2 de plus : `SourceCode` (`items.py:24-26`) et `seed_sources.sql`. | Que chaque **classe** source porte son lecteur (par exemple `read_items(raw) -> list[Item]`) : `raw_items` n'aurait plus d'aiguillage, et l'ajout d'une source se ferait en 2 fichiers et une ligne de `SOURCES`. **À concevoir avec G3** : si le lecteur est retrouvé en parcourant les instances de `SOURCES`, #87 reste ouvert. Il faut un lecteur par classe, retrouvé par le nom du dossier brut. | 2 h, à faire avec #85 qui touche déjà chaque lecteur. | |
| G3 | **La lecture dépend de la collecte** : `raw_items.py:17` importe `collect.SOURCES`. Seul le brut des sources **actuellement suivies** est lu ; un dossier d'une source retirée est sauté (`raw_items.py:65-68`, premier cas de #87). Second cas de #87 : un ancien classement est relu avec le `RANKING_SIZE` courant (`raw_items.py:135`) et rejeté si la taille a changé. | Aiguiller par préfixe du dossier brut (`github_releases_*` → lecteur des releases), indépendamment de `SOURCES`. Le dépôt viendrait alors du brut (`html_url`), une donnée non fiable : à valider (`code.md`, Sécurité). Le second cas demande de lire la taille dans le brut lui-même (nombre d'entrées demandé), pas dans la constante. | 1 h 30 ; ferme #87 si les deux cas sont faits. | |
| G4 | « Rien de nouveau → `None` » et l'avertissement « page pleine » sont écrits deux fois, presque à l'identique (`github_releases_source.py:33-48`, `github_advisories_source.py:50-63`). | Deux occurrences : la règle de `code.md` dit de factoriser à la troisième. À garder. | 0 | |
| G5 *(2nd passage)* | **L'avertissement « page pleine » est sauté à la première collecte** : `return` arrive avant le contrôle (`github_releases_source.py:33-34`, `github_advisories_source.py:52-53`). Une première collecte tronquée à 100 serait silencieuse. | Faire le contrôle de page pleine avant le `return` de la première collecte. | 30 min avec tests | |

## 3. Étapes spécifiques à chaque source

| # | Ce qui est | Plus simple | Coût | Décision |
|---|---|---|---|---|
| S1 | **Double validation.** Chaque lecteur valide à la main dans une `dataclass` (`github_releases.py:37-70`…), puis `Item` revalide en Pydantic. Une fois #85 fait tel qu'il est écrit, on aura deux modèles Pydantic par source : le modèle du lecteur, puis `Item`. | (a) #85 tel quel : un modèle Pydantic par source, puis `Item`. (b) Pas de modèle intermédiaire : le lecteur passe du dictionnaire brut à `Item`, et les contrôles propres à la source (préfixe d'URL, format GHSA) deviennent des types annotés. (b) supprime les 5 `dataclass` (volume de lignes non mesuré) ; (a) garde un modèle par source, utile seulement si un champ du brut sert ailleurs que dans `Item` (voir S2). | (a) 2,5 h (estimation de #85) ; (b) 3 h. | |
| S2 | **Des champs lus, validés, puis jamais utilisés** : `is_prerelease` et `tag_name` hors titre (`github_releases.py:18,22`), `severity` et `packages` (`github_advisories.py:23,28`), `version` (`arxiv_papers.py:27`), `rank`, `stars`, `topics` et `created_at` (`github_most_starred.py:16-23`). Le docstring de `github_most_starred_source.py:21-24` annonce une comparaison de classements qui n'existe pas. Hors de ce constat : `vendor_project` et `product` de CISA (`cisa_kev.py:23-24`), que #84 doit décider de stocker ou non. | Ne lire que ce qui va dans `Item` (RGESN 1.6, YAGNI) ; un champ entre quand une question de veille s'en sert, selon la règle du journal du 02/10. Le brut garde tout de toute façon. Effet sur W4 : lire moins de champs à la collecte affaiblit un peu le contrôle « cette page est bien ce qu'on attend ». | Inclus dans S1 (b) ; sinon 30 min. | |
| S3 | **Code mort** : le filtre par date de CISA (`cisa_kev.py:45-52`, paramètre `last_collected_at`) n'est appelé qu'avec `None` dans `src` (`cisa_kev_source.py:44`, `raw_items.py:123`). Seuls deux tests s'en servent (`test_cisa_kev.py:22`, `:73`). | Supprimer le paramètre, le filtre et les deux tests ; la fusion retire déjà les doublons du catalogue entier. | 15 min | |
| S4 | **#85 et #92 se contredisent.** #85 veut des messages « champ, valeur » ; #92 interdit la valeur reçue dans le motif d'un rejet. Aujourd'hui, des lecteurs recopient des valeurs du brut qui finissent dans le journal d'import par `raw_items.py:91` : `{full_name!r}` (`github_most_starred.py:56`), `{ghsa_id!r}`, `{cve_id!r}` et `{severity!r}` (`github_advisories.py:44,49,55`), `{stored_date!r}` (`github_dates.py:16`, utilisé par les trois lecteurs GitHub), `{cve_id!r}` et `{row['dateAdded']!r}` (`cisa_kev.py:60,65`). Côté arXiv, `{entry_id!r}` (`arxiv_papers.py:60`, `87`) et `{text!r}` (`arxiv_papers.py:121`) vont en WARNING sur stderr, pas dans le journal d'import (`arxiv_papers.py:43-46`). | Proposition pour accorder : une valeur qui vient **de K-B ou du protocole** (URL demandée, code HTTP, nom de fichier brut, nombre attendu / trouvé) peut s'écrire, c'est l'observé que demande `MEMORY.md`. Une valeur qui vient **du contenu collecté** ne s'écrit jamais, ni dans le journal d'import ni dans les logs : on écrit le champ et le type d'erreur (`entry 3: title: string_too_short`). Le critère de #85 devient alors « champ, type d'erreur », et #92 s'étend aux messages des lecteurs. | 15 min pour réécrire les critères ; le code suit avec #85. | |
| S5 | **Le motif `owner/name` existe en quatre versions** : `github_releases_source.py:14`, `github_most_starred.py:10`, `items.RepositoryName` (`items.py:35`, motif différent) et `schema.sql:71` (`GLOB '?*/?*'`). La garde `".." in` est écrite deux fois (`github_releases_source.py:21`, `github_most_starred.py:54`). | Un seul type Python que les lecteurs réutilisent ; le `CHECK` SQL reste (défense en profondeur). **Pas faisable avant F1 ou G2** : `items.py:20` importe `github_most_starred`, qui ne peut donc pas importer `items` sans import circulaire. | 15 min après F1 ou G2 | Débloqué par #97 (F1 fait), 2026-10-06. Lignes citées : état avant #97. |
| S6 *(2nd passage)* | **Le format CVE est écrit en trois endroits** : `cisa_kev.py:9`, `items.py:34` (`CveId`) et `schema.sql:88`. Le lecteur d'alertes GitHub importe `CVE_ID` depuis le lecteur CISA (`github_advisories.py:8`) : deux sources sont couplées. | Comme S5 : un seul type Python, après F1 ou G2 ; le `CHECK` SQL reste. | 15 min, avec S5 | Débloqué par #97 (F1 fait), 2026-10-06 : `CVE_ID` est dans `items.py`, à côté de `CveId`. Lignes citées : état avant #97. |
| S7 *(2nd passage)* | **arXiv bloqué au-delà de 2 000 papiers** (#71, hors E1) : si la fenêtre dépasse le plafond, la source échoue et sa date reste (`arxiv_source.py:52-56`) ; la fenêtre suivante est plus large encore. | Déjà porté par #71. | 0 ici | |

## 4. La base de données et son schéma

| # | Ce qui est | Plus simple | Coût | Décision |
|---|---|---|---|---|
| D1 | **L'exclusivité des sous-types n'est vérifiée nulle part.** `docs/stockage.md:206-209` et le journal du 02/10 (PR de #7) disent que le code de fusion vérifie deux contraintes : un item a au plus un sous-type ; DÉPÔT ne concerne que GitHub et GH Archive, VULNÉRABILITÉ que CISA KEV et GitHub. `merge.py` ne vérifie ni l'une ni l'autre. Le seul validateur, `items.py:62-66`, vérifie qu'un CVE implique une vulnérabilité. Aujourd'hui, aucun convertisseur ne produit un item à deux sous-types (`items.py:69-145`), mais rien ne l'empêche. | (a) Un validateur de plus dans `Item` : pas à la fois `is_vulnerability` et `repository_name`, et chaque sous-type limité à ses `source_code`. On corrige alors la doc : « vérifié par `Item` », pas par la fusion. (b) Remplacer `is_vulnerability` et `repository_name` par un champ `kind: Literal["vulnerability", "repository"] \| None` : l'exclusivité est alors portée par le type. (c) Des déclencheurs SQL : plus lourd, et SQLite seulement. | (a) 30 min avec tests et doc ; (b) 1 h 30. | |
| D2 | **Un sous-type n'est jamais retiré.** Si un item change de nature d'un import à l'autre, l'upsert (`import_items.py:93-104`) ajoute la nouvelle ligne de sous-type sans supprimer l'ancienne. Aucune source ne le fait aujourd'hui. | Avec D1 (a) ou (b), supprimer les lignes de sous-type de l'item avant de réécrire la sienne, comme `write_authors` le fait pour les auteurs (`import_items.py:129`). | 20 min | |
| D3 | `source_code = 'github'` regroupe trois natures d'items : releases (identifiant numérique), alertes (GHSA) et dépôts (`owner/name`) (`items.py:106,121,137`). Leurs `source_item_id` partagent la contrainte `UNIQUE (source_code, source_item_id)` (`schema.sql:36`). Les formats ne se chevauchent pas aujourd'hui, mais rien ne le garantit. Une release n'a pas de sous-type : elle n'est reconnaissable que par l'absence des deux autres. | À décider avant #21 : l'API devra filtrer « les releases ». Soit un préfixe dans `source_item_id` (`release:123`), soit une nature explicite (voir D1 (b), avec une valeur `release`). | Avec D1 (b) : + 30 min | |
| D4 | Les tables `highlight` (Zotero, #15) et `star_gain` (GH Archive, #16) existent pour des sources pas encore codées (`schema.sql:58-82`). | C'est un modèle Merise documenté, à garder. Elles ne coûtent rien tant qu'elles sont vides ; les retirer obligerait à remettre à jour le MCD, le MLD et le MPD. | 0 | |
| D5 | Rien n'est jamais supprimé de `item` : un brut retiré ne retire pas ses items. C'est le sujet de #83 (purge). | Rien de plus que #83. | 0 | |
| D6 *(2nd passage)* | **La fusion garde le premier vu** (`merge.py:33-34`, `52`) : une correction faite plus tard par la source (description CISA, description d'un dépôt, corps d'une release) n'entre jamais dans la base. Seul arXiv fait exception (nouvelle révision). C'est un choix documenté, mais sa conséquence pour « quoi de neuf » (#21) n'a pas été discutée. | À décider avant #21 : garder le premier vu, ou garder le dernier vu pour les champs descriptifs. | 0 à décider ; 1 h si on change | |
| D7 *(2nd passage)* | **Hypothèse, non vérifiée par un test** : `url` est `UNIQUE` dans toute la table (`schema.sql:27`) et l'upsert réécrit `url` (`import_items.py:32`). Comme rien n'est supprimé (D5), un item ancien et un nouvel item d'identifiant différent qui partageraient une URL feraient échouer **tout** l'import, car la fusion ne voit que le brut lu (`merge.py:54-58`). | Écrire d'abord le test qui le montre ; s'il échoue, traiter le conflit d'URL comme un doublon tracé plutôt qu'une erreur. | 30 min pour le test ; 1 h si correction | |

## 5. Organisation des fichiers de code

24 fichiers `.py` à plat dans `src/k_b/` (23 modules, plus `__init__.py`), plus `database/` pour
le SQL. Les dépendances vont dans un seul sens, à une exception près.

| # | Ce qui est | Plus simple | Coût | Décision |
|---|---|---|---|---|
| F1 | `items.py` importe les 5 `dataclass` des lecteurs et porte les 5 `convert_*` (`items.py:17-21`, `69-145`) : le modèle commun connaît chaque source. C'est aussi ce qui bloque S5 et S6 (import circulaire). | Mettre chaque `convert_X` à côté de son lecteur (ou dans la source, voir G2) : `items.py` ne garde que `Item` et ses types, que les lecteurs peuvent alors importer. | Inclus dans G2 | Fait par #97, 2026-10-06 : chaque `convert_*` est à côté de son lecteur. Lignes citées : état avant #97. |
| F2 | `raw_items.py` (lecture) importe `collect.py` (collecte) : c'est la dépendance qui remonte le courant (G3). | Voir G3. | Inclus dans G3 | |
| F3 | Un module de lecture et un module de collecte par source, à plat, avec des préfixes (`github_*` : 8 fichiers). | (a) Garder à plat, c'est lisible avec 23 modules. (b) Un sous-paquet `sources/` avec un fichier par source (collecte et lecture ensemble). (b) se justifie si G2 est retenu ; sinon, le déplacement n'apporte rien. | (b) 1 h, surtout des imports | |

## 6. Pertinence de chaque test

251 tests (`pytest --collect-only`), 25 fichiers. Verdict par fichier. Seuls les tests à
fusionner, remplacer ou supprimer sont nommés.

| Fichier | Verdict | Raison |
|---|---|---|
| `test_package.py` | **supprimer** | Vérifie que `k_b` s'importe ; les 250 autres tests le font déjà. |
| `test_schema.py` | **fusionner** dans `test_database.py` | `test_the_schema_and_the_sources_load_with_every_expected_table` est le seul test qui vérifie la liste des tables, dont `highlight` et `star_gain` : à garder, déplacé. Son compte des 7 sources double `test_database.py:9` : à retirer. `test_two_sources_can_share_a_cve` est à garder (décision de Sabine). `test_a_cve_is_found_through_its_index` est à **remplacer** : l'index `vulnerability_cve` est un choix de K-B (« indexé », `stockage.md:198`), à vérifier dans `sqlite_master` plutôt que par le plan de requête de SQLite. |
| `test_database.py` | garder | Création, refus, clés étrangères, échec sans fichier : des risques réels. |
| `test_items.py` | garder, sauf un | `test_an_item_cannot_be_changed` vérifie la configuration `frozen=True` de K-B ; c'est à peu près une ligne de configuration testée par une ligne de test. Suppression défendable, faible enjeu. `test_the_source_codes_are_those_of_the_database` est à garder : il tient deux copies d'une même connaissance alignées. |
| `test_tracked_repositories.py` | garder un sur deux | `test_the_tracked_repositories_are_those_of_docs_sources` est à **supprimer** : il recopie la constante, et le changer revient à changer la liste. |
| `test_github_api.py` | garder, sauf un | `test_the_response_is_returned_unchanged` est à **supprimer** : il double `test_http_download.py:46`. |
| `test_http_download.py` | garder | La frontière réseau : préfixe, redirection, taille, en-têtes. |
| `test_arxiv_source.py`, `test_cisa_kev_source.py` | garder, **alléger** | Dans `test_the_request_names_k_b_and_has_a_timeout`, l'agent utilisateur et le délai doublent `test_http_download.py:50`. Garder l'URL et les en-têtes propres à la source, retirer le reste. `test_the_window_ends_now` dépend de l'heure : il change avec W1. |
| `test_*_source.py` : `…_is_a_source_of_kb_collect` (5 tests : arxiv, advisories, most_starred, releases, tldr) | **fusionner** en un test dans `test_collect.py` | Un seul test qui liste les noms attendus de `SOURCES`. |
| `test_cisa_kev.py` | garder, sauf deux | `test_only_vulnerabilities_added_since_the_day_before…` et `test_a_vulnerability_dated_the_day_before…` sont à **supprimer avec le code mort** (S3). |
| `test_github_most_starred.py` | garder | Les assertions sur `stars`, `created_at` et `topics` (`:29-31`) tombent si S2 est retenu. |
| `test_github_releases.py`, `test_github_advisories.py`, `test_arxiv_papers.py` | garder | Ils seront adaptés par #85. Les tests « … not kept » (login, personnes créditées) sont des tests RGPD : à garder. |
| `test_github_releases_source.py`, `test_github_advisories_source.py`, `test_github_most_starred_source.py`, `test_tldr_source.py` | garder | La fenêtre de collecte, « rien de nouveau », l'avertissement de page pleine, les redirections TLDR : des règles de K-B. |
| `test_github_dates.py`, `test_raw_store.py`, `test_collect.py`, `test_merge.py`, `test_raw_items.py` | garder | Chaque test porte une règle écrite (fusion, immuabilité du brut, panne isolée). |
| `test_cli.py`, `test_import_items.py` | garder, **un doublon** | `test_cli.py:198` et `test_import_items.py:219` vérifient tous deux qu'une base absente est refusée et pas créée. Le premier vérifie en plus le code de sortie et le message, le second le type `MissingDatabaseError`. Garder le premier, retirer de l'autre l'assertion « pas créée », ou garder les deux : faible enjeu. |

Bilan si tout est retenu :
- 6 tests supprimés : `test_package`, `frozen`, `tracked…docs_sources`, `github_api` (réponse inchangée), et les 2 tests CISA du code mort ;
- 1 test remplacé (l'index CVE) ;
- 1 fichier fusionné (`test_schema.py` dans `test_database.py`) ;
- 5 tests fusionnés en un ;
- 2 tests allégés.

## Ce qui n'a pas été vérifié

- Le volume du brut et la durée de `kb import` sur des données réelles (W2, W6).
- D7 est une hypothèse tirée de la lecture du code, sans test qui la montre.
- Les coûts sont des estimations de Claude ; le second passage les a jugés plausibles, sans les
  mesurer.
- Le nombre de tests après les suppressions n'a pas été recompté par `pytest`.
