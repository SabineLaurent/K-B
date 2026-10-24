"""Read the GitHub REST API: one GET, answered as published."""

import os

from k_b.etl.http_download import download
from k_b.items import SourceCode

# The source of every GitHub module, in the source table of the base.
SOURCE_CODE: SourceCode = "github"
API_URL = "https://api.github.com/"
API_VERSION = "2026-03-10"
TOKEN_VARIABLE = "KB_GITHUB_TOKEN"  # noqa: S105 — the variable's name, not a token
# A page of 100 releases of anthropics/claude-code weighs 2.2 MB in 2026.
MAX_RESPONSE_BYTES = 5 * 1024 * 1024


def get_from_github_api(path_and_query: str) -> bytes:
    """Return the body of GET API_URL + path_and_query, with the token if there is one (60
    requests per hour without, 5,000 with)."""
    token = os.environ.get(TOKEN_VARIABLE)
    return download(
        API_URL + path_and_query,
        trusted_url_prefix=API_URL,
        max_bytes=MAX_RESPONSE_BYTES,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
        },
        # Never forwarded to a redirection: the token stays with api.github.com.
        unredirected_headers={"Authorization": f"Bearer {token}"} if token else None,
    )
