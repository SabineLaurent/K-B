"""Read the GitHub REST API: one GET, answered as published."""

import os
from urllib.request import Request, urlopen

from k_b.user_agent import USER_AGENT

API_URL = "https://api.github.com/"
API_VERSION = "2026-03-10"
TOKEN_VARIABLE = "KB_GITHUB_TOKEN"
TIMEOUT_SECONDS = 30
# A page of 100 releases of anthropics/claude-code weighs 2.2 MB in 2026.
MAX_RESPONSE_BYTES = 5 * 1024 * 1024


def get_from_github_api(path_and_query: str) -> bytes:
    """Return the body of GET API_URL + path_and_query, with the token if there is one.

    Without a token, GitHub allows 60 requests per hour instead of 5,000.
    """
    request = Request(
        API_URL + path_and_query,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": API_VERSION,
        },
    )
    token = os.environ.get(TOKEN_VARIABLE)
    if token:
        # urlopen follows redirections: an unredirected header never leaves the first request.
        request.add_unredirected_header("Authorization", f"Bearer {token}")
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        if not response.url.startswith(API_URL):
            raise ValueError(f"response redirected outside {API_URL}, refused")
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError(f"response larger than {MAX_RESPONSE_BYTES} bytes, refused")
    return body
