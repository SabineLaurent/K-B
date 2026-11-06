// The Log Analytics workspace log-kb, where the environment cae-kb sends the logs of the containers.
param location string
param tags object

resource workspace 'Microsoft.OperationalInsights/workspaces@2026-03-01' = {
  name: 'log-kb'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    // Within the 31 days included with the ingestion.
    retentionInDays: 30
    // Far above the logs of K-B, which hold counts and states only: bounds a runaway log at a few
    // cents a day (2.76 $ a GB beyond the free 5 GB a month). Beyond it, the day's logs are dropped.
    workspaceCapping: {
      dailyQuotaGb: json('0.2')
    }
  }
}

output id string = workspace.id
