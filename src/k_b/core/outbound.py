"""The rules of a connection K-B opens by HTTP (the collection to its sources, AI API to the model,
to the data API and to GitHub, kb digest to the AI API): the URL it accepts, its HTTP client and
the bound of a body read, in one place since all are security rules."""

import re
from collections.abc import Callable, Mapping
from urllib.parse import urlsplit

import httpx2

# A host name in lowercase, as urlsplit gives it: neither an IPv6 address nor a character an HTTP
# client would refuse later.
HOST_NAME = re.compile(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?")


def find_url_refusal(variable: str, url: str, schemes: tuple[str, ...]) -> str | None:
    """Why the URL of the variable is refused, or None. The URL is never quoted: it may carry a
    key (`https://user:key@host`, `?api-key=…`)."""
    try:
        parts = urlsplit(url)
        has_user_information = parts.username is not None or parts.password is not None
        # Read for its check: a port out of 0 to 65535, or not digits, raises.
        parts.port  # noqa: B018
    except ValueError:
        return f"{variable}: not a URL"
    if parts.scheme not in schemes:
        return f"{variable}: scheme not {' nor '.join(schemes)}"
    if not parts.hostname:
        return f"{variable}: no host"
    if not HOST_NAME.fullmatch(parts.hostname):
        return f"{variable}: host not a lowercase host name"
    if has_user_information:
        return f"{variable}: with user information"
    if parts.query or parts.fragment or "?" in url or "#" in url:
        return f"{variable}: with a query or a fragment"
    return None


def open_http_client(
    base_url: str,
    headers: Mapping[str, str],
    timeout: httpx2.Timeout,
    transport: httpx2.BaseTransport | None,
) -> httpx2.Client:
    """A client that reads neither a proxy nor a certificate of the environment, and follows no
    redirection."""
    return httpx2.Client(
        base_url=base_url,
        headers=headers,
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
        transport=transport,
    )


class BodyTooLargeError(Exception):
    """A body beyond its maximum, refused without reading the rest."""


class BodyTooLateError(Exception):
    """A body still being read when its deadline passed."""


def read_bounded_body(
    response: httpx2.Response,
    max_bytes: int,
    is_late: Callable[[], bool] | None = None,
) -> bytes:
    """The body of a streamed response, refused beyond max_bytes, stopped as soon as is_late()
    between two pieces. Decoded bytes: a compressed body is bounded by what it takes once read,
    at a peak of max_bytes + 1 MiB (httpx2 decodes by pieces of 1 MiB at most)."""
    length = response.headers.get("Content-Length")
    if (
        length is not None
        and length.isascii()
        and length.isdigit()
        and int(length) > max_bytes
    ):
        raise BodyTooLargeError
    body, is_cut = read_pieces(response, max_bytes, is_late)
    if is_cut:
        raise BodyTooLargeError
    return body


def read_body_head(
    response: httpx2.Response,
    max_bytes: int,
    is_late: Callable[[], bool] | None = None,
) -> bytes:
    """The first max_bytes of the body of a streamed response, decoded, the rest left unread and
    its Content-Length ignored; stopped as soon as is_late() between two pieces."""
    body, _ = read_pieces(response, max_bytes, is_late)
    return body


def read_pieces(
    response: httpx2.Response, max_bytes: int, is_late: Callable[[], bool] | None
) -> tuple[bytes, bool]:
    """The body up to max_bytes, and whether a byte beyond was seen: the one loop of both
    readings, so that a bound of the wait is written once."""
    body = bytearray()
    for chunk in response.iter_bytes():
        body += chunk
        if len(body) > max_bytes:
            return bytes(body[:max_bytes]), True
        if is_late is not None and is_late():
            raise BodyTooLateError
    return bytes(body), False
