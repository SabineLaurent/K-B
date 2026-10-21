"""kb collect: run the sources chosen and store their raw output in raw/."""

import logging
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from k_b.commands.exit_codes import ExitCode, find_exit_code
from k_b.commands.run_log import LOGGER_NAME, value_or_log_refusal
from k_b.etl.collected_sources import (
    COLLECT_ONLY_VARIABLE,
    VARIABLE_BY_SOURCE_NAME,
    CollectOnly,
    list_collected_sources,
    read_collect_only_or_refusal,
)
from k_b.etl.extract import CollectionOutcome, collect_all_sources
from k_b.etl.raw_store import RAW_DIR_NAME, InvalidCollectionStateError, RawStore
from k_b.etl.source_contract import Source, find_source_kind
from k_b.etl.source_kinds import SOURCE_KINDS
from k_b.etl.sources import github_advisories, github_releases
from k_b.etl.sources.github_api import TOKEN_VARIABLE

logger = logging.getLogger(LOGGER_NAME)

# The kinds whose sources call the GitHub REST API on its primary quota, the one KB_GITHUB_TOKEN
# raises from 60 to 5,000 requests per hour. Not github_most_starred nor github_most_forked: they
# call the search, which has its own quota, apart. Not gh_archive, which reads BigQuery.
GITHUB_CORE_QUOTA_FOLDER_PREFIXES = frozenset(
    {github_releases.FOLDER_PREFIX, github_advisories.FOLDER_PREFIX}
)


def run_collect(data_dir: Path) -> int:
    # The mapping the check reads is the one the sources are created from; the BigQuery client
    # reads os.environ itself.
    environ = os.environ
    collect_only = value_or_log_refusal(
        read_collect_only_or_refusal(environ, SOURCE_KINDS)
    )
    if collect_only is None:
        return ExitCode.NOT_STARTED
    sources = list_collected_sources(
        collect_only, environ, SOURCE_KINDS, RawStore(data_dir)
    )
    log_collection_start(sources, environ)
    try:
        outcome = collect_all_sources(
            sources,
            data_dir / RAW_DIR_NAME,
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


def log_collection_start(sources: Sequence[Source], environ: Mapping[str, str]) -> None:
    """Once, before the first source: the sources run, by the name of their line at the end,
    then, when one of them uses the primary quota of the GitHub API without KB_GITHUB_TOKEN,
    that quota. Of the token, only whether it is set is read, never its value."""
    logger.info("sources to collect: %s", ", ".join(source.name for source in sources))
    if not environ.get(TOKEN_VARIABLE) and any(
        is_github_core_quota_source(source) for source in sources
    ):
        # GitHub Docs, "Rate limits for the REST API", read on 2026-10-19.
        logger.warning(
            "%s not set: the GitHub API allows 60 requests per hour instead of 5,000",
            TOKEN_VARIABLE,
        )


def is_github_core_quota_source(source: Source) -> bool:
    kind = find_source_kind(source.name, SOURCE_KINDS)
    return kind is not None and kind.folder_prefix in GITHUB_CORE_QUOTA_FOLDER_PREFIXES


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
    return find_exit_code(
        has_failed=any(error is not None for error in errors),
        has_done=any(error is None for error in errors),
    )


def describe_outcome(error: Exception | None) -> str:
    return "ok" if error is None else f"failed ({type(error).__name__})"
