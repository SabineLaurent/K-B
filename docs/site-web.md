# Le site de K-B (`kb serve-web`)

Le site affiche la veille de K-B à sa seule opératrice, Sabine. Il est rendu par le serveur, avec FastAPI et
Jinja2, sans aucun JavaScript dans le navigateur. Il ne lit pas la base : il lit l'API de données par HTTP,
comme son client `WEB` (`KB_DATA_API_KEY_WEB`). Le paquet `src/k_b/web/` n'importe que `core` et `items`
(`tests/architecture/test_layers.py`).

## Pages

| Chemin | Page |
|---|---|
| `/` | « Quoi de neuf », le fil de veille (« Fil », ci-dessous) |
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
| Rechercher | `q` | espaces autour retirées ; vide, aucune recherche ; 200 caractères au plus, sans caractère de contrôle (les règles de `q` de l'API) |
| Sortes | `kind`, répété | les cinq cases cochées par défaut ; aucune cochée vaut les cinq ; une autre valeur est refusée, sans appel à l'API |
| Depuis | `period` : `1`, `3`, `7` ou `date` | `1` par défaut (D3, Sabine, 2026-11-11) ; N jours donne minuit UTC du jour J−N : « 1 jour » prend hier et aujourd'hui |
| Date de début | `start`, `AAAA-MM-JJ` | lue seulement si `date` est cochée (D4 : le bouton radio fait foi) ; son propre minuit UTC |
| page | `page` | `[1-9][0-9]{0,2}`, 501 au plus (l'`offset` 10 000 de l'API) ; absente, la page 1 |

La route lit `request.query_params` brut, jamais des paramètres typés par FastAPI : un `page=abc` partirait
sinon dans le 422 JSON de FastAPI, qui recopie la valeur reçue.

**La carte** d'un item donne sa sorte, sa date au mois en lettres (`<time>`), la pastille « Exploitée (KEV) »
(une faille toujours, une alerte dont la CVE est au catalogue), ses identifiants, son titre et le lien vers la
source, « (en anglais, site externe) » ou, pour une newsletter, « (site externe) ». Une URL qui n'est pas en
`https` vers un hôte ne devient jamais un lien. Le titre n'est pas encore un lien : le détail vient avec
#564. Une newsletter porte le nom que TLDR donne à son édition (`NEWSLETTER_NAME_BY_EDITION`, « TLDR AI »
comme les maquettes ; time-knight, 2026-11-11), « TLDR » et son identifiant d'API sinon.

**Les pages** : M = max(1, ⌈total ÷ 20⌉), 501 au plus ; au-delà de 10 020 items, une phrase dit d'affiner
les filtres. Une page au-delà de M, ou hors de sa forme, rend la page 404. Les liens de page gardent les
filtres. Le fil vide propose « Élargir à 7 jours ».

**Les erreurs** : un champ refusé par le site, ou `q` refusé par l'API (422 `invalid_parameter` sur `q`
seul), rend le fil en 422, sans liste, avec un résumé des erreurs et un message sous chaque champ. Tout autre
échec de l'API (5xx, 429, 401, délai, réponse hors schéma, 422 sur un paramètre que le site construit) rend
la page 500, et le journal écrit `data_api_failed: <état> http_status=<n|-> request_id=<id>`, jamais `q`.

**Le client** de l'API (`web/data_api_client.py`) : 5 s de connexion, 30 s de lecture
(`WEB_DATA_API_READ_TIMEOUT_SECONDS`), 10 s d'écriture, 5 s d'attente du pool ; une échéance de 35 s vérifiée
entre deux morceaux du corps, borné à 1 Mo. Les 30 s couvrent le réveil de l'API à zéro réplique, 20 à 26 s
(#414). Limite : chaque délai borne une attente, et l'échéance ne se lit qu'entre deux morceaux ; rien n'est
borné avant le premier morceau du corps (#436). Une requête peut donc durer environ 70 s au pire : la
connexion et le pool, 30 s jusqu'aux en-têtes, puis 30 s jusqu'au premier morceau du corps. Il ne suit aucune redirection et
ne lit pas l'environnement. Une réponse est lue par un modèle fermé aux cinq sortes ; un champ que l'API
ajoute est ignoré.

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

## Accès

Le site est privé. En ligne, Azure Container Apps fait signer Sabine par Microsoft Entra, puis pose
l'en-tête `X-MS-CLIENT-PRINCIPAL-ID`, l'identifiant d'objet de la personne connectée. La plateforme refuse
cet en-tête venu d'un client ([Microsoft Learn, « Authentication and authorization in Azure Container
Apps »](https://learn.microsoft.com/en-us/azure/container-apps/authentication), lu le 2026-11-11).

Le code le vérifie aussi, sur chaque requête sauf `/health` (`web/operator_check.py`). Le chemin comparé
est celui que suit le routeur, décodé (`scope["path"]`) : `request.url.path` lit `/health` dans
`/health%3F`. L'en-tête doit être
présent une seule fois, être un GUID, et valoir `KB_WEB_OPERATOR_ID`, sans tenir compte de la casse. Sinon,
la page 403 « Accès réservé » répond, avec un lien « Se déconnecter » (`/.auth/logout`). Le journal dit
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

En ligne, l'app sert `serve-web` par une entrée externe en HTTPS seulement, avec l'authentification Entra
en « Require authentication » (redirection vers `/.auth/login/aad`). Sa sonde est `GET /health`.

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
les unités `dvb` et la syntaxe d'intervalle des media queries. `text-wrap: balance`, « Newly available »,
ne fait qu'ajouter : un navigateur qui ne la connaît pas ne perd rien. Les trois largeurs des maquettes
(390, 820 et 1280 px) se lisent par deux seuils, `48rem` et `64rem`. Une page s'imprime sans en-tête, pied
de page ni boutons (`@media print`).

## Accessibilité

La cible est le RGAA 4.1.2, soit WCAG 2.1 AA, avec les règles du référentiel Opquast 2025 (version 5.0)
qu'un test peut vérifier. La charte vient des maquettes du 2026-11-09.

`tests/web/test_accessibility.py` vérifie sur chaque page :
- la langue, celle des passages en anglais, et un titre propre ;
- un seul `h1`, et des titres sans niveau sauté ;
- les zones et le lien d'évitement ;
- le lien courant, et les liens du pied de page en liste ;
- les SVG décoratifs ;
- l'absence de script ;
- un lien vers un autre site dit « site externe », et sa langue quand elle n'est pas le français ;
- la première abréviation d'une page suivie de son sens, une date au mois écrit en lettres ;
- aucune espace avant « : » ni « ; » dans le texte (règle de Sabine).

Sur le fil (normal, page 2, vide et refusé), il vérifie aussi : un `label` pour chaque champ, un `fieldset` et
sa `legend` pour chaque groupe, chaque `aria-describedby` qui nomme un élément de la page, le message et
`aria-invalid` d'un champ refusé, le résumé qui mène à chaque champ, les cartes en liste et leurs titres en
`h2`, les titres en anglais marqués (`lang="en"`), la date de chaque carte en `<time>`, la pastille écrite en
mots, et la pagination nommée.

`tests/web/test_stylesheet.py` calcule les contrastes de la charte, celui des liens visités compris, et
vérifie l'anneau de focus, la taille du lien d'évitement et la feuille d'impression.

Le reste se contrôle à la main : la validité du code, le zoom à 200 %, la largeur de 320 px, l'espacement
du texte, le clavier et le lecteur d'écran.
