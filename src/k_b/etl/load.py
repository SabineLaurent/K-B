"""Import the raw files not imported yet into the items database (docs/specs-collecte.md,
step 4).

The registry of the files already imported is raw_data, read before the raw. The files read,
their items and the log of the import are then written in one transaction. Each item, and each
file of trends, is written in its savepoint (database/savepoint.py): an entry the base refuses is
undone alone and becomes a rejection of the log, and the import goes on. Any other error writes
nothing in the base, and leaves no log; an interruption (Ctrl-C, SIGTERM) received once the base
has committed keeps the import and its log. A file registered is not read again, except by a
rebuild of the base.

The base removes the duplicates. The writer of each kind (database/writers/, chosen by
database/writing.py) holds, in its SQL, the rule of the nature of its source: a news feed keeps
the first version seen; a state catalog keeps the version of its latest collection; a feed with
revisions keeps the newest revision. An item left out is returned with its rule and the date
it was compared with, then written to the log. Run again on the same raw, the import gives the
same base.

A file of trends of GH Archive is not made of items: its rows go to the trend table, in the same
transaction, and its rule is a news feed applied to the whole window. A Zotero entry is a state
catalog, as CISA KEV, and so is each of its highlights (decision of 2026-10-13). A clip is
known by its URL, and keeps its latest version: a clip whose content changed is written again
(decision of 2026-10-19).

Only exact duplicates are found: the same identifier within its source (a replay, collections
that overlap). The same content under another identifier is not found, a written limit without
a content fingerprint: for TLDR, another URL or another edition (decision of 2026-10-12); for
Zotero, another key, though two entries of the same arXiv paper point to the same publication
(decision of 2026-10-13); for a clip, another URL (ADR, "Collecte : clips";
docs/specs-collecte.md).
"""

import logging
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from k_b.core.config import TrackedRepository
from k_b.core.quoting import quote_value
from k_b.database.connection import check_database_exists, connect_database
from k_b.database.reading import read_raw_file_paths
from k_b.database.savepoint import EntryRefusedError, write_in_savepoint
from k_b.database.writing import (
    Discard,
    write_item,
    write_raw_data,
    write_tracked_repositories,
    write_trend_rows,
)
from k_b.etl.import_log import TrendDiscard, write_import_log
from k_b.etl.raw_files import (
    RawFile,
    RawReading,
    Rejection,
    TrendFile,
    TrendReading,
)
from k_b.etl.raw_store import find_stream
from k_b.etl.rejections import reject
from k_b.etl.withdrawals import (
    mark_withdrawn_vulnerabilities,
    mark_withdrawn_zotero_rows,
)
from k_b.items import Item

logger = logging.getLogger(__name__)


class ImportLogExistsError(FileExistsError):
    """The log of this second is already written: the log of an import is never rewritten."""


class ImportSummary(NamedTuple):
    item_count: int
    # The items and the windows of trends left out.
    discard_count: int
    rejection_count: int
    # The raw files opened, files of trends included.
    read_count: int
    withdrawn_count: int
    # The rows written to the trend table.
    trend_count: int


@dataclass(frozen=True)
class FileWriting:
    """What the writing of files gave: one file, or the sum of several.

    Every field has its empty value by default, so that a site names only what it produced.
    default_factory, not [], and so a dataclass and not a NamedTuple: the default of a
    NamedTuple is built once, at the creation of the class, and every instance that omits the
    field shares that one list.
    """

    item_count: int = 0
    discards: list[Discard] = field(default_factory=list)
    trend_discards: list[TrendDiscard] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)
    withdrawn_count: int = 0
    trend_count: int = 0


def read_imported_paths(database_path: Path) -> frozenset[str]:
    """The raw files already imported, from the registry of the base."""
    check_database_exists(database_path)
    connection = connect_database(database_path)
    try:
        return read_raw_file_paths(connection)
    finally:
        connection.close()


def import_items(
    reading: RawReading,
    trend_reading: TrendReading,
    database_path: Path,
    log_path: Path,
    imported_at: datetime,
    tracked_repositories: Sequence[TrackedRepository],
) -> ImportSummary:
    """Write the tracked repositories, each file read with its items or its trends into the
    base, then the log of what was left out, all in one transaction.

    The files of items and those of trends are written in one sequence, in collection order: a
    base rebuilt registers them in the order the imports did.
    """
    check_database_exists(database_path)
    connection = connect_database(database_path)
    try:
        try:
            write_tracked_repositories(connection, tracked_repositories)
            writing = write_files(connection, reading, trend_reading)
            commit_with_log(connection, log_path, imported_at, writing)
        except BaseException:
            # BaseException: Ctrl-C must not leave half an import either.
            connection.rollback()
            raise
    finally:
        connection.close()
    return ImportSummary(
        writing.item_count,
        len(writing.discards) + len(writing.trend_discards),
        len(writing.rejections),
        reading.read_count + trend_reading.read_count,
        writing.withdrawn_count,
        writing.trend_count,
    )


def write_files(
    connection: sqlite3.Connection, reading: RawReading, trend_reading: TrendReading
) -> FileWriting:
    """Write each file in collection order; what the reading rejected comes first."""
    rejected_when_read = FileWriting(
        rejections=[*reading.rejections, *trend_reading.rejections]
    )
    return join_writings(
        [
            rejected_when_read,
            *(
                write_file(connection, file_read)
                for file_read in list_files_in_collection_order(reading, trend_reading)
            ),
        ]
    )


def commit_with_log(
    connection: sqlite3.Connection,
    log_path: Path,
    imported_at: datetime,
    writing: FileWriting,
) -> None:
    """Write the log, then commit.

    The log is written before the commit: a file registered is not read again, its log must
    not be lost. A commit that fails, or an interruption before the commit, removes the log
    written; an interruption once the base has committed keeps it.
    """
    # Checked once the base holds the write lock: two imports of the same second cannot both
    # find no log.
    check_log_absent(log_path)
    try:
        write_import_log(
            log_path,
            imported_at,
            writing.rejections,
            writing.discards,
            writing.trend_discards,
        )
        connection.commit()
    except BaseException as error:
        # The log goes with the import it describes. A commit that fails raises a sqlite3.Error,
        # whether SQLite keeps the transaction or undoes it itself. A Ctrl-C or a SIGTERM
        # received before the commit finds the transaction open; one received during the commit
        # is raised by Python once the commit has returned, with no transaction left.
        if isinstance(error, sqlite3.Error) or connection.in_transaction:
            # The log at log_path can only be this import's: it was absent above.
            log_path.unlink(missing_ok=True)
        else:
            # The name, not the path: quote_value cuts a long path before the name.
            logger.info("import committed, log kept: %s", quote_value(log_path.name))
        raise


def check_log_absent(log_path: Path) -> None:
    """The log of an import is never rewritten: one already at log_path stops the import."""
    if log_path.exists():
        raise ImportLogExistsError(f"{log_path} already exists")


def list_files_in_collection_order(
    reading: RawReading, trend_reading: TrendReading
) -> list[RawFile | TrendFile]:
    """The files of items and those of trends, oldest collection first; at the same collection,
    the files of items first, in their reading order (the sort is stable)."""

    def find_collected_at(file_read: RawFile | TrendFile) -> datetime:
        """The collection time of either kind of file: a file of trends holds it on the raw
        file it registers, not on itself."""
        if isinstance(file_read, TrendFile):
            return file_read.raw_file.collected_at
        return file_read.collected_at

    return sorted([*reading.files, *trend_reading.files], key=find_collected_at)


def join_writings(writings: list[FileWriting]) -> FileWriting:
    """The sum of several writings: the counts added, the discards and the rejections kept in
    the order given."""
    return FileWriting(
        item_count=sum(writing.item_count for writing in writings),
        discards=[discard for writing in writings for discard in writing.discards],
        trend_discards=[
            discard for writing in writings for discard in writing.trend_discards
        ],
        rejections=[
            rejection for writing in writings for rejection in writing.rejections
        ],
        withdrawn_count=sum(writing.withdrawn_count for writing in writings),
        trend_count=sum(writing.trend_count for writing in writings),
    )


def write_file(
    connection: sqlite3.Connection, file_read: RawFile | TrendFile
) -> FileWriting:
    """Write one file read, as what it holds says: a file of trends whole, a file of items item
    by item."""
    if isinstance(file_read, TrendFile):
        return write_trend_file(connection, file_read)
    return write_items_file(connection, file_read)


def write_items_file(connection: sqlite3.Connection, raw_file: RawFile) -> FileWriting:
    """Register the file read, write each of its items, then mark as withdrawn what its
    catalog no longer lists.

    Its items are those the reading kept, normalized: the releases of a repository out of the
    tracked list are rejected, and each item kept is normalized, before (etl/transform.py). The
    file is registered even with an item the base refuses, as with an entry rejected when read:
    only a rebuild of the base reads it again.
    """
    raw_data_id = register_raw_file(connection, raw_file)
    outcomes = [
        write_item_in_savepoint(connection, item, raw_data_id)
        for item in raw_file.items
    ]
    discards = [outcome for outcome in outcomes if isinstance(outcome, Discard)]
    refusals = [outcome for outcome in outcomes if isinstance(outcome, Rejection)]
    # An item the base refuses is in its file: a catalog with one withdraws nothing.
    counted_file = raw_file._replace(
        rejection_count=raw_file.rejection_count + len(refusals)
    )
    withdrawn_count = mark_withdrawn_vulnerabilities(
        connection, counted_file, raw_data_id
    ) + mark_withdrawn_zotero_rows(connection, counted_file, raw_data_id)
    return FileWriting(
        item_count=outcomes.count(None),
        discards=discards,
        rejections=refusals,
        withdrawn_count=withdrawn_count,
    )


def write_trend_file(
    connection: sqlite3.Connection, trend_file: TrendFile
) -> FileWriting:
    """Register the file of trends and write its rows in one savepoint; return how many were
    written, and each window the base left out.

    A file of trends with a row the base refuses is refused whole (decision of Sabine of
    2026-10-13): none of its rows is written, it is not registered, and the next import reads it
    again, as an unreadable file.
    """
    raw_file_path = trend_file.raw_file.raw_file_path
    try:
        with write_in_savepoint(connection):
            raw_data_id = register_raw_file(connection, trend_file.raw_file)
            written_count, collected_at_by_window_left_out = write_trend_rows(
                connection, trend_file.rows, raw_data_id
            )
    except EntryRefusedError as refusal:
        rejection = reject(raw_file_path, f"ranking refused by the base: {refusal}")
        return FileWriting(rejections=[rejection])
    discards = [
        TrendDiscard(trend_file.raw_file, window_end, collected_at)
        for window_end, collected_at in collected_at_by_window_left_out.items()
    ]
    return FileWriting(trend_discards=discards, trend_count=written_count)


def register_raw_file(connection: sqlite3.Connection, raw_file: RawFile) -> int:
    """Register the file read under its stream, the name of its source folder."""
    return write_raw_data(
        connection,
        raw_file.source_code,
        raw_file.raw_file_path,
        find_stream(raw_file.raw_file_path),
        raw_file.collected_at,
    )


def write_item_in_savepoint(
    connection: sqlite3.Connection, item: Item, raw_data_id: int
) -> Discard | Rejection | None:
    """Write the item in its savepoint; an item the base refuses is undone alone and returned
    as a rejection, an item it left out as a discard.

    A Zotero entry, its highlights and the publication it cites are written by one writer:
    they share the savepoint.
    """
    try:
        with write_in_savepoint(connection):
            return write_item(connection, item, raw_data_id)
    except EntryRefusedError as refusal:
        return reject(
            item.raw_file_path,
            f"{item.kind} {quote_value(item.source_item_id)} refused by the base: "
            f"{refusal}",
        )
