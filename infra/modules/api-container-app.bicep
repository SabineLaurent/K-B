// An app of K-B as a container app. Internal ingress by default, reached from the environment by
// https://<name>.internal.<defaultDomain> (the two APIs); from the internet only behind the sign-in of
// Microsoft Entra (the site, #571). Called once per app (main.bicep).

@description('The sign-in of Microsoft Entra in front of an app (Easy Auth): its registration and the one account let in.')
type entraSignInSettings = {
  @description('Application (client) ID of the app registration, single tenant: no secret.')
  clientId: string
  @description('Key Vault entry of its client secret: a secret of the app the platform reads, never a variable of the container.')
  clientSecretName: string
  @description('Object ID of the only Entra account let in.')
  allowedObjectId: string
}

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
@description('Ingress from the internet: honoured only with entraSignIn, so that no app of K-B is public without it.')
param external bool = false
@description('The sign-in of Microsoft Entra in front of the app; null: none, the app is internal.')
param entraSignIn entraSignInSettings?

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
// Versionless URLs: a new version of a secret reaches the app within 30 minutes.
var vaultSecrets = [
  for variable in items(vaultEntries): {
    name: variable.value
    keyVaultUrl: '${vaultUri}secrets/${variable.value}'
    identity: identity.id
  }
]
// Empty values when the app has no sign-in: ARM may evaluate the properties of a conditional resource that
// it does not deploy, and a property of null fails the deployment.
var signIn = entraSignIn ?? {
  clientId: ''
  clientSecretName: ''
  allowedObjectId: ''
}
// Without the ID of its registration, the app has no sign-in, so it stays internal: a sign-in that cannot work
// would leave nothing in front of the code.
var hasSignIn = entraSignIn != null && !empty(signIn.clientId)
// The client secret is a secret of the app, for the sign-in only: it is in no variable of the container.
var signInSecrets = hasSignIn
  ? [
      {
        name: signIn.clientSecretName
        keyVaultUrl: '${vaultUri}secrets/${signIn.clientSecretName}'
        identity: identity.id
      }
    ]
  : []

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
        external: external && hasSignIn
        targetPort: port
        transport: 'http'
        // HTTP is redirected to HTTPS; the clients of K-B follow no redirection, so they call in
        // HTTPS. The sign-in wants HTTPS only.
        allowInsecure: false
      }
      registries: [
        {
          server: registryServer
          identity: identity.id
        }
      ]
      secrets: concat(vaultSecrets, signInSecrets)
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

// The sign-in runs beside the container of each replica: it alone sets the X-MS-CLIENT-PRINCIPAL-*
// headers, and removes those a client sends (Microsoft Learn, "Authentication and authorization in Azure
// Container Apps", read on 2026-11-11). Microsoft Entra is the only provider: the code of the site does
// not check X-MS-CLIENT-PRINCIPAL-IDP, so another provider asks a new look at that check first.
resource signInConfiguration 'Microsoft.App/containerApps/authConfigs@2026-01-01' = if (hasSignIn) {
  parent: app
  name: 'current'
  properties: {
    platform: {
      enabled: true
    }
    globalValidation: {
      unauthenticatedClientAction: 'RedirectToLoginPage'
    }
    httpSettings: {
      requireHttps: true
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: signIn.clientId
          clientSecretSettingName: signIn.clientSecretName
          // The tenant of the deployment: an account of another tenant is refused.
          openIdIssuer: '${environment().authentication.loginEndpoint}${tenant().tenantId}/v2.0'
        }
        validation: {
          defaultAuthorizationPolicy: {
            allowedPrincipals: {
              identities: [
                signIn.allowedObjectId
              ]
            }
          }
        }
      }
    }
  }
}
