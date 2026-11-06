"""GET /health of an API of K-B from a job: its answer read within its bounds, then checked by a
closed schema; no retry, the job fails."""

import time
from collections.abc import Callable
from typing import Literal

import httpx2
from pydantic import BaseModel, ConfigDict, ValidationError

from k_b.core.api_health import HEALTH_PATH
from k_b.core.config import (
    HEALTH_CONNECT_TIMEOUT_SECONDS,
    HEALTH_POOL_TIMEOUT_SECONDS,
    HEALTH_READ_TIMEOUT_SECONDS,
    HEALTH_REQUEST_DEADLINE_SECONDS,
    HEALTH_WRITE_TIMEOUT_SECONDS,
    MAX_HEALTH_ANSWER_BYTES,
)
from k_b.core.outbound import (
    BodyTooLargeError,
    BodyTooLateError,
    open_http_client,
    read_bounded_body,
)

HEALTHY_STATUS = 200

type HealthState = Literal[
    "health_unavailable",
    "health_timeout",
    "health_failed",
    "health_invalid_response",
]


class HealthCheckError(Exception):
    """A health check that failed: its state and the HTTP status, never the URL nor the body."""

    def __init__(self, state: HealthState, http_status: int | None = None) -> None:
        """Name the failure by its state, and its HTTP status when the API answered."""
        status = () if http_status is None else (f"HTTP {http_status}",)
        super().__init__(", ".join((state, *status)))
        self.state: HealthState = state
        self.http_status = http_status


class HealthAnswer(BaseModel):
    """The answer of GET /health of both APIs (core/api_health.py), and nothing else."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    status: Literal["ok"]


def build_health_client(
    base_url: str, transport: httpx2.BaseTransport | None = None
) -> httpx2.Client:
    """A client of the API at base_url, without a key: /health is served without one."""
    return open_http_client(
        base_url,
        {},
        httpx2.Timeout(
            connect=HEALTH_CONNECT_TIMEOUT_SECONDS,
            read=HEALTH_READ_TIMEOUT_SECONDS,
            write=HEALTH_WRITE_TIMEOUT_SECONDS,
            pool=HEALTH_POOL_TIMEOUT_SECONDS,
        ),
        transport,
    )


def check_health(
    http_client: httpx2.Client, clock: Callable[[], float] = time.monotonic
) -> None:
    """GET /health, refused by HealthCheckError unless the API answers 200 and {"status": "ok"}."""
    deadline = clock() + HEALTH_REQUEST_DEADLINE_SECONDS
    try:
        with http_client.stream("GET", HEALTH_PATH) as response:
            if response.status_code != HEALTHY_STATUS:
                raise HealthCheckError("health_failed", response.status_code)
            body = read_bounded_body(
                response, MAX_HEALTH_ANSWER_BYTES, lambda: clock() > deadline
            )
    except (httpx2.TimeoutException, BodyTooLateError):
        raise HealthCheckError("health_timeout") from None
    except httpx2.TransportError:
        raise HealthCheckError("health_unavailable") from None
    except (BodyTooLargeError, httpx2.RequestError):
        # Beyond its bound, or a body that cannot be read (badly encoded).
        raise HealthCheckError("health_invalid_response") from None
    try:
        HealthAnswer.model_validate_json(body)
    except ValidationError:
        raise HealthCheckError("health_invalid_response") from None
