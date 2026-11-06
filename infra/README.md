# Infrastructure de K-B sur Azure

Le Bicep de ce dossier décrit les ressources de K-B dans Azure. `main.bicep` appelle un module par famille de
ressources (`modules/`). Les ressources portent l'étiquette `project=k-b` et sont créées dans la région du groupe
de ressources ; le budget, qui n'a ni étiquette ni région, compte les coûts de cette étiquette.

`main.bicep` se déploie en **deux passes**. Sans `imageTag`, il pose le socle, dont le serveur PostgreSQL (#421). Avec
`imageTag`, il ajoute les deux API, les deux jobs (`caj-kb-smoke-test`, `caj-kb-migrate-database`) et les rôles sur
les secrets. Chaque passe repose le socle, le serveur et l'identité de `caj-kb-migrate-database` compris. Entre les
deux passes, l'image est poussée dans le registre et les secrets sont posés dans le coffre (« Appliquer »).

| Module | Ressource | Passe | Issue |
|---|---|---|---|
| `log-analytics.bicep` | espace Log Analytics `log-kb` : 30 jours de rétention, plafond de 0,2 Go par jour | 1 | #414 |
| `container-apps-environment.bicep` | environnement Container Apps `cae-kb` : profil Consumption seul, sans VNet ; journaux vers `log-kb` par Azure Monitor, sans clé ; trafic chiffré entre les apps | 1 | #411, #414 |
| `identities.bicep` | identités managées `id-kb-ai-api`, `id-kb-data-api`, `id-kb-smoke-test`, et `id-kb-deploy` (le déploiement continu) | 1 | #414, #415 |
| `container-registry.bicep` | registre `crkb…` (ACR Basic), sans utilisateur admin ; AcrPull pour les trois identités | 1 | #414 |
| `key-vault.bicep` | coffre `kv-kb-…` en RBAC, suppression réversible 7 jours ; Key Vault Secrets Officer pour l'opératrice | 1 | #414 |
| `exchange-storage.bicep` | compte Blob `stkbexchange…`, clé partagée coupée ; conteneur `smoke-test`, lisible par `id-kb-smoke-test` seul | 1 | #414 (#420 le complète) |
| `budget.bicep` | budget `budget-kb` : 30 €/mois des coûts étiquetés `project=k-b`, e-mail à 50 % et 100 % du réel, à 100 % de la prévision ; rien n'est coupé au dépassement | 1 | #437 |
| `postgresql-server.bicep` | serveur PostgreSQL 18 flexible `pgsql-kb-…` (`Standard_B1ms`), Entra seul, 32 Gio, sauvegardes 7 jours, règle de pare-feu « services Azure » (« La base PostgreSQL ») | 1 | #421 |
| `key-vault-secret-access.bicep` | Key Vault Secrets User pour chaque identité, sur chacun de ses secrets seulement | 2 | #414 |
| `api-container-app.bicep` | `ca-kb-data-api` et `ca-kb-ai-api` : ingress interne seul, HTTPS, 0 à 1 réplique, sondes `GET /health` | 2 | #414 |
| `smoke-test-job.bicep` | job manuel `caj-kb-smoke-test`, qui lance `kb smoke-test` | 2 | #414 |
| `migrate-database-job.bicep` | identité `id-kb-migrate-database` et son AcrPull ; job manuel `caj-kb-migrate-database`, qui lance `kb migrate-database` | 1 (l'identité), 2 (le job) | #421 |
| `deploy-access.bicep` | pour `id-kb-deploy` : connexion OIDC depuis l'environnement GitHub `production` seul ; AcrPush et Reader sur le registre, Container Apps Contributor sur chaque app, Container Apps Jobs Contributor sur chaque job de `deployment.json` | 2 | #415 |

## Noms des ressources

- **Préfixe** : l'abréviation du type de ressource dans le Cloud Adoption Framework de Microsoft :
  - `cae` pour l'environnement, `ca` pour une app, `caj` pour un job ;
  - `cr` pour le registre, `kv` pour le coffre, `st` pour un compte de stockage, `log` pour l'espace de journaux,
    `id` pour une identité managée ;
  - `pgsql` pour la base (#421).

  Le budget n'est pas dans cette liste : `budget-kb` suit le même modèle. Après le préfixe viennent `kb`, puis le
  rôle de la pièce (`ca-kb-data-api`).
- **Suffixe** : `take(uniqueString(resourceGroup().id), 8)` (`main.bicep`), pour les seuls noms qu'Azure veut uniques
  dans tout Azure, parce que la ressource a une adresse publique : le registre, le coffre et le stockage.
  - La graine est l'identifiant complet du groupe de ressources : le même groupe donne toujours le même suffixe. Il
    ne faut jamais changer la graine après un déploiement, sinon chaque ressource serait recréée sous un autre nom.
  - L'empreinte est déterministe, mais elle n'est pas garantie unique.
- **8 caractères, et non les 13 de `uniqueString`** : un compte de stockage a 3 à 24 caractères, minuscules et
  chiffres seulement. `stkbexchange` (12) plus 13 donnerait 25, refusé ; avec 8, on obtient 20. Le registre n'admet
  que des lettres et des chiffres, sans tiret. Le coffre a 3 à 24 caractères ; les tirets y sont permis, mais pas deux
  de suite.
- **Ni l'environnement ni la région dans le nom** : le CAF demande de n'y mettre que ce qui ne change pas, et de
  porter le reste par des étiquettes. D'où l'étiquette `project=k-b`.

Sources (Microsoft Learn, lues le 2026-11-06) :
[abréviations du CAF](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-abbreviations),
[convention de nommage du CAF](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-naming),
[génération des noms en Bicep](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/patterns-name-generation),
[règles des noms par ressource](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/resource-name-rules),
[comptes de stockage](https://learn.microsoft.com/en-us/azure/storage/common/storage-account-overview).

## Vérifier

La CI (`.github/workflows/infra.yml`, job `bicep-build`) lance `az bicep build` sur toute PR qui touche `infra/`,
sans aucun droit Azure. Sur le Mac, avec la même version de Bicep :

```sh
az bicep install --version v0.48.1
# SHA256 de bicep-osx-arm64 v0.48.1 (Mac Apple Silicon), à changer avec la version
echo "62cd5958c62fa1b738e9b69f24799fabddb90ed83fdb7d6d2563dde376ce479d  $HOME/.azure/bin/bicep" | shasum -a 256 -c
az bicep build --file infra/main.bicep --stdout > /dev/null
```

Le build ne doit donner aucun avertissement : un avertissement de type inconnu signale une version d'API que cette
version de Bicep ne connaît pas. La CI ne le vérifie pas encore (#452).

## Appliquer (Sabine, à la main)

Ces fichiers donnent des rôles aux identités, ce qui demande le droit d'Owner sur le groupe : la CI ne l'a jamais.
Chaque passe se fait en deux temps : l'aperçu (`what-if`), puis la création (`create`), par la même commande. Les
commandes se lancent depuis la racine du dépôt. Toute nouvelle passe reprend **tous** les paramètres :
- sans `imageTag`, les API et le job ne sont pas touchés, et restent tels quels ;
- avec une étiquette plus ancienne, l'image d'avant revient.

Les étapes ci-dessous sont celles de la première mise en ligne, le 2026-11-06 (#414), avec les pièges rencontrés.

### 0. Les variables du shell

```sh
RG=<groupe de ressources>
EMAIL=<adresse des alertes du budget>
OPERATOR=$(az ad signed-in-user show --query id -o tsv)
OPERATOR_UPN=$(az ad signed-in-user show --query userPrincipalName -o tsv)
# Refuse une valeur vide, ou laissée entre chevrons.
kb_check() {
  for value in "$@"; do
    case "$value" in ''|*'<'*) echo "une valeur est vide ou encore un gabarit" >&2; return 1 ;; esac
  done
}
kb_check "$RG" "$EMAIL" "$OPERATOR" "$OPERATOR_UPN" && echo ok
```

`OPERATOR_UPN` fait de l'opératrice l'administratrice Entra du serveur PostgreSQL (#421).

Chaque `<…>` se remplace par sa valeur. Une valeur laissée entre chevrons part telle quelle : le 2026-11-06, une
adresse `<adresse>` a fait refuser le budget (« Notification cannot have invalid email addresses »), et le reste du
déploiement a été créé sans lui. `kb_check` refuse aussi une variable vide, par exemple dans un nouveau terminal où
elle n'a pas été posée.

Chaque `az deployment` qui suit commence par `kb_check … &&`. Dans un shell interactif, un contrôle qui échoue
n'arrête pas les lignes collées après lui : seul le `&&` empêche l'envoi. Dans un nouveau terminal, `kb_check`
n'existe pas encore : la commande échoue (`command not found`), et le `&&` bloque aussi.

L'adresse des alertes du budget se passe au déploiement : elle n'est jamais écrite dans le dépôt, mais elle reste
dans l'historique des déploiements du groupe, côté Azure, et dans la sortie du `what-if`.

### 1. Les fournisseurs de ressources

Le rôle de Lecteur de l'abonnement suffit pour cette lecture :

```sh
for ns in Microsoft.App Microsoft.ContainerRegistry Microsoft.KeyVault Microsoft.OperationalInsights Microsoft.Insights Microsoft.ManagedIdentity Microsoft.Storage Microsoft.DBforPostgreSQL; do
  printf '%s ' "$ns"; az provider show -n "$ns" --query registrationState -o tsv
done
```

Les huit doivent répondre `Registered`. Si l'un d'eux manque, seul un propriétaire de l'abonnement peut
l'enregistrer.

### 2. Première passe : le socle

```sh
kb_check "$RG" "$EMAIL" "$OPERATOR" "$OPERATOR_UPN" && az deployment group what-if -g "$RG" -f infra/main.bicep \
  -p budgetContactEmail="$EMAIL" operatorObjectId="$OPERATOR" operatorPrincipalName="$OPERATOR_UPN"
kb_check "$RG" "$EMAIL" "$OPERATOR" "$OPERATOR_UPN" && az deployment group create -g "$RG" -f infra/main.bicep \
  -p budgetContactEmail="$EMAIL" operatorObjectId="$OPERATOR" operatorPrincipalName="$OPERATOR_UPN" \
  --query "{state:properties.provisioningState,outputs:properties.outputs}"
```

L'aperçu attendu à la première fois :
- **à créer** : `log-kb` et son paramètre de diagnostic, le registre et ses 3 rôles AcrPull, le coffre et le rôle de
  l'opératrice, les 3 identités, le compte de stockage, son conteneur `smoke-test` et le rôle du job ;
- **à modifier** : `cae-kb` (les journaux et le chiffrement entre les apps), et `budget-kb`.
  - Pour `budget-kb`, c'est du bruit : `endDate` disparaît, et le format de `startDate` change. Sans date de fin,
    Azure en remet une à 10 ans.

La création peut dépasser 2 minutes. Elle doit répondre `Succeeded`, avec les noms du registre et du coffre :

```sh
REGISTRY=$(az deployment group show -g "$RG" -n main --query properties.outputs.registryName.value -o tsv)
KV=$(az deployment group show -g "$RG" -n main --query properties.outputs.keyVaultName.value -o tsv)
```

Une seconde création lancée pendant que la première tourne est refusée (`DeploymentActive`), sans effet.

### 3. Pousser l'image

Depuis une copie propre et à jour de `main`, pas depuis une branche : l'image doit être celle du commit dont elle
porte le SHA.

```sh
git status --porcelain            # rien : la copie est propre
TAG=$(git rev-parse --short HEAD)
az acr login --name "$REGISTRY"
docker buildx build --platform linux/amd64 --tag "$REGISTRY.azurecr.io/k-b:$TAG" --push .
az acr repository show-tags -n "$REGISTRY" --repository k-b -o tsv    # l'étiquette $TAG
```

Le point final de `docker buildx build` est le contexte de construction, c'est-à-dire le dossier courant. S'il
manque, la commande s'arrête sur `'docker buildx build' requires 1 argument`.

L'image ne se construit pas par `az acr build` : les tâches ACR sont suspendues sur les crédits gratuits d'Azure.

### 4. Poser les secrets

Dans son propre terminal, et non par le `!` de Claude Code : la saisie sans écho (`read -s`) demande un vrai
clavier. La valeur ne passe ni par l'écran, ni par l'historique du shell : `-o none` coupe la sortie, qui
afficherait sinon la valeur.

```sh
# Les 3 clés d'API : générées (43 caractères), jamais affichées.
for name in kb-ai-api-key-kb-digest kb-ai-api-key-kb-trend-report kb-data-api-key-ai-digest; do
  az keyvault secret set --vault-name "$KV" --name "$name" \
    --file <(python3 -c 'import secrets; print(secrets.token_urlsafe(32), end="")') -o none
done
# Les 3 secrets qui existent déjà : chacun collé sans écho, puis Entrée.
for name in kb-llm-api-key kb-ai-github-token kb-otlp-headers; do
  printf '%s : ' "$name"; read -rs VALUE; echo
  az keyvault secret set --vault-name "$KV" --name "$name" --file <(printf '%s' "$VALUE") -o none
  unset VALUE
done
az keyvault secret list --vault-name "$KV" --query "[].name" -o tsv    # les 6 noms, jamais les valeurs
```

| Secret | Contenu | Lu par |
|---|---|---|
| `kb-ai-api-key-kb-digest` | clé du client `KB_DIGEST` de l'API IA (généré) | `ca-kb-ai-api` |
| `kb-ai-api-key-kb-trend-report` | clé du client `KB_TREND_REPORT` de l'API IA (généré) | `ca-kb-ai-api` |
| `kb-data-api-key-ai-digest` | clé de l'API IA vers l'API de données (généré) | les deux API |
| `kb-llm-api-key` | clé du modèle (Azure AI Foundry) | `ca-kb-ai-api` |
| `kb-ai-github-token` | jeton GitHub des comptes rendus des tendances | `ca-kb-ai-api` |
| `kb-otlp-headers` | en-tête OTLP de Grafana Cloud (`KB_OTLP_HEADERS`) | `ca-kb-ai-api` |

Ce que dit chaque cas :
- **Rien ne s'affiche** : le secret est posé.
- **`ERROR: … Forbidden`** : le rôle Key Vault Secrets Officer de la passe 1 n'est pas encore actif. Il lui faut
  jusqu'à 10 minutes : relancer la commande.
- **Jamais Entrée sur une invite vide.** Elle poserait une version vide par-dessus la bonne, et l'API IA refuserait
  de démarrer. Pour sortir sans rien poser : Ctrl-C.

Pour refaire un seul secret (erreur, mauvaise valeur collée, ou rotation), la nouvelle version remplace l'ancienne.
Container Apps lit la dernière version dans les 30 minutes (référence sans version). Mais un conteneur qui tourne
garde ses variables d'environnement, et un redémarrage automatique n'est pas vérifié. Après la nouvelle valeur, on
redémarre donc la révision active de chaque app qui lit ce secret (colonne « Lu par »).

```sh
name=kb-ai-github-token
printf '%s : ' "$name"; read -rs VALUE; echo
az keyvault secret set --vault-name "$KV" --name "$name" --file <(printf '%s' "$VALUE") -o none
unset VALUE
for app in ca-kb-ai-api; do    # ca-kb-data-api ca-kb-ai-api pour kb-data-api-key-ai-digest
  az containerapp revision restart -n "$app" -g "$RG" \
    --revision "$(az containerapp revision list -n "$app" -g "$RG" --query "[?properties.active].name | [0]" -o tsv)"
done
```

Limite : `kb-data-api-key-ai-digest` est lu par les deux API. Tant qu'elles n'ont pas toutes deux la nouvelle
valeur, jusqu'à 30 minutes, l'API IA reçoit 401 de l'API de données. Si les 401 continuent après le redémarrage,
redémarrer de nouveau une fois les 30 minutes passées.

### 5. Seconde passe : les API et le job

Les trois valeurs sont celles du `.env` de l'opératrice : `KB_LLM_BASE_URL`, `KB_LLM_MODEL` et `KB_OTLP_ENDPOINT`
(l'adresse de base, sans `/v1/metrics`). Ce ne sont pas des secrets.

```sh
LLM_URL=<KB_LLM_BASE_URL>
LLM_MODEL=<KB_LLM_MODEL>
OTLP=<KB_OTLP_ENDPOINT>
kb_check "$RG" "$EMAIL" "$OPERATOR" "$OPERATOR_UPN" "$TAG" "$LLM_URL" "$LLM_MODEL" "$OTLP" && az deployment group what-if \
  -g "$RG" -f infra/main.bicep \
  -p budgetContactEmail="$EMAIL" operatorObjectId="$OPERATOR" operatorPrincipalName="$OPERATOR_UPN" imageTag="$TAG" \
     llmBaseUrl="$LLM_URL" llmModel="$LLM_MODEL" otlpEndpoint="$OTLP"
kb_check "$RG" "$EMAIL" "$OPERATOR" "$OPERATOR_UPN" "$TAG" "$LLM_URL" "$LLM_MODEL" "$OTLP" && az deployment group create \
  -g "$RG" -f infra/main.bicep \
  -p budgetContactEmail="$EMAIL" operatorObjectId="$OPERATOR" operatorPrincipalName="$OPERATOR_UPN" imageTag="$TAG" \
     llmBaseUrl="$LLM_URL" llmModel="$LLM_MODEL" otlpEndpoint="$OTLP" \
  --query "{state:properties.provisioningState}"
```

Le Bicep ne refuse pas ces valeurs vides : la passe 1 les laisse vides. Le contrôle vient donc de `kb_check`. Sans
lui, un `TAG` vide referait la passe 1 sans erreur, et une adresse vide déploierait une API IA qui refuse de démarrer
(`KB_OTLP_ENDPOINT: not set, while KB_OTLP_HEADERS is`).

L'aperçu attendu :
- **à créer** : `ca-kb-data-api`, `ca-kb-ai-api`, `caj-kb-smoke-test`, et 7 rôles Key Vault Secrets User, un par
  secret et par identité (`kb-data-api-key-ai-digest` en reçoit deux) ;
- **à modifier** : du bruit. L'aperçu ne résout pas les `reference(…)` (identifiants des identités, URL du coffre),
  et il liste les valeurs par défaut qu'Azure renvoie sans que le Bicep les écrive.

Les rôles sur les secrets se créent dans le même déploiement que les apps. Si une app échoue sur
« unable to fetch secret », c'est qu'ils ne sont pas encore actifs : relancer la même commande 10 minutes plus tard.

Une fois une version déployée par un tag (« Déployer une version »), `TAG` est la version en ligne, et non le SHA
de l'étape 3. Sinon, la passe remettrait l'ancienne image. Les apps tiennent leur image par son digest. La version
se retrouve à partir de ce digest :

```sh
DIGEST=$(az containerapp show -n ca-kb-ai-api -g "$RG" --query "properties.template.containers[0].image" -o tsv | cut -d@ -f2)
az acr manifest list-metadata -r "$REGISTRY" -n k-b --query "[?digest=='$DIGEST'].tags[]" -o tsv
```

Limite : la passe repose alors `k-b:<TAG>`, la même image, mais par une référence que l'on peut réécrire. Le
prochain déploiement par tag la repinne par digest. L'outil des passes (#455) pourra lire le digest en ligne.

### 6. Vérifier la mise en ligne

Les deux apps sont internes, et leur révision est saine :

```sh
for app in ca-kb-data-api ca-kb-ai-api; do
  az containerapp show -n "$app" -g "$RG" --query "{external:properties.configuration.ingress.external,fqdn:properties.configuration.ingress.fqdn}"
  az containerapp revision list -n "$app" -g "$RG" --query "[].{health:properties.healthState,replicas:properties.replicas}"
done
```

Attendu : `external: false`, et `Healthy`. Pour l'API de données, une révision saine montre aussi que ses sondes
portent le bon `Host` : sans lui, elle répond 400 à `/health`.

Le job d'essai (critère de #414) :

```sh
EXEC=$(az containerapp job start -n caj-kb-smoke-test -g "$RG" --query name -o tsv)
az containerapp job execution show -n caj-kb-smoke-test -g "$RG" --job-execution-name "$EXEC" --query properties.status
az containerapp job execution list -n caj-kb-smoke-test -g "$RG" --query "[].{name:name,status:properties.status,start:properties.startTime}" -o table
```

Attendu : `Running`, puis `Succeeded`.

Ce qu'a écrit le job se lit dans `log-kb`, quelques minutes après sa fin. `az containerapp job logs show` ne lit
qu'une exécution en cours : après, il répond `No replicas found`.

```sh
WS=$(az monitor log-analytics workspace show -n log-kb -g "$RG" --query customerId -o tsv)
az monitor log-analytics query -w "$WS" -o tsv \
  --analytics-query "ContainerAppConsoleLogs | where TimeGenerated > ago(1h) and isnotempty(JobName) | order by TimeGenerated asc" \
  --query "[].[TimeGenerated, Log]"
```

Attendu : `smoke test finished in … s: 3 of 3 checks passed`. Les API n'écrivent pas un `/health` réussi, seulement
un échec : avec `ContainerAppName` à la place de `JobName`, aucune ligne `status=400 route=/health` ne doit
apparaître. Le démarrage, le tirage de l'image et le réveil d'une app à 0 réplique sont dans
`ContainerAppSystemLogs`, à interroger de la même façon.

Mesuré le 06/11 : 1 s pour le test quand les API sont éveillées, 50 s quand elles sont au repos. L'API de données
répond 26 s après la première demande, et l'API IA 20 s après. Le job les appelle l'une après l'autre.

## Déployer une version

Un tag de version posé sur `main` part en ligne (#415). Une fusion ne déploie rien. Le workflow
`.github/workflows/deploy.yml` a deux jobs :
- **`check`** refuse un tag qui n'a pas la forme `vMAJEUR.MINEUR.CORRECTIF`, ou dont le commit n'est pas sur la
  première lignée de `main`.
- **`deploy`**, dans l'environnement GitHub `production`, fait le reste dans cet ordre :
  1. il se connecte à Azure en `id-kb-deploy`, par OIDC ;
  2. il construit et pousse `k-b:<tag>`, sauf si l'image existe déjà, construite depuis ce même commit ;
  3. il met les apps et les jobs de `deployment.json` à l'image du tag, par son digest (`k-b@sha256:…`) :
     une réplique qui se réveille tire l'image déployée, même si le tag est réécrit ;
  4. il lance `caj-kb-smoke-test` et attend `Succeeded`.

La migration de la base (#421) se placera entre l'image et les apps.

**Où est le verrou.** Le workflow qui tourne est celui du commit tagué. Le contrôle de `check` ne protège donc que
d'une erreur. Le verrou tient en trois pièces :
- **le ruleset « tags v »** réserve la création et la suppression des tags `v*` aux administrateurs du dépôt ;
- **le ruleset « tags v immuables »** interdit de déplacer un tag, à tout le monde. Supprimer puis recréer un tag
  revient à le déplacer, mais le déploiement échoue alors : l'image existante porte le SHA de l'ancien commit
  (label `org.opencontainers.image.revision`) ;
- **`id-kb-deploy` ne fait confiance qu'aux jetons de l'environnement `production`**, que seuls les tags
  `v*.*.*` peuvent atteindre.

Une administratrice peut modifier un ruleset : « personne ne déplace un tag » est une règle de travail, pas un
verrou absolu. Aucune session Claude ne pose ni ne pousse de tag sans une demande explicite de Sabine.

### Les réglages de GitHub, une fois, avant la passe 2

Avant la passe 2, qui crée la connexion de `id-kb-deploy`. Sinon, un workflow de branche qui déclarerait
`production` créerait l'environnement sans règle, et obtiendrait un jeton.

```sh
REPO=SabineLaurent/K-B
# L'environnement production, atteint par les seuls tags v*.*.*.
gh api -X PUT "repos/$REPO/environments/production" --input - -q .name <<'EOF'
{"deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}}
EOF
gh api -X POST "repos/$REPO/environments/production/deployment-branch-policies" -f name='v*.*.*' -f type=tag -q .name
# Création et suppression des tags v* : les administrateurs seuls (actor_id 5, à vérifier ci-dessous).
gh api -X POST "repos/$REPO/rulesets" --input - -q .name <<'EOF'
{"name": "tags v", "target": "tag", "enforcement": "active",
 "conditions": {"ref_name": {"include": ["refs/tags/v*"], "exclude": []}},
 "rules": [{"type": "creation"}, {"type": "deletion"}],
 "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}]}
EOF
# Un tag v* ne se déplace pas : sans contournement.
gh api -X POST "repos/$REPO/rulesets" --input - -q .name <<'EOF'
{"name": "tags v immuables", "target": "tag", "enforcement": "active",
 "conditions": {"ref_name": {"include": ["refs/tags/v*"], "exclude": []}},
 "rules": [{"type": "update", "parameters": {"update_allows_fetch_and_merge": false}}, {"type": "non_fast_forward"}],
 "bypass_actors": []}
EOF
```

À vérifier ensuite :
- dans Settings → Rules → Rulesets → « tags v », la liste des contournements montre « Repository admin ». La doc
  de GitHub ne donne pas le numéro de ce rôle ;
- `gh api "repos/$REPO/environments/production/deployment-branch-policies" -q '.branch_policies[] | [.name, .type]'`
  donne `["v*.*.*","tag"]`.

### Les secrets du dépôt, après la passe 2

Ce sont des identifiants, pas des mots de passe. En secrets, ils sont masqués dans les journaux, publics dès le
08/11. Aucune valeur ne s'affiche.

```sh
CLIENT_ID=$(az deployment group show -g "$RG" -n main --query properties.outputs.deployIdentityClientId.value -o tsv)
kb_check "$RG" "$REGISTRY" "$CLIENT_ID" && {
  gh secret set AZURE_CLIENT_ID --repo "$REPO" --body "$CLIENT_ID"
  gh secret set AZURE_TENANT_ID --repo "$REPO" --body "$(az account show --query tenantId -o tsv)"
  gh secret set AZURE_SUBSCRIPTION_ID --repo "$REPO" --body "$(az account show --query id -o tsv)"
  gh secret set KB_RESOURCE_GROUP --repo "$REPO" --body "$RG"
  gh secret set KB_REGISTRY --repo "$REPO" --body "$REGISTRY"
}
gh secret list --repo "$REPO"    # les 5 noms, jamais les valeurs
```

`az account show` doit être l'abonnement du groupe de ressources (`az group show -n "$RG"` le confirme).

### Poser une version

Sur demande de Sabine seulement, et toujours sur un commit de `main` :

```sh
git -C ~/REPO_GIT/K-B pull --ff-only
git -C ~/REPO_GIT/K-B tag -a v0.1.0 -m "v0.1.0" origin/main
git -C ~/REPO_GIT/K-B push origin v0.1.0
# Quelques secondes plus tard, l'exécution du tag :
gh run list --repo "$REPO" --workflow deploy.yml --limit 1
gh run watch --repo "$REPO" <id de l'exécution>
```

Un tag nouveau à chaque version, jamais déplacé. Une exécution en attente est annulée si une plus récente arrive ;
celle qui tourne va jusqu'au bout.

**Revenir en arrière**, c'est redéployer le tag précédent : l'image existe déjà, rien n'est reconstruit.
- Dans les 30 jours : « Re-run all jobs » sur l'exécution de ce tag.
- Au-delà : `gh workflow run deploy.yml --repo "$REPO" --ref v0.1.0`.

**Un job nouveau** (#421, #413) s'ajoute à `deployment.json`. Le Bicep lui donne le rôle de `id-kb-deploy`, et le
workflow met son image à jour.

### Le 08/11, une fois le dépôt public

Jusque-là, un tag déploie sans validation : c'est un risque accepté par Sabine le 06/11 (journal ADR, registre).
Les « required reviewers » ne s'ouvrent qu'aux dépôts publics. Le PUT remplace tout l'environnement, d'où la règle
des tags reprise dans le même corps.

```sh
gh api -X PUT "repos/$REPO/environments/production" --input - -q '.protection_rules[].type' <<'EOF'
{"deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true},
 "reviewers": [{"type": "User", "id": 189640103}], "prevent_self_review": false, "can_admins_bypass": false}
EOF
```

`prevent_self_review` reste à `false` : Sabine est la seule à valider. `can_admins_bypass` passe à `false` : sinon,
une administratrice, donc Sabine ou une session qui a ses droits, pourrait passer outre la validation.

Limite : avec ses droits, une session pourrait aussi approuver elle-même un déploiement en attente, par l'API
(`pending_deployments`). La validation reste donc un geste humain. Comme pour la pose d'un tag, seule la règle du
`MEMORY.md` l'en protège : aucune session n'approuve un déploiement.

## Vérifier le budget

```sh
SUB=$(az account show --query id -o tsv)
az rest --method get \
  --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Consumption/budgets/budget-kb?api-version=2024-08-01" \
  --query "properties.{amount:amount,timeGrain:timeGrain,timePeriod:timePeriod,filter:filter,notifications:notifications}"
```

`az consumption budget list` ne suffit pas : il rend `filter: null`, et il ne montre ni `thresholdType` ni `locale`
des alertes (constat du 2026-11-06).

## Relever la facture

Les données de coût arrivent avec retard : jusqu'à 72 h pour un abonnement en paiement à l'utilisation, 8 à 24 h
pour un contrat EA ou MCA ([Microsoft Learn](https://learn.microsoft.com/azure/cost-management-billing/costs/understand-cost-mgt-data)).
Le relevé se fait donc 72 h après la création, en deux requêtes.

Coût par compteur des ressources étiquetées `project=k-b`, jour par jour, depuis le début du mois :

```sh
SUB=$(az account show --query id -o tsv)
az rest --method post \
  --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.CostManagement/query?api-version=2023-11-01" \
  --body '{"type":"ActualCost","timeframe":"MonthToDate","dataset":{"granularity":"Daily","aggregation":{"totalCost":{"name":"Cost","function":"Sum"}},"grouping":[{"type":"Dimension","name":"Meter"}],"filter":{"tags":{"name":"project","operator":"In","values":["k-b"]}}}}' \
  --query "properties.{columns:columns[].name,rows:rows,next:nextLink}"
```

Une réponse vide ne prouve rien si les données ne sont pas encore arrivées. La requête témoin donne le coût de tout
le groupe, jour par jour : les jours relevés doivent y figurer.

```sh
az rest --method post \
  --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.CostManagement/query?api-version=2023-11-01" \
  --body '{"type":"ActualCost","timeframe":"MonthToDate","dataset":{"granularity":"Daily","aggregation":{"totalCost":{"name":"Cost","function":"Sum"}}}}' \
  --query "properties.{columns:columns[].name,rows:rows,next:nextLink}"
```

L'API répond parfois 429 (trop de requêtes) : relancer quelques minutes plus tard.

## La base PostgreSQL (#421)

`modules/postgresql-server.bicep` crée le serveur `pgsql-kb-<suffixe>` : PostgreSQL 18, `Standard_B1ms`
(Burstable), 32 Gio sans croissance automatique, sauvegardes du serveur 7 jours sans géoredondance, sans haute
disponibilité, accès public sans VNet, **Entra seul** (mot de passe coupé), `citext` permise,
`log_error_verbosity = TERSE`, et la règle de pare-feu « services Azure » (`0.0.0.0`). Le serveur se paie à
l'heure, qu'il serve ou non : environ 16 €/mois avec ses 32 Gio (estimation du plan de mise en ligne).

Le Bicep ne crée ni la base `kb` ni les rôles : l'administratrice Entra du serveur les crée en SQL, une fois
(`postgresql/`). Puis le job `caj-kb-migrate-database` lance `kb migrate-database`, qui pose le schéma sur une
base vide et ne fait rien sur une base qui l'a déjà.

| Rôle PostgreSQL | Pour | Droits |
|---|---|---|
| `id-kb-migrate-database` | le job `caj-kb-migrate-database` | `CONNECT`, `USAGE` et `CREATE` sur `public` ; propriétaire des tables |
| `id-kb-data-api` | l'API de données | membre de `kb_reader` : `CONNECT`, `USAGE`, `SELECT` sur les tables |
| `kb_writer` (sans connexion) | la routine quotidienne, avec #330 | `CONNECT`, `USAGE`, `SELECT`, `INSERT`, `UPDATE`, `DELETE` |

Aucun autre rôle ne se connecte à `kb` ni n'y crée rien : `grant-roles.sql` retire à `PUBLIC` les droits
qu'Azure lui laisse.

### Appliquer #421 sur le squelette en ligne

Dans l'ordre, sur le squelette déjà en ligne (#414). Les aperçus attendus, déduits du Bicep, ont été observés à
l'application du 06/11, avec le bruit des étapes 2 et 5 (valeurs par défaut qu'Azure renvoie, sondes permutées,
`reference(…)` non résolus).

1. Les étapes 0 et 1 d'« Appliquer » (`OPERATOR_UPN`, les huit fournisseurs).
2. La première passe (étape 2). Aperçu attendu :
   - **à créer** : `pgsql-kb-<suffixe>`, son administratrice Entra, ses deux paramètres (`azure.extensions`,
     `log_error_verbosity`), sa règle de pare-feu `AllowAllAzureServicesAndResourcesWithinAzureIps`, l'identité
     `id-kb-migrate-database` et son rôle AcrPull sur le registre ;
   - **à modifier** : du bruit seulement, comme à l'étape 2.
3. « Ouvrir une administration », puis « Créer les rôles et la base » (ci-dessous).
4. L'image (étape 3) : elle doit porter le code de #421 (`kb migrate-database`, `KB_DATABASE_AUTH`), que celle de
   #414 n'a pas. Puis « Vérifier la chaîne TLS du job ». L'étape 4 n'a rien de neuf : Entra seul, aucun secret.
5. La seconde passe (étape 5), avec l'étiquette de cette image. Aperçu attendu :
   - **à créer** : `caj-kb-migrate-database` ;
   - **à modifier** : `ca-kb-data-api` (son image, `KB_DATABASE_URL`, `KB_DATABASE_AUTH`, `AZURE_CLIENT_ID`, et
     `identitySettings` : `lifecycle` passe de `None` à `Main`),
     l'image de `ca-kb-ai-api` et de `caj-kb-smoke-test`, et le bruit de l'étape 5.
6. Aussitôt après, `caj-kb-migrate-database` (critère 1 de « Vérifier les trois critères de #421 ») : jusqu'à son
   premier lancement, l'API de données pointe vers une base sans tables. Puis les critères 2 et 3, et « Fermer
   l'administration ».

### Ouvrir une administration

Depuis le Mac, l'adresse publique du Mac est ouverte le temps de l'administration, par `az`, jamais par le
Bicep : une adresse IP resterait dans l'historique des déploiements. Le jeton d'accès sert de mot de passe à
`psql` ; il vit 5 à 60 minutes ([Microsoft Learn](https://learn.microsoft.com/azure/postgresql/security/security-entra-configure)),
il se demande juste avant chaque commande et n'est posé que pour elle (`PGPASSWORD=… psql`, sans `export` : `kb`
refuse une variable `PG*` dans son environnement).

Chaque `psql` de l'administration passe par `admin_psql`, qui pose aussi `search_path` à `pg_catalog` seul
(`PGOPTIONS`) : le rôle du job peut créer des fonctions et des opérateurs dans `public`, et l'un d'eux, s'il
correspond mieux à un appel que celui de `pg_catalog`, s'exécuterait avec les droits de l'administratrice
(CVE-2018-1058). Pour la même raison, l'administratrice ne lit dans `kb` que les catalogues, jamais une table du
job : le code d'une vue ou d'une politique de lignes qu'il y poserait s'exécuterait avec ses droits à elle.

```sh
RG=<groupe de ressources>
IP=<adresse IPv4 publique du Mac>
PG=$(az postgres flexible-server list -g "$RG" --query "[0].name" -o tsv)
FQDN=$(az postgres flexible-server show -g "$RG" -n "$PG" --query fullyQualifiedDomainName -o tsv)
ADMIN=$(az ad signed-in-user show --query userPrincipalName -o tsv)
CONN="host=$FQDN port=5432 user=$ADMIN sslmode=verify-full sslrootcert=system"
token() { az account get-access-token --resource-type oss-rdbms --query accessToken -o tsv; }
admin_psql() {  # admin_psql <base> <arguments de psql>
  PGPASSWORD="$(token)" PGOPTIONS='-c search_path=pg_catalog' psql "$CONN dbname=$1" "${@:2}"
}
az postgres flexible-server firewall-rule create -g "$RG" --server-name "$PG" --name admin-mac \
  --start-ip-address "$IP" --end-ip-address "$IP"
admin_psql postgres -At -c "SHOW search_path"
```

Attendu : `pg_catalog` (vérifié sur Azure le 06/11). `sslrootcert=system` fait
vérifier le certificat du serveur par les autorités de la libssl de `psql` (sur le Mac, celles d'OpenSSL de
Homebrew), et force `verify-full`.

### Créer les rôles et la base (une fois)

Après la première passe de `main.bicep` (étape 2 d'« Appliquer »), qui crée le serveur et les identités
(`id-kb-data-api`, et `id-kb-migrate-database` par `modules/migrate-database-job.bicep`), et avant la seconde
(étape 5), qui crée le job et donne la base à l'API de données. Chaque rôle est rattaché à son identité par l'identifiant de son principal de service, pas par son
nom, qu'une autre identité de l'annuaire peut porter.

```sh
MIGRATE_ID=$(az identity show -g "$RG" -n id-kb-migrate-database --query principalId -o tsv)
DATA_API_ID=$(az identity show -g "$RG" -n id-kb-data-api --query principalId -o tsv)
admin_psql postgres \
  -v migrate_database_principal_id="$MIGRATE_ID" -v data_api_principal_id="$DATA_API_ID" \
  -f infra/postgresql/create-principals.sql
admin_psql kb -v ON_ERROR_STOP=1 -f infra/postgresql/grant-roles.sql
```

`grant-roles.sql` se relance sans rien changer. `create-principals.sql` ne se relance pas : la base `kb` existe
déjà et `CREATE DATABASE` échoue.

### Vérifier la chaîne TLS du job

Le job ouvre la base en `sslmode=verify-full` contre `/etc/ssl/certs/ca-certificates.crt` de l'image. Avant le
premier lancement, la chaîne du serveur se vérifie contre ce même fichier (pare-feu du Mac ouvert) :

```sh
docker run --rm --entrypoint cat k-b:<étiquette de l'image poussée> /etc/ssl/certs/ca-certificates.crt > "$TMPDIR/k-b-ca.crt"
openssl s_client -starttls postgres -connect "$FQDN:5432" -servername "$FQDN" -verify_hostname "$FQDN" \
  -CAfile "$TMPDIR/k-b-ca.crt" -verify_return_error </dev/null 2>&1 | grep "Verify return code"
```

Attendu : `Verify return code: 0 (ok)`.

### Fermer l'administration

```sh
az postgres flexible-server firewall-rule delete -g "$RG" --server-name "$PG" --name admin-mac --yes
az postgres flexible-server firewall-rule list -g "$RG" --server-name "$PG" \
  --query "[].{name:name,start:startIpAddress,end:endIpAddress}" -o table
```

Attendu : la seule règle `AllowAllAzureServicesAndResourcesWithinAzureIps`, de `0.0.0.0` à `0.0.0.0`.

### Vérifier les trois critères de #421

1. `caj-kb-migrate-database` lancé deux fois rend `Succeeded` les deux fois, et la seconde ne change rien. Avant
   et après le second lancement, la même requête (administration ouverte) doit rendre la même ligne : le nombre
   de tables, une empreinte de leurs noms et de leurs droits, et le nombre de lignes écrites depuis le
   démarrage du serveur.

   ```sh
   admin_psql kb -At -c "SELECT count(*), md5(string_agg(c.relname || ':' || coalesce(c.relacl::text, ''), ',' ORDER BY c.relname)), (SELECT sum(n_tup_ins + n_tup_upd + n_tup_del) FROM pg_stat_user_tables) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind = 'r'"
   az containerapp job start -g "$RG" -n caj-kb-migrate-database
   az containerapp job execution list -g "$RG" -n caj-kb-migrate-database \
     --query "[].{name:name,status:properties.status,start:properties.startTime}" -o table
   WS=$(az monitor log-analytics workspace show -n log-kb -g "$RG" --query customerId -o tsv)
   az monitor log-analytics query -w "$WS" -o tsv \
     --analytics-query "ContainerAppConsoleLogs | where TimeGenerated > ago(1h) and JobName == 'caj-kb-migrate-database' | order by TimeGenerated asc" \
     --query "[].[TimeGenerated, Log]"
   ```

   La ligne de résultat du premier lancement est `database created: …`, celle du second
   `database unchanged: … already has its tables`. Elle se lit dans `log-kb` quelques minutes après la fin de
   l'exécution : `az containerapp job logs show` ne lit qu'une exécution en cours (étape 6 d'« Appliquer »).
2. Le mot de passe est coupé : `az postgres flexible-server show -g "$RG" -n "$PG" --query authConfig` rend
   `"passwordAuth": "Disabled"` et `"activeDirectoryAuth": "Enabled"`.
3. Sous `id-kb-data-api`, une écriture est refusée. Dans le catalogue, depuis l'administration :

   ```sh
   admin_psql kb -At -c "SELECT has_table_privilege('id-kb-data-api', 'public.source', 'SELECT'), has_table_privilege('id-kb-data-api', 'public.source', 'INSERT'), has_schema_privilege('id-kb-data-api', 'public', 'CREATE'), has_database_privilege('id-kb-data-api', 'kb', 'TEMPORARY')"
   ```

   Attendu : `t|f|f|f`. Cette lecture seule ne vaut que dans `kb` : dans `postgres`, la base du serveur, les
   identités gardent ce que `PUBLIC` y a (limite acceptée par Sabine le 06/11, journal ADR, « Base en ligne :
   trois rôles, posés par l'administratrice »). Ce qu'il en reste se lit, de même en lecture seule :

   ```sh
   admin_psql postgres -At -c "SELECT has_database_privilege('id-kb-data-api', 'postgres', 'TEMPORARY'), has_schema_privilege('id-kb-data-api', 'public', 'CREATE'), pg_get_userbyid(datdba) FROM pg_database WHERE datname = 'postgres'"
   ```

   Un `t` à l'une des deux premières colonnes ouvre une issue de suite : révoquer `TEMPORARY` et `CREATE` à
   `PUBLIC` dans `postgres`, jamais `CONNECT`, par lequel l'administratrice entre peut-être dans `postgres` pour
   `create-principals.sql`. La troisième nomme le propriétaire de `postgres`, pour cette issue.

   Puis dans l'API elle-même, par son identité :
   `az containerapp exec -g "$RG" -n ca-kb-data-api --command sh`, puis, dans le conteneur :

   ```sh
   python - <<'EOF'
   import os
   from pathlib import Path
   from k_b.database.engine import connect_database
   from k_b.database.location import read_database_location_or_refusal
   location = read_database_location_or_refusal(os.environ, Path(os.environ["KB_DATA_DIR"]))
   connection = connect_database(location)
   print("SELECT", connection.execute("SELECT count(*) FROM source").fetchone())
   connection.rollback()
   for statement in ("INSERT INTO source (source_code, label, source_type, acquisition_mode) VALUES ('probe', 'probe', 'file', 'watch')", "CREATE TABLE probe (n integer)"):
       try:
           connection.execute(statement)
           print("ACCEPTED", statement.split()[0])
       except Exception as error:
           print("REFUSED", statement.split()[0], type(error).__name__, getattr(error, "sqlstate", None))
       connection.rollback()
   connection.close()
   EOF
   ```

   Attendu : `SELECT (7,)` (les sept sources que `kb migrate-database` écrit ; aucun item, #330 amorce la base),
   puis `REFUSED INSERT InsufficientPrivilege 42501` et `REFUSED CREATE InsufficientPrivilege 42501`.
