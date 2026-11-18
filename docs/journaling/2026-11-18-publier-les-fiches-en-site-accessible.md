# Publier les fiches en site accessible, et passer la fiche du service d'IA à gpt-6.1-sol

- Date : 2026-11-18 (travail commencé le 2026-11-14)
- Branche : `docs/mkdocs-accessible-sheets`
- Issues : #167 (part « documentation »), #623 (en partie)
- Fichiers principaux : `mkdocs.yml`, `.github/workflows/docs.yml`, `documentation/accessibilite_pour_docu.md`,
  `documentation/service_ia_pour_docu.md`, `documentation/integration_continue_pour_docu.md`, `README.md` (section CI)
- Série : [la fiche du service d'IA](2026-11-10-ecrire-la-fiche-du-service-d-ia.md),
  [la fiche de l'intégration continue](2026-11-10-ecrire-la-fiche-de-l-integration-continue.md)

## Le pourquoi

Le référentiel demande, pour neuf critères (C8.5 à C20.7), une documentation « communiquée dans un format qui
respecte les recommandations d'accessibilité ». Des fichiers Markdown lus sur GitHub ne le prouvent pas : rien n'y
dit la langue, ni ne contrôle les titres, les liens ou les tableaux. Les fiches de `documentation/` deviennent donc un
site statique, construit à chaque PR et publié à la main, avec une fiche qui dit quelles recommandations sont
suivies et comment chacune se vérifie.

Dans la même PR, la fiche du service d'IA passe de `gpt-6-luna` à `gpt-6.1-sol`, le modèle que préconise le banc
des modèles du 2026-11-16 : la fiche doit décrire le service que K-B appelle.

## Le comment

### Un site sans requête hors de lui-même

```yaml
theme:
  name: material
  language: fr
  # No Google Fonts: the fonts of the system, no request out of the site.
  font: false
```

`mkdocs.yml:21-25`. `language: fr` donne `lang="fr"` à chaque page (RGAA 8.3). `font: false` retire Google Fonts. Le
plugin `privacy` (`mkdocs.yml:31-34`) télécharge à la construction ce que le thème irait chercher ailleurs, Mermaid
compris, et le sert avec le site : une lectrice ne charge rien d'un tiers, sauf dans deux cas écrits en limites de
la fiche (un correctif pour un vieux navigateur, et Mermaid tant que Pages n'est pas activé).

### La construction stricte, et l'empreinte de Mermaid

```yaml
      - run: uv run --locked --only-group docs mkdocs build --strict
      # The privacy plugin downloads Mermaid from unpkg, in its moving version 11 (mermaid@11): the build
      # fails unless the file is the one of the npm package of mermaid 11.17.2, checked on 2026-11-14 against
      # the integrity npm publishes for it (documentation/accessibilite_pour_docu.md, "Limites").
```

`.github/workflows/docs.yml:25-28`. `--strict` fait de chaque avertissement une erreur ; `mkdocs.yml:43-49` change en
avertissement une fiche hors de la navigation, une ancre absente et un lien non reconnu. Un lien cassé arrête donc
la PR. La ligne suivante (`:29`) compare par `sha256sum --check` le fichier de Mermaid téléchargé à celui de
Mermaid 11.17.2 : `mermaid@11` est une version qui bouge, l'empreinte la fige.

### La publication, à la main et depuis `main` seulement

```yaml
  deploy:
    # Launched by hand, and from main only: a dispatch can name any branch.
    if: github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'
    needs: build
```

`.github/workflows/docs.yml:35-38`. Seul ce job a `pages: write` et `id-token: write` (`:41-43`) ; le reste du
workflow ne lit que le dépôt (`:11-12`). Pages n'est pas activé : un site publié depuis un dépôt privé est public,
la publication attend donc la mise en public du dépôt (`documentation/accessibilite_pour_docu.md`, « Publier »).

### L'audit de toutes les dépendances

```yaml
      # Audit the versions pinned by uv.lock, with their hashes, against known vulnerabilities:
      # every group, docs included, which uv export leaves out by default.
      - run: uv export --frozen --no-emit-project --all-groups --format requirements-txt -o requirements-audit.txt
```

`.github/workflows/ci.yml:23-25`. MkDocs et Material vivent dans le groupe `docs` (`pyproject.toml:45-47`), que ni
les tests ni l'image n'installent. Sans `--all-groups`, `uv export` les laisse de côté : `audit` ne les verrait pas.

### `Docs` compte pour la livraison

`deploy.yml:51-67` refuse un tag tant qu'une exécution d'un workflow du dépôt sur son commit n'est pas finie et
verte. `Docs` ne tourne sur un commit de `main` que lancé à la main ; s'il y échoue, le tag de ce commit est refusé.
La fiche de l'intégration continue l'écrit, avec la parade : relancer `Docs`, ou livrer un commit suivant.

### La fiche du service d'IA, sur `gpt-6.1-sol`

Les déploiements, la ressource et les rôles de l'opératrice viennent de lectures `az` du 2026-11-18 ; le type du
déploiement, d'une capture du portail du 2026-11-17 ; que le déploiement réponde, de l'essai de bout en bout du
même jour. Une lecture du 2026-11-09, dont la ressource n'est pas établie, n'est citée que pour un déploiement
qu'elle listait et que celle du 2026-11-18 ne liste plus. Le schéma
porte un titre et une description courts pour un lecteur d'écran :

```text
    accTitle: Qui appelle le service d'IA et ce dont l'appel dépend
```

`documentation/service_ia_pour_docu.md:302`. Mermaid les rend en `title` et `desc` du dessin, liés par
`aria-labelledby` et `aria-describedby` (documentation de Mermaid 11.17.2, lue par Context7 le 2026-11-18).

## Choix faits et options écartées

- **MkDocs 1.6.1 et Material 9.8.1** (décision de Sabine du 2026-11-12) : l'outil nommé pour le format. Écartés :
  Zensical (en bêta), Sphinx avec MyST (les schémas Mermaid à reprendre), Jekyll (une seconde pile, Ruby).
- **Une empreinte** plutôt qu'une version exacte de Mermaid par `extra_javascript` : celle-ci chargerait 3,5 Mo sur
  chaque page, au lieu des seules pages à schéma.
- **`actions/configure-pages` retiré** : ses sorties ne servent qu'à l'adresse, fixée par `site_url`.
- **Des listes en retrait de quatre espaces** : Python-Markdown, qui construit les pages, ne rattache à un point de
  liste que ce qui est en retrait de quatre ; à deux ou trois espaces, les sous-listes s'aplatissaient et une liste
  numérotée se coupait en listes d'un seul point (constat de la relecture neuve). Écartée : l'extension
  `mdx_truly_sane_lists`, une dépendance de plus. Les autres fiches sont corrigées dans la PR B.
- **Des liens soulignés** (`documentation/stylesheets/extra.css:7-10`) : la couleur seule d'un lien donne 2,35:1
  contre le texte, sous les 3:1 du RGAA 10.6. **Le pied de page du thème retiré** (`mkdocs.yml:51-53`) : il était
  en anglais, et son lien ouvrait une nouvelle fenêtre.
- **L'accent du thème à `#303f9f`** (`documentation/stylesheets/extra.css:3-5`) : celui de Material, `#526cfe`, donne
  4,26:1 sur blanc, sous le seuil de 4,5:1 du RGAA 3.2.
- **`deploy.yml` inchangé** (tranché par time-knight) : en exclure `docs.yml` affaiblirait un contrôle de sécurité de
  la livraison.
- **La règle 6.1 d'AcceDe Web (citations) reportée à la PR B**, pour toutes les fiches (tranché par time-knight) :
  séparer les citations des titres cités demande de relire chaque fiche. Elle est écrite « non tenue ».
- **La ressource Foundry n'est pas nommée** : son nom est le sous-domaine du point de terminaison. Les captures et le
  relevé de l'essai restent hors du dépôt : ils montrent des noms que le dépôt public ne doit pas porter.
- **La section CI du README mise à jour** dans cette PR (accord de time-knight) : la PR ajoute `docs.yml`, et une
  correction se reporte partout (`.claude/rules/code.md`, « Avant de déclarer un travail fini », point 7).
- **Rebase sans push forcé** : la branche n'avait jamais été poussée.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run --locked --only-group docs mkdocs build --strict` : « Documentation built », aucun avertissement | aucun lien, aucune ancre cassés ; chaque fiche est dans la navigation |
| le contrôle du HTML construit : 0 constat sur `index`, `service_ia` et `integration_continue` ; sur `accessibilite`, seulement la règle qu'elle cite elle-même | un titre de niveau 1, aucun saut de niveau, des tableaux à `th`, aucun lien vague, aucune ressource externe |
| dans le texte des quatre fiches (`article`) : 0 `br` hors Mermaid, 0 attribut `title` ou `target` sur un lien, 0 `q` ni `blockquote` ; sur toute la page, 0 `target`, et un `title` sur les deux liens du logo du thème | les règles 1, 3.2 et la bonne pratique des fenêtres d'AcceDe Web sont tenues dans le texte ; la 6.1 ne l'est pas |
| `uv export --frozen --no-emit-project` sans `--all-groups` : ni `mkdocs` ni `mkdocs-material` ; avec : les deux | l'option est nécessaire pour qu'`audit` voie le groupe `docs` |

## Ce que tu dois pouvoir défendre

1. **Pourquoi un site plutôt que les fichiers Markdown sur GitHub ?** Le site déclare sa langue, a un sommaire par
   page et une navigation, et sa construction stricte refuse un lien cassé (`mkdocs.yml:43-49`).
2. **Que se passe-t-il si unpkg sert un autre fichier de Mermaid ?** `build` échoue sur l'empreinte
   (`docs.yml:29`) : rien n'est publié. La parade est écrite dans la fiche de l'intégration continue.
3. **Pourquoi le site n'est-il pas en ligne ?** Un site Pages publié depuis un dépôt privé est public : le publier
   avant la mise en public publierait toutes les fiches.
4. **Comment savez-vous que `gpt-6.1-sol` est déployé, et avec quels réglages ?** La lecture `az` des déploiements
   du 2026-11-18 le liste, avec sa capacité, sa version, sa mise à jour figée et son filtre ; son type vient de la
   capture du formulaire, car `az` en tableau ne le montre pas. L'essai du 2026-11-17 l'a appelé : 18 requêtes, dont
   17 `ok`.
5. **Pourquoi une règle d'AcceDe Web n'est-elle pas tenue ?** C'est un choix daté et écrit : la 6.1 demande un tri
   des citations dans toutes les fiches, prévu dans la PR B.

## Zones non vérifiées

- Le rendu au lecteur d'écran (parade : un essai VoiceOver par Sabine sur une fiche).
- Le rendu de `accTitle` et `accDescr` dans un navigateur : la syntaxe suit la documentation de Mermaid, le dessin
  n'a pas été inspecté.
- Qu'une relance réussie de `Docs` fasse passer le contrôle de `deploy.yml` : déduit de la requête de
  `deploy.yml:61-62`, non essayé.
- La publication sur Pages : jamais lancée.
- Le type des déploiements et le stockage de la surveillance des abus, non relus par `az` ; la cause de l'incident
  TLS (#629).

## Ce qui reste

- La PR B : la forme des fiches restantes (tests, livraison continue, import et base, API IA, architecture,
  installation), la règle 6.1 dans toutes les fiches, et les renvois de l'API IA et de l'architecture que #628 a
  décalés.
- La forme de la fiche du monitorage, après les PR de #620 et #621 et celle du passage de K-B à `gpt-6.1-sol`.
- L'activation de Pages, après la mise en public du dépôt.
