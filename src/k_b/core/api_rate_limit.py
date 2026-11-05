"""How often a client may call a route of an API (OWASP API4:2023): a sliding window per client
and per route, in memory, that a restart empties (docs/specs-api.md, "Débit")."""

import math
import time
from collections import deque
from collections.abc import Callable, Mapping

from fastapi import Request

from k_b.core.api_errors import RATE_LIMIT_EXCEEDED, ApiError
from k_b.core.api_request_log import find_route_template
from k_b.core.config import RateLimit


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

    def find_wait_seconds(self, client_name: str, route: str) -> int | None:
        """Count a call and return None, or the seconds until the oldest call leaves the window,
        without counting it; a route without a limit raises KeyError, a 500 that fails closed."""
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
    wait_seconds = request.app.state.rate_limiter.find_wait_seconds(
        request.state.client_name, find_route_template(request)
    )
    if wait_seconds is not None:
        raise ApiError(429, RATE_LIMIT_EXCEEDED, {"Retry-After": str(wait_seconds)})
