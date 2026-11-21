# L'accessibilité de la documentation de K-B

!!! note "Compétences de la certification"

    > La documentation est communiquée dans un format qui respecte les recommandations d'accessibilité (par exemple
    > celles de l'association Valentin Haüy ou de Microsoft).

    — C8.5, C9.11, C11.9, C12.7, C13.8, C17.12, C18.7, C19.7, C20.7

Cette fiche dit sous quel format la documentation de K-B est communiquée, quelles recommandations d'accessibilité
elle suit, comment chaque règle est tenue dans les fiches, et ce qui n'est pas vérifié. Les renvois `fichier:ligne`
visent le dépôt au 2026-11-18, et les fichiers qu'ils citent n'ont pas changé depuis (relu le 2026-11-21), sauf
`mkdocs.yml`, qui a reçu à sa ligne 16 l'entrée de la fiche des maquettes dans le menu (#619): ses renvois visent
le fichier avec cette ligne.
`mkdocs.yml`, `documentation/stylesheets/extra.css` et `.github/workflows/docs.yml` arrivent avec cette fiche.

## Le format

Les fiches sont écrites en Markdown dans `documentation/`. MkDocs 1.6.1, avec le thème Material for MkDocs 9.8.1, en
fait un site HTML statique: une page par fiche, une page d'accueil ([La documentation de K-B](index.md)) et un
champ de recherche (`mkdocs.yml:3-30`, `:72-73`). Sur un écran large, de 76,25em (1 220 pixels par défaut) ou plus,
une barre d'onglets en haut de chaque page mène à la documentation, au dépôt GitHub et au journal des décisions. Un
seul menu, à gauche, donne la page d'accueil, puis les quatre parties numérotées de la documentation et leurs fiches.
La table des matières de la page ouverte est sous son lien (`mkdocs.yml:39-45`). Sur un écran plus étroit, le bouton
de menu de l'en-tête ouvre ce menu sur la partie de la fiche ouverte, ou sur la liste des parties depuis l'accueil ou cette fiche.
Sa flèche de retour mène aux parties, puis au premier niveau, qui porte aussi les deux liens de la barre. Ce bouton
n'est pas atteint au clavier (« Limites »). Cette fiche est en fin de menu, sans numéro (`mkdocs.yml:27-28`). Le
pied de page y mène aussi, comme au dépôt et à la licence (`overrides/partials/copyright.html`). Les couleurs sont celles du back office du site de K-B, tirées de ses maquettes du 2026-11-09
(`documentation/stylesheets/extra.css:1-62`). Le site a un mode clair et un mode sombre. À la première visite, il
prend le réglage du système; ensuite, il garde le mode affiché, que la lectrice change par un bouton de l'en-tête
(`mkdocs.yml:46-62`). Le site se publie sur
GitHub Pages, à la main (section [Publier](#publier)).

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
    supplémentaires sont <q>nécessaire[s] pour garantir la conformité RGAA 4.1 et WCAG 2.1</q>. Les fiches sont
    vérifiées selon elle, règle par règle
    ([La vérification selon la notice d'AcceDe Web](#la-verification-selon-la-notice-daccede-web)).

## Les règles appliquées aux fiches

Le tableau suivant donne, pour chaque règle, sa source, comment elle est tenue dans les fiches, et comment elle se
vérifie.

| Règle | Source | Comment elle est tenue | Vérifiée par |
|---|---|---|---|
| Des titres hiérarchisés | AVH; Microsoft; RGAA 9.1 | Un seul titre de niveau 1 par fiche, puis `##` à `####` sans saut de niveau. Un paragraphe en gras n'est pas un titre. | Le contrôle du HTML construit |
| De vraies listes | AVH; RGAA 9.3 | Les listes Markdown, rendues en `ul` et `ol`. Chaque niveau est en retrait de quatre espaces: Python-Markdown, qui construit les pages, ne rattache à un point de liste que ce qui est en retrait de quatre espaces. | Le HTML construit |
| Un sommaire | AVH | La « Table des matières » de chaque page, tirée de ses titres par le thème, dans le menu de gauche, sous le titre de la page (`mkdocs.yml:45`); le menu donne la page d'accueil, puis les quatre parties numérotées et leurs fiches, puis cette fiche, sans numéro. | Le contrôle du HTML construit |
| Une alternative à chaque élément non textuel | AVH; Microsoft | Les deux images, les planches de la fiche des maquettes, ont chacune un texte de remplacement court qui nomme la section de leur description; cette description en texte en donne tout le contenu. Chaque schéma Mermaid est annoncé par une phrase qui nomme le texte qui le décrit. | La relecture de chaque fiche; chaque description de planche comparée au fichier source de la planche |
| Des polices lisibles | AVH | Les polices du système de la lectrice, sans Google Fonts (`mkdocs.yml:37-38`). | La configuration |
| Un contraste suffisant | AVH; RGAA 3.2 | Les couleurs du back office de K-B, en mode clair et en mode sombre, mesurées ([Les contrastes du thème](#les-contrastes-du-theme)) (`documentation/stylesheets/extra.css:8-62`); l'anneau de focus de la couleur de l'accent (`:42-43`, `:194-197`), et blanc sur l'en-tête, les onglets, le lien d'évitement, le logo du menu d'un écran étroit et le bouton du mode (`:172-186`). | Le calcul des rapports de contraste |
| Pas la couleur seule | AVH; Microsoft; RGAA 3.1; RGAA 10.6 | Aucune fiche ne porte une information par la couleur. Un lien est souligné (`documentation/stylesheets/extra.css:80-89`): sa couleur seule, contre le texte, ne donne que 2,25:1 en mode clair (`#0F5E6B` contre `#1C1E21`) et 1,22:1 en mode sombre (`#CFE3E6` contre `#F4F5F2`), sous le seuil de 3:1. L'onglet ouvert est en demi-gras et souligné (`:157-170`), de la même couleur que les autres onglets. Dans le menu, la page ouverte se distingue des autres liens par sa couleur, à 2,25:1 ou 1,22:1 seulement, et par un second signe. Sur un écran large, sa table des matières est dépliée sous son lien, bordée d'un filet à gauche, de la couleur du texte secondaire: 7,53:1 en mode clair, 12,08:1 en mode sombre (`:188-192`). Sur un écran plus étroit, une icône de table des matières suit son nom. Aucun schéma Mermaid n'a de style de couleur. | La relecture de chaque fiche; la feuille de style |
| Des liens explicites | Microsoft; RGAA 6.1 | Le texte d'un lien nomme sa cible: ni adresse brute, ni « ici », ni « plus haut ». Un lien vers un fichier du dépôt hors des fiches mène à sa page sur GitHub. | Le contrôle du HTML construit |
| Des tableaux simples à en-têtes | Microsoft; RGAA 5.6 | Des tableaux Markdown, rendus avec leurs en-têtes de colonne (`th`), annoncés par une phrase ou un titre. | Le contrôle du HTML construit |
| Des citations déclarées | AcceDe Web; RGAA 9.4 | Les mots d'une source, recopiés, forment une citation. En ligne, c'est un `q`, sans guillemets tapés: la feuille de style dessine les guillemets français, avec l'espace intérieure des guillemets tapés (`documentation/stylesheets/extra.css:205-209`). En bloc, comme l'intitulé du référentiel en tête de chaque fiche, c'est un `blockquote`, suivi de sa source. En tête de fiche, ces citations sont réunies dans un encadré titré « Compétences de la certification » (`mkdocs.yml:77-79`, `documentation/stylesheets/extra.css:120-146`). Le titre cité d'une section, d'une page ou d'un document, un mot dont on parle et un libellé d'interface gardent leurs guillemets tapés: ce ne sont pas des citations. | Le HTML construit; la relecture de chaque fiche |
| La langue de la page et ses changements | RGAA 8.3; RGAA 8.7 | `lang="fr"` sur chaque page (`mkdocs.yml:34`); un passage en anglais balisé `<span lang="en">`. Le pied de page du thème, en anglais, est retiré (`mkdocs.yml:94-96`). | Le contrôle du HTML construit |
| Aucune requête hors du site | (règle de K-B) | Le plugin `privacy` télécharge à la construction ce que le thème irait chercher ailleurs, Mermaid compris, et le sert avec le site (`mkdocs.yml:74-75`), sauf dans deux cas (« Limites »). | Le contrôle du HTML construit |

### Les contrastes du thème

Les rapports de contraste suivants sont calculés selon la formule des WCAG 2.1, le 2026-11-18, pour le mode clair et
pour le mode sombre. Ils portent sur les couleurs de `documentation/stylesheets/extra.css:8-62` et, pour les blocs de
code et les schémas, sur celles de la feuille de style construite de Material 9.8.1. Une couleur transparente du
thème est d'abord posée sur son fond, et c'est la couleur obtenue qui est mesurée. Ces couleurs composées sont
calculées, non lues à l'écran. En mode clair, Chrome dessine `#00000012` sur `#F4F5F2` en `#E2E3E0`, et non en
`#E3E4E1`: les rapports ainsi lus perdent au plus 0,07, sans passer sous le seuil. Le mode sombre n'a pas été lu à
l'écran. Le seuil du RGAA 3.2 est de 4,5:1 pour un texte de taille normale. Toutes les paires le passent; la plus
basse donne 4,85:1. Un aperçu local n'affiche pas les schémas Mermaid tant que le site n'est pas publié
(« Limites »): leurs paires sont calculées, non vues.

La charte n'a pas de mode sombre. Le mode sombre prend ses couleurs là où elles existent: l'encre `#1C1E21` pour le
fond, le gris lin `#F4F5F2` pour le texte, la pierre `#DADCD6` pour le texte secondaire, le « canard givré » `#CFE3E6`
pour les liens, la sarcelle foncée `#0A434C` pour le fond du code en ligne, le blanc du texte de l'en-tête pour un
lien sous le pointeur. Deux sortes de couleurs sont hors charte: `#121416`, tiré de sa teinte, pour l'en-tête, les
blocs de code et le pied de page; les couleurs du code coloré du mode sombre de Material. Le voile d'un titre du menu et d'une boîte d'un
schéma y est de 8 %, et non des 12 % de Material: à 12 %, une boîte au troisième niveau d'un schéma tomberait à
3,62:1.

| Texte | Mode clair | Rapport | Mode sombre | Rapport |
|---|---|---|---|---|
| Le texte d'une fiche, d'un tableau, du menu; le titre d'un résultat de recherche | `#1C1E21` sur `#F4F5F2` | 15,27:1 | `#F4F5F2` sur `#1C1E21` | 15,27:1 |
| Une ligne de tableau sous le pointeur | `#1C1E21` sur `#EBECE9` | 14,09:1 | `#F4F5F2` sur `#242628` | 13,88:1 |
| Un lien dans une ligne de tableau sous le pointeur | `#0F5E6B` sur `#EBECE9` | 6,25:1 | `#CFE3E6` sur `#242628` | 11,41:1 |
| Ce lien, lui-même sous le pointeur ou le focus | `#0A434C` sur `#EBECE9` | 9,22:1 | `#FFFFFF` sur `#242628` | 15,19:1 |
| Un texte secondaire: le titre de niveau 1, un bloc de citation, le titre d'une partie dans le menu d'un écran large, le titre « Table des matières » du menu entre 60em et 76,25em, l'extrait d'un résultat de recherche, l'indication du champ de recherche ouvert | `#4A4F57` sur `#F4F5F2` | 7,53:1 | `#DADCD6` sur `#1C1E21` | 12,08:1 |
| Le titre d'une partie dans le menu d'un écran étroit, le titre « Table des matières » de ce menu sous 60em, l'en-tête des résultats de recherche | `#4A4F57` sur `#E3E4E1` | 6,46:1 | `#DADCD6` sur `#2D2F31` | 9,72:1 |
| Un lien; le titre de l'encadré des compétences; la page ouverte dans le menu; la partie ouverte dans le menu d'un écran étroit; un lien du menu sous le pointeur ou le focus; un mot cherché, souligné dans un résultat de recherche; le lien des autres résultats d'une même page | `#0F5E6B` sur `#F4F5F2` | 6,77:1 | `#CFE3E6` sur `#1C1E21` | 12,56:1 |
| Un lien d'une fiche sous le pointeur ou le focus | `#0A434C` sur `#F4F5F2` | 9,99:1 | `#FFFFFF` sur `#1C1E21` | 16,71:1 |
| Un résultat de recherche sous le pointeur ou le focus: son titre | `#1C1E21` sur `#DCE3E1` | 12,82:1 | `#F4F5F2` sur `#2E3235` | 11,82:1 |
| Un résultat de recherche sous le pointeur ou le focus: son extrait | `#4A4F57` sur `#DCE3E1` | 6,33:1 | `#DADCD6` sur `#2E3235` | 9,35:1 |
| Un résultat de recherche sous le pointeur ou le focus: un mot cherché; le lien des autres résultats d'une même page sous le pointeur ou le focus | `#0F5E6B` sur `#DCE3E1` | 5,69:1 | `#CFE3E6` sur `#2E3235` | 9,72:1 |
| Le texte de l'en-tête, des onglets et du titre du menu d'un écran étroit | `#FFFFFF` sur `#1C1E21` | 16,71:1 | `#FFFFFF` sur `#121416` | 18,46:1 |
| L'indication du champ de recherche, dans l'en-tête | `#CFE3E6` sur `#151618` | 13,61:1 | `#CFE3E6` sur `#0D0F10` | 14,44:1 |
| L'indication du champ de recherche, dans l'en-tête, sous le pointeur | `#CFE3E6` sur `#38393C` | 8,68:1 | `#CFE3E6` sur `#2F3132` | 9,83:1 |
| Le lien d'évitement | `#F4F5F2` sur `#1C1E21` | 15,27:1 | `#1C1E21` sur `#F4F5F2` | 15,27:1 |
| Un lien du pied de page | `#0F5E6B` sur `#FFFFFF` | 7,41:1 | `#CFE3E6` sur `#121416` | 13,88:1 |
| Un lien du pied de page sous le pointeur ou le focus | `#0A434C` sur `#FFFFFF` | 10,94:1 | `#FFFFFF` sur `#121416` | 18,46:1 |
| Le code en ligne | `#36464E` sur `#E6F0F1` | 8,45:1 | `#DADCD6` sur `#0A434C` | 7,91:1 |
| Le code dans un lien d'une fiche | `#0F5E6B` sur `#E6F0F1` | 6,39:1 | `#CFE3E6` sur `#0A434C` | 8,22:1 |
| Le code dans un lien d'une fiche sous le pointeur ou le focus | `#0A434C` sur `#DCE3E1` | 8,39:1 | `#FFFFFF` sur `#2E3235` | 12,93:1 |
| Un bloc de code | `#36464E` sur `#FFFFFF` | 9,80:1 | `#DADCD6` sur `#121416` | 13,35:1 |
| Un bloc de code coloré: commentaire, variable, opérateur, ponctuation | `#4A4F57` sur `#FFFFFF` | 8,24:1 | `#DADCD6` sur `#121416` | 13,35:1 |
| Un bloc de code coloré: mot-clé | `#3F6EC6` sur `#FFFFFF` | 4,93:1 | `#6791E0` sur `#121416` | 5,89:1 |
| Un bloc de code coloré: nombre | `#D52A2A` sur `#FFFFFF` | 5,01:1 | `#E6695B` sur `#121416` | 5,75:1 |
| Un bloc de code coloré: commande intégrée | `#6E59D9` sur `#FFFFFF` | 5,13:1 | `#9383E2` sur `#121416` | 5,79:1 |
| Un bloc de code coloré: chaîne | `#1C7D4D` sur `#FFFFFF` | 5,13:1 | `#2FB170` sur `#121416` | 6,72:1 |
| Un bloc de code coloré: caractère échappé | `#DB1457` sur `#FFFFFF` | 4,94:1 | `#F06090` sur `#121416` | 5,96:1 |
| Le libellé d'une flèche d'un schéma (calculé, non vu) | `#36464E` sur `#F4F5F2` | 8,95:1 | `#DADCD6` sur `#1C1E21` | 12,08:1 |
| Le libellé d'une boîte d'un schéma, hors de tout sous-graphe (calculé, non vu) | `#36464E` sur `#DCE3E1` | 7,52:1 | `#DADCD6` sur `#2E3235` | 9,35:1 |
| Le titre d'un sous-graphe d'un schéma, premier niveau (calculé, non vu) | `#36464E` sur `#E3E4E1` | 7,68:1 | `#DADCD6` sur `#2D2F31` | 9,72:1 |
| Le titre d'un sous-graphe d'un schéma, deuxième niveau (calculé, non vu) | `#36464E` sur `#D3D4D1` | 6,58:1 | `#DADCD6` sur `#3D3F40` | 7,66:1 |
| Le titre d'un sous-graphe d'un schéma, troisième niveau (calculé, non vu) | `#36464E` sur `#C4C5C2` | 5,65:1 | `#DADCD6` sur `#4B4D4E` | 6,15:1 |
| Le libellé d'une boîte dans un sous-graphe de premier niveau (calculé, non vu) | `#36464E` sur `#CDD4D2` | 6,51:1 | `#DADCD6` sur `#3E4143` | 7,44:1 |
| Le libellé d'une boîte dans un sous-graphe de deuxième niveau (calculé, non vu) | `#36464E` sur `#BFC5C3` | 5,60:1 | `#DADCD6` sur `#4C5051` | 5,90:1 |
| Le libellé d'une boîte dans un sous-graphe de troisième niveau (calculé, non vu) | `#36464E` sur `#B1B8B6` | 4,85:1 | `#DADCD6` sur `#585C5D` | 4,89:1 |

Le troisième niveau est celui du schéma du déploiement sur Azure, dans
[la fiche de l'architecture](architecture_pour_docu.md).

Hors de l'en-tête, l'anneau de focus prend la couleur de l'accent (`documentation/stylesheets/extra.css:42-43`), y
compris sur la liste des résultats de recherche (`:194-197`). En mode clair, c'est la sarcelle `#0F5E6B`, la couleur
de focus de la charte, à 6,77:1 sur `#F4F5F2`. En mode sombre, c'est le canard givré `#CFE3E6`, à 12,56:1 sur
`#1C1E21`. Les deux passent le seuil de 3:1 du RGAA 3.3 pour un composant d'interface. Sur l'en-tête, les onglets, le
lien d'évitement, le logo du menu d'un écran étroit et le bouton du mode, l'anneau est blanc, `#FFFFFF`: 16,71:1 sur
`#1C1E21` en mode clair, 18,46:1 sur `#121416` en mode sombre, là où la sarcelle ne donnerait que 2,25:1
(`:172-186`). Le contour d'un bloc de code, `#DADCD6` sur blanc ou `#4A4F57` sur `#121416`, est un décor: il ne porte
aucune information.

## La vérification selon la notice d'AcceDe Web

Les douze pages du site ont été vérifiées selon chaque règle de la notice d'accessibilité éditoriale d'AcceDe Web,
sur le HTML construit par `mkdocs build --strict` et à la relecture: dix le 2026-11-18, la fiche des maquettes le
2026-11-19, la fiche du monitorage le 2026-11-21, après sa mise en forme (#669). Le tableau suivant donne chaque
règle de la notice, son résultat sur les douze pages, et comment il a été vérifié.

| Règle de la notice | Résultat | Vérifiée par |
|---|---|---|
| 1. Ne pas utiliser les sauts de lignes multiples | Tenue: aucune balise `br` hors des schémas Mermaid, aucun paragraphe vide. | Le HTML construit |
| 2. Utiliser correctement la hiérarchie des titres | Tenue: un titre de niveau 1 par page, puis aucun saut de niveau. | Le HTML construit |
| 3.1. Rédiger des intitulés de liens explicites | Tenue (règle « Des liens explicites » des [règles appliquées aux fiches](#les-regles-appliquees-aux-fiches)). | Le HTML construit |
| 3.2. Savoir utiliser les titres de liens en dernier recours | Tenue dans le texte des fiches: aucun lien n'y a d'attribut `title`. Les deux liens du logo du thème, dans l'en-tête et dans le menu, en portent un, le nom du site (« Limites »). | Le HTML construit |
| 4.1 à 4.3. Images décoratives, informatives, images-liens | Tenue: deux images informatives, les planches de la fiche des maquettes, chacune avec son texte de remplacement; aucune image décorative ni image-lien. | Le HTML construit |
| 4.4. Images informatives complexes: un court texte de remplacement et une description détaillée | Tenue pour les neuf schémas des fiches (un dans le service d'IA, quatre dans l'architecture, un dans l'API IA, deux dans l'import et la base, un dans les maquettes): chacun a un titre et une description courts (`accTitle` et `accDescr`, que Mermaid rend en `title` et `desc` du dessin), et le texte qui le suit pour description détaillée. Les neuf schémas ont été rendus le 2026-11-19 par le Mermaid du site, dans Chrome sans interface: leur `title` et leur `desc` y sont. Tenue pour les deux planches de la fiche des maquettes: chacune a un texte de remplacement court, qui nomme la section de sa description détaillée. | La relecture; le rendu des neuf schémas dans Chrome sans interface |
| 5. Utiliser correctement les listes à puces et listes numérotées | Tenue: des listes Markdown, en retrait de quatre espaces, aucune liste tapée à la main. | Le HTML construit |
| 6.1. Déclarer les citations en ligne et les blocs de citations | Tenue: une citation en ligne est un `q`, un bloc de citation un `blockquote` (règle « Des citations déclarées » des [règles appliquées aux fiches](#les-regles-appliquees-aux-fiches)). Chaque paire de guillemets tapés a été triée: celles qui restent entourent un titre, un mot dont on parle ou un libellé. | Le HTML construit; la relecture |
| 6.2. Déclarer les changements de langue | Tenue: chaque passage en anglais du texte des fiches est balisé `<span lang="en">`; le pied de page anglais du thème est retiré. | Le HTML construit |
| 6.3. Ne pas faire référence à un élément en se basant uniquement sur sa couleur, sa taille, sa forme ou sa position | Tenue: un renvoi nomme l'élément et suit l'ordre de lecture (« le tableau suivant donne… »), jamais une place à l'écran. | La relecture; le contrôle des renvois vagues |
| 7.1. Contrastes entre le texte et l'arrière-plan | Tenue ([Les contrastes du thème](#les-contrastes-du-theme)). | Le calcul des rapports de contraste |
| 7.2. Les couleurs ne sont pas le seul moyen de porter une information | Tenue: un lien est souligné. | La relecture; la feuille de style |
| 8.1. Associer une description détaillée aux contenus riches | Tenue: chaque schéma Mermaid et chaque planche a sa description en texte. | La relecture |
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
    (`mkdocs.yml:86-92`). Le workflow `docs.yml` la lance sur chaque demande de fusion
    (PR, <span lang="en">pull request</span>)
    (`.github/workflows/docs.yml:6-9`, `:25`).

2. Le contrôle du HTML construit, lancé sur `site/` pour chaque PR de mise en forme, compte dans chaque page: l'attribut
    `lang`, les titres de niveau 1 et les sauts de niveau, les tableaux sans `th`, les liens dont le texte est une
    adresse, « ici » ou « plus haut », et les ressources chargées hors du site. Il n'est pas dans le dépôt: son résultat
    est écrit dans la PR.

3. Relire chaque fiche: les vraies listes, la phrase avant chaque schéma et chaque tableau, l'absence de couleur seule,
    et chaque paire de guillemets tapés, qui n'entoure pas une citation.

4. Passer WAVE, l'outil de contrôle de WebAIM, sur trois pages du site servi en local, et les parcourir à la touche Tab,
    sur un écran large et sur un écran étroit. Le 2026-11-18, sur le thème de #652, WAVE relevait 15 erreurs de
    libellé, sur les cases cachées du thème et sur les `label` des deux radios du mode (« Limites »), et un contraste
    très faible, sur l'en-tête caché des résultats de recherche: un fond transparent, que WAVE ne compose pas avec la
    page. Cet en-tête a depuis un fond opaque, le même à l'œil (`documentation/stylesheets/extra.css:199-203`). La
    liste des résultats de recherche recevait le focus sans rien montrer: la recherche de Material se ferme sur la
    touche Tab avant que le focus ne bouge, et la liste repliée n'a plus de hauteur. Elle n'est plus un arrêt de la
    touche Tab (`documentation/javascripts/search-list.js`); les résultats s'atteignent par les flèches, depuis le
    champ de recherche. Sur un écran large, le parcours à la touche Tab suit l'ordre de la page, le bouton du mode
    compris. Le 2026-11-19, Sabine a passé WAVE sur la fiche du monitorage en mode sombre, et l'a parcourue à la
    touche Tab. WAVE relevait les mêmes 15 erreurs de libellé, 7 libellés vides et 8 multiples, et un seul contraste
    très faible, sur le lien d'évitement du thème, « Aller au contenu ». Ce lien reste transparent tant qu'il n'a pas
    le focus (`opacity: 0`), et WAVE mesure son texte transparent sur la page. Il paraît au premier appui sur la
    touche Tab, en `#1C1E21` sur `#F4F5F2`, soit 15,27:1 ([Les contrastes du thème](#les-contrastes-du-theme)). Le
    critère 1.4.3 des WCAG 2.1 n'impose aucun contraste à un texte que personne ne voit, et s'applique au texte qui
    paraît au focus: le lien passe le seuil de 4,5:1 dès qu'il paraît. Le parcours à la touche Tab suivait l'ordre de
    la page, le menu de gauche titre par titre. Le thème donne le focus à un bloc de code qui défile, pour le faire
    défiler au clavier (WCAG 2.1, critère 2.1.1).

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
- **WAVE relève des libellés vides ou multiples sur les cases cachées du thème et sur les radios du mode.** Material ouvre son menu, sa
    recherche et la table des matières d'une page par des cases à cocher cachées, liées à des `label` sans texte ou à
    plusieurs `label`. Sur la fiche des tests, il y en avait 5 vides et 3 multiples avant le thème de #652, et 7 et 8
    depuis: le menu numéroté ajoute une case par rubrique, et le bouton du mode deux radios, qui ont un nom. Les
    cases sont en `display: none`: elles ne sont ni dans
    l'ordre de la touche Tab ni dans l'arbre d'accessibilité de Chrome (relevé le 2026-11-18). Seuls y sont le
    champ de recherche et les deux radios du mode, chacun avec son nom (« Rechercher », « Passer au mode sombre »,
    « Passer au mode clair »).
- **Un navigateur sans `light-dark()` garde les couleurs de Material.** Avant Chrome 123, Firefox 120 et Safari 17.5
    (mai 2024), le bloc des couleurs de K-B est sauté (`documentation/stylesheets/extra.css:8-11`): le site prend les
    couleurs par défaut du thème, qui ne sont pas mesurées ici. Les règles de K-B hors de ce bloc ont alors des valeurs
    de repli, celles du thème.
- **Le bouton du mode clair ou sombre est un bouton radio du thème.** À chaque chargement d'une page en mode sombre,
    la touche Tab atteint le radio nommé « Passer au mode sombre », sur une page déjà sombre: un lecteur d'écran
    annonce l'inverse de ce qui se passe. Entrée change toujours le mode. Espace et les flèches cochent un radio, dont
    le nom dit l'inverse du mode qu'il pose. À la première touche sur une page sombre, Espace la passe en clair et les
    flèches la laissent sombre; ensuite, Espace ne change rien et les flèches changent le mode (relevé le 2026-11-18
    dans Chrome sans interface). Un vrai bouton est porté par #653.
- **Les deux liens du logo du thème portent un attribut `title`**, le nom du site, sur chaque page, dans l'en-tête et
    dans le menu (règle 3.2 d'AcceDe Web).
    Il vient du thème, hors du texte des fiches.
- **Deux chargements hors du site restent possibles.** Le script du thème demande
    `resize-observer-polyfill` à unpkg sur un navigateur qui n'a pas `ResizeObserver`, ce que le plugin `privacy` ne
    rapatrie pas. Mermaid est appelé par l'adresse du site publié, `site_url` (`mkdocs.yml:5`): tant que Pages n'est
    pas activé, un aperçu local de `site/` n'affiche pas les schémas. Sur les cinq fiches qui en ont, l'erreur de ce
    chargement arrête aussi, dans l'aperçu seulement, le bouton du mode et la recherche.
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

Lue le 2026-11-19:

- W3C, <span lang="en">« Understanding SC 1.4.3: Contrast (Minimum) »</span>,
    [page du W3C](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum), après une recherche web du même jour:
    un texte que personne ne voit n'a pas d'exigence de contraste; le texte qui paraît au focus en a une.
