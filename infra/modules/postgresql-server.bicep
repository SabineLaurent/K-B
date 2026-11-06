// The PostgreSQL server of K-B: public access without VNet (network decision of 06/11), Microsoft
// Entra only (authentication decision of 06/11). The base kb and the roles of the identities are
// created in SQL by the administrator (infra/postgresql/, infra/README.md).
param location string
param tags object

@description('Suffix of the names Azure wants unique worldwide.')
param suffix string

@description('Object id of the Microsoft Entra administrator of the server: given at deployment, never written in the repository.')
param administratorObjectId string

@description('Name of that administrator, its user principal name: given at deployment, never written in the repository.')
param administratorPrincipalName string

resource server 'Microsoft.DBforPostgreSQL/flexibleServers@2025-08-01' = {
  name: 'pgsql-kb-${suffix}'
  location: location
  tags: tags
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '18'
    // No password: every role is a Microsoft Entra principal, and the token is its password.
    authConfig: {
      activeDirectoryAuth: 'Enabled'
      passwordAuth: 'Disabled'
      tenantId: tenant().tenantId
    }
    // The smallest size; a full disk stops the writes rather than the bill growing.
    storage: {
      storageSizeGB: 32
      autoGrow: 'Disabled'
    }
    // The automatic backups of the server, 7 days, beside those of K-B (#390).
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    // Chosen at creation only: a server never moves into a VNet afterwards.
    network: {
      publicNetworkAccess: 'Enabled'
    }
  }
}

// The children of a server are updated one after the other: dependsOn chains them.
resource administrator 'Microsoft.DBforPostgreSQL/flexibleServers/administrators@2025-08-01' = {
  parent: server
  name: administratorObjectId
  properties: {
    principalType: 'User'
    principalName: administratorPrincipalName
    tenantId: tenant().tenantId
  }
}

// citext, in place of COLLATE NOCASE (docs/stockage.md); grant-roles.sql creates it in the base kb.
resource allowedExtensions 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2025-08-01' = {
  parent: server
  name: 'azure.extensions'
  properties: {
    value: 'CITEXT'
    source: 'user-override'
  }
  dependsOn: [
    administrator
  ]
}

// Without the DETAIL of an error, which quotes the row a constraint refused, an author with it, in
// the logs of the server (.claude/rules/poc.md, rule 5).
resource errorVerbosity 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2025-08-01' = {
  parent: server
  name: 'log_error_verbosity'
  properties: {
    value: 'TERSE'
    source: 'user-override'
  }
  dependsOn: [
    allowedExtensions
  ]
}

// "Allow public access from any Azure service": the outbound addresses of Container Apps are not
// fixed. It opens the server to the other customers of Azure too: the Entra authentication alone
// protects it. The address of the Mac is opened by az for an administration only (infra/README.md).
resource allowAzureServices 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2025-08-01' = {
  parent: server
  name: 'AllowAllAzureServicesAndResourcesWithinAzureIps'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
  dependsOn: [
    errorVerbosity
  ]
}

output name string = server.name
output fullyQualifiedDomainName string = server.properties.fullyQualifiedDomainName
