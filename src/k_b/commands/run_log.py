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
    SERVE_WEB_LOG_FILE_NAME,
)
from k_b.core.dates import DATABASE_DATE_FORMAT
from k_b.core.quoting import quote_value
from k_b.core.trace_context import read_current_trace_id

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
# The log of kb serve-web, apart for the same reason.
SERVE_WEB_LOG_FILE_PATH = Path(LOGS_DIR_NAME) / SERVE_WEB_LOG_FILE_NAME
# A line written during a request of an API carries its trace id after the name of the logger:
# `trace_field` is set by TracedFormatter.
LOG_LINE_FORMAT = "%(asctime)s %(levelname)s %(name)s:%(trace_field)s %(message)s"
# The HTTP client of the AI API logs each request at INFO, with its URL (the resource of the
# provider) and without the id of the request of kb serve-ai: from WARNING only.
HTTP_CLIENT_LOGGER_NAME = "httpx2"
# The Azure SDK logs each request at INFO, with its URL, which names the blob of a transfer: the
# title of a clip (exchange/storage.py, #412). At WARNING, it quotes the text of an answer,
# unescaped (the failure of a token, a value of the storage), and kb logs each failure itself: from
# ERROR only, where it writes fixed texts (review of #412, decided by time-knight on 2026-11-06).
AZURE_SDK_LOGGER_NAME = "azure"
# The HTTP client under the Azure SDK, and the BigQuery client: at WARNING, it may quote a whole URL
# (urllib3/connection.py, "Failed to parse headers"), the one of a blob. From ERROR only.
URLLIB3_LOGGER_NAME = "urllib3"
# The driver of PostgreSQL, whose name holds the logger of its pool (psycopg.pool), and the package of
# the pool, whose scheduler logs under its own module (psycopg_pool.sched): at WARNING, they quote
# the text of libpq and the connection (its host, user and base), which kb never logs (#417), and
# kb logs each failure itself, by its type (data_api/errors.py). At ERROR, psycopg writes only the
# failure of a notice callback, and the pool nothing (psycopg 3.3.8, psycopg_pool 3.3.3).
POSTGRESQL_DRIVER_LOGGER_NAME = "psycopg"
POSTGRESQL_POOL_LOGGER_NAME = "psycopg_pool"
# The lowest level each library logs at in the log of kb.
LIBRARY_LOG_LEVELS = {
    HTTP_CLIENT_LOGGER_NAME: logging.WARNING,
    AZURE_SDK_LOGGER_NAME: logging.ERROR,
    URLLIB3_LOGGER_NAME: logging.ERROR,
    POSTGRESQL_DRIVER_LOGGER_NAME: logging.ERROR,
    POSTGRESQL_POOL_LOGGER_NAME: logging.ERROR,
}
# The logger of every module of K-B: a line of any other comes from a library, which may log the
# text of an answer.
KB_LOGGER_NAME = "k_b"
# The length the message of a line of a library is cut to, quotes and escapes included: the line
# is the only copy of the message, as for the failure of a source (etl/extract.py).
MAX_QUOTED_LIBRARY_MESSAGE_LENGTH = 300

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
    formatter = TracedFormatter(LOG_LINE_FORMAT, datefmt=DATABASE_DATE_FORMAT)
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


class TracedFormatter(logging.Formatter):
    """The format of a log line, with the trace id of the request under way, read in the thread
    that logs (core/trace_context.py), nothing out of a request; the message of a library
    quoted."""

    def format(self, record: logging.LogRecord) -> str:
        """The line of the record, its trace field set first; a line of a library from a copy
        with its message quoted."""
        trace_id = read_current_trace_id()
        record.trace_field = "" if trace_id is None else f" trace_id={trace_id}"
        if not is_logged_by_kb(record):
            record = with_message_quoted(record)
        return super().format(record)


def is_logged_by_kb(record: logging.LogRecord) -> bool:
    """Whether a logger of K-B wrote the record: kb quotes the values it logs itself."""
    return record.name == KB_LOGGER_NAME or record.name.startswith(f"{KB_LOGGER_NAME}.")


def with_message_quoted(record: logging.LogRecord) -> logging.LogRecord:
    """A copy of the record, its message escaped and cut by quote_value: a line break a library
    logs writes no line of its own (conventions.md, rule 3). The record itself is left as it is
    for the other handlers."""
    quoted_record = logging.makeLogRecord(record.__dict__)
    quoted_record.msg = quote_value(
        record.getMessage(), MAX_QUOTED_LIBRARY_MESSAGE_LENGTH
    )
    quoted_record.args = None
    return quoted_record


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
