// An e-mail when the model resource spends more tokens than K-B does on its busiest days (#501, OWASP API4:2023,
// "billing alerts should be configured instead"): it warns, and stops nothing. On the whole resource, not on the
// deployment of K-B: a key of the resource gives access to all its deployments.
param modelAccountName string
param contactEmail string
param threshold int
param tags object

// Its name says who receives it: the next alerts of K-B can use the same group.
resource operatorGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'ag-kb-operator'
  location: 'global'
  tags: tags
  properties: {
    enabled: true
    // 12 characters at most, shown in the mails of the group.
    groupShortName: 'kb-operator'
    emailReceivers: [
      {
        // The address receives a one-time code, to enter within 30 minutes (infra/README.md).
        name: 'operator'
        emailAddress: contactEmail
        useCommonAlertSchema: true
      }
    ]
  }
}

resource tokenAlert 'Microsoft.Insights/metricAlerts@2026-01-01' = {
  name: 'alert-kb-model-tokens'
  location: 'global'
  tags: tags
  properties: {
    description: 'K-B (#501): the model resource spent more tokens in 24 hours than the threshold.'
    severity: 2
    enabled: true
    scopes: [
      resourceId('Microsoft.CognitiveServices/accounts', modelAccountName)
    ]
    // A sliding window of 24 hours, checked every 15 minutes.
    windowSize: 'P1D'
    evaluationFrequency: 'PT15M'
    autoMitigate: true
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          criterionType: 'StaticThresholdCriterion'
          name: 'total-tokens'
          metricNamespace: 'Microsoft.CognitiveServices/accounts'
          // Prompt and completion together, for every deployment: no dimension filter.
          metricName: 'TotalTokens'
          timeAggregation: 'Total'
          operator: 'GreaterThan'
          threshold: threshold
        }
      ]
    }
    actions: [
      {
        actionGroupId: operatorGroup.id
      }
    ]
  }
}
