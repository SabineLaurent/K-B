// The exchange storage of K-B (Blob), reached by managed identity only. Born here (#414) with the
// container of the smoke test alone; #420 adds the containers of the exchanges and their protections.
param location string
param tags object
@minLength(8)
@maxLength(8)
param suffix string
param smokeTestIdentityName string

var blobDataReaderRoleId = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'

resource account 'Microsoft.Storage/storageAccounts@2026-06-01' = {
  name: 'stkbexchange${suffix}'
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    accessTier: 'Hot'
    // Entra only: no account key, no SAS signed by a key, no anonymous read.
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
    allowBlobPublicAccess: false
    allowCrossTenantReplication: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    // An environment without VNet reaches public endpoints only, and so does the Mac (#424).
    publicNetworkAccess: 'Enabled'
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2026-06-01' = {
  parent: account
  name: 'default'
}

// SMOKE_TEST_CONTAINER of src/k_b/core/config.py, which kb smoke-test lists.
resource smokeTestContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2026-06-01' = {
  parent: blobService
  name: 'smoke-test'
  properties: {
    publicAccess: 'None'
  }
}

resource smokeTestIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = {
  name: smokeTestIdentityName
}

// On this container only: the job lists it, and reaches nothing else of the account.
resource smokeTestReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(smokeTestContainer.id, smokeTestIdentity.id, blobDataReaderRoleId)
  scope: smokeTestContainer
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataReaderRoleId)
    principalId: smokeTestIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

output blobEndpoint string = account.properties.primaryEndpoints.blob
