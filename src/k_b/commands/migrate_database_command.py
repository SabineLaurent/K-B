"""kb migrate-database: create the items database when it has no tables yet, and leave it as it is
when it has them; the job caj-kb-migrate-database runs it at each delivery."""

import logging
from collections.abc import Mapping
from pathlib import Path

from k_b.commands.exit_codes import ExitCode
from k_b.commands.run_log import LOGGER_NAME
from k_b.database.creation import UnsuitableDatabaseError, migrate_database
from k_b.database.errors import ENGINE_ERRORS, describe_engine_error
from k_b.database.location import (
    DatabaseLocation,
    UnreadableDatabaseUrlError,
    describe_location,
    read_database_location_or_refusal,
)

logger = logging.getLogger(LOGGER_NAME)


def run_migrate_database(data_dir: Path, environ: Mapping[str, str]) -> int:
    """Create the base the environment names unless it has its tables; a PostgreSQL base of other
    settings than K-B needs is refused before anything is written."""
    # Not value_or_log_refusal: mypy would join the two kinds of location into object.
    location = read_database_location_or_refusal(environ, data_dir)
    if isinstance(location, str):
        logger.error("%s", location)
        return ExitCode.NOT_STARTED
    try:
        created = migrate_database(location)
    except (UnsuitableDatabaseError, UnreadableDatabaseUrlError) as error:
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
    if created:
        print(f"database created: {describe_location(location)}")
    else:
        print(f"database unchanged: {describe_unchanged(location)}")
    return ExitCode.SUCCEEDED


def describe_unchanged(location: DatabaseLocation) -> str:
    """Why the base was left as it is: its file exists, or its PostgreSQL base has its tables."""
    if isinstance(location, Path):
        return f"{location} already exists"
    return f"{describe_location(location)} already has its tables"
