# Montrer par une ombre que le tableau des tendances continue dans son cadre

- **Date** : 2026-11-22
- **Branche** : `feat/web-trends-scroll-shadow`
- **Issue** : #618
- **Fichiers principaux** : `src/k_b/web/static/site.css`, `tests/web/test_stylesheet.py`, `docs/site-web.md`
- **Série** : le tableau et son cadre qui défile viennent de
  [2026-11-14-afficher-les-tendances-sur-le-site.md](2026-11-14-afficher-les-tendances-sur-le-site.md).

La note couvre les deux commits de la branche : `0ab6ad33` (l'ombre et ses tests) et `e7d7040f` (le tri des revues).
Les autres commits et fichiers que l'outil liste viennent de `main`, déjà fusionnés. Ils ne font pas partie de
cette PR.

## Le pourquoi

Le tableau des tendances a 560 px de large au moins, comme sa maquette. Sur un écran plus étroit, il défile dans
son cadre (décision de Sabine du 2026-11-14, #596). À 390 px, le cadre montre 356 px des 560, et il coupe juste
entre la colonne « Dépôt » et les colonnes des comptes : rien n'est tronqué à l'œil. Sur macOS et iOS, la barre de
défilement n'apparaît que pendant le défilement. Rien ne disait donc qu'il restait deux colonnes à droite.

Une ombre au bord du cadre le dit, tant que le tableau continue de ce côté. Le site n'a pas de JavaScript : tout se
fait en CSS.

## Le comment

### Quatre dégradés : deux ombres fixées au cadre, deux caches qui défilent

```css
/* src/k_b/web/static/site.css:952-960 */
    background-image:
      linear-gradient(to right, var(--color-card) 50%, var(--color-card-clear)),
      linear-gradient(to left, var(--color-card) 50%, var(--color-card-clear)),
      linear-gradient(to right, var(--color-stone), var(--color-stone-clear)),
      linear-gradient(to left, var(--color-stone), var(--color-stone-clear));
    background-position: 0 0, 100% 0, 0 0, 100% 0;
    background-size: 1.5rem 100%, 1.5rem 100%, 0.75rem 100%, 0.75rem 100%;
    background-repeat: no-repeat;
    background-attachment: local, local, scroll, scroll;
```

C'est la technique de [Lea Verou (2012)](https://lea.verou.me/2012/04/background-attachment-local/), citée par
l'issue.

- **Les ombres.** Les deux derniers dégradés vont de la couleur des bordures vers le transparent, sur 0,75rem, l'un
  au bord gauche (`0 0`), l'autre au bord droit (`100% 0`).
- **Les ombres ne bougent pas.** Leur `background-attachment: scroll` les fixe au cadre : quand le tableau défile,
  elles restent au bord.
- **Les caches.** Les deux premiers dégradés sont blancs, la couleur du cadre, sur leur première moitié, puis
  s'effacent. Ils sont posés aux mêmes positions que les ombres, et sont dessinés par-dessus, car un fond se peint
  dans l'ordre inverse de la liste : le premier calque est au-dessus.
- **Les caches défilent avec le tableau.** Leur `background-attachment: local` les attache au contenu qui défile, pas
  au cadre.

Le résultat, aux trois moments du défilement :
- **Au début**, le cache de gauche est sur l'ombre de gauche et la couvre. Le cache de droite est posé à la fin du
  contenu, hors de vue : l'ombre de droite se voit.
- **Au milieu**, les deux caches sont hors de vue : les deux ombres se voient.
- **À la fin**, le cache de droite arrive sur l'ombre de droite : seule celle de gauche se voit.
- Un tableau qui tient dans son cadre, à 1280 px, a ses deux caches sur ses deux ombres : aucune ombre.

### Chaque dégradé finit sur sa propre couleur rendue transparente

```css
/* src/k_b/web/static/site.css:55-56 */
    --color-card-clear: #FFFFFF00;
    --color-stone-clear: #DADCD600;
```

Le premier code finissait sur `transparent`, qui est du noir transparent, `rgba(0, 0, 0, 0)`.
- **Ce que dit la spécification.** Un navigateur doit interpoler un dégradé en alpha prémultiplié : le blanc va alors
  directement vers le transparent.
- **Le risque.** Sans prémultiplication, un cache passerait par du gris à mi-chemin, une bande grise visible même
  sur un tableau qui tient. Firefox interpole en prémultiplié depuis sa version 36 (bug 591600), mais un cas restait
  faux en Firefox 120 à 122 (bug 1869681, encore ouvert), et le cas « Premultiplied alpha » n'a été corrigé qu'en
  Firefox 137 (bug 1904106). Ces trois bugs ont été lus le 2026-11-22, après une revue de code qui trouvait la
  première version de ce texte trop affirmative. Le milieu de l'ombre passerait par un gris plus sombre que `--color-stone` : #B6B6B5 sur blanc, où le lien
  tomberait à 3,67:1.
- **La correction.** Finir chaque dégradé sur sa propre couleur, d'alpha nul (les deux derniers chiffres `00`).
  Qu'on prémultiplie ou non, on ne passe alors jamais par une autre teinte. Les deux couleurs entrent dans la charte,
  `:root`, parce que la feuille n'écrit aucune couleur hors de ses propriétés.

### Le contraste : le texte d'abord

L'ombre a la couleur des bordures, `--color-stone` (#DADCD6). Le texte du tableau passe dessus quand il défile. Le
test calcule, par la formule de luminance relative de WCAG déjà présente dans le fichier, le contraste de chaque
couleur de texte sur l'ombre :

```python
# tests/web/test_stylesheet.py:538-545
def test_each_text_of_the_table_keeps_its_contrast_on_the_shadows_of_its_frame(text):
    ...
    for shadow in read_frame_shadows():
        assert measure_contrast(colours[text], colours[shadow]) >= 4.5
```

Les résultats : encre 12,08:1, ardoise 5,96:1, lien 5,36:1, lien survolé 7,91:1. Tous dépassent 4,5:1 (WCAG 1.4.3).

### Les tests qui tiennent le mécanisme

- `test_the_frame_shows_a_shadow_at_each_edge_the_table_continues_past` (`:435`) : l'ordre `local, local, scroll,
  scroll` et deux ombres.
- `test_the_covers_of_the_frame_hide_its_shadows_while_the_table_ends_at_their_edge` (`:415`) : chaque cache est à
  la position de son ombre, et sa partie pleine (50 % de 1,5rem, soit 0,75rem) est au moins aussi large que l'ombre.
  Sans cela, une bande grise resterait au bord d'un tableau qui tient.
- `test_each_gradient_of_the_frame_fades_to_its_own_colour_made_transparent` (`:402`) : chaque dégradé finit sur une
  propriété dont la valeur est la couleur de départ suivie de `00`.

## Choix faits et options écartées

- **Retenu : quatre dégradés en fond**, la technique citée par l'issue. Une seule règle, sans élément de plus, sans
  JavaScript.
- **Écarté : `container-type: scroll-state` et `animation-timeline: scroll()`**, plus directs, mais pas Baseline
  (plan du 2026-11-19).
- **`background-attachment: local` est permis.** La feuille n'emploie que des fonctions Baseline « Widely
  available ». Dans web-features (fichier `background-attachment.yml.dist`, v3.47.0, lu le 2026-11-22), la clé
  `css.properties.background-attachment.local` est « widely available » depuis le 2024-09-14. La fonction entière
  `background-attachment` ne l'est plus depuis le 2026-01-29, à cause de la valeur `fixed`, sans effet sur iOS.
  Comme `text-wrap: balance`, la valeur ne fait qu'ajouter : un navigateur qui ne la connaît pas laisse les caches
  sur les ombres, et ne montre aucune ombre.
- **L'ombre dans la couleur des bordures, sans couleur nouvelle.** Le choix a été gardé au tri (time-knight, le
  2026-11-22). L'ombre est discrète : 1,36:1 au plus sombre, mesuré par le relecteur accessibilité. Pour que le lien
  garde 4,5:1, on ne pourrait la foncer que jusqu'à 1,65:1 environ.
- **Pas de 3:1 pour l'ombre (WCAG 1.4.11).** Ce qu'elle dit est aussi donné ailleurs : la légende nomme les étoiles
  et les *forks* gagnés. La page Understanding 1.4.11 exempte un graphique quand « The information is available in
  another form », et la charte classe déjà `--color-stone` sur blanc en décor.
- **Aucune règle d'impression.** Le premier code retirait l'ombre à l'impression, comme le plan le prévoyait.
  - La revue de code a montré la règle inutile, et la mesure l'a confirmé : sur papier, le cadre ne défile plus.
    `local` s'y comporte comme `scroll`, et les caches restent sur les ombres.
  - En impression émulée dans Chrome 157, les captures avec et sans la règle ne diffèrent que de 4 pixels, dans le
    texte d'un lien.
  - La règle et son test ont été retirés. C'est un écart au plan, tranché par time-knight sur cette mesure.
- **Écarté : des ombres en pseudo-éléments `position: sticky`**, suggérées par la revue contre un repeint à chaque
  image du défilement. Le relecteur accessibilité a compté 40 événements `Paint` sur 20 crans de molette, avec ou
  sans les ombres : aucun repeint en plus n'a été mesuré.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| Rouge avant le code de `0ab6ad33` : 6 échecs (aucun `background-attachment`, aucune ombre, rien à l'impression) | Les tests vérifiaient bien le changement |
| Rouge avant `e7d7040f` : les dégradés finissaient sur `transparent`, `read_frame_gradients()` vide | Le test de CR5 échouait sur l'ancien CSS |
| Trois mutations du CSS (cache de 1rem, arrêt à 30 %, positions inversées), chacune annulée ensuite : `1 failed` à chaque fois | Le test des caches attrape le défaut qu'il vise |
| Chrome 157, 390 px : début, ombre à droite seule ; milieu, les deux ; fin, à gauche seule (`wip/618/shots`, hors du dépôt) | Le mécanisme marche dans un vrai navigateur |
| Chrome 157, 1280 px : `clientWidth` 1070 = `scrollWidth` 1070, aucune ombre aux bords | Un tableau qui tient ne montre rien |
| Chrome 157, couleurs forcées émulées : `background-image` vaut `none, none, none, none` aux trois positions, bordure gardée | En couleurs forcées, l'ombre disparaît, le cadre reste visible |
| Chrome 157, impression émulée : aucune ombre au bord | Pas besoin de règle d'impression |
| `ruff check --no-cache`, `ruff format --check`, `mypy --strict` (198 fichiers), `uv run pytest` (5671 passés), aucun caractère `Cc` ou `Cf` | Les contrôles du dépôt passent |

## Ce que tu dois pouvoir défendre

1. **Comment l'ombre sait-elle que le tableau continue, sans JavaScript ?** Elle ne le sait pas. Les caches
   défilent avec le contenu (`local`) et couvrent les ombres fixées au cadre (`scroll`) quand le contenu s'arrête à
   ce bord. C'est la géométrie du défilement qui décide (`site.css:952-960`).
2. **Pourquoi une ombre si pâle ?** Parce que le texte passe dessus et doit garder 4,5:1 (WCAG 1.4.3). Le lien
   bornerait l'ombre à 1,65:1 environ. L'ombre n'a pas à tenir 3:1 (WCAG 1.4.11), car la légende donne aussi
   l'information.
3. **Et dans un navigateur qui ne connaît pas `local` ?** Les caches restent sur les ombres, on ne voit aucune ombre :
   le tableau défile comme avant. C'est le même raisonnement que pour `text-wrap: balance`.
4. **Pourquoi `#FFFFFF00` plutôt que `transparent` ?** `transparent` est du noir transparent. Un moteur qui
   n'interpole pas en alpha prémultiplié en ferait une bande grise ; Firefox l'a fait faux dans certains cas avant sa
   version 137 (bugs 1869681 et 1904106). Une couleur qui finit sur elle-même transparente ne change jamais de teinte
   (`site.css:55-56`).
5. **Et en couleurs forcées de Windows ?** Le navigateur retire les dégradés, mesuré dans l'émulation de Chrome. Le
   cadre garde sa bordure, et la barre de défilement de Windows reste l'indice.

## Zones non vérifiées

- **Firefox, Safari (macOS et iOS) et Android** : rien n'a été mesuré hors de Chrome 157, faute de ces navigateurs
  sur la machine. Le support de `local` vient des données de MDN et de web-features, et le risque de Firefox est levé
  par construction, sans mesure.
- **Les vraies couleurs forcées de Windows** : seule l'émulation de Chrome a été vue. Que la barre de défilement
  reste visible est une hypothèse.
- **La perception de l'ombre** : à 1,36:1, tout le monde ne la voit pas ; aucun essai avec une personne.
- **Les maquettes** : le relecteur accessibilité n'a pas pu lire le canevas. On ne sait pas si la maquette des
  tendances montrait une ombre.

## Ce qui reste

- Le défaut relevé par le relecteur accessibilité, déjà présent avant #618 : après un défilement à droite, Tab vers
  le premier lien d'une ligne ne ramène pas tout le lien dans le cadre, et son anneau est coupé à gauche. Le texte de
  l'issue XS est prêt ; elle sera créée avec l'accord de Sabine.
- Une ombre plus visible, ou un indice textuel (une mention par requête de conteneur), sort du périmètre de #618.
