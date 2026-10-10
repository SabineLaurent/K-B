"""Import the raw files into the items database (docs/specs-collecte.md, step 4).

Read, merge, then write the base in one transaction: an error in the base writes nothing there.
The log is written after the base, whole or not at all. Run again on the same raw, the import
gives the same base and the same log.
"""

import json
import os
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

from k_b.database.connection import connect_database
from k_b.items import Item
from k_b.merge import Discard, merge_items
from k_b.raw_items import Rejection, read_raw_items
from k_b.raw_store import find_stream
from k_b.source_contract import SourceKind

# The date format the CHECK constraints of schema.sql accept.
DATABASE_DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# Every field of an item but its identifier is rewritten when the item is imported again:
# a newer arXiv revision replaces the paper, under the same item_id.
UPSERT_ITEM = """
INSERT INTO item (
    source_code, source_item_id, title, url, published_at, revised_at, saved_at, summary,
    raw_data_id
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (source_code, source_item_id) DO UPDATE SET
    title = excluded.title,
    url = excluded.url,
    published_at = excluded.published_at,
    revised_at = excluded.revised_at,
    saved_at = excluded.saved_at,
    summary = excluded.summary,
    raw_data_id = excluded.raw_data_id
RETURNING item_id
"""


class MissingDatabaseError(FileNotFoundError):
    pass


class UnknownSourceError(LookupError):
    """An item's source_code has no row in the source table of the base."""


class ImportSummary(NamedTuple):
    item_count: int
    discard_count: int
    rejection_count: int


def import_items(
    raw_dir: Path,
    database_path: Path,
    log_path: Path,
    kinds: Sequence[SourceKind],
) -> ImportSummary:
    """Write the merged items of the raw files into the base, then the log of what was left out.

    The base must exist: connecting to a missing file would create an empty one.
    """
    if not database_path.is_file():
        raise MissingDatabaseError(f"{database_path} does not exist")
    reading = read_raw_items(raw_dir, kinds)
    merged = merge_items(reading.items)
    connection = connect_database(database_path)
    try:
        # The context manager commits on success and rolls back on any error.
        with connection:
            for item in merged.items:
                write_item(connection, item)
            delete_orphan_authors(connection)
    finally:
        connection.close()
    write_import_log(log_path, reading.rejections, merged.discards)
    return ImportSummary(
        len(merged.items), len(merged.discards), len(reading.rejections)
    )


def write_item(connection: sqlite3.Connection, item: Item) -> None:
    raw_data_id = write_raw_data(
        connection, item.source_code, item.collected_at, item.raw_file_path
    )
    (item_id,) = connection.execute(
        UPSERT_ITEM,
        (
            item.source_code,
            item.source_item_id,
            item.title,
            item.url,
            format_date(item.published_at),
            format_date(item.revised_at),
            format_date(item.saved_at),
            item.summary,
            raw_data_id,
        ),
    ).fetchone()
    write_authors(connection, item_id, item.authors)
    if item.repository_name is not None:
        connection.execute(
            "INSERT INTO repository (item_id, repository_name) VALUES (?, ?)"
            " ON CONFLICT (item_id) DO UPDATE SET repository_name = excluded.repository_name",
            (item_id, item.repository_name),
        )
    if item.is_vulnerability:
        connection.execute(
            "INSERT INTO vulnerability (item_id, cve) VALUES (?, ?)"
            " ON CONFLICT (item_id) DO UPDATE SET cve = excluded.cve",
            (item_id, item.cve),
        )


def write_raw_data(
    connection: sqlite3.Connection,
    source_code: str,
    collected_at: datetime,
    raw_file_path: str,
) -> int:
    source_row = connection.execute(
        "SELECT id FROM source WHERE source_code = ?", (source_code,)
    ).fetchone()
    if source_row is None:
        raise UnknownSourceError(f"source_code not in the source table: {source_code}")
    connection.execute(
        "INSERT INTO raw_data (source_id, raw_file_path, stream, collected_at)"
        " VALUES (?, ?, ?, ?) ON CONFLICT (raw_file_path) DO NOTHING",
        (
            source_row[0],
            raw_file_path,
            find_stream(raw_file_path),
            format_date(collected_at),
        ),
    )
    (raw_data_id,) = connection.execute(
        "SELECT id FROM raw_data WHERE raw_file_path = ?", (raw_file_path,)
    ).fetchone()
    return int(raw_data_id)


def write_authors(
    connection: sqlite3.Connection, item_id: int, authors: tuple[str, ...]
) -> None:
    """The authors of the item, in their order; a name repeated in the list is kept once.

    The base links an author to an item once (primary key item_id, author_id): a repeated name
    keeps its first position.
    """
    connection.execute("DELETE FROM item_author WHERE item_id = ?", (item_id,))
    for position, name in enumerate(dict.fromkeys(authors), start=1):
        connection.execute(
            "INSERT INTO author (name) VALUES (?) ON CONFLICT (name) DO NOTHING",
            (name,),
        )
        (author_id,) = connection.execute(
            "SELECT author_id FROM author WHERE name = ?", (name,)
        ).fetchone()
        connection.execute(
            "INSERT INTO item_author (item_id, author_id, position) VALUES (?, ?, ?)",
            (item_id, author_id, position),
        )


def delete_orphan_authors(connection: sqlite3.Connection) -> None:
    """An author whose items have all changed authors is personal data without use: deleted."""
    connection.execute(
        "DELETE FROM author WHERE author_id NOT IN (SELECT author_id FROM item_author)"
    )


def format_date(moment: datetime | None) -> str | None:
    return (
        None
        if moment is None
        else moment.astimezone(UTC).strftime(DATABASE_DATE_FORMAT)
    )


def write_import_log(
    log_path: Path, rejections: list[Rejection], discards: list[Discard]
) -> None:
    """One JSON line per rejection, then per duplicate removed; the file is rewritten each time.

    Written to a temporary file, then renamed over the log: a failed write leaves the previous
    log whole, and no temporary file behind.
    """
    lines = [
        {
            "kind": "rejection",
            "raw_file_path": rejection.raw_file_path,
            "reason": rejection.reason,
        }
        for rejection in rejections
    ] + [
        {
            "kind": "discard",
            "rule": discard.rule,
            "source_code": discard.item.source_code,
            "source_item_id": discard.item.source_item_id,
            "url": discard.item.url,
            "raw_file_path": discard.item.raw_file_path,
            "kept_url": discard.kept_url,
        }
        for discard in discards
    ]
    temporary_path = log_path.with_name(log_path.name + ".tmp")
    try:
        temporary_path.write_text(
            "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines)
        )
        os.replace(temporary_path, log_path)
    except BaseException:
        # BaseException: Ctrl-C during the write must not leave the temporary file either.
        temporary_path.unlink(missing_ok=True)
        raise
