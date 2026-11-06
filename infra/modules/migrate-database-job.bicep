// The manual job caj-kb-migrate-database (#421): kb migrate-database creates the base online when it
// has no tables yet, and leaves it as it is when it has them. Its identity owns the tables; its role
// in the base is created by the administrator of the server (infra/postgresql/, infra/README.md).
param location string
param tags object

@description('Name of the identity of the job, which is also its role in the base.')
param identityName string

@description('Name of the registry of the image: the identity of the job gets AcrPull on it only.')
param registryName string

@description('Second pass: the job, once the image is pushed. The first pass makes the identity alone, for create-principals.sql.')
param deployJob bool

param environmentId string
param registryServer string
param image string

@description('Variables of the container, by name, AZURE_CLIENT_ID apart.')
param environmentVariables object

var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: identityName
  location: location
  tags: tags
}

resource registry 'Microsoft.ContainerRegistry/registries@2025-11-01' existing = {
  name: registryName
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identity.id, acrPullRoleId)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: identity.properties.principalId
    // Set, or a role given right after the identity is created may fail (principal not found yet).
    principalType: 'ServicePrincipal'
  }
}

var plainVariables = [
  for variable in items(environmentVariables): {
    name: variable.key
    value: variable.value
  }
]
// The client id of the identity of the job: K-B asks its token for the base (KB_DATABASE_AUTH entra).
var clientIdVariable = {
  name: 'AZURE_CLIENT_ID'
  value: identity.properties.clientId
}

resource job 'Microsoft.App/jobs@2026-01-01' = if (deployJob) {
  name: 'caj-kb-migrate-database'
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
      // The delay of #421.
      replicaTimeout: 600
      // A failed creation must show: it is run again by hand or by the next delivery, never retried.
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
            'migrate-database'
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
  dependsOn: [
    acrPull
  ]
}

output principalId string = identity.properties.principalId
