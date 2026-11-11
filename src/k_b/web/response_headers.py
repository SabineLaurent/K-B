"""The headers of every answer of the site: its security, and how long the browser keeps it
(docs/site-web.md, "En-têtes")."""

from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from k_b.core.api_health import HEALTH_PATH
from k_b.core.config import WEB_PAGE_MAX_AGE_SECONDS

STATIC_PATH = "/static"
# No script, no style in a tag, nothing from another site; the forms send to the site only.
CONTENT_SECURITY_POLICY = (
    "default-src 'none'; style-src 'self'; img-src 'self'; form-action 'self';"
    " base-uri 'none'; frame-ancestors 'none'"
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    # Ignored by a browser over http, on the machine.
    "Strict-Transport-Security": "max-age=31536000",
    "X-Content-Type-Options": "nosniff",
    # The address of a page of the site never leaves with a link to arxiv.org or GitHub.
    "Referrer-Policy": "no-referrer",
}
PAGE_CACHE_CONTROL = f"private, max-age={WEB_PAGE_MAX_AGE_SECONDS}"


def choose_cache_control(path: str, status_code: int) -> str:
    """no-store for an error and for /health, answers of the moment; no-cache for the files of
    /static, checked again by their ETag at each page; a page, kept by the browser of the
    operator only, never by a cache on the way (private)."""
    if status_code >= 400 or path == HEALTH_PATH:
        return "no-store"
    if path.startswith(f"{STATIC_PATH}/"):
        return "no-cache"
    return PAGE_CACHE_CONTROL


async def add_response_headers(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    response.headers["Cache-Control"] = choose_cache_control(
        request.url.path, response.status_code
    )
    return response
