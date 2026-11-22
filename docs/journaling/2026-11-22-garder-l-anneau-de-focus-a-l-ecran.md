# Garder l'anneau de focus à l'écran quand le clavier fait défiler la page

- **Date** : 2026-11-22
- **Branche** : `fix/web-focus-ring-at-screen-edge`
- **Issue** : #700 (défaut D1 de l'essai du site du 2026-11-22)
- **Fichiers principaux** : `src/k_b/web/static/site.css`, `tests/web/test_stylesheet.py`, `docs/site-web.md`
- **Série** : la note de #693, [écrire la limite du focus dans le cadre des
  tendances](2026-11-22-ecrire-la-limite-du-focus-dans-le-cadre-des-tendances.md), traite du même anneau dans un
  autre défilement, celui du cadre du tableau.

Les commits de cette PR sont `1a3559d2` (la marge en bas, son test, la fiche), `91882c6b` (la marge des deux côtés,
après la revue) et `df76ceae` (la fiche, après la revue), plus celui de cette note. Les autres commits et fichiers listés
au lancement de la note sont l'histoire de `main` avant la branche, partie de `9658225a` : ils ne sont pas de cette PR.

## Le pourquoi

L'anneau de focus montre où est le clavier : sans lui, une personne qui navigue au clavier ne sait pas quel lien
Entrée va suivre. Le site le dessine sur chaque élément atteint au clavier, un contour bleu canard de 3 px posé à 2 px
de l'élément (charte du 2026-11-09).

L'essai du site du 2026-11-22, mené dans Chrome piloté par programme, a trouvé que l'anneau pouvait sortir en partie
de l'écran. Quand Tab atteint un élément à demi caché sous le bas de l'écran, Chrome fait défiler la page juste assez
pour montrer l'élément, pas son anneau. Les 5 px de l'anneau sous l'élément restaient hors de l'écran : 10 arrêts
coupés à 1 280 px, 41 à 200 %, 21 à 320 px.

L'anneau restait visible sur trois côtés, donc le critère WCAG 2.4.7 (focus visible) était tenu. La règle 165
d'Opquast, « Le focus clavier n'est ni supprimé ni masqué », ne l'était qu'en partie.

La revue a montré que le défaut existait aussi vers le haut, avec Maj+Tab. La correction tient donc les deux côtés.

## Le comment

### Ce que fait Chrome quand le focus arrive hors de l'écran

Quand le focus passe à un élément, le navigateur le fait défiler dans la vue. Chrome 157, mesuré le 2026-11-22, le
fait de deux façons :
- **Un élément entièrement hors de l'écran est centré** : son anneau est loin des bords.
- **Un élément en partie visible** est seulement ramené jusqu'au bord de l'écran : son bord bas au Tab, son bord haut
  au Maj+Tab. C'est le bord de l'élément qui touche celui de l'écran, et l'anneau, dessiné autour, dépasse.

Le site n'a pas de JavaScript : seul le CSS peut changer ce que Chrome fait défiler.

### La marge de défilement, la place de l'anneau

`scroll-margin` élargit la zone qu'un défilement vers l'élément doit montrer. Le navigateur fait défiler pour montrer
l'élément plus sa marge.

```css
  :focus-visible {
    outline: 3px solid var(--color-teal);
    outline-offset: 2px;
    /* Chrome scrolls an element partly out of the screen that Tab or Shift+Tab reaches only up to
       its edge. This margin keeps the ring in sight above and below it, the outline plus its offset. */
    scroll-margin-block: 5px;
  }
```
(`src/k_b/web/static/site.css:65-71`)

- **5 px**, c'est exactement la place de l'anneau : 3 px de contour plus 2 px d'écart.
- **`scroll-margin-block`** est la propriété logique pour le haut et le bas d'une page écrite de haut en bas. Le
  fichier n'emploie que des propriétés logiques (`docs/site-web.md`, « Feuille de style »).
- **Sur `:focus-visible`**, la règle de l'anneau, et non sur tous les éléments : la marge vit avec l'anneau, et ne
  vaut que pour un élément qui le porte. Un défilement vers un élément qui n'a pas le focus au clavier, comme la cible
  d'un lien de pagination, n'est pas visé par cette règle.

### Les couches décident entre deux marges

La feuille déclare ses couches dans un ordre fixe :

```css
@layer reset, base, layout, components;
```
(`src/k_b/web/static/site.css:13`)

Entre deux règles de couches différentes, la couche déclarée la plus tard gagne, quelle que soit la spécificité des
sélecteurs.

L'anneau est dans `base`. Deux composants ont déjà leur propre marge en haut, dans `components` :
- le champ du formulaire, atteint depuis le résumé des erreurs, `scroll-margin-block-start: 12rem` pour garder son
  libellé à l'écran (`site.css:489`) ;
- la ligne des résultats, cible des liens de pagination, `1rem` (`site.css:636`).

Elles gagnent sur la marge de l'anneau, et c'est voulu : 12rem et 1rem sont plus grands que 5 px, et gardent donc
aussi l'anneau à l'écran. En bas, ces composants n'ont pas de marge à eux et prennent les 5 px de l'anneau.

### Le test lit la règle elle-même

```python
    ring = int(width[1]) + int(offset[1])
    assert declarations.get("scroll-margin-block") == f"{ring}px"
```
(`tests/web/test_stylesheet.py:104-105`)

Le test lit, dans la seule règle `:focus-visible`, l'épaisseur du contour, son écart et la marge, puis vérifie que la
marge est leur somme. Il retire d'abord les commentaires, parce qu'un « : » dans un commentaire serait lu comme une
déclaration.

La somme lue dans la règle, plutôt qu'un « 5px » écrit en dur, fait qu'un anneau élargi sans sa marge fait échouer le
test.

## Choix faits et options écartées

- **Retenu : la marge sur `:focus-visible`, des deux côtés.** Elle corrige les deux cas mesurés, ne touche que les
  éléments qui portent l'anneau, et vit dans la même règle que lui.
- **Écart au plan.** La conception de #700, validée par Sabine, mettait la marge en bas seulement
  (`scroll-margin-block-end`). Elle écartait les deux côtés parce que « le haut de l'anneau n'est jamais coupé ».
  - Ce fait venait de deux mesures insuffisantes :
    - le script du plan arrêtait son retour en Maj+Tab dès le premier appui, parce que le focus était sorti de la
      page, et n'avait donc mesuré aucun arrêt ;
    - un second script ne testait qu'un élément entièrement au-dessus de l'écran, que Chrome centre.
  - `/code-review` a soulevé le cas d'un élément en partie au-dessus de l'écran. Mesuré, il est coupé de 5 px.
  - Le tri de la revue par time-knight, sur délégation de Sabine du 15/10, a fait passer la marge aux deux côtés.
- **Écarté : `scroll-padding-block` sur la page.** Il corrige aussi, mais il vaut pour tout défilement de la page, et
  il décale de 5 px la cible du lien d'évitement (mesuré, avec les deux côtés).
- **Écarté : une marge sur chaque élément que le clavier atteint.** Elle corrige aussi, mais elle jouerait hors du
  focus clavier, et ne vivrait plus avec l'anneau.
- **Écarté, constat CR3 de la revue : lire l'anneau en rem aussi dans le test.** L'anneau de la charte est en px, tenu
  par `test_the_focus_ring_is_the_one_of_the_chart`. Un passage en rem ferait échouer le test de façon visible, sans
  rien laisser passer (tri de time-knight).

## Preuve

Mesures faites dans Chrome 157.0.8103.80 sans interface, au clavier seul, sur les 24 pages de
`tests/web/test_accessibility.py`, à 1 280 px, à 200 % (640 px CSS à 2 px d'écran par px CSS) et à 320 px. L'avant et
l'après sont pris sur le même commit, `main` 9658225a, sans puis avec la marge (constat CR2 de la revue). Ce n'est pas
un contrôle à la main.

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| Le test de la marge en bas, lancé sur la feuille de `main` : `assert None == '5px'` ; puis passe | Le test voit l'absence de marge. |
| Le test des deux côtés, lancé sur `1a3559d2` (marge en bas seulement) : `assert None == '5px'` ; puis passe sur `91882c6b` | Le test exige les deux côtés. |
| Tab du premier arrêt au dernier : 10 / 41 / 21 bas d'anneau coupés sans la marge, 0 / 0 / 0 avec | Le défaut D1 est corrigé. |
| Maj+Tab du dernier arrêt au premier : 6 / 25 / 19 hauts coupés sans la marge, 0 / 0 / 0 avec | Le même défaut existait en haut, et il est corrigé. |
| Chaque arrêt placé à 1 px, puis à mi-hauteur, hors de l'écran, puis Tab ou Maj+Tab, 544 essais de chaque côté par réglage : 144 / 312 / 322 bas et 149 / 342 / 359 hauts coupés sans la marge, 0 avec | La marge tient même dans les positions les plus défavorables. |
| L'essai du matin, comparé arrêt par arrêt avant et après : défilement en largeur, arrêts, anneau et lien d'évitement inchangés | La marge ne change rien d'autre, et le lien d'évitement mène toujours au même endroit. |
| Le cadre des tendances, plus haut que l'écran à 200 % et à 320 px : anneau coupé de 1 à 2 px en haut au lieu de 6 à 7, de 5 px de plus en bas | Le seul autre effet, sur un élément qui ne peut pas tenir à l'écran. |
| `explore-fin.mjs` sur le fil à 200 % : 46 arrêts, retour au premier, puis le focus hors de la page au premier Maj+Tab | La cause de l'erreur du plan. |
| `uv run ruff check --no-cache`, `ruff format --check`, `mypy --strict` (199 fichiers), `uv run pytest` : 5 799 réussis | Les contrôles du dépôt sont verts sur `91882c6b`. |

Les relevés datés et les captures sont hors du dépôt, dans le dossier de la session, transmis au Second.

## Ce que tu dois pouvoir défendre

1. **Pourquoi 5 px et pas plus ?** C'est la place de l'anneau, 3 px plus 2 px, et le test le tient par la somme lue
   dans la règle. Plus serait une marge sans raison, que rien ne mesure. (`site.css:66-70`,
   `test_stylesheet.py:104-105`)
2. **Le formulaire garde-t-il ses 12rem ?** Oui. La marge du champ est dans la couche `components`, déclarée après
   `base`, et l'emporte quelle que soit la spécificité. 12rem gardent aussi l'anneau à l'écran. (`site.css:13`,
   `site.css:489`)
3. **Le lien d'évitement mène-t-il toujours au contenu ?** Oui, à la même place sur les 24 pages et dans les trois
   réglages, mesuré avant et après. `scroll-padding-block`, qui vaut pour tout défilement de la page, l'aurait
   décalée de 5 px.
4. **Pourquoi le plan s'est-il trompé sur le haut ?** Une mesure vide, prise pour un résultat : le retour en Maj+Tab
   s'arrêtait au premier appui. La leçon : une mesure qui ne trouve rien se vérifie aussi, en comptant les arrêts
   qu'elle a vraiment parcourus.
5. **Et WCAG 2.4.7 ?** Le critère était déjà tenu : l'anneau se voyait sur trois côtés. La correction rend l'anneau
   entier, ce que demande la règle 165 d'Opquast.

## Zones non vérifiées

- Firefox, Safari (macOS et iOS) et Android : rien n'a été mesuré hors de Chrome 157.
- Le zoom par le menu de Chrome, un vrai téléphone, le site en ligne : l'essai reproduit le zoom par la taille de la
  page.
- Le bouton du calendrier d'un champ de date porte l'anneau de Chrome, pas celui du site. Il n'est pas compté, et
  Chrome ne fait pas défiler la page quand l'icône est visible.
- 16 essais par réglage, élément placé sous l'écran, où Tab n'est pas arrivé sur l'arrêt placé : ils n'ont pas été
  examinés un par un.
- La spécification de `scroll-margin` n'a pas été relue pour ce cas. Le comportement est mesuré, pas déduit.

## Ce qui reste

- Le lien en partie hors du cadre des tendances reste coupé sur le côté par le cadre : c'est #693, une limite écrite,
  que cette marge ne touche pas.
- WAVE et l'essai au clavier de Sabine, avant la fusion.
