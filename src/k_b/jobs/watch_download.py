"""The sheets of the container watch for the Mac: a blob is a sheet only by a closed list of names,
<folder>/<day>.md under a folder kb writes, and its text holds no control and no Markdown that
Obsidian would run or fetch; each is downloaded as listed.

Two identities of jobs write in watch: its names and its texts are inputs, never trusted. A name out
of the list is never logged, its position in the listing instead (conventions.md, rule 3)."""

import itertools
import logging
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from azure.storage.blob import BlobProperties, ContainerClient

from k_b.core.config import (
    BIDI_CONTROLS,
    MAX_WATCH_LISTED_BLOBS,
    MAX_WATCH_SHEET_BYTES,
)
from k_b.jobs.clip_mirror import describe_counter, download_listed_version
from k_b.jobs.exchange_storage import ExchangeStorageError, naming_storage_errors

logger = logging.getLogger(__name__)

# The name of a sheet as publish_watch sends it: its folder under veille, of one or two levels
# (models, tops/most_starred), then its day in ISO 8601. ASCII classes, not \w nor \d, which take the
# letters and the digits of other scripts; matched whole (fullmatch), as $ would let a line feed end
# it.
SHEET_NAME = re.compile(
    r"(?P<folder>[a-z_]{1,64}(?:/[a-z_]{1,64})?)"
    r"/(?P<day>[0-9]{4}-[0-9]{2}-[0-9]{2})\.md"
)
# The controls a sheet of kb holds: neutralize_text (post/vault_files.py) turns any other, and
# each of BIDI_CONTROLS, into a space.
SHEET_CONTROL_CHARACTERS = frozenset("\t\n")
CONTROL_CATEGORY = "Cc"
# A character after an even number of backslashes, none included, is not escaped (CommonMark
# 0.31.2, 2.4): kb escapes the syntax of a text of a source by one.
NOT_ESCAPED = r"(?<!\\)(?:\\\\)*"

# A blob named as a sheet, in a folder kb does not write, a subject or a top added or retired
# since: left aside, not a failure.
type LeftAsideReason = Literal["sheet_folder_unknown"]
# A blob that is not a sheet kb writes: never written, a failure at each run until it is removed.
type SheetRefusal = Literal[
    "sheet_name_refused",
    "sheet_too_large",
    "sheet_text_not_utf8",
    "sheet_text_with_control_character",
    "sheet_text_with_bidirectional_control",
    "sheet_text_with_code",
    "sheet_text_with_tilde_fence",
    "sheet_text_with_embed",
    "sheet_text_with_html",
]
# The Markdown a sheet of kb never holds, which Obsidian or a plugin would run or fetch: code (a
# span, a fence, a query of Dataview inline or in JavaScript), a fence of tildes anywhere in a
# line (a quote or a list item opens one too), an embed (a remote image, a note), HTML (a tag, a
# command of Templater). kb writes < only to open an autolink. A [ after a ! is never escaped.
ACTIVE_MARKDOWN: tuple[tuple[re.Pattern[str], SheetRefusal], ...] = (
    (re.compile(NOT_ESCAPED + "`"), "sheet_text_with_code"),
    (re.compile(NOT_ESCAPED + "~~~"), "sheet_text_with_tilde_fence"),
    (re.compile(r"!\["), "sheet_text_with_embed"),
    (re.compile(NOT_ESCAPED + "<(?!https?://)"), "sheet_text_with_html"),
)


@dataclass(frozen=True)
class SheetName:
    """The folder of veille and the day a sheet is named by."""

    folder: str
    day: str


@dataclass(frozen=True)
class ListedSheet:
    """A sheet of the listing: its folder, its day, its blob, and its place in the listing."""

    folder: str
    day: str
    blob: BlobProperties
    where: str


@dataclass
class DownloadResult:
    """The blobs of a download, counted by outcome, and what stopped it."""

    listed: int = 0
    copied: int = 0
    already_there: int = 0
    left_to_next_run: int = 0
    left_aside: Counter[str] = field(default_factory=Counter)
    refused: Counter[str] = field(default_factory=Counter)
    failed: Counter[str] = field(default_factory=Counter)
    is_truncated: bool = False
    storage_error: ExchangeStorageError | None = None

    @property
    def has_failed(self) -> bool:
        """Whether a blob was refused or a sheet not written, or the listing or the storage
        stopped the download."""
        return bool(
            self.refused or self.failed or self.is_truncated or self.storage_error
        )

    @property
    def has_done(self) -> bool:
        """Whether a sheet is in veille as in watch, copied now or before."""
        return bool(self.copied or self.already_there)


def read_sheet_name(name: str) -> SheetName | None:
    """The folder and the day a sheet is named by, read from the name of its blob as it is,
    never normalized; None when it is not one. Its folder is not checked here."""
    match = SHEET_NAME.fullmatch(name)
    if match is None or not is_day(match["day"]):
        return None
    return SheetName(match["folder"], match["day"])


def is_day(text: str) -> bool:
    """Whether text is a day of the calendar written as date.isoformat writes it."""
    try:
        return date.fromisoformat(text).isoformat() == text
    except ValueError:
        return False


def list_watch_sheets(
    container_client: ContainerClient, folders: frozenset[str], result: DownloadResult
) -> list[ListedSheet]:
    """The sheets of the container in folders, MAX_WATCH_LISTED_BLOBS blobs listed at most; each
    other blob is left aside or refused, counted in result."""
    with naming_storage_errors():
        blobs = list(
            itertools.islice(container_client.list_blobs(), MAX_WATCH_LISTED_BLOBS + 1)
        )
    if len(blobs) > MAX_WATCH_LISTED_BLOBS:
        logger.error(
            "watch download: listing stopped: more than %d blobs",
            MAX_WATCH_LISTED_BLOBS,
        )
        result.is_truncated = True
        blobs = blobs[:MAX_WATCH_LISTED_BLOBS]
    result.listed = len(blobs)
    sheets = []
    for position, blob in enumerate(blobs, start=1):
        where = f"blob {position} of {len(blobs)}"
        sheet = read_listed_sheet(blob, folders, where, result)
        if sheet is not None:
            sheets.append(sheet)
    return sheets


def read_listed_sheet(
    blob: BlobProperties, folders: frozenset[str], where: str, result: DownloadResult
) -> ListedSheet | None:
    """The sheet of the blob, or None when it is left aside or refused."""
    sheet_name = read_sheet_name(blob.name)
    if sheet_name is None:
        refuse_blob(result, where, "sheet_name_refused")
        return None
    if sheet_name.folder not in folders:
        result.left_aside["sheet_folder_unknown"] += 1
        return None
    if blob.size > MAX_WATCH_SHEET_BYTES:
        measure = f", {blob.size} bytes, maximum {MAX_WATCH_SHEET_BYTES}"
        refuse_blob(result, where, "sheet_too_large", measure)
        return None
    return ListedSheet(sheet_name.folder, sheet_name.day, blob, where)


def refuse_blob(
    result: DownloadResult, where: str, refusal: SheetRefusal, measure: str = ""
) -> None:
    """Count the refusal and log it by the place of the blob and the measure, never its name."""
    logger.error("watch download: %s refused: %s%s", where, refusal, measure)
    result.refused[refusal] += 1


def download_sheet(
    container_client: ContainerClient, sheet: ListedSheet
) -> bytes | None:
    """The bytes of the version listed, never decompressed; None when the blob was removed or
    changed since the listing, seen again by the next run."""
    content = download_listed_version(container_client, sheet.blob)
    if content is None or len(content) != sheet.blob.size:
        return None
    return content


def find_sheet_text_refusal(content: bytes) -> SheetRefusal | None:
    """Why the text is not one kb writes: not UTF-8 (a lone surrogate neither), a control
    character but tab and line feed, a bidirectional control, or active Markdown; None when it
    is."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return "sheet_text_not_utf8"
    if any(
        unicodedata.category(character) == CONTROL_CATEGORY
        and character not in SHEET_CONTROL_CHARACTERS
        for character in text
    ):
        return "sheet_text_with_control_character"
    if any(character in BIDI_CONTROLS for character in text):
        return "sheet_text_with_bidirectional_control"
    for pattern, refusal in ACTIVE_MARKDOWN:
        if pattern.search(text):
            return refusal
    return None


def describe_download_result(result: DownloadResult) -> str:
    """5 blobs listed: 1 copied, 1 already there, 1 left to the next run, 1 left aside
    (sheet_folder_unknown: 1), 1 refused (sheet_name_refused: 1), 0 failed."""
    listed = f"{result.listed} blob{'' if result.listed == 1 else 's'} listed"
    return (
        f"{listed}: {result.copied} copied, {result.already_there} already there,"
        f" {result.left_to_next_run} left to the next run,"
        f" {describe_counter(result.left_aside, 'left aside')},"
        f" {describe_counter(result.refused, 'refused')},"
        f" {describe_counter(result.failed, 'failed')}"
    )
