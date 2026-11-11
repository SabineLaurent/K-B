# Ouvrir le socle du site privé de K-B (`kb serve-web`)

- **Date** : 2026-11-11
- **Branche** : `feat/web-foundation`
- **Issue** : #562 (étape 1 de la mission FO ; le fil, #563, et les détails et tendances, #564, suivent)
- **Fichiers principaux** : `src/k_b/web/` (`app.py`, `operator_check.py`, `settings.py`, `errors.py`,
  `response_headers.py`, `rendering.py`, `templates/`, `static/site.css`), `src/k_b/commands/serve_web_command.py`,
  `docs/site-web.md`, `tests/web/`
- **Décisions** : journal ADR, 2026-11-11, « Site : le socle privé de `kb serve-web` »

Les commits de la branche sont 61da6bf (le socle), 8a513d5 (première revue de code), db8a795 (ligne Opquast de
`conformite.md`), 1b017a8 (tri de sécurité, d'accessibilité et d'Opquast), 026d57c (renvoi après le rebase sur
#558), aee1d92 (limite WebSocket) et 471bb33 (seconde revue de code). Les autres commits de la liste de la PR
viennent de `main`, des PR déjà fusionnées (#556, #558 et avant) : cette note n'en parle pas.

## 1. Le pourquoi

Le livrable E4 a une interface web (décision de Sabine du 09/11) : fonctionnelle, déployée, accessible, et
**privée** : Sabine seule y entre (11/11). Ce socle en pose ce qui ne dépend pas encore des données :

- la commande qui sert le site ;
- la mise en page commune ;
- le contrôle de la personne connectée ;
- les en-têtes de sécurité ;
- les pages d'erreur ;
- les pages « Sources et conditions d'utilisation » et « Accessibilité ».

Il se déploie seul, pour essayer d'abord le risque principal : la connexion Microsoft Entra par la plateforme
Azure Container Apps, qu'un accès conditionnel de l'école pourrait bloquer.

Le site est la couche de présentation de K-B. Il lira l'API de données par HTTP (#563), comme un client de
plus, et n'importera jamais la base. Le socle ne lit encore rien.

## 2. Le comment

### 2.1 Un paquet de présentation, et l'ordre de ses middlewares

`web` est un paquet de premier niveau. Il n'importe que `core` et `items`, et seul `commands` l'importe
(`tests/architecture/test_layers.py`, le bloc « The site (#562) »). L'application se construit dans
`create_app`. Ses middlewares s'empilent : le dernier ajouté est le plus extérieur.

```python
    app.middleware("http")(check_operator)
    # www_redirect=False: Starlette would build its redirection with the scheme it sees, as for
    # redirect_slashes above.
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=list(allowed_hosts), www_redirect=False
    )
    app.middleware("http")(respond_to_unexpected_error)
    app.middleware("http")(add_response_headers)
    app.middleware("http")(log_request)
    app.add_middleware(GZipMiddleware)
```
(`src/k_b/web/app.py:43-52`)

Une requête traverse donc, de l'extérieur vers l'intérieur :

1. la compression ;
2. l'identifiant de demande (`log_request`, repris de `core/` tel quel) ;
3. les en-têtes de sécurité ;
4. le filet de la page 500 ;
5. le contrôle de l'hôte ;
6. le contrôle de l'opératrice ;
7. enfin, le routeur.

Cet ordre garantit trois choses :
- une page 403 ou 500 reçoit aussi ses en-têtes de sécurité et son identifiant ;
- tout est compressé, les erreurs comprises ;
- personne n'atteint une page, un fichier statique ou une 404 sans être passé par le contrôle.

`www_redirect=False` vient de la relecture de sécurité. Sans lui, Starlette redirigerait un hôte sans `www.`
vers son `www.`, avec le schéma qu'il voit. Derrière l'entrée d'Azure, ce schéma est `http`.

### 2.2 Le contrôle de l'opératrice

En ligne, la plateforme fait connecter Sabine par Entra. Elle pose ensuite l'en-tête
`X-MS-CLIENT-PRINCIPAL-ID`, l'identifiant d'objet de la personne connectée, et refuse cet en-tête s'il vient
d'un client. Le code le vérifie quand même : c'est la défense en profondeur de `code.md`.

```python
    if not values:
        return "header_absent"
    if len(values) > 1:
        return "header_repeated"
    [value] = values
    if not GUID.fullmatch(value):
        return "header_malformed"
    # compare_digest: the time taken does not tell how much of the id matched.
    if not hmac.compare_digest(value.lower(), operator_id):
        return "header_other"
```
(`src/k_b/web/operator_check.py:32-41`)

Chaque refus est un état nommé (règle « un échec est un état nommé » de `code.md`). Le journal écrit
`operator_refused: header_absent request_id=…`, jamais la valeur reçue. `GUID.fullmatch` impose la forme
8-4-4-4-12 entière ; `uuid.UUID` aurait accepté des accolades ou `urn:uuid:`.

`hmac.compare_digest` compare en temps constant. Ici, l'identifiant n'est pas un secret : c'est une
précaution, qui ne coûte rien.

Le point le plus fin est le chemin exempté :

```python
    if operator_id is None or request.scope["path"] == HEALTH_PATH:
        return await call_next(request)
```
(`src/k_b/web/operator_check.py:53-54`)

`scope["path"]` est le chemin décodé que suit le routeur. La première version comparait `request.url.path`.
Starlette reconstruit cette URL à partir du chemin décodé, puis la coupe au premier `?` ou `#`.

Prenons `GET /health%3F`. Le chemin décodé est `/health?`, mais l'URL reconstruite donne `/health` : la
requête sautait donc le contrôle. Le relecteur de sécurité a obtenu un 200 sans en-tête sur une route
`/{name}`. La leçon : comparer ce que le routeur utilise, pas une reconstruction.

### 2.3 Le mode local, borné par un fait de la plateforme

Sabine doit pouvoir voir le site sur le Mac, sans Entra. `KB_WEB_AUTH=off` coupe le contrôle, mais seulement
dans un cadre étroit :

```python
    if is_in_container_apps:
        return (
            f"{WEB_AUTH_VARIABLE}: {OFF_AUTH} in Azure Container Apps"
            f" ({CONTAINER_APP_NAME_VARIABLE} set)"
        )
    if not is_loopback:
        return (
```
(`src/k_b/web/settings.py:103-109`)

`CONTAINER_APP_NAME` est posée par la plateforme dans chaque conteneur : c'est un fait, pas un réglage qu'on
oublie. Le mode `entra` a la règle symétrique (`settings.py:127-132`). Hors de la boucle locale, il exige
d'être dans Container Apps. Sinon, sur le Mac en `0.0.0.0`, tout appareil du réseau pourrait poser l'en-tête
lui-même.

Un refus empêche `kb serve-web` de démarrer, avec un code de sortie nommé. Le journal dit le mode choisi,
jamais l'identifiant.

### 2.4 Des gabarits qui échappent tout, des erreurs qui ne disent rien d'interne

```python
templates = Jinja2Templates(
    env=Environment(
        loader=PackageLoader("k_b.web", "templates"),
        autoescape=True,
        undefined=StrictUndefined,
    ),
```
(`src/k_b/web/rendering.py:21-26`)

Ce code fait trois choix :
- **`autoescape=True`** échappe toute valeur, quel que soit le nom du gabarit. Le défaut de Starlette 1.8,
  `select_autoescape()`, n'échappe que `.html`, `.htm` et `.xml`. C'est la protection contre le XSS quand le
  fil affichera des textes venus de l'extérieur.
- **`StrictUndefined`** fait échouer une page dont une valeur manque, au lieu de l'afficher vide.
- **`PackageLoader`** lit les gabarits dans le paquet : l'image contient la roue, pas `src/`.

Une exception imprévue devient la page 500. Elle donne l'heure UTC et l'identifiant de la demande ; le
journal ne garde que le type de l'exception.

Depuis la seconde revue, la page 500 se rend hors du `except` :

```python
    try:
        return render_error_page(request, 500)
    except Exception as error:  # noqa: BLE001 — any failure of the template of the page 500
        log_unexpected_error(request, error)
        return HTMLResponse(FALLBACK_SERVER_ERROR_PAGE, status_code=500)
```
(`src/k_b/web/errors.py:102-106`)

Si le gabarit de la 500 échouait lui aussi, l'exception remonterait à Starlette, puis à uvicorn. Starlette
répondrait en texte brut ; uvicorn écrirait au journal la pile et le message, qui peut citer une valeur reçue
(règle 5 de `poc.md`). Le repli est une page HTML écrite sans gabarit.

### 2.5 Les en-têtes et le cache

Chaque réponse porte :
- une CSP `default-src 'none'` : ni script, ni style en ligne, ni ressource d'un autre site ;
- `Strict-Transport-Security`, `nosniff` et `Referrer-Policy: no-referrer`.

`kb serve-web` ne pose pas d'en-tête `Server` (`server_header=False`), qui nommerait le logiciel
(Opquast 213). Le cache suit une décision de Sabine :

```python
    if status_code < 400 and path.startswith(f"{STATIC_PATH}/"):
        return "no-cache"
    return "no-store"
```
(`src/k_b/web/response_headers.py:27-29`)

`no-store` : le navigateur ne garde aucune page, même pour son bouton Retour. Après `/.auth/logout`, plus rien
n'est lisible. La CSS et l'icône sont en `no-cache` : le navigateur les garde, mais les revalide à chaque
page par leur ETag, et reçoit un 304 tant qu'elles n'ont pas changé.

### 2.6 La feuille de style et l'accessibilité testée

La feuille de style n'emploie que des fonctions Baseline « Widely available ». Ces fonctions sont disponibles
dans les grands navigateurs depuis au moins 30 mois (données web-features 3.45.0). On y trouve :
- des couches (`@layer reset, base, layout, components`, `site.css:10`) ;
- l'imbrication ;
- des propriétés logiques ;
- la syntaxe d'intervalle des media queries.

Les trois largeurs des maquettes (390, 820 et 1280 px) se lisent par deux seuils :

```css
  h1 {
    margin-block-end: 1rem;
    font-size: 1.625rem;
    line-height: 1.25;

    @media (width >= 48rem) {
      font-size: 1.75rem;
    }

    @media (width >= 64rem) {
      font-size: 1.875rem;
    }
  }
```
(`src/k_b/web/static/site.css:71-83`, les 26, 28 et 30 px des maquettes)

L'accessibilité se teste avec `html.parser`, de la bibliothèque standard, sans dépendance
(`tests/web/test_accessibility.py`). Sur chaque page, le test vérifie :
- la langue ;
- le titre ;
- un seul `h1` ;
- les repères ;
- le lien d'évitement en premier ;
- le lien courant ;
- les liens du pied en liste ;
- les SVG décoratifs ;
- l'absence de script.

S'y ajoutent les règles Opquast qu'un test peut voir :
- un lien vers un autre site dit « site externe » ;
- la première abréviation d'une page donne son sens ;
- le mois d'une date est écrit en lettres ;
- aucune espace avant « : » ni « ; » dans le texte affiché (règle de Sabine).

`tests/web/test_stylesheet.py` calcule les contrastes de la charte avec la luminance relative des WCAG 2.1.

## 3. Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| FastAPI + Jinja2, rendu serveur, zéro JavaScript | Décision de Sabine (mission FO) : le site reste dans l'image, la CI et les protections de K-B | `app.frontend()` du skill `fastapi` : son repli de page unique avale les 404 |
| Contrôle par middleware | Il couvre les pages, `/static` et les 404 | Une dépendance FastAPI, qui ne couvre ni `StaticFiles` ni une route inconnue |
| `GUID.fullmatch` | La forme canonique seule | `uuid.UUID`, qui accepte accolades, `urn:uuid:` et tirets absents |
| `scope["path"]` | Le chemin du routeur | `request.url.path`, contourné par `/health%3F` |
| `CONTAINER_APP_NAME` pour borner les modes | Un fait de la plateforme | `KB_DEPLOYMENT_ENVIRONMENT`, posée à la main ; aucun mode local |
| `no-store` sur les pages | Décision de Sabine : rien de lisible après la déconnexion | `private, max-age=300` du plan (5 min lisibles) ; `private, no-cache`, sans revalidation garantie au bouton Retour (MDN) ; un cache en mémoire, perdu à zéro réplique |
| `/static` reste derrière le contrôle | Aucune exemption dans le contrôle (time-knight) | Exempter `/static` pour styler la 403 d'un autre compte : `allowedPrincipals` lui donne la 403 de la plateforme |
| Liens en chemin absolu | Indépendants des en-têtes `X-Forwarded-*` | `url_for`, qui prendrait `http` derrière l'entrée |
| Seuils `48rem` et `64rem` | Les maquettes donnent trois largeurs, pas de seuils | — (mon choix, accepté par time-knight) |
| Liens visités en `--color-slate` | Une couleur de la charte, contraste déjà testé (7,95:1) | Une couleur nouvelle, hors de la charte |
| Le mois en entier (« novembre ») | Opquast 4 | « nov. », une abréviation de plus pour la règle 5 |
| Motif GUID et règle des hôtes permis dans `core` | Une connaissance à un seul endroit (`code.md`) | Une troisième copie dans `web` |
| `jinja2>=3.1.6` en dépendance d'exécution | L'image (`uv sync --no-dev`) ne l'aurait pas | Le laisser venir par `pytest-html`, en développement seulement |

Ces choix sont imposés par une consigne du dépôt :
- les codes de sortie nommés (`poc.md`, règle 6) ;
- l'environnement lu une fois (`poc.md`, règle 2) ;
- le journal sans valeur reçue (`conventions.md`, règle 3) ;
- le test rouge avant le code (mission).

## 4. Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_path_that_only_reads_as_health_in_its_url_is_checked` : `/health%3F`, `/health%23x`, `/health%3Fa=1` → 200 avant la correction, 403 après | Le contrôle suit le chemin du routeur |
| `test_a_header_of_another_account_or_malformed_is_refused` (7 valeurs), `test_a_header_given_twice_is_refused` | Seule la forme canonique, présente une fois, passe |
| `test_a_refusal_is_logged_by_its_state_never_with_the_value`, `test_no_identity_header_reaches_the_log_or_a_page` | Ni l'identifiant reçu ni le nom de connexion ne vont au journal ou dans une page |
| `tests/web/test_settings.py` | `off` refusé hors de la boucle locale ou dans Container Apps ; `entra` refusé hors de la boucle sans `CONTAINER_APP_NAME` |
| `test_a_host_without_the_www_of_an_allowed_host_is_refused_never_redirected` : 307 → 400 | Aucune redirection construite en `http` |
| `test_every_answer_has_its_security_headers_and_its_cache` : `private, max-age=300` → `no-store` | Le cache décidé par Sabine, sur 200, 403, 404 et `/health` |
| `test_the_page_500_without_its_template_is_a_page_still_never_a_stack` : `text/plain` → `text/html` | Le repli de la 500, deux lignes `internal_error`, aucune pile ni message |
| `test_serve_web_listens_on_127_0_0_1_8002_by_default…` (`server_header: False`) ; `curl -si http://127.0.0.1:8002/sources` sans ligne `server` | Pas d'en-tête `Server` |
| `tests/web/test_templates.py` | Aucun `\|safe`, `Markup`, `url_for`, script, style en ligne ni attribut sans guillemets |
| `tests/web/test_accessibility.py`, `test_stylesheet.py` | Les critères RGAA/WCAG et les règles Opquast qu'un test peut voir |
| `uv run pytest` : 4491 passed ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` verts | Rien d'autre n'a cassé |
| Captures sous Chrome sans interface à 1280 et 820 px (`/sources`, 404, 500) | La 404 commence sous l'en-tête ; `/sources` est aligné sur le logo ; la note de la 500 est dans sa carte |
| `/security-review` : aucun constat au-dessus du seuil | La relecture n'a trouvé ni contournement, ni XSS, ni traversée de chemin |

## 5. Ce que tu dois pouvoir défendre

1. **« L'identifiant de Sabine n'est pas secret : quelqu'un ne peut-il pas poser l'en-tête lui-même ? »**
   Pas à travers la plateforme : en ligne, elle refuse cet en-tête venu d'un client et ne le pose qu'après la
   connexion Entra. Le contrôle du code est une seconde barrière, pas la seule
   (`operator_check.py:45-63`). La limite est assumée : sans l'authentification de la plateforme, il ne
   protège rien. Elle part donc dans le même déploiement que l'entrée externe, avec un `curl` forgé qui doit
   répondre 302 ou 401 (risque 1 de la PR).
2. **« Pourquoi `scope["path"]` et pas `request.url.path` ? »** Parce que le routeur suit `scope["path"]`.
   L'URL reconstruite se coupe au premier `?` : `/health%3F` aurait sauté le contrôle. Un test le prouve
   (`tests/web/test_operator_check.py:60`).
3. **« Que se passe-t-il si un texte d'une source contient du HTML ? »** Il sera échappé : `autoescape=True`
   pour tous les gabarits (`rendering.py:24`), et un test interdit `|safe` et `Markup`. La CSP sans script
   est une seconde barrière.
4. **« Le `no-store` n'est-il pas contraire à l'écoconception ? »** En partie : RGESN 6.2 n'est tenu que pour
   la CSS et l'icône. Une page pèse environ 1 Ko compressée, pour une seule lectrice. La sécurité passe
   d'abord (`code.md` : sécurité > lisibilité > simplicité) : aucune page lisible après la déconnexion. Un
   cache court côté serveur se tranche avec le fil (#563).
5. **« Pourquoi pas de JavaScript ? »** Décision de Sabine. Aucun script ne peut s'exécuter (CSP
   `default-src 'none'`), le site marche avec des liens et des formulaires GET, et le poids reste minimal
   (RGESN 4.5, 6.5).

## 6. Zones non vérifiées

- **La valeur réelle de l'en-tête en ligne** : la page ACA cite son nom, mais rien ne prouve encore qu'il porte
  l'identifiant d'objet. Le contrôle échoue fermé (403). Vérification prévue au premier déploiement : Sabine
  compare `/.auth/me` à `operatorObjectId`.
- **Une requête interne qui contournerait le sidecar d'authentification** : non vérifié, porté par l'infra.
- **Le rendu** :
  - pas vu à 390 ni 320 px : Chrome sans interface ne descend pas sous 500 px ;
  - pas de lecteur d'écran réel, pas de validateur Nu ;
  - ni Firefox, ni Safari, ni les couleurs forcées de Windows ;
  - le relecteur d'accessibilité a mesuré 922679d, pas la feuille de style de 1b017a8.
- **Ce que fait `/.auth/logout`**, la durée de la session de la plateforme et son cookie : à voir en ligne
  (Opquast 23, 29, 172).
- **L'en-tête `Server` que l'entrée d'Azure peut ajouter** : à voir en ligne.
- **Le comportement de `BaseHTTPMiddleware`** devant un WebSocket (il le laisse passer) est lu dans le code
  de Starlette, pas testé : le site n'a aucune route WebSocket.

## 7. Ce qui reste

- **Le fil (#563)** :
  - la lecture de l'API de données et son réveil ;
  - la pagination par 20 ;
  - le budget de poids et de requêtes (RGESN 6.1) ;
  - le choix d'un cache serveur (7.1) ;
  - la recherche (Opquast 168) ;
  - le test de `#8A8F96` réservé aux bordures.
- **Les détails et les tendances (#564)** :
  - le menu mobile ;
  - le plan du site (RGAA 12.1, Opquast 171) ;
  - GH Archive dans les sources ;
  - la ligne du registre pour les auteurs affichés.
- **#569** : retirer `Server: uvicorn` de `kb serve-data` et `kb serve-ai`.
- **La page de confidentialité** (Opquast 15), après l'oral blanc.
- **La minification de la CSS** (Opquast 229) : non tenue, faute d'outil sans dépendance nouvelle.
