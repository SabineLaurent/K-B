"""The entry point of kb: it reads the command and the environment (commands/environment.py),
opens the log and hands the run to its module in commands/, the environment given as a parameter."""

import argparse
import logging
import sys
from collections.abc import Callable, Mapping
from contextlib import ExitStack
from pathlib import Path
from typing import NamedTuple

from k_b.commands.collect_command import run_collect
from k_b.commands.create_db_command import run_create_db
from k_b.commands.daily_routine_command import (
    describe_daily_routine,
    run_daily_routine,
)
from k_b.commands.digest_command import run_digest
from k_b.commands.digest_watch_command import (
    describe_digest_watch,
    run_digest_watch,
)
from k_b.commands.download_watch_sheets_command import run_download_watch_sheets
from k_b.commands.environment import (
    read_data_dir,
    read_environment,
    read_log_to_file,
)
from k_b.commands.exit_codes import ExitCode
from k_b.commands.import_command import run_import
from k_b.commands.migrate_database_command import run_migrate_database
from k_b.commands.openapi_command import (
    AI_API_OPENAPI_PATH,
    DATA_API_OPENAPI_PATH,
    run_openapi,
)
from k_b.commands.run_log import (
    LOG_FILE_PATH,
    LOGGER_NAME,
    SERVE_AI_LOG_FILE_PATH,
    SERVE_DATA_LOG_FILE_PATH,
    logging_to,
)
from k_b.commands.serve_ai_command import run_serve_ai
from k_b.commands.serve_data_command import run_serve_data
from k_b.commands.sigterm import StoppedBySigtermError, stopping_on_sigterm
from k_b.commands.smoke_test_command import run_smoke_test
from k_b.commands.trend_report_command import run_trend_report
from k_b.commands.write_tops_command import run_write_tops
from k_b.core.config import (
    AI_API_HOST,
    AI_API_PORT,
    CLIPPINGS_CONTAINER,
    DATA_API_HOST,
    DATA_API_PORT,
    DATABASE_FILE_NAME,
    SMOKE_TEST_CONTAINER,
    WATCH_CONTAINER,
)
from k_b.database.location import DATABASE_URL_VARIABLE
from k_b.etl.collected_sources import COLLECT_ONLY_VARIABLE, VAULT_DIR_VARIABLE

logger = logging.getLogger(LOGGER_NAME)

# The long runs, each with its own log file: a rotation done by another command would leave it
# writing in the file of the day before (docs/specs-api.md, "Journal").
LOG_FILE_PATH_BY_COMMAND = {
    "serve-data": SERVE_DATA_LOG_FILE_PATH,
    "serve-ai": SERVE_AI_LOG_FILE_PATH,
}


class RoutineCommand(NamedTuple):
    """A command of a job that chains steps (#413): its run, and its steps for --dry-run."""

    run: Callable[[Path, Mapping[str, str]], int]
    describe: Callable[[], str]


ROUTINE_BY_COMMAND = {
    "daily-routine": RoutineCommand(run_daily_routine, describe_daily_routine),
    "digest-watch": RoutineCommand(run_digest_watch, describe_digest_watch),
}
DRY_RUN_HELP = "print the steps and their rules, run none and transfer nothing"
# The commands run with the data directory and the environment, by name, kb collect the default; a
# table rather than a branch each, which would pass the complexity ruff allows (C901, 10). kb serve-ai,
# kb digest, kb smoke-test and kb download-watch-sheets take the environment only (run_command).
RUN_BY_COMMAND: dict[str, Callable[[Path, Mapping[str, str]], int]] = {
    "create-db": run_create_db,
    "migrate-database": run_migrate_database,
    "import": run_import,
    "write-tops": run_write_tops,
    "serve-data": run_serve_data,
    "trend-report": run_trend_report,
} | {command: routine.run for command, routine in ROUTINE_BY_COMMAND.items()}


def main(argv: list[str] | None = None) -> int:
    """Run the kb command typed on the command line and return its exit code."""
    command, is_dry_run = read_command(argv)
    # Neither data nor key: the document is the same on every machine.
    if command == "openapi":
        return run_openapi()
    # Read once, here: every command gets the same mapping.
    environ = read_environment()
    data_dir = read_data_dir(environ)
    log_to_file = read_log_to_file(environ)
    if data_dir is None or log_to_file is None:
        return ExitCode.NOT_STARTED
    if is_dry_run:
        # KB_DATA_DIR and KB_LOG_TO_FILE checked as for a run, then the steps printed: nothing run
        # nor logged, and no setting of the job read (the criterion of #413 runs it without them).
        print(ROUTINE_BY_COMMAND[command].describe())
        return ExitCode.SUCCEEDED
    return run_with_log(command, data_dir, environ, log_to_file)


def read_command(argv: list[str] | None) -> tuple[str, bool]:
    """Read the kb command typed, such as collect or import, and whether --dry-run is given."""
    parser = argparse.ArgumentParser(
        prog="kb",
        epilog=describe_exit_codes(),
        # Keeps the lines of the epilog: the default formatter joins them.
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    command_parsers = parser.add_subparsers(dest="command", required=True)
    command_parsers.add_parser(
        "collect",
        help=f"run every source, or the ones of {COLLECT_ONLY_VARIABLE}, and store its raw"
        " output in raw/",
    )
    command_parsers.add_parser(
        "create-db",
        help=f"create the items database, {DATABASE_FILE_NAME}, or the tables of the"
        f" PostgreSQL base of {DATABASE_URL_VARIABLE}",
    )
    command_parsers.add_parser(
        "migrate-database",
        help="create the items database unless it already has its tables, then nothing is"
        " written; on PostgreSQL, also grant its tables to the roles of"
        " infra/postgresql/grant-roles.sql, which must exist",
    )
    command_parsers.add_parser(
        "import",
        help="read the raw items and write them into the database, which removes the duplicates",
    )
    command_parsers.add_parser(
        "write-tops",
        help="write the sheet of each top ranking in the vault of KB_VAULT_DIR, then delete"
        " the rankings it supersedes",
    )
    command_parsers.add_parser(
        "serve-data",
        help="serve the database, read only, on"
        f" http://{DATA_API_HOST}:{DATA_API_PORT} by default",
    )
    command_parsers.add_parser(
        "serve-ai",
        help="serve the digests of the watch by the AI API, on"
        f" http://{AI_API_HOST}:{AI_API_PORT} by default",
    )
    command_parsers.add_parser(
        "digest",
        help="ask the AI API for the digests of the watch, then write the sheet of each"
        f" subject in the vault of {VAULT_DIR_VARIABLE}",
    )
    command_parsers.add_parser(
        "trend-report",
        help="ask the AI API for the trend report of the GH Archive windows after the previous"
        f" one, then write it in the vault of {VAULT_DIR_VARIABLE}",
    )
    command_parsers.add_parser(
        "smoke-test",
        help="check that both APIs answer GET /health and that the identity of the job lists"
        f" the container {SMOKE_TEST_CONTAINER} of the exchange storage; writes counts only",
    )
    command_parsers.add_parser(
        "openapi",
        help=f"write the OpenAPI of the data API in {DATA_API_OPENAPI_PATH} and the one of"
        f" the AI API in {AI_API_OPENAPI_PATH}",
    )
    command_parsers.add_parser(
        "daily-routine",
        help=f"the job of each day: mirror the container {CLIPPINGS_CONTAINER} to the vault,"
        " kb collect, kb import unless kb collect exits with 1 or 2, kb write-tops, then"
        f" publish veille to the container {WATCH_CONTAINER} without replacing a blob",
    ).add_argument("--dry-run", action="store_true", help=DRY_RUN_HELP)
    command_parsers.add_parser(
        "download-watch-sheets",
        help=f"on the Mac: copy to veille of the vault each sheet of the container"
        f" {WATCH_CONTAINER} it lacks, by the account of az login; a sheet there is never"
        " replaced",
    )
    command_parsers.add_parser(
        "digest-watch",
        help="the job of the watch: wake both APIs, kb digest, wake them again, kb trend-report,"
        f" then publish veille to the container {WATCH_CONTAINER} without replacing a blob",
    ).add_argument("--dry-run", action="store_true", help=DRY_RUN_HELP)
    arguments = parser.parse_args(argv)
    command: str = arguments.command
    # Only the commands of ROUTINE_BY_COMMAND take --dry-run.
    is_dry_run: bool = getattr(arguments, "dry_run", False)
    return command, is_dry_run


def run_with_log(
    command: str, data_dir: Path, environ: Mapping[str, str], log_to_file: bool
) -> int:
    """Open the log of the run, then run the command; none is run without its log."""
    log_file_path = None
    if log_to_file:
        log_file_path = LOG_FILE_PATH_BY_COMMAND.get(command, LOG_FILE_PATH)
    with ExitStack() as log_stack:
        try:
            log_stack.enter_context(logging_to(data_dir, log_file_path))
        except OSError as error:
            # A run without its log would lose the failures the log is kept for: none is run.
            print(
                f"error: log file not opened: {type(error).__name__}: {error}",
                file=sys.stderr,
            )
            return ExitCode.NOT_STARTED
        return run_with_safety_nets(command, data_dir, environ)


def run_with_safety_nets(
    command: str, data_dir: Path, environ: Mapping[str, str]
) -> int:
    """Run the command; a stop by a signal or an unhandled exception is logged with its exit
    code."""
    try:
        with stopping_on_sigterm(command):
            return run_command(command, data_dir, environ)
    except StoppedBySigtermError:
        # Caught once the import or the collection has cleaned up on its way out.
        logger.error("kb stopped by SIGTERM")
        return ExitCode.STOPPED_BY_SIGTERM
    except KeyboardInterrupt:
        # The same for SIGINT (Ctrl-C), which Python raises as KeyboardInterrupt, not an
        # Exception: uncaught, Python would print its whole traceback.
        logger.error("kb stopped by SIGINT")
        return ExitCode.STOPPED_BY_SIGINT
    except Exception:
        # Logged here, while the log file is open, and not raised again: Python would print
        # its traceback a second time. 1, as Python exits on an exception: kb was run.
        logger.exception("kb stopped by an exception it does not handle")
        return ExitCode.FAILED


def describe_exit_codes() -> str:
    """List each exit code of kb with its meaning, shown at the end of kb --help."""
    lines = [f"  {code.value:>3}  {code.meaning}" for code in ExitCode]
    return "exit codes:\n" + "\n".join(lines)


def run_command(command: str, data_dir: Path, environ: Mapping[str, str]) -> int:
    """Run the kb command given and return its exit code."""
    if command == "serve-ai":
        return run_serve_ai(environ)
    if command == "digest":
        return run_digest(environ)
    if command == "smoke-test":
        return run_smoke_test(environ)
    if command == "download-watch-sheets":
        return run_download_watch_sheets(environ)
    return RUN_BY_COMMAND.get(command, run_collect)(data_dir, environ)
