"""The mirror of the clips: each clip of the container that the Clippings folder of the vault lacks,
or holds older, is copied there and dated as its blob; nothing is deleted.

The SDK has no ifSourceNewer, the option of azcopy the Mac sends the clips with (decision 7 of the
plan of 2026-11-06): it is recoded by the date of the blob against the date of its file. A blob is
named by the title of its clip (etl/sources/clipping.py): never logged, its position in the listing
instead (conventions.md, rule 3)."""

import logging
import os
import stat
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from azure.storage.blob import BlobProperties, ContainerClient

from k_b.core.atomic_write import write_file_atomically
from k_b.core.config import MAX_CLIP_NAME_BYTES
from k_b.core.quoting import name_os_error
from k_b.exchange.storage import (
    ExchangeStorageError,
    download_listed_version,
    naming_storage_errors,
)

logger = logging.getLogger(__name__)

# A blob that is not a clip of the first level of the folder, which etl/sources/clipping.py reads
# alone: left aside, not a failure.
type LeftAsideReason = Literal[
    "blob_in_a_folder", "blob_name_hidden", "blob_not_markdown"
]
# A clip the share cannot hold, or K-B refuses: a failure of the mirror at each run, until its blob
# is removed from the container.
type ClipRefusal = Literal[
    "clip_name_with_backslash",
    "clip_name_with_control_character",
    "clip_name_with_unsupported_character",
    "clip_name_refused_by_azure_files",
    "clip_name_too_long",
    "clip_too_large",
    "local_entry_not_a_file",
]

# The characters Azure Files refuses in a name, but / and \, checked before, and the control
# characters ("Naming and referencing shares, directories, files, and metadata", learn.microsoft.com,
# updated on 2025-02-12, read on 2026-11-06). Its reserved names (CON, NUL, ., ..) are whole names,
# without the extension of a clip.
AZURE_FILES_REFUSED_CHARACTERS = frozenset('":|<>*?')
# The control characters (Cc), wider than the 0x00 to 0x1F Azure Files names: DEL and C1 too.
CONTROL_CATEGORY = "Cc"
# A code point of private use (Co), which Azure Files refuses, and a lone surrogate (Cs), which UTF-8
# cannot encode.
UNSUPPORTED_CATEGORIES = frozenset({"Co", "Cs"})
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
ONE_MICROSECOND = timedelta(microseconds=1)


class ClippingsFolderRefusedError(Exception):
    """The Clippings folder is a symbolic link, which write_file_atomically would follow."""


@dataclass(frozen=True)
class ClipRules:
    """What makes a clip, as etl/sources/clipping.py reads it: its extension and its largest size."""

    extension: str
    max_bytes: int


@dataclass
class MirrorResult:
    """The blobs of a mirror, counted by outcome, and the error of the storage that stopped it."""

    listed: int = 0
    copied: int = 0
    unchanged: int = 0
    left_to_next_run: int = 0
    left_aside: Counter[str] = field(default_factory=Counter)
    refused: Counter[str] = field(default_factory=Counter)
    failed: Counter[str] = field(default_factory=Counter)
    storage_error: ExchangeStorageError | None = None

    @property
    def has_failed(self) -> bool:
        """Whether a clip was refused or not written, or the storage stopped the mirror."""
        return bool(self.refused or self.failed or self.storage_error)

    @property
    def has_done(self) -> bool:
        """Whether a clip is on the share as in the container, copied now or before."""
        return bool(self.copied or self.unchanged)


def mirror_clips(
    container_client: ContainerClient, clippings_dir: Path, rules: ClipRules
) -> MirrorResult:
    """Copy each clip of the container that clippings_dir lacks or holds older; an error of the
    storage stops the mirror, as each request would wait its retries."""
    if clippings_dir.is_symlink():
        raise ClippingsFolderRefusedError(
            f"clippings_folder_link: {clippings_dir.name} is a symbolic link"
        )
    result = MirrorResult()
    try:
        with naming_storage_errors():
            blobs = list(container_client.list_blobs())
        result.listed = len(blobs)
        for position, blob in enumerate(blobs, start=1):
            where = f"blob {position} of {len(blobs)}"
            mirror_blob(container_client, clippings_dir, rules, blob, where, result)
    except ExchangeStorageError as error:
        logger.error("clip mirror: stopped: %s", error)
        result.storage_error = error
    logger.info("clip mirror: %s", describe_mirror_result(result))
    return result


def mirror_blob(
    container_client: ContainerClient,
    clippings_dir: Path,
    rules: ClipRules,
    blob: BlobProperties,
    where: str,
    result: MirrorResult,
) -> None:
    """Leave the blob aside, refuse it, or copy it when newer; a local error is counted by its
    errno, never by its text, which names the file."""
    reason = find_left_aside_reason(blob.name, rules.extension)
    if reason is not None:
        result.left_aside[reason] += 1
        return
    refusal = describe_clip_refusal(blob, rules)
    if refusal is not None:
        refuse_clip(result, where, *refusal)
        return
    try:
        copy_when_newer(
            container_client,
            clippings_dir / blob.name,
            blob,
            rules.max_bytes,
            where,
            result,
        )
    except OSError as error:
        name = name_os_error(error)
        logger.error("clip mirror: %s not written: %s", where, name)
        result.failed[name] += 1


def find_left_aside_reason(name: str, extension: str) -> LeftAsideReason | None:
    """Why a blob is not a clip of the first level: in a folder, hidden, or not Markdown. The
    name .. is hidden, and holds no /: no name left can climb out of the folder."""
    if "/" in name:
        return "blob_in_a_folder"
    if name.startswith("."):
        return "blob_name_hidden"
    if not name.endswith(extension):
        return "blob_not_markdown"
    return None


def find_clip_name_refusal(name: str) -> ClipRefusal | None:
    """Why the share cannot hold the name of a clip, checked as it is written: never normalized."""
    if "\\" in name:
        return "clip_name_with_backslash"
    categories = {unicodedata.category(character) for character in name}
    if CONTROL_CATEGORY in categories:
        return "clip_name_with_control_character"
    if categories & UNSUPPORTED_CATEGORIES:
        return "clip_name_with_unsupported_character"
    if AZURE_FILES_REFUSED_CHARACTERS.intersection(name):
        return "clip_name_refused_by_azure_files"
    if count_name_bytes(name) > MAX_CLIP_NAME_BYTES:
        return "clip_name_too_long"
    return None


def count_name_bytes(name: str) -> int:
    """The length of the name in UTF-8; a lone surrogate, refused before, would count 3 bytes."""
    return len(name.encode("utf-8", "surrogatepass"))


def describe_clip_refusal(
    blob: BlobProperties, rules: ClipRules
) -> tuple[ClipRefusal, str] | None:
    """Why the clip is refused, with its measure; its size is the one listed, as the download asks
    for the version listed."""
    refusal = find_clip_name_refusal(blob.name)
    if refusal == "clip_name_too_long":
        measure = (
            f", {count_name_bytes(blob.name)} bytes, maximum {MAX_CLIP_NAME_BYTES}"
        )
        return refusal, measure
    if refusal is not None:
        return refusal, ""
    if blob.size > rules.max_bytes:
        return "clip_too_large", f", {blob.size} bytes, maximum {rules.max_bytes}"
    return None


def refuse_clip(
    result: MirrorResult, where: str, refusal: ClipRefusal, measure: str
) -> None:
    """Count the refusal and log it by the position of the blob and the measure, never its name."""
    logger.error("clip mirror: %s refused: %s%s", where, refusal, measure)
    result.refused[refusal] += 1


def copy_when_newer(
    container_client: ContainerClient,
    path: Path,
    blob: BlobProperties,
    max_bytes: int,
    where: str,
    result: MirrorResult,
) -> None:
    """Copy the blob when its file is missing or older (ifSourceNewer), then date the file as the
    blob: the next run compares two dates of the storage, whatever the clock of the container. The
    date set changes the ctime, which etl/sources/clipping.py reads: the collection sees the clip
    changed. At the same date, the size tells a second version sent within the same second,
    last_modified being to the second (RFC 1123); one of the same size is not told (limit accepted,
    #413). A file the date of which cannot be set stays copied, and counts as a failure."""
    try:
        status = path.lstat()
    except FileNotFoundError:
        status = None
    if status is not None and not stat.S_ISREG(status.st_mode):
        refuse_clip(result, where, "local_entry_not_a_file", "")
        return
    modified_ns = to_ns(blob.last_modified)
    if status is not None and (
        status.st_mtime_ns > modified_ns
        or (status.st_mtime_ns == modified_ns and status.st_size == blob.size)
    ):
        result.unchanged += 1
        return
    content = download_listed_version(container_client, blob, max_bytes)
    if content is None:
        result.left_to_next_run += 1
        return
    write_file_atomically(path, content)
    result.copied += 1
    try:
        os.utime(path, ns=(modified_ns, modified_ns), follow_symlinks=False)
    except OSError as error:
        name = name_os_error(error)
        logger.error("clip mirror: %s not dated: %s", where, name)
        result.failed[name] += 1


def to_ns(moment: datetime) -> int:
    """A moment in whole nanoseconds since EPOCH, as a file date: a float would round it."""
    return (moment - EPOCH) // ONE_MICROSECOND * 1000


def describe_mirror_result(result: MirrorResult) -> str:
    """3 blobs listed: 1 copied, 0 unchanged, 0 left to the next run, 1 left aside
    (blob_name_hidden: 1), 1 refused (clip_name_too_long: 1), 0 failed: not written or not dated."""
    listed = f"{result.listed} blob{'' if result.listed == 1 else 's'} listed"
    return (
        f"{listed}: {result.copied} copied, {result.unchanged} unchanged,"
        f" {result.left_to_next_run} left to the next run,"
        f" {describe_counter(result.left_aside, 'left aside')},"
        f" {describe_counter(result.refused, 'refused')},"
        f" {describe_counter(result.failed, 'failed')}"
    )


def describe_counter(counts: Counter[str], outcome: str) -> str:
    """0 refused, or 2 refused (clip_name_too_long: 1, clip_too_large: 1)."""
    total = sum(counts.values())
    if not total:
        return f"0 {outcome}"
    details = ", ".join(f"{name}: {count}" for name, count in sorted(counts.items()))
    return f"{total} {outcome} ({details})"
