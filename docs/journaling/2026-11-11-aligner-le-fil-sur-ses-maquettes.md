# Aligner le fil sur ses maquettes, et ouvrir les liens externes dans un nouvel onglet

- **Date** : 2026-11-11
- **Branche** : `fix/web-external-links`
- **Issue** : #587 (S, `interface`)
- **Commits de la branche** : `1871794` (le changement), `fbe710d` (le tri des revues). La liste injectée par le
  skill cite aussi `6f7ca4e` à `f43677d` : ce sont les commits de #571, fusionnés dans `main` par #578 avant cette
  branche (infra, registre, `MEMORY.md`, note de la mise en ligne). Ils ne font pas partie de cette PR, et cette
  note ne les couvre pas.
- **Fichiers principaux** : `src/k_b/web/templates/feed.html`, `base.html`, `403.html`, `sources.html`,
  `src/k_b/web/static/site.css`, `src/k_b/web/feed.py`, `tests/web/test_accessibility.py`, `test_stylesheet.py`,
  `test_feed_page.py`, `test_operator_check.py`, `docs/site-web.md`.
- **Note précédente de la série** : [Servir le fil de veille](2026-11-11-servir-le-fil-de-veille.md) (#563).

## Le pourquoi

Le fil de veille est l'écran de la démonstration de l'oral blanc du 13/11. En le comparant aux maquettes du 09/11,
Sabine a relevé des écarts, aux trois largeurs. Ses remarques ont été transmises par time-knight :

- la sorte d'un item n'était pas encadrée ;
- à 1280 px, le formulaire faisait 585 px de haut, contre 334 sur la maquette ;
- les cartes et la pagination n'avaient pas la forme dessinée ;
- un lien vers la source ouvrait l'article à la place de K-B, alors qu'elle veut « rester dans K-B » ;
- un changement de page remontait tout en haut de l'écran ;
- « Se déconnecter » n'était pas là où elle le cherchait, dans l'en-tête.

Cette PR corrige ces écarts sans changer ce que le fil montre : mêmes items, mêmes filtres, même API. Elle touche
la présentation (gabarits, feuille de style) et deux constantes de `feed.py`.

## Le comment

### 1. Un lien vers un autre site s'ouvre dans un nouvel onglet, et le dit

`src/k_b/web/templates/feed.html:82` :

```html
<a class="card-link" href="{{ card.link }}"{% if card.link_lang %} hreflang="{{ card.link_lang }}"{% endif %} target="_blank" rel="noopener noreferrer">{{ card.link_label }}<span aria-hidden="true">&nbsp;↗</span> <span class="link-note">({{ card.link_note }})</span></a>
```

- **`target="_blank"`** ouvre la page dans un nouvel onglet.
- **`rel="noopener"`** empêche la page ouverte d'agir sur l'onglet de K-B par `window.opener`.
- **`rel="noreferrer"`** n'envoie pas l'adresse de la page de K-B. Le site le fait déjà partout par
  `Referrer-Policy: no-referrer` : c'est une seconde barrière.
- **Le texte du lien** dit l'onglet : `link_note` vaut « site externe, nouvel onglet », ou « en anglais, site
  externe, nouvel onglet » (`src/k_b/web/feed.py:405-407`). Le nom que lit un lecteur d'écran est donc « Lire sur
  arxiv.org (en anglais, site externe, nouvel onglet) ».
- **La flèche** `↗` est décorative (`aria-hidden`). `&nbsp;` est une espace insécable : la flèche ne commence
  jamais seule une ligne, sur un écran de 320 px.
- **La note** est en plus petit (`.link-note`, 0,75rem, `site.css:660`). Le lien garde ainsi la longueur de la
  maquette (« Lire sur arxiv.org ↗ »).

Les deux liens de `/sources` prennent exactement la même forme. Un lien du site, lui, n'a jamais de `target`.

### 2. Le formulaire suit la maquette à chaque largeur, par la seule CSS

Le site n'a pas de JavaScript : c'est la feuille de style qui lit la largeur de l'écran, par des *media queries*
aux deux seuils déjà en place, `48rem` (768 px par défaut) et `64rem` (1024 px). `src/k_b/web/static/site.css:490-513` :

```css
.choices {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 1rem;
}

.kind-choices {
  @media (width >= 48rem) {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  @media (width >= 64rem) {
    display: flex;
```

Le gabarit ne fait que nommer les groupes (`kind-choices`, `period-choices`, `period-group`, `period-field`,
`feed.html:37`, `:47`, `:58`). La feuille de style décide de la mise en page :

| Largeur | Sortes | Boutons radio | Date de début |
|---|---|---|---|
| téléphone (moins de 48rem) | deux colonnes | deux colonnes | sous les boutons radio |
| tablette (48 à 64rem) | trois colonnes | une ligne | à droite des boutons radio : libellé et aide au-dessus du champ |
| ordinateur (64rem et plus) | une ligne | une ligne | après les boutons radio : libellé et aide à gauche du champ |

`minmax(0, 1fr)` laisse une colonne rétrécir sous la largeur de son contenu : « Articles de newsletters » passe
alors à la ligne au lieu d'élargir la page. La case cochée garde sa taille par `flex: none`.

Sur ordinateur, le champ de date est placé dans une grille de deux colonnes. `src/k_b/web/static/site.css:461-470` :

```css
@media (width >= 64rem) {
  flex: 0 1 auto;
  grid-template-columns: auto minmax(10rem, 14rem);
  align-items: center;
  column-gap: 0.75rem;

  & > input {
    grid-column: 2;
    grid-row: 1 / span 2;
```

- **À gauche**, le libellé et son aide occupent les deux lignes ; **à droite**, le champ s'étend sur ces deux
  lignes (`span 2`).
- **Un message d'erreur** vient sur une troisième ligne, sous l'aide.
- **`flex: 0 1 auto`** empêche le champ de grandir jusqu'au bord du formulaire : sans lui, le champ partait tout à
  droite, loin de son libellé, ce que la première capture a montré.

Les espacements viennent de la maquette : 16 px entre les groupes, 20 px de marge intérieure. Les aides sont
collées à leur libellé : elles perdent la marge de 1rem que leur donnait la règle générale des paragraphes
(`.field-help { margin: 0; }`). C'est le plus gros gain en hauteur.

### 3. La carte : une ligne pour la sorte, la date, les identifiants et la pastille

`feed.html:79` réunit dans un seul `<p class="card-meta">`, dans l'ordre de la maquette :
1. la sorte, encadrée (`.card-kind` : bordure de 1 px à l'encre, coins de 4 px, `site.css:610`) ;
2. la date en `<time>` ;
3. les identifiants, en chasse fixe ;
4. la pastille « Exploitée (KEV) ».

La ligne est en `flex-wrap` : sur un téléphone, les identifiants passent à la ligne d'eux-mêmes. Les identifiants
prennent la couleur et la taille de leur ligne, sans les redéclarer.

### 4. La pagination : des boutons qui mènent aux résultats

`src/k_b/web/feed.py:363` :

```python
previous_link=f"{build_page_link(form, page - 1)}#{RESULTS_ID}"
```

- **L'ancre** : `RESULTS_ID = "resultats"` (`feed.py:44`) est aussi l'`id` de la ligne des résultats
  (`feed.html:70`), reçu du contexte. Une seule constante tient les deux bouts.
- **Ce que voit Sabine** : sur la page 2, le navigateur fait défiler la page jusqu'à cette ligne (« 45 items
  depuis… Page 2 sur 3 »). `scroll-margin-block-start: 1rem` (`site.css:575`) la décolle du bord.
- **Les liens sans ancre** : « Élargir à 7 jours » et le formulaire envoyé (« Filtrer ») sont une nouvelle
  recherche. Ils partent de `build_page_link` sans ancre, et s'ouvrent en haut de la page.
- **Les boutons** : les deux liens prennent la classe `button-secondary`, le bouton encadré de la maquette, de
  44 px de haut au moins.

### 5. « Se déconnecter » dans l'en-tête, une fois par page

`src/k_b/web/templates/base.html:21` :

```html
{% block header_sign_out %}{% if is_operator_checked %}<a class="site-logout" href="/.auth/logout">Se déconnecter</a>{% endif %}{% endblock %}
```

- **Où** : le lien passe du pied de page à la fin de la barre de l'en-tête (`margin-inline-start: auto`,
  `site.css:172`).
- **Quand** : il n'apparaît qu'avec le contrôle de l'opératrice (`is_operator_checked`), soit en ligne et pas sur
  le Mac en `KB_WEB_AUTH=off`.
- **Le bloc Jinja** `header_sign_out` sert la page 403, qui le vide (`403.html:3`) : son bouton « Se déconnecter »
  est déjà l'action de la page, et l'en-tête ne la répète pas.

Enfin, `docs/site-web.md` dit maintenant ce que la plateforme répond sans session : un 302 vers la connexion de
Microsoft Entra pour un navigateur, un 401 `WWW-Authenticate: Bearer` pour un autre client. C'est le constat en
ligne de time-knight ; la doc parlait encore de `/.auth/login/aad`.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Nouvel onglet pour chaque lien externe, annoncé dans le texte | La demande de Sabine ; Opquast 146 ; la technique WCAG G201 (conseillée) | Le même onglet, défaut du web, que G200 conseille hors besoin : le besoin existe. L'annonce cachée derrière la seule flèche : une personne voyante ne la lit pas. |
| L'annonce en 0,75rem, dans le lien | Garder la longueur visible de la maquette ; contraste de 7,4:1 | L'annonce à la taille du lien : trop longue. Gardée par time-knight (relecture d'accessibilité, constat 4). |
| La même forme sur `/sources` et sur le fil | Opquast 138 : même nature, même forme | Une forme par page (relecture d'accessibilité, constat 1, corrigé) |
| La mise en page par CSS, aux seuils existants | Le site n'a pas de JavaScript, et les deux seuils lisent déjà les trois largeurs | Un nouveau seuil : aucun besoin mesuré |
| Les trois aides gardées, collées à leur libellé | Elles disent la règle d'un champ avant l'envoi (WCAG 3.3.2, ADR de #563) | Les retirer, comme la maquette : on perdrait cette règle |
| La largeur du contenu gardée à 70rem | La maquette plafonne elle aussi son contenu à 1072 px, mesuré ; tranché par time-knight | Élargir au-delà : des lignes de texte trop longues |
| « Se déconnecter » dans le `nav` de l'en-tête | La maquette y met son lien de droite ; gardé par time-knight (revue de code, constat 3) | Le sortir du `nav`, comme le proposait la revue |
| L'ancre écrite en Python, l'`id` par le contexte | Une seule constante pour les deux (revue de code, constat 5, gardé) | L'ancre écrite dans le gabarit |

Imposé par les règles du dépôt : aucun script, aucun style en ligne (`tests/web/test_templates.py`), des cibles de
44 px (Opquast 186), aucune espace avant « : » dans le texte du site.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_every_link_to_another_site_says_so_and_opens_a_new_tab_it_announces` | chaque lien `http` ou `https` de chaque page porte `target="_blank"`, `rel` avec `noopener` et `noreferrer`, et « site externe, nouvel onglet » |
| `test_every_link_to_another_site_has_the_same_form_its_arrow_held_to_its_text` | la flèche après `&nbsp;`, puis l'annonce en `.link-note`, sur le fil comme sur `/sources` |
| `test_a_link_within_the_site_opens_in_the_same_tab` | aucun lien du site n'a de `target` |
| `test_a_link_of_a_page_is_a_button_that_lands_on_the_line_of_the_results` | les deux liens de page en `button-secondary` vers `#resultats`, l'`id` présent, le formulaire inchangé |
| `test_the_empty_feed_says_so_and_proposes_seven_days` | « Élargir à 7 jours » sans ancre (son `href` finit à `period=7"`) |
| `test_the_first_line_of_a_card_gives_its_kind_its_date_its_identifiers_then_its_mark` | l'ordre de la ligne d'une carte, pour les 14 items de la fixture |
| `test_with_the_check_a_page_offers_to_sign_out_once_in_its_header`, `test_the_refusal_offers_to_sign_out_once_by_its_button` | un seul « Se déconnecter » par page : dans l'en-tête, ou le bouton de la 403 |
| `test_the_kind_of_a_card_is_framed_as_in_the_mockups`, `test_the_layout_of_the_mockups_holds_at_each_width` (13 règles) | chaque règle de mise en page reste dans son palier |
| Mesure dans Chrome sans interface, du formulaire de la fixture | 585 → 405 px à 1280, 585 → 453 à 1024, 606 → 539 à 820, 728 → 692 à 390, 814 → 734 à 320 ; aucun débordement à 320 px |
| `ruff check --no-cache`, `ruff format --check`, `mypy --strict`, `uv run pytest` | verts : 4776 tests réussis |
| `/security-review` ; `/code-review` (high) | aucune faille ; 7 constats, 5 corrigés dans `fbe710d`, 2 gardés |

## Ce que tu dois pouvoir défendre

1. **« Ouvrir un nouvel onglet est déconseillé : pourquoi le faire ? »** C'est une demande de l'utilisatrice, et la
   technique WCAG G200 ne le déconseille que sans besoin. Le RGAA 4.1.2 interdit seulement une fenêtre ouverte sans
   action (critère 13.2) : ici, il faut cliquer. Opquast 146 demande de prévenir : le texte de chaque lien le dit
   (`feed.py:405-407`).
2. **« À quoi sert `noopener noreferrer` ? »** Sans `noopener`, la page ouverte pourrait remplacer l'onglet de K-B
   par une autre page (*reverse tabnabbing*). `noreferrer` n'envoie pas l'adresse de la page de K-B, déjà retenue
   par `Referrer-Policy: no-referrer` : défense en profondeur.
3. **« Sans JavaScript, comment le site sait-il la largeur de l'écran ? »** Par les *media queries* de la CSS
   (`site.css:490-513`), en `rem` : elles suivent aussi la taille de police que la personne a choisie dans son
   navigateur.
4. **« L'ancre `#resultats` ne crée-t-elle pas une seconde adresse pour la page 2 (Opquast 169) ? »** Non : le
   fragment n'est jamais envoyé au serveur. `/?page=2` et `/?page=2#resultats` sont la même ressource ; le fragment
   ne dit au navigateur que l'endroit où défiler.
5. **« Un test ne voit pas l'écran : qu'est-ce qui prouve la mise en page ? »** Les tests gardent chaque règle de la
   feuille de style dans son palier. La preuve du rendu est la mesure dans Chrome, avant et après, aux cinq
   largeurs, et les captures comparées à la maquette. Cette mesure n'est pas dans la CI.

## Zones non vérifiées

- **Le rendu dans Safari et Firefox, et sur un vrai téléphone** : seules des captures de Chrome sans interface ont
  été faites. Aux largeurs de 320 et 390 px, la page était dans un `iframe` de cette largeur : Chrome sans
  interface garde une fenêtre d'environ 500 px au moins. Cet `iframe` n'émule ni la densité ni le tactile d'un
  téléphone.
- **L'ancre au clavier et à VoiceOver**, et **la validité du code au validateur du W3C** : Sabine les vérifie en
  ligne après le tag (tri de time-knight).
- **Les couleurs forcées de Windows** : la relecture d'accessibilité bornée les regarde, sans Windows. La bordure
  de la sorte est à l'encre, et celle des boutons transparente : en couleurs forcées, les deux deviennent la couleur
  du texte. Cela est supposé d'après la règle des couleurs forcées, pas observé.
- **Les navigateurs récents donnent déjà le comportement de `noopener` à `target="_blank"`** : je l'ai lu dans des
  sources secondaires, sans le vérifier dans la spécification HTML. La PR l'écrit de toute façon.
- **La lisibilité de l'annonce en 0,75rem** pour une personne qui voit mal : le contraste est mesuré, pas le
  confort de lecture.

## Ce qui reste

- **Le titre d'une carte en lien vers le détail de l'item** : #564, PR 1 (le détail des cinq sortes).
- **Les tendances et leur lien « Tendances »** dans l'en-tête : #564, PR 2. Il n'y a pas de menu repliable :
  décision D2 de Sabine sur le plan de #564.
- **Le formulaire reste plus haut que la maquette sur un téléphone** (692 px contre 398 à 390 px), à cause des
  trois aides : limite assumée, écrite au journal ADR.
