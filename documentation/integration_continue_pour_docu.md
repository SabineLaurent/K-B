# L'intégration continue de K-B

« Documentation des procédures d'installation et de test de la chaîne. » — C18

« Documentation utilisateur, pour le déclenchement de la chaîne. » — C18

Cette fiche dit ce que fait la chaîne d'intégration continue (CI) de K-B, comment on la déclenche et la relance,
comment elle s'installe, se configure et se teste, et que faire quand elle échoue. Elle est écrite d'après le code de
`main` au commit `0292266` (2026-11-09) et les réglages du dépôt lus le même jour. Les exécutions citées se relisent
par `gh run view <id> --repo SabineLaurent/K-B`. La mise en ligne d'une version, qui suit la CI, est dans
[la fiche de la livraison continue](livraison_continue_pour_docu.md).

## La chaîne en bref

Chaque PR vers `main`, et chaque push sur `main` (donc chaque fusion), lance la CI. Elle vérifie le code (tests,
couverture, lint, format, typage), ses dépendances (vulnérabilités connues), l'image du conteneur et, quand `infra/`
change, le Bicep. Une PR ne fusionne que si ses cinq contrôles requis sont verts sur une branche à jour avec `main`
(le ruleset, plus bas). La CI ne pousse rien et ne déploie rien: elle n'a aucun droit sur Azure.

### Les outils

| Outil | Rôle dans la chaîne | Où il est réglé |
|---|---|---|
| GitHub Actions | lance les workflows sur des runners `ubuntu-latest`; chaque action est épinglée par son SHA, sa version en commentaire (`actions/checkout` v7.0.1, `astral-sh/setup-uv` v10.3.3) | `.github/workflows/ci.yml`, `image.yml`, `infra.yml` |
| uv 0.13.6 | installe Python et les dépendances de `uv.lock` (`uv sync --locked`), lance chaque outil (`uv run`) | `ci.yml`, `version: "0.13.6"` dans chacun des six jobs (l. 20, 33, 45, 57, 89, 105) |
| pytest et pytest-cov | lancent les tests et mesurent la couverture des lignes et des branches de `src/k_b/` | `pyproject.toml`, `[tool.coverage.*]` (l. 72-83) |
| ruff | lint et format du Python | `pyproject.toml`, `[tool.ruff.*]` (l. 48-67) |
| mypy | typage, en mode `--strict` | `ci.yml:60`, `pyproject.toml:69-70` |
| pip-audit 2.10.1 | cherche les vulnérabilités connues des versions de `uv.lock`, avec leurs empreintes | `ci.yml:24-25` |
| PostgreSQL 18.6 | un service du job `tests-postgresql`, épinglé par son digest | `ci.yml:68-82` |
| Docker Buildx | construit l'image `linux/amd64` de K-B et la contrôle | `image.yml` |
| Azure CLI et Bicep v0.48.1 | compile `infra/main.bicep`, sans connexion à Azure | `infra.yml` |
| Dependabot | ouvre chaque semaine les PR de mise à jour des actions et des images de base du `Dockerfile` | `.github/dependabot.yml` |
| Ruleset « Basic-rules-main-protect » | dit quels contrôles une PR doit passer pour fusionner | réglages du dépôt (plus bas) |

### Les déclencheurs

| Déclencheur | Ce qui tourne |
|---|---|
| une PR vers `main`: ouverte, rouverte, ou un commit poussé sur sa branche | `CI` et `Image` (`ci.yml:3-7`, `image.yml:3-7`); `Infra` aussi si la PR touche `infra/**` ou `.github/workflows/infra.yml` (`infra.yml:7-9`) |
| un push sur `main`, c'est-à-dire une fusion | les mêmes, sur le commit de fusion (`ci.yml:4-5`, `image.yml:4-5`, `infra.yml:4-6`) |
| « Re-run all jobs » ou « Re-run failed jobs » sur une exécution, ou `gh run rerun <id>` | la même exécution, sur le même commit |
| le planning de Dependabot, chaque semaine (`dependabot.yml:6-7`, `:13-14`) | une PR de mise à jour, qui lance la CI comme toute PR |

Une PR vers une autre branche que `main` ne lance rien: le filtre `branches: [main]` porte sur la branche visée.
Aucun workflow de la CI n'a de `concurrency`: deux pushes rapprochés lancent deux exécutions, et la première n'est
pas annulée.

### Les jobs et leurs tâches

Les jobs d'un même workflow tournent en parallèle, chacun sur un runner neuf. Dans un job, les étapes s'enchaînent,
et la première qui échoue arrête le job. Chaque workflow n'a qu'un jeton qui lit le dépôt (`permissions: contents:
read`, `ci.yml:9-10`, `image.yml:9-10`, `infra.yml:11-12`) et ne lit aucun secret.

**`CI`** (`.github/workflows/ci.yml`). Chaque job récupère le dépôt, installe uv 0.13.6, puis
`uv sync --locked`, qui refuse un `uv.lock` qui ne suit plus le `pyproject.toml`. Seul `tests` garde le cache de uv
(`save-cache: false` dans les cinq autres, l. 21, 46, 58, 90 et 106).

| Job | Tâche | Requis à la fusion |
|---|---|---|
| `audit` (l. 14-25) | `uv export --frozen --no-emit-project` écrit les versions de `uv.lock` avec leurs empreintes, puis `uvx pip-audit@2.10.1 --require-hashes --disable-pip` les compare aux vulnérabilités connues | oui |
| `tests` (l. 27-37) | `uv run pytest --cov --cov-report=term-missing:skip-covered`: la suite, sans les tests marqués `e2e` ni `postgresql`, et le seuil de couverture de 96 % (`fail_under`, `pyproject.toml:83`) | oui |
| `lint` (l. 39-49) | `uv run ruff check`, puis `uv run ruff format --check` | oui |
| `types` (l. 51-60) | `uv run mypy --strict` sur `src` | oui |
| `tests-postgresql` (l. 62-92) | `uv run pytest -m postgresql`, contre le service `postgres:18.6` du job, joint par `KB_TEST_POSTGRESQL_URL` (l. 84), sans mot de passe (`POSTGRES_HOST_AUTH_METHOD: trust`, un serveur que seul le runner joint) | oui |
| `tests-data` (l. 94-108) | `uv run pytest tests/etl tests/test_schema.py tests/test_items.py tests/ai_api/test_watch_items.py`: les tests des données, à part, sans `--cov` (`tests` les lance aussi et garde le seuil) | non |

**`Image`** (`.github/workflows/image.yml`), un job, `image-build`, non requis à la fusion:

| # | Étape | Ce qu'elle vérifie |
|---|---|---|
| 1 | (l. 22-26) | plante des fichiers que `.dockerignore` doit écarter: `.env`, `.env.decoy`, des bases `*.sqlite*`, un `__pycache__`, `.DS_Store` |
| 2 | `Sends only what the Dockerfile copies to the build` (l. 29-35) | le contexte de construction ne contient que `README.md`, `pyproject.toml`, `src` et `uv.lock`, et aucun fichier planté |
| 3 | (l. 36) | `docker buildx build --platform linux/amd64 --tag k-b:ci .` |
| 4 | `Runs as a non-root user` (l. 37-41) | l'utilisateur de l'image n'est pas root (`id -u` différent de 0) |
| 5 | `Holds none of the planted files` (l. 43-46) | l'image ne contient ni `.git` ni aucun fichier planté |
| 6 | `Refuses to start without KB_DATA_DIR` (l. 49-55) | `kb create-db` sans `KB_DATA_DIR` sort en code 2 avec `KB_DATA_DIR must point to the data directory` |
| 7 | `Starts kb and creates the database` (l. 58-61) | `kb --help`, puis `kb create-db` dans le dossier de données de l'image |

L'image `k-b:ci` n'est poussée nulle part: celle qui part en ligne est construite par `Deploy`, depuis le commit du
tag.

**`Infra`** (`.github/workflows/infra.yml`), un job, `bicep-build`, non requis à la fusion: il demande à `az`
d'utiliser son propre Bicep (l. 22), installe Bicep v0.48.1 (l. 23), vérifie son SHA256 (l. 25), affiche sa version
(l. 26), puis compile `infra/main.bicep` (l. 27). Il ne se connecte pas à Azure: Sabine applique le Bicep à la main
(`infra/README.md`).

**Après la CI**: `Deploy` ne met en ligne qu'un commit dont toutes les exécutions des workflows du dépôt sont finies
et vertes, `Image` et `Infra` comprises (`deploy.yml:51-67`). Un contrôle non requis à la fusion compte donc à la
livraison.

## Déclencher la chaîne

Cette partie s'adresse à qui ouvre une PR sur K-B.

**Lancer la CI**: ouvrir une PR vers `main`, ou pousser un commit sur sa branche. Il n'y a rien d'autre à faire.

```sh
git push -u origin <branche>
gh pr create --repo SabineLaurent/K-B --base main
gh pr checks <n° de la PR> --repo SabineLaurent/K-B --watch    # attend la fin, puis un contrôle par ligne
```

Une PR qui ne touche pas `infra/` reçoit sept contrôles: les six jobs de `CI` et `image-build`. Celle qui touche
`infra/` en reçoit un huitième, `bicep-build`.

**Fusionner**: possible quand les cinq contrôles requis (`audit`, `tests`, `lint`, `types`, `tests-postgresql`) sont
verts et que la branche est à jour avec `main`. Si `main` a avancé, mettre la branche à jour (`git fetch origin`,
puis `git rebase origin/main` et `git push --force-with-lease`, ou « Update branch » sur la PR): la CI repasse sur
le nouveau commit. La fusion se fait par un commit de fusion, la seule méthode permise par le ruleset.

**Relancer** une exécution, par exemple après un échec du réseau: « Re-run failed jobs » sur la page de l'exécution,
ou:

```sh
gh run list --repo SabineLaurent/K-B --branch <branche> --limit 3     # l'id de l'exécution
gh run rerun <id> --repo SabineLaurent/K-B --failed                    # les jobs en échec seuls
gh run rerun <id> --repo SabineLaurent/K-B                             # tous les jobs
```

Une relance reprend le même commit et les mêmes workflows: pour tester une correction, pousser un commit.

**Lire le résultat d'une fusion** sur `main`:

```sh
gh run list --repo SabineLaurent/K-B --commit "$(git rev-parse origin/main)" \
  --json workflowName,event,status,conclusion -q '.[] | [.workflowName, .event, .status, .conclusion] | @tsv'
# lu sur 0292266 le 2026-11-09: « CI push completed success » et « Image push completed success »
```

## Installer la chaîne

Les workflows et `dependabot.yml` vivent dans le dépôt: un clone les a. Le reste se règle dans GitHub, une fois par
dépôt. Ces réglages se lisent sans rien changer, par les commandes données; leur création sur un dépôt neuf n'a pas
été essayée.

**1. GitHub Actions** (Settings → Actions → General):
- Actions activées, et le SHA complet exigé pour chaque action (`sha_pinning_required`);
- jeton par défaut des workflows en lecture seule, sans droit d'approuver une PR.

```sh
gh api repos/SabineLaurent/K-B/actions/permissions
# lu le 2026-11-09: {"enabled":true,"allowed_actions":"all","sha_pinning_required":true}
gh api repos/SabineLaurent/K-B/actions/permissions/workflow
# lu le 2026-11-09: {"default_workflow_permissions":"read","can_approve_pull_request_reviews":false}
```

**2. Le ruleset de `main`** (Settings → Rules → Rulesets), avec ces règles:
- nom « Basic-rules-main-protect », actif (`enforcement: active`), sans contournement (`bypass_actors` vide);
- cible: la branche par défaut et `refs/heads/main`;
- interdire la suppression (`deletion`) et le push forcé (`non_fast_forward`);
- exiger une PR (`pull_request`), fusion par commit de fusion seulement (`allowed_merge_methods: ["merge"]`), aucune
  approbation requise (`required_approving_review_count: 0`);
- exiger les contrôles `audit`, `tests`, `lint`, `types` et `tests-postgresql`, rendus par GitHub Actions
  (`integration_id` 15368), sur une branche à jour (`strict_required_status_checks_policy: true`).

```sh
gh api repos/SabineLaurent/K-B/rulesets --jq '.[] | "\(.id) \(.name) \(.target) \(.enforcement)"'
gh api repos/SabineLaurent/K-B/rulesets/25257125 --jq '{name, enforcement, bypass_actors, conditions, rules}'
```

Les deux rulesets des tags (« tags v », « tags v immuables ») servent la livraison: voir sa fiche.

**3. Dependabot**, dans les réglages de sécurité du dépôt: activer les alertes et les mises à jour de sécurité.
`dependabot.yml` règle les mises à jour de version.

```sh
gh api -i repos/SabineLaurent/K-B/vulnerability-alerts | head -1   # lu le 2026-11-09: HTTP/2.0 204 (alertes actives)
gh api repos/SabineLaurent/K-B/automated-security-fixes            # lu le 2026-11-09: {"enabled":true,"paused":false}
```

**4. Sur le poste**, pour reproduire un job: l'environnement de développement de
[la fiche de l'installation](installation_pour_docu.md), uv 0.13.6 compris (`uv self update 0.13.6`), et, pour
`tests-postgresql`, un serveur PostgreSQL ([la fiche des tests](tests_pour_docu.md)).

## Configurer la chaîne

Rien ne se règle hors du dépôt, en dehors de l'étape précédente: aucun workflow de la CI ne lit de variable
(`vars.`) ni de secret. Ce qui se change, et où:

| Réglage | Où | À changer avec |
|---|---|---|
| version de uv | `version:` des six jobs de `ci.yml`; `Dockerfile:7` | les deux ensemble, dans la plage `uv_build>=0.13.6,<0.14.0` de `pyproject.toml:30`. La PR de Dependabot ne change que le `Dockerfile`: les six `version:` se changent à la main, dans la même PR |
| version de pip-audit | `ci.yml:25` | à la main |
| image de PostgreSQL | `ci.yml:69`, tag et digest | à la main: Dependabot ne lit que les `uses:` d'un workflow (`ci.yml:63-64`) |
| version de Bicep | `infra.yml:23`, et son SHA256 à `infra.yml:25` | les deux ensemble, l'empreinte lue sur la release de Bicep |
| seuil de couverture | `fail_under`, `pyproject.toml:83` | une décision consignée au journal ADR (le seuil de 96 % date du 2026-11-08) |
| règles de lint | `[tool.ruff.lint]`, `pyproject.toml:48-67` | `uv run ruff check --no-cache` avant de pousser |
| tests écartés par défaut | marqueurs `e2e` et `postgresql`, écartés sauf s'ils sont nommés par `-m` (`tests/conftest.py:118-129`) | un test marqué `postgresql` ne tourne que dans `tests-postgresql` |
| contrôles requis à la fusion | le ruleset de `main` | un job nouveau n'est pas requis tant qu'il n'est pas ajouté au ruleset |
| fréquence et attente de Dependabot | `dependabot.yml`: chaque semaine, 7 jours d'attente pour une version nouvelle (`cooldown`, l. 8-9 et 15-16), ni version mineure ni majeure de `python` et d'`astral-sh/uv` (l. 24-28) | à la main |

Une action nouvelle s'écrit par son SHA complet, sa version en commentaire: le dépôt refuse une action non épinglée
(`sha_pinning_required`).

## Tester la chaîne

**Sur le poste**, chaque job a son équivalent, à lancer depuis la racine du dépôt, sans `.env` exporté:

| Job | Commande locale |
|---|---|
| `audit` | `uv export --frozen --no-emit-project --format requirements-txt -o requirements-audit.txt`, puis `uvx pip-audit@2.10.1 --require-hashes --disable-pip -r requirements-audit.txt` |
| `tests` | `uv run pytest --cov --cov-report=term-missing:skip-covered`, ou `make test-cov` |
| `lint` | `uv run ruff check --no-cache`, puis `uv run ruff format --check` |
| `types` | `uv run mypy --strict` |
| `tests-postgresql` | `KB_TEST_POSTGRESQL_URL=<URL d'un serveur> uv run pytest -m postgresql` |
| `tests-data` | `uv run pytest tests/etl tests/test_schema.py tests/test_items.py tests/ai_api/test_watch_items.py` |
| `image-build` | `docker buildx build --platform linux/amd64 --tag k-b .`, puis `docker run --rm k-b --help` |
| `bicep-build` | `az bicep build --file infra/main.bicep --stdout > /dev/null` |

**Sur GitHub, une PR témoin**: [#533](https://github.com/SabineLaurent/K-B/pull/533), fusionnée le 2026-11-09, ne
touche pas `infra/`. Elle a reçu sept contrôles, tous verts (`gh pr checks 533 --repo SabineLaurent/K-B`): `audit`
(13 s), `tests` (1 min 21 s), `lint` (11 s), `types` (15 s), `tests-postgresql` (1 min 1 s), `tests-data` (30 s),
dans l'exécution 42617081839 de `CI`, et `image-build` (23 s), dans l'exécution 42617082007 d'`Image`;
`bicep-build` n'y a pas tourné.

**Un push témoin**: la fusion `0292266` sur `main`, le 2026-11-09, a lancé `CI` (42620998480) et `Image`
(42620998487), toutes deux `success`; `Infra` n'a pas tourné, `infra/` n'ayant pas changé. La dernière exécution
d'`Infra` sur `main` est 42429157192, `success`, sur `ccf1455` (2026-11-08).

**Un refus témoin**: l'exécution 41215069368 de `CI`, sur la PR de la branche `feat/trend-report-github-cards`
(2026-10-31), a eu `audit` en échec, et ses trois autres jobs (`tests`, `lint`, `types`) verts. Son journal (`gh run view 41215069368 --repo
SabineLaurent/K-B --log-failed`) donne `Found 4 known vulnerabilities in 1 package`, puis `pyasn1 0.6.4`, quatre CVE
et la version corrigée, `0.6.5`.

## Quand la CI échoue

**Lire d'abord** le job en échec et ses dernières lignes:

```sh
gh pr checks <n° de la PR> --repo SabineLaurent/K-B          # quel job
gh run view <id> --repo SabineLaurent/K-B --log-failed       # ses lignes, étape par étape
```

Puis reproduire le job sur le poste (tableau plus haut), corriger, pousser un commit.

| Job en échec | Ce qu'il a vu | Quoi faire |
|---|---|---|
| `uv sync --locked`, dans tout job | `uv.lock` ne suit plus `pyproject.toml` | `uv lock`, puis committer `uv.lock` |
| `audit` | une version de `uv.lock` a une vulnérabilité connue: le paquet, sa version, l'identifiant et la version corrigée | monter le paquet (`uv lock --upgrade-package <paquet>`), relancer `audit` en local |
| `tests` | un test en échec, ou le seuil manqué (`Required test coverage of … not reached. Total coverage: …`) | lancer le test seul (`uv run pytest <chemin>::<test>`), ou `make test-cov` pour les lignes non couvertes |
| `lint` | une règle de ruff, ou un fichier à reformater | `uv run ruff check --no-cache`, `uv run ruff format` |
| `types` | une erreur de mypy, avec son fichier et sa ligne | `uv run mypy --strict` |
| `tests-postgresql` | un test en échec, ou le service qui ne démarre pas (`pg_isready` en échec 15 fois, 2 s d'écart, `ci.yml:78-82`) | relancer le job; puis le test sur un serveur local |
| `tests-data` | un test des données en échec | le même test, sur le poste |
| `image-build` | l'étape en échec dit le contrôle: un fichier planté trouvé (son chemin), l'utilisateur root, ou un code de sortie inattendu | `docker buildx build` en local, puis la commande de l'étape |
| `bicep-build` | une erreur de compilation, avec son fichier et sa ligne, ou une empreinte de Bicep différente (`sha256sum: WARNING`) | `az bicep build --file infra/main.bicep` en local; pour l'empreinte, vérifier la version et le SHA256 ensemble |

Un échec du runner ou du réseau (téléchargement de uv, de pip-audit ou de l'image `postgres`) se relance tel quel.

## Limites, lues le 2026-11-09

- **Aucune relecture n'est exigée**: le ruleset demande une PR, mais aucune approbation
  (`required_approving_review_count: 0`). La relecture en PR est une pratique, pas une règle.
- **Trois contrôles ne bloquent pas la fusion**: `tests-data`, `image-build` et `bicep-build` ne sont pas dans le
  ruleset. `bicep-build`, filtré par chemin, bloquerait toute PR qui ne touche pas `infra/` (`infra.yml:15`). Ils
  comptent à la livraison (`deploy.yml:51-67`).
- **Les tests de bout en bout ne tournent pas en CI**: les tests marqués `e2e` appellent les vraies sources et
  services; ils se lancent sur le poste ([la fiche des tests](tests_pour_docu.md)).
- **L'image n'est pas scannée**: `audit` lit les paquets Python de `uv.lock`, pas les paquets du système de l'image
  de base.
- **Aucun délai propre aux jobs**: aucun `timeout-minutes` dans `ci.yml`, `image.yml` ni `infra.yml`; le délai par
  défaut de GitHub s'applique.
- **Une PR vers une autre branche que `main`** ne lance aucune CI.
