"""kb digest: ask the AI API for the digests of the watch, then write the sheet of each subject
in the vault; kb serve-data and kb serve-ai must run."""

import logging
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from functools import partial
from pathlib import Path
from time import monotonic
from typing import NamedTuple

from k_b.commands.batch_summary import (
    COLUMN_GAP,
    describe_duration,
    render_rule,
    render_table,
)
from k_b.commands.exit_codes import ExitCode, find_exit_code
from k_b.commands.run_log import (
    LOGGER_NAME,
    describe_os_error,
    value_or_log_refusal,
)
from k_b.commands.wait_display import showing_the_wait
from k_b.core.config import (
    AI_API_READ_TIMEOUT_SECONDS,
    DIGEST_SUBJECTS,
    MAX_DIGEST_WINDOW_DAYS,
)
from k_b.core.dates import format_date
from k_b.etl.collected_sources import read_vault_dir_or_refusal
from k_b.post.ai_api_client import (
    DIGEST_KEY_VARIABLE,
    AiApiError,
    DigestsResponse,
    build_ai_api_client,
    describe_remedy,
    read_ai_api_client_settings_or_refusal,
    request_digests,
)
from k_b.post.digest_sheets import (
    read_subject_starts,
    refuse_written_sheets,
    write_digest_sheet,
    write_empty_sheet,
)
from k_b.post.vault_files import VaultEntryRefusedError

logger = logging.getLogger(LOGGER_NAME)

SHEET_WRITTEN = "sheet written"
NO_ITEM_SHEET_WRITTEN = "no item, sheet written"


class SummaryRow(NamedTuple):
    """A row of the summary of kb digest; sheet is empty when the sheet is not written."""

    subject: str
    status: str
    sheet: str


SUMMARY_HEADER = SummaryRow("subject", "status", "sheet")
SUMMARY_TITLE = "Digest summary"


def run_digest(environ: Mapping[str, str]) -> int:
    """Read the settings, check the vault, ask the digests, write their sheets; nothing is asked
    while a setting is refused or a sheet of the day is there, so no item is sent for nothing."""
    vault_dir = value_or_log_refusal(
        read_vault_dir_or_refusal(environ, "the digests are written in the vault")
    )
    if vault_dir is None:
        return ExitCode.NOT_STARTED
    settings = value_or_log_refusal(
        read_ai_api_client_settings_or_refusal(environ, DIGEST_KEY_VARIABLE)
    )
    if settings is None:
        return ExitCode.NOT_STARTED
    subject_names = [subject.name for subject in DIGEST_SUBJECTS]
    try:
        refuse_written_sheets(vault_dir, subject_names, read_today())
        since_by_subject = read_subject_starts(
            vault_dir, subject_names, datetime.now(UTC)
        )
    except VaultEntryRefusedError as error:
        logger.error("no digest asked: %s", error)
        return ExitCode.NOT_STARTED
    except OSError as error:
        logger.error("no digest asked: %s", describe_os_error(error))
        return ExitCode.FAILED
    logger.info("digest started: %d subjects asked", len(subject_names))
    logger.info(
        "digests asked of the AI API, read timeout %d seconds",
        AI_API_READ_TIMEOUT_SECONDS,
    )
    started = monotonic()
    try:
        with (
            build_ai_api_client(settings) as http_client,
            showing_the_wait("the digests", AI_API_READ_TIMEOUT_SECONDS),
        ):
            response = request_digests(http_client, subject_names, since_by_subject)
    except AiApiError as error:
        logger.error(
            "digests not received: %s%s",
            error,
            describe_remedy(error, DIGEST_KEY_VARIABLE),
        )
        return ExitCode.FAILED
    log_starts_brought_to_the_bound(response, since_by_subject)
    if response.items_in == 0:
        # An empty base or an import not run: a sheet would move a start over items not read
        # (decision of Sabine of 2026-11-11).
        logger.warning("no item read: no sheet written, the start of each subject kept")
        rows = []
    else:
        rows = write_digest_sheets(vault_dir, response)
    logger.info("digest finished in %s", describe_duration(monotonic() - started))
    written_count = sum(1 for row in rows if row.sheet)
    failed_count = len(rows) - written_count
    print(render_digest_summary(response, rows, written_count, failed_count))
    # A blank line after the result, apart from what follows (make's line of an error):
    # decision of Sabine of 2026-10-29, as for kb collect.
    print()
    return find_exit_code(has_failed=failed_count > 0, has_done=written_count > 0)


def read_today() -> date:
    """The UTC day of the run, the day of the sheets."""
    return datetime.now(UTC).date()


def log_starts_brought_to_the_bound(
    response: DigestsResponse, since_by_subject: Mapping[str, datetime]
) -> None:
    """A start the AI API brought to its bound: the items before it are in no sheet."""
    for subject, start in since_by_subject.items():
        applied = response.since_by_subject[subject]
        if applied > start:
            logger.warning(
                "%s: start %s brought to %s, the bound of %d days",
                subject,
                format_date(start),
                format_date(applied),
                MAX_DIGEST_WINDOW_DAYS,
            )


def write_digest_sheets(vault_dir: Path, response: DigestsResponse) -> list[SummaryRow]:
    """Each sheet in turn, a sheet not written not stopping the others; a subject fails when the
    AI API names it or its sheet is not written. One row of the summary per subject; a subject
    without items gets its sheet, the start of its next digest."""
    rows: list[SummaryRow] = []
    for digest in response.digests:
        rows.append(
            write_one_sheet(
                digest.subject,
                SHEET_WRITTEN,
                partial(write_digest_sheet, vault_dir, response, digest),
            )
        )
    for subject in response.subjects_without_items:
        rows.append(
            write_one_sheet(
                subject,
                NO_ITEM_SHEET_WRITTEN,
                partial(write_empty_sheet, vault_dir, response, subject),
            )
        )
    for failed in response.failed_subjects:
        logger.error(
            "%s: digest failed: %s at the stage %s",
            failed.subject,
            failed.error,
            failed.stage,
        )
        rows.append(SummaryRow(failed.subject, "digest failed", ""))
    return rows


def write_one_sheet(subject: str, status: str, write: Callable[[], str]) -> SummaryRow:
    """The row of a sheet written by write, or not written: logged, and not stopping the
    others."""
    try:
        sheet = write()
    except (OSError, VaultEntryRefusedError) as error:
        logger.error("%s: sheet not written: %s", subject, describe_error(error))
        return SummaryRow(subject, "sheet not written", "")
    return SummaryRow(subject, status, sheet)


def render_digest_summary(
    response: DigestsResponse,
    rows: list[SummaryRow],
    written_count: int,
    failed_count: int,
) -> str:
    """The summary after the end line: the window, a row per subject and the total, then the
    model and the id of the request, last, the reference to give when something goes wrong."""
    window = response.window
    table = render_table([SUMMARY_HEADER, *rows])
    # The total spans the status and the sheet: out of the table, under the status.
    subject_width = max(len(row.subject) for row in [SUMMARY_HEADER, *rows])
    total = describe_counts(written_count, failed_count)
    since, until = window.since.date().isoformat(), window.until.date().isoformat()
    return "\n".join(
        [
            "",
            # Underlined, the title of the block (decision of Sabine of 2026-10-29).
            SUMMARY_TITLE,
            "-" * len(SUMMARY_TITLE),
            f"Window: {since} → {until}, {response.items_in} items read",
            "",
            *table,
            render_rule(table),
            f"{'total':<{subject_width}}{COLUMN_GAP}{total}",
            "",
            f"Model: {response.model}",
            f"Request id: {response.request_id}",
        ]
    )


def describe_counts(written_count: int, failed_count: int) -> str:
    # Each subject has a row: written, without item and written, or failed (#565).
    return f"written {written_count}, failed {failed_count}"


def describe_error(error: OSError | VaultEntryRefusedError) -> str:
    """A refused entry of the vault by its state and its path in the vault; an OSError by its
    type and reason, never a path, which names the vault."""
    if isinstance(error, VaultEntryRefusedError):
        return str(error)
    return describe_os_error(error)
