"""kb create-db: create the items database, the SQLite file of the data directory or the
PostgreSQL base of KB_DATABASE_URL."""

import logging
from collections.abc import Mapping
from pathlib import Path

from k_b.commands.exit_codes import ExitCode
from k_b.commands.run_log import LOGGER_NAME
from k_b.database.creation import (
    ExistingDatabaseError,
    UnsuitableDatabaseError,
    create_database,
)
from k_b.database.errors import ENGINE_ERRORS, describe_engine_error
from k_b.database.location import describe_location, read_database_location_or_refusal

logger = logging.getLogger(LOGGER_NAME)


def run_create_db(data_dir: Path, environ: Mapping[str, str]) -> int:
    """Create the base the environment names; one that exists, or a PostgreSQL base of other
    settings than K-B needs, is refused before anything is written."""
    # Not value_or_log_refusal: mypy would join the two kinds of location into object.
    location = read_database_location_or_refusal(environ, data_dir)
    if isinstance(location, str):
        logger.error("%s", location)
        return ExitCode.NOT_STARTED
    try:
        create_database(location)
    except (FileExistsError, ExistingDatabaseError, UnsuitableDatabaseError) as error:
        logger.error("%s", error)
        return ExitCode.NOT_STARTED
    except ENGINE_ERRORS as error:
        logger.error(
            "%s: %s", describe_location(location), describe_engine_error(error)
        )
        return ExitCode.FAILED
    except OSError as error:
        logger.error(
            "%s: %s: %s", describe_location(location), type(error).__name__, error
        )
        return ExitCode.FAILED
    print(f"database created: {describe_location(location)}")
    return ExitCode.SUCCEEDED
