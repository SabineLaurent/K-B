# Afficher la version en ligne dans le pied du site

- **Date** : 2026-11-25
- **Branche** : `feat/web-deployed-version`
- **Issue** : #716
- **Commits** : `5e92cec8` (la ligne de version), `d95c186c` (corrections de la revue)
- **Fichiers principaux** : `Dockerfile`, `.github/workflows/deploy.yml`, `src/k_b/web/settings.py`,
  `src/k_b/web/rendering.py`, `src/k_b/web/templates/base.html`, `tests/web/test_settings.py`,
  `tests/web/test_accessibility.py`

La liste de fichiers fournie à la note compare la branche à une base plus ancienne que `origin/main` (139 fichiers) :
la branche elle-même ne porte que les deux commits ci-dessus, 18 fichiers (`git diff --stat origin/main...HEAD`).
Les autres fichiers de cette liste viennent de PR déjà fusionnées, et la note ne les couvre pas.

## Le pourquoi

Sabine a décidé, le 2026-11-25, qu'une ligne du pied de page de toutes les pages du site dirait la version
déployée, c'est-à-dire le tag (« v0.1.9 »). Elle veut voir d'un coup d'œil quel code tourne en ligne, sans ouvrir
Azure ni les journaux d'Actions.

Avant ce travail, rien ne transmettait le tag à l'application. `deploy.yml` construit l'image d'un tag une seule
fois, y écrit le commit dans un label OCI, puis met les apps à jour par l'empreinte de l'image. Le site, lui, ne
savait pas quelle version il était.

## Le comment

### 1. L'image porte son tag

```dockerfile
ARG KB_VERSION=""
ENV KB_VERSION=$KB_VERSION
```
(`Dockerfile:58-59`)

`ARG` déclare un argument de construction, que `docker buildx build --build-arg KB_VERSION=…` remplit. Il
n'existe que pendant la construction. `ENV` recopie sa valeur dans l'environnement de l'image : chaque conteneur
lancé de cette image a `KB_VERSION`. Sans l'argument, la valeur par défaut `""` donne une variable posée, mais vide.

Les deux lignes sont placées après le dernier `RUN`, juste avant `USER`. Un `RUN` placé après un `ARG` le voit dans
son environnement : changer la valeur de l'argument reconstruirait ce `RUN`, sans le cache. Ici, aucun `RUN` ne
suit, donc la valeur ne reconstruit rien.

### 2. `deploy.yml` donne le tag à la construction

```bash
--label "org.opencontainers.image.revision=$SHA" --build-arg "KB_VERSION=$GITHUB_REF_NAME" \
```
(`.github/workflows/deploy.yml:117`)

`$GITHUB_REF_NAME` est le nom du tag poussé (`v0.1.9`). C'est une variable du shell entre guillemets, pas une
expression `${{ github.ref_name }}` de GitHub Actions. Une expression serait recopiée dans le texte du script avant
son exécution, alors qu'une variable n'est jamais lue comme du code. Le job `check` a déjà refusé tout ref qui
n'est pas `vMAJEUR.MINEUR.CORRECTIF` (`deploy.yml:38`).

Comme l'image est construite une fois par tag puis épinglée par empreinte, la version suit l'image partout où elle
va. Un retour arrière reprend l'image du tag sans la reconstruire, avec sa version. Une passe 2 de Bicep, qui tire
`k-b:<tag>`, tire la même image.

### 3. `kb serve-web` lit la version et la vérifie

```python
VERSION_TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
```
(`src/k_b/web/settings.py:47`)

```python
    version = environ.get(VERSION_VARIABLE) or None
```
(`src/k_b/web/settings.py:73`)

`or None` fait d'une valeur vide une absence : c'est le cas d'une image construite sans l'argument (`image.yml`,
`compose.yaml`, à la main). `find_version_refusal` (`settings.py:106`) refuse ensuite une valeur posée qui ne suit
pas `VERSION_TAG`, avec `fullmatch`. `fullmatch` exige que tout le texte corresponde. `match` accepterait
`v0.1.9-rc.1`, et un `$` en fin de motif accepterait un `\n` final. `[0-9]` et non `\d` : en Python, `\d` accepte
aussi les chiffres d'autres écritures, comme le zéro pleine largeur.

Le refus passe par la chaîne des autres réglages (`settings.py:86`). `kb serve-web` sort alors avec le code 2 sans
rien servir, comme pour un port ou un hôte refusé.

### 4. Le gabarit commun reçoit la version

```python
        "deployed_version": request.app.state.version,
```
(`src/k_b/web/rendering.py:18`)

```html
{% if deployed_version -%}
<p class="site-footer-version">Version déployée: {{ deployed_version }}</p>
```
(`src/k_b/web/templates/base.html:34-35`)

`create_app` range la version dans `app.state.version`. `add_layout_context` est un *context processor* de
Starlette : une fonction appelée à chaque rendu, qui ajoute ses clés au contexte de la page. Toutes les pages
héritent de `base.html`, les pages d'erreur comprises, donc toutes ont la ligne. Le `-` de `-%}` retire le retour à
la ligne qui suit la balise, pour que le pied ne porte pas de ligne vide.

La clé s'appelle `deployed_version`, pas `version`. Starlette ajoute les clés du *context processor* après celles
de la page : une page qui poserait sa propre clé `version` (celle d'une release, par exemple) verrait sa valeur
remplacée par le tag du site, sans erreur (constat 2 de la revue).

### 5. Un test tient les deux règles égales

```python
CHECKED_REF = re.compile(r'\[\[ "\$GITHUB_REF" =~ \^refs/tags/(\S+)\$ \]\]')
```
(`tests/web/test_settings.py:22`)

Le test `test_the_rule_of_a_version_is_the_one_of_the_job_check_of_deploy_yml` (`test_settings.py:111`) lit dans
`deploy.yml` le motif du job `check` et le compare au texte de `VERSION_TAG.pattern`. Si quelqu'un élargit l'un
sans l'autre, par exemple pour accepter `v1.0.0-rc.1` au déploiement, le site refuserait de démarrer après la
migration de la base. Le test échoue avant (constat 3 de la revue). Un commentaire à chacun des deux endroits le
rappelle aussi.

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Transport du tag | `ARG`/`ENV` dans l'image, `--build-arg` dans `deploy.yml` : la version suit l'empreinte, une seule source | Une variable posée par Bicep depuis `imageTag` : `deploy.yml` ne change que l'image des apps, la variable garderait l'ancien tag jusqu'à la passe 2 à la main. `--set-env-vars` dans `deploy.yml` : une passe Bicep l'effacerait, deux sources pour une valeur. La `version` de `pyproject.toml` : 0.1.0 pour des tags v0.1.8, à monter à chaque tag. Le label OCI `revision` : illisible depuis le conteneur, et c'est le commit, pas le tag |
| Texte | « Version déployée: v0.1.9 », sans espace avant « : » | Règle de Sabine du 2026-11-11 pour le texte du site (tenue par `test_no_space_comes_before_a_colon_or_a_semicolon`) |
| Sans version | Pas de ligne : le site n'écrit jamais une version qu'il n'a pas | « Version inconnue » : une ligne qui n'apprend rien |
| Valeur mal formée | Refus de démarrer, code 2 : échouer fermé, comme les autres réglages (`code.md`) | Afficher ou taire la valeur : un réglage faux passerait sans bruit |
| Page 403 | La ligne y est aussi : en ligne, la plateforme ne laisse entrer que l'identifiant de Sabine (`allowedPrincipals`), et le tag est public | Retirer la ligne de la 403 (constat 1 de `/code-review`), non retenu, décision du plan validé |
| Garde dans `deploy.yml` | Aucune | Lire l'environnement de l'image épinglée et exiger `KB_VERSION=<tag>` : elle n'attrape qu'une ligne absente, visible dans le pied, et une garde boguée bloquerait le déploiement de la v0.1.9 |
| Paramètre de `create_app` | `version` en mot-clé obligatoire | Un défaut `None` : `kb serve-web` pourrait l'oublier sans qu'un test le voie |

Le plan a été relu par un sous-agent sans contexte (verdict « go, avec des changements », 7 constats sur 8
intégrés), puis validé par Sabine sur la recommandation de time-knight.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| Avant le code : 15 échecs et 4 erreurs dans `tests/web` (`create_app() got an unexpected keyword argument 'version'`) | Les tests ont été écrits d'abord, et échouaient sans le code |
| `test_the_footer_of_every_page_gives_the_version_deployed_after_its_links` (`test_accessibility.py:307`), sur les 24 pages de `PAGES`, 403, 404, 405 et 500 comprises | Chaque page que le site peut rendre porte la ligne, juste après la liste des liens |
| `test_a_site_without_a_version_has_no_line_of_version_in_its_footer` (`test_accessibility.py:318`) | Sans version, aucune ligne |
| `test_an_empty_version_is_no_version`, `test_a_version_tag_of_deploy_yml_is_kept`, `test_a_version_that_is_not_a_tag_of_deploy_yml_is_refused_quoted` (9 valeurs : `0.1.9`, `v0.1`, `v01.1.9`, `v0.01.9`, `v0.1.09`, `v0.1.9-rc.1`, `"v0.1.9\n"`, `" v0.1.9"`, un zéro pleine largeur) | La lecture et le refus, la valeur citée par `quote_value` |
| `test_serve_web_gives_the_version_of_its_image_to_the_site` (`test_serve_web.py:87`) | `kb serve-web` passe bien la version de l'environnement à l'app |
| `test_the_rule_of_a_version_is_the_one_of_the_job_check_of_deploy_yml` ; le même contrôle, rejoué en mémoire sur un `deploy.yml` élargi aux préversions, donne `False` | Les deux règles sont égales aujourd'hui, et le test voit un écart |
| `test_every_variable_kb_reads_is_in_the_example` | `KB_VERSION` est décrite dans `.env.example` |
| `uv run pytest` : 5 837 passés ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict`, `mkdocs build --strict` : verts | Les contrôles du dépôt |
| `/security-review` : aucun constat ; `/code-review` : 5 nits, 3 corrigés (`d95c186c`), 2 non retenus par décision du plan | La revue |

## Ce que tu dois pouvoir défendre

1. **Pourquoi passer par l'image plutôt que par une variable de l'app dans Bicep ?** Parce que `deploy.yml` ne
   change que l'image des apps (`az containerapp update --image`). Une variable de Bicep garderait l'ancien tag
   jusqu'à la passe 2 à la main. Dans l'image, la version suit l'empreinte, en retour arrière compris
   (`Dockerfile:58-59`, `deploy.yml:117`).
2. **Un tag piégé peut-il injecter du code dans le workflow ou une page ?** Non. Le job `check` n'accepte que
   `vN.N.N` (`deploy.yml:38`), et seuls les administrateurs poussent un tag `v*`. Le tag arrive au shell par une
   variable entre guillemets, jamais par `${{ }}`. Côté site, `VERSION_TAG.fullmatch` le revérifie, et Jinja2
   l'échappe (`autoescape=True`, `rendering.py`).
3. **Que se passe-t-il si quelqu'un élargit le job `check` aux préversions ?** `kb serve-web` refuserait
   `v1.0.0-rc.1` et sortirait en code 2, après la migration de la base. Le test d'égalité des deux règles échoue
   avant (`test_settings.py:111`).
4. **Pourquoi aucune ligne en local ?** Une image construite sans l'argument a `KB_VERSION` vide, et `or None` en
   fait une absence (`settings.py:73`). Le site ne montre jamais une version qu'il ne connaît pas.
5. **Montrer la version, n'est-ce pas une fuite d'information ?** Le dépôt, ses tags et les journaux d'Actions sont
   publics depuis le 2026-11-25. Le site est privé : Entra ne laisse entrer que l'identifiant de Sabine. C'est la
   version de K-B, pas celle d'un logiciel du serveur, que la règle Opquast 213 vise et que le site tait déjà
   (`server_header=False`).

## Zones non vérifiées

- **L'argument de `deploy.yml` de bout en bout** : il ne se vérifie qu'au déploiement d'un tag construit avec
  `KB_VERSION`. Docker ne tournait pas sur le Mac, et `image.yml` construit sans argument. Après ce déploiement,
  Sabine lit le pied en ligne.
- **Le rendu visuel** : la ligne n'a été vue ni dans un navigateur ni au zoom de 200 %. Sa couleur (`--color-slate`
  sur `--color-card`) est une paire déjà testée par `test_each_pair_of_the_chart_has_its_contrast`, et sa taille est
  en `rem`.
- **`/code-review`** s'est arrêté plus tôt que prévu, sur un avertissement de quota : sa liste peut être incomplète.

## Ce qui reste

- **La version de la documentation MkDocs en ligne** (décision de Sabine du 2026-11-25 : la date de publication et
  le commit construit par le job qui publie) : une issue et une PR à part, après celle-ci.
- **Les API** (`kb serve-data`, `kb serve-ai`) ne lisent pas `KB_VERSION` : la décision ne porte que sur le site.
