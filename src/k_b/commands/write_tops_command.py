"""kb write-tops: write the sheets of the top rankings in the vault, then delete the rankings
they supersede from raw/; it runs after kb import."""

import logging
from collections.abc import Mapping
from pathlib import Path
from time import monotonic

from k_b.commands.batch_summary import describe_count, describe_duration
from k_b.commands.exit_codes import ExitCode, find_exit_code
from k_b.commands.run_log import LOGGER_NAME, describe_os_error
from k_b.etl.collected_sources import VAULT_DIR_VARIABLE, read_vault_dir
from k_b.etl.raw_store import RawStore
from k_b.etl.source_kinds import TOPS
from k_b.post.top_sheets import SHEETS_VAULT_PATH, TopSheetsOutcome, write_top_sheets
from k_b.post.vault_files import VaultEntryRefusedError

logger = logging.getLogger(LOGGER_NAME)


def run_write_tops(data_dir: Path, environ: Mapping[str, str]) -> int:
    """Each top in turn, a top that fails not stopping the other; without a vault, nothing is
    read nor deleted, and nothing created, as write_file_atomically would create a vault
    misspelt."""
    vault_dir = read_vault_dir(environ)
    if vault_dir is None:
        logger.error(
            "%s not set; the sheets of the tops are written in the vault",
            VAULT_DIR_VARIABLE,
        )
        return ExitCode.NOT_STARTED
    if not vault_dir.is_dir():
        logger.error(
            "%s is not an existing directory; no folder is created", VAULT_DIR_VARIABLE
        )
        return ExitCode.NOT_STARTED
    logger.info("write-tops started: %s selected", describe_count(len(TOPS), "ranking"))
    started = monotonic()
    store = RawStore(data_dir)
    # The outcome of each top, or the error that stopped it, printed once all are done.
    outcomes: dict[str, TopSheetsOutcome | Exception] = {}
    for top in TOPS:
        try:
            outcomes[top.name] = write_top_sheets(store, vault_dir, top)
        except (OSError, VaultEntryRefusedError) as error:
            logger.error("top sheets failed: %s: %s", top.name, describe_error(error))
            outcomes[top.name] = error
    logger.info("write-tops finished in %s", describe_duration(monotonic() - started))
    for top_name, outcome in outcomes.items():
        print(f"{top_name}: {describe_outcome(outcome)}")
    ended = [
        outcome
        for outcome in outcomes.values()
        if isinstance(outcome, TopSheetsOutcome)
    ]
    # A top stopped may have deleted some rankings before its error: no count, rather than a
    # wrong one.
    if len(ended) == len(outcomes):
        print(
            f"Older raw files deleted: {sum(outcome.deleted_count for outcome in ended)}"
        )
    print(f"Sheets vault path: {SHEETS_VAULT_PATH.as_posix()}/")
    return find_exit_code(
        has_failed=len(ended) < len(outcomes)
        or any(outcome.unreadable_count > 0 for outcome in ended),
        has_done=any(
            outcome.written_count > 0 or outcome.unreadable_count == 0
            for outcome in ended
        ),
    )


def describe_error(error: OSError | VaultEntryRefusedError) -> str:
    """A refused entry of the vault by its state and its path in the vault; an OSError by its
    type and reason, never a path, which names the vault or a raw file."""
    if isinstance(error, VaultEntryRefusedError):
        return str(error)
    return f"{describe_os_error(error)}; run kb write-tops again"


def describe_outcome(outcome: TopSheetsOutcome | Exception) -> str:
    """An error first, then the sheets written, then the sheet of the day already there; the type
    of an error alone, never its message, which names the vault or a raw file."""
    if isinstance(outcome, Exception):
        return f"failed ({type(outcome).__name__})"
    if outcome.unreadable_count > 0:
        return "failed (ranking_unreadable)"
    if outcome.written_count > 0:
        return f"ok, {describe_count(outcome.written_count, 'sheet')} written"
    if outcome.skipped_count > 0:
        return "ok, 0 sheets written, the sheet of the day already exists"
    return "no ranking"
