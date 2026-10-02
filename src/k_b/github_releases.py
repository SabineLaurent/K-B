"""Read the releases of a raw GitHub API response."""

import json
from dataclasses import dataclass
from datetime import datetime

RELEASE_URL_PREFIX = "https://github.com/"


@dataclass(frozen=True)
class Release:
    """A release, without its author's login: not needed for the watch (GDPR minimisation)."""

    repository: str
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
    return [parse_release(entry, repository, position) for position, entry in enumerate(entries)]


def parse_release(entry: object, repository: str, position: int) -> Release:
    if not isinstance(entry, dict):
        raise ValueError(f"release {position}: not an object")
    tag_name = entry.get("tag_name")
    if not isinstance(tag_name, str):
        raise ValueError(f"release {position}: tag_name is not a string")
    url = entry.get("html_url")
    if not isinstance(url, str) or not url.startswith(RELEASE_URL_PREFIX):
        raise ValueError(f"release {position}: html_url is not a {RELEASE_URL_PREFIX} URL")
    is_prerelease = entry.get("prerelease")
    if not isinstance(is_prerelease, bool):
        raise ValueError(f"release {position}: prerelease is not a boolean")
    name = entry.get("name")
    body = entry.get("body")
    if not isinstance(name, str | None) or not isinstance(body, str | None):
        raise ValueError(f"release {position}: name or body is not a string")
    return Release(
        repository=repository,
        tag_name=tag_name,
        name=name,
        url=url,
        published_at=parse_publication_date(entry.get("published_at"), position),
        is_prerelease=is_prerelease,
        body=body,
    )


def parse_publication_date(published_at: object, position: int) -> datetime:
    """Refuse a date without a time zone: GitHub dates are UTC, written with a final Z."""
    if not isinstance(published_at, str):
        raise ValueError(f"release {position}: published_at is not a date")
    try:
        parsed_date = datetime.fromisoformat(published_at)
    except ValueError as error:
        raise ValueError(f"release {position}: invalid published_at: {published_at!r}") from error
    if parsed_date.tzinfo is None:
        raise ValueError(f"release {position}: published_at without a time zone")
    return parsed_date
