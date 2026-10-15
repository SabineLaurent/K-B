"""One log line per request: method, route template, status, duration and client; never the key,
a value of a parameter nor a raw path (docs/specs-api.md, "Journal")."""

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from k_b.core.quoting import quote_value
from k_b.data_api.health import HEALTH_PATH

logger = logging.getLogger(__name__)

# No route matched, no client named by a valid key, or no response sent.
NONE_SEEN = "-"


async def log_request(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Log the request once its response is known; in a finally, so that a request stopped
    before its response (the client gone, the server stopped) leaves its line, without status."""
    started = time.perf_counter()
    status_code: int | None = None
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        # A probe that answers 200 is not logged: one every few seconds would bury the requests
        # of the clients. A probe that fails keeps its line.
        if not (request.url.path == HEALTH_PATH and status_code == 200):
            logger.info(
                "%s",
                format_request_line(
                    request.method,
                    find_route_template(request),
                    status_code,
                    round((time.perf_counter() - started) * 1000),
                    getattr(request.state, "client_name", NONE_SEEN),
                ),
            )


def find_route_template(request: Request) -> str:
    """The template of the route matched (/items/{item_id}), never the path received.

    FastAPI puts in the scope its own routes only (fastapi/routing.py, 0.143): /docs,
    /openapi.json and /health, without parameter, are named by their path, the one the app gives
    them.
    """
    route = request.scope.get("route")
    if route is not None:
        return str(route.path)
    if request.url.path in {request.app.docs_url, request.app.openapi_url, HEALTH_PATH}:
        return request.url.path
    return NONE_SEEN


def format_request_line(
    method: str,
    route: str,
    status_code: int | None,
    duration_ms: int,
    client_name: str,
) -> str:
    # The method is the one value received: quoted, it cannot write a line of its own.
    status = NONE_SEEN if status_code is None else status_code
    return (
        f"request method={quote_value(method)} route={route} status={status}"
        f" duration_ms={duration_ms} client={client_name}"
    )
