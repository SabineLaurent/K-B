# Journal de décisions — K-B

Produit, architecture, conception : ce qui a été décidé, pourquoi, et les options écartées. La
méthode de travail n'y entre pas : elle vit dans les règles du dépôt.

## 2026-09-29

- **Périmètre.**
  - v0 : pipeline de veille (collecte → fusion → base → API) et fiches de veille.
  - v1 : wiki de savoir à la Karpathy.
  - Plus tard : RAG, fiches rédigées par LLM, MCP, tableau de bord.
    **Levée le 2026-10-15** pour les fiches de veille, que l'API IA rédige par sujet (« POC du 25/10 »,
    décision 4).
- **Deux wikis.**
  - *Veille* : fiches figées, une par question récurrente, tous les 3 jours
    (`wiki/veille/<question>/AAAA-MM-JJ.md`). Requête déterministe via l'API et gabarit, sans
    LLM ni RAG. **Levée le 2026-10-15** : les fiches de veille sont faites par l'API IA, par
    sujet (« POC du 25/10 », décision 4).
  - *Savoir* : pages vivantes, alimentées par `raw/manual/` et par les PDF retenus dans Zotero.
- **Données hors du dépôt de code** (ex. `~/K-B-data/` : `raw/automation/`, `raw/manual/`, base,
  `wiki/`), qui sert aussi de coffre Obsidian. Pourquoi : ne jamais publier de données collectées.
  **Exception provisoire le 2026-10-17** (« Coffre Obsidian : une copie dans un dossier ignoré du
  dépôt »).
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
  - Bac à sable, **sans compte de facturation rattaché** : au-delà d'1 Tio par mois, la requête
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

## 2026-10-02

### Base des items

- **SGBD : SQLite, un fichier dans le dossier de données, lu par le module `sqlite3` de la
  bibliothèque standard.** Choix de Sabine, « pour le moment ». Pourquoi : un utilisateur, un seul
  écrivain par semaine (le pipeline), quelques milliers d'items par an ; aucun serveur à
  installer, une installation qu'un tiers rejoue sans effort ; en mode WAL, l'API lit pendant
  que le pipeline écrit. Option écartée : PostgreSQL, dont les rôles SQL (un rôle en lecture
  seule pour l'API) et les écritures parallèles ne servent pas un outil local à un utilisateur,
  au prix d'un serveur à faire tourner et sécuriser et d'un pilote à ajouter. Limite assumée :
  pas de comptes dans la base ; le moindre privilège passe par l'ouverture en lecture seule et
  les droits du fichier. Une migration vers PostgreSQL reste possible (SQL standard, hors
  `STRICT` et `PRAGMA`). **Révisée le 2026-10-15** : SQLite au 25/10, PostgreSQL au 08/11
  (« POC du 25/10 », décision 2). — PR de #7
- **Schémas MCD et MLD en Mermaid dans le dépôt, MPD en script SQL.** Choix de Sabine. Pourquoi :
  GitHub affiche le Mermaid sans rien installer, et le texte se relit dans une PR. Le dossier
  écrit de la certif E1 pourra utiliser d'autres outils (Looping pour le MCD, draw.io pour le
  MLD), à redéfinir à sa rédaction. Option écartée : Mocodo, outil Merise qui dérive MLD et SQL
  du MCD, mais produit un SVG à régénérer et une dérivation automatique moins défendable à
  l'oral que faite à la main. Limite assumée : le MCD est dessiné avec un `flowchart`, qui
  imite la notation Merise sans la vérifier. — PR de #7
- **Le script du schéma vit dans `src/k_b/database/schema.sql`, paquet qui recevra aussi le code
  de connexion (#20).** Choix de Sabine : le schéma et le code qui l'ouvre restent ensemble.
  Option écartée : `docs/`, d'où une copie du schéma finirait par diverger du code. Les données
  de référence (les 7 sources) sont dans un fichier séparé, `seed_sources.sql`, qui se rejoue
  sans risque. Choix de Sabine : la structure et les valeurs de départ changent pour des
  raisons différentes. Limite assumée : les deux scripts s'exécutent toujours ensemble, dans
  l'ordre, car un item exige sa source. — PR de #7
- **ITEM porte le socle commun ; les champs propres à une nature d'item vont dans des sous-types
  (spécialisation Merise) : DÉPÔT (`nom_dépôt`) et VULNÉRABILITÉ (`cve`).** Choix de Sabine, sur
  recommandation. Pourquoi : la fusion et « quoi de neuf » ont besoin d'un socle commun à toutes
  les sources, sans perdre ce qui fait l'intérêt de certaines (le CVE sert au dédoublonnage).
  Un champ n'entre que si une question de veille le filtre, le trie ou l'affiche ; chaque issue
  de source ajoute ensuite les siens dans sa PR (CISA KEV : dans #20). Options écartées : une
  colonne JSON « extra » (défaut de brief09 : contraire à la 1re forme normale, non typée) ; une
  table attribut/valeur (rien de typé, requêtes illisibles) ; le socle seul (perd le CVE) ; des
  colonnes facultatives dans ITEM, plus simples pour trois champs, mais qui se remplissent de
  `NULL` à mesure que les sources ajoutent les leurs. Limite assumée : l'exclusivité des
  sous-types n'est pas portée par SQL, le code de fusion la vérifie. — PR de #7
- **Une table COLLECTE (date et chemin du brut) plutôt que ces deux champs dans ITEM.** Pourquoi :
  le chemin du brut détermine la date de collecte (horodatage dans le nom) ; les garder dans
  ITEM casserait la 3e forme normale. Option écartée : les deux champs dans ITEM, comme le
  modèle Pydantic de `specs-collecte.md`. — PR de #7
- **Les auteurs sont une entité AUTEUR liée aux items, pas une liste dans ITEM.** Pourquoi : 1re
  forme normale, et une purge RGPD qui devient un `DELETE` ciblé (#8). Option écartée : un champ
  texte « auteurs » (brief09). Limite assumée : deux homonymes sont confondus. — PR de #7
- **Les surlignages Zotero entrent dans la base (SURLIGNAGE).** Choix de Sabine, sur
  recommandation. Pourquoi : c'est la valeur propre de Zotero, et les fiches prévoient un bloc
  « Mes surlignages » (2026-09-29). — PR de #7
- **`url` est obligatoire et unique pour tout item.** CISA KEV prend la fiche NVD construite
  depuis le CVE (`https://nvd.nist.gov/vuln/detail/<CVE>`) ; Zotero, l'URL arXiv du papier ; Web
  Clipper, sa propriété `source`. Choix de Sabine. Pourquoi : l'unicité porte dans la base le
  dédoublonnage par URL de la fusion (deuxième contrôle si le code laisse passer un doublon).
  Le CSV CISA n'a pas de colonne URL : ses liens sont dans `notes`, sans place fixe ; écarté
  d'en extraire le premier, fragile. En v0, Zotero ne contient que des papiers arXiv ; écarté le
  repli sur le DOI, sans usage. Limite assumée : un document sans URL est rejeté ; si Zotero
  reçoit un jour des papiers hors arXiv, `url` redeviendra facultative. — PR de #7
- **Une date absente reste vide : `date_publication` est facultative et n'est jamais remplacée
  par une autre date. Une date d'ajout (`date_ajout`) est gardée à part pour Web Clipper
  (`created`) et Zotero (`dateAdded`).** Choix de Sabine : « l'info n'est pas la même ». Option
  écartée : prendre `created` quand `published` manque. Conséquence : « quoi de neuf » ne peut
  pas filtrer sur la seule date de publication ; la règle se décide dans #21. — PR de #7
- **Un dépôt est un seul item ; chaque fenêtre de 3 jours où il monte ajoute une MESURE (étoiles
  gagnées), à identifiant relatif au dépôt.** Choix de Sabine, sur recommandation. Remplace, avant
  toute PR, le choix pris plus tôt dans la session d'un item par dépôt et par fenêtre, qui
  contredisait l'unicité de `url` (même page de dépôt pour deux fenêtres). Pourquoi : on garde
  l'historique de la montée et l'URL unique, et un même dépôt vu par la recherche GitHub et par
  GH Archive devient un seul item. Options écartées : retirer l'unicité de `url` (perd le
  deuxième contrôle) ; un index unique partiel qui exempte GH Archive (exception cachée dans le
  schéma). La date de publication d'un dépôt reste vide : ce n'est pas une publication. — PR de #7
- **Les documents de `raw/manual/` n'entrent pas dans la base en v0.** Choix de Sabine. Pourquoi :
  ils alimentent le wiki de savoir, qui est la v1. Le schéma les accueillera par une ligne de
  SOURCE et un chemin de brut sous `raw/manual/`. — PR de #7

### Données personnelles

- **Le registre des traitements est tenu, bien que K-B relève probablement de l'exemption des
  activités strictement personnelles (RGPD art. 2.2.c).** Choix de Sabine. Pourquoi : le
  registre et les procédures de tri sont trois critères d'évaluation d'E1 (référentiel, C4), et
  l'exemption tomberait si l'outil servait un usage professionnel ou d'autres personnes. Une
  donnée publique (nom d'auteur, login) reste une donnée personnelle. Option écartée : retirer
  registre et purge de la v0, ce que le référentiel ne permet pas. — PR de #8
- **Deux fiches de registre, par finalité : la veille technologique (données de tiers) et la
  bibliothèque de lecture de l'utilisatrice (ses propres données Zotero et Obsidian).** Choix de
  Sabine, sur recommandation. Pourquoi : la CNIL demande une fiche par finalité, pas par source ;
  les personnes, les données et les durées diffèrent entre les deux. Option écartée : une seule
  fiche, qui mêlerait données de tiers et données de l'utilisatrice. — PR de #8

### Collecte

- **Une réponse d'API = un brut, octet pour octet ; une source par dépôt GitHub suivi.** Choix de
  Sabine. Pourquoi : c'est la règle du brut intact (2026-09-30) appliquée aux API qui demandent
  un appel par objet suivi. Une panne d'un dépôt n'arrête pas les autres, et seul un dépôt qui a
  du neuf écrit un fichier. `collect.py` n'a pas changé : chaque dépôt est une instance de source,
  avec sa date de dernière collecte. Options écartées : un JSON commun aux dépôts, qui réécrit
  les octets reçus, bloque tous les dépôts sur une seule panne et se réécrit dès qu'un dépôt a du
  neuf ; des sous-dossiers `github_releases/<owner>/<repo>/`, qui obligent à modifier
  `collect.py` pour un gain seulement visuel. Limite assumée : seule la première page (100
  releases) est lue. Un avertissement est journalisé quand elle est entièrement plus récente que
  la dernière collecte, signe qu'il faut gérer la pagination. L'en-tête `Link: rel="next"` a été
  écarté comme signal, car il est toujours présent. — PR de #10
- **Un `User-Agent` commun à toutes les sources : `K-B (+https://github.com/SabineLaurent)`,
  dans `k_b/user_agent.py`.** Choix de Sabine. Pourquoi : GitHub refuse une requête sans
  `User-Agent`, et un site sans compte n'a que cet en-tête pour savoir qui l'interroge et qui
  prévenir. Le profil est une page publique. Options écartées : l'URL du dépôt, qui mène à un 404
  (dépôt privé) et révèle le nom d'un dépôt privé ; `K-B` seul, qui ne dit à personne qui est
  derrière les requêtes. Limite assumée : chaque site interrogé reçoit le login de Sabine. D'où
  la condition posée dans #13 : vérifier le droit de scraper (`robots.txt` et conditions
  d'utilisation) avant tout scraping, puisque la requête identifie Sabine. Remplace la valeur
  `K-B (+https://github.com/SabineLaurent/K-B)` de `specs-collecte.md`. — PR de #10
- **La sécurité des projets de Sabine relève de Dependabot ; K-B ne suit que les alertes des
  paquets publiés par les dépôts de la veille.** Choix de Sabine. Pourquoi : Dependabot lit les
  fichiers de verrouillage de chaque dépôt (`uv.lock`, `pnpm-lock.yaml`), dépendances indirectes
  et GitHub Actions comprises, et propose la correction. K-B le referait moins bien, et il
  faudrait donner au jeton la permission de lire ces alertes, contre le moindre privilège. Les
  deux canaux n'ont pas le même but : corriger ses projets, savoir ce qui arrive aux outils
  suivis. Options écartées : tout l'écosystème `pip` (43 alertes par semaine, recoupe
  Dependabot) ; tous les écosystèmes (plus de 180 par semaine, dont plus de 100 pour npm) ;
  l'écosystème `actions` (déjà couvert par Dependabot pour les actions référencées par version) ;
  `pnpm` (pas utilisé pour le moment). Limites assumées : deux endroits à regarder ; les outils
  installés sur le poste (hors de tout dépôt) n'ont d'alerte que s'ils sont dans la liste suivie.
  — PR de #11
- **Les paquets suivis découlent des dépôts suivis : chaque dépôt déclare son écosystème et ses
  paquets principaux, au même endroit (`tracked_repositories.py`).** Choix de Sabine. Pourquoi :
  une seule liste pilote la veille GitHub ; suivre un nouveau dépôt donne à la fois ses releases
  et ses alertes. Seuls les paquets publiés par le dépôt lui-même (vérifié sur PyPI et npm) et
  encore maintenus entrent : `langchain-community` et `langchain-experimental` sont écartés
  (dépôts archivés), `langchain-classic` aussi (compatibilité avec la v0, non utilisée). Limite
  assumée : la liste se tient à la main ; un monorepo publie des dizaines de paquets
  d'intégration, ajoutés quand ils servent. — PR de #11
- **Alertes : le filtre par paquets se fait dans la requête (`affects=`), et la date suivie est
  celle de la revue par GitHub, pas de la publication.** Exception à la règle du brut intact
  (2026-09-30), comme arXiv : tout l'écosystème npm dépasse 100 alertes par semaine et obligerait
  à paginer. La date de revue : constat de la revue de code, vérifié sur l'API (12 alertes Maven
  sur 100 relues jusqu'à deux semaines après leur publication) ; avec la date de publication, une
  alerte relue après la collecte suivante serait perdue sans avertissement. Correction décidée par
  Sabine. Option écartée : la date de mise à jour (`updated`), qui ramène une alerte à chaque
  modification. Limite assumée : une alerte modifiée après sa revue (gravité, retrait) n'est pas
  recollectée. — PR de #11
- **Dépôts les plus étoilés : le top 100 de tout GitHub, sans filtre par topic, avec un instantané
  écrit à chaque collecte.** Choix de Sabine. Pourquoi : à plus de 116 000 étoiles pour le 100e,
  le classement ne s'achète pas ; mesuré le 2026-10-02, 36 dépôts sur 100 touchent à l'IA et 13
  ont moins d'un an, donc une entrée dans le top est un signal de veille. 100 est le maximum d'une
  page (une requête) et laisse voir un dépôt entrer par le bas du classement. Un classement change
  toujours (les étoiles bougent), d'où l'exception à « une source qui n'a rien de neuf n'écrit
  rien » : chaque instantané est un point de mesure, et les entrées, sorties et montées se
  calculent à la lecture. Options écartées : un filtre par topic (étiquettes libres, sans
  taxonomie ; plus de 14 000 nouveaux dépôts `llm` par mois) ; les dépôts récents les plus
  étoilés (plus exposés aux étoiles achetées) ; n'écrire que si la liste change (on perd
  l'évolution des étoiles) ; couper cette source au profit de #16. Limite assumée : ce
  classement dit ce qui s'est installé au sommet, pas ce qui monte, rôle de #16 (BigQuery).
  — PR de #11
- **arXiv : la fenêtre `submittedDate` part de 7 jours avant la dernière collecte réussie (la
  première collecte remonte au 01/05/2026, début de la formation).** C'est la correction du bug de watermark de
  brief09. Proposé par Claude, validé par Sabine. Pourquoi : `submittedDate` est le seul filtre de
  date de l'API, et un papier n'y apparaît qu'à son annonce, jusqu'à 3,5 jours après sa
  soumission (jeudi 14 h → dimanche 20 h, heure de New York), plus les jours fériés ; une fenêtre
  qui partirait de la dernière collecte perdrait ces papiers pour toujours. Option écartée : le
  tri par `lastUpdatedDate` arrêté au premier papier déjà vu (brief09), cause de la perte. Les
  bruts se recouvrent donc d'environ 7 jours, et une source sans rien de neuf écrit quand même ;
  la fusion dédoublonne par identifiant arXiv. Limites assumées : un papier retenu en modération
  plus de 7 jours est manqué ; la révision (`v2`) d'un papier soumis avant la fenêtre n'est pas
  collectée. Date de la première collecte : choix de Sabine, pour que la base et la liste de
  lecture démarrent avec un vrai passé (488 papiers, 1,2 Mo, mesurés le 2026-10-02 : une page
  suffit). Options écartées : les 7 derniers jours (une vingtaine de papiers, trop peu pour roder
  la suite) ; une profondeur relative, comme 60 jours (contenu qui dépend du jour du lancement).
  Limite assumée : si l'état des collectes est effacé dans quelques années, la fenêtre dépassera
  2 000 papiers et la collecte échouera, avec un message. — PR de #12
- **arXiv : une seule page de 2 000 résultats (le maximum de l'API) ; si `totalResults` dépasse ce
  que la page contient, la collecte échoue et sa date n'avance pas.** Proposé par Claude, validé
  par Sabine. Pourquoi : environ 40 papiers par fenêtre de 7 jours et plus ; échouer garde la
  fenêtre entière pour la collecte suivante, alors que brief09 avançait son watermark après une
  page plafonnée et sautait le reste pour toujours. Option écartée : paginer, avec 3 s de pause
  entre deux pages, sans usage à ce volume. Un `503` ou un délai dépassé fait aussi échouer la
  source, réessayée au prochain `kb collect` ; écarté : réessayer dans la même exécution.
  — PR de #12

## 2026-10-04

### Visibilité du dépôt

- **Le dépôt est privé jusqu'au 25/10, puis public, avant l'oral blanc du 29/10.** Choix de
  Sabine, confirmé le 2026-10-02 au soir. Pourquoi : le jury doit pouvoir ouvrir le dépôt. Le
  `User-Agent` décidé le 2026-10-02 (le profil public de Sabine) reste valable : il ne dépend pas
  de la visibilité, et le profil ne change pas si le dépôt est renommé.

## 2026-10-05

### Collecte

- **Une collecte par jour ; une collecte manquée est rattrapée à la suivante.** Décision de
  Sabine. Pourquoi : c'est le délai le plus court possible, et le plus juste pour les dépôts les
  plus étoilés, un instantané qui ne se rattrape pas ; c'est acceptable tant que les autres
  sources rattrapent les jours manqués. Tranche entre trois fréquences écrites (« chaque
  semaine » dans le `README.md`, « une par jour » dans les specs, « hebdomadaire » dans le
  registre des traitements) ; le code ne planifie rien. Remplace la collecte hebdomadaire du
  `README.md` et du registre, et la purge « à chaque collecte hebdomadaire » des décisions
  ouvertes. Le rattrapage suit ce que chaque source fait déjà, détaillé dans les
  [specs de la collecte](../specs-collecte.md). Limite connue : au-delà de 2 000 papiers dans la
  fenêtre, arXiv échoue à chaque collecte (#71). — PR de #65

### Lecture et fusion

- **L'item commun est un modèle Pydantic (`Item`, `src/k_b/items.py`), fermé et strict.**
  Décision de Sabine. Pourquoi, selon elle : FastAPI apportera Pydantic de toute façon avec
  l'API (#21). Option écartée : une `dataclass` validée à la main, comme les lecteurs actuels.
  Elle demande plus de code de validation, et il faudrait un second format pour l'API. Pydantic
  devient la première dépendance d'exécution de K-B. — PR de #79
- **Les lecteurs des sources restent en `dataclass` ; leur migration vers Pydantic est une issue
  à part (#85), après #20.** Décision de Sabine. Pourquoi : tenir l'échéance du 07/10. La
  migration dans #79 ajoutait environ 2,5 h, pour 13 h disponibles sur #20. Les lecteurs étaient
  en `dataclass` parce que les dépendances étaient interdites
  ([note du 30/09](../journaling/2026-09-30-commande-kb-collect.md), « la mission interdit de
  toucher aux dépendances » ; [note du 02/10](../journaling/2026-10-02-collecte-releases-github.md),
  Pydantic « n'est pas encore une dépendance du projet »). Cette raison ne tient plus depuis
  l'ajout de Pydantic. Limite assumée : deux façons de valider une entrée externe coexistent
  jusqu'à #85. — PR de #79
- **`url` est un texte contraint à `https://`, pas le type `HttpUrl` de Pydantic.** Pourquoi :
  `HttpUrl` réécrit l'URL (il ajoute par exemple un `/` final), alors que la fusion (#80) retire
  les doublons en comparant les URL comme du texte. Option écartée : `HttpUrl`, qui valide
  davantage (hôte, encodage), mais qui stockerait une autre URL que celle reçue. — PR de #79
- **Une même CVE dans deux sources donne deux items, reliés par leur CVE. Le doublon `same_cve`
  ne vaut qu'au sein d'une même source.** Décision de Sabine : « je veux rattacher, pas
  dédoublonner ». Une alerte GitHub (un paquet vulnérable) et une entrée CISA (une faille
  activement exploitée) sont deux informations, et `stockage.md` prévoit la CVE pour le
  « croisement avec CISA ». **Inverse une décision prise le même jour** pendant la conception de
  #80 (option a) : même CVE = doublon, on garde le premier vu, comme l'écrivait
  `specs-collecte.md` et comme l'imposait l'unicité de `vulnerability.cve` dans le schéma. Ce
  qui a changé : dédoublonner perdait l'information propre à chaque source, l'exploitation
  active chez CISA, le paquet et les versions chez GitHub. Et `stockage.md` prévoyait déjà le
  croisement avec CISA. Option écartée
  aussi : garder les deux items, mais la CVE sur le premier seulement (le lien serait perdu).
  Conséquence : `cve` cesse d'être unique dans le schéma (#81). — PR de #80

### Import dans la base

- **La nature « vulnérabilité » est portée par l'item (`Item.is_vulnerability`), pas déduite de
  la présence d'un CVE.** Décision de Sabine (option A). Raison présentée à Sabine, qui a retenu
  A sans en donner d'autre : le modèle dit `cve` « facultatif » (`stockage.md`), donc une alerte
  GitHub sans CVE est une vulnérabilité ; sans ce champ, l'import ne la distinguait pas d'une
  release. Option écartée (B) : une ligne VULNÉRABILITÉ seulement s'il y a un CVE ; rien à
  changer dans `Item`, mais elle contredit le modèle et les alertes sans CVE ne seraient plus
  trouvables comme vulnérabilités. Un validateur refuse un CVE sur un item qui n'est pas une
  vulnérabilité. Limite connue : l'exclusivité des sous-types (un item n'est pas à la fois dépôt
  et vulnérabilité), annoncée le 2026-10-02 comme vérifiée par le code de fusion, ne l'est
  toujours pas. — PR de #82
- **L'import réécrit un item existant sous le même `item_id` (upsert sur `source_code`,
  `source_item_id`).** Conception validée par Sabine. Pourquoi : l'API (#21) exposera `item_id`,
  qui doit rester stable d'un import à l'autre ; une révision arXiv réécrit le papier sans
  changer son identifiant. Option écartée : vider la base et tout réinsérer à chaque import,
  plus simple, mais qui renumérote les items. Limite assumée : les clés internes
  (`collection_id`, `author_id`) dépendent de l'ordre des imports ; le contenu de la base, lui,
  ne dépend que du brut. — PR de #82
- **Un auteur qui n'a plus d'item est supprimé à chaque import, dans la même transaction.**
  Décision de Sabine, sur un constat de revue. Pourquoi : une révision arXiv qui change ses
  auteurs laissait un nom de personne sans usage (RGPD, minimisation), et `stockage.md` exige
  qu'un auteur ait au moins un item. Option écartée : laisser ce nettoyage à la purge (#8),
  pas encore codée, le nom restant en base d'ici là. — PR de #82

## 2026-10-07

Décisions de la clarification du modèle ; le détail et les constats sont dans
[la clarification](../2026-10-07-clarification-modele.md). Le schéma codé (`schema.sql`) suit
encore l'ancien modèle.

### Modèle de la base

- **Une DONNÉE BRUTE (un fichier de `raw/`) remplace COLLECTE : une source fournit des données
  brutes, une donnée brute contient des items. La sous-catégorie d'une source (édition TLDR,
  dépôt suivi) est l'attribut `flux` de la donnée brute. Pas d'entité LANCEMENT pour
  l'instant.** Décision de Sabine. Pourquoi : « collecte » faisait penser au lancement de
  `kb collect`, alors qu'une collecte en base est un fichier brut, d'une seule source ; SOURCE et
  COLLECTE n'étaient pas reliées au MCD. Options écartées : une source par édition (GitHub en
  compterait une douzaine) ; une entité FLUX (aucun attribut propre à porter) ; SOURCE et
  LANCEMENT en plusieurs à plusieurs (aucun parcours v0 ne se sert du lancement). Prolonge la
  table COLLECTE du 2026-10-02 (PR de #7), renommée et reliée à SOURCE.
- **CISA KEV est un catalogue d'état : une ligne connue garde son identité et prend la dernière
  version (`revised_at` daté) ; une ligne absente est marquée retirée (`withdrawn_at`).** Décision
  de Sabine. Pourquoi : chaque collecte télécharge le catalogue entier, et CISA modifie des
  lignes sur place (`knownRansomwareCampaignUse`, 41 fois d'octobre 2023 à juillet 2024 selon
  GreyNoise). La règle « premier vu ou dernier vu » (D6 de la revue d'architecture) se règle par
  nature de source : flux de nouveautés (TLDR, alertes, releases) premier vu ; catalogue d'état
  dernière version ; flux avec révisions (arXiv) remplacé si `updated` est plus récent. Limite
  assumée : l'historique des versions n'est pas en base, le brut le garde (RGESN 1.6).
  **Révisée le 2026-10-19** : l'historique des versions est abandonné, le brut de CISA ne garde
  que le dernier catalogue importé (« Brut : catalogues d'état et conservation »).
- **Un référentiel est une chose de référence, à identifiant officiel et stable, vers laquelle
  les items pointent : VULNÉRABILITÉ (numéro CVE) dès le 07/10, PUBLICATION (référence arXiv)
  le 08/10. Il porte le contenu donné par la source qui fait foi (CISA KEV, arXiv) et pointe vers
  l'item de cette source quand elle l'a vu ; une source qui cite un référentiel le crée.**
  Décision de Sabine. Pourquoi : les 55 alertes pip du 2026-10-07 ont toutes un CVE, aucun n'est
  dans le CSV CISA du même jour, donc une alerte doit créer sa CVE sans fausse ligne KEV ; un
  article TLDR peut citer un papier qu'arXiv n'a pas vu. CISA fait foi : dans le périmètre de
  K-B, KEV est la liste officielle des failles exploitées. « Exploitée » se lit
  `item_id IS NOT NULL` ; un `CHECK` impose que les colonnes de la source qui fait foi soient
  remplies si et seulement si `item_id` l'est. Options écartées : une entité SUJET identifiée
  par le CVE ou l'URL ; `cve_id` en simple colonne sans clé étrangère ; un attribut
  `is_exploited` (doublon de `item_id`) ; une table KEV_ENTRY séparée (une table de plus pour
  éviter des colonnes vides que le `CHECK` tient). Remplace le sous-type VULNÉRABILITÉ (`cve`)
  du 2026-10-02 (PR de #7) et `Item.is_vulnerability` du 2026-10-05 (PR de #82), que porte
  désormais `kind`. Garde le principe du 2026-10-05 (PR de #80) : deux sources d'un même CVE
  sont rattachées, pas dédoublonnées. Périmètre : les failles dont l'exploitation est avérée ;
  la liste CVE complète (`CVEProject/cvelistV5`, 3,9 Go) n'est pas collectée.
- **Les auteurs d'un papier sont une liste JSON, attribut de PUBLICATION, dans l'ordre
  d'arXiv.** Décision de Sabine. Pourquoi : aucun parcours ne cherche par auteur ; la valeur est
  une mention d'affichage que la base ne découpe jamais. **Inverse** l'entité AUTEUR du
  2026-10-02 (PR de #7), choisie pour la 1re forme normale et une purge par `DELETE` ciblé, et
  rend sans objet la suppression des auteurs sans item du 2026-10-05 (PR de #82). Limite
  assumée : la purge d'une personne dans tous ses papiers n'est plus un `DELETE` ciblé ; le
  registre des traitements est à mettre à jour.
- **Option D : ITEM minimal (`id`, donnée brute de sa version actuelle, `kind`) ; chaque
  sous-type a une clé étrangère `item_id` obligatoire et unique ; l'exclusivité des sous-types
  est portée par une clé étrangère composée (`item_id`, `kind`).** Décision de Sabine. Pourquoi :
  ITEM reste le point d'entrée unique pour les notes, la recherche et P1. Options écartées : B,
  ITEM table de trace avec une clé étrangère facultative vers chaque référentiel (doublon de
  rôle) ; C, pas de table ITEM et une vue `UNION` (une table de liaison par type pour les
  notes). Remplace le « socle commun » d'ITEM du 2026-10-02 (PR de #7), dont la limite
  (« exclusivité non portée par SQL ») tombe. Conséquence : ITEM n'a plus d'URL, et l'ADR
  « `url` obligatoire et unique pour tout item » (2026-10-02, PR de #7) ne s'applique plus ;
  l'unicité passe par l'identifiant naturel de chaque table. Limite relevée par la relecture du
  09/10 : titre, résumé et date commune ne sont plus dans ITEM, alors que la recherche et P1 les
  demandent (question ouverte, ci-dessous).
- **Chaque table a un `id` technique pour clé primaire ; les identifiants naturels (`arxiv_id`,
  `cve_id`, `ghsa_id`, `release_id`, édition + date + rang) deviennent des contraintes
  `UNIQUE`.** Décision de Sabine. Option écartée : l'identifiant naturel en clé primaire, lisible
  sans jointure mais lié à un identifiant externe.
- **ARTICLE DE NEWSLETTER, sous-type d'ITEM (TLDR fait foi pour son résumé) : édition, date
  d'édition, rang, titre, résumé, URL de l'article d'origine sans `utm_*`, clé étrangère
  facultative vers la PUBLICATION citée ; clé naturelle (édition, date, rang).** Décision de
  Sabine. Pourquoi l'URL n'est pas unique : deux éditions peuvent résumer le même article.
  Remplace la règle de `stockage.md` où un résumé TLDR prenait l'URL de l'article qu'il résume,
  incompatible avec une URL unique.

### Collecte

- **Tops GitHub (P7, P8) hors de la base : le top 100 du jour par étoiles et le top 100 par
  forks, collectés par l'API GraphQL ; le JSON reçu est à la fois le brut et le top du jour, un
  fichier par critère et par collecte.** Décision de Sabine. Pourquoi : en v0, le top du jour
  seulement, sans historique ni comparaison de positions. Options écartées : des dépôts en items
  avec une mesure par instantané (environ 36 500 lignes par an) ; une table d'état `ranking` (une
  base pour un simple affichage) ; l'API REST (82 champs par dépôt, sans choix des champs).
  Remplace, pour l'API et l'entrée en base, l'ADR du 2026-10-02 sur les plus étoilés (PR de
  #11), qui garde le top 100 de tout GitHub et l'instantané quotidien. Exception à la règle du
  brut intact (2026-09-30), comme arXiv et les alertes : GraphQL ne renvoie que les champs
  demandés. Limite : durée de conservation des fichiers non décidée. **Révisée le 2026-10-19**,
  pour la méthode de collecte seule : les deux tops sont collectés par l'API REST au POC, jusqu'à
  #269 (« Collecte : méthode des tops GitHub »). **Révisée le 2026-10-19** encore : la durée du
  brut est tranchée (le dernier relevé lisible) et une fiche par jour garde l'historique du top
  (« Tops : les fiches par `kb write-tops` »).

## 2026-10-08

### Modèle de la base

- **Les paquets touchés par une alerte GitHub sont une liste JSON, attribut de l'alerte.**
  Décision de Sabine. Pourquoi : en v0, la liste est seulement affichée ; filtrer par paquet (P3)
  n'est pas planifié. Constat : sur 55 alertes pip, 42 touchent 1 paquet, 11 en touchent 2, 1 en
  touche 3, 1 en touche 4. Options écartées : des colonnes Paquet 1…N (groupe répétitif, 1re
  forme normale) ; une table `advisory_package` dès la v0 (pas de filtre à servir). Limite
  assumée : si P3 est fait, la liste est découpée en table.
- **DÉPÔT SUIVI est une table de référence (nom `owner/name`, écosystème, paquets suivis), à
  laquelle chaque RELEASE est rattachée ; la liste fait foi dans le code
  (`tracked_repositories.py`), qui remplit la table. RELEASE garde `id`, `tag_name`, `name`,
  `body` (Markdown tel que reçu) et `published_at`.** Décision de Sabine. Pourquoi : la liste des
  dépôts suivis existe déjà avec ses données, et la collecte la lit là. Option écartée : le nom du
  dépôt en simple colonne de RELEASE.
- **GH Archive : les dépôts qui montent entrent en base dans une table TENDANCE, qui n'est pas un
  item : une ligne par dépôt (`repo.id`, dernier nom vu) et par fenêtre de 3 jours, étoiles et
  forks gagnés, étoiles et forks totaux lus par GraphQL ; les 30 premiers par étoiles et les 30
  premiers par forks, réunis. Elle est produite par une donnée brute de `gh_archive` (le
  résultat de la requête BigQuery).** Décision de Sabine. Pourquoi : GH Archive est la seule
  source big data, et le bloc E1 demande d'agréger toutes les sources dans le jeu de données
  stocké (critères exacts non relus) ; toute donnée en base remonte à un fichier brut. Le rang se
  calcule par un tri. Options écartées : un fichier hors base, comme les tops GitHub ; deux
  tables par critère (mêmes données) ; une ligne par critère ; un top 100 (RGESN 1.6) ; TENDANCE
  sans lien au brut ; l'API REST pour les totaux (une requête par dépôt). **Inverse** l'ADR du
  2026-10-02 (PR de #7) : un dépôt n'est plus un item avec des MESURES. Limite relevée par la
  relecture du 09/10 : les totaux GraphQL n'ont pas de brut rattaché (à trancher).
- **L'URL d'un dépôt, d'un papier arXiv et d'une faille se déduit de son identifiant ; celle
  d'une release ou d'une alerte est gardée telle que GitHub la donne (`html_url`). Le chemin du
  brut est stocké, son nom de fichier en est déduit.** Décision de Sabine. Pourquoi : une
  étiquette de release peut contenir des caractères à encoder, la reconstruire serait moins sûr ;
  stocker le nom et reconstruire le chemin demanderait de recoder le rangement de chaque source.
- **Une longueur maximale est tenue deux fois, par Pydantic à la lecture du brut et par un
  `CHECK (length(col) <= n)` ; une valeur trop longue fait refuser l'item, et le journal dit quel
  champ dépasse et de combien.** Décision de Sabine. Pourquoi : défense en profondeur, comme
  pour les dates ; SQLite ignore la longueur d'un `VARCHAR(n)`. Options écartées : un seul des
  deux contrôles ; tronquer (modifie la donnée sans le dire). Limite assumée : la même limite
  écrite en Python et en SQL, un test vérifie qu'elles concordent.

### Collecte

- **Le flux arXiv s'appelle `arxiv_cscr_x_csai`, d'après sa requête (`cat:cs.CR AND cat:cs.AI`,
  `src/k_b/sources/arxiv.py:97`) ; comme tout flux, c'est le nom de son dossier brut.** Décision
  de Sabine (2026-10-08 ; pourquoi redit le 2026-10-09). Pourquoi : préciser le flux, et préparer
  d'autres catégories arXiv quand K-B tournera pour de vrai, une requête par flux. Aucune autre
  option discutée. Ne revient pas sur le choix des catégories (2026-10-01) : il nomme le flux
  existant. Limite : le changement de code (`name = FOLDER_PREFIX` devient
  `f"{FOLDER_PREFIX}_cscr_x_csai"`, `arxiv.py:63`) se fait dans une issue et une PR à part, et
  doit reporter la date de dernière collecte sous le nouveau nom, sinon la collecte repart du
  2026-05-01 (`collect.py:47`, `arxiv.py:44`). — PR #115

### Installation et interface

- **K-B tourne sur la machine de Sabine et s'installe comme une commande `kb`
  (`uv tool install --editable`) ; la veille s'interroge par des commandes (`kb search`,
  `kb top`).** Décision de Sabine. Pourquoi, selon elle : en ligne, elle ne voyait pas comment
  téléverser ni stocker les documents qu'elle dépose (bibliothèque choisie, futur wiki LLM) ;
  installé en local, le terminal est plus simple qu'une interface graphique. Une commande
  n'exclut pas une API REST locale (question ouverte, ci-dessous). Évolutions notées, sans
  issue : une TUI plein écran, puis une application de bureau (Tauri, hors « Python
  uniquement »). **Révisée le 2026-10-15** : le 25/10 est un POC en conteneurs en localhost,
  sans interface CLI dédiée ni front ; `kb search` vient après le 08/11 ; mise en ligne sur
  Azure Container Apps au 08/11 (« POC du 25/10 », décision 1).

### Schémas

- **MCD et MLD dessinés avec draw.io (`docs/merise/*.drawio`) ; le MPD reste le script SQL.**
  Décision de Sabine. Pourquoi : draw.io respecte mieux les conventions Merise, selon elle.
  **Inverse** le choix de Mermaid du 2026-10-02 (PR de #7), dont la limite était déjà
  qu'un `flowchart` imite la notation Merise sans la respecter. Limite (constat) : GitHub
  n'affiche pas un `.drawio` dans une PR, il montre son XML ; la relecture d'un changement se
  fait en ouvrant le fichier dans draw.io.

## 2026-10-09

### Collecte et stockage

- **Les dossiers du brut disent la finalité : `raw/automated_watch/` (la veille) et
  `raw/selected_library/` (ce que Sabine choisit).** Décision de Sabine. Pourquoi : ils répondent
  aux deux portes du README et aux deux fiches du registre. Options écartées : `choosen_files`,
  `curated_library` (la zone *curated* d'un lac de données est la donnée traitée),
  `hand_picked`, `personal_library`. Remplace `raw/automation/` et `raw/manual/` du 2026-09-29.
- **`collection_state.json` sort de `raw/`, vers la racine du dossier de données.** Décision de
  Sabine. Pourquoi : c'est le seul fichier de `raw/` réécrit à chaque collecte, alors que `raw/`
  est écrit une fois ; `raw/` pourra être en lecture seule et synchronisé sans l'état propre à
  chaque machine.
- **Le dossier de données est `~/.knowledge_base`, hors de tout dossier synchronisé et compris
  dans une sauvegarde.** Décision de Sabine. Pourquoi : la base SQLite et les données restent sur
  la machine ; c'est le brut qu'on sauvegarde (**inversé le 2026-11-04** : la base est la source
  de vérité, le brut gardé 6 mois, #83). Options écartées : `~/.local/share/k-b`
  (convention XDG, moins connue sur Mac), `~/Library/Application Support/K-B` (pensé pour les
  applications graphiques), `~/K-B-data` (exemple du 2026-09-29, un dossier visible de plus).
  **Révisée le 2026-10-15** : dans le POC, la base va dans un volume nommé et le brut dans un
  dossier partagé avec les conteneurs ; mise en ligne sur ACA au 08/11 (« POC du 25/10 »,
  décisions 1 et 2).
- **Le coffre Obsidian et le dossier de données sont séparés : K-B copie chaque clip nouveau ou
  modifié, horodaté, dans `raw/selected_library/clipping/`.** Décision de Sabine. Pourquoi : lire
  les clips en place, que Sabine annote, ferait changer ce que K-B reconstruit. Options écartées :
  lire `Clippings/` en place ; faire écrire le Web Clipper dans le brut (le dossier de données
  devrait être le coffre, et le clip serait à la fois note vivante et brut). **Inverse** l'ADR
  « Données hors du dépôt de code » du 2026-09-29, où le dossier de données servait aussi de
  coffre Obsidian.
- **Zotero : le brut est le résultat d'une requête SQL en lecture seule sur une copie temporaire
  de `zotero.sqlite`, vérifiée par `PRAGMA integrity_check` puis supprimée ; les PDF restent dans
  Zotero, K-B garde leur chemin.** Décision de Sabine. Pourquoi : Zotero ouvert, une lecture en
  place échoue (« database is locked ») ; la base entière comme brut est contraire à la
  minimisation (CNIL, RGESN 1.6). Options écartées : fermer et rouvrir Zotero par script ; ne
  lire que Zotero fermé ; l'API locale de Zotero 7 (plus de source « base de données ») ;
  `zotero.sqlite.bak` (fraîcheur non vérifiée). **Inverse** l'ADR provisoire du 2026-10-01 (PR
  de #6, « copie entière comme brut »). Limites : un champ non extrait aujourd'hui manque aux
  anciens bruts ; `zotero.sqlite` est en mode WAL (constaté le 09/10), et la copie du seul
  `.sqlite` peut manquer les dernières écritures sans que le contrôle d'intégrité le voie : la
  méthode de copie est à revoir avec #15.
- **La base reste jetable : un changement de schéma = recréer la base et tout réimporter depuis
  le brut, sans migration (W7).** Décision de Sabine. Pourquoi : la base doit rester
  reconstructible depuis le brut (registre, fiche 1), et c'est le brut qu'on sauvegarde. Options
  écartées : des migrations numérotées avec `PRAGMA user_version` ; Alembic et SQLAlchemy (deux
  dépendances, schéma à réécrire en Python). Limite : des migrations deviendront nécessaires le
  jour où la base gardera des données sans brut (**ce jour arrive avec #83**, 2026-11-04 : dès que
  le plus ancien brut a 6 mois). **Contredit** l'ADR du 2026-10-05 (PR de #82),
  qui écartait la reconstruction parce qu'elle renumérote `item_id`, que l'API exposera : la
  stabilité de `item_id` est ouverte (ci-dessous). **Révisée le 2026-10-15** : la base passe à
  PostgreSQL au 08/11 ; les migrations Alembic sont à reprendre pour PostgreSQL seulement,
  avec #186 (« POC du 25/10 », décision 2).

### Interface

- **Une API REST locale (sur `localhost`, à côté de la commande `kb`) fait partie d'E1 ; la page
  web et le déploiement relèvent d'un autre livrable.** Décision de Sabine. Pourquoi : l'API est
  attendue dans E1 ; une commande n'exclut pas une API, et une API locale ne revient pas sur la
  décision « local » du 2026-10-08. Conséquence : la
  stabilité de `item_id` face à une base jetable reste à trancher (question ouverte, ci-dessous).
  **Révisée le 2026-10-15** : l'API est mise en ligne sur Azure Container Apps au 08/11
  (« POC du 25/10 », décision 1).

### Périmètre

- **Tous les ajouts de la séance 4 restent dans E1 : bibliothèque indexée (texte complet des
  clips et des notes), Zotero et ses surlignages, clips, ACQUISITION_MODE, TENDANCE, tops
  GraphQL.** Décision de Sabine, après la relecture du 2026-10-09 (point 8). Pourquoi, selon
  elle : la certif demande une base de données parmi les sources (Zotero, source « base de
  données » depuis le 2026-09-29) ; pour TENDANCE, le pourquoi est celui du 2026-10-08. Limite :
  aucun de ces ajouts n'avait d'estimation au moment de la décision, pour une échéance au 25/10 ;
  estimés depuis par une relecture à l'aveugle à environ 36 h, plus environ 24 h de réécriture
  du schéma ; le report des fiches ne libère rien avant le 25/10 (jalon daté du 01/11). Décision à
  revoir avec time-knight (clarification, « Issues touchées »).

### Bibliothèque et recherche

- **En v0, K-B indexe la bibliothèque choisie (clips, Zotero, notes déposées) : chaque document
  devient une entrée en base, cherchable par `kb search`, et un item de la veille peut être relié
  à sa version creusée dans Zotero.** Décision de Sabine. Pourquoi : sinon la base ne verrait pas
  qu'un item a été creusé. Options écartées : stocker seulement ; compiler le wiki LLM (v1).
  **Inverse** l'ADR du 2026-10-02 (PR de #7) : « les documents de `raw/manual/` n'entrent pas
  dans la base en v0 ».
- **Une table de référence ACQUISITION_MODE (`watch`, `library`, `wiki`) regroupe les sources ;
  `kb search --in watch|library|wiki` filtre sur elle ; elle porte la durée de conservation que la
  purge lit.** Décision de Sabine. Pourquoi : la purge doit connaître le mode, sinon un document
  de la bibliothèque purgé serait recréé à la collecte suivante ; le contenu généré par un LLM se
  distingue du contenu collecté. Options écartées : un `CHECK` sur SOURCE ; la déduire du chemin
  du brut ; une colonne sur ITEM ; `--in clip|zotero|note` (doublon de `--source`) ; les noms
  ORIGIN, PROVENANCE, CANAL, `--mode`, `--scope`, `--from`.
- **En v0, la base ne garde que les items ; les fiches de veille et les notes du wiki LLM sont
  reportées après la collecte, l'indexation et `kb search`.** Décision de Sabine. Option écartée
  pour la v0 : une table NOTE et « une note cite des items ». Revient sur le périmètre v0 du
  2026-09-29 (« et fiches de veille ») et sur le calendrier des « Deux wikis ». **Révisée le
  2026-10-15** : les fiches de veille par sujet sont faites par l'API IA au 25/10 (« POC du 25/10 »,
  décision 4).
- **Les surlignages Zotero sont gardés en base et affichés avec leur papier dans `kb search`, sans
  être cherchables par leurs mots.** Décision de Sabine. Options écartées : les rendre
  cherchables (un index de plus) ; ne pas les collecter. Remplace le bloc « Mes surlignages » des
  fiches (2026-09-29, 2026-10-02), reportées.
- **Recherche plein texte par FTS5, triée par pertinence BM25 quand il y a des mots, par date
  sinon ; elle couvre le titre et le résumé des items, et le texte complet des clips et des
  notes déposées.** Décision de Sabine. Pourquoi : aucune dépendance ; un papier qui cite le
  terme une fois ne doit pas valoir un papier consacré au sujet. Options écartées : tri par date
  seul ; une option `--sort relevance` ; titre seul pour la bibliothèque. Limites : `porter` ne
  ramène à leur racine que les mots anglais ; FTS5 est propre à SQLite. **Révisée le
  2026-10-15** : aucun FTS5 nouveau ; la recherche plein texte se fera avec PostgreSQL
  (`tsvector`) après le 08/11, et #188 sera à reformuler (« POC du 25/10 », décision 2).

## 2026-10-10

### Modèle de la base

- **La base n'est jetable qu'en développement ; en usage réel elle est sauvegardée, et l'`id`
  technique des items reste stable.** Décision de Sabine. Pourquoi, selon elle : en usage réel la
  base aura des sauvegardes, et peut-être des exports `.csv` ou `.json` qui porteront l'`id`
  technique ; l'API REST locale l'expose aussi. **Inverse** en partie W7 (2026-10-09) : « la base
  reste jetable, sans migration » ne vaut plus que pour le développement. Options écartées :
  sortir l'API d'E1 ; exposer un identifiant instable ; une reconstruction qui remet à chaque item
  son ancien `id` par sa clé naturelle (mécanisme maison). Limite : la liste d'exclusion reste à
  concevoir (#20).
- **Les changements de schéma de la base d'usage réel passent par des migrations Alembic, écrites
  à la main en SQL ; le code de K-B garde `sqlite3` et le SQL ; SQLAlchemy n'entre que comme
  moteur d'Alembic.** Décision de Sabine. Pourquoi des migrations : la base d'usage réel est
  gardée (entrée précédente). Pourquoi Alembic plutôt que des scripts numérotés avec
  `PRAGMA user_version` : il fournit le suivi de version, le mode « batch » pour les tables que
  SQLite ne sait pas modifier en place, et le retour arrière, qu'il faudrait sinon coder. Pourquoi
  pas l'ORM : K-B écrit à un seul endroit (l'import) et lit surtout par une requête qui reste en
  SQL (entrée sur le titre et la date, ci-dessous) ; l'ORM aurait couvert une minorité de requêtes
  pour une seconde description des tables, un outil à apprendre et environ +4 à 6 h (estimation de
  la session, non relue). Il ne protège pas mieux de l'injection SQL : les requêtes sont déjà
  paramétrées (`?`), et ruff (règle S608) signale en CI une requête construite par concaténation.
  Un LLM ne le justifierait pas non plus : les agents lisent par l'API, et un LLM qui écrirait du
  SQL demanderait une connexion en lecture seule, pas un ORM. **Inverse** en partie W7
  (2026-10-09), qui écartait Alembic et SQLAlchemy ; une dépendance de plus (Alembic, qui apporte
  SQLAlchemy), acceptée par Sabine. Options écartées : l'ORM SQLAlchemy avec Alembic (retenu un
  temps, puis écarté par Sabine comme surdimensionné pour K-B) ; des scripts numérotés ; la
  réflexion de SQLAlchemy. Limite : Alembic n'est nécessaire qu'à partir de l'installation locale ;
  en développement, la base se recrée. L'ORM reste possible plus tard (passage à PostgreSQL, API
  qui écrit), par-dessus le même `schema.sql`. **Révisée le 2026-10-15** : la base passe à
  PostgreSQL au 08/11 ; les migrations Alembic sont à reprendre pour PostgreSQL seulement,
  avec #186 (« POC du 25/10 », décision 2).
- **`schema.sql` reste le MPD et fait foi ; la première migration Alembic l'exécute ; un test
  compare la structure de la base créée par `schema.sql` et de la base migrée jusqu'à la dernière
  révision (`PRAGMA` des colonnes, index, clés étrangères, `STRICT`), et le comportement des
  `CHECK`.** Décision de Sabine, sur l'alternative d'une relecture indépendante. Pourquoi
  `schema.sql` : c'est le MPD de la démarche Merise. Pourquoi ce contrôle : seul un test prouve
  que le SQL et les migrations décrivent la même base. Options écartées : une date dans
  `schema.sql` recopiée en commentaire ailleurs (rien ne vérifie qu'elle suit le code) ;
  l'identifiant de révision Alembic en en-tête de `schema.sql` (ne prouve rien sur le contenu) ;
  comparer le texte de `sqlite_schema` (SQLite garde le `CREATE` tel qu'il a été écrit, constaté
  le 2026-10-10). Limite : selon la doc d'Alembic, son mode batch ne recopie pas les `CHECK` d'une
  table recréée ; une migration peut les perdre sans bruit, d'où le test de comportement.
  **Révisée le 2026-10-15** : les migrations sont à reprendre pour PostgreSQL seulement, avec
  #186 (« POC du 25/10 », décision 2).
- **Le titre, le résumé et les dates restent dans chaque sous-type (article de newsletter,
  release, alerte) ou référentiel (publication, vulnérabilité) ; ITEM reste minimal ; les listes
  qui mélangent les sortes (`kb search`, « quoi de neuf », l'API) passent par une seule requête
  SQL imbriquée en `UNION ALL`, une branche par sorte, à paramètres liés.** Décision de Sabine,
  à revoir à l'usage. Pourquoi, selon elle : les informations propres à une publication, une
  vulnérabilité ou un article sont portées par sa table ; une requête SQL se lit et se teste, une
  vue est un concept qu'elle ne maîtrise pas encore ; une requête complexe s'écrit en SQL. La
  requête est écrite une fois et partagée. Un test vérifie que chaque `kind` a sa branche ; la
  table FTS5 est remplie à l'import (**révisé le 2026-10-15** : pas de FTS5 nouveau,
  « POC du 25/10 », décision 2). Options écartées : recopier titre, résumé et date dans ITEM (doublon) ; une
  table d'affichage remplie à l'import (même doublon, à remettre à jour à chaque révision CISA ou
  arXiv ; gardée en réserve) ; une vue SQL (même coût que la requête imbriquée, mesuré). Mesure (maquette en mémoire,
  1 million d'items, SQLite 3.51) : avec un filtre de date, 0,2 ms ; « les 50 plus récents » sans
  filtre, 69 ms, contre 0 ms pour une table recopiée. Ferme le point 2 de la relecture du
  2026-10-09.
- **Le mode d'acquisition (`watch`, `library`, `wiki`) est une colonne de SOURCE, tenue par un
  `CHECK` ; sa durée de conservation est dans `config.py`.** Décision de Sabine, sur la
  recommandation de la session. Pourquoi : la durée de conservation est un paramètre modulable,
  donc de configuration (Sabine) ; la table ne porterait plus qu'un code et un libellé, et le
  dossier du brut est déjà dans le code (`collect.py:68`, `raw_items.py:111`) ; ajouter un mode
  est rare (`wiki` en v1). **Inverse** la table ACQUISITION_MODE du 2026-10-09. Options écartées :
  garder la table (une table, un modèle et une jointure pour trois lignes). Limites : ajouter un
  mode demandera une migration qui recrée SOURCE ; un test vérifie que chaque mode du `CHECK` a
  une durée dans `config.py`. `kb search --in watch|library|wiki` ne change pas.
- **Les longueurs maximales ont leurs valeurs, en caractères : `publication` (`arxiv_id` 20,
  `title` 500, `summary` 5 000), `vulnerability` (`cve_id` 20, `name` 500, `description` 5 000,
  `vendor` 200, `product` 500), `release` (`tag_name` 255, `name` 255, `body` 125 000, `url`
  2 000), `advisory` (`ghsa_id` 19, `summary` 1 024, `url` 2 000). Elles vivent dans `items.py`,
  seul endroit à lire ; `stockage.md` y renvoie sans les recopier.** Décision de Sabine, sur la
  proposition de la session. Pourquoi ces valeurs : aucune n'était écrite. « Aux valeurs du
  document », dans l'issue, désignait le
  [dictionnaire de données Merise](https://docs.google.com/spreadsheets/d/1SnPOPJVSiNrmeTety9z_KOB0wJjqIFbGWdhPUJwQbgk/edit)
  (Google Sheet, état des décisions au 2026-10-08), qui ne donne aucune longueur de texte,
  seulement 19 pour la référence GHSA (constat de Sabine). Les autres partent du plus long texte
  de la collecte du 2026-10-07, avec une marge : aucune n'écarte un item de cette collecte (la
  plus longue note de release fait 28 783 caractères ; une borne à 10 000 en aurait écarté 22 sur
  100). Pourquoi pas de copie dans `stockage.md` : ce serait une troisième copie, qu'aucun test ne
  tient. Précise la décision du 2026-10-08 (« tenue deux fois »), sans la changer. Limites : les
  limites de GitHub pour `tag_name` et `name` ne sont pas vérifiées ; 1 024 pour le résumé d'une
  alerte (1 000 proposé d'abord) vient d'une copie tierce du schéma de l'API GitHub, relevée par
  la revue de code, **non vérifiée à la source** ; 125 000 vient d'un message d'erreur de l'API
  GitHub rapporté par des tiers, 1 920 pour un résumé arXiv de la page d'aide d'arXiv ; les
  autres dépôts suivis et les alertes `npm` ne sont pas dans la collecte mesurée ; une étiquette
  de release non ASCII, encodée dans l'URL, peut dépasser 2 000 caractères en restant sous 255 ;
  `length()` de SQLite s'arrête au premier caractère NUL. Conséquence assumée de « rien n'est
  tronqué » (2026-10-08) : un texte trop long écarte l'entrée entière ; une ligne CISA KEV
  refusée pour sa description laisse son CVE lu comme non exploité (`item_id` vide), et une
  révision arXiv refusée laisse en base la version précédente, avec pour seule trace une ligne
  du journal d'import, à chaque import.
- **Côté Pydantic, les longueurs sont une table des bornes par sorte d'item dans `items.py`, lue
  par un contrôle du modèle, et non un `max_length` par champ.** Décision de Sabine, sur la
  recommandation de la session. Pourquoi : `Item` est un modèle commun, et son champ `summary`
  alimente le résumé arXiv, la description CISA et la note de release ; avec la table, chaque
  colonne garde sa borne, et le message dit le champ, la longueur reçue et le maximum, comme le
  demande la décision du 2026-10-08. Options écartées : un `max_length` par champ (une seule
  borne, 125 000, pour les trois textes ; le message de Pydantic ne dit pas la longueur reçue) ;
  un modèle Pydantic par sorte (refonte d'`Item`, hors de l'issue). Une sorte sans table en base
  (`newsletter_article`) n'a pas de borne : elle vient avec sa table. Limite : le critère de
  l'issue sur le motif des rejets (#92, « le champ et le type d'erreur Pydantic […], sans la
  valeur reçue ») effacerait la longueur et le maximum ; son texte est à accorder.
- **Une liste JSON (`publication.authors`, `advisory.packages`) est bornée en nombre d'éléments,
  en base et dans l'item (1 000 auteurs, 100 paquets) ; la longueur de chaque élément (200 et 255
  caractères) n'est tenue que par l'item.** Décision de Sabine, sur la proposition de la session.
  Pourquoi : un `CHECK` de SQLite ne peut pas parcourir les éléments d'une liste (pas de
  sous-requête dans un `CHECK`). Le nombre d'éléments a son propre `CHECK`, séparé de celui de la
  forme JSON : SQLite nomme dans son message le `CHECK` qui refuse. Option écartée : borner la
  longueur du texte JSON (aucune borne égale côté item, le texte JSON est produit par l'import).
  Limites assumées : la longueur d'un nom **déroge** à « tenue deux fois » (2026-10-08) ; un
  papier de plus de 1 000 auteurs (grande collaboration) serait écarté, la collecte du
  2026-10-07 en compte 24 au plus.
- **Restent sans borne de longueur : les colonnes que le code remplit (`source`,
  `tracked_repository`, le chemin et le flux de `raw_data`), les dates, qui gardent leur `CHECK`
  de format, et `highlight`, `repository` et `star_gain`.** Décision de Sabine. Pourquoi : la
  borne tient ce qu'une source peut écrire ; ces colonnes n'ont pas de modèle Pydantic en face.
  Limite : les bornes de `highlight` sont à fixer avec son lecteur ; `repository` et `star_gain`
  sont des tables du modèle précédent, sans écrivain, dont le sort n'est pas décidé ici.
- **Chaque `CHECK` de `schema.sql` a sa valeur refusée dans un test, qui attend le texte de ce
  `CHECK` dans le message de SQLite ; une garde fait échouer la suite si un `CHECK` est ajouté
  sans sa valeur refusée.** Décision de Sabine, sur la proposition de la session et de la
  relecture du plan. Pourquoi : la décision du jour sur `schema.sql` demande un test du
  comportement des `CHECK`, qu'une migration peut perdre sans bruit ; compter les cas ne prouve
  pas que chaque `CHECK` a le sien. Options écartées : nommer les contraintes (`CONSTRAINT nom`),
  un essai de la relecture ayant vu un nom ressortir pour un autre `CHECK` ; déplacer les 11
  tests de refus déjà écrits dans la table des cas (retouche de code qui marche). Limite
  assumée : ces 11 `CHECK` sont testés deux fois.

### Configuration

- **Les paramètres modulables de la veille sont rassemblés dans `config.py`** : mots-clés et date
  de première collecte d'arXiv, éditions TLDR, dépôts et écosystèmes suivis, seuil et taille du
  top GitHub, durées de conservation, délai réseau. Décision de Sabine. Pourquoi, selon elle :
  sortir du code ce qui se règle. Restent dans le code : les faits des API et des formats (URL,
  expressions régulières, formats de date) et les plafonds de taille, garde-fous de sécurité
  qu'on ne doit pas relâcher en croyant régler la veille. Restent en variables d'environnement :
  les secrets et le dossier de données. **Révisée le 2026-10-15** : s'y ajoutent les réglages
  de déploiement (hôte, port, hôtes permis, chemins, fenêtres), règle 2 de
  `.claude/rules/poc.md` (« POC du 25/10 », décision 8).

## 2026-10-11

### Collecte : Zotero

- **L'issue Zotero s'arrête au brut : `kb collect` extrait la bibliothèque dans un fichier JSON,
  et rien de Zotero n'entre dans la base ; lire cet extrait vers la base est une issue à part.**
  Décision de Sabine, sur la recommandation de la session. Pourquoi, selon cette
  recommandation : le modèle de la bibliothèque est ouvert depuis le 2026-10-09 (ci-dessous) et
  touche aussi les clips Obsidian ; le trancher dans cette issue l'élargissait au-delà de son
  critère et de ses 5 h. Options écartées : aller jusqu'à la base avec un modèle minimal décidé
  le jour même (un sous-type d'item pour le papier Zotero ; environ 3 h de plus, estimation de la
  session, non relue) ; rattacher les surlignages à l'item arXiv existant (un papier que la
  collecte arXiv n'a pas vu perdrait ses surlignages). Limite assumée : la table `highlight`
  reste vide, et aucune commande ne montre encore un surlignage. — PR de #15
- **La requête ramène chaque document de premier niveau de la bibliothèque personnelle, hors
  corbeille, avec ses auteurs, ses étiquettes et leur type, les PDF rangés dans le stockage de
  Zotero, et les surlignages de ces PDF (annotations de type 1) avec leur commentaire.**
  Décision de Sabine, sur les propositions de la session. Pourquoi tous les documents : Zotero
  n'a pas d'état « lu », et un papier enregistré sans surlignage reste visible. Pourquoi les
  seuls PDF du stockage : un PDF lié garde son propre chemin, qui peut être absolu et contenir
  le nom du compte. Options écartées : seulement les documents surlignés (2 sur 5 le
  2026-10-11) ; seulement ceux dont le PDF a une date de dernière lecture (sens de `lastRead`
  non vérifié) ; tous les types d'annotation (aucun exemple observé) ; ne pas extraire les
  étiquettes (les 11 observées sont automatiques, l'issue les demandait). Les notes et les
  autres types d'annotation sont remis à plus tard par Sabine (« on verra plus tard »). Limites
  assumées : un PDF enregistré sans document parent, un surlignage sur un EPUB ou une capture de
  page web, et un titre rangé par Zotero sous un autre champ que `title` ne sont pas extraits ;
  « type 1 = surlignage » est déduit des 6 annotations observées, la documentation de Zotero
  consultée ne le dit pas. — PR de #15
- **La base Zotero est lue par une copie de `zotero.sqlite` et de son `-wal`, faite dans un
  dossier temporaire du système, vérifiée par `PRAGMA integrity_check` et gardée par une
  comparaison des deux fichiers (présence, taille, date de modification, inode) avant et après
  la copie.** Décision de Sabine, sur la proposition de la session ; ferme « la méthode de copie
  est à revoir avec #15 » (2026-10-09). Pourquoi les deux fichiers : la documentation de Zotero
  demande de garder le `-wal` avec la base quand on la copie, et le 2026-10-11, Zotero ouvert,
  le fichier principal datait du 7 octobre quand le `-wal` était du jour. Pourquoi la
  comparaison : les deux fichiers ne sont pas copiés au même instant, et la relecture du plan a
  montré, sur une base fabriquée, qu'une paire mal assortie passe `integrity_check`. Pourquoi
  le dossier temporaire du système : la source ne connaît pas le dossier de données, et une
  copie entière de la bibliothèque n'a pas à passer par un dossier compris dans une sauvegarde.
  Options écartées : l'API de sauvegarde de SQLite (elle ouvre l'original, que Zotero
  verrouille) ; `immutable=1` sur l'original (ignore le `-wal`) ; un temporaire caché dans le
  dossier de données, comme le veut la convention 2 pour les fichiers que K-B écrit ; un
  plafond de taille sur la base copiée (arbitraire : un disque plein arrête déjà la copie).
  Limites assumées : un processus tué (`kill`, terminal fermé, coupure) laisse le dossier
  `kb-zotero-…` dans le dossier temporaire du système jusqu'à l'extraction suivante, qui le
  retire ; deux `kb collect` lancés en même temps peuvent se retirer leur copie l'un à l'autre
  (K-B n'a pas de verrou) ; la règle commune « chaque téléchargement a une taille maximale » ne
  s'applique pas à cette copie. — PR de #15
- **La requête d'extraction d'une source qui est elle-même une base vit dans le module de cette
  source (`src/k_b/sources/zotero.py`), pas dans `src/k_b/database/` ; la règle 5 des
  conventions et sa commande sont précisées (« le SQL de la base K-B »).** Décision de Sabine,
  sur la recommandation de la session. Pourquoi : la base Zotero est une source externe, lue
  comme une API, pas la base de K-B ; l'issue GH Archive aura le même cas avec son SQL
  BigQuery. Option écartée : la ranger dans `src/k_b/database/` (la commande de la règle était
  respectée, mais le module d'accès à la base K-B aurait porté le schéma d'une source).
  Conséquence : la commande de l'issue qui déplace le SQL d'écriture (#135) change de la même
  façon. — PR de #15
- **Une source dit dans quel dossier de `raw/` va son brut (`acquisition_dir_name` :
  `automated_watch` ou `selected_library`) ; le dossier de données de Zotero est donné par la
  variable d'environnement `KB_ZOTERO_DIR`, et sans elle `kb collect` saute Zotero et
  l'affiche.** Décision de Sabine, sur les propositions de la session ; applique aux dossiers
  du brut la décision du 2026-10-09. Pourquoi une variable : un chemin de machine n'a pas sa
  place dans un dépôt public. Options écartées : porter le dossier par la sorte de source
  (`SourceKind` : il fallait changer la signature de la collecte et 14 appels de tests) ; une
  constante dans `config.py` ; faire échouer la collecte sur une machine sans Zotero. Limite
  assumée : le dossier redit, dans le code, le mode d'acquisition que `seed_sources.sql` porte
  déjà, et les six sources de la veille répètent la même ligne. — PR de #15
- **« Rien de neuf » se décide à la date de modification des deux fichiers de Zotero, et chaque
  extrait contient toute la bibliothèque.** Proposition de la session, validée par Sabine avec
  le plan. Pourquoi : la source ne lit pas le brut déjà écrit, elle ne peut pas comparer au
  dernier extrait. Limites assumées : Zotero ouvert écrit dans son `-wal` sans que la
  bibliothèque change, et un extrait identique au précédent est alors écrit (9 Ko le
  2026-10-11) ; une base restaurée avec d'anciennes dates n'est pas extraite tant qu'elle ne
  change pas ; la date de dernière collecte est rangée sous la clé `zotero`, sans lien avec le
  dossier : si `KB_ZOTERO_DIR` désigne ensuite un autre dossier dont les fichiers sont plus
  anciens que cette date, `kb collect` affiche `zotero: ok` et n'extrait rien tant que Zotero
  n'y écrit pas. — PR de #15
- **La base d'essai Zotero est un script SQL versionné : les 15 tables utiles, réécrites avec
  toutes leurs colonnes et contraintes relevées sur la base réelle, et des valeurs inventées.**
  Décision de Sabine (« si base réduite est fiable ok alors »). Pourquoi réduite : les 44
  autres tables ne sont jamais lues par la requête. Ce qui la rend fiable : `PRAGMA table_info`
  comparé à une copie de la base réelle (0 écart sur les 15 tables le 2026-10-11), et la
  collecte sur cette copie (5 documents, 6 surlignages). Options écartées : un fichier binaire
  versionné (illisible dans une PR ; une base réelle vidée peut garder des restes dans ses
  pages libres) ; les 59 tables ; les `CREATE TABLE` de Zotero recopiés mot pour mot. Limites :
  la comparaison se fait sur la machine de Sabine, pas dans la CI ; un changement de sens sans
  changement de structure ne serait pas vu. — PR de #15

### Collecte : GH Archive

- **GH Archive : #16 s'arrête à l'extraction ; la table TENDANCE et les étoiles et forks totaux lus
  par GraphQL viennent dans une issue de suite.** Décision de Sabine, sur la recommandation de la
  session. Pourquoi : l'estimation de 7 h tenait ; l'écrivain de TENDANCE aurait ajouté du SQL
  dans `import_items.py` avant que #135 ne le déplace dans `src/k_b/database/` (règle 5 des
  conventions) ; la file de Sabine met la chaîne ETL après BigQuery ; le POST que GraphQL demande
  viendra avec le passage à httpx (#86) ou après. Option écartée : aller jusqu'à TENDANCE dans #16.
  Limite : à la fin de #16, la source big data n'est pas encore en base ; la requête produit déjà
  la forme décidée le 2026-10-08 (étoiles et forks gagnés, 30 + 30 par fenêtre). — PR de #16
- **Client `google-cloud-bigquery` (>=3.46,<4).** Décision de Sabine, sur recommandation.
  Pourquoi : le client officiel, déjà nommé par les specs, qui porte `dry_run`,
  `maximum_bytes_billed` et la lecture de la clé par `GOOGLE_APPLICATION_CREDENTIALS`. Option
  écartée : appeler l'API REST de BigQuery soi-même (la clé doit signer un jeton, donc
  `google-auth` ou `cryptography` quand même, et un POST). Limite : 26 paquets ajoutés, dont
  `grpcio` et `cryptography` ; l'import coûte environ 90 ms à chaque commande `kb` (mesuré le
  2026-10-11), accepté par Sabine plutôt qu'un import dans les fonctions. — PR de #16
- **BigQuery plutôt que PySpark sur les fichiers bruts de GH Archive.** Décision de Sabine ;
  complète l'entrée « BigQuery » du 2026-09-29, qui le justifiait face à l'API GitHub. Option
  écartée : télécharger les fichiers de `data.gharchive.org` (un JSON compressé par heure) et les
  traiter avec PySpark. Pourquoi :
  - le volume à rapatrier : 24 fichiers et 272 Mo compressés pour la seule journée du 2026-10-10
    (en-têtes `Content-Length`, lus le 2026-10-11 sans télécharger), soit 72 fichiers et environ
    0,8 Go compressés pour une fenêtre de 3 jours, à décompresser et à lire en entier ; avec
    BigQuery, le calcul se fait là où les données sont déjà chargées, et seul le résultat arrive
    dans `raw/` (8 764 octets pour la fenêtre du 2026-10-10) ;
  - le stockage en colonnes : BigQuery ne lit que les 4 colonnes demandées, 133,8 Mo pour 3 jours,
    alors que la table d'une seule journée pèse 1 060 Mo (métadonnées du 2026-10-11) ; un JSON se
    lit ligne entière ;
  - aucune infrastructure : BigQuery est sans serveur, gratuit et plafonné en bac à sable ; Spark
    demande Java et de la mémoire sur le Mac, ou un cluster payant (Dataproc, Databricks) ;
  - la minimisation : `actor` n'est jamais sélectionné, donc jamais reçu ; avec les fichiers, il
    serait téléchargé puis à écarter (RGPD art. 5.1.c) ;
  - le besoin tient en SQL : filtrer, compter, classer.
  Limite : K-B dépend d'un service de Google et de la présence de GH Archive dans BigQuery. Spark
  redeviendrait le bon outil si les données étaient déjà chez nous en fichiers, si le traitement
  dépassait le SQL (apprentissage automatique, transformations en Python), ou pour un flux continu
  (Structured Streaming). — PR de #16
- **Une fenêtre = 3 jours UTC complets, de J-3 à J-1, glissante ; les fenêtres manquées sont
  rattrapées, 15 au plus (les plus récentes), en une seule requête.** Décision de Sabine.
  Pourquoi : les tables passées de GH Archive restent lisibles, donc l'ADR du 2026-10-05 (« une
  collecte manquée est rattrapée à la suivante ») s'applique ; la limite de 15 tient à la
  pertinence, selon Sabine : un dépôt qui a monté il y a plus de deux semaines n'apporte plus
  grand-chose à la veille. **S'écarte** de l'ADR du 2026-10-05 au-delà de 15 jours manqués.
  Options écartées : pas de rattrapage (comme les dépôts les plus étoilés, un instantané qui ne
  se rattrape pas) ; 30 fenêtres (proposition de la session) ; échouer au-delà de la limite (la
  source échouerait à chaque collecte, comme arXiv, #71). Limite : une collecte qui passe minuit
  UTC reprend une fenêtre déjà collectée (un brut en double, sans perte). — PR de #16
- **Plafond d'une requête : 650 Mo par fenêtre, 2 Go au plus ; quand la borne s'applique, la
  fenêtre la plus ancienne est retirée et le `dry_run` refait ; sinon, ou avec un `dry_run` sans
  volume, la source échoue sans rien exécuter.** Décision de Sabine, sur des valeurs mesurées et
  non choisies au jugé : la fenêtre la plus lourde prise seule × 1,5 donne le plafond par
  fenêtre ; le rattrapage maximal mesuré tient sous la borne (mesures, calcul et commandes datés
  dans [bigquery.md](../bigquery.md#mesures-du-2026-10-11)). Pourquoi : une collecte ordinaire qui
  lirait 20 fois trop est arrêtée au `dry_run` ; « 4 Go après réflexion ça fait beaucoup »
  (Sabine). Options écartées : 4 Go fixes (proposition de la session) ; 200 Mo par fenêtre (12 des
  15 fenêtres mesurées auraient échoué seules) ; 300 Mo par fenêtre ; retirer des fenêtres sous la
  borne (le plafond y baisse plus que le volume : second `/code-review`). Limite : en période
  lourde, le rattrapage maximal dépasserait la borne et perdrait ses plus anciennes fenêtres (pire
  cas estimé, pas mesuré). — PR de #16
- **La table de la veille doit être close (modifiée après minuit UTC) ; sinon la source échoue
  et la collecte suivante reprend.** Décision de Sabine (plan validé). Pourquoi : GH Archive ajoute
  chaque heure à la table de son jour, la dernière vers 00:08 UTC le lendemain (constaté le
  2026-10-11) ; une collecte lancée juste après minuit compterait un jour incomplet. Limite
  (relecture du plan, constat 7) : c'est un indice, pas une preuve ; une heure manquante ou
  appauvrie, ou une table manquante au milieu d'un rattrapage, ne se voit pas. Constaté le
  2026-10-11 : les tables depuis le 2026-10-06 ont des heures appauvries et ont pourtant passé ce
  contrôle ([bigquery.md](../bigquery.md)) ; un contrôle de complétude est proposé en issue de
  suite. — PR de #16
- **Sans `GOOGLE_APPLICATION_CREDENTIALS`, `kb collect` saute GH Archive et le dit ; un résultat
  avec une ligne invalide est refusé entier.** Décision de Sabine (plan, puis tri de la revue).
  Pourquoi : une machine sans clé (CI, autre poste) ne doit pas faire échouer chaque collecte,
  comme Zotero sans son dossier ; le résultat est un classement, que la règle 1 des conventions
  refuse en entier. Option écartée : refuser seulement la fenêtre fautive (une exception de plus à
  la règle 1). Limite assumée : une ligne invalide revient avec sa fenêtre et bloque la source
  jusqu'à ce que la fenêtre sorte du rattrapage (15 jours au plus) ; risque jugé faible, la
  requête écartant les dépôts sans identifiant ni nom (14 `ForkEvent` sans dépôt le 2026-10-10).
  — PR de #16

## 2026-10-12

### Wiki : décisions de la nuit du 11 au 12/10

Prises par Sabine hors session, transmises par l'ordre de mission du 2026-10-12 ; consignées ici
telles que transmises. Le pourquoi n'est écrit que là où il a été donné.

- **Pas de Claude dans la chaîne du wiki (ni Claude Code ni modèle Claude), et pas de tri ni de
  score de la veille par un modèle.** Décision de Sabine ; pourquoi non transmis. **Levée le
  2026-10-15** pour le classement de la veille par sujet, dans une liste fermée (« POC du 25/10 »,
  décision 5), puis **le 2026-10-16** pour la vérification des fiches par un LLM juge
  (« Fiches de veille : le LLM juge »). **Révisée le 2026-10-20** : le juge sort du contrat des
  fiches (« Squelette E1 E3 : cadrage du 20/10 », décision 2).
- **Inférence sur Azure, en API compatible OpenAI ; le modèle est choisi par rôle en
  configuration.** Décision de Sabine. Pourquoi (transmis) : le modèle reste interchangeable.
  **Révisée le 2026-10-15** : Mistral pour le POC ; Azure (Foundry) pour l'inférence reste
  possible au 08/11 par la configuration, sans toucher au code, mais n'est pas tranché : cela
  dépend de la souscription de l'école (« POC du 25/10 », décision 6).
- **Une API dédiée à l'IA, distincte de l'API de données (#21).** Décision de Sabine. Pourquoi
  (transmis) : deux choses distinctes à montrer, et la voie du wiki n'attend pas celle des
  données.
- **Contrat entre les deux voies : l'ETL fournit des `.md` *cleansed*, la partie LLM produit des
  `.md` *curated*.** Décision de Sabine. Limite : aujourd'hui l'ETL écrit en SQLite, pas en
  `.md` ; la forme du contrat reste à fixer avant le code (« Décisions encore ouvertes »).
- **Le modèle renvoie des opérations JSON, validées puis appliquées par le code ; les jetons et
  le coût de chaque appel sont journalisés.** Décision de Sabine. Rejoint la veille du
  2026-09-23 (« Ce qui converge », point 3 : vocabulaire d'actions fermé, règle vérifiée par du
  code).
- **Écriture automatique quand les contrôles passent ; Sabine n'est sollicitée qu'en cas de
  doute.** Décision de Sabine. Pourquoi : « montrer la proposition avant d'écrire ne cadre pas
  avec le concept de la bibliothèque qui se range toute seule ». **Inverse** le choix de la
  veille du 2026-09-23 (« le LLM propose un plan, l'humain coche, le code applique. C'est notre
  choix. »).

### Wiki : la première version (v0, étape 2)

- **La première version du wiki fait l'ingest seul : un document déposé devient des opérations JSON (une note
  de lecture, des pages reliées), contrôlées par le code (liste fermée d'opérations, fidélité,
  lint mécanique), écrites si les contrôles passent, sinon mises dans une file « à voir ».**
  Décision de Sabine, sur recommandation. Pourquoi : c'est le noyau qui donne un point d'API
  appelant le modèle, un client et des métriques de fidélité et d'acceptation ; le reste double
  ce qu'il faut tester et surveiller. Options gardées pour plus tard : les contradictions
  signalées (un second appel par ingest, une métrique difficile à définir) ; l'interrogation du
  wiki (`kb ask`, un second point d'API).
- **Dans sa première version, le wiki prend les papiers Zotero seuls ; les clips viendront après #14, les notes
  plus tard.** Recommandation présentée à Sabine et non contredite ; à confirmer par elle à la
  relecture de cette PR. Pourquoi : l'extrait Zotero existe (#15), et le résumé d'un papier
  Zotero avait été décidé dans la nuit du 11 au 12/10 (ordre de mission). Le wiki lit l'extrait, pas la base : #138 ne le bloque pas.
- **Pour un papier Zotero, le wiki écrit une note de lecture, comme si quelqu'un avait lu
  l'article entier ; le modèle reçoit donc le texte intégral.** Décision de Sabine. Option
  écartée : un résumé fait du résumé de l'article et des surlignages (Sabine veut une note de
  lecture, pas un résumé du résumé).
- **Le texte intégral vient du PDF que Zotero garde en local, pour tous les papiers.** Décision
  de Sabine. Pourquoi, selon elle : la variété des sources (un papier hors arXiv a aussi son
  PDF). Options écartées : la page HTML d'arXiv (plus propre, mais seulement pour les articles
  LaTeX soumis depuis le 2023-12-01 et convertis sans erreur, 75 % selon arXiv 2605.16562 ; et
  l'accès est à vérifier contre la politique de collecte d'arXiv) ; le HTML d'abord et le PDF en
  repli (deux chemins à tester) ; les deux textes donnés au modèle (jetons doublés, et la
  fidélité n'y gagne rien : c'est le code qui la mesure). Limite assumée : le texte extrait d'un
  PDF porte des ligatures, des mots coupés et un ordre de lecture à reconstruire sur deux
  colonnes ; le vérificateur de fidélité normalise les deux textes avant de comparer ; formules
  et tableaux sortent abîmés. Un papier sans PDF, ou au PDF scanné, passe à l'état
  `full_text_unavailable` et va dans la file « à voir ». Fait entrer dans le wiki le texte
  intégral des PDF, jusque-là hors v0 au README.
- **La bibliothèque d'extraction est choisie après un essai sur 5 PDF de Sabine : la part des
  citations retrouvées mot pour mot, pour un extracteur simple (pypdf ou PyMuPDF), pymupdf4llm
  et Unstructured.** Décision de Sabine. Pourquoi : aucun banc d'essai trouvé ne compare ces
  outils sur des articles scientifiques ; les extracteurs simples rendent le texte plus
  fidèlement que les outils « pour LLM » sur DocLayNet (banc de 2026, pas sur des articles), et
  GROBID est en tête sur des articles arXiv (eSciBench, LREC 2026). La licence compte dans le
  choix : Unstructured est sous Apache 2.0 mais demande Tesseract et Poppler ; la mise en page
  de pymupdf4llm passe par PyMuPDF-Layout, sous licence propre et non open source ; PyMuPDF
  serait sous AGPL (non vérifié).

### Wiki : API et client

- **La commande `kb` passe par l'API IA pour atteindre le modèle (`kb` → API IA authentifiée →
  Azure).** Décision de Sabine, sur recommandation. Pourquoi : avec une API dédiée à l'IA, `kb`
  en est le client naturel ; un seul chemin et un seul endroit où l'on mesure jetons et coût ;
  les agents passeront par la même porte. Option écartée : `kb` appelle le modèle en direct
  (plus simple, mais l'API IA n'aurait plus de client, et il en faudrait un pour la grille
  seulement). Limite assumée : l'API doit tourner pour ingérer. **Révisée le 2026-10-15** : pas
  d'interface CLI dédiée au 25/10, et l'inférence passe par Mistral pour le POC (« POC du 25/10 »,
  décisions 1 et 6).
- **L'API IA tourne en local, sur la machine de Sabine, comme le reste de K-B ; pas d'hébergement
  en v0.** Décision de Sabine, sur recommandation (découpage de l'après-midi). Pourquoi, celui de
  la recommandation : cohérent avec le README (« les données restent sur ma machine ») et avec
  « K-B tourne en local » (2026-10-08) ; rien à déployer ; l'API n'est pas exposée à Internet.
  Option écartée : l'API sur Azure (une issue de déploiement d'environ 6 h, et une
  authentification exposée à Internet). **Révisée le 2026-10-15** : l'API IA est en local pour
  l'oral blanc, sur Azure Container Apps au 08/11 (« POC du 25/10 », décision 1). — #156
- **Le client `kb` s'authentifie par un jeton d'accès de courte durée et un *refresh token* qui
  change à chaque usage ; l'API les délivre elle-même, sans implémenter le protocole OAuth 2.**
  Décision de Sabine. Pourquoi : le client doit renouveler son accès quand il expire, et c'est le
  schéma que recommande l'OWASP : jetons d'accès courts, *refresh tokens* protégés par rotation
  (OAuth 2.0 Cheat Sheet ; Secrets Management Cheat Sheet, § 2.12 : « Use short-lived access
  tokens and implement a secure refresh token rotation strategy » ; lus par Context7 le
  2026-10-12) ; Azure CLI suit ce schéma (Microsoft Learn, « Authenticate to Azure using Azure
  CLI »). Options écartées : une clé fixe sans expiration (recommandée d'abord ; selon OWASP
  API2:2023, une clé d'API authentifie un client, pas une utilisatrice, d'après un résumé de
  recherche, page non lue en entier) ; un jeton renouvelé à la main par `kb login` (pas de
  renouvellement automatique). Limites assumées : sans fournisseur d'identité, c'est le code de
  K-B qui délivre les jetons ; environ 5 h, mécanisme connu de Sabine mais pas pratiqué depuis
  plusieurs mois. Suivre OAuth 2 en entier reste à voir au début de #160 (Sabine : peut-être lourd
  ici). **Révisée le 2026-10-15** : au 29/10, les clés restent fixes ; les jetons qui expirent
  sont prévus en ligne au 08/11 (« POC du 25/10 », décision 7). — #160

### Wiki : métriques

- **L'API émet ses mesures en OpenTelemetry (durée, jetons, coût, erreurs, fidélité,
  acceptation) et en garde une copie en local, une ligne par appel ; l'outil de restitution et
  d'alerte est choisi après une comparaison courte (Langfuse Cloud, Grafana Cloud, Azure
  Monitor, Grafana local).** Décision de Sabine. Pourquoi : la destination reste
  interchangeable, comme le modèle ; la copie locale garde l'historique quelle que soit la
  conservation de l'outil (30 jours sur Langfuse Hobby, 14 jours sur LangSmith Developer,
  pages de prix lues le 2026-10-12) et permet de changer d'outil sans rien perdre ; la fidélité
  est calculée par K-B de toute façon. Sabine accepte un outil dans le cloud, l'inférence y
  étant déjà. Critères de la comparaison : temps réel, alerte sur seuil, accessibilité de
  l'interface, région UE, coût. Options écartées : une commande `kb metrics` seule (pas un
  vecteur de restitution en temps réel) ; Dash en local (recommandé d'abord sur une contrainte
  « local » qui ne venait pas de Sabine) ; LangSmith (auto-hébergé sous contrat Enterprise
  seulement) ; Langfuse auto-hébergé (6 services, environ 11 CPU et 25 Gio). **Revient** sur
  « tableau de bord : plus tard » (2026-09-29) et sur le README (hors v0) : un outil de
  restitution entre en v0, étape 2. **Révisée le 2026-10-15** : la copie locale devient une
  ligne JSON par appel, sur stdout (« POC du 25/10 », décision 8 ; règle 4 de
  `.claude/rules/poc.md`). **Close le 2026-10-20** : l'outil est Grafana Cloud, en
  OpenTelemetry (« Squelette E1 E3 : cadrage du 20/10 », décision 4). La comparaison qui le fonde,
  selon ces critères : `docs/outils-de-suivi.md` (2026-11-08, « Outils de suivi : la comparaison
  de #163 »).

### Périmètre

- **La v0 se fait en deux étapes : l'étape 1 est l'import des données (le pipeline de veille),
  l'étape 2 est le wiki LLM ; le README les décrit sans date.** Décision de Sabine. Option
  écartée : garder « v1 = le wiki » et ajouter une section « Périmètre de la v1 » (recommandée,
  puis retirée par Sabine). Pourquoi : non dit ; je comprends (déduction, à confirmer) que le
  wiki entre dans la même livraison que la veille. **Inverse** le périmètre du 2026-09-29
  (« v1 : wiki de savoir ») ; les mentions antérieures de « v1 » dans ce journal désignent
  désormais l'étape 2 de la v0. Les dates restent tenues par time-knight.

### Wiki : les clips avant les PDF (révision de l'après-midi)

- **Le wiki prend d'abord les clips du Web Clipper ; les papiers Zotero, lus depuis leur PDF,
  viennent ensuite comme seconde source de `.md` *cleansed*.** Décision de Sabine. Pourquoi,
  selon elle : plus simple, un wiki qui marche plus vite, les PDF s'ajoutant après. Ce que cela
  évite au départ : l'essai d'extraction, le choix d'une bibliothèque et de sa licence, la
  normalisation du texte avant la vérification de fidélité ; un clip est déjà du Markdown.
  **Inverse** l'entrée « le wiki prend les papiers Zotero seuls » ci-dessus ; « le texte intégral
  vient du PDF » et « essai sur 5 PDF » restent décidés, pour la seconde source. Limites
  assumées : #14 (collecte des clips) dépend d'un coffre Obsidian qui n'existe pas encore, et
  elle est hors de la file E1 (son ordre revient à time-knight) ; les fixtures demandent de vrais
  clips de Sabine ; une page web porte un risque d'injection de consignes plus fort qu'un article
  publié, à tester avec un clip piégé ; un clip peut porter des noms, à inscrire au registre avec
  l'envoi à Azure.
- **Un clip produit sa note de lecture et met à jour les fiches thématiques qu'il touche : une
  fiche par sujet, qui rassemble ce qu'en disent les clips, chaque affirmation renvoyant au sien.**
  Décision de Sabine (reformulation confirmée). Ce sont les pages « concept » du wiki de Karpathy,
  déjà comprises dans l'ingest (« des pages reliées ») ; à ne pas confondre avec les fiches de
  veille du 2026-09-29, périodiques, faites sans LLM et reportées. **Révisée le 2026-10-15** :
  les fiches de veille par sujet sont faites par l'API IA au 25/10, et la compilation des
  clips en wiki passe après le 29/10 (« POC du 25/10 », décision 4).
- **Les sujets forment une liste fermée tenue par Sabine en configuration ; le modèle peut
  proposer un sujet nouveau, qui va dans la file « à voir ».** Décision de Sabine, sur
  recommandation. Pourquoi : même règle que l'écriture automatique (Sabine sollicitée seulement en
  cas de doute, et un sujet nouveau en est un) ; le code refuse un sujet hors liste. Options
  écartées : une liste fermée sans proposition (un nouveau sujet attend qu'elle l'ajoute) ; des
  sujets créés librement par le modèle (fiches qui risquent de proliférer et de se doublonner,
  par exemple « prompt injection » et « injection de prompt » ; la veille du 2026-09-23 note que
  WeKnora contrôle les slugs en double et dédoublonne avant d'interroger le LLM, l. 96 et 98).
  **Révisée le 2026-10-15**, et inversée : le modèle ne choisit que dans la liste fermée, sans
  proposer de sujet nouveau (« POC du 25/10 », décision 5).

### Import dans la base

- **Fin du rejeu complet : `kb import` ne rejoue plus tout `raw/` à chaque exécution, il
  n'importera que les fichiers bruts pas encore importés.** Décision de Sabine du 2026-10-06
  (revue d'architecture, W0), consignée ici après coup avec la PR qui en pose la condition.
  Pourquoi, selon elle : « la collecte est incrémentale ; l'import doit l'être aussi ». Rejouer
  tout le brut refait le travail des imports précédents, et le journal se remplit de doublons
  attendus (W5). Les options écartées n'ont pas été écrites le 2026-10-06. Limite assumée : la
  reconstruction complète (supprimer la base, `kb create-db`, `kb import`) reste possible et
  exceptionnelle. Jusqu'à #106, qui code l'import incrémental, chaque import relit encore tout. —
  PR de #105
- **La base dédoublonne les items ; la fusion en mémoire (`merge_items`) disparaît, et `merge.py`
  ne garde que la normalisation. La règle de chaque nature de source est une clause SQL de
  l'écrivain de sa sorte d'item, et nulle part ailleurs.** Décision de Sabine. Pourquoi : la
  fusion ne voyait que ce qu'elle avait chargé, ce qui obligeait à relire tout le brut ; c'est la
  condition de l'entrée précédente. Règles : flux de nouveautés (releases, alertes), premier vu
  gardé, par `INSERT INTO item … WHERE NOT EXISTS` ; catalogue d'état (CISA KEV) et flux avec
  révisions (arXiv), par `ON CONFLICT … DO UPDATE … WHERE … RETURNING`. Le flux de nouveautés n'a
  pas d'`ON CONFLICT` : le sous-type exige un item déjà créé, et ITEM n'a pas de clé naturelle.
  Options écartées, pour la place de la nature (raisons données dans la question, option retenue
  par Sabine) : une colonne `source.nature`, que rien ne lirait et qui changeait le MCD/MLD ; une
  constante Python, qui redisait le SQL sans contrôle de concordance. Écarté pour le flux de
  nouveautés : créer l'item, puis le supprimer si le sous-type existait (un `DELETE` hors purge,
  règle 5 des conventions). **Inverse** deux points du 2026-10-05 : `same_cve` (deux alertes d'un
  même CVE dans une source) n'est plus un doublon, les deux alertes pointent vers la même
  vulnérabilité ; et la raison de garder `url` en texte plutôt qu'en `HttpUrl` n'est plus « la
  fusion compare les URL », mais « la base garde l'URL donnée par la source, sans ses paramètres
  utm_* ». Ce qui a changé : le modèle du 2026-10-10 (ITEM sans URL, `vulnerability.cve_id`
  unique). Limite assumée : seul le doublon exact (même identifiant dans sa source) est trouvé ;
  le quasi-doublon (autre URL, autre clé Zotero) est laissé à #57 et #138, avec une empreinte de
  contenu. La nature des sources sans import est décidée par leur issue d'import (#138, #142,
  #14). — PR de #105
- **Catalogue d'état : un catalogue est complet, et seule sa collecte la plus récente compte.**
  Décision de Sabine : une ligne n'est écrite que si son fichier est collecté après le dernier
  catalogue de la même source déjà importé, à la seconde, et que son contenu diffère ;
  `revised_at` prend alors la date de cette collecte. Le fichier en cours ne compte pas comme
  « déjà importé », sauf s'il porte la version en base (un rejeu). Pourquoi : sans cette garde,
  un rejeu réappliquait un ancien catalogue par-dessus le récent (constat de la relecture du
  plan). Selon Sabine, « catalogue complet » est la définition de la nature, pas une exception
  propre à CISA. Option écartée : comparer à la collecte de la version en base. Une ligne
  identique ne déplace pas cette version, et un fichier importé en retard pouvait réécrire une
  version périmée. Précise l'entrée du 2026-10-07 (« dernière version »). Les retraits
  (`withdrawn_at`, #106) s'appuient sur cette règle. Limite assumée (constat de `/code-review`,
  écarté par Sabine) : une version que seul un fichier importé en retard porte n'entre jamais en
  base ; une base reconstruite dans l'ordre des collectes peut alors différer de la base tenue
  au fil des imports par `revised_at` et par le fichier rattaché à l'item, pas par le contenu.
  Signalé à #106. — PR de #105
- **Une ligne du journal d'import pour chaque item écarté, avec sa règle et la date comparée,
  dans un champ qui dit d'où vient la date.** Règles : `already_seen`, `unchanged`,
  `no_newer_version` et `revision_not_newer` ; champs : `compared_with_collected_at` et
  `compared_with_revised_at`. Plus d'`url` ni de `kept_url`. Décision de Sabine. Pourquoi, selon
  elle : le journal montre la date contre laquelle on a comparé, et un nom de date dit d'où vient
  la date. Options écartées : une seule étiquette pour le catalogue d'état, qui ferait dire au
  journal l'inverse de ce qui s'est passé pour un catalogue plus récent mais identique ; un champ
  commun au nom neutre (`compared_with`), qui ne dit pas d'où vient la date ; un horodatage par
  ligne, que #106 met dans le nom du fichier. — PR de #105
- **Le registre des fichiers bruts importés est la table `raw_data` : un fichier lu y entre,
  même sans item ou avec des entrées rejetées ; un fichier illisible n'y entre pas, il est relu
  et rejeté à chaque import.** Décision de Sabine (option A). Raison présentée à Sabine, qui a
  retenu A sans en donner d'autre : une page illisible signale un défaut du lecteur ou du brut,
  pas une donnée ; la garder visible jusqu'à sa correction coûte une relecture, et l'import qui
  suit la correction la lit sans reconstruction. Option écartée (B) : inscrire le fichier
  illisible ; lu une fois, il n'aurait été relu que par une reconstruction (un écart de plus
  entre la base tenue et la base reconstruite), et un catalogue CISA illisible serait devenu le
  « dernier catalogue importé », qui bloque les catalogues valides plus anciens. Une collecte mal
  nommée n'a pas de date de collecte (`collected_at` NOT NULL) : elle n'est jamais inscrite.
  Limite assumée : un fichier illisible revient dans le journal de chaque import. — PR de #106
- **Le journal d'import est écrit dans la transaction, avant la validation de la base, et
  supprimé si la validation échoue.** Décision de Sabine. **Inverse** le choix de #105 (« le
  journal est écrit après la base ; s'il échoue, la base garde l'import »). Ce qui a changé : un
  fichier inscrit au registre n'est plus relu, donc un journal perdu après la validation
  perdrait pour toujours la trace de ses rejets et de ses écarts (raison présentée à Sabine,
  qui l'a retenue). — PR de #106
- **Un journal par import, `import-log-<AAAA-MM-JJTHHMMSSZ>.jsonl`, jamais réécrit, et chaque
  ligne porte l'instant de son import (`imported_at`, ISO 8601 UTC à la seconde).** Décision de
  Sabine du 2026-10-12, d'après le Logging Cheat Sheet de l'OWASP (« Log date and time
  (international format) »). **Inverse** l'option écartée par #105 dans l'entrée précédente
  (« un horodatage par ligne, que #106 met dans le nom du fichier ») : le nom et chaque ligne
  sont maintenant datés. La valeur est l'instant de l'import, le même que le nom du fichier :
  l'heure de chaque constat n'est pas mesurée, tout se fait dans une transaction. Un journal de
  la même seconde arrête l'import sans rien écrire. — PR de #106
- **Catalogue d'état : une ligne connue absente d'un catalogue collecté après le dernier
  catalogue importé est retirée (`withdrawn_at` = sa collecte, la première absence garde sa
  date) ; si elle réapparaît, elle est réécrite, `withdrawn_at` vidé et `revised_at` daté. Un
  catalogue dont une entrée est rejetée, ou qui ne donne aucun item, ne retire rien.** Décision
  de Sabine, qui applique le MCD du 2026-10-07 avec la règle du catalogue d'état de #105.
  **Écart au MCD**, accepté par Sabine : une ligne absente d'un catalogue avec rejet est retirée
  au catalogue propre suivant, et datée de lui, pas du premier qui a constaté son absence. Raison
  présentée à Sabine, qui l'a retenue : une ligne rejetée est présente, pas absente, et la
  retirer serait faux (échouer fermé). Le retrait est déclenché après les items d'un fichier de
  sorte `vulnerability` : la règle de la nature reste dans l'écrivain de sa sorte. — PR de #106
- **Un CVE qu'un catalogue importé en retard est seul à apporter, ou dont il remplit les
  colonnes KEV (CVE créé par une alerte), est écrit retiré, à la date du dernier catalogue
  importé ; le catalogue en retard ne retire rien d'autre et ne fait rien réapparaître.**
  Décision de Sabine. **Remplace pour ce cas** la règle de #105 (un fichier plus ancien que le
  dernier catalogue n'écrit rien en base, et laisse quand même une ligne au journal) et la
  limite acceptée dans le commentaire de #106. Pourquoi, selon elle : la reconstruction donne le
  même contenu. Le constat (relecture du plan, simulé sur le schéma) : sans cela, un catalogue en
  retard rendait actif un CVE que le dernier catalogue ne liste pas, et la base tenue différait
  de la base reconstruite par son contenu, pas seulement par ses dates. Limite assumée : après un
  catalogue en retard, une base reconstruite peut différer par `revised_at`, `withdrawn_at` et le
  fichier rattaché à l'item, pas par son contenu ni par ses lignes retirées, sauf dans un cas
  (constat de `/code-review`, limite acceptée par Sabine, option A) : un CVE dont la ligne est
  rejetée dans le dernier catalogue, puis apporté par un catalogue en retard, est écrit retiré
  alors qu'une base reconstruite le trouve actif ; un catalogue dont toutes les lignes sont
  rejetées compte comme le dernier catalogue. Options écartées : garder dans `raw_data` le nombre
  de rejets d'un fichier (une colonne de plus, qui change le MCD et sort de #106) ; écrire actifs
  les CVE d'un catalogue en retard (le contenu différerait dans le cas courant). — PR de #106

### Wiki : le modèle de la démonstration (découpage de l'après-midi)

- **La démonstration de l'oral blanc des 29 et 30/10 se fait sur un vrai modèle, qui compile un
  clip nouveau en direct.** Décision de Sabine ; pourquoi non dit. Options écartées : démontrer
  sur le modèle de remplacement, avec des clips aux réponses préparées (recommandée : le jalon
  est déjà chargé et le chemin complet tourne sans vrai modèle) ; le remplacement d'abord, le vrai
  modèle si le temps le permet. Le modèle de remplacement reste celui des tests et de la CI.
  **Révisée le 2026-10-15** : la démonstration de l'oral blanc porte sur les fiches de veille
  par sujet (« POC du 25/10 », décision 4). — #158
- **Une clé gratuite (Gemini ou Mistral, que Sabine a déjà) d'abord, puis Azure, sur le compte
  payé par l'école.** Décision de Sabine. Pourquoi, selon elle : limiter les coûts pendant le
  développement. **Modifie** « inférence sur Azure » (nuit du 11 au 12/10) : Azure vient en second.
  Option écartée : Azure d'emblée. Limites assumées : en offre gratuite, le texte envoyé peut
  servir à l'entraînement du fournisseur (Gemini : page de prix ; Mistral : plan Experiment,
  retrait possible ; recherches du 2026-10-12), à inscrire au registre (#157) ; changer de modèle
  peut changer la fidélité, la consigne sera peut-être à reprendre (#170). **Révisée le
  2026-10-15** : Mistral pour le POC ; Azure (Foundry) pour l'inférence reste possible au
  08/11 par la configuration, sans toucher au code, mais n'est pas tranché : cela dépend de la
  souscription de l'école (« POC du 25/10 », décision 6). — #158, #170

### Collecte : clips

- **La clé d'un clip est son URL source, paramètres `utm_*` retirés comme pour les autres
  sources ; pas d'empreinte de contenu, la limite est écrite.** Décision de Sabine, sur
  recommandation. Pourquoi, celui de la recommandation : c'est la normalisation déjà codée
  (`remove_tracking_parameters`, `merge.py`), sans ajout. Options écartées :
  une empreinte du titre et du texte normalisés contre les quasi-doublons (environ 1 h de plus,
  et « normalisé » à définir) ; une normalisation plus poussée de l'URL (une règle propre aux
  clips) ; le chemin du fichier dans le coffre (un même article gardé deux fois fait deux clips).
  Limite assumée : un même article gardé sous deux URL donne deux clips. La nature de la source
  (règle de dédoublonnage par la base) reste à décider par #14, comme le prévoit l'entrée de #105. — #14

### Collecte : articles TLDR

Mesures citées : les 18 pages collectées du 2026-09-30 au 2026-10-09 (3 éditions, 315 entrées,
40 sponsorisées, 3 offres d'emploi de TLDR, 272 articles).

- **La clé d'un article TLDR reste (édition, date de l'édition, rang), celle de l'entrée du
  2026-10-07 ; l'URL est rangée sans `utm_*`, ni unique ni dans la clé ; pas d'empreinte de
  contenu, les limites sont écrites dans `docs/specs-collecte.md`.** Décision de Sabine, sur
  recommandation (« ok avec 1 A »). Pourquoi, celui de la recommandation : avec cette clé, l'URL
  n'entre pas dans l'identité, donc sa normalisation ne change aucun doublon, et la règle est la
  même pour toute la base, comme pour les clips ; la clé ne donne aucune collision sur le brut.
  Options écartées : la clé (édition, date, URL), qui tient si une page est réordonnée entre
  deux collectes, mais revient sur la clé du 07/10 pour un cas non observé ; une empreinte du
  titre et du résumé normalisés (environ 1 h, pour 1 cas sur le brut, une offre d'emploi) ; une
  normalisation plus large de l'URL (casse de l'hôte, `www.`, paramètres), qui ne fusionnerait
  que cette offre et casserait les URL du type `?id=123`. Limites assumées : un même article
  résumé par deux éditions, ou repris un autre jour, fait deux lignes (10 URL sous deux clés,
  toujours avec deux résumés différents) ; un même contenu sous une autre URL n'est pas
  reconnu. Tranche, pour TLDR, ce que l'entrée de #105 laissait à #57 ; #138 reste concerné
  pour Zotero. — PR de #57
- **Le rang compte tous les `<article>` de la page, entrées sponsorisées et offres d'emploi
  comprises.** Décision de Sabine, sur recommandation (« Je valide tes recommandations »).
  Pourquoi, celui de la recommandation : le rang se vérifie à l'œil sur la page brute, et
  changer ce qui est écarté ne renumérote aucun article (les offres d'emploi ont été écartées
  le jour même sans décaler un rang). Option écartée : le rang parmi les articles gardés, qui
  ne bouge pas si un encart sponsor change mais dépend du filtre de K-B. Limite assumée : le
  jour de la dernière collecte est relu à chaque collecte ; si tldr.tech a modifié la page
  entre-temps (entrée ajoutée, retirée ou déplacée), la première version vue reste et un
  article décalé peut être écarté à tort ou entrer deux fois. Non mesurable sur le brut, où
  aucune page n'est collectée deux fois. — PR de #57
- **La colonne `newsletter_article.publication_id` (papier cité, entrée du 2026-10-07) est
  créée et laissée vide.** Décision de Sabine (« 2 B »), contre la recommandation de la
  session, qui était de la remplir pour un lien `https://arxiv.org/abs/<id>` (environ 20 min,
  2 articles sur le brut). Pourquoi : Sabine ne l'a pas dit ; l'option lui était présentée
  comme celle qui tient l'estimation de l'issue (déduction de la session, non confirmée).
  Option écartée aussi : ne pas créer la colonne, un écart à l'entrée du 07/10. Limite
  assumée : une colonne et son index sans écrivain, jusqu'à l'issue qui la remplira
  (« Décisions encore ouvertes »). — PR de #57
- **Le HTML des pages TLDR est lu avec BeautifulSoup (`beautifulsoup4`), sur l'analyseur
  `html.parser` de la bibliothèque standard.** Décision de Sabine (« je veux beautiful soup »),
  qui écarte la proposition de la session : `html.parser` seul, sans dépendance nouvelle.
  Pourquoi : réemployer ce qui marche, brief09 et `feat/tldr` lisant déjà ces pages avec
  BeautifulSoup (motif relayé par time-knight, dans la ligne de la consigne du 12/10 sur le
  réemploi de brief09). Non ajouté : `lxml`, l'analyseur de brief09, une dépendance de plus à
  soumettre. Conséquence : deux paquets de plus dans `uv.lock` (`beautifulsoup4`,
  `soupsieve`). K-B décode lui-même l'UTF-8 : BeautifulSoup devinerait l'encodage.
  **`soupsieve` est verrouillé en 2.10 (du 2026-09-24), pas en 3.0.3** : décision de Sabine,
  sur recommandation, après un constat de la revue de sécurité. Pourquoi : la 3.0.3 avait été
  publiée le jour même, 5 heures avant le commit, et aucune base d'alertes ne connaît encore
  une version si récente ; `beautifulsoup4` 4.15.0 accepte `soupsieve>=1.6.1`. Limite
  assumée : la borne n'est que dans `uv.lock`, un `uv lock --upgrade` la lèvera. — PR de #57
- **Les offres d'emploi de TLDR sont écartées comme les entrées sponsorisées, sans rejet ni
  ligne de journal, reconnues par leur lien (`https://jobs.ashbyhq.com/tldr.tech/`).**
  Décision de Sabine : « Ce ne sont pas des articles souhaités ». Ajout au périmètre de #57,
  dont le critère de fin a été modifié. Règles écartées, mesurées sur le brut : par les mots
  du titre ou du lien (« job », « hiring », « recruit »…), qui écartait à tort 3 vrais
  articles sur 6 entrées trouvées ; par la parenthèse finale du titre, qui écarterait tout
  article dont TLDR invente une mention ; par la phrase du résumé, qui dépend de la rédaction
  de chaque offre. Limite assumée : une offre publiée ailleurs que sur ce site d'offres entre
  comme article. — PR de #57
- **`HttpsUrl`, le type d'URL commun à toutes les sources, refuse ce que `urlsplit` refuse,
  et un lien sans hôte.**
  Décision de Sabine, sur recommandation, après un constat de la relecture du plan : un lien
  mal formé (`https://[x`) passait l'item, puis faisait lever `urlsplit` à la normalisation
  (`merge.py`) ; l'import s'arrêtait sur une trace Python, et de même à chaque import suivant.
  Les deux revues de la PR ont trouvé le même arrêt pour un lien sans hôte
  (`https://?utm_source=…`, réduit à `https://` une fois ses `utm_*` retirés) : refusé aussi.
  Pourquoi, celui de la recommandation : une seule entrée ne doit pas bloquer tout l'import
  (règle 1 des conventions) ; TLDR est la première source dont les liens viennent de tiers.
  Option écartée : ne rien changer et écrire la limite. Aucun des liens collectés ne
  déclenche le cas. — PR de #57

## 2026-10-13

### Modèle de la base : TENDANCE

- **GH Archive est un flux de nouveautés appliqué à la fenêtre entière : le premier classement vu
  d'une fenêtre est gardé entier ; une fenêtre qu'un autre fichier brut apporte de nouveau est
  écartée entière et tracée au journal d'import.** Décision de Sabine, sur la recommandation de
  la session ; raisons présentées, qu'elle a retenues sans en donner d'autre : une fenêtre de
  3 jours clos est un fait publié qui ne devrait plus changer, comme une release ; c'est la
  seule nature qui garde « une fenêtre = un classement cohérent » (30 premiers par étoiles et 30
  premiers par forks d'un même comptage) sans colonne nouvelle ni suppression ; une base
  reconstruite donne la même base. C'est une **variante nouvelle** du flux de nouveautés, qui
  compare jusque-là par clé de sous-type (2026-10-12) : la clé de `trend` est (`window_end`,
  `repository_id`), mais comparer par clé ajouterait à une fenêtre les dépôts entrés dans le
  classement à une seconde collecte, et mélangerait deux comptages. Options écartées : catalogue
  d'état (le dernier classement remplace l'ancien : il faut retirer les dépôts sortis du
  classement, donc une colonne `withdrawn_at` que la table décidée le 2026-10-08 n'a pas, ou une
  suppression hors purge, et une comparaison par fenêtre que la règle de CISA ne fait pas) ;
  flux avec révisions (GH Archive ne donne pas de date de révision, il faudrait la date de
  collecte, et les dépôts sortis du classement resteraient avec leurs anciens chiffres). Limites
  assumées : un compte faux à la première collecte reste, et les fenêtres du 2026-10-10, du
  2026-10-11 et du 2026-10-12 ont été comptées, en tout ou en partie, sur des tables appauvries
  ([bigquery.md](../bigquery.md)) : les corriger demande de retirer leur fichier brut et de
  reconstruire la base ; « premier vu » veut dire premier
  importé ; une fenêtre annoncée sans aucune ligne ne laisse pas de trace. — PR de #142
- **Les tables `repository` et `star_gain` sont retirées du schéma, avec leurs tests.** Décision
  de Sabine, sur la recommandation de la session ; raison présentée, qu'elle a retenue : ce sont
  les tables du modèle que TENDANCE remplace (2026-10-08), vides et sans code qui les lise ou les
  écrive, et les garder ferait porter au schéma deux modèles de la même donnée. Option écartée :
  les laisser (il aurait fallu dire jusqu'à quand). Clôt la décision ouverte du 2026-10-10.
  Limite : le dépôt n'a pas d'outil de migration, une base existante garde ses deux tables
  jusqu'à sa reconstruction, que `trend` demande déjà ; les MCD et MLD datés du 2026-10-12, qui
  les nomment encore, sont des instantanés et ne sont pas corrigés. — PR de #142
- **La table `trend` : une ligne par fenêtre et par dépôt, étoiles et forks gagnés, rattachée à
  sa donnée brute ; `window_end` est un jour, écrit à minuit UTC, et son `CHECK` n'accepte que
  minuit ; `repository_name` est borné à 255 caractères, dans `TrendRow` et par un `CHECK`, et
  `TrendRow` y refuse tout caractère de contrôle, NUL compris ; les trois entiers sont tenus sur
  64 bits.** Forme décidée le
  2026-10-08 ; ces précisions sont des choix de la session, validés par Sabine avec le plan.
  Pourquoi : deux heures d'un même jour feraient deux clés ; la borne applique la décision du
  2026-10-10 (« la borne tient ce qu'une source peut écrire », tenue dans l'item et en base) ;
  le `GLOB` de SQLite s'arrête au premier NUL et refuserait un nom que le motif accepte, ce qui
  arrêterait chaque import (constat de la relecture du plan) ; un autre caractère de contrôle
  (une séquence d'échappement) partirait au terminal qui affiche le nom (constat des deux
  revues) ; `sqlite3` lève `OverflowError` au-delà de 64 bits (essai du 2026-10-13). 255 est une borne large, pas celle de GitHub : le
  plus long nom de la collecte du 2026-10-11 fait 38 caractères, et la limite de GitHub n'a pas
  été confirmée par une source officielle. Limite assumée : un nom plus long, ou avec un caractère de
  contrôle, fait refuser le classement entier dès la collecte. Les totaux lus par GraphQL (`stars_total`,
  `forks_total`) n'entrent pas ici : pas de colonne sans écrivain (#143). — PR de #142

### Import dans la base : TENDANCE

- **L'écrivain de `trend` vit dans `import_items.py`, comme celui des articles TLDR : écart
  temporaire à la règle 5 des conventions.** Décision de Sabine : « on fait les sources
  manquantes avant. je veux que ça marche, ensuite on range ». **Revient sur** la raison de
  l'entrée du 2026-10-11 (#16 s'arrêtait à l'extraction pour ne pas ajouter de SQL dans
  `import_items.py` avant son déplacement). Ce qui a changé : la source big data devait entrer
  en base pour E1, et le déplacement du SQL d'écriture (#135) vient après les sources. La
  commande de #135 (« ne renvoie que des fichiers de `src/k_b/database/` ») verra ce SQL ; sa
  phrase « un écrivain par sorte d'item » ne nomme pas `trend`. — PR de #142
- **Le brut `gh_archive` est lu par un lecteur à part, `read_trend_files`
  (`src/k_b/sources/gh_archive.py`), que `run_import` appelle à côté du lecteur des items ; le
  contrat `SourceReader` et le lecteur générique ne sont pas généralisés.** Décision de Sabine,
  relayée par time-knight : que cela marche d'abord, la structure ensuite ; `trend` reste hors
  d'`item` (2026-10-08). Option écartée : étendre `SourceReader`, qui rend un `Item`, à autre
  chose qu'un item. Limite assumée : deux chemins de lecture, le second refaisant en une
  vingtaine de lignes le parcours d'un dossier, le saut d'un fichier déjà importé et les
  rejets ; la sorte `gh_archive` reste déclarée sans lecteur d'items dans `source_kinds.py`.
  Aucune issue ne porte la réunion des deux chemins (ci-dessous, décisions ouvertes). — PR de #142
- **`TrendRow` est défini dans `items.py`, et non dans le module de sa source : écart à la
  2e puce de la règle 4 des conventions (« chaque source garde son modèle Pydantic dans son
  module »).** Décision de Sabine, sur la recommandation de la session. Pourquoi : l'écrivain est
  dans un module générique, et `tests/test_module_dependencies.py` interdit à un module générique
  d'importer une source ; la 1re puce de la même règle met dans `items.py` « un type […] que la
  base contraint ». `TrendsExtract`, le document brut, reste dans `gh_archive.py`. Options
  écartées : un second type de 5 champs côté générique (les champs écrits deux fois) ; un
  `Protocol` (abstraction sans second usage) ; l'écrivain dans `gh_archive.py` (une source ne
  fait que lire, seconde commande de la règle 5). `.claude/rules/conventions.md` n'est pas
  modifié. — PR de #142
- **Les fichiers d'items et les classements sont écrits en une seule suite, dans l'ordre des
  collectes ; au journal d'import, une fenêtre écartée fait une ligne, à la forme des autres
  (`already_seen`, `source_item_id` = le dernier jour de la fenêtre), sans nom ni identifiant de
  dépôt.** Choix de la session après la relecture du plan, validés par Sabine avec le plan.
  Pourquoi : écrits après tous les items, les classements donnaient à une base reconstruite
  d'autres `raw_data.id` qu'à une base tenue jour après jour ; c'est la fenêtre que la règle
  écarte, et le nom d'un dépôt porte le login de son propriétaire. Option écartée : une ligne
  par dépôt écarté (jusqu'à 60 par fenêtre, avec `repo.id`). — PR de #142

### Modèle de la base : bibliothèque Zotero

Décisions de Sabine (« ok pour tout »), sur les recommandations de la session ; les pourquoi
sont ceux de ces recommandations. Mesuré sur l'extrait réel du 2026-10-13 : 5 documents, tous
arXiv, aucun dans le brut arXiv ; 6 surlignages ; 11 étiquettes, toutes automatiques ; un PDF
par document.

- **Un document Zotero est un sous-type d'item propre à Zotero, `zotero_entry`
  (`kind` = `zotero_entry`) : clé Zotero unique, type, titre, URL, date d'ajout, et une clé
  étrangère facultative vers PUBLICATION. Item > entrée Zotero > publication, à côté de item
  arXiv > publication.** C'est la piste de Sabine du 2026-10-12. Pourquoi : le plus petit chemin
  qui lit l'extrait vers la base. Options écartées : un sous-type DOCUMENT commun à la
  bibliothèque, clips compris (environ 45 min de plus, et ce serait trancher dès maintenant ce
  que les clips mettront en base, ce qui revient à #14) ; CONTENU, qui répond à « où garder le
  texte complet », hors de cette issue. DOCUMENT ou CONTENU reste ouvert pour le texte complet.
  Limite : si les clips demandent un sous-type commun, `zotero_entry` sera à généraliser.
  — PR de #138
- **Une publication peut être décrite par plusieurs items : son item arXiv
  (`publication.item_id`, unique), 0 à n entrées Zotero, 0 à n articles TLDR. Quand arXiv n'a
  pas vu le papier, personne ne remplit ses colonnes arXiv : la publication est créée avec sa
  seule référence arXiv, comme une CVE créée par une alerte GitHub ; le titre vu par Zotero
  reste dans `zotero_entry.title`.** Répond à la question que le 2026-10-08 laissait à Zotero
  (« qui remplit les colonnes quand arXiv n'a pas vu le papier »). Pourquoi : le `CHECK` de
  PUBLICATION ne change pas, et arXiv reste la seule source de vérité de ses colonnes. Option
  écartée : Zotero les remplit et arXiv les remplace (un `CHECK` à changer, deux sources de
  vérité). — PR de #138
- **Un document Zotero hors arXiv est une entrée Zotero sans publication ; son URL est
  facultative.** Pourquoi : ses surlignages gardent leur place, sans coût ; Zotero n'impose pas
  d'URL. Aucun document hors arXiv dans l'extrait du 2026-10-13. — PR de #138
- **Le chemin des PDF et les étiquettes restent hors base, dans l'extrait brut.** Pourquoi :
  rien ne les lit en base aujourd'hui ; le wiki lit l'extrait (2026-10-12). Précise « K-B garde
  leur chemin » (2026-10-09) : K-B le garde dans son brut. Options écartées : deux listes JSON
  dans `zotero_entry` (environ 20 min de plus) ; des tables `zotero_pdf` et `tag` (environ 1 h
  de plus, deux tables au MCD et au MLD). Limite : `kb search` ne peut pas filtrer par
  étiquette. — PR de #138
- **Les dates Zotero sont nommées par leur événement : `zotero_entry.saved_at` (date d'ajout du
  document) et `highlight.highlighted_at` (date d'ajout du surlignage). Aucune date constatée
  par K-B n'est ajoutée : la collecte est dans `raw_data.collected_at`. Le champ `date` du
  document n'est pas gardé en base.** Pourquoi : pour un papier arXiv, arXiv donne la date
  (`publication.submitted_at`) ; le champ `date` de Zotero, observé sous la forme
  « AAAA-MM-JJ AAAA-MM-JJ », peut être partiel (une année seule), ce que le `CHECK` des dates
  refuserait. Limite : un document hors arXiv n'a pas de date de publication en base. Le
  renommage des colonnes de date existantes n'est pas tranché (« Décisions encore ouvertes »).
  — PR de #138
- **`highlight` reçoit le commentaire du surlignage (`comment`, facultatif) ; la page et la clé
  du PDF restent dans l'extrait ; les auteurs vus par Zotero ne sont pas gardés en base.**
  Pourquoi : le commentaire est déjà au registre ; la page et le PDF n'ont pas d'usage en base ;
  minimisation (RGPD, RGESN 1.6) : arXiv donne les auteurs d'un papier arXiv. Limite : un
  document hors arXiv n'a pas d'auteurs en base. — PR de #138

### Import dans la base : Zotero

- **Zotero est un catalogue d'état, aux deux niveaux, l'entrée Zotero et le surlignage : seul le
  dernier extrait compte. Une entrée ou un surlignage modifié dans Zotero est réécrit, et
  `revised_at` prend la date de la collecte ; une entrée ou un surlignage absent d'un extrait
  plus récent est marqué retiré (`withdrawn_at`), jamais supprimé de la base.** Décision de
  Sabine. Pourquoi, selon elle : « les articles et mes surlignages et annotation dans zotero
  alimente le wiki. Les fiches de lecture qui découleront de ses articles doivent rester dans
  mon coffre fort même si je supprime physiquement l'article dans zotero » ; « si je modifie un
  commentaire ou un surlignage déjà importé, la base doit pouvoir se mettre à jour ». Suit le
  précédent de CISA KEV (2026-10-12, « Catalogue d'état », `withdrawn_at`), avec ses écarts : un
  extrait avec un rejet ne retire rien, un extrait importé en retard ne change rien. Retirer
  sans supprimer suit aussi la règle 5 des conventions (`.claude/rules/conventions.md`,
  « Écarté » : K-B « ne supprime que par la purge »). Options
  écartées : flux de nouveautés (premier vu gardé : ne suit pas les modifications) ; flux avec
  révisions (il faut la date de modification de Zotero, que la requête d'extraction de #15 ne
  lit pas, et les extraits existants ne l'ont pas). Coût : environ 1 h 30 de plus que
  l'estimation de l'issue (deux règles de retrait, `revised_at` et `withdrawn_at` sur
  `zotero_entry` et `highlight`, leurs tests). — PR de #138
- **Une entrée Zotero est reconnue par sa clé Zotero seule (`zotero_entry.zotero_key`, unique),
  un surlignage par la sienne (`highlight.zotero_key`) ; pas d'empreinte de contenu, la limite
  est écrite.** Décision de Sabine, sur la recommandation de la session. Pourquoi : deux entrées
  du même papier arXiv pointent déjà vers la même publication (même `arxiv_id`), le doublon se
  voit par une requête ; l'extrait n'a aucun texte du document, une empreinte ne porterait que
  sur le titre (deux titres proches confondus, un titre retouché non reconnu). Précédents : les
  clips et les articles TLDR, sans empreinte (2026-10-12). Option écartée : une colonne
  `content_fingerprint` sur le titre normalisé (environ 45 min). Limite : un document hors arXiv
  enregistré deux fois fait deux entrées que rien ne relie. La clé Zotero est unique dans une
  bibliothèque ; seule la bibliothèque personnelle est extraite. — PR de #138

## 2026-10-14

### API de données

La spécification est [specs-api.md](../specs-api.md). Décisions de Sabine du 2026-10-14
(commentaire de l'épic #21) ; les pourquoi marqués « sur recommandation » sont ceux que
time-knight a recommandés et que Sabine a acceptés le 2026-10-14.

- **« Quoi de neuf » : `since` porte sur la date que la source donne, propre à chaque sorte
  d'item : `publication.submitted_at`, `vulnerability.date_added`, `release.published_at`,
  `advisory.published_at`, `newsletter_article.edition_date`, `zotero_entry.saved_at`.**
  Décision de Sabine. Pourquoi, sur recommandation : la date de la source répond à « qu'est-ce
  qui est sorti cette semaine ? ». Options écartées : la date de collecte (`raw_data.collected_at` :
  un ajout de source ou une collecte relancée ferait passer des items anciens pour nouveaux) ; une
  date de révision (une révision ferait remonter un item ancien comme nouveau ; raison confirmée
  par Sabine). **Remplace** « P1 filtre alors sur publié ou révisé depuis N jours »
  ([clarification du modèle](../2026-10-07-clarification-modele.md), 2026-10-07). Limite
  assumée : un item ancien découvert cette semaine n'apparaît pas dans « quoi de neuf ». — PR de #182
- **Identifiant : `item.id` dans le chemin (`/items/{item_id}`) ; les clés naturelles (`arxiv_id`,
  `cve_id`, `ghsa_id`…) sont des champs de la réponse.** Décision de Sabine. Pourquoi, sur
  recommandation : la clé naturelle change de forme selon la sorte, certaines contiennent un
  « / » (l'ancien identifiant arXiv, `hep-th/9901001`), ce qui casse le chemin, et celle d'un article TLDR tient en trois champs
  (`edition`, `edition_date`, `rank`). Option écartée : la clé naturelle dans le chemin, une
  route par sorte. S'appuie sur l'`id` stable en usage réel (2026-10-10, « Modèle de la base »).
  — PR de #182
- **`kind` garde la valeur `paper`, et se filtre à valeurs exactes : `kind=vulnerability` ne
  ramène pas les alertes GitHub (`advisory`).** Décision de Sabine. Pourquoi, sur
  recommandation : `paper` est déjà la valeur du code et de la base ; en changer coûterait le
  schéma, le code, les tests et le contrat d'API. Option écartée : `publication`, le nom de la
  table de référence. Clôt la question ouverte de la relecture du 2026-10-09 (« si
  `kb search --kind vulnerability` ramène aussi les alertes GitHub »). — PR de #182
- **Accès par une clé fixe par client nommé : la variable `KB_API_KEY_<CLIENT>`, révocable seule ;
  le journal nomme le client, jamais la clé.** Décision de Sabine. Pourquoi des clés fixes ici,
  alors que l'entrée « Wiki : API et client » (2026-10-12) les écarte pour l'API IA, sur
  recommandation : la clé identifie le programme qui appelle (le terminal ou un script de Sabine,
  un agent, l'API IA) ; aucune personne ne se connecte, et l'API n'a qu'une propriétaire. C'est
  l'usage admis par OWASP API2:2023, « How To Prevent » : « API keys should not be used for user
  authentication. They should only be used for API clients authentication »
  ([API2:2023](https://api-security.owasp.org/editions/2023/en/0xa2-broken-authentication/),
  citation relevée par recherche web le 2026-10-14, confirmée par la relecture) ; l'API est
  locale, en lecture seule. Options
  écartées : une clé partagée (on ne retire pas un client seul) ; un jeton signé (JWT) avec
  renouvellement, parce que la même API délivrerait et vérifierait le jeton, en local, pour
  environ 5 h (route de connexion à protéger contre le forçage, clé de signature,
  renouvellement), et que l'expiration et le renouvellement des jetons sont déjà portés par
  l'API IA (#160). Limite assumée : une clé n'expire pas ; un retrait ne prend effet qu'au
  redémarrage de l'API. — PR de #182
- **Recherche `q` par `LIKE` maintenant, FTS5 triée par BM25 après l'oral blanc (#188) : écart
  temporaire à l'entrée « Bibliothèque et recherche » du 2026-10-09.** Décision de Sabine.
  Pourquoi, sur recommandation de time-knight, acceptée par Sabine le 2026-10-14 : FTS5 demande
  une table à remplir à chaque import et une reconstruction de la base. Constat : la table est
  ajoutée à une base existante par une migration (#186), selon le critère de #188. Limites assumées : `LIKE`
  exige les accents exacts (`vulnerabilite` ne trouve pas « Vulnérabilité ») et trie par date ; le
  passage à BM25 changera l'ordre des résultats avec `q`, annoncé par une nouvelle version de la
  spec et de l'OpenAPI. **Révisée le 2026-10-15** : aucun FTS5 nouveau ; la recherche plein
  texte se fera avec PostgreSQL (`tsvector`) après le 08/11, et #188 sera à reformuler
  (« POC du 25/10 », décision 2). — PR de #182
- **Paquet `src/k_b/data_api/`, organisé par rôle : `app.py` (`create_app`, rassemble les
  routers) ; `routers/item_router.py`, `routers/trend_router.py` (les routes, une entité par
  fichier) ; `schemas/item_schema.py`, `schemas/trend_schema.py` (les modèles Pydantic des
  réponses) ; `errors.py` (la gestion d'erreur, écrite une fois) ; `dependencies.py` (la clé par
  client, la connexion par requête) ; `request_log.py` (une ligne de journal par requête).**
  Décision de Sabine. Pourquoi, selon elle : c'est l'organisation apprise pendant la formation
  DWWM (titre professionnel Développeur web et web mobile), un dossier par rôle, un fichier par
  entité, où ce qui est où se lit d'un coup d'œil ; la doc FastAPI « Bigger Applications » suit
  le même plan (un `APIRouter` par module, `include_router`). Options écartées : un dossier
  `controllers/` (avec des routes en lecture seule, il ne ferait que passer l'appel à
  `database/reading.py` ; en FastAPI, la fonction de route est le contrôleur) ; les fichiers à
  plat `routes.py` et `responses.py` (moins lisibles quand l'API grandit, et quand l'API IA
  reprendra le même plan). Les issues qui servent la liste (#184) et le détail (#185) décrivent
  encore l'organisation à plat : leur mission les mettra à jour. **Complétée le 2026-10-15** :
  `health.py` (la route `/health`, sans clé ; « API de données : réglages et santé »). — PR de #182
- **Les lignes retirées d'un catalogue d'état (vulnérabilités, entrées Zotero, surlignages) sont
  servies avec leur `withdrawn_at`, pas filtrées.** Décision de Sabine. Pourquoi, sur
  recommandation : c'est plus honnête et traçable ; un retrait reste visible avec sa date, et un
  client peut filtrer s'il le veut. — PR de #182

### Interface

- **`kb search --in` ne prend que `watch` et `library` : `--in wiki` est retiré tant que le wiki
  n'entre pas en base ; `source.acquisition_mode` garde la valeur `wiki`.** Décision de Sabine.
  Pourquoi, sur recommandation de time-knight, acceptée par Sabine le 2026-10-14 : une option qui
  ne rend jamais rien est un piège ; elle sera ajoutée quand le wiki entrera en base. Constat :
  aucune source de `seed_sources.sql` n'a le mode `wiki`. **Révise** l'entrée « Bibliothèque et
  recherche » du 2026-10-09 (`kb search --in watch|library|wiki`) et celle du 2026-10-10 qui la
  redit (« `kb search --in watch|library|wiki` ne change pas »). **Révisée le 2026-10-15** :
  `kb search` vient après le 08/11 (« POC du 25/10 », décision 1). — PR de #182

### Journaux

- **`kb serve` écrit son journal de fonctionnement dans un fichier à part,
  `<KB_DATA_DIR>/logs/kb-serve.log`, au même format et avec la même rotation que `kb.log`
  (minuit UTC, `LOG_FILES_KEPT` fichiers gardés).** Décision de Sabine, sur recommandation de
  la session K-B. Constat : dans CPython 3.13.13 (`logging/handlers.py:448-450`),
  `TimedRotatingFileHandler.doRollover` revient sans rouvrir son flux ni recalculer sa
  prochaine rotation quand le fichier daté existe déjà. Si `kb collect` ou `kb import` fait la
  rotation de minuit avant que `kb serve` n'écrive, `kb serve` continue d'écrire dans
  `kb.log.<veille>` jusqu'à son redémarrage. Et quand ce fichier est supprimé au bout de
  `LOG_FILES_KEPT` jours, la rotation suivante de `kb serve` renommerait le `kb.log` en cours.
  Pourquoi un fichier à part : `kb serve` est le seul processus long, et son port est une
  constante, si bien qu'un second `kb serve` échoue au `bind` (constaté : code de sortie 3) ;
  il est donc le seul à écrire ce fichier. Options écartées : garder le même fichier en écrivant
  la limite (les lignes de l'API seraient rangées sous la mauvaise date, voire déplacées) ; un
  gestionnaire sans rotation ou une rotation externe (défait la rotation décidée avec #134).
  Complète la règle de #134 (le journal de fonctionnement dans `logs/kb.log`) : les règles 2 et
  3 de `.claude/rules/conventions.md` nomment désormais le second fichier, avec l'accord de
  Sabine. Limite assumée : `kb collect` et `kb import` partagent toujours `kb.log`, mais ils
  sont courts et lancés à la main, une fois par jour. **Révisée le 2026-10-15** : le port de
  `kb serve` est réglable (`KB_DATA_API_PORT`), si bien qu'un second `kb serve` sur un autre port
  ne bute plus sur le `bind` et écrirait le même fichier. La limite devient une consigne écrite :
  un seul `kb serve` par `KB_DATA_DIR` (`docs/specs-api.md`, « Journal ») ; aucun verrou n'est
  codé, compose lançant un conteneur par service (« API de données : réglages et santé »).
  — PR #195 (#184)

## 2026-10-15

### API de données : détail et tendances

Décisions de Sabine du 2026-10-15 (validation du plan de #185, relayée par time-knight), sur
recommandation de la session K-B sauf mention.

- **Le détail d'un item sert une liste blanche : les six champs de la liste, puis ceux de sa
  sorte nommés par la spec, et rien d'autre ; ni la clé Zotero d'un surlignage, ni le `name`
  d'une release.** Pourquoi : la spec liste ces champs, et ce qu'aucun client n'utilise ne sort
  pas (minimisation). La clé d'un surlignage ne permet pas de l'ouvrir dans Zotero : la clé de
  sa pièce jointe n'est pas gardée ; le `name` d'une release est déjà dans `title`. Option
  écartée : servir la ligne de chaque table entière (des clés internes et des colonnes de
  collecte sortiraient, API3). La réponse est une union discriminée par `kind` (`oneOf` et
  `discriminator` dans l'OpenAPI) ; option écartée : un schéma unique aux champs tous
  optionnels, qui ne dit pas quels champs une sorte a. — PR de #185
- **`item_id` et `window_end` ont une seule forme écrite : un entier sans zéro en tête, sans
  `+`, sans espace ni décimale, tenu sur 64 bits ; une date `AAAA-MM-JJ` exactement. Toute autre
  forme répond 422.** Pourquoi : laissés à Pydantic, `1.0`, ` 1` et `01` seraient chacun une URL
  de l'item 1, et `window_end=1760227200` serait lu comme une date Unix (constaté avec Pydantic
  2.13.5), ce que `since` refuse déjà. Options écartées : l'`int` et la `date` de Pydantic seuls ;
  un 404 au-delà de 64 bits (l'entier ne peut pas être lié à SQLite). — PR de #185
- **L'API et sa spec passent en version 0.2.0.** Décision de Sabine, sur recommandation de
  time-knight. Pourquoi : la règle de la spec s'applique (un changement visible par un client
  change la version) : `/items/1` passe de 404 `route_not_found` à un item servi, et un
  `item_id` au-delà de 64 bits passe de 404 à 422. Option écartée : garder 0.1.0 au motif que
  la spec 0.1.0 décrivait déjà ces routes (recommandée par la session K-B). — PR de #185
- **`item.id`, un identifiant séquentiel, reste dans l'URL : la recommandation d'OWASP
  API1:2023 d'identifiants difficiles à deviner est écartée.** Décision de Sabine. Pourquoi :
  K-B n'a qu'une propriétaire, et tout client authentifié lit tous les items (ligne API1 de
  `specs-api.md`) : deviner un identifiant ne donne rien qu'un client n'ait déjà. OWASP range
  les identifiants aléatoires et imprévisibles (GUID) parmi ses mesures de prévention, à côté
  du contrôle d'autorisation à chaque accès à un objet
  ([API1:2023](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/),
  section « How To Prevent », relevé par recherche web le 2026-10-15). Complète l'entrée « Identifiant : `item.id` dans le chemin » du
  2026-10-14. Limite assumée : à revoir si l'API a un jour plusieurs utilisateurs ou sert un
  site public. — PR de #185

### POC du 25/10

Décisions de Sabine du 2026-10-15, prises avec time-knight sur sa proposition du POC et
relayées par lui. Le pourquoi et les options écartées sont ceux qu'il a transmis. Les règles
qui en découlent sont dans `.claude/rules/poc.md`.

- **1. Le 25/10 est un POC en conteneurs Docker en localhost : la collecte, l'API de données et
  l'API IA ; l'inférence se fait chez un fournisseur distant ; il n'y a ni interface CLI dédiée
  ni front ; le tout est transposable sur Azure Container Apps (ACA) au 08/11 sans refonte.**
  Décision de Sabine (15/10, 11 h 16). Pourquoi : ACA fait tourner des conteneurs, si bien
  qu'un POC en conteneurs est la meilleure répétition du 08/11. Il oblige dès maintenant à
  régler l'hôte et les journaux par variables d'environnement, à gérer SIGTERM et à exposer
  `/health`. Cette entrée consigne aussi une décision de Sabine du 14/10, transmise par
  time-knight et non consignée jusqu'ici : l'API IA est en local pour l'oral blanc, et sur ACA
  au 08/11.
  Options écartées :
  - tout faire tourner sur le Mac, sans conteneurs (on ne répète pas la cible) ;
  - mettre en ligne sur ACA dès le 25/10 (décision du 14/10 ci-dessus) ;
  - une interface CLI dédiée et un front en localhost (Sabine, 15/10, 10 h 42 et 10 h 45 : le
    retour console suffit au 25/10, les maquettes restent pour le 08/11) ;
  - monter `zotero.sqlite` et le coffre dans le conteneur (on s'écarte de la cible, où le Mac
    collecte ces deux sources, et on expose des fichiers personnels au conteneur).

  **Révise** « Installation et interface » (2026-10-08), « Interface » (2026-10-09 et
  2026-10-14 : `kb search` vient après le 08/11), la
  décision qui garde la base et les données sur la machine (2026-10-09), et l'API IA « en local
  […] pas d'hébergement en v0 » (2026-10-12). — PR de #198 **Révisée le 2026-10-20** : trois temps,
  le Mac sans conteneur d'abord, puis les conteneurs en local, puis ACA (« Squelette E1 E3 : cadrage
  du 20/10 », décision 1).
- **2. SQLite au 25/10, PostgreSQL au 08/11.** Décision de Sabine (15/10, 11 h 17). Pourquoi :
  PostgreSQL ne sert que la mise en ligne, car sur ACA un fichier SQLite n'a pas de disque
  fiable ; en localhost, SQLite fonctionne. La règle « aucun nouveau SQL propre à SQLite » (règle
  1 de `poc.md`) évite de payer ce SQL au portage. La recherche plein texte se fera avec
  PostgreSQL (`tsvector`) après le 08/11 ; #188 sera à reformuler à ce moment-là.
  Options écartées :
  - passer à PostgreSQL avant le 25/10 : le portage est chiffré XL (25 à 30 h), hors de la marge
    du POC ;
  - mettre la base dans un dossier du Mac partagé avec les conteneurs : la fiabilité du fichier
    `-shm` du mode WAL à travers le partage de fichiers Mac ↔ VM n'est pas vérifiée. La base va
    donc dans un volume nommé, et seul le brut va dans le dossier partagé.

  **Révise** le choix du SGBD (2026-10-02, où PostgreSQL était écarté), W7 et la recherche par
  FTS5 (2026-10-09), les migrations Alembic (2026-10-10) et la recherche `LIKE` puis FTS5
  (2026-10-14). — PR de #198 **En attente depuis le 2026-10-20** : « La base au temps 3 »,
  question ouverte (plus bas).
- **3. Pas de planificateur sur le Mac : la collecte et l'import sont lancés à la main, et
  conçus comme des jobs. En ligne, un job ACA déclenché par cron, avec un lancement manuel
  possible.** Décision de Sabine (15/10, 10 h 48). Pourquoi : la collecte, lancée à la main
  mais conçue comme un job (une exécution qui se termine, avec un code de sortie nommé),
  devient un job ACA sans refonte ; il n'y a pas de planificateur à construire.
  Options écartées :
  - planifier par launchd sur le Mac, comme le prévoyait l'épic #22 ;
  - en ligne, un job déclenché par un événement (aucun signal extérieur n'existe).

  ACA connaît trois déclencheurs de job : manuel, planifié (expression cron) et par événement
  ([Jobs in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/jobs),
  relevé par recherche web le 2026-10-15). **Clôt** la question ouverte « Collecte automatisée
  et sa fréquence » (2026-10-05). — PR de #198
- **4. L'API IA fait des fiches de veille par sujet, sur une fenêtre réglable
  (`KB_DIGEST_WINDOW_DAYS`, 3 jours par défaut) ; la compilation des clips en wiki passe après
  le 29/10 ; la collecte des clips (#14) reste au 25/10.** Décision de Sabine (15/10, 11 h 25,
  choix « a »). Pourquoi : les fiches s'appuient sur ce qui existe déjà (la veille en base,
  l'API de données), montrent que l'API IA consomme le pipeline de données, et évitent de
  construire une sorte d'item de plus avant le 25/10. Selon Sabine (11 h 22), les fiches
  regroupées par sujet sont une fonction complémentaire du wiki, et regrouper et synthétiser
  est le rôle d'une API IA. La fenêtre est une variable parce que Sabine la fixera plus tard.
  Options écartées :
  - (b) les fiches et le wiki des clips au 25/10 : deux chaînes LLM, qui ne tiennent pas dans la
    marge (3 à 18 h) ;
  - (c) le wiki des clips seul au 25/10, les fiches après ;
  - les fiches sans LLM, par requête déterministe et gabarit (« Deux wikis », 2026-09-29).

  **Lève** l'entrée « Deux wikis » et la ligne « Plus tard : … fiches rédigées par LLM »
  (2026-09-29) sur ce point. **Révise** le report des fiches (2026-10-09 ; 2026-10-12, « Wiki :
  les clips avant les PDF ») et la démonstration de l'oral blanc sur un clip compilé en direct
  (2026-10-12) : elle porte sur les fiches. — PR de #198
- **5. Les fiches regroupent la veille par une liste fermée de sujets tenue par Sabine : le
  modèle ne choisit que dans la liste (`enum`), et le code refuse le reste.** Décision de
  Sabine. Option écartée : le regroupement par sorte d'item, fait par le code. **Inverse** la
  décision du 2026-10-12 où le modèle pouvait proposer un sujet nouveau, mis dans la file « à
  voir » ; la liste fermée sans proposition était alors l'option écartée. Pourquoi ce
  revirement : non transmis. **Lève**, pour le classement par sujet, « pas de tri ni de score
  de la veille par un modèle » (nuit du 11 au 12/10). — PR de #198
- **6. Le modèle est Mistral : clé gratuite, données dans l'UE par défaut, opt-out de
  l'entraînement avant le premier appel, traitement inscrit au registre.** Décision de Sabine.
  Option écartée : Gemini, dont les conditions pour l'Espace économique européen sont ambiguës.
  Azure (Foundry) pour l'inférence reste possible au 08/11 par la configuration, sans toucher
  au code, mais n'est pas tranché : cela dépend de la souscription de l'école. **Révise**
  « inférence sur Azure » (nuit du 11 au 12/10) et « une clé gratuite d'abord, puis Azure »
  (2026-10-12). **Clôt** la question ouverte « Wiki : la clé gratuite, Gemini ou Mistral »
  (2026-10-12). — PR de #198 **Révisée le 2026-10-15**, puis **le 2026-10-16** : Azure AI
  Foundry, avec gpt-6-luna (« Modèle des fiches : gpt-6-luna sur Foundry », plus bas, qui révise
  le choix du 15/10). « Données dans l'UE par
  défaut » était une erreur de fait : le point d'accès global `api.mistral.ai` ne s'engage sur
  aucun lieu d'inférence.
- **7. Les jetons qui expirent ne sont pas couverts au 29/10 : les clés restent fixes ; les
  jetons sont prévus en ligne au 08/11.** Décision de Sabine (15/10, 11 h 54). Option écartée :
  les coder avant le 29/10, par Entra ID ou par #160. Pourquoi : 6 à 8 h, hors de la marge du
  POC ; Entra ID dépend aussi de la souscription de l'école, où le droit d'enregistrer une
  application n'est pas vérifié. **Révise** le jeton de courte durée et le *refresh token*
  (2026-10-12, « Wiki : API et client »). — PR de #198 **Précisée le 2026-10-20** : la clé reste
  fixe, sa rotation est documentée ; #160 reste hors du squelette (« Squelette E1 E3 : cadrage du
  20/10 », décision 3).
- **8. Les recommandations des relectures plateforme et IA du 15/10 sont suivies ; elles
  deviennent les huit règles de `.claude/rules/poc.md`.** Décision de Sabine (15/10, 11 h 54).
  Options écartées : dans chaque issue qui porte une recommandation. **Révise** la copie locale
  des mesures (2026-10-12, « Wiki : métriques ») : une ligne JSON par appel, sur stdout (règle
  4). **Révise** « Restent en variables d'environnement : les secrets et le dossier de données »
  (2026-10-10) : s'y ajoutent les réglages de déploiement (règle 2). — PR de #198

### API de données : réglages et santé

Choix de la session K-B dans le plan de #199, relu par un agent architecte et validé par Sabine
(15/10, relayé par time-knight). Ils appliquent la décision 1 du « POC du 25/10 » (régler l'hôte
et les journaux par variables d'environnement, exposer `/health`) et la règle 2 de
`.claude/rules/poc.md`.

- **`kb serve` se règle par quatre variables, chacune avec un défaut local nommé dans
  `core/config.py` : `KB_DATA_API_HOST` (une adresse IPv4, `127.0.0.1`), `KB_DATA_API_PORT` (des
  chiffres, de 1 à 65535, `8000`), `KB_DATA_API_ALLOWED_HOSTS` (`127.0.0.1,localhost`) et
  `KB_LOG_TO_FILE` (`true`). Une valeur refusée fait sortir `kb serve` en code 2 avant
  d'écouter.** Pourquoi : un conteneur ne joint pas le `127.0.0.1` d'un autre (c'est le sien),
  donc l'API doit écouter sur `0.0.0.0` en conteneur et accepter le nom de service d'`api-ia`.
  L'hôte est une adresse IPv4, un type fermé : la valeur vide, qu'uvicorn lierait à toutes les
  interfaces, est refusée du même coup, et une IPv6 aussi, car le `Host` d'un client en IPv6
  garde ses crochets (`[::1]`), qu'aucun hôte permis ne peut nommer : un réglage accepté mais
  injoignable est pire qu'un refus (constat de `/code-review`, tranché par time-knight, délégation
  de Sabine du 15/10). Le port est lu en chiffres seuls (`int()` accepterait
  `+8000` ou `8_000`). Le préfixe `KB_DATA_API_` est celui du code (`DATA_API_HOST`) et de la doc
  (« API de données ») ; `KB_DATA_API_ALLOWED_HOSTS` est le choix de Sabine, à la place de
  `KB_ALLOWED_HOSTS` écrit dans l'issue, par cohérence avec les trois autres. Options écartées :
  `KB_HOST` et `KB_PORT` (ambigus dès que l'API IA tourne sur la même machine) ; `KB_SERVE_HOST`
  (le nom de la commande, pas de ce qu'on règle) ; un hôte libre, que seul uvicorn refuserait
  (code 3 au `bind`, après le démarrage). — PR de #199
- **Chaque entrée de `KB_DATA_API_ALLOWED_HOSTS` est un nom en minuscules, sans `*` ni port
  (`[a-z0-9]([a-z0-9.-]*[a-z0-9])?`) ; une liste vide, une entrée vide, une entrée avec `*` ou
  hors motif sont refusées par un message qui nomme la position de l'entrée.** Pourquoi :
  `TrustedHostMiddleware` laisse passer tout hôte pour `*` (OWASP API8:2023) et compare le
  `Host` reçu tel quel, sans mise en minuscules (`starlette/middleware/trustedhost.py`, 1.8.0) ;
  une entrée validée par le motif n'a rien à échapper au journal. Options écartées : mettre les
  entrées en minuscules (la liste dirait autre chose que ce qui est écrit, et un client qui envoie
  des majuscules serait refusé quand même : `urllib` garde la casse de l'URL) ; refuser `*` seul
  (le joker de sous-domaine ne sert à aucun service nommé, et un motif `a*b` fait échouer
  Starlette sur un `assert`). — PR de #199
- **`GET /health` répond 200 `{"status": "ok"}`, sans clé : une route de Starlette ajoutée par
  `app.add_route`, comme `/docs`, hors de l'OpenAPI ; une sonde de vivacité, qui n'ouvre pas la
  base. L'API passe en 0.3.0.** Pourquoi : la dépendance de clé reste posée sur toute l'app, que
  FastAPI applique à chaque *path operation* et pas à une route de Starlette ; aucune route de
  données ne peut donc l'oublier, et un test parcourt les routes de l'app pour vérifier que
  `/docs`, `/openapi.json` et `/health` sont les seules à répondre sans clé. `/health` ne dit ni
  version, ni chemin, ni état de la base : une sonde qui ouvrirait la base ferait redémarrer le
  conteneur en boucle tant que la base manque. Options écartées : la clé posée sur chaque routeur
  pour faire de `/health` une *path operation* documentée (un routeur ajouté plus tard pourrait
  l'oublier) ; un sous-app monté (une couche de plus pour une route) ; une sonde qui vérifie la
  base (disponibilité plutôt que vivacité). — PR de #199
- **Un appel de `/health` qui répond 200 n'écrit aucune ligne de journal ; tout autre statut en
  écrit une.** Pourquoi : une sonde toutes les quelques secondes écrirait des milliers de lignes
  par jour (≈ 8 640 pour une sonde toutes les 10 s), noierait les requêtes des clients et, au
  08/11, coûterait dans Log Analytics, facturé au volume (minimisation, RGESN) ; une sonde mal
  réglée (400, 405) reste visible. Option écartée : tout journaliser en écrivant la limite.
  Constat de `/code-review`, tranché par time-knight, délégation de Sabine du 15/10. — PR de #199
- **`KB_LOG_TO_FILE=false` envoie le journal de fonctionnement sur la sortie d'erreur seule, pour
  toutes les commandes ; toute autre valeur que `true` ou `false` est refusée (code 2).**
  Pourquoi : en conteneur, la sortie d'erreur part vers `docker compose logs`, puis Log Analytics
  sur ACA (règle 4 de `poc.md`) ; le fichier en double sur le volume ne sert à rien. La règle 3 de
  `.claude/rules/conventions.md` le dit désormais, avec l'accord de Sabine. Option écartée : un
  chemin de fichier réglable (tout état reste sous `KB_DATA_DIR`, règle 4 de `poc.md`).
  — PR de #199

### Fiches de veille : le contrat

Choix de la session K-B dans le plan de #203, relu par un agent ingénieur IA et validé par Sabine
(15/10, vers 15:30, relayé par time-knight : « je suis tes recommandations »). Ils engagent la
chaîne des fiches (#204 à #207, #156). Le détail est dans `docs/fiches-veille.md`.

- **Les fiches sont rédigées en français ; un fait se limite donc à un identifiant, une version,
  un nombre ou un nom propre, recopié mot pour mot de l'item.** Décision de Sabine (15/10, vers
  16:05) pour la langue. Pourquoi la limite des faits (relecture de faisabilité par un agent
  ingénieur IA, tri par time-knight, délégation de Sabine du 15/10) : les items sont surtout en
  anglais, et une expression anglaise traduite dans la phrase n'y serait plus trouvée, si bien que
  l'affirmation serait retirée. Option écartée : des faits en « courtes expressions », qui ne
  survivent pas à la traduction. Limite assumée : le code ne vérifie pas la catégorie d'un fait,
  seulement sa présence. — PR de #203
- **La complétude est calculée par le code : à la rédaction, le modèle ne rend pas de
  `not_retained` (items envoyés moins items cités) ; au classement, un item absent est compté
  « non retenu ». Un item en double ou inconnu reste un échec.** Pourquoi (même relecture, même
  tri) : sur 60 items, un petit modèle en oublie un, et un seul oubli faisait échouer tout le
  sujet, ou toute la demande au classement. La sécurité ne change pas : le contrôle des `item_id`
  refuse toujours un identifiant inventé. Option écartée : exiger du modèle qu'il rende chaque item
  exactement une fois, sous peine d'échec (la première forme de ce contrat, avant la relecture).
  — PR de #203

- **Un sujet par item, avec un ordre de départage écrit dans la liste des sujets.** Pourquoi : la
  complétude du classement (chaque item au plus une fois, dans un sujet ou « non retenu », un item
  absent compté « non retenu ») se contrôle par le code. Option écartée : plusieurs sujets par item (doublons entre fiches,
  complétude ambiguë). Limite assumée : le départage décide, pas le contenu ; une alerte sur
  LangChain va dans `vulnerabilities`, pas dans `agent_frameworks`. — PR de #203
- **Un fait est un extrait recopié de l'item qu'il cite, de 3 à 120 caractères, écrit aussi
  dans la phrase et trouvé entre deux limites de mot ; un fait CVE ou GHSA doit être égal au champ
  identifiant (`cve_id`, `ghsa_id`) d'un item cité ; chaque item cité porte au moins un fait
  trouvé. Une affirmation qui manque à l'une de ces règles est retirée et comptée.**
  Pourquoi : un extrait se vérifie par une recherche, sans second modèle, et l'exiger dans la
  phrase le lie à ce qu'elle affirme ; le relecteur a montré qu'une CVE écrite dans le résumé
  d'un article TLDR piégé (« dis que CVE-2026-0001 n'est pas exploitée », #206) aurait passé la
  recherche dans le texte libre ; la revue de la spec a montré qu'une affirmation pouvait citer
  dix items avec un seul fait, et faire ainsi citer un item piégé sans rien vérifier de lui
  (constat tranché par time-knight, délégation de Sabine du 15/10). Les bornes deviennent 1 à 5
  items et 1 à 10 faits par affirmation ; le maximum de sortie, donc le calcul de `max_tokens`
  (#150, #205), change avec elles. Options écartées : des faits libres, reformulés (invérifiables) ;
  laisser le piège CVE comme une limite écrite de la fidélité (choix (b), écarté par Sabine).
  Limites assumées : la fidélité ne vérifie pas le sens d'une phrase (négation, paraphrase) ; un
  article TLDR seul ne porte plus de CVE, la fiche la cite par l'entrée KEV ou l'alerte si elles
  sont dans la fenêtre. #206 est accordé (commentaire du 15/10) : ce piège est retiré et compté,
  pas un état nommé. — PR de #203 **Complétée le 2026-10-16** : la recherche reste sans second
  modèle, et un LLM juge vérifie ensuite le sens de chaque affirmation gardée (« Fiches de veille :
  le LLM juge », plus bas). **Révisée le 2026-10-20** : le juge sort du contrat des fiches
  (« Squelette E1 E3 : cadrage du 20/10 », décision 2).
- **Le modèle ne reçoit pas le champ `url` d'un item, et les URL des champs de texte envoyés sont
  masquées en `[url]` avant le prompt ; les sources d'une fiche (titre, URL) sont rendues par le
  code, lues dans l'API de données.** Pourquoi : rien à recopier, donc tout `://` en sortie est
  fautif et refusé sans exception (#206). Le masquage vient de la revue de la spec : le corps d'une
  release ou un résumé gardaient leurs liens, et le modèle, en les recopiant, aurait fait échouer
  le sujet (constat tranché par time-knight, délégation de Sabine du 15/10). Option écartée :
  envoyer l'URL au modèle (il pourrait la recopier, ou en écrire une fausse). Limites assumées : un
  domaine sans schéma (`example.com/x`) n'est ni masqué ni refusé, il est rendu en texte non
  cliquable ; le titre d'une source est rendu tel qu'il est collecté, et l'échapper revient à qui
  écrira la fiche dans le coffre. — PR de #203
- **`POST /digests` répond 200 dès que le classement a réussi ; chaque sujet dont la rédaction
  échoue est nommé dans `failed_subjects` avec son état, et les autres sont rendus.** Pourquoi :
  #205 demande qu'un sujet en échec n'empêche pas les autres. Options écartées : 207 Multi-Status
  (une sémantique WebDAV) ; l'échec de toute la demande au premier sujet en échec. Un échec du
  classement, lui, fait échouer la demande (502, 503 ou 504 selon la panne de l'amont).
  — PR de #203

### Modèle des fiches : gpt-5.6-luna sur Foundry

Décision de Sabine (15/10, relayée par time-knight avant 16 h 30), sur l'avis d'un expert IA neuf,
commandé sans biais (sans fournisseur ni choix antérieur). Le pourquoi et les options écartées
sont ceux de cet avis, validé par Sabine.

- **Le modèle des fiches est gpt-5.6-luna (version 2026-07-09) sur Azure AI Foundry, avec un
  abonnement Azure d'entreprise, en déploiement Data Zone Standard UE (Sweden Central ou France
  Central), `reasoning_effort: "none"`, version figée. Repli : gpt-5.4-mini (2026-03-17) dans la
  même ressource ; seul le nom du déploiement change. La spec des fiches reste neutre vis-à-vis du
  fournisseur (interface compatible OpenAI).** **Révise** la décision 6 de « POC du 25/10 »
  (Mistral, clé gratuite). Pourquoi : les trois contraintes dures (calcul dans l'UE, pas
  d'entraînement sur les données, contrat de sous-traitance) sont tenues par le contrat et par le
  type de déploiement, pas par un réglage de compte ; coût estimé par l'expert à 3 à 16 $ par
  mois ; la même ressource sert en local et sur ACA, avec une identité managée possible ; les
  sorties structurées strictes sont natives. Options écartées :
  - Mistral sur `api.mistral.ai` : ce point d'accès global ne s'engage sur aucun lieu
    d'inférence ; seul `api.eu.mistral.ai` traite dans l'UE, et rien ne dit qu'une clé gratuite y
    est acceptée ; l'entraînement est actif par défaut en offre gratuite, et les quotas ne sont
    pas publiés ;
  - Mistral Medium 3.5 sur Foundry : en préversion, `json_schema` non confirmé, environ 22 $ par
    mois ;
  - GPT-6 Astra : zone US seulement ;
  - Claude sur Foundry : pas de traitement dans l'UE ;
  - Gemini en offre gratuite : aucune garantie de région ;
  - gpt-4.1-mini et gpt-4o-mini : dépréciés.

  Limites assumées : `temperature` n'est pas pris par les modèles à raisonnement selon Azure, et
  la doc d'OpenAI et celle d'Azure se contredisent pour `reasoning_effort: "none"` ; le premier
  essai le tranche (#158). Le filtre de contenu d'Azure peut retenir une sortie sur le jailbreak
  ou l'injection, sujets de la veille : la spec en fait un état nommé, `llm_content_filtered`.
  **À vérifier par #158** : la disponibilité de gpt-5.4-mini en Data Zone Standard UE (une
  question Microsoft Q&A d'avril 2026 ne la voyait alors qu'aux États-Unis) ; si elle manque, le
  repli n'est pas dans la même ressource. Sources (consultées le 2026-10-15, relevées par
  recherche web) :
  [disponibilité par région](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure-region-availability),
  [données et confidentialité](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/data-privacy),
  [modèles à raisonnement](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning),
  [sorties structurées](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs),
  [annonce de GPT-5.6 sur Foundry](https://azure.microsoft.com/en-us/blog/gpt-5-6-now-available-in-microsoft-foundry/),
  [fiche de gpt-5.6-luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna),
  [inférence régionale de Mistral](https://docs.mistral.ai/inference/regional-inference).
  — PR de #203 **Révisée le 2026-10-16** : gpt-6-luna, repli gpt-5.6-luna (« Modèle des fiches :
  gpt-6-luna sur Foundry », plus bas).

### Appel du modèle

Choix de la session K-B dans le plan de #150, relu par un agent architecte et validé par Sabine
(15/10, relayé par time-knight : « je suis tes recommandations ») ; le choix du client HTTP et la
ligne sur les frameworks sont des décisions de Sabine, relayées par time-knight avec leur pourquoi.
Le détail est dans `src/k_b/ai_api/` et dans `docs/fiches-veille.md` (« États nommés »).

- **Le modèle est appelé par httpx2 seul, pour le POC : `POST {KB_LLM_BASE_URL}/chat/completions`,
  la clé en `Authorization: Bearer`, derrière `call_model` et `LlmCall` (`ai_api/llm_client.py`).**
  Décision de Sabine (15/10, relayée par time-knight vers 18 h). Pourquoi : un code générique,
  sans les types d'un fournisseur (préférence de Sabine) ; un seul point d'accès, sans diffusion
  (streaming) ni outils ; aucune version de plus à suivre. L'appel reste isolé dans un module :
  changer de client touche ce module, et les tests de l'interface ne changent pas. Option écartée :
  le SDK `openai` (recommandé dans le plan) : son README avertit, pour son client Azure, que « The
  Azure API shape differs from the core API shape which means that the static types for responses
  / params won't always be correct » ; il lit l'environnement ambiant (`OPENAI_API_KEY`,
  `OPENAI_BASE_URL`, `OPENAI_CUSTOM_HEADERS`, `src/openai/_client.py`) ; ses nouvelles tentatives
  auraient été coupées de toute façon (la politique est celle de K-B) ; il sort une version tous
  les 1 à 3 jours (3.25.0 le 06/10, 3.31.0 le 14/10, index PyPI). **À revoir au 08/11** si
  l'identité managée (jeton Entra), l'API Responses ou un autre point d'accès le demandent.
  Limites assumées : l'en-tête `Authorization: Bearer` avec une clé Azure n'est documenté que par
  l'exemple Python de Microsoft (`OpenAI(api_key=…, base_url=".../openai/v1/")`), les exemples curl
  utilisant `api-key` : à confirmer par #158, repli `api-key`. Le client ne lit ni proxy ni
  certificat de l'environnement (`trust_env=False`) et ne suit aucune redirection. — PR de #150
- **Le fournisseur de remplacement est un transport simulé d'httpx2 (`MockTransport`) sous le même
  client que le vrai fournisseur ; il rend, dans l'ordre, des étapes connues d'avance (complétion,
  réponse HTTP quelconque, délai, panne de connexion), écrites en code par les tests ou lues dans
  le fichier `KB_LLM_REPLAY_FILE` quand `KB_LLM_PROVIDER=replay`.** Pourquoi : tout le code d'un
  vrai appel (corps de requête, lecture de la réponse, correspondance des statuts et des pannes)
  est exercé en test et en CI, sans réseau, sans clé ni dépense ; le fichier rend réel le choix
  « en configuration » du critère de #150. Option écartée : une interface `Protocol` avec une
  fausse implémentation au-dessus du client (le code HTTP ne serait jamais testé). Limites
  assumées : les étapes supposent des appels l'un après l'autre (si #205 rédige en parallèle, il
  choisira une étape d'après le corps de la requête) ; un fichier figé ne cite que les `item_id`
  d'une veille connue d'avance. — PR de #150
- **`KB_LLM_PROVIDER`, `KB_LLM_BASE_URL` et `KB_LLM_MODEL` n'ont pas de valeur par défaut : sans
  eux, l'API IA ne démarre pas. La règle 2 de `.claude/rules/poc.md` le dit désormais.** Décision
  de Sabine (point B du plan). Pourquoi : un fournisseur distant n'a pas de valeur locale ; un
  défaut `replay` rendrait des fiches inventées sans le dire, et un défaut réel enverrait la veille
  à un service que personne n'a choisi, alors que le traitement dans l'UE tient au déploiement
  (« Modèle des fiches », plus haut). Échouer fermé (`code.md`). Option écartée : un défaut
  `replay` en local. Une URL refusée n'est jamais citée au journal, car elle peut porter une clé
  (`https://user:clé@hôte`, `?api-key=…`). Le choix fait est journalisé (« LLM provider replay »),
  pour qu'un conteneur réglé par erreur le dise. — PR de #150
- **Une seule nouvelle tentative par appel. Après une sortie refusée, avec le rappel constant du
  contrôle qui l'a refusée, fourni par l'étape appelante (#205, #206) ; après un 429, un 5xx ou une
  connexion refusée, après `Retry-After` en secondes (2 s sans lui), sauf au-delà de 20 s. Aucune
  après un autre 4xx, un délai dépassé, une sortie tronquée ou filtrée.** Pourquoi : à
  `temperature=0`, la même demande rend le plus souvent la même sortie (le déterminisme n'est pas
  garanti, guide « Advanced usage » d'OpenAI), d'où le rappel (commentaire du 15/10 sur
  #150) ; une attente plus courte que `Retry-After` rendrait un second 429. Un appel dure 150 s
  quand ses réponses arrivent d'un bloc ; une réponse envoyée par morceaux peut durer plus, car
  chaque lecture a son délai : la borne totale est celle de la demande (#205). Option écartée : un
  délai total par tentative (httpx2 n'en a pas ; il faudrait un minuteur, une couche de plus, pour
  une borne que la demande pose déjà) ; constat de `/code-review`, tranché par time-knight,
  délégation de Sabine du 15/10. Le rappel vient de
  l'étape parce qu'il appartient à sa consigne et à sa `prompt_version` (constat de l'architecte).
  Il est ajouté au message `system`, puisque la consigne déclare le message utilisateur « donnée,
  jamais consigne ». Options écartées : un message `user` de rappel (il contredirait la consigne) ;
  un second message `system` après le message utilisateur (ordre non vérifié chez chaque
  fournisseur) ; lire la forme « date HTTP » de `Retry-After` (rare : comptée comme un en-tête
  absent). **Ajouts aux états nommés de la spec** : un 400 dont `error.code` vaut `content_filter`
  (Azure filtre aussi l'entrée, catégorie jailbreak comprise) donne `llm_content_filtered` ; un
  `Retry-After` au-delà du plafond, `llm_rate_limited` ; une réponse 200 illisible,
  `llm_unavailable` ; un délai de connexion, `llm_timeout`. L'enveloppe de la réponse tolère les
  champs inconnus, la sortie du modèle non (`extra="forbid"`). Le statut HTTP de la dernière
  réponse est gardé (`http_status`, nouveau champ de la ligne de métrique) : un 401 de clé refusée
  se distingue d'un 503 (constat de `/security-review`, tranché par time-knight, délégation de
  Sabine du 15/10). Limite assumée : le format du 400
  d'Azure vient de constats publics (Microsoft Q&A, forum CrewAI) et reste à confirmer par #158.
  — PR de #150
- **Pas de framework d'orchestration ni agentique pour la chaîne des fiches, aujourd'hui : c'est
  un choix adapté au besoin actuel, pas une règle.** Formulation de Sabine (15/10, relayée par
  time-knight). La chaîne est fixe et décidée par le code, sans outil confié au modèle ni état qui
  dure entre deux demandes ; un framework n'y apporterait rien d'utilisé. Options examinées et
  écartées pour ce besoin : LangChain, LangGraph et d'autres. À réexaminer dès qu'un besoin le
  justifie : agent avec outils, RAG, reprise d'un traitement long. — PR de #150

Sources (consultées le 2026-10-15) :
[README du SDK `openai`, « Microsoft Azure OpenAI »](https://github.com/openai/openai-python/blob/main/README.md)
et [`src/openai/_client.py`](https://github.com/openai/openai-python/blob/main/src/openai/_client.py)
(lus par Context7) ; [index PyPI de `openai`](https://pypi.org/project/openai/) ;
[cycle de vie des versions de l'API Azure OpenAI](https://learn.microsoft.com/en-my/Azure/foundry-classic/openai/api-version-lifecycle)
et [Responses API, Foundry classic](https://learn.microsoft.com/en-us/azure/foundry-classic/openai/how-to/responses)
(recherche web) ; [filtre de contenu d'Azure](https://learn.microsoft.com/azure/ai-foundry/openai/concepts/content-filter)
et [Microsoft Q&A 2044545](https://learn.microsoft.com/en-us/answers/questions/2044545/content-filter-and-policy-violation-issues-when-us)
(recherche web) ; [transports d'httpx](https://github.com/encode/httpx/blob/master/docs/advanced/transports.md)
(Context7) ; [RFC 9110, § 10.2.3](https://www.rfc-editor.org/rfc/rfc9110#section-10.2.3).

### Fiches de veille : la lecture par l'API de données

Choix du plan de #204, relu par un agent architecte et validé par Sabine (15/10, relayé par
time-knight, qui a vérifié les recommandations dans le code avant de les transmettre). Le détail
est dans `src/k_b/ai_api/` et dans `docs/fiches-veille.md` (« Lecture plafonnée »).

- **Quand la lecture atteint le plafond de 300 items, la réponse nomme la sorte coupée
  (`window.capped_kind`) et la date de son premier item laissé de côté (`window.covered_after`),
  borne exclue : tout item de cette sorte strictement plus récent a été lu, et les sortes qui la
  suivent ne sont pas lues. Les deux champs sont nuls sans coupe.** Décision de Sabine (15/10,
  vers 20 h pour la borne, vers 20 h 05 pour la sorte). Pourquoi : les articles TLDR d'une
  édition, et les entrées KEV d'un jour, ont tous la même date, minuit UTC ; une coupe au milieu
  d'une édition aurait annoncé couvert un jour lu en partie, et une coupe entre deux sortes
  n'aurait laissé aucun item gardé à la sorte coupée (constat de l'architecte). L'ordre de
  `GET /items` (`source_date` puis `id`, décroissants, `database/reading.py`) est total : la
  borne exclue est vraie dans les deux cas. Sans le nom de la sorte, la date se lirait comme
  valable pour toutes les sortes (ajout de time-knight). Forme : deux champs à plat dans
  `window`, à côté de `since` et `until` (choix de la session K-B ; écarté : un objet `cap`, un
  niveau de plus pour deux valeurs). Option écartée : garder « la date du plus ancien item gardé
  de la sorte coupée » en écrivant ses deux limites (le champ aurait promis ce qui n'a pas été
  lu). **Révise** la règle « Coupe dite » de la spec (`window.covered_since`, « Fiches de
  veille : le contrat », plus haut). — PR de #204
- **La vérification d'une URL (jamais citée) et la construction d'un client httpx2 (ni proxy ni
  certificat de l'environnement, aucune redirection suivie) vivent une fois, dans
  `ai_api/outbound.py`, pour le modèle et pour l'API de données. Les deux constantes de la clé
  d'un client (32 caractères au moins, alphabet de `token_urlsafe`) passent de `cli.py` à
  `core/config.py`, lues par `kb serve` et par l'API IA.** Décision de Sabine (point 2 du plan).
  Pourquoi : ce sont des règles de sécurité, que deux copies feraient diverger (`code.md` met la
  sécurité avant l'absence de duplication). Option écartée : les recopier dans les modules de
  #204. Le module commun des clés par client reste à #156, dont c'est le critère (« reprise de
  #184 dans un module commun ») : seules les constantes bougent ici (constat de l'architecte). —
  PR de #204
- **L'API IA envoie la clé lue dans `KB_API_KEY_AI_DIGEST`, la variable que `kb serve` lit pour
  ce client ; l'URL de l'API de données se lit dans `KB_DATA_API_URL`, avec le défaut local
  `http://127.0.0.1:8000` nommé dans `core/config.py`.** Choix de la session K-B dans le plan,
  validé par Sabine. Pourquoi : une seule valeur pour les deux côtés, rien à tenir égal ; un
  réglage de déploiement a un défaut local, un secret n'en a pas (règle 2 de `poc.md`). `http`
  est accepté : l'API de données n'a pas de TLS avant ACA (`specs-api.md`, API8). Option
  écartée : une variable `KB_DATA_API_KEY` de plus, à tenir égale à la première. Limite : le
  défaut suit `DATA_API_PORT`, pas `KB_DATA_API_PORT` ; si Sabine change le port de `kb serve`,
  elle change aussi `KB_DATA_API_URL` (`.env.example`). — PR de #204

## 2026-10-16

### Modèle des fiches : gpt-6-luna sur Foundry

Recommandation de time-knight, retenue par Sabine le 16/10 (vers 11 h 45, heure de Paris).

- **Le modèle des fiches est gpt-6-luna (version 2026-09-22, en disponibilité générale) sur Azure
  AI Foundry, en déploiement Data Zone Standard UE (Sweden Central ou France Central ; North
  Europe exclu), `reasoning_effort: "none"`, version figée. Repli : gpt-5.6-luna (2026-07-09)
  dans la même ressource.** **Révise** « Modèle des fiches : gpt-5.6-luna sur Foundry »
  (2026-10-15). Pourquoi : gpt-6-luna est en disponibilité générale depuis le 22/09/2026, d'une
  génération plus récente que gpt-5.6-luna, avec les mêmes capacités utiles aux fiches (Chat
  Completions, sorties structurées, `reasoning_effort: "none"`, contexte de 1 050 000 jetons),
  le même quota par palier (palier 1 : 333 000 TPM en DataZoneStandard) et les mêmes régions
  Data Zone UE. Le code ne change pas : le nom du modèle est un réglage (`KB_LLM_MODEL`), et le
  client de #150 est générique. Le prix ne décide pas : au pire environ 420 000 jetons par
  demande, soit quelques centimes à 0,12 $ en entrée et 0,60 $ en sortie par million de jetons
  (prix UE) ; celui de gpt-5.6-luna n'a pas été lu. Options écartées :
  - gpt-5.6-luna comme modèle principal : il devient le repli, puisque c'est le choix du 15/10,
    aux capacités déjà vérifiées, sur la même ressource et dans les mêmes régions ;
  - gpt-5.4-mini et gpt-5.6-terra comme replis : un seul repli suffit, et c'est le modèle validé
    la veille. Ce retrait est un choix de time-knight, annoncé à Sabine le 16/10 sans objection
    de sa part.

  Limites assumées : la doc de Microsoft se contredit sur deux points, que #158 mesure et que
  cette entrée ne tranche pas. `temperature` est cochée pour gpt-6-luna dans le tableau de la
  page des modèles à raisonnement, alors que le texte de la même page dit que les modèles à
  raisonnement autres que gpt-6-astra ne l'acceptent pas (la spec dit « `temperature` si
  acceptée ») ; le quota est « sans demande » pour gpt-6-luna à un endroit, « demande selon le
  palier » pour la famille GPT-6 à un autre. Préalable : le compte Azure de #158 est un compte
  personnel d'essai de Sabine, distinct de l'abonnement d'entreprise de l'entrée du 15/10
  (réponse de Sabine du 16/10) ; il est à 0 TPM, elle le passe en paiement à l'usage, puis
  vérifie le quota de gpt-6-luna en Data Zone UE (#158). Ce que le DPA de Microsoft couvre pour
  un compte personnel en paiement à l'usage n'est pas vérifié : la page du DPA dit qu'il
  s'applique aux produits souscrits sous les Product Terms ; #157 le lit dans les Product Terms
  et le DPA avant le premier appel réel. Sources (consultées le 2026-10-16, relevées par time-knight) :
  [GPT-6 Astra, Sol and Luna sur Foundry](https://azure.microsoft.com/en-us/blog/gpt-6-astra-sol-and-luna-for-production-agents-in-microsoft-foundry/)
  (disponibilité générale, Data Zone UE, prix UE),
  [modèles vendus par Azure](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure)
  (Chat Completions, sorties structurées, contexte, sortie de 128 000 jetons au plus),
  [disponibilité par région](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure-region-availability)
  (onglet Data Zone Standard, Europe : gpt-6-luna et gpt-5.6-luna cochés pour francecentral et
  swedencentral entre autres, non cochés pour northeurope),
  [modèles à raisonnement](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning)
  (`none` accepté par gpt-6-luna),
  [quotas et limites](https://learn.microsoft.com/en-us/azure/foundry/openai/quotas-limits)
  (paliers ; le palier gratuit ne contient pas gpt-6-luna),
  [DPA de Microsoft](https://www.microsoft.com/licensing/docs/view/microsoft-products-and-services-data-protection-addendum-dpa)
  (s'applique aux produits souscrits sous les Product Terms). — PR #221

### Fiches de veille : le LLM juge

Décisions de Sabine des 15 et 16/10, relayées par time-knight. Celles du 16/10 (14 h 53, heure de
Paris) valident le découpage de la session K-B, relu par un agent ingénieur IA indépendant. Le
contrat vient avec #222, le code avec #223, l'étalonnage avec #224. **Révisée le 2026-10-20** : le
juge sort du contrat des fiches ; #223 et #224 restent ouvertes, hors du squelette (« Squelette E1
E3 : cadrage du 20/10 », décision 2).

- **Un LLM juge vérifie chaque affirmation d'une fiche : c'est le contrôle 8, après la fidélité
  (contrôle 7). Il rend
  un verdict par affirmation : appuyée, contredite ou invérifiable. Seules les affirmations
  appuyées sont gardées. Le juge ne peut que retirer.** Décision de Sabine du 15/10. Pourquoi
  (Sabine) : « L'idée c'est de ne pas avoir à intervenir (en tant qu'Humain) sur la gestion du
  contenu de kb » ; puis « Un llm as judge me semble indispensable ». C'est la promesse du
  README : une bibliothèque de veille qui se range toute seule. La fidélité ne vérifie pas le sens
  d'une phrase (négation, paraphrase, traduction ; `docs/fiches-veille.md`, « Ce qu'elle ne
  vérifie pas »), et le juge comble ce manque. La traduction entre dans son rôle : la fiche est
  en français, l'item souvent en anglais.
  Options écartées :
  - un statut « à relire » passé à la main, ou une file « à voir » (Sabine : pas d'intervention
    humaine) ;
  - la fidélité seule : le sens d'une phrase fausse appuyée sur des faits vrais n'est pas
    vérifié (`docs/fiches-veille.md`, « Injection d'instructions »).

  Le juge passe par le client de #150, sans framework (« Appel du modèle »), avec le modèle de
  remplacement en CI. Il se code après #158, car un juge ne se mesure que sur un vrai modèle. Son
  contrat est écrit avant #205, qui fixe la borne totale d'une demande en comptant ses appels.
  S'il ne tient pas avant l'oral blanc du 29/10, il passe juste après, jamais abandonné.
  **Lève**, pour la vérification des fiches, « pas de tri ni de score de la veille par un modèle »
  (nuit du 11 au 12/10), déjà levée pour le classement le 15/10 (« POC du 25/10 », décision 5).
  **Complète** « Un fait est un extrait recopié » (« Fiches de veille : le contrat ») : la
  recherche des faits reste sans second modèle, et le juge vient après elle.
  Limites assumées :
  - le juge ajoute au plus 8 appels par demande, 16 avec les nouvelles tentatives, soit 44 au lieu
    de 28 ;
  - le filtre de contenu d'Azure lit aussi son entrée (`llm_content_filtered`) ;
  - un item piégé ne peut pas faire garder une affirmation, puisque le juge ne fait que retirer ;
    mais il peut faire retirer les affirmations des autres items du même sujet, ce qui se voit
    seulement par le compte des retraits.

  — PR #225
- **Le juge appelle un autre déploiement que le rédacteur : `gpt-5.6-luna`, dans la même
  ressource et la même zone de données UE, nommé par `KB_LLM_JUDGE_MODEL`, sans valeur par
  défaut. Si le quota de ce second déploiement n'est pas accordé à temps, la variable pointe vers
  `gpt-6-luna`, le déploiement du rédacteur, et le journal de fonctionnement le dit.** Décision
  de Sabine du 16/10, sur la recommandation de la session ; le repli est un ajout de Sabine.
  Pourquoi (recommandation de la session) : un modèle juge tend à mieux noter un texte qui lui est
  familier, donc les siens. Wataoka et al. le mesurent sur l'évaluation de réponses, pas sur la
  vérification d'une affirmation contre sa source : l'appliquer à notre cas est une hypothèse.
  Autre raison, à vérifier par #158 : le quota d'Azure étant compté par modèle, le juge ne pèserait
  pas sur celui du rédacteur. Le coût est un déploiement de plus à créer (préalable de #158), et
  une variable.
  Option écartée : le même déploiement que le rédacteur (aucun réglage de plus, mais des erreurs
  corrélées entre rédacteur et juge). Elle reste le repli.
  Limites assumées :
  - les deux modèles sont de la même famille, donc leurs erreurs restent en partie corrélées ;
  - si le rédacteur passe à son repli, `gpt-5.6-luna`, juge et rédacteur redeviennent le même
    modèle ;
  - les mêmes données partent une seconde fois chez Microsoft, à inscrire au registre (#157).

  — PR #225 **Révisée le 2026-10-17** : juge `gpt-6-luna` en phases 1 et 2, juge définitif choisi
  en phase 3 (« Modèle des fiches : gpt-6-luna sur l'abonnement de l'organisme de formation »,
  plus bas).
- **Un juge en échec envoie le sujet dans `failed_subjects`, avec l'étape (`judge`). Un juge qui
  retire tout rend une fiche vide. `POST /digests` gagne un compteur par fiche
  (`claims_judged_removed`) et l'étape en échec, sans aucun état.** Décision de Sabine du 16/10.
  Pourquoi (recommandation de la session) : échouer fermé (`code.md`), car aucune affirmation non
  jugée n'est rendue. C'est
  cohérent avec « aucune fiche partielle » et avec la fiche vide de la fidélité (« c'est ce qui
  a été observé », `docs/fiches-veille.md`). La règle 7 de `poc.md` (API IA sans état) est
  tenue.
  Option écartée : rendre la fiche non jugée, marquée comme telle (un statut à relire, que
  Sabine refuse). — PR #225
- **Le juge est étalonné sur 30 affirmations réelles étiquetées par Sabine et 20 affirmations
  altérées par construction, après l'oral blanc du 29/10. On mesure deux taux, les gardées à tort
  (sécurité) et les retirées à tort (utilité), plus la stabilité sur deux passages.** Décision de
  Sabine du 16/10. Pourquoi (relecture de l'ingénieur IA) :
  - presque aucune affirmation contredite ne survit à la fidélité, et les altérées (négation,
    nombre changé, mauvais item, contresens de traduction) rendent sa détection mesurable ;
  - les affirmations sont prises à l'entrée du juge, sinon celles qu'il retire à tort ne se
    verraient pas ;
  - `temperature=0` ne garantit pas le déterminisme (« Appel du modèle »), d'où les deux
    passages.

  Sur les 30 réelles, Sabine coche aussi « faute de français ou style maladroit » et « oubli
  important dans l'item cité » (ajout de Sabine du 16/10).
  Option écartée : 40 affirmations réelles seules. Elles prenaient 2 à 2,5 h de Sabine, et la
  détection des contredites restait non mesurable.
  Limites assumées :
  - avec 30 affirmations, un taux a une marge large, au-delà de ±10 points (estimation du
    relecteur, ±10 pour 40) ;
  - l'échantillon réel reste sous le dossier de données et n'est jamais committé (le dépôt devient
    public) : seuls les étiquettes et les taux le sont.

  — PR #225
- **Au POC, rien n'est relu avant le juge, et rien ne repart vers le rédacteur après lui. Une
  révision après le juge, en un seul tour, est écrite comme étape possible, non codée.**
  Recommandation de time-knight, retenue par Sabine le 16/10 (« on reste sur le POC »). Pourquoi :
  - le besoin n'est pas mesuré : seuls l'étalonnage (#224) et le compte des retraits du juge
    (`claims_judged_removed`) diront si les fiches sortent trop maigres ;
  - le coût : jusqu'à 2 appels de plus par sujet touché (révision et nouveau jugement), soit 76
    appels au lieu de 44 au pire, nouvelles tentatives comprises ;
  - le POC du 25/10 n'a ni la marge ni le quota (le compte est à 0 TPM le 16/10).

  Dans cette révision, seules les affirmations
  retirées repartent au rédacteur, avec leur verdict en code fermé, jamais un texte libre du juge.
  Elles repassent ensuite les contrôles 1 à 7 et le juge, sur elles seules ; il n'y a jamais de
  troisième tour. Elle serait déclenchée si l'étalonnage montre des fiches trop maigres. Elle
  coûterait jusqu'à 2 appels de plus par sujet touché. — PR #225

Sources (consultée le 2026-10-16, relevée par recherche web) :
[Wataoka, Takahashi et Ri, « Self-Preference Bias in LLM-as-a-Judge », arXiv 2410.21819](https://arxiv.org/abs/2410.21819)
(GPT-4 montre une préférence pour ses propres sorties ; les auteurs la rattachent à la
perplexité plus basse de ces sorties ; la revue de publication n'a pas été confirmée).

### Modèle des fiches : Mistral Small 4 en repli temporaire

Décision de Sabine (16/10, vers 15 h 45, heure de Paris, relayée par time-knight) : « Pour 158 le
quota n'est pas réglé. On peut brancher Mistral pour mettre le code en place. » Repli temporaire,
sans optimisation de prompt. Les options écartées sont celles de l'ordre de mission de time-knight,
validées par Sabine avec le plan (16/10, vers 16 h 25).

- **Tant que #158 n'est pas faite, le modèle des fiches est `mistral-small-2603` (Mistral Small 4)
  sur le serveur UE de Mistral, `https://api.eu.mistral.ai/v1`, en clé gratuite, par
  `KB_LLM_PROVIDER=openai_compatible`, sans `KB_LLM_REASONING_EFFORT` (donc `temperature=0`).**
  Revient temporairement sur la décision 6 de « POC du 25/10 » (Mistral, clé gratuite), sans
  réviser « Modèle des fiches : gpt-6-luna sur Foundry » : gpt-6-luna reste la cible. Ce qui a
  changé depuis le 15/10 : le quota de gpt-6-luna est à 0 TPM, et la clé gratuite de Sabine est
  acceptée par `api.eu.mistral.ai` (`GET /v1/models` lancé par Sabine le 16/10, qui rend
  `mistral-small-2603` ; aucun appel au modèle), ce que l'entrée du 15/10 ne savait pas. Pourquoi :
  faire marcher l'appel réel du POC du 25/10 ; le code accepte déjà Mistral par la configuration.
  Options écartées :
  - attendre le quota de gpt-6-luna : délai inconnu, le POC du 25/10 reste bloqué ;
  - l'adresse globale de Mistral (`api.mistral.ai`) : « Mistral does not commit to a specific
    inference location » ;
  - Mistral Medium 3.5 : plus cher, et Small suffit pour faire marcher le POC.

  Ne change pas : la cible gpt-6-luna et #158, qui reste ouverte ; pas d'optimisation de prompt ;
  le LLM juge (#222 à #224) n'entre pas dans ce repli. Fondement contractuel : lecture retenue par
  Sabine le 16/10, non confirmée par Mistral : elle se considère comme *Customer* des conditions
  commerciales (« other entity that you represent »), et le DPA de Mistral s'applique (registre
  des traitements, « Envoi des items au modèle des fiches : repli temporaire chez Mistral AI »).
  Entraînement refusé par Sabine le 16/10 vers 14:02Z, avant tout appel.

  Limites assumées : le plan de contrôle de Mistral (compte, clés, facturation, statistiques
  d'usage) peut être traité hors de l'UE ; demandes et réponses gardées 30 jours glissants pour
  la surveillance des abus, ZDR étant réservé au paiement à l'usage ; l'appel sur Mistral ne
  mesure rien de propre à Azure (filtre de contenu, en-tête, `reasoning_effort`, quota TPM), qui
  reste à #158. Fin du repli : quand #158 est faite. Issue : #227. Sources (consultées le
  2026-10-16) : [inférence régionale de Mistral](https://docs.mistral.ai/inference/regional-inference),
  [conditions commerciales](https://legal.mistral.ai/terms/commercial-terms-of-service/),
  [DPA de Mistral](https://legal.mistral.ai/terms/data-processing-addendum/) ; les autres pages
  lues sont au registre des traitements (« Sources du repli Mistral »). — PR #228

### Modèle des fiches : Gemini 2.5 Flash-Lite en repli temporaire

Décisions de Sabine (16/10, entre 17 h 40 et 17 h 50, heure de Paris, relayées par time-knight).
Mistral est bloqué : le débit de sa clé est à 0 requête par minute (429,
`x-ratelimit-limit-req-minute: 0`, #227, commentaire du 16/10, 15:04Z). Le repli passe donc sur
Gemini, en clé gratuite.

- **Tant que #158 n'est pas faite, le modèle des fiches est `gemini-2.5-flash-lite` (Gemini 2.5
  Flash-Lite), à l'adresse compatible OpenAI de Google,
  `https://generativelanguage.googleapis.com/v1beta/openai`, en clé gratuite, par
  `KB_LLM_PROVIDER=openai_compatible`, sans `KB_LLM_REASONING_EFFORT` (donc `temperature=0`).**
  Remplace le repli sur Mistral Small 4 (entrée précédente) : ce qui a changé, c'est le débit à 0
  de la clé Mistral. Ne révise pas « Modèle des fiches : gpt-6-luna sur Foundry » : gpt-6-luna
  reste la cible. Pourquoi Flash-Lite : c'est le seul modèle de la clé de Sabine qui a répondu aux
  appels réels du 16/10, et c'est le choix de Sabine après son propre essai (« ping »,
  `finish_reason: length`). Options écartées :
  - `gemini-3.8-flash`, le premier choix : 503 « This model is currently experiencing high demand »
    aux 4 essais ;
  - `gemini-3.5-flash` : le ping est passé, puis les 3 classements ont rendu 503, aux deux
    tentatives de chacun ;
  - `gemini-3.7-flash` : 503 ;
  - `gemini-2.5-flash` : 404, « no longer available to new users » ;
  - attendre que le débit de Mistral soit rouvert : délai inconnu, et le POC du 25/10 reste bloqué.

  **RGPD** : Sabine, le 16/10 : « On laisse de côté le RGPD pour le moment, de toute façon c'est
  pour du perso, on sort des cases. Je précise que c'est du temporaire. » Il n'y a donc pas de
  section de registre pour Google, et les conditions de Google n'ont pas été lues. À savoir, sans
  l'avoir tranché ni lu à la source : sur le palier gratuit, Google peut utiliser les contenus
  envoyés pour améliorer ses produits.

  **Aucun changement du client** (`ai_api/llm_client.py`) : Gemini n'en oblige aucun. Le seul écart
  de format constaté est le corps d'erreur, une liste `[{"error": {...}}]` dont le `code` est un
  entier. Il ne change que la lecture d'un 400 `content_filter`, le format d'Azure, qui n'a pas été
  constaté chez Gemini. Option écartée : adapter `ErrorBody` à cette liste, c'est-à-dire du code
  pour un cas non observé (choix tranché par time-knight, délégation de Sabine du 15/10).

  Limites assumées :
  - les mesures du 16/10 sont celles de Gemini 2.5 Flash-Lite en clé gratuite, pas de gpt-6-luna :
    elles donnent un ordre de grandeur à #205, pas une valeur ;
  - une rédaction (`llm_security`) a échoué au contrôle du schéma, aux deux tentatives ; la sortie
    n'a pas été lue, donc la borne dépassée n'est pas connue ;
  - le nombre de jetons de raisonnement n'est pas rendu ;
  - aucun 429 n'a été obtenu, et les limites du palier gratuit de Flash-Lite n'ont pas été lues.
    Celles de 3.8 Flash sont 5 RPM, 250 000 TPM et 20 RPD (console AI Studio, lue par Sabine le
    2026-10-16) ;
  - comme pour Mistral, rien de propre à Azure n'est mesuré : c'est à #158.

  Ne change pas : #158 reste ouverte ; pas d'optimisation de prompt ; le LLM juge (#222 à #224)
  n'entre pas dans ce repli. Fin du repli : quand #158 est faite. Issue : #227. Sources (consultées
  le 2026-10-16) : [compatibilité OpenAI de Gemini](https://ai.google.dev/gemini-api/docs/openai),
  [limites de débit](https://ai.google.dev/gemini-api/docs/rate-limits),
  [guide Gemini 3](https://ai.google.dev/gemini-api/docs/gemini-3). — PR #229

## 2026-10-17

### Fiches de veille : le contrat du LLM juge

Contrat écrit par #222 dans `docs/fiches-veille.md`, section « Juge ». Plan de la session K-B,
relu par un agent ingénieur IA indépendant, validé par Sabine le 17/10 (relayé par time-knight) ;
spec relue par un second agent ingénieur IA ; constats tranchés par time-knight, délégation de
Sabine du 15/10, sauf les seuils et les altérées, tranchés par Sabine. Complète « Fiches de
veille : le LLM juge » (2026-10-16), sans la contredire. **Révisée le 2026-10-20** : le juge sort
du contrat des fiches (« Squelette E1 E3 : cadrage du 20/10 », décision 2).

- **Les seuils de l'étalonnage sont écrits en comptes sur l'échantillon fixé, comme des critères
  de passage : au plus 2 des 20 altérées gardées, aucune pour la négation ni pour le nombre changé
  non déclaré ; au plus 20 % des réelles étiquetées « appuyée » retirées (6 si les 30 le sont) ;
  même décision, garder ou retirer, aux deux passages pour au moins 45 des 50. Une réelle
  étiquetée « non appuyée » mais gardée par le juge est comptée à part et montrée à Sabine une
  par une, sans seuil. Tout seuil manqué donne une consigne `judge-2`, et les trois mesures sont
  refaites sur 20 nouvelles altérées.** Décision de Sabine du 17/10 (« je valide », puis « 1 ok,
  2 ok »). Précise « deux taux » de l'entrée du 16/10. Pourquoi (relectures des deux ingénieurs
  IA) :
  - avec 20 ou 30 affirmations, l'intervalle exact d'un taux est large (2 sur 20 : 1,2 % à
    31,7 %) : un seuil ne vaut que comme critère de passage ;
  - un dénominateur fixe : les réelles « non appuyée », dont le nombre n'est connu qu'après
    l'étiquetage, rendraient variable celui des altérées ;
  - remesurer `judge-2` sur les mêmes altérées ajusterait la consigne au jeu d'étalonnage ;
  - la stabilité porte sur la décision, la seule qui change la fiche ;
  - une utilité manquée dit un juge trop sévère : la révision du rédacteur ne vise pas cette
    cause et garde son déclencheur, des fiches trop maigres.

  Options écartées : laisser les seuils à #224 (un seuil fixé après la mesure se règle sur elle) ;
  des seuils en taux ; compter les réelles « non appuyée » gardées avec les altérées (proposition
  de la session, écartée par Sabine). Limite assumée : le zéro sur environ 5 altérées d'une sorte
  est un signal faible (0 sur 5 : 0 à 52,2 %). — PR de #222
- **Chaque altérée passe les contrôles 1 à 7. « CVE changée » est remplacée par la CVE d'un autre
  item cité (cas « mauvais item ») ; un « nombre changé » est un nombre non déclaré comme fait.**
  Décision de Sabine du 17/10. Pourquoi (relecture de la spec) : la fidélité retire toute CVE qui
  n'est pas celle de l'item cité, et tout fait déclaré absent de l'item ; une altérée qui ne
  passerait pas ces contrôles mesurerait un cas qui n'arrive jamais au juge. Option écartée :
  retirer la sorte « CVE » sans la remplacer. — PR de #222
- **Une affirmation n'est gardée que si son verdict est `supported` et sa raison
  `supported_by_item` ; toute autre paire, ou l'absence de verdict, la retire. Une sortie vide
  (`{"verdicts": []}`) retire donc tout, sans échec, et se voit par `claims_without_verdict`.**
  Choix de la session (plan validé par Sabine) ; sortie vide tranchée par time-knight. Pourquoi :
  un verdict qui se contredit n'est pas un appui (échouer fermé) ; la règle du critère de #222
  (« une affirmation sans verdict est retirée ») est tenue. Options écartées : garder tout
  `supported` ; refuser toute la sortie pour une paire incohérente (un appel de plus et le sujet
  perdu) ; faire d'une sortie vide un échec `completeness` avec nouvelle tentative (contredit le
  critère). Limite assumée : une panne du juge qui rend une liste vide ressemble à « rien
  d'appuyé » ; seule la métrique la distingue. — PR de #222
- **`FailedCheck` gagne une seule valeur, `claim_id` ; le juge réutilise `completeness` pour une
  affirmation jugée deux fois.** Choix de la session. Pourquoi : `completeness` dit déjà « un
  élément présent deux fois » au classement. Option écartée : réutiliser `item_id` pour un
  identifiant d'affirmation (la métrique dirait un item pour une affirmation). Limite assumée :
  `call_model` exige un rappel par valeur ; chaque étape écrit donc des rappels qu'elle n'envoie
  jamais (`claim_id` au classement et à la rédaction ; `subject`, `item_id`, `markup` au juge).
  — PR de #222
- **Le juge n'envoie rien tant qu'un repli de fournisseur du rédacteur (Mistral, Gemini) est
  actif ; #223 code un garde-fou vérifié avant l'appel. Le repli de déploiement Azure du 16/10 et
  le `replay` restent permis.** Constat bloquant de la relecture de la spec, tranché par
  time-knight. Pourquoi : les deux entrées de repli du 16/10 et le registre des traitements
  disent que le juge n'entre pas dans ces replis ; la spec écrivait « même fournisseur que le
  rédacteur », ce qui l'y aurait fait entrer. On ne peut pas compter sur l'échec de l'appel : le
  corps de la requête, items compris, part avant toute réponse d'erreur. La condition dit quand
  le juge peut envoyer, pas à qui : la spec reste indépendante du fournisseur. — PR de #222
- **`KB_LLM_JUDGE_MODEL` est exigée aussi en `replay`, validée mais envoyée nulle part ;
  `KB_LLM_REASONING_EFFORT` est commun au rédacteur et au juge.** Choix de la session, confirmé
  par time-knight. Pourquoi : une configuration testée en `replay` échoue fermé comme en vrai ;
  une variable de moins pour l'effort, sans besoin mesuré d'un réglage propre. Limites assumées :
  en `replay`, `KB_LLM_MODEL` n'est pas lue, la variable du juge l'est (asymétrie) ; que
  `reasoning_effort: "none"` vaille pour les deux déploiements reste ouvert jusqu'à #158.
  — PR de #222

Sources (consultées le 2026-10-17) : celles de `docs/fiches-veille.md`, « Sources », section
« Juge ».

### Modèle des fiches : gpt-6-luna sur l'abonnement de l'organisme de formation

Décisions de Sabine du 17/10 (relayées par time-knight, qui a guidé le déploiement dans le
portail) ; plan de #158 relu par un agent architecte plateforme Azure, validé par Sabine.

- **gpt-6-luna est déployé sur l'abonnement Azure de l'organisme de formation de Sabine, dans une
  ressource en France Central, en Zone de données standard (zone de données EUR), version
  2026-09-22 figée (« Refuser les mises à niveau automatiques »), 140 000 jetons par minute,
  garde-fous `DefaultV2`.** Met en œuvre « Modèle des fiches : gpt-6-luna sur Foundry »
  (2026-10-16) sur un autre compte que celui prévu : le compte personnel d'essai, à 0 TPM, n'est
  plus utilisé. Pourquoi l'abonnement de l'organisme : Sabine, « j'ai mon contrat de formation et
  la ressource est faite pour y déployer le projet de certification ». Options écartées :
  - un premier déploiement en Global Standard : le traitement peut avoir lieu dans toute région
    Azure, contraire à la règle « zone UE quand le fournisseur l'offre »
    (`.claude/rules/conformite.md`) ;
  - « Mettre à niveau une fois la nouvelle version par défaut disponible », proposée par défaut :
    elle change le modèle sans prévenir, contraire à la version figée.

- **Fondement de la sous-traitance : le contrat de formation de Sabine (lecture (a)).** Le client
  de Microsoft est l'organisme (abonnement « Plan Azure », annuaire et compte de connexion de
  l'organisme, rôle « Lecteur » de Sabine, aucun compte de facturation visible) ; selon le DPA de
  Microsoft du 22/05/2026, Microsoft est le sous-traitant de son client. Registre des traitements,
  « Envoi des items au modèle des fiches ». Options écartées par Sabine :
  - (b) écrire une limite assumée, la chaîne Sabine → organisme → Microsoft n'étant pas
    contractualisée, comme pour Gemini le 16/10 ;
  - (c) ne pas envoyer de données réelles sur cet abonnement : la mesure de #158 se fait sur une
    veille réelle.

  Limites assumées : un administrateur général de l'annuaire de l'organisme peut se donner accès à
  la ressource et à ses clés ; si l'organisme active les preuves des prompts de Defender for
  Cloud, des extraits des prompts apparaissent dans ses alertes ; Sabine, « Lecteur », ne reçoit
  pas le courriel d'avant retrait du modèle, envoyé aux propriétaires de l'abonnement ; la durée de
  l'accès de l'organisme n'est pas connue. L'organisme n'est nommé dans aucun fichier du dépôt
  (décision de Sabine du 17/10 : dépôt public le 25/10).

- **Pour les phases 1 (mécanique) et 2 (rodage de l'ETL et des fiches), le rédacteur et le juge
  sont `gpt-6-luna` : le juge suit le repli du déploiement du 16/10 ; le juge définitif se choisit
  en phase 3 (fiabilité des LLM et de leurs sorties).** Décisions de Sabine du 17/10 ; applique
  `docs/fiches-veille.md`, « Juge », « Réglage », « Repli du déploiement », sans la réviser.
  Pourquoi, selon Sabine : « Le juge était le même modèle que le rédacteur parce que je n'avais pas
  vraiment d'autres possibilités hier. Aujourd'hui que j'ai plus de liberté sur un choix de modèle,
  je veux faire les choses de façon structurée. Si c'est prouvé et documenté qu'un juge d'une autre
  famille est une bonne pratique, on le fera. » Le repli du 16/10 était donc une contrainte
  d'accès, pas un choix de fond. L'étude des modèles du 17/10 (agent ingénieur IA, lecture seule)
  recommande `gpt-6-luna` comme rédacteur ; pour le juge de la phase 3, deux candidats d'autres
  familles : DeepSeek-V4-Flash (disponibilité générale, zone de données UE, retrait le 2028-02-20)
  et Mistral-Large-3 (préversion, version non figée, français documenté) ; `gpt-5.4-mini` sera
  comparé comme rédacteur en phase 3. #158 vérifie seulement que les deux candidats tiennent les
  sorties structurées strictes, sur des données fabriquées. Option écartée : déployer
  `gpt-5.6-luna` comme juge, que recommandait la session : un modèle de la même famille que le
  rédacteur. Limite assumée en phases 1 et 2 : le biais d'un juge envers ses propres textes, que
  la spec voulait éviter, n'est pas écarté. **Révisée le 2026-10-20** pour le juge : il sort du
  contrat des fiches (« Squelette E1 E3 : cadrage du 20/10 », décision 2).

- **Fin des replis de fournisseur de #227 (Mistral Small 4, puis Gemini 2.5 Flash-Lite) à la
  fusion de la PR de #158.** « Modèle des fiches : Mistral Small 4 en repli temporaire » et
  « Gemini 2.5 Flash-Lite en repli temporaire » prévoyaient « Fin du repli : quand #158 est
  faite ». La section du registre sur Mistral est retirée : ses 4 sondes ne portaient aucune
  donnée de K-B.

- **Les envois à Google du 16/10 sont tracés au registre (« Repli temporaire chez Google »).**
  Décision de Sabine du 17/10, relayée par time-knight. **Révise** le point RGPD de « Gemini 2.5
  Flash-Lite en repli temporaire » (« On laisse de côté le RGPD pour le moment ») : de vrais
  champs d'items y sont partis, et le registre doit nommer ce destinataire, même passé.

Sources (consultées le 2026-10-17) : celles du registre des traitements, « Sources de l'envoi au
modèle » ; [Deployment types](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/deployment-types) ;
[Foundry Models lifecycle and support policy](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirements).
— PR de #158

### Appel du modèle : cache de prompt coupé

Constat de la relecture du plan de #158 par un agent architecte plateforme Azure, vérifié à la
source ; tranché par time-knight le 17/10 (délégation de Sabine du 15/10).

- **Chaque requête au modèle envoie `prompt_cache_options: {"mode": "explicit"}` sans point
  d'arrêt : le service n'écrit aucun cache de prompt.** À partir de GPT-5.6, le cache est actif par
  défaut et s'écrit sur le dernier message, donc sur le texte des items ; il reste réutilisable
  « for at least 30 minutes, but the service might retain it longer ». Pourquoi : une correction
  de minimisation (RGPD, RGESN 1.6), pas un risque accepté ; chaque message de K-B est différent,
  le cache n'apporterait presque rien ; la mesure de #158 reflète alors la production. Le champ
  est envoyé à chaque appel, sans réglage : en phases 1 et 2, seul `gpt-6-luna` est appelé (choix
  de la session, accordé par time-knight). Options écartées : garder le cache et le décrire au
  registre (une rétention de plus pour un gain presque nul) ; une variable d'environnement pour
  l'activer (un réglage sans second usage aujourd'hui). Limite assumée : selon la doc, un modèle
  d'avant GPT-5.6 refuse le champ par un 400 (`gpt-5.4-mini`, candidat rédacteur de la phase 3) ;
  les candidats juges sont mesurés par #158 ; un réglage viendra avec le second modèle, si besoin
  (#223, phase 3). Source : [Prompt caching](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/prompt-caching),
  consultée le 2026-10-17. — PR de #158

### Appel du modèle : délai de lecture à 90 s

Mesure de #158 sur gpt-6-luna (2026-10-17) ; tranché par time-knight (délégation de Sabine du
15/10), sur la recommandation de la session.

- **Le délai de lecture d'une réponse du modèle passe de 60 à 90 s (`LLM_CALL_TIMEOUT_SECONDS`) ;
  la borne d'un appel passe de 150 à 210 s (2 × (5 + 90) + 20).** **Révise** la valeur supposée
  de « Appel du modèle » (2026-10-15). Ce qui a changé : la mesure. Environ 7,35 ms par jeton de
  sortie sur 12 appels réels, soit ~60 s pour une sortie de 8 192 jetons. L'appel n'étant pas en
  diffusion, une sortie valide proche du plafond finirait en `llm_timeout`, sans nouvelle
  tentative (`send_and_check`) : la fiche serait perdue. Option écartée : garder
  60 s et plafonner la rédaction vers 6 000 jetons, car la marge reposerait sur une estimation non
  mesurée de la plus longue sortie permise par les bornes. Le choix de #205 entre parallèle et
  tâche de fond n'en dépend pas : la chaîne mesurée fait ~98 s en série pour 8 sujets, sous les
  240 s de l'ingress d'Azure Container Apps, et la borne de pire cas les dépasse avec 60 comme avec
  90 s. Un test garde la raison : au débit mesuré, 8 192 jetons avec 40 % de marge tiennent dans
  le délai. — PR de #158

### Fiches de veille : la durée d'une demande

Plan de #205, relu par un agent architecte logiciel, validé par Sabine le 17/10 (relayé par
time-knight, qui a vérifié les recommandations par commande ou à la source). Le pourquoi est celui
du plan, que Sabine a validé. Tranche la question posée le 15/10 et écrite le 16/10 sur #205
(point 5) : « rédiger les sujets en parallèle, ou passer `POST /digests` en tâche de fond ».

- **Les appels au modèle se font en série, un sujet après l'autre, sous une échéance de 200 s
  (`DIGEST_REQUEST_TIMEOUT_SECONDS`) comptée dès l'arrivée de la demande, qui borne aussi la
  lecture par l'API de données. Ni parallèle, ni tâche de fond.** C'est une troisième option, que
  la question du 15/10 ne posait pas. Pourquoi :
  - la chaîne mesurée par #158 dure environ 98 s pour 8 sujets, juge compris (113 s avec les
    appels les plus lents), sous les 240 s que l'ingress HTTP d'Azure Container Apps laisse à une
    requête ;
  - le pire cas (22 appels de 210 s) dépasse 240 s en série comme en parallèle : seule une
    échéance borne la demande, quel que soit le choix ;
  - la série garde le `replay` tel quel, puisqu'il donne ses étapes dans l'ordre (« Appel du
    modèle »), et évite une pointe sous le quota de 140 000 jetons par minute.

  Ce que voit le client : un sujet pas encore rédigé à l'échéance va dans `failed_subjects` avec
  `llm_timeout`, et les autres sont rendus ; un classement pas fini donne 504. Aucune requête ne
  part s'il reste moins de 10 s (`MIN_SECONDS_FOR_LLM_REQUEST`), au-dessus de la rédaction la plus
  lente mesurée (9,3 s) : les items ne partent pas pour une réponse que l'échéance jetterait. Une
  rédaction plus longue, jusqu'à environ 60 s au plafond de sortie, peut encore être coupée.
  Options écartées :
  - le parallèle : environ 30 s, mais un `replay` à refaire (choisir l'étape d'après le corps
    de la requête) et des 429 possibles selon la doc « Manage quota », pour un gain sans besoin
    mesuré ;
  - la tâche de fond : elle demande un état gardé entre deux requêtes, contraire à la règle 7
    de `poc.md`, et n'est utile qu'au-delà de 240 s.

  Limite assumée : la spec suppose une demande à la fois ; une seconde demande dans la même minute
  peut rendre un 429. — PR de #205
- **L'échéance n'est pas une borne dure ; c'est écrit en limite.** Le délai de lecture d'httpx2
  vaut pour chaque morceau reçu, et httpx2 2.13.1 n'a pas de délai total (doc d'httpx2,
  « Timeouts », lue par Context7 le 2026-10-17 ; vérifié dans son code). L'échéance ramène les
  délais de chaque requête au temps restant et se contrôle entre deux morceaux de l'API de
  données. Chaque phase d'une requête (pool, connexion, écriture, lecture) étant ramenée
  séparément, une requête lancée avant l'échéance peut la dépasser de la somme de ses délais :
  30 s au plus pour l'API de données ; pour le modèle, 20 s plus sa lecture, et sans borne pour une
  réponse envoyée au compte-gouttes, dont httpx2 lit la réponse entière (constat de `/code-review`,
  tranché par time-knight, délégation de Sabine du 15/10).
  **Revoit le motif** du rejet du « délai total par tentative » dans « Appel du modèle »
  (2026-10-15), « pour une borne que la demande pose déjà » : la demande pose une borne, mais pas
  une borne dure. Le rejet reste ; c'est son motif qui change.
  Option écartée : lire la réponse du modèle en flux pour contrôler l'échéance entre deux morceaux
  (relecture du plan) : elle resterait dépassable de la somme des délais, et le fournisseur répond
  d'un bloc. — PR de #205
- **Le schéma envoyé au modèle est écrit à la main, et les bornes des fiches vont dans la
  consigne, en texte.** Pourquoi (constat de la relecture du plan, confirmé à la source par
  time-knight) : Azure refuse `minItems`, `maxItems`, `minLength` et `maxLength` en mode strict
  ([structured outputs](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs),
  consultée le 2026-10-17). Le modèle Pydantic qui revérifie la sortie porte les bornes de
  structure (12 affirmations, 1 à 5 items) et écrirait donc ces mots-clés dans un schéma dérivé.
  Le `replay` ne lit pas le schéma : les tests seraient restés verts, et chaque vrai appel aurait
  échoué. Un test parcourt chaque schéma envoyé.
  Options écartées :
  - dériver le schéma puis le nettoyer : les `$ref` et `$defs` de Pydantic ne sont pas vérifiés
    chez Azure ;
  - le mot-clé `description` du schéma pour les bornes : non vérifié chez Azure.

  **Accorde** la spec, qui disait « Les bornes sont envoyées au modèle dans le `json_schema` »
  (commentaire daté sur #205). — PR de #205

### Coffre Obsidian : une copie dans un dossier ignoré du dépôt

Décision de Sabine du 2026-10-17, relayée par time-knight.

- **Exception provisoire à « Données hors du dépôt de code » (2026-09-29) : le coffre Obsidian
  de K-B est une copie des clips existants, rangée dans un dossier du dépôt que git ignore (règle
  `temp/` du `.gitignore`). Le code et la doc ne le désignent que par `KB_VAULT_DIR`, jamais par
  son chemin complet.** Pourquoi, selon Sabine : la praticité en développement. La copie sert de
  matière à la collecte des clips (#14, corps de #147) ; une fixture qui en est tirée est réduite
  au minimum, auteur remplacé, extrait court. Option écartée : le coffre hors du dépôt (critère
  initial de #147, conseil de time-knight), moins pratique en développement. La séparation du
  coffre et du dossier de données (2026-10-09) reste. Levée avec le vrai coffre, quand Web
  Clipper sera réglé pour y écrire (réglage à venir, sans issue). Limite assumée : des données
  personnelles (des noms d'auteurs) sont dans le dossier d'un dépôt public au 25/10, protégées
  par la seule règle `temp/` ; un `git clean -x` ou `-X`, ou une image construite sans
  `.dockerignore` qui exclut `temp/`, les toucherait. — PR de #147

### Collecte : clips (suite)

Décisions de Sabine du 2026-10-17 sur le plan de #14, relayées par time-knight.

- **Le frontmatter d'un clip est lu par PyYAML (dépendance d'exécution), avec son chargeur
  `BaseLoader`, et `types-pyyaml` entre dans les dépendances de développement.** Décision de
  Sabine, sur recommandation. Pourquoi, celui de la recommandation : Web Clipper écrit du YAML,
  avec ses guillemets et ses échappements, qu'un lecteur reconnu lit comme Obsidian ;
  `BaseLoader` ne devine aucun type et ne construit aucun objet (« Only loads the most basic
  YAML. All scalars are loaded as strings », page
  [PyYAML yaml.load(input) Deprecation](https://github.com/yaml/pyyaml/wiki/PyYAML-yaml.load(input)-Deprecation),
  lue par Context7 le 2026-10-17 ; une étiquette `!!python/…` n'est pas appliquée, sa valeur
  est lue comme du texte, vérifié par un test), et K-B lit lui-même les dates. PyYAML était déjà dans `uv.lock`, par
  `openapi-spec-validator` ; sans `types-pyyaml`, `mypy --strict` échoue. ruff prend
  `BaseLoader` pour un chargeur dangereux (S506) : `# noqa: S506`, avec la raison en commentaire.
  Options écartées : `yaml.safe_load`, qui devine les types (`yes` en booléen, un jour en date,
  un nombre en entier) et multiplie les cas à tester ; une exception mypy dans `pyproject.toml`
  au lieu des types ; une lecture faite à la main du gabarit relevé par #147 (environ 1 h de
  plus, et un YAML qu'elle n'a pas prévu serait lu autrement qu'Obsidian). Limite assumée : deux
  paquets de plus à suivre par l'audit des dépendances. — PR de #14
- **Un clip est un flux de nouveautés par URL : la première version vue d'une URL est gardée ;
  un clip copié de nouveau est écarté `already_seen`.** Décision de Sabine : ses clips restent
  tels quels, elle ne les retouche pas. Ferme la question ouverte « les versions d'un clip
  annoté » (relecture du 2026-10-09). Options écartées : remplacer la version en base quand le
  clip change (la recommandation de la session, avec `revised_at` : sans objet si les clips ne
  changent pas) ; un catalogue d'état comme Zotero (recopier tout le coffre à chaque collecte,
  contraire à la copie de « chaque clip nouveau ou modifié » du 2026-10-09). Limites assumées : un
  clip modifié quand même n'est pas repris ; un clip supprimé du coffre reste en base ; deux
  fichiers de même URL dans une même collecte, le premier dans l'ordre des noms de pages
  l'emporte. La collecte reste incrémentale et copie tout clip changé : le brut garde chaque
  version. **Précisée le 2026-10-19** : jusqu'à la sauvegarde de la base, au 08/11 (« Brut :
  catalogues d'état et conservation »). **Révisée le 2026-10-19** : un clip dont le contenu a
  changé est réécrit (« Collecte : mise à jour des `.md` importés »). **Précisée le 2026-10-20** :
  la sauvegarde de la base attend « La base au temps 3 » (« Squelette E1 E3 : cadrage du 20/10 »,
  décision 6). — PR de #14
- **Le texte complet d'un clip va dans la colonne `clip.body` de son sous-type ; ni `author`, ni
  `description`, ni `tags` n'entrent en base.** Décision de Sabine, sur recommandation. Pourquoi,
  celui de la recommandation : la spec (« titre, URL source, date, et le texte gardé ») et la
  minimisation, comme Zotero le 2026-10-13. La question « DOCUMENT ou CONTENU pour le texte
  complet » **reste ouverte** (Sabine, à questionner plus tard) : une future table CONTENU
  déplacerait cette colonne. Option écartée : créer CONTENU ici, hors du périmètre de #14.
  Limite assumée : le texte peut contenir la signature de l'article et les notes de
  l'utilisatrice (registre des traitements). **Révisée le 2026-10-19** pour les tags seulement :
  ils entrent en base (« Collecte : tags des `.md` importés »). — PR de #14

## 2026-10-18

### API IA : organisation par rôle

Décisions de Sabine du 2026-10-17 et du 2026-10-18 sur #242, relayées par time-knight.

- **Le paquet `src/k_b/ai_api/` reprend le plan de l'API de données : un dossier par rôle.
  `connectors/` (`outbound.py`, `llm_replay.py`, `llm_settings.py`, `llm_client.py`,
  `data_api_settings.py`, `data_api_client.py`) ; `stages/` (`classification.py`, `writing.py`,
  les étapes qui appellent le modèle) ; à la racine, `digests.py` (le parcours), `deadline.py` et
  `watch_items.py`. Après #156, la racine reçoit le plan de `data_api` : `app.py`, `routers/`,
  `schemas/`, `errors.py`, `dependencies.py`, `health.py`, `request_log.py`.** Pourquoi, selon
  Sabine : voir ce qui est où d'un coup d'œil, l'organisation apprise en DWWM, déjà celle de
  `data_api` (entrée du 2026-10-14, « Paquet `src/k_b/data_api/`, organisé par rôle », qui
  écartait les fichiers à plat « quand l'API IA reprendra le même plan »). Ranger avant #156 et
  #206, pour qu'aucun code nouveau ne soit déplacé ensuite ; un déplacement seul, sans changement
  de logique. `connectors/` regroupe le code par lequel l'API IA se connecte aux services
  extérieurs, et chaque module y joue le rôle d'une Gateway au sens de Martin Fowler (« An object
  that encapsulates access to an external system or resource »,
  [Catalog of Patterns of Enterprise Application Architecture](https://martinfowler.com/eaaCatalog/),
  entrée [Gateway](https://martinfowler.com/eaaCatalog/gateway.html), consulté le 2026-10-18).
  Les noms de fichiers ne changent pas ; `tests/ai_api/` reste à plat, comme `tests/data_api/`.
  Options écartées : un dossier `settings/` (`llm_settings` importe `llm_replay` : `settings/` et
  `connectors/` s'importeraient l'un l'autre) ; un dossier `digests/` pour toute la chaîne
  (`data_api_client` importe `watch_items`) ; `digests.py` dans `stages/` (c'est le parcours, pas
  une étape) ; `deadline` et `watch_items` dans `common/` (un dossier pour deux modules) ; le nom
  `clients/` (« client » désigne déjà, dans `data_api`, celui qui appelle l'API avec sa clé) ;
  les noms `gateways/`, `adapters/`, `outgoing/`, un dossier `services/`, des fichiers renommés
  en `<entité>_<rôle>.py` et `watch_items` sous `schemas/` (raison non consignée dans #242).
  Limite assumée : le nom de journal de `llm_settings` et de `data_api_settings`
  (`getLogger(__name__)`) devient `k_b.ai_api.connectors.*`, écrit dans chaque ligne ; rien ne
  lance encore l'API IA. — PR de #242
- **Le sens des imports dans `ai_api` est tenu par un test, lu à trois niveaux, en six couches
  du bas vers le haut : `deadline` et `watch_items` ; `outbound` et `llm_replay` ; les deux
  réglages ; les deux clients ; les deux étapes ; `digests`. Un module n'importe que les couches
  sous la sienne : deux modules d'une même couche ne s'importent pas ; un `__init__.py` n'importe
  rien d'`ai_api`.** Décision de Sabine du 2026-10-18, sur recommandation. Pourquoi, celui de la
  recommandation : une liste par couche et une seule règle, sur le modèle de la règle interne
  d'`etl` ; le code de `main` la respecte (25 imports internes, tous vers une couche
  inférieure). Le test ajoute un paramètre `depth` (2 par défaut) à `parse_imported_modules` et
  à `list_imported_modules` : les tests existants et `AI_API_ALLOWED_MODULES` ne changent pas.
  Options écartées : les flèches de #242 seules, qui laissent deux étapes s'importer ; une table
  « module → modules permis », plus longue que six couches. Limite assumée : un import latéral
  dont on aurait besoin un jour se décidera alors, et changera le test. — PR de #242

### Codes de sortie de kb

Décisions de Sabine du 2026-10-18 sur #193, relayées par time-knight, sur recommandation du plan
relu par un sous-agent.

- **Les codes de sortie de `kb` sont les membres d'une énumération, `ExitCode` (`cli.py`), dont
  chacun porte son sens : 0 `SUCCEEDED`, 1 `FAILED`, 2 `NOT_STARTED` (aussi l'usage refusé par
  `argparse`), 3 `SERVER_NOT_STARTED` (rendu par uvicorn, pas par `kb`), 4 `PARTIAL_FAILURE`,
  143 `STOPPED_BY_SIGTERM`. Ils sont listés par `kb --help`, généré depuis l'énumération ; le
  `README.md` garde les cas de chaque commande.** Pourquoi : en job de conteneur, le code est la
  seule façon de savoir ce qu'a fait `kb` sans lire le journal (règle 6 de `poc.md`). 0, 1 et 2
  gardent le sens décidé le 2026-10-01. 4 est la première valeur libre après 3, que rend uvicorn
  (`STARTUP_FAILURE`, `uvicorn/config.py:81`, 0.54.0) quand `kb serve` ne démarre pas. 143 est
  128 + 15, le code d'un processus arrêté par SIGTERM
  ([Bash Reference Manual, Simple Commands](https://www.gnu.org/software/bash/manual/html_node/Simple-Commands.html),
  consulté le 2026-10-18) ; `kb serve` y sort aussi, hors PID 1 : uvicorn remet l'ancien
  gestionnaire, `SIG_DFL`, et renvoie le signal (`uvicorn/server.py:339-349`), qu'un PID 1
  ignore (non vérifié en conteneur). Options écartées : 3 pour l'échec partiel (celui d'uvicorn) ; 64 à
  78 (`sysexits.h`, d'autres sens) ; 23 (propre à rsync) ; 1 pour SIGTERM (indistinct d'un
  échec) ; un dictionnaire des sens à côté de l'énumération, ou le `README.md` seul (deux copies
  à tenir). — PR de #193
- **Le code d'échec partiel (4) vaut pour `kb collect` seul : au moins une source a réussi, au
  moins une a échoué, et l'état de collecte est écrit. Toutes les sources lancées en échec, ou
  l'état non écrit, restent 1 ; `kb import` garde 0, 1 et 2.** Écart à la lettre de #193, qui
  prévoyait un code partiel pour `collect` et `import`. Pourquoi, celui de la recommandation :
  l'import est une seule transaction, qui écrit tout ou rien (`etl/load.py`) ; un import avec
  des rejets va au bout et sort en 0. L'état non écrit reste 1, comme l'écrivent #60 et #64 :
  une panne de disque ou de droits revient au lancement suivant. Options écartées : un import
  avec rejets en 4 (change le sens de 0, et un fichier illisible, relu et rejeté à chaque
  import, ferait sortir chaque import suivant en 4) ; l'erreur de l'import en 4 (rien n'est
  écrit, ce n'est pas partiel) ; l'état non écrit en 4 (contredit #60 et #64). — PR de #193
- **Sur SIGTERM, `kb collect` et `kb import` lèvent `StoppedBySigtermError`, un `SystemExit`, et
  sortent en 143 après le même nettoyage que pour toute exception ; `kb serve` garde le
  gestionnaire d'uvicorn.** Pourquoi : `docker stop` envoie SIGTERM puis SIGKILL (règle 6 de
  `poc.md`) ; une sous-classe dédiée laisse passer intact le `SystemExit(3)` d'uvicorn. 143 dit
  « arrêté par SIGTERM ; ce qui a été validé avant le signal est gardé » : le gestionnaire reste
  posé jusqu'à la fin de la commande, et un signal tardif, reçu après l'écriture de l'état de
  collecte ou la validation de l'import, sort aussi en 143 (tri de la revue de code, tranché par
  time-knight par délégation de Sabine). Ce n'est pas une régression : sans gestionnaire, le même
  signal tuait déjà le processus avec 143 ; retirer le gestionnaire avant l'affichage laisserait
  une autre fenêtre, entre l'écriture et le retrait. Limites assumées : `kb create-db` et
  `kb openapi` n'ont pas de gestionnaire (périmètre de #193, écart à la règle 6 de `poc.md`, qui
  dit « chaque commande ») ; un SIGTERM pendant la collecte perd les dates des sources déjà
  collectées dans ce lancement, qui sont recollectées au suivant (déjà vrai sans gestionnaire).
  — PR de #193
- **Le journal d'import n'est supprimé que si la base n'a pas validé l'import : le `commit` a
  levé une `sqlite3.Error`, ou une transaction reste ouverte. Une interruption (Ctrl-C, SIGTERM)
  reçue une fois la base validée garde l'import et son journal, et le journal de fonctionnement
  le dit (`import committed, log kept: '<nom du journal>'`, le nom et non le chemin, que
  `quote_value` couperait avant le nom).** Décision de Sabine du
  2026-10-18, ajoutée au périmètre de #193 (conception par l'architecte de données de
  time-knight). Pourquoi : Python lève l'exception d'un signal une fois le `commit` revenu, encore
  dans le `try` ; la version d'avant supprimait alors le journal d'un import validé, dont les
  fichiers enregistrés ne sont plus relus. Constaté avec un vrai SIGTERM envoyé pendant des
  `commit` (44 essais sur 300 : exception levée, base validée, plus de transaction ouverte).
  Applique l'entrée « supprimé si la validation échoue » (journal d'import écrit avant la
  validation) sans la contredire. Options écartées : masquer SIGTERM autour du `commit`
  (`signal.pthread_sigmask` : plus de mécanique, Unix et thread principal seulement, mêlée au
  gestionnaire de `cli.py`) ; écrire le journal après le `commit` (choix de #105, inversé par
  #106) ; le journal en base, dans la même transaction que `raw_data` (taille L, aucun
  code ne lit le journal, et la reconstruction de la base effacerait l'historique ; à rouvrir si
  un lecteur programmatique apparaît). Limite assumée : un commit refusé suivi, dans la même
  instruction, d'un signal remplace la `sqlite3.Error` par l'exception du signal ; si SQLite a
  annulé de lui-même, le journal reste sans import. — PR de #193

### Ligne de commande : une porte mince

Décisions de Sabine du 2026-10-18 sur #247, relayées par time-knight ; tri des revues par
time-knight (délégation de Sabine du 2026-10-15).

- **La ligne de commande est une porte : `cli.py` garde `main`, l'aiguillage et la liste des codes
  de sortie ; chaque commande a son module dans `commands/` (`<commande>_command.py`), à côté de ce
  qu'elles partagent, écrit une fois (`exit_codes.py`, `sigterm.py`, `run_log.py`,
  `environment.py`) ; `commands/__init__.py` est vide.** Pourquoi, selon Sabine : « cli mince et
  chaque réglage dans sa couche ». `cli.py` faisait 700 lignes sur `main` 4ebff3a, et #63, #200 et
  #209 (`kb digest`) allaient l'allonger. Déplacement seul : aides, messages et codes de sortie
  inchangés. `ExitCode` passe de `cli.py` (entrée « Codes de sortie de kb », plus haut) à
  `commands/exit_codes.py`, sans autre changement. Options écartées : un paquet `cli/` dont
  `__init__.py` porte `main` (`__init__.py` reste vide, `code.md`) ; un seul `cli.py` une fois les
  règles sorties (environ 470 lignes) ; le nom `cli_commands/` (répète `cli`) ; des modules nus
  (`import.py` est impossible, `import` est un mot réservé). — PR de #247
- **Chaque règle qui n'est pas propre au terminal va dans sa couche, et se lit sous la forme
  « valeur ou motif du refus » : les réglages de `kb serve` dans `data_api/settings.py`, les clés
  des clients dans `core/api_keys.py`, le choix des sources (`KB_COLLECT_ONLY`) dans
  `etl/collected_sources.py`, module de composition d'`etl` qui reçoit `SOURCE_KINDS` en paramètre.
  La porte journalise le refus, sous le nom `k_b.cli` (`LOGGER_NAME`), et décide de s'arrêter.**
  Pourquoi les clés dans `core/` : l'API IA ne peut importer que `ai_api`, `items` et `core`, et
  #156 prévoit le module commun des clés : il serait sinon déplacé deux fois (décision de Sabine).
  **Révise** l'entrée « Le module commun des clés par client reste à #156 » (PR de #204) : #247
  pose le module, et #156 garde le préfixe `KB_AI_API_KEY_` de l'API IA. Pourquoi la porte
  journalise : le nom de journal de chaque ligne ne change pas, et `tests/test_cli.py` le lit.
  Options écartées : laisser la couche journaliser, comme `llm_settings` (le nom deviendrait
  `k_b.data_api.settings`) ; `getLogger(__name__)` dans `commands/` (`k_b.commands.<module>` dans
  chaque ligne) ; les clés dans `data_api/settings.py` ; `collected_sources` qui importe
  `SOURCE_KINDS` (chaque test de collecte le remplacerait dans deux modules). — PR de #247
- **Les trois lectures de la porte passent par une seule fonction,
  `value_or_log_refusal` (`commands/run_log.py`) : la valeur lue, ou `None` après avoir journalisé
  le refus.** Tri de la revue de code par time-knight. Pourquoi : la troisième occurrence du même
  motif (`code.md`) ; le nom dit ce qui revient, l'appel étant une affectation, et fait pendant à
  `*_or_refusal`. Options écartées : trois copies ; les noms `log_refusal` (ne dit pas qu'une
  valeur revient) et `unwrap_or_log_refusal` (« unwrap » n'est pas un mot de K-B) ; un type
  `Refusal` (aucun lecteur n'a une `str` pour succès). Limites assumées : un refus se reconnaît à
  ce qu'il est une `str`, et un type sera posé si un lecteur dont le succès est une `str` arrive ;
  les deux copies d'`ai_api` (`read_llm_settings`, `read_data_api_settings`) restent, et la
  fonction rejoindra `core/` avec elles. — PR de #247
- **Le sens des imports de la porte est tenu par un test : `commands/` n'importe pas `cli`, et la
  composition d'`etl` (`source_kinds`, `collected_sources`) n'importe ni `cli` ni `commands`.**
  Tri de la revue de code par time-knight. Pourquoi : le rangement crée la règle, et elle se tient
  par un test, comme pour `ai_api` (#242). Option écartée : un `grep` du critère de fin seul, qui
  ne protège pas la suite. — PR de #247

### API de données : un module rassemble les routeurs

- **Le dossier de routeurs d'une API est rassemblé par un module à part, à côté de l'app :
  `data_api/api_router.py`, qui crée `api_router` et inclut `item_router.router` puis
  `trend_router.router`, sans argument. L'app n'importe que lui et l'inclut une fois ;
  `routers/__init__.py` reste vide. L'API IA suivra la même règle à #156.** Décision de Sabine
  du 2026-10-18. Pourquoi, selon elle : le dossier `routers/` a son fichier qui le rassemble,
  comme l'`index.js` de l'organisation apprise en DWWM, et chaque routeur ajouté ne touche plus
  `app.py`. Le nom vient du full-stack-fastapi-template (`backend/app/api/main.py`). Complète
  l'entrée du 2026-10-14 (« Paquet `src/k_b/data_api/` », où `app.py` rassemblait les
  routeurs) et le plan de `data_api` annoncé pour l'API IA (entrée de #242), qui comprend
  désormais `api_router.py`. Sa place, selon Sabine (18/10) : « router.py est le routeur
  principal de l'api et dans routers/ ce sont les routeurs secondaires importés par le
  principal » ; le principal est à la racine de l'API, comme `backend/app/api/main.py` hors de
  `api/routes/` dans le modèle. Options écartées : `routers/api_router.py` (relevé par la revue
  de code ; il mêlerait le principal aux routeurs d'entité, et la garde ne serait plus « `app.py`
  n'importe rien de `routers/` ») ; `routers/__init__.py` comme rassembleur (`code.md` : un
  `__init__.py` reste vide) ; les noms `index_route.py` (c'est un routeur, pas
  une route), `routers_index.py` (proposition de la session), `router.py` (à une lettre de
  `routers/`), `routes.py` (se confond avec `routers/`), `routers.py` (impossible à côté du
  paquet `routers/`) ; laisser `app.py` inclure chaque routeur. Aucun argument à l'inclusion : la
  clé reste une dépendance de l'app, qu'aucun routeur ajouté ne peut quitter. — PR de #246
- **La règle est tenue par deux tests de `tests/test_module_dependencies.py` : `app.py`
  n'importe aucun module de `data_api.routers`, et `routers/__init__.py` est vide.** Décision
  de Sabine du 2026-10-18, sur la relecture du plan ; deux tests plutôt qu'un, et « vide »
  plutôt que « n'importe rien », tris de time-knight (une fonction fait une chose ; `code.md` dit
  « reste vide », et un `__init__.py` pourrait relier les routeurs sans import). Pourquoi :
  comme pour #247, le rangement crée la règle et un test la tient. Limite assumée (tri de
  time-knight) : aucun test ne vérifie que chaque module de `routers/` est inclus par
  `api_router` ; les tests de route d'un nouveau routeur verraient son oubli. — PR de #246

### Base : une porte d'écriture

- **`database/writing.py` est la seule porte de `src/k_b` vers `database/writers/`, hors de
  `database/`. Il tient la table `WRITER_BY_KIND`, `write_item` et `KindWithoutTableError`,
  déplacés sans changement d'`etl/load.py`, et réexporte par `__all__` les objets des écrivains
  que lisent `load.py`, `import_log.py` et `import_command.py`, jamais un module de `writers/`.**
  Décision de Sabine du 2026-10-18 (« writing maintenant »). Pourquoi, selon elle : c'est la base
  qui sait quel écrivain écrit quelle sorte, et l'import lui parle par une seule porte, comme
  `api_router.py` rassemble les routeurs (#246) et comme la ligne de commande est mince (#247). Le
  nom est celui des voisins (`reading.py`, `creation.py`, `connection.py`), gardé malgré
  l'homonyme `ai_api/stages/writing.py` (« pour la db on va garder les ing »). Restent dans
  `load.py` ce qui lit `etl` (`write_item_in_savepoint`, `register_raw_file`, les conditions de
  retrait), car `database` n'importe pas `etl` (`conventions.md`, règle 5). Options écartées : les
  noms `db_writer.py` (« db_ » redit le dossier) et `writer.py` (une lettre d'écart avec
  `writers/`) ; ne déplacer que la table (six modules de `writers/` restaient importés) ;
  `writers/__init__.py` comme porte (`code.md`, décision de #246) ; laisser `import_log.py` et
  `import_command.py` lire `writers/` (une règle à exceptions). Forme : `__all__`, car
  `mypy --strict` refuse alors tout autre nom importé de la porte. Formes écartées, essayées le
  2026-10-18 : l'import implicite (F401, mypy), `import x as x` (PLC0414), des affectations
  `y = writer.x` (l'interface dispersée). Limite assumée : `KindWithoutTableError.__module__`
  devient `k_b.database.writing`, et une trace montre le cadre de `writing.py`. — PR de #251
- **Quatre objets sont renommés à l'import : `write_trend_rows`, `TREND_DISCARD_RULE`,
  `mark_withdrawn_vulnerabilities_not_in` et `mark_withdrawn_zotero_rows_not_in`. Les fonctions
  des écrivains et de `load.py` gardent leur nom.** Décision de Sabine du 2026-10-18, sur le plan
  de la partie 2 (l'issue disait à tort qu'un seul nom changeait). Pourquoi : `write` et
  `DISCARD_RULE` ne disent plus rien hors de leur module, et les deux `withdraw_absent` ne peuvent
  pas coexister ; « mark » dit qu'il s'agit d'un `UPDATE` de `withdrawn_at` et non d'une
  suppression, « not_in » dit ce que reçoit la fonction (la liste des présents). Options écartées :
  `withdraw_…_not_in` et `…_not_listed` (« withdraw » laisse croire à une suppression),
  `withdraw_unlisted_…` (proposition de la session ; « unlisted » redit « absent »). Limite
  assumée : la porte et les écrivains portent deux noms pour une même fonction jusqu'au renommage
  partout, dans une petite issue à part juste après #251 (décision de Sabine du 2026-10-18,
  21:20Z). — PR de #251
- **La porte est tenue par des tests de `tests/test_module_dependencies.py` : hors de `database/`,
  aucun module n'atteint `database.writers` (`reaches` : `from k_b import database` est refusé), et
  l'API de données n'importe pas `database.writing`. La règle de l'API lit désormais ses interdits
  avec `reaches`, elle aussi : `from k_b import database` lui est refusé, alors que son cas de test
  le permettait.** Pourquoi : une règle créée par un rangement se tient par un test (entrée de
  #247), avec ses cas paramétrés ; et une seule façon de lire une interdiction (tri de la revue de
  code par time-knight, délégation de Sabine du 2026-10-15). Option écartée : un `grep` du critère
  de fin seul ; garder `is_within` pour l'API (le paquet `database` y donnait accès à la porte
  d'écriture sans que le test le voie). — PR de #251
- **Chaque `__init__.py` de `src/k_b` est vide, sans exception, tenu par un seul test,
  `test_every_package_of_k_b_has_an_empty_init`. Il remplace le test de `routers/__init__.py`
  (entrée de #246, « deux tests ») et celui des paquets d'`ai_api` qui n'importent rien
  d'`ai_api` (#242).** Décision de Sabine du 2026-10-18, groupée dans #251. Pourquoi : la règle de
  `code.md` vaut pour tous les paquets, ceux créés plus tard compris ; un fichier vide n'importe
  rien, donc le test unique est plus strict que les deux qu'il remplace. Inverse en partie la forme
  retenue à #246 (deux tests) : la garde de `app.py` reste, celle de `routers/__init__.py` passe dans
  la règle générale. Limite assumée : le test ne voit pas un dossier de modules sans
  `__init__.py`. — PR de #251

## 2026-10-19

### Brut : catalogues d'état et conservation

- **Trois couches : *raw*, la réponse des sources ; *cleansed*, l'immuable (la base, et les `.md`
  normalisés selon les sources) ; *curated*, les fiches de lecture, les fiches de veille, le
  wiki, les classements et les tendances. Le *curated* n'est jamais purgé automatiquement ; le
  *cleansed* est immuable.** Décision de Sabine, qui reprend son vocabulaire du 2026-10-12
  (*cleansed* et *curated*, « Wiki ») et le donne à toutes les données de K-B. Pourquoi : chaque
  couche a sa règle de conservation, et la purge ne touche que le *raw*. Réserve de Sabine :
  « petit bémol pour les vieilles veilles, à voir » (ci-dessous, « Décisions encore ouvertes »).
  — PR de #139 **Révisée le 2026-10-20**, règle et pourquoi : la purge touche aussi la veille du
  *cleansed*, au terme de sa durée, 3 ans ; « immuable » veut dire jamais réécrit ; `trend` sort du
  *curated* « jamais purgé » (« Squelette E1 E3 : cadrage du 20/10 », décision 5).
- **Zotero et CISA KEV sont des catalogues d'état : leur brut ne garde que le dernier fichier
  importé, le nouveau remplace le précédent.** Décision de Sabine. Pourquoi, celui de Sabine :
  « L'historique de versions n'a pas d'intérêt pour un catalogue d'état qui est indexé en bdd. On
  suit déjà les dates entre deux imports directement dans la bdd » (`revised_at`, `withdrawn_at`
  de `zotero_entry`, `highlight` et `vulnerability`). Pour Zotero, c'est la purge que demandait
  `conformite.md` pour une donnée personnelle (auteurs, surlignages, commentaires) ; pour CISA,
  sans donnée personnelle, la sobriété (RGESN 1.6). Garde-fous, recommandés par time-knight et
  validés par Sabine : le précédent n'est supprimé qu'une fois le nouveau importé ; un brut pas
  encore importé n'est jamais supprimé ; un extrait Zotero identique au dernier n'est pas écrit.
  Tranché dans le plan de #139 et validé par Sabine : « importé » veut dire enregistré dans
  `raw_data`, même avec un rejet, sinon une entrée invalide pour toujours bloquerait la purge
  pour toujours (cohérent avec « seule la collecte la plus récente compte », 2026-10-12) ; la
  liste des fichiers à supprimer vient de ce registre, jamais du dossier, et rien n'est supprimé
  si le dernier fichier importé manque ; la purge tourne à la fin de `kb import`, après le
  commit ; la comparaison d'un extrait Zotero au dernier porte sur son contenu, plus sur la date
  des fichiers de Zotero ; un extrait Zotero dont tous les documents sont invalides fait échouer
  la source à la collecte (règle 1 de `conventions.md`), sinon il deviendrait le dernier et ferait
  supprimer le dernier bon ; pour la même raison, un catalogue sans entrée, Zotero ou CISA, fait
  échouer la source (`empty_catalog`), règle que l'import tenait déjà en ne retirant rien pour
  lui (constat de `/code-review`, tri de time-knight, délégation de Sabine du 2026-10-15). Options écartées : une durée en années, ou les N derniers (un
  catalogue complet rend chaque fichier plus ancien inutile à la base) ; purger à la collecte
  (elle n'ouvre pas la base, donc ne sait pas ce qui est importé) ; « importé et sans rejet ».
  Limites assumées : une base reconstruite depuis le brut n'a que l'état du dernier catalogue,
  ni les lignes retirées avant lui ni les dates de révision passées ; une entrée valide autrefois
  et refusée dans le dernier extrait reste en base mais sort du brut ; un extrait illisible n'est
  jamais importé, donc jamais supprimé ; une bibliothèque vraiment vidée n'est plus collectée ;
  un extrait dont tous les documents passent la collecte mais sont refusés à l'import (par `Item`
  ou par un `CHECK`) fait quand même supprimer le précédent, la collecte ne pouvant valider ni
  l'un ni l'autre sans valeurs factices ; un item inchangé reste rattaché au fichier qui l'a écrit
  (`item.raw_data_id`), et `raw_data` garde le chemin d'un fichier supprimé : il dit ce qui a été
  importé et quand, plus que le fichier existe (**précisé le 2026-11-04** : tant qu'une ligne de
  la base le cite, ou s'il est le dernier catalogue importé, #83) ; un dossier renommé à la main
  (`cisa_kev_<suffixe>`) n'est pas purgé. **Révise** l'entrée CISA du 2026-10-07 (« l'historique
  des versions n'est pas en base, le brut le garde ») et la phrase du 2026-10-09 « c'est le brut
  qu'on sauvegarde » pour ces deux sources. Tranche la question ouverte du 2026-10-11, « Durée de
  conservation et purge des extraits Zotero ». — PR de #139
- **Le brut des clips (copies et recopies) n'est supprimé qu'une fois la base sauvegardée, au
  08/11, avec PostgreSQL et Alembic. Règle écrite au registre seulement, sans code au 25/10.**
  Décision de Sabine. Pourquoi, celui de Sabine : une sauvegarde native se migre par
  `alembic_version`, un export CSV non. K-B ne touche jamais au coffre (`clipping.py`) ;
  **révisé le même jour** : K-B ne touche jamais aux clips, `kb write-tops` écrit `veille/tops/`
  du coffre (« Coffre : organisation »). Sort la
  purge des copies de clips de #139, où l'avait mise la décision du 2026-10-17. Limite assumée :
  jusque-là, chaque version d'un clip reste dans le brut, sans durée. — PR de #139 **Précisée le
  2026-10-20** : la règle reste ; « au 08/11, avec PostgreSQL et Alembic » attend « La base au
  temps 3 » ; fréquence : à chaque sauvegarde de la base (« Squelette E1 E3 : cadrage du 20/10 »,
  décision 6). **Inversée le 2026-11-04** : le brut des clips est gardé 6 mois au plus, puis part
  dès que deux sauvegardes saines le couvrent (#83).

### Collecte : mise à jour des `.md` importés

- **Une seule règle pour tous les `.md` importés : si ce que la base garde du `.md` change
  (titre, texte, dates, tags), il est réécrit en base et `revised_at` prend la date K-B de la
  collecte qui voit le changement ; au même contenu (vrai doublon, ou fichier touché sans
  changement), il est écarté `already_seen`, comme avant.** Décision de Sabine. Pourquoi, celui
  de Sabine : « Ma décision du 17/10 concernait la création d'un vrai doublon. Là si le contenu
  du fichier a changé il faudrait un update. » Elle vaut pour `clipping`, la seule source de
  `.md` collectée, et plus tard pour `manual_notes` (le dossier de dépôt manuel du coffre, `.md`
  et PDF, nom proposé par Sabine), nommé ici sans code : pas d'abstraction pour une source qui
  n'existe pas encore. Les tags entrent dans la comparaison avec leur code (#260). Un champ que
  la base ne garde pas (`author`, `description`) ne déclenche rien. La provenance d'un `.md` en
  base se lit par `item.kind = 'clip'` et par `item.raw_data_id` → `raw_data.source_id` →
  `source.source_code = 'clipper'` ; `manual_notes` aura sa propre source et sa propre sorte.
  **S'accorde avec « le *cleansed* est immuable »** (« Brut : catalogues d'état et
  conservation », ci-dessus), selon la précision de Sabine : « les clips sont immuables en
  contenu mais le tag peut changer. Mes .md manuels sont potentiellement modifiables aussi en
  contenu. Ce que je ne fais que rarement. » Le *cleansed* n'est jamais purgé (**révisée le
  2026-10-20** : sauf la veille, purgée à 3 ans ; « Squelette E1 E3 : cadrage du 20/10 »,
  décision 5) ; le texte d'un
  clip est immuable par usage, Sabine ne le modifie pas ; ses tags peuvent changer ; un `.md`
  manuel peut changer, rarement. Un texte de clip changé quand même est pris par la même règle,
  sans seconde règle. **Révise** « Collecte : clips (suite) » du 2026-10-17 (la première version
  vue d'une URL était gardée, et la réécriture écartée « sans objet si les clips ne changent
  pas »). Suite prévue, sans code ici : la tâche du LLM après la mise à jour d'un `.md` reste à
  définir dans la partie wiki (#148). Limites assumées : deux fichiers du coffre de même URL et
  de contenu différent, dans une même collecte : le second dans l'ordre des noms de pages
  réécrit le premier (révise la limite du 2026-10-17, « le premier l'emporte ») ; un clip dont
  l'URL source change devient un nouveau clip, l'ancien reste en base (la clé reste l'URL) ; un
  nom effacé d'un clip en base revient si le clip du coffre est recopié (une édition, une
  étiquette du Finder), l'effacement touche donc aussi le coffre (registre des traitements,
  étape 5) ; un clip réécrit ne revient pas dans la liste filtrée par `since` (« quoi de neuf »),
  qui date un clip par `saved_at` (`created`), que la réécriture ne change pas, et l'API de
  données n'expose pas encore `clip.revised_at` (constats de `/code-review`, signalés sans
  correction ; la suite après la mise à jour d'un `.md` relève de #148). — PR de #259
- **La comparaison se fait en Python (lecture de la ligne gardée, puis `UPDATE clip`), et un
  fichier collecté avant la version gardée est écarté `no_newer_version`.** Tranché dans le plan
  de #259, validé par Sabine. Pourquoi : le SQL reste portable (règle 1 de `poc.md`) ; le
  `WHERE (…) IS NOT (…)` d'un upsert, comme Zotero, compare des lignes d'une façon propre à
  SQLite, PostgreSQL écrivant `IS DISTINCT FROM` ; l'item reste créé seulement si le clip est
  absent ; et #260 comparera un ensemble de tags lu dans une table de liaison, qu'un `WHERE`
  sur une ligne ne compare pas. La garde d'ordre empêche la base de revenir à une version plus
  ancienne (deux imports en même temps, un brut plus ancien importé après), comme pour les
  catalogues d'état et arXiv ; elle compare par « avant », pas par « avant ou en même temps »,
  pour que le second fichier d'une même collecte réécrive le premier. Elle se compare au brut
  le plus récent du contenu gardé : une copie au même contenu, écartée `already_seen`, déplace
  l'item sur son brut, sans quoi un fichier intermédiaire importé en retard réécrirait la base
  avec une version plus ancienne que cette copie (constat de `/code-review`, tri de time-knight,
  délégation de Sabine du 2026-10-15 ; option écartée : comparer à la collecte la plus récente
  de tous les bruts de l'URL, que `raw_data` ne relie pas à l'URL). `revised_at` est posé même
  quand le changement est vu dans la collecte qui a créé le clip : il dit la collecte qui a vu
  le changement. Une réécriture ne va pas au journal d'import : ce n'est pas un rejet, comme une
  révision Zotero. Options écartées : l'upsert `ON CONFLICT (url) DO UPDATE … WHERE` (forme à
  porter, tags hors de sa portée) ; aucune garde d'ordre (plus court, mais une régression
  silencieuse possible) ; un cas à part pour ne pas dater une réécriture dans la collecte de
  création (une branche de plus pour un cas limite). — PR de #259
- **Le schéma change (`clip.revised_at`) : la base du POC est recréée, sans migration.**
  Décision de Sabine, sur la question posée par la relecture du plan (recréer, ou ajouter la
  colonne à la main par un `ALTER TABLE` écrit dans la PR). Pourquoi, celui de Sabine : « je
  n'ai rien changé dans zotero. Et pour cisa on ne perdrait que des dates de retraits et encore
  c'est même pas sûr qu'il y en ait eu. Donc pas grave ». Coût accepté : depuis #139, le brut
  de Zotero et de CISA KEV ne garde que le dernier fichier ; la base recréée perd les
  `withdrawn_at`, les `revised_at` passés et les lignes retirées avant lui (limite de « Brut :
  catalogues d'état et conservation »). Option écartée : l'`ALTER TABLE` à la main, sans perte
  (la recommandation de la session). — PR de #259

### Collecte : tags des `.md` importés

- **Les tags d'un `.md` importé entrent en base : une table `tag` partagée, une ligne par tag, et
  une table de liaison `item_tag` (plusieurs-à-plusieurs : un `.md` a plusieurs tags, un tag sert
  à plusieurs `.md`).** Décision de Sabine, option (a). Pourquoi, celui de Sabine : les tags
  serviront au wiki pour regrouper les fiches par tag (#148), et la table partagée prépare leur
  partage entre les sources de `.md`. **Révise** pour les tags seulement « Collecte : clips
  (suite) » du 2026-10-17 (« ni `author`, ni `description`, ni `tags` n'entrent en base ») ;
  `author` et `description` restent hors de la base. Zotero garde ses étiquettes dans l'extrait
  (ADR du 2026-10-13) : rien ne change pour lui. Tranché dans le plan de #260 (validé par
  time-knight, délégation de la pause de Sabine) : la liaison pointe sur `item`, pas sur `clip`,
  pour que `manual_notes`, qui aura sa propre sorte d'item, la réutilise sans migration ; la
  provenance d'un `.md` se lit déjà par `item.kind` (« Collecte : mise à jour des `.md`
  importés »). Aucune ligne de code ne traite une autre sorte que le clip. Les liaisons d'un
  item partent avec lui (`ON DELETE CASCADE`), comme ses surlignages Zotero (décidé par
  time-knight, délégation de la pause de Sabine). Le registre des traitements dit la durée et
  l'effacement par nom (étapes 2 et 5). Options écartées : `clip_tag` (une table de
  liaison par sorte, à dupliquer pour `manual_notes`). — PR de #260
- **Les tags sont normalisés à l'import : sans espaces autour, sans le `#` d'Obsidian au début,
  en minuscules ; un tag vide une fois normalisé est ignoré ; le tag `clippings` du gabarit de
  Web Clipper est écarté.** Décision de Sabine. Pourquoi, celui de Sabine pour `clippings` : la
  sorte et la source distinguent déjà un clip (le gabarit le met sur chaque clip : 5 sur 5 dans
  le relevé de la spec de collecte). La normalisation est une seule fonction, `normalize_tag`
  (`items.py`), et le type `Tag` refuse un tag qu'elle changerait encore : la forme est tenue à
  un seul endroit (règle 4 de `conventions.md`), prête pour `manual_notes`. Un tag invalide (pas
  du texte, plus de 100 caractères, avec un NUL, ou `##llm`, qui garde un `#`) fait refuser le
  clip entier, par la voie de rejet des autres propriétés (décision de time-knight, délégation
  de Sabine ; règles 1 et 4 de `conventions.md`). Tranché dans le plan de #260 : `lower()` et
  non `casefold()` (la décision dit « en minuscules » ; `casefold` change aussi `ß` en `ss`) ;
  un seul `#` retiré (`removeprefix`), pas tous (`lstrip`), pour ne pas lire `##llm` comme
  `llm` sans décision ; la base ne tient que la longueur de `tag.name` (`CHECK`), car le
  `lower` de SQLite ne connaît que l'ASCII et celui de PostgreSQL tout Unicode ; 100 caractères
  au plus, borne large non mesurée (le coffre n'est pas lu) ; 30 tags au plus par item
  (`TAG_MAX_COUNT`, tenu par l'item seul) : la borne vient d'un constat du second `/code-review`
  (sans borne, un clip de 1 Mo fait de tags d'une lettre écrirait environ 750 000 requêtes dans
  un seul savepoint), que time-knight a fait corriger (délégation de Sabine du 2026-10-15), ce
  qui revient sur « le clip est déjà borné à 1 Mo » du plan ; sa valeur est de Sabine, 30 et non
  les 100 proposés : « un garde-fou de ressources, pas une règle de rangement » ; un tag en
  double est refusé par l'item, sinon la clé de
  `item_tag` le refuserait et arrêterait tout l'import. Options écartées : normaliser dans
  `normalize_item` (`etl/normalize.py`), car `clippings` est propre à Web Clipper et la
  normalisation doit précéder la validation par `Item` ; normaliser dans l'écrivain (la couche
  d'accès aux données ne transforme pas, règle 5). Limites assumées, hypothèses non vérifiées
  sur le coffre : `tags: llm, ai` donne un seul tag `llm, ai`, et `tags: "#ai #llm"` le seul tag
  `ai #llm` (une espace intérieure n'est pas lue comme un séparateur) ; un mot sous deux formes
  Unicode (NFC et NFD) donne deux tags. — PR de #260
- **Les tags d'un clip font partie de son contenu : un tag ajouté ou retiré date `revised_at` ;
  la liaison d'un tag retiré (`item_tag`) est supprimée, celle d'un tag ajouté écrite.**
  Décision de Sabine. Pourquoi, celui de Sabine : « Un tag supprimé
  n'existe plus en base. Je ne vois pas l'utilité qu'aurait le fait de le garder en revised
  at. » **Exception nommée à la règle 5 de `conventions.md`** (« ne supprime que par la purge »),
  le premier `DELETE` de `src/k_b` : une liaison est une valeur d'une version du clip, comme une
  colonne que l'`UPDATE` écrase, pas un item ; elle ne touche pas au « retiré, jamais supprimé »
  des entrées Zotero (2026-10-13), qui vaut pour des items. Les tags se comparent comme un
  ensemble, sans leur ordre : l'ordre d'un `ORDER BY` dépend de la collation, qui n'est pas la
  même en SQLite et en PostgreSQL. Option écartée : un `withdrawn_at` sur `item_tag` (une
  colonne et un filtre à chaque lecture, pour un historique des tags que rien ne demande).
  Limite : `.claude/rules/conventions.md`, que la session ne modifie pas, ne nomme pas encore
  cette exception. — PR de #260
- **Un tag dont la dernière liaison est retirée est supprimé, dans la même transaction que le
  `DELETE` de cette liaison (`DELETE FROM tag … WHERE NOT EXISTS (… item_tag …)`, SQL
  portable).** Décision de Sabine (« on le supprime »). Pourquoi, celui de Sabine : « Un tag
  supprimé n'existe plus en base. » **Seconde exception nommée à la règle 5 de
  `conventions.md`** (« ne supprime que par la purge ») : le tag n'est pas un item, et un tag que
  plus rien ne porte n'a ni usage ni durée (un tag peut nommer une personne : registre des
  traitements). Un tag laissé sans liaison par la suppression d'un item (`ON DELETE CASCADE`)
  reste, lui, jusqu'à la purge (#83), qui supprime les tags sans liaison. Option écartée :
  garder le tag sans durée jusqu'à la purge (proposé par time-knight, pour ne pas faire une
  seconde exception et ne pas effacer un tag que le LLM aura créé sans liaison). Limite connue :
  un tag créé un jour sans liaison, par le LLM (suite prévue), sera supprimé quand sa dernière
  liaison l'est, ou restera s'il n'en a jamais eu ; la règle est à revoir à la migration de la
  provenance des tags. — PR de #260
- **Un `.md` changé est écrit en *patch*, pas en *put* : seules les colonnes qui ont changé
  (titre, texte, dates) sont écrites, avec `revised_at` ; seules les liaisons des tags retirés
  sont supprimées et celles des tags ajoutés écrites ; les liaisons inchangées ne bougent
  pas.** Décision de Sabine. Pourquoi, celui de Sabine : « je veux le patch. C'est plus sobre et
  propre ». Révise l'écriture livrée par #259 (« Collecte : mise à jour des `.md` importés »),
  qui écrivait toutes les colonnes. Le `SET` de l'`UPDATE` ne nomme que les colonnes changées,
  prises dans les champs de `ClipContent`, jamais dans une valeur lue. Option écartée : le *put*
  (toutes les colonnes, et toutes les liaisons supprimées puis écrites de nouveau) : plus simple,
  mais il écrit le texte entier, jusqu'à 1 Mo, pour un tag changé. Ce que le *patch* épargne sur
  le disque, à vérifier sur la base : en PostgreSQL (08/11), un `UPDATE` laisse en place la
  valeur hors ligne d'une colonne qui ne change pas (documentation TOAST) ; en SQLite, ce n'est
  pas établi : SQLite n'écrit que les pages qui changent quand la cellule garde sa taille
  (journal des sources de SQLite, 2018), mais des essais du forum montrent la ligne entière
  réécrite dans d'autres cas, non mesuré ici. — PR de #260
- **Suite prévue, sans code ici.** Le wiki regroupe les fiches par tag (#148) ; le LLM aura la
  main sur les tags, « de façon frugale », pour en créer et les revoir, par l'API de données,
  après le 25/10 ; la provenance d'un tag (Sabine ou LLM) n'est pas modélisée : Sabine préfère
  « une migration quand on en sera au llm ». Décisions de Sabine du 2026-10-19. — PR de #260

### Base : nom de la liaison des tags

- **La table de liaison d'un item à ses tags s'appelle `item_has_tag`, son index
  `item_has_tag_tag_id` ; la base du POC est recréée, sans migration.** Décision de Sabine.
  Pourquoi, celui de Sabine : « je préfère garder item_has_tag en mld et mpd ». **Révise** le
  nom seul de « Collecte : tags des `.md` importés » (même jour, `item_tag`) ; l'entrée et la
  note pédagogique du jour gardent l'ancien nom, la note reçoit un addendum. Option écartée :
  garder `item_tag`, le nom livré par #260. Sans migration, comme pour `clip.revised_at`
  (#259) : aucune n'existe dans le dépôt avant Alembic (08/11). Coût accepté par Sabine : la
  base recréée perd ce que le brut ne garde plus (les `withdrawn_at`, les `revised_at` passés
  et les lignes retirées, limite de « Brut : catalogues d'état et conservation »). Limite : le
  MLD du dépôt n'a pas encore les tables de tags (#211). — PR de #263

### Collecte : méthode des tops GitHub

- **Les deux tops GitHub, plus étoilés et plus forkés, sont collectés au POC par la recherche de
  l'API REST (`GET /search/repositories`, `sort=stars` ou `sort=forks`), et non par l'API
  GraphQL ; le passage à GraphQL est porté par #269, sans jalon.** Décision de Sabine.
  **Révise** « Tops GitHub (P7, P8) » (2026-10-07) pour la méthode de collecte seule, et
  **inverse** l'option qu'elle écartait : l'API REST (82 champs par dépôt, sans choix des
  champs). Le reste de la décision tient : top du jour, hors base, un fichier par critère et par
  collecte ; elle était complète dès l'origine (`docs/2026-10-07-clarification-modele.md:294-297`).
  Pourquoi, celui de Sabine (arbitrage du 2026-10-19) : la date du 25/10. Aucun POST n'existe dans
  K-B (`etl/http_download.py` ne fait que des GET) et la migration vers httpx (#86) venait avant
  (remarque de Sabine du 2026-10-11). Les plus étoilés sont d'ailleurs en REST depuis le
  2026-10-02 (PR de #11) : un seul chemin de collecte pour les deux. L'argument de frugalité du
  2026-10-07 tient, mesuré le 2026-10-19 : JSON compact de chaque dépôt
  (`json.dumps(item, separators=(",", ":"))`) contre un objet des 4 champs de GraphQL
  (`nameWithOwner`, `description`, `stargazerCount`, `forkCount`) sérialisé de même. Sur
  `tests/fixtures/github_most_starred_extract.json` : 5 878 o contre 177 o par dépôt, 574 Kio
  contre 17 Kio pour un classement de 100, facteur 33,2 (5 880 et 178 dans #264 : arrondis). Sur
  le relevé réel des plus forkés (appel du 2026-10-19, 17:40:43Z) : 5 523 o contre 194 o,
  facteur 28,4. Conséquence : l'exception au brut intact de l'entrée du 2026-10-07 tombe jusqu'à
  #269, le brut des tops est la réponse REST entière. Option écartée : GraphQL au POC, qui
  demandait un client POST avant #86. Limite assumée : un brut environ 30 fois plus lourd que
  nécessaire jusqu'à #269 (RGESN 1.6). — PR de #264

### Coffre : organisation

- **À la racine du coffre (`KB_VAULT_DIR`) : `Clippings/` et le dossier des PDF, que Sabine
  remplit ; `wiki/`, le savoir *curated*, à elle jusqu'à #148 ; `veille/`, que K-B écrit : les
  fiches de veille par sujet (`veille/<sujet>/AAAA-MM-JJ.md`, #209) et les fiches des tops
  (`veille/tops/`). K-B lit `Clippings/` et écrit `veille/`, rien d'autre.** Décision de Sabine
  du 2026-10-17, jamais reportée jusqu'ici (compte rendu de time-knight du 2026-10-19), et sa
  variante du 2026-10-19 pour les tops : « tops fait partie de la veille, donc veille/tops pour les
  tops ». Ne réécrit pas l'entrée du 2026-09-29 (`wiki/veille/<question>/`) : elle la remplace
  pour le chemin des fiches de veille. Options écartées : `tops/` à la racine, frère de `veille/`
  (première version de l'arbitrage du 2026-10-19, révisée par Sabine) ; les tops sous
  `wiki/veille/` (une fiche de top ferait passer le critère de #210 sans fiche du LLM). `tops`
  devient un nom réservé sous `veille/` : aucun sujet de `DIGEST_SUBJECTS` ne peut le prendre,
  sinon ses fiches iraient dans le dossier des tops (test de `tests/etl/test_top_sheets.py`).
  **Révise** « K-B ne touche jamais au coffre » (« Brut : catalogues d'état et conservation »,
  même jour) : K-B ne touche jamais aux clips. — PR de #265

### Tops : les fiches par `kb write-tops`

- **Les fiches des deux tops sont écrites par une commande à part, `kb write-tops`, avec son
  propre code de sortie ; `kb import` ne lit pas `KB_VAULT_DIR` et ne touche pas au coffre. En
  dev, la chaîne se lance par `kb collect; kb import; kb write-tops`.** Décision de Sabine du
  2026-10-19 (18:45Z–19:00Z). Pourquoi, celui de Sabine : un pipeline d'étapes logiques qui
  s'enchaînent (collecte → import en base → création des fiches) ; en ligne, une automatisation
  les enchaînera, `kb import` ne sera pas lancé à la main ; la ligne du README reproduit en dev le
  fonctionnement de la prod, sans commande d'orchestration à coder. `;` plutôt que `&&` (choix de
  Sabine sur proposition de la session) : `kb collect` sort en 4 dès qu'une source échoue (arXiv
  au-delà de 2 000 papiers, « Problèmes connus » de `MEMORY.md`), et `kb write-tops` ne lit que
  le brut. **Révise** l'arbitrage C du même jour (la fiche à la fin de `kb import`, critère
  initial de #265, jamais écrit dans ce journal). Options écartées : la fiche en fin de
  `kb import` (deux rôles dans une commande) ; `&&` (une source en panne arrête les fiches). Une
  commande `kb write-notes` qui les regrouperait n'est pas à créer maintenant. Sans
  `KB_VAULT_DIR`, ou s'il n'est pas un dossier existant : code 2, rien n'est lu ni supprimé, aucun
  dossier créé (`write_file_atomically` créerait un faux coffre sur une faute de frappe) ; aucun
  relevé : code 0 (tranché par time-knight, délégation de Sabine du 2026-10-15). Point ouvert :
  où tourne `kb write-tops` en ligne, avec le coffre, d'ici le 08/11. — PR de #265
- **Une fiche par top et par jour de collecte encore présent dans le brut,
  `veille/tops/<most_starred|most_forked>/AAAA-MM-JJ.md`, nommée par le jour UTC du relevé ; une
  fiche qui existe n'est jamais réécrite. Une fois les fiches d'un top écrites, ses relevés
  lisibles antérieurs au dernier relevé lisible sont supprimés du brut.** Décision de Sabine
  (proposition (a) de la session, 2026-10-19). Pourquoi : « une fiche datée par top et par
  collecte » (décision 2 du 2026-10-19), alors que `kb collect` et `kb write-tops` ne tournent pas
  au même rythme ; « je valide le dernier json importé avec succès » (décision 4) : importé avec
  succès = sa fiche est écrite. Option écartée : la fiche du dernier relevé seul (la lettre du
  premier critère), qui supprimerait sans fiche les relevés des jours sans `kb write-tops`.
  **Tranche** la limite « durée de conservation des fichiers non décidée » de « Tops GitHub (P7,
  P8) » (2026-10-07) pour le brut : seul le dernier relevé lisible reste, avec ceux qui le
  suivent ; et **révise** son « sans historique » : les fiches gardent un top par jour. Chaque
  relevé listé est relu, sa fiche écrite ou non : un relevé illisible n'est jamais pris pour le
  dernier lisible (constat de la relecture du plan). Le dossier est lu une fois : un relevé écrit
  pendant la commande (brut partagé, #200) n'est ni lu ni supprimé. Limites assumées : deux
  collectes le même jour ne donnent qu'une fiche, celle du premier relevé de ce jour encore dans le
  brut, alors que le brut ne garde que le second (et `kb top`, #266, l'affichera) ; au premier
  lancement sur les vraies données, tout l'historique des relevés devient des fiches, puis ces
  relevés sont supprimés ; deux `kb write-tops` simultanés peuvent réécrire une fiche créée entre
  le contrôle et l'écriture (même contenu pour un même relevé). — PR de #265
- **Un relevé illisible (nom qui n'est pas une heure de collecte, JSON invalide, classement
  refusé) est gardé, jamais supprimé, journalisé sans le nom de son fichier, et `kb write-tops`
  sort en 1 tant qu'il est là.** Décision de Sabine (proposition (a), 2026-10-19). Pourquoi :
  échouer fermé, la fiche de son jour manque. Option écartée : le journaliser et sortir en 0.
  Limite assumée : un relevé illisible fait échouer chaque `kb write-tops` jusqu'à son retrait à
  la main, comme arXiv au-delà de 2 000 papiers ; c'est le cas si #269 change le lecteur sans
  reprendre les relevés REST. — PR de #265
- **La fiche est du Markdown déterministe, en français : un frontmatter (`classement`, `releve`,
  `depots`), puis un tableau par rang (dépôt en lien, étoiles ou forks, description). L'URL est
  construite depuis le nom, jamais lue dans `html_url` ; la description est neutralisée :
  contrôles, surrogates isolés et contrôles bidirectionnels remplacés par une espace, blancs
  réduits à une espace, `\`, `[`, `]`, `<`, `>`, `|`, l'accent grave, `#`, `%` et `$` échappés
  par une barre oblique inverse.** Décision
  de Sabine pour la description échappée (P4, 2026-10-19) ; la liste est celle du critère,
  complétée par la session (tranché par time-knight) : `#` (un tag Obsidian dans le coffre, alors
  que les tags d'une fiche sont réservés au LLM), `%` (un commentaire `%%` masque la suite), `$`
  (une formule), les surrogates (qui feraient échouer l'encodage UTF-8 de toute la commande) et
  les contrôles bidirectionnels (qui réordonnent l'affichage ; U+200D, qui joint les émojis, est
  gardé). Pourquoi : une description est un texte libre venu de GitHub, une donnée et jamais une
  syntaxe. Limites assumées : une URL nue reste cliquable dans Obsidian (lien vers une page
  publique ; la casser abîmerait le texte) ; `==`, `*`, `_` et `~` restent de la mise en forme ;
  un processus tué laisse un temporaire caché `.AAAA-MM-JJ.md.*.tmp` dans le coffre. — PR de #265
- **`kb write-tops` ne suit jamais un lien symbolique dans le coffre : si `veille/`, `veille/tops/`,
  `veille/tops/<top>/` ou la fiche d'un des relevés est un lien symbolique
  (`vault_link_refused`), si une fiche n'est pas un fichier régulier (`sheet_not_a_file` : un
  dossier, par exemple), ou si la fiche d'un relevé lu manque avant sa suppression
  (`sheet_missing`), il refuse ce top avant d'en écrire aucune fiche, journalise le refus avec
  son chemin dans le coffre, ne supprime aucun de ses relevés et sort en 1 ; l'autre top est
  traité.** Décision de Sabine du 2026-10-19, 22:04Z (relayée par time-knight). Pourquoi, celui de
  Sabine : c'est le dossier où `kb write-tops` écrit qui est en jeu ; une règle d'écriture, à part
  de celle de la lecture et de l'import. `sheet_not_a_file`, `sheet_missing` et les recontrôles sont tranchés par
  time-knight (délégation de Sabine du 2026-10-15), après les revues : une entrée prise pour une
  fiche écrite laisserait supprimer son relevé sans fiche. Le contrôle lit l'entrée elle-même
  (`lstat`, jamais sa cible) : les dossiers et la fiche de chaque relevé listé (son jour vient de
  son nom) avant de lire un relevé et d'écrire une fiche ; les dossiers et la fiche de nouveau
  avant chaque écriture ; les dossiers et les fiches des relevés lisibles une dernière fois avant
  la suppression, où chaque fiche doit être là (`sheet_missing` sinon : une fiche retirée depuis
  son écriture laisserait supprimer son relevé sans fiche). Options écartées : suivre le lien et l'écrire comme une limite (premier plan) ;
  écrire par descripteurs (`O_NOFOLLOW | O_DIRECTORY`), écarté par time-knight :
  `write_file_atomically` est partagée par tout le projet, et aucune limite de droits n'est à
  défendre. Limite assumée : une entrée remplacée par un lien entre un contrôle et l'écriture qui
  le suit serait encore suivie ; seul un processus qui a déjà le compte de l'utilisatrice peut
  exploiter cette course, et le contenu des fiches est public. — PR de #265

## 2026-10-20

### Squelette E1 E3 : cadrage du 20/10

Décisions de Sabine du 2026-10-20, relayées par time-knight. Elles portent sur sa proposition du
« squelette E1 E3 » : les tâches qui couvrent les livrables E1 et E3 par les usages de K-B. Cette
proposition est tirée de deux rapports en lecture seule sur K-B, l'un d'un *product owner*,
l'autre d'un architecte (deux sous-agents de time-knight). Les décisions 6 et 7 ont été prises le
même jour, au découpage du squelette en issues. Un pourquoi que ces sources ne donnent pas est
écrit « non consigné ». Ces décisions s'appliquent par #276 (procédure de tri, durées), #277
(contrat des fiches), #156 (clé), #162 et #163 (métriques) et #210 (essais).

- **1. K-B tourne en trois temps. D'abord sur le Mac, en environnement de développement, sans
  conteneur : retour en CLI, fiches en `.md`. Puis en conteneurs en local, pour répéter le
  déploiement (préproduction), « avant le 29/10 si le temps le permet ». Enfin sur Azure
  Container Apps (ACA), au 08/11. Ce qui est construit au premier temps passe aux suivants sans
  refonte.** Décision de Sabine. Pourquoi de Sabine : non consigné ; elle dit que « le premier
  temps passe d'abord ». Argument de la proposition : les conteneurs (#200, #202) ne remplissent
  aucun critère encore vide d'E1 ou d'E3 ; selon le rapport du *product owner*, ils viennent de la
  contrainte de déploiement, pas des critères. Option écartée : un POC en conteneurs dès le 25/10
  (« POC du 25/10 », décision 1). **Révise**, pour le premier temps, l'option que cette décision
  écartait : « tout faire tourner sur le Mac, sans conteneurs (on ne répète pas la cible) ». La
  répétition de la cible passe au deuxième temps. — PR de #275
- **2. Le LLM juge sort du contrat des fiches de veille.** Décision de Sabine : « on voit plus
  tard ». Pourquoi, selon la proposition : une spécification qui dit ce que fait le produit.
  Option écartée : garder le juge dans le contrat sans le coder. Le rapport du *product owner* y
  relève une contradiction : la spécification décrit un parcours, une réponse et des métriques que
  le produit n'a pas. #223 (le juge codé) et #224 (son étalonnage) restent ouvertes, hors du
  squelette. Conséquence : le manque que le juge devait combler revient, puisque la fidélité ne
  vérifie pas le sens d'une phrase (« Fiches de veille : le LLM juge »). **Révise** « Fiches de
  veille : le LLM juge » (2026-10-16) et « Fiches de veille : le contrat du LLM juge »
  (2026-10-17). #277 aligne `docs/fiches-veille.md`. — PR de #275
- **3. La clé de l'API IA reste fixe. Sa rotation est documentée, avec ce que fait `kb digest` sur
  un 401 (dans #156). Le renouvellement de l'accès (#160) reste hors de ce travail.** Décision de
  Sabine, sur la recommandation de la proposition. Pourquoi, selon la proposition : pour une seule
  utilisatrice, des jetons qui expirent seraient une greffe ; le critère de la certification dit
  « éventuelles » ; la décision 7 du 15/10 garde déjà les clés fixes au 29/10. Option écartée :
  #160 (jetons qui expirent, taille M) dans le squelette. Remarque de Sabine : une interface web
  en ligne demandera probablement un login, avec des jetons qui expirent, où le renouvellement
  deviendrait naturel ; à voir plus tard. **Précise** « POC du 25/10 », décision 7. — PR de #275
- **4. Les métriques du modèle partent en OpenTelemetry vers Grafana Cloud, en région UE, dès le
  premier temps. Le bac à sable est une pile dédiée, ou un label d'environnement. Au troisième
  temps, seuls l'URL et le jeton changent. La ligne JSON par appel sur la sortie standard reste.**
  Décision de Sabine : l'option M3 du rapport de l'architecte, et non Azure Monitor. Pourquoi
  Grafana Cloud plutôt qu'Azure Monitor (décision de Sabine du 2026-10-20) : « Pourquoi : à
  établir par la comparaison de #163, qui fonde ce choix (critères 26 et 28 de la revue
  certif). » Cette comparaison suit les critères de « Wiki : métriques » (temps réel, alerte sur
  seuil, accessibilité, région UE, coût). Selon le rapport de l'architecte, l'option rend la
  surveillance du modèle démontrable dès le premier temps, sans attendre la mise en ligne. Options
  écartées, avec les propriétés relevées par l'architecte :
  - Azure Monitor (Application Insights) par OpenTelemetry (M4), recommandé par l'architecte :
    démontrable dès le premier temps, sans outil de plus au troisième ; raison du rejet non
    consignée ;
  - la sortie standard envoyée par ACA vers Log Analytics, avec un classeur et une alerte (M1,
    recommandé par le *product owner*) : rien de visible avant le troisième temps ;
  - Grafana et Loki en local, par compose (M2) : démontrable au deuxième temps seulement, puis un
    second outil au troisième, ou des tableaux réécrits de LogQL en KQL.

  Limites assumées : un tiers de plus (rapport de l'architecte) ; Grafana Labs devient un
  sous-traitant, dont le DPA est lu, et qui est inscrit au registre, avant le premier envoi
  (critère de #162). **Clôt** l'outil « à choisir » de « Wiki : métriques » (2026-10-12), où
  Grafana Cloud était candidat. Ne révise pas la ligne JSON sur stdout (« POC du 25/10 »,
  décision 8). **Précisée le 2026-11-08** : la comparaison de #163 est écrite
  (`docs/outils-de-suivi.md`) ; Grafana Cloud seul pour le rendu du 25/11, Application Insights
  repris après (« Outils de suivi : la comparaison de #163 », 2026-11-08). — PR de #275
- **5. La veille collectée en base est purgée au terme de sa durée. « Immuable » veut dire jamais
  réécrit, pas gardé pour toujours. Les fiches déjà écrites dans le coffre ne sont pas touchées.
  La durée passe de 2 à 3 ans pour les items de veille, le brut de veille (`raw/automated_watch/`)
  et les tendances (`trend`).** **Inversée le 2026-11-04 pour le brut, gardé 6 mois au plus
  (#83).** Décision de Sabine. Pourquoi, selon la proposition : rendre
  cohérentes les étapes 2 (purge des items de veille) et 9 (« le *cleansed* est immuable ») de la
  procédure de tri du registre. Pourquoi 3 ans plutôt que 2 (décision de Sabine du 2026-10-20) :
  « Je ne prévois pas d'interroger la base sur des sujets de plus de 3 ans. Une durée plus courte
  n'a pas été écartée par un fait : elle sera revue quand l'usage réel de la base sera mesuré. »
  Pourquoi purger plutôt que garder la veille sans limite (décision de Sabine du 2026-10-20) :
  « La veille est reprise dans des fiches de veille, que je garde : elle n'est donc pas perdue
  quand la base est purgée. La veille vaut par sa fraîcheur : la base n'a pas à garder ses
  entrées les plus anciennes. » Options écartées : garder la veille sans limite, en lisant
  « immuable » comme « gardé pour toujours » ; 2 ans, la durée provisoire du 2026-10-10.
  L'application (`RETENTION_YEARS_BY_ACQUISITION_MODE` de `core/config.py`, le registre, les
  étapes 2, 3 et 9) est portée par #276 ; la purge n'est pas codée (#83). **Clôt** « Conservation
  des vieilles veilles » (2026-10-19) et, pour la veille, « Durées de conservation et fréquence de
  la purge ». **Révise** « Brut : catalogues d'état et conservation » (2026-10-19), sa règle et son
  pourquoi (« la purge ne touche que le *raw* ») : la veille du *cleansed* est purgée, et `trend`
  sort du *curated* « jamais purgé ». — PR de #275
- **6. L'étape 8 de la procédure de tri (suppression du brut des clips) reste rattachée à la
  base : elle attend « La base au temps 3 » (question ouverte, plus bas). Sa règle du 2026-10-19 ne
  change pas : le brut des clips n'est supprimé qu'une fois la base sauvegardée. Sa fréquence : à
  chaque sauvegarde de la base.** **Inversée le 2026-11-04** : le brut des clips suit la règle
  des 6 mois (#83). Décision de Sabine, prise au découpage. Pourquoi (décision de
  Sabine du 2026-10-20) : « la base sera certainement PostgreSQL, avec Alembic pour les
  migrations. On est en développement : le plan reste de supprimer le brut des clips quand une
  sauvegarde de la base sera fonctionnelle. » « La base au temps 3 » reste pourtant ouverte :
  Sabine la tranchera le moment venu. Options écartées :
  - des migrations Alembic sur SQLite : elles réviseraient le 2026-10-15, où les migrations sont à
    reprendre pour PostgreSQL seulement ;
  - une copie native de la base, sans migration : elle réviserait la raison du 2026-10-19 (« une
    sauvegarde native se migre par `alembic_version`, un export CSV non »).

  **Précise** « Brut : catalogues d'état et conservation » (2026-10-19) : « au 08/11, avec
  PostgreSQL et Alembic » attend la décision sur la base. Le registre est mis à jour par #276.
  — PR de #275
- **7. #210 garde trois essais sur gpt-6-luna, avec `reasoning_effort: "none"`, sur la veille
  réelle. La comparaison de configurations validée le 2026-10-15 en sort : `none` contre `low`,
  stabilité sur 5 passages, 50 items étiquetés par Sabine, règle de décision. Ses seuils restent
  une grille de lecture : 100 % de schémas valides après une nouvelle tentative, au moins 95 % de
  fidélité, aucun item oublié.** Décision de Sabine, prise au découpage. Option écartée : garder
  la comparaison (l'issue passait à la taille M, plus l'étiquetage des 50 items par Sabine).
  **Révise** la comparaison validée par Sabine le 2026-10-15, consignée dans un commentaire de
  #210 et non dans ce journal. — PR de #275

## 2026-10-21

### Tests : un test de bout en bout par source, hors de la CI

- **Un test de bout en bout par source, marqué `e2e`, lance `kb create-db`,
  `KB_COLLECT_ONLY=<source> kb collect` puis `kb import` sur la vraie source dans un
  `KB_DATA_DIR` neuf, et vérifie les codes de sortie et ce qui arrive en base. `uv run pytest`,
  la commande de la CI, les écarte ; `uv run pytest -m e2e` les lance.** Décision de Sabine du
  2026-10-21, relayée par time-knight : un ajout au critère de #25. Pourquoi : les rejouer à
  l'identique au deuxième temps (`docker compose run kb uv run pytest -m e2e`) et au troisième
  (un job ACA). Hors de la CI parce qu'ils appellent les vraies sources : réseau, clés, et une
  requête BigQuery réelle pour `gh_archive`. La forme a été tranchée au plan de #25, validé par
  Sabine, puis aux revues, par time-knight (délégation de Sabine du 15/10) :
  - un seul test, paramétré par les dossiers de `SOURCE_KINDS`, plutôt qu'un test écrit à la
    main par source, qui ferait dix copies du même déroulé ;
  - l'exclusion se fait dans `tests/conftest.py` (`pytest_collection_modifyitems`), et non par
    `addopts = "-m 'not e2e'"` dans `pyproject.toml`, modification que Sabine aurait dû taper
    elle-même sans rien y gagner ;
  - l'interface `-m e2e` est gardée, plutôt qu'une option `--run-e2e`, qui aurait changé la
    commande décidée ;
  - le nom `e2e` est cherché dans l'expression `-m` par la règle `ident` de la grammaire de
    pytest, et non par l'API `Expression` de pytest, privée et changée en 8.x ;
  - une source dont la variable manque (Zotero, coffre, clé BigQuery) est sautée, plutôt qu'en
    échec : en conteneur, Zotero et les clips restent sur le Mac.

  Limites assumées :
  - le test dépend de la disponibilité de la source réelle : un rouge se lit d'abord dans le
    journal, avant d'être pris pour un défaut de K-B ;
  - chaque `kb` reçoit tout l'environnement du terminal (`uv run --env-file .env`), clés Azure
    comprises, comme dans un usage ordinaire de `kb` ;
  - ce qu'un test garde (sa console et `logs/`) est à l'étape 10 de la procédure de tri du
    registre. — PR de #25

### Tests : les tests de bout en bout ne reçoivent que leurs variables, et rendent un rapport HTML

- **Les tests de bout en bout se lancent par
  `uv run --env-file .env.e2e_test pytest -m e2e -rs --html=reports/e2e-report.html --self-contained-html` :
  `.env.e2e_test` ne porte que leurs variables (jeton GitHub, dossier Zotero, coffre, clé
  BigQuery ; modèle suivi par git, `.env.e2e_test.example`), et `pytest-html`, en dépendance de
  développement, écrit un rapport où chaque test inscrit ses chiffres par `record_property`.**
  Met à jour une limite assumée de l'entrée précédente (« chaque `kb` reçoit tout
  l'environnement du terminal, clés Azure comprises ») : moindre privilège, demandé par
  l'utilisatrice le 2026-10-21 juste après #25. Le rapport, parce que le compte rendu de #25 a été
  recopié à la main depuis la console ; il donne les résultats, l'interprétation reste écrite à la
  main. Décisions de l'utilisatrice du 2026-10-21 (outil, fixture, nom du fichier), puis au plan de
  #290, relayé par time-knight :
  - un garde-fou arrête les tests avant tout `kb` si une variable de `.env.example`, absente de
    `.env.e2e_test.example`, est dans l'environnement : uv ajoute `--env-file` à l'environnement
    du terminal, qui prime, et un `.env` exporté donnerait encore toutes les clés à chaque `kb`.
    Il compare des noms, jamais des valeurs : ceux de `.env.example`, lignes commentées comprises
    (une clé y est commentée), moins ceux que `.env.e2e_test.example` pose (un nom qu'il commente
    n'est pas aux tests) ;
  - il laisse passer les noms que le test pose lui-même (`KB_DATA_DIR`, `KB_COLLECT_ONLY`) ou que
    `tests/conftest.py` retire avant lui (`KB_LOG_TO_FILE`, `KB_DATA_API_HOST`, `KB_DATA_API_PORT`,
    `KB_DATA_API_ALLOWED_HOSTS`) : leur valeur
    n'atteint jamais `kb`, et en conteneur ou en job ACA, où `KB_DATA_DIR` et `KB_LOG_TO_FILE`
    sont posés, le critère à la lettre aurait tout arrêté. Écart au critère de #290, décidé par
    l'utilisatrice (option écartée : le critère à la lettre, qui aurait cassé le rejeu à
    l'identique en conteneur) ;
  - le rapport va dans `reports/`, ignoré par git, en `0600` (dossier créé en `0700` s'il est
    neuf), un seul fichier écrasé à chaque production : il garde la sortie capturée des tests.
    Un rapport demandé ailleurs dans le dépôt arrête pytest avant tout fichier (le dépôt devient
    public le 25/10). Écartés : ignorer `reports/` à toute profondeur, qui ne couvre ni un
    rapport hors d'un dossier `reports/` ni un fichier suivi écrasé, et ignorerait sans bruit un
    futur dossier de code nommé ainsi ; `temp/`, le dossier de données des essais de
    l'utilisatrice ; un dossier hors du dépôt (`$TMPDIR`), dont la durée de conservation n'est
    pas vérifiable ;
  - `pytest-html` n'affiche pas `user_properties` : une colonne s'ajoute par ses hooks, dans
    `tests/conftest.py`, chaque valeur échappée.

  Limites assumées :
  - lancer depuis un terminal sans `.env` exporté reste une consigne : le garde-fou ne connaît que
    les noms de `.env.example`, et la famille `KB_API_KEY_<CLIENT>` par son préfixe (la seule que
    `kb` lit par préfixe) ; une variable d'un autre outil (une clé exportée par un autre projet)
    passe ;
  - si `.env.example` ou `.env.e2e_test.example` manque (une image qui ne les copie pas, #200),
    les tests échouent ;
  - `KB_DATA_API_URL`, réglage de l'API IA, n'est ni posé ni retiré par le test : présent dans
    l'environnement (un conteneur qui le pose, #200), il arrête les tests ;
  - `uv.lock` gagne trois dépendances de `pytest-html` (`pytest-metadata`, `jinja2`,
    `markupsafe`), en développement seulement, acceptées par l'utilisatrice. — PR de #290

### API IA : servir les fiches par `POST /digests`

Décisions de Sabine du 2026-10-21 sur #156, relayées par time-knight : le plan relu par un
sous-agent et validé (14:33Z), puis les décisions prises pendant le travail. Tri des revues par
time-knight (délégation de Sabine du 2026-10-15).

- **Ce qui est commun aux deux API vit une fois dans `core/` : la clé lue au démarrage
  (`api_keys.py`, le préfixe en paramètre) et vérifiée à chaque requête (`api_access.py`), les
  erreurs et leurs gestionnaires (`api_errors.py`), le journal des requêtes (`api_request_log.py`),
  la santé (`api_health.py`), la règle de l'hôte et du port (`api_settings.py`). `data_api/` ne
  garde que ce que sa base donne (`database_missing`, `database_error`) et ses hôtes permis.**
  Pourquoi : critère de #156 (« sans être recopiés ») ; l'API IA ne peut importer que `ai_api`,
  `items` et `core`. La vérification est à part de la lecture, pour que la lecture de
  l'environnement n'importe pas FastAPI (relecture du plan). Options écartées : un module
  `core/api_app.py` qui câblerait l'app commune (deuxième occurrence ; l'ordre des middlewares
  diffère, `TrustedHostMiddleware` de l'API de données passant sous le journal) ; recopier dans
  `ai_api/`. Limite assumée : le nom de journal des lignes de requête devient
  `k_b.core.api_request_log`, au lieu de `k_b.data_api.request_log`. **Révise** 2026-10-14,
  « API de données », entrée « Paquet `src/k_b/data_api/` » : `request_log.py` et `health.py`
  quittent le paquet, et `dependencies.py` n'y porte plus la clé. **Révise** 2026-10-18, « API IA :
  organisation par rôle » : la racine d'`ai_api` ne reçoit ni `health.py` ni `request_log.py`,
  qui sont dans `core/`, mais `settings.py` et `metrics.py` (les lignes `llm_call`). — PR de #156
- **Chaque requête des deux API reçoit un identifiant (UUID) du journal commun, écrit dans chacune
  de ses lignes de journal et renvoyé dans l'en-tête `X-Request-ID` ; l'API IA le rend aussi dans
  sa réponse 200 et dans ses lignes de métrique.** Pourquoi, celui du plan validé : un outil commun
  ne connaît pas de cas particulier (`code.md`), et l'en-tête relie un 502 à ses lignes `llm_call`
  sans changer le corps `{"error": …}` (réserve du relecteur du plan). Options écartées : un
  identifiant de l'API IA seule ; un identifiant dans le corps d'une erreur. L'API de données passe
  en 0.5.0 (seconde revue de code). — PR de #156
- **L'API IA est servie par `kb serve-ai`, réglée par `KB_AI_API_HOST` (`127.0.0.1`),
  `KB_AI_API_PORT` (`8001`) et `KB_DIGEST_WINDOW_DAYS` (3, de 1 à 14), avec son propre fichier de
  journal, `logs/kb-serve-ai.log` ; ses clients ont leur clé dans `KB_AI_API_KEY_<CLIENT>`
  (`kb digest` est le client `KB_DIGEST`).** Pourquoi, celui du plan validé : un processus long a
  son fichier, pour la même raison que `kb serve` (2026-10-14, « Journaux »).
  Options écartées : `kb serve-ia`, `kb serve --ai`. Limite assumée : un seul `kb serve-ai` par
  `KB_DATA_DIR`. **Révise** 2026-10-14, « Journaux » : `kb serve` n'est plus le seul processus long.
  — PR de #156
- **Pas de `TrustedHostMiddleware` sur l'API IA.** Pourquoi (relecteur du plan, accepté par
  Sabine) : sans clé, une requête n'atteint que `/health`, `/docs` et `/openapi.json`, qui ne
  contiennent aucune donnée ; un rebinding DNS n'obtient rien et ne coûte aucun appel. Écart voulu
  à la ligne API8 de `docs/specs-api.md`. Option écartée : `KB_AI_API_ALLOWED_HOSTS`. Limite
  assumée : à revoir par #161 (OWASP API Top 10 de l'API IA) et en conteneurs (#200), où l'hôte
  appelant change. — PR de #156
- **Chaque `APIRouter` de `routers/`, dans les deux API, déclare son `prefix` et ses `tags`
  (`/digests`, `/items`, `/trends`), la route n'écrivant que la fin de son chemin ; un test
  d'architecture tient la règle.** Pourquoi, celui de Sabine : suivre la doc FastAPI (skill
  `fastapi`, `references/path-operations.md`) et le critère du 17/10 sur #156 ; les tags regroupent
  les routes dans `/docs` et l'OpenAPI. Option écartée : le chemin entier dans le décorateur, sans
  `prefix`, la forme de l'API de données jusque-là, recommandée un temps par time-knight pour
  n'avoir qu'une règle. Les adresses ne changent pas. — PR de #156
- **Les clés de l'API de données s'appellent `KB_DATA_API_KEY_<CLIENT>`, en face de
  `KB_AI_API_KEY_<CLIENT>` ; la constante `API_KEY_VARIABLE_PREFIX` garde son nom ; la clé que
  l'API IA envoie devient `KB_DATA_API_KEY_AI_DIGEST`.** Pourquoi, celui de Sabine : tous les
  réglages de l'API de données s'écrivent déjà `KB_DATA_API_*`, et `KB_API_KEY_AI_DIGEST` se
  lisait comme une clé de l'API IA. Option écartée : garder `KB_API_KEY_`. Limite assumée : après
  la fusion, `kb serve` ne trouve plus une clé sous l'ancien nom (il refuse de démarrer, « no API
  key ») : l'utilisatrice renomme ses variables. **Révise** 2026-10-21, « Tests : les tests de bout
  en bout ne reçoivent que leurs variables… », limite « la famille `KB_API_KEY_<CLIENT>` … la
  seule que `kb` lit par préfixe » : la famille s'appelle `KB_DATA_API_KEY_<CLIENT>`, et
  `KB_AI_API_KEY_<CLIENT>` est une seconde famille lue par préfixe, que le garde-fou ne connaît
  pas encore (signalé à la piste A). — PR de #156
- **`kb serve-ai` lit les réglages du modèle et de l'API de données par
  `read_llm_settings_or_refusal` et `read_data_api_settings_or_refusal`, et journalise un refus par
  `value_or_log_refusal`, sous `k_b.cli`, comme `kb serve` ; les enveloppes `read_llm_settings` et
  `read_data_api_settings` sont retirées.** Pourquoi : la porte journalise le refus (2026-10-18,
  « Ligne de commande : une porte mince ») ; plus de copie du motif (commentaire du 18/10 sur #156).
  Option écartée : faire rejoindre `core/` à `value_or_log_refusal`, qui n'a plus qu'un appelant,
  `commands/`. **Révise** 2026-10-18, « Ligne de commande : une porte mince », limite « la fonction
  rejoindra `core/` avec elles » : les copies sont retirées et la fonction reste dans `commands/`.
  — PR de #156
- **`kb serve-ai` refuse de démarrer (code 2) si une clé de ses clients est celle qu'il envoie à
  l'API de données ; il ne la compare qu'à `KB_DATA_API_KEY_AI_DIGEST`.** Pourquoi : l'API de
  données donne tout à chaque client, et partager cette clé ouvrirait la base au client de l'IA
  (première revue de code). Comparer aussi aux autres clés de l'API de données est écarté par
  Sabine : sur le Mac, `kb digest` lit déjà tout l'environnement, et toutes les clés de l'API de
  données ont les mêmes droits. Limite assumée : en conteneurs et sur ACA, une clé distincte par
  service, chacun ne recevant que les siennes (signalé). — PR de #156

### Fiches de veille : `kb digest` les écrit dans le coffre

Décisions de Sabine du 2026-10-21 sur #209, relayées par time-knight (plan v2, relu par un
sous-agent, validé à 18:03Z), et choix de la session acceptés par time-knight (délégation de
Sabine du 2026-10-15).

- **`kb digest` demande les fiches à `POST /digests` par HTTP, avec la clé
  `KB_AI_API_KEY_KB_DIGEST` et l'adresse `KB_AI_API_URL` (défaut `http://127.0.0.1:8001`, nommé
  dans `core/config.py`), puis écrit une fiche par sujet rendu, `veille/<sujet>/AAAA-MM-JJ.md`, au
  jour UTC de `window.until`. Le client est `etl/ai_api_client.py`, la fiche
  `etl/digest_sheets.py`, la porte `commands/digest_command.py`.** Choix de la session dans le
  plan validé. Pourquoi : seul `kb` écrit le coffre (règle 7 de `poc.md`) ; `etl` est la couche du
  métier, sous les commandes, et n'importe pas `ai_api` (règle 5 de `conventions.md`) : l'API IA
  est jointe par son contrat, comme un service extérieur. Options écartées : un paquet nouveau pour
  le client, au-dessus d'`ai_api` ; une demande avec `window_days` (la fenêtre reste un réglage de
  `kb serve-ai`, `KB_DIGEST_WINDOW_DAYS`). Partie commune avec `kb ingest` (#159) : `core/outbound.py`,
  la lecture « URL et clé d'un client » et les états `ai_api_*` ; aucun client générique n'est
  écrit d'avance. — PR de #209
- **La réponse 200 de `POST /digests` donne `model`, le modèle des réglages de `kb serve-ai`
  (`replay` pour le replay) ; l'API IA passe en 0.2.0. `MODEL_NAME` passe de
  `ai_api/connectors/llm_settings.py` à `core/config.py`.** Décision de Sabine (décision 1).
  Pourquoi : le critère de #209 met le modèle dans le frontmatter de la fiche, et la réponse ne le
  donnait pas ; `kb digest` relit le modèle reçu par le même motif avant de l'écrire. Options
  écartées : `kb digest` lit `KB_LLM_MODEL` (le réglage d'un autre processus, qui peut différer) ;
  une fiche sans modèle (contre le critère). — PR de #209
- **Une clé refusée par l'API IA (401) fait sortir `kb digest` en 1 ; une clé absente ou hors
  règle, en 2. Le sens de 2 ne change pas. Le message nomme `KB_AI_API_KEY_KB_DIGEST`, jamais la
  clé.** Décision de Sabine (décision 2). Pourquoi, celui de Sabine : une clé absente, `kb` refuse
  avant de lancer ; une clé refusée par le service appelé, la requête est partie. C'est la règle de
  `kb collect`, où une source qui rend 401 échoue (`etl/extract.py:45`), et celle d'autres outils :
  l'AWS CLI sort en 253 sur une configuration ou des identifiants absents, en 254 quand le service
  a répondu par une erreur ([return codes](https://github.com/aws/aws-cli/blob/v2/awscli/topics/return-codes.rst)) ;
  `gh auth status` sort en 1 sur un jeton refusé ([manuel](https://cli.github.com/manual/gh_auth_status)),
  consultés le 2026-10-21 par time-knight. Options écartées : 2 avec un sens élargi (proposition de
  la session : le remède est celui d'une clé absente) ; un code dédié à l'authentification (le 4
  de `gh`, [exit codes](https://cli.github.com/manual/gh_help_exit-codes)), à reconsidérer pour
  toutes les commandes avec #160 (jetons qui expirent). — PR de #209
- **Même résultat, même code : une commande faite de parties sort en 4 quand une partie a échoué
  et qu'une autre est faite et gardée, en 1 quand aucune ne l'est. La partie est la source pour
  `kb collect`, le top pour `kb write-tops`, le sujet pour `kb digest` ; `find_exit_code`
  (`commands/exit_codes.py`) tient la règle pour les trois.** Règle de Sabine (décision 2 bis).
  Pour `kb digest` : un sujet en échec (dans `failed_subjects`, ou sa fiche non écrite) et une
  fiche écrite, 4 ; aucune fiche écrite, 1. Pour `kb write-tops` : un top échoue s'il est arrêté
  (`OSError`, entrée refusée du coffre) ou garde un relevé illisible ; il aboutit s'il va au bout
  et écrit une fiche, ou va au bout sans échec, un top sans relevé compris (choix de la session,
  accepté par time-knight : comme une source sans rien de neuf pour `kb collect`). Un relevé
  illisible quand des fiches sont écrites sort en 4 : « échouer fermé » (2026-10-19) tient, car 4
  n'est pas 0. Options écartées : `kb write-tops` dans une issue à part ; 1 pour l'échec partiel de
  `kb digest` (proposition de la session). **Révise** 2026-10-18, « Codes de sortie de kb » :
  « Le code d'échec partiel (4) vaut pour `kb collect` seul ». **Révise** 2026-10-19, « Tops : les
  fiches par `kb write-tops` » : un relevé illisible, ou un top refusé quand l'autre aboutit, sort
  en 4 et non plus en 1. — PR de #209
- **Les règles d'une connexion sortante (`find_url_refusal`, `open_http_client` : URL jamais
  citée, ni proxy ni certificat de l'environnement, aucune redirection suivie) passent
  d'`ai_api/connectors/outbound.py` à `core/outbound.py`, que l'API IA et `kb digest` importent ;
  un test tient qu'`etl` n'importe ni `data_api` ni `ai_api`.** Décision de Sabine (décision 3).
  Pourquoi : `etl` n'importe pas `ai_api`, et une règle de sécurité ne se recopie pas (même motif
  qu'en #204). Options écartées : un paquet `outbound/` à côté de `core/` ; une copie dans `etl`,
  même temporaire (contraire à #204). **Révise** 2026-10-15, « Fiches de veille : la lecture par
  l'API de données » : ces règles ne vivent plus « dans `ai_api/outbound.py` ». **Révise**
  2026-10-18, « API IA : organisation par rôle » : `connectors/` ne contient plus `outbound.py`,
  et la deuxième couche d'`ai_api` n'a plus que `llm_replay`. Signalé, pas fait ici : renommer
  `core/` en `common/` après le POC, dans une issue seule (décision de Sabine ; `core/outbound.py`
  suivra le dossier) ; deux modules de connexions sortantes, `etl/http_download.py` (urllib, la
  collecte) et `core/outbound.py` (httpx2), à harmoniser après le POC. — PR de #209
- **L'écriture sûre d'une fiche dans le coffre vit une fois, dans `etl/vault_files.py`, pour les
  fiches des tops et les fiches de veille : `write_new_sheet` (dossiers recontrôlés, aucun lien vu
  suivi, aucune fiche vue réécrite, temporaire caché renommé) et `neutralize_text`, qui reçoit les
  caractères à échapper.** Choix de la session dans le plan validé. Pourquoi : la mission demande
  l'écriture sûre « réemployée, pas recopiée ». Options écartées : la recopier dans
  `etl/digest_sheets.py` ; la mettre dans `core/` (elle écrit par `write_file_atomically` de
  `etl/raw_store.py`, et `core` n'importe rien de K-B). Limite assumée, décision de Sabine du
  2026-10-21 (constat 1 de la revue de code, confirmé par un relecteur de sécurité) : une fiche
  apparue entre `has_sheet` et le `os.replace` de `write_file_atomically` est remplacée sans
  message (CWE-367), et un dossier remplacé par un lien dans cette fenêtre fait écrire hors du
  coffre (CWE-59, déjà acceptée le 2026-10-19 pour `kb write-tops`) ; seuls deux lancements de
  l'utilisatrice qui se chevauchent le peuvent, jamais un contenu non fiable. Correction (publier
  par `os.link`, écrire par descripteurs) : #295, après les squelettes d'E1 et d'E3, au plus tard
  dès que `kb digest` ou `kb write-tops` tourne sans l'utilisatrice. Option écartée ici : modifier
  `write_file_atomically` et la règle 2 de `conventions.md` dans cette PR. Les fiches des tops gardent leur jeu de
  caractères et leur URL nue cliquable (2026-10-19). — PR de #209
- **Dans une fiche de veille, chaque affirmation et chaque titre de source est écrit en texte : le
  jeu des fiches des tops (le `&` d'une référence de caractère compris), plus `~`, `:` et `@`,
  puis le point de `www.`, sans casse, la
  ponctuation d'un marqueur de liste en tête du texte, et une espace entre deux deux-points ; une
  affirmation renvoie à ses sources par leur numéro. Une URL de source n'est écrite, en lien
  automatique `<…>`, que si elle commence par `http://` ou `https://` et n'est faite que des
  caractères de la RFC 3986, moins `[`, `]` et `$`, sans `::`, sans référence de caractère, et
  sans caractère caché une fois ses pourcents décodés ; sinon « (sans URL) ».** Choix de la session
  (plan validé ; la règle de l'URL resserrée en codant, acceptée par time-knight le 2026-10-21 ;
  `&` et le marqueur de liste ajoutés après la revue de code et un relecteur de sécurité, tranchés
  par time-knight, délégation de Sabine du 2026-10-15).
  Pourquoi : la réponse est une entrée non fiable (OWASP LLM10:2026) ; une affirmation ou un titre
  piégés deviendraient actifs dans Obsidian, jusqu'au JavaScript d'un bloc `dataviewjs` ou d'une
  requête `$=` si l'utilisatrice les a activés. `~` ouvre un bloc `~~~` ; `:` et `@` font les liens
  automatiques de GFM (`http://`, et, dans Obsidian, `mailto:`, `xmpp:` et une adresse mail, d'après
  la recette du 2026-10-21 ; cmark-gfm, le moteur de GitHub, en fait encore un lien `mailto:`) et
  les champs Dataview `::` ;
  `&` ouvre une référence de caractère, que CommonMark décode (`&rlm;` rend le contrôle
  bidirectionnel que la neutralisation retire) ; un marqueur de liste en tête imbrique une liste
  (CWE-116 : une structure, sans injection ; un titre « 2026. Bilan » suffit). L'espace entre deux
  deux-points vient de la recette de Sabine du 2026-10-21 dans Obsidian : `\[champ\:\: valeur\]`
  s'affichait encore en champ Dataview en mode lecture, car Dataview y cherche `::` dans le HTML
  rendu (`replaceInlineFields`, 0.5.68), où les échappements ont disparu ; son indexeur lit la
  source, où `\:\:` n'est pas un champ : aucune métadonnée n'entrait dans la page (code de
  Dataview 0.5.68 lu le 2026-10-21). Option écartée : un caractère invisible entre les deux-points
  (U+2060), qui tromperait un copier-coller. Limite assumée : `std::string` s'affiche
  `std: :string`. Une affirmation du modèle ne fait jamais un lien, à la différence d'une
  description de top.
  Dans `<…>`, une barre oblique n'échappe rien (CommonMark 0.31.2, § 6.5) : l'URL ne doit contenir
  aucun caractère qui la ferait sortir, et `[`, `]`, `$` sont de la syntaxe d'Obsidian. Après la
  seconde revue de code et un relecteur de sécurité (tranchés par time-knight, délégation de
  Sabine du 2026-10-15) : une référence de caractère (`&#x202E;`, que cmark-gfm décode dans le
  texte du lien) ou un caractère caché encodé en pourcents (`%E2%80%AE`, que markdown-it montre)
  ferait lire un lien autrement qu'il ne mène (CWE-451) ; `::` ferait un champ Dataview dans la
  ligne rendue, et même dans les métadonnées de la page (l'indexeur lit les champs d'un élément de
  liste). L'URL est refusée, jamais réécrite, ce qui changerait sa cible. Options
  écartées : le seul contrôle 6 de l'API IA, qui reste en amont (il laisse passer `$=`, `#`, `%%`,
  `::` et une adresse mail, et ne lit pas les titres, donnée de source) ; l'URL lue en ASCII
  imprimable sans espace, `<`, `>` ni `\` (plan v2, moins strict). Limites assumées : l'emphase
  (`*x*`, `_x_`, `==x==`) n'est pas échappée, c'est de la mise en forme ; le rendu dans Obsidian,
  logiciel fermé, n'est prouvé que par la recette de la PR. — PR de #209
- **Une seule règle pour les deux écrivains du coffre : le `&` qui ouvre une référence de caractère
  (`&` suivi de `#`, ou d'un nom ASCII puis `;`) est échappé, dans une description de top comme
  dans une fiche de veille ; un autre `&` reste.** Décisions de Sabine du 2026-10-21, relayées par
  time-knight, sur un constat du relecteur de sécurité : d'abord `&` échappé partout, puis, le même
  soir, ce seul `&`, d'abord pour les tops, enfin pour les deux, ce qui affine les premières sans en
  changer le but : aucune référence décodée, un fichier `.md` plus lisible, les URL nues des tops
  justes. Pourquoi : une
  référence nommée (`&rlm;`, `&lrm;`) rend à l'affichage le contrôle bidirectionnel que
  `neutralize_text` retire ; les références numériques étaient déjà inactives, puisque `#` est
  échappé. Un `&` toujours échappé cassait les URL nues des tops qui ont une requête :
  `?q=a\&page=2` devient, dans cmark-gfm, un lien vers `?q=a%5C&page=2` (seconde revue de code,
  constat 3) ; les URL nues des tops restent justes. Le motif est appliqué dans la même passe que
  l'échappement, sur la ligne, avant toute barre insérée, jamais après un passage qui échappe déjà
  `&`. Options écartées : `&` dans les seules fiches de veille ; tout `&` échappé (la première
  décision) ; tout `&` dans les fiches de veille et le seul `&` d'une référence dans les tops (deux
  règles). Limite assumée : `#` et `%` cassaient déjà, depuis le 2026-10-19, dans
  cmark-gfm, une URL nue de top qui a une ancre ou un pourcent ; non vérifié dans Obsidian.
  **Révise** 2026-10-19, « Tops : les fiches par `kb write-tops` » : la liste des caractères
  échappés d'une description (P4) compte le `&` d'une référence. — PR de #209
- **Avant sa demande, `kb digest` vérifie, pour chaque sujet de la liste, que ni `veille/` ni
  `veille/<sujet>/` n'est un lien symbolique et que la fiche du jour UTC n'existe pas ; sinon il
  sort en 2 sans rien demander.** Choix de la session dans le plan validé. Pourquoi : aucun item ne
  part au modèle pour une fiche qui ne serait pas écrite (minimisation, coût). Option écartée :
  demander, puis sauter les fiches qui existent. Limites assumées : relancer le même jour après un
  échec partiel sort en 2, et les sujets en échec s'écrivent le lendemain si leurs items restent
  dans la fenêtre ; le jour contrôlé est celui de l'horloge de `kb`, celui de la fiche est
  `window.until` : une demande à cheval sur minuit UTC compte en échec un sujet dont la fiche du
  lendemain existe déjà. — PR de #209
- **`kb digest` attend la réponse 240 s au plus (`AI_API_READ_TIMEOUT_SECONDS`), sans nouvelle
  tentative ; un `Retry-After` est affiché, jamais attendu. Le corps de la réponse est lu sans
  borne de taille.** Décision de Sabine pour la borne (décision 6) : risque accepté pour le POC,
  faible, car c'est son propre service, à une adresse qu'elle règle. Pourquoi 240 : au-dessus de
  `DIGEST_REQUEST_TIMEOUT_SECONDS` (200 s) et du dernier appel au modèle en cours (environ 20 s de
  plus, `ai_api/deadline.py`), égal à la borne de l'ingress d'Azure Container Apps. Option écartée :
  relancer après un 503 (une attente sans borne, seconde revue de #156). Signalé, avec son
  déclencheur : avant la mise en ligne du 08/11, une borne de lecture dans `core/outbound.py`,
  commune aux deux clients (`read_bounded_body` et son échéance). — PR de #209
- **Les clés du frontmatter sont en anglais partout ; le texte rédigé d'une fiche (affirmations,
  titres de section, phrases fixes) est en français ; une citation garde sa langue (titre d'une
  source, nom d'un dépôt).** Règle de Sabine (décision 5). Les identifiants sont en anglais : le
  code, les champs de l'API et les clés du frontmatter, dont Obsidian impose lui-même certaines en
  anglais (`tags`, `aliases`, `cssclasses`). Les fiches des tops passent de `classement`, `releve`
  et `depots` à `ranking`, `collected_at` et `repositories`. **Révise** 2026-10-19, « Tops : les
  fiches par `kb write-tops` » : « en français : un frontmatter (`classement`, `releve`,
  `depots`) ». Limite assumée : une fiche n'est jamais réécrite, donc les fiches des tops du coffre
  de dev (`temp/` du dépôt) gardent leurs anciennes clés ; le vrai coffre de Sabine n'en a aucune
  (dit par Sabine). — PR de #209

## 2026-10-22

### Post-traitement : un paquet `k_b.post` hors de l'ETL

- **Les quatre modules de post-traitement sortent de `src/k_b/etl/` vers un paquet nouveau,
  `src/k_b/post/`, à plat : `ai_api_client.py` (la demande de `kb digest` à l'API IA),
  `digest_sheets.py` (la fiche de veille rendue), `top_sheets.py` (les fiches des tops) et
  `vault_files.py` (l'écriture sûre dans le coffre). Déplacement mécanique : `git mv`, aucun corps
  de fonction, nom de fonction ni nom de module changé ; seules des lignes d'`import` sont
  modifiées.** Décision de Sabine du 2026-10-22, sur la cible annoncée dans
  `docs/refactoring/inventaire.md`. Pourquoi : `etl` nomme un parcours précis — extraire d'une
  source, transformer en items communs, charger en base — et demander des fiches à un modèle, les
  rendre en Markdown et les écrire dans un coffre Obsidian n'en fait pas partie ; un paquet dont le
  nom ne prédit plus le contenu ne sert plus de table des matières (`code.md`, « Lisibilité »).
  Les sous-dossiers `post/digest/` et `post/render/` de la cible ne sont pas créés : avec quatre
  modules, deux dossiers de deux fichiers ne font rien gagner, et `digest_sheets.py` relèverait des
  deux. Options écartées : garder les quatre dans `etl/` avec une convention écrite (la règle
  ci-dessous serait intenable) ; les ranger tout de suite en `digest/` et `render/`.
  — branche `refactoring/etl`
- **`Top` et `TopEntry` sont définies dans `src/k_b/etl/tops.py`, pas dans le module des fiches :
  `etl` garde le vocabulaire que ses sources produisent, et `post/top_sheets.py` le consomme.**
  Décision de Sabine du 2026-10-22, prise sur un blocage signalé par la session : trois modules qui
  restent dans `etl/` importaient `etl/top_sheets.py` (`source_kinds.py` pour `Top`,
  `sources/github_most_starred.py` et `sources/github_most_forked.py` pour `TopEntry`), de sorte
  que le déplacement tel quel aurait créé trois imports `etl` → `post`. Les deux classes sont
  déplacées à l'identique, sans changement de champ, de nom ni de signature. Le nom au pluriel dit
  une famille de types, à côté de `top_sheets.py` qui dit un traitement. Conséquence pour la doc :
  un module de `etl` se décrit par ce qu'il produit, pas par son consommateur dans `post` — les
  docstrings de `read_top_entries` renvoient à `(TopEntry, etl/tops.py)`. Options écartées :
  `items.py` (un top n'entre jamais en base) ; laisser `top_sheets.py` dans `etl/` ; déplacer
  `top_sheets.py` sans extraire les types, en renonçant à la règle ou en lui faisant une exception.
  — branche `refactoring/etl`
- **`k_b.etl` n'importe jamais `k_b.post`. La règle est tenue par
  `tests/architecture/test_layers.py` : `test_etl_imports_nothing_of_the_post_processing` lit les
  imports de chaque fichier de `etl/` par `ast`, et `reaches` refuse aussi le paquet qui y donne
  accès (`from k_b import post`) ; un second test, paramétré, vérifie que le détecteur refuse
  chaque forme d'import et laisse passer un module de `etl`.** Décision de Sabine du 2026-10-22,
  première des règles de la cible. Pourquoi : le post-traitement part de ce que le pipeline a
  produit, donc il lit `etl` ; l'inverse ferait dépendre la collecte de la façon de présenter ses
  résultats, et formerait un cycle d'imports. Même motif que la porte des écrivains (#251) et que
  la règle qui tient `etl` sous les API (#209) : une règle d'architecture qu'aucun test ne tient
  n'est qu'un texte. Les deux listes de `tests/architecture/module_imports.py` suivent (`"post"`
  dans `TOP_LEVEL_MODULES`, les quatre modules hors d'`ETL_PIPELINE_MODULES`, `"etl.tops"` dedans) :
  elles font échouer `test_every_module_of_k_b_is_listed` et
  `test_every_module_of_etl_is_in_exactly_one_list` si un module arrive sans qu'on décide où il va.
  Vérifiée par contre-épreuve : un import ajouté dans `etl/user_agent.py` fait échouer le test.
  Option écartée : un `grep` du critère de fin seul. — branche `refactoring/etl`
- **Une mention de chemin dans le dépôt est corrigée si elle décrit l'état actuel, laissée
  intacte si elle raconte un état passé.** Décision de Sabine du 2026-10-22, sur le classement
  proposé par la session. Sont vivants : les commentaires et docstrings du code,
  `docs/fiches-veille.md` (le contrat des fiches) et `docs/registre-traitements.md` (le registre en
  vigueur). Sont historiques, donc non réécrits : `docs/journaling/`, les entrées déjà écrites de
  ce journal, `docs/refactoring/inventaire.md` et `docs/2026-10-21-collecte-reelle.md`, tous deux
  épinglés à un commit. Pourquoi : une note datée dit ce qui a été observé ce jour-là, numéros de
  ligne compris ; la réécrire la ferait mentir. Confirme ce que posait déjà la note du 2026-10-18
  sur les tests d'architecture. Limite assumée : le classement est un jugement, pas un critère
  automatique ; un document nouveau se classe à la main. — branche `refactoring/etl`

### Tendances : un lecteur porté par la sorte, et un seul parcours de `raw/`

- **La sorte d'une source porte un second lecteur, `trend_reader` (`TrendReader` :
  `source_code`, `read_rows`), à côté de `reader`, et c'est par lui que le lecteur des tendances
  de GH Archive parvient à `etl/transform.py`. `read_trend_files` quitte
  `etl/sources/gh_archive.py` ; la source ne garde que ce qui lui est propre (la requête
  BigQuery, `read_trends`, `TrendsExtract`, `describe_validation_error`) et expose
  `read_trend_rows` par la constante `TREND_READER`, que `source_kinds.py` lui donne, comme les
  sept `READER` des autres sources.** Décision de Sabine du 2026-10-22, étape 3 du plan de
  refactorisation, après un relevé en lecture seule des options. Pourquoi : `transform.py` est un
  module du pipeline, et un test d'architecture lui interdit d'importer une source ou la
  composition
  (`test_no_module_of_the_pipeline_imports_the_sources_or_the_composition`) ; le lecteur doit
  donc arriver par paramètre, et la sorte est déjà l'endroit où une source dit comment lire son
  dossier brut (`find_source_kind` route un dossier vers exactement une sorte). Le champ a `None`
  pour défaut : les vingt constructions de `SourceKind` de `src/` et de `tests/` restent
  intactes, et seule la ligne de GH Archive change. Le vocabulaire est celui de la base
  (`trend`, `TrendRow`, `TrendFile`, `TrendReading`) et non « ranking », qui désigne déjà les
  tops GitHub. Un invariant tenu par un test, faute d'un type qui l'exprime : une sorte porte un
  lecteur ou l'autre, jamais les deux
  (`test_no_kind_has_both_a_reader_of_items_and_a_trend_reader`). Aucun test d'architecture n'a
  été modifié : les 102 passent tels quels, ce qui prouve que c'est la composition, et non le
  transform, qui nomme la source. Options écartées : étendre `SourceReader` (déjà écartée le
  2026-10-13 ; raison de fond ajoutée : `EntryReading` porte des rejets par entrée, alors qu'un
  classement se refuse en entier, exception de la règle 1 de `conventions.md`) ; une constante
  `RANKING_KINDS` déclarée à côté de `SOURCE_KINDS`, sur le modèle de `TOPS` (deux listes à tenir
  en phase, `gh_archive` nommé dans les deux, et deux listes à porter dans le `pipeline.py` de
  l'étape 4). — branche `refactoring/etl`
- **Un seul parcours de `raw/` rend les deux lectures : `read_raw_files` appelle
  `list_collections`, qui classe chaque collecte selon le lecteur de sa sorte, puis rend
  `RawReadings(items, trends)`. `kb import` l'appelle une fois au lieu de deux ; `import_items`
  garde ses deux lectures et n'est pas touché.** Décision de Sabine du 2026-10-22. Pourquoi :
  `list_collections` parcourait déjà tous les dossiers de `raw/` et trouvait la sorte de chacun,
  y compris celle de GH Archive, qu'il journalisait et sautait ; il classe désormais au lieu de
  sauter. **Close** « Un seul chemin de lecture pour les items et les classements » (2026-10-13,
  décisions ouvertes) et **lève la limite assumée** de « Import dans la base : TENDANCE » : il
  n'y a plus deux chemins de lecture, et plus personne ne refait « en une vingtaine de lignes le
  parcours d'un dossier, le saut d'un fichier déjà importé et les rejets ». Les deux `read_count`
  restent séparés dans `RawReadings` : leur somme est le `raw files read` que `kb import`
  affiche. — branche `refactoring/etl`
- **Deux changements de comportement, acceptés.** Décisions de Sabine du 2026-10-22, sur le
  compte rendu de la session. (1) La ligne de journal « source without a reader of items,
  skipped by the item reader: 'x' » devient « source without a reader, skipped: 'x' » : avec une
  entrée de lecture unique, « sauté par le lecteur d'items » n'a plus de sens, et le message ne
  concerne plus que les deux classements GitHub, seules sortes sans aucun lecteur. (2) Le dossier
  brut des tendances est trouvé **par préfixe**, comme pour toute autre source : un dossier
  `gh_archive_<suffixe>`, ou un `gh_archive` sous `selected_library/`, serait désormais lu, là où
  l'ancien lecteur ne lisait que `automated_watch/gh_archive`. Même règle que pour les autres
  sources, dont un dossier plus suivi reste lu (`cisa_kev_old`,
  `test_the_raw_files_of_a_folder_no_longer_tracked_are_read`) ; aucune source ne peut écrire un
  tel dossier aujourd'hui. Un chemin d'erreur a été préservé exprès : `list_collections` ne liste
  un dossier de source que s'il a un lecteur, sinon un dossier de top illisible ferait échouer
  tout l'import là où il était sauté. — branche `refactoring/etl`
- **La lecture du brut par `RawStore` ne se fait pas à l'étape 3 : elle devient l'étape 3 bis,
  pour tout `transform.py` d'un coup.** Décision de Sabine du 2026-10-22, sur la recommandation
  de la session, qui **amende le texte de l'étape 3 du plan** (« via RawStore »). Pourquoi : les
  tendances par clé et les items par `Path` donneraient à un seul module deux adresses pour le
  même arbre (une clé de `RawStore` commence par `raw/`, un `raw_file_path` en est relatif), ce
  qui condamnerait le parcours unique ; et le contrôle de la règle 3 de `poc.md` est un `grep -rl`,
  une liste de **fichiers** : `transform.py` y reste tant que le lecteur d'items ouvre le brut,
  donc la moitié du chemin ne gagne rien de mesurable. Ce que l'étape 3 gagne sur la règle 3 est
  la sortie de `gh_archive.py` de cette liste, qui vient du déplacement et non de la poignée (la
  liste passe de onze à dix fichiers, et `etl/transform.py` est le seul qui touche encore le
  brut). L'étape 3 bis demandera deux ou trois méthodes nouvelles de `RawStore` (lister les
  dossiers de source, lister les entrées d'un dossier dossiers compris, la conversion clé ↔
  `raw_file_path` nommée une fois) et touchera cinq signatures et les tests qui passent un
  `raw_dir`. Option écartée : tout faire dans l'étape 3, en acceptant un diff large dans la même
  étape qu'une décision de conception (`plan.md`, §6 : les déplacements mécaniques sont séparés
  des changements de comportement). — branche `refactoring/etl`

## 2026-10-23

### ETL : `pipeline.py` enchaîne les stages, la relecture du brut et les rejets à part

- **`etl/pipeline.py` porte les deux parcours de l'ETL et devient la porte unique de `commands/`
  vers eux : `collect(sources, data_dir, now)` pour la collecte (stage 1) et
  `import_raw_files(data_dir, kinds, tracked_repositories, imported_at)` pour l'import (stages 2
  puis 3). Il ne lit aucun réglage, n'affiche rien et ne rend aucun code de sortie ; ce qui nomme
  les sources arrive en paramètre, et chaque parcours rend un résultat nommé que la commande
  affiche. `__all__` dit ce qui passe la porte, comme `database/writing.py` pour les écrivains, de
  sorte que `commands/` n'importe plus `etl/extract.py`, `etl/transform.py`, `etl/load.py` ni
  `etl/raw_purge.py`.** Décision de Sabine du 2026-10-23, étape 4 du plan de refactorisation,
  après le relevé en lecture seule de `docs/refactoring/orchestration.md` (2026-10-22). Pourquoi :
  l'orchestration de `kb import` vivait à deux endroits, la commande et `load.import_items`, avec
  la frontière au milieu d'un parcours — le registre lu dans `load.py`, le brut dans
  `transform.py`, et la commande qui les mettait dans l'ordre. Un parcours s'écrit comme une suite
  d'étapes nommées (`code.md`) ; la commande garde ce qui lui revient : l'environnement, l'horloge,
  le résumé affiché, les codes de sortie et SIGTERM (posé par `cli.py`, `poc.md`, règle 6). Le
  module est ajouté à `ETL_PIPELINE_MODULES`, ce qui le soumet à
  `test_no_module_of_the_pipeline_imports_the_sources_or_the_composition` : `SOURCE_KINDS`,
  `TRACKED_REPOSITORIES` et `LATEST_ONLY_FOLDER_KEYS` restent donc dans la commande, puisqu'ils
  nomment des sources. La boucle des sources ne bouge pas : la cible (§1 du plan) donne le parcours
  de la liste à `extract.py`, et `pipeline.collect` ne fait que nommer le parcours. Effet mesuré :
  la liste des dépôts suivis n'entre plus qu'une fois dans l'import et va au filtre du transform
  comme à la table de la base — l'incohérence entre les deux, signalée au §8 du plan, devient
  inatteignable depuis les commandes. Options écartées : l'orchestration dans `commands/`
  (option C du relevé : elle contredit la règle 5 de `conventions.md` sur deux points, et aucun
  test d'architecture ne la tiendrait) ; trois paquets `etl/extract/`, `etl/transform/`,
  `etl/load/` (option B : le plus large diff, pour des paquets de un ou deux modules).
  — branche `refactoring/etl`
- **La purge du brut reste une étape à part, appelée par la commande après l'affichage du résumé :
  `pipeline.purge_superseded_raw(data_dir, latest_only_folder_keys)`, et non une étape de
  `import_raw_files`.** **Révisée le 2026-11-04** : les purges sortent de l'ETL, dans
  `src/k_b/purge/` (#83). Décision de Sabine du 2026-10-23, sur les deux options du compte rendu de
  la session. Pourquoi : aucun changement de comportement — le résumé de l'import sort avant la
  purge, donc un import qui a commité dit ce qu'il a écrit même quand la purge échoue — et le plan
  classe la rétention hors des trois stages (§1). Conséquence : `ImportOutcome` ne porte que le
  résumé et le chemin du journal, la commande garde ses deux `try` et son unique ligne de journal
  de purge (qui a besoin de `describe_os_error`, dans `commands/`, donc hors de portée d'`etl`).
  Un test fige l'ordre : `test_a_failed_purge_leaves_the_summary_of_the_import_it_committed`.
  Option écartée : la purge dans `import_raw_files`, avec son erreur portée par `ImportOutcome`
  sur le modèle de `CollectionOutcome.state_error` — l'invariant « la purge ne tourne qu'après le
  commit » serait devenu structurel, mais un SIGTERM reçu pendant la purge aurait fait perdre le
  résumé affiché aujourd'hui. — branche `refactoring/etl`
- **L'enchaînement des deux parcours reste hors périmètre : `pipeline.py` nomme les deux parcours,
  et c'est la suite de commandes (`kb collect ; kb import`) qui les enchaîne, tant qu'aucun job en
  conteneur ne l'appelle. Le §2, règle 5 du plan est amendé en ce sens.** Décision de Sabine du
  2026-10-23, sur la recommandation de la session. Pourquoi : la fonction d'enchaînement n'aurait
  aucun appelant (`code.md` : aucune abstraction sans second usage, pas de couche pour plus tard) ;
  l'enchaînement en ligne est un job ACA qui enchaîne des exécutions de conteneur, pas deux
  fonctions dans un processus ; et un seul code de sortie pour deux parcours contredirait le
  README, qui garantit aujourd'hui qu'« chaque étape tourne même si la précédente a échoué en
  partie […] et garde son propre code de sortie ». À rouvrir au temps 2 (conteneurs), avec la
  question du code de sortie posée. Option écartée : écrire `collect_then_import` et une commande
  `kb run` maintenant. — branche `refactoring/etl`
- **`reject` quitte `etl/transform.py` pour un module à lui, `etl/rejections.py` ; le type
  `Rejection` reste définitivement dans `etl/raw_files.py`, le vocabulaire pur partagé par les
  stages.** Décision de Sabine du 2026-10-23, prise sur un blocage signalé par la session : sortir
  la relecture du brut de `transform.py` (ci-dessous) demandait que les fonctions déplacées
  atteignent `reject`, alors que `transform.py` importe désormais le module qui les porte — garder
  `reject` dans `transform.py` aurait formé un cycle. Pourquoi ce module plutôt que `raw_reading.py`
  ou `raw_files.py` : `reject` journalise, donc il n'a pas sa place dans un vocabulaire pur (§8 du
  plan) ; et `load.py` l'appelle aussi, de sorte que le mettre dans le module de relecture du brut
  aurait fait importer celui-ci par le load. La destination du §8 est donc atteinte d'un coup,
  plutôt qu'en deux déplacements d'une fonction qui journalise. Effet de bord mesuré : `load.py:63`
  était le seul import de `transform` par `load` — après ce déplacement, `extract`, `transform` et
  `load` ne s'importent plus entre eux. Option écartée : `reject` dans `raw_reading.py`, suivi d'un
  second déplacement à l'étape 5. — branche `refactoring/etl`
- **Ce qui lit `raw/` sort de `etl/transform.py` dans `etl/raw_reading.py` : `list_collections`,
  `read_collection`, `read_page`, `list_pages`, `list_visible_entries` et le type `Collections`,
  déplacés tels quels ; `read_raw_trends` est séparé entre son parcours, qui reste dans
  `transform.py` à côté de celui des items, et la lecture d'un fichier, `read_trend_file`, qui part
  avec les autres. `join_readings` va dans `etl/raw_files.py`, à côté de `RawReading`, avec
  `join_trend_readings` écrit sur son modèle.** Décision de Sabine du 2026-10-23, sur le constat de
  la session que `transform.py` ne se lisait plus comme une table des matières : 334 lignes et
  quatre niveaux de détail dans le même module (le parcours, les étapes pures, la relecture du brut,
  et un `read_raw_trends` qui mélangeait parcours et détail). Pourquoi maintenant, et non à l'étape 3 bis comme la session le proposait d'abord : l'étape 3 bis,
  liée au passage du brut à Azure Blob Storage, vient après le jalon, alors que le but du jalon est
  un ETL lisible ; et elle ne réécrira plus qu'un seul module, celui-ci. `transform.py` tombe à 159 lignes et sept définitions, sans accès au système de
  fichiers et sans ligne de journal propre ; il sort de la liste des fichiers qui touchent le brut
  (`poc.md`, règle 3), où `raw_reading.py` le remplace. Les cinq déplacements ont été vérifiés
  identiques au caractère, bloc par bloc, contre `HEAD`. Le nom `read_trend_file` a remplacé
  `read_ranking` après coup : « ranking » désigne les tops GitHub, et `read_ranking` existait déjà
  trois fois pour eux. Options écartées : garder la relecture du brut dans `transform.py` jusqu'à
  l'étape 3 bis ; ne déplacer que les fonctions de listage, qui n'appellent pas `reject` (le but,
  sortir `transform.py` de la liste de la règle 3, n'était pas atteint : `read_page` ouvre le brut).
  — branche `refactoring/etl`
- **Deux changements de nom de logger, acceptés.** Décisions de Sabine du 2026-10-23, sur les
  comptes rendus de la session. (1) Une ligne de rejet (`rejected from <chemin> : <raison>`) passe
  de `k_b.etl.transform` à `k_b.etl.rejections`, y compris les deux rejets émis pendant l'écriture
  en base (une entrée que la base refuse, un fichier de tendances refusé) : ils disaient
  `k_b.etl.transform` alors qu'aucun transform ne tournait, et la nouvelle valeur est plus juste au
  sens de la règle 3 de `conventions.md` (« quand, où, qui, quoi »). (2) Les trois lignes `INFO` du
  listage de `raw/` (« folder without a source kind, skipped », « source without a reader,
  skipped », « folder inside a collection folder, skipped ») passent de `k_b.etl.transform` à
  `k_b.etl.raw_reading`. Vérifié avant de décider : aucun test ne filtre sur le nom de ce logger
  (les tests du transform capturent la racine), et le texte des lignes ne change pas. Limite
  assumée : un `grep` du journal de fonctionnement sur `k_b.etl.transform` ne trouvera plus ces
  lignes. — branche `refactoring/etl`
- **La règle « extract, transform et load ne s'importent pas entre eux » est tenue par un test :
  `test_no_stage_of_the_etl_imports_another_stage` (`tests/architecture/test_layers.py`), sur le
  modèle des trois règles voisines — un détecteur (`list_imports_of_another_stage`), un test sur
  les fichiers réels, et un test paramétré des formes d'import.** Décision de Sabine du
  2026-10-23, étape 5 du plan. Pourquoi : une règle d'architecture qu'aucun test ne tient n'est
  qu'un texte (même motif que la porte des écrivains, #251, et que la règle `etl` → `post`). Le
  détecteur retire du jeu l'étape qui interroge, parce que la liste interdite dépend de qui
  demande, et `reaches` refuse aussi le paquet qui donne accès (`from k_b import etl`) ;
  `pipeline.py`, qui n'est pas un stage, garde le droit d'importer les trois. Contre-épreuve :
  l'import que le déplacement de `reject` a retiré (`from k_b.etl.transform import reject` dans
  `etl/load.py`) remis en place fait échouer le test, qui nomme le fichier et l'étape atteinte ;
  l'import a ensuite été retiré, et le fichier vérifié identique. Option écartée : un `grep` du
  critère de fin seul. — branche `refactoring/etl`

## 2026-10-24

### Métriques : l'export OpenTelemetry de l'API IA (#162)

Décisions prises au plan de #162, validé par Sabine le 2026-10-24 et relayé par time-knight, puis
aux deux revues de code, tranchées par time-knight (délégation de Sabine du 2026-10-15). Elles
appliquent « Squelette E1 E3 : cadrage du 20/10 », décision 4.

- **K-B lit ses propres variables d'export, `KB_OTLP_ENDPOINT` et `KB_OTLP_HEADERS`, et `kb
  serve-ai` refuse de démarrer si une variable `OTEL_*` est présente.** Pourquoi, constaté dans le
  code du SDK 1.45.1 à la relecture du plan : l'exporteur relit l'environnement même quand on lui
  passe l'en-tête (`_resolve_headers`), et son lecteur d'en-têtes journalise tel quel un segment
  mal formé, donc le jeton ; d'autres variables changent son comportement en silence
  (`OTEL_SDK_DISABLED`, intervalle, attributs de ressource). Refuser tout le préfixe est une règle
  fermée, qui ne prend pas de retard sur la version suivante du SDK. Options écartées : les noms
  standard `OTEL_EXPORTER_OTLP_*`, que Grafana Cloud et Honeycomb donnent tout prêts (premier
  plan) ; une liste des variables à refuser. Changer d'outil reste un changement d'URL et
  d'en-tête : les valeurs se collent sous un autre nom. Contredit le skill `fastapi` du dépôt
  (0.143.1, section OpenTelemetry), qui conseille la télémétrie native réglée par les `OTEL_*` :
  non appliqué ici, signalé pour #281. — PR de #162
- **`KB_DEPLOYMENT_ENVIRONMENT` (`sandbox` ou `production`) n'a pas de défaut ; elle est exigée
  dès que l'export est réglé, ignorée sans lui.** Décision de Sabine du 2026-10-24. Pourquoi, selon
  la question posée par la relecture du plan : avec un défaut `sandbox`, une production où l'on
  oublie la variable serait étiquetée `sandbox` sans message. Option écartée : un défaut `sandbox`
  dans `core/config.py`. **Précise** la décision 4 du 20/10 (« seuls l'URL et le jeton changent ») :
  d'un environnement à l'autre, trois réglages changent, aucun code. Écart à la règle 2 de
  `.claude/rules/poc.md` (un réglage de déploiement a un défaut local), au même titre qu'un service
  distant. — PR de #162
- **La ressource est construite par son constructeur : `service.name`, `deployment.environment.name`
  et un `service.instance.id` tiré au hasard par processus, rien d'autre.** Pourquoi : le critère de
  #162 interdit `host.name`, `process.owner`, `process.command_args` et tout chemin ;
  `Resource.create` lit `OTEL_RESOURCE_ATTRIBUTES` et les détecteurs de
  `OTEL_EXPERIMENTAL_RESOURCE_DETECTORS`. L'identifiant d'instance (première revue de code) : sans
  lui, deux processus qui exportent en même temps écrivent les mêmes séries cumulées. Limite
  assumée : chaque redémarrage ouvre de nouvelles séries (89 pour une demande ordinaire, face aux
  10 000 séries actives de l'offre gratuite). Option écartée : `Resource.create`, la voie que la doc
  du SDK présente d'abord. — PR de #162
- **OpenTelemetry ne s'importe que dans `ai_api/connectors/metrics_export.py` et
  `ai_api/metric_instruments.py` ; l'app, le routeur et les commandes ne voient que `ModelMetrics`
  (enregistrer, arrêter). Un test d'architecture le tient.** Décision de Sabine du 2026-10-24,
  ajoutée au plan, sur la recommandation de time-knight (« je suis tes recommandations »).
  Pourquoi de Sabine, le 24/10 vers 10:00 UTC : « On avait parlé d'une façon de faire qui
  limitait la "pollution" du code par opentelemetry ». La règle est tenue par un test, selon sa
  règle d'harmonisation : une règle par sujet, tenue par un test. Conséquence : les règles de
  l'export (refus des `OTEL_*`, ressource fermée, session HTTP sans l'environnement) restent en un
  seul endroit. `requests`, client de l'exporteur, est tenu de même dans `metrics_export.py`. —
  PR de #162
- **L'arrêt envoie les dernières mesures dans le `lifespan` de l'app, et non après `uvicorn.run`.**
  Pourquoi, constaté à la relecture du plan dans `uvicorn/server.py` : uvicorn finit les demandes
  en cours, termine le `lifespan`, puis relance le SIGTERM qui tue le processus ; un code placé
  après `uvicorn.run` ne s'exécute jamais. Option écartée : un `finally` après `uvicorn.run` (premier
  plan). Limite assumée (première revue) : une demande en cours retarde le dernier envoi jusqu'à
  `DIGEST_REQUEST_TIMEOUT_SECONDS`, au-delà des 10 s de `docker stop` ; le délai d'arrêt du conteneur
  est renvoyé à #200. — PR de #162
- **La télémétrie native de FastAPI 0.143 est coupée dans les deux API (`core/api_telemetry.py`).**
  Pourquoi (première revue, vérifiée par time-knight) : les paquets ajoutés par #162 arment sa
  configuration automatique ; avec `FASTAPI_OTEL_AUTO_CONFIGURE=true`, FastAPI pose ses propres
  fournisseurs globaux, et une trace de l'API de données porterait la requête brute d'un client vers
  un destinataire absent du registre. Option écartée : la couper dans l'API IA seule (premier état
  du code). Les traces restent l'objet de #281. — PR de #162
- **La durée de lecture de la veille est mesurée à chaque demande lue, même sans appel au modèle ;
  les compteurs de la fidélité qui existent (`claims_removed`, `items_uncited`) partent dès #162.**
  Décisions de Sabine du 2026-10-24, sur les recommandations du plan. Pourquoi : la ligne JSON ne
  porte pas la lecture d'une demande sans appel (`docs/fiches-veille.md`, « Métriques »,
  « Limites ») ; les deux compteurs sont déjà sur la ligne, #207 n'ajoute que `facts_checked` et
  `facts_found`. Options écartées : la lecture seulement quand la ligne JSON la porte ; tous les
  compteurs de la fidélité à #207. — PR de #162
- **Le DPA de Grafana Labs est lu, non signé ; il est à signer avant tout envoi d'une donnée
  personnelle.** Décision de Sabine du 2026-10-24. Pourquoi : le DPA (ver. 2026.04.02) ne prend effet
  que signé par la cliente et reçu par Grafana Labs, et les mesures ne portent aucune donnée
  personnelle (test). Option écartée : le signer avant le premier envoi. Inscrit au registre
  (« Envoi des mesures à Grafana Cloud »). — PR de #162

### Fiches de veille : la fidélité (#207)

Décisions de Sabine du 2026-10-24 sur les recommandations du plan de #207, relayées par time-knight,
puis décisions de time-knight sur les revues de #207 (délégation de Sabine du 2026-10-15).

- **`fidelity_rate` est un champ de la ligne `llm_call`, arrondi à 4 décimales, nul au classement,
  pour une rédaction en échec et sans fait vérifié ; seuls `facts_checked` et `facts_found` partent
  en OpenTelemetry.** Pourquoi : la spec définissait le taux sans lui donner de place ; la règle 4
  de `poc.md` met les métriques de l'API IA sur une ligne JSON par appel, et le critère de #153 veut
  un taux « calculé à chaque appel » ; un taux ne s'additionne pas, Grafana le tire des deux
  compteurs ; 4 décimales donnent un pourcentage à 2 décimales, assez pour lire le seuil de 95 %.
  Options écartées : aucun champ (#210 le calculerait à la main, et aucun code ne tiendrait « est
  calculé ») ; le taux dans la réponse de `POST /digests` (OpenAPI changée, sans lecteur). Le taux
  d'un essai de #210 est la somme des `facts_found` sur la somme des `facts_checked`, pas la moyenne
  des taux. — PR de #207
- **`facts_checked` compte chaque fait de chaque affirmation d'une sortie contrôlée, y compris
  d'une affirmation retirée pour une borne.** Pourquoi : le taux mesure ce que le modèle recopie,
  `claims_removed` ce qui est retiré ; appui donné par time-knight : Faithfulness de Ragas met toutes
  les affirmations au dénominateur, et `check_evidence.py` vérifie chaque candidat. Option écartée :
  les seules affirmations dans leurs bornes (un fait exact d'une affirmation trop longue ne
  compterait pas). Limite assumée : les règles propres à l'affirmation (identifiant non déclaré,
  item cité sans fait, texte déguisé) n'entrent pas dans le taux, qui peut valoir 1 avec des
  retraits et se lit avec `claims_removed`. — PR de #207
- **Les séparateurs des motifs CVE et GHSA passent de `[\s-]*` à `[\W_]*`, et un fait sans lettre
  ni chiffre une fois normalisé n'est jamais trouvé.** Pourquoi : `CVE_2026_0001` échappait au
  motif, et le piège de #206 passait sous cette écriture ; une espace ou une chaîne vide serait
  trouvée presque partout, et un item se ferait citer pour un fait qui ne dit rien de lui. Option
  écartée : garder les motifs et la recherche de la spec telles quelles. Complète l'entrée du
  2026-10-15 (« Un fait est un extrait recopié… »), sans l'inverser ; le fait est comparé à l'item
  **qu'il cite**, comme la spec le dit, plus strict que « un item cité » de cette entrée. — PR de
  #207
- **La détection des identifiants lit large (préfixe éclaté, mot de numéro, emphase retirée, sosies
  du préfixe, `o`, `l`, `i` pour des chiffres), et une affirmation dont le texte cache ou déguise
  (marque, point de code privé ou non attribué, remplissage hangul ou braille, mot qui mêle des
  lettres latines à une lettre sosie) est retirée.** Décisions de time-knight sur les revues de #207,
  après un relecteur de sécurité neuf. Pourquoi : chaque écriture que la détection manque laisse
  passer le piège (« la CVE n°2026-0001 n'est pas exploitée », `C`+U+FE0F+`VE`, `СVЕ` cyrillique,
  `CVE-2026-00**01**`) ; « CVE n° » est une tournure française que le modèle écrit sans attaque.
  Options écartées : refuser toute lettre non latine (les titres d'articles portent du grec,
  `β-VAE`, `5 µs`) ; une table complète des sosies UTS #39 (dépendance nouvelle) ; lire `AAAA-NNNN`
  seul comme un identifiant (`2025-2026` le deviendrait). Limites assumées : des faux positifs dans
  le sens sûr (« Le CV en 2026, 0001 candidats ») ; ne sont pas lus `CVE-2026-0001a`, « la faille
  2026-0001 » ni un sosie hors des listes. — PR de #207

## 2026-10-25

### Rangement : les utilitaires partagés dans `core`, l'API IA rangée par rôle

- **`write_file_atomically` (et `REFUSED_FOLDER_SYNC_ERRORS`) passe de `etl/raw_store.py` à
  `core/atomic_write.py`, et `database/dates.py` devient `core/dates.py` ; `core.atomic_write` est
  refusé aux deux API par `tests/architecture/test_apis.py` (`DATA_API_FORBIDDEN_MODULES`,
  `AI_API_FORBIDDEN_MODULES`).** Mission cosmétique décidée par Sabine le 2026-10-25, codée par
  time-knight sur sa délégation. Pourquoi : les deux servent à plusieurs modules (`etl`, `post`,
  `commands`, `database`), et `core` est le vocabulaire commun à toutes les couches (règle 5 de
  `conventions.md` ; déjà recommandé par `docs/refactoring/paquets.md`, point 3 des gains rapides).
  `post` n'importe plus `etl` ni `database` pour écrire un fichier ou une date. Le refus aux API
  garde la règle « une API n'écrit aucun fichier » (règle 7 de `poc.md`) au même niveau
  qu'avant : tant que la fonction vivait dans `etl`, le refus d'`etl` suffisait. Options écartées :
  le nom `core/file_writing.py` (collision avec `etl/file_writing.py`, qui écrit en base) ; laisser
  les API importer `core.atomic_write` (la règle ne tiendrait plus que par un `grep`). — branche
  `refactor/cosmetic-a`
- **Sous `k_b.ai_api`, `fidelity` passe dans `stages/`, `metrics` et `metric_instruments` dans un
  paquet nouveau, `observability/` ; la racine garde le squelette de l'API (`app`, `api_router`,
  `dependencies`, `errors`, `settings`, comme `data_api`), le parcours d'une demande (`digests`,
  comme `etl/pipeline.py`) et le vocabulaire que partagent toutes les couches d'`ai_api`
  (`watch_items`, `deadline`).** Même mission, choix de time-knight. Pourquoi : « un dossier par
  rôle » (`code.md`) et le plan par rôle attendu pour l'API IA (2026-10-17, paquet `data_api`) ;
  la fidélité contrôle une affirmation rédigée, c'est une étape comme `classification` et
  `writing`. Les couches de `AI_API_LAYERS` ne changent pas, seuls les noms des modules. Option
  écartée : `watch_items` et `deadline` dans `stages/` (les connecteurs, plus bas, les importent).
  Limite : la racine garde huit fichiers, dont trois qui ne sont pas du squelette. — branche
  `refactor/cosmetic-a`

### Collecte : un seul nouvel essai, poli envers les sources

- **Tout téléchargement d'une source (`download`) a un seul nouvel essai après un 429, un 5xx, un
  403 qui porte un `Retry-After` ou un échec de connexion ; il attend le `Retry-After` en secondes,
  plafonné à 60 s et jamais moins de 3 s, sinon 5 s, et 60 s pour un 429 de l'API GitHub ; un délai
  dépassé, un autre statut, une erreur servie hors du préfixe de confiance et un quota épuisé
  (`x-ratelimit-remaining: 0`) n'en ont pas, et le quota épuisé note sur l'erreur l'heure de sa
  remise à zéro. La règle vit dans un module à elle, `etl/http_retry.py`.** Demandé par Sabine le
  2026-10-25 (429 et quotas, puis 5xx et connexion sur la recommandation de time-knight, qui l'a
  codé sur sa délégation). Pourquoi : la collecte n'avait aucun nouvel essai (constat du 24/10) ;
  la même règle que l'appel au modèle (`ai_api/connectors/llm_client.py` : un essai de plus,
  `Retry-After` plafonné, pas de nouvel essai sur un délai dépassé), une seule règle par sujet.
  5 s dépassent les 3 s qu'arXiv demande entre deux requêtes ; GitHub demande au moins une minute
  sans `Retry-After` et interdit de retenter avant la remise à zéro d'un quota épuisé
  ([Rate limits for the REST API](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api),
  lu le 2026-10-25). Options écartées : attendre la remise à zéro d'un quota GitHub (jusqu'à une
  heure dans une collecte ; la source échoue, sa date reste, la collecte suivante redemande) ;
  plusieurs nouveaux essais avec attente croissante (une collecte planifiée repasse de toute
  façon) ; la règle dans `http_download.py` (deux rôles dans un fichier). Limites : un 403 sans
  `Retry-After` n'est pas retenté (c'est d'abord un refus, même quand GitHub y met sa limite
  secondaire) ; la lecture du `Retry-After` existe en double, ici et dans `llm_client.py` (la mettre
  dans `core` toucherait l'API IA, hors de cette PR). — branche `fix/source-download-retry`
- **La lecture du `Retry-After` passe dans `core/retry_after.py` (`read_retry_after`,
  `is_retry_after_too_long`) ; la collecte (`etl/http_retry.py`), l'appel au modèle
  (`ai_api/connectors/llm_client.py`) et `kb digest` (`post/ai_api_client.py`) l'appellent.** Lève
  la limite de l'entrée précédente, sur l'accord de Sabine du 2026-10-25 (« ok après la fusion »).
  Pourquoi : trois lectures du même en-tête, chacune à sa façon (`[0-9]+` et une longueur, `[0-9]{1,9}`
  et un motif « trop long », `[0-9]{1,6}`) : une seule règle par sujet, et `core` est le
  vocabulaire commun à plusieurs couches. La règle d'attente reste à chaque client (statuts,
  plafonds, attente par défaut) : elle n'est pas la même pour une source, le modèle et `kb digest`.
  Seul changement visible : `kb digest` affiche tel quel un `Retry-After` de 7 à 9 chiffres, qu'il
  citait entre guillemets. Option écartée : mettre toute la règle du nouvel essai dans `core` (elle
  ne sert qu'à l'ETL, sur les erreurs d'`urllib`). — branche `refactor/retry-after-in-core`

### ETL : chaque module de source construit de la même façon, EXTRACT puis TRANSFORM

- **Chaque module de `etl/sources/` suit une seule forme : son identité (`logger`, `SOURCE_CODE`,
  `FOLDER_PREFIX`, les constantes partagées), puis un bandeau `# === EXTRACT ===` (la requête, la
  classe `…Source` et `fetch`, ses aides), puis `# === TRANSFORM ===` (ce qui est gardé, la
  lecture, la conversion, `READER`) ; `tests/architecture/test_source_modules.py` la tient.**
  Demandé par Sabine le 2026-10-25 (« de l'harmonisation et de l'uniformité ») : savoir expliquer
  le pipeline de n'importe quelle source en s'appuyant sur le code, avec la même carte pour toutes.
  Les bandeaux en toutes lettres, pas en initiales (demande de Sabine). Relevé avant : le squelette
  existait dans la plupart des modules, mais les constantes de la lecture étaient mêlées à celles
  de la requête (arXiv, Zotero, GH Archive), les erreurs toutes en tête, et `read_catalog` de CISA
  après sa conversion. Pur déplacement : chaque définition identique à l'original (arbre
  syntaxique comparé, 367 instructions), aucun commentaire perdu. Pas de bandeau LOAD : le
  chargement est commun à toutes les sources (`etl/load.py`, `database/writers/`). Limites : une
  fonction d'aide que le modèle de la lecture utilise dès sa définition reste avant lui (Zotero,
  clips) ; une fonction que seul `fetch` appelle mais annotée par un modèle de la lecture
  (`check_document` de Zotero) est sous TRANSFORM. Options écartées : un module par bloc
  (`<source>/extract.py`, `<source>/transform.py`), deux fois plus de fichiers pour des modules de
  100 à 450 lignes ; une classe de base commune, quand le `Protocol` du contrat suffit et que les
  formats (Atom, CSV, JSON, HTML, SQLite, BigQuery) n'ont rien d'autre en commun. — branche
  `refactor/source-modules-extract-transform`
- **Les sources GitHub passent dans un paquet `etl/sources/github/` (`api`, `releases`,
  `advisories`, `most_starred`, `most_forked`) ; `tracked_repositories.py` disparaît : la liste
  `TRACKED_REPOSITORIES` va dans `core/config.py`, à côté de son type, `list_packages_by_ecosystem`
  dans `etl/source_kinds.py`, son seul appelant, et `is_repository_name` dans `items.py`, à côté du
  motif `REPOSITORY_NAME` qu'elle complète.** Demandé par Sabine le 2026-10-25 (« un dossier
  `sources/github_…` ») ; la répartition de `tracked_repositories.py` est la recommandation de
  time-knight, acceptée (« version complète »). Pourquoi : un dossier par fournisseur, et le client
  GitHub avec les quatre sources qui l'appellent ; la liste des dépôts suivis n'est pas une aide des
  sources GitHub (les commandes, le pipeline, le load, le transform et la base s'en servent), et
  `core/config.py` annonçait déjà qu'elle y viendrait avec #123. Avance une partie de #123, qui
  reste ouverte pour les autres paramètres. Les noms des dossiers de `raw/` (`github_releases_…`,
  `github_advisories_…`) ne changent pas. Pur déplacement : chaque définition identique, imports
  mis à part. Options écartées : la liste dans la composition de l'ETL (une source ne peut pas
  l'importer, or trois sources GitHub lisent `is_repository_name`) ; le seul regroupement des cinq
  modules, `tracked_repositories.py` laissé en attendant #123. — branche
  `refactor/github-sources-package`

### Configuration : les réglages de la veille rassemblés dans `core/config.py` (#123)

- **Les 14 réglages de la veille sont dans `core/config.py`, chacun préfixé par sa source :
  `ARXIV_` (mots-clés, marge d'annonce, première collecte), `TLDR_` (éditions, pause, première
  collecte), `GITHUB_` (dépôts suivis, écosystèmes, requêtes et taille des tops), `GH_ARCHIVE_`
  (taille du top, fenêtres rattrapées) et `HTTP_` (délai réseau) ; les écosystèmes ne sont écrits
  qu'une fois (`type Ecosystem`, d'où `GITHUB_ECOSYSTEMS`).** Applique la décision de Sabine du
  2026-10-10 (« Configuration ») et la règle de nommage du 2026-10-13 ; demandé le 2026-10-25, plan
  validé. Les faits des API, les formats et les plafonds restent dans le module de la source.
  Valeurs inchangées (relevées avant et après). Deux écarts à l'issue : la requête des plus forkés
  (`GITHUB_MOST_FORKED_SEARCH_QUERY`), venue après #123 avec #264, en plus, d'où 14 réglages et non
  13 ; `GITHUB_RANKING_SIZE` plutôt que `GITHUB_MOST_STARRED_RANKING_SIZE`, la taille étant
  partagée par les deux tops. Limite : c'est toujours un fichier Python ; une configuration hors du
  code (fichier lu au démarrage) serait une autre décision. — branche
  `refactor/watch-settings-in-config`

### Configuration : l'environnement lu à un seul endroit

- **`os.environ` n'est lu qu'à un endroit, `read_environment` de `commands/environment.py`, appelé
  une fois par `cli.py` ; les commandes et les lecteurs reçoivent l'environnement en paramètre
  (`environ: Mapping[str, str]`), chaque lecteur près de son domaine ; un test d'architecture le
  tient (`tests/architecture/test_environment.py`).** Point noté le 2026-10-21 (« un seul endroit lit
  et valide ») ; plan validé par Sabine le 2026-10-25, lecture dans `environment.py` à sa demande.
  Les lecteurs maison (`read_…_or_refusal(environ)`, déjà neuf) sont gardés **pour le moment**,
  sans pydantic-settings (voir les décisions encore ouvertes). `kb` ne charge jamais un `.env`
  lui-même, sans `dotenv` : `uv run --env-file` le fait (un `load_dotenv` chercherait un `.env` en
  remontant les dossiers). **Exception provisoire** : le jeton GitHub reste lu par
  `etl/sources/github/api.py`. Le passer aux sources GitHub, essayé dans la même PR, ajoutait une
  troisième façon de créer une source (instances déclarées, création par la sorte pour GitHub,
  création au cas par cas dans `etl/collected_sources.py` pour Zotero, les clips et GH Archive) ;
  Sabine : « je ne suis pas certaine que ce soit très clean ». Il attend une seule façon de créer toutes les sources qui ont besoin
  de l'environnement, à concevoir à part. Options écartées : tout regrouper dans `core/` (les
  réglages du modèle, des API et des sources mêlés, sans gain) ; la lecture dans `cli.py` (moins
  facile à trouver que dans le module qui porte le nom). — branche `refactor/read-environment-once`

## 2026-10-26

### Fiches de veille : une réponse par item au classement

- **La sortie du classement est un objet avec une propriété obligatoire par item du lot, dans
  son ordre : sa valeur est un sujet de la liste ou `no_suitable_subject` (consigne `classify-2`).
  `no_suitable_subject` est un nom réservé (`NO_SUITABLE_SUBJECT_ANSWER`, `core/config.py`),
  qu'aucun sujet ne peut prendre. Une clé JSON présente deux fois dans une sortie du modèle est
  refusée (contrôle 2, `schema`, `is_json_without_key_twice` dans `llm_client.py`), aux deux étapes.** Plan
  validé par Sabine le 2026-10-26, proposé par time-knight ; Sabine : « pour le moment on met une
  case pour avancer ». Pourquoi : à l'essai 1 de #210 sur la veille réelle (2026-10-26, 268 items,
  gpt-6-luna), le modèle a donné à deux items d'un lot de 50 articles TLDR à la fois un sujet et
  « non retenu », aux deux tentatives ; le contrôle 5 a refusé le lot, et toute la demande a
  échoué (502). Le rejeu du lot l'a montré, par les seuls identifiants. Le mode strict ne pouvait
  pas l'interdire dans des listes : `uniqueItems` n'y est pas pris en charge (OpenAI et Azure).
  Avec une propriété par item, cet état ne peut plus s'écrire. Pydantic garde sans le dire la
  dernière valeur d'une clé répétée, d'où le refus explicite. La valeur dit au modèle pourquoi il
  la choisit (« not suitable category », Sabine), au lieu de `not_retained`. Options écartées :
  dédoublonner par le code (il réparerait en silence ce que le modèle écrit) ; laisser un lot en
  échec sans faire échouer la demande (utile en plus, il ne corrige pas la cause, et les items du
  lot seraient perdus) ; des lots plus petits (la probabilité baisse, le cas reste) ; une phrase
  de plus dans la consigne (une règle en prose ne tient pas) ; un sujet secondaire par item (voir
  les décisions encore ouvertes). Limites tenues par un test, les plus strictes connues : 100
  propriétés d'objet par schéma (Azure), 500 valeurs d'`enum` et 15 000 caractères de chaînes
  (erreurs d'OpenAI rapportées sur son forum) ; au plafond de 50 items et 8 sujets, 50 propriétés,
  450 valeurs et environ 6 400 caractères. Limite assumée : un 10e sujet dépasserait 500 valeurs
  et demanderait des lots plus petits. — PR de #210 (`classify-2`)
- **Le classement distingue trois cas : catégorisé (un sujet), sans sujet adapté
  (`no_suitable_subject`, un jugement du modèle, rendu dans `no_suitable_subject`) et non traité (aucune
  réponse, un raté du modèle, rendu dans le champ nouveau `unanswered` de la réponse). Un item non
  traité ne fait pas échouer le lot ; chaque ligne de métrique du classement compte
  `items_with_subject`, `items_no_suitable_subject` et `items_unanswered`, en JSON et en
  OpenTelemetry ; x + y + z = `items_in`. Le cas y porte partout le nom choisi par Sabine,
  `no_suitable_subject` (« not suitable category », adapté au vocabulaire « sujet »), à la place de
  `not_retained` dans la réponse.** Décision de Sabine du
  2026-10-26 : « Quand il oublie l'item, rien. Du coup à la fin on a x items catégorisés, y items
  avec aucune catégorie adaptée et z items non traités » ; « un item non traité est une forme de
  raté quand même ». Pourquoi : un jugement et un raté sont deux choses ; les confondre ferait
  passer une panne pour une décision, et rendrait impossible à mesurer le seuil « aucun item
  oublié » des essais de #210. Un `items_no_suitable_subject` élevé dira aussi qu'il manque un sujet à la
  liste fermée (Sabine). **Précise** la décision du 2026-10-15 (« La complétude est calculée par
  le code », PR de #203) : un item absent n'est toujours pas un échec, mais il n'est plus confondu
  avec un item non retenu. Options écartées : faire échouer le lot pour un item sans réponse (un
  item perdu ferait tomber toutes les fiches ; proposé un temps dans la même PR) ; le compter
  « non retenu » sans compteur (une panne passerait pour un jugement). La réponse de l'API IA passe
  en version 0.3.0 (`unanswered` ajouté, `not_retained` renommé `no_suitable_subject` ; aucun client
  ne lit ce champ, et `kb digest` ignore ceux qu'il ne connaît pas). Limite :
  un item non traité n'est pas redemandé ; une seconde chance ciblée viendra si les essais en
  montrent. **Une sortie qui ne répond à aucun item du lot (`{}`) est refusée** (`completeness`,
  avec une nouvelle tentative) : elle ne trie rien, et vient d'un fournisseur qui ignore le mode
  strict ; sans ce refus, tout le lot passerait en « non traité » et la demande rendrait un 200
  vide (revue de code `high` de la PR, proposé par time-knight, confirmé par Sabine le 2026-10-26 :
  « Je suis d'accord sur le principe »). Sabine, même jour : la seconde chance ciblée reste une
  option, décidée sur ce que montrent les essais (« en fonction de ce qu'il se passe en vrai »).
  — PR de #210 (`classify-2`)

### Fiches de veille : le nom dit quand un item quitte la fiche

- **Trois champs de l'API IA sont renommés (réponse, ligne de métrique, OpenTelemetry, et les
  structures qui portent le même compte), pour que chacun dise le moment où l'item quitte la
  fiche : `items_dropped` → `items_dropped_before_writing_stage` (écartés par le code avant la
  rédaction : retirés ou disparus à la lecture, avant tout modèle ; au-delà des 60 plus récents
  d'un sujet, après la classification, qui les a vus) ; `digests[].not_retained` →
  `digests[].items_not_retained_in_output` (envoyés au modèle,
  cités par aucune affirmation de sa sortie) ; `digests[].items_uncited` →
  `digests[].items_removed_by_checks` (cités par le modèle, plus cités une fois retirées les
  affirmations hors bornes ou infidèles ; métrique `k_b.digest.items_removed_by_checks`).**
  Décision de Sabine du 2026-10-26, noms choisis par elle en séance avec time-knight. Pourquoi :
  les trois listes ont toutes des items absents des sources de la fiche ; seul le moment les
  distingue. Options écartées : `not_used`, `not_used_for_digest`, `not_retained_for_digest` (ils
  décrivent aussi les items retirés par les contrôles) ; `never_cited`, `not_cited_in_output` et
  `not_cited_by_model` (« not cited » se lit comme une faute de citation, un fait écrit sans sa
  source, Sabine) ; `not_used_by_llm_choice` (le modèle est borné à 12 affirmations, ce n'est pas
  un libre choix) ; `not_selected` (la sélection est celle des 60 items les plus récents, par le
  code) ; `dropped_by_checks` (confondu avec `items_dropped`) ; `rejected_by_controls` et
  `removed_by_checks` sans préfixe (ce sont les affirmations qui sont retirées, et
  `claims_removed` est à côté) ; `items_dropped_by_code` (les contrôles sont du code aussi) ;
  `items_dropped_before_model` (faux pour les items au-delà de 60, que la classification a vus ;
  relevé par la revue `high` de la PR) ; `items_dropped` gardé (ne dit pas le moment) ;
  `before_redaction` (faux ami : *redaction* veut dire caviardage en anglais). Les comptes
  internes de la lecture (`WatchReading`) et de la sélection (`WritingSelection`) gardent
  `items_dropped`, ce que leur étape écarte ; seule leur somme prend le nom public (Sabine, même
  jour, sur la même revue : la lecture ne connaît pas la rédaction).
  L'API IA passe en version 0.4.0 ; aucun client ne lit ces champs (`kb digest` les ignore). La
  spec dit aussi « aucun sujet ne convient » (`no_suitable_subject`) là où elle disait « non
  retenu ». — branche `refactor/name-when-an-item-leaves-the-digest`

## 2026-10-27

### API IA : le parcours dans `digests.py`, chaque étape dans son module

- **`ai_api/digests.py` ne garde que le parcours d'une demande (`build_digests`, `FailedSubject`,
  `DigestsResult`) ; le détail de chaque étape va dans son module. `classify`, `Classification` et
  `ClassificationFailure` passent dans `stages/classification.py` ; `to_digest`, ses trois
  fonctions d'aide, `SOURCE_URL_SCHEMES`, `Digest`, `DigestClaim` et `DigestSource` dans un module
  nouveau, `stages/checking.py` ; `Stage` et `StageCall` dans un module nouveau à la racine,
  `ai_api/stage_calls.py`. Déplacement à l'identique (arbre syntaxique comparé, définition par
  définition) : seuls les imports changent.** Décision de Sabine du 2026-10-27 : « chaque étape de
  traitement des watch donne accès au détail du code de l'étape dans le module python dédié ».
  Pourquoi : `digests.py` gardait le détail de deux étapes (la boucle des lots et le décompte des
  trois cas du classement ; les bornes, la fidélité et l'assemblage du compte rendu), contre deux
  règles de `code.md` (« Un module se lit comme une table des matières », « Un parcours s'écrit
  comme une suite d'étapes nommées, chacune dans son module ») ; et c'est le préalable des traces
  (un span par étape, chaque étape dans son module). `stages/` se lit désormais classification,
  writing, checking (classer, rédiger, contrôler), `fidelity.py` restant le détail du contrôle.
  `stage_calls.py` est à la racine parce que plusieurs couches le lisent (étapes, parcours,
  observabilité, schémas), comme `watch_items` et `deadline` (2026-10-25). `AI_API_LAYERS` reçoit
  deux couches : `stage_calls` entre les connecteurs et les étapes, `stages.checking` entre
  `stages.fidelity` et `digests`. **Révise en partie** 2026-10-18, « API IA : organisation par
  rôle » (#242), qui décrivait `stages/` comme « les étapes qui appellent le modèle » : `fidelity`
  (2026-10-25) et `checking` n'en appellent aucun. Options écartées : `to_digest` dans
  `fidelity.py` (proposé d'abord, écarté avec Sabine : deux niveaux de détail dans un module) ;
  `StageCall` dans `llm_client.py` (il décrit une étape, pas une connexion) ou dans
  `watch_items.py` (plus bas que `llm_client`, alors que `StageCall` contient un `LlmCall`) ;
  laisser `StageCall` dans `digests.py` (une étape importerait le parcours qui l'appelle, refusé
  par `tests/architecture/test_apis.py`) ; réexporter les types depuis `digests.py`. Limites : la
  racine d'`ai_api` passe à neuf fichiers ; `build_digests` construit toujours en ligne le
  `StageCall` de la rédaction (une vingtaine de lignes), laissé à une autre PR. — branche
  `refactor/one-module-per-digest-stage`

### Traces : `POST /digests` vers Grafana Cloud, sans texte (#345)

Décisions du plan des traces (time-knight, version 3 du 27/10, relue deux fois), sur lequel Sabine
a donné son « go » le 2026-10-27 ; celles de Sabine sont dites comme telles.

- **Les traces de `POST /digests` partent vers Grafana Cloud seul, en bac à sable comme en
  production, par l'exportation des métriques ; la PR de #345 envoie les spans et les raisons, sans
  aucun texte, et le contenu (consigne, items, réponse) viendra par une PR à part.** Décision de
  Sabine du 2026-10-27 à 11:23 UTC (« commençons par cela »), sur la recommandation de time-knight
  (recherche du 27/10). Pourquoi, selon la recommandation : l'essai 1 de #210 (26/10) n'a pu être
  compris que par un script de rejeu ; Grafana Cloud reçoit déjà les mesures, et relie un span à ses
  journaux (« Logs for this span »). Options écartées : Jaeger en local et Honeycomb en production
  (deux outils, un sous-traitant de plus) ; Grafana pour le système et Langfuse pour la couche IA
  (un sous-traitant de plus ; Langfuse va dans la suite du projet) ; l'image `otel-lgtm` en local.
  Limite assumée : une trace part chez un tiers dès le bac à sable. — branche
  `feat/trace-digest-steps`
- **Les spans sont ouverts en ligne par une façade, `ai_api/tracing.py`, que chaque étape reçoit
  par `tracing=`, comme `Deadline` ; le défaut, `TRACING_OFF`, n'enregistre rien, et un test lit le
  code : dans `ai_api`, tout appel à une fonction qui prend `tracing` le lui passe.** Pourquoi : un
  span ouvert en ligne voit un 500 et se lit en direct ; la façade garde OpenTelemetry hors des
  étapes (aucune n'importe `SpanKind` ni `StatusCode`). Un span n'enregistre jamais d'exception :
  un échec pose l'état nommé, ou le nom du type, dans `error.type`, le statut sans description.
  Options écartées : des spans construits après coup depuis les résultats (première version du
  plan : un 500 y perd toute sa trace, rien ne se voit en direct, et il faudrait des instants dans
  six types métier) ; l'API d'OpenTelemetry appelée dans les étapes, avec un fournisseur global ; la
  racine dans un middleware (elle perdrait l'état nommé, et `log_request` vit dans `core`, que
  partage l'API de données) ; le span `SERVER` natif de FastAPI (il porte `url.path`, `url.query` et
  `server.address`, et reprend un `traceparent` reçu), contre le skill `fastapi` du dépôt, comme
  pour #162. **Révise en partie** 2026-10-24, « Métriques : l'export OpenTelemetry de l'API IA »
  (#162) : OpenTelemetry s'importe désormais dans quatre modules (`tracing.py` et
  `connectors/trace_export.py` en plus) ; l'intention de Sabine (« limiter la "pollution" du code
  par opentelemetry ») reste tenue : l'app, le routeur et les étapes ne voient que `Tracing` et
  `TraceExport`, et le test d'architecture garde la liste. Limites assumées : un 401 et un 422 n'ont
  pas de trace ; une erreur après le `return` de la route laisse une racine à 200. — branche
  `feat/trace-digest-steps`
- **Un span `chat <model>` par requête HTTP envoyée au modèle, et non un par appel.** Écart assumé
  à la convention GenAI, qui regroupe les relances d'une erreur passagère : K-B relance après une
  attente, avec la même consigne, ou après un contrôle raté, avec un rappel, et chaque tentative a
  son état, ses jetons et son contrôle refusé. Le span porte `gen_ai.prompt.name` et
  `gen_ai.prompt.version` (l'étape et la version de sa consigne), pas `server.address`. Option
  écartée : un span par appel, les tentatives en attributs. — branche `feat/trace-digest-steps`
- **Le pourquoi d'une affirmation retirée : des codes fermés (`out_of_bounds`,
  `fact_not_found:<fait>:<item>`, `undeclared_identifier`, `cited_item_without_fact`,
  `disguised_text`), un enregistrement de journal OTLP `gen_ai.evaluation.result` par affirmation,
  rattaché au dernier `chat` de sa rédaction et daté de sa fin.** Pourquoi : un journal, parce
  qu'OpenTelemetry déprécie l'API des événements de span ; sans texte, la règle 5 de `poc.md`
  suffit telle quelle ; rattaché par le contexte du span fermé (`SpanRef`), parce que les contrôles
  tournent après la fin de l'appel. Options écartées : des événements de span ; deux évaluations,
  `k_b.claim_bounds` et `k_b.fidelity` (plan v3). **Ce dernier point est un choix de time-knight au
  code, validé par Sabine le 2026-10-27 (« je valide pour le moment. On verra à l'usage »)** : une
  affirmation hors bornes et infidèle aurait donné deux enregistrements, alors que le critère de
  #345 en demande un par affirmation ; une seule évaluation, `k_b.claim_checks`, dont les codes
  disent quel contrôle a refusé. Limite assumée : Grafana ne filtre plus par le nom de
  l'évaluation, mais par le contenu de l'explication. — branche
  `feat/trace-digest-steps`
- **L'export des traces reprend l'URL de base et l'en-tête des métriques (`/v1/traces`,
  `/v1/logs`), avec un jeton à trois droits ; 3 s par envoi ; tous les spans gardés ; 2 048 octets
  par attribut ; une seule ressource pour les trois fournisseurs ; les journaux du SDK filtrés sur
  quatre noms ; et à l'arrêt, les trois fournisseurs en même temps.** Pourquoi : le point d'entrée
  OTLP de Grafana Cloud reçoit les trois signaux, distingués par leur chemin, sans réglage nouveau ;
  un arrêt envoie au plus deux fois (l'envoi
  en cours, puis le reste), d'où max(2 × 3, 2 × 3, 5) = 6 s, sous les 10 s de `docker stop` ; une
  demande fait quelques dizaines de spans, et celle qui échoue est celle qu'on veut lire ; Grafana
  Cloud Traces coupe chaque attribut à 2 Ko, et le SDK compte des caractères, pas des octets. Seul
  `trace_export.py` importe les modules privés du SDK et de l'exporteur (un test le tient).
  La file d'attente est d'un seul lot (512) : avec la file par défaut du SDK (2 048, par lots de
  512), un arrêt pouvait envoyer quatre lots après celui en cours (revue de code, tranchée par
  time-knight). Et chaque arrêt tourne dans un fil à part, attendu 6 s au plus puis laissé : le SDK
  ne borne pas le total d'un envoi, son délai valant pour chaque attente de la connexion, et son
  arrêt n'en prend aucun (seconde revue de code). Options écartées : 5 s comme les métriques (2 × 5 atteint les 10 s) ; un
  échantillonnage ; un arrêt l'un après l'autre (les délais s'additionnent) ; la file par défaut.
  Limites assumées : si Grafana répond en plus de 3 s, des lots sont perdus en marche normale, avec
  une ligne de l'exporteur ; au-delà de 512 en attente, le SDK abandonne le plus ancien ; un arrêt
  laissé au bout de 6 s perd ce qu'il n'a pas envoyé. — branche
  `feat/trace-digest-steps`
- **Grafana reçoit désormais, dans les traces, le sujet, le `request_id`, les identifiants des items
  et les codes des contrôles.** Décision de Sabine du 2026-10-27 (« je valide »). **Inverse**, pour
  les traces, la ligne du registre qui l'interdisait (« Envoi des mesures à Grafana Cloud »,
  données envoyées) ; les mesures gardent leur règle. Pourquoi : sans eux, une trace ne dit ni quel
  sujet, ni quelle demande, ni quel item ; aucun n'est une donnée personnelle (liste fermée, UUID
  tiré par le serveur, entiers internes). Inscrit au registre. — branche `feat/trace-digest-steps`
- **OpenTelemetry est borné sous 1.46 (`>=1.45.1,<1.46`) sur ses trois paquets.** Décision de Sabine
  du 2026-10-27 (« je valide »). Pourquoi : les journaux et leur exporteur sont des modules privés
  qui bougent d'une version à l'autre (dépréciations depuis la 1.35), et rien ne figeait leur
  version. Limite assumée : la montée de version se fait à la main, en relisant ces modules. —
  branche `feat/trace-digest-steps`

## 2026-10-28

### Traces : le contenu des appels au modèle, sous réglage (#347)

Décisions D1 et D2 de Sabine (27/10), sa précision de D1 (28/10), et les choix du plan court de la
PR 2 (time-knight, relu par un sous-agent, validé par Sabine le 2026-10-28) ; celles de Sabine sont
dites comme telles.

- **Le contenu d'un appel au modèle (la consigne, les champs des items envoyés, la sortie) part vers
  Grafana Cloud, dans un enregistrement de journal OTLP `gen_ai.client.inference.operation.details`
  par requête, rattaché à son `chat`, sous le réglage `KB_TRACE_CONTENT` : `none` par défaut,
  `anomalies`, ou `all`, refusé au démarrage en production.** Piste de Sabine du 2026-10-26 (« c'est
  important de connaître ce qui a fait le choix du llm surtout en phase de dev. Mais aussi en prod
  quand quelque chose sort des clous ») ; texte de l'exception à la règle 5 de `poc.md` validé par
  Sabine le 2026-10-27 (D2, « je valide D2 »). **Inverse** le critère de #163, « texte des prompts
  jamais émis » (réécrit le 2026-10-27 avec l'accord de Sabine), et la phrase de l'entrée du
  2026-10-27 « sans aucun texte » pour ce seul enregistrement ; ce qui a changé : l'essai du 27/10
  a retiré 37 affirmations, dont les codes ne disent pas si le refus était juste. Options écartées :
  le contenu en attributs de span (Grafana Cloud Traces les coupe à 2 Ko) ; un stockage externe
  avec une référence sur le span, l'usage que la convention recommande en production pour ses
  droits d'accès séparés (un second service à tenir pour une utilisatrice) ; Langfuse (un
  sous-traitant de plus, suite du projet) ; `OTEL_INSTRUMENTATION_GENAI_CAPTURE_CONTENT` (K-B refuse
  toute variable `OTEL_*`). La règle 8 de `poc.md` (« une sortie hors schéma n'est jamais écrite »)
  vise le coffre et la réponse de l'API, à cause de l'injection ; elle reçoit une phrase qui le dit
  (accord de Sabine du 2026-10-28, sur la revue de sécurité) : le contenu envoyé, sortie refusée
  comprise, reste une donnée, jamais une consigne, en chaîne échappée dans un corps de journal. Le
  texte de D2 est corrigé le même jour avec son accord : le masquage retire les adresses web
  partout, mais les logins `@…` des seules notes d'une release, et jamais une adresse mail (erreur de
  la proposition de time-knight du 27/10, trouvée par la revue de sécurité). Limites
  assumées : des données personnelles (un login dans un nom de dépôt, un nom en texte libre) partent
  chez un sous-traitant, dont le DPA doit être signé avant le premier envoi ; leur purge n'est pas
  codée par K-B, c'est la rétention de Grafana Cloud (14 jours dans l'offre gratuite) ; le contenu
  se lit avec les traces, sans droits séparés. — branche `feat/trace-model-content`
- **Un appel est en anomalie s'il finit en `llm_invalid_output`, `llm_truncated`,
  `llm_content_filtered` ou `llm_timeout`, s'il a été relancé après le refus d'un contrôle, ou si
  son lot de classement a laissé des items sans réponse ; `anomalies` envoie chacune de ses
  requêtes.** Décision de Sabine du 2026-10-27 (D1, « je valide D1 »), sur la proposition de
  time-knight modifiée par lui. Pourquoi : le contenu explique ces cas. Ne sont pas des anomalies :
  `llm_rate_limited` et `llm_unavailable`, dont la cause est le fournisseur (minimisation) ; une
  affirmation retirée (les 8 sujets en avaient à l'essai du 27/10 : `anomalies` vaudrait presque
  `all`), dont le pourquoi s'enquête en bac à sable avec `all`. **Précisée par Sabine le
  2026-10-28** (« Pas une anomalie ») : un `llm_timeout` posé par le délai de la demande avant la
  relance d'un 429, d'un 5xx ou d'une erreur de transport n'en est pas une, pour la même raison ;
  dans un projet courant, ce cas se lit sur le span en erreur et les métriques. **Étendue par
  Sabine le même jour** (« Pas une anomalie », sur les deux revues de la PR) à la relance qui part,
  son délai réduit au temps restant, puis expire : un `llm_timeout` dont la première tentative a eu
  un 429, un 5xx ou une erreur de transport n'est pas une anomalie (`LlmCall.first_outcome`). Un
  délai dépassé dès la première tentative (le modèle trop lent) en reste une. Option écartée pour
  ce cas : D1 à la lettre (aucun code, mais les items partent quand le fournisseur limite près du
  délai). Un refus de contrôle prime : relancé puis en 429 ou en 5xx, l'appel est en anomalie. D1
  vit dans `connectors/llm_client.py` (`is_anomaly`, `trace_contents`), non dans `tracing.py` comme
  l'issue le prévoyait : les couches interdisent à `tracing.py` d'importer `LlmCall`. Variante
  écartée pour l'instant : envoyer en production le texte des seules affirmations retirées. À
  rejuger après #210. — branche `feat/trace-model-content`
- **Le corps de l'enregistrement est une chaîne JSON aux trois clés de la convention
  (`system_instructions`, `input_messages`, `output_messages`), coupée au-delà de 200 000 octets en
  donnant à chaque texte la même longueur, la plus grande qui tient.** Choix de time-knight (plan
  validé par Sabine le 2026-10-28). Pourquoi : Loki refuse une ligne de plus de 256 Ko, et la ligne
  qu'il reçoit est ce corps même, dont K-B mesure les octets ; la structure garde le sens d'un
  contenu coupé. Options écartées : un dictionnaire, que le récepteur convertit en JSON avec son
  propre échappement (taille non garantie) ; ne couper que le message utilisateur (le plus long en
  pratique, pas en garantie). `output_messages` est vide sans sortie, le corps d'une erreur pouvant
  citer l'entrée. — branche `feat/trace-model-content`
- **`KB_TRACE_CONTENT` se lit avec les autres variables de l'export, et se refuse posé sans
  l'export ; les textes ne sont gardés dans un appel (`LlmCall.contents`) que si le réglage n'est
  pas `none`, et jamais dans son `repr`.** Choix de time-knight (plan validé par Sabine le
  2026-10-28). Pourquoi : `KB_DEPLOYMENT_ENVIRONMENT`, dont dépend le refus en production, n'est lu
  que là ; posé sans export, le réglage garderait des textes en mémoire pour rien et dirait le
  contraire de ce qui part, comme `KB_OTLP_HEADERS` sans `KB_OTLP_ENDPOINT`, déjà refusé. Options
  écartées : une lecture à part dans `trace_export.py` (une branche de refus et un paramètre de
  plus) ; accepter le réglage sans export ; descendre un drapeau dans les trois fonctions qui lisent
  la réponse, la sortie restant de toute façon en mémoire dans `call_model`. —
  branche `feat/trace-model-content`

### Codes de sortie de kb : SIGINT (#352)

Décision de Sabine du 2026-10-28 (issue et PR à part, après #351), sur le plan de time-knight relu
par un sous-agent et validé par elle (« go »).

- **Sur SIGINT (Ctrl-C), `kb` journalise une ligne datée, `kb stopped by SIGINT`, et sort
  normalement avec le code nommé 130, `STOPPED_BY_SIGINT`, après le même nettoyage que pour
  SIGTERM ; `kb serve-data` et `kb serve-ai` gardent l'arrêt d'uvicorn, en 0.** Pourquoi : un
  Ctrl-C imprimait toute la trace de Python, hors du journal daté (essai de Sabine du 2026-10-28) ;
  `cli.py` attrapait SIGTERM et `Exception`, mais `KeyboardInterrupt` n'est ni l'un ni l'autre. 130
  est 128 + 2, comme 143 est 128 + 15 (entrée « Codes de sortie de kb » du 2026-10-18). La ligne
  dit le signal observé, qui vient aussi de `kill -INT` (`code.md`, « Journalisation »). Le
  nettoyage était déjà là : l'import, l'écriture atomique, la création de la base et la copie de
  Zotero défont leur travail sur toute `BaseException`. Option écartée : finir le processus par
  SIGINT (`os.kill` sur soi-même, comme Python le fait depuis la 3.8 pour un Ctrl-C non attrapé,
  [bpo-1054041](https://bugs.python.org/issue1054041)), pour qu'un script bash qui lance `kb`
  s'arrête aussi ; sous `uv run kb …`, la façon de lancer `kb` du README, uv sort lui-même
  normalement en 130 (vérifié le 2026-10-28), et le gain ne vaudrait que pour `.venv/bin/kb` lancé
  directement, au prix d'une sortie standard à vider avant le signal et d'un remplacement dans les
  tests. Limites assumées : un Ctrl-C reçu avant que `kb` n'ouvre son journal (l'import des
  modules, la lecture de l'environnement) et `kb openapi`, qui sort avant, gardent la trace de
  Python ; un script bash qui lance `.venv/bin/kb` continue après un Ctrl-C (vérifié le 2026-10-28
  avec un programme qui sort en 130 sur `KeyboardInterrupt`). `kb create-db` sort en
  130 sur SIGINT mais n'a toujours pas de gestionnaire de SIGTERM (limite de l'entrée du
  2026-10-18). **Un second Ctrl-C pendant l'annulation peut la couper** (un fichier de base à
  moitié créé, un temporaire caché) : SIGTERM ignore un second signal, SIGINT non, comme sur `main`
  avant cette PR. Laissé ainsi par Sabine le 2026-10-28 (« ok », sur la revue de code) : un Ctrl-C
  suppose quelqu'un devant l'écran, qui voit l'erreur. Sur Azure, sans personne, l'arrêt vient par
  SIGTERM, puis SIGKILL 30 s plus tard
  ([Application lifecycle management in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/application-lifecycle-management),
  lue le 2026-10-28) ; le signal que reçoit un job arrêté n'y est pas écrit : à vérifier à la mise
  en ligne du 08/11, par la ligne `kb stopped by …` du journal après un `az containerapp job stop`.
  Option écartée : un gestionnaire de SIGINT qui ignore le second, comme pour SIGTERM. —
  branche `fix/stop-on-sigint`

## 2026-10-29

### Commandes : le retour console sans tableau (#359)

Décisions de Sabine du 2026-10-29, après avoir vu en vrai les tableaux de #291 (PR #358) ; plan de
time-knight relu par un sous-agent et validé par elle.

- **`kb collect`, `kb import` et `kb write-tops` finissent sans tableau ; `kb digest` garde le
  sien (#357).** **Inverse** les tableaux de #291 (décisions de Sabine du 2026-10-28 et du
  2026-10-29 au matin, PR #358) : pour collect, « la version initiale avec source et ok me convient
  mieux » ; pour write-tops, « pas besoin de tableau » ; pour digest, vu en vrai le même matin,
  « Il me convenait. Je veux la garder comme ça ». Ce qui reste de #358 : les lignes de journal
  (`collection started: N sources selected`, le départ et la fin de chaque source, les durées,
  `import started` et `import finished`). Ce qui est retiré, parce qu'il ne servait qu'aux
  tableaux : les comptes par source de l'import (`SourceImport`, `count_by_source`), le nombre de
  bruts écrits par source dans le résultat de la collecte (`raw_file_counts`), et l'alignement à
  droite de `render_table`.
  - **collect** reprend le rendu d'avant #291 : `<source>: ok` ou `failed (<type>)`, puis
    `<source>: skipped (<réglage>)`, puis `collection_state: failed (<type>)` si l'état n'est pas
    écrit. Le nombre de bruts écrits par une source collectée est au journal seulement ; celui
    d'une source en échec au milieu de ses pages n'est plus donné, comme avant #291.
  - **import** affiche une ligne :
    `import: N raw read, N written, N trend rows, N left out, N rejected, N withdrawn`. Une ligne de
    journal nouvelle, `import log kept: '<nom>'`, dit où lire les rejets, choix de Sabine : sur un
    import normal, aucune ligne ne nommait le journal d'import, que seul `Log:` donnait. Elle
    n'en cite que le nom, comme `etl/load.py` : le chemin nomme le dossier des données.
  - **write-tops** journalise son départ et sa fin, puis affiche une ligne par top, dans cet ordre
    de priorité : `failed (<type>)`, ou `failed (ranking_unreadable)` pour un relevé illisible ou
    mal nommé ; `ok, N sheet(s) written` ; `ok, 0 sheets written, the sheet of the day already
    exists` ; `no ranking`. Les trois cas de Sabine : « ça marche ça écrit », « ça existe déjà, ça
    n'écrit pas », « ça foire une erreur ». Suivent `Older raw files deleted: N` et
    `Sheets vault path: veille/tops/`. Le type d'une erreur est affiché seul, jamais son message,
    qui nomme le coffre. Le code de sortie ne change pas.
  - **Une ligne vide avant et après le résultat** dans les trois commandes. Celle d'avant le
    sépare du journal, comme pour digest : c'est la proposition de Sabine, « une séparation entre
    le retour log et le print en console ». Celle d'après le sépare de la ligne de make après un
    échec (`make: *** [collect] Error 4`), autre idée de Sabine. Une ligne vide écrite par le
    `Makefile` en cas d'échec a été écartée au profit de la sienne, plus simple.
    Limite : un arrêt avant tout résultat (code 2) n'imprime rien.
    `kb digest` finit lui aussi son bilan par une ligne vide, et son titre `Digest summary` est
    souligné de `-`, pour qu'il se lise comme le titre du bloc (demandes de Sabine) ; son tableau ne
    change pas. Écartés : un soulignement de `=`, qui l'aurait distingué de la règle du total ; les
    capitales ; le gras ANSI, qu'il faudrait réserver au terminal.
    Écartés : un titre au-dessus du résultat, plus long que la ligne de l'import ; une règle
    `-----`, qui sépare le total d'un tableau dans digest.

  Options écartées :
  - le bilan de l'import en ligne de journal, pour qu'il entre dans `kb.log` : la règle 3 de
    `conventions.md` donne le résultat d'une commande à `print`, le déroulé à `logger` ;
  - le tableau de write-tops, validé le matin du 2026-10-29, avant que Sabine renonce aux autres ;
  - un revert de #358 : il retirait aussi les lignes de journal gardées, à recoder ensuite.

  Limites assumées :
  - **write-tops imprime ses lignes une fois tous les tops finis**, comme collect : un SIGINT ou
    un SIGTERM pendant le second top fait perdre la ligne du premier.
  - **`Older raw files deleted` manque quand un top a été arrêté par une erreur** : la commande
    ne sait pas si l'erreur est venue pendant ses suppressions, la dernière étape d'un top. C'était
    la règle de l'ancien bilan de l'import. L'erreur est au journal.

  — PR de #359

### Collecte : l'échec prévu d'une source, sans sa trace Python (#361)

Décisions de Sabine du 2026-10-29, après un essai réel sur main d490346 (un coffre sans
`Clippings` : une ligne claire, puis 11 lignes de trace) ; plan de time-knight relu par un
sous-agent et validé par elle.

- **Une erreur prévue d'une source est journalisée sur sa ligne seule, sans trace ; toute autre
  garde sa trace.** Prévue : `ExpectedSourceError` (`etl/source_contract.py`), à laquelle les 11
  erreurs nommées des sources sont rattachées, et les erreurs réseau (`URLError`, dont `HTTPError`
  pour un statut HTTP refusé ; `ConnectionError` ; `TimeoutError`), tuple `EXPECTED_SOURCE_ERRORS`
  (`etl/extract.py`). Pourquoi (raison présentée à Sabine avec l'avant/après) : la trace n'apprend
  rien d'un échec attendu, dont le message dit tout ; elle reste là où une faute est à chercher
  dans le code. Écarté : la trace dans `kb.log` seulement (choix (2), non retenu par Sabine, sans
  raison dite). Le bilan, le code de sortie et la date de dernière collecte ne changent pas. Garde
  la décision du 2026-10-14 (la trace suit sa ligne datée) ; change ce que `specs-collecte.md`
  disait de toute panne d'une source (« avec sa trace »).
- **Une page refusée sur ce qu'elle contient lève `PageRefusedError`, fille de `ValueError` ; tout
  autre `ValueError` garde sa trace** (choix (a) de Sabine). Convertis : les refus de page qui
  remontent de `fetch` à la collecte (`all_items_invalid`, `empty_catalog`, réponse trop grande, les
  deux classements en entier, arXiv, CISA, releases, advisories, `not_the_edition_of_the_day` de
  tldr). Restent `ValueError` les bugs, réglages et états faux (préfixe de confiance, segment de
  chemin, dernier jour de collecte après aujourd'hui). Fille de `ValueError` : l'import rejette
  toujours la page qu'il ne lit pas (`raw_reading.py`). Écartés, parce qu'un bug dans un lecteur
  (`int('x')`) perdrait sa trace : (b) compter tout `ValueError` comme prévu ; convertir tout
  `ValueError` levé pendant `fetch` (proposé par la revue de code). Effet voulu : le type affiché
  devient `PageRefusedError` dans la ligne de journal, le bilan (`failed (PageRefusedError)`),
  `import-log.jsonl` et le journal de `kb write-tops`.
- **Sur la ligne d'échec d'une source, le message et les notes sont cités jusqu'à 300 caractères,
  pas 100** (`MAX_QUOTED_FAILURE_LENGTH` ; `quote_value` prend la longueur en paramètre et reste la
  seule fonction de la règle 3). Pourquoi : sans trace, la ligne est la seule copie du message ; à
  100, la fin d'un message long se perdait (celui de Zotero va jusqu'à 200 caractères : constat de
  la revue de code, correction acceptée par Sabine). Écarté : garder 100 partout.
- **Le message d'un dossier `Clippings` absent donne son remède** : `…; create it, or check
  KB_VAULT_DIR` (avec le choix (1) de Sabine). Un contrôle avant la collecte a été déconseillé par
  time-knight : clipping est une source locale, et la collecte ne s'arrête pas sur l'échec d'une
  source.

  Limites assumées :
  - **Gardent leur trace** : `JSONDecodeError` des lecteurs GitHub, `UnicodeDecodeError` et
    `csv.Error` de CISA, les erreurs de BigQuery et de google-auth, les `OSError` hors réseau
    (coffre, `zotero.sqlite` absent, `raw/`), `ssl.SSLError` et `IncompleteRead` pendant une
    lecture, l'état non écrit (`extract.py`) et l'exception non traitée (`cli.py`). À rouvrir si
    l'un apparaît en vrai.
  - **Un délai de BigQuery** lève un `TimeoutError` souvent sans message : sa ligne dit la source
    et le type, pas l'étape qui a attendu.
  - **Un 4xx dû à un bug de requête perd sa trace** : la ligne nomme la source, et chaque source n'a
    qu'une sorte de requête.

  — branche `fix/collect-expected-errors-without-traceback`

## 2026-10-30

### Tendances : un compte rendu deux fois par semaine, orchestré par l'API IA

Décisions de Sabine du 2026-10-29 (heures UTC), sur une conception de time-knight (architecte en
sous-agent, rendue vers 19:16Z ; relecture en sous-agent vers 19:50Z), plan approuvé le soir même.
Contrat : [tendances.md](../tendances.md). Le pourquoi est celui de Sabine quand il est entre
guillemets ou attribué ; sinon, celui de la conception qu'elle a approuvée.

- **Un compte rendu des tendances de GH Archive, deux fois par semaine, dans le coffre :
  `veille/tendances/<date>.md`** (rythme ~17:00, depuis la fin du compte rendu précédent ; lieu
  ~17:20). Pourquoi : la table `trend` n'est rendue nulle part. Le coffre reste le seul lieu où K-B
  écrit (« Coffre : organisation », 2026-10-19, inchangé) ; `tendances` devient un nom réservé sous
  `veille/`, comme `tops`. En v1, `kb trend-report` est lancé à la main, comme la collecte (« POC du
  25/10 », décision 3) ; la planification vient avec la mise en ligne.
- **Les fenêtres glissantes de 3 jours restent ; la collecte ne change pas** (13:41). Le compte
  rendu est du **post-traitement** : rien de ce qu'il lit sur GitHub n'est gardé, ni brut ni base
  (~17:50).
- **Ce que disent les textes** (16:53) : trajectoire, secteur (topics), rattachement aux sujets de la
  veille, prudence en faits et non en verdicts, licence ; résumé du README attribué à l'auteur,
  tronqué ; une version récente du dépôt n'est pas retenue ; aucune commande ni bloc de code en
  sortie.
- **V1 sans recomptage par GitHub : les comptes de GH Archive seuls, avec leur limite écrite**
  (~17:25). La limite dite alors, « 1 à 2 % des étoiles vues », est remplacée par la mesure du
  2026-10-29 : environ 1 % ([specs-collecte.md](../specs-collecte.md), « GH Archive sur BigQuery »).
  Écarté pour la v1 : recompter le top 100 par GitHub (« Hors v1 » du contrat).
- **Une chaîne fixe en 4 temps, pas un agent** (vision ~17:40, chaîne ~18:55) : le modèle choisit,
  le code lit GitHub, le modèle écrit, le code enregistre. Une **fiche légère** GitHub de chaque
  candidat est lue avant le choix, le README des seuls choisis après (~18:50). Écarté : un agent qui
  choisit ses lectures (piste après le 08/11).
- **Quatre critères (durable, nouveau, en accélération, sujet de la veille), au plus 5 dépôts
  choisis, sur les étoiles seules** (~19:00). Les forks viendront ensuite, avec un filtre à décider
  sur les premiers vrais tops (décisions encore ouvertes). **Durable** est jugé sur la période et les
  2 fenêtres qui la précèdent (19:16–19:26). Le code recalcule le rang des étoiles (`stars_gained desc,
  repository_id asc`), parce que `GET /trends` départage par les forks ; le code rend les faits
  (rangs, critères, licence, dates, étoiles totales), le modèle n'écrit que 4 textes.
- **L'API IA orchestre ; un client GitHub neuf ; un second jeton, `KB_AI_GITHUB_TOKEN`**
  (19:16–19:26). Pourquoi : l'API IA n'importe ni `etl` ni les sources (`tests/architecture/`), et
  le même parcours que `kb digest` → `POST /digests` garde l'API IA sans état. Le second jeton est du
  même compte : la limite de 5 000 requêtes par heure est par compte (conditions de GitHub,
  `specs-collecte.md`). Écarté : `kb` lit GitHub (`post` n'importe ni les sources ni les API) ;
  réutiliser le client de la collecte (couches).
- **« Propriétaire récent » retiré de la v1** (19:16–19:26) : c'est la seule donnée qu'il aurait
  fallu lire sur une personne (`GET /users/{owner}`).
- **Le code garde un registre des comptes rendus, en fichier : `KB_DATA_DIR/trend_reports.json`**
  (19:33 : « Je préfèrerais que le code garde un registre » ; fichier, 19:43). Une entrée par compte
  rendu (fenêtres, fichier, date, `request_id`, modèle), sur le modèle de `collection_state.json`,
  écrite par `write_file_atomically` ; registre illisible = arrêt. Écarté : lire la période dans
  l'en-tête du dernier compte rendu (proposé vers 19:20, remplacé à 19:33) : le coffre resterait lu
  par K-B. Une table viendra si une interface web liste l'historique.
- **Un choix du modèle en échec donne un compte rendu factuel**, avec « choix non fait » et la
  raison ; le registre le note et la période avance (~19:45). Remplace le 502
  `llm_invalid_output` que prévoyait la conception. Une rédaction en échec ne retire que les textes
  de son dépôt.
- **Plafonds** : 15 fenêtres (`GH_ARCHIVE_MAX_CATCH_UP_WINDOWS`), 60 candidats, 70 requêtes GitHub
  par compte rendu, en série ; un 301 n'est pas suivi en v1 (`core/outbound.py` ne suit aucune
  redirection), écart à la recommandation de GitHub accepté. Écarté : suivre un seul 301 vers
  `api.github.com` (une exception au client sortant).

- **Le contenu des appels des tendances suit D1 : tracé sous `KB_TRACE_CONTENT`, comme les fiches.**
  Décision de Sabine du 2026-10-30 (~16:12Z), relayée par time-knight. Le choix et la rédaction
  appellent `trace_contents` après avoir jugé l'appel ; le contenu (`owner/repo`, description, topics,
  README nettoyé, sortie du modèle) part vers Grafana Cloud selon le réglage (`none` par défaut, et
  tant que Grafana Labs n'a pas accusé réception du DPA) ; les spans restent sans nom de dépôt ni
  `repository_id`. Remplace le « jamais tracé » de la conception du 29/10, qui revenait sur D1
  (« Traces : le contenu des appels au modèle, sous réglage », 2026-10-28) sans que ce soit vu.
  Écarté : une exception pour les tendances.

  Lien avec #143 (étoiles et forks totaux lus par GraphQL à la collecte, ADR du 2026-10-08) : non
  remplacé ; le compte rendu lit les étoiles totales en REST au moment de l'écrire, sans les garder.

  Limites assumées : les comptes de GH Archive sont un échantillon, des rangs proches ne se
  départagent pas ; le filtre de contenu d'Azure peut refuser une description ou un README qui parle
  de jailbreak ; le côté `kb` (registre, coffre) suit la question ouverte « Où tourne `kb
  write-tops` en ligne ».

  — #364 (contrat) ; code : #365 à #370

## 2026-10-31

### Tendances : la fiche GitHub de chaque candidat (#367)

Conception de time-knight, relue par un sous-agent, validée par Sabine le 31/10 (~14:33Z).

- **Seul un 403 de limite arrête le compte rendu ; tout autre 403 écarte le candidat, et le 3e
  arrête en `github_forbidden`.** Décision de Sabine du 31/10 (14:20Z), « Q1 (b) ». Revient sur le
  tableau « GitHub » du contrat (#364), où tout 403 arrêtait : la doc de GitHub (« Get a
  repository ») donne le 403 comme une réponse de l'endpoint lui-même, en plus des limites de débit.
  Un candidat qui répondrait toujours 403 ferait échouer chaque compte rendu dont la période le
  contient, et un compte rendu en échec ne fait pas avancer la période. Une limite : tout 429, ou un
  403 avec `x-ratelimit-remaining: 0`, un `retry-after`, ou un message « rate limit » ou « abuse »
  (classeur des 403 d'Octokit) → 503 `github_rate_limited`. Le garde-fou du 3e 403
  (`GITHUB_MAX_FORBIDDEN_PER_REPORT`) évite d'insister si une limite était mal lue ; il porte un état
  à lui, pas `github_rate_limited`, qui nommerait une supposition. Écarté : (a) le contrat tel quel.
  Limite assumée : un 403 de limite au message changé par GitHub serait lu comme un refus, deux fois
  au plus par compte rendu.
- **`KB_AI_GITHUB_TOKEN` doit être un jeton *fine-grained* (`github_pat_`).** Un jeton *classic*
  porte des *scopes* larges, au-delà de la lecture de dépôts publics (moindre privilège,
  `docs/jeton-github.md`) : `kb serve-ai` le refuse au démarrage, sans le citer. Écarté : accepter
  tout jeton. Limite : la forme du jeton est vérifiée, pas ses permissions.
- **Un candidat écarté par GitHub sort du compte rendu et n'est que compté.** 404, 410, 451, toute
  redirection (non suivie), un `id` différent, un 403 hors limite : son nom peut désigner désormais
  un autre dépôt, et le coffre en ferait un lien. La réponse le compte par motif (`candidates`), et
  `kb` écrit une ligne des écartés, motifs à zéro omis. Écarté : le garder dans `repositories[]`
  avec `facts: null`.
- **Le budget de 70 requêtes par compte rendu est compté par le client, relances comprises.** Un
  objet par compte rendu (`GithubReading`) tient le budget, les refus et l'échéance ; épuisé, la
  lecture s'arrête en `github_unavailable`. Une relance sur 5xx, sans attente : attendre 5 s comme la
  collecte mangerait l'échéance de 60 s. Les README de #369 partageront ce budget.

— #367

### Collecte : le flux arXiv lu par defusedxml (#69)

- **Le flux arXiv est lu par `defusedxml.ElementTree.fromstring`, réglages par défaut
  (`forbid_entities=True`, `forbid_external=True`).** Option tranchée par Sabine le 18/10, « pour
  raison de sécurité » ; dépendances accordées le 31/10 : `defusedxml`, et `types-defusedxml` en
  dépendance de développement (`mypy --strict` en CI ; Q-A, « je suis ta recommandation »). Le flux
  est une donnée non fiable, et `xml.etree.ElementTree` seul développe une entité interne déclarée
  dans son DTD (observé le 31/10 : le test de l'entité interne, lancé sur l'ancien code, ne lève
  rien). Une déclaration d'entité devient `PageRefusedError("XML refused: <type>")`, l'exception de
  defusedxml masquée de la trace (`from None`) : elle cite le nom de l'entité et l'adresse déclarés
  dans le flux. Écartés : garder `ElementTree` avec un `# noqa: S314` justifié (l'entité interne
  resterait développée) ; `forbid_dtd=True` (refuse un flux pour un seul `DOCTYPE`, sans protection
  de plus que les entités et références externes refusées) ; `# type: ignore[import-untyped]` ou un
  `cast` au lieu des types. Limites assumées : une dépendance de plus, verrouillée en 0.7.1, publiée
  le 2021-03-08 (`uv.lock`) ; l'exception de defusedxml reste dans `__context__`, que rien dans l'ETL
  ne lit.

— #69

### Collecte : téléchargée par httpx2, chaque redirection contrôlée avant d'être demandée (#86)

Plan de time-knight, relu par un sous-agent, validé par Sabine le 31/10 (~18:08Z). Reprend le
contrat de #54 (fermée) ; fait l'harmonisation des deux modules de connexions sortantes signalée
par la PR de #209 (« à harmoniser après le POC ») : la collecte passe par `open_http_client` de
`core/outbound.py`, comme l'API IA.

- **Les redirections sont suivies par le code, pas par httpx2, et chacune est contrôlée sur l'URL
  que httpx2 demandera, avant d'être demandée.** Le client ne suit rien (`follow_redirects=False`) ;
  la cible, `urljoin(URL demandée, Location)`, est construite par `client.build_request`, puis
  `str(request.url)` est comparée au préfixe de confiance, et c'est cette requête-là qui part :
  `https://tldr.tech/ai/2026-10-04/../../login` passerait un `startswith` sur la chaîne brute, puis
  httpx2 demanderait `https://tldr.tech/login`. Une cible hors préfixe lève `RedirectedOutsideError`
  sans requête vers elle, et garde sa cible entière (`redirect_url`, que lit tldr). Au plus 10 sauts
  (`HTTP_MAX_REDIRECTS`, la valeur d'urllib), en `GET`, avec les seuls en-têtes ordinaires : jamais
  `response.next_request`, qui renverrait `Authorization` à une redirection de même origine. Écarté :
  `follow_redirects=True` (httpx2 suivrait avant tout contrôle : l'écart même de #54, où `urlopen`
  suivait jusqu'à 10 sauts, `http://` compris, et seule l'URL finale était contrôlée). Limite
  constatée sur httpx2 2.13.1 : `client.send` lit lui-même la `Location` d'un 3xx ; une `Location`
  qu'il ne sait pas lire (une tabulation) y lève `httpx2.RemoteProtocolError`, une erreur réseau,
  relancée une fois, la cible jamais demandée. Tranché par la session K-B : aucun code pour ce cas.
  Une `Location` qu'il lit, mais que `urljoin` refuse (`https://a]b/`) ou résout en une adresse
  qu'il refuse, est refusée (`PageRefusedError`), jamais demandée (revue de #86, tranché par
  time-knight).
- **Un statut hors 2xx est une `SourceStatusError(ExpectedSourceError)`, dans
  `etl/source_contract.py`, avec `status` et `headers` (`httpx2.Headers`, insensibles à la
  casse).** Son message est `HTTP <statut> <raison>`, la raison de `httpx2.codes`, jamais celle du
  serveur. Elle remplace `HTTPError` ; le 304 de CISA KEV se lit sur `status`. Des `headers` en
  `dict` rendraient `Retry-After` invisible sous une autre casse, et un 429 serait relancé à 60 s.
  Écartés : `HttpStatusError` (trop proche de `httpx2.HTTPStatusError`) ; rendre `bytes | None` pour
  un 304 (le téléchargement saurait ce que CISA veut dire) ; laisser `httpx2.HTTPStatusError` aux
  sources (elles dépendraient de httpx2). `is_served_from` et l'URL de l'erreur sont retirés : une
  fois chaque saut contrôlé, une réponse vient toujours du préfixe.
- **La lecture bornée d'un corps vit une fois, `read_bounded_body(response, max_bytes, is_late)`
  dans `core/outbound.py`.** Décision de Sabine du 31/10 (~18:05Z, Q-B), à la troisième occurrence
  (`code.md`) : la collecte et les deux connecteurs de l'API IA (`data_api_client.py`,
  `github_client.py`) changent `BodyTooLargeError` et `BodyTooLateError` en leur erreur, leurs tests
  inchangés. Octets décodés : un corps compressé est borné par sa taille une fois lu, à un pic de
  `max_bytes` + 1 Mio (httpx2 décompresse par morceaux d'1 Mio au plus). Écarté : une troisième copie,
  réunie plus tard.
- **`EXPECTED_SOURCE_ERRORS` : `URLError` devient `httpx2.TransportError`.** Une erreur réseau
  reste sur sa ligne, sans trace (décision du 2026-10-29, #361) ; un délai dépassé
  (`httpx2.TimeoutException`) n'a toujours pas de relance. `ConnectionError` sort de `download` et de
  `find_retry_wait` (httpx2 change toute `OSError` en `ConnectError`, `ReadError` ou `WriteError`) ;
  il reste dans `EXPECTED_SOURCE_ERRORS`, que lèvent d'autres chemins. Écarté : envelopper
  `httpx2.TransportError` dans une erreur de K-B (une classe de plus, pour le même message).

— #86

## 2026-11-01

### Tendances : le choix du modèle et ses contrôles (#368)

Conception de time-knight (31/10), relue par un sous-agent, corrigée, complétée par les réponses de
Sabine (Q1 le 31/10, Q2 et Q3 le 01/11), validée par Sabine le 01/11 (~20:40Z). Contrat :
[tendances.md](../tendances.md), « Ce que rend #368 ». Le pourquoi est celui de Sabine quand la
décision lui est attribuée ; sinon, celui de la conception qu'elle a validée.

- **Le modèle reçoit la trajectoire (le rang par fenêtre), pas une « direction ».** Décision de
  Sabine du 01/11 (~20:27Z), « Q2 (a) ». Pourquoi : « direction » n'était définie nulle part dans
  le contrat (#364) ; la trajectoire porte le décollage, le pic et le recul. Format court : les
  fenêtres une fois, puis par candidat une liste de rangs alignée sur elles. Écartés : (b) une
  direction calculée par le code (une mesure à inventer, et la forme de la courbe perdue) ; (c) ni
  l'une ni l'autre (le modèle ne distinguerait plus un dépôt qui monte d'un dépôt qui retombe).
- **L'échéance de `POST /trend-reports` passe de 60 à 200 s**, comme celle de `POST /digests`, et
  pour la même raison : sous les 240 s de `kb` et de l'ingress d'ACA, avec une marge pour le dernier
  appel en cours. Écarté : garder 60 s, qui couvre les lectures GitHub mais laisse moins qu'un appel
  au modèle (`LLM_CALL_TIMEOUT_SECONDS` = 90) ; écartée aussi, une réserve de temps pour le modèle
  pendant la lecture de GitHub. Limite assumée : si GitHub prend presque toute l'échéance, le choix
  échoue en `llm_timeout` et le compte rendu reste factuel, la période avance ; #370 le mesure.
- **Les choisis vont dans le fichier du coffre dès #368**, dans une section « Choisis par le modèle »
  avant « Dépôts qui ressortent » (nom en lien, critères, sujets ; ou la raison d'un choix non
  fait). Décision de Sabine du 31/10 (~16:02Z), « Q1 (a) ». #369 y ajoutera les textes sans réécrire
  la section. Écarté : (b) rien dans le fichier avant #369, le choix au seul registre.
- **Plus de 5 choix sont refusés par le schéma de sortie (`schema`), pas par un contrôle du code.**
  `Field(max_length=5)` dans le modèle Pydantic, comme les bornes de structure de la rédaction ; le
  schéma envoyé n'a pas de `maxItems`, dont le support en mode strict n'est pas vérifié. Le nouvel
  état de contrôle, `criterion`, refuse ce qui touche aux critères (aucun, en double, hors des 4, un
  critère 1 à 3 non calculé, `watch_subject` sans sujet ou l'inverse) ; il entre dans toutes les
  tables de rappels. Écarté : `completeness` pour plus de 5 choix (le contrôle de la complétude du
  classement, d'un autre sens) ; un second état neuf (le contrat n'en nomme qu'un).
- **`Stage` gagne `select` : l'appel du choix écrit sa ligne de métrique et ses mesures
  OpenTelemetry**, qu'il réussisse ou échoue. Décision de Sabine du 01/11 (~20:35Z), « Q3 (a) » :
  le contrat le disait déjà (« le type `Stage` est étendu ») et la règle 4 de `poc.md` le demande
  (une ligne JSON par appel au modèle). Les mesures de la demande (`data_fetch_ms`, `items_capped`,
  `items_dropped_before_writing_stage`) y sont nulles, choix de time-knight : les lectures sont
  mesurées dans leurs spans. Écartés : les métriques hors de #368 (le premier plan) ;
  `data_fetch_ms` rempli par la lecture des fenêtres et de GitHub (un autre sens sous le même nom
  que les fiches). `FailedSubjectSchema.stage` des fiches garde `classify` ou `write`.

Limites assumées : une description peut pousser son dépôt vers un choix par `watch_subject` (le code
vérifie que le sujet est de la liste, pas que le dépôt en relève) ; le message au plafond mesure
116 323 caractères, environ 39 000 jetons à 3 caractères par jeton (estimation), et un choix au
plafond et sa relance partagent le quota de 140 000 jetons par minute avec un `kb digest` lancé dans
la même minute.

— #368

## 2026-11-03

### Collecte : le nombre de bruts écrits sur la ligne de chaque source

Décision de Sabine du 2026-11-03, demandée pendant la rédaction de l'annexe E1 c1.8 (la capture
d'une collecte) ; plan de time-knight relu par un sous-agent et validé par elle. Pas d'issue.

- **Le bilan de `kb collect` donne, à côté de `ok`, le nombre de fichiers bruts écrits par la
  source : `cisa_kev: ok (1 raw file)`, `tldr_ai: ok (6 raw files)`, `ok (0 raw files)` pour une
  source sans rien de neuf.** Les lignes `failed (…)`, `skipped (…)` et `collection_state` ne
  changent pas. **Revient sur un point** de « Commandes : le retour console sans tableau (#359) »
  du 2026-10-29 : « le nombre de bruts écrits par une source collectée est au journal
  seulement ». Ce qui a changé : le nombre revient sans tableau, sur la ligne que #359 a gardée ;
  un `ok` seul ne dit pas si la source a rapporté quelque chose (constat de Sabine du
  2026-10-28 : « ok » laisse croire que la source a été collectée).
  - Format : trois options présentées, `ok (6 raw files)` retenu par Sabine, sans autre raison
    dite que celle présentée (les parenthèses de `failed (…)` et `skipped (…)` du même bilan).
    Écartés : `ok, 6 raw files written`, aligné sur `kb write-tops` (`ok, 2 sheets written`) ;
    garder `ok` seul, comme décidé le 2026-10-29.
  - Le nombre est celui que la collecte journalisait déjà (`source 'cisa_kev' collected, raw
    files written: 1`) : un par fichier, un par page pour une source à pages (tldr : un jour
    d'édition ; clips : un clip), 0 seulement quand la source dit « rien de neuf ».
  - Code : `CollectionOutcome.written_count_by_source`, un dict à part (la forme de
    `raw_file_counts` de #291) ; `errors_by_source`, le code de sortie et les 17 assertions de
    tests qui le lisent ne bougent pas. Écarté : un résultat par source (erreur ou nombre) dans un
    seul dict, plus juste en type mais qui réécrit ces assertions, hors besoin.

Limites assumées : un fichier brut écrit ne dit pas combien d'items il porte (une réponse vide
fait `1 raw file`) ; le nombre d'items vient à l'import. Une source en échec au milieu de ses
pages garde les pages déjà écrites, mais sa ligne reste `failed (…)`, sans leur nombre, comme
avant.

## 2026-11-04

### Conservation : la base, source de vérité, et la purge hors de l'ETL (#83)

Décisions de Sabine du 2026-11-04, en séance avec time-knight (session « code K-B »), demandées
pour finir la purge et le critère C4 d'E1 ; plan relu par un sous-agent (17 constats pris), puis
« go ». Elles tranchent les questions de « Durées de conservation et fréquence de la purge »
restées ouvertes.

- **La base devient la source de vérité ; le brut est gardé 6 mois au plus, sauf les catalogues
  d'état (Zotero, CISA KEV), dont il garde le dernier fichier importé (#139). Les relevés des tops
  et les copies des clips suivent la même règle ; un fichier jamais importé part aussi : 6 mois est
  un maximum.** Décision de Sabine : « hors zotero et cisa, les raw files sont gardés 6 mois max
  […] La base devient la "source" de vérité. » Pourquoi, celui de Sabine : « Une veille de plus de
  six mois n'est plus de première fraîcheur. Ça minimise aussi le stockage et retire des données
  inutilisées. » Vérifié : aucune collecte ne relit un brut ancien (seuls l'import, `kb write-tops`
  et le dernier extrait Zotero lisent `raw/`) ; les logins des auteurs des releases et des personnes
  créditées dans les alertes, qui ne sont que dans le brut, partent avec lui. **Inverse** l'ADR du 2026-10-09 (« c'est le brut qu'on sauvegarde ») et
  la décision 5 de « Squelette E1 E3 : cadrage du 20/10 » pour le brut (3 ans). Écarté : garder le
  brut 3 ans, comme la base. Limites assumées : tant que la base n'a pas de sauvegarde, elle est la
  seule copie de ce qui a plus de 6 mois ; dès que le plus ancien brut a 6 mois, un changement de
  schéma passe par une migration, que K-B n'a pas encore (la limite de W7, 2026-10-09, arrive).
- **Une fois la base sauvegardée, le brut (hors Zotero et CISA KEV) part dès que deux sauvegardes
  saines le couvrent ; les 6 mois restent le maximum. Règle écrite au registre (étape 3), pas
  codée.** Décision de Sabine : « A partir du moment où le système de backup de bdd est en place,
  purge toutes les deux sauvegardes de base. » Elle reprend les intervalles qu'elle avait fixés le
  2026-10-19 avec time-knight, jamais entrés dans K-B jusqu'ici : deux sauvegardes par semaine,
  chacune vérifiée par une restauration d'essai, 8 gardées, celle d'avant une migration gardée sans
  limite, une copie hors du Mac. Écarté pour l'instant : une commande `kb purge` à part, ou un
  dossier `cron_jobs/` (proposé par Sabine) : le cron vit hors du code (« le code ne planifie
  rien »), et sur le Mac rien n'est planifié, une purge à part pourrait ne jamais tourner ; la purge
  du brut après sauvegarde ira avec la commande de sauvegarde.
- **En base, la veille est gardée 3 ans jour pour jour depuis la collecte de son fichier
  (`raw_data.collected_at`), `trend` comprise ; les catalogues d'état et la bibliothèque sont
  gardés sans limite, CISA KEV comme Zotero et les clips.** Décisions de Sabine : `trend`
  (« pour trend ok », sur la recommandation : une seule règle pour toute la veille, et l'écart avec
  `window_end` n'est que de quelques jours, une ligne n'étant écrite que par le premier fichier
  qui apporte sa fenêtre) ; CISA KEV (« cisa devrait être comme zotero et clips pour base de
  données » ; avis de time-knight : la base porte l'état du catalogue, une entrée retirée y est
  marquée, `vulnerability` ne porte aucune donnée personnelle, et une durée comptée depuis la
  première collecte purgerait une entrée encore au catalogue pour la réécrire au suivant). Écarté :
  `trend.window_end` comme point de départ. Un papier encore cité par une `zotero_entry` ou une
  `newsletter_article` ne garde que son identifiant arXiv ; une référence que plus rien ne cite
  est supprimée (minimisation, choix de time-knight nommé au plan).
- **Un dépôt suivi (`tracked_repository`) reste tant qu'il est dans `GITHUB_TRACKED_REPOSITORIES`
  ; retiré de la liste, il part avec sa dernière release. Une ligne de `raw_data` part quand son
  fichier n'existe plus et que plus rien ne la cite, sauf celle du dernier fichier importé d'un
  catalogue d'état.** Décisions de Sabine (« pour track repository ok », « ok pour raw_data »).
  Pourquoi : une release cite son dépôt (clé étrangère) ; une ligne de `raw_data` date ses items
  et ses tendances, et celle du dernier catalogue dit à l'import quel catalogue est le dernier
  (`SELECT_LATEST_CATALOG`, `catalog.py`) : la supprimer ferait prendre un catalogue tardif pour
  plus récent (constat de la relecture du plan). Écarté : supprimer le dépôt et ses releases dès
  qu'il sort de la liste (ses releases partiraient avant leurs 3 ans). Sans dossier `raw/` (un
  volume non monté), le registre n'est pas purgé : chaque fichier y paraîtrait absent.
- **Ce que Sabine dépose dans K-B n'est jamais supprimé automatiquement.** Décision de Sabine :
  « ce que je dépose moi dans kb n'est jamais supprimé automatiquement. » Déjà vrai : K-B n'écrit
  ni dans un clip du coffre ni dans Zotero, et la bibliothèque n'a pas de durée en base. Les copies
  brutes des clips suivent pourtant la règle des 6 mois (option b, choisie par Sabine) : le clip
  reste dans le coffre et dans la base. **Inverse** la décision 6 de « Squelette E1 E3 : cadrage du
  20/10 » et la règle du 2026-10-19 (brut des clips gardé jusqu'à une sauvegarde).
- **Limite acceptée : une donnée que la source republie est une nouvelle collecte, ses 3 ans
  repartent.** Décision de Sabine (« a, je suis ta recommandation ») : une release encore parmi
  les 100 dernières de son dépôt, ou une alerte que GitHub met à jour, revient comme un item neuf
  après sa purge. Écarté : l'import qui écarte un item de flux dont la date de publication précède
  la borne (il perdrait la mise à jour d'une alerte). Tranche le cas du commentaire de #83 du
  2026-10-06.
- **La purge a sa place hors de l'ETL : le paquet `src/k_b/purge/`, à côté de `post/`, lancé par
  `kb import` après le commit et le bilan, dans cet ordre : les catalogues remplacés (étape 7,
  déplacée de `etl/raw_purge.py`), la base, le brut, le registre ; la première erreur arrête la
  suite, que l'import suivant relance. Le SQL est dans `src/k_b/database/purge.py`.** Décision de
  Sabine : « je veux que la purge ait une place hors de ETL », « avec un emplacement logique et
  adapté du code qui respecte nos principes architecturaux ». La purge n'est ni E, ni T, ni L
  (`docs/refactoring/orchestration.md`, « `raw_purge` est le cas douteux »). Les tests
  d'architecture la tiennent comme `post/` : l'ETL n'importe rien d'elle, elle n'importe de l'ETL
  que `raw_store` et `raw_files`, les API ne l'importent pas. **Révise** la décision du 2026-10-23
  (la purge du brut, fonction de `etl/pipeline.py`). Limite signalée à Sabine et gardée : l'accès
  au brut (`RawStore`) est rangé dans `etl/` alors que c'est un accès au stockage ; le déplacer
  touche 21 modules, une refonte hors de #83, à revoir avec le passage du brut à Blob. — PR de #83

### API : la documentation servie en `sandbox` seulement (#393)

- **Les deux API ne servent `/docs` et `/openapi.json` que si `KB_DEPLOYMENT_ENVIRONMENT=sandbox` ;
  avec `production`, une autre valeur ou rien, ces routes répondent 404 ; `/health` reste servi.**
  Décision de Sabine : « production ok, sandbox pour développement, si autre valeur ou rien on
  affiche rien ». Pourquoi : une variable oubliée ou mal écrite ne montre rien (échouer fermé,
  `code.md`). Ce n'est pas une mesure de sécurité, dit-elle aussi : « ce qui est caché n'est pas
  pour autant protégé » ; la clé protège les données, et l'entrée interne de l'API de données en
  ligne reste à faire. Écartés : couper sur la seule valeur `production` (proposé par time-knight :
  une variable oubliée laissait la doc servie) ; refuser de démarrer sur une valeur inconnue
  (inutile : elle ne montre rien). Limite : en local, `/docs` demande
  `KB_DEPLOYMENT_ENVIRONMENT=sandbox` dans le `.env`. Le contrat reste versionné : `kb openapi`
  l'écrit par `app.openapi()`, indépendant de la route. — PR de #393

### Journaux : deux mots, deux dossiers, 6 mois (#267)

Décisions de Sabine du 2026-11-04.

- **Un log dit ce qu'un programme a fait, pour le surveiller ; un journal dit ce qu'un import a décidé
  sur les données. Les fichiers JSON de l'import deviennent des journaux, dans leur dossier :
  `journals/import-journal-<date>.jsonl`. Les logs de fonctionnement ne changent ni de nom, ni de
  place, ni de format (`logs/kb.log`, `logs/kb-serve-data.log`, `logs/kb-serve-ai.log`).** Pourquoi,
  celui de Sabine : « les log partent à grafana et les journals reste dans kb work dir », « in fine
  toute l'application sera tracées de bout en bout pour suivre le flux d'une requetes » : c'est la
  cible ; aujourd'hui, seul `kb serve-ai` envoie à Grafana. Écarté : tout dans `logs/` (d'abord
  recommandé par time-knight : un journal y aurait recréé la confusion, et les tests de bout en
  bout, qui gardent `logs/`, auraient gardé les journaux, qui portent des URL de clips).
- **Logs et journaux sont gardés 6 mois, jour lu dans leur nom, par une seule purge à la fin de `kb
  import` ; la rotation de minuit ne supprime plus rien (`backupCount=0`).** Décision de Sabine
  (« oui et note que c'est une recommandation de la CNIL »), sur la recommandation de time-knight.
  Pourquoi : six mois est le bas de la fourchette de la CNIL pour une journalisation, six mois à un
  an (délibération n° 2021-122, recommandation non contraignante ; page lue, PDF non lu), et la durée
  du brut ; une seule règle pour tout ce qui n'est pas la base. Sabine sur les deux purges :
  « Est ce utile et nécessaire que leur purge soit différente ? » **Révise** sa décision du 2026-10-19
  (30 jours glissants, #267). Écartés : 30 jours, sous la recommandation ; 30 fichiers (`backupCount`
  compte des fichiers, pas des jours : un jour sans commande n'en crée pas, la durée n'est donc pas
  dite). Limite : sans `kb import`, rien n'est supprimé. — PR de #267

## 2026-11-05

### API : borner le corps des requêtes et la réponse du modèle (#161)

- **Le corps d'une requête à l'API IA est borné à 1 024 octets par le `RequestBodyLimitMiddleware` de
  Starlette, précédé d'un contrôle de `Content-Length` propre à K-B : au-delà, 413
  `content_too_large`, avant la clé.** Recommandation de time-knight, acceptée par Sabine (« go » sur
  l'option B). Pourquoi : FastAPI lit le corps avant la clé, et ce corps n'avait pas de taille
  maximale (OWASP API4:2023, revue de la certif du 05/11). Starlette compte les octets reçus, en flux
  compris ; mais quand la longueur annoncée dépasse la borne, il remplace toute réponse par un 413 en
  texte brut (`send_with_limit`, essayé sur 1.8.0), hors du schéma d'erreur qu'API8 demande. K-B répond
  donc d'abord, en lisant la longueur par `int()` comme Starlette. Écartés : Starlette seul (413 en
  texte brut dans le cas courant) ; un middleware entièrement à K-B (refait le comptage que la
  bibliothèque fournit) ; lever une exception depuis `receive` (FastAPI en fait un 400) ; une borne
  posée par ACA (rien dans le dépôt, rien en local). Limite : en flux, le serveur lit encore le morceau
  qui franchit la borne, sans clé. — PR de #161, à venir

- **La réponse du fournisseur du modèle est lue par `read_bounded_body`, à 1 000 000 d'octets au plus :
  au-delà, `llm_unavailable` sans nouvelle tentative ; à l'échéance, `llm_timeout`.** Validé par Sabine
  avec le plan de la PR. Pourquoi : une réponse de tiers est une entrée non fiable (OWASP API10:2023),
  et l'API de données et GitHub ont déjà cette lecture. Écarté : garder `http_client.post`, qui lit tout
  en mémoire avant toute décision. Limites assumées : la valeur repose sur une estimation (environ
  65 Ko pour 8 192 jetons), non mesurée ; un 429 ou un 5xx de plus d'1 Mo perd son `Retry-After`, et une
  réponse trop grosse ne donne pas ses jetons consommés (lire l'usage demanderait de lire le corps).
  — PR de #161, à venir

### API : un client par route, une demande à la fois, un débit par client (#161)

- **Chaque route de l'API IA s'ouvre à un seul client, par une table (`AI_API_CLIENT_BY_ROUTE`) lue
  par une dépendance de l'app : `POST /digests` à `KB_DIGEST`, `POST /trend-reports` à
  `KB_TREND_REPORT` ; tout autre client à clé valide reçoit 403 `client_not_allowed`, et une route
  absente de la table est refusée à tous.** Recommandation de time-knight, validée par Sabine avec le
  plan de la PR (2026-11-05). Pourquoi : toute clé valide ouvrait les deux routes, qui appellent un
  modèle payant (OWASP API5:2023, revue de la certif du 05/11). Écartée : une dépendance par routeur,
  qu'une route oubliée contournerait. Limite assumée : une clé sans route est acceptée au démarrage ;
  elle ne reçoit que des 403. — PR 2A de #161, à venir

- **Une demande à la fois par route de l'API IA, sans file : la suivante reçoit 429
  `request_already_running`, avec `Retry-After: 200`.** Validé par Sabine avec le plan. Pourquoi :
  une demande dure jusqu'à 200 s et fait plusieurs appels payants, si bien qu'un débit par minute ne
  suffit pas (commentaire de #161 du 2026-10-21). Par route et non pour toute l'API : un digest et un
  compte rendu peuvent tourner ensemble. Écartés : une file d'attente (le client attendrait jusqu'à
  200 s pour rien) ; `limit_concurrency` d'uvicorn, qui compte aussi les connexions muettes (31 sockets
  sans clé couperaient l'API, `/health` compris : essai du relecteur du plan à 4, doc d'uvicorn 0.54),
  renvoyé au jalon ACA. Limites assumées : la demande court jusqu'à son échéance même si son client est
  parti, donc après un Ctrl-C la relance est refusée environ 200 s au plus ; `Retry-After` vaut toujours
  200, une borne haute. Essayé : un client qui ne lit pas une réponse de 50 Mo ne garde pas le verrou
  (rendu à 0,1 s, uvicorn 0.54, FastAPI 0.143.1). — PR 2A de #161, à venir

- **Un débit par client et par route sur les deux API, compté par une fenêtre glissante en mémoire
  écrite dans K-B (`core/api_rate_limit.py`) : 20 demandes par 24 h sur chaque route du modèle ;
  1 200 (`/items/{item_id}`), 120 (`/items`) et 120 (`/trends`) par minute sur l'API de données ; au-delà,
  429 `rate_limit_exceeded`, avec `Retry-After`.** Validé par Sabine avec le plan. Pourquoi : rien ne
  limitait le nombre d'appels au modèle (OWASP API4 et API6:2023), et les deux API seront exposées au
  08/11. Les chiffres viennent des journaux d'essai du 26 au 29/10 : 7 demandes de fiches par jour au
  plus (20 en fait environ 3 fois), 804 détails et 21 listes par minute au plus. **Revient sur « Pas de
  limite de débit : le client est local »** (`docs/specs-api.md`, « Hors de cette version », depuis
  #185) : ce qui a changé, c'est la mise en ligne prévue au 08/11 et la revue OWASP de la certif.
  Écartés : `slowapi` 0.1.10 (un décorateur et un paramètre `request` sur chaque route, et il ajoute
  `limits`) ; `limits` 5.8.0 (3 dépendances, et son atout, Redis, ne sert pas ici) ; une limite d'Azure
  (rien en local, rien dans le dépôt) ; une fenêtre fixe (double rafale à la frontière) ; une variable
  d'environnement par limite (aucun environnement n'en demande une autre). Limites assumées : **ce n'est
  pas un budget**, car un redémarrage ou un passage à zéro réplique remet le compte à zéro, et il ne
  vaut que pour une réplique ; il compte les tentatives, un 422 de schéma ou une panne rapide compris ;
  aucune limite pour les requêtes sans clé valide (par adresse, elle passerait par `X-Forwarded-For`,
  à justifier avec la revue des 10 points) ; sur le Mac, la veille ne compte pas dans la fenêtre
  (`time.monotonic`, `mach_absolute_time()`). — PR 2A de #161, à venir

## 2026-11-06

### Tests : mesurer la couverture par `pytest-cov`, sans seuil

- **La couverture des tests se mesure par `uv run pytest --cov --cov-report=term-missing` : `pytest-cov`
  7.1.0 en dépendance de développement, `coverage` 7.17.0 figée dans `uv.lock`, réglée dans
  `[tool.coverage.run]` de `pyproject.toml` (`source = ["k_b"]`, `branch = true`,
  `patch = ["subprocess"]`). Aucun seuil, CI inchangée.** Demandée par l'utilisatrice en rédigeant E3
  (05/11) : mesurer d'abord, elle fixe le seuil ensuite. Plan de time-knight validé le 06/11 :
  - `coverage` 7.17.0 (22/10), recommandation de time-knight suivie par l'utilisatrice : 7.17.1 (03/11)
    et 7.17.2 (04/11), publiées depuis deux ou trois jours, n'ont pas laissé le temps de signaler un
    paquet compromis ;
  - `branch = true` : une ligne d'un `if` compte couverte même si l'une de ses branches n'est jamais
    prise ; écartée, la mesure des lignes seules ;
  - `patch = ["subprocess"]` : `pytest-cov` 7.0 ne mesure plus les processus enfants (son journal des
    versions renvoie à ce réglage de `coverage`), et des tests lancent le code de K-B dans un enfant
    (`test_sigint.py`, `test_sigterm.py`, `test_serve_ai.py`…). Écarté : laisser ce code compter comme
    non testé. Mesuré le 06/11 : 130 lignes de plus sur le seul test du SIGINT en processus propre,
    écart nul sur la suite entière, où chaque ligne lancée par un enfant l'est aussi dans le processus
    de pytest ;
  - ni `fail_under` ni job de CI : le seuil attend la décision de l'utilisatrice sur la mesure
    (« Décisions encore ouvertes »).
    **Révisée le 2026-11-08** : 96 %, vérifié par le job `tests` de la CI (« Tests : un seuil de
    couverture de 96 %, vérifié par la CI (#465) »).

  Limites assumées :
  - les tests de bout en bout (`-m e2e`, écartés de `uv run pytest` par `tests/conftest.py`) ne
    comptent pas dans la mesure ;
  - un enfant lancé avec un environnement réduit à quelques variables (`test_api_telemetry.py`) ne
    reçoit pas `COVERAGE_PROCESS_CONFIG` et n'est pas mesuré ;
  - `coverage` pose `a1_coverage.pth` dans `.venv`, lu à chaque démarrage de Python dans cet
    environnement ; il n'agit que si `COVERAGE_PROCESS_START` ou `COVERAGE_PROCESS_CONFIG` est posé ;
  - `uv.lock` gagne deux paquets (`pytest-cov`, `coverage`), en développement seulement. — PR de #405

### API de données : un délai par requête et les bornes du détail (#331)

- **Une requête de l'API de données a 5 s dans la base, comptées depuis le premier contrôle de sa
  première lecture : le contrôle posé par `set_progress_handler` sur sa connexion, toutes les 1 000
  instructions de SQLite, arrête la lecture une fois l'échéance passée ; l'API répond 503
  `query_timeout`, sans le message de SQLite.**
  Plan validé par Sabine le 06/11, sur la façon écrite le 05/11 dans `docs/specs-api.md` (« Ce qui
  manque, et comment le tenir », #404). Pourquoi : un `LIKE` de `q` lit tout le corps des releases ;
  mesuré le 06/11, la pire recherche (199 « a » puis « b ») sur 400 corps de 125 000 « a » prend
  environ 10 s, une recherche ordinaire sur 50 millions de caractères 0,03 s (OWASP API4:2023).
  5 s reste sous les 10 s que le client de l'API IA attend chaque morceau d'une réponse
  (`DATA_API_READ_TIMEOUT_SECONDS`), ce qu'un test tient. 1 000 instructions, et non 100 comme le
  disait le plan validé : chaque contrôle reprend le GIL, et 1 000 en fait dix fois moins pour les
  autres requêtes ; la pire recherche, mesurée par l'API, s'arrête à 5,75 s au lieu de 5,10 s, sous
  les 10 s du client ; les tests le ramènent à 1, la base de test n'atteignant pas 1 000
  instructions au détail ni aux tendances (revue de code, tranché par time-knight, que Sabine a
  laissé trancher le 06/11). L'interruption se
  reconnaît à `SQLITE_INTERRUPT` (`sqlite_errorcode`, lu par `getattr` : une erreur levée par Python
  n'en a pas). L'échéance part du premier contrôle, pas de l'ouverture de la connexion : la
  dépendance et la route attendent chacune un fil du pool, et cette attente ne se passe pas dans la
  base ; le temps de Python entre deux lectures, lui, compte (revue de code, tranché par time-knight
  le 06/11). Écartés : `interrupt()` lancé par un minuteur de la boucle (`call_later`), car une
  échéance tombée entre deux instructions n'arrête pas la suivante, un test à 0 s ferait courir le
  minuteur contre la requête, et il faudrait une dépendance async ; un délai asyncio autour de la
  route, que SQLite ignorerait (la route tourne dans un fil) ; une variable d'environnement (une borne
  de protection, comme le débit, pas un réglage de déploiement) ; 504, qui dit qu'une passerelle n'a
  pas eu de réponse. Limites assumées : une instruction seule ne s'interrompt pas (un `LIKE` sur un
  clip de 1 000 000 de caractères, environ 0,2 s, extrapolé) ; à côté d'un fil Python qui calcule
  sans pause, une requête de 3 ms en prend 1,5 s à 1 000 instructions (essai du relecteur du
  plan) ; sous charge, l'attente du pool, non comptée, peut porter la réponse au-delà des 10 s du
  client de l'API IA, qui lit alors `data_api_timeout` au lieu du 503 ; le délai
  se multiplie par le débit (120 listes par minute), sans plafond de requêtes simultanées
  (« Une limite de connexions du serveur », ci-dessous). Pour #418 (PostgreSQL) :
  `statement_timeout` à 5 000 ms pour le rôle de l'API de données (`ALTER ROLE … SET`, côté
  serveur ; le paramètre de démarrage `options` peut être refusé par un pooler comme PgBouncer, à
  vérifier alors) ; son dépassement, SQLSTATE 57014 `query_canceled`, donne le même 503. Il compte par
  instruction : le détail en fait jusqu'à trois, 15 s en théorie, au-delà des 10 s du client.
  `transaction_timeout` (PostgreSQL 17) bornerait la requête entière, mais il ferme la session
  (FATAL), qu'on ne distingue pas d'une panne. `set_progress_handler` (`data_api/dependencies.py`)
  et `SQLITE_INTERRUPT` (`data_api/errors.py`) sont propres à SQLite : c'est là que #416 et #418
  les trouveront. — PR de #331, à venir

- **Un détail sert 125 000 caractères de texte long au plus, la longueur maximale du corps d'une
  release qu'il sert déjà entier : une entrée Zotero sert ses surlignages dans l'ordre, retirés
  compris, tant qu'ils sont 100 au plus et que leurs `text` et `comment` tiennent ensemble dans
  125 000 caractères ; un clip, les 125 000 premiers caractères de son texte. `highlights_truncated`
  et `body_truncated`, toujours servis, disent la coupe.** Choix de Sabine du 06/11 : le nombre et la
  taille, plutôt que le nombre seul que demandait l'issue. Pourquoi : 100 surlignages de 10 000
  caractères de texte et autant de commentaire feraient 2 000 000 de caractères, 16 fois le clip
  (relecture du plan). La coupe garde un début de la liste : un surlignage fait plus tard, donc daté
  plus tard, ne décale pas ceux déjà servis. Écartés : refuser le détail (le client ne lirait plus
  rien de l'item) ; paginer les surlignages ou le texte (une route de plus, hors de la taille S) ;
  servir le nombre total (aucun client ne le lit). Limites assumées : la coupe se fait dans la route,
  après la lecture, pour ne pas toucher `database/`, que l'axe PostgreSQL réécrit : les surlignages
  sont tous lus, bornés en temps par le délai, pas en mémoire ; `q` trouve un clip par la partie de
  son texte que le détail ne sert pas ; les valeurs ne reposent sur aucune mesure de la bibliothèque
  réelle (6 surlignages dans la base de test). — PR de #331, à venir

### Infrastructure : Bicep dans `infra/`, appliqué à la main, vérifié par la CI (#411)

- **L'infrastructure Azure de K-B est décrite en Bicep dans `infra/` : `main.bicep` appelle un module par
  famille de ressources (`infra/modules/`). Sabine l'applique à la main, `what-if` puis `create`. La CI la
  vérifie par `az bicep build` (workflow `infra.yml`, job `bicep-build`, Bicep v0.48.1 épinglé), sans
  aucun droit Azure.** Plan de mise en ligne validé par Sabine le 06/11 :
  - Bicep n'est pas du Python. C'est une exception à la règle « Python uniquement », acceptée par Sabine
    le 06/11, comme le YAML de la CI ;
  - application à la main : les fichiers donneront des rôles aux identités, ce qui demande le droit
    d'Owner du groupe de ressources (`roleAssignments/write`), et la CI ne l'a jamais. Écarté : un
    déploiement de l'infrastructure par la CI, qui obligerait à donner ce droit à une identité de la CI.
    Évolution possible, notée au plan : les identités et les rôles à la main, le reste par la CI ;
  - un fichier de workflow à lui, pas un job de plus dans `ci.yml` : chaque workflow nouveau a son
    fichier, pour que deux PR ouvertes ne touchent jamais le même (règle des axes de la mise en ligne,
    06/11). Filtré sur `infra/**`, le job ne doit pas devenir un contrôle obligatoire de `main` : il
    bloquerait toute PR qui ne touche pas `infra/`.

  Limites assumées :
  - `az bicep build` vérifie la syntaxe et les types, pas ce qu'Azure acceptera (droits, quotas, noms
    déjà pris) : seul le `what-if` le montre, et seule Sabine le lance ;
  - entre deux applications, rien ne compare l'état d'Azure au Bicep : une modification faite dans le
    portail reste invisible jusqu'au `what-if` suivant. — PR de #411, à venir

### `kb` : la réponse de l'API IA lue dans sa borne (#422)

Choix de la session dans le plan validé par Sabine le 06/11, relu en sous-agent. Clôt la décision
ouverte « Une borne de lecture des réponses de l'API IA et de l'API de données » (2026-10-21) :
l'API IA lit déjà l'API de données dans sa borne (`MAX_DATA_API_BODY_BYTES`) ; restait `kb`.

- **`kb digest` et `kb trend-report` lisent la réponse de l'API IA par `read_bounded_body`
  (`core/outbound.py`), dans `send_request` (`post/ai_api_client.py`), qu'ils partagent :
  8 000 000 d'octets décodés au plus (`MAX_AI_API_ANSWER_BYTES`), annoncés ou comptés, une borne
  pour les deux routes.** **Révise** 2026-10-21, « Fiches de veille : `kb digest` les écrit dans le
  coffre » (« Le corps de la réponse est lu sans borne de taille », décision 6 de Sabine, risque
  accepté pour le POC jusqu'à la mise en ligne), et son extension à `kb trend-report` du 2026-10-30
  (#366) : la mise en ligne vient (#423). Pourquoi 8 Mo : au-dessus du pire que les bornes du code
  permettent, tout caractère échappé en `\u00XX` (6 octets, la sérialisation de FastAPI) : environ
  5,7 Mo pour `POST /digests` (300 items lus, chacun dans une fiche, un titre de 1 024 caractères et
  une URL de 2 000 ; 12 affirmations de 400 caractères par fiche), 1,7 Mo pour
  `POST /trend-reports` (450 dépôts, 60 fiches GitHub) ; environ 1,7 Mo et 1 Mo sans échappement.
  Écartés : 4 Mo comme l'API de données, sous ce pire ; une borne par route (deux constantes pour un
  client, sans gain). Limite assumée : une estimation sur les bornes du code, pas la mesure d'une
  réponse réelle. — PR de #422

- **La réponse a 240 s depuis l'envoi (`AI_API_REQUEST_DEADLINE_SECONDS`, égal à
  `AI_API_READ_TIMEOUT_SECONDS`, la borne de l'ingress d'ACA), contrôlées après chaque morceau ;
  au-delà, `ai_api_timeout`.** Pourquoi : les délais d'httpx2 bornent chaque attente, jamais la
  réponse ; une réponse au compte-gouttes, sous la borne de taille, tiendrait `kb` sans fin.
  L'horloge est un paramètre de `send_request` (`time.monotonic` par défaut), pour le test.
  Écartés : déplacer `Deadline` d'`ai_api/` vers `core/` (`post` n'importe pas `ai_api`, et
  17 fichiers l'importent) ; aucune échéance. Limite assumée : le contrôle vient après chaque
  morceau décodé ; rien ne borne l'attente avant le premier (chaque lecture de l'en-tête attend
  240 s, pas leur somme), ni des morceaux bruts qui ne se décodent en rien (un corps gzip de blocs
  vides) : un défaut de `read_bounded_body` pour ses quatre clients, déjà sur `main` avant #422
  (revue de code, tranché par time-knight le 06/11, délégation de Sabine du 15/10), porté par
  #436 ; en ligne, l'ingress d'ACA coupe une requête à 240 s. — PR de #422

- **Au-delà de la borne, l'erreur garde l'état de son statut (`ai_api_invalid_response` pour un 200,
  `ai_api_failed` pour une 5xx…), son statut HTTP, `response larger than 8000000 bytes`, son
  `X-Request-ID` et son `Retry-After`, jamais le corps.** Pourquoi : une 5xx reste une panne de
  l'API IA quel que soit son corps (le défaut que #376 relève dans deux clients de l'API IA) ; les
  en-têtes retrouvent la demande dans `logs/kb-serve-ai.log`. Écartés : un état nouveau
  `ai_api_response_too_large` (l'API de données et GitHub nomment ce cas `…_invalid_response`, le
  modèle `llm_unavailable` ; le code de sortie, 1, ne change pas) ; toujours
  `ai_api_invalid_response` (reproduirait le défaut de #376). Écart voulu avec la correction que
  propose #376 (« sur une 5xx, ne pas lire le corps ») : `kb` lit le corps d'une 5xx, dans sa borne,
  pour afficher son `error` ; time-knight n'y voit pas de contradiction (06/11). — PR de #422

### Base : PostgreSQL en ligne, par un adaptateur maison (#417)

- **En ligne, la base est PostgreSQL ; en local, SQLite, pleinement fonctionnel. `KB_DATABASE_URL`
  choisit le moteur : absente, la base est le fichier `<KB_DATA_DIR>/k-b.sqlite` ; posée, une URL
  `postgresql://` ou `postgres://`. Les deux moteurs passent par un adaptateur maison,
  `database/engine.py`, dont la branche PostgreSQL (`database/postgresql.py`) enveloppe psycopg 3 ;
  SQLAlchemy Core est écarté.** Cadre posé par Sabine le 05/11 au soir : « avoir une variable
  switch entre sqlite et postgressql. En production c'est postgresql qui est le porteur de la base
  de donnée. Comme ça je garde sqlite fonctionnel dans le cas où je fais une installation locale de
  kb » ; précisé le 06/11 : l'un ou l'autre selon le mode d'installation, sans copie d'une base
  vers l'autre (transmis par time-knight). Il ferme « La base au temps 3 » (« Décisions encore
  ouvertes ») et confirme la décision 2 du « POC du 25/10 » (2026-10-15), mise en attente le
  2026-10-20. Options écartées en ligne, selon le rapport des faits Azure de time-knight du 06/11,
  non relu dans cette session : SQLite sur un partage Azure Files monté, parce que la doc de
  Container Apps ne dit rien des verrous de SQLite sur un partage SMB, et que des sources de la
  communauté le jugent peu fiable
  ([Preventing File Locks, Azure Container Apps](https://azureossd.github.io/2024/05/16/Preventing-File-Locks-Azure-Container-Apps),
  [SQLite on Azure Files (SMB)](https://dev.to/argha_dev/sqlite-on-azure-files-smb-a-debugging-story-with-a-humbling-ending-1p93)) ;
  SQLite et Blob, que recommandait le rapport de l'architecte du 20/10, parce qu'un conteneur Blob
  ne se monte pas dans Container Apps
  ([Storage mounts](https://learn.microsoft.com/en-gb/azure/container-apps/storage-mounts)). Pourquoi un
  adaptateur maison plutôt que SQLAlchemy Core, que time-knight avait recommandé le 05/11 : la doc
  du dialecte SQLite de SQLAlchemy 2.0 décrit, avec le pilote pysqlite, un « Incorrect behavior for
  SAVEPOINT » (le pilote n'ouvre une transaction qu'avant un ordre qui écrit) ; ses deux remèdes
  changent le moment du `BEGIN`, et il faudrait réécrire le `BEGIN` explicite de la lecture
  (`database/reading.py`), les savepoints (`database/savepoint.py`) et la prise des erreurs de
  l'import (`etl/load.py`), soit le code SQLite que décrit le livrable E1 (relecture du plan de
  mise en ligne, 06/11). L'adaptateur garde la branche SQLite telle quelle (`sqlite3.Connection`,
  sans enveloppe) et le SQL écrit pour `sqlite3` (décision du 2026-10-10 : `sqlite3` et SQL, pas
  d'ORM) : il traduit les marqueurs `?` et `:nom` selon la règle de SQLAlchemy 2.0.55, double les
  `%`, et un test fait passer chaque texte SQL de `database/` dans le traducteur. Plan validé par
  Sabine le 06/11 (commentaire de #417), dont ces choix :
  - le type de la connexion est l'union `sqlite3.Connection | PostgresConnection`. Écartés : un
    `Protocol` (une abstraction ouverte pour deux moteurs connus) ; envelopper aussi SQLite ;
  - les dates restent du texte UTC `AAAA-MM-JJTHH:MM:SSZ`, et les listes JSON du texte, contrôlés
    par `CHECK` (`schema_postgresql.sql`, à côté de `schema.sql`, qui fait foi) : les deux moteurs
    rendent les mêmes valeurs, et le SQL compare les dates en texte. Écartés : `timestamptz` et
    `jsonb`, que `docs/stockage.md` proposait : psycopg rendrait des `datetime` et des listes, et
    une ligne lue différerait d'un moteur à l'autre ;
  - la base PostgreSQL est créée hors de K-B (compose, Azure : #419, #421), en UTF8 et en collation
    C ; `kb create-db` en refuse une autre. Pourquoi C : `citext`, qui remplace `COLLATE NOCASE`,
    plie la casse selon la collation de la base, et en C celle des lettres ASCII seules, comme
    `NOCASE` (observé le 06/11). Écarté : `COLLATE "C"` colonne par colonne, qui ne règle pas
    `citext` ;
  - une entrée est rejetée seule sur les SQLSTATE 23514, 23505 hors clé primaire, 23502 et 22003,
    comme `sqlite3.IntegrityError` en SQLite (règle 1 de `conventions.md`, modifiée dans cette PR
    sur accord de Sabine) ; le motif d'un refus, comme la ligne de journal d'une erreur, garde la
    classe, le SQLSTATE et les noms que donne `diag` (table, colonne, type, contrainte), par
    `quote_value`, jamais un message de PostgreSQL : le message principal peut citer la valeur
    refusée (22003, 22P02), et le `DETAIL` recopie la ligne (revue de sécurité, tranché par
    time-knight le 06/11) ;
  - les lignes retirées (KEV, Zotero) se trouvent par une différence en Python, puis un `UPDATE`
    par clé, au lieu du `IN` généré que demandait #417 : un `IN` de plus de 32 766 paramètres
    lève « too many SQL variables » en SQLite (observé), une erreur du système qui arrêterait
    chaque import ;
  - un import à la fois, par un verrou consultatif (`pg_advisory_xact_lock`) attendu 5 s au plus,
    le délai de `sqlite3` ;
  - avec une base PostgreSQL, une variable que libpq lit en plus de l'URL (`PGHOST`, `PGPASSWORD`…,
    les 42 noms de sa doc) fait refuser la commande (code 2) : libpq la lirait en silence (règle 2
    de `poc.md`) ; `PGDATA`, que pose Homebrew, n'en est pas (précision de Sabine du 06/11) ;
  - `psycopg[binary]` entre seul dans cette PR ; `psycopg-pool` entre avec #418, qui s'en sert
    (décision 10 du plan de mise en ligne : chaque dépendance dans la PR qui en a besoin) ;
  - les tests sur PostgreSQL portent le marqueur `postgresql`, écarté de `uv run pytest`, et
    tournent dans un workflow à eux (`postgresql.yml`), sur PostgreSQL 18 épinglé par son digest :
    la version du Mac, disponible sur le serveur flexible d'Azure ; K-B demande 17 ou plus (`IS JSON`
    et `pg_input_is_valid` depuis 16, `pg_database.datlocale`, que lit `kb create-db`, et le
    fournisseur builtin depuis 17 ; revue de code, tranché par time-knight le 06/11).
    **Révisée le 2026-11-08** : ils tournent dans le job `tests-postgresql` de `ci.yml` (#464) ; le
    workflow à part évitait que deux PR ouvertes en même temps touchent le même fichier, ce qui ne
    tient plus.

  Ce qui reste ouvert après cette PR : la lecture sur PostgreSQL (`read_items`, l'API de données,
  le délai des requêtes, le verrou en tête des purges : #418) ; le compose de préproduction (#419) ;
  la base en ligne, ses rôles et son schéma par `caj-kb-migrate-database` (#421) ; les migrations
  (#186) ; la sauvegarde de la base, par un `pg_dump` planifié, puis la purge du brut couvert par
  deux sauvegardes saines (#390, Sabine, 06/11). Limites assumées : jusqu'à #418, `kb serve-data`
  lit le fichier SQLite pendant que `kb import` écrit dans PostgreSQL ; un commit perdu sur une
  coupure du réseau a une issue incertaine (le serveur a pu le valider), et `etl/load.py` efface
  alors le journal d'import (famille de #302) ; le digest de l'image de PostgreSQL de la CI se met
  à jour à la main, Dependabot ne suivant que les `uses:` ; deux schémas à tenir ensemble, dont la
  structure n'est pas encore comparée par un test (#418). — PR de #417, à venir

### Base : la base du Mac est jetable

- **La base SQLite du Mac ne passe pas en ligne : la base PostgreSQL en ligne repart du brut, par
  `kb create-db` puis `kb import`.** Décision de Sabine du 06/11 (« b »), raison non dite, entre
  deux options posées par la relecture du plan de mise en ligne : (a) copier la base du Mac dans
  PostgreSQL avec ses `id`, comme le prévoyait `docs/stockage.md` (chaque table copiée, puis sa
  séquence recalée par `setval`), un outil que K-B n'a pas, et que recommandait time-knight ; (b) la
  déclarer jetable. Sa suite, le même jour : « en ligne on aura un cron de pg dump […] et un autre
  systeme de purge automatique » (#390). Ce que la
  décision coûte : ce que le brut n'a plus est perdu, soit le brut de plus de 6 mois et les
  lignes de Zotero et de CISA KEV retirées avant le dernier fichier importé de leur catalogue, dont
  seul celui-là est gardé ; et les `id` techniques changent. **Inverse en partie** deux décisions : « en usage réel, la base est gardée
  et l'`id` technique des items reste stable » (2026-10-10), dont l'`id` change une fois, au passage
  en ligne ; et « la base devient la source de vérité » (2026-11-04), qui vaut pour la base en
  ligne, pas pour celle du Mac. `docs/stockage.md` (« Faire évoluer le schéma ») est corrigé dans la
  PR de #417. Limite assumée : la base du Mac garde des lignes que la base en ligne n'aura jamais.
  — PR de #417, à venir

### Base : pas de migration avant le premier changement de schéma en ligne

- **La base en ligne part vierge, et K-B n'a pas encore de migration : `kb migrate-database` (#421)
  pose le schéma sur une base vide et ne fait rien sur une base qui l'a déjà ; il ne lance pas
  `alembic upgrade head`. Les migrations Alembic (#186) attendent le premier changement de schéma de
  la base en ligne, et ne passent plus avant #421.** Décision de Sabine du 06/11 (vers 10:55 UTC,
  transmise par time-knight) : « pour le moment on a pas de migration. On repart d'une base de prod
  vierge ». Raison non dite au-delà de ces mots. **Révise** la décision du 2026-10-10 (« Les
  changements de schéma de la base d'usage réel passent par des migrations Alembic », dont la
  limite disait Alembic nécessaire à partir de l'installation locale) : Alembic n'est plus
  nécessaire avant le premier changement de schéma d'une base gardée. Ordre de l'axe PostgreSQL qui
  en découle : #418, #419, #202, puis #421 ; #186 plus tard. Limite assumée : le premier changement
  de schéma de la base en ligne attend #186 ; d'ici là, un changement de schéma n'a pas de chemin
  sur une base qui garde des données que le brut n'a plus (« Faire évoluer le schéma »,
  `docs/stockage.md`). — PR de #417, à venir

### Image : deux étapes, UID 10001, sans processus d'init (#200)

Plan validé par Sabine le 06/11 (I1 du plan de mise en ligne).

- **Une seule image pour toutes les commandes `kb` (`Dockerfile` à la racine), en deux étapes sur la même
  base, `python:3.13-slim-trixie` épinglée par digest. L'étape de construction installe l'environnement
  par uv 0.11.13, épinglé par digest lui aussi (`uv sync --locked --no-dev --no-editable`, les
  dépendances puis K-B). L'étape finale ne garde que `/app/.venv`, sans uv ni `src/`, et compile en `.pyc`
  la bibliothèque standard, que la base livre sans eux.** Pourquoi : l'image ne porte ni l'outil de
  construction ni les dépendances de développement. Avec la même base, l'environnement retrouve le Python
  vers lequel il pointe. uv 0.11.13 : uv construit K-B avec son propre backend, et sa version reste dans la
  plage de `build-system.requires` (`uv_build>=0.11.13,<0.12.0`), la version du Mac ; uv 0.13.6, prévu au
  plan, construisait hors de cette plage (relecture du 06/11). Sans les `.pyc`, chaque démarrage
  recompilait en mémoire environ 200 modules, que l'UID 10001 ne peut pas écrire. Une seule image : « une
  container app par service, un environnement » (18/10), chaque service lançant sa commande. Écartée :
  une étape unique, qui garderait uv et son cache dans l'image. **Révisée le 2026-11-08** : uv 0.13.6
  (`uv_build>=0.13.6,<0.14.0`), la même version dans l'image, dans la CI (`setup-uv`, jusque-là sans
  version, prenait la dernière, 0.13.7, hors de la plage, et le disait dans chaque job) et sur le Mac ;
  décision de Sabine : monter uv plutôt que fixer la CI sur 0.11 (#485). Sur le Mac, `uv self update
  0.13.6` lancé par Sabine le 2026-11-08 vers 12:30 UTC : `uv --version` rend « uv 0.13.6 (329bf9448
  2026-10-26 aarch64-apple-darwin) ». — PR de #200
- **Le dossier de données de l'image est `/var/lib/knowledge_base`, où se monte le volume.** Décidé par
  Sabine le 06/11 (« ok pour la convention linux »), à la place de `/data`, prévu au plan. Pourquoi : le
  Filesystem Hierarchy Standard range sous `/var/lib` « state information pertaining to an application »
  (FHS 3.0, § 5.8.1, lu le 06/11), et le nom reprend le dossier local `~/.knowledge_base`. — PR de #200
- **`KB_DATA_DIR` n'a pas de valeur dans l'image : elle se pose au lancement, avec le volume.** Tranché par
  Sabine le 06/11. Pourquoi : la règle 2 de `.claude/rules/poc.md` (sans `KB_DATA_DIR`, la commande
  échoue). Une container app ou un job déployé sans son montage refuse alors de démarrer (code 2), au
  lieu d'écrire dans un dossier éphémère de l'image ; la CI vérifie ce refus. Écartée : `ENV KB_DATA_DIR`
  dans l'image, prévue au plan, une exception à la règle (relecture du 06/11). — PR de #200
- **`kb` tourne sous l'UID et le GID fixes `10001`, propriétaires du dossier de données.** Pourquoi : jamais root,
  et `kb` écrit ses fichiers en `0600` (commentaire du 16/10 sur #200). Tout conteneur qui les lit doit
  tourner sous l'UID qui les a écrits, donc sous un UID connu d'avance. Écarté : un UID choisi au
  lancement, qui pourrait changer d'un conteneur à l'autre. Essai du 06/11 : sous cet UID, l'écriture
  par `write_file_atomically` dans un dossier du Mac monté sur `/data/raw` sort en 0 (#200). — PR de #200
- **Pas de processus d'init (ni tini ni `--init`) : `kb` est le PID 1, lancé en forme exec.** Mesure
  du 06/11 sur l'image : `docker stop` d'un `kb serve-data` prend 0,32 s, uvicorn s'arrête en entier et
  le code de sortie est 0. Avec `--init`, l'arrêt prend 0,28 s et le code est 143. Pourquoi : l'arrêt
  est propre sans init, et rien ne s'ajoute à l'image. Limite assumée : après SIGTERM, `kb serve-data`
  et `kb serve-ai` sortent en 0, pas en 143. uvicorn remet le gestionnaire par défaut, puis relance le
  signal, qu'un PID 1 ignore (tri de la PR #244, 18/10). Autre limite (revue de code du 06/11, tranché
  par time-knight, délégation de Sabine du 15/10) : en PID 1, une commande sans gestionnaire de
  SIGTERM l'ignore et finit en SIGKILL au bout du délai d'arrêt. C'est le cas de `kb create-db` et de
  `kb openapi` : seules les commandes de `COMMANDS_STOPPED_BY_SIGTERM` (`commands/sigterm.py`) en
  posent un. Une transaction ainsi coupée est annulée par la base, sans perte. Chaque commande lancée en
  job entre donc dans `COMMANDS_STOPPED_BY_SIGTERM` (règle 6 de `poc.md`) : `daily-routine` et
  `digest-watch` (#413), `migrate-database` (#421). — PR de #200
- **Ni `curl`, ni `azcopy`, ni `HEALTHCHECK` dans l'image.** Les transferts passent par
  `azure-storage-blob` (#412), et `/health` par httpx2 (décision de Sabine du 06/11). Les sondes sont
  celles d'Azure Container Apps (#414). — PR de #200
- **`.dockerignore` refuse tout par défaut : la construction ne reçoit que `pyproject.toml`, `uv.lock`,
  `README.md` et `src/`, moins les fichiers d'environnement, les bases (`*.sqlite*`), `__pycache__` et
  `.DS_Store` de `src/`.** Pourquoi : un constructeur distant (#415, s'il construit sur Azure) reçoit
  tout le contexte ; refuser par défaut garde sur le Mac `temp/` et `reports/` (données personnelles),
  `tests/`, `docs/`, `infra/`, et tout fichier nouveau. Et le backend de construction emballe tout
  fichier de `src/k_b/` : un `.env` ou une base laissés là entraient dans l'image (essai du 06/11, avant
  `.dockerignore`). Écartée : une liste d'exclusions, qui laissait partir tout le reste (revue de code du
  06/11, tranché par time-knight, délégation de Sabine du 15/10). — PR de #200
- **La CI construit l'image en `linux/amd64` sur chaque PR vers `main` et sur chaque push sur `main`,
  dans son propre workflow (`image.yml`, job `image-build`), et ne la pousse nulle part** (le registre et
  la livraison sont #415). Elle plante des fichiers que `.dockerignore` refuse, à la racine et dans
  `src/k_b/`, puis vérifie que le contexte de construction, écrit tel quel dans un dossier, ne contient
  que les quatre chemins copiés et aucun fichier planté, et que l'image n'en contient aucun. Elle
  contrôle aussi l'UID (≠ 0), le refus de démarrer sans `KB_DATA_DIR` (code 2), `kb --help` et
  `kb create-db` (le SQL du paquet installé). — PR de #200
- **Dependabot tient les digests des deux images de base, et leurs versions de correctif seulement, avec
  7 jours d'attente comme pour les actions.** Pourquoi : sur un tag à suffixe, il propose la plus haute
  version au même suffixe (dependabot-core, `docker/README.md`, « Semver », lu le 06/11) :
  `3.13-slim-trixie` passerait à `3.14-slim-trixie`, alors que `.python-version` dit 3.13, et uv sortirait
  de la plage de `uv_build`. Les montées mineures et majeures de `python` et d'`astral-sh/uv` sont donc
  ignorées. Une montée de Python ou de la plage d'`uv_build` lève la règle avec elle. — PR de #200

### Jobs : `kb smoke-test` et le paquet `jobs` (#412)

Choix de la session dans le plan validé par Sabine le 06/11 (commentaire de #412, parcours allégé).

- **Le code commun aux commandes des jobs d'ACA vit dans un paquet nouveau, `src/k_b/jobs/` :
  `exchange_storage.py` (le stockage d'échange, Blob, par l'identité managée) et `api_health.py`
  (`GET /health` des deux API). Seul `commands` l'importe, et il n'importe que `core` (tenu par
  `test_layers`).** Pourquoi : une couche sous `commands`, comme `post` pour l'API IA ; les deux API
  n'ont aucun accès au stockage d'échange (plan de mise en ligne du 06/11), la règle le rend visible
  dans le code. Écartés : `core/`, ouvert à toutes les couches, les deux API comprises ; `commands/`,
  qui mêlerait la présentation et les entrées/sorties (`code.md`, SoC) ; `post/`, le post-traitement
  de la veille. Limite assumée : `jobs` ne porte aujourd'hui que la liste d'un conteneur ; l'envoi et
  le téléchargement viennent avec #413, qui les appelle (pas de code sans appelant). — PR de #412

- **Le journal de `kb` tient les loggers `azure` et `urllib3` à ERROR (`LIBRARY_LOG_LEVELS`,
  `logging_to`, `commands/run_log.py`), `httpx2` restant à WARNING.** Pourquoi, observé avec
  azure-core 1.41.0 : à INFO, `HttpLoggingPolicy` écrit `Request URL: '…/<conteneur>/<blob>'` pour un
  transfert, donc le nom d'un clip, qui est son titre (règle 5 de `poc.md`) ; une liste n'y écrit que
  le conteneur. À WARNING, `azure.identity` écrit deux fois l'échec d'un jeton avec le texte de la
  réponse, sans `quote_value` (un `\n` y fabrique une fausse ligne de `kb`), et
  `storage/blob/_generated/_utils/serialization.py` des valeurs de la réponse ; `urllib3` peut écrire
  une URL entière (`urllib3/connection.py`, « Failed to parse headers »). À ERROR, ces bibliothèques
  n'écrivent que des textes fixes, sauf `storage/blob/_shared/avro/avro_io.py:166`, qui y écrit des
  octets d'une réponse avro qu'aucune liste n'atteint (à revoir par #413 s'il lit un flux avro) ; et
  `kb` journalise lui-même chaque échec, une fois (règle 3 de `conventions.md`). Revue de code,
  tranché par time-knight le 06/11 (délégation de Sabine du 15/10), sur le verdict d'un sous-agent
  neuf. Écartés : WARNING, le niveau de `httpx2` (le premier choix du
  plan, qui laissait passer ces lignes) ; `azure.identity` seul (le stockage écrit aussi des valeurs) ;
  un filtre de masquage des URL (plus de code pour le même effet). Limite assumée : les avertissements
  de `urllib3` sont aussi perdus pour les autres sources qui passent par `requests` ; les lignes des
  autres bibliothèques (BigQuery, OpenTelemetry) restent non échappées, un défaut déjà sur `main`,
  porté par #441. — PR de #412

- **Une erreur du stockage est nommée par son état (`exchange_storage_forbidden`, `_not_found`,
  `_unauthorized`, `_unavailable`, `_no_token`, `_failed`), son statut HTTP et son code (`x-ms-error-code`,
  gardé s'il est un mot de lettres), jamais par `str(error)` ; rien du SDK n'est chaîné (`from
  None`). L'état du stockage se lit au statut, pas à la classe. Le jeton est demandé à part
  (`check_identity`) : tout échec de l'identité est `exchange_storage_no_token`, refus ou panne,
  réponse qui n'est pas un objet JSON comprise (une 500 en HTML lève `JSONDecodeError`, une liste
  `AttributeError`, hors des `AzureError`) ; un 401 du stockage reste `exchange_storage_unauthorized`
  (deux revues de code, tranché par time-knight le 06/11, délégation de Sabine du 15/10).** Pourquoi : le message du SDK recopie le corps de la réponse, qui
  peut citer le chemin d'un blob (`AuthenticationErrorDetail`) ; le SDK lève
  `ClientAuthenticationError` pour une 403 `AuthenticationFailed`
  (`azure/storage/blob/_shared/response_handlers.py`) ; le diagnostic utile d'un job en ligne est
  « l'identité » ou « le rôle » ; et la classe d'une erreur d'azure-identity ne distingue pas un
  refus d'une panne (une 500 en JSON est `CredentialUnavailableError`, comme un client id inconnu),
  sans porter le statut du point d'accès (azure-identity 1.27.0, observé le 06/11). Écartés :
  `quote_value(str(error))`, qui garderait le début du nom ; deux états pour l'identité
  (`…_unauthorized` et `…_identity_unavailable`, premier tri de la revue), qui suivaient la classe et
  non ce qu'avait fait le point d'accès.
  — PR de #412

- **Réglages de `kb smoke-test` : `AZURE_CLIENT_ID` (un GUID, passé en `client_id=`) et
  `KB_EXCHANGE_BLOB_URL` (en `https`) sans défaut ; le conteneur d'essai est une constante,
  `SMOKE_TEST_CONTAINER = "smoke-test"`, créé par #414. Le transport du SDK ne lit ni proxy ni
  certificat de l'environnement (`RequestsTransport(use_env_settings=False)`) et ne suit aucune
  redirection (`permit_redirects=False`), comme `open_http_client` ; il attend 20 s une connexion et
  60 s une lecture, les délais que le SDK de stockage ne pose que s'il construit lui-même son
  transport (sans eux, 300 s : revue de code, tranché par time-knight le 06/11, délégation de Sabine
  du 15/10). `/health` : 60 s de lecture, une échéance de 65 s (connexion puis lecture), corps de
  1 Kio au plus, `{"status":"ok"}` exact, sans nouvel essai.** Pourquoi : sans
  `client_id`, `ManagedIdentityCredential` cherche l'identité système, que les jobs de K-B n'ont pas ;
  aucune valeur locale n'existe pour un compte Azure (règle 2 de `poc.md`, comme `KB_LLM_BASE_URL`) ;
  rien ne change le conteneur d'un déploiement à l'autre. Écarté : une variable pour le conteneur.
  Limite assumée : les 60 s sont une hypothèse (le réveil d'une API à 0 réplique), à mesurer à #414 ;
  les nouvelles tentatives du stockage restent celles du SDK (3, après environ 18, 24 et 42 s, à 3 s
  près, mesuré le 06/11) : environ 7 min quand chaque essai attend son délai, sans trace au journal,
  le logger `azure` étant tenu à ERROR. Ce n'est pas une borne : le délai de lecture borne chaque
  lecture, pas une réponse, et les nouvelles tentatives d'azure-identity n'y sont pas comptées
  (seconde revue de code). — PR de #412

### API de données : la lecture sur PostgreSQL (#418)

- **Sur PostgreSQL, l'API de données lit par un pool (`psycopg-pool` 3.3.3, publiée le 2026-09-22),
  ouvert par `kb serve-data` : 1 à 4 connexions, chacune en `REPEATABLE READ READ ONLY`, avec le
  délai de 5 s comme `statement_timeout` de sa session, posé par K-B à son ouverture. Un dépassement
  (SQLSTATE 57014) répond le même 503 `query_timeout` qu'en SQLite ; une requête qui n'a pas de
  connexion en 2 s répond 500 `database_error`.** Plan validé par Sabine le 06/11 (commentaire sur
  #418) ; `psycopg-pool` accordé par Sabine le 06/11. **Révise le « Pour #418 » de l'entrée de #331**
  (« un délai par requête », ci-dessus), qui posait le délai par `ALTER ROLE … SET
  statement_timeout`, côté serveur : une recommandation de la session de #331, pas une décision de
  Sabine ; accord de time-knight du 06/11. Ce qui a changé : le rôle de l'API n'existe pas avant
  #421, et la valeur posée par K-B est la même pour les deux moteurs, dans le dépôt, prouvée en CI ;
  sans réglage du serveur, la lecture n'est jamais sans délai. Pourquoi un pool : une connexion par
  requête refait TLS et l'authentification à chaque requête. Pourquoi `REPEATABLE READ` : les
  trois lectures du détail voient un seul état de la base, ce que le `BEGIN` de SQLite tenait ;
  `READ ONLY` : une écriture est refusée par le serveur, avant le rôle en lecture seule de #421.
  Le pool se connecte en arrière-plan, pour que `kb serve-data` démarre sans attendre la base,
  comme en SQLite ; il vérifie chaque connexion avant de la prêter (une connexion coupée par un
  redémarrage ou une bascule n'est pas servie), et chaque connexion lui revient sans transaction.
  2 s d'attente plus 5 s d'instruction restent sous les 10 s du client de l'API IA (un test).
  Un délai de moins d'1 ms est refusé : à 0, `statement_timeout` n'arrête plus rien. `psycopg` et
  `psycopg_pool` sont tenus à ERROR (`LIBRARY_LOG_LEVELS`), comme `azure` et `urllib3` (#412) : à
  WARNING, ils citent le texte de libpq et la connexion (hôte, utilisateur, base). Écartés :
  `ALTER ROLE` (la valeur hors du dépôt, un oubli à l'installation laisse la lecture sans délai) ;
  `options=-c statement_timeout` dans l'URL (refusé par un pooler comme PgBouncer) ; `SET LOCAL` à
  chaque requête (utile seulement derrière un pooler en mode transaction, que #421 ne prévoit pas) ;
  `transaction_timeout` (il ferme la session, FATAL) ; `SET TRANSACTION` après le `BEGIN` de
  psycopg (l'isolement écrit à deux endroits) ; fermer le pool dans le `lifespan` de FastAPI (rien
  à y gagner en lecture seule, et chaque test de l'API devrait entrer dans le `TestClient`) ; un 503
  propre à l'attente du pool (un code de plus au contrat) ; un `NullHandler` dans `postgresql.py`
  (une seconde façon de taire une bibliothèque). Limites assumées : le délai compte par
  instruction, et le détail en fait jusqu'à trois (15 s en théorie, au-delà des 10 s du client) ;
  une annulation par un administrateur (`pg_cancel_backend`) répond aussi 503 `query_timeout` ;
  une base injoignable (mot de passe, port, `sslmode`) ne se voit qu'en `PoolTimeout` à chaque
  requête ; sur SIGTERM, uvicorn relance le signal et le processus meurt sans fermer le pool : le
  système ferme ses sockets, et une lecture seule n'a rien à perdre ; un `SET` de session ne tient
  pas derrière un PgBouncer en mode transaction (« For #421 » de la PR). — PR de #418

- **La recherche `q` ignore la casse par `lower(champ) LIKE lower(:pattern) ESCAPE '\'`, le même
  SQL sur les deux moteurs.** Plan validé par Sabine le 06/11. Pourquoi : `LIKE` ignore la casse des
  lettres ASCII en SQLite et la respecte en PostgreSQL ; `lower()` ne plie que les lettres ASCII, en
  SQLite comme en PostgreSQL dans la collation C que `kb create-db` exige, et rend donc en
  PostgreSQL les résultats de SQLite (le tableau de « Recherche `q` », `docs/specs-api.md`, vérifié
  le 06/11 sur PostgreSQL 18.4). Écartés : `ILIKE`, propre à PostgreSQL (règle 1 de `poc.md`) ;
  `citext` sur les titres et les résumés (un changement de schéma) ; plier le motif en Python, car
  `str.lower` plie aussi `É`, alors que la base ne le plie pas. Limite assumée, inchangée : une
  lettre accentuée ne se trouve que dans sa casse exacte. — PR de #418

### Mise en public du dépôt (#278)

- **L'historique git est rendu public tel quel, et consigné ici et au registre (« Dépôt public »).**
  Décision de Sabine du 06/11, sur le relevé de #278 (voie « l'accepter et le consigner »). Ce qui
  reste lisible dans l'historique : l'adresse personnelle de l'autrice (1 354 commits) et celle de
  l'organisme de formation (32 commits, 2 tags annotés), dans les métadonnées seulement ; le chemin du
  compte macOS, dans 3 fichiers de l'historique ; 23 lignes `Claude-Session:` ; les contenus de tiers d'avant leur
  déplacement ou leur retrait ; 13 commits que les refs ne montrent plus (anciens force-push, branches
  supprimées), que GitHub sert par leur SHA. Aucun secret : gitleaks 8.30.1 ne trouve que des faux
  positifs. Pourquoi, selon Sabine (06/11) : les deux autres voies changent tous les SHA, dont ceux que
  citent les rapports de la certification ; et l'historique (les PR, les revues de code et leurs
  comptes rendus) montre la façon de travailler sur le projet. Écartés : réécrire par `git filter-repo`, puis faire
  purger `refs/pull/*` et les commits hors des refs par le support de GitHub (branches réécrites, pistes
  en cours à rebaser, purge par le support qui prend des jours) ; repartir d'un nouveau dépôt (issues
  à transférer, PR et comptes rendus de revue perdus, board, CI et réglages à refaire, lien du jury
  changé). Décisions du même jour : les commits à venir gardent la même adresse ; le nom `time-knight`
  reste dans le dépôt, les issues et les PR (aucun lien vers ce dépôt privé, ses 2 chemins corrigés) ;
  les anciennes versions des textes GitHub corrigés ne sont pas supprimées ; le wiki, sans page, est
  désactivé. Limite assumée : un clone fait après la bascule garde tout ce qui précède. — PR de #278
  (documentation)

- **Une fixture qui reprend le texte d'autrui garde la forme d'un exemple collecté, avec un texte
  écrit pour l'occasion ; les auteurs arXiv des fixtures deviennent des noms fictifs, les logins GitHub
  sont gardés.** Décision de Sabine du 06/11, sur la recommandation de la session. **Précise la
  consigne du 2026-10-10** (« une fixture part d'un exemple issu de la collecte ») : la structure vient
  toujours de la collecte, le texte non, quand sa licence ne permet pas de le publier ; les chaînes
  que les tests assertent sont réécrites avec la fixture. Les noms propres (produits, pays) restent :
  ce sont des faits, et des tests s'en servent (un nom qui ne doit pas fuir dans les traces, le fait
  que cite l'article piégé ; choix de la session, PR 2). Pourquoi : la newsletter TLDR n'a aucune
  condition d'utilisation trouvée (droits réservés par défaut) et l'auteur d'un article Medium garde
  ses droits. Les noms fictifs des auteurs arXiv : décision de Sabine du 06/11, sur la recommandation
  de time-knight ; pourquoi : les auteurs sont des données personnelles pour K-B (règle 3 de
  `conventions.md`, registre), et aucun test n'a besoin des vrais noms (minimisation), bien que leurs
  métadonnées soient sous CC0. Gardés, avec leur
  licence au README (« Contenus de tiers ») : WCAG 2.2 (W3C Document License), une page de l'OWASP
  (CC BY-SA 4.0), les avis de sécurité de GitHub (CC BY 4.0), les métadonnées arXiv et le catalogue
  KEV (CC0 1.0), les métadonnées de dépôts GitHub (logins compris : donnée publique, finalité de
  test). Retirées de l'arbre : les notes d'une vidéo YouTube dont la source n'est pas citée. Écartée :
  l'autre option posée par #278, un texte pris sous une licence compatible (raison non dite). — PR de
  #278

- **Le schéma de Zotero recopié dans `tests/fixtures/zotero_extract.sql` est gardé, avec la mention
  de sa licence, l'AGPL v3 ou plus.** Décision de Sabine du 06/11, sur la recommandation de la
  session. L'en-tête de `resource/schema/userdata.sql` (dépôt `zotero/zotero`, lu le 06/11) dit :
  © 2009 Center for History and New Media, George Mason University, AGPL v3 ou plus. Pourquoi : le
  test de fidélité au schéma réel garde sa force. Écarté : réduire la fixture aux colonnes que lit
  K-B (le test ne verrait plus un changement du schéma réel). Limite : la fixture est sous AGPL dans
  un dépôt sous CC BY-NC 4.0 ; la compatibilité des deux n'est pas tranchée par un juriste. Clôt la
  décision ouverte du 2026-10-11 (« Licence du schéma de Zotero »). — PR de #278

### Mise en ligne : le squelette de K-B sur Azure (#414)

Choix de la session dans le plan validé par Sabine le 06/11 (parcours complet), sauf mention. Appliqué par
Sabine le 06/11 ; les mesures viennent de `log-kb`.

- **Un seul `main.bicep`, appliqué en deux passes que pilote le paramètre `imageTag`. Vide, il pose le socle :
  journaux, environnement, identités, registre et ses rôles AcrPull, coffre, stockage d'échange, budget. Avec
  une étiquette, il ajoute les deux API, le job et les rôles du coffre par secret.** Pourquoi : une app ne se
  crée qu'une fois son image dans le registre et ses secrets dans le coffre ; et AcrPull, donné en passe 1, a
  propagé quand vient la passe 2. Écartés : deux fichiers Bicep, qui déclareraient deux fois les mêmes noms ;
  des secrets factices posés par Bicep, qu'un nouveau passage écraserait. Limite assumée : un rôle du coffre
  peut mettre jusqu'à 10 min à propager, et une passe 2 refusée se relance par la même commande
  (`infra/README.md`, « Appliquer »). — PR de #414

- **Les deux API à 0 réplique au repos, 1 au plus.** Décision de Sabine du 06/11, sur la recommandation de la
  session. Pourquoi : avec PostgreSQL et le registre, 0 réplique tient sous le budget de 30 € par mois
  (environ 27 $), et 1 le dépasse (environ 47 $). Clôt la décision ouverte du 2026-11-05 (« `minReplicas` des
  deux API »). Mesuré le 06/11 sur l'exécution `caj-kb-smoke-test-us77d03`, les API au repos depuis plus de
  300 s :
  - l'API de données répond 26 s après la première demande, et l'API IA 20 s après ;
  - le test dure 50 s, contre 1 s quand les API sont éveillées ; l'image se tire en 4 s environ ;
  - l'hypothèse des 60 s de lecture de `/health` (#412) tient, avec une marge d'environ ×2,3.

  Limites assumées :
  - le compte du débit (#161) repart de zéro à chaque réveil ;
  - pendant un déploiement, l'ancienne et la nouvelle révision tournent ensemble : deux répliques, chacune avec
    son compte, si bien qu'un client peut brièvement passer jusqu'au double de sa limite (revue de code de la
    PR #451, tranché par time-knight le 06/11, délégation de Sabine du 15/10) ;
  - le client de l'API IA vers l'API de données lit en 10 s au plus, sans nouvel essai
    (`DATA_API_READ_TIMEOUT_SECONDS`). Une fiche demandée pendant que l'API de données dort échoue donc. Moyen
    proposé à #413 : un `GET /health` des deux API avant les fiches ; une API reste éveillée 300 s après sa
    dernière demande, le délai par défaut d'ACA. — PR de #414

- **Registre : Azure Container Registry Basic (`crkb` et le suffixe), en France Central. Pas de compte admin.
  Chaque pièce tire l'image par son identité (AcrPull), et le mode des rôles est fixé à
  `LegacyRegistryPermissions`.** Décision de Sabine du 06/11, sur la recommandation de la session. Pourquoi :
  l'image se tire par identité managée, sans aucun secret, pour 5,07 $ par mois. Écarté : le registre de
  GitHub (GHCR), gratuit pour un paquet public. ACA n'y tire pas par identité managée : il faudrait un jeton
  GitHub, rangé dans le coffre et à renouveler, et l'image serait hébergée hors de l'UE. Le mode des rôles est
  fixé parce que le mode ABAC d'ACR, bientôt le défaut, ignore AcrPull. Sabine pousse l'image depuis une copie
  propre de `main`, avec le SHA court du commit pour étiquette, par `docker buildx build --platform
  linux/amd64 --push`. Écarté : `az acr build`, suspendu sur les crédits gratuits. — PR de #414

- **Coffre `kv-kb` (et le suffixe) en RBAC. Un rôle Key Vault Secrets User par secret et par identité (7
  rôles), Secrets Officer pour Sabine. Suppression réversible pendant 7 jours, sans protection contre la purge.
  Les apps lisent les secrets par des références sans version.** Pourquoi un rôle par secret : l'API de
  données ne lit que `kb-data-api-key-ai-digest`, un secret qu'elle partage avec l'API IA, et un coffre par
  app obligerait à le copier. C'est un écart à la recommandation de Microsoft, qui supporte ce rôle mais
  conseille un coffre par application. Pourquoi 7 jours : le réglage est irréversible, Sabine ne peut pas
  purger, et un nom gardé 90 jours bloquerait une recréation. La protection contre la purge est irréversible
  elle aussi. Sabine pose les secrets par `read -rs` et `--file`, avec `-o none` : la valeur ne passe ni par
  l'historique ni par l'écran. Limites assumées : on ne récupère un secret supprimé que pendant 7 jours ; une
  nouvelle valeur atteint une app en 30 min au plus. Un conteneur qui tourne garde ses variables, et un
  redémarrage automatique n'est pas vérifié. Après une rotation, on redémarre donc la révision de chaque app
  qui lit le secret (`infra/README.md`, « Poser les secrets »). Pour `kb-data-api-key-ai-digest`, lu par les
  deux API, les deux valeurs peuvent différer jusqu'à 30 min, et l'API IA reçoit alors 401 (revue de code de la
  PR #451, tranché par time-knight le 06/11, délégation de Sabine du 15/10). — PR de #414

- **Les deux API sont internes : `https://<app>.internal.<defaultDomain>`, `allowInsecure: false`. Le
  trafic entre apps est chiffré (`peerTrafficConfiguration`), le mTLS reste coupé, et `cae-kb` garde
  `publicNetworkAccess: 'Enabled'`.** Pourquoi : le client de K-B ne suit aucune redirection, et l'API IA
  envoie sa clé à l'API de données. Le mTLS est coupé parce que ce qu'il ajoute au chiffrement n'est pas
  documenté. `Disabled` n'accepterait que des points de terminaison privés, qui demandent un VNet, absent
  (décision réseau du 06/11). Vérifié : `external: false` pour les deux, et le job joint les deux `/health`
  par leur nom interne. Limite assumée : le coffre, le registre et le stockage restent joignables sur
  Internet, sous Entra ID ; seul un VNet les fermerait. — PR de #414

- **Les sondes (démarrage, disponibilité, vie) font un `GET /health`. Celles de l'API de données portent
  l'en-tête `Host` de son nom interne, seul nom de `KB_DATA_API_ALLOWED_HOSTS`.** Pourquoi : par défaut, une
  sonde envoie l'IP du pod en `Host`, ce que l'API de données refuse, `/health` compris. La sonde de
  démarrage attend 1 + 6 × 10 s au plus : `failureThreshold` est plafonné à 10, et le plan prévoyait
  2 s × 30. Vérifié : aucune ligne `route=/health` dans les journaux des API, et une révision saine.
  Écartées : des sondes TCP, le repli prévu. — PR de #414

- **Un délai d'arrêt de 250 s pour l'API IA, le défaut de 30 s pour l'API de données.** Pourquoi : 240 s
  pour la plus longue demande que laisse passer l'entrée d'ACA, 6 s au plus pour les exports de fin, et une
  marge. Les requêtes de l'API de données sont bornées à 5 s. Limite assumée, pour #413 : un job n'a pas de
  délai d'arrêt réglable. — PR de #414

- **Les journaux vont dans `log-kb` (30 jours, 0,2 Go par jour au plus) par `azure-monitor` et un paramètre
  de diagnostic de `cae-kb`, une table par catégorie (`Dedicated`).** Pourquoi : la destination
  `log-analytics` mettrait la clé partagée de l'espace dans la configuration, et le plafond borne un
  emballement. Observé : Azure relit `logAnalyticsDestinationType` vide, mais les lignes arrivent bien dans
  `ContainerAppConsoleLogs` et `ContainerAppSystemLogs`. Limite assumée (risque accepté par Sabine le 06/11,
  à revoir avec #413 et #420) : les lecteurs de l'abonnement lisent `log-kb`, tirent sans doute l'image et
  voient la configuration des apps, sans les valeurs du coffre (registre, « Hébergement sur Azure »). —
  PR de #414

- **Une identité par pièce (`id-kb-ai-api`, `id-kb-data-api`, `id-kb-smoke-test`). Celles des API servent au
  tirage et au coffre, pas au conteneur (`identitySettings.lifecycle: 'None'`) ; celle du job lui est donnée
  par `AZURE_CLIENT_ID`.** Le stockage d'échange refuse la clé partagée, et le job n'y est que Storage Blob
  Data Reader, sur le seul conteneur `smoke-test`. #420 complète le compte. — PR de #414

- **Le job `caj-kb-smoke-test` se lance à la main, avec un `replicaTimeout` de 900 s et sans nouvel essai
  (`replicaRetryLimit: 0`).** Pourquoi 900 s : les bornes du job doivent tomber avant l'arrêt forcé, sinon
  l'échec nommé de #412 se perd. Elles font environ 576 s, soit deux `/health` de 65 s, les nouvelles
  tentatives du SDK de stockage (environ 7 min, #412) et le démarrage du job, sans compter les nouvelles
  tentatives d'azure-identity (`core/config.py`). Le coût ne compte qu'en cas de blocage. Le plan disait 600 s ;
  porté à 900 s par la revue de code de la PR #451 (tranché par time-knight le 06/11, délégation de Sabine du
  15/10), et appliqué en ligne par la passe suivante, celle de #421. Pourquoi sans nouvel essai : un échec doit
  se voir, et Sabine relance à la main. Écarté : 1
  nouvel essai, que Microsoft recommande pour la maintenance. Confirmé au déploiement : le nom d'un job tient
  sous 32 caractères, en minuscules, chiffres et `-`. Limite assumée, pour la CD de #415 : le droit
  `jobs/start/action` permet de changer l'image et les variables au lancement, donc de se servir de
  l'identité du job. — PR de #414

- **Les noms suivent les préfixes du Cloud Adoption Framework, suivis de `kb`. Un suffixe
  `take(uniqueString(resourceGroup().id), 8)` termine les noms uniques sur Azure, sans environnement ni
  région (`infra/README.md`, « Noms des ressources »).** Pourquoi 8 caractères : `stkbexchange` et
  13 caractères dépasseraient les 24 d'un compte de stockage. — PR de #414

- **Le `cooldown` de Dependabot ne joue pas sur ghcr.io, qui ne donne pas la date d'une version : une mise à
  jour de l'image `astral-sh/uv` arrive aussitôt (« Cooldown could not be applied », #444). La date d'une
  version se vérifie à la main avant de fusionner** (commentaire de `.github/dependabot.yml`). Gardé dans
  #414 sur la décision de tn-orchestrateur du 06/11. — PR de #414

### Base en ligne : Entra seul, un jeton à chaque connexion (#421)

- **En ligne, K-B ouvre la base PostgreSQL sans mot de passe : sous `KB_DATABASE_AUTH=entra`, chaque
  connexion nouvelle, celles du pool comprises, présente comme mot de passe un jeton de l'identité
  managée d'`AZURE_CLIENT_ID` (`ManagedIdentityCredential`, portée
  `https://ossrdbms-aad.database.windows.net/.default`), et K-B refuse alors une URL sans
  `sslmode=verify-full` ou qui porte un mot de passe. Le serveur coupe l'authentification par mot de
  passe.** Entra seul et sans VNet : décisions 2 et 1 du plan de mise en ligne du 06/11 (hors du
  dépôt, recopiées dans #421). Le reste : plan de #421 validé par Sabine le 06/11 (commentaire de
  l'issue), relu par un sous-agent ; les raisons ci-dessous sont celles du plan. Pourquoi
  `verify-full` exigé : le jeton est un secret porteur ; sans vérification du certificat, libpq
  l'enverrait à un serveur qui se fait passer pour celui de K-B (« For #421 » des PR de #440 et #446).
  Pourquoi un jeton par connexion : il vit une heure environ ; le pool reçoit ses paramètres de
  connexion par une fonction (`kwargs` appelable de `psycopg_pool` 3.3.3), et son `max_lifetime` par
  défaut (3 600 s) borne la vie d'une session. Pourquoi une variable explicite : déduire Entra
  d'`AZURE_CLIENT_ID` ou d'`IDENTITY_ENDPOINT` le rendrait implicite ; et `entra` sans
  `KB_DATABASE_URL` est refusé, au lieu du fichier SQLite du dossier de données : le job écrirait sa
  base sur son disque éphémère et dirait « database created » (revue de code, tranché par time-knight
  le 06/11, délégation de Sabine du 15/10). Le certificat se vérifie contre
  le magasin de l'image, `sslrootcert=/etc/ssl/certs/ca-certificates.crt` (vérifié dans `k-b:ci` le
  06/11 : DigiCert Global Root G2 et Microsoft RSA Root Certificate Authority 2017 y sont). Un jeton
  que l'identité ne donne pas devient `DatabaseNoTokenError`, une `psycopg.OperationalError` sans le
  texte du SDK, que chaque commande prend par `except ENGINE_ERRORS`. Écartés : la sous-classe de
  `psycopg.Connection` de l'exemple de Microsoft (plus de code pour le même effet) ; un mot de passe
  dans le Key Vault (décision 2) ; `sslrootcert=system` (dépend de l'`OPENSSLDIR` de la libssl que
  psycopg-binary embarque) ; un certificat versionné dans le dépôt (à suivre à chaque rotation
  d'Azure). Limites assumées : le transport et l'identifiant client sont écrits une seconde fois,
  après `jobs/exchange_storage.py`, la base ne pouvant importer les jobs (règle 5 de
  `conventions.md`), mis en commun à la troisième (accord de time-knight du 06/11) ; aucune source
  officielle ne dit qu'une session survit à l'expiration de son jeton, `max_lifetime` la borne ; les
  tests prouvent ce que libpq reçoit, pas que le serveur le vérifie (le serveur de test est en
  `trust`), mais en ligne, le 06/11, le serveur a accepté le jeton du job et celui de l'API, mot de
  passe coupé (critères de #421, `infra/README.md`) ; le code du conteneur de `ca-kb-data-api` obtient des jetons d'`id-kb-data-api`, donc de
  tous ses droits : `kb_reader`, AcrPull sur le registre et Key Vault Secrets User sur
  `kb-data-api-key-ai-digest`, déjà dans son environnement (`identityLifecycle: 'Main'`, l'API IA gardant
  `'None'`). Sans `'Main'`, chaque connexion échoue en `database_no_token` (revue de code, R1). Écartée :
  une seconde identité réservée à la base (une identité, un rôle et du SQL de plus pour un gain presque
  nul). Risque accepté par Sabine le 06/11, sur la recommandation de time-knight. — PR de #421, à venir

### Base en ligne : trois rôles, posés par l'administratrice (#421)

- **La base en ligne a trois rôles : `id-kb-migrate-database`, celui du job
  `caj-kb-migrate-database`, crée les tables et en est propriétaire ; `id-kb-data-api` lit, par le
  groupe `kb_reader` (`SELECT`) ; `kb_writer` (`SELECT`, `INSERT`, `UPDATE`, `DELETE`) attend
  l'identité de la routine quotidienne (#330). Aucun autre rôle ne se connecte à la base ni n'y crée
  rien. La base `kb` et les rôles se créent en SQL, une fois, par l'administratrice Entra du serveur
  (`infra/postgresql/`) ; `kb migrate-database` pose les droits sur les tables dans la transaction qui
  les crée.** Les trois rôles et leurs droits : contenu de #421 (lecture seule pour l'API, parce que
  le registre affirme que « l'API ouvre la base en lecture seule »). `kb_writer` créé ici, son membre
  `id-kb-daily-routine` et son `GRANT` dans #330 : décision de Sabine du 06/11 vers 15:28 UTC,
  transmise par time-knight, raison non dite. Le reste : plan validé par Sabine le 06/11, raisons du
  plan. Chaque rôle d'identité est rattaché par l'identifiant de son principal de service
  (`pgaadauth_create_principal_with_oid`), pas par son nom : une identité d'un autre groupe de
  l'annuaire de l'école peut porter le même. `REVOKE ALL ON DATABASE` et `REVOKE CREATE ON SCHEMA
  public` à `PUBLIC` : sur Azure, tout rôle peut créer dans `public` (Microsoft Learn, « Access
  management », lu le 06/11). L'administration de la base passe avec `search_path` à `pg_catalog`
  seul (`SET` en tête de `grant-roles.sql`, `PGOPTIONS` devant chaque `psql` du README) : le rôle du
  job peut créer des fonctions et des opérateurs dans `public`, et l'un d'eux, plus proche d'un appel
  que celui de `pg_catalog`, s'exécuterait avec les droits de l'administratrice (CVE-2018-1058 ;
  revue de sécurité, tranché par time-knight le 06/11, prouvé par un test qui pose un
  `public.format(text, name)`). La base se crée depuis `template0`, en UTF8 et en collation C, que
  `kb migrate-database` vérifie ; écarté : la créer par le Bicep, dont la doc ne dit pas qu'il pose
  `LC_CTYPE`. Les droits sur les tables (`grants_postgresql.sql`) sont posés par leur propriétaire, à
  la création ; écartés : l'identité de migration administratrice Entra (membre d'`azure_pg_admin`,
  bien au-delà du DDL) ; `ALTER DEFAULT PRIVILEGES` (utile à une table ajoutée plus tard, donc à
  #186, pas à une base créée en une transaction) ; les droits dans `schema_postgresql.sql` (`kb
  create-db` voudrait alors les rôles en local). `kb migrate-database` est le mode « créer si
  absente » de « Base : pas de migration avant le premier changement de schéma en ligne » (ci-dessus) :
  une base qui a ses tables n'est pas touchée, code 0 ; sinon, réglages vérifiés, puis schéma, sources
  et droits dans une transaction. Écartés : relancer les `GRANT` à chaque exécution (la seconde
  écrirait au catalogue, contre le critère de #421) ; un verrou consultatif (de deux migrations à la
  fois, la seconde échoue sur la table déjà créée, en 23505 sur `pg_type`, et rien n'est écrit à
  moitié, le DDL de PostgreSQL étant transactionnel ; la relance dit « unchanged » ; le verrou
  PostgreSQL d'une seconde commande `kb` est #426). Limites assumées : une table ajoutée à la base en ligne n'a de
  droits que par une migration (#186) ; les deux scripts d'administration se lancent à la main, et la
  livraison continue ne les rejoue pas ; `grant-roles.sql` est testé tel quel, `create-principals.sql`,
  propre à Azure, ne l'est pas ; la lecture seule d'`id-kb-data-api` ne vaut que dans `kb` : dans
  `postgres`, la base du serveur, les identités gardent `CONNECT` et `TEMPORARY` (les droits de `PUBLIC`
  par défaut dans PostgreSQL), de quoi remplir le disque de 32 Gio que `postgres` partage avec `kb`,
  mais pas `CREATE` sur son schéma `public` (lu en ligne le 06/11 : `t|f|azure_pg_admin`, `postgres`
  appartenant à `azure_pg_admin`) ; `postgres` ne porte aucune donnée de K-B (revue de sécurité, S2 ;
  risque accepté par Sabine le 06/11 vers 17:12 UTC, sur la recommandation de time-knight). Le critère 3
  de `infra/README.md` le lit en lecture seule ; un `t` en ligne ouvre une issue de suite, qui révoque
  `TEMPORARY` et `CREATE`, jamais `CONNECT` : l'administratrice se connecte à `postgres` pour lancer
  `create-principals.sql`, peut-être par le seul `CONNECT` de `PUBLIC` (non vérifié) ; retirer
  `TEMPORARY` ou `CREATE` ne coupe l'accès de personne.
  — PR de #421, à venir

### Base en ligne : le serveur (#421)

- **Le serveur est un PostgreSQL 18 flexible `Standard_B1ms` (Burstable), 32 Gio sans croissance
  automatique, sauvegardes 7 jours sans géoredondance, sans haute disponibilité, en accès public avec
  la seule règle « services Azure » ; `log_error_verbosity = TERSE` ; ni PgBouncer, ni `ALTER ROLE …
  SET statement_timeout`.** Taille, accès public et sauvegardes : contenu de #421 (B1ms, environ
  16 €/mois d'après le plan de mise en ligne, sous le budget de 30 €). Le reste : plan validé par
  Sabine le 06/11. Pourquoi « services Azure » : les adresses de sortie de Container Apps ne sont pas
  fixes ; la règle ouvre aussi le serveur aux autres clients d'Azure, et c'est l'authentification
  Entra seule qui le protège. L'adresse du Mac s'ouvre et se ferme par `az`, le temps d'une
  administration ; écartée : une règle dans le Bicep, qui laisserait une adresse IP dans l'historique
  des déploiements. `TERSE` : sans le `DETAIL` « Failing row contains », qui recopierait dans les
  journaux du serveur la ligne refusée, un auteur avec elle (règle 5 de `poc.md`). Pas de PgBouncer :
  B1ms n'a pas de PgBouncer intégré (faits Azure de time-knight du 05/11), le `SET` de session de #418
  tient donc ; `ALTER ROLE` reste écarté pour la raison de #418 (la valeur hors du dépôt). 32 Gio sans
  croissance : un disque plein arrête les écritures au lieu de faire monter la facture. API
  `2025-08-01` : `2026-10-01` donne l'avertissement BCP081 sous Bicep v0.48.1 (essayé le 06/11).
  Azure a accepté `log_error_verbosity` et `citext` en 18 (application du 06/11). Limites assumées :
  le serveur se paie à l'heure, qu'il serve ou non ; les sauvegardes du serveur
  ne sont pas celles de #390 (aucune restauration d'essai), et ne permettent pas de supprimer le
  brut. — PR de #421, à venir

### Jobs : `kb daily-routine` et `kb digest-watch` (#413)

Plan validé par Sabine le 06/11 (« Je suis les recommandations de time-knight »), relu par un sous-agent neuf.

- **Chaque job lance une commande `kb` qui enchaîne ses étapes dans le même processus, par l'appel des
  fonctions des commandes (`run_collect(data_dir, environ)`…), pas par `subprocess.run` (`commands/job_routine.py`).**
  Choix de la session, noté par time-knight le 06/11. Pourquoi : `kb` est le PID 1 du conteneur, le seul processus
  que SIGTERM atteint ; dans le même processus, `stopping_on_sigterm` couvre chaque étape (`daily-routine` et
  `digest-watch` dans `COMMANDS_STOPPED_BY_SIGTERM`), et le code d'une étape est celui que rendrait sa commande. Une
  exception imprévue d'une étape vaut 1 et la suite tourne, comme pour une commande seule (`cli.py`). Écarté : un
  sous-processus par étape, qui demandait un relais du signal vers l'enfant et l'attente de sa fin. — PR de #413
- **Le code de sortie d'une routine est le pire de ses étapes, dans l'ordre 0, 4, 2, 1 ; 130 et 143 arrêtent la
  routine sans lancer la suite.** Décision de Sabine du 06/11, sur la recommandation de time-knight. Pourquoi : leur
  valeur ne les ordonne pas, et un 2 peut être bénin (`kb digest` le rend quand la fiche du jour existe, donc sur une
  relance le même jour), alors qu'un 1 est une étape lancée qui a échoué. Écarté : 0, 4, 1, 2, proposé d'abord (un
  réglage refusé se répète chaque jour), qui laissait un 2 bénin cacher un vrai 1 (relecture du plan). Le réveil des
  API ne compte pas dans ce code ; ses lignes ERROR restent (revue de code, tranché par time-knight le 06/11,
  délégation de Sabine du 15/10) : une API injoignable fait échouer l'étape qui suit, qui le dit. — PR de #413
- **Conduite (issue #413) : `kb import` n'est pas lancé si `kb collect` rend 1 ou 2 ; toute autre étape est lancée
  quel que soit le code d'avant ; `kb trend-report` tourne après un échec de `kb digest` ; les deux API sont
  réveillées par `GET /health` avant `kb digest` et à nouveau avant `kb trend-report`.** Pourquoi le second réveil
  (choix de la session) : une demande de fiches dure jusqu'à 200 s, et les 300 s d'éveil d'une API sont le défaut
  d'ACA, non chronométré ; un `/health` d'une API éveillée coûte une fraction de seconde. `kb write-tops` tourne même
  quand `kb import` est sauté : les relevés des tops n'entrent pas en base, `kb write-tops` est leur seul lecteur
  (« Tops : les fiches par `kb write-tops` », 2026-10-19, `;` choisi par Sabine). — PR de #413
- **Le miroir des clips recode `ifSourceNewer` (décision 7 du plan de mise en ligne, Sabine, 06/11) : un clip est
  copié si son fichier manque ou est plus ancien que le blob, ou, à la même date, d'une autre taille ; une fois écrit par
  `write_file_atomically`, le fichier prend la date du blob (`os.utime`). Le téléchargement demande la version
  listée (`etag`, `IfNotModified`), jamais décompressée (`decompress=False`) ; rien n'est supprimé.** Pourquoi : le
  SDK n'a pas l'option d'azcopy ; dater le fichier par le blob fait comparer deux dates du stockage, quelle que soit
  l'horloge du conteneur, et poser la date change le ctime, que lit `clipping.py` : la collecte voit le clip changé.
  La taille, à la même date seulement : `last_modified` est à la seconde, et un fichier plus récent est gardé quelle
  que soit sa taille (deux revues de code, tranché par time-knight). La version épinglée et
  `decompress=False` : un blob `Content-Encoding: gzip` de moins de 1 Mo pourrait faire des Go une fois décompressé
  (relecture du plan). Après une copie, la routine attend `CLIP_CHANGE_MARGIN` plus 5 s, sans quoi le clip serait
  collecté le jour même ou le lendemain selon la durée des autres sources (choix de la session, marge de 5 s
  tranchée par time-knight). Un fichier écrit dont la date ne peut être posée reste copié, et compte en échec.
  Limites assumées : un second envoi de même taille dans la même seconde n'est pas vu ; Azure Files ignore la casse
  (`a.md` et `A.md` tombent sur un fichier, le plus récent l'emporte), un cas qui ne vient que d'un blob déposé
  autrement, le coffre du Mac en APFS, insensible à la casse par défaut, ne pouvant porter les deux noms ; l'écart des
  horloges du partage et du conteneur n'est pas mesuré. — PR de #413
- **Un nom de blob qui n'est pas un clip du premier niveau (avec `/`, un `.` initial, ou qui ne finit pas par `.md`)
  est laissé de côté, sans échec ; un clip que le partage ne peut pas porter (`\`, caractère `Cc`, `Co` ou `Cs`,
  `" : | < > * ?`, plus de 241 octets en UTF-8) ou plus gros que `CLIP_MAX_BYTES` est refusé, et l'étape rend 4. Le
  journal le cite par sa position dans la liste, jamais par son nom.** Choix de la session pour les deux sortes ;
  `..` refusé comme composant de chemin, ce que couvrent `/`, `\` et le `.` initial, décidé par Sabine le 06/11.
  Pourquoi : `clipping.py` saute de même ce qui n'est pas un clip, et un `.DS_Store` rendrait 4 chaque jour ; un
  clip refusé ne doit jamais l'être en silence, comme un clip trop gros (`ClipTooLargeError`) ; 241 : les 255 d'un
  nom moins les 14 caractères du temporaire de `write_file_atomically` ; le nom d'un clip est son titre (règle 3 de
  `conventions.md`). Écarté : `..` refusé partout, qui refusait chaque jour un titre « Les options... ». Limite : un
  clip refusé l'est à chaque exécution jusqu'à la suppression de son blob dans `clippings`. — PR de #413
- **La publication envoie chaque fiche de `veille/` absente du conteneur `watch`, à sa racine, par
  `upload_blob(overwrite=False)` (`If-None-Match: *`), après la liste des blobs ; les entrées cachées, les liens et
  les fichiers qui ne sont pas réguliers sont laissés de côté, un dossier illisible fait échouer l'étape.** Pourquoi :
  « sans écraser un blob qui existe » (issue) ; la liste évite de renvoyer chaque jour toutes les fiches ; une
  erreur du stockage arrête l'étape, sinon chaque envoi attendrait ses nouvelles tentatives (environ 7 min, #412).
  Écarté : envoyer sans liste et compter les 409, qui renverrait chaque jour chaque fiche du partage. Limite : la liste
  de `watch` grandit sans purge, comme `veille/`. — PR de #413
- **`--dry-run` imprime les étapes et leurs règles, après le démarrage ordinaire (`KB_DATA_DIR`), sans lire les
  réglages du job.** Pourquoi : le critère de #413 le lance dans l'image sans eux
  (`docker run --rm -e KB_DATA_DIR=/var/lib/knowledge_base <image> daily-routine --dry-run`). — PR de #413
- **En ligne, `kb import` garde sa purge du brut à 6 mois jusqu'à #390, qui la sortira dans l'étape « `pg_dump` puis
  purge » de `kb daily-routine`.** Décision de Sabine du 06/11 (option c, recommandée par la session et par
  time-knight). Pourquoi : elle tient la décision du 04/11 (« le brut est gardé 6 mois au plus » ; les deux
  sauvegardes saines valent « une fois la base sauvegardée ») et celle du 06/11 vers 11:30Z (en ligne, la purge après
  `pg_dump`), qui suppose une sauvegarde que #390 apporte. Écartées : (a) pas de purge du brut en ligne d'ici #390,
  qui fait tomber le maximum de 6 mois quelques jours après l'amorçage (il copie le brut du Mac) ; (b) coder
  `pg_dump` dans #413, le périmètre de #390 (client PostgreSQL dans l'image, jeton Entra, lieu des sauvegardes).
  Écart avec la carte des axes de time-knight (« enchaînée par `kb daily-routine` (#413) »). Limite déjà assumée le
  04/11 : sans sauvegarde de K-B, la base est la seule copie de ce qui a plus de 6 mois. — PR de #413

### Livraison continue : une version taguée sur `main`, par OIDC (#415)

Plan validé par Sabine le 06/11 (mode plan, relu en xhigh, avis de tn-orchestrateur). Les choix sont de la session,
sauf mention.

- **Une mise en ligne part d'un tag de version nouveau `vMAJEUR.MINEUR.CORRECTIF`, posé sur `main` et jamais
  déplacé. Une fusion ne déploie rien. Revenir en arrière, c'est redéployer le tag précédent.** Décision de Sabine
  du 06/11 (git-tag, « On Re-tagging »). Écartés : une branche `production` ; un tag mobile `deploy`, qui demande de
  retaguer, de pousser en force, et ne garde pas l'historique. Le motif et le premier tag, `v0.1.0`, sont validés
  par Sabine avec le plan : le 0 dit « avant la 1.0 », ce qui est juste pour un POC. Au-delà des 30 jours où GitHub
  relance une exécution, `workflow_dispatch` redéploie un tag (`gh workflow run deploy.yml --ref <tag>`), sous les
  mêmes règles. — PR de #415

- **Le verrou n'est pas le workflow, mais trois réglages de GitHub et l'identité Azure.**
  - Un ruleset réserve la création et la suppression des tags `v*` aux administrateurs.
  - Un second ruleset interdit à tous de déplacer un tag. C'est la décision de Sabine, validée avec le plan.
  - L'environnement `production` n'est atteint que par les tags `v*.*.*`.
  - `id-kb-deploy` n'accepte que les jetons de cet environnement : sujet `repo:SabineLaurent@189640103/K-B@1383589029:environment:production`.

  Pourquoi : un tag poussé lance le workflow **du commit tagué**, si bien que le job `check` (le format du tag, le
  commit sur la première lignée de `main`) ne protège que d'une erreur. Les réglages se posent avant la passe qui
  crée la connexion : un job qui déclare un environnement inexistant le crée, sans règle.

  K-B, créé le 23/09, après le 15/07/2026, a le sujet OIDC **immuable**, avec les identifiants numériques
  (`GET …/actions/oidc/customization/sub`). Le sujet en noms seuls, écrit au premier plan, n'aurait jamais
  correspondu : constat bloquant de la relecture.

  Limites assumées :
  - supprimer puis recréer un tag revient à le déplacer. Le déploiement échoue alors, car l'image existante porte le
    SHA de l'ancien commit (label `org.opencontainers.image.revision`), et une image n'est jamais reconstruite ;
  - une administratrice peut modifier un ruleset : « personne ne déplace un tag » est une règle de travail. Aucune
    session ne pose ni ne pousse de tag sans une demande explicite de Sabine (`MEMORY.md`). — PR de #415

- **Risque accepté par Sabine le 06/11, écart à l'issue : jusqu'au 08/11, un tag déploie sans sa validation.**
  Son plan GitHub est Pro. Dans un dépôt privé, il ouvre les environnements, leurs règles de tags et les rulesets,
  mais pas les « required reviewers », réservés aux dépôts publics. K-B le devient le 08/11 (#278). Sabine a choisi
  de déployer par tag dès ce soir, plutôt que d'attendre le 08/11 pour le premier tag (la recommandation de la
  session). Le contournent jusque-là : Sabine, administratrice, et toute session qui pousse avec ses droits. Le
  08/11 : Sabine en « required reviewer », avec `prevent_self_review: false`, puisqu'elle est la seule à valider,
  et `can_admins_bypass: false`, pour qu'une administratrice ne passe pas outre (revue de sécurité, tranché par
  time-knight le 06/11) (`infra/README.md`). Limite : une session qui a ses droits pourrait approuver elle-même un
  déploiement en attente par l'API (`pending_deployments`). La validation reste un geste humain, que seule la règle
  du `MEMORY.md` protège : aucune session n'approuve un déploiement. — PR de #415

- **`id-kb-deploy` a quatre rôles, chacun sur une ressource, jamais sur le groupe : AcrPush et Reader sur le
  registre, Container Apps Contributor sur chaque app, Container Apps Jobs Contributor sur chaque job. Rien sur le
  coffre, le stockage ni les données.**
  - Pourquoi Reader : `az acr login` lit le registre par ARM, ce qu'AcrPush ne permet pas. En mode « RBAC Registry
    Permissions », Reader permet aussi de tirer, ce qu'AcrPush permet déjà.
  - Pourquoi le rôle des jobs : Container Apps Contributor ne couvre pas `Microsoft.App/jobs`.
  - **Managed Identity Operator, prévu au premier plan, est retiré.** La relecture a lu le code d'azure-cli :
    `az containerapp update --image` envoie un `PATCH` qui ne porte que le `template`, sans l'identité, donc
    `assign/action` n'est pas vérifié. Moins de droits pour le même effet.
  - Repli écrit, si le premier déploiement rend `LinkedAuthorizationFailed` sur `managedEnvironments/join/action` :
    Container Apps Jobs Operator sur `cae-kb` seul.
  - Limite assumée : les jokers des deux rôles Container Apps couvrent `listSecrets/action`. L'identité lit donc
    les secrets des apps et des jobs en clair. C'est le constat 6, accepté par Sabine le 06/11 et écrit au registre
    (« Déploiement continu »). — PR de #415

- **Le workflow construit l'image du tag seulement si elle n'existe pas. Elle porte le SHA de son commit en
  label, et une image existante d'un autre commit arrête le déploiement. Les apps et les jobs reçoivent l'image
  par son digest (`k-b@sha256:…`), dont le label est revérifié.** Seule une réponse « not found » fait construire :
  toute autre erreur de lecture est un échec, pour qu'une panne du registre n'écrase jamais une image.
  - Pourquoi : un retour en arrière redéploie l'image d'origine, sans la reconstruire. Le digest est la référence
    immuable : une réplique qui se réveille tire exactement l'image déployée, même si quelqu'un qui a AcrPush
    réécrit le tag, l'identité de CD comprise.
  - Écartés : reconstruire à chaque exécution, qui écraserait le tag d'une version déjà en ligne ; verrouiller le tag
    dans ACR (`--write-enabled false`), car on ne sait pas si AcrPush suffit, et ce serait une étape à défaire.
  - Le digest vient de la revue de sécurité, tranché par time-knight le 06/11 (délégation de Sabine du 15/10).
  - Limite assumée : une passe Bicep faite à la main repose `k-b:<imageTag>`, la même image, mais par une référence
    mobile, jusqu'au déploiement suivant. L'outil des passes (#455) pourra lire le digest en ligne. — PR de #415

- **Une seule liste des apps et des jobs déployés, `infra/deployment.json`, lue par le Bicep
  (`loadJsonContent`, pour les rôles) et par le workflow (`jq`, pour les images).** Écartées : deux listes à tenir
  ensemble, et une liste lue dans Azure, qui demanderait de lire tout le groupe. Limite assumée : une ancienne
  exécution relancée reprend son ancienne liste.

  À dire à #421 : un retour en arrière relance l'ancienne migration sur une base plus récente, puis les apps N-1
  sur le schéma N. La migration doit donc accepter une base en avance, et le schéma rester compatible avec la
  version précédente. — PR de #415

- **La migration de la base passe avant les apps : `caj-kb-migrate-database` à l'image du tag, lancé et attendu
  jusqu'à `Succeeded`. Rien n'est mis à jour après un échec.** Pourquoi : les apps d'une version ne doivent pas
  tourner sur une base sans son schéma. `kb migrate-database` laisse telle quelle une base qui a ses tables (#421),
  donc un retour à un tag précédent la relance sans effet. La limite viendra avec la première vraie migration
  (#186) : le schéma devra rester compatible avec la version précédente. — PR de #415

- **Un test de fumée clôt chaque déploiement : `caj-kb-smoke-test` lancé et attendu jusqu'à `Succeeded`.**
  Validé par Sabine avec le plan, hors du texte de l'issue. Pourquoi : c'est la preuve que la version déployée
  répond. Une mise à jour réussie ne dit pas si les apps démarrent. Avant lui, le workflow attend que la dernière
  révision de chaque app soit prête, à l'image du tag (tranché par time-knight, revue de code de #460) : en mode une
  révision, l'ancienne répond jusque-là, et `/health` rend un texte fixe. — PR de #415

- **Un tag n'est déployé que si les exécutions des workflows du dépôt sur son commit, sauf celles de Deploy, sont
  finies et vertes.** Tranché par time-knight, revue de code de #460. Pourquoi : le ruleset de `main` n'exige
  qu'une partie de la CI, et un contrôle peut rougir après la fusion. Les exécutions que GitHub crée lui-même
  (Dependabot, sur la tête de `main`) ne comptent pas. Un tag posé trop tôt est refusé : on relance la CI du commit
  si elle est rouge, puis l'exécution du tag. Écarté : une règle écrite seulement. — PR de #415

- **Les identifiants Azure sont des secrets du dépôt, et chaque commande `az` du workflow passe en `-o none` ou par
  une `--query` étroite.** Pourquoi : les journaux deviennent publics le 08/11, et `az containerapp update`
  affiche par défaut toute la configuration de l'app. Écarté : des variables, qui s'afficheraient en clair. Une
  passe 2 faite à la main prend désormais pour `imageTag` la version en ligne : sinon, elle remettrait l'ancienne
  image. — PR de #415

## 2026-11-08

### Tendances : les textes des dépôts choisis, écrits depuis leur README (#369)

Plan de time-knight (08/11), relu par un sous-agent et trié par time-knight (délégation de Sabine du 15/10) ; cinq
points tranchés par Sabine le 08/11, « je suis tes recommandations ». Contrat : [tendances.md](../tendances.md),
« Rédaction » et « Ce que rend #369 ». Le pourquoi est celui de Sabine quand la décision lui est attribuée ; sinon,
celui du plan qu'elle a validé, ou du tri de time-knight quand il est nommé.

- **Le README est lu en brut, sa tête seule : 65 536 octets, le reste jamais téléchargé.**
  `GET /repos/{owner}/{repo}/readme`, `Accept: application/vnd.github.raw+json`. Pourquoi : GitHub sert un README
  jusqu'à 100 Mo, et la lecture bornée des fiches refuse un corps trop long : appliquée au README, une longue liste
  ferait échouer le compte rendu. 65 536 octets font au moins 16 384 caractères en UTF-8, plus que la coupe brute du
  nettoyage (4 × 4 000) : il voit toujours la coupe et retire le mot entamé. La tête et le corps borné partagent une
  boucle (`core/outbound.py`), pour que #436 s'y corrige une fois. Un 200 servi en `application/json` est refusé
  (`github_invalid_response`). Écartés : la forme JSON en base64 (le corps entier à lire, puis à décoder) ; un refus
  au-delà d'une borne ; l'en-tête `Range` (non documenté par GitHub). Limite : le type de média du brut n'est pas
  documenté (recherche du 08/11) ; #370 le relève. — PR de #369

- **404 et 410 donnent un README `absent` ; un 403 hors limite, un 451 ou une redirection, `refused` ; le dépôt
  reste choisi.** Le fichier dit `README : absent.` ou `README : non servi par GitHub.` (décision 1 de Sabine). Le
  403 compte parmi les 3 refus des fiches : la décision du 31/10 (« Q1 (b) ») s'étend au README. Écarté : écarter
  un choisi après le choix. — PR de #369

- **Tous les README sont lus avant la première rédaction, en série, dans l'ordre du modèle, sous le budget et le
  compteur de refus des fiches.** Pourquoi : rédiger dépôt par dépôt enverrait au modèle un README pour un compte
  rendu qu'une erreur GitHub sur le README suivant priverait de ses textes (minimisation). Une seule
  `GithubReading` par compte rendu ; le budget de 70 reste, son calcul écrit (60 fiches, 5 README, 5 relances ; tri
  de time-knight). Avant chaque README, une échéance qui ne laisse plus le temps d'un appel au modèle arrête la
  lecture, et les choisis non lus prennent `llm_timeout`. Écarté : README et rédaction dépôt par dépôt. — PR de #369

- **Une erreur GitHub pendant la lecture des README ne fait pas échouer le compte rendu.** Décision 3 de Sabine, sur
  la recommandation de time-knight. Le compte rendu est écrit avec le choix et les faits ; chaque choisi porte l'état
  en `writing_failure` et `Textes non écrits : <raison>.` ; aucun README ne part au modèle ; `kb` journalise l'état
  en avertissement, le span `read_readmes` est en erreur. Pourquoi : cohérent avec les décisions du 29/10 (un choix
  en échec donne un compte rendu factuel, une rédaction en échec ne retire que ses textes), et le choix déjà payé
  est gardé. **Revient sur le contrat de #364**, « pas de compte rendu partiel » pour toute erreur GitHub : la règle
  ne vaut plus que pour les fenêtres et les fiches. Écarté : arrêter le compte rendu, que proposait le plan, avec la
  ligne de métrique du choix écrite quand même (tombée avec la décision). Coût assumé : la période avance, comme
  pour un choix en échec. — PR de #369

- **Un seul champ d'échec, `writing_failure`, porte les états du modèle (`llm_*`) et de GitHub (`github_*`).**
  Choix de la session, que la mission lui laissait. Pourquoi : les deux familles sont disjointes par leur préfixe ;
  une seule ligne dans le fichier, un seul contrôle croisé dans `kb`. Écarté : deux champs, qui demanderaient un
  contrôle de plus pour interdire les deux à la fois. — PR de #369

- **La rédaction reçoit le `ref`, le nom du dépôt sans le login du propriétaire, son langage, sa licence, ses
  topics, ses critères, ses seuls sujets avec leur définition, sa description et son README nettoyés ; `null` quand
  GitHub ne donne pas de README.** Décision 5 de Sabine ; le nom sans le login, tranché par time-knight
  (minimisation). Pourquoi : ni étoiles, ni dates, ni prudences, que le code écrit lui-même et dont les nombres
  feraient retirer les textes par la règle des nombres ; `null` plutôt que le mot « absent », qu'un résumé recopié
  ferait passer à la fidélité. Écartés : « les faits du code », que disait le contrat ; tous les sujets de la
  veille. — PR de #369

- **Un nombre ne s'écrit que comme fait déclaré et trouvé : le code retire du texte les faits trouvés, du plus long
  au plus court et entre leurs limites, et un chiffre qui reste retire le texte.** Pourquoi : une règle fermée par
  construction, NFKC compris (`²`, `３`). Écartée : une liste de motifs de nombres, toujours incomplète. Limite : un
  nombre écrit en lettres n'est pas vu (décision 4). — PR de #369

- **Un texte vide sans fait est permis, il dit « rien à dire » ; un texte écrit sans source est retiré
  (`no_source`).** Décision 2 de Sabine. **Relâche la borne de l'architecte du 29/10** (des textes jamais vides),
  conformément à l'issue. Pourquoi : une borne qui oblige à écrire pousse le modèle à écrire ce que sa source ne
  dit pas. Un texte qui passe les contrôles sans
  lettre ni chiffre, une fois normalisé, compte pour vide (tri de la revue de code du 08/11, time-knight).
  — PR de #369

- **Des limites écrites au contrat plutôt que codées.** Décision 4 de Sabine : un bloc de code indenté de 4 espaces
  n'est pas retiré du README (il faudrait un analyseur Markdown) ; « version récente non retenue » et « prudence en
  faits, pas en verdicts » ne sont tenues que par la consigne ; un nombre en lettres et « Installez X » en prose ne
  sont pas vus. Ajoutées par le tri de la revue de code du 08/11 : `sudo` et `npx` refusés même en prose (refus
  fermé) ; un gestionnaire hors du motif de commande (`conda`, `poetry`…) non vu ; le README lu par le nom, sans
  contrôle de l'`id`. Pourquoi : chaque texte est neutralisé dans le coffre, rien ne s'y exécute, et #370 mesure ces
  cas. Le registre et le contrat, qui disaient « blocs de code retirés », sont corrigés. — PR de #369

- **Dans le coffre, sous la ligne des faits de chaque choisi, une ligne par texte, indentée de 2 espaces :
  `Secteur`, `Lien avec la veille`, `D'après son README` (`D'après le début de son README` s'il est coupé),
  `Promesse`.** Décision 1 de Sabine. Pourquoi : l'indentation garde les lignes dans l'élément du dépôt, comme celle
  des faits ; l'étiquette posée par le code tient l'« attribué à l'auteur » et le « tronqué » du 29/10 (16:53). Un
  texte retiré : « non retenu par les contrôles. » ; un texte vide : pas de ligne. — PR de #369

- **L'étape de métrique `write_trends` : une ligne par rédaction envoyée ; `FailedSubjectSchema.stage` des fiches
  reçoit son type, `DigestStage`.** Pourquoi : réutiliser `write` mêlerait les taux des fiches et des tendances.
  Rétablit ce que disait l'entrée du 01/11 (« `FailedSubjectSchema.stage` des fiches garde `classify` ou
  `write` ») : le code l'avait typé par `Stage`, et l'OpenAPI y listait `select`. — PR de #369

- **La réponse passe en 0.12.0 : chaque choisi gagne `readme`, `texts`, `texts_removed` (les noms, dans l'ordre) et
  `writing_failure`.** Pourquoi : le fichier dit quel texte est retiré. Écarté : un compte des textes retirés.
  `kb` relit chaque texte borné et sans caractère qui cache (Cf sauf U+200D, Co, Cn ; tri de la relecture du plan),
  et refuse une réponse qui se contredit. — PR de #369

### Tests : un seuil de couverture de 96 %, vérifié par la CI (#465)

- **`fail_under = 96` et `precision = 2` dans `[tool.coverage.report]` de `pyproject.toml` ; le job `tests`
  de `ci.yml` lance `uv run pytest --cov --cov-report=term-missing:skip-covered`, la suite de
  `make test-cov`, et échoue sous le seuil.** Décision de l'utilisatrice du 08/11, pour C12 d'E3 (demande
  de la certif n° 85, 07/11) : un plancher contre la régression, pas une cible. Mesure du 08/11 sur
  `2d240f7` : 98,41 % (lignes et branches), la même sur le Mac et sur le runner Linux de la CI (job
  `tests` de la PR, run 42469593428) ; celle du 06/11 : 99,26 %.
  - 96 %, au-dessus du niveau le plus haut que Google propose à ses projets, 90 % (« exemplary » [1],
    niveau 5 de la Table 2 [2]). Écartés : 90 %, sous lequel 8 points de régression passeraient sans
    signal ; un seuil collé à la mesure (98 %), qui ferait échouer une PR ajoutant un peu de code non
    couvert sans régression réelle. [1] déconseille de viser plus haut pour le chiffre (« We should not
    be obsessing on how to get from 90% code coverage to 95% ») et rappelle qu'un fort taux ne garantit
    pas la qualité des tests ;
  - `precision = 2` : `coverage` arrondit le total à `precision` décimales avant de le comparer au seuil
    (`round(total, precision) < fail_under`, `coverage/results.py`, 7.17.0) ; sans elle, 95,5 % passerait.
    Avec elle, l'arrondi ne tolère plus que 0,005 point, et dans cette bande le résumé de `pytest-cov`, qui
    compare le total brut (`pytest_cov/plugin.py`), affiche « FAIL » sur un job qui passe ;
  - le seuil vit dans `pyproject.toml` seul : `pytest-cov` le lit dans la configuration de `coverage`
    quand `--cov-fail-under` est absent (`pytest_cov/plugin.py`, 7.1.0), et `make test-cov` comme la CI
    s'en servent. Écarté : `--cov-fail-under=96` dans `ci.yml`, un second endroit à tenir ;
  - dans le job `tests`, pas dans un job à part. Écarté : un job `coverage`, qui relancerait la suite et
    ajouterait un sixième contrôle exigé au ruleset de `main`. Coût mesuré : 30 s → 41 s en local ; le
    job `tests` de la CI, 75 s → 112 s.

  Limites assumées : les tests `e2e` et `postgresql` restent hors de la mesure, comme le 06/11, et le
  code qu'eux seuls lancent compte comme non couvert. Le 08/11, les chemins de PostgreSQL laissent
  `database/postgresql.py` à 73,79 %, `database/creation.py` à 70,79 % et `database/errors.py` à
  82,46 % ; la mesure peut baisser de 2,4 points avant le premier échec.

  Sources, lues le 08/11/2026 : [1] C. Arguelles, M. Ivanković, A. Bender, « Code Coverage Best
  Practices », Google Testing Blog, 7 août 2020,
  https://testing.googleblog.com/2020/08/code-coverage-best-practices.html ; [2] M. Ivanković,
  G. Petrović, R. Just, G. Fraser, « Code Coverage at Google », ESEC/FSE ’19, p. 955-963,
  https://doi.org/10.1145/3338906.3340459. — PR de #465

### API : `https` vers une API interne, `http` vers la machine ou un service du compose (#473)

- **Une URL d'API interne de K-B (`KB_DATA_API_URL`, `KB_AI_API_URL`) n'est acceptée en `http` que
  vers `127.0.0.1` ou `localhost` (`LOCAL_HOSTS`), dans tout environnement, ou vers `api-donnees` ou
  `api-ia` (`COMPOSE_HOSTS`, `core/config.py`), les services d'un compose (#419), avec
  `KB_DEPLOYMENT_ENVIRONMENT=sandbox` ; tout autre hôte en `http` est refusé, `sandbox` ou non, et le
  démarrage avec (code 2), le message nommant la variable sans citer sa valeur ni celle qui
  débloque.** Décision de l'utilisatrice du 08/11 (option C') ; risque relevé par la relecture
  d'API8 et d'API10 (#454) : en ligne, le `https` ne tenait qu'au réglage du déploiement, et une URL
  `http` posée par erreur aurait envoyé une clé en clair. Une fonction,
  `find_internal_api_url_refusal` (`core/outbound.py`), appelée par les trois lecteurs de ces URL
  (`kb serve-ai`, `kb digest` et `kb trend-report`, `kb smoke-test` et `kb digest-watch`), selon la
  règle OWASP des deux API (05/11). Le contrôle du nom d'hôte de `find_url_refusal` passe avant.
  Révise le commentaire « No TLS before Azure Container Apps : http on the machine and in the
  compose network » (`DATA_API_SCHEMES`, `AI_API_SCHEMES`, retirés).
  - Le premier choix de l'utilisatrice, le matin du 08/11 (C), permettait `http` vers tout hôte en
    `sandbox`. La revue de code l'a relevé (un nom public en `sandbox` aurait reçu la clé en clair),
    et un sous-agent de sécurité neuf, en lecture seule, l'a jugé : « Le risque existe dans le code,
    mais il est faible ». Le scénario est sur le Mac, où `.env.example` conseille `sandbox` pour
    développer, et une restriction aux noms sans point serait contournée par une IPv4 numérique
    (`http://134744072`). D'où C' : une liste fermée de noms.
  - Écartées : `http` vers la machine seule (A), qui aurait forcé le compose de #419 au `https` ;
    `https` exigé en `production` seulement, ouvert par défaut, alors que les jobs n'ont pas la
    variable ; D, `http` vers `127.0.0.1`, `localhost`, `api-donnees` et `api-ia` dans tout
    environnement, sans `KB_DEPLOYMENT_ENVIRONMENT` : il s'écarte davantage de C et accepterait
    `http://api-ia` en production. Aucune app en ligne ne porte ce nom (`ca-kb-*`), mais la
    résolution d'un nom sans point dans Container Apps n'est pas vérifiée ; C' ferme le même risque
    en gardant la porte du compose derrière `sandbox` (choix de l'utilisatrice, sur la
    recommandation de time-knight).
  - `sandbox` est comparé tel quel (`Sandbox` ne compte pas), par `is_sandbox`
    (`core/api_settings.py`), que lit aussi `read_openapi_url`.

  Limites assumées : seuls `127.0.0.1` et `localhost` comptent pour la machine (ni le reste de
  `127.0.0.0/8`, ni `::1`, qu'un nom d'hôte de K-B refuse déjà) ; `localhost` est cru sur son nom,
  comme pour les hôtes par défaut de l'API de données (`DATA_API_ALLOWED_HOSTS = LOCAL_HOSTS`) ; un
  compose aux noms de service autres que `api-donnees` et `api-ia` devra les ajouter à
  `COMPOSE_HOSTS`. — PR de #473

### Outils de suivi : la comparaison de #163

La comparaison écrite qui fonde le choix de Grafana Cloud (décision 4 du 20/10) :
[outils-de-suivi.md](../outils-de-suivi.md). Elle compare Application Insights, Grafana Cloud,
Langfuse Cloud (UE), LangSmith (UE) et Honeycomb, selon les critères de « Wiki : métriques ».

- **Grafana Cloud reste le seul outil de suivi pour le rendu du 25/11 ; Application Insights est
  repris après le rendu.** Décision de Sabine du 2026-11-08 (« 10. ta recommandation »), sur la
  recommandation de time-knight, dont les raisons lui ont été dites. D'abord, deux outils avant le
  25/11, c'est deux mises en place, deux documentations (C11.8) et deux essais d'accessibilité
  (C11.4). Ensuite, Application Insights demande soit un collecteur OpenTelemetry avec une
  authentification Entra, soit une dépendance nouvelle (l'exportateur Azure Monitor), qui
  demanderait son accord ; les métriques au format Prometheus et leurs alertes dépendent de
  `Microsoft.Monitor` et `Microsoft.AlertsManagement`, non enregistrés sur l'abonnement de l'école
  le 08/11, que Sabine, Reader, ne peut pas enregistrer. Pourquoi le reprendre après le rendu : les
  traces et les journaux resteraient chez Microsoft, sous le DPA de l'école (le contenu d'un appel
  au modèle en anomalie ne partirait pas chez un sous-traitant américain), dans un outil Azure
  natif. Faits de la comparaison : Grafana Cloud reçoit les trois signaux OTLP de K-B (métriques,
  traces, journaux), il est en place depuis #162, #345 et #347, et coûte 0 $ dans les limites de
  l'offre gratuite. Option écartée : les deux outils dès maintenant, ce qui couvre Application
  Insights dès le 25/11, recommandé par la comparaison sans biais du sous-agent de time-knight du
  08/11 (aucun sous-traitant nouveau, le DPA de l'école, quelques centimes par mois, tout en Bicep,
  à condition d'enregistrer les deux fournisseurs, d'avoir l'accord du DPO de l'école et une règle
  d'alerte qui traite l'absence de données) ; elle est écartée pour les deux raisons de time-knight
  (deux mises en place avant le 25/11 ; collecteur ou dépendance nouvelle, et fournisseurs non
  enregistrés). Les pages de Langfuse Cloud et de LangSmith ne décrivent que des traces OTLP : les
  métriques et les journaux de K-B n'y auraient pas de destination. Les autres outils sont écartés
  dans le document, chacun avec sa raison. Limites assumées : l'accessibilité n'est essayée que sur
  Grafana Cloud, les autres outils sont jugés sur leurs déclarations publiées ; cet essai passe à
  #164 (choix 18 de Sabine, 2026-11-08) ; le texte des prompts, avantage propre de Langfuse et
  LangSmith, n'est pas montré par Grafana Cloud tant que `KB_TRACE_CONTENT` vaut `none` en ligne.
  Remonté à Sabine, non tranché : le DPA de Grafana Labs, signé le 28/10, ne vaut selon sa réponse
  du 29/10 que pour les entreprises (registre, « Envoi des mesures à Grafana Cloud »). **Précise**
  la décision 4 du 20/10 (« Squelette E1 E3 : cadrage du 20/10 ») ; sa phrase « au troisième temps,
  seuls l'URL et le jeton changent » ne vaut pas pour Application Insights (un collecteur et Entra,
  ou l'exportateur Azure Monitor ; des histogrammes exponentiels, la temporalité delta se
  convertissant dans le collecteur) : remonté à Sabine.
  — PR de #163

## 2026-11-09

### API de données : la lecture du détail bornée dans la base (#430)

- **La base lit d'un détail un surlignage et un caractère de texte de clip de plus que ce que la
  route sert, jamais la suite : `SELECT_HIGHLIGHTS` finit
  par `LIMIT ?` et `SELECT_CLIP` lit `substr(body, 1, ?)` (`database/reading.py`). La route passe
  `DetailBounds(MAX_SERVED_HIGHLIGHTS + 1, MAX_SERVED_TEXT_LENGTH + 1)`, soit 101 surlignages et
  125 001 caractères, à `read_item_detail`, qui le passe à chaque lecteur de `READ_DETAILS_BY_KIND`.**
  Tranche la décision ouverte du 06/11 (« Un `LIMIT` à la lecture des surlignages », #331) : la
  lecture n'était bornée qu'en temps, et un clip pouvait faire lire 1 000 000 de caractères pour en
  servir 125 000. Plan de time-knight validé par l'utilisatrice le 09/11.
  - La base lit « au plus n » ; c'est la route qui demande un de plus, pour voir la coupe sans lire
    le reste. Les drapeaux `highlights_truncated` et `body_truncated` de #331 sont inchangés, et
    `bound_details` aussi : le contrat de l'API ne bouge pas, pas de nouvelle version.
  - Les bornes ne sont écrites qu'une fois, dans `item_router.py`, comme l'issue le demande.
  - `substr` compte des caractères en SQLite et en PostgreSQL, la base PostgreSQL étant en UTF8
    (`creation.py`). En SQL_ASCII, il compterait des octets. Le test le vérifie sur un texte de
    « é », écrits en deux octets chacun.
  - Écartées : le +1 dans `database/`, parce que la base connaîtrait la logique de coupe de la
    route ; un cas à part pour l'entrée Zotero et le clip hors de la table des lecteurs, qui
    casserait la table ; une valeur par défaut des bornes dans `database/`, qui écrirait la borne
    une seconde fois.
  - Une borne négative ou au-delà de 64 bits est refusée (`check_within_bounds`), comme la limite
    de `read_items` : SQLite lit toutes les lignes sous un `LIMIT` négatif, et seul PostgreSQL
    refuse une longueur négative de `substr`. Ajouté au tri de la revue de code.
  - Limites :
    - `LIMIT` borne le nombre des surlignages, pas leur taille : la base lit au plus
      101 × (10 000 + 10 000) = 2 020 000 caractères de texte et de commentaire. La borne de
      taille (125 000) reste dans la route, comme l'issue le prévoit.
    - En SQLite, le moteur tourne dans le processus de l'API : la borne vaut pour ce que Python
      reçoit. Ce que SQLite charge pour calculer `substr` n'est pas mesuré. En PostgreSQL, c'est le
      serveur qui coupe le texte.
    - Les cinq autres lecteurs reçoivent les bornes sans s'en servir, pour garder une seule
      signature par sorte.
    - Le temps reste borné par instruction, comme avant (5 s, #418).
  - Preuve : `test_the_detail_reads_one_more_than_it_serves_and_says_the_cut`
    (`tests/data_api/test_item_router.py`), sur les deux moteurs.
  — PR de #430

## 2026-11-10

### Stockage en ligne : `job-data` et les conteneurs d'échange (#420)

Plan validé par Sabine le 10/11 (« Plan validé : A, B, C (a), D accepté »), relu par un sous-agent neuf et par
time-knight. Appliqué par Sabine le 10/11 ; les essais sont dans `infra/README.md`, « Vérifier les critères de #420 ».

- **Deux comptes : Files pour les jobs (`stkbjobfiles…`, partage `job-data`, que le Mac ne touche jamais), Blob pour
  les échanges avec le Mac (`stkbexchange…` : `clippings` et `zotero` montent, `watch` descend), sans conteneur
  `wiki`.** Décision 3 de Sabine du 06/11. Pourquoi : les jobs ont besoin d'un dossier qui dure, et le Mac n'échange
  avec Azure que par des dossiers à sens unique (issue #420). Pas de `wiki` : aucune identité ne pourrait y écrire ;
  un vrai ingest du wiki sur Azure reste #170. — PR de #420
- **Le sens des échanges est tenu par les rôles : un par identité et par conteneur, aucun sur le compte.
  `id-kb-daily-routine` lit `clippings` et `zotero` et écrit `watch` ; `id-kb-digest-watch` écrit `watch` ; Sabine
  écrit `clippings` et `zotero` et lit `watch` ; les API et `id-kb-migrate-database` n'ont rien.** Décision 4 de
  Sabine du 06/11, le verrou de sens. Pourquoi : la clé partagée coupée, une synchronisation à l'envers échoue en 403.
  Observé le 10/11 : depuis le Mac, `watch` refuse et `clippings` accepte ; sous `id-kb-daily-routine`, `clippings`
  refuse (403 `AuthorizationPermissionMismatch`) et `watch` accepte. Les deux tables du Bicep (`principalKeys`,
  `principals`) viennent de BCP120 : le nom d'un rôle doit être connu au début du déploiement, un `principalId` ne
  l'est qu'une fois l'identité créée. — PR de #420
- **Versions ; suppression réversible des blobs et des conteneurs, 30 jours ; les copies Zotero (`zotero/…`)
  effacées à 14 jours avec leurs versions ; rien n'efface `clippings` ; personne n'a Storage Blob Data Owner.**
  Décision 6 du 06/11 (les versions dès #420) et constats 3 à 5 de la relecture du plan. Pourquoi : la suppression
  réversible des conteneurs est la seule parade à un `clippings` supprimé par erreur ; `prefixMatch: ["zotero/"]`,
  sans quoi la règle toucherait `clippings` ; `version.delete`, sans quoi chaque copie effacée resterait en version
  précédente, sans fin ; `clippings` sans règle : « ce que je dépose moi dans kb n'est jamais supprimé
  automatiquement » (Sabine, 04/11). Limite assumée, écrite au registre : les versions des clips et des fiches sont
  gardées sans limite, contre la minimisation que demande le RGESN (critère 1.6) ; en effacer une demande un rôle
  Owner temporaire et la levée du verrou. — PR de #420
- **Un verrou `CanNotDelete` sur chaque compte.** Pourquoi : contre l'erreur de manipulation (issue #420). Écarté :
  `ReadOnly`, qui bloquerait les attributions de rôle. Limites : il n'arrête pas un Owner, qui peut le lever, et son
  geste reste au journal d'activité ; il bloque aussi la suppression d'un rôle sur le compte ou ses conteneurs, et
  celle d'un instantané : le lever, agir, le reposer (`infra/README.md`). — PR de #420
- **`job-data` est monté par l'identité système de `cae-kb` (Storage File Data SMB MI Admin sur `stkbjobfiles…`),
  pas par une identité attribuée par l'utilisateur.** Choix de la session, sur le constat 15 de la relecture du plan.
  Pourquoi : une identité attribuée pourrait être attachée à une autre ressource par un Contributor, qui aurait alors
  l'accès SMB admin à tout le compte ; l'identité système reste liée à `cae-kb`, et fait une ressource de moins. Son
  `principalId` se lit dans le même déploiement : l'environnement, puis le rôle, puis le stockage de l'environnement.
  Écarté : la convention `id-kb-<pièce>`, faite pour les identités qui doivent exister avant leur pièce. Limite
  assumée : le rôle appartient à l'environnement, et toute app ou tout job de `cae-kb` qui déclare le volume monte le
  partage. Seuls les jobs de #330 le déclareront : une convention, pas un contrôle, que `id-kb-deploy` peut contourner
  (registre, « Déploiement continu »). — PR de #420
- **La clé partagée est coupée aussi sur `stkbjobfiles…`, et le repli par la clé n'est pas codé.** Choix B du plan,
  validé par Sabine le 10/11 : rien d'écrit d'avance pour le repli, car un repli jamais essayé ne prouve rien ; une
  clé ouverte lui serait revenue, puis à une revue de sécurité. **Revient sur le repli demandé par Sabine le 06/11**
  (issue #420 : montage par la clé du seul `stkbjobfiles`, `listKeys()` dans Bicep, paramètre `filesAuth`), rendu
  inutile par l'essai du 10/11 : le partage se monte par l'identité, clé coupée. Observé aussi : les options
  `uid=10001,gid=10001,dir_mode=0700,file_mode=0600`, que la doc ne décrit pas pour ce montage, tiennent (partage en
  `10001` et `0700`, fichier écrit par `write_file_atomically` en `0600`). Limite : la doc de Microsoft déconseille
  de couper la clé d'un compte Files. — PR de #420
- **Instantanés de `job-data` : un avant l'amorçage (#330), un avant chaque mise en production, pris et supprimés à
  la main par Sabine, gardés 7 jours au plus, chacun avec sa date de suppression (`delete_after`).** Décision de
  Sabine du 10/11 (choix C (a), recommandé par la session). Pourquoi : un instantané sert à revenir sur une mise en
  production ratée, ce qui se voit en un ou deux jours ; la suppression réversible de Files ne vaut que pour le
  partage entier. **Écart accepté à la règle du 04/11** (« le brut est gardé 6 mois au plus ») : un brut vit au plus
  6 mois et 7 jours, écrit au registre, et un effacement à la demande touche aussi les instantanés. Écartées : aucun
  instantané, qui tient les 6 mois mais laisse un amorçage ou une mise en production ratés sans retour ; Azure Backup,
  un coffre, une stratégie, un coût, et le même écart. Limite : la borne de 7 jours tient par la date reprise dans la
  mission suivante, pas par du code. — PR de #420
- **Risque accepté par Sabine le 10/11 (choix D) : des tiers de l'organisme peuvent atteindre ces données.** Lu ce
  jour-là : 5 rôles Owner au groupe d'administration ; à l'abonnement, 1 Owner, 4 User Access Administrator et
  1 Contributor ; Sabine n'y est que Reader. Un Owner ou un User Access Administrator peut se donner un rôle de
  données et lever les verrous ; un Contributor peut rouvrir la clé partagée, ou créer un job qui monte `job-data`.
  Pourquoi l'accepter : rien dans les droits de Sabine ne l'empêche, son rôle de Reader ne permet aucune politique de
  refus. Prolonge le risque accepté le 06/11 (« destinataires possibles chez l'organisme »), cette fois avec des
  données (registre, « Droits d'accès »). — PR de #420
- **Les critères qui demandent l'identité d'un job à venir sont essayés par une sonde écrite dans le modèle de
  `caj-kb-smoke-test`, le temps d'un commit d'essai, retiré par un revert et une seconde passe.** Choix A du plan,
  validé par Sabine le 10/11. Pourquoi : une exécution ne change ni les identités ni les volumes, et sa surcharge
  remplace tout le modèle. Écarté : reporter ces essais à #330, qui changeait le critère et tranchait le repli trop
  tard. Limite tenue pendant l'essai : aucune exécution du workflow Deploy tant que la sonde était en ligne,
  `id-kb-deploy` pouvant lancer le job, donc agir sous `id-kb-daily-routine`. — PR de #420

### Coffre et brut : écrire un fichier une fois, même par deux lancements (#295)

Plan validé par Sabine le 10/11 (transmis par time-knight), relu par un sous-agent sans contexte (« sound with
changes », 8 constats intégrés) et par time-knight.

- **Un fichier écrit une fois (fiche du coffre, brut) est réservé par son temporaire caché au nom fixe,
  `.<nom>.tmp`, créé seulement s'il n'existe pas (`O_CREAT | O_EXCL`), puis cherché dans la liste de son dossier,
  juste avant le renommage : `write_file_atomically(…, replace=False)`.** Inverse le moyen prévu le 2026-10-21 et par #295 (« publier par
  `os.link` ») : « Plan an Azure Files deployment » (Microsoft Learn, mis à jour le 2026-10-26, lu le 2026-11-10)
  donne « Hard link support: Not supported » pour SMB, et le coffre des jobs est le partage SMB `job-data` (#420).
  La réservation tient sur SMB : le client Linux envoie `FILE_CREATE` pour `O_EXCL` (`fs/smb/client/dir.c`,
  `cifs_do_create`), que le serveur refuse si le fichier existe (MS-SMB2 2.2.13 et 3.3.5.9). La liste du dossier, et
  non le statut du fichier : le client Linux répond « absent » depuis son cache jusqu'à une seconde
  (`cifs_d_revalidate`, v6.19), constat du relecteur du plan. Options écartées : `os.link` (aucun lien physique sur
  SMB) ; `renameat2(RENAME_NOREPLACE)` ou `renamex_np` (absents de `os`, appelés par ctypes, comportement non vérifié
  sur SMB2) ; créer la cible elle-même en `O_EXCL` (après un SIGKILL, une fiche tronquée serait publiée dans `watch`,
  figée par `If-None-Match`, jamais réécrite) ; un verrou `fcntl` (dépend des options de montage) ou un verrou par
  lancement (même reste après un arrêt brutal, et il bloque davantage). Limites assumées : un SIGKILL, une session
  SMB perdue, ou un SIGTERM reçu dans les quelques microsecondes entre la création de la réservation et le bloc qui
  la retire (constat 1 de la revue de code), laisse `.<nom>.tmp`, qui refuse cette fiche jusqu'à son retrait à la
  main : la fiche d'un jour pour `kb digest` et `kb trend-report` ; pour `kb write-tops`, la fiche de ce top à chaque
  lancement, son relevé gardé et réessayé (constat 3) ; un programme autre que `kb` qui crée la cible entre la
  lecture de la liste, juste avant le renommage, et le renommage la voit remplacée ; que la liste d'un dossier soit
  à jour entre deux répliques vient du code du noyau et de « SMB Directory Leasing: Not supported », sans essai. La règle 2 de `conventions.md` (une seule fonction d'écriture) reste à amender par
  Sabine. — PR #539 (commit `25df4fb`)
- **Un temporaire trouvé fait échouer la commande (`temporary_file_found`, une `VaultEntryRefusedError`) dans
  `kb write-tops`, `kb digest` et `kb trend-report`, et `kb` ne le retire jamais.** Pourquoi, fait relevé par
  tn-codeur et transmis par time-knight le 10/11 : `kb write-tops` traite une fiche déjà là comme une information
  (`top_sheets.py:149`) ; un temporaire pris pour une fiche ferait réussir sans fiche le job planifié de #330. Jamais
  retiré : son nom peut être la réservation d'un lancement en cours (plan validé). L'alerte sur une exécution en
  échec et le retrait d'un temporaire vieux de plus d'une heure : deux issues que tn-codeur crée à sa PR (#330). —
  PR #539
- **La descente par descripteurs (`dir_fd`, `O_NOFOLLOW | O_DIRECTORY`) contre un dossier remplacé par un lien
  (CWE-59) sort de #295.** Décision de Sabine du 10/11, sur la recommandation du plan : le montage de `job-data`
  essayé pour #420 (`f10e5e3`) n'a pas `mfsymlinks`, sans lequel le client SMB de Linux ne crée pas de lien
  symbolique (« Troubleshoot Azure Files issues in Linux (SMB) », Microsoft Learn, lu le 2026-11-10) ; sur le Mac,
  seul un processus qui a déjà le compte de l'utilisatrice peut remplacer un dossier ; la limite était déjà acceptée
  le 2026-10-19 (`kb write-tops`) et le 2026-10-21 (`kb digest`). Option écartée : la coder dans #295. La limite et
  sa parade sont au registre (fiche 1, « Sécurité ») : un montage qui ajoute `mfsymlinks` rouvre la course. — PR
  #539
- **L'essai sur `job-data` de la réservation se fait pendant l'amorçage de #330, préparé par tn-codeur dans #330,
  sans sonde à part ni tag pour lui.** Décision de Sabine du 10/11, transmise par time-knight ; elle revient sur la
  forme décidée plus tôt le même jour (un essai à part, le tag de #330 attendant que #295 soit fusionnée et
  essayée). Option écartée : pas d'essai (proposée par le plan, une sonde ne reproduisant pas la course entre deux
  répliques). — PR #539

### Purge : sa propre commande, `kb purge` (#540)

Plan validé par Sabine le 10/11, relu par time-knight avant elle.

- **La purge sort de `kb import` : une commande à part, `kb purge`, que `kb daily-routine` lance juste après
  `kb import`.** Décision de Sabine du 2026-11-10 : « Je veux qu'elle soit appelée en dehors du script d'import à
  proprement parler » ; le principe : des briques qui marchent chacune seule, puis un chapeau par-dessus, la routine
  quotidienne (#540). **Révise** la décision du 2026-11-04 (« lancé par `kb import` après le commit et le bilan ») et
  celle du 2026-10-23 (la purge appelée par `kb import` après l'affichage du résumé) : le test qui figeait cet ordre,
  `test_a_failed_purge_leaves_the_summary_of_the_import_it_committed`, disparaît avec la purge de l'import. L'étape
  entre dans la routine dans le même changement : sans elle, plus rien ne purgerait en ligne. Elle prend la place que
  la décision du 2026-11-06 réservait à l'étape « `pg_dump` puis purge » de #390, qui ajoutera la sauvegarde avant
  elle. — PR de #540
- **Dans la routine, `kb purge` tourne même après un `kb import` en échec ou non lancé : pas de règle
  `NotRunAfter`.** Décision de Sabine du 2026-11-10, sur la recommandation du plan (« aussi après un import en échec
  ou non lancé »). **Lève l'invariant** « la purge ne
  tourne qu'après le commit » (2026-10-23). Pourquoi : l'import est une seule transaction ; en échec, il n'a rien
  validé, la base et le registre restent ceux du dernier import validé, et la purge y est cohérente ; un brut pas
  encore importé n'est jamais supprimé comme catalogue remplacé, la liste venant du registre (`purge/catalogs.py`,
  vérifié aussi par time-knight) ; avec la règle, un import qui échoue chaque jour ne purgerait plus rien, et les
  durées, qui sont des maxima, seraient dépassées. Option écartée : `NotRunAfter("kb import", {1, 2})`, qui garde
  l'invariant, mais purgerait quand l'import est sauté (`kb collect` en 1 ou 2) et pas quand il échoue. Limite
  assumée, déjà vraie avant : un brut de plus de 6 mois jamais importé part (procédure de tri, étape 3, compté à part
  au journal), même si les imports échouent depuis. — PR de #540
- **La purge est datée par l'heure de lancement de `kb purge` (UTC, à la seconde), et non plus par celle de
  l'import.** Décision de Sabine du 2026-11-10, sur la recommandation du plan. Pourquoi : `kb purge` marche seule,
  sans import le jour même, et les durées sont des maxima. Option écartée : l'heure du dernier import, lue en base ;
  une purge sans import nouveau ne supprimerait pas ce qui a expiré depuis. — PR de #540

### Le Mac : les fiches de `watch` par le SDK (#424)

Plan validé par Sabine le 10/11 (« Plan validé : le SDK au lieu d'AzCopy »), relu par un sous-agent sans contexte et
par time-knight. #424 ne fait plus que `make download-watch-sheets` ; `make upload-library` part dans #542 (décision
de Sabine du 10/11).

- **`make download-watch-sheets` passe par le SDK déjà installé (`azure-storage-blob`, et `AzureCliCredential` sur le
  compte d'`az login`), pas par AzCopy.** Choix proposé par la session, validé par Sabine. Pourquoi : chaque nom de
  blob se contrôle avant toute écriture, alors que deux identités de jobs écrivent dans `watch` (revue de sécurité de
  #420 : des noms non fiables, une traversée de chemin possible). AzCopy n'est pas installé sur le Mac, `az` l'est ;
  sans AzCopy, rien n'écrit de journal ni de plan citant les noms (essai 4 de #424 sans objet) ; le SDK ne fait que des
  appels au conteneur, comme les jobs. Revient, pour la descente, sur l'outil du plan de mise en ligne du 06/11 (I9 :
  AzCopy v10), recopié dans #424 ; pour la montée, le choix est à reprendre dans #542. Options écartées :
  `azcopy copy --recursive --overwrite=false`, où AzCopy bâtit lui-même le chemin local à partir du nom ;
  `azcopy list`, puis `--include-path`, qui demande deux outils et la lecture d'une sortie texte. Limite assumée :
  `az` reçoit tout l'environnement que charge `uv run --env-file`, secrets compris ; parade, un fichier
  d'environnement réduit pour cette cible, faisable avec nos droits, pas faite. — PR de #424
- **Une liste fermée de noms : `<dossier>/<jour>.md`, le dossier exactement l'un de ceux où écrivent les écrivains de
  `post/` (les 9 sujets, `tops/<top>`, `tendances`). Un nom de cette forme d'un autre dossier est laissé de côté, sans
  échec ; tout autre nom est refusé, cité par sa position, jamais écrit, et ne bloque pas les fiches valides.**
  « Ne bloque pas » : remarque de tn-orchestrateur, validée par Sabine. Sinon, un seul blob inattendu, que Sabine ne
  peut pas supprimer (elle n'a que Reader sur `watch`), arrêterait pour toujours tous ses téléchargements. Le code de
  sortie suit `find_exit_code`, la règle commune : 4 quand une fiche est dans `veille/`, 1 sinon (tranché par
  time-knight). Les dossiers des tops ont deux niveaux (`tops/most_starred`), que le plan omettait : écart trouvé au
  code, tranché par time-knight. Un test compare la liste aux trois `find_sheets_dir` de `post/`. — PR de #424
- **Une fiche déjà dans `veille/` n'est ni téléchargée ni remplacée, même modifiée sur le Mac ; l'écriture passe par
  `write_new_sheet` (`post/vault_files.py`), qui refuse un lien et ne remplace rien.** Pourquoi : le critère de #424
  (un second passage copie 0 fichier, une fiche modifiée en local n'est pas écrasée), et une seule règle des liens
  pour tous les écrivains du coffre. Options écartées : déplacer `vault_files` dans `core/`, pour que `jobs/` l'importe
  (les trois écrivains du coffre à toucher) ; recopier ses contrôles dans `jobs/`. Limite assumée (constat 12 de #424) :
  une fiche supprimée sur le Mac revient tant que `watch` la porte ; parade, la supprimer dans `job-data`, puis dans
  `watch`, puis sur le Mac, par un rôle temporaire (registre des traitements, « Procédure de tri », étape 9). — PR de
  #424
- **Un blob de plus de 4 000 000 octets est refusé, comme un texte qui n'est pas de l'UTF-8, qui porte un caractère
  de contrôle autre que la tabulation et le retour à la ligne, ou un contrôle bidirectionnel ; la liste s'arrête à
  20 000 blobs.** Pourquoi : borner ce qu'une identité de job peut faire écrire sur le Mac (OWASP API4:2023), et
  refuser ce que kb n'écrit jamais. 4 000 000 : le double d'une réponse de l'API IA non échappée
  (`MAX_AI_API_ANSWER_BYTES`), supposé, pas mesuré ; 20 000 : environ 4 ans de fiches à 12 dossiers. Limite assumée :
  au pire, 20 000 blobs de 4 000 000 octets sur le disque (parade, une borne d'octets par passage, pas faite). — PR de
  #424
- **Le Markdown actif est refusé, hors échappement compté par la parité des `\` : un accent grave, `~~~` n'importe où
  dans une ligne, `![`, un `<` qui n'ouvre pas un autolien `http://` ou `https://`.** Tranché par time-knight sur le
  constat de la revue de sécurité de #424, après la relecture d'un sous-agent neuf, sous la délégation de Sabine du
  15/10. Pourquoi : une requête Dataview (DQL), active par défaut et que les réglages du JavaScript ne coupent pas
  (`DEFAULT_SETTINGS` d'obsidian-dataview, lu par Context7 le 2026-11-10), lirait tout le coffre et pourrait
  l'envoyer par une image distante ; kb n'écrit aucun de ces quatre motifs sans l'échapper (il écrit un `[` dans les
  liens des tops et des `~` dans une URL ou une description). Options écartées : refuser seulement une clôture en
  début de ligne (`> ~~~` et `- ~~~` en ouvrent une aussi) ; garder le Markdown actif avec pour seule parade le
  JavaScript de Dataview désactivé (la parade du plan, qui ne couvre pas DQL). Un faux positif, une description de top
  qui contient `~~~`, refuse sa fiche : un échec visible. Limite assumée : un plugin qui agit sur un fichier neuf
  (Templater et « Trigger Templater on new file creation ») reste hors de ce contrôle ; parade, ce déclencheur
  inactif ou `veille/` dans ses « Excluded folders » (réglages de Templater, lus le 2026-11-10), faisable avec nos
  droits, à vérifier par Sabine sur son coffre avec le JavaScript de Dataview désactivé. — PR de #424
- **Refusés aussi : une référence de caractère non échappée (`&#x202E;`, `&rlm;`), même dans un autolien, et un `\`
  dans un autolien ; une URL de source qui contient `~~~` n'est plus écrite en autolien, mais « (sans URL) ».**
  Tranché par time-knight sur les deuxième et troisième `/code-review` de #424, sous la délégation de Sabine du 15/10 ;
  complète la puce précédente. Pourquoi : CommonMark décode une référence en contrôle bidirectionnel, même dans un
  autolien, ce qui contournait le refus des contrôles bidirectionnels ; un `\` n'échappe rien dans un autolien
  (CommonMark 0.31.2, § 6.5) et y laissait la référence décodée ; kb n'écrit ni l'un ni l'autre
  (`CHARACTER_REFERENCE`, `URL_CHARACTERS`). Une URL qui contenait `~~~` faisait refuser par la descente toute la
  fiche du sujet et du jour, et non sa seule source. `CHARACTER_REFERENCE` passe dans `core/config.py` : une seule
  définition pour les écrivains et la descente (`jobs/` n'importe pas `post/`). Options écartées : échapper `~` dans
  les descriptions des tops (le faux positif accepté à la puce précédente reste) ; une regex des références plus
  étroite, à la grammaire de CommonMark, que celle des écrivains (règle de Sabine du 2026-10-21, une règle pour les
  deux écrivains : la descente refuse exactement ce qu'ils échappent). Non vérifié : qu'Obsidian décode une référence
  dans un autolien comme cmark-gfm ; le refus vaut dans les deux cas. — PR de #424

### Routine quotidienne en ligne : `caj-kb-daily-routine` (#330)

Plan validé par Sabine le 10/11 (sortie du mode plan à 10:48Z), relu par un sous-agent neuf et par time-knight.

- **`kb write-tops` tourne en ligne dans `caj-kb-daily-routine`, sur le coffre de travail de `job-data`, et ses
  fiches descendent au Mac par `watch`.** Plan de mise en ligne du 06/11 (I7), validé par Sabine ; ferme la partie
  `kb write-tops` de la question ouverte « Où tourne … en ligne » (2026-10-19). Pourquoi, dit par Sabine le 10/11 :
  « Parce qu'ils font partie du process de collect. Il skip l'import parce qu'ils ne vont pas en bdd et suivent
  ensuite un parcours de digest sans passage par la case llm puisque tout est déterministe par du code python. » Et :
  « C'est un peu mon témoin de fonctionnement du pipeline + restitution sans llm. » Les tops sont un chemin de
  référence sans LLM : si les comptes rendus échouent alors que les fiches des tops sortent, la collecte et la
  publication fonctionnent, et la panne est sur le chemin des comptes rendus (l'import, les deux API ou le modèle). Les
  relevés des deux tops GitHub viennent de `kb collect`, n'entrent pas en base (`etl/raw_reading.py`, journal du
  2026-10-07), et leurs fiches sont écrites par du code, sans l'API IA (`post/top_sheets.py`) : leur place est la
  routine, pas `caj-kb-digest-watch`, qui appelle le modèle. Le montage de `job-data` (#420) lève l'obstacle de la
  question, qu'aucun conteneur ne montait le coffre. `kb digest` et `kb trend-report` restent ouverts jusqu'à #423
  (`caj-kb-digest-watch`). — PR de #330
- **Règle 3 de `.claude/rules/poc.md` amendée : en ligne, le brut reste un fichier sous `KB_DATA_DIR`, sur Azure
  Files ; Blob ne sert qu'aux échanges avec le Mac ; les clés POSIX relatives de `raw_store` restent ; le brut dans
  Blob passe en suite du projet (#317).** Décision 9 de Sabine du 06/11, appliquée dans la PR qui met le brut sur
  Azure Files. Pourquoi : la raison de la règle (« au 08/11, le brut passe dans Azure Blob Storage ») ne tient plus
  depuis que les jobs gardent leurs données dans un partage (décision 3 du 06/11) ; les clés restent pour que Blob
  reste possible sans toucher aux appelants. Le texte de la règle est modifié par Sabine (`.claude/`). — PR de #330
- **Rien du Mac ne passe en ligne : ni brut, ni état de la collecte, ni fiche. La routine part de zéro, sur un
  partage vide et une base qui n'a que ses sept sources.** Décision de Sabine du 10/11 : « les collect et production
  précédente de kb local sur ma machine ne sont pas à garder » (des essais de développement, `kb` n'étant pas encore
  utilisé pour de vrai). **Inverse en partie** « Base : la base du Mac est jetable » (2026-11-06) : la base en ligne ne
  repart plus du brut du Mac, et l'amorçage de l'issue (copier `raw/`, l'état et `veille/`, un instantané avant)
  tombe ; **et** l'instantané « avant l'amorçage » (2026-11-10, #420) : aucun, le partage étant vide, la règle d'un
  instantané avant chaque mise en production vaut dès le tag qui suit. Ce que la décision coûte : la base en ligne n'a
  que ce qu'une première collecte rapporte (arXiv depuis le 01/05, 7 jours de TLDR, tout CISA KEV, 8 jours de GH
  Archive). Limite : sur le Mac, la purge du brut ne tourne qu'avec un `kb purge` local ; sa parade est au registre
  (fiche 1, « Sécurité »). — PR de #330
- **Les deux dossiers vides du coffre, `vault/` et `vault/Clippings/`, sont créés une fois par l'opératrice, sous un
  rôle temporaire Storage File Data Privileged Contributor posé sur le seul partage, retiré ensuite.** Décision de
  Sabine du 10/11 (« on garde le plan »). Pourquoi : la routine refuse de démarrer sans `vault/`, et la collecte des
  clips échoue sans `vault/Clippings/`. Écarté : les faire créer par la routine, qui ne verrait plus un `KB_VAULT_DIR`
  mal écrit ou un coffre disparu ; `kb init` (#356) viendra plus tard. Limite : le temps du geste, l'opératrice lit et
  écrit tout le partage ; le rôle ne se retire que verrou levé (`infra/README.md`, « Les deux dossiers du coffre »).
  — PR de #330
- **La routine démarre à 08:00 UTC (`0 8 * * *`), soit 9 h à Paris en hiver.** Décision de Sabine du 10/11
  (« collecte quotidienne à 9h »). **Inverse** le cron `0 3 * * *` du plan de mise en ligne du 06/11, venu de
  l'architecte sans raison écrite. Ce qui suit : aucune exécution à la main ne démarre après 07:00 UTC jusqu'à la fin
  de celle du cron, 09:00 UTC au plus (le délai de 3 600 s borne aussi la reprise, Microsoft Learn, « Jobs in Azure
  Container Apps ») ; `caj-kb-digest-watch` démarre à 10:00 UTC (#423). Limite : rien ne tient deux exécutions à
  l'écart avant #426, la règle des heures est une consigne. — PR de #330
- **`id-kb-deploy` garde Container Apps Jobs Contributor sur la routine, donc peut agir sous son identité et obtenir
  ses deux secrets.** Risque accepté par Sabine le 10/11 (plan de #330, décision 3), sous réserve de la revue de
  sécurité. Pourquoi : le risque est propre à toute livraison continue (risque accepté le 06/11, constat 6 de #415),
  et les deux secrets sont au moindre privilège : un jeton *fine-grained* sans permission, la clé d'un compte de
  service qui n'a que BigQuery Job User dans un projet sans facturation, chacun révocable seul. Écarté : un rôle
  personnalisé sans `Microsoft.App/jobs/*/action`, puisque `Microsoft.App/jobs/write`, qu'exige le changement
  d'image, couvre tout le job. — PR de #330
- **#458 (les échecs de connexion à la base en ligne) n'est plus un préalable de #330 : elle passe après #423.**
  Décision de Sabine du 10/11. Ce qui la remplace pour la routine : la vérification des droits de
  `id-kb-daily-routine` (`t|t|t`) avant la première exécution, et un test de `kb import` puis de `kb purge` sous un
  membre de `kb_writer` (`tests/commands/test_purge_command.py`) ; la première exécution en ligne, le 10/11, sous ce
  rôle et avec l'image `v0.1.1`, dont la purge tourne dans `kb import`, a fini `Succeeded`. — PR de #330
- **L'essai de #295 sur `job-data` se fait dans l'amorçage de #330, sans sonde ni tag à part : un temporaire
  `.<jour>.md.tmp` posé par az (un second client, FileREST) dans le dossier d'une fiche de top, puis deux exécutions
  du job le même jour UTC. La première doit échouer sur `temporary_file_found` pour ce top ; la seconde, temporaire
  retiré, doit laisser intacte la fiche de l'autre top écrite par la première.** Décisions de Sabine du 10/11. Le tag
  n'attend plus que la fusion de #295. Écartées : une sonde sur `job-data`, avec un tag ou une passe à part ; une
  fausse fiche du jour posée par az, que la publication de la même exécution aurait envoyée dans `watch`, où la vraie
  fiche de ce jour ne serait jamais arrivée, et que personne ne peut effacer des versions. Limites, écrites au registre
  avec leur parade (« Écritures concurrentes en ligne ») : deux conteneurs qui écrivent en même temps, et la fraîcheur
  d'une écriture d'un client pour un autre. — PR de #330

## 2026-11-11

### API de données : la liste des items pour le fil (#550)

Plan de la session K-B validé par Sabine le 2026-11-11 ; les points de revue, tranchés par
time-knight sous la délégation de Sabine du 15/10.

- **`GET /items` sert, pour chaque item, les identifiants de sa sorte sous les noms du détail :
  `arxiv_id` (papier) ; `cve_id` et `exploited` (faille) ; `repository_name` et `tag_name`
  (release) ; `ghsa_id`, `cve_id`, `exploited` et `packages` (alerte) ; `edition` (article) ; rien
  de plus pour une entrée Zotero et un clip. La liste est une union discriminée par `kind`, et le
  détail de chaque sorte est l'item listé de sa sorte, plus ses champs propres.** Pourquoi : la
  carte du fil de l'interface web (décision de Sabine du 2026-11-09, maquettes validées) affiche
  ces identifiants sous le titre, et Sabine a choisi de compléter la liste plutôt que d'appauvrir
  les maquettes. Prolonge la liste blanche du détail (2026-10-15, « API de données : détail et
  tendances ») : ni auteur, ni texte long dans la liste. Option écartée : un schéma plat aux
  champs nuls, où un `null` dirait à la fois « pas de CVE » et « pas une alerte ». La spec passe
  en 0.12.0.
  - L'`arxiv_id` d'une entrée Zotero est lu par la liste, qui ne le sert pas (son schéma ne le
    nomme pas), et servi par le détail. Pourquoi : un champ de sorte ne doit jamais porter le nom
    d'un champ de la liste, sinon il le remplacerait sans bruit
    (`test_no_field_of_a_kind_takes_the_name_of_a_field_of_the_list`, #185). Option écartée à la
    revue : lire cet `arxiv_id` au seul détail, ce qui retirait de la liste un `LEFT JOIN` par la
    clé primaire de `publication`, au coût jugé négligeable.
- **`total`, le nombre des items qui répondent à `kind`, `since` et `q`, est compté par une
  requête `count(*)` sur les mêmes filtres, sans tri ni `LIMIT`, dans la même transaction de
  lecture que la page ; `limit` et `offset` gardent leurs bornes.** Pourquoi : le fil affiche
  « n items » ; la transaction commune empêche un import entre les deux lectures de les faire
  diverger. Option écartée : `count(*) OVER ()` dans la lecture de la page, car une page au-delà
  de la fin n'a aucune ligne, donc aucun total, et il faudrait un second chemin. Limite acceptée
  par Sabine le 2026-11-11 : en PostgreSQL, la liste fait deux instructions de 5 s chacune, plus
  2 s d'attente du pool, soit 12 s au pire, au-delà des 10 s du client de l'API IA ; en SQLite,
  la page et son total se partagent les 5 s de la requête (relevé à la revue de code). Pour réduire
  le risque : `count(*) OVER ()`, une lecture au lieu de deux, que PostgreSQL et SQLite calculent
  sur les lignes du `WHERE`, avant `LIMIT` (`docs/specs-api.md`, « Délai ») ; faisable, du code
  seulement. Gardé à la revue : un total recompté à chaque page, même pour l'API IA, qui ne le lit
  pas. Le compter à la seule première page changerait le contrat validé.
- **`exploited` garde le sens de l'ADR du 2026-10-07 (« exploitée » se lit
  `item_id IS NOT NULL`) : vrai pour toute faille du catalogue CISA KEV, retirée depuis ou non, le
  retrait se lisant dans `withdrawn_at` ; pour une alerte, faux veut dire « absente du catalogue »,
  et il est nul sans CVE. Il est servi dans la liste et, désormais, au détail d'une faille.**
  Décision de Sabine du 2026-11-11. La règle est écrite dans les branches de `LISTED_ITEMS`, une
  par sorte, et le détail la reprend de l'item listé (`SELECT_ADVISORY` disparaît).
- **La liste sert les 10 premiers paquets d'une alerte, dans l'ordre de la base, et
  `packages_truncated` dit qu'il en manque ; le détail les sert tous, avec
  `packages_truncated` faux.** Décision de Sabine du 2026-11-11 : c'est la parade de la limite
  (b) du plan. Servis entiers (l'import en permet 100 de 255 caractères), les paquets ajoutaient
  environ 2,58 Mo à une page de 100 alertes, et la page passait, avec les 2 Mo de son pire estimé,
  la borne de 4 000 000 octets que lit le client de l'API IA (`MAX_DATA_API_BODY_BYTES`). À 10,
  ils ajoutent environ 0,26 Mo. La borne vit dans `item_router.py` (`MAX_LISTED_PACKAGES`), comme
  celles du détail (#430) ; la description de `packages` dans l'OpenAPI l'écrit en chiffre, pour
  qu'un client la lise, et le test qui l'écrit aussi en dur (`TEN_PACKAGES`) échoue si la constante
  change, comme pour 100 surlignages et 125 000 caractères (tri de la revue). Options écartées à la
  revue : une description sans chiffre (« up to the bound of the list », lue comme la borne de
  `limit`) ; la constante déplacée dans le schéma pour l'écrire par f-string, contre le
  rangement des bornes de #430. Limite :
  la base lit tous les paquets avant la coupe, qui borne la réponse, pas la lecture.
  — PR de #550

### Stockage d'échange : son client dans un paquet `exchange`, que l'API de données peut importer (#558)

Choix du plan de la session K-B, accepté par time-knight le 2026-11-11 ; les points de revue,
tranchés par time-knight sous la délégation de Sabine du 15/10.

- **Le client du stockage d'échange (réglages, identité, transport, erreurs nommées) passe de
  `jobs/exchange_storage.py` dans un paquet neuf, `exchange/storage.py`, avec le téléchargement
  d'une version listée (`download_listed_version`, pris de `jobs/clip_mirror.py`). Seuls `jobs`,
  `commands` et `data_api` l'importent ; il n'importe que `core`, jamais `core.atomic_write` (tenu
  par `tests/architecture/test_layers.py` et `test_apis.py`).** Pourquoi : le site, entièrement
  privé, ne lit que l'API de données (décisions de Sabine du 2026-11-11), et il affiche les tops,
  les comptes rendus de veille et le rapport de tendances, publiés dans le conteneur `watch` (#559
  à #561) ; or l'API de données ne pouvait pas importer `jobs`. Le téléchargement rend des octets :
  leur écriture reste dans `jobs`, et l'API de données n'écrit aucun fichier. **Modifie la décision
  du 2026-11-06 (« Jobs : `kb smoke-test` et le paquet `jobs` », #412)** : `jobs` importe désormais
  `exchange` et `core`, et l'API de données a accès au stockage d'échange ; l'API IA, `etl` et
  `database` n'y ont toujours pas accès. Options écartées : `core/`, ouvert à toutes les couches,
  par lequel l'API IA, `etl` et `database` atteindraient le stockage ; ouvrir `jobs` à `data_api`,
  qui atteindrait alors l'écriture d'un fichier (`jobs/clip_mirror.py` importe `core.atomic_write`) ;
  une seconde copie du client, pour deux raisons (time-knight, le 2026-11-11) : une même
  connaissance à deux endroits (`code.md`, « Duplication ») ; et les gardes du client,
  `decompress=False` et le contrôle de l'etag (`If-Match`), devraient être tenues à l'identique dans
  les deux copies, si bien qu'une correction de sécurité faite dans l'une manquerait à l'autre.
  - Le comportement des jobs ne change pas : leurs tests passent sans changement d'assertion. Les
    faux du stockage suivent le paquet, dans `tests/exchange/storage_fakes.py` (tri de la revue). La
    copie du transport et de l'identifiant client dans `database/` (2026-11-06, #421) reste : la
    base n'importe pas `exchange`, et la mise en commun attend une troisième copie (même entrée).
  - Limites, préexistantes à l'identique dans `jobs/clip_mirror.py`, reportées à #559, qui fait de
    l'API de données un appelant : (a) `download_listed_version` rend `None` sur tout 404, un
    conteneur absent (`ContainerNotFound`) compris, comme pour un blob retiré ou changé ; (b) il lit
    tout le blob, sans borne en octets, et compte sur chaque appelant pour comparer d'abord la taille
    listée à sa borne. Pour réduire le risque : (a) garder le code d'erreur dans
    `ExchangeStorageError` et ne rendre `None` que sur `BlobNotFound` et `ConditionNotMet`
    (`StorageErrorCode` d'azure-storage-blob 12.31.1, lu le 2026-11-11) ; (b) passer à
    `download_blob` un `length` égal à la borne plus un octet (paramètre de
    `ContainerClient.download_blob`, même version, lu le 2026-11-11). Faisables, du code seulement.
  — PR de #558

### Site : le socle privé de `kb serve-web` (#562)

Plan de la session K-B FO validé par Sabine le 2026-11-11 ; écarts et points de revue tranchés par
time-knight sous la délégation de Sabine du 15/10, sauf ce qui est marqué Sabine.

- **Le site est un paquet neuf, `web`, en FastAPI et Jinja2, rendu par le serveur, sans aucun
  JavaScript dans le navigateur ; il n'importe que `core` et `items`, et seul `commands` l'importe
  (`tests/architecture/test_layers.py`).** Pourquoi : décision de Sabine du 2026-11-11 (mission FO),
  qui garde le site dans l'image, la CI et les protections de K-B ; le site lira l'API de données
  par HTTP (#563), jamais la base. Les gabarits échappent toute valeur (`autoescape=True`, quel que
  soit le nom du gabarit : le défaut de Starlette 1.8 n'échappe que `.html`, `.htm` et `.xml`) et
  refusent une valeur absente (`StrictUndefined`). Options écartées : `app.frontend()`, que propose
  le skill `fastapi`, dont le repli de page unique avalerait les 404 ; des liens par `url_for`, qui
  prendraient le schéma vu derrière l'entrée d'Azure (`http`). — PR de #562
- **L'accès est réservé à l'opératrice par l'authentification Microsoft Entra de la plateforme
  Azure Container Apps, doublée dans le code : un middleware compare l'en-tête
  `X-MS-CLIENT-PRINCIPAL-ID` (présent une fois, un GUID) à `KB_WEB_OPERATOR_ID` sur chaque requête
  sauf `/health`, et rend la page 403 sinon, sans la valeur au journal.** Pourquoi : la plateforme
  refuse cet en-tête venu d'un client (Microsoft Learn, « Authentication and authorization in Azure
  Container Apps », lu le 2026-11-11), et la connexion se règle sans administrateur de l'école
  (vérifié par tn-codeur le 2026-11-11). Le chemin comparé est celui que suit le routeur
  (`scope["path"]`) : `request.url.path` lisait `/health` dans `/health%3F` (relecture de sécurité,
  corrigé avant la PR). Options écartées : une dépendance FastAPI, qui ne couvre ni `StaticFiles` ni
  une route inconnue ; `uuid.UUID`, qui accepte accolades, `urn:uuid:` et tirets absents ; une
  exemption de `/static` pour la page 403 d'un autre compte, puisque `allowedPrincipals` lui rend le
  403 de la plateforme ; un mot de passe codé par K-B, gardé en repli si l'accès conditionnel de
  l'école bloquait l'essai. Limites assumées : le contrôle ne protège rien sans l'authentification
  de la plateforme, l'identifiant de Sabine n'étant pas un secret ; il ne voit pas une connexion
  WebSocket (`BaseHTTPMiddleware`), et le site n'en a aucune. Pour réduire le risque :
  l'authentification part dans le même déploiement que l'entrée externe, Entra seul fournisseur,
  et un `curl` avec l'en-tête forgé sans session doit répondre 302 ou 401 (infra, faisable). — PR
  de #562
- **`KB_WEB_AUTH=off`, sans contrôle d'en-tête, n'est accepté que sur une adresse de boucle locale et
  sans `CONTAINER_APP_NAME`, que la plateforme pose dans chaque conteneur ; en `entra`, une adresse
  hors de la boucle locale est refusée sans `CONTAINER_APP_NAME`.** Pourquoi : Sabine voit le site
  sur le Mac, et sur le Mac en `0.0.0.0` tout appareil du réseau pourrait poser l'en-tête. Options
  écartées : `KB_DEPLOYMENT_ENVIRONMENT`, posée à la main, où un oubli suffit ; aucun mode local.
  Limite : `CONTAINER_APP_NAME` ne prouve pas que l'authentification de la plateforme est active
  (première revue de code, écarté : c'est la limite de l'entrée précédente). — PR de #562
- **Aucune page n'est gardée : `no-store` sur chaque page, chaque erreur et `/health` ; `no-cache`,
  revalidé par ETag, sur `/static` ; aucun cache côté serveur.** Décision de Sabine du 2026-11-11.
  **Révise le choix 8 du plan validé le même jour** (`private, max-age=300`) : relevé par la revue de
  code, une page restait lisible 5 minutes après `/.auth/logout`. Options écartées : `private,
  max-age=300` ; `private, no-cache`, qui ne garantit pas la revalidation au bouton Retour (MDN, reco
  de time-knight) ; un cache en mémoire, perdu à chaque retour à zéro réplique et sans gain pour une
  seule lectrice. Limite : RGESN 6.2 n'est tenu que pour la CSS et l'icône ; un cache court des
  réponses de l'API de données (idée de Sabine du 09/11, le fil change une fois par jour) se tranche
  dans le plan du fil (#563). — PR de #562
- **Le site suit, en plus du RGAA 4.1.2 et du RGESN 2024, le référentiel Opquast – Qualité numérique,
  Règles 2025, version 5.0 ; chaque PR du site porte le relevé des règles applicables. La feuille de
  style n'emploie que des fonctions CSS Baseline « Widely available » ; une « Newly available » ne
  sert qu'en amélioration qui ne retire rien à un navigateur plus ancien.** Pourquoi : demande de
  Sabine du 2026-11-11, « bonnes pratiques du web et écoconception du web », puis une CSS à jour de
  fonctions stables ; son choix entre trois options. Options écartées : y ajouter les 115 bonnes
  pratiques d'écoconception du Collectif Green IT, plus longues à relever à chaque PR ; l'écoconception
  seule, sans Opquast. La lecture de Baseline (web-features du W3C WebDX, 3.45.0) est acceptée par
  time-knight. Limite : la CSS n'est pas minifiée (Opquast 229), faute d'outil de build sans
  dépendance nouvelle. — PR de #562

### Comptes rendus en ligne : `caj-kb-digest-watch` (#423)

Plan de tn-codeur validé par Sabine le 2026-11-11, relu par un sous-agent neuf ; ses décisions sont citées entrée par
entrée.

- **`caj-kb-digest-watch` lance `kb digest-watch` le lundi et le jeudi à 10:00 UTC, une fois la routine finie.** Les
  jours sont ceux de l'issue (plan de mise en ligne du 2026-11-06). L'heure suit la routine : celle-ci démarre à 08:00
  UTC et finit à 09:00 UTC au plus (« Routine quotidienne en ligne : `caj-kb-daily-routine` (#330) », 2026-11-10).
  **Inverse** le cron `0 5 * * 1,4` de l'issue, écrit quand la routine devait démarrer à 03:00. Limite : rien ne tient
  les deux jobs à l'écart l'un de l'autre, sauf une consigne sur les heures de départ à la main (`infra/README.md`,
  « La règle des heures ») ; le verrou de #426 ne couvrira que les commandes qui touchent la base, pas ce job.
  — PR de #423
- **L'expression cron est un paramètre de l'infra, `digestWatchCronExpression` dans `infra/main.bicep`, avec
  `0 10 * * 1,4` par défaut, passé au module sans défaut.** Décision de Sabine du 2026-11-11 : « l'expression cron en
  paramètre de l'infra, pas en dur ». Le défaut est un choix de la session : une passe qui ne donne pas le paramètre,
  CI comprise, garde le rythme décidé, et changer l'heure ne demande pas de toucher au code. Écarté : un paramètre sans
  défaut, que chaque passe devrait donner. Limite : le cron de la routine reste écrit dans son module
  (`infra/modules/daily-routine-job.bicep`). — PR de #423
- **Le job monte `job-data` à sa racine, sur `KB_DATA_DIR`, comme la routine.** Décision de Sabine du 2026-11-11.
  Pourquoi : `kb trend-report` tient le registre de ses comptes rendus dans `KB_DATA_DIR`
  (`post/trend_report_registry.py:26`), et repartirait de zéro à chaque passage sans partage ; `kb digest` et
  `kb trend-report` cherchent le compte rendu du jour dans le coffre avant toute demande. **Inverse en partie**
  « `job-data` est monté par l'identité système de `cae-kb` » (2026-11-10, #420) : « Seuls les jobs de #330 le
  déclareront » devient la routine et ce job. Écarté : un second partage, qui demande un second coffre, de nouveaux
  gestes, et ôte le rattrapage par la routine, qui republie chaque jour `veille/` du coffre commun. Limite : le job voit
  aussi le brut, l'état de la collecte et les journaux de la routine ; la parade par `subPath`, non appliquée, est au
  registre des traitements (« Données personnelles avec #423 »). — PR de #423
- **Aucune reprise (`replicaRetryLimit: 0`), un délai de 1 800 s.** Comme le veut l'issue (constat 14 du plan du
  2026-11-06). Pourquoi : après une expiration côté `kb`, une reprise appellerait le modèle une seconde fois, et
  `kb digest` comme `kb trend-report` ne refusent que si le compte rendu du jour existe, ce qu'une exécution coupée n'a
  pas forcément écrit. Limite : Microsoft Learn conseille « Set the replica retry limit to at least `1` » à cause de la
  maintenance de la plateforme (« Jobs in Azure Container Apps », lu le 2026-11-11). Parade : la routine republie
  `veille/` chaque jour, et une exécution coupée avant d'écrire une fiche se relance à la main le même jour, après
  celle du cron. Limite de la parade : coupée après une fiche, la relance ne rattrape rien, car `kb digest` refuse
  tous les sujets dès qu'une fiche du jour existe ; les sujets manquants attendent le passage suivant. — PR de #423
- **La fenêtre des comptes rendus reste à 3 jours en ligne, le défaut : aucun `KB_DIGEST_WINDOW_DAYS`.** Décision de
  Sabine du 2026-11-11 (« 5 jours c'est trop, je veux 3 »), sur une recommandation de 5 jours. Limite : deux pertes
  chaque semaine, la fenêtre suivant la date de la source (`docs/fiches-veille.md`, « Fenêtre ») : le calendrier, rien
  ne couvrant du jeudi 10:00 au vendredi 10:00 UTC ; le retard de collecte, un item daté avant le début d'une fenêtre
  mais collecté après le compte rendu précédent n'entrant dans aucun (les éditions TLDR et les entrées KEV du lundi et
  du jeudi, datées de minuit, collectées le lendemain). Parade : #565, « Démarrer chaque compte rendu de veille à la
  fin du précédent de son sujet », qui code la règle de Sabine du 2026-10-26 (`docs/tendances.md`, fin de « Hors
  v1 »), couvre le calendrier, pas le retard de collecte, qui attend la lecture par date d'arrivée dans K-B, prévue
  après l'oral blanc (décision de Sabine du 2026-11-11). Options écartées par la session avant la décision : 4 jours (le
  TLDR et les entrées KEV du jeudi, datés de minuit et collectés le vendredi, restaient hors de toute fenêtre) ; un
  passage par jour (`kb trend-report` est prévu deux fois par semaine, « Tendances : un compte rendu deux fois par
  semaine », 2026-10-29). — PR de #423
- **`kb digest` et `kb trend-report` tournent en ligne dans `caj-kb-digest-watch`.** Clôt la question « Où tourne
  `kb write-tops` en ligne » (2026-10-19), étendue à `kb digest` (2026-10-21) et à `kb trend-report` (2026-10-30),
  close pour `kb write-tops` le 2026-11-10 dans la routine. Pourquoi : le montage de `job-data` lève l'obstacle de la
  question, qu'aucun conteneur ne montait le coffre ; ces deux commandes appellent le modèle, leur place est le job
  des comptes rendus, pas la routine, qui reste le chemin sans modèle. — PR de #423

### Fiches de veille : chaque sujet repart de la fin de sa fiche précédente (#565)

Plan de la session K-B validé par Sabine le 2026-11-11 vers 16:00 UTC (D1, D2 ; commentaire de
#565) ; écarts du code tranchés par time-knight sous la délégation de Sabine du 15/10.

- **Un compte rendu de veille part du `until` de la fiche précédente de son sujet et finit à
  l'instant de la demande : plus de fenêtre fixe.** Pourquoi : règle de Sabine du 2026-10-26
  (`docs/tendances.md`, relayée par time-knight le 30/10), redite le 2026-11-11 : aucun item ne
  doit tomber entre deux comptes rendus. Ils partent le lundi et le jeudi ; une fenêtre fixe de
  3 jours perdait donc un jour chaque lundi. Hors de #565, après l'oral blanc du 13/11 : le rejeu
  des créneaux manqués, et le compte à la date d'arrivée dans K-B (la lecture filtre sur la date de
  la source). Limites et parades : `docs/fiches-veille.md`, « Limites de la fenêtre ». — PR de #565
- **`kb digest` lit le `until` de la dernière fiche de chaque sujet dans le coffre (D1, option A) ;
  un sujet sans item reçoit une fiche « Aucun item classé dans ce sujet. », pour que son début
  avance.** Pourquoi : le coffre reste la seule source de la fin d'un compte rendu, et les fiches
  déjà écrites à fenêtre fixe (le job en ligne du 11/11, et du 12/11 s'il tourne avant le
  déploiement) doivent servir de précédent, exigence de Sabine du 11/11 ; aucun registre ne les
  connaît. Écartée, l'option B : un registre `KB_DATA_DIR/digest_windows.json`, sur le modèle de
  `trend_reports.json` ; il ferait deux sources de la même fin, et les fiches seraient relues quand
  même à la reprise. **S'écarte, pour les seules fiches de veille, du choix des tendances** (2026-10-30,
  « Le code garde un registre des comptes rendus »), qui écartait de lire la période dans
  l'en-tête du dernier compte rendu pour que K-B ne relise pas le coffre. Ce qui a changé : des
  fiches existent sans registre, et doivent être reprises. Le registre des tendances reste. Limite :
  un `until` changé à la main décale le début du sujet ; après l'heure de `kb`, la demande est
  refusée (`previous_sheet_invalid`, code 2). — PR de #565
- **Le premier compte rendu d'un sujet sans fiche relit `KB_DIGEST_WINDOW_DAYS`, la variable
  existante (D2), et non une variable nouvelle** (l'issue proposait `KB_DIGEST_FIRST_WINDOW_DAYS`).
  Pourquoi : choix de Sabine du 2026-11-11, sur la recommandation de time-knight : une variable de
  moins, déjà bornée de 1 à 14 et documentée, dont le sens devient « la fenêtre d'un sujet sans
  début ». Limite : hors bornes, c'est `kb serve-ai` qui refuse de démarrer, pas `kb digest`. — PR de
  #565
- **L'API IA reste sans état : `POST /digests` reçoit le début de chaque sujet
  (`since_by_subject`, facultatif), lit une fois depuis le plus ancien, classe une fois, et ne garde
  pour chaque sujet que ses items datés de son début, avant la sélection des 60 items d'une
  fiche.** Pourquoi : règle 7 de `.claude/rules/poc.md` (rien qui survive à un redémarrage), le
  schéma de `after` pour `kb trend-report` ; une seule passe, parce que des débuts égaux donnent la
  même lecture et le même nombre d'appels au modèle qu'avant : le jeu de référence de
  `POST /digests` rejoue sans nouvel enregistrement. Écartée : deux passes de lecture, la plus
  récente d'abord, retirée du plan par time-knight (v3) ; elle reste la parade de la limite « Une
  seule passe de lecture ». Un début de plus de 14 jours (`MAX_DIGEST_WINDOW_DAYS`, la borne de
  `window_days`) est ramené à la borne, et `kb` le journalise. Après une lecture plafonnée, le
  compte rendu suivant part de `until`, pas de `covered_after` : sinon, les sortes rares déjà
  écrites reviendraient en double ; ce que le plafond laisse de côté est perdu pour les fiches.
  API IA 0.13.0. — PR de #565
- **`kb digest` refuse une réponse dont un sujet commence avant le début envoyé
  (`start_before_the_one_sent`), et les fiches perdent `window_days`.** Écarts du code au plan,
  tranchés par time-knight. Pourquoi : la fiche d'un tel sujet redonnerait des items de la
  précédente ; `window_days` n'était lu par aucun code, et une fenêtre n'a plus de durée fixe
  (`since` est désormais le début du sujet). — PR de #565
- **La fenêtre d'un sujet finit à `until`, exclu ; `kb digest` refuse un début plus tard que
  l'envoyé, sauf à la borne des 14 jours (`start_after_the_one_sent`), et une réponse où un sujet
  manque (`subject_missing`).** Tri de `/code-review` sur #565, par time-knight. Pourquoi : sans
  borne haute, un item daté de `until` ou après serait dans la fiche et dans la suivante ; un début
  plus tard qui n'est pas la borne laisserait des items hors de toute fiche, et le journal en
  aurait donné une cause non observée ; un sujet absent des trois listes n'aurait ni fiche ni ligne
  au bilan. Limite : un item daté après `until` n'est compté à part nulle part. — PR de #565
- **Une lecture entièrement vide n'écrit aucune fiche, et garde le début de chaque sujet : une
  ligne de journal, code de sortie 0.** Décision de Sabine du 2026-11-11, sur la recommandation de
  la session (constat 6 de `/code-review` sur #565, posé par time-knight). Pourquoi : une base vide
  ou un import pas lancé aurait donné neuf fiches « Aucun item classé dans ce sujet. », et avancé
  chaque début sur des items jamais lus, perdus ensuite pour les fiches. Précise D1 : un sujet sans
  item a sa fiche quand la lecture en a trouvé d'autres. — PR de #565

### Site : le fil de veille (#563)

Plan de la session K-B FO validé par Sabine le 2026-11-11 (décisions D1 à D5) ; écarts aux maquettes et
points de revue tranchés par time-knight sous la délégation de Sabine du 15/10.

- **Aucun cache côté serveur des réponses de l'API de données (D1) : RGESN 7.1 non tenu, par décision.**
  Décision de Sabine du 2026-11-11, sur la recommandation du plan : une seule lectrice, un appel
  d'environ 20 ms, un cache perdu à chaque retour à zéro réplique, et une taille M à deux jours de l'oral.
  Tranche la question que l'entrée du socle laissait au plan du fil (idée de Sabine du 09/11). Option
  écartée : un cache en mémoire de 5 min et 64 réponses valides au plus, sous verrou, qui aurait servi le
  bouton Retour malgré `no-store`, pour environ 40 lignes et une taille L. — PR de #563
- **Un écran du fil tient en 3 requêtes et 30 Ko transférés, cache vide, gzip compris (D2, RGESN 6.1),
  mesurés par un test sur 20 items.** Décision de Sabine du 2026-11-11. Option écartée : aucun budget,
  6.1 non tenu. — PR de #563
- **« Depuis » vaut « 1 jour » par défaut, en jours UTC : hier et aujourd'hui (D3) ; une date de début
  remplie ne compte que si « Date » est cochée (D4).** Décisions de Sabine du 2026-11-11. Pourquoi D3 : la
  maquette. Option écartée : 7 jours, parce qu'un papier porte la date de sa soumission, souvent un à trois
  jours avant sa collecte ; c'est la limite déjà acceptée de « quoi de neuf ». Pourquoi D4 : sinon, on ne
  reviendrait plus à « 3 jours » sans vider le champ. Option écartée : la date remplie l'emporte. — PR de
  #563
- **Le registre des traitements nomme le site dans #563, et non dans #564 (D5).** Décision de Sabine du
  2026-11-11 : le fil met en ligne `repository_name`, qui contient le login du propriétaire d'un dépôt
  suivi, et le registre ne nommait pas le site parmi les moyens de lecture. Option écartée : attendre
  #564 et les auteurs, le fil étant alors en ligne avant que le registre le dise. — PR de #563
- **Le site lit l'API de données par un client à lui (`web/data_api_client.py`) : 30 s de lecture, une
  échéance de 35 s vérifiée entre deux morceaux du corps, 1 Mo, sans redirection ni environnement ; une
  réponse lue par un modèle fermé aux cinq sortes, un champ ajouté ignoré.** Pourquoi : `web` n'importe
  que `core` et `items`, il ne peut pas reprendre le client de l'API IA ; les 30 s couvrent le réveil de
  l'API à zéro réplique, 20 à 26 s (#414). Options écartées : les 10 s du client de l'API IA, qui ne
  couvrent pas le réveil ; importer les bornes de `GET /items` depuis `core` dans l'API de données, au lieu
  de les recopier dans `core/config.py`, gardées égales par un test, parce que `src/k_b/data_api/` est à la
  piste A (revue de code, constat 5, gardé par time-knight) ; lire le 422 par le modèle du serveur, le
  client lisant par ses propres modèles stricts comme celui de l'API IA (constat 7, gardé). Limite
  assumée : une requête peut durer environ 70 s au pire (la connexion et le pool, 30 s jusqu'aux en-têtes,
  30 s jusqu'au premier morceau), rien n'étant borné avant le premier morceau (#436) ; pour réduire le
  risque : le réveil ci-dessous et ouvrir le site quelques minutes avant l'oral, faisables ; une borne
  totale demanderait une lecture asynchrone ou un fil à part, non faite. Ce GET borné est la troisième copie
  du dépôt : sa factorisation dans `core/outbound.py` est reportée après l'oral (constat 10). — PR de #563
- **Au démarrage, `kb serve-web` fait un seul `GET /health` de l'API de données, dans un fil à part ; le
  journal donne l'état, jamais l'URL.** Pourquoi : l'idée de Sabine du 09/11, réveiller l'API dès
  l'ouverture de l'accueil ; au démarrage du site, l'API se réveille pendant que Sabine se connecte par
  Microsoft Entra. Un échec n'arrête rien : le fil rendra la page 500. — PR de #563
- **La route du fil lit `request.query_params` brut, jamais des paramètres typés par FastAPI ; une page
  hors de `[1-9][0-9]{0,2}` ou au-delà de 501 rend la 404 avant tout appel.** Pourquoi : un `page=abc`
  partirait dans le 422 JSON de FastAPI, qui recopie la valeur reçue (relecture du plan). Option écartée :
  des paramètres typés. Limite : `page=1` sert aussi la page 1, qu'aucun lien n'écrit (revue de code,
  constat 9, gardé). — PR de #563
- **Deux écarts aux maquettes : le lien d'une faille dit « Voir la fiche sur nvd.nist.gov », et une
  newsletter porte le nom que TLDR donne à son édition (« TLDR AI », `NEWSLETTER_NAME_BY_EDITION`), son
  identifiant d'API inchangé.** Tranchés par time-knight le 2026-11-11 : un nom de domaine dit la
  destination du lien, ce n'est pas une abréviation à développer (Opquast 5) ; la maquette écrit « TLDR
  AI ». Les noms viennent du titre `h1` des pages de TLDR (fixtures de la collecte ; « TLDR InfoSec », lu
  sur tldr.tech/infosec le 2026-11-11). Options écartées : « Voir la fiche NVD », une abréviation ; le
  slug tel quel, « TLDR ai ». Limite assumée (revue de code, constat 3, tranché par time-knight) : la
  pastille « Exploitée (KEV) » reste sur une alerte dont la CVE a quitté le catalogue, la liste ne servant
  pas ce retrait ; le bandeau à trois états du détail (#564) le dira. — PR de #563
- **Une faille retirée du catalogue CISA KEV n'a pas la pastille « Exploitée (KEV) » : sa carte garde la
  ligne « retirée du catalogue le … ».** Décision de Sabine du 2026-11-11, sur la recommandation de la
  session, après le relecteur d'accessibilité (constat 9) : la pastille affirmait ce que la ligne suivante
  démentait. Option écartée : garder la pastille, au sens d'`exploited` dans l'API (au catalogue, retiré
  depuis ou non). — PR de #563
- **Deux aides de plus que les maquettes : la date de début « Obligatoire avec « Date », sans effet avec 1,
  3 ou 7 jours », et « Sans case cochée, le fil montre les cinq sortes ».** Tranché par time-knight le
  2026-11-11 (relecteur d'accessibilité, constat 1) : sans script, `required` ne peut pas dire une
  obligation qui dépend d'un bouton radio, et WCAG 3.3.2 (niveau A) demande que la règle soit écrite avant
  l'envoi. Limite assumée (constat 7, gardé) : le lien d'un article de newsletter ne dit pas sa langue, que
  K-B ne connaît pas ; « souvent en anglais » serait une supposition. — PR de #563

### Site en ligne : `ca-kb-web` derrière la connexion Entra de la plateforme (#571)

Décisions de Sabine du 2026-11-11 (mission de la piste B), puis plan de la session validé par Sabine le même
jour, avec ses quatre points ; relu par time-knight et par un sous-agent sans contexte. Le détail et les gestes :
`infra/README.md`, « Le site privé ».

- **Le site est une 3e app de `cae-kb`, `ca-kb-web`, depuis l'image de K-B, derrière la connexion Microsoft Entra
  de la plateforme (Easy Auth) : un seul tenant, `RedirectToLoginPage`, et `allowedPrincipals.identities` réduit à
  l'object ID de Sabine ; le secret client de l'inscription « K-B site » vit dans le coffre, référencé par l'app,
  jamais variable du conteneur, et expire le 2027-05-11.** Décisions de Sabine du 2026-11-11 : un site entièrement
  privé, où elle seule entre ; la connexion par la plateforme, doublée dans le code (#562) ; un secret client.
  Pourquoi la plateforme : elle seule retire les en-têtes `X-MS-CLIENT-PRINCIPAL-*` qu'envoie un client (Microsoft
  Learn, « Authentication and authorization in Azure Container Apps », lu le 2026-11-11), et K-B ne code ni OAuth 2
  ni session. Options écartées :
  - l'inscription par l'extension Microsoft Graph de Bicep : un outil de plus (`bicepconfig.json`, la CI) pour un
    objet créé une fois. Elle se crée à la main, par les commandes `az ad` de Learn ;
  - l'« affectation requise » : elle impose le consentement d'un administrateur (verdict de tn-codeur, lu par
    Sabine le 2026-11-11) ;
  - un secret remplacé par l'identité managée (MI as FIC) : décrit sur Learn pour App Service seulement ;
  - `authConfigs` en `2026-07-01` : elle n'ajoute que le magasin de jetons, et `2026-01-01` est celle de l'app.

  6 mois de validité pour le secret : au-delà du rendu du 25/11 et de la soutenance. Limites assumées :
  - le consentement et l'accès conditionnel du tenant de l'école ne se voient qu'à la première connexion : un refus
    mène au repli par mot de passe, au choix de Sabine ;
  - le 403 de `allowedPrincipals` pour un autre compte du tenant ne se constate qu'avec un second compte. Sans lui,
    le contrôle du code tient seul la vérification du compte. — PR de #571
- **Le site naît fermé et ne s'ouvre qu'une fois sa connexion lue : le module refuse une entrée externe sans
  connexion (`external && entraSignIn != null`), et la première création se fait en deux passes, la passe A en
  ingress interne, la connexion lue par `az containerapp auth show`, puis la passe B par `exposeWeb=true`.**
  Décision de Sabine du 2026-11-11, sur la recommandation de la session. Pourquoi : un sous-agent sans contexte
  l'a relevé, sans connexion rien ne retire un en-tête forgé. Le contrôle du code (#562) croirait alors un
  visiteur qui pose l'object ID de Sabine, que l'annuaire ne tient pas secret. ARM crée l'app avant son
  `authConfigs`, et un `authConfigs` qui échoue laisserait l'app ouverte. Un `exposeWeb` oublié ferme le site au lieu
  de l'ouvrir. Revues de la PR (tri de time-knight du 2026-11-11) : chaque passe tire `exposeWeb` de la connexion en
  ligne (`az containerapp auth show`), si bien qu'une recréation du site le crée fermé ; et sans ID d'inscription,
  le module ne pose ni connexion ni entrée externe (`hasSignIn` exige `clientId`). Option écartée : une seule passe, avec le site sans connexion le temps de sa création. **Précise
  l'entrée de #562 du même jour** : « l'authentification part dans le même déploiement que l'entrée externe »
  devient « avant l'entrée externe ». Règle d'arrêt : un `curl` qui rend 200 sans session, avec l'en-tête forgé ou
  non, ferme l'entrée (`az containerapp ingress disable`). — PR de #571
- **Microsoft Entra est le seul fournisseur d'identité de `ca-kb-web`.** Pourquoi : le code du site ne vérifie pas
  `X-MS-CLIENT-PRINCIPAL-IDP` (revue de sécurité de #562, relayée par time-knight le 2026-11-11). Un autre
  fournisseur pourrait donner le même en-tête d'identité. C'est une contrainte de l'infra : ajouter un fournisseur
  demande d'abord de revoir ce contrôle. — PR de #571
- **`id-kb-web`, identité propre du site, en `identityLifecycle: None` : la plateforme tire l'image et lit les deux
  secrets ; le code n'obtient aucun jeton.** Pourquoi : « le site n'a aucun droit Azure » (décision de Sabine du
  2026-11-11). Avec `Main`, le code pourrait obtenir un jeton d'`id-kb-web` et lire le secret client (time-knight,
  le 2026-11-11). Option écartée : partager `id-kb-data-api`, qui ouvre la base. — PR de #571
- **`api-container-app.bicep` porte aussi le site, par deux paramètres facultatifs (`external`, `entraSignIn`) dont
  les défauts gardent les deux API telles quelles ; pas de magasin de jetons, aucun chemin exclu de la connexion,
  `/health` compris ; 0,5 vCPU et 1 Gio, de 0 à 1 réplique.** Pourquoi :
  - un seul module par app, sans une 5e copie de la boucle des variables (#554) ;
  - le code ne reçoit que les en-têtes d'identité, et rien n'est servi sans connexion ;
  - le réveil des API, à la même taille, est mesuré : 20 à 26 s.

  Options écartées :
  - un module `web-container-app.bicep`, qui recopierait sondes, registre et identité ;
  - 0,25 vCPU, dont le réveil n'est pas mesuré ;
  - `excludedPaths: ['/health']`, gardé en repli sur l'accord de Sabine, si la révision n'est pas `Healthy` parce que
    les sondes passeraient par la connexion. Learn ne le dit pas. Une sonde envoie `Accept: */*` (kubernetes.io) :
    elle y recevrait le 401 constaté le 2026-11-11 pour un client sans `Accept: text/html` (une déduction).

  Coût estimé au cours de l'API des prix du 2026-11-11 : ≈ 25,7 à 27,2 € par mois pour tout K-B, sous les 30 € du
  budget (accepté par Sabine). Limite assumée : une requête sans connexion réveille la réplique (déduction, non
  vérifiée). Un robot qui la tiendrait éveillée coûterait ≈ 39 $ de plus. Pour réduire le risque : les alertes du
  budget, en place ; `ipSecurityRestrictions` reste possible, mais n'est pas retenu, car l'adresse de Sabine change.
  — PR de #571
- **`id-kb-deploy` reçoit Container Apps Contributor sur `ca-kb-web`, qui entre dans `deployment.json`.** Pourquoi :
  le Deploy met chaque app à l'image du tag. Limite assumée (plan validé par Sabine le 2026-11-11) : il peut lire le
  secret client et la clé `WEB` (`listSecrets`), et retirer la connexion, ce qui rendrait le site public ; le rôle
  porte `containerApps/*/write` et `*/action`, sans exclusion (Learn, « Azure built-in roles for Containers », mise
  à jour le 2026-07-01). Il n'y gagne aucune donnée : il tient déjà `ca-kb-data-api`. Pour réduire
  le risque : les rulesets des tags et l'environnement `production` ; une alerte gratuite du journal d'activité sur
  `Microsoft.App/containerApps/authConfigs/write`, faisable, non posée (registre, « Déploiement continu »). — PR de
  #571

### API de données : la lecture de `watch` pour le site (#571)

- **`id-kb-data-api` reçoit Storage Blob Data Reader sur le conteneur `watch` seul, et `ca-kb-data-api` reçoit
  `KB_EXCHANGE_BLOB_URL`.** Décision de Sabine du 2026-11-11 (option A de l'architecte) : l'API de données est la
  seule porte du site, qu'elle sert en JSON, et le site n'a aucun droit Azure. **Modifie la décision 4 du
  2026-11-06**, tenue par #420 (« les API et `id-kb-migrate-database` n'ont rien ») : l'API de données lit
  désormais `watch` ; l'API IA et `id-kb-migrate-database` n'ont toujours rien. Le sens tient : un rôle de lecture,
  sur un conteneur, aucun sur le compte. Le verrou `CanNotDelete` n'empêche pas d'ajouter un rôle. Option écartée :
  le site qui lit `watch` lui-même, avec un rôle Azure pour son code. Limite assumée (consigne de time-knight du
  2026-11-11, écart au moindre privilège accepté) : le rôle, `KB_EXCHANGE_BLOB_URL` et la clé `WEB` sont posés avant
  leur code (#559 à #561, #563), pour éviter une seconde passe avant le fil. Pour réduire le risque : ils restent
  sans code quelques jours, et #559 et #563 les utilisent ; le rôle ne permet que la lecture de `watch`. Depuis #563,
  fusionnée le même jour, le site lit la clé `WEB` : seuls le rôle et `KB_EXCHANGE_BLOB_URL` précèdent encore leur code
  (#559 à #561). Suit l'entrée de #558 du même jour, qui ouvre
  le client du stockage d'échange à l'API de données. — PR de #571

### Site : le fil aligné sur ses maquettes, les liens externes dans un nouvel onglet (#587)

Remarques de Sabine du 2026-11-11 sur le fil vu en local à côté des maquettes, relayées par time-knight ; plan court
validé par Sabine le même jour ; points de revue tranchés par time-knight sous la délégation de Sabine du 15/10.

- **Chaque lien vers un autre site s'ouvre dans un nouvel onglet (`target="_blank"`, `rel="noopener noreferrer"`),
  que son texte annonce, en plus petit : « (en anglais, site externe, nouvel onglet) » ; sur le fil comme sur
  `/sources`, la même forme, écrite par une seule macro Jinja, `external_link`, et un lien du site s'ouvre
  toujours dans le même onglet.** Pourquoi : la demande de
  Sabine, « rester dans K-B » quand elle ouvre une source ; Opquast 2025, règle 146 (« L'utilisateur est averti des
  ouvertures de nouvelles fenêtres »), et règle 138 (même comportement pour les liens de même nature). Le RGAA 4.1.2
  ne demande pas l'avertissement : son critère 13.2 interdit seulement une fenêtre ouverte sans action (lu le
  2026-11-11) ; la technique WCAG G201, conseillée et non exigée, le place dans le texte du lien. `noopener` et
  `noreferrer` : la page ouverte n'atteint ni la page de K-B ni son adresse. Options écartées : le même onglet, le
  défaut, que G200 conseille hors besoin ; l'annonce à la taille du lien, plus longue que le lien de la maquette ;
  l'annonce cachée derrière la seule flèche, que G201 permet mais qu'une personne voyante ne lit pas. Limite
  assumée : un onglet ouvert d'office peut dérouter (G200) ; pour réduire le risque, l'annonce dans chaque lien,
  faite. L'annonce est en 0,75rem (12 px par défaut), au contraste de 7,4:1 (gardée par time-knight, relecture
  d'accessibilité, constat 4). — PR de #587
- **« Se déconnecter » passe du pied de page à la fin de l'en-tête, une fois par page ; la page 403 ne garde que son
  bouton.** Pourquoi : la demande de Sabine, qui l'y cherche ; un écart aux maquettes, qui ne le placent pas. Il reste
  dans le `nav` de l'en-tête, là où la maquette met son lien de droite, « Back office » (revue de code, constat 3,
  gardé par time-knight). Options écartées : le garder aussi au pied de page, la même action deux fois ; le sortir
  du `nav` (proposition de la revue de code), alors que la maquette y met son lien de droite et que « Se
  déconnecter » mène à une page de la plateforme. — PR de #587
- **Le fil suit ses maquettes à chaque largeur : sur un téléphone, les sortes et les boutons radio en deux colonnes ;
  sur une tablette, les sortes en trois et la date de début à droite des boutons radio ; sur un ordinateur, les
  sortes, puis les boutons radio et le champ de date, chacun sur une ligne ; les espacements de la maquette ; la
  ligne d'une carte réunit sa sorte encadrée, sa date, ses identifiants et sa pastille ; les liens de page sont des
  boutons qui mènent à la ligne des résultats (`#resultats`).** Pourquoi : les remarques de Sabine sur ses captures du
  mobile, de la tablette et du desktop ; l'ancre, sa demande de ne pas remonter tout en haut en changeant de page
  (le formulaire envoyé, une nouvelle recherche, s'ouvre en haut). La ligne des résultats porte `tabindex="-1"` :
  en suivant l'ancre, le navigateur lui donne le focus (WHATWG, « Scrolling to a fragment », les étapes de focus sur
  la cible, le *viewport* sinon), et le clavier comme un lecteur d'écran repartent des résultats ; tranché par
  time-knight sur la deuxième revue de code, qui corrige la lecture de la spécification par la session. Option
  écartée : un `<p>` sans `tabindex`, où le focus irait au *viewport*. Mesuré dans Chrome le 2026-11-11, le formulaire
  passe de 585 à 405 px de haut à 1280 px (334 sur la maquette), de 606 à 539 à 820 et de 728 à 692 à 390. Option
  écartée : retirer les trois aides, que la maquette n'a pas ; elles tiennent la règle d'un champ avant l'envoi (WCAG
  3.3.2, ADR de #563) et restent, en 0,875rem, collées à leur libellé. Limite assumée : sur un téléphone, le
  formulaire reste plus haut que la maquette (692 px contre 398 à 390 px), par ces aides. — PR de #587
- **Le contenu garde sa largeur de 70rem (1072 px de texte), comme la maquette desktop.** Tranché par time-knight le
  2026-11-11 sur la mesure de la session : la maquette plafonne elle aussi son contenu (`max-width` de 1120 px moins
  24 px de marge de chaque côté), et la colonne étroite que Sabine voyait venait de son écran d'environ 2 600 px de
  large. Option écartée : élargir au-delà de 1280 px, qui allongerait les lignes de l'intro et des titres au-delà
  d'une longueur lisible. — PR de #587

## 2026-11-12

### Site : le détail d'un item (#564)

Plan validé par Sabine le 2026-11-11 (D1 à D4), puis le 2026-11-12 avec deux ajouts de time-knight ; choix de
la session C1 à C17 et points de revue tranchés par time-knight, sous la délégation de Sabine du 15/10.

- **#564 est coupée en deux PR : le détail des cinq sortes et le lien du titre d'une carte (#564, M), puis les
  tendances et la navigation (#596, S).** Décision de Sabine (D1). Pourquoi : le détail est prêt plus tôt, chaque
  revue est plus courte, et si le temps manque avant l'oral blanc, c'est la seconde qui attend. Option écartée :
  une PR L, un seul tour de revues, mais rien de prêt avant la fin. — PR de #564
- **Les notes d'une *release* s'affichent en texte brut, échappé : un paragraphe par bloc séparé d'une ligne
  vide, les retours à la ligne et le retrait des lignes gardés, aucun lien rendu ; la section s'intitule « Notes
  de version, texte brut ».** Décision de Sabine (D3). Option écartée : rendre le Markdown, qui demande une
  dépendance que la mission n'accorde pas, et dont le réglage par défaut laissait passer le HTML brut
  (`.claude/rules/code.md`, « Pratiques à jour »). Limite assumée : les titres et les listes Markdown n'ont pas de
  structure (RGAA 9.1 et 9.3), ce que dit la déclaration d'accessibilité. — PR de #564
- **Un écran de détail tient le budget du fil, 3 requêtes et 30 Ko transférés, cache vide, gzip compris, son
  résumé ou sa description à sa borne de 5 000 caractères ; les notes d'une *release* (125 000 caractères au
  plus) et les auteurs d'un papier (1 000 au plus) sont hors budget.** Décision de Sabine (D4, RGESN 6.1).
  Pourquoi hors budget : l'API les sert entiers. Option écartée : aucun budget sur le détail. — PR de #564
- **L'identifiant d'un item est lu dans l'adresse comme une chaîne, par une seule fonction, `read_item_id` :
  `[1-9][0-9]{0,18}` en chiffres ASCII, au plus 2⁶³ − 1 ; hors de cette forme, la page 404 sans appel à l'API.**
  Pourquoi : FastAPI, sur un paramètre typé `int`, rendrait un 422 en JSON qui cite la valeur reçue ; une seule
  adresse par item (Opquast 169) ; et #403, qui passera l'identifiant en UUID, ne changera que cette fonction
  (ajout de time-knight, validé par Sabine). Limite assumée : Starlette route sur le chemin décodé (spécification
  ASGI), si bien que `/items/%39` sert aussi l'item 9. — PR de #564
- **Le client du site ne prend pour « item absent » que le 404 dont le corps dit `item_not_found` ; tout autre 404
  de l'API (`route_not_found`, un 404 sans JSON de l'entrée d'Azure) rend la page 500.** Pourquoi : un état par
  route ; un 404 d'une route inconnue n'est pas un item absent, et le confondre cacherait une panne. — PR de #564
- **Une entrée Zotero ou un clip est lu par sa sorte seule (`ExcludedItem`), et la route rend la page 404 ; son
  texte n'est jamais modélisé, montré ni journalisé.** Pourquoi : le site ne les montre pas (mission du 11/11).
  Limite assumée, relevée par la revue de code et tranchée par time-knight le 2026-11-12 : la clé `WEB` lit tous
  les items, si bien que leur texte arrive au conteneur du site avant d'être jeté. C'est un défaut déjà présent
  sur `main` (API1, « tout client authentifié lit tous les items ») : il revient à une issue, pas à cette PR. Pour
  réduire le risque : réserver au client `WEB` les sortes que le site montre, côté API de données (#597). Écrit au
  registre des traitements. — PR de #564
- **Tout texte reçu de l'API et rendu passe par une seule fonction, `clean_received_text`, au fil comme au
  détail : elle retire les contrôles (`Cc`) sauf la tabulation et le retour à la ligne, les demi-paires isolées
  (`Cs`), les non-caractères, et les douze contrôles bidirectionnels de `BIDI_CONTROLS` (`core/config.py`), et
  ramène `\r\n` et `\r` à `\n`.** Pourquoi : ces caractères sont des erreurs d'analyse HTML (RGAA 8.2), que
  l'échappement de Jinja2 ne retire pas ; `NonEmptyText` ne refuse que le NUL et la demi-paire isolée ; jamais
  fermé, un contrôle bidirectionnel (U+202E) renverserait l'affichage de la date qui suit dans la même ligne
  (seconde revue de code, constat de sécurité relu par un sous-agent neuf : la liste est celle des points
  `Bidi_Control` de PropList 18.0.0 et de l'UAX #9). Une liste par sujet : `BIDI_CONTROLS` sert déjà le coffre.
  Options écartées : retirer tout `Cf`, qui ôterait U+200D des emojis composés ; envelopper chaque texte dans un
  `<bdi>`, un complément jugé non nécessaire. — PR de #564
- **Les textes longs du détail (résumé, description, éditeur, produit, auteurs) sont lus en `str`, et un texte
  vide ou fait de blancs se dit : « Aucun résumé. », « Aucune description. », « Non renseigné », un auteur vide
  retiré ; un titre que le nettoyage vide devient « Sans titre », en français, au fil et au détail ; une version
  vide, « sans nom ».** Pourquoi (revue de code, tranché par time-knight) : la base ne borne que leur longueur
  (`schema.sql`), si bien qu'un résumé vide y est une valeur valide. `NonEmptyText` en aurait fait une page 500,
  et un titre vidé un lien sans nom (RGAA 6.2). Une seule définition du vide, `is_blank` : rien que des blancs et
  des caractères de format (`Cf`, comme U+200B), sans quoi un titre fait de U+200B s'afficherait vide (dernière
  revue de code). Option écartée : refuser ces items, alors que la base les tient. — PR de #564
- **L'identifiant d'une alerte est lu par un type `GhsaId`, ajouté à `items.py` à côté de `CveId`, et non
  nettoyé ni remplacé : un identifiant hors de sa forme est une réponse invalide de l'API (la page 500).** Tranché
  par time-knight le 2026-11-12 (dernière revue de code), écart mineur au plan qui laissait `items.py` intact.
  Pourquoi : la base tient `GHSA_ID` par sa GLOB, et la règle 4 de `conventions.md` nomme déjà `GhsaId` parmi
  les types d'`items.py`. Options écartées : un repli « sans identifiant », pour un cas que la base interdit ; le
  même type écrit dans le site, hors d'`items.py`, contre la règle 4. — PR de #564
- **Le bandeau d'une faille ou d'une alerte est un état nommé, calculé depuis `exploited` et `withdrawn_at` sans
  rien supposer, dont le texte est écrit dans le gabarit ; seul un item au catalogue KEV prend le style d'alerte.
  Une alerte dont la CVE est au catalogue dit « Entrée au catalogue KEV », avec sa limite ; une faille retirée a
  le bandeau de son retrait, jamais « Exploitée ».** Pourquoi : le mot porte l'état, la couleur ne fait que suivre
  (RGAA 3.1, C4). Le texte est dans le gabarit, parce qu'il porte le sens des sigles en HTML (`<i lang="en">`) et
  qu'aucun gabarit n'écrit `|safe`. `exploited` vrai veut dire « entrée au catalogue, retirée depuis ou non »
  (`specs-api.md`), et l'API ne relie pas encore une alerte à sa faille (C5). Option écartée : « Exploitée
  activement: oui » ou « non » pour une alerte, comme la maquette, alors que faux veut dire « absente du
  catalogue », pas « non exploitée ». — PR de #564
- **La couleur des liens visités ne va que sur le titre d'une carte.** Tranché par time-knight le 2026-11-12, un
  écart mineur au plan. Pourquoi : Opquast 141 vise les liens dans un texte ; un bouton plein vers la source
  perdrait son contraste en ardoise ; « ← Retour au fil » mène à `/`, toujours visité, où la couleur ne dirait
  rien. — PR de #564
- **Un test sert le site sur la vraie API de données de la base de test, en mémoire, sans réseau : il refuse une
  date du formulaire du fil, accepte un filtre, puis suit le titre d'une carte jusqu'au détail.** Ajout de
  time-knight, validé par Sabine le 2026-11-12. Pourquoi : c'est la preuve qu'attend C17.3 de la certification
  (une saisie validée et un second écran) ; jusque-là, aucun test n'allait de la page à la vraie API. Il n'est
  pas marqué `e2e`, réservé aux sources réelles et écarté de la CI : il tourne en CI. Limite : écrit après la
  route, il n'a jamais été rouge avant le code ; son rouge a été montré par deux mutations sur une copie (lien du
  titre retiré, route cassée). — PR de #564

### API de données : les tops servis au site, du jumeau JSON de leur fiche dans `watch` (#559)

Plan de la session K-B validé par Sabine le 2026-11-11 ; les écarts et les points de revue, tranchés par time-knight
sous la délégation de Sabine du 15/10.

- **L'API de données lit aussi le conteneur `watch` : `GET /tops/{top}` et `GET /tops/{top}/days` servent au site,
  au seul client `WEB`, les tops GitHub du jour et leurs jours passés. Elle les lit dans un jumeau JSON que
  `kb write-tops` écrit une fois à côté de chaque fiche (`tops/<top>/<jour>.json`), relu par un schéma fermé commun à
  l'écrivain et au lecteur (`TopProduction`, `items.py`).** Décision de Sabine du 2026-11-11 : c'est la forme du
  POC, et la cible reste un index en base des productions (#531). **Étend la décision du 2026-10-14 (« API de
  données »)** : l'API servait jusqu'ici la seule base (items, tendances) ; elle sert désormais aussi ce que les jobs
  publient dans `watch`, en lecture seule, par l'identité que lui donne #571. Pourquoi le jumeau plutôt que relire
  la fiche Markdown : le site ne lit que l'API de données et ne rend plus aucun Markdown (`markdown-it-py` et `nh3`
  retirées : ni dépendance ni risque XSS d'un rendu), et les fiches sont échappées pour Obsidian (`neutralize_text`,
  `post/vault_files.py`), donc illisibles brutes. Conséquence : le jumeau se revalide à la lecture par un schéma
  fermé, comme toute sortie que K-B sert (règle 8 de `poc.md`). Limites assumées, chacune avec sa parade écrite
  dans `docs/specs-api.md` (« Lecture de `watch` ») : (a) une requête froide peut dépasser les 30 s de lecture du
  site ; (b) des requêtes froides simultanées vont chacune au stockage ; (c) sur le Mac, sans `AZURE_CLIENT_ID`, les
  tops répondent 503 ; (d) l'historique commence au premier jumeau ; (e) une fiche écrite avant #559 peut recevoir
  le jumeau d'un relevé plus tardif du même jour, une fois, pour le dernier jour de chaque top. — PR de #559
- **Le marqueur d'une page de liste coupée court est suivi : 5 000 noms au plus, sur 2 pages au plus
  (`MAX_WATCH_FOLDER_NAMES`, `MAX_WATCH_FOLDER_PAGES`), au-delà 502 `watch_listing_too_long`.** Tranché par
  time-knight le 2026-11-12. Pourquoi : List Blobs peut rendre une page de moins de noms que demandé avec un
  `NextMarker` (Microsoft Learn, « List Blobs », « Remarks », lu le 2026-11-12). **Modifie le plan validé**, qui
  répondait 502 à tout marqueur : il aurait refusé une liste légitime. — PR de #559
- **L'heure d'un jumeau se nomme `ranked_at`, dans le jumeau comme dans la réponse ; l'en-tête Markdown de la fiche
  garde `collected_at`.** Tranché par time-knight le 2026-11-12 (option B). Pourquoi : l'API ne sert jamais une date
  de collecte (OWASP API3, `test_no_route_documents_a_raw_file_path_or_a_collection_date`), et ce test reste tel
  quel. Option écartée : servir `collected_at` en exemptant les tops du test, ce qui affaiblirait une preuve d'API3
  « Tenue » (`docs/specs-api.md`) pour sauver un nom, et donnerait deux sens à un même nom dans une API qui écrit
  `collected_at` « jamais servi ». Conséquence : l'exemption se serait ouverte à chaque production suivante (#560,
  #561). — PR de #559
- **Ce que le jumeau refuse, la collecte des plus étoilés et des plus forkés le refuse avant, par la page entière :
  un compte hors de 0 à 2^63 − 1, un nom de plus de 255 caractères.** Tranché par time-knight le 2026-11-12 (revue de
  #559). Pourquoi : un relevé que la source acceptait et que le jumeau refusait n'avait plus de fiche, et
  `kb write-tops` échouait à chaque passage en gardant le relevé ; la page entière, car retirer un dépôt décalerait
  les rangs du top (exception de la règle 1 de `conventions.md`). Le refus du jumeau reste un filet, tenu par son
  test. Prolonge la règle 4 de `conventions.md` (« Tout ce que la base refuse, l'item le refuse avant ») au jumeau.
  — PR de #559
- **Pendant une requête de l'API de données, tout échec du jeton de l'identité est 502 `exchange_storage_no_token`,
  la règle de `check_identity` des jobs ; jamais un 500, ni l'état d'un stockage qui n'a pas été joint.** Tranché
  par time-knight le 2026-11-12 (revue de #559). Pourquoi : l'API demande son jeton au milieu d'une requête, non
  avant comme un job, et azure-identity 1.27.0 laisse passer un `ValueError` ou un `AttributeError` sur une réponse
  qui n'est pas du JSON. Limite assumée : un délai de l'identité est aussi `exchange_storage_no_token`, et non
  `exchange_storage_timeout`. — PR de #559

## 2026-11-13

### Dépendances : `soupsieve` et OpenTelemetry montés pour des vulnérabilités publiées (#606)

- **`soupsieve` passe de 2.10 à 4.0.1, et les trois paquets d'OpenTelemetry de 1.45.1 à 1.45.2, dans `uv.lock` seul.
  Inverse le verrou de `soupsieve` en 2.10 du 2026-10-12.** Décision de Sabine, sur recommandation. Ce qui a
  changé : pip-audit a trouvé quatre vulnérabilités publiées entre le 12/11 et le 13/11 (CI de `main` rouge sur
  5bbe3ce). Une seule est atteignable par K-B : un sélecteur à combinateur descendant (`article article`,
  `etl/sources/tldr.py`) sur une page de TLDR très imbriquée, qui ralentirait la collecte. Les deux autres de
  `soupsieve` demandent un sélecteur écrit par l'attaquant, et celle d'`opentelemetry-api` un appel à `extract()`,
  que K-B ne fait pas. Pourquoi 4.0.1 : elle corrige les trois de `soupsieve` et a 9 jours de recul, ce qui garde la
  raison du 12/10 (pas de version du jour même). Options écartées : 4.1 (du 10/11), moins de recul sans correctif de
  plus pour K-B ; 3.0.x, qui laisse CVE-2026-126190 ; le tag v0.1.6 posé sur la CI rouge, qui aurait mis en ligne les
  versions vulnérables. Vérifié : sur les éditions `ai`, `tech` et `dev` du 13/11, la 2.10 et la 4.0.1 trouvent les
  mêmes articles, titres, résumés et `h1`, et aucun article n'est dans un `template`, que la 4.0 ne parcourt plus ;
  entre 1.45.1 et 1.45.2, les modules privés des journaux n'ont pas changé (relecture voulue par la décision du
  27/10), et le SDK ajoute une limite de 2 000 jeux d'attributs par instrument, loin des listes fermées de K-B.
  Limite assumée : la borne de `soupsieve` reste dans `uv.lock` seul. — PR de #606

### CI : `bicep-build` sur toute PR, contrôle exigé de `main` (#496)

- **`infra.yml` n'a plus de filtre de chemin : `bicep-build` construit `infra/main.bicep` sur toute PR vers `main` et
  tout push sur `main`, et devient un contrôle exigé du ruleset de `main`, posé par Sabine le 2026-11-14, juste avant
  la fusion.** Plan validé par Sabine le 13/11, sur la décision du 08/11 de tenir cette partie du « durcissement
  répétable » d'API8 (`docs/fiches-veille.md`). Pourquoi : avec le filtre, une PR pouvait fusionner sans que le Bicep se
  construise, et un contrôle exigé qu'un filtre saute reste en attente et bloque toute PR qui ne touche pas
  `infra/`. Options écartées : un job préalable qui saute la construction hors d'`infra/` (plus de code, et un job
  sauté par une condition rend « Success », ce qu'il faudrait encore rattraper) ; l'action `dorny/paths-filter`
  (une dépendance de plus dans la CI). Coût : 18 à 54 s de runner par PR (les dernières exécutions, le 11/11). Le
  ruleset changé juste avant la fusion, pas avant : les PR ouvertes des autres pistes attendraient sinon un
  contrôle jamais lancé ; elles le reçoivent à leur mise à jour sur `main`, que `strict` impose déjà.
- **Le reste du « durcissement répétable » se justifie, en trois écarts voulus** (décision de Sabine du 08/11) :
  le socle appliqué à la main (la CI n'a jamais le droit d'Owner qu'exigent les rôles) ; l'image changée hors du
  Bicep par `deploy.yml` (seul le digest change, vérifié contre le commit) ; aucune relecture exigée par le ruleset
  (une seule personne au dépôt, et une auteure ne peut pas approuver sa PR). Chacun a sa limite, son « Pour lever
  l'écart » et son « Pour réduire le risque » dans `docs/fiches-veille.md`, API8. Limite assumée : la mesure n'est
  tenue qu'une fois `bicep-build` exigé et vu vert sur une PR qui ne touche pas `infra/`. — PR de #496

## 2026-11-14

### Site : les tendances (#596)

Plan validé par Sabine le 2026-11-11 (partie « PR 2 » du plan de #564) ; deux décisions de Sabine du 2026-11-14 ;
points de revue tranchés par time-knight, sous la délégation de Sabine du 15/10.

- **`/tendances` montre une fenêtre de 3 jours de GH Archive par `GET /trends` : la plus récente, ou celle qui se
  termine le jour du formulaire. Le site calcule le rang (l'ordre de l'API, à partir de 1), le premier jour
  (`window_end` − 2 jours) et le lien vers GitHub ; il n'écrit pas « jusqu'à 60 dépôts ».** Pourquoi : la mission du
  11/11, qui relève ces écarts entre la maquette et l'API. L'API, tenue par une autre piste, reste inchangée, et
  `web/trends.py` calcule sans entrée ni sortie, donc testable seul. Le jour est lu par `WrittenDay`, la règle des
  routes de l'API, désormais commune au fil : `2026-02-30` n'est plus réaffiché dans le champ du fil. — PR de #596
- **Le tableau a 560 px de large au moins (`35rem`), comme la maquette, et défile dans son cadre sur un écran plus
  étroit. Le cadre prend le focus (`tabindex="0"`) : c'est une région nommée par la légende. Il est le conteneur de
  la légende (`container-type: inline-size`), qui garde sa largeur (`max-inline-size: 100cqi`).** Décision de Sabine
  du 2026-11-14 pour les 560 px ; le cadre (C7 de #564) et la légende, tris de time-knight. Pourquoi : la maquette
  (`min-width: 560px`) ; WCAG 1.4.10 exempte un tableau de données ; WCAG 2.1.1 demande le clavier, sans script. Sans
  borne, la légende, qui fait partie du tableau, sortirait de l'écran. `cqi` est retenu parce que la fonction
  « Container queries » est Baseline « widely available » depuis le 2025-08-14 (web-features explorer ; unités dans
  Chrome et Edge 105, Firefox 110, Safari 16, caniuse, lus le 14/11). Options écartées : la largeur naturelle du
  tableau, qui ne défilait qu'avec un nom aux longueurs maximales de GitHub mais tassait les colonnes sur un
  téléphone, loin de la maquette ; pour la légende, `calc(100vw - …)`, qui dépend des marges de la page et compte la
  barre de défilement de la page. Limite assumée : sous 600 px environ, les colonnes des comptes ne se voient qu'en
  faisant défiler le cadre (à 390 px, le cadre en montre 356 px sur 560), et une barre de défilement superposée
  (macOS, iOS) n'apparaît qu'au défilement. Pour réduire le risque : une ombre au bord du cadre quand le tableau
  continue, en CSS seul (`background-attachment: local`, technique de Lea Verou, 2012 ; le cadre a un fond uni,
  condition de la technique, CSS-Tricks), faisable avec nos droits : #618 (XS, au Backlog, tri de time-knight). Un
  auteur la dit peu fiable sur mobile ; support des navigateurs non vérifié ce jour. — PR de #596
- **L'annonce « (en anglais, site externe, nouvel onglet) » reste visible dans chaque lien du tableau, comme
  ailleurs sur le site.** Décision de Sabine du 2026-11-14, sur l'option (a) que recommandait time-knight après la
  relecture d'accessibilité. Confirme la décision de #587 (2026-11-11). Option écartée (b) : la flèche seule visible
  dans le tableau, l'annonce dans le nom accessible et expliquée sous le tableau. Les lignes seraient plus basses,
  mais une personne voyante ne lirait pas l'annonce au moment du clic (G201), et le tableau ferait autrement que le
  reste du site (Opquast 138). Limite assumée : à 390 px, l'annonce passe sur deux lignes et rend chaque ligne plus
  haute. À l'impression, la flèche et l'annonce sont retirées du seul tableau. — PR de #596
- **Le champ du jour reste un `input type=date` ; un jour refusé n'y revient pas, et son message le nomme quand il a
  la forme d'un jour (`DAY_SHAPE`, chiffres ASCII et tirets seuls : « Date invalide: 2026-02-30 n’existe pas. ») ;
  toute autre valeur n'atteint jamais la page.** Tri de time-knight du 2026-11-14 (Opquast 81 : les données
  refusées restent modifiables). Pourquoi : un champ date natif ne peut pas tenir une valeur invalide (WHATWG), et
  le sélecteur de date du navigateur n'envoie qu'un jour valide : une valeur refusée ne vient que d'une adresse
  écrite à la main. Ne nommer que des chiffres et des tirets : un lien qui ferait dire à la page un texte choisi
  (usurpation de contenu) n'a rien à y mettre, et la longueur est fixe. Options écartées : un champ texte, qui
  perdrait le sélecteur de date ; nommer toute valeur reçue, ce que le fil s'interdit déjà (« a value received is
  never sent back raw », `web/feed.py`). Limite assumée : Opquast 81 tenue en partie, la valeur ne revient pas dans
  le champ ; un jour valide que l'API refuserait (même règle `WrittenDay` que le site) vide aussi le champ, sans
  être nommé. — PR de #596
- **Le dépôt est l'en-tête de sa ligne (`th scope="row"`), en graisse normale ; les colonnes portent les mots de la
  maquette, « Étoiles gagnées » et « *Forks* gagnés ».** Tris de time-knight (relecture d'accessibilité). Pourquoi :
  RGAA 5.7, un lecteur d'écran annonce le dépôt avec chacun de ses comptes ; « gagnées » reste dit avec son
  échantillon, dans la légende et l'introduction (GH Archive ne voit qu'environ 1 % des étoiles). Option écartée :
  le rang en en-tête de ligne, un numéro qui ne nomme pas la ligne. — PR de #596
- **Un nom que `is_repository_name` refuse (un segment `.` ou `..`, ou `..` en son sein) garde sa ligne et son
  rang, écrit sans lien ; une fenêtre d'un autre jour que celui demandé est hors contrat (page 500).** Tris de
  time-knight sur les deux `/code-review`. Le premier tri renvoyait toute la fenêtre en page 500 pour un tel nom ;
  le second l'a révisé : un seul nom ne doit ni cacher 59 lignes justes ni fausser le rang des autres. Un navigateur
  résoudrait `https://github.com/owner/..` vers une autre page de GitHub, d'où l'absence de lien. Une fenêtre d'un
  autre jour, affichée, ferait dire à la page une fenêtre et en montrer une autre. Limite assumée : un tel nom peut
  entrer en base. Pour réduire le risque : la même règle à l'import des tendances (#615, faisable avec nos droits).
  — PR de #596

### API de données : les comptes rendus de veille servis au site, du jumeau JSON de leur fiche dans `watch` (#560)

Plan de la session K-B validé par Sabine le 2026-11-14 ; les écarts et les points de revue, tranchés par time-knight
sous la délégation de Sabine du 15/10. Prolonge l'entrée de #559 (2026-11-12), sans la modifier.

- **`kb digest` écrit, une fois, à côté de chaque fiche d'un sujet son jumeau JSON (`veille/<sujet>/<jour>.json`),
  que l'API de données sert au seul client `WEB` : `GET /digests/{subject}` et `GET /digests/{subject}/days`, relu
  par un schéma fermé commun à l'écrivain et au lecteur (`DigestProduction`, `items.py`). Chaque source y garde son
  `item_id`, que la fiche n'écrit pas.** Décision de Sabine du 2026-11-11 : la forme de #559, pour la même raison
  (le site ne lit que l'API de données et ne rend aucun Markdown) ; la cible reste un index en base (#531).
  L'`item_id`, pour que le site mène de la source à l'item du fil (issue #560). Limites assumées, chacune avec sa
  parade dans `docs/specs-api.md` (« `GET /digests/{subject}` ») : (a) l'historique commence au premier jumeau ;
  (b) en ligne, rien avant le tag, une exécution de `caj-kb-digest-watch` et l'abonnement Azure rétabli ; (c) un
  jumeau non écrit après sa fiche perd ce jour sur le site ; (d) `item_id` est une clé de substitution, qu'une base
  refaite renumérote ; (e) un sujet retiré rend ses comptes rendus inaccessibles ; (f) les textes du modèle et les
  titres des sources peuvent nommer une personne ; (g) une affirmation sans caractère visible fait refuser le
  jumeau, et le compte rendu du sujet attend le lancement suivant (parade : #624, tranché par time-knight, revue de
  code de #560). — PR de #560
- **Le jumeau est construit et relu par son schéma avant la fiche : refusé, ni fiche ni jumeau, le sujet échoue
  (`twin_refused`) et garde son début ; sinon la fiche, puis le jumeau.** Plan validé (point 1), comme #559 : rien
  n'est écrit que l'API refuserait, et le sujet gardant son début (#565), son compte rendu suivant recouvre la
  fenêtre, sans perte. La fiche avant le jumeau (raison déduite du code par la session, validée par time-knight
  le 2026-11-14) : la fiche seule fait avancer le début du sujet (`find_previous_until`) ; un jumeau écrit avant une
  fiche en échec montrerait au site un compte rendu absent du coffre, dont le suivant relirait la fenêtre, et
  refuserait un nouveau lancement du même jour (`twin_exists`). Le revers est la limite (c). — PR de #560
- **Un seul lecteur de `watch` pour toutes les sortes de jumeaux : une `TwinKind` par sorte (`TOP_TWINS`,
  `DIGEST_TWINS` : dossier, schéma, contrôle du dossier et du jour, borne en octets, nombre gardé), et à chaque
  sorte son cache des productions lues.** Plan validé (point 4). Écarté : un second lecteur copié, que #561 aurait
  triplé. Les listes, une par dossier (9 sujets et 2 tops, un ensemble fermé), gardées 60 s ; les productions,
  8 tops et 16 comptes rendus (le dernier jour des 9 sujets et une marge) : lire les comptes rendus ne fait pas
  oublier un top. Choix de forme annoncés à time-knight le 2026-11-14 et acceptés : des fonctions typées pour lire
  le dossier et le moment d'une production, plutôt qu'un `getattr` sur un nom de champ, non typé ;
  `WATCH_CACHED_PRODUCTIONS` renommée `WATCH_CACHED_TOPS`, son nom devenu faux. — PR de #560
- **Un jumeau de compte rendu fait 400 000 octets au plus (`MAX_DIGEST_TWIN_BYTES`) : le plus gros que son schéma
  permet à `kb digest` en fait 389 968, mesuré le 2026-11-14 ; servi, il reste sous le 1 Mo que le site lit.**
  Tranché par time-knight le 2026-11-14. Pourquoi : la borne refuse avant le téléchargement ce que `kb digest` ne
  peut pas écrire (OWASP API4:2023) ; prise sur le pire cas mesuré plutôt que sur les 4 Mo d'une fiche, elle borne
  aussi le cache, 6,4 Mo pour 16 comptes rendus. Un test refait la mesure sur les bornes du schéma : une borne
  relevée qui ferait dépasser les 400 000 octets le fait échouer. — PR de #560
- **`subject` est un `Literal` de l'API de données, `DigestSubjectName`, tenu égal à `DIGEST_SUBJECTS` par un
  test ; un autre sujet répond 422.** Plan validé (point 5). Pourquoi un `Literal` écrit en clair (raison de la
  session, validée par time-knight le 2026-11-14) : il donne l'`enum` des sujets dans l'OpenAPI, et mypy le
  vérifie ; un type construit de `DIGEST_SUBJECTS` à l'exécution ne se vérifie pas statiquement. Limite (e)
  ci-dessus. — PR de #560

### Documentation publiée par un site MkDocs sur GitHub Pages (#167)

- **Les fiches de `documentation/` deviennent un site statique, construit par MkDocs 1.6.1 avec le thème Material for
  MkDocs 9.8.1, en mode strict sur chaque PR (`docs.yml`), et publié sur GitHub Pages à la main.** Le format, un site
  publié par MkDocs ou un équivalent sur GitHub Pages, est la décision de Sabine du 2026-11-11 pour le critère du
  « format qui respecte les recommandations d'accessibilité » (tri des relectures « jury » des fiches) ; l'outil, son
  « go » du 2026-11-12, sur la recommandation de time-knight. Pourquoi MkDocs avec Material : c'est l'outil demandé pour le format
  (rapporté par time-knight) ; Material reçoit ses corrections de sécurité jusqu'au
  2027-05-05, après le rendu et la soutenance ; il borne MkDocs sous la version 2. Options écartées : Zensical 0.1.1,
  successeur de Material par la même équipe, en Beta depuis le 2026-11-10 (il lit `mkdocs.yml` : migration possible
  plus tard) ; Sphinx avec MyST (les schémas Mermaid à reprendre) ; Jekyll (Ruby, une seconde pile). La dépendance
  vit dans un groupe à part, `docs`, que ni les tests ni l'image n'installent (choix 2 du même « go »). Les règles
  suivies (AVH, Microsoft, RGAA 4.1.2) et leur contrôle : `documentation/accessibilite_pour_docu.md`.
- **Écarts du 2026-11-14 au plan, acceptés par time-knight sous la délégation de Sabine du 15/10.** L'audit de la CI
  exporte tous les groupes (`--all-groups`) : `uv export` laisse le groupe `docs` de côté par défaut, et une faille de
  MkDocs ou de Material fait donc échouer `audit` sur toute PR. `actions/configure-pages` retiré : ses sorties ne
  servent qu'à l'adresse du site, déjà fixée par `site_url`. La publication est bornée à `main`, car un
  `workflow_dispatch` peut nommer toute branche. L'accent du thème passe de `#526cfe` (4,26:1 sur blanc, sous le seuil
  du RGAA 3.2) à `#303f9f` (8,98:1). Mermaid, que le plugin `privacy` télécharge d'unpkg dans sa version flottante
  `mermaid@11`, est vérifié par son empreinte, celle de Mermaid 11.17.2 recoupée avec l'intégrité publiée par npm ;
  option écartée : une version exacte chargée par `extra_javascript`, qui fixe aussi le fichier mais charge 3,5 Mo
  sur chaque page, au lieu des seules pages à schéma. `deploy.yml` ne change pas : une exécution manuelle de `Docs`
  en échec fait refuser le tag de son commit, parade écrite dans la fiche de l'intégration continue (relancer `Docs`,
  ou livrer un commit suivant) ; exclure `docs.yml` de son contrôle est écarté, car c'est un contrôle de sécurité de la
  livraison.
- Limites assumées : le rendu au lecteur d'écran n'est pas vérifié (parade : un essai VoiceOver par Sabine sur une
  fiche par lot) ; la publication attend que le dépôt soit public, puisqu'un site publié depuis un dépôt privé est
  public ; Material est en fin de vie le 2027-05-05, sans migration faite ; une nouvelle version 11 de Mermaid demande
  de revérifier et de changer l'empreinte. — PR A de la tâche 2 (Refs #167, #623)

## 2026-11-17

### Appel du modèle : les réglages des modèles du banc de C7 (#627)

Mission de time-knight du 2026-11-17, avec l'accord de Sabine (« OK PR de la branche du banc ») ; le code, écrit et
testé sur la branche du banc du 16/11.

- **`KB_LLM_REASONING_EFFORT` accepte `none`, `minimal` et `low` ; toute autre valeur arrête le démarrage.**
  Pourquoi : gpt-6.1-sol, le service que préconise le banc de C7 pour C8, refuse `none` et `minimal` et demande
  `low` ; gpt-5-nano et gpt-5-mini ne descendent pas sous `minimal`. Sur `main`, seul `none` passait : C8 aurait
  décrit un réglage que le code refuse. La liste reste fermée (`ReasoningEffort`, `core/config.py`), comme avant :
  une valeur au-delà de `low` n'a pas d'usage. Limite assumée : à `minimal` ou `low`, le raisonnement compte dans
  `max_completion_tokens`, que K-B ne relève pas (1 024 pour la sélection des tendances) ; tri de la revue de code
  par time-knight le 2026-11-17 : pas de code, la mesure du banc à l'appui (gpt-6.1-sol à `low`, aucun appel coupé
  sur 5 passages ; gemini-4-hydrogen, choix coupé 2 fois sur 5 ; `docs/fiches-veille.md`, « Réglages d'appel »),
  remesurée par l'essai de bout en bout de C8. — PR de #627
- **`KB_LLM_SEND_PROMPT_CACHE_OPTIONS` (`true` par défaut) : à `false`, `prompt_cache_options` ne part plus, pour
  un modèle d'avant GPT-5.6 ou un autre fournisseur, qui le refusent par un 400.** Revient en partie sur l'entrée du
  2026-10-17 (« Appel du modèle : cache de prompt coupé »), qui écartait une variable « sans second usage
  aujourd'hui » et annonçait un réglage « avec le second modèle, si besoin » : le banc de C7 en est le second usage.
  Le défaut garde la décision de 2026-10-17 en production : sans la variable, rien ne change pour gpt-6-luna.
  Limite assumée : à `false`, le fournisseur peut garder les items dans son cache de prompt, d'où l'entrée
  suivante. — PR de #627
- **`kb serve-ai` refuse de démarrer avec `KB_LLM_SEND_PROMPT_CACHE_OPTIONS=false` et
  `KB_DEPLOYMENT_ENVIRONMENT=production` ; `false` reste accepté en local et en bac à sable.** Tranché par
  time-knight le 2026-11-17 après un relecteur neuf (délégation de Sabine du 15/10), sur le constat C2 de la revue
  de code. Pourquoi : à `false`, le cache de prompt du fournisseur garde le texte des items (données personnelles
  possibles) au moins 30 minutes, alors que le registre dit le cache coupé ; le même refus que `KB_TRACE_CONTENT=all`
  en production (`metrics_export.py`) ; aucun usage bloqué, gpt-6-luna et gpt-6.1-sol acceptant le champ (banc du
  16/11). Option écartée : une garde par l'écrit seul (registre, `MEMORY.md`), la recommandation de la session, que
  rien ne fait respecter. Une valeur de `KB_DEPLOYMENT_ENVIRONMENT` posée hors de `sandbox` et `production` est
  refusée elle aussi avec `false` (constat R1 de la seconde revue, tranché par time-knight après un relecteur neuf) :
  une faute de frappe échoue fermé au lieu de faire sauter le refus ; non posée, c'est un poste local. Limite
  assumée : un Gemini en production demanderait sa ligne au registre et la levée de ce refus. — PR de #627
- **`KB_LLM_MODEL` accepte un modèle derrière son éditeur, `<éditeur>/<modèle>`, une barre oblique au plus, chaque
  côté au motif d'un nom de modèle (`MODEL_NAME`).** Pourquoi : Google Cloud nomme ses modèles `google/<modèle>`
  sur son point compatible Chat Completions. Le nom ne part que dans le corps JSON, jamais dans l'URL ni un
  en-tête (un test) ; `MODEL_NAME` contrôle aussi le nom que `kb digest` et `kb trend-report` lisent dans la
  réponse de l'API IA (qui le tient de `KB_LLM_MODEL`, jamais du fournisseur) avant qu'il n'entre dans une fiche,
  et l'admet donc lui aussi avec une barre oblique. Options écartées : non consignées par la session du banc.
  — PR de #627

## 2026-11-18

### Monitorage et production : K-B passe à gpt-6.1-sol (#631 à #635)

Seuils décidés par Sabine dans la nuit du 18/11, recopiés par la mission de time-knight ; plan de la session validé
par Sabine le 2026-11-18 (« plan validé avec les précisions de tn-orchestrateur »).

- **Le budget Azure `budget-kb` passe de 30 à 40 € par mois, pour tout K-B : hébergement et inférence.** Revient
  sur les 30 € de #437, qui ne voyaient pas le modèle : sa ressource n'avait pas l'étiquette `project=k-b`. Pourquoi
  (Sabine) : 40 € est le budget visé du benchmark de C7. Le filtre `project=k-b` et les trois seuils (50 % et
  100 % du réel, 100 % de la prévision) restent. Limite assumée : `sabl-certif-resource`, dans le même groupe de
  ressources, n'entre dans le budget qu'une fois étiquetée, un geste de Sabine après la fusion. — PR de #632
- **L'alerte `KbModelCostOverBudget` passe de plus de 1 USD à plus de 2 USD sur 7 jours.** Revient sur le budget du
  2026-11-08 (1 USD, `documentation/monitoring_pour_docu.md`), fixé pour gpt-6-luna. Pourquoi (Sabine) : 2 USD est
  au-dessus du maximum normal de gpt-6.1-sol, 1,55 USD par semaine : l'alerte signale une dépense anormale.
  — PR de #632
- **Le coût estimé est compté aux prix de gpt-6.1-sol : 2,40 USD en entrée et 12,00 USD en sortie par million de
  jetons (Data Zone Standard, France Central, contexte court).** Relus le 2026-11-18 dans l'API Azure Retail Prices
  (`core/config.py`, `docs/fiches-veille.md`, « Sources »). Revient sur les prix de gpt-6-luna du 2026-10-21. Limite
  assumée, inchangée : tout appel est compté à ces prix, quel que soit `KB_LLM_MODEL`, et le contexte long
  (4,80 et 18,00 USD) n'est pas distingué. — PR de #631
- **Une alerte `KbModelCallFailures` : la part des appels en échec après leur nouvelle tentative, sur 24 h, au-dessus
  de 0 %.** Un échec est un délai dépassé, un service indisponible, un 429, le filtre de contenu (`k_b_outcome`,
  aux mêmes valeurs que `error.type`) ou une sortie coupée au plafond de jetons (`llm_truncated`, ajoutée par
  Sabine sur le constat C1 de la revue de code : aucune alerte ne la voyait, et le raisonnement de l'effort
  `low` compte dans ce plafond). Seuil : recommandation de la session et de time-knight, choisie par Sabine
  le 2026-11-18. Pourquoi : un appel en échec est un sujet ou un compte rendu qui manque. Limite assumée : jusqu'à
  #630, l'alerte se déclenchera à chaque fiche de veille (le 2026-11-17, 5 sujets sur 9 étaient en
  `llm_timeout`), et c'est un vrai signal. — PR de #633
- **Une mesure nouvelle, `k_b.request.duration`, de chaque demande de compte rendu entière (`POST /digests` et
  `POST /trend-reports`), et une alerte `KbRequestOverDuration` : la part des demandes de plus de 180 s, sur 24 h,
  au-dessus de 0 %.** Pourquoi (Sabine) : 180 s, c'est sous l'échéance de 200 s d'une demande, que `POST /digests`
  a atteinte le 2026-11-17 avec gpt-6.1-sol. « Compte rendu » couvre les deux routes, le vocabulaire de Sabine
  (interprétation de la session, acceptée par time-knight). L'attribut de la route est `http.route`, comme sur les
  spans racines. La part se lit par le nombre de demandes moins celles du palier de 180 s. Option écartée par la
  session : `histogram_quantile(1, …) > 180`, qui groupe par `le` et lit une borne de palier, pas une durée. Limite
  assumée : la forme de `le` dans Grafana Cloud (`180` ou `180.0`) n'est pas encore relevée, et l'expression lit les
  deux ; aucun scénario du bac à sable ne déclenche ces deux alertes. — PR de #634
- **En production, l'effort de raisonnement passe de `none` à `low` (`infra/main.bicep`), dans la même passe que
  le modèle gpt-6.1-sol, jamais l'un sans l'autre.** Pourquoi : gpt-6.1-sol refuse `none` (« Appel du modèle : les
  réglages des modèles du banc de C7 », 2026-11-17), et gpt-6-luna était réglé à `none`. Le modèle et l'adresse
  restent des paramètres de la seconde passe, donnés par Sabine. — PR de #635

### Fiches de veille : les sujets rédigés en parallèle, le délai par appel à l'échéance (#630, #640)

Décisions de Sabine du 2026-11-17 (livrable E2, C7, partie 4.3) et du 2026-11-18, recopiées par la mission de
time-knight ; plan de la session relu par time-knight, validé par Sabine le 2026-11-18 (« plan validé ; 429 :
d'accord, à écrire ; délai par appel : 200 s, égal à l'échéance, avec le calcul en commentaire »).

- **Les sujets d'une demande de `POST /digests` sont rédigés en parallèle, un fil par sujet, tous à la fois ; le
  classement reste en série.** **Inverse** l'option écartée le 2026-10-17 (« Fiches de veille : la durée d'une
  demande », plan de #205 : « le parallèle […] pour un gain sans besoin mesuré »). Ce qui a changé : la mesure. Le
  2026-11-17, sur 300 items et gpt-6.1-sol, la demande a atteint son échéance de 200 s avec 4 fiches sur 9, les
  rédactions prenant 23,4 à 30,7 s chacune l'une après l'autre (#630). Pourquoi (Sabine) : plus simple et plus adapté
  que le passage en asynchrone, qui ne viendra que si la parallélisation ne suffit pas (YAGNI). Les deux objections
  du 17/10 tombent : le `replay` reste en série, donc tel quel (ses réponses suivent l'ordre des requêtes), et le
  quota de gpt-6.1-sol, 250 000 jetons par minute, tient les 9 rédactions à la fois (environ 150 000 jetons
  estimés). Le client d'httpx2 est partagé (pool sûr entre fils, doc d'httpx2 lue par Context7 le 2026-11-18) ;
  chaque fil reçoit une copie du contexte, pour que son span reste sous la demande. Les fiches et les lignes de
  métriques gardent l'ordre de la liste. Options écartées par la session : borner le nombre de fils (environ 60 s de
  plus en trois vagues, pour peu de protection contre un 429) ; un `replay` apparié au sujet (du code et un
  réenregistrement du jeu de référence, pour un replay que rien n'oblige à paralléliser). Limite assumée : le
  `replay` ne passe pas par les fils ; seuls les tests du fournisseur simulé les exercent. — PR de #630
- **Après un 429, « plus aucun envoi » ne vaut plus que pour un sujet pas encore parti.** Révise la règle du
  2026-10-17 (#205, minimisation, RGPD art. 5.1.c) : en parallèle, les items de tous les sujets partent à la fois,
  avant qu'un 429 puisse être connu. Accepté par Sabine le 2026-11-18, sur la recommandation de la session et de
  time-knight : les 9 rédactions tiennent sous le quota, et borner les fils coûterait environ 60 s pour peu de
  protection. La règle reste entière en série (le `replay`). — PR de #630
- **Le délai de lecture d'une réponse du modèle passe de 90 à 200 s (`LLM_CALL_TIMEOUT_SECONDS`), l'échéance
  d'une demande.** **Révise** « Appel du modèle : délai de lecture à 90 s » (2026-10-17). Ce qui a changé : le
  modèle. Au débit mesuré sur gpt-6.1-sol le 2026-11-17 (environ 20 ms par jeton, contre 7,35 sur gpt-6-luna), une
  sortie de 8 192 jetons prend environ 164 s, 229 s avec la marge de 40 % de #158. Valeur choisie par Sabine ; le
  pourquoi de 200 plutôt que 229 n'a pas été dit, déduction de la session à confirmer par Sabine : l'échéance ramène
  déjà chaque délai au temps restant (`Deadline.cap`), si bien qu'un délai au-delà de 200 s ne change rien. Ce que
  cela change : l'échéance est la seule borne d'un appel, et un appel bloqué n'est plus relancé, un classement
  compris, qui part en premier et emporte alors la demande (504 `llm_timeout`). Options écartées par la session :
  170 s (4 % de marge) ; un délai par étape (aucun besoin écrit). Un test garde le calcul (la plus longue sortie au
  débit mesuré tient dans le délai) et l'égalité avec l'échéance. — PR de #640

## Décisions encore ouvertes

- **Le rôle Log Analytics Reader d'`id-kb-data-api` sur `log-kb`** (2026-11-11, #571) : il donnerait au back office
  du site ses chiffres de fonctionnement sans Grafana (architecte du 11/11). Pas encore décidé par Sabine, hors du
  1er passage d'infra du site.

- **Le tri du fil** (2026-11-11, #550) : choisir l'ordre de `GET /items`, aujourd'hui du plus
  récent au plus ancien par la date de la source ; à préciser par Sabine, hors de #550.

- **Une limite de connexions du serveur** (2026-11-05, #161) : `limit_concurrency` d'uvicorn, écarté
  de la PR 2A parce qu'il compte les connexions muettes, à mesurer derrière l'entrée d'ACA. Laissée
  ouverte par Sabine le 06/11 (#414), qui n'a rien mesuré : en ligne, les deux API sont internes, et seules
  les pièces de `cae-kb` les joignent.

- **Les seuils des critères des tendances** (2026-10-30) : 2 jours actifs pour « durable », 5 rangs
  pour « en accélération ». À revoir sur les premiers comptes rendus réels (#370).

- **Le filtre des forks dans le compte rendu des tendances** (2026-10-30) : les forks entrent après la
  v1, avec un filtre (`is_template` ou autre) à décider sur les premiers vrais tops.

- **Un sujet secondaire par item au classement** (2026-10-26, idée de Sabine) : une case de sujet
  principal et une case de sujet secondaire, pour ne pas perdre qu'un item touche deux sujets.
  Questions : à quoi servirait-il (une ligne « Voir aussi » dans la fiche, le wiki, l'annotation
  des items en base) ; le modèle remplit-il à bon escient une case facultative ; tient-il sous les
  limites du mode strict (deux propriétés par item, soit 100 pour un lot de 50, la limite d'Azure).
  Rouvre « Un sujet par item » (2026-10-15, PR de #203), qui écartait plusieurs sujets par item
  pour les doublons entre fiches. À décider après les essais de #210.

- **Lecteurs maison ou pydantic-settings** (2026-10-21, gardés le 2026-10-25 « pour le moment ») :
  les lecteurs `read_…_or_refusal(environ)` de K-B, sans dépendance, contre pydantic-settings, la
  solution standard. Ce que coûte pydantic-settings : une dépendance directe nouvelle, la réécriture
  des neuf lecteurs, des familles de variables à préfixe variable (`KB_DATA_API_KEY_<CLIENT>`) mal
  servies, et une erreur de validation qui recopie la valeur refusée, jeton compris, sauf
  `hide_input_in_errors`. Ce qui pourrait faire changer d'avis, selon time-knight (non dit par
  Sabine) : beaucoup plus de variables, ou des lecteurs maison qui divergent.

- **Une seule façon de créer les sources qui ont besoin de l'environnement** (2026-10-25) : les
  sources GitHub (leur jeton, aujourd'hui lu par `etl/sources/github/api.py`), Zotero, les clips et
  GH Archive ; lève l'exception provisoire de « l'environnement lu à un seul endroit ».

- **La base au temps 3** (2026-10-20) : SQLite et Blob, ou PostgreSQL. Avec la première option,
  recommandée par le rapport de l'architecte, la base est un fichier produit par le job de
  collecte et d'import, puis rangé dans Azure Blob Storage ; rien ne change aux temps 1 et 2.
  Non tranchée le 2026-10-20. Met en attente « PostgreSQL au 08/11 » (« POC du 25/10 »,
  décision 2) et la sauvegarde de la base, donc la purge du brut après deux sauvegardes saines
  (2026-11-04) ; l'étape 8 de la procédure de tri n'en dépend plus depuis le 2026-11-04 (#83). `README.md` et `docs/stockage.md` (« Le SGBD ») y renvoient. **Close le 2026-11-06** :
  PostgreSQL en ligne (« Base : PostgreSQL en ligne, par un adaptateur maison (#417) ») ; la
  sauvegarde de la base et la purge qui en dépend passent à #390.

- **Un code de sortie dédié à l'authentification**, pour toutes les commandes (2026-10-21) : à
  reconsidérer avec #160 (jetons qui expirent) ; une clé refusée sort aujourd'hui en 1.


- **Révision après le juge, en un seul tour** (2026-10-16) : la coder ou non, au vu des taux de
  l'étalonnage du juge (#224), si les fiches sont trop maigres (« Fiches de veille : le LLM
  juge »). **En attente depuis le 2026-10-20** : le juge sort du contrat des fiches (« Squelette E1
  E3 : cadrage du 20/10 », décision 2).

- **Remplir `newsletter_article.publication_id`** (2026-10-12) : quand le lien d'un article TLDR
  est `https://arxiv.org/abs/<id>`, le rattacher à sa PUBLICATION, créée sans ses colonnes arXiv
  si arXiv ne l'a pas encore donnée (ce qu'une alerte GitHub fait déjà pour sa CVE). Signalé par
  #57, sans issue ; 2 articles sur les 272 du brut du 2026-09-30 au 2026-10-09.

- **Noms des colonnes de date** (2026-10-12) : ils ne disent pas d'où vient la date
  (`vulnerability.date_added` est une date CISA, `vulnerability.revised_at` et `withdrawn_at`
  sont des dates K-B, `publication.revised_at` est une date arXiv). Le renommage sera décidé avec
  le modèle des publications (Sabine, relevé à la PR de #105). Le modèle de la bibliothèque
  (2026-10-13) nomme ses dates nouvelles par leur événement Zotero, sans renommer les colonnes
  existantes.

- **Conservation des vieilles veilles** (2026-10-19) : le *cleansed* est immuable, avec le
  « petit bémol pour les vieilles veilles, à voir » de Sabine (« Brut : catalogues d'état et
  conservation »). **Close le 2026-10-20** : la veille est purgée au terme de sa durée, 3 ans
  (« Squelette E1 E3 : cadrage du 20/10 », décision 5).
- **Licence du schéma de Zotero** (2026-10-11) : le code de Zotero est sous AGPL v3 « sauf
  fichier qui dit autrement » (page « Licensing » de zotero.org), K-B sous CC BY-NC 4.0.
  La base d'essai réécrit 15 tables aux noms et types de Zotero ; si cela pose une question de
  licence n'est pas tranché, et l'en-tête du fichier de schéma de Zotero n'a pas été lu.
  **Close le 2026-11-06** : la fixture est gardée, avec la mention de l'AGPL v3 ou plus (« Mise en
  public du dépôt (#278) »).
- **Notes Zotero et autres types d'annotation** (soulignement, note, encre, image) : remis à
  plus tard par Sabine le 2026-10-11.

- **Nommage des tables et des colonnes.** Gardé tel quel le 2026-10-02 ; Sabine demandera les
  renommages à l'usage, une fois les schémas sous les yeux.
- **L'effacement d'un login de propriétaire de dépôt suivi** (#268), dernier reste de « Durées de
  conservation et fréquence de la purge », close le 2026-11-04 (« Conservation : la base, source
  de vérité, et la purge hors de l'ETL (#83) ») : décision de Sabine en attente.
- **Liste d'exclusion** des personnes qui demandent l'effacement, pour qu'une collecte ou une
  reconstruction ne les réintroduise pas : proposée dans le registre, à concevoir dans #20.
  Indispensable avec une base reconstruite, en développement (2026-10-10).
- **Questions laissées par la relecture indépendante du 2026-10-09**, à décider par Sabine :
  DOCUMENT ou CONTENU pour le texte complet (une publication décrite par plusieurs items et un
  document Zotero hors arXiv sont tranchés le 2026-10-13, « Modèle de la base : bibliothèque
  Zotero » ; le texte d'un clip est rangé dans `clip.body` le 2026-10-17, en attendant) ; les
  versions d'un clip annoté sont tranchées le 2026-10-17 (« Collecte : clips (suite) »), puis
  révisées le 2026-10-19 (« Collecte : mise à jour des `.md` importés »).
- **Transfert hors UE par les agents** : un agent qui lit les items par l'API envoie leur contenu
  au fournisseur du modèle (États-Unis). Cadre juridique non vérifié. **Révisée le
  2026-10-15**, puis **le 2026-10-16** : l'API IA appelle gpt-6-luna sur Azure AI Foundry, en
  déploiement Data Zone Standard UE (« Modèle des fiches : gpt-6-luna sur Foundry ») ; à inscrire au registre (#157).
  La question reste ouverte pour les clients de l'API de données.
- **Motif d'un rejet pour longueur** : le critère de l'issue sur le motif des rejets (#92) ne
  garde que le champ et le type d'erreur, alors que la décision du 2026-10-08 demande la longueur
  reçue et le maximum. À accorder par Sabine avant de coder #92 (2026-10-10).
- **Totaux GraphQL de TENDANCE** (2026-10-11, réduit le 2026-10-13) : `trend` est en base
  (#142) ; restent les étoiles et forks totaux lus par GraphQL (#143) et leur brut (relecture du
  2026-10-09).
- **Recollecter une fenêtre GH Archive déjà prise** (2026-10-13) : la règle par fenêtre garde le
  premier classement vu ; un classement compté sur des tables appauvries (fenêtres du 2026-10-10,
  du 2026-10-11 et du 2026-10-12) ne se corrige qu'en retirant son fichier brut et en
  reconstruisant la base. Signalé par #142,
  sans issue ; la détection d'une table incomplète (#141) empêche ou marque une collecte à
  venir, elle ne reprend pas une fenêtre déjà collectée.
- **Un seul chemin de lecture pour les items et les classements** (2026-10-13) : `trend` est lu
  par `read_trend_files`, à côté du lecteur générique, dont le contrat rend un `Item`. Signalé
  par #142, sans issue ; aucune issue du rangement (#107, #85, #135, #136) ne le porte.
  **Close le 2026-10-22** : `etl/transform.py` lit les deux par un seul parcours de `raw/`, le
  lecteur des tendances lui arrivant par `SourceKind.trend_reader` (« Tendances : un lecteur
  porté par la sorte, et un seul parcours de `raw/` », étape 3 du plan de refactorisation).
- **Wiki : le texte envoyé au modèle et reçu de lui, dans l'outil de suivi** (2026-10-12) : jamais
  (mesures seules), seulement en environnement d'essai, ou toujours (et inscrit au registre).
  Sabine tranchera à la comparaison des outils de restitution. La trace d'un outil comme Langfuse
  tire son intérêt de ce texte, qui contient les noms des auteurs. **Précisée le 2026-10-20** :
  l'outil est Grafana Cloud (« Squelette E1 E3 : cadrage du 20/10 », décision 4) ; la question reste
  ouverte jusqu'à #163. **Précisée le 2026-10-27** : les traces partent sans texte (#345) ; le
  contenu des appels au modèle viendra par une PR à part. **Tranchée pour l'API IA des fiches le
  2026-10-28** (« Traces : le contenu des appels au modèle, sous réglage (#347) ») ; reste ouverte
  pour le wiki.
- **Wiki : forme du contrat `.md` *cleansed*** (2026-10-12) : l'ETL écrit en SQLite ; ce que la
  partie LLM reçoit d'un papier Zotero (texte du PDF, métadonnées, surlignages) est à fixer avant
  le code.
- **Wiki : questions laissées par la session du 2026-10-12**, faute de temps : si la veille
  automatique nourrit le wiki ou seulement les dépôts de Sabine (Sabine : « on verra ») ; les
  données envoyées au fournisseur du modèle et à l'outil de suivi, à inscrire au registre (#157,
  #163, #170). Tranchées l'après-midi : l'API IA en local, l'accès qui expire, le vrai modèle
  pour la démonstration (entrées du 2026-10-12). **Révisée le 2026-10-15** : l'API IA est sur
  Azure Container Apps au 08/11, et la démonstration porte sur les fiches de veille
  (« POC du 25/10 », décisions 1 et 4).
- **Wiki : suivre OAuth 2 en entier, ou le schéma de jetons seul** (2026-10-12) : à voir au début
  de #160. **Révisée le 2026-10-15** : #160 vient en ligne au 08/11 ; la question reste ouverte
  jusque-là (« POC du 25/10 », décision 7). **Précisée le 2026-10-20** : #160 reste hors du
  squelette ; à revoir avec une interface web en ligne (« Squelette E1 E3 : cadrage du 20/10 »,
  décision 3). **Précisée le 2026-11-11** : l'interface web en ligne
  (#562) se connecte par l'authentification Entra de la plateforme Azure Container Apps ; K-B n'y
  code ni OAuth 2 ni jeton (« Site : le socle privé de `kb serve-web` »). La question reste posée
  pour l'accès aux API (#160).
