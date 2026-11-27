"""kb import: read the raw files not imported yet and write them into the database."""

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from k_b.commands.batch_summary import describe_duration
from k_b.commands.exit_codes import ExitCode
from k_b.commands.run_log import LOGGER_NAME
from k_b.core.config import GITHUB_TRACKED_REPOSITORIES
from k_b.core.quoting import quote_value
from k_b.database.errors import ENGINE_ERRORS, describe_engine_error
from k_b.database.location import (
    MissingDatabaseError,
    UnreadableDatabaseUrlError,
    read_database_location_or_refusal,
)
from k_b.database.writing import KindWithoutTableError, UnknownSourceError
from k_b.etl.pipeline import (
    ImportJournalExistsError,
    ImportOutcome,
    import_raw_files,
)
from k_b.etl.source_kinds import SOURCE_KINDS

logger = logging.getLogger(LOGGER_NAME)


def run_import(data_dir: Path, environ: Mapping[str, str]) -> int:
    """Run the import into the base the environment names, then print its summary."""
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
        logger.error(
            "%s; create it with kb create-db, or online with kb migrate-database", error
        )
        return ExitCode.NOT_STARTED
    except ImportJournalExistsError as error:
        logger.error("%s; run kb import again", error)
        return ExitCode.NOT_STARTED
    except UnreadableDatabaseUrlError as error:
        logger.error("%s", error)
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
    return ExitCode.SUCCEEDED


def print_import_result(outcome: ImportOutcome) -> None:
    """The summary of the import on screen, between two blank lines."""
    # A blank line before and after the result, apart from the log and from what follows (make's
    # line of an error): decisions of Sabine of 2026-10-29.
    print()
    print(describe_import_summary(outcome))
    print()


def describe_import_summary(outcome: ImportOutcome) -> str:
    """The totals of the import on one line; the rejections are detailed in its log."""
    summary = outcome.summary
    return (
        f"import: {summary.read_count} raw read, {summary.item_count} written,"
        f" {summary.trend_count} trend rows, {summary.discard_count} left out,"
        f" {summary.rejection_count} rejected, {summary.withdrawn_count} withdrawn"
    )
