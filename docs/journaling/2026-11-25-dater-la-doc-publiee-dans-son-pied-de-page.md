# Dater la doc publiée dans son pied de page

- **Date** : 2026-11-25
- **Branche** : `feat/docs-published-version`
- **Issue** : #719 (et #720, ouverte par le tri de la revue)
- **Fichiers** : `.github/workflows/docs.yml`, `mkdocs.yml`, `overrides/partials/copyright.html`,
  `documentation/stylesheets/extra.css`, `documentation/accessibilite.md`, `documentation/integration-continue.md`
- **Série** : suit [l'habillage du site de la doc](2026-11-18-habiller-le-site-de-la-doc-aux-couleurs-du-back-office.md),
  qui a écrit le pied de page (`overrides/partials/copyright.html`), et
  [la publication des fiches en site accessible](2026-11-18-publier-les-fiches-en-site-accessible.md), qui a écrit
  `docs.yml`.
- **Commits** : `3bef4b9e` (la ligne, son contrôle, sa couleur), `dd46686b` (intégration de `main`, sans contenu
  propre), `50328124` (la doc et le report des renvois `docs.yml:N`), `df518ead` (le tri de la revue). La liste de
  fichiers que la note a reçue compare à une copie locale de `main` en retard : le diff réel de la branche
  (`git diff origin/main...HEAD`) ne touche que les six fichiers ci-dessus, et cette note.

## Le pourquoi

`docs.yml` publie le site de la doc sur GitHub Pages à chaque push sur `main`. Pendant le blocage de la CI, trois
publications ont échoué, et la doc en ligne datait du 22/11 (`2da20b16`) sans que rien ne le dise. Sabine a décidé le
2026-11-25 que le pied de page dirait quelle version est en ligne, par sa date et son commit, sur le modèle
« Documentation publiée le 25/11/2026, commit a1a01efd ». Publier la doc seulement au tag a été écarté par Sabine :
après le gel de K-B qui suit la v0.1.9, aucune correction de la doc ne pourrait plus partir sans livrer l'application.

La contrainte de l'issue : la ligne dit vrai sur ce qui est en ligne. Elle porte le commit construit par le job qui
publie, pas celui d'une PR, et le job échoue avant toute publication si la ligne manque.

## Le comment

### 1. Le workflow nomme le commit et le jour, le site les lit

`.github/workflows/docs.yml:30-33` :

```yaml
      - name: Names the commit and the day of the build
        run: |
          echo "KB_DOCS_COMMIT=$(git rev-parse HEAD)" >> "$GITHUB_ENV"
          echo "KB_DOCS_PUBLISHED_ON=$(date -u +%F)" >> "$GITHUB_ENV"
```

Une ligne écrite dans le fichier `$GITHUB_ENV` devient une variable d'environnement des étapes suivantes du même job.
`git rev-parse HEAD` donne le commit que `actions/checkout` vient de récupérer, donc celui que l'étape suivante
construit. `date -u +%F` donne le jour en UTC, au format `2026-11-25`. MkDocs lit ces deux variables par la balise
`!ENV` (`mkdocs.yml:112-113`) :

```yaml
  published_commit: !ENV [KB_DOCS_COMMIT, ""]
  published_on: !ENV [KB_DOCS_PUBLISHED_ON, ""]
```

La liste donne la variable, puis la valeur prise quand elle n'existe pas : `""`. Les gabarits les lisent sous
`config.extra`.

### 2. Le gabarit écrit la ligne, ou rien

`overrides/partials/copyright.html:15-21` (extrait) :

```jinja
  {%- if config.extra.published_commit and config.extra.published_on %}
  {%- set published_commit = config.extra.published_commit | string %}
  {%- set published_on = config.extra.published_on | string %}
  ...
  {%- set year, month, day = published_on.split("-") %}
```

`!ENV` ne rend pas toujours une chaîne : il donne à la valeur son type YAML implicite. `2026-11-25` devient une date,
et une variable posée mais vide devient `None`. Le test se fait donc sur les valeurs brutes, avant `| string` : une
date et une chaîne non vide sont vraies, `None` et `""` sont fausses. Après le test, `| string` remet la date en
`2026-11-25`, que `split("-")` coupe en trois. Le jour s'écrit « 1er » le premier du mois, puis le mois en lettres,
comme sur le site de K-B (`write_day`, `src/k_b/web/french_dates.py:27-30`, nommé en commentaire comme le jumeau du
gabarit). Le lien vers le commit garde les 40 caractères dans son adresse et en montre 8, comme l'exemple de Sabine.
`<time datetime="2026-11-25">` donne la date en format machine à côté du texte lisible.

### 3. Deux contrôles avant toute publication

`.github/workflows/docs.yml:42-45` cherche la ligne attendue dans la page d'accueil construite :

```yaml
          grep -qF "Documentation publiée le <time datetime=\"$KB_DOCS_PUBLISHED_ON\">" site/index.html
          grep -qF "href=\"https://github.com/SabineLaurent/K-B/commit/$KB_DOCS_COMMIT\"" site/index.html
```

`-F` cherche le texte tel quel, sans expression régulière ; `-q` ne rend que le code de sortie. Un `grep` qui ne
trouve rien sort en 1, et le shell de GitHub (`bash -e`) arrête l'étape : le dépôt de l'artefact de Pages, plus bas,
n'a pas lieu.

`.github/workflows/docs.yml:46-56` prouve le cas inverse, ajouté par le tri de la revue : une valeur vide vaut une
valeur absente. Trois constructions, hors de `site/` (le seul dossier publié), avec le commit vide, le jour vide, puis
sans les deux variables :

```yaml
          for site in empty-commit empty-day not-set; do
            grep -qF 'aria-label="Pied de page"' "$RUNNER_TEMP/$site/index.html"
            if grep -qF 'class="kb-footer-version"' "$RUNNER_TEMP/$site/index.html"; then echo "$site: line found"; exit 1; fi
          done
```

Le premier `grep` vérifie que le pied est là : sans lui, l'absence de la ligne ne prouverait rien. Le second est dans
un `if`, et non écrit `! grep` : sous `bash -e`, une commande précédée de `!` n'arrête jamais le script, et seul le
code de la dernière commande compterait.

### 4. La couleur, et son repli sans `light-dark()`

Les couleurs de K-B sont posées par `light-dark()`, dans un bloc `@supports` qu'un navigateur antérieur à mai 2024
saute (`documentation/stylesheets/extra.css:8-11`). La ligne suit le modèle des autres règles hors du bloc : une
variable de K-B posée dans le bloc (`extra.css:62`), lue avec une valeur de repli (`extra.css:239-246`) :

```css
    --kb-footer-version: var(--md-default-fg-color--light);
...
  color: var(--kb-footer-version, var(--md-footer-fg-color--light));
```

Dans le bloc, c'est le texte secondaire du thème : 8,24:1 en mode clair, 13,35:1 en mode sombre. Hors du bloc, la
variable n'existe pas et `var()` prend la seconde valeur, la couleur des liens du pied de Material, `#FFFFFFB3`, sur
son pied sombre : 9,26:1 en mode clair, 9,44:1 en mode sombre. La première version prenait, hors du bloc, le texte
secondaire du mode clair de Material, `#0000008A` : noir sur ce pied sombre, 1,1:1. Le commit, lui, est un lien : il prend les couleurs des liens
du pied, déjà au tableau des contrastes.

## Choix faits et options écartées

- **Le jour de la construction, pas celui du déploiement** : seul `build` récupère le dépôt et construit le site ;
  `deploy` publie l'artefact tel quel. Le texte « Documentation publiée le » reste celui de la décision de Sabine, et
  l'écart est écrit dans `documentation/accessibilite.md`, « Publier » (constat 5 de la revue, tranché par time-knight,
  délégation de Sabine du 15/10) : un déploiement qui attend son tour, ou `deploy` relancé seul, publie plus tard un
  site construit avant.
- **Publier au tag** : écarté par Sabine (voir « Le pourquoi »).
- **Le format « 25 novembre 2026 »**, en UTC, et non « 25/11/2026 » : le plan validé par Sabine le 2026-11-25 (« je suis
  les reco de time-knight à la condition qu'il soit sûr de lui » ; time-knight : « sûr : oui »), le format des dates du
  site de K-B.
- **Les mois recopiés dans le gabarit** plutôt qu'un hook MkDocs qui importerait `write_day` : un hook coûterait un
  module Python de plus, lu par MkDocs, pour douze mots. La copie est gardée et son jumeau nommé (constat 6, tranché par
  time-knight).
- **Valeur vide = absente** (constat 2) : tester les valeurs brutes avant `| string`. Écarté : un test pytest qui rend
  le gabarit avec Jinja2 ; il ne verrait pas `!ENV`, qui fait de `""` un `None`, la cause même du défaut. Retenu : trois
  constructions réelles dans `docs.yml`, environ une seconde chacune sur le Mac.
- **Repli de couleur** (constat 1) : `--md-footer-fg-color--light`, 9,26:1. Écarté : `--md-footer-fg-color--lighter`,
  la couleur du texte de pied de Material, 4,52:1, trop près du seuil de 4,5:1.
- **Les renvois `mkdocs.yml:N` en retard d'une ligne** (constat 3) : défaut antérieur, laissé à #720. La cause vérifiée
  est `6a71c217` (#510), et non `3e5494b0` (#685) comme le disait la revue. Vérifié ensuite, le constat ne tient pas : un
  renvoi vise le commit que sa fiche nomme dans son introduction. Avant #708, la fiche faisait viser ses renvois
  `mkdocs.yml` à la demande de fusion de #684 (`2da20b16`, `validation:` à la ligne 98, cité par `97-103`), où ils
  tombent sur leurs lignes ; #708 les fait viser `38ae9df5`, où ils tombent aussi. #720 n'a donc pas d'objet.
- **Le commit que visent les renvois de cette branche** : `df518ead`, où `docs.yml` et `extra.css` ont leur forme finale,
  nommé dans l'introduction des deux fiches pour ces deux fichiers ; les autres renvois gardent le commit qu'elles
  nommaient.
- **Les fiches à la règle de #708** (décisions de Sabine du 23/11, appliquées par #708) : ni date de lecture ou de calcul,
  ni nom de personne. Les ajouts de cette branche aux fiches les suivent depuis l'intégration de `main` : la décision
  de #719 y est citée par son issue, et « calculé le » ou « lu le » en sont retirés.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| Avant le tri : `KB_DOCS_COMMIT=` donne `commit None` dans `index.html` ; `KB_DOCS_PUBLISHED_ON=` arrête la construction (`ValueError: not enough values to unpack`) ; l'étape `docs.yml:46-56` sort en 1 | Le défaut du constat 2 existait, et le contrôle le voit |
| Après le tri : l'étape `docs.yml:46-56`, lancée sur le Mac (`bash -eo pipefail`, `RUNNER_TEMP` dans le scratchpad), sort en 0 ; l'étape `docs.yml:42-45` aussi | Une valeur vide ou absente ne donne pas de ligne ; la ligne attendue est là avec les deux valeurs |
| Session précédente : l'étape `docs.yml:42-45` sort en 1 sur une construction sans la ligne, puis en 0 | Le contrôle de la ligne échoue quand elle manque |
| `KB_DOCS_PUBLISHED_ON=2026-12-01` donne `<time datetime="2026-12-01">1er décembre 2026</time>` | La règle du « 1er » |
| `mkdocs build --strict` vert avec et sans variables ; empreinte de Mermaid `OK` ; `uv run pytest` : 5 799 passés | Rien d'autre ne casse (aucun fichier Python touché) |
| Chrome 158 sans interface, axe-core 4.14.1 : 3 pages, modes clair et sombre, 100 % et 200 %, sites avec la ligne, sans elle, et avec la ligne sans le bloc `@supports` (36 cas) | Ligne à 8,24:1 et 13,35:1 ; lien du commit à 7,41:1 et 13,88:1 ; repli à 9,2:1 et 9,39:1 ; 4 arrêts de Tab dans le pied avec la ligne, 3 sans, anneau visible ; mêmes violations axe avec et sans la ligne, aucune dans le pied |

Le repli mesuré par le navigateur (9,2:1 et 9,39:1) est un peu sous le calcul (9,26:1 et 9,44:1) :
`getComputedStyle` arrondit l'opacité à deux décimales (0,7 pour `B3`, soit 179/255 = 0,702).

## Ce que tu dois pouvoir défendre

1. **Comment sait-on que la ligne dit vrai sur ce qui est en ligne ?** Le commit est celui que `build` a récupéré et
   construit, le jour celui de la construction ; `docs.yml:42-45` vérifie les deux valeurs exactes dans la page
   construite, avant le dépôt de l'artefact que `deploy` publie. Seul l'écart de jour est possible, et il est écrit
   (« Publier »).
2. **Que se passe-t-il si une variable est vide ?** Pas de ligne, et la construction continue : le test porte sur les
   valeurs brutes (`copyright.html:15`), et `docs.yml:46-56` le prouve à chaque construction.
3. **Pourquoi pas un test pytest ?** Le défaut vient de `!ENV`, qui fait d'une variable vide un `None` : seul un vrai
   `mkdocs build` passe par là. Le contrôle vit où le site est construit.
4. **Et un navigateur ancien ?** Il saute le bloc `@supports` ; la ligne prend alors la couleur des liens du pied de
   Material, 9,26:1 (`extra.css:239-246`), mesurée aussi dans Chrome avec le bloc rendu faux.
5. **Pourquoi recopier les mois ?** Le site de la doc n'importe pas K-B : un hook MkDocs le ferait pour douze mots. Le
   jumeau `write_day` est nommé dans le gabarit, pour que l'un ne change pas sans l'autre.

## Zones non vérifiées

- **L'étape `docs.yml:46-56` n'a pas encore tourné sur GitHub** : elle a tourné sur le Mac, extraite du workflow, avec
  le `bash` et l'`env -u` de macOS. `env -u` de GNU, sur `ubuntu-latest`, a la même option, et le défaut de
  `bash -e` y est le même ; la CI de la PR le dira.
- **Le repli sans `light-dark()`** est mesuré dans Chrome 158, le bloc `@supports` rendu faux par une copie modifiée
  du site, pas dans un navigateur ancien.
- **La relance du seul `deploy`** : tirée de la doc de GitHub (« Re-running workflows and jobs », lue le 2026-11-25) et
  du défaut `retention-days: "1"` de `actions/upload-pages-artifact` v5.0.0, pas observée.
- **Les types implicites de `!ENV`** : un commit fait de chiffres seuls serait lu comme un entier, que `| string`
  réécrit. Le cas n'a pas été essayé (environ une chance sur 150 millions pour 40 caractères hexadécimaux).
- **Le rendu au lecteur d'écran** n'est pas vérifié, comme pour le reste du site.
- **Relevé au navigateur, non corrigé** : au focus, l'anneau du lien du commit recouvre la virgule qui le précède
  (« 2026, »), à 100 % comme à 200 %.

## Ce qui reste

- #720 : sans objet (voir « Choix faits »), à fermer.
- Après la fusion : lire la ligne sur `https://sabinelaurent.github.io/K-B/`, une fois `deploy` passé.
- L'anneau qui recouvre la virgule : à trancher (le laisser, ou espacer le lien), hors du tri de cette revue.
