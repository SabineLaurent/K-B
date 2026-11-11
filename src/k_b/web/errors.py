"""The errors of the site, each an HTML page: 403, 404, 500 and the others, never with the text of
an exception nor a value received (docs/site-web.md, "Erreurs")."""

from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime

from fastapi import Request, Response
from fastapi.responses import HTMLResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from k_b.core.api_errors import ErrorHandlers, log_unexpected_error
from k_b.core.api_request_log import read_request_id
from k_b.web.french_dates import write_moment
from k_b.web.rendering import render_page

ERROR_TEMPLATES = {403: "403.html", 404: "404.html", 500: "500.html"}
# Any other status: a page that gives its code.
OTHER_ERROR_TEMPLATE = "error.html"
# The page 500 when its template fails too, written without template.
FALLBACK_SERVER_ERROR_PAGE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Erreur du serveur · K-B</title>
</head>
<body>
<main>
<p>Erreur 500</p>
<h1>Erreur du serveur</h1>
<p><a href="/">Retour au fil de veille</a></p>
</main>
</body>
</html>
"""


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
            "occurred_at_text": write_moment(occurred_at),
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
    return render_server_error_page(request)


def render_server_error_page(request: Request) -> Response:
    """The page 500, or the page written without template if its template fails too: an
    exception out of here would reach Starlette, which answers in text, and uvicorn, which logs
    its stack."""
    try:
        return render_error_page(request, 500)
    except Exception as error:  # noqa: BLE001 — any failure of the template of the page 500
        log_unexpected_error(request, error)
        return HTMLResponse(FALLBACK_SERVER_ERROR_PAGE, status_code=500)


ERROR_HANDLERS: ErrorHandlers = {StarletteHTTPException: handle_http_error}
