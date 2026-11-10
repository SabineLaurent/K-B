"""kb download-watch-sheets, run on the Mac by make download-watch-sheets: each sheet of the
container watch that veille lacks is copied there, by the Entra account of az login.

A sheet in veille is never downloaded nor replaced, changed on the Mac or not; one deleted there
comes back at the next run, while watch holds it (README). The steps: the listing and the names
(jobs/watch_download.py), then the writing, which follows no symbolic link (post/vault_files.py)."""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from azure.storage.blob import ContainerClient

from k_b.commands.exit_codes import ExitCode, find_exit_code
from k_b.commands.run_log import value_or_log_refusal
from k_b.core.config import (
    DIGEST_SUBJECTS,
    TOPS_DIR_NAME,
    TRENDS_DIR_NAME,
    WATCH_CONTAINER,
    WATCH_DIR_NAME,
)
from k_b.core.quoting import name_os_error
from k_b.etl.collected_sources import read_vault_dir_or_refusal
from k_b.etl.source_kinds import TOPS
from k_b.jobs.exchange_storage import (
    EXCHANGE_BLOB_URL_VARIABLE,
    ExchangeStorageError,
    build_cli_credential,
    check_identity,
    find_exchange_blob_url_refusal,
    naming_storage_errors,
    open_container_client,
)
from k_b.jobs.watch_download import (
    DownloadResult,
    ListedSheet,
    describe_download_result,
    download_sheet,
    find_sheet_text_refusal,
    list_watch_sheets,
    refuse_blob,
)
from k_b.post.vault_files import (
    VaultEntryRefusedError,
    has_sheet,
    refuse_linked_folders,
    write_new_sheet,
)

logger = logging.getLogger(__name__)

# The folders of veille kb writes a sheet in, as publish_watch names them in watch: one per subject
# (post/digest_sheets.py), one per top (post/top_sheets.py), the trend reports
# (post/trend_report_sheets.py). A test compares them with the folders of those writers.
WATCH_SHEET_FOLDERS = frozenset(
    {subject.name for subject in DIGEST_SUBJECTS}
    | {f"{TOPS_DIR_NAME}/{top.name}" for top in TOPS}
    | {TRENDS_DIR_NAME}
)


@dataclass(frozen=True)
class WatchDownloadSettings:
    """The account of the exchange storage, and the vault the sheets are copied to."""

    account_url: str
    vault_dir: Path


def run_download_watch_sheets(environ: Mapping[str, str]) -> int:
    """Copy to veille each sheet of watch it lacks; 2 when a setting is refused, 1 when the storage
    is not reached, else the code of the sheets (find_exit_code)."""
    settings = value_or_log_refusal(read_watch_download_settings_or_refusal(environ))
    if settings is None:
        return ExitCode.NOT_STARTED
    try:
        with (
            naming_storage_errors(),
            build_cli_credential() as credential,
            open_container_client(
                settings.account_url, WATCH_CONTAINER, credential
            ) as container_client,
        ):
            check_identity(credential)
            result = download_watch(container_client, settings.vault_dir)
    except ExchangeStorageError as error:
        logger.error("watch download: not run: %s", error)
        return ExitCode.FAILED
    summary = describe_download_result(result)
    logger.info("watch download: %s", summary)
    print(summary)
    return find_exit_code(has_failed=result.has_failed, has_done=result.has_done)


def read_watch_download_settings_or_refusal(
    environ: Mapping[str, str],
) -> WatchDownloadSettings | str:
    """The settings of the download, or why one is refused; no AZURE_CLIENT_ID, as the Mac acts by
    the account of az login."""
    refusal = find_exchange_blob_url_refusal(environ)
    if refusal is not None:
        return refusal
    vault_dir = read_vault_dir_or_refusal(
        environ, "the sheets of watch are copied to its veille folder"
    )
    if isinstance(vault_dir, str):
        return vault_dir
    return WatchDownloadSettings(environ[EXCHANGE_BLOB_URL_VARIABLE], vault_dir)


def download_watch(
    container_client: ContainerClient, vault_dir: Path
) -> DownloadResult:
    """Copy each sheet of the listing that veille lacks; a blob refused stops none, an error of
    the storage stops the download, the rest copied by the next run."""
    result = DownloadResult()
    try:
        for sheet in list_watch_sheets(container_client, WATCH_SHEET_FOLDERS, result):
            copy_sheet(container_client, vault_dir, sheet, result)
    except ExchangeStorageError as error:
        logger.error("watch download: stopped: %s", error)
        result.storage_error = error
    return result


def copy_sheet(
    container_client: ContainerClient,
    vault_dir: Path,
    sheet: ListedSheet,
    result: DownloadResult,
) -> None:
    """Copy the sheet unless veille holds it, checked before its download; a local error is
    counted, by its errno for an OSError, whose text names the file."""
    sheets_dir = vault_dir / WATCH_DIR_NAME / sheet.folder
    sheet_path = sheets_dir / f"{sheet.day}.md"
    try:
        # The links first: lstat follows a link among the folders above the sheet.
        refuse_linked_folders(vault_dir, sheets_dir)
        if has_sheet(sheet_path, vault_dir):
            result.already_there += 1
            return
        content = download_sheet(container_client, sheet)
        if content is None:
            result.left_to_next_run += 1
            return
        refusal = find_sheet_text_refusal(content)
        if refusal is not None:
            refuse_blob(result, sheet.where, refusal)
            return
        text = content.decode("utf-8")
        if write_new_sheet(vault_dir, sheets_dir, sheet_path, text):
            result.copied += 1
        else:
            result.already_there += 1
    except VaultEntryRefusedError as error:
        # Its text names the entry by its path in the vault, made of a name of the closed list.
        logger.error("watch download: %s not written: %s", sheet.where, error)
        result.failed["vault_entry_refused"] += 1
    except OSError as error:
        name = name_os_error(error)
        logger.error("watch download: %s not written: %s", sheet.where, name)
        result.failed[name] += 1
