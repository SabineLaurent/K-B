"""The helpers several test files of the kb commands use."""

import sqlite3

from k_b.etl.source_contract import SourceKind


def collected_kinds(*sources):
    """One kind without a reader: the collection tests only need its sources."""
    return (SourceKind("test", sources, None),)


# The date of a log line, in the format of the dates of the base: ISO 8601, UTC, its zone Z.
LOG_LINE_DATE = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"


class SigtermNotHandledByKbError(Exception):
    """Raised by the handler of the test: kb did not set its own."""


class SigintNotHandledByKbError(Exception):
    """Raised by the SIGINT handler of the test: kb did not set its own."""


def dump_database(data_dir):
    """Every table, row by row, as SQL text, as in etl/test_load.py, which cannot be imported
    from here."""
    connection = sqlite3.connect(data_dir / "k-b.sqlite")
    try:
        return list(connection.iterdump())
    finally:
        connection.close()


def list_hidden_files(directory):
    return [path for path in directory.rglob(".*") if path.is_file()]


def list_sheets(vault_dir):
    return sorted(
        path.relative_to(vault_dir).as_posix() for path in vault_dir.rglob("*.md")
    )


# kb collect run as the kb script runs it, sys.exit(main()), with a source that says it has
# started, then waits for a signal (SIGTERM or SIGINT).
COLLECT_WAITING_FOR_A_SIGNAL = """
import signal
import sys
import time

from k_b import cli
from k_b.commands import collect_command
from k_b.etl.source_contract import SourceKind


class WaitingSource:
    name = "waiting"
    extension = "json"
    acquisition_dir_name = "automated_watch"

    def fetch(self, last_collected_at):
        print("ready", flush=True)
        time.sleep(60)
        return b"{}"


# SIGINT as a terminal gives it: a pytest run with SIGINT ignored would pass it on to kb.
signal.signal(signal.SIGINT, signal.default_int_handler)
collect_command.SOURCE_KINDS = (SourceKind("test", (WaitingSource(),), None),)
sys.exit(cli.main(["collect"]))
"""
