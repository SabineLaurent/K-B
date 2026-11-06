# Infrastructure de K-B sur Azure

Le Bicep de ce dossier décrit les ressources de K-B dans Azure. `main.bicep` appelle un module par famille de
ressources (`modules/`). Les ressources portent l'étiquette `project=k-b` et sont créées dans la région du groupe
de ressources ; le budget, qui n'a ni étiquette ni région, compte les coûts de cette étiquette.

`main.bicep` se déploie en **deux passes**. Sans `imageTag`, il pose le socle. Avec `imageTag`, il ajoute les deux
API, le job d'essai et les rôles sur les secrets. Entre les deux passes, l'image est poussée dans le registre et les
secrets sont posés dans le coffre (« Appliquer »).

| Module | Ressource | Passe | Issue |
|---|---|---|---|
| `log-analytics.bicep` | espace Log Analytics `log-kb` : 30 jours de rétention, plafond de 0,2 Go par jour | 1 | #414 |
| `container-apps-environment.bicep` | environnement Container Apps `cae-kb` : profil Consumption seul, sans VNet ; journaux vers `log-kb` par Azure Monitor, sans clé ; trafic chiffré entre les apps | 1 | #411, #414 |
| `identities.bicep` | identités managées `id-kb-ai-api`, `id-kb-data-api`, `id-kb-smoke-test` | 1 | #414 |
| `container-registry.bicep` | registre `crkb…` (ACR Basic), sans utilisateur admin ; AcrPull pour les trois identités | 1 | #414 |
| `key-vault.bicep` | coffre `kv-kb-…` en RBAC, suppression réversible 7 jours ; Key Vault Secrets Officer pour l'opératrice | 1 | #414 |
| `exchange-storage.bicep` | compte Blob `stkbexchange…`, clé partagée coupée ; conteneur `smoke-test`, lisible par `id-kb-smoke-test` seul | 1 | #414 (#420 le complète) |
| `budget.bicep` | budget `budget-kb` : 30 €/mois des coûts étiquetés `project=k-b`, e-mail à 50 % et 100 % du réel, à 100 % de la prévision ; rien n'est coupé au dépassement | 1 | #437 |
| `key-vault-secret-access.bicep` | Key Vault Secrets User pour chaque identité, sur chacun de ses secrets seulement | 2 | #414 |
| `api-container-app.bicep` | `ca-kb-data-api` et `ca-kb-ai-api` : ingress interne seul, HTTPS, 0 à 1 réplique, sondes `GET /health` | 2 | #414 |
| `smoke-test-job.bicep` | job manuel `caj-kb-smoke-test`, qui lance `kb smoke-test` | 2 | #414 |

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
# Refuse une valeur vide, ou laissée entre chevrons.
kb_check() {
  for value in "$@"; do
    case "$value" in ''|*'<'*) echo "une valeur est vide ou encore un gabarit" >&2; return 1 ;; esac
  done
}
kb_check "$RG" "$EMAIL" "$OPERATOR" && echo ok
```

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
for ns in Microsoft.App Microsoft.ContainerRegistry Microsoft.KeyVault Microsoft.OperationalInsights Microsoft.Insights Microsoft.ManagedIdentity Microsoft.Storage; do
  printf '%s ' "$ns"; az provider show -n "$ns" --query registrationState -o tsv
done
```

Les sept doivent répondre `Registered`. Si l'un d'eux manque, seul un propriétaire de l'abonnement peut
l'enregistrer.

### 2. Première passe : le socle

```sh
kb_check "$RG" "$EMAIL" "$OPERATOR" && az deployment group what-if -g "$RG" -f infra/main.bicep \
  -p budgetContactEmail="$EMAIL" operatorObjectId="$OPERATOR"
kb_check "$RG" "$EMAIL" "$OPERATOR" && az deployment group create -g "$RG" -f infra/main.bicep \
  -p budgetContactEmail="$EMAIL" operatorObjectId="$OPERATOR" \
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
kb_check "$RG" "$EMAIL" "$OPERATOR" "$TAG" "$LLM_URL" "$LLM_MODEL" "$OTLP" && az deployment group what-if \
  -g "$RG" -f infra/main.bicep \
  -p budgetContactEmail="$EMAIL" operatorObjectId="$OPERATOR" imageTag="$TAG" \
     llmBaseUrl="$LLM_URL" llmModel="$LLM_MODEL" otlpEndpoint="$OTLP"
kb_check "$RG" "$EMAIL" "$OPERATOR" "$TAG" "$LLM_URL" "$LLM_MODEL" "$OTLP" && az deployment group create \
  -g "$RG" -f infra/main.bicep \
  -p budgetContactEmail="$EMAIL" operatorObjectId="$OPERATOR" imageTag="$TAG" \
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
