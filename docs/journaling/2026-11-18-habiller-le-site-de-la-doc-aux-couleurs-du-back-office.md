# Habiller le site de la doc aux couleurs du back office

- **Date** : 2026-11-18
- **Branche** : `docs/doc-site-theme`
- **Issue** : #649
- **Fichiers** : `mkdocs.yml`, `documentation/stylesheets/extra.css`, `documentation/accessibilite_pour_docu.md`,
  `documentation/integration_continue_pour_docu.md` (un renvoi de ligne décalé)
- **Série** : suit [la publication des fiches en site accessible](2026-11-18-publier-les-fiches-en-site-accessible.md),
  qui a choisi MkDocs avec Material et écrit la déclaration d'accessibilité.

## Le pourquoi

En lisant le site de la doc en local, Sabine a relevé trois points. Sur ordinateur, deux menus l'entourent : la
navigation à gauche, la table des matières de la page à droite, et elle s'y perd. Il n'y a pas de barre de
navigation. Les couleurs sont celles du thème par défaut, pas celles de K-B. Elle a demandé un seul menu, une barre
en haut, un menu rangé par partie du produit, et la charte du back office du site de K-B. Le site de la doc est le
format de remise des fiches au jury, et la déclaration d'accessibilité en fait partie : changer les couleurs oblige
à remesurer chaque contraste.

## Le comment

### Un seul menu et une barre d'onglets : trois réglages du thème

Material range la table des matières à droite par défaut. Trois réglages changent la disposition
(`mkdocs.yml:34-37`) :

```
  features:
    - navigation.tabs
    - navigation.tabs.sticky
    - toc.integrate
```

`navigation.tabs` fait une barre d'onglets des entrées de premier niveau du `nav`. `navigation.tabs.sticky` la garde
visible quand la page défile. `toc.integrate` place la table des matières dans le menu de gauche, sous le lien de la
page ouverte : il ne reste qu'un menu. Ces trois réglages ne valent que sur un écran large, de 76,25em ou plus ; en
dessous, Material cache la barre et ouvre le menu par un bouton de l'en-tête.

### Un `nav` par partie du produit

Une barre d'onglets n'a de sens que si le `nav` a des rubriques : à plat, chaque fiche y prendrait un onglet. Le
`nav` est rangé en cinq parties, le choix de Sabine (`mkdocs.yml:8-13`) :

```
nav:
  - Démarrer:
      - index.md
      - installation_pour_docu.md
      - architecture_pour_docu.md
```

Les autres parties sont Données, IA, Qualité et livraison, Projet. Le rangement par bloc et par compétence de la
certification a été écarté par Sabine : le site documente le produit.

### Les couleurs : des variables du thème, pas des règles

Material dessine tout par des variables CSS. Les redéfinir sur `:root` suffit à changer l'en-tête, le fond, les
liens et le focus, sans réécrire ses règles (`documentation/stylesheets/extra.css:5-8`, `:15-19`) :

```
:root {
  /* The header and the bar of tabs: white on ink. */
  --md-primary-fg-color: #1C1E21;
  --md-primary-bg-color: #FFFFFF;
...
  --md-typeset-a-color: #0F5E6B;
  --md-accent-fg-color: #0F5E6B;
```

Les couleurs viennent de la planche « Charte graphique » des maquettes du 2026-11-09, relayées par la session qui a
fait le front : encre `#1C1E21`, gris lin `#F4F5F2`, sarcelle `#0F5E6B`. L'accent de Material dessine l'anneau de
focus : il prend la sarcelle, la couleur de focus de la charte. Un lien survolé garde la sarcelle foncée du front,
`#0A434C`, par sa propre règle, code compris (`:27-34`).

### L'anneau de focus sur fond d'encre

Sur l'en-tête, la sarcelle ne donnerait que 2,25:1 contre l'encre : un anneau à peine visible. L'en-tête, les
onglets, le lien d'évitement et le logo du menu d'un écran étroit prennent un anneau blanc
(`documentation/stylesheets/extra.css:52-70`) :

```
.md-header__button,
.md-nav__button,
.md-skip,
.md-tabs__link {
  outline-color: #FFFFFF;
}
...
.md-tabs__link {
  padding-inline: 0.4rem;
  outline-offset: -0.2rem;
}
```

Un onglet est aussi haut que sa liste, qui coupe ce qui dépasse : la relecture a vu l'anneau coupé en haut et en
bas. Il est donc dessiné à l'intérieur du lien (`outline-offset` négatif), et l'espace entre deux onglets passe de
l'élément de liste au lien, pour que l'anneau ne touche pas le texte. La liste des résultats de recherche n'avait pas
de couleur d'anneau dans le thème : elle prend la sarcelle, au lieu du bleu du navigateur (`:72-76`).

### Les contrastes, une ligne par paire

La déclaration (`documentation/accessibilite_pour_docu.md`, « Les contrastes du thème ») donne le rapport de chaque
paire de couleurs que le site dessine. Une couleur transparente du thème est d'abord posée sur son fond, puis
mesurée : par exemple, le fond d'un résultat de recherche survolé est `#0A434C` à 10 % sur le gris lin, soit
`#DCE3E1`. Toutes les paires passent le seuil de 4,5:1 ; la plus basse est le libellé d'une boîte au troisième
niveau d'un schéma Mermaid, 4,85:1, calculé et non vu.

## Choix faits et options écartées

- **Les variables du thème sur `:root`**, plutôt qu'une `palette` personnalisée de Material : sans `palette`, rien ne
  pose d'autres couleurs sur le `body`. Écarté : `theme.palette` avec `custom`, un réglage de plus. Limite écrite
  dans le commentaire de `extra.css:1-4` : ajouter une `palette` annulerait ces couleurs.
- **Le focus en sarcelle `#0F5E6B`**, tranché par time-knight contre mon avis (garder `#0A434C`, plus contrasté) :
  c'est la couleur de focus de la charte que Sabine a demandée, et 6,77:1 passe le seuil de 3:1 d'un composant
  d'interface.
- **La barre collante** (`navigation.tabs.sticky`) : Sabine ne trouvait pas de barre de navigation ; une barre qui
  disparaît au défilement aurait gardé le problème.
- **Ni largeur de 1 120 px ni pied de page de la maquette** : le contenu garde la grille de Material, et le pied de
  page n'a pas de texte. Seuls son fond blanc et son filet de pierre sont repris.
- **Sans `navigation.indexes`** : Material ne le permet pas avec `toc.integrate`.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run --locked --only-group docs mkdocs build --strict` : code de sortie 0 | `nav`, liens et ancres valides |
| HTML construit : `<nav class="md-tabs" aria-label="Onglets">` à cinq entrées, `md-nav--integrated` présent, aucun `md-sidebar--secondary` | une barre, un seul menu |
| Capture de Chrome sans interface, 1 280 px | en-tête d'encre, onglet ouvert souligné, table des matières dans le menu de gauche |
| Capture d'un onglet atteint au clavier, avant et après correction | l'anneau était coupé ; il est entier et ne touche plus le texte |
| Calcul des rapports par la formule des WCAG 2.1, couleurs composées comprises, refait par deux relectures neuves | chaque ligne du tableau de la déclaration |
| Couleurs lues dans Chrome par la seconde relecture : `#00000012` sur `#F4F5F2` dessiné `#E2E3E0` | les rapports lus à l'écran perdent au plus 0,07, sans passer sous 4,5:1 |
| Chaque renvoi `mkdocs.yml:N` et `extra.css:N` relu sur le fichier | les renvois pointent les bonnes lignes |

## Ce que tu dois pouvoir défendre

1. **Pourquoi l'onglet ouvert est-il souligné, et pas seulement en gras ?** Une différence de graisse seule est un
   signe faible ; le soulignement en ajoute un second, et tous les onglets ont la même couleur
   (`documentation/stylesheets/extra.css:46-50`).
2. **Pourquoi deux couleurs d'anneau de focus ?** Un anneau doit contraster avec son fond à 3:1. La sarcelle passe
   sur le gris lin (6,77:1), pas sur l'encre (2,25:1) : là, il est blanc (16,71:1).
3. **Un lecteur d'écran sait-il quel onglet est ouvert ?** Non : Material ne pose pas `aria-current`. C'est écrit
   dans les « Limites » de la déclaration.
4. **Et sur un téléphone ?** Pas de barre d'onglets sous 76,25em : le bouton de l'en-tête ouvre le menu sur la partie
   ouverte, et sa flèche de retour mène aux cinq parties. Ce bouton n'est pas atteint au clavier, un défaut du thème
   déjà présent sur `main` : il est écrit dans les « Limites », avec sa parade, et porté par #651.
5. **Pourquoi des contrastes « calculés, non vus » ?** Un aperçu local n'affiche pas les schémas Mermaid tant que le
   site n'est pas publié ; leurs couleurs sont calculées depuis les règles du thème.

## Zones non vérifiées

- Les schémas Mermaid dessinés avec ces couleurs : calculés, pas vus.
- Le rendu à 390 px : la capture de Chrome sans interface coupe le texte à droite, sur `main` comme sur cette
  branche ; écart de l'outil de capture ou défaut existant, non tranché.
- Firefox et Safari, et un lecteur d'écran.
- La planche « Charte graphique » elle-même : ses couleurs sont reprises du relevé de la session du front, non relues
  à la source.

## Ce qui reste

- `aria-current` sur l'onglet et la page ouverts : il faudrait surcharger les gabarits du thème ; hors de cette PR.
- Le bouton du menu d'un écran étroit, atteint au clavier : #651.
- La fiche de la conduite du projet (#512) ira dans la partie Projet, et la fiche des maquettes dans Démarrer.
