"""kb digest-watch, the command of the job caj-kb-digest-watch (#413): the wake of both APIs,
kb digest, the wake again, kb trend-report, then the publication of veille, which replaces nothing.

The wake goes first: the AI API reads the data API within 10 s, without retry, and the data API
answers 26 s after its first request once at 0 replica (measured by #414). It goes again before
kb trend-report: a digest request lasts up to 200 s, and the 300 s an API stays awake are the
default of Azure Container Apps, not timed."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from k_b.commands.digest_command import run_digest
from k_b.commands.exit_codes import ExitCode, find_exit_code
from k_b.commands.job_routine import RoutineStep, describe_routine, run_routine
from k_b.commands.job_transfers import publish_the_watch
from k_b.commands.run_log import value_or_log_refusal
from k_b.commands.smoke_test_command import (
    AI_API_NAME,
    DATA_API_NAME,
    SmokeTestSettings,
    check_api,
    read_smoke_test_settings_or_refusal,
)
from k_b.commands.trend_report_command import run_trend_report
from k_b.etl.collected_sources import read_vault_dir_or_refusal

DIGEST_WATCH_TITLE = "kb digest-watch"


@dataclass(frozen=True)
class DigestWatchSettings:
    """What the steps of the routine read: the data directory and the environment, given to each
    command; both APIs and the exchange storage, the settings kb smoke-test proves online; the
    vault."""

    data_dir: Path
    environ: Mapping[str, str]
    job: SmokeTestSettings
    vault_dir: Path


def wake_the_apis(settings: DigestWatchSettings) -> int:
    """GET /health of both APIs, which wakes an API at 0 replica; 4 when one of them failed."""
    results = [
        check_api(DATA_API_NAME, settings.job.data_api_url),
        check_api(AI_API_NAME, settings.job.ai_api_url),
    ]
    return find_exit_code(
        has_failed=not all(result.has_passed for result in results),
        has_done=any(result.has_passed for result in results),
    )


# The steps call their function by its name in this module, at the time they run: a test replaces
# it there. A failed wake neither stops kb digest nor counts in the exit code: an API that stays out
# of reach fails the step that follows, which reports it (decided by time-knight on 2026-11-06,
# under Sabine's delegation of 2026-10-15).
DIGEST_WATCH_STEPS: tuple[RoutineStep[DigestWatchSettings], ...] = (
    RoutineStep(
        "wake of the APIs before kb digest",
        lambda settings: wake_the_apis(settings),
        is_counted=False,
    ),
    RoutineStep("kb digest", lambda settings: run_digest(settings.environ)),
    RoutineStep(
        "wake of the APIs before kb trend-report",
        lambda settings: wake_the_apis(settings),
        is_counted=False,
    ),
    RoutineStep(
        "kb trend-report",
        lambda settings: run_trend_report(settings.data_dir, settings.environ),
    ),
    RoutineStep(
        "watch publication",
        lambda settings: publish_the_watch(
            settings.job.exchange_storage, settings.vault_dir
        ),
    ),
)


def run_digest_watch(data_dir: Path, environ: Mapping[str, str]) -> int:
    """Read the settings of the routine, then run its steps; none runs while one is refused."""
    settings = value_or_log_refusal(
        read_digest_watch_settings_or_refusal(data_dir, environ)
    )
    if settings is None:
        return ExitCode.NOT_STARTED
    return run_routine(DIGEST_WATCH_TITLE, DIGEST_WATCH_STEPS, settings)


def describe_digest_watch() -> str:
    """The steps of kb digest-watch, for --dry-run."""
    return describe_routine(DIGEST_WATCH_TITLE, DIGEST_WATCH_STEPS)


def read_digest_watch_settings_or_refusal(
    data_dir: Path, environ: Mapping[str, str]
) -> DigestWatchSettings | str:
    """The settings of the routine, or why one is refused; those of a step are read by the step.
    The URLs of the APIs have the local defaults of kb smoke-test: online, a URL not set fails the
    wake (1), not the start (2)."""
    job = read_smoke_test_settings_or_refusal(environ)
    if isinstance(job, str):
        return job
    vault_dir = read_vault_dir_or_refusal(environ, "veille is published from the vault")
    if isinstance(vault_dir, str):
        return vault_dir
    return DigestWatchSettings(data_dir, environ, job, vault_dir)
