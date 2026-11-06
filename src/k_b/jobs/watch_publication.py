"""The publication of veille: each sheet the container lacks is sent to it, at its root, never
replacing a blob (If-None-Match: *); the hidden entries, such as the temporary files
write_file_atomically leaves when its process is killed, and the links are left aside."""

import logging
import os
import stat
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from azure.storage.blob import ContainerClient

from k_b.jobs.clip_mirror import name_os_error
from k_b.jobs.exchange_storage import ExchangeStorageError, naming_storage_errors

logger = logging.getLogger(__name__)

# An upload answered 409 (BlobAlreadyExists) or 412 (the SDK turns it into the same error): the
# blob was created since the listing, by another run.
STATUS_ALREADY_THERE = frozenset({409, 412})


class WatchFolderRefusedError(Exception):
    """The folder veille is a symbolic link: its sheets are not those kb wrote."""


@dataclass
class PublicationResult:
    """The sheets of a publication, counted by outcome, and the error of the storage that stopped
    it."""

    found: int = 0
    sent: int = 0
    already_there: int = 0
    left_aside: int = 0
    failed: Counter[str] = field(default_factory=Counter)
    storage_error: ExchangeStorageError | None = None

    @property
    def has_failed(self) -> bool:
        """Whether a sheet or a folder was not read, or the storage stopped the publication."""
        return bool(self.failed or self.storage_error)

    @property
    def has_done(self) -> bool:
        """Whether a sheet is in the container, sent now or before."""
        return bool(self.sent or self.already_there)


def publish_watch(
    container_client: ContainerClient, watch_dir: Path
) -> PublicationResult:
    """Send each sheet of watch_dir the container lacks; an error of the storage stops the
    publication, the rest is sent by the next run."""
    if watch_dir.is_symlink():
        raise WatchFolderRefusedError(
            f"watch_folder_link: {watch_dir.name} is a symbolic link"
        )
    result = PublicationResult()
    if watch_dir.is_dir():
        send_missing_sheets(container_client, watch_dir, result)
    logger.info(
        "watch publication: %s",
        describe_publication_result(result, container_client.container_name),
    )
    return result


def send_missing_sheets(
    container_client: ContainerClient, watch_dir: Path, result: PublicationResult
) -> None:
    """List the sheets and the blobs, then send each sheet that is not a blob."""
    sheet_names = list_sheet_names(watch_dir, result)
    result.found = len(sheet_names)
    try:
        # list_blob_names does not decode a name the storage sends encoded (azure-storage-blob
        # 12.31.1, _list_blobs_helper.py, BlobNamesPaged): such a name, which kb never writes, is
        # sent again and answered 409.
        with naming_storage_errors():
            published_names = set(container_client.list_blob_names())
        for position, sheet_name in enumerate(sheet_names, start=1):
            if sheet_name in published_names:
                result.already_there += 1
                continue
            where = f"sheet {position} of {len(sheet_names)}"
            send_sheet(container_client, watch_dir, sheet_name, where, result)
    except ExchangeStorageError as error:
        logger.error("watch publication: stopped: %s", error)
        result.storage_error = error


def list_sheet_names(watch_dir: Path, result: PublicationResult) -> list[str]:
    """The path of each regular, visible file under watch_dir, relative and POSIX, in name order;
    a hidden entry or one that is not a regular file is counted, never followed, as a folder that
    cannot be listed."""
    sheet_names = []

    def count_folder_not_listed(error: OSError) -> None:
        """A folder that cannot be listed: its sheets are not sent, which fails the publication."""
        name = name_os_error(error)
        logger.error("watch publication: a folder not listed: %s", name)
        result.failed[name] += 1

    # Not following the links: a link to a folder is listed among the files, then left aside.
    for folder, folder_names, file_names in watch_dir.walk(
        on_error=count_folder_not_listed
    ):
        hidden_folders = [name for name in folder_names if name.startswith(".")]
        result.left_aside += len(hidden_folders)
        folder_names[:] = sorted(set(folder_names) - set(hidden_folders))
        for file_name in sorted(file_names):
            path = folder / file_name
            if file_name.startswith(".") or not is_regular_file(path):
                result.left_aside += 1
                continue
            sheet_names.append(path.relative_to(watch_dir).as_posix())
    return sheet_names


def is_regular_file(path: Path) -> bool:
    """Whether path is a regular file, read by lstat; one removed since the listing is not."""
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except FileNotFoundError:
        return False


def send_sheet(
    container_client: ContainerClient,
    watch_dir: Path,
    sheet_name: str,
    where: str,
    result: PublicationResult,
) -> None:
    """Send the sheet unless a blob of its name exists; a sheet not read is counted by its errno."""
    try:
        content = read_without_following(watch_dir / sheet_name)
    except OSError as error:
        name = name_os_error(error)
        logger.error("watch publication: %s not read: %s", where, name)
        result.failed[name] += 1
        return
    try:
        with naming_storage_errors():
            container_client.upload_blob(sheet_name, content, overwrite=False)
    except ExchangeStorageError as error:
        if error.http_status not in STATUS_ALREADY_THERE:
            raise
        result.already_there += 1
        return
    result.sent += 1


def read_without_following(path: Path) -> bytes:
    """The bytes of the file; O_NOFOLLOW, so that a file replaced by a link is not followed."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as sheet_file:
        return sheet_file.read()


def describe_publication_result(result: PublicationResult, container: str) -> str:
    """3 sheets found: 2 sent, 1 already in watch, 1 left aside, 0 not read."""
    found = f"{result.found} sheet{'' if result.found == 1 else 's'} found"
    not_read = sum(result.failed.values())
    return (
        f"{found}: {result.sent} sent, {result.already_there} already in {container},"
        f" {result.left_aside} left aside, {not_read} not read"
    )
