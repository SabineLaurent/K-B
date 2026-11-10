// The Container Apps environment of K-B: Consumption profile only, without VNet (network decision of 06/11).
param location string
param tags object
@description('The Log Analytics workspace that receives the logs of the containers.')
param workspaceId string

resource environment 'Microsoft.App/managedEnvironments@2026-01-01' = {
  name: 'cae-kb'
  location: location
  tags: tags
  // Mounts the share job-data without account key (#420). System-assigned: bound to the environment, it
  // cannot be attached to another resource, unlike a user-assigned identity.
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
    // Set at creation only; zone redundancy would need a VNet.
    zoneRedundant: false
    // The logs go through the diagnostic setting below, by Azure Monitor: no shared key of the
    // workspace in the environment, as the log-analytics destination would need.
    appLogsConfiguration: {
      destination: 'azure-monitor'
    }
    // TLS between the apps of the environment: the AI API sends its key and reads the data of the
    // data API. Its cost, some latency under high load, does not apply to K-B.
    peerTrafficConfiguration: {
      encryption: {
        enabled: true
      }
    }
    // Left off: what it adds to the encryption above is not documented.
    peerAuthentication: {
      mtls: {
        enabled: false
      }
    }
    // Disabled accepts private endpoints only, which need a VNet. The apps are internal: a request
    // from outside the environment gets a 404 from its proxy.
    publicNetworkAccess: 'Enabled'
  }
}

// A preview: the version the template reference gives as current (2026-11-06), none stable since.
resource logs 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'logs-to-log-kb'
  scope: environment
  properties: {
    workspaceId: workspaceId
    // One table per category (ContainerAppConsoleLogs, ContainerAppSystemLogs), as Microsoft
    // recommends for a new setting.
    logAnalyticsDestinationType: 'Dedicated'
    logs: [
      {
        category: 'ContainerAppConsoleLogs'
        enabled: true
      }
      {
        category: 'ContainerAppSystemLogs'
        enabled: true
      }
    ]
  }
}

output id string = environment.id
output name string = environment.name
output defaultDomain string = environment.properties.defaultDomain
output principalId string = environment.identity.principalId
