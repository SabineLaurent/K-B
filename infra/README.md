# Infrastructure de K-B sur Azure

Le Bicep de ce dossier décrit les ressources de K-B dans Azure. `main.bicep` appelle un module par famille de
ressources (`modules/`). Les ressources portent l'étiquette `project=k-b` et sont créées dans la région du groupe
de ressources ; le budget, qui n'a ni étiquette ni région, compte les coûts de cette étiquette.

| Module | Ressource | Issue |
|---|---|---|
| `container-apps-environment.bicep` | environnement Container Apps `cae-kb` : profil Consumption seul, sans VNet, sans destination de journaux | #411 |
| `budget.bicep` | budget `budget-kb` : 30 €/mois des coûts étiquetés `project=k-b`, e-mail à 50 % et 100 % du réel, à 100 % de la prévision ; rien n'est coupé au dépassement | #437 |

## Vérifier

La CI (`.github/workflows/infra.yml`, job `bicep-build`) lance `az bicep build` sur toute PR qui touche `infra/`,
sans aucun droit Azure. Sur le Mac, avec la même version de Bicep :

```sh
az bicep install --version v0.48.1
# SHA256 de bicep-osx-arm64 v0.48.1 (Mac Apple Silicon), à changer avec la version
echo "62cd5958c62fa1b738e9b69f24799fabddb90ed83fdb7d6d2563dde376ce479d  $HOME/.azure/bin/bicep" | shasum -a 256 -c
az bicep build --file infra/main.bicep --stdout > /dev/null
```

## Appliquer (Sabine, à la main)

Ces fichiers donneront des rôles aux identités, ce qui demande le droit d'Owner sur le groupe : la CI ne l'a jamais.
D'abord l'aperçu, puis la création. L'adresse des alertes du budget se passe au déploiement : elle n'est jamais
écrite dans le dépôt, mais elle reste dans l'historique des déploiements du groupe, côté Azure.

```sh
RG=<groupe de ressources>
EMAIL=<adresse des alertes du budget>
az deployment group what-if --resource-group "$RG" --template-file infra/main.bicep --parameters budgetContactEmail="$EMAIL"
az deployment group create --resource-group "$RG" --template-file infra/main.bicep --parameters budgetContactEmail="$EMAIL"
```

Vérifier le budget une fois créé :

```sh
az consumption budget list --resource-group "$RG" --query "[].{name:name,amount:amount,timeGrain:timeGrain,filter:filter,notifications:notifications}"
```

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
