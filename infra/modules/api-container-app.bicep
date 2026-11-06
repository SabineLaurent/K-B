// An API of K-B as a container app with internal ingress only: reached from the environment by
// https://<name>.internal.<defaultDomain>, never from the internet. Called once per API (main.bicep).
param name string
param location string
param tags object
param environmentId string
param identityName string
param registryServer string
param image string
@description('The kb command the container runs, such as serve-data.')
param command string
param port int
@description('Variables of the container, by name: values that are no secret.')
param environmentVariables object
@description('Variable name to the name of its Key Vault entry: names only, never a value.')
param vaultEntries object
param vaultUri string
@description('Host header of the probes, for an API that refuses any other host; empty: none.')
param probeHost string = ''
param terminationGracePeriodSeconds int = 30
@description('Who may use the identity: None, the platform only (image, secrets); Main, also the code of the container.')
@allowed([
  'None'
  'Main'
])
param identityLifecycle string = 'None'

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = {
  name: identityName
}

var probeHeaders = empty(probeHost) ? [] : [
  {
    name: 'Host'
    value: probeHost
  }
]
// GET, never HEAD: both APIs answer 405 to HEAD (#401). An HTTP probe sends the IP of the pod as
// Host unless told otherwise.
var probeRequest = {
  path: '/health'
  port: port
  scheme: 'HTTP'
  httpHeaders: probeHeaders
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

resource app 'Microsoft.App/containerApps@2026-01-01' = {
  name: name
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
      activeRevisionsMode: 'Single'
      ingress: {
        external: false
        targetPort: port
        transport: 'http'
        // HTTP is redirected to HTTPS; the clients of K-B follow no redirection, so they call in
        // HTTPS.
        allowInsecure: false
      }
      registries: [
        {
          server: registryServer
          identity: identity.id
        }
      ]
      // Versionless URLs: a new version of a secret reaches the app within 30 minutes.
      secrets: [
        for variable in items(vaultEntries): {
          name: variable.value
          keyVaultUrl: '${vaultUri}secrets/${variable.value}'
          identity: identity.id
        }
      ]
      // The identity pulls the image and reads the secrets. With 'None', the container itself cannot get
      // a token of it; with 'Main', its code can (the data API, for the base online, #421).
      identitySettings: [
        {
          identity: identity.id
          lifecycle: identityLifecycle
        }
      ]
    }
    template: {
      terminationGracePeriodSeconds: terminationGracePeriodSeconds
      containers: [
        {
          name: 'kb'
          image: image
          // The image runs kb (ENTRYPOINT): the command only.
          args: [
            command
          ]
          env: concat(plainVariables, secretReferences)
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          probes: [
            // Up to 60 s for kb and uvicorn to start after a wake from 0 replica.
            {
              type: 'Startup'
              httpGet: probeRequest
              initialDelaySeconds: 1
              periodSeconds: 6
              timeoutSeconds: 2
              failureThreshold: 10
            }
            {
              type: 'Readiness'
              httpGet: probeRequest
              periodSeconds: 5
              timeoutSeconds: 2
              failureThreshold: 3
            }
            {
              type: 'Liveness'
              httpGet: probeRequest
              periodSeconds: 30
              timeoutSeconds: 5
              failureThreshold: 3
            }
          ]
        }
      ]
      // 0 at rest (decision of Sabine of 06/11); 1 at most: the rate of each client is counted in
      // the memory of one replica, two during a rollout, when the old and the new revision run together.
      scale: {
        minReplicas: 0
        maxReplicas: 1
      }
    }
  }
}
