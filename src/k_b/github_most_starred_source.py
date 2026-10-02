"""Download the ranking of the most starred GitHub repositories, as published."""

from datetime import datetime
from urllib.parse import urlencode

from k_b.github_api import get_from_github_api
from k_b.github_most_starred import read_most_starred

# The search needs a criterion: this one keeps the whole top 100 (the 100th had 116,161 stars on
# 2026-10-02).
SEARCH_QUERY = "stars:>10000"
# The API maximum: one request, deep enough to see a repository enter the top.
RANKING_SIZE = 100


class GithubMostStarredSource:
    name = "github_most_starred"
    extension = "json"

    def fetch(self, last_collected_at: datetime | None) -> bytes | None:
        """Return a snapshot of the ranking at every collection: star counts always change.

        Entries, exits and climbs are found at the reading, by comparing two snapshots.
        """
        query = {"q": SEARCH_QUERY, "sort": "stars", "order": "desc", "per_page": RANKING_SIZE}
        raw_response = get_from_github_api(f"search/repositories?{urlencode(query)}")
        read_most_starred(raw_response)
        return raw_response
