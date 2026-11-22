# Tenir le site sans défilement horizontal à texte 200 %

- **Date** : 2026-11-21
- **Branche** : `fix/web-reflow-at-200-percent`, commits `10553a28`, `45cbef1d` et `307dfd34`, sur `origin/main` à
  `36c1e02d`
- **Issue** : #599
- **Série** : suite de [Servir le fil de veille](2026-11-11-servir-le-fil-de-veille.md) (#563) et
  d'[Afficher les tendances sur le site](2026-11-14-afficher-les-tendances-sur-le-site.md) (#596)
- **Fichiers principaux** :
  - `src/k_b/web/static/site.css` ;
  - les gabarits `404.html`, `500.html`, `error.html`, `feed.html` et la macro `links.html` ;
  - les tests : `tests/web/test_stylesheet.py`, `tests/web/test_accessibility.py`, et trois tests qui citent le
    balisage d'un lien vers un autre site (`test_feed_page.py`, `test_item_page.py`, `test_trends_page.py`) ;
  - `docs/site-web.md`.

La liste des commits et des fichiers donnée à la note compare la branche à un `main` plus ancien. Les commits de
`36c1e02d` et d'avant viennent des PR déjà fusionnées, comme leurs fichiers (`infra/`, `docs/fiches-veille.md`,
`documentation/`, les autres notes). Cette note ne les couvre pas. `git diff --stat origin/main...HEAD` donne les
12 fichiers de la branche.

## Le pourquoi

Une personne qui lit mal agrandit le texte. Sur un téléphone de 320 px de large, à texte 200 %, plusieurs pages du
site défilaient en largeur : il fallait faire glisser la page de gauche à droite pour lire chaque ligne. Ce sont les
critères WCAG 1.4.4 (agrandir le texte à 200 % sans perte) et 1.4.10 (pas de défilement en deux dimensions à
320 px), soit les critères RGAA 10.4 et 10.11. Le relecteur d'accessibilité de #564 l'avait relevé sur la 404, la
500 et le formulaire du fil. La flèche d'un bouton, de plus, passait seule sur sa ligne.

La mesure du jour, sur les 24 pages que rendent les tests d'accessibilité, à 7 largeurs et 9 tailles de texte,
trouvait 67 défauts sur `origin/main`. Après ces trois commits, elle n'en trouve plus aucun. À texte 100 %, la mise
en page des maquettes ne change pas.

## Le comment

### 1. Une requête de conteneur qui suit la taille du texte

Le cœur de la correction est une seule règle, en fin de feuille de style
(`src/k_b/web/static/site.css:1028`) :

```css
  @container body (inline-size < 15em) {
```

Une **requête de conteneur** applique des règles selon la largeur d'un élément ancêtre, le conteneur. Ici, ce
conteneur est le corps de la page, déclaré ainsi (`site.css:73`) :

```css
    container: body / inline-size;
```

`body` est le nom donné au conteneur, `inline-size` dit qu'on interroge sa largeur. Le point décisif est l'unité :
dans la condition d'une requête de conteneur, un `em` vaut la taille de police **du conteneur** (CSS Conditional 5,
section 5.1). Quand la personne agrandit le texte, l'`em` grandit avec lui. « Moins de 15em de large » veut donc dire
« étroit pour la taille du texte ». À texte 100 % (16 px), c'est moins de 240 px, ce qu'aucun écran n'atteint dès
320 px : la règle ne s'applique jamais, et les maquettes restent intactes. À texte 200 % (32 px), c'est moins de
480 px : les téléphones.

### 2. Ce qui change à fort zoom

Sous ce seuil, la feuille fait trois choses (`site.css:1028-1062`) :

```css
    .choices {
      grid-template-columns: minmax(0, 1fr);
    }
```

- **Une seule colonne** de cases et de boutons radio dans le formulaire du fil, au lieu de deux : à 200 %,
  « Releases » ne tenait plus dans sa demi-colonne (décision de Sabine du 2026-11-21).
- **Un titre plus petit** sur les pages d'erreur : `font-size: 1.625rem` au lieu de `2.125rem`. C'est la taille des
  autres titres sur un téléphone. Elle reste en `rem`, donc suit toujours le texte agrandi. Le mot « introuvable »
  de la 404 ne déborde plus.
- **Des marges qui ne doublent plus** avec le texte : la gouttière de la page (`--gutter: 0.25rem`), et la marge
  intérieure du formulaire, des cartes, des champs et des boutons. C'est ce qui fait tenir le champ de date : Chrome
  ne le rend pas plus étroit que son contenu, « jj/mm/aaaa » et l'icône du calendrier, soit 261 px à 200 %. Le forcer
  plus étroit couperait la date, une perte de contenu pire qu'un défilement.

### 3. Les colonnes de la carte d'incident de la 500

Hors de la requête, une seule règle change pour tous les écrans (`site.css:391`) :

```css
      grid-template-columns: repeat(auto-fit, minmax(min(12rem, 100%), 1fr));
```

Chaque colonne demandait au moins `12rem`, soit 384 px à texte 200 %, plus que l'écran. `min(12rem, 100%)` prend la
plus petite des deux valeurs : jamais plus large que la carte. À texte 100 %, `12rem` vaut 192 px et reste la plus
petite : rien ne change.

### 4. La flèche d'un bouton liée à son mot

Un bouton du site est un conteneur `flex` qui passe à la ligne (`flex-wrap: wrap`). Avant, la flèche et le texte
étaient deux éléments `flex` distincts : à 200 %, le texte passait sous la flèche, laissée seule. Désormais
(`src/k_b/web/templates/404.html:11`) :

```html
<a class="button" href="/"><span><span class="arrow-start" aria-hidden="true">←&nbsp;</span>Retour au fil de veille</span></a>
```

- Le `span` extérieur fait du libellé **un seul élément** du bouton : le texte passe à la ligne entre ses mots, comme
  un paragraphe.
- L'**espace insécable** (`&nbsp;`) interdit la coupure entre la flèche et « Retour ».
- Elle est **dans** le `span` caché (`aria-hidden="true"`), comme dans la macro des liens externes : le nom que
  lit un lecteur d'écran reste « Retour au fil de veille », sans espace en tête.

Le `gap` de 8 px du bouton ne séparait plus la flèche de son mot. Une marge le rend (`site.css:365-377`) : 0,25rem
pour `←` et `→`, et 0,5rem pour `↗`, dont l'espace insécable s'ajoutait déjà au `gap`. Mesuré à texte 100 % : 7,9 px
au lieu de 8 pour `←` et `→`, 11,9 px comme avant pour `↗`. Chaque flèche a sa classe (`arrow-start`, `arrow-end`,
`external-arrow`), parce qu'un sélecteur CSS ne voit pas le texte voisin : il ne peut pas savoir de quel côté poser
la marge.

La macro des liens vers un autre site reçoit le même `span` (`links.html:6`). Le bouton « Voir la fiche sur
nvd.nist.gov ↗ » d'une faille passait lui aussi sa flèche seule à la ligne.

### 5. Le fond de la page

Un élément conteneur ne transmet plus son fond à la toile de la fenêtre, visible quand une page rebondit en fin de
défilement. Le fond papier passe donc sur `html` (`site.css:64`), et `body` n'en porte plus.

## Choix faits et options écartées

- **Requête de conteneur plutôt que `auto-fit` et `min()` sur la grille des choix** (le plan validé du 19/11 prévoyait
  `auto-fit`). Avec `auto-fit`, la colonne unique serait apparue aussi à texte 100 % sur 320 px : elle changeait les
  maquettes et un test de leur mise en page. Écart technique tranché par time-knight.
- **Le corps comme conteneur**. La page n'a pas d'autre enveloppe (`body > header, main, footer`). `main` ne peut pas
  servir : une requête de conteneur ne style que les descendants, or elle doit réduire la marge de `main` lui-même.
  Mesuré : `body` ne devient pas le bloc contenant d'un élément `position: absolute` (le lien d'évitement garde sa
  place), et un contenu trop large fait toujours défiler la page.
- **Nommer le conteneur**. Le cadre du tableau des tendances est lui aussi un conteneur. Sans nom, une règle
  s'appliquerait au conteneur le plus proche. Le nom `page` a été écarté au profit de `body`, parce que `<main>` porte
  déjà la classe `page` : `@container page` aurait laissé croire qu'on interroge `main`.
- **15em plutôt que 18em**. Avec 18em, une police par défaut de 18 px (112 %) atteignait déjà le seuil à 320 px, et
  les marges y devenaient minces sans besoin. Mesure sans la requête : aucun défaut à 14,5em de large et au-delà.
  15em garde une marge.
- **Une espace insécable dans un seul `span`, plutôt qu'un `span` en `white-space: nowrap` autour de la flèche et de
  son mot** (la piste du plan). Avec `nowrap`, le reste du libellé serait devenu un second élément `flex`, et le `gap`
  de 8 px aurait élargi l'espace entre « Retour » et « au ».
- **Une marge sur la flèche plutôt qu'accepter 3,9 px** : time-knight a voulu que rien ne change à texte 100 %.
- **Champ de date** : pas de `min-inline-size: 0`, qui couperait la date.
- **`overflow-wrap: anywhere` sur les boutons**, écarté au profit d'une marge intérieure de bouton plus fine à fort
  zoom : il aurait coupé « nvd.nist.gov » au milieu d'un mot.
- Imposé par le dépôt : tailles en `rem` (test `test_every_font_size_is_in_rem`), fonctions CSS Baseline « Widely
  available » seulement (les requêtes de conteneur le sont depuis le 2025-08-14), aucun JavaScript.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_narrow_screen_for_the_size_of_its_text_takes_one_column_and_thin_margins` (7 cas) | chaque règle du fort zoom est dans la requête `@container body (inline-size < 15em)` |
| `test_the_body_is_the_container_of_the_queries_of_a_strong_zoom`, `test_the_canvas_takes_the_paper_of_the_pages` | le conteneur nommé sur `body`, le fond sur `html` seul |
| `test_the_card_of_an_incident_never_has_a_column_wider_than_itself` | la colonne `min(12rem, 100%)` |
| `test_the_arrow_of_a_button_stays_on_the_line_of_its_word` | sur toutes les pages rendues, chaque bouton fléché (au moins 404, 405, 500, page 2, détail d'un papier) a sa flèche liée à son mot, dans un seul `span` |
| `test_the_arrow_of_a_button_keeps_the_space_it_had_as_an_item_of_its_own` | les trois marges des flèches |
| `test_every_link_to_another_site_has_the_same_form_its_arrow_held_to_its_text` | chaque lien vers un autre site, du `span` ouvrant à l'annonce |
| Tests rouges avant le code : 12 (`10553a28`), 16 (`45cbef1d`), 9 (`307dfd34`) | les tests vérifiaient bien le changement |
| Mesure dans Chrome 157, 24 pages × 7 largeurs × 9 tailles de texte (1512 relevés) | 67 défauts sur `origin/main`, 0 sur `307dfd34` |
| Mesure des flèches sur 9 pages | à 200 %, aucune flèche seule (toutes l'étaient de 320 à 390 px sur `origin/main`) ; à 100 %, 7,9 et 11,9 px, hauteurs inchangées |
| Bouton « nvd.nist.gov » à 320 px et 200 % | 30 px de marge (−2 px avant la marge de bouton réduite) |

## Ce que tu dois pouvoir défendre

1. **Pourquoi une requête de conteneur et pas une media query ?** Dans une media query, l'`em` vaut la taille de
   police par défaut du navigateur, pas celle de la page. Dans une requête de conteneur, il vaut la police du
   conteneur : la règle suit le texte agrandi quelle que soit la façon de l'agrandir. Voir `site.css:1028`.
2. **Le titre plus petit à fort zoom, est-ce encore « 200 % » ?** Il reste en `rem` : il suit le texte. À fort zoom,
   il grandit de 1,53 fois au lieu de 2. *Understanding 1.4.4* (WCAG 2.2) admet qu'un texte grandisse de façon
   inégale d'un point de rupture à l'autre, tant que 200 % reste atteignable : le zoom de page le double. Voir
   `site.css:1036`.
3. **Que se passe-t-il à texte 100 % ?** Rien : 15em vaut 240 px, et aucun écran visé n'est si étroit. Le relecteur
   d'accessibilité a comparé les boîtes de toutes les pages, avant et après : seul l'espace entre une flèche et son
   mot différait, et la marge l'a rendu.
4. **Pourquoi ne pas rétrécir le champ de date ?** Chrome ne l'affiche pas plus étroit que « jj/mm/aaaa » et son
   calendrier. Plus étroit, la date serait coupée : c'est une perte de contenu, que 1.4.4 interdit. Ce sont les
   marges autour qui cèdent.
5. **Un lecteur d'écran lit-il la flèche ?** Non : elle est dans un `span` en `aria-hidden="true"`, avec son espace
   insécable. Le nom du lien reste son texte, vérifié dans l'arbre d'accessibilité de Chrome par le relecteur.

## Zones non vérifiées

- **D'autres systèmes** : seuls Chrome 157 et la police système de macOS ont été mesurés. Windows et Android ont
  d'autres polices. À 320 px et 200 %, le champ de date du fil a 286 px pour 278 demandés, et le bouton
  « nvd.nist.gov » 30 px de marge.
- **Firefox** (son zoom du texte seul), **Safari**, et un vrai téléphone.
- **Un vrai lecteur d'écran** : seul l'arbre d'accessibilité de Chrome a été lu.
- **L'impression** avec la requête de conteneur.
- **La propagation d'`overflow`** de `body` à la fenêtre, qu'un conteneur pourrait bloquer : `body` n'en porte pas
  aujourd'hui.
- **Les maquettes** : le canevas n'a pas pu être lu dans cette session. L'espace des flèches suit `origin/main`.

## Ce qui reste

- **Texte 200 % et espacement du texte de 1.4.12 ensemble**, que WCAG n'exige pas : à 320 px, 17 pages sur 24
  défilent encore, de 2 à 76 px.
- **Le bouton « Retour au fil de veille »**, écrit trois fois à l'identique dans les pages d'erreur : sa factorisation
  en macro est l'issue #681.
- **Le lien « ← Retour au fil » du détail** (`.back-link`, pas un bouton) garde son ancien balisage. Mesuré sans
  défaut, il est hors du périmètre.
