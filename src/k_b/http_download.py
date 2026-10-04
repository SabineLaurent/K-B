"""Download one URL for a source: the network boundary every collection goes through."""

from urllib.request import Request, urlopen

from k_b.user_agent import USER_AGENT

TIMEOUT_SECONDS = 30


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
    request = Request(url, headers={**(headers or {}), "User-Agent": USER_AGENT})
    for name, value in (unredirected_headers or {}).items():
        request.add_unredirected_header(name, value)
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        # urlopen follows redirections, even to plain HTTP: only an answer from here is trusted.
        if not response.url.startswith(trusted_url_prefix):
            raise ValueError(f"response redirected outside {trusted_url_prefix}, refused")
        body = response.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise ValueError(f"response larger than {max_bytes} bytes, refused")
    return body
