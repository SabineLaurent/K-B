// The manual job caj-kb-smoke-test: kb smoke-test (#412) asks GET /health of both APIs by their
// internal name, then lists the container smoke-test by the identity of the job.
// TRIAL OF #420, removed by the next commit: the job runs the probe of #420 instead, under
// id-kb-daily-routine, with the share job-data mounted. An execution can replace neither the identities
// nor the volumes, and its override replaces the whole template: the probe lives in the template.
param location string
param tags object
param environmentId string
param identityName string
param registryServer string
param image string
@description('Variables of the container, by name, AZURE_CLIENT_ID apart.')
param environmentVariables object
@description('Trial of #420: the identity the probe acts under.')
param probeIdentityName string
@description('Trial of #420: the storage of the environment that holds the share job-data.')
param jobDataStorageName string

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = {
  name: identityName
}

resource probeIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = {
  name: probeIdentityName
}

var plainVariables = [
  for variable in items(environmentVariables): {
    name: variable.key
    value: variable.value
  }
]
// The probe asks the token of id-kb-daily-routine; the registry is still pulled by id-kb-smoke-test.
var clientIdVariable = {
  name: 'AZURE_CLIENT_ID'
  value: probeIdentity.properties.clientId
}
// The data directory of the image (Dockerfile), owned by 10001:10001, files in 0600.
var dataDir = '/var/lib/knowledge_base'
// Checks the mount and the atomic write as the user of the image, then the lock of direction: clippings
// refuses id-kb-daily-routine, watch accepts it. Hidden names without .md: the mirror of the clips and
// make download-watch-sheets leave them; each object is removed by the probe that wrote it.
var probe = '''
import os
import stat
import sys
from pathlib import Path

from azure.core.exceptions import HttpResponseError
from azure.identity import ManagedIdentityCredential
from azure.storage.blob import BlobServiceClient

from k_b.core.atomic_write import write_file_atomically

failures = []
root = Path("/var/lib/knowledge_base")
name = ".probe-420"


def describe(path):
    status = path.stat()
    return f"uid={status.st_uid} gid={status.st_gid} mode={oct(stat.S_IMODE(status.st_mode))}"


print("probe 420: process uid", os.getuid(), "gid", os.getgid())
if not os.path.ismount(root):
    failures.append("job-data is not mounted")
else:
    print("probe 420: mount", describe(root))
    probe = root / name
    try:
        write_file_atomically(probe, b"first")
        write_file_atomically(probe, b"second")
        print("probe 420: file", describe(probe))
        if probe.read_bytes() != b"second":
            failures.append("the second write did not replace the first")
    except OSError as error:
        failures.append(f"write_file_atomically: {error!r}")
    finally:
        probe.unlink(missing_ok=True)

service = BlobServiceClient(
    os.environ["KB_EXCHANGE_BLOB_URL"],
    credential=ManagedIdentityCredential(client_id=os.environ["AZURE_CLIENT_ID"]),
)
try:
    service.get_blob_client("clippings", name).upload_blob(b"probe", overwrite=True)
    failures.append("clippings accepted a write")
except HttpResponseError as error:
    print("probe 420: clippings", error.status_code, error.error_code)
    if error.status_code != 403:
        failures.append(f"clippings answered {error.status_code}, not 403")
try:
    blob = service.get_blob_client("watch", name)
    blob.upload_blob(b"probe", overwrite=True)
    blob.delete_blob()
    print("probe 420: watch written, then deleted")
except HttpResponseError as error:
    failures.append(f"watch answered {error.status_code} {error.error_code}")

print("probe 420:", ("failed: " + "; ".join(failures)) if failures else "passed")
sys.exit(1 if failures else 0)
'''

resource job 'Microsoft.App/jobs@2026-01-01' = {
  name: 'caj-kb-smoke-test'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
      '${probeIdentity.id}': {}
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
      // The bounds of the job must fall before this one, or the replica is killed before its summary:
      // the two /health of 65 s at most each, then the retries of the storage SDK, about 7 min
      // (core/config.py), about 576 s with the start of the job; the retries of azure-identity are not
      // counted there. 900 s leaves them a margin, and costs only when the job is stuck.
      replicaTimeout: 900
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
          // Replaces the entrypoint kb of the image.
          command: [
            'python'
          ]
          args: [
            '-c'
            probe
          ]
          env: concat(plainVariables, [
            clientIdVariable
          ])
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          volumeMounts: [
            {
              volumeName: 'job-data'
              mountPath: dataDir
            }
          ]
        }
      ]
      volumes: [
        {
          name: 'job-data'
          storageType: 'AzureFile'
          storageName: jobDataStorageName
          // The user of the image (#200): without them, the share is mounted as root.
          mountOptions: 'uid=10001,gid=10001,dir_mode=0700,file_mode=0600'
        }
      ]
    }
  }
}
