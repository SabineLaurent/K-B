# Afficher le détail d'un item sur le site

- **Date** : 2026-11-12
- **Branche** : `feat/web-item-detail`, commits `e5ce50b` à `7aa9524`, partie d'`origin/main` à `1b6e0b8`
- **Issue** : #564 (PR 1 du découpage de #564 ; les tendances sont devenues #596)
- **Série** : suite de [Servir le fil de veille](2026-11-11-servir-le-fil-de-veille.md) (#563) et
  d'[Aligner le fil sur ses maquettes](2026-11-11-aligner-le-fil-sur-ses-maquettes.md) (#587)
- **Fichiers principaux** :
  - `src/k_b/web/item_detail.py` (nouveau) ;
  - `src/k_b/web/received_text.py` (nouveau) ;
  - `src/k_b/web/templates/item.html` (nouveau) ;
  - `src/k_b/web/data_api_client.py`, `src/k_b/web/pages.py`, `src/k_b/web/feed.py`, `src/k_b/web/static/site.css` ;
  - les tests : `tests/web/test_item_detail.py`, `tests/web/test_item_page.py`, `tests/web/test_site_on_the_data_api.py`.

La liste des fichiers et des commits donnée à la note compare la branche au `main` local, en retard. Les commits
jusqu'à `1b6e0b8` et les fichiers `infra/`, `observability/`, `tests/data_api/`, `tests/database/` et les notes du
11/11 viennent des PR déjà fusionnées (#571, #581, #587, #592, #594) : ils ne sont pas de cette branche et cette
note ne les couvre pas.

## Le pourquoi

Le fil de veille montre des cartes : la sorte, la date, les identifiants, le titre et un lien vers la source.
Mais il ne montre pas ce que K-B a gardé de chaque item : le résumé d'un papier et ses auteurs, la description
d'une faille, les notes d'une *release*, les paquets d'une alerte. Les maquettes du 09/11 prévoient une page
par item, atteinte par le titre de sa carte.

Cette PR ajoute cette page, `/items/<id>`. Elle la sert pour les cinq sortes du fil, et jamais pour une entrée
Zotero ni un clip, que le site ne montre pas. La page lit l'API de données par la clé du client `WEB`, comme le
fil : le site n'ouvre jamais la base.

Elle apporte aussi la preuve qu'attend le critère C17.3 de la certification : une saisie validée, puis un second
écran, prouvés par un test de bout en bout. Le test sert le site sur la vraie API de données de la base de
test, refuse une date du formulaire du fil, accepte un filtre, puis suit le titre d'une carte jusqu'au détail.

## Le comment

### 1. L'adresse : un identifiant lu à la main, une seule fonction

FastAPI sait typer un paramètre de chemin (`item_id: int`). Mais un `abc` y rendrait un 422 en JSON qui cite la
valeur reçue, alors que le site doit répondre par sa page 404. La route le lit donc comme une chaîne, et une
seule fonction en décide :

```python
def read_item_id(text: str) -> int | None:
    if not ITEM_ID.fullmatch(text):
        return None
    item_id = int(text)
    return item_id if item_id <= MAX_INT64 else None
```
(`src/k_b/web/item_detail.py:127-132`)

- **`ITEM_ID`, `[1-9][0-9]{0,18}`** (`item_detail.py:34`) : des chiffres ASCII, sans zéro en tête. Ce n'est pas
  `\d` : `\d` accepte aussi un chiffre arabe ou pleine chasse, que `int()` saurait lire. Une seule adresse par
  item (Opquast 169) : `01` et `+1` sont refusés.
- **`fullmatch`, et non `match` avec `$`** : `$` accepte un retour à la ligne final, si bien que `"1\n"`
  passerait.
- **La borne 2⁶³ − 1** : 19 chiffres peuvent dépasser un entier de 64 bits, que la base ne tient pas.
- **#403** remplacera un jour l'identifiant par un UUID : elle ne changera que cette fonction.

### 2. Le client : un état par route, et la sorte d'un item exclu sans son texte

```python
status, body = send(http_client, f"{ITEMS_PATH}/{item_id}", {}, clock)
if status == httpx2.codes.NOT_FOUND and is_item_not_found(body):
    raise DataApiError("data_api_item_not_found", status)
if status != httpx2.codes.OK:
    raise name_failure(status, body)
```
(`src/k_b/web/data_api_client.py:254-258`)

- **Le chemin est bâti d'un entier**, jamais de la chaîne reçue : aucun `../` ne peut atteindre une autre route
  de l'API.
- **Seul un 404 dont le corps dit `item_not_found`** veut dire « item absent ». Un 404 `route_not_found`, ou un
  404 sans JSON venu de l'entrée d'Azure, est une réponse hors contrat : la page 500.
- **La réponse est validée par une union discriminée sur `kind`** (`DETAIL`, `data_api_client.py:195-197`).
  Elle compte un modèle par sorte du fil, plus `ExcludedItem` (`:167`), qui ne lit que `kind` pour une entrée
  Zotero ou un clip. `extra="ignore"` laisse le reste du corps hors du modèle : le texte d'un clip n'est jamais
  modélisé, montré ni journalisé.
- **Sous `strict=True`, une date n'est acceptée que dans du JSON** : c'est pourquoi les tests construisent le
  détail par `validate_json`, comme le client.
- **`ItemDetail` est un alias simple** (`:175`), pas une instruction `type`. Avec `type`, pydantic voyait une
  seule branche de l'union, mal discriminée.

### 3. La route : trois 404, une 500

```python
read_id = read_item_id(item_id)
if read_id is None:
    return render_error_page(request, 404)
try:
    detail = read_item(request.app.state.data_api_client, read_id)
except DataApiError as error:
    if error.state == "data_api_item_not_found":
        return render_error_page(request, 404)
```
(`src/k_b/web/pages.py:113-120`)

La route rend la page 404 dans trois cas, et la page 500 sinon :
- un identifiant hors de sa forme : aucun appel à l'API n'est fait ;
- un item absent ;
- une entrée Zotero ou un clip (`pages.py:123`).

Tout autre échec rend la page 500. Il est journalisé par la même ligne que le fil, sans l'identifiant de
l'item. Le journal des requêtes écrit le gabarit `/items/{item_id}` (`find_route_template`), jamais l'adresse
reçue.

### 4. Les textes reçus : nettoyés une fois, et jamais du HTML

Tout texte venu de l'API est une donnée non fiable. Jinja2 l'échappe (`autoescape=True`, `rendering.py`), et
aucun gabarit n'écrit `|safe` (test de `tests/web/test_templates.py`). Mais l'échappement ne retire pas les
caractères que le HTML refuse. Une seule fonction les retire :

```python
def is_kept(character: str) -> bool:
    if character in KEPT_CONTROLS:
        return True
    if character in BIDI_CONTROLS:
        return False
    if unicodedata.category(character) in DROPPED_CATEGORIES:
        return False
    return not is_noncharacter(character)
```
(`src/k_b/web/received_text.py:40-47`)

- **Ce qui est retiré** :
  - les contrôles (`Cc`), sauf la tabulation et le retour à la ligne ;
  - les demi-paires isolées (`Cs`), que l'UTF-8 ne sait pas encoder ;
  - les non-caractères ;
  - les douze contrôles bidirectionnels (`BIDI_CONTROLS`, `core/config.py:487`). Jamais fermé, un U+202E
    renverserait l'affichage de la date qui suit dans la même ligne. La même liste sert déjà le coffre
    (`post/vault_files.py`).
- **Ce qui est gardé** : les autres `Cf`. U+200D, par exemple, lie les emojis composés.
- **`clean_received_value`** (`received_text.py:26`) rend `None` quand il ne reste rien de dessiné : que des blancs
  et des caractères de format (`Cf`, comme U+200B ou U+FEFF), par `is_blank` (`:32`), la seule définition du vide. L'appelant
  dit alors « Sans titre », « sans nom » ou « Non renseigné » (fil et détail), plutôt qu'un lien sans nom.
- **Les notes d'une *release*** restent du texte brut (D3) : jamais de Markdown rendu, jamais de lien.
  `split_paragraphs` (`item_detail.py:318-324`) coupe aux lignes vides. Une ligne d'espaces Unicode, insécables
  comprises, compte comme vide (`BLANK_LINES`, `:33`). Les lignes vides aux bouts d'un paragraphe sont retirées,
  mais le retrait d'une ligne écrite est gardé, sous `white-space: pre-wrap`.

### 5. Le bandeau : l'état en mots, lu sans rien supposer

```python
if isinstance(detail, AdvisoryDetail):
    if detail.exploited is None:
        return "advisory_without_cve"
    if detail.exploited:
        return "advisory_in_catalog"
    return "advisory_absent_from_catalog"
```
(`src/k_b/web/item_detail.py:246-251`)

Le code ne rend qu'un nom d'état. Le gabarit écrit le texte de chaque état, avec le sens de CVE, KEV et CISA à
leur première occurrence (`item.html`).
- **Faux veut dire « absente du catalogue KEV »**, pas « non exploitée » : le catalogue ne liste que des failles
  dont l'exploitation est connue.
- **Seul un item au catalogue prend le style d'alerte.** Le mot porte l'état, la couleur ne fait que suivre
  (RGAA 3.1).
- **Une faille retirée a le bandeau de son retrait**, jamais un « Exploitée » (décision de Sabine sur la carte,
  étendue au détail).

### 6. La mise en page : une colonne qui ne déborde pas

La page suit les maquettes : 760 px de large avec ses marges, le titre en `h1`, les faits en `<dl>`, les textes
sous des `h2`, et le lien vers la source en bouton. Trois règles viennent de la mesure :
- **La colonne** : `.item` et `.item-facts` ont `grid-template-columns: minmax(0, 1fr)` (`site.css:709`,
  `:786`). Sans cette règle, une colonne de grille prend la largeur de son mot le plus long. À texte 200 % sur
  320 px, la page défilait alors en largeur.
- **Le bouton** : `.button` passe à la ligne (`flex-wrap: wrap`), pour que son libellé et son annonce
  « (site externe, nouvel onglet) » tiennent sur un téléphone.
- **Le titre d'une carte** : il a `margin-block: 0.75rem` (`site.css:650`), pour que la marge intérieure de son
  lien (une cible de 44 px) et son anneau de focus ne mordent ni sur la ligne du dessus ni sur le lien du
  dessous.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Deux PR pour #564 : le détail, puis les tendances (#596) | décision de Sabine (D1, 11/11) : le détail part plus tôt, chaque revue est plus courte | une PR L : un seul tour de revues, rien avant la fin |
| Les notes en texte brut (D3) | décision de Sabine ; la mission n'accorde que `jinja2` | rendre le Markdown : une dépendance, dont le réglage par défaut laissait passer le HTML brut (`code.md`) |
| Le même budget, 3 requêtes et 30 Ko par écran (D4) | décision de Sabine ; mesuré texte à sa borne | aucun budget : RGESN 6.1 non tenu |
| L'identifiant en chaîne, validé par une fonction | un 422 JSON de FastAPI citerait la valeur ; #403 ne change qu'elle | `item_id: int` : le 422 en JSON |
| Le texte du bandeau dans le gabarit, son état en Python | un développement de sigle est du HTML (`<i lang="en">`), et le filtre `safe` est interdit | des chaînes avec balises : il faudrait `Markup` |
| Les champs longs du détail en `str`, pas `NonEmptyText` | la base ne borne que la longueur (`schema.sql`) : un résumé vide doit donner « Aucun résumé. », pas une 500 (revue de code, tranché par time-knight) | `NonEmptyText` : une 500 pour une valeur que la base tient |
| `ghsa_id` typé `GhsaId`, ajouté à `items.py` à côté de `CveId` | la base tient `GHSA_ID` par sa GLOB ; la règle 4 de `conventions.md` nomme déjà `GhsaId` ; un identifiant hors forme n'est pas une réponse de l'API (la 500), plutôt qu'un repli pour un cas que la base interdit (tranché par time-knight, écart mineur au plan qui laissait `items.py` intact) | un repli « sans identifiant » ; un type écrit dans le site, hors d'`items.py` |
| `id` du fil à `ge=1` | le fil ne bâtit jamais un lien que la route refuse ; les identifiants partent de 1 (tranché par time-knight) | accepter 0 : un lien vers une 404 |
| La couleur des liens visités sur le titre de carte seul | Opquast 141 vise les liens dans un texte ; un bouton plein perdrait son contraste en ardoise ; « Retour au fil » mène à `/`, toujours visité (tranché par time-knight) | sur chaque lien du détail |
| Garder `drop_control_characters` du fil à côté de `clean_received_text` | deux règles pour deux raisons : un contrôle refusé dans une saisie, un texte reçu nettoyé (`code.md`) | les fusionner : deux raisons de changer liées |
| Le titre d'une *release* sans `lang="en"` | comme au fil : un nom de dépôt et un nom de version | le marquer : faux pour `owner/repo` |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_detail_of_each_kind_is_read_on_the_real_data_api_as_the_fixture_holds_it` | la fixture `web_item_details.json` est la réponse de la vraie API sur la base de test : un champ renommé échoue ici |
| `test_a_zotero_entry_or_a_clip_is_read_by_its_kind_alone`, `test_a_zotero_entry_or_a_clip_is_the_page_not_found_its_text_never_shown` | une entrée Zotero ou un clip : sa sorte seule, la 404, son texte ni dans la page ni au journal |
| `test_an_id_in_its_form_is_read`, `test_an_id_out_of_its_form_is_refused` (13 formes) | la forme de l'adresse, chiffre arabe et pleine chasse compris |
| `test_a_404_other_than_item_not_found_is_an_answer_out_of_schema` | un état par route : un autre 404 n'est pas un item absent |
| `test_every_value_received_is_escaped_never_a_tag` | un repère `<b>` dans chaque champ rendu sort échappé |
| `test_a_text_received_loses_its_bidirectional_controls` (12 cas), `test_a_bidirectional_override_received_never_reaches_the_page` | les contrôles bidirectionnels n'atteignent pas la page |
| `test_the_log_of_a_request_names_the_route_never_the_id` | le journal écrit `route=/items/{item_id}`, jamais `424242` |
| `test_site_on_the_data_api.py` (2 tests) | C17.3 : la date `2026-02-30` refusée sous son champ (422, `aria-invalid`, aucun appel), puis un filtre gardé, puis le titre d'une carte jusqu'à son détail (200, son `h1`) |
| mutation sur une copie : lien du titre retiré | ce test échoue : `IndexError: list index out of range` |
| mutation sur une copie : route cassée | ce test échoue : `assert 404 == 200` |
| `test_the_screen_of_a_detail_holds_three_requests_and_30_kb_at_most` (5 sortes) ; mutation : 40 000 caractères dans `item.html` | D4 tenu ; mutation : `assert 33445 <= 30000` |
| `test_accessibility.py` : 10 états du détail dans `PAGES` | langue, titre propre à chaque item, un `h1`, landmarks, liens nommés et externes annoncés, sens de CVE, KEV et CISA à leur première occurrence, `<dl>`, `<time>` |
| Chrome sans interface, 11 pages × 5 largeurs (320 à 1280) | 0 débordement ; titre de carte cliquable sur 44 px (`elementFromPoint`), anneau à 2 px et 3 px de ses voisins |
| texte 200 % à 320, 360 et 390 px | 0 débordement sur les détails ; la 404, la 500 et le formulaire du fil débordent comme sur `origin/main` (#599) |
| `uv run pytest` | 5105 tests passés |

## Ce que tu dois pouvoir défendre

1. **« Pourquoi ne pas typer `item_id` en `int` ? »** FastAPI rendrait un 422 en JSON qui cite la valeur reçue,
   sur un site qui ne répond qu'en pages HTML. `read_item_id` décide seule, et un identifiant hors de sa forme
   rend la 404 sans appeler l'API (`item_detail.py:127`, `pages.py:113`).
2. **« Le titre d'un item vient de GitHub : un `<script>` dedans ? »** Jinja2 échappe toute valeur
   (`autoescape=True`), aucun gabarit n'écrit `|safe`, et un test le vérifie champ par champ
   (`test_every_value_received_is_escaped_never_a_tag`). Les notes ne deviennent jamais du HTML (D3), et une URL
   hors `https` ne devient jamais un lien (`keep_https_link`).
3. **« Un clip est privé : le site peut-il l'afficher ? »** Non. Le client n'en lit que la sorte (`ExcludedItem`),
   et la route rend la 404. Mais la clé `WEB` peut lire tous les items : le texte arrive donc au conteneur du site
   avant d'être jeté. C'est une limite écrite au registre, que #597 corrigera côté API de données.
4. **« Que dit le bandeau d'une alerte dont la CVE a quitté le catalogue ? »** « Entrée au catalogue KEV », avec
   sa limite : « Un retrait du catalogue depuis ne se voit pas sur cette page ». L'API ne relie pas encore une
   alerte à sa faille (`specs-api.md`).
5. **« Comment savez-vous que le test de bout en bout prouve quelque chose ? »** Il a été montré rouge par deux
   mutations sur une copie : le lien du titre retiré, puis la route cassée. Il sert le site sur la vraie API de
   la base de test, en mémoire, et tourne en CI.

## Zones non vérifiées

- **Lecteur d'écran** (VoiceOver, NVDA), **clavier réel**, **couleurs forcées** : le relecteur n'a envoyé que des
  tabulations par CDP, et Chrome sans interface n'a pas repeint la page en couleurs forcées. **Validateur HTML** :
  aucun n'est installé ; le code a été relu à la main. **`role="list"` sous Safari** : supposé, comme au fil.
  Parade : Sabine les essaie en ligne au tag qui suivra l'oral.
- **`lang="en"` sur les textes des sources** : une hypothèse ; une note écrite en français sera mal marquée. La
  déclaration d'accessibilité le dit.
- **Starlette route sur le chemin décodé** (spécification ASGI, `path`) : `/items/%39` sert l'item 9. Lu dans la
  spécification, non testé.
- **Le test de bout en bout et le budget** ont été écrits après la route, donc jamais rouges avant le code : leur
  rouge a été montré par mutation, sur une copie.
- **Un détail de plus d'1 Mo** rend la page 500 : seuls 1 000 auteurs de 200 caractères échappés y arrivent, au
  pire théorique. C'est un risque accepté au plan, non mesuré sur une base réelle.

## Ce qui reste

- **Les tendances**, leur lien dans la navigation, et le `start=2026-02-30` réaffiché par le fil : #596 (PR 2).
- **Réserver au client `WEB` les sortes que le site montre** : #597 (API de données).
- **La 404, la 500 et le formulaire du fil à texte 200 % sur 320 px** : #599.
- **Une alerte reliée à sa faille**, pour voir le retrait de sa CVE : hors de la version de l'API
  (`specs-api.md`, « Hors de cette version »).
- **Les comptes rendus, le top 10 et le back office** : étapes 2 et 3 de la mission, sur message de time-knight.
