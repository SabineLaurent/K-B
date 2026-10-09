# Clarification : de ce que donnent les sources au modèle de la base

Séance du 2026-10-07 (mission « clarifier ce que K-B doit faire »). Rien n'est codé : ce document
relève les faits, note les parcours de Sabine et consigne ses décisions de modèle. Les décisions
sont aussi au [journal ADR](ADR/journal-decisions-projet.md).

## 1. Ce que les sources donnent

Le détail, champ par champ, est en [annexe](#annexe--les-sources-champ-par-champ).

- Cinq sources ont un lecteur : CISA KEV, GitHub (alertes, releases, plus étoilés) et arXiv.
  TLDR est collecté brut, sans lecteur (« Lire les articles des pages TLDR brutes », #57) ; un
  article TLDR est un résumé qui pointe vers un article d'ailleurs (`openai.com`, `x.com`,
  `github.com`, `arxiv.org`…). Clips
  Obsidian, Zotero et GH Archive ne sont pas encore collectés.
- Une seule table `item` reçoit tout. Deux sous-types existent : `vulnerability` (CVE) et
  `repository` (nom du dépôt). Une release n'a pas de sous-type : son dépôt n'est écrit que
  dans son titre.
- Le code source `github` regroupe trois natures d'items : alerte, release et dépôt.
- Les lecteurs lisent des champs que la base ne garde pas : `vendorProject` et `product` de CISA,
  `severity` et les paquets des alertes GitHub, le rang, les étoiles et les topics des plus
  étoilés, la version d'un papier arXiv. Aucun code n'écrit dans `star_gain`.

## 2. Les parcours de Sabine en v0

En v0, il n'y a pas de LLM : on ne pose pas de question en langage naturel. K-B offre **un champ
de recherche** (titre et résumé), **des filtres** (période, type d'item, source) et **trois
classements** (vent en poupe, plus étoilés, plus forkés). Les parcours ci-dessous disent lequel des
trois sert. Version légère ; la version formelle (user stories, wireframes) relève de C14 et E4.

| Parcours | Moyen en v0 |
|---|---|
| P1 | filtre de période |
| P2, P3 | filtre de type (release, vulnérabilité), combiné à la recherche (`langgraph`) |
| P4 | croisement par CVE, affiché avec la vulnérabilité |
| P5, P7, P8 | classement |
| P6, P9 | champ de recherche |

Effet sur le modèle : un index plein texte sur `item.title` et `item.summary` (FTS5 dans SQLite,
`tsvector` dans PostgreSQL), et un type d'item qui se filtre directement.

| # | Question | Ce qu'elle demande à la base | Aujourd'hui | LLM ? |
|---|---|---|---|---|
| P1 | Quoi de neuf depuis N jours, toutes sources ou par thème ? | une date par item pour filtrer | `published_at` vide pour certains items ; règle à fixer (#21) | non |
| P2 | Quelles nouvelles versions de mes outils ? | relier une release à son dépôt | le dépôt n'est que dans `item.title` | non |
| P3 | Quelles failles touchent mes outils, mes paquets ? | les paquets touchés par une alerte | paquets lus, non gardés | non |
| P4 | Cette faille est-elle exploitée activement ? | croiser CISA et GitHub par CVE | `vulnerability.cve`, non unique : possible | non |
| P5 | Quels dépôts ont le vent en poupe ? Tous les dépôts, via GH Archive, par fenêtre de 3 jours | étoiles gagnées par dépôt et par fenêtre | `star_gain` existe, vide ; GH Archive pas codé | non |
| P6 | Quels papiers récents sur un sujet (prompt injection…) ? | le mot-clé ou le texte du papier | titre et résumé gardés ; mot-clé de la requête non gardé | non par mots-clés, oui par le sens |
| P7 | Quels sont les dépôts les plus étoilés (top 10) ? | les étoiles d'un dépôt à une date | `stargazers_count` lu, non gardé | non |
| P8 | Quels sont les dépôts les plus forkés de GitHub (top 10) ? | les forks d'un dépôt à une date, sur tout GitHub | non collecté : la recherche est triée par étoiles ; une requête triée par forks en plus | non |
| P9 | Quoi de neuf dans l'écosystème LangChain ? | les dépôts et paquets suivis, plus les items qui citent `langchain` ou `langgraph` | liste dans `tracked_repositories.py` ; recherche dans le texte à faire | non par mots-clés, oui par le sens |

- **Question ouverte** : « quels sujets cartonnent en ce moment ? ». LLM : non si l'on compte des
  étiquettes existantes (topics GitHub, mots-clés arXiv, rubriques ou domaines TLDR), oui pour des
  thèmes que personne n'a étiquetés. Ce qu'on compte n'est pas décidé.
- **En v0 depuis la séance 4** : Zotero et clips, cherchables par `kb search` (LLM : non ; voir
  « Collecte large et sources choisies »). La recherche dans les surlignages n'est pas décidée.
- **Pas en v0** : ce qu'une fiche cite
  (non) ; le doublon entre un résumé TLDR et son article d'origine (non, par l'URL) ; d'où vient
  une affirmation de ma fiche (non si la fiche cite ses items, oui s'il faut la retrouver à partir
  du texte).
- La colonne LLM ne décide pas du modèle : ce qui le décide, c'est si la donnée est collectée et
  gardée. Elle dit seulement ce qui attend le LLM, et la place à laisser à des embeddings.

## 3. Pistes en réflexion (non décidées)

Rien de cette section n'est décidé : Sabine y réfléchit avant de trancher. Les recommandations
sont celles de la session.

### Trois axes à ne pas confondre

| Source | Type de source (`source.source_type`) | Types d'items qu'elle donne (piste 3a) |
|---|---|---|
| GitHub | service web | `vulnerability` (alertes), `release`, `repository` |
| arXiv | service web | `article` |
| CISA KEV | fichier | `vulnerability` |
| Clips Obsidian | fichier | `article` |
| tldr.tech | scraping | `summary` |
| Zotero | base de données | `article` |
| GH Archive | big data | `repository` (et des mesures d'étoiles) |

- Le type de source décrit la source : il vit dans `source`, comme aujourd'hui.
- Le type d'item décrit l'item : il ne se déduit pas de la source (GitHub en donne trois).
- Un même type d'item arrive par plusieurs sources : c'est là que se jouent doublons et
  croisements (CVE pour les failles, URL pour les dépôts et les articles).

### Types d'items

- **Constat** : une release n'a pas de sous-type, elle se reconnaît par élimination (D3). Un
  résumé TLDR prend l'URL de l'article dont il parle (`docs/stockage.md:59`) ; avec `url`
  unique dans toute la table, un résumé et son article d'origine ne peuvent pas coexister. Les
  vrais liens TLDR ont la forme des items existants : `arxiv.org/abs/2609.38149`,
  `github.com/NVIDIA/OpenShell` (aucun n'est dans la collecte du 2026-10-07).
- **3a, types** — recommandé : `article` (arXiv, clip, Zotero), `summary` (TLDR),
  `vulnerability` (CISA, alerte GitHub), `repository`, `release`. Étoiles et forks sont des
  mesures sur un dépôt, pas des items.
- **3b, colonne ou sous-type** — recommandé : `item.kind` obligatoire (CHECK sur les cinq
  valeurs), plus une sous-table pour les types qui ont des champs propres (`vulnerability`,
  `repository`, et `release` avec le dépôt). Écartés : sous-tables seules (jointure pour filtrer,
  rien pour `article` et `summary`) ; colonne seule (champs propres souvent vides dans `item`).
- **3c, lien résumé → article** — recommandé : le résumé a sa propre identité
  (`ai/2026-10-06#2`), son `url` est celle de l'article, `UNIQUE (source_code, url)` remplace
  `UNIQUE (url)`, et le lien se fait par jointure sur l'URL. Écartés : clé étrangère vers
  l'article (l'ordre d'import compte) ; résumé comme simple mention (le modèle change plus).

Exemple, avec les vrais items du 2026-10-07 (ligne 7 inventée) :

| item_id | source_code | source_item_id | kind | url |
|---|---|---|---|---|
| 1 | cisa_kev | CVE-2026-88779 | vulnerability | nvd.nist.gov/vuln/detail/CVE-2026-88779 |
| 2 | github | GHSA-fjqc-hq36-qh5p | vulnerability | github.com/advisories/GHSA-fjqc-hq36-qh5p |
| 3 | github | 404958910 | release | github.com/anthropics/claude-code/releases/tag/v2.1.292 |
| 4 | github | codecrafters-io/build-your-own-x | repository | github.com/codecrafters-io/build-your-own-x |
| 5 | arxiv | 2605.00955 | article | arxiv.org/abs/2605.00955 |
| 6 | tldr | ai/2026-10-06#2 | summary | openai.com/index/eu-text-provenance/ |
| 7 | tldr | ai/2026-10-08#5 | summary | arxiv.org/abs/2605.00955 |

### Source, collecte et lancement

- **Constat** : SOURCE et COLLECTE ne sont pas reliées au MCD (`docs/stockage.md:95-96`). Une
  collecte en base est un fichier brut (`docs/stockage.md:107`), pas un lancement de
  `kb collect` : elle appartient à une seule source. La source d'une collecte ne se lit que dans
  son chemin ou par ses items : `item.source_code` dépend de `item.collection_id`.
- **Idée de Sabine** : SOURCE et LANCEMENT en plusieurs à plusieurs, la table de liaison portant
  les items par source et par date de collecte. Cette table de liaison est le fichier brut : une
  source × un lancement. Réifiée, elle devient l'entité COLLECTE.

```
SOURCE ──0,n── (FOURNIR) ──1,1── COLLECTE ──1,1── (DÉCLENCHER) ──1,n── LANCEMENT
                                    │ 1,n
                                (EXTRAIRE)
                                    │ 1,1
                                  ITEM
```

- PUBLIER (SOURCE → ITEM) devient redondante au MCD.
- Recommandations : FOURNIR maintenant (`collection.source_code`, au niveau de la table
  `source`) ; LANCEMENT et DÉCLENCHER plus tard, avec la surveillance des exécutions (aucun
  parcours v0 ne s'en sert) ; `item.source_code` gardé pour les contraintes d'unicité, contrôlé
  par une clé étrangère composée (`collection_id`, `source_code`) ; une page TLDR reste une
  collecte.

### Le MCD de Sabine (séance de l'après-midi)

**Décidé par Sabine** :

- **SOURCE ─0,n─ (FOURNIR) ─1,1─ DONNÉE BRUTE ─1,n─ (CONTENIR) ─1,1─ ITEM.** Une donnée brute
  est un fichier de `raw/` : le `.xml` d'arXiv, le `.csv` de CISA, un `.html` de TLDR (une
  édition, un jour). Un item est une entrée de ce fichier : une `<entry>`, une ligne, un
  `<article>`. « Donnée brute » remplace « collecte », qui faisait penser au lancement de
  `kb collect`. Pas d'entité LANCEMENT pour l'instant.
- **Sous-catégorie d'une source** : un attribut `flux` de DONNÉE BRUTE, qui vaut le nom du
  dossier brut (`tldr_ai`, `tldr_infosec`…). Écartés : une source par édition (GitHub en
  compterait une douzaine) ; une entité FLUX (pas d'attribut propre à porter pour l'instant).
  Les filtres d'arXiv ne sont pas une sous-catégorie : une requête, un flux.
- **GitHub est mis de côté** : le modèle se pose d'abord sur arXiv, CISA et TLDR.
- **CISA KEV est un catalogue d'état**, pas un flux de nouveautés : chaque collecte télécharge le
  catalogue entier (`cisa_kev.py:49-70`) ; une ligne est modifiée sur place (le brut du
  2026-10-07 est trié par `dateAdded` décroissant, sans CVE en double ; `knownRansomwareCampaignUse`
  change en silence, 41 fois d'octobre 2023 à juillet 2024 selon
  [GreyNoise](https://www.greynoise.io/blog/unveiling-vulnerability-insights-from-the-cisa-kev-catalog-at-bsideslv)).
  À chaque collecte :
  - une ligne nouvelle crée un item ;
  - une ligne connue garde son identité (`item_id`, CVE) ; tout le reste, titre compris, est
    remplacé par la dernière version si le contenu diffère, et `revised_at` prend la date de la
    collecte qui a constaté le changement ; une ligne identique ne change rien ;
  - une ligne connue absente du catalogue est marquée retirée : `withdrawn_at` prend la date de la
    collecte qui a constaté son absence ; si elle réapparaît, `withdrawn_at` est vidé et
    `revised_at` daté ;
  - l'historique des versions n'est pas en base : le brut le garde (RGESN 1.6).

**Conséquences** : pour un catalogue d'état, CONTENIR relie l'item à la donnée brute qui a
apporté sa version actuelle. La règle « premier vu ou dernier vu » (D6) se règle par nature de
source :

| Nature | Sources | Item déjà vu |
|---|---|---|
| flux de nouveautés | TLDR, alertes GitHub, releases | inchangé (premier vu) |
| catalogue d'état | CISA (et le top 100 GitHub, mis de côté) | dernière version, `revised_at` daté, `withdrawn_at` si absent |
| flux avec révisions | arXiv | remplacé si `updated` est plus récent (déjà le cas) |

P1 filtre alors sur « publié ou révisé depuis N jours ».

**Incrémentalité des sources** (relevé du code) : CISA et le top 100 GitHub téléchargent tout à
chaque fois ; les releases relisent leur première page ; arXiv (7 jours), les alertes (1 jour) et
TLDR (1 jour) se recouvrent volontairement. Les répétitions sont la règle : la base doit
reconnaître un item déjà vu, quelle que soit la source.

### Référentiels : PAPER et CVE

**Décidé par Sabine** :

- **Un référentiel est une chose de référence vers laquelle des items pointent**, avec un
  identifiant officiel et stable. Il remplace la piste SUJET (nom écarté par Sabine). Sa
  traduction en tables est l'option D ci-dessous (sous-types à clé partagée), qui remplace la
  première idée d'une clé étrangère facultative par référentiel dans ITEM (option B).
- **Référentiel épais** : il porte le contenu de la chose, donné par la source qui fait foi.
  L'item garde ce qui est propre à la collecte (donnée brute, source, clé vers le référentiel).
- **PAPER, arXiv fait foi** : `arxiv_id`, titre, résumé, auteurs, dates de soumission et de
  révision. Raison : Zotero, source prévue en v0, ne contient que des papiers arXiv et doit se
  recouper avec la collecte arXiv (`docs/stockage.md:63-65`) ; l'item Zotero pointera vers le
  même PAPER.
- **CVE, CISA KEV fait foi** (forme revue en séance 2, voir « Référentiels et clés ») : `cve_id`, nom (`vulnerabilityName`), description
  (`shortDescription`), éditeur (`vendorProject`) et produit (`product`), ce qui règle #84, date
  d'ajout (`dateAdded`), usage connu par un rançongiciel (`knownRansomwareCampaignUse`, `Known` ou
  `Unknown`), `revised_at`, `withdrawn_at`. Raison : dans le périmètre de K-B, le catalogue KEV est
  la liste officielle des failles exploitées. `knownRansomwareCampaignUse` est le champ que CISA
  modifie en silence : sans lui, `revised_at` ne dirait pas pourquoi une faille a changé.
- **Auteurs : un attribut de PAPER** (tableau JSON, dans l'ordre d'arXiv), pas de table `author`
  ni de table de liaison. Raison : aucun parcours ne cherche par auteur ; la valeur est une
  mention d'affichage que la base ne découpe jamais. Purger le papier purge ses auteurs ; la
  purge d'une personne dans tous ses papiers n'est plus possible par un `DELETE` ciblé. Le
  registre des traitements est à mettre à jour.
- **NEWSLETTER_ARTICLE, TLDR fait foi pour son résumé** : édition, date d'édition, rang, titre,
  résumé, URL de l'article d'origine sans `utm_*` (non unique : deux éditions peuvent résumer le
  même article), clé étrangère facultative vers le PAPER cité. Clé naturelle : (édition, date,
  rang).
- **Option D : ITEM minimal, clé partagée.** ITEM ne porte que `item_id`, la donnée brute de sa
  version actuelle et `kind` (`paper`, `vulnerability`, `newsletter_article`). Chaque sous-type (clé revue en séance 2 : `id` technique)
  (PAPER, CVE, NEWSLETTER_ARTICLE) a pour clé primaire `item_id`, qui est aussi sa clé étrangère
  vers ITEM (règle 4 du MLD de `docs/stockage.md`). L'exclusivité (D1) est portée par une clé
  étrangère composée (`item_id`, `kind`). Écartés : B, ITEM table de trace avec des clés
  étrangères facultatives vers chaque référentiel (doublon de rôle) ; C, pas de table ITEM et une
  vue `UNION` (il faudrait une table de liaison par type pour les notes du point 4). Raison : ITEM
  reste le point d'entrée unique pour les notes, la recherche et P1.
- Le modèle n'a plus de table de liaison : toutes les associations sont en 1,n ou 0,1 (les listes de paquets du lot GitHub, en réflexion, sont aussi en 1,n).
- **Périmètre des failles : celles dont l'exploitation est avérée.** Pas de collecte de la liste
  CVE (cve.org, dépôt `CVEProject/cvelistV5`, 3,9 Go décompressé). Constaté sur un record
  (`CVE-2026-69086`) : un conteneur `cna` (description, produits touchés avec `packageURL`,
  CVSS) et un conteneur `CISA-ADP` avec une évaluation SSVC (`"Exploitation": "none"`). Piste
  future si le périmètre s'élargit, sans issue.

**Écarté** (piste du matin) : un item décrit une chose (la faille, l'article) que d'autres items peuvent
décrire aussi : ITEM ─1,1─ (DÉCRIRE) ─1,n─ SUJET (nom provisoire), identifié par le CVE ou par
l'URL normalisée. Il réglerait le croisement CISA × GitHub (P4), le lien résumé TLDR → article
(3c) et `UNIQUE (source, sujet)` (#105). Non décidé, comme 3a, 3b et 3c.

### GitHub (en réflexion, non décidé)

**Décidé par Sabine (2026-10-08)** : les paquets touchés par une alerte sont une liste JSON,
attribut de l'alerte, comme les auteurs d'un papier, et non la table `advisory_package` proposée
ci-dessous. Raison : en v0, la liste est seulement affichée ; P3 (filtrer par paquet) n'est pas
planifié. Si P3 est fait, une migration de la base la découpe en table. Constat dans le brut du
2026-10-07 (55 alertes pip) : 42 alertes touchent 1 paquet, 11 en touchent 2, 1 en touche 3, 1 en
touche 4. Écartées : des colonnes Paquet 1…N (groupe répétitif, 1re forme normale) ; la table dès
la v0 (pas de filtre à servir).

**Décidé par Sabine (2026-10-08)** : une entité DÉPÔT SUIVI, à laquelle chaque RELEASE est
rattachée (un dépôt suivi publie 1,n releases, une release vient d'un seul dépôt). Ses données :
nom du dépôt (`owner/name`), écosystème (`pip`, `npm`), paquets suivis. « Nom du dépôt » quitte
RELEASE. Raison : la liste des dépôts suivis existe déjà avec ses propres données, dans le code
(`src/k_b/sources/tracked_repositories.py`, 4 dépôts) ; l'objection de la proposition ci-dessous
(« les dépôts suivis ne sont pas tous dans le top 100 ») est tombée avec la sortie des classements
de la base. DÉPÔT SUIVI est une table de référence, comme SOURCE, pas un item. La liste fait foi
dans le code, qui remplit la table (décidé par Sabine le 2026-10-08) : la collecte la lit déjà là.
Les paquets suivis sont une liste choisie à la main ; ils filtrent la collecte des alertes
(`affects`, `src/k_b/sources/github_advisories.py:58`) : une alerte qui ne touche aucun paquet
suivi n'est pas collectée.

**Décidé par Sabine (2026-10-08)** : RELEASE garde la référence GitHub (`id`), l'étiquette
(`tag_name`), le nom (`name`), les notes (`body`, texte Markdown gardé tel que reçu) et la date de
publication (`published_at`), et se rattache à son DÉPÔT SUIVI. Constat dans le brut du 2026-10-07
(100 releases de `anthropics/claude-code`) : 99 notes en Markdown (titres, puces), 1 vide, la plus
longue fait 28 783 caractères.

Proposition de la session, selon l'option D :

- **ADVISORY** (GitHub fait foi, flux, premier vu) : `ghsa_id` unique, `cve_id` facultatif,
  `summary`, `severity`, `published_at`, `withdrawn_at`. `cve_id` n'est pas une clé étrangère
  vers CVE : CVE ne contient que les failles de KEV ; P4 devient « les alertes dont le `cve_id`
  est aussi dans CVE ». Les paquets touchés, que P3 filtre, vont dans
  `advisory_package (item_id, package_name)` : ici la base découpe la liste, un JSON enfreindrait
  la 1re forme normale.
- **RELEASE** (GitHub fait foi, flux, premier vu) : `release_id` unique, `repository_name`
  (colonne, pas clé étrangère : les dépôts suivis ne sont pas tous dans le top 100), `tag_name`,
  `name`, `body`, `published_at`. Règle D3.
- **Tops (P7, P8), décidé par Sabine** : en v0, le top du jour seulement, sans historique ni
  comparaison de positions. Les classements n'entrent pas en base : le dépôt n'est pas un item et
  REPOSITORY n'est pas un sous-type. La collecte passe par l'API GraphQL de GitHub (jeton
  obligatoire, `KB_GITHUB_TOKEN`), qui ne renvoie que les champs demandés : `nameWithOwner`,
  `description`, `stargazerCount`, `forkCount`. Deux requêtes, le top 100 par étoiles et le top
  100 par forks ; le rang est la position dans `data.search.nodes`. Le JSON reçu est à la fois le
  brut et le top du jour : un fichier par critère et par collecte, tous gardés ; la durée
  de conservation et la purge seront décidées plus tard. Ce qui s'affiche
  (top 10 ou plus) se décidera plus tard. Écartés : « dépôts en items + une mesure par
  instantané » (environ 36 500 lignes par an), la table d'état `ranking` (une base pour un simple
  affichage), l'API REST (82 champs par dépôt, sans choix des champs). À vérifier au codage : la
  chaîne de recherche (`stars:>1 sort:stars-desc`, non testée en GraphQL) ; une erreur GraphQL
  peut arriver avec un statut 200, dans la clé `errors`.

### Référentiels et clés (séance 2)

**Décidé par Sabine** :

- **Une source qui cite un CVE le crée.** Constat qui l'impose : les 55 alertes pip du
  2026-10-07 ont toutes un `cve_id`, aucun n'est dans le CSV CISA du même jour (1 734 CVE). Avec
  CVE en sous-type d'ITEM, une alerte ne pouvait pas créer sa CVE sans une fausse ligne KEV.
- **CVE devient un référentiel à clé propre** : `cve_id` unique, `item_id` clé étrangère
  facultative et unique vers l'item KEV, colonnes de KEV facultatives. « Exploitée » se lit
  `item_id IS NOT NULL`, sans attribut en double. Un `CHECK` impose : colonnes de KEV remplies si
  et seulement si `item_id` l'est. ADVISORY porte une clé étrangère facultative vers CVE ; P4 est
  la jointure ADVISORY → CVE dont `item_id` est rempli. Écartés : `cve_id` en simple colonne sans
  clé étrangère ; un attribut `is_exploited` (doublon de `item_id`) ; une table KEV_ENTRY séparée
  (une table de plus, pour éviter des colonnes vides que le `CHECK` tient).
- **Règle des référentiels** : un référentiel a pour clé unique son identifiant officiel
  (`cve_id`, `arxiv_id`) et pointe vers l'item de la source qui fait foi, quand elle l'a vu. CVE
  l'applique en v0 ; PAPER y passera avec Zotero (#15), qui décidera qui remplit ses colonnes
  quand arXiv n'a pas vu le papier.
- **Chaque table a un `id` technique** comme clé primaire. Les identifiants naturels (`arxiv_id`,
  `cve_id`, `ghsa_id`, `release_id`, édition + date + rang) deviennent des contraintes `UNIQUE`.
  Conséquence sur l'option D : un sous-type n'a plus `item_id` pour clé primaire, mais une clé
  étrangère `item_id` obligatoire et unique ; l'exclusivité (D1) reste portée par la clé
  étrangère composée (`item_id`, `kind`). Écarté : l'identifiant naturel en clé primaire, lisible
  sans jointure mais lié à un identifiant externe.

**Pistes notées en séance 2, à reprendre dans la liste des issues** :

- durée de conservation et purge des fichiers de classement GitHub (RGESN 1.6, même sans donnée
  personnelle) ;
- collecter le SBOM des dépôts suivis pour élargir P3 aux dépendances, hors v0 (l'appel direct
  `GET /repos/{owner}/{repo}/dependency-graph/sbom` ferme le 13/11/2026 selon la doc GitHub ; flux
  asynchrone à la place) ;
- activer Dependabot sur le dépôt K-B (sécurité de la chaîne d'approvisionnement, hors modèle) ;
- vérifier ce que la BOD 26-04 de la CISA change pour le catalogue KEV (la BOD 22-01 est
  marquée révoquée sur cisa.gov).

### GH Archive (séance 3)

**Décidé par Sabine (2026-10-08)** : les dépôts qui montent (P5, #16) entrent en base, dans une
table TENDANCE : nom du dépôt, fin de la fenêtre de 3 jours, étoiles gagnées, rang. Ce n'est pas un
item ni un sous-type ; elle remplace `repository` et `star_gain` de `docs/stockage.md`. Raison :
GH Archive est la seule source big data, et le bloc E1 demande d'agréger toutes les sources dans
le jeu de données stocké (critères exacts non relus ici). Écarté : un fichier par collecte hors
base, comme les tops GitHub (cohérent, mais la source big data n'entrerait pas en base).

**Décidé par Sabine (2026-10-08)**, forme de TENDANCE : une ligne par dépôt et par fenêtre, avec deux
mesures, étoiles gagnées (`WatchEvent`) et forks gagnés (`ForkEvent`), tirées d'une seule requête.
Le rang n'est pas stocké : il se calcule par un tri (type C). Sont gardés les 30 premiers par
étoiles et les 30 premiers par forks, réunis (60 dépôts au plus par fenêtre). La requête regroupe
par `repo.id`, gardé en base (référence du dépôt), avec le dernier nom vu. Écartés : deux tables TENDANCE ÉTOILES et TENDANCE FORKS
(mêmes données, signe d'une seule entité) ; une ligne par critère (un dépôt des deux tops sur
deux lignes) ; un top 100 (plus que l'affichage n'en demande, RGESN 1.6). Constat du 2026-10-08 :
sur la journée du 2026-10-06, aucun `repo.id` n'apparaît sous deux noms dans ces événements
(71,6 Mo lus) ; le regroupement par `repo.id` couvre un renommage en cours de fenêtre.

**Décidé par Sabine (2026-10-08)** : TENDANCE est rattachée à la chaîne de traçabilité. Le résultat
de la requête BigQuery est une donnée brute de la source `gh_archive` (déjà dans
`src/k_b/database/seed_sources.sql`), un fichier par collecte sous `raw/automation/gh_archive/` ;
DONNÉE BRUTE ─0,n─ (PRODUIRE) ─1,1─ TENDANCE, soit `trend.raw_data_id` au MLD. TENDANCE n'est pas un
item. Raison : toute donnée en base remonte à un fichier brut et à sa source, et TENDANCE se
reconstruit depuis le brut sans relancer BigQuery. Écarté : TENDANCE sans lien (seule table hors
de la chaîne).

**Décidé par Sabine (2026-10-08)** : TENDANCE garde aussi les étoiles totales et les forks
totaux de chaque dépôt, lus le jour de la collecte par l'API GraphQL de GitHub (une requête, un
alias par dépôt, `stargazerCount` et `forkCount`, `databaseId` comparé au `repo.id`). GH Archive
ne les donne pas : il enregistre des événements, sans les étoiles d'avant 2011 ni les retraits.
Écarté : l'API REST (une requête par dépôt, environ 82 champs sans choix). À vérifier au codage :
un dépôt renommé interrogé par son ancien nom ; le plafond d'alias et le coût d'une requête.

### PUBLICATION devient un référentiel (séance 3)

**Décidé par Sabine (2026-10-08)**, revient sur la règle des référentiels de la séance 2 (« PAPER y
passera avec Zotero ») : PUBLICATION est un référentiel dès la v0, comme VULNÉRABILITÉ. Sa clé
unique est la référence arXiv ; elle pointe vers l'item arXiv quand arXiv l'a vue (`item_id`
facultatif et unique) ; titre, résumé, auteurs et dates sont remplis si et seulement si cet item
existe (`CHECK`, comme pour CVE). Une source qui cite un papier le crée : un article de newsletter
peut pointer vers un papier que la collecte arXiv n'a pas vu. L'item arXiv n'a plus de sous-type ;
la spécialisation de ITEM ne compte plus que ARTICLE DE NEWSLETTER, RELEASE et ALERTE GITHUB.
Zotero (#15) décidera toujours qui remplit les colonnes quand arXiv n'a pas vu le papier.

### Liens (séance 3)

**Décidé par Sabine (2026-10-08)** : l'URL d'un dépôt (DÉPÔT SUIVI, TENDANCE) et celle d'un papier
arXiv se déduisent de leur nom ou de leur référence (`https://github.com/` + `owner/name`,
`https://arxiv.org/abs/` + référence) : données calculées, non stockées. L'URL d'une release est
gardée telle que GitHub la donne (`html_url`) : une étiquette peut contenir des caractères à
encoder, la reconstruire serait moins sûr. De même, l'URL d'une alerte GitHub est gardée telle que
donnée (`html_url`) ; celle d'une faille se déduit du numéro CVE
(`https://nvd.nist.gov/vuln/detail/` + numéro), comme le fait déjà le lecteur CISA.

**Décidé par Sabine (2026-10-08)** : le chemin de la donnée brute est stocké (`raw_file_path`) ;
le nom du fichier en est le dernier élément, calculé et absent du MLD. Écarté : stocker le nom et
reconstruire le chemin, qui demanderait de recoder les règles de rangement de chaque source (mode
`automation` ou `manual`, dossier de collecte de TLDR).

### Noms des associations (séance 3)

**Validés par Sabine (2026-10-08)** : FOURNIR (SOURCE, DONNÉE BRUTE), CONTENIR (DONNÉE BRUTE, ITEM),
PRODUIRE (DONNÉE BRUTE, TENDANCE), RECENSER (ITEM, VULNÉRABILITÉ), DÉCRIRE (ITEM, PUBLICATION),
CITER (ALERTE GITHUB, VULNÉRABILITÉ), RÉSUMER (ARTICLE DE NEWSLETTER, PUBLICATION), PUBLIER (DÉPÔT
SUIVI, RELEASE). MCD et MLD du jour : `docs/merise/mcd-k-b.drawio`, `docs/merise/mld-k-b.drawio`.

### Longueurs maximales (séance 3)

**Décidé par Sabine (2026-10-08)** : une longueur maximale du dictionnaire de données est tenue
deux fois, par Pydantic à la lecture du brut et par un `CHECK (length(col) <= n)` dans le schéma.
Raison : défense en profondeur (`.claude/rules/code.md`), comme pour les dates (Pydantic, puis
`CHECK` de `schema.sql`). Constat : SQLite ignore la longueur d'un `VARCHAR(n)` (affinité TEXT) ;
les colonnes restent en `TEXT`. Coût : la même limite écrite en Python et en SQL ; un test vérifie
qu'elles concordent. Écartés : un seul des deux contrôles ; la convention VARCHAR / TEXT de MySQL,
sans effet sur SQLite. Une valeur plus longue que la limite fait refuser l'item, et le journal dit
quel champ dépasse et de combien (décidé par Sabine le 2026-10-08) ; écarté : tronquer, qui
modifie la donnée sans le dire.

### Collecte large et sources choisies (séance 4)

**Décidé par Sabine (2026-10-09)** : les deux dossiers du brut disent la finalité, pas le mode
d'arrivée. `raw/automation/` devient `raw/automated_watch/` (la collecte large de la veille) ;
`raw/manual/` devient `raw/selected_library/` (les sources que Sabine choisit sciemment). Ils
répondent aux deux portes du README (veille, base de connaissance) et aux deux finalités du
registre (`docs/registre-traitements.md`, fiches 1 et 2). Écartés : `choosen_files` (« files »
dit le format, et Zotero n'est pas un dépôt de fichiers) ; `curated_library` (en ingénierie des
données, la zone *curated* d'un lac de données est la donnée traitée, contraire de `raw/`) ;
`hand_picked` (ne dit pas la finalité) ; `personal_library` (se confond avec « données
personnelles »).

Ce que Sabine y range : les clips du Web Clipper d'Obsidian (Markdown, frontmatter écrit par le
clipper), ses notes et PDF déposés, plus tard des livres PDF ou EPUB (après la v0). Un article
de la veille que Sabine creuse et met dans Zotero relève ensuite de la bibliothèque choisie.

- Le Web Clipper écrit chaque clip dans le dossier « Note location » de son modèle, chemin
  relatif au coffre ([aide Obsidian](https://obsidian.md/help/web-clipper/capture)) ; le coffre
  est le dossier de données (ADR). Non testé.
- **Décidé par Sabine (2026-10-09)** : en v0, K-B **indexe** la bibliothèque choisie. Chaque
  document déposé devient une entrée en base (titre, URL, date de dépôt, source : clip, Zotero,
  note), cherchable par `kb search` ; un item de la veille peut être relié à sa version creusée
  dans Zotero. Revient sur l'ADR de la PR de #7 (« les documents de `raw/manual/` n'entrent pas
  dans la base en v0 »). Écartés : stocker seulement (la base ne verrait pas qu'un item a été
  creusé) ; compiler le wiki LLM (v1).
- **Décidé par Sabine (2026-10-09)** : `kb search` prend un filtre `--in watch|library|wiki`, le
  mode d'acquisition ; l'aide de la commande le dit (« --in watch|library|wiki : restreint au mode
  d'acquisition »). Le détail (clip, Zotero, note, arXiv…) passe par `--source`. Écartés :
  `--in clip|zotero|note` (doublon de `--source` si chaque dépôt est une ligne de SOURCE) ; un
  filtre à deux sens ; `--origin` (nom abandonné, voir plus bas) ; `--mode` (« mode de quoi ? ») ;
  `--scope` (abstrait) ; `--acquisition` (long) ; `--from` (se confond avec `--source` et une date).
- **Décidé par Sabine (2026-10-09) : une table de référence ACQUISITION_MODE** (mode
  d'acquisition), dès la v0, trois lignes. Association **REGROUPER** : un mode d'acquisition
  regroupe 0 à n sources ; une source est regroupée dans un seul mode (1,1). Le sujet est le mode
  d'acquisition, placé à gauche de SOURCE au MCD (`docs/merise/mcd-k-b.drawio`). Écartés pour l'entité :
  ORIGIN et PROVENANCE (synonymes de « source » dans la langue courante), CANAL (se confond avec
  le flux d'une source), MODE D'ENTRÉE (`intake`, peu connu). Écartés pour l'association : ÊTRE
  OBTENU PAR et ÊTRE COLLECTÉE (passifs, seules exceptions aux huit associations validées ; un
  contenu `wiki` n'est pas collecté), RELEVER (retenu d'abord, remplacé par REGROUPER au choix de
  Sabine), APPARTENIR, DÉTERMINER.

  | `acquisition_mode_code` (base et `--in`) | `label` | Dossier du brut | Exemples de sources |
  |---|---|---|---|
  | `watch` | system automation | `raw/automated_watch/` | arXiv, CISA, GitHub, TLDR, GH Archive |
  | `library` | user selection | `raw/selected_library/` | clips, Zotero, notes déposées |
  | `wiki` | llm generation | aucun (une note générée n'est pas un brut) | notes du wiki LLM (v1) |

  ACQUISITION_MODE porte aussi la **durée de conservation**, que la purge lit au lieu de la coder.
  Les **2 ans restent pour le moment** et sont **à revoir**, peut-être au cas par cas (registre :
  2 ans pour la veille, fiche 1 ; bibliothèque gérée par Sabine dans ses outils, fiche 2 ; rien
  pour le wiki). Pourquoi le mode d'acquisition : la purge doit le connaître, sinon un document de la bibliothèque purgé à 2 ans serait recréé à la collecte
  suivante depuis `selected_library/` ; et le contenu généré par un LLM se distingue du contenu
  collecté (K-B déterministe, « d'où vient cette affirmation »). Codes courts et libellés, comme
  SOURCE (`source_code`, `label`). Écartés : une contrainte `CHECK` sur SOURCE (durée et dossier
  dans le code ; ajouter une valeur oblige SQLite à recréer la table) ; la déduire du chemin du
  brut (une règle de rétention dépendrait d'un nom de dossier) ; une colonne sur ITEM (répétée sur
  chaque item, alors qu'elle dépend de la source) ; des codes longs (`system_automation`…) avec
  des alias dans la CLI (une correspondance à tenir). Ouvert : comment une note générée entre en
  base, quand le wiki sera conçu.

  Au MLD, selon la règle de l'`id` technique (séance 2) : `acquisition_mode (id PK,
  acquisition_mode_code UNIQUE, label, raw_folder, retention…)` et `source (id PK, source_code
  UNIQUE, label, source_type, acquisition_mode_id FK → acquisition_mode.id NOT NULL)`. Les codes
  courts servent à la CLI ; les jointures passent par l'`id`. Aujourd'hui `source_code` est la clé
  primaire (`src/k_b/database/schema.sql:9`). La forme de `retention` se décidera avec la revue
  des durées.
- **Point 4, notes (décidé par Sabine, 2026-10-09)** : en v0, la base ne garde que les items ; la
  CLI (`kb search`, `kb top`) affiche les résultats sans les inscrire dans une note. Les fiches de
  veille (gabarit, sans LLM) et les notes du wiki LLM ne sont **pas abandonnées** : elles sont
  **reportées**, avec ou sans LLM, et se décideront une fois bouclés la chaîne de collecte et de
  fusion, l'indexation en base et `kb search`. La ligne `wiki` de ACQUISITION_MODE leur laisse la porte
  ouverte. Écartée pour la v0 : NOTE et une table de liaison « une note cite des items »
  (plusieurs à plusieurs), qui supposaient des fiches en v0.
- **Zotero (décidé par Sabine, 2026-10-09)**, revient sur l'ADR de la PR de #6 (« le brut est la
  copie entière de `zotero.sqlite`, pas le résultat d'une requête », provisoire, à revoir dans
  #15). Coût assumé : un champ non extrait aujourd'hui (étiquettes, collections…) n'est pas dans
  les anciens bruts ; il faudra relancer la requête sur la base Zotero du moment. Zotero
  reste une source « base de données », interrogée en SQL. Constat : l'accès direct à
  `zotero.sqlite` doit se faire en lecture seule, et Zotero casse le verrouillage normal de
  SQLite ([doc Zotero](https://www.zotero.org/support/dev/client_coding/direct_sqlite_database_access)) :
  Zotero ouvert, une lecture en place échoue (« database is locked »). Recommandé : (1) copier
  `zotero.sqlite` dans un dossier temporaire, Zotero ouvert ou non ; (2) `PRAGMA integrity_check`
  sur la copie, et en cas d'échec un état nommé (ex. `zotero_copy_inconsistent`), rattrapé à la
  collecte suivante ; (3) requête SQL en lecture seule sur la copie ; (4) écrire comme brut le
  résultat de la requête (titres, URL, dates, surlignages, chemin des PDF) en JSON sous
  `raw/selected_library/zotero/`, puis supprimer la copie. Les PDF restent dans le stockage de
  Zotero ; K-B garde leur chemin. Écartés : un script qui ferme Zotero puis le rouvre
  (interrompt l'usage, risque d'écriture interrompue, K-B piloterait une application) ; lire
  seulement Zotero fermé (jamais collecté si Zotero reste ouvert) ; la base entière comme brut
  (contraire à la minimisation, CNIL et RGESN 1.6) ; l'API locale de Zotero 7 (plus de source
  « base de données ») ; `zotero.sqlite.bak` (fréquence et fraîcheur non vérifiées). Non
  vérifié : la fiabilité d'une copie à chaud, d'où le contrôle d'intégrité.
- **Surlignages (décidé par Sabine, 2026-10-09)** : en v0, ils sont gardés en base et **affichés
  avec leur papier** dans les résultats de `kb search`, seulement si le papier en a. Ils ne sont
  pas cherchables par leurs mots. Écartés : les rendre cherchables (un index de plus sur un texte
  déjà lu) ; ne pas les collecter en v0 (perd ce que la requête Zotero ramène de toute façon).
- **Index plein texte (décidé par Sabine, 2026-10-09)** : FTS5, le module de recherche plein
  texte intégré à SQLite (aucune dépendance ; essayé avec le SQLite 3.50.4 de K-B : mot, phrase
  exacte, préfixe, racine des mots anglais avec `porter`, accents neutralisés). **Tri** : avec des
  mots à chercher, par pertinence BM25 (fonction `bm25()` de FTS5, plus bas = plus pertinent) ;
  sans mots, par date. **Couverture** : titre et résumé des items ; pour les clips et les notes
  déposées, titre et **texte complet**, stocké en base. Écartés : tri par date seulement (un papier
  qui cite le terme une fois au rang d'un papier consacré au sujet) ; tri par date avec
  `--sort relevance` (une option de plus) ; titre seul pour la bibliothèque (un clip ne se
  retrouve que par son titre). Limites : `porter` ne ramène à leur racine que les mots anglais ;
  FTS5 est propre à SQLite (PostgreSQL : `tsvector`). Reste au modèle : la colonne qui porte le
  texte complet d'un document de la bibliothèque.
- **Clips (décidé par Sabine, 2026-10-09)** : les clips vivent dans le dossier `Clippings/` du
  coffre Obsidian de la knowledge base, où Sabine les annote librement. K-B **copie** chaque clip
  nouveau ou modifié, horodaté, dans `raw/selected_library/clipping/` ; le chemin de `Clippings/`
  se règle par une variable d'environnement, comme `KB_DATA_DIR`. Le coffre et le dossier de
  données de K-B sont **séparés** : revient sur l'ADR « Données hors du dépôt de code », qui
  faisait du dossier de données le coffre Obsidian. Écartés : lire `Clippings/` en place (le brut
  ne serait plus figé : une annotation changerait ce que K-B reconstruit) ; faire écrire le Web
  Clipper dans `raw/selected_library/clipping/` (possible seulement si le dossier de données est
  le coffre, puisque la « Note location » est relative au coffre ; le clip serait à la fois note
  vivante et brut, et le coffre contiendrait les bruts de la veille et la base).
  Relevé sur les 26 clips du coffre de Sabine (2026-10-09, par commande) : `title`, `source`,
  `author`, `published`, `created`, `description`, `tags` présents dans les 26 ; `published` vide
  dans 12 ; `author` est une liste de liens Obsidian (`- "[[Nom]]"`, à nettoyer, plusieurs
  auteurs possibles) ; corps de 517 octets à 42,7 ko (400 ko pour les 26), avec le bruit de la
  page (images, mentions du site). Correspondance : `title` → `item.title`, `source` →
  `item.url`, `published` → `item.published_at` (vide si absente), `created` → `item.saved_at`,
  `author` → `author.name`, **`description` → `item.summary`** (absente de `docs/stockage.md:58`),
  `tags` : rien en v0, corps → texte complet.
- **Dossier de données (décidé par Sabine, 2026-10-09)** : `KB_DATA_DIR=~/.knowledge_base` (brut,
  base, journal d'import), réglé dans `~/.zshrc` ; c'est un réglage d'installation, pas une règle du
  code (`src/k_b/cli.py:18` lit la variable). Deux règles : hors de tout dossier synchronisé par
  iCloud (base SQLite, données hors machine) ; dans la sauvegarde Time Machine (c'est le brut
  qu'on sauvegarde, W7 ; sauvegarde des dossiers cachés non vérifiée). Écartés : `~/.local/share/k-b`
  (convention XDG, moins connue sur Mac), `~/Library/Application Support/K-B` (pensé pour les
  applications graphiques), `~/K-B-data` (exemple de l'ADR, un dossier visible de plus).

### Question ouverte : miroir et multi-machines (séance 4)

**Non décidé ; à réfléchir par Sabine.** Besoins : collecter quand la machine qui collecte est éteinte ;
travailler la veille sur une autre machine (un portable, peut-être une tablette). Écarté par
Sabine : allumer la machine qui collecte automatiquement (`pmset`).

- **Ce qu'une collecte manquée fait perdre** : presque rien. arXiv, TLDR, alertes et releases
  GitHub, CISA, GH Archive repartent de la dernière collecte (#65) ; seules les photos de
  classement (top étoiles et forks) d'un jour manqué sont perdues. Zotero, clips et notes sont sur
  le Mac : un miroir en ligne ne les lirait pas.
- **Synchroniser le brut, jamais la base** : le brut est écrit une fois, jamais réécrit, horodaté,
  donc sans conflit ; chaque machine reconstruit sa base. Un fichier SQLite partagé ou dans un
  dossier cloud se corrompt facilement.
- **Tablette** : K-B (CLI Python) n'y tourne pas ; on y lirait (Obsidian), on n'y interrogerait pas
  sans une autre interface (feuille de route : TUI, Tauri, sans issue).
- **Contrainte** : le registre et sa purge sont tenus par choix, bien que K-B relève
  probablement de l'exemption des activités strictement personnelles (ADR, PR de #8). Un dépôt
  git garde dans son historique ce que la purge supprime. Une sauvegarde de la base ou un export
  CSV n'y change rien (mêmes données personnelles ; binaire recopié à chaque version) et
  empêcherait de retraiter le brut.

| Piste | Pour | Contre |
|---|---|---|
| Dépôt git privé du brut, plus une GitHub Action programmée | collecte machine éteinte ; autre machine à jour par `pull` | purge sans effet sur l'historique ; données hors machine (revient sur la décision « local » du 08/10) ; jetons dans les secrets GitHub ; deux collecteurs à départager ; 2 000 min/mois d'Actions en privé |
| Synchronisation de fichiers du brut (iCloud Drive, Syncthing) | la suppression se propage, la purge tient | pas de collecte Mac éteint ; iCloud garde les fichiers hors machine (Syncthing non) |
| Rien : tout sur la machine qui collecte, rattrapage au démarrage | simple ; décision « local » intacte | photos de classement des jours éteints perdues ; pas d'autre machine |

### À reprendre dans la liste des issues (séance 3)

- **Revoir les paquets principaux des dépôts suivis** (demande de Sabine, 2026-10-08). La collecte
  des alertes ne demande que les alertes qui touchent un paquet suivi (`affects`,
  `src/k_b/sources/github_advisories.py:58`) : une alerte qui ne touche qu'un paquet absent de la
  liste n'est pas collectée. La liste actuelle (7 paquets pip, 1 npm) et ses exclusions
  (`langchain-community`, `langchain-experimental`, `langchain-classic`) sont dans `docs/sources.md`.
- **Renommer `raw/automation/` en `raw/automated_watch/`** (séance 4) : code
  (`src/k_b/collect.py:68`, `src/k_b/raw_items.py:111`), tests, `docs/specs-collecte.md`, règle 4
  du registre. Les bruts déjà écrits sont à déplacer.
- **Table ACQUISITION_MODE** (séance 4) : schéma, colonne `acquisition_mode_id` dans SOURCE, `seed_sources.sql`, une
  ligne de SOURCE pour les notes déposées ; purge qui lit la durée dans ACQUISITION_MODE ; registre des
  traitements, règle 2 (aujourd'hui « les items collectés il y a plus de 2 ans », sans
  distinguer la provenance) et durées à revoir.
- **W7, migrations de schéma** (revue d'architecture ; décidé par Sabine, 2026-10-09) : **la base
  reste jetable**. Un changement de schéma = recréer la base puis tout réimporter depuis le brut
  (« la base doit rester reconstructible depuis le brut », registre, fiche 1) ; pas de migration ;
  c'est le brut qu'on sauvegarde. Écartés pour la v0 : les migrations numérotées avec
  `PRAGMA user_version` proposées par la revue ; Alembic + SQLAlchemy (deux dépendances, schéma à
  réécrire en Python ; son mode « batch » recrée les tables que SQLite ne sait pas modifier). La
  base devra être sauvegardée, avec des migrations (numérotées ou Alembic, à choisir alors), le
  jour où elle gardera des données sans brut : notes du wiki LLM si elles ne vivent pas en
  fichiers dans `wiki/`, ou brut purgé avant la base. Mesure (collecte réelle du 2026-10-07,
  2 500 items) : brut 5,6 Mo (1,03 Mo compressé), base 3,1 Mo (0,97 Mo compressée, sans index
  plein texte) ; dans la durée le brut grossit plus vite (chaque collecte s'ajoute, CISA et le top
  étoiles réécrivent tout), la base ne grossit que des nouveautés (déduit, non mesuré).
- **Installation et launchd** (issue à créer, décidée le 2026-10-08) : la doc d'installation du
  README donne `KB_DATA_DIR=~/.knowledge_base` et le chemin du dossier `Clippings/` du coffre
  (séance 4).
- **Fiches de veille reportées** (séance 4) : l'epic des fiches (#22) et le test de bout en bout
  qui vérifie la fiche produite (#26) passent après la collecte, l'indexation et `kb search` ;
  l'ADR « Deux wikis » (fiches figées dans `wiki/veille/`) et la chaîne de `docs/stockage.md:4`
  et `:10` (« base → API REST → fiches, agents ») sont à mettre à jour.
- **Zotero (#15)** (séance 4) : reprendre la décision ci-dessus dans l'issue ; ADR de la PR de #6 à réviser ; mettre à
  jour `docs/specs-collecte.md:185` (aujourd'hui, la copie entière comme brut sous
  `raw/automation/zotero/`) et le registre (fiche 2 et règle 5, « supprimer les copies Zotero du
  brut sauf la plus récente », sans objet si la copie n'est plus gardée).

<!-- Points 4 et 5 : à suivre. -->

## Annexe : les sources, champ par champ

**Exemplaires** : tirés de la première vraie collecte, lancée source par source le 2026-10-07
(chemins relatifs à `<KB_DATA_DIR>/`). Une source par nature d'item : les autres releases, les
alertes npm et les éditions TLDR `infosec` et `dev` ont la même forme. Les fixtures de
`tests/fixtures/` en sont des extraits, parfois allégés (logins remplacés par `example-user`, textes et
listes coupés). Les logins vus dans le brut ne sont pas recopiés ici.

Légende : **gardé** = écrit en base ; **lu** = lu et validé par le lecteur, puis abandonné ;
**non lu** = laissé dans le brut.

### CISA KEV (`cisa_kev`, fichier CSV)

Exemplaire : vraie collecte du 2026-10-07, `raw/automation/cisa_kev/2026-10-07T083507Z.csv`,
ligne 2 (le catalogue entier : 1 734 vulnérabilités, `dateAdded` du 2021-11-03 au 2026-10-04).

| Champ | Exemple | Sort | `table.colonne` |
|---|---|---|---|
| `cveID` | `CVE-2026-88779` | gardé | `item.source_item_id`, `vulnerability.cve` ; sert aussi à `item.url` |
| — | `https://nvd.nist.gov/vuln/detail/CVE-2026-88779` | construit | `item.url` |
| `vulnerabilityName` | `Citrix NetScaler Improper Restriction of Operations within the Bounds of a Memory Buffer Vulnerability` | gardé | `item.title` |
| `dateAdded` | `2026-10-04` | gardé (minuit UTC) | `item.published_at` |
| `shortDescription` | `Citrix NetScaler ADC (formerly Citrix ADC) and Citrix NetScaler Gateway … contain an improper restriction…` | gardé | `item.summary` |
| `vendorProject` | `Citrix` | lu | — (#84) |
| `product` | `NetScaler` | lu | — (#84) |
| `requiredAction`, `dueDate` | `Apply mitigations in accordance with vendor instructions…`, `2026-10-07` | non lu | — |
| `knownRansomwareCampaignUse` | `Unknown` | non lu | — |
| `forensicTriage`, `notes`, `cwes` | `Yes`, liens Citrix, `CWE-119` | non lu | — |

### GitHub, alertes de sécurité (`github`, API REST `GET /advisories`)

Exemplaire : vraie collecte du 2026-10-07, `raw/automation/github_advisories_pip/2026-10-07T083812Z.json`,
entrée 0 (première collecte : 55 alertes, toutes avec un CVE, revues du 2023-04-05 au 2026-06-25).
C'est la même alerte que l'entrée 0 de la fixture ; le vrai brut a en plus le champ `comments`.
Les paquets cités par ces 55 alertes dépassent la liste suivie : `langchain-community`, `numexpr`,
`llama-index-llms-rungpt`… y figurent aussi.

| Champ | Exemple | Sort | `table.colonne` |
|---|---|---|---|
| `ghsa_id` | `GHSA-fjqc-hq36-qh5p` | gardé | `item.source_item_id` |
| `cve_id` | `CVE-2026-48775` (peut être `null`) | gardé | `vulnerability.cve` |
| `summary` | `LangGraph Checkpoint: Unsafe JSON deserialization in checkpoint loading` | gardé | `item.title` |
| `html_url` | `https://github.com/advisories/GHSA-fjqc-hq36-qh5p` | gardé | `item.url` |
| `published_at` | `2026-06-25T18:25:42Z` | gardé | `item.published_at` |
| `github_reviewed_at` | `2026-06-25T18:25:42Z` | lu (pilote la collecte) | — |
| `severity` | `medium` | lu | — |
| `vulnerabilities[].package.name` | `langgraph-checkpoint` | lu | — |
| `description` | `## Summary\n\nLangGraph's JsonPlusSerializer…` | non lu | — |
| `vulnerable_version_range`, `first_patched_version` | `< 4.1.1`, `4.1.1` | non lu | — |
| `cvss_severities`, `cwes`, `epss` | `6.8`, `CWE-502`, `0.00685` | non lu | — |
| `source_code_location` | `https://github.com/langchain-ai/langgraph` | non lu | — |
| `credits` | login de la personne créditée | non lu (minimisation RGPD) | — |
| `nvd_published_at`, `references`, `comments` | `2026-06-16T19:16:58Z`, liens NVD et GitHub, `1` | non lu | — |

### GitHub, releases (`github`, API REST `GET /repos/{owner}/{repo}/releases`)

Exemplaire : vraie collecte du 2026-10-07,
`raw/automation/github_releases_anthropics_claude_code/2026-10-07T084008Z.json`, entrée 0
(première collecte : 100 releases, la page entière, publiées du 2026-06-11 au 2026-10-06 ; aucune
préversion ; `name` égal à `tag_name` pour les 100 ; 2,2 Mo, surtout la liste `assets`). La
fixture avait `assets` vide et pas de champ `reactions`.

| Champ | Exemple | Sort | `table.colonne` |
|---|---|---|---|
| `id` | `404958910` | gardé | `item.source_item_id` |
| `html_url` | `https://github.com/anthropics/claude-code/releases/tag/v2.1.292` | gardé | `item.url` ; le dépôt en est extrait |
| dépôt + (`name` ou `tag_name`) | `anthropics/claude-code v2.1.292` | gardé, concaténé | `item.title` |
| `published_at` | `2026-10-06T18:59:30Z` | gardé | `item.published_at` |
| `body` | `## What's changed\n\n- Added --marketplace <source> to claude plugin install…` | gardé | `item.summary` |
| `prerelease` | `false` | lu | — |
| `tag_name` seul | `v2.1.292` | lu | — (seulement dans le titre) |
| `author` | login | non lu (minimisation RGPD) | — |
| `created_at`, `assets`, `draft`, `reactions` | `2026-10-06T18:59:09Z`, binaires `claude-darwin-arm64…`, `false`, `24` | non lu | — |

### GitHub, 100 dépôts les plus étoilés (`github`, API REST `GET /search/repositories`)

Exemplaire : vraie collecte du 2026-10-07, `raw/automation/github_most_starred/2026-10-07T084154Z.json`,
`items[0]` (100 dépôts, `incomplete_results` à `false` ; 82 champs par dépôt ; 560 Ko). Même
dépôt en tête que dans la fixture.

| Champ | Exemple | Sort | `table.colonne` |
|---|---|---|---|
| `full_name` | `codecrafters-io/build-your-own-x` | gardé | `item.source_item_id`, `item.title`, `repository.repository_name` |
| `html_url` | `https://github.com/codecrafters-io/build-your-own-x` | gardé | `item.url` |
| `description` | `Master programming by recreating your favorite technologies from scratch.` | gardé | `item.summary` |
| rang dans la réponse | `1` | lu | — |
| `stargazers_count`, `topics`, `created_at` | `551937`, `awesome-list`, `tutorials`…, `2018-05-09T12:03:18Z` | lu | — |
| `language`, `forks_count`, `pushed_at` | `Markdown`, `51783`, `2026-07-14T19:25:58Z` | non lu | — |
| `owner` | login et URL du propriétaire | non lu | — |

### arXiv (`arxiv`, API Atom)

Exemplaire : vraie collecte du 2026-10-07, `raw/automation/arxiv/2026-10-07T084333Z.xml`, première
`<entry>` (première collecte, depuis `FIRST_COLLECTION_START` = 2026-05-01 : `totalResults` 511,
511 entrées, publiées du 2026-05-01 au 2026-10-06 ; 1,3 Mo).

| Champ | Exemple | Sort | `table.colonne` |
|---|---|---|---|
| `id` sans version | `2605.00955` (de `http://arxiv.org/abs/2605.00955v1`) | gardé | `item.source_item_id` ; sert à `item.url` |
| — | `https://arxiv.org/abs/2605.00955` | construit | `item.url` |
| version | `1` | lu | — |
| `title` | `E-MIA: Exam-Style Black-Box Membership Inference Attacks against RAG Systems` | gardé | `item.title` |
| `summary` | `Retrieval-Augmented Generation (RAG) equips large language models (LLMs) with external evidence…` | gardé | `item.summary` |
| `author/name` | 7 auteurs, dont `Zelin Guan`, `Shengda Zhuo` | gardé, dans l'ordre | `author.name`, `item_author.position` |
| `published` | `2026-05-01T12:30:00Z` | gardé | `item.published_at` |
| `updated` | `2026-05-01T12:30:00Z` | gardé | `item.revised_at` |
| `link` PDF, `category`, `primary_category` | `https://arxiv.org/pdf/2605.00955v1`, `cs.CR`, `cs.AI` | non lu | — |

### tldr.tech (`tldr`, pages HTML, une par édition et par jour)

Pas encore de lecteur (#57) : le tableau dit ce que la page contient, et ce que `docs/stockage.md`
prévoit d'en garder. Exemplaire : vraie collecte du 2026-10-07,
`raw/automation/tldr_ai/2026-10-07T084509Z/2026-10-06.html`, deuxième `<article>` (5 pages, du
2026-09-30 au 2026-10-06, sans le 03, le 04 ni le 07 ; 74 à 84 Ko chacune). Sur les 5 pages :
80 articles hors sponsor, et 3 sponsors sur la page du 06.

| Élément de l'article | Exemple | Sort prévu | `table.colonne` prévue |
|---|---|---|---|
| lien (`<a href>`) | `https://openai.com/index/eu-text-provenance/?utm_source=tldrai` | gardé, sans `utm_*` | `item.source_item_id`, `item.url` |
| titre (`<h3>`) | `OpenAI to Add Text Watermarks` | gardé | `item.title` |
| mention en fin de titre | `(7 minute read)` ; ailleurs `(GitHub Repo)`, `(Hugging Face Repo)`, `(Website)`, `(Sponsor)` | non prévu ; `(Sponsor)` écarté | — |
| résumé (`<div>`) | `OpenAI said it would add invisible text watermarks to eligible ChatGPT and Codex outputs in the EU…` | gardé | `item.summary` |
| date de l'édition (nom de la page) | `2026-10-06` | gardé (minuit UTC) | `item.published_at` |
| rubrique (titre de section) | `Headlines & Launches`, `Deep Dives & Analysis`, `Engineering & Research` | non prévu | — |

Mentions sur les 80 articles : `N minute read` 75, `GitHub Repo` 2, `Hugging Face Repo` 1,
`Website` 1, une offre d'emploi 1. Domaines des liens les plus fréquents : `x.com` 7, `openai.com` 5,
`techcrunch.com` 5, `www.anthropic.com` 3, `links.tldrnewsletter.com` 3 ; `github.com` 2,
`arxiv.org` 2. La page ne porte ni auteur ni expéditeur (aucune occurrence de `author`).

### À venir : clips Obsidian (#14), Zotero (#15), GH Archive

D'après `docs/stockage.md`, `docs/specs-collecte.md` et `docs/registre-traitements.md` :

| Source | Ce qu'elle donnera | `table.colonne` prévue |
|---|---|---|
| Clips Obsidian | un fichier `.md` par page gardée : en-tête YAML (`source`, `published`, `created`, `author`) et le texte gardé | `item.url` (`source`), `item.published_at` (`published`, vide si absent), `item.saved_at` (`created`), `author.name` (`author`) ; le texte gardé n'a pas de colonne |
| Zotero | papiers lus (titre, auteurs, date, étiquettes, chemin du PDF) et leurs surlignages | `item.*`, `item.saved_at` (`dateAdded`), `author.name`, `highlight.*` ; étiquettes hors base |
| GH Archive | les dépôts qui gagnent le plus d'étoiles sur 3 jours | `repository`, `star_gain.stars_gained`, `star_gain.window_end` |
