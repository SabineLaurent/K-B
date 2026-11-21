"""The client of the probes without key of a job: the API answered its /health just before, so a
probe waits less than the wake of an API."""

from k_b.core.config import (
    HEALTH_READ_TIMEOUT_SECONDS,
    PROBE_CONNECT_TIMEOUT_SECONDS,
    PROBE_READ_TIMEOUT_SECONDS,
)
from k_b.jobs.api_probes import build_probe_client

TEST_API_URL = (
    "https://ca-kb-data-api.internal.example.francecentral.azurecontainerapps.io"
)


def test_a_probe_waits_a_read_shorter_than_the_wake_of_an_api():
    with build_probe_client(TEST_API_URL) as http_client:
        timeout = http_client.timeout

    assert timeout.connect == PROBE_CONNECT_TIMEOUT_SECONDS
    assert timeout.read == PROBE_READ_TIMEOUT_SECONDS
    assert PROBE_READ_TIMEOUT_SECONDS < HEALTH_READ_TIMEOUT_SECONDS
    assert "authorization" not in http_client.headers
