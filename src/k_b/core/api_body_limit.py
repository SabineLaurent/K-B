"""The bound of a request body (OWASP API4:2023): Starlette counts the bytes received, and K-B
first refuses a body announced beyond the bound, in the error schema of the APIs."""

from fastapi import FastAPI
from starlette.datastructures import Headers
from starlette.middleware.body_limit import RequestBodyLimitMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from k_b.core.api_errors import CONTENT_TOO_LARGE, respond_with_error


def bound_request_bodies(app: FastAPI, max_bytes: int) -> None:
    """A body beyond max_bytes gets 413 content_too_large before any route reads it. FastAPI
    0.143 does not pass the max_body_size of Starlette: both are added as middlewares."""
    # The last added is the outermost: the Content-Length is checked before Starlette counts.
    app.add_middleware(RequestBodyLimitMiddleware, max_body_size=max_bytes)
    app.add_middleware(RefuseBodyAnnouncedTooLarge, max_bytes=max_bytes)


class RefuseBodyAnnouncedTooLarge:
    """A request whose Content-Length is beyond max_bytes gets 413 before any reading: on such a
    request, RequestBodyLimitMiddleware replaces any answer by a 413 in plain text (Starlette 1.8,
    send_with_limit)."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and is_announced_beyond(scope, self.max_bytes):
            await respond_with_error(413, CONTENT_TOO_LARGE)(scope, receive, send)
            return
        await self.app(scope, receive, send)


def is_announced_beyond(scope: Scope, max_bytes: int) -> bool:
    """True when the Content-Length of the request, read by int() as Starlette reads it, is beyond
    max_bytes; a value int() refuses is left to the count of Starlette."""
    length = Headers(scope=scope).get("content-length")
    if length is None:
        return False
    try:
        return int(length) > max_bytes
    except ValueError:
        return False
