// The secrets vault of K-B, in RBAC mode. Sabine sets the secrets by hand (infra/README.md): their
// values are never in the repository nor in a deployment; each identity reads its own secrets only
// (key-vault-secret-access.bicep).
param location string
param tags object
@minLength(8)
@maxLength(8)
param suffix string
@description('Object ID of the Entra account of the operator, who sets the secrets.')
param operatorObjectId string

var secretsOfficerRoleId = 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'

resource vault 'Microsoft.KeyVault/vaults@2026-05-15' = {
  name: 'kv-kb-${suffix}'
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    // Set at creation only. 7 days, the minimum: Sabine cannot purge a deleted vault, and its name
    // stays taken while it is recoverable. Purge protection is left off: it cannot be turned off.
    softDeleteRetentionInDays: 7
    // Without VNet, Container Apps reads the secrets by the public endpoint.
    publicNetworkAccess: 'Enabled'
  }
}

resource operatorSecretsOfficer 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, operatorObjectId, secretsOfficerRoleId)
  scope: vault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', secretsOfficerRoleId)
    principalId: operatorObjectId
    principalType: 'User'
  }
}

output name string = vault.name
output uri string = vault.properties.vaultUri
