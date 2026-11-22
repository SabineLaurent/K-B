# Écrire la limite du focus dans le cadre du tableau des tendances

- **Date** : 2026-11-22
- **Branche** : `docs/web-trends-focus-limit`
- **Issue** : #693 (née de la relecture accessibilité de #618)
- **Fichiers principaux** : `src/k_b/web/templates/accessibilite.html`, `tests/web/test_accessibility.py`,
  `docs/site-web.md`
- **Série** : suit [`2026-11-14-afficher-les-tendances-sur-le-site.md`](2026-11-14-afficher-les-tendances-sur-le-site.md)
  (le tableau de 560 px qui défile dans son cadre, #596) et
  [`2026-11-22-montrer-que-le-tableau-des-tendances-continue.md`](2026-11-22-montrer-que-le-tableau-des-tendances-continue.md)
  (l'ombre au bord du cadre, #618).

Le changement tient dans deux commits de la PR, `b0fdf73b` (la limite, son test, la fiche) et `84d0c821` (le tri de la
revue) ; ses autres commits ajoutent cette note et la corrigent. Les autres commits et fichiers listés au lancement de
la note sont l'histoire de `main` avant la branche, partie de `bbfb6510` : ils ne sont pas de cette PR.

## Le pourquoi

Le tableau des tendances a 560 px de large au moins ; sur un écran plus étroit, il défile dans son cadre
(décision de Sabine du 2026-11-14). La relecture accessibilité de #618 a relevé qu'à 390 px, le cadre défilé vers la
droite, Tab vers le lien d'une ligne laisse le début du lien caché, et son anneau de focus coupé à gauche.

L'issue demandait de reproduire le défaut sur `main`, de mesurer où le navigateur fait défiler le cadre, puis de
chercher une correction en CSS seul (le site n'a pas de JavaScript), ou d'écrire la limite si rien ne tient. Les
mesures n'ont trouvé aucune règle CSS qui corrige le Tab sans un autre défaut : Sabine a validé d'écrire la limite
(« ok conception #693 »). Ce travail ne change donc aucun comportement du site ; il dit à l'utilisatrice, dans la
déclaration d'accessibilité, ce que le site ne fait pas, et garde dans la fiche du site la mesure et les options
écartées, pour que personne ne les réessaie à l'aveugle.

## Le comment

### 1. Le cadre : un conteneur qui défile, atteint au clavier

```html
<div class="table-frame" role="region" aria-labelledby="trends-caption" tabindex="0">
```
`src/k_b/web/templates/trends.html:26`

```css
    overflow-x: auto;
```
`src/k_b/web/static/site.css:942`

Le cadre est un conteneur qui défile horizontalement (`overflow-x: auto`). Il prend le focus (`tabindex="0"`) pour
qu'on puisse le faire défiler aux flèches (WCAG 2.1.1). Chaque ligne du tableau a un lien, dans la deuxième colonne
(« Dépôt »). Quand ce lien prend le focus, c'est le navigateur, pas le site, qui décide s'il fait défiler le cadre
pour le montrer : sans JavaScript, le site n'a aucune prise sur ce choix, sauf par le CSS.

### 2. La mesure : le clavier simulé dans Chrome sans interface

La page des tendances est rendue par le site lui-même (un `TestClient` et la fixture de dix tendances, outil
`wip/618/tools/render_trends.py`), puis ouverte dans Chrome 157 sans interface. Le script envoie de vraies touches
par le protocole DevTools, comme un clavier :

```js
async function press(key, shift = false) {
  const common = { key, code: key, windowsVirtualKeyCode: KEYS[key], modifiers: shift ? 8 : 0 };
  await send("Input.dispatchKeyEvent", { type: "rawKeyDown", ...common });
```
`wip/693/tools/focus.mjs:31-33` (dossier `wip/`, ignoré par git : l'outil n'entre pas dans le dépôt)

Le parcours : Tab jusqu'au cadre, quarante flèches à droite, puis Tab vers le lien de la première ligne. À chaque
étape, le script lit la position du cadre (`scrollLeft`), les bords du lien et ceux de son anneau, puis dit si
l'anneau tient dans le cadre :

```js
    const ring = parseFloat(style.outlineWidth) + parseFloat(style.outlineOffset);
    ...
    result.ringInside = link.left - ring >= inner.left && link.right + ring <= inner.right;
```
`wip/693/tools/focus.mjs:50-53`

L'anneau déborde du lien de `outline-width` + `outline-offset`, 3 px + 2 px (`site.css:66-67`).

### 3. Ce que fait Chrome : il ne défile que vers un lien entièrement caché

À 390 px, le cadre défilé au bout (`scrollLeft` 219 sur 219), Tab sur le lien de la ligne 1 laisse le cadre à 219 :
le lien va de −138 à 130 px, le cadre de 17 à 358 px. Pour vérifier le mécanisme, un essai élargit la première
colonne pour que le lien parte **entièrement** hors du cadre : Chrome défile alors, de 0 à 341, et centre le lien.
D'où la règle observée : au Tab, Chrome ne fait défiler le cadre que si le lien en est entièrement sorti ; en
partie visible, le lien laisse le cadre où il est.

Deux autres cas mesurés : le cadre défilé de 160 px donne un lien de −79 à 189 px (le cas de la relecture) ; à
320 px, sans aucun défilement, le lien va de 81 à 349 px pour un cadre de 17 à 288 px, coupé à droite. Enfin, le
focus sur le lien, dix flèches à gauche ramènent le cadre à 0 : les flèches font défiler le cadre, et le focus
reste sur le lien.

### 4. La limite, dite à l'utilisatrice et tenue par un test

```html
<li>Dans le tableau des tendances qui défile dans son cadre, un lien en partie hors du cadre n’y est pas ramené quand il prend le focus, constaté dans Chrome (Firefox et Safari ne sont pas vérifiés): une partie du lien et un côté de son anneau de focus restent cachés. Les flèches du clavier font défiler le cadre, et le focus reste sur le lien.</li>
```
`src/k_b/web/templates/accessibilite.html:33`

La puce rejoint les « Limites connues » de la déclaration. Elle dit le constat, le navigateur où il est fait, ce
qui n'est pas vérifié, et le moyen qui reste (les flèches). Pas d'espace avant « : » : la règle du texte du site,
tenue par `tests/web/test_accessibility.py`.

```python
def test_the_statement_says_a_link_partly_out_of_the_trends_frame_stays_partly_hidden():
    """WCAG 2.4.7 holds, but Chrome leaves the frame where it is on focus (docs/site-web.md)."""
    text = outline(PAGES["/accessibilite"]).text

    assert "un lien en partie hors du cadre n’y est pas ramené" in text
```
`tests/web/test_accessibility.py:689-693`

Le test suit le modèle de `test_the_statement_says_its_limits_of_the_detail` : une limite écrite dans la
déclaration est tenue par un test, pour qu'elle ne disparaisse pas sans qu'on le voie.

### 5. Ce que la revue a ajouté : la date, le renvoi, le fait seul

La déclaration change, donc sa date de mise à jour aussi (règle Opquast 6, « établie, puis mise à jour ») :

```html
<p>Déclaration établie le <time datetime="2026-11-11">11 novembre 2026</time>, mise à jour le <time datetime="2026-11-22">22 novembre 2026</time>.</p>
```
`src/k_b/web/templates/accessibilite.html:6`, tenue par `test_the_accessibility_statement_gives_its_date`
(`tests/web/test_accessibility.py:428-433`)

La liste « Ce que les tests vérifient » disait « l’anneau de focus visible au clavier », ce qui semblait contredire
la nouvelle limite ; elle renvoie maintenant à celle-ci (`accessibilite.html:24`). Dans la fiche, la phrase sur
`scroll-padding` ne garde que le fait mesuré (`docs/site-web.md:221-223`) : la première version disait « ne jouent
que pour `scrollIntoView` » en citant MDN, une déduction que MDN ne dit pas.

## Choix faits et options écartées

- **Retenu : écrire la limite, sans CSS nouveau** (conception validée par Sabine, « ok conception #693 »). Aucune
  règle CSS mesurée ne corrige le Tab sans un défaut ailleurs ; l'anneau reste visible sur ses autres côtés
  (WCAG 2.4.7).
- **Écarté : `scroll-padding-inline: 1rem` sur le cadre, `scroll-margin-inline: 1rem` sur le lien** (la piste de
  l'issue). Appliqués (16 px calculés), sans effet au Tab sur un lien en partie visible. En contrôle,
  `scrollIntoView({ inline: "nearest" })` les respecte (le lien vient à 33 px au lieu de 17), mais le site n'appelle
  aucun script.
- **Écarté : `scroll-padding-inline: 50%`.** Il centre le lien qui ne touche pas le milieu du cadre (de −138 à 130,
  le lien vient de 54 à 322) ; il laisse le cas à −79 px, qui touche le milieu, et les 320 px.
- **Écarté : aimanter le cadre sur la colonne « Dépôt » tant qu'un lien a le focus** (`:has(a:focus-visible)`,
  `scroll-snap-type: x mandatory`, `scroll-snap-align: start` sur la colonne). Il tient à 390 px (lien de 25 à 293),
  pas à 320 px (anneau coupé de 10 px à droite) ; et, une seule position d'aimantation, il bloque le défilement du
  cadre tant qu'un lien a le focus : étoiles et *forks* hors de vue.
- **Écarté : l'aimantation seule** (`proximity` ou `mandatory`) : sans effet au Tab.
- **Écarté sans essai : figer la colonne « Dépôt »** (`position: sticky`). Il change le défilement dans le cadre,
  que la décision du 2026-11-14 (#596) garde hors périmètre.
- **Imposé par le dépôt** : pas de JavaScript dans le navigateur (`docs/site-web.md:4`, et la CSP `default-src 'none'`, sans `script-src`, `docs/site-web.md:314-315`) ; une règle Opquast
  non tenue l'est par décision écrite (`conformite.md`) : ici la 165, « Le focus clavier n'est ni supprimé ni
  masqué », tenue en partie, et cette PR en est la décision écrite.
- **Tri de la revue** : les quatre constats de `/code-review` corrigés, tranché par time-knight (le Second),
  délégation de Sabine du 15/10.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_statement_says_a_link_partly_out_of_the_trends_frame_stays_partly_hidden`, lancé avant la puce : 1 failed ; après : passe | La déclaration dit la limite, et le test l'aurait vue manquer. |
| `test_the_accessibility_statement_gives_its_date` passé à `2026-11-22`, lancé avant le gabarit : 1 failed ; après : passe | La date de mise à jour suit le changement. |
| Chrome 157, 390 px, cadre au bout : `scrollLeft` 219 avant et après Tab, lien de −138 à 130 pour un cadre de 17 à 358 | Le défaut existe sur `main` (e8bbb5d2), et le cadre ne bouge pas du tout. |
| Lien rendu entièrement hors du cadre : `scrollLeft` de 0 à 341, lien de 164 à 211 | Chrome défile vers un lien entièrement caché, et le centre. |
| 320 px, sans défilement : lien de 81 à 349 pour un cadre de 17 à 288 | Le défaut existe aussi sans aucun défilement. |
| 390 px, dix ArrowLeft sur le lien : `scrollLeft` 0, focus sur la ligne 1, anneau dans le cadre | Les flèches font défiler le cadre et gardent le focus sur le lien. |
| `scroll-padding-inline: 1rem` : Tab sans effet ; `scrollIntoView` en contrôle : lien de 33 à 301 | La règle s'applique, mais pas au Tab sur un lien en partie visible. |
| `uv run ruff check --no-cache`, `ruff format --check`, `mypy --strict` (199 fichiers), `uv run pytest` : 5726 passed | Les contrôles du dépôt sont verts sur `84d0c821`. |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas corriger plutôt qu'écrire une limite ?** Aucune règle CSS mesurée ne fait défiler le cadre au
   Tab vers un lien en partie visible, et le site n'a pas de script. Les deux options qui « marchent » en partie ont
   un coût : `scroll-padding: 50%` laisse des cas, l'aimantation bloque le défilement et ne tient pas à 320 px.
   (`docs/site-web.md:214-227`)
2. **Le focus reste-t-il visible (WCAG 2.4.7) ?** Oui dans tous les cas mesurés : l'anneau se voit sur trois côtés,
   et les flèches ramènent le lien. Le critère 2.4.11 des WCAG 2.2 (focus non masqué) n'est pas dans le RGAA 4.1.2,
   qui reprend les WCAG 2.1 ; la règle Opquast 165, elle, n'est tenue qu'en partie, et la PR le dit.
3. **Est-ce un défaut de K-B ou du navigateur ?** Le comportement est celui de Chrome : il ne défile que vers un
   élément entièrement caché, mesuré par l'essai du lien éloigné. K-B en hérite parce que son tableau défile dans
   un cadre (choix du 2026-11-14) et que son lien porte l'annonce « (en anglais, site externe, nouvel onglet) »,
   qui l'élargit.
4. **Pourquoi un test pour une phrase ?** Une limite connue fait partie de la déclaration : si quelqu'un la retire
   sans corriger le défaut, le test échoue. (`tests/web/test_accessibility.py:689-693`)
5. **Pourquoi dire « constaté dans Chrome » ?** Seul Chrome a été mesuré ; écrire la limite pour tous les
   navigateurs aurait affirmé un fait non observé (`code.md`, « Journalisation » : n'affirmer que l'observé).

## Zones non vérifiées

- **Firefox, Safari (macOS et iOS), Android** : rien n'est mesuré hors de Chrome 157. Le tableau d'ally.js (non
  daté) rapporte le même comportement pour Gecko, Blink et WebKit ; il n'est pas revérifié.
- **Le mécanisme interne de Chrome** : la règle « entièrement caché » est déduite de mesures, pas lue dans le code
  de Chromium ; aucun bogue Chromium qui la décrit n'a été trouvé.
- **Les vrais noms de dépôts** : la fixture a des noms courts (`owner-0/repository-0`) ; un nom plus long élargit
  le lien. À 320 px, le lien et son anneau sont déjà plus larges que le cadre.
- **Chrome avec interface et un vrai clavier** : les touches sont simulées par le protocole DevTools, dans Chrome
  sans interface.
- **La base de la branche** : les mesures sont faites sur `main` e8bbb5d2 ; la branche part de `bbfb6510` (#698),
  qui ne touche que les pages d'erreur et `links.html`, pas le tableau.

## Ce qui reste

- Une correction, si un navigateur ou une règle CSS nouvelle permet un jour de faire défiler un conteneur vers un
  élément en partie visible au focus ; ou si le tableau cesse de défiler dans son cadre, ce qui reviendrait sur la
  décision du 2026-11-14 (Sabine).
- La mesure dans Firefox et Safari, faute d'outil dans cette session.
