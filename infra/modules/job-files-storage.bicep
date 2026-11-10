// The storage of the jobs (Azure Files, decision 3 of 2026-11-06): the share job-data, that the Mac never
// touches (raw data, state, logs, working vault). The environment mounts it by its system-assigned
// identity, without account key (storage-mounts, Microsoft Learn, 2026-10-13: preview).
param location string
param tags object
@minLength(8)
@maxLength(8)
param suffix string
@description('The Container Apps environment that mounts the share.')
param environmentName string
@description('Principal ID of the system-assigned identity of the environment.')
param environmentPrincipalId string

var smbMiAdminRoleId = 'a235d3ee-5935-4cfb-8cc5-a3303ad5995e'
var shareName = 'job-data'

resource account 'Microsoft.Storage/storageAccounts@2026-06-01' = {
  name: 'stkbjobfiles${suffix}'
  location: location
  tags: tags
  // StorageV2: the pay-as-you-go model, billed on the space used; the quota of the share is a ceiling.
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    // The hardening of stkbexchange, the key cut included: the mount by identity works without the key (trial
    // of #420, 2026-11-10), though Microsoft advises against the cut on an account of Azure Files.
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
    allowBlobPublicAccess: false
    allowCrossTenantReplication: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: 'Enabled'
    // SMB by managed identity: an OAuth token over Kerberos, without Active Directory. The SMB settings
    // of the account keep Kerberos allowed (default): SMBOAuth neither enables nor checks it.
    azureFilesIdentityBasedAuthentication: {
      directoryServiceOptions: 'None'
      smbOAuthSettings: {
        isSmbOAuthEnabled: true
      }
    }
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2026-06-01' = {
  parent: account
  name: 'default'
  properties: {
    // A deleted share stays 30 days. It protects the whole share only, not each file (finding 17): the
    // snapshots taken by hand do that (infra/README.md).
    shareDeleteRetentionPolicy: {
      enabled: true
      days: 30
    }
  }
}

resource share 'Microsoft.Storage/storageAccounts/fileServices/shares@2026-06-01' = {
  parent: fileService
  name: shareName
  properties: {
    enabledProtocols: 'SMB'
    // Many small writes (write_file_atomically: a temporary file, a sync, a rename).
    accessTier: 'TransactionOptimized'
    // A ceiling with margin, in GiB: only the space used is billed.
    shareQuota: 100
  }
}

// At the scope of the account, as Microsoft requires for this role; the account holds this share only.
resource smbMiAdmin 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(account.id, environmentPrincipalId, smbMiAdminRoleId)
  scope: account
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', smbMiAdminRoleId)
    principalId: environmentPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource environment 'Microsoft.App/managedEnvironments@2026-01-01' existing = {
  name: environmentName
}

// A preview: the only version where the storage of an environment takes an identity (2026-03-02-preview).
// Any app or job of the environment that declares a volume of it mounts the share.
resource environmentStorage 'Microsoft.App/managedEnvironments/storages@2026-03-02-preview' = {
  parent: environment
  name: shareName
  properties: {
    azureFile: {
      accountName: account.name
      shareName: share.name
      accessMode: 'ReadWrite'
      identity: 'system'
    }
  }
  // A dependency does not wait for the propagation of the role (up to 10 minutes): if this PUT fails, the
  // deployment is run again later (infra/README.md).
  dependsOn: [
    smbMiAdmin
  ]
}

// Against a mistake of the hand, as for stkbexchange. It also blocks deleting a snapshot of the share
// (a control-plane operation) and a role on the account: lift it, act, set it again (infra/README.md).
resource lock 'Microsoft.Authorization/locks@2020-05-01' = {
  name: 'lock-${account.name}'
  scope: account
  properties: {
    level: 'CanNotDelete'
    notes: 'K-B storage of the jobs (#420): lift it only to delete a snapshot, a role or the account (#428).'
  }
}

output storageName string = environmentStorage.name
