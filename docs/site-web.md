# Le site de K-B (`kb serve-web`)

Le site affiche la veille de K-B à sa seule opératrice, Sabine. Il est rendu par le serveur, avec FastAPI et
Jinja2, sans aucun JavaScript dans le navigateur. Il ne lit pas la base : il lit l'API de données par HTTP,
comme son client `WEB` (à partir du fil, #563). Le paquet `src/k_b/web/` n'importe que `core` et `items`
(`tests/architecture/test_layers.py`).

## Pages

| Chemin | Page |
|---|---|
| `/` | « Quoi de neuf » ; le fil de veille (#563) y prend place |
| `/sources` | « Sources et conditions d'utilisation » |
| `/accessibilite` | « Accessibilité » |
| `/static/site.css`, `/static/favicon.svg` | la feuille de style et l'icône |
| `/health` | `{"status":"ok"}`, pour les sondes ; ni page ni donnée |

Une route inconnue rend la page 404 ; `/sources/` en est une (pas de redirection). Le site ne sert ni OpenAPI
ni `/docs`.

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

Aucune page n'est gardée, ni par le serveur ni par le navigateur (décision de Sabine du 2026-11-11) :

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

`tests/web/test_stylesheet.py` calcule les contrastes de la charte, celui des liens visités compris, et
vérifie l'anneau de focus, la taille du lien d'évitement et la feuille d'impression.

Le reste se contrôle à la main : la validité du code, le zoom à 200 %, la largeur de 320 px, l'espacement
du texte, le clavier et le lecteur d'écran.
