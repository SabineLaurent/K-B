"""The headers of every answer of the site: its security, and how long the browser keeps it
(docs/site-web.md, "En-têtes")."""

from collections.abc import Awaitable, Callable

from fastapi import Request, Response

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


def choose_cache_control(path: str, status_code: int) -> str:
    """no-cache for a file of /static, checked again by its ETag at each page; no-store for any
    other answer, a page included: kept by no browser, even for its button Back."""
    if status_code < 400 and path.startswith(f"{STATIC_PATH}/"):
        return "no-cache"
    return "no-store"


async def add_response_headers(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    # The path the router follows, decoded: request.url.path stops at a ? or a # it holds.
    response.headers["Cache-Control"] = choose_cache_control(
        request.scope["path"], response.status_code
    )
    return response
