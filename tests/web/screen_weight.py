"""The weight of a screen of the site, the budget of D2 of #563 and D4 of #564 (Sabine, 2026-11-11;
RGESN 6.1): the page and what it fetches, cache empty, compressed."""

import gzip
import re
from dataclasses import dataclass

from site_client import OPERATOR_HEADERS

RESOURCE = re.compile(r"<(?:link|img|script|iframe|source)\b[^>]*>")
TARGET = re.compile(r'(?:href|src)="([^"]+)"')
# 3 requests and 30 KB transferred by screen.
SCREEN_RESOURCES = ["/static/site.css", "/static/favicon.svg"]
SCREEN_BUDGET_BYTES = 30_000


@dataclass(frozen=True)
class Screen:
    status_code: int
    resources: list[str]
    weight: int


def weigh_screen(client, path):
    """The status of the page, the paths it fetches, and its weight with them: the page compressed
    by gzip, each resource as transferred."""
    headers = {**OPERATOR_HEADERS, "Accept-Encoding": "gzip"}
    page = client.get(path, headers=headers)
    resources = [TARGET.search(tag).group(1) for tag in RESOURCE.findall(page.text)]
    weights = [len(gzip.compress(page.content))] + [
        client.get(resource, headers=headers).num_bytes_downloaded
        for resource in resources
    ]
    return Screen(page.status_code, resources, sum(weights))
