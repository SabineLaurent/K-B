"""Read every raw file of raw/automation/ into common items (docs/specs-collecte.md, step 2)."""

import csv
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

from pydantic import ValidationError

from k_b.items import Item
from k_b.source import SourceKind, SourceReader, find_source_kind

logger = logging.getLogger(__name__)

# The name collect.py gives every raw file of a collection.
COLLECTION_NAME_FORMAT = "%Y-%m-%dT%H%M%SZ"


class Rejection(NamedTuple):
    raw_file_path: str
    reason: str


class RawReading(NamedTuple):
    items: list[Item]
    rejections: list[Rejection]


def read_raw_items(raw_dir: Path, kinds: Sequence[SourceKind]) -> RawReading:
    """Every item of the raw files whose source kind has a reader, in collection order.

    A file that cannot be read, or an entry refused as an item, is rejected and logged; the
    other files and entries are still read.
    """
    items = []
    rejections = []
    for path, reader in list_raw_files(raw_dir, kinds):
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


def list_raw_files(
    raw_dir: Path, kinds: Sequence[SourceKind]
) -> list[tuple[Path, SourceReader[Any]]]:
    """Each raw file with the reader of its kind, found by the name of its folder, whether its
    source is still tracked or not."""
    raw_files: list[tuple[Path, SourceReader[Any]]] = []
    for source_dir in sorted((raw_dir / "automation").glob("*/")):
        kind = find_source_kind(source_dir.name, kinds)
        if kind is None:
            logger.info("folder without a source kind, skipped: %s", source_dir.name)
            continue
        reader = kind.reader
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
    return raw_files


def reject(raw_file_path: str, reason: str) -> Rejection:
    logger.warning("rejected from %s: %s", raw_file_path, reason)
    return Rejection(raw_file_path, reason)
