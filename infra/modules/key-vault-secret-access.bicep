// Key Vault Secrets User for each identity, on each of its secrets only, rather than on the vault:
// the data API reads one secret, which it shares with the AI API; a vault per app, as Microsoft
// recommends, would copy it. Second pass (main.bicep): the secrets must exist, set by Sabine, or the
// deployment fails here.
param vaultName string
@description('One entry per secret and identity: { secret, identity }.')
param grants array

var secretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'

resource vault 'Microsoft.KeyVault/vaults@2026-05-15' existing = {
  name: vaultName
}

resource secrets 'Microsoft.KeyVault/vaults/secrets@2026-05-15' existing = [
  for grant in grants: {
    parent: vault
    name: grant.secret
  }
]

resource identities 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = [
  for grant in grants: {
    name: grant.identity
  }
]

resource secretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for (grant, index) in grants: {
    name: guid(secrets[index].id, identities[index].id, secretsUserRoleId)
    scope: secrets[index]
    properties: {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', secretsUserRoleId)
      principalId: identities[index].properties.principalId
      principalType: 'ServicePrincipal'
    }
  }
]
