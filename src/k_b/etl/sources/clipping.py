"""The Web Clipper source: copy the clips of the user's Obsidian vault as they are (E), then read
each clip into an item (T).

A clip is a Markdown file the Web Clipper extension writes into the vault: a YAML frontmatter
between two --- lines, then the text kept. The vault stays the user's: K-B reads it, never writes
to it, and copies each clip new or modified since the last collection under
raw/selected_library/clipping/ (ADR of 2026-10-09). A clip is part of the library, never of the
watch: no digest reads it (ai_api/watch_items.py).
"""

import hashlib
import logging
import os
import re
import stat
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Annotated, Any, NamedTuple

import yaml
from pydantic import BaseModel, BeforeValidator, ConfigDict, ValidationError

from k_b.core.quoting import quote_value, without_values
from k_b.etl.normalize import remove_tracking_parameters
from k_b.etl.raw_store import SELECTED_LIBRARY_DIR_NAME
from k_b.etl.source_contract import EntryReading, SourceReader, check_not_all_invalid
from k_b.items import CLIP_MAX_BYTES, Item, NonEmptyText, SourceCode, WebUrl

logger = logging.getLogger(__name__)

# The name of its raw folders, written once: its instances and its kind use it.
FOLDER_PREFIX = "clipping"
SOURCE_CODE: SourceCode = "clipper"
# The folder of the vault the default template of Web Clipper writes to (docs/specs-collecte.md).
CLIPPINGS_DIR_NAME = "Clippings"
CLIP_EXTENSION = ".md"
MAX_CLIP_BYTES = CLIP_MAX_BYTES
# The page name of a clip: the start of the SHA-256 of its file name, in hexadecimal. The same
# clip has the same name from one collection to the next, and its file name, which is its
# title, goes neither into the path of the raw nor into the import log.
PAGE_NAME_LENGTH = 16
# A file date is in nanoseconds since EPOCH; a datetime, in microseconds.
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
ONE_MICROSECOND = timedelta(microseconds=1)
FRONTMATTER_FENCE = "---"
# A day as Web Clipper writes a property of type date: YYYY-MM-DD, the year on four digits from
# 1000, so that the base writes it as it reads it. Another form (a time, a time zone, a number)
# is refused, not guessed: pydantic alone would read a number as a Unix time.
DAY = re.compile(r"[1-9][0-9]{3}-[0-9]{2}-[0-9]{2}")
# What YAML writes for an absent value; BaseLoader reads all three as text.
ABSENT_VALUES = ("", "null", "~")


class ClipTooLargeError(Exception):
    """clip_too_large: a clip of the vault is larger than MAX_CLIP_BYTES. Nothing is copied, and
    the last collection date stays: the next collection tries again."""


class ClippingSource:
    name = FOLDER_PREFIX
    extension = "md"
    acquisition_dir_name = SELECTED_LIBRARY_DIR_NAME

    def __init__(self, vault_dir: Path) -> None:
        self.vault_dir = vault_dir

    def fetch(self, last_collected_at: datetime | None) -> dict[str, bytes] | None:
        """Return each clip modified since last_collected_at (all, at the first collection), as
        it is, by page name; None when none was."""
        clips = {
            make_page_name(path): read_clip_file(path)
            for path in list_clip_files(self.vault_dir / CLIPPINGS_DIR_NAME)
            if last_collected_at is None or was_modified_since(path, last_collected_at)
        }
        if not clips:
            return None
        # Read as the import will: clips all invalid fail the source (conventions.md, rule 1).
        readings = [read_clip_safely(clip) for clip in clips.values()]
        check_not_all_invalid(
            EntryReading(
                [entry for reading in readings for entry in reading.entries],
                [
                    reason
                    for reading in readings
                    for reason in reading.rejection_reasons
                ],
            )
        )
        logger.info("clipping: %d clips copied", len(clips))
        return clips


def list_clip_files(clippings_dir: Path) -> list[Path]:
    """The clips of the folder, in name order: its Markdown files that are regular files, not
    hidden. Its subfolders are not read, and a symbolic link is left: it may point out of the
    vault."""
    return sorted(
        path
        for path in clippings_dir.iterdir()
        if not path.name.startswith(".")
        and path.name.endswith(CLIP_EXTENSION)
        and stat.S_ISREG(path.lstat().st_mode)
    )


def was_modified_since(path: Path, last_collected_at: datetime) -> bool:
    """Whether the clip was written or changed since last_collected_at. The change date counts
    too: a copy that keeps the modification date (cp -p, the Finder, a sync) is a new clip."""
    status = path.lstat()
    changed_at_ns = max(status.st_mtime_ns, status.st_ctime_ns)
    # In whole nanoseconds: a float would round a write made in the same microsecond as the
    # last collection onto it.
    last_collected_at_ns = (last_collected_at - EPOCH) // ONE_MICROSECOND * 1000
    return changed_at_ns > last_collected_at_ns


def make_page_name(path: Path) -> str:
    return hashlib.sha256(os.fsencode(path.name)).hexdigest()[:PAGE_NAME_LENGTH]


def read_clip_file(path: Path) -> bytes:
    """The bytes of the clip, read once, at most one more than the maximum: a clip that grows
    after it was listed is measured as read. O_NOFOLLOW: a file replaced by a link since it was
    listed is not followed."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as clip_file:
        content = clip_file.read(MAX_CLIP_BYTES + 1)
    if len(content) > MAX_CLIP_BYTES:
        raise ClipTooLargeError(
            f"clip_too_large: {quote_value(path.name)}: more than {MAX_CLIP_BYTES} bytes,"
            f" maximum {MAX_CLIP_BYTES} bytes"
        )
    return content


class ClipEntry(NamedTuple):
    """A clip read: the properties of its frontmatter, and its text."""

    properties: dict[str, Any]
    text: str


def read_clip(raw_clip: bytes) -> EntryReading[ClipEntry]:
    """A clip as its only entry. A clip that is not UTF-8, without frontmatter, whose frontmatter
    is not YAML or not a mapping cannot be read (conventions.md, rule 1). The error says where,
    never what: the YAML error of PyYAML quotes the text around it."""
    try:
        text = raw_clip.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"clip not UTF-8: byte {error.start}") from None
    frontmatter, body = split_frontmatter(text)
    try:
        # BaseLoader resolves no type and builds no object: only str, list and dict. A tag such
        # as !!python/object/apply is not applied: its value is read as text or list. ruff takes
        # it for an unsafe loader (S506).
        properties = yaml.load(frontmatter, Loader=yaml.BaseLoader)  # noqa: S506
    except yaml.YAMLError as error:
        raise ValueError(describe_yaml_error(error)) from None
    if not isinstance(properties, dict):
        raise ValueError("frontmatter not a mapping")
    return EntryReading([ClipEntry(properties, body)], [])


def split_frontmatter(text: str) -> tuple[str, str]:
    """The frontmatter, between the first line and the next line that is ---, and the text
    after it, as written: a --- further down is a rule of the text."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != FRONTMATTER_FENCE:
        raise ValueError("clip without frontmatter")
    for position, line in enumerate(lines[1:], start=1):
        if line.rstrip("\r\n") == FRONTMATTER_FENCE:
            return "".join(lines[1:position]), "".join(lines[position + 1 :])
    raise ValueError("clip without frontmatter: no closing line")


def describe_yaml_error(error: yaml.YAMLError) -> str:
    mark = getattr(error, "problem_mark", None)
    if mark is None:
        return "frontmatter not YAML"
    # The line in the clip: the frontmatter starts on its second line.
    return f"frontmatter not YAML: line {mark.line + 2}, column {mark.column + 1}"


def read_clip_safely(raw_clip: bytes) -> EntryReading[ClipEntry]:
    """A clip the import would reject is a rejection here, not a failure: the collection counts
    the clips all invalid."""
    try:
        reading = read_clip(raw_clip)
    except ValueError as unreadable:
        return EntryReading([], [str(unreadable)])
    try:
        for entry in reading.entries:
            ClipFrontmatter.model_validate(entry.properties)
    except ValidationError as refusal:
        return EntryReading([], [str(without_values(refusal))])
    return reading


def read_absent(value: object) -> object:
    return None if value in ABSENT_VALUES else value


def check_day_form(value: object) -> object:
    """Let pydantic read the day only in the form of Web Clipper."""
    if not isinstance(value, str) or not DAY.fullmatch(value):
        raise ValueError("not a day of Web Clipper (YYYY-MM-DD)")
    return value


ClipDay = Annotated[date, BeforeValidator(check_day_form)]


class ClipFrontmatter(BaseModel):
    """The properties of a clip read. Not read, to keep out of the base: author (a personal
    data, without use in the base), description and tags (docs/registre-traitements.md)."""

    model_config = ConfigDict(frozen=True, extra="ignore", hide_input_in_errors=True)

    title: NonEmptyText
    source: WebUrl
    created: ClipDay
    published: Annotated[ClipDay | None, BeforeValidator(read_absent)] = None


def at_midnight_utc(day: date) -> datetime:
    """A day is written at midnight UTC (docs/stockage.md), as dateAdded of CISA KEV."""
    return datetime.combine(day, time(), UTC)


def convert_clip(entry: ClipEntry, collected_at: datetime, raw_file_path: str) -> Item:
    """A clip as an item of the library, its text kept as written.

    Refused, the error names each field and its error, never its value: a title or a text is
    chosen by the user, and goes into the import log.
    """
    try:
        frontmatter = ClipFrontmatter.model_validate(entry.properties)
        return Item(
            source_code=SOURCE_CODE,
            # The key of the base: the URL normalize_item will give the item.
            source_item_id=remove_tracking_parameters(frontmatter.source),
            kind="clip",
            title=frontmatter.title,
            url=frontmatter.source,
            published_at=at_midnight_utc(frontmatter.published)
            if frontmatter.published is not None
            else None,
            saved_at=at_midnight_utc(frontmatter.created),
            summary=entry.text,
            collected_at=collected_at,
            raw_file_path=raw_file_path,
        )
    except ValidationError as error:
        raise without_values(error) from None


READER: SourceReader[ClipEntry] = SourceReader(SOURCE_CODE, read_clip, convert_clip)
