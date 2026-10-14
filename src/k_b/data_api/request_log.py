"""One log line per request: method, route template, status, duration and client; never the key,
a value of a parameter nor a raw path (docs/specs-api.md, "Journal")."""

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from k_b.core.quoting import quote_value

logger = logging.getLogger(__name__)

# No route matched, or no client named by a valid key.
NONE_SEEN = "-"


async def log_request(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Log the request once its response is known; in a finally, so that an exception the API
    does not handle leaves its line, with the 500 Starlette answers."""
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        # The router puts the route it matched in the scope; its path is the template
        # (/items/{item_id}), not the path received.
        route = request.scope.get("route")
        logger.info(
            "%s",
            format_request_line(
                request.method,
                getattr(route, "path", NONE_SEEN),
                status_code,
                round((time.perf_counter() - started) * 1000),
                getattr(request.state, "client_name", NONE_SEEN),
            ),
        )


def format_request_line(
    method: str, route: str, status_code: int, duration_ms: int, client_name: str
) -> str:
    # The method is the one value received: quoted, it cannot write a line of its own.
    return (
        f"request method={quote_value(method)} route={route} status={status_code}"
        f" duration_ms={duration_ms} client={client_name}"
    )
