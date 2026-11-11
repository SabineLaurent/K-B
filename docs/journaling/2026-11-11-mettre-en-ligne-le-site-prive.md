# Mettre en ligne le site privé de K-B (`ca-kb-web`)

- **Date** : 2026-11-11
- **Branche** : `feat/private-site-infra`
- **Issue** : #571 (l'infra du site, 1er passage ; le code du site est #562, et le fil #563)
- **Fichiers principaux** : `infra/modules/api-container-app.bicep`, `infra/main.bicep`,
  `infra/modules/exchange-storage.bicep`, `infra/deployment.json`, `infra/README.md` (« Le site privé »),
  `docs/registre-traitements.md`
- **Décisions** : journal ADR, 2026-11-11, « Site en ligne : `ca-kb-web` derrière la connexion Entra de la
  plateforme » et « API de données : la lecture de `watch` pour le site »
- **Note précédente de la série** : [Ouvrir le socle du site privé](2026-11-11-ouvrir-le-socle-du-site-prive.md)
  (#562), le contrôle de l'en-tête dans le code

Les commits de la branche, rebasée sur `main` (94e7b2d), sont :
- 0285865, le Bicep ;
- c9f2d11, le README ;
- c7067f6, le registre ;
- 23aa702, l'ADR et `MEMORY.md` ;
- 76e99df, le tri des trois revues ;
- cfd9350, cette note ;
- 83906a9, le risque A4 accepté par Sabine, avec ses deux parades à venir.

Les autres commits listés depuis `66e03f1` appartiennent à d'autres PR, déjà fusionnées sur `main`, et cette note ne
les couvre pas.

## Le pourquoi

Sabine veut voir le site de K-B déployé et accessible à l'oral blanc du 13/11. Le 11/11, elle a décidé trois
choses :
- **le site est entièrement privé** : elle seule y entre ;
- **la connexion passe par Microsoft Entra**, assurée par la plateforme Azure Container Apps et doublée d'un
  contrôle dans le code (#562) ;
- **l'API de données est la seule porte du site** (option A) : elle lit les fiches publiées dans le conteneur
  `watch` et les sert en JSON. Le site ne lit qu'elle, et n'a aucun droit dans Azure.

Cette PR écrit l'infrastructure de ces décisions :
- une 3e app dans l'environnement `cae-kb` ;
- sa connexion Entra ;
- son identité ;
- sa clé pour l'API de données ;
- le droit de lecture de l'API de données sur `watch`.

L'application en ligne se fait à la main : Sabine fait les gestes, tn-codeur relit. Les gestes sont dans
`infra/README.md`, « Le site privé ».

## Le comment

### 1. La chaîne d'une requête, et qui retire les en-têtes

```
navigateur ──HTTPS──▶ entrée de cae-kb ──▶ réplique de ca-kb-web
                                           ├─ module de connexion (sidecar de la plateforme)
                                           │    sans session : 302 vers /.auth/login/aad
                                           │    session d'un autre compte : 403 (allowedPrincipals)
                                           │    session de Sabine : pose X-MS-CLIENT-PRINCIPAL-ID, transmet
                                           └─ conteneur kb serve-web (port 8002)
                                                en-tête absent, répété ou d'un autre object ID : 403 (#562)
```

La connexion tourne dans chaque réplique, à côté du conteneur. Elle seule pose les en-têtes
`X-MS-CLIENT-PRINCIPAL-*` : « External requests aren't allowed to set these headers, so they're present only if
set by Container Apps » (Microsoft Learn, « Authentication and authorization in Azure Container Apps », lu le
2026-11-11). Le contrôle du code compare `X-MS-CLIENT-PRINCIPAL-ID` à l'object ID de Sabine. **Il ne tient que si
la connexion est là** : sans elle, n'importe qui peut forger cet en-tête. Tout le reste de la PR découle de ce point.

### 2. La connexion, déclarée dans le module de l'app

```bicep
resource signInConfiguration 'Microsoft.App/containerApps/authConfigs@2026-01-01' = if (hasSignIn) {
  parent: app
  name: 'current'
```
(`infra/modules/api-container-app.bicep:198-200`)

`authConfigs` est une ressource enfant de l'app. Ses réglages (`:202-229`) :
- `RedirectToLoginPage` : un visiteur sans session est renvoyé vers la connexion ;
- `requireHttps` ;
- un émetteur limité au tenant du déploiement :
  `openIdIssuer: '${environment().authentication.loginEndpoint}${tenant().tenantId}/v2.0'` (`:218`) ;
- un seul object ID admis, celui de Sabine (`allowedPrincipals.identities`, `:222-226`).

Le secret client de l'inscription « K-B site » est un secret de l'app, référencé au coffre (`signInSecrets`,
`:93-101`). Il n'est **jamais** une variable du conteneur : la connexion le lit, le code ne le voit pas. Le module
sert aussi les deux API. Pour elles, `entraSignIn` est absent, la connexion n'est pas déclarée, et leur sortie
compilée ne change pas.

### 3. Le module refuse une entrée publique sans connexion

```bicep
var hasSignIn = entraSignIn != null && !empty(signIn.clientId)
```
(`infra/modules/api-container-app.bicep:91`)

```bicep
        external: external && hasSignIn
```
(`infra/modules/api-container-app.bicep:119`)

L'entrée ne devient externe que si la connexion est déclarée **avec l'ID de son inscription**. Sans cet ID, le
module ne pose ni connexion ni entrée externe : le site reste interne, joignable seulement depuis l'environnement.

`signIn` (`:84-88`) est `entraSignIn`, ou un objet aux valeurs vides quand il manque. ARM peut évaluer les propriétés
d'une ressource conditionnelle qu'il ne déploie pas, et une propriété lue sur `null` ferait échouer le déploiement
des deux API.

### 4. Le site naît fermé et s'ouvre ensuite : `exposeWeb`

ARM crée l'app **avant** son `authConfigs`, puisque l'un est l'enfant de l'autre. Le modèle compilé le montre :
`signInConfiguration` porte `dependsOn: ['app']`. Une app créée d'emblée en entrée externe serait donc publique
quelques instants sans connexion, et le resterait si `authConfigs` échouait.

D'où le paramètre `exposeWeb`, `false` par défaut, qui choisit aussi le nom du site :

```bicep
var webHost = exposeWeb
  ? 'ca-kb-web.${containerAppsEnvironment.outputs.defaultDomain}'
  : 'ca-kb-web.${internalDomain}'
```
(`infra/main.bicep:162-164`)

La première création se fait en deux passes :
1. **La passe A** (`exposeWeb=false`) crée le site en entrée interne, avec sa connexion.
2. On lit `az containerapp auth show`.
3. **La passe B** (`exposeWeb=true`) ouvre le site.

Ensuite, chaque passe tire `exposeWeb` de l'état en ligne :

```sh
[ "$(az containerapp auth show -n ca-kb-web -g "$RG" --query platform.enabled -o tsv 2>/dev/null)" = true ] \
  && EXPOSE_WEB=true || EXPOSE_WEB=false
```
(`infra/README.md:252-253`)

Une recréation, une app supprimée ou un groupe rebâti créent donc le site fermé. Un `exposeWeb` oublié ferme le site
au lieu de l'ouvrir.

### 5. L'identité du site n'a aucun droit pour son code

`ca-kb-web` a sa propre identité, `id-kb-web`. Elle n'a que deux rôles : AcrPull, pour tirer l'image, et Key Vault
Secrets User, sur ses deux secrets. Elle reste au défaut du module, `identityLifecycle: 'None'` (`:38`) : la
plateforme s'en sert, mais **le code ne peut obtenir aucun jeton**. Le commentaire du module le dit (`infra/main.bicep:304-306`).
C'est ce qui rend vraie la phrase « le site n'a aucun droit Azure ». Avec `Main`, comme pour l'API de données, le code
pourrait obtenir un jeton d'`id-kb-web` et lire le secret client.

Le site ne parle qu'à l'API de données, en interne, par la clé du client `WEB` (`KB_DATA_API_KEY_WEB`). La même
valeur est lue par les deux apps (`infra/main.bicep:170`, `:187`), comme `KB_DATA_API_KEY_AI_DIGEST` pour l'API IA.

### 6. L'API de données lit `watch`, et rien d'autre

```bicep
  {
    container: 'watch'
    principal: 'dataApi'
    roleId: blobDataReaderRoleId
  }
```
(`infra/modules/exchange-storage.bicep:170-174`)

Le rôle est posé sur un conteneur, jamais sur le compte, comme tous les rôles du stockage d'échange (#420). L'API de
données lit `watch`. Elle n'écrit nulle part, et ne lit ni `clippings` ni `zotero`. Elle reçoit
`KB_EXCHANGE_BLOB_URL` (`infra/main.bicep:250`). Son identité est déjà en `Main`, pour la base (#421) : son code
obtient donc le jeton qui lit `watch`.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Options écartées, et pourquoi |
|---|---|---|
| La connexion par la plateforme, doublée dans le code | Décision de Sabine du 11/11 ; seule la plateforme retire les en-têtes forgés, et K-B ne code ni OAuth 2 ni session | Un mot de passe codé par K-B : gardé en repli, si le tenant refusait le consentement |
| Deux passes (interne, puis `exposeWeb`), et le module qui refuse une entrée externe sans connexion | Décision de Sabine sur la recommandation de la session ; constat d'un sous-agent sans contexte, puis des trois revues | Une seule passe, qui laisse le site public le temps de sa création |
| `exposeWeb` tiré de la connexion en ligne à chaque passe | Tri de time-knight : une recréation doit naître fermée | `exposeWeb=true` en dur à l'étape 5, qui rouvrait la fenêtre |
| Entra seul fournisseur d'identité | Le code ne vérifie pas `X-MS-CLIENT-PRINCIPAL-IDP` (revue de sécurité de #562) | Un autre fournisseur, qui demanderait d'abord de revoir ce contrôle |
| `id-kb-web` à part, en `None` | Moindre privilège : aucun jeton pour le code | Partager `id-kb-data-api`, qui ouvre la base |
| Étendre `api-container-app.bicep` | Un module par app, sans une 5e copie de la boucle des variables (#554) | `web-container-app.bicep`, qui recopierait sondes, registre et identité |
| L'inscription créée à la main par `az ad` | Un objet créé une fois, par des commandes de Learn | L'extension Microsoft Graph de Bicep : un outil de plus pour la CI |
| Le secret client au coffre, valable jusqu'au 2027-05-11 | Comme les autres secrets ; 6 mois, au-delà du rendu et de la soutenance | MI as FIC, sans secret : décrit sur Learn pour App Service seulement |
| `authConfigs` en `2026-01-01` | La version de l'app, connue de Bicep v0.48.1 | `2026-07-01`, qui n'ajoute que le magasin de jetons |
| Pas de magasin de jetons, aucun chemin exclu | Le code ne reçoit aucun jeton, et rien n'est servi sans connexion | `excludedPaths: ['/health']`, gardé en repli sur l'accord de Sabine |
| 0,5 vCPU et 1 Gio, de 0 à 1 réplique | Le réveil des API à cette taille est mesuré (20 à 26 s) | 0,25 vCPU, dont le réveil n'est pas mesuré |
| La clé `WEB` et le rôle sur `watch` dès cette passe | Consigne de time-knight : éviter une seconde passe avant le fil (#563) | Attendre leur code : un écart au moindre privilège, accepté pour quelques jours |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `~/.azure/bin/bicep build infra/main.bicep --stdout` : code 0, aucune ligne sur la sortie d'erreur (v0.48.1, celle de la CI) | Le Bicep se construit sans avertissement, versions d'API comprises |
| Modèle compilé : `external` = `[and(parameters('external'), variables('hasSignIn'))]` ; `authConfigs` sous `[variables('hasSignIn')]` ; `hasSignIn` exige `clientId` | Le garde de l'entrée et la condition de la connexion sont dans l'ARM, pas seulement dans le Bicep |
| Critère rouge, lu par Sabine le 11/11 : `ca-kb-web` → `ResourceNotFound` ; `id-kb-data-api` n'a qu'AcrPull et un secret ; aucune variable du site sur l'API de données | L'état de départ : rien de cette PR n'est en ligne |
| `az ad app create` → un appId ; `az ad sp create` → `assignmentRequired: false` | Le tenant de l'école laisse Sabine inscrire une application |
| Les deux `az keyvault secret set`, sans sortie | Les deux secrets sont posés, sans valeur affichée |
| `/security-review` : aucun constat au-delà de 80 % de confiance | Aucune vulnérabilité exploitable trouvée dans le changement |

La preuve en ligne viendra après les passes A et B (`infra/README.md`, « Les constats ») :
- `302` sans session, avec l'en-tête forgé ou non, **jamais `200`** ;
- l'accueil affiché à Sabine une fois connectée.

## Ce que tu dois pouvoir défendre

1. **Pourquoi deux contrôles, et lequel tient quand l'autre tombe ?**
   - La connexion de la plateforme authentifie (le tenant) et autorise (un seul object ID).
   - Le code revérifie l'object ID.
   - Si `allowedPrincipals` ne tenait pas pour un autre compte du tenant, le code refuse ce compte : son en-tête porte
     son propre object ID.
   - Si la connexion manque, le code ne tient plus, puisque l'en-tête se forge. C'est pourquoi le module refuse alors
     l'entrée externe (`api-container-app.bicep:119`).
2. **Que se passe-t-il si `authConfigs` échoue ?** Le site ne s'ouvre pas. Une création passe toujours d'abord en
   entrée interne (`exposeWeb` tiré de l'état en ligne, `infra/README.md:252-253`), et sans l'ID de l'inscription,
   le module ne pose pas d'entrée externe (`:91`). La règle d'arrêt ferme l'entrée si un `curl` rend `200`.
3. **Le site a-t-il des droits dans Azure ?** Non. `id-kb-web` ne sert qu'à la plateforme : elle tire l'image et lit
   deux secrets. En `None`, le code n'obtient aucun jeton (`:38`). Le site lit l'API de données par une clé, en interne.
4. **Qui pourrait quand même ouvrir le site ?** `id-kb-deploy`, l'identité du déploiement continu. Elle reçoit
   Container Apps Contributor sur l'app, et ce rôle porte `containerApps/*/write` et `*/action` (Learn, « Azure
   built-in roles for Containers »). Elle pourrait donc retirer la connexion et lire le secret client. Elle n'y
   gagne aucune donnée, puisqu'elle tient déjà l'API de données. Parades :
   - les rulesets des tags et l'environnement `production` ;
   - une alerte du journal d'activité sur `authConfigs/write`, faisable mais non posée.
5. **Combien ça coûte ?** Au cours de l'API des prix du 11/11, environ 1,5 € par mois pour le site, à 1 h d'usage par
   jour. Tout K-B passe à environ 25,7 à 27,2 €, sous le budget de 30 €. Un robot qui tiendrait le site éveillé tout
   le mois coûterait environ 39 $ de plus, car une requête sans connexion réveille la réplique ; l'alerte du budget à
   50 % le signale.

Les codes de réponse :
- **302** : pas de session, renvoi vers la connexion ;
- **401** : un client sans navigateur, ou une sonde, si elle passait par la connexion ;
- **403** : un compte du tenant hors de `allowedPrincipals`, venant de la plateforme, ou un en-tête refusé par le
  code (#562).

## Zones non vérifiées

- **Le chemin des sondes.** Learn ne dit pas si elles passent par la connexion. Si oui, le 302 compte comme un succès,
  si bien que `Healthy` ne prouve pas que le site répond. Seul l'accueil affiché le prouve.
- **Un appel direct au port 8002 depuis une autre pièce de `cae-kb`**, qui passerait à côté de la connexion. Ce n'est
  ni démontré ni exclu : Learn ne décrit d'appel entre apps que par l'entrée, et le réseau de l'environnement est
  commun.
- **Le 403 de `allowedPrincipals` pour un autre compte du tenant.** Il faudrait un second compte pour le constater.
- **Le consentement et l'accès conditionnel du tenant de l'école.** Ils se voient à la première connexion.
- **Ce que la connexion écrit dans `log-kb`.**
- **L'effet du réveil sans connexion sur le coût** : une déduction, non vérifiée à la source.
- **Le nom `current` d'`authConfigs`.** Il vient des exemples de l'API REST (registre Pulumi) et de l'usage d'az CLI ;
  il se constate au `what-if` et au `create`.

## Ce qui reste

- **La passe A, puis la passe B**, que tn-codeur applique avec Sabine, une fois le socle du site dans un tag ;
  ensuite les constats en ligne, puis la fusion.
- **Une issue après cette PR**, pour lire le site à chaque Deploy, avec le `curl` à l'en-tête forgé.
- **Le rôle Log Analytics Reader** pour les chiffres du back office : décision encore ouverte (journal ADR).
- **Le code qui lit la clé `WEB` et `watch`** : #563 (le fil) et #559 à #561 (l'API de données).
- **La rotation du secret client** avant le 2027-05-11 (`infra/README.md`, « La rotation du secret client »).
