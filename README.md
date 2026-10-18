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

Les données restent sur ma machine, et l'inférence passe par une API. Je lis dans Obsidian et
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
  - API GitHub : releases des dépôts suivis, alertes de sécurité, dépôts les plus étoilés ;
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
| `KB_VAULT_DIR` | non | dossier du coffre Obsidian de K-B, celui qui contient `Clippings/`, en chemin complet (un `~` écrit dans `.env` n'est pas développé). Sans elle, `kb collect` saute les clips et l'affiche (`clipping: skipped (KB_VAULT_DIR not set)`). Avec elle, chaque clip nouveau ou changé est copié tel quel dans `<KB_DATA_DIR>/raw/selected_library/clipping/` ; K-B ne modifie jamais le coffre. |
| `KB_COLLECT_ONLY` | non | les dossiers des sources que `kb collect` lance, séparés par des virgules (`zotero,clipping`) ; la casse ne compte pas. Sans elle, pas de filtre : chaque source tourne comme avant (Zotero, clips et GH Archive selon leur variable). Une source écartée affiche `<dossier>: skipped (not in KB_COLLECT_ONLY)` ; un nom qui n'est pas un dossier de source, une valeur ou une entrée vide, ou une source choisie sans sa variable (`zotero` sans `KB_ZOTERO_DIR`) : code 2, rien n'est collecté ([docs/specs-collecte.md](docs/specs-collecte.md), « Choisir les sources »). |
| `KB_GITHUB_TOKEN` | non | jeton GitHub en lecture seule ([docs/jeton-github.md](docs/jeton-github.md)). Sans lui, l'API GitHub accepte 60 requêtes par heure au lieu de 5 000. |
| `KB_API_KEY_<CLIENT>` | pour `kb serve` | la clé d'un client de l'API de données (`<CLIENT>` en `A-Z`, `0-9` et `_`, par exemple `KB_API_KEY_TERMINAL`), une variable par client ([docs/specs-api.md](docs/specs-api.md)). |

**Créer la base** (une fois) :

```sh
mkdir -p ~/K-B-data
KB_DATA_DIR=~/K-B-data uv run kb create-db
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
KB_DATA_DIR=~/K-B-data uv run kb collect
```

Avec le jeton rangé dans le `.env` à la racine du dépôt, ignoré par git :
`KB_DATA_DIR=~/K-B-data uv run --env-file .env kb collect`.

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
KB_DATA_DIR=~/K-B-data uv run kb import
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

Les codes de toutes les commandes et leur sens sont listés par `uv run kb --help`.

**Lancer l'API** (la liste des items, en lecture seule, sur la machine ; voir
[docs/specs-api.md](docs/specs-api.md)) :

1. Créer une clé par client, qui identifie le programme qui appelle (le terminal, un script, un
   agent) :

   ```sh
   uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

   et la ranger dans le `.env` : `KB_API_KEY_TERMINAL=<la clé>`.
2. Lancer l'API, qui écoute par défaut sur `http://127.0.0.1:8000`, et seulement sur la machine
   (`KB_DATA_API_HOST`, `KB_DATA_API_PORT` et `KB_DATA_API_ALLOWED_HOSTS` changent l'hôte, le port
   et les hôtes permis : `docs/specs-api.md`, « Règles communes ») :

   ```sh
   KB_DATA_DIR=~/K-B-data uv run --env-file .env kb serve
   ```

3. L'appeler avec la clé :

   ```sh
   curl -H "Authorization: Bearer <la clé>" "http://127.0.0.1:8000/items?kind=paper&limit=5"
   ```

La documentation de l'API est servie sur `http://127.0.0.1:8000/docs`, sans clé ; son OpenAPI est
versionnée dans `docs/api/openapi-donnees.json`, réécrite par `uv run kb openapi` lancé à la
racine du dépôt (ailleurs, sans dossier `docs/api`, il n'écrit rien et sort en code 2). `kb serve` journalise une ligne par requête dans
`<KB_DATA_DIR>/logs/kb-serve.log`, avec le nom du client, jamais sa clé. Code de sortie 2, sans
lancer l'API, si `KB_DATA_DIR` manque, si aucune clé n'est donnée, si un nom de client est vide ou
hors `A-Z`, `0-9` et `_`, si une clé a moins de 32 caractères ou un caractère hors `A-Z`, `a-z`,
`0-9`, `_` et `-` (l'alphabet de `token_urlsafe`), ou si deux clients ont la même clé :
le message nomme la variable, jamais sa valeur. Code 2 aussi si l'hôte n'est pas une adresse IPv4,
si le port n'est pas un entier de 1 à 65535, si la liste des hôtes permis est vide ou contient une
entrée vide, une entrée avec `*` ou une entrée hors nom en minuscules, ou si `KB_LOG_TO_FILE` n'est
ni `true` ni `false` (`false` : journal sur la sortie d'erreur seule) ; le message nomme la
variable et cite la valeur refusée. Si le port est déjà pris (par exemple par un autre
`kb serve`), uvicorn écrit `address already in use` au journal et `kb serve` sort en code 3.

Limites :

- un client se retire en retirant sa variable, puis en redémarrant `kb serve` : un retrait ne
  prend effet qu'au redémarrage ;
- une variable `KB_API_KEY_*` exportée dans le profil du shell (`~/.zshrc`) reste valide même
  retirée du `.env` : la retirer aussi de là ;
- `uv run --env-file .env kb serve` charge tout le `.env`, donc aussi le jeton GitHub et les
  identifiants Google, dont l'API n'a pas besoin : `kb serve` tourne avec plus de droits que sa
  tâche n'en demande (moindre privilège).

**Lire la base sans l'API** : la base s'ouvre en lecture seule avec `sqlite3`, sans clé ni
serveur :

```sh
sqlite3 -readonly ~/K-B-data/k-b.sqlite "SELECT kind, count(*) FROM item GROUP BY kind"
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
