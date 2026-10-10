"""The GitHub security advisories source: its download (E), and the reading of its raw response.

Download the security advisories of the tracked packages of one ecosystem, as published.

Read the security advisories of a raw GitHub API response: the download uses it to tell the new
ones. No item yet: the advisories are skipped at the import until #121.
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from k_b.items import CVE_ID
from k_b.sources.github_api import get_from_github_api
from k_b.sources.github_dates import parse_github_date

logger = logging.getLogger(__name__)

ECOSYSTEMS = ("pip", "npm")
# The API maximum. Only the first page is read: see the warning in fetch.
ADVISORIES_PER_PAGE = 100


GHSA_ID = re.compile(r"GHSA(-[23456789cfghjmpqrvwx]{4}){3}")
ADVISORY_URL_PREFIX = "https://github.com/advisories/"
SEVERITIES = ("low", "medium", "high", "critical", "unknown")


# The name of its raw folders, written once: its instances and its kind use it.
FOLDER_PREFIX = "github_advisories"


class GithubAdvisoriesSource:
    extension = "json"

    def __init__(self, ecosystem: str, packages: tuple[str, ...]):
        if ecosystem not in ECOSYSTEMS:
            raise ValueError(f"not a tracked ecosystem: {ecosystem!r}")
        self.ecosystem = ecosystem
        self.packages = packages
        self.name = f"{FOLDER_PREFIX}_{ecosystem}"

    def fetch(self, last_collected_at: datetime | None) -> bytes | None:
        """Return the advisories of the packages; None if none was reviewed since last_collected_at.

        Only reviewed advisories are asked for, and GitHub may review one days after publishing
        it: the publication date would miss it, so collections follow the review date.

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
            query["reviewed"] = f">={since.isoformat()}"
        raw_response = get_from_github_api(f"advisories?{urlencode(query)}")
        review_dates = [
            advisory.reviewed_at for advisory in read_advisories(raw_response)
        ]
        if not review_dates:
            return None
        if last_collected_at is None:
            return raw_response
        if not any(reviewed_at > last_collected_at for reviewed_at in review_dates):
            return None
        is_page_full = len(review_dates) >= ADVISORIES_PER_PAGE
        if is_page_full and min(review_dates) > last_collected_at:
            logger.warning(
                "%s: more than %d advisories since the last collection, some may be missing; "
                "time to read the next pages",
                self.name,
                ADVISORIES_PER_PAGE,
            )
        return raw_response


@dataclass(frozen=True)
class Advisory:
    """An advisory, without the people it credits: not needed for the watch (GDPR minimisation)."""

    ghsa_id: str
    cve_id: str | None
    summary: str
    severity: str
    url: str
    published_at: datetime
    # GitHub may review an advisory days after publishing it: collections follow this date.
    reviewed_at: datetime
    packages: tuple[str, ...]


def read_advisories(raw_response: bytes) -> list[Advisory]:
    """One advisory per entry of a `GET /advisories` response, newest first."""
    entries = json.loads(raw_response)
    if not isinstance(entries, list):
        raise ValueError("expected a list of advisories")
    return [parse_advisory(entry, position) for position, entry in enumerate(entries)]


def parse_advisory(entry: object, position: int) -> Advisory:
    if not isinstance(entry, dict):
        raise ValueError(f"advisory {position}: not an object")
    ghsa_id = entry.get("ghsa_id")
    if not isinstance(ghsa_id, str) or not GHSA_ID.fullmatch(ghsa_id):
        raise ValueError(f"advisory {position}: not a GHSA identifier: {ghsa_id!r}")
    cve_id = entry.get("cve_id")
    if cve_id is not None and not (
        isinstance(cve_id, str) and CVE_ID.fullmatch(cve_id)
    ):
        raise ValueError(f"advisory {position}: not a CVE identifier: {cve_id!r}")
    summary = entry.get("summary")
    if not isinstance(summary, str):
        raise ValueError(f"advisory {position}: summary is not a string")
    severity = entry.get("severity")
    if severity not in SEVERITIES:
        raise ValueError(f"advisory {position}: unknown severity: {severity!r}")
    url = entry.get("html_url")
    if not isinstance(url, str) or not url.startswith(ADVISORY_URL_PREFIX):
        raise ValueError(
            f"advisory {position}: html_url is not a {ADVISORY_URL_PREFIX} URL"
        )
    return Advisory(
        ghsa_id=ghsa_id,
        cve_id=cve_id,
        summary=summary,
        severity=severity,
        url=url,
        published_at=parse_github_date(
            entry.get("published_at"), f"advisory {position}: published_at"
        ),
        reviewed_at=parse_github_date(
            entry.get("github_reviewed_at"), f"advisory {position}: github_reviewed_at"
        ),
        packages=parse_package_names(entry.get("vulnerabilities"), position),
    )


def parse_package_names(vulnerabilities: object, position: int) -> tuple[str, ...]:
    """The affected packages, each once: an advisory lists one package per vulnerable range."""
    if not isinstance(vulnerabilities, list):
        raise ValueError(f"advisory {position}: vulnerabilities is not a list")
    package_names: list[str] = []
    for vulnerability in vulnerabilities:
        package = (
            vulnerability.get("package") if isinstance(vulnerability, dict) else None
        )
        name = package.get("name") if isinstance(package, dict) else None
        if not isinstance(name, str):
            raise ValueError(
                f"advisory {position}: a vulnerability has no package name"
            )
        if name not in package_names:
            package_names.append(name)
    return tuple(package_names)
