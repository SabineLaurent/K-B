// K-B on Azure. Applied by hand by Sabine to her resource group (infra/README.md), checked by the CI.
targetScope = 'resourceGroup'

@description('Region of every K-B resource: the resource group\'s by default (France Central).')
param location string = resourceGroup().location

@description('Address of the budget alerts: given at deployment, never written in the repository.')
param budgetContactEmail string

var tags = {
  project: 'k-b'
}

module containerAppsEnvironment 'modules/container-apps-environment.bicep' = {
  params: {
    location: location
    tags: tags
  }
}

module budget 'modules/budget.bicep' = {
  params: {
    contactEmail: budgetContactEmail
    project: tags.project
  }
}
