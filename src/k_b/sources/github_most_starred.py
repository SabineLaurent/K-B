"""The most starred GitHub repositories source: its download (E), and the reading of its ranking.

Download the ranking of the most starred GitHub repositories, as published.

Read a raw ranking of the most starred GitHub repositories: the download checks its response with
it. The ranking gives no item: it does not enter the base (decision "Tops", 2026-10-08).
"""

import json
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode

from k_b.raw_store import AUTOMATED_WATCH_DIR_NAME
from k_b.sources.github_api import get_from_github_api
from k_b.sources.github_dates import parse_github_date
from k_b.sources.tracked_repositories import is_repository_name

# The search needs a criterion: this one keeps the whole top 100 (the 100th had 116,161 stars on
# 2026-10-02).
SEARCH_QUERY = "stars:>10000"


REPOSITORY_URL_PREFIX = "https://github.com/"
# The API maximum: one request, deep enough to see a repository enter the top.
RANKING_SIZE = 100


# The name of its raw folders, written once: its instances and its kind use it.
FOLDER_PREFIX = "github_most_starred"


class GithubMostStarredSource:
    name = FOLDER_PREFIX
    extension = "json"
    acquisition_dir_name = AUTOMATED_WATCH_DIR_NAME

    def fetch(self, last_collected_at: datetime | None) -> bytes | None:
        """Return a snapshot of the ranking at every collection: star counts always change.

        Entries, exits and climbs are found at the reading, by comparing two snapshots.
        """
        query = {
            "q": SEARCH_QUERY,
            "sort": "stars",
            "order": "desc",
            "per_page": RANKING_SIZE,
        }
        raw_response = get_from_github_api(f"search/repositories?{urlencode(query)}")
        read_ranking(raw_response)
        return raw_response


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


def read_most_starred(
    raw_response: bytes, expected_size: int
) -> list[StarredRepository]:
    """One repository per item of a `GET /search/repositories` response, by rank.

    A ranking with fewer repositories than asked for, or marked incomplete, is refused: compared
    with the previous one, it would show repositories leaving the top that never left it.
    """
    response = json.loads(raw_response)
    items = response.get("items") if isinstance(response, dict) else None
    if not isinstance(items, list):
        raise ValueError("expected a search response with a list of items")
    if response.get("incomplete_results") is not False:
        raise ValueError("incomplete search results, refused")
    if len(items) != expected_size:
        raise ValueError(
            f"{len(items)} repositories, expected {expected_size}, refused"
        )
    return [parse_repository(item, rank) for rank, item in enumerate(items, start=1)]


def parse_repository(item: object, rank: int) -> StarredRepository:
    if not isinstance(item, dict):
        raise ValueError(f"repository {rank}: not an object")
    full_name = item.get("full_name")
    if not isinstance(full_name, str) or not is_repository_name(full_name):
        raise ValueError(f"repository {rank}: not an owner/name: {full_name!r}")
    url = item.get("html_url")
    if not isinstance(url, str) or not url.startswith(REPOSITORY_URL_PREFIX):
        raise ValueError(
            f"repository {rank}: html_url is not a {REPOSITORY_URL_PREFIX} URL"
        )
    description = item.get("description")
    if not isinstance(description, str | None):
        raise ValueError(f"repository {rank}: description is not a string")
    stars = item.get("stargazers_count")
    # bool is a subclass of int in Python: refuse it explicitly.
    if not isinstance(stars, int) or isinstance(stars, bool):
        raise ValueError(f"repository {rank}: stargazers_count is not an integer")
    topics = item.get("topics")
    if not isinstance(topics, list) or not all(
        isinstance(topic, str) for topic in topics
    ):
        raise ValueError(f"repository {rank}: topics is not a list of strings")
    return StarredRepository(
        rank=rank,
        full_name=full_name,
        url=url,
        description=description,
        stars=stars,
        topics=tuple(topics),
        created_at=parse_github_date(
            item.get("created_at"), f"repository {rank}: created_at"
        ),
    )


def read_ranking(raw_response: bytes) -> list[StarredRepository]:
    return read_most_starred(raw_response, expected_size=RANKING_SIZE)
