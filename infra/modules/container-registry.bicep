// The image registry of K-B, ACR Basic (decision of Sabine of 06/11, rather than GHCR): the apps and
// the jobs pull by their managed identity, without any secret.
param location string
param tags object
@minLength(8)
@maxLength(8)
param suffix string
@description('Names of the identities that pull the image: each gets AcrPull on this registry only.')
param pullerIdentityNames array

var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource registry 'Microsoft.ContainerRegistry/registries@2025-11-01' = {
  name: 'crkb${suffix}'
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    // Pinned: in the ABAC mode, which is to become the default, AcrPull is not honoured and the
    // Owner of the resource group cannot push.
    roleAssignmentMode: 'LegacyRegistryPermissions'
    // The managed identities of Container Apps ask a token of this audience.
    policies: {
      azureADAuthenticationAsArmPolicy: {
        status: 'enabled'
      }
    }
    // Basic has no network rule nor private endpoint, and the environment has no VNet.
    publicNetworkAccess: 'Enabled'
  }
}

resource pullers 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = [
  for name in pullerIdentityNames: {
    name: name
  }
]

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for (name, index) in pullerIdentityNames: {
    name: guid(registry.id, pullers[index].id, acrPullRoleId)
    scope: registry
    properties: {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
      principalId: pullers[index].properties.principalId
      // Set, or a role given right after the identity is created may fail (principal not found yet).
      principalType: 'ServicePrincipal'
    }
  }
]

output name string = registry.name
output loginServer string = registry.properties.loginServer
