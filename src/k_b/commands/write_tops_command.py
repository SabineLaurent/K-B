"""kb write-tops: write the sheets of the top rankings in the vault, then delete the rankings they
supersede from raw/ (ADR of 2026-10-19). It runs after kb import: kb collect; kb import;
kb write-tops."""

import logging
import os
from pathlib import Path

from k_b.commands.exit_codes import ExitCode
from k_b.commands.run_log import LOGGER_NAME
from k_b.etl.collected_sources import VAULT_DIR_VARIABLE, read_vault_dir
from k_b.etl.raw_store import RawStore
from k_b.etl.source_kinds import TOPS
from k_b.etl.top_sheets import (
    TopSheetsOutcome,
    VaultEntryRefusedError,
    write_top_sheets,
)

logger = logging.getLogger(LOGGER_NAME)


def run_write_tops(data_dir: Path) -> int:
    """Each top in turn: a top that fails does not stop the other. Without a vault, nothing is
    read nor deleted, and no folder is created: write_file_atomically would create a vault
    misspelt."""
    vault_dir = read_vault_dir(os.environ)
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
    store = RawStore(data_dir)
    has_failed = False
    for top in TOPS:
        try:
            outcome = write_top_sheets(store, vault_dir, top)
        except (OSError, VaultEntryRefusedError) as error:
            logger.error("top sheets failed: %s: %s", top.name, describe_error(error))
            has_failed = True
            continue
        print(f"{top.name} sheets: {describe_outcome(outcome)}")
        has_failed = has_failed or outcome.unreadable_count > 0
    return ExitCode.FAILED if has_failed else ExitCode.SUCCEEDED


def describe_error(error: OSError | VaultEntryRefusedError) -> str:
    """A refused link by its named state and its path in the vault; an OSError by its type and
    its reason, never a path: it names the vault or a raw file."""
    if isinstance(error, VaultEntryRefusedError):
        return str(error)
    reason = f" ({error.strerror})" if error.strerror else ""
    return f"{type(error).__name__}{reason}; run kb write-tops again"


def describe_outcome(outcome: TopSheetsOutcome) -> str:
    if outcome == TopSheetsOutcome(0, 0, 0, 0):
        return "no ranking"
    return (
        f"written {outcome.written_count},"
        f" rankings skipped (sheet of their day exists) {outcome.skipped_count},"
        f" superseded rankings deleted {outcome.deleted_count},"
        f" unreadable rankings kept {outcome.unreadable_count}"
    )
