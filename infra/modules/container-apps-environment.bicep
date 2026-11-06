// The Container Apps environment of K-B: Consumption profile only, without VNet (network decision of 06/11).
param location string
param tags object

resource environment 'Microsoft.App/managedEnvironments@2026-01-01' = {
  name: 'cae-kb'
  location: location
  tags: tags
  properties: {
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
    // Set at creation only; zone redundancy would need a VNet.
    zoneRedundant: false
    // No appLogsConfiguration, hence no log destination: the Log Analytics workspace log-kb comes with #414.
  }
}
