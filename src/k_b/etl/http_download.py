"""Download one URL for a source: the network boundary every collection goes through."""

import logging
from time import sleep
from urllib.parse import urljoin, urlsplit

import httpx2

from k_b.core.config import HTTP_MAX_REDIRECTS, HTTP_TIMEOUT_SECONDS
from k_b.core.outbound import BodyTooLargeError, open_http_client, read_bounded_body
from k_b.core.quoting import quote_value
from k_b.core.user_agent import USER_AGENT
from k_b.etl.http_retry import (
    RETRY_WAIT_SECONDS,
    find_retry_wait,
    note_rate_limit_reset,
)
from k_b.etl.source_contract import PageRefusedError, SourceStatusError

logger = logging.getLogger(__name__)


class RedirectedOutsideError(PageRefusedError):
    """A redirection out of the trusted prefix, refused before it is requested; redirect_url is
    its target resolved against the requested url (tldr.tech redirects a day without an
    edition)."""

    def __init__(self, trusted_url_prefix: str, redirect_url: str):
        super().__init__(
            f"response redirected to {without_query(redirect_url)}, outside "
            f"{trusted_url_prefix}, refused"
        )
        self.redirect_url = redirect_url


def download(
    url: str,
    trusted_url_prefix: str,
    max_bytes: int,
    headers: dict[str, str] | None = None,
    unredirected_headers: dict[str, str] | None = None,
    rate_limited_wait_seconds: float = RETRY_WAIT_SECONDS,
) -> bytes:
    """Return the body of GET url, refused if too large or redirected out of trusted_url_prefix;
    one retry after a 429, a 5xx or a failed connection (etl/http_retry.py), after
    rate_limited_wait_seconds for a 429 without Retry-After.

    An unredirected header (a token) goes with the first request only; a SourceStatusError not
    retried is left to the caller, who alone knows what a status such as 304 means."""
    check_trusted_url_prefix(url, trusted_url_prefix)
    try:
        return download_once(
            url, trusted_url_prefix, max_bytes, headers, unredirected_headers
        )
    except (httpx2.TransportError, SourceStatusError) as error:
        wait = find_retry_wait(error, rate_limited_wait_seconds)
        if wait is None:
            raise
        logger.warning(
            "GET %s failed: %s; one retry in %s s",
            quote_value(without_query(url)),
            quote_value(str(error)),
            wait,
        )
        sleep(wait)
    return download_once(
        url, trusted_url_prefix, max_bytes, headers, unredirected_headers
    )


def download_once(
    url: str,
    trusted_url_prefix: str,
    max_bytes: int,
    headers: dict[str, str] | None,
    unredirected_headers: dict[str, str] | None,
) -> bytes:
    """Download a URL once, following only trusted redirections, and return its body."""
    with open_http_client("", {}, httpx2.Timeout(HTTP_TIMEOUT_SECONDS), None) as client:
        response = send_following_redirections(
            client, url, trusted_url_prefix, headers or {}, unredirected_headers or {}
        )
        try:
            if not response.is_success:
                error = SourceStatusError(response.status_code, response.headers)
                note_rate_limit_reset(error)
                raise error
            return read_body(response, max_bytes)
        finally:
            response.close()


def send_following_redirections(
    client: httpx2.Client,
    url: str,
    trusted_url_prefix: str,
    headers: dict[str, str],
    unredirected_headers: dict[str, str],
) -> httpx2.Response:
    """The first answer that is not a redirection, its body not read yet. Each redirection is
    checked on the url httpx2 would request, before it is requested; its body is never read. A
    Location httpx2 cannot read raises httpx2.RemoteProtocolError in client.send; one it reads,
    but not once urljoin has resolved it, raises PageRefusedError, never requested."""
    request = build_request(client, url, {**headers, **unredirected_headers})
    if not str(request.url).startswith(trusted_url_prefix):
        raise ValueError(
            f"url outside its trusted prefix {trusted_url_prefix!r} once normalized, refused"
        )
    response = client.send(request, stream=True)
    redirections = 0
    while response.has_redirect_location:
        response.close()
        if redirections == HTTP_MAX_REDIRECTS:
            raise PageRefusedError(
                f"more than {HTTP_MAX_REDIRECTS} redirections, refused"
            )
        redirections += 1
        # Built from the headers alone, never by response.next_request: it would send the
        # unredirected headers again to a redirection on the same host.
        location = response.headers["Location"]
        try:
            target = urljoin(str(request.url), location)
            request = build_request(client, target, headers)
        except (ValueError, httpx2.InvalidURL) as error:
            # A Location httpx2 reads, but not once urljoin has resolved it: refused, never
            # requested. Cut by hand: urlsplit, behind without_query, refuses it too.
            cut_location = location.partition("?")[0].partition("#")[0]
            raise PageRefusedError(
                f"redirection to an unreadable location {quote_value(cut_location)}, "
                f"refused ({type(error).__name__})"
            ) from None
        if not str(request.url).startswith(trusted_url_prefix):
            raise RedirectedOutsideError(trusted_url_prefix, target)
        response = client.send(request, stream=True)
    return response


def build_request(
    client: httpx2.Client, url: str, headers: dict[str, str]
) -> httpx2.Request:
    """The GET request of url, the User-Agent of K-B last."""
    return client.build_request(
        "GET", url, headers={**headers, "User-Agent": USER_AGENT}
    )


def read_body(response: httpx2.Response, max_bytes: int) -> bytes:
    """Read the body of a response, refusing one larger than max_bytes or not decodable."""
    try:
        return read_bounded_body(response, max_bytes)
    except BodyTooLargeError:
        raise PageRefusedError(
            f"response larger than {max_bytes} bytes, refused"
        ) from None
    except httpx2.DecodingError:
        raise PageRefusedError("body not decodable, refused") from None


def without_query(url: str) -> str:
    """The url without its query nor fragment: the url of a source, or of a redirection, may
    carry anything there."""
    return urlsplit(url)._replace(query="", fragment="").geturl()


def check_trusted_url_prefix(url: str, trusted_url_prefix: str) -> None:
    """Refuse a prefix that would trust too much, or a url the prefix does not cover.

    The prefix names an https host and a path, so that "https://example.org.evil.com" cannot
    pass; no user info either: "https://evil.com\\@good.com/" names good.com."""
    prefix_parts = urlsplit(trusted_url_prefix)
    is_prefix_strict = (
        prefix_parts.scheme == "https"
        and bool(prefix_parts.hostname)
        and "@" not in prefix_parts.netloc
        and prefix_parts.path.startswith("/")
    )
    if not is_prefix_strict:
        raise ValueError(
            f"trusted prefix {trusted_url_prefix!r} is not https://<host>/, refused"
        )
    if not url.startswith(trusted_url_prefix):
        raise ValueError(
            f"url outside its trusted prefix {trusted_url_prefix!r}, refused"
        )
