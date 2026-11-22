# Le produit K-B

Cette page dit ce que fait K-B, ce qu'il ne fait pas, ses contraintes techniques et ses moyens. Elle est écrite
d'après `main` au commit `39cb5eb9` (2026-11-22). Le détail de chaque partie est dans les fiches du menu.

## L'objectif

K-B a deux portes d'entrée:

- **La veille**: un pipeline collecte chaque jour l'actualité tech venue de plusieurs sources, la range en items
    datés dans une base, puis répond à <q>quoi de neuf cette semaine ?</q>. Un modèle de langage en écrit des comptes
    rendus par sujet, rangés en fiches datées dans un coffre Obsidian.
- **La base de connaissance**: les documents qui comptent sont déposés à la main, puis compilés en un wiki
    Markdown durable, à la façon du <span lang="en">LLM wiki</span> d'Andrej Karpathy: les sources restent
    immuables, et le wiki relie les pages, signale les contradictions et date ce qu'il affirme. Cette porte est
    prévue (section [Plus tard](#plus-tard)).

La revue des outils existants est dans
[la veille de l'existant](https://github.com/SabineLaurent/K-B/blob/main/docs/veille/2026-09-23-veille-existant.md),
du 2026-09-23. Son constat principal: aucun ne fait de veille datée.

## Ce que fait K-B

### L'import des données: le pipeline de veille

- **La collecte**, avec un point de lancement unique, une panne isolée par source et une sauvegarde brute. Les sept
    sources sont les suivantes.
    - L'API GitHub: les releases des dépôts suivis, les alertes de sécurité, les dépôts les plus étoilés et les
        plus forkés.
    - L'API arXiv: les papiers sur la sécurité de l'IA, leurs métadonnées et leur résumé.
    - Le catalogue KEV (<span lang="en">Known Exploited Vulnerabilities</span>) de la CISA, l'agence américaine de
        cybersécurité: les vulnérabilités activement exploitées, un fichier CSV.
    - Le Markdown que produit Obsidian Web Clipper, dans un coffre Obsidian dédié.
    - Les newsletters tldr.tech, lues par <span lang="en">scraping</span>.
    - Les papiers lus dans Zotero et leurs surlignages, dans sa base SQLite.
    - Les dépôts GitHub qui montent sur 3 jours, calculés depuis GH Archive sur BigQuery.

    Les sources suivies sont dans [la liste des sources](https://github.com/SabineLaurent/K-B/blob/main/docs/sources.md),
    leur accès et leurs limites dans
    [les spécifications de la collecte](https://github.com/SabineLaurent/K-B/blob/main/docs/specs-collecte.md).
- **Le dédoublonnage par la base**: les dates sont normalisées, les doublons écartés selon la nature de chaque
    source, les écarts et les rejets tracés, et les règles écrites ([la fiche des données](donnees.md)).
- **Le stockage** dans une base modélisée avec Merise, avec une installation qu'un tiers peut rejouer.
- **L'API REST authentifiée**, documentée en OpenAPI, qui sert les items et répond à
    <q>quoi de neuf cette semaine ?</q>.
- **Les données personnelles**: un registre des traitements et une purge codée, `kb purge`.

### Les comptes rendus de veille

Un modèle lit la veille, à travers l'API de données, et ce qui en sort est rangé dans le coffre Obsidian, sous
`veille/`.

- **Les comptes rendus de veille par sujet** (`kb digest`): le modèle range les items de la fenêtre dans les sujets
    d'une liste fermée, puis écrit, pour chaque sujet, des affirmations qui citent leurs items; une fiche par sujet,
    `veille/<sujet>/AAAA-MM-JJ.md`.
- **Le compte rendu des tendances** (`kb trend-report`): parmi les dépôts qui montent sur GH Archive, le code
    calcule les rangs et les critères (durables, nouveaux, en accélération) et lit la fiche GitHub de chaque
    candidat; le modèle en choisit au plus 5, puis écrit quatre textes courts sur chacun, depuis sa fiche, son README
    et les définitions des sujets de veille qu'il porte; `veille/tendances/AAAA-MM-JJ.md`.
- **Les tops** (`kb write-tops`, sans modèle): une fiche datée pour chacun des deux classements de 100 dépôts, les
    plus étoilés et les plus forkés, sous `veille/tops/`.
- **Les contrôles**: le modèle renvoie du JSON; le code le revalide (schéma fermé, sujets de la liste, items cités
    parmi ceux envoyés, ni lien ni balise) et retire une affirmation dont les faits ne se retrouvent pas dans l'item
    cité. Une sortie hors schéma n'est jamais écrite.
- **L'API IA authentifiée**, distincte de l'API de données et documentée en OpenAPI, dont `kb digest` et
    `kb trend-report` sont les clients. L'inférence passe par Azure, en zone de données UE, par une API compatible
    OpenAI: le modèle se choisit en configuration ([la fiche de l'API IA](api-ia.md),
    [la fiche du service d'IA](service-ia.md)).
- **Les mesures** de chaque appel (durée, jetons, coût estimé, erreurs, fidélité), sur une ligne JSON de la sortie
    standard et en OpenTelemetry vers Grafana Cloud, en région UE. Un tableau de bord les montre, et cinq alertes sur
    seuil partent par courriel: sorties invalides, fidélité basse, coût au-dessus du budget, appels en échec, demande
    de compte rendu de plus de 180 s ([la fiche du monitorage](monitorage.md)).
- **Le site**, servi par `kb serve-web`, sans JavaScript: le fil des items, leur détail et les tendances.

## Hors du périmètre

- Les contradictions signalées entre pages du wiki, son interrogation, le contrôle du wiki par l'IA.
- Des notes personnelles comme entrées du wiki.
- Les livres en PDF, et les images, tableaux et pages scannées des PDF.
- Un serveur MCP (<span lang="en">Model Context Protocol</span>).
- Tout entraînement de modèle.

## Plus tard

- La compilation des clips en wiki, par des fiches de lecture que le modèle rédige (#168), puis sa mise en ligne
    (#170).
- La recherche dans la base, `kb search`.

## Les contraintes techniques

- **Python 3.13** (`.python-version`), langage du code; dépendances et environnement par uv. **SQL** pour le schéma
    et les requêtes, sans ORM (<span lang="en">object-relational mapping</span>): `database/schema.sql` et le module `sqlite3`, `database/schema_postgresql.sql` et
    psycopg 3 pour PostgreSQL ([la fiche de l'installation](installation.md)).
- **La base**: SQLite en local, PostgreSQL en ligne; `KB_DATABASE_URL` choisit le moteur, et les deux reçoivent
    les mêmes requêtes ([la fiche des données](donnees.md), « Deux usages, deux moteurs »).
- **Les données hors du dépôt**, dans le dossier de `KB_DATA_DIR`.
- **Les réglages par variables d'environnement**: hôtes, ports, chemins et secrets; un secret n'a pas de valeur par
    défaut, et une commande sans lui refuse de démarrer.
- **Les données personnelles**: le modèle traite en zone de données UE; ce que K-B garde, et combien de temps, est
    tenu par le
    [registre des traitements](https://github.com/SabineLaurent/K-B/blob/main/docs/registre-traitements.md).
- **Les contrôles**: chaque demande de fusion vers `main`, branche protégée, passe les six contrôles requis de l'intégration continue (CI)
    (`audit`, `tests`, `lint`, `types`, `tests-postgresql`, `bicep-build`) avant d'être fusionnée, rejoués en local du
    2026-11-22 au prochain déploiement ([la fiche de l'intégration continue](integration-continue.md)).

## Les moyens et leurs coûts

Les coûts du tableau suivant, sauf la ligne du modèle, ont été relevés le 2026-10-25, avant le choix de PostgreSQL pour la base en ligne, le
2026-11-06 ([journal des décisions](https://github.com/SabineLaurent/K-B/blob/main/docs/ADR/journal-decisions-projet.md),
« Base: PostgreSQL en ligne, par un adaptateur maison (#417) »). Il donne chaque poste et son coût.

| Poste | Coût |
|---|---|
| API GitHub | un jeton en lecture seule, sans frais ([le jeton GitHub](https://github.com/SabineLaurent/K-B/blob/main/docs/jeton-github.md)) |
| BigQuery (GH Archive) | un bac à sable sans compte de facturation: au-delà du quota gratuit (1 Tio lu par mois), une requête est refusée, jamais facturée ([BigQuery](https://github.com/SabineLaurent/K-B/blob/main/docs/bigquery.md)) |
| Modèle des fiches | gpt-6.1-sol depuis le 2026-11-18, 250 000 jetons par minute ([la fiche du service d'IA](service-ia.md)); avant, gpt-6-luna sur Azure AI Foundry, région France Central, zone de données UE, 140 000 jetons par minute (journal des décisions, 2026-10-17). Pour gpt-6-luna, l'ordre de grandeur relevé le 2026-10-16: au pire environ 420 000 jetons par demande de fiches, à 0,12 $ en entrée et 0,60 $ en sortie par million de jetons, prix UE, soit quelques centimes (journal des décisions, 2026-10-16) |
| Mise en ligne: coûts communs aux deux options (France Central, prix publics en dollars, mois de 730 h) | **8,96 $ par mois** sans l'offre gratuite d'Azure Container Apps, **5,26 $** avec elle; **29,32 $**, ou environ **27,70 $**, si les deux API gardent une réplique. Le détail: le job de collecte et d'import, une exécution par jour de 15 min à 0,5 vCPU (<span lang="en">virtual CPU</span>) et 1 Gio (hypothèse, non mesurée), 0,41 $ au tarif actif (0,000024 $ par vCPU-seconde, 0,000003 $ par Gio-seconde); `kb serve-data` et `kb serve-ai`, 0,5 vCPU et 1 Gio chacune, à zéro réplique au repos (décidé le 2026-11-06, #414) et actives 1 h par jour (hypothèse), 3,29 $, ou 23,65 $ avec une réplique gardée, au tarif de repos (0,000003 $ par vCPU-seconde et par Gio-seconde); le brut dans Blob Storage (Hot LRS, <span lang="en">locally redundant storage</span>, 0,0192 $ par Go et par mois), 10 Go supposés, non mesurés, 0,19 $; le registre d'images Azure Container Registry Basic (0,1666 $ par jour, 10 Go compris), 5,07 $, ou 0 $ avec le registre de GitHub (GHCR), gratuit pour un paquet public; ACR Basic choisi le 2026-11-06 (#414), tiré par identité managée, sans secret; les journaux dans Log Analytics, 0 $ sous 5 Go par mois, puis 2,76 $ par Go. L'offre gratuite (180 000 vCPU-secondes, 360 000 Gio-secondes et 2 millions de requêtes par abonnement et par mois) couvre le job et les deux API à zéro réplique (123 188 vCPU-secondes, 246 375 Gio-secondes) |
| Mise en ligne, option SQLite et Blob | **0,02 $ par mois** de plus: la base, un fichier produit par le job puis rangé dans Blob Storage, et lu par `kb serve-data` au démarrage (hypothèse: la façon de la lire n'était pas décidée), 1 Go supposé, au prix du brut |
| Mise en ligne, option PostgreSQL, retenue le 2026-11-06 | **18,13 $ par mois** de plus: Azure Database for PostgreSQL, serveur flexible Burstable B1ms (1 vCore, 2 Gio), 0,019 $ de l'heure, 13,87 $, et 32 Gio de stockage, le minimum, à 0,133 $ par Go et par mois, 4,26 $; une sauvegarde au-delà du stockage compris est comptée 0,10 $ par Go et par mois, non chiffrée |

Les sources de ces coûts, consultées le 2026-10-25:

- Les prix de France Central:
    [l'API des prix de détail d'Azure](https://learn.microsoft.com/rest/api/cost-management/retail-prices/azure-retail-prices)
    (Microsoft Learn), requête `https://prices.azure.com/api/retail/prices` filtrée par
    `armRegionName eq 'francecentral'` et par `serviceName` (`Azure Container Apps`, `Container Registry`, `Storage`,
    `Azure Database for PostgreSQL`, `Log Analytics`). Les pages de prix d'Azure n'affichaient pas leurs chiffres ce
    jour-là.
- L'offre gratuite, la facturation des jobs et le compteur de gestion (plan <span lang="en">Dedicated</span>
    seulement): [<span lang="en">Azure Container Apps pricing</span>](https://azure.microsoft.com/en-us/pricing/details/container-apps/).
- Le stockage minimal de 32 Gio:
    [<span lang="en">Compute options in Azure Database for PostgreSQL</span>](https://learn.microsoft.com/azure/postgresql/compute-storage/concepts-compute)
    (Microsoft Learn, mis à jour le 2026-07-08).
- Le stockage compris dans Container Registry Basic:
    [<span lang="en">Azure Container Registry service tiers</span>](https://learn.microsoft.com/azure/container-registry/container-registry-skus)
    (Microsoft Learn).
- GHCR gratuit pour un paquet public:
    [<span lang="en">How use of GitHub Packages is measured</span>](https://docs.github.com/en/billing/concepts/product-billing/github-packages)
    (GitHub Docs).
