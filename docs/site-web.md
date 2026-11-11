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

Le code le vérifie aussi, sur chaque requête sauf `/health` (`web/operator_check.py`). L'en-tête doit être
présent une seule fois, être un GUID, et valoir `KB_WEB_OPERATOR_ID`, sans tenir compte de la casse. Sinon,
la page 403 « Accès réservé » répond, avec un lien « Se déconnecter » (`/.auth/logout`). Le journal dit
`operator_refused: header_absent|header_repeated|header_malformed|header_other request_id=…`, jamais la
valeur reçue.

Ce contrôle ne protège rien sans l'authentification de la plateforme : l'identifiant de Sabine n'est pas
un secret. Elle est donc posée dans le même déploiement que l'entrée publique du site.

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

## Cache

Il n'y a pas de cache côté serveur : avec une seule lectrice, le cache de son navigateur fait le même travail.

- Une page : `private, max-age=300` (`WEB_PAGE_MAX_AGE_SECONDS`), gardée par le navigateur seul.
- Une erreur et `/health` : `no-store`.
- `/static` : `no-cache`, revalidé par son ETag à chaque page.

Une réponse de plus de 500 octets est compressée en gzip si le navigateur l'accepte.

## Erreurs

Chaque erreur rend une page HTML : 403, 404, 500, et une page qui donne le code pour les autres (405). Une
exception imprévue rend la page 500, avec l'heure UTC et l'identifiant de la demande (`X-Request-ID`). Le
journal en écrit le type, `internal_error: <Type> request_id=…`, jamais le message ni la pile. Le lien
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

## Accessibilité

La cible est le RGAA 4.1.2, soit WCAG 2.1 AA. La charte vient des maquettes du 2026-11-09.

`tests/web/test_accessibility.py` vérifie sur chaque page :
- la langue et un titre propre ;
- un seul `h1`, et des titres sans niveau sauté ;
- les zones et le lien d'évitement ;
- le lien courant ;
- les SVG décoratifs ;
- l'absence de script.

`tests/web/test_stylesheet.py` calcule les contrastes de la charte et vérifie l'anneau de focus.

Le reste se contrôle à la main : la validité du code, le zoom à 200 %, la largeur de 320 px, l'espacement
du texte, le clavier et le lecteur d'écran.
