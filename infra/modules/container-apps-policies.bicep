// Two built-in definitions of Azure Policy assigned to the resource group, to audit the configuration of the
// container apps online between two reviews (#497, OWASP API8:2023, "Repeatable hardening and periodic review").
// Built-in definitions only: Sabine is Owner of the resource group, not of the subscription, where a custom
// definition would be created. No parameter: the default effect of both is Audit (versions 1.1.0 and 1.0.1, read
// in Azure/azure-policy on 2026-11-18), which flags and refuses nothing; no identity, which only deployIfNotExists
// and modify need. They also audit the apps of the other projects of the group.
param webAppName string

resource externalIngress 'Microsoft.Authorization/policyAssignments@2026-07-01' = {
  name: 'audit-kb-ca-external-ingress'
  properties: {
    displayName: 'Container Apps should disable external network access'
    description: 'K-B (#497): an app whose ingress is external is non-compliant.'
    policyDefinitionId: tenantResourceId(
      'Microsoft.Authorization/policyDefinitions',
      '783ea2a8-b8fd-46be-896a-9ae79643a0b1'
    )
    // The site is open on purpose, behind the sign-in of Microsoft Entra (#571).
    notScopes: [
      resourceId('Microsoft.App/containerApps', webAppName)
    ]
  }
}

resource httpsOnly 'Microsoft.Authorization/policyAssignments@2026-07-01' = {
  name: 'audit-kb-ca-https-only'
  properties: {
    displayName: 'Container Apps should only be accessible over HTTPS'
    description: 'K-B (#497): an app whose ingress allows HTTP is non-compliant.'
    policyDefinitionId: tenantResourceId(
      'Microsoft.Authorization/policyDefinitions',
      '0e80e269-43a4-4ae9-b5bc-178126b8a5cb'
    )
  }
}
