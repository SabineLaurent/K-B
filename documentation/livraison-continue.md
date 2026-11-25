# La livraison continue de K-B

!!! note "Compétences de la certification"

    > Documentation des procédures d'installation et de test de la chaîne.

    — C13

    > Documentation utilisateur, pour le déclenchement de la chaîne.

    — C13

    > Documentation de la procédure de livraison continue: outils, configurations, exécution, débug.

    — C19

Cette fiche dit ce que fait la chaîne de livraison continue de K-B, comment on la déclenche, comment elle
s'installe, se configure et se teste, et que faire quand une livraison échoue. Elle est écrite d'après le code de
`main` au commit `b412323`, les jobs planifiés (#330, #423) d'après le code de la demande de fusion
(PR, <span lang="en">pull request</span>) de #423, et les apps que la livraison met à jour, les exécutions attendues
sur un commit de `main` et la place de `Docs` dans le contrôle de l'intégration continue (CI) d'après `main` au
commit `fd956430`, puis d'après la demande de fusion de #684, qui fait tourner `Docs` sur
chaque fusion. Les exécutions citées se relisent par `gh run view <id> --repo SabineLaurent/K-B`, et
leur journal par `--log`.

## La chaîne en bref

Une version part en ligne quand un tag `vX.Y.Z` est poussé sur un commit de `main` dont la CI est finie et verte.
Une fusion ne déploie rien. La chaîne a trois temps.

1. **La CI**, sur chaque PR vers `main` et sur chaque push sur `main`: `ci.yml` (tests, lint, typage, audit),
    `image.yml` (l'image se construit et se contrôle, sans être poussée), et `infra.yml` (le Bicep se compile, sur
    toute PR depuis #496). Son détail est l'affaire de
    [la fiche de l'intégration continue](integration-continue.md).
2. **Le tag**: une administratrice du dépôt pose `vX.Y.Z` sur un commit de `main` et le pousse.
3. **Le workflow `Deploy`** (`.github/workflows/deploy.yml`): le job `check` vérifie le tag et la CI de son commit,
    puis le job `deploy` construit l'image du tag, migre la base, met les trois apps (les deux API et le site,
    `ca-kb-web`) et les jobs à cette image (`.github/workflows/deploy.yml:165-176`), attend les nouvelles révisions
    et lance le test de fumée.

L'image livrée est construite par `deploy`, depuis le commit du tag. Celle d'`image.yml` n'est poussée nulle part.

### Les outils

| Outil | Rôle dans la chaîne | Où il est réglé |
|---|---|---|
| GitHub Actions | lance la CI et `Deploy`; chaque action est épinglée par son SHA (`actions/checkout` v7.0.1, `azure/login` v3.1.0) | `.github/workflows/` |
| Rulesets de tags et environnement `production` de GitHub | disent qui peut poser un tag et quel job peut se connecter à Azure | réglages du dépôt |
| OpenID Connect (OIDC) de GitHub et identité managée `id-kb-deploy` | connexion à Azure sans aucun mot de passe: GitHub signe un jeton court, qu'Azure accepte s'il vient de l'environnement `production` | [le module Bicep `deploy-access.bicep`](https://github.com/SabineLaurent/K-B/blob/main/infra/modules/deploy-access.bicep) |
| Docker Buildx | construit l'image `linux/amd64`, lit son label et son digest (`docker buildx imagetools inspect`) | `deploy.yml` |
| Azure Container Registry (`crkb…`) | garde les images `k-b:<tag>` | [le module Bicep `container-registry.bicep`](https://github.com/SabineLaurent/K-B/blob/main/infra/modules/container-registry.bicep) |
| Azure CLI (`az`) | met les apps et les jobs à l'image, lance les jobs, lit leur état | `deploy.yml` |
| Azure Container Apps | fait tourner `ca-kb-data-api`, `ca-kb-ai-api`, `ca-kb-web` (le site, `infra/main.bicep:322-324`), et les jobs `caj-kb-migrate-database`, `caj-kb-smoke-test`, `caj-kb-daily-routine` et `caj-kb-digest-watch` | `infra/main.bicep` et ses modules; ceux que la livraison met à jour sont listés dans [le fichier `deployment.json` de l'infrastructure](https://github.com/SabineLaurent/K-B/blob/main/infra/deployment.json) |
| `gh` et `jq` | `check` lit les exécutions de la CI du commit; `deploy` lit `deployment.json`, et l'état des apps et de leur dernière révision | `deploy.yml` |

### Les déclencheurs

| Déclencheur | Ce qui tourne |
|---|---|
| un tag poussé qui suit le filtre `v[0-9]+.[0-9]+.[0-9]+` | `Deploy`, sur ce tag |
| `gh workflow run deploy.yml --repo SabineLaurent/K-B --ref <tag>` (`workflow_dispatch`) | `Deploy`, sur ce tag: c'est le retour à une version au-delà des 30 jours où une exécution se relance |
| « <span lang="en">Re-run all jobs</span> » sur une exécution de `Deploy` (ou `gh run rerun <id>`) | la même exécution, sur le même tag |
| une PR vers `main`, un push sur `main` | la CI seule: rien ne part en ligne |

Une livraison à la fois: `deploy.yml` a la file `concurrency: production`, avec `cancel-in-progress: false`. Celle qui
tourne va au bout; une livraison en attente est annulée par une plus récente.

### Le job `check`

Il tourne sans droit sur Azure, avec un jeton qui lit le dépôt et ses exécutions (`contents: read`,
`actions: read`). Il récupère tout l'historique (`fetch-depth: 0`), puis enchaîne les trois contrôles du tableau
suivant. Le premier qui refuse arrête l'exécution, et `deploy` est `skipped`.

| Étape | Ce qu'elle refuse | Message |
|---|---|---|
| `Refuses a ref that is not a version tag` | une référence qui n'est pas `refs/tags/vMAJEUR.MINEUR.CORRECTIF`, chaque nombre sans zéro de tête | `not a version tag vMAJOR.MINOR.PATCH: <ref>` |
| `Refuses a tag whose commit is not on main` | un commit absent de la première lignée de `main` (`git rev-list --first-parent origin/main`): la tête d'une branche, ou un commit d'une branche déjà fusionnée. Un tag annoté est suivi jusqu'à son commit (`^{commit}`) | `<tag> is not on main: <sha>` |
| `Refuses a commit whose CI is not finished and green` | un commit dont une exécution de la CI est en cours, rouge ou annulée, ou qui n'en a aucune. Comptent les exécutions des workflows de `.github/workflows/`, sauf `deploy.yml` (une livraison s'attendrait elle-même, et une livraison ratée bloquerait un retour en arrière). Celles que GitHub crée lui-même, comme Dependabot, ne comptent pas | la liste `<chemin du workflow>: <status> <conclusion>`, puis `the CI of <sha> is not finished and green` |

Les exécutions de `Docs` (`.github/workflows/docs.yml`) comptent aussi: ce contrôle n'écarte que `deploy.yml`
(`.github/workflows/deploy.yml:60-62`). `Docs` tourne sur chaque push sur `main`
(`.github/workflows/docs.yml:10-11`): son exécution en échec, annulée ou pas encore finie, fait refuser le tag de ce commit,
comme celle de `CI`. Pour livrer ce commit malgré tout, relancer `Docs`
(`gh run rerun <id> --repo SabineLaurent/K-B`), ou livrer un commit suivant de `main`. Retirer `Docs` de
ce contrôle a été écarté: c'est un contrôle de sécurité de la livraison (journal des décisions d'architecture, ou
ADR, « Documentation publiée par un site MkDocs sur GitHub Pages »,
`docs/ADR/journal-decisions-projet.md:7358`). Le même fait est écrit dans
[la section « Après la CI » de la fiche de l'intégration continue](integration-continue.md#apres-la-ci).

Le SHA du commit passe ensuite à `deploy`.

### Le job `deploy`

Il tourne dans l'environnement GitHub `production`, avec le droit de demander un jeton OIDC (`id-token: write`), et
75 minutes au plus (`timeout-minutes: 75`). Le groupe de ressources et le registre lui viennent de deux secrets du
dépôt. Il récupère le commit du tag, puis enchaîne les étapes du tableau suivant. Si une étape échoue, les suivantes ne
tournent pas.

| # | Étape | Ce qu'elle fait | Ligne de résultat |
|---|---|---|---|
| 1 | `azure/login` | se connecte à Azure en `id-kb-deploy`, par OIDC | `Azure CLI login succeeds by using OIDC.` |
| 2 | `Signs in to the registry` | `az acr login` sur le registre; l'image visée est `<registre>.azurecr.io/k-b:<tag>` | `Login Succeeded` |
| 3 | `Builds and pushes the image of the tag, unless it is there` | lit l'image du tag. Absente (`not found`), elle est construite pour `linux/amd64`, avec le SHA du commit en label `org.opencontainers.image.revision` et le tag dans `KB_VERSION`, que le pied du site affiche, puis poussée. Présente et construite depuis ce même commit, elle est reprise sans être reconstruite (un retour en arrière). Présente avec un autre SHA, ou toute autre erreur de lecture: l'étape s'arrête. Puis elle lit le digest de l'image et revérifie le label de l'image désignée par ce digest | `<tag>: sha256:…` |
| 4 | `Writes the run of a job` | écrit la fonction `run_job`: mettre un job à l'image, le lancer, lire son état toutes les 15 s | aucune |
| 5 | `Migrates the base` | `run_job caj-kb-migrate-database 52`. `kb migrate-database` crée une base qui n'a pas ses tables, et laisse telle quelle celle qui les a: un retour à un tag précédent la relance sans risque | `caj-kb-migrate-database: Succeeded` |
| 6 | `Sets the apps to the image of the tag` | `az containerapp update` de chaque app de `deployment.json`, à l'image par son digest (`k-b@sha256:…`): une réplique qui se réveille tire l'image déployée, même si le tag était réécrit | `<app>: <tag> (sha256:…)` |
| 7 | `Sets the jobs to the image of the tag` | `az containerapp job update` de chaque job de `deployment.json`, de même | `<job>: <tag> (sha256:…)` |
| 8 | `Waits for the revisions of the apps at the image of the tag` | attend, pour chaque app, que sa dernière révision soit prête (`latestReadyRevisionName` égal à `latestRevisionName`) et que l'image de cette révision soit celle du tag. 40 lectures, 15 s d'écart. Sans cette attente, l'ancienne révision répond encore, et le test de fumée pourrait passer sur l'ancienne version | `the latest revision of each app is ready at <tag> (sha256:…)` |
| 9 | `Runs the smoke test` | `run_job caj-kb-smoke-test 72`: `kb smoke-test` demande `GET /health` aux deux API, pas au site (`src/k_b/commands/smoke_test_command.py:79-83`), leur envoie, depuis #499, ses sondes sans clé (401, 404, 405), et liste le conteneur `smoke-test` du stockage d'échange, par l'identité du job | `caj-kb-smoke-test: Succeeded` |

`run_job` lit l'état d'une exécution jusqu'au `replicaTimeout` du job plus 180 s, pour le démarrage et le tirage de
l'image: 600 s pour la migration (`infra/modules/migrate-database-job.bicep`), donc 52 lectures, et 900 s pour le
test de fumée (`infra/modules/smoke-test-job.bicep`), donc 72 lectures. `Succeeded` rend 0; `Failed`, `Stopped` ou
`Degraded` rend 1; un job qui n'a pas fini après ses lectures rend 1, avec
`<job>: still <état> after <n> reads, 15 s apart`. Une lecture `az` qui échoue est relue au tour suivant, dans
`run_job` comme dans l'étape 8.

## Déclencher une livraison

Cette partie s'adresse à la personne qui livre une version.

### Qui peut livrer

Une administratrice du dépôt, seule à pouvoir créer un tag `v*` (ruleset « tags v »). Un tag n'est posé et poussé que
sur sa demande explicite.

### Avant de livrer

Le commit à livrer est sur `main`, et sa CI est finie et verte. Un tag posé trop tôt n'attend pas: il est refusé par
`check`. Sur un commit de `main`, `CI`, `Image` et `Infra` tournent à chaque push (`.github/workflows/ci.yml:3-5`,
`.github/workflows/image.yml:3-5`, `.github/workflows/infra.yml:3-5`).

```sh
export GH_PAGER=cat
REPO=SabineLaurent/K-B
git fetch origin
gh run list --repo "$REPO" --commit "$(git rev-parse origin/main)" \
  --json workflowName,event,status,conclusion -q '.[] | [.workflowName, .event, .status, .conclusion] | @tsv'
# attendu, sur fd956430: « CI push completed success », « Image push completed success » et « Infra push completed success »
# (avec deux « Dependabot Updates dynamic completed success », que check ne compte pas)
```

### Poser le tag

Un numéro nouveau à chaque version, jamais réutilisé. Le premier est `v0.1.0`: le 0 dit « avant la 1.0 »; `v1.0.0`
est gardé pour la version de la soutenance (choix du plan de #415).

```sh
VERSION=<vX.Y.Z, jamais posée>
git tag -a "$VERSION" -m "$VERSION" origin/main
git push origin "$VERSION"
gh run list --repo "$REPO" --workflow deploy.yml --limit 1    # l'exécution du tag, quelques secondes plus tard
gh run watch --repo "$REPO" <id de l'exécution>
```

### C'est livré

C'est livré quand les deux jobs sont verts et que la dernière ligne de `deploy` est `caj-kb-smoke-test: Succeeded`.
Une livraison complète a pris 4 minutes 13 s
([La livraison témoin `v0.1.0`](#la-livraison-temoin-v010)).

### Relancer une livraison refusée

Pour relancer une livraison refusée parce que la CI n'était pas finie ou verte: relancer d'abord la CI du commit
(« <span lang="en">Re-run failed jobs</span> », ou `gh run rerun <id> --failed`), puis, une fois verte, l'exécution
du tag (« <span lang="en">Re-run all jobs</span> », ou `gh run rerun <id>`).

### Revenir en arrière

Revenir en arrière, c'est livrer de nouveau le tag précédent. Son image existe déjà: elle n'est pas reconstruite.

- Dans les 30 jours: « <span lang="en">Re-run all jobs</span> » sur l'exécution de ce tag.
- Au-delà: `gh workflow run deploy.yml --repo "$REPO" --ref <tag précédent>`.

## Installer la chaîne

L'installation se fait une fois, à la main: par une administratrice du dépôt GitHub pour les réglages de GitHub,
et par une propriétaire (Owner) du groupe de ressources Azure pour le Bicep, qui donne des rôles aux identités, ce
que la CI n'a jamais le droit de faire. Les commandes de chaque étape sont dans
[le README de l'infrastructure](https://github.com/SabineLaurent/K-B/blob/main/infra/README.md), qui en garde la seule
copie. L'ordre compte.

1. **Le socle Azure** (`infra/README.md`, « Appliquer », étapes 0 à 4): la passe 1 du Bicep crée entre autres le
    registre et l'identité `id-kb-deploy`; une première image est poussée à la main; les secrets des API sont posés
    dans le coffre.
2. **Les réglages de GitHub** (`infra/README.md`, « Les réglages de GitHub, une fois, avant la passe 2 »):
    - l'environnement `production`, que seuls les tags `v*.*.*` atteignent;
    - le ruleset « tags v »: créer ou supprimer un tag `v*` est réservé au rôle
        « <span lang="en">Repository admin</span> »;
    - le ruleset « tags v immuables »: personne ne déplace un tag `v*`.

    Ils se posent avant la passe 2. Sinon, un workflow de branche qui déclarerait `production` créerait
    l'environnement sans règle, et obtiendrait un jeton.

3. **La passe 2 du Bicep** (`infra/README.md`, « 5. Seconde passe »): elle crée les apps et les jobs, et, par
    `deploy-access.bicep`, la confiance et les droits d'`id-kb-deploy`:
    - un *<span lang="en">federated identity credential</span>* `github-production`, d'émetteur
        `https://token.actions.githubusercontent.com` et de sujet
        `repo:SabineLaurent@189640103/K-B@1383589029:environment:production` (`infra/main.bicep`);
    - AcrPush et Reader sur le registre;
    - Container Apps Contributor sur chaque app, et Container Apps Jobs Contributor sur chaque job de
        `deployment.json`.

    `id-kb-deploy` n'a aucun rôle sur le coffre, le stockage ni la base.

4. **Les secrets du dépôt** (`infra/README.md`, « Les secrets du dépôt, après la passe 2 »): les cinq du tableau de
    [Configurer la chaîne](#configurer-la-chaine).

### Vérifier l'installation

En lecture seule:

```sh
export GH_PAGER=cat
REPO=SabineLaurent/K-B
RG=<groupe de ressources>
gh api "repos/$REPO/environments/production/deployment-branch-policies" -q '.branch_policies[] | [.name, .type]'
gh api "repos/$REPO/rulesets" -q '.[] | [.id, .name, .target, .enforcement] | @tsv'
gh api "repos/$REPO/rulesets/<id>" -q '.bypass_actors'    # pour chacun des deux rulesets de tags
gh secret list --repo "$REPO"    # les noms, jamais les valeurs
az identity federated-credential list --identity-name id-kb-deploy -g "$RG" --query "[].{name:name,subject:subject}" -o table
```

La règle de l'environnement est `["v*.*.*","tag"]`; les rulesets sont
« Basic-rules-main-protect » (`branch`), « tags v » et « tags v immuables » (`tag`), tous trois `active`; « tags v »
a pour seul contournement le rôle 5 (« <span lang="en">Repository admin</span> »), et « tags v immuables » n'en a
aucun; les cinq secrets sont là. La dernière commande n'a pas été lancée pour cette fiche: le sujet attendu est celui
du Bicep, et la connexion de `v0.1.0` l'a utilisé ([La livraison témoin `v0.1.0`](#la-livraison-temoin-v010)).

## Configurer la chaîne

| Réglage | Où | Valeur | Ce qu'il change |
|---|---|---|---|
| `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` | secrets du dépôt | l'identifiant client d'`id-kb-deploy`, le tenant et l'abonnement | la connexion OIDC de `azure/login` |
| `KB_RESOURCE_GROUP`, `KB_REGISTRY` | secrets du dépôt | le groupe de ressources et le nom du registre | les cibles de chaque commande `az` |
| environnement `production` | réglages du dépôt | une seule règle de déploiement: les tags `v*.*.*` | le seul job qui reçoit un jeton accepté par `id-kb-deploy` |
| `infra/deployment.json` | dépôt | `apps`: `ca-kb-data-api`, `ca-kb-ai-api`, `ca-kb-web` (`infra/deployment.json:2`); `jobs`: `caj-kb-smoke-test`, `caj-kb-migrate-database`, `caj-kb-daily-routine`, `caj-kb-digest-watch` | lu par le Bicep pour les rôles (`loadJsonContent`, `infra/main.bicep:61`, `:479-480`) et par le workflow pour les images (`jq`, `.github/workflows/deploy.yml:167`, `:173`, `:184`) |
| nombre de lectures et écart | `deploy.yml` | 52 et 72 lectures pour les jobs, 40 pour les révisions, 15 s | les attentes; celles d'un job suivent son `replicaTimeout` plus 180 s |

Ces identifiants ne sont pas des mots de passe. Ils sont des secrets pour que GitHub les masque dans les journaux
d'exécution, et chaque commande `az` du workflow n'affiche rien (`-o none`), affiche une requête étroite
(`--query`), ou passe sa sortie à `jq`.

**Un job nouveau** se déclare d'abord dans le Bicep, puis s'ajoute à `deployment.json` (`infra/main.bicep`). La
passe 2 suivante lui donne le rôle d'`id-kb-deploy`, et le workflow met ensuite son image à jour.

**Une passe 2 après une livraison** prend pour `imageTag` la version en ligne, et non un SHA plus ancien: sinon,
elle remettrait l'ancienne image (`infra/README.md`, « 5. Seconde passe », qui donne la commande qui lit la
version en ligne).

## Tester la chaîne

### Les refus attendus

Le tableau suivant donne une ligne par refus. « Vu » dit s'il a été observé sur une exécution réelle de GitHub, ou seulement simulé par la
session de #415, avec de faux `az` et `gh` ou un registre local
([note du 2026-11-06](https://github.com/SabineLaurent/K-B/blob/main/docs/journaling/2026-11-06-deployer-une-version-taguee-par-oidc.md), « Preuve »).

| Cas | Refusé par | Ce qui s'affiche | Vu |
|---|---|---|---|
| une référence qui n'est pas un tag de version: `v01.2.3`, ou une branche donnée à `workflow_dispatch` | `check`, étape 1 | `not a version tag vMAJOR.MINOR.PATCH: <ref>` | simulé (`v01.2.3`, `v1.2`, `v1.2.3-rc1` et `refs/heads/main` refusés, `v0.1.0` accepté) |
| un tag sur la tête d'une branche | `check`, étape 2 | `v0.0.1 is not on main: 80d1327e80c6d0eac338c4b35bd1fe1a4eedd86d` | exécution 42289900589: `check` en échec, `deploy` `skipped` |
| un tag sur un commit d'une branche déjà fusionnée | `check`, étape 2 | `<tag> is not on main: <sha>` | simulé (`7f5de09` refusé, sa fusion `fde743e` acceptée) |
| une CI en cours, rouge, absente, ou faite seulement de `Deploy` ou de Dependabot | `check`, étape 3 | `the CI of <sha> is not finished and green` | simulé; une CI verte est acceptée, même avec un Dependabot en cours ou rouge, et un `Deploy` rouge ne compte pas |
| un job sans environnement qui demande un jeton à Azure | `id-kb-deploy` | `AADSTS700213: No matching federated identity record found for presented assertion subject 'repo:SabineLaurent@189640103/K-B@1383589029:ref:refs/heads/test/oidc-outside-production'` | exécution 42293728980 (workflow d'essai sur une branche supprimée ensuite), job `without-environment` |
| un job de branche qui déclare `production` | la règle de l'environnement | le job échoue avant toute étape (<q lang="en">Branch … is not allowed to deploy to production due to environment protection rules</q>, relevé par la note) | même exécution, job `with-environment` (0 étape) |
| un tag supprimé puis recréé sur un autre commit | `deploy`, étape 3 | `the image of <tag> was built from another commit: <sha>` | non essayé; la lecture du label et du « <span lang="en">not found</span> » l'est (registre local) |
| un job de `run_job` qui finit en `Failed` ou `Degraded`, ou ne finit pas | `deploy`, étapes 5 et 9 | `<job>: Failed`, ou `<job>: still <état> after <n> reads, 15 s apart` | simulé |
| une révision jamais prête, à une autre image, ou restée l'ancienne | `deploy`, étape 8 | `not ready at the image of <tag> after 40 reads, 15 s apart: <apps>` | simulé |

Le ruleset « tags v » n'a pas été essayé par un compte qui n'est pas administrateur. Le push de
`v0.0.1` par un compte administrateur a affiché <q lang="en">Bypassed rule violations… creations being restricted</q>
(note).

### La livraison témoin `v0.1.0`

Le tag annoté `v0.1.0` est posé sur `ccf1455`, un commit de fusion de `main`. Son exécution, 42429577646 (push du
tag, `success`), est le test de chaque étape sur Azure. Les lignes citées dans cette section sont lues dans son
journal (digest abrégé).

`check`, de 00:24:09 à 00:24:17Z: les trois étapes passent. La troisième liste quatre workflows,
`.github/workflows/postgresql.yml`, `.github/workflows/infra.yml`, `.github/workflows/image.yml` et
`.github/workflows/ci.yml`, tous `completed success`. `postgresql.yml` est entré
depuis dans `ci.yml`, comme job `tests-postgresql` (`86a1c94`).

`deploy`, de 00:24:20 à 00:28:22Z:

| # | Étape | Ligne lue | Heure (UTC) |
|---|---|---|---|
| 1 | `azure/login` | `subject claim - repo:SabineLaurent@189640103/K-B@1383589029:environment:production`, puis `Azure CLI login succeeds by using OIDC.` | 00:24:24, 00:24:25 |
| 2 | `Signs in to the registry` | `Login Succeeded` | 00:24:31 |
| 3 | `Builds and pushes the image of the tag, unless it is there` | l'image est construite (elle n'existait pas), puis `v0.1.0: sha256:37c6d42b…16a9fab2` | 00:25:00 |
| 5 | `Migrates the base` | `caj-kb-migrate-database: Succeeded` | 00:25:58 |
| 6 | `Sets the apps to the image of the tag` | `ca-kb-data-api: v0.1.0 (sha256:37c6d42b…16a9fab2)`, `ca-kb-ai-api: v0.1.0 (…)` | 00:26:15, 00:26:28 |
| 7 | `Sets the jobs to the image of the tag` | `caj-kb-smoke-test: v0.1.0 (…)`, `caj-kb-migrate-database: v0.1.0 (…)` | 00:26:47, 00:27:06 |
| 8 | `Waits for the revisions of the apps at the image of the tag` | `the latest revision of each app is ready at v0.1.0 (sha256:37c6d42b…16a9fab2)`, à la première lecture | 00:27:11 |
| 9 | `Runs the smoke test` | `caj-kb-smoke-test: Succeeded` | 00:28:19 |

Relu ensuite par `az` (note du 2026-11-06, « Preuve »): les deux apps, leur modèle comme leur
révision `--0000002` (`Healthy`), et les deux jobs sont au digest de `k-b:v0.1.0`. Le site, `ca-kb-web`, n'était
pas encore dans `deployment.json`: il y est entré par `f43677d6` (#571). L'étape 6 de la livraison de
`v0.1.5` (exécution 43230567404) écrit `ca-kb-web: v0.1.5 (sha256:…)`, après les deux API.

**Une fusion ne déploie rien**: de `ccf1455` à `b412323`, `main` a reçu 18 fusions
(`git log --first-parent --merges ccf1455..b412323`), et `Deploy` n'a toujours que deux exécutions, celle de
`v0.1.0` et celle du refus de `v0.0.1` (`gh run list --workflow deploy.yml`).

## Quand une livraison échoue

**Lire d'abord** l'étape en échec et ses dernières lignes:

```sh
gh run view <id> --repo "$REPO" --log-failed
```

Chaque étape écrit ce qu'elle a observé (tableaux de [Le job `check`](#le-job-check) et de
[Le job `deploy`](#le-job-deploy)). **Rien ne revient tout seul**: si une étape échoue en route, celles déjà faites
restent sur la nouvelle version (la base migrée, des apps ou des jobs), jusqu'à une nouvelle livraison. Le tableau
suivant donne, pour chaque étape en échec, ce qui a déjà changé en ligne et quoi faire.

| Étape en échec | Ce qui a déjà changé en ligne | Quoi faire |
|---|---|---|
| `check` | rien | lire le message. CI pas finie ou rouge: la relancer, puis l'exécution du tag. Tag hors de `main` ou mal formé: poser un tag nouveau, correct, sur un commit de `main` (un tag `v*` ne se déplace pas) |
| `azure/login` | rien | comparer le `subject claim` qu'affiche l'étape au sujet du *<span lang="en">federated identity credential</span>* (`az identity federated-credential list`, [Vérifier l'installation](#verifier-linstallation)), et vérifier les trois secrets `AZURE_*` (`gh secret list`) |
| `Signs in to the registry` | rien | vérifier `KB_REGISTRY` et les rôles AcrPush et Reader d'`id-kb-deploy` sur le registre |
| `Builds and pushes…` | au plus, l'image du tag dans le registre | `was built from another commit`: le tag a été recréé ailleurs, livrer un numéro nouveau. `no digest for the image of <tag>` ou `the image <digest> was not built from <sha>`: le digest ou le label ne se lisent pas comme prévu. Le commentaire de l'étape nomme un cas: un runner passé au stockage containerd pousserait un index, dont le label ne se lit plus. Toute autre erreur de lecture est affichée telle quelle |
| `Migrates the base` | la base a pu être migrée, et `caj-kb-migrate-database` est à l'image du tag | lire le journal du job dans `log-kb` ([Le journal d'un job](#le-journal-dun-job)), corriger, livrer une version nouvelle; ou revenir au tag précédent |
| `Sets the apps…`, `Sets the jobs…` | la base est migrée et `caj-kb-migrate-database` est à l'image du tag; les apps et les jobs déjà nommés par une ligne `<nom>: <tag> (sha256:…)` le sont aussi, et au plus celui dont la mise à jour était en cours | revenir au tag précédent, ou livrer une version corrigée |
| `Waits for the revisions…` | la base est migrée; le modèle de chaque app et de chaque job est à l'image du tag, mais la révision prête d'une app peut encore être l'ancienne | lire l'état des révisions et les journaux système ([L'état des révisions](#letat-des-revisions), [Le journal d'un job](#le-journal-dun-job)), puis revenir au tag précédent |
| `Runs the smoke test` | tout est à la nouvelle version | lire le journal du test de fumée ([Le test de fumée](#le-test-de-fumee)), puis revenir au tag précédent si une API ne répond pas ou si une sonde reçoit un autre statut |

### L'état des révisions

L'état des révisions d'une app (attendu: `Healthy`):

```sh
az containerapp revision list -n <app> -g "$RG" --query "[].{name:name,health:properties.healthState,replicas:properties.replicas}" -o table
```

### Le journal d'un job

Le journal d'un job se lit dans l'espace Log Analytics `log-kb`, quelques minutes après sa fin.
`az containerapp job logs show` ne lit qu'une exécution en cours: après, il répond `No replicas found`.

```sh
WS=$(az monitor log-analytics workspace show -n log-kb -g "$RG" --query customerId -o tsv)
az monitor log-analytics query -w "$WS" -o tsv \
  --analytics-query "ContainerAppConsoleLogs | where TimeGenerated > ago(1h) and isnotempty(JobName) | order by TimeGenerated asc" \
  --query "[].[TimeGenerated, Log]"
```

Le démarrage d'une app, le tirage de l'image et le réveil d'une app à 0 réplique sont dans
`ContainerAppSystemLogs`, à interroger de la même façon.

### Le test de fumée

Le test de fumée réussi écrit `smoke test finished in … s: 9 of 9 checks passed`. Ses neuf contrôles tournent
toujours, et chaque échec a sa ligne, avec son état:

- pour le `/health` d'une API: `health_failed`, `health_timeout`, `health_unavailable` ou `health_invalid_response`;
- pour une sonde sans clé (#499), trois par API: une route à clé (`GET /items`,
    `POST /digests`) qui doit rendre 401, `GET /docs` qui doit rendre 404, et `HEAD /health` qui doit rendre 405:
    `probe_unexpected_status` avec le statut reçu, `probe_timeout` ou `probe_unavailable`;
- pour le stockage d'échange: `exchange_storage_no_token` (l'identité du job sans jeton, refusée ou injoignable),
    `exchange_storage_forbidden`, `exchange_storage_unauthorized`, `exchange_storage_not_found`,
    `exchange_storage_unavailable` ou `exchange_storage_failed`.

Son code de sortie: 0 si les neuf contrôles passent, 1 si l'un échoue, 2 si rien n'est contrôlé (une variable
manque ou est refusée), rendus par `src/k_b/commands/smoke_test_command.py`; 143 sur SIGTERM et 130 sur SIGINT,
rendus par `src/k_b/cli.py`, `kb smoke-test` étant dans `COMMANDS_STOPPED_BY_SIGTERM` (`src/k_b/commands/sigterm.py`).
Leurs valeurs sont dans `src/k_b/commands/exit_codes.py`.

## Limites, lues le 2026-11-08

- **Aucune validation humaine avant la mise en ligne.** L'environnement `production` n'a que sa règle des tags:
    aucun validateur, et `can_admins_bypass: true` (`gh api repos/SabineLaurent/K-B/environments/production`). L'étape
    d'`infra/README.md` qui fait de l'administratrice du dépôt la validatrice de chaque livraison (`reviewers`,
    `can_admins_bypass: false`) n'est pas appliquée. Un tag poussé part donc en ligne sans autre geste. Ce risque a
    été accepté jusqu'au 2026-11-08 (`infra/README.md`).
- **Pas de retour automatique**: revenir en arrière, c'est livrer le tag précédent.
- **Pas de cache entre deux tags**: une version nouvelle se construit en entier.
- **Une passe 2 faite à la main** repose l'image par son tag (`k-b:<TAG>`), une référence que l'on peut réécrire, et
    non par son digest. La livraison suivante la repinne par digest (#455).
- **Les jobs planifiés ne sont pas essayés par la livraison**: un tag change l'image de `caj-kb-daily-routine` et de
    `caj-kb-digest-watch` (étape 7), sans les lancer. Une image fautive ne se voit qu'à leur exécution suivante, au cron
    (`infra/README.md`, « Lire une exécution »).
