"""The sheets of the top rankings in the vault: one Markdown file per top and per day of
collection, then the rankings they supersede deleted from raw/ (ADR of 2026-10-19).

A sheet is curated: written once, never rewritten nor purged by K-B. Its path is made of
constants and of the day of its ranking, never of a value read from GitHub.
"""

import logging
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import NamedTuple

from k_b.core.config import TOPS_DIR_NAME, WATCH_DIR_NAME
from k_b.core.quoting import quote_value
from k_b.database.dates import format_date
from k_b.etl.raw_store import RawStore, write_file_atomically
from k_b.etl.transform import COLLECTION_NAME_FORMAT, parse_collection_name

logger = logging.getLogger(__name__)

# The format characters that reorder a line as it is displayed (Unicode bidirectional controls
# and marks, UAX #9). U+200D, which joins the emojis, is kept.
BIDI_CONTROLS = frozenset(
    "\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
)
# The characters a description loses: the controls (Cc) and the lone surrogates (Cs), which
# UTF-8 cannot encode.
REMOVED_CATEGORIES = frozenset({"Cc", "Cs"})
# The ASCII punctuation that would make syntax of a description in Markdown or Obsidian: a link,
# an embed or a wikilink ([ ]), HTML (< >), a cell of the table (|), code (`), a tag (#), a
# comment (%%), a formula ($). Each is escaped by a backslash, as CommonMark allows for any
# ASCII punctuation; the backslash too, so that a description ending with one does not escape
# the | that closes its cell.
ESCAPED_CHARACTERS = frozenset("\\[]<>|`#%$")


@dataclass(frozen=True)
class TopEntry:
    """A repository of a ranking, as its sheet shows it."""

    rank: int
    # owner/name, checked by the reader of its source.
    full_name: str
    # Built from the name by the source, never read in the response.
    url: str
    description: str | None
    # Its stars or its forks.
    count: int


@dataclass(frozen=True)
class Top:
    """A top ranking: the folder of its sheets under veille/tops/, the raw folder of its
    rankings and their reader, and the words of its sheet."""

    name: str
    folder_key: str
    read_entries: Callable[[bytes], list[TopEntry]]
    count_heading: str
    # What it ranks, after "Top <n> des".
    subject: str


@dataclass(frozen=True)
class TopSheetsOutcome:
    written_count: int
    existing_count: int
    deleted_count: int
    unreadable_count: int


class Ranking(NamedTuple):
    collected_at: datetime
    entries: list[TopEntry]


def write_top_sheets(store: RawStore, vault_dir: Path, top: Top) -> TopSheetsOutcome:
    """Write the sheet of each day of collection of top that has none, then delete the rankings
    read before the last one read: of each day, the first ranking still in raw/ gives its sheet.

    Every ranking listed is read, its sheet written or not: only a ranking read is readable, and
    only the readable ones before the last readable are deleted. An unreadable one is kept and
    counted. The folder is listed once: a ranking collected meanwhile is neither read nor
    deleted. An exception raised by a read or a write (OSError, SIGTERM) deletes nothing.
    """
    sheets_dir = vault_dir / WATCH_DIR_NAME / TOPS_DIR_NAME / top.name
    readable_keys = []
    written_count = 0
    keys = store.list_file_keys(top.folder_key)
    for key in keys:
        ranking = read_ranking(store, top, key)
        if ranking is None:
            continue
        readable_keys.append(key)
        written_count += write_sheet(sheets_dir, top, ranking)
    deleted_count = sum(store.delete(key) for key in readable_keys[:-1])
    logger.info("%s: %d superseded rankings deleted", top.name, deleted_count)
    return TopSheetsOutcome(
        written_count=written_count,
        existing_count=len(readable_keys) - written_count,
        deleted_count=deleted_count,
        unreadable_count=len(keys) - len(readable_keys),
    )


def read_ranking(store: RawStore, top: Top, key: str) -> Ranking | None:
    """The ranking of key, or None after logging why it is kept unread. Its file is never
    named in the log: a name that is not a collection time is not quoted."""
    collected_at = find_collection_time(key)
    if collected_at is None:
        logger.error(
            "%s: ranking_name_invalid, a file of its raw folder kept", top.name
        )
        return None
    try:
        entries = top.read_entries(store.read(key))
    except (ValueError, RecursionError) as error:
        # The messages of the readers give a position or a measure, never a value (#264).
        logger.error(
            "%s ranking of %s: ranking_unreadable, kept: %s %s",
            top.name,
            collected_at.date(),
            type(error).__name__,
            quote_value(str(error)),
        )
        return None
    return Ranking(collected_at, entries)


def find_collection_time(key: str) -> datetime | None:
    """The time of the collection that named the file of key, None for another name. The name
    must be the one kb collect writes: strptime also takes 2026-10-5, which would break the
    order of the names."""
    collection_name = PurePosixPath(key).stem
    try:
        collected_at = parse_collection_name(collection_name)
    except ValueError:
        return None
    if collected_at.strftime(COLLECTION_NAME_FORMAT) != collection_name:
        return None
    return collected_at


def write_sheet(sheets_dir: Path, top: Top, ranking: Ranking) -> bool:
    """Write the sheet of the day of ranking, unless it exists; whether it was written."""
    day = ranking.collected_at.date()
    sheet_path = sheets_dir / f"{day.isoformat()}.md"
    if sheet_path.exists():
        logger.info("%s sheet of %s: sheet_exists, not rewritten", top.name, day)
        return False
    write_file_atomically(sheet_path, render_sheet(top, ranking).encode("utf-8"))
    logger.info("%s sheet of %s: sheet_written", top.name, day)
    return True


def render_sheet(top: Top, ranking: Ranking) -> str:
    """The Markdown of a sheet, in French: a frontmatter, then the repositories by rank."""
    day = ranking.collected_at.date().isoformat()
    lines = [
        "---",
        f"classement: {top.name}",
        f"releve: {format_date(ranking.collected_at)}",
        f"depots: {len(ranking.entries)}",
        "---",
        "",
        f"# Top {len(ranking.entries)} des {top.subject}, relevé du {day}",
        "",
        f"| Rang | Dépôt | {top.count_heading} | Description |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {entry.rank} | [{entry.full_name}]({entry.url}) | {entry.count} |"
        f" {neutralize_description(entry.description)} |"
        for entry in ranking.entries
    ]
    return "\n".join(lines) + "\n"


def neutralize_description(description: str | None) -> str:
    """The description on one line, as text: its controls, lone surrogates and bidirectional
    controls become spaces, its whitespace one space, its syntax characters escaped. A bare URL
    is left as it is: Obsidian shows it as a link."""
    if description is None:
        return ""
    visible = "".join(
        " "
        if character in BIDI_CONTROLS
        or unicodedata.category(character) in REMOVED_CATEGORIES
        else character
        for character in description
    )
    return "".join(
        f"\\{character}" if character in ESCAPED_CHARACTERS else character
        for character in " ".join(visible.split())
    )
