"""The log of a run of kb: where it goes, its format, and the refusals of the layers it records."""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from k_b.core.config import LOG_FILES_KEPT
from k_b.database.dates import DATABASE_DATE_FORMAT

# The name of the logger of cli.py and of every module of commands/, written in each line: one
# name for the command line, whichever of its modules logs.
LOGGER_NAME = "k_b.cli"
# The log of every run, successes and failures, apart from the import logs: those are written
# only when an import reaches the end of its writing in the base.
LOG_FILE_PATH = Path("logs") / "kb.log"
# The log of kb serve, apart: a long run that shared kb.log would keep writing in the file of the
# day before once a rotation done by kb collect or kb import has renamed it (docs/specs-api.md,
# "Journal").
SERVE_LOG_FILE_PATH = Path("logs") / "kb-serve.log"
# The log of kb serve-ai, apart for the same reason: a long run, beside kb serve.
SERVE_AI_LOG_FILE_PATH = Path("logs") / "kb-serve-ai.log"
LOG_LINE_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
# The HTTP client of the AI API logs each request at INFO, with its URL (the resource of the
# provider) and without the id of the request of kb serve-ai: from WARNING only.
HTTP_CLIENT_LOGGER_NAME = "httpx2"

logger = logging.getLogger(LOGGER_NAME)


@contextmanager
def logging_to(
    data_dir: Path, log_file_path: Path | None = LOG_FILE_PATH
) -> Iterator[None]:
    """Log every line of level INFO and above on stderr and, unless log_file_path is None, in
    the log file of the data directory (logs/kb.log, logs/kb-serve.log for kb serve,
    logs/kb-serve-ai.log for kb serve-ai), dated
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
    http_client_logger = logging.getLogger(HTTP_CLIENT_LOGGER_NAME)
    previous_http_client_level = http_client_logger.level
    for handler in handlers:
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
    http_client_logger.setLevel(logging.WARNING)
    try:
        yield
    finally:
        root_logger.setLevel(previous_level)
        http_client_logger.setLevel(previous_http_client_level)
        for handler in handlers:
            root_logger.removeHandler(handler)
            handler.close()


def value_or_log_refusal[ValueT](value_or_refusal: ValueT | str) -> ValueT | None:
    """The value read by a layer, or None after logging why the layer refused it; the caller
    decides to stop. The value read is never a str: a str is the refusal."""
    if isinstance(value_or_refusal, str):
        logger.error("%s", value_or_refusal)
        return None
    return value_or_refusal
