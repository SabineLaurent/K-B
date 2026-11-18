# K-B

**Une bibliothèque de veille tech qui se range toute seule.**

## Objectif

K-B a deux portes d'entrée :

- **La veille** : un pipeline collecte chaque jour l'actualité tech venue de plusieurs sources (une
  collecte manquée est rattrapée à la suivante), la range en items datés dans une base, puis
  répond à « quoi de neuf cette semaine ? ».
- **La base de connaissance** : je dépose à la main les documents qui comptent. Une IA les
  compile en un wiki Markdown durable, à la façon du LLM wiki d'Andrej Karpathy : les sources
  restent immuables, et le wiki relie les pages, signale les contradictions et date ce qu'il
  affirme.

Au POC du 25/10, les données restent sur ma machine, et l'inférence passe par une API ; au 08/11,
K-B est mis en ligne sur Azure (voir « Conduite du projet »). Je lis dans Obsidian et
j'interroge depuis le terminal. La revue des implémentations existantes est dans
[docs/veille/2026-09-23-veille-existant.md](docs/veille/2026-09-23-veille-existant.md). Le constat principal :
aucune ne fait de veille datée.

## Utilisateurs

1. Moi, d'abord : un seul utilisateur.
2. Des agents (Claude Code…), qui interrogent la base par l'API REST.
3. Plus tard, les mêmes agents via un serveur MCP.

## Périmètre de la v0

La v0 se fait en deux étapes.

### Étape 1 — l'import des données : le pipeline de veille

L'étape 1 couvre la porte « veille » :

- **Collecte**, avec un point de lancement unique, une panne isolée par source et une sauvegarde
  brute :
  - API GitHub : releases des dépôts suivis, alertes de sécurité, dépôts les plus étoilés et les
    plus forkés ;
  - API arXiv : papiers sur la sécurité de l'IA, métadonnées et résumé ;
  - catalogue CISA des vulnérabilités activement exploitées (fichier CSV) ;
  - Markdown produit par Obsidian Web Clipper, dans un coffre Obsidian dédié ;
  - newsletters tldr.tech, lues par scraping ;
  - mes papiers lus dans Zotero et leurs surlignages (base SQLite) ;
  - les dépôts GitHub qui montent sur 3 jours, calculés depuis GH Archive sur BigQuery.

  Les sources suivies sont dans [docs/sources.md](docs/sources.md), leur accès et leurs limites
  dans [docs/specs-collecte.md](docs/specs-collecte.md).
- **Dédoublonnage par la base** : dates normalisées, doublons écartés selon la nature de chaque
  source, écarts et rejets tracés, règles écrites.
- **Stockage** dans une base modélisée avec Merise, avec une installation qu'un tiers peut rejouer.
- **API REST authentifiée**, documentée en OpenAPI, qui sert les items et répond à « quoi de neuf
  cette semaine ».
- **Données personnelles** : un registre des traitements et une procédure de purge.

### Étape 2 — les comptes rendus de veille

L'étape 2 fait lire la veille par un modèle, à travers l'API de données, et range ce qui en sort
dans mon coffre Obsidian, sous `veille/` :

- **Comptes rendus de veille par sujet** (`kb digest`) : le modèle range les items de la
  fenêtre (3 jours par défaut) dans les sujets d'une liste fermée que je tiens, puis écrit, pour
  chaque sujet, des affirmations qui citent leurs items ; une fiche par sujet,
  `veille/<sujet>/AAAA-MM-JJ.md`.
- **Compte rendu des tendances** (`kb trend-report`) : parmi les dépôts qui montent sur GH
  Archive, le code calcule les rangs et les critères (durables, nouveaux, en accélération) et lit
  la fiche GitHub de chaque candidat ; le modèle en choisit au plus 5, puis écrit quatre textes
  courts sur chacun, depuis sa fiche, son README et les définitions des sujets de veille qu'il
  porte ; `veille/tendances/<date>.md`.
- **Tops** (`kb write-tops`, sans modèle) : une fiche datée pour chacun des deux classements de
  100 dépôts, les plus étoilés et les plus forkés, sous `veille/tops/`.
- **Contrôles** : le modèle renvoie du JSON ; le code le revalide (schéma fermé, sujets de la
  liste, items cités parmi ceux envoyés, ni lien ni balise) et retire une affirmation dont les
  faits ne se retrouvent pas dans l'item cité. Une sortie hors schéma n'est jamais écrite.
- **API IA authentifiée**, distincte de l'API de données et documentée en OpenAPI. `kb digest`
  et `kb trend-report` en sont les clients. L'inférence passe par Azure, en zone de données UE,
  en API compatible OpenAI : le modèle se choisit en configuration. Son architecture :
  [docs/architecture-api-ia.md](docs/architecture-api-ia.md).
- **Métriques** de chaque appel (durée, jetons, coût estimé, erreurs, fidélité), sur une ligne
  JSON de la sortie standard et en OpenTelemetry vers Grafana Cloud, en région UE. Un tableau de
  bord les montre à jour et dans le temps, et cinq alertes sur seuil partent par e-mail : sorties
  invalides, fidélité basse, coût au-dessus du budget, appels en échec, demande de compte rendu de
  plus de 180 s. Le tableau et les alertes sont versionnés dans `observability/grafana/` ; leur
  installation, leur lecture et le relevé du bac à sable qui a déclenché les trois premières sont dans
  [documentation/monitoring_pour_docu.md](documentation/monitoring_pour_docu.md).
- **Plus tard, les fiches de lecture** : de mes clips du Web Clipper, puis des papiers que je
  garde dans Zotero, le modèle rédigera des fiches de lecture, réunies en un wiki (#168). Aucun
  code ne les écrit encore, et le wiki n'est pas de la mise en ligne du 08/11 (#170).

## Hors périmètre de la v0

- Les contradictions signalées entre pages du wiki, son interrogation, le lint par l'IA.
- Mes notes comme entrées du wiki.
- Les livres en PDF, et les images, tableaux et pages scannées des PDF.
- Le serveur MCP.
- Tout entraînement de modèle.

## Conduite du projet

### Acteurs

- **Moi** : je porte le projet, je le pilote, je relis, je teste, je décide et je fusionne. K-B
  est mon projet support de la certification Développeur IA (RNCP37827).
- **Claude Code** écrit l'essentiel du code et de la documentation, sous ma relecture.
- **time-knight**, un agent Claude Code, tient les jalons et relaie mes décisions.
- **Mon organisme de formation** fournit l'abonnement Azure sur lequel tourne le modèle.

Les utilisateurs du produit sont décrits plus haut, dans « Utilisateurs ».

### Contraintes techniques

- **Python 3.13** (`.python-version`), langage du code ; dépendances et environnement par
  [uv](https://docs.astral.sh/uv/). **SQL** pour le schéma et les requêtes
  (`src/k_b/database/schema.sql`, module `sqlite3`, sans ORM ; pour PostgreSQL,
  `schema_postgresql.sql` et psycopg 3).
- **Base** : SQLite aux deux premiers temps, le Mac puis des conteneurs en local (voir « Le POC
  du 25/10 et la suite ») ; au troisième (Azure Container Apps, 08/11), PostgreSQL, que
  `KB_DATABASE_URL` choisit (journal ADR, 2026-11-06, « Base : PostgreSQL en ligne, par un
  adaptateur maison (#417) »). Les deux moteurs lisent le même SQL : aucun SQL propre à SQLite
  n'est ajouté (règle 1 de `.claude/rules/poc.md`). La base du Mac ne passe pas en ligne : la base
  en ligne repart du brut ([docs/stockage.md](docs/stockage.md), « Faire évoluer le schéma »).
- **Données hors du dépôt**, dans le dossier `KB_DATA_DIR` (`~/.knowledge_base` sur ma machine,
  journal ADR du 2026-10-09). Au deuxième temps, en conteneurs, la base ira dans un volume nommé et
  le brut dans un dossier partagé avec les conteneurs (journal ADR, 2026-10-15, « POC du 25/10 »,
  décision 2 ; #200).
- **Réglages par variables d'environnement** : hôtes, ports, chemins et secrets ; un secret n'a
  pas de valeur par défaut (règle 2 de `.claude/rules/poc.md`).
- **Données personnelles** : le modèle traite en zone de données UE ; ce que K-B garde, et
  combien de temps, est tenu par le [registre des traitements](docs/registre-traitements.md).
- **Contrôles** : chaque PR vers `main`, branche protégée, passe les cinq jobs requis de la CI
  (`audit`, `tests`, `lint`, `types`, `tests-postgresql`) avant d'être fusionnée.

### Budget

| Poste | Coût |
|---|---|
| API GitHub | un jeton en lecture seule, sans frais ([docs/jeton-github.md](docs/jeton-github.md)) |
| BigQuery (GH Archive) | bac à sable sans compte de facturation : au-delà du quota gratuit (1 Tio lu par mois), une requête est refusée, jamais facturée ([docs/bigquery.md](docs/bigquery.md)) |
| Modèle des fiches | gpt-6-luna sur Azure AI Foundry, sur l'abonnement Azure de mon organisme de formation, fourni pour ce projet : région France Central, zone de données UE, 140 000 jetons par minute (journal ADR, 2026-10-17). Je n'en vois pas la facturation. Ordre de grandeur : au pire environ 420 000 jetons par demande de fiches, à 0,12 $ en entrée et 0,60 $ en sortie par million de jetons, prix UE, soit quelques centimes (journal ADR, 2026-10-16) ; les appels d'une demande sont détaillés dans [docs/fiches-veille.md](docs/fiches-veille.md), « Lecture plafonnée » |
| Mise en ligne du 08/11 : coûts communs aux deux options (France Central, prix publics en dollars relevés le 2026-10-25, mois de 730 h) | **8,96 $ par mois** sans l'offre gratuite d'Azure Container Apps, **5,26 $** avec elle ; **29,32 $**, ou environ **27,70 $**, si les deux API gardent une réplique. Le détail : le job de collecte et d'import, une exécution par jour de 15 min à 0,5 vCPU et 1 Gio (hypothèse, non mesurée), 0,41 $ au tarif actif (0,000024 $ par vCPU-seconde, 0,000003 $ par Gio-seconde) ; `kb serve-data` et `kb serve-ai`, 0,5 vCPU et 1 Gio chacune, à zéro réplique au repos (décidé le 06/11, #414) et actives 1 h par jour (hypothèse), 3,29 $, ou 23,65 $ avec une réplique gardée, au tarif de repos (0,000003 $ par vCPU-seconde et par Gio-seconde) ; le brut dans Blob Storage (Hot LRS, 0,0192 $ par Go et par mois), 10 Go supposés, non mesurés, 0,19 $ ; le registre d'images Azure Container Registry Basic (0,1666 $ par jour, 10 Go compris), 5,07 $, ou 0 $ avec le registre de GitHub (GHCR), gratuit pour un paquet public ; ACR Basic choisi le 06/11 (#414), tiré par identité managée, sans secret ; les journaux dans Log Analytics, 0 $ sous 5 Go par mois, puis 2,76 $ par Go. L'offre gratuite (180 000 vCPU-secondes, 360 000 Gio-secondes et 2 millions de requêtes par abonnement et par mois) couvre le job et les deux API à zéro réplique (123 188 vCPU-secondes, 246 375 Gio-secondes) ; elle vaut par abonnement, et celui de la mise en ligne n'est pas connu. |
| Mise en ligne, option SQLite et Blob | **0,02 $ par mois** de plus : la base, un fichier produit par le job puis rangé dans Blob Storage, et lu par `kb serve-data` au démarrage (hypothèse : la façon de la lire n'est pas décidée), 1 Go supposé, au prix du brut |
| Mise en ligne, option PostgreSQL | **18,13 $ par mois** de plus : Azure Database for PostgreSQL, serveur flexible Burstable B1ms (1 vCore, 2 Gio), 0,019 $ de l'heure, 13,87 $, et 32 Gio de stockage, le minimum, à 0,133 $ par Go et par mois, 4,26 $ ; une sauvegarde au-delà du stockage compris est comptée 0,10 $ par Go et par mois, non chiffrée. Microsoft déconseille le niveau Burstable pour la production. |
| Temps | chaque issue porte son estimation en heures ; les jalons les regroupent |

Ces coûts ont été relevés avant que « La base au temps 3 » soit tranchée, pour PostgreSQL, le 2026-11-06 (journal ADR).

#### Sources du budget (consultées le 2026-10-25)

- Prix de France Central : [API des prix de détail d'Azure](https://learn.microsoft.com/rest/api/cost-management/retail-prices/azure-retail-prices) (Microsoft Learn), requête `https://prices.azure.com/api/retail/prices` filtrée par `armRegionName eq 'francecentral'` et par `serviceName` (`Azure Container Apps`, `Container Registry`, `Storage`, `Azure Database for PostgreSQL`, `Log Analytics`). Les pages de prix d'Azure n'affichaient pas leurs chiffres ce jour-là.
- Offre gratuite, facturation des jobs et compteur de gestion (plan Dedicated seulement) : [Azure Container Apps pricing](https://azure.microsoft.com/en-us/pricing/details/container-apps/).
- Stockage minimal de 32 Gio et usage du niveau Burstable : [Compute options in Azure Database for PostgreSQL](https://learn.microsoft.com/azure/postgresql/compute-storage/concepts-compute) (Microsoft Learn, mis à jour le 2026-07-08).
- Stockage compris dans Container Registry Basic : [Azure Container Registry service tiers](https://learn.microsoft.com/azure/container-registry/container-registry-skus) (Microsoft Learn).
- GHCR gratuit pour un paquet public : [How use of GitHub Packages is measured](https://docs.github.com/en/billing/concepts/product-billing/github-packages) (GitHub Docs).

### Organisation du travail

Une issue par changement, suivie sur un board GitHub Project (Backlog, Ready, In progress, In
review, Done). Chaque changement suit le même cycle : une conception courte dans l'issue, que je
valide ; une branche ; les tests d'abord ; les contrôles du dépôt ; une revue par un agent sans
contexte ; une note pédagogique ([docs/journaling/](docs/journaling/)) ; une PR vers `main`, que
je fusionne. Les décisions et leur pourquoi sont consignées dans le
[journal ADR](docs/ADR/journal-decisions-projet.md).

### Planning

Les jalons et leurs issues sont sur la
[page des jalons](https://github.com/SabineLaurent/K-B/milestones). Les jalons encore ouverts,
relevés le 14/11/2026 (`gh api 'repos/SabineLaurent/K-B/milestones?state=all'`) :

| Jalon | Échéance | Issues fermées | Issues ouvertes |
|---|---|---|---|
| POC 25/10 | 25/10/2026 | 54 | 8 |
| Oral blanc E1 E3 29/10 | 29/10/2026 | 6 | 2 |
| Fiches de veille tous les 3 jours | 01/11/2026 | 0 | 2 |
| Mise en ligne 08/11 | 08/11/2026 | 8 | 7 |
| Wiki : ingest des clips | sans date | 0 | 1 |

Les quatre premiers jalons, « Cadrage et socle », « Fusion et base », « API « quoi de neuf » » et
« Collecte multi-sources », sont fermés.

### Le POC du 25/10 et la suite

**Le 25/10** (journal ADR, 2026-10-20, « Squelette E1 E3 : cadrage du 20/10 », décision 1) : K-B
tourne sur ma machine, sans conteneur ; c'est le premier de trois temps. La collecte, l'import,
l'API de données et l'API IA s'y lancent par `kb`. L'API IA rédige des comptes rendus de veille par sujet,
chacun depuis la fin du précédent du même sujet (le premier sur `KB_DIGEST_WINDOW_DAYS`, 3 jours par
défaut), avec gpt-6-luna ; le modèle
ne choisit le sujet que dans une liste fermée que je tiens. Le retour se lit dans la console, et les
fiches en `.md` dans mon coffre : ni interface CLI dédiée ni front. La collecte et l'import sont
lancés à la main, et conçus comme des jobs. Au deuxième temps, avant le 29/10 si le temps le permet,
des conteneurs en local répètent le déploiement : Zotero et les clips y restent collectés sur ma
machine (`KB_COLLECT_ONLY`), sans que ma bibliothèque soit montée dans un conteneur.

**Où on en est** : la collecte, l'import, l'API de données, le service des fiches par l'API IA
(`kb serve-ai`, #156) et leur écriture en `.md` dans le coffre (`kb digest`, #209) sont codés (voir
« Installer et lancer »), comme l'export des métriques du modèle vers Grafana Cloud (#162). Leur
tableau de bord et leurs trois alertes sur seuil sont livrés (#164), et les trois alertes ont été
déclenchées dans un bac à sable le 08/11 ; deux de plus, appels en échec et demande de plus de 180 s, le
18/11 (#633, #634), sans scénario du bac à sable. Restent, dans #164, le réimport du tableau et de la règle
de fidélité, changés depuis, et l'essai d'accessibilité ; puis, au deuxième temps, l'image étant
construite (#200), l'installation par compose (#202).

**La suite** :

- au 08/11, mise en ligne sur Azure Container Apps : brut dans Azure Blob Storage, collecte en
  job déclenché par cron ; la base sur PostgreSQL ;
- après le 29/10, la compilation des clips en wiki ;
- après le 08/11, la recherche `kb search`.

## Installer et lancer

**Prérequis** : Python 3.13 ou plus récent (`requires-python` du `pyproject.toml`) et
[uv](https://docs.astral.sh/uv/).

**Installer** :

```sh
git clone https://github.com/SabineLaurent/K-B.git
cd K-B
uv sync
```

**Variables d'environnement** :

| Variable | Obligatoire | Rôle |
|---|---|---|
| `KB_DATA_DIR` | oui | dossier des données, hors du dépôt ; il doit exister. La collecte écrit le brut dans `<KB_DATA_DIR>/raw/` et son état dans `<KB_DATA_DIR>/collection_state.json`. |
| `KB_DATABASE_URL` | non | l'URL d'une base PostgreSQL, `postgresql://…` ou `postgres://…`, créée hors de K-B en UTF8 et en collation C ([docs/stockage.md](docs/stockage.md), « Le SGBD »). Sans elle, la base est le fichier SQLite `<KB_DATA_DIR>/k-b.sqlite`. Une autre valeur, vide comprise, une URL que libpq ne lit pas, ou une variable que libpq lit posée à côté (`PGHOST`, `PGPASSWORD`…) : code 2, sans que la valeur soit citée. Lue par `kb create-db`, `kb migrate-database`, `kb import`, `kb purge` (et `kb daily-routine`, qui lance ces deux-là) et `kb serve-data`. |
| `KB_ZOTERO_DIR` | non | dossier de données de Zotero, celui qui contient `zotero.sqlite`, en chemin complet (un `~` écrit dans `.env` n'est pas développé). Sans elle, `kb collect` saute Zotero et l'affiche (`zotero: skipped (KB_ZOTERO_DIR not set)`). Avec elle, les papiers et leurs surlignages sont extraits dans `<KB_DATA_DIR>/raw/selected_library/zotero/`, sans que K-B ouvre la base de Zotero : il en lit une copie temporaire. |
| `KB_VAULT_DIR` | non | dossier du coffre Obsidian de K-B, celui qui contient `Clippings/`, en chemin complet (un `~` écrit dans `.env` n'est pas développé). Sans elle, `kb collect` saute les clips et l'affiche (`clipping: skipped (KB_VAULT_DIR not set)`). Avec elle, chaque clip nouveau ou changé est copié tel quel dans `<KB_DATA_DIR>/raw/selected_library/clipping/` ; K-B ne modifie jamais les clips. `kb write-tops` écrit les fiches des tops dans `veille/tops/` du coffre, `kb digest` les comptes rendus de veille dans `veille/<sujet>/`, `kb trend-report` les comptes rendus des tendances dans `veille/tendances/` ; aucun des trois ne tourne sans elle (code 2). |
| `GOOGLE_APPLICATION_CREDENTIALS` | non | chemin complet de la clé JSON du compte de service BigQuery, rangée hors du dépôt ([docs/bigquery.md](docs/bigquery.md)). Elle est lue par le client BigQuery ; K-B ne l'ouvre pas. Sans elle, `kb collect` saute GH Archive et l'affiche (`gh_archive: skipped (GOOGLE_APPLICATION_CREDENTIALS not set)`). Avec elle, les dépôts qui montent sur 3 jours sont extraits dans `<KB_DATA_DIR>/raw/automated_watch/gh_archive/`. |
| `KB_COLLECT_ONLY` | non | les dossiers des sources que `kb collect` lance, séparés par des virgules (`zotero,clipping`) ; la casse ne compte pas. Sans elle, pas de filtre : chaque source tourne comme avant (Zotero, clips et GH Archive selon leur variable). Une source écartée affiche `<dossier>: skipped (not in KB_COLLECT_ONLY)` ; un nom qui n'est pas un dossier de source, une valeur ou une entrée vide, ou une source choisie sans sa variable (`zotero` sans `KB_ZOTERO_DIR`) : code 2, rien n'est collecté ([docs/specs-collecte.md](docs/specs-collecte.md), « Choisir les sources »). |
| `KB_GITHUB_TOKEN` | non | jeton GitHub en lecture seule ([docs/jeton-github.md](docs/jeton-github.md)). Sans lui, l'API GitHub accepte 60 requêtes par heure au lieu de 5 000. |
| `KB_DATA_API_KEY_<CLIENT>` | pour `kb serve-data` | la clé d'un client de l'API de données (`<CLIENT>` en `A-Z`, `0-9` et `_`, par exemple `KB_DATA_API_KEY_TERMINAL`), une variable par client ([docs/specs-api.md](docs/specs-api.md)). |
| `KB_AI_API_KEY_<CLIENT>` | pour `kb serve-ai`, `kb digest` et `kb trend-report` | la clé d'un client de l'API IA, une variable par client, mêmes règles que `KB_DATA_API_KEY_<CLIENT>` ; `kb digest` est le client `KB_DIGEST` et lit la même variable, `KB_AI_API_KEY_KB_DIGEST` ; `kb trend-report` est le client `KB_TREND_REPORT`, `KB_AI_API_KEY_KB_TREND_REPORT`, avec une autre clé (`kb serve-ai` refuse deux fois la même). Chacun n'ouvre que sa route ; tout autre client reçoit 403. Les autres réglages de `kb serve-ai` (modèle, API de données, hôte, port, fenêtre) sont décrits dans `.env.example`. |
| `KB_AI_API_URL` | non | l'adresse de l'API IA pour `kb digest` et `kb trend-report`, `https`, ou `http` vers `127.0.0.1` ou `localhost`, ou, avec `KB_DEPLOYMENT_ENVIRONMENT=sandbox`, vers `api-donnees` ou `api-ia`, les services d'un compose ; sans utilisateur, requête ni fragment. Une autre URL `http` fait sortir la commande en 2, le message nomme la variable sans citer sa valeur (#473) ; la même règle vaut pour `KB_DATA_API_URL`, lue par `kb serve-ai`, et pour les deux URL de `kb smoke-test` et `kb digest-watch`. Sans elle, `http://127.0.0.1:8001` (`core/config.py`) ; elle ne suit pas `KB_AI_API_PORT` : la changer aussi quand le port change. |
| `KB_WEB_OPERATOR_ID` | pour `kb serve-web`, sauf `KB_WEB_AUTH=off` | l'identifiant d'objet de l'opératrice dans Microsoft Entra, un GUID : chaque requête au site, sauf `/health`, doit le porter dans l'en-tête `X-MS-CLIENT-PRINCIPAL-ID`, que pose Azure Container Apps une fois la connexion faite. Jamais journalisé ni cité. `KB_WEB_AUTH=off` n'en lit aucun, sur `127.0.0.1` et hors d'Azure seulement ; `KB_WEB_HOST`, `KB_WEB_PORT` et `KB_WEB_ALLOWED_HOSTS` changent l'hôte, le port et les noms servis ([docs/site-web.md](docs/site-web.md)). |

**Créer la base** (une fois) :

```sh
mkdir -p ~/.knowledge_base
KB_DATA_DIR=~/.knowledge_base uv run kb create-db
```

`kb create-db` crée `<KB_DATA_DIR>/k-b.sqlite` : les tables, les 7 sources, le mode WAL. Avec
`KB_DATABASE_URL`, il crée les tables et les 7 sources dans la base PostgreSQL de l'URL, qui doit
déjà exister. Code de sortie :

- 0 : la base est créée ;
- 1 : la création a échoué (dossier en lecture seule, disque plein…). Le message dit l'erreur, et
  aucun fichier de base ne reste ;
- 2 : `KB_DATA_DIR` manque ou n'est pas un dossier existant, ou la base existe déjà. Une base
  existante n'est pas touchée : pour repartir de zéro, supprimer le fichier. Sur PostgreSQL :
  `KB_DATABASE_URL` est refusée, ou la base a déjà sa table `source`, ou elle n'est pas en UTF8 et
  en collation C ;
- 130 : `kb create-db` a reçu SIGINT (Ctrl-C) : comme pour 1, aucun fichier de base ne reste, sauf
  si un second Ctrl-C coupe sa suppression (le supprimer à la main).

**Lancer une collecte** (une par jour, voir [docs/specs-collecte.md](docs/specs-collecte.md)) :

```sh
KB_DATA_DIR=~/.knowledge_base uv run kb collect
```

Avec le jeton rangé dans le `.env` à la racine du dépôt, ignoré par git :
`KB_DATA_DIR=~/.knowledge_base uv run --env-file .env kb collect`.

`kb collect` journalise son début (`collection started: 17 sources selected`), le départ de
chaque source puis ce qu'elle a écrit, et sa fin avec la durée, puis affiche une ligne par source
(`ok` avec le nombre de fichiers bruts écrits, `ok (1 raw file)`, ou `failed`, avec le type de
l'erreur ; `skipped` pour Zotero sans `KB_ZOTERO_DIR`, les clips
sans `KB_VAULT_DIR`, GH Archive sans `GOOGLE_APPLICATION_CREDENTIALS`, une source que
`KB_COLLECT_ONLY` écarte). Code de sortie : 0 si
tout a réussi ; 4 si au moins une source a réussi et au moins une a échoué, l'état de collecte
écrit ; 1 si aucune source lancée n'a réussi ou si l'état de collecte n'a pas pu être écrit ; 2 si
`KB_DATA_DIR` manque, n'est pas un dossier existant, si l'état de collecte est illisible, ou si
`KB_COLLECT_ONLY` est refusée ; 143 si `kb collect` reçoit SIGTERM (`docker stop`), 130 s'il reçoit
SIGINT (Ctrl-C) : ce qui a été fait avant le signal est gardé ; reçu avant l'écriture de l'état de
collecte, il laisse l'état inchangé, et la collecte suivante repart des mêmes dates.

**Importer le brut dans la base** (après une collecte) :

```sh
KB_DATA_DIR=~/.knowledge_base uv run kb import
```

`kb import` lit les fichiers de `<KB_DATA_DIR>/raw/automated_watch/` et de
`<KB_DATA_DIR>/raw/selected_library/` (les extraits Zotero) pas encore importés et
écrit leurs items dans la base, qui écarte les doublons, et les lignes des classements GH Archive
dans sa table `trend` ; sans nouveau brut, il ne lit rien,
sauf un fichier illisible, relu et rejeté à chaque import. Il journalise son début, sa fin avec
la durée et le nom de son journal, puis affiche son bilan sur une ligne
(`import: 35 raw read, 120 written, 40 trend rows, 3 left out, 2 rejected, 4 withdrawn`) : fichiers
bruts lus, items écrits (nouveaux ou mis à jour), lignes de tendance écrites, items et fenêtres de
classement écartés (doublons, ou versions qui ne sont pas plus récentes que celle de la base),
rejets et lignes retirées (CISA, entrées et surlignages Zotero). Les rejets sont détaillés dans
`<KB_DATA_DIR>/journals/import-journal-<AAAA-MM-JJTHHMMSSZ>.jsonl`, un journal par import, gardé 6 mois. Pour reconstruire
la base depuis tout le brut : supprimer `k-b.sqlite`, puis `kb create-db` et `kb import`. Code de
sortie :

- 0 : l'import a réussi ;
- 1 : l'import a échoué. Il n'écrit rien, ni dans la base ni au journal : le journal est écrit
  avant la validation de la base ;
- 2 : `KB_DATA_DIR` manque, la base n'existe pas (`kb create-db`), le journal de cette
  seconde existe déjà (relancer `kb import`), ou `KB_DATABASE_URL` est refusée. Une base
  PostgreSQL sans ses tables sort en 1 (#421) ;
- 143 : `kb import` a reçu SIGTERM (`docker stop`). Reçu avant la validation de la base, il
  n'écrit rien, comme pour 1, ni dans la base ni au journal ; reçu pendant ou après, l'import est
  gardé, avec son journal. Sur PostgreSQL, un signal reçu pendant la validation laisse son issue
  inconnue : le journal est gardé, et la ligne `import commit interrupted, outcome unknown` le
  dit ;
- 130 : `kb import` a reçu SIGINT (Ctrl-C), avec le même effet que SIGTERM, sauf un second Ctrl-C,
  qui peut couper l'annulation : SIGTERM ignore un second signal, SIGINT non.

**Purger ce qui a passé sa durée** (après un import, ou seul) :

```sh
KB_DATA_DIR=~/.knowledge_base uv run kb purge
```

`kb purge` supprime ce qui a passé sa durée de conservation, à compter de l'heure de son lancement :
les bruts remplacés des catalogues d'état (Zotero, CISA KEV), la veille de la base (items et
tendances, 3 ans), le brut de plus de 6 mois, les lignes du registre dont le fichier n'est plus là
et que rien ne cite, puis les logs et les journaux d'import de plus de 6 mois ([registre des traitements](docs/registre-traitements.md),
« Procédure de tri »). `kb import` ne purge rien. Chaque purge journalise ce qu'elle a supprimé,
en nombres, jamais un nom, puis `kb purge` affiche le bilan sur une ligne
(`purge: 2 superseded raw files, 40 items, 0 trend rows, 12 references, 0 tracked repositories, 3 raw collections, 3 registry rows, 5 logs and journals deleted`).
Code de sortie :

- 0 : les purges ont réussi ;
- 1 : une purge a échoué ; les suivantes ne tournent pas, et le `kb purge` suivant les relance
  (`purge failed: … ; run kb purge again`). Aucun bilan n'est affiché : ce que les purges d'avant ont
  supprimé n'est qu'au journal ;
- 2 : `KB_DATA_DIR` manque, la base n'existe pas (`kb create-db`), ou `KB_DATABASE_URL` est refusée ;
- 143, 130 : `kb purge` a reçu SIGTERM ou SIGINT (Ctrl-C) ; la purge en cours dans la base est
  annulée, et ce qui a déjà été supprimé le reste.

**Écrire les fiches des tops dans le coffre** (après un import) :

```sh
KB_DATA_DIR=~/.knowledge_base KB_VAULT_DIR=<coffre> uv run kb write-tops
```

`kb write-tops` écrit, pour le top 100 des dépôts les plus étoilés et celui des plus forkés, une
fiche Markdown par jour de collecte encore présent dans le brut :
`<KB_VAULT_DIR>/veille/tops/most_starred/AAAA-MM-JJ.md` et `.../most_forked/AAAA-MM-JJ.md`,
nommée par le jour UTC du relevé. Une fiche qui existe n'est jamais réécrite, même par deux
lancements qui se chevauchent (#295) : deux collectes le
même jour ne donnent qu'une fiche, celle du premier relevé de ce jour encore dans le brut. Un
temporaire caché qu'un arrêt brutal laisse à côté d'une fiche (un SIGKILL, une session SMB perdue, ou
un SIGTERM reçu dans les quelques microsecondes entre sa création et le bloc qui le retire) arrête ce
top à chaque lancement, son relevé gardé, jusqu'à ce que le temporaire soit retiré à la main. Une fois
les fiches d'un top écrites, ses relevés lisibles plus anciens que le dernier relevé lisible sont
supprimés du brut ; au premier lancement, tout l'historique des relevés devient des fiches, puis
ces relevés sont supprimés. Il journalise son début et sa fin avec la durée, puis affiche une ligne
par top : `ok, 1 sheet written` ; `ok, 0 sheets written, the sheet of the day already exists` ;
`failed (<type>)` pour un top arrêté, avec le type de l'erreur seul, ou `failed (ranking_unreadable)`
pour un relevé illisible ou mal nommé, gardé ; `no ranking` sans relevé. Suivent les relevés
remplacés supprimés (`Older raw files deleted: N`, absent si un top a été arrêté : l'erreur a pu
venir pendant ses suppressions) et le dossier des fiches dans le coffre
(`Sheets vault path: veille/tops/`). Code de sortie :

- 0 : chaque top a réussi, ou n'a aucun relevé ;
- 4 : un top a échoué, et un autre a abouti. L'unité est le top : il échoue quand une erreur de
  lecture, d'écriture ou de suppression (`OSError`) ou une entrée refusée du coffre (lien
  symbolique, ou temporaire caché `.AAAA-MM-JJ.md.tmp` d'une fiche, `temporary_file_found`) l'arrête,
  ou quand il garde un relevé illisible (gardé, jamais supprimé, tant qu'il
  est là) ; il aboutit quand il va au bout et écrit une fiche, ou va au bout sans échec (un top
  sans relevé compris). Un top qui écrit ses fiches et garde un relevé illisible a donc échoué et
  abouti : seul, il sort en 4, jamais en 0 (échouer fermé). Aucun relevé n'est supprimé avant que
  les fiches de son top soient écrites ; une suppression qui échoue laisse celles déjà faites. Un
  top arrêté a sa ligne `failed (<type>)` ; son erreur est au journal. L'autre top est traité quand
  même ;
- 1 : un top a échoué et aucun n'a abouti (les deux arrêtés, ou rien que des relevés illisibles) ;
- 2 : `KB_DATA_DIR` manque, ou `KB_VAULT_DIR` manque ou n'est pas un dossier existant : rien n'est
  lu dans le brut, rien n'est écrit dans le coffre ni supprimé, aucun dossier du coffre n'est créé ;
  l'erreur va au journal ;
- 143 : `kb write-tops` a reçu SIGTERM (`docker stop`), 130 : SIGINT (Ctrl-C). Les fiches déjà
  écrites sont gardées, aucun relevé n'est supprimé avant que ses fiches soient écrites. Aucune
  ligne de top n'est affichée, pas même celle d'un top déjà fini : elles le sont à la fin.

**Toute la chaîne en dev**, comme en ligne, où une automatisation enchaînera les étapes :

```sh
export KB_DATA_DIR=~/.knowledge_base KB_VAULT_DIR=<coffre>
uv run --env-file .env kb collect; uv run --env-file .env kb import; uv run --env-file .env kb purge
uv run --env-file .env kb write-tops
```

Chaque étape tourne même si la précédente a échoué en partie (un code 4 de `kb collect`, une
source en panne), et garde son propre code de sortie : `kb write-tops` ne lit que le brut, pas la
base.

Les codes de toutes les commandes et leur sens sont listés par `uv run kb --help`.

**Lancer l'API** (la liste des items, en lecture seule, sur la machine ; voir
[docs/specs-api.md](docs/specs-api.md)) :

1. Créer une clé par client, qui identifie le programme qui appelle (le terminal, un script, un
   agent) :

   ```sh
   uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

   et la ranger dans le `.env` : `KB_DATA_API_KEY_TERMINAL=<la clé>`.
2. Lancer l'API, qui écoute par défaut sur `http://127.0.0.1:8000`, et seulement sur la machine
   (`KB_DATA_API_HOST`, `KB_DATA_API_PORT` et `KB_DATA_API_ALLOWED_HOSTS` changent l'hôte, le port
   et les hôtes permis : `docs/specs-api.md`, « Règles communes ») :

   ```sh
   KB_DATA_DIR=~/.knowledge_base uv run --env-file .env kb serve-data
   ```

3. L'appeler avec la clé :

   ```sh
   curl -H "Authorization: Bearer <la clé>" "http://127.0.0.1:8000/items?kind=paper&limit=5"
   ```

La documentation de l'API est servie sur `http://127.0.0.1:8000/docs`, sans clé, seulement avec
`KB_DEPLOYMENT_ENVIRONMENT=sandbox` dans le `.env` (404 sinon, en production comme sans la variable) ;
son OpenAPI est versionnée dans `docs/api/openapi-donnees.json`, réécrite par `uv run kb openapi` lancé à la
racine du dépôt (ailleurs, sans dossier `docs/api`, il n'écrit rien et sort en code 2). `kb serve-data` journalise une ligne par requête dans
`<KB_DATA_DIR>/logs/kb-serve-data.log`, avec le nom du client, jamais sa clé. Code de sortie 2, sans
lancer l'API, si `KB_DATA_DIR` manque, si aucune clé n'est donnée, si un nom de client est vide ou
hors `A-Z`, `0-9` et `_`, si une clé a moins de 32 caractères ou un caractère hors `A-Z`, `a-z`,
`0-9`, `_` et `-` (l'alphabet de `token_urlsafe`), ou si deux clients ont la même clé :
le message nomme la variable, jamais sa valeur. Code 2 aussi si l'hôte n'est pas une adresse IPv4,
si le port n'est pas un entier de 1 à 65535, si la liste des hôtes permis est vide ou contient une
entrée vide, une entrée avec `*` ou une entrée hors nom en minuscules, ou si `KB_LOG_TO_FILE` n'est
ni `true` ni `false` (`false` : journal sur la sortie d'erreur seule) ; le message nomme la
variable et cite la valeur refusée. Code 2 encore si `KB_DATABASE_URL` est refusée (voir « Variables
d'environnement ») : le message nomme la variable, sans citer sa valeur. Avec une base PostgreSQL,
`kb serve-data` démarre sans attendre la base ; une base injoignable ne se voit qu'à la requête,
qui répond 500 `database_error` ([docs/specs-api.md](docs/specs-api.md), « Lecture seule »). Si le port est déjà pris (par exemple par un autre
`kb serve-data`), uvicorn écrit `address already in use` au journal et `kb serve-data` sort en code 3.
Une fois le serveur démarré, un Ctrl-C arrête uvicorn proprement : `kb serve-data` sort en code 0,
sans la ligne `kb stopped by SIGINT` des autres commandes ; pendant le démarrage, le code dépend du
moment : 130 avec cette ligne, 3 ou 0.

Limites :

- un client se retire en retirant sa variable, puis en redémarrant `kb serve-data` : un retrait ne
  prend effet qu'au redémarrage ;
- une variable `KB_DATA_API_KEY_*` exportée dans le profil du shell (`~/.zshrc`) reste valide même
  retirée du `.env` : la retirer aussi de là ;
- `uv run --env-file .env kb serve-data` charge tout le `.env`, donc aussi le jeton GitHub et les
  identifiants Google, dont l'API n'a pas besoin : `kb serve-data` tourne avec plus de droits que sa
  tâche n'en demande (moindre privilège).

**Lancer l'API IA** (les comptes rendus de veille d'une fenêtre, par sujet ; voir
[docs/fiches-veille.md](docs/fiches-veille.md)) : elle lit la veille par l'API de données, qui doit
donc tourner, et appelle le modèle ; elle ne garde rien entre deux demandes.

1. Ranger dans le `.env` une clé par client de l'API IA, faite comme celles de l'API de données
   (`KB_AI_API_KEY_KB_DIGEST=<la clé>`, `KB_AI_API_KEY_KB_TREND_REPORT=<une autre clé>`), la clé que l'API IA envoie à l'API de données
   (`KB_DATA_API_KEY_AI_DIGEST=<une autre clé>`, que `kb serve-data` lit aussi : redémarrer `kb serve-data`),
   le jeton GitHub des comptes rendus des tendances (`KB_AI_GITHUB_TOKEN=<le jeton>`, un second jeton
   *fine-grained* sans permission : [docs/jeton-github.md](docs/jeton-github.md)), et le modèle
   (`KB_LLM_PROVIDER` et ses variables, `.env.example`). `replay` répond par les réponses d'un
   fichier, sans réseau ni clé ni coût.
2. Lancer l'API IA, à côté de `kb serve-data` ; elle écoute par défaut sur `http://127.0.0.1:8001`, et
   seulement sur la machine (`KB_AI_API_HOST` et `KB_AI_API_PORT` changent l'hôte et le port ;
   `KB_DIGEST_WINDOW_DAYS`, de 1 à 14, la fenêtre d'un sujet sans début, 3 jours) :

   ```sh
   KB_DATA_DIR=~/.knowledge_base uv run --env-file .env kb serve-ai
   ```

3. Demander les fiches d'une fenêtre (`window_days` facultatif, de 1 à 14 ; `since_by_subject`
   facultatif, le début d'un sujet, date avec fuseau, ramené à 14 jours au plus :
   [docs/fiches-veille.md](docs/fiches-veille.md), « Fenêtre ») :

   ```sh
   curl -X POST -H "Authorization: Bearer <la clé>" -H "Content-Type: application/json" \
     -d '{"window_days": 3, "since_by_subject": {"models": "2026-11-09T10:00:00Z"}}' \
     http://127.0.0.1:8001/digests
   ```

La documentation de l'API IA est servie sur `http://127.0.0.1:8001/docs`, sans clé, seulement avec
`KB_DEPLOYMENT_ENVIRONMENT=sandbox` (404 sinon) ; son OpenAPI est versionnée dans `docs/api/openapi-ia.json`, réécrite par `uv run kb openapi` avec celle de
l'API de données. `kb serve-ai` journalise une ligne par requête dans
`<KB_DATA_DIR>/logs/kb-serve-ai.log` (ni `kb.log` ni `kb-serve-data.log` : un seul `kb serve-ai` par
`KB_DATA_DIR`), avec le nom du client et l'identifiant de la requête, rendu aussi dans l'en-tête
`X-Request-ID` de chaque réponse ; chaque appel au modèle écrit une ligne JSON de métrique sur la
sortie standard, sans texte. Code de sortie 2, sans lancer l'API, si `KB_DATA_DIR` manque, si une
clé, l'hôte, le port, la fenêtre, le modèle, la clé `KB_DATA_API_KEY_AI_DIGEST` ou le jeton
`KB_AI_GITHUB_TOKEN` (absent, *classic*, ou un caractère hors `[A-Za-z0-9_]`) est refusé : le
message nomme la variable, jamais une clé, un jeton ni l'URL du modèle. Port déjà pris : code 3, et Ctrl-C une
fois démarré : code 0, comme `kb serve-data`.

**Changer une clé** (la clé reste fixe, sans date d'expiration : journal ADR, 2026-10-20,
« Squelette E1 E3 », décision 3) :

- clé d'un client de l'API IA : faire une nouvelle clé, la ranger dans sa variable
  (`KB_AI_API_KEY_KB_DIGEST`, `KB_AI_API_KEY_KB_TREND_REPORT`), puis redémarrer `kb serve-ai` ; l'ancienne clé est refusée dès le
  redémarrage, pas avant. Retirer un client : retirer sa variable et redémarrer ;
- clé `KB_DATA_API_KEY_AI_DIGEST` : la changer dans le `.env`, puis redémarrer `kb serve-data` et
  `kb serve-ai`, qui la lisent tous deux ; tant que l'un des deux garde l'ancienne, chaque demande
  de fiches rend 502 `data_api_unauthorized` ;
- sur un 401 de l'API IA (`invalid_api_key`, clé absente, changée d'un seul côté ou retirée),
  `kb digest` n'écrit aucune fiche, ne cite jamais la clé, nomme la variable
  `KB_AI_API_KEY_KB_DIGEST` et sort en code 1 : la requête est partie (une clé absente de
  `kb digest` donne 2, rien n'est demandé) ; de même `kb trend-report`, qui nomme
  `KB_AI_API_KEY_KB_TREND_REPORT`.

**Limites de l'API IA** : une demande à la fois par route, 20 par 24 h glissantes
([docs/fiches-veille.md](docs/fiches-veille.md), « Accès »). Redémarrer `kb serve-ai` remet le compte à
zéro. Après un Ctrl-C de `kb digest`, l'API finit la demande en cours : la relance est refusée (429)
tant qu'elle n'a pas fini, environ 200 s au plus.

Limites : une variable `KB_AI_API_KEY_*` exportée dans le profil du shell reste valide même retirée
du `.env` ; `uv run --env-file .env kb serve-ai` charge tout le `.env`, donc aussi des secrets dont
l'API IA n'a pas besoin (moindre privilège).

**Écrire les comptes rendus de veille dans le coffre** (`kb serve-data` et `kb serve-ai` lancés ; voir
[docs/fiches-veille.md](docs/fiches-veille.md), « Fiches dans le coffre ») :

```sh
KB_DATA_DIR=~/.knowledge_base KB_VAULT_DIR=<coffre> uv run --env-file .env kb digest
```

`kb digest` demande à l'API IA la fiche de chaque sujet depuis la fin de la précédente : il lit le
`until` de la dernière fiche du sujet dans le coffre et l'envoie (#565) ; un sujet sans fiche prend
la fenêtre de `KB_DIGEST_WINDOW_DAYS`, lue par `kb serve-ai` ; un début de plus de 14 jours est
ramené à 14 jours, et journalisé. La demande part avec la clé `KB_AI_API_KEY_KB_DIGEST`, à
l'adresse `KB_AI_API_URL` (`http://127.0.0.1:8001` par défaut ; elle ne suit pas `KB_AI_API_PORT` :
la changer aussi). Il écrit une fiche par sujet rendu, `<KB_VAULT_DIR>/veille/<sujet>/AAAA-MM-JJ.md`,
au jour UTC de la demande, et une fiche « Aucun item classé dans ce sujet. » pour un sujet sans
item, d'où part son compte rendu suivant : un frontmatter (`subject`, `generated`, `model`, la
fenêtre du sujet, `since` et `until`, `items_capped`, la sorte coupée par le plafond et la date de son premier item laissé (`capped_kind`, `covered_after`),
`request_id`), les affirmations, chacune avec le numéro de ses sources, puis les sources, leur
titre et leur URL. Chaque affirmation et chaque titre est écrit en texte : ni lien, ni image, ni
balise, ni code, ni requête Dataview ne peut s'y activer. Une fiche n'est jamais réécrite, même par deux
lancements qui se chevauchent (#295) : s'il en existe
une du jour, aucune demande n'est faite. Une demande dure jusqu'à environ 220 s ; `kb digest`
attend 240 s au plus (une réponse de 8 000 000 d'octets au plus, et sans borne avant son premier
morceau : [docs/fiches-veille.md](docs/fiches-veille.md), « Fiches dans le coffre », « Limites »), sans nouvelle tentative, et montre qu'il attend : une ligne qui tourne dans un
terminal, une ligne datée toutes les 10 s ailleurs. Il journalise son début et sa fin, avec la durée, puis
affiche un bilan : la fenêtre et le nombre d'items lus, un tableau par sujet (statut, chemin de la
fiche), le total, puis le modèle et le `request_id`, que `logs/kb-serve-ai.log` reprend. Code
de sortie, l'unité étant le sujet :

- 0 : chaque sujet a sa fiche écrite, avec ou sans item ; ou rien n'est lu (une base vide, un
  import pas lancé) : aucune fiche n'est écrite, et chaque sujet garde son début ;
- 4 : un sujet a échoué (nommé par l'API IA, ou sa fiche non écrite) et au moins une fiche est
  écrite ;
- 1 : rien n'est écrit : l'API IA est injoignable, dépasse le délai, refuse la clé (le message
  nomme `KB_AI_API_KEY_KB_DIGEST`, jamais la clé), refuse la route à ce client (403, même message),
  refuse pour l'instant (429 : une demande tourne déjà, ou 20 demandes en 24 h), répond en échec (502,
  503, 504 : son état, son `X-Request-ID` et son `Retry-After` sont affichés) ou hors du schéma attendu ; ou chaque sujet a
  échoué ; ou une erreur du système (`OSError`, un dossier illisible) arrête le contrôle d'avant la
  demande, sans rien demander ;
- 2 : rien n'est demandé : `KB_DATA_DIR`, `KB_VAULT_DIR` (absente, ou pas un dossier existant) ou
  `KB_AI_API_KEY_KB_DIGEST` manque ou est refusée, une fiche du jour est déjà là, un dossier
  `veille/…` est un lien symbolique, ou la dernière fiche d'un sujet n'a pas de `until` valide
  (`previous_sheet_invalid`) ;
- 143 : `kb digest` a reçu SIGTERM, 130 : SIGINT (Ctrl-C). Les fiches déjà écrites sont gardées.

Le code 4 dit la même chose pour `kb collect` (l'unité est la source), `kb write-tops` (le top) et
`kb digest` (le sujet) : une partie a échoué, une autre est faite et gardée.

**Écrire le compte rendu des tendances dans le coffre** (`kb serve-data` et `kb serve-ai` lancés ;
contrat : [docs/tendances.md](docs/tendances.md)) :

```sh
KB_DATA_DIR=~/.knowledge_base KB_VAULT_DIR=<coffre> uv run --env-file .env kb trend-report
```

`kb trend-report` lit le registre des comptes rendus, `<KB_DATA_DIR>/trend_reports.json`, puis
demande à l'API IA les fenêtres de GH Archive postérieures à la dernière du compte rendu précédent
(les 4 dernières au premier), avec la clé `KB_AI_API_KEY_KB_TREND_REPORT`, à l'adresse
`KB_AI_API_URL`. Il écrit `<KB_VAULT_DIR>/veille/tendances/AAAA-MM-JJ.md`, au jour UTC du lancement :
un frontmatter (`generated`, la première et la dernière fenêtre, leur nombre, celui des manquantes,
`windows_capped`, `first_report`, `new_evaluated`, `repositories_dropped`, `model`, `request_id`), la
période et ses limites, la limite de GH Archive (un échantillon d'environ 1 % des étoiles), puis un
tableau des dépôts qui remplissent au moins un critère (durable, nouveau, en accélération) : lien,
critères, meilleur rang et rang par fenêtre (`hors top`, `—` pour une fenêtre manquante), et une
ligne des dépôts que GitHub a écartés, par motif, s'il y en a (l'API IA lit sur GitHub la fiche de
chaque candidat depuis #367 ; ses faits entrent dans le fichier avec #369). Il ajoute
enfin une entrée au registre, qui donne sa période au compte rendu suivant : le coffre n'est jamais
relu. Un compte rendu n'est jamais réécrit : s'il en existe un du jour, aucune demande n'est faite.
Il montre qu'il attend comme `kb digest`, puis affiche un bilan en comptes, sans nom de dépôt : la
période, les dépôts retenus et écartés, le chemin du fichier, le modèle (`none` tant qu'aucun ne
choisit, #368) et le `request_id`. Code de sortie :

- 0 : le compte rendu est écrit et noté au registre ; ou aucune fenêtre n'est postérieure au
  compte rendu précédent, ou la base n'en a aucune : rien n'est écrit, et le bilan le dit (une base
  plus ancienne que le registre, restaurée, donne un avertissement avec les deux dates) ;
- 1 : rien n'est écrit : l'API IA échoue comme pour `kb digest` (le message nomme
  `KB_AI_API_KEY_KB_TREND_REPORT` sur un 401 ou un 403), ou sa réponse contredit la demande (une période qui
  ferait reculer, sauter ou grossir le registre) ; ou le compte rendu n'est pas écrit (registre inchangé) ;
  ou il est écrit mais le registre n'est pas mis à jour : le message le dit, et le compte rendu
  suivant reprend ces fenêtres ; ou une erreur du système arrête le contrôle d'avant la demande ;
- 2 : rien n'est demandé : `KB_DATA_DIR`, `KB_VAULT_DIR` ou `KB_AI_API_KEY_KB_TREND_REPORT` manque
  ou est refusée, le registre est illisible ou hors de son schéma, le compte rendu du jour est déjà
  là, ou un dossier `veille/…` est un lien symbolique ;
- 143 : SIGTERM, 130 : SIGINT (Ctrl-C). Un compte rendu déjà écrit est gardé ; si le registre n'a
  pas suivi, le compte rendu suivant reprend ces fenêtres.

**Vérifier un job en ligne** (`kb smoke-test`, la commande du job `caj-kb-smoke-test`, #412) :

```sh
KB_DATA_DIR=<dossier> KB_EXCHANGE_BLOB_URL=https://<compte>.blob.core.windows.net \
  AZURE_CLIENT_ID=<client id de l'identité du job> uv run kb smoke-test
```

`kb smoke-test` demande `GET /health` à l'API de données (`KB_DATA_API_URL`) et à l'API IA
(`KB_AI_API_URL`), sans clé. Après le `/health` de chaque API, qui la réveille, trois sondes sans clé vérifient
qu'elle refuse ce qu'elle doit refuser (#499, `jobs/api_probes.py`) : une route à clé rend 401 (`GET /items`,
`POST /digests`), `GET /docs` rend 404 (200 avec `KB_DEPLOYMENT_ENVIRONMENT=sandbox`, où les API le servent) et
`HEAD /health` rend 405 ; le corps d'une réponse n'est jamais lu. Puis il demande le jeton de l'identité managée
attribuée au job (`AZURE_CLIENT_ID`,
un GUID ; sans lui, le SDK chercherait l'identité système, que les jobs de K-B n'ont pas), et liste
une page d'au plus 100 noms du conteneur `smoke-test` du stockage d'échange (`KB_EXCHANGE_BLOB_URL`,
en `https`, sans défaut). Les neuf contrôles tournent toujours. Il n'écrit que des comptes : jamais
le nom d'un blob (celui d'un clip est son titre), ni le message d'une erreur du SDK, mais son état
(`exchange_storage_forbidden`…), son statut HTTP et son code ; l'identité sans jeton, refusée ou
injoignable, est `exchange_storage_no_token`. Code de sortie :

- 0 : les deux API répondent `{"status":"ok"}`, chaque sonde reçoit son statut et le conteneur est listé ;
- 1 : un contrôle échoue (`health_failed`, `health_timeout`… pour le `/health` d'une API ;
  `probe_unexpected_status` avec le statut reçu, `probe_timeout` ou `probe_unavailable` pour une sonde) ;
- 2 : rien n'est contrôlé : une variable manque ou est refusée ;
- 143 : SIGTERM, 130 : SIGINT (Ctrl-C).

**Les commandes des jobs planifiés** (#413) : en ligne, tout tournera dans des jobs, rien sur le Mac.
`kb daily-routine` et `kb digest-watch`, commandes des jobs `caj-kb-daily-routine` (#330, chaque jour à 08:00 UTC)
et `caj-kb-digest-watch` (#423, le lundi et le jeudi à 10:00 UTC), déclarés dans `infra/`, enchaînent leurs étapes
dans le même processus, chacune avec le code qu'elle rendrait seule :

```sh
KB_DATA_DIR=<dossier> KB_VAULT_DIR=<coffre> KB_EXCHANGE_BLOB_URL=https://<compte>.blob.core.windows.net \
  AZURE_CLIENT_ID=<client id de l'identité du job> uv run kb daily-routine
uv run kb daily-routine --dry-run    # les étapes et leurs règles, rien lancé ni transféré, code 0
```

- `kb daily-routine` : le miroir du conteneur `clippings` vers `Clippings/` du coffre, `kb collect`,
  `kb import` (pas lancé si `kb collect` rend 1 ou 2), `kb purge` (lancé même si `kb import` échoue ou n'est pas lancé),
  `kb write-tops`, puis la publication de
  `veille/` vers le conteneur `watch`. L'étape Zotero viendra entre le miroir et `kb collect` (#425).
- `kb digest-watch` : `GET /health` des deux API, qui réveille une API à 0 réplique (`KB_DATA_API_URL`,
  `KB_AI_API_URL`), `kb digest`, de nouveau les deux `/health`, `kb trend-report`, puis la même
  publication. `kb trend-report` tourne même si `kb digest` échoue ; un réveil échoué n'arrête rien
  et ne compte pas dans le code de sortie (ses lignes ERROR restent) : une API injoignable fait
  échouer l'étape qui suit.
- Le miroir copie un clip du premier niveau que le coffre n'a pas, ou a plus ancien (à la même
  seconde, d'une autre taille) : date du blob contre date du fichier, qui prend ensuite celle du
  blob ; il ne supprime rien. Laissé de côté,
  sans échec : un blob dans un dossier (`/`), caché (`.` initial) ou qui ne finit pas par `.md`.
  Refusé, l'étape rend 4 : un clip que le partage ne peut pas porter (`\`, caractère de contrôle ou
  d'usage privé, `" : | < > * ?`, plus de 241 octets) ou plus gros que 1 000 000 octets. Le journal
  le cite par sa position dans la liste (`blob 12 of 120`), jamais par son nom ; il est refusé à
  chaque exécution jusqu'à ce que son blob soit supprimé de `clippings` (le renommer sur le Mac
  laisse l'ancien blob). Après une copie, la routine attend la marge de `kb collect` plus 5 s
  (65 s), pour qu'il lise le clip le jour même.
- La publication envoie chaque fiche de `veille/` absente de `watch`, à sa racine
  (`tops/<top>/<jour>.md`), sans jamais remplacer un blob ; les entrées cachées (dont les
  temporaires d'une écriture interrompue) et les liens sont laissés de côté ; un dossier illisible
  fait échouer l'étape.

Code de sortie : le pire de ceux des étapes, dans l'ordre 0, 4, 2, 1 (un 2 peut être bénin :
`kb digest` le rend quand la fiche du jour existe) ; 2 aussi quand rien n'est lancé, un réglage du job
(`KB_EXCHANGE_BLOB_URL`, `AZURE_CLIENT_ID`, `KB_VAULT_DIR`) manquant ou refusé ; 143 : SIGTERM, 130 :
SIGINT, la routine s'arrête sans lancer la suite.

**Les fiches en ligne sur le Mac** (`make download-watch-sheets`, #424) : chaque fiche du conteneur `watch`
que `veille/` du coffre n'a pas y est copiée, par le compte Entra de l'opératrice (rôle Storage Blob Data
Reader sur `watch`, #420). Une fois par séance, `az login --tenant <tenant>` : la commande prend le jeton
d'`az` (Azure CLI), dans le tenant de son compte courant ; ni AzCopy, ni `AZURE_CLIENT_ID`. Le `.env` porte
`KB_DATA_DIR`, `KB_VAULT_DIR` et `KB_EXCHANGE_BLOB_URL` (`https://<compte>.blob.core.windows.net`).

```sh
az login --tenant <tenant>
make download-watch-sheets
```

- Une fiche déjà dans `veille/` n'est ni téléchargée ni remplacée, même modifiée sur le Mac : un second
  passage copie 0 fiche.
- Seuls passent les noms `<dossier>/<jour>.md` (jour en `AAAA-MM-JJ`) d'un dossier où kb écrit : les
  9 sujets, `tops/most_starred`, `tops/most_forked`, `tendances`. Un nom de cette forme d'un autre
  dossier (un sujet ajouté ou retiré) est laissé de côté, sans échec. Tout autre nom est refusé, cité
  par sa position (`blob 3 of 12`), jamais écrit ; les autres fiches sont copiées quand même. Refusés
  aussi : un blob de plus de 4 000 000 octets, un texte qui n'est pas de l'UTF-8, qui porte un
  caractère de contrôle autre que la tabulation et le retour à la ligne, ou un contrôle bidirectionnel
  (`BIDI_CONTROLS`, que kb n'écrit jamais). Refusé enfin, le Markdown qu'Obsidian ou un plugin
  exécuterait ou chargerait, que kb n'écrit jamais sans l'échapper : un accent grave (du code, une
  requête Dataview, `sheet_text_with_code`), `~~~` n'importe où dans une ligne
  (`sheet_text_with_tilde_fence`), `![` (une image distante, une note incluse, `sheet_text_with_embed`),
  un `<` qui n'ouvre pas un autolien `<http://…>` ou `<https://…>` (du HTML, une commande Templater,
  `sheet_text_with_html`), une référence de caractère, même dans un autolien (`&#x202E;`, `&rlm;` :
  Obsidian l'affiche décodée, un contrôle bidirectionnel, `sheet_text_with_character_reference`).
  Échappé, c'est-à-dire précédé d'un nombre impair de `\`, le caractère passe, hors d'un autolien, où
  une barre oblique n'échappe rien (CommonMark 0.31.2, § 6.5) : un `\` dans un autolien est refusé
  (`sheet_text_with_backslash_in_autolink`), kb n'en écrivant jamais.
  kb écrit des liens `[dépôt](url)` dans les tops et des `~` dans une URL ou une description : un lien
  ne s'ouvre qu'au clic, et une description de top qui contient `~~~` fait refuser sa fiche, un échec
  visible. Au-delà de 20 000 blobs, la liste s'arrête et la commande échoue.
- `veille/` ou un de ses dossiers en lien symbolique est refusé ; un temporaire laissé par une écriture
  interrompue (`veille/<dossier>/.<jour>.md.tmp`) fait échouer sa fiche, nommé par son chemin : le
  supprimer à la main.

Code de sortie : 0 ; 4 quand un blob est refusé, une fiche non écrite, la liste arrêtée à 20 000 blobs
ou le stockage en erreur pendant le téléchargement, une autre fiche de `watch` étant dans `veille/` ;
1 dans les mêmes cas quand aucune ne l'est, ou que le stockage n'est pas joint (sans `az login` :
`exchange_storage_no_token`) ; 2 quand un réglage manque ou est refusé (un coffre qui n'existe pas n'est
jamais créé) ; 130 : SIGINT, 143 : SIGTERM.

Limites, chacune avec sa parade :

- **Une fiche supprimée sur le Mac revient** au passage suivant tant que `watch` la porte, et `watch` la
  reçoit de nouveau de `job-data` à la publication suivante. Parade : la supprimer dans `job-data`, puis
  dans `watch`, puis sur le Mac. L'opératrice n'a que Reader sur `watch` : supprimer un blob demande
  Storage Blob Data Contributor ([Delete Blob](https://learn.microsoft.com/rest/api/storageservices/delete-blob),
  lu le 2026-11-10), un rôle temporaire qu'un Owner peut se donner (registre des traitements,
  « Procédure de tri », étape 9) ; pas fait par #424.
- **Une fiche est du Markdown qu'Obsidian affiche**, écrit par une identité de job. Le téléchargement
  refuse le Markdown actif (ci-dessus) ; restent hors de ce contrôle les plugins qui agissent sur un
  fichier neuf, comme Templater avec « Trigger Templater on new file creation », qui remplace alors
  chaque commande trouvée dans le fichier ([réglages de Templater](https://silentvoid13.github.io/Templater/settings.html),
  lus le 2026-11-10). Gestes à faire, faisables avec nos droits (les réglages du coffre) : vérifier que
  « Enable JavaScript Queries » et « Enable Inline JavaScript Queries » de Dataview sont désactivés,
  comme par défaut depuis la 0.4.13 (CVE-2021-42057), et que le déclencheur de Templater est inactif ou
  que `veille/` est dans ses « Excluded folders ».
- **`az` reçoit tout l'environnement** que `uv run --env-file` charge, secrets du `.env` compris
  (azure-identity le passe au processus d'`az`). Parade : un fichier d'environnement réduit pour cette
  cible, faisable avec nos droits (un fichier sur le Mac, sans droit Azure) ; pas fait.
- **Les limites de l'écriture du coffre** (`post/vault_files.py`) : un lien posé après le contrôle est
  suivi, et une fiche qu'un autre programme écrit entre le contrôle et le renommage est remplacée.
- **Le disque** : au pire, 20 000 blobs de 4 000 000 octets. Parade : une borne d'octets par passage, du
  code seul ; pas faite.

**Lire la base sans l'API** : la base s'ouvre en lecture seule avec `sqlite3`, sans clé ni
serveur :

```sh
sqlite3 -readonly ~/.knowledge_base/k-b.sqlite "SELECT kind, count(*) FROM item GROUP BY kind"
```

**Lancer les tests** :

```sh
uv run pytest
```

Cette commande écarte les tests marqués `e2e` et `postgresql` (`MARKERS_LEFT_OUT_BY_DEFAULT`,
`tests/conftest.py`) : ils ne tournent que si `-m` les nomme (ci-dessous). Les outils des tests sont le groupe
`dev` du `pyproject.toml`, que `uv sync` installe avec le projet, et que l'image laisse de côté (`--no-dev`,
`Dockerfile`) :

| Paquet | Rôle |
|---|---|
| `pytest` | lance les tests |
| `pytest-cov` | mesure la couverture (`--cov`) et fait échouer la commande sous le seuil |
| `pytest-html` | écrit le rapport HTML d'une exécution (`--html`, les cibles `make test`, `make test-ai-api`, `make test-data-api` et `make test-etl`) |
| `openapi-spec-validator` | valide l'OpenAPI de chaque API, dans `tests/data_api/test_openapi.py` et `tests/ai_api/test_ai_api_openapi.py` |
| `ruff` | le lint et le format (`uv run ruff check`, `uv run ruff format --check`) |
| `mypy` | le typage (`uv run mypy --strict`) |
| `types-defusedxml`, `types-pyyaml` | les annotations de types de `defusedxml` et de `pyyaml`, deux dépendances de K-B, pour mypy |

**Lancer les tests sur PostgreSQL** (marqués `postgresql`) : il leur faut un serveur PostgreSQL, que nomme
`KB_TEST_POSTGRESQL_URL`.

```sh
KB_TEST_POSTGRESQL_URL=postgresql://<rôle>@127.0.0.1:5432/postgres uv run pytest -m postgresql
```

L'URL vise une base d'un serveur de test : un PostgreSQL de la machine (sur le Mac, celui de Homebrew) ou le
service de la CI, jamais la base de production. Son rôle doit pouvoir créer et supprimer une base et, pour les
tests des droits de la base en ligne, des rôles (`identity_roles`, `tests/conftest.py`). Un test qui écrit
reçoit une base neuve, en UTF8 et en collation C, comme `kb create-db` la demande, supprimée après les tests de
son module (`make_postgresql_base`) ; les tests de lecture partagent une base, construite une fois. Un test de
lecture prend la fixture `engine` : sa moitié SQLite tourne dans `uv run pytest`, sa moitié PostgreSQL ici.
Sans la variable, un test marqué échoue ; il n'est jamais sauté. La CI les lance dans le job
`tests-postgresql`.

**Lancer les tests de bout en bout** (marqués `e2e`, `tests/e2e/`) : ils lancent `kb` sur les vraies sources,
un test par source, et l'envoi réel des mesures à Grafana Cloud (`test_real_export.py`). Ni la CI ni
`uv run pytest` ne les lancent. Les tests qui demandent une variable sont sautés sans elle, et `-rs` en donne la
raison : celui de Zotero sans `KB_ZOTERO_DIR`, celui des clips sans `KB_VAULT_DIR`, celui de `gh_archive` sans
`GOOGLE_APPLICATION_CREDENTIALS`, celui de l'envoi des mesures sans `KB_OTLP_ENDPOINT` ni `KB_OTLP_HEADERS`
(avec une seule des deux, il échoue). Depuis un terminal sans `.env` exporté :

```sh
uv run --env-file .env.e2e_test pytest -m e2e -rs --html=reports/e2e-report.html --self-contained-html
```

`.env.e2e_test` ne porte que leurs variables (modèle : `.env.e2e_test.example`). Si l'environnement tient une
autre variable de `.env.example`, ou la clé d'un client de l'API de données, ils s'arrêtent avant tout `kb`, en
citant leurs noms, jamais leurs valeurs (`tests/e2e/conftest.py`). `-k <source>` n'en lance qu'un, la source
nommée comme dans l'identifiant du test (`cisa_kev`, `tldr`, `arxiv_cscr_x_csai`…). Celui de `gh_archive`
lance une requête BigQuery réelle : à ne pas relancer à la légère. Ce qu'ils écrivent, et ce qu'il
en reste : le [registre des traitements](docs/registre-traitements.md), « Procédure de tri », étape 10.

**Lancer les tests avec leur rapport** (sans le `.env`, comme la CI) : chaque commande écrit le rapport HTML
de pytest-html dans `reports/`, ignoré par git, en `0600`, écrasé au lancement suivant.

```sh
make test           # comme uv run pytest, sans les tests e2e ni postgresql : reports/test.html
make test-ai-api    # tests/ai_api, puis les tests du code commun aux deux API
make test-data-api  # tests/data_api, puis les tests du code commun aux deux API
make test-etl       # tests/etl
```

Les rapports d'un groupe sont `reports/test-ai-api.html`, `reports/test-data-api.html` et
`reports/test-etl.html` ; ceux du code commun aux deux API, `reports/test-api-common.html`. Ces tests
communs (`core/`) sont à la racine de `tests/` : `test_api_methods.py`, `test_api_rate_limit.py` et
`test_api_telemetry.py`, listés dans `API_COMMON_TESTS` du `Makefile`. Un nouveau test commun s'y ajoute à
la main. `make` s'arrête au premier échec : si les tests de l'API échouent, les tests communs ne sont pas
lancés. Ce que prouvent les tests de l'API IA et de la chaîne des fiches, et ce qu'ils ne prouvent pas :
[docs/2026-11-08-tests-api-ia.md](docs/2026-11-08-tests-api-ia.md).

**Mesurer la couverture des tests** (lignes et branches de `src/k_b/`) :

```sh
make test-cov       # les fichiers sous 100 % dans la console, le tableau complet dans reports/coverage.md
uv run pytest --cov --cov-report=term-missing   # tous les fichiers dans la console, sans fichier
```

Sous 96 % (lignes et branches), les deux commandes échouent : c'est le `fail_under` de
`[tool.coverage.report]` dans `pyproject.toml`, un plancher contre la régression et non une cible
(journal ADR, 2026-11-08). La CI le vérifie dans le job `tests`. Seules les commandes avec `--cov` le
vérifient (`make test` et `uv run pytest`, non) ; sur une partie de la suite, ajouter `--cov-fail-under=0`.

**La CI** (GitHub Actions, `.github/workflows/`) : cinq workflows. `ci.yml` et `image.yml` tournent sur chaque
PR vers `main` et sur chaque push sur `main`, donc après chaque fusion, et `infra.yml` de même, sans filtre de
chemin depuis #496 ; `deploy.yml`, sur un tag `vX.Y.Z` poussé, ou à la main
(`gh workflow run deploy.yml --ref <tag>`) ; `docs.yml` (#167), sur chaque PR vers `main`, ou à la main, et il ne
publie le site des fiches de `documentation/` sur GitHub Pages que lancé depuis `main`
([documentation/accessibilite_pour_docu.md](documentation/accessibilite_pour_docu.md), « Publier »). Le jeton de
chaque workflow ne lit que le dépôt (`permissions: contents: read`), sauf ce que les jobs de `deploy.yml` et le job
`deploy` de `docs.yml` ajoutent. Chaque action est épinglée par son SHA, sa version en commentaire.

| Job | Workflow | Ce qu'il fait |
|---|---|---|
| `audit` | `ci.yml` | cherche les vulnérabilités connues des versions de `uv.lock`, de tous les groupes de dépendances (`docs` compris), avec leurs empreintes (`uv export --all-groups`, puis pip-audit 2.10.1) |
| `tests` | `ci.yml` | `uv run pytest --cov --cov-report=term-missing:skip-covered` : la suite, sans `e2e` ni `postgresql`, et le seuil de couverture |
| `lint` | `ci.yml` | `uv run ruff check` et `uv run ruff format --check` |
| `types` | `ci.yml` | `uv run mypy --strict` |
| `tests-postgresql` | `ci.yml` | `uv run pytest -m postgresql`, sur un service `postgres:18.6` épinglé par son digest |
| `tests-data` | `ci.yml` | les tests des données, à part des autres : avant la base, `tests/etl`, `tests/test_schema.py` et `tests/test_items.py` (l'item commun où chaque source est lue avant l'import) ; avant le modèle, `tests/ai_api/test_watch_items.py` (les items tels que l'API IA les envoie) ; sans le test `postgresql` de `tests/etl`, que lance `tests-postgresql`, et sans `--cov`, car `tests` les lance aussi et garde le seuil |
| `image-build` | `image.yml` | construit l'image `linux/amd64`, puis vérifie ce que la construction reçoit, l'utilisateur non root, l'absence dans l'image des fichiers que `.dockerignore` écarte (`.git`, et des `.env*` et `*.sqlite*` plantés pour l'essai), le refus de démarrer sans `KB_DATA_DIR`, puis `kb --help` et `kb create-db` ; l'image n'est poussée nulle part |
| `bicep-build` | `infra.yml` | compile `infra/main.bicep` par Bicep v0.48.1, vérifié par son SHA256, sans aucun droit sur Azure |
| `build` | `docs.yml` | construit le site des fiches de `documentation/` par MkDocs, en mode strict (un lien ou une ancre absents le font échouer), et vérifie l'empreinte du fichier de Mermaid téléchargé ; lancé à la main depuis `main`, dépose le site en artefact de Pages |
| `deploy` | `docs.yml` | lancé à la main depuis `main` seulement, publie le site sur GitHub Pages ; sauté sur une PR |
| `check` | `deploy.yml` | refuse un tag hors de la forme `vX.Y.Z`, dont le commit n'est pas sur `main`, ou dont la CI n'est pas finie et verte |
| `deploy` | `deploy.yml` | met le tag en ligne : [infra/README.md](infra/README.md), « Déployer une version » |

Les jobs de `ci.yml` et le job `build` de `docs.yml` installent uv par `astral-sh/setup-uv`, à la version fixée
dans chacun des sept (`version: "0.13.6"`) : la même que le `Dockerfile`, dans la plage `uv_build` de `build-system.requires` du
`pyproject.toml`. Sur le Mac, la même version s'installe par `uv self update 0.13.6`.

**Dependabot** (`.github/dependabot.yml`) ouvre chaque semaine les PR de mise à jour des actions des workflows
(leur SHA et leur commentaire de version) et des images de base du `Dockerfile` (leur digest et leur tag). Une
version nouvelle attend 7 jours avant sa PR, sauf une mise à jour de sécurité ; ghcr.io ne donne pas la date
d'une version, et l'attente ne s'applique pas à `astral-sh/uv` : sa date se vérifie à la main avant la fusion.
Pour `python` et `astral-sh/uv`, il ne propose que les correctifs et les digests, jamais une version mineure ou
majeure. Sa PR d'`astral-sh/uv` ne change que le `Dockerfile` : la `version:` des six jobs de `ci.yml` et celle de
`docs.yml` se changent à la main, dans la même PR. Ses mises à jour de version ne touchent ni l'image `postgres` du job `tests-postgresql`, à changer à
la main, ni `uv.lock`. Les alertes et les mises à jour de sécurité de Dependabot sont activées dans les
réglages du dépôt, et le graphe des dépendances y voit les paquets Python (96 le 2026-11-08) : seule une mise
à jour de sécurité peut ouvrir une PR sur `uv.lock`. Aucune PR de sécurité n'a encore été ouverte.

**La protection de `main`** est le ruleset « Basic-rules-main-protect », actif, sans contournement pour
personne, administratrice comprise. Il se lit par `gh api repos/SabineLaurent/K-B/rulesets/25257125` :
- `main` ne se supprime pas et ne reçoit pas de push forcé ;
- tout changement passe par une PR, fusionnée par un commit de fusion (la seule méthode permise), sans
  approbation requise ;
- 6 checks requis, rendus par GitHub Actions : `audit`, `tests`, `lint`, `types`, `tests-postgresql` et, depuis
  #496, `bicep-build` ;
  `strict` : la branche doit être à jour avec `main` avant la fusion, et la CI repasse après sa mise à jour.

`image-build`, `tests-data` et `build` de `docs.yml` ne sont pas requis à la fusion. `bicep-build` l'est depuis #496 : il tourne sur toute
PR, car un check qu'un filtre de chemin saute reste en attente et bloque la fusion (commentaire de `infra.yml`). Les
non requis comptent au déploiement : `check` exige
que chaque workflow du dépôt lancé sur le commit du tag ait fini en succès, sauf Deploy et les exécutions que
GitHub crée lui-même (Dependabot). `docs.yml` ne tourne sur un commit de `main` que lancé à la main : une telle
exécution en échec fait refuser le tag de ce commit, jusqu'à une relance réussie
([documentation/integration_continue_pour_docu.md](documentation/integration_continue_pour_docu.md), « Après la
CI »). Sur un dépôt neuf, ce ruleset se recrée dans
Settings → Rules → Rulesets, avec ces règles. Les rulesets des tags, l'environnement `production` et les secrets
du déploiement se posent par [infra/README.md](infra/README.md), « Les réglages de GitHub, une fois, avant la
passe 2 » et « Les secrets du dépôt, après la passe 2 ».

**Ce que la CI lit comme réglages** (les noms, jamais les valeurs) :
- `deploy.yml` lit cinq secrets du dépôt : `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` et `AZURE_SUBSCRIPTION_ID`
  (la connexion à Azure par OIDC), `KB_RESOURCE_GROUP` et `KB_REGISTRY`. Son job `deploy` tourne dans
  l'environnement `production` ; `check` lit les exécutions de la CI par le jeton du workflow (`github.token`).
- `tests-postgresql` pose `KB_TEST_POSTGRESQL_URL` dans le job, vers son service, sans mot de passe
  (`POSTGRES_HOST_AUTH_METHOD: trust` : un serveur que seul le runner joint).
- Aucun workflow ne lit de variable du dépôt (`vars.`), et les quatre autres ne lisent aucun secret.

**Une PR témoin** : [#533](https://github.com/SabineLaurent/K-B/pull/533) a passé, avant sa fusion le
2026-11-09, les 7 checks que recevait alors une PR qui ne touchait ni `infra/` ni `.github/workflows/infra.yml` : les six de CI, `audit`, `tests`,
`lint`, `types`, `tests-postgresql` et `tests-data` (exécution 42617081839), et `image-build` (exécution 42617082007 d'Image), tous verts
(`gh pr checks 533 --repo SabineLaurent/K-B`) ; `bicep-build` n'y a pas tourné. Depuis #496, toute PR reçoit aussi
`bicep-build`, un huitième check, et depuis #167, `build` de `docs.yml`, un neuvième.

**Construire l'image** (Docker ; une image pour toutes les commandes `kb`, voir le `Dockerfile`) :

```sh
docker buildx build --platform linux/amd64 --tag k-b .
docker run --rm k-b --help
docker volume create k-b-data
docker run --rm -v k-b-data:/var/lib/knowledge_base -e KB_DATA_DIR=/var/lib/knowledge_base k-b create-db
```

Azure Container Apps ne lance que des images `linux/amd64` : sur un Mac à puce Apple, Docker Desktop les
construit et les lance par émulation. L'image lance `kb` sous l'utilisateur `10001:10001`, jamais root. Son
dossier de données, où se monte le volume, est `/var/lib/knowledge_base`, et il appartient à cet utilisateur.
`KB_DATA_DIR` n'a pas de valeur dans l'image : elle se donne au lancement, avec le volume, et sans elle `kb`
refuse de démarrer. Le journal est la sortie d'erreur (`KB_LOG_TO_FILE=false`). Chaque variable se change au
lancement (`-e`). `.dockerignore` refuse tout par défaut : la construction ne reçoit que `pyproject.toml`,
`uv.lock`, `README.md` et `src/`, sans les fichiers d'environnement, les bases `*.sqlite` (et leurs fichiers
annexes) ni les caches de `src/`. Le job `image-build` de la CI (`.github/workflows/image.yml`) construit
l'image sur chaque PR vers `main` et sur chaque push sur `main`, et la contrôle, sans la pousser nulle part.

## Licence

© 2026 Sabine Laurent — sous licence [Creative Commons Attribution - Pas d'Utilisation Commerciale 4.0 International (CC BY-NC 4.0)](https://creativecommons.org/licenses/by-nc/4.0/deed.fr).

- **Réutilisation autorisée**, à condition de citer l'origine : [github.com/SabineLaurent/K-B](https://github.com/SabineLaurent/K-B).
- **Toute utilisation commerciale est interdite** sans mon accord écrit préalable.

Texte complet : voir [LICENSE](LICENSE).

## Contenus de tiers

La licence ci-dessus couvre ce que j'ai écrit. Quelques fichiers de test reprennent des extraits d'autrui, sous
leur propre licence (lues à la source le 2026-11-06) :

| Fichier | Source | Licence |
|---|---|---|
| `tests/fixtures/clipping/page_with_a_rule_in_its_text.md` | [WCAG 2.2](https://www.w3.org/TR/WCAG22/), Copyright © 2020-2024 World Wide Web Consortium | [W3C Document License](https://www.w3.org/copyright/document-license/) |
| `tests/fixtures/clipping/page_without_author_or_date.md` | une page du site de l'[OWASP](https://owasp.org/) | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/deed.fr) |
| `tests/fixtures/github_advisories_extract.json` | [GitHub Advisory Database](https://github.com/github/advisory-database) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.fr) |
| `tests/fixtures/arxiv_extract.xml` | métadonnées de l'API arXiv ([conditions](https://info.arxiv.org/help/api/tou.html)) | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/deed.fr) |
| `tests/fixtures/cisa_kev_extract.csv` | catalogue KEV de la CISA ([`cisagov/kev-data`](https://github.com/cisagov/kev-data)) | CC0 1.0 |
| `tests/fixtures/digests_reference.json` | les réponses d'un modèle réel à `POST /digests` (#479) sur les items des deux fichiers ci-dessus, dont elles citent des passages | passages cités : CC0 1.0 ; texte du modèle et métadonnées du fournisseur : licence non établie |
| `tests/fixtures/zotero_extract.sql` | 15 tables du schéma de Zotero (`resource/schema/userdata.sql` du dépôt [`zotero/zotero`](https://github.com/zotero/zotero)), © 2009 Center for History and New Media, George Mason University ; les valeurs sont inventées | [AGPL v3 ou plus](https://www.gnu.org/licenses/agpl-3.0.html) |
| `tests/fixtures/github_*_extract.json`, `tests/fixtures/gh_archive_extract.json` | métadonnées publiques de dépôts GitHub (noms, descriptions, notes de version), par l'API de GitHub et GH Archive | celle de chaque dépôt ; de courts extraits, gardés pour les tests |

## Crédits

Les papiers viennent de l'API arXiv, qui demande cette mention à chacun de ses utilisateurs
([arXiv API Access](https://info.arxiv.org/help/api/index.html), consulté le 2026-10-25) :

> Thank you to arXiv for use of its open access interoperability.

L'API de données la donne aussi, dans la description de son OpenAPI (`docs/api/openapi-donnees.json`, et `/docs` en `sandbox`).
