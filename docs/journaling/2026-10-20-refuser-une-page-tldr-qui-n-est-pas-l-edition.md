# Refuser à la collecte une page TLDR qui n'est pas l'édition du jour

- **Date** : 2026-10-20
- **Branche** : `fix/tldr-read-page-at-collection`
- **Issue** : #274
- **Fichiers principaux** : `src/k_b/etl/sources/tldr.py`, `tests/etl/sources/test_tldr.py`,
  `tests/etl/test_extract.py`, `tests/fixtures/tldr_ai_landing_extract.html`,
  `docs/specs-collecte.md`, `MEMORY.md`
- **Série** : suite de [la collecte des pages brutes](2026-10-04-collecte-tldr-pages-brutes.md)
  et de [la lecture des articles](2026-10-12-lecture-articles-tldr.md).

Les commits couverts sont les quatre de la branche (`02a31be` → `df256c1`). Les autres commits de
la liste injectée viennent de `main`, déjà fusionnés par d'autres PR : cette note ne les couvre pas.

## Le pourquoi

La collecte TLDR téléchargeait une page par jour et la gardait telle quelle, sans la lire. Si
tldr.tech servait, à l'adresse d'un jour, une page qui n'est pas une édition (page d'erreur en 200,
page d'accueil, édition d'un autre jour), K-B l'écrivait au brut, la date de dernière collecte
avançait, et l'import refusait la page à chaque passage. L'édition de ce jour était perdue, et
rien ne le disait à la collecte. C'était un écart à la règle 1 de `.claude/rules/conventions.md` :
« à la collecte, une source n'échoue que si sa page est illisible […] ; sa date de dernière collecte
reste alors inchangée ». La spec et `MEMORY.md` le portaient comme non tranché.

Désormais, la collecte lit chaque page avant de la garder. Une page refusée n'est jamais écrite.
Selon son jour, la source échoue (le jour sera redemandé), abandonne le jour (avec un
avertissement), ou saute aujourd'hui (il sera relu).

## Le comment

### 1. Lire la page comme à l'import

`src/k_b/etl/sources/tldr.py:161-174`, `find_refusal` :

```python
    try:
        reading = read_articles(page)
    except ValueError as error:
        return str(error)
    # read_articles raises for a page without any article: the first one is there.
    edition_date = reading.entries[0].edition_date
    if edition_date != day:
        return f"edition of {edition_date.isoformat()}"
    return None
```

La collecte appelle `read_articles`, le **même lecteur** que l'import. Une page que l'import
refuserait (pas UTF-8, pas de `h1`, `h1` sans « TLDR … AAAA-MM-JJ », article imbriqué, aucun
article complet) est donc refusée dès la collecte. La fonction ne lève pas : elle rend **ce qui a
été observé** (le message du lecteur, où le `h1` est déjà cité par `quote_value`, ou la date
trouvée), ou `None` pour l'édition du jour. `entries[0]` est sûr : `read_articles` lève quand la
page n'a aucun article complet. On n'attrape que `ValueError` (`UnicodeDecodeError` en est une
sous-classe) : une autre exception est inattendue et doit faire échouer la source (point 4).

### 2. Lire sans décider : `read_pages`

`src/k_b/etl/sources/tldr.py:115-148`. Pour chaque jour, `read_pages` télécharge la page, la lit
par `find_refusal` et range le résultat : la page (`bytes`) ou son refus (`PageRefusal`, l. 43-46 :
l'URL demandée et l'observé). Un jour redirigé vers la page d'accueil de l'édition est sauté,
comme avant. La fonction ne choisit rien : toute la politique est dans `fetch`. C'est une
correction de la revue de code (constat 6, `code.md` : « une fonction fait une chose »). Dans une
première version, la règle d'aujourd'hui vivait ici et celle des jours passés dans `fetch`.

### 3. La politique, dans `fetch`

`src/k_b/etl/sources/tldr.py:86-98` :

```python
        today_refusal = refusals.pop(today, None)
        if today_refusal is not None:
            logger.info(
                "%s %s: %s, read again at the next collection; %s, from %s",
        ...
        last_edition_day = max(pages, default=None)
        if any(last_edition_day is None or day > last_edition_day for day in refusals):
            raise self.refuse(refusals)
```

Trois cas, dans cet ordre :
- **aujourd'hui (UTC) refusé** : il est retiré des refus, journalisé en `INFO` et sauté. Rien
  n'est perdu, car `list_days_to_collect` (l. 181) part du jour de la dernière collecte et le
  relira (décision de Sabine du 2026-10-20) ;
- **un jour passé refusé après la dernière édition lue, ou sans aucune édition lue** : la source
  échoue. `extract.py` n'écrit rien et ne change pas la date de dernière collecte : c'est la
  règle 1, sans toucher à `extract.py` ;
- sinon, chaque jour refusé **précède** une édition lue : il est abandonné, avec une ligne
  `WARNING` (l. 99-108). Puis `fetch` rend les pages, avec des clés en texte ISO
  (`2026-10-05`), le format qu'attend `extract.py`.

Le cœur du raisonnement : une édition lue **après** le jour refusé prouve deux choses. Le site
sert des éditions, ce n'est donc pas une panne générale. Et ce jour est passé, son édition ne
paraîtra plus. On peut alors cesser de le redemander sans bloquer la source.

### 4. Une erreur qui dit chaque jour

`src/k_b/etl/sources/tldr.py:150-158`, `refuse` : une `ValueError` au message court,
`not_the_edition_of_the_day` (l'état nommé, l. 35), et deux **notes** par jour refusé de la
fenêtre, dans l'ordre : `"<source> <jour>, from <URL>"`, puis l'observé. `extract.py:48-50` cite
chaque note à part, par `quote_value`, sur la ligne datée du journal. Le message reste court pour
que la coupe à 100 caractères de `quote_value` ne mange pas l'observé (constat 6 de la relecture
du plan). Depuis la revue de code (constat 4), les jours qui précèdent une édition lue sont notés
aussi : le journal dit tout ce que la collecte a vu.

Une exception inattendue du lecteur passe par le même `except` que le téléchargement
(`tldr.py:141`) : elle reçoit la note jour + URL et elle est levée. C'est échouer fermé.

### 5. Les tests et leur fixture

`tests/fixtures/tldr_ai_landing_extract.html` est la page d'accueil réelle de l'édition
(`https://tldr.tech/ai`), reçue le 2026-10-20 par un seul `curl`, avec le `User-Agent` de K-B (choix
de Sabine). Elle est réduite à sa structure et à son `h1`, « Keep up with AI in 5 minutes », sans
article ni autre texte de tiers. Les anciens tests utilisaient un `EDITION_PAGE` réduit à un `h1`,
que la lecture refuse désormais. Il est maintenant dérivé de `tldr_ai_extract.html` par
`replace` du titre (`test_tldr.py`, en tête), sans modifier ce fichier.

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Quand cesser de redemander un jour passé refusé | Quand une édition d'un jour postérieur a été lue dans la même collecte : c'est un fait observé, et le blocage dure au plus jusqu'à la prochaine édition publiée | Une borne de N jours : la constante est arbitraire, et la source reste en échec N jours, éditions suivantes comprises. Un compte d'essais dans `collection_state.json` : il change le format de l'état, touche `raw_store.py` et `extract.py` (hors périmètre), et rejoint le problème connu des collectes concurrentes |
| Comment lire la page | `read_articles`, le lecteur de l'import : la collecte refuse ce que l'import refuserait | Le `h1` seul : une page sans article complet serait encore écrite, puis refusée à chaque import |
| Aujourd'hui refusé | Sauté, ligne `INFO`, la source réussit ; le jour est relu (décision de Sabine du 2026-10-20) | Faire échouer la source, comme le dit la lettre du critère : si tldr.tech sert avant la parution une page en 200 (non observé), chaque collecte du matin échouerait, et la fenêtre grandirait sans fin, comme arXiv (#71) |
| Niveau du journal d'un jour abandonné | `WARNING` : une édition peut être perdue, la ligne doit se distinguer d'un jour sans édition. Précédents : `github_releases.py:86`, `github_advisories.py:90` | `INFO` : elle se confondrait avec les jours redirigés |
| Forme de l'erreur | Message court + notes par jour, citées à part par `extract.py` | Tout dans le message : coupé à 100 caractères sur la ligne datée |
| Fixture | Un `curl` de la page d'accueil, réduite (choix de Sabine) | Une page fournie par Sabine : possible, mais pas nécessaire |

Choix imposés par les consignes du dépôt : la règle 1 de `conventions.md` (date inchangée sur un
échec), la règle 3 et la règle 5 de `poc.md` (observé cité par `quote_value`, aucun texte d'article
au journal), la consigne des fixtures du 2026-10-10.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_page_that_is_not_an_edition_fails_the_source_with_its_day_and_url` | La page d'accueil servie à l'URL d'un jour passé fait échouer la source, avec l'état, le jour, l'URL et le `h1` observé |
| `test_the_edition_of_another_day_fails_the_source_with_its_date` | L'édition du 02 servie à l'URL du 03 est refusée : `edition of 2026-10-02` |
| `test_a_tldr_page_that_is_not_an_edition_writes_nothing_and_keeps_the_date` (`test_extract.py:300`) | Rien n'est écrit sous `raw/`, pas même l'édition lue avant, et la date de dernière collecte reste ; la ligne datée exacte |
| `test_a_past_tldr_day_never_an_edition_stops_failing_once_a_later_edition_is_read` (`test_extract.py:337`) | Sur trois collectes : échec samedi ; lundi, l'édition est lue, le jour est abandonné en `WARNING` et la date avance ; mardi, le jour n'est plus demandé |
| `test_a_past_day_refused_before_an_edition_read_is_given_up_and_logged` | Le texte exact de la ligne `WARNING` |
| `test_a_page_of_today_that_is_not_an_edition_is_skipped_and_logged` | Aujourd'hui refusé : ligne `INFO`, aucune ligne `WARNING` ni d'erreur, et les autres pages sont rendues |
| `test_each_day_refused_after_the_last_edition_read_is_noted`, `test_a_day_refused_before_an_edition_read_is_noted_too_when_the_source_fails` | Une paire de notes par jour refusé de la fenêtre, dans l'ordre |
| `test_an_http_error_after_a_page_refused_is_raised`, `test_an_unexpected_error_of_the_reader_is_raised_with_its_day_and_url` | Une erreur HTTP ou une exception inattendue du lecteur est levée telle quelle, avec la note jour + URL |
| `test_a_day_redirected_to_the_edition_landing_page_is_logged_and_skipped` (inchangé) | La redirection vers la page d'accueil reste sautée |
| `uv run pytest` : 1956 passed ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` verts | Les contrôles du dépôt |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas écrire les éditions lues quand un autre jour est refusé ?** Le contrat de
   collecte est « une source en échec n'écrit rien » (`extract.py`, règle 1). Les éditions seront
   relues à la collecte suivante, car la date n'a pas avancé. Écrire une partie demanderait de
   changer `extract.py` et la sémantique de la date de dernière collecte.
2. **Un jour abandonné, n'est-ce pas une perte ?** Oui, si sa vraie édition revient plus tard
   (page passagère). C'est une limite acceptée par Sabine, et tracée par une ligne `WARNING` avec
   le jour, l'URL et l'observé. Avant ce correctif, la même perte arrivait sans état nommé
   (`tldr.py:99-108` ; spec, « Limites »).
3. **La source peut-elle rester bloquée comme arXiv ?** Pas pour un jour passé : dès qu'une
   édition postérieure est lue, il est abandonné. Pas pour aujourd'hui : il est sauté. Elle échoue
   à chaque collecte seulement quand **aucune** édition n'est lue (site cassé, sélecteurs changés).
   C'est voulu, et rien n'est perdu tant que tldr.tech garde ses anciennes pages (spec, « En cas
   de panne »).
4. **Où est la sécurité ?** La page est une entrée non fiable. Elle est lue par `html.parser`, qui
   n'exécute rien, et plafonnée à 1 Mio. Elle n'est jamais un chemin (les noms de fichier viennent
   des dates calculées par K-B). Le journal ne cite que le `h1`, échappé et coupé par
   `quote_value`, jamais un article. `/security-review` n'a rien trouvé.
5. **Pourquoi `WARNING` alors que la règle 1 dit qu'aucun `logger.warning` d'une source n'est un
   rejet d'entrée ?** Ce n'est pas une entrée rejetée à l'import, c'est un jour abandonné à la
   collecte, comme les pages non lues de `github_releases.py:86`.

## Zones non vérifiées

- **Ce que sert tldr.tech avant la parution du jour, en semaine** : seules des redirections de
  week-end ont été observées (03 et 04/10). Le cas « page 200 qui n'est pas une édition à
  l'adresse d'un jour » n'est pas observé : la fixture est la page d'accueil, reçue à sa propre
  adresse.
- **Que BeautifulSoup ne lève que `ValueError` ou `ParserRejectedMarkup`** : non vérifié. Toute
  autre exception fait échouer la source (échouer fermé). Sur un jour passé, elle la ferait échouer
  à chaque collecte (aucune observée).
- La lecture d'un HTML très imbriqué peut être lente : hors champ de la revue de sécurité
  (ressources), la page est plafonnée à 1 Mio.

## Ce qui reste

- Comparer le nom d'édition du `h1` au dossier (`tldr_ai`) : limite déjà écrite dans la spec, non
  demandée par #274.
- Un premier jour de fenêtre, relu et déjà gardé, qui serait refusé cette fois fait échouer la
  source jusqu'à la prochaine édition. Le distinguer d'un jour encore à collecter demanderait de
  lire le brut (spec, « Limites »).
- La collecte réelle de toutes les sources : #25.
