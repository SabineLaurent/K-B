"""Read the raw files of raw/automated_watch/ not imported yet into common items
(docs/specs-collecte.md, step 2)."""

import csv
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

from pydantic import ValidationError

from k_b.items import Item, SourceCode
from k_b.raw_store import AUTOMATED_WATCH_DIR_NAME
from k_b.source_contract import SourceKind, SourceReader, find_source_kind

logger = logging.getLogger(__name__)

# The name collect.py gives every raw file of a collection.
COLLECTION_NAME_FORMAT = "%Y-%m-%dT%H%M%SZ"


class Rejection(NamedTuple):
    raw_file_path: str
    reason: str


class RawFile(NamedTuple):
    """A raw file read: a page, for a collection that is a folder of pages."""

    raw_file_path: str
    source_code: SourceCode
    collected_at: datetime
    items: list[Item]
    # Its entries refused as items: a catalog with one of them withdraws nothing (#106).
    rejection_count: int


class RawReading(NamedTuple):
    files: list[RawFile]
    rejections: list[Rejection]
    # The pages opened, readable or not.
    read_count: int


def read_raw_items(
    raw_dir: Path, kinds: Sequence[SourceKind], imported_paths: frozenset[str]
) -> RawReading:
    """Every raw file whose source kind has a reader and that is not in imported_paths, in
    collection order.

    A collection is a raw file, or a folder of pages; a raw file is read as a single page. A
    collection not named by its time or that cannot be listed, a page that cannot be read, or
    an entry refused as an item, is rejected and logged; the others are still read. A page
    already imported is not opened.
    """
    reading = join_readings(
        [
            read_collection(collection_path, raw_dir, reader, imported_paths)
            for collection_path, reader in list_collections(raw_dir, kinds)
        ]
    )
    # Stable sort: within a collection, the files keep their page order.
    reading.files.sort(key=lambda raw_file: raw_file.collected_at)
    return reading


def join_readings(readings: list[RawReading]) -> RawReading:
    return RawReading(
        [raw_file for reading in readings for raw_file in reading.files],
        [rejection for reading in readings for rejection in reading.rejections],
        sum(reading.read_count for reading in readings),
    )


def read_collection(
    collection_path: Path,
    raw_dir: Path,
    reader: SourceReader[Any],
    imported_paths: frozenset[str],
) -> RawReading:
    try:
        if collection_path.is_dir():
            # A folder name is taken whole: a file name without its extension.
            collected_at = parse_collection_name(collection_path.name)
            pages = list_pages(collection_path, raw_dir)
        else:
            collected_at = parse_collection_name(collection_path.stem)
            pages = [collection_path]
    except (ValueError, OSError) as error:
        relative_collection_path = collection_path.relative_to(raw_dir).as_posix()
        return RawReading(
            [],
            [reject(relative_collection_path, f"{type(error).__name__}: {error}")],
            0,
        )
    return join_readings(
        [
            read_page(page_path, raw_dir, reader, collected_at)
            for page_path in pages
            if page_path.relative_to(raw_dir).as_posix() not in imported_paths
        ]
    )


def parse_collection_name(collection_name: str) -> datetime:
    return datetime.strptime(collection_name, COLLECTION_NAME_FORMAT).replace(
        tzinfo=UTC
    )


def read_page(
    page_path: Path, raw_dir: Path, reader: SourceReader[Any], collected_at: datetime
) -> RawReading:
    raw_file_path = page_path.relative_to(raw_dir).as_posix()
    try:
        entries = reader.read_entries(page_path.read_bytes())
    except (ValueError, csv.Error, OSError) as error:
        # Not a file read: it is not registered, and is read again at the next import.
        return RawReading(
            [], [reject(raw_file_path, f"{type(error).__name__}: {error}")], 1
        )
    items = []
    rejections = []
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
    raw_file = RawFile(
        raw_file_path, reader.source_code, collected_at, items, len(rejections)
    )
    return RawReading([raw_file], rejections, 1)


def list_collections(
    raw_dir: Path, kinds: Sequence[SourceKind]
) -> list[tuple[Path, SourceReader[Any]]]:
    """Each collection (raw file or folder of pages) with the reader of its kind, found by the
    name of its source folder, whether its source is still tracked or not."""
    collections: list[tuple[Path, SourceReader[Any]]] = []
    for source_dir in sorted((raw_dir / AUTOMATED_WATCH_DIR_NAME).glob("*/")):
        kind = find_source_kind(source_dir.name, kinds)
        if kind is None:
            logger.info("folder without a source kind, skipped: %s", source_dir.name)
            continue
        reader = kind.reader
        if reader is None:
            logger.info("source without a reader, skipped: %s", source_dir.name)
            continue
        collections.extend((path, reader) for path in list_visible_entries(source_dir))
    return collections


def list_pages(collection_dir: Path, raw_dir: Path) -> list[Path]:
    """The files of a collection folder."""
    pages = []
    for path in list_visible_entries(collection_dir):
        if path.is_dir():
            logger.info(
                "folder inside a collection folder, skipped: %s",
                path.relative_to(raw_dir).as_posix(),
            )
            continue
        pages.append(path)
    return pages


def list_visible_entries(folder: Path) -> list[Path]:
    """The entries of a folder in name order, hidden ones left out: they are not raw data
    (.DS_Store written by macOS, for instance)."""
    return sorted(path for path in folder.iterdir() if not path.name.startswith("."))


def reject(raw_file_path: str, reason: str) -> Rejection:
    logger.warning("rejected from %s: %s", raw_file_path, reason)
    return Rejection(raw_file_path, reason)
