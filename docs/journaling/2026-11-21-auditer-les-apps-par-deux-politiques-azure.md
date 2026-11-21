# Relire la configuration en ligne à chaque version, et auditer les apps par deux politiques Azure

- Date : 2026-11-21 (code du 2026-11-18 au 2026-11-20, posé en ligne le 2026-11-20)
- Branche : `feat/container-apps-audit-policies`
- Issue : #497 (PR #662)
- Fichiers : `infra/modules/container-apps-policies.bicep` (nouveau), `infra/main.bicep`, `infra/README.md`,
  `docs/fiches-veille.md` (API8 de l'auto-évaluation OWASP, et le compte), `docs/ADR/journal-decisions-projet.md`
- Série : [relire API8 et API10 après la mise en ligne](2026-11-08-relire-api8-et-api10-apres-la-mise-en-ligne.md)
  (la relecture du 2026-11-08, dont les requêtes sont reprises ici).

Les commits de #611 (`b06a40ab` à `4ca6e2f0`, PR #664) et de #501 (`1a2b1a9c` à `ffdf2a7a`, PR #665) de la liste
de la branche viennent des deux fusions d'`origin/main` (`c9f0e066`, `fd069bef`) : ils ont leurs notes,
`2026-11-20-relire-api10-depuis-le-jeton-de-production.md` et `2026-11-21-alerter-sur-les-jetons-du-modele.md`.
`MEMORY.md`, `docs/registre-traitements.md`, `infra/modules/model-token-alert.bicep` et ces deux notes viennent
d'eux.

## Le pourquoi

OWASP API8:2023 (*Security Misconfiguration*) demande un durcissement répétable **et** une revue périodique des
configurations de toute la pile. Le durcissement est le Bicep, relu en PR (#496). Mais rien ne relisait ce qui tourne
en ligne : une passe oubliée, un réglage changé dans le portail, et la configuration réelle s'écarte du dépôt sans
que personne ne le voie. La relecture du 2026-11-08 avait vérifié, à la main, que les deux API sont internes, en
HTTPS, et que l'API IA joint l'API de données par son nom interne ; elle n'avait été faite qu'une fois.

#497 la rend périodique de deux façons :

- **à chaque version déployée**, Sabine relance les requêtes de la relecture du 2026-11-08, écrites dans
  `infra/README.md` avec leurs valeurs attendues ;
- **entre deux versions**, deux politiques d'Azure Policy regardent chaque app du groupe, et Azure les réévalue une
  fois toutes les 24 h.

## Le comment

### Deux définitions intégrées, assignées au groupe

Azure Policy sépare la **définition** (la règle : « une app dont l'entrée est externe est non conforme ») de
l'**assignation** (où la règle s'applique, avec quels paramètres). K-B ne crée aucune définition : il assigne deux
définitions intégrées, fournies par Microsoft, au groupe de ressources.

```bicep
resource externalIngress 'Microsoft.Authorization/policyAssignments@2026-07-01' = {
  name: 'audit-kb-ca-external-ingress'
  properties: {
    displayName: 'Container Apps should disable external network access'
```

(`infra/modules/container-apps-policies.bicep:11-14`). La définition est nommée par son identifiant, le même dans
tous les tenants (`tenantResourceId(…, '783ea2a8-…')`, `:16-19`). La seconde assignation, `audit-kb-ca-https-only`,
suit le même modèle (`:32-47`). Pourquoi des définitions intégrées : une définition personnalisée se crée dans un
groupe d'administration ou un abonnement, où Sabine n'est que lectrice ; une assignation se crée au niveau du groupe,
dont elle est propriétaire.

### L'effet écrit : `Audit`

```bicep
    parameters: {
      effect: {
        value: 'Audit'
      }
    }
```

(`container-apps-policies.bicep:20-24`, et `:41-45`). L'effet dit ce que fait Azure d'une ressource non conforme :
`Audit` la signale dans l'état de conformité, `Deny` refuse son déploiement, `Disabled` n'évalue rien. Les deux
définitions ont `Audit` par défaut ; l'écrire quand même est la décision de Sabine du 2026-11-20 : le Bicep dit ce
qu'il fait sans ouvrir la définition, et une nouvelle version de la définition ne peut pas changer l'effet en
silence.

### Le site hors de la première politique : `notScopes`

```bicep
    // The site is open on purpose, behind the sign-in of Microsoft Entra (#571).
    notScopes: [
      resourceId('Microsoft.App/containerApps', webAppName)
    ]
```

(`container-apps-policies.bicep:25-28`). `ca-kb-web` a une entrée externe par choix : sans exclusion, il serait non
conforme pour toujours, et un constat permanent cache les vrais. Le nom vient de `webAppName`, une variable de
`main.bicep` (`:79`) que lisent aussi l'app du site (`:351`) et son hôte (`:194-195`) : le nom n'est écrit qu'une fois
dans le Bicep. `infra/deployment.json`, que lit `deploy.yml`, l'écrit aussi : un commentaire, `main.bicep:77-78`,
demande de renommer les deux ensemble. La politique HTTPS n'a pas d'exclusion : le site aussi refuse le HTTP.

### Les deux passes appliquent le module

```bicep
// Both passes: the policies audit the apps of the group, whatever the image (#497).
module containerAppsPolicies 'modules/container-apps-policies.bicep' = {
```

(`infra/main.bicep:166-167`). Le module n'est pas sous `deployWorkloads` : il ne dépend ni de l'image ni des apps, et
une passe sans `imageTag` (l'étape 2) le pose sans toucher aux apps. C'est ainsi que Sabine l'a posé le 2026-11-20.

### Les lectures : par le nom des assignations, puis l'évaluation à la demande

```sh
az policy state trigger-scan -g "$RG"
# Par le nom des assignations seulement : les deux ne visent que les apps (Microsoft.App/containerApps).
az policy state list -g "$RG" \
  --query "[?starts_with(policyAssignmentName, 'audit-kb-')].{app:resourceId, policy:policyAssignmentName, state:complianceState}" -o table
```

(`infra/README.md:376-379`). Trois choix dans ces lignes. Le filtre porte sur le **nom** de l'assignation
(`audit-kb-`), pas sur son nom affiché, qui est celui de la définition : un autre projet du groupe pourrait avoir
assigné la même. Le champ lu est `complianceState` : `isCompliant` est déprécié. Et `trigger-scan` est une **action**
(il lance une évaluation), pas une lecture : Sabine la lance, cinq minutes au moins après la passe, le temps qu'une
assignation nouvelle s'applique ; sans elle, il faudrait attendre la réévaluation des 24 h. En complément, `summarize`
rend des comptes, filtrés sur les deux assignations de K-B (`:380-382`) : à la racine de sa sortie, pas sous
`value[0]`, que la CLI ne rend pas.

### La relecture, ce que les politiques ne voient pas

```sh
az containerapp env show -n cae-kb -g "$RG" \
  --query "{encryption: properties.peerTrafficConfiguration.encryption.enabled, mtls: properties.peerAuthentication.mtls.enabled}"
az containerapp env http-route-config list -n cae-kb -g "$RG"
```

(`infra/README.md:357-359`). Les politiques regardent l'entrée de chaque app ; elles ne voient ni le chiffrement
entre les apps de l'environnement, ni ses routes, ni les URL internes que les apps se donnent
(`KB_DATA_API_URL`, `KB_DATA_API_ALLOWED_HOSTS`, `:353-354`), ni le mode des révisions (`activeRevisionsMode`,
`:355`), dont dépend la parade d'API9 : une seule révision active, `Single`. Ces requêtes, avec leurs valeurs
attendues (`:363-367`), le font à chaque version.

## Choix faits et options écartées

| Choix | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Définitions intégrées, assignées au groupe | Les droits de Sabine : propriétaire du groupe, lectrice de l'abonnement | Une définition personnalisée : elle se crée dans un abonnement ou un groupe d'administration |
| Effet `Audit`, écrit dans chaque assignation | Décision de Sabine du 2026-11-20 (constat 4 du relecteur Azure) ; inverse le plan du 2026-11-13, « pas de paramètre d'effet si le défaut est `Audit` » | `Deny` : il refuserait aussi l'app d'un autre projet créée dans le groupe ; une variable partagée : la décision dit « dans chaque assignation », et `code.md` factorise à la troisième occurrence |
| `ca-kb-web` exclu par `notScopes` | Le site est ouvert exprès, derrière Entra (#571) | Une exemption, visible comme « Exempt » : en API de préversion seulement |
| Ni identité ni `location` | Seuls les effets `deployIfNotExists` et `modify` en demandent | — |
| Le module hors de `deployWorkloads` | Il ne dépend ni de l'image ni des apps | Sous `deployWorkloads` : une passe sans `imageTag` ne le poserait plus |
| Les requêtes relancées à la main, à chaque version | C'est le texte de l'issue ; ce sont des lectures | Les lancer dans un outil des passes : #455 pourrait les reprendre |
| `policyAssignments@2026-07-01` | La version GA la plus récente (référence des modèles et Context7, le 2026-11-20) ; le build Bicep ne rend aucun BCP081 | — |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `~/.azure/bin/bicep build infra/main.bicep` : exit 0, aucun avertissement | Le module et la version d'API se construisent ; aucune version inconnue de Bicep |
| Avant la passe (2026-11-20, vers 18:41 UTC) : `az policy assignment list -g slaurentRG --query "[].name" -o tsv` ne rend rien ; `Microsoft.PolicyInsights` `Registered` | Le critère rouge : aucune assignation avant #497 ; le fournisseur qui évalue les politiques est là |
| Aperçu de la passe : 2 à créer (les deux assignations), 31 à modifier et 1 non analysable, les mêmes qu'à la passe de #501, aucune suppression | La passe ne crée que ce que #497 ajoute ; le reste est le bruit connu de l'étape 2 |
| Création `Succeeded` (fin à 23:38:26 UTC) ; `trigger-scan` fini à 23:57 UTC | Les deux assignations existent en ligne et ont été évaluées |
| `az policy assignment list` (2026-11-21, 00:09 UTC) : les deux, `ca-kb-web` dans les `notScopes` d'`audit-kb-ca-external-ingress` | L'exclusion du site est en place |
| `az policy state list` : `ca-kb-data-api` et `ca-kb-ai-api` `Compliant` aux deux ; `ca-kb-web` `Compliant` à `audit-kb-ca-https-only`, absent de l'autre | Les deux API sont internes et en HTTPS ; le site est en HTTPS |
| `az policy state summarize` : aucune ressource non conforme aux deux assignations de K-B | Le même constat, en comptes |
| La relecture du même jour : `external` false, `allowInsecure` false, `transport` `Http`, `customDomains` null pour les deux API ; les deux URL internes ; chiffrement entre les apps actif, mTLS coupé, aucune route | Les valeurs du 2026-11-08, inchangées |
| `docs/fiches-veille.md:1035`, `:1039` | API8 passe en « Écart voulu, justifié » ; le compte : 6 entrées tenues sur 10, les 4 autres des écarts voulus et justifiés |

## Ce que tu dois pouvoir défendre

1. **Pourquoi `Audit` et pas `Deny`, qui bloquerait une mauvaise configuration ?** `Deny` refuserait aussi le
   déploiement de l'app d'un autre projet créée dans le groupe, que K-B n'a pas à gouverner. La mauvaise
   configuration est signalée et lue : par les politiques entre deux versions, par la relecture à chaque version
   (`infra/README.md`, « Limites »).
2. **Pourquoi écrire l'effet, puisque c'est déjà le défaut ?** Pour que le Bicep se lise seul, et qu'une nouvelle
   version de la définition, qui changerait son défaut, ne change pas ce que fait K-B (`container-apps-policies.bicep:20-24`).
3. **Le site a une entrée externe : comment est-il conforme ?** Il est hors de la politique qui l'interdit, par
   `notScopes`, parce qu'il est ouvert exprès derrière la connexion Entra ; il reste sous la politique HTTPS, où il
   est conforme (`container-apps-policies.bicep:25-28`).
4. **Que voient les politiques que la relecture ne voit pas, et l'inverse ?** Les politiques voient chaque app du
   groupe, toutes les 24 h, sans geste. La relecture voit ce que les politiques ignorent : le chiffrement entre les
   apps, les routes, les URL internes et le mode des révisions ; elle tourne à chaque version
   (`infra/README.md:344-367`).
5. **Où est la sécurité de la PR elle-même ?** Aucune identité, aucun rôle, aucune `location` créés ; `notScopes`
   ne nomme qu'une app ; aucune requête du README n'affiche une clé (revue de sécurité du 2026-11-20, sans constat).

## Zones non vérifiées

- **Une exclusion qui nomme une app pas encore créée**, sur un groupe neuf à la première passe : aucune source ne dit
  qu'Azure l'accepte ou la refuse ; en ligne, le site existe depuis le 2026-11-11.
- **La fin d'une évaluation** n'a pas de délai garanti (« Get compliance data of Azure resources », « Evaluation
  triggers ») : celle du 2026-11-20 a fini environ 19 minutes après la création.
- **Une app non conforme** : aucune ne l'a été ; le passage à `NonCompliant` n'a pas été observé.

## Ce qui reste

- Lancer les requêtes de la relecture dans un outil des passes (#455).
- Les renvois `infra/main.bicep:N` que les fusions décalent (#663).
- La commande de « Les instantanés de `job-data` » ne montre pas leur date de suppression : une issue XS la
  reprendra, hors de #497.
