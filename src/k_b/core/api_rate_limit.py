"""How often a client may call a route of an API (OWASP API4:2023): a sliding window per client
and per route, in memory, that a restart empties (docs/specs-api.md, "Débit"); and the one request
at a time of a route that calls the model (docs/fiches-veille.md, "Accès")."""

import math
import time
from collections import deque
from collections.abc import AsyncIterator, Callable, Mapping

from fastapi import Request

from k_b.core.api_errors import RATE_LIMIT_EXCEEDED, REQUEST_ALREADY_RUNNING, ApiError
from k_b.core.api_request_log import find_route_template
from k_b.core.config import RUNNING_REQUEST_RETRY_AFTER_SECONDS, RateLimit


class RateLimiter:
    """The recent calls of each client to each route: at most the requests of its limit, for the
    clients a valid key names, so its size is bounded.

    Called from the event loop only, by check_rate_limit: no lock."""

    def __init__(
        self,
        limit_by_route: Mapping[str, RateLimit],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit_by_route = limit_by_route
        self.clock = clock
        self.calls: dict[tuple[str, str], deque[float]] = {}

    def admit_call(self, client_name: str, route: str) -> int | None:
        """Admit the call, counted, and return None; or refuse it, not counted, and return the
        seconds until the oldest call leaves the window. A route without a limit raises KeyError,
        a 500 that fails closed."""
        limit = self.limit_by_route[route]
        calls = self.calls.setdefault((client_name, route), deque())
        now = self.clock()
        while calls and now - calls[0] >= limit.window_seconds:
            calls.popleft()
        if len(calls) >= limit.requests:
            return math.ceil(limit.window_seconds - (now - calls[0]))
        calls.append(now)
        return None


async def check_rate_limit(request: Request) -> None:
    """Refuse a client beyond the limit of the route with a 429 that says how long to wait; after
    check_api_key, so that a request without a valid key counts for nothing."""
    wait_seconds = request.app.state.rate_limiter.admit_call(
        request.state.client_name, find_route_template(request)
    )
    if wait_seconds is not None:
        raise ApiError(429, RATE_LIMIT_EXCEEDED, {"Retry-After": str(wait_seconds)})


async def hold_route_slot(request: Request) -> AsyncIterator[None]:
    """One request at a time on a route, the next one refused with a 429 and no queue: waiting
    would only delay it. Held until the response is sent, or until the route ends when its client
    has gone: a route stops spending at its own deadline, not with its client."""
    slot = request.app.state.slot_by_route[find_route_template(request)]
    if not slot.acquire(blocking=False):
        raise ApiError(
            429,
            REQUEST_ALREADY_RUNNING,
            {"Retry-After": str(RUNNING_REQUEST_RETRY_AFTER_SECONDS)},
        )
    try:
        yield
    finally:
        slot.release()
