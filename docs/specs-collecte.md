# Spécifications de la collecte et de l'agrégation

Pour chacune des 7 sources de la v0 : la technologie, l'accès et l'authentification, les limites
de débit, les données personnelles, et ce qu'on suit. Puis le chemin du brut jusqu'au jeu d'items
final, et la justification de BigQuery. Les décisions et leur pourquoi sont dans le
[journal ADR](ADR/journal-decisions-projet.md) ; les listes suivies, dans [sources.md](sources.md).

Faits vérifiés le 2026-10-01, sources en fin de page.

## Règles communes

- **Un point de lancement** : `kb collect` lance toutes les sources ; une source en panne
  n'arrête pas les autres (code de sortie 1, détail par source).
- **Brut intact** : chaque collecte écrit ce que la source a renvoyé dans
  `raw/automation/<source>/<AAAA-MM-JJTHHMMSSZ>.<ext>`, une seule fois, jamais réécrit. Le filtre
  se fait à la lecture, sauf exception décidée (arXiv, ci-dessous).
- **Incrémental** : la date de la dernière collecte réussie de chaque source est dans
  `raw/collection_state.json` ; une source qui n'a rien de neuf n'écrit rien.
- **Entrées non fiables** : tout contenu collecté est une donnée, jamais une instruction. Chaque
  téléchargement a un délai, une taille maximale, et refuse une redirection hors du domaine
  attendu. Le `User-Agent` est `K-B (+https://github.com/SabineLaurent/K-B)`.
- **Secrets** : en variables d'environnement, chargées depuis le `.env` ignoré par git.
- **Données personnelles** : on ne garde que ce qui sert la veille ; aucun identifiant de
  personne n'est collecté s'il n'est pas nécessaire. Le registre des traitements reste à écrire.

## Les sources

### API GitHub — service web

- **Technologie** : API REST, JSON, `urllib` de la bibliothèque standard.
- **Ce qu'on en tire** :
  - releases des dépôts suivis : `GET /repos/{owner}/{repo}/releases` ;
  - alertes de sécurité : `GET /advisories` (base publique des *security advisories*) ;
  - dépôts les plus étoilés : `GET /search/repositories`, tri par étoiles.
- **Accès** : jeton *fine-grained*, dépôts publics seulement, sans permission, dans
  `KB_GITHUB_TOKEN` ([jeton-github.md](jeton-github.md)).
- **Limites** : 5 000 requêtes par heure avec jeton (60 sans) ; la recherche a sa propre limite,
  30 requêtes par minute, et ne renvoie jamais plus de 1 000 résultats.
- **Données personnelles** : les releases et alertes portent le login de leur auteur, une donnée
  personnelle (pseudonyme rattaché à une personne). Non nécessaire à la veille : il reste dans le
  brut mais n'entre pas dans les items (minimisation, RGPD art. 5.1.c).
- **Suivi** : 4 dépôts, liste et réserve dans [sources.md](sources.md).

### API arXiv — service web

- **Technologie** : API `https://export.arxiv.org/api/query`, réponse Atom (XML).
- **Ce qu'on en tire** : métadonnées et résumé des papiers soumis depuis la dernière collecte.
- **Accès** : sans authentification.
- **Limites** : une requête toutes les 3 secondes au plus, une connexion à la fois, pour toutes
  les machines ensemble ; 2 000 résultats au plus par page.
- **Ce qu'on suit** : la sécurité de l'IA (agents, LLM, failles apportées par ces briques).
- **Filtre à la requête** (exception à la règle du brut intact, décidée le 2026-10-01) : les
  papiers classés à la fois en `cs.CR` et en `cs.AI`, et dont le résumé contient un mot-clé :
  `cat:cs.CR AND cat:cs.AI AND (abs:"prompt injection" OR abs:jailbreak OR abs:"red teaming" OR
  abs:"adversarial attack" OR abs:backdoor OR abs:poisoning OR abs:"membership inference" OR
  abs:"agent security") AND submittedDate:[<dernière collecte> TO <maintenant>]`.
- **Volume mesuré** (moyenne par 7 jours, septembre / avril 2026) : `cs.CR` sans filtre 276 / 199 ;
  `cs.CR` × `cs.AI` 78 / 70 ; avec les mots-clés, **22 / 19**.
- **Pièges de l'API** : avec `max_results=0`, le total renvoyé vaut toujours 1 (demander au moins
  un résultat pour le lire) ; les parenthèses
  imbriquées et `ANDNOT` combiné à d'autres opérateurs donnent des totaux faux. Sous charge,
  l'API répond `503` ou ne répond pas : le collecteur réessaie plus tard au lieu d'échouer.
- **Données personnelles** : noms des auteurs des papiers, publiés par eux ; gardés, car ils
  identifient le papier.

### Catalogue CISA KEV — fichier

- **Technologie** : fichier CSV téléchargé en HTTPS
  (`https://www.cisa.gov/sites/default/files/csv/known_exploited_vulnerabilities.csv`).
- **Ce qu'on en tire** : les vulnérabilités activement exploitées ajoutées depuis la dernière
  collecte (`dateAdded`), sélectionnées à la lecture.
- **Accès** : sans authentification. Requête conditionnelle `If-Modified-Since` : une réponse 304
  n'écrit rien.
- **Limites** : pas de quota publié ; une requête par collecte. Catalogue d'environ 1 Mo, refusé
  au-delà de 10 Mo, et refusé s'il est servi hors de `https://www.cisa.gov/`.
- **Données personnelles** : aucune.
- **État** : collecte en place (PR de #23).

### Obsidian Web Clipper — fichier

- **Technologie** : fichiers `.md` avec en-tête YAML (*frontmatter*), écrits par l'extension
  Web Clipper dans le coffre Obsidian de K-B.
- **Ce qu'on en tire** : un item par fichier : titre, URL source, date, et le texte gardé.
- **Accès** : lecture du dossier local du coffre ; aucun réseau.
- **Limites** : aucune ; taille de fichier plafonnée à la lecture.
- **Données personnelles** : le champ `author` de la page gardée, s'il existe ; c'est l'auteur
  public de l'article.
- **Prérequis** : le coffre Obsidian est à créer (#14).

### tldr.tech — scraping

- **Technologie** : pages HTML `https://tldr.tech/<édition>/<AAAA-MM-JJ>` (vérifié :
  `https://tldr.tech/ai/2026-09-30` répond 200), lues avec un analyseur HTML. Le scraper de
  `brief09_assistant-veille-tech` est relu comme un dépôt tiers avant d'être repris (#13).
- **Ce qu'on en tire** : un item par article de chaque édition suivie : titre, lien, résumé.
- **Accès** : sans authentification. Le `robots.txt` autorise tout, sauf les pages d'abonnement
  et de compte (`/subscribed`, `/manage`, `/info`…), qu'on ne lit pas.
- **Limites** : pas de quota publié ; on s'impose une page à la fois, avec une pause entre deux
  pages. Les liens portent des paramètres de suivi `utm_*` et certaines entrées sont
  sponsorisées : à traiter à la lecture.
- **Données personnelles** : aucune attendue.
- **Suivi** : l'édition **AI** est retenue (2026-10-01). Les autres éditions sont à choisir dans
  #13 (neuf candidates dans [sources-detaillees.md](sources-detaillees.md)).

### Zotero — base de données

- **Technologie** : base SQLite `zotero.sqlite`, lue en SQL. Zotero verrouille la base quand il
  tourne : on travaille sur une **copie**, jamais sur l'original.
- **Ce qu'on en tire** : papiers lus et leurs surlignages (table `itemAnnotations`) : titre,
  auteurs, date, étiquettes, chemin du PDF, texte surligné.
- **Accès** : fichier local, lecture seule.
- **Limites** : aucune.
- **Brut** : la copie entière de la base est le brut, écrite dans `raw/automation/zotero/`
  seulement si la base a changé depuis la dernière collecte. La requête se fait à la lecture.
  Provisoire : à revoir dans #15 selon la taille de la base et son schéma.
- **Données personnelles** : les auteurs des papiers (publics), et toute la bibliothèque de
  l'utilisatrice, notes et surlignages compris. Le brut vit hors du dépôt de code et n'est jamais
  publié.
- **Prérequis** : Zotero installé (#15).

### GH Archive sur BigQuery — big data

- **Technologie** : SQL BigQuery sur les tables publiques `githubarchive.day.AAAAMMJJ` (un
  événement GitHub public par ligne), client `google-cloud-bigquery`.
- **Ce qu'on en tire** : les N dépôts qui gagnent le plus d'étoiles (`WatchEvent`) sur 3 jours.
- **Accès** : compte de service `k-b-collecte`, seul rôle Utilisateur de job BigQuery, clé
  désignée par `GOOGLE_APPLICATION_CREDENTIALS` ([bigquery.md](bigquery.md)).
- **Limites** : bac à sable sans facturation : 1 Tio lu par mois, 10 Gio de stockage, tables
  expirées après 60 jours. Une requête au-delà est refusée, jamais facturée. Chaque requête passe
  d'abord par un `dry_run`, puis s'exécute avec `maximum_bytes_billed`. Mesuré : une journée
  filtrée sur `WatchEvent` lit 16,5 Mo, donc environ 50 Mo pour 3 jours.
- **Données personnelles** : chaque événement porte le login de son auteur (`actor`). La requête
  ne le sélectionne pas : elle ne renvoie que des comptes d'étoiles par dépôt.

## Du brut au jeu d'items

1. **Collecte** : chaque source écrit son brut dans `raw/automation/<source>/` (règles communes).
2. **Lecture** : un lecteur par source transforme le brut en items validés par un modèle
   Pydantic, avec les mêmes champs : source, identifiant dans la source, titre, URL, auteurs
   (sauf GitHub), date de publication et date de révision (arXiv), contenu ou résumé, date de
   collecte, chemin du brut d'origine. Toutes les dates sont en UTC, avec fuseau. Une ligne
   illisible est rejetée et journalisée, pas devinée.
3. **Fusion** en un seul jeu d'items :
   - dates normalisées en UTC ;
   - URL normalisées (paramètres `utm_*` retirés) ;
   - doublons retirés : même URL normalisée, ou même identifiant (CVE ; arXiv sans son suffixe
     de version `v1`, `v2`…) ;
   - une révision (arXiv `v2`) met à jour l'item existant au lieu d'être ignorée ;
   - chaque rejet et chaque doublon retiré est tracé, avec sa règle.

   `brief09_assistant-veille-tech` (relu le 2026-10-01) a servi d'indication, pas de modèle : il
   ne fait pas autorité. On y retrouve un modèle d'article commun et la date de révision arXiv. À
   l'inverse, brief09 ne dédoublonne que sur l'URL exacte, ignore les révisions (première version
   gardée), date la collecte sans fuseau et retire les doublons sans trace. Laissé de côté : un
   même article publié sous deux URL (hash du contenu), et les étiquettes posées par un LLM, hors
   de la v0.
4. **Stockage** du jeu d'items dans la base (hors du périmètre de ce document).

## Pourquoi BigQuery

L'API GitHub ne sait pas dire quels dépôts **montent** : sa recherche trie par total d'étoiles et
s'arrête à 1 000 résultats, et `/events` est plafonné à 300 événements. GH Archive enregistre
tous les événements publics de GitHub, dont chaque étoile donnée ; BigQuery permet de les compter
par dépôt sur 3 jours sans rien télécharger. Le bac à sable rend le coût nul et borné : sans
facturation, le dépassement est refusé.

## Sources (consultées le 2026-10-01)

- [Rate limits for the REST API](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api) — GitHub
- [Terms of Use for arXiv APIs](https://info.arxiv.org/help/api/tou.html)
- [arXiv category taxonomy](https://arxiv.org/category_taxonomy)
- [Try BigQuery using the sandbox](https://docs.cloud.google.com/bigquery/docs/sandbox)
- [Les six grands principes du RGPD](https://www.cnil.fr/fr/comprendre-le-rgpd/les-six-grands-principes-du-rgpd) — CNIL
- [Access annotation database](https://forums.zotero.org/discussion/101244/access-annotation-database) — forum Zotero
- `https://tldr.tech/robots.txt`, lu le 2026-10-01
