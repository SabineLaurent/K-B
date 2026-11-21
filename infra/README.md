# Infrastructure de K-B sur Azure

Le Bicep de ce dossier décrit les ressources de K-B dans Azure. `main.bicep` appelle un module par famille de
ressources (`modules/`). Les ressources portent l'étiquette `project=k-b` et sont créées dans la région du groupe
de ressources ; le budget, qui n'a ni étiquette ni région, compte les coûts de cette étiquette.

`main.bicep` se déploie en **deux passes**. Sans `imageTag`, il pose le socle, dont le serveur PostgreSQL (#421). Avec
`imageTag`, il ajoute les deux API, le site (#571), les jobs (`caj-kb-smoke-test`, `caj-kb-migrate-database`,
`caj-kb-daily-routine`, `caj-kb-digest-watch`) et les rôles sur les secrets. Chaque passe repose le socle, le serveur et l'identité de `caj-kb-migrate-database` compris. Entre les
deux passes, l'image est poussée dans le registre et les secrets sont posés dans le coffre (« Appliquer »).

| Module | Ressource | Passe | Issue |
|---|---|---|---|
| `log-analytics.bicep` | espace Log Analytics `log-kb` : 30 jours de rétention, plafond de 0,2 Go par jour | 1 | #414 |
| `container-apps-environment.bicep` | environnement Container Apps `cae-kb` : profil Consumption seul, sans VNet ; journaux vers `log-kb` par Azure Monitor, sans clé ; trafic chiffré entre les apps ; identité système, qui monte `job-data` | 1 | #411, #414, #420 |
| `identities.bicep` | identités managées `id-kb-ai-api`, `id-kb-data-api`, `id-kb-smoke-test`, `id-kb-deploy` (le déploiement continu), `id-kb-daily-routine` et `id-kb-digest-watch` (les jobs planifiés), `id-kb-web` (le site) | 1 | #414, #415, #420, #571 |
| `container-registry.bicep` | registre `crkb…` (ACR Basic), sans utilisateur admin ; AcrPull pour les identités des apps et des jobs | 1 | #414, #330, #423, #571 |
| `key-vault.bicep` | coffre `kv-kb-…` en RBAC, suppression réversible 7 jours ; Key Vault Secrets Officer pour l'opératrice | 1 | #414 |
| `exchange-storage.bicep` | compte Blob `stkbexchange…`, clé partagée coupée ; conteneurs `smoke-test`, `clippings`, `zotero`, `watch`, un rôle par identité et par conteneur ; versions, suppression réversible, effacement des copies Zotero, verrou (« Le stockage ») | 1 | #414, #420, #571 |
| `job-files-storage.bicep` | compte Files `stkbjobfiles…`, partage `job-data` des jobs, monté par l'identité de `cae-kb` ; verrou (« Le stockage ») | 1 | #420 |
| `budget.bicep` | budget `budget-kb` : 40 €/mois des coûts étiquetés `project=k-b`, hébergement et inférence (la ressource du modèle comptée si elle est dans ce groupe de ressources et porte l'étiquette), e-mail à 50 % et 100 % du réel, à 100 % de la prévision ; rien n'est coupé au dépassement | 1 | #437, #632 |
| `container-apps-policies.bicep` | deux politiques intégrées d'Azure Policy assignées au groupe, d'effet `Audit` : `audit-kb-ca-external-ingress` (« Container Apps should disable external network access »), sauf `ca-kb-web`, et `audit-kb-ca-https-only` (« Container Apps should only be accessible over HTTPS ») ; elles n'arrêtent rien, et auditeraient aussi l'app d'un autre projet créée dans le groupe (« La relecture de la configuration ») | 1 | #497 |
| `model-token-alert.bicep` | groupe d'actions `ag-kb-operator` (un e-mail, l'adresse du budget) ; règle `alert-kb-model-tokens` : plus de 400 000 jetons (`TotalTokens`) sur 24 h glissantes, sur toute la ressource du modèle, évaluée toutes les 15 minutes ; rien n'est coupé (« L'alerte sur les jetons du modèle ») | 1, si `modelAccountName` est donné | #501 |
| `postgresql-server.bicep` | serveur PostgreSQL 18 flexible `pgsql-kb-…` (`Standard_B1ms`), Entra seul, 32 Gio, sauvegardes 7 jours, règle de pare-feu « services Azure » (« La base PostgreSQL ») | 1 | #421 |
| `key-vault-secret-access.bicep` | Key Vault Secrets User pour chaque identité, sur chacun de ses secrets seulement | 2 | #414 |
| `api-container-app.bicep` | `ca-kb-data-api`, `ca-kb-ai-api` et `ca-kb-web` : HTTPS, 0 à 1 réplique, sondes `GET /health` ; ingress interne, sauf le site, ouvert par `exposeWeb` derrière la connexion Microsoft Entra (« Le site privé ») | 2 | #414, #571 |
| `smoke-test-job.bicep` | job manuel `caj-kb-smoke-test`, qui lance `kb smoke-test` | 2 | #414 |
| `migrate-database-job.bicep` | identité `id-kb-migrate-database` et son AcrPull ; job manuel `caj-kb-migrate-database`, qui lance `kb migrate-database` | 1 (l'identité), 2 (le job) | #421 |
| `daily-routine-job.bicep` | job planifié `caj-kb-daily-routine`, qui lance `kb daily-routine` chaque jour à 08:00 UTC, sur `job-data` (« La routine quotidienne ») | 2 | #330 |
| `digest-watch-job.bicep` | job planifié `caj-kb-digest-watch`, qui lance `kb digest-watch` à l'heure du paramètre `digestWatchCronExpression`, le lundi et le jeudi à 10:00 UTC par défaut, sur `job-data` (« Les comptes rendus en ligne ») | 2 | #423 |
| `deploy-access.bicep` | pour `id-kb-deploy` : connexion OIDC depuis l'environnement GitHub `production` seul ; AcrPush et Reader sur le registre, Container Apps Contributor sur chaque app, Container Apps Jobs Contributor sur chaque job de `deployment.json` | 2 | #415 |

## Noms des ressources

- **Préfixe** : l'abréviation du type de ressource dans le Cloud Adoption Framework de Microsoft :
  - `cae` pour l'environnement, `ca` pour une app, `caj` pour un job ;
  - `cr` pour le registre, `kv` pour le coffre, `st` pour un compte de stockage, `log` pour l'espace de journaux,
    `id` pour une identité managée ;
  - `pgsql` pour la base (#421) ;
  - `ag` pour le groupe d'actions (#501).

  Le budget n'est pas dans cette liste, ni la règle d'alerte : `budget-kb` et `alert-kb-model-tokens` suivent le même
  modèle. Après le préfixe viennent `kb`, puis le rôle de la pièce (`ca-kb-data-api`). Une assignation de politique
  n'a pas d'abréviation (le CAF ne donne qu'un nom « descriptif » pour une définition, lu le 2026-11-18) :
  `audit-kb-ca-…`, l'effet, `kb`, puis ce qui est audité.
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

La CI (`.github/workflows/infra.yml`, job `bicep-build`) lance `az bicep build` sur toute PR vers `main` et tout
push sur `main`, sans aucun droit Azure ; c'est un contrôle exigé de `main` depuis #496. Sur le Mac, avec la même
version de Bicep :

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
MODEL_ACCOUNT=sabl-certif-resource
MODEL_ID=$(az cognitiveservices account show -n "$MODEL_ACCOUNT" -g "$RG" --query id -o tsv)
# Refuse une valeur vide, ou laissée entre chevrons.
kb_check() {
  for value in "$@"; do
    case "$value" in ''|*'<'*) echo "une valeur est vide ou encore un gabarit" >&2; return 1 ;; esac
  done
}
kb_check "$RG" "$EMAIL" "$OPERATOR" "$OPERATOR_UPN" "$MODEL_ACCOUNT" "$MODEL_ID" && echo ok
```

`OPERATOR_UPN` fait de l'opératrice l'administratrice Entra du serveur PostgreSQL (#421). `MODEL_ACCOUNT` est la
ressource du modèle, dans le même groupe : la règle `alert-kb-model-tokens` la surveille (#501). `MODEL_ID` est vide si
elle n'est pas dans ce groupe, et `kb_check` le refuse.

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
for ns in Microsoft.App Microsoft.ContainerRegistry Microsoft.KeyVault Microsoft.OperationalInsights Microsoft.Insights Microsoft.ManagedIdentity Microsoft.Storage Microsoft.DBforPostgreSQL Microsoft.PolicyInsights; do
  printf '%s ' "$ns"; az provider show -n "$ns" --query registrationState -o tsv
done
```

Les neuf doivent répondre `Registered`. Si l'un d'eux manque, seul un Contributor ou un Owner de l'abonnement peut
l'enregistrer (Learn, « Quickstart: Create a policy assignment to identify non-compliant resources by using a Bicep
file », lu le 2026-11-18). `Microsoft.PolicyInsights` (#497) donne les états de conformité des politiques d'audit :
« `Microsoft.PolicyInsights` must be registered in your Azure subscription ».

### 2. Première passe : le socle

```sh
kb_check "$RG" "$EMAIL" "$OPERATOR" "$OPERATOR_UPN" "$MODEL_ACCOUNT" && az deployment group what-if -g "$RG" -f infra/main.bicep \
  -p budgetContactEmail="$EMAIL" operatorObjectId="$OPERATOR" operatorPrincipalName="$OPERATOR_UPN" \
     modelAccountName="$MODEL_ACCOUNT"
kb_check "$RG" "$EMAIL" "$OPERATOR" "$OPERATOR_UPN" "$MODEL_ACCOUNT" && az deployment group create -g "$RG" -f infra/main.bicep \
  -p budgetContactEmail="$EMAIL" operatorObjectId="$OPERATOR" operatorPrincipalName="$OPERATOR_UPN" \
     modelAccountName="$MODEL_ACCOUNT" \
  --query "{state:properties.provisioningState,outputs:properties.outputs}"
```

Une passe sans `modelAccountName` ne touche pas l'alerte sur les jetons du modèle : en mode incrémental, rien n'est
supprimé, et l'alerte reste telle qu'en ligne.

L'aperçu attendu à la première fois, sur un groupe où `cae-kb` existe déjà (#411) :
- **à créer** :
  - `log-kb` et son paramètre de diagnostic ; le registre et ses 4 rôles AcrPull ; le coffre et le rôle de
    l'opératrice ;
  - les 7 identités : `id-kb-ai-api`, `id-kb-data-api`, `id-kb-smoke-test`, `id-kb-deploy`, `id-kb-daily-routine`,
    `id-kb-digest-watch` et `id-kb-migrate-database` ;
  - `pgsql-kb-…`, son administratrice Entra, ses deux paramètres et sa règle de pare-feu (« La base PostgreSQL ») ;
  - `stkbexchange…`, son service Blob, ses 4 conteneurs, leurs 8 rôles, la règle de cycle de vie et le verrou ;
    `stkbjobfiles…`, son service de fichiers, le partage `job-data`, le rôle SMB MI Admin, le stockage `job-data`
    de `cae-kb` et le verrou (« Le stockage ») ;
  - les deux politiques d'audit, `audit-kb-ca-external-ingress` et `audit-kb-ca-https-only` (#497) ;
- **à modifier** : `cae-kb` (les journaux, le chiffrement entre les apps et l'identité système), et `budget-kb`.
  - Pour `budget-kb`, c'est du bruit : `endDate` disparaît, et le format de `startDate` change. Sans date de fin,
    Azure en remet une à 10 ans.

La création peut dépasser 2 minutes. Elle doit répondre `Succeeded`, avec les noms du registre et du coffre :

```sh
REGISTRY=$(az deployment group show -g "$RG" -n main --query properties.outputs.registryName.value -o tsv)
KV=$(az deployment group show -g "$RG" -n main --query properties.outputs.keyVaultName.value -o tsv)
```

Une seconde création lancée pendant que la première tourne est refusée (`DeploymentActive`), sans effet.

Si la création échoue sur le stockage `job-data` de `cae-kb`, c'est que le rôle SMB MI Admin, créé dans la même
passe, n'est pas encore actif (jusqu'à 10 minutes) : relancer la même commande 10 minutes plus tard.

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
| `kb-data-api-key-web` | clé du site vers l'API de données, client `WEB` (généré, « Le site privé ») | `ca-kb-data-api`, `ca-kb-web` |
| `kb-web-auth-client-secret` | secret client de l'inscription « K-B site », lu par la connexion Entra, jamais par le code (« Le site privé ») | `ca-kb-web` |

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

### 5. Seconde passe : les API, le site et les jobs

Les trois valeurs sont celles du `.env` de l'opératrice : `KB_LLM_BASE_URL`, `KB_LLM_MODEL` et `KB_OTLP_ENDPOINT`
(l'adresse de base, sans `/v1/metrics`). Ce ne sont pas des secrets. `LLM_MODEL` nomme le déploiement de
gpt-6.1-sol : `main.bicep` pose l'effort `low` (`KB_LLM_REASONING_EFFORT`), le plus bas que gpt-6.1-sol accepte ; le
modèle et l'effort partent dans la même passe, jamais l'un sans l'autre (#635). `WEB_APP_ID` est l'ID de l'inscription
« K-B site » (#571), pas un secret non plus. S'il n'y a pas exactement une inscription de ce nom, `WEB_APP_ID` est
vidé, et `kb_check` refuse la passe.

```sh
LLM_URL=<KB_LLM_BASE_URL>
LLM_MODEL=<KB_LLM_MODEL>
OTLP=<KB_OTLP_ENDPOINT>
WEB_APP_ID=$(az ad app list --display-name "K-B site" --query "[].appId" -o tsv)
[ "$(az ad app list --display-name "K-B site" --query "length(@)" -o tsv)" = 1 ] || WEB_APP_ID=''
# Ouvert seulement si sa connexion est déjà posée en ligne : un site à créer, ou sans connexion, reste fermé.
[ "$(az containerapp auth show -n ca-kb-web -g "$RG" --query platform.enabled -o tsv 2>/dev/null)" = true ] \
  && EXPOSE_WEB=true || EXPOSE_WEB=false
kb_check "$RG" "$EMAIL" "$OPERATOR" "$OPERATOR_UPN" "$MODEL_ACCOUNT" "$TAG" "$LLM_URL" "$LLM_MODEL" "$OTLP" "$WEB_APP_ID" && az deployment group what-if \
  -g "$RG" -f infra/main.bicep \
  -p budgetContactEmail="$EMAIL" operatorObjectId="$OPERATOR" operatorPrincipalName="$OPERATOR_UPN" imageTag="$TAG" \
     llmBaseUrl="$LLM_URL" llmModel="$LLM_MODEL" otlpEndpoint="$OTLP" webAuthClientId="$WEB_APP_ID" exposeWeb="$EXPOSE_WEB" \
     modelAccountName="$MODEL_ACCOUNT"
kb_check "$RG" "$EMAIL" "$OPERATOR" "$OPERATOR_UPN" "$MODEL_ACCOUNT" "$TAG" "$LLM_URL" "$LLM_MODEL" "$OTLP" "$WEB_APP_ID" && az deployment group create \
  -g "$RG" -f infra/main.bicep \
  -p budgetContactEmail="$EMAIL" operatorObjectId="$OPERATOR" operatorPrincipalName="$OPERATOR_UPN" imageTag="$TAG" \
     llmBaseUrl="$LLM_URL" llmModel="$LLM_MODEL" otlpEndpoint="$OTLP" webAuthClientId="$WEB_APP_ID" exposeWeb="$EXPOSE_WEB" \
     modelAccountName="$MODEL_ACCOUNT" \
  --query "{state:properties.provisioningState}"
```

`EXPOSE_WEB` vaut `true` seulement si la connexion du site est déjà posée en ligne. Une passe qui crée ou recrée le
site le crée donc fermé, en ingress interne ; il ne s'ouvre qu'à la passe suivante, une fois sa connexion lue (« Le
site privé »). `exposeWeb` oublié ferme le site au lieu de l'ouvrir.

Le Bicep ne refuse pas ces valeurs vides : la passe 1 les laisse vides. Le contrôle vient donc de `kb_check`. Sans
lui, un `TAG` vide referait la passe 1 sans erreur, une adresse vide déploierait une API IA qui refuse de démarrer
(`KB_OTLP_ENDPOINT: not set, while KB_OTLP_HEADERS is`). Un `WEB_APP_ID` vide, s'il passait, ôterait la connexion du
gabarit et laisserait le site en ingress interne (`api-container-app.bicep`, `hasSignIn`).

L'aperçu attendu à la première passe 2, le 2026-11-06 (#414) :
- **à créer** : `ca-kb-data-api`, `ca-kb-ai-api`, `caj-kb-smoke-test`, et 7 rôles Key Vault Secrets User, un par
  secret et par identité (`kb-data-api-key-ai-digest` en reçoit deux) ;
- **à modifier** : du bruit. L'aperçu ne résout pas les `reference(…)` (identifiants des identités, URL du coffre),
  et il liste les valeurs par défaut qu'Azure renvoie sans que le Bicep les écrive.

Une passe qui ajoute une pièce a son aperçu dans la section de la pièce : « Appliquer #420 sur le squelette en
ligne », « La seconde passe, avec le tag » (#330), « La passe A : le site fermé » (#571). Une passe qui n'ajoute
rien ne montre que ce bruit, et l'image des apps et des jobs : après un déploiement par tag, `k-b@sha256:…` devient
`k-b:<TAG>`, la même image si `TAG` est la version en ligne.

Les rôles sur les secrets se créent dans le même déploiement que les apps. Si une app échoue sur
« unable to fetch secret », c'est qu'ils ne sont pas encore actifs : relancer la même commande 10 minutes plus tard.

Une fois une version déployée par un tag (« Déployer une version »), `TAG` est la version en ligne, et non le SHA
de l'étape 3. Sinon, la passe remettrait l'ancienne image. Après un déploiement par tag, les apps tiennent leur image
par son digest (`k-b@sha256:…`) ; après une passe à la main, par son tag (`k-b:<TAG>`). La version se retrouve dans
les deux cas :

```sh
IMAGE=$(az containerapp show -n ca-kb-ai-api -g "$RG" --query "properties.template.containers[0].image" -o tsv)
case "$IMAGE" in
  *@*) az acr manifest list-metadata -r "$REGISTRY" -n k-b --query "[?digest=='${IMAGE#*@}'].tags[]" -o tsv ;;
  *) echo "${IMAGE##*:}" ;;
esac
```

Limite : la passe repose alors `k-b:<TAG>`, la même image, mais par une référence que l'on peut réécrire. Le
prochain déploiement par tag la repinne par digest. L'outil des passes (#455) pourra lire le digest en ligne.

### 6. Vérifier la mise en ligne

Les deux API sont internes, le site est externe (#571), et chaque révision est saine :

```sh
for app in ca-kb-data-api ca-kb-ai-api ca-kb-web; do
  az containerapp show -n "$app" -g "$RG" --query "{external:properties.configuration.ingress.external,fqdn:properties.configuration.ingress.fqdn}"
  az containerapp revision list -n "$app" -g "$RG" --query "[].{health:properties.healthState,replicas:properties.replicas}"
done
```

Attendu : `external: false` pour les deux API, `true` pour `ca-kb-web` une fois ouvert, et `Healthy`. Pour
`ca-kb-web`, `Healthy` ne prouve pas que le site répond (« Le site privé », « Les constats »). Pour l'API de données, une révision saine montre aussi que ses sondes
portent le bon `Host` : sans lui, elle répond 400 à `/health`.

**La relecture de la configuration, à chaque version déployée** (#497) : les requêtes de la relecture du
2026-11-08 (`docs/fiches-veille.md`, API8, « TLS, même pour une API interne »), plus le mode des révisions
(`docs/fiches-veille.md`, API9), en lecture seule.

```sh
DOMAIN=$(az containerapp env show -n cae-kb -g "$RG" --query properties.defaultDomain -o tsv)
for app in ca-kb-data-api ca-kb-ai-api; do
  az containerapp show -n "$app" -g "$RG" \
    --query "properties.configuration.ingress.{external:external, allowInsecure:allowInsecure, transport:transport, customDomains:customDomains}"
  az containerapp show -n "$app" -g "$RG" \
    --query "properties.template.containers[0].env[?name=='KB_DATA_API_URL' || name=='KB_DATA_API_ALLOWED_HOSTS'].{name:name, value:value}"
  az containerapp show -n "$app" -g "$RG" --query properties.configuration.activeRevisionsMode -o tsv
done
az containerapp env show -n cae-kb -g "$RG" \
  --query "{encryption: properties.peerTrafficConfiguration.encryption.enabled, mtls: properties.peerAuthentication.mtls.enabled}"
az containerapp env http-route-config list -n cae-kb -g "$RG"
echo "$DOMAIN"
```

Attendu, comme le 2026-11-08 : pour les deux API, `external` false, `allowInsecure` false, `transport` `Http` et
`customDomains` null ; sur `ca-kb-ai-api`, `KB_DATA_API_URL` = `https://ca-kb-data-api.internal.$DOMAIN` ; sur
`ca-kb-data-api`, `KB_DATA_API_ALLOWED_HOSTS` = `ca-kb-data-api.internal.$DOMAIN` ; `encryption` true, `mtls`
false ; aucune route (`[]`). Et pour les deux API, `Single` : une seule révision active
(`api-container-app.bicep:117`).

**Les politiques d'audit** (`container-apps-policies.bicep`), après une passe qui les crée ou les change :

```sh
az policy assignment list -g "$RG" --query "[?starts_with(name, 'audit-kb-')].{name:name, notScopes:notScopes}" -o json
# Cinq minutes au moins après la passe, le temps qu'une assignation nouvelle s'applique ; puis l'évaluation à la
# demande, attendue jusqu'à sa fin ; sans elle, Azure réévalue une fois toutes les 24 h. Une action, pas une
# lecture : Sabine la lance ; Owner du groupe suffit.
az policy state trigger-scan -g "$RG"
# Par le nom des assignations seulement : les deux ne visent que les apps (Microsoft.App/containerApps).
az policy state list -g "$RG" \
  --query "[?starts_with(policyAssignmentName, 'audit-kb-')].{app:resourceId, policy:policyAssignmentName, state:complianceState}" -o table
# En complément, des comptes seulement : les deux assignations de K-B.
az policy state summarize -g "$RG" \
  --query "policyAssignments[?contains(policyAssignmentId, 'audit-kb-')].{id:policyAssignmentId, results:results}"
```

Attendu : les deux assignations, `audit-kb-ca-external-ingress` avec l'identifiant de `ca-kb-web` dans `notScopes` ;
`ca-kb-data-api` et `ca-kb-ai-api` en `Compliant` pour les deux (`complianceState` ; `isCompliant` est déprécié,
référence REST « Policy States », lue le 2026-11-18) ; `ca-kb-web` absent de `audit-kb-ca-external-ingress`, et en
`Compliant` pour `audit-kb-ca-https-only` (`allowInsecure: false`, `api-container-app.bicep`) ; au `summarize`,
`nonCompliantResources` 0 pour chacune des deux. Une
app d'un autre projet du groupe y figurerait aussi ; le 2026-11-21, il n'y en a aucune (`audit-kb-ca-https-only` compte
3 apps, celles de K-B). Une assignation nouvelle s'applique en cinq minutes environ ;
la fin de l'évaluation n'a pas de délai garanti (page « Get compliance data of Azure resources », « Evaluation
triggers », lue le 2026-11-18).

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

Attendu : `smoke test finished in … s: 9 of 9 checks passed`. Les API n'écrivent pas un `GET /health` réussi,
seulement un échec : avec `ContainerAppName` à la place de `JobName`, aucune ligne `method='GET' route=/health` ne
doit apparaître (un `status=400`, par exemple, est un hôte refusé). Les sondes sans clé (#499) y laissent chacune sa
ligne, attendue : `method='GET' route=/items status=401` pour
l'API de données, `method='POST' route=/digests status=401` pour l'API IA, et pour les deux
`method='GET' route=/docs status=404` et `method='HEAD' route=/health status=405`, toutes avec `client=-` (lignes
relevées le 2026-11-18 sur l'API de données construite hors `sandbox`). Le démarrage, le tirage de l'image et le réveil d'une app à 0 réplique sont dans
`ContainerAppSystemLogs`, à interroger de la même façon.

Mesuré le 06/11 : 1 s pour le test quand les API sont éveillées, 50 s quand elles sont au repos. L'API de données
répond 26 s après la première demande, et l'API IA 20 s après. Le job les appelle l'une après l'autre.

## Déployer une version

Un tag de version posé sur `main` part en ligne (#415). Une fusion ne déploie rien. Le workflow
`.github/workflows/deploy.yml` a deux jobs :
- **`check`** refuse un tag qui n'a pas la forme `vMAJEUR.MINEUR.CORRECTIF`, dont le commit n'est pas sur la
  première lignée de `main`, ou dont la CI n'est pas finie et verte (les exécutions des workflows du dépôt sur ce
  commit, sauf Deploy ; celles que GitHub crée lui-même, comme Dependabot, ne comptent pas).
- **`deploy`**, dans l'environnement GitHub `production`, fait le reste dans cet ordre :
  1. il se connecte à Azure en `id-kb-deploy`, par OIDC ;
  2. il construit et pousse `k-b:<tag>`, sauf si l'image existe déjà, construite depuis ce même commit. Sans
     cache entre deux tags : une version neuve se construit en entier ;
  3. il lance `caj-kb-migrate-database` à cette image et attend `Succeeded`. `kb migrate-database` laisse telle
     quelle une base qui a ses tables : un retour à un tag précédent la relance sans risque ;
  4. il met les apps et les jobs de `deployment.json` à l'image du tag, par son digest (`k-b@sha256:…`) :
     une réplique qui se réveille tire l'image déployée, même si le tag est réécrit ;
  5. il attend que la dernière révision de chaque app soit prête, et que l'image de cette révision soit celle du
     tag (40 lectures, 15 s d'écart). En mode une révision, l'ancienne répond jusque-là, et `/health` rend un texte
     fixe : sans cette attente, le test de fumée pourrait passer sur l'ancienne version ;
  6. il lance `caj-kb-smoke-test` et attend `Succeeded`.

Si une étape échoue, les suivantes ne tournent pas.

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
# Sans défileur : gh en ouvrirait un après la première commande, et les lignes collées s'y perdraient.
export GH_PAGER=cat
REPO=SabineLaurent/K-B
# L'environnement production, atteint par les seuls tags v*.*.*.
gh api -X PUT "repos/$REPO/environments/production" --input - -q .name <<'EOF'
{"deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}}
EOF
gh api -X POST "repos/$REPO/environments/production/deployment-branch-policies" -f name='v*.*.*' -f type=tag -q .name
# Création et suppression des tags v* : les administrateurs seuls (actor_id 5 : « Repository admin »).
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
  de GitHub ne donne pas le numéro de ce rôle : le 5 a été vérifié ainsi le 06/11 ;
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

Sur demande de Sabine seulement, et toujours sur un commit de `main` dont la CI est finie et verte. Un tag posé
trop tôt, ou sur une CI annulée ou rouge, est refusé par `check`. On relance alors d'abord la CI du commit
(« Re-run failed jobs » sur son exécution), puis, une fois verte, « Re-run all jobs » sur l'exécution du tag.

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

**Revenir en arrière**, c'est redéployer le tag précédent : l'image existe déjà, rien n'est reconstruit. Il n'y a
pas de retour automatique : si une étape échoue en route, ou le test de fumée, celles déjà faites restent sur la
nouvelle version (la base migrée, des apps ou des jobs) jusqu'à ce redéploiement.
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

## L'alerte sur les jetons du modèle (#501)

`budget-kb` compte la ressource du modèle depuis qu'elle porte `project=k-b` (geste de Sabine du 2026-11-18, #632) ;
un budget s'évalue une fois par 24 h. La règle `alert-kb-model-tokens` voit les jetons eux-mêmes, toutes les 15
minutes : elle écrit à `ag-kb-operator` quand la ressource dépasse 400 000 jetons sur 24 h glissantes.

| Réglage | Valeur |
|---|---|
| Métrique | `TotalTokens` de `Microsoft.CognitiveServices/accounts`, en entrée et en sortie, agrégation `Total` |
| Portée | toute la ressource `$MODEL_ACCOUNT`, sans filtre de déploiement : une clé de la ressource ouvre tous ses déploiements |
| Seuil | 400 000 jetons : 4 fois les 80 954 du jeudi 2026-11-19, jour de collecte et de veille, arrondi au 100 000 au-dessus (seuil de Sabine du 2026-11-20) |
| Fenêtre, fréquence | `P1D`, `PT15M` |
| Destinataire | `ag-kb-operator`, un e-mail : `budgetContactEmail`, l'adresse du budget |

L'alerte prévient ; la borne qui refuse les appels est le quota du déploiement : capacité 250, soit 250 000 jetons par
minute (lue le 2026-11-20).

### La poser

La passe de l'étape 2, avec `modelAccountName`. Aperçu attendu :
- **à créer** : `ag-kb-operator` et `alert-kb-model-tokens` ;
- **à modifier** : le bruit de l'étape 2.

L'aperçu montre l'adresse du groupe : elle est caviardée dans toute sortie recopiée et dans toute capture.

Constaté le 2026-11-20 : 2 ressources à créer, ces deux-là ; 31 à modifier, du bruit (les `reference(…)` non résolus
des rôles, les valeurs par défaut qu'Azure renvoie, le diagnostic de `cae-kb` et `budget-kb`) ; 1 non analysable, le
rôle SMB de `cae-kb` sur `stkbjobfiles…`, dont l'identifiant se calcule au déploiement ; aucune suppression. La
création a rendu `Succeeded`.

Azure a accepté le couple `P1D` et `PT15M`, que Microsoft Learn ne décrit pas. Si une création échoue sur
`alert-kb-model-tokens` avec une erreur qui nomme `evaluationFrequency` ou `windowSize`, la ligne
`evaluationFrequency: 'PT15M'` de `infra/modules/model-token-alert.bicep` devient `evaluationFrequency: 'PT1H'`, puis
la même passe se relance.

À la création du groupe, Azure écrit à cette adresse un code à usage unique, à saisir dans les 30 minutes qui suivent
l'enregistrement du groupe ; s'il a expiré, le portail le renvoie (« Resend »).

### La vérifier

```sh
az monitor metrics alert show -n alert-kb-model-tokens -g "$RG" \
  --query "{enabled:enabled,window:windowSize,frequency:evaluationFrequency,criteria:criteria.allOf,actions:actions[].actionGroupId}"
az monitor action-group show -n ag-kb-operator -g "$RG" \
  --query "{enabled:enabled,receivers:emailReceivers[].name,statuses:emailReceivers[].status}"
az resource show --ids "$MODEL_ID" --query tags.project -o tsv
```

Attendu : la règle active, `P1D` et `PT15M`, `TotalTokens` au-dessus de 400 000, l'identifiant de `ag-kb-operator` ;
le groupe actif, un destinataire, `operator`, et son statut (`statuses`), relevé après la saisie du code ; `k-b`.
Aucune de ces lectures n'affiche l'adresse.

Puis un e-mail d'essai, que la commande envoie à l'adresse donnée en ligne de commande (le `show` prouve le groupe,
l'essai prouve l'adresse) :

```sh
kb_check "$RG" "$EMAIL" && { az monitor action-group test-notifications create --action-group ag-kb-operator -g "$RG" \
  -a email operator "$EMAIL" usecommonalertschema --alert-type metricstaticthreshold \
  --query "{state:state,actions:actionDetails}"; } 2>&1 \
  | sed -E -e 's#/subscriptions/[0-9A-Fa-f-]{36}#/subscriptions/<abonnement>#g' -e 's/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+/<adresse>/g'
```

Le `sed` masque toute adresse et l'ID d'abonnement de la sortie, rendue entière.

La commande attend la fin de l'essai, qui vient plusieurs minutes après l'e-mail : l'e-mail reçu fait la preuve.

Constaté le 2026-11-20, après la passe : la règle active, `P1D`, `PT15M`, `TotalTokens` au-dessus de 400 000,
reliée à `ag-kb-operator` ; le groupe actif, un destinataire, `operator`, vérifié par le code à usage unique, à
l'état `Enabled` ; `k-b`. L'e-mail d'essai est arrivé, déclenché à 23:23 UTC ; la commande attendait encore la fin
de l'essai plus de 3 minutes après lui.

### Si elle sonne

1. Lire les jetons par jour et par déploiement, pour savoir lequel a consommé :

   ```sh
   az monitor metrics list --resource "$MODEL_ID" --metrics TotalTokens --aggregation Total --interval P1D \
     --dimension ModelDeploymentName --offset 3d
   ```

2. Si la consommation ne vient pas de K-B : régénérer la clé de la ressource dans le portail (jamais par une commande
   qui l'affiche), puis refaire le secret `kb-llm-api-key` (« Pour refaire un seul secret »).

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

1. Les étapes 0 et 1 d'« Appliquer » (`OPERATOR_UPN`, les fournisseurs).
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
DAILY_ROUTINE_ID=$(az identity show -g "$RG" -n id-kb-daily-routine --query principalId -o tsv)
admin_psql postgres -v daily_routine_principal_id="$DAILY_ROUTINE_ID" \
  -f infra/postgresql/create-daily-routine-principal.sql
admin_psql kb -v ON_ERROR_STOP=1 -f infra/postgresql/grant-roles.sql
```

`grant-roles.sql` se relance sans rien changer. `create-principals.sql` ne se relance pas : la base `kb` existe
déjà et `CREATE DATABASE` échoue. Le rôle de la routine a donc son propre fichier, venu avec #330 (« La routine
quotidienne ») : sur un serveur neuf, les trois fichiers passent dans cet ordre.

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

## Le stockage (#420)

Deux comptes, sans clé partagée, joints par les seules identités. Le Mac échange par des conteneurs Blob au sens
verrouillé : les clips et Zotero montent, les fiches descendent. Les jobs gardent leur état dans un partage Files
que le Mac ne touche jamais (décisions 3 à 8 du 06/11, journal ADR).

| Compte | Conteneur ou partage | Qui y accède |
|---|---|---|
| `stkbexchange…` (Blob) | `clippings` | `id-kb-daily-routine` lit ; l'opératrice écrit (`make upload-library`, #424) |
| | `zotero` | `id-kb-daily-routine` lit ; l'opératrice écrit |
| | `watch` | `id-kb-daily-routine` et `id-kb-digest-watch` écrivent ; l'opératrice lit (`make download-watch-sheets`) ; `id-kb-data-api` lit, pour le site (#571) |
| | `smoke-test` | `id-kb-smoke-test` lit |
| `stkbjobfiles…` (Files) | `job-data` | l'identité système de `cae-kb` (Storage File Data SMB MI Admin, sur le compte) |

- **Le sens est tenu par les rôles**, un par identité et par conteneur, aucun sur le compte. L'API de données lit
  `watch` seul (#571) ; l'API IA et `id-kb-migrate-database` n'en ont aucun. Écrire à contresens répond 403 (`AuthorizationPermissionMismatch`).
- **`job-data` est tenu par le Bicep, pas par une identité** : le rôle appartient à l'environnement. Toute app ou
  tout job de `cae-kb` qui déclare un volume `job-data` monte le partage. Seuls `caj-kb-daily-routine` (#330) et `caj-kb-digest-watch` (#423) le déclarent : c'est une convention, pas un contrôle. `id-kb-deploy`, qui met à jour les apps et les jobs de `deployment.json`, peut passer outre (registre des traitements, ligne « Déploiement continu »).
- **Protections de `stkbexchange`** : versions ; suppression réversible des blobs et des conteneurs, 30 jours ;
  les copies Zotero (`zotero/…`) effacées après 14 jours avec leurs versions, par la règle `erase-zotero-copies` (un
  passage par jour, sans heure garantie : la copie, puis sa version au passage suivant ; ce qu'elle efface reste
  30 jours en suppression réversible : environ 46 jours en tout). Rien n'efface `clippings`.
  Personne n'a Storage Blob Data Owner : une version précédente ne s'efface pas.
- **Protections de `stkbjobfiles`** : suppression réversible du partage, 30 jours. Elle ne protège pas un fichier :
  les instantanés le font (ci-dessous).
- **Un verrou `CanNotDelete` sur chaque compte**, contre l'erreur de manipulation. Il n'arrête pas un Owner, qui
  peut le lever ; son geste reste au journal d'activité.

### Appliquer #420 sur le squelette en ligne

1. Les étapes 0 et 1 d'« Appliquer ».
2. `TAG` = la version en ligne (fin de l'étape 5) : les API tiennent leur image par digest, la passe crée donc une
   révision par API, à la même image.
3. La seconde passe (étape 5). Aperçu attendu :
   - **à créer** : `stkbjobfiles…`, son service de fichiers, le partage `job-data`, le rôle SMB MI Admin, le stockage
     `job-data` de `cae-kb`, les identités `id-kb-daily-routine` et `id-kb-digest-watch`, les conteneurs
     `clippings`, `zotero` et `watch`, leurs 7 rôles, la règle de cycle de vie, les 2 verrous ;
   - **à modifier** : `cae-kb` (l'identité système seule), le service Blob de `stkbexchange…` (versions,
     suppressions réversibles), l'image des deux API, et le bruit de l'étape 5.
   - Tout autre changement sur `cae-kb` arrête l'application : l'environnement porte les deux API.
4. La création. Si le stockage `job-data` de `cae-kb` échoue, c'est que le rôle n'est pas encore actif (jusqu'à
   10 minutes) : relancer la même commande 10 minutes plus tard.
5. Attendre 10 minutes après la création des rôles, puis vérifier les critères.

La passe de #420 a aussi porté la sonde de l'essai (commit `f10e5e3`, retirée par `d2f5b6e` : critère 5 ci-dessous) :
`caj-kb-smoke-test` portait `id-kb-daily-routine`, montait `job-data` et lançait la sonde au lieu de `kb smoke-test`.
Pour la rejouer, même règle : **aucune exécution du workflow Deploy** (ni tag, ni re-run, ni `workflow_dispatch`) tant que la sonde est en ligne
dans Azure, jusqu'à ce qu'une passe sans la sonde soit appliquée : le revert dans git ne suffit pas. Le workflow
lancerait la sonde, et `id-kb-deploy` pourrait agir comme `id-kb-daily-routine`.

### Vérifier les critères de #420

```sh
EXCHANGE=$(az storage account list -g "$RG" --query "[?starts_with(name,'stkbexchange')].name" -o tsv)
JOBFILES=$(az storage account list -g "$RG" --query "[?starts_with(name,'stkbjobfiles')].name" -o tsv)
```

1. Depuis le Mac, par le compte Entra de l'opératrice, un objet caché sans `.md`, au contenu neutre :

   ```sh
   PROBE=$(mktemp) && printf 'probe 420' > "$PROBE"
   az storage blob upload --auth-mode login --account-name "$EXCHANGE" -c watch -n .probe-420 -f "$PROBE"
   az storage blob upload --auth-mode login --account-name "$EXCHANGE" -c clippings -n .probe-420 -f "$PROBE"
   az storage blob delete --auth-mode login --account-name "$EXCHANGE" -c clippings -n .probe-420
   rm "$PROBE"
   ```

   Attendu : `watch` refuse (`AuthorizationPermissionMismatch`), `clippings` accepte. L'objet supprimé reste en
   version précédente, que personne ne peut effacer : son nom est caché et sans `.md`, le miroir des clips l'écarte.
2. La clé partagée est coupée :
   `az storage account show -n "$EXCHANGE" -g "$RG" --query allowSharedKeyAccess` rend `false`, de même pour
   `"$JOBFILES"` : le montage par identité se passe de la clé (essai du 10/11).
3. La sonde, sous `id-kb-daily-routine`, le partage monté : elle a tourné le 10/11 (`f10e5e3`), lue comme à
   l'étape 6 d'« Appliquer », avec `JobName == 'caj-kb-smoke-test'`. Résultat, puis `Succeeded` :
   - `probe 420: process uid 10001 gid 10001` ;
   - `probe 420: mount uid=10001 gid=10001 mode=0o700` et `probe 420: file uid=10001 gid=10001 mode=0o600` ;
   - `probe 420: clippings 403 AuthorizationPermissionMismatch` ;
   - `probe 420: watch written, then deleted` ;
   - `probe 420: passed`.

   Si la réplique ne démarre pas, le montage a échoué : la cause est dans `ContainerAppSystemLogs`.
4. Les protections :

   ```sh
   az lock list -g "$RG" --query "[].{name:name,level:level}" -o table
   az storage account blob-service-properties show -n "$EXCHANGE" -g "$RG" \
     --query "{versions:isVersioningEnabled,blobs:deleteRetentionPolicy.days,containers:containerDeleteRetentionPolicy.days}"
   az storage account management-policy show --account-name "$EXCHANGE" -g "$RG" \
     --query "policy.rules[].{name:name,prefix:definition.filters.prefixMatch,blob:definition.actions.baseBlob.delete.daysAfterCreationGreaterThan,version:definition.actions.version.delete.daysAfterCreationGreaterThan}"
   az storage account file-service-properties show -n "$JOBFILES" -g "$RG" --query shareDeleteRetentionPolicy
   ```

   Attendu : deux verrous `CanNotDelete` ; `true`, `30`, `30` ; la règle `erase-zotero-copies` sur `zotero/`, `14`
   et `14` ; le partage gardé 30 jours.
5. Retirer la sonde : revert de `f10e5e3` (`d2f5b6e`), puis la seconde passe. Aperçu attendu : `caj-kb-smoke-test` seul à
   modifier (son identité, son volume, sa commande). Puis
   `az containerapp job show -n caj-kb-smoke-test -g "$RG" --query "{identities:identity.userAssignedIdentities,volumes:properties.template.volumes}"`
   ne montre plus que `id-kb-smoke-test`, sans volume, et le job repasse : `3 of 3 checks passed` au relevé de #420,
   `9 of 9 checks passed` depuis #499.

### Les instantanés de `job-data`

Un instantané avant chaque mise en production, dès le tag qui suit l'amorçage (#330). Aucun avant l'amorçage : le
partage part vide (décision de Sabine du 10/11). Ils se prennent et se suppriment à la
main, par l'opératrice : ce sont des gestes du plan de contrôle, que son rôle Owner couvre. `id-kb-deploy` n'y a
aucun droit. Chacun est **gardé 7 jours au plus** (décision de Sabine du 10/11) et porte sa date de suppression.
Un brut vit donc au plus 6 mois et 7 jours, écrit au registre des traitements.

```sh
az storage share-rm snapshot --storage-account "$JOBFILES" -g "$RG" -n job-data --metadata delete_after=<AAAA-MM-JJ>
az storage share-rm list --storage-account "$JOBFILES" -g "$RG" --include-snapshot \
  --query "[].{snapshot:snapshotTime,deleteAfter:metadata.delete_after}" -o table
```

À la date venue, le verrou se lève, l'instantané se supprime **par sa date** (`--snapshot`), et le verrou revient
(ci-dessous). Sans `--snapshot`, `az storage share-rm delete` vise le partage lui-même. Un effacement à la demande
(étape 5 de la procédure de tri du registre) touche aussi les instantanés qui gardent la donnée.

```sh
az storage share-rm delete --storage-account "$JOBFILES" -g "$RG" -n job-data --snapshot "<snapshotTime>" --yes
```

### Le verrou : le lever, agir, le reposer

`CanNotDelete` bloque toute suppression par le plan de contrôle sur le compte et ce qu'il contient : le compte, un
conteneur, le partage, un instantané, et un rôle posé sur le compte ou un conteneur (le rôle temporaire de
l'amorçage, #330 ; un Storage Blob Data Owner posé pour effacer une version). Il ne bloque pas les données : une
identité qui a le droit écrit et supprime des blobs et des fichiers. Il se lève avant #428, la fermeture.

```sh
az lock delete -n "lock-$JOBFILES" -g "$RG" --resource "$JOBFILES" --resource-type Microsoft.Storage/storageAccounts
# … le geste …
az lock create -n "lock-$JOBFILES" -g "$RG" --resource "$JOBFILES" --resource-type Microsoft.Storage/storageAccounts \
  --lock-type CanNotDelete --notes "K-B storage of the jobs (#420): lift it only to delete a snapshot, a role or the account (#428)."
```

Même geste pour `"$EXCHANGE"`. Une passe du Bicep repose aussi un verrou oublié.

Sources (Microsoft Learn, lues le 2026-11-10) :
[montages de stockage de Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/storage-mounts),
[Azure Files par identité managée](https://learn.microsoft.com/en-us/azure/storage/files/files-managed-identities),
[stockage d'un environnement, 2026-03-02-preview](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/2026-03-02-preview/managedenvironments/storages),
[rôles intégrés du stockage](https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/storage),
[facturation d'Azure Files](https://learn.microsoft.com/en-us/azure/storage/files/understanding-billing),
[`az storage share-rm`](https://learn.microsoft.com/en-us/cli/azure/storage/share-rm).

## La routine quotidienne (#330)

`caj-kb-daily-routine` lance `kb daily-routine` (#413) chaque jour à 08:00 UTC, soit 9 h à Paris en hiver et 10 h en
été (décision de Sabine du 10/11). L'ordre des étapes : le miroir des clips, `kb collect`, `kb import`,
`kb purge`, `kb write-tops`, puis la publication de `veille` dans `watch`. L'image `v0.1.1`, posée avant `kb purge`
(#540), a 5 étapes, et sa purge tourne dans `kb import`, jusqu'au tag suivant. Son dossier de données est le partage
`job-data`, monté sur `/var/lib/knowledge_base` : le brut, l'état de la collecte et le coffre y restent d'une exécution
à l'autre. Il écrit la base sous `id-kb-daily-routine`, membre de `kb_writer`.

| Réglage | Valeur |
|---|---|
| Déclenchement | cron `0 8 * * *`, lu en UTC ; parallélisme 1 |
| Délai, reprise | 3 600 s, 1 reprise. Le délai borne aussi la reprise : une exécution du cron finit avant 09:00 UTC |
| Ressources | 0,5 vCPU, 1 Gio, relevés à la première exécution ; à changer par `az containerapp job update --cpu --memory`, jamais par `job start` |
| Volumes | `job-data` sur `/var/lib/knowledge_base` (uid 10001, `0700` et `0600`, les options essayées par la sonde de #420) ; `secrets` sur `/mnt/secrets`, la seule clé BigQuery |
| Secrets | `KB_GITHUB_TOKEN` ← `kb-github-token` ; `GOOGLE_APPLICATION_CREDENTIALS=/mnt/secrets/bigquery-key.json` ← `kb-bigquery-key` |

**Le job part de zéro** (décision de Sabine du 10/11) : rien du Mac n'est copié, ni brut, ni état, ni fiche. Le
partage est vide, et la base n'a que ses sept sources. La première exécution collecte donc comme une première
collecte : arXiv depuis le 01/05, les 7 derniers jours de TLDR, tout le catalogue de CISA KEV, les 8 derniers jours de
GH Archive (6 fenêtres de 3 jours), aucun clip ni Zotero. Sur le Mac, le 21/10, une première collecte a pris 84 s, et
l'import moins de 10 s ([collecte réelle du 21/10](../docs/2026-10-21-collecte-reelle.md)).

Dans l'ordre :
1. Le critère rouge : `az containerapp job show -n caj-kb-daily-routine -g "$RG"` répond `ResourceNotFound`.
2. Les deux secrets.
3. Le principal et ses droits.
4. La seconde passe, avec un tag posé après la fusion de #295.
5. Un rôle temporaire sur le partage, pour les deux dossiers du coffre et le temporaire de l'essai de #295.
6. L'exécution d'essai, puis la première vraie exécution, le même jour UTC ; le rôle se retire ensuite.
7. Le lendemain : l'exécution du cron.

Une seule passe ou écriture dans Azure à la fois : chacune se signale avant d'être lancée.

### Les deux secrets de la routine

Chacun est à part de ceux du Mac et de l'API IA : il se révoque sans rien arrêter d'autre.
- **`kb-github-token`** : un nouveau jeton *fine-grained* ([docs/jeton-github.md](../docs/jeton-github.md),
  « Créer un jeton »), nommé `K-B routine en ligne (lecture seule)`, sur les dépôts publics, sans aucune permission,
  pour 90 jours.
- **`kb-bigquery-key`** : une nouvelle clé JSON du compte `k-b-collecte` ([docs/bigquery.md](../docs/bigquery.md),
  « La clé »). Elle se pose depuis le fichier téléchargé, qui est supprimé aussitôt après.

Dans son propre terminal, comme à l'étape 4 d'« Appliquer » :

```sh
name=kb-github-token
printf '%s : ' "$name"; read -rs VALUE; echo
az keyvault secret set --vault-name "$KV" --name "$name" --file <(printf '%s' "$VALUE") -o none
unset VALUE
KEY_FILE=<chemin du fichier .json téléchargé>
kb_check "$KV" "$KEY_FILE" && az keyvault secret set --vault-name "$KV" --name kb-bigquery-key --file "$KEY_FILE" -o none \
  && rm "$KEY_FILE"
az keyvault secret list --vault-name "$KV" --query "[].name" -o tsv    # les noms, jamais les valeurs
```

Les deux secrets doivent exister avant la seconde passe : elle donne à `id-kb-daily-routine` un rôle sur chacun.

Pour en refaire un, la nouvelle version remplace l'ancienne (étape 4, « Pour refaire un seul secret »). Un job n'a pas
de révision à redémarrer. Qu'une exécution lancée plus de 30 minutes après lise la nouvelle version n'est pas encore
vérifié : ce sera fait à la première rotation.

### Le principal de la routine et ses droits

`create-principals.sql` ne se relance pas (la base `kb` existe déjà) : le rôle de la routine a son propre fichier.
L'administration ouverte (« Ouvrir une administration ») :

```sh
DAILY_ROUTINE_ID=$(az identity show -g "$RG" -n id-kb-daily-routine --query principalId -o tsv)
kb_check "$DAILY_ROUTINE_ID" && admin_psql postgres -v daily_routine_principal_id="$DAILY_ROUTINE_ID" \
  -f infra/postgresql/create-daily-routine-principal.sql
admin_psql kb -v ON_ERROR_STOP=1 -f infra/postgresql/grant-roles.sql
admin_psql kb -At -c "SELECT pg_has_role('id-kb-daily-routine', 'kb_writer', 'MEMBER'), has_database_privilege('id-kb-daily-routine', 'kb', 'CONNECT'), has_table_privilege('id-kb-daily-routine', 'public.source', 'INSERT')"
```

Attendu : `t|t|t`. Puis « Fermer l'administration ». La première exécution ne part qu'après ce `t|t|t`.

### La seconde passe, avec le tag

`TAG` est un tag posé après la fusion de #295. La passe se lance depuis la branche de #330, avec ce `TAG`, comme à
l'étape 5 d'« Appliquer », après 09:00 UTC : l'essai et la première exécution suivent le même jour UTC. Aperçu
attendu :
- **à créer** : `caj-kb-daily-routine` ; l'AcrPull d'`id-kb-daily-routine` sur le registre ; ses deux rôles Key Vault
  Secrets User (`kb-github-token`, `kb-bigquery-key`) ; le Container Apps Jobs Contributor d'`id-kb-deploy` sur le
  job ;
- **à modifier** : l'image des deux API et des deux jobs (`k-b@sha256:…` devient `k-b:<TAG>`, la même image), et le
  bruit de l'étape 5.
- Tout autre changement arrête la passe, en particulier sur `cae-kb`, le stockage ou les verrous.

Si le job échoue sur « unable to fetch secret », c'est que ses rôles sur les secrets ne sont pas encore actifs :
relancer la même commande 10 minutes plus tard.

Dès cette passe, chaque tag change aussi l'image de la routine (`deployment.json`). `id-kb-deploy` peut alors agir
sous l'identité de la routine, et lire ses deux secrets (risque accepté par Sabine le 10/11, registre des traitements,
ligne « Déploiement continu »).

### Les deux dossiers du coffre et le temporaire de l'essai

La routine refuse de démarrer sans `vault/` : `KB_VAULT_DIR` doit être un dossier existant, sinon elle sort en 2 et
rien ne tourne. Sans `vault/Clippings/`, la collecte des clips échoue chaque jour (`clippings_folder_missing`). Ni la
routine ni le Bicep ne les créent, pour qu'un `KB_VAULT_DIR` mal écrit ou un coffre disparu se voie.

Le même geste prépare l'essai de #295 sur `job-data` (décision de Sabine du 10/11) : un temporaire `.<jour>.md.tmp`
posé dans le dossier de la fiche du top `most_forked`, par un autre client que le conteneur (FileREST, depuis le
Mac). Il est caché : la publication l'écarte, rien de faux ne part dans `watch`.

C'est une écriture de données, que l'opératrice fait une fois, par un rôle temporaire posé sur le seul partage. La
portée s'écrit avec `fileshares`, et non `shares` : sinon le rôle ne vaut pas.

```sh
JOBFILES=$(az storage account list -g "$RG" --query "[?starts_with(name,'stkbjobfiles')].name" -o tsv)
SHARE_SCOPE="$(az storage account show -n "$JOBFILES" -g "$RG" --query id -o tsv)/fileServices/default/fileshares/job-data"
kb_check "$OPERATOR" "$JOBFILES" "$SHARE_SCOPE" && az role assignment create --assignee-object-id "$OPERATOR" \
  --assignee-principal-type User --role "Storage File Data Privileged Contributor" --scope "$SHARE_SCOPE" -o none
az role assignment list --assignee "$OPERATOR" --scope "$SHARE_SCOPE" --query "[].{role:roleDefinitionName,scope:scope}" -o table
```

Attendu : `Storage File Data Privileged Contributor`, sur une portée qui finit par `/fileshares/job-data`. La sortie de
`az role assignment create` ne porte pas ce nom : son `--query roleDefinitionName` ne rend rien (vu le 2026-11-10).

Dix minutes plus tard, le temps que le rôle soit actif (le 2026-11-10, il l'était en 2 minutes environ). `DAY` est le
jour UTC de l'essai, celui que portera la fiche :

```sh
DAY=$(date -u +%F)
for dir in vault vault/Clippings vault/veille vault/veille/tops vault/veille/tops/most_forked; do
  az storage directory create --account-name "$JOBFILES" --share-name job-data --name "$dir" \
    --auth-mode login --backup-intent
done
EMPTY=$(mktemp)
az storage file upload --account-name "$JOBFILES" --share-name job-data --source "$EMPTY" \
  --path "vault/veille/tops/most_forked/.$DAY.md.tmp" --auth-mode login --backup-intent
rm "$EMPTY"
az storage file list --account-name "$JOBFILES" --share-name job-data --path vault \
  --auth-mode login --backup-intent --query "[].name" -o tsv
az storage file list --account-name "$JOBFILES" --share-name job-data --path vault/veille/tops/most_forked \
  --auth-mode login --backup-intent --query "[].name" -o tsv
```

Attendu : `{"created": true}` pour chaque dossier (vu le 2026-11-10), aucune erreur pour le temporaire ; `Clippings`
et `veille` ; puis `.<DAY>.md.tmp` seul. `--backup-intent` est obligatoire pour
toute commande `az storage file` ou `az storage directory` par compte Entra : sans lui, la commande est refusée.

### L'essai de #295, puis la première exécution

Le rôle temporaire reste posé jusqu'à la fin de cette section. Les deux exécutions démarrent le même jour UTC, `DAY`,
hors de la fenêtre du cron (règle des heures, ci-dessous).

**L'exécution d'essai.** C'est aussi la première collecte en ligne : sa durée est celle d'une première collecte.

```sh
EXEC=$(az containerapp job start -n caj-kb-daily-routine -g "$RG" --query name -o tsv)
az containerapp job execution show -n caj-kb-daily-routine -g "$RG" --job-execution-name "$EXEC" \
  --query "{status:properties.status,start:properties.startTime,end:properties.endTime}"
```

Attendu, lu au journal (« Lire une exécution », ci-dessous) :
- `top sheets failed: most_forked: temporary_file_found: veille/tops/most_forked/.<DAY>.md.tmp is there` : la fiche
  de `most_forked` n'est pas écrite, et son relevé reste dans le brut ;
- `most_starred sheet of <DAY>: sheet_written` : l'autre top est écrit quand même ;
- `kb write-tops` sort en 4 (un top échoue, un autre est fait) ; la publication tourne quand même, et n'envoie que la
  fiche de `most_starred` ;
- `kb daily-routine finished in …: exit code 4`.

Le code 4 fait échouer la réplique : le job la reprend une fois, qui finit de même (sa fiche de `most_starred` est
alors `sheet_exists, not rewritten`), puis l'exécution est `Failed`. Constaté le 2026-11-10, première fois qu'un code
autre que 0 sortait d'un job de K-B en ligne : la reprise a écrit deux lignes `sheet_exists` pour `most_starred`, une
par relevé du jour resté dans le brut (le dernier relevé lu reste jusqu'au suivant), et l'exécution `Failed` n'a pas
d'heure de fin (`"end": null`). Le temporaire, lui, reste en place : `kb` ne
retire jamais un temporaire qu'il n'a pas créé. Une source qui échoue fait aussi sortir `kb collect` en 4 (arXiv a
déjà expiré au bout de 30 s pendant une première collecte, le 21/10) : l'essai se lit sur les lignes de
`kb write-tops`.

**Entre les deux.** Le temporaire se retire, et la fiche de `most_starred` se relève :

```sh
az storage file delete --account-name "$JOBFILES" --share-name job-data \
  --path "vault/veille/tops/most_forked/.$DAY.md.tmp" --auth-mode login --backup-intent
az storage file list --account-name "$JOBFILES" --share-name job-data --path vault/veille/tops/most_forked \
  --auth-mode login --backup-intent --query "[].name" -o tsv
az storage file show --account-name "$JOBFILES" --share-name job-data \
  --path "vault/veille/tops/most_starred/$DAY.md" --auth-mode login --backup-intent \
  --query "properties.{modified:lastModified,etag:etag}"
```

`az storage file delete` rend `{"deleted": null}`, même quand le fichier est retiré (vu le 2026-11-10) : le retrait se
lit à la liste qui suit, qui ne rend plus rien.

**La première vraie exécution,** lancée comme l'essai. Attendu : `most_starred sheet of <DAY>: sheet_exists, not
rewritten` (la seconde exécution laisse intacte la fiche de la première), `most_forked sheet of <DAY>: sheet_written`,
`exit code 0`, puis `Succeeded`. La même commande `az storage file show` rend la même date et le même etag.

Puis le rôle se retire, verrou levé (« Le verrou : le lever, agir, le reposer ») :

```sh
az lock delete -n "lock-$JOBFILES" -g "$RG" --resource "$JOBFILES" --resource-type Microsoft.Storage/storageAccounts
az role assignment delete --assignee "$OPERATOR" --role "Storage File Data Privileged Contributor" --scope "$SHARE_SCOPE"
az lock create -n "lock-$JOBFILES" -g "$RG" --resource "$JOBFILES" --resource-type Microsoft.Storage/storageAccounts \
  --lock-type CanNotDelete --notes "K-B storage of the jobs (#420): lift it only to delete a snapshot, a role or the account (#428)."
az role assignment list --assignee "$OPERATOR" --scope "$SHARE_SCOPE" --query "[].roleDefinitionName" -o tsv
az lock list -g "$RG" --query "[].{name:name,level:level}" -o table
```

Attendu : aucune ligne pour le rôle, puis les deux verrous `CanNotDelete`.

Ce que l'essai ne couvre pas, écrit au registre avec sa parade : deux conteneurs qui écrivent en même temps, et la
fraîcheur de ce qu'un client voit d'une écriture faite par un autre client.

### Lire une exécution

Les exécutions, dont celle du cron, le lendemain :

```sh
az containerapp job execution list -n caj-kb-daily-routine -g "$RG" \
  --query "[].{name:name,status:properties.status,start:properties.startTime,end:properties.endTime}" -o table
```

Une exécution `Failed` n'a pas d'heure de fin (vu le 2026-11-10) : sa durée se lit au journal.

Le journal se lit dans `log-kb`, quelques minutes après la fin (`WS` : étape 6 d'« Appliquer ») :

```sh
az monitor log-analytics query -w "$WS" -o tsv \
  --analytics-query "ContainerAppConsoleLogs | where TimeGenerated > ago(3h) and JobName == 'caj-kb-daily-routine' | order by TimeGenerated asc" \
  --query "[].[TimeGenerated, Log]"
```

On y relève :
- `kb daily-routine started: 6 steps`, puis, pour chaque étape, `… step <n> of 6, <étape>, exited with <code>` ;
  avec `v0.1.1`, `5 steps` et `step <n> of 5`, sans `kb purge` ;
- `kb daily-routine finished in …: exit code <code>`, puis le tableau des étapes ;
- les octets lus par BigQuery : `gh_archive: … bytes processed, … rows` ;
- la durée, face au délai de 3 600 s.

Puis les fiches publiées :

```sh
EXCHANGE=$(az storage account list -g "$RG" --query "[?starts_with(name,'stkbexchange')].name" -o tsv)
az storage blob list --auth-mode login --account-name "$EXCHANGE" -c watch --prefix tops/ --query "[].name" -o tsv
```

Attendu : `tops/<top>/<jour>.md`. Le démarrage, le tirage de l'image et le montage sont dans `ContainerAppSystemLogs`.
La clé BigQuery est un fichier du volume `secrets`, que l'uid 10001 lit (le 2026-11-10, `gh_archive` a lu 6 fenêtres,
60 Mo). S'il ne se lit plus, le journal porte `collection failed for source 'gh_archive': PermissionError …`, suivi de sa trace, puis
`gh_archive: failed (PermissionError)` (`src/k_b/etl/extract.py`, `src/k_b/commands/collect_command.py`) ; la
collecte sort en 4, les autres sources gardées. S'il manque, l'erreur est `DefaultCredentialsError` (google-auth).

### La règle des heures

Rien ne tient deux exécutions de la routine à l'écart l'une de l'autre avant #426, un verrou dans la base. #426 ne
couvrira pas `caj-kb-digest-watch` (#423), qui ne touche pas la base : pour ce job, seule cette règle tient. Elle
porte sur l'heure de départ d'une exécution à la main, son délai compris (3 600 s pour la routine, 1 800 s pour les
comptes rendus), avec 5 minutes de marge pour le démarrage et le tirage de l'image :
- **la routine à la main ne démarre jamais entre 06:55 et 09:00 UTC**, ni, le lundi et le jeudi, entre 06:55 et
  10:35 UTC : elle finirait pendant celle du cron ou pendant les comptes rendus ;
- **`caj-kb-digest-watch` à la main ne démarre jamais le lundi ni le jeudi avant la fin de celle du cron**
  (10:35 UTC) : ses fiches du jour feraient refuser le cron (`kb digest` sort en 2), qui finirait `Failed`. Après,
  ces deux jours, seulement pour relancer une exécution du cron coupée avant d'écrire une fiche. Les autres jours,
  jamais entre 07:25 et 09:05 UTC ;
- **aucun tag n'est posé pendant une exécution d'un cron** (08:00 à 09:05 UTC chaque jour, 10:00 à 10:35 UTC le lundi
  et le jeudi) : la livraison change les deux API au milieu d'une demande de 240 s ;
- un échec de la routine se diagnostique avant 06:55 UTC le lendemain.

Le risque visé : `kb import` qui écrit la base pendant que l'API de données la lit, page par page, pour un compte rendu
([specs-api.md](../docs/specs-api.md)). Le partage n'est pas en cause : la publication compte une fiche déjà dans
`watch` (409, 412) comme « déjà là », et une fiche du coffre ne s'écrit qu'une fois (#295).

### Un temporaire resté en ligne (#295)

Un fichier écrit une fois passe par un temporaire caché à son nom, `.<nom>.tmp`, à côté de la fiche (`vault/veille/…`)
ou du brut (`raw/…`). Si le job est tué pendant l'écriture (délai dépassé), le temporaire reste. Ce fichier ne s'écrit
plus ensuite : la ligne `temporary_file_found: .<nom>.tmp is there` le nomme, et l'étape échoue chaque jour.

Le retrait se fait à la main, quand aucune exécution n'est `Running` (`az containerapp job execution list`). Il prend le
même rôle temporaire que les deux dossiers, puis :

```sh
az storage file list --account-name "$JOBFILES" --share-name job-data --path "<dossier>" \
  --auth-mode login --backup-intent --query "[?starts_with(name, '.')].name" -o tsv
az storage file delete --account-name "$JOBFILES" --share-name job-data --path "<dossier>/.<nom>.tmp" \
  --auth-mode login --backup-intent
```

La suppression rend `{"deleted": null}` même quand elle a eu lieu : la première commande, relancée, ne liste plus le
temporaire.

Enfin, le rôle se retire, verrou levé, comme pour les deux dossiers. Le retrait par `kb` lui-même, au-delà d'un seuil,
attend son issue.

Sources (Microsoft Learn, lues le 2026-11-10) :
[jobs de Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/jobs) (cron en UTC, délai prioritaire
sur les reprises, rôles qui lisent les secrets d'un job),
[`Microsoft.App/jobs` 2026-01-01](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/2026-01-01/jobs)
(volume `Secret`, `secrets` limités à une liste),
[Azure Files par OAuth sur REST](https://learn.microsoft.com/en-us/azure/storage/files/authorize-oauth-rest) (rôle
Privileged Contributor, portée en `fileshares`, `--backup-intent`),
[`az storage directory`](https://learn.microsoft.com/en-us/cli/azure/storage/directory).

## Les comptes rendus en ligne (#423)

`caj-kb-digest-watch` lance `kb digest-watch` (#413) le lundi et le jeudi à 10:00 UTC, une fois la routine finie.
L'ordre des étapes : `GET /health` des deux API (qui réveille une API à 0 réplique), `kb digest`, de nouveau les deux
`/health`, `kb trend-report`, puis la publication de `veille` dans `watch`. Son dossier de données est le partage
`job-data`, comme pour la routine (décision de Sabine du 11/11). Il le faut pour deux raisons :
- le registre des comptes rendus des tendances (`trend_reports.json`) y reste d'un passage à l'autre ;
- `kb digest` et `kb trend-report` y cherchent le compte rendu du jour avant toute demande.

Il n'a aucun rôle sur la base : il la lit par les deux API.

| Réglage | Valeur |
|---|---|
| Déclenchement | le paramètre `digestWatchCronExpression` de `main.bicep`, `0 10 * * 1,4` par défaut, lu en UTC ; parallélisme 1 |
| Délai, reprise | 1 800 s, aucune reprise (ci-dessous) |
| Ressources | 0,25 vCPU, 0,5 Gio, comme la sonde, relevés à la première exécution ; à changer par `az containerapp job update --cpu --memory` |
| Volume | `job-data` sur `/var/lib/knowledge_base` (uid 10001, `0700` et `0600`) |
| Variables | `KB_DATA_DIR`, `KB_VAULT_DIR`, `KB_EXCHANGE_BLOB_URL`, `KB_DATA_API_URL` et `KB_AI_API_URL` (les noms internes, en HTTPS), `AZURE_CLIENT_ID` |
| Secrets | `KB_AI_API_KEY_KB_DIGEST` ← `kb-ai-api-key-kb-digest` ; `KB_AI_API_KEY_KB_TREND_REPORT` ← `kb-ai-api-key-kb-trend-report` |

**Aucun secret nouveau** : ce sont les deux clés que l'API IA vérifie déjà (étape 4 d'« Appliquer »). Une clé se
change pour les deux côtés à la fois ([README](../README.md), « Changer une clé »). Qu'une exécution du job lise la
nouvelle version n'est pas encore vérifié, comme pour la routine.

**Changer l'heure** : la passe ajoute `digestWatchCronExpression='<minute> <heure> * * <jours>'` à ses `-p`. Les
heures restent celles de « La règle des heures ».

**Aucune reprise.** Après une expiration côté `kb`, une reprise appellerait le modèle une seconde fois. Or `kb digest`
et `kb trend-report` ne refusent que si le compte rendu du jour existe, ce qu'une exécution coupée n'a pas forcément
écrit. Limite : Microsoft Learn conseille au moins une reprise, parce qu'une maintenance de la plateforme peut couper
une exécution. Pour réduire le risque :
- la routine republie `veille` chaque jour : une fiche écrite mais pas publiée part le lendemain ;
- une exécution coupée avant d'écrire une fiche se relance à la main le même jour, après celle du cron (« La règle
  des heures »).

Limite de cette parade : coupée après une fiche, la relance ne rattrape rien. `kb digest` refuse tous les sujets dès
qu'une fiche du jour existe (`src/k_b/commands/digest_command.py`), et les sujets manquants attendent le passage
suivant.

**La fenêtre** : depuis #565, chaque compte rendu par sujet lit les items datés du `until` de la fiche précédente du
sujet jusqu'à sa demande, par la date de la source : du lundi au jeudi, 3 jours ; du jeudi au lundi, 4, sans trou
entre deux comptes rendus (règle de Sabine du 26/10, [tendances.md](../docs/tendances.md), fin de « Hors v1 »). Le
premier compte rendu d'un sujet sans fiche lit 3 jours (`KB_DIGEST_WINDOW_DAYS`, le défaut ; décision de Sabine du
11/11, 3 jours et non 5) ([fiches-veille.md](../docs/fiches-veille.md), « Fenêtre »). Limite : une perte reste.
- **Le retard de collecte** : la base ne se remplit qu'à 08:00 UTC. Un item daté avant le `until` d'un compte rendu,
  mais collecté après lui, n'entre ni dans ce compte rendu ni dans le suivant, qui part de ce `until`. C'est le cas
  des éditions TLDR et des entrées KEV, datées de minuit : celle du lundi, collectée le mardi, tombe avant la fenêtre
  du jeudi (qui part du lundi 10:00) ; celle du jeudi, collectée le vendredi, avant celle du lundi.

Pour réduire le risque :
- La lecture par date d'arrivée dans K-B, prévue plus tard (décision de Sabine du 11/11). #565 a couvert le
  passage d'un compte rendu au suivant, le trou du jeudi 10:00 au vendredi 10:00 UTC.
- Les items absents d'un compte rendu ne sont pas perdus pour K-B : ils restent 3 ans dans la base
  ([registre](../docs/registre-traitements.md), fiche 1, « Durée de conservation ») et se lisent par l'API de données
  (`GET /items?since=…`, [specs-api.md](../docs/specs-api.md)).

Dans l'ordre :
1. Le critère rouge : `az containerapp job show -n caj-kb-digest-watch -g "$RG"` répond `ResourceNotFound`.
2. La seconde passe, depuis la branche de #423, avec le tag en ligne.
3. La première exécution, à la main, dans les heures permises.
4. Les comptes rendus, sur le Mac.
5. Le lundi ou le jeudi suivant : l'exécution du cron.

Une seule passe ou écriture dans Azure à la fois : chacune se signale avant d'être lancée.

### La seconde passe

`TAG` est la version en ligne (étape 5 d'« Appliquer », pour la retrouver). La passe se lance depuis la branche de
#423, rebasée sur `main` juste avant, pour ne défaire aucune infra fusionnée entre-temps. Aperçu attendu :
- **à créer** : `caj-kb-digest-watch` ; l'AcrPull d'`id-kb-digest-watch` sur le registre ; ses deux rôles Key Vault
  Secrets User (`kb-ai-api-key-kb-digest`, `kb-ai-api-key-kb-trend-report`) ; le Container Apps Jobs Contributor
  d'`id-kb-deploy` sur le job ;
- **à modifier** : l'image des deux API et des jobs (`k-b@sha256:…` devient `k-b:<TAG>`, la même image), et le bruit
  de l'étape 5 ;
- tout autre changement arrête la passe, en particulier sur `cae-kb`, le stockage, les verrous ou les variables des
  API.

Si le job échoue sur « unable to fetch secret », ses rôles sur les secrets ne sont pas encore actifs : relancer la
même commande 10 minutes plus tard.

**La fusion de la PR et tout tag attendent une passe `Succeeded`** : sans le job, le tag suivant échouerait à « Sets the
jobs to the image of the tag » (`.github/workflows/deploy.yml`), les apps déjà changées, et la sonde ne tournerait pas.

Dès cette passe, chaque tag change aussi l'image de ce job (`deployment.json`). `id-kb-deploy` peut alors agir sous
`id-kb-digest-watch` et lire ses deux clés. Ce n'est pas un accès nouveau : il atteint déjà `watch` et `job-data` par
la routine, et les deux clés par Container Apps Contributor sur `ca-kb-ai-api`. Ce rôle change l'app, son image et sa
commande comprises, donc exécute du code sous `id-kb-ai-api`, qui lit les deux clés dans le Key Vault (registre des
traitements, ligne « Déploiement continu »).

### La première exécution

Au moins 10 minutes après la passe : l'AcrPull et les deux Key Vault Secrets User qu'elle crée peuvent mettre jusqu'à
10 minutes à s'appliquer, et chaque exécution tire l'image et lit ses secrets à son départ. Un mercredi, un vendredi,
un samedi ou un dimanche, ou un lundi ou un jeudi après la fin du cron, hors des heures de « La règle des heures » :

```sh
az containerapp job start -n caj-kb-digest-watch -g "$RG" --query name -o tsv
az containerapp job execution list -n caj-kb-digest-watch -g "$RG" \
  --query "[].{name:name,status:properties.status,start:properties.startTime,end:properties.endTime}" -o table
```

Le journal, quelques minutes après la fin (`WS` : étape 6 d'« Appliquer ») :

```sh
az monitor log-analytics query -w "$WS" -o tsv \
  --analytics-query "ContainerAppConsoleLogs | where TimeGenerated > ago(3h) and JobName == 'caj-kb-digest-watch' | order by TimeGenerated asc" \
  --query "[].[TimeGenerated, Log]"
```

On y relève :
- `kb digest-watch started: 5 steps`, puis, pour chaque étape, `… step <n> of 5, <étape>, exited with <code>` ; les
  deux réveils portent `, not counted` dans le tableau des étapes ;
- pour `kb digest` :
  - `digest started: <n> subjects asked`, puis `digest finished in …` ;
  - la durée, face aux 200 s d'une demande ;
  - par sujet, `<sujet>: digest failed: <état> at the stage <étape>` ou `<sujet>: sheet not written: …` ;
  - dans le bilan, `Window: <début> → <fin>, <n> items read` ;
- pour `kb trend-report` : `trend report finished in …`, ou `no window after …; nothing written`. Un code 0 ne
  prouve pas que le modèle a répondu : `choice of the model not made: …` et `writing of chosen.<n> not made: …`
  l'écrivent, et le bilan porte `Model: none` ;
- la publication : `watch publication: <n> sheets found: <n> sent, <n> already in watch, …`.

Un sujet qui expire ne se rattrape pas le même jour : la fiche du jour d'un autre sujet bloque la relance de
`kb digest`.

**La première exécution, le 2026-11-11** (`caj-kb-digest-watch-suoshpa`, à la main, 16:21:16 → 16:25:25 UTC) :
- image tirée en 4 s ; réveil de l'API de données en 22 s, de l'API IA en 20 s ;
- `kb digest` : 141 items lus (fenêtre du 2026-11-08 au 2026-11-11), 2 min 13 s, 8 fiches sur 9. Le sujet
  `coding_assistants` finit `llm_invalid_output`, après deux sorties refusées par le contrôle `markup` (journal de
  l'API IA, `failed_check`). L'étape sort en 4 ;
- `kb trend-report` : 39 s, 4 fenêtres (du 2026-11-07 au 2026-11-10), 27 dépôts, code 0 ;
- publication : `13 sheets found: 9 sent, 4 already in watch` (les fiches des tops, publiées par la routine) ;
- code de sortie 4, donc `Failed` pour Azure, sans heure de fin, comme une exécution `Failed` de la routine.

Les journaux arrivent dans `log-kb` avec plusieurs minutes de retard : une exécution déjà `Failed` peut montrer un
journal arrêté au milieu d'une étape. On attend avant de conclure.

### Les comptes rendus, sur le Mac

```sh
make download-watch-sheets
ls "$VAULT"/veille/*/$(date -u +%F).md
```

Le bilan du téléchargement dit `<n> copied`. Il ne remplace jamais une fiche déjà sur le Mac : seul `copied` prouve
que la fiche vient de l'exécution. La fiche porte le jour UTC de l'exécution, d'où `date -u`.

Sources (Microsoft Learn, lues le 2026-11-11) :
[jobs de Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/jobs) (cron en UTC, « Set the replica
retry limit to at least 1 » pour la maintenance de la plateforme, rôles qui lisent les secrets d'un job),
[secrets de Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets) (« Permissions for
managing secrets » : les rôles Contributor des apps et des jobs couvrent `listSecrets`),
[dépannage d'Azure RBAC](https://learn.microsoft.com/en-us/azure/role-based-access-control/troubleshooting) (« it can
take up to 10 minutes for changes to take effect »).

## Le site privé (#571)

`ca-kb-web` lance `kb serve-web` (#562) depuis l'image de K-B. Sabine seule y entre (décision du 11/11). Le site ne
lit que l'API de données, par la clé du client `WEB`, et l'API de données lit `watch` pour lui (option A, décision du
11/11).

Trois verrous, dans l'ordre où une requête les rencontre :
1. **La connexion Microsoft Entra de la plateforme** (Easy Auth, `authConfigs`). Elle tourne à côté du conteneur, dans
   chaque réplique. Sans session, elle renvoie un navigateur (`Accept: text/html`) tout droit vers la page de
   connexion d'Entra, `login.microsoftonline.com/<tenant>` (302), et répond `401` à tout autre client (constaté le
   2026-11-11, « Les constats »). Elle n'admet que les comptes du tenant (`openIdIssuer`), et parmi eux le seul
   object ID de Sabine (`allowedPrincipals.identities`). Elle seule pose les en-têtes `X-MS-CLIENT-PRINCIPAL-*`,
   et elle retire ceux qu'envoie un client.
2. **Le contrôle du code** (#562) : chaque requête, sauf `/health`, porte `X-MS-CLIENT-PRINCIPAL-ID`, égal à
   `KB_WEB_OPERATOR_ID` ; sinon, 403.
3. **Le module refuse une entrée externe sans connexion** : `external` n'est suivi que si `entraSignIn` est posé avec
   l'ID de son inscription (`api-container-app.bicep`, `hasSignIn`). Le site naît fermé, en ingress interne, et ne
   s'ouvre que par `exposeWeb=true`, à une passe qui trouve sa connexion déjà posée en ligne.

Le contrôle du code ne tient pas seul : sans la connexion, rien ne retire un en-tête forgé. C'est pourquoi le site ne
s'ouvre qu'après la lecture de `authConfigs`.

**Un seul fournisseur d'identité, Microsoft Entra.** Le code ne vérifie pas `X-MS-CLIENT-PRINCIPAL-IDP`. Ajouter un
autre fournisseur à `ca-kb-web` demande d'abord de revoir ce contrôle.

| Réglage | Valeur |
|---|---|
| Commande, port | `serve-web`, 8002 ; 0,5 vCPU, 1 Gio, 0 à 1 réplique, comme les API |
| Identité | `id-kb-web` : AcrPull et ses deux secrets. `identityLifecycle` reste `None` : le code n'obtient aucun jeton, et n'a aucun droit dans Azure |
| Variables | `KB_DATA_DIR`, `KB_WEB_HOST=0.0.0.0`, `KB_WEB_PORT=8002`, `KB_WEB_ALLOWED_HOSTS` (le nom du site, aussi le `Host` des sondes), `KB_WEB_OPERATOR_ID` (`operatorObjectId`), `KB_DATA_API_URL` (le nom interne de l'API de données), `KB_DEPLOYMENT_ENVIRONMENT=production` ; `KB_WEB_AUTH` n'est pas posée (`entra` par défaut) |
| Secrets | `KB_DATA_API_KEY_WEB` ← `kb-data-api-key-web`. `kb-web-auth-client-secret` est un secret de l'app, que lit la connexion ; il n'est jamais une variable du conteneur |
| Connexion | `RedirectToLoginPage` ; HTTPS seul ; pas de magasin de jetons, donc le code ne reçoit que les en-têtes d'identité ; aucun chemin exclu, `/health` compris |
| Inscription d'application | « K-B site », un seul tenant (`AzureADMyOrg`), jetons d'identité permis, adresse de retour `https://ca-kb-web.<domaine>/.auth/login/aad/callback` ; sans « affectation requise », qui imposerait le consentement d'un administrateur |
| Secret client | expire le **2027-05-11** (« La rotation du secret client ») |
| API de données | `KB_EXCHANGE_BLOB_URL` et `KB_DATA_API_KEY_WEB` ; Storage Blob Data Reader sur `watch` seul |

Dans l'ordre, une écriture dans Azure ou dans Entra à la fois, et jamais pendant une exécution d'un cron (« La règle
des heures ») : **aucune passe entre 08:00 et 09:05 UTC, ni, le lundi et le jeudi, entre 10:00 et 10:35 UTC**. Une
passe change les apps et les jobs au milieu d'une exécution, comme un tag.
1. Le critère rouge.
2. L'inscription d'application, puis son principal.
3. Les deux secrets.
4. La passe A : le site fermé.
5. La lecture de la connexion.
6. La passe B : le site ouvert.
7. Les constats.
8. La fusion de la PR.

Jusqu'à la fusion, toute passe part de la branche de #571 : une passe depuis `main` retirerait les variables de
l'API de données. Le Deploy lit `deployment.json` au commit du tag : un tag posé avant la fusion ne touche pas le
site ; un tag posé après exige que `ca-kb-web` existe, sans quoi le Deploy échoue. La fusion vient donc après la
passe B.

### Le critère rouge

```sh
az containerapp show -n ca-kb-web -g "$RG" --query name -o tsv    # ResourceNotFound
az role assignment list --assignee "$(az identity show -g "$RG" -n id-kb-data-api --query principalId -o tsv)" --all \
  --query "[].{role:roleDefinitionName,scope:scope}" -o table    # rien sur …/containers/watch
az containerapp show -n ca-kb-data-api -g "$RG" --query "properties.template.containers[0].env[].name" -o tsv
```

La dernière commande ne doit montrer ni `KB_EXCHANGE_BLOB_URL` ni `KB_DATA_API_KEY_WEB`. Constaté par Sabine le
2026-11-11.

### L'inscription d'application et son principal

Par le compte de l'opératrice, qui peut créer une application dans le tenant (`allowedToCreateApps`, lu le 11/11) :

```sh
DOMAIN=$(az containerapp env show -n cae-kb -g "$RG" --query properties.defaultDomain -o tsv)
kb_check "$DOMAIN" && az ad app create --display-name "K-B site" --sign-in-audience AzureADMyOrg \
  --enable-id-token-issuance true --web-redirect-uris "https://ca-kb-web.$DOMAIN/.auth/login/aad/callback" \
  --query appId -o tsv
WEB_APP_ID=<le GUID rendu>
kb_check "$WEB_APP_ID" && az ad sp create --id "$WEB_APP_ID" \
  --query "{id:id,appId:appId,assignmentRequired:appRoleAssignmentRequired}" -o json
```

Attendu : un GUID, puis `assignmentRequired: false`. Fait le 2026-11-11.

### Les deux secrets du site

Dans son propre terminal, comme à l'étape 4 d'« Appliquer ». La clé du site est générée. Le secret client vient
d'Entra : il passe de la sortie de `az ad` au coffre par une variable, sans être affiché.

```sh
az keyvault secret set --vault-name "$KV" --name kb-data-api-key-web \
  --file <(python3 -c 'import secrets; print(secrets.token_urlsafe(32), end="")') -o none
WEB_SECRET=$(az ad app credential reset --id "$WEB_APP_ID" --display-name kb-web-easy-auth --end-date 2027-05-11 \
  --query password -o tsv) \
  && az keyvault secret set --vault-name "$KV" --name kb-web-auth-client-secret --file <(printf '%s' "$WEB_SECRET") -o none
unset WEB_SECRET
az ad app credential list --id "$WEB_APP_ID" --query "[].{name:displayName,end:endDateTime}" -o table
az keyvault secret list --vault-name "$KV" --query "[].name" -o tsv    # les noms, jamais les valeurs
```

`az ad app credential reset` sans `--append` remplace tous les secrets de l'application : c'est voulu la première
fois, pas à la rotation. Les deux secrets doivent exister avant la passe A, qui donne un rôle sur chacun.

### La passe A : le site fermé

Depuis la branche de #571, avec un `TAG` qui contient `kb serve-web` (#562), et `exposeWeb=false` :

```sh
kb_check "$RG" "$EMAIL" "$OPERATOR" "$OPERATOR_UPN" "$TAG" "$LLM_URL" "$LLM_MODEL" "$OTLP" "$WEB_APP_ID" && az deployment group what-if \
  -g "$RG" -f infra/main.bicep \
  -p budgetContactEmail="$EMAIL" operatorObjectId="$OPERATOR" operatorPrincipalName="$OPERATOR_UPN" imageTag="$TAG" \
     llmBaseUrl="$LLM_URL" llmModel="$LLM_MODEL" otlpEndpoint="$OTLP" webAuthClientId="$WEB_APP_ID" exposeWeb=false
```

Puis `create`, avec les mêmes paramètres.

Aperçu attendu :
- **à créer** :
  - `id-kb-web` et son AcrPull ;
  - `ca-kb-web`, en ingress interne (`external: false`), avec `identitySettings` en `None`, et son `authConfigs`
    `current` ;
  - 3 rôles Key Vault Secrets User : `kb-data-api-key-web` pour `id-kb-web` et pour `id-kb-data-api`,
    `kb-web-auth-client-secret` pour `id-kb-web` ;
  - Storage Blob Data Reader sur `watch` pour `id-kb-data-api` ;
  - Container Apps Contributor d'`id-kb-deploy` sur `ca-kb-web`.
- **à modifier** :
  - `ca-kb-data-api` : 2 variables (`KB_EXCHANGE_BLOB_URL`, `KB_DATA_API_KEY_WEB`) et 1 secret ;
  - l'image de `ca-kb-data-api`, de `ca-kb-ai-api` et des 4 jobs (`k-b@sha256:…` devient `k-b:<TAG>`, la même
    image), même avec `TAG` = la version en ligne ;
  - le bruit de l'étape 5.
- Tout autre écart arrête la passe, en particulier sur `cae-kb`, le stockage, les verrous, ou `ca-kb-ai-api` hors de
  son image.

AcrPull et les rôles du coffre d'`id-kb-web` naissent dans la même passe que l'app. Si l'app échoue sur « unable to
fetch secret », ou si le tirage de l'image est refusé, relancer la même commande 10 minutes plus tard.

### Lire la connexion, avant d'ouvrir

```sh
az containerapp auth show -n ca-kb-web -g "$RG" --query "{platform:platform.enabled,action:globalValidation.unauthenticatedClientAction,https:httpSettings.requireHttps,clientId:identityProviders.azureActiveDirectory.registration.clientId,secret:identityProviders.azureActiveDirectory.registration.clientSecretSettingName,issuer:identityProviders.azureActiveDirectory.registration.openIdIssuer,allowed:identityProviders.azureActiveDirectory.validation.defaultAuthorizationPolicy.allowedPrincipals.identities}" -o json
for app in ca-kb-web ca-kb-data-api; do
  az containerapp show -n "$app" -g "$RG" --query "{latest:properties.latestRevisionName,ready:properties.latestReadyRevisionName}" -o json
  az containerapp revision list -n "$app" -g "$RG" --query "[?properties.active].{name:name,health:properties.healthState}" -o table
done
az containerapp show -n ca-kb-data-api -g "$RG" --query "properties.template.containers[0].env[].name" -o tsv
az containerapp show -n ca-kb-web -g "$RG" --query "{external:properties.configuration.ingress.external,lifecycle:properties.configuration.identitySettings[0].lifecycle}" -o json
```

Attendu :
- `platform: true`, `RedirectToLoginPage`, `https: true` ;
- l'ID de « K-B site », `kb-web-auth-client-secret`, et `https://login.microsoftonline.com/<tenant>/v2.0` ;
- `allowed` : le seul object ID de Sabine ;
- pour chaque app, `latest` égal à `ready`, et cette révision `Healthy`. Une app dont la nouvelle révision a échoué
  (par exemple sur « unable to fetch secret ») garde l'ancienne, saine : sans cette égalité, le contrôle passerait à
  tort ;
- `KB_EXCHANGE_BLOB_URL` et `KB_DATA_API_KEY_WEB` parmi les variables de l'API de données ;
- `external: false` et `lifecycle: None`.

Un champ vide ou absent arrête la suite : le site reste fermé.

Les sondes visent le port 8002 du conteneur ; Microsoft Learn ne dit pas si elles passent par la connexion
(« Health probes in Azure Container Apps », lu le 2026-11-11). Une sonde envoie `Accept: */*`, comme `curl` par
défaut (page des sondes de kubernetes.io, lue le 2026-11-11) : si elle passait par la connexion, elle recevrait son
`401`, et la révision ne serait pas `Healthy`. C'est une déduction du constat de « Les constats », non vérifiée.
Le repli serait alors `excludedPaths: ['/health']`, qui sert `/health` sans connexion (un texte fixe, sans donnée),
sur l'accord de Sabine seulement. `Healthy` ne prouve que `/health` : c'est l'accueil affiché à Sabine (« Les
constats ») qui prouve que le site répond.

### La passe B : le site ouvert

Les mêmes commandes, avec `exposeWeb=true`, une fois la connexion lue. Aperçu attendu : seule l'entrée de
`ca-kb-web` change (`external`), avec `KB_WEB_ALLOWED_HOSTS` et le `Host` des sondes, qui passent du nom interne au
nom du site. Ensuite, chaque passe tire `exposeWeb` de la connexion en ligne (étape 5 d'« Appliquer »).

### Les constats

```sh
SITE=$(az deployment group show -g "$RG" -n main --query properties.outputs.webAddress.value -o tsv)
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' -H "Accept: text/html" "$SITE/"
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' -H "Accept: text/html" \
  -H "X-MS-CLIENT-PRINCIPAL-ID: $OPERATOR" "$SITE/"
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' -H "Accept: text/html" "$SITE/health"
```

Attendu : trois fois `302` vers `https://login.microsoftonline.com/<tenant>/oauth2/v2.0/authorize?…`, **jamais
`200`**. Le renvoi va tout droit à Entra, sans passer par `/.auth/login/aad`, car la connexion n'a qu'un fournisseur.

La connexion ne renvoie vers la page de connexion qu'un navigateur, qui demande du HTML. Les mêmes `curl` sans
`-H "Accept: text/html"` reçoivent `401`, avec un en-tête `WWW-Authenticate: Bearer` qui nomme le tenant et l'ID
de l'inscription : là aussi, **jamais `200`**. Les deux comportements ont été constatés le 2026-11-11, après la
passe B.

Le deuxième essai forge l'en-tête de Sabine sans session : il ne change rien. Son `302` prouve que la connexion
répond avant le code, même à un en-tête forgé ; il ne prouve pas que l'en-tête est retiré. Ce retrait tient à la
plateforme (Learn : « External requests aren't allowed to set these headers »), et au code, qui refuse un en-tête
répété (#562). Puis Sabine ouvre `$SITE` dans son navigateur, se connecte, consent à la première connexion, et voit
l'accueil.

Ce que tranche la première connexion :
- **le consentement** : une application inscrite dans l'organisation reçoit le consentement de l'utilisateur pour les
  permissions « à faible impact », avec le réglage recommandé. Le réglage du tenant n'a pas été lu ;
- **l'accès conditionnel du tenant**, illisible avec nos droits ;
- **le chemin de l'en-tête** : il porte bien l'object ID, la connexion lit le secret référencé au coffre, et le
  `Host` passe jusqu'au code.

Un refus « Need admin approval », ou une erreur AADSTS, arrête l'essai. Le repli par mot de passe est alors au choix
de Sabine.

**Règle d'arrêt.** Si un `curl` sans connexion rend `200`, avec ou sans `Accept: text/html`, ou si la connexion n'est
plus posée, fermer l'entrée tout de suite :

```sh
az containerapp ingress disable -n ca-kb-web -g "$RG"
```

Le 403 de `allowedPrincipals` pour un autre compte du tenant ne se constate qu'avec un second compte. Sans lui, il
reste non constaté, et le contrôle du code tient seul la vérification du compte.

### La rotation du secret client

Le secret expire le **2027-05-11**, et time-knight rappelle la date. Après elle, la connexion échoue, et le site n'est
plus joignable. La rotation ne coupe pas la connexion : l'ancien secret reste valide jusqu'à ce que la plateforme
lise le nouveau.

```sh
WEB_APP_ID=$(az ad app list --display-name "K-B site" --query "[].appId" -o tsv)
[ "$(az ad app list --display-name "K-B site" --query "length(@)" -o tsv)" = 1 ] || WEB_APP_ID=''
END_DATE=<AAAA-MM-JJ>
OLD_KEY=$(az ad app credential list --id "$WEB_APP_ID" --query "[?displayName=='kb-web-easy-auth'].keyId" -o tsv)
kb_check "$WEB_APP_ID" "$END_DATE" "$OLD_KEY" && WEB_SECRET=$(az ad app credential reset --id "$WEB_APP_ID" --append \
  --display-name kb-web-easy-auth --end-date "$END_DATE" --query password -o tsv) \
  && az keyvault secret set --vault-name "$KV" --name kb-web-auth-client-secret --file <(printf '%s' "$WEB_SECRET") -o none
unset WEB_SECRET
```

Puis, dans l'ordre :
1. attendre 30 minutes : la plateforme lit la dernière version d'un secret dans les 30 minutes (étape 4
   d'« Appliquer ») ;
2. redémarrer la révision active de `ca-kb-web`, comme à l'étape 4 ;
3. vérifier que Sabine se connecte. Avant ces 30 minutes, ce constat passerait encore avec l'ancien secret ;
4. retirer l'ancien secret : `az ad app credential delete --id "$WEB_APP_ID" --key-id "$OLD_KEY"` ;
5. reporter la date nouvelle ici, au registre et dans `MEMORY.md`.

### Limites

- **`id-kb-deploy` reçoit Container Apps Contributor sur `ca-kb-web`** (`deployment.json`). Les actions du rôle
  sont `Microsoft.App/containerApps/*/read`, `*/write`, `*/delete` et `*/action`, sans exclusion (Learn, « Azure
  built-in roles for Containers », mise à jour le 2026-07-01). Il peut donc changer l'image, les réglages et la
  connexion du site (`authConfigs/write`), et lire en clair son secret client et la clé `WEB` (`listSecrets`, Learn,
  « Manage secrets in Azure Container Apps »). Retirer la connexion rendrait le site public : sans elle, un en-tête
  d'identité se forge, et le contrôle du code ne tient plus. Il n'y gagne aucune donnée : il tient déjà
  `ca-kb-data-api`.
  Pour réduire le risque :
  - les rulesets des tags et l'environnement `production` (« Déployer une version ») ;
  - une alerte du journal d'activité, gratuite, sur `Microsoft.App/containerApps/authConfigs/write`, qui détecte sans
    empêcher (faisable avec nos droits, non posée).
- **Le coût d'un réveil sans connexion.** Le sidecar tourne dans la réplique : une requête sans connexion réveille
  donc le site. C'est une déduction, non vérifiée à la source. Un robot qui le tiendrait éveillé tout le mois
  coûterait environ 39 $ de plus.
  Pour réduire le risque :
  - les alertes du budget, à 50 % et à 100 % : faisable, déjà en place ;
  - `ipSecurityRestrictions` sur l'entrée : faisable avec nos droits, mais non retenu, car l'adresse de Sabine change.
- **Le réveil en chaîne**, le site puis l'API de données : environ 50 s. Ouvrir le site quelques minutes avant d'en
  avoir besoin.
- **Un appel direct au port du conteneur, depuis une autre charge de `cae-kb`.** Il passerait à côté de la connexion,
  avec un en-tête forgé. Learn ne décrit d'appel entre apps que par leur entrée (« Communicate between container
  apps ») ; un mainteneur de Microsoft écrit que l'accès à une réplique par son IP n'est pas pris en charge
  (microsoft/azure-container-apps #531, 2022-12-20), mais « non pris en charge » ne veut pas dire « bloqué » ; et
  les apps d'un environnement partagent le même réseau (Architecture Center, « Container Apps » multitenant, mise à
  jour le 2026-10-13). Ni démontré, ni exclu. Il faut d'abord exécuter du code dans une autre pièce de K-B, et
  l'attaquant n'y gagne que ce que lit la clé `WEB`, que `ca-kb-data-api` tient déjà. **Risque accepté par Sabine le
  2026-11-11.**
  Pour réduire le risque : une lecture du site à chaque Deploy, avec le `curl` à l'en-tête forgé, est une issue à
  ouvrir après #571 (faisable, du workflow seulement) ; vérifier dans le site le jeton signé par Entra au lieu de
  l'en-tête d'identité, ce qui ne se forge pas sans la clé d'Entra (issue à ouvrir plus tard, demandée par
  Sabine ; une dépendance de plus, sur son accord) ; un environnement à part pour le site couperait le réseau commun
  (faisable avec nos droits, non retenu pour le 13/11).
- **Des droits posés avant leur code** (consigne de time-knight du 2026-11-11, pour éviter une seconde passe). Depuis
  #563 (fusionnée le 2026-11-11), le site lit `KB_DATA_API_URL` et la clé `WEB`. Seuls le rôle de lecture sur `watch` et
  `KB_EXCHANGE_BLOB_URL` existent encore avant que l'API de données les lise (#559 à #561). Pour réduire le risque :
  ils restent sans code quelques jours, et #559 les utilise ; le rôle ne donne que la lecture de `watch`.

Sources (lues le 2026-11-11) :
- Microsoft Learn :
  - [Authentication and authorization in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/authentication),
    mise à jour le 2026-07-08 : le sidecar, les en-têtes que seule la plateforme pose, `allowInsecure` désactivé, les
    commandes `az ad` ;
  - [`Microsoft.App/containerApps/authConfigs`](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/containerapps/authconfigs)
    et [son journal des versions](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/change-log/containerapps/authconfigs)
    (`2026-07-01` n'ajoute que le magasin de jetons) ;
  - [`az ad app credential`](https://learn.microsoft.com/en-us/cli/azure/ad/app/credential) ;
  - [consentement de l'utilisateur](https://learn.microsoft.com/en-gb/entra/identity/enterprise-apps/configure-user-consent) ;
- [sondes de Kubernetes](https://kubernetes.io/docs/concepts/workloads/pods/probes/) ;
- [Azure Retail Prices](https://prices.azure.com/api/retail/prices), France Central, en USD et en EUR.

## La relecture de la configuration (#497)

La configuration en ligne des apps se relit de deux façons (API8 de l'auto-évaluation OWASP, « Revue périodique des
configurations ») : les requêtes de « La relecture de la configuration » (étape 6), relancées par Sabine à chaque
version déployée ; et deux politiques intégrées d'Azure Policy, d'effet `Audit`, assignées au groupe
(`container-apps-policies.bicep`), qu'Azure réévalue une fois toutes les 24 h. Ce sont des définitions intégrées : une
définition personnalisée se crée dans un groupe d'administration ou un abonnement (« The definition location must be a
management group or a subscription. », page « Azure Policy definition structure basics », lue le 2026-11-18), où
Sabine n'est que lectrice ; l'assignation se crée au niveau du groupe, dont elle est propriétaire. Azure Policy est gratuit pour les ressources Azure (« There are no charges for using Azure Policy on
Azure resources. », page des prix d'Azure Policy, relue le 2026-11-21).

### Appliquer #497 en ligne

Après la fusion de #630 (décision de Sabine du 2026-11-18 : aucune passe avant). Le module ne dépend pas de l'image :
la première passe l'applique, la seconde aussi.

1. Le critère rouge, avant la passe, par le nom des assignations (le nom affiché est celui de la définition, qu'un
   autre projet du groupe peut avoir assignée) :
   `az policy assignment list -g "$RG" --query "[?starts_with(name, 'audit-kb-')].name" -o tsv` ne rend rien. Et
   `az provider show -n Microsoft.PolicyInsights --query registrationState -o tsv` rend `Registered` : sinon, son
   enregistrement, un geste d'un Contributor ou d'un Owner de l'abonnement, vient avant la passe.
2. La première passe (étape 2). Aperçu attendu, déduit du Bicep : **à créer** `audit-kb-ca-external-ingress` et
   `audit-kb-ca-https-only` ; **à modifier** le bruit de l'étape 2.
3. Les constats : « La relecture de la configuration » et « Les politiques d'audit » (étape 6).

Constaté le 2026-11-20, à la séance commune avec #501 : avant la passe, `az policy assignment list` ne rend rien et
`Microsoft.PolicyInsights` est `Registered` ; à l'aperçu, 2 ressources à créer, les deux assignations ; 31 à modifier
et 1 non analysable, les mêmes qu'à la passe de #501 (« L'alerte sur les jetons du modèle (#501) », « La poser ») ;
aucune suppression. La création a rendu `Succeeded` (fin à 23:38:26 UTC) ; l'évaluation à la demande a fini à
23:57 UTC. Le 2026-11-21 à 00:09 UTC, les lectures des politiques à l'étape 6 rendent l'attendu : les deux
assignations, `ca-kb-web` dans les `notScopes` d'`audit-kb-ca-external-ingress` ; `ca-kb-data-api` et `ca-kb-ai-api`
`Compliant` aux deux, `ca-kb-web` `Compliant` à `audit-kb-ca-https-only` ; à 00:15 UTC, au `summarize`, aucune
ressource non conforme aux deux assignations. La relecture de la configuration, à 00:09 UTC, rend les valeurs du
2026-11-08.

### Limites

- **L'audit ne refuse rien** : une app déployée avec une entrée externe ou en HTTP est signalée, pas bloquée.
  Pour réduire le risque : l'effet `Deny` (paramètre `effect` des deux définitions) refuserait son déploiement, en
  403 avant le fournisseur de ressources (page de l'effet `deny`, lue le 2026-11-18) ; faisable avec nos droits, propriétaire du groupe, mais non retenu : il refuserait aussi l'app d'un autre projet
  créée dans le groupe.
- **Les politiques visent tout le groupe** : assignées à `slaurentRG`, elles auditeraient aussi l'app d'un autre projet
  qui y serait créée, et ses constats s'ajouteraient à ceux de K-B. Le 2026-11-21, `az policy state list` ne montre
  que les trois apps de K-B.
  Pour réduire le risque : rien à refuser avec `Audit` ; la lecture de l'étape 6 nomme chaque app par son
  identifiant, ceux de K-B se lisent à part.
- **Les requêtes ne tournent qu'à la main** : une version déployée sans leur relecture n'est relue que par les
  politiques, qui ne voient ni le chiffrement entre les apps, ni les routes de l'environnement, ni les URL internes.
  Pour réduire le risque : un outil des passes (#455) pourrait les lancer ; faisable avec nos droits, ce sont des
  lectures.
