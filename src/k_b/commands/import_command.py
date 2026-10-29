"""kb import: read the raw files not imported yet and write them into the database."""

import logging
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from k_b.commands.batch_summary import describe_duration, render_rule, render_table
from k_b.commands.exit_codes import ExitCode
from k_b.commands.run_log import LOGGER_NAME, describe_os_error
from k_b.core.config import GITHUB_TRACKED_REPOSITORIES
from k_b.core.quoting import quote_value
from k_b.database.connection import MissingDatabaseError
from k_b.database.writing import KindWithoutTableError, UnknownSourceError
from k_b.etl.pipeline import (
    ImportLogExistsError,
    ImportOutcome,
    SourceImport,
    import_raw_files,
    purge_superseded_raw,
)
from k_b.etl.raw_store import (
    AUTOMATED_WATCH_DIR_NAME,
    SELECTED_LIBRARY_DIR_NAME,
    make_source_folder_key,
)
from k_b.etl.source_kinds import SOURCE_KINDS
from k_b.etl.sources import cisa_kev, zotero

logger = logging.getLogger(LOGGER_NAME)

# The state catalogs: of each, only the last raw file imported is kept (ADR of 2026-10-19).
LATEST_ONLY_FOLDER_KEYS = (
    make_source_folder_key(SELECTED_LIBRARY_DIR_NAME, zotero.FOLDER_PREFIX),
    make_source_folder_key(AUTOMATED_WATCH_DIR_NAME, cisa_kev.FOLDER_PREFIX),
)
# The name of a source folder kb writes; another name, read from raw/, is quoted.
SOURCE_NAME = re.compile(r"[a-z0-9_]+")
IMPORT_SUMMARY_HEADER = ("source", "raw read", "written", "left out", "rejected")


def run_import(data_dir: Path) -> int:
    """Run the import, print its summary, then purge the raw files superseded; before the purge,
    so that whatever stops it (an error, Ctrl-C) leaves the summary of the import committed."""
    imported_at = datetime.now(UTC).replace(microsecond=0)
    logger.info("import started")
    started = monotonic()
    try:
        outcome = import_raw_files(
            data_dir, SOURCE_KINDS, GITHUB_TRACKED_REPOSITORIES, imported_at
        )
    except MissingDatabaseError as error:
        logger.error("%s; create it with kb create-db", error)
        return ExitCode.NOT_STARTED
    except ImportLogExistsError as error:
        logger.error("%s; run kb import again", error)
        return ExitCode.NOT_STARTED
    except (
        sqlite3.Error,
        OSError,
        UnknownSourceError,
        KindWithoutTableError,
    ) as error:
        logger.error("%s: %s", type(error).__name__, error)
        return ExitCode.FAILED
    logger.info("import finished in %s", describe_duration(monotonic() - started))
    print(render_import_summary(outcome))
    deleted_count: int | None = None
    purge_error: Exception | None = None
    try:
        deleted_count = purge_superseded_raw(data_dir, LATEST_ONLY_FOLDER_KEYS)
    except (sqlite3.Error, OSError, ValueError) as error:
        purge_error = error
    finally:
        # The log last, even when the purge is stopped.
        print(render_import_end(outcome.log_path, deleted_count))
    if purge_error is not None:
        # The type, and the reason of an OSError, never the name of a raw file.
        logger.error(
            "import committed, raw purge failed: %s; run kb import again",
            describe_os_error(purge_error)
            if isinstance(purge_error, OSError)
            else type(purge_error).__name__,
        )
        return ExitCode.FAILED
    return ExitCode.SUCCEEDED


def render_import_summary(outcome: ImportOutcome) -> str:
    """The summary after the end line: a row per source and the total, the trend rows of
    gh_archive apart from the items, the sources left unread, then the withdrawals."""
    summary = outcome.summary
    total = (
        "total",
        str(summary.read_count),
        str(summary.item_count),
        str(summary.discard_count),
        str(summary.rejection_count),
    )
    rows = [
        IMPORT_SUMMARY_HEADER,
        *(
            describe_source_import(source_name, source_import)
            for source_name, source_import in summary.by_source.items()
        ),
        total,
    ]
    if summary.trend_count:
        rows.append(("", "", f"+ {summary.trend_count} trend rows", "", ""))
    table = render_table(rows, right_aligned=frozenset({1, 2, 3, 4}))
    total_position = len(summary.by_source) + 1
    lines = [
        "",
        "Import summary",
        "",
        *table[:total_position],
        render_rule(table),
        *table[total_position:],
    ]
    if outcome.unread_sources:
        lines += [
            "",
            "Not imported (no reader, read by kb write-tops):",
            *(f"  {describe_source_name(name)}" for name in outcome.unread_sources),
        ]
    lines += [
        "",
        (
            "Withdrawn (vulnerabilities, Zotero entries, highlights):"
            f" {summary.withdrawn_count}"
        ),
    ]
    return "\n".join(lines)


def render_import_end(log_path: Path, deleted_count: int | None) -> str:
    """After the purge: the raw files it deleted (no line when it did not end), then the log."""
    lines = [f"Log: {log_path}"]
    if deleted_count is not None:
        lines.insert(
            0, f"Older raw files deleted (a newer one replaces them): {deleted_count}"
        )
    return "\n".join(lines)


def describe_source_import(
    source_name: str, source_import: SourceImport
) -> tuple[str, str, str, str, str]:
    """A source of trends (gh_archive) writes trend rows, not items: its written cell says so."""
    written = (
        f"{source_import.trend_count} trend rows"
        if source_import.writes_trends
        else str(source_import.item_count)
    )
    return (
        describe_source_name(source_name),
        str(source_import.read_count),
        written,
        str(source_import.discard_count),
        str(source_import.rejection_count),
    )


def describe_source_name(source_name: str) -> str:
    return (
        source_name if SOURCE_NAME.fullmatch(source_name) else quote_value(source_name)
    )
