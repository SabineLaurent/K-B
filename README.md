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

### Étape 2 — le wiki

L'étape 2 ouvre la porte « base de connaissance », d'abord pour mes clips du Web Clipper, puis
pour les papiers que je garde dans Zotero :

- **Ingest** : de chaque document, le modèle écrit une note de lecture, comme après une lecture
  du texte entier : le clip tel quel, puis le texte intégral du PDF d'un papier. Il met aussi à
  jour les fiches thématiques que le document touche : une fiche par sujet, qui rassemble ce
  qu'en disent les documents, chaque affirmation renvoyant au sien. Les sujets viennent d'une
  liste que je tiens ; un sujet nouveau proposé par le modèle attend mon accord.
- **Contrôles** : le modèle renvoie des opérations JSON ; le code les valide (liste fermée
  d'opérations, sujets connus, citations, nombres et dates retrouvés mot pour mot dans la source,
  liens et frontmatter), puis écrit dans le wiki si tout passe. Sinon, la proposition attend dans
  une file « à voir ».
- **API IA authentifiée**, distincte de l'API de données et documentée en OpenAPI. La commande
  `kb` en est le client. L'inférence passe par Azure, en API compatible OpenAI : le modèle se
  choisit en configuration.
- **Métriques** de chaque appel (durée, jetons, coût, erreurs, fidélité, propositions
  acceptées), émises en OpenTelemetry, gardées sur ma machine et restituées en temps réel, avec
  une alerte sur seuil, par un outil à choisir.

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
  (`src/k_b/database/schema.sql`, module `sqlite3`, sans ORM).
- **Base** : SQLite aux deux premiers temps, le Mac puis des conteneurs en local (voir « Le POC
  du 25/10 et la suite ») ; au troisième (Azure Container Apps, 08/11), SQLite et Blob ou
  PostgreSQL, non tranché (journal ADR, « Décisions encore ouvertes », « La base au
  temps 3 »). D'ici là, aucun SQL propre à SQLite n'est ajouté (règle 1 de `.claude/rules/poc.md`).
- **Données hors du dépôt**, dans le dossier `KB_DATA_DIR` (`~/.knowledge_base` sur ma machine,
  journal ADR du 2026-10-09). Au deuxième temps, en conteneurs, la base ira dans un volume nommé et
  le brut dans un dossier partagé avec les conteneurs (journal ADR, 2026-10-15, « POC du 25/10 »,
  décision 2 ; #200).
- **Réglages par variables d'environnement** : hôtes, ports, chemins et secrets ; un secret n'a
  pas de valeur par défaut (règle 2 de `.claude/rules/poc.md`).
- **Données personnelles** : le modèle traite en zone de données UE ; ce que K-B garde, et
  combien de temps, est tenu par le [registre des traitements](docs/registre-traitements.md).
- **Contrôles** : chaque PR vers `main`, branche protégée, passe les quatre jobs de la CI
  (`audit`, `tests`, `lint`, `types`) avant d'être fusionnée.

### Budget

| Poste | Coût |
|---|---|
| API GitHub | un jeton en lecture seule, sans frais ([docs/jeton-github.md](docs/jeton-github.md)) |
| BigQuery (GH Archive) | bac à sable sans compte de facturation : au-delà du quota gratuit (1 Tio lu par mois), une requête est refusée, jamais facturée ([docs/bigquery.md](docs/bigquery.md)) |
| Modèle des fiches | gpt-6-luna sur Azure AI Foundry, sur l'abonnement Azure de mon organisme de formation, fourni pour ce projet : région France Central, zone de données UE, 140 000 jetons par minute (journal ADR, 2026-10-17). Je n'en vois pas la facturation. Ordre de grandeur : au pire environ 420 000 jetons par demande de fiches, à 0,12 $ en entrée et 0,60 $ en sortie par million de jetons, prix UE, soit quelques centimes (journal ADR, 2026-10-16) ; les appels d'une demande sont détaillés dans [docs/fiches-veille.md](docs/fiches-veille.md), « Lecture plafonnée » |
| Mise en ligne du 08/11 : coûts communs aux deux options (France Central, prix publics en dollars relevés le 2026-10-25, mois de 730 h) | **8,96 $ par mois** sans l'offre gratuite d'Azure Container Apps, **5,26 $** avec elle ; **29,32 $**, ou environ **27,70 $**, si les deux API gardent une réplique. Le détail : le job de collecte et d'import, une exécution par jour de 15 min à 0,5 vCPU et 1 Gio (hypothèse, non mesurée), 0,41 $ au tarif actif (0,000024 $ par vCPU-seconde, 0,000003 $ par Gio-seconde) ; `kb serve-data` et `kb serve-ai`, 0,5 vCPU et 1 Gio chacune, à zéro réplique au repos et actives 1 h par jour (hypothèse), 3,29 $, ou 23,65 $ avec une réplique gardée, au tarif de repos (0,000003 $ par vCPU-seconde et par Gio-seconde) ; le brut dans Blob Storage (Hot LRS, 0,0192 $ par Go et par mois), 10 Go supposés, non mesurés, 0,19 $ ; le registre d'images Azure Container Registry Basic (0,1666 $ par jour, 10 Go compris), 5,07 $, ou 0 $ avec le registre de GitHub (GHCR), gratuit pour un paquet public, le choix n'étant pas fait ; les journaux dans Log Analytics, 0 $ sous 5 Go par mois, puis 2,76 $ par Go. L'offre gratuite (180 000 vCPU-secondes, 360 000 Gio-secondes et 2 millions de requêtes par abonnement et par mois) couvre le job et les deux API à zéro réplique (123 188 vCPU-secondes, 246 375 Gio-secondes) ; elle vaut par abonnement, et celui de la mise en ligne n'est pas connu. |
| Mise en ligne, option SQLite et Blob | **0,02 $ par mois** de plus : la base, un fichier produit par le job puis rangé dans Blob Storage, et lu par `kb serve-data` au démarrage (hypothèse : la façon de la lire n'est pas décidée), 1 Go supposé, au prix du brut |
| Mise en ligne, option PostgreSQL | **18,13 $ par mois** de plus : Azure Database for PostgreSQL, serveur flexible Burstable B1ms (1 vCore, 2 Gio), 0,019 $ de l'heure, 13,87 $, et 32 Gio de stockage, le minimum, à 0,133 $ par Go et par mois, 4,26 $ ; une sauvegarde au-delà du stockage compris est comptée 0,10 $ par Go et par mois, non chiffrée. Microsoft déconseille le niveau Burstable pour la production. |
| Temps | chaque issue porte son estimation en heures ; les jalons les regroupent |

Ces coûts ne tranchent pas « La base au temps 3 » (journal ADR, « Décisions encore ouvertes ») : ils en donnent le prix.

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
[page des jalons](https://github.com/SabineLaurent/K-B/milestones). Les jalons à venir, relevés
le 18/10/2026 :

| Jalon | Échéance |
|---|---|
| POC 25/10 | 25/10/2026 |
| Comptes rendus de veille tous les 3 jours | 01/11/2026 |
| Mise en ligne 08/11 | 08/11/2026 |
| Wiki : ingest des clips | sans date, après le 29/10 |

### Le POC du 25/10 et la suite

**Le 25/10** (journal ADR, 2026-10-20, « Squelette E1 E3 : cadrage du 20/10 », décision 1) : K-B
tourne sur ma machine, sans conteneur ; c'est le premier de trois temps. La collecte, l'import,
l'API de données et l'API IA s'y lancent par `kb`. L'API IA rédige des comptes rendus de veille par sujet,
sur une fenêtre réglable (`KB_DIGEST_WINDOW_DAYS`, 3 jours par défaut), avec gpt-6-luna ; le modèle
ne choisit le sujet que dans une liste fermée que je tiens. Le retour se lit dans la console, et les
fiches en `.md` dans mon coffre : ni interface CLI dédiée ni front. La collecte et l'import sont
lancés à la main, et conçus comme des jobs. Au deuxième temps, avant le 29/10 si le temps le permet,
des conteneurs en local répètent le déploiement : Zotero et les clips y restent collectés sur ma
machine (`KB_COLLECT_ONLY`), sans que ma bibliothèque soit montée dans un conteneur.

**Où on en est** : la collecte, l'import, l'API de données, le service des fiches par l'API IA
(`kb serve-ai`, #156) et leur écriture en `.md` dans le coffre (`kb digest`, #209) sont codés (voir
« Installer et lancer »). Restent les métriques du modèle vers Grafana Cloud (#162, #164) ; puis, au deuxième
temps, l'image et les conteneurs (#200) et l'installation par compose (#202).

**La suite** :

- au 08/11, mise en ligne sur Azure Container Apps : brut dans Azure Blob Storage, collecte en
  job déclenché par cron ; la base, SQLite et Blob ou PostgreSQL, reste à trancher ;
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
| `KB_ZOTERO_DIR` | non | dossier de données de Zotero, celui qui contient `zotero.sqlite`, en chemin complet (un `~` écrit dans `.env` n'est pas développé). Sans elle, `kb collect` saute Zotero et l'affiche (`zotero: skipped (KB_ZOTERO_DIR not set)`). Avec elle, les papiers et leurs surlignages sont extraits dans `<KB_DATA_DIR>/raw/selected_library/zotero/`, sans que K-B ouvre la base de Zotero : il en lit une copie temporaire. |
| `KB_VAULT_DIR` | non | dossier du coffre Obsidian de K-B, celui qui contient `Clippings/`, en chemin complet (un `~` écrit dans `.env` n'est pas développé). Sans elle, `kb collect` saute les clips et l'affiche (`clipping: skipped (KB_VAULT_DIR not set)`). Avec elle, chaque clip nouveau ou changé est copié tel quel dans `<KB_DATA_DIR>/raw/selected_library/clipping/` ; K-B ne modifie jamais les clips. `kb write-tops` écrit les fiches des tops dans `veille/tops/` du coffre, `kb digest` les comptes rendus de veille dans `veille/<sujet>/` ; ni l'un ni l'autre ne tourne sans elle (code 2). |
| `GOOGLE_APPLICATION_CREDENTIALS` | non | chemin complet de la clé JSON du compte de service BigQuery, rangée hors du dépôt ([docs/bigquery.md](docs/bigquery.md)). Elle est lue par le client BigQuery ; K-B ne l'ouvre pas. Sans elle, `kb collect` saute GH Archive et l'affiche (`gh_archive: skipped (GOOGLE_APPLICATION_CREDENTIALS not set)`). Avec elle, les dépôts qui montent sur 3 jours sont extraits dans `<KB_DATA_DIR>/raw/automated_watch/gh_archive/`. |
| `KB_COLLECT_ONLY` | non | les dossiers des sources que `kb collect` lance, séparés par des virgules (`zotero,clipping`) ; la casse ne compte pas. Sans elle, pas de filtre : chaque source tourne comme avant (Zotero, clips et GH Archive selon leur variable). Une source écartée affiche `<dossier>: skipped (not in KB_COLLECT_ONLY)` ; un nom qui n'est pas un dossier de source, une valeur ou une entrée vide, ou une source choisie sans sa variable (`zotero` sans `KB_ZOTERO_DIR`) : code 2, rien n'est collecté ([docs/specs-collecte.md](docs/specs-collecte.md), « Choisir les sources »). |
| `KB_GITHUB_TOKEN` | non | jeton GitHub en lecture seule ([docs/jeton-github.md](docs/jeton-github.md)). Sans lui, l'API GitHub accepte 60 requêtes par heure au lieu de 5 000. |
| `KB_DATA_API_KEY_<CLIENT>` | pour `kb serve-data` | la clé d'un client de l'API de données (`<CLIENT>` en `A-Z`, `0-9` et `_`, par exemple `KB_DATA_API_KEY_TERMINAL`), une variable par client ([docs/specs-api.md](docs/specs-api.md)). |
| `KB_AI_API_KEY_<CLIENT>` | pour `kb serve-ai` et `kb digest` | la clé d'un client de l'API IA, une variable par client, mêmes règles que `KB_DATA_API_KEY_<CLIENT>` ; `kb digest` est le client `KB_DIGEST` et lit la même variable, `KB_AI_API_KEY_KB_DIGEST`. Les autres réglages de `kb serve-ai` (modèle, API de données, hôte, port, fenêtre) sont décrits dans `.env.example`. |
| `KB_AI_API_URL` | non | l'adresse de l'API IA pour `kb digest`, `http` ou `https`, sans utilisateur, requête ni fragment. Sans elle, `http://127.0.0.1:8001` (`core/config.py`) ; elle ne suit pas `KB_AI_API_PORT` : la changer aussi quand le port change. |

**Créer la base** (une fois) :

```sh
mkdir -p ~/.knowledge_base
KB_DATA_DIR=~/.knowledge_base uv run kb create-db
```

`kb create-db` crée `<KB_DATA_DIR>/k-b.sqlite` : les tables, les 7 sources, le mode WAL. Code de
sortie :

- 0 : la base est créée ;
- 1 : la création a échoué (dossier en lecture seule, disque plein…). Le message dit l'erreur, et
  aucun fichier de base ne reste ;
- 2 : `KB_DATA_DIR` manque ou n'est pas un dossier existant, ou la base existe déjà. Une base
  existante n'est pas touchée : pour repartir de zéro, supprimer le fichier.

**Lancer une collecte** (une par jour, voir [docs/specs-collecte.md](docs/specs-collecte.md)) :

```sh
KB_DATA_DIR=~/.knowledge_base uv run kb collect
```

Avec le jeton rangé dans le `.env` à la racine du dépôt, ignoré par git :
`KB_DATA_DIR=~/.knowledge_base uv run --env-file .env kb collect`.

`kb collect` affiche une ligne par source (`ok` ou `failed`, avec le type de l'erreur ; `skipped`
pour Zotero sans `KB_ZOTERO_DIR`, les clips sans `KB_VAULT_DIR`, GH Archive sans
`GOOGLE_APPLICATION_CREDENTIALS`, une source que `KB_COLLECT_ONLY` écarte). Code de sortie : 0 si
tout a réussi ; 4 si au moins une source a réussi et au moins une a échoué, l'état de collecte
écrit ; 1 si aucune source lancée n'a réussi ou si l'état de collecte n'a pas pu être écrit ; 2 si
`KB_DATA_DIR` manque, n'est pas un dossier existant, si l'état de collecte est illisible, ou si
`KB_COLLECT_ONLY` est refusée ; 143 si `kb collect` reçoit SIGTERM (`docker stop`) : ce qui a été
fait avant le signal est gardé ; reçu avant l'écriture de l'état de collecte, il laisse l'état
inchangé, et la collecte suivante repart des mêmes dates.

**Importer le brut dans la base** (après une collecte) :

```sh
KB_DATA_DIR=~/.knowledge_base uv run kb import
```

`kb import` lit les fichiers de `<KB_DATA_DIR>/raw/automated_watch/` et de
`<KB_DATA_DIR>/raw/selected_library/` (les extraits Zotero) pas encore importés et
écrit leurs items dans la base, qui écarte les doublons, et les lignes des classements GH Archive
dans sa table `trend` ; sans nouveau brut, il ne lit rien,
sauf un fichier illisible, relu et rejeté à chaque import. Il affiche le nombre de fichiers bruts lus, d'items écrits (nouveaux ou mis à jour), de lignes de tendance écrites, d'items et de fenêtres de
classement écartés (doublons, ou versions qui ne sont pas plus récentes que celle de la base), de lignes retirées
(CISA, entrées et surlignages Zotero) et de rejets, détaillés dans
`<KB_DATA_DIR>/import-log-<AAAA-MM-JJTHHMMSSZ>.jsonl`, un journal par import. Pour reconstruire
la base depuis tout le brut : supprimer `k-b.sqlite`, puis `kb create-db` et `kb import`. Code de
sortie :

- 0 : l'import a réussi ;
- 1 : l'import a échoué. Il n'écrit rien, ni dans la base ni au journal : le journal est écrit
  avant la validation de la base ;
- 2 : `KB_DATA_DIR` manque, la base n'existe pas (`kb create-db`), ou le journal de cette
  seconde existe déjà (relancer `kb import`) ;
- 143 : `kb import` a reçu SIGTERM (`docker stop`). Reçu avant la validation de la base, il
  n'écrit rien, comme pour 1, ni dans la base ni au journal ; reçu pendant ou après, l'import est
  gardé, avec son journal.

**Écrire les fiches des tops dans le coffre** (après un import) :

```sh
KB_DATA_DIR=~/.knowledge_base KB_VAULT_DIR=<coffre> uv run kb write-tops
```

`kb write-tops` écrit, pour le top 100 des dépôts les plus étoilés et celui des plus forkés, une
fiche Markdown par jour de collecte encore présent dans le brut :
`<KB_VAULT_DIR>/veille/tops/most_starred/AAAA-MM-JJ.md` et `.../most_forked/AAAA-MM-JJ.md`,
nommée par le jour UTC du relevé. Une fiche qui existe n'est jamais réécrite (sauf deux lancements
qui se chevauchent : #295) : deux collectes le
même jour ne donnent qu'une fiche, celle du premier relevé de ce jour encore dans le brut. Une fois
les fiches d'un top écrites, ses relevés lisibles plus anciens que le dernier relevé lisible sont
supprimés du brut ; au premier lancement, tout l'historique des relevés devient des fiches, puis
ces relevés sont supprimés. Il affiche une ligne par top (fiches écrites, relevés sautés parce que la fiche de leur jour
existe, relevés supprimés, relevés illisibles gardés). Code de sortie :

- 0 : chaque top a réussi, ou n'a aucun relevé ;
- 4 : un top a échoué, et un autre a abouti. L'unité est le top : il échoue quand une erreur de
  lecture, d'écriture ou de suppression (`OSError`) ou une entrée refusée du coffre (lien
  symbolique) l'arrête, ou quand il garde un relevé illisible (gardé, jamais supprimé, tant qu'il
  est là) ; il aboutit quand il va au bout et écrit une fiche, ou va au bout sans échec (un top
  sans relevé compris). Un top qui écrit ses fiches et garde un relevé illisible a donc échoué et
  abouti : seul, il sort en 4, jamais en 0 (échouer fermé). Aucun relevé n'est supprimé avant que
  les fiches de son top soient écrites ; une suppression qui échoue laisse celles déjà faites. Un
  top arrêté n'a pas de ligne : son erreur est au journal. L'autre top est traité quand même ;
- 1 : un top a échoué et aucun n'a abouti (les deux arrêtés, ou rien que des relevés illisibles) ;
- 2 : `KB_DATA_DIR` manque, ou `KB_VAULT_DIR` manque ou n'est pas un dossier existant : rien n'est
  lu dans le brut, rien n'est écrit dans le coffre ni supprimé, aucun dossier du coffre n'est créé ;
  l'erreur va au journal ;
- 143 : `kb write-tops` a reçu SIGTERM (`docker stop`) : les fiches déjà écrites sont gardées,
  aucun relevé n'est supprimé avant que ses fiches soient écrites.

**Toute la chaîne en dev**, comme en ligne, où une automatisation enchaînera les étapes :

```sh
export KB_DATA_DIR=~/.knowledge_base KB_VAULT_DIR=<coffre>
uv run --env-file .env kb collect; uv run --env-file .env kb import; uv run --env-file .env kb write-tops
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

La documentation de l'API est servie sur `http://127.0.0.1:8000/docs`, sans clé ; son OpenAPI est
versionnée dans `docs/api/openapi-donnees.json`, réécrite par `uv run kb openapi` lancé à la
racine du dépôt (ailleurs, sans dossier `docs/api`, il n'écrit rien et sort en code 2). `kb serve-data` journalise une ligne par requête dans
`<KB_DATA_DIR>/logs/kb-serve-data.log`, avec le nom du client, jamais sa clé. Code de sortie 2, sans
lancer l'API, si `KB_DATA_DIR` manque, si aucune clé n'est donnée, si un nom de client est vide ou
hors `A-Z`, `0-9` et `_`, si une clé a moins de 32 caractères ou un caractère hors `A-Z`, `a-z`,
`0-9`, `_` et `-` (l'alphabet de `token_urlsafe`), ou si deux clients ont la même clé :
le message nomme la variable, jamais sa valeur. Code 2 aussi si l'hôte n'est pas une adresse IPv4,
si le port n'est pas un entier de 1 à 65535, si la liste des hôtes permis est vide ou contient une
entrée vide, une entrée avec `*` ou une entrée hors nom en minuscules, ou si `KB_LOG_TO_FILE` n'est
ni `true` ni `false` (`false` : journal sur la sortie d'erreur seule) ; le message nomme la
variable et cite la valeur refusée. Si le port est déjà pris (par exemple par un autre
`kb serve-data`), uvicorn écrit `address already in use` au journal et `kb serve-data` sort en code 3.

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
   (`KB_AI_API_KEY_KB_DIGEST=<la clé>`), la clé que l'API IA envoie à l'API de données
   (`KB_DATA_API_KEY_AI_DIGEST=<une autre clé>`, que `kb serve-data` lit aussi : redémarrer `kb serve-data`), et
   le modèle (`KB_LLM_PROVIDER` et ses variables, `.env.example`). `replay` répond par les
   réponses d'un fichier, sans réseau ni clé ni coût.
2. Lancer l'API IA, à côté de `kb serve-data` ; elle écoute par défaut sur `http://127.0.0.1:8001`, et
   seulement sur la machine (`KB_AI_API_HOST` et `KB_AI_API_PORT` changent l'hôte et le port ;
   `KB_DIGEST_WINDOW_DAYS`, de 1 à 14, la fenêtre par défaut, 3 jours) :

   ```sh
   KB_DATA_DIR=~/.knowledge_base uv run --env-file .env kb serve-ai
   ```

3. Demander les fiches d'une fenêtre (`window_days` facultatif, de 1 à 14) :

   ```sh
   curl -X POST -H "Authorization: Bearer <la clé>" -H "Content-Type: application/json" \
     -d '{"window_days": 3}' http://127.0.0.1:8001/digests
   ```

La documentation de l'API IA est servie sur `http://127.0.0.1:8001/docs`, sans clé ; son OpenAPI
est versionnée dans `docs/api/openapi-ia.json`, réécrite par `uv run kb openapi` avec celle de
l'API de données. `kb serve-ai` journalise une ligne par requête dans
`<KB_DATA_DIR>/logs/kb-serve-ai.log` (ni `kb.log` ni `kb-serve-data.log` : un seul `kb serve-ai` par
`KB_DATA_DIR`), avec le nom du client et l'identifiant de la requête, rendu aussi dans l'en-tête
`X-Request-ID` de chaque réponse ; chaque appel au modèle écrit une ligne JSON de métrique sur la
sortie standard, sans texte. Code de sortie 2, sans lancer l'API, si `KB_DATA_DIR` manque, si une
clé, l'hôte, le port, la fenêtre, le modèle ou la clé `KB_DATA_API_KEY_AI_DIGEST` est refusé : le
message nomme la variable, jamais une clé ni l'URL du modèle. Port déjà pris : code 3, comme
`kb serve-data`.

**Changer une clé** (la clé reste fixe, sans date d'expiration : journal ADR, 2026-10-20,
« Squelette E1 E3 », décision 3) :

- clé d'un client de l'API IA : faire une nouvelle clé, la ranger dans sa variable
  (`KB_AI_API_KEY_KB_DIGEST`), puis redémarrer `kb serve-ai` ; l'ancienne clé est refusée dès le
  redémarrage, pas avant. Retirer un client : retirer sa variable et redémarrer ;
- clé `KB_DATA_API_KEY_AI_DIGEST` : la changer dans le `.env`, puis redémarrer `kb serve-data` et
  `kb serve-ai`, qui la lisent tous deux ; tant que l'un des deux garde l'ancienne, chaque demande
  de fiches rend 502 `data_api_unauthorized` ;
- sur un 401 de l'API IA (`invalid_api_key`, clé absente, changée d'un seul côté ou retirée),
  `kb digest` n'écrit aucune fiche, ne cite jamais la clé, nomme la variable
  `KB_AI_API_KEY_KB_DIGEST` et sort en code 1 : la requête est partie (une clé absente de
  `kb digest` donne 2, rien n'est demandé).

Limites : une variable `KB_AI_API_KEY_*` exportée dans le profil du shell reste valide même retirée
du `.env` ; `uv run --env-file .env kb serve-ai` charge tout le `.env`, donc aussi des secrets dont
l'API IA n'a pas besoin (moindre privilège).

**Écrire les comptes rendus de veille dans le coffre** (`kb serve-data` et `kb serve-ai` lancés ; voir
[docs/fiches-veille.md](docs/fiches-veille.md), « Fiches dans le coffre ») :

```sh
KB_DATA_DIR=~/.knowledge_base KB_VAULT_DIR=<coffre> uv run --env-file .env kb digest
```

`kb digest` demande à l'API IA les fiches de sa fenêtre par défaut (`KB_DIGEST_WINDOW_DAYS`, lue
par `kb serve-ai`), avec la clé `KB_AI_API_KEY_KB_DIGEST`, à l'adresse `KB_AI_API_URL`
(`http://127.0.0.1:8001` par défaut ; elle ne suit pas `KB_AI_API_PORT` : la changer aussi). Il
écrit une fiche par sujet rendu, `<KB_VAULT_DIR>/veille/<sujet>/AAAA-MM-JJ.md`, au jour UTC de la
demande : un frontmatter (`subject`, `generated`, `model`, la fenêtre, `items_capped`, la sorte
coupée par le plafond et la date de son premier item laissé (`capped_kind`, `covered_after`),
`request_id`), les affirmations, chacune avec le numéro de ses sources, puis les sources, leur
titre et leur URL. Chaque affirmation et chaque titre est écrit en texte : ni lien, ni image, ni
balise, ni code, ni requête Dataview ne peut s'y activer. Une fiche n'est jamais réécrite (sauf deux
lancements qui se chevauchent, qui peuvent en remplacer une sans message : #295) : s'il en existe
une du jour, aucune demande n'est faite. Une demande dure jusqu'à environ 220 s ; `kb digest`
attend 240 s au plus, sans nouvelle tentative, et montre qu'il attend : une ligne qui tourne dans un
terminal, une ligne datée toutes les 10 s ailleurs. Il affiche ensuite une ligne par fiche écrite, puis un
résumé (fiches écrites, en échec, modèle, `request_id`, que `logs/kb-serve-ai.log` reprend). Code
de sortie, l'unité étant le sujet :

- 0 : chaque fiche rendue est écrite, ou la fenêtre n'en a aucune ;
- 4 : un sujet a échoué (nommé par l'API IA, ou sa fiche non écrite) et au moins une fiche est
  écrite ;
- 1 : rien n'est écrit : l'API IA est injoignable, dépasse le délai, refuse la clé (le message
  nomme `KB_AI_API_KEY_KB_DIGEST`, jamais la clé), répond en échec (502, 503, 504 : son état, son
  `X-Request-ID` et son `Retry-After` sont affichés) ou hors du schéma attendu ; ou chaque sujet a
  échoué ; ou une erreur du système (`OSError`, un dossier illisible) arrête le contrôle d'avant la
  demande, sans rien demander ;
- 2 : rien n'est demandé : `KB_DATA_DIR`, `KB_VAULT_DIR` (absente, ou pas un dossier existant) ou
  `KB_AI_API_KEY_KB_DIGEST` manque ou est refusée, une fiche du jour est déjà là, ou un dossier
  `veille/…` est un lien symbolique ;
- 143 : `kb digest` a reçu SIGTERM : les fiches déjà écrites sont gardées.

Le code 4 dit la même chose pour `kb collect` (l'unité est la source), `kb write-tops` (le top) et
`kb digest` (le sujet) : une partie a échoué, une autre est faite et gardée.

**Lire la base sans l'API** : la base s'ouvre en lecture seule avec `sqlite3`, sans clé ni
serveur :

```sh
sqlite3 -readonly ~/.knowledge_base/k-b.sqlite "SELECT kind, count(*) FROM item GROUP BY kind"
```

**Lancer les tests** :

```sh
uv run pytest
```

La CI (GitHub Actions, `.github/workflows/ci.yml`) lance quatre jobs, `audit` (pip-audit sur `uv.lock`),
`tests` (pytest), `lint` (ruff check et ruff format --check) et `types` (mypy --strict), sur chaque PR vers
`main` et sur chaque push sur `main`, donc après chaque fusion.

## Licence

© 2026 Sabine Laurent — sous licence [Creative Commons Attribution - Pas d'Utilisation Commerciale 4.0 International (CC BY-NC 4.0)](https://creativecommons.org/licenses/by-nc/4.0/deed.fr).

- **Réutilisation autorisée**, à condition de citer l'origine : [github.com/SabineLaurent/K-B](https://github.com/SabineLaurent/K-B).
- **Toute utilisation commerciale est interdite** sans mon accord écrit préalable.

Texte complet : voir [LICENSE](LICENSE).

## Crédits

Les papiers viennent de l'API arXiv, qui demande cette mention à chacun de ses utilisateurs
([arXiv API Access](https://info.arxiv.org/help/api/index.html), consulté le 2026-10-25) :

> Thank you to arXiv for use of its open access interoperability.

L'API de données la donne aussi, dans la description de son OpenAPI (`/docs`).
