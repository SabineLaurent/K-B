# Habiller le site de la doc aux couleurs du back office

- **Date** : 2026-11-18
- **Branche** : `docs/doc-site-theme`
- **Issue** : #649
- **Fichiers** : `mkdocs.yml`, `documentation/stylesheets/extra.css`, `overrides/partials/copyright.html`,
  `documentation/accessibilite_pour_docu.md`, l'en-tête de neuf fiches, un renvoi de
  `documentation/integration_continue_pour_docu.md`
- **Série** : suit [la publication des fiches en site accessible](2026-11-18-publier-les-fiches-en-site-accessible.md),
  qui a choisi MkDocs avec Material et écrit la déclaration d'accessibilité.

## Le pourquoi

En lisant le site de la doc en local, Sabine a relevé que deux menus l'entouraient (la navigation à gauche, la table
des matières à droite), qu'il manquait une barre de navigation, et que les couleurs n'étaient pas celles de K-B. Sur
une première version, elle a demandé ensuite : un menu de gauche plus large, numéroté par partie ; une barre du haut
pour d'autres liens, comme le dépôt GitHub ; un pied de page ; un mode clair et un mode sombre ; le code en ligne sur
un bleu léger ; les rappels de compétence dans un encadré. Le site de la doc est le format de remise des fiches au
jury, et sa déclaration d'accessibilité en fait partie : chaque couleur changée se remesure.

## Le comment

### La disposition : réglages du thème et `nav`

Trois réglages donnent un seul menu et une barre en haut (`mkdocs.yml:42-46`) : `navigation.tabs` fait une barre des
entrées de premier niveau du `nav`, `navigation.tabs.sticky` la garde visible, `toc.integrate` place la table des
matières de la page sous son lien, dans le menu de gauche. `navigation.sections` affiche les parties comme des
rubriques. Le `nav` porte donc la documentation et deux liens en premier niveau, et les parties en second
(`mkdocs.yml:10-13`) :

```
nav:
  - Documentation:
      - K-B, mon outil de veille tech: index.md
      - 1. Démarrer:
```

Les deux autres entrées de premier niveau, « Le dépôt GitHub » et « Le journal des décisions », sont des adresses :
Material en fait des onglets. La déclaration d'accessibilité sort du menu, le pied de page y mène
(`mkdocs.yml:29-31`). Sans `not_in_nav`, le mode strict refuserait une page absente du menu.

### Le pied de page : un gabarit surchargé

Material lit d'abord les gabarits de `custom_dir` (`mkdocs.yml:37`). `overrides/partials/copyright.html` remplace son
pied de page par une liste de trois liens. Le lien vers la déclaration passe par le filtre `url`, qui le rend relatif
à chaque page : `{{ 'accessibilite_pour_docu/' | url }}`.

### Deux modes, chaque couleur écrite une fois

`theme.palette` déclare un schéma clair (`default`) et un schéma sombre (`slate`), chacun avec sa requête
`prefers-color-scheme` et le libellé de son bouton (`mkdocs.yml:47-63`). À la première visite, le site prend le
réglage du système ; ensuite, Material garde le mode affiché. Material pose `color-scheme: light` ou
`dark` selon le schéma. La fonction CSS `light-dark()` choisit alors sa première ou sa seconde valeur, ce qui permet
d'écrire chaque couleur une seule fois (`documentation/stylesheets/extra.css:42-43`) :

```
    --md-typeset-a-color: light-dark(var(--kb-teal), var(--kb-frost));
    --md-accent-fg-color: light-dark(var(--kb-teal), var(--kb-frost));
```

Le bloc est sous `@supports (color: light-dark(#000000, #FFFFFF))` (`:11`). Un navigateur sans `light-dark()` jugerait
ces couleurs invalides : le texte blanc de l'en-tête resterait sans fond. Il saute donc le bloc et garde les couleurs
de Material ; les règles de K-B hors du bloc ont des valeurs de repli, celles du thème. La charte n'a pas de mode sombre : il prend ses couleurs là où elles existent (encre, lin, pierre,
« canard givré » pour les liens, sarcelle foncée), et en ajoute deux sortes, nommées « hors charte » dans la déclaration : `#121416` et les couleurs du code coloré
sombre de Material.

### Le menu plus large

Élargir la barre latérale (`inline-size: 15rem`) ne suffisait pas : Material tient le menu à 11,5rem par une marge
intérieure, `padding-right: calc(100% - 11.5rem)`, quelle que soit la largeur de la barre. Une capture a montré la
barre à 300 px et le menu à 230 px. La surcharge remet cette marge à 0,6rem (`extra.css:69-78`).

### L'encadré des compétences

L'extension `admonition` (`mkdocs.yml:74-76`) donne les encadrés `!!! note`. Chaque fiche réunit ses rappels dans un
seul encadré, dont chaque citation garde son `blockquote` et sa source
(`documentation/import_et_base_pour_docu.md:3-7`) :

```
!!! note "Compétences de la certification"

    > Documentation des scripts.

    — C3
```

La feuille de style lui donne l'allure d'une alerte de GitHub : un filet coloré au début, un titre coloré, ni cadre
ni ombre (`extra.css:120-146`).

### Les contrastes, mesurés par un script

La déclaration donne, pour chaque texte que le site dessine, sa paire de couleurs et son rapport en mode clair et en
mode sombre : 35 lignes. Une couleur transparente est d'abord posée sur son fond. Le calcul a trouvé une paire sous
le seuil : en mode sombre, le voile de 12 % de Material, empilé sur trois niveaux d'un schéma Mermaid, donnait 3,62:1.
Le voile sombre passe à 8 % : 4,89:1. La plus basse paire du site est à 4,85:1.

## Choix faits et options écartées

- **`light-dark()`**, plutôt que deux blocs de variables sur `[data-md-color-scheme=default]` et `slate` : une couleur
  écrite une fois (demande de Sabine : du CSS moderne). Il est « Baseline » depuis mai 2024 (Chrome 123, Firefox 120,
  Safari 17.5), et sa limite pour un navigateur plus ancien est écrite.
- **Le focus en sarcelle `#0F5E6B`** en mode clair, tranché par time-knight contre mon avis (garder `#0A434C`) : c'est
  la couleur de focus de la charte. En mode sombre, l'accent est le canard givré, à 12,56:1.
- **Les liens du mode sombre en `#CFE3E6`**, la seule couleur de lien que la charte pose sur l'encre (relevé de FO). Ils
  sont proches du texte (1,22:1) : leur soulignement les distingue.
- **Les blocs de code restent blancs** en mode clair : sur le bleu léger du code en ligne, un mot-clé coloré passerait
  sous 4,5:1.
- **Les liens de la barre** : le dépôt et le journal des décisions. Le board reste privé (décision de Sabine).
- **Sans `navigation.indexes`** : Material ne le permet pas avec `toc.integrate`.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run --locked --only-group docs mkdocs build --strict` : code de sortie 0 | `nav`, `not_in_nav`, liens et ancres valides |
| HTML construit : trois onglets, `md-nav--integrated`, `data-md-color-scheme="default"` sur le `body`, deux `input` de mode avec `aria-label` | la barre, un menu, deux modes nommés |
| Captures de Chrome sans interface, 1 500 px, en mode clair et en mode sombre | menu numéroté sur une ligne, encadré, code en ligne, pied de page |
| Mesure dans Chrome : barre latérale 300 px, menu 230 px avant la surcharge | la cause du « K-B » coupé |
| Script de contraste (formule des WCAG 2.1, couleurs composées) | chaque ligne du tableau des deux modes |
| Deux relectures neuves sur la première version, une sur la seconde | renvois, rapports et rendu |

## Ce que tu dois pouvoir défendre

1. **Comment le site choisit-il son mode ?** À la première visite, le réglage du système (`prefers-color-scheme`) ;
   ensuite, le mode gardé par Material, que le bouton de l'en-tête change. `light-dark()` lit le `color-scheme` du
   schéma.
2. **Et un vieux navigateur ?** Il saute le bloc `@supports` et garde les couleurs par défaut de Material, lisibles,
   plutôt qu'un en-tête blanc sur blanc.
3. **Pourquoi des couleurs « hors charte » ?** La charte n'a pas de mode sombre. Le mode sombre prend ses couleurs là où
   elles existent, et nomme les autres dans la déclaration.
4. **L'encadré casse-t-il la citation ?** Non : chaque rappel reste un `blockquote` suivi de sa source, dans l'encadré.
5. **Un lecteur d'écran sait-il quel onglet est ouvert ?** Non : Material ne pose pas `aria-current`. C'est écrit dans
   les « Limites ».

## Zones non vérifiées

- Les schémas Mermaid avec ces couleurs : calculés, pas vus (un aperçu local ne les dessine pas).
- Le mode sombre lu à l'écran : les couleurs composées sont calculées ; seul le mode clair a été comparé aux pixels.
- Firefox et Safari, et un lecteur d'écran.
- Le rendu à 390 px de la capture sans interface, qui coupait déjà le texte sur `main`.

## Ce qui reste

- `aria-current` sur l'onglet et la page ouverts : il faudrait surcharger d'autres gabarits du thème.
- Le bouton du menu d'un écran étroit, atteint au clavier : #651.
- Un vrai bouton pour le mode, nommé par son action, qu'Entrée et Espace changent de la même façon : #653.
- La fiche de la conduite du projet (#512) deviendra la partie 5 du menu, et la fiche des maquettes entrera dans
  « 1. Démarrer ».
