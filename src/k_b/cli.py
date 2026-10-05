"""Command line: `kb collect`."""

import argparse
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from k_b.collect import SOURCES, collect_all_sources
from k_b.raw_store import InvalidCollectionStateError

DATA_DIR_VARIABLE = "KB_DATA_DIR"


def configure_logging() -> None:
    """Show every log line of level INFO and above on stderr, with its level and logger."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kb")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("collect", help="run every source and store its raw output in raw/")
    parser.parse_args(argv)
    configure_logging()

    data_dir = os.environ.get(DATA_DIR_VARIABLE)
    if not data_dir:
        print(f"error: {DATA_DIR_VARIABLE} must point to the data directory", file=sys.stderr)
        return 2
    if not Path(data_dir).is_dir():
        print(f"error: {DATA_DIR_VARIABLE} is not an existing directory", file=sys.stderr)
        return 2

    try:
        outcome = collect_all_sources(SOURCES, Path(data_dir) / "raw", datetime.now(UTC))
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
