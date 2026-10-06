"""Read every raw file of raw/automation/ into common items (docs/specs-collecte.md, step 2)."""

import csv
import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, NamedTuple

from pydantic import ValidationError

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


class SourceReader(NamedTuple):
    """How to read a raw file of a source: its entries, then each entry as an item."""

    read_entries: Callable[[bytes], Sequence[object]]
    convert: Callable[[Any, datetime, str], Item]


class Rejection(NamedTuple):
    raw_file_path: str
    reason: str


class RawReading(NamedTuple):
    items: list[Item]
    rejections: list[Rejection]


def read_raw_items(raw_dir: Path) -> RawReading:
    """Every item of the raw files whose source has a reader, in collection order.

    A file that cannot be read, or an entry refused as an item, is rejected and logged; the
    other files and entries are still read.
    """
    readers = list_readers_by_source()
    raw_files = []
    for source_dir in sorted((raw_dir / "automation").glob("*/")):
        reader = readers.get(source_dir.name)
        if reader is None:
            logger.info("source without a reader, skipped: %s", source_dir.name)
            continue
        for path in sorted(source_dir.iterdir()):
            # Hidden files are not raw files: .DS_Store written by macOS, for instance.
            if path.name.startswith("."):
                continue
            if path.is_dir():
                logger.info(
                    "folder of pages without a reader, skipped: %s",
                    path.relative_to(raw_dir).as_posix(),
                )
                continue
            raw_files.append((path, reader))

    items = []
    rejections = []
    for path, reader in raw_files:
        raw_file_path = path.relative_to(raw_dir).as_posix()
        try:
            collected_at = datetime.strptime(path.stem, COLLECTION_NAME_FORMAT).replace(
                tzinfo=UTC
            )
            entries = reader.read_entries(path.read_bytes())
        except (ValueError, csv.Error, OSError) as error:
            rejections.append(reject(raw_file_path, f"{type(error).__name__}: {error}"))
            continue
        for position, entry in enumerate(entries):
            try:
                items.append(reader.convert(entry, collected_at, raw_file_path))
            except ValidationError as error:
                rejections.append(
                    reject(
                        raw_file_path,
                        f"entry {position}: {type(error).__name__}: {error}",
                    )
                )
    # Stable sort: within a collection, the items keep their source order.
    items.sort(key=lambda item: item.collected_at)
    return RawReading(items, rejections)


def reject(raw_file_path: str, reason: str) -> Rejection:
    logger.warning("rejected from %s: %s", raw_file_path, reason)
    return Rejection(raw_file_path, reason)


def list_readers_by_source() -> dict[str, SourceReader]:
    """The reader of each collected source, by the name of its raw folder."""
    readers: dict[str, SourceReader] = {}
    for source in SOURCES:
        match source:
            case ArxivSource():
                readers[source.name] = SourceReader(read_papers, convert_paper)
            case CisaKevSource():
                # The whole catalog: duplicates between collections are removed by the merge.
                readers[source.name] = SourceReader(
                    lambda raw: read_new_vulnerabilities(raw, last_collected_at=None),
                    convert_vulnerability,
                )
            case GithubReleasesSource(repository=repository):
                readers[source.name] = SourceReader(
                    partial(read_releases, repository=repository),
                    convert_release,
                )
            case GithubAdvisoriesSource():
                readers[source.name] = SourceReader(read_advisories, convert_advisory)
            case GithubMostStarredSource():
                readers[source.name] = SourceReader(
                    lambda raw: read_most_starred(raw, expected_size=RANKING_SIZE),
                    convert_starred_repository,
                )
    return readers
