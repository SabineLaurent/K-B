"""The log of a run of kb: where it goes, its format, and the refusals of the layers it records."""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from k_b.core.config import (
    LOG_FILE_NAME,
    LOGS_DIR_NAME,
    SERVE_AI_LOG_FILE_NAME,
    SERVE_DATA_LOG_FILE_NAME,
)
from k_b.core.dates import DATABASE_DATE_FORMAT

# The name of the logger of cli.py and of every module of commands/, written in each line: one
# name for the command line, whichever of its modules logs.
LOGGER_NAME = "k_b.cli"
# The log of every run, successes and failures, apart from the import journals: those are written
# only when an import reaches the end of its writing in the base.
LOG_FILE_PATH = Path(LOGS_DIR_NAME) / LOG_FILE_NAME
# The log of kb serve-data, apart: a long run that shared kb.log would keep writing in the file of the
# day before once a rotation done by kb collect or kb import has renamed it (docs/specs-api.md,
# "Journal").
SERVE_DATA_LOG_FILE_PATH = Path(LOGS_DIR_NAME) / SERVE_DATA_LOG_FILE_NAME
# The log of kb serve-ai, apart for the same reason: a long run, beside kb serve-data.
SERVE_AI_LOG_FILE_PATH = Path(LOGS_DIR_NAME) / SERVE_AI_LOG_FILE_NAME
LOG_LINE_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
# The HTTP client of the AI API logs each request at INFO, with its URL (the resource of the
# provider) and without the id of the request of kb serve-ai: from WARNING only.
HTTP_CLIENT_LOGGER_NAME = "httpx2"
# The Azure SDK logs each request at INFO, with its URL, which names the blob of a transfer: the
# title of a clip (jobs/exchange_storage.py, #412). At WARNING, it quotes the text of an answer,
# unescaped (the failure of a token, a value of the storage), and kb logs each failure itself: from
# ERROR only, where it writes fixed texts (review of #412, decided by time-knight on 2026-11-06).
AZURE_SDK_LOGGER_NAME = "azure"
# The HTTP client under the Azure SDK, and the BigQuery client: at WARNING, it may quote a whole URL
# (urllib3/connection.py, "Failed to parse headers"), the one of a blob. From ERROR only.
URLLIB3_LOGGER_NAME = "urllib3"
# The lowest level each library logs at in the log of kb.
LIBRARY_LOG_LEVELS = {
    HTTP_CLIENT_LOGGER_NAME: logging.WARNING,
    AZURE_SDK_LOGGER_NAME: logging.ERROR,
    URLLIB3_LOGGER_NAME: logging.ERROR,
}

logger = logging.getLogger(LOGGER_NAME)


@contextmanager
def logging_to(
    data_dir: Path, log_file_path: Path | None = LOG_FILE_PATH
) -> Iterator[None]:
    """Log every line of level INFO and above on stderr and, unless log_file_path is None, in a
    file of the data directory, dated in UTC and turned at midnight UTC.

    On exit the handlers are closed and removed, as the tests run kb many times in one
    interpreter."""
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file_path is not None:
        log_path = data_dir / log_file_path
        log_path.parent.mkdir(exist_ok=True)
        handlers.append(
            TimedRotatingFileHandler(
                log_path,
                when="midnight",
                utc=True,
                # A rotation deletes nothing: backupCount counts files, not days. Only the purge
                # deletes a log (purge/run_records.py).
                backupCount=0,
                encoding="utf-8",
            )
        )
    formatter = logging.Formatter(LOG_LINE_FORMAT, datefmt=DATABASE_DATE_FORMAT)
    # The Z of the format says UTC: the time is read in UTC, not in local time.
    formatter.converter = time.gmtime
    root_logger = logging.getLogger()
    previous_level = root_logger.level
    previous_library_levels = {
        name: logging.getLogger(name).level for name in LIBRARY_LOG_LEVELS
    }
    for handler in handlers:
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
    for name, level in LIBRARY_LOG_LEVELS.items():
        logging.getLogger(name).setLevel(level)
    try:
        yield
    finally:
        root_logger.setLevel(previous_level)
        for name, previous_library_level in previous_library_levels.items():
            logging.getLogger(name).setLevel(previous_library_level)
        for handler in handlers:
            root_logger.removeHandler(handler)
            handler.close()


def value_or_log_refusal[ValueT](value_or_refusal: ValueT | str) -> ValueT | None:
    """The value read by a layer, or None after logging why the layer refused it; a str is the
    refusal."""
    if isinstance(value_or_refusal, str):
        logger.error("%s", value_or_refusal)
        return None
    return value_or_refusal


def describe_os_error(error: OSError) -> str:
    """An OSError by its type and its reason, never its text, which names a file (the vault, a
    raw file)."""
    reason = f" ({error.strerror})" if error.strerror else ""
    return f"{type(error).__name__}{reason}"
