# Le site de K-B (`kb serve-web`)

Le site affiche la veille de K-B à sa seule opératrice, Sabine. Il est rendu par le serveur, avec FastAPI et
Jinja2, sans aucun JavaScript dans le navigateur. Il ne lit pas la base : il lit l'API de données par HTTP,
comme son client `WEB` (`KB_DATA_API_KEY_WEB`). Le paquet `src/k_b/web/` n'importe que `core` et `items`
(`tests/architecture/test_layers.py`).

## Pages

| Chemin | Page |
|---|---|
| `/` | « Quoi de neuf », le fil de veille (« Fil », ci-dessous) |
| `/items/<id>` | le détail d'un item du fil (« Détail », ci-dessous) |
| `/comptes-rendus`, `/comptes-rendus/<sujet>`, `/comptes-rendus/<sujet>/<jour>` | « Comptes rendus de veille », les sujets, puis le compte rendu d'un sujet (« Comptes rendus », ci-dessous) |
| `/comptes-rendus/<sujet>/<jour>/sources/<id>` | une source d'un compte rendu : la page de son item, ou « Source introuvable » |
| `/tendances` | « Dépôts qui ont le vent en poupe », les tendances d'une fenêtre (« Tendances », ci-dessous) |
| `/sources` | « Sources et conditions d'utilisation » |
| `/accessibilite` | « Accessibilité » |
| `/static/site.css`, `/static/favicon.svg` | la feuille de style et l'icône |
| `/health` | `{"status":"ok"}`, pour les sondes ; ni page ni donnée |

Une route inconnue rend la page 404 ; `/sources/` en est une (pas de redirection). Le site ne sert ni OpenAPI
ni `/docs`.

## Fil

`/` montre les items de cinq sortes, `paper`, `vulnerability`, `advisory`, `release` et `newsletter_article`,
jamais `zotero_entry` ni `clip`, par pages de 20, du plus récent au plus ancien (l'ordre de `GET /items`).
Chaque page fait un seul `GET /items` (`web/data_api_client.py`), avec `kind` toujours envoyé, `limit=20`,
`offset` et `since` ; `web/feed.py` lit le formulaire et bâtit les cartes, sans entrée ni sortie.

**Le formulaire** (GET, sans JavaScript) :

| Champ | Dans l'adresse | Règle |
|---|---|---|
| Rechercher | `q` | espaces autour retirées ; vide, aucune recherche ; 200 caractères au plus (la règle de `q` de l'API) ; un caractère de contrôle (catégorie Unicode `Cc`) est refusé, et la saisie réaffichée sans lui |
| Sortes | `kind`, répété | les cinq cases cochées par défaut ; aucune cochée vaut les cinq, ce que dit l'aide du groupe ; une autre valeur est refusée, sans appel à l'API |
| Depuis | `period` : `1`, `3`, `7` ou `date` | `1` par défaut (D3, Sabine, 2026-11-11) ; N jours donne minuit UTC du jour J−N : « 1 jour » prend hier et aujourd'hui |
| Date de début | `start`, `AAAA-MM-JJ` | lue seulement si `date` est cochée (D4 : le bouton radio fait foi), ce que dit son aide (WCAG 3.3.2) ; son propre minuit UTC ; un jour qui existe, lu par `WrittenDay` (`items.py`), le type des routes de l'API ; réaffichée seulement si c'est un jour (pas `2026-02-30`, #596), jamais brute ; refusée, le message des tendances (`write_day_refusal`, #617) |
| page | `page` | `[1-9][0-9]{0,2}`, 501 au plus (l'`offset` 10 000 de l'API) ; absente, la page 1 |

La route lit `request.query_params` brut, jamais des paramètres typés par FastAPI : un `page=abc` partirait
sinon dans le 422 JSON de FastAPI, qui recopie la valeur reçue. Limite : `q`, `period` ou `start` répété garde
sa dernière valeur, alors qu'une `page` répétée rend la 404 ; seule une adresse écrite à la main répète un
champ.

**La carte** d'un item donne, sur une ligne qui passe à la ligne sur un téléphone, sa sorte encadrée, sa date
au mois en lettres (`<time>`), ses identifiants et la pastille « Exploitée (KEV) » (lue dans `exploited` : une
faille, une alerte dont la CVE est au catalogue ; une faille retirée du catalogue n'a que la ligne « retirée du
catalogue le … », décision de Sabine du 2026-11-11) ; puis son titre et le lien vers la source, court et petit
comme les maquettes (« Lire sur arxiv.org ↗ »). Ce lien s'ouvre dans un nouvel onglet (`target="_blank"`,
`rel="noopener noreferrer"` : la page ouverte n'atteint ni la page de K-B ni son adresse), que son texte annonce,
en plus petit : « (en anglais, site externe, nouvel onglet) » ou, pour une newsletter, « (site externe, nouvel
onglet) » (Opquast 2025, règle 146 ; demande de Sabine du 2026-11-11, pour rester dans K-B). Les liens de
`/sources` font de même : tout lien vers un autre site s'écrit par la macro `external_link`
(`web/templates/links.html`), seule à poser `target="_blank"` (`tests/web/test_templates.py`) ; un lien du site ne
s'ouvre jamais ailleurs (règle 138). Une URL qui n'est pas en
`https` vers un hôte ne devient jamais un lien. Le titre mène au détail de l'item (« Détail ») ; il passe,
comme tout texte reçu, par `clean_received_text` (`web/received_text.py`). Une newsletter porte le nom que TLDR donne à son édition (`NEWSLETTER_NAME_BY_EDITION`, « TLDR AI »
comme les maquettes ; time-knight, 2026-11-11), « TLDR » et son identifiant d'API sinon.

**Les pages** : M = max(1, ⌈total ÷ 20⌉), 501 au plus ; la ligne des résultats donne le total, la page,
M et les 20 items par page (Opquast 13), les milliers groupés par une espace fine insécable (U+202F) comme dans
le tableau des tendances, par `write_count` (`web/french_dates.py`) : « 12 345 items » ; au-delà de 10 020 items, une phrase dit d'affiner
les filtres. Une page au-delà de M, ou hors de sa forme, rend la page 404. Les liens de page, des boutons
encadrés comme les maquettes, « Page suivante » à droite même quand la ligne se replie, gardent les filtres et mènent à la ligne des résultats (`#resultats`, décalée
du bord par `scroll-margin`) : l'autre page s'ouvre sur ses items (Sabine, 2026-11-11). Cette ligne porte
`tabindex="-1"` : en suivant l'ancre, le navigateur lui donne le focus (WHATWG, « Scrolling to a fragment » :
les étapes de focus sur la cible, le *viewport* sinon), et le clavier comme un lecteur d'écran repartent des
résultats (tranché par time-knight, deuxième revue de code ; non essayé dans un navigateur). Le formulaire envoyé
et « Élargir à 7 jours », une nouvelle recherche, s'ouvrent en haut de la page. Le fil vide propose « Élargir
à 7 jours ».

**Les erreurs** : un champ refusé par le site, ou `q` refusé par l'API (422 `invalid_parameter` sur `q`
seul), rend le fil en 422, sans liste, avec un résumé des erreurs et un message sous chaque champ, ouvert par
« Erreur. » : le mot dit l'erreur sans couleur (#590). Sans lui, seule la couleur séparait le message du libellé
au-dessus, `#7C2D12` et `#1C1E21`, 1,78:1 entre eux (RGAA 3.1, WCAG 1.4.1), et en couleurs forcées le message
prend la couleur du texte, comme le libellé (RGAA 11.10). Le résumé, sous son titre « Filtre à corriger », dit chaque message
sans ce mot. Il a l'encadré « Couleur signalée » de la planche « Charte graphique » (Sabine, 2026-11-22) : bordure
rouille (`--color-alert`), fond pêche pâle (`--color-alert-wash`), titre en rouille sombre (`--color-alert-deep`, 8,47:1
sur le fond), texte en brun brûlé (`--color-alert-ink`, 11,13:1), c'est-à-dire les puces, chaque message étant un lien,
souligné, en rouille sombre (8,47:1) ; l'anneau de
focus y a 6,70:1. Le mot est écrit dans les gabarits, jamais dans les messages de `web/feed.py`. Tout autre
échec de l'API (5xx, 429, 401, délai, réponse hors schéma, 422 sur un paramètre que le site construit) rend
la page 500, et le journal écrit `data_api_failed: <état> http_status=<n|-> request_id=<id>`, jamais `q`.

**Le client** de l'API (`web/data_api_client.py`) : 5 s de connexion, 30 s de lecture
(`WEB_DATA_API_READ_TIMEOUT_SECONDS`), 10 s d'écriture, 5 s d'attente du pool ; une échéance de 35 s vérifiée
entre deux morceaux du corps, borné à 1 Mo. Les 30 s couvrent le réveil de l'API à zéro réplique, 20 à 26 s
(#414). Limite : chaque délai borne une attente, et l'échéance ne se lit qu'entre deux morceaux ; rien n'est
borné avant le premier morceau du corps (#436). Une requête peut donc durer environ 70 s au pire : la
connexion et le pool, 30 s jusqu'aux en-têtes, puis 30 s jusqu'au premier morceau du corps. Il ne suit aucune redirection et
ne lit pas l'environnement. Une réponse est lue par un modèle fermé aux cinq sortes ; un champ que l'API
ajoute est ignoré. Limite : un seul item hors de ce modèle fait de toute la page une page 500, et le journal
ne dit pas lequel ; la collecte valide les items par les mêmes types d'`items.py`.

**Le réveil** : au démarrage, `kb serve-web` fait un `GET /health` de l'API de données dans un fil à part ;
l'API se réveille pendant que Sabine se connecte. Le journal donne l'état (`data API wake-up: health ok`, ou
l'état de l'échec), jamais l'URL. Risque accepté : après un repos, le premier affichage peut attendre
environ 50 s (le site, puis l'API) ; une API qui répond lentement retient la page jusqu'à environ 70 s
avant la page 500 (« Le client », ci-dessus). Pour réduire le risque : ce réveil, et ouvrir le site
quelques minutes avant l'oral, faisables avec nos droits. Une borne totale de la requête demanderait une
lecture asynchrone ou un fil à part : non faite (httpx2 ne change pas un délai en cours de lecture).

**Le poids** (D2, RGESN 6.1) : 3 requêtes au plus, la page, la feuille de style et l'icône, et 30 Ko
transférés, cache vide, gzip compris, mesurés sur 20 items de la fixture
(`test_the_screen_of_the_feed_holds_three_requests_and_30_kb_at_most`).

## Détail

`/items/<id>` (#564) montre un item des cinq sortes du fil, par `GET /items/{item_id}` de l'API de données, avec
la clé du client `WEB`. Maquettes du 09/11 : `Maquette-papier`, `Maquette-alerte` et `Maquette-faille`.

**L'identifiant** est lu en chaîne, jamais typé par FastAPI (sinon un 422 en JSON) : `[1-9][0-9]{0,18}`, en
chiffres ASCII, puis au plus 2⁶³ − 1, par `read_item_id` (`web/item_detail.py`), seule à porter cette forme
(#403 la changera seule pour un UUID). Hors de sa forme, la page 404, sans appel à l'API. Limite : Starlette
route sur le chemin décodé (spécification ASGI, `path`), si bien que `/items/%39` sert aussi l'item 9.

**La page**, un seul gabarit (`item.html`) dans l'ordre des maquettes : « ← Retour au fil » (vers `/`, sans les
filtres ; « ← Retour au compte rendu » pour un item atteint par une source, « Comptes rendus », ci-dessous) ; la sorte encadrée, les identifiants et les dates en `<time>` ; le titre en `h1` ; le bandeau ; les
faits en `<dl>` ; les textes sous des `h2` ; le lien vers la source, en bouton, par la macro `external_link`
(nouvel onglet annoncé, même texte que sur la carte). Aucun lien de la navigation n'est marqué courant.

| Sorte | Ligne du haut | Faits | Textes |
|---|---|---|---|
| papier | arXiv …, « Publié le », « dernière version arXiv le » | — | « Auteurs: » puis les noms dans l'ordre d'arXiv ; « Résumé » |
| faille | « Ajoutée au catalogue le », « modification vue par K-B le » | CVE, usage par des rançongiciels, éditeur, produit | « Description » |
| alerte | « Publiée le » | identifiant GitHub, CVE (« Aucune »), paquets touchés (« Aucun ») | — |
| *release* | dépôt, version, « Publiée le » | — | « Notes de version, texte brut », ou « Aucune note de version. » |
| newsletter | « TLDR AI », « édition du », n° (milliers groupés, `write_count`) | — | « Résumé » |

**Le bandeau** dit l'état en mots, la couleur ne fait que suivre (RGAA 3.1) ; seul un item au catalogue KEV prend
le style d'alerte. Il lit `exploited` et `withdrawn_at`, sans rien supposer :

| Item | Titre |
|---|---|
| faille au catalogue | Exploitée activement: oui |
| faille retirée | Retirée du catalogue le … (jamais « Exploitée », décision de Sabine du 2026-11-11) |
| alerte, `exploited` vrai | Entrée au catalogue KEV ; le texte dit qu'un retrait depuis ne se voit pas ici |
| alerte, faux | Absente du catalogue KEV |
| alerte, nul | Sans CVE |

**Les textes** : les notes d'une *release* sont du texte brut, échappé, jamais du Markdown rendu ni un lien
(D3 de #564, décision de Sabine du 2026-11-11) ; les retours à la ligne sont gardés (`white-space: pre-wrap`) et
les lignes vides séparent les paragraphes. Tout texte reçu passe d'abord par `clean_received_text` : sans
caractère de contrôle hors tabulation et retour à la ligne, sans non-caractère ni demi-paire isolée, `\r\n` et
`\r` ramenés à `\n` (RGAA 8.2). Le titre, le résumé, la description et les notes sont en `lang="en"`, comme
au fil (hypothèse : un texte en français serait mal marqué) ; l'éditeur et le produit d'une faille aussi.

**Les erreurs** : la page 404 pour un identifiant hors de sa forme, un 404 `item_not_found`, une entrée Zotero ou
un clip (le client n'en lit que la sorte : leur texte n'est jamais modélisé, montré ni journalisé). Tout autre
404 de l'API (`route_not_found`, un 404 sans JSON) et tout autre échec rendent la page 500, journalisée comme au
fil (`data_api_failed: …`), sans l'identifiant. Le journal des requêtes écrit `route=/items/{item_id}`.

**Le budget** (D4 de #564, RGESN 6.1) : 3 requêtes et 30 Ko transférés par écran, cache vide, gzip compris, le
résumé ou la description à sa borne de 5 000 caractères (`tests/web/test_item_page.py`). Hors budget : les notes
d'une *release* (125 000 caractères au plus) et les auteurs d'un papier (1 000 au plus), que l'API sert entiers.

**La preuve de bout en bout** (C17.3) : `tests/web/test_site_on_the_data_api.py` sert le site sur la vraie API
de données de la base de test, en mémoire : une date du fil refusée sous son champ, un filtre gardé, puis le
détail par le lien du titre d'une carte. Il tourne dans `uv run pytest`, donc en CI.

## Comptes rendus

`/comptes-rendus` (#724) montre les comptes rendus de veille que `kb digest` écrit le lundi et le jeudi (job
`caj-kb-digest-watch`, #423), par `GET /digests/{subject}` et `GET /digests/{subject}/days` de l'API de données,
avec la clé du client `WEB` (#560). Aucun écran n'est maquetté : la page suit la mise en page du détail et la
charte, sans couleur nouvelle. `web/digests.py` lit l'adresse et bâtit les pages, sans entrée ni sortie.

| Chemin | Page | Appels à l'API |
|---|---|---|
| `/comptes-rendus` | les 9 sujets, chacun une carte : son libellé en lien (`h2`), une ligne qui le décrit | 0 |
| `/comptes-rendus/<sujet>` | le compte rendu le plus récent du sujet | 2 |
| `/comptes-rendus/<sujet>/<AAAA-MM-JJ>` | le compte rendu de ce jour | 2 |
| `/comptes-rendus/<sujet>/<AAAA-MM-JJ>/sources/<id>` | la page de l'item de la source, ou « Source introuvable » | 2 |

**Les sujets** gardent leur code d'API dans l'adresse (`agent_frameworks`). Leur libellé et leur ligne, en
français, sont dans `SUBJECTS` (`web/digests.py`), dans l'ordre de `DIGEST_SUBJECTS`, tenus égaux par un test : un
sujet ajouté à `DIGEST_SUBJECTS` le fait échouer tant que le site ne le nomme pas. Corrections de Sabine du
2026-11-26 : « Vulnérabilités », « Frameworks agentiques », LLM gardé tel quel. La ligne est écrite pour le
site : les définitions de `DIGEST_SUBJECTS` sont celles que lit le modèle. Écartés : un code français par sujet
dans l'adresse (une seconde table à tenir) ; le dernier jour de chaque sujet sur l'index (9 appels par affichage,
RGESN) ; un formulaire de date, comme les tendances (le site ne sait pas quels jours existent : la liste des jours
le dit).

**L'adresse** est lue en chaînes, jamais typée par FastAPI (sinon un 422 en JSON) : le sujet parmi `SUBJECTS`, le
jour par `read_written_day` (`AAAA-MM-JJ`, un jour qui existe), le numéro de la source par `read_item_id`. Hors de
sa forme, la page 404, sans appel à l'API. Le journal des requêtes écrit le gabarit de la route
(`route=/comptes-rendus/{subject}/{day}`), jamais le sujet ni le jour.

**La page d'un compte rendu** (`digest.html`), dans l'ordre : « ← Tous les comptes rendus » ; « Compte rendu »
encadré et la fenêtre, du jour de `since` au jour de `until`, en `<time>` ; le libellé et le jour en `h1` ; le
bandeau « Compte rendu partiel » quand la lecture est coupée ; « Rédigé par le LLM (grand modèle de langage) … à
partir des items du fil. Chaque affirmation cite ses sources. », le modèle lu dans la réponse (`model`), jamais
écrit dans le site ; sous le `h2` « Affirmations », une liste numérotée dans l'ordre de la fiche, chaque
affirmation suivie de « Source: » ou « Sources: » et de la liste de ses sources dans l'ordre où elle les cite,
chacune un lien qui porte son titre, en `lang="en"` (hypothèse, comme au fil), la liste nommée par son « Sources: »
(`aria-labelledby`) ; sous le `h2` « Les jours du sujet », les 30 jours les plus récents, chacun un lien vers son compte rendu, le jour affiché marqué
`aria-current="page"`, sans lien. Au-delà de 30 jours, la liste le dit (« Les 30 jours les plus récents sur 45. »),
sans pagination : à deux comptes rendus par semaine, 30 jours en couvrent quinze. Aucun lien de la navigation n'est marqué courant, comme sur le détail d'un item ; l'index marque « Comptes rendus ».

Les sources sont sous leur affirmation : on lit l'affirmation et ce qui l'appuie au même endroit, au clavier et au
lecteur d'écran, sans aller-retour (écarté : les renvois numérotés de la fiche vers une liste en bas). Un seul lien
par source, vers son item ; le lien vers la page d'origine reste sur la page de l'item (écarté : deux liens par
source, jusqu'à 120 arrêts de Tab). Chaque lien d'une source ou d'un jour est une cible de 44 px par son
`padding` (Opquast 186), et un titre sans espace se coupe partout (320 px). Un lien de source ou de jour visité
prend l'ardoise de la charte (Opquast 141). Les titres des sources sont à 14 px, comme le lien d'une carte : ils
appuient l'affirmation, qui reste à la taille du texte.

**Le bandeau « Compte rendu partiel »** : l'API IA lit les sortes dans l'ordre de `WATCH_KINDS` (failles, alertes,
papiers, *releases*, articles de newsletters) et s'arrête à la coupe (`list_items`,
`ai_api/connectors/data_api_client.py`) ; `covered_after` est la date du premier item laissé de côté, borne exclue.
Le bandeau dit, chaque phrase seulement si elle nomme une sorte : la sorte coupée et le moment, à la seconde, après
lequel ses items sont lus ; les sortes qui la suivent, « n’ont pas été lus » ; celles qui la précèdent, « ont été
lus en entier » (« lues » si elles sont toutes au féminin). `since` est propre au sujet, `covered_after` est celle de
la lecture de tous les sujets : quand `covered_after` précède `since`, la sorte coupée est lue en entier dans la
fenêtre du sujet, et s'il ne manque rien au sujet (coupe sur la dernière sorte), aucun bandeau. `WatchKind` et
`WATCH_KINDS` sont passés d'`ai_api/watch_items.py` à `items.py` : le site n'importe que `core` et `items`.

**Les textes reçus** : une affirmation et un titre passent par `clean_received_text`, puis sont échappés ; une
balise ou une adresse dans un texte reste du texte, jamais un lien (OWASP LLM10). Une affirmation que le nettoyage
laisse vide se lit « Sans texte. », un titre « Sans titre » (sans `lang`).

**Le lien d'une source vers son item** (limite (d) de `GET /digests/{subject}`, `docs/specs-api.md`) : `item_id`
est une clé de substitution, et une base refaite renumérote ses items. Le lien vise donc
`/comptes-rendus/<sujet>/<jour>/sources/<id>`, jamais `/items/<id>` : au clic, le site relit le compte rendu, puis
l'item, et compare l'URL de l'item à celle de la source, quand la source en a une (le jumeau l'écrit telle quelle,
`find_writable_url`) ; sinon, le titre de l'item, mis sur une ligne comme l'écrit le jumeau (`make_visible`, passée
de `post/vault_files.py` à `items.py` : une seule règle pour l'écrivain du jumeau et le site), au titre de la
source. L'URL d'abord : les failles du catalogue KEV partagent leur titre (`vulnerabilityName`), jamais leur URL
(NVD et le n° CVE), et l'import met à jour sur place le titre d'un papier qu'arXiv retitre
(`database/writers/paper_writer.py`), jamais son URL (`abs/<id>`, sans version). Un même article TLDR, repris par
deux éditions, est deux items d'une même URL : sa source mène alors à l'un ou à l'autre, le même article.

| Item | Page |
|---|---|
| son URL est celle de la source, ou son titre si la source n'a pas d'URL | la page de l'item (`item.html`), « ← Retour au compte rendu », son titre suivi de « , source du compte rendu … du … » (RGAA 8.6) |
| une autre URL (ou un autre titre), `item_not_found`, une entrée Zotero ou un clip | « Source introuvable » : « Le n° … de la base de K-B ne mène pas à cette source. », le titre de la source, et son lien d'origine s'il est en `https`, par `external_link`, sans langue : le site ne connaît ni la sorte de la source ni la langue de sa page, comme pour l'article d'une newsletter |
| la source n'est pas dans le compte rendu | la page 404, sans lecture d'item |

Écartés : un lien direct vers `/items/<id>`, qu'une base refaite mènerait sans erreur à un autre item ; contrôler
chaque source à l'affichage, jusqu'à 60 `GET /items/{id}` par page. Le titre de l'adresse n'est jamais lu : celui
de la source vient du compte rendu relu.

**Les états** :

| État | Statut | Page |
|---|---|---|
| l'index | 200 | les 9 sujets, sans appel |
| un sujet hors de `SUBJECTS`, un jour ou un numéro hors de sa forme, un jour qui n'existe pas (`2026-02-30`) | 404 | sans appel à l'API |
| un 404 `digest_not_found` sans jour | 200 | « Aucun compte rendu pour ce sujet. », sans appel de ses jours |
| un 404 `digest_not_found` avec un jour | 404 | la page 404 (l'adresse vient d'un lien ou d'une saisie) |
| `outcome` `no_claim` | 200 | « Aucune affirmation retenue. », les mots de la fiche (`post/digest_sheets.py`), et les jours |
| `outcome` `no_item` | 200 | « Aucun item classé dans ce sujet. », de même |
| la lecture coupée (`items_capped`) | 200 | le bandeau « Compte rendu partiel » (ci-dessus), s'il manque au sujet une sorte ou une part d'une sorte |
| tout autre échec, une réponse hors contrat | 500 | journalisée comme au fil (`data_api_failed: …`), sans le sujet ni le jour |

Sans affirmation, la ligne « Rédigé par … » n'est pas écrite : `no_item` dit qu'aucun item n'est allé au modèle.
Une réponse est hors contrat pour un autre sujet ou un autre jour que ceux demandés, une affirmation qui cite une
source absente du compte rendu (OWASP LLM07), une source listée deux fois, un `outcome` qui contredit les affirmations, une lecture coupée sans
sa sorte ou sans sa date, une sorte coupée hors des cinq du fil, un modèle hors de la forme que `kb` écrit
(`MODEL_NAME`), et au-delà des bornes de `items.py` et de `core/config.py` (12 affirmations, 400 caractères, 1 à 5
sources par affirmation, 60 sources, un titre de 1 024 caractères, une URL de 2 000) ; pour les jours, au-delà de
30, un jour listé deux fois ou un total plus petit que les jours servis. Le 503 `watch_unconfigured` (le Mac sans `AZURE_CLIENT_ID`) est la
page 500.

**Le budget** (D4 de #564, RGESN 6.1) : 3 requêtes et 30 Ko transférés, cache vide, gzip compris, sur un compte
rendu à ses bornes (12 affirmations de 400 caractères, 60 sources aux titres de 140 caractères) et 30 jours
(`tests/web/test_digest_pages.py`). Hors budget : des titres à leur borne de 1 024 caractères, comme les notes
d'une *release* au détail. Appels à l'API : 0 pour l'index, 2 par compte rendu, 2 par clic sur une source. RGESN
7.1 n'est pas tenu, par décision (D1, le site ne garde aucune réponse de l'API).

**La preuve de bout en bout** : `tests/web/test_site_on_the_data_api.py` dépose un jumeau dans un `watch`
simulé, sert le site sur la vraie API de données de la base de test, puis suit le lien d'une source jusqu'à son
item : la source, écrite comme `kb digest` l'écrit depuis le détail que lit l'API IA, retrouve l'item par son URL.

## Tendances

`/tendances` (#596) montre les dépôts d'une fenêtre de 3 jours de GH Archive, par `GET /trends` de l'API de
données, avec la clé du client `WEB` : la plus récente, ou celle qui se termine le jour du formulaire. Maquette
du 09/11 : `Maquette-tendances`. `web/trends.py` lit le jour et bâtit la page, sans entrée ni sortie.

**Le formulaire** (GET, sans JavaScript) a un champ, « Fenêtre se terminant le » (`window_end`,
`type=date`), et son aide, « Sans date: la fenêtre la plus récente. ». Le jour est lu par `read_written_day`
(`web/feed.py`), la règle de la date de début du fil : `WrittenDay`, `AAAA-MM-JJ`, un jour qui existe. Vide ou
absent, la fenêtre la plus récente ; répété, sa dernière valeur. Le champ montre le dernier jour de la fenêtre
affichée, ou le jour demandé d'une fenêtre absente ; jamais une valeur refusée (la valeur d'un `type=date` est un
jour valide ou rien : WHATWG, RGAA 8.2). Le message nomme donc une valeur refusée qui a la forme d'un jour, chiffres
ASCII et tirets seuls (`DAY_FORM` d'`items.py`, « Date invalide: 2026-02-30 n’existe pas. Choisissez un jour qui
existe. ») ; toute autre valeur n'atteint jamais la page, qu'un lien ferait sinon dire n'importe quel texte. Une
année de 5 ou 6 chiffres, que Chrome laisse taper et envoie, a sa phrase, sans la valeur (« Date invalide: l’année a
plus de 4 chiffres. ») ; toute autre valeur reçoit « Date invalide: choisissez un jour dans le champ. ». Aucun
message ne donne de format : le champ montre le jour à la façon du navigateur (`10/10/2026` dans Chrome en
français), que le site ne connaît pas (Opquast 80, #617). La
date de début du fil a les mêmes phrases, le champ nommé par chaque page (« Date de début », « Date »), par la
même fonction (`write_day_refusal`, `web/feed.py`). Limite
(Opquast 81) : la valeur refusée ne revient pas dans le champ. GH Archive est expliqué à sa première occurrence, dans les mots de `/sources` (Opquast 5).

**Le tableau** a sa légende (`caption`) : la fenêtre, du premier au dernier jour en `<time>` au mois en lettres,
le premier jour étant `window_end` − 2 jours (`GH_ARCHIVE_WINDOW_DAYS`), « sur GitHub » et l'échantillon de GH
Archive. Ses colonnes sont en `th scope="col"`, avec les mots de la maquette : « Rang » (la position dans l'ordre
de l'API), « Dépôt », « Étoiles gagnées » et « *Forks* gagnés », ces deux derniers alignés à droite en chiffres
tabulaires, les milliers groupés par une espace fine insécable (U+202F), par `write_count` comme dans le fil. Le dépôt de chaque ligne est son en-tête
(`th scope="row"`, RGAA 5.7), écrit comme les autres cellules : un lien vers `https://github.com/<owner>/<repo>`,
bâti d'un `RepositoryName` validé, par la macro `external_link` (nouvel onglet, « (en anglais, site externe, nouvel
onglet) », gardée visible : décision de Sabine du 2026-11-14). Le tableau a 560 px de large au moins (`35rem`),
comme la maquette (décision de Sabine du 2026-11-14) : sur un écran plus étroit, il défile dans son cadre, sans
élargir la page. Le cadre prend le focus (`tabindex="0"`), une région nommée par la légende (C7 de #564 ;
WCAG 2.1.1) ; il est le conteneur de la légende (`container-type: inline-size`), qui garde sa largeur
(`max-inline-size: 100cqi`) et reste lisible sans défiler ; sous le tableau, 6 px gardent en vue l'anneau de focus du
dernier lien, que le cadre couperait. Une ombre au bord du cadre dit que le tableau continue de ce côté (#618) :
deux caches de la couleur du cadre défilent avec le tableau (`background-attachment: local`) et couvrent les deux
ombres, fixées au cadre, tant que le tableau s'arrête à leur bord ([Lea Verou, 2012](https://lea.verou.me/2012/04/background-attachment-local/)).
L'ombre a la couleur des bordures (`--color-stone`) : chaque texte du tableau y garde 4,5:1 au moins, 5,36:1 pour un
lien (WCAG 1.4.3). Chaque dégradé finit sur sa propre couleur rendue transparente (`--color-card-clear`,
`--color-stone-clear`), jamais sur le noir transparent de `transparent` : un moteur qui n'interpole pas en alpha
prémultiplié en ferait une bande grise, plus sombre que l'ombre. Firefox interpole en alpha prémultiplié depuis sa
version 36 ([bug 591600](https://bugzilla.mozilla.org/show_bug.cgi?id=591600)) ; un cas resté faux en Firefox 120 à
122 ([bug 1869681](https://bugzilla.mozilla.org/show_bug.cgi?id=1869681), encore ouvert) ; le cas « Premultiplied
alpha » corrigé en Firefox 137 ([bug 1904106](https://bugzilla.mozilla.org/show_bug.cgi?id=1904106), qui ne cite pas
1869681) ; tous lus le 2026-11-22. Les deux couleurs transparentes ne dépendent d'aucune version. L'ombre n'a pas de 3:1 à tenir (WCAG 1.4.11) : ce qu'elle dit est aussi donné ailleurs, la
légende nomme les étoiles et les *forks* gagnés ([Understanding 1.4.11](https://www.w3.org/WAI/WCAG21/Understanding/non-text-contrast),
« The information is available in another form »), et la charte classe `--color-stone` sur blanc en décor. Choix
(time-knight, 2026-11-22) : l'ombre garde la couleur de la charte. Elle est discrète, 1,36:1 au plus sombre sur 12 px
(mesuré dans Chrome 157), et tout le monde ne la voit pas ; la foncer serait borné à 1,65:1 environ, où le lien
tombe à 4,5:1. En couleurs forcées, Chrome retire les dégradés, et le cadre garde sa bordure (mesuré dans Chrome 157
le 2026-11-22). À l'impression, le cadre ne défile plus : les caches restent sur les ombres, qui ne se voient pas
(impression émulée dans Chrome 157, le 2026-11-22) ; la flèche et l'annonce des liens du tableau sont retirées.

**Le focus dans le cadre** a une limite (#693, mesurée dans Chrome 157 sans interface, au clavier seul, sur
`main` e8bbb5d2, le 2026-11-22) : au Tab, Chrome ne fait défiler le cadre que si le lien qui prend le focus en est
entièrement sorti, et le centre alors ; un lien en partie visible laisse le cadre où il est. À 390 px, le cadre
défilé au bout, le lien de la première ligne va de −138 à 130 px pour un cadre de 17 à 358 px ; à 320 px, sans
défilement, il va de 81 à 349 px pour un cadre de 17 à 288 px. Une partie du lien et un côté de son anneau restent
cachés ; l'anneau se voit sur ses autres côtés (WCAG 2.4.7). Les flèches font défiler le cadre, le focus restant sur
le lien (à 390 px, le cadre revient au début). La déclaration d'accessibilité le dit dans ses limites connues.
Écarté : `scroll-padding-inline` sur le cadre et `scroll-margin-inline` sur le lien, appliqués (16 px calculés),
n'ont aucun effet au Tab sur un lien en partie visible ; ils déplacent `scrollIntoView` (mesuré en contrôle), que le
site, sans JavaScript, n'appelle pas ; `scroll-padding-inline: 50%` ne ramène que le lien
qui ne touche pas le milieu du cadre ; aimanter le cadre sur la colonne « Dépôt » tant qu'un lien a le focus
(`:has(a:focus-visible)` et `scroll-snap-type: x mandatory`) ne tient pas à 320 px et bloque le défilement du
cadre ; figer la colonne (`position: sticky`) change le défilement dans le cadre, décidé le 2026-11-14 (#596).
Firefox et Safari ne sont pas mesurés ; le tableau d'[ally.js](https://allyjs.io/tests/scrolling/table.html) (non
daté) rapporte le même comportement pour Gecko, Blink et WebKit.

**L'échantillon** est dit au-dessus du tableau : GH Archive ne voit qu'environ 1 % des étoiles et de 0,8 à 1,3 % des
*forks*, jusqu'à 4,2 % (mesures du 29/10, `docs/specs-collecte.md`, « Limite mesurée le 2026-10-29 ») ; l'ordre, sous le
tableau (étoiles gagnées, puis *forks*). Pas de « jusqu'à 60 dépôts » (mission du 2026-11-11).

**Les états** :

| État | Statut | Page |
|---|---|---|
| une fenêtre | 200 | le tableau |
| un jour refusé par le site | 422 | le message sous le champ, qui nomme une valeur de la forme d'un jour, `aria-invalid`, « Tendances, date à corriger », sans tableau ni appel à l'API |
| un 422 `invalid_parameter` de l'API sur `window_end` seul | 422 | le même, « La base de K-B refuse cette date » |
| un 404 `trend_window_not_found` avec un jour | 200 | « Aucune tendance pour la fenêtre qui se termine le … », et « Voir la fenêtre la plus récente » |
| un 404 `trend_window_not_found` sans jour | 200 | « Aucune tendance en base. » |
| tout autre échec, une réponse hors contrat | 500 | journalisée comme au fil (`data_api_failed: …`), sans le jour |

Une réponse est hors contrat sans ligne, au-delà de 60 lignes, avec un nom hors de `RepositoryName`, un compte
négatif ou au-delà de 64 bits, une fenêtre qui finirait avant le 3 janvier de l'an 1 (son premier jour
n'existerait pas), ou une autre fenêtre que celle du jour demandé. Un nom que `is_repository_name` refuse (un
segment `.` ou `..`, ou `..` en son sein) garde sa ligne et son rang, écrit sans lien : un navigateur résoudrait
`https://github.com/owner/..` vers une autre page de GitHub, et un seul nom ne cache pas les autres lignes. Le
journal des requêtes écrit `route=/tendances`, jamais le jour.

**La navigation** mène au fil (« Veille »), aux comptes rendus (#724) et aux tendances, visibles à toutes les
largeurs, sans menu replié (D2 de #564, décision de Sabine du 2026-11-11) ; la page 404 propose aussi « Voir les tendances ».

**Le budget** (D4 de #564, RGESN 6.1) : 3 requêtes et 30 Ko transférés, 60 lignes aux noms de 140 caractères
(`tests/web/test_trends_page.py`), pesé par la même aide que le fil et le détail (`tests/web/screen_weight.py`).

## Accès

Le site est privé. En ligne, Azure Container Apps fait signer Sabine par Microsoft Entra, puis pose
l'en-tête `X-MS-CLIENT-PRINCIPAL-ID`, l'identifiant d'objet de la personne connectée. La plateforme refuse
cet en-tête venu d'un client ([Microsoft Learn, « Authentication and authorization in Azure Container
Apps »](https://learn.microsoft.com/en-us/azure/container-apps/authentication), lu le 2026-11-11).

Le code le vérifie aussi, sur chaque requête sauf `/health` (`web/operator_check.py`). Le chemin comparé
est celui que suit le routeur, décodé (`scope["path"]`) : `request.url.path` lit `/health` dans
`/health%3F`. L'en-tête doit être
présent une seule fois, être un GUID, et valoir `KB_WEB_OPERATOR_ID`, sans tenir compte de la casse. Sinon,
la page 403 « Accès réservé » répond, avec un lien « Se déconnecter » (`/.auth/logout`). Avec le contrôle,
chaque autre page porte « Se déconnecter » à la fin de son en-tête (Sabine, 2026-11-11) ; la page 403 ne le
répète pas, son bouton suffit. La plateforme sert `/.auth/logout` : elle efface les cookies de la session,
supprime les jetons de l'utilisatrice du magasin de jetons, la déconnecte côté serveur de Microsoft Entra, puis
renvoie vers `/.auth/logout/done` ([Microsoft Learn, « Authentication and authorization in Azure Container
Apps »](https://learn.microsoft.com/en-us/azure/container-apps/authentication), « Sign out of a session », page
mise à jour le 2026-07-08, lue le 2026-11-11). Le journal dit
`operator_refused: header_absent|header_repeated|header_malformed|header_other request_id=…`, jamais la
valeur reçue.

Ce contrôle ne protège rien sans l'authentification de la plateforme : l'identifiant de Sabine n'est pas
un secret. Elle est donc posée dans le même déploiement que l'entrée publique du site.

Le contrôle est un middleware HTTP (`BaseHTTPMiddleware`) : il ne voit pas une connexion WebSocket. Le site
n'en a aucune route ; une route WebSocket demanderait un contrôle écrit en ASGI pur.

`KB_WEB_AUTH=off` ne vérifie aucun en-tête, pour essayer le site sur le Mac. `kb serve-web` ne l'accepte
que sur une adresse de boucle locale, hors d'Azure Container Apps (`CONTAINER_APP_NAME` absente). Avec
`entra`, il refuse d'écouter hors de la boucle locale sans `CONTAINER_APP_NAME` : sur le Mac, tout appareil
du réseau pourrait poser l'en-tête.

## Réglages

| Variable | Sur le Mac | En ligne |
|---|---|---|
| `KB_DATA_DIR` | obligatoire, comme pour toute commande `kb` | le montage, comme pour les API |
| `KB_WEB_HOST` | `127.0.0.1` par défaut | `0.0.0.0` |
| `KB_WEB_PORT` | `8002` par défaut | le port cible de l'entrée |
| `KB_WEB_ALLOWED_HOSTS` | `127.0.0.1,localhost` par défaut | le nom externe du site, et le `Host` donné aux sondes |
| `KB_WEB_AUTH` | `off` pour un essai | non posée (`entra`) |
| `KB_WEB_OPERATOR_ID` | — | `operatorObjectId` de `infra/main.bicep` |
| `KB_DATA_API_KEY_WEB` | obligatoire : la clé que lit aussi `kb serve-data` pour son client `WEB` | un secret posé aux deux apps |
| `KB_DATA_API_URL` | `http://127.0.0.1:8000` par défaut | l'URL interne de l'API de données, en `https` |
| `KB_LOG_TO_FILE` | `true` par défaut : `logs/kb-serve-web.log` | `false` (image) : la sortie d'erreur |
| `KB_VERSION` | non posée : pas de ligne de version | posée par l'image : le tag de sa construction |

`KB_VERSION` ne se pose jamais à la main. `deploy.yml` construit l'image d'un tag avec
`--build-arg KB_VERSION=<tag>`, et le `Dockerfile` garde cette valeur dans l'environnement de l'image : la version
suit l'empreinte de l'image, en retour arrière comme en passe 2 de Bicep. Le pied de chaque page la donne après ses
liens, « Version déployée: v0.1.9 ». Vide ou absente, pas de ligne : l'image a été construite hors de `deploy.yml`
(`image.yml`, `compose.yaml`, à la main) ou avant le premier tag construit avec `KB_VERSION`. Posée, elle doit être `vMAJEUR.MINEUR.CORRECTIF`,
sans zéro en tête (`VERSION_TAG`, `web/settings.py`), sinon `kb serve-web` refuse de démarrer. C'est la règle du job
`check` de `deploy.yml`, qui refuse tout autre tag : les deux changent ensemble, sinon un tag livré empêcherait le
site de démarrer.

En ligne, l'app sert `serve-web` par une entrée externe en HTTPS seulement, avec l'authentification Entra
en « Require authentication » : sans session, un navigateur reçoit un 302 vers la connexion de Microsoft Entra
(`login.microsoftonline.com/<tenant>/oauth2/v2.0/authorize`, seul fournisseur), et un client qui n'accepte pas
`text/html` un 401 avec `WWW-Authenticate: Bearer` (constat en ligne de time-knight, 2026-11-11). Sa sonde est
`GET /health`.

## En-têtes

Chaque réponse porte :

- `Content-Security-Policy: default-src 'none'; style-src 'self'; img-src 'self'; form-action 'self';
  base-uri 'none'; frame-ancestors 'none'` : ni script, ni style en ligne, ni ressource d'un autre site ;
- `Strict-Transport-Security: max-age=31536000`, `X-Content-Type-Options: nosniff` ;
- `Referrer-Policy: no-referrer` : l'adresse d'une page ne part pas avec un lien vers arxiv.org ou GitHub.

Aucune ne porte d'en-tête `Server` (`server_header=False` d'uvicorn), qui nommerait le logiciel (Opquast 2025,
règle 213). En ligne, l'entrée d'Azure Container Apps peut en poser un.

## Cache

Aucune page n'est gardée, ni par le serveur ni par le navigateur (décision de Sabine du 2026-11-11) ; le
site ne garde pas non plus les réponses de l'API de données (D1, Sabine, 2026-11-11 : RGESN 7.1 non tenu,
par décision) :

- une page, une erreur et `/health` : `no-store`, que le navigateur ne garde pas même pour son bouton
  Retour ;
- `/static` : `no-cache`, revalidé par son ETag à chaque page.

Une réponse de plus de 500 octets, page d'erreur comprise, est compressée en gzip si le navigateur
l'accepte.

## Erreurs

Chaque erreur rend une page HTML : 403, 404, 500, et une page qui donne le code pour les autres (405).
Une exception : une requête dont le `Host` n'est pas dans `KB_WEB_ALLOWED_HOSTS` reçoit le 400 en texte
brut de `TrustedHostMiddleware`, avant le site ; il ne vise qu'une sonde ou un réglage faux. Il ne redirige
jamais vers le `www.` d'un hôte permis (`www_redirect=False`) : la redirection prendrait le schéma vu, `http`. Une
exception imprévue rend la page 500, avec l'heure UTC et l'identifiant de la demande (`X-Request-ID`). Le
journal en écrit le type, `internal_error: <Type> request_id=…`, jamais le message ni la pile. Si le
gabarit de la page 500 échoue lui aussi, une page écrite sans gabarit répond (`FALLBACK_SERVER_ERROR_PAGE`),
et le journal écrit une seconde ligne `internal_error` : l'exception ne remonte jamais à Starlette, qui
répondrait en texte, ni à uvicorn, qui en écrirait la pile. Le lien
« Réessayer » pointe vers la page elle-même (`href=""`), jamais vers un chemin reçu.

## Gabarits

`web/rendering.py` monte Jinja2 avec deux réglages :
- `autoescape=True` : toute valeur est échappée, quel que soit le nom du gabarit ;
- `StrictUndefined` : une valeur absente fait échouer la page.

Les gabarits sont lus dans le paquet. `tests/web/test_templates.py` vérifie qu'un gabarit n'écrit jamais :
- `|safe`, `Markup` ni `autoescape false` ;
- `url_for` : derrière l'entrée d'Azure, le schéma vu serait `http` ;
- un script, un style en ligne ni une ressource d'un autre site ;
- un attribut sans guillemets.

## Feuille de style

`web/static/site.css` n'emploie que des fonctions CSS Baseline « Widely available » (données web-features
3.45.0, lues le 2026-11-11) : l'imbrication, les couches (`@layer`), les propriétés logiques, `:where()`,
les unités `dvb` et la syntaxe d'intervalle des media queries ; les requêtes de conteneur, « Widely available »
depuis le 2025-08-14 (web-features explorer, lu le 2026-11-21). `text-wrap: balance`, « Newly available »,
ne fait qu'ajouter : un navigateur qui ne la connaît pas ne perd rien. De même `background-attachment: local`, « Widely
available » par sa propre clé (web-features 3.47.0, lu le 2026-11-22), alors que la fonction `background-attachment`
ne l'est plus depuis le 2026-01-29, à cause de `fixed` sur iOS : un navigateur qui ne la connaît pas ne montre pas
d'ombre au bord du tableau des tendances. Les trois largeurs des maquettes
(390, 820 et 1280 px) se lisent par deux seuils, `48rem` et `64rem`. Le formulaire du fil suit chacune
(Sabine, 2026-11-11) : sur un téléphone, les sortes et les boutons radio en deux colonnes ; sur une tablette,
les sortes en trois, et « Date de début » à droite des boutons radio ; sur un ordinateur, les sortes sur une
ligne, et le champ de date après son libellé, sur la ligne des boutons radio. Les aides restent collées à leur
libellé. Mesuré dans Chrome le 2026-11-11, il passe de 585 à 409 px de haut à 1280 px (334 px pour la
maquette, sans les trois aides). Une page s'imprime sans en-tête, pied de page ni boutons (`@media print`).

À fort zoom sur un petit écran, la mise en page s'adapte (#599) : sous 15em de la police du corps, soit 240 px à
texte 100 %, jamais atteints dès 320 px, et 480 px à texte 200 %. Le corps est le conteneur de cette requête,
nommé `body` (`@container body (inline-size < 15em)`) : l'`em` d'une requête de conteneur est la taille de police
de son conteneur (CSS Conditional 5, 5.1), il suit donc le texte agrandi. Sans elle, aucune page ne débordait à
14,5em et au-delà (mesuré le 2026-11-21). Les choix du fil passent en une colonne (Sabine, 2026-11-21), le titre
des pages d'erreur prend la taille des autres titres sur un téléphone, en rem, et les marges (page, formulaire,
cartes, champs, boutons) ne doublent plus avec le texte : un champ de date, qui ne peut être plus étroit que son
jour et son calendrier sans les cacher, tient dans 320 px. La flèche d'un bouton (←, → et ↗) est liée à son mot
par une espace insécable, dans un seul élément du bouton avec son libellé ; une marge lui rend l'espace qu'elle
avait. Mesuré dans Chrome 157 le 2026-11-21, avec la police système de macOS : aucune des 24 pages de
`tests/web/test_accessibility.py` ne défile en largeur, de 320 à 1280 px, à texte de 100 à 200 %.

L'anneau de focus (`:focus-visible`, un contour de 3 px à 2 px de l'élément) a une marge de défilement en haut et en
bas, `scroll-margin-block: 5px`, la place de l'anneau autour de l'élément (#700). Au clavier, Chrome ne fait défiler la
page vers un élément en partie hors de l'écran que jusqu'au bord de l'élément, le bord bas au Tab, le bord haut au
Maj+Tab : sans la marge, ce côté de l'anneau restait caché, de 5 px au plus. Mesuré dans Chrome 157 sans interface, au
clavier seul, sur les 24 pages de `tests/web/test_accessibility.py`, à 1280 px, à 200 % (640 px CSS à 2 px d'écran par
px CSS) et à 320 px, sur `main` 9658225a, sans puis avec la marge (2026-11-22) :

- au Tab, du premier arrêt au dernier : 10, 41 et 21 bas d'anneau coupés sans la marge, aucun avec ;
- au Maj+Tab, du dernier arrêt au premier : 6, 25 et 19 hauts coupés sans la marge, aucun avec ;
- chaque arrêt placé à 1 px, puis à mi-hauteur, hors de l'écran, puis Tab ou Maj+Tab (544 essais de chaque côté par
  réglage) : 144, 312 et 322 bas coupés, 149, 342 et 359 hauts coupés sans la marge, aucun avec.

Le lien d'évitement mène au même endroit avec et sans la marge, et le reste de l'essai ne change pas, sauf le cadre des
tendances, plus haut que l'écran à 200 % et à 320 px : son anneau est coupé de 1 à 2 px en haut au lieu de 6 à 7, et
de 5 px de plus en bas. Le bouton du calendrier d'un champ de date porte l'anneau de Chrome, pas celui du site : il
n'est pas compté. Écarté : `scroll-padding-block` sur la page, qui vaut pour tout défilement et décale de 5 px la
cible du lien d'évitement (mesuré avec les deux côtés) ; une marge sur chaque élément que le clavier atteint, qui
jouerait hors du focus clavier. La marge ne ramène pas un lien en partie hors du cadre des tendances (plus haut, #693).
Firefox et Safari ne sont pas mesurés.

## Accessibilité

La cible est le RGAA 4.1.2, soit WCAG 2.1 AA, avec les règles du référentiel Opquast 2025 (version 5.0)
qu'un test peut vérifier. La charte vient des maquettes du 2026-11-09.

`tests/web/test_accessibility.py` vérifie sur chaque page :
- la langue, celle des passages en anglais, et un titre propre ;
- un seul `h1`, et des titres sans niveau sauté ;
- les zones et le lien d'évitement ;
- le lien courant, et les liens du pied de page en liste ;
- la version déployée, au bas du pied de page, après ses liens ;
- les SVG décoratifs ;
- l'absence de script ;
- un lien vers un autre site dit « site externe » et « nouvel onglet », s'ouvre dans un nouvel onglet
  (`target="_blank"`, `rel="noopener noreferrer"`) et donne sa langue quand elle n'est pas le français ; un lien
  du site s'ouvre dans le même onglet ;
- la première abréviation d'une page suivie de son sens, une date au mois écrit en lettres ;
- aucune espace avant « : » ni « ; » dans le texte (règle de Sabine).

Sur le fil (normal, page 2, vide et refusé), il vérifie aussi : un `label` pour chaque champ, un `fieldset` et
sa `legend` pour chaque groupe, chaque `aria-describedby` qui nomme un élément de la page, le message d'un
champ refusé, ouvert par « Erreur. », et son `aria-invalid`, le résumé qui mène à chaque champ et dit chaque
message sans ce mot, les cartes en liste et leurs titres en
`h2`, les titres en anglais marqués (`lang="en"`), la date de chaque carte en `<time>`, la pastille écrite en
mots, et la pagination nommée.

Sur les tendances (une fenêtre, un jour refusé, une fenêtre absente, la base vide), il vérifie : le `label` et
l'aide du champ, le message d'un jour refusé, ouvert par « Erreur. », et son `aria-invalid`, la légende du tableau, un `th scope="col"`
par colonne et un `th scope="row"` par ligne (RGAA 5.4, 5.6 et 5.7), les deux jours de la fenêtre en `<time>`, *forks* en `lang="en"`,
l'échantillon et l'ordre dits, et le cadre du tableau atteint au clavier, une région nommée par sa légende. Sur
chaque page, la navigation mène au fil, aux comptes rendus et aux tendances ; la 404 propose le fil et les
tendances.

Sur les comptes rendus (l'index, un compte rendu, sans affirmation, partiel, un sujet sans compte rendu, une source
et une source introuvable), il vérifie : LLM et UTC expliqués à leur première occurrence, les affirmations en
liste numérotée sous leur `h2`, la liste des sources sous chaque affirmation, et la liste des jours sous son `h2`.

`tests/web/test_stylesheet.py` calcule les contrastes de la charte, celui des liens visités compris, et
vérifie l'anneau de focus et sa marge de défilement, la taille du lien d'évitement, les règles du fort zoom et la
feuille d'impression.
`tests/web/test_accessibility.py` vérifie aussi la flèche de chaque bouton liée à son mot.

Le reste se contrôle à la main : la validité du code, le zoom à 200 %, la largeur de 320 px, l'espacement
du texte, le clavier et le lecteur d'écran.
