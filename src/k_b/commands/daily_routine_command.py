"""kb daily-routine, the command of the job caj-kb-daily-routine (#413): the mirror of the clips,
kb collect, kb import unless kb collect exits with 1 or 2, kb purge, kb write-tops, then the
publication of veille, which replaces nothing."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from k_b.commands.collect_command import run_collect
from k_b.commands.exit_codes import ExitCode
from k_b.commands.import_command import run_import
from k_b.commands.job_routine import (
    NotRunAfter,
    RoutineStep,
    describe_routine,
    run_routine,
)
from k_b.commands.job_transfers import mirror_the_clips, publish_the_watch
from k_b.commands.purge_command import run_purge
from k_b.commands.run_log import value_or_log_refusal
from k_b.commands.write_tops_command import run_write_tops
from k_b.etl.collected_sources import read_vault_dir_or_refusal
from k_b.exchange.storage import (
    ExchangeStorageSettings,
    read_exchange_storage_settings_or_refusal,
)

DAILY_ROUTINE_TITLE = "kb daily-routine"


@dataclass(frozen=True)
class DailyRoutineSettings:
    """What the steps of the routine read: the data directory and the environment, given to each
    command, the exchange storage with the identity of the job, and the vault."""

    data_dir: Path
    environ: Mapping[str, str]
    exchange_storage: ExchangeStorageSettings
    vault_dir: Path


# The steps call their function by its name in this module, at the time they run: a test replaces
# it there.
DAILY_ROUTINE_STEPS: tuple[RoutineStep[DailyRoutineSettings], ...] = (
    RoutineStep(
        "clip mirror",
        lambda settings: mirror_the_clips(
            settings.exchange_storage, settings.vault_dir
        ),
    ),
    # The copy of the Zotero library comes here, between the mirror and kb collect (#425).
    RoutineStep(
        "kb collect", lambda settings: run_collect(settings.data_dir, settings.environ)
    ),
    RoutineStep(
        "kb import",
        lambda settings: run_import(settings.data_dir, settings.environ),
        NotRunAfter("kb collect", frozenset({ExitCode.FAILED, ExitCode.NOT_STARTED})),
    ),
    # Even after an import that fails or is not run: it committed nothing, and the purge reads the
    # base of the last import committed (decision of Sabine of 2026-11-10, #540).
    RoutineStep(
        "kb purge", lambda settings: run_purge(settings.data_dir, settings.environ)
    ),
    RoutineStep(
        "kb write-tops",
        lambda settings: run_write_tops(settings.data_dir, settings.environ),
    ),
    RoutineStep(
        "watch publication",
        lambda settings: publish_the_watch(
            settings.exchange_storage, settings.vault_dir
        ),
    ),
)


def run_daily_routine(data_dir: Path, environ: Mapping[str, str]) -> int:
    """Read the settings of the routine, then run its steps; none runs while one is refused."""
    settings = value_or_log_refusal(
        read_daily_routine_settings_or_refusal(data_dir, environ)
    )
    if settings is None:
        return ExitCode.NOT_STARTED
    return run_routine(DAILY_ROUTINE_TITLE, DAILY_ROUTINE_STEPS, settings)


def describe_daily_routine() -> str:
    """The steps of kb daily-routine, for --dry-run."""
    return describe_routine(DAILY_ROUTINE_TITLE, DAILY_ROUTINE_STEPS)


def read_daily_routine_settings_or_refusal(
    data_dir: Path, environ: Mapping[str, str]
) -> DailyRoutineSettings | str:
    """The settings of the routine, or why one is refused; those of a step are read by the step."""
    exchange_storage = read_exchange_storage_settings_or_refusal(environ)
    if isinstance(exchange_storage, str):
        return exchange_storage
    vault_dir = read_vault_dir_or_refusal(
        environ, "the clips are mirrored to the vault, and veille published from it"
    )
    if isinstance(vault_dir, str):
        return vault_dir
    return DailyRoutineSettings(data_dir, environ, exchange_storage, vault_dir)
