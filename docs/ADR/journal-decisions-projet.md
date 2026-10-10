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
  `STRICT` et `PRAGMA`). — PR de #7
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
  demandés. Limite : durée de conservation des fichiers non décidée.

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
  uniquement »).

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
  la machine ; c'est le brut qu'on sauvegarde. Options écartées : `~/.local/share/k-b`
  (convention XDG, moins connue sur Mac), `~/Library/Application Support/K-B` (pensé pour les
  applications graphiques), `~/K-B-data` (exemple du 2026-09-29, un dossier visible de plus).
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
  jour où la base gardera des données sans brut. **Contredit** l'ADR du 2026-10-05 (PR de #82),
  qui écartait la reconstruction parce qu'elle renumérote `item_id`, que l'API exposera : la
  stabilité de `item_id` est ouverte (ci-dessous).

### Interface

- **Une API REST locale (sur `localhost`, à côté de la commande `kb`) fait partie d'E1 ; la page
  web et le déploiement relèvent d'un autre livrable.** Décision de Sabine. Pourquoi : l'API est
  attendue dans E1 ; une commande n'exclut pas une API, et une API locale ne revient pas sur la
  décision « local » du 2026-10-08. Conséquence : la
  stabilité de `item_id` face à une base jetable reste à trancher (question ouverte, ci-dessous).

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
  2026-09-29 (« et fiches de veille ») et sur le calendrier des « Deux wikis ».
- **Les surlignages Zotero sont gardés en base et affichés avec leur papier dans `kb search`, sans
  être cherchables par leurs mots.** Décision de Sabine. Options écartées : les rendre
  cherchables (un index de plus) ; ne pas les collecter. Remplace le bloc « Mes surlignages » des
  fiches (2026-09-29, 2026-10-02), reportées.
- **Recherche plein texte par FTS5, triée par pertinence BM25 quand il y a des mots, par date
  sinon ; elle couvre le titre et le résumé des items, et le texte complet des clips et des
  notes déposées.** Décision de Sabine. Pourquoi : aucune dépendance ; un papier qui cite le
  terme une fois ne doit pas valoir un papier consacré au sujet. Options écartées : tri par date
  seul ; une option `--sort relevance` ; titre seul pour la bibliothèque. Limites : `porter` ne
  ramène à leur racine que les mots anglais ; FTS5 est propre à SQLite.

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
  qui écrit), par-dessus le même `schema.sql`.
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
- **Le titre, le résumé et les dates restent dans chaque sous-type (article de newsletter,
  release, alerte) ou référentiel (publication, vulnérabilité) ; ITEM reste minimal ; les listes
  qui mélangent les sortes (`kb search`, « quoi de neuf », l'API) passent par une seule requête
  SQL imbriquée en `UNION ALL`, une branche par sorte, à paramètres liés.** Décision de Sabine,
  à revoir à l'usage. Pourquoi, selon elle : les informations propres à une publication, une
  vulnérabilité ou un article sont portées par sa table ; une requête SQL se lit et se teste, une
  vue est un concept qu'elle ne maîtrise pas encore ; une requête complexe s'écrit en SQL. La
  requête est écrite une fois et partagée. Un test vérifie que chaque `kind` a sa branche ; la
  table FTS5 est remplie à l'import. Options écartées : recopier titre, résumé et date dans ITEM (doublon) ; une
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
  2 000), `advisory` (`ghsa_id` 19, `summary` 1 000, `url` 2 000). Elles vivent dans `items.py`,
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
  limites de GitHub pour `tag_name`, `name` et le résumé d'une alerte ne sont pas vérifiées ;
  125 000 vient d'un message d'erreur de l'API GitHub rapporté par des tiers, 1 920 pour un
  résumé arXiv de la page d'aide d'arXiv ; les autres dépôts suivis et les alertes `npm` ne sont
  pas dans la collecte mesurée ; `length()` de SQLite s'arrête au premier caractère NUL.
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
  Limite assumée : la longueur d'un nom **déroge** à « tenue deux fois » (2026-10-08).
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
  les secrets et le dossier de données.

## Décisions encore ouvertes

- **Nommage des tables et des colonnes.** Gardé tel quel le 2026-10-02 ; Sabine demandera les
  renommages à l'usage, une fois les schémas sous les yeux.
- **Règle de « quoi de neuf cette semaine »** (date de publication, d'ajout ou de collecte) : à
  décider dans #21.
- **Durées de conservation et fréquence de la purge** : provisoirement 2 ans après la collecte
  (base et brut), purge à chaque collecte (une par jour) ; la durée, par mode d'acquisition,
  sera dans `config.py` (2026-10-10), à revoir. Sabine n'a pas tranché le 2026-10-02 ; à confirmer
  quand #20 code la purge. La purge des tables nouvelles (référentiels, TENDANCE, bibliothèque)
  n'est pas définie (relecture du 2026-10-09).
- **Collecte automatisée et sa fréquence** : aujourd'hui lancée à la main, une fois par jour.
  Le lancement automatique et sa fréquence seront définis plus tard (Sabine, 2026-10-05).
- **Liste d'exclusion** des personnes qui demandent l'effacement, pour qu'une collecte ou une
  reconstruction ne les réintroduise pas : proposée dans le registre, à concevoir dans #20.
  Indispensable avec une base reconstruite, en développement (2026-10-10).
- **Questions laissées par la relecture indépendante du 2026-10-09**, à décider par Sabine :
  le modèle de la bibliothèque (DOCUMENT ou CONTENU, une publication décrite par plusieurs
  items, un article Zotero hors arXiv) ; les versions d'un clip annoté ; si `kb search --kind vulnerability` ramène aussi les
  alertes GitHub (`kind` = `advisory`).
- **Transfert hors UE par les agents** : un agent qui lit les items par l'API envoie leur contenu
  au fournisseur du modèle (États-Unis). Cadre juridique non vérifié.
- **Motif d'un rejet pour longueur** : le critère de l'issue sur le motif des rejets (#92) ne
  garde que le champ et le type d'erreur, alors que la décision du 2026-10-08 demande la longueur
  reçue et le maximum. À accorder par Sabine avant de coder #92 (2026-10-10).
- **Tables `repository` et `star_gain`** : restées dans `schema.sql` après la réécriture, sans
  écrivain ; la clarification les remplace par TENDANCE. Quand les retirer n'est pas décidé
  (2026-10-10).
