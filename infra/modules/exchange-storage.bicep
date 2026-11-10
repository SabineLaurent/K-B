// The exchange storage of K-B (Blob), reached by managed identity only. Born with #414 with the
// container of the smoke test alone; #420 adds the containers of the exchanges with the Mac, their
// protections and one role per identity and container (decisions 3 to 8 of 2026-11-06).
param location string
param tags object
@minLength(8)
@maxLength(8)
param suffix string
param smokeTestIdentityName string
@description('Identity of kb daily-routine: reads clippings and zotero, writes watch.')
param dailyRoutineIdentityName string
@description('Identity of kb digest-watch: writes watch.')
param digestWatchIdentityName string
@description('Object ID of the Entra account of the operator (Sabine): sends clippings and zotero from the Mac, reads watch.')
param operatorObjectId string

var blobDataReaderRoleId = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
var blobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
// A deleted blob or container stays 30 days: the only way back for a container deleted by mistake.
var softDeleteDays = 30
// The copies of Zotero (zotero/<timestamp>/, #424) are erased after 14 days.
var zoteroCopyDays = 14

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
  properties: {
    // Each overwrite or deletion keeps the previous version (decision 6). Nobody can erase a version:
    // that needs Storage Blob Data Owner, which no one holds.
    isVersioningEnabled: true
    deleteRetentionPolicy: {
      enabled: true
      days: softDeleteDays
    }
    containerDeleteRetentionPolicy: {
      enabled: true
      days: softDeleteDays
    }
  }
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

// The exchanges with the Mac (decision 3): clippings and zotero go up, watch comes down. No wiki:
// no identity could write it (finding 13); a real ingest of the wiki on Azure is #170.
var exchangeContainerNames = [
  'clippings'
  'zotero'
  'watch'
]

resource exchangeContainers 'Microsoft.Storage/storageAccounts/blobServices/containers@2026-06-01' = [
  for name in exchangeContainerNames: {
    parent: blobService
    name: name
    properties: {
      publicAccess: 'None'
    }
  }
]

resource dailyRoutineIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = {
  name: dailyRoutineIdentityName
}

resource digestWatchIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = {
  name: digestWatchIdentityName
}

// The lock of direction (decision 4): a role per identity and container, none on the account. With the
// key cut, a sync in the wrong direction fails with 403. The APIs and id-kb-migrate-database get none.
// The name of a role is known at the start of the deployment, a principalId only once the identity exists:
// two tables.
var principalKeys = {
  dailyRoutine: dailyRoutineIdentity.id
  digestWatch: digestWatchIdentity.id
  operator: operatorObjectId
}
var principals = {
  dailyRoutine: {
    principalId: dailyRoutineIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
  digestWatch: {
    principalId: digestWatchIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
  operator: {
    principalId: operatorObjectId
    principalType: 'User'
  }
}
var grants = [
  {
    container: 'clippings'
    principal: 'dailyRoutine'
    roleId: blobDataReaderRoleId
  }
  {
    container: 'zotero'
    principal: 'dailyRoutine'
    roleId: blobDataReaderRoleId
  }
  {
    container: 'watch'
    principal: 'dailyRoutine'
    roleId: blobDataContributorRoleId
  }
  {
    container: 'watch'
    principal: 'digestWatch'
    roleId: blobDataContributorRoleId
  }
  {
    container: 'clippings'
    principal: 'operator'
    roleId: blobDataContributorRoleId
  }
  {
    container: 'zotero'
    principal: 'operator'
    roleId: blobDataContributorRoleId
  }
  {
    container: 'watch'
    principal: 'operator'
    roleId: blobDataReaderRoleId
  }
]

resource exchangeRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for grant in grants: {
    name: guid(
      exchangeContainers[indexOf(exchangeContainerNames, grant.container)].id,
      principalKeys[grant.principal],
      grant.roleId
    )
    scope: exchangeContainers[indexOf(exchangeContainerNames, grant.container)]
    properties: {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', grant.roleId)
      principalId: principals[grant.principal].principalId
      principalType: principals[grant.principal].principalType
    }
  }
]

// What the lifecycle rule erases stays 30 days in soft delete; the rule runs within 24 hours.
resource lifecycle 'Microsoft.Storage/storageAccounts/managementPolicies@2026-06-01' = {
  parent: account
  name: 'default'
  properties: {
    policy: {
      rules: [
        {
          name: 'erase-zotero-copies'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: {
              blobTypes: [
                'blockBlob'
              ]
              // A prefix starts with the container: without it, the rule would reach clippings too
              // (finding 3). Nothing erases clippings (Sabine, 2026-11-04).
              prefixMatch: [
                'zotero/'
              ]
            }
            actions: {
              baseBlob: {
                delete: {
                  daysAfterCreationGreaterThan: zoteroCopyDays
                }
              }
              // Without it, each erased copy would stay as a previous version, without end. Counted from
              // the first write of the version.
              version: {
                delete: {
                  daysAfterCreationGreaterThan: zoteroCopyDays
                }
              }
            }
          }
        }
      ]
    }
  }
}

// Against a mistake of the hand, not the deliberate act of an Owner, which stays in the activity log.
// ReadOnly would block the role assignments. CanNotDelete also blocks deleting a role on the account or
// its containers: lift it, act, set it again (infra/README.md).
resource lock 'Microsoft.Authorization/locks@2020-05-01' = {
  name: 'lock-${account.name}'
  scope: account
  properties: {
    level: 'CanNotDelete'
    notes: 'K-B exchanges with the Mac (#420): lift it only to remove a role or the account (#428).'
  }
}

output blobEndpoint string = account.properties.primaryEndpoints.blob
