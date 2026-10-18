"""kb collect: run the sources chosen and store their raw output in raw/."""

import logging
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from k_b.commands.exit_codes import ExitCode
from k_b.commands.run_log import LOGGER_NAME, value_or_log_refusal
from k_b.etl.collected_sources import (
    COLLECT_ONLY_VARIABLE,
    VARIABLE_BY_SOURCE_NAME,
    CollectOnly,
    list_collected_sources,
    read_collect_only_or_refusal,
)
from k_b.etl.extract import CollectionOutcome, collect_all_sources
from k_b.etl.raw_store import InvalidCollectionStateError
from k_b.etl.source_kinds import SOURCE_KINDS

logger = logging.getLogger(LOGGER_NAME)


def run_collect(data_dir: Path) -> int:
    # The mapping the check reads is the one the sources are created from; the BigQuery client
    # reads os.environ itself.
    environ = os.environ
    collect_only = value_or_log_refusal(
        read_collect_only_or_refusal(environ, SOURCE_KINDS)
    )
    if collect_only is None:
        return ExitCode.NOT_STARTED
    try:
        outcome = collect_all_sources(
            list_collected_sources(collect_only, environ, SOURCE_KINDS),
            data_dir / "raw",
            data_dir,
            datetime.now(UTC),
        )
    except InvalidCollectionStateError as error:
        logger.error("%s", error)
        return ExitCode.NOT_STARTED
    for source_name, source_error in outcome.errors_by_source.items():
        print(f"{source_name}: {describe_outcome(source_error)}")
    print_skipped_sources(collect_only, environ)
    if outcome.state_error is not None:
        print(f"collection_state: {describe_outcome(outcome.state_error)}")
    return find_collection_exit_code(outcome)


def print_skipped_sources(
    collect_only: CollectOnly, environ: Mapping[str, str]
) -> None:
    """One line per source not run: not chosen, or, without KB_COLLECT_ONLY, its variable not
    set. A source chosen without its variable never gets here: read_collect_only_or_refusal
    refuses it."""
    for kind in SOURCE_KINDS:
        if not collect_only.is_collected(kind.folder_prefix):
            print(f"{kind.folder_prefix}: skipped (not in {COLLECT_ONLY_VARIABLE})")
    for source_name, variable in VARIABLE_BY_SOURCE_NAME.items():
        if collect_only.is_collected(source_name) and not environ.get(variable):
            print(f"{source_name}: skipped ({variable} not set)")


def find_collection_exit_code(outcome: CollectionOutcome) -> ExitCode:
    """Partial when some sources failed and the others are kept for good; a state not written
    is a failure, as when every source fails: the next collection starts from the same dates."""
    errors = outcome.errors_by_source.values()
    if outcome.state_error is not None:
        return ExitCode.FAILED
    if all(error is None for error in errors):
        return ExitCode.SUCCEEDED
    if any(error is None for error in errors):
        return ExitCode.PARTIAL_FAILURE
    return ExitCode.FAILED


def describe_outcome(error: Exception | None) -> str:
    return "ok" if error is None else f"failed ({type(error).__name__})"
