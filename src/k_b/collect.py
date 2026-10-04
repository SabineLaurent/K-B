"""Run every source and store its raw output; a failing source never stops the others."""

import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from k_b.arxiv_source import ArxivSource
from k_b.cisa_kev_source import CisaKevSource
from k_b.github_advisories_source import GithubAdvisoriesSource
from k_b.github_most_starred_source import GithubMostStarredSource
from k_b.github_releases_source import GithubReleasesSource
from k_b.raw_store import load_last_collection_dates, save_last_collection_dates, write_new_raw_file
from k_b.tldr_source import TRACKED_EDITIONS, TldrSource
from k_b.tracked_repositories import TRACKED_REPOSITORIES, list_packages_by_ecosystem

logger = logging.getLogger(__name__)

SAFE_PATH_SEGMENT = re.compile(r"[a-z0-9_]+")
# A page name is a file name under the collection folder: a date such as 2026-09-30.
SAFE_PAGE_NAME = re.compile(r"[a-z0-9_-]+")


class Source(Protocol):
    name: str
    extension: str

    def fetch(self, last_collected_at: datetime | None) -> bytes | dict[str, bytes] | None:
        """Return the raw content published since last_collected_at (None: first collection).

        A source that reads several pages (a scraped site) returns them by page name. Return
        None when the source says nothing changed since last_collected_at.
        """
        ...


SOURCES: list[Source] = [
    CisaKevSource(),
    *(GithubReleasesSource(repository.name) for repository in TRACKED_REPOSITORIES),
    *(
        GithubAdvisoriesSource(ecosystem, packages)
        for ecosystem, packages in list_packages_by_ecosystem(TRACKED_REPOSITORIES).items()
    ),
    GithubMostStarredSource(),
    ArxivSource(),
    *(TldrSource(edition) for edition in TRACKED_EDITIONS),
]


def collect_all_sources(
    sources: list[Source], raw_dir: Path, now: datetime
) -> dict[str, Exception | None]:
    """Collect each source; return, per source name, its error or None if it succeeded."""
    if now.utcoffset() != timedelta(0):
        raise ValueError(f"collection time must be in UTC, got {now!r}")
    last_collection_dates = load_last_collection_dates(raw_dir)
    errors_by_source: dict[str, Exception | None] = {}
    for source in sources:
        try:
            collect_one_source(source, raw_dir, now, last_collection_dates.get(source.name))
        except Exception as error:
            logger.exception("collection failed for source %r", source.name)
            errors_by_source[source.name] = error
        else:
            last_collection_dates[source.name] = now
            errors_by_source[source.name] = None
    save_last_collection_dates(raw_dir, last_collection_dates)
    return errors_by_source


def collect_one_source(
    source: Source, raw_dir: Path, now: datetime, last_collected_at: datetime | None
) -> None:
    for path_segment in (source.name, source.extension):
        if not SAFE_PATH_SEGMENT.fullmatch(path_segment):
            raise ValueError(f"not a safe path segment: {path_segment!r}")
    raw_content = source.fetch(last_collected_at)
    if raw_content is None:
        return
    source_dir = raw_dir / "automation" / source.name
    collection_name = f"{now:%Y-%m-%dT%H%M%SZ}"
    if isinstance(raw_content, bytes):
        write_new_raw_file(source_dir / f"{collection_name}.{source.extension}", raw_content)
        return
    # Every name is checked before the first write: a refused page leaves no partial collection.
    for page_name in raw_content:
        if not SAFE_PAGE_NAME.fullmatch(page_name):
            raise ValueError(f"not a safe page name: {page_name!r}")
    for page_name, page in raw_content.items():
        write_new_raw_file(source_dir / collection_name / f"{page_name}.{source.extension}", page)
