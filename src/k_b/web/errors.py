"""The errors of the site, each an HTML page: 403, 404, 500 and the others, never with the text of
an exception nor a value received (docs/site-web.md, "Erreurs")."""

from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime

from fastapi import Request, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from k_b.core.api_errors import ErrorHandlers, log_unexpected_error
from k_b.core.api_request_log import read_request_id
from k_b.web.rendering import render_page

ERROR_TEMPLATES = {403: "403.html", 404: "404.html", 500: "500.html"}
# Any other status: a page that gives its code.
OTHER_ERROR_TEMPLATE = "error.html"


def render_error_page(
    request: Request, status_code: int, headers: Mapping[str, str] | None = None
) -> Response:
    """The page of an error, with the time in UTC and the id of the request the page 500 gives."""
    occurred_at = datetime.now(UTC).replace(microsecond=0)
    return render_page(
        request,
        ERROR_TEMPLATES.get(status_code, OTHER_ERROR_TEMPLATE),
        {
            "status_code": status_code,
            "request_id": read_request_id(request),
            "occurred_at": occurred_at.isoformat().replace("+00:00", "Z"),
            "occurred_at_text": f"{occurred_at:%d/%m/%Y à %H:%M} UTC",
        },
        status_code=status_code,
        headers=headers,
    )


async def handle_http_error(
    request: Request, error: StarletteHTTPException
) -> Response:
    """The errors Starlette raises as it routes a request, a 404 or a 405, each by its page."""
    return render_error_page(request, error.status_code, error.headers)


async def respond_to_unexpected_error(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """An exception no handler takes: the page 500, its type logged once, never its message nor
    its stack, which may quote a value received.

    A middleware, as in core/api_errors.py: Starlette raises again after a handler of Exception."""
    try:
        return await call_next(request)
    except Exception as error:  # noqa: BLE001 — every exception no handler takes
        log_unexpected_error(request, error)
        return render_error_page(request, 500)


ERROR_HANDLERS: ErrorHandlers = {StarletteHTTPException: handle_http_error}
