# Déployer une version taguée sur `main`, par OIDC

- **Date** : 2026-11-06
- **Branche** : `feat/tag-deployment`
- **Issue** : #415
- **Fichiers principaux** : `.github/workflows/deploy.yml`, `infra/modules/deploy-access.bicep`,
  `infra/main.bicep`, `infra/deployment.json`, `infra/README.md` (« Déployer une version »)

Suite de la note `2026-11-06-mettre-en-ligne-le-squelette-sur-azure.md` (#414). Elle couvre les commits 3ccab2f
(le workflow, l'identité, ses rôles) et bc2c806 (l'image par son digest, les documents : registre, journal ADR,
`MEMORY.md`).

## Le pourquoi

#414 a mis K-B en ligne à la main : Sabine construisait l'image, la poussait, puis relançait le Bicep. #415 en
fait une livraison continue. Un tag de version nouveau, posé sur `main`, part en ligne sans autre geste. Une simple
fusion ne déploie rien. C'est la décision de Sabine du 06/11 : on déploie quand un tag précis est posé, pas à
chaque fusion.

Le risque est connu (constat 6, accepté par Sabine). Qui peut changer l'image d'un job se sert de ses secrets et de
son identité. Tout repose donc sur une question : **qui peut obtenir le droit de déployer ?** Le travail porte
surtout là-dessus.

## Le comment

### Aucun secret pour se connecter à Azure : OIDC

GitHub Actions ne garde aucun mot de passe Azure. À chaque exécution, GitHub signe un jeton court qui dit d'où il
vient, et Azure l'échange contre un accès, à une condition : l'identité `id-kb-deploy` doit faire confiance à ce
jeton. C'est le *federated identity credential* :

```bicep
resource githubCredential 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2024-11-30' = {
  parent: deployIdentity
  name: 'github-production'
  properties: {
    issuer: 'https://token.actions.githubusercontent.com'
    subject: githubSubject
```
(`infra/modules/deploy-access.bicep:25-30`)

Le `subject` doit être, au caractère près, celui que porte le jeton :

```bicep
var githubDeploySubject = 'repo:SabineLaurent@189640103/K-B@1383589029:environment:production'
```
(`infra/main.bicep:47`)

Il ne nomme ni une branche ni un tag, mais un **environnement GitHub**, `production`. Seul un job qui déclare
cet environnement reçoit un jeton de ce sujet (`.github/workflows/deploy.yml:52`).

Les deux nombres sont les identifiants de la propriétaire et du dépôt. K-B a été créé après le 15/07/2026, et
GitHub lui donne cette forme « immuable » : renommer le dépôt, ou en créer un autre du même nom, ne la reproduit
pas. La relecture du plan l'a trouvé. Le sujet sans les nombres n'aurait jamais correspondu.

### Le verrou n'est pas dans le workflow

Le contrôle du workflow paraît être la sécurité :

```bash
sha=$(git rev-parse "$GITHUB_REF^{commit}")
if ! git rev-list --first-parent origin/main | grep -qx "$sha"; then
```
(`.github/workflows/deploy.yml:42-43`)

Il refuse un tag dont le commit n'est pas sur la première lignée de `main`, c'est-à-dire les commits de `main`
lui-même, commits de fusion compris. `--is-ancestor` aurait aussi accepté la tête d'une branche déjà fusionnée.

Mais un tag poussé lance **le workflow du commit tagué**. Un tag posé sur une branche dont le `deploy.yml` serait
modifié ferait tourner ce workflow-là, sans contrôle. Ce contrôle ne protège donc que d'une erreur. Le verrou est
ailleurs, en trois pièces (`infra/README.md`, « Où est le verrou ») :
- **le ruleset « tags v »** : seuls les administrateurs du dépôt créent ou suppriment un tag `v*` ;
- **le ruleset « tags v immuables »** : personne ne déplace un tag ;
- **l'environnement `production`** : il n'est atteint que par un tag `v*.*.*`, et c'est le seul que
  `id-kb-deploy` accepte.

Ces réglages se posent avant la passe Bicep qui crée la connexion. Un job qui déclare un environnement
inexistant le crée, sans règle : avant les réglages, n'importe quelle branche aurait pu l'atteindre.

### Des droits sur chaque ressource, jamais sur le groupe

```bicep
resource appRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for (name, index) in appNames: {
    name: guid(apps[index].id, deployIdentity.id, containerAppsContributorRoleId)
    scope: apps[index]
```
(`infra/modules/deploy-access.bicep:65-68`)

`id-kb-deploy` a quatre rôles, chacun sur une ressource (`infra/modules/deploy-access.bicep:53-89`) :
- AcrPush et Reader sur le registre, pour pousser l'image (Reader parce que `az acr login` lit le registre par ARM) ;
- Container Apps Contributor sur chaque app ;
- Container Apps Jobs Contributor sur chaque job.

Il n'a rien sur le coffre, le stockage ni les données. Les apps et les jobs, `caj-kb-migrate-database` de #421 compris, viennent d'une seule liste,
`infra/deployment.json`. Le Bicep la lit pour donner les rôles (`loadJsonContent`, `infra/main.bicep:43`), et le
workflow pour mettre les images à jour (`jq`).

### Une image jamais écrasée, déployée par son digest

```bash
digest=$(docker buildx imagetools inspect "$IMAGE" --format '{{ .Manifest.Digest }}')
…
pinned="$REGISTRY.azurecr.io/k-b@$digest"
if [ "$(docker buildx imagetools inspect "$pinned" --format "$label")" != "$SHA" ]; then
```
(`.github/workflows/deploy.yml:97-103`)

L'image `k-b:<tag>` porte en label le SHA du commit dont elle vient. Le workflow la construit seulement si elle
n'existe pas, et seule une réponse « not found » déclenche la construction. Si elle existe déjà, deux cas :
- **même commit** : c'est un retour en arrière, et l'image est redéployée sans être reconstruite ;
- **autre commit** : le tag a été supprimé puis recréé ailleurs, et le déploiement s'arrête.

Les apps et les jobs reçoivent ensuite l'image par son digest, l'empreinte de son contenu. Une réplique qui se
réveille de 0 tire exactement cette image, même si quelqu'un réécrit le tag.

### Les journaux deviennent publics

Le dépôt devient public le 08/11, et ses journaux d'exécution avec lui. Les identifiants Azure (client, tenant,
abonnement, groupe, registre) sont donc des **secrets** du dépôt : ce ne sont pas des mots de passe, mais GitHub
masque un secret partout où il apparaît. Chaque commande `az` passe en `-o none` ou par une `--query` étroite.
`az containerapp update` afficherait sinon toute la configuration de l'app.

## Choix faits et options écartées

| Choix | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Un tag nouveau `vX.Y.Z` par version, jamais déplacé (Sabine, 06/11) | l'historique des versions reste lisible ; revenir en arrière = redéployer le tag précédent | une branche `production` ; un tag mobile `deploy` (retaguer, pousser en force, pas d'historique) |
| Premier tag `v0.1.0` (Sabine, avec le plan) | le 0 dit « avant la 1.0 », juste pour un POC | `v1.0.0`, gardé pour la version de la soutenance |
| OIDC lié à l'environnement `production` (session) | aucun secret Azure dans GitHub ; jeton court, d'une seule source | un secret de client : à garder, à renouveler, à voler |
| Déployer sans validation jusqu'au 08/11 (Sabine, risque accepté) | la validation (« required reviewers ») n'existe qu'en dépôt public pour son plan | attendre le 08/11 pour le premier tag (la recommandation de la session) |
| Pas de Managed Identity Operator (session, après relecture) | le `PATCH` de `az containerapp update` ne porte pas l'identité | le donner par précaution : un droit de plus pour rien |
| Image par digest (revue de sécurité, tranché par time-knight) | une réplique tire l'image déployée, même si le tag est réécrit | verrouiller le tag dans ACR : droit incertain, étape à défaire |
| Une seule liste `infra/deployment.json` (session) | le Bicep et le workflow ne peuvent pas diverger | deux listes ; lire les jobs dans Azure (droit sur tout le groupe) |
| Test de fumée en fin de déploiement (Sabine, avec le plan) | la preuve que la version déployée répond | s'arrêter à la mise à jour, qui ne dit pas si les apps démarrent |
| `workflow_dispatch` (Sabine, avec le plan) | redéployer un tag après les 30 jours de relance de GitHub | la relance seule |
| Identifiants en secrets du dépôt (session) | masqués dans les journaux publics | des variables, affichées en clair |

Imposés par une consigne : la CI n'applique jamais le Bicep (#411 : il donne des rôles, droit d'Owner) ; les
actions sont épinglées par SHA (#234) ; un workflow nouveau a son propre fichier (règle des axes).

## Preuve

| Sortie observée | Ce que ça démontre |
|---|---|
| Avant le code : `az identity show -n id-kb-deploy` → `ResourceNotFound` ; `gh workflow view deploy.yml` → `HTTP 404` (collé dans #415) | le test rouge |
| `gh api repos/SabineLaurent/K-B/actions/oidc/customization/sub` → `use_immutable_subject: true`, `repo:SabineLaurent@189640103/K-B@1383589029` | le sujet du federated credential est le bon |
| Simulation locale de `check` : `v0.1.0` accepté ; `v01.2.3`, `v1.2`, `v1.2.3-rc1`, `refs/heads/main` refusés ; `fde743e` (fusion) accepté, `7f5de09` (commit de branche fusionnée) refusé, alors que `--is-ancestor` l'aurait accepté | le format du tag et la première lignée |
| Registre local : `imagetools inspect` lit le label `abc123` et le digest `sha256:…` ; un tag absent répond `not found` (sortie 1) | la lecture du label, du digest et du « not found » |
| `az bicep build` sans avertissement | le Bicep est valide |
| `/security-review` (xhigh) : aucun constat à 8 ou plus | aucune faille trouvée avant d'appliquer |
| Essai 5.1 (06/11, 20:37Z) : `v0.0.1` sur la tête de la branche ; au push, « Bypassed rule violations… creations being restricted » ; exécution 42289900589, `check` en échec (« v0.0.1 is not on main: 80d1327… »), `deploy` `skipped` ; suppression : « Bypassed… Cannot delete this tag » | un tag hors de `main` est refusé ; la règle des tags s'applique, et Sabine la contourne comme administratrice (`actor_id 5` = « Repository admin », vu dans les réglages) |
| Fonction `run_job` avec un faux `az` : `Succeeded` rend 0, `Failed` et `Degraded` rendent 1, un job qui ne finit pas rend 1 après `polls × 15 s` | l'attente d'un job, migration et test de fumée |
| Essais 5.2 et 5.3 (exécution 42293728980, branche temporaire supprimée ensuite) : sans environnement, `azure/login` reçoit « AADSTS700213: No matching federated identity record found for presented assertion subject 'repo:SabineLaurent@189640103/K-B@1383589029:ref:refs/heads/test/oidc-outside-production' » ; un job de branche qui déclare `production` est refusé avant toute étape (« Branch … is not allowed to deploy to production due to environment protection rules ») | la connexion n'existe que depuis `production`, et une branche ne l'atteint pas ; le préfixe immuable du sujet est celui que GitHub émet |
| *(à venir)* `v0.1.0` : les apps et le job au digest de `k-b:v0.1.0`, `caj-kb-smoke-test` `Succeeded` | le critère de l'issue |

## Ce que tu dois pouvoir défendre

1. **Qui peut déployer, aujourd'hui ?**
   - Celui qui peut pousser un tag `v*`, c'est-à-dire toi, administratrice, ou une session qui a tes droits.
   - Ni une PR de fork ni Dependabot n'obtiennent de jeton OIDC.
   - Une branche ne peut pas atteindre l'environnement `production`.
   - Jusqu'au 08/11, rien d'autre ne s'interpose : c'est le risque que tu as accepté. Il est compensé par la règle
     du `MEMORY.md` : aucune session ne pose de tag sans ta demande.
2. **Pourquoi le contrôle « sur `main` » ne suffit-il pas ?** Parce que le workflow qui tourne est celui du commit
   tagué. Le verrou est dans les réglages de GitHub et dans le sujet de l'identité (`deploy-access.bicep:25-30`).
3. **Que se passe-t-il si un tag est supprimé puis recréé sur un autre commit ?** L'image `k-b:<tag>` existe déjà
   avec l'ancien SHA en label : le déploiement s'arrête (`deploy.yml:84-88`).
4. **Pourquoi l'identité de déploiement peut-elle lire les secrets ?** Les rôles Container Apps couvrent
   `listSecrets`. Mais qui change l'image d'un job peut de toute façon se servir de ses secrets : c'est le
   constat 6, propre à toute livraison continue, accepté et écrit au registre.
5. **Comment revenir en arrière ?**
   - Dans les 30 jours, en relançant l'exécution du tag précédent.
   - Au-delà, par `gh workflow run deploy.yml --ref <tag>`.
   - Dans les deux cas, l'image existe déjà : elle est redéployée sans être reconstruite.

## Zones non vérifiées

- `az acr login` avec AcrPush seul : la doc ne tranche pas. Reader est donné par précaution, non essayé sans lui.
- Le `PATCH` de `az containerapp update` sans `assign/action` : lu dans le code d'azure-cli par le relecteur, pas
  encore essayé. Le repli est écrit (Container Apps Jobs Operator sur `cae-kb`).
- `azure/login` avec des rôles posés seulement sur des ressources, sans rien sur l'abonnement : non essayé.
- `{{ .Manifest.Digest }}` sur une image poussée par le pilote `docker` du runner : essayé sur un registre local
  avec le pilote `docker-container`.
- La fin du sujet, `:environment:production` : le préfixe immuable est confirmé par l'essai 5.2, la fin par la doc de GitHub. Le premier tag `v0.1.0` le prouvera.

## Ce qui reste

- La passe 2 qui crée `id-kb-deploy` et ses rôles : après la fusion de #421, une passe à la fois.
- Les essais 5.1 à 5.3, puis le premier tag `v0.1.0`, sur ta demande.
- Le 08/11 : toi en « required reviewer », sans contournement pour les administrateurs.
- Une passe Bicep faite à la main repose une image par tag, pas par digest : l'outil des passes (#455).
