# L'accessibilité de la documentation de K-B

« La documentation est communiquée dans un format qui respecte les recommandations d'accessibilité (par exemple
celles de l'association Valentin Haüy ou de Microsoft). » — C8.5, C9.11, C11.9, C12.7, C13.8, C17.12, C18.7, C19.7,
C20.7

Cette fiche dit sous quel format la documentation de K-B est communiquée, quelles recommandations d'accessibilité
elle suit, comment chaque règle est tenue dans les fiches, et ce qui n'est pas vérifié. Les renvois `fichier:ligne`
visent le dépôt au 2026-11-14: `mkdocs.yml`, `documentation/stylesheets/extra.css` et `.github/workflows/docs.yml`
arrivent avec cette fiche.

## Le format

Les fiches sont écrites en Markdown dans `documentation/`. MkDocs 1.6.1, avec le thème Material for MkDocs 9.8.1, en
fait un site HTML statique: une page par fiche, une navigation commune, une page d'accueil
([La documentation de K-B](index.md)) et un champ de recherche (`mkdocs.yml:3-19`, `:31-32`). Le site se publie sur
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
    AcceDe Web en version 4.1.2). Elle s'adresse aux « contributrices et contributeurs éditoriaux » d'un outil de
    publication: ici, l'outil est MkDocs, et ses règles portent sur le texte des fiches. Elle dit d'elle-même: « Cette
    version en ligne couvre actuellement les WCAG 2.2 et le RGAA 4.1.2 »; sa section 9 dit que ses règles
    supplémentaires sont « nécessaire[s] pour garantir la conformité RGAA 4.1 et WCAG 2.1 ». Les fiches mises en forme
    sont vérifiées selon elle, règle par règle
    ([La vérification selon la notice d'AcceDe Web](#la-verification-selon-la-notice-daccede-web)).

## Les règles appliquées aux fiches

Le tableau suivant donne, pour chaque règle, sa source, comment elle est tenue dans les fiches mises en forme
(`index.md`, cette fiche, le service d'IA et l'intégration continue), et comment elle se vérifie. Les autres fiches
suivent (« Limites »).

| Règle | Source | Comment elle est tenue | Vérifiée par |
|---|---|---|---|
| Des titres hiérarchisés | AVH; Microsoft; RGAA 9.1 | Un seul titre de niveau 1 par fiche, puis `##` à `####` sans saut de niveau. Un paragraphe en gras n'est pas un titre. | Le contrôle du HTML construit |
| De vraies listes | AVH; RGAA 9.3 | Les listes Markdown, rendues en `ul` et `ol`. Chaque niveau est en retrait de quatre espaces: Python-Markdown, qui construit les pages, ne rattache à un point de liste que ce qui est en retrait de quatre espaces. | Le HTML construit |
| Un sommaire | AVH | La « Table des matières » de chaque page, tirée de ses titres par le thème, et la navigation du site. | Le contrôle du HTML construit |
| Une alternative à chaque élément non textuel | AVH; Microsoft | Les fiches n'ont aucune image. Chaque schéma Mermaid est annoncé par une phrase qui nomme le texte qui le décrit. | La relecture de chaque fiche |
| Des polices lisibles | AVH | Les polices du système de la lectrice, sans Google Fonts (`mkdocs.yml:24-25`). | La configuration |
| Un contraste suffisant | AVH; RGAA 3.2 | Les couleurs du thème mesurées ([Les contrastes du thème](#les-contrastes-du-theme)); celle d'un lien survolé, foncée (`documentation/stylesheets/extra.css:3-5`). | Le calcul des rapports de contraste |
| Pas la couleur seule | AVH; Microsoft; RGAA 3.1; RGAA 10.6 | Aucune fiche ne porte une information par la couleur. Un lien est souligné (`documentation/stylesheets/extra.css:7-10`): sa couleur seule, `#4051b5` contre le texte, ne donne que 2,35:1, sous le seuil de 3:1. Aucun schéma Mermaid n'a de style de couleur. | La relecture de chaque fiche; la feuille de style |
| Des liens explicites | Microsoft; RGAA 6.1 | Le texte d'un lien nomme sa cible: ni adresse brute, ni « ici », ni « plus haut ». Un lien vers un fichier du dépôt hors des fiches mène à sa page sur GitHub. | Le contrôle du HTML construit |
| Des tableaux simples à en-têtes | Microsoft; RGAA 5.6 | Des tableaux Markdown, rendus avec leurs en-têtes de colonne (`th`), annoncés par une phrase ou un titre. | Le contrôle du HTML construit |
| La langue de la page et ses changements | RGAA 8.3; RGAA 8.7 | `lang="fr"` sur chaque page (`mkdocs.yml:23`); un passage en anglais balisé `<span lang="en">`. Le pied de page du thème, en anglais, est retiré (`mkdocs.yml:51-53`). | Le contrôle du HTML construit |
| Aucune requête hors du site | (règle de K-B) | Le plugin `privacy` télécharge à la construction ce que le thème irait chercher ailleurs, Mermaid compris, et le sert avec le site (`mkdocs.yml:33-34`). | Le contrôle du HTML construit |

### Les contrastes du thème

Les rapports de contraste suivants sont calculés selon la formule des WCAG 2.1, sur les couleurs de la feuille de
style construite de Material 9.8.1, le 2026-11-14. Le seuil du RGAA 3.2 est de 4,5:1 pour un texte de taille normale.

| Texte | Couleurs | Rapport |
|---|---|---|
| Le texte d'une fiche | `#000000de` sur blanc | 16,10:1 |
| Un texte secondaire du thème | `#0000008a` sur blanc | 4,61:1 |
| Un lien | `#4051b5` sur blanc | 6,86:1 |
| Un lien survolé, couleur du thème | `#526cfe` sur blanc | 4,26:1, sous le seuil |
| Un lien survolé, couleur de K-B | `#303f9f` sur blanc | 8,98:1 |
| Le texte de l'en-tête | blanc sur `#4051b5` | 6,86:1 |
| Le code | `#36464e` sur `#f5f5f5` | 8,99:1 |

## La vérification selon la notice d'AcceDe Web

Le 2026-11-18, les quatre fiches mises en forme (`index.md`, cette fiche, `service_ia_pour_docu.md` et
`integration_continue_pour_docu.md`) ont été vérifiées selon chaque règle de la notice d'accessibilité éditoriale
d'AcceDe Web, sur le HTML construit par `mkdocs build --strict` et à la relecture. Le tableau suivant donne chaque
règle de la notice, son résultat, et comment il a été vérifié.

| Règle de la notice | Résultat | Vérifiée par |
|---|---|---|
| 1. Ne pas utiliser les sauts de lignes multiples | Tenue: aucune balise `br` hors des schémas Mermaid, aucun paragraphe vide. | Le HTML construit |
| 2. Utiliser correctement la hiérarchie des titres | Tenue: un titre de niveau 1 par page, puis aucun saut de niveau. | Le HTML construit |
| 3.1. Rédiger des intitulés de liens explicites | Tenue (règle « Des liens explicites » des [règles appliquées aux fiches](#les-regles-appliquees-aux-fiches)). | Le HTML construit |
| 3.2. Savoir utiliser les titres de liens en dernier recours | Tenue dans le texte des fiches: aucun lien n'y a d'attribut `title`. Le lien du logo du thème en porte un, le nom du site (« Limites »). | Le HTML construit |
| 4.1 à 4.3. Images décoratives, informatives, images-liens | Sans objet: aucune image. | Le HTML construit |
| 4.4. Images informatives complexes: un court texte de remplacement et une description détaillée | Tenue pour le seul schéma des quatre fiches, celui du service d'IA: un titre et une description courts (`accTitle` et `accDescr`, que Mermaid rend en `title` et `desc` du dessin), et la liste qui le suit pour description détaillée. Le rendu dans un navigateur n'est pas vérifié. | La relecture |
| 5. Utiliser correctement les listes à puces et listes numérotées | Tenue: des listes Markdown, en retrait de quatre espaces, aucune liste tapée à la main. | Le HTML construit |
| 6.1. Déclarer les citations en ligne et les blocs de citations | **Non tenue**: les citations sont entre guillemets, sans `q` ni `blockquote` (RGAA 9.4). Raison: séparer, guillemet par guillemet, les citations des titres de page ou de section cités demande de relire chaque fiche. Parade: la correction dans la demande de fusion (PR) suivante de la mise en forme, pour toutes les fiches. | Le HTML construit |
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
courants (API, HTML, URL, UTC, SHA) ne le sont pas.

## Vérifier

1. Construire le site en mode strict:

    ```sh
    uv run --locked --only-group docs mkdocs build --strict
    ```

    Un lien vers un fichier absent, une ancre absente ou une fiche oubliée dans la navigation arrête la construction
    (`mkdocs.yml:43-49`). Le workflow `docs.yml` la lance sur chaque PR
    (`.github/workflows/docs.yml:6-9`, `:25`).

2. Le contrôle du HTML construit, lancé sur `site/` pour chaque PR de mise en forme, compte dans chaque page: l'attribut
    `lang`, les titres de niveau 1 et les sauts de niveau, les tableaux sans `th`, les liens dont le texte est une
    adresse, « ici » ou « plus haut », et les ressources chargées hors du site. Il n'est pas dans le dépôt: son résultat
    est écrit dans la PR.

3. Relire chaque fiche: les vraies listes, la phrase avant chaque schéma et chaque tableau, l'absence de couleur seule.

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
- **Les citations ne sont pas déclarées** (notice d'AcceDe Web, règle 6.1; RGAA 9.4): voir
    [La vérification selon la notice d'AcceDe Web](#la-verification-selon-la-notice-daccede-web). Parade: la correction
    dans la PR suivante de la mise en forme, pour toutes les fiches.
- **Les fiches ne sont pas encore toutes mises en forme.** Cette fiche et la PR qui l'introduit couvrent `index.md`,
    le service d'IA et l'intégration continue. Les autres fiches gardent, le 2026-11-18, des listes en retrait de deux
    ou trois espaces, mal rendues, des schémas sans phrase d'annonce, et, pour le monitorage, un second titre de
    niveau 1; la PR suivante de la mise en forme les corrige.
- **Le lien du logo du thème porte un attribut `title`**, le nom du site, sur chaque page (règle 3.2 d'AcceDe Web).
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

Lue le 2026-11-18:

- Atalan, AcceDe Web, « Notice d'accessibilité éditoriale »,
    [version en ligne](https://www.accede-web.com/notices/editoriale/), ses neuf sections et ses bonnes pratiques
    (pages de la section `notices/editoriale-modele/`). Context7 ne la couvre pas: elle a été lue à la source, après
    une recherche web du même jour.
