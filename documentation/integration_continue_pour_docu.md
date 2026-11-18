# L'intégration continue de K-B

« Documentation des procédures d'installation et de test de la chaîne. » — C18

« Documentation utilisateur, pour le déclenchement de la chaîne. » — C18

Cette fiche dit ce que fait la chaîne d'intégration continue (CI) de K-B, comment on la déclenche et la relance,
comment elle s'installe, se configure et se teste, et que faire quand elle échoue. Elle est écrite d'après le code de
`main` au commit `57ff235` (2026-11-14), avec le workflow `Docs` et l'audit de tous les groupes de dépendances ajoutés
le même jour (#167), et d'après les réglages du dépôt lus le même jour. Les exécutions citées se relisent
par `gh run view <id> --repo SabineLaurent/K-B`, 90 jours au plus: c'est la durée de garde des journaux du dépôt
(`gh api repos/SabineLaurent/K-B/actions/permissions/artifact-and-log-retention` → `"days":90`). La mise en ligne
d'une version, qui suit la CI, est dans [la fiche de la livraison continue](livraison_continue_pour_docu.md).

## La chaîne en bref

Chaque demande de fusion (PR, <span lang="en">pull request</span>) vers `main`, et chaque push sur `main` (donc chaque fusion), lance la CI. Elle vérifie le code (tests,
couverture, lint, format, typage), ses dépendances (vulnérabilités connues), l'image du conteneur et le Bicep. Sur
chaque PR, elle construit aussi le site des fiches de `documentation/` ([Le workflow `Docs`](#le-workflow-docs)). Une
PR ne fusionne que si ses six contrôles requis sont verts sur une branche à jour avec `main`
([Le ruleset de `main`](#le-ruleset-de-main)). La CI ne pousse rien et ne déploie rien sur Azure, où elle n'a aucun
droit. Seul `Docs`, lancé à la main depuis `main`, publie quelque chose: le site des fiches, sur GitHub Pages.

### Les outils

| Outil | Rôle dans la chaîne | Où il est réglé |
|---|---|---|
| GitHub Actions | lance les workflows sur des runners `ubuntu-latest`; chaque action est épinglée par son SHA, sa version en commentaire | `.github/workflows/ci.yml`, `image.yml`, `infra.yml`, `docs.yml` |
| uv 0.13.6 | installe Python 3.13 (`.python-version`) et les dépendances de `uv.lock` (`uv sync --locked`), lance chaque outil (`uv run`) | `ci.yml`, `version: "0.13.6"` dans chacun des six jobs (l. 20, 34, 46, 58, 90, 106); `docs.yml:22` |
| pytest et pytest-cov | lancent les tests et mesurent la couverture des lignes et des branches de `src/k_b/` | `pyproject.toml`, `[tool.coverage.*]` (l. 76-89) |
| ruff | lint et format du Python | `pyproject.toml`, `[tool.ruff.*]` (l. 52-71) |
| mypy | typage, en mode `--strict` | `ci.yml:61`, `pyproject.toml:73-74` |
| pip-audit 2.10.1 | cherche les vulnérabilités connues des versions de `uv.lock`, de tous les groupes de dépendances, avec leurs empreintes | `ci.yml:25-26` |
| PostgreSQL 18.6 | un service du job `tests-postgresql`, épinglé par son digest | `ci.yml:69-83` |
| Docker Buildx | construit l'image `linux/amd64` de K-B et la contrôle | `image.yml` |
| Azure CLI et Bicep v0.48.1 | compile `infra/main.bicep`, sans connexion à Azure | `infra.yml` |
| MkDocs 1.6.1, avec Material for MkDocs 9.8.1 | construit le site des fiches de `documentation/`, en mode strict | `mkdocs.yml`; versions dans `uv.lock`, groupe `docs` (`pyproject.toml:45-47`) |
| Dependabot | ouvre chaque semaine les PR de mise à jour des actions et des images de base du `Dockerfile` | `.github/dependabot.yml` |
| Ruleset « Basic-rules-main-protect » | dit quels contrôles une PR doit passer pour fusionner | réglages du dépôt ([Le ruleset de `main`](#le-ruleset-de-main)) |

Les actions épinglées sont `actions/checkout` v7.0.1 et `astral-sh/setup-uv` v10.3.3 dans les workflows, et en plus,
dans `docs.yml`, `actions/upload-pages-artifact` v5.0.0 et `actions/deploy-pages` v5.0.1 (`docs.yml:31`, `:49`).

La chaîne tourne sur GitHub Actions, et ces faits l'y attachent: le dépôt est sur GitHub (`git remote get-url origin`
→ `git@github.com:SabineLaurent/K-B.git`); son ruleset exige des contrôles rendus par GitHub Actions (`integration_id`
15368, l'identifiant de l'application `github-actions` d'après `gh api apps/github-actions`); Dependabot met à jour les
actions épinglées et leur commentaire de version (`.github/dependabot.yml:3-9`); le dépôt exige le SHA complet de
chaque action (`sha_pinning_required`, `gh api repos/SabineLaurent/K-B/actions/permissions`).

### Les déclencheurs

| Déclencheur | Ce qui tourne |
|---|---|
| une PR vers `main`: ouverte, rouverte, ou un commit poussé sur sa branche | `CI`, `Image`, `Infra` et `Docs` (`ci.yml:3-7`, `image.yml:3-7`, `infra.yml:3-7`, `docs.yml:6-8`); `Infra` sans filtre de chemin depuis #496 |
| un push sur `main`, c'est-à-dire une fusion | `CI`, `Image` et `Infra`, sur le commit de fusion (`ci.yml:4-5`, `image.yml:4-5`, `infra.yml:4-5`); pas `Docs`, qui n'a pas de déclencheur `push` (`docs.yml:6-9`) |
| un lancement de `Docs` à la main (`workflow_dispatch`, `docs.yml:9`), sur une branche choisie | `Docs` seul; il ne publie le site que lancé depuis `main` (`docs.yml:30`, `:37`) |
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
`deploy` de `Docs` attend son `build` (`needs`, `docs.yml:38`). Dans un job, les étapes s'enchaînent, et la première
qui échoue arrête le job. Chaque workflow n'a qu'un jeton qui lit le dépôt (`permissions: contents: read`,
`ci.yml:9-10`, `image.yml:9-10`, `infra.yml:9-10`, `docs.yml:11-12`), et aucun ne lit de secret. Seul le job `deploy`
de `Docs` a ses propres droits, `pages: write` et `id-token: write` (`docs.yml:41-43`), pour publier sur GitHub Pages.

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

Depuis #167, `audit` lit aussi le groupe `docs`, MkDocs et Material (`pyproject.toml:45-47`), que `uv export` laisse
de côté sans `--all-groups` (`ci.yml:23-25`). Le 2026-11-14, `uv export --frozen --no-emit-project` sans l'option ne
liste ni `mkdocs` ni `mkdocs-material`, mais liste `pytest` et `mypy`, du groupe `dev`; avec l'option, il liste
`mkdocs==1.6.1` et `mkdocs-material==9.8.1`. Une vulnérabilité connue de MkDocs ou de Material fait donc échouer
`audit` sur chaque PR.

#### Le workflow `Image`

`.github/workflows/image.yml`, un job, `image-build`, non requis à la fusion. Le tableau suivant donne ses étapes dans
l'ordre, et ce que fait chacune; une étape sans nom dans `image.yml` y est décrite en français.

| # | Étape (lignes d'`image.yml`) | Ce qu'elle fait |
|---|---|---|
| 1 | Récupérer le dépôt (l. 18) | `actions/checkout`, `.git` compris |
| 2 | Planter des fichiers à écarter (l. 22-26) | crée des fichiers que `.dockerignore` doit écarter du contexte de construction, nommés après le tableau |
| 3 | `Sends only what the Dockerfile copies to the build` (l. 29-35) | vérifie que le contexte de construction ne contient, à sa racine, que `README.md`, `pyproject.toml`, `src` et `uv.lock` (l. 33), et nulle part un fichier planté ni un `__pycache__` (l. 34) |
| 4 | Construire l'image (l. 36) | `docker buildx build --platform linux/amd64 --tag k-b:ci .` |
| 5 | `Runs as a non-root user` (l. 37-41) | vérifie que l'utilisateur de l'image n'est pas root (`id -u` différent de 0) |
| 6 | `Holds none of the planted files` (l. 43-46) | vérifie qu'aucun chemin de l'image ne s'appelle `.env*`, `*.sqlite*`, `decoy`, `.DS_Store` ni `.git` (l. 45); `__pycache__` n'est cherché que dans le contexte (étape 3) |
| 7 | `Refuses to start without KB_DATA_DIR` (l. 49-55) | vérifie que `kb create-db` sans `KB_DATA_DIR` sort en code 2 avec `KB_DATA_DIR must point to the data directory` |
| 8 | `Starts kb and creates the database` (l. 58-61) | lance `kb --help`, puis `kb create-db` dans le dossier de données de l'image |

Les fichiers plantés à l'étape 2 sont, à la racine, `.env`, `.env.decoy`, `temp/decoy`, `reports/decoy` et
`.venv/decoy`, et dans `src/k_b/`, `.env.decoy`, `decoy.sqlite`, `decoy.sqlite-wal`, `.DS_Store` et
`__pycache__/decoy.pyc` (l. 23-26).

L'image `k-b:ci` n'est poussée nulle part: celle qui part en ligne est construite par `Deploy`, depuis le commit du
tag.

#### Le workflow `Infra`

`.github/workflows/infra.yml`, un job, `bicep-build`, requis à la fusion depuis #496: il récupère le dépôt (l. 19),
demande à `az` d'utiliser son propre Bicep (l. 21), installe Bicep v0.48.1 (l. 22), vérifie son SHA256 (l. 24),
affiche sa version (l. 25), puis compile `infra/main.bicep` (l. 26). Il ne se connecte pas à Azure: Sabine applique le
Bicep à la main (`infra/README.md`).

#### Le workflow `Docs`

`.github/workflows/docs.yml`, ajouté avec #167, deux jobs, aucun requis à la fusion (ruleset lu le 2026-11-14). Il
tourne sur chaque PR vers `main` et quand on le lance à la main (`workflow_dispatch`), jamais sur un push sur `main`
(`docs.yml:6-9`).

- `build` (l. 16-33) récupère le dépôt (l. 19) et installe uv 0.13.6, sans enregistrer le cache (l. 20-23). Il
  construit le site par `uv run --locked --only-group docs mkdocs build --strict` (l. 24-25): le groupe `docs` seul, aux
  versions de `uv.lock`, sans K-B ni ses outils de développement. En mode strict, un lien vers un fichier absent, une
  ancre absente ou une fiche oubliée dans la navigation fait échouer la construction (`mkdocs.yml:43-49`). Puis
  `sha256sum --check` compare le fichier de Mermaid que le plugin `privacy` a téléchargé depuis unpkg, dans sa version
  11 qui bouge (`mermaid@11`), à l'empreinte du fichier de Mermaid 11.17.2 (l. 26-29). Lancé à la main depuis
  `main`, il dépose enfin `site/` en artefact de Pages (l. 30-33), que `deploy` publie.
- `deploy` (l. 35-49) ne tourne que lancé à la main depuis `main` (l. 37), après `build` (l. 38). Il a les droits
  `pages: write` et `id-token: write` (l. 41-43), dans l'environnement `github-pages` (l. 44-46), et publie le site
  par `actions/deploy-pages` (l. 48-49).

Sur une PR, `deploy` est donc sauté. GitHub Pages n'est pas activé sur le dépôt le 2026-11-14:
voir [GitHub Pages](#github-pages).

#### Après la CI

`Deploy` ne met en ligne qu'un commit dont toutes les exécutions des workflows du dépôt sont finies et vertes, `Image`
et `Infra` comprises (`deploy.yml:51-67`). Un contrôle non requis à la fusion compte donc à la livraison.

`Docs` compte aussi. Sur un commit de `main`, il ne tourne que lancé à la main (`docs.yml:6-9`), et une telle
exécution en échec, ou pas encore finie, fait refuser le tag de ce commit. Pour livrer ce commit malgré tout, relancer
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

Une PR reçoit neuf contrôles: les six jobs de `CI`, `image-build`, `bicep-build`, que `infra.yml` lance sur toute PR
depuis #496, qu'elle touche `infra/` ou non, et `build` de `Docs`. Le job `deploy` de `Docs` est sauté sur une PR
(`docs.yml:37`). Que GitHub le liste parmi les contrôles, comme sauté, n'est pas vérifié: le 2026-11-14, `Docs` ne
figure pas encore dans la liste des workflows du dépôt (`gh api repos/SabineLaurent/K-B/actions/workflows`).

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
- exiger les contrôles `audit`, `tests`, `lint`, `types`, `tests-postgresql` et `bicep-build`, rendus par GitHub
  Actions (`integration_id` 15368), sur une branche à jour (`strict_required_status_checks_policy: true`).

```sh
gh api repos/SabineLaurent/K-B/rulesets --jq '.[] | "\(.id) \(.name) \(.target) \(.enforcement)"'
gh api repos/SabineLaurent/K-B/rulesets/25257125 --jq '{name, enforcement, bypass_actors, conditions, rules}'
```

Le 2026-11-14, la seconde commande rend les règles de la liste, et la première trois rulesets actifs: celui-ci,
25257125, et les deux des tags, « tags v » et « tags v immuables », qui servent la livraison
([la fiche de la livraison continue](livraison_continue_pour_docu.md)).

### Les réglages de Dependabot

Dans les réglages de sécurité du dépôt, activer les alertes et les mises à jour de sécurité. `dependabot.yml` règle
les mises à jour de version.

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
[la section Publier de la fiche de l'accessibilité](accessibilite_pour_docu.md#publier).

### Sur le poste

Pour reproduire un job: l'environnement de développement de [la fiche de l'installation](installation_pour_docu.md),
uv 0.13.6 compris (`uv self update 0.13.6`), et, pour `tests-postgresql`, un serveur PostgreSQL
([la fiche des tests](tests_pour_docu.md)).

## Configurer la chaîne

Rien ne se règle hors du dépôt, en dehors des réglages d'[Installer la chaîne](#installer-la-chaine): aucun workflow de
la CI ne lit de variable (`vars.`) ni de secret.

### Ce qui se change, et où

Le tableau suivant donne chaque réglage de la chaîne, où il se trouve, et comment le changer.

| Réglage | Où | À changer avec |
|---|---|---|
| version de uv | `version:` des six jobs de `ci.yml` et de `docs.yml:22`; `Dockerfile:7` | tous ensemble ([Le détail des réglages](#le-detail-des-reglages)) |
| version de pip-audit | `ci.yml:26` | à la main |
| image de PostgreSQL | `ci.yml:70`, tag et digest | à la main: d'après le commentaire de `ci.yml:64-65`, Dependabot ne la met pas à jour |
| chemins envoyés à la construction | `.dockerignore`, `Dockerfile` et la liste de `image.yml:33` | ensemble: un chemin de plus à la racine du contexte fait échouer l'étape 3 d'`Image` tant qu'il manque à la liste |
| version de Bicep | `infra.yml:22`, et son SHA256 à `infra.yml:24` | les deux ensemble, l'empreinte lue sur la release de Bicep |
| versions de MkDocs et de Material | `uv.lock`, groupe `docs` (`pyproject.toml:45-47`) | `uv lock --upgrade-package <paquet>`, puis la construction du site sur le poste |
| fichier de Mermaid attendu par `Docs` | son empreinte, `docs.yml:29` | à la main, après vérification ([Le détail des réglages](#le-detail-des-reglages)) |
| seuil de couverture | `fail_under`, `pyproject.toml:87` | une décision consignée au journal ADR (le seuil de 96 % date du 2026-11-08) |
| règles de lint | `[tool.ruff.lint]`, `pyproject.toml:52-71` | `uv run ruff check --no-cache` avant de pousser |
| tests écartés par défaut | marqueurs `e2e` et `postgresql`, écartés sauf s'ils sont nommés par `-m` (`tests/conftest.py:125-137`) | un test marqué `postgresql` ne tourne que dans `tests-postgresql` |
| contrôles requis à la fusion | le ruleset de `main` | un job nouveau n'est pas requis tant qu'il n'est pas ajouté au ruleset |
| fréquence et attente de Dependabot | `dependabot.yml` | à la main ([Le détail des réglages](#le-detail-des-reglages)) |

### Le détail des réglages

- **La version de uv**: les sept `version:` (six dans `ci.yml`, une dans `docs.yml`) et `Dockerfile:7` se changent
  ensemble, dans la plage `uv_build>=0.13.6,<0.14.0` de `pyproject.toml:31`. La PR de Dependabot ne change que le
  `Dockerfile`: les `version:` des workflows se changent à la main, dans la même PR.
- **Le fichier de Mermaid**: le plugin `privacy` télécharge Mermaid depuis unpkg dans sa dernière version 11
  (`mermaid@11`), et un autre fichier que celui de Mermaid 11.17.2 arrête `build` (`docs.yml:26-29`). Avant de
  changer l'empreinte, vérifier le nouveau fichier contre l'intégrité que npm publie pour son paquet, comme le dit
  [la section Limites de la fiche de l'accessibilité](accessibilite_pour_docu.md#limites).
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
| `image-build` | `docker buildx build --platform linux/amd64 --tag k-b .`, puis `docker run --rm k-b --help` |
| `bicep-build` | `az bicep install --version v0.48.1`, puis `az bicep build --file infra/main.bicep --stdout > /dev/null`; sans le contrôle du SHA256 (`infra.yml:24`) |
| `build` de `Docs` | `uv run --only-group docs mkdocs build --strict`, puis le contrôle de l'empreinte de Mermaid (après le tableau) |

Pour `audit`, la liste des versions s'écrit hors du dépôt, où git ne l'ignorerait pas:

```sh
uv export --frozen --no-emit-project --all-groups --format requirements-txt -o "${TMPDIR:-/tmp}/requirements-audit.txt"
uvx pip-audit@2.10.1 --require-hashes --disable-pip -r "${TMPDIR:-/tmp}/requirements-audit.txt"
```

Pour `image-build`, les autres étapes (`image.yml:22-61`) ne tournent que sur le runner: elles écrivent dans
`$RUNNER_TEMP` et plantent des fichiers dans l'arbre de travail. Leur résultat se lit dans le journal du job
(`gh run view <id> --log`).

Pour `build` de `Docs`, sur macOS, `shasum -a 256` remplace le `sha256sum` du runner:

```sh
uv run --only-group docs mkdocs build --strict
echo "581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8  site/assets/external/unpkg.com/mermaid@11/dist/mermaid.min.js" | shasum -a 256 --check
```

### Une PR témoin

[La PR n° 533](https://github.com/SabineLaurent/K-B/pull/533), fusionnée le 2026-11-09, ne touche pas `infra/`. Elle a
reçu sept contrôles, tous verts (`gh pr checks 533 --repo SabineLaurent/K-B`): `audit` (13 s), `tests` (1 min 21 s),
`lint` (11 s), `types` (15 s), `tests-postgresql` (1 min 1 s), `tests-data` (30 s), dans l'exécution 42617081839 de
`CI`, et `image-build` (23 s), dans l'exécution 42617082007 d'`Image`; `bicep-build` n'y a pas tourné. Depuis #496,
toute PR reçoit aussi `bicep-build`, un huitième contrôle, et avec `Docs` (#167), `build`, un neuvième.

### Un push témoin

La fusion `89ef7fb` sur `main`, le 2026-11-10, a lancé `CI` (42815479408) et `Image` (42815479369), toutes deux
`success`; `Infra` n'y a pas tourné, `infra/` n'ayant pas changé, avant #496, qui le lance sur tout push sur `main`.
La dernière exécution d'`Infra` sur `main` était alors 42750689052, `success`, sur `cad8328` (2026-11-10).

### Un refus témoin

L'exécution 41215069368 de `CI`, sur la PR de la branche `feat/trend-report-github-cards` (2026-10-31), a eu `audit`
en échec, et ses trois autres jobs (`tests`, `lint`, `types`) verts. Son journal
(`gh run view 41215069368 --repo SabineLaurent/K-B --log-failed`) donne `Found 4 known vulnerabilities in 1 package`,
puis `pyasn1 0.6.4`, quatre identifiants publics de vulnérabilités (CVE) et la version corrigée, `0.6.5`. Ce journal se relit jusque vers le 2027-01-29.

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
| `image-build` | l'étape en échec dit le contrôle: un fichier planté trouvé (son chemin), l'utilisateur root, ou un code de sortie inattendu | `docker buildx build` en local, puis la commande de l'étape |
| `bicep-build` | une erreur de compilation, avec son fichier et sa ligne, ou une empreinte de Bicep différente (`sha256sum: WARNING`) | `az bicep build --file infra/main.bicep` en local; pour l'empreinte, vérifier la version et le SHA256 ensemble |
| `build` de `Docs` | un avertissement du mode strict, qui nomme le fichier et le lien ou l'ancre; ou un autre fichier de Mermaid (`sha256sum: WARNING`) | la construction en local; pour Mermaid, [Le détail des réglages](#le-detail-des-reglages) |

Un échec du runner ou du réseau (téléchargement de uv, de pip-audit ou de l'image `postgres`) se relance tel quel.

## Limites

Lues le 2026-11-10; le workflow `Docs` et les réglages du dépôt, le 2026-11-14. Chaque parade a été vérifiée à la
source le 2026-11-10 (sources en fin de liste).

- **Aucune relecture n'est exigée**: le ruleset demande une PR, mais aucune approbation
  (`required_approving_review_count: 0`). La relecture en PR est une pratique, pas une règle.
  Pour réduire le risque: exiger une approbation dans le ruleset serait faisable avec nos droits (administratrice du
  dépôt), mais « <span lang="en">Pull request authors cannot approve their own pull requests</span> »: avec une seule
  personne au dépôt et aucun contournement, plus aucune PR ouverte sous son compte ne fusionnerait; seules celles de
  Dependabot, d'un autre auteur, le pourraient. Ce n'est donc pas faisable sans une seconde personne.
- **Trois contrôles ne bloquent pas la fusion**: `tests-data`, `image-build` et `build` de `Docs` ne sont pas dans le
  ruleset. `tests-data` et `image-build` comptent à la livraison (`deploy.yml:51-67`). `bicep-build` y est depuis
  #496: `infra.yml` n'a plus de filtre de chemin, car un workflow sauté par son filtre laisse ses contrôles
  « <span lang="en">Pending</span> » et bloque la fusion.
  Pour réduire le risque: ajouter ces trois contrôles aux contrôles requis du ruleset (faisable avec nos droits).
- **Les tests de bout en bout ne tournent pas en CI**: les tests marqués `e2e` appellent les vraies sources et
  services; ils se lancent sur le poste ([la fiche des tests](tests_pour_docu.md)).
  Pour réduire le risque: un workflow planifié (`on: schedule`, sur la branche par défaut) lancerait
  `pytest -m e2e`. C'est faisable avec nos droits, les clés des sources en secrets du dépôt, mais pas pour tout: les
  tests de Zotero et des clips lisent des fichiers du poste et seraient sautés. Le prix: des appels réels, dont une
  vraie requête BigQuery pour `gh_archive`, et des clés de plus dans GitHub. Le dépôt est privé
  (`gh api repos/SabineLaurent/K-B` → `"visibility":"private"`): un workflow planifié y prend sur l'usage inclus du
  compte, compté en montant; au-delà, il est payé s'il y a un moyen de paiement, dans la limite des budgets, et
  bloqué sinon. Public, il serait gratuit, mais coupé après 60 jours sans activité.
- **L'image n'est pas scannée**: `audit` lit les paquets Python de `uv.lock`, pas les paquets du système de l'image
  de base.
  Pour réduire le risque: scanner l'image `k-b:ci` dans `image-build`, par exemple par Grype (`anchore/scan-action`,
  v7.4.2), qui fait échouer le job à partir d'un seuil de sévérité (`severity-cutoff`, `medium` par défaut).
  Par défaut (`only-fixed: false`), une vulnérabilité sans correctif le fait échouer aussi; `only-fixed: true` ne
  retient que celles qui en ont un.
  Faisable avec nos droits: une action publique, épinglée par son SHA, sans secret. En attendant, Dependabot propose
  chaque semaine le nouveau digest des images de base du `Dockerfile` (`dependabot.yml:10-16`).
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
