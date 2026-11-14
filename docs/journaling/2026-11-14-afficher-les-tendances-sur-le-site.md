# Afficher les tendances sur le site

- **Date** : 2026-11-14
- **Branche** : `feat/web-trends`, commits `8d656f7` à `69a7feb`, sur `origin/main` à `690a63f`
- **Issue** : #596 (PR 2 du découpage de #564)
- **Série** : suite de [Servir le fil de veille](2026-11-11-servir-le-fil-de-veille.md) (#563) et
  d'[Afficher le détail d'un item](2026-11-12-afficher-le-detail-d-un-item.md) (#564)
- **Fichiers principaux** :
  - `src/k_b/web/trends.py` (nouveau) et `src/k_b/web/templates/trends.html` (nouveau) ;
  - `src/k_b/web/data_api_client.py` (`read_trends`, `TrendWindow`), `src/k_b/web/pages.py` (`show_trends`),
    `src/k_b/web/feed.py` (`read_written_day`), `src/k_b/web/static/site.css` ;
  - la navigation (`base.html`), la 404, `/sources` et la déclaration d'accessibilité ;
  - les tests : `tests/web/test_trends.py`, `tests/web/test_trends_page.py`, `tests/web/test_accessibility.py`,
    `tests/web/test_stylesheet.py`, `tests/web/test_site_data_api_client.py`, `tests/web/test_site_on_the_data_api.py`,
    et l'aide commune du budget, `tests/web/screen_weight.py`.

La liste des commits et des fichiers donnée à la note compare la branche au `main` local, en retard. Les commits
jusqu'à `690a63f` et les fichiers `docs/stockage.md`, `docs/specs-collecte.md`, `docs/fiches-veille.md`,
`item_detail.py`, `received_text.py`, `item.html`, `uv.lock` et les notes du 12/11 et du 13/11 viennent des PR
déjà fusionnées (#601, #607, #608, #609, #610). Ils ne sont pas de cette branche, et cette note ne les couvre pas.
`git diff --stat 690a63f..69a7feb` donne les 25 fichiers de la branche.

## Le pourquoi

K-B collecte chaque jour, dans GH Archive, les dépôts GitHub qui gagnent le plus d'étoiles et de *forks* sur une
fenêtre de 3 jours. L'API de données les sert par `GET /trends`, mais jusqu'ici seuls `kb` et l'API IA les
lisaient. Les maquettes du 09/11 prévoient une page « Dépôts qui ont le vent en poupe » sur le site. C'est le
dernier morceau de l'étape 1 de la mission : le socle, le fil, les détails, les tendances.

Cette PR ajoute `/tendances` : la fenêtre la plus récente, ou celle qui se termine le jour choisi dans un
formulaire. La page montre un tableau (rang, dépôt lié à GitHub, étoiles et *forks* gagnés), relié à la navigation
et à la page 404. Comme le fil, le site ne lit que l'API de données, par la clé de son client `WEB`, et ne garde
rien.

## Le comment

### 1. Le client : une fenêtre validée, et jamais une autre que celle demandée

Le site ne fait pas confiance à l'API de données : sa réponse est une entrée externe, validée à la frontière
(`code.md`, « Sécurité dès la conception »). `TrendWindow` est un modèle Pydantic fermé.

```python
class TrendWindow(DataApiModel):
    window_end: Annotated[date, Field(ge=FIRST_WINDOW_END)]
    # A window exists by its rows only: GET /trends answers 404 without one.
    trends: Annotated[list[Trend], Field(min_length=1, max_length=MAX_TRENDS)]
```
(`src/k_b/web/data_api_client.py:204-207`)

- Au plus `MAX_TRENDS` lignes, soit 60 : les 30 premiers par étoiles et les 30 premiers par *forks*
  (`2 * GH_ARCHIVE_TOP_SIZE`). Au-delà, la réponse est hors contrat.
- `FIRST_WINDOW_END` : le site écrit le premier jour de la fenêtre, 2 jours avant son dernier. Une fenêtre qui
  finirait avant le 3 janvier de l'an 1 aurait un premier jour qui n'existe pas en Python (`date.min`).
- Chaque `Trend` a un `repository_name` de type `RepositoryName` (`items.py`, le même type que la base) et des
  comptes entre 0 et 2⁶³ − 1.

Puis une seconde garde, après la validation :

```python
    # The window of the day asked or 404 (docs/specs-api.md): never another shown as its answer.
    if window_end is not None and window.window_end != window_end:
        raise DataApiError("data_api_invalid_response", status)
```
(`src/k_b/web/data_api_client.py:324-326`)

Le contrat de l'API dit : la fenêtre du jour demandé, ou 404. Une réponse valide mais d'un autre jour ne doit
jamais s'afficher comme la réponse à la question posée : le titre et la légende diraient une fenêtre, le tableau
en montrerait une autre. Ce cas devient une erreur nommée, donc une page 500.

### 2. La route : quatre issues, chacune nommée

```python
    form = read_trends_form(request.query_params)
    if form.error:
        return render_trends(request, build_refused_page(form.error))
    try:
        window = read_trends(request.app.state.data_api_client, form.window_end)
    except DataApiError as error:
        if error.state == "data_api_trend_window_not_found":
            return render_trends(request, build_missing_window_page(form.window_end))
        field_error = find_api_window_end_error(error)
        if field_error is None:
            log_data_api_failure(request, error)
            return render_server_error_page(request)
        return render_trends(request, build_refused_page(field_error))
    return render_trends(request, build_trends_page(window))
```
(`src/k_b/web/pages.py:144-157`)

La fonction se lit comme une recette, avec les arrêts tôt :

1. **Un jour refusé par le site** : page en 422, message sous le champ, et aucun appel à l'API.
2. **Un 404 `trend_window_not_found`** : page en 200 qui dit « Aucune tendance pour la fenêtre qui se termine
   le … », avec un lien vers la plus récente ; sans jour, « Aucune tendance en base. ».
3. **Un 422 de l'API sur `window_end` seul** : le même message lié au champ (« La base de K-B refuse cette
   date »). Tout autre refus vient du site, qui n'envoie que ce paramètre : c'est une erreur, pas un champ à
   corriger.
4. **Tout le reste** (5xx, 429, délai, réponse hors contrat) : page 500, journalisée par l'état et le statut
   HTTP, jamais par le jour demandé.

Le commentaire de la ligne 140 dit pourquoi `window_end` n'est pas un paramètre typé de FastAPI : un 422 de
FastAPI citerait la valeur reçue dans sa réponse. Le site la lit brute et décide lui-même, comme le fil.

### 3. Le jour : une seule règle pour le fil et les tendances

```python
def read_written_day(value: str) -> date | None:
    """The day of a field input type=date, the start of the feed or the end of a window of the
    trends; None for any other value."""
    try:
        return WRITTEN_DAY.validate_python(value)
    except ValidationError:
        return None
```
(`src/k_b/web/feed.py:261-267`, avec `WRITTEN_DAY = TypeAdapter(WrittenDay)` à la ligne 85)

Avant cette PR, le fil acceptait au réaffichage toute chaîne de la forme `\d{4}-\d{2}-\d{2}` : `2026-02-30`
revenait dans le champ, alors qu'un `input type=date` ne tient qu'un jour valide ou rien (WHATWG). Désormais le
fil et les tendances passent par `WrittenDay` (`items.py:214`), la règle des routes de l'API de données : la forme
`AAAA-MM-JJ` et un jour qui existe. Une seule connaissance, à un seul endroit (`code.md`, « Duplication »).

### 4. La page sans entrée ni sortie : rang, début de fenêtre, lien vers GitHub

`web/trends.py` ne fait ni réseau ni rendu : il reçoit une `TrendWindow` et rend un `TrendsPage`, des données que
le gabarit affiche. Trois choses que l'API ne sert pas sont calculées par le site (écarts connus de la mission) :

- **le rang** : la position dans l'ordre de l'API, à partir de 1 (`enumerate(window.trends, start=1)`,
  `trends.py:123`) ;
- **le premier jour** : `window_end - timedelta(days=GH_ARCHIVE_WINDOW_DAYS - 1)` (`trends.py:98-100`) ;
- **le lien** :

```python
def build_github_link(repository_name: str) -> str | None:
    if not is_repository_name(repository_name):
        return None
    return f"{GITHUB_URL}/{repository_name}"
```
(`src/k_b/web/trends.py:136-142`, docstring retirée de l'extrait)

`RepositoryName` permet `owner/..` : un navigateur résoudrait `https://github.com/owner/..` vers une autre page de
GitHub. `is_repository_name` refuse ces segments. Un tel nom garde sa ligne et son rang, écrit sans lien. Écarter
toute la fenêtre pour un seul nom aurait caché 59 lignes justes et faussé le rang des autres (tri du second
`/code-review`).

Les comptes sont écrits à la française, les milliers groupés par une espace fine insécable
(`write_count`, `trends.py:103-104`, `chr(0x202F)` et jamais un échappement dans la source : `MEMORY.md`,
« Échappements »).

### 5. Le tableau : un vrai tableau de données, lisible au clavier et au lecteur d'écran

```html
<div class="table-frame" role="region" aria-labelledby="trends-caption" tabindex="0">
<table class="trends-table">
<caption id="trends-caption">Fenêtre du <time …>…</time> au <time …>…</time>: étoiles et …</caption>
…
<tr><td class="rank">{{ row.rank }}</td><th scope="row">{% if row.link %}{{ external_link(…) }}…</th>…
```
(`src/k_b/web/templates/trends.html:25-33`, abrégé)

- `caption` en tête du tableau, `th scope="col"` pour chaque colonne avec les mots de la maquette (« Étoiles
  gagnées », « *Forks* gagnés »), et le dépôt de chaque ligne en `th scope="row"` : un lecteur d'écran annonce
  le dépôt avec chaque compte (RGAA 5.4, 5.6 et 5.7).
- Les deux jours de la fenêtre en `<time datetime>`, le mois en lettres (Opquast 4 et 231).
- Le lien passe par la macro `external_link` (`templates/links.html`) : nouvel onglet annoncé « (en anglais, site
  externe, nouvel onglet) », `rel="noopener noreferrer"`. L'annonce reste visible (décision de Sabine du
  2026-11-14).
- Le cadre défile au clavier sans script : il prend le focus (`tabindex="0"`) et forme une région nommée par la
  légende (WCAG 2.1.1).

### 6. La mise en page : 560 px, un cadre qui défile, une légende qui reste en vue

```css
  .table-frame {
    margin-block-end: 1rem;
    padding-block-end: 0.375rem;
    overflow-x: auto;
    container-type: inline-size;
    …
  }
  .trends-table {
    inline-size: 100%;
    min-inline-size: 35rem;
    …
    & caption {
      max-inline-size: 100cqi;
```
(`src/k_b/web/static/site.css:898-916`, abrégé)

- **`min-inline-size: 35rem`** : 560 px au moins, comme la maquette (`min-width: 560px` dans
  `Maquette-tendances.dc.html`, décision de Sabine du 2026-11-14). Sur un écran plus étroit, le tableau défile dans
  son cadre (`overflow-x: auto`) au lieu d'élargir la page. WCAG 1.4.10 exempte un tableau de données.
- **`container-type: inline-size` et `100cqi`** : sans eux, la légende, qui fait partie du tableau, aurait ses
  560 px et sortirait de l'écran à 320 px. Le cadre devient un conteneur, et `100cqi` vaut sa largeur : la légende
  se replie dans ce qui se voit.
- **`padding-block-end: 0.375rem`** : un cadre qui défile coupe ce qui dépasse ses bords, l'anneau de focus du
  dernier lien compris (3 px à 2 px du lien, `:focus-visible`). Les 6 px du bas le gardent en vue.
- **`td.number { white-space: nowrap }`** : un compte ne se coupe jamais, mais l'en-tête « Étoiles gagnées » se
  replie sur un écran étroit.
- **À l'impression**, le cadre ne défile plus (`overflow: visible`). La flèche et l'annonce des liens sont
  retirées du tableau seulement : sur papier, aucun lien n'ouvre d'onglet, et l'annonce se répéterait à chaque
  ligne.

## Choix faits et options écartées

| Sujet | Retenu | Écarté, et pourquoi |
|---|---|---|
| Largeur du tableau | 560 px au moins, comme la maquette, défilement dans le cadre (Sabine, 14/11) | La largeur naturelle : le tableau ne défilait que pour un nom aux longueurs maximales, mais les colonnes se tassaient sur téléphone, loin de la maquette |
| Unité des 560 px | `35rem`, comme toutes les tailles de la feuille (`47.5rem` pour les 760 px du détail) | `560px` : seule taille en px hors des bordures ; et `rem` suit le réglage de taille de texte du navigateur |
| Légende bornée | `container-type` et `100cqi`, Baseline « widely available » (fonction « Container queries » de web-features depuis le 2025-08-14 ; Chrome et Edge 105, Firefox 110, Safari 16 pour les unités, caniuse, lus le 14/11) | `calc(100vw - …)` : dépend des marges de la page, à recalculer à chaque changement de gouttière, et `100vw` compte la barre de défilement de la page |
| Annonce du nouvel onglet | visible (Sabine, 14/11, option (a) de time-knight) | Dans le seul nom accessible, expliquée sous le tableau : une personne voyante ne saurait pas, au moment du clic, qu'un onglet s'ouvre |
| En-tête de ligne | le dépôt (`th scope="row"`), en graisse normale (tri de time-knight) | Le rang : un numéro ne nomme pas une ligne ; aucun en-tête de ligne : le lecteur d'écran n'annoncerait pas le dépôt avec ses comptes |
| Masquer la flèche à l'impression | sélecteur `.trends-table a > span[aria-hidden="true"]`, limité au tableau | Une classe nouvelle dans la macro `external_link` : toucherait tous les liens externes du site et leurs tests, pour un besoin du seul tableau |
| Nom refusé par `is_repository_name` | sa ligne et son rang, sans lien | Écarter toute la fenêtre (page 500) : un seul nom cacherait 59 lignes justes |
| Fenêtre d'un autre jour que celui demandé | page 500 (`data_api_invalid_response`) | L'afficher : la page dirait une fenêtre et en montrerait une autre |
| `window_end` | lu brut par la route | Paramètre typé de FastAPI : son 422 citerait la valeur reçue |
| « Voir la fenêtre la plus récente » | bouton secondaire (gardé par time-knight) | Lien simple de la maquette : l'écart est écrit dans la PR |
| Pas de « jusqu'à 60 dépôts » | consigne de la mission du 11/11 | — |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_latest_window_is_a_table_of_its_rows`, `test_the_window_asked_sends_its_day` (`test_trends_page.py`) | la fenêtre la plus récente sans jour, `window_end` envoyé avec un jour |
| `test_a_day_refused_gives_the_page_in_422_without_asking_the_data_api` | un jour refusé ne coûte aucun appel à l'API |
| `test_a_window_other_than_the_day_asked_gives_the_page_500` | une fenêtre d'un autre jour n'est jamais montrée |
| `test_a_name_is_repository_name_refuses_keeps_its_row_and_its_rank_without_a_link` (`test_trends.py`) | `owner/..`, `./repo`, `owner/foo..bar` : ligne et rang gardés, aucun lien |
| `test_a_failure_of_the_data_api_gives_the_page_500_logged_without_the_day` | le journal ne cite pas le jour demandé |
| `test_the_screen_of_the_trends_holds_three_requests_and_30_kb_at_most` | 60 lignes aux longueurs maximales de GitHub : 3 requêtes, 30 Ko au plus (RGESN 6.1) |
| `test_the_table_of_the_trends_has_its_caption_and_a_header_for_each_column` (`test_accessibility.py`) | légende en tête, `th scope="col"` avec les mots de la maquette, `th scope="row"` dans chaque ligne |
| `test_the_frame_of_the_table_scrolls_by_the_keyboard_named_by_its_caption` | cadre au clavier, région nommée par la légende |
| `test_the_caption_of_the_table_wraps_in_the_width_of_its_frame`, `test_the_frame_keeps_the_focus_ring_of_its_last_link_in_sight`, `test_a_table_printed_drops_the_announcement_of_its_links` (`test_stylesheet.py`) | les règles CSS des corrections du 14/11 sont là ; les 8 tests nouveaux ou adaptés étaient rouges avant le code |
| Mesure dans Chrome sans interface, iframes de 320 à 1280 px (9 largeurs), fixture et pire cas (nom de 39 + 100 caractères, comptes de 19 chiffres) | 0 px de débordement de page sur les 18 rendus ; sous 600 px, tableau à 560 px dans un cadre qui défile ; légende de la largeur du cadre ; 2 px de marge sous l'anneau du dernier lien ; aucun défilement vertical du cadre |
| `pdftotext` du PDF imprimé par Chrome | ni « ↗ » ni « nouvel onglet » dans le tableau imprimé |
| `uv run pytest` | 5290 passed (ruff `--no-cache`, format, mypy `--strict` verts) |

## Ce que tu dois pouvoir défendre

1. **« Pourquoi le site recalcule-t-il le rang et le premier jour au lieu de les demander à l'API ? »**
   L'API sert l'ordre et le dernier jour, pas le rang ni le début (contrat de `GET /trends`, `docs/specs-api.md`).
   Les calculer dans `web/trends.py`, sans entrée ni sortie, les rend testables seuls (`test_trends.py:99`,
   `:111`), sans changer l'API, que tient une autre piste.
2. **« Un tableau de 560 px sur un téléphone de 320 px, ce n'est pas un défaut d'accessibilité ? »**
   WCAG 1.4.10 (*Reflow*) exempte le contenu qui demande une mise en page en deux dimensions, comme un tableau de
   données. La page ne défile pas en largeur : seul le cadre défile, au clavier aussi (`tabindex="0"`, région
   nommée), et la légende reste lisible (`100cqi`). Mesuré de 320 à 1280 px.
3. **« Où est la sécurité, puisque la page affiche des noms venus de GitHub ? »**
   Trois couches : la réponse validée par un modèle fermé (`RepositoryName`, 60 lignes au plus, comptes bornés) ;
   le lien bâti seulement si `is_repository_name` l'accepte ; l'échappement automatique de Jinja2, sans `|safe`
   (tenu par les tests de `tests/web/`). Le lien s'ouvre avec `noopener noreferrer` : la page ouverte n'atteint
   ni la page de K-B ni son adresse.
4. **« Que se passe-t-il si l'API renvoie la fenêtre du 9 octobre quand on demande le 10 ? »**
   Page 500, journalisée `data_api_invalid_response` (`data_api_client.py:325`). Le site ne montre jamais une
   réponse à une autre question que celle posée.
5. **« Pourquoi `container-type` et `cqi`, une fonction récente ? »**
   Elle est Baseline « widely available » depuis le 2025-08-14 : disponible dans les navigateurs principaux
   depuis plus de 30 mois. Elle borne la légende à la largeur réelle du cadre, sans calcul qui dépende des marges
   de la page.

## Zones non vérifiées

- **Le comportement de `max-inline-size` sur un `caption`** n'est pas cité d'une spécification : il est mesuré
  dans Chrome seulement (légende de la largeur du cadre de 320 à 600 px). Firefox et Safari ne sont pas mesurés.
- **Le statut Baseline des unités `cqi` elles-mêmes** est déduit : la page de web-features explorer de « Container
  queries » (Baseline depuis le 2025-08-14) renvoie à la table caniuse des unités, dont les premières versions sont
  celles de `@container`. La liste des clés de compatibilité de la fonction n'a pas été lue.
- **Le pire cas à 390 px** : avec deux comptes de 19 chiffres, qui ne se coupent jamais, la colonne du dépôt garde
  environ 60 px, et un nom de 140 caractères s'y écrit sur une vingtaine de lignes. C'était déjà vrai avant le
  14/11. Des comptes de cette taille sont la borne du contrat (2⁶³ − 1), pas une valeur observée.
- **Le lecteur d'écran réel** (VoiceOver, NVDA) n'a pas été essayé : l'annonce du `th scope="row"` et de la région
  est attendue d'après RGAA et WCAG, pas entendue.
- **Les mesures ont été faites en iframes** : Chrome sans interface a une largeur minimale de fenêtre, et une
  capture directe à 390 px montre une page plus large que l'écran. La capture dans un iframe de 390 px est
  conforme à la mesure.

## Ce qui reste

- #617 : les messages de date du fil et des tendances disent `AAAA-MM-JJ`, alors que le champ montre `JJ/MM/AAAA`
  dans un Chrome en français (Opquast 80).
- #614 : les milliers groupés sur tout le site, pas seulement dans les tendances.
- #615 : la règle du nom de dépôt (`is_repository_name`) à l'import des tendances, pour qu'un `owner/..` n'entre
  pas en base.
- #597 : réserver à la clé `WEB` les sortes que le site montre (côté API de données).
- L'étape 2 de la mission (comptes rendus, top 10, rapport de tendances) attend le message de time-knight.
