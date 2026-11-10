// K-B on Azure. Applied by hand by Sabine to her resource group (infra/README.md), checked by the CI.
// Two passes: without imageTag, the foundation (logs, registry, vault, identities, the two storage accounts,
// PostgreSQL server);
// once the image is pushed and the secrets set, with imageTag, the two APIs and the two jobs.
targetScope = 'resourceGroup'

@description('Region of every K-B resource: the resource group\'s by default (France Central).')
param location string = resourceGroup().location

@description('Address of the budget alerts: given at deployment, never written in the repository.')
param budgetContactEmail string

@description('Object ID of the Entra account of the operator (Sabine), Key Vault Secrets Officer.')
param operatorObjectId string

@description('User principal name of the Entra account of the operator (Sabine), administrator of the PostgreSQL server.')
param operatorPrincipalName string

@description('Tag of the image k-b in the registry; empty: the first pass, without the APIs and the job.')
param imageTag string = ''

@description('Second pass: URL of the model of the AI API (KB_LLM_BASE_URL), given by Sabine.')
param llmBaseUrl string = ''

@description('Second pass: name of the model (KB_LLM_MODEL), given by Sabine.')
param llmModel string = ''

@description('Second pass: OTLP endpoint of the metrics and traces of the AI API (KB_OTLP_ENDPOINT), given by Sabine.')
param otlpEndpoint string = ''

var tags = {
  project: 'k-b'
}
// For the names Azure wants unique in the world: stkbexchange and 13 characters would pass the 24 of
// a storage account.
var suffix = take(uniqueString(resourceGroup().id), 8)
var deployWorkloads = !empty(imageTag)
var identityNames = {
  aiApi: 'id-kb-ai-api'
  dataApi: 'id-kb-data-api'
  smokeTest: 'id-kb-smoke-test'
  // The continuous deployment (#415), signed in from GitHub Actions; it pulls nothing.
  deploy: 'id-kb-deploy'
  // Born with their roles on the exchange storage (#420), before their jobs (#330 for the routine).
  dailyRoutine: 'id-kb-daily-routine'
  digestWatch: 'id-kb-digest-watch'
}
// The apps and the jobs the continuous deployment updates, also read by .github/workflows/deploy.yml: a job
// added to the Bicep goes in this list too.
var deployment = loadJsonContent('deployment.json')
// The subject of the GitHub OIDC tokens of the environment production. K-B was created after 2026-07-15: its
// tokens carry the immutable form, owner and repository with their numeric IDs
// (GET /repos/SabineLaurent/K-B/actions/oidc/customization/sub: use_immutable_subject).
var githubDeploySubject = 'repo:SabineLaurent@189640103/K-B@1383589029:environment:production'
// The image has no KB_DATA_DIR (journal ADR, 2026-11-06): each piece sets it. No piece mounts a share
// yet: the directory of the image, emptied at each start, on purpose.
var dataDir = '/var/lib/knowledge_base'
// The ports of kb serve-data and kb serve-ai by default (core/config.py), set again on each app.
var dataApiPort = 8000
var aiApiPort = 8001

module logAnalytics 'modules/log-analytics.bicep' = {
  params: {
    location: location
    tags: tags
  }
}

module containerAppsEnvironment 'modules/container-apps-environment.bicep' = {
  params: {
    location: location
    tags: tags
    workspaceId: logAnalytics.outputs.id
  }
}

module identities 'modules/identities.bicep' = {
  params: {
    location: location
    tags: tags
    names: identityNames
  }
}

module registry 'modules/container-registry.bicep' = {
  params: {
    location: location
    tags: tags
    suffix: suffix
    pullerIdentityNames: [
      identityNames.aiApi
      identityNames.dataApi
      identityNames.smokeTest
    ]
  }
  dependsOn: [
    identities
  ]
}

module keyVault 'modules/key-vault.bicep' = {
  params: {
    location: location
    tags: tags
    suffix: suffix
    operatorObjectId: operatorObjectId
  }
}

module exchangeStorage 'modules/exchange-storage.bicep' = {
  params: {
    location: location
    tags: tags
    suffix: suffix
    smokeTestIdentityName: identityNames.smokeTest
    dailyRoutineIdentityName: identityNames.dailyRoutine
    digestWatchIdentityName: identityNames.digestWatch
    operatorObjectId: operatorObjectId
  }
  dependsOn: [
    identities
  ]
}

// The environment first, for its identity; then the role, then the storage of the environment.
module jobFilesStorage 'modules/job-files-storage.bicep' = {
  params: {
    location: location
    tags: tags
    suffix: suffix
    environmentName: containerAppsEnvironment.outputs.name
    environmentPrincipalId: containerAppsEnvironment.outputs.principalId
  }
}

module budget 'modules/budget.bicep' = {
  params: {
    contactEmail: budgetContactEmail
    project: tags.project
  }
}

// Second pass. The internal names: https://<app>.internal.<defaultDomain>, in HTTPS, as the clients
// of K-B follow no redirection.
var internalDomain = 'internal.${containerAppsEnvironment.outputs.defaultDomain}'
var dataApiHost = 'ca-kb-data-api.${internalDomain}'
var aiApiHost = 'ca-kb-ai-api.${internalDomain}'
var image = '${registry.outputs.loginServer}/k-b:${imageTag}'
// Variable to Key Vault secret, for each API. KB_DATA_API_KEY_AI_DIGEST is the key of the AI API to
// the data API: read by both.
var dataApiSecretVariables = {
  KB_DATA_API_KEY_AI_DIGEST: 'kb-data-api-key-ai-digest'
}
var aiApiSecretVariables = {
  KB_AI_API_KEY_KB_DIGEST: 'kb-ai-api-key-kb-digest'
  KB_AI_API_KEY_KB_TREND_REPORT: 'kb-ai-api-key-kb-trend-report'
  KB_AI_GITHUB_TOKEN: 'kb-ai-github-token'
  KB_DATA_API_KEY_AI_DIGEST: 'kb-data-api-key-ai-digest'
  KB_LLM_API_KEY: 'kb-llm-api-key'
  KB_OTLP_HEADERS: 'kb-otlp-headers'
}
var secretGrants = concat(
  map(items(dataApiSecretVariables), variable => {
    secret: variable.value
    identity: identityNames.dataApi
  }),
  map(items(aiApiSecretVariables), variable => {
    secret: variable.value
    identity: identityNames.aiApi
  })
)

module secretAccess 'modules/key-vault-secret-access.bicep' = if (deployWorkloads) {
  params: {
    vaultName: keyVault.outputs.name
    grants: secretGrants
  }
  dependsOn: [
    identities
  ]
}

module dataApi 'modules/api-container-app.bicep' = if (deployWorkloads) {
  params: {
    name: 'ca-kb-data-api'
    location: location
    tags: tags
    environmentId: containerAppsEnvironment.outputs.id
    identityName: identityNames.dataApi
    // Its code asks the token of its identity that opens the base (#421).
    identityLifecycle: 'Main'
    registryServer: registry.outputs.loginServer
    image: image
    command: 'serve-data'
    port: dataApiPort
    environmentVariables: {
      KB_DATA_DIR: dataDir
      // The base online (#421), opened by the token of the identity of the API, role kb_reader.
      KB_DATABASE_URL: 'postgresql://${identityNames.dataApi}@${databaseHost}:5432/${databaseName}?${databaseUrlOptions}'
      KB_DATABASE_AUTH: 'entra'
      AZURE_CLIENT_ID: dataApiIdentity.properties.clientId
      KB_DATA_API_HOST: '0.0.0.0'
      KB_DATA_API_PORT: string(dataApiPort)
      // TrustedHost compares the Host received, /health included: the internal name only.
      KB_DATA_API_ALLOWED_HOSTS: dataApiHost
      // Neither /docs nor /openapi.json.
      KB_DEPLOYMENT_ENVIRONMENT: 'production'
    }
    vaultEntries: dataApiSecretVariables
    vaultUri: keyVault.outputs.uri
    probeHost: dataApiHost
  }
  dependsOn: [
    secretAccess
  ]
}

module aiApi 'modules/api-container-app.bicep' = if (deployWorkloads) {
  params: {
    name: 'ca-kb-ai-api'
    location: location
    tags: tags
    environmentId: containerAppsEnvironment.outputs.id
    identityName: identityNames.aiApi
    registryServer: registry.outputs.loginServer
    image: image
    command: 'serve-ai'
    port: aiApiPort
    environmentVariables: {
      KB_DATA_DIR: dataDir
      KB_AI_API_HOST: '0.0.0.0'
      KB_AI_API_PORT: string(aiApiPort)
      // Required with the OTLP export; neither /docs nor /openapi.json.
      KB_DEPLOYMENT_ENVIRONMENT: 'production'
      KB_TRACE_CONTENT: 'none'
      KB_LLM_PROVIDER: 'openai_compatible'
      KB_LLM_BASE_URL: llmBaseUrl
      KB_LLM_MODEL: llmModel
      // Required by gpt-6-luna: without it, each call answers 400 (docs/fiches-veille.md).
      KB_LLM_REASONING_EFFORT: 'none'
      KB_DATA_API_URL: 'https://${dataApiHost}'
      KB_OTLP_ENDPOINT: otlpEndpoint
    }
    vaultEntries: aiApiSecretVariables
    vaultUri: keyVault.outputs.uri
    // The longest request the ingress lets through (240 s), then the last exports of the lifespan
    // (6 s at most), and a margin: a shorter stop would cut the request and lose its measures.
    terminationGracePeriodSeconds: 250
  }
  dependsOn: [
    secretAccess
  ]
}

module smokeTestJob 'modules/smoke-test-job.bicep' = if (deployWorkloads) {
  params: {
    location: location
    tags: tags
    environmentId: containerAppsEnvironment.outputs.id
    identityName: identityNames.smokeTest
    registryServer: registry.outputs.loginServer
    image: image
    environmentVariables: {
      KB_DATA_DIR: dataDir
      KB_EXCHANGE_BLOB_URL: exchangeStorage.outputs.blobEndpoint
      KB_DATA_API_URL: 'https://${dataApiHost}'
      KB_AI_API_URL: 'https://${aiApiHost}'
    }
  }
  dependsOn: [
    identities
  ]
}

// The base online (#421): its name, created by infra/postgresql/create-principals.sql, and the TLS of
// libpq: the token is a bearer secret, it goes only to a server whose certificate is checked against
// the store of the image.
var databaseName = 'kb'
var databaseUrlOptions = 'sslmode=verify-full&sslrootcert=/etc/ssl/certs/ca-certificates.crt'
var migrateDatabaseIdentityName = 'id-kb-migrate-database'

// First pass: the server and the identity of the job, for infra/postgresql/; second pass: the job.
module postgresqlServer 'modules/postgresql-server.bicep' = {
  params: {
    location: location
    tags: tags
    suffix: suffix
    administratorObjectId: operatorObjectId
    administratorPrincipalName: operatorPrincipalName
  }
}

var databaseHost = postgresqlServer.outputs.fullyQualifiedDomainName

module migrateDatabaseJob 'modules/migrate-database-job.bicep' = {
  params: {
    location: location
    tags: tags
    identityName: migrateDatabaseIdentityName
    registryName: registry.outputs.name
    deployJob: deployWorkloads
    environmentId: containerAppsEnvironment.outputs.id
    registryServer: registry.outputs.loginServer
    image: image
    environmentVariables: {
      KB_DATA_DIR: dataDir
      KB_DATABASE_URL: 'postgresql://${migrateDatabaseIdentityName}@${databaseHost}:5432/${databaseName}?${databaseUrlOptions}'
      KB_DATABASE_AUTH: 'entra'
    }
  }
}

resource dataApiIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = {
  name: identityNames.dataApi
}

module deployAccess 'modules/deploy-access.bicep' = if (deployWorkloads) {
  params: {
    deployIdentityName: identityNames.deploy
    registryName: registry.outputs.name
    appNames: deployment.apps
    jobNames: deployment.jobs
    githubSubject: githubDeploySubject
  }
  dependsOn: [
    identities
    dataApi
    aiApi
    smokeTestJob
    migrateDatabaseJob
  ]
}

output registryName string = registry.outputs.name
output registryLoginServer string = registry.outputs.loginServer
output keyVaultName string = keyVault.outputs.name
output postgresqlServerName string = postgresqlServer.outputs.name
output postgresqlServerHost string = databaseHost
// The secret AZURE_CLIENT_ID of the repository (infra/README.md, « Déployer une version »).
output deployIdentityClientId string = deployWorkloads ? deployAccess!.outputs.clientId : ''
