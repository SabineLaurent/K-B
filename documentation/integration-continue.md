# L'intégration continue de K-B

!!! note "Compétences de la certification"

    > Documentation des procédures d'installation et de test de la chaîne.

    — C18

    > Documentation utilisateur, pour le déclenchement de la chaîne.

    — C18

Cette fiche dit ce que fait la chaîne d'intégration continue (CI) de K-B, comment on la déclenche et la relance,
comment elle s'installe, se configure et se teste, et que faire quand elle échoue. Elle est écrite d'après le code de
`main` au commit `57ff235` (2026-11-14), avec le workflow `Docs` et l'audit de tous les groupes de dépendances ajoutés
le même jour (#167), et d'après les réglages du dépôt lus le même jour; la publication du site à chaque fusion et les
contrôles requis, d'après la demande de fusion de #684 et le ruleset lu le 2026-11-22. Les exécutions citées se relisent
par `gh run view <id> --repo SabineLaurent/K-B`, 90 jours au plus: c'est la durée de garde des journaux du dépôt
(`gh api repos/SabineLaurent/K-B/actions/permissions/artifact-and-log-retention` → `"days":90`). La mise en ligne
d'une version, qui suit la CI, est dans [la fiche de la livraison continue](livraison-continue.md).

## La chaîne en bref

Chaque demande de fusion (PR, <span lang="en">pull request</span>) vers `main`, et chaque push sur `main` (donc chaque fusion), lance la CI. Elle vérifie le code (tests,
couverture, lint, format, typage), ses dépendances (vulnérabilités connues), l'image du conteneur et le Bicep. Sur
chaque PR, elle construit aussi le site des fiches de `documentation/` ([Le workflow `Docs`](#le-workflow-docs)). Une
PR ne fusionne que si ses six contrôles requis sont verts sur une branche à jour avec `main`
([Le ruleset de `main`](#le-ruleset-de-main)). La CI ne pousse rien et ne déploie rien sur Azure, où elle n'a aucun
droit. Seul `Docs` publie quelque chose: le site des fiches, sur GitHub Pages, à chaque fusion une fois la variable
de dépôt `PAGES_PUBLISH` posée à `true`, ou lancé à la main depuis `main`.

### Les outils

| Outil | Rôle dans la chaîne | Où il est réglé |
|---|---|---|
| GitHub Actions | lance les workflows sur des runners `ubuntu-latest`; chaque action est épinglée par son SHA, sa version en commentaire | `.github/workflows/ci.yml`, `image.yml`, `infra.yml`, `docs.yml` |
| uv 0.13.6 | installe Python 3.13 (`.python-version`) et les dépendances de `uv.lock` (`uv sync --locked`), lance chaque outil (`uv run`) | `ci.yml`, `version: "0.13.6"` dans chacun des sept jobs (l. 20, 34, 46, 58, 90, 106, 121); `docs.yml:25` |
| pytest et pytest-cov | lancent les tests et mesurent la couverture des lignes et des branches de `src/k_b/` | `pyproject.toml`, `[tool.coverage.*]` (l. 76-89) |
| ruff | lint et format du Python | `pyproject.toml`, `[tool.ruff.*]` (l. 52-71) |
| mypy | typage, en mode `--strict` | `ci.yml:61`, `pyproject.toml:73-74` |
| pip-audit 2.10.1 | cherche les vulnérabilités connues des versions de `uv.lock`, de tous les groupes de dépendances, avec leurs empreintes | `ci.yml:25-26` |
| PostgreSQL 18.6 | un service du job `tests-postgresql`, épinglé par son digest | `ci.yml:69-83` |
| Docker Buildx | construit l'image `linux/amd64` de K-B et la contrôle | `image.yml` |
| Grype v0.121.3 (Anchore) | cherche dans l'image les vulnérabilités connues des paquets Debian, des paquets Python (l'environnement virtuel, et `pip` de l'image de base) et de CPython; refuse une haute ou critique qui a un correctif | `image.yml:64-82` |
| Azure CLI et Bicep v0.48.1 | compile `infra/main.bicep`, sans connexion à Azure | `infra.yml` |
| MkDocs 1.6.1, avec Material for MkDocs 9.8.1 | construit le site des fiches de `documentation/`, en mode strict | `mkdocs.yml`; versions dans `uv.lock`, groupe `docs` (`pyproject.toml:45-47`) |
| Dependabot | ouvre chaque semaine les PR de mise à jour des actions et des images de base du `Dockerfile` | `.github/dependabot.yml` |
| Ruleset « Basic-rules-main-protect » | dit quels contrôles une PR doit passer pour fusionner | réglages du dépôt ([Le ruleset de `main`](#le-ruleset-de-main)) |

Les actions épinglées sont `actions/checkout` v7.0.1 et `astral-sh/setup-uv` v10.3.3 dans les workflows, et en plus,
dans `docs.yml`, `actions/upload-pages-artifact` v5.0.0 et `actions/deploy-pages` v5.0.1 (`docs.yml:36`, `:61`).

La chaîne tourne sur GitHub Actions, et ces faits l'y attachent: le dépôt est sur GitHub (`git remote get-url origin`
→ `git@github.com:SabineLaurent/K-B.git`); son ruleset exige des contrôles rendus par GitHub Actions (`integration_id`
15368, l'identifiant de l'application `github-actions` d'après `gh api apps/github-actions`); Dependabot met à jour les
actions épinglées et leur commentaire de version (`.github/dependabot.yml:3-9`); le dépôt exige le SHA complet de
chaque action (`sha_pinning_required`, `gh api repos/SabineLaurent/K-B/actions/permissions`).

### Les déclencheurs

| Déclencheur | Ce qui tourne |
|---|---|
| une PR vers `main`: ouverte, rouverte, ou un commit poussé sur sa branche | `CI`, `Image`, `Infra` et `Docs` (`ci.yml:3-7`, `image.yml:3-7`, `infra.yml:3-7`, `docs.yml:7-9`); `Infra` sans filtre de chemin depuis #496 |
| un push sur `main`, c'est-à-dire une fusion | `CI`, `Image`, `Infra` et `Docs`, sur le commit de fusion (`ci.yml:4-5`, `image.yml:4-5`, `infra.yml:4-5`, `docs.yml:10-11`); `Docs` n'y publie le site que si la variable de dépôt `PAGES_PUBLISH` vaut `true` (`docs.yml:33-35`, `:42-44`) |
| un lancement de `Docs` à la main (`workflow_dispatch`, `docs.yml:12`), sur une branche choisie | `Docs` seul; il ne publie le site que lancé depuis `main` (`docs.yml:33-35`, `:42-44`) |
| « <span lang="en">Re-run all jobs</span> » ou « <span lang="en">Re-run failed jobs</span> » sur une exécution, ou `gh run rerun <id>` | la même exécution, sur le même commit |
| le planning de Dependabot, chaque semaine (`dependabot.yml:6-7`, `:13-14`) | une PR de mise à jour, qui lance la CI comme toute PR |
| une alerte de Dependabot, à tout moment (mises à jour de sécurité, activées dans [Les réglages de Dependabot](#les-reglages-de-dependabot)) | une PR de sécurité, sans attente, qui lance la CI comme toute PR |

Une PR vers une autre branche que `main` ne lance rien: le filtre `branches: [main]` porte sur la branche visée.
`Docs` se lance à la main depuis l'onglet <span lang="en">Actions</span> du dépôt, ce qui n'a pas été essayé le
2026-11-14; ce qu'il faut régler avant qu'il publie est dans [GitHub Pages](#github-pages).
GitHub lance aussi deux workflows à lui, hors du dépôt, « <span lang="en">Dependabot Updates</span> » et
« <span lang="en">Dependency Graph</span> » (chemin `dynamic/…` dans `gh api repos/SabineLaurent/K-B/actions/workflows`,
événement `dynamic` de leurs exécutions); `Deploy` ne les compte pas (`deploy.yml:61-62`).
Aucun workflow de la CI n'a de `concurrency`, `Docs` compris: deux pushes rapprochés lancent deux exécutions, et la
première n'est pas annulée.

### Les jobs et leurs tâches

Les jobs d'un même workflow tournent en parallèle, chacun sur un runner neuf, sauf un job qui en attend un autre: le
`deploy` de `Docs` attend son `build` (`needs`, `docs.yml:45`). Dans un job, les étapes s'enchaînent, et la première
qui échoue arrête le job. Chaque workflow n'a qu'un jeton qui lit le dépôt (`permissions: contents: read`,
`ci.yml:9-10`, `image.yml:9-10`, `infra.yml:9-10`, `docs.yml:14-15`), et aucun ne lit de secret. Seul le job `deploy`
de `Docs` a ses propres droits, `pages: write` et `id-token: write` (`docs.yml:53-55`), pour publier sur GitHub Pages.

#### Le workflow `CI`

`.github/workflows/ci.yml`. Chaque job récupère le dépôt, installe uv 0.13.6, puis `uv sync --locked`, qui refuse un
`uv.lock` qui ne suit plus le `pyproject.toml`. Seul `tests` garde le cache de uv (`save-cache: false` dans les cinq
autres, l. 21, 47, 59, 91 et 107).

Le tableau suivant donne chaque job de `CI`, ses lignes, sa tâche, et s'il est requis à la fusion.

| Job | Tâche | Requis à la fusion |
|---|---|---|
| `audit` (l. 14-26) | `uv export --frozen --no-emit-project --all-groups` écrit les versions de `uv.lock`, de tous les groupes de dépendances, avec leurs empreintes, puis `uvx pip-audit@2.10.1 --require-hashes --disable-pip` les compare aux vulnérabilités connues | oui |
| `tests` (l. 28-38) | `uv run pytest --cov --cov-report=term-missing:skip-covered`: la suite, sans les tests marqués `e2e` ni `postgresql`, et le seuil de couverture de 96 % (`fail_under`, `pyproject.toml:87`) | oui |
| `lint` (l. 40-50) | `uv run ruff check`, puis `uv run ruff format --check` | oui |
| `types` (l. 52-61) | `uv run mypy --strict` sur `src` | oui |
| `tests-postgresql` (l. 63-93) | `uv run pytest -m postgresql`, contre le service `postgres:18.6` du job (utilisateur `kb`, base en UTF8 et collation C, l. 72-76), joint par `KB_TEST_POSTGRESQL_URL` (l. 85), sans mot de passe (`POSTGRES_HOST_AUTH_METHOD: trust`, un serveur que seul le runner joint) | oui |
| `tests-data` (l. 95-109) | `uv run pytest tests/etl tests/test_schema.py tests/test_items.py tests/ai_api/test_watch_items.py`: les tests des données, à part, sans `--cov` (`tests` les lance aussi et garde le seuil) | non |
| `digests-reference` (l. 111-131) | `uv run python tests/ai_api/digests_evaluation.py reports/digests-reference-report.md`: rejoue le jeu de référence de `POST /digests` (#479) et échoue sous un seuil du 15/10 (100 % de schémas valides après une nouvelle tentative, au moins 95 % de fidélité, aucun item oublié), ou si le rejeu n'envoie pas tous les appels du jeu dans leur ordre, ou si la route ne répond pas 200; puis `actions/upload-artifact` v7.0.2 dépose le rapport, même en échec (`gh run download <id> -n digests-reference-report`, gardé 30 jours). Le jeu est rejoué, jamais envoyé au modèle: le job juge les contrôles de K-B sur des sorties enregistrées, et un changement de `prompt_version` le périme; le modèle se mesure à chaque enregistrement du jeu par Sabine (#520). | non |

Depuis #167, `audit` lit aussi le groupe `docs`, MkDocs et Material (`pyproject.toml:45-47`), que `uv export` laisse
de côté sans `--all-groups` (`ci.yml:23-25`). Le 2026-11-14, `uv export --frozen --no-emit-project` sans l'option ne
liste ni `mkdocs` ni `mkdocs-material`, mais liste `pytest` et `mypy`, du groupe `dev`; avec l'option, il liste
`mkdocs==1.6.1` et `mkdocs-material==9.8.1`. Une vulnérabilité connue de MkDocs ou de Material fait donc échouer
`audit` sur chaque PR.

#### Le workflow `Image`

`.github/workflows/image.yml`, un job, `image-build`, que le ruleset de `main` ne requiert pas à la fusion (lu le
2026-11-22). Le tableau suivant donne ses
étapes dans l'ordre, et ce que fait chacune; une étape sans nom dans `image.yml` y est décrite en français.

| # | Étape (lignes d'`image.yml`) | Ce qu'elle fait |
|---|---|---|
| 1 | Récupérer le dépôt (l. 20) | `actions/checkout`, `.git` compris |
| 2 | Planter des fichiers à écarter (l. 24-28) | crée des fichiers que `.dockerignore` doit écarter du contexte de construction, nommés après le tableau |
| 3 | `Sends only what the Dockerfile copies to the build` (l. 31-37) | vérifie que le contexte de construction ne contient, à sa racine, que `README.md`, `pyproject.toml`, `src` et `uv.lock` (l. 35), et nulle part un fichier planté ni un `__pycache__` (l. 36) |
| 4 | Construire l'image (l. 38) | `docker buildx build --platform linux/amd64 --tag k-b:ci .` |
| 5 | `Runs as a non-root user` (l. 39-43) | vérifie que l'utilisateur de l'image n'est pas root (`id -u` différent de 0) |
| 6 | `Holds none of the planted files` (l. 45-48) | vérifie qu'aucun chemin de l'image ne s'appelle `.env*`, `*.sqlite*`, `decoy`, `.DS_Store` ni `.git` (l. 47); `__pycache__` n'est cherché que dans le contexte (étape 3) |
| 7 | `Refuses to start without KB_DATA_DIR` (l. 51-57) | vérifie que `kb create-db` sans `KB_DATA_DIR` sort en code 2 avec `KB_DATA_DIR must point to the data directory` |
| 8 | `Starts kb and creates the database` (l. 60-63) | lance `kb --help`, puis `kb create-db` dans le dossier de données de l'image |
| 9 | `Installs Grype v0.121.3` (l. 67-72) | télécharge l'archive de Grype de sa release et vérifie son SHA256 (l. 71), comme Bicep dans `Infra` |
| 10 | `Has no high or critical vulnerability that has a fix` (l. 78-82) | lance `grype docker:k-b:ci --only-fixed --fail-on high`: Grype lit le système de fichiers final de l'image, tire sa base de vulnérabilités à chaque exécution (refusée si elle a plus de 5 jours, son défaut), garde les vulnérabilités qui ont un correctif (`--only-fixed`), puis échoue s'il en reste une haute ou critique (`--fail-on high`); le tableau des vulnérabilités gardées se lit dans le journal de l'étape. En dernier, pour qu'un scan rouge ne cache pas le résultat des étapes 5 à 8 |

Les fichiers plantés à l'étape 2 sont, à la racine, `.env`, `.env.decoy`, `temp/decoy`, `reports/decoy` et
`.venv/decoy`, et dans `src/k_b/`, `.env.decoy`, `decoy.sqlite`, `decoy.sqlite-wal`, `.DS_Store` et
`__pycache__/decoy.pyc` (l. 25-28).

L'image `k-b:ci` n'est poussée nulle part: celle qui part en ligne est construite par `Deploy`, depuis le commit du
tag.

#### Le workflow `Infra`

`.github/workflows/infra.yml`, un job, `bicep-build`, requis à la fusion depuis #496: il récupère le dépôt (l. 19),
demande à `az` d'utiliser son propre Bicep (l. 21), installe Bicep v0.48.1 (l. 22), vérifie son SHA256 (l. 24),
affiche sa version (l. 25), puis compile `infra/main.bicep` (l. 26). Il ne se connecte pas à Azure: Sabine applique le
Bicep à la main (`infra/README.md`).

#### Le workflow `Docs`

`.github/workflows/docs.yml`, ajouté avec #167, deux jobs, aucun requis à la fusion (ruleset lu le 2026-11-14). Il
tourne sur chaque PR vers `main`, sur chaque push sur `main` et quand on le lance à la main (`workflow_dispatch`)
(`docs.yml:7-12`).

- `build` (l. 19-38) récupère le dépôt (l. 22) et installe uv 0.13.6, sans enregistrer le cache (l. 23-26). Il
    construit le site par `uv run --locked --only-group docs mkdocs build --strict` (l. 27-28): le groupe `docs` seul, aux
    versions de `uv.lock`, sans K-B ni ses outils de développement. En mode strict, un lien vers un fichier absent, une
    ancre absente ou une fiche oubliée dans la navigation fait échouer la construction (`mkdocs.yml:89-95`). Puis
    `sha256sum --check` compare le fichier de Mermaid que le plugin `privacy` a téléchargé depuis unpkg, dans sa version
    11 qui bouge (`mermaid@11`), à l'empreinte du fichier de Mermaid 11.17.2 (l. 29-32). Depuis `main`, sur un push
    quand la variable de dépôt `PAGES_PUBLISH` vaut `true`, ou lancé à la main, il dépose enfin `site/` en artefact de
    Pages (l. 33-38), que `deploy` publie.
- `deploy` (l. 40-61) ne tourne que depuis `main`, sur un push quand `PAGES_PUBLISH` vaut `true`, ou lancé à la main
    (l. 42-44), après `build` (l. 45); un seul déploiement tourne à la fois (l. 48-50). Il a les droits
    `pages: write` et `id-token: write` (l. 53-55), dans l'environnement `github-pages` (l. 56-58), et publie le site
    par `actions/deploy-pages` (l. 60-61).

Sur une PR, `deploy` est donc sauté. GitHub Pages n'est pas activé sur le dépôt le 2026-11-14:
voir [GitHub Pages](#github-pages).

#### Après la CI

`Deploy` ne met en ligne qu'un commit dont toutes les exécutions des workflows du dépôt sont finies et vertes, `Image`
et `Infra` comprises (`deploy.yml:51-67`). Un contrôle non requis à la fusion compte donc à la livraison.

`Docs` compte aussi. Il tourne sur chaque commit de `main` (`docs.yml:10-11`), et son exécution en échec, annulée ou pas
encore finie, fait refuser le tag de ce commit. Pour livrer ce commit malgré tout, relancer
`Docs` jusqu'à ce qu'il passe (`gh run rerun <id> --repo SabineLaurent/K-B`), ou livrer un commit suivant. `Deploy`
n'écarte pas `Docs` de son contrôle: c'est un contrôle de sécurité de la livraison (journal des décisions d'architecture, ou ADR,
2026-11-14, « Documentation publiée par un site MkDocs sur GitHub Pages »).

## Déclencher la chaîne

Cette partie s'adresse à qui ouvre une PR sur K-B.

### Lancer la CI

Ouvrir une PR vers `main`, ou pousser un commit sur sa branche. Il n'y a rien d'autre à faire.

```sh
git push -u origin <branche>
gh pr create --repo SabineLaurent/K-B --base main
gh pr checks <n° de la PR> --repo SabineLaurent/K-B --watch    # attend la fin, puis un contrôle par ligne
```

Une PR reçoit onze contrôles: les sept jobs de `CI`, `image-build`, `bicep-build`, que `infra.yml` lance sur toute PR
depuis #496, qu'elle touche `infra/` ou non, et les deux jobs de `Docs`, `build` et `deploy`. Dix tournent; `deploy`
est sauté sur une PR (`docs.yml:42-44`), et GitHub le liste comme tel: le 2026-11-18, `gh pr checks 637` donne `deploy`
à `skipping`.

### Fusionner

C'est possible quand les six contrôles requis (`audit`, `tests`, `lint`, `types`, `tests-postgresql`,
`bicep-build`) sont verts et que la branche est à jour avec `main`. Si `main` a avancé, mettre la branche à jour
(`git fetch origin`, puis `git rebase origin/main` et `git push --force-with-lease`, ou
« <span lang="en">Update branch</span> » sur la PR): la CI repasse sur le nouveau commit. La fusion se fait par un
commit de fusion, la seule méthode permise par le ruleset.

### Relancer une exécution

Par exemple après un échec du réseau: « <span lang="en">Re-run failed jobs</span> » sur la page de l'exécution, ou:

```sh
gh run list --repo SabineLaurent/K-B --branch <branche> --limit 3     # l'id de l'exécution
gh run rerun <id> --repo SabineLaurent/K-B --failed                    # les jobs en échec seuls
gh run rerun <id> --repo SabineLaurent/K-B                             # tous les jobs
```

Une relance reprend le même commit et les mêmes workflows, jusqu'à 30 jours après l'exécution: pour tester une
correction, pousser un commit.

### Lire le résultat d'une fusion

Le résultat d'une fusion sur `main` se lit par:

```sh
git fetch origin
gh run list --repo SabineLaurent/K-B --commit "$(git rev-parse origin/main)" \
  --json workflowName,event,status,conclusion -q '.[] | [.workflowName, .event, .status, .conclusion] | @tsv'
# lu sur 89ef7fb le 2026-11-10: « CI push completed success » et « Image push completed success »
```

## Installer la chaîne

Les workflows et `dependabot.yml` vivent dans le dépôt: un clone les a. Le reste se règle dans GitHub, une fois par
dépôt. Ces réglages se lisent sans rien changer, par les commandes données, relues le 2026-11-14; leur création sur
un dépôt neuf n'a pas été essayée.

### Les réglages de GitHub Actions

Dans <span lang="en">Settings → Actions → General</span>:

- Actions activées, toutes les actions permises (`allowed_actions: all`, pour les actions tierces), et le SHA complet
    exigé pour chaque action (`sha_pinning_required`);
- jeton par défaut des workflows en lecture seule, sans droit d'approuver une PR.

```sh
gh api repos/SabineLaurent/K-B/actions/permissions
# lu le 2026-11-14: {"enabled":true,"allowed_actions":"all","sha_pinning_required":true}
gh api repos/SabineLaurent/K-B/actions/permissions/workflow
# lu le 2026-11-14: {"default_workflow_permissions":"read","can_approve_pull_request_reviews":false}
```

### Le ruleset de `main`

Dans <span lang="en">Settings → Rules → Rulesets</span>, avec ces règles:

- nom « Basic-rules-main-protect », actif (`enforcement: active`), sans contournement (`bypass_actors` vide);
- cible: la branche par défaut et `refs/heads/main`;
- interdire la suppression (`deletion`) et le push forcé (`non_fast_forward`);
- exiger une PR (`pull_request`), fusion par commit de fusion seulement (`allowed_merge_methods: ["merge"]`), aucune
    approbation requise (`required_approving_review_count: 0`), et le réglage par défaut
    `require_extra_approval_for_unattributed_changes: true`, sans effet ici: il ajoute une approbation à une PR que
    Copilot ouvre sans personne attribuée, et rien quand aucune n'est requise;
- exiger les contrôles `audit`, `tests`, `lint`, `types`, `tests-postgresql` et `bicep-build` (depuis #496), lus le
    2026-11-22, rendus par GitHub Actions (`integration_id` 15368), sur une branche à jour
    (`strict_required_status_checks_policy: true`).

```sh
gh api repos/SabineLaurent/K-B/rulesets --jq '.[] | "\(.id) \(.name) \(.target) \(.enforcement)"'
gh api repos/SabineLaurent/K-B/rulesets/25257125 --jq '{name, enforcement, bypass_actors, conditions, rules}'
```

Le 2026-11-14, la seconde commande rend les règles de la liste, et la première trois rulesets actifs: celui-ci,
25257125, et les deux des tags, « tags v » et « tags v immuables », qui servent la livraison
([la fiche de la livraison continue](livraison-continue.md)).

### Les réglages de Dependabot

Dans les réglages de sécurité du dépôt, activer les alertes et les mises à jour de sécurité. `dependabot.yml` règle
les mises à jour de version, qui ne touchent pas `uv.lock`: seule une mise à jour de sécurité peut ouvrir une PR sur
lui. Le graphe des dépendances du dépôt voit les paquets Python (96 le 2026-11-08).

```sh
gh api -i repos/SabineLaurent/K-B/vulnerability-alerts | head -1   # lu le 2026-11-14: HTTP/2.0 204 (alertes actives)
gh api repos/SabineLaurent/K-B/automated-security-fixes            # lu le 2026-11-14: {"enabled":true,"paused":false}
```

### GitHub Pages

Pour que `Docs` publie le site des fiches, GitHub Pages doit être activé sur le dépôt. Il ne l'est pas le 2026-11-14:

```sh
gh api -i repos/SabineLaurent/K-B/pages | head -1   # lu le 2026-11-14: HTTP/2.0 404 Not Found
```

Les gestes de la première publication, et pourquoi pas avant que le dépôt soit public, sont dans
[la section Publier de la fiche de l'accessibilité](accessibilite.md#publier).

### Sur le poste

Pour reproduire un job: l'environnement de développement de [la fiche de l'installation](installation.md),
uv 0.13.6 compris (`uv self update 0.13.6`), et, pour `tests-postgresql`, un serveur PostgreSQL
([la fiche des tests](tests.md)).

## Configurer la chaîne

Rien ne se règle hors du dépôt, en dehors des réglages d'[Installer la chaîne](#installer-la-chaine): aucun workflow de
la CI ne lit de secret, et seul `docs.yml` lit une variable du dépôt, `PAGES_PUBLISH`, qui ouvre la publication du
site à chaque push sur `main` (`.github/workflows/docs.yml:35`, `:44`).

### Ce qui se change, et où

Le tableau suivant donne chaque réglage de la chaîne, où il se trouve, et comment le changer.

| Réglage | Où | À changer avec |
|---|---|---|
| version de uv | `version:` des sept jobs de `ci.yml` et de `docs.yml:25`; `Dockerfile:7` | tous ensemble ([Le détail des réglages](#le-detail-des-reglages)) |
| version de pip-audit | `ci.yml:26` | à la main |
| image de PostgreSQL | `ci.yml:70`, tag et digest | à la main: d'après le commentaire de `ci.yml:64-65`, Dependabot ne la met pas à jour |
| chemins envoyés à la construction | `.dockerignore`, `Dockerfile` et la liste de `image.yml:35` | ensemble: un chemin de plus à la racine du contexte fait échouer l'étape 3 d'`Image` tant qu'il manque à la liste |
| version de Bicep | `infra.yml:22`, et son SHA256 à `infra.yml:24` | les deux ensemble, l'empreinte lue sur la release de Bicep |
| version de Grype | `image.yml:67` et `:70` (deux fois), et son SHA256 à `image.yml:71` | à la main, ensemble ([Le détail des réglages](#le-detail-des-reglages)) |
| version épinglée d'un paquet Debian | `Dockerfile:48-54` (zlib1g) | retirée par son issue, #647, quand l'image de base porte le correctif ([Une vulnérabilité dans l'image](#une-vulnerabilite-dans-limage), étape 3) |
| versions de MkDocs et de Material | `uv.lock`, groupe `docs` (`pyproject.toml:45-47`) | `uv lock --upgrade-package <paquet>`, puis la construction du site sur le poste |
| fichier de Mermaid attendu par `Docs` | son empreinte, `docs.yml:32` | à la main, après vérification ([Le détail des réglages](#le-detail-des-reglages)) |
| seuil de couverture | `fail_under`, `pyproject.toml:87` | une décision consignée au journal ADR (le seuil de 96 % date du 2026-11-08) |
| règles de lint | `[tool.ruff.lint]`, `pyproject.toml:52-71` | `uv run ruff check --no-cache` avant de pousser |
| tests écartés par défaut | marqueurs `e2e` et `postgresql`, écartés sauf s'ils sont nommés par `-m` (`tests/conftest.py:125-137`) | un test marqué `postgresql` ne tourne que dans `tests-postgresql` |
| contrôles requis à la fusion | le ruleset de `main` | un job nouveau n'est pas requis tant qu'il n'est pas ajouté au ruleset |
| fréquence et attente de Dependabot | `dependabot.yml` | à la main ([Le détail des réglages](#le-detail-des-reglages)) |

### Le détail des réglages

- **La version de uv**: les sept `version:` (six dans `ci.yml`, une dans `docs.yml`) et `Dockerfile:7` se changent
    ensemble, dans la plage `uv_build>=0.13.6,<0.14.0` de `pyproject.toml:31`. La PR de Dependabot ne change que le
    `Dockerfile`: les `version:` des workflows se changent à la main, dans la même PR.
- **La version de Grype**: `image.yml:67` et `:70` (deux fois), et son SHA256 à `image.yml:71`, se changent ensemble, à
    la main: la dernière version publiée depuis 7 jours au moins (la même attente que Dependabot, qui ne voit pas un
    binaire téléchargé), l'empreinte lue sur sa release (le digest de `grype_<version>_linux_amd64.tar.gz`) et
    recoupée avec `grype_<version>_checksums.txt`. La version est aussi écrite dans les pages qui la citent
    (`grep -rn "Grype v0" docs/fiches-veille.md documentation/`).
- **Le fichier de Mermaid**: le plugin `privacy` télécharge Mermaid depuis unpkg dans sa dernière version 11
    (`mermaid@11`), et un autre fichier que celui de Mermaid 11.17.2 arrête `build` (`docs.yml:29-32`). Avant de
    changer l'empreinte, vérifier le nouveau fichier contre l'intégrité que npm publie pour son paquet, comme le dit
    [la section Limites de la fiche de l'accessibilité](accessibilite.md#limites).
- **Dependabot**: chaque semaine, 7 jours d'attente pour une version nouvelle (`cooldown`, `dependabot.yml:8-9` et
    `:15-16`), sauf une mise à jour de sécurité (l. 9) et `astral-sh/uv`, dont ghcr.io ne donne pas la date, à vérifier
    à la main avant la fusion (l. 17-19). Pour `python` et `astral-sh/uv`, ni version mineure ni majeure (l. 24-28).

Une action nouvelle s'écrit par son SHA complet, sa version en commentaire: le dépôt refuse une action non épinglée
(`sha_pinning_required`).

## Tester la chaîne

### Chaque job sur le poste

Chaque job a son équivalent, à lancer depuis la racine du dépôt, sans `.env` exporté; ceux d'`image-build` et de
`bicep-build` ne refont qu'une partie du job. Le tableau suivant donne la commande de chaque job; celles d'`audit` et
de `build` sont écrites en entier après le tableau.

| Job | Commande locale |
|---|---|
| `audit` | `uv export`, puis `uvx pip-audit@2.10.1` (après le tableau) |
| `tests` | `uv run pytest --cov --cov-report=term-missing:skip-covered`, ou `make test-cov` |
| `lint` | `uv run ruff check --no-cache`, puis `uv run ruff format --check` |
| `types` | `uv run mypy --strict` |
| `tests-postgresql` | `KB_TEST_POSTGRESQL_URL=<URL d'un serveur> uv run pytest -m postgresql` |
| `tests-data` | `uv run pytest tests/etl tests/test_schema.py tests/test_items.py tests/ai_api/test_watch_items.py` |
| `image-build` | `docker buildx build --platform linux/amd64 --tag k-b .`, puis `docker run --rm k-b --help`; avec Grype installé, `grype docker:k-b --only-fixed --fail-on high` |
| `bicep-build` | `az bicep install --version v0.48.1`, puis `az bicep build --file infra/main.bicep --stdout > /dev/null`; sans le contrôle du SHA256 (`infra.yml:24`) |
| `build` de `Docs` | `uv run --locked --only-group docs mkdocs build --strict`, puis le contrôle de l'empreinte de Mermaid (après le tableau) |

Pour `audit`, la liste des versions s'écrit hors du dépôt, où git ne l'ignorerait pas:

```sh
uv export --frozen --no-emit-project --all-groups --format requirements-txt -o "${TMPDIR:-/tmp}/requirements-audit.txt"
uvx pip-audit@2.10.1 --require-hashes --disable-pip -r "${TMPDIR:-/tmp}/requirements-audit.txt"
```

Pour `image-build`, les autres étapes (`image.yml:24-82`) ne tournent que sur le runner: elles écrivent dans
`$RUNNER_TEMP` et plantent des fichiers dans l'arbre de travail. Leur résultat se lit dans le journal du job
(`gh run view <id> --log`).

Pour `build` de `Docs`, sur macOS, `shasum -a 256` remplace le `sha256sum` du runner:

```sh
uv run --locked --only-group docs mkdocs build --strict
echo "581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8  site/assets/external/unpkg.com/mermaid@11/dist/mermaid.min.js" | shasum -a 256 --check
```

### Une PR témoin

[La PR n° 533](https://github.com/SabineLaurent/K-B/pull/533), fusionnée le 2026-11-09, ne touche pas `infra/`. Elle a
reçu sept contrôles, tous verts (`gh pr checks 533 --repo SabineLaurent/K-B`): `audit` (13 s), `tests` (1 min 21 s),
`lint` (11 s), `types` (15 s), `tests-postgresql` (1 min 1 s), `tests-data` (30 s), dans l'exécution 42617081839 de
`CI`, et `image-build` (23 s), dans l'exécution 42617082007 d'`Image`; `bicep-build` n'y a pas tourné. Depuis, toute
PR reçoit aussi `bicep-build` (#496), les deux jobs de `Docs` (#167), `build` et `deploy`, sauté, et
`digests-reference`, ajouté à `CI` le 2026-11-20 (`63d22175`): onze contrôles ([Lancer la CI](#lancer-la-ci)).

### Un push témoin

La fusion `89ef7fb` sur `main`, le 2026-11-10, a lancé `CI` (42815479408) et `Image` (42815479369), toutes deux
`success`; `Infra` n'y a pas tourné, `infra/` n'ayant pas changé, avant #496, qui le lance sur tout push sur `main`.
La dernière exécution d'`Infra` sur `main` était alors 42750689052, `success`, sur `cad8328` (2026-11-10).

### Un refus témoin

L'exécution 41215069368 de `CI`, sur la PR de la branche `feat/trend-report-github-cards` (2026-10-31), a eu `audit`
en échec, et ses trois autres jobs (`tests`, `lint`, `types`) verts. Son journal
(`gh run view 41215069368 --repo SabineLaurent/K-B --log-failed`) donne `Found 4 known vulnerabilities in 1 package`,
puis `pyasn1 0.6.4`, quatre CVE (<span lang="en">Common Vulnerabilities and Exposures</span>, l'identifiant public d'une vulnérabilité) et la version corrigée, `0.6.5`. Ce journal se relit jusque vers le 2027-01-29.

## Quand la CI échoue

### Lire le job en échec

Lire d'abord le job en échec et ses dernières lignes:

```sh
gh pr checks <n° de la PR> --repo SabineLaurent/K-B          # quel job
gh run view <id> --repo SabineLaurent/K-B --log-failed       # ses lignes, étape par étape
```

Puis reproduire le job sur le poste ([Chaque job sur le poste](#chaque-job-sur-le-poste)), corriger, pousser un
commit.

### Les échecs, job par job

Le tableau suivant donne, pour chaque job en échec, ce qu'il a vu et quoi faire.

| Job en échec | Ce qu'il a vu | Quoi faire |
|---|---|---|
| `uv sync --locked`, dans tout job | `uv.lock` ne suit plus `pyproject.toml` | `uv lock`, puis committer `uv.lock` |
| `audit` | une version de `uv.lock` a une vulnérabilité connue: le paquet, sa version, l'identifiant et la version corrigée | monter le paquet (`uv lock --upgrade-package <paquet>`), relancer `audit` en local |
| `tests` | un test en échec, ou le seuil manqué (`Required test coverage of … not reached. Total coverage: …`) | lancer le test seul (`uv run pytest <chemin>::<test>`), ou `make test-cov` pour les lignes non couvertes |
| `lint` | une règle de ruff, ou un fichier à reformater | `uv run ruff check --no-cache`, `uv run ruff format` |
| `types` | une erreur de mypy, avec son fichier et sa ligne | `uv run mypy --strict` |
| `tests-postgresql` | un test en échec, ou le service qui ne démarre pas (`pg_isready` en échec 15 fois, 2 s d'écart, 5 s de délai chacune, `ci.yml:79-83`) | relancer le job; puis le test sur un serveur local |
| `tests-data` | un test des données en échec | le même test, sur le poste |
| `image-build` | l'étape en échec dit le contrôle: un fichier planté trouvé (son chemin), l'utilisateur root, un code de sortie inattendu, ou, pour le scan (étape 10), le tableau des vulnérabilités hautes ou critiques qui ont un correctif: le paquet, sa version, la version corrigée, son type, l'identifiant et la sévérité | `docker buildx build` en local, puis la commande de l'étape; pour le scan, la section [Une vulnérabilité dans l'image](#une-vulnerabilite-dans-limage) |
| `bicep-build` | une erreur de compilation, avec son fichier et sa ligne, ou une empreinte de Bicep différente (`sha256sum: WARNING`) | `az bicep build --file infra/main.bicep` en local; pour l'empreinte, vérifier la version et le SHA256 ensemble |
| `build` de `Docs` | un avertissement du mode strict, qui nomme le fichier et le lien ou l'ancre; ou un autre fichier de Mermaid (`sha256sum: WARNING`) | la construction en local; pour Mermaid, [Le détail des réglages](#le-detail-des-reglages) |

Un échec du runner ou du réseau (téléchargement de uv, de pip-audit, de l'image `postgres`, de Grype ou de sa base)
se relance tel quel.

### Une vulnérabilité dans l'image

C'est l'étape 10 d'`image-build`. Le ruleset n'exige pas ce contrôle à la fusion; la mise en ligne, elle, refuse le
tag d'un commit dont un workflow a échoué (`deploy.yml:51-67`).
Dans cet ordre:

1. Un paquet Python de l'environnement virtuel (type `python`, sous `/app/.venv`): `audit` échoue aussi. Monter le
    paquet dans `uv.lock` (ligne `audit` du tableau).
2. Un paquet Debian (type `deb`), CPython (type `binary`) ou un paquet Python de l'image de base (type `python`, sous
    `/usr/local/lib/python3.13`, `pip` notamment, hors d'`uv.lock` et que `audit` ne voit pas), quand l'image amont a
    déjà le correctif: monter à la main le digest des deux `FROM python:3.13-slim-trixie@sha256:…` du `Dockerfile`
    (l. 10 et 27), dans une PR, sans attendre la PR hebdomadaire de Dependabot. Le digest du jour se lit par
    `docker buildx imagetools inspect python:3.13-slim-trixie` (ligne `Digest:`); le scan de la PR dit si le
    correctif y est.
3. Un paquet Debian dont la version corrigée s'installe depuis les sources d'APT de l'image (l'archive de sécurité,
    `trixie-security`, pour un avis DSA) mais n'est pas encore dans l'image amont: l'installer dans l'étape finale du
    `Dockerfile`, avant `USER`, à la version corrigée écrite en entier
    (`apt-get install --yes --no-install-recommends <paquet>=<version>`), avec une issue qui retire le bloc dès que
    l'étape 2 apporte le correctif. La version corrigée se lit sur la page de l'avis du
    [suivi de sécurité de Debian](https://security-tracker.debian.org/tracker/) (ligne `trixie (security)`). Fait
    pour zlib1g le 2026-11-18 (`Dockerfile:48-54`, retiré par #647).
4. Sinon, aucune des étapes 1 à 3 ne s'appliquant (par exemple un paquet Debian dont le correctif est encore dans
    `trixie-proposed-updates`, que `apt-get install` ne trouve pas, ou un CPython corrigé que l'image amont n'a pas
    encore): une entrée dans `.grype.yaml`, à la racine du dépôt, le premier fichier de réglages que Grype cherche
    dans le dossier où il tourne. Chaque entrée est décidée par Sabine (« Une règle non tenue l'est par décision
    écrite », `.claude/rules/conformite.md`), avec sa raison, sa date et l'issue qui la retire dès que l'étape 2 ou 3
    apporte le correctif:

```yaml
ignore:
  - vulnerability: CVE-AAAA-NNNNN
    package:
      name: <paquet>
    reason: "<pourquoi l'accepter>, décidé par Sabine le AAAA-MM-JJ, retiré par #<issue>"
```

Le fichier n'existe pas tant qu'aucune entrée n'est décidée; `.dockerignore` le tient hors de l'image. Écarté:
`apt-get upgrade` dans le `Dockerfile`, qui ferait dépendre l'image du jour de sa construction, et non plus du digest
épinglé. L'étape 3 n'installe qu'un paquet, à une version écrite: elle révise le 2026-11-18, pour ce seul cas, la
décision du 2026-11-14 (décision de Sabine, journal ADR).

## Limites

Lues le 2026-11-10; le workflow `Docs`, les réglages du dépôt et le scan de l'image (#498), le 2026-11-14. Chaque
parade a été vérifiée à la source le 2026-11-10, celles de #498 le 2026-11-14 (sources en fin de liste).

- **Aucune relecture n'est exigée**: le ruleset demande une PR, mais aucune approbation
    (`required_approving_review_count: 0`). La relecture en PR est une pratique, pas une règle.
    Pour réduire le risque: exiger une approbation dans le ruleset serait faisable avec nos droits (administratrice du
    dépôt), mais <q lang="en">Pull request authors cannot approve their own pull requests</q>: avec une seule
    personne au dépôt et aucun contournement, plus aucune PR ouverte sous son compte ne fusionnerait; seules celles de
    Dependabot, d'un autre auteur, le pourraient. Ce n'est donc pas faisable sans une seconde personne.
- **Quatre contrôles ne bloquent pas la fusion**: `tests-data`, `digests-reference`, `image-build` et `build` de
    `Docs` ne sont pas dans le ruleset, lu le 2026-11-22. Tous comptent à la livraison (`deploy.yml:51-67`).
    `bicep-build` y est depuis #496: ni `infra.yml` ni `image.yml` n'ont de filtre de chemin, car un workflow sauté par son filtre laisse ses contrôles
    « <span lang="en">Pending</span> » et bloque la fusion.
    Pour réduire le risque: ajouter ces quatre contrôles aux contrôles requis du ruleset (faisable avec nos droits).
- **Les tests de bout en bout ne tournent pas en CI**: les tests marqués `e2e` appellent les vraies sources et
    services; ils se lancent sur le poste ([la fiche des tests](tests.md)).
    Pour réduire le risque: un workflow planifié (`on: schedule`, sur la branche par défaut) lancerait
    `pytest -m e2e`. C'est faisable avec nos droits, les clés des sources en secrets du dépôt, mais pas pour tout: les
    tests de Zotero et des clips lisent des fichiers du poste et seraient sautés. Le prix: des appels réels, dont une
    vraie requête BigQuery pour `gh_archive`, et des clés de plus dans GitHub. Le dépôt est privé
    (`gh api repos/SabineLaurent/K-B` → `"visibility":"private"`): un workflow planifié y prend sur l'usage inclus du
    compte, compté en montant; au-delà, il est payé s'il y a un moyen de paiement, dans la limite des budgets, et
    bloqué sinon. Public, il serait gratuit, mais coupé après 60 jours sans activité.
- **Le scan ne voit pas tout** (#498, lu le 2026-11-14): avec `--only-fixed`, une vulnérabilité sans correctif ne
    le fait pas échouer et n'est pas listée; une vulnérabilité publiée après la dernière exécution d'`Image` sur `main`
    n'est vue qu'à la PR suivante: l'image en ligne, que `deploy.yml` reconstruit au tag (l. 102-117) sans la scanner,
    peut la porter d'ici là. Une bibliothèque compilée dans un module d'une wheel n'est vue ni par apt ni par le scan:
    grpcio 1.84.0 compile sa propre zlib dans `cygrpc.so`, dans la plage de CVE-2026-85091 (zlib 1.2.11 à 1.3.2),
    mais sans `gzwrite.c`, où est le code fautif `gz_write`: son `setup.py` compile la liste de
    `grpc_core_dependencies.py`, qui ne compte que 11 fichiers de zlib, aucun `gz*.c` (l. 1562-1572 au tag v1.84.0,
    lu le 2026-11-18).
    Pour réduire le risque: Dependabot propose chaque semaine le nouveau digest des images de base du `Dockerfile`
    (`dependabot.yml:10-16`), qui apporte les correctifs de Debian et de CPython, et la CI le scanne (déjà fait). Le
    même scan dans `deploy.yml`, avant la mise en ligne (#626): faisable avec nos droits. Un déclenchement planifié
    d'`image.yml` (`on: schedule`, sur la branche par défaut) scannerait `main` sans attendre une PR: faisable avec nos
    droits, sur l'usage inclus du compte tant que le dépôt est privé (`"visibility":"private"`, lu le 2026-11-14).
- **Une vulnérabilité publiée rend rouges toutes les PR** (#498): une vulnérabilité haute ou critique corrigée qui
    entre dans la base de Grype rend rouge `image-build` sur toute PR, comme `audit` le 2026-11-13 (#606), et bloque la
    mise en ligne, jusqu'à la montée du digest, l'installation du paquet corrigé ou une entrée de `.grype.yaml`.
    Pour réduire le risque: la marche à suivre est écrite ([Une vulnérabilité dans l'image](#une-vulnerabilite-dans-limage));
    faisable avec nos droits, une PR suffit.
- **Une version épinglée de Debian fait échouer la construction de l'image quand l'archive de sécurité la remplace**
    (#498, 2026-11-18): l'index de `trixie-security`, lu le 2026-11-18, ne porte qu'une version de zlib1g, la
    `+deb13u1` qu'installe le `Dockerfile` (l. 48-54). Quand une `+deb13u2` la remplacera, `apt-get install` ne
    trouvera plus la version écrite: `image-build` et la construction de `deploy.yml` échoueront, jusqu'à une PR.
    Pour réduire le risque: #647 retire le bloc dès qu'un digest de l'image de base porte le correctif. Le scan ne le
    dit pas, vert tant que le bloc est là: `docker run --rm python:3.13-slim-trixie@sha256:<digest> dpkg-query -W zlib1g`
    le dit, sur le digest de chaque PR de Dependabot. Faisable avec nos droits, par une PR.
- **Grype v0.121.3 porte un avis que v0.122.0 corrige** (lu le 2026-11-18): GHSA-q7gw-24fr-5p69 (moyen), dans le
    SDK OpenTelemetry pour Go que Grype embarque: la borne de longueur d'un attribut de trace ou de journal ne coupe
    pas une valeur faite du caractère U+FFFD. Le job ne règle aucune variable `OTEL_*` (`image.yml`); que Grype
    n'exporte alors aucune trace, et que l'avis ne change pas le résultat du scan, est une hypothèse, non vérifiée
    dans son code. v0.122.0, publiée le 2026-11-16 à 20:41 UTC, n'a pas encore les 7 jours
    d'attente que se donne la CI.
    Pour réduire le risque: monter Grype à v0.122.0 après le 2026-11-23 à 20:41 UTC
    ([Le détail des réglages](#le-detail-des-reglages), version de Grype); faisable avec nos droits, par une PR.
- **Aucun délai propre aux jobs**: aucun `timeout-minutes` dans `ci.yml`, `image.yml`, `infra.yml` ni `docs.yml`; le
    délai par défaut de GitHub s'applique, 360 minutes par job, prises sur l'usage inclus du compte tant que le
    dépôt est privé.
    Pour réduire le risque: un `timeout-minutes` par job, à quelques fois sa durée observée (1 min 21 s au plus sur
    la PR n° 533). Faisable avec nos droits, par un changement des workflows.
- **Une PR vers une autre branche que `main`** ne lance aucune CI.
    Pour réduire le risque: rien n'entre dans `main` sans une PR vers `main` (règle `pull_request` du ruleset), qui
    lance la CI et attend ses six contrôles requis. Retirer `branches: [main]` du `pull_request` de chaque workflow
    lancerait aussi la CI sur les autres PR (faisable avec nos droits).

Sources, lues le 2026-11-10: GitHub Docs,
[« <span lang="en">Approving a pull request with required reviews</span> »](https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/approving-a-pull-request-with-required-reviews),
[« <span lang="en">Troubleshooting required status checks</span> »](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)
(« <span lang="en">Handling skipped but required checks</span> »),
[« <span lang="en">Events that trigger workflows</span> »](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
(`schedule`),
[« <span lang="en">Workflow syntax</span> »](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
(`jobs.<job_id>.timeout-minutes`),
[« <span lang="en">Re-running workflows and jobs</span> »](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)
(30 jours), [« <span lang="en">GitHub Actions billing</span> »](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
(dépôt privé) et
[« <span lang="en">Available rules for rulesets</span> »](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)
(Copilot); le dépôt [anchore/scan-action](https://github.com/anchore/scan-action), son
`action.yml` et sa dernière release, v7.4.2 (2026-08-28).

Sources de #498, lues le 2026-11-14: les releases de Grype,
[v0.121.3](https://github.com/anchore/grype/releases/tag/v0.121.3) (les avis qu'elle corrige, lus sur GitHub et
[OSV](https://osv.dev/); le 2026-11-18, le digest de `grype_0.121.3_linux_amd64.tar.gz`, recoupé avec
`grype_0.121.3_checksums.txt`) et [v0.122.0](https://github.com/anchore/grype/releases/tag/v0.122.0) (l'avis
qu'elle corrige, [GHSA-q7gw-24fr-5p69](https://github.com/advisories/GHSA-q7gw-24fr-5p69), lu le 2026-11-18); la [référence des réglages de Grype](https://oss.anchore.com/docs/reference/grype/configuration/)
(ordre de recherche de `.grype.yaml`, `db.max-allowed-built-age` à 120 h, `check-for-app-update`, règles `ignore` et
`reason`); Context7 `/anchore/grype` (`--only-fixed`, `--fail-on`); GitHub Docs,
[« Events that trigger workflows »](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
(`schedule`: « Scheduled workflows run on the latest commit on the default branch »). Le 2026-11-18, pour zlib1g:
le suivi de sécurité de Debian, [DSA-6613-1](https://security-tracker.debian.org/tracker/DSA-6613-1) et
[CVE-2026-85091](https://security-tracker.debian.org/tracker/CVE-2026-85091) (versions touchées, version corrigée de
trixie), l'index `Packages.xz` de `trixie-security` pour amd64 (une seule version de zlib1g), et, pour grpcio, son
[`setup.py`](https://github.com/grpc/grpc/blob/v1.84.0/setup.py) et
[`grpc_core_dependencies.py`](https://github.com/grpc/grpc/blob/v1.84.0/src/python/grpcio/grpc_core_dependencies.py)
au tag v1.84.0.
