// The monthly budget of K-B: e-mail alerts only, nothing is stopped when it is exceeded.
param contactEmail string
param project string

resource budget 'Microsoft.Consumption/budgets@2024-08-01' = {
  name: 'budget-kb'
  properties: {
    category: 'Cost'
    // In the billing currency (EUR), for all of K-B, hosting and inference (thresholds of Sabine of
    // 2026-11-18): the resource of the model counts only in this resource group, tagged project=k-b.
    amount: 40
    timeGrain: 'Monthly'
    // The first of a month; no end date, so Azure sets 10 years.
    timePeriod: {
      startDate: '2026-11-01'
    }
    // The resource group holds other projects: count only the costs tagged with this one.
    filter: {
      tags: {
        name: 'project'
        operator: 'In'
        values: [
          project
        ]
      }
    }
    notifications: {
      actual50: {
        enabled: true
        thresholdType: 'Actual'
        operator: 'GreaterThanOrEqualTo'
        threshold: 50
        contactEmails: [
          contactEmail
        ]
        locale: 'fr-fr'
      }
      actual100: {
        enabled: true
        thresholdType: 'Actual'
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        contactEmails: [
          contactEmail
        ]
        locale: 'fr-fr'
      }
      forecasted100: {
        enabled: true
        thresholdType: 'Forecasted'
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        contactEmails: [
          contactEmail
        ]
        locale: 'fr-fr'
      }
    }
  }
}
