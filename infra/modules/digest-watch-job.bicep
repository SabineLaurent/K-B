// The scheduled job caj-kb-digest-watch (#423): kb digest-watch (#413) on its cron, the wake of both APIs, kb digest,
// the wake again, kb trend-report, then the publication of the watch. Its data directory is the share job-data, as for
// the routine (#330): the register of the trend reports is there, and the vault, where the reports of the day are
// looked for before any request. Its two secrets are the keys of the clients of the AI API, from the vault.
param location string
param tags object
param environmentId string
param identityName string
param registryServer string
param image string
@description('When the job starts, in UTC (main.bicep).')
param cronExpression string
@description('Variables of the container, by name, AZURE_CLIENT_ID and the secrets apart.')
param environmentVariables object
@description('Variable to Key Vault secret, read as a variable.')
param vaultEntries object
param vaultUri string
@description('The storage of the environment that holds the share job-data (job-files-storage.bicep).')
param jobDataStorageName string
@description('The data directory of the image, where job-data is mounted (main.bicep).')
param dataDir string

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = {
  name: identityName
}

var plainVariables = [
  for variable in items(environmentVariables): {
    name: variable.key
    value: variable.value
  }
]
var secretReferences = [
  for variable in items(vaultEntries): {
    name: variable.key
    secretRef: variable.value
  }
]
// The client id of the identity of the job: K-B asks its token for the storage.
var fixedVariables = [
  {
    name: 'AZURE_CLIENT_ID'
    value: identity.properties.clientId
  }
]

resource job 'Microsoft.App/jobs@2026-01-01' = {
  name: 'caj-kb-digest-watch'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    environmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Schedule'
      // Read in UTC by Container Apps; no run of the routine by hand at the same time (infra/README.md, « La règle
      // des heures »).
      scheduleTriggerConfig: {
        cronExpression: cronExpression
        parallelism: 1
        replicaCompletionCount: 1
      }
      // kb waits 240 s at most for each of its two requests and 65 s for each of the four wakes (core/config.py):
      // 740 s, then the publication, under 1 800 s unless the storage is slow.
      replicaTimeout: 1800
      // No retry (#423): after a timeout on the side of kb, a second run would call the model again. kb digest and kb
      // trend-report refuse only when the report of the day exists, which a cut run may not have written.
      replicaRetryLimit: 0
      registries: [
        {
          server: registryServer
          identity: identity.id
        }
      ]
      // Versionless URLs, as for the apps (api-container-app.bicep).
      secrets: [
        for variable in items(vaultEntries): {
          name: variable.value
          keyVaultUrl: '${vaultUri}secrets/${variable.value}'
          identity: identity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'kb'
          image: image
          args: [
            'digest-watch'
          ]
          env: concat(plainVariables, fixedVariables, secretReferences)
          // As the smoke test: calls over HTTP and a few sheets. Measured at the first run (infra/README.md).
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          volumeMounts: [
            {
              volumeName: 'job-data'
              mountPath: dataDir
            }
          ]
        }
      ]
      volumes: [
        {
          name: 'job-data'
          storageType: 'AzureFile'
          storageName: jobDataStorageName
          // The user of the image (#200), as for the routine.
          mountOptions: 'uid=10001,gid=10001,dir_mode=0700,file_mode=0600'
        }
      ]
    }
  }
}
