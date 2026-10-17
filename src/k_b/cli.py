"""Command line: `kb collect`, `kb create-db`, `kb import`, `kb serve`, `kb openapi`."""

import argparse
import ipaddress
import json
import logging
import os
import re
import sqlite3
import sys
import time
from collections.abc import Iterator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import uvicorn
from pydantic import SecretStr

from k_b.core.config import (
    API_KEY_CHARACTERS,
    DATA_API_ALLOWED_HOSTS,
    DATA_API_HOST,
    DATA_API_PORT,
    LOG_FILES_KEPT,
    LOG_TO_FILE,
    MIN_API_KEY_LENGTH,
)
from k_b.core.quoting import quote_value
from k_b.data_api.app import create_app
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
from k_b.etl.raw_store import InvalidCollectionStateError, write_file_atomically
from k_b.etl.source_contract import list_sources
from k_b.etl.source_kinds import SOURCE_KINDS
from k_b.etl.sources.clipping import FOLDER_PREFIX as CLIPPING_SOURCE_NAME
from k_b.etl.sources.clipping import ClippingSource
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
# The Obsidian vault of K-B, the one that holds Clippings/. Not set: the clips are skipped. No
# default (.claude/rules/poc.md, rule 2), as KB_ZOTERO_DIR: a folder of the user's machine.
VAULT_DIR_VARIABLE = "KB_VAULT_DIR"
# The path of the BigQuery service account key, read by the client. Not set: GH Archive is skipped.
BIGQUERY_KEY_VARIABLE = "GOOGLE_APPLICATION_CREDENTIALS"
# One log per import, named by its second as a raw file by its collection: never rewritten.
IMPORT_LOG_FILE_NAME = "import-log-{imported_at}.jsonl"


# The log of every run, successes and failures, apart from the import logs: those are written
# only when an import reaches the end of its writing in the base.
LOG_FILE_PATH = Path("logs") / "kb.log"
# The log of kb serve, apart: a long run that shared kb.log would keep writing in the file of the
# day before once a rotation done by kb collect or kb import has renamed it (docs/specs-api.md,
# "Journal").
SERVE_LOG_FILE_PATH = Path("logs") / "kb-serve.log"
LOG_LINE_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
# true or false; not set: LOG_TO_FILE of core/config.py.
LOG_TO_FILE_VARIABLE = "KB_LOG_TO_FILE"
LOG_TO_FILE_VALUES = {"true": True, "false": False}


# The key of each client of the data API: one variable KB_API_KEY_<CLIENT> per client
# (docs/specs-api.md, "Accès par clé").
API_KEY_VARIABLE_PREFIX = "KB_API_KEY_"
CLIENT_NAME = re.compile(r"[A-Z0-9_]+")
# Where kb serve listens and the hosts it answers; not set: the defaults of core/config.py.
DATA_API_HOST_VARIABLE = "KB_DATA_API_HOST"
DATA_API_PORT_VARIABLE = "KB_DATA_API_PORT"
DATA_API_ALLOWED_HOSTS_VARIABLE = "KB_DATA_API_ALLOWED_HOSTS"
# Digits only: int() would also read " 8000", "+8000" and "8_000".
PORT_DIGITS = re.compile(r"[0-9]{1,5}")
PORT_NUMBERS = range(1, 65536)
# A host name in lowercase, without * nor port: TrustedHostMiddleware compares the Host received
# as it is (starlette/middleware/trustedhost.py), and an entry of this form has nothing to escape
# in the log.
ALLOWED_HOST = re.compile(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?")
# Written from the root of the repository, which versions it.
OPENAPI_PATH = Path("docs") / "api" / "openapi-donnees.json"


@contextmanager
def logging_to(
    data_dir: Path, log_file_path: Path | None = LOG_FILE_PATH
) -> Iterator[None]:
    """Log every line of level INFO and above on stderr and, unless log_file_path is None, in
    the log file of the data directory (logs/kb.log, or logs/kb-serve.log for kb serve), dated
    in UTC in the format of the base (2026-10-14T11:30:00Z); the file turns at midnight UTC into
    <file>.<day>.

    Raises OSError when the log file cannot be opened. On exit the handlers are closed and
    removed: the tests run kb many times in the interpreter of pytest.
    """
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file_path is not None:
        log_path = data_dir / log_file_path
        log_path.parent.mkdir(exist_ok=True)
        handlers.append(
            TimedRotatingFileHandler(
                log_path,
                when="midnight",
                utc=True,
                backupCount=LOG_FILES_KEPT,
                encoding="utf-8",
            )
        )
    formatter = logging.Formatter(LOG_LINE_FORMAT, datefmt=DATABASE_DATE_FORMAT)
    # The Z of the format says UTC: the time is read in UTC, not in local time.
    formatter.converter = time.gmtime
    root_logger = logging.getLogger()
    previous_level = root_logger.level
    for handler in handlers:
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
    try:
        yield
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
    commands.add_parser(
        "serve",
        help="serve the database, read only, on"
        f" http://{DATA_API_HOST}:{DATA_API_PORT} by default",
    )
    commands.add_parser(
        "openapi", help=f"write the OpenAPI of the data API in {OPENAPI_PATH}"
    )
    arguments = parser.parse_args(argv)

    # Neither data nor key: the document is the same on every machine.
    if arguments.command == "openapi":
        return run_openapi()
    data_dir = read_data_dir()
    log_to_file = read_log_to_file()
    if data_dir is None or log_to_file is None:
        return 2
    log_file_path = None
    if log_to_file:
        log_file_path = (
            SERVE_LOG_FILE_PATH if arguments.command == "serve" else LOG_FILE_PATH
        )
    with ExitStack() as log_stack:
        try:
            log_stack.enter_context(logging_to(data_dir, log_file_path))
        except OSError as error:
            # A run without its log would lose the failures the log is kept for: none is run.
            print(
                f"error: log file not opened: {type(error).__name__}: {error}",
                file=sys.stderr,
            )
            return 2
        try:
            return run_command(arguments.command, data_dir)
        except Exception:
            # Logged here, while the log file is open, and not raised again: Python would print
            # its traceback a second time. 1, as Python exits on an exception: kb was run.
            logger.exception("kb stopped by an exception it does not handle")
            return 1


def run_command(command: str, data_dir: Path) -> int:
    if command == "create-db":
        return run_create_db(data_dir)
    if command == "import":
        return run_import(data_dir)
    if command == "serve":
        return run_serve(data_dir)
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


def read_log_to_file() -> bool | None:
    """Whether kb logs in a file as well as on stderr, or None after printing why the value is
    refused: the log is not open yet."""
    value = os.environ.get(LOG_TO_FILE_VARIABLE)
    if value is None:
        return LOG_TO_FILE
    if value not in LOG_TO_FILE_VALUES:
        print(
            f"error: {LOG_TO_FILE_VARIABLE}: {quote_value(value)} neither true nor false",
            file=sys.stderr,
        )
        return None
    return LOG_TO_FILE_VALUES[value]


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
    vault_dir = os.environ.get(VAULT_DIR_VARIABLE)
    if vault_dir:
        sources.append(ClippingSource(Path(vault_dir)))
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
    if not vault_dir:
        print(f"{CLIPPING_SOURCE_NAME}: skipped ({VAULT_DIR_VARIABLE} not set)")
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


@dataclass(frozen=True)
class ServeSettings:
    host: str
    port: int
    allowed_hosts: tuple[str, ...]


def run_serve(data_dir: Path) -> int:
    """Serve the base with the keys and the settings of the environment; the log of uvicorn is
    the one of kb."""
    api_keys = read_api_keys(os.environ)
    settings = read_serve_settings(os.environ)
    if api_keys is None or settings is None:
        return 2
    logger.info("API clients loaded: %s", ", ".join(sorted(api_keys)))
    logger.info("API allowed hosts: %s", ", ".join(settings.allowed_hosts))
    uvicorn.run(
        create_app(
            data_dir / DATABASE_FILE_NAME,
            api_keys,
            allowed_hosts=settings.allowed_hosts,
        ),
        host=settings.host,
        port=settings.port,
        log_config=None,
        access_log=False,
    )
    return 0


def read_serve_settings(environ: Mapping[str, str]) -> ServeSettings | None:
    """The host, the port and the hosts allowed of kb serve, or None after logging the variable
    refused, with its value quoted. Not set: the default of core/config.py."""
    host = environ.get(DATA_API_HOST_VARIABLE, DATA_API_HOST)
    port = environ.get(DATA_API_PORT_VARIABLE, str(DATA_API_PORT))
    allowed_hosts_value = environ.get(DATA_API_ALLOWED_HOSTS_VARIABLE)
    # Split once: the list checked is the list served.
    allowed_hosts = (
        DATA_API_ALLOWED_HOSTS
        if allowed_hosts_value is None
        else split_allowed_hosts(allowed_hosts_value)
    )
    refusal = (
        find_host_refusal(host)
        or find_port_refusal(port)
        or find_allowed_hosts_refusal(allowed_hosts)
    )
    if refusal is not None:
        logger.error("%s", refusal)
        return None
    return ServeSettings(host=host, port=int(port), allowed_hosts=allowed_hosts)


def find_host_refusal(host: str) -> str | None:
    """Why the host is refused, or None. An IPv4 address only: uvicorn would bind an empty host
    to every interface, and the Host of a client in IPv6 keeps its brackets ([::1]), which no
    allowed host can name."""
    try:
        ipaddress.IPv4Address(host)
    except ValueError:
        return f"{DATA_API_HOST_VARIABLE}: {quote_value(host)} not an IPv4 address"
    return None


def find_port_refusal(port: str) -> str | None:
    if PORT_DIGITS.fullmatch(port) and int(port) in PORT_NUMBERS:
        return None
    return (
        f"{DATA_API_PORT_VARIABLE}: {quote_value(port)} not an integer"
        f" from {PORT_NUMBERS.start} to {PORT_NUMBERS.stop - 1}"
    )


def split_allowed_hosts(allowed_hosts: str) -> tuple[str, ...]:
    """The entries of the list, separated by commas, without the spaces around each."""
    return tuple(entry.strip() for entry in allowed_hosts.split(","))


def find_allowed_hosts_refusal(allowed_hosts: tuple[str, ...]) -> str | None:
    """Why the hosts allowed are refused, or None: TrustedHostMiddleware would serve any host for
    a * (docs/specs-api.md, API8)."""
    # A value empty or made of spaces gives one empty entry.
    if allowed_hosts == ("",):
        return f"{DATA_API_ALLOWED_HOSTS_VARIABLE}: empty, set the hosts separated by commas"
    for position, entry in enumerate(allowed_hosts, start=1):
        where = f"{DATA_API_ALLOWED_HOSTS_VARIABLE}: entry {position} of {len(allowed_hosts)}"
        if not entry:
            return f"{where} empty"
        if "*" in entry:
            return f"{where} {quote_value(entry)} with '*', name each host"
        if not ALLOWED_HOST.fullmatch(entry):
            return f"{where} {quote_value(entry)} not a lowercase host name"
    return None


def read_api_keys(environ: Mapping[str, str]) -> dict[str, SecretStr] | None:
    """The key of each client, by its name, or None after logging the variable refused: the
    name of the variable, never its value."""
    variables = sorted(
        name for name in environ if name.startswith(API_KEY_VARIABLE_PREFIX)
    )
    if not variables:
        logger.error("no API key: set %s<CLIENT>", API_KEY_VARIABLE_PREFIX)
        return None
    api_keys: dict[str, SecretStr] = {}
    variable_by_key: dict[str, str] = {}
    for variable in variables:
        key = environ[variable]
        refusal = find_api_key_refusal(variable, key, variable_by_key)
        if refusal is not None:
            logger.error("%s", refusal)
            return None
        variable_by_key[key] = variable
        api_keys[variable.removeprefix(API_KEY_VARIABLE_PREFIX)] = SecretStr(key)
    return api_keys


def find_api_key_refusal(
    variable: str, key: str, variable_by_key: Mapping[str, str]
) -> str | None:
    """Why the variable of a client is refused, or None; variable_by_key holds the keys already
    read. The variable is quoted: its name comes from the environment."""
    client_name = variable.removeprefix(API_KEY_VARIABLE_PREFIX)
    if not CLIENT_NAME.fullmatch(client_name):
        return f"{quote_value(variable)}: client name empty or not [A-Z0-9_]+"
    if len(key) < MIN_API_KEY_LENGTH:
        return (
            f"{quote_value(variable)}: key of {len(key)} characters,"
            f" minimum {MIN_API_KEY_LENGTH}"
        )
    if not API_KEY_CHARACTERS.fullmatch(key):
        return f"{quote_value(variable)}: key with a character outside [A-Za-z0-9_-]"
    if key in variable_by_key:
        return (
            f"{quote_value(variable_by_key[key])} and {quote_value(variable)}: same key"
        )
    return None


def run_openapi() -> int:
    """Write the OpenAPI of the data API, versioned with the code (docs/specs-api.md)."""
    # Run from another folder, it would write a document the repository never sees.
    if not OPENAPI_PATH.parent.is_dir():
        print(
            f"error: {OPENAPI_PATH.parent} is not a directory of the current directory;"
            " run kb openapi at the root of the repository",
            file=sys.stderr,
        )
        return 2
    # The app is made without base nor key: its document does not depend on them.
    openapi = create_app(Path(DATABASE_FILE_NAME), {}).openapi()
    content = json.dumps(openapi, indent=2, ensure_ascii=False) + "\n"
    try:
        write_file_atomically(OPENAPI_PATH, content.encode())
    except OSError as error:
        print(
            f"error: {OPENAPI_PATH} not written: {type(error).__name__}",
            file=sys.stderr,
        )
        return 1
    print(f"OpenAPI written: {OPENAPI_PATH}")
    return 0
