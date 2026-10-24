"""The environment of a run, read before its log is open: the data directory, the log file."""

import os
import sys
from pathlib import Path

from k_b.core.config import LOG_TO_FILE
from k_b.core.quoting import quote_value

DATA_DIR_VARIABLE = "KB_DATA_DIR"
# true or false; not set: LOG_TO_FILE of core/config.py.
LOG_TO_FILE_VARIABLE = "KB_LOG_TO_FILE"
LOG_TO_FILE_VALUES = {"true": True, "false": False}


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
    refused."""
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
