# Corriger les relevés WAVE du site de la doc

- **Date** : 2026-11-18
- **Branche** : `docs/doc-site-keyboard`
- **Issue** : #654
- **Fichiers** : `mkdocs.yml`, `documentation/javascripts/search-list.js` (nouveau),
  `documentation/stylesheets/extra.css`, `documentation/accessibilite_pour_docu.md`, un renvoi de
  `documentation/integration_continue_pour_docu.md`
- **Série** : suit [l'habillage du site de la doc](2026-11-18-habiller-le-site-de-la-doc-aux-couleurs-du-back-office.md)
  (#652).

## Le pourquoi

Sabine a passé WAVE, l'outil de contrôle d'accessibilité de WebAIM, sur le site de la doc après le thème de #652.
Il relevait 15 erreurs de libellé de formulaire, un contraste très faible et une navigation au clavier qui semblait
cassée. Avant de corriger, il fallait savoir ce que le thème avait introduit et ce qui venait déjà de Material. Le
site de la doc est le format de remise des fiches au jury, et sa déclaration d'accessibilité ne doit rien affirmer
que WAVE contredit.

## Le comment

### Mesurer avant de corriger

Un script pilote Chrome par son protocole de débogage : il appuie sur Tab, relève l'élément atteint, sa place et son
anneau, compte les `input` et leurs `label`, lit l'arbre d'accessibilité et calcule les contrastes comme WAVE. Lancé
sur le site d'avant le thème (`a7d7c309`) et sur celui de #652, il a montré :
- les erreurs de libellé viennent des cases à cocher cachées de Material (5 vides et 3 multiples avant, 7 et 8 après) ;
  elles sont en `display: none`, donc absentes de l'arbre d'accessibilité ;
- le contraste faible est l'en-tête caché des résultats de recherche, sur un fond transparent que WAVE ne compose pas ;
- sur grand écran, le parcours au clavier suit la page ; seule la liste vide des résultats reçoit le focus sans rien
  montrer.

### La liste des résultats hors du Tab

Material met `tabindex="0"` sur la liste des résultats, pour qu'une longue liste défile au clavier. Mais sa recherche
se ferme sur la touche Tab avant que le focus ne bouge : le focus tombe alors sur la liste repliée, sans hauteur, et
disparaît, qu'elle ait des résultats ou non. Un script local d'une ligne la sort du Tab
(`documentation/javascripts/search-list.js:4`) :

```
document.querySelector(".md-search__scrollwrap")?.setAttribute("tabindex", "-1");
```

Les résultats s'atteignent par les flèches, depuis le champ de recherche, comme Material le prévoit. Le texte de la
liste (« 7 documents trouvés », « Aucun document trouvé ») reste lu : seul `tabindex` change.

### Un fond opaque pour l'en-tête caché de la recherche

L'en-tête des résultats a pour fond le voile transparent de Material. La feuille de style peint ce voile sur la
couleur de la page, avec les mêmes variables (`documentation/stylesheets/extra.css:199-203`) :

```
  background: linear-gradient(var(--md-default-fg-color--lightest) 0 0), var(--md-default-bg-color);
```

Le fond devient opaque et le rendu ne change pas (pixels identiques avant et après, en clair et en sombre). WAVE lit
alors la couleur de la page sous le texte. Aucune couleur n'est recopiée à la main.

### La fiche de l'accessibilité dans le menu

Avec `toc.integrate`, la table des matières d'une page pend sous son lien du menu. Hors du menu, la fiche de
l'accessibilité n'en avait plus. Elle revient en fin de menu, sans numéro, et garde son lien au pied de page
(`mkdocs.yml:26-27`) : la décision de Sabine.

## Choix faits et options écartées

- **Écrire les erreurs de libellé en limite**, plutôt que réécrire les gabarits du menu : les cases sont hors de
  l'arbre d'accessibilité, sans effet pour un lecteur d'écran (avis de tn-orchestrateur).
- **Un script plutôt que `visibility: hidden`** sur la liste : cachée, elle ne dirait plus « Aucun document trouvé »
  ni le nombre de résultats. Une première version ne la sortait du Tab que vide ; la relecture a montré que la
  recherche se ferme sur Tab, donc la liste est toujours repliée quand le focus l'atteint.
- **Le voile peint sur la page**, plutôt que sa couleur calculée à la main : une connaissance à un seul endroit (règle
  DRY de `code.md`).
- **Le tiroir des écrans étroits** (#651) reste pour une autre PR : le parcours au clavier n'est cassé que là, et la
  tâche 1 passe avant.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| Tab réel dans Chrome, 1 500 px, avant et après | la liste vide n'est plus un arrêt ; chaque arrêt est visible |
| Requête « postgresql » (7 résultats), puis Tab : le focus va au premier onglet, visible | la liste n'est plus un arrêt, même pleine |
| Pixels de l'en-tête de la recherche ouverte, avant et après : `#E3E4E1` en clair, `#2D2F31` en sombre | le fond opaque ne change rien à l'œil |
| Scan des contrastes, clair et sombre | plus aucune paire sous 4,5:1 |
| Arbre d'accessibilité de Chrome | les cases cachées n'y sont pas ; les radios du mode et la recherche y sont, nommés |
| `mkdocs build --strict` | menu, liens et ancres valides |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas corriger les 15 erreurs de WAVE ?** Elles portent sur des cases en `display: none`, que ni le
   clavier ni un lecteur d'écran n'atteignent. La déclaration le dit, avec les mesures.
2. **Le script casse-t-il la recherche ?** Non : il ne touche que `tabindex`. La saisie, les résultats, les flèches et
   Échap marchent comme avant.
3. **Le clavier était-il cassé ?** Sur grand écran, non : le panneau « Order » de WAVE omettait le bouton du mode. Sur
   un écran étroit, oui : le tiroir fermé reste dans l'ordre du Tab (#651).

## Zones non vérifiées

- WAVE lui-même : il sera repassé par Sabine sur l'aperçu avant la fusion.
- Firefox, Safari et un lecteur d'écran.

## Ce qui reste

- Le tiroir des écrans étroits et son bouton au clavier : #651.
- Un vrai bouton pour le mode : #653.
