# Servir le fil de veille sur l'accueil du site

- **Date** : 2026-11-11
- **Branche** : `feat/web-feed`, commits `ca6eaf0` à `a58a48a` et le commit de cette mise à jour, rebasés sur `main` à `0a6ba26`
- **Issue** : #563
- **Note précédente de la série** : [Ouvrir le socle du site privé](2026-11-11-ouvrir-le-socle-du-site-prive.md) (#562)
- **Fichiers principaux** : `src/k_b/web/data_api_client.py`, `src/k_b/web/feed.py`, `src/k_b/web/pages.py`,
  `src/k_b/web/templates/feed.html`, `src/k_b/web/static/site.css`, `src/k_b/commands/serve_web_command.py`,
  `src/k_b/web/settings.py`, `docs/site-web.md`, `docs/registre-traitements.md`

La liste des fichiers que donne le skill part d'un commit plus ancien que `main` : les commits antérieurs à
`0a6ba26` (#562, #550, #558, #423, #579, #582…) appartiennent à des PR déjà fusionnées, chacune avec sa note. Cette note ne
couvre que les commits de la branche.

## Le pourquoi

Le socle (#562) servait un accueil d'attente. Le livrable E4 demande une interface web fonctionnelle,
déployée et accessible ; l'oral blanc a lieu le 13/11. #563 met à sa place le fil « Quoi de neuf » des
maquettes du 09/11 : les items de cinq sortes (papiers, failles, alertes, releases, articles de
newsletters), filtrés par un formulaire, par pages de 20.

Le site ne lit jamais la base : il lit l'API de données par HTTP, avec la clé de son propre client `WEB`.
C'est la règle des couches de K-B (`conventions.md`, règle 5) et celle du paquet `web`, qui n'importe que
`core` et `items` (`tests/architecture/test_layers.py`). L'API de données reste la seule porte vers la base ;
le site n'est qu'un client de plus, au même titre que l'API IA.

## Le comment

### 1. Un client de l'API de données propre au site

`web` ne peut pas importer le client de l'API IA (`ai_api/connectors/data_api_client.py`) : il a le sien.
Il fait un seul `GET /items` par page et lit la réponse par un modèle fermé.

```python
class FeedItemPage(DataApiModel):
    # A kind out of the five, zotero_entry or clip, is refused here.
    items: list[Annotated[FeedItem, Field(discriminator="kind")]]
    total: Annotated[int, Field(ge=0)]
```
`src/k_b/web/data_api_client.py:126`

`FeedItem` est l'union des cinq modèles de sortes, discriminée par `kind` : une entrée Zotero ou un clip
dans la réponse fait échouer la lecture (`data_api_invalid_response`), donc la page 500, jamais leur
affichage. `DataApiModel` est `strict=True` (un type faux est refusé, jamais converti) et
`extra="ignore"` (un champ que l'API ajoute ne fait pas tomber le fil).

```python
    params: dict[str, str | int | list[str]] = {
        "kind": list(query.kinds),
        "since": format_day(query.since_day),
        "limit": FEED_PAGE_SIZE,
        "offset": query.offset,
    }
```
`src/k_b/web/data_api_client.py:188`

`kind` est **toujours** envoyé : sans lui, l'API servirait aussi `zotero_entry` et `clip`. Le même interdit
est donc tenu deux fois, à la demande et à la réponse (défense en profondeur). `since` est écrit par
`core/dates.format_day`, qui passe par `isoformat` : `strftime` laisse la largeur de l'année à la
bibliothèque C, et sous Linux l'an 1 s'écrirait `1`, refusé par l'API (revue de code, constat 6).

Les délais : 5 s de connexion, 30 s de lecture, 10 s d'écriture, 5 s d'attente du pool, une échéance de
35 s vérifiée entre deux morceaux du corps, et un corps borné à 1 Mo. Chaque échec devient un état nommé,
relevé `from None` pour que l'exception d'httpx2, qui cite l'URL, ne suive pas :

```python
    except httpx2.TimeoutException:
        raise DataApiError("data_api_timeout") from None
    except httpx2.TransportError:
        raise DataApiError("data_api_unavailable") from None
```
`src/k_b/web/data_api_client.py:219`

### 2. Le formulaire, lu sans entrée ni sortie

`web/feed.py` ne fait aucun appel : il lit le formulaire, calcule la requête, les pages et les cartes. On le
teste donc sans serveur (`tests/web/test_feed.py`, 80 cas environ).

```python
def read_page_number(params: QueryParams) -> int | None:
    """The page asked, 1 without one; None for a page out of its form or beyond MAX_PAGE."""
    values = params.getlist(PAGE_FIELD)
    if not values:
        return 1
    if len(values) > 1 or not PAGE_NUMBER.fullmatch(values[0]):
        return None
```
`src/k_b/web/feed.py:186`

`PAGE_NUMBER` vaut `[1-9][0-9]{0,2}` (`feed.py:67`) : ni `01`, ni `+1`, ni un chiffre pleine largeur (`[0-9]`
ne prend que l'ASCII). `MAX_PAGE` vaut 501, la page de l'`offset` 10 000 de l'API (`feed.py:69`). Une page
refusée rend `None`, que la route change en 404 avant tout appel.

La période part toujours d'un jour UTC :

```python
    today = now.astimezone(UTC).date()
    return today - timedelta(days=DAYS_BY_PERIOD[form.period])
```
`src/k_b/web/feed.py:291`

« 1 jour » donne hier : le fil prend hier et aujourd'hui, en jours UTC. `now` vient d'une horloge injectée
(`app.state.clock`), ce qui rend les tests indépendants du moment où ils tournent.

Ce que le formulaire réaffiche passe aussi par lui (second passage de la revue de code) :
- une recherche qui porte un caractère de contrôle (catégorie Unicode `Cc`) est refusée, puis réaffichée sans
  lui : renvoyé brut dans `value` et dans les liens de page, il rendrait le HTML invalide ;
- la date de début n'est réaffichée que sous la forme `AAAA-MM-JJ`, jamais brute, quelle que soit sa longueur.

### 3. La route lit les paramètres bruts

```python
@router.get(FEED_PATH)
def show_feed(request: Request) -> Response:
    """The watch feed: a page of 20 items of the filters of its form, the most recent first."""
    page = read_page_number(request.query_params)
    if page is None:
        return render_error_page(request, 404)
    form = read_feed_form(request.query_params)
    if form.errors:
        return render_feed(request, form, form.errors, None)
```
`src/k_b/web/pages.py:43`

La route ne déclare aucun paramètre typé (`page: int = 1`) : FastAPI répondrait alors à `page=abc` par son
422 en JSON, qui recopie la valeur reçue. Lire `request.query_params` brut garde chaque refus dans une page
HTML du site. La suite de la route est une recette : un champ refusé rend le fil en 422 avec ses messages ;
un échec de l'API rend la page 500, sauf un 422 sur `q`, que `find_api_field_error` (`feed.py:305`) met sur
son champ ; une page au-delà de la dernière rend la 404.

`log_data_api_failure` (`pages.py`) écrit `data_api_failed: <état> http_status=<n|-> request_id=<id>` : ni
`q`, ni l'URL, ni le corps.

### 4. Les cartes et leurs liens

Une carte donne la sorte, la date au mois en lettres, la pastille « Exploitée (KEV) », les identifiants,
le titre et le lien vers la source. Le lien ne passe que par une seule fonction :

```python
    if (
        url is None
        or not url.startswith("https://")
        or not url.isprintable()
        or " " in url
    ):
        return None
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return None
```
`src/k_b/web/feed.py:423`

Elle refuse `javascript:`, `data:`, `http:`, une adresse précédée d'une espace (que `urlsplit` aurait
acceptée en la retirant), un caractère invisible (`isprintable` est faux pour un contrôle) et, depuis la
revue de code (constat 1), un hôte que `urlsplit` ne sait pas lire (`https://[oops/x`) : il levait
`ValueError` et faisait tomber tout le fil en 500. Une URL refusée donne une carte sans lien, jamais une
erreur. Le gabarit échappe ensuite chaque valeur (`autoescape=True`, socle), et la CSP bloquerait un script
de toute façon.

```html
<h2 class="card-title"{% if card.title_lang %} lang="{{ card.title_lang }}"{% endif %}>{{ card.title }}</h2>
```
`src/k_b/web/templates/feed.html:81`

Le titre d'un papier, d'une faille, d'une alerte et d'un article est en `lang="en"` (RGAA 8.7) : les sources
écrivent en anglais. Celui d'une release (un dépôt et une version) ne l'est pas.

### 5. Le réveil de l'API au démarrage

En ligne, l'API de données dort à zéro réplique et met 20 à 26 s à se réveiller (#414).

```python
    threading.Thread(
        target=lambda: wake_data_api(base_url), name="wake-data-api", daemon=True
    ).start()
```
`src/k_b/commands/serve_web_command.py:36`

Au démarrage, `kb serve-web` lance un `GET /health` dans un fil à part : l'API se réveille pendant que
Sabine se connecte par Microsoft Entra. Le fil est `daemon` : il n'empêche pas le processus de s'arrêter.
La `lambda` laisse un test remplacer `wake_data_api` dans le module, si bien qu'aucun test ne touche le
réseau. Le journal donne `data API wake-up: health ok` ou l'état de l'échec, jamais l'URL. Sur le Mac, la
ligne `health ok` a été vue au démarrage.

### 6. Accessibilité et poids, prouvés par du code

`tests/web/test_accessibility.py` rend le fil dans quatre états (normal, page 2, vide, refusé), lit le HTML
par le parseur de la bibliothèque standard et vérifie, entre autres :

- un `label` lié à chacun des 11 champs ;
- un `fieldset` et sa `legend` pour chaque groupe ;
- chaque `aria-describedby` qui nomme un élément de la page ;
- l'erreur lue avant l'aide ;
- les champs refusés en `aria-invalid` ;
- le résumé des erreurs, qui mène à chaque champ ;
- deux `nav` nommées.

`test_the_screen_of_the_feed_holds_three_requests_and_30_kb_at_most` (`tests/web/test_feed_page.py`) tient
le budget D2 : la page, la CSS et l'icône, 30 Ko au plus.

## Choix faits et options écartées

Les décisions sont au journal ADR, 2026-11-11, « Site : le fil de veille (#563) ». En bref :

| Choix | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Aucun cache des réponses de l'API (D1, Sabine) | une seule lectrice, un cache perdu à chaque retour à zéro réplique, taille M avant l'oral | un cache en mémoire de 5 min : 40 lignes, taille L |
| 3 requêtes et 30 Ko par écran (D2, Sabine) | RGESN 6.1, mesuré par un test | aucun budget |
| « 1 jour » par défaut (D3, Sabine) | la maquette | 7 jours |
| La date de début ne compte qu'avec « Date » (D4, Sabine) | sinon, on ne revient plus à « 3 jours » sans vider le champ | la date remplie l'emporte |
| Le registre nomme le site dès #563 (D5, Sabine) | le fil met en ligne le nom des dépôts suivis, qui contient un login | attendre #564 |
| Un client à lui, 30 s de lecture | `web` n'importe que `core` et `items` ; 30 s couvrent le réveil | les 10 s du client de l'API IA |
| Les paramètres lus bruts | le 422 JSON de FastAPI recopie la valeur | des paramètres typés |
| « Voir la fiche sur nvd.nist.gov » (time-knight) | un nom de domaine dit la destination | « Voir la fiche NVD », une abréviation (Opquast 5) |
| « TLDR AI » par une table des éditions (time-knight) | la maquette ; les noms du titre `h1` de TLDR | le slug « TLDR ai » |
| Pas de pastille sur une faille retirée (Sabine) | elle contredisait la ligne « retirée du catalogue » | la garder, au sens d'`exploited` |
| Deux aides de plus que la maquette (time-knight) | WCAG 3.3.2 : sans script, `required` ne dit pas une obligation conditionnelle | rien écrit avant l'envoi |
| Les bornes de l'API recopiées dans `core/config.py`, gardées égales par un test | `src/k_b/data_api/` est à la piste A | les importer dans l'API de données |

Limites assumées, écrites dans la PR (tranchées par time-knight) :
- un item hors du modèle fermé fait de toute la page une page 500, sans dire lequel ;
- `q`, `period` ou `start` répété garde sa dernière valeur, alors qu'une `page` répétée rend la 404 ;
- une alerte dont la CVE a quitté le catalogue garde sa pastille, la liste ne servant pas ce retrait (#564) ;
- le lien d'un article de newsletter ne dit pas la langue de l'article, que K-B ne connaît pas.

Imposés par les règles du dépôt :

- le modèle fermé et la validation à la frontière (`code.md`, « Sécurité dès la conception ») ;
- un journal sans valeur reçue (`conventions.md`, règle 3) ;
- la lecture de l'environnement par `environ` (`poc.md`, règle 2).

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_feed_reads_the_five_kinds_of_the_real_data_api_never_a_zotero_entry_nor_a_clip` (`tests/web/test_site_data_api_client.py`) | le client lit la vraie API, sur sa base de test : 14 items, cinq sortes |
| `test_a_kind_out_of_the_five_is_refused` (même fichier) | un `clip` dans la réponse est refusé |
| `test_each_answer_but_a_page_is_a_named_state`, `test_a_failure_of_the_transport_is_a_named_state` | 401, 429, 5xx, 404, redirection, hors schéma, délai : chacun son état |
| `test_an_error_never_quotes_the_url_nor_the_key` | l'erreur ne garde ni l'URL ni la clé |
| `test_a_page_number_out_of_its_form_or_beyond_501_is_none` (`tests/web/test_feed.py`) | `01`, `+1`, `abc`, `502`, `１` refusés |
| `test_a_url_out_of_https_gives_no_link` | `http`, `javascript:`, une espace, `//`, `[oops` : pas de lien |
| `test_a_failure_of_the_data_api_is_the_page_500_logged_without_the_search` (`tests/web/test_feed_page.py`) | page 500, et la ligne de journal sans la recherche |
| `test_a_title_received_is_escaped_never_a_tag` | un titre `<script>` est rendu en texte |
| `test_the_screen_of_the_feed_holds_three_requests_and_30_kb_at_most` | le budget D2 |
| `test_serve_web_wakes_the_data_api_at_its_start`, `test_the_wake_up_logs_its_state_never_the_url` (`tests/web/test_serve_web.py`) | le réveil est lancé, et son journal ne cite pas l'URL |
| Sur le Mac, `kb serve-data` sur la base de fixture et `kb serve-web` en `KB_WEB_AUTH=off` | `data API wake-up: health ok` ; fil vide en 200 ; 14 cartes depuis 2020 ; 404 au-delà ; 422 sur `kind=clip` |
| La même chose, API arrêtée | page 500, `data_api_failed: data_api_unavailable http_status=- request_id=…`, sans la recherche |
| Captures à 320 px (dans un `iframe`) et à 1280 px | la page tient sans défilement horizontal ; deux défauts vus et corrigés (`b560c83`) |
| `uv run pytest` → 4711 passed ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` | les contrôles du dépôt |

Les tests ont été écrits avant le code, et leur échec a été montré dans la session. Trois exceptions sont
dites telles quelles :

- le test de l'année sur quatre chiffres passait déjà sur le Mac, il ne rougirait que sous Linux ;
- les réglages de l'accès à l'API ont été codés avant leurs propres tests ;
- les premiers tests d'accessibilité du fil ont été écrits après son gabarit.

## Ce que tu dois pouvoir défendre

**Pourquoi le site ne lit-il pas la base ?** Parce que l'API de données est la seule porte vers la base :
elle borne les requêtes, applique sa clé et son débit, et ne sert que des champs en liste blanche. Le site
n'importe que `core` et `items`, et un test d'architecture le tient (`tests/architecture/test_layers.py`).

**Comment un titre piégé ou un lien `javascript:` venu d'une source est-il neutralisé ?** Par trois
contrôles successifs :
- le gabarit échappe toute valeur (`autoescape=True`) ;
- un lien n'est écrit que s'il est en `https` vers un hôte lisible (`keep_https_link`, `feed.py:419`) ;
- la CSP interdit tout script.

Les tests `test_a_title_received_is_escaped_never_a_tag` et `test_a_url_out_of_https_gives_no_link` en font la
preuve.

**Que se passe-t-il si l'API de données dort ou plante ?** Le site la réveille à son démarrage, et sa
lecture attend jusqu'à 30 s par étape, assez pour un réveil. Au-delà, ou sur une erreur, la page 500
s'affiche avec l'heure et l'identifiant de la demande, et le journal écrit l'état sans la recherche. Au
pire, l'attente dure environ 70 s : les délais bornent chaque étape, pas la requête entière (`docs/site-web.md`, « Le client »).

**Pourquoi pas de cache, alors que l'écoconception le recommande ?** C'est la décision D1 de Sabine,
écrite : une seule lectrice, un appel bref, et un cache que chaque retour à zéro réplique viderait. RGESN 7.1
est donc non tenu, par décision, et non par oubli.

**Comment sait-on qu'une entrée Zotero ne s'affiche jamais ?** `kind` est toujours envoyé avec les cinq
sortes, `kind=clip` dans l'adresse est refusé sans appel à l'API, et la réponse est lue par une union fermée
aux cinq sortes. Trois tests le prouvent :
- `test_a_kind_out_of_the_five_is_refused` ;
- `test_a_kind_out_of_the_five_is_refused_in_html_without_asking_the_api` ;
- `test_the_query_sends_the_five_kinds_a_page_of_20_its_offset_and_since_in_utc`.

## Zones non vérifiées

- **L'arrêt sur SIGTERM** : le client HTTP se ferme quand `uvicorn.run` rend la main (`with`). Le test ne
  vérifie que la fermeture après un `uvicorn.run` simulé, pas un vrai SIGTERM ; qu'uvicorn rende la main
  après son arrêt propre est supposé, pas mesuré ici.
- **Le zoom à 200 %, l'espacement du texte, le clavier, le lecteur d'écran, Safari et le validateur
  W3C** : non contrôlés. Le relecteur d'accessibilité les juge probablement tenus d'après le code, sans
  pouvoir le prouver.
- **Les captures à 320 et 390 px** : Chrome sans tête impose une fenêtre d'environ 500 px. La page a donc
  été rendue dans un `iframe` de 320 px, sur une copie locale, sans les en-têtes du serveur.
- **Le poids de la page dans le test D2** : le test recompresse le HTML par `gzip.compress`, une
  approximation de ce qu'envoie `GZipMiddleware` ; pour la CSS et l'icône, il lit les octets reçus.
- **« Un appel d'environ 20 ms »** (pourquoi de D1) : c'est une estimation du plan, pas une mesure en ligne.
- **L'entrée interne d'Azure Container Apps pendant le réveil** : qu'elle garde la requête 20 à 26 s n'est
  pas vérifié ; tn-codeur le constatera en ligne.
- **La langue des titres sur des données réelles** : un titre de release peut être une phrase anglaise non
  marquée, et un papier arXiv écrit dans une autre langue est marqué `en`.

## Ce qui reste

- **#564** : le détail de chaque sorte et le lien du titre vers lui, la page des tendances, le menu mobile
  sans JavaScript, le bandeau à trois états d'une alerte (il dira aussi le retrait d'une CVE du catalogue,
  que la liste ne sert pas), et les auteurs d'un papier au registre.
- **La mise en ligne**, par tn-codeur : le secret `KB_DATA_API_KEY_WEB`, de même valeur dans `ca-kb-web` et
  `ca-kb-data-api`, et `KB_DATA_API_URL`, l'URL interne en `https`.
- **La factorisation du GET borné** (troisième copie, revue de code, constat 10), dans une issue à faire
  après l'oral et après #565.
- **« Le tri du fil »** reste une décision ouverte au journal ADR (2026-11-11, #550).
