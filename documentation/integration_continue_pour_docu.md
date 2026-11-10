# L'intégration continue de K-B

« Documentation des procédures d'installation et de test de la chaîne. » — C18

« Documentation utilisateur, pour le déclenchement de la chaîne. » — C18

Cette fiche dit ce que fait la chaîne d'intégration continue (CI) de K-B, comment on la déclenche et la relance,
comment elle s'installe, se configure et se teste, et que faire quand elle échoue. Elle est écrite d'après le code de
`main` au commit `89ef7fb` (2026-11-10) et les réglages du dépôt lus le même jour. Les exécutions citées se relisent
par `gh run view <id> --repo SabineLaurent/K-B`, 90 jours au plus: c'est la durée de garde des journaux du dépôt
(`gh api repos/SabineLaurent/K-B/actions/permissions/artifact-and-log-retention` → `"days":90`). La mise en ligne
d'une version, qui suit la CI, est dans [la fiche de la livraison continue](livraison_continue_pour_docu.md).

## La chaîne en bref

Chaque PR vers `main`, et chaque push sur `main` (donc chaque fusion), lance la CI. Elle vérifie le code (tests,
couverture, lint, format, typage), ses dépendances (vulnérabilités connues), l'image du conteneur et, quand `infra/`
change, le Bicep. Une PR ne fusionne que si ses cinq contrôles requis sont verts sur une branche à jour avec `main`
(le ruleset, plus bas). La CI ne pousse rien et ne déploie rien: elle n'a aucun droit sur Azure.

### Les outils

| Outil | Rôle dans la chaîne | Où il est réglé |
|---|---|---|
| GitHub Actions | lance les workflows sur des runners `ubuntu-latest`; chaque action est épinglée par son SHA, sa version en commentaire (`actions/checkout` v7.0.1, `astral-sh/setup-uv` v10.3.3) | `.github/workflows/ci.yml`, `image.yml`, `infra.yml` |
| uv 0.13.6 | installe Python 3.13 (`.python-version`) et les dépendances de `uv.lock` (`uv sync --locked`), lance chaque outil (`uv run`) | `ci.yml`, `version: "0.13.6"` dans chacun des six jobs (l. 20, 33, 45, 57, 89, 105) |
| pytest et pytest-cov | lancent les tests et mesurent la couverture des lignes et des branches de `src/k_b/` | `pyproject.toml`, `[tool.coverage.*]` (l. 72-85) |
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
| une alerte de Dependabot, à tout moment (mises à jour de sécurité, activées plus bas) | une PR de sécurité, sans attente, qui lance la CI comme toute PR |

Une PR vers une autre branche que `main` ne lance rien: le filtre `branches: [main]` porte sur la branche visée.
GitHub lance aussi deux workflows à lui, hors du dépôt, « Dependabot Updates » et « Dependency Graph » (événement
`dynamic`, `gh api repos/SabineLaurent/K-B/actions/workflows`); `Deploy` ne les compte pas (`deploy.yml:53`).
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
| `tests-postgresql` (l. 62-92) | `uv run pytest -m postgresql`, contre le service `postgres:18.6` du job (utilisateur `kb`, base en UTF8 et collation C, l. 71-75), joint par `KB_TEST_POSTGRESQL_URL` (l. 84), sans mot de passe (`POSTGRES_HOST_AUTH_METHOD: trust`, un serveur que seul le runner joint) | oui |
| `tests-data` (l. 94-108) | `uv run pytest tests/etl tests/test_schema.py tests/test_items.py tests/ai_api/test_watch_items.py`: les tests des données, à part, sans `--cov` (`tests` les lance aussi et garde le seuil) | non |

**`Image`** (`.github/workflows/image.yml`), un job, `image-build`, non requis à la fusion:

| # | Étape | Ce qu'elle vérifie |
|---|---|---|
| 1 | (l. 18) | récupère le dépôt (`actions/checkout`), `.git` compris |
| 2 | (l. 22-26) | plante des fichiers que `.dockerignore` doit écarter, à la racine (`.env`, `.env.decoy`, `temp/decoy`, `reports/decoy`, `.venv/decoy`) et dans `src/k_b/` (`.env.decoy`, `decoy.sqlite`, `decoy.sqlite-wal`, `.DS_Store`, `__pycache__/decoy.pyc`) |
| 3 | `Sends only what the Dockerfile copies to the build` (l. 29-35) | le contexte de construction ne contient, à sa racine, que `README.md`, `pyproject.toml`, `src` et `uv.lock` (l. 33), et nulle part un fichier planté ni un `__pycache__` (l. 34) |
| 4 | (l. 36) | `docker buildx build --platform linux/amd64 --tag k-b:ci .` |
| 5 | `Runs as a non-root user` (l. 37-41) | l'utilisateur de l'image n'est pas root (`id -u` différent de 0) |
| 6 | `Holds none of the planted files` (l. 43-46) | aucun chemin de l'image ne s'appelle `.env*`, `*.sqlite*`, `decoy`, `.DS_Store` ni `.git` (l. 45); `__pycache__` n'est cherché que dans le contexte (étape 3) |
| 7 | `Refuses to start without KB_DATA_DIR` (l. 49-55) | `kb create-db` sans `KB_DATA_DIR` sort en code 2 avec `KB_DATA_DIR must point to the data directory` |
| 8 | `Starts kb and creates the database` (l. 58-61) | `kb --help`, puis `kb create-db` dans le dossier de données de l'image |

L'image `k-b:ci` n'est poussée nulle part: celle qui part en ligne est construite par `Deploy`, depuis le commit du
tag.

**`Infra`** (`.github/workflows/infra.yml`), un job, `bicep-build`, non requis à la fusion: il récupère le dépôt
(l. 20), demande à `az` d'utiliser son propre Bicep (l. 22), installe Bicep v0.48.1 (l. 23), vérifie son SHA256
(l. 25), affiche sa version (l. 26), puis compile `infra/main.bicep` (l. 27). Il ne se connecte pas à Azure:
Sabine applique le Bicep à la main (`infra/README.md`).

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

Une PR qui ne touche ni `infra/` ni `.github/workflows/infra.yml` reçoit sept contrôles: les six jobs de `CI` et
`image-build`. Celle qui touche l'un des deux en reçoit un huitième, `bicep-build`.

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

Une relance reprend le même commit et les mêmes workflows, jusqu'à 30 jours après l'exécution: pour tester une
correction, pousser un commit.

**Lire le résultat d'une fusion** sur `main`:

```sh
git fetch origin
gh run list --repo SabineLaurent/K-B --commit "$(git rev-parse origin/main)" \
  --json workflowName,event,status,conclusion -q '.[] | [.workflowName, .event, .status, .conclusion] | @tsv'
# lu sur 89ef7fb le 2026-11-10: « CI push completed success » et « Image push completed success »
```

## Installer la chaîne

Les workflows et `dependabot.yml` vivent dans le dépôt: un clone les a. Le reste se règle dans GitHub, une fois par
dépôt. Ces réglages se lisent sans rien changer, par les commandes données; leur création sur un dépôt neuf n'a pas
été essayée.

**1. GitHub Actions** (Settings → Actions → General):
- Actions activées, toutes les actions permises (`allowed_actions: all`, pour les actions tierces), et le SHA complet
  exigé pour chaque action (`sha_pinning_required`);
- jeton par défaut des workflows en lecture seule, sans droit d'approuver une PR.

```sh
gh api repos/SabineLaurent/K-B/actions/permissions
# lu le 2026-11-10: {"enabled":true,"allowed_actions":"all","sha_pinning_required":true}
gh api repos/SabineLaurent/K-B/actions/permissions/workflow
# lu le 2026-11-10: {"default_workflow_permissions":"read","can_approve_pull_request_reviews":false}
```

**2. Le ruleset de `main`** (Settings → Rules → Rulesets), avec ces règles:
- nom « Basic-rules-main-protect », actif (`enforcement: active`), sans contournement (`bypass_actors` vide);
- cible: la branche par défaut et `refs/heads/main`;
- interdire la suppression (`deletion`) et le push forcé (`non_fast_forward`);
- exiger une PR (`pull_request`), fusion par commit de fusion seulement (`allowed_merge_methods: ["merge"]`), aucune
  approbation requise (`required_approving_review_count: 0`), une approbation de plus pour un changement non
  attribué (`require_extra_approval_for_unattributed_changes: true`);
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
gh api -i repos/SabineLaurent/K-B/vulnerability-alerts | head -1   # lu le 2026-11-10: HTTP/2.0 204 (alertes actives)
gh api repos/SabineLaurent/K-B/automated-security-fixes            # lu le 2026-11-10: {"enabled":true,"paused":false}
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
| image de PostgreSQL | `ci.yml:69`, tag et digest | à la main: d'après le commentaire de `ci.yml:63-64`, Dependabot ne la met pas à jour |
| chemins envoyés à la construction | `.dockerignore`, `Dockerfile` et la liste de `image.yml:33` | ensemble: un chemin de plus dans le contexte fait échouer l'étape 3 d'`Image` tant qu'il manque à la liste |
| version de Bicep | `infra.yml:23`, et son SHA256 à `infra.yml:25` | les deux ensemble, l'empreinte lue sur la release de Bicep |
| seuil de couverture | `fail_under`, `pyproject.toml:83` | une décision consignée au journal ADR (le seuil de 96 % date du 2026-11-08) |
| règles de lint | `[tool.ruff.lint]`, `pyproject.toml:48-67` | `uv run ruff check --no-cache` avant de pousser |
| tests écartés par défaut | marqueurs `e2e` et `postgresql`, écartés sauf s'ils sont nommés par `-m` (`tests/conftest.py:118-130`) | un test marqué `postgresql` ne tourne que dans `tests-postgresql` |
| contrôles requis à la fusion | le ruleset de `main` | un job nouveau n'est pas requis tant qu'il n'est pas ajouté au ruleset |
| fréquence et attente de Dependabot | `dependabot.yml`: chaque semaine, 7 jours d'attente pour une version nouvelle (`cooldown`, l. 8-9 et 15-16), sauf une mise à jour de sécurité (l. 9) et `astral-sh/uv`, dont ghcr.io ne donne pas la date, à vérifier à la main avant la fusion (l. 17-19), ni version mineure ni majeure de `python` et d'`astral-sh/uv` (l. 24-28) | à la main |

Une action nouvelle s'écrit par son SHA complet, sa version en commentaire: le dépôt refuse une action non épinglée
(`sha_pinning_required`).

## Tester la chaîne

**Sur le poste**, chaque job a son équivalent, à lancer depuis la racine du dépôt, sans `.env` exporté; ceux
d'`image-build` et de `bicep-build` ne refont qu'une partie du job:

| Job | Commande locale |
|---|---|
| `audit` | `uv export --frozen --no-emit-project --format requirements-txt -o "${TMPDIR:-/tmp}/requirements-audit.txt"`, puis `uvx pip-audit@2.10.1 --require-hashes --disable-pip -r "${TMPDIR:-/tmp}/requirements-audit.txt"` (hors du dépôt, où git ne l'ignorerait pas) |
| `tests` | `uv run pytest --cov --cov-report=term-missing:skip-covered`, ou `make test-cov` |
| `lint` | `uv run ruff check --no-cache`, puis `uv run ruff format --check` |
| `types` | `uv run mypy --strict` |
| `tests-postgresql` | `KB_TEST_POSTGRESQL_URL=<URL d'un serveur> uv run pytest -m postgresql` |
| `tests-data` | `uv run pytest tests/etl tests/test_schema.py tests/test_items.py tests/ai_api/test_watch_items.py` |
| `image-build` | `docker buildx build --platform linux/amd64 --tag k-b .`, puis `docker run --rm k-b --help`; les étapes 2, 3, 5 à 7 et le `create-db` de l'étape 8 (`image.yml:22-61`) se refont une à une |
| `bicep-build` | `az bicep install --version v0.48.1`, puis `az bicep build --file infra/main.bicep --stdout > /dev/null`; sans le contrôle du SHA256 (`infra.yml:25`) |

**Sur GitHub, une PR témoin**: [#533](https://github.com/SabineLaurent/K-B/pull/533), fusionnée le 2026-11-09, ne
touche pas `infra/`. Elle a reçu sept contrôles, tous verts (`gh pr checks 533 --repo SabineLaurent/K-B`): `audit`
(13 s), `tests` (1 min 21 s), `lint` (11 s), `types` (15 s), `tests-postgresql` (1 min 1 s), `tests-data` (30 s),
dans l'exécution 42617081839 de `CI`, et `image-build` (23 s), dans l'exécution 42617082007 d'`Image`;
`bicep-build` n'y a pas tourné.

**Un push témoin**: la fusion `89ef7fb` sur `main`, le 2026-11-10, a lancé `CI` (42815479408) et `Image`
(42815479369), toutes deux `success`; `Infra` n'a pas tourné, `infra/` n'ayant pas changé. La dernière exécution
d'`Infra` sur `main` est 42750689052, `success`, sur `cad8328` (2026-11-10).

**Un refus témoin**: l'exécution 41215069368 de `CI`, sur la PR de la branche `feat/trend-report-github-cards`
(2026-10-31), a eu `audit` en échec, et ses trois autres jobs (`tests`, `lint`, `types`) verts. Son journal
(`gh run view 41215069368 --repo SabineLaurent/K-B --log-failed`) donne `Found 4 known vulnerabilities in 1 package`,
puis `pyasn1 0.6.4`, quatre CVE et la version corrigée, `0.6.5`. Ce journal se relit jusque vers le 2027-01-29.

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
| `tests-postgresql` | un test en échec, ou le service qui ne démarre pas (`pg_isready` en échec 15 fois, 2 s d'écart, 5 s de délai chacune, `ci.yml:78-82`) | relancer le job; puis le test sur un serveur local |
| `tests-data` | un test des données en échec | le même test, sur le poste |
| `image-build` | l'étape en échec dit le contrôle: un fichier planté trouvé (son chemin), l'utilisateur root, ou un code de sortie inattendu | `docker buildx build` en local, puis la commande de l'étape |
| `bicep-build` | une erreur de compilation, avec son fichier et sa ligne, ou une empreinte de Bicep différente (`sha256sum: WARNING`) | `az bicep build --file infra/main.bicep` en local; pour l'empreinte, vérifier la version et le SHA256 ensemble |

Un échec du runner ou du réseau (téléchargement de uv, de pip-audit ou de l'image `postgres`) se relance tel quel.

## Limites, lues le 2026-11-10

Chaque parade a été vérifiée à la source le 2026-11-10 (sources en fin de liste).

- **Aucune relecture n'est exigée**: le ruleset demande une PR, mais aucune approbation
  (`required_approving_review_count: 0`). La relecture en PR est une pratique, pas une règle.
  Pour réduire le risque: exiger une approbation dans le ruleset serait faisable avec nos droits (administratrice du
  dépôt), mais « Pull request authors cannot approve their own pull requests »: avec une seule personne au dépôt et
  aucun contournement, plus aucune PR ouverte sous son compte ne fusionnerait; seules celles de Dependabot, d'un autre
  auteur, le pourraient. Ce n'est donc pas faisable sans une seconde personne.
- **Trois contrôles ne bloquent pas la fusion**: `tests-data`, `image-build` et `bicep-build` ne sont pas dans le
  ruleset. `bicep-build`, filtré par chemin, bloquerait toute PR qui ne touche pas `infra/` (`infra.yml:15`). Ils
  comptent à la livraison (`deploy.yml:51-67`).
  Pour réduire le risque: ajouter `tests-data` et `image-build` aux contrôles requis du ruleset (faisable avec nos
  droits). Pour `bicep-build`, GitHub conseille de ne pas exiger un workflow qui peut être sauté: un workflow sauté par
  son filtre de chemins laisse ses contrôles « Pending » et bloque la fusion, alors qu'un job sauté par une condition
  (`if:`) rend « Success ». Le filtre passerait du déclencheur d'`infra.yml` à une condition du job, calculée par un
  job préalable, avec `always()`: sans lui, un job dont le préalable échoue est sauté et ne bloque pas la fusion
  (faisable avec nos droits, un changement d'`infra.yml`).
- **Les tests de bout en bout ne tournent pas en CI**: les tests marqués `e2e` appellent les vraies sources et
  services; ils se lancent sur le poste ([la fiche des tests](tests_pour_docu.md)).
  Pour réduire le risque: un workflow planifié (`on: schedule`, sur la branche par défaut) lancerait
  `pytest -m e2e`. C'est faisable avec nos droits, les clés des sources en secrets du dépôt, mais pas pour tout: les
  tests de Zotero et des clips lisent des fichiers du poste et seraient sautés. Le prix: des appels réels, dont une
  vraie requête BigQuery pour `gh_archive`, et des clés de plus dans GitHub. Le dépôt est privé
  (`gh api repos/SabineLaurent/K-B` → `"visibility":"private"`): un workflow planifié y prend les minutes du compte,
  puis est facturé; public, il serait gratuit, mais coupé après 60 jours sans activité.
- **L'image n'est pas scannée**: `audit` lit les paquets Python de `uv.lock`, pas les paquets du système de l'image
  de base.
  Pour réduire le risque: scanner l'image `k-b:ci` dans `image-build`, par exemple par Grype (`anchore/scan-action`,
  v7.4.2), qui fait échouer le job à partir d'un seuil de sévérité (`severity-cutoff`, `medium` par défaut).
  Par défaut (`only-fixed: false`), une vulnérabilité sans correctif le fait échouer aussi; `only-fixed: true` ne
  retient que celles qui en ont un.
  Faisable avec nos droits: une action publique, épinglée par son SHA, sans secret. En attendant, Dependabot propose
  chaque semaine le nouveau digest des images de base du `Dockerfile` (`dependabot.yml:10-16`).
- **Aucun délai propre aux jobs**: aucun `timeout-minutes` dans `ci.yml`, `image.yml` ni `infra.yml`; le délai par
  défaut de GitHub s'applique, 360 minutes par job, prises sur les minutes du compte tant que le
  dépôt est privé.
  Pour réduire le risque: un `timeout-minutes` par job, à quelques fois sa durée observée (1 min 21 s au plus sur
  #533). Faisable avec nos droits, par un changement des workflows.
- **Une PR vers une autre branche que `main`** ne lance aucune CI.
  Pour réduire le risque: rien n'entre dans `main` sans une PR vers `main` (règle `pull_request` du ruleset), qui
  lance la CI et attend ses cinq contrôles requis. Retirer `branches: [main]` du `pull_request` de chaque workflow
  lancerait aussi la CI sur les autres PR (faisable avec nos droits).

Sources, lues le 2026-11-10: GitHub Docs,
[« Approving a pull request with required reviews »](https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/approving-a-pull-request-with-required-reviews),
[« Troubleshooting required status checks »](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)
(« Handling skipped but required checks »),
[« Events that trigger workflows »](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
(`schedule`) et
[« Workflow syntax »](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
(`jobs.<job_id>.timeout-minutes`),
[« Re-running workflows and jobs »](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)
(30 jours) et [« GitHub Actions billing »](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
(dépôt privé); le dépôt [anchore/scan-action](https://github.com/anchore/scan-action), son
`action.yml` et sa dernière release, v7.4.2 (2026-08-28).
