"""Requests without a key to an API of K-B from a job, each with the status it expects: the version
deployed refuses what it must refuse (OWASP API8:2023). The body of an answer is never read."""

from typing import Literal, NamedTuple

import httpx2

from k_b.core.api_health import HEALTH_PATH
from k_b.core.config import (
    PROBE_CONNECT_TIMEOUT_SECONDS,
    PROBE_POOL_TIMEOUT_SECONDS,
    PROBE_READ_TIMEOUT_SECONDS,
    PROBE_WRITE_TIMEOUT_SECONDS,
)
from k_b.core.outbound import open_http_client

# FastAPI's path of Swagger UI, served by both APIs in the sandbox only (read_openapi_url).
DOCS_PATH = "/docs"
DOCS_SERVED_STATUS = 200
DOCS_NOT_SERVED_STATUS = 404
# A route that needs a key, called without one (core/api_access.py).
WITHOUT_KEY_STATUS = 401
# HEAD on /health, which answers GET only (core/api_methods.py, remove_implicit_head).
METHOD_NOT_ALLOWED_STATUS = 405

type Route = tuple[str, str]

# A route of each API that needs a key: its method and its path. tests/ai_api and tests/data_api
# send each probe to the apps themselves.
DATA_API_ROUTE_WITH_KEY: Route = ("GET", "/items")
AI_API_ROUTE_WITH_KEY: Route = ("POST", "/digests")

type ProbeState = Literal[
    "probe_unexpected_status",
    "probe_timeout",
    "probe_unavailable",
]


class Probe(NamedTuple):
    """A request without a key, and the status it expects."""

    method: str
    path: str
    expected_status: int


class ProbeError(Exception):
    """A probe that failed: its state and the HTTP status received, never the URL nor the body."""

    def __init__(self, state: ProbeState, http_status: int | None = None) -> None:
        """Name the failure by its state, and the HTTP status when the API answered."""
        status = () if http_status is None else (f"HTTP {http_status}",)
        super().__init__(", ".join((state, *status)))
        self.state: ProbeState = state
        self.http_status = http_status


def build_probe_client(
    base_url: str, transport: httpx2.BaseTransport | None = None
) -> httpx2.Client:
    """A client of the API at base_url, without a key, whose waits are those of an API awake."""
    return open_http_client(
        base_url,
        {},
        httpx2.Timeout(
            connect=PROBE_CONNECT_TIMEOUT_SECONDS,
            read=PROBE_READ_TIMEOUT_SECONDS,
            write=PROBE_WRITE_TIMEOUT_SECONDS,
            pool=PROBE_POOL_TIMEOUT_SECONDS,
        ),
        transport,
    )


def list_probes(route_with_key: Route, is_sandbox: bool) -> tuple[Probe, ...]:
    """The probes of an API: a route of it without its key, /docs, served in the sandbox only, and
    HEAD on /health."""
    method, path = route_with_key
    docs_status = DOCS_SERVED_STATUS if is_sandbox else DOCS_NOT_SERVED_STATUS
    return (
        Probe(method, path, WITHOUT_KEY_STATUS),
        Probe("GET", DOCS_PATH, docs_status),
        Probe("HEAD", HEALTH_PATH, METHOD_NOT_ALLOWED_STATUS),
    )


def send_probe(http_client: httpx2.Client, probe: Probe) -> None:
    """Send the probe, refused by ProbeError unless the API answers its expected status; the
    answer is closed unread."""
    try:
        with http_client.stream(probe.method, probe.path) as response:
            status = response.status_code
    except httpx2.TimeoutException:
        raise ProbeError("probe_timeout") from None
    except httpx2.TransportError:
        raise ProbeError("probe_unavailable") from None
    if status != probe.expected_status:
        raise ProbeError("probe_unexpected_status", status)
