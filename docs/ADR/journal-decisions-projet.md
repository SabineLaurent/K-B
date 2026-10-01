# Journal de décisions — K-B

Produit, architecture, conception : ce qui a été décidé, pourquoi, et les options écartées. La
méthode de travail n'y entre pas : elle vit dans les règles du dépôt.

## 2026-09-29

- **Périmètre.**
  - v0 : pipeline de veille (collecte → fusion → base → API) et fiches de veille.
  - v1 : wiki de savoir à la Karpathy.
  - Plus tard : RAG, fiches rédigées par LLM, MCP, tableau de bord.
- **Deux wikis.**
  - *Veille* : fiches figées, une par question récurrente, tous les 3 jours
    (`wiki/veille/<question>/AAAA-MM-JJ.md`). Requête déterministe via l'API et gabarit, sans
    LLM ni RAG.
  - *Savoir* : pages vivantes, alimentées par `raw/manual/` et par les PDF retenus dans Zotero.
- **Données hors du dépôt de code** (ex. `~/K-B-data/` : `raw/automation/`, `raw/manual/`, base,
  `wiki/`), qui sert aussi de coffre Obsidian. Pourquoi : ne jamais publier de données collectées.
- **Sources de la v0**, une par type de source exigé par la certif, au minimum :

  | Source | Type |
  |---|---|
  | API GitHub, API arXiv | service web |
  | Catalogue CISA KEV (CSV), Web Clipper (`.md`) | fichier |
  | tldr.tech | scraping |
  | Zotero | base de données |
  | GH Archive sur BigQuery | big data |

  - Le scraper TLDR est repris de `brief09_assistant-veille-tech`, relu comme un dépôt tiers
    avant d'être repris. Le `robots.txt` de tldr.tech l'autorise.
  - Le catalogue CISA KEV (vulnérabilités activement exploitées, CSV public, sans clé) a été ajouté
    parce qu'un jury pourrait voir un `.md` comme un document plutôt qu'un fichier de données. Il
    sert aussi un vrai besoin : croiser les failles exploitées avec l'outillage suivi.
  - Zotero : Sabine enregistre ses papiers avec le connecteur et les lit dans Zotero. K-B lit une
    copie de `zotero.sqlite` (papiers, surlignages). Les surlignages alimentent un bloc « Mes
    surlignages » dans les fiches.
- **Sources écartées.**
  - Gmail : TLDR le remplace, et on évite l'OAuth et des mails personnels à traiter.
  - Flux RSS des éditeurs, scraping d'Anthropic : doublons.
  - Historique Brave, favoris Firefox : les favoris faisaient doublon avec le Clipper.
- **BigQuery.**
  - Pourquoi : l'API GitHub ne peut pas repérer les dépôts qui montent. Sa recherche s'arrête à
    1 000 résultats et trie par total d'étoiles, et `/events` est plafonné à 300 événements.
  - Bac à sable, **sans compte de facturation rattaché** : au-delà d'1 To par mois, la requête
    est refusée, pas facturée.
  - Chaque requête est vérifiée par `dry_run` et plafonnée par `maximum_bytes_billed`.

## 2026-09-30

### Collecte

- **Le brut de chaque source est stocké complet et intact ; le filtre se fait à la lecture.**
  Chaque collecte écrit dans `raw/automation/<source>/` ce que la source a publié, sans le
  filtrer ni le modifier. La sélection des nouveautés (pour CISA KEV : `dateAdded` depuis la
  dernière collecte) se fait quand on lit ce brut, jamais quand on l'écrit. Pourquoi : pouvoir
  rejouer le traitement sur le brut. Cela prolonge l'immuabilité de `raw/`, retenue lors de la
  revue de l'existant. Option écartée : filtrer à l'écriture. Le brut serait plus petit, mais on
  ne pourrait plus rejouer le traitement ; et si le filtre est faux, ce qu'il écarte est perdu.
  Pour CISA KEV, le catalogue est cumulatif : on perdrait surtout son état à la date de la
  collecte (les lignes modifiées ou retirées depuis). Pour une source non cumulative
  (événements GitHub, TLDR), la perte serait définitive. Limite assumée :
  chaque collecte où le catalogue a changé stocke le catalogue entier (environ 1 Mo en 2026).
  Une collecte sans changement n'écrit rien (réponse HTTP 304). — PR de #23

### Sources suivies et accès

- **arXiv : une seule catégorie pour démarrer, `cs.CR`.** Pourquoi : démarrer avec le minimum et
  grossir à l'usage (choix de Sabine). `cs.CR` couvre la sécurité, en lien avec OWASP et CISA KEV.
  Options écartées pour l'instant : `cs.SE` et `cs.IR` (proposées, remises à plus tard), `cs.CL`
  (environ 940 papiers par semaine), `cs.AI` et `cs.LG` (plus de 2 000 chacune : trop de bruit).
  Six mots-clés de départ sont notés dans `docs/sources.md` ; leur usage reste ouvert (voir
  plus bas). — PR de #24
- **Dépôts GitHub suivis pour démarrer : `langchain-ai/langchain`, `langchain-ai/langgraph`,
  `run-llama/llama_index` et `anthropics/claude-code`.** Pourquoi : démarrer petit (choix de
  Sabine). Dix autres dépôts proposés sont gardés sous le coude dans `docs/sources.md` :
  l'outillage de K-B (uv, pytest, FastAPI, Pydantic, SDK Anthropic), le reste de l'écosystème
  LLM, le top 10 LLM d'OWASP et Obsidian. Écartés : les dépôts qui ne publient que des tags (`python/cpython`,
  `OWASP/Top10`), car l'API des releases n'y trouve rien. Limite assumée :
  `langchain-ai/langchain` est un monorepo qui publie une release par paquet, donc bruyant.
  — PR de #24
- **Jeton GitHub *fine-grained*, accès aux dépôts publics seulement, sans aucune permission.**
  Pourquoi : moindre privilège. La collecte ne lit que des données publiques (releases,
  advisories, recherche de dépôts), qui ne demandent aucune permission ; le jeton ne sert qu'à
  relever le quota de 60 à 5 000 requêtes par heure (vérifié le 2026-09-30). S'il fuite, il ne
  lit aucun dépôt privé et n'écrit nulle part. Option écartée : un jeton *classic*, dont les
  scopes sont larges (`repo` ouvre tous les dépôts privés en écriture). Expiration fixée à la
  création. — PR de #24
- **Le jeton vit dans `KB_GITHUB_TOKEN`, et non `GITHUB_TOKEN`.** Pourquoi : la CLI `gh` lit
  `GITHUB_TOKEN` en priorité sur la connexion de l'utilisatrice ; ce jeton sans permission aurait
  alors bloqué toute écriture par `gh` (PR, issues). — PR de #24
- **Le jeton est rangé dans le `.env` du dépôt, ignoré par git, et chargé au lancement.** Choix de
  Sabine. Options écartées : le trousseau macOS avec un `export` dans `~/.zshrc`, qui met le jeton
  dans tous les processus de tous les terminaux ; le trousseau lu commande par commande, plus
  strict mais plus lourd. Limite assumée : le jeton est en clair sur le disque, acceptable pour
  un jeton en lecture publique seule, sans permission et qui expire. — PR de #24

## 2026-10-01

### Sources suivies et accès

- **BigQuery : un compte de service `k-b-collecte` au seul rôle BigQuery Job User, dans un projet
  bac à sable sans facturation (`k-b-bigquery`).** Sa clé JSON est rangée hors du dépôt, dans un
  dossier personnel non synchronisé, lisible par sa seule propriétaire, et désignée par
  `GOOGLE_APPLICATION_CREDENTIALS` dans le `.env`. Choix de Sabine, sur recommandation. Pourquoi :
  moindre privilège, puisque le compte ne peut que lancer des requêtes dans ce projet, et GH
  Archive est public. Le critère de #36 veut aussi des identifiants en variable
  d'environnement. Options écartées : les identifiants `gcloud` de l'utilisatrice, qui ouvrent
  tout son compte Google, ne passent pas par une variable et demandent d'installer le SDK ; la
  fédération d'identité de charge de travail, sans objet tant que le pipeline tourne sur un Mac
  sans fournisseur d'identité, à reconsidérer si la collecte passe en CI. Limite assumée : la clé
  n'expire pas. Si elle fuit, le pire est la consommation du quota gratuit, car rien n'est
  facturable ; Google désactive aussi les clés détectées dans un dépôt public. Vérifié le
  2026-10-01 : un `dry_run` sur une journée de GH Archive lit 16,5 Mo. — PR de #36

### Collecte

- **arXiv : les mots-clés filtrent à la requête, pas à la lecture.** Exception assumée à la règle
  du 2026-09-30 (brut stocké intact, filtre à la lecture). Choix de Sabine. Pourquoi : la veille
  arXiv cible la sécurité des LLM, des agents et de l'IA en général, et les papiers qui documentent
  une attaque et son déroulé. Elle ne vise pas une liste exhaustive, qui n'aurait pas d'intérêt et
  noierait l'information. Mesuré sur la semaine du 2026-09-24 au 2026-10-01 : 45 papiers en
  `cs.CR` avec les 6 mots-clés de départ, contre 358 sans. Option écartée : collecter tout `cs.CR` et filtrer
  à la lecture, cohérent avec la règle mais hors du besoin. Limite assumée : un papier que les
  mots-clés manquent n'est jamais collecté, et un mot-clé ajouté ne s'applique pas aux semaines
  passées. — PR de #6
- **Zotero : le brut est la copie entière de `zotero.sqlite`, pas le résultat d'une requête.**
  Provisoire : à revoir dans #15, une fois la taille et le schéma de la base connus. Choix de
  Sabine. Pourquoi : la règle du brut intact (2026-09-30) s'applique, et la requête peut
  changer et se rejouer. Option écartée : n'écrire que le résultat de la requête, plus léger et
  qui ne stocke pas toute la bibliothèque. Limite assumée : chaque collecte où la base a changé
  stocke une copie entière ; elle contient toute la bibliothèque, hors du dépôt de code. — PR de #6
- **GitHub : le login de l'auteur d'une release ou d'une alerte n'entre pas dans les items.** Choix
  de Sabine. Pourquoi : la veille n'en a pas besoin, et c'est une donnée personnelle
  (minimisation, RGPD art. 5.1.c). Il reste dans le brut, intact. — PR de #6
- **arXiv ne suit que la sécurité de l'IA : papiers classés à la fois en `cs.CR` et `cs.AI`, avec
  8 mots-clés** (`prompt injection`, `jailbreak`, `red teaming`, `adversarial attack`,
  `backdoor`, `poisoning`, `membership inference`, `agent security`). Remplace le choix du
  2026-09-30 (`cs.CR` seule, 6 mots-clés de départ). Choix de Sabine. Pourquoi : le croisement garantit le sujet
  par le classement de l'auteur, et les mots-clés gardent un flux lisible, environ 20 papiers par
  semaine (19 à 22 en moyenne sur septembre et avril 2026). Options écartées, mesurées sur ces
  deux mois : `cs.CR` avec les mots-clés seuls (38 à 52 par semaine) ; les mots-clés sur `cs.CR`,
  `cs.CL`, `cs.AI` et `cs.LG` (63 à 75) ; une liste de mots-clés par catégorie, même volume pour
  trois listes de plus ; les croisements de `cs.CR` avec `cs.AI`, `cs.CL` et `cs.LG` sans mots-clés
  (99 à 113), trop pour être lus. Retirés : `LLM security` et `agent hijacking`, qui ne ramenaient
  presque rien. Limite assumée : un papier au vocabulaire nouveau, ou classé en `cs.CR` avec
  `cs.CL` ou `cs.LG` seulement, n'est pas collecté. — PR de #6
- **arXiv ne suit pas les LLM, les agents et les nouvelles architectures en général ; Hugging Face
  *Daily Papers*, une sélection générale de papiers d'IA, est gardé pour plus tard.** Choix de
  Sabine. Pourquoi : `cs.CL` et `cs.AI` publient 590 à 1 350 papiers par semaine, et aucun mot-clé
  ne rend ce flux lisible ; il faut une sélection faite par d'autres. En v0, l'édition AI de TLDR
  (#13) donne l'actualité générale de l'IA. Hugging Face, une sélection votée par la communauté
  (131 à 165 papiers par semaine, dont environ 60 % parlent de LLM ou d'agents et le reste surtout
  de vision ; on garderait les 10 plus votés), ajouterait une source à dix jours du jalon ; elle
  est notée « pour plus tard » dans `docs/sources.md`. Limite assumée : en v0, aucune source ne
  suit les papiers de ce sujet. — PR de #6

## Décisions encore ouvertes

- **Zotero : garder la copie entière comme brut ?** Décidé à titre provisoire le 2026-10-01 ; à
  revoir dans #15 selon la taille de `zotero.sqlite` et son schéma.
