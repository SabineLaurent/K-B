// The user-assigned managed identities of K-B: one per piece, named id- and the name of the piece
// (names decided on 06/11). Their roles are given by the module of each resource they reach.
param location string
param tags object
param names object

resource identities 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = [
  for name in items(names): {
    name: name.value
    location: location
    tags: tags
  }
]
