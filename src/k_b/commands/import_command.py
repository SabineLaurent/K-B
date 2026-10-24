"""kb import: read the raw files not imported yet and write them into the database."""

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from k_b.commands.exit_codes import ExitCode
from k_b.commands.run_log import LOGGER_NAME, describe_os_error
from k_b.database.connection import MissingDatabaseError
from k_b.database.writing import KindWithoutTableError, UnknownSourceError
from k_b.etl.pipeline import (
    ImportLogExistsError,
    ImportOutcome,
    import_raw_files,
    purge_superseded_raw,
)
from k_b.etl.raw_store import (
    AUTOMATED_WATCH_DIR_NAME,
    SELECTED_LIBRARY_DIR_NAME,
    make_source_folder_key,
)
from k_b.etl.source_kinds import SOURCE_KINDS
from k_b.etl.sources import cisa_kev, zotero
from k_b.etl.sources.tracked_repositories import TRACKED_REPOSITORIES

logger = logging.getLogger(LOGGER_NAME)

# The state catalogs: of each, only the last raw file imported is kept (ADR of 2026-10-19).
LATEST_ONLY_FOLDER_KEYS = (
    make_source_folder_key(SELECTED_LIBRARY_DIR_NAME, zotero.FOLDER_PREFIX),
    make_source_folder_key(AUTOMATED_WATCH_DIR_NAME, cisa_kev.FOLDER_PREFIX),
)


def run_import(data_dir: Path) -> int:
    """Run the import, print what it wrote, then purge the raw files superseded; after the
    summary, so that a purge that fails leaves the summary of the import committed."""
    imported_at = datetime.now(UTC).replace(microsecond=0)
    try:
        outcome = import_raw_files(
            data_dir, SOURCE_KINDS, TRACKED_REPOSITORIES, imported_at
        )
    except MissingDatabaseError as error:
        logger.error("%s; create it with kb create-db", error)
        return ExitCode.NOT_STARTED
    except ImportLogExistsError as error:
        logger.error("%s; run kb import again", error)
        return ExitCode.NOT_STARTED
    except (
        sqlite3.Error,
        OSError,
        UnknownSourceError,
        KindWithoutTableError,
    ) as error:
        logger.error("%s: %s", type(error).__name__, error)
        return ExitCode.FAILED
    print_import_summary(outcome)
    try:
        deleted_count = purge_superseded_raw(data_dir, LATEST_ONLY_FOLDER_KEYS)
    except (sqlite3.Error, OSError, ValueError) as error:
        # The type, and the reason of an OSError, never the name of a raw file.
        logger.error(
            "import committed, raw purge failed: %s; run kb import again",
            describe_os_error(error)
            if isinstance(error, OSError)
            else type(error).__name__,
        )
        return ExitCode.FAILED
    print(f"superseded raw files deleted: {deleted_count}")
    return ExitCode.SUCCEEDED


def print_import_summary(outcome: ImportOutcome) -> None:
    """What the import wrote, left out and rejected, then where its log details it."""
    summary = outcome.summary
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
    print(f"log: {outcome.log_path}")
