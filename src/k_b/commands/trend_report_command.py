"""kb trend-report: ask the AI API for the trend report of the GH Archive windows after the
previous report, write it in the vault, then add it to the register; kb serve-data and kb serve-ai
must run (docs/tendances.md)."""

import logging
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from time import monotonic
from typing import NamedTuple

from pydantic import ValidationError

from k_b.commands.batch_summary import describe_duration
from k_b.commands.exit_codes import ExitCode
from k_b.commands.run_log import (
    LOGGER_NAME,
    describe_os_error,
    value_or_log_refusal,
)
from k_b.commands.wait_display import showing_the_wait
from k_b.core.config import AI_API_READ_TIMEOUT_SECONDS
from k_b.core.quoting import locate_first_error
from k_b.etl.collected_sources import read_vault_dir_or_refusal
from k_b.post.ai_api_client import (
    AiApiClientSettings,
    AiApiError,
    build_ai_api_client,
    describe_remedy,
    read_ai_api_client_settings_or_refusal,
)
from k_b.post.trend_report_client import (
    TREND_REPORT_KEY_VARIABLE,
    TrendReportResponse,
    request_trend_report,
)
from k_b.post.trend_report_registry import (
    TREND_REPORTS_FILENAME,
    InvalidTrendRegistryError,
    TrendReportEntry,
    append_trend_report,
    load_trend_reports,
)
from k_b.post.trend_report_sheets import (
    ReportFile,
    locate_report_file,
    refuse_written_sheet,
    write_trend_report_sheet,
)
from k_b.post.vault_files import VaultEntryRefusedError

logger = logging.getLogger(LOGGER_NAME)

SUMMARY_TITLE = "Trend report summary"


class Preparation(NamedTuple):
    """What the request needs, once every check before it has passed."""

    report_file: ReportFile
    settings: AiApiClientSettings
    entries: list[TrendReportEntry]


def run_trend_report(data_dir: Path, environ: Mapping[str, str]) -> int:
    """Check, ask, write the report, then the register; nothing is asked while a setting, the
    register or the report of the day is refused. The instant of the run, read once, gives the
    day of the report and the time of its entry."""
    generated = read_now()
    preparation = prepare_request(data_dir, environ, generated.date())
    if isinstance(preparation, ExitCode):
        return preparation
    previous = preparation.entries[-1] if preparation.entries else None
    logger.info("trend report started: %s", describe_previous(previous))
    started = monotonic()
    response = ask_trend_report(preparation.settings, previous, generated.date())
    if response is None:
        return ExitCode.FAILED
    if not response.period.windows:
        report_empty_period(response, previous)
        return ExitCode.SUCCEEDED
    if response.choice_failure is not None:
        # The report stays factual and the period moves on (decision of Sabine, 2026-10-29); a
        # refused key (llm_unavailable) is no longer silent.
        logger.warning(
            "choice of the model not made: %s, request_id %s",
            response.choice_failure,
            response.request_id,
        )
    for number, chosen in enumerate(response.chosen):
        if chosen.writing_failure is not None:
            # By its place, never its name: the texts are left out, the report written.
            logger.warning(
                "writing of chosen.%d not made: %s, request_id %s",
                number,
                chosen.writing_failure,
                response.request_id,
            )
    entry = make_entry(preparation.report_file, response, generated)
    if entry is None:
        return ExitCode.FAILED
    if not write_sheet(preparation.report_file, response, generated):
        return ExitCode.FAILED
    if not add_entry(data_dir, preparation.entries, entry):
        return ExitCode.FAILED
    logger.info("trend report finished in %s", describe_duration(monotonic() - started))
    print(render_trend_report_summary(response, entry.file))
    # A blank line after the result, apart from what follows, as for kb digest.
    print()
    return ExitCode.SUCCEEDED


def read_now() -> datetime:
    return datetime.now(UTC)


def prepare_request(
    data_dir: Path, environ: Mapping[str, str], day: date
) -> Preparation | ExitCode:
    """The report of day located, not written yet, the settings and the register; else the code
    to exit with, its reason logged."""
    vault_dir = value_or_log_refusal(
        read_vault_dir_or_refusal(environ, "the trend report is written in the vault")
    )
    if vault_dir is None:
        return ExitCode.NOT_STARTED
    settings = value_or_log_refusal(
        read_ai_api_client_settings_or_refusal(environ, TREND_REPORT_KEY_VARIABLE)
    )
    if settings is None:
        return ExitCode.NOT_STARTED
    report_file = locate_report_file(vault_dir, day)
    try:
        entries = load_trend_reports(data_dir)
        refuse_written_sheet(report_file)
    except (InvalidTrendRegistryError, VaultEntryRefusedError) as error:
        logger.error("no trend report asked: %s", error)
        return ExitCode.NOT_STARTED
    except OSError as error:
        # A folder of the vault that cannot be looked into: as kb digest.
        logger.error("no trend report asked: %s", describe_os_error(error))
        return ExitCode.FAILED
    return Preparation(report_file, settings, entries)


def describe_previous(previous: TrendReportEntry | None) -> str:
    if previous is None:
        return "first report"
    return f"windows after {previous.last_window.isoformat()}"


def ask_trend_report(
    settings: AiApiClientSettings, previous: TrendReportEntry | None, today: date
) -> TrendReportResponse | None:
    """The response, checked; None once its failure is logged."""
    logger.info(
        "trend report asked of the AI API, read timeout %d seconds",
        AI_API_READ_TIMEOUT_SECONDS,
    )
    try:
        with (
            build_ai_api_client(settings) as http_client,
            showing_the_wait("the trend report", AI_API_READ_TIMEOUT_SECONDS),
        ):
            return request_trend_report(
                http_client,
                None if previous is None else previous.last_window,
                None if previous is None else previous.first_window,
                today,
            )
    except AiApiError as error:
        logger.error(
            "trend report not received: %s%s",
            error,
            describe_remedy(error, TREND_REPORT_KEY_VARIABLE),
        )
        return None


def report_empty_period(
    response: TrendReportResponse, previous: TrendReportEntry | None
) -> None:
    """Nothing written: no window in the base, none after the previous report, or a base older
    than the register (restored), each said with the days observed."""
    latest = response.period.latest_window
    # Without a previous report, a period is empty only for a base without a window: the client
    # refuses any other (post/trend_report_client.py).
    if latest is None or previous is None:
        logger.warning("no GH Archive window in the base; nothing written")
        result = "No GH Archive window in the base; nothing written"
    else:
        after = previous.last_window.isoformat()
        if latest < previous.last_window:
            logger.warning(
                "the latest window in the base, %s, is before the last window of %s, %s;"
                " nothing written",
                latest.isoformat(),
                TREND_REPORTS_FILENAME,
                after,
            )
        else:
            logger.info("no window after %s; nothing written", after)
        result = f"No new window after {after}; nothing written"
    print()
    print(result)
    print(f"Request id: {response.request_id}")
    print()


def make_entry(
    report_file: ReportFile, response: TrendReportResponse, generated: datetime
) -> TrendReportEntry | None:
    """The entry of the report in the register, checked as it will be read back, before anything
    is written; None once its refusal is logged."""
    windows = response.period.windows
    try:
        return TrendReportEntry.model_validate(
            {
                # Written YYYY-MM-DD, as read back.
                "first_window": windows[0].isoformat(),
                "last_window": windows[-1].isoformat(),
                "file": report_file.name,
                "written_at": generated,
                "request_id": response.request_id,
                "model": response.model,
                # The response names its model only when the choice is made.
                "choice_made": response.model is not None,
            }
        )
    except ValidationError as error:
        logger.error(
            "trend report not written: its entry of %s is invalid: %s, request_id %s",
            TREND_REPORTS_FILENAME,
            locate_first_error(error),
            response.request_id,
        )
        return None


def write_sheet(
    report_file: ReportFile, response: TrendReportResponse, generated: datetime
) -> bool:
    """Whether the report is written; its failure logged with the request_id."""
    try:
        write_trend_report_sheet(report_file, response, generated)
    except (OSError, VaultEntryRefusedError) as error:
        logger.error(
            "trend report not written: %s, request_id %s",
            describe_error(error),
            response.request_id,
        )
        return False
    logger.info("sheet written: %s", report_file.name)
    return True


def add_entry(
    data_dir: Path, entries: list[TrendReportEntry], entry: TrendReportEntry
) -> bool:
    """Add the report to the register; False once its failure is logged, the report kept."""
    try:
        append_trend_report(data_dir, entries, entry)
    except OSError as error:
        logger.error(
            "sheet written, %s not updated: %s, request_id %s; the next report covers these"
            " windows again",
            TREND_REPORTS_FILENAME,
            describe_os_error(error),
            entry.request_id,
        )
        return False
    return True


def describe_error(error: OSError | VaultEntryRefusedError) -> str:
    """A refused entry of the vault by its state and its path in the vault; an OSError by its
    type and reason, never a path, which names the vault."""
    if isinstance(error, VaultEntryRefusedError):
        return str(error)
    return describe_os_error(error)


def render_trend_report_summary(response: TrendReportResponse, sheet: str) -> str:
    """The summary: the period, the counts of repositories and the report, then the model and the
    id of the request, last, the reference to give when something goes wrong. Never a name."""
    period = response.period
    first, last = period.windows[0].isoformat(), period.windows[-1].isoformat()
    windows = f"{len(period.windows)} windows, {len(period.missing_windows)} missing"
    repositories = (
        f"{len(response.repositories)} meeting a criterion,"
        f" {response.repositories_dropped} dropped"
    )
    return "\n".join(
        [
            "",
            SUMMARY_TITLE,
            "-" * len(SUMMARY_TITLE),
            f"Period: {first} → {last}, {windows}",
            f"Repositories: {repositories}",
            f"Sheet: {sheet}",
            "",
            f"Model: {response.model or 'none'}",
            f"Request id: {response.request_id}",
        ]
    )
