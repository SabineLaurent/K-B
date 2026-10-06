"""Download one URL for a source: the network boundary every collection goes through."""

from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from k_b.user_agent import USER_AGENT

TIMEOUT_SECONDS = 30


class RedirectedOutsideError(ValueError):
    """The answer came from outside the trusted prefix; redirect_url says where it led.

    A source may read it (tldr.tech redirects a day without an edition to its landing page).
    Refusing a redirection before following it (#54) must keep raising this error, with the
    redirection target resolved against the requested url.
    """

    def __init__(self, trusted_url_prefix: str, redirect_url: str):
        super().__init__(
            f"response redirected to {redirect_url}, outside {trusted_url_prefix}, refused"
        )
        self.redirect_url = redirect_url


def download(
    url: str,
    trusted_url_prefix: str,
    max_bytes: int,
    headers: dict[str, str] | None = None,
    unredirected_headers: dict[str, str] | None = None,
) -> bytes:
    """Return the body of GET url, refused if served from outside trusted_url_prefix or too large.

    An unredirected header (a token) is never forwarded to a redirection. An HTTPError is raised
    to the caller, who alone knows what a status such as 304 means.
    """
    check_trusted_url_prefix(url, trusted_url_prefix)
    # https only: check_trusted_url_prefix refuses any other scheme.
    request = Request(url, headers={**(headers or {}), "User-Agent": USER_AGENT})  # noqa: S310
    for name, value in (unredirected_headers or {}).items():
        request.add_unredirected_header(name, value)
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
        # urlopen follows redirections, even to plain HTTP: only an answer from here is trusted.
        if not response.url.startswith(trusted_url_prefix):
            raise RedirectedOutsideError(trusted_url_prefix, response.url)
        body: bytes = response.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise ValueError(f"response larger than {max_bytes} bytes, refused")
    return body


def check_trusted_url_prefix(url: str, trusted_url_prefix: str) -> None:
    """Refuse a prefix that would trust too much, or a url the prefix does not cover.

    The prefix must name an https host and end it with a path, so that "https://" or
    "https://example.org" (which "https://example.org.evil.com" starts with) cannot be passed.
    No user info either: urlsplit reads "https://evil.com\\@good.com/" as good.com, urllib does not.
    """
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
