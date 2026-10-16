"""Import the raw files not imported yet into the items database (docs/specs-collecte.md,
step 4).

The registry of the files already imported is raw_data, read before the raw. The files read,
their items and the log of the import are then written in one transaction. Each item, and each
ranking, is written in its savepoint (database/savepoint.py): an entry the base refuses is
undone alone and becomes a rejection of the log, and the import goes on. Any other error writes
nothing in the base, and leaves no log. A file registered is not read again, except by a
rebuild of the base.

The base removes the duplicates. The writer of each kind (database/writers/) holds, in its
SQL, the rule of the nature of its source: a news feed keeps the first version seen; a state
catalog keeps the version of its latest collection; a feed with revisions keeps the newest
revision. An item left out is returned with its rule and the date it was compared with, then
written to the log. Run again on the same raw, the import gives the same base.

A ranking of GH Archive is not made of items: its rows go to the trend table, in the same
transaction, and its rule is a news feed applied to the whole window. A Zotero entry is a state
catalog, as CISA KEV, and so is each of its highlights (decision of 2026-10-13).

Only exact duplicates are found: the same identifier within its source (a replay, collections
that overlap). The same content under another identifier is not found, a written limit without
a content fingerprint: for TLDR, another URL or another edition (decision of 2026-10-12); for
Zotero, another key, though two entries of the same arXiv paper point to the same publication
(decision of 2026-10-13; docs/specs-collecte.md).
"""

import sqlite3
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from k_b.core.config import TrackedRepository
from k_b.core.quoting import quote_value
from k_b.database.connection import check_database_exists, connect_database
from k_b.database.reading import read_raw_file_paths
from k_b.database.savepoint import (
    ENTRY_REFUSAL_ERRORS,
    describe_refusal,
    write_in_savepoint,
)
from k_b.database.writers import (
    advisory_writer,
    newsletter_article_writer,
    paper_writer,
    release_writer,
    shared_rows,
    trend_writer,
    vulnerability_writer,
    zotero_entry_writer,
)
from k_b.database.writers.discard import Discard
from k_b.etl.import_log import TrendDiscard, write_import_log
from k_b.etl.normalize import normalize_item
from k_b.etl.raw_store import find_stream
from k_b.etl.transform import (
    RawFile,
    RawReading,
    Rejection,
    TrendFile,
    TrendReading,
    reject,
)
from k_b.items import Item


class ImportLogExistsError(FileExistsError):
    """The log of this second is already written: the log of an import is never rewritten."""


class KindWithoutTableError(LookupError):
    """An item's kind has no table in the base yet: the import refuses it."""


class ImportSummary(NamedTuple):
    item_count: int
    # The items and the windows of a ranking left out.
    discard_count: int
    rejection_count: int
    # The raw files opened, rankings included.
    read_count: int
    withdrawn_count: int
    # The rows written to the trend table.
    trend_count: int


def read_imported_paths(database_path: Path) -> frozenset[str]:
    """The raw files already imported, from the registry of the base."""
    check_database_exists(database_path)
    connection = connect_database(database_path)
    try:
        return read_raw_file_paths(connection)
    finally:
        connection.close()


class FileWriting(NamedTuple):
    """What the writing of files gave: one file, or the sum of several."""

    item_count: int
    discards: list[Discard]
    trend_discards: list[TrendDiscard]
    rejections: list[Rejection]
    withdrawn_count: int
    trend_count: int


def import_items(
    reading: RawReading,
    trend_reading: TrendReading,
    database_path: Path,
    log_path: Path,
    imported_at: datetime,
    tracked_repositories: Sequence[TrackedRepository],
) -> ImportSummary:
    """Write the tracked repositories, each file read with its items or its ranking into the
    base, then the log of what was left out, all in one transaction.

    The files of items and the rankings are written in one sequence, in collection order: a
    base rebuilt registers them in the order the imports did.
    """
    check_database_exists(database_path)
    connection = connect_database(database_path)
    try:
        try:
            release_writer.write_tracked_repositories(connection, tracked_repositories)
            writing = write_files(
                connection, reading, trend_reading, tracked_repositories
            )
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
    connection: sqlite3.Connection,
    reading: RawReading,
    trend_reading: TrendReading,
    tracked_repositories: Sequence[TrackedRepository],
) -> FileWriting:
    """Write each file in collection order; what the reading rejected comes first."""
    rejected_when_read = FileWriting(
        0, [], [], [*reading.rejections, *trend_reading.rejections], 0, 0
    )
    return join_writings(
        [
            rejected_when_read,
            *(
                write_file(connection, file_read, tracked_repositories)
                for file_read in list_files_in_collection_order(reading, trend_reading)
            ),
        ]
    )


def join_writings(writings: list[FileWriting]) -> FileWriting:
    return FileWriting(
        sum(writing.item_count for writing in writings),
        [discard for writing in writings for discard in writing.discards],
        [discard for writing in writings for discard in writing.trend_discards],
        [rejection for writing in writings for rejection in writing.rejections],
        sum(writing.withdrawn_count for writing in writings),
        sum(writing.trend_count for writing in writings),
    )


def write_file(
    connection: sqlite3.Connection,
    file_read: RawFile | TrendFile,
    tracked_repositories: Sequence[TrackedRepository],
) -> FileWriting:
    if isinstance(file_read, TrendFile):
        return write_trend_file(connection, file_read)
    return write_items_file(connection, file_read, tracked_repositories)


def commit_with_log(
    connection: sqlite3.Connection,
    log_path: Path,
    imported_at: datetime,
    writing: FileWriting,
) -> None:
    """Write the log, then commit.

    The log is written before the commit: a file registered is not read again, its log must
    not be lost. A commit that fails, or an interruption, removes the log written.
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
    except BaseException:
        # The log at log_path can only be this import's: it was absent above.
        log_path.unlink(missing_ok=True)
        raise


def list_files_in_collection_order(
    reading: RawReading, trend_reading: TrendReading
) -> list[RawFile | TrendFile]:
    """The files of items and the rankings, oldest collection first; at the same collection,
    the files of items first, in their reading order (the sort is stable)."""

    def read_collected_at(file_read: RawFile | TrendFile) -> datetime:
        if isinstance(file_read, TrendFile):
            return file_read.raw_file.collected_at
        return file_read.collected_at

    return sorted([*reading.files, *trend_reading.files], key=read_collected_at)


def reject_untracked_releases(
    items: list[Item], tracked_repositories: Sequence[TrackedRepository]
) -> tuple[list[Item], list[Rejection]]:
    """The items without the releases of a repository out of the list, each one rejected.

    The import goes on, as for an entry refused when read. Their file is registered: only a
    rebuild of the base reads them again.
    """
    tracked_names = {repository.name.lower() for repository in tracked_repositories}
    kept = []
    rejections = []
    for item in items:
        if (
            # A release always has its repository (items.py): str() only satisfies the typing.
            item.kind == "release"
            and str(item.repository_name).lower() not in tracked_names
        ):
            rejections.append(
                reject(
                    item.raw_file_path,
                    f"repository not in the tracked list: {item.repository_name}",
                )
            )
        else:
            kept.append(item)
    return kept, rejections


def write_items_file(
    connection: sqlite3.Connection,
    raw_file: RawFile,
    tracked_repositories: Sequence[TrackedRepository],
) -> FileWriting:
    """Register the file read, write each of its items, then withdraw what its catalog no
    longer lists.

    The file is registered even with an item the base refuses, as with an entry rejected when
    read: only a rebuild of the base reads it again.
    """
    items, untracked = reject_untracked_releases(raw_file.items, tracked_repositories)
    raw_data_id = register_raw_file(connection, raw_file)
    outcomes = [
        write_item_in_savepoint(connection, item, raw_data_id)
        for item in map(normalize_item, items)
    ]
    discards = [outcome for outcome in outcomes if isinstance(outcome, Discard)]
    refusals = [outcome for outcome in outcomes if isinstance(outcome, Rejection)]
    # An item the base refuses is in its file: a catalog with one withdraws nothing.
    counted_file = raw_file._replace(
        rejection_count=raw_file.rejection_count + len(refusals)
    )
    withdrawn_count = withdraw_absent_vulnerabilities(
        connection, counted_file, raw_data_id
    ) + withdraw_absent_zotero_rows(connection, counted_file, raw_data_id)
    return FileWriting(
        outcomes.count(None),
        discards,
        [],
        [*untracked, *refusals],
        withdrawn_count,
        0,
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
    except ENTRY_REFUSAL_ERRORS as error:
        return reject(
            item.raw_file_path,
            f"{item.kind} {quote_value(item.source_item_id)} refused by the base: "
            f"{describe_refusal(error)}",
        )


def write_item(
    connection: sqlite3.Connection, item: Item, raw_data_id: int
) -> Discard | None:
    """Write the item of the raw data raw_data_id, or return why the base left it out."""
    write_kind = WRITER_BY_KIND.get(item.kind)
    if write_kind is None:
        raise KindWithoutTableError(f"kind without a table in the base: {item.kind}")
    return write_kind(connection, item, raw_data_id)


def register_raw_file(connection: sqlite3.Connection, raw_file: RawFile) -> int:
    """Register the file read under its stream, the name of its source folder."""
    return shared_rows.write_raw_data(
        connection,
        raw_file.source_code,
        raw_file.raw_file_path,
        find_stream(raw_file.raw_file_path),
        raw_file.collected_at,
    )


def write_trend_file(
    connection: sqlite3.Connection, trend_file: TrendFile
) -> FileWriting:
    """Register the ranking and write its rows in one savepoint; return how many were written,
    and each window the base left out.

    A ranking with a row the base refuses is refused whole (decision of Sabine of 2026-10-13):
    none of its rows is written, it is not registered, and the next import reads it again, as
    an unreadable file.
    """
    raw_file_path = trend_file.raw_file.raw_file_path
    try:
        with write_in_savepoint(connection):
            raw_data_id = register_raw_file(connection, trend_file.raw_file)
            written_count, collected_at_by_window_left_out = trend_writer.write(
                connection, trend_file.rows, raw_data_id
            )
    except ENTRY_REFUSAL_ERRORS as error:
        rejection = reject(
            raw_file_path, f"ranking refused by the base: {describe_refusal(error)}"
        )
        return FileWriting(0, [], [], [rejection], 0, 0)
    discards = [
        TrendDiscard(trend_file.raw_file, window_end, collected_at)
        for window_end, collected_at in collected_at_by_window_left_out.items()
    ]
    return FileWriting(0, [], discards, [], 0, written_count)


def withdraw_absent_vulnerabilities(
    connection: sqlite3.Connection, raw_file: RawFile, raw_data_id: int
) -> int:
    """Withdraw the CVE a catalog no longer lists (vulnerability_writer.py); return how many.

    Only a file of vulnerabilities, all of its entries read: a rejected row is in the catalog,
    not absent from it.
    """
    present_cve_ids = [
        item.cve
        for item in raw_file.items
        if item.kind == "vulnerability" and item.cve is not None
    ]
    if not present_cve_ids or raw_file.rejection_count:
        return 0
    return vulnerability_writer.withdraw_absent(
        connection,
        raw_file.source_code,
        raw_file.collected_at,
        raw_data_id,
        present_cve_ids,
    )


def withdraw_absent_zotero_rows(
    connection: sqlite3.Connection, raw_file: RawFile, raw_data_id: int
) -> int:
    """Withdraw the entries and the highlights an extract no longer lists
    (zotero_entry_writer.py); return how many.

    The same conditions as for a catalog of CISA KEV: an extract with a rejected entry, or
    without entry, withdraws nothing.
    """
    entries = [item for item in raw_file.items if item.kind == "zotero_entry"]
    if not entries or raw_file.rejection_count:
        return 0
    return zotero_entry_writer.withdraw_absent(
        connection, raw_file.source_code, raw_file.collected_at, raw_data_id, entries
    )


# The kinds that have a table in the base, each with its writer.
WRITER_BY_KIND: dict[str, Callable[[sqlite3.Connection, Item, int], Discard | None]] = {
    "paper": paper_writer.write,
    "vulnerability": vulnerability_writer.write,
    "release": release_writer.write,
    "advisory": advisory_writer.write,
    "newsletter_article": newsletter_article_writer.write,
    "zotero_entry": zotero_entry_writer.write,
}


def check_log_absent(log_path: Path) -> None:
    """The log of an import is never rewritten: one already at log_path stops the import."""
    if log_path.exists():
        raise ImportLogExistsError(f"{log_path} already exists")
