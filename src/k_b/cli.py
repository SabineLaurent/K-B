"""Command line: `kb collect`, `kb create-db`, `kb import`."""

import argparse
import logging
import os
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from k_b.collect import SOURCES, collect_all_sources
from k_b.database import DATABASE_FILE_NAME, create_database
from k_b.import_items import MissingDatabaseError, import_items
from k_b.raw_store import InvalidCollectionStateError

DATA_DIR_VARIABLE = "KB_DATA_DIR"
IMPORT_LOG_FILE_NAME = "import-log.jsonl"


def configure_logging() -> None:
    """Show every log line of level INFO and above on stderr, with its level and logger."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kb")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("collect", help="run every source and store its raw output in raw/")
    commands.add_parser("create-db", help=f"create the items database, {DATABASE_FILE_NAME}")
    commands.add_parser("import", help="merge the raw items and write them into the database")
    arguments = parser.parse_args(argv)
    configure_logging()

    data_dir = read_data_dir()
    if data_dir is None:
        return 2
    if arguments.command == "create-db":
        return run_create_db(data_dir)
    if arguments.command == "import":
        return run_import(data_dir)
    return run_collect(data_dir)


def read_data_dir() -> Path | None:
    """The data directory, or None after printing why it cannot be used."""
    data_dir = os.environ.get(DATA_DIR_VARIABLE)
    if not data_dir:
        print(f"error: {DATA_DIR_VARIABLE} must point to the data directory", file=sys.stderr)
        return None
    if not Path(data_dir).is_dir():
        print(f"error: {DATA_DIR_VARIABLE} is not an existing directory", file=sys.stderr)
        return None
    return Path(data_dir)


def run_create_db(data_dir: Path) -> int:
    database_path = data_dir / DATABASE_FILE_NAME
    try:
        create_database(database_path)
    except FileExistsError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except (sqlite3.Error, OSError) as error:
        print(f"error: {database_path}: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print(f"database created: {database_path}")
    return 0


def run_import(data_dir: Path) -> int:
    database_path = data_dir / DATABASE_FILE_NAME
    log_path = data_dir / IMPORT_LOG_FILE_NAME
    try:
        summary = import_items(data_dir / "raw", database_path, log_path)
    except MissingDatabaseError as error:
        print(f"error: {error}; create it with kb create-db", file=sys.stderr)
        return 2
    except (sqlite3.Error, OSError) as error:
        print(f"error: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print(f"items imported: {summary.item_count}")
    print(f"duplicates removed: {summary.discard_count}")
    print(f"rejections: {summary.rejection_count}")
    print(f"log: {log_path}")
    return 0


def run_collect(data_dir: Path) -> int:
    try:
        outcome = collect_all_sources(SOURCES, data_dir / "raw", datetime.now(UTC))
    except InvalidCollectionStateError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    for source_name, error in outcome.errors_by_source.items():
        print(f"{source_name}: {describe_outcome(error)}")
    if outcome.state_error is not None:
        print(f"collection_state: {describe_outcome(outcome.state_error)}")
    has_failure = outcome.state_error is not None or any(
        error is not None for error in outcome.errors_by_source.values()
    )
    return 1 if has_failure else 0


def describe_outcome(error: Exception | None) -> str:
    return "ok" if error is None else f"failed ({type(error).__name__})"
