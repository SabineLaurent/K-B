"""Download the latest releases of a tracked GitHub repository, as published."""

import logging
import re
from datetime import datetime

from k_b.github_api import get_from_github_api
from k_b.github_releases import read_releases
from k_b.tracked_repositories import is_repository_name

logger = logging.getLogger(__name__)

# The API maximum. Only the first page is read: see the warning in fetch.
RELEASES_PER_PAGE = 100


# The name of its raw folders, written once: its instances and its kind use it.
FOLDER_PREFIX = "github_releases"


class GithubReleasesSource:
    extension = "json"

    def __init__(self, repository: str):
        if not is_repository_name(repository):
            raise ValueError(f"not an owner/name repository: {repository!r}")
        self.repository = repository
        self.name = f"{FOLDER_PREFIX}_" + re.sub(r"[^a-z0-9]+", "_", repository.lower())

    def fetch(self, last_collected_at: datetime | None) -> bytes | None:
        """Return the first page of releases; None if none is newer than last_collected_at."""
        raw_response = get_from_github_api(
            f"repos/{self.repository}/releases?per_page={RELEASES_PER_PAGE}"
        )
        # Read even at the first collection: a page that is not a list of releases raises.
        releases = read_releases(raw_response)
        # Defence in depth: the page must be of the tracked repository, whose case GitHub may
        # write differently.
        for position, release in enumerate(releases):
            if release.repository.lower() != self.repository.lower():
                raise ValueError(
                    f"{self.repository}: release {position} is of the repository "
                    f"{release.repository!r}"
                )
        if last_collected_at is None:
            return raw_response
        publication_dates = [release.published_at for release in releases]
        if not any(
            published_at > last_collected_at for published_at in publication_dates
        ):
            return None
        is_page_full = len(publication_dates) >= RELEASES_PER_PAGE
        if is_page_full and min(publication_dates) > last_collected_at:
            logger.warning(
                "%s: more than %d releases since the last collection, some may be missing; "
                "time to read the next pages",
                self.repository,
                RELEASES_PER_PAGE,
            )
        return raw_response
