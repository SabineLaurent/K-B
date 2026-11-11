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
    // Far above the logs of K-B, which hold counts and states only: holds a runaway log near 0.2 GB
    // a day (2.76 $ a GB beyond the free 5 GB a month). Once it is reached, collection stops
    // until the reset hour of the workspace, which differs from one workspace to another and cannot
    // be configured. It does not stop exactly at the cap: the excess, larger when logs come fast, is
    // billed (Microsoft Learn, "Set daily cap on Log Analytics workspace", read on 2026-11-11).
    workspaceCapping: {
      dailyQuotaGb: json('0.2')
    }
  }
}

output id string = workspace.id
