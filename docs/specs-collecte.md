# Spécifications de la collecte et de l'agrégation

Pour chacune des 7 sources de la v0 : la technologie, l'accès et l'authentification, les limites
de débit, les données personnelles, et ce qu'on suit. Puis le chemin du brut jusqu'au jeu d'items
final, et la justification de BigQuery. Les décisions et leur pourquoi sont dans le
[journal ADR](ADR/journal-decisions-projet.md) ; les listes suivies, dans [sources.md](sources.md).

Faits vérifiés le 2026-10-01, sources en fin de page.

## Règles communes

- **Un point de lancement** : `kb collect` lance toutes les sources ; une source en panne
  n'arrête pas les autres. Il affiche une ligne par source (`ok` ou `failed (<type d'erreur>)`),
  `zotero: skipped (KB_ZOTERO_DIR not set)` quand le dossier de Zotero n'est pas donné, et
  `gh_archive: skipped (GOOGLE_APPLICATION_CREDENTIALS not set)` sans la clé BigQuery.
  Code de sortie : **0** si tout a réussi ; **1** si une source a échoué, ou si
  `collection_state.json` n'a pas pu être écrit (disque plein, droits) ; **2** si la collecte n'a
  pas eu lieu (`KB_DATA_DIR` absent ou pas un dossier, état de collecte illisible). Quand l'état
  ne s'écrit pas, le brut est déjà écrit : `kb collect` journalise l'erreur avec le chemin du
  fichier et ajoute la ligne `collection_state: failed (<type d'erreur>)`. Les dates de
  dernière collecte n'avancent pas : la collecte suivante relit les mêmes fenêtres, et le brut en
  double est retiré à la transformation.
- **Brut intact** : chaque collecte écrit ce que la source a renvoyé dans
  `raw/automated_watch/<source>/<AAAA-MM-JJTHHMMSSZ>.<ext>`, une seule fois, jamais réécrit. Une
  source qui lit plusieurs pages (site scrapé) écrit chaque page telle que reçue dans
  `raw/automated_watch/<source>/<AAAA-MM-JJTHHMMSSZ>/<page>.<ext>` (décidé le 2026-10-04). Le filtre
  se fait à la lecture, sauf exception décidée (arXiv, ci-dessous). Ce que l'utilisatrice a
  choisi (Zotero) va dans `raw/selected_library/<source>/` (journal ADR, 2026-10-09).
- **Fréquence** : une collecte par jour, lancée à la main
  (`KB_DATA_DIR=<dossier> uv run --env-file .env kb collect`) ; l'automatisation viendra après.
  Une collecte manquée est rattrapée à la suivante, jusqu'à une limite propre à chaque source
  (code au 2026-10-05) :

  | Source | Rattrapage des jours manqués |
  |---|---|
  | tldr.tech | jour par jour, depuis le jour de la dernière collecte |
  | arXiv | depuis la dernière collecte moins 7 jours, 2 000 papiers au plus (au-delà, la source échoue) |
  | CISA KEV | complet : le catalogue entier est téléchargé |
  | GitHub, releases et alertes | 100 éléments au plus par dépôt ou par écosystème (au-delà, un avertissement) |
  | GitHub, dépôts les plus étoilés | aucun : un instantané par collecte, un jour manqué n'est pas récupérable |
  | Zotero | complet : chaque extrait contient toute la bibliothèque |
  | GH Archive | chaque fenêtre de 3 jours manquée depuis la dernière collecte, 15 au plus (les plus récentes), en une requête |

- **Incrémental** : la date de la dernière collecte réussie de chaque source est dans
  `collection_state.json`, à la racine du dossier de données et hors de `raw/` ; une source qui
  n'a rien de neuf n'écrit rien.
- **Entrées non fiables** : tout contenu collecté est une donnée, jamais une instruction. Chaque
  téléchargement a un délai, une taille maximale, et refuse une redirection hors du domaine
  attendu. Le `User-Agent` est `K-B (+https://github.com/SabineLaurent)` : le profil public de
  Sabine, le dépôt étant privé jusqu'au 25/10, puis public.
- **Secrets** : en variables d'environnement, chargées depuis le `.env` ignoré par git.
- **Données personnelles** : on ne garde que ce qui sert la veille ; aucun identifiant de
  personne n'est collecté s'il n'est pas nécessaire. Durées et purge : [registre des
  traitements](registre-traitements.md).

## Les sources

### API GitHub — service web

- **Technologie** : API REST, JSON, `urllib` de la bibliothèque standard.
- **Ce qu'on en tire** :
  - releases des dépôts suivis : `GET /repos/{owner}/{repo}/releases` ;
  - alertes de sécurité : `GET /advisories` (base publique des *security advisories*), relues
    par GitHub, pour les paquets publiés par les dépôts suivis ; la sécurité des projets de
    Sabine relève de Dependabot, pas de K-B ;
  - dépôts les plus étoilés : `GET /search/repositories`, tri par étoiles : le top 100 de tout
    GitHub, sans filtre par topic.
- **Accès** : jeton *fine-grained*, dépôts publics seulement, sans permission, dans
  `KB_GITHUB_TOKEN` ([jeton-github.md](jeton-github.md)).
- **Limites** : 5 000 requêtes par heure avec jeton (60 sans) ; la recherche a sa propre limite,
  30 requêtes par minute, et ne renvoie jamais plus de 1 000 résultats.
- **Données personnelles** : les releases et alertes portent le login de leur auteur, une donnée
  personnelle (pseudonyme rattaché à une personne), comme celui des personnes créditées dans une
  alerte (`credits`). Non nécessaire à la veille : il reste dans le
  brut mais n'entre pas dans les items (minimisation, RGPD art. 5.1.c).
- **Suivi** : 4 dépôts, liste et réserve dans [sources.md](sources.md).
- **État** : releases collectées (PR de #10) : un brut par dépôt, la première page de 100
  releases, lue avant d'être écrite, première collecte comprise (une page qui n'est pas une
  liste de releases valides fait échouer la source) ; un avertissement est journalisé si la page
  entière est plus récente que la dernière collecte (des releases ont pu manquer, il faudra lire les pages suivantes).
  Alertes collectées (PR de #11) : un brut par écosystème (`pip`, `npm`), relues par GitHub
  depuis la veille de la dernière collecte (date de revue, pas de publication : GitHub relit
  parfois une alerte des jours après l'avoir publiée), même avertissement si la page de 100 est
  pleine.
  Dépôts les plus étoilés collectés (PR de #11) : un instantané du top 100 à chaque collecte
  (un classement change toujours) ; entrées, sorties et montées se calculent à la lecture en
  comparant deux instantanés. Une réponse marquée `incomplete_results`, ou de moins de 100 dépôts, est
  refusée.
- **Filtre à la requête** (exception à la règle du brut intact, décidée le 2026-10-02) : les
  alertes sont demandées pour les seuls paquets suivis (`affects=`). Tout l'écosystème `npm`
  dépasse 100 alertes par semaine et obligerait à paginer.

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
  abs:"agent security") AND submittedDate:[<dernière collecte − 7 jours> TO <maintenant>]`.
- **Volume mesuré** (moyenne par 7 jours, septembre / avril 2026) : `cs.CR` sans filtre 276 / 199 ;
  `cs.CR` × `cs.AI` 78 / 70 ; avec les mots-clés, **22 / 19**.
- **Pièges de l'API** : avec `max_results=0`, le total renvoyé vaut toujours 1 (demander au moins
  un résultat pour le lire) ; les parenthèses
  imbriquées et `ANDNOT` combiné à d'autres opérateurs donnent des totaux faux. Sous charge,
  l'API répond `503` ou ne répond pas : la source échoue sans bloquer les autres, et sa date
  n'avance pas ; la collecte suivante redemande la même fenêtre.
- **Données personnelles** : noms des auteurs des papiers, publiés par eux ; gardés, car ils
  identifient le papier.
- **État** : collecte en place (PR de #12). Une requête par collecte, une page de 2 000 ; si l'API
  annonce plus de résultats que la page n'en contient, la collecte échoue et sa date n'avance pas.
  La fenêtre `submittedDate` part de **7 jours avant** la dernière collecte (la première collecte
  remonte au 01/05/2026, début de la formation : 488 papiers, 1,2 Mo, mesurés le 2026-10-02) : un papier n'est visible dans l'API qu'à son annonce, jusqu'à 3,5
  jours après sa soumission (jeudi 14 h → dimanche 20 h, heure de New York), plus les jours fériés
  ([Availability of submissions](https://info.arxiv.org/help/availability.html)). Partir de la
  dernière collecte perdrait ces papiers pour toujours (le bug de watermark de brief09). Chaque
  brut recouvre donc le précédent ; la base dédoublonne par identifiant (étape 4). Une entrée mal formée
  ne fait pas échouer la collecte (sa fenêtre la garderait pour toujours) : elle entre dans le
  brut, et sa lecture la rejette et la journalise. Une entrée d'erreur de l'API fait, elle,
  échouer la collecte. Limites assumées : la révision (`v2`) d'un papier soumis avant la fenêtre
  n'est pas collectée, ni un papier retenu en modération plus de 7 jours.

### Catalogue CISA KEV — fichier

- **Technologie** : fichier CSV téléchargé en HTTPS
  (`https://www.cisa.gov/sites/default/files/csv/known_exploited_vulnerabilities.csv`).
- **Ce qu'on en tire** : les vulnérabilités activement exploitées ajoutées depuis la dernière
  collecte (`dateAdded`), sélectionnées à la lecture.
- **Accès** : sans authentification. Requête conditionnelle `If-Modified-Since` : une réponse 304
  n'écrit rien.
- **Limites** : pas de quota publié ; une requête par collecte. Catalogue d'environ 1 Mo, refusé
  au-delà de 10 Mo, et refusé s'il est servi hors de `https://www.cisa.gov/`. Le catalogue est
  lu avant d'être écrit : une réponse qui n'en est pas un (page HTML, colonnes manquantes, ligne
  invalide) fait échouer la source, sans brut écrit ni date avancée.
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
  `https://tldr.tech/ai/2026-09-30` répond 200). La collecte garde chaque page brute ; la lecture des articles se fait à la
  transformation.
- **Ce qu'on en tire** : un item par article de chaque édition suivie : titre, lien, résumé.
- **Jours sans édition** : un jour redirigé vers la page d'accueil de l'édition,
  `https://tldr.tech/<édition>`, n'a pas de page d'édition (observé pour le 2026-10-03 et le
  2026-10-04) : il est journalisé avec l'adresse de redirection et sauté. Toute autre
  redirection ou erreur HTTP fait échouer la source.
- **Journal** : chaque jour donne une ligne, avec l'édition, le jour et ce qui a été observé :
  page gardée (taille en octets), redirection vers la page d'accueil (adresse d'arrivée), ou
  erreur (message reçu et URL demandée) ; une collecte sans aucune page le dit aussi.
  `kb collect` affiche les lignes de niveau INFO et au-dessus.
- **Fréquence** : voir les règles communes.
  Chaque collecte lit chaque jour depuis le jour de la dernière collecte, relu car son édition a
  pu paraître après elle, jusqu'à aujourd'hui (UTC) ; la première lit les 7 jours précédents et
  aujourd'hui. La page relue est en double dans deux collectes : le doublon est retiré à la
  transformation.
- **Accès** : sans authentification. Le `robots.txt` autorise tout, sauf les pages d'abonnement
  et de compte (`/subscribed`, `/manage`, `/info`…), qu'on ne lit pas.
- **Limites** : pas de quota publié ; on s'impose une page à la fois, avec une pause entre deux
  pages. Les liens portent des paramètres de suivi `utm_*` et certaines entrées sont
  sponsorisées : à traiter à la lecture.
- **Données personnelles** : aucune (voir le registre des traitements).
- **Suivi** : éditions **ai**, **infosec** et **dev** (ai le 2026-10-01, les deux autres le
  2026-10-04), une source par édition (`tldr_ai`…), dans `TRACKED_EDITIONS` de
  `k_b/sources/tldr.py` (neuf candidates dans [sources-detaillees.md](sources-detaillees.md)).

### Zotero — base de données

- **Technologie** : base SQLite `zotero.sqlite`, dans le dossier de données de Zotero, lue par
  une requête SQL (`src/k_b/sources/zotero.py`). Zotero verrouille sa base quand il tourne, et
  ses dernières écritures sont dans `zotero.sqlite-wal` : K-B copie les deux fichiers dans un
  dossier temporaire, vérifie la copie (`PRAGMA integrity_check`), l'ouvre en lecture seule,
  lance la requête, puis supprime la copie, après un succès, une erreur ou un Ctrl-C. Un
  processus tué laisse sa copie dans le dossier temporaire du système (`kb-zotero-…`) : chaque
  extraction retire d'abord celles de l'utilisatrice. Deux `kb collect` lancés en même temps
  peuvent se retirer leur copie l'un à l'autre : K-B n'a pas de verrou. L'original n'est jamais
  ouvert par SQLite.
- **Ce qu'on en tire** : chaque document de premier niveau de la bibliothèque personnelle, hors
  corbeille : clé Zotero, type, titre, date, date d'ajout, URL, référence arXiv (`archiveID`),
  auteurs dans leur ordre, étiquettes avec leur type (0 : posée à la main ; 1 : automatique),
  clé et chemin de chaque PDF rangé dans le stockage de Zotero (`storage:<fichier>`), et les
  surlignages de ces PDF (annotations de type 1 : clé, texte, commentaire, page, date d'ajout),
  dans l'ordre du document. Ne sont pas lus : les notes, les résumés, les autres types
  d'annotation, les PDF liés hors du stockage de Zotero, les surlignages d'un fichier qui n'est
  pas un PDF, un PDF enregistré sans document parent et ses surlignages, les bibliothèques de
  groupe. Le titre et la date sont lus dans les champs `title` et `date` de Zotero : un type de
  document qui les range sous un autre champ (décision de justice, mail, brevet) sort avec un
  titre ou une date vide.
- **Accès** : fichier local. Le dossier de données de Zotero est donné par la variable
  d'environnement `KB_ZOTERO_DIR`, en chemin complet (K-B ne développe pas un `~`). Absente ou
  vide : Zotero est sauté, `kb collect` l'affiche, et son code de sortie ne change pas.
- **Limites** : aucune limite de débit. Pas de taille maximale sur la base copiée, à la
  différence des téléchargements (règles communes) : un disque plein arrête la copie, et le
  dossier temporaire est supprimé.
- **Brut** : le résultat de la requête, en JSON, dans
  `raw/selected_library/zotero/<AAAA-MM-JJTHHMMSSZ>.json` (journal ADR, 2026-10-09), écrit
  seulement si `zotero.sqlite` ou son `-wal` a été modifié depuis la dernière collecte. Les
  valeurs sont celles de Zotero, sans conversion (dates `AAAA-MM-JJ HH:MM:SS` en UTC). Zotero
  ouvert écrit dans son `-wal` sans que la bibliothèque change : un extrait peut être identique
  au précédent. `kb import` ne lit pas encore ces extraits : rien de Zotero n'entre dans la base.
- **En cas de panne :** la source échoue par un état nommé, n'écrit rien, et sa date de dernière
  collecte reste ; la collecte suivante recommence. Les états :
  `ZoteroCopyInconsistentError` (le contrôle d'intégrité refuse la copie),
  `ZoteroChangedDuringCopyError` (un des deux fichiers a changé pendant la copie),
  `ZoteroQueryFailedError` (la requête échoue ; le message nomme la table ou la colonne
  absente, sinon le type de l'erreur et le nom que SQLite lui donne, jamais un contenu de la
  bibliothèque), `FileNotFoundError` (pas de `zotero.sqlite` dans le dossier).
- **Données personnelles** : les auteurs des papiers (publics), et ce que l'utilisatrice a
  enregistré et surligné. Le journal ne cite ni auteur, ni titre, ni texte surligné : deux
  nombres seulement. Le brut vit hors du dépôt de code et n'est jamais publié
  ([registre des traitements](registre-traitements.md), fiche 2).
- **Prérequis** : Zotero installé.

### GH Archive sur BigQuery — big data

- **Technologie** : SQL BigQuery sur les tables publiques `githubarchive.day.AAAAMMJJ` (un
  événement GitHub public par ligne), client `google-cloud-bigquery`.
- **Ce qu'on en tire** : pour chaque fenêtre de 3 jours UTC complets (J-3 à J-1), les étoiles
  (`WatchEvent`) et les forks (`ForkEvent`) gagnés par dépôt (`repo.id`, dernier nom vu) ; les 30
  premiers par étoiles et les 30 premiers par forks, réunis (60 dépôts au plus par fenêtre). On
  compte des événements, pas des personnes. Un événement sans `repo.id` ou sans `repo.name` est
  écarté (14 `ForkEvent` sans dépôt le 2026-10-10). Le brut,
  `raw/automated_watch/gh_archive/<collecte>.json`, donne les fenêtres couvertes et les lignes ; il
  est refusé entier si une ligne est invalide (un classement, règle 1). Risque accepté (Sabine,
  2026-10-11) : une ligne invalide revient avec sa fenêtre à chaque collecte, et la source échoue
  jusqu'à ce que cette fenêtre sorte du rattrapage (15 jours au plus) ; il est faible, les valeurs
  vides étant écartées par la requête et la règle du nom (`owner/name`, sans espace) étant large.
  Requête : `TRENDS_QUERY`, `src/k_b/sources/gh_archive.py`. Pas encore lu vers la base (TENDANCE,
  issue de suite).
- **Rattrapage** : les fenêtres manquées depuis la dernière collecte, 15 au plus (un dépôt qui a
  monté il y a plus de deux semaines n'apporte plus grand-chose à la veille), en une seule
  requête qui lit chaque jour une fois. La table de la veille doit être close (modifiée après
  minuit UTC ; constaté le 2026-10-11 : sa dernière heure arrive vers 00:08 UTC) ; sinon la source
  échoue (`DayTableNotClosedError`) et la collecte suivante reprend. Lancer `kb collect` après
  00:10 UTC (02:10 à Paris en été, 01:10 en hiver) : lancé chaque jour plus tôt, GH Archive
  échouerait chaque jour.
- **Limites acceptées (Sabine, 2026-10-11)** : une table de jour **absente** au milieu des jours
  lus (panne de GH Archive) est sautée sans bruit par le joker `day.20*`, et ses fenêtres sont
  comptées sur deux jours au lieu de trois ; des **heures manquantes ou appauvries** dans une
  table présente ne se voient pas non plus. Ni l'une ni l'autre ne laisse de trace dans le brut
  ou le journal.
- **Fait constaté le 2026-10-11** : depuis le 2026-10-06 (baisse dès 17:00 UTC, franche à 18:00,
  complète à 19:00), les tables BigQuery de GH Archive ont des heures appauvries (environ dix fois
  moins d'événements jusqu'au 08/10 à 02:59,
  puis environ moitié moins, avec une nouvelle chute du 09/10 15:00 au 10/10 00:59), alors que
  les fichiers source de chaque heure existent ; détail et limite de la conclusion dans
  [bigquery.md](bigquery.md#anomalie-constatée--les-tables-de-gh-archive-incomplètes-depuis-le-2026-10-06).
  La collecte réelle du 2026-10-11 (fenêtre du 08 au 10/10, 48 dépôts) a été faite sur ces
  données partielles : ses comptes sont trop bas, son classement possiblement faux. Les contrôles
  de la source (table close, résultat valide) sont passés.
- **Accès** : compte de service `k-b-collecte`, seul rôle Utilisateur de job BigQuery, clé
  désignée par `GOOGLE_APPLICATION_CREDENTIALS` ([bigquery.md](bigquery.md)).
- **Limites** : bac à sable sans facturation : 1 Tio lu par mois, 10 Gio de stockage, tables
  expirées après 60 jours. Une requête au-delà est refusée, jamais facturée. Chaque requête passe
  d'abord par un `dry_run`, puis s'exécute avec `maximum_bytes_billed` au plafond, qui grandit
  avec les fenêtres : 650 Mo par fenêtre, 2 Go au plus. Quand la borne de 2 Go s'applique (dès
  4 fenêtres), la fenêtre la plus ancienne est retirée et un nouveau `dry_run` est fait ; sinon,
  ou avec un `dry_run` sans volume, la source échoue (`DryRunOverLimitError`,
  `DryRunVolumeUnknownError`). Délai : 300 s. Mesures et calcul des bornes, datés, avec leurs
  commandes : [bigquery.md](bigquery.md#mesures-du-2026-10-11). Une
  requête sur des tables à joker (`day.20*`) n'est pas mise en cache : chaque exécution est
  facturée au quota (constaté le 2026-10-11).
- **Données personnelles** : chaque événement porte le login de son auteur (`actor`). La requête
  ne le sélectionne pas : elle ne renvoie que des comptes par dépôt. Le nom du dépôt
  (`owner/repo`) porte le login de son propriétaire quand c'est une personne : gardé, il identifie
  le dépôt ([registre](registre-traitements.md)). Un message d'erreur n'en cite que la longueur.
- **Prérequis** : la clé du compte de service ; sans `GOOGLE_APPLICATION_CREDENTIALS`, la source
  est sautée.

## Du brut au jeu d'items

1. **Collecte** : chaque source écrit son brut dans `raw/automated_watch/<source>/` (règles communes).
2. **Lecture** : un lecteur par sorte de source transforme le brut en items validés par un modèle
   Pydantic. Le lecteur est retrouvé par le nom du dossier brut (`github_releases_<dépôt>/` est
   lu par celui des releases), que la source soit encore suivie ou non. Les sortes sont déclarées
   une seule fois, dans `source_kinds.py`. Un dossier qui n'appartient à aucune sorte est
   journalisé et sauté. Les items ont les mêmes champs : source, identifiant dans la source,
   titre, URL, auteurs (sauf GitHub), date de publication et date de révision (arXiv), date d'ajout (Clipper, Zotero),
   contenu ou résumé, date de collecte, chemin du brut d'origine. Une date absente reste vide. Toutes les dates sont en UTC, avec fuseau. Une ligne
   illisible est rejetée et journalisée, pas devinée.
3. **Normalisation** des items lus (`normalize_item`, `src/k_b/merge.py`) :
   - dates ramenées en UTC ;
   - URL normalisées : les paramètres `utm_*` sont retirés, les autres restent tels quels et
     dans leur ordre.

   `brief09_assistant-veille-tech` (relu le 2026-10-01) a servi d'indication, pas de modèle : il
   ne fait pas autorité. On y retrouve un modèle d'article commun et la date de révision arXiv. À
   l'inverse, brief09 ne dédoublonne que sur l'URL exacte, ignore les révisions (première version
   gardée), date la collecte sans fuseau et retire les doublons sans trace. Laissé de côté : les
   étiquettes posées par un LLM, hors de la v0.
4. **Stockage** des items dans la base : SGBD, modèles et ce que chaque source met dans l'item,
   dans [stockage.md](stockage.md). `kb import` (`run_import`, `src/k_b/cli.py`) n'importe que
   les fichiers bruts pas encore importés (#106) : il lit le registre de la base
   (`read_imported_paths`, `src/k_b/import_items.py`), puis les fichiers qui n'y sont pas
   (`read_raw_items`, `src/k_b/raw_items.py`), puis écrit la base (`import_items`). Il affiche
   le nombre de fichiers bruts lus (`raw files read`).

   - **Registre** : la table `raw_data`, une ligne par fichier lu, ou par page d'un dossier de
     pages. Un fichier lu y entre, même s'il n'a donné aucun item, et même si certaines de ses
     entrées sont rejetées : celles-ci ne seront relues que par une reconstruction. Un fichier
     sauté faute de lecteur n'y entre pas. **Un fichier illisible n'y entre pas** (décision de
     Sabine du 2026-10-12) : il est relu et rejeté à chaque import, et l'import qui suit la
     correction du lecteur ou du brut le lit, sans reconstruction. Une collecte mal nommée
     (dossier ou fichier dont le nom n'est pas une date) n'a pas de date de collecte : elle
     n'entre pas non plus au registre, et elle est rejetée à chaque import, sans compter dans
     `raw files read`.
   - **Une transaction** : chaque fichier lu est inscrit au registre, puis ses items sont
     écrits ; le journal est écrit avant la validation (`COMMIT`). Une erreur dans la base, ou
     un journal qui ne s'écrit pas, n'écrit rien : aucun fichier n'est inscrit, tous seront
     relus. Si la validation échoue, ou sur une interruption (Ctrl-C), le journal écrit est
     supprimé. Pourquoi : un fichier
     inscrit n'est plus relu, un journal perdu après la validation perdrait pour toujours la
     trace de ses rejets et de ses écarts (décision de Sabine du 2026-10-12, qui revient sur le
     journal écrit après la base de #105).
     **Limites** (constats de revue, acceptées par Sabine le 2026-10-12) : un `SIGKILL` entre
     l'écriture du journal et la validation laisse le journal d'un import annulé ; une
     interruption qui arrive juste après la validation, avant la fin du bloc qui la protège,
     supprime le journal d'un import validé (une fenêtre de quelques instructions Python).
   - **Reconstruction complète** : supprimer la base, `kb create-db`, puis `kb import`, qui
     relit tout `raw/`. Pas d'option : une base vide n'a rien au registre.

   **La base dédoublonne** (#105, décisions de Sabine du 2026-10-12). Les items arrivent dans
   l'ordre des collectes. Un item déjà en base est reconnu par la clé naturelle de son sous-type
   ou de son référentiel (`release_id`, `ghsa_id`, `cve_id`, `arxiv_id`) ; ce qu'il en advient
   dépend de la **nature** de sa source. La règle de chaque nature est une clause SQL de
   l'écrivain de sa sorte d'item, et nulle part ailleurs :

   | Nature | Sources | Item déjà vu | SQL | Règle au journal |
   |---|---|---|---|---|
   | flux de nouveautés | releases, alertes GitHub ; TLDR quand ses articles seront lus (#57) | inchangé : la première version vue est gardée | `INSERT INTO item … SELECT … WHERE NOT EXISTS (sous-type de même clé) RETURNING id` | `already_seen` |
   | catalogue d'état | CISA KEV | remplacé si son fichier est collecté après le dernier catalogue de la source déjà importé et que son contenu diffère ; `revised_at` prend la date de cette collecte | `ON CONFLICT (cve_id) DO UPDATE … WHERE` (collecte plus récente et contenu différent) `RETURNING id` | `unchanged`, `no_newer_version` |
   | flux avec révisions | arXiv | remplacé si sa révision (`updated`) est plus récente | `ON CONFLICT (arxiv_id) DO UPDATE … WHERE excluded.revised_at > publication.revised_at RETURNING id` | `revision_not_newer` |

   - Le flux de nouveautés n'a pas d'`ON CONFLICT` : le sous-type exige un item déjà créé, et
     ITEM n'a pas de clé naturelle. L'item n'est donc créé que si le sous-type est absent ; la
     contrainte `UNIQUE` du sous-type reste le filet.
   - **Catalogue d'état** : un catalogue est complet (CISA ne donne que son catalogue du jour,
     qui cumule tout), et seule la collecte la plus récente compte. Une ligne est comparée au
     dernier catalogue de la même source déjà importé, à la seconde : deux catalogues du même
     jour, à 9 h et à 18 h, celui de 18 h l'emporte. Le fichier en cours n'en est pas, sauf s'il
     porte déjà la version en base (un rejeu, que le registre empêche depuis #106 ; gardé pour
     une base d'avant #106 ou deux imports simultanés). Un fichier plus ancien est un fichier
     importé en retard : il ne change pas une ligne connue, même si son contenu diffère. Une
     ligne connue rattache son item au fichier qui a apporté sa version actuelle. Le CVE qu'une
     alerte a déjà créé, sans colonnes KEV, prend ses colonnes à sa première ligne CISA, sans
     `revised_at`.
   - **Ligne retirée du catalogue** (#106, « Le MCD de Sabine »,
     [clarification du modèle](2026-10-07-clarification-modele.md)) : un catalogue collecté
     après le dernier catalogue importé marque retirée chaque ligne connue (item KEV) qui n'y
     figure pas, écrite ou écartée : `withdrawn_at` prend la date de sa collecte, et la
     première absence garde sa date. L'item garde le fichier de sa version : une absence n'est
     pas une version. Si la ligne réapparaît dans un catalogue plus récent, elle est réécrite
     même à contenu identique : `withdrawn_at` est vidé, `revised_at` daté, l'item pointe vers
     ce fichier. `kb import` affiche le nombre de lignes retirées
     (`vulnerabilities withdrawn`).
     - **Écart au MCD** (décision de Sabine du 2026-10-12) : un catalogue dont une entrée est
       rejetée, ou qui ne donne aucun item, ne retire rien. Une ligne rejetée est présente, pas
       absente. Une ligne absente d'un tel catalogue est donc retirée au catalogue propre
       suivant, et datée de lui, pas du premier catalogue qui a constaté son absence.
     - **Catalogue importé en retard** (plus ancien que le dernier importé, ou au même
       instant) : il ne retire rien et ne fait rien réapparaître. Un CVE qu'il est seul à
       apporter, ou dont il remplit les colonnes KEV (CVE créé par une alerte), est écrit
       **retiré**, à la date du dernier catalogue importé, qui ne le liste pas (décision de
       Sabine du 2026-10-12 : une base reconstruite le trouve retiré elle aussi).
     - **Limite** : une base reconstruite, qui importe tous les fichiers dans l'ordre des
       collectes, a le même contenu et les mêmes lignes retirées que la base tenue au fil des
       imports. Après un catalogue importé en retard, elle peut en différer par les dates
       (`revised_at`, `withdrawn_at`) et par le fichier rattaché à l'item. Exception (constat
       de revue, limite acceptée par Sabine le 2026-10-12) : si la ligne d'un CVE est rejetée
       dans le dernier catalogue importé, et qu'un catalogue en retard apporte ce CVE, il est
       écrit retiré alors que le dernier catalogue le liste ; une base reconstruite le trouve
       actif. De même, un catalogue dont toutes les lignes sont rejetées est inscrit au
       registre et compte comme le dernier catalogue importé. Le cas demande deux anomalies à
       la fois ; une reconstruction le règle une fois le rejet corrigé.
   - **Sources sans import** (`zotero`, `gh_archive`, `clipper`, classement des plus étoilés) :
     leur nature est décidée par leur issue d'import (#138, #142, #14). Zotero, extrait complet
     lui aussi, entrera peut-être dans le catalogue d'état : #138 le dira.
   - Une même CVE dans deux sources (une entrée CISA et une alerte GitHub), ou citée par deux
     alertes, n'est **pas** un doublon : chaque alerte est gardée, et toutes pointent vers la
     même vulnérabilité (`vulnerability.cve_id` unique).
   - **Limite** : la base ne trouve que le doublon exact, le même identifiant dans sa source (un
     rejeu de l'ETL, des collectes qui se chevauchent). Le quasi-doublon (même contenu, autre
     métadonnée : autre URL, autre clé Zotero) est laissé à #57 et #138, qui soumettront une
     empreinte de contenu.
   - **Journal** : `<KB_DATA_DIR>/import-log-<AAAA-MM-JJTHHMMSSZ>.jsonl`, un fichier par
     import, nommé par sa seconde au format des noms de bruts, jamais réécrit : si le journal
     de cette seconde existe déjà, l'import s'arrête sans rien écrire (code de sortie 2). Une
     ligne JSON par rejet (`raw_file_path`, `reason`), puis par item écarté (`rule`,
     `source_code`, `source_item_id`, `raw_file_path` et la date comparée). Chaque ligne porte
     l'instant de son import, `imported_at`, en ISO 8601 UTC à la seconde, au format des dates
     de la base (`2026-10-12T15:49:03Z`, décision de Sabine du 2026-10-12, d'après le
     [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
     de l'OWASP). La date comparée est dans un champ qui dit d'où elle vient :

     | Règle | Constat | Champ | Date |
     |---|---|---|---|
     | `already_seen` | le sous-type est déjà en base | `compared_with_collected_at` | collecte de la version gardée |
     | `unchanged` | fichier plus récent que le dernier catalogue importé, contenu identique | `compared_with_collected_at` | collecte de la version gardée, la seule comparée au contenu |
     | `no_newer_version` | fichier collecté avant le dernier catalogue importé, ou au même instant | `compared_with_collected_at` | collecte de ce dernier catalogue |
     | `revision_not_newer` | révision arXiv plus ancienne ou égale | `compared_with_revised_at` | révision arXiv de la version gardée |

   - **Rejouable** : un second import sans nouveau brut ne lit aucun fichier (sauf un fichier
     illisible ou une collecte mal nommée) et ne change pas la base ; un item déjà en base garde
     son `item_id`, que l'API exposera.
   - Un nom répété dans les auteurs d'un item n'est lié qu'une fois, à sa première position : la
     base lie un auteur à un item une seule fois.
   - Un auteur qui n'a plus d'item (une révision arXiv a changé ses auteurs) est supprimé dans
     la même transaction : un nom sans usage n'est pas gardé.

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
