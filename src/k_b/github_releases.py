"""Read the releases of a raw GitHub API response, and convert each one into an item."""

import json
from dataclasses import dataclass
from datetime import datetime

from k_b.github_dates import parse_github_date
from k_b.items import Item

RELEASE_URL_PREFIX = "https://github.com/"


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


def read_releases(raw_response: bytes, repository: str) -> list[Release]:
    """One release per entry of a `GET /repos/{owner}/{repo}/releases` response, newest first."""
    entries = json.loads(raw_response)
    if not isinstance(entries, list):
        raise ValueError("expected a list of releases")
    return [
        parse_release(entry, repository, position)
        for position, entry in enumerate(entries)
    ]


def parse_release(entry: object, repository: str, position: int) -> Release:
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
    if not isinstance(url, str) or not url.startswith(RELEASE_URL_PREFIX):
        raise ValueError(
            f"release {position}: html_url is not a {RELEASE_URL_PREFIX} URL"
        )
    is_prerelease = entry.get("prerelease")
    if not isinstance(is_prerelease, bool):
        raise ValueError(f"release {position}: prerelease is not a boolean")
    name = entry.get("name")
    body = entry.get("body")
    if not isinstance(name, str | None) or not isinstance(body, str | None):
        raise ValueError(f"release {position}: name or body is not a string")
    return Release(
        repository=repository,
        release_id=release_id,
        tag_name=tag_name,
        name=name,
        url=url,
        published_at=parse_github_date(
            entry.get("published_at"), f"release {position}: published_at"
        ),
        is_prerelease=is_prerelease,
        body=body,
    )


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
