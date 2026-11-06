"""Import the raw files not imported yet into the items database, in one transaction with the journal
of the import.

An entry the base refuses becomes a rejection and the import goes on; any other error writes
nothing in the base and leaves no journal."""

import logging
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from k_b.core.config import TrackedRepository
from k_b.core.quoting import quote_value
from k_b.database.engine import (
    Connection,
    connect_database,
    is_commit_finished_before_a_signal,
    lock_for_writing,
)
from k_b.database.errors import ENGINE_ERRORS
from k_b.database.location import DatabaseLocation, check_database_exists
from k_b.database.reading import read_raw_file_paths
from k_b.database.writing import write_tracked_repositories
from k_b.etl.file_writing import FileWriting, write_file
from k_b.etl.import_journal import write_import_journal
from k_b.etl.raw_files import RawFile, RawReading, TrendFile, TrendReading

logger = logging.getLogger(__name__)


class ImportJournalExistsError(FileExistsError):
    """The journal of this second is already written: the journal of an import is never rewritten."""


class ImportSummary(NamedTuple):
    """The counts of an import, as printed on its summary line."""

    item_count: int
    # The items and the windows of trends left out.
    discard_count: int
    rejection_count: int
    # The raw files opened, files of trends included.
    read_count: int
    withdrawn_count: int
    # The rows written to the trend table.
    trend_count: int


def read_imported_paths(database: DatabaseLocation) -> frozenset[str]:
    """Read the paths of the raw files already imported, from the registry of the database."""
    check_database_exists(database)
    connection = connect_database(database)
    try:
        return read_raw_file_paths(connection)
    finally:
        connection.close()


def import_items(
    reading: RawReading,
    trend_reading: TrendReading,
    database: DatabaseLocation,
    journal_path: Path,
    imported_at: datetime,
    tracked_repositories: Sequence[TrackedRepository],
) -> ImportSummary:
    """Write the tracked repositories, each file read and the journal, in one transaction; files of
    items and of trends in collection order, so that a rebuilt base registers them in the same
    order. The lock of the writers is taken first: on PostgreSQL, two imports write one after the
    other, as behind the write lock of SQLite."""
    check_database_exists(database)
    connection = connect_database(database)
    try:
        try:
            lock_for_writing(connection)
            write_tracked_repositories(connection, tracked_repositories)
            writing = write_files(connection, reading, trend_reading)
            commit_with_journal(connection, journal_path, imported_at, writing)
        except BaseException:
            # BaseException: Ctrl-C must not leave half an import either. Only an open
            # transaction: a connection psycopg closed on a signal refuses the rollback, whose
            # error would replace the signal (exit 1 instead of 143).
            if connection.in_transaction:
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
    connection: Connection, reading: RawReading, trend_reading: TrendReading
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


def commit_with_journal(
    connection: Connection,
    journal_path: Path,
    imported_at: datetime,
    writing: FileWriting,
) -> None:
    """Write the journal, then commit: a file registered is not read again, so its journal must not be
    lost. A failed commit, or an interruption before it, removes the journal; an interruption
    (Ctrl-C, SIGTERM) once the base has committed keeps the import and its journal, as one during
    the commit on PostgreSQL, whose outcome kb does not know."""
    # Checked once the base holds the write lock: two imports of the same second cannot both
    # find no journal.
    check_journal_absent(journal_path)
    try:
        write_import_journal(
            journal_path,
            imported_at,
            writing.rejections,
            writing.discards,
            writing.trend_discards,
        )
        connection.commit()
    except BaseException as error:
        # The journal goes with the import it describes. A commit that fails raises an error of
        # the engine, whether the base keeps the transaction or undoes it itself. A Ctrl-C or a
        # SIGTERM received before the commit finds the transaction open. Each line names the
        # journal, not its path: quote_value cuts a long path before the name.
        if isinstance(error, ENGINE_ERRORS) or connection.in_transaction:
            # The journal at journal_path can only be this import's: it was absent above.
            journal_path.unlink(missing_ok=True)
        elif is_commit_finished_before_a_signal(connection):
            logger.info(
                "import committed, journal kept: %s", quote_value(journal_path.name)
            )
        else:
            # On the signal, psycopg asks the server to cancel COMMIT: the server may have
            # committed the import all the same, or undone it. The journal is kept: if undone, the next import reads the files again and
            # writes a second journal of the same rejections, which costs less than an import
            # committed without its journal (family of #302).
            logger.info(
                "import commit interrupted, outcome unknown, journal kept: %s",
                quote_value(journal_path.name),
            )
        raise


def check_journal_absent(journal_path: Path) -> None:
    """Refuse to import when the import journal of this second already exists."""
    if journal_path.exists():
        raise ImportJournalExistsError(f"{journal_path} already exists")


def list_files_in_collection_order(
    reading: RawReading, trend_reading: TrendReading
) -> list[RawFile | TrendFile]:
    """The files of items and those of trends, oldest collection first; at the same collection,
    the files of items first (the sort is stable)."""

    def find_collected_at(file_read: RawFile | TrendFile) -> datetime:
        """A file of trends holds its collection time on the raw file it registers."""
        if isinstance(file_read, TrendFile):
            return file_read.raw_file.collected_at
        return file_read.collected_at

    return sorted([*reading.files, *trend_reading.files], key=find_collected_at)


def join_writings(writings: list[FileWriting]) -> FileWriting:
    """The sum of several writings, the discards and the rejections in the order given."""
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
