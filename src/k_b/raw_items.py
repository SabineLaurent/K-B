"""Read every raw file of raw/automation/ into common items (docs/specs-collecte.md, step 2)."""

import csv
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

from k_b.arxiv_papers import read_papers
from k_b.arxiv_source import ArxivSource
from k_b.cisa_kev import read_new_vulnerabilities
from k_b.cisa_kev_source import CisaKevSource
from k_b.collect import SOURCES
from k_b.github_advisories import read_advisories
from k_b.github_advisories_source import GithubAdvisoriesSource
from k_b.github_most_starred import read_most_starred
from k_b.github_most_starred_source import RANKING_SIZE, GithubMostStarredSource
from k_b.github_releases import read_releases
from k_b.github_releases_source import GithubReleasesSource
from k_b.items import (
    Item,
    convert_advisory,
    convert_paper,
    convert_release,
    convert_starred_repository,
    convert_vulnerability,
)

logger = logging.getLogger(__name__)

# The name collect.py gives every raw file of a collection.
COLLECTION_NAME_FORMAT = "%Y-%m-%dT%H%M%SZ"

ReadRawFile = Callable[[bytes, datetime, str], list[Item]]


class Rejection(NamedTuple):
    raw_file_path: str
    reason: str


class RawReading(NamedTuple):
    items: list[Item]
    rejections: list[Rejection]


def read_raw_items(raw_dir: Path) -> RawReading:
    """Every item of the raw files whose source has a reader, in collection order.

    A file that cannot be read is rejected and logged; the other files are still read.
    """
    readers = list_readers_by_source()
    raw_files = []
    for source_dir in sorted((raw_dir / "automation").glob("*/")):
        read_raw_file = readers.get(source_dir.name)
        if read_raw_file is None:
            logger.info("source without a reader, skipped: %s", source_dir.name)
            continue
        for path in sorted(source_dir.iterdir()):
            if path.is_dir():
                logger.info(
                    "folder of pages without a reader, skipped: %s",
                    path.relative_to(raw_dir).as_posix(),
                )
                continue
            raw_files.append((path, read_raw_file))

    items = []
    rejections = []
    for path, read_raw_file in raw_files:
        raw_file_path = path.relative_to(raw_dir).as_posix()
        try:
            collected_at = datetime.strptime(path.stem, COLLECTION_NAME_FORMAT).replace(tzinfo=UTC)
            items.extend(read_raw_file(path.read_bytes(), collected_at, raw_file_path))
        except (ValueError, csv.Error, OSError) as error:
            reason = f"{type(error).__name__}: {error}"
            logger.warning("raw file rejected: %s: %s", raw_file_path, reason)
            rejections.append(Rejection(raw_file_path, reason))
    # Stable sort: within a collection, the items keep their source order.
    items.sort(key=lambda item: item.collected_at)
    return RawReading(items, rejections)


def list_readers_by_source() -> dict[str, ReadRawFile]:
    """The reader of each collected source, by the name of its raw folder."""
    readers: dict[str, ReadRawFile] = {}
    for source in SOURCES:
        match source:
            case ArxivSource():
                readers[source.name] = lambda raw, collected_at, raw_file_path: [
                    convert_paper(paper, collected_at, raw_file_path) for paper in read_papers(raw)
                ]
            case CisaKevSource():
                # The whole catalog: duplicates between collections are removed by the merge.
                readers[source.name] = lambda raw, collected_at, raw_file_path: [
                    convert_vulnerability(vulnerability, collected_at, raw_file_path)
                    for vulnerability in read_new_vulnerabilities(raw, last_collected_at=None)
                ]
            case GithubReleasesSource(repository=repository):
                readers[source.name] = (
                    lambda raw, collected_at, raw_file_path, repository=repository: [
                        convert_release(release, collected_at, raw_file_path)
                        for release in read_releases(raw, repository)
                    ]
                )
            case GithubAdvisoriesSource():
                readers[source.name] = lambda raw, collected_at, raw_file_path: [
                    convert_advisory(advisory, collected_at, raw_file_path)
                    for advisory in read_advisories(raw)
                ]
            case GithubMostStarredSource():
                readers[source.name] = lambda raw, collected_at, raw_file_path: [
                    convert_starred_repository(repository, collected_at, raw_file_path)
                    for repository in read_most_starred(raw, expected_size=RANKING_SIZE)
                ]
    return readers
