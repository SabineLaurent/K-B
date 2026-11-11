// The rights of the continuous deployment (#415). id-kb-deploy signs in from GitHub Actions by OIDC, in the
// environment production only, pushes the image and changes the image of the apps and the jobs. Each role is on
// one resource, never on the resource group; no role on the vault, the storage nor the data. But a job it may
// change acts under the identity of that job: through caj-kb-daily-routine (#330), it may read the clips and the
// Zotero library, write the base, reach the share job-data and get the two secrets of the routine, a risk accepted
// by Sabine on 2026-11-10 (docs/registre-traitements.md, « Déploiement continu »). caj-kb-digest-watch (#423) adds no
// access: watch and job-data through the routine, and its two keys through ca-kb-ai-api, which holds them. Second
// pass: the apps and the jobs must exist.
param deployIdentityName string
param registryName string
@description('The apps and the jobs whose image the deployment changes (infra/deployment.json).')
param appNames array
param jobNames array
@description('Subject of the GitHub OIDC tokens allowed to sign in as id-kb-deploy.')
param githubSubject string

var acrPushRoleId = '8311e382-0749-4cb8-b61a-304f252e45ec'
// az acr login reads the registry through Azure Resource Manager, which AcrPush does not allow.
var readerRoleId = 'acdd72a7-3385-48ef-bd42-f606fba81ae7'
// Container apps only: the jobs need their own role.
var containerAppsContributorRoleId = '358470bc-b998-42bd-ab17-a7e34c199c0f'
var containerAppsJobsContributorRoleId = '4e3d2b60-56ae-4dc6-a233-09c8e5a82e68'

resource deployIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = {
  name: deployIdentityName
}

// One credential only: two written at the same time on one identity fail with 409.
resource githubCredential 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2024-11-30' = {
  parent: deployIdentity
  name: 'github-production'
  properties: {
    issuer: 'https://token.actions.githubusercontent.com'
    subject: githubSubject
    audiences: [
      'api://AzureADTokenExchange'
    ]
  }
}

resource registry 'Microsoft.ContainerRegistry/registries@2025-11-01' existing = {
  name: registryName
}

resource apps 'Microsoft.App/containerApps@2026-01-01' existing = [
  for name in appNames: {
    name: name
  }
]

resource jobs 'Microsoft.App/jobs@2026-01-01' existing = [
  for name in jobNames: {
    name: name
  }
]

resource registryRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for roleId in [acrPushRoleId, readerRoleId]: {
    name: guid(registry.id, deployIdentity.id, roleId)
    scope: registry
    properties: {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleId)
      principalId: deployIdentity.properties.principalId
      principalType: 'ServicePrincipal'
    }
  }
]

resource appRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for (name, index) in appNames: {
    name: guid(apps[index].id, deployIdentity.id, containerAppsContributorRoleId)
    scope: apps[index]
    properties: {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', containerAppsContributorRoleId)
      principalId: deployIdentity.properties.principalId
      principalType: 'ServicePrincipal'
    }
  }
]

resource jobRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for (name, index) in jobNames: {
    name: guid(jobs[index].id, deployIdentity.id, containerAppsJobsContributorRoleId)
    scope: jobs[index]
    properties: {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', containerAppsJobsContributorRoleId)
      principalId: deployIdentity.properties.principalId
      principalType: 'ServicePrincipal'
    }
  }
]

output clientId string = deployIdentity.properties.clientId
