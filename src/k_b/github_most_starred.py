"""Read a raw ranking of the most starred GitHub repositories."""

import json
import re
from dataclasses import dataclass
from datetime import datetime

from k_b.github_dates import parse_github_date

OWNER_SLASH_NAME = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
REPOSITORY_URL_PREFIX = "https://github.com/"


@dataclass(frozen=True)
class StarredRepository:
    rank: int
    # owner/name: the owner's login is kept, as it identifies the repository (see the register).
    full_name: str
    url: str
    description: str | None
    stars: int
    topics: tuple[str, ...]
    created_at: datetime


def read_most_starred(raw_response: bytes) -> list[StarredRepository]:
    """One repository per item of a `GET /search/repositories` response, by rank."""
    response = json.loads(raw_response)
    items = response.get("items") if isinstance(response, dict) else None
    if not isinstance(items, list):
        raise ValueError("expected a search response with a list of items")
    # GitHub cut the search short: a partial ranking would show false exits from the top.
    if response.get("incomplete_results") is not False:
        raise ValueError("incomplete search results, refused")
    return [parse_repository(item, rank) for rank, item in enumerate(items, start=1)]


def parse_repository(item: object, rank: int) -> StarredRepository:
    if not isinstance(item, dict):
        raise ValueError(f"repository {rank}: not an object")
    full_name = item.get("full_name")
    is_owner_slash_name = isinstance(full_name, str) and bool(OWNER_SLASH_NAME.fullmatch(full_name))
    if not is_owner_slash_name or ".." in full_name:
        raise ValueError(f"repository {rank}: not an owner/name: {full_name!r}")
    url = item.get("html_url")
    if not isinstance(url, str) or not url.startswith(REPOSITORY_URL_PREFIX):
        raise ValueError(f"repository {rank}: html_url is not a {REPOSITORY_URL_PREFIX} URL")
    description = item.get("description")
    if not isinstance(description, str | None):
        raise ValueError(f"repository {rank}: description is not a string")
    stars = item.get("stargazers_count")
    # bool is a subclass of int in Python: refuse it explicitly.
    if not isinstance(stars, int) or isinstance(stars, bool):
        raise ValueError(f"repository {rank}: stargazers_count is not an integer")
    topics = item.get("topics")
    if not isinstance(topics, list) or not all(isinstance(topic, str) for topic in topics):
        raise ValueError(f"repository {rank}: topics is not a list of strings")
    return StarredRepository(
        rank=rank,
        full_name=full_name,
        url=url,
        description=description,
        stars=stars,
        topics=tuple(topics),
        created_at=parse_github_date(item.get("created_at"), f"repository {rank}: created_at"),
    )
