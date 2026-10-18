"""kb import: read the raw files not imported yet and write them into the database."""

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from k_b.commands.exit_codes import ExitCode
from k_b.commands.run_log import LOGGER_NAME
from k_b.database.connection import DATABASE_FILE_NAME, MissingDatabaseError
from k_b.database.writers.shared_rows import UnknownSourceError
from k_b.etl.load import (
    ImportLogExistsError,
    KindWithoutTableError,
    import_items,
    read_imported_paths,
)
from k_b.etl.source_kinds import SOURCE_KINDS
from k_b.etl.sources.gh_archive import read_trend_files
from k_b.etl.sources.tracked_repositories import TRACKED_REPOSITORIES
from k_b.etl.transform import COLLECTION_NAME_FORMAT, read_raw_items

logger = logging.getLogger(LOGGER_NAME)

# One log per import, named by its second as a raw file by its collection: never rewritten.
IMPORT_LOG_FILE_NAME = "import-log-{imported_at}.jsonl"


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
    return ExitCode.SUCCEEDED
