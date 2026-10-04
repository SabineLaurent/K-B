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
HTML **brutes**, au format d'URL éprouvé dans brief09, une fois par jour, lancée à la main. On est
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
`src/k_b/tldr_source.py:44`

L'URL est celle de brief09, `https://tldr.tech/<édition>/<AAAA-MM-JJ>`. La page est gardée
octet pour octet, sans analyse.

### Un jour sans édition se reconnaît à sa redirection

tldr.tech ne répond pas 404 pour un jour sans édition. Il redirige vers la page d'accueil de
l'édition. En donnant l'URL de la page elle-même comme préfixe de confiance, toute redirection
devient visible : `download` lève `RedirectedOutsideError`, qui porte l'adresse d'arrivée.

```python
except RedirectedOutsideError as refusal:
    if refusal.redirect_url.rstrip("/") != f"{SITE_URL}{self.edition}":
        raise
    logger.info("%s %s: no edition page, redirected to %s", ...)
```
`src/k_b/tldr_source.py:48`

Seule la redirection vers `https://tldr.tech/<édition>` vaut « pas d'édition ». Le jour est
journalisé avec ce qui a été observé, puis sauté. Une redirection ailleurs (page de connexion,
anti-bot) remonte et fait échouer la source. Cette règle couvre les week-ends, les jours fériés
et l'édition pas encore parue, **sans calendrier**.

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
`src/k_b/tldr_source.py:70`

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
  ouvrés et fériés : une seule règle, observée sur le site, qui couvre tous les cas. Écarté :
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

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_page_of_a_day_is_asked_at_its_brief09_url` | l'URL est `https://tldr.tech/ai/2026-10-04` |
| `test_every_day_from_the_last_collection_day_to_today_is_asked` | le dernier jour est relu, samedi et dimanche sont demandés |
| `test_a_first_collection_asks_the_seven_days_before_today_and_today` | première collecte : 8 jours |
| `test_an_edition_page_is_returned_unchanged_under_its_day` | la page est rendue octet pour octet |
| `test_a_day_redirected_to_the_edition_landing_page_is_logged_and_skipped` | jour sans édition sauté, journal avec l'URL d'arrivée, avec ou sans `/` final |
| `test_a_redirection_elsewhere_than_the_edition_landing_page_is_raised` | une autre redirection fait échouer la source |
| `test_an_http_error_is_raised` | un HTTP 500 remonte |
| `test_a_page_name_that_is_not_a_safe_path_segment_is_refused_before_any_write` | `../escape` refusé, rien d'écrit |
| `test_a_refused_redirection_tells_where_it_led` | l'erreur porte `redirect_url` et reste un `ValueError` |
| Collecte réelle de `tldr_ai` du 02 au 04/10 | 02/10 : page de 81 913 octets ; 03/10 et 04/10 : `redirected to https://tldr.tech/ai` |
| `uv run pytest` | 169 tests passent |

## Ce que tu dois pouvoir défendre

1. **Pourquoi pas de calendrier des jours ouvrés ?** Le site dit lui-même qu'il n'y a pas
   d'édition en redirigeant vers sa page d'accueil. Un calendrier serait une seconde source de
   vérité, à tenir à jour (fériés américains), qui pourrait contredire le site
   (`tldr_source.py:48`).
2. **Que se passe-t-il si tldr.tech redirige vers une page de connexion ?** La source échoue,
   l'erreur donne l'URL d'arrivée. Les autres sources continuent, et la date de dernière
   collecte de `tldr_ai` n'avance pas : tout sera redemandé la fois suivante (`tldr_source.py:49`,
   `collect.py`).
3. **Si je collecte à 7 h et que l'édition du jour sort à 14 h ?** Le jour est journalisé comme
   sans édition. Le lendemain, la collecte repart de ce jour-là et le récupère
   (`tldr_source.py:73`).
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
