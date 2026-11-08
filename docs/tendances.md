# Spécification du compte rendu des tendances

Le compte rendu des tendances dit quels dépôts GitHub ressortent des fenêtres de GH Archive (table
`trend`), et pourquoi : le code calcule les rangs et les critères, lit sur GitHub une fiche légère
de chaque candidat, puis le modèle choisit **au plus 5 dépôts** et écrit quatre textes courts sur
chacun. Le fichier va dans le coffre, `veille/tendances/<date>.md`. Ce document est son contrat,
écrit avant le code (#364) ; le code vient par #365 à #370. Les décisions et leur pourquoi sont dans
le [journal ADR](ADR/journal-decisions-projet.md) (2026-10-30, « Tendances : un compte rendu deux
fois par semaine, orchestré par l'API IA ») ; les données envoyées au modèle, dans le
[registre des traitements](registre-traitements.md) ; la source et ses limites, dans
[specs-collecte.md](specs-collecte.md) (« API GitHub », « GH Archive sur BigQuery »).

C'est du **post-traitement**, pas de l'ETL : rien de ce qui est lu sur GitHub n'est gardé, ni dans
le brut ni dans la base. Les références `fichier:ligne` valent pour `main` au commit `8898095`.

**Rythme.** Deux fois par semaine, voulu par Sabine (29/10). En v1, `kb trend-report` est lancé à la
main : rien n'est planifié, comme la collecte (journal ADR, 2026-10-15, « POC du 25/10 »,
décision 3). La période part du compte rendu précédent : elle tient n'importe quel rythme. La
planification vient avec la mise en ligne (« Hors v1 »).

## Le parcours d'une demande

Comme `kb digest` → `POST /digests` ([fiches-veille.md](fiches-veille.md)) :

1. **`kb trend-report`** (`commands/trend_report_command.py`) lit le registre des comptes rendus
   (ci-dessous), vérifie que le fichier à écrire n'existe pas (comme
   `commands/digest_command.py:73`), puis envoie `POST /trend-reports` à l'API IA.
2. **L'API IA** (`ai_api/trend_reports.py`, sur le modèle de `ai_api/digests.py`), sous une échéance
   nommée de la route :
   1. lit les fenêtres de la période par l'API de données, un `GET /trends?window_end=` par jour
      (404 `trend_window_not_found` = fenêtre manquante) ; la plus récente par `GET /trends` sans
      `window_end` ; chaque réponse revalidée par un schéma fermé ;
   2. calcule rangs, trajectoires et critères en code pur (`ai_api/trajectories.py`) ;
   3. lit la fiche légère de chaque candidat sur GitHub (`ai_api/connectors/github_client.py`),
      textes nettoyés (`ai_api/repository_texts.py`) ;
   4. fait choisir au modèle au plus 5 dépôts (`ai_api/stages/trend_selection.py`) ;
   5. lit le README des seuls choisis ;
   6. fait écrire au modèle 4 textes par dépôt choisi, **un appel par dépôt**
      (`ai_api/stages/trend_writing.py`), puis contrôle la forme et la fidélité.
3. **`kb`** lit la réponse dans la borne de `kb digest` (8 000 000 d'octets et 240 s :
   [fiches-veille.md](fiches-veille.md), « Fiches dans le coffre », étape 3), la relit par un schéma fermé
   (`post/trend_report_client.py`), rend le Markdown
   (`post/trend_report_sheets.py`), l'écrit par `write_new_sheet` (`post/vault_files.py:41`), puis
   ajoute l'entrée au registre.

**Ordre des lectures GitHub.** Les fiches avant le choix ; les README entre le choix et la
rédaction. Le chemin d'un README est construit par le code depuis le nom associé au `ref` du
candidat, jamais depuis la sortie du modèle.

**Un client GitHub neuf.** L'API IA n'importe que `ai_api`, `items` et `core`
(`tests/architecture/test_apis.py:102`), et `post` n'importe ni les sources
(`tests/architecture/test_layers.py:109`) ni les API (`:207`) : le client de la collecte
(`etl/sources/github/api.py`) n'est pas joignable. Le client neuf repose sur `open_http_client`
(`core/outbound.py:45-53` : aucune redirection suivie, aucun proxy lu). Ce que les deux partagent
(`USER_AGENT`, `API_VERSION`, `WINDOW_DAYS`, les règles de relance de `etl/http_retry.py:24-29`) passe
d'abord dans `core`, sans changer de comportement (#365).

**L'API IA reste sans état** (règle 7 de `.claude/rules/poc.md`) : elle reçoit les bornes de la
période dans la demande, et seul `kb` lit le registre et écrit le coffre.

## Registre des comptes rendus

`KB_DATA_DIR/trend_reports.json`, sur le modèle de `collection_state.json` (`etl/raw_store.py:21`) :
une entrée par compte rendu écrit, avec ses fenêtres (première et dernière), le fichier, la date
d'écriture, le `request_id`, le modèle, et si le choix a été fait. Écrit par
`write_file_atomically` (règle 2 de `.claude/rules/conventions.md`). Le coffre reste en écriture
seule : `kb` ne relit jamais un compte rendu pour trouver le précédent.

| Cas | Ce que fait `kb trend-report` |
|---|---|
| Registre illisible | Arrêt avant toute demande, code 2 (`ExitCode.NOT_STARTED`) |
| Fichier du jour déjà présent | Arrêt avant la demande, code 2 |
| Aucune fenêtre nouvelle | Réponse 200 sans appel à GitHub ni au modèle ; sortie en 0, rien d'écrit |
| Compte rendu écrit | Entrée ajoutée au registre après l'écriture du fichier |
| Choix en échec | Compte rendu factuel écrit (« choix non fait ») ; le registre le note ; la période avance |
| Rédaction en échec, ou GitHub en échec sur un README | Compte rendu écrit, choix et faits compris ; « Textes non écrits : <raison>. » sous chaque dépôt concerné ; un avertissement par dépôt (sa place, l'état et le `request_id`, jamais un nom) ; la période avance (décision de Sabine du 08/11) |

**Ce que fait `kb trend-report` depuis #366** (`commands/trend_report_command.py`). Une entrée du
registre : `first_window` et `last_window` (les bornes de `period.windows`, manquantes comprises),
`file` (chemin dans le coffre), `written_at` (l'instant UTC du lancement, lu une fois, qui donne
aussi le jour du fichier), `request_id`, `model` (nul) et `choice_made` (faux ; depuis #368,
`model` est celui de la réponse et `choice_made` est vrai quand il est rempli) ; schéma fermé
(`post/trend_report_registry.py`), une entrée de plus de 15 fenêtres refusée comme la demande
(`has_too_many_windows`, `items.py`). La précédente est la dernière entrée. La réponse est revalidée
par `post/trend_report_client.py` : la période doit partir du lendemain d'`after` (ou, plafonnée,
compter 15 fenêtres), jour après jour, jusqu'à `latest_window`, sans dépasser le jour du lancement ; chaque dépôt, une trajectoire alignée sur la
période et des critères que la période permet. Cas ajoutés au tableau :

| Cas | Ce que fait `kb trend-report` |
|---|---|
| Base sans aucune fenêtre (`latest_window` nul) | Avertissement, sortie en 0, rien d'écrit |
| Base plus ancienne que le registre (`latest_window` < `after`) | Avertissement avec les deux dates, sortie en 0, rien d'écrit |
| Réponse qui contredit la demande ou elle-même | Code 1, rien d'écrit ; le refus cite la place et le contrôle, jamais une valeur |
| Fichier écrit, registre non mis à jour (disque, SIGTERM) | Code 1 (143 sur SIGTERM), fichier gardé ; le compte rendu suivant reprend ces fenêtres |

Deux lancements qui se chevauchent ajoutent chacun leur entrée à la liste lue au début : le dernier
écrit l'emporte, comme pour le coffre (`post/vault_files.py`).

Le nom `tendances` est réservé sous `veille/` (`TRENDS_DIR_NAME` dans `core/config.py`, comme
`TOPS_DIR_NAME`, `:283`) : aucun sujet de `DIGEST_SUBJECTS` ne peut le prendre. Comme chaque commande,
`kb trend-report` sort avec un code nommé, s'arrête sur SIGTERM (règle 6 de `poc.md`) et reçoit
l'environnement de `read_environment` (règle 2).

## Période

- Les fenêtres postérieures à la dernière fenêtre du compte rendu précédent, jusqu'à la plus
  récente en base.
- **Premier compte rendu** : les 4 dernières fenêtres ; « nouveau » n'est pas évalué, et le fichier
  le dit.
- **Plafond** : `GH_ARCHIVE_MAX_CATCH_UP_WINDOWS` (15, `core/config.py:84`) ; au-delà, les plus
  récentes, et le fichier l'écrit (`windows_capped`).
- **Fenêtres manquantes** listées (`missing_windows`) ; la trajectoire montre le trou.
- Une période de 1 ou 2 fenêtres est dite dans le fichier.

## Rang et critères

Les critères se calculent en code pur, sur les **étoiles seules** en v1 (les forks : « Hors v1 »).

- **Rang** : recalculé par `(stars_gained desc, repository_id asc)`, 30 premiers. C'est la définition
  de `star_rank` à la collecte (`etl/sources/gh_archive.py:76-78`) ; `GET /trends` rend ses lignes
  départagées par les forks (`database/reading.py:150`), qui n'entrent pas dans le rang des étoiles.
  Un dépôt sans étoile gagnée dans une fenêtre (entré par ses forks) n'est dans aucun top.
- **Durable** : dans le top 30 de deux fenêtres **sans jour commun**, lues sur la période et les 2
  fenêtres qui la précèdent, et dans le top d'au moins une fenêtre de la période. Deux fenêtres de
  3 jours finissant à D et D+2 partagent un jour ; D et D+3, non.
- **Nouveau** : absent du top dans les fenêtres du compte rendu précédent. Non évalué au premier
  compte rendu, ni si toutes les fenêtres précédentes manquent.
- **En accélération** : lu sur la **dernière suite** de fenêtres où le dépôt est dans le top
  (décision A de Sabine, 30/10) : au moins deux rangs, chacun meilleur que le précédent, et 5 rangs
  gagnés au moins sur la suite. Un écart de moins de 5 rangs est « stable ». Une fenêtre où le dépôt
  est hors du top rompt la suite, qui repart ; une fenêtre manquante est sautée. Un dépôt hors du top
  à la dernière fenêtre présente n'est donc pas en accélération (sa suite repart, vide).
- **Candidats** : 60 au plus ; d'abord ceux qui remplissent un critère, puis par meilleur pic (le
  meilleur rang atteint, départagé par `repository_id`).
- **Seuils** (2 jours actifs, 5 rangs) : revus sur les premiers comptes rendus réels (#370).

**Le compte rendu factuel** (#366, et quand le choix échoue) affiche les dépôts qui remplissent au
moins un critère, chacun avec sa trajectoire et ses critères. Dès qu'un dépôt du tableau est durable,
une phrase sous le tableau rappelle la règle : il n'affiche que la période, pas ses 2
fenêtres de recul.

## Fiche légère

Lue sur GitHub pour chaque candidat, avant le choix (#367), jamais gardée :

- licence, ou « aucune licence reconnue par GitHub » ;
- date de création, langage, topics (`[a-z0-9-]{1,50}`, 20 au plus envoyés au modèle) ;
- étoiles totales, lues au moment du compte rendu ;
- prudence : créé il y a moins de 7 jours ; aucune licence reconnue par GitHub ;
- l'URL du dépôt est construite depuis son nom, jamais lue dans une réponse.

Un `id` GitHub différent du `repository_id` de `trend` écarte le candidat (dépôt renommé ou
remplacé).

## Contrats

### Demande

`POST /trend-reports` : `{"after": "AAAA-MM-JJ" | null, "previous_first_window": "AAAA-MM-JJ" | null}`.
`after` est la dernière fenêtre du compte rendu précédent, `previous_first_window` sa première ; les
deux sont nuls ensemble (premier compte rendu) ou renseignés ensemble. 422 : un champ en trop, une
demande incohérente, un écart de plus de 15 fenêtres. 413 `content_too_large` : un corps de plus de
1 024 octets, avant la clé, comme pour `POST /digests` ([fiches-veille.md](fiches-veille.md),
« Demande »).

Depuis #366 (`docs/api/openapi-ia.json`, version 0.5.0) : les deux champs sont obligatoires, et un
jour s'écrit `AAAA-MM-JJ` seulement (la garde `WrittenDay` d'`items.py`, celle de `GET /trends`). Le
refus rend `{"error": "invalid_parameter", "parameters": [...]}` : le nom du champ refusé, `body`
pour un champ en trop ou un contrôle croisé (un seul nul, ordre inversé, plus de 15 fenêtres).

### Choix

Consigne `select-trends-1`, une constante (règle 8 de `poc.md`). Message utilisateur : un JSON
encodé, `watch_subjects` (les sujets de `DIGEST_SUBJECTS` et leur définition) et `candidates[]`
(`ref`, `repository`, description, topics, langage, critères calculés, pic, trajectoire (rang par
fenêtre)). « Direction », qui n'était définie nulle part, est remplacée par la trajectoire
(décision de Sabine du 01/11, Q2 du plan de #368) : elle porte décollage, pic et recul.

Sortie stricte : `{"choices": [{"ref", "criteria", "watch_subjects"}]}`, où `ref` est un des `ref`
envoyés, `criteria` ⊂ {`durable`, `new`, `accelerating`, `watch_subject`} et chaque sujet ∈
`DIGEST_SUBJECTS`. Le code revérifie : 5 choix au plus ; un critère 1 à 3 annoncé est un critère
calculé ; `watch_subject` va avec au moins un sujet. Zéro choix est permis. Un contrôle refusé
déclenche une relance avec rappel ; l'état de contrôle nouveau est `criterion` (dans toutes les
tables de rappels). Après la relance, le choix est en échec (« Défenses et échecs »). Les états
de contrôle, leur ordre et ce que chacun refuse sont dans « Ce que rend #368 ».

### Rédaction

Consigne `write-trends-1`, **un appel par dépôt choisi**. Entrée : son `ref`, son nom sans le login
du propriétaire (`name`), son langage, sa licence, ses topics (les 20 envoyés au choix), ses critères,
les seuls sujets de la veille qu'il porte avec leur définition, sa description (500 caractères) et son
README nettoyé, coupé à 4 000 caractères, `null` quand GitHub n'en donne pas (décision de Sabine du
08/11 : un README réduit au mot « absent » pourrait passer la fidélité). Ni étoiles, ni dates, ni
prudences : le code les écrit lui-même, et ces nombres feraient retirer les textes par la règle des
nombres ; le nom sans le login, par minimisation (tranché par time-knight le 08/11).

Sortie : `{"repositories": [{"ref", "sector", "watch_link", "readme_summary", "promise"}]}`, chaque
texte de la forme `{"text", "facts"}` :

| Texte | Ce qu'il dit | Faits cherchés dans |
|---|---|---|
| `sector` | le secteur du dépôt | les topics |
| `watch_link` | le lien avec un sujet de la veille | la définition du sujet |
| `readme_summary` | un résumé du README, attribué à l'auteur, tronqué | le README (au moins un fait) |
| `promise` | ce que le dépôt promet | le README ou la description (au moins un fait) |

Ni commande ni bloc de code en sortie ; une version récente du dépôt n'est pas un fait retenu
(décision de Sabine, 29/10, 16:53). Bornes de longueur vérifiées par le code : `sector` 120 caractères,
`watch_link` 300, `readme_summary` 400, `promise` 200 (`core/config.py`), 0 à 5 faits par texte, au
moins un pour `readme_summary` et `promise`, chacun de 3 à 120 caractères. Un texte vide sans fait est
permis, et un texte sans lettre ni chiffre compte pour vide (`is_empty`) : il dit qu'il n'y a rien à dire, n'est ni écrit ni retiré (décision de Sabine du 08/11, qui
relâche la borne de l'architecte du 29/10, « textes jamais vides », conformément à l'issue).

**Fidélité**, par `normalize` et `is_found` (`ai_api/stages/fidelity.py:153,291`) : chaque fait est
cherché dans son texte et dans la seule source de son texte ; `to_searched_text` prend la longueur
coupée (4 000) en paramètre ; le masque `[email]` est retiré des textes cherchés, avec `[url]` et
`@user`, pour tous les appelants (un masque de K-B n'est jamais la source d'un fait ; effet nul sur les
fiches, que `watch_items.py` ne masque pas par `[email]`) ; `is_disguised` s'applique ; un nombre écrit
doit être un fait déclaré et trouvé.

**Contrôles de la sortie** (`ai_api/stages/trend_writing.py`), dans l'ordre des fiches. La sortie
entière est refusée, puis relancée une fois avec son rappel : un dépôt de plus ou de moins (`schema`),
un `ref` autre que celui envoyé (`item_id`), un lien, une image ou une balise (`MARKUP`,
`ai_api/stages/writing.py`), un accent grave, `~~~` ou un motif de commande (`markup`). Le motif de
commande : un tube vers un shell (`| sh`, `| bash`, `| zsh`, `| iex`), `Invoke-Expression`, `sudo`,
`npx`, `curl` ou `wget` suivis d'une option, un gestionnaire qui installe (`pip`, `pip3`, `pipx`, `npm`,
`pnpm`, `yarn`, `brew`, `apt`, `apt-get`, `cargo`, `gem`, `uv` suivis de `install`, `add` ou `i`),
`go install` ou `go get`, `docker run` ou `docker pull`, `git clone`, `$(` et `&&`. Le nom d'un
programme seul reste de la prose (« développé en Go », « un client comme curl », « publié sur npm »).

Puis chaque texte, son premier refus le retire (`texts_removed`, codes sur le span) :

| Ordre | Refus | Code |
|---|---|---|
| 1 | longueur, nombre de faits, fait trop court ou trop long, texte vide avec un fait | `out_of_bounds` |
| 2 | texte écrit sans source : `sector` sans topic, `watch_link` sans sujet, `readme_summary` sans README, `promise` sans README ni description | `no_source` |
| 3 | un fait introuvable dans son texte ou dans sa source (une valeur sans lettre ni chiffre l'est toujours) | `fact_not_found:<position>` |
| 4 | une CVE ou une GHSA dans le texte | `identifier_from_free_text` |
| 5 | un chiffre qui reste une fois retirés les faits trouvés (NFKC : `²`, `３` sont des chiffres) | `undeclared_number` |
| 6 | un caractère qui cache ou maquille le texte | `disguised_text` |

### Réponse

`request_id`, `model`, `period` (fenêtres, `missing_windows`, `windows_capped`), `chosen[]`
(trajectoire, faits du code, textes gardés, `texts_removed`) et les compteurs de candidats (lus,
écartés par motif). **Le code rend les faits** : rangs, critères, licence, dates, étoiles totales,
prudence, URL. Le modèle n'écrit que les 4 textes.

**Ce que rend #366**, le compte rendu factuel, sans GitHub ni modèle :

| Champ | Contenu |
|---|---|
| `request_id` | celui de l'en-tête `X-Request-ID` |
| `model` | `null` : aucun modèle n'a choisi |
| `period.first_report` | vrai si `after` est nul |
| `period.windows` | les fenêtres du compte rendu, de la plus ancienne à la plus récente, manquantes comprises ; vide si aucune n'est postérieure à `after` |
| `period.missing_windows` | celles que la base n'a pas |
| `period.windows_capped` | des fenêtres plus anciennes laissées de côté (plafond de 15) |
| `period.new_evaluated` | faux au premier compte rendu, et si toutes les fenêtres du précédent manquent |
| `period.latest_window` | la plus récente en base, `null` si elle n'en a aucune ; antérieure à `after` si la base a été restaurée |
| `repositories[]` | ceux qui remplissent au moins un critère, par meilleur rang puis `repository_id` : `repository_id`, `repository_name` (celui de la fenêtre la plus récente), `criteria` (`durable`, `new`, `accelerating`, dans cet ordre), `best_rank`, `trajectory[]` |
| `repositories[].trajectory[]` | un point par fenêtre de la période : `window_end`, `state` (`top`, `out_of_top`, `missing`), `rank` et `stars_gained` dans le top seulement |
| `repositories_dropped` | ceux qui remplissent un critère, écartés : leur nom vaut `.` ou contient `..`, et irait dans un chemin |

Ses erreurs d'amont sont celles de l'API de données : 502 (`data_api_invalid_response`,
`data_api_unauthorized`, `data_api_unavailable`), 503 (`data_api_rate_limited`), 504
(`data_api_timeout`). S'y ajoutent celles de l'accès, comme pour `POST /digests`
([fiches-veille.md](fiches-veille.md), « Accès ») : la route s'ouvre au seul client `KB_TREND_REPORT`
(403 `client_not_allowed` pour un autre), une demande à la fois (429 `request_already_running`), 20 par
24 h glissantes (429 `rate_limit_exceeded`). Les lectures sont 32 au
plus (la plus récente, puis la période, ses 2 fenêtres de recul et celles du compte rendu précédent,
chacune une fois), sous `TREND_REPORT_REQUEST_TIMEOUT_SECONDS` (60 s, `core/config.py` ; 200 s
depuis #368). Les
candidats (`select_candidates`, `ai_api/trajectories.py`) servent depuis #367, qui lit leur fiche sur
GitHub.

**Ce que rend #367** (version 0.6.0 de `docs/api/openapi-ia.json`) : le compte rendu de #366, plus la
fiche GitHub de chaque candidat, lue par l'API IA après les fenêtres et avant tout choix du modèle,
sans être gardée. Les candidats sont les trajectoires de la période dont le nom peut aller dans un
chemin (`is_repository_name`), qu'elles remplissent un critère ou non : 60 au plus, ceux qui
remplissent un critère d'abord. Le fichier du coffre gagne alors une ligne (ci-dessous) ; les faits y
sont écrits depuis (« Les faits dans le fichier »).

| Champ | Contenu |
|---|---|
| `repositories[].facts` | la fiche d'un candidat lu ; `null` pour un dépôt qui remplit un critère sans être candidat (au-delà des 60) |
| `facts.license` | l'identifiant SPDX (`license.spdx_id`) ; `null` quand `license` est nul, ou `spdx_id` nul ou `NOASSERTION` : aucune licence reconnue par GitHub |
| `facts.created_at` | la date de création, en UTC |
| `facts.language` | le langage, ou `null` |
| `facts.topics` | tels que lus, chacun `[a-z0-9-]{1,50}`, 100 au plus (20 au plus envoyés au modèle par #368) |
| `facts.stars_total` | les étoiles totales (`stargazers_count`), lues au moment du compte rendu |
| `facts.cautions` | `created_recently` (créé moins de 7 jours avant l'heure de la demande, `TREND_RECENT_REPOSITORY_DAYS` ; à 7 jours pile, non), puis `no_license` |
| `candidates.selected` | les candidats dont la fiche est demandée ; `read` plus la somme de `dropped` |
| `candidates.read` | ceux dont la fiche est lue |
| `candidates.dropped` | ceux que GitHub écarte, par motif : `not_found` (404, 410), `unavailable_for_legal_reasons` (451), `moved` (une redirection, non suivie), `id_mismatch` (un autre dépôt sous ce nom), `forbidden` (un 403 qui n'est pas une limite) |

Un candidat écarté **sort de `repositories[]`** : son nom peut désigner désormais un autre dépôt, et
le coffre en ferait un lien. `kb` relit les compteurs par un schéma fermé, refuse ceux qui ne
s'additionnent pas, et écrit, seulement si au moins un candidat est écarté : « Candidats écartés par
GitHub : n (introuvables : …, bloqués : …, renommés ou déplacés : …, remplacés : …, refusés : …) »,
les motifs à zéro omis. Sans écarté, le fichier est celui de #366. L'URL d'un dépôt reste construite
par `kb` depuis son nom. Ses erreurs : celles de l'API de données et celles de GitHub (« Défenses et
échecs »).

**Ce que rend #368** (version 0.7.0 de `docs/api/openapi-ia.json`) : le compte rendu de #367, plus le
choix du modèle parmi les candidats lus (`ai_api/stages/trend_selection.py`), sous l'échéance de la
demande, passée à 200 s (`TREND_REPORT_REQUEST_TIMEOUT_SECONDS`, comme `POST /digests` : sous les
240 s de `kb` et de l'ingress d'ACA). Aucun candidat lu : aucun appel, ni choix ni échec.

| Champ | Contenu |
|---|---|
| `model` | le nom du déploiement quand le choix est fait, zéro choisi compris ; `null` si le choix a échoué ou si aucun candidat n'est lu |
| `choice_failure` | l'état `llm_*` d'un choix en échec ; `null` sinon. Le compte rendu reste factuel (`repositories[]` inchangé) |
| `chosen[]` | 5 au plus, dans l'ordre du modèle : `repository_id`, `repository_name`, `criteria` (annoncés et revérifiés, dans l'ordre `durable`, `new`, `accelerating`, `watch_subject`), `watch_subjects` (avec `watch_subject` seulement, dans l'ordre de `DIGEST_SUBJECTS`), `best_rank`, `trajectory[]`, `facts`. Un choisi par `watch_subject` seul peut ne pas être dans `repositories[]` : d'où son nom et ses faits ici |

Le message envoyé : `watch_subjects`, puis `windows` une fois (`window_end`, `missing`), puis un
objet par candidat lu, dans l'ordre des candidats : `ref` (`c1` … `c60`, le seul identifiant d'un
candidat dans les spans), `repository`, `description` (nettoyée par `ai_api/repository_texts.py`,
500 caractères au plus, `null` si GitHub n'en donne pas), `topics` (les 20 premiers), `language`,
`criteria` (calculés), `best_rank` et `ranks`, alignés sur `windows` (un rang, ou `null` hors du top
et pour une fenêtre manquante). Au plafond (60 candidats, descriptions de 500 caractères, 20 topics
de 50, 15 fenêtres), le message mesure 116 323 caractères (`tests/ai_api/test_trend_selection.py`).

La sortie est relue par un modèle Pydantic fermé (`extra="forbid"`), `choices` borné à 5 ; le schéma
envoyé, écrit à la main, porte les `enum` (`ref` envoyés, les 4 critères, les sujets) et pas de
`maxItems`. Puis le code revérifie, dans l'ordre des contrôles des fiches
([fiches-veille.md](fiches-veille.md), « Contrôles ») :

| Contrôle | Refuse | `failed_check` |
|---|---|---|
| Schéma | plus de 5 choix, un champ en trop, un type faux | `schema` |
| Sujets | un sujet hors de `DIGEST_SUBJECTS`, ou deux fois pour un dépôt | `subject` |
| `ref` | un `ref` non envoyé, ou deux fois | `item_id` |
| Critères | aucun critère ; un critère deux fois ou hors des 4 ; `durable`, `new` ou `accelerating` non calculé pour ce candidat ; `watch_subject` sans sujet, ou des sujets sans `watch_subject` | `criterion` |

Chaque refus déclenche une relance avec le rappel de son contrôle (`SELECTION_RETRY_REMINDERS`) ;
refusé deux fois, le choix est en échec `llm_invalid_output`. Avant l'appel, une échéance qui ne
laisse plus `MIN_SECONDS_FOR_LLM_REQUEST` n'envoie rien : échec `llm_timeout`. Tout échec du choix
rend 200, le compte rendu factuel et l'état ; les erreurs de la route ne changent pas.

`kb` relit `model`, `choice_failure` et `chosen[]` (nom, critères, sujets, faits) par un schéma fermé, et
refuse une réponse qui se contredit : un modèle et un échec ensemble, des choisis avec un échec ou
sans modèle, un choix ou un échec sans candidat lu, ni l'un ni l'autre avec des candidats lus, un
choisi deux fois, des critères hors d'ordre, `new` non évalué, un critère 1 à 3 absent de ce dépôt
dans `repositories[]`, `watch_subject` sans sujet ou l'inverse, des sujets hors de `DIGEST_SUBJECTS`
ou hors d'ordre. Un choix en échec est journalisé en avertissement (l'état et le `request_id`,
jamais un nom) ; la sortie standard ne change pas. Le registre note `model` et `choice_made`.

Le fichier du coffre gagne une section « Choisis par le modèle », avant « Dépôts qui ressortent »
(décision de Sabine du 31/10, Q1 (a)), et `choice_failure` dans son front matter :

- choix fait : « <modèle> en a retenu n sur m candidats : », puis une ligne par choisi,
  `- <https://github.com/owner/repo> : <critères> ; sujet de la veille (a, b)` ;
- zéro choisi : « <modèle> n'en a retenu aucun sur m candidats. » ;
- échec : « Choix non fait : <raison>. », une phrase par état ;
- aucun candidat lu : « Choix non fait : aucun candidat lu. ».

#369 y ajoute les textes sous chaque dépôt (« Ce que rend #369 », ci-dessous).

**Les faits dans le fichier.** `kb` relit `facts` par un schéma fermé et les écrit :

- sous chaque choisi, une ligne : date de création, langage, licence, étoiles totales, topics
  (`MAX_TOPICS_FOR_SELECTION` au plus), puis la prudence s'il y en a une ; un fait que GitHub ne donne
  pas est omis ;
- dans « Dépôts qui ressortent », trois colonnes : « Créé le », « Étoiles totales », « Prudence » ;
  `—` pour un dépôt sans fiche, au-delà de `TREND_MAX_CANDIDATES`.

Le langage et la licence passent par `neutralize_digest_text`. `kb` refuse des faits qui se
contredisent : prudences hors d'ordre, `no_license` sans licence nulle ou l'inverse, faits d'un choisi
autres que ceux du tableau. Les étoiles gagnées restent absentes du fichier : elles viennent de
l'échantillon de GH Archive (« Limite de GH Archive »).

**Ce que rend #369** (version 0.12.0 de `docs/api/openapi-ia.json`) : le compte rendu de #368, plus
le README de chaque choisi, lu sur GitHub entre le choix et la rédaction, et les textes que le modèle
en écrit (« Rédaction »). Chaque choisi gagne :

| Champ | Contenu |
|---|---|
| `chosen[].readme` | `read` ; `cut` (coupé à 4 000 caractères une fois nettoyé) ; `absent` (404, 410, ou vide une fois nettoyé) ; `refused` (un 403 qui n'est pas une limite, un 451, une redirection) ; `null` quand il n'est pas lu (GitHub en échec, ou l'échéance avant lui) |
| `chosen[].texts` | `sector`, `watch_link`, `readme_summary`, `promise`, chacun `null` quand il est vide ou retiré ; `null` en entier quand la rédaction n'est pas faite, avec `writing_failure` |
| `chosen[].texts_removed` | les textes retirés par les contrôles, dans l'ordre `sector`, `watch_link`, `readme_summary`, `promise` |
| `chosen[].writing_failure` | l'état `llm_*` de l'appel, ou `github_*` de GitHub sur un README, après quoi aucun README ne part au modèle ; `null` sinon. Les faits restent |

Un seul champ d'échec porte les deux familles d'états, disjointes par leur préfixe : une seule ligne
dans le fichier, un seul contrôle croisé dans `kb`. Les `ref` (`c1`…) restent ceux du choix.

**Les README.** `GET /repos/{owner}/{repo}/readme`, en brut (`Accept: application/vnd.github.raw+json`),
tous lus avant la première rédaction, en série, dans l'ordre du modèle, sous le budget et le compteur
de refus des fiches. Seule la tête est lue, 65 536 octets (`MAX_GITHUB_README_BYTES`), le reste jamais
téléchargé, le flux fermé : à 4 octets par caractère au plus, elle dépasse la coupe brute du nettoyage
(4 × 4 000 caractères), qui la recoupe et retire le mot entamé. Décodé en UTF-8, un caractère coupé
remplacé. Un 200 servi en `application/json` (la forme base64, comparée exactement, paramètres
retirés) est refusé : `github_invalid_response`. Avant chaque README, une échéance qui ne laisse plus
le temps d'un appel au modèle arrête la lecture : les choisis non lus prennent `llm_timeout`.

**`kb`** relit `readme`, `texts`, `texts_removed` et `writing_failure` par un schéma fermé : chaque
texte borné comme dans l'API IA, sans caractère des catégories Cf (sauf U+200D, le liant des emoji),
Co ni Cn. Il refuse une réponse qui se contredit : des textes non écrits sans échec, ou écrits avec
un échec, des textes retirés avec un échec, hors d'ordre, deux fois ou encore écrits, un README non lu
sans échec, un résumé sans README (`absent`, `refused`), un lien avec la veille sans sujet, un secteur
sans topic. Un refus cite la place et le contrôle, jamais une valeur. Une rédaction en échec est
journalisée en avertissement, `writing of chosen.<n> not made: <état>, request_id <id>`, jamais un
nom ; la sortie standard ne change pas.

Le fichier gagne, sous la ligne des faits de chaque choisi, une ligne par texte, indentée de 2 espaces
(décision de Sabine du 08/11), chaque texte passé par `neutralize_digest_text` :

- `Secteur : …`, `Lien avec la veille : …`, `D'après son README : …` (`D'après le début de son
  README : …` quand il est coupé), `Promesse : …` ;
- un texte retiré : `<Étiquette> : non retenu par les contrôles.` ; un texte vide : pas de ligne ;
- `README : absent.` ou `README : non servi par GitHub.` à la place de la ligne du résumé, quel que
  soit le texte rendu ;
- une rédaction en échec : la seule ligne `Textes non écrits : <raison>.`, les raisons du choix pour un
  état `llm_*`, et pour GitHub : « GitHub indisponible », « GitHub n'a pas répondu à temps », « le quota
  de GitHub est atteint », « GitHub a refusé le jeton », « GitHub a refusé 3 lectures », « la réponse de
  GitHub n'a pas passé les contrôles ».

## Défenses et échecs

**Avant l'envoi au modèle**, en plus des défenses de [fiches-veille.md](fiches-veille.md)
(« Injection d'instructions ») : commentaires HTML retirés ; caractères des catégories Unicode Cf,
Co, Cs et Cc retirés, sauf le saut de ligne ; sélecteurs de variante et étiquettes Unicode retirés ;
images et badges (en ligne ou par référence), balises HTML et blocs de code délimités (`` ``` `` ou
`~~~`) retirés, un bloc indenté de 4 espaces gardé (limite ci-dessous) ; toute URL devient `[url]`, tout `@login`
devient `@user`, toute adresse mail devient `[email]` ; chaque texte est coupé. Les corps lus sur
GitHub sont bornés avant d'être nettoyés (un README peut atteindre 100 Mo chez GitHub). Le texte d'un
dépôt n'entre que dans le message utilisateur, jamais dans la consigne (règle 8 de `poc.md`).

**Sortie de la rédaction.**

| Ce que le code trouve | Ce qu'il fait |
|---|---|
| `ref` faux, pas exactement un dépôt, lien, image, balise (`MARKUP`, `ai_api/stages/writing.py`), accent grave, `~~~`, motif de commande | refuse la sortie entière du dépôt (relancée une fois) |
| borne dépassée, texte sans source, fait introuvable, CVE ou GHSA tirée d'un texte libre, nombre non déclaré, texte maquillé | retire ce texte seul, et le fichier dit « non retenu par les contrôles » |

**Dans le coffre** : chaque texte est échappé par `neutralize_digest_text` (`post/digest_sheets.py:187`),
déplacé dans `post/vault_files.py` pour les deux écrivains du coffre (#365). Rendu déterministe.

**GitHub.**

| Réponse | Ce que fait l'API IA |
|---|---|
| 404, 410, 451, toute redirection (301, 302, 307…) | candidat écarté et compté (une redirection n'est pas suivie en v1 : `core/outbound.py` ne suit aucune redirection ; c'est un écart à la recommandation de GitHub, et un dépôt transféré est compté) |
| `id` ≠ `repository_id` | candidat écarté et compté |
| 401 | 502 `github_unauthorized` |
| tout 429 ; un 403 **de limite** : `x-ratelimit-remaining: 0`, un en-tête `retry-after`, ou un message qui contient « rate limit » ou « abuse » (sans tenir compte de la casse) | plus aucune requête ; 503 `github_rate_limited` avec `Retry-After` : l'en-tête `retry-after` ; sinon, si `x-ratelimit-remaining` vaut 0, le reset moins l'heure de la demande, 60 s au moins ; sinon 60 s ; 3 600 s au plus (`MAX_GITHUB_RETRY_AFTER_SECONDS`), un `retry-after` trop long à lire compris |
| tout autre 403 | candidat écarté et compté `forbidden` ; au 3e d'un même compte rendu (`GITHUB_MAX_FORBIDDEN_PER_REPORT`), plus aucune requête : 502 `github_forbidden`, sans `Retry-After` (décision de Sabine du 31/10, Q1 (b)) |
| 5xx | une relance, sans attente, puis 502 `github_unavailable` |
| connexion impossible ; budget de 70 requêtes épuisé | 502 `github_unavailable` |
| délai ou échéance dépassés | 504 `github_timeout` |
| corps au-delà de `MAX_GITHUB_REPOSITORY_BYTES`, illisible ou hors schéma ; tout autre statut (204, 400, 422…) | 502 `github_invalid_response` |

Pour un README (#369), les mêmes statuts, avec ces différences :

| Réponse | Ce que fait l'API IA |
|---|---|
| 200 | sa tête lue (« Ce que rend #369 ») ; servi en `application/json` : `github_invalid_response` |
| 404, 410 | `readme` `absent`, le dépôt reste choisi, sa rédaction se fait sans README |
| un 403 qui n'est pas une limite, 451, toute redirection | `readme` `refused`, de même ; le 403 compte parmi les 3 refus |
| toute erreur (401, limite, 5xx deux fois, délai, budget, 3e refus, réponse illisible) | 200 ; aucun README ne part au modèle ; chaque choisi porte l'état en `writing_failure`, ses faits gardés ; le span `read_readmes` en erreur ; le `Retry-After` d'une limite est perdu |

Toute erreur sur les fenêtres ou les fiches arrête le compte rendu : pas de compte rendu partiel. Une
erreur sur un README n'arrête que la rédaction (décision de Sabine du 08/11 : comme un choix en échec,
le compte rendu reste factuel ; « pas de compte rendu partiel » vaut pour les fiches) ; le choix déjà
payé est gardé, la période avance, et `kb` journalise l'état en avertissement. La route journalise
l'état et le statut HTTP d'une erreur qui arrête le compte rendu avec le `request_id`, jamais un nom
de dépôt ; `kb serve-ai` ne garde aucune ligne de requête de httpx2, qui porterait l'URL
`repos/<owner>/<repo>` (`commands/run_log.py`).

Requêtes en série, 70 au plus par compte rendu (`GITHUB_MAX_REQUESTS_PER_REPORT`, relances comprises,
comptées par le client : 60 fiches, 5 README et 5 relances), avec le `User-Agent` de K-B et
`X-GitHub-Api-Version`, chaque
délai de `HTTP_TIMEOUT_SECONDS` réduit par l'échéance de la demande, par un jeton *fine-grained* sans
permission, `KB_AI_GITHUB_TOKEN`, du même compte que celui de la collecte : `kb serve-ai` ne démarre
pas sans lui (`ExitCode.NOT_STARTED`), jamais en anonyme, ni avec un jeton *classic* (préfixe autre
que `github_pat_`). La limite de 5 000 requêtes par heure est celle du compte, partagée par ses
jetons (`docs/jeton-github.md`, mis à jour par #367).

**Modèle.** Un appel de choix, puis un appel de rédaction par dépôt choisi, une relance chacun, avec
`max_completion_tokens` et `MIN_SECONDS_FOR_LLM_REQUEST`.
- **Choix en échec** : compte rendu factuel (les dépôts qui remplissent un critère), avec « choix non
  fait » et la raison ; le registre le note ; la période avance (décision de Sabine, 29/10, ~19:45Z).
- **Rédaction en échec pour un dépôt** (dont un refus de Prompt Shields sur un README qui parle
  d'injection, [fiches-veille.md](fiches-veille.md), « Limite : un lot de classement en échec ») : les
  textes de ce dépôt seul sont retirés, ses faits restent (même isolement que
  `routers/digest_router.py:54-56`). Après un échec par 429, plus rien n'est envoyé ; sans le temps
  d'un appel, `llm_timeout`, sans requête (`find_skipped_state`, `ai_api/stage_calls.py`).
- Limite : un bloc de code indenté de 4 espaces n'est pas retiré du README (il faudrait un analyseur
  Markdown) ; en sortie restent le refus de l'accent grave et le motif de commande (décision de Sabine
  du 08/11).
- Limite : « une version récente n'est pas un fait retenu » et « prudence en faits, pas en verdicts »
  ne sont tenues que par la consigne ; un nombre écrit en lettres, « Installez X » en prose et un
  gestionnaire hors de la liste du motif (`conda`, `poetry`, `dnf`, `pacman`…) échappent aux contrôles
  (décision de Sabine du 08/11 ; le gestionnaire hors liste : tri de la revue du 08/11). Chaque texte
  est neutralisé dans le coffre (`post/vault_files.py`) : rien ne s'y exécute.
- Limite : `sudo` et `npx` suivis d'une espace sont refusés même en prose (« sans sudo ni droits
  root », « via npx ou pnpm ») : la sortie entière est refusée, relancée, puis la rédaction de ce
  dépôt échoue en `llm_invalid_output` si le texte revient. Le refus est fermé ; #370 en mesure la
  fréquence (tri de la revue du 08/11).
- Limite : le nettoyage d'un README coûte du temps sans contrôle de l'échéance pendant qu'il tourne
  (`URL` mesure 1,27 s sur 20 000 lettres, `ai_api/repository_texts.py`) ; et l'échéance n'est vérifiée
  qu'avant chaque README : un README lent peut finir en `github_timeout`, ce qui ne retire que les
  textes. Mesuré par #370.
- Limite : le type de média d'un README servi en brut n'est pas documenté par GitHub (recherche du
  08/11) ; seul `application/json` est refusé. Relevé par #370.
- Limite : le README est lu par le nom (`GET /repos/{owner}/{repo}/readme`, seule forme documentée
  par GitHub, recherche du 08/11), sans contrôle de l'`id` : un dépôt supprimé puis recréé sous ce nom
  entre sa fiche et son README (le choix les sépare, 200 s au plus, `TREND_REPORT_REQUEST_TIMEOUT_SECONDS`)
  donnerait le sien. Seul le titulaire du nom peut le faire, et il tient déjà le README ; une
  redirection reste refusée (tri de la revue du 08/11).
- Limite : le filtre de contenu d'Azure peut refuser une description ou un README qui parle de
  jailbreak (sujet `llm_security` de la veille).
- Limite : une description peut pousser son dépôt vers un choix par `watch_subject` (« idéal pour
  la sécurité des agents ») ; le code vérifie que le sujet est de la liste, pas que le dépôt en
  relève (comme un item qui oriente le classement entre deux sujets permis,
  [fiches-veille.md](fiches-veille.md), « Injection d'instructions »).
- Limite du masquage : une adresse part telle quelle quand elle est écrite avec `＠` pleine chasse
  (U+FF20) ou `﹫` (U+FE6B), avec une lettre suivie d'une marque combinante (accent en NFD, signe
  vocalique…), maquillée (`[at]`, « at », espaces autour du `@`), ou scindée autour de son `@` par
  un bloc de code, une image ou un badge, ou par une balise non fermée où tombe la coupe brute ;
  quand sa partie locale porte un autre caractère hors `\w.%+'-` (`&`…), ce qui précède ce caractère
  part ; un nom en texte libre aussi. Une adresse hors ASCII (`josé@exemple.fr`), avec une
  apostrophe (`o'brien@…`) ou sans point dans son domaine est masquée, comme un `x@y` qui n'en est
  pas une (`react@latest`). Après une coupe brute, le mot qu'elle entame est retiré.
- Limite : si GitHub prend presque toute l'échéance, le choix échoue en `llm_timeout` et le compte
  rendu reste factuel ; aucune réserve de temps n'est gardée pour le modèle. Mesuré par #370.
- Limite : le message au plafond mesure 116 323 caractères ; en jetons, ce n'est qu'une estimation,
  environ 39 000 à 3 caractères par jeton (supposé), davantage si un JSON fait de topics courts
  tourne plus près de 2,5. Un choix au plafond et sa relance font environ 80 000 jetons, sous le
  quota de 140 000 jetons par minute du déploiement (journal ADR, « gpt-6-luna est déployé… ») ; un
  `kb digest` lancé dans la même minute partage ce quota. Mesuré par #370.

**Traces.** Cinq spans (fenêtres, fiches, choix, README, rédaction), avec des comptes, des états et
des `ref` (le span des fenêtres, `read_trend_windows`, porte `k_b.windows.period`, `k_b.windows.read`,
`k_b.windows.missing`, `k_b.windows.capped`, `k_b.repositories.dropped` et `k_b.repositories.reported` :
les dépôts qui remplissent un critère, comptés sur les fenêtres, avant GitHub ; le span des fiches,
`read_repository_cards`, depuis #367 : `k_b.candidates.selected`, `k_b.candidates.read`,
`k_b.candidates.dropped.<motif>` (les écartés), `k_b.github.requests`, et l'état d'un échec ; le span
du choix, `select_trends`, depuis #368 : `k_b.descriptions.truncated`, `k_b.outcome`,
`k_b.choices.count`, `k_b.choices.refs` (les `ref` choisis, dans l'ordre du modèle) et l'état d'un
échec, avec sous lui le span `chat <modèle>` de chaque tentative ; depuis #369, le span des README,
`read_readmes` : `k_b.readmes.read` (servis par GitHub), `k_b.readmes.absent`, `k_b.readmes.refused`,
`k_b.readmes.skipped` (non lus, échéance ou après une erreur), `k_b.github.requests` et l'état d'un
échec ; puis un span `write_trend` par choisi : `k_b.ref`, `k_b.readme`, `k_b.outcome`,
`k_b.facts.checked`, `k_b.facts.found`, `k_b.texts.kept` (noms), `k_b.texts.removed`
(`texte:raison`), en erreur sans requête quand il n'est pas écrit, avec sous lui le span `chat` de
chaque tentative), jamais un nom de dépôt ni un `repository_id` (registre des traitements). Aucun nom
de dépôt dans les journaux.

**Métriques** (règle 4 de `poc.md`, décision de Sabine du 01/11, Q3 du plan de #368) : le type `Stage`
(`ai_api/stage_calls.py`) gagne `select`. L'appel du choix écrit une ligne `llm_call` sur la sortie
standard, comme un appel des fiches ([fiches-veille.md](fiches-veille.md), « Métriques »), qu'il
réussisse ou échoue, et ses mesures OpenTelemetry portent `k_b.stage=select` : `stage` `select`,
`subject` nul, `prompt_version` `select-trends-1`, `items_in` les candidats envoyés,
`items_truncated` les descriptions coupées ; `data_fetch_ms`, `items_capped` et
`items_dropped_before_writing_stage` nuls (les lectures sont mesurées dans leurs spans). Aucun
appel (aucun candidat lu, ou l'échéance avant l'envoi) : aucune ligne. Depuis #369, `Stage` gagne
`write_trends` : une ligne par rédaction envoyée, `subject` nul, `prompt_version` `write-trends-1`,
`items_in` 1, `items_truncated` 1 si le README ou la description est coupé, `facts_checked`,
`facts_found`, `claims_removed` (les textes retirés) ; une rédaction non envoyée n'écrit pas de ligne.
`FailedSubjectSchema.stage` de `POST /digests` a son propre type, `DigestStage` (`classify` ou
`write`) : l'OpenAPI n'y liste plus `select`.

**Contenu des appels sous `KB_TRACE_CONTENT`**, comme les fiches (décision D1 du 2026-10-27, précisée
le 28/10, #347 ; journal ADR, « Traces : le contenu des appels au modèle, sous réglage ») : le choix
et la rédaction appellent `trace_contents(llm_call, tracing=tracing)` après avoir jugé l'appel. Le
contenu (`owner/repo` au choix, le nom sans le login à la rédaction, description, topics, README
nettoyé, sortie du modèle) part vers Grafana Cloud
selon `KB_TRACE_CONTENT` : `none` par défaut, et tant que Grafana Labs n'a pas accusé réception du
DPA ; `anomalies` ; `all` en bac à sable seulement. Il n'est que dans le corps de l'enregistrement ;
les spans et leurs attributs restent sans nom de dépôt ni `repository_id`. Décision de Sabine du
2026-10-30 (~16:12Z), qui remplace le « jamais tracé » de la conception du 29/10.

## Ce qui le prouve

Les tests que portent #366 à #369 :

| Défense | Cas de test |
|---|---|
| Rang | une égalité au 30e rang départagée par les forks n'entre pas |
| Durable | faux pour un pic d'un jour et pour D et D+2 ; vrai pour D et D+3 |
| Accélération | 4 rangs contre 5 ; fenêtre manquante sautée ; fenêtre hors top = rupture |
| Période | premier compte rendu sans « nouveau » ; plafond ; aucune fenêtre nouvelle = aucun appel (faux clients qui comptent) |
| Registre et coffre | registre illisible → code 2, rien lancé ; fichier existant vu avant la demande → code 2 ; `tendances` réservé ; rendu déterministe et échappé |
| Demande | les bornes (422) ; un corps de plus de 1 024 octets, annoncé ou en flux (413) |
| GitHub | 301 non suivie ; `id` différent écarté ; plus de requête après un 403 de quota ; 403 nu ; taille bornée ; sans jeton, `kb serve-ai` ne démarre pas |
| Choix | description piégée absente des messages `system` ; dépôt inventé, critère faux, sujet hors liste, plus de 5 choix refusés ; choix en échec → compte rendu factuel écrit et noté au registre |
| Rédaction | README piégé absent des messages `system` ; README qui vise un autre dépôt ; commande, lien, accent grave refusés ; fait introuvable → texte retiré ; rédaction en échec → ses seuls textes retirés |
| Traces et journaux | spans sans nom de dépôt ni `repository_id` ; avec `KB_TRACE_CONTENT=none`, aucun enregistrement de contenu ; avec `all`, le contenu n'est que dans le corps de l'enregistrement |
| Couches | `tests/architecture/` : `AI_API_LAYERS`, `TRACED_FUNCTIONS`, environnement lu par `commands/environment.py` seul |

Aucun test n'appelle GitHub ni le modèle : réponses enregistrées, fixture tirée d'une vraie réponse.
L'essai réel de bout en bout est #370.

## Limite de GH Archive

Les comptes de `trend` sont un **échantillon** : environ 1 % des étoiles données sur GitHub, mesuré
le 29/10 ([specs-collecte.md](specs-collecte.md), « GH Archive sur BigQuery »). Le compte rendu le
dit, ne départage pas des rangs proches, et n'écrit jamais « étoiles gagnées » tirées de GH Archive
sans le dire.

## Tenue sur ACA

- **Tient tel quel** : tout ce qui vit dans l'API IA (sans état, réglée par variables
  d'environnement, API de données lue par son nom court en ingress interne, appels sortants vers
  GitHub, second jeton en secret, traces vers Grafana Cloud).
- **Ne tient pas seul** : le côté `kb` (lire le registre, écrire le coffre). C'est la question
  ouverte du journal ADR, « Où tourne `kb write-tops` en ligne », qui vaut déjà pour `kb digest` ; le
  compte rendu en hérite sans l'aggraver, puisque l'API IA reçoit les bornes de la période dans la
  demande.
- **À vérifier** : la durée de `POST /trend-reports` (70 requêtes GitHub au plus et les appels au
  modèle) face au délai de l'ingress d'ACA ; mesurée à l'essai réel (#370).

## Hors v1

Des pistes, sans décision :

- **Forks** : un filtre (`is_template` ou autre) à décider sur les premiers vrais tops.
- **Recomptage par GitHub** (top 100) : les totaux à la collecte, par GraphQL, sont #143.
- **« Propriétaire récent »** (`GET /users/{owner}`) : retiré de la v1, c'est la seule donnée sur une
  personne.
- **Planification** de `kb trend-report` : avec la mise en ligne.
- **Où `kb` écrit en ligne**, pour les trois sorties ensemble (tops, fiches, tendances), à comparer
  pour la décision commune du 08/11 :
  - un **coffre-dépôt GitHub** (idée de Sabine, 29/10) : `kb` pousse ses fiches dans un dépôt privé,
    qu'Obsidian et le web lisent ;
  - **Azure Blob Storage**, conteneur privé en UE, identité managée sans clé (job `kb` en écriture,
    front en lecture), noms stables, écrits une fois. Pratique courante pour ce qu'une machine écrit
    et qu'une appli lit : métadonnées en base, fichiers en stockage d'objets
    ([MLflow, backend store](https://mlflow.org/docs/latest/self-hosting/architecture/backend-store/),
    [artifact store](https://mlflow.org/docs/latest/self-hosting/architecture/artifact-store/)) ; pour
    ce que des humains éditent et publient, du Markdown dans un dépôt git
    ([Decap CMS](https://decapcms.org/features/developer/)). Le site statique `$web` de Blob n'accepte
    que la lecture anonyme publique
    ([FAQ](https://docs.azure.cn/en-us/storage/blobs/static-website-hosting-faq)) : pas pour K-B,
    privé ; un front lirait les blobs par identité managée, ou un site reconstruit à chaque fiche sur
    Azure Static Web Apps. Obsidian ne lit pas Blob : une synchronisation (`azcopy sync`) serait à
    prévoir ;
  - **Blob vers un dépôt GitHub** : pas de synchronisation native ; un workflow GitHub Actions
    planifié (« git scraping », [Willison](https://simonwillison.net/2020/Oct/9/git-scraping/)), connecté
    à Azure par OIDC sans mot de passe
    ([Microsoft Learn](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect)),
    lit Blob en lecture seule et commite s'il y a du nouveau.
- **Un agent** (actualité tech d'un dépôt, vérifier une promesse) : la v1 est une chaîne fixe.
- **Une interface web** pour lire les comptes rendus ; le registre passerait alors en table.

Hors de ce compte rendu, et ce n'est pas une piste : les **fiches de veille** partiront du `until`
de la fiche précédente, et leur rattrapage rejouera chaque créneau manqué (une requête par créneau,
sa fenêtre de 3 ou 4 jours, fiche datée du créneau), prévu pour le 08/11 (décision de Sabine du
2026-10-26, ~10:07Z et ~15:09Z, relayée par time-knight le 30/10).

## Sources

Pages de « Hors v1 », relevées par time-knight le 29/10/2026 (~19:40Z à ~19:55Z) :
[MLflow, backend store](https://mlflow.org/docs/latest/self-hosting/architecture/backend-store/) ;
[MLflow, artifact store](https://mlflow.org/docs/latest/self-hosting/architecture/artifact-store/) ;
[Decap CMS](https://decapcms.org/features/developer/) ;
[Azure, static website hosting FAQ](https://docs.azure.cn/en-us/storage/blobs/static-website-hosting-faq) ;
[Simon Willison, git scraping](https://simonwillison.net/2020/Oct/9/git-scraping/) ;
[Microsoft Learn, OpenID Connect depuis GitHub Actions](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect).
Conditions de GitHub et limite de GH Archive : sources dans [specs-collecte.md](specs-collecte.md).
