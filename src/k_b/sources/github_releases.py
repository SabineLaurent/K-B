"""The GitHub releases source: its download (E), then its reader (T).

Download the latest releases of a tracked GitHub repository, as published.

Read the releases of a raw GitHub API response, and convert each one into an item.
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import unquote

from k_b.items import Item
from k_b.source import SourceReader
from k_b.sources.github_api import get_from_github_api
from k_b.sources.github_dates import parse_github_date
from k_b.sources.tracked_repositories import OWNER_SLASH_NAME, is_repository_name

logger = logging.getLogger(__name__)

# The API maximum. Only the first page is read: see the warning in fetch.
RELEASES_PER_PAGE = 100


# The repository is read in the release URL: the raw file can be read without its source.
# The whole URL is checked, so that the link opens the repository of the title: the tag part
# takes only the path characters of RFC 3986 and /, so no query, fragment, space or non-ASCII.
RELEASE_URL = re.compile(
    rf"https://github\.com/({OWNER_SLASH_NAME.pattern})/releases/tag/"
    r"(?:[A-Za-z0-9._~!$&'()*+,;=:@/-]|%[0-9A-Fa-f]{2})+"
)


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


@dataclass(frozen=True)
class Release:
    """A release, without its author's login: not needed for the watch (GDPR minimisation)."""

    repository: str
    release_id: int
    tag_name: str
    name: str | None
    url: str
    published_at: datetime
    is_prerelease: bool
    body: str | None


def read_releases(raw_response: bytes) -> list[Release]:
    """One release per entry of a `GET /repos/{owner}/{repo}/releases` response, newest first."""
    entries = json.loads(raw_response)
    if not isinstance(entries, list):
        raise ValueError("expected a list of releases")
    return [parse_release(entry, position) for position, entry in enumerate(entries)]


def parse_release(entry: object, position: int) -> Release:
    if not isinstance(entry, dict):
        raise ValueError(f"release {position}: not an object")
    release_id = entry.get("id")
    # bool is a subclass of int: refused explicitly.
    if not isinstance(release_id, int) or isinstance(release_id, bool):
        raise ValueError(f"release {position}: id is not an integer")
    tag_name = entry.get("tag_name")
    if not isinstance(tag_name, str):
        raise ValueError(f"release {position}: tag_name is not a string")
    url = entry.get("html_url")
    url_match = RELEASE_URL.fullmatch(url) if isinstance(url, str) else None
    if (
        url_match is None
        or not is_repository_name(url_match.group(1))
        or has_dot_segment(url_match.string)
    ):
        raise ValueError(
            f"release {position}: html_url is not a release URL of an owner/name "
            f"repository: {url!r}"
        )
    is_prerelease = entry.get("prerelease")
    if not isinstance(is_prerelease, bool):
        raise ValueError(f"release {position}: prerelease is not a boolean")
    name = entry.get("name")
    body = entry.get("body")
    if not isinstance(name, str | None) or not isinstance(body, str | None):
        raise ValueError(f"release {position}: name or body is not a string")
    return Release(
        repository=url_match.group(1),
        release_id=release_id,
        tag_name=tag_name,
        name=name,
        url=url_match.string,
        published_at=parse_github_date(
            entry.get("published_at"), f"release {position}: published_at"
        ),
        is_prerelease=is_prerelease,
        body=body,
    )


def has_dot_segment(url: str) -> bool:
    """A `.` or `..` path segment, even percent-encoded: a browser would resolve it."""
    return any(segment in (".", "..") for segment in unquote(url).split("/"))


def convert_release(
    release: Release, collected_at: datetime, raw_file_path: str
) -> Item:
    return Item(
        source_code="github",
        source_item_id=str(release.release_id),
        title=f"{release.repository} {release.name or release.tag_name}",
        url=release.url,
        published_at=release.published_at,
        summary=release.body,
        collected_at=collected_at,
        raw_file_path=raw_file_path,
    )


READER: SourceReader[Release] = SourceReader(read_releases, convert_release)
