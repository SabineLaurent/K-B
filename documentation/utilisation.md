# Utiliser K-B

Cette page donne chaque commande de `kb` dans l'ordre où elle sert: la base, la collecte et l'import, les deux API, les
comptes rendus, le site, puis les commandes des jobs en ligne. Pour chacune, elle dit comment la lancer, ce qu'elle
affiche et ses codes de sortie, et renvoie à la fiche qui la détaille. Elle est écrite d'après `main` au commit
`39cb5eb9` (2026-11-22). Les chemins du code de K-B (`commands/…`, `post/…`) partent de `src/k_b/`, les autres de la
racine du dépôt. L'installation et chaque variable d'environnement sont dans
[la fiche de l'installation](installation_pour_docu.md).

## Lancer une commande

En local, chaque commande se lance depuis la racine du dépôt, avec le `.env`:

```sh
uv run --env-file .env kb <commande>
```

`kb` ne charge jamais un `.env` lui-même: `uv run --env-file .env` le lui donne. `KB_DATA_DIR`, le dossier des
données, hors du dépôt, est demandé par toutes les commandes sauf `kb --help` et `kb openapi`. `uv run kb --help`
liste les 16 commandes et leurs codes de sortie, sans lire l'environnement. Le tableau suivant donne le sens commun de
chaque code.

| Code | Sens |
|---|---|
| 0 | la commande a réussi |
| 1 | la commande a tourné et a échoué |
| 2 | rien n'a été lancé: un réglage, un fichier ou la ligne de commande est refusé |
| 3 | `kb serve-data`, `kb serve-ai`, `kb serve-web`: le serveur n'a pas démarré |
| 4 | `kb collect`, `kb write-tops`, `kb digest`: une partie a échoué, une autre est faite et gardée |
| 130 | la commande a reçu SIGINT (Ctrl-C) |
| 143 | la commande a reçu SIGTERM (`docker stop`, l'arrêt d'un job) |

Le code 4 dit la même chose pour `kb collect` (l'unité est la source), `kb write-tops` (le top) et `kb digest` (le
sujet): une partie a échoué, une autre est faite et gardée. `kb download-watch-sheets`, `kb daily-routine` et
`kb digest-watch` ont leurs propres règles du code 4, données dans leur section.

## La base et le brut

### Créer la base

```sh
uv run --env-file .env kb create-db
```

`kb create-db` crée le fichier SQLite `<KB_DATA_DIR>/k-b.sqlite`, ou, avec `KB_DATABASE_URL`, les tables de la base
PostgreSQL de l'URL, qui doit déjà exister. Une base qui existe n'est jamais touchée. Ses étapes et ses codes sont
dans [la fiche des données](import_et_base_pour_docu.md), « Installer le système de gestion de base de données ».

### Collecter: `kb collect`

```sh
uv run --env-file .env kb collect
```

`kb collect` journalise son début (`collection started: 17 sources selected`), le départ de chaque source puis ce
qu'elle a écrit, et sa fin avec la durée. Il affiche ensuite une ligne par source:

- `ok`, avec le nombre de fichiers bruts écrits, par exemple `ok (1 raw file)`;
- `failed`, avec le type de l'erreur;
- `skipped`: Zotero sans `KB_ZOTERO_DIR`, les clips sans `KB_VAULT_DIR`, GH Archive sans
    `GOOGLE_APPLICATION_CREDENTIALS`, une source que `KB_COLLECT_ONLY` écarte.

Ses codes de sortie:

- 0: tout a réussi;
- 4: au moins une source a réussi et au moins une a échoué, l'état de la collecte écrit;
- 1: aucune source lancée n'a réussi, ou l'état de la collecte n'a pas pu être écrit;
- 2: `KB_DATA_DIR` manque ou n'est pas un dossier existant, l'état de la collecte est illisible, ou
    `KB_COLLECT_ONLY` est refusée;
- 143, 130: SIGTERM, SIGINT. Ce qui a été fait avant le signal est gardé; reçu avant l'écriture de l'état de la
    collecte, le signal laisse l'état inchangé, et la collecte suivante repart des mêmes dates.

La collecte, pas à pas, est dans [la fiche des données](import_et_base_pour_docu.md), « La commande qui précède
l'import: `kb collect` »; l'accès à chaque source et ses limites, dans
[les spécifications de la collecte](https://github.com/SabineLaurent/K-B/blob/main/docs/specs-collecte.md).

### Importer: `kb import`

```sh
uv run --env-file .env kb import
```

`kb import` lit le brut pas encore importé et écrit ses items dans la base, qui écarte les doublons. Son bilan, son
journal et ses codes sont dans [la fiche des données](import_et_base_pour_docu.md), « Le script d'agrégation et
d'import: `kb import` ». Pour reconstruire une base SQLite depuis tout le brut: supprimer `k-b.sqlite`, puis lancer
`kb create-db` et `kb import`.

### Purger: `kb purge`

```sh
uv run --env-file .env kb purge
```

`kb purge` supprime ce qui a passé sa durée de conservation, à compter de l'heure de son lancement: les bruts
remplacés des catalogues d'état (Zotero, CISA KEV), la veille de la base (items et tendances, 3 ans), le brut de plus
de 6 mois, les lignes du registre dont le fichier n'est plus là et que rien ne cite, puis les journaux de
fonctionnement et les journaux d'import de plus de 6 mois
([le registre des traitements](https://github.com/SabineLaurent/K-B/blob/main/docs/registre-traitements.md),
« Procédure de tri »). `kb import` ne purge rien. Chaque purge journalise ce qu'elle a supprimé, en nombres, jamais
un nom, puis `kb purge` affiche son bilan sur une ligne:

```text
purge: 2 superseded raw files, 40 items, 0 trend rows, 12 references, 0 tracked repositories, 3 raw collections, 3 registry rows, 5 logs and journals deleted
```

Ses codes de sortie:

- 0: les purges ont réussi;
- 1: une purge a échoué; les suivantes ne tournent pas, et le `kb purge` suivant les relance
    (`purge failed: … ; run kb purge again`). Aucun bilan n'est affiché: ce que les purges d'avant ont supprimé est
    au journal;
- 2: `KB_DATA_DIR` manque, la base n'existe pas (`kb create-db`), ou `KB_DATABASE_URL` est refusée;
- 143, 130: SIGTERM, SIGINT; la purge en cours dans la base est annulée, et ce qui a déjà été supprimé le reste.

### Écrire les fiches des tops: `kb write-tops`

```sh
uv run --env-file .env kb write-tops
```

`kb write-tops` lit les classements dans le brut et écrit leurs fiches dans le coffre de `KB_VAULT_DIR`, sous
`veille/tops/`. Ses lignes, ses règles et ses codes sont dans [la fiche des données](import_et_base_pour_docu.md),
« La commande qui suit l'import: `kb write-tops` ».

### Toute la chaîne, en local

```sh
uv run --env-file .env kb collect; uv run --env-file .env kb import; uv run --env-file .env kb purge
uv run --env-file .env kb write-tops
```

Chaque étape tourne même si la précédente a échoué en partie, et garde son propre code de sortie. En ligne, le job
de chaque jour enchaîne ces étapes ([Les commandes des jobs en ligne](#les-commandes-des-jobs-en-ligne)).

## L'API de données: `kb serve-data`

L'API de données sert la base, en lecture seule: les items, leur détail, les tendances, et, en ligne, les fiches des
tops et des comptes rendus. Son contrat est dans
[les spécifications des API](https://github.com/SabineLaurent/K-B/blob/main/docs/specs-api.md).

### La lancer et l'appeler

1. Faire une clé par client, qui nomme le programme qui appelle (le terminal, un script):

    ```sh
    uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
    ```

    puis la ranger dans le `.env`: `KB_DATA_API_KEY_TERMINAL=<la clé>`.

2. Lancer l'API. Elle écoute par défaut sur `http://127.0.0.1:8000`, la machine seule; `KB_DATA_API_HOST`,
    `KB_DATA_API_PORT` et `KB_DATA_API_ALLOWED_HOSTS` changent l'hôte, le port et les hôtes permis:

    ```sh
    uv run --env-file .env kb serve-data
    ```

3. L'appeler avec la clé:

    ```sh
    curl -H "Authorization: Bearer <la clé>" "http://127.0.0.1:8000/items?kind=paper&limit=5"
    ```

La documentation de l'API est servie sur `http://127.0.0.1:8000/docs`, sans clé, avec
`KB_DEPLOYMENT_ENVIRONMENT=sandbox` seulement; sinon, en production comme sans la variable, `/docs` répond 404. Son
OpenAPI est versionnée dans `docs/api/openapi-donnees.json`, réécrite par `uv run kb openapi`, lancé à la racine du
dépôt; ailleurs, sans dossier `docs/api`, il n'écrit rien et sort en code 2. `kb serve-data` journalise une ligne par
requête dans `<KB_DATA_DIR>/logs/kb-serve-data.log`, avec le nom du client, jamais sa clé.

### Ses codes de sortie

- 2, sans lancer l'API: `KB_DATA_DIR` manque; aucune clé n'est donnée; un nom de client est vide ou hors `A-Z`, `0-9`
    et `_`; une clé a moins de 32 caractères, ou un caractère hors `A-Z`, `a-z`, `0-9`, `_` et `-`, l'alphabet de
    `token_urlsafe`; deux clients ont la même clé. Le message nomme la variable, jamais sa valeur.
- 2 aussi: l'hôte n'est pas une adresse IPv4, le port n'est pas un entier de 1 à 65535, la liste des hôtes permis
    est vide ou contient une entrée vide, une entrée avec `*` ou une entrée hors nom en minuscules, ou
    `KB_LOG_TO_FILE` n'est ni `true` ni `false` (`false`: le journal sur la sortie d'erreur seule). Le message nomme
    la variable et cite la valeur refusée.
- 2 encore: `KB_DATABASE_URL` est refusée. Le message nomme la variable, sans citer sa valeur.
- 3: le port est déjà pris, par exemple par un autre `kb serve-data`; uvicorn écrit `address already in use` au
    journal.
- 0: un Ctrl-C, une fois le serveur démarré, arrête uvicorn proprement, sans la ligne `kb stopped by SIGINT` des
    autres commandes. Pendant le démarrage, le code dépend du moment: 130 avec cette ligne, 3 ou 0.

Avec une base PostgreSQL, `kb serve-data` démarre sans attendre la base: une base injoignable se voit à la requête,
qui répond 500 `database_error`.

### Ce que l'opératrice tient

- Un client se retire en retirant sa variable, puis en redémarrant `kb serve-data`: le retrait prend effet au
    redémarrage.
- Une variable `KB_DATA_API_KEY_*` exportée dans le profil du shell (`~/.zshrc`) reste valide même retirée du `.env`:
    elle se retire aussi de là.
- `uv run --env-file .env kb serve-data` charge tout le `.env`, jeton GitHub et identifiants Google compris, dont
    l'API n'a pas besoin. Un fichier d'environnement réduit à ses variables, donné à `--env-file`, ne lui donne que
    les droits de sa tâche.

## L'API IA: `kb serve-ai`

L'API IA rédige les comptes rendus de veille d'une fenêtre, par sujet, et le compte rendu des tendances. Elle lit la
veille par l'API de données, qui doit donc tourner, et appelle le modèle; elle ne garde rien entre deux demandes. Son
détail est dans [la fiche de l'API IA](api_ia_pour_docu.md), celui du modèle dans
[la fiche du service d'IA](service_ia_pour_docu.md).

### La lancer et lui demander des comptes rendus

1. Ranger dans le `.env`:
    - une clé par client de l'API IA, faite comme celles de l'API de données: `KB_AI_API_KEY_KB_DIGEST=<la clé>` et
        `KB_AI_API_KEY_KB_TREND_REPORT=<une autre clé>`;
    - la clé que l'API IA envoie à l'API de données, `KB_DATA_API_KEY_AI_DIGEST=<une autre clé>`, que
        `kb serve-data` lit aussi: redémarrer `kb serve-data`;
    - le jeton GitHub des comptes rendus des tendances, `KB_AI_GITHUB_TOKEN=<le jeton>`, un second jeton
        <span lang="en">fine-grained</span> sans permission
        ([le jeton GitHub](https://github.com/SabineLaurent/K-B/blob/main/docs/jeton-github.md));
    - le modèle: `KB_LLM_PROVIDER` et ses variables, décrites dans `.env.example`. `replay` répond par les réponses
        d'un fichier, sans réseau, sans clé et sans coût.

2. Lancer l'API IA, à côté de `kb serve-data`. Elle écoute par défaut sur `http://127.0.0.1:8001`, la machine seule;
    `KB_AI_API_HOST` et `KB_AI_API_PORT` changent l'hôte et le port, `KB_DIGEST_WINDOW_DAYS`, de 1 à 14, la fenêtre
    d'un sujet sans début, 3 jours par défaut:

    ```sh
    uv run --env-file .env kb serve-ai
    ```

3. Demander les comptes rendus d'une fenêtre. `window_days` est facultatif, de 1 à 14; `since_by_subject` aussi, le
    début d'un sujet, une date avec son fuseau, ramené à 14 jours au plus
    ([les fiches de veille](https://github.com/SabineLaurent/K-B/blob/main/docs/fiches-veille.md), « Fenêtre »):

    ```sh
    curl -X POST -H "Authorization: Bearer <la clé>" -H "Content-Type: application/json" \
      -d '{"window_days": 3, "since_by_subject": {"models": "2026-11-09T10:00:00Z"}}' \
      http://127.0.0.1:8001/digests
    ```

La documentation de l'API IA est servie sur `http://127.0.0.1:8001/docs`, sans clé, avec
`KB_DEPLOYMENT_ENVIRONMENT=sandbox` seulement (404 sinon). Son OpenAPI est versionnée dans `docs/api/openapi-ia.json`,
réécrite par `uv run kb openapi` avec celle de l'API de données. `kb serve-ai` journalise une ligne par requête dans
`<KB_DATA_DIR>/logs/kb-serve-ai.log`, un seul `kb serve-ai` par `KB_DATA_DIR`, avec le nom du client et l'identifiant
de la requête, rendu aussi dans l'en-tête `X-Request-ID` de chaque réponse. Chaque appel au modèle écrit une ligne
JSON de mesure sur la sortie standard, sans texte.

### Ses codes de sortie

- 2, sans lancer l'API: `KB_DATA_DIR` manque, ou une clé, l'hôte, le port, la fenêtre, le modèle, la clé
    `KB_DATA_API_KEY_AI_DIGEST` ou le jeton `KB_AI_GITHUB_TOKEN` (absent, <span lang="en">classic</span>, ou un
    caractère hors `[A-Za-z0-9_]`) est refusé. Le message nomme la variable, jamais une clé, un jeton ni l'URL du
    modèle.
- 3: le port est déjà pris.
- 0: un Ctrl-C, une fois le serveur démarré, comme pour `kb serve-data`.

### Ses limites de débit

Une demande à la fois par route, et 20 par 24 heures glissantes
([les fiches de veille](https://github.com/SabineLaurent/K-B/blob/main/docs/fiches-veille.md), « Accès »).
Redémarrer `kb serve-ai` remet le compte à zéro. Après un Ctrl-C de `kb digest`, l'API finit la demande en cours: une
relance reçoit 429 tant qu'elle n'a pas fini, environ 200 s au plus.

### Changer une clé

Une clé est fixe, sans date d'expiration. La faire, puis la changer en local ou en ligne: [la fiche de l'API
IA](api_ia_pour_docu.md), « Expiration et changement d'une clé ». Ce que chaque côté voit pendant le changement:

- l'ancienne clé d'un client de l'API IA est refusée dès le redémarrage de `kb serve-ai`, pas avant;
- tant que `kb serve-data` ou `kb serve-ai` garde l'ancienne `KB_DATA_API_KEY_AI_DIGEST`, chaque demande de comptes
    rendus reçoit 502 `data_api_unauthorized`;
- sur un 401 de l'API IA (`invalid_api_key`: une clé absente, changée d'un seul côté ou retirée), `kb digest`
    n'écrit aucune fiche, nomme la variable `KB_AI_API_KEY_KB_DIGEST` sans citer la clé, et sort en code 1, car la
    requête est partie; sans la clé, `kb digest` sort en code 2, sans rien demander. De même `kb trend-report`, qui
    nomme `KB_AI_API_KEY_KB_TREND_REPORT`.

Comme pour l'API de données, une variable `KB_AI_API_KEY_*` exportée dans le profil du shell reste valide même
retirée du `.env`, et `uv run --env-file .env kb serve-ai` charge tout le `.env`: un fichier réduit à ses variables
ne lui donne que les droits de sa tâche.

## Les comptes rendus dans le coffre

### Les comptes rendus de veille: `kb digest`

`kb serve-data` et `kb serve-ai` doivent tourner.

```sh
uv run --env-file .env kb digest
```

`kb digest` demande à l'API IA le compte rendu de chaque sujet depuis la fin du précédent: il lit le `until` de la
dernière fiche du sujet dans le coffre et l'envoie. Un sujet sans fiche prend la fenêtre de `KB_DIGEST_WINDOW_DAYS`,
lue par `kb serve-ai`; un début de plus de 14 jours est ramené à 14 jours, et journalisé. La demande part avec la clé
`KB_AI_API_KEY_KB_DIGEST`, à l'adresse `KB_AI_API_URL` (`http://127.0.0.1:8001` par défaut; elle ne suit pas
`KB_AI_API_PORT`: la changer aussi).

Il écrit une fiche par sujet rendu, `<KB_VAULT_DIR>/veille/<sujet>/AAAA-MM-JJ.md`, au jour UTC de la demande, et une
fiche « Aucun item classé dans ce sujet. » pour un sujet sans item, d'où part son compte rendu suivant. Une fiche
porte:

- un <span lang="en">frontmatter</span>: `subject`, `generated`, `model`, la fenêtre du sujet, `since` et `until`,
    `items_capped`, la sorte coupée par le plafond et la date de son premier item laissé (`capped_kind`,
    `covered_after`), `request_id`;
- les affirmations, chacune avec le numéro de ses sources;
- les sources, leur titre et leur URL.

Chaque affirmation et chaque titre est écrit en texte: ni lien, ni image, ni balise, ni code, ni requête Dataview ne
peut s'y activer. Une fiche n'est jamais réécrite, même par deux lancements qui se chevauchent: s'il en existe une du
jour, aucune demande n'est faite. Une demande dure jusqu'à environ 220 s. `kb digest` attend 240 s au plus, une
réponse de 8 000 000 d'octets au plus, sans nouvelle tentative; le délai ne compte qu'à partir du premier morceau de
la réponse ([les fiches de veille](https://github.com/SabineLaurent/K-B/blob/main/docs/fiches-veille.md), « Fiches
dans le coffre », « Limites »). Il montre qu'il attend: une ligne qui tourne dans un terminal, une ligne datée toutes
les 10 s ailleurs. Il journalise son début et sa fin, avec la durée, puis affiche un bilan: la fenêtre et le nombre
d'items lus, un tableau par sujet (statut, chemin de la fiche), le total, puis le modèle et le `request_id`, que
`logs/kb-serve-ai.log` reprend.

Ses codes de sortie, l'unité étant le sujet:

- 0: chaque sujet a sa fiche écrite, avec ou sans item; ou rien n'est lu (une base vide, un import pas lancé):
    aucune fiche n'est écrite, et chaque sujet garde son début;
- 4: un sujet a échoué (nommé par l'API IA, ou sa fiche non écrite) et au moins une fiche est écrite;
- 1: rien n'est écrit. L'API IA est injoignable, dépasse le délai, refuse la clé (le message nomme
    `KB_AI_API_KEY_KB_DIGEST`, jamais la clé), refuse la route à ce client (403, même message), refuse pour
    l'instant (429: une demande tourne déjà, ou 20 demandes en 24 heures), répond en échec (502, 503, 504: son état,
    son `X-Request-ID` et son `Retry-After` sont affichés) ou hors du schéma attendu; ou chaque sujet a échoué; ou une
    erreur du système (`OSError`, un dossier illisible) arrête le contrôle d'avant la demande, sans rien demander;
- 2: rien n'est demandé. `KB_DATA_DIR`, `KB_VAULT_DIR` (absente, ou pas un dossier existant) ou
    `KB_AI_API_KEY_KB_DIGEST` manque ou est refusée, une fiche du jour est déjà là, un dossier `veille/…` est un lien
    symbolique, ou la dernière fiche d'un sujet n'a pas de `until` valide (`previous_sheet_invalid`);
- 143, 130: SIGTERM, SIGINT. Les fiches déjà écrites sont gardées.

### Le compte rendu des tendances: `kb trend-report`

`kb serve-data` et `kb serve-ai` doivent tourner. Le contrat du compte rendu est dans
[les tendances](https://github.com/SabineLaurent/K-B/blob/main/docs/tendances.md).

```sh
uv run --env-file .env kb trend-report
```

`kb trend-report` lit le registre des comptes rendus, `<KB_DATA_DIR>/trend_reports.json`, puis demande à l'API IA les
fenêtres de GH Archive postérieures à la dernière du compte rendu précédent (les 4 dernières au premier), avec la clé
`KB_AI_API_KEY_KB_TREND_REPORT`, à l'adresse `KB_AI_API_URL`. Il écrit `<KB_VAULT_DIR>/veille/tendances/AAAA-MM-JJ.md`,
au jour UTC du lancement: la période et ses limites, la limite de GH Archive (un échantillon d'environ 1 % des
étoiles), le tableau des dépôts qui remplissent au moins un critère (durable, nouveau, en accélération), puis les
dépôts que le modèle a choisis, chacun avec ses quatre textes. Il ajoute enfin une entrée au registre, qui donne sa
période au compte rendu suivant: le coffre n'est jamais relu. Un compte rendu n'est jamais réécrit: s'il en existe
un du jour, aucune demande n'est faite. Un choix du modèle qui échoue laisse un compte rendu des seuls faits, et un
texte qui échoue laisse les textes de son dépôt de côté; chacun est journalisé avec son état et le `request_id`
(`commands/trend_report_command.py:82-98`).

Il montre qu'il attend comme `kb digest`, puis affiche un bilan en comptes, sans nom de dépôt: la période, les dépôts
retenus et écartés, le chemin du fichier, le modèle (`none` quand aucun choix n'est fait) et le `request_id`
(`commands/trend_report_command.py:283-305`).

Ses codes de sortie:

- 0: le compte rendu est écrit et noté au registre; ou aucune fenêtre n'est postérieure au compte rendu précédent, ou
    la base n'en a aucune: rien n'est écrit, et le bilan le dit (une base plus ancienne que le registre, restaurée,
    donne un avertissement avec les deux dates);
- 1: rien n'est écrit. L'API IA échoue comme pour `kb digest` (le message nomme `KB_AI_API_KEY_KB_TREND_REPORT` sur un
    401 ou un 403), ou sa réponse contredit la demande (une période qui ferait reculer, sauter ou grossir le
    registre); ou le compte rendu n'est pas écrit, le registre inchangé; ou il est écrit mais le registre n'est pas
    mis à jour: le message le dit, et le compte rendu suivant reprend ces fenêtres; ou une erreur du système arrête
    le contrôle d'avant la demande;
- 2: rien n'est demandé. `KB_DATA_DIR`, `KB_VAULT_DIR` ou `KB_AI_API_KEY_KB_TREND_REPORT` manque ou est refusée, le
    registre est illisible ou hors de son schéma, le compte rendu du jour est déjà là, ou un dossier `veille/…` est
    un lien symbolique;
- 143, 130: SIGTERM, SIGINT. Un compte rendu déjà écrit est gardé; si le registre n'a pas suivi, le compte rendu
    suivant reprend ces fenêtres.

## Le site: `kb serve-web`

```sh
uv run --env-file .env kb serve-web
```

Le site montre le fil des items, leur détail et les tendances, sans JavaScript. Il écoute par défaut sur
`http://127.0.0.1:8002` et lit l'API de données avec la clé de son client, `KB_DATA_API_KEY_WEB`. Il est privé: chaque
requête, sauf `/health`, doit porter dans l'en-tête `X-MS-CLIENT-PRINCIPAL-ID` l'identifiant d'objet Microsoft Entra
de `KB_WEB_OPERATOR_ID`, que pose Azure Container Apps une fois la connexion faite; cet identifiant n'est jamais
journalisé ni cité. En local, `KB_WEB_AUTH=off` n'en lit aucun, sur `127.0.0.1` et hors d'Azure seulement.
`KB_WEB_HOST`, `KB_WEB_PORT` et `KB_WEB_ALLOWED_HOSTS` changent l'hôte, le port et les noms servis
([le site](https://github.com/SabineLaurent/K-B/blob/main/docs/site-web.md)).

## Les fiches publiées en ligne, dans le coffre local: `kb download-watch-sheets`

En ligne, les jobs publient les fiches de `veille/` dans le conteneur `watch` du stockage d'échange. En local,
`make download-watch-sheets` copie dans `veille/` du coffre chaque fiche de `watch` qui lui manque, par le compte
Entra de l'opératrice, qui a le rôle Storage Blob Data Reader sur `watch`. Une fois par séance, `az login` donne le
jeton: la commande prend celui d'`az` (Azure CLI), dans le tenant de son compte courant, sans AzCopy ni
`AZURE_CLIENT_ID`. Le `.env` porte `KB_DATA_DIR`, `KB_VAULT_DIR` et `KB_EXCHANGE_BLOB_URL`
(`https://<compte>.blob.core.windows.net`).

```sh
az login --tenant <tenant>
make download-watch-sheets
```

- Une fiche déjà dans `veille/` n'est ni téléchargée ni remplacée, même modifiée en local: un second passage copie
    0 fiche.
- Seuls passent les noms `<dossier>/<jour>.md` (jour en `AAAA-MM-JJ`) d'un dossier où `kb` écrit: les 9 sujets,
    `tops/most_starred`, `tops/most_forked`, `tendances`. Un nom de cette forme d'un autre dossier (un sujet ajouté ou
    retiré) est laissé de côté, sans échec. Tout autre nom est refusé, cité par sa position (`blob 3 of 12`), jamais
    écrit; les autres fiches sont copiées quand même.
- Sont refusés aussi: un blob de plus de 4 000 000 octets, un texte qui n'est pas de l'UTF-8, qui porte un caractère
    de contrôle autre que la tabulation et le retour à la ligne, ou un contrôle bidirectionnel (`BIDI_CONTROLS`, que
    `kb` n'écrit jamais).
- Est refusé enfin le Markdown qu'Obsidian ou un module d'Obsidian exécuterait ou chargerait, que `kb` n'écrit jamais
    sans l'échapper: un accent grave (du code, une requête Dataview, `sheet_text_with_code`), `~~~` n'importe où dans
    une ligne (`sheet_text_with_tilde_fence`), `![` (une image distante, une note incluse, `sheet_text_with_embed`),
    un `<` qui n'ouvre pas un autolien `<http://…>` ou `<https://…>` (du HTML, une commande Templater,
    `sheet_text_with_html`), une référence de caractère, même dans un autolien (`&#x202E;`, `&rlm;`: Obsidian
    l'affiche décodée, un contrôle bidirectionnel, `sheet_text_with_character_reference`). Échappé, c'est-à-dire
    précédé d'un nombre impair de `\`, le caractère passe, hors d'un autolien, où une barre oblique inverse n'échappe
    rien (CommonMark 0.31.2, § 6.5): un `\` dans un autolien est refusé (`sheet_text_with_backslash_in_autolink`).
    `kb` écrit des liens `[dépôt](url)` dans les tops et des `~` dans une URL ou une description: un lien ne s'ouvre
    qu'au clic, et une description de top qui contient `~~~` fait refuser sa fiche, un refus visible.
- Au-delà de 20 000 blobs, la liste s'arrête et la commande échoue.
- `veille/` ou un de ses dossiers en lien symbolique est refusé; un temporaire laissé par une écriture interrompue
    (`veille/<dossier>/.<jour>.md.tmp`) fait échouer sa fiche, nommée par son chemin: il se supprime à la main.

Ses codes de sortie:

- 0: chaque fiche de `watch` est dans `veille/`;
- 4: un blob est refusé, une fiche non écrite, la liste arrêtée à 20 000 blobs ou le stockage en erreur pendant le
    téléchargement, et une autre fiche de `watch` est dans `veille/`;
- 1: les mêmes cas, quand aucune ne l'est; ou le stockage n'est pas joint (sans `az login`:
    `exchange_storage_no_token`);
- 2: un réglage manque ou est refusé; un coffre qui n'existe pas n'est jamais créé;
- 130, 143: SIGINT, SIGTERM.

Ce que la commande laisse à l'opératrice:

- **Une fiche supprimée en local revient** au passage suivant tant que `watch` la porte, et `watch` la reçoit de
    nouveau du partage `job-data` à la publication suivante. Pour la retirer: la supprimer dans `job-data`, puis dans
    `watch`, puis en local. Supprimer un blob demande le rôle Storage Blob Data Contributor
    ([<span lang="en">Delete Blob</span>](https://learn.microsoft.com/rest/api/storageservices/delete-blob), lu le
    2026-11-10), un rôle temporaire qu'un <span lang="en">Owner</span> peut se donner
    ([le registre des traitements](https://github.com/SabineLaurent/K-B/blob/main/docs/registre-traitements.md),
    « Procédure de tri », étape 9); l'opératrice n'a que Reader sur `watch`.
- **Une fiche est du Markdown qu'Obsidian affiche**, écrit par l'identité d'un job. Le téléchargement refuse le
    Markdown actif; les modules qui agissent sur un fichier neuf, comme Templater avec
    <span lang="en">« Trigger Templater on new file creation »</span>, qui remplace alors chaque commande trouvée
    dans le fichier ([les réglages de Templater](https://silentvoid13.github.io/Templater/settings.html), lus le
    2026-11-10), se règlent dans le coffre. Les gestes: vérifier que
    <span lang="en">« Enable JavaScript Queries »</span> et <span lang="en">« Enable Inline JavaScript Queries »</span>
    de Dataview sont désactivés, comme par défaut depuis sa version 0.4.13 (CVE-2021-42057), et que le déclencheur de
    Templater est inactif ou que `veille/` est dans ses <span lang="en">« Excluded folders »</span>.
- **`az` reçoit tout l'environnement** que `uv run --env-file` charge, secrets du `.env` compris (azure-identity le
    passe au processus d'`az`). Un fichier d'environnement réduit aux trois variables de la commande ne lui donne que
    celles-ci.
- **L'écriture du coffre** (`post/vault_files.py`) suit un lien posé après son contrôle, et remplace une fiche qu'un
    autre programme écrit entre le contrôle et le renommage.
- **Le disque**: au pire, 20 000 blobs de 4 000 000 octets par passage.

## Les commandes des jobs en ligne

En ligne, les commandes tournent dans des jobs d'Azure Container Apps, déclarés dans `infra/`
([la fiche de l'architecture](architecture_pour_docu.md), « L'hébergement »). Chacune se lance aussi en local, avec
les réglages du job.

### Le test de fumée: `kb smoke-test`

```sh
KB_DATA_DIR=<dossier> KB_EXCHANGE_BLOB_URL=https://<compte>.blob.core.windows.net \
  AZURE_CLIENT_ID=<client id de l'identité du job> uv run kb smoke-test
```

`kb smoke-test`, la commande du job `caj-kb-smoke-test`, demande `GET /health` à l'API de données (`KB_DATA_API_URL`)
et à l'API IA (`KB_AI_API_URL`), sans clé. Après le `/health` de chaque API, qui la réveille, trois sondes sans clé
vérifient qu'elle refuse ce qu'elle doit refuser (`jobs/api_probes.py`): une route à clé rend 401 (`GET /items`,
`POST /digests`), `GET /docs` rend 404 (200 avec `KB_DEPLOYMENT_ENVIRONMENT=sandbox`, où les API le servent) et
`HEAD /health` rend 405; le corps d'une réponse n'est jamais lu. Puis il demande le jeton de l'identité managée
attribuée au job (`AZURE_CLIENT_ID`, un GUID; sans lui, le SDK chercherait l'identité système, que les jobs de K-B
n'ont pas), et liste une page d'au plus 100 noms du conteneur `smoke-test` du stockage d'échange
(`KB_EXCHANGE_BLOB_URL`, en `https`, sans défaut). Les neuf contrôles tournent toujours. Il n'écrit que des comptes:
jamais le nom d'un blob (celui d'un clip est son titre), ni le message d'une erreur du SDK, mais son état
(`exchange_storage_forbidden`…), son statut HTTP et son code; l'identité sans jeton, refusée ou injoignable, est
`exchange_storage_no_token`.

Ses codes de sortie:

- 0: les deux API répondent `{"status":"ok"}`, chaque sonde reçoit son statut et le conteneur est listé;
- 1: un contrôle échoue (`health_failed`, `health_timeout`… pour le `/health` d'une API; `probe_unexpected_status`
    avec le statut reçu, `probe_timeout` ou `probe_unavailable` pour une sonde);
- 2: rien n'est contrôlé, une variable manque ou est refusée;
- 143, 130: SIGTERM, SIGINT.

### Les jobs planifiés: `kb daily-routine` et `kb digest-watch`

`kb daily-routine` et `kb digest-watch` sont les commandes des jobs `caj-kb-daily-routine`, chaque jour à 08:00 UTC,
et `caj-kb-digest-watch`, par défaut le lundi et le jeudi à 10:00 UTC. Elles enchaînent leurs étapes dans le même
processus, chacune avec le code qu'elle rendrait seule:

```sh
KB_DATA_DIR=<dossier> KB_VAULT_DIR=<coffre> KB_EXCHANGE_BLOB_URL=https://<compte>.blob.core.windows.net \
  AZURE_CLIENT_ID=<client id de l'identité du job> uv run kb daily-routine
KB_DATA_DIR=<dossier> uv run kb daily-routine --dry-run    # les étapes et leurs règles, rien lancé, code 0
```

- `kb daily-routine`: le miroir du conteneur `clippings` vers `Clippings/` du coffre, `kb collect`, `kb import` (pas
    lancé si `kb collect` rend 1 ou 2), `kb purge` (lancé même si `kb import` échoue ou n'est pas lancé),
    `kb write-tops`, puis la publication de `veille/` vers le conteneur `watch`.
- `kb digest-watch`: `GET /health` des deux API, qui réveille une API à zéro réplique (`KB_DATA_API_URL`,
    `KB_AI_API_URL`), `kb digest`, de nouveau les deux `/health`, `kb trend-report`, puis la même publication.
    `kb trend-report` tourne même si `kb digest` échoue; un réveil échoué n'arrête rien et ne compte pas dans le code
    de sortie, ses lignes `ERROR` restent au journal: une API injoignable fait échouer l'étape qui suit.
- Le miroir copie un clip du premier niveau que le coffre n'a pas, ou a plus ancien (à la même seconde, d'une autre
    taille): la date du blob contre celle du fichier, qui prend ensuite celle du blob; il ne supprime rien. Laissé de
    côté, sans échec: un blob dans un dossier (`/`), caché (`.` initial) ou qui ne finit pas par `.md`. Refusé, et
    l'étape rend 4: un clip que le partage ne peut pas porter (`\`, un caractère de contrôle ou d'usage privé,
    `" : | < > * ?`, plus de 241 octets) ou plus gros que 1 000 000 octets. Le journal le cite par sa position dans
    la liste (`blob 12 of 120`), jamais par son nom; il est refusé à chaque exécution jusqu'à ce que son blob soit
    supprimé de `clippings`, et le renommer en local laisse l'ancien blob. Après une copie, la routine attend la
    marge de `kb collect` plus 5 s (65 s), pour qu'il lise le clip le jour même.
- La publication envoie chaque fiche de `veille/` absente de `watch`, à sa racine (`tops/<top>/<jour>.md`), sans
    jamais remplacer un blob; les entrées cachées, dont les temporaires d'une écriture interrompue, et les liens sont
    laissés de côté; un dossier illisible fait échouer l'étape.

Leur code de sortie est le pire de ceux des étapes, dans l'ordre 0, 4, 2, 1; un 2 peut venir d'une étape sans
échec: `kb digest` le rend quand la fiche du jour existe. 2 aussi quand rien n'est lancé, un réglage du job
(`KB_EXCHANGE_BLOB_URL`, `AZURE_CLIENT_ID`, `KB_VAULT_DIR`) manquant ou refusé; 143, 130: SIGTERM, SIGINT, la routine
s'arrête sans lancer la suite.

## L'image

Une image sert toutes les commandes `kb` (`Dockerfile`):

```sh
docker buildx build --platform linux/amd64 --tag k-b .
docker run --rm k-b --help
docker volume create k-b-data
docker run --rm -v k-b-data:/var/lib/knowledge_base -e KB_DATA_DIR=/var/lib/knowledge_base k-b create-db
```

Azure Container Apps ne lance que des images `linux/amd64`: sur un Mac à puce Apple, Docker Desktop les construit et
les lance par émulation. L'image lance `kb` sous l'utilisateur `10001:10001`, jamais root. Son dossier de données, où
se monte le volume, est `/var/lib/knowledge_base`, et il appartient à cet utilisateur. `KB_DATA_DIR` n'a pas de valeur
dans l'image: elle se donne au lancement, avec le volume, et sans elle `kb` refuse de démarrer. Le journal est la
sortie d'erreur (`KB_LOG_TO_FILE=false`). Chaque variable se change au lancement (`-e`). `.dockerignore` refuse tout
par défaut: la construction ne reçoit que `pyproject.toml`, `uv.lock`, `README.md` et `src/`. Le contrôle de l'image
par la CI est dans [la fiche de l'intégration continue](integration_continue_pour_docu.md), « Le workflow `Image` ».

## Lire la base, lancer les tests

- Lire la base sans l'API, en local et en ligne: [la fiche des données](import_et_base_pour_docu.md), « Lire la base
    sans l'API ».
- Lancer les tests, leurs rapports et la couverture: [la fiche des tests](tests_pour_docu.md).
- La CI de chaque demande de fusion: [la fiche de l'intégration continue](integration_continue_pour_docu.md).
