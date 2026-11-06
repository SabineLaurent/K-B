// The manual job caj-kb-smoke-test: kb smoke-test (#412) asks GET /health of both APIs by their
// internal name, then lists the container smoke-test by the identity of the job.
param location string
param tags object
param environmentId string
param identityName string
param registryServer string
param image string
@description('Variables of the container, by name, AZURE_CLIENT_ID apart.')
param environmentVariables object

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = {
  name: identityName
}

var plainVariables = [
  for variable in items(environmentVariables): {
    name: variable.key
    value: variable.value
  }
]
// The client id of the identity of the job: without it, the SDK asks for the system-assigned
// identity, which the job does not have.
var clientIdVariable = {
  name: 'AZURE_CLIENT_ID'
  value: identity.properties.clientId
}

resource job 'Microsoft.App/jobs@2026-01-01' = {
  name: 'caj-kb-smoke-test'
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
      triggerType: 'Manual'
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      // The retries of the storage SDK may last about 7 min (core/config.py), after the two /health
      // of 65 s at most each: beyond it, the replica is killed before its summary.
      replicaTimeout: 600
      // A failed smoke test must show: it is run again by hand, never retried.
      replicaRetryLimit: 0
      registries: [
        {
          server: registryServer
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
            'smoke-test'
          ]
          env: concat(plainVariables, [
            clientIdVariable
          ])
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
    }
  }
}
