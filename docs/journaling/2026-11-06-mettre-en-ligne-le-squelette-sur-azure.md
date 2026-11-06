# Mettre en ligne le squelette de K-B sur Azure

- **Date** : 2026-11-06
- **Branche** : `feat/online-skeleton`
- **Issue** : #414
- **Fichiers principaux** : `infra/main.bicep`, `infra/modules/api-container-app.bicep`,
  `infra/modules/key-vault-secret-access.bicep`, `infra/modules/container-registry.bicep`,
  `infra/modules/smoke-test-job.bicep`, `infra/README.md`

Suite de #411 (l'environnement `cae-kb` et le budget, journal ADR « Infrastructure : Bicep dans `infra/` ») et de
#412 (`kb smoke-test`, note `2026-11-06-kb-smoke-test-api-et-stockage-d-echange.md`). La note couvre le commit
2a7de6d (le Bicep) et les documents de la PR : `infra/README.md`, journal ADR, registre, `README.md`,
`.github/dependabot.yml`.

## Le pourquoi

#411 avait posé un environnement Container Apps vide. #414 y met le plus court chemin démontrable : un registre
d'images, un coffre de secrets, un espace de journaux, les deux API de K-B (`kb serve-data` et `kb serve-ai`),
joignables de l'intérieur seulement, et un job, `caj-kb-smoke-test`, qui prouve que tout se tient.
Le job lance `kb smoke-test` (#412). Celui-ci appelle `/health` sur les deux API par leur nom interne, puis liste
un conteneur du stockage d'échange avec l'identité managée du job. Critère de l'issue : l'exécution du job est
`Succeeded`.

Rien n'y lit encore de données : l'API de données démarre sans base, et répond 503 `database_missing` hors de
`/health`. #421 branche la base, #413 les jobs des fiches. #414 fournit le socle où ils se branchent.

## Le comment

### Un fichier, deux passes

Une app ne se crée que si son image est dans le registre et ses secrets dans le coffre. Or le registre et le coffre
sont créés par le même fichier. Le paramètre `imageTag` coupe donc le déploiement en deux :

```bicep
var suffix = take(uniqueString(resourceGroup().id), 8)
var deployWorkloads = !empty(imageTag)
```
(`infra/main.bicep:32-33`)

```bicep
module secretAccess 'modules/key-vault-secret-access.bicep' = if (deployWorkloads) {
```
(`infra/main.bicep:143`)

Première passe, `imageTag` vide : le socle. Ce sont les journaux, l'environnement, les trois identités, le
registre et ses rôles AcrPull, le coffre, le stockage d'échange et le budget. Entre les deux passes, Sabine pousse
l'image et pose les six secrets à la main. Seconde passe, avec l'étiquette de l'image : les rôles du coffre par
secret, les deux API et le job. La commande est la même, un paramètre de plus. Le suffixe est un hachage stable du
groupe de ressources : il rend uniques les noms qui doivent l'être sur tout Azure (registre, coffre, stockage), et
redonne les mêmes noms à chaque passage.

### Aucun secret dans la configuration : des identités managées

Chaque pièce a une identité gérée par Azure (`id-kb-data-api`, `id-kb-ai-api`, `id-kb-smoke-test`). Une app s'en
sert pour tirer son image et pour lire ses secrets, sans mot de passe nulle part :

```bicep
      secrets: [
        for variable in items(vaultEntries): {
          name: variable.value
          keyVaultUrl: '${vaultUri}secrets/${variable.value}'
          identity: identity.id
        }
      ]
      identitySettings: [
        {
          identity: identity.id
          lifecycle: 'None'
        }
      ]
```
(`infra/modules/api-container-app.bicep:83-97`)

Le secret n'est pas copié dans l'app. L'app en garde une **référence** au coffre, une URL sans version : une
nouvelle valeur l'atteint en 30 min au plus. `lifecycle: 'None'` retire l'identité au conteneur : le code de K-B
ne peut pas demander de jeton en son nom, seule la plateforme s'en sert. Le job, lui, en a besoin pour lister le
stockage. Il reçoit son `AZURE_CLIENT_ID` (`infra/modules/smoke-test-job.bicep:24`).

Le registre n'a pas de compte admin, et fixe le mode de ses rôles :

```bicep
    adminUserEnabled: false
    // Pinned: in the ABAC mode, which is to become the default, AcrPull is not honoured and the
    // Owner of the resource group cannot push.
    roleAssignmentMode: 'LegacyRegistryPermissions'
```
(`infra/modules/container-registry.bicep:21-24`)

### Un rôle par secret

Le coffre est en RBAC : un droit est un rôle Azure donné à une identité sur une portée. Ici, la portée est le
secret lui-même, pas le coffre :

```bicep
resource secretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for (grant, index) in grants: {
    name: guid(secrets[index].id, identities[index].id, secretsUserRoleId)
    scope: secrets[index]
```
(`infra/modules/key-vault-secret-access.bicep:28-31`)

L'API de données lit un seul secret, `kb-data-api-key-ai-digest`, et ne peut lire que lui. L'API IA en lit six.
Le nom du rôle est un `guid()` de ses trois composantes : le même rôle garde le même nom d'une passe à l'autre,
et Azure ne le recrée pas. Microsoft supporte ce rôle par secret, mais recommande plutôt un coffre par application.
Ici, il faudrait alors copier le secret partagé dans deux coffres.

### Deux API internes, et des sondes qui disent leur nom

```bicep
      ingress: {
        external: false
        targetPort: port
        transport: 'http'
        allowInsecure: false
      }
```
(`infra/modules/api-container-app.bicep:68-75`)

`external: false` : l'API n'a qu'un nom interne, `https://<app>.internal.<defaultDomain>`. Seules les pièces de
`cae-kb` le joignent, et une demande venue d'ailleurs reçoit une 404 du proxy. `allowInsecure: false` redirige le
HTTP vers le HTTPS, et comme le client de K-B ne suit aucune redirection, tout appel se fait en `https://`.

L'API de données compare l'en-tête `Host` de chaque demande à sa liste (`KB_DATA_API_ALLOWED_HOSTS`, le seul nom
interne). Or une sonde de santé envoie par défaut l'IP du pod en `Host`. La sonde aurait donc reçu une 400, et
Azure aurait redémarré l'app sans fin. La sonde porte donc ce nom :

```bicep
var probeHeaders = empty(probeHost) ? [] : [
  {
    name: 'Host'
    value: probeHost
  }
]
```
(`infra/modules/api-container-app.bicep:25-30`)

La sonde parle au conteneur directement, en HTTP sur son port, sans passer par l'entrée d'ACA. Trois sondes
`GET /health` : démarrage (jusqu'à 1 + 6 × 10 s), disponibilité (toutes les 5 s) et vie (toutes les 30 s)
(`infra/modules/api-container-app.bicep:114-138`).

### Zéro réplique au repos

```bicep
      scale: {
        minReplicas: 0
        maxReplicas: 1
      }
```
(`infra/modules/api-container-app.bicep:143-146`)

Au repos, aucune API ne tourne, et rien ne se paie au tarif actif. La première demande réveille l'API : le proxy
la garde, KEDA crée une réplique, et la demande passe quand la sonde de disponibilité répond. Une seule réplique
au plus, parce que le débit de chaque client est compté dans la mémoire d'une réplique (#161). Mesuré le 06/11 :
26 s pour réveiller l'API de données et 20 s pour l'API IA.

## Choix faits et options écartées

Le détail est au journal ADR, 2026-11-06, « Mise en ligne : le squelette de K-B sur Azure (#414) ».

| Choix | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Deux passes d'un même fichier (session, plan validé) | l'image et les secrets n'existent qu'entre les deux | deux fichiers : les mêmes noms déclarés deux fois ; secrets factices : écrasés au passage suivant |
| 0 réplique au repos, 1 au plus (Sabine, 06/11) | tient sous le budget de 30 € par mois avec PostgreSQL et le registre | 1 réplique gardée : environ 47 $ par mois |
| ACR Basic (Sabine, 06/11) | tiré par identité managée, sans secret, en France Central | GHCR : gratuit si public, mais tiré par un jeton GitHub à garder et renouveler, hors UE |
| Un rôle du coffre par secret (session) | l'API de données ne lit que son secret | un coffre par app (recommandé par Microsoft) : le secret partagé copié deux fois |
| `Host` dans les sondes de l'API de données (session) | sans lui, `/health` répond 400 à la sonde | des sondes TCP, le repli prévu : elles ne vérifient pas que l'app répond |
| Journaux par `azure-monitor` et un paramètre de diagnostic (session) | aucune clé de l'espace dans la configuration | `log-analytics` : la clé partagée dans `cae-kb` |
| Délai d'arrêt de 250 s pour l'API IA (session) | 240 s de demande au plus, les exports de fin, une marge | le défaut de 30 s : une fiche en cours coupée à l'arrêt |
| Job sans nouvel essai, 600 s au plus (session) | un échec doit se voir ; couvre les nouvelles tentatives du SDK | 1 nouvel essai (recommandé pour la maintenance) |
| Coffre : 7 jours de suppression réversible, sans protection de purge (session) | réglages irréversibles ; un nom gardé 90 jours bloquerait une recréation | 90 jours, protection de purge |

Imposés par une consigne : Sabine applique le Bicep à la main (#411, la CI n'a pas le droit de donner des rôles) ;
elle donne elle-même `llmBaseUrl`, `llmModel` et `otlpEndpoint` (06/11 : le `.env` n'est pas lu) ; une revue de
sécurité en xhigh avant la passe 1 (06/11).

## Preuve

| Sortie observée | Ce que ça démontre |
|---|---|
| Avant le Bicep : `az containerapp job execution list -n caj-kb-smoke-test` → `ResourceNotFound` | le test rouge : le critère n'était pas atteint |
| `az bicep build --file infra/main.bicep` sans avertissement | le fichier est valide pour Bicep v0.48.1 |
| `/security-review` (xhigh) sur le Bicep : aucun constat | aucune faille trouvée avant d'appliquer |
| Exécution `caj-kb-smoke-test-56tyd99` : `Succeeded` ; `log-kb` : `smoke test finished in 1 s: 3 of 3 checks passed`, `exchange storage: 0 blobs listed in smoke-test` | le critère de #414 : les deux `/health` joints par leur nom interne, la liste faite par l'identité du job |
| `az containerapp show … --query properties.configuration.ingress.external` → `false` pour les deux, révisions `Healthy` | les API sont internes, et leurs sondes passent |
| Aucune ligne `route=/health` dans `ContainerAppConsoleLogs` des API | la sonde de l'API de données porte le bon `Host` (un échec serait journalisé) |
| Journal de démarrage de l'API de données : `API allowed hosts: ca-kb-data-api.internal.…` | la liste des hôtes est le seul nom interne |
| Exécution `caj-kb-smoke-test-us77d03`, API au repos : `smoke test finished in 50 s` ; `KEDAScaleTargetActivated` à 18:30:04, `/health` de l'API de données à 18:30:30, de l'API IA à 18:30:50 | le réveil : 26 s et 20 s |

## Ce que tu dois pouvoir défendre

1. **Où est la sécurité, sans réseau privé ?** Dans l'identité. Aucun secret n'est écrit dans la configuration :
   les apps lisent le coffre par leur identité, chacune sur ses seuls secrets
   (`key-vault-secret-access.bicep:28-31`). Le registre n'a pas de compte admin, et le stockage refuse la clé
   partagée. Les API n'ont pas d'adresse publique (`external: false`). Reste un risque, accepté par Sabine le
   06/11 : les lecteurs de l'abonnement lisent les journaux et la configuration (registre, « Hébergement sur
   Azure »).
2. **Que se passe-t-il si l'API de données dort quand une fiche démarre ?** L'API IA attend sa réponse 10 s au
   plus, sans nouvel essai (`DATA_API_READ_TIMEOUT_SECONDS`). Le réveil prend 26 s : la fiche échoue. D'où la
   proposition faite à #413 : réveiller les deux API par `GET /health`, comme le fait le job, avant de demander
   les fiches.
3. **Pourquoi pas GHCR, gratuit ?** ACA n'y tire pas une image par identité managée : il faudrait un jeton
   GitHub, rangé dans le coffre et renouvelé, et l'image serait hors de l'UE. ACR coûte 5,07 $ par mois.
4. **Pourquoi deux passes, et pas un seul déploiement ?** Une app refuse de se créer si son image ou un de ses
   secrets manque. Le registre et le coffre doivent donc exister, et être remplis, avant les apps
   (`main.bicep:33`, `:143`).
5. **Pourquoi l'en-tête `Host` dans une sonde ?** L'API de données refuse tout `Host` inconnu, contre les
   attaques par en-tête `Host`. La sonde envoie par défaut l'IP du pod, et sans ce réglage l'app ne serait
   jamais déclarée saine (`api-container-app.bicep:25-30`).

## Zones non vérifiées

- Ce que voient au juste les lecteurs de l'abonnement : lire `log-kb` est documenté par Microsoft ; tirer l'image
  et voir la configuration est probable, non essayé. Le risque est accepté par Sabine.
- `logAnalyticsDestinationType` : Azure le relit vide alors que le Bicep le fixe à `Dedicated`. Les lignes
  arrivent pourtant dans les tables dédiées. La raison n'est pas connue.
- Le mTLS entre apps est laissé coupé, parce que ce qu'il ajoute au chiffrement n'est pas documenté.
- Le délai de 300 s avant qu'une API ne retourne à 0 : c'est le défaut documenté d'ACA, non chronométré ici.
- L'échec d'une fiche quand l'API de données dort : déduit du code et de la mesure, pas observé, aucune fiche
  n'ayant encore tourné en ligne.
- Les 30 min avant qu'une nouvelle valeur de secret n'atteigne une app, et les 10 min de propagation d'un rôle :
  documentation de Microsoft, non essayées.
- Le mode ABAC d'ACR, qui ignorerait AcrPull : documentation de Microsoft, non essayé.

## Ce qui reste

- La base en ligne et `KB_DATABASE_URL` : #421.
- Le stockage d'échange au complet (conteneurs, rôles des jobs) : #420.
- Les jobs des fiches, avec le réveil des API avant de les demander, et la limite d'un job sans délai d'arrêt
  réglable : #413.
- Le déploiement continu, et ce que permet le droit `jobs/start/action` : #415.
- Un réseau privé (VNet), qui fermerait au public le coffre, le registre et le stockage : non prévu.
- `limit_concurrency` d'uvicorn : décision encore ouverte au journal ADR.
- Deux textes de `main` décrivent encore l'avant-#414 : le commentaire des 60 s « to be measured by #414 »
  (`src/k_b/core/config.py:529-530`) et le point API4 de `docs/fiches-veille.md` (« Aucun fichier de
  déploiement »). Ils sont signalés dans la PR, hors de son périmètre.
