"""kb purge: delete what is past its duration, dated by the start of the command, on its own and
not after an import (docs/registre-traitements.md, procedure of sorting)."""

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from k_b.commands.batch_summary import describe_duration
from k_b.commands.exit_codes import ExitCode
from k_b.commands.run_log import LOGGER_NAME, describe_os_error
from k_b.core.config import GITHUB_TRACKED_REPOSITORIES
from k_b.database.errors import ENGINE_ERRORS
from k_b.database.location import (
    MissingDatabaseError,
    UnreadableDatabaseUrlError,
    read_database_location_or_refusal,
)
from k_b.etl.raw_store import (
    AUTOMATED_WATCH_DIR_NAME,
    SELECTED_LIBRARY_DIR_NAME,
    make_source_folder_key,
)
from k_b.etl.sources import cisa_kev, zotero
from k_b.purge.all_purges import StateCatalog, run_purges

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


def run_purge(data_dir: Path, environ: Mapping[str, str]) -> int:
    """Run the purges on the base the environment names, dated by now; the first failure stops
    the purges after it, which the next kb purge runs."""
    # Not value_or_log_refusal: mypy would join the two kinds of location into object.
    database = read_database_location_or_refusal(environ, data_dir)
    if isinstance(database, str):
        logger.error("%s", database)
        return ExitCode.NOT_STARTED
    purged_at = datetime.now(UTC).replace(microsecond=0)
    logger.info("purge started")
    started = monotonic()
    try:
        run_purges(
            data_dir, database, purged_at, STATE_CATALOGS, GITHUB_TRACKED_REPOSITORIES
        )
    # Before OSError: a FileNotFoundError.
    except MissingDatabaseError as error:
        logger.error("%s; create it with kb create-db", error)
        return ExitCode.NOT_STARTED
    except UnreadableDatabaseUrlError as error:
        logger.error("%s", error)
        return ExitCode.NOT_STARTED
    except (*ENGINE_ERRORS, OSError, ValueError) as error:
        # The type, and the reason of an OSError, never the name of a raw file.
        logger.error(
            "purge failed: %s; run kb purge again",
            describe_os_error(error)
            if isinstance(error, OSError)
            else type(error).__name__,
        )
        return ExitCode.FAILED
    logger.info("purge finished in %s", describe_duration(monotonic() - started))
    return ExitCode.SUCCEEDED
