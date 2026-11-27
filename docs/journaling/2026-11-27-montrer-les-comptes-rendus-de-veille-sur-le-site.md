# Montrer les comptes rendus de veille sur le site

- **Date** : 2026-11-27
- **Branche** : `feat/digest-pages`, sur `4d593c83` : `ab6a3979` (les pages et leurs tests), `47d2858f` (les
  constats de la première revue), `9c46c498` (le fort zoom), `d0e652ae` (les constats de la deuxième revue), puis
  cette note
- **Issue** : #724
- **Fichiers principaux** : `src/k_b/web/digests.py`, `src/k_b/web/pages.py`, `src/k_b/web/data_api_client.py`,
  `src/k_b/web/templates/digest.html`, `digest_source.html`, `digests.html`, `digest_absent.html`,
  `src/k_b/web/static/site.css`, `src/k_b/items.py`, `tests/web/test_digest_pages.py`,
  `tests/web/test_digest_client.py`, `docs/site-web.md` (section « Comptes rendus »)
- **Série** : suite de [Servir les comptes rendus au site depuis leur jumeau](2026-11-14-servir-les-comptes-rendus-au-site-depuis-leur-jumeau.md)
  (#560) et d'[Afficher le détail d'un item](2026-11-12-afficher-le-detail-d-un-item.md)
- **Périmètre** : les quatre commits de code de la branche, d'`ab6a3979` à `d0e652ae` ; la fusion d'`origin/main` et
  les commits de doc qui suivent n'y entrent pas. Les autres fichiers de la liste de départ viennent de `main`,
  fusionnés par d'autres PR, chacune avec sa note.

## Le pourquoi

`kb digest` écrit un compte rendu par sujet de veille le lundi et le jeudi, en ligne par le job
`caj-kb-digest-watch` (#423). Depuis #560, l'API de données les sert au client `WEB` (`GET /digests/{subject}` et
`GET /digests/{subject}/days`), mais aucune page du site ne les lisait. La veille doit être consultable en ligne,
comptes rendus compris. Cette PR ajoute au site l'index des neuf sujets, le compte rendu d'un sujet (le plus récent,
ou celui d'un jour) et la page de chaque source.

Un compte rendu est un texte écrit par un LLM. La page doit donc montrer ce qui appuie chaque affirmation (OWASP
LLM07, *Misinformation*), dire quand la lecture des items a été coupée, pour qu'un compte rendu partiel ne passe pas
pour entier, et afficher le texte du modèle et les titres des sources comme du texte, jamais comme du HTML (LLM10,
*Improper Output Handling*). Elle doit aussi tenir les règles du site : RGAA 4.1.2, sans JavaScript, et le budget
RGESN d'un écran.

## Le comment

### 1. Des pages bâties sans entrée ni sortie, des appels dans `pages.py`

Les chemins sont des constantes de `web/digests.py` (`src/k_b/web/digests.py:25-28`) :

```python
DIGESTS_PATH = "/comptes-rendus"
SUBJECT_PATH = "/comptes-rendus/{subject}"
DAY_PATH = "/comptes-rendus/{subject}/{day}"
SOURCE_PATH = "/comptes-rendus/{subject}/{day}/sources/{item_id}"
```

`web/digests.py` ne fait aucun appel : il reçoit des réponses déjà validées et rend des *dataclasses* figées
(`DigestPage`, `CapNotice`, `MissingSourcePage`) que les gabarits affichent. Les appels à l'API et le choix de la page
sont dans `pages.py`, comme pour le fil et les tendances (`code.md`, « Séparation des responsabilités »). L'adresse est
lue en chaînes, jamais typée par FastAPI (`src/k_b/web/pages.py:189-192`) :

```python
    read_day = read_written_day(day)
    if subject not in SUBJECTS or read_day is None:
        return render_error_page(request, 404)
    return show_digest(request, subject, read_day)
```

Un paramètre typé par FastAPI répondrait 422 en JSON, et non la page 404 du site. Un sujet hors de `SUBJECTS` ou un
jour qui n'existe pas (`2026-02-30`) donne la page 404 avant tout appel à l'API.

### 2. La réponse de l'API, validée à la frontière

`WatchDigest` (`src/k_b/web/data_api_client.py`) reprend les bornes que `kb` écrit : 12 affirmations au plus, de 1 à 5
sources chacune, 60 sources au plus, un titre de 1 024 caractères au plus, un modèle de la forme `MODEL_NAME`. Quatre validateurs
ajoutent ce qu'un type seul ne dit pas, dont celui-ci (`src/k_b/web/data_api_client.py:295-300`) :

```python
    @model_validator(mode="after")
    def check_each_claim_cites_a_source_listed(self) -> Self:
        """Each claim leads to its sources (OWASP LLM07)."""
        listed = {source.item_id for source in self.sources}
        if any(not listed.issuperset(claim.item_ids) for claim in self.claims):
```

Les trois autres refusent une lecture coupée qui ne nomme pas sa sorte ou sa date, un `outcome` qui contredit les
affirmations et une source listée deux fois. `read_digest` refuse enfin un compte rendu d'un autre sujet ou d'un autre
jour que celui demandé (`src/k_b/web/data_api_client.py:458`). Toute réponse refusée devient
`DataApiError("data_api_invalid_response")`, puis la page 500, journalisée sans le sujet ni le jour : le site ne montre
jamais un compte rendu qu'il n'a pas pu vérifier.

Les trois lectures d'un 404 nommé (`item_not_found`, `trend_window_not_found`, `digest_not_found`) passent par une
seule fonction, `is_error_named` (`src/k_b/web/data_api_client.py:481-486`), au lieu d'un modèle Pydantic par erreur.

### 3. Le lien d'une source : relire le compte rendu, puis comparer

`item_id` est une clé de substitution : une base refaite renumérote ses items (`docs/specs-api.md`,
`GET /digests/{subject}`, limite (d)). Un lien direct vers `/items/<id>` pourrait donc mener sans erreur à un autre
item. Le lien d'une source vise `SOURCE_PATH`. Au clic, le site relit le compte rendu, y trouve la source, lit l'item,
puis compare (`src/k_b/web/digests.py:329-336`) :

```python
def is_item_of_source(detail: ItemDetail, source: DigestSource) -> bool:
    ...
    if source.url is not None:
        return source.url == detail.url
    return make_visible(detail.title) == source.title
```

L'URL d'abord, parce que deux cas trompent le titre. Les failles du catalogue KEV de la CISA peuvent partager leur
titre (`vulnerabilityName`, sans contrainte d'unicité dans le schéma), jamais leur URL (NVD et le n° CVE). L'import
met à jour sur place le titre d'un papier qu'arXiv retitre (`UPSERT_PUBLICATION`, `src/k_b/database/writers/paper_writer.py:13-24`), jamais son URL. Sans URL, le
titre de l'item est mis sur une ligne par `make_visible`, comme le jumeau l'écrit, puis comparé à celui de la source.

Si l'item n'a pas l'URL de la source (ou son titre, si la source n'a pas d'URL), si l'API répond `item_not_found`, ou
si le numéro mène à une entrée Zotero ou à un clip, la page « Source introuvable » répond en 200 : « Le n° … de la base
de K-B ne mène pas à cette source. », puis le titre de la source et son lien d'origine s'il est en `https`. Le 200,
et non le 404 : la source existe dans le compte rendu relu, seul l'item manque. Une source absente du compte rendu
donne la page 404, sans lecture d'item (`src/k_b/web/pages.py:224-226`). Le titre de l'adresse n'est jamais lu.

### 4. Le bandeau « Compte rendu partiel »

L'API IA lit les sortes dans l'ordre de `WATCH_KINDS` (failles, alertes, papiers, *releases*, articles de
newsletters) et s'arrête à la coupe. `covered_after` est la date du premier item laissé de côté, bornes exclues, et
vaut pour la lecture de tous les sujets ; `since` est la fenêtre propre au sujet (`src/k_b/web/digests.py:252-255`) :

```python
    is_cut_in_window = digest.covered_after >= digest.since
    whole = WATCH_KINDS[: position if is_cut_in_window else position + 1]
    unread = WATCH_KINDS[position + 1 :]
    if not is_cut_in_window and not unread:
```

Si la coupe tombe dans la fenêtre du sujet, la sorte coupée n'est lue qu'après `covered_after` ; sinon, elle est lue
en entier pour ce sujet. Les sortes qui la suivent ne sont pas lues. S'il ne manque rien au sujet (coupe hors de sa
fenêtre, sur la dernière sorte), le bandeau n'apparaît pas. Le gabarit écrit une phrase par cas, chacune seulement si
elle nomme une sorte : la sorte coupée et le moment, à la seconde, dans un `<time>` ; « … n'ont pas été lus » ; « … ont
été lus en entier », au féminin si toutes ces sortes le sont (`FEMININE_KINDS`). La première version ne nommait que la
sorte coupée et disait les autres lues en entier : la première revue a relevé que les sortes après la coupe ne sont
pas lues du tout (`47d2858f`).

### 5. Les textes reçus et la page au clavier et au lecteur d'écran

Une affirmation et un titre passent par `clean_received_value`, puis par l'échappement automatique de Jinja2 : une
balise ou une adresse dans un texte reste du texte, jamais un lien. Un texte que le nettoyage laisse vide devient
« Sans texte. » ou « Sans titre ». Chaque affirmation est suivie de la liste de ses sources
(`src/k_b/web/templates/digest.html:47-49`) :

```html
<p class="claim-sources-label" id="sources-{{ loop.index }}">{{ "Source" if claim.sources|length == 1 else "Sources" }}:</p>
<ul class="claim-sources" role="list" aria-labelledby="sources-{{ loop.index }}">
```

Les affirmations forment une liste numérotée (`<ol>`) sous le `h2` « Affirmations ». Chaque liste de sources est
nommée par son libellé (`aria-labelledby`, WCAG 1.3.1), et `role="list"` est posé parce que Safari retire la
sémantique d'une liste sans puces. Le lien d'une source porte `lang="en"` quand elle a un titre, par hypothèse, comme les titres du fil.
Chaque lien de source ou de jour est une cible d'au moins 44 px de haut par son `padding` (Opquast 186) et prend l'ardoise de
la charte une fois visité (Opquast 141). À 200 % de texte dès 320 px, le cadre des textes et la marge des numéros
laissaient moins de dix lettres par ligne : la règle du fort zoom les réduit (`9c46c498`,
`src/k_b/web/static/site.css`).

### 6. Ce que le site partage avec `kb` : `items.py`

Le paquet `web` n'importe que `web`, `core` et `items` (`WEB_ALLOWED_MODULES`,
`tests/architecture/test_layers.py:471`). Le site avait besoin de deux choses écrites ailleurs : l'ordre des sortes de
la veille, pour dire ce qu'une coupe a laissé, et la mise sur une ligne d'un titre, pour retrouver la source.
`WatchKind` et `WATCH_KINDS` passent donc d'`ai_api/watch_items.py` à `items.py` (`src/k_b/items.py:49-55`), et
`make_visible` de `post/vault_files.py` à `items.py` (`src/k_b/items.py:200-208`). L'écrivain du jumeau et le site
appliquent ainsi une seule règle, au lieu de deux copies qui pourraient diverger. Les deux phrases d'un compte rendu sans
affirmation (« Aucune affirmation retenue. », « Aucun item classé dans ce sujet. ») sont recopiées dans le site, qui
n'importe pas `post`. Un test les tient égales à celles de la fiche.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Le lien d'une source vise `/comptes-rendus/…/sources/<id>`, contrôlé au clic | une base refaite renumérote ses items | un lien direct vers `/items/<id>` : il mènerait sans erreur à un autre item ; contrôler chaque source à l'affichage : jusqu'à 60 `GET /items/{id}` par page (RGESN) |
| La comparaison par l'URL quand la source en a une, sinon par le titre (`d0e652ae`) | des failles KEV peuvent partager leur titre ; un papier retitré garde son URL | le titre seul (première version) : une autre faille du même titre passait ; le titre et l'URL (deuxième version) : un papier retitré devenait « Source introuvable » |
| « Source introuvable » en 200 | la source existe dans le compte rendu relu, seul l'item manque | 404 : il dirait la page inexistante |
| Les sources sous leur affirmation | on lit l'affirmation et ce qui l'appuie au même endroit, au clavier et au lecteur d'écran | les renvois numérotés de la fiche vers une liste en bas : un aller-retour par affirmation |
| Un seul lien par source, vers son item | le lien d'origine reste sur la page de l'item | deux liens par source : jusqu'à 120 arrêts de Tab |
| Le code d'API du sujet dans l'adresse, son libellé dans `SUBJECTS`, tenu égal à `DIGEST_SUBJECTS` par un test | une seule liste de codes | un code français par sujet : une seconde table à tenir |
| L'index sans appel à l'API | 0 requête à l'API pour la page d'entrée des comptes rendus | le dernier jour de chaque sujet : 9 appels par affichage (RGESN) |
| Les jours du sujet en liste de liens, 30 au plus, les plus récents d'abord, le total dit au-delà | le site ne sait pas quels jours existent ; à deux comptes rendus par semaine, 30 jours en couvrent quinze | un formulaire de date, comme les tendances : on y taperait des jours sans compte rendu ; une pagination : une page de plus pour un besoin non observé |
| Le texte du modèle affiché tel quel, espace avant « : » comprise | décision de Sabine : « garder la fiche telle quelle » ; la règle des espaces vaut pour le texte écrit par le site | réécrire le texte du modèle : le site ne montrerait plus ce que le modèle a écrit |
| Le lien d'origine d'une source introuvable sans `hreflang` | le site ne connaît ni la sorte de la source ni la langue de sa page, comme pour l'article d'une newsletter | `hreflang="en"` et la note « en anglais » (essayés, `47d2858f`) : une affirmation sans preuve |
| `WatchKind`, `WATCH_KINDS` et `make_visible` dans `items.py` | le site n'importe que `core` et `items` (`test_layers.py`) | une copie dans `web` : deux listes à tenir égales |

Imposés par une consigne du dépôt : le site sans JavaScript et ses gabarits sans `|safe` (`MEMORY.md`, « Interface ») ;
aucune espace avant « : » dans le texte du site (`tests/web/test_accessibility.py`) ; le budget de 3 requêtes et
30 Ko par écran (D4 de #564).

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_source_whose_item_has_its_title_leads_to_the_page_of_the_item` (`tests/web/test_digest_pages.py`) | une source retrouvée mène à la page de l'item, « Retour au compte rendu » |
| `test_a_source_whose_paper_was_retitled_leads_to_the_page_of_its_item` | une source qui a une URL se contrôle par l'URL seule |
| `test_a_source_whose_item_has_its_title_under_another_url_is_not_found` | une autre faille du même titre, sous une autre URL, n'est pas montrée comme la source |
| `test_a_source_absent_from_the_digest_is_the_page_not_found_without_reading_an_item` | une source inventée dans l'adresse ne fait lire aucun item |
| `test_a_digest_cut_says_in_words_what_was_read_and_what_was_not` (paramétré) et `test_a_cut_that_leaves_nothing_out_of_the_subject_has_no_banner` | le bandeau nomme la sorte coupée, les sortes non lues et les sortes lues en entier, et n'apparaît pas quand rien ne manque |
| `test_an_answer_out_of_the_contract_is_refused` (`tests/web/test_digest_client.py`, paramétré) et `test_a_digest_of_another_subject_gives_the_page_500` | une réponse hors contrat n'est jamais affichée |
| `test_a_text_of_the_model_or_of_a_source_is_shown_as_text_never_as_a_link` | une balise dans un texte reçu reste du texte (LLM10) |
| `test_an_address_out_of_its_form_is_the_page_not_found_without_asking_the_data_api` | une adresse mal formée ne coûte aucun appel |
| `test_the_subjects_are_those_of_the_digests_in_their_order` | un sujet ajouté à `DIGEST_SUBJECTS` fait échouer le site tant qu'il ne le nomme pas |
| `test_the_words_of_a_digest_without_claim_are_those_of_its_sheet` | les mots d'un compte rendu vide restent ceux de la fiche |
| `test_the_screen_of_a_digest_holds_three_requests_and_30_kb_at_most` | un compte rendu à ses bornes (12 affirmations, 60 sources, 30 jours) tient le budget RGESN |
| `test_the_claims_are_an_ordered_list_under_their_heading_each_source_a_list`, `test_each_list_of_sources_is_named_by_the_label_above_it` (`tests/web/test_accessibility.py`) | la structure lue par un lecteur d'écran |
| `test_a_digest_of_watch_shows_its_claims_then_a_source_leads_to_the_item_of_its_url` (`tests/web/test_site_on_the_data_api.py`) | de bout en bout, sur la vraie API de données : un jumeau écrit comme `kb digest` l'écrit, puis le lien d'une source retrouve son item par son URL, en quatre appels |
| `uv run pytest` sur `d0e652ae` : 6 061 tests verts ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` verts | les contrôles du dépôt |
| captures à 320 px et 200 % de texte, mot par mot, sur les neuf pages, sur `d0e652ae` | aucune affirmation ne déborde au fort zoom |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas lier directement à `/items/<id>` ?** Une base refaite renumérote ses items : le lien mènerait
   sans erreur à un autre item, et la page dirait faux en silence. Le site relit donc le compte rendu et compare
   l'item à la source avant de le montrer (`is_item_of_source`, `src/k_b/web/digests.py:329`).
2. **Pourquoi l'URL et pas le titre ?** Le titre trompe dans deux cas relevés dans le code : des failles KEV qui
   peuvent partager leur titre, et un papier qu'arXiv retitre sur place (`paper_writer.py:13-24`). L'URL d'un item de la
   veille ne change pas à l'import. Le titre ne sert qu'aux sources sans URL.
3. **Que se passe-t-il si l'API renvoie un compte rendu dont une affirmation cite une source absente ?** Le
   validateur `check_each_claim_cites_a_source_listed` le refuse, et le site rend la page 500, sans rien afficher
   (`src/k_b/web/data_api_client.py:295`). Une affirmation sans sa source n'est jamais montrée (LLM07).
4. **Où est la sécurité face à un texte piégé du modèle ou d'une source ?** Le texte est nettoyé
   (`clean_received_value`), puis échappé par Jinja2 ; aucun gabarit n'écrit `|safe`. Le seul lien vers l'extérieur
   que ces pages ajoutent est celui d'une source introuvable, gardé s'il est en `https` (`keep_https_link`) et ouvert par `external_link`, qui
   annonce le nouvel onglet.
5. **Comment le lecteur sait-il qu'un compte rendu est partiel ?** Par le bandeau, en mots : la couleur ne fait que
   suivre (RGAA 3.1). Quand la coupe tombe dans la fenêtre du sujet, son moment est donné à la seconde, en UTC, dans un `<time>`.

## Zones non vérifiées

- **La langue des titres des sources** : `lang="en"` est une hypothèse, la même qu'au fil. Un titre en français
  serait annoncé en anglais par un lecteur d'écran.
- **Les lecteurs d'écran** : la structure est prouvée par les tests et lue par un relecteur accessibilité ; aucun
  lecteur d'écran (VoiceOver, NVDA) n'a été lancé sur ces pages. Le `role="list"` posé pour Safari suit le
  comportement connu de WebKit, non rejoué ici.
- **WAVE** n'a pas encore été passé sur l'aperçu : Sabine le passe avant la fusion.
- **En ligne** : aucun tag n'est posé. Les pages n'ont lu que le conteneur `watch` simulé des tests et l'aperçu
  local, pas les jumeaux de production.
- **Un article TLDR repris par deux éditions** est deux items de la même URL : sa source mène à l'un ou à l'autre,
  le même article. Aucun test ne le rejoue.

## Ce qui reste

- Les deux pertes que le jumeau ne porte pas encore (les items laissés de côté avant l'écriture, ceux restés sans
  réponse à la classification) : #727, au Backlog.
- La mise en ligne, au prochain tag.
- Un sujet retiré de `DIGEST_SUBJECTS` rend ses anciens comptes rendus inaccessibles (limite (e) de
  `GET /digests/{subject}`, `docs/specs-api.md`), non planifié.
