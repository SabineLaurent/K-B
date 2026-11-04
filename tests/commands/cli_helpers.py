"""The helpers several test files of the kb commands use."""

import itertools
import logging
import threading
from datetime import UTC, datetime, timedelta

from k_b.etl.source_contract import SourceKind


def collected_kinds(*sources):
    """One kind without a reader: the collection tests only need its sources."""
    return (SourceKind("test", sources, None),)


# The date of a log line, in the format of the dates of the base: ISO 8601, UTC, its zone Z.
LOG_LINE_DATE = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"


class WaitLineSeen(logging.Handler):
    """Sets seen at the first line of the wait logged: an event, as an assert in the thread of the
    wait would only be a warning of pytest."""

    def __init__(self):
        super().__init__()
        self.seen = threading.Event()

    def emit(self, record):
        if record.getMessage().startswith("still waiting for "):
            self.seen.set()


class SigtermNotHandledByKbError(Exception):
    """Raised by the handler of the test: kb did not set its own."""


def list_hidden_files(directory):
    return [path for path in directory.rglob(".*") if path.is_file()]


def list_sheets(vault_dir):
    return sorted(
        path.relative_to(vault_dir).as_posix() for path in vault_dir.rglob("*.md")
    )


# The day the tests run kb import, unless one says otherwise: its purge deletes by age, and the
# raw files of the tests are named in October 2026.
KB_IMPORT_DAY = datetime(2026, 10, 20, tzinfo=UTC)


def make_clock(start):
    """A datetime whose now gives start, then a second later at each call, so that two imports
    of a test each write their own log."""
    seconds = itertools.count()

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return start + timedelta(seconds=next(seconds))

    return Clock
