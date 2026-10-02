"""Download the security advisories of the tracked packages of one ecosystem, as published."""

import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from k_b.github_advisories import read_advisories
from k_b.github_api import get_from_github_api

logger = logging.getLogger(__name__)

ECOSYSTEMS = ("pip", "npm")
# The API maximum. Only the first page is read: see the warning in fetch.
ADVISORIES_PER_PAGE = 100


class GithubAdvisoriesSource:
    extension = "json"

    def __init__(self, ecosystem: str, packages: tuple[str, ...]):
        if ecosystem not in ECOSYSTEMS:
            raise ValueError(f"not a tracked ecosystem: {ecosystem!r}")
        self.ecosystem = ecosystem
        self.packages = packages
        self.name = f"github_advisories_{ecosystem}"

    def fetch(self, last_collected_at: datetime | None) -> bytes | None:
        """Return the advisories of the packages; None if none is newer than last_collected_at.

        The packages are filtered in the request, not at the reading: the whole ecosystem would
        exceed a page (npm publishes more than 100 advisories a week).
        """
        query = {
            "type": "reviewed",
            "ecosystem": self.ecosystem,
            "affects": ",".join(self.packages),
            "per_page": ADVISORIES_PER_PAGE,
        }
        if last_collected_at is not None:
            # The filter is checked to the day only: a day of margin, then the exact comparison.
            since = last_collected_at.astimezone(UTC).date() - timedelta(days=1)
            query["published"] = f">={since.isoformat()}"
        raw_response = get_from_github_api(f"advisories?{urlencode(query)}")
        publication_dates = [advisory.published_at for advisory in read_advisories(raw_response)]
        if not publication_dates:
            return None
        if last_collected_at is None:
            return raw_response
        if not any(published_at > last_collected_at for published_at in publication_dates):
            return None
        is_page_full = len(publication_dates) >= ADVISORIES_PER_PAGE
        if is_page_full and min(publication_dates) > last_collected_at:
            logger.warning(
                "%s: more than %d advisories since the last collection, some may be missing; "
                "time to read the next pages",
                self.name,
                ADVISORIES_PER_PAGE,
            )
        return raw_response
