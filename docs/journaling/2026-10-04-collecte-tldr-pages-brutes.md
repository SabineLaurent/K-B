# Collecte des pages brutes TLDR

- **Date** : 2026-10-04
- **Branche** : `feat/tldr-raw-pages`
- **Issue** : #13
- **Fichiers principaux** : `src/k_b/tldr_source.py`, `src/k_b/collect.py`, `src/k_b/http_download.py`
- **Série** : suit [le téléchargement commun](2026-10-04-telechargement-commun.md), dont cette PR
  étend l'erreur de redirection.

## Le pourquoi

K-B doit collecter les newsletters tldr.tech (éditions ai, infosec, dev). tldr.tech n'a pas
d'API : on lit ses pages web, une par édition et par jour. Une première branche (`feat/tldr`)
avait accumulé des règles (titre vérifié, « aujourd'hui » à part, 404/410 conditionnels, jours
ouvrés, lecture des articles dès la collecte). Sabine a recadré : la collecte récupère les pages
HTML **brutes**, une fois par jour, lancée à la main. On est
reparti de `main` avec seulement ce qu'il faut. La lecture des articles viendra à l'étape de
transformation, sur ce brut gardé intact.

## Le comment

### Une source par édition, une page par jour

`TldrSource("ai")` est une source comme les autres : un `name` (`tldr_ai`), une `extension`
(`html`) et une méthode `fetch`. La seule différence : elle renvoie **plusieurs** pages, une par
jour, dans un dictionnaire `{"2026-10-02": b"<html>…"}`.

```python
page_url = f"{SITE_URL}{self.edition}/{day.isoformat()}"
try:
    # The page url itself is the trusted prefix: any redirection is noticed.
    pages[day.isoformat()] = download(page_url, page_url, MAX_PAGE_BYTES)
```
`src/k_b/tldr_source.py:45`

L'URL est `https://tldr.tech/<édition>/<AAAA-MM-JJ>`. La page est gardée
octet pour octet, sans analyse.

### Un jour sans édition se reconnaît à sa redirection

Le 03 et le 04/10 (un week-end), tldr.tech n'a pas répondu 404 : il a redirigé vers la page
d'accueil de l'édition. En donnant l'URL de la page elle-même comme préfixe de confiance, toute
redirection devient visible : `download` lève `RedirectedOutsideError`, qui porte l'adresse
d'arrivée.

```python
except Exception as error:
    if (
        isinstance(error, RedirectedOutsideError)
        and error.redirect_url.rstrip("/") == f"{SITE_URL}{self.edition}"
    ):
```
`src/k_b/tldr_source.py:49`

Seule la redirection vers `https://tldr.tech/<édition>` vaut « pas d'édition » : le jour est
journalisé avec l'adresse d'arrivée, puis sauté (`continue`). Une redirection ailleurs (page de
connexion, anti-bot) remonte et fait échouer la source.

### Une ligne de journal par jour, affichée par `kb collect`

```python
logger.error("%s %s: %s, from %s", self.name, day, error, page_url)
raise
```
`src/k_b/tldr_source.py:62`

Chaque jour produit une ligne qui dit ce qui a été observé : `edition page, 75510 bytes`,
`no edition page, redirected to https://tldr.tech/infosec`, ou l'erreur reçue suivie de l'URL
demandée. Ce dernier cas compte : le message d'un `HTTPError` (`HTTP Error 500: Internal Server
Error`) ou d'un délai dépassé (`<urlopen error timed out>`) ne dit ni le jour ni l'URL. Une
collecte sans aucune page le dit aussi (`tldr_source.py:66`).

Ces lignes sont de niveau INFO. Sans configuration, Python n'affiche que WARNING et au-dessus :
`kb collect` appelle donc `configure_logging()` (`src/k_b/cli.py:18`), qui affiche INFO et
au-dessus, avec le niveau et le module.

### L'erreur qui dit où la redirection a mené

```python
if not response.url.startswith(trusted_url_prefix):
    raise RedirectedOutsideError(trusted_url_prefix, response.url)
```
`src/k_b/http_download.py:44`

Avant cette PR, `download` levait un `ValueError` sans l'adresse d'arrivée. La nouvelle classe
hérite de `ValueError`, ce qui ne change rien pour les autres sources, et ajoute `redirect_url`
pour la source qui en a besoin.

### Les jours à collecter : rattrapage depuis la dernière collecte

```python
if last_collected_at is None:
    first_day = today - timedelta(days=FIRST_COLLECTION_DAYS)
else:
    first_day = last_collected_at.astimezone(UTC).date()
```
`src/k_b/tldr_source.py:81`

Chaque collecte lit tous les jours, du jour de la dernière collecte (inclus) jusqu'à aujourd'hui
en UTC. Le dernier jour est relu parce que son édition a pu paraître après la collecte. Un jour
oublié n'est pas perdu : la collecte suivante le rattrape.

### Plusieurs pages par collecte, chacune écrite telle quelle

```python
for page_name in raw_content:
    if not SAFE_PAGE_NAME.fullmatch(page_name):
        raise ValueError(f"not a safe page name: {page_name!r}")
for page_name, page in raw_content.items():
    write_new_raw_file(source_dir / collection_name / f"{page_name}.{source.extension}", page)
```
`src/k_b/collect.py:88`

Le contrat commun `Source` accepte désormais `bytes` ou `dict[str, bytes]`. Les pages vont dans
`raw/automation/tldr_ai/<horodatage>/<jour>.html`. Chaque nom de page est vérifié
(`[a-z0-9_-]+`, ni point ni barre oblique) **avant** la première écriture : un nom refusé ne
laisse aucune collecte partielle.

## Choix faits et options écartées

- **Repartir de `main`** plutôt que simplifier `feat/tldr` : la PR passe d'environ 870 lignes à
  moins de 300, lisible d'un trait. `feat/tldr` est gardée : son analyseur servira à la
  transformation.
- **Redirection vers la page d'accueil = pas d'édition**, plutôt qu'un calendrier des jours
  ouvrés et fériés : une seule règle, observée sur le site le 03 et le 04/10. Écarté :
  « toute redirection = pas d'édition », plus simple mais qui confondrait une page anti-bot avec
  un week-end, sans erreur (constat de la relecture indépendante du plan).
- **Comparaison exacte de l'URL d'arrivée** (`/` final toléré) plutôt qu'une analyse par
  `urlsplit` : si tldr.tech change sa redirection, la source échoue et le journal montre l'URL
  reçue (échouer fermé, `.claude/rules/code.md`). Point soulevé par la revue de code, gardé.
- **Relire le jour de la dernière collecte** plutôt que partir du lendemain : on ne perd pas une
  édition parue après la collecte. Le prix : la page est en double dans deux collectes, retirée à
  la transformation.
- **Pas d'analyse HTML à la collecte** : le brut reste intact (règle commune de collecte), et
  aucune dépendance n'est ajoutée (pas de BeautifulSoup dans cette PR).
- **Tous les jours sont demandés, week-end compris** : à 2 s de pause entre deux pages, un
  week-end coûte deux requêtes par édition, négligeable.
- Pause de 2 s, une page à la fois : décidé dans #6, tldr.tech ne publie pas de limite.
- **Journaliser l'erreur avec le jour et l'URL, puis relancer l'erreur d'origine**, plutôt que
  l'envelopper dans un `ValueError` : `kb collect` affiche toujours le vrai type
  (`failed (HTTPError)`). Consigne « K-B est déterministe » : chaque ligne dit ce qui a été
  observé.
- **`logging.basicConfig` dans `cli.py`**, plutôt qu'un gestionnaire propre au paquet `k_b` :
  une ligne, la pratique de la bibliothèque standard pour un point d'entrée en ligne de
  commande. Le changement vaut pour toutes les sources, pas seulement TLDR.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_page_of_a_day_is_asked_at_its_edition_and_date_url` | l'URL est `https://tldr.tech/ai/2026-10-04` |
| `test_every_day_from_the_last_collection_day_to_today_is_asked` | le dernier jour est relu, samedi et dimanche sont demandés |
| `test_a_first_collection_asks_the_seven_days_before_today_and_today` | première collecte : 8 jours |
| `test_an_edition_page_is_returned_unchanged_under_its_day_and_logged` | la page est rendue octet pour octet, une ligne donne sa taille |
| `test_a_day_redirected_to_the_edition_landing_page_is_logged_and_skipped` | jour sans édition sauté, journal avec l'URL d'arrivée, avec ou sans `/` final |
| `test_a_redirection_elsewhere_than_the_edition_landing_page_is_logged_and_raised` | une autre redirection est journalisée et fait échouer la source |
| `test_an_error_is_logged_with_its_day_and_url_then_raised` | HTTP 500, délai dépassé, page trop grosse : une ligne avec le jour, le message reçu et l'URL, puis l'erreur remonte |
| `test_no_edition_page_in_the_window_returns_none_and_is_logged` | une collecte sans page le dit, avec la fenêtre de jours |
| `test_an_info_line_of_k_b_is_shown_once_logging_is_configured` | `configure_logging()` affiche une ligne INFO, dans un interpréteur neuf |
| `test_a_page_name_that_is_not_a_safe_path_segment_is_refused_before_any_write` | `../escape` refusé, rien d'écrit |
| `test_a_refused_redirection_tells_where_it_led` | l'erreur porte `redirect_url` et reste un `ValueError` |
| Collecte réelle de `tldr_ai` du 02 au 04/10 | 02/10 : page de 81 913 octets ; 03/10 et 04/10 : `redirected to https://tldr.tech/ai` |
| Collecte réelle de `tldr_infosec` du 02 au 04/10, avec `configure_logging()` | trois lignes INFO affichées : `edition page, 75510 bytes`, puis deux `redirected to https://tldr.tech/infosec` |
| `uv run pytest` | 172 tests passent |

## Ce que tu dois pouvoir défendre

1. **Pourquoi pas de calendrier des jours ouvrés ?** Le site dit lui-même qu'il n'y a pas
   d'édition en redirigeant vers sa page d'accueil. Un calendrier serait une seconde source de
   vérité, à tenir à jour (fériés américains), qui pourrait contredire le site
   (`tldr_source.py:49`). Limite : seul un week-end a été observé (voir Zones non vérifiées).
2. **Que se passe-t-il si tldr.tech redirige vers une page de connexion ?** La source échoue,
   le journal donne le jour, l'URL demandée et l'URL d'arrivée. Les autres sources continuent, et
   la date de dernière collecte de `tldr_ai` n'avance pas : tout sera redemandé la fois suivante
   (`tldr_source.py:62`,
   `collect.py`).
3. **Si je collecte à 7 h et que l'édition du jour sort à 14 h ?** Le jour est journalisé comme
   sans édition. Le lendemain, la collecte repart de ce jour-là et le récupère
   (`tldr_source.py:84`).
4. **Où est la sécurité ?** Aucune redirection n'est suivie sans être vue (préfixe = URL de la
   page). Taille limitée à 1 Mo. Le slug d'édition et chaque nom de page sont validés par une
   expression fermée avant de construire un chemin de fichier. Rien n'est analysé ni exécuté à
   la collecte.
5. **Pourquoi garder la page brute plutôt que les articles ?** Si l'analyse casse ou évolue, on
   relit le brut sans retélécharger. C'est la règle « brut intact » de `docs/specs-collecte.md`.

## Zones non vérifiées

- **Jours fériés** : seule la redirection d'un week-end a été observée (03 et 04/10). Qu'un jour
  férié ou une édition pas encore parue redirige de la même façon est supposé, pas observé.
- **Heure de parution** des éditions : inconnue. Le rattrapage d'un jour suffit si l'édition
  paraît le jour même en UTC, ce qui n'a pas été mesuré.
- **`urlopen` suit la redirection avant le contrôle du préfixe** : la requête atteint la cible
  avant le refus. Le corps n'est ni lu ni stocké. C'est préexistant et suivi dans #54.
- **Écriture interrompue** (disque plein) : les pages déjà écrites restent. C'est documenté dans
  `collect.py:87`, pas traité.
- **Registre des traitements** : la ligne « aucune donnée personnelle » vient de la lecture des
  pages faite sur `feat/tldr`. Elle n'a pas été refaite dans cette session.

## Ce qui reste

- **Lecture des articles** (titre, lien, résumé, sponsors écartés, `utm_*` retirés) : étape de
  transformation, en reprenant l'analyseur `tldr_editions.py` de `feat/tldr`.
- **Retrait du doublon** du jour relu : à la fusion des items.
- **Automatisation** de la collecte quotidienne : après, hors #13.
- **Élargir la première collecte** au-delà de 7 jours à la mise en service.
