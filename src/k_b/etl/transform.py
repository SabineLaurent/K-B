"""Read the raw files of raw/automated_watch/ and raw/selected_library/ not imported yet into
common items (docs/specs-collecte.md, step 2), then reject the releases of a repository out of
the tracked list (docs/stockage.md) and normalize the items kept (step 3)."""

import csv
import logging
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from k_b.core.config import TrackedRepository
from k_b.core.quoting import quote_value, without_values
from k_b.etl.normalize import normalize_item
from k_b.etl.raw_files import RawFile, RawReading, Rejection, parse_collection_name
from k_b.etl.raw_store import RAW_DIR_NAMES
from k_b.etl.source_contract import SourceKind, SourceReader, find_source_kind
from k_b.items import Item

logger = logging.getLogger(__name__)


def read_raw_items(
    raw_dir: Path,
    kinds: Sequence[SourceKind],
    imported_paths: frozenset[str],
    tracked_repositories: Sequence[TrackedRepository],
) -> RawReading:
    """Every raw file whose source kind has a reader and that is not in imported_paths, in
    collection order, without the releases of a repository out of tracked_repositories, each
    item kept normalized.

    A collection is a raw file, or a folder of pages; a raw file is read as a single page. A
    collection not named by its time or that cannot be listed, a page that cannot be read, or
    an entry rejected by its reader or refused as an item, is rejected and logged; the others
    are still read. A page
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


def list_collections(
    raw_dir: Path, kinds: Sequence[SourceKind]
) -> list[tuple[Path, SourceReader[Any]]]:
    """Each collection (raw file or folder of pages) with the reader of its kind, found by the
    name of its source folder, whether its source is still tracked or not."""
    collections: list[tuple[Path, SourceReader[Any]]] = []
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
        reader = kind.reader
        if reader is None:
            # Not always left unread: the rankings of GH Archive, which are not items, have
            # their own reader (etl/sources/gh_archive.py).
            logger.info(
                "source without a reader of items, skipped by the item reader: %s",
                quote_value(source_dir.name),
            )
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
