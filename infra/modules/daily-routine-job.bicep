// The scheduled job caj-kb-daily-routine (#330): kb daily-routine (#413) every day at 03:00 UTC, the
// mirror of the clips, kb collect, kb import, kb write-tops, then the publication of the watch. Its data
// directory is the share job-data (#420), which keeps the raw, the state and the vault from one
// execution to the next; its secrets come from the vault, the key of BigQuery as a file.
param location string
param tags object
param environmentId string
param identityName string
param registryServer string
param image string
@description('Variables of the container, by name, AZURE_CLIENT_ID and the secrets apart.')
param environmentVariables object
@description('Variable to Key Vault secret, read as a variable.')
param vaultEntries object
@description('The Key Vault secret of the key of BigQuery, read as a file.')
param bigQueryKeySecretName string
param vaultUri string
@description('The storage of the environment that holds the share job-data (job-files-storage.bicep).')
param jobDataStorageName string
@description('The data directory of the image, where job-data is mounted (main.bicep).')
param dataDir string

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = {
  name: identityName
}

// Out of the share: the key is never written where the job keeps its data.
var secretsDir = '/mnt/secrets'
var bigQueryKeyFileName = 'bigquery-key.json'
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
var fixedVariables = [
  // The client id of the identity of the job: K-B asks its token for the storage and the base.
  {
    name: 'AZURE_CLIENT_ID'
    value: identity.properties.clientId
  }
  // kb collect reads GH Archive only when the variable is set (etl/collected_sources.py).
  {
    name: 'GOOGLE_APPLICATION_CREDENTIALS'
    value: '${secretsDir}/${bigQueryKeyFileName}'
  }
]
var vaultSecretNames = concat(map(items(vaultEntries), variable => variable.value), [
  bigQueryKeySecretName
])

resource job 'Microsoft.App/jobs@2026-01-01' = {
  name: 'caj-kb-daily-routine'
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
      // Read in UTC by Container Apps. A run takes minutes; no run by hand from 02:00 UTC to the end
      // of the run of the cron (infra/README.md, « La routine quotidienne (#330) »): nothing keeps two
      // runs apart until #426.
      scheduleTriggerConfig: {
        cronExpression: '0 3 * * *'
        parallelism: 1
        replicaCompletionCount: 1
      }
      // The bound of #330: replicaTimeout bounds the retry too, so a run never reaches 05:00 UTC, and a
      // second collect the same day finds no window of GH Archive due (etl/sources/gh_archive.py).
      replicaTimeout: 3600
      replicaRetryLimit: 1
      registries: [
        {
          server: registryServer
          identity: identity.id
        }
      ]
      // Versionless URLs, as for the apps (api-container-app.bicep).
      secrets: [
        for secretName in vaultSecretNames: {
          name: secretName
          keyVaultUrl: '${vaultUri}secrets/${secretName}'
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
            'daily-routine'
          ]
          env: concat(plainVariables, fixedVariables, secretReferences)
          // Measured at the first run (infra/README.md).
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          volumeMounts: [
            {
              volumeName: 'job-data'
              mountPath: dataDir
            }
            {
              volumeName: 'secrets'
              mountPath: secretsDir
            }
          ]
        }
      ]
      volumes: [
        {
          name: 'job-data'
          storageType: 'AzureFile'
          storageName: jobDataStorageName
          // The user of the image (#200), as the probe of #420 tried them: without them, the share is
          // mounted as root.
          mountOptions: 'uid=10001,gid=10001,dir_mode=0700,file_mode=0600'
        }
        {
          name: 'secrets'
          storageType: 'Secret'
          // The key of BigQuery alone: without this list, every secret of the job is a file of the
          // volume, the token of GitHub included.
          secrets: [
            {
              secretRef: bigQueryKeySecretName
              path: bigQueryKeyFileName
            }
          ]
        }
      ]
    }
  }
}
