"""kb digest: ask the AI API for the digests of the watch, then write the sheet of each subject
in the vault; kb serve-data and kb serve-ai must run."""

import logging
import os
from datetime import UTC, date, datetime
from pathlib import Path

from k_b.commands.exit_codes import ExitCode, find_exit_code
from k_b.commands.run_log import (
    LOGGER_NAME,
    describe_os_error,
    value_or_log_refusal,
)
from k_b.core.config import AI_API_READ_TIMEOUT_SECONDS, DIGEST_SUBJECTS
from k_b.etl.collected_sources import VAULT_DIR_VARIABLE, read_vault_dir
from k_b.post.ai_api_client import (
    AI_API_KEY_VARIABLE,
    AiApiError,
    DigestsResponse,
    build_ai_api_client,
    read_ai_api_client_settings_or_refusal,
    request_digests,
)
from k_b.post.digest_sheets import refuse_written_sheets, write_digest_sheet
from k_b.post.vault_files import VaultEntryRefusedError

logger = logging.getLogger(LOGGER_NAME)


def run_digest() -> int:
    """Read the settings, check the vault, ask the digests, write their sheets; nothing is asked
    while a setting is refused or a sheet of the day is there, so no item is sent for nothing."""
    vault_dir = read_vault_dir(os.environ)
    if vault_dir is None:
        logger.error(
            "%s not set; the digests are written in the vault", VAULT_DIR_VARIABLE
        )
        return ExitCode.NOT_STARTED
    if not vault_dir.is_dir():
        logger.error(
            "%s is not an existing directory; no folder is created", VAULT_DIR_VARIABLE
        )
        return ExitCode.NOT_STARTED
    settings = value_or_log_refusal(read_ai_api_client_settings_or_refusal(os.environ))
    if settings is None:
        return ExitCode.NOT_STARTED
    subject_names = [subject.name for subject in DIGEST_SUBJECTS]
    try:
        refuse_written_sheets(vault_dir, subject_names, read_today())
    except VaultEntryRefusedError as error:
        logger.error("no digest asked: %s", error)
        return ExitCode.NOT_STARTED
    except OSError as error:
        logger.error("no digest asked: %s", describe_os_error(error))
        return ExitCode.FAILED
    logger.info(
        "digests asked of the AI API, read timeout %d seconds",
        AI_API_READ_TIMEOUT_SECONDS,
    )
    try:
        with build_ai_api_client(settings) as http_client:
            response = request_digests(http_client, subject_names)
    except AiApiError as error:
        logger.error("digests not received: %s%s", error, describe_remedy(error))
        return ExitCode.FAILED
    return write_digest_sheets(vault_dir, response)


def read_today() -> date:
    """The UTC day of the run, the day of the sheets."""
    return datetime.now(UTC).date()


def write_digest_sheets(vault_dir: Path, response: DigestsResponse) -> ExitCode:
    """Each sheet in turn, a sheet not written not stopping the others; a subject fails when the
    AI API names it or its sheet is not written."""
    written_count = 0
    failed_count = 0
    for digest in response.digests:
        try:
            sheet = write_digest_sheet(vault_dir, response, digest)
        except (OSError, VaultEntryRefusedError) as error:
            logger.error(
                "%s: sheet not written: %s", digest.subject, describe_error(error)
            )
            failed_count += 1
            continue
        print(f"{digest.subject}: sheet written, {sheet}")
        written_count += 1
    for failed in response.failed_subjects:
        logger.error(
            "%s: digest failed: %s at the stage %s",
            failed.subject,
            failed.error,
            failed.stage,
        )
        failed_count += 1
    print(
        f"digests: {describe_counts(written_count, failed_count)}; {describe_request(response)}"
    )
    return find_exit_code(has_failed=failed_count > 0, has_done=written_count > 0)


def describe_counts(written_count: int, failed_count: int) -> str:
    if written_count == failed_count == 0:
        return "none in the window"
    return f"written {written_count}, failed {failed_count}"


def describe_request(response: DigestsResponse) -> str:
    """The model and the id of the request, to find it in the log of kb serve-ai."""
    return f"model {response.model}, request_id {response.request_id}"


def describe_remedy(error: AiApiError) -> str:
    """The variable to check after a 401: named, never its key."""
    if error.state == "ai_api_unauthorized":
        return f"; the AI API refused the key of {AI_API_KEY_VARIABLE}"
    return ""


def describe_error(error: OSError | VaultEntryRefusedError) -> str:
    """A refused entry of the vault by its state and its path in the vault; an OSError by its
    type and reason, never a path, which names the vault."""
    if isinstance(error, VaultEntryRefusedError):
        return str(error)
    return describe_os_error(error)
