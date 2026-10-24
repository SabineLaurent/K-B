"""Write into the base what one raw file read holds: a file of items item by item, a file of
trends whole (stage 3). No function here writes a file; writing a file to disk is the business of
etl/raw_store.py (conventions.md, rule 2).

Each item, and each file of trends, is written in its own savepoint (database/savepoint.py): an
entry the base refuses is undone alone and becomes a rejection of the log of the import, and the
import goes on.

The base removes the duplicates. The writer of each kind (database/writers/, chosen by
database/writing.py) holds, in its SQL, the rule of the nature of its source: a news feed keeps
the first version seen; a state catalog keeps the version of its latest collection; a feed with
revisions keeps the newest revision. An item left out is returned with its rule and the date
it was compared with, then written to the log. Run again on the same raw, the import gives the
same base.

A file of trends of GH Archive is not made of items: its rows go to the trend table, in the same
transaction, and its rule is a news feed applied to the whole window. A Zotero entry is a state
catalog, as CISA KEV, and so is each of its highlights (decision of 2026-10-13). A clip is
known by its URL, and keeps its latest version: a clip whose content changed is written again
(decision of 2026-10-19).

Only exact duplicates are found: the same identifier within its source (a replay, collections
that overlap). The same content under another identifier is not found, a written limit without
a content fingerprint: for TLDR, another URL or another edition (decision of 2026-10-12); for
Zotero, another key, though two entries of the same arXiv paper point to the same publication
(decision of 2026-10-13); for a clip, another URL (ADR, "Collecte : clips";
docs/specs-collecte.md).
"""

import sqlite3
from dataclasses import dataclass, field

from k_b.core.quoting import quote_value
from k_b.database.savepoint import EntryRefusedError, write_in_savepoint
from k_b.database.writing import Discard, write_item, write_raw_data, write_trend_rows
from k_b.etl.import_log import TrendDiscard
from k_b.etl.raw_files import RawFile, Rejection, TrendFile
from k_b.etl.raw_store import find_stream
from k_b.etl.rejections import reject
from k_b.etl.withdrawals import (
    mark_withdrawn_vulnerabilities,
    mark_withdrawn_zotero_rows,
)
from k_b.items import Item


@dataclass(frozen=True)
class FileWriting:
    """What the writing of files gave: one file, or the sum of several.

    Every field has its empty value by default, so that a site names only what it produced.
    default_factory, not [], and so a dataclass and not a NamedTuple: the default of a
    NamedTuple is built once, at the creation of the class, and every instance that omits the
    field shares that one list.
    """

    item_count: int = 0
    discards: list[Discard] = field(default_factory=list)
    trend_discards: list[TrendDiscard] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)
    withdrawn_count: int = 0
    trend_count: int = 0


def write_file(
    connection: sqlite3.Connection, file_read: RawFile | TrendFile
) -> FileWriting:
    """Write one file read, as what it holds says: a file of trends whole, a file of items item
    by item."""
    if isinstance(file_read, TrendFile):
        return write_trend_file(connection, file_read)
    return write_items_file(connection, file_read)


def write_items_file(connection: sqlite3.Connection, raw_file: RawFile) -> FileWriting:
    """Register the file read, write each of its items, then mark as withdrawn what its
    catalog no longer lists.

    Its items are those the reading kept, normalized: the releases of a repository out of the
    tracked list are rejected, and each item kept is normalized, before (etl/transform.py). The
    file is registered even with an item the base refuses, as with an entry rejected when read:
    only a rebuild of the base reads it again.
    """
    raw_data_id = register_raw_file(connection, raw_file)
    outcomes = [
        write_item_in_savepoint(connection, item, raw_data_id)
        for item in raw_file.items
    ]
    discards = [outcome for outcome in outcomes if isinstance(outcome, Discard)]
    refusals = [outcome for outcome in outcomes if isinstance(outcome, Rejection)]
    # An item the base refuses is in its file: a catalog with one withdraws nothing.
    counted_file = raw_file._replace(
        rejection_count=raw_file.rejection_count + len(refusals)
    )
    withdrawn_count = mark_withdrawn_vulnerabilities(
        connection, counted_file, raw_data_id
    ) + mark_withdrawn_zotero_rows(connection, counted_file, raw_data_id)
    return FileWriting(
        item_count=outcomes.count(None),
        discards=discards,
        rejections=refusals,
        withdrawn_count=withdrawn_count,
    )


def write_trend_file(
    connection: sqlite3.Connection, trend_file: TrendFile
) -> FileWriting:
    """Register the file of trends and write its rows in one savepoint; return how many were
    written, and each window the base left out.

    A file of trends with a row the base refuses is refused whole (decision of Sabine of
    2026-10-13): none of its rows is written, it is not registered, and the next import reads it
    again, as an unreadable file.
    """
    raw_file_path = trend_file.raw_file.raw_file_path
    try:
        with write_in_savepoint(connection):
            raw_data_id = register_raw_file(connection, trend_file.raw_file)
            written_count, collected_at_by_window_left_out = write_trend_rows(
                connection, trend_file.rows, raw_data_id
            )
    except EntryRefusedError as refusal:
        rejection = reject(raw_file_path, f"ranking refused by the base: {refusal}")
        return FileWriting(rejections=[rejection])
    discards = [
        TrendDiscard(trend_file.raw_file, window_end, collected_at)
        for window_end, collected_at in collected_at_by_window_left_out.items()
    ]
    return FileWriting(trend_discards=discards, trend_count=written_count)


def register_raw_file(connection: sqlite3.Connection, raw_file: RawFile) -> int:
    """Register the file read under its stream, the name of its source folder."""
    return write_raw_data(
        connection,
        raw_file.source_code,
        raw_file.raw_file_path,
        find_stream(raw_file.raw_file_path),
        raw_file.collected_at,
    )


def write_item_in_savepoint(
    connection: sqlite3.Connection, item: Item, raw_data_id: int
) -> Discard | Rejection | None:
    """Write the item in its savepoint; an item the base refuses is undone alone and returned
    as a rejection, an item it left out as a discard.

    A Zotero entry, its highlights and the publication it cites are written by one writer:
    they share the savepoint.
    """
    try:
        with write_in_savepoint(connection):
            return write_item(connection, item, raw_data_id)
    except EntryRefusedError as refusal:
        return reject(
            item.raw_file_path,
            f"{item.kind} {quote_value(item.source_item_id)} refused by the base: "
            f"{refusal}",
        )
