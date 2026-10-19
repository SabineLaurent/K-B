# Spécifications de la collecte et de l'agrégation

Pour chacune des 9 sources de la v0, de 7 fournisseurs : la technologie, l'accès et
l'authentification, les limites de débit, les données personnelles, ce qu'on suit, et ce qui se
passe en cas de panne. Puis le chemin du brut jusqu'au jeu d'items final, et la justification de
BigQuery. Les décisions et leur pourquoi sont dans le
[journal ADR](ADR/journal-decisions-projet.md) ; les listes suivies, dans [sources.md](sources.md).

**Langage** : K-B est écrit en Python 3.13 (`.python-version` ; `requires-python = ">=3.13"` dans
`pyproject.toml`), avec ses dépendances gérées par `uv`. Chaque source nomme ci-dessous, dans sa
puce « Technologie », la bibliothèque qui la lit.

Faits vérifiés le 2026-10-01, sources en fin de page ; revus sur le code le 2026-10-18 (#64).

## Règles communes

- **Un point de lancement** : `kb collect` lance toutes les sources, ou celles de
  `KB_COLLECT_ONLY` (ci-dessous) ; une source en panne n'arrête pas les autres. Au lancement,
  avant la première source et avant de lire l'état de collecte, il journalise une fois les
  sources qu'il va collecter (`INFO k_b.cli: sources to collect: cisa_kev, …`), chacune sous le
  nom de sa ligne de fin. À la fin, il affiche une ligne par source (`ok` ou
  `failed (<type d'erreur>)`),
  `zotero: skipped (KB_ZOTERO_DIR not set)` quand le dossier de Zotero n'est pas donné,
  `clipping: skipped (KB_VAULT_DIR not set)` quand le coffre Obsidian ne l'est pas, et
  `gh_archive: skipped (GOOGLE_APPLICATION_CREDENTIALS not set)` sans la clé BigQuery. Quand
  l'état ne s'écrit pas, le brut est déjà écrit : `kb collect` journalise l'erreur avec le chemin
  du fichier et ajoute la ligne `collection_state: failed (<type d'erreur>)`. Les dates de
  dernière collecte n'avancent pas : la collecte suivante relit les mêmes fenêtres, et l'import
  écarte les items déjà en base (étape 4 de « Du brut au jeu d'items »).
- **Codes de sortie** de `kb collect`, nommés par `ExitCode` (`src/k_b/commands/exit_codes.py`)
  et listés par `kb --help` :

  | Code | Nom | Quand |
  |---|---|---|
  | **0** | `SUCCEEDED` | chaque source lancée a réussi ; une source sans rien de neuf réussit (`ok`, rien d'écrit, sa date avance) |
  | **1** | `FAILED` | aucune source lancée n'a réussi ; ou `collection_state.json` n'a pas pu être écrit (disque plein, droits), quel que soit le sort des sources ; ou une exception que `kb` ne traite pas, journalisée avec sa trace |
  | **2** | `NOT_STARTED` | rien n'a été collecté, ni brut ni état écrit : `KB_DATA_DIR` absente ou vide ; `KB_DATA_DIR` qui n'est pas un dossier existant ; `KB_LOG_TO_FILE` qui n'est ni `true` ni `false` ; fichier de journal qui ne s'ouvre pas ; `collection_state.json` illisible ou invalide (pas du JSON, pas un objet, une date sans fuseau) ; `KB_COLLECT_ONLY` refusée (ci-dessous) ; commande absente ou inconnue, refusée par `argparse` (son message d'usage, sur la sortie d'erreur seulement : le journal n'est pas encore ouvert) |
  | **4** | `PARTIAL_FAILURE` | au moins une source a réussi, au moins une a échoué, et l'état est écrit : les sources réussies sont acquises, les autres repartent de leur date à la collecte suivante |
  | **143** | `STOPPED_BY_SIGTERM` | arrêt par SIGTERM (`docker stop`) : le brut déjà écrit reste ; si l'arrêt vient avant l'écriture de l'état, l'état n'est pas écrit et la collecte suivante relit les mêmes fenêtres ; s'il vient après (pendant l'affichage des lignes), l'état est écrit et le code reste 143 |

  Le code 3 (`SERVER_NOT_STARTED`) est propre à `kb serve`. Ctrl-C (SIGINT) n'est pas traité par
  `kb` : Python affiche sa trace hors du journal daté, l'état n'est pas écrit si l'arrêt vient
  avant lui, et le code de sortie, donné par le shell, est 130 ; aucun code nommé ne le décrit.
- **Choisir les sources** (#201) : `KB_COLLECT_ONLY`, posée, ne lance que les sources nommées,
  séparées par des virgules (`KB_COLLECT_ONLY=zotero,clipping`, la collecte du Mac au POC ; les
  conteneurs collectent le reste). Un nom est le dossier d'une source sous `raw/` (`FOLDER_PREFIX`) :
  `cisa_kev`, `github_releases`, `github_advisories`, `github_most_starred`, `arxiv_cscr_x_csai`,
  `tldr`, `zotero`, `clipping`, `gh_archive` ; `tldr` lance toutes ses éditions, `github_releases`
  tous ses dépôts. Les espaces autour d'un nom sont retirés, puis le nom est mis en minuscules
  (`Zotero` est `zotero`, décision de Sabine du 2026-10-18) ; un nom refusé est cité tel qu'il est
  écrit, sans les espaces autour. Une source écartée affiche une seule ligne,
  `<dossier>: skipped (not in KB_COLLECT_ONLY)`, au nom de son dossier (une source lancée affiche
  le nom de la source, `tldr_ai`), et sa date de dernière collecte reste. Code de sortie **2**,
  sans rien collecter (ni brut ni état écrit ; le refus va au journal), quand la valeur est vide,
  qu'une entrée est vide, qu'un nom n'est pas un dossier de source (le nom est cité, tronqué et
  échappé), ou qu'une source choisie n'a pas sa variable (`zotero` sans `KB_ZOTERO_DIR`, `clipping`
  sans `KB_VAULT_DIR`, `gh_archive` sans `GOOGLE_APPLICATION_CREDENTIALS`) : un choix qui ne peut
  pas tourner est refusé (décision de Sabine du 2026-10-18). Sans `KB_COLLECT_ONLY`, pas de
  filtre : toutes les sources sont lancées, et une source sans sa variable est sautée sans changer
  le code de sortie (Zotero et clips ci-dessous).
- **Brut intact** : chaque collecte écrit ce que la source a renvoyé dans
  `raw/automated_watch/<source>/<AAAA-MM-JJTHHMMSSZ>.<ext>`, une seule fois, jamais réécrit. Une
  source qui lit plusieurs pages (site scrapé) écrit chaque page telle que reçue dans
  `raw/automated_watch/<source>/<AAAA-MM-JJTHHMMSSZ>/<page>.<ext>` (décidé le 2026-10-04). Le filtre
  se fait à la lecture, sauf exception décidée (arXiv, ci-dessous). Ce que l'utilisatrice a
  choisi (Zotero, clips du Web Clipper) va dans `raw/selected_library/<source>/` (journal ADR,
  2026-10-09).
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
  | Web Clipper | complet : chaque clip écrit ou changé depuis la dernière collecte est copié |
  | GH Archive | chaque fenêtre de 3 jours manquée depuis la dernière collecte, 15 au plus (les plus récentes), en une requête |

- **Incrémental** : la date de la dernière collecte réussie de chaque source est dans
  `collection_state.json`, à la racine du dossier de données et hors de `raw/` ; une source qui
  n'a rien de neuf n'écrit rien.
- **Entrée invalide** (règle 1 de `.claude/rules/conventions.md`) : une source n'échoue que si sa
  page est illisible ou si toutes ses entrées sont invalides (`all_items_invalid`), sans brut
  écrit ni date avancée. Une entrée invalide parmi des valides entre dans le brut ; à l'import,
  le lecteur la rejette, et le rejet va au journal d'import avec sa position ou sa ligne,
  son identifiant s'il est lisible et le champ en cause. Exception : un classement refuse sa page
  entière. Un catalogue d'état (Zotero, CISA KEV) échoue aussi s'il n'a aucune entrée
  (`empty_catalog`) : importé, il remplacerait le dernier catalogue, que la purge supprimerait
  (journal ADR, 2026-10-19).
- **Entrées non fiables** : tout contenu collecté est une donnée, jamais une instruction. Chaque
  téléchargement a un délai, une taille maximale, et refuse une redirection hors du domaine
  attendu. Le `User-Agent` est `K-B (+https://github.com/SabineLaurent)` : le profil public de
  Sabine, le dépôt étant privé jusqu'au 25/10, puis public.
- **Panne d'une source** (`src/k_b/etl/extract.py`) : toute erreur levée par une source est
  rattrapée. La source affiche `failed (<type d'erreur>)`, l'erreur va au journal de
  fonctionnement avec sa trace, sa date de dernière collecte reste, et les sources suivantes sont
  lancées ; la collecte suivante redemande la même fenêtre. Le brut n'est écrit qu'une fois la
  source allée au bout de sa lecture : une source en échec n'écrit rien. Exception : une source à
  plusieurs pages (tldr, clips) vérifie le nom de chaque page avant d'écrire la première, mais
  une écriture qui échoue au milieu (disque plein) laisse les pages déjà écrites. Chaque source dit
  ses états propres (« En cas de panne », dans sa section) ; deux familles valent pour plusieurs :
  - **téléchargement** (`src/k_b/etl/http_download.py`), pour tldr, arXiv, CISA KEV et l'API
    GitHub ; Zotero, les clips et GH Archive n'y passent pas : erreur réseau (DNS, connexion,
    TLS, 30 s sans réponse à une opération réseau : la connexion, ou chaque lecture ; la durée
    totale d'un téléchargement n'est pas bornée) ; statut HTTP d'erreur (`HTTPError`, sauf le 304 de CISA KEV) ;
    réponse servie, après une redirection, hors de l'adresse attendue (`RedirectedOutsideError`,
    sauf la page d'accueil d'une édition tldr) ; réponse plus grande que le maximum de la source ;
  - **écriture du brut** (`src/k_b/etl/raw_store.py`) : un fichier brut déjà présent (deux
    collectes dans la même seconde) est refusé (`FileExistsError`) ; un dossier ou un fichier qui
    ne s'écrit pas (droits, disque plein) lève une `OSError`.
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
  liste de releases, ou dont toutes les releases sont invalides, fait échouer la source) ; un
  avertissement est journalisé si la page entière est plus récente que la dernière collecte (des
  releases ont pu manquer, il faudra lire les pages suivantes). Limite : une page dont la seule
  release nouvelle est invalide n'est pas écrite ; son rejet n'atteint le journal d'import
  qu'avec la page suivante écrite, tant qu'elle reste parmi les 100 dernières releases.
  Alertes collectées (PR de #11) : un brut par écosystème (`pip`, `npm`), relues par GitHub
  depuis la veille de la dernière collecte (date de revue, pas de publication : GitHub relit
  parfois une alerte des jours après l'avoir publiée), même avertissement si la page de 100 est
  pleine. Une page qui porte une alerte invalide est écrite, même sans alerte valide nouvelle :
  l'alerte sort de la page à mesure que la fenêtre avance, et son rejet doit atteindre le journal
  d'import.
  Un écosystème dont la seule alerte de la fenêtre est invalide échoue à chaque collecte
  (`all_items_invalid`, sa date reste), jusqu'à la première alerte valide revue.
  Dépôts les plus étoilés collectés (PR de #11) : un instantané du top 100 à chaque collecte
  (un classement change toujours) ; entrées, sorties et montées se calculent à la lecture en
  comparant deux instantanés. Une réponse marquée `incomplete_results`, ou de moins de 100 dépôts, est
  refusée.
- **Filtre à la requête** (exception à la règle du brut intact, décidée le 2026-10-02) : les
  alertes sont demandées pour les seuls paquets suivis (`affects=`). Tout l'écosystème `npm`
  dépasse 100 alertes par semaine et obligerait à paginer.
- **Jeton** : sans `KB_GITHUB_TOKEN` (ou vide), les requêtes partent sans jeton, avec la limite
  de 60 requêtes par heure. Quand les releases ou les alertes sont collectées, `kb collect` le
  journalise une fois, au lancement :
  `WARNING k_b.cli: KB_GITHUB_TOKEN not set: the GitHub API allows 60 requests per hour instead
  of 5,000`. Avec le jeton, rien n'est journalisé sur lui, et sa valeur n'entre dans aucun
  message. Les dépôts les plus étoilés seuls ne le déclenchent pas : ils appellent la recherche,
  qui a son propre quota, à part. Un jeton que GitHub refuse donne un statut HTTP d'erreur à
  chaque source GitHub (états communs du téléchargement).
- **En cas de panne :** releases (`github_releases_<dépôt>`), en plus des états communs : la page
  n'est pas du JSON, ou pas une liste ; toutes ses releases sont invalides (`all_items_invalid`) ;
  une release est d'un autre dépôt que celui demandé (casse ignorée). Une release invalide parmi
  des valides entre dans le brut quand la page est écrite, et l'import la rejette (limite : une
  page dont la seule release nouvelle est invalide n'est pas écrite, voir « État »).
- **En cas de panne :** alertes (`github_advisories_<écosystème>`), en plus des états communs : la
  page n'est pas du JSON, ou pas une liste ; toutes ses alertes sont invalides
  (`all_items_invalid` ; un écosystème dont la seule alerte de la fenêtre est invalide échoue à
  chaque collecte, voir « État »).
- **En cas de panne :** dépôts les plus étoilés (`github_most_starred`), en plus des états
  communs : un classement refuse sa page entière (règle 1 de `.claude/rules/conventions.md`) :
  pas du JSON ; pas une réponse de recherche avec une liste `items` ; `incomplete_results` autre
  que `false` ; un nombre de dépôts autre que 100 ; un dépôt invalide (nom qui n'est pas
  `owner/name`, URL hors de `https://github.com/`, nombre d'étoiles qui n'est pas un entier…).
  Sans fenêtre de dates, un échec ne retarde rien : la collecte suivante prend un nouvel
  instantané, et celui du jour manqué est perdu.

### API arXiv — service web

- **Technologie** : API `https://export.arxiv.org/api/query`, réponse Atom (XML), lue avec
  `xml.etree.ElementTree` de la bibliothèque standard.
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
  parmi des valides ne fait pas échouer la collecte (sa fenêtre la garderait pour toujours) :
  elle entre dans le brut, et l'import la rejette au journal d'import. Si toutes le sont, la
  source échoue (`all_items_invalid`). Une entrée d'erreur de l'API fait, elle,
  échouer la collecte. Limites assumées : la révision (`v2`) d'un papier soumis avant la fenêtre
  n'est pas collectée, ni un papier retenu en modération plus de 7 jours.
- **En cas de panne :** en plus des états communs (dont le `503` sous charge, ci-dessus), la
  source échoue si la réponse n'est pas du XML ou pas un flux Atom, si le flux porte une entrée
  d'erreur de l'API, si `totalResults` manque ou n'est pas un nombre, si l'API annonce plus de
  papiers que la page n'en contient, ou si toutes les entrées sont invalides
  (`all_items_invalid`). La fenêtre partant de la dernière collecte réussie, un échec passager est
  repris à la collecte suivante. Le dépassement des 2 000 papiers, lui, se répète tant que la
  fenêtre les dépasse : elle part toujours du même point et s'allonge (problème connu, #71).

### Catalogue CISA KEV — fichier

- **Technologie** : fichier CSV téléchargé en HTTPS
  (`https://www.cisa.gov/sites/default/files/csv/known_exploited_vulnerabilities.csv`), lu avec
  le module `csv` de la bibliothèque standard.
- **Ce qu'on en tire** : les vulnérabilités activement exploitées ajoutées depuis la dernière
  collecte (`dateAdded`), sélectionnées à la lecture.
- **Accès** : sans authentification. Requête conditionnelle `If-Modified-Since` : une réponse 304
  n'écrit rien.
- **Limites** : pas de quota publié ; une requête par collecte. Catalogue d'environ 1 Mo, refusé
  au-delà de 10 Mio, et refusé s'il est servi hors de `https://www.cisa.gov/`. Le catalogue est
  lu avant d'être écrit : une réponse qui n'en est pas un (page HTML, colonnes manquantes), ou
  dont toutes les lignes sont invalides, fait échouer la source, sans brut écrit ni date avancée.
  Une ligne invalide parmi des valides est rejetée à l'import, avec son numéro et son `cveID`
  s'il est lisible ; tant qu'un catalogue porte une ligne rejetée, il ne retire aucune
  vulnérabilité.
- **Données personnelles** : aucune.
- **État** : collecte en place (PR de #23).
- **En cas de panne :** en plus des états communs (tout statut HTTP autre que 304), la source
  échoue si le catalogue dépasse 10 Mio, n'est pas en UTF-8 (`UnicodeDecodeError`), ne se découpe
  pas en lignes CSV (`csv.Error`, par exemple un champ de plus de 131 072 caractères, la limite
  par défaut du module `csv`), n'a pas les colonnes attendues, n'a aucune ligne
  (`empty_catalog`), ou si toutes ses lignes sont invalides (`all_items_invalid`). Un octet NUL ne fait pas échouer la source (le module `csv` de
  Python 3.13 le lit) : sa ligne entre dans le brut, et l'import la rejette. Cas limite : une date de dernière collecte qui
  n'est pas en UTC (`collection_state.json` édité à la main) fait échouer l'en-tête
  `If-Modified-Since` (`ValueError`), à chaque collecte jusqu'à ce que l'état soit corrigé.

### Obsidian Web Clipper — fichier

- **Technologie** : fichiers `.md` avec en-tête YAML (*frontmatter*) entre deux lignes `---`,
  puis le texte gardé en Markdown, écrits par l'extension Web Clipper dans le coffre Obsidian
  de K-B (voir « Prérequis » : elle n'y écrit pas encore).
- **Dossier** : le coffre est donné par la variable `KB_VAULT_DIR` ; son chemin n'est écrit dans
  aucun fichier du dépôt. Les clips sont dans `<KB_VAULT_DIR>/Clippings/`, le dossier du gabarit
  par défaut de Web Clipper.
- **Gabarit** : relevé le 2026-10-17 sur les 5 clips du coffre, conforme au gabarit par défaut
  de Web Clipper (mêmes clés, ordre, types, dossier et nom de fichier). Le nom du fichier est le
  titre, privé des caractères qu'un nom de fichier refuse. Les 7 clés sont présentes dans chaque
  clip, dans cet ordre ; une clé sans valeur est vide (`author:`). K-B lit une valeur vide de
  `published` absente ; un `title`, une `source` ou un `created` vide est refusé.

  | Clé | Forme relevée | Type par défaut dans Web Clipper | Valeur présente |
  |---|---|---|---|
  | `title` | texte entre guillemets | `text` | 5/5 |
  | `source` | URL `https` entre guillemets ; chaîne de requête sur 2 | `text` | 5/5 |
  | `author` | liste de liens `"[[Nom]]"` | `multitext` | 2/5 |
  | `published` | date `AAAA-MM-JJ` sans guillemets, sans heure ni fuseau | `date` | 3/5 |
  | `created` | date `AAAA-MM-JJ` sans guillemets, sans heure ni fuseau | `date` | 5/5 |
  | `description` | texte entre guillemets | `text` | 4/5 |
  | `tags` | liste, `"clippings"` | `multitext` | 5/5 |

  K-B lit le frontmatter avec PyYAML et son chargeur `BaseLoader`, qui ne devine aucun type
  (« All scalars are loaded as strings »,
  [PyYAML yaml.load(input) Deprecation](https://github.com/yaml/pyyaml/wiki/PyYAML-yaml.load(input)-Deprecation),
  lue par Context7 le 2026-10-17) : chaque valeur est un texte ou une liste de textes, et une date est lue par K-B, pas par le
  lecteur YAML (« Du brut au jeu d'items », Clips). La forme des dates dépend des réglages de
  Web Clipper (un type `datetime` changerait les dates) : une autre forme est rejetée, pas
  devinée. Source du gabarit par défaut (dossier `Clippings`, clés,
  valeurs et types) : `createDefaultTemplate` et `updateGlobalPropertyTypes` dans
  [`src/managers/template-manager.ts`](https://github.com/obsidianmd/obsidian-clipper/blob/c48ccdfe35a20e996d563fa843b17bb05bcb68c3/src/managers/template-manager.ts)
  du dépôt officiel `obsidianmd/obsidian-clipper`, dernier commit du fichier `c48ccdf` du
  2024-12-04, lue par l'API GitHub le 2026-10-17.
- **Ce qu'on en tire** : un item par fichier : titre (`title`), URL source (`source`), date
  d'ajout (`created`), date de publication (`published`, si la page en donne une), et le texte
  gardé, après le frontmatter, et ses tags (`tags`, depuis #260). Ne sont pas lus : `author`,
  `description`. Comment un clip
  entre en base (champs, clé, dates, rejets, doublons) : « Du brut au jeu d'items », étape 4,
  « Clips ».
- **Accès** : lecture du dossier local du coffre (`src/k_b/etl/sources/clipping.py`) ; aucun
  réseau. Le coffre est donné par la variable `KB_VAULT_DIR`, en chemin complet ; absente ou
  vide, les clips sont sautés, `kb collect` l'affiche, et son code de sortie ne change pas. Pas
  de valeur par défaut, comme `KB_ZOTERO_DIR` : c'est un dossier de la machine de
  l'utilisatrice (règle 2 de `.claude/rules/poc.md`). K-B ne fait que lire le coffre : il n'y
  écrit, n'y déplace et n'y supprime rien.
- **Ce qui est lu** : les fichiers `.md` de `Clippings/`, sans ses sous-dossiers ni les fichiers
  cachés ; un lien symbolique est sauté (il pourrait pointer hors du coffre), et un fichier
  remplacé par un lien entre sa liste et sa lecture n'est pas suivi (`O_NOFOLLOW`).
- **Limites** : aucune limite de débit. Un clip fait au plus 1 000 000 octets
  (`CLIP_MAX_BYTES`, `src/k_b/items.py` ; le plus gros des 5 clips du 2026-10-17 fait
  183 441 octets), lu au plus un octet de plus.
- **Brut** : chaque clip écrit ou changé depuis la dernière collecte (la plus récente de sa date
  de modification et de sa date de changement : une copie qui garde la date de modification,
  par `cp -p`, le Finder ou une synchronisation, a une date de changement nouvelle), copié **tel
  quel** dans `raw/selected_library/clipping/<AAAA-MM-JJTHHMMSSZ>/<nom>.md` (journal ADR,
  2026-10-09). Le nom est fait des 16 premiers caractères hexadécimaux du SHA-256 du nom du
  fichier dans le coffre : le même clip a le même nom d'une collecte à l'autre, et son titre
  n'entre ni dans le chemin du brut ni dans le journal d'import. Aucun clip changé : rien n'est
  écrit. **Marge**, dans les deux sens (`CLIP_CHANGE_MARGIN`, 60 s, `core/config.py`) : un clip
  changé jusqu'à 60 s avant la dernière collecte est copié de nouveau, puis écarté
  `already_seen` à l'import s'il n'a pas changé ; un clip changé moins de 60 s avant la collecte
  en cours, qui peut être encore en cours d'écriture (Obsidian, Web Clipper, une
  synchronisation), est laissé à la collecte suivante, qui le prend (un clip copié tronqué
  entrerait tronqué en base, jusqu'à la collecte suivante qui le recopie). Un clip dont la date a changé entre la liste du dossier et sa lecture
  (une synchronisation, une édition) est laissé de même à la collecte suivante. Un clip renommé ou
  supprimé entre la liste et la lecture est sauté, et compté au journal : son nouveau nom est lu à
  la collecte suivante. Hypothèse, non
  mesurée : l'horloge d'un système de fichiers peut être plus grossière que celle de `kb` (un
  tick sous Linux) ou en retard sur elle (coffre monté depuis l'hôte dans un conteneur, #200) ;
  sans marge, un clip écrit juste après le début d'une collecte serait daté d'avant elle et
  jamais copié (décision du 2026-10-17 : une perte sans trace est pire que quelques octets
  recopiés). Limites : un clip supprimé du coffre n'est pas vu ; un changement de ses seules
  métadonnées (`chmod`, une étiquette du Finder) change sa date de changement, et le clip est
  recopié pour rien (RGESN 1.6, quelques octets par clip).
- **En cas de panne :** la source échoue, n'écrit rien (sauf une écriture qui échoue au milieu de
  la copie : les clips déjà écrits restent, règles communes, « Panne d'une source »), et sa date
  de dernière collecte reste ; la collecte suivante recommence. Les états :
  - `ClipTooLargeError` (`clip_too_large` : un clip dépasse 1 000 000 octets ; le message cite
    son nom de fichier, tronqué et échappé par `quote_value`, sa taille et le maximum). **Exception
    à la règle 1 de `.claude/rules/conventions.md`**, qui ne fait échouer une source que pour une
    page illisible ou des entrées toutes invalides (décision du 2026-10-17, tranchée par
    time-knight sur délégation de Sabine) : un clip est une page, et un plafond dépassé se voit à
    chaque collecte au lieu de passer en silence. Tant que le fichier reste dans le coffre, aucun
    clip nouveau n'est copié ;
  - `all_items_invalid` : tous les clips copiés seraient rejetés à l'import (lus et convertis
    comme par l'import, `RecursionError` comprise) ;
  - `all_items_invalid`, cas limite assumé (règle 1, décision du 2026-10-17) : une note sans
    frontmatter posée seule dans `Clippings/` fait échouer la source à chaque collecte, jusqu'au
    clip valide suivant ; elle est alors copiée, et rejetée à chaque import ;
  - `ClippingsFolderMissingError` (`clippings_folder_missing`, sans chemin dans le message) : le
    coffre n'a pas de dossier `Clippings/`, ou n'existe pas. Créer `Clippings/`, ou attendre le
    premier clip (Web Clipper le crée). Pas pris pour un coffre sans clip : la date de collecte
    avancerait, et les clips qu'un montage ou une synchronisation apporteraient ensuite, avec
    leurs dates anciennes, ne seraient jamais copiés (décision du 2026-10-17, tranchée par
    time-knight sur délégation de Sabine, qui inverse une correction du même jour) ;
  - `PermissionError` : un clip ou le dossier ne se lit pas (droits) ;
  - `OSError` : un clip qui ne se lit pas pour une autre raison, dont `ELOOP` (un fichier
    remplacé par un lien symbolique entre sa liste et sa lecture). Hypothèse, non vérifiée : un
    fichier iCloud non téléchargé pourrait lever une telle erreur ; macOS peut aussi le
    télécharger à la lecture, ou le montrer sous un nom caché (`.icloud`), que la liste saute. Un
    tel clip fait échouer la source, comme `clip_too_large`, au lieu d'être sauté :
    sauté pendant que la date avance, il ne serait plus revu tant qu'il ne change pas (décision
    du 2026-10-17, tranchée par time-knight sur délégation de Sabine).

  Un clip illisible parmi des clips valides est copié : l'import le rejette (règle 1 de
  `.claude/rules/conventions.md`). Le journal ne cite que des nombres : clips lus, laissés à la
  collecte suivante (changés depuis moins de 60 s, ou pendant leur lecture), disparus entre la
  liste et la lecture.
- **Données personnelles** : le champ `author` de la page gardée, s'il existe (l'auteur public de
  l'article, écrit en liens `[[Nom]]`) : copié dans le brut, jamais lu en base. La description, le
  texte gardé et ses liens `[[…]]` sont du texte libre qui peut nommer des personnes, et le
  texte peut porter les notes de l'utilisatrice ; le texte va en base (`clip.body`). Le nom du
  fichier est le titre. Voir le [registre des traitements](registre-traitements.md).
- **Prérequis** : coffre créé le 2026-10-17 (#147), avec une copie de 5 clips ; Web Clipper n'y
  écrit pas encore (réglage à venir).

### tldr.tech — scraping

- **Technologie** : pages HTML `https://tldr.tech/<édition>/<AAAA-MM-JJ>` (vérifié :
  `https://tldr.tech/ai/2026-09-30` répond 200). La collecte garde chaque page brute ; la lecture des articles se fait à la
  transformation.
- **Ce qu'on en tire** : un item par article de chaque édition suivie : titre, lien, résumé.
- **Lecture d'une page** (#57, `read_articles`, `k_b/etl/sources/tldr.py`, avec BeautifulSoup et
  l'analyseur `html.parser` de la bibliothèque standard) : une entrée par `<article>` de la
  page. Le titre est le texte de `a.font-bold`, le lien son `href`, le résumé le texte de
  `div.newsletter-html`, ses morceaux (paragraphes, liens) séparés par une espace. L'édition est lue dans le nom du dossier brut
  (`tldr_ai` → `ai`), la date de l'édition dans le premier `h1` de la page
  (`TLDR AI 2026-10-08`), le rang est la position de l'entrée parmi les `<article>` de la
  page, à partir de 1.
  - **Entrées écartées**, sans rejet ni ligne de journal : celles dont le titre contient
    « (Sponsor) », et les offres d'emploi de TLDR, reconnues par leur lien
    (`https://jobs.ashbyhq.com/tldr.tech/`, décision de Sabine du 2026-10-12). Elles comptent
    dans le rang : changer ce qui est écarté ne renumérote aucun article.
  - **Page refusée entière** (rejet au journal d'import, page non inscrite au registre, relue à
    chaque import) : elle n'est pas en UTF-8 ; elle n'a pas de `h1` ; son premier `h1` n'est
    pas « TLDR <titre> <date> » (le `h1` trouvé est cité, échappé et coupé à 100 caractères) ;
    un `<article>` en contient un autre (refusée avant la lecture des entrées : une page
    d'articles imbriqués coûterait un temps quadratique, 18 s mesurées pour 50 Ko) ;
    aucun de ses articles n'a à la fois un titre, un lien et un résumé (le nombre d'`<article>`
    trouvés est cité).
  - **Entrée refusée** (rejet au journal d'import, les autres entrées sont lues) : sans titre,
    sans lien `https` (un lien sans hôte, ou que `urlsplit` refuse, est refusé aussi, pour
    toutes les sources : le motif dit l'état et la longueur du lien, sans le recopier), sans
    résumé, ou avec un texte trop long. Dans le motif, `entry N` est
    la position de l'entrée parmi les entrées lues, à partir de 0, entrées écartées non
    comptées : ce n'est pas le rang.
  - Certains liens sont échappés deux fois dans la page (`&amp;amp;`) : le lecteur défait le
    second échappement, sinon leur `utm_*` resterait. Les `utm_*` sont retirés à la
    normalisation, comme pour tout item.
  - **Limites** (mesures sur les 18 pages collectées du 2026-09-30 au 2026-10-09, 315
    entrées) : le titre d'édition du `h1` n'est pas comparé au dossier : une page d'une autre
    édition rangée sous `tldr_ai` entrerait comme édition `ai`. Si la date du `h1` diffère de
    celle du nom du fichier, celle du `h1` l'emporte (18 pages sur 18 ont la même) : une page
    de la veille servie à l'adresse du jour voit ses articles écartés `already_seen` ; une
    page qui se dirait d'un jour à venir prendrait la clé de ce jour, et l'édition de ce jour
    serait écartée à son tour. Le `h1` doit porter un nom d'édition entre « TLDR » et la
    date : une édition titrée « TLDR <date> » serait refusée à chaque import (forme non
    observée ; à vérifier quand une édition est ajoutée à `TRACKED_EDITIONS`). Une offre
    d'emploi publiée ailleurs que sur le site d'offres de TLDR entre comme article. Un lien
    qui passe par `links.tldrnewsletter.com` est gardé tel quel (3 liens) : l'adresse de
    l'article demanderait un appel réseau.
  - **Dépendance** : `beautifulsoup4` (4.15.0, du 2026-06-07) amène `soupsieve`, verrouillé
    en 2.10 (du 2026-09-24) dans `uv.lock` : la 3.0.3 que `uv` avait choisie datait du jour
    même (décision de Sabine du 2026-10-12, constat de la revue de sécurité). **Limite** :
    `pyproject.toml` ne porte pas cette borne ; un `uv lock --upgrade` remontera `soupsieve`.
- **Jours sans édition** : un jour redirigé vers la page d'accueil de l'édition,
  `https://tldr.tech/<édition>`, n'a pas de page d'édition (observé pour le 2026-10-03 et le
  2026-10-04) : il est journalisé avec l'adresse de redirection et sauté. Toute autre
  redirection ou erreur HTTP fait échouer la source.
- **Journal** : chaque jour donne une ligne, avec l'édition, le jour et ce qui a été observé :
  page gardée (taille en octets), redirection vers la page d'accueil (adresse d'arrivée), ou
  erreur (message reçu et URL demandée) ; une collecte sans aucune page le dit aussi.
  `kb collect` affiche les lignes de niveau INFO et au-dessus.
- **En cas de panne :** une erreur sur un jour (redirection autre que vers la page d'accueil de
  l'édition, statut HTTP d'erreur, réseau, page de plus de 1 Mio) fait échouer l'édition (sa
  source, `tldr_<édition>`) ; le journal donne l'erreur avec le jour et l'URL demandée. Les pages
  déjà téléchargées pendant cette collecte ne sont pas écrites, et les jours suivants ne sont pas
  demandés ; la collecte suivante reprend au jour de la dernière collecte réussie. Une date de
  dernière collecte postérieure à aujourd'hui (UTC) fait échouer l'édition avant tout
  téléchargement. **Écart à la règle 1** de `.claude/rules/conventions.md` (constaté le
  2026-10-18, non tranché ici) : une page reçue n'est pas lue à la collecte ; une page qui n'est
  pas une édition est écrite telle quelle, et refusée à chaque import (« Page refusée entière »,
  ci-dessus).
- **Fréquence** : voir les règles communes.
  Chaque collecte lit chaque jour depuis le jour de la dernière collecte, relu car son édition a
  pu paraître après elle, jusqu'à aujourd'hui (UTC) ; la première lit les 7 jours précédents et
  aujourd'hui. La page relue est en double dans deux collectes : ses articles sont écartés à
  l'import, `already_seen` (12 à 18 lignes au journal d'import par page relue : ses
  articles gardés).
- **Accès** : sans authentification. Le `robots.txt` autorise tout, sauf les pages d'abonnement
  et de compte (`/subscribed`, `/manage`, `/info`…), qu'on ne lit pas.
- **Limites** : pas de quota publié ; on s'impose une page à la fois, avec une pause entre deux
  pages. Les liens portent des paramètres de suivi `utm_*` et certaines entrées sont
  sponsorisées : traité à la lecture (ci-dessus).
- **Données personnelles** : aucune (voir le registre des traitements).
- **Suivi** : éditions **ai**, **infosec** et **dev** (ai le 2026-10-01, les deux autres le
  2026-10-04), une source par édition (`tldr_ai`…), dans `TRACKED_EDITIONS` de
  `k_b/etl/sources/tldr.py` (neuf candidates dans [sources-detaillees.md](sources-detaillees.md)).

### Zotero — base de données

- **Technologie** : base SQLite `zotero.sqlite`, dans le dossier de données de Zotero, lue par
  une requête SQL avec le module `sqlite3` de la bibliothèque standard
  (`src/k_b/etl/sources/zotero.py`). Zotero verrouille sa base quand il tourne, et
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
  `raw/selected_library/zotero/<AAAA-MM-JJTHHMMSSZ>.json` (journal ADR, 2026-10-09). La
  bibliothèque est extraite à chaque collecte ; l'extrait est écrit seulement s'il diffère, octet
  pour octet, du dernier extrait de ce dossier (#139). La date des fichiers de Zotero n'est pas
  comparée : Zotero ouvert écrit dans son `-wal` sans que la bibliothèque change, et un autre
  dossier Zotero peut avoir des fichiers plus anciens que la dernière collecte. Un extrait dont
  tous les documents sont invalides fait échouer la source (`all_items_invalid`, règle 1 de
  `conventions.md`) et n'est pas écrit. Les valeurs sont celles de Zotero, sans conversion
  (dates `AAAA-MM-JJ HH:MM:SS` en UTC). `kb import` lit ces extraits vers `zotero_entry` et
  `highlight` (#138 ; voir [stockage.md](stockage.md) et la règle du catalogue d'état, étape 4),
  puis ne garde que le dernier extrait importé (journal ADR, 2026-10-19).
- **En cas de panne :** la source échoue par un état nommé, n'écrit rien, et sa date de dernière
  collecte reste ; la collecte suivante recommence. Les états :
  `ZoteroCopyInconsistentError` (le contrôle d'intégrité refuse la copie),
  `ZoteroChangedDuringCopyError` (un des deux fichiers a changé pendant la copie),
  `ZoteroQueryFailedError` (la requête échoue ; le message nomme la table ou la colonne
  absente, sinon le type de l'erreur et le nom que SQLite lui donne, jamais un contenu de la
  bibliothèque), `FileNotFoundError` (pas de `zotero.sqlite` dans le dossier),
  `empty_catalog` (aucun document) et `all_items_invalid` (tous les documents invalides : le
  message donne leur nombre, la position, le champ et le type d'erreur du premier, jamais sa
  valeur).
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
  Requête : `TRENDS_QUERY`, `src/k_b/etl/sources/gh_archive.py`. `kb import` écrit ses lignes dans
  la table `trend` (« Du brut au jeu d'items », étape 4, « Classements GH Archive »).
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
- **En cas de panne :** sans `GOOGLE_APPLICATION_CREDENTIALS`, la source est sautée, pas en
  échec. Avec elle, la source échoue si le fichier de clé est introuvable ou refusé à la création
  du client BigQuery ; si la table de la veille n'est pas close (`DayTableNotClosedError`) ; si le
  `dry_run` ne donne pas de volume (`DryRunVolumeUnknownError`) ou dépasse le plafond
  (`DryRunOverLimitError`) ; si BigQuery refuse ou interrompt la requête (droits, quota du bac à
  sable, délai de 300 s), avec l'erreur de son client ; si le résultat n'est pas un classement
  lisible (`TrendsExtractInvalidError`, refusé entier) ; ou si la date de dernière collecte est
  postérieure à aujourd'hui (UTC). Rien n'est écrit, et les fenêtres dues le restent : la
  collecte suivante les reprend, 15 au plus.
- **Données personnelles** : chaque événement porte le login de son auteur (`actor`). La requête
  ne le sélectionne pas : elle ne renvoie que des comptes par dépôt. Le nom du dépôt
  (`owner/repo`) porte le login de son propriétaire quand c'est une personne : gardé, il identifie
  le dépôt ([registre](registre-traitements.md)). Un message d'erreur n'en cite que la longueur.
- **Prérequis** : la clé du compte de service ; sans `GOOGLE_APPLICATION_CREDENTIALS`, la source
  est sautée.

## Du brut au jeu d'items

1. **Collecte** : chaque source écrit son brut dans `raw/automated_watch/<source>/`, ou, pour ce
   que l'utilisatrice a choisi (Zotero, clips), dans `raw/selected_library/<source>/` (règles
   communes).
2. **Lecture** : un lecteur par sorte de source transforme le brut en items validés par un modèle
   Pydantic. Le lecteur est retrouvé par le nom du dossier brut (`github_releases_<dépôt>/` est
   lu par celui des releases), que la source soit encore suivie ou non. Les sortes sont déclarées
   une seule fois, dans `source_kinds.py`. Un dossier qui n'appartient à aucune sorte est
   journalisé et sauté. Exception : un classement GH Archive n'est pas fait d'items (ADR du
   2026-10-08) ; ses lignes sont lues par un lecteur à part (`read_trend_files`,
   `src/k_b/etl/sources/gh_archive.py`), et la sorte `gh_archive` reste déclarée sans lecteur
   d'items. Les items ont les mêmes champs : source, identifiant dans la source,
   titre, URL, auteurs (arXiv), date de publication et date de révision (arXiv), date d'ajout (Clipper, Zotero),
   contenu ou résumé, date de collecte, chemin du brut d'origine. Une date absente reste vide. Toutes les dates sont en UTC, avec fuseau. Une ligne
   illisible est rejetée et journalisée, pas devinée.
3. **Normalisation** des items lus (`normalize_item`, `src/k_b/etl/normalize.py`) :
   - dates ramenées en UTC ;
   - URL normalisées : les paramètres `utm_*` sont retirés, les autres restent tels quels et
     dans leur ordre.

   `brief09_assistant-veille-tech` (relu le 2026-10-01) a servi d'indication, pas de modèle : il
   ne fait pas autorité. On y retrouve un modèle d'article commun et la date de révision arXiv. À
   l'inverse, brief09 ne dédoublonne que sur l'URL exacte, ignore les révisions (première version
   gardée), date la collecte sans fuseau et retire les doublons sans trace. Laissé de côté : les
   étiquettes posées par un LLM, hors de la v0.
4. **Stockage** des items dans la base : SGBD, modèles et ce que chaque source met dans l'item,
   dans [stockage.md](stockage.md). `kb import` (`run_import`,
   `src/k_b/commands/import_command.py`) n'importe que les fichiers bruts pas encore importés
   (#106) : il lit le registre de la base
   (`read_imported_paths`, `src/k_b/etl/load.py`), puis les fichiers qui n'y sont pas
   (`read_raw_items`, `src/k_b/etl/transform.py`, pour les items ; `read_trend_files`,
   `src/k_b/etl/sources/gh_archive.py`, pour les classements GH Archive), puis écrit la base
   (`import_items`) : fichiers d'items et classements en une seule suite, dans l'ordre des
   collectes. Il affiche
   le nombre de fichiers bruts lus (`raw files read`).

   - **Registre** : la table `raw_data`, une ligne par fichier lu, ou par page d'un dossier de
     pages. Un fichier lu y entre, même s'il n'a donné aucun item, et même si certaines de ses
     entrées sont rejetées : celles-ci ne seront relues que par une reconstruction. Un fichier
     sauté faute de lecteur n'y entre pas. **Un fichier illisible n'y entre pas** (décision de
     Sabine du 2026-10-12) : il est relu et rejeté à chaque import, et l'import qui suit la
     correction du lecteur ou du brut le lit, sans reconstruction. Une collecte mal nommée
     (dossier ou fichier dont le nom n'est pas une date) n'a pas de date de collecte : elle
     n'entre pas non plus au registre, et elle est rejetée à chaque import, sans compter dans
     `raw files read`. **Un classement GH Archive dont la base refuse une ligne n'y entre pas
     non plus** (décision de Sabine du 2026-10-13, #136) : il est refusé entier et relu à chaque
     import. Limite, la même que pour un fichier illisible : une fois accepté, il est inscrit
     après des classements collectés plus tard ; le premier classement vu d'une fenêtre peut
     alors différer de celui d'une reconstruction.
   - **Une transaction** : chaque fichier lu est inscrit au registre, puis ses items sont
     écrits ; le journal est écrit avant la validation (`COMMIT`). Chaque item (une entrée
     Zotero avec ses surlignages et sa publication citée), et chaque classement avec son
     inscription, est écrit dans un `SAVEPOINT` (`database/savepoint.py`, #136) : une entrée que
     la base refuse pour ses propres valeurs (`CHECK`, `UNIQUE`, `NOT NULL`, entier au-delà de
     64 bits, surrogate isolé) est annulée seule (`ROLLBACK TO SAVEPOINT`) et devient un rejet du
     journal ; l'import continue. Une `FOREIGN KEY`, une `PRIMARY KEY` ou un type de table
     `STRICT` refusés ne viennent pas de l'entrée mais de son écrivain ou du schéma : ils
     arrêtent l'import.
     Le fichier d'un item refusé reste inscrit, comme celui d'une entrée rejetée à la lecture, et
     son catalogue (CISA KEV, Zotero) ne retire rien. Toute autre erreur dans la base (disque
     plein, base verrouillée), ou un journal qui ne s'écrit pas, n'écrit rien : aucun fichier
     n'est inscrit, tous seront relus. Si la validation échoue, ou sur une interruption (Ctrl-C,
     SIGTERM) reçue avant elle, le journal écrit est supprimé ; une interruption reçue pendant ou
     après la validation garde l'import et son journal, et le journal de fonctionnement le dit
     (`import committed, log kept`). Pourquoi : un fichier
     inscrit n'est plus relu, un journal perdu après la validation perdrait pour toujours la
     trace de ses rejets et de ses écarts (décision de Sabine du 2026-10-12, qui revient sur le
     journal écrit après la base de #105).
     **Limite** (constat de revue, acceptée par Sabine le 2026-10-12) : un `SIGKILL` entre
     l'écriture du journal et la validation laisse le journal d'un import annulé. L'autre limite
     acceptée ce jour-là, une interruption juste après la validation qui supprimait le journal
     d'un import validé, est levée par la décision de Sabine du 2026-10-18 (#193).
   - **Reconstruction complète** : supprimer la base, `kb create-db`, puis `kb import`, qui
     relit tout `raw/`. Pas d'option : une base vide n'a rien au registre.

   **La base dédoublonne** (#105, décisions de Sabine du 2026-10-12). Les items arrivent dans
   l'ordre des collectes. Un item déjà en base est reconnu par la clé naturelle de son sous-type
   ou de son référentiel (`release_id`, `ghsa_id`, `cve_id`, `arxiv_id` ; édition, date et
   rang pour un article TLDR) ; ce qu'il en advient
   dépend de la **nature** de sa source. La règle de chaque nature est une clause SQL de
   l'écrivain de sa sorte d'item, et nulle part ailleurs :

   | Nature | Sources | Item déjà vu | SQL | Règle au journal |
   |---|---|---|---|---|
   | flux de nouveautés | releases, alertes GitHub, articles TLDR | inchangé : la première version vue est gardée | `INSERT INTO item … SELECT … WHERE NOT EXISTS (sous-type de même clé) RETURNING id` | `already_seen` |
   | flux de nouveautés, **par fenêtre** (variante propre aux classements, #142) | classements GH Archive (table `trend`, pas un item) | inchangée : le premier classement vu d'une fenêtre est gardé entier ; une fenêtre qu'un autre fichier brut a déjà apportée est écartée entière | `INSERT INTO trend … SELECT … WHERE NOT EXISTS (ligne de la même fenêtre venue d'un autre fichier brut) ON CONFLICT (window_end, repository_id) DO NOTHING RETURNING id` | `already_seen`, une ligne par fenêtre |
   | catalogue d'état | CISA KEV | remplacé si son fichier est collecté après le dernier catalogue de la source déjà importé et que son contenu diffère ; `revised_at` prend la date de cette collecte | `ON CONFLICT (cve_id) DO UPDATE … WHERE` (collecte plus récente et contenu différent) `RETURNING id` | `unchanged`, `no_newer_version` |
   | flux avec révisions | arXiv | remplacé si sa révision (`updated`) est plus récente | `ON CONFLICT (arxiv_id) DO UPDATE … WHERE excluded.revised_at > publication.revised_at RETURNING id` | `revision_not_newer` |
   | `.md` importé, **par URL** (#14, #259, #260) | clips du Web Clipper | écrit en *patch* si son contenu (titre, texte, dates, tags) diffère et que son fichier n'est pas collecté avant le brut le plus récent du contenu gardé : seules les colonnes changées, la liaison de chaque tag retiré supprimée (et le tag s'il n'a plus de liaison), celle de chaque tag ajouté écrite ; `revised_at` prend la date de cette collecte | `INSERT INTO item … SELECT … WHERE NOT EXISTS (clip de même URL) RETURNING id` ; sinon lecture de la ligne gardée et de ses tags, comparaison en Python, `UPDATE clip SET` (colonnes changées), `DELETE FROM item_tag` et `DELETE FROM tag … WHERE NOT EXISTS` (les deux exceptions à la règle 5 de `conventions.md`), `INSERT INTO tag … ON CONFLICT (name) DO NOTHING` et `INSERT INTO item_tag` | `already_seen`, `no_newer_version` |
   | catalogue d'état, **à deux niveaux** (#138) | Zotero : l'entrée et chacun de ses surlignages | comme CISA KEV : remplacé si son extrait est collecté après le dernier extrait importé et que son contenu diffère ; `revised_at` prend la date de cette collecte | `ON CONFLICT (zotero_key) DO UPDATE … WHERE` (extrait plus récent, et retiré ou contenu différent) `RETURNING`, pour `zotero_entry` et pour `highlight` | `unchanged`, `no_newer_version` |

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
     (`rows withdrawn (vulnerabilities, Zotero entries, highlights)`, qui compte aussi les
     retraits Zotero).
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
   - **Classements GH Archive** (#142, décisions de Sabine du 2026-10-13) : une ligne de
     `trend` par fenêtre et par dépôt, avec ses étoiles et ses forks gagnés (les 30 premiers
     par étoiles et les 30 premiers par forks, réunis). La clé est (`window_end`,
     `repository_id`), mais la règle compare **par fenêtre**, et non par clé comme les autres
     flux de nouveautés : un classement est un tout, et un dépôt entré dans le classement à
     une seconde collecte aurait une clé nouvelle. Une ligne n'est écrite que si aucun autre
     fichier brut n'a déjà apporté sa fenêtre ; les lignes du fichier en cours, qui partagent
     sa donnée brute, ne s'écartent pas entre elles. Limites :
     - un compte faux à la première collecte reste. Trois fenêtres ont été comptées, en tout
       ou en partie, sur des tables de jour appauvries (ci-dessus, et
       [bigquery.md](bigquery.md#relevé-du-2026-10-13)) : celle du 2026-10-10, collectée le
       2026-10-11 ; celles du 2026-10-11 (deux jours appauvris sur trois, le 09/10 et le 10/10)
       et du 2026-10-12 (un sur trois, le 10/10), collectées le 2026-10-13. Les corriger
       demande de retirer leur fichier brut et de reconstruire la base. Aucune issue ne porte
       la recollecte d'une fenêtre déjà prise ;
     - « premier vu » veut dire premier importé : un fichier brut plus ancien, importé après
       un plus récent de la même fenêtre, est écarté ; une base reconstruite, qui lit dans
       l'ordre des collectes, garderait le plus ancien ;
     - une fenêtre annoncée par un fichier sans aucune ligne ne laisse pas de trace : un
       fichier ultérieur de cette fenêtre est écrit.
   - **Zotero** (#138, décisions de Sabine du 2026-10-13) : l'extrait est complet à chaque
     collecte ; seul le dernier compte, pour l'entrée comme pour chaque surlignage. Pourquoi,
     selon Sabine : les fiches de lecture tirées d'un article restent dans son coffre même si
     elle supprime l'article dans Zotero, et une modification d'un commentaire ou d'un
     surlignage doit se reporter en base. Règles, celles de CISA KEV :
     - un document ou un surlignage modifié dans Zotero est réécrit, `revised_at` daté ; un
       surlignage modifié compte son entrée comme écrite, et l'item pointe alors vers ce
       fichier ;
     - un document ou un surlignage absent d'un extrait plus récent est marqué retiré
       (`withdrawn_at`), jamais supprimé ; la première absence garde sa date ; un document
       retiré retire ses surlignages (ils sont absents de l'extrait) ; s'il réapparaît, il est
       réécrit, `withdrawn_at` vidé et `revised_at` daté, même à contenu identique ;
     - une entrée dont seul un surlignage est retiré est journalisée `unchanged` et garde son
       fichier : une absence n'est pas une version ;
     - un extrait dont un document est rejeté, ou sans document, ne retire rien. **Limite**
       (acceptée par Sabine le 2026-10-13) : l'extrait étant complet, un document invalide
       revient dans chaque extrait, et plus rien n'est retiré tant qu'il n'est pas corrigé dans
       Zotero ; le rejet est écrit au journal et compté par `kb import` à chaque import ;
     - un extrait importé en retard ne change rien ; ce qu'il est seul à apporter (une entrée,
       un surlignage) est écrit retiré, à la date du dernier extrait importé, et son entrée est
       comptée écrite. Il ne crée pas de publication pour une entrée qu'il n'écrit pas.
       **Limite** (constat de revue, comme celle de CISA KEV du 2026-10-12) : une entrée
       rejetée dans le dernier extrait, qu'un extrait plus ancien importé en retard apporte
       valide, est écrite retirée alors qu'elle est encore dans Zotero ; une reconstruction de
       la base, une fois le rejet corrigé, la règle.
   - **Clips** (#14, décisions de Sabine du 2026-10-17) : un clip a un `item.id` technique, comme
     les autres items ; son URL est sa clé naturelle (`clip.url`, unique). Agrégation :
     - **champs lus** : `title` (texte non vide, au plus 1 000 caractères), `source` (URL `http`
       ou `https`), `created` (obligatoire), `published` (facultative) et le texte après le
       frontmatter (au plus 1 000 000 caractères), gardé tel quel, une ligne `---` plus bas
       comprise (un filet du texte), et `tags` (#260, ci-dessous). Les autres propriétés sont
       ignorées ;
     - **tags** (#260, décisions de Sabine du 2026-10-19) : lus en liste, ou en texte simple
       (`tags: llm`, un tag) ; une valeur absente (vide, `null`, `~`, ou pas de propriété) ne
       donne aucun tag, et un élément absent est ignoré. Chaque tag est normalisé
       (`normalize_tag`, `items.py`) : sans espaces autour, sans le `#` d'Obsidian au début, en
       minuscules ; `LLM`, ` llm ` et `#llm` donnent `llm`, une fois. Un tag vide une fois
       normalisé est ignoré ; `clippings`, que le gabarit par défaut met sur chaque clip (5 clips
       sur 5 relevés), est écarté. Un tag qui n'est pas du texte (une liste, un dictionnaire),
       trop long (plus de 100 caractères) ou avec un NUL, ou plus de 30 tags, fait **refuser le
       clip entier**, par la
       voie de rejet des autres propriétés ; de même un tag que la normalisation laisse sous une
       forme qu'elle changerait encore (`##llm` donne `#llm`). Un tag est une ligne de `tag`,
       partagée par les clips qui le portent, liée à chacun par `item_tag`. **Limites**
       (hypothèses, non vérifiées sur le coffre) : `tags: llm, ai` donne un seul tag `llm, ai`,
       et `tags: "#ai #llm"` le seul tag `ai #llm` : ni une virgule ni une espace intérieure ne
       sont lues comme un séparateur ; un même mot écrit sous deux formes
       Unicode (NFC et NFD) donne deux tags. Un `#tag` sans guillemets (`- #llm`, `tags: #llm`)
       est un commentaire YAML : lu absent, il est perdu sans trace (vérifié avec `BaseLoader` le
       2026-10-19 ; Web Clipper écrit ses tags entre guillemets). Les tags sont rangés par nom :
       l'ordre du coffre n'est pas gardé. La clé stable d'un tag est son nom (`tag.name`,
       unique) ; `tag.id` est interne, et SQLite peut redonner l'id d'un tag supprimé au tag
       créé ensuite (rien ne l'expose). Les `#tags` écrits dans le texte ne sont pas lus ;
     - **clé** : l'URL sans ses paramètres `utm_*` (`remove_tracking_parameters`), les autres
       paramètres gardés tels quels et dans leur ordre ; pas d'empreinte de contenu (journal ADR,
       « Collecte : clips ») ;
     - **homogénéisation** : `created` et `published` sont des jours `AAAA-MM-JJ`, l'année sur
       4 chiffres à partir de 1000, écrits à minuit UTC, comme `dateAdded` de CISA KEV. Le jour
       est celui que Web Clipper a écrit, dans le fuseau de l'utilisatrice. Une valeur vide,
       `null` ou `~` de `published` se lit absente. Une autre forme (heure, fuseau, nombre, forme
       compacte, semaine ISO) est rejetée, pas devinée ;
     - **rejets** : une marque d'ordre des octets en tête du clip est ignorée, comme par
       Obsidian. Un clip qui n'est pas de l'UTF-8, sans frontmatter, dont le frontmatter n'est
       pas du YAML ou pas un dictionnaire est une **page illisible** (règle 1 de
       `.claude/rules/conventions.md`) : elle n'entre pas au registre et elle est rejetée à
       chaque import. **Limite** (décision du 2026-10-17, tranchée par time-knight sur
       délégation de Sabine) : le brut ne changeant pas, ce rejet revient à chaque import
       jusqu'à la correction du lecteur ou le retrait du fichier brut. Le motif dit la ligne et
       la colonne d'une erreur YAML, jamais le texte. Un clip lisible dont une propriété est
       refusée est rejeté seul, une fois : le motif nomme le champ et son erreur, jamais la
       valeur ;
     - **nature** : `.md` importé, par URL ; la dernière version est gardée (décision de Sabine
       du 2026-10-19, #259). Un clip copié de nouveau, ou une autre copie de la même URL, au même
       contenu (titre, texte, `created`, `published`, tags normalisés, sans leur ordre) est
       écarté `already_seen` ; un contenu changé est écrit en *patch* (décision de Sabine du
       2026-10-19, #260) : seules les colonnes qui ont changé, la liaison de chaque tag retiré
       supprimée (exception à la règle 5 de `.claude/rules/conventions.md`, journal ADR,
       2026-10-19), et le tag lui-même s'il n'a plus de liaison, celle de chaque tag ajouté
       écrite, les autres laissées telles quelles ;
       `revised_at` prend la date de la collecte qui voit le changement.
       L'item pointe sur le brut le plus récent de son contenu, une copie au même contenu
       comprise. Une propriété que la base ne garde pas (`author`, `description`) ne réécrit
       rien. Un fichier collecté avant ce brut, au contenu différent, est écarté
       `no_newer_version`. `compared_with_collected_at` est la collecte de ce brut. **Limites** : deux fichiers de même URL et de contenu différent dans une même
       collecte : le second dans l'ordre des noms de pages réécrit le premier, un ordre fait par
       le hachage, donc arbitraire pour l'utilisatrice ; un clip dont l'URL source change devient
       un nouveau clip, l'ancien reste en base ; un même article gardé sous deux URL donne deux
       clips ; un clip supprimé du coffre reste en base.
   - **Source sans import** (classement des plus étoilés) : il n'entre pas dans la base (journal
     ADR, 2026-10-07).
   - Une même CVE dans deux sources (une entrée CISA et une alerte GitHub), ou citée par deux
     alertes, n'est **pas** un doublon : chaque alerte est gardée, et toutes pointent vers la
     même vulnérabilité (`vulnerability.cve_id` unique).
   - **Limite** : la base ne trouve que le doublon exact, le même identifiant dans sa source (un
     rejeu de l'ETL, des collectes qui se chevauchent). Le quasi-doublon (même contenu, autre
     métadonnée) n'est pas trouvé. Pour Zotero (décision de Sabine du 2026-10-13) : la clé
     est la clé Zotero seule, sans empreinte de contenu ; un même papier arXiv enregistré deux
     fois fait deux entrées, qui pointent vers la même publication ; un document hors arXiv
     enregistré deux fois fait deux entrées que rien ne relie.
   - **Articles TLDR** (#57, décisions de Sabine du 2026-10-12) : la clé est (édition, date de
     l'édition, rang), celle de l'ADR du 2026-10-07 ; l'URL, rangée sans `utm_*`, n'est ni
     unique ni dans la clé ; pas d'empreinte de contenu. Mesuré sur les 18 pages collectées
     (272 articles) :
     - un même article résumé par deux éditions, ou repris un autre jour, fait deux lignes :
       voulu par l'ADR (10 URL sous deux clés, toujours avec deux résumés différents) ;
     - un même contenu sous une autre URL n'est pas reconnu (aucun cas parmi les 272 ; le seul
       du brut était une offre d'emploi, écartée) ;
     - le rang est une position : le jour de la dernière collecte est relu, et si tldr.tech a
       modifié la page entre-temps (entrée ajoutée, retirée ou déplacée, encart sponsor
       compris), la première version vue reste, et un article décalé peut être écarté à tort
       ou entrer deux fois. Non mesurable sur ce brut, où aucune page n'est collectée deux
       fois.
     - La colonne `publication_id` (papier cité) est créée et laissée vide : la remplir pour
       un lien `https://arxiv.org/abs/<id>` (2 articles sur 272) n'est pas fait.
   - **Journal** : `<KB_DATA_DIR>/import-log-<AAAA-MM-JJTHHMMSSZ>.jsonl`, un fichier par
     import, nommé par sa seconde au format des noms de bruts, jamais réécrit : si le journal
     de cette seconde existe déjà, l'import s'arrête sans rien écrire (code de sortie 2). Une
     ligne JSON par rejet (`raw_file_path`, `reason`), puis par item écarté (`rule`,
     `source_code`, `source_item_id`, `raw_file_path` et la date comparée), puis par fenêtre
     d'un classement GH Archive écartée, à la même forme : `source_item_id` y est le dernier
     jour de la fenêtre (`2026-10-10`), et aucun dépôt n'est nommé (son nom porte le login de
     son propriétaire). Chaque ligne porte
     l'instant de son import, `imported_at`, en ISO 8601 UTC à la seconde, au format des dates
     de la base (`2026-10-12T15:49:03Z`, décision de Sabine du 2026-10-12, d'après le
     [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
     de l'OWASP). La date comparée est dans un champ qui dit d'où elle vient :

     | Règle | Constat | Champ | Date |
     |---|---|---|---|
     | `already_seen` | le sous-type est déjà en base, ou la fenêtre d'un classement vient déjà d'un autre fichier brut | `compared_with_collected_at` | collecte de la version gardée |
     | `unchanged` | fichier plus récent que le dernier catalogue importé, contenu identique | `compared_with_collected_at` | collecte de la version gardée, la seule comparée au contenu |
     | `no_newer_version` | catalogue : fichier collecté avant le dernier catalogue importé, ou au même instant ; clip : fichier collecté avant le brut le plus récent du contenu gardé, contenu différent | `compared_with_collected_at` | catalogue : collecte de ce dernier catalogue ; clip : collecte de ce brut |
     | `revision_not_newer` | révision arXiv plus ancienne ou égale | `compared_with_revised_at` | révision arXiv de la version gardée |

   - **Rejouable** : un second import sans nouveau brut ne lit aucun fichier (sauf un fichier
     illisible ou une collecte mal nommée) et ne change pas la base ; un item déjà en base garde
     son `item_id`, que l'API de données expose (`GET /items/{item_id}`).
   - **Auteurs** : il n'y a pas de table d'auteurs. Les auteurs d'un papier arXiv sont une liste
     JSON de noms, dans l'ordre d'arXiv, dans la colonne `publication.authors`
     (`src/k_b/database/schema.sql`), écrite telle quelle à l'import ; une révision arXiv plus
     récente remplace la liste avec le reste du papier (règle « flux avec révisions »). Elle
     reste vide tant que seul Zotero cite le papier. Les auteurs d'une entrée Zotero restent dans
     son brut, et le champ `author` d'un clip n'est pas lu : aucun n'entre en base.

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
