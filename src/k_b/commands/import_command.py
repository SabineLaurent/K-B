"""kb import: read the raw files not imported yet and write them into the database."""

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from k_b.commands.batch_summary import describe_duration
from k_b.commands.exit_codes import ExitCode
from k_b.commands.run_log import LOGGER_NAME, describe_os_error
from k_b.core.config import GITHUB_TRACKED_REPOSITORIES
from k_b.core.quoting import quote_value
from k_b.database.errors import ENGINE_ERRORS, describe_engine_error
from k_b.database.location import (
    DatabaseLocation,
    MissingDatabaseError,
    read_database_location_or_refusal,
)
from k_b.database.writing import KindWithoutTableError, UnknownSourceError
from k_b.etl.pipeline import (
    ImportJournalExistsError,
    ImportOutcome,
    import_raw_files,
)
from k_b.etl.raw_store import (
    AUTOMATED_WATCH_DIR_NAME,
    SELECTED_LIBRARY_DIR_NAME,
    make_source_folder_key,
)
from k_b.etl.source_kinds import SOURCE_KINDS
from k_b.etl.sources import cisa_kev, zotero
from k_b.purge.after_import import StateCatalog, purge_after_import

logger = logging.getLogger(LOGGER_NAME)

# The state catalogs: of each, the raw keeps only the last file imported (ADR of 2026-10-19) and
# the base every row (decision of Sabine of 2026-11-04).
STATE_CATALOGS = (
    StateCatalog(
        make_source_folder_key(SELECTED_LIBRARY_DIR_NAME, zotero.FOLDER_PREFIX),
        zotero.SOURCE_CODE,
    ),
    StateCatalog(
        make_source_folder_key(AUTOMATED_WATCH_DIR_NAME, cisa_kev.FOLDER_PREFIX),
        cisa_kev.SOURCE_CODE,
    ),
)


def run_import(data_dir: Path, environ: Mapping[str, str]) -> int:
    """Run the import into the base the environment names, print its summary, then run the purges;
    the summary before them, so that whatever stops them (an error, Ctrl-C) leaves the summary of
    the import committed."""
    # Not value_or_log_refusal: mypy would join the two kinds of location into object.
    database = read_database_location_or_refusal(environ, data_dir)
    if isinstance(database, str):
        logger.error("%s", database)
        return ExitCode.NOT_STARTED
    imported_at = datetime.now(UTC).replace(microsecond=0)
    logger.info("import started")
    started = monotonic()
    try:
        outcome = import_raw_files(
            data_dir, database, SOURCE_KINDS, GITHUB_TRACKED_REPOSITORIES, imported_at
        )
    except MissingDatabaseError as error:
        logger.error("%s; create it with kb create-db", error)
        return ExitCode.NOT_STARTED
    except ImportJournalExistsError as error:
        logger.error("%s; run kb import again", error)
        return ExitCode.NOT_STARTED
    except ENGINE_ERRORS as error:
        logger.error("%s", describe_engine_error(error))
        return ExitCode.FAILED
    except (OSError, UnknownSourceError, KindWithoutTableError) as error:
        logger.error("%s: %s", type(error).__name__, error)
        return ExitCode.FAILED
    logger.info("import finished in %s", describe_duration(monotonic() - started))
    # Where the rejections are detailed (decision of Sabine of 2026-10-29); its name only, as
    # etl/load.py logs it: the path names the data directory.
    logger.info("import journal kept: %s", quote_value(outcome.journal_path.name))
    print_import_result(outcome)
    return purge_after_the_import(data_dir, database, imported_at)


def print_import_result(outcome: ImportOutcome) -> None:
    """The summary of the import on screen, between two blank lines."""
    # A blank line before and after the result, apart from the log and from what follows (make's
    # line of an error): decisions of Sabine of 2026-10-29.
    print()
    print(describe_import_summary(outcome))
    print()


def purge_after_the_import(
    data_dir: Path, database: DatabaseLocation, imported_at: datetime
) -> ExitCode:
    """Run the purges, dated by the import; a failure leaves the import committed."""
    try:
        purge_after_import(
            data_dir, database, imported_at, STATE_CATALOGS, GITHUB_TRACKED_REPOSITORIES
        )
    except (*ENGINE_ERRORS, OSError, ValueError) as error:
        # The type, and the reason of an OSError, never the name of a raw file.
        logger.error(
            "import committed, purge failed: %s; run kb import again",
            describe_os_error(error)
            if isinstance(error, OSError)
            else type(error).__name__,
        )
        return ExitCode.FAILED
    return ExitCode.SUCCEEDED


def describe_import_summary(outcome: ImportOutcome) -> str:
    """The totals of the import on one line; the rejections are detailed in its log."""
    summary = outcome.summary
    return (
        f"import: {summary.read_count} raw read, {summary.item_count} written,"
        f" {summary.trend_count} trend rows, {summary.discard_count} left out,"
        f" {summary.rejection_count} rejected, {summary.withdrawn_count} withdrawn"
    )
