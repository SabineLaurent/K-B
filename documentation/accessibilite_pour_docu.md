# L'accessibilité de la documentation de K-B

> La documentation est communiquée dans un format qui respecte les recommandations d'accessibilité (par exemple
> celles de l'association Valentin Haüy ou de Microsoft).

— C8.5, C9.11, C11.9, C12.7, C13.8, C17.12, C18.7, C19.7, C20.7

Cette fiche dit sous quel format la documentation de K-B est communiquée, quelles recommandations d'accessibilité
elle suit, comment chaque règle est tenue dans les fiches, et ce qui n'est pas vérifié. Les renvois `fichier:ligne`
visent le dépôt au 2026-11-18: `mkdocs.yml`, `documentation/stylesheets/extra.css` et `.github/workflows/docs.yml`
arrivent avec cette fiche.

## Le format

Les fiches sont écrites en Markdown dans `documentation/`. MkDocs 1.6.1, avec le thème Material for MkDocs 9.8.1, en
fait un site HTML statique: une page par fiche, une page d'accueil ([La documentation de K-B](index.md)) et un
champ de recherche (`mkdocs.yml:3-25`, `:43-44`). Sur un écran large, de 76,25em (1 220 pixels par défaut) ou plus,
une barre d'onglets en haut de chaque page mène aux cinq parties de la documentation. Un seul menu, à gauche, y donne
les fiches de la partie ouverte et la table des matières de la page (`mkdocs.yml:34-37`). Sur un écran plus étroit, le
bouton de menu de l'en-tête ouvre le menu sur la partie ouverte, et sa flèche de retour mène aux cinq parties. Ce
bouton n'est pas atteint au clavier (« Limites »). Les couleurs sont celles du back office du site de K-B, tirées de
ses maquettes du 2026-11-09 (`documentation/stylesheets/extra.css:1-25`). Le site se publie sur GitHub Pages, à la
main (section [Publier](#publier)).

Le format de remise, un site publié par MkDocs ou un outil équivalent, est une décision de Sabine du 2026-11-11, et
l'outil, MkDocs avec Material, la sienne du 2026-11-12 ([journal des décisions](https://github.com/SabineLaurent/K-B/blob/main/docs/ADR/journal-decisions-projet.md),
2026-11-14, « Documentation publiée par un site MkDocs sur GitHub Pages »). Les deux outils sont dans un groupe de
dépendances à part, `docs` (`pyproject.toml`), que ni les tests ni l'image de K-B n'installent.

## Les recommandations suivies

Quatre sources: les trois premières lues le 2026-11-14, la quatrième le 2026-11-18.

- **L'association Valentin Haüy** (AVH), la page « L'essentiel à savoir » sur l'accessibilité des documents. Elle
    vise les documents de bureautique. Ses règles de structure valent pour une page HTML, et ce sont elles que la
    documentation suit: titres hiérarchisés, vraies listes, sommaire, alternative aux éléments non textuels, polices
    lisibles, couleurs contrastées, pas de couleur seule pour porter une information. Elle préfère le format `.docx` au
    PDF; les fiches n'ont ni l'un ni l'autre.
- **Microsoft**, la page <span lang="en">« Make your Word documents accessible to people with disabilities »</span>,
    pour deux règles que l'AVH ne détaille pas: un texte de lien qui a un sens lu seul, et des tableaux simples, pour
    les données seulement, à en-têtes de colonne.
- **Le RGAA 4.1.2**, le référentiel général d'amélioration de l'accessibilité, le référentiel français pour le
    HTML (WCAG 2.1, les <span lang="en">Web Content Accessibility Guidelines</span> du W3C, niveaux A et AA), version
    en vigueur le 2026-11-14; le RGAA 5 est annoncé pour la fin de 2026. Ses critères donnent la mesure de chaque règle
    dans les pages construites.
- **La notice d'accessibilité éditoriale d'AcceDe Web**, publiée par Atalan, dans sa version en ligne (les notices
    AcceDe Web en version 4.1.2). Elle s'adresse aux <q>contributrices et contributeurs éditoriaux</q> d'un outil de
    publication: ici, l'outil est MkDocs, et ses règles portent sur le texte des fiches. Elle dit d'elle-même: <q>Cette
    version en ligne couvre actuellement les WCAG 2.2 et le RGAA 4.1.2</q>; sa section 9 dit que ses règles
    supplémentaires sont <q>nécessaire[s] pour garantir la conformité RGAA 4.1 et WCAG 2.1</q>. Les fiches mises en forme
    sont vérifiées selon elle, règle par règle
    ([La vérification selon la notice d'AcceDe Web](#la-verification-selon-la-notice-daccede-web)).

## Les règles appliquées aux fiches

Le tableau suivant donne, pour chaque règle, sa source, comment elle est tenue dans les fiches mises en forme
(toutes, sauf celle du monitorage), et comment elle se vérifie. La fiche du monitorage suit (« Limites »).

| Règle | Source | Comment elle est tenue | Vérifiée par |
|---|---|---|---|
| Des titres hiérarchisés | AVH; Microsoft; RGAA 9.1 | Un seul titre de niveau 1 par fiche, puis `##` à `####` sans saut de niveau. Un paragraphe en gras n'est pas un titre. | Le contrôle du HTML construit |
| De vraies listes | AVH; RGAA 9.3 | Les listes Markdown, rendues en `ul` et `ol`. Chaque niveau est en retrait de quatre espaces: Python-Markdown, qui construit les pages, ne rattache à un point de liste que ce qui est en retrait de quatre espaces. | Le HTML construit |
| Un sommaire | AVH | La « Table des matières » de chaque page, tirée de ses titres par le thème, dans le menu de gauche, sous le titre de la page (`mkdocs.yml:37`); la barre d'onglets des parties et le menu de la partie ouverte. | Le contrôle du HTML construit |
| Une alternative à chaque élément non textuel | AVH; Microsoft | Les fiches n'ont aucune image. Chaque schéma Mermaid est annoncé par une phrase qui nomme le texte qui le décrit. | La relecture de chaque fiche |
| Des polices lisibles | AVH | Les polices du système de la lectrice, sans Google Fonts (`mkdocs.yml:30-31`). | La configuration |
| Un contraste suffisant | AVH; RGAA 3.2 | Les couleurs du back office de K-B, mesurées ([Les contrastes du thème](#les-contrastes-du-theme)) (`documentation/stylesheets/extra.css:5-34`); l'anneau de focus sarcelle (`:15-18`, `:72-76`), et blanc sur l'en-tête, les onglets, le lien d'évitement et le logo du menu d'un écran étroit (`:52-70`). | Le calcul des rapports de contraste |
| Pas la couleur seule | AVH; Microsoft; RGAA 3.1; RGAA 10.6 | Aucune fiche ne porte une information par la couleur. Un lien est souligné (`documentation/stylesheets/extra.css:88-91`): sa couleur seule, `#0F5E6B` contre le texte `#1C1E21`, ne donne que 2,25:1, sous le seuil de 3:1. L'onglet de la partie ouverte est en demi-gras et souligné (`:46-50`), de la même couleur que les autres onglets. Dans le menu, la page ouverte se distingue des autres liens par sa couleur, à 2,25:1 seulement, et par un second signe. Sur un écran large, sa table des matières est dépliée sous son lien, bordée d'un filet à gauche. Sur un écran plus étroit, une icône de table des matières suit son nom. Aucun schéma Mermaid n'a de style de couleur. | La relecture de chaque fiche; la feuille de style |
| Des liens explicites | Microsoft; RGAA 6.1 | Le texte d'un lien nomme sa cible: ni adresse brute, ni « ici », ni « plus haut ». Un lien vers un fichier du dépôt hors des fiches mène à sa page sur GitHub. | Le contrôle du HTML construit |
| Des tableaux simples à en-têtes | Microsoft; RGAA 5.6 | Des tableaux Markdown, rendus avec leurs en-têtes de colonne (`th`), annoncés par une phrase ou un titre. | Le contrôle du HTML construit |
| Des citations déclarées | AcceDe Web; RGAA 9.4 | Les mots d'une source, recopiés, forment une citation. En ligne, c'est un `q`, sans guillemets tapés: la feuille de style dessine les guillemets français, avec l'espace intérieure des guillemets tapés (`documentation/stylesheets/extra.css:93-97`). En bloc, comme l'intitulé du référentiel en tête de chaque fiche, c'est un `blockquote`, suivi de sa source. Le titre cité d'une section, d'une page ou d'un document, un mot dont on parle et un libellé d'interface gardent leurs guillemets tapés: ce ne sont pas des citations. | Le HTML construit; la relecture de chaque fiche |
| La langue de la page et ses changements | RGAA 8.3; RGAA 8.7 | `lang="fr"` sur chaque page (`mkdocs.yml:29`); un passage en anglais balisé `<span lang="en">`. Le pied de page du thème, en anglais, est retiré (`mkdocs.yml:63-65`). | Le contrôle du HTML construit |
| Aucune requête hors du site | (règle de K-B) | Le plugin `privacy` télécharge à la construction ce que le thème irait chercher ailleurs, Mermaid compris, et le sert avec le site (`mkdocs.yml:45-46`), sauf dans deux cas (« Limites »). | Le contrôle du HTML construit |

### Les contrastes du thème

Les rapports de contraste suivants sont calculés selon la formule des WCAG 2.1, le 2026-11-18. Ils portent sur les
couleurs de `documentation/stylesheets/extra.css:5-34` et, pour le code et les schémas, sur celles de la feuille de
style construite de Material 9.8.1. Une couleur transparente du thème est d'abord posée sur son fond, et c'est la
couleur obtenue qui est mesurée. Ces couleurs composées sont calculées, non lues à l'écran. Chrome dessine
`#00000012` sur `#F4F5F2` en `#E2E3E0`, et non en `#E3E4E1`: les rapports ainsi lus perdent au plus 0,07, sans
passer sous le seuil. Le seuil du RGAA 3.2 est de 4,5:1 pour un texte de taille normale. Toutes les paires le passent. Un
aperçu local n'affiche pas les schémas Mermaid tant que le site n'est pas publié (« Limites »): leurs paires sont
calculées, non vues.

| Texte | Couleurs | Rapport |
|---|---|---|
| Le texte d'une fiche, d'un tableau, du menu; le titre d'un résultat de recherche | `#1C1E21` sur `#F4F5F2` | 15,27:1 |
| Une ligne de tableau sous le pointeur | `#1C1E21` sur `#EBECE9` | 14,09:1 |
| Un lien dans une ligne de tableau sous le pointeur | `#0F5E6B` sur `#EBECE9` | 6,25:1 |
| Ce lien, lui-même sous le pointeur ou le focus | `#0A434C` sur `#EBECE9` | 9,22:1 |
| Un texte secondaire: le titre de niveau 1, un bloc de citation, le titre d'une partie dans le menu d'un écran large, le titre « Table des matières » du menu entre 60em et 76,25em, l'extrait d'un résultat de recherche, l'indication du champ de recherche ouvert | `#4A4F57` sur `#F4F5F2` | 7,53:1 |
| Le titre d'une partie dans le menu d'un écran étroit, le titre « Table des matières » de ce menu sous 60em, l'en-tête des résultats de recherche | `#4A4F57` sur `#E3E4E1` | 6,46:1 |
| Un lien; la page ouverte dans le menu; la partie ouverte dans le menu d'un écran étroit; un lien du menu sous le pointeur ou le focus; un mot cherché, souligné dans un résultat de recherche; le lien des autres résultats d'une même page | `#0F5E6B` sur `#F4F5F2` | 6,77:1 |
| Un lien d'une fiche sous le pointeur ou le focus | `#0A434C` sur `#F4F5F2` | 9,99:1 |
| Le code dans un lien d'une fiche | `#0F5E6B` sur `#FFFFFF` | 7,41:1 |
| Le code dans un lien d'une fiche sous le pointeur ou le focus | `#0A434C` sur `#DCE3E1` | 8,39:1 |
| Un résultat de recherche sous le pointeur ou le focus: son titre | `#1C1E21` sur `#DCE3E1` | 12,82:1 |
| Un résultat de recherche sous le pointeur ou le focus: son extrait | `#4A4F57` sur `#DCE3E1` | 6,33:1 |
| Un résultat de recherche sous le pointeur ou le focus: un mot cherché; le lien des autres résultats d'une même page sous le pointeur ou le focus | `#0F5E6B` sur `#DCE3E1` | 5,69:1 |
| Le texte de l'en-tête, des onglets et du titre du menu d'un écran étroit | `#FFFFFF` sur `#1C1E21` | 16,71:1 |
| L'indication du champ de recherche, dans l'en-tête | `#CFE3E6` sur `#151618` | 13,61:1 |
| L'indication du champ de recherche, dans l'en-tête, sous le pointeur | `#CFE3E6` sur `#38393C` | 8,68:1 |
| Le lien d'évitement | `#F4F5F2` sur `#1C1E21` | 15,27:1 |
| Le code | `#36464E` sur `#FFFFFF` | 9,80:1 |
| Le code coloré: commentaire, variable, opérateur, ponctuation | `#4A4F57` sur `#FFFFFF` | 8,24:1 |
| Le code coloré: mot-clé | `#3F6EC6` sur `#FFFFFF` | 4,93:1 |
| Le code coloré: nombre | `#D52A2A` sur `#FFFFFF` | 5,01:1 |
| Le code coloré: commande intégrée | `#6E59D9` sur `#FFFFFF` | 5,13:1 |
| Le code coloré: chaîne | `#1C7D4D` sur `#FFFFFF` | 5,13:1 |
| Le code coloré: caractère échappé | `#DB1457` sur `#FFFFFF` | 4,94:1 |
| Le libellé d'une flèche d'un schéma | `#36464E` sur `#F4F5F2` | 8,95:1, calculé, non vu |
| Le libellé d'une boîte d'un schéma, hors de tout sous-graphe | `#36464E` sur `#DCE3E1` | 7,52:1, calculé, non vu |
| Le titre d'un sous-graphe d'un schéma, premier niveau | `#36464E` sur `#E3E4E1` | 7,68:1, calculé, non vu |
| Le titre d'un sous-graphe d'un schéma, deuxième niveau | `#36464E` sur `#D3D4D1` | 6,58:1, calculé, non vu |
| Le titre d'un sous-graphe d'un schéma, troisième niveau | `#36464E` sur `#C4C5C2` | 5,65:1, calculé, non vu |
| Le libellé d'une boîte dans un sous-graphe de premier niveau | `#36464E` sur `#CDD4D2` | 6,51:1, calculé, non vu |
| Le libellé d'une boîte dans un sous-graphe de deuxième niveau | `#36464E` sur `#BFC5C3` | 5,60:1, calculé, non vu |
| Le libellé d'une boîte dans un sous-graphe de troisième niveau | `#36464E` sur `#B1B8B6` | 4,85:1, calculé, non vu |

Le troisième niveau est celui du schéma du déploiement sur Azure, dans
[la fiche de l'architecture](architecture_pour_docu.md).

Hors de l'en-tête, l'anneau de focus est sarcelle, `#0F5E6B`, la couleur de focus de la charte
(`documentation/stylesheets/extra.css:15-18`), y compris sur la liste des résultats de recherche (`:72-76`). Il donne
6,77:1 sur `#F4F5F2`, au-dessus du seuil de 3:1 du RGAA 3.3 pour un composant d'interface. Sur l'en-tête, les onglets,
le lien d'évitement et le logo du menu d'un écran étroit, il est blanc, `#FFFFFF`: 16,71:1 sur `#1C1E21`, là où la
sarcelle ne donnerait que 2,25:1 (`:52-70`). Le contour d'un bloc de code, `#DADCD6` sur blanc, est un décor: il ne porte aucune
information.

## La vérification selon la notice d'AcceDe Web

Le 2026-11-18, les dix pages mises en forme, toutes sauf la fiche du monitorage, ont été vérifiées selon chaque règle de la notice d'accessibilité éditoriale
d'AcceDe Web, sur le HTML construit par `mkdocs build --strict` et à la relecture. Le tableau suivant donne chaque
règle de la notice, son résultat, et comment il a été vérifié.

| Règle de la notice | Résultat | Vérifiée par |
|---|---|---|
| 1. Ne pas utiliser les sauts de lignes multiples | Tenue: aucune balise `br` hors des schémas Mermaid, aucun paragraphe vide. | Le HTML construit |
| 2. Utiliser correctement la hiérarchie des titres | Tenue: un titre de niveau 1 par page, puis aucun saut de niveau. | Le HTML construit |
| 3.1. Rédiger des intitulés de liens explicites | Tenue (règle « Des liens explicites » des [règles appliquées aux fiches](#les-regles-appliquees-aux-fiches)). | Le HTML construit |
| 3.2. Savoir utiliser les titres de liens en dernier recours | Tenue dans le texte des fiches: aucun lien n'y a d'attribut `title`. Les deux liens du logo du thème, dans l'en-tête et dans le menu, en portent un, le nom du site (« Limites »). | Le HTML construit |
| 4.1 à 4.3. Images décoratives, informatives, images-liens | Sans objet: aucune image. | Le HTML construit |
| 4.4. Images informatives complexes: un court texte de remplacement et une description détaillée | Tenue pour les huit schémas des fiches mises en forme (un dans le service d'IA, quatre dans l'architecture, un dans l'API IA, deux dans l'import et la base): chacun a un titre et une description courts (`accTitle` et `accDescr`, que Mermaid rend en `title` et `desc` du dessin), et le texte qui le suit pour description détaillée. Le rendu dans un navigateur n'est pas vérifié. | La relecture |
| 5. Utiliser correctement les listes à puces et listes numérotées | Tenue: des listes Markdown, en retrait de quatre espaces, aucune liste tapée à la main. | Le HTML construit |
| 6.1. Déclarer les citations en ligne et les blocs de citations | Tenue: une citation en ligne est un `q`, un bloc de citation un `blockquote` (règle « Des citations déclarées » des [règles appliquées aux fiches](#les-regles-appliquees-aux-fiches)). Chaque paire de guillemets tapés a été triée: celles qui restent entourent un titre, un mot dont on parle ou un libellé. | Le HTML construit; la relecture |
| 6.2. Déclarer les changements de langue | Tenue: chaque passage en anglais du texte des fiches est balisé `<span lang="en">`; le pied de page anglais du thème est retiré. | Le HTML construit |
| 6.3. Ne pas faire référence à un élément en se basant uniquement sur sa couleur, sa taille, sa forme ou sa position | Tenue: un renvoi nomme l'élément et suit l'ordre de lecture (« le tableau suivant donne… »), jamais une place à l'écran. | La relecture; le contrôle des renvois vagues |
| 7.1. Contrastes entre le texte et l'arrière-plan | Tenue ([Les contrastes du thème](#les-contrastes-du-theme)). | Le calcul des rapports de contraste |
| 7.2. Les couleurs ne sont pas le seul moyen de porter une information | Tenue: un lien est souligné. | La relecture; la feuille de style |
| 8.1. Associer une description détaillée aux contenus riches | Tenue: chaque schéma Mermaid a sa description en texte. | La relecture |
| 8.2 et 8.3. Contenus en mouvement; vidéos | Sans objet: ni l'un ni l'autre. | Le HTML construit |
| 9. Fournir une alternative textuelle aux contenus textuels ambigus (émoticônes, art ASCII) | Tenue: aucune émoticône ni art ASCII. La flèche « → » sert à écrire un chemin de menu ou le résultat d'une commande; ce qu'en dit un lecteur d'écran n'est pas vérifié. | Le HTML construit |

Ses bonnes pratiques: aucun lien n'ouvre de nouvelle fenêtre (aucun `target`, le pied de page du thème retiré); aucun fichier n'est proposé au
téléchargement; les capitales gardent leurs accents; aucun texte n'est justifié. Les sigles du domaine (RGAA, WCAG,
AELE, RGPD, PR, ADR, CVE, DINUM, OSV) sont développés à leur premier emploi dans chaque fiche; les sigles techniques
courants (API, HTML, URL, UTC, SHA) ne le sont pas. Le libellé d'un schéma ne compte pas comme premier emploi: un sigle
peut y paraître avant le texte qui le développe.

## Vérifier

1. Construire le site en mode strict:

    ```sh
    uv run --locked --only-group docs mkdocs build --strict
    ```

    Un lien vers un fichier absent, une ancre absente ou une fiche oubliée dans la navigation arrête la construction
    (`mkdocs.yml:55-61`). Le workflow `docs.yml` la lance sur chaque demande de fusion
    (PR, <span lang="en">pull request</span>)
    (`.github/workflows/docs.yml:6-9`, `:25`).

2. Le contrôle du HTML construit, lancé sur `site/` pour chaque PR de mise en forme, compte dans chaque page: l'attribut
    `lang`, les titres de niveau 1 et les sauts de niveau, les tableaux sans `th`, les liens dont le texte est une
    adresse, « ici » ou « plus haut », et les ressources chargées hors du site. Il n'est pas dans le dépôt: son résultat
    est écrit dans la PR.

3. Relire chaque fiche: les vraies listes, la phrase avant chaque schéma et chaque tableau, l'absence de couleur seule,
    et chaque paire de guillemets tapés, qui n'entoure pas une citation.

## Publier

Le workflow `docs.yml` publie le site sur GitHub Pages quand on le lance à la main, depuis `main` seulement
(`.github/workflows/docs.yml:9`, `:30-49`). Seul son job `deploy` a le droit d'écrire sur Pages (`:41-43`). Le
2026-11-14, Pages n'est pas activé sur le dépôt (`gh api repos/SabineLaurent/K-B/pages` rend 404). Avant la
première publication, deux gestes de Sabine:

1. Rendre le dépôt public, comme prévu (il est privé le 2026-11-14). Pages ne sert un dépôt privé qu'avec une offre
    payante de GitHub (Pro, Team ou Enterprise), et **un site publié depuis un dépôt privé est public**: activer Pages
    sur le dépôt encore privé publierait toutes les fiches.
2. Dans les réglages du dépôt, <span lang="en">Settings > Pages > Build and deployment > Source</span>, choisir
    <span lang="en">« GitHub Actions »</span>.

Puis lancer le workflow `Docs` depuis l'onglet <span lang="en">Actions</span>, sur `main`. Cette procédure n'a pas
été essayée.

## Limites

- **Le rendu au lecteur d'écran n'est pas vérifié.** Le contrôle porte sur le HTML, pas sur ce qu'un lecteur d'écran
    en dit. Parade: un essai avec VoiceOver par Sabine sur une fiche de chaque lot, le site construit.
- **Lue sur GitHub, une citation en ligne ne reçoit pas la feuille de style du site.** Le rendu de GitHub garde le
    `q` (vérifié le 2026-11-18 par son rendu Markdown, `gh api markdown`), mais pas la feuille de style du site: le
    navigateur devrait y dessiner les guillemets de la langue de la page de GitHub, l'anglais (propriété CSS
    `quotes`, valeur `auto`). Ce rendu n'a pas été vu. Le format de remise est le site.
- **La fiche du monitorage n'est pas encore mise en forme.** Elle garde, le 2026-11-18, des listes en retrait de deux
    ou trois espaces, trois renvois de position (deux « ci-dessus », un « plus bas »), et ses citations entre guillemets,
    sans `q`. Elle est mise en forme après les PR de #620 et #621, qui la changent.
- **Les schémas larges sont réduits à la largeur du texte.** Dans l'architecture, le flux en bref et le déploiement
    sur Azure sont dessinés sur 688 pixels de large, et leurs libellés ne se lisent qu'avec le zoom du navigateur
    (relevé le 2026-11-18 dans Chrome sans interface). Le texte qui suit chaque schéma le décrit flèche par flèche.
- **La partie et la page ouvertes ne sont signalées qu'à la vue.** Le thème marque l'onglet de la partie ouverte et
    le lien de la page ouverte par une classe CSS, sans attribut `aria-current` (relevé le 2026-11-18 dans le HTML
    construit). Sans cet attribut, rien dans le HTML ne les désigne comme courants pour un lecteur d'écran.
- **Le bouton du menu d'un écran étroit n'est pas atteint au clavier.** Sous 76,25em, ce bouton est un `label` du
    thème, sans `tabindex`: la touche Tab ne s'y arrête pas (relevé le 2026-11-18 dans Chrome sans interface, à
    390 pixels; #651). Parade: le champ de recherche, atteint au clavier, mène à chaque fiche. Une fenêtre élargie, ou
    un zoom réduit, jusqu'à 76,25em ou plus fait paraître la barre d'onglets.
- **Les deux liens du logo du thème portent un attribut `title`**, le nom du site, sur chaque page, dans l'en-tête et
    dans le menu (règle 3.2 d'AcceDe Web).
    Il vient du thème, hors du texte des fiches.
- **Deux chargements hors du site restent possibles.** Le script du thème demande
    `resize-observer-polyfill` à unpkg sur un navigateur qui n'a pas `ResizeObserver`, ce que le plugin `privacy` ne
    rapatrie pas. Mermaid est appelé par l'adresse du site publié, `site_url` (`mkdocs.yml:5`): tant que Pages n'est
    pas activé, un aperçu local de `site/` n'affiche pas les schémas.
- **Un schéma Mermaid est dessiné par un script.** Sans JavaScript, la page montre son code source; le texte qui le
    décrit reste lisible dans les deux cas.
- **Mermaid est téléchargé depuis unpkg à la construction**, dans sa dernière version 11 (`mermaid@11`), une version
    qui bouge. Parade: le workflow `docs.yml` vérifie l'empreinte du fichier téléchargé, celle de Mermaid 11.17.2,
    vérifiée le 2026-11-14 contre l'empreinte que npm publie pour son paquet; un autre fichier arrête la construction
    (`.github/workflows/docs.yml:26-29`). Une nouvelle version 11 de Mermaid demande de refaire cette vérification et
    de changer l'empreinte.
- **Material for MkDocs est en fin de vie le 2027-05-05**: ses corrections de sécurité s'arrêtent à cette date. Son
    successeur, Zensical, lit `mkdocs.yml`; la migration n'est pas faite.
- **Le site n'est pas en ligne** le 2026-11-14 (section [Publier](#publier)).

## Sources

Lues le 2026-11-14:

- Association Valentin Haüy, « L'essentiel à savoir »,
    [page de l'accessibilité des documents](https://www.avh.asso.fr/nos-solutions/accessibilite/accessibilite-numerique/documents-courriels/essentiel-savoir).
- Microsoft, <span lang="en">« Make your Word documents accessible to people with disabilities »</span>,
    [page du support de Microsoft](https://support.microsoft.com/en-us/office/make-your-word-documents-accessible-to-people-with-disabilities-d9bf3683-87ac-47ea-b91a-78dcacb3c66d).
- Direction interministérielle du numérique (DINUM), RGAA 4.1.2,
    [critères et tests](https://accessibilite.numerique.gouv.fr/methode/criteres-et-tests/), qui annonce le RGAA 5 pour la fin de 2026.
- GitHub, <span lang="en">« What is GitHub Pages? »</span>,
    [page de la documentation de GitHub](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages),
    pour l'offre qui permet Pages sur un dépôt privé.
- GitHub, <span lang="en">« Configuring a publishing source for your GitHub Pages site »</span>,
    [page de la documentation de GitHub](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).
- Material for MkDocs, [notes de la version 9.8.1](https://github.com/squidfunk/mkdocs-material/releases/tag/9.8.1),
    pour sa fin de vie; versions de MkDocs et de Material lues sur PyPI, sans faille connue dans la base OSV
    (<span lang="en">Open Source Vulnerabilities</span>).

Lues le 2026-11-18:

- MDN, la propriété CSS `quotes`,
    [page de MDN](https://developer.mozilla.org/docs/Web/CSS/quotes), par Context7 et une recherche web: les
    guillemets d'un `q` se fixent par des paires de chaînes; la valeur `auto`, par défaut, suit la langue héritée.
- Atalan, AcceDe Web, « Notice d'accessibilité éditoriale »,
    [version en ligne](https://www.accede-web.com/notices/editoriale/), ses neuf sections et ses bonnes pratiques
    (pages de la section `notices/editoriale-modele/`). Context7 ne la couvre pas: elle a été lue à la source, après
    une recherche web du même jour.
