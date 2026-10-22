"""Read the raw files of raw/automated_watch/ and raw/selected_library/ not imported yet into
common items (docs/specs-collecte.md, step 2), then reject the releases of a repository out of
the tracked list (docs/stockage.md) and normalize the items kept (step 3).

The raw files of a source whose kind carries a trend reader (GH Archive) are read beside them,
by the same walk of raw/: their rows are not items (ADR of 2026-10-08).
"""

import csv
import logging
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple

from pydantic import ValidationError

from k_b.core.config import TrackedRepository
from k_b.core.quoting import quote_value, without_values
from k_b.etl.normalize import normalize_item
from k_b.etl.raw_files import (
    RawFile,
    RawReading,
    Rejection,
    TrendFile,
    TrendReading,
    parse_collection_name,
)
from k_b.etl.raw_store import RAW_DIR_NAMES
from k_b.etl.source_contract import (
    SourceKind,
    SourceReader,
    TrendReader,
    find_source_kind,
)
from k_b.items import Item

logger = logging.getLogger(__name__)


class RawReadings(NamedTuple):
    """What one walk of raw/ gives the import: the files read as items, and those read as
    trends."""

    items: RawReading
    trends: TrendReading


class Collections(NamedTuple):
    """The collections of raw/ with the reader each one is read by: as items (a raw file, or a
    folder of pages), or as trends."""

    of_items: list[tuple[Path, SourceReader[Any]]]
    of_trends: list[tuple[Path, TrendReader]]


def read_raw_files(
    raw_dir: Path,
    kinds: Sequence[SourceKind],
    imported_paths: frozenset[str],
    tracked_repositories: Sequence[TrackedRepository],
) -> RawReadings:
    """Every raw file not in imported_paths read as its kind says, from one walk of raw/: each
    source folder is listed once, and the reader of its kind says what its files hold."""
    collections = list_collections(raw_dir, kinds)
    return RawReadings(
        read_raw_items(
            collections.of_items, raw_dir, imported_paths, tracked_repositories
        ),
        read_raw_trends(collections.of_trends, raw_dir, imported_paths),
    )


def read_raw_items(
    collections: list[tuple[Path, SourceReader[Any]]],
    raw_dir: Path,
    imported_paths: frozenset[str],
    tracked_repositories: Sequence[TrackedRepository],
) -> RawReading:
    """Every collection of items that is not in imported_paths, in collection order, without
    the releases of a repository out of tracked_repositories, each item kept normalized.

    A collection is a raw file, or a folder of pages; a raw file is read as a single page. A
    collection not named by its time or that cannot be listed, a page that cannot be read, or
    an entry rejected by its reader or refused as an item, is rejected and logged; the others
    are still read. A page
    already imported is not opened.
    """
    reading = join_readings(
        [
            read_collection(collection_path, raw_dir, reader, imported_paths)
            for collection_path, reader in collections
        ]
    )
    # Stable sort: within a collection, the files keep their page order.
    reading.files.sort(key=lambda raw_file: raw_file.collected_at)
    # The filter first: it reads each item as its source gave it.
    kept = reject_untracked_releases(reading, tracked_repositories)
    return normalize_items(kept)


def join_readings(readings: list[RawReading]) -> RawReading:
    return RawReading(
        [raw_file for reading in readings for raw_file in reading.files],
        [rejection for reading in readings for rejection in reading.rejections],
        sum(reading.read_count for reading in readings),
    )


def reject_untracked_releases(
    reading: RawReading, tracked_repositories: Sequence[TrackedRepository]
) -> RawReading:
    """The same reading, without the releases of a repository out of the list, each one
    rejected.

    The import goes on, as for an entry refused when read. A file keeps its place even with no
    item left: the import registers it, and only a rebuild of the base reads it again (#106).
    """
    tracked_names = {repository.name.lower() for repository in tracked_repositories}
    files: list[RawFile] = []
    rejections = list(reading.rejections)
    for raw_file in reading.files:
        kept: list[Item] = []
        for item in raw_file.items:
            if is_untracked_release(item, tracked_names):
                rejections.append(
                    reject(
                        item.raw_file_path,
                        f"repository not in the tracked list: {item.repository_name}",
                    )
                )
                continue
            kept.append(item)
        # A release left out does not count in rejection_count, which stays the entries its
        # reader rejected or the item refused (raw_files.py): it was read whole, and no state
        # catalog holds a release, so no withdrawal depends on it (decision of Sabine of
        # 2026-10-22).
        files.append(raw_file._replace(items=kept))
    return RawReading(files, rejections, reading.read_count)


def is_untracked_release(item: Item, tracked_names: set[str]) -> bool:
    """Whether the item is a release of a repository out of the tracked list."""
    # A release always has its repository (items.py): str() only satisfies the typing.
    return (
        item.kind == "release"
        and str(item.repository_name).lower() not in tracked_names
    )


def normalize_items(reading: RawReading) -> RawReading:
    """The same reading, each item of each file normalized (etl/normalize.py).

    Outside the reading of a page, which turns a ValidationError into a rejection: the second
    validation of normalize_item must stop the whole import, not reject one item. An item
    refuses beforehand what the normalization would break (check_url_can_be_normalized,
    items.py).
    """
    return reading._replace(
        files=[
            raw_file._replace(items=[normalize_item(item) for item in raw_file.items])
            for raw_file in reading.files
        ]
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


def read_page(
    page_path: Path, raw_dir: Path, reader: SourceReader[Any], collected_at: datetime
) -> RawReading:
    raw_file_path = page_path.relative_to(raw_dir).as_posix()
    try:
        entry_reading = reader.read_entries(page_path.read_bytes())
    # RecursionError: a JSON nested too deep (#103); the page alone is rejected.
    except (ValueError, csv.Error, OSError, RecursionError) as error:
        # Not a file read: it is not registered, and is read again at the next import.
        return RawReading(
            [], [reject(raw_file_path, f"{type(error).__name__}: {error}")], 1
        )
    items = []
    rejections = [
        reject(raw_file_path, reason) for reason in entry_reading.rejection_reasons
    ]
    # The position counts the entries read: those rejected by the reader are not.
    for position, entry in enumerate(entry_reading.entries):
        try:
            items.append(reader.convert(entry, collected_at, raw_file_path))
        except ValidationError as error:
            rejections.append(
                reject(
                    raw_file_path,
                    f"read entry {position}: {type(error).__name__}: "
                    f"{without_values(error)}",
                )
            )
    raw_file = RawFile(
        raw_file_path, reader.source_code, collected_at, items, len(rejections)
    )
    return RawReading([raw_file], rejections, 1)


def read_raw_trends(
    collections: list[tuple[Path, TrendReader]],
    raw_dir: Path,
    imported_paths: frozenset[str],
) -> TrendReading:
    """Every raw file of trends that is not in imported_paths, in collection order, each read as
    a whole ranking.

    As for the items: a file not named by its collection time is rejected without being opened;
    a file that cannot be read, or that its reader refuses, is rejected and counted as opened. A
    rejected file is not registered: the next import reads it again. A file already imported is
    not opened. Unlike a collection of items, a folder is not a collection of pages: the source
    writes one file per collection, and a folder is rejected without being opened, its path left
    out of the reason.
    """
    files: list[TrendFile] = []
    rejections: list[Rejection] = []
    read_count = 0
    # A raw file is named by its collection time: the order of the names is the order of time.
    for path, reader in collections:
        raw_file_path = path.relative_to(raw_dir).as_posix()
        if raw_file_path in imported_paths:
            continue
        if path.is_dir():
            rejections.append(reject(raw_file_path, "a folder, not a raw file"))
            continue
        try:
            collected_at = parse_collection_name(path.stem)
        except ValueError as error:
            rejections.append(reject(raw_file_path, f"{type(error).__name__}: {error}"))
            continue
        read_count += 1
        try:
            rows = reader.read_rows(path.read_bytes())
        except (ValueError, OSError) as error:
            rejections.append(reject(raw_file_path, f"{type(error).__name__}: {error}"))
            continue
        raw_file = RawFile(raw_file_path, reader.source_code, collected_at, [], 0)
        files.append(TrendFile(raw_file, rows))
    return TrendReading(files, rejections, read_count)


def list_collections(raw_dir: Path, kinds: Sequence[SourceKind]) -> Collections:
    """Each collection with the reader it is read by, that of its kind, found by the name of its
    source folder, whether its source is still tracked or not."""
    of_items: list[tuple[Path, SourceReader[Any]]] = []
    of_trends: list[tuple[Path, TrendReader]] = []
    source_dirs = [
        source_dir
        for raw_dir_name in RAW_DIR_NAMES
        for source_dir in sorted((raw_dir / raw_dir_name).glob("*/"))
    ]
    for source_dir in source_dirs:
        kind = find_source_kind(source_dir.name, kinds)
        if kind is None:
            # The name of a folder of raw/ is not checked: it is quoted.
            logger.info(
                "folder without a source kind, skipped: %s",
                quote_value(source_dir.name),
            )
            continue
        item_reader = kind.reader
        trend_reader = kind.trend_reader
        # Listed only for a kind that has a reader: a folder left unread is never opened.
        if item_reader is not None:
            of_items.extend(
                (path, item_reader) for path in list_visible_entries(source_dir)
            )
        elif trend_reader is not None:
            of_trends.extend(
                (path, trend_reader) for path in list_visible_entries(source_dir)
            )
        else:
            # The rankings of the two GitHub tops: they do not enter the base (ADR of
            # 2026-10-07), and kb write-tops reads them from raw/.
            logger.info(
                "source without a reader, skipped: %s", quote_value(source_dir.name)
            )
    return Collections(of_items, of_trends)


def list_pages(collection_dir: Path, raw_dir: Path) -> list[Path]:
    """The files of a collection folder."""
    pages = []
    for path in list_visible_entries(collection_dir):
        if path.is_dir():
            logger.info(
                "folder inside a collection folder, skipped: %s",
                quote_value(path.relative_to(raw_dir).as_posix()),
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
