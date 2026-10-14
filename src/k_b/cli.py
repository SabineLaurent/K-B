"""Command line: `kb collect`, `kb create-db`, `kb import`."""

import argparse
import logging
import os
import sqlite3
import sys
import time
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from k_b.core.config import LOG_FILES_KEPT
from k_b.database.connection import DATABASE_FILE_NAME, MissingDatabaseError
from k_b.database.creation import create_database
from k_b.database.dates import DATABASE_DATE_FORMAT
from k_b.database.writers.shared_rows import UnknownSourceError
from k_b.etl.extract import collect_all_sources
from k_b.etl.load import (
    ImportLogExistsError,
    KindWithoutTableError,
    import_items,
    read_imported_paths,
)
from k_b.etl.raw_store import InvalidCollectionStateError
from k_b.etl.source_contract import list_sources
from k_b.etl.source_kinds import SOURCE_KINDS
from k_b.etl.sources.gh_archive import FOLDER_PREFIX as GH_ARCHIVE_SOURCE_NAME
from k_b.etl.sources.gh_archive import (
    GhArchiveSource,
    create_bigquery_client,
    read_trend_files,
)
from k_b.etl.sources.tracked_repositories import TRACKED_REPOSITORIES
from k_b.etl.sources.zotero import FOLDER_PREFIX as ZOTERO_SOURCE_NAME
from k_b.etl.sources.zotero import ZoteroSource
from k_b.etl.transform import COLLECTION_NAME_FORMAT, read_raw_items

logger = logging.getLogger(__name__)

DATA_DIR_VARIABLE = "KB_DATA_DIR"
# The Zotero data directory, the one that holds zotero.sqlite. Not set: Zotero is skipped.
ZOTERO_DIR_VARIABLE = "KB_ZOTERO_DIR"
# The path of the BigQuery service account key, read by the client. Not set: GH Archive is skipped.
BIGQUERY_KEY_VARIABLE = "GOOGLE_APPLICATION_CREDENTIALS"
# One log per import, named by its second as a raw file by its collection: never rewritten.
IMPORT_LOG_FILE_NAME = "import-log-{imported_at}.jsonl"


# The log of every run, successes and failures, apart from the import logs: those are written
# only when an import reaches the end of its writing in the base.
LOG_FILE_PATH = Path("logs") / "kb.log"
LOG_LINE_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


@contextmanager
def logging_to(data_dir: Path) -> Iterator[None]:
    """Log every line of level INFO and above on stderr and in logs/kb.log of the data
    directory, dated in UTC in the format of the base (2026-10-14T11:30:00Z); the file turns
    at midnight UTC into kb.log.<day>.

    Raises OSError when the log file cannot be opened. On exit the handlers are closed and
    removed: the tests run kb many times in the interpreter of pytest.
    """
    log_path = data_dir / LOG_FILE_PATH
    log_path.parent.mkdir(exist_ok=True)
    file_handler = TimedRotatingFileHandler(
        log_path,
        when="midnight",
        utc=True,
        backupCount=LOG_FILES_KEPT,
        encoding="utf-8",
    )
    formatter = logging.Formatter(LOG_LINE_FORMAT, datefmt=DATABASE_DATE_FORMAT)
    # The Z of the format says UTC: the time is read in UTC, not in local time.
    formatter.converter = time.gmtime
    handlers: list[logging.Handler] = [logging.StreamHandler(), file_handler]
    root_logger = logging.getLogger()
    previous_level = root_logger.level
    for handler in handlers:
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
    try:
        yield
    except Exception:
        # Written while the handlers are there: the traceback Python prints next is not in
        # the file.
        logger.exception("kb stopped by an exception it does not handle")
        raise
    finally:
        root_logger.setLevel(previous_level)
        for handler in handlers:
            root_logger.removeHandler(handler)
            handler.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kb")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "collect", help="run every source and store its raw output in raw/"
    )
    commands.add_parser(
        "create-db", help=f"create the items database, {DATABASE_FILE_NAME}"
    )
    commands.add_parser(
        "import",
        help="read the raw items and write them into the database, which removes the duplicates",
    )
    arguments = parser.parse_args(argv)

    data_dir = read_data_dir()
    if data_dir is None:
        return 2
    with ExitStack() as log_stack:
        try:
            log_stack.enter_context(logging_to(data_dir))
        except OSError as error:
            # A run without its log would lose the failures the log is kept for: none is run.
            print(
                f"error: log file not opened: {type(error).__name__}: {error}",
                file=sys.stderr,
            )
            return 2
        return run_command(arguments.command, data_dir)


def run_command(command: str, data_dir: Path) -> int:
    if command == "create-db":
        return run_create_db(data_dir)
    if command == "import":
        return run_import(data_dir)
    return run_collect(data_dir)


def read_data_dir() -> Path | None:
    """The data directory, or None after printing why it cannot be used."""
    data_dir = os.environ.get(DATA_DIR_VARIABLE)
    if not data_dir:
        print(
            f"error: {DATA_DIR_VARIABLE} must point to the data directory",
            file=sys.stderr,
        )
        return None
    if not Path(data_dir).is_dir():
        print(
            f"error: {DATA_DIR_VARIABLE} is not an existing directory", file=sys.stderr
        )
        return None
    return Path(data_dir)


def run_create_db(data_dir: Path) -> int:
    database_path = data_dir / DATABASE_FILE_NAME
    try:
        create_database(database_path)
    except FileExistsError as error:
        logger.error("%s", error)
        return 2
    except (sqlite3.Error, OSError) as error:
        logger.error("%s: %s: %s", database_path, type(error).__name__, error)
        return 1
    print(f"database created: {database_path}")
    return 0


def run_import(data_dir: Path) -> int:
    """Read the registry of the base, then the raw files not in it (the items, then the
    rankings of GH Archive), then write the base."""
    database_path = data_dir / DATABASE_FILE_NAME
    imported_at = datetime.now(UTC).replace(microsecond=0)
    log_path = data_dir / IMPORT_LOG_FILE_NAME.format(
        imported_at=imported_at.strftime(COLLECTION_NAME_FORMAT)
    )
    try:
        imported_paths = read_imported_paths(database_path)
        reading = read_raw_items(data_dir / "raw", SOURCE_KINDS, imported_paths)
        trend_reading = read_trend_files(data_dir / "raw", imported_paths)
        summary = import_items(
            reading,
            trend_reading,
            database_path,
            log_path,
            imported_at,
            TRACKED_REPOSITORIES,
        )
    except MissingDatabaseError as error:
        logger.error("%s; create it with kb create-db", error)
        return 2
    except ImportLogExistsError as error:
        logger.error("%s; run kb import again", error)
        return 2
    except (
        sqlite3.Error,
        OSError,
        UnknownSourceError,
        KindWithoutTableError,
    ) as error:
        logger.error("%s: %s", type(error).__name__, error)
        return 1
    print(f"raw files read: {summary.read_count}")
    print(f"items written (new or updated): {summary.item_count}")
    print(f"trend rows written: {summary.trend_count}")
    print(
        "items and trend windows left out (duplicates or versions not newer):"
        f" {summary.discard_count}"
    )
    print(
        "rows withdrawn (vulnerabilities, Zotero entries, highlights):"
        f" {summary.withdrawn_count}"
    )
    print(f"rejections: {summary.rejection_count}")
    print(f"log: {log_path}")
    return 0


def run_collect(data_dir: Path) -> int:
    sources = list_sources(SOURCE_KINDS)
    zotero_dir = os.environ.get(ZOTERO_DIR_VARIABLE)
    if zotero_dir:
        sources.append(ZoteroSource(Path(zotero_dir)))
    bigquery_key = os.environ.get(BIGQUERY_KEY_VARIABLE)
    if bigquery_key:
        sources.append(GhArchiveSource(create_bigquery_client))
    try:
        outcome = collect_all_sources(
            sources,
            data_dir / "raw",
            data_dir,
            datetime.now(UTC),
        )
    except InvalidCollectionStateError as error:
        logger.error("%s", error)
        return 2
    for source_name, source_error in outcome.errors_by_source.items():
        print(f"{source_name}: {describe_outcome(source_error)}")
    if not zotero_dir:
        print(f"{ZOTERO_SOURCE_NAME}: skipped ({ZOTERO_DIR_VARIABLE} not set)")
    if not bigquery_key:
        print(f"{GH_ARCHIVE_SOURCE_NAME}: skipped ({BIGQUERY_KEY_VARIABLE} not set)")
    if outcome.state_error is not None:
        print(f"collection_state: {describe_outcome(outcome.state_error)}")
    has_failure = outcome.state_error is not None or any(
        error is not None for error in outcome.errors_by_source.values()
    )
    return 1 if has_failure else 0


def describe_outcome(error: Exception | None) -> str:
    return "ok" if error is None else f"failed ({type(error).__name__})"
